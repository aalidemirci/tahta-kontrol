"""Web uygulaması: idare paneli ve tahta ajanlarının konuştuğu arayüz.

Panel uçları oturum çerezi ister; /ajan/* uçları tahtanın kimliği ve anahtarıyla
çalışır. Sunucudan tahtaya bağlantı açılmaz: ajan "uzun bekleme" isteği atar,
komut gelince istek hemen yanıtlanır.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from collections import defaultdict
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile

from . import (
    __version__,
    acil,
    acilis_kilidi,
    adresler,
    arama,
    ayar,
    ayar_bolumleri,
    bolum_serit,
    bugun,
    dugme,
    duyuru,
    guncelleme,
    guvenlik,
    hedef,
    kilit_program,
    marka,
    metin,
    paket,
    panel_program,
    panel_usb,
    panel_yoklama,
    program_is,
    saklama,
    sinav,
    tahta_liste,
    tema,
    usb_anahtar,
    vt,
    wol,
    yedek,
    zamanlama,
)
from . import ariza as ariza_mod
from . import envanter as envanter_mod
from . import program as program_mod
from . import temizlik as temizlik_mod
from . import yoklama as yoklama_mod
from .komut import KOMUT_ADI, KOMUT_DURUMU, KOMUT_OMRU, komut_ekle  # noqa: F401  (KOMUT_OMRU burada da anılır)

gunluk = logging.getLogger("tahta-sunucu")
ISTANBUL = ZoneInfo("Europe/Istanbul")
CEREZ = "tk_oturum"
ROLLER = {"yonetici": "Yönetici", "idareci": "İdareci"}
DUZEYLER = hedef.DUZEYLER
DEVRELER = hedef.DEVRELER

# Yan menü (0.15.0, kabuk): üç küme, en çok on üst öğe; açılır grup ve alt liste yok (0.17.0: bölümün alt sayfaları
# sayfa içi sekme şeridindedir). Öğe alanları:
#   ad, yol (VAR OLAN GET adresi), simge (taban.html sprite'ında m-<simge>), esler (etkin sayılacağı yollar),
#   rol ("yonetici" ise yalnız yöneticiye çizilir), sayi (rozet sayısının anahtarı; sayfa() hesaplar),
#   alt_cubuk (telefon alt çubuğunda da yer alır).
# Öğe eklenirse biri çıkar (test_menu_uc_kume_ve_en_cok_on_oge).
MENU = [
    {"kume": "Her gün", "ogeler": [
        # 0.17.0: alt liste kalktı; Arızalar, Envanter, Gruplar, CSV ve ajan paketi sayfa içi sekme şeridindedir
        # (_tahtalar_bas.html). Şeridi çizen her sayfa burada `esler`'dedir; /tahtalar/ice-aktar "/tahtalar" eşinden seçilir.
        # 0.18.0: "/" Bugün'dür ("/" eşi yalnız tam eşleşmede seçilir; _secili). Rozet sayıları bugun.bekleyenler'den:
        # "tahtalar" = süren arıza (+ yöneticide onay bekleyen tahta), "yedekler" = yedek uyarısı satırları.
        {"ad": "Bugün", "yol": "/", "simge": "bugun", "esler": ["/"], "alt_cubuk": True},
        {"ad": "Tahtalar", "yol": "/tahtalar", "simge": "tahta", "sayi": "tahtalar", "alt_cubuk": True,
         "esler": ["/tahtalar", "/tahta/", "/arizalar", "/ariza", "/envanter", "/gruplar", "/ekle"]},
        {"ad": "Duyurular", "yol": "/duyurular", "simge": "duyuru", "esler": ["/duyurular"], "alt_cubuk": True},
        {"ad": "Yoklama", "yol": "/yoklama", "simge": "yoklama", "esler": ["/yoklama"], "alt_cubuk": True},
    ]},
    {"kume": "Dönemlik", "ogeler": [
        # 0.19.0: şeridi çizen her sayfa esler'dedir (bolum_serit.SERITLER["program"]); öğretmen programı buradadır.
        {"ad": "Program", "yol": "/program", "simge": "program", "esler": ["/program", "/ogretmen-programi"]},
        {"ad": "Sınavlar", "yol": "/sinavlar", "simge": "sinav", "esler": ["/sinavlar", "/sinav"]},
        {"ad": "Kişiler ve anahtarlar", "yol": "/ogrenciler", "simge": "kisiler",
         # 0.19.0: üç sayfa kendi sekme şeridini çizer (_kisiler_bas.html); /ogretmen-programi Program şeridindedir.
         "esler": ["/ogrenciler", "/ogretmenler", "/usb-anahtarlar"]},
    ]},
    {"kume": "Yönetim", "ogeler": [
        {"ad": "Yedekler", "yol": "/yedekler", "simge": "yedek", "esler": ["/yedekler"], "rol": "yonetici",
         "sayi": "yedekler"},
        {"ad": "İşlem kaydı", "yol": "/kayit", "simge": "kayit", "esler": ["/kayit"]},
        # 0.16.0: Kullanıcılar Ayarlar'ın bir bölümüdür (/ayarlar/kullanicilar); eski adres oraya yönlenir.
        {"ad": "Ayarlar", "yol": "/ayarlar", "simge": "ayar", "esler": ["/ayarlar", "/kullanicilar"], "rol": "yonetici"},
    ]},
]
# Kümelerin dışında, en üstte; iki role de çizilir (K4).
MENU_ACIL = {"ad": "Acil durum", "yol": "/acil", "esler": ["/acil"]}
MENU_BOS = {"kumeler": [], "alt_cubuk": []}


def _secili(oge: dict, yol: str) -> bool:
    for es in oge.get("esler", []):
        if yol == es or (es.endswith("/") and es != "/" and yol.startswith(es)) or (es != "/" and yol.startswith(es + "/")):
            return True
    return False


# Genel aramanın dizini (0.20.0): sayfa, sekme, iş, süzgeç ve ayar girdileri yukarıdaki MENU'den, bolum_serit ve
# ayar_bolumleri tanımlarından TÜRER; süreç başında bir kez kurulur (sahipsiz hedef varsa içe aktarmada patlar).
ARAMA = arama.kur(MENU, MENU_ACIL, _secili)
ARAMA_SABIT = ARAMA["sabit"]


def menu_gorunumu(k, yol: str, sayilar: dict | None = None) -> dict:
    """Role göre süzülmüş yan menü: {"kumeler": [{"ad", "ogeler"}], "alt_cubuk": [oge]}.

    Öğe: {"ad", "yol", "simge", "secili", "sayi"}. `secili` öğenin `esler`'inden gelir: bölümün sekme şeridindeki
    sayfalar (rolle gizlenen sekmenin sayfası dahil; idareci /gruplar'ı adresle açarsa "Tahtalar" yine vurgulanır)
    aynı öğeyi seçer. `sayi` (0 ise rozet yok) `sayilar[öğenin sayi anahtarı]`dır.
    """
    sayilar = sayilar or {}
    rol = k["rol"] if k else None

    def gorunur(oge: dict) -> bool:
        return not oge.get("rol") or oge["rol"] == rol

    kumeler, alt_cubuk = [], []
    for kume in MENU:
        ogeler = []
        for oge in kume["ogeler"]:
            if not gorunur(oge):
                continue
            gorunum = {
                "ad": oge["ad"],
                "yol": oge["yol"],
                "simge": oge["simge"],
                "secili": _secili(oge, yol),
                "sayi": int(sayilar.get(oge.get("sayi"), 0) or 0),
            }
            ogeler.append(gorunum)
            if oge.get("alt_cubuk"):
                alt_cubuk.append(gorunum)
        if ogeler:
            kumeler.append({"ad": kume["kume"], "ogeler": ogeler})
    return {"kumeler": kumeler, "alt_cubuk": alt_cubuk}


OTURUM_SINIFI = {
    "etapadmin": "Yönetici hesabı (etapadmin)",
    "ogretmen": "Öğretmen hesabı (ortak)",
    "ogrenci": "Öğrenci hesabı (sınırlı)",
    "kisisel": "Kişisel hesap",
    "yok": "Oturum açık değil",
    "windows": "Windows oturumu",
}

# İçerik güvenlik politikası: satır içi betik/stil yok, dış kaynak yok.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; "
    "font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
UZUN_ONBELLEK = "public, max-age=31536000, immutable"
ADRES_YETENEGI = "adres_listesi"


def zaman_yaz(epoch) -> str:
    if not epoch:
        return "—"
    return datetime.fromtimestamp(int(epoch), ISTANBUL).strftime("%d.%m.%Y %H:%M:%S")


def saat_yaz(epoch) -> str:
    return datetime.fromtimestamp(int(epoch), ISTANBUL).strftime("%H:%M") if epoch else "—"


def tarih_yaz(epoch) -> str:
    return datetime.fromtimestamp(int(epoch), ISTANBUL).strftime("%d.%m.%Y %H:%M") if epoch else "—"


def gecen_sure(epoch) -> str:
    if not epoch:
        return "hiç bağlanmadı"
    fark = max(0, int(time.time()) - int(epoch))
    if fark < 90:
        return "şimdi"
    if fark < 3600:
        return f"{fark // 60} dk önce"
    if fark < 86400:
        return f"{fark // 3600} sa önce"
    return f"{fark // 86400} gün önce"


def uygulama_olustur(parmak_izi: str = "", guncelleme_getirici=None) -> FastAPI:
    """guncelleme_getirici: GitHub sürüm denetiminin getiricisi (testler sahte verir; yoksa gerçek ağ)."""
    vt.hazirla()
    guncelleme_denetleyici = guncelleme.Denetleyici(guncelleme_getirici)
    uygulama = FastAPI(title="Tahta Kontrol", docs_url=None, redoc_url=None, openapi_url=None)
    uygulama.mount("/statik", StaticFiles(directory=ayar.SUNUCU_DIZINI / "statik"), name="statik")
    sablonlar = Jinja2Templates(directory=ayar.SUNUCU_DIZINI / "sablonlar")
    sablonlar.env.filters["zaman"] = zaman_yaz
    sablonlar.env.filters["gecen"] = gecen_sure
    sablonlar.env.filters["saat"] = saat_yaz
    sablonlar.env.filters["tarih"] = tarih_yaz
    sablonlar.env.filters["kat_adi"] = hedef.kat_adi
    sablonlar.env.globals.update(
        surum=__version__,
        ara_en_uzun=ayar_bolumleri.SORGU_EN_UZUN,
        bolum_seridi=bolum_serit.gorunum,
        komut_adi=KOMUT_ADI,
        komut_durumu=KOMUT_DURUMU,
        roller=ROLLER,
        oturum_sinifi=OTURUM_SINIFI,
        duzeyler=DUZEYLER,
        devreler=DEVRELER,
        gun_kisa=zamanlama.GUN_KISA,
        yayin_durumu=duyuru.YAYIN_DURUMU,
        plan_durumu=duyuru.PLAN_DURUMU,
        acil_turleri=acil.TURLER,
        acil_bitis_nedeni=acil.BITIS_NEDENI,
        katlar=[(None, "Belirtilmemiş")] + [(k, hedef.kat_adi(k)) for k in range(-2, 21)],
    )

    bekleyenler: dict[int, tuple[asyncio.AbstractEventLoop, asyncio.Event]] = {}
    kayit_denemeleri: dict[str, list[float]] = defaultdict(list)
    giris_denemeleri: dict[str, list[float]] = defaultdict(list)

    # ---- yardımcılar ---------------------------------------------------------
    def istemci_ip(istek: Request) -> str:
        return istek.client.host if istek.client else ""

    def yerel_mi(istek: Request) -> bool:
        return istemci_ip(istek) in ("127.0.0.1", "::1")

    def kullanici(istek: Request):
        belirtec = istek.cookies.get(CEREZ)
        if not belirtec:
            return None
        with vt.islem() as b:
            return b.execute(
                "SELECT k.* FROM oturum o JOIN kullanici k ON k.id = o.kullanici_id "
                "WHERE o.belirtec_ozet = ? AND o.bitis > ? AND k.aktif = 1",
                (guvenlik.ozet(belirtec), vt.simdi()),
            ).fetchone()

    def yonlendir(adres: str, mesaj: str = "", hata: bool = False) -> RedirectResponse:
        """İleti ?m= ile taşınır; hata=True ise bant hata görünümünde ve role="alert" ile çizilir."""
        if mesaj:
            from urllib.parse import quote

            adres, isaret, parca = adres.partition("#")  # ileti parçadan (#…) önce gelmeli
            tur = "&t=hata" if hata else ""
            adres += ("&" if "?" in adres else "?") + "m=" + quote(mesaj) + tur + isaret + parca
        return RedirectResponse(adres, status_code=303)

    def acil_ozeti(b, simdi: int | None = None) -> dict | None:
        """Panel bandı ve /api/durum için süren acil yayın: {"id","tur","baslik","kalan_sn","baslatan","baslangic"}."""
        simdi = vt.simdi() if simdi is None else simdi
        yayin = acil.aktif(b, simdi)
        if not yayin:
            return None
        return {
            "id": yayin["id"],
            "tur": yayin["tur"],
            "baslik": yayin["baslik"],
            "kalan_sn": max(0, yayin["bitis_plan"] - simdi),
            "baslatan": yayin["baslatan"],
            "baslangic": yayin["baslangic"],
        }

    def sayfa(istek: Request, ad: str, k, durum_kodu: int = 200, **baglam) -> HTMLResponse:
        with vt.islem() as b:
            okul_adi = vt.ayar_al(b, "okul_adi", "")
            ana, vurgu = tema.tema_al(b)
            logo_v = marka.logo_surumu(b)
            aktif_acil = acil_ozeti(b) if k else None
            # Menü rozetleri Bugün'deki satırlarla AYNI koddan çıkar (bugun.bekleyenler; yalnız rozetli üreticiler).
            rozetli = baglam.pop("rozetli", None)  # Bugün tam listeyi zaten hesapladı
            if rozetli is None:
                rozetli = bugun.bekleyenler(b, k, yalniz_rozet=True) if k else []
            menu_sayilari = bugun.rozet_sayilari(rozetli) if k else {}
        # menu_yolu: sayfa başka bir uçta (POST /ayarlar → Acil › Şablonlar) yeniden çizilirken etkin menü öğesi
        # isteğin değil, çizilen sayfanın yoluna göre seçilir.
        menu_yolu = baglam.pop("menu_yolu", None) or istek.url.path
        baglam.update(
            menu=menu_gorunumu(k, menu_yolu, menu_sayilari) if k else MENU_BOS,
            menu_acil={**MENU_ACIL, "secili": _secili(MENU_ACIL, menu_yolu)},
            aktif_acil=aktif_acil,
            acil_yetkili=acil.yetkili(k),
            istek_yolu=istek.url.path,
            kullanici=k,
            okul_adi=okul_adi,
            tema_v=tema.surum(ana, vurgu),
            tema_serit=tema.uret(ana, vurgu)["acik"]["serit"],
            logo_v=logo_v,
            monogram=tema.bas_harfler(okul_adi),
        )
        # İleti yönlendirme adresinden gelir; aynı yanıtta yeniden çizilen form kendi iletisini verebilir.
        baglam.setdefault("mesaj", istek.query_params.get("m", ""))
        baglam.setdefault("mesaj_hata", istek.query_params.get("t") == "hata")
        baglam.setdefault("ileti_yeri", istek.query_params.get("yer", ""))
        # Tahtalar bölümünün sekme şeridi (_tahtalar_bas.html) süren arıza sayısını buradan alır (ek sorgu yok).
        baglam.setdefault("ariza_sayisi", bugun.satir_sayisi(rozetli, "ariza"))
        return sablonlar.TemplateResponse(istek, ad, baglam, status_code=durum_kodu)

    def onayli_tahtalari_uyandir() -> None:
        with vt.islem() as b:
            idler = [s["id"] for s in b.execute("SELECT id FROM tahta WHERE durum = 'onayli'").fetchall()]
        for tahta_id in idler:
            uyandir(tahta_id)

    def hiz_siniri(kayit: dict[str, list[float]], anahtar: str, adet: int, pencere: int) -> bool:
        simdi = time.time()
        kayit[anahtar] = [z for z in kayit[anahtar] if simdi - z < pencere]
        if len(kayit[anahtar]) >= adet:
            return False
        kayit[anahtar].append(simdi)
        return True

    def sunucu_adresi(istek: Request) -> str:
        host = (istek.headers.get("host") or "").strip().lower()
        if istek.url.scheme == "https" and host and adresler.betige_yazilabilir_mi(f"https://{host}"):
            return f"https://{host}"
        with vt.islem() as b:
            liste = adresler.al(b)
        if liste:  # A6: adres listesinin ilk öğesi birincildir (kurulum betiği bunu kullanır)
            return liste[0]
        ipler = guvenlik.yerel_ipler()
        return f"https://{ipler[0] if ipler else '127.0.0.1'}:{ayar.HTTPS_PORT}"

    def uyandir(tahta_id: int) -> None:
        kayit = bekleyenler.get(tahta_id)
        if kayit:
            dongu, olay = kayit
            dongu.call_soon_threadsafe(olay.set)

    def uyandir_hepsi(idler) -> None:
        for tahta_id in set(idler):
            uyandir(tahta_id)

    def tahta_gorunumu(
        satir,
        acil_gorenler: set[int] | None = None,
        gruplar: dict | None = None,
        bos_dersler: dict | None = None,
        sinavlar: dict | None = None,
        altyapi: dict | None = None,
        acil_suruyor: bool = False,
        program_kilidi_acik: bool = False,
    ) -> dict:
        """Pano kartı ve /api/durum için tahta özeti.

        acil_gorenler: süren acil yayını ekrana almış tahtaların kimlikleri (yoksa None).
        gruplar: tahta kimliği → grup kimlikleri (pano ilk verisi için; yoksa boş liste).
        bos_dersler: tahta kimliği → "3. ders (kapalı)" (program_is.bos_ders_metinleri).
        sinavlar: tahta kimliği → sınav penceresi (sinav.pencere_haritasi); yoksa `sinav` None.
        altyapi: altyapi_verisi(b) — A6 arıza sayısı ve "donanım değişti" rozeti için; yoksa 0/False.
        acil_suruyor, program_kilidi_acik: `liste` alanının (0.17.0; tahta_liste.durum_ozeti — satırın rozetleri,
        birincil düğmesi, menü pasiflikleri) girdileri. Durum kuralı yalnız oradadır; panel.js yeniden hesaplamaz.
        """
        durum = json.loads(satir["durum_json"] or "{}")
        cevrimici = bool(satir["son_gorulme"]) and (vt.simdi() - satir["son_gorulme"]) < ayar.CEVRIMICI_ESIK_SN
        ekranlar = durum.get("ekranlar") or []
        oturum = (durum.get("oturum") or {}).get("sinif", "yok")
        yetenekler = acil.yetenekler(satir)
        gorunum = {
            "bina": satir["bina"],
            "kat": satir["kat"],
            "duzeyler": hedef.kume(satir["duzeyler"]),
            "devre": satir["devre"],
            "subeler": hedef.kume(satir["subeler"]),
            "gruplar": (gruplar or {}).get(satir["id"], []),
            "alanlar": hedef.alanlar_metni(satir),
            "yetenekler": yetenekler,
            "acil_yetenegi": acil.ACIL_YETENEK in yetenekler,
            "acil_gorundu": bool(acil_gorenler) and satir["id"] in acil_gorenler,
            "id": satir["id"],
            "ad": satir["ad"],
            "derslik": satir["derslik"],
            "durum": satir["durum"],
            "cevrimici": cevrimici,
            "kilitli": bool(durum.get("kilitli")) if cevrimici else None,
            "duyuru_var": bool(durum.get("duyuru_var")) if cevrimici else False,
            "ekran_bagli": any(e.get("arayuz") not in (None, "yok", "komut") for e in ekranlar),
            "oturum": OTURUM_SINIFI.get(oturum, oturum),
            "oturum_acik": cevrimici and oturum != "yok",
            "son_gorulme": gecen_sure(satir["son_gorulme"]),
            "surum": satir["surum"],
            "guncel": satir["surum"] == paket.ajan_paketi().surum,
            "ip": satir["ip"],
            "program": program_is.tahta_program(satir, (bos_dersler or {}).get(satir["id"])),
            # A4: sunucunun hesabıyla sınav penceresi {"sinav_id","salon_id","sinav_adi","salon_adi","evre","bitis_saat"}
            # (ajan sürümünden bağımsız; pano rozeti ve ek onay buna bakar) ve ajanın bildirdiği ekran evresi.
            "sinav": (sinavlar or {}).get(satir["id"]),
            "sinav_ekran": sinav_ekran_evresi(durum) if cevrimici else None,
            "sinav_yetenegi": sinav.SINAV_YETENEGI in yetenekler,
            # A5: rozet "Yoklama: ajan güncellenmeli" yetenekten üretilir; yoklama_acik ajanın bildirdiği bayraktır.
            "yoklama_yetenegi": yoklama_mod.YOKLAMA_YETENEGI in yetenekler,
            "yoklama_acik": bool(durum.get("yoklama_acik")) if cevrimici else False,
            # A6: açık + inceleniyor arıza sayısı (pano rozeti "Arıza"), donanım kimliği değişti rozeti,
            # ajanın bildirdiği bağlantı adresi ve yetenekler ("Ajan güncellenmeli" notu).
            "ariza_sayisi": int(((altyapi or {}).get("arizalar") or {}).get(satir["id"], 0)),
            "donanim_degisti": satir["id"] in ((altyapi or {}).get("donanim") or ()),
            "envanter_yetenegi": envanter_mod.YETENEK in yetenekler,
            "ariza_yetenegi": ariza_mod.YETENEK in yetenekler,
            "adres_listesi_yetenegi": ADRES_YETENEGI in yetenekler,
            "dugme_yetenegi": dugme.YETENEK in yetenekler,
            # 0.11.0: rozet "USB anahtar: ajan güncellenmeli" (yalnız özellik açıkken anlamlı).
            "usb_anahtar_yetenegi": usb_anahtar.YETENEK in yetenekler,
            "bagli_adres": str(durum.get("sunucu_adresi") or "")[:200],
        }
        gorunum["liste"] = tahta_liste.durum_ozeti(gorunum, acil_suruyor, program_kilidi_acik)
        return gorunum

    def altyapi_verisi(b) -> dict:
        """tahta_gorunumu(altyapi=…) için tek seferde: süren arıza sayıları ve donanım uyarıları."""
        return {"arizalar": ariza_mod.suren_sayilari(b), "donanim": envanter_mod.donanim_uyarilari(b)}

    ip_onbellegi: list = [0.0, None, []]  # [zaman, işlev, liste]

    def yerel_ipler() -> list[str]:
        """Bu bilgisayarın adresleri, 60 sn bellekte: /api/durum 4 sn'de bir bekleyen işleri hesaplar (adres uyarısı).
        İşlev değişmişse (testler `guvenlik.yerel_ipler`'i değiştirir) bellek geçersizdir."""
        simdi = time.monotonic()
        if ip_onbellegi[1] is not guvenlik.yerel_ipler or simdi - ip_onbellegi[0] > 60:
            ip_onbellegi[:] = [simdi, guvenlik.yerel_ipler, guvenlik.yerel_ipler()]
        return list(ip_onbellegi[2])

    def sinav_ekran_evresi(durum: dict) -> str | None:
        bildirilen = durum.get("sinav") if isinstance(durum.get("sinav"), dict) else None
        evre = bildirilen.get("evre") if bildirilen and not bildirilen.get("yerel_kapali") else None
        return evre if evre in sinav.EKRAN_EVRE_ADI else None

    # ---- güvenlik katmanı ----------------------------------------------------
    @uygulama.middleware("http")
    async def kapilar(istek: Request, sonraki):
        yol = istek.url.path
        if istek.method == "POST" and not yol.startswith("/ajan/"):
            # Çerezle çalışan uçlara başka siteden istek attırılmasın.
            kaynak = istek.headers.get("origin")
            if kaynak and kaynak.split("://", 1)[-1] != istek.headers.get("host", ""):
                return JSONResponse({"hata": "Geçersiz istek kaynağı."}, status_code=403)
        yanit = await sonraki(istek)
        basliklar = yanit.headers
        basliklar["X-Content-Type-Options"] = "nosniff"
        basliklar["X-Frame-Options"] = "DENY"
        # no-referrer KULLANMA: tarayıcı form gönderiminde "Origin: null" yollar, kaynak denetimi reddeder.
        basliklar["Referrer-Policy"] = "same-origin"
        basliklar.setdefault("Content-Security-Policy", CSP)
        basliklar.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), usb=()")
        basliklar.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if not yol.startswith("/statik"):
            basliklar.setdefault("Cache-Control", "no-store")
        return yanit

    def kapatma_ozeti(kural: dict) -> str:
        parcalar = []
        if kural.get("etkin") and kural.get("saatler"):
            parcalar.append("hafta içi " + ", ".join(kural["saatler"]))
        if kural.get("hafta_sonu"):
            parcalar.append(f"hafta sonu {kural.get('hafta_sonu_dk', 60)} dakika açık kalınca")
        return " · ".join(parcalar)

    def kurulum_gerekli() -> bool:
        with vt.islem() as b:
            return b.execute("SELECT COUNT(*) FROM kullanici").fetchone()[0] == 0

    # ---- oturum --------------------------------------------------------------
    @uygulama.get("/saglik")
    async def saglik():
        return {"durum": "calisiyor", "surum": __version__}

    @uygulama.get("/kurulum", response_class=HTMLResponse)
    async def kurulum_formu(istek: Request):
        if not kurulum_gerekli():
            return yonlendir("/giris")
        # A6 §6.8: yerelde "Yedekten geri yükle" bağlantısı (→ /yedekler/geri-yukle, oturumsuz).
        return sayfa(istek, "kurulum.html", None, yerel=yerel_mi(istek), geri_yukleme=yerel_mi(istek))

    @uygulama.post("/kurulum")
    async def kurulum_kaydet(istek: Request):
        if not kurulum_gerekli():
            return yonlendir("/giris")
        if not yerel_mi(istek):
            return yonlendir("/kurulum", "İlk kurulum yalnız sunucunun kurulu olduğu bilgisayardan yapılabilir.", hata=True)
        form = await istek.form()
        ad = str(form.get("ad", "")).strip().lower()
        parola = str(form.get("parola", ""))
        if len(ad) < 3 or len(parola) < 8 or parola != str(form.get("parola2", "")):
            return yonlendir("/kurulum", "Kullanıcı adı en az 3, parola en az 8 karakter olmalı ve iki parola aynı girilmeli.", hata=True)
        with vt.islem() as b:
            # İlk yönetici acil yetkisini de alır (göçteki kuralla aynı: sistem acil yetkilisiz kalmasın).
            b.execute(
                "INSERT INTO kullanici (ad, gorunen_ad, parola_ozet, rol, olusturma, acil_yetki) VALUES (?, ?, ?, 'yonetici', ?, 1)",
                (ad, str(form.get("gorunen_ad", "")).strip() or ad, guvenlik.parola_ozetle(parola), vt.simdi()),
            )
            vt.ayar_yaz(b, "okul_adi", str(form.get("okul_adi", "")).strip())
            vt.kayit_dus(b, ad, "İlk kurulum", "Yönetici hesabı oluşturuldu.", istemci_ip(istek))
        return yonlendir("/giris", "Kurulum tamamlandı. Giriş yapabilirsiniz.")

    @uygulama.get("/giris", response_class=HTMLResponse)
    async def giris_formu(istek: Request):
        if kurulum_gerekli():
            return yonlendir("/kurulum")
        return sayfa(istek, "giris.html", None)

    @uygulama.post("/giris")
    async def giris(istek: Request):
        form = await istek.form()
        ad = str(form.get("ad", "")).strip().lower()
        if not hiz_siniri(giris_denemeleri, istemci_ip(istek), 10, 300):
            return yonlendir("/giris", "Çok fazla deneme yapıldı. Birkaç dakika sonra yeniden deneyin.", hata=True)
        with vt.islem() as b:
            satir = b.execute("SELECT * FROM kullanici WHERE ad = ? AND aktif = 1", (ad,)).fetchone()
            if not satir or not guvenlik.parola_dogrula(str(form.get("parola", "")), satir["parola_ozet"]):
                vt.kayit_dus(b, ad or "?", "Başarısız giriş", "", istemci_ip(istek))
                basarili = False
            else:
                belirtec = guvenlik.belirtec()
                b.execute("DELETE FROM oturum WHERE bitis < ?", (vt.simdi(),))
                b.execute(
                    "INSERT INTO oturum (belirtec_ozet, kullanici_id, bitis) VALUES (?, ?, ?)",
                    (guvenlik.ozet(belirtec), satir["id"], vt.simdi() + ayar.OTURUM_SAAT * 3600),
                )
                vt.kayit_dus(b, ad, "Giriş", "", istemci_ip(istek))
                basarili = True
        if not basarili:
            return yonlendir("/giris", "Kullanıcı adı ya da parola hatalı.", hata=True)
        yanit = yonlendir("/")
        yanit.set_cookie(
            CEREZ,
            belirtec,
            max_age=ayar.OTURUM_SAAT * 3600,
            httponly=True,
            samesite="strict",
            secure=istek.url.scheme == "https",
        )
        return yanit

    @uygulama.post("/cikis")
    async def cikis(istek: Request):
        belirtec = istek.cookies.get(CEREZ)
        if belirtec:
            with vt.islem() as b:
                b.execute("DELETE FROM oturum WHERE belirtec_ozet = ?", (guvenlik.ozet(belirtec),))
        yanit = yonlendir("/giris")
        yanit.delete_cookie(CEREZ)
        return yanit

    # ---- Bugün ve tahtalar (0.18.0): "/" Bugün'dür, "/tahtalar" listedir; ikisi ve /api/durum aynı görünümü kullanır
    def tahta_baglami(b, hepsi: bool = True) -> dict:
        """Tahta görünümleri için ortak yükleme: {"tahtalar", "program", "gorenler", "simdi", "an"}.

        hepsi=False yalnız onaylıları yükler (/api/durum). Durum kuralı `tahta_gorunumu` → `tahta_liste.durum_ozeti`."""
        an = vt.simdi()
        kosul = "durum != 'iptal'" if hepsi else "durum = 'onayli'"
        satirlar = b.execute(f"SELECT * FROM tahta WHERE {kosul}").fetchall()
        gorenler = acil_gorenler(b)
        simdi_dt = datetime.fromtimestamp(an, ISTANBUL)
        program_ozeti = program_is.program_ozeti(b, simdi_dt)
        bos_dersler = program_is.bos_ders_metinleri(b, simdi_dt)
        sinavlar = sinav.pencere_haritasi(b, an)
        altyapi = altyapi_verisi(b)
        uyelik = grup_uyelikleri(b) if hepsi else None
        kilit_acik = program_ozeti["kilit"] != "kapali"
        return {
            "tahtalar": [
                tahta_gorunumu(s, gorenler, uyelik, bos_dersler, sinavlar, altyapi, gorenler is not None, kilit_acik)
                for s in satirlar
            ],
            "program": program_ozeti,
            "gorenler": gorenler,
            "simdi": simdi_dt,
            "an": an,
        }

    @uygulama.get("/", response_class=HTMLResponse)
    async def bugun_sayfasi(istek: Request):
        """Bugün (0.18.0): şu an, bekleyen işler, tahta özeti, yoklama ve duyuru kutuları. Liste /tahtalar'dadır.

        0.17.0'da "/" listeydi: `?durum=` ya da `?s=` taşıyan eski adres listeye yönlenir (yer imleri, açık sekmeler)."""
        k = kullanici(istek)
        if not k:
            return yonlendir("/kurulum" if kurulum_gerekli() else "/giris")
        sorgu = istek.query_params
        if "durum" in sorgu or "s" in sorgu:
            from urllib.parse import urlencode

            aktar = {}
            suzgec = tahta_liste.suzgec_coz(sorgu.get("durum", ""))
            if suzgec:
                aktar["durum"] = suzgec
            if sorgu.get("s", "").isdigit() and hedef.kimlik_mi(sorgu["s"]):
                aktar["s"] = sorgu["s"]
            if sorgu.get("m"):
                aktar["m"] = sorgu["m"][:500]
                if sorgu.get("t") == "hata":
                    aktar["t"] = "hata"
            return RedirectResponse("/tahtalar" + ("?" + urlencode(aktar) if aktar else ""), status_code=303)
        with vt.islem() as b:
            ortak = tahta_baglami(b)
            an = ortak["an"]
            onayli = [t for t in ortak["tahtalar"] if t["durum"] == "onayli"]
            tahta_ozeti = bugun.tahta_ozeti(onayli)
            satirlar = bugun.bekleyenler(b, k, an=an, ipler=yerel_ipler(), tahta_sayilari=tahta_ozeti["sayilar"])
            kurulum_onbellegi(b, k, an, taze=[s for s in satirlar if s["anahtar"] == "kurulum"])
            akis = bugun.akis(b, ortak["simdi"]) if ortak["program"]["ders_saati_var"] else []
            yoklama_ozeti = bugun.yoklama_ozeti(b, an)
            duyuru_ozeti = bugun.duyuru_ozeti(b, an)
        return sayfa(
            istek,
            "bugun.html",
            k,
            program=ortak["program"],
            akis=akis,
            bekleyenler=satirlar,
            acik_satir=bugun.acik_satir_sayisi(satirlar),
            rozetli=[s for s in satirlar if s["rozet"]],  # menü rozetleri aynı listeden; sayfa() yeniden sorgulamaz
            bekleyen_imza=bugun.imza(satirlar),
            bekleyen_tahta=sum(1 for t in ortak["tahtalar"] if t["durum"] == "bekliyor"),
            tahta_ozeti=tahta_ozeti,
            yoklama_ozeti=yoklama_ozeti,
            duyuru_ozeti=duyuru_ozeti,
            odakla=True,  # ?m= iletisi (yetkisiz dönüş, Durdur, Hepsini kilitle) sayfa başında çizilir ve odaklanır
        )

    @uygulama.get("/tahtalar", response_class=HTMLResponse)
    async def tahtalar_sayfasi(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/kurulum" if kurulum_gerekli() else "/giris")
        yonetici = k["rol"] == "yonetici"
        with vt.islem() as b:
            kilit_kodu_var = bool(vt.ayar_al(b, "kilit_kodu"))
            kapatma = kapatma_ozeti(vt.ayar_al(b, "otomatik_kapatma") or {})
            ortak = tahta_baglami(b)
            # 0.21.0: toplu adlandırmanın değiştireceği tahta sayısı (bant yalnız yöneticide; kural tahta_liste'de).
            adlandirilacak = len(tahta_liste.adlandirilacaklar(adlandirma_satirlari(b))) if yonetici else 0
        tahtalar = ortak["tahtalar"]
        onayli = [t for t in tahtalar if t["durum"] == "onayli"]
        # Kurulum sırası (= numara sırası): yeni kayıtlar "Tahta <no>" adıyla gelir, kurulumda not edilen numarayla aranır.
        bekleyen = sorted((t for t in tahtalar if t["durum"] == "bekliyor"), key=lambda t: t["id"])
        for t in onayli:  # satırın "⋯" menüsü role göre kurulur: idareciye yönetici öğesi hiç çizilmez
            t["menu"] = tahta_liste.menu_ogeleri(t, k["rol"])
        gruplar = tahta_liste.gruplar(onayli)
        suzgec = tahta_liste.suzgec_coz(istek.query_params.get("durum", ""))
        for g in gruplar:  # bütün satırları süzgeç dışında kalan grubun başlığı da gizlenir
            g["gorunen"] = sum(1 for t in g["tahtalar"] if not suzgec or suzgec in t["liste"]["durumlar"])
        ileti_satiri = istek.query_params.get("s", "")  # satır komutundan dönüş: ileti o satırda da çizilir
        return sayfa(
            istek,
            "tahtalar.html",
            k,
            # Menü yüklerini (t["menu"]) taşımayan sade kopya: ilk-veri /api/durum ile aynı biçimdedir.
            onayli=[{a: d for a, d in t.items() if a not in ("menu", "alt_satir")} for g in gruplar for t in g["tahtalar"]],
            gruplar=gruplar,
            sayilar=tahta_liste.sayilar(onayli),
            suzgecler=tahta_liste.SUZGECLER,
            suzgec=suzgec,
            # Onay bekleyenin adı ve adresi yalnız yöneticiye gider; idareci yalnız sayıyı görür.
            bekleyen=bekleyen if yonetici else [],
            bekleyen_sayisi=len(bekleyen),
            ayni_ad_sayisi=adlandirilacak,
            liste_yolu="/tahtalar",
            donus="/tahtalar" + (f"?durum={suzgec}" if suzgec else ""),
            ileti_satiri=int(ileti_satiri) if ileti_satiri.isdigit() and hedef.kimlik_mi(ileti_satiri) else 0,
            tahtalar_sekme="tahtalar",
            kilit_kodu_var=kilit_kodu_var,
            kapatma=kapatma,
            program_kilidi=ortak["program"]["kilit"] != "kapali",
        )

    def acil_gorenler(b) -> set[int] | None:
        yayin = acil.aktif(b)
        if not yayin:
            return None
        return {s["tahta_id"] for s in b.execute("SELECT tahta_id FROM acil_teslim WHERE acil_id = ?", (yayin["id"],))}

    def grup_uyelikleri(b) -> dict[int, list[int]]:
        sonuc: dict[int, list[int]] = {}
        for s in b.execute("SELECT tahta_id, grup_id FROM tahta_grubu_uye ORDER BY grup_id"):
            sonuc.setdefault(s["tahta_id"], []).append(s["grup_id"])
        return sonuc

    KURULUM_ONBELLEK_SN = 30
    kurulum_bellek: dict = {}

    def kurulum_onbellegi(b, k, an: int, taze: list | None = None) -> list:
        """Canlı tazeleme için `kurulum` satırı (yalnız yönetici) en çok 30 sn bellekte durur: kurulum eksikleri
        saniyeler içinde değişmez, üreticisi ise dokuz ayar okur. Bugün sayfası her yüklemede taze hesaplar ve belleği
        yeniler (`taze`); böylece yeni yüklenen sayfanın imzası ile ilk /api/durum yanıtı aynıdır. Süre gerçek
        (monotonik) saattendir; bellek süreç içidir, kişi verisi taşımaz."""
        if k["rol"] != "yonetici":
            return []
        simdi_m = time.monotonic()
        if taze is None:
            kayit = kurulum_bellek.get("satir")
            if kayit and simdi_m - kayit[0] < KURULUM_ONBELLEK_SN:
                return kayit[1]
            taze = bugun.kurulum_satiri(b, k, an=an, ipler=yerel_ipler())
        kurulum_bellek["satir"] = (simdi_m, taze)
        return taze

    @uygulama.get("/api/durum")
    async def api_durum(istek: Request):
        """Canlı tazeleme (Tahtalar ve Bugün). Sözleşme yalnız EKLEMELİ değişir: 0.18.0'da `bekleyen_is` eklendi
        ({"sayi", "imza"}; isteği yapan kullanıcının rolüyle süzülmüş bugun.bekleyenler)."""
        k = kullanici(istek)
        if not k:
            return JSONResponse({"hata": "Oturum gerekli."}, status_code=401)
        with vt.islem() as b:
            ortak = tahta_baglami(b, hepsi=False)
            bekleyen = b.execute("SELECT COUNT(*) FROM tahta WHERE durum = 'bekliyor'").fetchone()[0]
            ozet = acil_ozeti(b)
            isler = bugun.bekleyenler(b, k, an=ortak["an"], ipler=yerel_ipler(), kurulum=kurulum_onbellegi(b, k, ortak["an"]))
        if ozet:
            ozet["teslim"] = len(ortak["gorenler"] or ())
            ozet["hedef"] = len(ortak["tahtalar"])
        return {
            "tahtalar": ortak["tahtalar"],
            "bekleyen": bekleyen,
            "acil": ozet,
            "program": ortak["program"],
            "bekleyen_is": {"sayi": len(isler), "imza": bugun.imza(isler)},
        }

    # ---- genel arama (0.20.0) ---------------------------------------------------------------------------------
    # Sorgu HİÇBİR YERE yazılmaz: işlem kaydı, günlük, tablo, çerez yok. Kişi tablolarına sorgu gitmez; dizin ve
    # rol süzmesi arama.py'dedir. Sayfa başlığına sorgu konmaz (tarayıcı geçmişinin başlık sütununa düşmesin).
    def arama_sonucu(k, ham, en_cok: int) -> dict:
        q = arama.sorgu_duzelt(ham)
        devingen = []
        if ayar_bolumleri.sozcukler(q):
            with vt.islem() as b:
                devingen = arama.devingen_dizin(b, k["rol"], ARAMA)
        return arama.ara(q, ARAMA_SABIT, devingen, k["rol"], en_cok)

    @uygulama.get("/ara", response_class=HTMLResponse)
    async def ara_sayfasi(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/kurulum" if kurulum_gerekli() else "/giris")
        sonuc = arama_sonucu(k, istek.query_params.get("q", ""), arama.SAYFA_EN_COK)
        return sayfa(
            istek,
            "ara.html",
            k,
            ara=sonuc,
            ara_gruplari=arama.gruplu(sonuc["sonuclar"]),
            sik_isler=[] if sonuc["etkin"] else arama.sik_isler(ARAMA_SABIT, k["rol"]),
            yonetici=k["rol"] == "yonetici",
        )

    @uygulama.get("/api/ara")
    async def api_ara(istek: Request):
        """Yan menüdeki kutunun önerileri: {"sorgu", "sonuclar": [{"tur","ad","yer","yol"}], "toplam", "fazla"}."""
        k = kullanici(istek)
        if not k:
            return JSONResponse({"hata": "Oturum gerekli."}, status_code=401)
        ham = istek.query_params.get("q", "")
        if len(arama.sorgu_duzelt(ham)) < arama.ONERI_EN_KISA:  # veritabanına gidilmez
            return {"sorgu": arama.sorgu_duzelt(ham), "sonuclar": [], "toplam": 0, "fazla": False}
        sonuc = arama_sonucu(k, ham, arama.ONERI_EN_COK)
        return {
            "sorgu": sonuc["sorgu"],
            "sonuclar": [{a: s[a] for a in ("tur", "ad", "yer", "yol")} for s in sonuc["sonuclar"]],
            "toplam": sonuc["toplam"],
            "fazla": sonuc["fazla"],
        }

    @uygulama.post("/islem")
    async def islem(istek: Request):
        """Tahtalara komut. Hedef önceliği (0.17.0): `tek` > `kapsam` > işaretli liste; dallar arasında düşme yoktur
        (tahta_liste.islem_hedefi). `tek=<tur>:<id>` gelince YALNIZ o tahta işlenir; formdaki `tur` ve işaretli
        `tahta` listesi okunmaz. `kapsam=hepsi` yalnız `kilitle` ile ve yalnız onaylı + çevrimiçi tahtalara gider;
        sınav penceresindeki tahtalar ATLANIR ve iletide sayısı söylenir (V2, 0.18.0; yalnız bu dalda).
        Hata dallarında komut yazılmaz, tahta uyandırılmaz."""
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        form = await istek.form()
        donus = tahta_liste.guvenli_donus(form.get("donus"), "/tahtalar")
        secim = tahta_liste.islem_hedefi(form)
        if "hata" in secim:
            return yonlendir(donus, secim["hata"], hata=True)
        tur, dal = secim["tur"], secim["dal"]
        idler = secim.get("idler") or []
        if tur == "temizlik":  # K7: yalnız tahta sayfasındaki onaylı uçtan (yetenek denetimiyle) verilir
            return yonlendir(donus, "Oturum temizliği tahta sayfasından başlatılır.", hata=True)
        veri: dict = {}
        if tur == "duyuru":
            # Hemen gönderim (0.17.0'dan beri arayüzü yok; uç korunur): tek yayın yolundan, hedef seçili tahtalar.
            metin_ = str(form.get("metin", "")).strip()
            baslik = str(form.get("baslik", "")).strip()[:200]
            if not metin_:
                return yonlendir(donus, "Duyuru metni boş olamaz.", hata=True)
            if guvenlik.tc_kimlik_var(metin_) or guvenlik.tc_kimlik_var(baslik):
                with vt.islem() as b:
                    vt.kayit_dus(b, k["ad"], "Duyuru reddedildi", "T.C. kimlik numarasına benzeyen sayı", istemci_ip(istek))
                return yonlendir(donus, guvenlik.TC_KIMLIK_ILETISI, hata=True)
            try:
                sure_dk = max(1, min(240, int(str(form.get("sure_dk", "5")))))
            except ValueError:
                sure_dk = 5
            with vt.islem() as b:
                if not hedef.coz(b, {"tahtalar": idler}):
                    return yonlendir(donus, "Seçilen tahtalar bulunamadı.", hata=True)
                _, idler = duyuru.duyuru_yayimla(
                    b,
                    baslik=baslik,
                    metin=metin_[:4000],
                    sure_sn=sure_dk * 60,
                    kapatilabilir=form.get("kapatilabilir") == "1",
                    hedef={"tahtalar": idler},
                    olusturan=k["ad"],
                    an=vt.simdi(),
                    ip=istemci_ip(istek),
                )
            uyandir_hepsi(idler)
            return yonlendir(donus, f"Duyuru: {len(idler)} tahtaya gönderildi.")
        omur = None
        if tur == "guncelle":
            veri = {"sha256": paket.ajan_paketi().sha256, "surum": paket.ajan_paketi().surum}
        notlar = []
        atlanan_cevrimdisi = 0
        atlanan_sinav = 0
        with vt.islem() as b:
            if dal == "tek":
                tahtalar = b.execute("SELECT * FROM tahta WHERE durum = 'onayli' AND id = ?", (secim["id"],)).fetchall()
                if not tahtalar:
                    return yonlendir(donus, "Tahta bulunamadı.", hata=True)
                if tahta_liste.liste_yolu_mu(donus) and "#" not in donus:
                    # Liste, komut verilen satırda açılır; sayfa başındaki ileti ekran dışında kalacağı için ileti
                    # o satırda da çizilir (s=<id>; tahtalar.html).
                    donus += ("&" if "?" in donus else "?") + f"s={secim['id']}#t-{secim['id']}"
            elif dal == "kapsam":
                an = vt.simdi()
                onaylilar = b.execute("SELECT * FROM tahta WHERE durum = 'onayli' ORDER BY id").fetchall()
                tahtalar = [t for t in onaylilar if t["son_gorulme"] and an - t["son_gorulme"] < ayar.CEVRIMICI_ESIK_SN]
                atlanan_cevrimdisi = len(onaylilar) - len(tahtalar)
                if not tahtalar:
                    return yonlendir(donus, "Çevrimiçi tahta yok; komut gönderilmedi.", hata=True)
                # V2 (varsayıldı; geri almak için bu süzme kaldırılır): sınav penceresindeki tahta toplu kilide girmez.
                # Kaynak satır rozetindeki `t.sinav` ile aynıdır (sinav.pencere_haritasi).
                sinavdakiler = set(sinav.pencere_haritasi(b, an))
                atlanan_sinav = sum(1 for t in tahtalar if t["id"] in sinavdakiler)
                tahtalar = [t for t in tahtalar if t["id"] not in sinavdakiler]
                if not tahtalar:
                    return yonlendir(donus, "Çevrimiçi tahtaların hepsi sınav kipinde; komut gönderilmedi.", hata=True)
            else:
                isaret = ",".join("?" * len(idler))
                tahtalar = b.execute(
                    f"SELECT * FROM tahta WHERE durum = 'onayli' AND id IN ({isaret})", idler
                ).fetchall()
                if not tahtalar:
                    return yonlendir(donus, "Seçilen tahtalar bulunamadı.", hata=True)
            adlar = ", ".join(t["ad"] for t in tahtalar)
            if tur == "uyandir":
                for t in tahtalar:
                    if not t["mac"]:
                        notlar.append(f"{t['ad']}: MAC adresi bilinmiyor")
                        continue
                    try:
                        wol.gonder(t["mac"], t["ip"])
                    except (ValueError, OSError) as hata:
                        notlar.append(f"{t['ad']}: {hata}")
            else:
                if tur == "envanter":  # A6: eski ajan komutu tanımaz; yeteneği olmayan tahta atlanır
                    atlanan = [t for t in tahtalar if envanter_mod.YETENEK not in acil.yetenekler(t)]
                    tahtalar = [t for t in tahtalar if envanter_mod.YETENEK in acil.yetenekler(t)]
                    if atlanan:
                        notlar.append(f"{len(atlanan)} tahtada ajan güncellenmeli; envanter istenmedi")
                    if not tahtalar:
                        return yonlendir(donus, "Seçilen tahtaların ajanı envanter göndermiyor; önce ajanı güncelleyin.", hata=True)
                    adlar = ", ".join(t["ad"] for t in tahtalar)
                for t in tahtalar:
                    komut_ekle(b, t["id"], tur, veri, k["ad"], omur)
            ayrinti = f"{len(tahtalar)} tahta: {adlar}"
            if dal == "kapsam":
                ayrinti = "bütün çevrimiçi tahtalar · " + ayrinti
                if atlanan_sinav:
                    ayrinti += f" · {atlanan_sinav} tahta sınavda atlandı"
            vt.kayit_dus(b, k["ad"], KOMUT_ADI[tur], ayrinti, istemci_ip(istek))
        for t in tahtalar:
            uyandir(t["id"])
        if tur == "uyandir":
            mesaj = f"Uzaktan açma paketi {len(tahtalar) - len(notlar)} tahtaya gönderildi. Tahtanın açılıp açılmadığını Tahtalar sayfasından izleyin."
        elif dal == "tek":
            mesaj = f"{KOMUT_ADI[tur]}: {tahtalar[0]['ad']} tahtasına gönderildi."
        else:
            mesaj = f"{KOMUT_ADI[tur]}: {len(tahtalar)} tahtaya gönderildi."
        if atlanan_sinav:
            mesaj += f" {atlanan_sinav} tahta sınav kipinde olduğu için atlandı."
        if atlanan_cevrimdisi:
            mesaj += f" {atlanan_cevrimdisi} çevrimdışı tahtaya gönderilmedi."
        if notlar:
            mesaj += " " + "; ".join(notlar)
        return yonlendir(donus, mesaj)

    # ---- tahta ayrıntısı -----------------------------------------------------
    @uygulama.get("/tahta/{tahta_id}", response_class=HTMLResponse)
    async def tahta_sayfasi(istek: Request, tahta_id: int):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        with vt.islem() as b:
            satir = b.execute("SELECT * FROM tahta WHERE id = ? AND durum != 'iptal'", (tahta_id,)).fetchone()
            if not satir:
                return yonlendir("/tahtalar", "Tahta bulunamadı.", hata=True)
            komutlar = b.execute(
                "SELECT * FROM komut WHERE tahta_id = ? ORDER BY id DESC LIMIT 30", (tahta_id,)
            ).fetchall()
            gruplar = b.execute("SELECT id, ad FROM tahta_grubu ORDER BY ad COLLATE NOCASE").fetchall()
            uyelik = grup_uyelikleri(b)
            binalar = mevcut_binalar(b)
            program_baglami = panel_program.tahta_program_baglami(b, satir)
            sinavlar = sinav.pencere_haritasi(b, vt.simdi())
            altyapi = altyapi_verisi(b)
            tahta_arizalari = ariza_mod.listele(b, "", tahta_id)
            adres_listesi = adresler.al(b)
            temizlik_ozeti = temizlik_mod.tahta_ozeti(b, satir)
            usb_etkin = usb_anahtar.ayar_al(b)["etkin"]  # 0.11.0: "USB anahtar" satırı yalnız özellik açıkken
            acil_suruyor = acil.aktif(b) is not None
            kilit_acik = program_is.program_ozeti(b, datetime.fromtimestamp(vt.simdi(), ISTANBUL))["kilit"] != "kapali"
        tani = json.loads(satir["tani_json"]) if satir["tani_json"] else None
        durum = json.loads(satir["durum_json"] or "{}")
        t_gorunum = tahta_gorunumu(satir, None, uyelik, None, sinavlar, altyapi, acil_suruyor, kilit_acik)
        bagli = t_gorunum["bagli_adres"]
        # 0.17.0: sayfa dört sekmedir (Genel · Program · Bakım · Bilgiler); yönlendirme yapılmaz, bilinmeyen değer Genel'dir.
        sekme = tahta_liste.sekme_coz(
            istek.query_params.get("sekme", ""), k["rol"], satir["durum"], istek.query_params.get("yer", "")
        )
        return sayfa(
            istek,
            "tahta.html",
            k,
            t=t_gorunum,
            sekme=sekme,
            sekme_yolu=f"/tahta/{tahta_id}" + (f"?sekme={sekme}" if sekme != "genel" else ""),
            menu_ogeleri=tahta_liste.menu_ogeleri(t_gorunum, k["rol"]),
            # A6 (§6.3): envanter kartı, arıza kartı, bağlantı satırı
            envanter=envanter_mod.gorunum(satir["envanter_json"]),
            envanter_zamani=satir["envanter_zamani"],
            demirbas_no=satir["demirbas_no"],
            envanter_notu=satir["envanter_notu"],
            arizalar=tahta_arizalari,
            ariza_kategorileri=ariza_mod.ARIZA_KATEGORI,
            baglanti={
                "adres": bagli,
                "listede": (not adres_listesi) or (bagli in adres_listesi) if bagli else None,
                "liste_guncel": (
                    (durum.get("adres_listesi_ozet") == adresler.ozet(adres_listesi)) if adres_listesi and t_gorunum["adres_listesi_yetenegi"] else None
                ),
                "imza": "imza" in t_gorunum["yetenekler"],
            },
            ham=satir,
            komutlar=komutlar,
            tani=tani,
            durum=durum,
            gruplar=gruplar,
            binalar=binalar,
            program=program_baglami,
            gun_adlari=program_mod.GUN_ADLARI,
            temizlik=temizlik_ozeti,
            temizlik_zamanlari=temizlik_mod.ZAMANLAR,
            usb_etkin=usb_etkin,
            program_kilidi_acik=kilit_acik,
        )

    @uygulama.post("/tahta/{tahta_id}/temizlik")
    async def tahta_temizlik(istek: Request, tahta_id: int):
        """K7: "Şimdi temizle" (panelde onay dialoglu). Yalnız onaylı, çevrimiçi ve `temizlik` yeteneği
        bildiren tahtaya; ayar kapalı olsa da elle verilebilir. Tahtada kullanan kişi 60 sn içinde vazgeçebilir."""
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        if not acil.yetkili(k):
            return yetkisiz_reddet(istek, k, "Oturum temizliği")
        donus = f"/tahta/{tahta_id}?sekme=bakim&yer=temizlik#ileti"  # ileti Bakım'daki temizlik bölümünde çizilir
        form = await istek.form()
        if form.get("eylem") != "temizle":
            return yonlendir(donus, "Bilinmeyen işlem.", hata=True)
        with vt.islem() as b:
            t = b.execute("SELECT * FROM tahta WHERE id = ? AND durum = 'onayli'", (tahta_id,)).fetchone()
            if not t:
                return yonlendir("/tahtalar", "Tahta bulunamadı.", hata=True)
            if not temizlik_mod.yetenekli(t):
                return yonlendir(donus, "Bu tahtanın ajanı oturum temizliğini bilmiyor; önce ajanı güncelleyin.", hata=True)
            if not t["son_gorulme"] or vt.simdi() - t["son_gorulme"] >= ayar.CEVRIMICI_ESIK_SN:
                return yonlendir(donus, "Tahta çevrimdışı; temizlik verilmedi (kaçan temizlik sonradan yapılmaz).", hata=True)
            temizlik_mod.temizlik_komutu(b, t["id"], k["ad"])
            vt.kayit_dus(b, k["ad"], "Oturum temizliği", f"elle: {t['ad']}", istemci_ip(istek))
        uyandir(tahta_id)
        return yonlendir(donus, "Oturum temizliği tahtaya gönderildi. Tahta kullanılıyorsa 60 saniyelik uyarı çıkar; "
                                "sonuç birkaç dakika içinde bu bölümde görünür.")

    def mevcut_binalar(b) -> list[str]:
        """Kayıtlı tahtalarda geçen bina adları (datalist önerisi; büyük/küçük harf duyarsız tekil)."""
        gorulen: dict[str, str] = {}
        for s in b.execute("SELECT bina FROM tahta WHERE durum != 'iptal' AND bina != '' ORDER BY bina"):
            gorulen.setdefault(hedef.bina_anahtari(s["bina"]), s["bina"].strip())
        return sorted(gorulen.values(), key=lambda a: metin.tr_sirala_anahtari(a))

    def tahta_alanlari_coz(form) -> dict:
        """Tahta formundaki nitelik alanları; hatada iletiyle ValueError."""
        bina = " ".join(str(form.get("bina", "")).split())
        if len(bina) > hedef.BINA_EN_UZUN:
            raise ValueError(f"Bina adı en çok {hedef.BINA_EN_UZUN} karakter olabilir.")
        duzeyler = [d for d in DUZEYLER if d in {str(x) for x in form.getlist("duzey")}]
        if any(str(x) not in DUZEYLER for x in form.getlist("duzey")):
            raise ValueError("Düzey değeri geçersiz.")
        devre = str(form.get("devre", ""))
        if devre and devre not in DEVRELER:
            raise ValueError("Devre değeri geçersiz.")
        return {
            "bina": bina,
            "kat": hedef.kat_coz(form.get("kat", "")),
            "duzeyler": ",".join(duzeyler),
            "devre": devre,
            "subeler": ",".join(hedef.subeler_coz(form.get("subeler", ""))),
            "gruplar": sorted({int(g) for g in form.getlist("grup") if str(g).isdigit() and hedef.kimlik_mi(g)}),
        }

    def grup_uyeligi_yaz(b, tahta_id: int, grup_idler) -> None:
        b.execute("DELETE FROM tahta_grubu_uye WHERE tahta_id = ?", (tahta_id,))
        for grup_id in grup_idler:
            b.execute(
                "INSERT OR IGNORE INTO tahta_grubu_uye (grup_id, tahta_id) SELECT id, ? FROM tahta_grubu WHERE id = ?",
                (tahta_id, grup_id),
            )

    def adlandirma_satirlari(b) -> list[tuple]:
        """Toplu adlandırma kuralının girdisi: kaldırılmamış (onaylı + bekleyen) tahtaların (kimlik, ad, makine adı)."""
        return [tuple(s) for s in b.execute("SELECT id, ad, makine_adi FROM tahta WHERE durum != 'iptal' ORDER BY id")]

    def nolar_metni(idler: list[int]) -> str:
        """"No 3, No 5" (en çok 5 numara, fazlası " …")."""
        return ", ".join(f"No {i}" for i in idler[:5]) + (" …" if len(idler) > 5 else "")

    def ayni_adli_baska_tahtalar(b, tahta_id: int, ad: str) -> list[int]:
        """Adı `ad` ile aynı olan (tahta_liste.ad_anahtari) öbür kaldırılmamış tahtaların kimlikleri."""
        anahtar = tahta_liste.ad_anahtari(ad)
        return [
            s["id"]
            for s in b.execute("SELECT id, ad FROM tahta WHERE durum != 'iptal' AND id != ? ORDER BY id", (tahta_id,))
            if anahtar and tahta_liste.ad_anahtari(s["ad"]) == anahtar
        ]

    @uygulama.post("/tahta/{tahta_id}/kaydet")
    async def tahta_kaydet(istek: Request, tahta_id: int):
        k = kullanici(istek)
        if not k or k["rol"] != "yonetici":
            if k:
                with vt.islem() as b:
                    vt.kayit_dus(b, k["ad"], "Yetkisiz işlem reddedildi", f"Tahta #{tahta_id} düzenleme", istemci_ip(istek))
            return yonlendir(f"/tahta/{tahta_id}", "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        form = await istek.form()
        ad = str(form.get("ad", "")).strip()[:60]
        eylem = str(form.get("eylem", "kaydet"))
        alanlar = None
        if form.get("alanlar") == "1":  # nitelik alanları formda varsa (gizli işaret) yazılır
            try:
                alanlar = tahta_alanlari_coz(form)
            except ValueError as hata:
                return yonlendir(f"/tahta/{tahta_id}?sekme=bilgiler", str(hata), hata=True)
        with vt.islem() as b:
            satir = b.execute("SELECT * FROM tahta WHERE id = ?", (tahta_id,)).fetchone()
            if not satir:
                return yonlendir("/tahtalar", "Tahta bulunamadı.", hata=True)
            if eylem == "sil":
                b.execute("UPDATE tahta SET durum = 'iptal', anahtar_ozet = '' WHERE id = ?", (tahta_id,))
                b.execute("DELETE FROM tahta_grubu_uye WHERE tahta_id = ?", (tahta_id,))
                b.execute("DELETE FROM tahta_ders WHERE tahta_id = ?", (tahta_id,))  # K34
                b.execute("DELETE FROM program_isaret WHERE tahta_id = ?", (tahta_id,))
                b.execute("DELETE FROM yoklama_belirtec WHERE tahta_id = ?", (tahta_id,))
                vt.kayit_dus(b, k["ad"], "Tahta kaldırıldı", satir["ad"], istemci_ip(istek))
                return yonlendir("/tahtalar", f"{satir['ad']} kaldırıldı. Tahtadaki ajan artık sunucuya bağlanamaz.")
            if not ad:
                return yonlendir(f"/tahta/{tahta_id}?sekme=bilgiler", "Tahta adı boş olamaz.", hata=True)
            yeni_durum = "onayli" if eylem == "onayla" else satir["durum"]
            b.execute(
                "UPDATE tahta SET ad = ?, derslik = ?, durum = ? WHERE id = ?",
                (ad, str(form.get("derslik", "")).strip()[:60], yeni_durum, tahta_id),
            )
            ayrinti = ad
            if alanlar is not None:
                b.execute(
                    "UPDATE tahta SET bina = ?, kat = ?, duzeyler = ?, devre = ?, subeler = ? WHERE id = ?",
                    (alanlar["bina"], alanlar["kat"], alanlar["duzeyler"], alanlar["devre"], alanlar["subeler"], tahta_id),
                )
                grup_uyeligi_yaz(b, tahta_id, alanlar["gruplar"])
                guncel = b.execute("SELECT * FROM tahta WHERE id = ?", (tahta_id,)).fetchone()
                ayrinti += " · " + (hedef.alanlar_metni(guncel) or "nitelik yok")
            vt.kayit_dus(
                b, k["ad"], "Tahta onaylandı" if eylem == "onayla" else "Tahta düzenlendi", ayrinti, istemci_ip(istek)
            )
            kalan_bekleyen = b.execute("SELECT COUNT(*) FROM tahta WHERE durum = 'bekliyor'").fetchone()[0]
            ayni_ad = ayni_adli_baska_tahtalar(b, tahta_id, ad)
        uyandir(tahta_id)
        # 0.21.0: aynı ad REDDEDİLMEZ (okul bilerek aynı adı verebilir); yalnız uyarılır.
        ayni_ad_notu = ""
        if ayni_ad:
            ayni_ad_notu = (
                f" Dikkat: bu adı taşıyan {len(ayni_ad)} tahta daha var ({nolar_metni(ayni_ad)}); "
                "tahtaları ayırt etmek için farklı bir ad verin."
            )
        # Onaydan sonra Genel açılır (komutlar artık açık); düzenlemeden sonra Bilgiler'de kalınır.
        if eylem == "onayla" and satir["durum"] == "bekliyor":
            mesaj = f"{ad} onaylandı; artık komut alır."
            if kalan_bekleyen:
                mesaj += f" {kalan_bekleyen} tahta daha onay bekliyor (Tahtalar sayfasında)."
            return yonlendir(f"/tahta/{tahta_id}", mesaj + ayni_ad_notu)
        return yonlendir(
            f"/tahta/{tahta_id}" + ("" if eylem == "onayla" else "?sekme=bilgiler"), "Kaydedildi." + ayni_ad_notu
        )

    @uygulama.post("/tahtalar/adlandir")
    async def tahtalar_adlandir(istek: Request):
        """0.21.0: adını kurulumdan alan (bilgisayar adı ya da "Yeni tahta") ve adı başka bir tahtayla AYNI olan her
        tahtaya "Tahta <no>" adını verir (Tahtalar › aynı ad bandı; kural `tahta_liste.adlandirilacaklar`). Elle
        verilmiş ad değişmez.

        Yalnız yönetici; yalnız `eylem=adlandir` ile (onay penceresinin "evet" düğmesi ekler). Derslik, nitelikler,
        durum ve makine adı DEĞİŞMEZ (eski ad makine adıdır, sütununda durur). Liste sunucuda yeniden hesaplanır
        (formdan kimlik okunmaz) ve sabit noktaya kadar yinelenir: verilen ad yeni bir çakışma kurarsa o da çözülür;
        elle verilmiş adla kalan çakışma iletide numaralarıyla söylenir. İşlem kaydına yalnız sayı yazılır."""
        k = kullanici(istek)
        if not k or k["rol"] != "yonetici":
            if k:
                with vt.islem() as b:
                    vt.kayit_dus(b, k["ad"], "Yetkisiz işlem reddedildi", "Tahtaları yeniden adlandırma", istemci_ip(istek))
            return yonlendir("/tahtalar", "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        form = await istek.form()
        if str(form.get("eylem", "")) != "adlandir":
            return yonlendir("/tahtalar", "Bilinmeyen işlem.", hata=True)
        with vt.islem() as b:
            degisen: list[int] = []
            satirlar = adlandirma_satirlari(b)
            # Sabit nokta: her tahta en çok bir kez değişir (kendi varsayılan adını alan tahta bir daha seçilmez).
            for _ in range(len(satirlar) + 1):
                idler = tahta_liste.adlandirilacaklar(satirlar)
                if not idler:
                    break
                for tahta_id in idler:
                    b.execute("UPDATE tahta SET ad = ? WHERE id = ?", (tahta_liste.varsayilan_ad(tahta_id), tahta_id))
                    degisen.append(tahta_id)
                satirlar = adlandirma_satirlari(b)
            # Verilen adlardan biri elle verilmiş bir adla hâlâ çakışıyorsa (ör. başka tahtaya elle "Tahta 7" denmiş).
            yeni_adlar = {tahta_liste.ad_anahtari(tahta_liste.varsayilan_ad(i)) for i in degisen}
            adlar = {k_: ad for k_, ad, _ in satirlar}
            kalan = [
                i
                for i in tahta_liste.ayni_adlilar((k_, ad) for k_, ad, _ in satirlar)
                if tahta_liste.ad_anahtari(adlar[i]) in yeni_adlar
            ]
            if degisen:
                vt.kayit_dus(b, k["ad"], "Aynı adlı tahtalar yeniden adlandırıldı", f"{len(degisen)} tahta", istemci_ip(istek))
        uyandir_hepsi(degisen)  # kilit ekranının üst bandı tahtanın adını taşır
        if not degisen:
            return yonlendir("/tahtalar", "Kurulumdan kalan aynı adı taşıyan tahta yok; hiçbir ad değişmedi.")
        mesaj = f"{len(degisen)} tahta “Tahta <no>” biçiminde yeniden adlandırıldı. Derslikler ve elle verilen adlar değişmedi."
        if kalan:
            mesaj += (
                f" Dikkat: adı hâlâ aynı olan {len(kalan)} tahta var ({nolar_metni(kalan)}); elle verilen ad "
                "değiştirilmedi, birini kendi sayfasının Bilgiler sekmesinden yeniden adlandırın."
            )
        return yonlendir("/tahtalar", mesaj)

    # ---- tahta ekleme --------------------------------------------------------
    @uygulama.get("/ekle", response_class=HTMLResponse)
    async def ekle(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        with vt.islem() as b:
            pencere = vt.ayar_al(b, "kayit_penceresi") or {}
        acik = bool(pencere) and pencere.get("bitis", 0) > vt.simdi()
        return sayfa(
            istek,
            "ekle.html",
            k,
            acik=acik,
            kod=pencere.get("kod") if acik else "",
            bitis=pencere.get("bitis") if acik else None,
            adres=sunucu_adresi(istek),
            parmak_izi=parmak_izi,
            paket=paket.ajan_paketi(),
        )

    @uygulama.post("/ekle")
    async def ekle_ayarla(istek: Request):
        k = kullanici(istek)
        if not k or k["rol"] != "yonetici":
            if k:
                with vt.islem() as b:
                    vt.kayit_dus(b, k["ad"], "Yetkisiz işlem reddedildi", "Tahta ekleme penceresi", istemci_ip(istek))
            return yonlendir("/ekle", "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        form = await istek.form()
        with vt.islem() as b:
            if form.get("eylem") == "kapat":
                vt.ayar_yaz(b, "kayit_penceresi", {})
                vt.kayit_dus(b, k["ad"], "Tahta ekleme kapatıldı", "", istemci_ip(istek))
                return yonlendir("/ekle", "Tahta ekleme kapatıldı.")
            vt.ayar_yaz(
                b,
                "kayit_penceresi",
                {"kod": guvenlik.kayit_kodu(), "bitis": vt.simdi() + ayar.KAYIT_PENCERESI_DK * 60},
            )
            vt.kayit_dus(b, k["ad"], "Tahta ekleme açıldı", f"{ayar.KAYIT_PENCERESI_DK} dakika", istemci_ip(istek))
        return yonlendir("/ekle", "Tahta ekleme açıldı; yeni eşleştirme kodu üretildi.")

    @uygulama.get("/kur")
    async def kur_betigi(istek: Request):
        with vt.islem() as b:
            liste = adresler.al(b)
        icerik = paket.kurulum_betigi(sunucu_adresi(istek), parmak_izi, liste)
        return Response(
            icerik,
            media_type="application/x-sh",
            headers={"Content-Disposition": 'attachment; filename="tahta-kur.sh"'},
        )

    @uygulama.get("/kur/paket")
    async def kur_paketi():
        p = paket.ajan_paketi()
        return Response(
            p.icerik,
            media_type="application/vnd.debian.binary-package",
            headers={"Content-Disposition": f'attachment; filename="{p.dosya_adi}"', "X-Sha256": p.sha256},
        )

    def usb_adresleri() -> list[str]:
        with vt.islem() as b:
            return adresler.al(b)

    @uygulama.get("/kur/usb.zip")
    async def kur_usb(istek: Request):
        if not kullanici(istek):
            return yonlendir("/giris")
        return Response(
            paket.usb_paketi(sunucu_adresi(istek), parmak_izi, usb_adresleri()),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="tahta-kurulum.zip"'},
        )

    # ---- kayıt, kullanıcılar, ayarlar (duyurular: panel_duyuru.py) ------------
    @uygulama.get("/kayit", response_class=HTMLResponse)
    async def kayit(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        with vt.islem() as b:
            satirlar = b.execute("SELECT * FROM kayit ORDER BY id DESC LIMIT 300").fetchall()
        return sayfa(istek, "kayit.html", k, kayitlar=satirlar)

    @uygulama.get("/kullanicilar", response_class=HTMLResponse)
    async def kullanicilar(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        if k["rol"] != "yonetici":
            return yonlendir("/", "Bu sayfa için yönetici yetkisi gerekir.", hata=True)
        # 0.16.0: sayfa Ayarlar › Panel kullanıcıları bölümüdür; eski adres (yer imi, eski yönlendirme) oraya gider.
        return yonlendir("/ayarlar/kullanicilar", istek.query_params.get("m", ""), hata=istek.query_params.get("t") == "hata")

    def yetkisiz_reddet(istek: Request, k, islem: str):
        """Yönetici olmayanın yetkili işlem denemesini kayda düşürüp reddeder (oturum yoksa girişe)."""
        if not k:
            return yonlendir("/giris")
        with vt.islem() as b:
            vt.kayit_dus(b, k["ad"], "Yetkisiz işlem reddedildi", islem, istemci_ip(istek))
        return yonlendir("/", "Bu işlem için yönetici yetkisi gerekir.", hata=True)

    @uygulama.post("/kullanicilar")
    async def kullanici_islem(istek: Request):
        k = kullanici(istek)
        if not k or k["rol"] != "yonetici":
            return yetkisiz_reddet(istek, k, "Kullanıcı işlemi")
        form = await istek.form()
        eylem = str(form.get("eylem", ""))
        # İleti ilgili kartta çizilir: ekleme "Kullanıcı ekle" kartında, satır işlemleri "Hesaplar" kartında.
        ekle_adresi = "/ayarlar/kullanicilar?yer=ekle#ileti"
        hesap_adresi = "/ayarlar/kullanicilar?yer=hesaplar#ileti"
        if eylem == "ekle":
            ad = str(form.get("ad", "")).strip().lower()
            parola = str(form.get("parola", ""))
            rol = str(form.get("rol", "idareci"))
            ekle_hatasi = ""
            if len(ad) < 3 or len(parola) < 8 or rol not in ROLLER:
                ekle_hatasi = "Kullanıcı adı en az 3, parola en az 8 karakter olmalı."
            else:
                with vt.islem() as b:
                    if b.execute("SELECT 1 FROM kullanici WHERE ad = ?", (ad,)).fetchone():
                        ekle_hatasi = "Bu kullanıcı adı zaten var."
            if ekle_hatasi:
                # Sayfa aynı yanıtta (400) yeniden çizilir: yazılan ad soyad, kullanıcı adı ve yetki kaybolmaz.
                # Parola hiçbir zaman geri yazılmaz.
                return bolum_sayfasi(
                    istek, k, "kullanicilar", yer="ekle", hata=ekle_hatasi,
                    ekle_formu={"gorunen_ad": str(form.get("gorunen_ad", "")).strip()[:80], "ad": ad[:40],
                                "rol": rol if rol in ROLLER else "idareci"},
                )  # fmt: skip
        with vt.islem() as b:
            if eylem == "ekle":
                if b.execute("SELECT 1 FROM kullanici WHERE ad = ?", (ad,)).fetchone():  # iki işlem arasında eklendiyse
                    return yonlendir(ekle_adresi, "Bu kullanıcı adı zaten var.", hata=True)
                # acil_yetki 0.8.0'dan beri okunmaz (K4: bütün kullanıcılar yetkili); eski sürüme dönülürse
                # aynı davranış sürsün diye 1 yazılır.
                b.execute(
                    "INSERT INTO kullanici (ad, gorunen_ad, parola_ozet, rol, olusturma, acil_yetki) VALUES (?, ?, ?, ?, ?, 1)",
                    (ad, str(form.get("gorunen_ad", "")).strip() or ad, guvenlik.parola_ozetle(parola), rol, vt.simdi()),
                )
                vt.kayit_dus(b, k["ad"], "Kullanıcı eklendi", f"{ad} ({ROLLER[rol]})", istemci_ip(istek))
                return yonlendir(ekle_adresi, "Kullanıcı eklendi.")
            hedef = b.execute("SELECT * FROM kullanici WHERE id = ?", (str(form.get("id", "")),)).fetchone()
            if not hedef:
                return yonlendir(hesap_adresi, "Kullanıcı bulunamadı.", hata=True)
            if eylem == "durum":
                if hedef["id"] == k["id"]:
                    return yonlendir(hesap_adresi, "Kendi hesabınızı kapatamazsınız.", hata=True)
                b.execute("UPDATE kullanici SET aktif = ? WHERE id = ?", (0 if hedef["aktif"] else 1, hedef["id"]))
                b.execute("DELETE FROM oturum WHERE kullanici_id = ?", (hedef["id"],))
                vt.kayit_dus(
                    b, k["ad"], "Kullanıcı kapatıldı" if hedef["aktif"] else "Kullanıcı açıldı", hedef["ad"], istemci_ip(istek)
                )
            elif eylem == "parola":
                parola = str(form.get("parola", ""))
                if len(parola) < 8:
                    return yonlendir(hesap_adresi, "Parola en az 8 karakter olmalı.", hata=True)
                b.execute(
                    "UPDATE kullanici SET parola_ozet = ? WHERE id = ?", (guvenlik.parola_ozetle(parola), hedef["id"])
                )
                if hedef["id"] != k["id"]:
                    b.execute("DELETE FROM oturum WHERE kullanici_id = ?", (hedef["id"],))
                vt.kayit_dus(b, k["ad"], "Parola değiştirildi", hedef["ad"], istemci_ip(istek))
            elif eylem == "acil_yetki":
                # 0.8.0 (K4): ayrı acil yetkisi yoktur; eski bir sekmeden gelen istek reddedilir ve kayda düşer.
                vt.kayit_dus(b, k["ad"], "Acil yetkisi değişikliği reddedildi", f"{hedef['ad']}: ayrı yetki kaldırıldı",
                             istemci_ip(istek))  # fmt: skip
                return yonlendir(hesap_adresi, "Acil yayın yetkisi artık ayrı verilmez: bütün yönetici ve idareciler "
                                 "parola ve onayla başlatabilir.", hata=True)  # fmt: skip
            else:
                return yonlendir(hesap_adresi, "Bilinmeyen işlem.", hata=True)
        return yonlendir(hesap_adresi, "Kaydedildi.")

    # ---- Ayarlar (0.16.0): giriş sayfası + 11 bölüm; liste, özetler ve arama `ayar_bolumleri.py`'dedir ----
    def bugun_tarihi():
        return datetime.fromtimestamp(vt.simdi(), ISTANBUL).date()

    @uygulama.get("/ayarlar", response_class=HTMLResponse)
    async def ayarlar(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        if k["rol"] != "yonetici":
            return yonlendir("/", "Bu sayfa için yönetici yetkisi gerekir.", hata=True)
        # Eski tek sayfanın `?yer=` adresi (yer imi, açık sekmedeki eski yönlendirme) yeni bölüme taşınır.
        yer = istek.query_params.get("yer", "")
        hedef = ayar_bolumleri.ESKI_YER.get(yer)
        if hedef:
            m = istek.query_params.get("m", "")
            if hedef.startswith("/"):
                adres = hedef + ("#ileti" if m else "")
            else:
                adres = f"/ayarlar/{hedef}" + (f"?yer={yer}#ileti" if m else "")
            return yonlendir(adres, m, hata=istek.query_params.get("t") == "hata")
        sonuc = ayar_bolumleri.ara(istek.query_params.get("ara", ""))
        with vt.islem() as b:
            ozet = ayar_bolumleri.ozetler(b, bugun_tarihi())
            kurulum = ayar_bolumleri.kurulum(b, bugun_tarihi())
        return sayfa(
            istek,
            "ayarlar.html",
            k,
            ara=sonuc,
            ayar_kumeleri=ayar_bolumleri.menu(ozet, sonuc["bolumler"] if sonuc["etkin"] else None),
            baska_yerde=ayar_bolumleri.baska_yerde(sonuc["baska"] if sonuc["etkin"] else None),
            kurulum=kurulum,
            eski_parca=ayar_bolumleri.ESKI_PARCA,
            ara_en_uzun=ayar_bolumleri.SORGU_EN_UZUN,
        )

    @uygulama.get("/ayarlar/{anahtar}", response_class=HTMLResponse)
    async def ayar_bolumu(istek: Request, anahtar: str):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        if k["rol"] != "yonetici":
            return yonlendir("/", "Bu sayfa için yönetici yetkisi gerekir.", hata=True)
        if not ayar_bolumleri.bolum(anahtar):
            return yonlendir("/ayarlar", "Bilinmeyen ayar bölümü.", hata=True)
        return bolum_sayfasi(istek, k, anahtar)

    def eski_ajan_sayisi(b, yetenekli) -> int:
        return sum(1 for t in b.execute("SELECT * FROM tahta WHERE durum = 'onayli'") if not yetenekli(t))

    def bolum_baglami(b, anahtar: str) -> dict:
        """Yalnız o bölümün şablon bağlamı (değişken adları 0.15.0 tek sayfasındakilerle aynıdır)."""
        kilit_kodu_var = bool(vt.ayar_al(b, "kilit_kodu"))
        if anahtar == "okul":
            ana, vurgu = tema.tema_al(b)
            uretilen = tema.uret(ana, vurgu)
            logo = marka.logo_oku(b)
            logo_bilgi = None
            if logo:
                bilgi = logo[1]
                logo_bilgi = {
                    "tur": "PNG" if bilgi.get("tur") == "png" else "JPEG",
                    "en": bilgi.get("en"),
                    "boy": bilgi.get("boy"),
                    "kb": max(1, round(int(bilgi.get("boyut") or 0) / 1024)),
                    "zaman": datetime.fromtimestamp(int(bilgi.get("zaman") or 0), ISTANBUL).strftime("%d.%m.%Y %H:%M"),
                }
            return {
                "tema_ana": ana,
                "tema_vurgu": vurgu,
                "varsayilan_vurgu": tema.VARSAYILAN_VURGU,
                "tema_notlar": uretilen["notlar"],
                "tema_rapor": uretilen["rapor"],
                "logo": logo_bilgi,
            }
        if anahtar == "kilit":
            return {
                "kilit_kodu_var": kilit_kodu_var,
                "acilis_kilidi_acik": acilis_kilidi.ayar_al(b),
                "acilis_eski": eski_ajan_sayisi(b, acilis_kilidi.yetenekli),
                "acilis_en_yasli_sn": acilis_kilidi.EN_YASLI_OTURUM_SN,
                "usb_ayari": usb_anahtar.ayar_al(b),
            }
        if anahtar == "gunsonu":
            temizlik_ayari = temizlik_mod.ayar_al(b)
            return {
                "kapatma": vt.ayar_al(b, "otomatik_kapatma") or {},
                "temizlik_ayari": temizlik_ayari,
                "temizlik_zamani": temizlik_mod.zaman_ozeti(b, bugun_tarihi()),
                "temizlik_zamanlari": temizlik_mod.ZAMANLAR,
                "temizlik_eski": eski_ajan_sayisi(b, temizlik_mod.yetenekli),
            }
        if anahtar == "yuzer":
            return {
                "dugme_ayari": dugme.ayar_al(b),
                "dugme_islemleri": dugme.ISLEMLER,
                "dugme_eski": eski_ajan_sayisi(b, dugme.yetenekli),
                "dugme_yoklama_kapali": not yoklama_mod.etkin(b),
                "dugme_kilit_kodu_yok": not kilit_kodu_var,
            }
        if anahtar == "yoklama":
            return panel_yoklama.ayar_baglami(b)
        if anahtar == "usb":
            return panel_usb.ayar_baglami(b)
        if anahtar == "sinav":
            return {
                "sinav_kurallari": sinav.kurallar(b),
                "sinav_kurallari_ozel": isinstance(vt.ayar_al(b, "sinav_kurallari"), str),
                "sinav_kurallari_en_uzun": sinav.KURALLAR_EN_UZUN,
            }
        if anahtar == "veri":
            return {"saklama_durumu": saklama.durum(b, bugun_tarihi()), **panel_altyapi.yedek_ayar_baglami(b)}
        if anahtar == "sunucu":
            adres_listesi = adresler.al(b)
            adres_ozeti = adresler.ozet(adres_listesi)
            adres_durumu = {"onayli": 0, "yetenekli": 0, "alan": 0}
            for t in b.execute("SELECT durum_json FROM tahta WHERE durum = 'onayli'"):
                adres_durumu["onayli"] += 1
                durum_ = json.loads(t["durum_json"] or "{}")
                if ADRES_YETENEGI in (durum_.get("yetenekler") or []):
                    adres_durumu["yetenekli"] += 1
                    if adres_listesi and durum_.get("adres_listesi_ozet") == adres_ozeti:
                        adres_durumu["alan"] += 1
            return {
                "sunucu_adresleri": adres_listesi,
                "sunucu_adresleri_metni": "\n".join(adres_listesi),
                "adres_en_cok": adresler.EN_COK,
                "adres_durumu": adres_durumu,
                "ipler": guvenlik.yerel_ipler(),
                "https_port": ayar.HTTPS_PORT,
                "parmak_izi": parmak_izi,
                "veri_dizini": str(ayar.veri_dizini()),
            }
        if anahtar == "guncelleme":
            return {"guncelleme": guncelleme.gorunum(b)}  # saklanan durum; sayfa çizimi ağ çağrısı yapmaz (kural 32)
        if anahtar == "kullanicilar":
            return {"kullanicilar": b.execute("SELECT * FROM kullanici ORDER BY ad").fetchall()}
        return {}

    def bolum_sayfasi(istek: Request, k, anahtar: str, hata: str = "", yer: str = "", **ustune) -> HTMLResponse:
        """Ayarlar'ın bir bölüm sayfası. hata: doğrulama hatasında sayfa aynı yanıtta (400) yeniden çizilir;
        `ustune` gönderilen değeri taşır (yazılan kaybolmaz), ileti `yer` kartının başında çizilir."""
        with vt.islem() as b:
            baglam = bolum_baglami(b, anahtar)
            ozet = ayar_bolumleri.ozetler(b, bugun_tarihi())
        baglam.update(ustune)
        if hata:
            baglam.update(mesaj=hata, mesaj_hata=True, ileti_yeri=yer)
        return sayfa(
            istek,
            "ayar_bolum.html",
            k,
            durum_kodu=400 if hata else 200,
            bolum=ayar_bolumleri.bolum(anahtar),
            ayar_kumeleri=ayar_bolumleri.menu(ozet),
            ara_en_uzun=ayar_bolumleri.SORGU_EN_UZUN,
            **baglam,
        )

    def acil_sablonlarini_kaydet(istek: Request, k, form, ip: str):
        """Ayarlar › Acil şablonları (bolum=acil_sablonlari).

        Alanlar paralel listelerdir: s_ad, s_baslik, s_metin (satır sırasıyla). Adı boş satır
        silinmiş sayılır. eylem=varsayilan örnek şablonlara döndürür. Doğrulama hatasında
        sayfa gönderilen değerlerle yeniden çizilir (düzenlemeler kaybolmaz).
        """
        adres = "/acil?sekme=sablonlar#ileti"  # 0.16.0: şablonlar Acil › Şablonlar görünümündedir; ileti orada çizilir ve odaklanır
        if form.get("eylem") == "varsayilan":
            with vt.islem() as b:
                vt.ayar_yaz(b, "acil_sablonlar", None)
                vt.kayit_dus(b, k["ad"], "Acil şablonları örneklere döndürüldü", "", ip)
            return yonlendir(adres, "Acil şablonları örnek metinlere döndürüldü.")
        adlar, basliklar, metinler = form.getlist("s_ad"), form.getlist("s_baslik"), form.getlist("s_metin")
        kullanilan: set[str] = set()
        gonderilen = []
        yeni = []
        hata = ""
        for sira, ad in enumerate(adlar):
            ad = " ".join(str(ad).split())[:40]
            baslik = str(basliklar[sira] if sira < len(basliklar) else "").strip()[: acil.BASLIK_EN_UZUN]
            metin_ = str(metinler[sira] if sira < len(metinler) else "").strip()[: acil.METIN_EN_UZUN]
            if not ad:
                continue
            gonderilen.append({"ad": ad, "baslik": baslik, "metin": metin_})
            if hata:
                continue
            if not metin_:
                hata = f"'{ad}' şablonunun metni boş olamaz."
            elif guvenlik.tc_kimlik_var(baslik) or guvenlik.tc_kimlik_var(metin_):
                hata = guvenlik.TC_KIMLIK_ILETISI
                with vt.islem() as b:  # numaranın kendisi kayda yazılmaz
                    vt.kayit_dus(b, k["ad"], "Acil şablonu reddedildi", "T.C. kimlik numarasına benzeyen sayı", ip)
            else:
                yeni.append({"kod": acil.sablon_kodu(ad, kullanilan), "ad": ad, "baslik": baslik, "metin": metin_})
        if not hata and len(yeni) > acil.SABLON_EN_COK:
            hata = f"En çok {acil.SABLON_EN_COK} şablon tanımlanabilir."
        if hata:
            return y.acil_sablon_sayfasi(istek, k, sablon_formu=gonderilen[: acil.SABLON_EN_COK], hata=hata)
        with vt.islem() as b:
            vt.ayar_yaz(b, "acil_sablonlar", yeni)
            vt.kayit_dus(b, k["ad"], "Acil şablonları kaydedildi", f"{len(yeni)} şablon", ip)
        return yonlendir(adres, "Acil şablonları kaydedildi.")

    def sinav_kurallarini_kaydet(istek: Request, k, form, ip: str):
        """Ayarlar › Sınav ekranı (bolum=sinav): `sinav_kurallari` (≤ 1500 karakter, ≤ 8 satır); boş ya
        da eylem=varsayilan ise varsayılan metin. T.C. kimlik numarasına benzeyen sayı reddedilir.
        Hatada sayfa gönderilen metinle yeniden çizilir (yazılan kaybolmaz)."""
        adres = "/ayarlar/sinav?yer=sinav#ileti"
        metin_ = str(form.get("sinav_kurallari", "")).replace("\r\n", "\n").strip()
        if form.get("eylem") == "varsayilan":
            metin_ = ""
        gonderilen = metin_[: sinav.KURALLAR_EN_UZUN * 2]
        if len(metin_) > sinav.KURALLAR_EN_UZUN:
            return bolum_sayfasi(istek, k, "sinav", yer="sinav", sinav_kurallari=gonderilen,
                                     hata=f"Sınav kuralları en çok {sinav.KURALLAR_EN_UZUN} karakter olabilir.")  # fmt: skip
        if len(metin_.split("\n")) > sinav.KURALLAR_EN_COK_SATIR:
            return bolum_sayfasi(istek, k, "sinav", yer="sinav", sinav_kurallari=gonderilen,
                                     hata=f"Sınav kuralları en çok {sinav.KURALLAR_EN_COK_SATIR} satır olabilir "
                                   "(tahtada sayacın altına sığsın).")  # fmt: skip
        if guvenlik.tc_kimlik_var(metin_):
            with vt.islem() as b:
                vt.kayit_dus(b, k["ad"], "Sınav kuralları reddedildi", "T.C. kimlik numarasına benzeyen sayı", ip)
            return bolum_sayfasi(istek, k, "sinav", yer="sinav", sinav_kurallari=gonderilen,
                                     hata=guvenlik.TC_KIMLIK_ILETISI)
        with vt.islem() as b:
            vt.ayar_yaz(b, "sinav_kurallari", metin_ or None)
            vt.kayit_dus(b, k["ad"], "Sınav kuralları kaydedildi", f"{len(metin_)} karakter" if metin_ else "varsayılan metin", ip)
        onayli_tahtalari_uyandir()
        return yonlendir(adres, "Sınav kuralları kaydedildi." if metin_ else "Sınav kuralları varsayılan metne döndürüldü.")

    def yoklama_ayarlarini_kaydet(k, form, ip: str):
        """Ayarlar › Ders yoklaması (bolum=yoklama): yalnız `yoklama` anahtarı yazılır."""
        adres = "/ayarlar/yoklama?yer=yoklama#ileti"
        try:
            yeni = yoklama_mod.ayar_coz(form)
        except ValueError as hata:
            return yonlendir(adres, str(hata), hata=True)
        with vt.islem() as b:
            onceki = yoklama_mod.ayar_al(b)
            vt.ayar_yaz(b, "yoklama", yeni)
            ogrenci_yok = not b.execute("SELECT 1 FROM ogrenci WHERE aktif = 1 LIMIT 1").fetchone()
            vt.kayit_dus(
                b, k["ad"], "Yoklama ayarları kaydedildi",
                f"{'etkin' if yeni['etkin'] else 'kapalı'} · {yeni['maske']} · oturum {yeni['oturum_dk']} dk · "
                f"boşta {yeni['bosta_dk']} dk", ip,
            )  # fmt: skip
        if onceki["etkin"] != yeni["etkin"]:
            onayli_tahtalari_uyandir()  # yoklama_etkin tahtalara hemen insin
        mesaj = "Yoklama ayarları kaydedildi."
        if yeni["etkin"] and ogrenci_yok:
            mesaj += " Uyarı: öğrenci listesi henüz yüklenmedi; tahtada liste boş görünür."
        return yonlendir(adres, mesaj)

    def saklama_kaydet(istek: Request, k, form, ip: str):
        """Ayarlar › Veri saklama ve yedek (bolum=saklama): `ogretim_yili_bitis` (K3, `saklama.py`).

        Geçmiş tarih (bugünden önce) o tarihe kadarki kayıtları bir sonraki imha turunda siler; bu yüzden
        `sk_onay` ister ve silinecek kayıt sayılarını iletide gösterir. Boş tarih silmeyi durdurur.
        """
        adres = "/ayarlar/veri?yer=saklama#ileti"
        bugun = datetime.fromtimestamp(vt.simdi(), ISTANBUL).date()
        try:
            yeni = saklama.bitis_coz(form.get("oneri_kullan") or form.get("ogretim_yili_bitis"), bugun)
        except ValueError as hata:
            return yonlendir(adres, str(hata), hata=True)
        onaysiz = ""
        with vt.islem() as b:
            onceki = saklama.bitis_al(b)
            if yeni == onceki:
                return yonlendir(adres, "Öğretim yılı bitiş tarihi değişmedi.")
            if yeni and yeni < bugun and form.get("sk_onay") != "1":
                sinir = yeni.isoformat()
                yoklama_ = b.execute("SELECT COUNT(*) FROM yoklama WHERE tarih <= ?", (sinir,)).fetchone()[0]
                uyari_ = b.execute("SELECT COUNT(*) FROM bos_ders_uyari WHERE tarih <= ?", (sinir,)).fetchone()[0]
                sinav_ = sum(
                    1 for s in b.execute("SELECT * FROM sinav WHERE kisisel_silinme IS NULL")
                    if (g := sinav._sinav_gunu(s)) is not None and g.date() <= yeni
                )  # fmt: skip
                vt.kayit_dus(b, k["ad"], "Saklama tarihi reddedildi", f"geçmiş tarih {saklama.tarih_metni(yeni)}, onay yok", ip)
                onaysiz = (
                    f"{saklama.tarih_metni(yeni)} geçmiş bir tarih: {yoklama_} yoklama, {sinav_} sınavın öğrenci listesi ve "
                    f"{uyari_} boş ders uyarısı bir saat içinde kalıcı silinir. Eminseniz onay kutusunu işaretleyip yeniden kaydedin."
                )
            else:
                vt.ayar_yaz(b, saklama.AYAR_ANAHTARI, yeni.isoformat() if yeni else None)
                vt.kayit_dus(
                    b, k["ad"], "Öğretim yılı bitiş tarihi kaydedildi",
                    f"{saklama.tarih_metni(onceki) or 'yok'} → {saklama.tarih_metni(yeni) or 'yok (silme yapılmaz)'}", ip,
                )  # fmt: skip
        if onaysiz:
            # Hiçbir şey yazılmadı. Sayfa aynı yanıtta (400) yeniden çizilir: gönderilen tarih alanda kalır, yönetici
            # yalnız onay kutusunu işaretler (kutu kendiliğinden işaretlenmez).
            return bolum_sayfasi(istek, k, "veri", yer="saklama", hata=onaysiz, saklama_gonderilen=yeni.isoformat())
        if not yeni:
            return yonlendir(adres, "Öğretim yılı bitiş tarihi kaldırıldı; kayıtlar kendiliğinden silinmeyecek.")
        mesaj = f"Öğretim yılı bitiş tarihi kaydedildi: {saklama.tarih_metni(yeni)}."
        if onceki and onceki >= bugun and yeni > onceki:
            mesaj += (f" Dikkat: önceki tarih ({saklama.tarih_metni(onceki)}) henüz geçmemişti; o yılın kayıtları da "
                      "yeni tarihe kadar saklanacak.")  # fmt: skip
        return yonlendir(adres, mesaj)

    def temizlik_ayarini_kaydet(k, form, ip: str):
        """Ayarlar › Oturum temizliği (bolum=temizlik, K7): yalnız `oturum_temizligi` anahtarı yazılır."""
        adres = "/ayarlar/gunsonu?yer=temizlik#ileti"
        try:
            yeni = temizlik_mod.ayar_coz(form)
        except ValueError as hata:
            return yonlendir(adres, str(hata), hata=True)
        with vt.islem() as b:
            vt.ayar_yaz(b, temizlik_mod.AYAR_ANAHTARI, yeni)
            zaman = temizlik_mod.ZAMANLAR[yeni["zaman"]] + (f" ({yeni['saat']})" if yeni["zaman"] == "saat" else "")
            vt.kayit_dus(b, k["ad"], "Oturum temizliği ayarı kaydedildi",
                         f"{'açık' if yeni['etkin'] else 'kapalı'} · {zaman}", ip)  # fmt: skip
            ozet = temizlik_mod.zaman_ozeti(b, datetime.fromtimestamp(vt.simdi(), ISTANBUL).date())
        mesaj = "Oturum temizliği ayarı kaydedildi." if yeni["etkin"] else "Oturum temizliği kapatıldı."
        if ozet["uyari"]:
            mesaj += " Uyarı: " + ozet["uyari"]
        return yonlendir(adres, mesaj)

    def dugme_ayarini_kaydet(k, form, ip: str):
        """Ayarlar › Tahtadaki yüzer düğme (bolum=dugme, 0.9.0): yalnız `tahta_dugmesi` anahtarı yazılır.

        Ayar her `/ajan/bekle` yanıtında `ayar.dugme` olarak iner; tahtalar hemen uyandırılır."""
        yeni = dugme.ayar_coz(form)
        with vt.islem() as b:
            onceki = dugme.ayar_al(b)
            vt.ayar_yaz(b, dugme.AYAR_ANAHTARI, yeni)
            vt.kayit_dus(b, k["ad"], "Yüzer düğme ayarı kaydedildi", dugme.ozet(yeni), ip)
        if onceki != yeni:
            onayli_tahtalari_uyandir()
        if not yeni["acik"]:
            mesaj = "Yüzer düğme kapatıldı; tahtalarda görünmez."
        elif not any(yeni["islemler"].values()):
            mesaj = "Yüzer düğme ayarı kaydedildi. Hiçbir işlem seçilmediği için düğme tahtalarda görünmez."
        else:
            mesaj = "Yüzer düğme ayarı kaydedildi."
        return yonlendir("/ayarlar/yuzer?yer=dugme#ileti", mesaj)

    def acilis_kilidi_kaydet(k, form, ip: str):
        """Ayarlar › Açılışta kilit (bolum=acilis_kilidi, 0.9.0): yalnız `acilis_kilidi` anahtarı yazılır."""
        yeni = form.get("ak_acik") == "1"
        with vt.islem() as b:
            vt.ayar_yaz(b, acilis_kilidi.AYAR_ANAHTARI, yeni)
            kod_var = bool(vt.ayar_al(b, "kilit_kodu"))
            vt.kayit_dus(b, k["ad"], "Açılışta kilit ayarı kaydedildi", "açık" if yeni else "kapalı", ip)
        if not yeni:
            mesaj = "Açılışta kilit kapatıldı; tahtalar açılınca açık başlar."
        elif not kod_var:
            mesaj = "Açılışta kilit açık, ama kilit kodu belirlenmediği için uygulanmaz. Kilit kodunu belirleyin."
        else:
            mesaj = "Açılışta kilit açık: tahta açılınca ya da oturum açılınca, sunucuya ulaşabiliyorsa kilitli başlar."
        return yonlendir("/ayarlar/kilit?yer=acilis#ileti", mesaj, hata=yeni and not kod_var)

    def usb_anahtar_kaydet(k, form, ip: str):
        """Ayarlar › USB anahtar (bolum=usb_anahtar, 0.11.0): yalnız `usb_anahtar` anahtarı yazılır.

        Tahtaya yalnız `ayar.usb_anahtar.etkin` iner; değişiklikte tahtalar uyandırılır (izleme hemen başlasın/dursun).
        """
        with vt.islem() as b:
            onceki = usb_anahtar.ayar_al(b)
            yeni = usb_anahtar.ayar_coz(form, onceki)
            vt.ayar_yaz(b, usb_anahtar.AYAR_ANAHTARI, yeni)
            vt.kayit_dus(b, k["ad"], "USB anahtar ayarı kaydedildi", usb_anahtar.ayar_ozeti(yeni), ip)
            yoklama_kapali = not yoklama_mod.etkin(b)
            if not usb_anahtar.baskan_acik(yeni):
                # 0.21.0: başkan anahtarları kapatılınca onlarla açılmış yoklama ekranları anında düşer
                # (oturum_coz da ayarı denetler; bu silme ikinci kattır).
                b.execute("DELETE FROM yoklama_belirtec WHERE ogretmen_id IS NULL AND kullanici_id IS NULL AND anahtar_id IN "
                          "(SELECT id FROM usb_anahtar WHERE sahip_turu = 'sube')")  # fmt: skip
        if onceki != yeni:
            onayli_tahtalari_uyandir()
        mesaj = "USB anahtar ayarı kaydedildi." if yeni["etkin"] else "USB anahtar kapalı; tahtalar takılan belleklere bakmaz."
        if yeni["etkin"] and yoklama_kapali:
            mesaj += " Ders yoklaması kapalı; USB anahtar yalnız kilit açmada işe yarar."
        elif usb_anahtar.baskan_acik(yeni):
            mesaj += " Sınıf başkanı anahtarları açık (deneme)."
        return yonlendir("/ayarlar/usb?yer=usb_anahtar#ileti", mesaj)

    def guncelleme_ayarini_kaydet(k, form, ip: str):
        """Ayarlar › Güncelleme denetimi (bolum=guncelleme): yalnız `guncelleme_denetimi` anahtarı yazılır.

        Kaydetmek ağ çağrısı yapmaz; açıldıysa ilk denetim zamanlayıcının sonraki turunda arka planda yürür.
        """
        yeni = form.get("gd_acik") == "1"
        with vt.islem() as b:
            vt.ayar_yaz(b, guncelleme.AYAR_ANAHTARI, yeni)
            vt.kayit_dus(b, k["ad"], "Güncelleme denetimi ayarı kaydedildi", "açık" if yeni else "kapalı", ip)
        mesaj = (
            "Güncelleme denetimi açık: sunucu günde bir kez GitHub'daki son sürüme bakar."
            if yeni
            else "Güncelleme denetimi kapalı; GitHub'a istek gönderilmez."
        )
        return yonlendir("/ayarlar/guncelleme?yer=guncelleme#ileti", mesaj)

    @uygulama.post("/ayarlar/guncelleme/denetle")
    async def guncelleme_simdi_denetle(istek: Request):
        """Şimdi denetle: yalnız yönetici; ayar kapalıyken istek çıkmaz. Ağ çağrısı olay döngüsünü tutmaz."""
        k = kullanici(istek)
        if not k or k["rol"] != "yonetici":
            return yetkisiz_reddet(istek, k, "Ayarlar")
        adres = "/ayarlar/guncelleme?yer=guncelleme#ileti"
        durum = await asyncio.to_thread(guncelleme_denetleyici.simdi_denetle)
        if durum is None:
            return yonlendir(adres, "Güncelleme denetimi kapalı; GitHub'a istek gönderilmedi.", hata=True)
        with vt.islem() as b:
            sonuc = guncelleme.gorunum(b)["sonuc"]
            if not durum.get("taze"):
                vt.kayit_dus(b, k["ad"], "Güncelleme denetimi yapıldı", sonuc, istemci_ip(istek))
        if durum.get("taze"):
            return yonlendir(adres, f"Az önce denetlendi; yeniden istek gönderilmedi. {sonuc}")
        return yonlendir(adres, sonuc, hata=durum["sonuc"] != "tamam")

    def adresleri_kaydet(istek: Request, k, form, ip: str):
        """Ayarlar › Sunucu adresleri (bolum=adresler): `sunucu_adresleri` (satır başına bir adres, en çok 5).

        Kaydedilince onaylı bütün tahtalar uyandırılır (liste her yanıtta `ayar.sunucu_adresleri` ile iner).
        """
        gonderilen = str(form.get("sunucu_adresleri", ""))[:2000]
        try:
            liste = adresler.dogrula(gonderilen)
        except ValueError as hata:
            return bolum_sayfasi(istek, k, "sunucu", yer="adresler", sunucu_adresleri_metni=gonderilen, hata=str(hata))
        with vt.islem() as b:
            onceki = adresler.al(b)
            adresler.yaz(b, liste)
            vt.kayit_dus(b, k["ad"], "Sunucu adres listesi kaydedildi",
                         ", ".join(liste) if liste else "boş (bu bilgisayarın ilk ağ adresi)", ip)  # fmt: skip
        onayli_tahtalari_uyandir()
        mesaj = "Sunucu adresleri kaydedildi." if liste != onceki else "Sunucu adresleri değişmedi."
        return yonlendir("/ayarlar/sunucu?yer=adresler#ileti", mesaj)

    FORM_EKSIK = "Form eksik gönderildi; ayar değişmedi."

    def kapatma_coz(form) -> dict | None:
        """Otomatik kapatma alanlarını (`ok_*`) ayar değerine çevirir; saat biçimi bozuksa None.
        `bolum=kapatma` ile uyumluluk bölümü `genel` aynı ayrıştırmayı kullanır."""
        saatler = [s.strip().replace(".", ":") for s in str(form.get("ok_saatler", "")).split(",") if s.strip()]
        if any(not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", s) for s in saatler):
            return None
        try:
            hafta_sonu_dk = max(10, min(600, int(str(form.get("ok_hafta_sonu_dk", "60")) or "60")))
        except ValueError:
            hafta_sonu_dk = 60
        return {
            "etkin": form.get("ok_etkin") == "1" and bool(saatler),
            "saatler": sorted(set(saatler)),
            "hafta_sonu": form.get("ok_hafta_sonu") == "1",
            "hafta_sonu_dk": hafta_sonu_dk,
        }

    KAPATMA_SAAT_HATASI = "Kapatma saatleri SS:DD biçiminde, virgülle ayrılarak yazılmalı (ör. 19:15)."

    def okul_adini_kaydet(k, form, ip: str):
        """Ayarlar › Okul kimliği › Okulun adı (bolum=okul, 0.16.0): yalnız `okul_adi` anahtarı yazılır.

        Nöbetçi alan: `okul_adi` formda yoksa istek bu form değildir; hiçbir şey yazılmaz."""
        adres = "/ayarlar/okul?yer=ad#ileti"
        if form.get("okul_adi") is None:
            return yonlendir(adres, FORM_EKSIK, hata=True)
        yeni = str(form.get("okul_adi", "")).strip()[:120]
        with vt.islem() as b:
            if yeni == vt.ayar_al(b, "okul_adi", ""):
                return yonlendir(adres, "Okul adı değişmedi.")
            vt.ayar_yaz(b, "okul_adi", yeni)
            vt.kayit_dus(b, k["ad"], "Okul adı kaydedildi", "", ip)
        onayli_tahtalari_uyandir()
        return yonlendir(adres, "Okul adı kaydedildi.")

    def kapatmayi_kaydet(k, form, ip: str):
        """Ayarlar › Kapatma ve gün sonu › Otomatik kapatma (bolum=kapatma, 0.16.0): yalnız `otomatik_kapatma`.

        Nöbetçi alanlar `ok_saatler` ve `ok_hafta_sonu_dk`: işaretsiz onay kutusu hiç gönderilmediği için formun
        kimliği metin alanlarından anlaşılır; ikisi yoksa ayar sıfırlanmaz. Saat hatasında hiçbir şey yazılmaz."""
        adres = "/ayarlar/gunsonu?yer=kapatma#ileti"
        if form.get("ok_saatler") is None or form.get("ok_hafta_sonu_dk") is None:
            return yonlendir(adres, FORM_EKSIK, hata=True)
        yeni = kapatma_coz(form)
        if yeni is None:
            return yonlendir(adres, KAPATMA_SAAT_HATASI, hata=True)
        with vt.islem() as b:
            onceki = vt.ayar_al(b, "otomatik_kapatma")
            vt.ayar_yaz(b, "otomatik_kapatma", yeni)
            vt.kayit_dus(b, k["ad"], "Otomatik kapatma ayarı kaydedildi", kapatma_ozeti(yeni) or "kapalı", ip)
        if onceki != yeni:
            onayli_tahtalari_uyandir()
        mesaj = "Otomatik kapatma ayarı kaydedildi."
        if form.get("ok_etkin") == "1" and not yeni["saatler"]:
            mesaj += " Saat girilmediği için hafta içi kapatma kapalı."
        return yonlendir(adres, mesaj)

    def kilit_kodunu_kaydet(k, form, ip: str):
        """Ayarlar › Kilit ve güvenlik › Ortak kilit kodu (bolum=kilit_kodu, 0.16.0): yalnız `kilit_kodu`.

        Sıra: açık `kilit_kodu_sil=1` kodu kaldırır → dolu kod doğrulanıp yazılır → boş alan HİÇBİR ŞEY yazmaz
        (boş gönderim kodu silmez). Kod iletiye, kayda, adrese yazılmaz."""
        adres = "/ayarlar/kilit?yer=kod#ileti"
        if form.get("kilit_kodu") is None and form.get("kilit_kodu_sil") is None:
            return yonlendir(adres, FORM_EKSIK, hata=True)
        kod = str(form.get("kilit_kodu") or "").strip()
        with vt.islem() as b:
            if form.get("kilit_kodu_sil") == "1":
                if not vt.ayar_al(b, "kilit_kodu"):
                    return yonlendir(adres, "Kilit kodu zaten tanımlı değil.")
                vt.ayar_yaz(b, "kilit_kodu", None)
                vt.kayit_dus(b, k["ad"], "Kilit kodu kaldırıldı", "", ip)
                mesaj = "Kilit kodu kaldırıldı; kilitlenen tahta yalnız panelden açılır."
                if acilis_kilidi.ayar_al(b):
                    mesaj += " Açılışta kilit kod olmadan uygulanmaz."
            elif kod:
                if not (kod.isdigit() and 4 <= len(kod) <= 8):
                    return yonlendir(adres, "Kilit kodu 4-8 haneli rakamlardan oluşmalı.", hata=True)
                vt.ayar_yaz(b, "kilit_kodu", guvenlik.kilit_kodu_ozetle(kod))
                vt.kayit_dus(b, k["ad"], "Kilit kodu değiştirildi", "", ip)
                mesaj = "Kilit kodu kaydedildi."
            else:
                return yonlendir(adres, "Kilit kodu değişmedi.")
        onayli_tahtalari_uyandir()
        return yonlendir(adres, mesaj)

    @uygulama.post("/ayarlar")
    async def ayarlar_kaydet(istek: Request):
        k = kullanici(istek)
        if not k or k["rol"] != "yonetici":
            return yetkisiz_reddet(istek, k, "Ayarlar")
        form = await istek.form()
        # Ayarlar bölümlüdür: her bölüm yalnız kendi anahtarlarını yazar (gizli "bolum").
        bolum = str(form.get("bolum", "genel")) or "genel"
        if bolum == "acil_sablonlari":
            return acil_sablonlarini_kaydet(istek, k, form, istemci_ip(istek))
        if bolum == "sinav":
            return sinav_kurallarini_kaydet(istek, k, form, istemci_ip(istek))
        if bolum == "yoklama":
            return yoklama_ayarlarini_kaydet(k, form, istemci_ip(istek))
        if bolum == "adresler":
            return adresleri_kaydet(istek, k, form, istemci_ip(istek))
        if bolum == "saklama":
            return saklama_kaydet(istek, k, form, istemci_ip(istek))
        if bolum == "temizlik":
            return temizlik_ayarini_kaydet(k, form, istemci_ip(istek))
        if bolum == "dugme":
            return dugme_ayarini_kaydet(k, form, istemci_ip(istek))
        if bolum == "acilis_kilidi":
            return acilis_kilidi_kaydet(k, form, istemci_ip(istek))
        if bolum == "usb_anahtar":
            return usb_anahtar_kaydet(k, form, istemci_ip(istek))
        if bolum == "guncelleme":
            return guncelleme_ayarini_kaydet(k, form, istemci_ip(istek))
        # 0.16.0: eski "genel" üç ayrı bölüme ayrıldı; her biri yalnız kendi anahtarını yazar.
        if bolum == "okul":
            return okul_adini_kaydet(k, form, istemci_ip(istek))
        if bolum == "kapatma":
            return kapatmayi_kaydet(k, form, istemci_ip(istek))
        if bolum == "kilit_kodu":
            return kilit_kodunu_kaydet(k, form, istemci_ip(istek))
        if bolum != "genel":
            return yonlendir("/ayarlar", "Bilinmeyen ayar bölümü.", hata=True)
        # "genel" yalnız UYUMLULUK içindir (0.15.0 sayfası açık kalmış sekme, eski betik): okul adı, otomatik
        # kapatma ve kilit kodunu birlikte yazar; hiçbir şablon kullanmaz. Tek sertleştirme: `okul_adi` alanı hiç
        # yoksa istek eski form değildir (gizli `bolum` unutulmuş bir form buraya düşebilir) → yazmadan reddedilir;
        # yoksa okul adı boşalır, otomatik kapatma kapanırdı. İkinci sertleştirme: otomatik kapatma yalnız `ok_saatler`
        # metin alanı formda varken yazılır (0.15.0 formu onu HER ZAMAN gönderir; yalnız `okul_adi` taşıyan, gizli
        # `bolum`u düşmüş bir "Okulun adı" formu kapatma ayarını sıfırlamasın).
        if form.get("okul_adi") is None:
            return yonlendir("/ayarlar", FORM_EKSIK, hata=True)
        kapatma_ = None
        if form.get("ok_saatler") is not None:
            kapatma_ = kapatma_coz(form)
            if kapatma_ is None:
                return yonlendir("/ayarlar", KAPATMA_SAAT_HATASI, hata=True)
        with vt.islem() as b:
            vt.ayar_yaz(b, "okul_adi", str(form.get("okul_adi", "")).strip()[:120])
            # Sunucu adresi A6'dan beri ayrı bölümdür (bolum=adresler); genel bölüm ona dokunmaz.
            if kapatma_ is not None:
                vt.ayar_yaz(b, "otomatik_kapatma", kapatma_)
            kod = str(form.get("kilit_kodu", "")).strip()
            if form.get("kilit_kodu_sil") == "1":
                vt.ayar_yaz(b, "kilit_kodu", None)
                vt.kayit_dus(b, k["ad"], "Kilit kodu kaldırıldı", "", istemci_ip(istek))
            elif kod:
                if not (kod.isdigit() and 4 <= len(kod) <= 8):
                    return yonlendir("/ayarlar", "Kilit kodu 4-8 haneli rakamlardan oluşmalı.", hata=True)
                vt.ayar_yaz(b, "kilit_kodu", guvenlik.kilit_kodu_ozetle(kod))
                vt.kayit_dus(b, k["ad"], "Kilit kodu değiştirildi", "", istemci_ip(istek))
            vt.kayit_dus(b, k["ad"], "Ayarlar kaydedildi", "", istemci_ip(istek))
            idler = [s["id"] for s in b.execute("SELECT id FROM tahta WHERE durum = 'onayli'").fetchall()]
        for tahta_id in idler:  # yeni ayar tahtalara hemen insin
            uyandir(tahta_id)
        return yonlendir("/ayarlar", "Ayarlar kaydedildi.")

    # ---- okul kimliği: renkler ve logo ----------------------------------------
    @uygulama.post("/ayarlar/gorunum")
    async def gorunum_kaydet(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        if k["rol"] != "yonetici":
            return yonlendir("/", "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        form = await istek.form()
        if form.get("eylem") == "varsayilan":
            with vt.islem() as b:
                vt.ayar_yaz(b, "tema", None)
                vt.kayit_dus(b, k["ad"], "Görünüm varsayılana döndürüldü", "", istemci_ip(istek))
            onayli_tahtalari_uyandir()
            return yonlendir("/ayarlar/okul?yer=kimlik#ileti", "Renkler varsayılana döndürüldü.")
        ana = tema.renk_dogrula(form.get("ana_renk"))
        vurgu = None
        if form.get("vurgu_kullan") == "1":
            vurgu = tema.renk_dogrula(form.get("vurgu_renk"))
            if not vurgu:
                ana = None
        if not ana:
            return yonlendir("/ayarlar/okul?yer=kimlik#ileti", "Renk #rrggbb biçiminde olmalı.", hata=True)
        with vt.islem() as b:
            vt.ayar_yaz(b, "tema", {"ana": ana, "vurgu": vurgu})
            vt.kayit_dus(b, k["ad"], "Görünüm değiştirildi", f"{ana} {vurgu or '-'}", istemci_ip(istek))
        onayli_tahtalari_uyandir()
        return yonlendir("/ayarlar/okul?yer=kimlik#ileti", "Renkler kaydedildi.")

    @uygulama.post("/ayarlar/logo")
    async def logo_yukle(istek: Request):
        # Yetki, form ayrıştırılmadan önce denetlenir.
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        if k["rol"] != "yonetici":
            return yonlendir("/", "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        boyut_iletisi = "Logo dosyası en çok 256 KB olabilir."
        try:
            if int(istek.headers.get("content-length") or 0) > 600_000:
                return yonlendir("/ayarlar/okul?yer=logo#ileti", boyut_iletisi, hata=True)
        except ValueError:
            return yonlendir("/ayarlar/okul?yer=logo#ileti", "Logo dosyası okunamadı.", hata=True)
        try:
            form = await istek.form(max_files=1, max_fields=2)
        except Exception:
            return yonlendir("/ayarlar/okul?yer=logo#ileti", "Logo dosyası okunamadı.", hata=True)
        dosya = form.get("logo")
        if not isinstance(dosya, UploadFile):
            return yonlendir("/ayarlar/okul?yer=logo#ileti", "Logo dosyası seçilmedi.", hata=True)
        veri = await dosya.read(marka.LOGO_SINIRI + 1)
        await form.close()
        if not veri:
            return yonlendir("/ayarlar/okul?yer=logo#ileti", "Logo dosyası seçilmedi.", hata=True)
        if len(veri) > marka.LOGO_SINIRI:
            return yonlendir("/ayarlar/okul?yer=logo#ileti", boyut_iletisi, hata=True)
        try:
            tur, en, boy = marka.logo_dogrula(veri)
        except ValueError as hata:
            return yonlendir("/ayarlar/okul?yer=logo#ileti", str(hata), hata=True)
        marka.logo_yaz(veri)
        with vt.islem() as b:
            vt.ayar_yaz(
                b,
                "logo",
                {
                    "sha256": hashlib.sha256(veri).hexdigest(),
                    "tur": tur,
                    "en": en,
                    "boy": boy,
                    "boyut": len(veri),
                    "zaman": vt.simdi(),
                },
            )
            vt.kayit_dus(b, k["ad"], "Okul logosu yüklendi", f"{tur} {en}x{boy} {len(veri)} bayt", istemci_ip(istek))
        onayli_tahtalari_uyandir()
        return yonlendir("/ayarlar/okul?yer=logo#ileti", "Logo yüklendi.")

    @uygulama.post("/ayarlar/logo/sil")
    async def logo_kaldir(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        if k["rol"] != "yonetici":
            return yonlendir("/", "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        marka.logo_sil()
        with vt.islem() as b:
            vt.ayar_yaz(b, "logo", None)
            vt.kayit_dus(b, k["ad"], "Okul logosu kaldırıldı", "", istemci_ip(istek))
        onayli_tahtalari_uyandir()
        return yonlendir("/ayarlar/okul?yer=logo#ileti", "Logo kaldırıldı.")

    @uygulama.get("/marka/tema.css")
    async def tema_css(istek: Request):
        with vt.islem() as b:
            ana, vurgu = tema.tema_al(b)
        onbellek = UZUN_ONBELLEK if istek.query_params.get("v") == tema.surum(ana, vurgu) else "no-cache"
        return Response(
            tema.css_metni(ana, vurgu),
            media_type="text/css; charset=utf-8",
            headers={"Cache-Control": onbellek},
        )

    @uygulama.get("/marka/logo")
    async def logo_sun(istek: Request):
        # Oturum istemez: logo giriş sayfasında ve tahtada zaten herkese görünür.
        with vt.islem() as b:
            logo = marka.logo_oku(b)
        if not logo:
            return Response("Logo yok.", status_code=404, media_type="text/plain; charset=utf-8")
        veri, bilgi = logo
        onbellek = UZUN_ONBELLEK if istek.query_params.get("v") == bilgi["sha256"][:12] else "no-cache"
        return Response(
            veri,
            media_type=marka.TURLER[bilgi["tur"]],
            headers={
                "Cache-Control": onbellek,
                "ETag": f'"{bilgi["sha256"]}"',
                "Content-Security-Policy": "default-src 'none'; sandbox",
            },
        )

    # ---- ajan arayüzü --------------------------------------------------------
    def tahta_dogrula(istek: Request):
        kimlik = istek.headers.get("x-tahta-id", "")
        anahtar = istek.headers.get("x-tahta-anahtar", "")
        if not (kimlik.isdigit() and anahtar):
            return None
        with vt.islem() as b:
            return b.execute(
                "SELECT * FROM tahta WHERE id = ? AND anahtar_ozet = ? AND durum != 'iptal'",
                (int(kimlik), guvenlik.ozet(anahtar)),
            ).fetchone()

    def ajan_ayari(b, tahta) -> dict:
        """Onaylı tahtaya her yanıtta inen ayarlar. Logo baytları buraya girmez (yalnız özeti).

        `acil` bir DURUMDUR (komut değil): anahtar her zaman bulunur, yayın yoksa None.
        Logo özeti dosya-özeti önbelleğinden gelir; logo her çağrıda yeniden özetlenmez.
        """
        ana, vurgu = tema.tema_al(b)
        # Ad ve derslik uzun bekleme sırasında değişmiş olabilir: güncel satırdan okunur.
        guncel = b.execute("SELECT * FROM tahta WHERE id = ?", (tahta["id"],)).fetchone() or tahta
        sonuc = {
            "okul_adi": vt.ayar_al(b, "okul_adi", ""),
            "kilit_kodu": vt.ayar_al(b, "kilit_kodu"),
            "sunucu_saat": time.time(),
            "ajan_surumu": paket.ajan_paketi().surum,
            "tema": dict(tema.uret(ana, vurgu)["tahta"]),
            "logo_sha256": marka.logo_ozeti(b),
            "tahta": {"ad": guncel["ad"], "derslik": guncel["derslik"]},
            "acil": acil.ajan_gorunumu(b),
            # A4: durum tabanlı; pencere dışında None (ajan None görünce sınav ekranını kaldırır).
            "sinav": sinav.tahta_sinavi(b, tahta["id"], vt.simdi()),
            # A5: durum tabanlı, yalnız açık/kapalı (başka yoklama ayarı tahtaya gitmez).
            "yoklama_etkin": yoklama_mod.etkin(b),
            # 0.9.0 (G3): yüzer düğme, durum tabanlı. Alan yoksa (eski sunucu) ajan düğmeyi göstermez.
            "dugme": dugme.ajan_gorunumu(b),
            # 0.11.0: durum tabanlı, YALNIZ açık/kapalı (anahtar listesi, özet, PIN ayarı tahtaya inmez).
            "usb_anahtar": usb_anahtar.ajan_gorunumu(b),
        }
        if "gun_programi" in acil.yetenekler(guncel):
            sonuc["gun_programi"] = kilit_program.ajan_gorunumu(b, guncel, vt.simdi())
        # A6: durum tabanlı adres listesi; boşsa gönderilmez (ajan elindeki listeyi korur).
        liste = adresler.al(b)
        if liste:
            sonuc["sunucu_adresleri"] = liste
        return sonuc

    @uygulama.post("/ajan/kaydol")
    async def ajan_kaydol(istek: Request):
        if not hiz_siniri(kayit_denemeleri, istemci_ip(istek), 10, 600):
            return JSONResponse({"hata": "Çok fazla deneme; on dakika sonra yeniden deneyin."}, status_code=429)
        try:
            govde = await istek.json()
        except ValueError:
            return JSONResponse({"hata": "Geçersiz istek."}, status_code=400)
        with vt.islem() as b:
            pencere = vt.ayar_al(b, "kayit_penceresi") or {}
            import hmac

            gecerli = (
                pencere.get("bitis", 0) > vt.simdi()
                and pencere.get("kod")
                and hmac.compare_digest(str(govde.get("kod", "")), str(pencere["kod"]))
            )
            if not gecerli:
                vt.kayit_dus(b, "tahta:?", "Reddedilen tahta kaydı", "Kod geçersiz ya da tahta ekleme kapalı.", istemci_ip(istek))
                return JSONResponse(
                    {"hata": "Eşleştirme kodu geçersiz ya da panelde tahta ekleme açık değil."}, status_code=403
                )
            anahtar = guvenlik.belirtec()
            makine_adi = str(govde.get("makine_adi", "")).strip()[:60]
            # 0.21.0: varsayılan ad "Tahta <no>"dur; no, kurulumun sonunda tahtanın ekranına basılan kimliktir.
            # ETAP'ta bütün tahtaların makine adı aynıdır ("etap"); ad makine adından alınırsa tahtalar panelde
            # ayırt edilemez. Makine adı kendi sütununda kalır (Bakım › Bağlantı ve ajan). INSERT ve UPDATE aynı
            # işlemdedir: kimlik lastrowid'den gelir, başka bir kayıtla yarışmaz.
            imlec = b.execute(
                "INSERT INTO tahta (ad, anahtar_ozet, kayit_zamani, ip, mac, makine_adi, surum, platform) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "Yeni tahta",
                    guvenlik.ozet(anahtar),
                    vt.simdi(),
                    istemci_ip(istek),
                    str(govde.get("mac", ""))[:17],
                    makine_adi or "Yeni tahta",
                    str(govde.get("surum", ""))[:20],
                    str(govde.get("platform", ""))[:120],
                ),
            )
            tahta_id = imlec.lastrowid
            ad = tahta_liste.varsayilan_ad(tahta_id)
            b.execute("UPDATE tahta SET ad = ? WHERE id = ?", (ad, tahta_id))
            vt.kayit_dus(b, f"tahta:{ad}", "Tahta kaydoldu", "Onay bekliyor.", istemci_ip(istek))
            return {"tahta_id": tahta_id, "anahtar": anahtar}

    @uygulama.post("/ajan/bekle")
    async def ajan_bekle(istek: Request):
        tahta = tahta_dogrula(istek)
        if not tahta:
            return JSONResponse({"hata": "Tahta tanınmıyor."}, status_code=401)
        try:
            govde = await istek.json()
        except ValueError:
            return JSONResponse({"hata": "Geçersiz istek."}, status_code=400)
        durum = govde.get("durum") if isinstance(govde.get("durum"), dict) else None
        acilis_komutu = False
        with vt.islem() as b:
            if durum is not None:
                olaylar = durum.pop("olaylar", []) or []
                b.execute(
                    "UPDATE tahta SET son_gorulme = ?, ip = ?, surum = ?, durum_json = ?, mac = ?, makine_adi = ?, platform = ? "
                    "WHERE id = ?",
                    (
                        vt.simdi(),
                        istemci_ip(istek),
                        str(govde.get("surum", ""))[:20],
                        json.dumps(durum, ensure_ascii=False)[:20000],
                        str(durum.get("mac") or tahta["mac"])[:17],
                        str(durum.get("makine_adi") or tahta["makine_adi"])[:60],
                        str(durum.get("platform") or tahta["platform"])[:120],
                        tahta["id"],
                    ),
                )
                # Olaylar düz metindir (kodla açma, 0.9.0'dan beri tahtadan kilitleme/kapatma da); kullanıcı
                # adı taşımaz. Uzunluk sınırı: bozuk ya da kötü niyetli bir ajan kaydı şişirmesin.
                for olay in (olaylar if isinstance(olaylar, list) else [])[:20]:
                    vt.kayit_dus(b, f"tahta:{tahta['ad']}", "Tahta olayı", str(olay)[:300], istemci_ip(istek))
                if tahta["durum"] == "onayli":
                    # 0.9.0: yeni oturumda bir kez "açılışta kilit" (komut aşağıdaki bekleyen_komutlar ile hemen iner).
                    acilis_komutu = acilis_kilidi.degerlendir(b, tahta, program_is.durum_oku(tahta), durum,
                                                              datetime.fromtimestamp(vt.simdi(), ISTANBUL)) == "kilitlendi"  # fmt: skip
            else:
                b.execute("UPDATE tahta SET son_gorulme = ?, ip = ? WHERE id = ?", (vt.simdi(), istemci_ip(istek), tahta["id"]))
            # A6: arıza kuyruğu ve envanter yalnız onaylı tahtadan kabul edilir (onay bekleyende yanıt alanı da yok).
            ek_yanit: dict = {}
            ip = istemci_ip(istek)
            if tahta["durum"] == "onayli":
                if "arizalar" in govde:
                    ek_yanit["ariza_alindi"] = ariza_mod.tahtadan_al(b, tahta, govde.get("arizalar"), ip)
                if govde.get("envanter") is not None:
                    try:
                        envanter_mod.kaydet(b, tahta, govde.get("envanter"), (durum or {}).get("envanter_ozet", ""), ip)
                    except envanter_mod.EnvanterHatasi as hata:
                        vt.kayit_dus(b, f"tahta:{tahta['ad']}", "Envanter reddedildi", str(hata), ip)
            if durum is not None and tahta["durum"] == "onayli" and durum.get("acil_id") is not None:
                # Ajan ekrana aldığı acil yayının kimliğini bildirir: ilk görülme kaydı.
                yayin = acil.aktif(b)
                if yayin and durum.get("acil_id") == yayin["id"]:
                    acil.teslim_yaz(b, yayin["id"], tahta["id"], durum, "acil")
            for sonuc in (govde.get("sonuclar") or [])[:50]:
                komut = b.execute(
                    "SELECT * FROM komut WHERE id = ? AND tahta_id = ?", (sonuc.get("komut_id"), tahta["id"])
                ).fetchone()
                if not komut or komut["durum"] in ("tamam", "hata", "iptal"):
                    continue
                cikti = str(sonuc.get("cikti", ""))
                basarili = bool(sonuc.get("basarili"))
                if komut["tur"] == "tani" and basarili:
                    b.execute(
                        "UPDATE tahta SET tani_json = ?, tani_zamani = ? WHERE id = ?",
                        (cikti[:200000], vt.simdi(), tahta["id"]),
                    )
                    cikti = "Tanılama raporu alındı."
                if komut["tur"] == "envanter" and basarili:
                    try:
                        envanter_mod.kaydet(b, tahta, json.loads(cikti), (durum or {}).get("envanter_ozet", ""), ip)
                        cikti = "Envanter alındı."
                    except envanter_mod.EnvanterHatasi as hata:
                        basarili, cikti = False, str(hata)
                    except ValueError:
                        basarili, cikti = False, "Envanter okunamadı."
                if komut["tur"] == "temizlik":
                    # K7: ajanın raporu yalnız sayı ve adım sonucu içerir (ad, dosya, ev dizini yok).
                    cikti = cikti[:600]
                    vt.kayit_dus(b, f"tahta:{tahta['ad']}", "Oturum temizliği sonucu", cikti, ip)
                if komut["tur"] == "duyuru" and basarili:
                    acil_id = acil.yedek_teslim_acil_id(json.loads(komut["veri_json"] or "{}"))
                    if acil_id:  # eski ajana yedek yolla giden acil yayın gösterildi
                        acil.teslim_yaz(b, acil_id, tahta["id"], durum or json.loads(tahta["durum_json"] or "{}"), "yedek_duyuru")
                b.execute(
                    "UPDATE komut SET durum = ?, sonuc = ?, tamamlanma = ? WHERE id = ?",
                    ("tamam" if basarili else "hata", cikti[:4000], vt.simdi(), komut["id"]),
                )
            ayarlar_ = ajan_ayari(b, tahta)
            if tahta["durum"] == "onayli" and durum is not None and envanter_mod.YETENEK in acil.yetenekler({"durum_json": json.dumps(durum)}):
                guncel_env = b.execute("SELECT envanter_json, envanter_ozet FROM tahta WHERE id = ?", (tahta["id"],)).fetchone()
                ek_yanit["envanter_iste"] = envanter_mod.envanter_iste(guncel_env, durum.get("envanter_ozet"))
        if acilis_komutu:
            uyandir(tahta["id"])  # bu istek komut almıyorsa (komut_al=False) bekleyen uzun bekleme alsın
        if tahta["durum"] != "onayli":
            return {"durum": "bekliyor", "ayar": {"sunucu_saat": time.time()}}
        if govde.get("komut_al", True) is False:
            return {"durum": "onayli", "komutlar": [], "ayar": ayarlar_, **ek_yanit}

        def bekleyen_komutlar() -> list[dict]:
            with vt.islem() as b:
                b.execute(
                    "UPDATE komut SET durum = 'zaman_asimi' WHERE tahta_id = ? AND durum = 'bekliyor' AND bitis < ?",
                    (tahta["id"], vt.simdi()),
                )
                satirlar = b.execute(
                    "SELECT * FROM komut WHERE tahta_id = ? AND durum = 'bekliyor' ORDER BY id", (tahta["id"],)
                ).fetchall()
                guncel = b.execute("SELECT durum_json FROM tahta WHERE id = ?", (tahta["id"],)).fetchone()
                acil_yetenekli = acil.ACIL_YETENEK in acil.yetenekler(guncel)
                cikti = []
                for s in satirlar:
                    veri = json.loads(s["veri_json"] or "{}")
                    if s["tur"] == "duyuru" and acil_yetenekli and acil.yedek_teslim_acil_id(veri):
                        # Tahta bu arada güncellendi: acil yayını ayar.acil ile alır, yedek duyuru gerekmez.
                        b.execute(
                            "UPDATE komut SET durum = 'iptal', tamamlanma = ?, sonuc = ? WHERE id = ?",
                            (vt.simdi(), "Ajan acil yayını kendisi gösteriyor; yedek duyuru gerekmedi.", s["id"]),
                        )
                        continue
                    if s["tur"] == "duyuru":  # tahtanın saatine güvenilmez; kalan süre burada hesaplanır
                        veri["sure_sn"] = max(5, int(veri.pop("bitis_sunucu", vt.simdi() + 60)) - vt.simdi())
                    if s["tur"] == "kilitle" and veri.get("kaynak") == "program":
                        # Program kilidinin süresi de inerken hesaplanır; aralık geçtiyse komut düşer.
                        kalan = int(veri.pop("bitis_sunucu", 0)) - vt.simdi()
                        if kalan < 30:
                            b.execute(
                                "UPDATE komut SET durum = 'iptal', tamamlanma = ?, sonuc = ? WHERE id = ?",
                                (vt.simdi(), "Kilit aralığı geçti; gönderilmedi.", s["id"]),
                            )
                            continue
                        veri["sure_sn"] = kalan
                    cikti.append({"id": s["id"], "tur": s["tur"], "veri": veri})
                    b.execute("UPDATE komut SET durum = 'gonderildi' WHERE id = ?", (s["id"],))
                return cikti

        komutlar = bekleyen_komutlar()
        bekle = max(0, min(25, int(govde.get("bekle", 0) or 0)))
        if not komutlar and bekle:
            olay = asyncio.Event()
            bekleyenler[tahta["id"]] = (asyncio.get_running_loop(), olay)
            try:
                await asyncio.wait_for(olay.wait(), timeout=bekle)
            except TimeoutError:
                pass
            finally:
                guncel = bekleyenler.get(tahta["id"], (None, None))[1] is olay
                if guncel:
                    bekleyenler.pop(tahta["id"], None)
            # Yerini daha yeni bir uzun bekleme aldıysa bu bağlantı ölüdür (ajan yeniden başladı, tahta yeniden
            # açıldı): komutları o almaz, yoksa "gönderildi" sayılıp kaybolurlardı (0.9.0 Docker denemesi).
            komutlar = bekleyen_komutlar() if guncel else []
            with vt.islem() as b:
                ayarlar_ = ajan_ayari(b, tahta)
        return {"durum": "onayli", "komutlar": komutlar, "ayar": ayarlar_, **ek_yanit}

    @uygulama.get("/ajan/paket")
    async def ajan_paketi(istek: Request):
        if not tahta_dogrula(istek):
            return JSONResponse({"hata": "Tahta tanınmıyor."}, status_code=401)
        p = paket.ajan_paketi()
        return Response(p.icerik, media_type="application/vnd.debian.binary-package", headers={"X-Sha256": p.sha256})

    @uygulama.get("/ajan/logo")
    async def ajan_logo(istek: Request):
        if not tahta_dogrula(istek):
            return JSONResponse({"hata": "Tahta tanınmıyor."}, status_code=401)
        with vt.islem() as b:
            logo = marka.logo_oku(b)
        if not logo:
            return JSONResponse({"hata": "Logo yok."}, status_code=404)
        veri, bilgi = logo
        return Response(
            veri,
            media_type=marka.TURLER[bilgi["tur"]],
            headers={"X-Sha256": bilgi["sha256"], "Cache-Control": "no-store"},
        )

    # ---- otomatik kapatma ----------------------------------------------------
    hafta_sonu_son: dict[int, float] = {}

    def zamanlayici(simdi: datetime | None = None) -> int:
        """Otomatik kapatma kurallarını uygular; komut verilen tahta sayısını döndürür.

        Sunucu bunu 20 saniyede bir çağırır. Yalnız o anda çevrimiçi olan tahtalara
        komut verilir; saatinden sonra açılan tahta kapatılmaz. Komut uyarılıdır:
        kullanılan tahtada geri sayım çıkar ve kullanan kişi vazgeçebilir.
        """
        simdi = simdi or datetime.now(ISTANBUL)
        hedefler, neden = [], ""
        with vt.islem() as b:
            kural = vt.ayar_al(b, "otomatik_kapatma") or {}
            if not (kural.get("etkin") or kural.get("hafta_sonu")):
                return 0
            acik = [
                t
                for t in b.execute("SELECT * FROM tahta WHERE durum = 'onayli'").fetchall()
                if t["son_gorulme"] and vt.simdi() - t["son_gorulme"] < ayar.CEVRIMICI_ESIK_SN
            ]
            # Acil yayın sürerken otomatik kapatma hiç komut vermez (saat işareti yine yazılır
            # ki yayın bitince geç kapatma yapılmasın).
            acil_suruyor = acil.aktif(b) is not None
            if simdi.weekday() < 5:
                isaretler = vt.ayar_al(b, "kapatma_isaretleri") or []
                for saat in kural.get("saatler", []) if kural.get("etkin") else []:
                    an = simdi.replace(hour=int(saat[:2]), minute=int(saat[3:]), second=0, microsecond=0)
                    isaret = f"{simdi:%Y-%m-%d} {saat}"
                    if 0 <= (simdi - an).total_seconds() < 600 and isaret not in isaretler:
                        vt.ayar_yaz(b, "kapatma_isaretleri", (isaretler + [isaret])[-20:])
                        if acil_suruyor:
                            vt.kayit_dus(b, "sistem", "Otomatik kapatma acil yayın nedeniyle atlandı", f"saat {saat}")
                            return 0
                        hedefler, neden = acik, f"Otomatik kapatma (saat {saat})"
                        break
            elif kural.get("hafta_sonu") and not acil_suruyor:
                sinir = int(kural.get("hafta_sonu_dk", 60)) * 60
                for t in acik:
                    acik_sure = json.loads(t["durum_json"] or "{}").get("acik_sure", 0)
                    if acik_sure > sinir and time.time() - hafta_sonu_son.get(t["id"], 0) > sinir:
                        hafta_sonu_son[t["id"]] = time.time()
                        hedefler.append(t)
                neden = "Hafta sonu otomatik kapatma"
            if hedefler:
                # A4: sınav penceresindeki eşli tahtaya otomatik kapatma verilmez (eski ajana da).
                sinavdaki = sinav.pencere_tahtalari(b, int(simdi.timestamp()))
                atlanan = [t for t in hedefler if t["id"] in sinavdaki]
                if atlanan:
                    hedefler = [t for t in hedefler if t["id"] not in sinavdaki]
                    vt.kayit_dus(
                        b, "sistem", "Otomatik kapatma sınav nedeniyle atlandı",
                        f"{len(atlanan)} tahta: " + ", ".join(t["ad"] for t in atlanan),
                    )  # fmt: skip
            for t in hedefler:
                komut_ekle(b, t["id"], "kapat", {"uyari_sn": 60, "neden": neden}, "sistem")
            if hedefler:
                vt.kayit_dus(b, "sistem", neden, f"{len(hedefler)} tahta: " + ", ".join(t["ad"] for t in hedefler))
        for t in hedefler:
            uyandir(t["id"])
        return len(hedefler)

    # ---- duyuru planları ve acil denetimi ---------------------------------------
    def duyuru_zamanlayici(simdi: datetime | None = None) -> int:
        """Duyuru planlarını işletir (20 sn'de bir ve açılışta); yayımlanan gösterim sayısını döndürür."""
        simdi = simdi or datetime.now(ISTANBUL)
        with vt.islem() as b:
            sayi, idler = duyuru.planlari_isle(b, simdi)
        uyandir_hepsi(idler)
        return sayi

    def acil_denetim(simdi: datetime | None = None) -> int:
        """Süresi dolan acil yayını zamanında kapatır (kayıt düşsün); süren yayın varsa 1."""
        an = int(simdi.timestamp()) if simdi else None
        with vt.islem() as b:
            return 1 if acil.aktif(b, an) else 0

    # ---- ders programı (Aşama 3) ------------------------------------------------------------
    program_isleyici = program_is.ProgramZamanlayici()

    def program_zamanlayici(simdi: datetime | None = None) -> list[int]:
        """Program kilidi, açma yedeği, boş ders uyarısı, bakım (§5.5); uyandırılan tahtaları döndürür."""
        simdi = simdi or datetime.fromtimestamp(vt.simdi(), ISTANBUL)
        with vt.islem() as b:
            idler = program_isleyici.calistir(b, simdi)
        if program_isleyici.wal_budanacak:
            program_is.bos_ders_imha_sonrasi()
        uyandir_hepsi(idler)
        return idler

    # ---- oturum temizliği (K7, 0.8.0) ---------------------------------------------------------------
    def temizlik_zamanlayici(simdi: datetime | None = None) -> list[int]:
        """Zamanı gelen gün sonu temizliğini çevrimiçi, yetenekli tahtalara verir (sınavdakiler hariç)."""
        simdi = simdi or datetime.fromtimestamp(vt.simdi(), ISTANBUL)
        with vt.islem() as b:
            idler = temizlik_mod.zamanlayici(b, simdi, sinav.pencere_tahtalari)
        uyandir_hepsi(idler)
        return idler

    # ---- sınav (Aşama 4) ---------------------------------------------------------------------------
    sinav_isleyici = sinav.SinavZamanlayici()

    def sinav_zamanlayici(simdi: datetime | None = None) -> list[int]:
        """Saklama temizliği (öğretim yılı sonu, saklama.py) ve evre geçişinde eşli tahtaları uyandırma; uyandırılanlar."""
        an = int(simdi.timestamp()) if simdi else vt.simdi()
        with vt.islem() as b:
            idler, silindi = sinav_isleyici.calistir(b, an)
        if silindi:
            vt.wal_buda()
        uyandir_hepsi(idler)
        return idler

    # ---- ders yoklaması (Aşama 5) ------------------------------------------------------------------
    yoklama_isleyici = yoklama_mod.YoklamaZamanlayici()

    def yoklama_zamanlayici(simdi: datetime | None = None) -> bool:
        """Saatte en çok bir kez imha (öğretim yılı sonu, referanssız pasif öğrenci, eski oturumlar)."""
        an = int(simdi.timestamp()) if simdi else vt.simdi()
        with vt.islem() as b:
            silindi = yoklama_isleyici.calistir(b, an)
        if silindi:
            vt.wal_buda()
        return silindi

    # ---- otomatik yedek (Aşama 6) --------------------------------------------------------------
    acilis = vt.simdi()

    def yedek_zamanlayici(simdi: datetime | None = None) -> bool:
        """Parola var, program ≥ 5 dk açık ve bugünün günlük yedeği yoksa alır (başarısızsa 30 dk sonra yeniden).

        Kilit doluysa (yedek, göç ya da geri yükleme sürüyor) o tur atlanır. Yedek alındıysa True.
        """
        an = int(simdi.timestamp()) if simdi else vt.simdi()
        with vt.islem() as b:
            saklama = int(yedek.ayarlar(b).get("saklama") or yedek.SAKLAMA_VARSAYILAN)
            gerekli = yedek.otomatik_gerekli_mi(b, uygulama.state.acilis, an)
        # KVKK: onaylanmamış geri yükleme (1 gün) ve geri yükleme öncesi kopyalar (saklama günü) budanır.
        try:
            silinen = yedek.kalintilari_temizle(saklama, an)
        except OSError as hata:
            gunluk.warning("Geri yükleme kalıntıları silinemedi: %s", hata)
        else:
            if silinen:
                with vt.islem() as b:
                    vt.kayit_dus(b, "sistem", "Geri yükleme kalıntıları silindi", ", ".join(silinen)[:300], "")
        if not gerekli:
            return False
        try:
            return bool(yedek.yedek_al("gunluk", bekle=False, simdi=an)["yeni"])
        except yedek.YedekHatasi as hata:  # son_yedek ve işlem kaydı yedek_al içinde yazıldı
            gunluk.warning("Otomatik yedek alınamadı: %s", hata)
            return False

    def yayimla(b, **kw) -> tuple[int | None, list[int]]:
        """Sonraki aşamalar için tek yayın yolu (duyuru.duyuru_yayimla); uyandırmayı çağıran yapar."""
        return duyuru.duyuru_yayimla(b, **kw)

    # ---- panel bölümleri (ayrı modüller) ---------------------------------------
    y = SimpleNamespace(
        kullanici=kullanici,
        sayfa=sayfa,
        yonlendir=yonlendir,
        uyandir=uyandir,
        uyandir_hepsi=uyandir_hepsi,
        istemci_ip=istemci_ip,
        hiz_siniri=hiz_siniri,
        giris_denemeleri=giris_denemeleri,
        tahta_gorunumu=tahta_gorunumu,
        grup_uyelikleri=grup_uyelikleri,
        grup_uyeligi_yaz=grup_uyeligi_yaz,
        mevcut_binalar=mevcut_binalar,
        acil_ozeti=acil_ozeti,
        tahta_dogrula=tahta_dogrula,
        # A6
        parmak_izi=parmak_izi,
        yerel_mi=yerel_mi,
        kurulum_gerekli=kurulum_gerekli,
        yetkisiz_reddet=yetkisiz_reddet,
        altyapi_verisi=altyapi_verisi,
        tarih_yaz=tarih_yaz,
    )
    from . import (
        panel_acil,
        panel_aktar,
        panel_altyapi,
        panel_cizelge,
        panel_duyuru,
        panel_ogretmen_program,
        panel_sinav,
        panel_tahtalar,
    )

    panel_duyuru.kaydet(uygulama, y)
    panel_tahtalar.kaydet(uygulama, y)
    panel_acil.kaydet(uygulama, y)
    panel_program.kaydet(uygulama, y)
    panel_cizelge.kaydet(uygulama, y)
    panel_aktar.kaydet(uygulama, y)
    panel_sinav.kaydet(uygulama, y)
    panel_yoklama.kaydet(uygulama, y)
    panel_usb.kaydet(uygulama, y)
    panel_ogretmen_program.kaydet(uygulama, y)
    panel_altyapi.kaydet(uygulama, y)

    uygulama.state.zamanlayici = zamanlayici
    uygulama.state.program_zamanlayici = program_zamanlayici
    # 0.10.0: zil düzenleyici bugünkü saatleri değiştirince bellekteki boş ders sürelerini sıfırlar.
    uygulama.state.program_isleyici = program_isleyici
    uygulama.state.temizlik_zamanlayici = temizlik_zamanlayici
    # Sonraki aşamalar (A4 sınav penceresi) buraya kanca(b, tahta_id, an_epoch) -> bool ekler.
    uygulama.state.program_askida_kancalari = program_isleyici.askida_kancalari
    # A4 (§0-7): sınav penceresindeki eşli tahta program işinde askıdadır (program kilidi verilmez, boş ders
    # uyarısı üretilmez); pencereden önceki 10 dk'da yeni program kilidi verilmez (süreli kilit pencereye taşmasın).
    program_isleyici.askida_kancalari.append(lambda b, tahta_id, an: tahta_id in sinav.pencere_tahtalari(b, an))
    program_isleyici.kilit_engel_kancalari.append(
        lambda b, tahta_id, an: tahta_id in sinav.pencere_tahtalari(b, an, sinav.PROGRAM_ONCESI_SN)
    )
    uygulama.state.sinav_zamanlayici = sinav_zamanlayici
    uygulama.state.yoklama_zamanlayici = yoklama_zamanlayici
    uygulama.state.duyuru_zamanlayici = duyuru_zamanlayici
    uygulama.state.acil_denetim = acil_denetim
    uygulama.state.duyuru_yayimla = yayimla
    # sunucu.py yedeği tek arka plan işine verir; diğerlerini ayrı try içinde sırayla çağırır.
    uygulama.state.zamanlayicilar = [
        ("acil_denetim", acil_denetim),
        ("otomatik_kapatma", zamanlayici),
        ("duyuru_planlari", duyuru_zamanlayici),
        ("program", program_zamanlayici),
        ("oturum_temizligi", temizlik_zamanlayici),
        ("sinav_saklama", sinav_zamanlayici),
        ("yoklama_imha", yoklama_zamanlayici),
        ("yedek", yedek_zamanlayici),
        # 0.11.0: indirilmeden süresi dolan USB anahtarlar düşer (işlem kaydına "indirilmedi").
        ("usb_bekleyen", uygulama.state.usb_bekleyen_temizle),
        # 0.13.1: süresi dolan öğretmen programı önizlemesi (ham adlar) bellekte beklemez.
        ("ogretmen_program_onizleme", uygulama.state.ogretmen_program_onizleme.suresi_dolanlari_sil),
        # GitHub'dan yeni sürüm denetimi: günde en çok bir kez; ağ çağrısını kendi arka plan işinde yapar.
        ("guncelleme", guncelleme_denetleyici.zamanla),
    ]
    uygulama.state.guncelleme = guncelleme_denetleyici
    # Otomatik yedeğin "program ≥ 5 dk açık" ölçüsü (testler ilerletebilir).
    uygulama.state.acilis = acilis
    uygulama.state.yedek_zamanlayici = yedek_zamanlayici
    return uygulama
