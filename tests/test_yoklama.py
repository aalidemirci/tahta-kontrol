"""Ders yoklaması (Aşama 5): sunucu uçları, PIN sınırları, icmal, imha. Bütün veriler UYDURMADIR."""

from __future__ import annotations

import re
import sqlite3

import pytest
from yardimci import (
    an,
    bekle,
    gir,
    ileti,
    kimlik,
    kullanici_ekle,
    kur_ve_gir,
    sorgu,
    tahta_ekle,
    yeni_ajan_durumu,
)

from tahta_sunucu import maske, vt
from tahta_sunucu import yoklama as yk

OGRENCI_CSV = (
    "Sınıf/Şube;Okul No;Adı;Soyadı\n"
    "10/A;1047;Ayşe;YILMAZ\n10/A;1102;Burak;KAYA\n10/A;1150;Ayşe;YURT\n10/A;0215;Cemre;DOĞAN\n"
    "10/B;2001;Deniz;ÇELİK\n10/B;2002;Ege;TUNA\n"
).encode()
YOKLAMA_DURUMU = yeni_ajan_durumu(yetenekler=["acil", "duyuru_id", "yoklama"])


def ayar_kaydet(panel, **alanlar):
    form = {"bolum": "yoklama", "yk_etkin": "1", "yk_maske": "ad_soyadbas", "yk_oturum_dk": "8", "yk_bosta_dk": "3"}
    form.update(alanlar)
    if form.get("yk_etkin") is None:
        form.pop("yk_etkin")
    return panel.post("/ayarlar", data=form)


def ogrenci_yukle(panel, veri: bytes = OGRENCI_CSV, ad: str = "liste.csv"):
    yanit = panel.post("/ogrenciler/onizle", files={"dosya": (ad, veri, "text/csv")})
    assert yanit.status_code == 200, ileti(yanit)
    belirtec = re.search(r'name="onizleme" value="([^"]+)"', yanit.text).group(1)
    return panel.post("/ogrenciler/aktar", data={"onizleme": belirtec})


def ogretmen_ekle(panel, ad="Ayşe", soyad="Örnek") -> tuple[int, str]:
    panel.post("/ogretmenler", data={"eylem": "ekle", "ad": ad, "soyad": soyad})
    satir = sorgu("SELECT o.id, p.kod FROM ogretmen o JOIN ogretmen_pin p ON p.ogretmen_id = o.id ORDER BY o.id DESC LIMIT 1")[0]
    return satir["id"], satir["kod"]


def pin_uret(panel, ogretmen_id: int) -> str:
    yanit = panel.post("/ogretmenler", data={"eylem": "pin_uret", "id": str(ogretmen_id)})
    assert yanit.status_code == 200, ileti(yanit)
    return re.search(r'class="pusula-pin">(\d{3}) (\d{3})<', yanit.text).expand(r"\1\2")


@pytest.fixture()
def hazir(panel, tahta):
    """Kurulum + yoklama etkin + öğrenciler + 10/A tahtası + PIN'li öğretmen."""
    kur_ve_gir(panel)
    assert "t=hata" not in ayar_kaydet(panel).headers["location"]
    assert "t=hata" not in ogrenci_yukle(panel).headers["location"]
    basliklar = tahta_ekle(panel, tahta, "10A Tahtası", durum=YOKLAMA_DURUMU, subeler="10/A")
    ogr_id, kod = ogretmen_ekle(panel)
    pin = pin_uret(panel, ogr_id)
    return {"basliklar": basliklar, "kod": kod, "pin": pin, "ogretmen_id": ogr_id}


def ajan(tahta, basliklar, uc: str, govde: dict | None = None):
    return tahta.post(f"/ajan/yoklama/{uc}", headers=basliklar, json=govde or {})


def baslat(tahta, h, kod=None, pin=None):
    return ajan(tahta, h["basliklar"], "baslat", {"kod": kod or h["kod"], "pin": pin or h["pin"]})


def ogrenci_id(okul_no: str) -> int:
    return sorgu("SELECT id FROM ogrenci WHERE okul_no = ?", okul_no)[0]["id"]


def test_programdaki_ogretmen_farkli_olsa_da_baska_subede_yoklama_alinir(hazir, panel, tahta):
    diger_id, _ = ogretmen_ekle(panel, "Program", "Öğretmeni")
    with vt.islem() as b:
        b.execute("INSERT INTO ogretmen_program(sube,gun,ders_no,baslangic,bitis,ders_adi,ogretmen_id,guncelleme) "
                  "VALUES('10/B',0,1,'08:20','09:00','Yapay Ders',?,?)", (diger_id, vt.simdi()))
    oturum = baslat(tahta, hazir).json()["belirtec"]
    yanit = ajan(tahta, hazir["basliklar"], "kaydet", {"belirtec": oturum, "sube": "10/B", "ders_no": 1, "yok": []})
    assert yanit.status_code == 200
    with vt.islem() as b:
        kayit = b.execute("SELECT * FROM yoklama WHERE sube = '10/B'").fetchone()
        assert kayit["ogretmen_id"] == hazir["ogretmen_id"]
        assert yk.kayit_ayrintisi(b, kayit["id"])["program_eslesiyor"] is False


def tum_metin() -> str:
    """Veritabanındaki bütün tabloların bütün hücreleri (gizli bilgi taraması için)."""
    with vt.islem() as b:
        tablolar = [s[0] for s in b.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return "\n".join(repr(tuple(s)) for t in tablolar for s in b.execute(f"SELECT * FROM {t}"))


def ders_saatleri_yaz(gun: int = 0, devre: str = "normal", saatler=None) -> None:
    saatler = saatler or [("08:20", "09:00"), ("09:10", "09:50"), ("10:00", "10:40"), ("10:50", "11:30")]
    with vt.islem() as b:
        for no, (bas, bit) in enumerate(saatler, 1):
            b.execute("INSERT INTO ders_saati (gun, devre, devre_adi, ders_no, baslangic, bitis) VALUES (?, ?, 'Normal', ?, ?, ?)",
                      (gun, devre, no, bas, bit))  # fmt: skip


# ---- göç ve ayar -----------------------------------------------------------------------------------
def test_goc_bos_ve_onceki_surum_veritabaninda_calisir(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    yol = tmp_path / "tahta-kontrol.db"
    b = sqlite3.connect(yol)
    for sira in range(4):  # 0.5.0 şeması
        b.executescript(vt.GOCLER[sira])
    b.execute("PRAGMA user_version = 4")
    b.commit()
    b.close()
    vt.hazirla()
    with vt.islem() as b:
        assert b.execute("PRAGMA user_version").fetchone()[0] == len(vt.GOCLER) >= 5
        for tablo in ("ogretmen", "ogretmen_pin", "ogrenci", "yoklama", "yoklama_yok", "yoklama_iz", "yoklama_belirtec",
                      "eokul_islendi", "ogrenci_aktarim"):  # fmt: skip
            assert b.execute(f"SELECT COUNT(*) FROM {tablo}").fetchone()[0] == 0
    (tmp_path / "bos").mkdir()
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path / "bos"))
    vt.hazirla()
    vt.hazirla()


def test_ayar_sinirlari_ve_tam_ad_secenegi_reddedilir(panel, tahta):
    kur_ve_gir(panel)
    assert ileti(ayar_kaydet(panel, yk_oturum_dk="30")).startswith("Yoklama oturumu 3–15")
    assert ileti(ayar_kaydet(panel, yk_maske="tam")) == "Tahtadaki ad görünümü geçersiz."
    yanit = ayar_kaydet(panel)
    assert "öğrenci listesi henüz yüklenmedi" in ileti(yanit)
    with vt.islem() as b:
        assert yk.ayar_al(b)["etkin"] is True
        vt.ayar_yaz(b, "yoklama", {"etkin": True, "maske": "tam"})  # elle yazılmış eski değer
        assert yk.ayar_al(b)["maske"] == maske.VARSAYILAN_SINIF_BICIMI == "no_ad_soyadbas"
    assert 'name="yk_maske"' in panel.get("/ayarlar/yoklama").text


def test_tahtaya_giden_ayar_yalniz_yoklama_etkin_tasir(panel, tahta):
    kur_ve_gir(panel)
    basliklar = tahta_ekle(panel, tahta, "T", durum=YOKLAMA_DURUMU)
    assert bekle(tahta, basliklar)["ayar"]["yoklama_etkin"] is False
    ayar_kaydet(panel)
    ayar_ = bekle(tahta, basliklar)["ayar"]
    assert ayar_["yoklama_etkin"] is True
    assert not any(k.startswith("yoklama") and k != "yoklama_etkin" for k in ayar_)
    assert "maske" not in str(ayar_) and "saklama" not in str(ayar_)


def test_yoklama_kapaliyken_ajan_uclari_409_doner(panel, tahta):
    kur_ve_gir(panel)
    basliklar = tahta_ekle(panel, tahta, "T", durum=YOKLAMA_DURUMU)
    for uc in ("oneri", "baslat", "liste", "kaydet"):
        yanit = ajan(tahta, basliklar, uc, {"kod": "101", "pin": "123456"})
        assert yanit.status_code == 409 and yanit.json()["hata"] == yk.ILETI_ETKIN_DEGIL
    assert ajan(tahta, basliklar, "bitir", {"belirtec": "x"}).status_code == 200
    assert tahta.post("/ajan/yoklama/oneri", json={}).status_code == 401


# ---- PIN ----------------------------------------------------------------------------------------------
def test_pin_uretimi_ozeti_saklar_duz_pini_saklamaz(panel, tahta, hazir):
    pin = hazir["pin"]
    assert len(pin) == 6 and pin.isdigit()
    assert pin not in tum_metin()
    yanit = panel.post("/ogretmenler", data={"eylem": "pin_uret", "id": str(hazir["ogretmen_id"])})
    yeni = re.search(r'class="pusula-pin">(\d{3}) (\d{3})<', yanit.text).expand(r"\1\2")
    assert yanit.headers["cache-control"] == "no-store" and "location" not in yanit.headers
    assert yeni not in tum_metin() and "pin" not in str(yanit.url).lower().split("?")[-1]
    assert sorgu("SELECT pin_ozet FROM ogretmen_pin")[0]["pin_ozet"].startswith("scrypt$")


def test_pin_dogru_ise_belirtec_ve_kalan_sure_doner(panel, tahta, hazir):
    yanit = baslat(tahta, hazir)
    assert yanit.status_code == 200, yanit.text
    veri = yanit.json()
    assert veri["kalan_sn"] == 480 and veri["bosta_sn"] == 180
    assert veri["ogretmen"] == {"kod": hazir["kod"], "etiket": "A. Örnek"}
    assert len(veri["belirtec"]) >= 40 and veri["belirtec"] not in tum_metin()
    assert sorgu("SELECT islem, ayrinti FROM kayit WHERE islem = 'Yoklama oturumu açıldı'")[0]["ayrinti"] == f"öğretmen kodu {hazir['kod']}"


def test_bilinmeyen_kod_ve_yanlis_pin_ayni_iletiyi_alir(panel, tahta, hazir):
    yanlis = "000000" if hazir["pin"] != "000000" else "111111"
    a = baslat(tahta, hazir, pin=yanlis)
    b_ = baslat(tahta, hazir, kod="999", pin=yanlis)
    c = baslat(tahta, hazir, kod="abc", pin="12")
    assert a.status_code == b_.status_code == c.status_code == 403
    assert a.json() == b_.json() == c.json() == {"hata": yk.ILETI_HATALI, "bekleme_sn": 0}


def test_ogretmen_tahta_cifti_uc_hatada_bekletilir(panel, tahta, hazir, saat):
    yanlis = "000000" if hazir["pin"] != "000000" else "111111"
    assert baslat(tahta, hazir, pin=yanlis).status_code == 403
    assert baslat(tahta, hazir, pin=yanlis).status_code == 403
    ucuncu = baslat(tahta, hazir, pin=yanlis)
    assert ucuncu.status_code == 429 and ucuncu.json()["bekleme_sn"] == 120
    assert baslat(tahta, hazir).status_code == 429  # doğru PIN de bekler
    saat.ilerlet(121)
    assert baslat(tahta, hazir).status_code == 200


def test_tahta_on_dakikada_on_hatada_kapanir(panel, tahta, hazir, saat):
    for i in range(9):
        assert baslat(tahta, hazir, kod=str(900 + i), pin="000000").status_code == 403
    onuncu = baslat(tahta, hazir, kod="909", pin="000000")
    assert onuncu.status_code == 429 and onuncu.json()["bekleme_sn"] == 600
    assert onuncu.json()["hata"] == yk.ILETI_TAHTA_KAPALI
    assert baslat(tahta, hazir).status_code == 429
    saat.ilerlet(1)
    sonraki = baslat(tahta, hazir)  # kapanma sürerken de aynı ileti (kalan 599 sn)
    assert sonraki.status_code == 429 and sonraki.json()["hata"] == yk.ILETI_TAHTA_KAPALI
    assert sonraki.json()["bekleme_sn"] == 599
    saat.ilerlet(600)
    assert baslat(tahta, hazir).status_code == 200


def test_ogretmen_yirmi_dort_saatte_on_hatada_kilitlenir_ve_panelden_acilir(panel, tahta, hazir, saat):
    yanlis = "000000" if hazir["pin"] != "000000" else "111111"
    son = None
    for i in range(10):
        if i and i % 3 == 0:
            saat.ilerlet(121)  # çift katmanının beklemesi geçsin
        son = baslat(tahta, hazir, pin=yanlis)
    assert son.status_code == 423 and son.json()["hata"] == yk.ILETI_KILITLI
    assert sorgu("SELECT kilitli FROM ogretmen_pin")[0]["kilitli"] == 1
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Öğretmen PIN''i kilitlendi'")[0]["ayrinti"] == f"kod {hazir['kod']}"
    saat.ilerlet(601)
    assert baslat(tahta, hazir).status_code == 423  # doğru PIN de kilitli
    assert "PIN kilitli" in panel.get("/ogretmenler").text
    panel.post("/ogretmenler", data={"eylem": "pin_kilit_ac", "id": str(hazir["ogretmen_id"])})
    assert baslat(tahta, hazir).status_code == 200


def test_pasif_ogretmen_giris_yapamaz(panel, tahta, hazir):
    panel.post("/ogretmenler", data={"eylem": "durum", "id": str(hazir["ogretmen_id"])})
    assert baslat(tahta, hazir).status_code == 403


def test_yeni_pin_acik_oturumlari_dusurur(panel, tahta, hazir):
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    assert ajan(tahta, hazir["basliklar"], "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1}).status_code == 200
    pin_uret(panel, hazir["ogretmen_id"])
    yanit = ajan(tahta, hazir["basliklar"], "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1})
    assert yanit.status_code == 401 and yanit.json()["hata"] == yk.ILETI_OTURUM_BITTI


def test_belirtec_baska_tahtada_gecersiz(panel, tahta, hazir):
    diger = tahta_ekle(panel, tahta, "Diğer", durum=YOKLAMA_DURUMU)
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    assert ajan(tahta, diger, "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1}).status_code == 401


def test_belirtec_suresi_dolunca_reddedilir(panel, tahta, hazir, saat):
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    saat.ilerlet(8 * 60)
    assert ajan(tahta, hazir["basliklar"], "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1}).status_code == 401


# ---- liste ve kaydet -----------------------------------------------------------------------------------
def test_liste_maskeye_gore_etiket_uretir(panel, tahta, hazir):
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    yanit = ajan(tahta, hazir["basliklar"], "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1})
    veri = yanit.json()
    etiketler = [o["etiket"] for o in veri["ogrenciler"]]
    # 0.14.0: sıra okul numarasıdır (0215 < 1047 < 1102 < 1150), her biçimde.
    assert etiketler == ["Cemre D.", "Ayşe Y. (47)", "Burak K.", "Ayşe Y. (50)"]
    for gizli in ("YILMAZ", "KAYA", "DOĞAN", "1047", "1102", "0215", "Deniz"):
        assert gizli not in yanit.text
    assert veri["mevcut"] == 4 and veri["yok"] == [] and veri["baska_yoklama"] is False
    assert veri["gec"] == [] and veri["gec_secilebilir"] is True  # zil saati yok: 1. ders ilk ders sayılır
    ayar_kaydet(panel, yk_maske="no_basharf")
    yanit = ajan(tahta, hazir["basliklar"], "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1})
    etiketler = sorted(o["etiket"] for o in yanit.json()["ogrenciler"])
    assert etiketler == ["0215 C. D.", "1047 A. Y.", "1102 B. K.", "1150 A. Y."]
    assert "Ayşe" not in yanit.text and "YILMAZ" not in yanit.text


def test_etiket_cakismasi_numara_son_haneleriyle_cozulur():
    ogrenciler = [
        {"id": 1, "ad": "Ayşe", "soyad": "YILMAZ", "okul_no": "1047"},
        {"id": 2, "ad": "Ayşe", "soyad": "YURT", "okul_no": "2047"},
        {"id": 3, "ad": "Ayşe", "soyad": "YAZ", "okul_no": "3150"},
        {"id": 4, "ad": "Elif Su", "soyad": "DEMİR", "okul_no": "9"},
    ]
    sonuc = maske.sinif_etiketleri(ogrenciler, "ad_soyadbas")
    # İkinci çakışmada açık ad ile tam numara yan yana gelmez (M2): baş harfli biçime geçilir.
    assert sonuc == {1: "1047 A. Y.", 2: "2047 A. Y.", 3: "Ayşe Y. (50)", 4: "Elif Su D."}
    assert maske.sinif_etiketi("Elif Su", "DEMİR", "1047", "no_basharf") == "1047 E. S. D."
    assert maske.sinif_etiketi("Ayşe", "yılmaz", "1", "tam") == "Ayşe Y."  # bilinmeyen biçim maskeli kalır


def test_gelecek_ders_saati_secilemez(panel, tahta, hazir, saat):
    ders_saatleri_yaz()  # pazartesi 2. ders 09:10'da; saat 09:06 + 5 dk payı → 2. ders seçilebilir, 3. değil
    saat.ilerlet(6 * 60)
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    for ders_no, kod in ((1, 200), (2, 200), (3, 400), (7, 400)):
        yanit = ajan(tahta, hazir["basliklar"], "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": ders_no})
        assert yanit.status_code == kod, (ders_no, yanit.text)
    oneri = ajan(tahta, hazir["basliklar"], "oneri").json()
    assert [(d["ders_no"], d["secilebilir"]) for d in oneri["ders_saatleri"]] == [(1, True), (2, True), (3, False), (4, False)]


def test_oneri_programdan_sube_ve_ders_onerir(panel, tahta, hazir, saat):
    ders_saatleri_yaz()
    saat.ayarla(an(16, 8, 30))  # 1. ders sürüyor
    yanit = ajan(tahta, hazir["basliklar"], "oneri")
    veri = yanit.json()
    assert veri["oneri"] == {"sube": "10/A", "ders_no": 1, "ders_adi": "", "ogretmen": None, "ders_adaylari": []}  # tek şube
    assert veri["subeler_once"] == ["10/A"] and veri["devre_adi"] == "" and veri["simdiki_ders_no"] == 1
    assert veri["subeler"] == ["10/A", "10/B"] and veri["tarih"] == "2026-11-16"
    assert veri["tarih_yazi"] == "16.11.2026 Pazartesi"
    assert "Ayşe" not in yanit.text and "1047" not in yanit.text
    with vt.islem() as b:
        b.execute("INSERT INTO tahta_ders (tahta_id, gun, devre, ders_no, sube) VALUES (?, 0, 'normal', 1, '10/B')",
                  (kimlik(hazir["basliklar"]),))  # fmt: skip
    assert ajan(tahta, hazir["basliklar"], "oneri").json()["oneri"]["sube"] == "10/B"


def test_kaydet_baska_subenin_ogrencisini_reddeder(panel, tahta, hazir):
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    yanit = ajan(tahta, hazir["basliklar"], "kaydet", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1, "yok": [ogrenci_id("2001")]})
    assert yanit.status_code == 409 and yanit.json()["hata"] == yk.ILETI_LISTE_DEGISTI
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama")[0]["n"] == 0


def test_ascii_olmayan_rakamlar_500_vermez(panel, tahta, hazir):
    assert baslat(tahta, hazir, kod="1²3").status_code == 403
    assert baslat(tahta, hazir, kod="²²²").status_code == 403
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    yanit = ajan(tahta, hazir["basliklar"], "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": "²"})
    assert yanit.status_code == 400
    assert panel.get("/yoklama/gir?sube=10/A&ders_no=²").status_code == 200
    assert yk.no_anahtari("1²3")[0] == 1 and yk.kod_gecerli("²²²") is False


def test_kaydet_sonrasi_belirtec_tek_kullanimlik(panel, tahta, hazir):
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    govde = {"belirtec": belirtec, "sube": "10/A", "ders_no": 1, "yok": [ogrenci_id("1047"), ogrenci_id("0215")]}
    yanit = ajan(tahta, hazir["basliklar"], "kaydet", govde)
    assert yanit.json() == {"tamam": True, "yok_sayisi": 2, "gec_sayisi": 0, "mevcut": 4}
    assert ajan(tahta, hazir["basliklar"], "kaydet", govde).status_code == 401
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yoklama alındı'")[0]["ayrinti"] == f"10/A 1. ders, 2 yok, öğretmen kodu {hazir['kod']}"


def test_ayni_ogretmen_ayni_saati_gunceller_iz_yazar(panel, tahta, hazir):
    for yok in (["1047", "1102"], ["1102", "0215"]):
        belirtec = baslat(tahta, hazir).json()["belirtec"]
        liste = ajan(tahta, hazir["basliklar"], "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 2}).json()
        if yok[0] == "1102":
            assert sorted(liste["yok"]) == sorted([ogrenci_id("1047"), ogrenci_id("1102")])  # önceki işaretler hazır gelir
        ajan(tahta, hazir["basliklar"], "kaydet", {"belirtec": belirtec, "sube": "10/A", "ders_no": 2, "yok": [ogrenci_id(n) for n in yok]})
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama")[0]["n"] == 1
    izler = sorgu("SELECT islem, eklenen, cikarilan FROM yoklama_iz ORDER BY id")
    assert [i["islem"] for i in izler] == ["olustur", "guncelle"]
    assert izler[1]["eklenen"] == f"[{ogrenci_id('0215')}]" and izler[1]["cikarilan"] == f"[{ogrenci_id('1047')}]"


def tahtadan_yoklama(tahta, h, sube: str, ders_no: int, yok_nolar: list[str]):
    belirtec = baslat(tahta, h).json()["belirtec"]
    yanit = ajan(tahta, h["basliklar"], "kaydet", {"belirtec": belirtec, "sube": sube, "ders_no": ders_no, "yok": [ogrenci_id(n) for n in yok_nolar]})
    assert yanit.status_code == 200, yanit.text


def test_iki_ogretmenin_kaydinda_en_son_kaydedilen_tam_durum_gecerlidir(panel, tahta, hazir):
    """0.14.0 birleşim kuralı: ikinci öğretmenin listesi ders saatinin GEÇERLİ durumuyla açılır (ilk öğretmenin
    işareti hazır gelir) ve kaydı tam durumdur; ilk öğretmenin kaydı olduğu gibi durur."""
    tahtadan_yoklama(tahta, hazir, "10/A", 3, ["1047"])
    ikinci_id, ikinci_kod = ogretmen_ekle(panel, "Can", "Demir")
    ikinci = dict(hazir, kod=ikinci_kod, pin=pin_uret(panel, ikinci_id))
    belirtec = baslat(tahta, ikinci).json()["belirtec"]
    liste = ajan(tahta, hazir["basliklar"], "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 3}).json()
    assert liste["baska_yoklama"] is True and liste["yok"] == [ogrenci_id("1047")]
    ajan(tahta, hazir["basliklar"], "kaydet", {"belirtec": belirtec, "sube": "10/A", "ders_no": 3,
                                               "yok": [ogrenci_id("1047"), ogrenci_id("1102")]})  # fmt: skip
    ilk = sorgu("SELECT id FROM yoklama WHERE ogretmen_id = ?", hazir["ogretmen_id"])[0]["id"]
    assert [s["ogrenci_id"] for s in sorgu("SELECT ogrenci_id FROM yoklama_yok WHERE yoklama_id = ?", ilk)] == [ogrenci_id("1047")]
    with vt.islem() as b:
        veri = yk.icmal(b, yk.bugun(), "10/A")
    s = veri["subeler"][0]
    assert [o["okul_no"] for o in s["ogrenciler"]] == ["1047", "1102"]
    assert s["alanlar"][2]["metin"] == "A. Örnek, C. Demir"
    sayfa = panel.get("/yoklama").text
    assert "2 kayıt; en son kaydedilen geçerli" in sayfa and ">2 yok<" in sayfa


def test_yok_isaretsiz_yoklama_tam_sayilir(panel, tahta, hazir):
    tahtadan_yoklama(tahta, hazir, "10/A", 1, [])
    with vt.islem() as b:
        g = yk.gunluk_gorunum(b, yk.bugun(), vt.simdi())
    hucre = g["satirlar"][0]["hucreler"][0]
    assert (hucre["durum"], hucre["yok"]) == ("alindi", 0)
    assert re.search(r'class="rozet" data-durum="tamam" href="/yoklama/kayit/\d+"[^>]*>0<', panel.get("/yoklama").text)


def test_alinmayan_ders_sari_gorunur(panel, tahta, hazir, saat):
    with vt.islem() as b:
        g = yk.gunluk_gorunum(b, yk.bugun(), vt.simdi())
    assert all(h["durum"] == "bos" for s in g["satirlar"] for h in s["hucreler"])  # program yok → boş
    assert g["ozet"]["beklenen"] is None
    ders_saatleri_yaz()
    with vt.islem() as b:
        for no in (1, 2):
            b.execute("INSERT INTO tahta_ders (tahta_id, gun, devre, ders_no, sube) VALUES (?, 0, 'normal', ?, '10/A')",
                      (kimlik(hazir["basliklar"]), no))  # fmt: skip
    saat.ilerlet(16 * 60)  # 09:16: 1. ders 09:00'da bitti + 15 dk
    with vt.islem() as b:
        g = yk.gunluk_gorunum(b, yk.bugun(), vt.simdi())
    satir = next(s for s in g["satirlar"] if s["sube"] == "10/A")
    assert [h["durum"] for h in satir["hucreler"]] == ["alinmadi", "bos"]  # 2. ders 09:50'de biter
    assert g["ozet"]["beklenen"] == 2 and len(g["sutunlar"]) == 2  # sütun = programdaki en büyük ders saati
    assert 'data-durum="uyari" href="/yoklama/gir?' in panel.get("/yoklama").text and "alınmadı" in panel.get("/yoklama").text


def test_icmal_metni_ve_csv_bicimi(panel, tahta, hazir):
    with vt.islem() as b:
        b.execute("UPDATE ogrenci SET ad = '=HYPERLINK(1)' WHERE okul_no = '1102'")
    tahtadan_yoklama(tahta, hazir, "10/A", 1, ["1047", "1102"])
    tahtadan_yoklama(tahta, hazir, "10/A", 2, ["1047"])
    with vt.islem() as b:
        veri = yk.icmal(b, yk.bugun())
    metin_ = yk.icmal_metni(veri)
    # Program yokken payda ızgaradaki gibi en az 8 saat: alınmayan saatler görünür (yalnız "alınan son saat" değil).
    assert metin_.startswith("16.11.2026 Pazartesi — ders yoklaması icmali\n"
                             "10/A (yoklama alınan: 1-2; alınmayan: 3-8; ders programı yüklü değil, 8 saat varsayıldı)\n")
    a = next(s for s in veri["subeler"] if s["sube"] == "10/A")
    assert (a["alinan_sayisi"], a["sutun_sayisi"], a["program_bilinir"]) == (2, 8, False)
    assert a["ogrenciler"][0]["hucreler"] == ["Y", "Y", "-", "-", "-", "-", "-", "-"]
    assert "1047\tAyşe YILMAZ\t1,2\t2\n" in metin_
    assert "10/B (yoklama alınan: yok)\nyok yazılan öğrenci yok" in metin_
    yanit = panel.get("/yoklama/icmal.csv?tarih=2026-11-16")
    assert yanit.headers["content-disposition"] == 'attachment; filename="yoklama-icmali-2026-11-16.csv"'
    govde = yanit.content.decode("utf-8")
    assert govde.startswith("﻿Tarih;Şube;Okul No;Adı;Soyadı;Yok Ders Saatleri;Yok Ders Saati Sayısı;")
    assert govde.splitlines()[0].endswith(";Yoklama Alınan Ders Saati Sayısı;Geç Sayısı;Özürlü Yok Sayısı")  # yeni sütunlar sonda
    assert "16.11.2026;10/A;1047;Ayşe;YILMAZ;1,2;2;2;0;0\r\n" in govde
    assert ";'=HYPERLINK(1);" in govde
    kayitlar = [s["islem"] for s in sorgu("SELECT islem FROM kayit")]
    assert "Devamsızlık icmali indirildi (CSV)" in kayitlar
    sayfa = panel.get("/yoklama/icmal?tarih=2026-11-16&sube=10/A")
    assert sayfa.status_code == 200 and "Ayşe YILMAZ" in sayfa.text
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Devamsızlık icmali açıldı'")[0]["ayrinti"] == "16.11.2026, 10/A"


def test_icmal_ogrencinin_gunici_sube_degisimini_dogru_gosterir(panel, tahta, hazir):
    tahtadan_yoklama(tahta, hazir, "10/A", 1, ["1047"])
    ogrenci_yukle(panel, "Şube;Okul No;Adı;Soyadı\n10/B;1047;Ayşe;YILMAZ\n10/B;2001;Deniz;ÇELİK\n10/B;2002;Ege;TUNA\n".encode())
    h2 = dict(hazir, basliklar=tahta_ekle(panel, tahta, "10B", durum=YOKLAMA_DURUMU, subeler="10/B"))
    tahtadan_yoklama(tahta, h2, "10/B", 4, ["1047"])
    with vt.islem() as b:
        veri = {s["sube"]: s for s in yk.icmal(b, yk.bugun())["subeler"]}
    assert [(o["okul_no"], o["saatler"]) for o in veri["10/A"]["ogrenciler"]] == [("1047", [1])]
    assert [(o["okul_no"], o["saatler"]) for o in veri["10/B"]["ogrenciler"]] == [("1047", [4])]


# ---- panel -----------------------------------------------------------------------------------------------
def test_panelden_duzeltme_gerekce_ister_ve_iz_yazar(panel, tahta, hazir):
    tahtadan_yoklama(tahta, hazir, "10/A", 1, ["1047"])
    yid = sorgu("SELECT id FROM yoklama")[0]["id"]
    sayfa = panel.get(f"/yoklama/kayit/{yid}")
    assert sayfa.status_code == 200 and "Ayşe YILMAZ" in sayfa.text and yk.ILETI_ADLI_SAYFA in sayfa.text
    yanit = panel.post(f"/yoklama/kayit/{yid}", data={"eylem": "duzelt", "yok": [], "aciklama": "abc"})
    assert "Gerekçe yazın" in ileti(yanit)
    from yardimci import SAHTE_TC

    assert ileti(panel.post(f"/yoklama/kayit/{yid}", data={"eylem": "duzelt", "aciklama": f"no {SAHTE_TC}"})).startswith("Metinde T.C.")
    yanit = panel.post(f"/yoklama/kayit/{yid}", data={"eylem": "duzelt", "yok": [str(ogrenci_id("1102"))],
                                                    "aciklama": "2. derste geldi, öğretmen bildirdi"})  # fmt: skip
    assert ileti(yanit) == "Düzeltme kaydedildi."
    iz = sorgu("SELECT * FROM yoklama_iz ORDER BY id DESC LIMIT 1")[0]
    assert (iz["islem"], iz["kim"], iz["aciklama"]) == ("duzelt", "yonetici", "2. derste geldi, öğretmen bildirdi")
    assert "Burak KAYA" in panel.get(f"/yoklama/kayit/{yid}").text
    yanit = panel.post(f"/yoklama/kayit/{yid}", data={"eylem": "sil", "aciklama": "yanlış şubeye girildi"})
    assert ileti(yanit) == "Yoklama kaydı silindi." and sorgu("SELECT COUNT(*) AS n FROM yoklama_iz")[0]["n"] == 0
    silme = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yoklama silindi'")[0]["ayrinti"]
    assert silme.endswith("· gerekçe: yanlış şubeye girildi") and "1102" not in silme and "KAYA" not in silme


def test_panelden_yoklama_son_yedi_gunle_sinirli(panel, tahta, hazir):
    assert panel.get("/yoklama/gir?tarih=2026-11-16&sube=10/A&ders_no=1").status_code == 200
    eski = panel.post("/yoklama/gir", data={"tarih": "2026-11-08", "sube": "10/A", "ders_no": "1"})
    assert "son 7 gün" in ileti(eski)
    gelecek = panel.post("/yoklama/gir", data={"tarih": "2026-11-17", "sube": "10/A", "ders_no": "1"})
    assert "son 7 gün" in ileti(gelecek)
    yanit = panel.post("/yoklama/gir", data={"tarih": "2026-11-09", "sube": "10/A", "ders_no": "5",
                                             "ogretmen_id": str(hazir["ogretmen_id"]), "yok": [str(ogrenci_id("0215"))]})  # fmt: skip
    assert "t=hata" not in yanit.headers["location"], ileti(yanit)
    y = sorgu("SELECT * FROM yoklama")[0]
    assert (y["tarih"], y["kaynak"], y["kaydeden"], y["ogretmen_id"]) == ("2026-11-09", "panel", "yonetici", hazir["ogretmen_id"])


def test_idareci_ogrenci_aktaramaz_ama_pin_sifirlayabilir(panel, tahta, hazir):
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    yanit = panel.post("/ogrenciler/onizle", files={"dosya": ("l.csv", OGRENCI_CSV, "text/csv")})
    assert ileti(yanit) == "Bu işlem için yönetici yetkisi gerekir."
    assert ileti(panel.post("/ogrenciler/temizle", data={"onay": "SİL"})) == "Bu işlem için yönetici yetkisi gerekir."
    assert ileti(panel.post("/ogretmenler", data={"eylem": "ekle", "ad": "X"})) == "Bu işlem için yönetici yetkisi gerekir."
    assert ileti(panel.post("/ogretmenler", data={"eylem": "toplu_pin"})) == "Bu işlem için yönetici yetkisi gerekir."
    assert panel.post("/ayarlar", data={"bolum": "yoklama"}).headers["location"].startswith("/?m=")
    assert pin_uret(panel, hazir["ogretmen_id"]).isdigit()
    for yol in ("/yoklama", "/ogretmenler", "/ogrenciler", "/yoklama/icmal", "/yoklama/gir"):
        assert panel.get(yol).status_code == 200, yol
    assert "Öğrenci listesi aktarma" in [s["ayrinti"] for s in sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yetkisiz işlem reddedildi'")]


def test_toplu_pin_yalniz_pini_olmayanlara_uretir(panel, tahta, hazir):
    ogretmen_ekle(panel, "Can", "Demir")
    ogretmen_ekle(panel, "Ece", "Tan")
    yanit = panel.post("/ogretmenler", data={"eylem": "toplu_pin"})
    assert yanit.status_code == 200 and yanit.text.count('class="pusula-pin"') == 2
    assert "Ayşe Örnek" not in yanit.text
    assert ileti(panel.post("/ogretmenler", data={"eylem": "toplu_pin"})) == "PIN'i olmayan etkin öğretmen yok."


def test_islem_kaydinda_ogrenci_adi_ve_numarasi_gecmez(panel, tahta, hazir):
    tahtadan_yoklama(tahta, hazir, "10/A", 1, ["1047", "1102"])
    panel.post("/yoklama/gir", data={"tarih": "2026-11-16", "sube": "10/B", "ders_no": "1", "yok": [str(ogrenci_id("2001"))]})
    panel.get("/yoklama/icmal")
    panel.get("/yoklama/icmal.csv")
    panel.post("/yoklama/islendi", data={"tarih": "2026-11-16", "sube": "10/A", "deger": "1"})
    kayit = repr(sorgu("SELECT * FROM kayit"))
    for gizli in ("Ayşe", "YILMAZ", "Burak", "KAYA", "Deniz", "ÇELİK", "1047", "1102", "2001", "0215", hazir["pin"], "Örnek"):
        assert gizli not in kayit, gizli
    assert "e-Okul'a işlendi işaretlendi" in kayit
    assert sorgu("SELECT * FROM eokul_islendi")[0]["sube"] == "10/A"


def test_ogrenci_aktarma_dosyadaki_subeyi_tam_liste_sayar(panel, tahta, hazir):
    yanit = ogrenci_yukle(panel, "Şube;Okul No;Adı;Soyadı\n10/A;1047;Ayşe;YILMAZ\n10/A;3000;Yeni;ÖĞRENCİ\n10/A;2001;Deniz;ÇELİK\n".encode())
    assert ileti(yanit) == "Aktarıldı: 1 şube, 1 öğrenci eklendi, 1 güncellendi, 3 pasifleşti, 0 satır atlandı."
    aktif = {s["okul_no"]: s["sube"] for s in sorgu("SELECT okul_no, sube FROM ogrenci WHERE aktif = 1")}
    assert aktif == {"1047": "10/A", "3000": "10/A", "2001": "10/A", "2002": "10/B"}  # 10/B'ye dokunulmadı (2001 taşındı)
    assert sorgu("SELECT pasif, eklenen FROM ogrenci_aktarim ORDER BY id DESC LIMIT 1")[0] == {"pasif": 3, "eklenen": 1}
    eski = panel.post("/ogrenciler/aktar", data={"onizleme": "gecersiz"})
    assert ileti(eski) == "Önizlemenin süresi doldu; dosyayı yeniden yükleyin."


def test_onizleme_belirteci_tek_kullanimlik_ve_yaziya_gecmez(panel, tahta, hazir):
    yanit = panel.post("/ogrenciler/onizle", files={"dosya": ("l.csv", OGRENCI_CSV, "text/csv")})
    belirtec = re.search(r'name="onizleme" value="([^"]+)"', yanit.text).group(1)
    assert "Önizle" in yanit.text and sorgu("SELECT COUNT(*) AS n FROM ogrenci_aktarim")[0]["n"] == 1  # yalnız ilk aktarım
    panel.post("/ogrenciler/aktar", data={"onizleme": belirtec})
    assert ileti(panel.post("/ogrenciler/aktar", data={"onizleme": belirtec})).startswith("Önizlemenin süresi doldu")


# ---- imha ve yıl sonu ------------------------------------------------------------------------------------
def test_imha_saklama_suresini_uygular(panel, tahta, hazir, saat, uygulama):
    panel.post("/yoklama/gir", data={"tarih": "2026-11-16", "sube": "10/A", "ders_no": "1", "yok": [str(ogrenci_id("1047"))]})
    ogrenci_yukle(panel, "Şube;Okul No;Adı;Soyadı\n10/A;1102;Burak;KAYA\n10/A;0215;Cemre;DOĞAN\n10/A;1150;Ayşe;YURT\n".encode())
    # 1047 artık pasif ama yok kaydı var: kalır. 10/B'deki öğrencilere dokunulmadı.
    assert uygulama.state.yoklama_zamanlayici() is False
    assert {s["okul_no"] for s in sorgu("SELECT okul_no FROM ogrenci WHERE aktif = 0")} == {"1047"}
    saat.ilerlet(31 * 86400)
    gir(panel, "yonetici")  # panel oturumu 12 saatte biter
    yanit = panel.post("/yoklama/gir", data={"tarih": yk.bugun().isoformat(), "sube": "10/A", "ders_no": "1"})
    assert "t=hata" not in yanit.headers["location"], ileti(yanit)
    # K3: öğretim yılı bitiş tarihi girilmedikçe 31 gün geçse de silinmez.
    assert uygulama.state.yoklama_zamanlayici() is False
    assert len(sorgu("SELECT tarih FROM yoklama")) == 2
    from tahta_sunucu import vt

    with vt.islem() as b:
        vt.ayar_yaz(b, "ogretim_yili_bitis", "2026-11-20")
        vt.ayar_yaz(b, "yoklama_imha_son_tur", 0)
    assert uygulama.state.yoklama_zamanlayici() is True
    assert sorgu("SELECT tarih FROM yoklama") == [{"tarih": yk.bugun().isoformat()}]  # bitişten sonraki kalır
    assert not sorgu("SELECT 1 FROM ogrenci WHERE okul_no = '1047'")
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yoklama imhası'")[0]["ayrinti"] == (
        "1 kayıt, 1 öğrenci (öğretim yılı bitişi 20.11.2026)"
    )
    assert uygulama.state.yoklama_zamanlayici() is False  # saatte bir
    assert ("yoklama_imha", uygulama.state.yoklama_zamanlayici) in uygulama.state.zamanlayicilar


def test_ogrencileri_temizle_sil_onayi_ister(panel, tahta, hazir):
    tahtadan_yoklama(tahta, hazir, "10/A", 1, ["1047"])
    baslat(tahta, hazir)
    assert "SİL yazın" in ileti(panel.post("/ogrenciler/temizle", data={"onay": "sil"}))
    assert sorgu("SELECT COUNT(*) AS n FROM ogrenci")[0]["n"] == 6
    assert ileti(panel.post("/ogrenciler/temizle", data={"onay": "SİL"})) == "Silindi: 6 öğrenci, 1 yoklama kaydı."
    for tablo in ("ogrenci", "yoklama", "yoklama_yok", "yoklama_iz", "yoklama_belirtec", "eokul_islendi"):
        assert sorgu(f"SELECT COUNT(*) AS n FROM {tablo}")[0]["n"] == 0, tablo
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Tüm öğrenci ve yoklama verisi silindi'")[0]["ayrinti"] == "6 öğrenci, 1 yoklama"


# ---- panel görünümü ve tahta özeti ---------------------------------------------------------------------
def test_menu_ve_tahta_ozeti_yoklama_yetenegini_gosterir(panel, tahta, hazir):
    sayfa = panel.get("/").text
    assert '<a href="/yoklama"' in sayfa
    eski = tahta_ekle(panel, tahta, "Eski", durum=yeni_ajan_durumu())
    tahtalar = {t["ad"]: t for t in panel.get("/api/durum").json()["tahtalar"]}
    assert tahtalar["10A Tahtası"]["yoklama_yetenegi"] is True and tahtalar["Eski"]["yoklama_yetenegi"] is False
    bekle(tahta, hazir["basliklar"], dict(YOKLAMA_DURUMU, yoklama_acik=True))
    assert {t["ad"]: t for t in panel.get("/api/durum").json()["tahtalar"]}["10A Tahtası"]["yoklama_acik"] is True
    assert "Eski" in panel.get("/yoklama").text and kimlik(eski)


def test_sinav_penceresinde_yoklama_acilmaz(panel, tahta, hazir, monkeypatch):
    from tahta_sunucu import sinav

    monkeypatch.setattr(sinav, "tahta_sinav_penceresinde", lambda b, tahta_id, an, on_pay=0: True)
    assert ajan(tahta, hazir["basliklar"], "oneri").json()["hata"] == yk.ILETI_SINAV
    assert baslat(tahta, hazir).status_code == 409


# ---- arayüz (A5 arayüz uygulayıcısı) ---------------------------------------------------------------------
def test_komut_istemcisi_ekran_sayilmaz_ve_tahta_sayfasi_yoklama_rozeti(panel, tahta, hazir):
    tid = kimlik(hazir["basliklar"])
    # Yalnız kısa ömürlü komut istemcisi bağlıysa ekran yardımcısı "bağlı" sayılmaz (yeni ajan bunu göndermez; savunma).
    bekle(tahta, hazir["basliklar"], dict(YOKLAMA_DURUMU, ekranlar=[{"arayuz": "komut"}]))
    assert {t["ad"]: t for t in panel.get("/api/durum").json()["tahtalar"]}["10A Tahtası"]["ekran_bagli"] is False
    bekle(tahta, hazir["basliklar"], dict(YOKLAMA_DURUMU, yoklama_acik=True))
    sayfa = panel.get(f"/tahta/{tid}?sekme=bakim").text
    assert "Yoklama: destekleniyor" in sayfa and "Şu an yoklama alınıyor" in sayfa
    assert "Şu an yoklama alınıyor" in panel.get(f"/tahta/{tid}").text  # Genel › Durum'da da görünür
    eski = tahta_ekle(panel, tahta, "Eski", durum=yeni_ajan_durumu())
    assert "Yoklama: ajan güncellenmeli" in panel.get(f"/tahta/{kimlik(eski)}?sekme=bakim").text


def test_yoklama_sayfalari_bilesen_dili_ve_kancalar(panel, tahta, hazir):
    tahtadan_yoklama(tahta, hazir, "10/A", 1, ["1047"])
    gunluk = panel.get("/yoklama").text
    # Sayfa içi sekmeler, KVKK notu, e-Okul kutusu (JS'siz yedek düğmeli) ve renk sınıfı yerine data-durum.
    assert 'class="sekmeler bolum-serit"' in gunluk and '<a href="/yoklama" aria-current="page">Günlük</a>' in gunluk
    assert yk.ILETI_ADLI_SAYFA in gunluk and "data-otomatik-gonder" in gunluk and "data-js-gizle" in gunluk
    assert "rozet yesil" not in gunluk and "rozet kirmizi" not in gunluk and "rozet sari" not in gunluk
    yid = sorgu("SELECT id FROM yoklama LIMIT 1")[0]["id"]
    kayit = panel.get(f"/yoklama/kayit/{yid}").text
    assert 'data-onay="yoklama_sil"' in kayit and 'id="sil-formu"' in kayit and "data-sayac-yok" in kayit
    icmal = panel.get("/yoklama/icmal").text
    assert 'data-kopyala="icmal-metni"' in icmal and "data-yazdir" in icmal and 'class="yazdirma"' in icmal
    assert 'id="icmal-metni"' in icmal and "rapor-sayfasi" in icmal and "DERS YOKLAMASI İCMALİ" in icmal
    assert 'class="sekmeler bolum-serit"' in icmal and '<a href="/yoklama/icmal" aria-current="page">' in icmal
    for yol in ("/yoklama/gir?sube=10/A&ders_no=1", "/ogretmenler", "/ogrenciler?sube=10/A"):
        sayfa = panel.get(yol)
        assert sayfa.status_code == 200 and 'class="sekmeler bolum-serit"' in sayfa.text, yol
    assert "Ayşe YILMAZ" in panel.get("/yoklama/gir?sube=10/A&ders_no=1").text


def test_buyuk_ogrenci_listesi_gecici_dosyaya_tasmaz():
    """Starlette 1 MB'tan büyük dosya parçasını %TEMP%'e taşır; bellekte_form taşırmamalı (§8.4)."""
    import asyncio

    from starlette.datastructures import UploadFile
    from starlette.requests import Request

    from tahta_sunucu import eokul
    from tahta_sunucu.panel_program import bellekte_form

    sinir = "----sinir"
    icerik = b"10/A;1047;Ayse;DENEME\n" * (2 * 1024 * 1024 // 22)  # ~2 MB, uydurma
    govde = (f"--{sinir}\r\nContent-Disposition: form-data; name=\"dosya\"; filename=\"l.csv\"\r\n"
             f"Content-Type: text/csv\r\n\r\n").encode() + icerik + f"\r\n--{sinir}--\r\n".encode()  # fmt: skip
    kapsam = {"type": "http", "method": "POST", "path": "/", "query_string": b"",
              "headers": [(b"content-type", f"multipart/form-data; boundary={sinir}".encode()),
                          (b"content-length", str(len(govde)).encode())]}  # fmt: skip

    async def al():
        return {"type": "http.request", "body": govde, "more_body": False}

    async def calistir():
        form = await bellekte_form(Request(kapsam, al), eokul.DOSYA_SINIRI + 64 * 1024)
        try:
            dosya = form.get("dosya")
            assert isinstance(dosya, UploadFile)
            assert dosya.file._rolled is False  # diske taşmadı
            assert await dosya.read() == icerik
        finally:
            await form.close()

    asyncio.run(calistir())
