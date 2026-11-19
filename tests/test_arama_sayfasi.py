"""Genel arama uçları (0.20.0): GET /ara, GET /api/ara, kabuktaki kutu; gizlilik ve rol sızıntısı.

Bağlayıcı: dizine ve sonuçlara kişi verisi girmez; arama metni hiçbir yere yazılmaz; idareci, yöneticiye özel
sayfanın adını da adresini de sayısını da görmez. Bütün veriler UYDURMADIR ("zzq…" imleri gerçek bir şeye benzemesin
diye seçildi).
"""

from __future__ import annotations

import html
import logging
import re
import sqlite3
from pathlib import Path

import pytest
from test_kabuk import alt_cubuk, karistir, yan_menu
from test_yoklama import ayar_kaydet, hazir  # noqa: F401 (fikstür)
from yardimci import gir, kimlik, kullanici_ekle, sorgu, tahta_ekle, yeni_ajan_durumu

from tahta_sunucu import arama, tema, vt, web

KOK = Path(web.__file__).resolve().parent
STIL = (KOK / "statik" / "stil.css").read_text(encoding="utf-8")
BETIK = (KOK / "statik" / "panel.js").read_text(encoding="utf-8")
TABAN = (KOK / "sablonlar" / "taban.html").read_text(encoding="utf-8")
SABLON = (KOK / "sablonlar" / "ara.html").read_text(encoding="utf-8")
ARAMA_JS = BETIK.split("function aramaKur")[1].split("function sayacKur")[0]

# Hiçbir sorguda sonuç vermemesi gereken imler (kişi, içerik, cihaz kimliği, bekleyen tahta).
YASAK_IMLER = [
    "Zzqogr", "Zzqsoyad", "98765", "Zzqhoca", "Zzqsoy", "QQZ7", "zzqidareci", "Zzqgorunen", "Zzqusb", "Zzqbaslik",
    "zzqmetin", "Zzqplan", "zzqplanmetni", "zzqariza", "zzqcozum", "Zzqsinav", "Zzqders", "zzqaciklama", "10.9.8.7",
    "zzqmakine", "ZZQ-001", "zzqnot", "Zzqbekleyen", "zzqbekmakine", "Ayşe YILMAZ", "Burak", "1047", "Örnek",
]  # fmt: skip
YONETICI_PARCALARI = ("/ayarlar", "/yedekler", "/ekle", "/gruplar", "/tahtalar/ice-aktar", "/ogretmen-programi",
                      "/program/aktar", "/program/gecmis", "sablonlar", "onay-bekleyen")  # fmt: skip
YONETICI_BASLIKLARI = ("Yedekler", "Ayarlar", "Gruplar", "Şablonlar", "Ajan kurulum paketi", "Önceki programlar",
                       "Öğretmen programı", "Kilit ve güvenlik", "Veri saklama ve yedek", "Panel kullanıcıları",
                       "Yedek al, indir", "Tahta ekle", "Tahta grubu", "Onay bekleyen", "Acil durum şablonları")  # fmt: skip


@pytest.fixture()
def tohum(hazir, panel, tahta):  # noqa: F811
    """Yoklama fikstürünün (10/A, 10/B, bir öğretmen, "10A Tahtası") üstüne her gizli tabloya uydurma, imli veri."""
    kullanici_ekle(panel, "zzqidareci")
    zzq = kimlik(tahta_ekle(panel, tahta, "Zzqtahta 9-Q", yeni_ajan_durumu(), bina="Zzqblok", kat="1"))
    panel.post("/ekle", data={"eylem": "ac"})
    kod = panel.get("/ekle").text.split('class="buyuk-kod">')[1].split("<")[0]
    bekleyen = tahta.post("/ajan/kaydol", json={"kod": kod, "makine_adi": "zzqbekmakine", "surum": "0.19.0"}).json()["tahta_id"]
    with vt.islem() as b:
        b.execute("UPDATE kullanici SET gorunen_ad = 'Zzqgorunen' WHERE ad = 'zzqidareci'")
        b.execute("UPDATE tahta SET ip = '10.9.8.7', mac = 'aa:bb:cc:dd:ee:ff', makine_adi = 'zzqmakine', demirbas_no = 'ZZQ-001', "
                  "envanter_notu = 'zzqnot' WHERE id = ?", (zzq,))  # fmt: skip
        b.execute("UPDATE tahta SET ad = 'Zzqbekleyen', bina = 'Zzqbekleyen' WHERE id = ?", (bekleyen,))
        b.execute("INSERT INTO ogrenci (sube, okul_no, ad, soyad, aktif, guncelleme) VALUES ('9/A', '98765', 'Zzqogr', 'Zzqsoyad', 1, 0)")
        ogrenci = b.execute("SELECT id FROM ogrenci WHERE okul_no = '98765'").fetchone()["id"]
        b.execute("INSERT INTO ogretmen (ad, soyad) VALUES ('Zzqhoca', 'Zzqsoy')")
        ogretmen = b.execute("SELECT id FROM ogretmen WHERE ad = 'Zzqhoca'").fetchone()["id"]
        b.execute("INSERT INTO ogretmen_pin (ogretmen_id, kod) VALUES (?, 'QQZ7')", (ogretmen,))
        b.execute("INSERT INTO usb_anahtar (kimlik, gizli_ozet, sahip_turu, ogretmen_id, etiket, olusturan, olusturma) "
                  "VALUES ('ZZQKIMLK', 'x', 'ogretmen', ?, 'Zzqusb', 'yonetici', 0)", (ogretmen,))  # fmt: skip
        b.execute("INSERT INTO duyuru (baslik, metin, sure_sn, kapatilabilir, hedef, olusturan, olusturma) "
                  "VALUES ('Zzqbaslik', 'zzqmetin', 60, 1, 'tumu', 'yonetici', 0)")  # fmt: skip
        b.execute("INSERT INTO duyuru_plani (baslik, metin, sure_sn, kapatilabilir, hedef_json, tekrar, saat, baslangic, bitis, gunler, "
                  "gecerlilik, olusturan, olusturma) VALUES ('Zzqplan', 'zzqplanmetni', 60, 1, '{}', 'gunluk', '13:00', '2026-11-16', "
                  "'2026-11-20', '0,1,2,3,4', 0, 'yonetici', 0)")  # fmt: skip
        b.execute("INSERT INTO ariza (tahta_id, kaynak, kategori, aciklama, bildiren, olusturma, guncelleme, cozum_notu) "
                  "VALUES (?, 'panel', 'diger', 'zzqariza', 'yonetici', 0, 0, 'zzqcozum')", (zzq,))  # fmt: skip
        b.execute("INSERT INTO sinav (ad, baslangic, olusturan, olusturma, guncelleme) VALUES ('Zzqsinav', 0, 'yonetici', 0, 0)")
        b.execute("INSERT INTO ogretmen_program (sube, gun, ders_no, baslangic, bitis, ders_adi, ogretmen_id, guncelleme) "
                  "VALUES ('9/A', 0, 1, '08:30', '09:10', 'Zzqders', ?, 0)", (ogretmen,))  # fmt: skip
        b.execute("INSERT INTO yoklama_mazeret (ogrenci_id, bas_tarih, bit_tarih, tur, giren, olusturma) "
                  "VALUES (?, '2026-11-16', '2026-11-16', 'raporlu', 'yonetici', 0)", (ogrenci,))  # fmt: skip
        b.execute("INSERT INTO tahta_grubu (ad, aciklama, olusturan, olusturma) VALUES ('Zzqgrup', 'zzqaciklama', 'yonetici', 0)")
    return {"tahta": zzq, "bekleyen": bekleyen}


def govde(sayfa: str) -> str:
    return sayfa.split('<main id="icerik"')[1].split("</main>")[0]


def sonuc_yollari(sayfa: str) -> list[str]:
    """Sonuç listesindeki hedefler (sonuç sayfasının gövdesindeki `ayar-liste` bağlantıları)."""
    return [html.unescape(y) for y in re.findall(r'<li><a href="([^"]+)">', govde(sayfa))]


def ara(panel, q: str):
    yanit = panel.get("/ara", params={"q": q})
    assert yanit.status_code == 200, q
    return yanit.text


def api(panel, q: str) -> dict:
    yanit = panel.get("/api/ara", params={"q": q})
    assert yanit.status_code == 200, q
    return yanit.json()


def izle(islev) -> list[str]:
    """İşlev boyunca veritabanına giden bütün SQL deyimleri (parametreleri açılmış)."""
    deyimler: list[str] = []
    asil = sqlite3.connect

    def izli(*a, **kw):
        baglanti = asil(*a, **kw)
        baglanti.set_trace_callback(deyimler.append)
        return baglanti

    sqlite3.connect = izli
    try:
        islev()
    finally:
        sqlite3.connect = asil
    return deyimler


# ---- oturum, başlık ------------------------------------------------------------------------------------------
def test_ara_oturumsuz_girise_yonlenir(panel, tohum):
    panel.cookies.clear()
    yanit = panel.get("/ara?q=Zzqtahta")
    assert yanit.status_code == 303 and yanit.headers["location"] == "/giris"
    assert "Zzqtahta" not in yanit.headers["location"] and "zzq" not in yanit.text.lower()


def test_ara_kurulumdan_once_kuruluma_yonlenir(panel):
    assert panel.get("/ara?q=x").headers["location"] == "/kurulum"
    assert panel.get("/api/ara?q=xx").status_code == 401


def test_api_ara_oturumsuz_401(panel, tohum):
    panel.cookies.clear()
    yanit = panel.get("/api/ara?q=Zzqtahta")
    assert yanit.status_code == 401 and yanit.json() == {"hata": "Oturum gerekli."}
    assert "zzq" not in yanit.text.lower()  # hata gövdesi sorguyu yankılamaz, sonuç vermez


def test_ara_no_store(panel, tohum):
    for yol in ("/ara", "/ara?q=zil", "/api/ara?q=zil", "/api/ara?q=z"):
        yanit = panel.get(yol)
        assert yanit.status_code == 200 and yanit.headers["cache-control"] == "no-store", yol
        assert yanit.headers["referrer-policy"] == "same-origin" and "content-security-policy" in yanit.headers


def test_ara_sayfa_basliginda_sorgu_yok(panel, tohum):
    for q in ("zil", "Zzqtahta", "Zzqogr"):
        sayfa = ara(panel, q)
        assert "<title>Arama · Tahta Kontrol</title>" in sayfa
        assert q not in sayfa.split("<head>")[1].split("</head>")[0]
    assert "<h1>Arama</h1>" in ara(panel, "zil") and "{% block baslik %}Arama · Tahta Kontrol{% endblock %}" in SABLON


# ---- gizlilik: kişi verisi, içerik, cihaz kimliği ------------------------------------------------------------
def test_kisisel_veri_hicbir_sorguda_cikmaz(panel, tohum):
    for rol in ("yonetici", "zzqidareci"):
        gir(panel, rol)
        for im in YASAK_IMLER:
            sayfa = ara(panel, im)
            g = govde(sayfa)
            assert sonuc_yollari(sayfa) == [] and 'id="ara-bos"' in g and "data-grup=" not in g, (rol, im)
            assert "için 0 sonuç" in g, (rol, im)
            # İm gövdede yalnız yankıdır: arama kutusunun değeri ve sonuç satırı.
            assert g.lower().count(html.escape(im).lower()) == 2, (rol, im)
            veri = api(panel, im)
            assert veri["sonuclar"] == [] and veri["toplam"] == 0 and veri["fazla"] is False, (rol, im)
    # Ortak önek: yalnız onaylı tahtanın (ve yöneticide grubun) ADI döner.
    gir(panel, "yonetici")
    assert sonuc_yollari(ara(panel, "zzq")) == [f"/tahta/{tohum['tahta']}", "/gruplar#grup-1"]
    assert [(s["tur"], s["ad"]) for s in api(panel, "zzq")["sonuclar"]] == [("tahta", "Zzqtahta 9-Q"), ("grup", "Zzqgrup")]
    yonetici = govde(ara(panel, "zzq"))
    gir(panel, "zzqidareci")
    assert sonuc_yollari(ara(panel, "zzq")) == [f"/tahta/{tohum['tahta']}"]
    assert [(s["tur"], s["ad"]) for s in api(panel, "zzq")["sonuclar"]] == [("tahta", "Zzqtahta 9-Q")]
    idareci = govde(ara(panel, "zzq"))
    for g in (yonetici, idareci):
        kucuk = g.lower()
        for im in ("zzqbekleyen", "zzqaciklama", "zzqnot", "10.9.8.7", "aa:bb:cc", "zzqmakine", "zzq-001", "zzqogr", "zzqhoca",
                   "zzqusb", "zzqbaslik", "zzqsinav", "zzqders", "zzqariza", "zzqgorunen", "zzqidareci", "98765"):  # fmt: skip
            assert im not in kucuk, im
    assert "zzqgrup" not in idareci.lower() and "Zzqgrup" in yonetici


def test_sonucsuz_notu_sabittir_var_yok_kahini_degil(panel, tohum):
    """Kişi adı aranınca çıkan not, hiçbir şeye benzemeyen sorgudakiyle bayt bayt aynıdır."""

    def notu(q: str) -> str:
        return re.search(r'<div class="bos-not ara-bos" id="ara-bos">.*?</div>', ara(panel, q), re.S).group(0)

    yonetici = {notu(q) for q in ("Zzqogr", "Zzqhoca Zzqsoy", "98765", "qqxyzw", "Zzqbekleyen", "zzqidareci", "Zzqsinav")}
    assert len(yonetici) == 1
    def duz(parca: str) -> str:
        return " ".join(re.sub(r"<[^>]+>", " ", parca).split())

    yonetici_notu = duz(yonetici.pop())
    assert yonetici_notu == (
        "Sonuç bulunamadı. Sayfa, iş, ayar, tahta ve şube adı aranır. "
        "Yazımı denetleyin ya da sözcüğün yalnız başını yazın (ör. “yokl”, “duy”). "
        "Öğrenci ve öğretmen adları aranmaz; bir öğrencinin yoklaması için Yoklama › Şube defteri 'nden şubesini açın. "
        "Sık yapılan işler için aramayı temizleyin ."
    )
    assert "yönetici" not in yonetici_notu.lower()
    gir(panel, "zzqidareci")
    # Yazım hatası, yetkisi olmayan konu ve kişi adı: idarecide de not tektir (yol gösterir ama sorguya göre değişmez).
    idareci = {notu(q) for q in ("Zzqogr", "qqxyzw", "ayar", "yedek", "Zzqgrup", "yoklma", "şifre", "logo")}
    assert len(idareci) == 1
    metin = duz(idareci.pop())
    assert metin.startswith("Sonuç bulunamadı. Sayfa, iş, tahta ve şube adı aranır.") and "ayar" not in metin.lower()
    # İdareciye ek sabit satır: sayfa adı ve adres taşımaz (hangi sayfanın var olduğunu söylemez).
    assert "Yalnız yöneticinin açabildiği sayfalar sonuçlarda görünmez." in metin and "Yazımı denetleyin" in metin
    for parca in (*YONETICI_PARCALARI, *YONETICI_BASLIKLARI):
        assert parca not in metin, parca
    assert ".ara-bos { max-inline-size: 48rem;" in STIL  # not, sonuç kartlarıyla aynı ende
    assert '<a href="/yoklama/sube">Şube defteri</a>' in ara(panel, "qqxyzw")


def test_tahta_ve_sube_adi_bulunur(panel, tohum):
    for rol in ("yonetici", "zzqidareci"):
        gir(panel, rol)
        for q in ("zzqtahta", "zzqblok", "9-q", "9q", "9/q", "ZZQTAHTA"):
            assert f"/tahta/{tohum['tahta']}" in sonuc_yollari(ara(panel, q)), (rol, q)
            assert f"/tahta/{tohum['tahta']}" in [s["yol"] for s in api(panel, q)["sonuclar"]], (rol, q)
        for q in ("10/A", "10a", "10-a"):
            assert sonuc_yollari(ara(panel, q))[0] == "/yoklama/sube?sube=10%2FA", (rol, q)
        sayfa = ara(panel, "10/a")
        assert '<b>10/A şube defteri</b><small>Yoklama › Şube defteri</small>' in sayfa
        assert panel.get("/yoklama/sube?sube=10%2FA").status_code == 200
        assert panel.get(f"/tahta/{tohum['tahta']}").status_code == 200
    satir = ara(panel, "zzqtahta")
    assert "<b>Zzqtahta 9-Q</b><small>Tahta · Zzqblok · 1. kat</small>" in satir
    # Yoklama kapalıyken şube girdisi yok (şube defteri sayfası da kapalıdır).
    gir(panel, "yonetici")
    ayar_kaydet(panel, yk_etkin=None)
    assert not [y for y in sonuc_yollari(ara(panel, "10/a")) if "sube=" in y]
    assert not [s for s in api(panel, "10/a")["sonuclar"] if s["tur"] == "sube"]


def test_idareci_sonucunda_yonetici_basligi_ve_adresi_yok(panel, tohum):
    sorgular = ("ayar", "yedek", "kilit kodu", "grup", "ajan", "kvkk", "kullanıcı", "şablon", "içe aktar", "onay", "tahta",
                "program", "a", "e", "öğretmen", "zzq")  # fmt: skip
    toplam = {}
    for q in sorgular:
        sayfa, veri = ara(panel, q), api(panel, q) if len(q) > 1 else {"sonuclar": [], "toplam": None}
        toplam[q] = (len(sonuc_yollari(sayfa)), veri["toplam"])
    yonetici_metni = " ".join(govde(ara(panel, q)) for q in sorgular)
    for parca in (*YONETICI_PARCALARI, *YONETICI_BASLIKLARI):
        assert parca in yonetici_metni, parca
    assert any(any(p in s["yol"] for p in YONETICI_PARCALARI) for q in sorgular[:9] for s in api(panel, q)["sonuclar"])
    gir(panel, "zzqidareci")
    for q in sorgular:
        sayfa = ara(panel, q)
        g = govde(sayfa)
        for parca in (*YONETICI_PARCALARI, *YONETICI_BASLIKLARI):
            assert parca not in g, (q, parca)
        yollar = sonuc_yollari(sayfa)
        assert len(yollar) < toplam[q][0], q  # sayı da süzülmüş kümedendir
        assert f"için {len(yollar)} sonuç" in g, q
        if len(q) > 1:
            veri = api(panel, q)
            ham = panel.get("/api/ara", params={"q": q}).text
            for parca in YONETICI_PARCALARI:
                assert parca not in ham, (q, parca)
            assert veri["toplam"] < toplam[q][1] and veri["toplam"] == len(yollar), q
    # Sorgu boşken gösterilen kısa yollar da rolle süzülür.
    bos = govde(panel.get("/ara").text)
    for parca in (*YONETICI_PARCALARI, *YONETICI_BASLIKLARI):
        assert parca not in bos, parca
    # İdarecinin açabildiği her sonuç gerçekten açılır (200); yönetici sayfasına götüren sonuç yoktur.
    for q in ("tahta", "program", "a", "yoklama"):
        for yol in sonuc_yollari(ara(panel, q)):
            assert panel.get(yol).status_code == 200, (q, yol)


def test_yonetici_sonuclarinin_hepsi_acilir(panel, tohum):
    gorulen = set()
    for q in ("a", "e", "tahta", "ayar", "zzq", "10", "k", "p", "y"):
        for yol in sonuc_yollari(ara(panel, q)):
            if yol not in gorulen:
                gorulen.add(yol)
                assert panel.get(yol).status_code == 200, (q, yol)
    assert len(gorulen) >= 55
    for yol in sonuc_yollari(panel.get("/ara").text):
        assert panel.get(yol).status_code == 200, yol


# ---- sorgu hiçbir yere yazılmaz ----------------------------------------------------------------------------
def test_arama_islem_kaydina_ve_veritabanina_yazmaz(panel, tohum):
    once = sorgu("SELECT COUNT(*) AS n FROM kayit")[0]["n"]

    def istekler() -> None:
        for q in ("Zzqiz arama", "zil", "Zzqtahta", "Zzqogr", "9/a", ""):
            assert panel.get("/ara", params={"q": q}).status_code == 200
            assert panel.get("/api/ara", params={"q": q}).status_code == 200

    deyimler = izle(istekler)
    assert len(deyimler) > 20
    for deyim in deyimler:
        assert not re.match(r"\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|DROP|ALTER)\b", deyim, re.I), deyim
    assert sorgu("SELECT COUNT(*) AS n FROM kayit")[0]["n"] == once
    assert not sorgu("SELECT 1 FROM kayit WHERE lower(ayrinti) LIKE '%zzqiz%' OR lower(islem) LIKE '%zzqiz%'")
    assert not sorgu("SELECT 1 FROM ayar WHERE lower(deger) LIKE '%zzqiz%'")
    assert "zzqiz" not in " ".join(d.lower() for d in deyimler)  # sorgu SQL'e parametre olarak bile gitmez


def test_arama_gunluge_yazmaz(panel, tohum, caplog):
    with caplog.at_level(logging.DEBUG):
        ara(panel, "Zzqgunluk imi")
        api(panel, "Zzqgunluk imi")
    bizim = [k for k in caplog.records if k.name != "httpx"]  # sınama istemcisinin kendi kaydı değil
    assert "zzqgunluk" not in " ".join(k.getMessage() for k in bizim).lower()


def test_erisim_gunlugu_kapali():
    kaynak = (KOK / "sunucu.py").read_text(encoding="utf-8")
    assert '"access_log": False' in kaynak and "access_log=True" not in kaynak and '"access_log": True' not in kaynak


def test_arama_kodunda_kayit_ve_gunluk_cagrisi_yok():
    kaynak = (KOK / "web.py").read_text(encoding="utf-8")
    dilim = kaynak.split("# ---- genel arama (0.20.0)")[1].split('@uygulama.post("/islem")')[0]
    for yasak in ("kayit_dus", "gunluk.", "ayar_yaz", "set_cookie", "print("):
        assert yasak not in dilim, yasak
    saf = Path(arama.__file__).read_text(encoding="utf-8")
    for yasak in ("kayit_dus", "logging", "ayar_yaz", "INSERT", "UPDATE ", "DELETE", "SELECT *", "fastapi", "import web", "from .web"):
        assert yasak not in saf, yasak


def test_arama_kisi_tablolarina_sorgu_atmaz(panel, tohum):
    """/api/ara: oturum sorgusu + en çok 4 dar dizin sorgusu; kişi ve içerik tablolarına hiç gidilmez."""
    izinli = {"oturum", "kullanici", "tahta", "ayar", "ogrenci", "tahta_grubu"}
    for rol in ("yonetici", "zzqidareci"):
        gir(panel, rol)
        for q in ("Zzqogr", "Zzqhoca", "zzqtahta", "10/a", "zil", "98765", "Zzqusb"):
            deyimler = [d for d in izle(lambda q=q: api(panel, q)) if d.lstrip().upper().startswith("SELECT")]
            assert 1 <= len(deyimler) <= 5, (rol, q, deyimler)
            for deyim in deyimler:
                tablolar = set(re.findall(r"(?:FROM|JOIN)\s+([a-z_]+)", deyim))
                assert tablolar <= izinli, deyim
                assert "*" not in deyim.replace("k.*", "") and "COUNT" not in deyim, deyim
                if "kullanici" in tablolar:
                    assert "FROM oturum" in deyim and "belirtec_ozet" in deyim, deyim  # yalnız oturum denetimi
                if "ogrenci" in tablolar:
                    assert deyim.strip() == "SELECT DISTINCT sube FROM ogrenci WHERE aktif = 1", deyim
                if tablolar == {"tahta"}:
                    assert deyim.strip() == "SELECT id, ad, derslik, bina, kat, subeler FROM tahta WHERE durum = 'onayli'", deyim
                if tablolar == {"tahta_grubu"}:
                    assert rol == "yonetici" and deyim.strip() == "SELECT id, ad FROM tahta_grubu", deyim
        if rol != "yonetici":  # idareci isteğinde grup tablosu sorgulanmaz bile
            assert not [d for d in izle(lambda: api(panel, "zzqgrup")) if "tahta_grubu" in d]


def test_arama_sorgu_sayisi_tahta_sayisindan_bagimsiz(panel, tohum):
    def say() -> int:
        return len([d for d in izle(lambda: api(panel, "9/a")) if d.lstrip().upper().startswith("SELECT")])

    az = say()
    with vt.islem() as b:
        b.executemany(
            "INSERT INTO tahta (ad, anahtar_ozet, durum, kayit_zamani, bina, kat, subeler) VALUES (?, 'x', 'onayli', 0, ?, ?, ?)",
            [(f"T-{i}", f"Blok {i % 3}", i % 4, f"9/{chr(65 + i % 12)}") for i in range(60)],
        )
        b.executemany(
            "INSERT INTO ogrenci (okul_no, ad, soyad, sube, aktif, guncelleme) VALUES (?, 'Uydurma', 'ÖĞRENCİ', ?, 1, 0)",
            [(str(6000 + i), f"9/{chr(65 + i % 12)}") for i in range(400)],
        )
        b.executemany("INSERT INTO tahta_grubu (ad, aciklama, olusturan, olusturma) VALUES (?, '', 'x', 0)", [(f"G{i}",) for i in range(30)])
    cok = say()
    assert az == cok and cok <= 6
    veri = api(panel, "9/a")
    assert veri["sonuclar"][0]["yol"] == "/yoklama/sube?sube=9%2FA" and len(veri["sonuclar"]) <= arama.ONERI_EN_COK
    assert veri["toplam"] >= 6 and veri["fazla"] is (veri["toplam"] > arama.ONERI_EN_COK)


def test_api_ara_kisa_sorguda_veritabanina_gitmez(panel, tohum):
    for q in ("", "z", " 9 ", "\t"):
        deyimler = [d for d in izle(lambda q=q: api(panel, q)) if not d.startswith("PRAGMA")]
        assert len(deyimler) == 1 and "FROM oturum" in deyimler[0], q  # yalnız oturum denetimi
        assert api(panel, q) == {"sorgu": q.strip(), "sonuclar": [], "toplam": 0, "fazla": False}
    # Sayfa boş sorguda devingen dizini kurmaz (tahta ve öğrenci tablosuna gitmez).
    deyimler = izle(lambda: panel.get("/ara"))
    assert not [d for d in deyimler if "FROM ogrenci" in d or "FROM tahta_grubu" in d or "subeler FROM tahta" in d]


def test_api_durum_yukunde_arama_yok(panel, tohum):
    """/api/durum sık çağrılır: sözleşmesi ve sorguları aramadan etkilenmez."""
    assert set(panel.get("/api/durum").json()) == {"tahtalar", "bekleyen", "acil", "program", "bekleyen_is"}
    kaynak = (KOK / "web.py").read_text(encoding="utf-8")
    durum = kaynak.split('@uygulama.get("/api/durum")')[1].split("    # ---- genel arama")[0]
    assert "async def api_durum" in durum and "bekleyen_is" in durum
    sayfa_islevi = kaynak.split("    def sayfa(istek: Request")[1].split("\n    def ")[0]
    assert "arama" not in durum and "arama" not in sayfa_islevi and "ARAMA" not in sayfa_islevi


# ---- girdi sağlamlığı ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("q", ['"><script>alert(1)</script>', "</title><b>kalin</b>", "{{7*7}}", "%00", "'; DROP TABLE tahta;--",
                               "<img src=x onerror=alert(1)>", "\x00\x01", "../../etc", "javascript:alert(1)"])  # fmt: skip
def test_ara_sorgusu_html_kacisli(panel, tohum, q):
    sayfa = ara(panel, q)
    g = govde(sayfa)
    assert "<script>alert" not in sayfa and "<b>kalin</b>" not in sayfa and "<img src=x" not in sayfa
    assert "49" not in re.sub(r"<[^>]+>", "", g) or "{{7*7}}" not in q  # şablon ifadesi çalışmaz
    assert sayfa.count("<title>") == 1 and sayfa.count("</title>") == 1
    veri = api(panel, q)
    assert veri["sorgu"] == arama.sorgu_duzelt(q) and "\x00" not in veri["sorgu"] and set(veri) == {"sorgu", "sonuclar", "toplam", "fazla"}
    assert sorgu("SELECT COUNT(*) AS n FROM tahta")[0]["n"] >= 3


def test_ara_uzun_sorgu(panel, tohum):
    uzun = "zil" + "x" * 5000
    sayfa = ara(panel, uzun)
    yanki = re.search(r'id="ara-q" name="q" value="([^"]*)"', sayfa).group(1)
    assert len(yanki) == 60 and "x" * 61 not in sayfa
    assert len(api(panel, uzun)["sorgu"]) == 60
    assert panel.get("/ara", params=[("q", "zil"), ("q", "yedek")]).status_code == 200  # yinelenen parametre patlatmaz


def test_api_ara_sozlesmesi(panel, tohum):
    for q in ("ta", "ayar", "zzq", "10", "program", "qqxyzw", "a b"):
        veri = api(panel, q)
        assert set(veri) == {"sorgu", "sonuclar", "toplam", "fazla"}, q
        assert veri["sorgu"] == q and isinstance(veri["toplam"], int) and isinstance(veri["fazla"], bool)
        assert len(veri["sonuclar"]) <= arama.ONERI_EN_COK == 8 and veri["toplam"] >= len(veri["sonuclar"])
        assert veri["fazla"] is (veri["toplam"] > len(veri["sonuclar"]))
        for s in veri["sonuclar"]:
            assert set(s) == {"tur", "ad", "yer", "yol"}, q
            assert s["yol"].startswith("/") and not s["yol"].startswith("//") and "\\" not in s["yol"]
            assert s["tur"] in arama.TUR_SIRASI and s["ad"]
    assert api(panel, "ayar")["fazla"] is True and len(api(panel, "ayar")["sonuclar"]) == 8


# ---- sonuç sayfası -------------------------------------------------------------------------------------------
def test_ara_sayfasi_gruplu_ve_sinirli(panel, tohum):
    sayfa = ara(panel, "a")
    g = govde(sayfa)
    assert re.findall(r'data-grup="([a-z]+)"', g) == ["sayfa", "ayar", "sube", "tahta"]  # "a": 10/A şubesi de
    basliklar = re.findall(r'<h2 id="ara-grup-[a-z]+">([^<]+) <span class="not">· (\d+)</span></h2>', g)
    assert [b[0] for b in basliklar] == ["Sayfalar ve işler", "Ayarlar", "Şubeler", "Tahtalar"]
    assert sum(int(b[1]) for b in basliklar) == len(sonuc_yollari(sayfa))
    assert [b[0] for b in re.findall(r'<h2 id="ara-grup-[a-z]+">([^<]+) <span class="not">· (\d+)', govde(ara(panel, "zzq")))] == ["Tahtalar", "Gruplar"]
    assert re.findall(r'<h2 id="ara-grup-[a-z]+">([^<]+) <', govde(ara(panel, "10")))[:1] == ["Şubeler"]
    assert '<p class="ayar-ara-sonuc" id="ara-sonuc" role="status">“zzq” için 2 sonuç</p>' in ara(panel, "zzq")
    # Ayar sonucunda bölümün kısa açıklaması; vurgulama (<mark>) ve `| safe` yok.
    assert "<b>Veri saklama ve yedek</b><small>Ayarlar › Veri ve sistem · Öğretim yılı bitişi (KVKK)" in ara(panel, "kvkk")
    assert "<mark" not in sayfa and "| safe" not in SABLON and "|safe" not in SABLON
    # Sonuç sayfası 50 ile sınırlıdır.
    with vt.islem() as b:
        b.executemany("INSERT INTO tahta (ad, anahtar_ozet, durum, kayit_zamani) VALUES (?, 'x', 'onayli', 0)", [(f"Sinirtahta {i}",) for i in range(70)])
    cok = ara(panel, "sinirtahta")
    assert len(sonuc_yollari(cok)) == arama.SAYFA_EN_COK == 50 and "için 70 sonuç" in cok
    assert "İlk 50 sonuç gösteriliyor. Daha az sonuç için bir sözcük daha yazın." in cok
    assert "İlk 50 sonuç" not in sayfa


def test_ara_bosken_sik_isler_role_gore(panel, tohum):
    for adres in ("/ara", "/ara?q=", "/ara?q=%20%20"):
        sayfa = panel.get(adres).text
        g = govde(sayfa)
        assert '<h2 id="ara-sik">Sık işler</h2>' in g and 'id="ara-bos"' not in g and 'id="ara-sonuc"' not in g
        assert sonuc_yollari(sayfa) == [s["yol"] for s in arama.sik_isler(web.ARAMA_SABIT, "yonetici")]
        assert 1 <= len(sonuc_yollari(sayfa)) <= 8 and sonuc_yollari(sayfa)[0] == "/duyurular/yeni"  # döküm değil
        assert re.search(r'<input type="search" id="ara-q" name="q" value=""[^>]* autofocus>', g)
        assert "zzq" not in g.lower()  # devingen girdi (tahta, şube, grup) yok
    assert " autofocus" not in govde(ara(panel, "zil"))  # dolu sonuçta klavye sonuçların üstüne açılmasın
    assert "Aranacak bir sözcük yazın." in ara(panel, "?!") and "Sık işler" in ara(panel, "?!")
    # Sayfa ve iş satırında baş simgesi yok: satır sonundaki okla aynı ok iki kez çizilmez.
    satirlar = re.findall(r"<li><a href=[^>]*>.*?</a></li>", g, re.S)
    assert satirlar and all(s.count("<svg") == 1 and '"><span class="ad">' in s for s in satirlar)
    assert ".ayar-liste a > .ad:first-child { grid-column: 1 / 4; }" in STIL
    # Ayar, tahta ve şube satırlarında baş simgesi durur.
    assert all(s.count("<svg") == 2 for s in re.findall(r"<li><a href=[^>]*>.*?</a></li>", govde(ara(panel, "kvkk")), re.S))
    assert "Sayfa, iş, ayar, tahta ve şube adı aranır. Öğrenci ve öğretmen adı aranmaz. Sonuçlar rolünüze göre süzülür." in sayfa
    gir(panel, "zzqidareci")
    idareci = panel.get("/ara").text
    assert sonuc_yollari(idareci) == [s["yol"] for s in arama.sik_isler(web.ARAMA_SABIT, "idareci")]
    assert 1 <= len(sonuc_yollari(idareci)) <= 8 and sonuc_yollari(idareci)[0] == "/duyurular/yeni"
    for yol in sonuc_yollari(idareci):
        assert panel.get(yol.split("#")[0]).status_code == 200, yol
    assert "Sayfa, iş, tahta ve şube adı aranır." in govde(idareci) and "ayar" not in re.sub(r"<[^>]+>", "", govde(idareci)).lower().replace("ayarla", "")


def test_ara_sayfasinda_dis_baglanti_ve_form_yan_etkisi_yok(panel, tohum):
    for q in ("", "a", "zzq", "qqxyzw"):
        g = govde(ara(panel, q))
        assert not re.findall(r'href="(?!/|#)[^"]*"', g), q  # yalnız site içi bağlantı
        formlar = re.findall(r"<form[^>]*>", g)
        assert formlar == ['<form class="ayar-ara" method="get" action="/ara" role="search" aria-label="Arama sayfası">'], q  # POST yok, komut yok
        # İki arama alanı ayrı adla duyulur; sayfa kutusu öneriyi yan menüdekiyle aynı koddan alır (data-ara-oneri).
        assert '<label class="gizli" for="ara-q">Aranacak sözcük</label>' in g and g.count("data-ara-oneri") == 1
        assert "data-genel-ara" not in g
        assert "<button" in g and g.count("<button") == 1 and 'method="post"' not in g


# ---- kabuk ---------------------------------------------------------------------------------------------------
def test_arama_menu_ogesi_degil(panel, tohum):
    ogeler = [o for k in web.MENU for o in k["ogeler"]]
    assert len(ogeler) == 10 and not [o for o in ogeler if "ara" in o["ad"].lower().split() or o["yol"].startswith("/ara")]
    for q in ("", "zil", "qqxyzw"):
        sayfa = ara(panel, q)
        assert 'aria-current="page"' not in sayfa and "data-secili" not in yan_menu(sayfa), q
        assert alt_cubuk(sayfa).count("<a ") == 5  # Bugün · Tahtalar · Duyurular · Yoklama · Menü
    assert yan_menu(ara(panel, "zil")).count("<li") == 10


def test_kabukta_arama_kutusu_her_sayfada_get_formu(panel, tohum):
    form = ('<form class="genel-ara" method="get" action="/ara" role="search">\n'
            '    <svg class="simge" aria-hidden="true"><use href="#s-ara"/></svg>\n'
            '    <label class="gizli" for="genel-ara">Ara</label>\n'
            '    <input type="search" id="genel-ara" name="q" maxlength="60" placeholder="Tahta, şube, sayfa ara" '
            'autocomplete="off" enterkeyhint="search" data-genel-ara>\n'
            '    <kbd aria-hidden="true">/</kbd>\n'
            "  </form>")  # fmt: skip
    for rol, yollar in (("yonetici", ("/", "/tahtalar", "/yoklama", "/ayarlar", "/ayarlar/veri", "/yoklama/sube", "/ara?q=zil")),
                        ("zzqidareci", ("/", "/tahtalar", "/yoklama", "/duyurular/yeni", "/ara"))):  # fmt: skip
        gir(panel, rol)
        for yol in yollar:
            sayfa = panel.get(yol).text
            menu = yan_menu(sayfa)
            assert form in menu and sayfa.count('class="genel-ara"') == 1, (rol, yol)
            assert menu.index('class="acil-dugme"') < menu.index('class="genel-ara"') < menu.index('class="yan-gezinme"'), yol
            ust = sayfa.split('class="ust-cubuk"')[1].split("</header>")[0]
            assert '<a class="ust-ara" href="/ara"><svg class="simge" aria-hidden="true"><use href="#s-ara"/></svg><span class="gizli">Ara</span></a>' in ust
            # Kutuda sorgu yankılanmaz (sonuç sayfasının kendi kutusu yankılar); combobox rolünü yalnız panel.js ekler.
            assert 'role="combobox"' not in sayfa and "aria-autocomplete" not in sayfa and 'id="genel-oneri"' not in sayfa
    assert 'role="combobox"' not in TABAN and "<button" not in TABAN.split('class="genel-ara"')[1].split("</form>")[0]
    # Yer tutucu iki rolde aynıdır ve "ayar" demez (idareciye olmayan şeyi vaat etmez).
    assert "ayar" not in form.split('placeholder="')[1].split('"')[0].lower()
    # Kabuksuz sayfalarda (giriş) kutu yok.
    panel.cookies.clear()
    giris = panel.get("/giris").text
    assert "genel-ara" not in giris and "ust-ara" not in giris and 'action="/ara"' not in giris


def test_ayarlar_ici_arama_degismedi(panel, tohum):
    sayfa = panel.get("/ayarlar?ara=kvkk").text
    assert '<form class="ayar-ara" method="get" action="/ayarlar" role="search">' in sayfa
    assert 'name="ara" value="kvkk"' in sayfa and "data-ayar-ara" in sayfa and '<p class="ayar-ara-sonuc" id="ayar-ara-sonuc" role="status">1 sonuç</p>' in sayfa
    assert 'href="/ara"' not in govde(sayfa)  # iki kutu yan yana bağlanmaz; genel kutu yan menüdedir
    for parca in ("function ayarAraKur", "AYAR_KATLA_KAYNAK", "function ayarSozcukleri", "  ayarAraKur();"):
        assert parca in BETIK, parca
    assert BETIK.count("AYAR_KATLA_KAYNAK") == 2 and "AYAR_KATLA" not in ARAMA_JS  # tek harf haritası; aramaya kopyalanmadı


# ---- betik ve stil (kaynak denetimi) ---------------------------------------------------------------------------
def test_arama_sablonu_ve_betigi_csp():
    for kaynak in (SABLON, TABAN.split('class="genel-ara"')[1].split("</form>")[0]):
        assert "style=" not in kaynak and "<style" not in kaynak and "<script" not in kaynak
        assert not re.search(r" on[a-z]+=", kaynak)
    for yasak in ("innerHTML", "insertAdjacentHTML", "outerHTML", "document.write", "localStorage", "sessionStorage", "document.cookie",
                  "indexedDB", "matchMedia", "innerWidth", "http", "form.id", "eval(", "AYAR_KATLA", "toLocaleLowerCase"):  # fmt: skip
        assert yasak not in ARAMA_JS, yasak
    for gerekli in ("textContent", "AbortController", '"/api/ara?q="', "encodeURIComponent", '"aria-activedescendant"', '"Escape"',
                    "stopPropagation", '"combobox"', '"listbox"', '"option"', '"aria-expanded"', '"aria-controls"', '"aria-selected"',
                    '"ArrowDown"', '"ArrowUp"', '"Enter"', '"pagehide"', '"focusout"', "siteIciYol(", 'credentials: "same-origin"',
                    "ARAMA_BEKLEME_MS", "ARAMA_EN_KISA"):  # fmt: skip
        assert gerekli in ARAMA_JS, gerekli
    assert "var ARAMA_BEKLEME_MS = 150;" in BETIK and "var ARAMA_EN_KISA = 2;" in BETIK
    assert "  kabukKur();\n  aramaKur();\n" in BETIK.replace("\r\n", "\n")
    # aramaKur, kabukKur diliminin DIŞINDADIR (kabuk testleri o dilimi inceler).
    assert "aramaKur" not in BETIK.split("function kabukKur")[1].split("function menuKur")[0]


def test_kisayol_sayfadan_ayirmaz():
    """Çekmece kipinde (telefon, 800 px, 1600 px'e kadar şube defteri) "/" sayfayı terk ETMEZ: çekmeceyi açıp kutuya
    odaklar. Eskiden /ara'ya gidiyordu; yarım kalmış duyuru ve fırçayla çalışılan defter tek tuşla kayboluyordu."""
    kisayol = ARAMA_JS.split('olay.key !== "/"')[1].split("function aramaOneriKur")[0]
    assert "location." not in kisayol and "assign" not in kisayol and "href" not in kisayol
    assert "kabukCekmeceAc(tetik)" in kisayol and "gorunur(sayfaKutusu)" in kisayol
    # preventDefault yalnız bir hedef bulununca: çekmece açılamıyorsa tuş olağan davranışında kalır.
    assert kisayol.index("return;\n        hedef = kutu;") < kisayol.index("olay.preventDefault();")
    kabuk = BETIK.split("function kabukKur")[1].split("function menuKur")[0]
    assert "kabukCekmeceAc = function (tetik) { ac(tetik); return acikMi(); };" in kabuk
    assert "var kabukCekmeceAc = null;" in BETIK


def test_oneri_kodu_tek_ve_iki_kutuda_ayni():
    assert BETIK.count("function aramaOneriKur(kutu, listeKimligi)") == 1 and BETIK.count('"/api/ara?q="') == 1
    assert 'aramaOneriKur(kutu, "genel-oneri");' in ARAMA_JS and 'aramaOneriKur(sayfaKutusu, "sayfa-oneri");' in ARAMA_JS
    assert 'document.querySelector("input[data-ara-oneri]")' in ARAMA_JS and "data-ara-oneri" in SABLON
    assert 'a.setAttribute("id", listeKimligi + "-" + secenekler.length);' in ARAMA_JS  # iki listede kimlik çakışmaz
    # Yazmaya devam edilince etkin seçenek sıfırlanır; Enter yalnız kutudaki yazının önerisine gider.
    girdi = ARAMA_JS.split('kutu.addEventListener("input", function () {')[1].split("});")[0]
    assert girdi.strip().startswith("sec(-1);")
    assert "if (acik && etkin >= 0 && cizilen === sorguMetni()) {" in ARAMA_JS
    # Duyurulan sayı gezilebilen öneri sayısıdır.
    assert '"İlk " + oneri + " öneri, toplam " + toplam + " sonuç"' in ARAMA_JS and 'Math.max(toplam' not in ARAMA_JS


def test_arama_stili_dar_ve_kisa_ekran():
    kabuk = STIL.split("@layer kabuk {")[1].split("/* ---- 0.15.0 sonu ---- */")[0]
    # "Tüm sonuçlar" satırı kayan listede görünür kalır.
    hepsi = kabuk.split(".ara-oneri a.hepsi {")[1].split("}")[0]
    assert "position: sticky;" in hepsi and "inset-block-end: 0;" in hepsi and "background: var(--yuzey);" in hepsi
    # Telefonda okul adı görsel olarak gizlenir (yarım kesik ad yerine logo); display: none DEĞİL (bağlantının adı kalır).
    dar = kabuk.split("@media (max-width: 26rem) {")[1].split("\n  }")[0]
    assert ".ust-cubuk .kimlik-okul { position: absolute; inline-size: 1px; block-size: 1px;" in dar and "display: none" not in dar
    # Kısa pencerede (fareyle) gezinme sıkışır; dokunmatikte 44 px hedef değişmez.
    kisa = kabuk.split("@media (max-height: 40rem) and (pointer: fine) {")[1].split("\n  }")[0]
    assert ".yan-gezinme a { min-block-size: 2rem; }" in kisa
    assert "@media (pointer: coarse) { .yan-gezinme a, .yan-cikis { min-block-size: var(--dokunma); } }" in kabuk


def test_ara_sorgusunda_denetim_karakteri_yankilanmaz(panel, tohum):
    sayfa = ara(panel, "zil\x00\u202e\u200b")
    assert "\x00" not in sayfa and "\u202e" not in sayfa and "\u200b" not in govde(sayfa)
    assert 'id="ara-q" name="q" value="zil"' in sayfa and api(panel, "zi\u202el")["sorgu"] == "zil"


def test_kisayol_metin_alaninda_tetiklenmez():
    for gerekli in ('olay.key !== "/"', "olay.ctrlKey", "olay.altKey", "olay.metaKey", "olay.defaultPrevented", '"dialog[open]"',
                    '"textarea, select, [contenteditable]"', "isContentEditable", 'h.tagName === "INPUT"', "ARAMA_YAZISIZ.indexOf("):  # fmt: skip
        assert gerekli in ARAMA_JS, gerekli
    liste = re.search(r"var ARAMA_YAZISIZ = \[([^\]]+)\];", BETIK).group(1)
    assert re.findall(r'"([a-z]+)"', liste) == ["checkbox", "radio", "button", "submit", "reset", "range", "file", "color"]
    assert '"Control"' not in ARAMA_JS and 'key === "k"' not in ARAMA_JS  # Ctrl+K eklenmedi (tarayıcı kısayolu)


def test_arama_stili_kabuk_katmaninda_ve_ham_renk_yok():
    kabuk = STIL.split("@layer kabuk {")[1].split("/* ---- 0.15.0 sonu ---- */")[0]
    for secici in (".genel-ara {", ".genel-ara input[type=search] {", ".genel-ara kbd {", ".ara-oneri {", ".ara-oneri a {",
                   '.ara-oneri a[aria-selected="true"] {', ".ust-ara {"):  # fmt: skip
        assert STIL.count(secici) >= 1 and secici in kabuk, secici
    satirlar = [s for s in STIL.splitlines() if re.search(r"genel-ara|ara-oneri|ust-ara|ara-grup|ara-fazla|--kb-kisayol", s)]
    assert len(satirlar) > 20
    for satir in satirlar:
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(|oklch\(", satir), satir
    assert "grid-template-rows: auto auto auto minmax(0, 1fr) auto;" in kabuk  # arama satırı ızgarada sayılır
    assert "max-block-size: min(24rem, 100dvh - 12rem); overflow-y: auto; overscroll-behavior: contain;" in kabuk
    assert "--kb-kisayol: none;" in kabuk and kabuk.count("--kb-kisayol: inline-block;") == 2
    assert ".yan-cikis, .yan-kapat, .ust-cubuk .menu-ac, .ust-ara { display: inline-flex;" in kabuk
    baski = kabuk.split("@media print {")[-1]
    assert ".yan-menu, .ust-cubuk, .alt-cubuk, .perde { display: none !important; }" in baski  # kutu ve simge baskıda yok


@pytest.mark.parametrize("ana, vurgu", [(None, None), ("#7a1f2b", "#0f766e"), ("#f2c200", None), ("#e8f0fb", "#ffd9a8")])
def test_arama_yer_tutucu_kontrasti(ana, vurgu):
    """Kutu saydam zeminlidir: yer tutucu (--serit-soluk) doğrudan şerit zemininde durur; yazılan metin --serit-yazi."""
    assert ".genel-ara input[type=search]::placeholder { color: var(--serit-soluk); opacity: 1; }" in STIL
    kural = STIL.split(".genel-ara input[type=search] {")[1].split("}")[0]
    assert "background: none;" in kural and "color: var(--serit-yazi);" in kural
    uretilen = tema.uret(ana, vurgu) if ana else tema.varsayilan()
    for kip in ("acik", "koyu"):
        serit, yazi, soluk = (uretilen[kip][a] for a in ("serit", "serit-yazi", "serit-soluk"))
        assert tema.kontrast(soluk, serit) >= 4.5 and tema.kontrast(yazi, serit) >= 7, kip
        # Kenarlık (şerit yazısının %35'i) kutuyu zeminden ayırır: metin dışı öğe için 3:1'e yakın, en az 2:1.
        assert tema.kontrast(karistir(yazi, serit, 0.35), serit) >= 2, kip
        # Öneri listesi sayfa yüzeyindedir: metin ve soluk yazı var olan yüzey çiftleridir.
        assert tema.kontrast(uretilen[kip]["metin"], uretilen[kip]["yuzey2"]) >= 7, kip
        assert tema.kontrast(uretilen[kip]["soluk"], uretilen[kip]["yuzey2"]) >= 4.5, kip
