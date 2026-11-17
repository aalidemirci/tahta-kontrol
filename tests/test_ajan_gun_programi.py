"""Günlük dersler servis belleğinde; durum dosyası ve tanılamaya girmez."""

from __future__ import annotations

import json

import pytest


@pytest.fixture
def servis(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_AJAN_DIZIN", str(tmp_path / "ayar"))
    monkeypatch.setenv("TAHTA_AJAN_DURUM", str(tmp_path / "durum"))
    from tahta_ajan import ayar
    from tahta_ajan import servis as servis_mod

    monkeypatch.setattr(servis_mod.sistem, "etkin_oturum", lambda: {"sinif": "ogretmen", "tur": "x11"})
    ayar.yaz({"sunucu": "https://ornek.invalid:8788", "tahta_id": 7, "anahtar": "uydurma"})
    return servis_mod.Servis(), servis_mod, ayar


def program():
    return {"tarih": "2026-11-17", "dersler": [{"ders_no": 1, "baslangic": "08:00", "bitis": "08:40",
            "sube": "9/A", "ders_adi": "Yapay Ders", "ogretmen": "Gönderilmeyecek Kişi"}], "gecerli_sn": 120}


def test_program_kisi_alanlari_ayiklanir_ve_diske_yazilmaz(servis):
    s, _, ayar = servis
    s._yanit_isle({"ayar": {"gun_programi": program()}})
    assert s.gorunum()["gun_programi"]["dersler"][0]["ders_adi"] == "Yapay Ders"
    assert "Gönderilmeyecek" not in json.dumps(s.gorunum(), ensure_ascii=False)
    assert "gun_programi" not in s.durum_ozeti()
    assert "Yapay Ders" not in json.dumps(ayar.durum_oku(), ensure_ascii=False)


def test_gece_yarisi_suresinde_program_kalkar(servis, monkeypatch):
    s, mod, _ = servis
    saat = [100.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: saat[0])
    s._yanit_isle({"ayar": {"gun_programi": program()}})
    saat[0] += 121
    assert s.gorunum()["gun_programi"] is None


def test_eski_sunucu_ve_eksik_omur_programi_temizler(servis):
    s, _, _ = servis
    s._yanit_isle({"ayar": {"gun_programi": program()}})
    s._yanit_isle({"ayar": {}})
    assert s.gorunum()["gun_programi"] is None
    p = program()
    del p["gecerli_sn"]
    s._yanit_isle({"ayar": {"gun_programi": p}})
    assert s.gorunum()["gun_programi"] is None
