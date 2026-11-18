"""GitHub'dan yeni sürüm denetimi (yalnız sunucu; FastAPI'siz iş mantığı).

Sunucu günde en çok bir kez deponun "son sürüm" kaydına bakar ve yeni sürüm varsa panoda YALNIZ yöneticiye
haber verir. Kendiliğinden indirme ya da kurma YOKTUR; tahtalar internete çıkmaz (ajan değişmedi).

Giden veri yok: tek bir GET; istekte yalnız genel `User-Agent` ("tahta-kontrol") ve `Accept` başlığı vardır.
Okul adı, tahta sayısı, kimlik, kurulu sürüm numarası gönderilmez; sorgu parametresi ve telemetri yoktur.
(GitHub, her internet isteğinde olduğu gibi, isteğin geldiği internet adresini görür.)

Gelen veri güvenilmez girdidir: yanıt en çok 256 KiB okunur, yönlendirme izlenmez, etiket yalnız
`^v?\\d+(\\.\\d+){1,3}$` ise kabul edilir; bağlantı yanıttaki `html_url`'den DEĞİL, doğrulanmış sürümden sabit
kalıpla kurulur; sürüm notu metni hiçbir yere yazılmaz. Taslak ve ön sürüm yok sayılır.

Ağ çağrısı olay döngüsünde ve `vt.KILIT` altında yapılmaz: zamanlayıcı işi ayrı (daemon) iş parçacığında
yürür, kapanış onu beklemez. Başarısızlık sessizdir (yalnız Ayarlar'da "ulaşılamadı"); başarısız deneme de
günlük hakkı tüketir, sonraki deneme ertesi gündür. Ayar kapalıyken hiç istek çıkmaz ("Şimdi denetle" dahil).
Bir denetimin TOPLAM süresi (ad çözümlemesi, bağlantı, başlıklar, gövde) 5 sn ile sınırlıdır; kapanışta süren
bekleme hemen bırakılır ("Şimdi denetle" de kapanışı tutmaz). Saklanan durum (sürüm ve zaman) okunurken
yeniden doğrulanır: bozuk kayıt panoyu ya da Ayarlar'ı düşüremez.
"""

from __future__ import annotations

import json
import logging
import re
import ssl
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime
from zoneinfo import ZoneInfo

from . import __version__, vt

gunluk = logging.getLogger("tahta-sunucu")
ISTANBUL = ZoneInfo("Europe/Istanbul")

DEPO = "aalidemirci/tahta-kontrol"
API_ADRESI = f"https://api.github.com/repos/{DEPO}/releases/latest"
SURUM_SAYFASI = f"https://github.com/{DEPO}/releases/tag/v{{surum}}"
BASLIKLAR = {"User-Agent": "tahta-kontrol", "Accept": "application/vnd.github+json"}
ZAMAN_ASIMI_SN = 5
YANIT_SINIRI = 256 * 1024
ARALIK_SN = 86400  # günde en çok bir kendiliğinden denetim
EN_GEC_ZAMAN = 4102444800  # 01.01.2100; saklanan zaman bu aralığın dışındaysa bozuk sayılır
ELLE_ARALIK_SN = 60  # "Şimdi denetle" art arda basılırsa yeni istek çıkmaz
ETIKET = re.compile(r"v?\d+(\.\d+){1,3}", re.ASCII)

AYAR_ANAHTARI = "guncelleme_denetimi"
DURUM_ANAHTARI = "guncelleme_durumu"  # {"zaman": epoch, "sonuc": "tamam" | "ulasilamadi", "surum": "x.y.z" | ""}
VARSAYILAN = True


class GuncellemeHatasi(Exception):
    """GitHub'a ulaşılamadı ya da yanıt kabul edilmedi (ayrıntı yalnız günlüğe, hata ayıklama düzeyinde)."""


# ---- sürüm ve yanıt (saf) -------------------------------------------------------------------------
def surum_coz(metin) -> tuple[int, ...] | None:
    """"v0.13.10" → (0, 13, 10, 0); kalıba uymayan her şey None. Karşılaştırma sayısaldır (0.13.10 > 0.13.9)."""
    if not isinstance(metin, str) or len(metin) > 40 or not ETIKET.fullmatch(metin):
        return None
    parcalar = [int(p) for p in metin.removeprefix("v").split(".")]
    return tuple(parcalar + [0] * (4 - len(parcalar)))


def surum_metni(metin) -> str:
    """Doğrulanmış etiketin "v"siz yazımı ("v0.13.0" → "0.13.0"); geçersizse ""."""
    return metin.removeprefix("v") if surum_coz(metin) else ""


def yanit_coz(ham: bytes) -> str:
    """Yanıttan yayımlanmış son sürümün numarası; taslak, ön sürüm ya da bozuk etiket ise "" (yok sayılır).

    Yanıt JSON nesnesi değilse GuncellemeHatasi. Yalnız `tag_name`, `draft`, `prerelease` okunur.
    """
    try:
        veri = json.loads(ham.decode("utf-8"))
    except (ValueError, RecursionError) as hata:
        raise GuncellemeHatasi("yanıt çözülemedi") from hata
    if not isinstance(veri, dict):
        raise GuncellemeHatasi("yanıt nesne değil")
    if veri.get("draft") is not False or veri.get("prerelease") is not False:
        return ""
    return surum_metni(veri.get("tag_name"))


def yeni_mi(son: str, kurulu: str) -> bool:
    a, b = surum_coz(son), surum_coz(kurulu)
    return bool(a and b and a > b)


def surum_adresi(surum: str) -> str:
    """Sürüm sayfası SABİT kalıptan kurulur; doğrulanmamış metinle çağrılırsa ValueError."""
    if not surum_coz(surum):
        raise ValueError("geçersiz sürüm")
    return SURUM_SAYFASI.format(surum=surum.removeprefix("v"))


# ---- ağ ---------------------------------------------------------------------------------------------
class _YonlendirmeYok(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):  # yönlendirme izlenmez (yanıt HTTPError olur)
        return None


def _ac(istek: urllib.request.Request, zaman_asimi: float):
    # ssl.create_default_context: sertifika ve ana makine adı doğrulaması açık; Windows'ta sistem deposunu
    # kullanır (PyInstaller paketinde de). Sistemin vekil (proxy) ayarı urllib'in olağan yoluyla geçerlidir.
    acici = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=ssl.create_default_context()), _YonlendirmeYok()
    )
    return acici.open(istek, timeout=zaman_asimi)


def github_getir(ac: Callable | None = None) -> bytes:
    """Tek GET; gövde yok, sorgu parametresi yok. Hata, zaman aşımı, 200 dışı yanıt ve dev yanıt → GuncellemeHatasi.

    `ac(istek, zaman_asimi)` testlerde sahte verilir; varsayılan gerçek ağdır (testlerde conftest kapatır).
    Buradaki süre denetimi yalnız okumalar ARASINDADIR (soket zaman aşımı her okumada yeniden başlar; ad
    çözümlemesi ona hiç bağlı değildir); toplam süreyi kesin olarak `denetle` sınırlar.
    """
    istek = urllib.request.Request(API_ADRESI, headers=BASLIKLAR, method="GET")
    bitis = time.monotonic() + ZAMAN_ASIMI_SN
    try:
        with (ac or _ac)(istek, ZAMAN_ASIMI_SN) as yanit:
            if getattr(yanit, "status", 200) != 200:
                raise GuncellemeHatasi(f"HTTP {yanit.status}")
            oku = getattr(yanit, "read1", None) or yanit.read  # read1: tek soket okuması; damlayan gövdede asılmaz
            parcalar, toplam = [], 0
            while True:
                if time.monotonic() > bitis:
                    raise GuncellemeHatasi("zaman aşımı")
                parca = oku(16384)
                if not parca:
                    break
                toplam += len(parca)
                if toplam > YANIT_SINIRI:
                    raise GuncellemeHatasi("yanıt çok büyük")
                parcalar.append(parca)
    except GuncellemeHatasi:
        raise
    except (OSError, ValueError, urllib.error.URLError) as hata:  # ağ, TLS, zaman aşımı, HTTP hatası
        raise GuncellemeHatasi(type(hata).__name__) from hata
    return b"".join(parcalar)


def _sinirli_getir(getirici: Callable[[], bytes], sure: float, iptal: threading.Event | None) -> bytes:
    """Getiriciyi kısa ömürlü (daemon) iş parçacığında çalıştırır; `sure` dolunca ya da `iptal` gelince bırakır.

    Ad çözümlemesi + bağlantı + başlıklar + gövde TOPLAMI böylece sınırlanır: yanıtı bayt bayt damlatan bir ağ
    aygıtı çağıranı (ve `Denetleyici._ag` kilidini) soket zaman aşımının katları kadar tutamaz. Bırakılan iş
    parçacığı kendi soket zaman aşımıyla söner; sonucu hiçbir yere yazılmaz.
    """
    kutu: dict = {}
    bitti = threading.Event()

    def calis():
        try:
            kutu["veri"] = getirici()
        except BaseException as hata:  # iş parçacığından dışarı hata sızmaz; çağırana aktarılır
            kutu["hata"] = hata
        finally:
            bitti.set()

    threading.Thread(target=calis, name="guncelleme-ag", daemon=True).start()
    bitis = time.monotonic() + sure
    while not bitti.wait(min(0.1, max(0.0, bitis - time.monotonic()))):
        if iptal is not None and iptal.is_set():
            raise GuncellemeHatasi("kapanış")
        if time.monotonic() >= bitis:
            raise GuncellemeHatasi("zaman aşımı")
    if "hata" in kutu:
        raise kutu["hata"]
    return kutu["veri"]


def denetle(
    getirici: Callable[[], bytes] | None = None,
    sure: float = ZAMAN_ASIMI_SN,
    iptal: threading.Event | None = None,
) -> dict:
    """Bir denetim: {"sonuc": "tamam", "surum": "x.y.z" | ""} ya da {"sonuc": "ulasilamadi", "surum": ""}.

    Hiçbir hata dışarı çıkmaz ve çağrı en çok `sure` saniye sürer (`_sinirli_getir`); `iptal` kapanışta
    beklemeyi hemen keser. Kurulu sürüm bu işleve GİRMEZ (dışarıya gidemez); karşılaştırma `gorunum`dedir.
    """
    try:
        return {"sonuc": "tamam", "surum": yanit_coz(_sinirli_getir(getirici or github_getir, sure, iptal))}
    except GuncellemeHatasi as hata:
        gunluk.debug("Güncelleme denetimi: GitHub'a ulaşılamadı (%s).", hata)
    except Exception:  # getirici ne atarsa atsın program etkilenmez
        gunluk.debug("Güncelleme denetimi başarısız.", exc_info=True)
    return {"sonuc": "ulasilamadi", "surum": ""}


# ---- ayar ve durum ----------------------------------------------------------------------------------
def etkin(b) -> bool:
    deger = vt.ayar_al(b, AYAR_ANAHTARI)
    return VARSAYILAN if deger is None else bool(deger)


def _zaman_coz(deger) -> int:
    """Saklanan denetim zamanı da güvenilmez girdidir (bozuk ya da geri yüklenmiş veritabanı): geçersizse 0."""
    if isinstance(deger, bool) or not isinstance(deger, int | float) or not 0 < deger < EN_GEC_ZAMAN:
        return 0
    return int(deger)


def _zaman_metni(zaman: int) -> str:
    try:
        return datetime.fromtimestamp(zaman, ISTANBUL).strftime("%d.%m.%Y %H:%M") if zaman else ""
    except (OverflowError, OSError, ValueError):
        return ""


def durum_al(b) -> dict:
    d = vt.ayar_al(b, DURUM_ANAHTARI)
    if not isinstance(d, dict):
        return {}
    return {
        "zaman": _zaman_coz(d.get("zaman")),
        "sonuc": "tamam" if d.get("sonuc") == "tamam" else "ulasilamadi",
        "surum": surum_metni(d.get("surum")),  # saklanan değer de yeniden doğrulanır
    }


def durum_yaz(b, sonuc: dict, an: int) -> dict:
    """Başarısız denemede bilinen son sürüm korunur (pano notu bir ağ kesintisiyle kaybolmasın)."""
    surum = sonuc["surum"] if sonuc["sonuc"] == "tamam" else durum_al(b).get("surum", "")
    durum = {"zaman": int(an), "sonuc": sonuc["sonuc"], "surum": surum}
    vt.ayar_yaz(b, DURUM_ANAHTARI, durum)
    return durum


def gerekli_mi(b, an: int) -> bool:
    """Ayar açıksa ve son denemeden (başarılı ya da başarısız) bu yana bir gün geçtiyse."""
    if not etkin(b):
        return False
    zaman = durum_al(b).get("zaman", 0)
    return not zaman or an - zaman >= ARALIK_SN or zaman > an + 300  # saat geri alındıysa takılı kalmasın


def gorunum(b, kurulu: str = __version__) -> dict:
    """Ayarlar ve pano bağlamı. `yeni`: {"surum", "adres"} ya da None (ayar kapalıyken hep None)."""
    acik = etkin(b)
    durum = durum_al(b)
    yeni = None
    if acik and durum.get("surum") and yeni_mi(durum["surum"], kurulu):
        yeni = {"surum": durum["surum"], "adres": surum_adresi(durum["surum"])}
    if not durum:
        sonuc = "Henüz denetlenmedi."
    elif durum["sonuc"] != "tamam":
        sonuc = "GitHub'a ulaşılamadı."
    elif yeni:
        sonuc = f"Yeni sürüm {yeni['surum']} yayımlanmış."
    else:
        sonuc = "Kurulu sürüm güncel."
    zaman = _zaman_metni(durum.get("zaman", 0))
    return {"acik": acik, "kurulu": kurulu, "zaman": zaman, "sonuc": sonuc, "yeni": yeni, "denetlendi": bool(durum)}


# ---- zamanlayıcı ve elle denetim ----------------------------------------------------------------------
class Denetleyici:
    """Günlük denetimi ana zamanlayıcıyı bekletmeden yürütür (yedek_is.YedekIsleyici düzeni).

    `getirici` verilmezse çağrı anındaki `guncelleme.github_getir` kullanılır (testler modül adını değiştirir).
    """

    def __init__(self, getirici: Callable[[], bytes] | None = None):
        self._getirici = getirici
        self._kilit = threading.Lock()  # iş parçacığı kaydı ve "bugün denendi mi" kararı; ağ çağrısında tutulmaz
        self._ag = threading.Lock()  # aynı anda tek istek
        self._kapandi = False
        self._kapanis = threading.Event()  # süren ağ beklemesini kapanışta keser
        self._parca: threading.Thread | None = None
        self._son_deneme = 0  # durum yazılamasa bile fırtına olmasın

    def _bir_denetim(self, elle: bool = False) -> dict | None:
        """Ağ çağrısı (veritabanı bağlantısı açık DEĞİLKEN) ve sonucun yazılması. Sonuç yazılmadıysa None.

        Karar `_ag` kilidi alındıktan SONRA yeniden verilir: kilit beklenirken başka bir denetim bittiyse
        ikinci istek çıkmaz (elle denetim onun sonucunu `"taze": True` ile döndürür).
        """
        if not self._ag.acquire(timeout=ZAMAN_ASIMI_SN + 2):
            return None
        try:
            with vt.islem() as b:
                if not etkin(b):  # iş başlamadan hemen önce kapatıldıysa istek çıkmaz
                    return None
                durum = durum_al(b)
                an = vt.simdi()
                if elle and durum and 0 <= an - durum["zaman"] < ELLE_ARALIK_SN:
                    return {**durum, "taze": True}
                if not elle and not gerekli_mi(b, an):
                    return None
            if self._kapanis.is_set():  # kapanıştan sonra ağ çağrısına hiç başlanmaz
                return None
            self._son_deneme = an
            sonuc = denetle(self._getirici, iptal=self._kapanis)
            if self._kapanis.is_set():
                return None
            with vt.islem() as b:
                return durum_yaz(b, sonuc, vt.simdi())
        finally:
            self._ag.release()

    def zamanla(self, simdi: datetime | None = None) -> bool:
        """Zamanlayıcı işi (20 sn'de bir): gerekiyorsa denetimi arka planda başlatır ve hemen döner."""
        an = int(simdi.timestamp()) if simdi else vt.simdi()
        with self._kilit:  # karar ve başlatma tek kilit bloğunda: eşzamanlı çağrılar tek iş başlatır
            if self._kapandi or (self._parca is not None and self._parca.is_alive()):
                return False
            if self._son_deneme and 0 <= an - self._son_deneme < ARALIK_SN:
                return False
            with vt.islem() as b:
                if not gerekli_mi(b, an):
                    return False
            self._son_deneme = an
            parca = threading.Thread(target=self._calistir, name="guncelleme-denetimi", daemon=True)
            parca.start()
            self._parca = parca
        return True

    def _calistir(self) -> None:
        try:
            self._bir_denetim()
        except Exception:  # veritabanı yazılamadıysa da sessiz; sonraki deneme ertesi gün
            gunluk.debug("Güncelleme denetimi sonucu yazılamadı.", exc_info=True)

    def simdi_denetle(self) -> dict | None:
        """"Şimdi denetle": çağıranın iş parçacığında (web ucu `asyncio.to_thread` ile) bir denetim.

        Ayar kapalıysa None (istek çıkmaz). Son denemeden bu yana ELLE_ARALIK_SN geçmediyse istek çıkmaz;
        saklanan durum `"taze": True` ile döner (süren kendiliğinden denetim beklenir, ikinci istek çıkmaz).
        Kapanışta hemen döner; o zaman sonuç yazılmaz, saklanan durum (yoksa "ulaşılamadı") döner.
        """
        with vt.islem() as b:
            if not etkin(b):
                return None
        durum = self._bir_denetim(elle=True)
        if durum is not None:
            return durum
        with vt.islem() as b:
            if not etkin(b):
                return None
            return {**(durum_al(b) or {"zaman": 0, "sonuc": "ulasilamadi", "surum": ""}), "taze": True}

    def bekle(self, zaman_asimi: float = 5) -> bool:
        """Süren arka plan işini bekler (testler için)."""
        parca = self._parca
        if parca is not None:
            parca.join(zaman_asimi)
            return not parca.is_alive()
        return True

    def durdur(self) -> None:
        """Kapanış: yeni iş başlamaz, süren işin sonucu yazılmaz. BEKLEMEZ (kapanış bütçesi değişmez)."""
        with self._kilit:
            self._kapandi = True
        self._kapanis.set()
