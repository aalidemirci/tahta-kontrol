"""Yoklama 0.14.0 temeli: sunucu–ajan sözleşme dosyası, şema göçü ve yeni sınıf listesi etiketi.

Sözleşme `tests/yoklama_sozlesme.json`'dadır; sunucu ve ajan testleri aynı dosyadan beslenir.
Bütün veriler UYDURMADIR.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tahta_sunucu import maske, vt

SOZLESME_YOLU = Path(__file__).with_name("yoklama_sozlesme.json")
SOZLESME = json.loads(SOZLESME_YOLU.read_text(encoding="utf-8"))
GOC_SIRASI = next(i for i, g in enumerate(vt.GOCLER) if "CREATE TABLE yoklama_gec" in g)


# ---- sözleşme dosyası ------------------------------------------------------------------------------
def test_sozlesme_ornekleri_bildirilen_anahtar_kumesini_tasir():
    for uc, tanim in SOZLESME["uclar"].items():
        zorunlu = set(tanim["yanit_anahtarlari"])
        serbest = set(tanim.get("istege_bagli_anahtarlar", []))
        for ad, ornek in tanim["ornekler"].items():
            yanit = ornek["yanit"]
            if ornek.get("kod", 200) != 200:
                assert set(yanit) == {"hata"}, (uc, ad)
                continue
            assert zorunlu <= set(yanit) <= zorunlu | serbest, (uc, ad)
            if isinstance(yanit.get("oneri"), dict):
                assert set(yanit["oneri"]) == set(tanim["oneri_anahtarlari"]), (uc, ad)
            for saat in yanit.get("ders_saatleri", []):
                assert set(saat) == set(tanim["ders_saati_anahtarlari"]), (uc, ad)
            for ogrenci in yanit.get("ogrenciler", []):
                assert set(ogrenci) == set(tanim["ogrenci_anahtarlari"]), (uc, ad)
                assert len(ogrenci["etiket"]) <= SOZLESME["sinirlar"]["etiket_en_uzun"]


def test_sozlesme_ornekleri_sinirlara_ve_degismezlere_uyar():
    sinir = SOZLESME["sinirlar"]
    uclar = SOZLESME["uclar"]
    for ornek in uclar["/ajan/yoklama/oneri"]["ornekler"].values():
        yanit = ornek["yanit"]
        assert len(yanit["subeler_once"]) <= sinir["subeler_once_oneri"]
        assert len(yanit["oneri"]["ders_adaylari"]) <= sinir["ders_adaylari"]
        assert yanit["oneri"]["ders_adi"] == "" and yanit["oneri"]["ogretmen"] is None
        # İki aday varken ders seçili gelmez; tek sonuç varken aday listesi boştur.
        assert not (yanit["oneri"]["ders_adaylari"] and yanit["oneri"]["ders_no"] is not None)
    for uc in ("/ajan/yoklama/baslat", "/ajan/usb/yoklama"):
        for ornek in uclar[uc]["ornekler"].values():
            assert len(ornek["yanit"]["subeler_once"]) <= sinir["subeler_once_baslat"]
    for ornek in uclar["/ajan/yoklama/liste"]["ornekler"].values():
        yanit = ornek["yanit"]
        idler = [o["id"] for o in yanit["ogrenciler"]]
        assert set(yanit["yok"]) | set(yanit["gec"]) <= set(idler)
        assert not set(yanit["yok"]) & set(yanit["gec"])
        assert yanit["gec_secilebilir"] or not yanit["gec"]
        assert yanit["mevcut"] == len(idler) and yanit["ders_adi"] == ""
    kaydet = uclar["/ajan/yoklama/kaydet"]
    for ornek in kaydet["ornekler"].values():
        assert set(ornek["istek"]) <= set(kaydet["istek_anahtarlari"])
        if ornek["kod"] == 200:
            assert set(ornek["yanit"]) == set(kaydet["yanit_anahtarlari"])
    assert {h["govde"]["hata"] for h in SOZLESME["hatalar"].values()} >= {
        o["yanit"]["hata"] for o in kaydet["ornekler"].values() if o["kod"] != 200
    }


def test_sozlesmede_kisisel_veri_alani_ve_ders_adi_yok():
    """Uç örneklerinde (istek ve yanıt) soyad, tam ad, T.C. no, mazeret, öğretmen kimliği alanı ve dolu ders adı yok.
    "soyad" yalnız etiket örneklerinin GİRDİSİNDE geçer."""
    for kaynak in (SOZLESME["uclar"], SOZLESME["eski_sunucu"]):
        metin = json.dumps(kaynak, ensure_ascii=False)
        for yasak in ('"soyad"', '"ad_soyad"', '"tc"', '"okul_no"', '"mazeret"', '"ogretmen_id"', '"ders_adi": "M'):
            assert yasak not in metin, yasak
        assert metin.count('"ders_adi": ""') == metin.count('"ders_adi": ')


def test_sozlesme_durum_degerleri_semadaki_denetimlerle_ayni():
    goc = vt.GOCLER[GOC_SIRASI]
    durum = SOZLESME["durumlar"]
    assert "(" + ", ".join(f"'{d}'" for d in durum["duzeltme"]) + ")" in goc
    assert "(" + ", ".join(f"'{t}'" for t in [*durum["mazeret_turleri"], durum["mazeret_iptal_turu"]]) + ")" in goc
    assert "(" + ", ".join(f"'{d}'" for d in durum["mazeret_dayanaklari"]) + ")" in goc


# ---- etiket ve yerleşim (maske.py) -------------------------------------------------------------------
def test_sozlesme_sabitleri_maske_modulundekiyle_ayni():
    sinir = SOZLESME["sinirlar"]
    assert sinir["etiket_en_uzun"] == maske.ETIKET_EN_UZUN
    assert sinir["okul_no_en_uzun"] == maske.OKUL_NO_EN_UZUN
    assert sinir["gec_eki"] == maske.GEC_EKI and sinir["kesme_isareti"] == maske.KESME_ISARETI
    assert sinir["sayfa_boyu"] == maske.YOKLAMA_SAYFA_BOYU
    assert {int(k): v for k, v in SOZLESME["yerlesim"]["ad_esigi"].items()} == maske.AD_ESIGI
    assert maske.VARSAYILAN_SINIF_BICIMI == "no_ad_soyadbas"
    assert list(maske.SINIF_BICIMLERI) == ["no_ad_soyadbas", "ad_soyadbas", "no_basharf"] and "tam" not in maske.SINIF_BICIMLERI


@pytest.mark.parametrize("satir", SOZLESME["yerlesim"]["tablo"], ids=lambda s: f"n{s['n']}")
def test_yerlesim_tablosu(satir):
    assert maske.yoklama_yerlesim(satir["n"]) == (satir["sutun"], satir["satir"])
    assert maske.yoklama_sayfa_sayisi(satir["n"]) == satir["sayfa_sayisi"]
    sutun, satir_sayisi = maske.yoklama_yerlesim(satir["n"])
    assert sutun * satir_sayisi >= min(satir["n"], maske.YOKLAMA_SAYFA_BOYU)  # bir sayfa kaydırmasız sığar


@pytest.mark.parametrize("ornek", SOZLESME["etiket"]["ornekler"], ids=lambda o: f"{o['okul_no'].strip() or 'nosuz'}-{o['sutun']}")
def test_etiket_ornekleri(ornek):
    esik = maske.ad_esigi(ornek["sutun"])
    etiket = maske.sinif_etiketi(ornek["ad"], ornek["soyad"], ornek["okul_no"], "no_ad_soyadbas", esik)
    assert etiket == ornek["etiket"]
    no = maske.etiket_no(ornek["okul_no"])
    ad_kismi = etiket[len(no) :].strip()
    assert len(ad_kismi) <= esik and len(etiket) <= maske.ETIKET_EN_UZUN
    # Soyadın baş harfi her zaman kalır; soyadın kendisi hiçbir zaman görünmez.
    harfler = " ".join(maske._bas_harf(s) for s in ornek["soyad"].split())
    assert etiket.endswith(harfler)
    assert all(s.lower() not in etiket.lower() for s in ornek["soyad"].split() if len(s) > 2)


def test_ad_kisaltma_kurali_adim_adim():
    assert maske.ad_kisalt("Ayşe Nur", "YILMAZ", 16) == "Ayşe Nur Y."
    assert maske.ad_kisalt("Muhammed Emin", "YILDIRIM", 16) == "Muhammed Emin Y."  # tam eşikte: kısaltılmaz
    assert maske.ad_kisalt("Muhammed Emin", "YILDIRIM", 15) == "Muhammed E. Y."  # önce sonraki adlar baş harfe iner
    assert maske.ad_kisalt("Muhammed Emin", "YILDIRIM", 13) == "Muhamm… E. Y."  # sonra ilk ad kesilir
    assert maske.ad_kisalt("Abdurrahman", "KAYA", 13) == "Abdurrahm… K."
    assert maske.ad_kisalt("Abdurrahman Ali Can Efe", "KARA ÖZ", 13) == "Abdurr… K. Ö."  # ilk ada yer kalmazsa aradakiler atılır
    assert maske.ad_kisalt("", "YILMAZ") == "Y." and maske.ad_kisalt("Ayşe", "") == "Ayşe" and maske.ad_kisalt("", "") == "?"
    for esik in range(8, 20):
        for ad in ("Ayşe", "Muhammed Emin", "Abdurrahman Muhammed Emin", "Elif Su Naz"):
            sonuc = maske.ad_kisalt(ad, "YILMAZ", esik)
            assert len(sonuc) <= esik and sonuc.endswith(" Y."), (ad, esik, sonuc)


def test_yeni_bicimde_cakisma_cozumu_calismaz_ve_esik_mevcuttan_gelir():
    ayni = [
        {"id": 1, "ad": "Ayşe", "soyad": "YILMAZ", "okul_no": "1047"},
        {"id": 2, "ad": "Ayşe", "soyad": "YURT", "okul_no": "2047"},
        {"id": 3, "ad": "Ayşe", "soyad": "YAZ", "okul_no": ""},
        {"id": 4, "ad": "Ayşe", "soyad": "YEL", "okul_no": ""},
    ]
    assert maske.sinif_etiketleri(ayni, "no_ad_soyadbas") == {1: "1047 Ayşe Y.", 2: "2047 Ayşe Y.", 3: "Ayşe Y.", 4: "Ayşe Y."}
    assert maske.sinif_etiketleri(ayni) == maske.sinif_etiketleri(ayni, "no_ad_soyadbas")  # yeni varsayılan
    uzun = {"ad": "Muhammed Emin", "soyad": "YILDIRIM"}
    sinif = lambda n: [{"id": i, "okul_no": str(100 + i), **uzun} for i in range(n)]  # noqa: E731
    assert maske.sinif_etiketleri(sinif(48))[0] == "100 Muhammed Emin Y."  # 6 sütun: eşik 16
    assert maske.sinif_etiketleri(sinif(49))[0] == "100 Muhamm… E. Y."  # 7 sütun: eşik 13
    assert maske.sinif_etiketleri(sinif(3), sutun=7)[0] == "100 Muhamm… E. Y."
    # Eski biçimler değişmedi; bilinmeyen biçim tam soyadı açmaz.
    assert maske.sinif_etiketi("Ayşe", "yılmaz", "1", "ad_soyadbas") == "Ayşe Y."
    assert maske.sinif_etiketi("Elif Su", "DEMİR", "1047", "no_basharf") == "1047 E. S. D."
    assert maske.sinif_etiketi("Ayşe", "yılmaz", "1", "tam") == "Ayşe Y."


@pytest.mark.parametrize("ornek", SOZLESME["etiket"]["gec_eki_ornekleri"], ids=lambda o: str(len(o["etiket"])))
def test_eski_ajana_giden_gec_eki_kirk_karakteri_asmaz(ornek):
    sonuc = maske.gec_ekli(ornek["etiket"])
    assert sonuc == ornek["eski_ajana"]
    assert len(sonuc) <= maske.ETIKET_EN_UZUN and sonuc.endswith(maske.GEC_EKI)


def test_sinav_maskesi_degismedi():
    assert maske.kalabalik("Ahmet Yılmaz") == "Ah*** Yı****" and maske.no_son("1047") == "47"


# ---- göç (0.13.1 → 0.14.0) -----------------------------------------------------------------------------
def eski_veritabani(dizin: Path, yoklama_ayari: dict | None) -> None:
    """0.13.1 şeması + uydurma veri (öğretmen, öğrenci, yoklama, yok satırı, iz, e-Okul işareti)."""
    b = sqlite3.connect(dizin / "tahta-kontrol.db")
    for sira in range(GOC_SIRASI):
        b.executescript(vt.GOCLER[sira])
    b.execute(f"PRAGMA user_version = {GOC_SIRASI}")
    b.execute("INSERT INTO ogretmen (id, ad, soyad) VALUES (1, 'Uydurma', 'Öğretmen')")
    b.executemany("INSERT INTO ogrenci (id, sube, okul_no, ad, soyad, guncelleme) VALUES (?, '10/A', ?, ?, ?, 1)",
                  [(11, "0215", "Elif Su", "DENEME"), (12, "1047", "Ayşe Nur", "ÖRNEK"), (13, "1102", "Burak", "YAPAY")])  # fmt: skip
    b.execute("INSERT INTO yoklama (id, tarih, ders_no, sube, ogretmen_id, kaynak, kaydeden, mevcut, olusturma, guncelleme) "
              "VALUES (5, '2026-11-16', 1, '10/A', 1, 'tahta', 'ogretmen:112', 3, 1000, 1100)")  # fmt: skip
    b.execute("INSERT INTO yoklama_yok (yoklama_id, ogrenci_id) VALUES (5, 13)")
    b.execute("INSERT INTO yoklama_iz (yoklama_id, zaman, kim, islem, eklenen) VALUES (5, 1000, 'ogretmen:112', 'olustur', '[13]')")
    b.execute("INSERT INTO eokul_islendi (tarih, sube, kullanici, zaman) VALUES ('2026-11-16', '10/A', 'idareci', 1200)")
    if yoklama_ayari is not None:
        b.execute("INSERT INTO ayar (anahtar, deger) VALUES ('yoklama', ?)", (json.dumps(yoklama_ayari),))
    b.commit()
    b.close()


def test_goc_tek_ogedir_ve_sondadir():
    # 0.14.0 göçü tek öğedir; sonraki göçler (0.21.0: usb_anahtar) bu tablolara dokunmaz.
    assert GOC_SIRASI == next(i for i, g in enumerate(vt.GOCLER) if "ALTER TABLE yoklama ADD COLUMN devre" in g)
    assert sum("yoklama_gec" in g or "yoklama_duzeltme" in g or "yoklama_mazeret" in g for g in vt.GOCLER) == 1


def test_goc_onceki_surumden_veri_kaybetmeden_gecer(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    eski_veritabani(tmp_path, {"etkin": True, "maske": "ad_soyadbas", "oturum_dk": 10, "bosta_dk": 4})
    vt.hazirla()
    with vt.islem() as b:
        assert b.execute("PRAGMA user_version").fetchone()[0] == len(vt.GOCLER)
        yoklama = dict(b.execute("SELECT * FROM yoklama").fetchone())
        assert (yoklama["id"], yoklama["tarih"], yoklama["sube"], yoklama["ders_no"], yoklama["ogretmen_id"], yoklama["kaynak"],
                yoklama["kaydeden"], yoklama["mevcut"], yoklama["guncelleme"]) == (5, "2026-11-16", "10/A", 1, 1, "tahta", "ogretmen:112", 3, 1100)  # fmt: skip
        assert yoklama["devre"] == ""  # eski satır: devre kayıttan değil, eskisi gibi türetilir
        assert [tuple(s) for s in b.execute("SELECT yoklama_id, ogrenci_id FROM yoklama_yok")] == [(5, 13)]
        iz = dict(b.execute("SELECT * FROM yoklama_iz").fetchone())
        assert (iz["eklenen"], iz["cikarilan"], iz["gec_eklenen"], iz["gec_cikarilan"]) == ("[13]", "[]", "[]", "[]")
        assert b.execute("SELECT COUNT(*) FROM ogrenci").fetchone()[0] == 3
        assert b.execute("SELECT zaman FROM eokul_islendi").fetchone()[0] == 1200
        for tablo in ("yoklama_gec", "yoklama_duzeltme", "yoklama_mazeret"):
            assert b.execute(f"SELECT COUNT(*) FROM {tablo}").fetchone()[0] == 0
        indeksler = {s[0] for s in b.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        assert {"yoklama_sube_tarih", "yoklama_gec_ogrenci", "yoklama_duzeltme_hucre", "yoklama_mazeret_ogrenci", "yoklama_tek"} <= indeksler
        # Yalnız maske çevrilir; öbür alanlar olduğu gibi kalır.
        assert vt.ayar_al(b, "yoklama") == {"etkin": True, "maske": "no_ad_soyadbas", "oturum_dk": 10, "bosta_dk": 4}
    assert len(list((tmp_path / "goc-oncesi").glob(f"tahta-kontrol-v{GOC_SIRASI}-*.db"))) == 1
    vt.hazirla()  # ikinci kez çalışmak bir şey değiştirmez


@pytest.mark.parametrize(("once", "sonra"), [
    ({"etkin": True, "maske": "no_basharf"}, {"etkin": True, "maske": "no_basharf"}),  # bilerek seçilen biçim kalır
    ({"etkin": False}, {"etkin": False}),  # maske yazılmamış: yeni varsayılan zaten geçerli
    (None, None),  # ayar satırı yok
    ("bozuk", "bozuk"),  # nesne olmayan değer göçü düşürmez
])  # fmt: skip
def test_goc_maske_ayarinin_yalniz_eski_varsayilanini_cevirir(tmp_path, monkeypatch, once, sonra):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    eski_veritabani(tmp_path, once)
    vt.hazirla()
    with vt.islem() as b:
        assert vt.ayar_al(b, "yoklama") == sonra


def test_yeni_tablolarin_kisitlari(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    eski_veritabani(tmp_path, None)
    vt.hazirla()
    mazeret = ("INSERT INTO yoklama_mazeret (ogrenci_id, bas_tarih, bit_tarih, ders_bas, ders_bit, devre, tur, dayanak, giren, olusturma) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'idareci', 2000)")  # fmt: skip
    duzeltme = "INSERT INTO yoklama_duzeltme (tarih, sube, ders_no, ogrenci_id, durum, giren, zaman) VALUES ('2026-11-16', '10/A', 1, ?, ?, 'idareci', 2000)"
    with vt.islem() as b:
        b.execute("INSERT INTO yoklama_gec (yoklama_id, ogrenci_id) VALUES (5, 11)")
        for durum in SOZLESME["durumlar"]["duzeltme"]:
            b.execute(duzeltme, (12, durum))
        assert b.execute("SELECT aciklama FROM yoklama_duzeltme LIMIT 1").fetchone()[0] == ""
        for tur in [*SOZLESME["durumlar"]["mazeret_turleri"], SOZLESME["durumlar"]["mazeret_iptal_turu"]]:
            b.execute(mazeret, (12, "2026-11-16", "2026-11-18", None, None, "", tur, ""))
        for dayanak in SOZLESME["durumlar"]["mazeret_dayanaklari"]:
            b.execute(mazeret, (12, "2026-11-16", "2026-11-16", 2, 4, "sabah", "izinli", dayanak))
        satir = b.execute("SELECT * FROM yoklama_mazeret WHERE ders_bas IS NULL LIMIT 1").fetchone()
        assert (satir["iptal_zamani"], satir["iptal_eden"], satir["devre"], satir["dayanak"]) == (None, None, "", "")
        assert "aciklama" not in satir.keys()  # mazerette serbest metin sütunu yok
        hatali = [
            (duzeltme, (12, "ozurlu")),
            (duzeltme, (999, "yok")),  # olmayan öğrenci
            (mazeret, (12, "2026-11-16", "2026-11-16", None, None, "", "rehberlik", "")),
            (mazeret, (12, "2026-11-16", "2026-11-16", None, None, "", "izinli", "serbest metin")),
            (mazeret, (12, "2026-11-18", "2026-11-16", None, None, "", "izinli", "")),  # bitiş < başlangıç
            (mazeret, (12, "2026-11-16", "2026-11-16", 3, None, "", "izinli", "")),  # yarım ders aralığı
            (mazeret, (12, "2026-11-16", "2026-11-16", 4, 2, "", "izinli", "")),
            (mazeret, (999, "2026-11-16", "2026-11-16", None, None, "", "izinli", "")),
            ("INSERT INTO yoklama_gec (yoklama_id, ogrenci_id) VALUES (5, ?)", (11,)),  # yineleme
            ("INSERT INTO yoklama_gec (yoklama_id, ogrenci_id) VALUES (5, ?)", (999,)),
        ]
        for sql, degerler in hatali:
            with pytest.raises(sqlite3.IntegrityError):
                b.execute(sql, degerler)
        # Geç satırı yoklamayla birlikte gider (CASCADE); düzeltme ve mazeret öğrenciye bağlıdır, açık DELETE ister.
        with pytest.raises(sqlite3.IntegrityError):
            b.execute("DELETE FROM ogrenci WHERE id = 12")
        b.execute("DELETE FROM yoklama WHERE id = 5")
        assert b.execute("SELECT COUNT(*) FROM yoklama_gec").fetchone()[0] == 0
        assert b.execute("SELECT COUNT(*) FROM yoklama_duzeltme").fetchone()[0] == len(SOZLESME["durumlar"]["duzeltme"])


def test_bos_veritabaninda_yeni_sema_dogrudan_kurulur(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    vt.hazirla()
    with vt.islem() as b:
        assert "devre" in {s["name"] for s in b.execute("PRAGMA table_info(yoklama)")}
        assert {s["name"] for s in b.execute("PRAGMA table_info(yoklama_duzeltme)")} == {
            "id", "tarih", "sube", "ders_no", "ogrenci_id", "durum", "aciklama", "giren", "zaman"}  # fmt: skip
        assert {s["name"] for s in b.execute("PRAGMA table_info(yoklama_mazeret)")} == {
            "id", "ogrenci_id", "bas_tarih", "bit_tarih", "ders_bas", "ders_bit", "devre", "tur", "dayanak", "giren",
            "olusturma", "iptal_zamani", "iptal_eden"}  # fmt: skip
