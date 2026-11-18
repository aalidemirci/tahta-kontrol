"""Uydurma programla yetki, önizleme ve tek kullanımlı onay."""

from __future__ import annotations

import re

from test_ogretmen_program import matris
from yardimci import gir, ileti, kullanici_ekle, kur_ve_gir, sorgu

from tahta_sunucu import eokul_program, vt


def kur(panel, monkeypatch):
    kur_ve_gir(panel)
    monkeypatch.setattr(eokul_program, "matris_oku", lambda _: matris())
    with vt.islem() as b:
        b.execute("INSERT INTO ogretmen (id, ad, soyad) VALUES (1, 'Örnek', 'Öğretmen')")
        b.execute("INSERT INTO ogretmen (id, ad, soyad) VALUES (2, 'Diğer', 'Öğretmen')")


def yukle(panel):
    return panel.post("/ogretmen-programi/onizle", files={"program": ("uydurma.xls", b"uydurma")},
                      data={"subeler": "9/A,9/B"})


def test_onizleme_yazmaz_onay_yazar_ve_belirtec_ikinci_kez_kullanilmaz(panel, monkeypatch):
    kur(panel, monkeypatch)
    yanit = yukle(panel)
    assert yanit.status_code == 200 and "no-store" in yanit.headers["cache-control"]
    assert "Örnek Öğretmen" in yanit.text
    assert sorgu("SELECT COUNT(*) AS n FROM ogretmen_program")[0]["n"] == 0
    belirtec = re.search(r'name="belirtec" value="([^"]+)"', yanit.text)
    assert belirtec, yanit.text
    form = {"belirtec": belirtec[1], "onay": "1", "ogretmensiz_onay": "1", "esle_0": "2", "esle_1": "1"}
    yanit = panel.post("/ogretmen-programi/uygula", data=form)
    assert yanit.status_code == 303 and "4 ders" in ileti(yanit)
    assert sorgu("SELECT COUNT(*) AS n FROM ogretmen_program")[0]["n"] == 4
    yanit = panel.post("/ogretmen-programi/uygula", data=form)
    assert "daha önce kullanılmış" in ileti(yanit)
    kayit = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Öğretmen programı aktarıldı'")[0]["ayrinti"]
    assert "Örnek" not in kayit and "Öğretmen" not in kayit
    assert "Matematik" in panel.get("/ogretmen-programi").text


def test_onay_yoksa_eski_program_korunur_ve_onizleme_yeniden_verilir(panel, monkeypatch):
    kur(panel, monkeypatch)
    with vt.islem() as b:
        b.execute("INSERT INTO ogretmen_program "
                  "(sube,gun,ders_no,baslangic,bitis,ders_adi,ogretmen_id,guncelleme) "
                  "VALUES ('10/A',0,1,'08:00','08:40','Eski Ders',1,?)", (vt.simdi(),))
    yanit = yukle(panel)
    belirtec = re.search(r'name="belirtec" value="([^"]+)"', yanit.text)[1]
    yanit = panel.post("/ogretmen-programi/uygula", data={"belirtec": belirtec})
    assert yanit.status_code == 200 and "değişeceğini onaylayın" in yanit.text
    yeni = re.search(r'name="belirtec" value="([^"]+)"', yanit.text)[1]
    assert yeni != belirtec
    assert sorgu("SELECT ders_adi FROM ogretmen_program") == [{"ders_adi": "Eski Ders"}]


def test_idareci_aktarim_yapamaz_oturumsuz_giris_ister(panel, monkeypatch):
    assert panel.get("/ogretmen-programi").headers["location"] == "/giris"
    kur(panel, monkeypatch)
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    yanit = yukle(panel)
    assert yanit.status_code == 303 and "yönetici" in ileti(yanit)
    assert sorgu("SELECT COUNT(*) AS n FROM ogretmen_program")[0]["n"] == 0


def test_vazgec_onizlemeyi_bellekten_siler(panel, monkeypatch):
    kur(panel, monkeypatch)
    depo = panel.app.state.ogretmen_program_onizleme
    yanit = yukle(panel)
    assert '/ogretmen-programi/vazgec' in yanit.text and len(depo.kayitlar) == 1
    belirtec = re.search(r'name="belirtec" value="([^"]+)"', yanit.text)[1]
    yanit = panel.post("/ogretmen-programi/vazgec", data={"belirtec": belirtec})
    assert yanit.status_code == 303 and "vazgeçildi" in ileti(yanit)
    assert depo.kayitlar == {}
    yanit = panel.post("/ogretmen-programi/uygula", data={"belirtec": belirtec, "onay": "1"})
    assert "daha önce kullanılmış" in ileti(yanit)


def test_suresi_dolan_onizleme_zamanlayicida_silinir(panel, monkeypatch):
    from tahta_sunucu import yoklama

    kur(panel, monkeypatch)
    depo = panel.app.state.ogretmen_program_onizleme
    yukle(panel)
    isler = dict(panel.app.state.zamanlayicilar)
    isler["ogretmen_program_onizleme"]()
    assert len(depo.kayitlar) == 1  # süresi dolmadan silinmez
    gercek = yoklama.time.monotonic
    monkeypatch.setattr(yoklama.time, "monotonic", lambda: gercek() + yoklama.ONIZLEME_OMRU_SN + 1)
    isler["ogretmen_program_onizleme"]()
    assert depo.kayitlar == {}


def test_onizleme_belirsiz_hucreyi_ve_ayni_adi_uyarir(panel, monkeypatch):
    kur(panel, monkeypatch)
    m = matris()
    m[1][2] = "Seçmeli\nÖrnek Öğretmen - Sanat  Örnek Öğretmen - Müzik"
    m[2][3] = "Seçmeli\nYapay Birinci - Sanat Uydurma İkinci - Müzik"
    monkeypatch.setattr(eokul_program, "matris_oku", lambda _: m)
    yanit = yukle(panel)
    assert "kişi ile ders adı ayrılamadı" in yanit.text
    assert "aynı adlı iki öğretmen olabilir" in yanit.text
    assert "Uydurma" not in yanit.text and "Yapay" not in yanit.text


def test_ajan_yanitinda_gun_programi_anahtari_var_program_yokken_degeri_bos(panel, tahta):
    from yardimci import bekle, tahta_ekle

    kur_ve_gir(panel)
    durum = {"kilitli": False, "yetenekler": ["acil", "gun_programi"]}
    basliklar = tahta_ekle(panel, tahta, "T-01", durum)
    ayar = bekle(tahta, basliklar, durum)["ayar"]
    assert "gun_programi" in ayar and ayar["gun_programi"] is None
    with vt.islem() as b:
        b.execute("UPDATE tahta SET subeler = '9/A'")
        b.execute("INSERT INTO ogretmen_program (sube,gun,ders_no,baslangic,bitis,ders_adi,guncelleme) "
                  "VALUES ('9/A',0,1,'08:00','08:40','Örnek Ders',?)", (vt.simdi(),))
    assert isinstance(bekle(tahta, basliklar, durum)["ayar"]["gun_programi"], dict)
    eski = bekle(tahta, basliklar, {"kilitli": False, "yetenekler": ["acil"]})["ayar"]
    assert "gun_programi" not in eski
