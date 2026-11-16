"""Aşama 2 inceleme düzeltmeleri: işlem kaydı, girdi sınırları, CSV kaçışı, acil raporu, formların korunması."""

from __future__ import annotations

import json
from urllib.parse import quote

import pytest
from yardimci import (
    PAROLA,
    SAHTE_TC,
    bekle,
    gir,
    ileti,
    kimlik,
    kullanici_ekle,
    kur_ve_gir,
    plan_formu,
    sorgu,
    tahta_ekle,
    yeni_ajan_durumu,
)


@pytest.fixture()
def okul(panel, tahta):
    kur_ve_gir(panel)
    return tahta_ekle(panel, tahta, "A-01", durum=yeni_ajan_durumu()), tahta_ekle(panel, tahta, "B-02", durum=yeni_ajan_durumu())


def reddedilenler():
    return [s["ayrinti"] for s in sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yetkisiz işlem reddedildi'")]


def test_idarecinin_acil_yetkisi_ve_ayar_denemesi_kayda_duser(okul, panel):
    kullanici_ekle(panel, "idareci1")
    hedef = sorgu("SELECT id FROM kullanici WHERE ad = 'idareci1'")[0]["id"]
    gir(panel, "idareci1")
    yanit = panel.post("/kullanicilar", data={"eylem": "acil_yetki", "id": hedef})
    assert "yönetici yetkisi" in ileti(yanit)
    assert sorgu("SELECT acil_yetki FROM kullanici WHERE id = ?", hedef)[0]["acil_yetki"] == 0
    yanit = panel.post("/ayarlar", data={"bolum": "acil_sablonlari", "s_ad": "X", "s_baslik": "X", "s_metin": "x"})
    assert "yönetici yetkisi" in ileti(yanit)
    assert sorted(reddedilenler()) == ["Ayarlar", "Kullanıcı işlemi"]


def test_tc_kimlik_reddi_plan_duzenlemede_ve_acil_sablonunda_kayda_duser(okul, panel):
    panel.post("/duyurular", data=plan_formu(zaman="tekrarli", siklik="gunluk", tekrar_saat="08:00", bitis="2026-12-31"))
    plan = sorgu("SELECT id FROM duyuru_plani")[0]["id"]
    yanit = panel.post(
        f"/duyurular/plan/{plan}",
        data=plan_formu(eylem="kaydet", metin=f"No {SAHTE_TC}", zaman="tekrarli", siklik="gunluk", tekrar_saat="08:00",
                        bitis="2026-12-31"),
    )  # fmt: skip
    assert yanit.status_code == 400
    yanit = panel.post(
        "/ayarlar",
        data={"bolum": "acil_sablonlari", "eylem": "kaydet", "s_ad": ["Deprem", "Gaz"], "s_baslik": ["DEPREM", "GAZ"],
              "s_metin": ["Çök kapan tutun.", f"Numara {SAHTE_TC}"]},
    )  # fmt: skip
    assert yanit.status_code == 400
    kayitlar = sorgu("SELECT islem, ayrinti FROM kayit WHERE islem IN ('Duyuru reddedildi', 'Acil şablonu reddedildi')")
    assert {k["islem"] for k in kayitlar} == {"Duyuru reddedildi", "Acil şablonu reddedildi"}
    assert all(SAHTE_TC not in k["ayrinti"] for k in kayitlar)  # numaranın kendisi kayda yazılmaz


def test_acil_sablonu_hatasinda_duzenlemeler_korunur(okul, panel):
    yanit = panel.post(
        "/ayarlar",
        data={"bolum": "acil_sablonlari", "eylem": "kaydet", "s_ad": ["Deprem", "Gaz kaçağı"],
              "s_baslik": ["DEPREM — DİKKAT", "GAZ"], "s_metin": ["Okulun yeni metni.", ""]},
    )  # fmt: skip
    assert yanit.status_code == 400
    assert "'Gaz kaçağı' şablonunun metni boş olamaz." in ileti(yanit)
    assert 'value="Gaz kaçağı"' in yanit.text and "Okulun yeni metni." in yanit.text
    assert sorgu("SELECT deger FROM ayar WHERE anahtar = 'acil_sablonlar'") == []  # hiçbir şey yazılmadı
    # "Örnek şablonlara dön" yalnız onaylı tetikle gelir (örnek metinler kullanılırken hiç görünmez).
    assert 'data-onay="sablon_varsayilan"' not in panel.get("/ayarlar").text
    panel.post("/ayarlar", data={"bolum": "acil_sablonlari", "s_ad": "Deprem", "s_baslik": "D", "s_metin": "m"})
    assert 'data-onay="sablon_varsayilan"' in panel.get("/ayarlar").text


@pytest.mark.parametrize("deger", ["100000000000000000000", "2147483648"])
def test_hedefte_cok_buyuk_kimlik_400_doner(okul, panel, deger):
    yanit = panel.get("/api/hedef-onizleme?hedef=" + quote(json.dumps({"gruplar": [int(deger)]})))
    assert yanit.status_code == 400
    yanit = panel.post("/duyurular", data=plan_formu(kime="secim", grup=deger, zaman="hemen"))
    assert yanit.status_code == 400
    a = kimlik(okul[0])
    yanit = panel.post(f"/tahta/{a}/kaydet", data={"ad": "A-01", "eylem": "kaydet", "alanlar": "1", "grup": deger})
    assert ileti(yanit) == "Kaydedildi."
    assert panel.get(f"/duyurular/yeni?kopya={deger}").status_code == 200
    assert "Önce en az bir tahta" in ileti(panel.post("/islem", data={"tur": "kilitle", "tahta": deger}))


def test_csv_formul_kacisi_gidis_donuste_geri_alinir(okul, panel):
    from tahta_sunucu import metin

    assert metin.csv_hucre_coz("'-1 Lab") == "-1 Lab" and metin.csv_hucre_coz("'Okul") == "'Okul"
    a = kimlik(okul[0])
    panel.post(f"/tahta/{a}/kaydet", data={"ad": "-Lab", "derslik": "=A1", "eylem": "kaydet", "alanlar": "1",
                                          "bina": "+Ek bina"})  # fmt: skip
    disa = panel.get("/tahtalar.csv").content
    assert b"'-Lab;'=A1;'+Ek bina" in disa
    sayfa = panel.post("/tahtalar/ice-aktar", data={"eylem": "onizle"}, files={"dosya": ("t.csv", disa, "text/csv")}).text
    assert "0 tahta değişecek, 2 değişmiyor, 0 hatalı" in sayfa


def test_acil_raporu_sonradan_acilan_tahtayi_cevrimdisi_gosterir(okul, panel, tahta, saat):
    a, b = okul
    saat.ilerlet(3600)  # B bir saattir kapalı; A açık
    bekle(tahta, a, yeni_ajan_durumu())
    panel.post("/acil/baslat", data={"tur": "tatbikat", "metin": "Toplanma alanına gidiniz.", "sure_dk": "10",
                                     "onay": "1", "parola": PAROLA})  # fmt: skip
    acil_id = sorgu("SELECT id FROM acil_yayin")[0]["id"]
    bekle(tahta, a, yeni_ajan_durumu(acil_id=acil_id))
    rapor = panel.get(f"/acil/{acil_id}").text
    assert rapor.count("Çevrimdışıydı") == 1
    panel.post(f"/acil/{acil_id}/bitir", data={"donus": "/acil"})
    saat.ilerlet(3600)
    bekle(tahta, b, yeni_ajan_durumu())  # B sonradan açıldı
    tahta_ekle(panel, tahta, "Sonradan eklenen", durum=yeni_ajan_durumu())
    rapor = panel.get(f"/acil/{acil_id}").text
    assert rapor.count("Çevrimdışıydı") == 1 and "Sonradan eklenen" not in rapor


def test_acil_formu_hatali_parolada_korunur_parola_ve_onay_bos(okul, panel):
    yanit = panel.post("/acil/baslat", data={"tur": "tatbikat", "sablon": "tahliye", "baslik": "TAHLİYE",
                                             "metin": "Düzeltilmiş özel metin.", "sure_dk": "45", "onay": "1",
                                             "parola": "yanlis-parola"})  # fmt: skip
    assert yanit.status_code == 400 and ileti(yanit) == "Parola hatalı; yayın başlatılmadı."
    s = yanit.text
    assert 'value="tatbikat" required checked' in s and 'value="tahliye"' in s and "Düzeltilmiş özel metin." in s
    assert 'value="45"' in s and "yanlis-parola" not in s and 'name="onay" value="1" required>' in s
    assert 'id="acil-metin-kvkk"' in s  # KVKK notu sayaçtan ayrı, kalıcı


def test_bos_tarih_alana_ozgu_ileti(okul, panel):
    yanit = panel.post("/duyurular", data=plan_formu(zaman="bir_kez", bir_tarih="", bir_saat="10:00"))
    assert "Duyurunun tarihini seçin." in yanit.text
    yanit = panel.post("/duyurular", data=plan_formu(zaman="tekrarli", siklik="gunluk", tekrar_saat="08:00", bitis=""))
    assert "Bitiş tarihini seçin." in yanit.text


def test_ekran_acil_basligi_bant_sozcugunu_tekrarlamaz_ve_uzun_metin_kuculur():
    from tahta_ajan import ekran

    assert ekran.acil_basligi("ACİL DURUM", False) == "" and ekran.acil_basligi("acil durum", False) == ""
    assert ekran.acil_basligi("TATBİKAT", True) == "" and ekran.acil_basligi("", False) == ""
    assert ekran.acil_basligi("TAHLİYE", False) == "TAHLİYE"
    assert [ekran.acil_metin_sinifi("x" * n) for n in (10, 300, 301, 600, 601, 1000)] == [
        "", "", "uzun", "uzun", "cok-uzun", "cok-uzun"
    ]  # fmt: skip
    assert b"#acil-metin.cok-uzun" in ekran.STIL_OLCU
