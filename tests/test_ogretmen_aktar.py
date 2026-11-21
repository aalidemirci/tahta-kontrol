"""Toplu öğretmen listesi aktarımı (0.21.0, ogretmen_aktar.py ve /ogretmenler/onizle|aktar). Bütün veriler UYDURMADIR.

Depoya ikili .xls konmaz: e-Okul personel listesi (OOK01001R1) yerleşimi matris verilerek sınanır.
"""

from __future__ import annotations

import re

import pytest
from r5_uret import r5
from yardimci import SAHTE_TC, gir, ileti, kullanici_ekle, kur_ve_gir, sorgu

from tahta_sunucu import eokul, metin, ogretmen_aktar, vt

# ---- uydurma kaynaklar -------------------------------------------------------------------------------------
ASC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<timetable importtype="database" options="idprefix:X,daynumbering1" displayname="aSc Timetables 2012 XML">
  <periods options="canadd,export:silent" columns="period,name,short,starttime,endtime">
    <period name="1" short="1" period="1" starttime="08:30" endtime="09:10"/>
  </periods>
  <subjects options="canadd" columns="id,name,short"><subject id="S1" name="ZZQDERS" short="ZQ"/></subjects>
  <teachers options="canadd,export:silent" columns="id,name,short,gender,color,email,mobile,partner_id,firstname,lastname">
    <teacher id="A1" name="ŞULE İPEK" short="ZQS" gender="F" color="#FF0000" email="zzqposta@ornek.test" mobile="05559990011" partner_id="ZZQORTAK" firstname="ŞULE" lastname="İPEK"/>
    <teacher id="A2" name="CAN DENEME ÖRNEK" short="CDO" gender="" color="#00FF00" email="" mobile="" partner_id="" firstname="CAN" lastname="DENEME ÖRNEK"/>
    <teacher id="A3" name="ELİF SU IŞIK" short="ESI" firstname="" lastname=""/>
    <teacher id="A4" name="" short="BOS" firstname="" lastname=""/>
  </teachers>
  <students options="canadd" columns="id,classid,name"><student id="O1" classid="C1" name="ZZQOGRENCI"/></students>
</timetable>
""".encode()

# e-Okul OOK01001R1 yerleşimi (sütunlar 0/6/8/10; sonda tek ve iki hücreli altbilgi). Adlar uydurmadır.
OOK_MATRIS = [
    ["ADI SOYADI", "", "", "", "", "", "GÖREVİ", "", "KADRO DURUMU", "", "BRANŞI", "", "", "", ""],
    ["AYŞE ÖRNEKOĞLU", "", "", "", "", "", "Müdür", "", "ZZQKADRO", "", "ZZQBRANS", "", "", "", ""],
    ["MEHMET ALİ DENEME", "", "", "", "", "", "Müdür Yardımcısı", "", "ZZQKADRO", "", "ZZQBRANS", "", "", "", ""],
    ["İLKER IŞIK", "", "", "", "", "", "Öğretmen", "", "ZZQKADRO", "", "ZZQBRANS", "", "", "", ""],
    ["Deniz Kaya", "", "", "", "", "", "Sözleşmeli Öğretmen(657 S.K. 4/B)", "", "ZZQKADRO", "", "ZZQBRANS", "", "", "", ""],
    ["ZEKİ MEMUROĞLU", "", "", "", "", "", "Memur", "", "ZZQKADRO", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
    ["ZZQ Deneme Anadolu Lisesi Müdürlüğü", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", "", "46000.5", "", "1.234567890123"],
]


def tablo(satirlar: list[str]) -> bytes:
    return ("\n".join(satirlar) + "\n").encode()


@pytest.fixture()
def yonetici(panel):
    kur_ve_gir(panel)
    return panel


def onizle(panel, veri: bytes, ad: str = "liste.csv"):
    return panel.post("/ogretmenler/onizle", files={"dosya": (ad, veri, "application/octet-stream")})


def belirtec(yanit) -> str:
    assert yanit.status_code == 200, ileti(yanit)
    return re.search(r'name="onizleme" value="([^"]+)"', yanit.text).group(1)


def isaretli(yanit, ad: str) -> list[str]:
    """Önizleme sayfasındaki işaretli kutuların değerleri."""
    return re.findall(rf'name="{ad}" value="([^"]+)" checked', yanit.text)


def ogretmenler() -> list[tuple]:
    return [(s["ad"], s["soyad"], s["kod"], s["aktif"], s["pin_ozet"]) for s in
            sorgu("SELECT o.ad, o.soyad, o.aktif, p.kod, p.pin_ozet FROM ogretmen o JOIN ogretmen_pin p ON p.ogretmen_id = o.id ORDER BY o.id")]  # fmt: skip


# ---- metin -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("ham", "beklenen"),
    [("ŞULE İPEK", "Şule İpek"), ("IŞIK", "Işık"), ("İLKER ÇAĞLAR", "İlker Çağlar"), ("AYŞE-NUR ÖZTÜRK", "Ayşe-Nur Öztürk"),
     ("ILGIN İNCİ", "Ilgın İnci"), ("ÜMİT  GÜNEŞ", "Ümit Güneş")],
)  # fmt: skip
def test_buyuk_harf_turkce_bas_harfe_cevrilir(ham, beklenen):
    assert metin.tamami_buyuk_mu(ham)
    assert metin.tr_bas_buyuk(ham) == beklenen


def test_karisik_yazilmis_ad_aynen_kalir():
    assert ogretmen_aktar.ad_bicimle("Ayşe", "YILMAZ") == ("Ayşe", "YILMAZ")
    assert ogretmen_aktar.ad_bicimle("ŞULE", "İPEK") == ("Şule", "İpek")
    assert not metin.tamami_buyuk_mu("123") and not metin.tamami_buyuk_mu("")


# ---- aSc XML -----------------------------------------------------------------------------------------------
def test_asc_yalniz_ad_ve_soyad_okunur():
    sonuc = ogretmen_aktar.dosya_oku(ASC_XML, "program.xml")
    assert sonuc["kaynak"] == "asc"
    adlar = [(s["ad"], s["soyad"], s["bolme"]) for s in sonuc["ogretmenler"]]
    assert adlar == [("Şule", "İpek", False), ("Can", "Deneme Örnek", False), ("Elif Su", "Işık", True)]
    assert sonuc["atlanan"] == [{"satir": 4, "neden": "ad boş"}]
    metin_ = repr(sonuc)
    for gizli in ("zzqposta", "05559990011", "ZZQORTAK", "ZQS", "#FF0000", "ZZQDERS", "ZZQOGRENCI", "A1"):
        assert gizli not in metin_, gizli
    assert all(set(s) == {"satir", "ad", "soyad", "kod", "gorev", "bolme"} for s in sonuc["ogretmenler"])


def test_asc_okuyucusu_derslik_sihirbazinin_atlama_listesine_dokunmaz():
    from tahta_sunucu import program_aktar

    assert "teachers" in program_aktar.ASC_ATLA


@pytest.mark.parametrize(
    ("veri", "ileti_"),
    [
        (b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "b">]><timetable/>', "güvenli olmayan"),
        (b'<?xml version="1.0"?><kok><teachers><teacher firstname="A" lastname="B"/></teachers></kok>', "aSc Timetables XML"),
        (b'<?xml version="1.0"?><timetable><classes/></timetable>', "öğretmen listesi bulunamadı"),
        (b'<?xml version="1.0"?><timetable><teachers>', "okunamadı"),
    ],
)
def test_asc_hatalari_turkce(veri, ileti_):
    with pytest.raises(ValueError, match=ileti_):
        ogretmen_aktar.dosya_oku(veri, "x.xml")


# ---- e-Okul OOK01001R1 -------------------------------------------------------------------------------------
def test_eokul_personel_listesi_basliktan_bulunur(monkeypatch):
    monkeypatch.setattr(eokul, "matris_oku", lambda veri, asiri=None: ("eokul_xls", [list(s) for s in OOK_MATRIS]))
    sonuc = ogretmen_aktar.dosya_oku(b"x", "OOK01001R1.XLS")
    assert sonuc["kaynak"] == "eokul" and "OOK01001R1" in sonuc["kaynak_adi"]
    adlar = [(s["ad"], s["soyad"], s["gorev"], s["bolme"]) for s in sonuc["ogretmenler"]]
    assert adlar == [
        ("Ayşe", "Örnekoğlu", "Müdür", False),
        ("Mehmet Ali", "Deneme", "Müdür Yardımcısı", True),
        ("İlker", "Işık", "Öğretmen", False),
        ("Deniz", "Kaya", "Sözleşmeli Öğretmen(657 S.K. 4/B)", False),  # karışık yazım aynen
        ("Zeki", "Memuroğlu", "Memur", False),
    ]
    assert sonuc["atlanan"] == []
    assert "2 altbilgi satırı atlandı" in sonuc["notlar"][0]
    assert "ZZQKADRO" not in repr(sonuc) and "ZZQBRANS" not in repr(sonuc)
    assert any("KADRO DURUMU" in u and "BRANŞI" in u for u in sonuc["uyarilar"])


def test_eokul_sutun_yeri_degisebilir_ve_tc_sutunu_okunmaz():
    matris = [["ADI SOYADI", "GÖREVİ", "KADRO DURUMU", "BRANŞI", "T.C. Kimlik No"],
              ["CAN TEST", "Öğretmen", "ZZQKADRO", "ZZQBRANS", SAHTE_TC],
              ["", "", "", "", "", "45000"]]  # fmt: skip
    sonuc = ogretmen_aktar.matris_coz("eokul_xls", matris)
    assert [(s["ad"], s["soyad"], s["gorev"]) for s in sonuc["ogretmenler"]] == [("Can", "Test", "Öğretmen")]
    assert "T.C. Kimlik No sütunu bulundu, okunmadı." in sonuc["uyarilar"]
    assert SAHTE_TC not in repr(sonuc)


# ---- şablon ve düz tablo -----------------------------------------------------------------------------------
def test_sablon_csv_geri_okunur_ve_ornek_satir_onerilmez(yonetici):
    sonuc = ogretmen_aktar.dosya_oku(ogretmen_aktar.sablon_csv(), "sablon.csv")
    assert sonuc["kaynak"] == "csv" and [(s["ad"], s["soyad"]) for s in sonuc["ogretmenler"]] == [("Ayşe", "Örnek")]
    with vt.islem() as b:
        p = ogretmen_aktar.plan(b, sonuc)
    assert p["satirlar"][0]["durum"] == "ekle" and not p["satirlar"][0]["secili"]


def test_xlsx_sablonu_okunur_kod_ve_tc_ile():
    veri = r5(a1="Öğretmen listesi", a2="", basliklar=("Adı", "Soyadı", "Öğretmen Kodu", "TC Kimlik No", "Kısa ad"),
              satirlar=[("Ece", "Tan", 150, SAHTE_TC, "ET"), (f"Ali {SAHTE_TC}", "Yanlış", "", "", "")])  # fmt: skip
    sonuc = ogretmen_aktar.dosya_oku(veri, "liste.xlsx")
    assert sonuc["kaynak"] == "xlsx"
    assert [(s["ad"], s["soyad"], s["kod"]) for s in sonuc["ogretmenler"]] == [("Ece", "Tan", "150")]
    assert sonuc["atlanan"] == [{"satir": 6, "neden": "adda T.C. kimlik numarasına benzeyen değer var"}]
    assert "T.C. Kimlik No sütunu bulundu, okunmadı." in sonuc["uyarilar"]
    assert SAHTE_TC not in repr(sonuc)


def test_tek_sutun_ad_soyad_son_sozcugu_soyad_sayar():
    sonuc = ogretmen_aktar.dosya_oku(tablo(["Adı Soyadı;Kod", "Ayşe Nur Örnek;", "Can Tan;120"]))
    assert [(s["ad"], s["soyad"], s["bolme"], s["kod"]) for s in sonuc["ogretmenler"]] == [
        ("Ayşe Nur", "Örnek", True, ""), ("Can", "Tan", False, "120")]  # fmt: skip


def test_ad_sutunu_bulunamazsa_turkce_hata():
    with pytest.raises(ValueError, match="öğretmen adı sütunları bulunamadı"):
        ogretmen_aktar.dosya_oku(tablo(["Kadro Durumu;Branşı", "x;y"]))


# ---- plan --------------------------------------------------------------------------------------------------
def test_plan_var_pasif_yinelenen_ve_kod_cakismasi(yonetici):
    yonetici.post("/ogretmenler", data={"eylem": "ekle", "ad": "Can", "soyad": "Demir"})  # kod 101
    yonetici.post("/ogretmenler", data={"eylem": "ekle", "ad": "Ece", "soyad": "Tan", "kod": "150"})
    ece = sorgu("SELECT id FROM ogretmen WHERE ad = 'Ece'")[0]["id"]
    yonetici.post("/ogretmenler", data={"eylem": "durum", "id": str(ece)})  # pasif
    sonuc = ogretmen_aktar.dosya_oku(tablo([
        "Adı;Soyadı;Kod", "CAN;DEMİR;", "Ece;Tan;", "Deniz;Kaya;101", "Ali;Er;50", "Banu;Su;160", "Cem;Ok;160",
        "deniz;KAYA;", "Ela;Az;",
    ]))  # fmt: skip
    with vt.islem() as b:
        p = ogretmen_aktar.plan(b, sonuc)
    durum = {(x["ad"], x["soyad"]): (x["durum"], x["kod"], x["kod_kaynagi"]) for x in p["satirlar"] if x["durum"] != "yinelenen"}
    assert durum == {
        ("Can", "Demir"): ("var", "101", "mevcut"),  # büyük harf katlanarak eşleşir
        ("Ece", "Tan"): ("pasif", "150", "mevcut"),
        ("Deniz", "Kaya"): ("ekle", "102", "otomatik"),  # 101 başka öğretmende → otomatik
        ("Ali", "Er"): ("ekle", "103", "otomatik"),  # 50 geçersiz
        ("Banu", "Su"): ("ekle", "160", "dosya"),
        ("Cem", "Ok"): ("ekle", "104", "otomatik"),  # 160 dosyada iki kez
        ("Ela", "Az"): ("ekle", "105", "otomatik"),
    }
    assert [x["durum"] for x in p["satirlar"]].count("yinelenen") == 1
    assert {a: p["sayilar"][a] for a in ("ekle", "var", "pasif", "yinelenen", "dosyada")} == {
        "ekle": 5, "var": 1, "pasif": 1, "yinelenen": 1, "dosyada": 8}  # fmt: skip
    # Planlamak yazmaz.
    assert len(sorgu("SELECT id FROM ogretmen")) == 2


# ---- uçlar -------------------------------------------------------------------------------------------------
def test_toplu_yukleme_ekler_pinsiz_ve_kayda_ad_yazmaz(yonetici):
    yonetici.post("/ogretmenler", data={"eylem": "ekle", "ad": "Ece", "soyad": "Tan"})
    ece = sorgu("SELECT id FROM ogretmen WHERE ad = 'Ece'")[0]["id"]
    yonetici.post("/ogretmenler", data={"eylem": "durum", "id": str(ece)})
    sayfa = yonetici.get("/ogretmenler").text
    assert 'action="/ogretmenler/onizle"' in sayfa and 'href="/ogretmenler/sablon.csv"' in sayfa and "OOK01001R1" in sayfa
    yanit = onizle(yonetici, ASC_XML, "program.xml")
    b_ = belirtec(yanit)
    assert "Şule" in yanit.text and "zzqposta" not in yanit.text and "Görev" not in yanit.text
    assert isaretli(yanit, "ekle") == ["1", "2", "3"]
    assert 'name="etkinlestir"' not in yanit.text  # bu dosyada pasif ad yok
    aktar = yonetici.post("/ogretmenler/aktar", data={"onizleme": b_, "ekle": ["1", "3"]})
    assert ileti(aktar).startswith("2 öğretmen eklendi. PIN'i olmayanların hepsine PIN üretmek için")
    assert ogretmenler()[1:] == [("Şule", "İpek", "102", 1, None), ("Elif Su", "Işık", "103", 1, None)]  # 101 pasif Ece'de
    kayit = repr(sorgu("SELECT islem, ayrinti FROM kayit"))
    for gizli in ("Şule", "İpek", "Elif", "Işık", "ŞULE", "Ece", "Tan"):
        assert gizli not in kayit, gizli
    assert "Öğretmen listesi aktarıldı" in kayit and "2 eklendi, 0 etkinleştirildi" in kayit
    # Önizleme tek kullanımlıktır.
    assert ileti(yonetici.post("/ogretmenler/aktar", data={"onizleme": b_})).startswith("Önizlemenin süresi doldu")


def test_pasif_ogretmen_yalniz_isaretlenirse_etkinlesir(yonetici):
    yonetici.post("/ogretmenler", data={"eylem": "ekle", "ad": "Ece", "soyad": "Tan"})
    ece = sorgu("SELECT id FROM ogretmen WHERE ad = 'Ece'")[0]["id"]
    yonetici.post("/ogretmenler", data={"eylem": "durum", "id": str(ece)})
    veri = tablo(["Adı;Soyadı", "ECE;TAN", "Can;Ok"])
    yanit = onizle(yonetici, veri)
    assert f'name="etkinlestir" value="{ece}">' in yanit.text and isaretli(yanit, "etkinlestir") == []
    yonetici.post("/ogretmenler/aktar", data={"onizleme": belirtec(yanit), "ekle": ["3"]})
    assert [(o[0], o[3]) for o in ogretmenler()] == [("Ece", 0), ("Can", 1)]  # işaretsiz: pasif kaldı, yeni kayıt yok
    yanit = onizle(yonetici, veri)
    aktar = yonetici.post("/ogretmenler/aktar", data={"onizleme": belirtec(yanit), "etkinlestir": [str(ece)]})
    assert ileti(aktar).startswith("0 öğretmen eklendi, 1 öğretmen etkinleştirildi.")
    assert [(o[0], o[3]) for o in ogretmenler()] == [("Ece", 1), ("Can", 1)]


def test_dosyada_olmayan_ogretmene_dokunulmaz_ve_vazgec_siler(yonetici):
    yonetici.post("/ogretmenler", data={"eylem": "ekle", "ad": "Eski", "soyad": "Kayıt"})
    yanit = onizle(yonetici, tablo(["Adı;Soyadı", "Yeni;Kişi"]))
    vazgec = yonetici.post("/ogretmenler/aktar", data={"onizleme": belirtec(yanit), "ekle": ["2"], "eylem": "vazgec"})
    assert ileti(vazgec) == "Önizleme silindi; hiçbir öğretmen eklenmedi."
    assert [o[0] for o in ogretmenler()] == ["Eski"]
    yanit = onizle(yonetici, tablo(["Adı;Soyadı", "Yeni;Kişi"]))
    yonetici.post("/ogretmenler/aktar", data={"onizleme": belirtec(yanit), "ekle": ["2"]})
    assert [(o[0], o[3]) for o in ogretmenler()] == [("Eski", 1), ("Yeni", 1)]


def test_onizlemeden_sonra_eklenen_ad_yeniden_eklenmez(yonetici):
    yanit = onizle(yonetici, tablo(["Adı;Soyadı;Kod", "Can;Ok;101", "Ela;Az;"]))
    b_ = belirtec(yanit)
    yonetici.post("/ogretmenler", data={"eylem": "ekle", "ad": "Can", "soyad": "Ok"})  # arada elle: kod 101
    yonetici.post("/ogretmenler/aktar", data={"onizleme": b_, "ekle": ["2", "3"]})
    assert ogretmenler() == [("Can", "Ok", "101", 1, None), ("Ela", "Az", "102", 1, None)]


def test_idareci_toplu_yukleyemez(yonetici):
    kullanici_ekle(yonetici, "idareci1")
    gir(yonetici, "idareci1")
    assert ileti(onizle(yonetici, tablo(["Adı;Soyadı", "Can;Ok"]))) == "Bu işlem için yönetici yetkisi gerekir."
    assert ileti(yonetici.post("/ogretmenler/aktar", data={"onizleme": "x"})) == "Bu işlem için yönetici yetkisi gerekir."
    assert 'action="/ogretmenler/onizle"' not in yonetici.get("/ogretmenler").text
    assert ogretmenler() == []


def test_yonetici_belirteci_baska_onizleme_turunde_gecmez(yonetici):
    """Depo öğrenci ve mazeret önizlemesiyle ortaktır; öğretmen belirteci öğrenci aktarımına geçmez."""
    b_ = belirtec(onizle(yonetici, tablo(["Adı;Soyadı", "Can;Ok"])))
    assert ileti(yonetici.post("/ogrenciler/aktar", data={"onizleme": b_})).startswith("Önizlemenin süresi doldu")
    assert ogretmenler() == []


def test_hatali_dosya_reddedilir_ve_bos_liste_bildirilir(yonetici):
    assert "öğretmen adı sütunları bulunamadı" in ileti(onizle(yonetici, tablo(["Kod", "101"])))
    assert ileti(onizle(yonetici, tablo(["Adı;Soyadı", f"{SAHTE_TC};Ok"]))).startswith("Dosyada eklenebilecek öğretmen satırı yok (1 satır")
    kayit = repr(sorgu("SELECT ayrinti FROM kayit"))
    assert SAHTE_TC not in kayit and "Öğretmen listesi reddedildi" in repr(sorgu("SELECT islem FROM kayit"))


def test_sablon_indirilir_ve_oturum_ister(yonetici, uygulama):
    yanit = yonetici.get("/ogretmenler/sablon.csv")
    assert yanit.status_code == 200 and yanit.headers["content-type"].startswith("text/csv")
    assert yanit.content.decode("utf-8-sig").splitlines() == ["Adı;Soyadı;Kod", "Ayşe;Örnek;"]
    yonetici.cookies.clear()
    assert yonetici.get("/ogretmenler/sablon.csv").headers["location"].startswith("/giris")
