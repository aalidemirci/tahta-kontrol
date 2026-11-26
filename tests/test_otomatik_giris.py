"""Açılışta otomatik giriş (0.22.0, kural 39): sunucu tarafı.

Ayar (`ayar.otomatik_giris`, durum tabanlı, üç değerli), Ayarlar kartı, kilitsiz açılma koruması, Bugün uyarısı,
tahta sayfasındaki durum satırı. Bütün veriler UYDURMADIR.
"""

from __future__ import annotations

import pytest
from yardimci import bekle, gir, ileti, kimlik, kullanici_ekle, kur_ve_gir, sorgu, tahta_ekle

from tahta_ajan import otomatik_giris as ajan_og
from tahta_sunucu import otomatik_giris, vt

YETENEKLER = ["acil", "duyuru_id", "dugme", "acilis_kilidi", "otomatik_giris"]
YENI = {"kilitli": False, "yetenekler": YETENEKLER, "ekranlar": [], "oturum": {"sinif": "yok"}}
ESKI = {"kilitli": False, "yetenekler": ["acil", "duyuru_id", "dugme"], "ekranlar": []}


@pytest.fixture
def okul(panel, tahta, saat):
    kur_ve_gir(panel)
    return {"yeni": tahta_ekle(panel, tahta, "T-01", YENI, surum="0.22.0"),
            "eski": tahta_ekle(panel, tahta, "T-02", ESKI, surum="0.21.0")}  # fmt: skip


def giris_ayari(tahta, basliklar, durum=None):
    ayar = bekle(tahta, basliklar, durum or YENI, surum="0.22.0")["ayar"]
    return ayar.get("otomatik_giris", "YOK")


def kaydet(panel, kip):
    return panel.post("/ayarlar", data={"bolum": "otomatik_giris", "og_kip": kip})


def kilit_kodu(panel, kod="2468"):
    panel.post("/ayarlar", data={"bolum": "kilit_kodu", "kilit_kodu": kod})


def test_varsayilan_dokunma_alan_hic_gonderilmez(panel, tahta, okul):
    assert giris_ayari(tahta, okul["yeni"]) == "YOK"
    sayfa = panel.get("/ayarlar/kilit").text
    assert 'id="giris"' in sayfa and 'name="og_kip" value="dokunma" checked' in sayfa


def test_ogretmen_kilit_kodu_yokken_kaydedilmez(panel, tahta, okul):
    yanit = kaydet(panel, "ogretmen")
    assert "t=hata" in yanit.headers["location"] and "kilit kodu belirlenmedi" in ileti(yanit)
    assert giris_ayari(tahta, okul["yeni"]) == "YOK"
    # Seçenek pasif çizilmez (Ayarlar kuralı); nedeni yazılır.
    sayfa = panel.get("/ayarlar/kilit").text
    assert 'value="ogretmen" aria-describedby="giris-engel"' in sayfa and "şu an kaydedilemez" in sayfa
    assert 'value="ogretmen" disabled' not in sayfa


def test_ogretmen_acilista_kilit_kapaliyken_kaydedilmez(panel, tahta, okul):
    kilit_kodu(panel)
    panel.post("/ayarlar", data={"bolum": "acilis_kilidi"})  # kutu işaretsiz: kapalı
    yanit = kaydet(panel, "ogretmen")
    assert "açılışta kilit kapalı" in ileti(yanit)
    assert giris_ayari(tahta, okul["yeni"]) == "YOK"


def test_ogretmen_kaydedilir_yalniz_yetenekli_tahtaya_iner_kayda_duser(panel, tahta, okul):
    kilit_kodu(panel)
    yanit = kaydet(panel, "ogretmen")
    assert yanit.headers["location"].startswith("/ayarlar/kilit?yer=giris")
    assert "bir sonraki açılışta" in ileti(yanit) and "1 tahtada ajan güncellenmeli" in ileti(yanit)
    assert giris_ayari(tahta, okul["yeni"]) == {"hesap": "ogretmen"}
    assert giris_ayari(tahta, okul["eski"], ESKI) == "YOK"
    kayit = sorgu("SELECT * FROM kayit WHERE islem = ?", otomatik_giris.ISLEM_ADI)
    assert kayit and kayit[-1]["ayrinti"] == "öğretmen hesabı"
    assert "değişmedi" in ileti(kaydet(panel, "ogretmen"))
    # Kaldır: hesap None iner (ajan yalnız kendi dosyasını siler).
    kaydet(panel, "kapali")
    assert giris_ayari(tahta, okul["yeni"]) == {"hesap": None}
    kaydet(panel, "dokunma")
    assert giris_ayari(tahta, okul["yeni"]) == "YOK"


def test_bilinmeyen_deger_ve_baska_hesap_yazilmaz(panel, tahta, okul):
    kilit_kodu(panel)
    for deger in ("etapadmin", "root", "kisisel", ""):
        yanit = kaydet(panel, deger)
        assert "t=hata" in yanit.headers["location"]
    with vt.islem() as b:
        assert vt.ayar_al(b, otomatik_giris.AYAR_ANAHTARI) is None
        vt.ayar_yaz(b, otomatik_giris.AYAR_ANAHTARI, "etapadmin")  # bozuk kayıt varsayılana düşer
        assert otomatik_giris.ayar_al(b) == "dokunma"
    assert giris_ayari(tahta, okul["yeni"]) == "YOK"


def test_hesap_listesi_ajanla_ayni_ve_dar():
    assert otomatik_giris.HESAPLAR == ajan_og.HESAPLAR == ("ogretmen",)
    # Ajan ve paket kaldırma betiği (prerm) aynı dosyayı ve imzayı tanır. (araclar/otomatik-giris.sh depoda
    # izlenmez; aynı ad ve içeriği yazar.)
    from tahta_sunucu import ayar as sunucu_ayar

    prerm = (sunucu_ayar.SUNUCU_DIZINI / "ajan_paket" / "prerm").read_text(encoding="utf-8")
    assert ajan_og.icerik("ogretmen").splitlines()[2:] == [
        "[Seat:*]",
        "autologin-user=ogretmen",
        "autologin-user-timeout=0",
    ]
    assert ajan_og.DOSYA_ADI in prerm and ajan_og.IMZA.replace(".", r"\.") in prerm


def test_yalniz_yonetici_degistirir(panel, tahta, okul):
    kilit_kodu(panel)
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    kaydet(panel, "ogretmen")
    gir(panel, "yonetici")
    assert giris_ayari(tahta, okul["yeni"]) == "YOK"


def test_kosul_sonradan_bozulursa_bugun_yoneticiyi_uyarir(panel, tahta, okul):
    kilit_kodu(panel)
    kaydet(panel, "ogretmen")
    assert "Otomatik giriş açık ama" not in panel.get("/").text
    yanit = panel.post("/ayarlar", data={"bolum": "acilis_kilidi"})
    assert "kilitsiz açılır" in ileti(yanit)
    bugun = panel.get("/").text
    assert "Otomatik giriş açık ama açılışta kilit kapalı" in bugun
    assert "Tahtalar kilitsiz açılır" in panel.get("/ayarlar/kilit").text
    # Ayar kendiliğinden değişmez; idareci uyarıyı görmez.
    assert giris_ayari(tahta, okul["yeni"]) == {"hesap": "ogretmen"}
    kullanici_ekle(panel, "idareci2")
    gir(panel, "idareci2")
    assert "Otomatik giriş açık ama" not in panel.get("/").text


def test_tahta_sayfasi_ajanin_bildirdigi_durumu_sinifla_gosterir(panel, tahta, okul):
    durum = dict(
        YENI,
        otomatik_giris={"lightdm": True, "etkin": "ogretmen", "bizim": True, "ezilmis": False, "hata": ""},
    )
    bekle(tahta, okul["yeni"], durum, surum="0.22.0")
    sayfa = panel.get(f"/tahta/{kimlik(okul['yeni'])}?sekme=bakim").text
    assert "<dt>Otomatik giriş</dt>" in sayfa and "öğretmen" in sayfa and "Tahta Kontrol ayarı" in sayfa
    # Kişisel hesap adı gelse de görünmez; bilinmeyen değer atılır.
    durum["otomatik_giris"] = {
        "lightdm": True,
        "etkin": "ayse.yilmaz",
        "bizim": False,
        "ezilmis": False,
        "hata": "",
    }
    bekle(tahta, okul["yeni"], durum, surum="0.22.0")
    sayfa = panel.get(f"/tahta/{kimlik(okul['yeni'])}?sekme=bakim").text
    assert "ayse.yilmaz" not in sayfa
    durum["otomatik_giris"] = {
        "lightdm": True,
        "etkin": "kisisel",
        "bizim": True,
        "ezilmis": True,
        "hata": "",
    }
    bekle(tahta, okul["yeni"], durum, surum="0.22.0")
    sayfa = panel.get(f"/tahta/{kimlik(okul['yeni'])}?sekme=bakim").text
    assert "kişisel hesap" in sayfa and "Başka bir ayar eziyor" in sayfa
    eski = panel.get(f"/tahta/{kimlik(okul['eski'])}?sekme=bakim").text
    assert "<dt>Otomatik giriş</dt>" in eski and "ajan desteklemiyor" in eski


def test_tahta_durumu_suzer():
    assert otomatik_giris.tahta_durumu({}) is None
    d = otomatik_giris.tahta_durumu({"otomatik_giris": {"lightdm": "evet", "etkin": "x", "hata": "a" * 500}})
    assert d == {"lightdm": False, "etkin": "", "bizim": False, "ezilmis": False, "hata": "a" * 200}


def test_ayarlar_sayilari(panel, tahta, okul):
    kilit_kodu(panel)
    kaydet(panel, "ogretmen")
    durum = dict(
        YENI,
        otomatik_giris={"lightdm": True, "etkin": "ogretmen", "bizim": True, "ezilmis": False, "hata": ""},
    )
    bekle(tahta, okul["yeni"], durum, surum="0.22.0")
    sayfa = panel.get("/ayarlar/kilit").text
    assert "Uygulandı: 1 tahta" in sayfa and "1 tahtada ajan güncellenmeli" in sayfa
    giris = panel.get("/ayarlar").text
    assert "otomatik giriş" in giris


def test_dokunmaya_alininca_tahtada_kalan_ayar_icin_de_uyarilir(panel, tahta, okul):
    # İnceleme bulgusu (0.22.0): ayar "dokunma"ya alınınca dosya tahtada kalır; kilit koruması tahtaların
    # bildirdiğine de bakmalı, yoksa açılışta kilit kapatılınca tahtalar uyarısız kilitsiz açılır.
    kilit_kodu(panel)
    kaydet(panel, "ogretmen")
    durum = dict(
        YENI,
        otomatik_giris={"lightdm": True, "etkin": "ogretmen", "bizim": True, "ezilmis": False, "hata": ""},
    )
    bekle(tahta, okul["yeni"], durum, surum="0.22.0")
    assert "Son yazılan ayar tahtada kalır" in ileti(kaydet(panel, "dokunma"))
    assert "1 tahtada Tahta Kontrol'ün otomatik giriş ayarı duruyor" in panel.get("/ayarlar/kilit").text
    yanit = panel.post("/ayarlar", data={"bolum": "acilis_kilidi"})
    assert "kilitsiz açılır" in ileti(yanit)
    bugun = panel.get("/").text
    assert "1 tahtada otomatik giriş ayarı duruyor ama açılışta kilit kapalı" in bugun
    assert "Tahtalar kilitsiz açılır" in panel.get("/ayarlar/kilit").text
    # Kod kaldırılırken de uyarılır.
    panel.post("/ayarlar", data={"bolum": "acilis_kilidi", "ak_acik": "1"})
    yanit = panel.post("/ayarlar", data={"bolum": "kilit_kodu", "kilit_kodu_sil": "1"})
    assert "kilitsiz açılır" in ileti(yanit)
    # Tahta dosyayı kaldırdığını bildirince uyarı kalkar.
    durum["otomatik_giris"] = {"lightdm": True, "etkin": "", "bizim": False, "ezilmis": False, "hata": ""}
    bekle(tahta, okul["yeni"], durum, surum="0.22.0")
    assert "otomatik giriş ayarı duruyor" not in panel.get("/").text
    with vt.islem() as b:
        assert otomatik_giris.kilitsiz_risk(b) is None
