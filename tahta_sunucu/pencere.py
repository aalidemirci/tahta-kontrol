"""Masaüstü durum penceresi (kısayolların açtığı).

Kurulu programda sunucu bir Windows hizmetidir (tahta_sunucu.hizmet); pencere onu
BAŞLATMAZ, yalnız durumunu gösterir ve paneli açar. Pencereyi kapatmak sunucuyu
durdurmaz. Kip, açılışta `/yerel/durum` yanıtına ve hizmetin durumuna göre seçilir:

- calisiyor          : sunucu yanıt veriyor (hizmet ya da geliştirme sunucusu) → bilgi.
- hizmet_calismiyor  : hizmet kurulu ama yanıt yok → "Hizmeti başlat" (UAC sorar).
- kurulu_degil       : paketli program ama hizmet yok → yeniden kurun (sunucu açılmaz;
                       hizmetle çift çalışma olmasın). Yalnız sc "hizmet yok" (1060) deyince.
- okunamadi          : (0.21.0, durum uygulaması) sc query bu kez okunamadı → yeniden denenir.
- gelistirme         : `uv run … pencere` → sunucuyu pencere içinde çalıştırır (eski davranış).

0.21.0: kurulu programda pencere bildirim alanında simgeyle durur (tepsi.py): X pencereyi gizler, süreç
simgede kalır, gerçek çıkış simge menüsündeki "Çık"tır; durum 15 sn arayla ayrı iş parçacığında okunur ve
pencere/simge değişince güncellenir. `pencere --gizli` pencere açmadan yalnız simgeyi getirir (kurucudaki
isteğe bağlı "Tahta Kontrol durum simgesi" oturum açılışı kısayolu; kural 28 istisnası). Bu yolların HİÇBİRİ sunucu açmaz: Sunucu yalnız geliştirme kipinde
(`_gelistirme_penceresi`) içe aktarılır. Geliştirmede bildirim alanı yoktur (TAHTA_TEPSI_DENE=1 ile elle
denenebilir; o kip de sunucu açmaz).

Pencere hizmetin veri dizinine (ProgramData) dokunmaz; kendi günlüğü
`%LOCALAPPDATA%\\TahtaKontrol\\pencere.log`'dur.
"""

from __future__ import annotations

import json
import logging
import queue
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
from tkinter import messagebox

from . import __version__, ayar, tepsi

DURUMLAR = (
    "STOPPED",
    "START_PENDING",
    "STOP_PENDING",
    "RUNNING",
    "CONTINUE_PENDING",
    "PAUSE_PENDING",
    "PAUSED",
)
_DURUM_DESENI = re.compile(r":\s*(\d+)\s+(" + "|".join(DURUMLAR) + r")\b")
HIZMET_YOK_KODU = 1060  # ERROR_SERVICE_DOES_NOT_EXIST
DURUM_TURKCE = {
    "STOPPED": "durdurulmuş",
    "START_PENDING": "başlatılıyor",
    "STOP_PENDING": "durduruluyor",
    "RUNNING": "çalışıyor ama yanıt vermiyor",
    "PAUSED": "duraklatılmış",
}
SON_YEDEK_ESKI_SN = 3 * 86400
ACILIS_BEKLEME_SN = 20


# ---- saf mantık (testli) ----------------------------------------------------------------
def sc_durumu_coz(cikti: str, cikis_kodu: int) -> str | None:
    """`sc.exe query TahtaKontrol` çıktısından durum. Hizmet yoksa "yok", anlaşılmazsa None.

    sc.exe alan adları her dilde İngilizcedir ("STATE : 4 RUNNING"); yine de yalnız sayı +
    durum adı deseni aranır.
    """
    if cikis_kodu == HIZMET_YOK_KODU:
        return "yok"
    eslesme = _DURUM_DESENI.search(cikti or "")
    return eslesme.group(2) if eslesme else None


_CIKIS_DESENI = re.compile(r"SERVICE_EXIT_CODE\s*:\s*(\d+)")
# Hizmetin kendi çıkış kodları (hizmet.py) → durum penceresi açıklaması.
HIZMET_CIKIS_ACIKLAMASI = {
    3: "eski veri taşınmayı bekliyor ya da taşıma yarıda kalmış (TASIMA-BEKLIYOR.txt / TASIMA-SURUYOR.txt)",
}


def sc_cikis_kodu_coz(cikti: str) -> int | None:
    """`sc.exe query` çıktısındaki SERVICE_EXIT_CODE (hizmetin kendi çıkış kodu); yoksa None."""
    eslesme = _CIKIS_DESENI.search(cikti or "")
    return int(eslesme.group(1)) if eslesme else None


def kip_sec(durum: dict | None, hizmet_durumu: str | None, paketli: bool) -> str:
    if durum is not None:
        return "calisiyor"
    if hizmet_durumu not in (None, "yok"):
        return "hizmet_calismiyor"
    if paketli:
        return "kurulu_degil"
    return "gelistirme"


def uyarilar(durum: dict, simdi: float | None = None) -> list[str]:
    """Durum penceresinde gösterilecek uyarılar (sır içermez)."""
    simdi = time.time() if simdi is None else simdi
    sonuc = []
    if not durum.get("yedek_parolasi_var"):
        sonuc.append("Yedek parolası belirlenmedi; otomatik yedek alınmıyor (Panel → Yedekler).")
    else:
        son = durum.get("son_yedek") or {}
        if son.get("basarili") is False:
            sonuc.append("Son yedek alınamadı (Panel → Yedekler).")
        elif not son.get("zaman") or simdi - float(son["zaman"]) > SON_YEDEK_ESKI_SN:
            sonuc.append("Son üç günde yedek alınmadı (Panel → Yedekler).")
    if durum.get("hizmet"):
        sonuc.append(
            "Bu bilgisayar uykuya geçerse tahtalar çevrimdışı kalır; güç ayarlarında uykuyu kapatın."
        )
    return sonuc


# ---- işletim sistemi ----------------------------------------------------------------------
def yerel_durum_oku(zaman_asimi: float = 2.0) -> dict | None:
    adres = f"http://127.0.0.1:{ayar.HTTP_PORT}/yerel/durum"
    try:
        with urllib.request.urlopen(adres, timeout=zaman_asimi) as yanit:  # noqa: S310 - sabit yerel adres
            return json.loads(yanit.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def _sc_sorgu() -> tuple[str, int] | None:
    if not sys.platform.startswith("win"):
        return None
    try:
        sonuc = subprocess.run(
            ["sc.exe", "query", ayar.HIZMET_ADI],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return sonuc.stdout, sonuc.returncode


def hizmet_durumu() -> str | None:
    sorgu = _sc_sorgu()
    return sc_durumu_coz(*sorgu) if sorgu else None


def hizmet_cikis_kodu() -> int | None:
    sorgu = _sc_sorgu()
    return sc_cikis_kodu_coz(sorgu[0]) if sorgu else None


def hizmeti_baslat() -> None:
    """Yönetici onayı (UAC) isteyerek `sc start TahtaKontrol` çalıştırır. ShellExecuteW istisna fırlatmaz:
    32 ya da küçük dönüş başarısızlıktır (5: UAC'de "Hayır" ya da erişim reddi) → OSError."""
    import ctypes

    kod = int(ctypes.windll.shell32.ShellExecuteW(None, "runas", "sc.exe", f"start {ayar.HIZMET_ADI}", None, 0))
    if kod <= 32:
        neden = "yönetici onayı verilmedi" if kod == 5 else f"Windows hata kodu {kod}"
        raise OSError(f"sc.exe çalıştırılamadı ({neden}).")


def baslatma_sonucu_metni(durum: str | None, cikis_kodu: int | None) -> str | None:
    """"Hizmeti başlat"tan birkaç saniye sonra hizmet hâlâ çalışmıyorsa gösterilecek metin; çalışıyorsa None."""
    if durum in ("RUNNING", "START_PENDING"):
        return None
    metin = "Hizmet başlatılamadı ya da hemen durdu."
    if cikis_kodu:
        metin += f" Hizmetin çıkış kodu: {cikis_kodu}"
        if cikis_kodu in HIZMET_CIKIS_ACIKLAMASI:
            metin += f" ({HIZMET_CIKIS_ACIKLAMASI[cikis_kodu]})"
        metin += "."
    return metin + f"\n\nAyrıntı (yönetici olarak): {ayar.hizmet_veri_dizini()}\\gunluk\\sunucu.log"


# ---- pencere ------------------------------------------------------------------------------
def _gunluk_kur() -> None:
    if ayar.paketli_windows():
        dizin = ayar.eski_veri_dizini()  # kullanıcının kendi klasörü; hizmetin verisi değil
        dizin.mkdir(parents=True, exist_ok=True)
        dosya = dizin / "pencere.log"
    else:
        dosya = ayar.veri_dizini() / "sunucu.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        filename=str(dosya),
        encoding="utf-8",
    )


def _baslik(cerceve, metin: str, alt: str = "") -> None:
    tk.Label(cerceve, text=metin, font=("Segoe UI", 14, "bold"), justify="left").pack(anchor="w")
    if alt:
        tk.Label(cerceve, text=alt, fg="#555", justify="left").pack(anchor="w", pady=(0, 12))


def _adresler(cerceve, yerel: str, ag: list[str]) -> None:
    tk.Label(cerceve, text="Bu bilgisayardan panel adresi:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
    tk.Label(cerceve, text=yerel, fg="#1d4ed8").pack(anchor="w", pady=(0, 8))
    tk.Label(cerceve, text="Diğer idari bilgisayarlardan panel adresi:", font=("Segoe UI", 9, "bold")).pack(
        anchor="w"
    )
    for adres in ag or ["(ağ bağlantısı bulunamadı)"]:
        kutu = tk.Entry(cerceve, width=42, relief="flat", fg="#1d4ed8")
        kutu.insert(0, adres)
        kutu.configure(state="readonly")
        kutu.pack(anchor="w")
    tk.Label(
        cerceve,
        text=(
            "Diğer bilgisayarlarda tarayıcı ilk açılışta sertifika uyarısı gösterir;\n"
            '"Gelişmiş" → "siteye ilerle" ile devam edilir.'
        ),
        fg="#555",
        justify="left",
    ).pack(anchor="w", pady=(4, 10))


def calistir(gizli: bool = False) -> int:
    """Durum penceresi. Kurulu programda (ya da TAHTA_TEPSI_DENE=1 ile geliştirmede) bildirim alanı simgesiyle
    çalışır ve SUNUCU AÇMAZ; `gizli` ile pencere açılmadan yalnız simge gelir.
    Geliştirmede (hizmet yok) sunucu pencere içinde çalışır; orada bildirim alanı yoktur."""
    _gunluk_kur()
    if ayar.paketli_windows() or tepsi.deneme_kipi():
        return _durum_uygulamasi(gizli, tepsi_acik=True)
    if gizli:
        # Gizli kip yalnız durum simgesi içindir; geliştirmede sunucu açan pencereye hiçbir yoldan düşmez.
        ileti = f"pencere --gizli yalnız kurulu programda (ya da {tepsi.DENEME_DEGISKENI}=1 ile) çalışır."
        logging.warning(ileti)
        print(ileti, file=sys.stderr)
        return 2
    if _gelistirme_kipi_mi():
        return _gelistirme_penceresi()
    return _durum_uygulamasi(False, tepsi_acik=False)


def _gelistirme_kipi_mi() -> bool:
    """Geliştirmede: ne sunucu yanıt veriyor ne hizmet kurulu → pencere sunucuyu kendisi çalıştırır."""
    durum = yerel_durum_oku()
    hizmet = hizmet_durumu() if durum is None else None
    bitis = time.time() + ACILIS_BEKLEME_SN
    while durum is None and hizmet in ("START_PENDING", "RUNNING") and time.time() < bitis:
        # Hizmet yeni başladıysa sunucu birkaç saniyede yanıt verir (ilk açılışta sertifika üretir).
        time.sleep(1)
        durum = yerel_durum_oku()
        hizmet = hizmet_durumu() if durum is None else None
    kip = kip_sec(durum, hizmet, False)
    logging.info("Durum penceresi: %s", kip)
    return kip == "gelistirme"


def pencere_kipi(anlik: tepsi.Anlik | None) -> str:
    """Durum uygulamasının kipi. `kip_sec`'e her zaman paketli=True verilir: bu uygulama "gelistirme" kipine
    (sunucu açan pencere) hiçbir durumda geçmez."""
    if anlik is None:
        return "okunuyor"
    if anlik.bekleniyor:
        return "bekleniyor"
    if anlik.durum is None and anlik.hizmet is None:
        # sc query bu kez okunamadı (zaman aşımı, anlaşılmayan çıktı): "kurulu değil" DEĞİLDİR; yeniden kurulum
        # öğüdü yalnız sc "hizmet yok" (1060) deyince çizilir.
        return "okunamadi"
    return kip_sec(anlik.durum, anlik.hizmet, True)


def bekleniyor_metni(hizmet: str | None, baslatildi: bool) -> tuple[str, str]:
    """"bekleniyor" kipinin (başlık, alt satır). "Hizmet yeni başladı" yalnız hizmet gerçekten başlarken
    (START_PENDING / CONTINUE_PENDING) ya da kullanıcı bu pencereden "Hizmeti başlat" dedikten sonra yazılır;
    açılışta zaten RUNNING olup yanıt vermeyen hizmet saatlerdir askıda olabilir: orada nötr metin."""
    if baslatildi or hizmet in ("START_PENDING", "CONTINUE_PENDING"):
        return "Sunucu başlatılıyor", "Hizmet yeni başladı; sunucu birkaç saniyede yanıt verir."
    return "Sunucunun yanıtı bekleniyor", "Hizmet çalışıyor; sunucunun yanıtı bekleniyor."


def _durum_uygulamasi(gizli: bool, tepsi_acik: bool) -> int:
    olaylar: queue.Queue = queue.Queue()
    simge = None
    _mutex = None  # süreç boyunca tutulur; bırakılırsa tek örnek engeli kalkar
    if tepsi_acik:
        _mutex, ilk = tepsi.tek_ornek_al()
        if not ilk:  # bu oturumda zaten açık: onu göster (gizli açılışta hiçbir şey yapma)
            if not gizli and not tepsi.var_olani_goster():
                logging.warning("Durum simgesi bu oturumda açık ama penceresine ulaşılamadı.")
                tepsi.uyari_kutusu(tepsi.IKINCI_ORNEK_UYARISI)
            return 0
        simge = tepsi.Tepsi(olaylar)
        if not simge.baslat():
            logging.warning("Bildirim alanı simgesi kurulamadı; pencere kapatılınca program kapanır.")
            simge = None
    if gizli and simge is None:
        return 1
    izleyici = tepsi.DurumIzleyici(olaylar, yerel_durum_oku, hizmet_durumu)
    uygulama = DurumUygulamasi(olaylar, izleyici, simge, gizli=gizli)
    izleyici.baslat()
    try:
        return uygulama.calistir()
    finally:
        izleyici.durdur()
        if simge is not None:
            simge.kapat()


class DurumUygulamasi:
    """Tek Tk kökü; içerik bir çerçevede durum değiştikçe yeniden çizilir. Simge varsa X pencereyi gizler
    (süreç bildirim alanında kalır), gerçek çıkış simge menüsündeki "Çık"tır; simge yoksa X kapatır.
    Sunucu açmaz (kip_sec'e paketli=True; bkz. pencere_kipi)."""

    def __init__(
        self, olaylar: queue.Queue, izleyici: tepsi.DurumIzleyici, simge: tepsi.Tepsi | None, gizli: bool
    ):
        self.olaylar = olaylar
        self.izleyici = izleyici
        self.simge = simge
        self.anlik: tepsi.Anlik | None = None
        self.kip = "okunuyor"
        self.kararli: str | None = None
        self.balon_gosterildi = False
        self.baslatildi = False  # bu pencereden "Hizmeti başlat" dendi mi (bekleniyor_metni)
        self.kok = tk.Tk()
        if gizli:
            self.kok.withdraw()
        self.kok.title("Tahta Kontrol")
        self.kok.resizable(False, False)
        self.kok.protocol("WM_DELETE_WINDOW", self.gizle if simge else self.cik)
        self.cerceve: tk.Frame | None = None
        self._ciz()
        self.kok.after(200, self._olaylari_isle)

    def calistir(self) -> int:
        self.kok.mainloop()
        return 0

    # -- olaylar (yalnız Tk iş parçacığında)
    def _olaylari_isle(self) -> None:
        try:
            while True:
                olay = self.olaylar.get_nowait()
                try:
                    self._olay(olay)
                except Exception:
                    logging.exception("Durum penceresi olayı işlenemedi: %s", olay[0])
        except queue.Empty:
            pass
        except tk.TclError:  # pencere kapandı
            return
        try:
            self.kok.after(200, self._olaylari_isle)
        except tk.TclError:
            pass

    def _olay(self, olay: tuple) -> None:
        tur = olay[0]
        if tur == "durum":
            self._durum_degisti(olay[1])
        elif tur == "simge_kapandi":
            self._simge_kapandi()
        elif tur == "uyari":
            self.goster()
            messagebox.showwarning("Tahta Kontrol", olay[1], parent=self.kok)
        elif tur == "menu":
            eylem = {
                "goster": self.goster,
                "panel": lambda: webbrowser.open(tepsi.PANEL_ADRESI),
                "baslat": self.baslat,
                "cik": self.cik,
            }.get(olay[1])
            if eylem:
                eylem()

    def _durum_degisti(self, anlik: tepsi.Anlik) -> None:
        self.anlik = anlik
        self.kip = pencere_kipi(anlik)
        logging.info("Durum penceresi: %s", self.kip)
        simge_turu, ipucu = tepsi.tepsi_durumu(anlik.durum, anlik.hizmet)
        if self.simge is not None:
            self.simge.guncelle(simge_turu, ipucu, tepsi.menu_ogeleri(self.kip, anlik.hizmet))
            metin = tepsi.gecis_bildirimi(self.kararli, simge_turu)
            if metin:
                self.simge.balon(metin, uyari=True)
        self.kararli = tepsi.kararli_tur(self.kararli, simge_turu)
        self._ciz()

    def _simge_kapandi(self) -> None:
        """Simgenin ileti döngüsü istenmeden bitti: pencere artık simgesizdir (X kapatır). Pencere gizliyse
        kullanıcının ona ulaşacağı yol kalmadı: süreç görünmez yaşayıp tek örnek engelini tutmasın, çıkar."""
        self.simge = None
        self.kok.protocol("WM_DELETE_WINDOW", self.cik)
        if self.kok.state() == "withdrawn":
            self.cik()
        else:
            self._ciz()

    # -- eylemler
    def gizle(self) -> None:
        self.kok.withdraw()
        if self.simge is not None and not self.balon_gosterildi:
            self.balon_gosterildi = True
            self.simge.balon(tepsi.BALON_GIZLENDI)

    def goster(self) -> None:
        self._ciz()  # uyarılar zamana bağlı (son yedeğin yaşı): gösterirken tazele
        self.kok.deiconify()
        self.kok.lift()
        self.kok.focus_force()

    def cik(self) -> None:
        self.izleyici.durdur()
        if self.simge is not None:
            self.simge.kapat()
        self.kok.destroy()

    def baslat(self) -> None:
        try:
            hizmeti_baslat()
        except Exception as hata:  # UAC reddi ya da Windows dışı
            self.goster()
            messagebox.showerror("Tahta Kontrol", f"Hizmet başlatılamadı:\n\n{hata}", parent=self.kok)
            return
        self.baslatildi = True
        self.izleyici.hizlandir()
        self.kok.after(6000, self._baslatma_denetimi)

    def _baslatma_denetimi(self) -> None:
        def denetle() -> None:  # sc ve HTTP beklemesi Tk'yi dondurmasın
            if yerel_durum_oku(1.0) is None:
                metin = baslatma_sonucu_metni(hizmet_durumu(), hizmet_cikis_kodu())
                if metin:
                    self.olaylar.put(("uyari", metin))
            self.izleyici.simdi()

        threading.Thread(target=denetle, name="baslatma-denetimi", daemon=True).start()

    # -- çizim
    def _ciz(self) -> None:
        if self.cerceve is not None:
            self.cerceve.destroy()
        cerceve = self.cerceve = tk.Frame(self.kok, padx=22, pady=18)
        cerceve.pack()
        dugmeler = tk.Frame(cerceve)
        anlik = self.anlik
        if self.kip == "okunuyor":
            _baslik(cerceve, "Tahta Kontrol", "Sunucunun durumu okunuyor…")
        elif self.kip == "bekleniyor":
            _baslik(cerceve, *bekleniyor_metni(anlik.hizmet if anlik else None, self.baslatildi))
        elif self.kip == "okunamadi":
            _baslik(
                cerceve,
                "Sunucunun durumu okunamadı",
                f"Hizmetin durumu bu kez okunamadı; kısa süre içinde yeniden denenir · pencere sürümü {__version__}",
            )
            tk.Button(dugmeler, text="Yeniden dene", width=14, command=self.izleyici.simdi).pack(
                side="left", padx=(0, 8)
            )
        elif self.kip == "calisiyor" and anlik is not None and anlik.durum is not None:
            durum = anlik.durum
            ek = " (Windows hizmeti)" if durum.get("hizmet") else ""
            _baslik(
                cerceve, f"Tahta Kontrol sunucusu çalışıyor{ek}", f"Sürüm {durum.get('surum') or __version__}"
            )
            _adresler(cerceve, tepsi.PANEL_ADRESI, list(durum.get("ag_adresleri") or []))
            for metin in uyarilar(durum):
                tk.Label(cerceve, text="• " + metin, fg="#92400e", justify="left", wraplength=420).pack(
                    anchor="w"
                )
            tk.Button(
                dugmeler, text="Paneli aç", width=16, command=lambda: webbrowser.open(tepsi.PANEL_ADRESI)
            ).pack(side="left", padx=(0, 8))
        elif self.kip == "hizmet_calismiyor":
            hizmet = anlik.hizmet if anlik else None
            _baslik(
                cerceve,
                "Sunucu hizmeti çalışmıyor",
                f"Hizmet durumu: {DURUM_TURKCE.get(hizmet or '', hizmet or 'bilinmiyor')} · pencere sürümü {__version__}",
            )
            tk.Label(
                cerceve,
                text=(
                    "Tahtalar çevrimdışı; kilitler 90 saniye sonra tahtadan açılabilir.\n\n"
                    "Ayrıntı: Olay Görüntüleyicisi > Windows Günlükleri > Uygulama, ya da yönetici olarak\n"
                    f"{ayar.hizmet_veri_dizini()}\\gunluk\\sunucu.log\n"
                    "Kurulumdan sonra hiç açılmadıysa eski veri taşınmayı bekliyor olabilir:\n"
                    f"{ayar.hizmet_veri_dizini()}\\TASIMA-BEKLIYOR.txt"
                ),
                justify="left",
            ).pack(anchor="w", pady=(0, 12))
            tk.Button(dugmeler, text="Hizmeti başlat", width=16, command=self.baslat).pack(side="left")
            tk.Button(dugmeler, text="Yeniden dene", width=14, command=self.izleyici.simdi).pack(
                side="left", padx=8
            )
        else:  # kurulu_degil
            _baslik(
                cerceve,
                "Sunucu hizmeti kurulu değil",
                "Tahta Kontrol kurucusunu yeniden çalıştırın; kurucu hizmeti kaydeder ve başlatır.",
            )
        if self.simge is not None:
            not_ = (
                "Pencereyi gizlemek sunucuyu durdurmaz. Tahta Kontrol bildirim alanında kalır;\n"
                'programı kapatmak için simgeye sağ tıklayıp "Çık"ı seçin.'
            )
        else:
            not_ = "Bu pencereyi kapatmak sunucuyu durdurmaz."
        tk.Label(cerceve, text=not_, fg="#555", justify="left").pack(anchor="w", pady=(10, 12))
        dugmeler.pack(anchor="w")
        if self.simge is not None:
            tk.Button(dugmeler, text="Gizle", width=12, command=self.gizle).pack(side="left")
        else:
            tk.Button(dugmeler, text="Kapat", width=12, command=self.cik).pack(side="left")


def _gelistirme_penceresi() -> int:
    """Hizmet yokken (geliştirme) sunucuyu pencere içinde çalıştırır; pencere kapanınca sunucu durur."""
    from .sunucu import Sunucu

    kok = tk.Tk()
    kok.title("Tahta Kontrol")
    kok.resizable(False, False)
    try:
        sunucu = Sunucu()
        sunucu.baslat()
    except Exception as hata:  # pencere açılamadan önce kullanıcıya gösterilir
        logging.exception("Sunucu başlatılamadı")
        kok.withdraw()
        messagebox.showerror("Tahta Kontrol", f"Sunucu başlatılamadı:\n\n{hata}")
        return 1

    cerceve = tk.Frame(kok, padx=22, pady=18)
    cerceve.pack()
    _baslik(cerceve, "Tahta Kontrol sunucusu çalışıyor (geliştirme)", f"Sürüm {__version__}")
    _adresler(cerceve, sunucu.yerel_adres, sunucu.ag_adresleri())
    dugmeler = tk.Frame(cerceve)
    dugmeler.pack(anchor="w")
    tk.Button(dugmeler, text="Paneli aç", width=16, command=lambda: webbrowser.open(sunucu.yerel_adres)).pack(
        side="left"
    )
    tk.Button(dugmeler, text="Simge durumuna küçült", width=22, command=kok.iconify).pack(side="left", padx=8)

    def kapat():
        if messagebox.askyesno(
            "Tahta Kontrol",
            "Sunucu durdurulursa tahtalar çevrimdışı kalır ve panel açılmaz.\n\nSunucu durdurulsun mu?",
        ):
            sunucu.durdur()
            kok.destroy()

    tk.Button(dugmeler, text="Sunucuyu durdur", width=16, command=kapat).pack(side="left")
    kok.protocol("WM_DELETE_WINDOW", kapat)
    kok.mainloop()
    return 0
