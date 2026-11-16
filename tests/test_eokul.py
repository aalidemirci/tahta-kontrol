"""Öğrenci listesi ayrıştırıcısı (Aşama 5, eokul.py). Bütün veriler UYDURMADIR.

Depoya ikili .xls konmaz (şartname §8.5): e-Okul blok yerleşimi matris verilerek sınanır, .xls dalı
yalnız "bozuk dosya → Türkçe hata" yoluyla.
"""

from __future__ import annotations

import pytest
from r5_uret import r5

from tahta_sunucu import eokul, metin

# Şartname §7.1'deki uydurma örnek (satır sırası korunur).
EOKUL_MATRIS = [
    ["T.C. ... DENEME ANADOLU LİSESİ"],
    ["AL - 10. Sınıf / A Şubesi (ALANI YOK) Sınıf Listesi"],
    ["Sınıf Öğretmeni : Ayşe ÖRNEK"],
    ["S.No", "Öğrenci No", "Adı", "Soyadı", "Cinsiyeti", "Pansiyon Durum"],
    ["1", "1047", "Ayşe", "YILMAZ", "Kız", "Gündüzlü"],
    ["2", "1102", "Burak", "KAYA", "Erkek", "Gündüzlü"],
    ["Kız Öğrenci Sayısı : 1  Erkek Öğrenci Sayısı : 1  Toplam Öğrenci Sayısı : 2"],
    ["AL - 10. Sınıf / İ Şubesi (ALANI YOK) Sınıf Listesi"],
    ["S.No", "Öğrenci No", "Adı", "Soyadı", "Cinsiyeti", "Pansiyon Durum"],
    ["1", "0215", "Cemre", "DOĞAN", "Kız", "Gündüzlü"],
    ["OOG01001R020"],
]


def oku_matris(matris, monkeypatch):
    """matris_oku'yu atlayıp ayrıştırıcıya doğrudan matris verir (.xls yerine)."""
    monkeypatch.setattr(eokul, "matris_oku", lambda veri: ("eokul_xls", [list(s) for s in matris]))
    return eokul.ogrenci_listesi_oku(b"x")


def test_eokul_blok_listesi_duzlestirilir(monkeypatch):
    sonuc = oku_matris(EOKUL_MATRIS, monkeypatch)
    ogrenciler = [(s["sube"], s["okul_no"], s["ad"], s["soyad"]) for s in sonuc["satirlar"]]
    assert ogrenciler == [("10/A", "1047", "Ayşe", "YILMAZ"), ("10/A", "1102", "Burak", "KAYA"), ("10/İ", "0215", "Cemre", "DOĞAN")]
    assert sonuc["satirlar"][0]["satir"] == 5  # Excel satır numarası korunur
    assert sonuc["atlanan"] == []
    assert "2 şube bloğu" in sonuc["notlar"][0]
    assert any("Cinsiyeti" in u for u in sonuc["uyarilar"])  # okunmayan sütun bildirilir


def test_hazirlik_blogu_okunur(monkeypatch):
    matris = [["Hazırlık Sınıfı / B Şubesi Sınıf Listesi"], ["S.No", "Öğrenci No", "Adı", "Soyadı"], ["1", "0007", "Deniz", "ÇELİK"]]
    sonuc = oku_matris(matris, monkeypatch)
    assert [(s["sube"], s["okul_no"]) for s in sonuc["satirlar"]] == [("Hazırlık/B", "0007")]


def test_basligi_cozulmeyen_blok_onceki_subeyi_devralmaz(monkeypatch):
    matris = [
        ["10. Sınıf / A Şubesi"], ["S.No", "Öğrenci No", "Adı", "Soyadı"], ["1", "1047", "Ayşe", "YILMAZ"],
        ["Toplam Öğrenci Sayısı : 1"],
        ["10. Sınıf / (ALANI YOK) Şubesi"],  # harf yok: şube çözülemez
        ["S.No", "Öğrenci No", "Adı", "Soyadı"], ["1", "2001", "Ege", "TUNA"],
    ]  # fmt: skip
    sonuc = oku_matris(matris, monkeypatch)
    assert [s["okul_no"] for s in sonuc["satirlar"]] == ["1047"]
    assert sonuc["atlanan"] == [{"satir": 7, "neden": "şube çözülemedi"}]


def test_dipnot_ve_rapor_kodu_satirlari_ogrenci_sayilmaz(monkeypatch):
    sonuc = oku_matris(EOKUL_MATRIS + [["16.11.2026", "10:15"], ["45976", "0.43"]], monkeypatch)
    assert len(sonuc["satirlar"]) == 3 and sonuc["atlanan"] == []


def test_duz_tablo_es_anlamli_basliklar():
    csv = "Öğrenci Soyadı;Öğrenci Adı;Sınıf;Numara\r\nYILMAZ;Ayşe;10-a;1047\r\n".encode()
    sonuc = eokul.ogrenci_listesi_oku(csv)
    assert [(s["sube"], s["okul_no"], s["ad"], s["soyad"]) for s in sonuc["satirlar"]] == [("10/A", "1047", "Ayşe", "YILMAZ")]
    tek = "Şube;Okul No;Adı Soyadı\n10/B;1200;Elif Su DEMİR\n".encode()
    satir = eokul.ogrenci_listesi_oku(tek)["satirlar"][0]
    assert (satir["ad"], satir["soyad"]) == ("Elif Su", "DEMİR")


def test_xlsx_duz_tablo_okunur():
    veri = r5(a1="Deneme listesi", a2="", basliklar=("Sınıf/Şube", "Okul No", "Adı", "Soyadı"),
              satirlar=[("10/A", "1047", "Ayşe", "YILMAZ"), ("11/C", "2050", "Kerem", "ÖZ")], sayisal_no=True)  # fmt: skip
    sonuc = eokul.ogrenci_listesi_oku(veri)
    assert sonuc["bicim"] == "xlsx"
    assert [(s["sube"], s["okul_no"]) for s in sonuc["satirlar"]] == [("10/A", "1047"), ("11/C", "2050")]


def test_csv_utf8_ve_windows1254_ayrac_tespiti():
    metin_ = "Sınıf/Şube,Okul No,Adı,Soyadı\n10/A,1047,Ayşe,YILMAZ\n"
    for kodlama in ("utf-8-sig", "cp1254"):
        sonuc = eokul.ogrenci_listesi_oku(metin_.encode(kodlama))
        assert sonuc["bicim"] == "csv"
        assert [(s["sube"], s["ad"]) for s in sonuc["satirlar"]] == [("10/A", "Ayşe")]
    sekme = eokul.ogrenci_listesi_oku("Şube\tOkul No\tAdı\tSoyadı\n9/B\t901\tCan\tAK\n".encode())
    assert sekme["satirlar"][0]["sube"] == "9/B"


def test_sube_duzelt_bicimleri():
    beklenen = {"10-a": "10/A", "10 A": "10/A", "10.Sınıf A": "10/A", "Haz/B": "Hazırlık/B", "HAZ/A": "Hazırlık/A",
                "Hazırlık A": "Hazırlık/A", "10/i": "10/İ", "10/I": "10/I", "13/A": None}  # fmt: skip
    for ham, kanonik in beklenen.items():
        assert metin.sube_duzelt(ham) == kanonik, ham


def test_tc_sutunu_okunmaz_ve_uyarilir():
    csv = "T.C. Kimlik No;Sınıf/Şube;Okul No;Adı;Soyadı\n12345678950;10/A;1047;Ayşe;YILMAZ\n".encode()
    sonuc = eokul.ogrenci_listesi_oku(csv)
    assert "T.C. Kimlik No sütunu bulundu, okunmadı." in sonuc["uyarilar"]
    assert "12345678950" not in repr(sonuc["satirlar"])


def test_cift_okul_no_iki_satiri_da_atlar():
    csv = "Şube;Okul No;Adı;Soyadı\n10/A;1047;Ayşe;YILMAZ\n10/B;1047;Burak;KAYA\n10/A;1102;Cem;ER\n;1200;Su;AK\n10/A;12a;Ece;ON\n".encode()
    sonuc = eokul.ogrenci_listesi_oku(csv)
    assert [s["okul_no"] for s in sonuc["satirlar"]] == ["1102"]
    nedenler = {a["satir"]: a["neden"] for a in sonuc["atlanan"]}
    assert nedenler[2].startswith("aynı okul no") and nedenler[3].startswith("aynı okul no")
    assert nedenler[5] == "şube çözülemedi" and nedenler[6].startswith("okul no rakam")


def test_bozuk_xls_turkce_hata_verir():
    with pytest.raises(eokul.OkumaHatasi, match="Excel 97-2003"):
        eokul.ogrenci_listesi_oku(eokul.OLE2 + b"\x00" * 600)


def test_basliksiz_dosya_turkce_hata_verir():
    with pytest.raises(eokul.OkumaHatasi, match="sütunları bulunamadı"):
        eokul.ogrenci_listesi_oku("Ad;Telefon\nAyşe;05550000000\n".encode())


def test_ascii_olmayan_rakamli_okul_no_atlanir():
    # "²" ve "١" str.isdigit()'ten geçer ama int() ile sıralanamaz; satır atlanmalı (500 değil).
    csv = "Şube;Okul No;Adı;Soyadı\n10/A;1²3;Ece;DENEME\n10/A;١٢;Can;ÖRNEK\n10/A;3001;Su;AK\n".encode()
    sonuc = eokul.ogrenci_listesi_oku(csv)
    assert [s["okul_no"] for s in sonuc["satirlar"]] == ["3001"]
    assert all(a["neden"].startswith("okul no rakam") for a in sonuc["atlanan"])
    assert metin.rakam_mi("0215") and not metin.rakam_mi("²") and not metin.rakam_mi("") and not metin.rakam_mi(None)
