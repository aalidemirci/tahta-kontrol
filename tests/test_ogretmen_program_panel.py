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
