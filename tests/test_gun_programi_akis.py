"""Sunucudan ajana günlük program; şube ve yetenek süzgeci."""

from __future__ import annotations

from yardimci import bekle, kur_ve_gir, tahta_ekle

from tahta_sunucu import vt


def test_program_yalniz_yetenekli_tahtaya_kisi_bilgisi_olmadan_iner(panel, tahta):
    kur_ve_gir(panel)
    with vt.islem() as b:
        ogretmen = b.execute("INSERT INTO ogretmen(ad,soyad) VALUES('Gönderilmeyen','Öğretmen')").lastrowid
        b.execute("INSERT INTO ogretmen_program(sube,gun,ders_no,baslangic,bitis,ders_adi,ogretmen_id,guncelleme) "
                  "VALUES('9/A',0,1,'08:00','08:40','Yapay Ders',?,?)", (ogretmen, vt.simdi()))
    durum = {"kilitli": False, "yetenekler": ["gun_programi"]}
    basliklar = tahta_ekle(panel, tahta, "Örnek Tahta", durum=durum, subeler="9/A")
    g = bekle(tahta, basliklar, durum)["ayar"]["gun_programi"]
    assert len(g["dersler"]) == 1 and g["dersler"][0]["ders_adi"] == "Yapay Ders"
    assert "Gönderilmeyen" not in str(g) and "ogretmen_id" not in str(g)
    eski = bekle(tahta, basliklar, {"kilitli": False, "yetenekler": []})
    assert "gun_programi" not in eski["ayar"]
