"""Aşama 2 göçü ve göç öncesi kopya."""

from __future__ import annotations

import os
import sqlite3
import time

import pytest


def eski_veritabani(dizin):
    from tahta_sunucu import vt

    yol = dizin / "tahta-kontrol.db"
    b = sqlite3.connect(yol)
    b.executescript(vt.GOCLER[0])
    b.execute("PRAGMA user_version = 1")
    b.execute("INSERT INTO kullanici (ad, gorunen_ad, parola_ozet, rol, olusturma) VALUES ('yonetici', 'Y', 'x', 'yonetici', 1)")
    b.execute("INSERT INTO kullanici (ad, gorunen_ad, parola_ozet, rol, olusturma) VALUES ('idareci', 'I', 'x', 'idareci', 1)")
    b.execute(
        "INSERT INTO duyuru (baslik, metin, sure_sn, kapatilabilir, hedef, olusturan, olusturma) "
        "VALUES ('', 'Eski duyuru', 300, 1, 'Tahta', 'yonetici', 1000)"
    )
    b.commit()
    b.close()
    return yol


def test_goc_eski_veritabanini_yukseltir(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    from tahta_sunucu import vt

    eski_veritabani(tmp_path)
    vt.hazirla()
    with vt.islem() as b:
        assert b.execute("PRAGMA user_version").fetchone()[0] == len(vt.GOCLER) == 2
        sutunlar = {s["name"] for s in b.execute("PRAGMA table_info(tahta)")}
        assert {"bina", "kat", "duzeyler", "devre", "subeler"} <= sutunlar
        yetki = {s["ad"]: s["acil_yetki"] for s in b.execute("SELECT ad, acil_yetki FROM kullanici")}
        assert yetki == {"yonetici": 1, "idareci": 0}
        duyuru = b.execute("SELECT * FROM duyuru").fetchone()
        assert (duyuru["an"], duyuru["bitis"], duyuru["durum"]) == (1000, 1300, "gonderildi")
        for tablo in ("tahta_grubu", "tahta_grubu_uye", "duyuru_plani", "acil_yayin", "acil_teslim"):
            assert b.execute(f"SELECT COUNT(*) FROM {tablo}").fetchone()[0] == 0
    vt.hazirla()  # ikinci kez çalışmak bir şey değiştirmez


def test_goc_oncesi_kopya_alinir_ve_uc_tane_kalir(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    from tahta_sunucu import vt

    eski_veritabani(tmp_path)
    kopyalar = tmp_path / "goc-oncesi"
    kopyalar.mkdir()
    for sira in range(4):  # eski kopyalar
        eski = kopyalar / f"tahta-kontrol-v1-0{sira}.01.2026-000000.db"
        eski.write_bytes(b"eski")
        os.utime(eski, (time.time() - 1000 + sira, time.time() - 1000 + sira))
    vt.hazirla()
    kalan = sorted(p.name for p in kopyalar.iterdir())
    assert len(kalan) == 3
    yeni = [p for p in kopyalar.iterdir() if p.read_bytes()[:15] == b"SQLite format 3"]
    assert len(yeni) == 1 and yeni[0].name.startswith("tahta-kontrol-v1-")
    b = sqlite3.connect(yeni[0])
    assert b.execute("PRAGMA user_version").fetchone()[0] == 1  # kopya göçten öncedir
    b.close()


def test_kopya_alinamazsa_goc_yapilmaz(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    from tahta_sunucu import vt

    yol = eski_veritabani(tmp_path)
    (tmp_path / "goc-oncesi").write_text("klasör değil")  # klasör oluşturulamasın
    with pytest.raises(RuntimeError, match="kopya"):
        vt.hazirla()
    b = sqlite3.connect(yol)
    assert b.execute("PRAGMA user_version").fetchone()[0] == 1
    b.close()


def test_yeni_veritabaninda_kopya_alinmaz(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    from tahta_sunucu import vt

    vt.hazirla()
    assert not (tmp_path / "goc-oncesi").exists()
