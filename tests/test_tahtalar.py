"""Tahta nitelikleri, gruplar, CSV dışa/içe aktarma, menü."""

from __future__ import annotations

import pytest
from yardimci import gir, ileti, kimlik, kullanici_ekle, kur_ve_gir, plan_formu, sorgu, tahta_ekle


@pytest.fixture()
def iki_tahta(panel, tahta):
    kur_ve_gir(panel)
    return tahta_ekle(panel, tahta, "Z-01"), tahta_ekle(panel, tahta, "Z-02")


def tahta_satiri(tahta_id):
    return sorgu("SELECT * FROM tahta WHERE id = ?", tahta_id)[0]


def test_tahta_alanlari_yalniz_yonetici_degistirir(iki_tahta, panel):
    t = kimlik(iki_tahta[0])
    form = {"ad": "Z-01", "eylem": "kaydet", "alanlar": "1", "bina": " A  Blok ", "kat": "2", "duzey": ["11", "9"],
            "devre": "sabah", "subeler": "9-a, 11/c"}  # fmt: skip
    assert ileti(panel.post(f"/tahta/{t}/kaydet", data=form)) == "Kaydedildi."
    satir = tahta_satiri(t)
    assert (satir["bina"], satir["kat"], satir["duzeyler"], satir["devre"], satir["subeler"]) == (
        "A Blok", 2, "9,11", "sabah", "9/A,11/C"
    )  # fmt: skip
    assert panel.post(f"/tahta/{t}/kaydet", data=form).headers["location"].startswith(f"/tahta/{t}?sekme=bilgiler&m=")
    sayfa = panel.get(f"/tahta/{t}?sekme=bilgiler").text  # 0.17.0: düzenleme formu Bilgiler sekmesinde
    assert 'value="A Blok"' in sayfa and 'name="duzey" value="11" checked' in sayfa
    assert 'id="tahta-bilgi"' not in panel.get(f"/tahta/{t}").text
    for alan, deger, parca in (("kat", "çatı", "Kat"), ("subeler", "13/Z", "Şube"), ("devre", "gece", "Devre")):
        yanit = panel.post(f"/tahta/{t}/kaydet", data={**form, alan: deger})
        assert "t=hata" in yanit.headers["location"] and parca in ileti(yanit)
    # Alan işareti yoksa (eski form) nitelikler korunur.
    panel.post(f"/tahta/{t}/kaydet", data={"ad": "Z-01 yeni", "eylem": "kaydet"})
    assert tahta_satiri(t)["bina"] == "A Blok"
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    yanit = panel.post(f"/tahta/{t}/kaydet", data={**form, "bina": "B Blok"})
    assert "yönetici yetkisi" in ileti(yanit) and tahta_satiri(t)["bina"] == "A Blok"
    assert sorgu("SELECT * FROM kayit WHERE islem = 'Yetkisiz işlem reddedildi'")
    assert "A Blok · 2. kat · 9, 11 · Sabah" in panel.get(f"/tahta/{t}").text
    assert "yönetici yetkisi" in ileti(panel.post("/gruplar", data={"eylem": "ekle", "ad": "X"}))
    assert panel.get("/gruplar").status_code == 200 and "Grup ekle" not in panel.get("/gruplar").text


def test_grup_ekle_uyeler_adlandir(iki_tahta, panel):
    a, b = (kimlik(x) for x in iki_tahta)
    panel.post("/gruplar", data={"eylem": "ekle", "ad": "Fen laboratuvarları", "aciklama": "2. kat"})
    assert "zaten var" in ileti(panel.post("/gruplar", data={"eylem": "ekle", "ad": "FEN LABORATUVARLARI"}))
    grup = sorgu("SELECT id FROM tahta_grubu")[0]["id"]
    assert "2 tahta" in ileti(panel.post("/gruplar", data={"eylem": "uyeler", "id": grup, "tahta": [a, b, 999]}))
    panel.post("/gruplar", data={"eylem": "ad", "id": grup, "ad": "Laboratuvarlar", "aciklama": ""})
    assert sorgu("SELECT ad FROM tahta_grubu")[0]["ad"] == "Laboratuvarlar"
    # Tahta sayfasından grup üyeliği
    panel.post(f"/tahta/{a}/kaydet", data={"ad": "Z-01", "eylem": "kaydet", "alanlar": "1"})
    assert [s["tahta_id"] for s in sorgu("SELECT tahta_id FROM tahta_grubu_uye")] == [b]
    assert "Laboratuvarlar" in panel.get("/gruplar").text


def test_grup_etkin_planda_kullaniliyorsa_silinemez(iki_tahta, panel):
    panel.post("/gruplar", data={"eylem": "ekle", "ad": "Sınav salonları"})
    grup = sorgu("SELECT id FROM tahta_grubu")[0]["id"]
    panel.post("/duyurular", data=plan_formu(kime="secim", grup=str(grup), zaman="tekrarli", siklik="gunluk",
                                             tekrar_saat="08:00", bitis="2026-12-31", baslik="Sınav günü"))  # fmt: skip
    yanit = panel.post("/gruplar", data={"eylem": "sil", "id": grup})
    assert "1 duyuru planında kullanılıyor ('Sınav günü')" in ileti(yanit)
    plan = sorgu("SELECT id FROM duyuru_plani")[0]["id"]
    panel.post(f"/duyurular/plan/{plan}", data={"eylem": "sil"})
    assert "silindi" in ileti(panel.post("/gruplar", data={"eylem": "sil", "id": grup}))
    assert sorgu("SELECT COUNT(*) AS n FROM tahta_grubu")[0]["n"] == 0


def test_tahta_kaldirilinca_tahta_grubu_uyeligi_silinir(iki_tahta, panel):
    a, b = (kimlik(x) for x in iki_tahta)
    panel.post("/gruplar", data={"eylem": "ekle", "ad": "Grup"})
    grup = sorgu("SELECT id FROM tahta_grubu")[0]["id"]
    panel.post("/gruplar", data={"eylem": "uyeler", "id": grup, "tahta": [a, b]})
    panel.post(f"/tahta/{a}/kaydet", data={"ad": "x", "eylem": "sil"})
    assert [s["tahta_id"] for s in sorgu("SELECT tahta_id FROM tahta_grubu_uye")] == [b]


def csv_yukle(panel, icerik: bytes):
    return panel.post("/tahtalar/ice-aktar", data={"eylem": "onizle"}, files={"dosya": ("t.csv", icerik, "text/csv")})


def uygula(panel, sayfa: str):
    import html
    import re

    icerik = html.unescape(re.search(r'name="icerik" value="([^"]*)"', sayfa, re.S).group(1))
    return panel.post("/tahtalar/ice-aktar", data={"eylem": "uygula", "icerik": icerik})


def test_csv_disa_ice_aktarma_gidis_donus(iki_tahta, panel):
    a, b = (kimlik(x) for x in iki_tahta)
    disa = panel.get("/tahtalar.csv")
    assert disa.headers["content-type"].startswith("text/csv") and disa.content.startswith("﻿".encode())
    satirlar = disa.content.decode("utf-8-sig").splitlines()
    assert satirlar[0] == "id;ad;derslik;bina;kat;duzeyler;devre;subeler;gruplar;cevrimici;ajan_surumu"
    # Excel'de doldurulmuş hâli: Türkçe karakterli cp1254, ayraç ;
    yeni = (
        "id;ad;derslik;bina;kat;düzeyler;devre;şube;gruplar\r\n"
        f"{a};Z-01;9/A;A Blok;Zemin;9;Sabah;9/A;Fen laboratuvarları\r\n"
        f"{b};Z-02;9/B;A Blok;2. kat;Hazırlık|10;Öğleden sonra;;Fen laboratuvarları|Sınav salonları\r\n"
    ).encode("cp1254")
    sayfa = csv_yukle(panel, yeni).text
    assert "2 tahta değişecek, 0 değişmiyor, 0 hatalı" in sayfa and "Fen laboratuvarları, Sınav salonları" in sayfa
    assert sorgu("SELECT bina FROM tahta WHERE id = ?", a)[0]["bina"] == ""  # önizleme yazmaz
    yanit = uygula(panel, sayfa)
    assert "2 tahta, 0 hatalı satır" in ileti(yanit)
    sa, sb = tahta_satiri(a), tahta_satiri(b)
    assert (sa["bina"], sa["kat"], sa["duzeyler"], sa["devre"], sa["subeler"], sa["derslik"]) == ("A Blok", 0, "9", "sabah", "9/A", "9/A")
    assert (sb["kat"], sb["duzeyler"], sb["devre"]) == (2, "hazirlik,10", "ogle")
    assert len(sorgu("SELECT * FROM tahta_grubu_uye")) == 3
    # Dışa aktarılan dosya aynen geri yüklenince hiçbir şey değişmez (UTF-8 BOM, ;).
    sayfa = csv_yukle(panel, panel.get("/tahtalar.csv").content).text
    assert "0 tahta değişecek, 2 değişmiyor, 0 hatalı" in sayfa
    # Virgül ayraçlı UTF-8 (BOM'suz)
    sayfa = csv_yukle(panel, f"id,kat\n{a},1\n".encode()).text
    assert "1 tahta değişecek" in sayfa
    uygula(panel, sayfa)
    assert tahta_satiri(a)["kat"] == 1
    assert sorgu("SELECT * FROM kayit WHERE islem = 'Tahta alanları içe aktarıldı'")


def test_csv_bilinmeyen_id_ve_hatali_kat_satiri_atlanir(iki_tahta, panel):
    a, b = (kimlik(x) for x in iki_tahta)
    icerik = f"id;kat;devre\n999;1;\n{a};çatı katı;\n{b};3;Sabah\n{b};4;\n".encode()
    sayfa = csv_yukle(panel, icerik).text
    assert "1 tahta değişecek, 0 değişmiyor, 3 hatalı" in sayfa
    assert "Bu kimlikte tahta yok" in sayfa and "Kat tanınmadı" in sayfa and "birden çok kez" in sayfa
    uygula(panel, sayfa)
    assert tahta_satiri(a)["kat"] is None and tahta_satiri(b)["kat"] == 3
    assert csv_yukle(panel, b"ad;kat\nx;1\n").status_code == 400
    assert "Dosya en çok" in csv_yukle(panel, b"id\n" + b"1\n" * 1_100_000).text


def test_csv_eksik_sutuna_dokunulmaz_bos_hucre_temizler(iki_tahta, panel):
    a = kimlik(iki_tahta[0])
    panel.post(f"/tahta/{a}/kaydet", data={"ad": "Z-01", "derslik": "D-1", "eylem": "kaydet", "alanlar": "1",
                                            "bina": "A Blok", "kat": "1", "duzey": "9", "devre": "sabah"})  # fmt: skip
    uygula(panel, csv_yukle(panel, f"id;kat\n{a};2\n".encode()).text)
    satir = tahta_satiri(a)
    assert (satir["kat"], satir["bina"], satir["duzeyler"], satir["devre"]) == (2, "A Blok", "9", "sabah")
    uygula(panel, csv_yukle(panel, f"id;bina;ad;derslik\n{a};;;\n".encode()).text)
    satir = tahta_satiri(a)
    assert (satir["bina"], satir["ad"], satir["derslik"]) == ("", "Z-01", "D-1")  # ad/derslik boşsa değişmez


def test_csv_disa_aktarmada_ip_mac_yok(iki_tahta, panel):
    metin = panel.get("/tahtalar.csv").content.decode("utf-8-sig")
    assert "10.0.0.20" not in metin and "aa:bb" not in metin.lower()
    assert "ip" not in metin.splitlines()[0].split(";") and "mac" not in metin.splitlines()[0].split(";")


def test_csv_formul_kacisi_ve_ice_aktarma_yetkisi(iki_tahta, panel):
    a = kimlik(iki_tahta[0])
    panel.post(f"/tahta/{a}/kaydet", data={"ad": "=HYPERLINK(1)", "eylem": "kaydet"})
    assert ";'=HYPERLINK(1);" in panel.get("/tahtalar.csv").content.decode("utf-8-sig")
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    assert panel.get("/tahtalar.csv").status_code == 200
    assert "yönetici" in ileti(panel.get("/tahtalar/ice-aktar"))
    assert "yönetici" in ileti(csv_yukle(panel, f"id;kat\n{a};2\n".encode()))


def test_menu_ve_rol_gorunurlugu(iki_tahta, panel):
    sayfa = panel.get("/gruplar").text
    for parca in ('href="/gruplar" aria-current="page"', 'href="/acil"', 'href="/ayarlar"'):
        assert parca in sayfa, parca
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    sayfa = panel.get("/").text
    assert 'href="/acil"' in sayfa
    # Yan menüde (0.15.0) idareciye yönetici öğesi çizilmez; "Yönetim" kümesi İşlem kaydı için idarecide de vardır.
    menu = sayfa.split('id="menu"')[1].split("</aside>")[0]
    for yol in ("/kullanicilar", "/ayarlar", "/yedekler", "/ekle", "/gruplar"):
        assert f'href="{yol}"' not in menu, yol
