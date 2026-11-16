"""Duyuru: tek yayın yolu, planlar, zamanlayıcı, kaçırma kuralı, durdurma, yetki."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from yardimci import (
    SAHTE_TC,
    TZ,
    an,
    bekle,
    gir,
    ileti,
    kimlik,
    kullanici_ekle,
    kur_ve_gir,
    plan_formu,
    sorgu,
    tahta_ekle,
)


@pytest.fixture()
def okul(panel, tahta):
    kur_ve_gir(panel)
    return tahta_ekle(panel, tahta, "11-A", durum={"kilitli": False, "yetenekler": ["acil", "duyuru_id"]})


def calistir(panel, saat, zaman) -> int:
    saat.ayarla(zaman)
    return panel.app.state.duyuru_zamanlayici(zaman)


def plan_kur(panel, **alanlar) -> int:
    yanit = panel.post("/duyurular", data=plan_formu(**alanlar))
    assert yanit.status_code == 303 and "t=hata" not in yanit.headers["location"], yanit.text[:3000]
    return sorgu("SELECT MAX(id) AS id FROM duyuru_plani")[0]["id"]


def yayinlar(plan_id=None):
    if plan_id is None:
        return sorgu("SELECT * FROM duyuru ORDER BY id")
    return sorgu("SELECT * FROM duyuru WHERE plan_id = ? ORDER BY an", plan_id)


# ---- tek yayın yolu ----------------------------------------------------------------------
def test_hemen_duyuru_eski_pano_akisiyla_calisir_ve_duyuru_id_tasir(okul, panel, tahta):
    yanit = panel.post("/islem", data={"tur": "duyuru", "tahta": kimlik(okul), "metin": "Tören 10.00'da.", "sure_dk": "3"})
    assert ileti(yanit) == "Duyuru: 1 tahtaya gönderildi."
    yayin = yayinlar()[0]
    assert (yayin["durum"], yayin["tahta_sayisi"], yayin["hedef"]) == ("gonderildi", 1, "11-A")
    komut = bekle(tahta, okul)["komutlar"][0]
    assert komut["tur"] == "duyuru" and komut["veri"]["duyuru_id"] == yayin["id"]
    assert komut["veri"]["sure_sn"] == 180 and "bitis_sunucu" not in komut["veri"]
    assert sorgu("SELECT duyuru_id FROM komut")[0]["duyuru_id"] == yayin["id"]
    assert "Tören 10.00" in panel.get("/duyurular").text


def test_komut_ekle_duyuru_omru_ister(uygulama):
    from tahta_sunucu import komut, vt

    with vt.islem() as b, pytest.raises(ValueError, match="ömür"):
        komut.komut_ekle(b, 1, "duyuru", {}, "x")


# ---- plan zamanlayıcısı ------------------------------------------------------------------
def test_bir_kezlik_plan_zamaninda_bir_kez_yayimlanir_ve_biter(okul, panel, saat):
    plan_id = plan_kur(panel, zaman="bir_kez", bir_tarih="2026-11-16", bir_saat="10.00", sure_dk="10")
    assert calistir(panel, saat, an(16, 9, 59)) == 0
    assert calistir(panel, saat, an(16, 10, 0, 5)) == 1
    assert calistir(panel, saat, an(16, 10, 0, 25)) == 0
    assert [y["an"] for y in yayinlar(plan_id)] == [int(an(16, 10).timestamp())]
    assert sorgu("SELECT durum FROM duyuru_plani")[0]["durum"] == "bitti"
    assert "plan #" in sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Zamanlanmış duyuru'")[0]["ayrinti"]


def test_gunluk_plan_hafta_sonunu_atlar(okul, panel, saat):
    plan_id = plan_kur(panel, zaman="tekrarli", siklik="gunluk", tekrar_saat="08:25", baslangic="2026-11-17", bitis="2027-06-18")
    for gun in range(17, 24):  # salı → pazartesi
        calistir(panel, saat, an(gun, 8, 25, 30))
    gunler = [datetime.fromtimestamp(y["an"], TZ).weekday() for y in yayinlar(plan_id)]
    assert gunler == [1, 2, 3, 4, 0]
    # Hafta sonu dâhil plan
    saat.ayarla(an(20, 9))
    gir(panel, "yonetici")
    plan_kur(panel, zaman="tekrarli", siklik="gunluk", hafta_sonu="1", tekrar_saat="12:00",
             baslangic="2026-11-21", bitis="2026-11-22")  # fmt: skip
    assert calistir(panel, saat, an(21, 12, 0, 10)) == 1 and calistir(panel, saat, an(22, 12, 0, 10)) == 1


def test_haftalik_plan_yalniz_secili_gunlerde(okul, panel, saat):
    plan_id = plan_kur(panel, zaman="tekrarli", siklik="haftalik", gun=["0", "3"], tekrar_saat="13:00",
                       baslangic="2026-11-16", bitis="2026-12-31")  # fmt: skip
    sonuc = [calistir(panel, saat, an(gun, 13, 1)) for gun in range(16, 23)]
    assert sonuc == [1, 0, 0, 1, 0, 0, 0]
    assert len(yayinlar(plan_id)) == 2


def test_sunucu_kapaliyken_sure_icinde_kalan_sureyle_gonderilir(okul, panel, tahta, saat):
    plan_id = plan_kur(panel, zaman="bir_kez", bir_tarih="2026-11-16", bir_saat="10:40", sure_dk="10")
    assert calistir(panel, saat, an(16, 10, 44)) == 1  # sunucu 10:44'te açıldı
    komut = bekle(tahta, okul)["komutlar"][0]
    assert komut["veri"]["sure_sn"] == 360
    assert yayinlar(plan_id)[0]["durum"] == "gonderildi"


def test_sure_gectiyse_kacirildi_yazilir_ve_bir_daha_gonderilmez(okul, panel, tahta, saat):
    plan_id = plan_kur(panel, zaman="bir_kez", bir_tarih="2026-11-16", bir_saat="10:40", sure_dk="10")
    assert calistir(panel, saat, an(16, 10, 55)) == 0
    assert calistir(panel, saat, an(16, 10, 56)) == 0
    satirlar = yayinlar(plan_id)
    assert [(y["durum"], y["tahta_sayisi"]) for y in satirlar] == [("kacirildi", 0)]
    assert sorgu("SELECT COUNT(*) AS n FROM komut")[0]["n"] == 0
    assert bekle(tahta, okul)["komutlar"] == []
    assert len(sorgu("SELECT * FROM kayit WHERE islem = 'Zamanlanmış duyuru kaçırıldı'")) == 1
    sayfa = panel.get("/").text
    assert "Sunucu kapalıyken 1 zamanlanmış duyuru kaçırıldı." in sayfa
    assert "Kaçırıldı — sunucu kapalıydı" in panel.get("/duyurular").text


def test_olusturma_oncesi_an_kacirildi_sayilmaz(okul, panel, saat):
    saat.ayarla(an(16, 10, 5))
    plan_id = plan_kur(panel, zaman="tekrarli", siklik="gunluk", tekrar_saat="10:00", baslangic="2026-11-16", bitis="2026-11-20")
    assert calistir(panel, saat, an(16, 10, 6)) == 0
    assert yayinlar(plan_id) == []
    assert calistir(panel, saat, an(17, 10, 0, 10)) == 1


def test_duraklatilan_plan_surdurulunce_aradakiler_sayilmaz(okul, panel, saat):
    plan_id = plan_kur(panel, zaman="tekrarli", siklik="gunluk", tekrar_saat="08:25", baslangic="2026-11-16", bitis="2026-12-31")
    assert "duraklatıldı" in ileti(panel.post(f"/duyurular/plan/{plan_id}", data={"eylem": "duraklat"}))
    calistir(panel, saat, an(17, 8, 26))
    assert yayinlar(plan_id) == []
    saat.ayarla(an(18, 9, 0))
    gir(panel, "yonetici")
    panel.post(f"/duyurular/plan/{plan_id}", data={"eylem": "surdur"})
    assert calistir(panel, saat, an(18, 9, 0, 30)) == 0
    assert yayinlar(plan_id) == []  # 17 ve 18'i ne yayımlandı ne kaçırıldı
    assert calistir(panel, saat, an(19, 8, 25, 20)) == 1


def test_yedi_gunden_eski_kacirma_raporlanmaz_tek_kesinti_kaydi(okul, panel, saat):
    from tahta_sunucu import vt, zamanlama

    plan_id = plan_kur(panel, zaman="tekrarli", siklik="gunluk", tekrar_saat="08:25", baslangic="2026-11-16", bitis="2026-12-31")
    calistir(panel, saat, an(16, 9, 1))
    simdi = an(30, 9, 0)
    calistir(panel, saat, simdi)
    with vt.islem() as b:
        plan = b.execute("SELECT * FROM duyuru_plani WHERE id = ?", (plan_id,)).fetchone()
    beklenen = zamanlama.anlar(plan, simdi - timedelta(days=7), simdi)
    assert [y["an"] for y in yayinlar(plan_id)] == beklenen and len(beklenen) == 5
    assert {y["durum"] for y in yayinlar(plan_id)} == {"kacirildi"}
    assert len(sorgu("SELECT * FROM kayit WHERE islem = 'Zamanlanmış duyurular: uzun kesinti'")) == 1
    calistir(panel, saat, an(30, 9, 1))
    assert len(sorgu("SELECT * FROM kayit WHERE islem = 'Zamanlanmış duyurular: uzun kesinti'")) == 1


def test_yayin_durdurulunca_bekleyen_komutlar_iptal_ve_kaldir_komutu(okul, panel, tahta):
    ikinci = tahta_ekle(panel, tahta, "11-B")
    panel.post("/islem", data={"tur": "duyuru", "tahta": [kimlik(okul), kimlik(ikinci)], "metin": "Toplantı", "sure_dk": "30"})
    bekle(tahta, okul)  # birinci tahta aldı; ikinci çevrimdışı
    yayin = yayinlar()[0]
    yanit = panel.post(f"/duyurular/yayin/{yayin['id']}/durdur")
    assert ileti(yanit) == "Duyuru durduruldu."
    assert sorgu("SELECT durum, durduran FROM duyuru")[0] == {"durum": "durduruldu", "durduran": "yonetici"}
    durumlar = {s["tahta_id"]: s["durum"] for s in sorgu("SELECT tahta_id, durum FROM komut WHERE tur = 'duyuru'")}
    assert durumlar == {kimlik(okul): "gonderildi", kimlik(ikinci): "iptal"}
    assert bekle(tahta, ikinci)["komutlar"] == []
    kaldir = bekle(tahta, okul)["komutlar"]
    assert [(k["tur"], k["veri"]) for k in kaldir] == [("duyuru_kaldir", {"duyuru_id": yayin["id"]})]
    assert "t=hata" in panel.post(f"/duyurular/yayin/{yayin['id']}/durdur").headers["location"]


def test_cevrimdisi_tahta_sure_icinde_gelince_kalan_sureyle_alir(okul, panel, tahta, saat):
    plan_kur(panel, zaman="bir_kez", bir_tarih="2026-11-16", bir_saat="10:00", sure_dk="10")
    calistir(panel, saat, an(16, 10, 0, 10))
    saat.ayarla(an(16, 10, 4))
    assert bekle(tahta, okul)["komutlar"][0]["veri"]["sure_sn"] == 360
    # Süre bittikten sonra gelen başka tahta almaz.
    panel.post("/duyurular", data=plan_formu(zaman="bir_kez", bir_tarih="2026-11-16", bir_saat="11:00", sure_dk="1"))
    calistir(panel, saat, an(16, 11, 0, 5))
    saat.ayarla(an(16, 11, 2))
    assert bekle(tahta, okul)["komutlar"] == []
    assert sorgu("SELECT durum FROM komut ORDER BY id DESC LIMIT 1")[0]["durum"] == "zaman_asimi"


def test_hedefsiz_yayin_kaydedilir_komut_uretmez(okul, panel, saat):
    yanit = panel.post(
        "/duyurular",
        data=plan_formu(kime="secim", bina="Olmayan Blok", zaman="bir_kez", bir_tarih="2026-11-16", bir_saat="10:00"),
    )
    assert "hiçbir tahtaya ulaşmıyor" in ileti(yanit)
    calistir(panel, saat, an(16, 10, 0, 5))
    assert [(y["durum"], y["tahta_sayisi"]) for y in yayinlar()] == [("hedefsiz", 0)]
    assert sorgu("SELECT COUNT(*) AS n FROM komut")[0]["n"] == 0
    # Hemen gönderimde 0 tahta reddedilir.
    yanit = panel.post("/duyurular", data=plan_formu(kime="secim", bina="Olmayan Blok", zaman="hemen"))
    assert yanit.status_code == 400 and "hiçbir tahtaya ulaşmıyor" in yanit.text


@pytest.mark.parametrize(
    ("alanlar", "ileti_"),
    [
        ({"zaman": "bir_kez", "bir_tarih": "2026-11-16", "bir_saat": "08:00"}, "Duyuru zamanı geçmişte olamaz."),
        ({"zaman": "bir_kez", "bir_tarih": "2027-12-01", "bir_saat": "08:00"}, "En çok bir yıl sonrası planlanabilir."),
        ({"zaman": "tekrarli", "siklik": "gunluk", "tekrar_saat": "08:00", "baslangic": "2026-12-01", "bitis": "2026-11-30"},
         "Bitiş tarihi başlangıçtan önce olamaz."),
        ({"zaman": "tekrarli", "siklik": "gunluk", "tekrar_saat": "08:00", "baslangic": "2026-11-16", "bitis": "2027-11-30"},
         "Tekrarlı duyuru en çok bir yıl sürebilir."),
        ({"zaman": "tekrarli", "siklik": "haftalik", "tekrar_saat": "08:00", "bitis": "2026-12-30"},
         "Haftalık duyuru için en az bir gün seçin."),
        ({"metin": "  "}, "Duyuru metni boş olamaz."),
        ({"sure_dk": "0"}, "Süre 1-240 dakika olmalı."),
        ({"kime": "secim"}, "Duyurunun hangi tahtalara gideceğini seçin."),
        ({"zaman": "tekrarli", "siklik": "gunluk", "tekrar_saat": "25:00", "bitis": "2026-12-30"}, "Saat SS:DD"),
    ],
)  # fmt: skip
def test_plan_formu_gecersiz_girdileri_reddeder(okul, panel, alanlar, ileti_):
    yanit = panel.post("/duyurular", data=plan_formu(**alanlar))
    assert yanit.status_code == 400 and ileti_ in yanit.text
    assert sorgu("SELECT COUNT(*) AS n FROM duyuru_plani")[0]["n"] == 0
    # Form alanları korunur.
    if "metin" not in alanlar:
        assert "Ders başlamadan telefonlarınızı kapatınız." in yanit.text


def test_tc_kimlik_numarasi_iceren_duyuru_reddedilir(okul, panel):
    yanit = panel.post("/duyurular", data=plan_formu(metin=f"No: {SAHTE_TC}"))
    assert yanit.status_code == 400 and "T.C. kimlik numarasına benzeyen" in yanit.text
    yanit = panel.post("/islem", data={"tur": "duyuru", "tahta": kimlik(okul), "metin": f"{SAHTE_TC}"})
    assert "T.C." in ileti(yanit) and yayinlar() == []
    assert len(sorgu("SELECT * FROM kayit WHERE islem = 'Duyuru reddedildi'")) == 2
    # Denetim hanesi tutmayan 11 hane kabul edilir.
    yanit = panel.post("/duyurular", data=plan_formu(metin="Santral 12345678951"))
    assert yanit.status_code == 303 and len(yayinlar()) == 1


def test_idareci_baskasinin_planini_degistiremez_yonetici_degistirir(okul, panel, saat):
    plan_yon = plan_kur(panel, zaman="tekrarli", siklik="gunluk", tekrar_saat="08:25", bitis="2026-12-31")
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    for eylem in ("duraklat", "sil"):
        yanit = panel.post(f"/duyurular/plan/{plan_yon}", data={"eylem": eylem})
        assert "yalnız oluşturan ya da yönetici" in ileti(yanit)
    yanit = panel.post(f"/duyurular/plan/{plan_yon}", data=plan_formu(eylem="kaydet", zaman="tekrarli", siklik="gunluk",
                                                                      tekrar_saat="09:00", bitis="2026-12-31"))  # fmt: skip
    assert "yalnız oluşturan" in ileti(yanit)
    assert "kullanıcısına ait" in panel.get(f"/duyurular/plan/{plan_yon}").text
    assert sorgu("SELECT durum, saat FROM duyuru_plani WHERE id = ?", plan_yon)[0] == {"durum": "etkin", "saat": "08:25"}
    assert len(sorgu("SELECT * FROM kayit WHERE islem = 'Yetkisiz işlem reddedildi'")) == 3
    plan_ida = plan_kur(panel, zaman="tekrarli", siklik="gunluk", tekrar_saat="10:00", bitis="2026-12-31")
    assert ileti(panel.post(f"/duyurular/plan/{plan_ida}", data={"eylem": "duraklat"})).startswith("Plan duraklatıldı")
    gir(panel, "yonetici")
    yanit = panel.post(f"/duyurular/plan/{plan_ida}", data=plan_formu(eylem="kaydet", zaman="tekrarli", siklik="gunluk",
                                                                      tekrar_saat="11:00", bitis="2026-12-31"))  # fmt: skip
    assert ileti(yanit).startswith("Plan kaydedildi.")
    satir = sorgu("SELECT * FROM duyuru_plani WHERE id = ?", plan_ida)[0]
    assert (satir["saat"], satir["guncelleyen"], satir["durum"]) == ("11:00", "yonetici", "duraklatildi")
    assert "Yalnız oluşturan" not in panel.get("/duyurular").text
    yanit = panel.post(f"/duyurular/plan/{plan_ida}", data={"eylem": "sil"})
    assert sorgu("SELECT durum FROM duyuru_plani WHERE id = ?", plan_ida)[0]["durum"] == "silindi"


def test_kacirilan_yayin_yeniden_gonderilir(okul, panel, tahta, saat):
    plan_kur(panel, zaman="bir_kez", bir_tarih="2026-11-16", bir_saat="10:00", sure_dk="5")
    calistir(panel, saat, an(16, 10, 30))
    kacan = yayinlar()[0]
    assert kacan["durum"] == "kacirildi"
    assert "Yeniden gönder" in panel.get("/duyurular").text
    form = panel.get(f"/duyurular/yeni?yayin={kacan['id']}").text
    assert "Ders başlamadan telefonlarınızı kapatınız." in form
    yanit = panel.post(f"/duyurular/yayin/{kacan['id']}/yeniden")
    assert ileti(yanit) == "Duyuru yeniden gönderildi: 1 tahta."
    yeni = yayinlar()[-1]
    assert (yeni["durum"], yeni["an"], yeni["sure_sn"], yeni["plan_id"]) == ("gonderildi", saat.t, 300, None)
    assert bekle(tahta, okul)["komutlar"][0]["veri"]["sure_sn"] == 300
    # Gönderilmiş yayın yeniden gönderilmez.
    assert "t=hata" in panel.post(f"/duyurular/yayin/{yeni['id']}/yeniden").headers["location"]


def test_plan_sayfalari_ve_cogaltma(okul, panel):
    plan_id = plan_kur(panel, zaman="tekrarli", siklik="haftalik", gun=["0", "3"], tekrar_saat="13:00", bitis="2026-12-31",
                       kime="secim", hedef_tahta=str(kimlik(okul)))  # fmt: skip
    liste = panel.get("/duyurular").text
    assert "Her hafta Pzt, Per 13:00 · 16.11.2026–31.12.2026" in liste and "16.11.2026 13:00" in liste
    kopya = panel.get(f"/duyurular/yeni?kopya={plan_id}").text
    assert 'name="gun" value="3" checked' in kopya and f'name="hedef_tahta" value="{kimlik(okul)}" checked' in kopya
    duzen = panel.get(f"/duyurular/plan/{plan_id}").text
    assert f'action="/duyurular/plan/{plan_id}"' in duzen and 'value="hemen"' not in duzen
    yanit = panel.post(f"/duyurular/plan/{plan_id}", data=plan_formu(eylem="kaydet", zaman="hemen"))
    assert yanit.status_code == 400 and "Hemen" in yanit.text
