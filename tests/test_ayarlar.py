"""Ayarlar (0.16.0, panel arayüzü 2. aşama): giriş sayfası, 11 bölüm sayfası, yeni POST bölümleri (okul, kapatma,
kilit_kodu), kayıt güvenliği (bir bölüm başka bölümün ayarını ezmez), özetler, kurulum listesi, arama, eski adresler.

Uydurma veriyle; gerçek okul, kişi ya da ağ adresi yoktur.
"""

from __future__ import annotations

import json
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_marka import png
from yardimci import PAROLA, ayar_sayfasi, bekle, gir, ileti, kullanici_ekle, kur_ve_gir, sorgu, tahta_ekle

from tahta_sunucu import (
    acilis_kilidi,
    ayar_bolumleri,
    dugme,
    guncelleme,
    saklama,
    temizlik,
    usb_anahtar,
    vt,
    web,
)

KOK = Path(__file__).resolve().parent.parent / "tahta_sunucu"
SABLONLAR = KOK / "sablonlar"
BETIK = (KOK / "statik" / "panel.js").read_text(encoding="utf-8")
STIL = (KOK / "statik" / "stil.css").read_text(encoding="utf-8")
YEDEK_PAROLASI = "uzun-yedek-parolasi-1"
KOD = "4826"
BOLUMLER = ayar_bolumleri.ANAHTARLAR
SABLON_SAYFASI = "/acil?sekme=sablonlar"


@pytest.fixture(autouse=True)
def hizli_kdf(monkeypatch):
    from tahta_sunucu import yedek

    monkeypatch.setattr(yedek, "KDF_VARSAYILAN", {"n": 2**12, "r": 8, "p": 1})


@pytest.fixture()
def okul(panel, uygulama):
    from tahta_sunucu import ayar, guvenlik

    guvenlik.sertifika_hazirla(ayar.veri_dizini())
    kur_ve_gir(panel)
    return panel


def gonder(panel, **alanlar):
    return panel.post("/ayarlar", data=alanlar)


def ayarlar_tablosu() -> dict[str, str]:
    return {s["anahtar"]: s["deger"] for s in sorgu("SELECT anahtar, deger FROM ayar")}


def ayar(anahtar: str):
    with vt.islem() as b:
        return vt.ayar_al(b, anahtar)


def kayitlar() -> list[str]:
    return [s["islem"] for s in sorgu("SELECT islem FROM kayit ORDER BY id")]


def doldur(panel) -> None:
    """BÜTÜN ayarları varsayılan dışı "dolu" değere getirir (çapraz testin başlangıç durumu)."""
    adimlar = [
        gonder(panel, bolum="okul", okul_adi="Deneme Ortaokulu"),
        gonder(panel, bolum="kilit_kodu", kilit_kodu=KOD),
        gonder(panel, bolum="kapatma", ok_etkin="1", ok_saatler="12:40, 18:30", ok_hafta_sonu="1", ok_hafta_sonu_dk="90"),
        gonder(panel, bolum="acilis_kilidi"),  # kapalı (varsayılan açık)
        gonder(panel, bolum="temizlik", tm_etkin="1", tm_zaman="saat", tm_saat="17:45"),
        gonder(panel, bolum="dugme", dg_acik="1", dg_kilitle="1", dg_ariza="1"),
        gonder(panel, bolum="yoklama", yk_etkin="1", yk_maske="ad_soyadbas", yk_oturum_dk="10", yk_bosta_dk="2"),
        gonder(panel, bolum="usb_anahtar", ua_etkin="1", ua_kilit_acar="1", ua_pin_idare="1", ua_pin_ogretmen="1"),
        gonder(panel, bolum="sinav", sinav_kurallari="Sessiz olunuz."),
        gonder(panel, bolum="saklama", ogretim_yili_bitis="2027-06-25"),
        gonder(panel, bolum="adresler", sunucu_adresleri="https://10.0.0.5:8788\nhttps://tahta.okul.local:8788"),
        gonder(panel, bolum="guncelleme"),  # kapalı (varsayılan açık)
        gonder(panel, bolum="acil_sablonlari", s_ad="Sel", s_baslik="SEL", s_metin="Üst kata çıkınız."),
        panel.post("/ayarlar/gorunum", data={"eylem": "kaydet", "ana_renk": "#7a1f2b", "vurgu_kullan": "1", "vurgu_renk": "#d4a017"}),
        panel.post("/ayarlar/logo", files={"logo": ("logo.png", png(128, 128), "image/png")}),
        panel.post("/yedekler/parola", data={"hesap_parolasi": PAROLA, "parola": YEDEK_PAROLASI, "parola2": YEDEK_PAROLASI}),
        panel.post("/yedekler/ayar", data={"saklama": "9", "kopya_dizini": ""}),
    ]  # fmt: skip
    for sira, yanit in enumerate(adimlar):
        assert yanit.status_code == 303 and "t=hata" not in yanit.headers["location"], (sira, ileti(yanit))


# ---- kayıt güvenliği: çapraz test -------------------------------------------------------------------------
# (ad, uç, EN YALIN gövde — bütün onay kutuları işaretsiz, izinli ayar anahtarları, değişim bekleniyor mu)
FORMLAR = [
    ("okul", "/ayarlar", {"bolum": "okul", "okul_adi": ""}, {"okul_adi"}, True),
    ("kapatma", "/ayarlar", {"bolum": "kapatma", "ok_saatler": "", "ok_hafta_sonu_dk": "60"}, {"otomatik_kapatma"}, True),
    ("kilit_kodu_yeni", "/ayarlar", {"bolum": "kilit_kodu", "kilit_kodu": "1357"}, {"kilit_kodu"}, True),
    ("kilit_kodu_sil", "/ayarlar", {"bolum": "kilit_kodu", "kilit_kodu_sil": "1"}, {"kilit_kodu"}, True),
    ("kilit_kodu_bos", "/ayarlar", {"bolum": "kilit_kodu", "kilit_kodu": ""}, set(), False),
    ("acilis_kilidi", "/ayarlar", {"bolum": "acilis_kilidi", "ak_acik": "1"}, {acilis_kilidi.AYAR_ANAHTARI}, True),
    ("temizlik", "/ayarlar", {"bolum": "temizlik"}, {temizlik.AYAR_ANAHTARI}, True),
    ("dugme", "/ayarlar", {"bolum": "dugme"}, {dugme.AYAR_ANAHTARI}, True),
    ("yoklama", "/ayarlar", {"bolum": "yoklama", "yk_maske": "no_basharf", "yk_oturum_dk": "5", "yk_bosta_dk": "1"}, {"yoklama"}, True),
    ("usb_anahtar", "/ayarlar", {"bolum": "usb_anahtar"}, {usb_anahtar.AYAR_ANAHTARI}, True),
    ("sinav", "/ayarlar", {"bolum": "sinav", "sinav_kurallari": ""}, {"sinav_kurallari"}, True),
    ("saklama", "/ayarlar", {"bolum": "saklama", "ogretim_yili_bitis": ""}, {saklama.AYAR_ANAHTARI}, True),
    ("adresler", "/ayarlar", {"bolum": "adresler", "sunucu_adresleri": ""}, {"sunucu_adresleri", "sunucu_adresi"}, True),
    ("guncelleme", "/ayarlar", {"bolum": "guncelleme", "gd_acik": "1"}, {guncelleme.AYAR_ANAHTARI}, True),
    ("acil_sablonlari", "/ayarlar", {"bolum": "acil_sablonlari", "eylem": "varsayilan"}, {"acil_sablonlar"}, True),
    ("gorunum", "/ayarlar/gorunum", {"eylem": "varsayilan"}, {"tema"}, True),
    ("logo_sil", "/ayarlar/logo/sil", {}, {"logo"}, True),
    ("yedek_ayar", "/yedekler/ayar", {"saklama": "12", "kopya_dizini": "", "donus": "ayarlar"}, {"yedek"}, True),
    ("yedek_parola", "/yedekler/parola",
     {"hesap_parolasi": PAROLA, "parola": "baska-yedek-parolasi-2", "parola2": "baska-yedek-parolasi-2", "donus": "ayarlar"},
     {"yedek"}, True),
    # Uyumluluk bölümü: eski tek formun gövdesi (kilit kodu alanı boş) kodu silmez; başka bölüme dokunmaz.
    ("genel", "/ayarlar", {"bolum": "genel", "okul_adi": "Başka", "ok_saatler": "", "kilit_kodu": ""}, {"okul_adi", "otomatik_kapatma"}, True),
    ("bolumsuz", "/ayarlar", {"okul_adi": "Başka"}, {"okul_adi", "otomatik_kapatma"}, True),
]  # fmt: skip


@pytest.mark.parametrize(("ad", "uc", "govde", "izinli", "degisir"), FORMLAR, ids=[f[0] for f in FORMLAR])
def test_bolum_yalniz_kendi_anahtarini_yazar(okul, ad, uc, govde, izinli, degisir):
    doldur(okul)
    once = ayarlar_tablosu()
    yanit = okul.post(uc, data=govde)
    assert yanit.status_code == 303, ad
    sonra = ayarlar_tablosu()
    degisen = {a for a in set(once) | set(sonra) if once.get(a) != sonra.get(a)}
    assert degisen <= izinli, (ad, degisen - izinli)
    assert bool(degisen) is degisir, (ad, degisen, ileti(yanit))


def test_yalniz_okul_adi_gonderilince_kapatma_ve_kilit_kodu_degismez(okul):
    doldur(okul)
    once = ayarlar_tablosu()
    yanit = gonder(okul, bolum="okul", okul_adi="  Yeni Ad Ortaokulu  ")
    assert yanit.headers["location"].startswith("/ayarlar/okul?yer=ad&m=") and yanit.headers["location"].endswith("#ileti")
    assert ileti(yanit) == "Okul adı kaydedildi." and ayar("okul_adi") == "Yeni Ad Ortaokulu"
    sonra = ayarlar_tablosu()
    assert sonra["otomatik_kapatma"] == once["otomatik_kapatma"] and sonra["kilit_kodu"] == once["kilit_kodu"]
    assert ileti(gonder(okul, bolum="okul", okul_adi="Yeni Ad Ortaokulu")) == "Okul adı değişmedi."


def test_yalniz_kapatma_gonderilince_okul_adi_ve_kilit_kodu_degismez(okul):
    doldur(okul)
    once = ayarlar_tablosu()
    yanit = gonder(okul, bolum="kapatma", ok_etkin="1", ok_saatler="19.15, 13:30, 13:30", ok_hafta_sonu_dk="9999")
    assert yanit.headers["location"].startswith("/ayarlar/gunsonu?yer=kapatma&m=")
    assert ileti(yanit) == "Otomatik kapatma ayarı kaydedildi."
    assert ayar("otomatik_kapatma") == {"etkin": True, "saatler": ["13:30", "19:15"], "hafta_sonu": False, "hafta_sonu_dk": 600}
    sonra = ayarlar_tablosu()
    assert sonra["okul_adi"] == once["okul_adi"] and sonra["kilit_kodu"] == once["kilit_kodu"]


def test_yalniz_kilit_kodu_gonderilince_okul_adi_ve_kapatma_degismez(okul):
    doldur(okul)
    once = ayarlar_tablosu()
    yanit = gonder(okul, bolum="kilit_kodu", kilit_kodu="97531")
    assert yanit.headers["location"].startswith("/ayarlar/kilit?yer=kod&m=") and ileti(yanit) == "Kilit kodu kaydedildi."
    sonra = ayarlar_tablosu()
    assert sonra["kilit_kodu"] != once["kilit_kodu"]
    assert sonra["okul_adi"] == once["okul_adi"] and sonra["otomatik_kapatma"] == once["otomatik_kapatma"]


def test_bos_kilit_kodu_kodu_silmez(okul):
    gonder(okul, bolum="kilit_kodu", kilit_kodu=KOD)
    once = ayar("kilit_kodu")
    assert once
    for govde in ({"kilit_kodu": ""}, {"kilit_kodu": "   "}, {"kilit_kodu": "", "kilit_kodu_sil": "0"}, {"kilit_kodu_sil": ""}):
        yanit = gonder(okul, bolum="kilit_kodu", **govde)
        assert ileti(yanit) == "Kilit kodu değişmedi." and "t=hata" not in yanit.headers["location"], govde
        assert ayar("kilit_kodu") == once, govde
    assert kayitlar().count("Kilit kodu değiştirildi") == 1 and "Kilit kodu kaldırıldı" not in kayitlar()


def test_kilit_kodu_sil_yalniz_acik_istekle(okul):
    assert ileti(gonder(okul, bolum="kilit_kodu", kilit_kodu_sil="1")) == "Kilit kodu zaten tanımlı değil."
    gonder(okul, bolum="kilit_kodu", kilit_kodu=KOD)
    # Sil ile birlikte kod da gelirse sil kazanır (eski sıra). Açılışta kilit açıkken iletiye uyarı eklenir.
    yanit = gonder(okul, bolum="kilit_kodu", kilit_kodu_sil="1", kilit_kodu="1234")
    assert ileti(yanit) == "Kilit kodu kaldırıldı; kilitlenen tahta yalnız panelden açılır. Açılışta kilit kod olmadan uygulanmaz."
    assert ayar("kilit_kodu") is None and kayitlar()[-1] == "Kilit kodu kaldırıldı"
    gonder(okul, bolum="kilit_kodu", kilit_kodu=KOD)
    gonder(okul, bolum="acilis_kilidi")
    assert ileti(gonder(okul, bolum="kilit_kodu", kilit_kodu_sil="1")) == "Kilit kodu kaldırıldı; kilitlenen tahta yalnız panelden açılır."


@pytest.mark.parametrize("kod", ["123", "123456789", "12a4", "12 34", "١٢٣٤x"])
def test_kilit_kodu_gecersizse_yazilmaz(okul, kod):
    gonder(okul, bolum="kilit_kodu", kilit_kodu=KOD)
    once = ayar("kilit_kodu")
    yanit = gonder(okul, bolum="kilit_kodu", kilit_kodu=kod)
    assert ileti(yanit) == "Kilit kodu 4-8 haneli rakamlardan oluşmalı." and "t=hata" in yanit.headers["location"]
    assert ayar("kilit_kodu") == once


def test_kilit_kodu_iletide_kayitta_ve_sayfada_gorunmez(okul):
    yanit = gonder(okul, bolum="kilit_kodu", kilit_kodu="73914")
    assert "73914" not in yanit.headers["location"]
    ozet = ayar("kilit_kodu")
    assert ozet and "73914" not in json.dumps(ozet)
    for satir in sorgu("SELECT islem, ayrinti FROM kayit"):
        assert "73914" not in satir["islem"] + satir["ayrinti"]
    for yol in ("/ayarlar", "/ayarlar/kilit", yanit.headers["location"].split("#")[0], "/kayit"):
        sayfa = okul.get(yol).text
        assert "73914" not in sayfa, yol
        for parca in (ozet if isinstance(ozet, dict) else {"ozet": ozet}).values():
            if isinstance(parca, str) and len(parca) >= 8:
                assert parca not in sayfa, yol
    sayfa = ayar_sayfasi(okul, "kilit")
    alan = re.search(r'<input type="password" id="kilit_kodu"[^>]*>', sayfa).group(0)
    assert "value=" not in alan and 'autocomplete="new-password"' in alan and 'pattern="[0-9]{4,8}"' in alan


def test_kapatma_nobetci_alan_yoksa_yazilmaz(okul):
    doldur(okul)
    once = ayarlar_tablosu()
    for govde in ({}, {"ok_etkin": "1"}, {"ok_saatler": "10:00"}, {"ok_hafta_sonu_dk": "30"}):
        yanit = gonder(okul, bolum="kapatma", **govde)
        assert ileti(yanit) == "Form eksik gönderildi; ayar değişmedi." and "t=hata" in yanit.headers["location"], govde
        assert yanit.headers["location"].startswith("/ayarlar/gunsonu?yer=kapatma")
    assert ayarlar_tablosu() == once
    assert "Otomatik kapatma ayarı kaydedildi" not in kayitlar()[-4:]


def test_okul_nobetci_alan_yoksa_yazilmaz(okul):
    doldur(okul)
    once = ayarlar_tablosu()
    yanit = gonder(okul, bolum="okul")
    assert ileti(yanit) == "Form eksik gönderildi; ayar değişmedi." and "t=hata" in yanit.headers["location"]
    yanit = gonder(okul, bolum="kilit_kodu")
    assert ileti(yanit) == "Form eksik gönderildi; ayar değişmedi." and "t=hata" in yanit.headers["location"]
    assert ayarlar_tablosu() == once


def test_kapatma_saat_hatasinda_hicbir_sey_yazilmaz(okul):
    doldur(okul)
    once = ayarlar_tablosu()
    yanit = gonder(okul, bolum="kapatma", ok_etkin="1", ok_saatler="25:00", ok_hafta_sonu_dk="60")
    assert ileti(yanit) == "Kapatma saatleri SS:DD biçiminde, virgülle ayrılarak yazılmalı (ör. 19:15)."
    assert "t=hata" in yanit.headers["location"] and ayarlar_tablosu() == once


def test_kapatma_saatsiz_etkin_kapali_sayilir_ve_soyler(okul):
    yanit = gonder(okul, bolum="kapatma", ok_etkin="1", ok_saatler=" ", ok_hafta_sonu_dk="x")
    assert ileti(yanit) == "Otomatik kapatma ayarı kaydedildi. Saat girilmediği için hafta içi kapatma kapalı."
    assert ayar("otomatik_kapatma") == {"etkin": False, "saatler": [], "hafta_sonu": False, "hafta_sonu_dk": 60}
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Otomatik kapatma ayarı kaydedildi'")[-1]["ayrinti"] == "kapalı"


def test_genel_eski_govdeyle_ucunu_birlikte_yazar(okul):
    """0.15.0 formunun tam gövdesi (açık kalmış sekme): okul adı, kapatma ve kilit kodu birlikte yazılır."""
    yanit = gonder(okul, bolum="genel", okul_adi="Eski Form Lisesi", kilit_kodu="2468", ok_etkin="1", ok_saatler="19:15",
                   ok_hafta_sonu="1", ok_hafta_sonu_dk="45")  # fmt: skip
    assert yanit.headers["location"].startswith("/ayarlar?m=") and ileti(yanit) == "Ayarlar kaydedildi."
    assert ayar("okul_adi") == "Eski Form Lisesi" and ayar("kilit_kodu")
    assert ayar("otomatik_kapatma") == {"etkin": True, "saatler": ["19:15"], "hafta_sonu": True, "hafta_sonu_dk": 45}
    assert kayitlar()[-2:] == ["Kilit kodu değiştirildi", "Ayarlar kaydedildi"]
    sayfa = okul.get(yanit.headers["location"]).text  # ileti giriş sayfasının başında
    assert "Ayarlar kaydedildi." in sayfa and 'id="ayar-kapsam"' in sayfa
    gonder(okul, bolum="genel", okul_adi="Eski Form Lisesi", ok_saatler="", kilit_kodu_sil="1")
    assert ayar("kilit_kodu") is None


def test_genel_okul_adi_yoksa_yazmaz(okul):
    doldur(okul)
    once = ayarlar_tablosu()
    for govde in ({"bolum": "genel"}, {}, {"bolum": "genel", "ok_saatler": "10:00"}, {"bolum": ""}, {"ak_acik": "1"}):
        yanit = okul.post("/ayarlar", data=govde)
        assert yanit.headers["location"].startswith("/ayarlar?m=") and "t=hata" in yanit.headers["location"], govde
        assert ileti(yanit) == "Form eksik gönderildi; ayar değişmedi."
    assert ayarlar_tablosu() == once


def test_bolumsuz_istek_genel_sayilir(okul):
    yanit = okul.post("/ayarlar", data={"okul_adi": "Bölümsüz"})
    assert ileti(yanit) == "Ayarlar kaydedildi." and ayar("okul_adi") == "Bölümsüz"
    assert ileti(gonder(okul, bolum="yok_boyle", okul_adi="x")) == "Bilinmeyen ayar bölümü."
    assert ayar("okul_adi") == "Bölümsüz"


# ---- şablon yapısı: bir ayarın bütün alanları tek formda ---------------------------------------------------
class FormOkuyucu(HTMLParser):
    """Sayfadaki formlar: [{"action", "id", "ozellik": {…}, "alanlar": {ad: [öznitelikler]}, "dugmeler": [öznitelikler]}]."""

    def __init__(self):
        super().__init__()
        self.formlar: list[dict] = []
        self.acik: dict | None = None
        self.details: list[bool] = []
        self.kapali_details_metni: list[str] = []

    def handle_starttag(self, etiket, ozellikler):
        o = dict(ozellikler)
        if etiket == "details":
            self.details.append("open" in o)
        if etiket == "form":
            self.acik = {"action": o.get("action", ""), "id": o.get("id", ""), "ozellik": o, "alanlar": {}, "dugmeler": []}
            self.formlar.append(self.acik)
        elif self.acik is not None and etiket in ("input", "select", "textarea", "button"):
            if etiket == "button":
                self.acik["dugmeler"].append(o)
            if o.get("name"):
                self.acik["alanlar"].setdefault(o["name"], []).append({**o, "_etiket": etiket})

    def handle_endtag(self, etiket):
        if etiket == "form":
            self.acik = None
        if etiket == "details" and self.details:
            self.details.pop()

    def handle_data(self, veri):
        if self.details and not all(self.details):
            self.kapali_details_metni.append(veri)


def formlar(html: str) -> list[dict]:
    okuyucu = FormOkuyucu()
    okuyucu.feed(html)
    return [f for f in okuyucu.formlar if f["action"] not in ("/cikis", "") and f["ozellik"].get("method") != "dialog"]


def bolum_degeri(form: dict) -> str:
    gizli = form["alanlar"].get("bolum")
    return gizli[0].get("value", "") if gizli else ""


def duzlestir(metin: str) -> str:
    return " ".join(metin.split())


def kapali_details_metni(html: str) -> str:
    okuyucu = FormOkuyucu()
    okuyucu.feed(html)
    return duzlestir(" ".join(okuyucu.kapali_details_metni))


# Şartname §1.1: her bölüm sayfasındaki formlar — (uç, bolum, alan adları). Koşullu alanlar `hazir_durum`da görünür.
BEKLENEN_FORMLAR = {
    "okul": [
        ("/ayarlar", "okul", {"bolum", "okul_adi"}),
        ("/ayarlar/gorunum", "", {"ana_renk", "vurgu_kullan", "vurgu_renk", "eylem"}),
        ("/ayarlar/logo", "", {"logo"}),
        ("/ayarlar/logo/sil", "", set()),
    ],
    "kilit": [
        ("/ayarlar", "kilit_kodu", {"bolum", "kilit_kodu"}),
        ("/ayarlar", "acilis_kilidi", {"bolum", "ak_acik"}),
        ("/ayarlar", "kilit_kodu", {"bolum"}),  # "Kodu kaldır…": kilit_kodu_sil=1 onay penceresinden gelir
    ],
    "gunsonu": [
        ("/ayarlar", "kapatma", {"bolum", "ok_etkin", "ok_saatler", "ok_hafta_sonu", "ok_hafta_sonu_dk"}),
        ("/ayarlar", "temizlik", {"bolum", "tm_etkin", "tm_zaman", "tm_saat"}),
    ],
    "yuzer": [("/ayarlar", "dugme", {"bolum", "dg_acik", *(f"dg_{k}" for k in dugme.ISLEMLER)})],
    "yoklama": [("/ayarlar", "yoklama", {"bolum", "yk_etkin", "yk_maske", "yk_oturum_dk", "yk_bosta_dk"})],
    "usb": [("/ayarlar", "usb_anahtar", {"bolum", "ua_etkin", "ua_kilit_acar", "ua_pin_idare", "ua_pin_ogretmen"})],
    "sinav": [("/ayarlar", "sinav", {"bolum", "sinav_kurallari", "eylem"})],
    "veri": [
        ("/ayarlar", "saklama", {"bolum", "ogretim_yili_bitis", "oneri_kullan", "sk_onay"}),
        ("/yedekler/parola", "", {"donus", "hesap_parolasi", "parola", "parola2"}),
        ("/yedekler/ayar", "", {"donus", "saklama", "kopya_dizini"}),
    ],
    "sunucu": [("/ayarlar", "adresler", {"bolum", "sunucu_adresleri"})],
    # "Şimdi denetle" ayrı formdur ve son denetim satırının yanında (ayar formundan önce) durur.
    "guncelleme": [("/ayarlar/guncelleme/denetle", "", set()), ("/ayarlar", "guncelleme", {"bolum", "gd_acik"})],
}


def hazir_durum(panel) -> None:
    """Koşullu alanların HEPSİ görünsün: kilit kodu var, logo var, özel sınav metni, özel acil şablonu, Okul Zili önerisi,
    ikinci kullanıcı, güncelleme açık."""
    doldur(panel)
    gonder(panel, bolum="guncelleme", gd_acik="1")
    gonder(panel, bolum="saklama", ogretim_yili_bitis="")
    with vt.islem() as b:
        vt.ayar_yaz(b, "zil_takvimi", {"ogretim": {"bas": "2026-09-07", "bit": "2027-06-25"}})
    kullanici_ekle(panel, "idareci1")


@pytest.mark.parametrize("bolum", list(BEKLENEN_FORMLAR))
def test_her_bolum_tek_formda(okul, bolum):
    """§3.5: bir ayar anahtarının bütün alanları TEK formdadır (işaretsiz kutu gönderilmez; bölünürse ezilir)."""
    hazir_durum(okul)
    bulunan = [(f["action"], bolum_degeri(f), set(f["alanlar"])) for f in formlar(ayar_sayfasi(okul, bolum))]
    arama = ("/ayarlar", "", {"ara"})  # yan menüdeki GET araması
    assert [f for f in bulunan if f != arama] == BEKLENEN_FORMLAR[bolum]
    degerler = [b for _, b, _ in bulunan if b]
    for deger in set(degerler):
        assert degerler.count(deger) == (2 if deger == "kilit_kodu" else 1), deger


def test_usb_dort_kutu_tek_formda(okul):
    doldur(okul)
    form = next(f for f in formlar(ayar_sayfasi(okul, "usb")) if bolum_degeri(f) == "usb_anahtar")
    for ad in ("ua_etkin", "ua_kilit_acar", "ua_pin_idare", "ua_pin_ogretmen"):
        (alan,) = form["alanlar"][ad]
        assert alan["type"] == "checkbox" and alan["value"] == "1" and "checked" in alan and "disabled" not in alan, ad
    # Yalnız biri işaretli gönderilirse öbür üçü bilerek kapanır: dördü aynı formda olduğu için sessiz ezilme olmaz.
    gonder(okul, bolum="usb_anahtar", ua_etkin="1")
    assert ayar(usb_anahtar.AYAR_ANAHTARI) == {"etkin": True, "kilit_acar": False, "pin_idare": False, "pin_ogretmen": False}


def test_sayfalarda_devre_disi_ya_da_gizli_ayar_alani_yok(okul):
    """disabled alan gönderilmez → ezilir; alan `hidden`/`disabled` ile gizlenmez (yalnız CSS sınıfıyla soluklaşır)."""
    hazir_durum(okul)
    for bolum in BEKLENEN_FORMLAR:
        for form in formlar(ayar_sayfasi(okul, bolum)):
            for ad, alanlar in form["alanlar"].items():
                for alan in alanlar:
                    assert "disabled" not in alan, (bolum, ad)
                    if alan["_etiket"] != "button" and alan.get("type") != "hidden":
                        assert "hidden" not in alan, (bolum, ad)


def test_hicbir_alan_adi_kaybolmadi(okul):
    """0.15.0 `ayarlar.html`, `yedekler.html` (parola + ayar) ve `kullanicilar.html` formlarının dökümü: her
    (uç, alan) çifti yeni sayfalarda durur. `genel`'in alanları yeni üç bölümde aranır."""
    eski = {
        ("/ayarlar", a) for a in (
            "okul_adi", "kilit_kodu", "ok_etkin", "ok_saatler", "ok_hafta_sonu", "ok_hafta_sonu_dk",
            "sunucu_adresleri", "s_ad", "s_baslik", "s_metin", "eylem", "sinav_kurallari",
            "yk_etkin", "yk_maske", "yk_oturum_dk", "yk_bosta_dk",
            "ua_etkin", "ua_kilit_acar", "ua_pin_idare", "ua_pin_ogretmen",
            "ogretim_yili_bitis", "oneri_kullan", "sk_onay", "tm_etkin", "tm_zaman", "tm_saat", "ak_acik", "gd_acik",
            "dg_acik", "dg_kilitle", "dg_kapat", "dg_yeniden_baslat", "dg_ariza", "dg_yoklama", "bolum",
        )
    } | {
        ("/ayarlar/gorunum", "ana_renk"), ("/ayarlar/gorunum", "vurgu_kullan"), ("/ayarlar/gorunum", "vurgu_renk"),
        ("/ayarlar/gorunum", "eylem"), ("/ayarlar/logo", "logo"),
        ("/yedekler/parola", "hesap_parolasi"), ("/yedekler/parola", "parola"), ("/yedekler/parola", "parola2"),
        ("/yedekler/ayar", "saklama"), ("/yedekler/ayar", "kopya_dizini"),
        ("/kullanicilar", "id"), ("/kullanicilar", "parola"), ("/kullanicilar", "eylem"), ("/kullanicilar", "gorunen_ad"),
        ("/kullanicilar", "ad"), ("/kullanicilar", "rol"),
    }  # fmt: skip
    eski_uclar = {"/ayarlar", "/ayarlar/gorunum", "/ayarlar/logo", "/ayarlar/logo/sil", "/ayarlar/guncelleme/denetle",
                  "/yedekler/parola", "/yedekler/ayar", "/kullanicilar"}  # fmt: skip
    eski_bolumler = {"adresler", "acil_sablonlari", "sinav", "yoklama", "usb_anahtar", "saklama", "temizlik",
                     "acilis_kilidi", "guncelleme", "dugme"}  # fmt: skip
    hazir_durum(okul)
    yeni, uclar, bolumler = set(), set(), set()
    for html in [ayar_sayfasi(okul, b) for b in BOLUMLER] + [okul.get(SABLON_SAYFASI).text]:
        for form in formlar(html):
            uclar.add(form["action"])
            bolumler.add(bolum_degeri(form))
            yeni |= {(form["action"], ad) for ad in form["alanlar"]}
    assert eski - yeni == set()
    assert eski_uclar - uclar == set()
    assert eski_bolumler - bolumler == set() and {"okul", "kapatma", "kilit_kodu"} <= bolumler and "genel" not in bolumler
    # kilit_kodu_sil artık form alanı değil, onay penceresinin gönderdiği değerdir (düğme + ONAY sözlüğü).
    assert 'data-onay="kilit_kodu_sil"' in ayar_sayfasi(okul, "kilit")
    assert re.search(r'kilit_kodu_sil:\s*\{\s*ad: "kilit_kodu_sil", deger: "1"', BETIK)
    # Fazladan gelen tek alan `donus` (yedek formlarının dönüş adresi).
    fazla = {ad for uc, ad in yeni - eski if uc != "/ayarlar" or ad != "ara"}
    assert fazla == {"donus"}, fazla


# §4'te kalın/uyarı sayılan cümleler: ilgili sayfada geçer ve kapalı <details> içinde DEĞİLDİR.
ACIK_UYARILAR = {
    "usb": ["Anahtar bir dosyadır ve kopyalanabilir.", "PIN, kopyalanan dosyayı tek başına işe yaramaz kılar.",
            "Kaybolan anahtarı hemen iptal edin.", "Kapalıyken tahtalar takılan belleklere hiç bakmaz."],
    "veri": ["Yedek parolası unutulursa yedekler hiçbir yolla açılamaz.", "Kâğıda yazıp okulun kasasında saklayın.",
             "Parola değişince eski yedekler eski parolayla açılır.", "Tarih boşsa hiçbir kayıt kendiliğinden silinmez.",
             "Geçmiş bir tarih giriyorsam o tarihe kadarki kayıtların bir saat içinde kalıcı olarak silineceğini biliyorum"],
    "sunucu": ["yeni adresi taşımadan ÖNCE ekleyin ve bütün tahtalar listeyi alana kadar bekleyin.",
               "Sertifika kaybolursa bütün tahtalara ajan yeniden kurulur."],
    "yoklama": ["Tam soyad ve T.C. kimlik numarası hiçbir biçimde tahtaya gitmez.",
                "kâğıt yoklamanın yanında tutulan yardımcı kayıttır; onun yerine geçmez."],
    "gunsonu": ["Yalnız öğretmen ve öğrenci ortak hesaplarında yapılır.", "zorla kapatılmaz",
                "Kilitli ya da oturum açılmamış tahta uyarısız kapanır."],
    "sinav": ["Öğrenci adı ya da kişisel bilgi yazmayın."],
    "guncelleme": ["Kendiliğinden indirme ya da kurma yapılmaz."],
    "kilit": ["Sınıfın önünde ekrandan girildiği için öğrencilerce görülebilir; düzenli aralıklarla değiştirin.",
              "Kod kaldırılırsa kilitli tahta yalnız panelden açılır; öğretmenler tahtayı kendileri açamaz."],
    "kullanicilar": ["Acil durum ve tatbikat yayınını bütün yönetici ve idareciler başlatabilir; yayın parolanızı ve açık onayı ister."],
}  # fmt: skip
# Katlı açıklamada (ya da açıkta) durabilen ama SAYFADA bulunması gereken cümleler.
SAYFADAKI_CUMLELER = {
    "guncelleme": ["okul adı, tahta sayısı, kurulu sürüm ya da başka bir bilgi gönderilmez", "Tahtalar internete çıkmaz."],
    "gunsonu": ["Yönetici (etapadmin) ve kişisel hesaplarda hiçbir zaman yapılmaz.", "Resmî tatiller ayrıca tanınmaz",
                "Acil yayın sürerken ve sınavdaki tahtada yapılmaz.", "yer imlerine ve kayıtlı parolalara dokunulmaz"],
    "kilit": ["Kod tahtalara özet olarak gider ve sunucu kapalıyken de çalışır.", "Yönetici (etapadmin) oturumunda."],
    "usb": ["Bellek biçimlendirilmez ve anahtar olarak işgal edilmez", "Takılınca hiçbir ekran kendiliğinden açılmaz",
            "Sunucuya ulaşılamayan tahtada USB anahtar çalışmaz"],
    "yuzer": ["Tahta olayı", "kullanıcı adı gönderilmez", "10 saniyelik geri sayımla onay ister"],
    "sunucu": ["sudo tahta-ajan sunucu https://YENİ-ADRES:", "Okul DNS'inde bir ad tanımlıysa onu da ekleyin"],
    "veri": ["Öğrenci listesi bu silmeye girmez", "Şifreli yedekler bu verinin kopyasını",
             "Panele girdiğiniz parola; kimliğinizi doğrulamak içindir."],
    "sinav": ["tahtada mevzuat dayanağı gösterilmez", "En çok 8 satır"],
    "okul": ["Ana renk panelin menüsünde", "Kontrast raporu", "PNG ya da JPEG, en çok 256 KB, kenarlar 64–2048 piksel.",
             "Önizleme kaydetmeden önce yaklaşıktır"],
}  # fmt: skip


def test_uyari_cumleleri_kaybolmadi(okul):
    hazir_durum(okul)
    for bolum in BOLUMLER:
        html = ayar_sayfasi(okul, bolum)
        metin = duzlestir(re.sub(r"<[^>]+>", "", html)).replace("&#39;", "'")
        kapali = kapali_details_metni(html).replace("&#39;", "'")
        for cumle in ACIK_UYARILAR.get(bolum, []):
            assert cumle in metin, (bolum, cumle)
            assert cumle not in kapali, (bolum, cumle)
        for cumle in SAYFADAKI_CUMLELER.get(bolum, []):
            assert cumle in metin, (bolum, cumle)
    html = okul.get(SABLON_SAYFASI).text
    assert "Öğrenci ya da kişi adı yazmayın." in html and "iş güvenliği sorumlunuzun görüşünü alın" in html
    assert "Öğrenci ya da kişi adı yazmayın." not in kapali_details_metni(html)
    gonder(okul, bolum="acil_sablonlari", eylem="varsayilan")
    assert "Aşağıdakiler örnek metinlerdir; mevzuat metni değildir." in okul.get(SABLON_SAYFASI).text


def test_kosullu_uyarilar_bolum_sayfalarinda(okul, tahta):
    """Koşullu bantlar (kod yok, yoklama kapalı, öğrenci listesi yok, parola yok, tarih yok) ilgili bölümde çizilir."""
    tahta_ekle(okul, tahta, "T-1")
    kilit = ayar_sayfasi(okul, "kilit")
    assert "<strong>Kilit kodu belirlenmedi:</strong> açılışta kilit uygulanmıyor." in kilit and "Tanımsız" in kilit
    assert 'data-onay="kilit_kodu_sil"' not in kilit  # kod yokken "Dikkat gerektirir" kutusu çizilmez
    yuzer = ayar_sayfasi(okul, "yuzer")
    assert "<strong>Kilit kodu belirlenmedi:</strong>" in yuzer and 'href="/ayarlar/kilit"' in yuzer
    assert "ders yoklaması kapalıyken görünmez" in yuzer and 'href="/ayarlar/yoklama"' in yuzer
    assert "Öğrenci listesi henüz yüklenmedi" in ayar_sayfasi(okul, "yoklama")
    veri = ayar_sayfasi(okul, "veri")
    assert "Yedek parolası belirlenmedi; otomatik yedek alınmıyor." in veri and "Öğretim yılı bitiş tarihi girilmedi" in veri
    assert re.search(r"<details class=\"ozet-satir\" open>", veri)  # parola yokken form açık gelir
    gonder(okul, bolum="usb_anahtar", ua_etkin="1")
    assert "USB anahtar yalnız kilit açmada işe yarar" in ayar_sayfasi(okul, "usb")
    assert "1 tahtada ajan güncellenmeli (eski ajan belleğe bakmaz)." in ayar_sayfasi(okul, "usb")
    assert "1 tahtada ajan güncellenmeli (eski ajan temizlik yapmaz)." in ayar_sayfasi(okul, "gunsonu")
    doldur(okul)
    veri = ayar_sayfasi(okul, "veri")
    assert "Belirlendi ·" in veri and '<details class="ozet-satir">' in veri
    assert YEDEK_PAROLASI not in veri and PAROLA not in veri


def test_sablonlarda_genel_bolumu_ve_eski_baglanti_yok():
    for yol in SABLONLAR.glob("*.html"):
        metin = yol.read_text(encoding="utf-8")
        assert 'value="genel"' not in metin, yol.name
        if yol.name != "ayarlar.html":  # giriş sayfasındaki açıklama yorumu eski parça adresini anar
            assert "/ayarlar#" not in metin, yol.name
        assert "/ayarlar?yer=" not in metin, yol.name
        assert 'href="/kullanicilar"' not in metin, yol.name
    kod = "\n".join(s for s in (KOK / "web.py").read_text(encoding="utf-8").splitlines() if not s.lstrip().startswith("#"))
    assert "/ayarlar#" not in kod and "/ayarlar?yer=" not in kod
    assert not (SABLONLAR / "kullanicilar.html").exists()


def test_ayar_baglantilari_gecerli_bolum():
    for yol in [*SABLONLAR.glob("*.html"), *KOK.glob("*.py")]:
        metin = yol.read_text(encoding="utf-8")
        for hedef in re.findall(r"""["'(](/ayarlar/[a-z_]+)""", metin):
            parca = hedef.split("/")[2]
            assert parca in BOLUMLER or parca in ("gorunum", "logo", "guncelleme"), (yol.name, hedef)
        for hedef in re.findall(r'href="/ayarlar/([^"#?{]+)', metin):
            assert hedef in BOLUMLER, (yol.name, hedef)


def test_sablonlarda_form_p_icinde_degil_ayarlar():
    adlar = ["ayarlar.html", "ayar_bolum.html", "_ayar.html", "_acil_sablonlar.html", *(f"_ayar_{b}.html" for b in BOLUMLER)]
    for ad in adlar:
        metin = (SABLONLAR / ad).read_text(encoding="utf-8")
        for parca in re.findall(r"<p\b.*?</p>", metin, re.S):
            assert "<form" not in parca and "<button" not in parca.split("<form")[0][:0], (ad, parca[:60])
        # Makro bağımsız değişkeni adı "on…" ile başlamaz.
        for imza in re.findall(r"{% macro \w+\((.*?)\) -?%}", metin):
            for arguman in imza.split(","):
                assert not arguman.strip().startswith("on"), (ad, imza)


def test_onayli_dugmeler_button_tipinde(okul):
    hazir_durum(okul)
    onay_sozlugu = BETIK.split("var ONAY = {")[1].split("\n  };")[0]
    gorulen = set()
    for html in [ayar_sayfasi(okul, b) for b in BOLUMLER] + [okul.get(SABLON_SAYFASI).text]:
        for form in formlar(html):
            for d in form["dugmeler"]:
                if "data-onay" in d:
                    gorulen.add(d["data-onay"])
                    assert d.get("type") == "button" and form["id"], d
                    assert "id" not in form["alanlar"], d  # name="id" alanı olan forma onay konmaz (form.id tuzağı)
                    assert re.search(rf"\n    {d['data-onay']}: \{{", onay_sozlugu), d
    assert gorulen == {"kilit_kodu_sil", "logo_sil", "sablon_varsayilan"}
    assert re.search(r'logo_sil:\s*\{\s*ad: "eylem", deger: "sil"', BETIK)


def test_kirli_izlenen_formlarda_kaydet_dugmesi_ve_js_siz_calisir(okul):
    hazir_durum(okul)
    izlenen = 0
    for bolum in BOLUMLER:
        html = ayar_sayfasi(okul, bolum)
        for form in formlar(html):
            if "data-kirli-izle" not in form["ozellik"]:
                continue
            izlenen += 1
            assert "id" not in form["alanlar"] and form["action"] != "/yedekler/parola", bolum
            gonderen = [d for d in form["dugmeler"] if d.get("type", "submit") == "submit"]
            assert gonderen and "ana" in gonderen[0].get("class", ""), bolum  # Enter ilk gönderim düğmesini (Kaydet) seçer
            assert all("disabled" not in d for d in form["dugmeler"]), bolum
            vazgec = [d for d in form["dugmeler"] if d.get("type") == "reset"]
            assert len(vazgec) == 1 and "hidden" in vazgec[0], bolum
        # JS'siz: durum yazıları gizli gelir, yalnız Kaydet görünür.
        assert html.count('<span class="kc-yok" hidden>') == html.count('<div class="kaydet-cubugu">')
        assert html.count('<span class="kc-var" role="status" hidden>') == html.count('<div class="kaydet-cubugu">')
    assert izlenen == 14
    assert "data-kirli-izle" not in okul.get(SABLON_SAYFASI).text


def test_panel_js_ayar_kancalari():
    for kanca in ("data-kirli-izle", "data-ayar-ara", "beforeunload", "kilit_kodu_sil", "logo_sil", "ayar-eski-parca",
                  "data-ara-kat", "toLocaleLowerCase(\"tr\")"):  # fmt: skip
        assert kanca in BETIK, kanca
    assert "form.id" not in BETIK
    assert "ayarKirliKur();" in BETIK and "ayarAraKur();" in BETIK


def test_js_ve_python_katlama_haritasi_ayni():
    kaynak = re.search(r'var AYAR_KATLA_KAYNAK = "([^"]+)";', BETIK).group(1)
    hedef = re.search(r'var AYAR_KATLA_HEDEF = "([^"]+)";', BETIK).group(1)
    assert (kaynak, hedef) == (ayar_bolumleri.KATLA_KAYNAK, ayar_bolumleri.KATLA_HEDEF)
    assert len(kaynak) == len(hedef) and ayar_bolumleri.katla("çığöşüâîû") == "cigosuaiu"
    assert ayar_bolumleri.kucult("IŞIK İLE") == "ışık ile"


def test_ayar_stili_yeni_ham_renk_icermez():
    blok = STIL.split("/* ---- 0.16.0: ayarlar")[1].split("/* ---- 0.16.0 sonu ---- */")[0]
    govde = blok.split("---- */", 1)[1]
    # bilesen katmanındadır (kabuk katmanı üstüne gelir); katman sırası satırı 0.15.0'daki gibidir.
    assert govde.count("@layer bilesen {") == 1 and "@layer sifirla, temel, bilesen, kabuk, yardimci;" in STIL
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", govde) and "oklch(" not in govde and "rgb(" not in govde
    for sinif in (".ayar-duzen", ".ayar-menu", ".dar-secim", ".ayar-liste", ".ayar-deger", ".ayar-ara", ".kirinti",
                  ".kurulum", ".kurulum-liste", ".ayar-satir", "details.nedir", "details.ozet-satir", ".kaydet-cubugu",
                  "form.kirli .kaydet-cubugu", ".dikkat-kutu"):  # fmt: skip
        assert sinif in govde, sinif


# ---- uyandırma ve kayıt -----------------------------------------------------------------------------------
def test_yeni_bolumler_tahtalari_uyandirir_ve_ajan_ayarina_iner(okul, tahta, uygulama):
    basliklar = tahta_ekle(okul, tahta, "T-1")
    gonder(okul, bolum="okul", okul_adi="İnen Ad Lisesi")
    gonder(okul, bolum="kilit_kodu", kilit_kodu=KOD)
    yanit = bekle(tahta, basliklar)
    assert yanit["ayar"]["okul_adi"] == "İnen Ad Lisesi"
    assert json.dumps(yanit["ayar"]).count(KOD) == 0 and yanit["ayar"]["kilit_kodu"] == ayar("kilit_kodu")
    gonder(okul, bolum="kilit_kodu", kilit_kodu_sil="1")
    assert not bekle(tahta, basliklar)["ayar"].get("kilit_kodu")


def test_yeni_bolumler_kayda_duser_ve_degismeyen_kayit_dusmez(okul):
    gonder(okul, bolum="okul", okul_adi="Kayıt Lisesi")
    gonder(okul, bolum="okul", okul_adi="Kayıt Lisesi")  # değişmedi
    gonder(okul, bolum="kilit_kodu", kilit_kodu="")  # değişmedi
    gonder(okul, bolum="kilit_kodu", kilit_kodu=KOD)
    gonder(okul, bolum="kapatma", ok_etkin="1", ok_saatler="18:30", ok_hafta_sonu_dk="60")
    gonder(okul, bolum="kilit_kodu", kilit_kodu_sil="1")
    yeni = [k for k in kayitlar() if k in ("Okul adı kaydedildi", "Kilit kodu değiştirildi", "Kilit kodu kaldırıldı",
                                           "Otomatik kapatma ayarı kaydedildi", "Ayarlar kaydedildi")]  # fmt: skip
    assert yeni == ["Okul adı kaydedildi", "Kilit kodu değiştirildi", "Otomatik kapatma ayarı kaydedildi", "Kilit kodu kaldırıldı"]
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Otomatik kapatma ayarı kaydedildi'")[0]["ayrinti"] == "hafta içi 18:30"
    for satir in sorgu("SELECT ayrinti FROM kayit WHERE islem LIKE 'Kilit kodu%'"):
        assert satir["ayrinti"] == ""


# ---- yetki ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("yol", ["/ayarlar", "/ayarlar?ara=kilit", *(f"/ayarlar/{b}" for b in BOLUMLER)])
def test_ayar_sayfalari_yalniz_yonetici(okul, yol):
    assert okul.get(yol).status_code == 200
    kullanici_ekle(okul, "idareci1")
    gir(okul, "idareci1")
    yanit = okul.get(yol)
    assert yanit.status_code == 303 and yanit.headers["location"].startswith("/?m=") and "t=hata" in yanit.headers["location"]
    assert ileti(yanit) == "Bu sayfa için yönetici yetkisi gerekir."
    okul.cookies.clear()
    assert okul.get(yol).headers["location"] == "/giris"


def test_bilinmeyen_bolum_girise_doner(okul):
    for yol in ("/ayarlar/yok", "/ayarlar/1", "/ayarlar/genel", "/ayarlar/OKUL"):
        yanit = okul.get(yol)
        assert yanit.status_code == 303 and yanit.headers["location"].startswith("/ayarlar?m="), yol
        assert ileti(yanit) == "Bilinmeyen ayar bölümü."


@pytest.mark.parametrize("govde", [
    {"bolum": "okul", "okul_adi": "Ele Geçti"},
    {"bolum": "kapatma", "ok_etkin": "1", "ok_saatler": "08:00", "ok_hafta_sonu_dk": "10"},
    {"bolum": "kilit_kodu", "kilit_kodu": "0000"},
    {"bolum": "kilit_kodu", "kilit_kodu_sil": "1"},
], ids=["okul", "kapatma", "kilit_kodu", "kilit_kodu_sil"])  # fmt: skip
def test_yeni_post_bolumleri_idareciye_kapali_ve_kayda_duser(okul, govde):
    doldur(okul)
    once = ayarlar_tablosu()
    kullanici_ekle(okul, "idareci1")
    gir(okul, "idareci1")
    yanit = okul.post("/ayarlar", data=govde)
    assert yanit.headers["location"].startswith("/?m=") and ileti(yanit) == "Bu işlem için yönetici yetkisi gerekir."
    assert ayarlar_tablosu() == once
    assert sorgu("SELECT kullanici, ayrinti FROM kayit WHERE islem = 'Yetkisiz işlem reddedildi'")[-1] == {
        "kullanici": "idareci1", "ayrinti": "Ayarlar"}  # fmt: skip
    okul.cookies.clear()
    assert okul.post("/ayarlar", data=govde).headers["location"] == "/giris"
    assert ayarlar_tablosu() == once


def test_acil_sablon_sekmesi_yalniz_yonetici(okul):
    sayfa = okul.get("/acil").text
    assert 'aria-label="Acil durum bölümleri"' in sayfa and '<a href="/acil?sekme=sablonlar">Şablonlar</a>' in sayfa
    assert 'id="acil-sablon-formu"' not in sayfa and 'id="acil-formu"' in sayfa
    sablon = okul.get(SABLON_SAYFASI).text
    assert 'id="acil-sablon-formu"' in sablon and 'id="acil-formu"' not in sablon and 'id="acil-sablon-bilgi"' in sablon
    assert '<a href="/acil?sekme=sablonlar" aria-current="page">Şablonlar</a>' in sablon and "data-sablon-sil" in sablon
    yanit = gonder(okul, bolum="acil_sablonlari", s_ad="Sel", s_baslik="SEL", s_metin="Üst kata çıkınız.")
    assert yanit.headers["location"].startswith("/acil?sekme=sablonlar&m=") and yanit.headers["location"].endswith("#ileti")
    sayfa = okul.get(yanit.headers["location"].split("#")[0]).text
    assert sayfa.count("Acil şablonları kaydedildi.") == 1
    assert sayfa.index('id="ileti"') > sayfa.index('id="acil-sablonlari"')
    kullanici_ekle(okul, "idareci1")
    gir(okul, "idareci1")
    sayfa = okul.get("/acil").text
    assert "Acil durum bölümleri" not in sayfa and "sekme=sablonlar" not in sayfa and 'id="acil-formu"' in sayfa
    yanit = okul.get(SABLON_SAYFASI)
    assert yanit.status_code == 303 and yanit.headers["location"].startswith("/acil?m=") and "t=hata" in yanit.headers["location"]
    assert ileti(yanit) == "Şablonları yalnız yönetici düzenler."
    assert "yönetici" in ileti(gonder(okul, bolum="acil_sablonlari", s_ad="X", s_metin="y"))


def test_kullanicilar_adresi_bolume_yonlenir_ve_idareciye_kapali(okul):
    yanit = okul.get("/kullanicilar")
    assert yanit.status_code == 303 and yanit.headers["location"] == "/ayarlar/kullanicilar"
    yanit = okul.get("/kullanicilar?m=Kaydedildi.&t=hata")
    assert yanit.headers["location"].startswith("/ayarlar/kullanicilar?m=Kaydedildi.") and "t=hata" in yanit.headers["location"]
    ekle = okul.post("/kullanicilar", data={"eylem": "ekle", "ad": "idareci1", "gorunen_ad": "Deneme İdareci",
                                            "parola": PAROLA, "rol": "idareci"})  # fmt: skip
    assert ekle.headers["location"].startswith("/ayarlar/kullanicilar?yer=ekle&m=") and ileti(ekle) == "Kullanıcı eklendi."
    assert ekle.headers["location"].endswith("#ileti")
    sayfa = okul.get(ekle.headers["location"]).text
    assert "Kullanıcı eklendi." in sayfa and "Deneme İdareci" in sayfa and 'action="/kullanicilar"' in sayfa
    kisa = okul.post("/kullanicilar", data={"eylem": "ekle", "ad": "x", "parola": "1", "rol": "idareci"})
    assert kisa.status_code == 400 and ileti(kisa) == "Kullanıcı adı en az 3, parola en az 8 karakter olmalı."
    menu = sayfa.split('id="menu"')[1].split("</aside>")[0]
    assert 'href="/kullanicilar"' not in menu and '<a href="/ayarlar" aria-current="page">' in menu
    gir(okul, "idareci1")
    assert okul.get("/kullanicilar").headers["location"].startswith("/?m=")
    assert okul.get("/ayarlar/kullanicilar").headers["location"].startswith("/?m=")
    assert okul.post("/kullanicilar", data={"eylem": "ekle", "ad": "yeni12", "parola": PAROLA}).headers["location"].startswith("/?m=")


def test_baska_kaynaktan_ayar_istegi_reddedilir(okul):
    doldur(okul)
    once = ayarlar_tablosu()
    for govde in ({"bolum": "okul", "okul_adi": "Kötü"}, {"bolum": "kilit_kodu", "kilit_kodu_sil": "1"},
                  {"bolum": "kapatma", "ok_saatler": "", "ok_hafta_sonu_dk": "60"}):  # fmt: skip
        assert okul.post("/ayarlar", data=govde, headers={"Origin": "https://kotu.example"}).status_code == 403
    assert ayarlar_tablosu() == once


# ---- özetler ve giriş sayfası -----------------------------------------------------------------------------
BUGUN = date(2026, 11, 16)


def ozet(ipler=None) -> dict[str, tuple[str, str]]:
    with vt.islem() as b:
        return {a: (o["metin"], o["ton"]) for a, o in ayar_bolumleri.ozetler(b, BUGUN, ipler=[] if ipler is None else ipler).items()}


def test_ozetler_degerle_tutarli(okul):
    o = ozet()
    assert o["okul"] == ("Örnek Anadolu Lisesi", "") and o["kilit"] == ("Kod tanımsız", "uyari")
    assert o["gunsonu"] == ("Kapatma kapalı", "") and o["yuzer"] == ("Açık", "") and o["yoklama"] == ("Kapalı", "")
    assert o["usb"] == ("Kapalı", "") and o["sinav"] == ("Varsayılan", "") and o["veri"] == ("2 eksik", "uyari")
    assert o["sunucu"] == ("Adres: otomatik", "") and o["guncelleme"] == ("Denetlenmedi", "") and o["kullanicilar"] == ("1 kişi", "")
    assert set(o) == set(BOLUMLER)
    doldur(okul)
    o = ozet()
    assert o["okul"] == ("Deneme Ortaokulu", "") and o["kilit"] == ("Kod tanımlı · açılışta kilit kapalı", "")
    assert o["gunsonu"] == ("12:40, 18:30 · hafta sonu · temizlik açık", "")
    assert o["yoklama"] == ("Açık · Ayşe Y.", "") and o["usb"] == ("Açık", "")
    assert o["sinav"] == ("Özel metin", "") and o["veri"] == ("25.06.2027", "") and o["sunucu"] == ("2 adres", "")
    assert o["guncelleme"] == ("Kapalı", "")
    gonder(okul, bolum="okul", okul_adi="")
    gonder(okul, bolum="dugme", dg_acik="1")
    gonder(okul, bolum="dugme")
    assert ozet()["okul"] == ("Ad girilmedi", "uyari") and ozet()["yuzer"] == ("Kapalı", "")
    gonder(okul, bolum="dugme", dg_acik="1")
    assert ozet()["yuzer"] == ("İşlem seçilmedi", "uyari")
    gonder(okul, bolum="kapatma", ok_etkin="1", ok_saatler="18:30", ok_hafta_sonu_dk="60")
    gonder(okul, bolum="temizlik", tm_zaman="kapatma_oncesi")
    assert ozet()["gunsonu"] == ("18:30", "")
    # Saklama: tarih yok / geçti; yedek parolası var.
    gonder(okul, bolum="saklama", ogretim_yili_bitis="")
    assert ozet()["veri"] == ("Tarih yok", "uyari")
    gonder(okul, bolum="saklama", ogretim_yili_bitis="2026-06-26", sk_onay="1")
    assert ozet()["veri"] == ("Tarih geçti", "uyari")
    # Sunucu: bu bilgisayarın adresi listede yoksa uyarı (pano bandının koşulu: listede DNS adı varsa uyarmaz);
    # adresin kendisi yazılmaz.
    assert ozet(ipler=["10.0.0.99"])["sunucu"] == ("2 adres", "")
    gonder(okul, bolum="adresler", sunucu_adresleri="https://10.0.0.5:8788")
    assert ozet(ipler=["10.0.0.99"])["sunucu"] == ("Adres listede yok", "uyari")
    assert ozet(ipler=["10.0.0.5"])["sunucu"] == ("1 adres", "")
    # Güncelleme: saklanan durumdan.
    gonder(okul, bolum="guncelleme", gd_acik="1")
    with vt.islem() as b:
        vt.ayar_yaz(b, guncelleme.DURUM_ANAHTARI, {"zaman": vt.simdi(), "sonuc": "tamam", "surum": "0.0.1"})
    assert ozet()["guncelleme"] == ("Güncel", "")
    with vt.islem() as b:
        vt.ayar_yaz(b, guncelleme.DURUM_ANAHTARI, {"zaman": vt.simdi(), "sonuc": "tamam", "surum": "99.0.1"})
    assert ozet()["guncelleme"] == ("Yeni sürüm 99.0.1", "")
    with vt.islem() as b:
        vt.ayar_yaz(b, guncelleme.DURUM_ANAHTARI, {"zaman": vt.simdi(), "sonuc": "ulasilamadi", "surum": ""})
    assert ozet()["guncelleme"] == ("Ulaşılamadı", "")
    kullanici_ekle(okul, "idareci1")
    assert ozet()["kullanicilar"] == ("2 kişi", "")


def test_ozetlerde_sir_ve_adres_yok(okul):
    doldur(okul)
    kullanici_ekle(okul, "idareci1")
    with vt.islem() as b:
        metin = json.dumps(ayar_bolumleri.ozetler(b, BUGUN, ipler=["10.0.0.99"]), ensure_ascii=False)
        metin += json.dumps(ayar_bolumleri.kurulum(b, BUGUN, ipler=["10.0.0.99"]), ensure_ascii=False)
        kod_ozeti = json.dumps(vt.ayar_al(b, "kilit_kodu"))
    for yasak in (KOD, kod_ozeti.strip('"'), YEDEK_PAROLASI, PAROLA, "10.0.0.5", "10.0.0.99", "tahta.okul.local", "https://",
                  "idareci1", "Deneme Yönetici", ":\\", "TahtaKontrol"):  # fmt: skip
        assert yasak not in metin, yasak


def test_giris_ve_yan_menu_ayni_ozeti_gosterir(okul):
    doldur(okul)
    giris = okul.get("/ayarlar").text
    yan = ayar_sayfasi(okul, "sinav")
    with vt.islem() as b:
        beklenen = ayar_bolumleri.ozetler(b, date(2026, 11, 16))
    for anahtar in BOLUMLER:
        kalip = r'<a href="/ayarlar/{}"[^>]*>.*?<span class="ayar-deger[^"]*">(?:<svg.*?</span>)?{}</span>'
        metin, kisa = beklenen[anahtar]["metin"], beklenen[anahtar]["kisa"]
        # Kartta tam özet; kısası farklıysa ikisi de çizilir (telefonda stil.css kısasını gösterir).
        govde = metin if kisa == metin else f'<span class="uzun">{metin}</span><span class="kisa">{kisa}</span>'
        desen = kalip.format(anahtar, re.escape(govde))
        assert re.search(desen, giris, re.S), anahtar
        # Dar yan menüde aynı özetin kısa karşılığı yazılır (dar <details> + geniş liste: ikisi de aynı kaynaktan).
        desen = kalip.format(anahtar, re.escape(beklenen[anahtar]["kisa"]))
        assert len(re.findall(desen, yan, re.S)) == 2, anahtar
    assert yan.count('<a href="/ayarlar/sinav" aria-current="page">') == 2
    assert giris.count('class="ayar-deger') == 11
    assert "11 kısa bölümde" in giris and len(BOLUMLER) == 11


def kurulum(ipler=None) -> dict:
    with vt.islem() as b:
        return ayar_bolumleri.kurulum(b, BUGUN, ipler=[] if ipler is None else ipler)


def eksikler(k: dict) -> tuple[list[str], list[str]]:
    return [m["anahtar"] for m in k["zorunlu_eksik"]], [m["anahtar"] for m in k["oneri_eksik"]]


def test_kurulum_listesi_kosullari(okul):
    assert eksikler(kurulum()) == (["yedek_parolasi", "ogretim_yili"], ["kilit_kodu", "zil", "derslik", "ikinci_yonetici"])
    k = kurulum()
    assert (k["toplam"], k["tamam"]) == (8, 2)
    sayfa = okul.get("/ayarlar").text
    assert "Kurulumu tamamlayın" in sayfa and '<progress class="ilerleme" id="kurulum-ilerleme" max="8" value="2">' in sayfa
    assert "8 adımdan 2 tanesi tamam" in sayfa and "isteğe bağlı" in sayfa
    for madde in k["zorunlu_eksik"] + k["oneri_eksik"]:
        assert madde["neden"] in sayfa and f'href="{madde["yol"]}"' in sayfa, madde["anahtar"]
    # Pano bantlarıyla aynı anda yanar/söner.
    pano = okul.get("/").text
    assert "Yedek parolası" in pano and "Kilit kodu tanımlı değil" in pano
    okul.post("/yedekler/parola", data={"hesap_parolasi": PAROLA, "parola": YEDEK_PAROLASI, "parola2": YEDEK_PAROLASI})
    gonder(okul, bolum="kilit_kodu", kilit_kodu=KOD)
    assert eksikler(kurulum()) == (["ogretim_yili"], ["zil", "derslik", "ikinci_yonetici"])
    assert "Kilit kodu tanımlı değil" not in okul.get("/").text
    gonder(okul, bolum="okul", okul_adi="")
    assert "okul_adi" in eksikler(kurulum())[0]
    gonder(okul, bolum="okul", okul_adi="Örnek Anadolu Lisesi")
    # Sunucu adresi: pano uyarısının koşulu (adres listede yok); adresin kendisi maddede yazılmaz.
    gonder(okul, bolum="adresler", sunucu_adresleri="https://10.0.0.5:8788")
    k = kurulum(ipler=["10.0.0.99"])
    assert "sunucu_adresi" in eksikler(k)[0] and "10.0.0" not in json.dumps(k, ensure_ascii=False)
    assert "sunucu_adresi" not in eksikler(kurulum(ipler=["10.0.0.5"]))[0]
    # Tarih geçmişse madde yine eksik, nedeni değişir.
    gonder(okul, bolum="saklama", ogretim_yili_bitis="2026-06-26", sk_onay="1")
    madde = next(m for m in kurulum()["zorunlu"] if m["anahtar"] == "ogretim_yili")
    assert not madde["tamam"] and madde["neden"] == "Tarih geçti; yeni öğretim yılının bitişini girin."
    gonder(okul, bolum="saklama", ogretim_yili_bitis="2027-06-25")
    # Zorunlular tamam: kutu tek satırlık kapalı <details> olur.
    kullanici_ekle(okul, "yonetici2", "yonetici")
    assert eksikler(kurulum()) == ([], ["zil", "derslik"])
    with vt.islem() as b:  # giriş sayfası gerçek IP'yi okur; liste boşsa "adres listede yok" koşulu doğmaz
        from tahta_sunucu import adresler

        adresler.yaz(b, [])
    sayfa = okul.get("/ayarlar").text
    if "Kurulumu tamamlayın" not in sayfa:
        assert '<details class="kutu kurulum" id="kurulum">' in sayfa and "Kurulum tamam · 2 isteğe bağlı adım kaldı" in sayfa
        assert "<progress" not in sayfa
        # Özet satırı açılır olduğunu söyler (düz kalın yazı gibi görünüyordu).
        assert '<span class="degistir"><span class="ac">Göster</span><span class="kapa">Gizle</span></span></summary>' in sayfa


def test_ogrenci_maddesi_yalniz_yoklama_etkinken(okul):
    assert "ogrenci" not in [m["anahtar"] for m in kurulum()["oneri"]]
    gonder(okul, bolum="yoklama", yk_etkin="1", yk_maske="ad_soyadbas", yk_oturum_dk="8", yk_bosta_dk="3")
    madde = next(m for m in kurulum()["oneri"] if m["anahtar"] == "ogrenci")
    assert not madde["tamam"] and madde["yol"] == "/ogrenciler" and kurulum()["toplam"] == 9
    with vt.islem() as b:
        sutunlar = [s["name"] for s in b.execute("PRAGMA table_info(ogrenci)")]
    assert "aktif" in sutunlar


def test_kurulum_kutusu_hepsi_tamamsa_cizilmez(okul, monkeypatch):
    k = {"zorunlu": [], "oneri": [], "toplam": 8, "tamam": 8, "zorunlu_eksik": [], "oneri_eksik": [], "tamamlanan": []}
    monkeypatch.setattr(ayar_bolumleri, "kurulum", lambda b, bugun, ipler=None: k)
    sayfa = okul.get("/ayarlar").text
    assert 'id="kurulum"' not in sayfa and "Kurulum" not in sayfa.split('id="icerik"')[1].split('id="ayar-kapsam"')[0]


def test_giris_sayfasi_ag_cagrisi_yapmaz(tmp_path, monkeypatch, saat, ag_kapali):
    """Kural 32: giriş ve bölüm sayfaları yalnız SAKLANAN durumu okur; sayfa çizimi GitHub'a istek çıkarmaz."""

    class Sayac:
        cagri = 0

        def __call__(self):
            self.cagri += 1
            raise guncelleme.GuncellemeHatasi("çağrılmamalı")

    getirici = Sayac()
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    uygulama = web.uygulama_olustur("ab" * 32, guncelleme_getirici=getirici)
    panel = TestClient(uygulama, client=("127.0.0.1", 50000), follow_redirects=False)
    kur_ve_gir(panel)
    for yol in ("/ayarlar", "/ayarlar?ara=github", *(f"/ayarlar/{b}" for b in BOLUMLER)):
        assert panel.get(yol).status_code == 200, yol
    gonder(panel, bolum="guncelleme")
    for yol in ("/ayarlar", "/ayarlar/guncelleme"):
        sayfa = panel.get(yol).text
        assert "github.com" not in sayfa and "api.github" not in sayfa, yol
    assert "Şimdi denetle" not in panel.get("/ayarlar/guncelleme").text
    assert getirici.cagri == 0 and ag_kapali == []


# ---- arama ------------------------------------------------------------------------------------------------
def gorunen_satirlar(html: str) -> tuple[list[str], list[str]]:
    """(görünen bölüm anahtarları, görünen "başka yerde" adresleri)."""
    kapsam = html.split('id="ayar-kapsam"')[1].split('<p class="ilgili">')[0]
    bolumler, baska = [], []
    for li, yol in re.findall(r'<li data-ara="[^"]*" data-ara-kat="[^"]*"( hidden)?><a href="([^"]+)"', kapsam):
        if li:
            continue
        (bolumler if yol.startswith("/ayarlar/") else baska).append(yol.removeprefix("/ayarlar/"))
    return bolumler, baska


def test_ara_sunucuda_suzer(okul):
    assert gorunen_satirlar(okul.get("/ayarlar").text) == (BOLUMLER, [])
    assert gorunen_satirlar(okul.get("/ayarlar?ara=kvkk").text) == (["veri"], [])
    assert gorunen_satirlar(okul.get("/ayarlar?ara=kayar buton").text) == (["yuzer"], [])
    assert gorunen_satirlar(okul.get("/ayarlar?ara=KAYAR").text) == (["yuzer"], [])
    assert gorunen_satirlar(okul.get("/ayarlar?ara=yuzer").text) == (["yuzer"], [])  # harf katlama
    assert gorunen_satirlar(okul.get("/ayarlar?ara=renk").text) == (["okul"], [])
    bolumler, baska = gorunen_satirlar(okul.get("/ayarlar?ara=pin").text)
    assert bolumler == ["yoklama", "usb"] and baska == ["/ogretmenler"]
    bolumler, baska = gorunen_satirlar(okul.get("/ayarlar?ara=yedek").text)
    assert bolumler == ["veri"] and baska == ["/yedekler"]
    bolumler, baska = gorunen_satirlar(okul.get("/ayarlar?ara=kilit").text)
    assert bolumler == ["kilit", "yuzer", "usb"] and baska == ["/program?bolum=kurallar"]
    assert gorunen_satirlar(okul.get("/ayarlar?ara=kilidi durdur").text) == ([], ["/program?bolum=kurallar", "/"])
    sayfa = okul.get("/ayarlar?ara=zil").text
    assert gorunen_satirlar(sayfa) == ([], ["/program"])
    assert '<section class="kutu baska-yerde" id="baska-yerde" aria-labelledby="baska-baslik">' in sayfa  # hidden değil
    assert '<p class="ayar-ara-sonuc" id="ayar-ara-sonuc" role="status">1 sonuç</p>' in sayfa
    assert sayfa.count('class="kutu ayar-kume"') == 4 and sayfa.count('aria-labelledby="ayar-kume-') == 4
    assert len(re.findall(r'<section class="kutu ayar-kume"[^>]* hidden>', sayfa)) == 4  # boş kalan küme kartları gizli
    assert 'id="kurulum"' not in sayfa  # aramada kurulum kutusu gizlenir
    assert re.search(r'<p class="bos-not" id="ayar-ara-bos" hidden>', sayfa)
    bos = okul.get("/ayarlar?ara=qqq").text
    assert gorunen_satirlar(bos) == ([], []) and '<p class="bos-not" id="ayar-ara-bos">' in bos
    assert "Bu sözcükle bir ayar bulunamadı." in bos and ">0 sonuç<" in bos
    assert 'id="baska-yerde" aria-labelledby="baska-baslik" hidden>' in bos
    # Boş ve yalnız boşluktan oluşan sorgu: süzme yok.
    assert gorunen_satirlar(okul.get("/ayarlar?ara=%20%20").text) == (BOLUMLER, [])
    assert 'value="kayar buton"' in okul.get("/ayarlar?ara=kayar+buton").text


def test_ara_kurali(okul):
    ara = ayar_bolumleri.ara
    assert ara("")["etkin"] is False and ara("   ")["bolumler"] == BOLUMLER
    assert ara("kil")["bolumler"] == ["kilit", "yuzer", "usb"]  # sözcüğün BAŞINDA
    assert ara("ilit")["sayi"] == 0  # ortada geçmek yetmez
    assert ara("kilit kodu")["bolumler"] == ["kilit"]  # her sözcük eşleşmeli
    assert ara("İP")["bolumler"] == ["sunucu"] and ara("IŞIK")["sayi"] == 0
    assert ara("guncelleme")["bolumler"] == ["guncelleme"] and ara("sinav")["bolumler"] == ["sinav"]
    assert ara("x" * 500)["sorgu"] == "x" * ayar_bolumleri.SORGU_EN_UZUN


def test_ara_dizini_ve_html_ozellikleri_ayni_kaynaktan(okul):
    sayfa = okul.get("/ayarlar").text
    for b in ayar_bolumleri.BOLUMLER:
        saman = ayar_bolumleri.samanlik(b["baslik"], b["aciklama"], b["sozcukler"], b["kume"])
        assert f'<li data-ara="{saman}" data-ara-kat="{ayar_bolumleri.katla(saman)}"><a href="/ayarlar/{b["anahtar"]}">' in sayfa
        assert saman == ayar_bolumleri.kucult(saman) and all(s in saman.split() for s in ayar_bolumleri.sozcukler(b["sozcukler"]))
    for o in ayar_bolumleri.BASKA_YERDE:
        saman = ayar_bolumleri.samanlik(o["ad"], o["yer"], o["sozcukler"])
        assert f'<li data-ara="{saman}" data-ara-kat="{ayar_bolumleri.katla(saman)}" hidden><a href="{o["yol"]}">' in sayfa
    assert 'data-ayar-ara aria-describedby="ayar-ara-sonuc"' in sayfa and 'name="ara"' in sayfa
    assert '<form class="ayar-ara" method="get" action="/ayarlar" role="search">' in sayfa
    assert '<form class="ayar-ara" method="get" action="/ayarlar" role="search">' in ayar_sayfasi(okul, "okul")


def test_baska_yerde_adresleri_var_olan_yollardir(okul, uygulama):
    yollar = {r.path for r in uygulama.routes if "GET" in getattr(r, "methods", set())}
    for o in ayar_bolumleri.BASKA_YERDE:
        assert o["yol"].split("?")[0] in yollar, o["yol"]
        assert okul.get(o["yol"]).status_code == 200, o["yol"]
    for hedef in ayar_bolumleri.ESKI_PARCA.values():
        assert okul.get(hedef.split("#")[0]).status_code == 200, hedef
    giris = okul.get("/ayarlar").text
    for hedef in re.findall(r'<p class="ilgili">(.*?)</p>', giris, re.S)[0].split('href="')[1:]:
        assert okul.get(hedef.split('"')[0]).status_code == 200, hedef


def test_ara_dizininde_kisi_ve_tahta_adi_yok(okul, tahta):
    tahta_ekle(okul, tahta, "Zzqtahta 9-Q")
    kullanici_ekle(okul, "zzqidareci")
    sayfa = okul.get("/ayarlar?ara=zzq").text
    kapsam = sayfa.split('id="ayar-kapsam"')[1].split('<p class="ilgili">')[0]
    assert gorunen_satirlar(sayfa) == ([], []) and "Zzqtahta" not in kapsam and "zzqidareci" not in kapsam.replace('value="zzq"', "")
    with vt.islem() as b:
        assert "Örnek Anadolu" not in json.dumps([ayar_bolumleri.menu({}), ayar_bolumleri.baska_yerde()], ensure_ascii=False)
        assert b is not None


def test_ara_sorgusu_html_kacisli(okul):
    sayfa = okul.get("/ayarlar", params={"ara": '<script>alert(1)</script>"><b>'}).text
    assert "<script>alert(1)" not in sayfa and "alert(1)</script>" not in sayfa
    assert 'value="&lt;script&gt;alert(1)&lt;/script&gt;&#34;&gt;&lt;b&gt;"' in sayfa


# ---- eski adresler ve dönüşler ----------------------------------------------------------------------------
@pytest.mark.parametrize(("yer", "hedef"), list(ayar_bolumleri.ESKI_YER.items()))
def test_eski_yer_adresi_bolume_yonlenir(okul, yer, hedef):
    yanit = okul.get(f"/ayarlar?yer={yer}&m=Kaydedildi.&t=hata")
    konum = yanit.headers["location"]
    assert yanit.status_code == 303 and ileti(yanit) == "Kaydedildi." and "t=hata" in konum and konum.endswith("#ileti")
    beklenen = hedef if hedef.startswith("/") else f"/ayarlar/{hedef}?yer={yer}"
    assert konum.startswith(beklenen + "&m="), konum
    sayfa = okul.get(konum.split("#")[0])
    assert sayfa.status_code == 200 and sayfa.text.count('id="ileti"') == 1
    assert okul.get(f"/ayarlar?yer={yer}").headers["location"] == (hedef if hedef.startswith("/") else f"/ayarlar/{hedef}")


def test_eski_yer_taninmiyorsa_giris_sayfasi(okul):
    assert len(ayar_bolumleri.ESKI_YER) == 11
    for yer in ("", "yok", "ad", "kod"):
        assert okul.get(f"/ayarlar?yer={yer}").status_code == 200


def test_eski_parca_haritasi_gecerli_adresler(okul):
    sayfa = okul.get("/ayarlar").text
    blok = re.search(r'<script type="application/json" id="ayar-eski-parca">(.*?)</script>', sayfa, re.S).group(1)
    harita = json.loads(blok)
    assert harita == ayar_bolumleri.ESKI_PARCA and "ileti" not in harita and "menu" not in harita and "icerik" not in harita
    for parca, hedef in harita.items():
        yol, _, cipa = hedef.partition("#")
        html = okul.get(yol).text
        if cipa:
            assert f'id="{cipa}"' in html, (parca, hedef)
    for parca in ("adresler", "acil-sablonlari", "sinav-ekrani", "ders-yoklamasi", "usb-anahtar", "usb_anahtar", "saklama",
                  "oturum-temizligi", "acilis-kilidi", "guncelleme-denetimi", "guncelleme", "yuzer-dugme", "kimlik",
                  "okul_adi", "onizleme"):  # fmt: skip
        assert parca in harita, parca


# (gövde, uç, beklenen dönüş öneki) — şartname §5.1'in her satırı.
DONUSLER = [
    ("okul", "/ayarlar", {"bolum": "okul", "okul_adi": "A"}, "/ayarlar/okul?yer=ad&m="),
    ("gorunum", "/ayarlar/gorunum", {"eylem": "kaydet", "ana_renk": "#0e7490"}, "/ayarlar/okul?yer=kimlik&m="),
    ("gorunum_hata", "/ayarlar/gorunum", {"eylem": "kaydet", "ana_renk": "red"}, "/ayarlar/okul?yer=kimlik&m="),
    ("logo_sil", "/ayarlar/logo/sil", {}, "/ayarlar/okul?yer=logo&m="),
    ("logo_hata", "/ayarlar/logo", {"x": "1"}, "/ayarlar/okul?yer=logo&m="),
    ("kilit_kodu", "/ayarlar", {"bolum": "kilit_kodu", "kilit_kodu": "1234"}, "/ayarlar/kilit?yer=kod&m="),
    ("acilis_kilidi", "/ayarlar", {"bolum": "acilis_kilidi"}, "/ayarlar/kilit?yer=acilis&m="),
    ("kapatma", "/ayarlar", {"bolum": "kapatma", "ok_saatler": "", "ok_hafta_sonu_dk": "60"}, "/ayarlar/gunsonu?yer=kapatma&m="),
    ("temizlik", "/ayarlar", {"bolum": "temizlik"}, "/ayarlar/gunsonu?yer=temizlik&m="),
    ("temizlik_hata", "/ayarlar", {"bolum": "temizlik", "tm_zaman": "hep"}, "/ayarlar/gunsonu?yer=temizlik&m="),
    ("dugme", "/ayarlar", {"bolum": "dugme"}, "/ayarlar/yuzer?yer=dugme&m="),
    ("yoklama", "/ayarlar", {"bolum": "yoklama", "yk_maske": "ad_soyadbas", "yk_oturum_dk": "8", "yk_bosta_dk": "3"},
     "/ayarlar/yoklama?yer=yoklama&m="),
    ("yoklama_hata", "/ayarlar", {"bolum": "yoklama", "yk_maske": "tam"}, "/ayarlar/yoklama?yer=yoklama&m="),
    ("usb_anahtar", "/ayarlar", {"bolum": "usb_anahtar"}, "/ayarlar/usb?yer=usb_anahtar&m="),
    ("sinav", "/ayarlar", {"bolum": "sinav", "sinav_kurallari": "Kural."}, "/ayarlar/sinav?yer=sinav&m="),
    ("saklama", "/ayarlar", {"bolum": "saklama", "ogretim_yili_bitis": "2027-06-25"}, "/ayarlar/veri?yer=saklama&m="),
    ("saklama_hata", "/ayarlar", {"bolum": "saklama", "ogretim_yili_bitis": "bozuk"}, "/ayarlar/veri?yer=saklama&m="),
    ("adresler", "/ayarlar", {"bolum": "adresler", "sunucu_adresleri": ""}, "/ayarlar/sunucu?yer=adresler&m="),
    ("guncelleme", "/ayarlar", {"bolum": "guncelleme"}, "/ayarlar/guncelleme?yer=guncelleme&m="),
    ("denetle", "/ayarlar/guncelleme/denetle", {}, "/ayarlar/guncelleme?yer=guncelleme&m="),
    ("acil_sablonlari", "/ayarlar", {"bolum": "acil_sablonlari", "eylem": "varsayilan"}, "/acil?sekme=sablonlar&m="),
    ("genel", "/ayarlar", {"bolum": "genel", "okul_adi": "A"}, "/ayarlar?m="),
    ("bilinmeyen", "/ayarlar", {"bolum": "yok"}, "/ayarlar?m="),
    ("yedek_ayar", "/yedekler/ayar", {"saklama": "9", "kopya_dizini": "", "donus": "ayarlar"}, "/ayarlar/veri?yer=ayar&m="),
    ("yedek_parola", "/yedekler/parola", {"hesap_parolasi": "yanlis", "parola": "x", "parola2": "x", "donus": "ayarlar"},
     "/ayarlar/veri?yer=parola&m="),
    ("kullanici", "/kullanicilar", {"eylem": "yok", "id": "1"}, "/ayarlar/kullanicilar?yer=hesaplar&m="),
]  # fmt: skip


@pytest.mark.parametrize(("ad", "uc", "govde", "onek"), DONUSLER, ids=[d[0] for d in DONUSLER])
def test_donus_adresleri_bolume_gider(okul, ad, uc, govde, onek):
    yanit = okul.post(uc, data=govde)
    konum = yanit.headers["location"]
    assert yanit.status_code == 303 and konum.startswith(onek), (ad, konum)
    sayfa = okul.get(konum.split("#")[0])
    assert sayfa.status_code == 200, ad
    if "yer=" in konum or "sekme=" in konum:
        assert konum.endswith("#ileti") and sayfa.text.count('id="ileti"') == 1, ad
    else:
        assert 'id="ileti"' not in sayfa.text and ileti(yanit) in sayfa.text.replace("&#39;", "'"), ad


def test_yedek_formu_donus_ayarlar_ve_beyaz_liste(okul):
    for donus in ("//kotu.example", "https://kotu.example", "/ayarlar/okul", "AYARLAR", ""):
        yanit = okul.post("/yedekler/ayar", data={"saklama": "9", "kopya_dizini": "", "donus": donus})
        assert yanit.headers["location"].startswith("/yedekler?yer=ayar&m="), donus
    for donus in ("//kotu.example", "/ayarlar/okul"):  # parola ucunda hız sınırı var (5 deneme); az deneme yeter
        yanit = okul.post("/yedekler/parola", data={"hesap_parolasi": "yanlis", "parola": "x", "parola2": "x", "donus": donus})
        assert yanit.headers["location"].startswith("/yedekler?yer=parola&m="), donus
    assert okul.post("/yedekler/ayar", data={"saklama": "9", "kopya_dizini": ""}).headers["location"].startswith("/yedekler?yer=ayar")
    # Ayarlar'daki form: hesap parolası doğrulaması ve kayıt satırları aynen (kural 21).
    yanit = okul.post("/yedekler/parola", data={"hesap_parolasi": "yanlis", "parola": YEDEK_PAROLASI,
                                                 "parola2": YEDEK_PAROLASI, "donus": "ayarlar"})  # fmt: skip
    assert ileti(yanit) == "Hesap parolanız doğrulanamadı." and "t=hata" in yanit.headers["location"]
    with vt.islem() as b:
        from tahta_sunucu import yedek

        assert not yedek.ayarlar(b)["parola_var"]
    assert kayitlar()[-1] == "Yedek parolası belirlenemedi"
    yanit = okul.post("/yedekler/parola", data={"hesap_parolasi": PAROLA, "parola": YEDEK_PAROLASI,
                                                 "parola2": YEDEK_PAROLASI, "donus": "ayarlar"})  # fmt: skip
    assert yanit.headers["location"].startswith("/ayarlar/veri?yer=parola&m=") and ileti(yanit).startswith("Yedek parolası belirlendi.")
    sayfa = okul.get(yanit.headers["location"].split("#")[0]).text
    assert YEDEK_PAROLASI not in sayfa and PAROLA not in sayfa and "Belirlendi ·" in sayfa
    # Yedekler sayfası çalışmaya devam eder ve Ayarlar'ı gösterir.
    yedekler = okul.get("/yedekler").text
    assert 'action="/yedekler/parola"' in yedekler and 'action="/yedekler/ayar"' in yedekler
    assert 'href="/ayarlar/veri#yedek"' in yedekler and 'name="donus"' not in yedekler


@pytest.mark.parametrize(("govde", "yol", "metin"), [
    ({"bolum": "sinav", "sinav_kurallari": "\n".join(f"Kural satırı {i}" for i in range(9))}, "sinav", "Kural satırı 8"),
    ({"bolum": "adresler", "sunucu_adresleri": "http://10.0.0.5:8788\nhttps://ikinci.okul.local:8788"}, "sunucu",
     "https://ikinci.okul.local:8788"),
    ({"bolum": "acil_sablonlari", "eylem": "kaydet", "s_ad": ["Deprem", "Gaz kaçağı"], "s_baslik": ["D", "G"],
      "s_metin": ["Okulun yeni metni.", ""]}, "acil", "Okulun yeni metni."),
], ids=["sinav", "adresler", "acil"])  # fmt: skip
def test_hata_400_ayni_bolumde_cizilir(okul, govde, yol, metin):
    once = ayarlar_tablosu()
    yanit = okul.post("/ayarlar", data=govde)
    assert yanit.status_code == 400 and metin in yanit.text and ayarlarTablosuAyni(once)
    assert yanit.text.count('id="ileti"') == 1 and 'class="bant hata" role="alert" id="ileti" tabindex="-1" data-odakla' in yanit.text
    if yol == "acil":
        assert 'id="acil-sablon-formu"' in yanit.text and 'value="Gaz kaçağı"' in yanit.text
        assert '<a href="/acil?sekme=sablonlar" aria-current="page">Şablonlar</a>' in yanit.text
    else:
        assert f"<h1>{ayar_bolumleri.bolum(yol)['baslik']}</h1>" in yanit.text
        assert f'<a href="/ayarlar/{yol}" aria-current="page">' in yanit.text
        kart = {"sinav": 'id="sinav"', "sunucu": 'id="adresler"'}[yol]
        assert yanit.text.index('id="ileti"') > yanit.text.index(kart)


def ayarlarTablosuAyni(once: dict) -> bool:  # noqa: N802
    return ayarlar_tablosu() == once


def test_ileti_kartin_icinde_ve_odakli(okul):
    doldur(okul)
    for b in ayar_bolumleri.BOLUMLER:
        html = ayar_sayfasi(okul, b["anahtar"])
        assert 'id="ileti"' not in html, b["anahtar"]
        for yer in b["yerler"]:
            sayfa = okul.get(f"/ayarlar/{b['anahtar']}?yer={yer}&m=Deneme+iletisi").text
            assert sayfa.count('id="ileti"') == 1 and sayfa.count("Deneme iletisi") == 1, (b["anahtar"], yer)
            bolme = sayfa.split('id="ileti"')
            kart_baslangici = bolme[0].rfind("<section")
            kart = bolme[0][kart_baslangici:]
            assert "</section>" not in kart, (b["anahtar"], yer)  # bant, açılmış ve kapanmamış bir kartın içindedir
            assert 'tabindex="-1" data-odakla' in bolme[1][:60]
        # Sayfada karşılığı olmayan `yer`: ileti sayfa başında (odaksız) çizilir.
        sayfa = okul.get(f"/ayarlar/{b['anahtar']}?yer=baska&m=Deneme+iletisi").text
        assert sayfa.count("Deneme iletisi") == 1 and 'id="ileti"' not in sayfa
        assert sayfa.index("Deneme iletisi") < sayfa.index('class="sayfa-bas"')
    # Her kartın `yer` değeri bir kez ve yalnız kendi bölümünde tanımlıdır.
    yerler = [y for b in ayar_bolumleri.BOLUMLER for y in b["yerler"]]
    assert len(yerler) == len(set(yerler))


def test_bolum_sayfasi_iskeleti(okul):
    for b in ayar_bolumleri.BOLUMLER:
        html = ayar_sayfasi(okul, b["anahtar"])
        assert f"<title>{b['baslik']} · Ayarlar · Tahta Kontrol</title>" in html
        assert html.count("<h1>") == 1 and f"<h1>{b['baslik']}</h1>" in html
        assert '<nav class="kirinti" aria-label="Konum"><a href="/ayarlar">Ayarlar</a>' in html and f"<span>{b['kume']}</span>" in html
        assert '<nav class="ayar-menu" aria-label="Ayar bölümleri">' in html and '<details class="dar-secim">' in html
        assert f'<use href="#{b["simge"]}"/>' in html
        menu = html.split('id="menu"')[1].split("</aside>")[0]
        assert menu.count('aria-current="page"') == 1 and '<a href="/ayarlar" aria-current="page">' in menu
        kimlikler = re.findall(r'\sid="([^"]+)"', html)
        assert len(kimlikler) == len(set(kimlikler)), [k for k in kimlikler if kimlikler.count(k) > 1]
        for hedef in re.findall(r'<label[^>]* for="([^"]+)"', html):
            assert hedef in kimlikler, (b["anahtar"], hedef)
    assert '<a class="dugme sayfa-eylem" href="/yedekler">Yedekleri gör</a>' in ayar_sayfasi(okul, "veri")
    taban = (SABLONLAR / "taban.html").read_text(encoding="utf-8")
    for simge in {b["simge"] for b in ayar_bolumleri.BOLUMLER} | {"s-ara", "s-ok", "s-soru", "s-kalem"}:
        assert f'<symbol id="{simge}"' in taban, simge


def test_baska_sayfalardaki_ayar_baglantilari(okul, tahta):
    basliklar = tahta_ekle(okul, tahta, "T-1", durum={"kilitli": False, "yetenekler": ["dugme", "temizlik"]})
    kimlik = basliklar["X-Tahta-Id"]
    assert 'href="/ayarlar/kilit"' in okul.get("/").text  # "Kilit kodu tanımlı değil" bandı
    sayfa = okul.get(f"/tahta/{kimlik}?sekme=bakim").text  # 0.17.0: yetenek satırları Bakım sekmesinde
    assert 'href="/ayarlar/yuzer"' in sayfa
    assert 'href="/ayarlar/yoklama"' in okul.get("/yoklama").text
    assert 'href="/ayarlar/usb"' in okul.get("/usb-anahtarlar").text
    assert 'href="/acil?sekme=sablonlar"' in okul.get("/acil").text
    gonder(okul, bolum="kapatma", ok_etkin="1", ok_saatler="18:30", ok_hafta_sonu_dk="60")
    assert 'href="/ayarlar/gunsonu"' in okul.get("/").text


# ---- inceleme düzeltmeleri (0.16.0) ------------------------------------------------------------------------
def test_yoklama_maskesi_ornekli_radyo_kartlari(okul):
    """Gizlilik ayarı açılır listede kesiliyordu: üç seçenek, örneğiyle, radyo kartı olarak açık durur."""
    from tahta_sunucu import maske

    gonder(okul, bolum="yoklama", yk_etkin="1", yk_maske="no_basharf", yk_oturum_dk="8", yk_bosta_dk="3")
    html = ayar_sayfasi(okul, "yoklama")
    (form,) = [f for f in formlar(html) if bolum_degeri(f) == "yoklama"]
    secenekler = form["alanlar"]["yk_maske"]
    assert [s["value"] for s in secenekler] == list(maske.SINIF_BICIMLERI)
    assert all(s["_etiket"] == "input" and s["type"] == "radio" for s in secenekler)
    assert [s["value"] for s in secenekler if "checked" in s] == ["no_basharf"]
    assert "<select" not in html.split('id="yoklama"')[1] and '"tam"' not in html
    for ornek in ("Tahtada: 123 Ayşe Y.", "Tahtada: Ayşe Y.", "Tahtada: 1047 A. Y."):
        assert ornek in html, ornek
    for kod, etiket in maske.SINIF_BICIMLERI.items():
        ad, ornek = maske.bicim_parcalari(kod)
        assert ad and ornek and etiket == f"{ad} ({ornek})"
    assert maske.bicim_parcalari("tam") == ("", "")
    # Seçilen kart kaydedilir; alan adı ve değerler değişmedi.
    yanit = gonder(okul, bolum="yoklama", yk_etkin="1", yk_maske="ad_soyadbas", yk_oturum_dk="8", yk_bosta_dk="3")
    assert ileti(yanit).startswith("Yoklama ayarları kaydedildi.")
    assert ayar("yoklama")["maske"] == "ad_soyadbas"
    assert ".radyo-kart" in STIL


def test_yedek_parolasi_hatasinda_form_acik_gelir(okul):
    okul.post("/yedekler/parola", data={"hesap_parolasi": PAROLA, "parola": YEDEK_PAROLASI, "parola2": YEDEK_PAROLASI})
    kapali = '<details class="ozet-satir">'
    acik = '<details class="ozet-satir" open>'
    assert kapali in ayar_sayfasi(okul, "veri")
    yanit = okul.post("/yedekler/parola", data={"hesap_parolasi": "yanlis", "parola": YEDEK_PAROLASI,
                                                 "parola2": YEDEK_PAROLASI, "donus": "ayarlar"})  # fmt: skip
    sayfa = okul.get(yanit.headers["location"].split("#")[0]).text
    assert "Hesap parolanız doğrulanamadı." in sayfa and acik in sayfa and kapali not in sayfa
    assert YEDEK_PAROLASI not in sayfa and "yanlis" not in sayfa
    # Başarılı kayıtta ve başka kartın hatasında kapalı kalır.
    yanit = okul.post("/yedekler/parola", data={"hesap_parolasi": PAROLA, "parola": YEDEK_PAROLASI,
                                                 "parola2": YEDEK_PAROLASI, "donus": "ayarlar"})  # fmt: skip
    assert kapali in okul.get(yanit.headers["location"].split("#")[0]).text
    assert kapali in okul.get("/ayarlar/veri?yer=ayar&m=Deneme&t=hata").text


def test_saklama_onaysiz_gecmis_tarih_alanda_kalir(okul):
    gonder(okul, bolum="saklama", ogretim_yili_bitis="2027-06-25")
    once = ayarlar_tablosu()
    yanit = gonder(okul, bolum="saklama", ogretim_yili_bitis="2026-06-26")
    assert yanit.status_code == 400 and ayarlar_tablosu() == once
    assert "26.06.2026 geçmiş bir tarih" in ileti(yanit) and "onay kutusunu işaretleyip" in ileti(yanit)
    assert 'name="ogretim_yili_bitis" value="2026-06-26"' in yanit.text
    assert '<input type="checkbox" name="sk_onay" value="1">' in yanit.text  # kutu kendiliğinden işaretlenmez
    assert yanit.text.index('id="ileti"') > yanit.text.index('id="saklama"')
    assert '<a href="/ayarlar/veri" aria-current="page">' in yanit.text
    assert kayitlar()[-1] == "Saklama tarihi reddedildi"
    # Olağan sayfada alan kayıtlı tarihi gösterir; onayla aynı tarih kaydedilir.
    assert 'name="ogretim_yili_bitis" value="2027-06-25"' in ayar_sayfasi(okul, "veri")
    yanit = gonder(okul, bolum="saklama", ogretim_yili_bitis="2026-06-26", sk_onay="1")
    assert yanit.status_code == 303 and ayar(saklama.AYAR_ANAHTARI) == "2026-06-26"


def test_kullanici_ekleme_hatasi_kartta_ve_yazilanlar_korunur(okul):
    yanit = okul.post("/kullanicilar", data={"eylem": "ekle", "ad": "Yeni.Idareci", "gorunen_ad": "Deneme <İdareci>",
                                             "parola": "kisa", "rol": "yonetici"})  # fmt: skip
    assert yanit.status_code == 400 and ileti(yanit) == "Kullanıcı adı en az 3, parola en az 8 karakter olmalı."
    html = yanit.text
    assert html.count('id="ileti"') == 1 and html.index('id="ileti"') > html.index('id="kullanici-ekle"')
    assert 'name="gorunen_ad" value="Deneme &lt;İdareci&gt;"' in html and 'name="ad" value="yeni.idareci"' in html
    assert '<option value="yonetici" selected>' in html and "kisa" not in html.split('id="kullanici-ekle"')[1]
    assert 'name="parola" minlength="8" required' in html and 'name="parola" value' not in html
    assert sorgu("SELECT COUNT(*) AS n FROM kullanici")[0]["n"] == 1
    # Var olan ad da aynı kartta reddedilir.
    kullanici_ekle(okul, "idareci1")
    yanit = okul.post("/kullanicilar", data={"eylem": "ekle", "ad": "idareci1", "gorunen_ad": "İkinci", "parola": PAROLA})
    assert yanit.status_code == 400 and ileti(yanit) == "Bu kullanıcı adı zaten var."
    assert sorgu("SELECT COUNT(*) AS n FROM kullanici")[0]["n"] == 2
    # Satır işlemlerinin iletisi "Hesaplar" kartında.
    yanit = okul.post("/kullanicilar", data={"eylem": "parola", "id": "1", "parola": "kisa"})
    assert yanit.headers["location"].startswith("/ayarlar/kullanicilar?yer=hesaplar&m=") and "t=hata" in yanit.headers["location"]
    html = okul.get(yanit.headers["location"].split("#")[0]).text
    assert '<h2 id="hesaplar-baslik">Hesaplar</h2>' in html
    assert html.index('id="hesaplar"') < html.index('id="ileti"') < html.index('id="kullanici-ekle"')


def test_ara_es_anlamlilar_ve_sonucsuz_durum(okul):
    ara = ayar_bolumleri.ara
    for sorgu_, bolum in (("temizlik", "gunsonu"), ("kapanma saati", "gunsonu"), ("kapanış", "gunsonu"),
                          ("kişisel veri", "veri"), ("kisisel", "veri"), ("tarih", "veri"), ("yıl sonu", "veri"),
                          ("şifre", "veri"), ("idareci ekle", "kullanicilar"), ("hesap ekle", "kullanicilar"),
                          ("müdür yardımcısı", "kullanicilar")):  # fmt: skip
        assert bolum in ara(sorgu_)["bolumler"], sorgu_
    assert ara("ikili")["baska"] == [3] and ayar_bolumleri.BASKA_YERDE[3]["yol"] == "/program"
    bos = okul.get("/ayarlar?ara=qqq").text
    assert '<a href="/ayarlar">aramayı temizleyip bütün bölümleri görün</a>' in bos
    # Telefonda kesilmeyen kısa örnek metin.
    assert 'placeholder="Ara: kilit kodu, kvkk, zil…"' in bos


def test_ozet_yalniz_hafta_sonu_kapatmasinda_kapali_demez(okul):
    """Kartın rozeti "Açık" derken giriş özeti "Kapatma kapalı" diyordu."""
    gonder(okul, bolum="kapatma", ok_saatler="", ok_hafta_sonu="1", ok_hafta_sonu_dk="60")
    assert ozet()["gunsonu"] == ("Hafta sonu", "")
    assert '<span class="rozet" data-durum="tamam">Açık</span>' in ayar_sayfasi(okul, "gunsonu").split('id="temizlik"')[0]
    gonder(okul, bolum="kapatma", ok_etkin="1", ok_saatler="18:30", ok_hafta_sonu="1", ok_hafta_sonu_dk="60")
    assert ozet()["gunsonu"] == ("18:30 · hafta sonu", "")
    gonder(okul, bolum="kapatma", ok_saatler="18:30", ok_hafta_sonu_dk="60")  # saat yazılı ama kapalı
    assert ozet()["gunsonu"] == ("Kapatma kapalı", "")
    kapatma_ozeti = ayar_bolumleri.kapatma_ozeti
    assert kapatma_ozeti(None) == kapatma_ozeti("bozuk") == kapatma_ozeti({}) == "Kapatma kapalı"


def test_ozetler_tek_basina_anlasilir_ve_kisa_karsiligi_var(okul):
    with vt.islem() as b:
        o = ayar_bolumleri.ozetler(b, BUGUN, ipler=[])
    assert all(set(v) == {"metin", "ton", "kisa"} and v["kisa"] for v in o.values())
    assert (o["kilit"]["metin"], o["kilit"]["kisa"]) == ("Kod tanımsız", "Tanımsız")
    assert (o["sunucu"]["metin"], o["sunucu"]["kisa"]) == ("Adres: otomatik", "Otomatik")
    gonder(okul, bolum="kilit_kodu", kilit_kodu=KOD)
    gonder(okul, bolum="yoklama", yk_etkin="1", yk_maske="no_ad_soyadbas", yk_oturum_dk="8", yk_bosta_dk="3")
    with vt.islem() as b:
        o = ayar_bolumleri.ozetler(b, BUGUN, ipler=[])
    assert (o["kilit"]["metin"], o["kilit"]["kisa"]) == ("Kod tanımlı · açılışta kilit açık", "Tanımlı")
    assert (o["yoklama"]["metin"], o["yoklama"]["kisa"]) == ("Açık · 123 Ayşe Y.", "Açık")
    assert KOD not in json.dumps(o, ensure_ascii=False)


def test_genel_ok_saatler_yoksa_kapatmayi_sifirlamaz(okul):
    """Gizli `bolum`u düşmüş "Okulun adı" formu (yalnız okul_adi) otomatik kapatmayı sıfırlamaz; 0.15.0 formu
    `ok_saatler` metin alanını her zaman gönderdiği için eski davranış değişmez."""
    doldur(okul)
    kapatma = ayar("otomatik_kapatma")
    once = ayarlar_tablosu()
    yanit = okul.post("/ayarlar", data={"okul_adi": "Yalnız Ad"})
    assert ileti(yanit) == "Ayarlar kaydedildi." and ayar("okul_adi") == "Yalnız Ad"
    assert ayar("otomatik_kapatma") == kapatma
    assert {a for a in once if once[a] != ayarlar_tablosu()[a]} == {"okul_adi"}
    # Eski tam form: boş ok_saatler kapatmayı (bilerek) kapatır; bozuk saat hiçbir şey yazmaz.
    okul.post("/ayarlar", data={"bolum": "genel", "okul_adi": "Tam Form", "ok_saatler": ""})
    assert ayar("otomatik_kapatma") == {"etkin": False, "saatler": [], "hafta_sonu": False, "hafta_sonu_dk": 60}
    once = ayarlar_tablosu()
    yanit = okul.post("/ayarlar", data={"bolum": "genel", "okul_adi": "Bozuk", "ok_saatler": "25:00"})
    assert "t=hata" in yanit.headers["location"] and ayarlar_tablosu() == once


def test_acil_sablon_hatasinda_menude_acil_etkin(okul):
    yanit = gonder(okul, bolum="acil_sablonlari", eylem="kaydet", s_ad="Deprem", s_baslik="D", s_metin="")
    assert yanit.status_code == 400
    menu = yanit.text.split('id="menu"')[1].split("</aside>")[0]
    assert '<a href="/ayarlar" aria-current="page">' not in menu and 'href="/ayarlar"' in menu
    assert re.search(r'<a class="acil-dugme" href="/acil" aria-current="page">', yanit.text)


def test_kilit_kodu_goster_ve_js_siz_notlar(okul):
    doldur(okul)
    kilit = ayar_sayfasi(okul, "kilit")
    # "Kodu göster": adsız kutu (gönderilmez), JS'siz gizli; alan parola türünde çizilir.
    assert '<label class="satir" hidden><input type="checkbox" data-goster="kilit_kodu"> Kodu göster</label>' in kilit
    assert '<input type="password" id="kilit_kodu" name="kilit_kodu"' in kilit
    assert "kodGosterKur();" in BETIK and "input[data-goster]" in BETIK
    # Onaylı işler JS ister (taslak §3 madde 6); JS'siz tarayıcıya bunu söyleyen not vardır.
    okul_sayfasi = ayar_sayfasi(okul, "okul")
    for html in (kilit, okul_sayfasi):
        assert "<noscript><p class=\"not\">Bu işlem onay penceresiyle yapılır; tarayıcıda JavaScript açık olmalıdır.</p></noscript>" in html


def test_varsayilan_renk_dugmesi_kaydet_cubugunun_disinda(okul):
    html = ayar_sayfasi(okul, "okul")
    form = html.split('id="gorunum-formu"')[1].split("</form>")[0]
    assert "Renkleri kaydet" in form and "Varsayılan renklere dön" not in form
    assert '<button form="gorunum-formu" name="eylem" value="varsayilan">Varsayılan renklere dön</button>' in html
    # Düğme aynı uca aynı değeri yollar; JS'siz de çalışır.
    okul.post("/ayarlar/gorunum", data={"eylem": "kaydet", "ana_renk": "#7a1f2b"})
    yanit = okul.post("/ayarlar/gorunum", data={"eylem": "varsayilan", "ana_renk": "#7a1f2b"})
    assert ileti(yanit) == "Renkler varsayılana döndürüldü."


def test_simdi_denetle_son_denetim_satirinda_ve_usb_notu(okul):
    gonder(okul, bolum="guncelleme", gd_acik="1")
    html = ayar_sayfasi(okul, "guncelleme")
    satir = html.split('class="oneri-satir denetim-satiri"')[1].split("</div>")[0]
    assert "Kurulu sürüm" in satir and 'action="/ayarlar/guncelleme/denetle"' in satir and "Şimdi denetle" in satir
    assert html.count("Şimdi denetle") == 1
    usb = ayar_sayfasi(okul, "usb")
    assert "Kapalıyken aşağıdaki seçenekler de uygulanmaz." in usb and "Yoklama › " not in usb
    assert "Yoklama › " not in ayar_sayfasi(okul, "yoklama")


def test_kurulum_tamamlananlar_adlariyla_tek_satirda(okul):
    sayfa = okul.get("/ayarlar").text
    k = kurulum()
    adlar = ", ".join(m["ad"] for m in k["tamamlanan"])
    assert f"{len(k['tamamlanan'])} adım tamam: {adlar}.</span></p>" in sayfa
    assert '<details class="nedir">' not in sayfa.split('id="kurulum"')[1].split("</section>")[0]


def test_saklama_notu_yeni_bolum_adini_soyler(okul):
    with vt.islem() as b:
        assert "(Ayarlar › Veri saklama ve yedek)" in saklama.silinme_metni(b)
    for dosya in list(KOK.glob("*.py")) + list(SABLONLAR.glob("*.html")):
        assert "Kişisel veri saklama" not in dosya.read_text(encoding="utf-8"), dosya.name
