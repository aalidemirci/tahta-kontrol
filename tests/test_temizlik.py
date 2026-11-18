"""Oturum temizliği (K7, 0.8.0): sunucu tarafı — ayar, zamanlayıcı, komut, yetki, panel ve uçtan uca akış.

Saat `saat` fikstürüyle sabittir (pazartesi 16.11.2026). Bütün veriler UYDURMADIR.
"""

from __future__ import annotations

import pytest
from yardimci import (
    PAROLA,
    an,
    bekle,
    gir,
    ileti,
    kimlik,
    kullanici_ekle,
    kur_ve_gir,
    sorgu,
    tahta_ekle,
    zil_elle,
)

from tahta_sunucu import vt

YETENEKLI = {"kilitli": False, "yetenekler": ["acil", "duyuru_id", "program_kilidi", "temizlik"],
             "ekranlar": [{"arayuz": "gtk3"}], "oturum": {"sinif": "ogretmen"}}  # fmt: skip
ESKI = {"kilitli": False, "yetenekler": ["acil", "duyuru_id"], "ekranlar": [{"arayuz": "gtk3"}]}


@pytest.fixture
def okul(panel, tahta, saat):
    kur_ve_gir(panel)
    yeni = tahta_ekle(panel, tahta, "T-01", YETENEKLI)
    eski = tahta_ekle(panel, tahta, "T-02", ESKI)
    return {"yeni": yeni, "eski": eski}


def ayarla(panel, **alanlar):
    form = {"bolum": "temizlik", "tm_etkin": "1", "tm_zaman": "kapatma_oncesi", "tm_saat": "17:30", **alanlar}
    return ileti(panel.post("/ayarlar", data=form))


def kapatma(panel, saatler="17:00"):
    panel.post("/ayarlar", data={"bolum": "genel", "okul_adi": "Örnek Lisesi", "ok_etkin": "1", "ok_saatler": saatler})


def calistir(uygulama, saat, zaman):
    saat.ayarla(zaman)
    with vt.islem() as b:
        b.execute("UPDATE tahta SET son_gorulme = ?", (vt.simdi(),))
    return uygulama.state.temizlik_zamanlayici(zaman)


def temizlikler():
    return sorgu("SELECT * FROM komut WHERE tur = 'temizlik' ORDER BY id")


def test_temizlik_varsayilan_kapali(uygulama, panel, okul, saat):
    kapatma(panel)
    assert calistir(uygulama, saat, an(16, 16, 55, 10)) == [] and temizlikler() == []
    sayfa = panel.get("/ayarlar/gunsonu").text
    assert "checked" not in sayfa.split('name="tm_etkin"')[1].split(">")[0]
    assert "Gün sonunda ortak hesapta oturum temizliği yap" in sayfa


def test_temizlik_kapatmadan_once_bir_kez_yalniz_yetenekli_tahtaya(uygulama, panel, okul, saat):
    kapatma(panel, "17:00")
    assert ayarla(panel) == "Oturum temizliği ayarı kaydedildi."
    assert calistir(uygulama, saat, an(16, 16, 54, 50)) == []  # henüz değil
    idler = calistir(uygulama, saat, an(16, 16, 55, 10))
    assert idler == [kimlik(okul["yeni"])]
    (k,) = temizlikler()
    assert k["tahta_id"] == kimlik(okul["yeni"]) and k["olusturan"] == "sistem"
    assert k["bitis"] - int(an(16, 16, 55, 10).timestamp()) == 120  # kısa ömür
    assert '"hesaplar": ["ogretmen", "ogrenci"]' in k["veri_json"]
    assert calistir(uygulama, saat, an(16, 16, 55, 30)) == [] and len(temizlikler()) == 1  # aynı an için bir kez
    kayit = sorgu("SELECT * FROM kayit WHERE islem = 'Oturum temizliği'")[-1]
    assert "otomatik kapatma (17:00) öncesi: 1 tahta" in kayit["ayrinti"] and "1 tahtada ajan güncellenmeli" in kayit["ayrinti"]


def test_temizlik_kacan_is_sonradan_calismaz(uygulama, panel, tahta, okul, saat):
    kapatma(panel, "17:00")
    ayarla(panel)
    assert calistir(uygulama, saat, an(16, 16, 59, 30)) == []  # zamanından 4,5 dk sonra: yapılmaz
    assert temizlikler() == []
    # Komut verildi ama tahta 2 dk içinde almadıysa süresi dolar (sonradan açılan tahta eski komutu almaz).
    calistir(uygulama, saat, an(17, 16, 55, 0))
    saat.ilerlet(200)
    yanit = bekle(tahta, okul["yeni"], YETENEKLI)
    assert all(k["tur"] != "temizlik" for k in yanit["komutlar"])
    assert temizlikler()[0]["durum"] == "zaman_asimi"


def test_temizlik_otomatik_kapatma_yoksa_yapilmaz_ve_ayarlarda_uyarir(uygulama, panel, okul, saat):
    assert "Uyarı: Otomatik kapatma kapalı" in ayarla(panel)
    assert calistir(uygulama, saat, an(16, 16, 55, 10)) == []
    assert "Otomatik kapatma kapalı ya da saati yok" in panel.get("/ayarlar/gunsonu").text


def test_temizlik_belirli_saatte_ve_hafta_sonu_yok(uygulama, panel, okul, saat):
    assert ayarla(panel, tm_zaman="saat", tm_saat="18.10") == "Oturum temizliği ayarı kaydedildi."
    assert ileti(panel.post("/ayarlar", data={"bolum": "temizlik", "tm_etkin": "1", "tm_zaman": "saat", "tm_saat": "25:00"})) \
        == "Temizlik saati SS:DD biçiminde olmalı (ör. 17:30)."  # fmt: skip
    assert ileti(panel.post("/ayarlar", data={"bolum": "temizlik", "tm_zaman": "hep"})) == "Temizlik zamanı geçersiz."
    assert calistir(uygulama, saat, an(16, 18, 10, 5)) == [kimlik(okul["yeni"])]
    assert calistir(uygulama, saat, an(21, 18, 10, 5)) == []  # cumartesi


def test_temizlik_ikili_egitimde_gun_sonu_son_devrenin_sonu(uygulama, panel, okul, saat):
    gunler = ["0", "1", "2", "3", "4"]
    sabah = {"eylem": "uret", "devre_adi": "Sabah", "ilk_ders": "07:30", "ders_sayisi": "6", "ders_dk": "40",
             "teneffus_dk": "10", "ogle_sonra": "0", "ogle_dk": "0", "gunler": gunler}  # fmt: skip
    assert zil_elle(sabah) == "Zil saatleri kaydedildi."
    assert zil_elle({**sabah, "devre_adi": "Öğleden sonra", "ilk_ders": "13:00"}) \
        == "Zil saatleri kaydedildi."  # fmt: skip
    ayarla(panel, tm_zaman="gun_sonu")
    assert calistir(uygulama, saat, an(16, 12, 30, 10)) == []  # sabah devresinin sonu (12:20 + 10) gün sonu değildir
    assert calistir(uygulama, saat, an(16, 18, 0, 10)) == [kimlik(okul["yeni"])]  # öğlenin son dersi 17:50 + 10 dk
    assert "Bugün: 18:00." in panel.get("/ayarlar/gunsonu").text


def test_temizlik_acil_surerken_ve_sinavdaki_tahtada_verilmez(uygulama, panel, okul, saat, monkeypatch):
    from tahta_sunucu import sinav

    ayarla(panel, tm_zaman="saat", tm_saat="18:00")
    saat.ayarla(an(16, 17, 50))
    yanit = panel.post("/acil/baslat", data={"tur": "tatbikat", "sablon": "", "baslik": "TATBİKAT", "metin": "Toplanınız.",
                                              "sure_dk": "30", "onay": "1", "parola": PAROLA})  # fmt: skip
    assert yanit.status_code == 303
    assert calistir(uygulama, saat, an(16, 18, 0, 5)) == [] and temizlikler() == []
    assert sorgu("SELECT * FROM kayit WHERE islem = 'Oturum temizliği acil yayın nedeniyle atlandı'")
    monkeypatch.setattr(sinav, "pencere_tahtalari", lambda b, an_, on_pay=0: {kimlik(okul["yeni"])})
    assert calistir(uygulama, saat, an(17, 18, 0, 5)) == [] and temizlikler() == []
    assert "1 tahta sınavda (atlandı)" in sorgu("SELECT * FROM kayit WHERE islem = 'Oturum temizliği'")[-1]["ayrinti"]


def test_temizlik_elle_onayli_uctan_ve_yetki(panel, tahta, okul, saat):
    yeni, eski = kimlik(okul["yeni"]), kimlik(okul["eski"])
    sayfa = panel.get(f"/tahta/{yeni}").text
    assert 'data-onay="temizlik"' in sayfa and "Henüz yapılmadı." in sayfa
    assert "Oturum temizliği için ajan güncellenmeli" in panel.get(f"/tahta/{eski}").text
    assert 'data-onay="temizlik"' not in panel.get(f"/tahta/{eski}").text
    assert ileti(panel.post(f"/tahta/{eski}/temizlik", data={"eylem": "temizle"})).startswith("Bu tahtanın ajanı oturum temizliğini bilmiyor")
    assert ileti(panel.post(f"/tahta/{yeni}/temizlik", data={})) == "Bilinmeyen işlem."
    assert ileti(panel.post(f"/tahta/{yeni}/temizlik", data={"eylem": "temizle"})).startswith("Oturum temizliği tahtaya gönderildi.")
    (k,) = temizlikler()
    assert k["olusturan"] == "yonetici" and k["tahta_id"] == yeni
    assert sorgu("SELECT * FROM kayit WHERE islem = 'Oturum temizliği'")[-1]["ayrinti"] == "elle: T-01"
    # Pano toplu işlem ucundan temizlik verilemez (yetenek denetimi yalnız tahta ucunda).
    assert ileti(panel.post("/islem", data={"tur": "temizlik", "tahta": str(eski)})) == "Oturum temizliği tahta sayfasından başlatılır."
    assert len(temizlikler()) == 1
    # Çevrimdışı tahtaya verilmez.
    saat.ilerlet(3600)
    assert ileti(panel.post(f"/tahta/{yeni}/temizlik", data={"eylem": "temizle"})).startswith("Tahta çevrimdışı")
    # Oturumsuz istek girişe gider; idareci elle verebilir; ayarı yalnız yönetici değiştirir.
    panel.cookies.clear()
    assert panel.post(f"/tahta/{yeni}/temizlik", data={"eylem": "temizle"}).headers["location"].startswith("/giris")
    gir(panel, "yonetici")
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    bekle(tahta, okul["yeni"], YETENEKLI)
    assert ileti(panel.post(f"/tahta/{yeni}/temizlik", data={"eylem": "temizle"})).startswith("Oturum temizliği tahtaya gönderildi.")
    assert ileti(panel.post("/ayarlar", data={"bolum": "temizlik", "tm_etkin": "1", "tm_zaman": "saat", "tm_saat": "18:00"})) \
        == "Bu işlem için yönetici yetkisi gerekir."  # fmt: skip
    assert sorgu("SELECT * FROM kayit WHERE islem = 'Yetkisiz işlem reddedildi' AND ayrinti = 'Ayarlar'")


def test_temizlik_sonucu_kayda_ve_tahta_sayfasina_duser(panel, tahta, okul, saat):
    yeni = kimlik(okul["yeni"])
    panel.post(f"/tahta/{yeni}/temizlik", data={"eylem": "temizle"})
    yanit = bekle(tahta, okul["yeni"], YETENEKLI)
    (komut,) = [k for k in yanit["komutlar"] if k["tur"] == "temizlik"]
    assert temizlikler()[0]["durum"] == "gonderildi"
    assert "Temizlik sürüyor ya da tahtada uyarı gösteriliyor" in panel.get(f"/tahta/{yeni}").text
    cikti = "Tamamlandı · Pencereler: 2 pencereye kapatma istendi · Tarayıcı: Firefox 1 profil, 4 çerez/oturum dosyası silindi"
    bekle(tahta, okul["yeni"], YETENEKLI, sonuclar=[{"komut_id": komut["id"], "basarili": True, "cikti": cikti}])
    assert temizlikler()[0]["durum"] == "tamam"
    assert sorgu("SELECT * FROM kayit WHERE islem = 'Oturum temizliği sonucu'")[-1]["ayrinti"] == cikti
    sayfa = panel.get(f"/tahta/{yeni}").text
    assert "Firefox 1 profil, 4 çerez/oturum dosyası silindi" in sayfa and "(elle: yonetici)" in sayfa
    assert "Temizlik sürüyor" not in sayfa


def test_temizlik_gercek_ajanla_uctan_uca(panel, tahta, okul, saat, tmp_path, monkeypatch):
    """Gerçek ajan servisi: komut iner, uyarı başlar, Vazgeç'ten sonra ertelenmiş sonuç sunucuya gider."""
    monkeypatch.setenv("TAHTA_AJAN_DIZIN", str(tmp_path / "ajan-ayar"))
    monkeypatch.setenv("TAHTA_AJAN_DURUM", str(tmp_path / "ajan-durum"))
    from tahta_ajan import servis as servis_mod

    monkeypatch.setattr(servis_mod.sistem, "etkin_oturum", lambda: {"sinif": "ogretmen", "tur": "x11"})
    monkeypatch.setattr(servis_mod.sistem, "ortak_oturum", lambda izinli=None: {"sinif": "ogretmen", "tur": "x11", "uid": 1001,
                                                                               "gid": 1001, "ev": "/home/ogretmen"})  # fmt: skip
    monkeypatch.setattr(servis_mod.sistem, "acik_sure", lambda: 60)
    monkeypatch.setattr(servis_mod.sistem, "ag_bilgisi", lambda *_: {})
    s = servis_mod.Servis()
    s.yapi = {"tahta_id": kimlik(okul["yeni"])}
    s.bildir = lambda: None
    s.ekranlar[1] = {"gonder": lambda _m: None, "bilgi": {"arayuz": "gtk3"}}
    panel.post(f"/tahta/{kimlik(okul['yeni'])}/temizlik", data={"eylem": "temizle"})
    yanit = bekle(tahta, okul["yeni"], s.durum_ozeti())
    for komut in yanit["komutlar"]:
        assert s.komut_uygula(komut) is None  # uyarı başladı; sonuç ertelendi
    assert s.durum_ozeti()["temizlik_bekliyor"] is True and s.gorunum()["temizlik"]["kalan"] > 0
    s.ekran_mesaji(1, {"tur": "temizlik_iptal"})
    sonuclar, s.sonuclar = s.sonuclar, []
    bekle(tahta, okul["yeni"], s.durum_ozeti(), sonuclar=sonuclar)
    k = temizlikler()[0]
    assert k["durum"] == "tamam" and k["sonuc"].startswith("Vazgeçildi")
