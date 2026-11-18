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


def hucreli(hucre):
    m = matris()
    m[2][3] = hucre
    return op.matris_oku(m, ["9/A", "9/B"])


def sali(veri):
    return [s for s in veri["dersler"] if s["gun"] == 1]


def test_ayni_satirdaki_iki_secmeli_grup_ayri_okunur_ad_ders_adina_karismaz():
    veri = hucreli("SEÇMELİ DERS\nYapay Birinci - Sanat  Uydurma İkinci - Müzik")
    assert {(s["ders_adi"], s["ogretmen_anahtari"]) for s in sali(veri)} == {
        ("Sanat", op.ad_anahtari("Yapay Birinci")), ("Müzik", op.ad_anahtari("Uydurma İkinci"))}
    assert op.ad_anahtari("Uydurma İkinci") in veri["ogretmenler"]
    assert veri["belirsiz"] == 0


def test_uc_secmeli_grup_ve_karisik_ayiricilar():
    veri = hucreli("SEÇMELİ DERS\nYapay Birinci - Sanat   Uydurma İkinci - Kur`an-ı Kerim\tÖrnek Öğretmen - Müzik; "
                   "Diğer Öğretmen - Spor")
    assert {s["ders_adi"] for s in sali(veri)} == {"Sanat", "Kur`an-ı Kerim", "Müzik", "Spor"}
    assert len({s["ogretmen_anahtari"] for s in sali(veri)}) == 4
    adlar = " ".join(veri["ogretmenler"].values())
    assert not any(k in s["ders_adi"] for s in veri["dersler"] for k in adlar.split())


def test_tek_boslukla_bitisik_belirsiz_hucre_genel_basliga_iner():
    veri = hucreli("SEÇMELİ DERS\nYapay Birinci - Sanat Uydurma İkinci - Müzik")
    assert [(s["ders_adi"], s["ogretmen_anahtari"]) for s in sali(veri)] == [("SEÇMELİ DERS", "")]
    assert veri["belirsiz"] == 1
    assert not any("Uydurma" in s["ders_adi"] or "Yapay" in s["ders_adi"] for s in veri["dersler"])
    assert not any("yapay" in a or "uydurma" in a for a in veri["ogretmenler"])


def test_baslik_satiri_kisi_kalibindaysa_ders_adina_yazilmaz():
    veri = hucreli("Yapay Birinci - Sanat")
    assert [s["ders_adi"] for s in sali(veri)] == [op.GENEL_BASLIK]
    assert veri["belirsiz"] == 1


def test_ayni_ad_ayni_saatte_farkli_derste_onizlemede_isaretlenir(baglanti):
    m = matris()
    m[1][2] = "Seçmeli\nÖrnek Öğretmen - Sanat  Örnek Öğretmen - Müzik"
    veri = op.matris_oku(m, ["9/A", "9/B"])
    ozet = op.onizle(baglanti, veri)
    assert ozet["cakisan_sayisi"] == 1
    assert [e["cakisan"] for e in ozet["ogretmenler"]] == [False, True]  # ada göre sıralı: Diğer, Örnek


def test_birlestirilen_subelerde_ayni_ders_cakisma_sayilmaz(baglanti):
    m = matris()
    m[3][2] = "Matematik\nÖrnek Öğretmen"
    m[3][1] = "08:00-08:40"
    veri = op.matris_oku(m, ["9/A", "9/B"])
    assert op.onizle(baglanti, veri)["cakisan_sayisi"] == 0


def test_goc_bozuk_ders_adini_genel_basliga_indirir(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    vt.hazirla()
    with vt.islem() as b:
        b.execute("INSERT INTO ogretmen (id, ad, soyad) VALUES (1, 'Örnek', 'Öğretmen')")
        ekle = ("INSERT INTO ogretmen_program (sube,gun,ders_no,baslangic,bitis,ders_adi,ogretmen_id,guncelleme) "
                "VALUES ('9/A',0,?,'08:00','08:40',?,1,1)")
        b.execute(ekle, (1, "Sanat Uydurma İkinci - Müzik"))
        b.execute(ekle, (2, "Spor Uydurma İkinci - Müzik"))
        b.execute(ekle, (2, "Seçmeli ders"))
        b.execute(ekle, (3, "Kur`an-ı Kerim"))
        b.executescript(next(g for g in vt.GOCLER if "'Seçmeli ders'" in g))  # 0.13.1 göçü
        assert [tuple(s) for s in b.execute("SELECT ders_no, ders_adi FROM ogretmen_program ORDER BY ders_no")] == [
            (1, "Seçmeli ders"), (2, "Seçmeli ders"), (3, "Kur`an-ı Kerim")]


@pytest.mark.parametrize("hucre", [
    "SEÇMELİ DERS\nYapay Birinci - Sanat Uydurma İkinci",
    "SEÇMELİ DERS\nYapay Birinci - Sanat Uydurma İkinci – Müzik",
    "SEÇMELİ DERS\nYapay Birinci - Sanat/Uydurma İkinci",
    "Uydurma İkinci\nYapay Birinci",
    "Matematik Uydurma İkinci",
])
def test_raporda_kisi_olarak_gorulen_ad_ders_adina_yazilmaz(hucre):
    """Hücre tek başına yakalayamadığı sapmalar: ad başka hücrede kişi olarak görülüyorsa ders adı iner."""
    m = [["Ders", "Saat", "PAZARTESİ", "SALI"],
         ["1", "08:00-08:40", "Müzik\nUydurma İkinci", hucre]]
    veri = op.matris_oku(m, ["9/A"])
    adlar = {d["ders_adi"] for d in veri["dersler"]}
    assert not any("kinci" in a or "Birinci" in a for a in adlar)
    assert op.GENEL_BASLIK in adlar and veri["belirsiz"] >= 1
    indirilen = [d for d in veri["dersler"] if d["ders_adi"] == op.GENEL_BASLIK]
    assert all(d["ogretmen_anahtari"] == "" for d in indirilen)


def test_tek_sozcuklu_kisi_adi_ders_adlarini_indirmez():
    """Tek sözcüklü "kişi" (bozuk satır) meşru ders adlarını genel başlığa indirmesin."""
    m = [["Ders", "Saat", "PAZARTESİ", "SALI"],
         ["1", "08:00-08:40", "Müzik\nSanat", "Görsel Sanat\nYapay Birinci"]]
    veri = op.matris_oku(m, ["9/A"])
    assert {d["ders_adi"] for d in veri["dersler"]} == {"Müzik", "Görsel Sanat"}
    assert veri["belirsiz"] == 0


def test_onizleme_farkli_ders_adlarinin_tamamini_verir(baglanti):
    m = [["Ders", "Saat", "PAZARTESİ", "SALI"]]
    m += [[str(n), f"{7 + n:02d}:00-{7 + n:02d}:40", f"Uydurma Ders {n}\nYapay Birinci", ""] for n in range(1, 9)]
    veri = op.matris_oku(m, ["9/A"])
    ozet = op.onizle(baglanti, veri)
    assert ozet["ders_adlari"] == [f"Uydurma Ders {n}" for n in range(1, 9)]
