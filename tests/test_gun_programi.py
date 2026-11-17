"""Günlük program yalnız yetkili tahtaya ve kimliksiz alanlarla gider."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tahta_ajan import gun_programi
from tahta_sunucu import kilit_program, vt

AN = int(datetime(2026, 11, 17, 8, tzinfo=ZoneInfo("Europe/Istanbul")).timestamp())


@pytest.fixture
def veri(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    vt.hazirla()
    with vt.islem() as b:
        yield b


def ekle(b, sube="9/A", no=1, bas="08:00", bit="08:40", adi="Örnek Ders", gun=1):
    b.execute("INSERT INTO ogretmen_program(sube,gun,ders_no,baslangic,bitis,ders_adi,guncelleme) VALUES(?,?,?,?,?,?,?)",
              (sube, gun, no, bas, bit, adi, AN))


def test_yalniz_tahtanin_subeleri_ve_ders_alanlari(veri):
    ekle(veri)
    ekle(veri, sube="10/A")
    g = kilit_program.ajan_gorunumu(veri, {"subeler": "9/A"}, AN)
    assert len(g["dersler"]) == 1
    assert set(g["dersler"][0]) == {"sube", "ders_no", "baslangic", "bitis", "ders_adi"}
    assert g["tarih"] == "2026-11-17" and 0 < g["gecerli_sn"] <= 86400


def test_ayni_saat_secmeli_dersler_birlesir(veri):
    ekle(veri, adi="Ders A")
    ekle(veri, adi="Ders B")
    assert kilit_program.ajan_gorunumu(veri, {"subeler": "9/A"}, AN)["dersler"][0]["ders_adi"] == "Ders A / Ders B"


def test_ikili_egitim_ayni_ders_numarasi_saatle_ayrilir(veri):
    ekle(veri)
    ekle(veri, sube="10/A", bas="13:00", bit="13:40")
    dersler = kilit_program.ajan_gorunumu(veri, {"subeler": "10/A,9/A"}, AN)["dersler"]
    assert [(d["sube"], d["baslangic"]) for d in dersler] == [("9/A", "08:00"), ("10/A", "13:00")]


def test_tatil_rapordaki_dersi_gizler(veri, monkeypatch):
    ekle(veri)
    monkeypatch.setattr(kilit_program.program, "gun_plani", lambda *a: {"tatil": "Tatil"})
    assert kilit_program.ajan_gorunumu(veri, {"subeler": "9/A"}, AN)["dersler"] == []


def test_telafi_program_gunune_uyar(veri, monkeypatch):
    ekle(veri, gun=0)
    monkeypatch.setattr(kilit_program.program, "gun_plani", lambda *a: {"tatil": None, "dersler": [], "program_gunu": 0})
    assert len(kilit_program.ajan_gorunumu(veri, {"subeler": "9/A"}, AN)["dersler"]) == 1


def test_gercek_ikili_cizelgede_devre_tekil_eslesir(veri, monkeypatch):
    ekle(veri)
    ekle(veri, sube="10/A", bas="13:00", bit="13:40")
    sabah = datetime(2026, 11, 17, 8, tzinfo=ZoneInfo("Europe/Istanbul"))
    ogle = sabah.replace(hour=13)
    monkeypatch.setattr(kilit_program.program, "gun_plani", lambda *a: {"tatil": None, "program_gunu": 1,
        "dersler": [("sabah", "Sabah", 1, sabah, sabah + timedelta(minutes=35)),
                    ("ogle", "Öğle", 1, ogle, ogle + timedelta(minutes=35))]})
    dersler = kilit_program.ajan_gorunumu(veri, {"subeler": "9/A,10/A"}, AN)["dersler"]
    assert [(s["sube"], s["bitis"]) for s in dersler] == [("9/A", "08:35"), ("10/A", "13:35")]


def test_degisen_cizelgede_belirsiz_devre_eski_saati_gostermez(veri, monkeypatch):
    ekle(veri)
    bas = datetime(2026, 11, 17, 9, tzinfo=ZoneInfo("Europe/Istanbul"))
    monkeypatch.setattr(kilit_program.program, "gun_plani", lambda *a: {"tatil": None, "program_gunu": 1,
        "dersler": [("sabah", "Sabah", 1, bas, bas + timedelta(minutes=35)),
                    ("ogle", "Öğle", 1, bas.replace(hour=13), bas.replace(hour=13) + timedelta(minutes=35))]})
    g = kilit_program.ajan_gorunumu(veri, {"subeler": "9/A"}, AN)
    assert g["dersler"] == [] and "eşleştirilemedi" in g["ileti"]


def test_yalniz_program_silinince_de_wal_budamasi_istenir(veri):
    from tahta_sunucu import yoklama

    ekle(veri)
    vt.ayar_yaz(veri, "ogretim_yili_bitis", "2026-11-17")
    assert yoklama.YoklamaZamanlayici().calistir(veri, AN + 3 * 86400)
    assert veri.execute("SELECT COUNT(*) FROM ogretmen_program").fetchone()[0] == 0


def test_ajan_beklenmeyen_kisi_alanlarini_atar():
    ham = {"tarih": "2026-11-17", "dersler": [{"ders_no": 1, "sube": "9/A", "baslangic": "08:00",
            "bitis": "08:40", "ders_adi": "Örnek", "ogretmen": "Yapay Kişi", "ogrenciler": ["Yapay Öğrenci"]}],
            "ogretmenler": ["Yapay Kişi"], "ileti": ""}
    assert "Yapay" not in json.dumps(gun_programi.coz(ham), ensure_ascii=False)
    assert gun_programi.coz({"tarih": "bozuk"}) is None


def test_yil_sonu_programi_temizler_gelecek_aktarimi_korur(veri):
    from tahta_sunucu import yoklama

    ekle(veri)
    ekle(veri, sube="10/A")
    veri.execute("UPDATE ogretmen_program SET guncelleme = ? WHERE sube = '10/A'", (AN + 2 * 86400,))
    vt.ayar_yaz(veri, "ogretim_yili_bitis", "2026-11-17")
    yoklama.imha(veri, AN + 3 * 86400)
    assert [r[0] for r in veri.execute("SELECT sube FROM ogretmen_program")] == ["10/A"]


def test_kayit_ayrintisinda_usb_ve_farkli_ogretmen_bilgisi(veri):
    from tahta_sunucu import yoklama

    ilk = veri.execute("INSERT INTO ogretmen(ad,soyad) VALUES('Program','Öğretmeni')").lastrowid
    alan = veri.execute("INSERT INTO ogretmen(ad,soyad) VALUES('Nöbetçi','Öğretmen')").lastrowid
    ekle(veri)
    veri.execute("UPDATE ogretmen_program SET ogretmen_id = ?", (ilk,))
    kayit_id, _ = yoklama.yoklama_yaz(veri, tarih="2026-11-17", sube="9/A", ders_no=1, ogretmen_id=alan,
                                     kaynak="tahta", kaydeden="ogretmen:102", tahta_id=None, yok=[],
                                     kim="ogretmen:102 (tahta:Örnek) USB K7Q2M9XA", an=AN)
    g = yoklama.kayit_ayrintisi(veri, kayit_id)
    assert g["usb_kimlikleri"] == ["K7Q2-M9XA"]
    assert g["program_ogretmenleri"] == ["Program Öğretmeni"]
    assert g["program_eslesiyor"] is False and g["ogretmen"] == "Nöbetçi Öğretmen"
