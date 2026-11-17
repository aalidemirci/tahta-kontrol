"""Uydurma raporlarla öğretmen programı, açık eşleme ve PDF sırası."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from tahta_sunucu import ogretmen_program as op
from tahta_sunucu import vt


def matris():
    return [
        ["Ders", "Saat", "PAZARTESİ", "SALI"],
        ["1", "08:00-08:40", "Matematik\nÖrnek Öğretmen", ""],
        ["2", "08:50-09:30", "", "Seçmeli\nÖrnek Öğretmen - Sanat\nDiğer Öğretmen - Müzik"],
        ["1", "13:00-13:40", "Fen", ""],
    ]


@pytest.fixture
def veri():
    return op.matris_oku(matris(), ["9/A", "9/B"])


@pytest.fixture
def baglanti(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    vt.hazirla()
    with vt.islem() as b:
        b.execute("INSERT INTO ogretmen (id, ad, soyad) VALUES (1, 'Örnek', 'Öğretmen')")
        b.execute("INSERT INTO ogretmen (id, ad, soyad) VALUES (2, 'Diğer', 'Öğretmen')")
        yield b


def test_ayri_devre_ve_secmeli_ogretmenleri_okur(veri):
    assert len(veri["dersler"]) == 4
    assert len(veri["ogretmenler"]) == 2
    assert {s["ders_adi"] for s in veri["dersler"]} == {"Matematik", "Sanat", "Müzik", "Fen"}
    assert veri["ogretmensiz"] == 1
    assert veri["dersler"][-1]["baslangic"] == "13:00"


def test_sube_sayisi_ve_tekrarli_sube_reddedilir():
    with pytest.raises(ValueError, match="aynı sayıda"):
        op.matris_oku(matris(), ["9/A"])
    with pytest.raises(ValueError, match="farklı"):
        op.matris_oku(matris(), ["9/A", "9/A"])


def test_ayni_dersin_birden_cok_ogretmeni_ayri_eslenir():
    m = matris()
    m[1][2] = "Matematik\nÖrnek Öğretmen, Diğer Öğretmen"
    veri = op.matris_oku(m, ["9/A", "9/B"])
    dersler = [s for s in veri["dersler"] if s["gun"] == 0 and s["sube"] == "9/A"]
    assert len(dersler) == 2
    assert len({s["ogretmen_anahtari"] for s in dersler}) == 2


def test_pdf_sayfa_sirasi_ogretmen_satirlariyla_dogrulanir():
    dogru = [op.ad_anahtari("Örnek Öğretmen / Örnek Öğretmen - Sanat / Diğer Öğretmen - Müzik"), ""]
    assert op.matris_oku(matris(), ["9/A", "9/B"], dogru)["dersler"]
    with pytest.raises(ValueError, match="uyuşmuyor"):
        op.matris_oku(matris(), ["9/B", "9/A"], list(reversed(dogru)))


def test_pdf_sube_basliklarini_yalniz_bellekte_okur(monkeypatch):
    sayfalar = [SimpleNamespace(extract_text=lambda: "AL - 9. Sınıf / A Şubesi"),
                SimpleNamespace(extract_text=lambda: "AL - 9. Sınıf / B Şubesi")]
    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=lambda _: SimpleNamespace(
        is_encrypted=False, pages=sayfalar)))
    subeler, metinler = op.pdf_oku(b"%PDF-uydurma")
    assert subeler == ["9/A", "9/B"] and len(metinler) == 2
    sayfalar.append(sayfalar[0])
    with pytest.raises(ValueError, match="birden çok"):
        op.pdf_oku(b"%PDF-uydurma")


def test_tam_ad_eslesir_ayni_ad_belirsiz_kalir(baglanti, veri):
    onizleme = op.onizle(baglanti, veri)
    assert onizleme["eslesmeyen"] == 0
    baglanti.execute("INSERT INTO ogretmen (ad, soyad) VALUES ('Örnek', 'Öğretmen')")
    onizleme = op.onizle(baglanti, veri)
    assert onizleme["eslesmeyen"] == 1
    assert next(s for s in onizleme["ogretmenler"] if s["anahtar"] == op.ad_anahtari("Örnek Öğretmen"))["belirsiz"]


def test_acik_onayla_yazar_kaynak_adi_saklanmaz_ve_surumu_denetler(baglanti, veri):
    with pytest.raises(ValueError, match="ayrı onay"):
        op.uygula(baglanti, veri, 0, {})
    assert baglanti.execute("SELECT COUNT(*) FROM ogretmen_program").fetchone()[0] == 0
    assert op.uygula(baglanti, veri, 0, {}, ogretmensiz_onay=True) == 4
    assert op.surum(baglanti) == 1
    sutunlar = {s[1] for s in baglanti.execute("PRAGMA table_info(ogretmen_program)")}
    assert "kaynak_ogretmen" not in sutunlar
    with pytest.raises(ValueError, match="bu sırada değişti"):
        op.uygula(baglanti, veri, 0, {}, ogretmensiz_onay=True)
    assert baglanti.execute("SELECT COUNT(*) FROM ogretmen_program").fetchone()[0] == 4


def test_pasif_ogretmene_esleme_ve_sessiz_atlama_yapilmaz(baglanti, veri):
    baglanti.execute("UPDATE ogretmen SET aktif = 0 WHERE id = 1")
    with pytest.raises(ValueError, match="Bütün kaynak"):
        op.uygula(baglanti, veri, 0, {op.ad_anahtari("Örnek Öğretmen"): "1"}, ogretmensiz_onay=True)
    assert op.uygula(baglanti, veri, 0, {op.ad_anahtari("Örnek Öğretmen"): "yok"}, ogretmensiz_onay=True) == 4
