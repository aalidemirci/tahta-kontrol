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
    ayar,
    dugme,
    duyuru,
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

# Üst menü (ortak sözlük §4). Her aşama yalnız kendi öğesini ekler. "rol" verilmişse
# yalnız o role görünür; "esler" sayfanın hangi yollarda seçili sayılacağını söyler.
MENU = [
    {"ad": "Pano", "yol": "/", "esler": ["/", "/tahta/"]},
    {"ad": "Duyurular", "yol": "/duyurular", "esler": ["/duyurular"]},
    {"ad": "Program", "yol": "/program", "esler": ["/program", "/ogretmen-programi"]},
    {"ad": "Sınavlar", "yol": "/sinavlar", "esler": ["/sinavlar", "/sinav"]},
    {"ad": "Yoklama", "yol": "/yoklama", "esler": ["/yoklama", "/ogretmenler", "/ogrenciler", "/usb-anahtarlar"]},
    {
        "ad": "Tahtalar",
        "alt": [
            {"ad": "Tahta ekle", "yol": "/ekle", "esler": ["/ekle"]},
            {"ad": "Gruplar", "yol": "/gruplar", "esler": ["/gruplar", "/tahtalar/ice-aktar"]},
            {"ad": "Envanter", "yol": "/envanter", "esler": ["/envanter"]},
            # "sayi": menü öğesinde rozetle gösterilen sayının anahtarı (sayfa() hesaplar).
            {"ad": "Arızalar", "yol": "/arizalar", "esler": ["/arizalar", "/ariza"], "sayi": "ariza"},
        ],
    },
    {"ad": "İşlem kaydı", "yol": "/kayit", "esler": ["/kayit"]},
    {
        "ad": "Yönetim",
        "rol": "yonetici",
        "alt": [
            {"ad": "Kullanıcılar", "yol": "/kullanicilar", "esler": ["/kullanicilar"]},
            {"ad": "Yedekler", "yol": "/yedekler", "esler": ["/yedekler"]},
            {"ad": "Ayarlar", "yol": "/ayarlar", "esler": ["/ayarlar"]},
        ],
    },
]
MENU_ACIL = {"ad": "Acil durum", "yol": "/acil", "esler": ["/acil"]}


def _secili(oge: dict, yol: str) -> bool:
    for es in oge.get("esler", []):
        if yol == es or (es.endswith("/") and es != "/" and yol.startswith(es)) or (es != "/" and yol.startswith(es + "/")):
            return True
    return False


def menu_gorunumu(k, yol: str, sayilar: dict | None = None) -> list[dict]:
    """Kullanıcının rolüne göre süzülmüş menü; her öğede `secili`, grupta `alt` ve `secili`.

    `sayi` (0 ise rozet yok): alt öğede `sayilar[oge["sayi"]]`, grupta alt öğelerin toplamı (A6 arızalar).
    """
    sayilar = sayilar or {}
    sonuc = []
    for oge in MENU:
        if oge.get("rol") and (not k or k["rol"] != oge["rol"]):
            continue
        if "alt" in oge:
            alt = [
                {"ad": a["ad"], "yol": a["yol"], "secili": _secili(a, yol), "sayi": int(sayilar.get(a.get("sayi"), 0) or 0)}
                for a in oge["alt"]
            ]
            sonuc.append(
                {"ad": oge["ad"], "alt": alt, "secili": any(a["secili"] for a in alt), "sayi": sum(a["sayi"] for a in alt)}
            )
        else:
            sonuc.append({"ad": oge["ad"], "yol": oge["yol"], "secili": _secili(oge, yol)})
    return sonuc


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


def uygulama_olustur(parmak_izi: str = "") -> FastAPI:
    vt.hazirla()
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
            menu_sayilari = {"ariza": ariza_mod.suren_toplam(b)} if k else {}
        baglam.update(
            menu=menu_gorunumu(k, istek.url.path, menu_sayilari) if k else [],
            menu_acil={**MENU_ACIL, "secili": _secili(MENU_ACIL, istek.url.path)},
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
    ) -> dict:
        """Pano kartı ve /api/durum için tahta özeti.

        acil_gorenler: süren acil yayını ekrana almış tahtaların kimlikleri (yoksa None).
        gruplar: tahta kimliği → grup kimlikleri (pano ilk verisi için; yoksa boş liste).
        bos_dersler: tahta kimliği → "3. ders (kapalı)" (program_is.bos_ders_metinleri).
        sinavlar: tahta kimliği → sınav penceresi (sinav.pencere_haritasi); yoksa `sinav` None.
        altyapi: altyapi_verisi(b) — A6 arıza sayısı ve "donanım değişti" rozeti için; yoksa 0/False.
        """
        durum = json.loads(satir["durum_json"] or "{}")
        cevrimici = bool(satir["son_gorulme"]) and (vt.simdi() - satir["son_gorulme"]) < ayar.CEVRIMICI_ESIK_SN
        ekranlar = durum.get("ekranlar") or []
        oturum = (durum.get("oturum") or {}).get("sinif", "yok")
        yetenekler = acil.yetenekler(satir)
        return {
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

    def altyapi_verisi(b) -> dict:
        """tahta_gorunumu(altyapi=…) için tek seferde: süren arıza sayıları ve donanım uyarıları."""
        return {"arizalar": ariza_mod.suren_sayilari(b), "donanim": envanter_mod.donanim_uyarilari(b)}

    def altyapi_uyarilari(b, k) -> list[dict]:
        """Pano uyarı şeritleri (§6.2), öncelik sırasıyla en çok üç: {"tur": tehlike|uyari, "metin", "yol", "yol_adi"}."""
        uyarilar: list[dict] = []
        yonetici = k["rol"] == "yonetici"
        yedek_ayari = yedek.ayarlar(b)
        if not yedek_ayari["parola_var"]:
            if yonetici:
                uyarilar.append({"tur": "tehlike", "metin": "Yedek parolası belirlenmedi; otomatik yedek alınmıyor.",
                                 "yol": "/yedekler", "yol_adi": "Yedekler"})  # fmt: skip
            else:
                uyarilar.append({"tur": "tehlike", "metin": "Yedek alınmıyor; yöneticiye bildirin.", "yol": "", "yol_adi": ""})
        else:
            son = yedek.son_yedek(b)
            simdi = vt.simdi()
            son_basarili = int(son.get("son_basarili") or 0)
            eski = (son_basarili and simdi - son_basarili > 2 * 86400) or (
                not son_basarili and simdi - int(yedek_ayari.get("parola_zamani") or simdi) > 2 * 86400
            )
            if son and not son.get("basarili", True):
                metin_ = (f"Son başarılı yedek: {tarih_yaz(son_basarili)}. " if son_basarili else "Henüz başarılı yedek yok. ")
                uyarilar.append({"tur": "uyari", "metin": metin_ + f"Son deneme başarısız: {son.get('hata') or 'bilinmeyen hata'}.",
                                 "yol": "/yedekler" if yonetici else "", "yol_adi": "Yedekler"})  # fmt: skip
            elif eski:
                metin_ = f"Son yedek: {tarih_yaz(son_basarili)}." if son_basarili else "Henüz yedek alınmadı."
                uyarilar.append({"tur": "uyari", "metin": metin_ + " Yedek 2 günden eski.",
                                 "yol": "/yedekler" if yonetici else "", "yol_adi": "Yedekler"})  # fmt: skip
            if son.get("basarili") and son.get("kopya_hata"):
                uyarilar.append({"tur": "uyari", "metin": f"Yedeğin ikinci kopyası yazılamadı: {son['kopya_hata']}",
                                 "yol": "/yedekler" if yonetici else "", "yol_adi": "Yedekler"})  # fmt: skip
        liste = adresler.al(b)
        ipler = guvenlik.yerel_ipler()
        if ipler and not adresler.bu_bilgisayar_listede_mi(liste, ipler):
            uyarilar.append({
                "tur": "uyari",
                "metin": f"Bu bilgisayarın adresi ({ipler[0]}) tahtalara bildirilen listede yok. "
                "Tahtalar eski adresi kullanıyor olabilir.",
                "yol": "/ayarlar?yer=adresler#adresler" if yonetici else "", "yol_adi": "Ayarlar",
            })  # fmt: skip
        return uyarilar[:3]

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

    # ---- pano ----------------------------------------------------------------
    @uygulama.get("/", response_class=HTMLResponse)
    async def pano(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/kurulum" if kurulum_gerekli() else "/giris")
        with vt.islem() as b:
            satirlar = b.execute(
                "SELECT * FROM tahta WHERE durum != 'iptal' ORDER BY derslik COLLATE NOCASE, ad COLLATE NOCASE"
            ).fetchall()
            kilit_kodu_var = bool(vt.ayar_al(b, "kilit_kodu"))
            kapatma = kapatma_ozeti(vt.ayar_al(b, "otomatik_kapatma") or {})
            gorenler = acil_gorenler(b)
            uyelik = grup_uyelikleri(b)
            kacirilan = b.execute(
                "SELECT COUNT(*) FROM duyuru WHERE durum = 'kacirildi' AND olusturma > ?", (vt.simdi() - 86400,)
            ).fetchone()[0]
            simdi_dt = datetime.fromtimestamp(vt.simdi(), ISTANBUL)
            program_ozeti = program_is.program_ozeti(b, simdi_dt)
            bos_dersler = program_is.bos_ders_metinleri(b, simdi_dt)
            sinavlar = sinav.pencere_haritasi(b, vt.simdi())
            altyapi = altyapi_verisi(b)
            uyarilar = altyapi_uyarilari(b, k)
        tahtalar = [tahta_gorunumu(s, gorenler, uyelik, bos_dersler, sinavlar, altyapi) for s in satirlar]
        return sayfa(
            istek,
            "pano.html",
            k,
            onayli=[t for t in tahtalar if t["durum"] == "onayli"],
            bekleyen=[t for t in tahtalar if t["durum"] == "bekliyor"],
            kilit_kodu_var=kilit_kodu_var,
            kapatma=kapatma,
            kacirilan_sayisi=kacirilan,
            program=program_ozeti,
            altyapi_uyarilari=uyarilar,
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

    @uygulama.get("/api/durum")
    async def api_durum(istek: Request):
        if not kullanici(istek):
            return JSONResponse({"hata": "Oturum gerekli."}, status_code=401)
        with vt.islem() as b:
            satirlar = b.execute("SELECT * FROM tahta WHERE durum = 'onayli'").fetchall()
            bekleyen = b.execute("SELECT COUNT(*) FROM tahta WHERE durum = 'bekliyor'").fetchone()[0]
            ozet = acil_ozeti(b)
            gorenler = acil_gorenler(b)
            simdi_dt = datetime.fromtimestamp(vt.simdi(), ISTANBUL)
            program_ozeti = program_is.program_ozeti(b, simdi_dt)
            bos_dersler = program_is.bos_ders_metinleri(b, simdi_dt)
            sinavlar = sinav.pencere_haritasi(b, vt.simdi())
            altyapi = altyapi_verisi(b)
        if ozet:
            ozet["teslim"] = len(gorenler or ())
            ozet["hedef"] = len(satirlar)
        return {
            "tahtalar": [tahta_gorunumu(s, gorenler, None, bos_dersler, sinavlar, altyapi) for s in satirlar],
            "bekleyen": bekleyen,
            "acil": ozet,
            "program": program_ozeti,
        }

    @uygulama.post("/islem")
    async def islem(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        form = await istek.form()
        tur = str(form.get("tur", ""))
        idler = [int(d) for d in form.getlist("tahta") if str(d).isdigit() and hedef.kimlik_mi(d)]
        if not idler:
            return yonlendir("/", "Önce en az bir tahta seçin.", hata=True)
        if tur not in KOMUT_ADI:
            return yonlendir("/", "Bilinmeyen işlem.", hata=True)
        donus = str(form.get("donus", "/")) if str(form.get("donus", "/")).startswith("/") else "/"
        if tur == "temizlik":  # K7: yalnız tahta sayfasındaki onaylı uçtan (yetenek denetimiyle) verilir
            return yonlendir(donus, "Oturum temizliği tahta sayfasından başlatılır.", hata=True)
        veri: dict = {}
        if tur == "duyuru":
            # Panodaki hemen gönderim: tek yayın yolundan, hedef seçili tahtalar.
            metin = str(form.get("metin", "")).strip()
            baslik = str(form.get("baslik", "")).strip()[:200]
            if not metin:
                return yonlendir(donus, "Duyuru metni boş olamaz.", hata=True)
            if guvenlik.tc_kimlik_var(metin) or guvenlik.tc_kimlik_var(baslik):
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
                    metin=metin[:4000],
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
        with vt.islem() as b:
            isaret = ",".join("?" * len(idler))
            tahtalar = b.execute(
                f"SELECT * FROM tahta WHERE durum = 'onayli' AND id IN ({isaret})", idler
            ).fetchall()
            if not tahtalar:
                return yonlendir("/", "Seçilen tahtalar bulunamadı.", hata=True)
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
            vt.kayit_dus(b, k["ad"], KOMUT_ADI[tur], f"{len(tahtalar)} tahta: {adlar}", istemci_ip(istek))
        for t in tahtalar:
            uyandir(t["id"])
        mesaj = f"{KOMUT_ADI[tur]}: {len(tahtalar)} tahtaya gönderildi."
        if tur == "uyandir":
            mesaj = f"Uzaktan açma paketi {len(tahtalar) - len(notlar)} tahtaya gönderildi. Tahtanın açılıp açılmadığını panodan izleyin."
        if notlar:
            mesaj += " " + "; ".join(notlar)
        return yonlendir(str(form.get("donus", "/")) if str(form.get("donus", "/")).startswith("/") else "/", mesaj)

    # ---- tahta ayrıntısı -----------------------------------------------------
    @uygulama.get("/tahta/{tahta_id}", response_class=HTMLResponse)
    async def tahta_sayfasi(istek: Request, tahta_id: int):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        with vt.islem() as b:
            satir = b.execute("SELECT * FROM tahta WHERE id = ? AND durum != 'iptal'", (tahta_id,)).fetchone()
            if not satir:
                return yonlendir("/", "Tahta bulunamadı.", hata=True)
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
        tani = json.loads(satir["tani_json"]) if satir["tani_json"] else None
        durum = json.loads(satir["durum_json"] or "{}")
        t_gorunum = tahta_gorunumu(satir, None, uyelik, None, sinavlar, altyapi)
        bagli = t_gorunum["bagli_adres"]
        return sayfa(
            istek,
            "tahta.html",
            k,
            t=t_gorunum,
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
        donus = f"/tahta/{tahta_id}?yer=temizlik#ileti"  # ileti temizlik bölümünde çizilir
        form = await istek.form()
        if form.get("eylem") != "temizle":
            return yonlendir(donus, "Bilinmeyen işlem.", hata=True)
        with vt.islem() as b:
            t = b.execute("SELECT * FROM tahta WHERE id = ? AND durum = 'onayli'", (tahta_id,)).fetchone()
            if not t:
                return yonlendir("/", "Tahta bulunamadı.", hata=True)
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
                return yonlendir(f"/tahta/{tahta_id}", str(hata), hata=True)
        with vt.islem() as b:
            satir = b.execute("SELECT * FROM tahta WHERE id = ?", (tahta_id,)).fetchone()
            if not satir:
                return yonlendir("/", "Tahta bulunamadı.", hata=True)
            if eylem == "sil":
                b.execute("UPDATE tahta SET durum = 'iptal', anahtar_ozet = '' WHERE id = ?", (tahta_id,))
                b.execute("DELETE FROM tahta_grubu_uye WHERE tahta_id = ?", (tahta_id,))
                b.execute("DELETE FROM tahta_ders WHERE tahta_id = ?", (tahta_id,))  # K34
                b.execute("DELETE FROM program_isaret WHERE tahta_id = ?", (tahta_id,))
                b.execute("DELETE FROM yoklama_belirtec WHERE tahta_id = ?", (tahta_id,))
                vt.kayit_dus(b, k["ad"], "Tahta kaldırıldı", satir["ad"], istemci_ip(istek))
                return yonlendir("/", f"{satir['ad']} kaldırıldı. Tahtadaki ajan artık sunucuya bağlanamaz.")
            if not ad:
                return yonlendir(f"/tahta/{tahta_id}", "Tahta adı boş olamaz.", hata=True)
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
        uyandir(tahta_id)
        return yonlendir(f"/tahta/{tahta_id}", "Kaydedildi.")

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
        with vt.islem() as b:
            satirlar = b.execute("SELECT * FROM kullanici ORDER BY ad").fetchall()
        return sayfa(istek, "kullanicilar.html", k, kullanicilar=satirlar)

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
        with vt.islem() as b:
            if eylem == "ekle":
                ad = str(form.get("ad", "")).strip().lower()
                parola = str(form.get("parola", ""))
                rol = str(form.get("rol", "idareci"))
                if len(ad) < 3 or len(parola) < 8 or rol not in ROLLER:
                    return yonlendir("/kullanicilar", "Kullanıcı adı en az 3, parola en az 8 karakter olmalı.", hata=True)
                if b.execute("SELECT 1 FROM kullanici WHERE ad = ?", (ad,)).fetchone():
                    return yonlendir("/kullanicilar", "Bu kullanıcı adı zaten var.", hata=True)
                # acil_yetki 0.8.0'dan beri okunmaz (K4: bütün kullanıcılar yetkili); eski sürüme dönülürse
                # aynı davranış sürsün diye 1 yazılır.
                b.execute(
                    "INSERT INTO kullanici (ad, gorunen_ad, parola_ozet, rol, olusturma, acil_yetki) VALUES (?, ?, ?, ?, ?, 1)",
                    (ad, str(form.get("gorunen_ad", "")).strip() or ad, guvenlik.parola_ozetle(parola), rol, vt.simdi()),
                )
                vt.kayit_dus(b, k["ad"], "Kullanıcı eklendi", f"{ad} ({ROLLER[rol]})", istemci_ip(istek))
                return yonlendir("/kullanicilar", "Kullanıcı eklendi.")
            hedef = b.execute("SELECT * FROM kullanici WHERE id = ?", (str(form.get("id", "")),)).fetchone()
            if not hedef:
                return yonlendir("/kullanicilar", "Kullanıcı bulunamadı.", hata=True)
            if eylem == "durum":
                if hedef["id"] == k["id"]:
                    return yonlendir("/kullanicilar", "Kendi hesabınızı kapatamazsınız.", hata=True)
                b.execute("UPDATE kullanici SET aktif = ? WHERE id = ?", (0 if hedef["aktif"] else 1, hedef["id"]))
                b.execute("DELETE FROM oturum WHERE kullanici_id = ?", (hedef["id"],))
                vt.kayit_dus(
                    b, k["ad"], "Kullanıcı kapatıldı" if hedef["aktif"] else "Kullanıcı açıldı", hedef["ad"], istemci_ip(istek)
                )
            elif eylem == "parola":
                parola = str(form.get("parola", ""))
                if len(parola) < 8:
                    return yonlendir("/kullanicilar", "Parola en az 8 karakter olmalı.", hata=True)
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
                return yonlendir("/kullanicilar", "Acil yayın yetkisi artık ayrı verilmez: bütün yönetici ve idareciler "
                                 "parola ve onayla başlatabilir.", hata=True)  # fmt: skip
            else:
                return yonlendir("/kullanicilar", "Bilinmeyen işlem.", hata=True)
        return yonlendir("/kullanicilar", "Kaydedildi.")

    @uygulama.get("/ayarlar", response_class=HTMLResponse)
    async def ayarlar(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        if k["rol"] != "yonetici":
            return yonlendir("/", "Bu sayfa için yönetici yetkisi gerekir.", hata=True)
        return ayarlar_sayfasi(istek, k)

    def ayarlar_sayfasi(
        istek: Request,
        k,
        sablon_formu: list | None = None,
        sablon_hata: str = "",
        sinav_formu: str | None = None,
        adres_formu: str | None = None,
    ) -> HTMLResponse:
        """Ayarlar sayfası. sablon_formu/sablon_hata: acil şablonu doğrulama hatasında gönderilen
        değerler aynı yanıtta (400) yeniden çizilir; düzenlemeler kaybolmaz. sinav_formu: sınav
        kuralları reddedildiğinde gönderilen metin (ileti sablon_hata'da). adres_formu: A6 adres listesi
        reddedildiğinde gönderilen metin (ileti sablon_hata'da, ileti_yeri "adresler")."""
        with vt.islem() as b:
            kilit_kodu_var = bool(vt.ayar_al(b, "kilit_kodu"))
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
            kapatma = vt.ayar_al(b, "otomatik_kapatma") or {}
            ana, vurgu = tema.tema_al(b)
            logo = marka.logo_oku(b)
            acil_sablonlar = acil.sablonlar(b)
            acil_sablon_ornek = not isinstance(vt.ayar_al(b, "acil_sablonlar"), list)
            sinav_kurallari = sinav.kurallar(b)
            sinav_kurallari_ozel = isinstance(vt.ayar_al(b, "sinav_kurallari"), str)
            yoklama_baglami = panel_yoklama.ayar_baglami(b)
            usb_baglami = panel_usb.ayar_baglami(b)
            saklama_durumu = saklama.durum(b, datetime.fromtimestamp(vt.simdi(), ISTANBUL).date())
            temizlik_ayari = temizlik_mod.ayar_al(b)
            temizlik_zamani = temizlik_mod.zaman_ozeti(b, datetime.fromtimestamp(vt.simdi(), ISTANBUL).date())
            temizlik_eski = sum(
                1 for t in b.execute("SELECT * FROM tahta WHERE durum = 'onayli'") if not temizlik_mod.yetenekli(t)
            )
            dugme_ayari = dugme.ayar_al(b)
            dugme_eski = sum(1 for t in b.execute("SELECT * FROM tahta WHERE durum = 'onayli'") if not dugme.yetenekli(t))
            dugme_yoklama_kapali = not yoklama_mod.etkin(b)
            acilis_kilidi_acik = acilis_kilidi.ayar_al(b)
            acilis_eski = sum(
                1 for t in b.execute("SELECT * FROM tahta WHERE durum = 'onayli'") if not acilis_kilidi.yetenekli(t)
            )
        uretilen = tema.uret(ana, vurgu)
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
        ek: dict = {}
        if sablon_formu is not None:
            acil_sablonlar = sablon_formu
            ek = {"mesaj": sablon_hata, "mesaj_hata": True, "ileti_yeri": "acil"}
        elif sinav_formu is not None:
            sinav_kurallari = sinav_formu
            ek = {"mesaj": sablon_hata, "mesaj_hata": True, "ileti_yeri": "sinav"}
        elif adres_formu is not None:
            ek = {"mesaj": sablon_hata, "mesaj_hata": True, "ileti_yeri": "adresler"}
        return sayfa(
            istek,
            "ayarlar.html",
            k,
            durum_kodu=400 if sablon_formu is not None or sinav_formu is not None or adres_formu is not None else 200,
            **ek,
            tema_ana=ana,
            tema_vurgu=vurgu,
            varsayilan_vurgu=tema.VARSAYILAN_VURGU,
            tema_notlar=uretilen["notlar"],
            tema_rapor=uretilen["rapor"],
            logo=logo_bilgi,
            kilit_kodu_var=kilit_kodu_var,
            # A6 adres listesi (bolum=adresler): metin alanı satır başına bir adres
            sunucu_adresleri=adres_listesi,
            sunucu_adresleri_metni=adres_formu if adres_formu is not None else "\n".join(adres_listesi),
            adres_en_cok=adresler.EN_COK,
            adres_durumu=adres_durumu,
            kapatma=kapatma,
            ipler=guvenlik.yerel_ipler(),
            https_port=ayar.HTTPS_PORT,
            parmak_izi=parmak_izi,
            veri_dizini=str(ayar.veri_dizini()),
            acil_sablonlar=acil_sablonlar,
            acil_sablon_ornek=acil_sablon_ornek,
            acil_sablon_en_cok=acil.SABLON_EN_COK,
            sinav_kurallari=sinav_kurallari,
            sinav_kurallari_ozel=sinav_kurallari_ozel,
            sinav_kurallari_varsayilan=sinav.SINAV_KURALLARI_VARSAYILAN,
            sinav_kurallari_en_uzun=sinav.KURALLAR_EN_UZUN,
            **yoklama_baglami,
            **usb_baglami,
            saklama_durumu=saklama_durumu,
            temizlik_ayari=temizlik_ayari,
            temizlik_zamani=temizlik_zamani,
            temizlik_zamanlari=temizlik_mod.ZAMANLAR,
            temizlik_eski=temizlik_eski,
            dugme_ayari=dugme_ayari,
            dugme_islemleri=dugme.ISLEMLER,
            dugme_eski=dugme_eski,
            dugme_yoklama_kapali=dugme_yoklama_kapali,
            dugme_kilit_kodu_yok=not kilit_kodu_var,
            acilis_kilidi_acik=acilis_kilidi_acik,
            acilis_eski=acilis_eski,
            acilis_en_yasli_sn=acilis_kilidi.EN_YASLI_OTURUM_SN,
        )

    def acil_sablonlarini_kaydet(istek: Request, k, form, ip: str):
        """Ayarlar › Acil şablonları (bolum=acil_sablonlari).

        Alanlar paralel listelerdir: s_ad, s_baslik, s_metin (satır sırasıyla). Adı boş satır
        silinmiş sayılır. eylem=varsayilan örnek şablonlara döndürür. Doğrulama hatasında
        sayfa gönderilen değerlerle yeniden çizilir (düzenlemeler kaybolmaz).
        """
        adres = "/ayarlar?yer=acil#ileti"  # ileti şablon bölümünün içinde çizilir ve odaklanır
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
            return ayarlar_sayfasi(istek, k, sablon_formu=gonderilen[: acil.SABLON_EN_COK], sablon_hata=hata)
        with vt.islem() as b:
            vt.ayar_yaz(b, "acil_sablonlar", yeni)
            vt.kayit_dus(b, k["ad"], "Acil şablonları kaydedildi", f"{len(yeni)} şablon", ip)
        return yonlendir(adres, "Acil şablonları kaydedildi.")

    def sinav_kurallarini_kaydet(istek: Request, k, form, ip: str):
        """Ayarlar › Sınav ekranı (bolum=sinav): `sinav_kurallari` (≤ 1500 karakter, ≤ 8 satır); boş ya
        da eylem=varsayilan ise varsayılan metin. T.C. kimlik numarasına benzeyen sayı reddedilir.
        Hatada sayfa gönderilen metinle yeniden çizilir (yazılan kaybolmaz)."""
        adres = "/ayarlar?yer=sinav#ileti"
        metin_ = str(form.get("sinav_kurallari", "")).replace("\r\n", "\n").strip()
        if form.get("eylem") == "varsayilan":
            metin_ = ""
        gonderilen = metin_[: sinav.KURALLAR_EN_UZUN * 2]
        if len(metin_) > sinav.KURALLAR_EN_UZUN:
            return ayarlar_sayfasi(istek, k, sinav_formu=gonderilen,
                                   sablon_hata=f"Sınav kuralları en çok {sinav.KURALLAR_EN_UZUN} karakter olabilir.")  # fmt: skip
        if len(metin_.split("\n")) > sinav.KURALLAR_EN_COK_SATIR:
            return ayarlar_sayfasi(istek, k, sinav_formu=gonderilen,
                                   sablon_hata=f"Sınav kuralları en çok {sinav.KURALLAR_EN_COK_SATIR} satır olabilir "
                                   "(tahtada sayacın altına sığsın).")  # fmt: skip
        if guvenlik.tc_kimlik_var(metin_):
            with vt.islem() as b:
                vt.kayit_dus(b, k["ad"], "Sınav kuralları reddedildi", "T.C. kimlik numarasına benzeyen sayı", ip)
            return ayarlar_sayfasi(istek, k, sinav_formu=gonderilen, sablon_hata=guvenlik.TC_KIMLIK_ILETISI)
        with vt.islem() as b:
            vt.ayar_yaz(b, "sinav_kurallari", metin_ or None)
            vt.kayit_dus(b, k["ad"], "Sınav kuralları kaydedildi", f"{len(metin_)} karakter" if metin_ else "varsayılan metin", ip)
        onayli_tahtalari_uyandir()
        return yonlendir(adres, "Sınav kuralları kaydedildi." if metin_ else "Sınav kuralları varsayılan metne döndürüldü.")

    def yoklama_ayarlarini_kaydet(k, form, ip: str):
        """Ayarlar › Ders yoklaması (bolum=yoklama): yalnız `yoklama` anahtarı yazılır."""
        adres = "/ayarlar?yer=yoklama#ileti"
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

    def saklama_kaydet(k, form, ip: str):
        """Ayarlar › Kişisel veri saklama (bolum=saklama): `ogretim_yili_bitis` (K3, `saklama.py`).

        Geçmiş tarih (bugünden önce) o tarihe kadarki kayıtları bir sonraki imha turunda siler; bu yüzden
        `sk_onay` ister ve silinecek kayıt sayılarını iletide gösterir. Boş tarih silmeyi durdurur.
        """
        adres = "/ayarlar?yer=saklama#ileti"
        bugun = datetime.fromtimestamp(vt.simdi(), ISTANBUL).date()
        try:
            yeni = saklama.bitis_coz(form.get("oneri_kullan") or form.get("ogretim_yili_bitis"), bugun)
        except ValueError as hata:
            return yonlendir(adres, str(hata), hata=True)
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
                return yonlendir(
                    adres,
                    f"{saklama.tarih_metni(yeni)} geçmiş bir tarih: {yoklama_} yoklama, {sinav_} sınavın öğrenci listesi ve "
                    f"{uyari_} boş ders uyarısı bir saat içinde kalıcı silinir. Eminseniz onay kutusunu işaretleyip yeniden kaydedin.",
                    hata=True,
                )
            vt.ayar_yaz(b, saklama.AYAR_ANAHTARI, yeni.isoformat() if yeni else None)
            vt.kayit_dus(
                b, k["ad"], "Öğretim yılı bitiş tarihi kaydedildi",
                f"{saklama.tarih_metni(onceki) or 'yok'} → {saklama.tarih_metni(yeni) or 'yok (silme yapılmaz)'}", ip,
            )  # fmt: skip
        if not yeni:
            return yonlendir(adres, "Öğretim yılı bitiş tarihi kaldırıldı; kayıtlar kendiliğinden silinmeyecek.")
        mesaj = f"Öğretim yılı bitiş tarihi kaydedildi: {saklama.tarih_metni(yeni)}."
        if onceki and onceki >= bugun and yeni > onceki:
            mesaj += (f" Dikkat: önceki tarih ({saklama.tarih_metni(onceki)}) henüz geçmemişti; o yılın kayıtları da "
                      "yeni tarihe kadar saklanacak.")  # fmt: skip
        return yonlendir(adres, mesaj)

    def temizlik_ayarini_kaydet(k, form, ip: str):
        """Ayarlar › Oturum temizliği (bolum=temizlik, K7): yalnız `oturum_temizligi` anahtarı yazılır."""
        adres = "/ayarlar?yer=temizlik#ileti"
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
        return yonlendir("/ayarlar?yer=dugme#ileti", mesaj)

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
        return yonlendir("/ayarlar?yer=acilis#ileti", mesaj, hata=yeni and not kod_var)

    def usb_anahtar_kaydet(k, form, ip: str):
        """Ayarlar › USB anahtar (bolum=usb_anahtar, 0.11.0): yalnız `usb_anahtar` anahtarı yazılır.

        Tahtaya yalnız `ayar.usb_anahtar.etkin` iner; değişiklikte tahtalar uyandırılır (izleme hemen başlasın/dursun).
        """
        yeni = usb_anahtar.ayar_coz(form)
        with vt.islem() as b:
            onceki = usb_anahtar.ayar_al(b)
            vt.ayar_yaz(b, usb_anahtar.AYAR_ANAHTARI, yeni)
            vt.kayit_dus(b, k["ad"], "USB anahtar ayarı kaydedildi", usb_anahtar.ayar_ozeti(yeni), ip)
            yoklama_kapali = not yoklama_mod.etkin(b)
        if onceki != yeni:
            onayli_tahtalari_uyandir()
        mesaj = "USB anahtar ayarı kaydedildi." if yeni["etkin"] else "USB anahtar kapalı; tahtalar takılan belleklere bakmaz."
        if yeni["etkin"] and yoklama_kapali:
            mesaj += " Ders yoklaması kapalı; USB anahtar yalnız kilit açmada işe yarar."
        return yonlendir("/ayarlar?yer=usb_anahtar#ileti", mesaj)

    def adresleri_kaydet(istek: Request, k, form, ip: str):
        """Ayarlar › Sunucu adresleri (bolum=adresler): `sunucu_adresleri` (satır başına bir adres, en çok 5).

        Kaydedilince onaylı bütün tahtalar uyandırılır (liste her yanıtta `ayar.sunucu_adresleri` ile iner).
        """
        gonderilen = str(form.get("sunucu_adresleri", ""))[:2000]
        try:
            liste = adresler.dogrula(gonderilen)
        except ValueError as hata:
            return ayarlar_sayfasi(istek, k, adres_formu=gonderilen, sablon_hata=str(hata))
        with vt.islem() as b:
            onceki = adresler.al(b)
            adresler.yaz(b, liste)
            vt.kayit_dus(b, k["ad"], "Sunucu adres listesi kaydedildi",
                         ", ".join(liste) if liste else "boş (bu bilgisayarın ilk ağ adresi)", ip)  # fmt: skip
        onayli_tahtalari_uyandir()
        mesaj = "Sunucu adresleri kaydedildi." if liste != onceki else "Sunucu adresleri değişmedi."
        return yonlendir("/ayarlar?yer=adresler#ileti", mesaj)

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
            return saklama_kaydet(k, form, istemci_ip(istek))
        if bolum == "temizlik":
            return temizlik_ayarini_kaydet(k, form, istemci_ip(istek))
        if bolum == "dugme":
            return dugme_ayarini_kaydet(k, form, istemci_ip(istek))
        if bolum == "acilis_kilidi":
            return acilis_kilidi_kaydet(k, form, istemci_ip(istek))
        if bolum == "usb_anahtar":
            return usb_anahtar_kaydet(k, form, istemci_ip(istek))
        if bolum != "genel":
            return yonlendir("/ayarlar", "Bilinmeyen ayar bölümü.", hata=True)
        with vt.islem() as b:
            vt.ayar_yaz(b, "okul_adi", str(form.get("okul_adi", "")).strip()[:120])
            # Sunucu adresi A6'dan beri ayrı bölümdür (bolum=adresler); genel bölüm ona dokunmaz.
            saatler = [s.strip().replace(".", ":") for s in str(form.get("ok_saatler", "")).split(",") if s.strip()]
            if any(not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", s) for s in saatler):
                return yonlendir("/ayarlar", "Kapatma saatleri SS:DD biçiminde, virgülle ayrılarak yazılmalı (ör. 19:15).", hata=True)
            try:
                hafta_sonu_dk = max(10, min(600, int(str(form.get("ok_hafta_sonu_dk", "60")) or "60")))
            except ValueError:
                hafta_sonu_dk = 60
            vt.ayar_yaz(
                b,
                "otomatik_kapatma",
                {
                    "etkin": form.get("ok_etkin") == "1" and bool(saatler),
                    "saatler": sorted(set(saatler)),
                    "hafta_sonu": form.get("ok_hafta_sonu") == "1",
                    "hafta_sonu_dk": hafta_sonu_dk,
                },
            )
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
            return yonlendir("/ayarlar?yer=kimlik#ileti", "Renkler varsayılana döndürüldü.")
        ana = tema.renk_dogrula(form.get("ana_renk"))
        vurgu = None
        if form.get("vurgu_kullan") == "1":
            vurgu = tema.renk_dogrula(form.get("vurgu_renk"))
            if not vurgu:
                ana = None
        if not ana:
            return yonlendir("/ayarlar?yer=kimlik#ileti", "Renk #rrggbb biçiminde olmalı.", hata=True)
        with vt.islem() as b:
            vt.ayar_yaz(b, "tema", {"ana": ana, "vurgu": vurgu})
            vt.kayit_dus(b, k["ad"], "Görünüm değiştirildi", f"{ana} {vurgu or '-'}", istemci_ip(istek))
        onayli_tahtalari_uyandir()
        return yonlendir("/ayarlar?yer=kimlik#ileti", "Renkler kaydedildi.")

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
                return yonlendir("/ayarlar?yer=kimlik#ileti", boyut_iletisi, hata=True)
        except ValueError:
            return yonlendir("/ayarlar?yer=kimlik#ileti", "Logo dosyası okunamadı.", hata=True)
        try:
            form = await istek.form(max_files=1, max_fields=2)
        except Exception:
            return yonlendir("/ayarlar?yer=kimlik#ileti", "Logo dosyası okunamadı.", hata=True)
        dosya = form.get("logo")
        if not isinstance(dosya, UploadFile):
            return yonlendir("/ayarlar?yer=kimlik#ileti", "Logo dosyası seçilmedi.", hata=True)
        veri = await dosya.read(marka.LOGO_SINIRI + 1)
        await form.close()
        if not veri:
            return yonlendir("/ayarlar?yer=kimlik#ileti", "Logo dosyası seçilmedi.", hata=True)
        if len(veri) > marka.LOGO_SINIRI:
            return yonlendir("/ayarlar?yer=kimlik#ileti", boyut_iletisi, hata=True)
        try:
            tur, en, boy = marka.logo_dogrula(veri)
        except ValueError as hata:
            return yonlendir("/ayarlar?yer=kimlik#ileti", str(hata), hata=True)
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
        return yonlendir("/ayarlar?yer=kimlik#ileti", "Logo yüklendi.")

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
        return yonlendir("/ayarlar?yer=kimlik#ileti", "Logo kaldırıldı.")

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
            ad = str(govde.get("makine_adi", "")).strip()[:60] or "Yeni tahta"
            imlec = b.execute(
                "INSERT INTO tahta (ad, anahtar_ozet, kayit_zamani, ip, mac, makine_adi, surum, platform) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ad,
                    guvenlik.ozet(anahtar),
                    vt.simdi(),
                    istemci_ip(istek),
                    str(govde.get("mac", ""))[:17],
                    ad,
                    str(govde.get("surum", ""))[:20],
                    str(govde.get("platform", ""))[:120],
                ),
            )
            vt.kayit_dus(b, f"tahta:{ad}", "Tahta kaydoldu", "Onay bekliyor.", istemci_ip(istek))
            return {"tahta_id": imlec.lastrowid, "anahtar": anahtar}

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
    ]
    # Otomatik yedeğin "program ≥ 5 dk açık" ölçüsü (testler ilerletebilir).
    uygulama.state.acilis = acilis
    uygulama.state.yedek_zamanlayici = yedek_zamanlayici
    return uygulama
