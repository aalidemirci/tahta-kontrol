"""Yoklama 0.14.0 — tahta uçları: ders ön seçimi, teneffüs adayları, ikili eğitim, "geç", eski ajan uyumu.

Sözleşme `tests/yoklama_sozlesme.json`'dadır. Bütün adlar, numaralar ve program satırları UYDURMADIR.
"""

# ruff: noqa: F811  (içe aktarılan fikstürler test parametresi olarak yeniden adlandırılır)
from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_yoklama import (  # noqa: F401
    YOKLAMA_DURUMU,
    ajan,
    ayar_kaydet,
    baslat,
    ders_saatleri_yaz,
    hazir,
    ogrenci_id,
    ogretmen_ekle,
    pin_uret,
)
from yardimci import an, bekle, kimlik, sorgu, tahta_ekle

from tahta_sunucu import vt
from tahta_sunucu import yoklama as yk

SOZLESME = json.loads(Path(__file__).with_name("yoklama_sozlesme.json").read_text(encoding="utf-8"))
YENI_DURUM = {**YOKLAMA_DURUMU, "yetenekler": [*YOKLAMA_DURUMU["yetenekler"], SOZLESME["yetenek"]]}
SABAH = [("07:30", "08:10"), ("08:20", "09:00"), ("09:10", "09:50"), ("10:00", "10:40"), ("10:50", "11:30"), ("11:40", "12:20")]
OGLE = [("12:30", "13:10"), ("13:20", "14:00"), ("14:10", "14:50"), ("15:00", "15:40"), ("15:50", "16:30"), ("16:40", "17:20")]


def yetenekli_yap(tahta, basliklar) -> None:
    """Tahta `yoklama_gec` yeteneğini bildirir (0.14.0 ajanı)."""
    bekle(tahta, basliklar, YENI_DURUM, surum="0.14.0")


def eski_ajan_yap(tahta, basliklar) -> None:
    bekle(tahta, basliklar, YOKLAMA_DURUMU, surum="0.13.1")


def program_satiri(ogretmen_id: int, sube: str, ders_no: int, bas: str, bit: str, gun: int = 0, ders_adi: str = "Yapay Ders") -> None:
    with vt.islem() as b:
        b.execute("INSERT INTO ogretmen_program(sube,gun,ders_no,baslangic,bitis,ders_adi,ogretmen_id,guncelleme) VALUES(?,?,?,?,?,?,?,?)",
                  (sube, gun, ders_no, bas, bit, ders_adi, ogretmen_id, vt.simdi()))  # fmt: skip


def ikili_kur(tahta_id: int | None = None) -> None:
    """Pazartesi: sabah ve öğle devresi; 10/A sabahçı, 10/B öğlenci (derslik programı bir tahtadan)."""
    with vt.islem() as b:
        for devre, ad, saatler in (("sabah", "Sabah", SABAH), ("ogle", "Öğle", OGLE)):
            for no, (bas, bit) in enumerate(saatler, 1):
                b.execute("INSERT INTO ders_saati (gun, devre, devre_adi, ders_no, baslangic, bitis) VALUES (0, ?, ?, ?, ?, ?)",
                          (devre, ad, no, bas, bit))  # fmt: skip
                if tahta_id:
                    b.execute("INSERT INTO tahta_ders (tahta_id, gun, devre, ders_no, sube) VALUES (?, 0, ?, ?, ?)",
                              (tahta_id, devre, no, "10/A" if devre == "sabah" else "10/B"))  # fmt: skip


# ---- ders kuralı (saf) -------------------------------------------------------------------------------
def test_ders_kurali_suren_baslayacak_biten_ve_iki_aday():
    def saat(s, d):
        return int(an(16, s, d).timestamp())

    saatler = [{"ders_no": n, "bas": saat(*bas), "bit": saat(*bit)} for n, (bas, bit) in
               enumerate([((8, 20), (9, 0)), ((9, 10), (9, 50)), ((10, 0), (10, 40))], 1)]  # fmt: skip
    assert yk.ders_kurali(saatler, saat(9, 20)) == (2, [])  # süren
    assert yk.ders_kurali(saatler, saat(8, 16)) == (1, [])  # 5 dk içinde başlayacak
    assert yk.ders_kurali(saatler, saat(9, 52)) == (2, [])  # yalnız biten tutuyor (sıradaki 8 dk sonra)
    assert yk.ders_kurali(saatler, saat(9, 56)) == (None, [2, 3])  # teneffüs: iki aday [biten, baslayacak]
    assert yk.ders_kurali(saatler, saat(10, 55)) == (3, [])  # son 15 dk içinde biten
    assert yk.ders_kurali(saatler, saat(11, 0)) == (None, [])  # son dersten 20 dk sonra: ön seçim yok
    assert yk.ders_kurali(saatler, saat(8, 0)) == (None, [])
    # Yeteneksiz (eski) ajan: biten ders kuralı ve adaylar uygulanmaz.
    assert yk.ders_kurali(saatler, saat(9, 52), biten_dahil=False) == (None, [])
    assert yk.ders_kurali(saatler, saat(9, 56), biten_dahil=False) == (3, [])
    assert yk.ilk_ders_mi(saatler, 1) and not yk.ilk_ders_mi(saatler, 2) and yk.ilk_ders_mi([], 1) and not yk.ilk_ders_mi([], 3)


# ---- teneffüs, öğretmen programı, kimliksiz yanıt ------------------------------------------------------
def test_teneffuste_iki_aday_ogretmen_programi_secer_eski_ajana_biten_onerilmez(panel, tahta, hazir, saat):
    ders_saatleri_yaz()  # 1: 08:20–09:00 · 2: 09:10–09:50 · 3: 10:00–10:40 · 4: 10:50–11:30
    h = hazir["basliklar"]
    saat.ayarla(an(16, 9, 56))
    yetenekli_yap(tahta, h)
    veri = ajan(tahta, h, "oneri").json()
    assert veri["oneri"] == {"sube": "10/A", "ders_no": None, "ders_adi": "", "ogretmen": None, "ders_adaylari": [2, 3]}
    assert veri["simdiki_ders_no"] is None and veri["subeler_once"] == ["10/A"] and veri["devre_adi"] == ""
    assert veri["simdiki_bitti"] is False
    # Az önce biten ders tek adaysa ön seçilir ama "şimdi" diye değil "bitti" diye işaretlenir (simdiki_bitti).
    saat.ayarla(an(16, 9, 52))
    biten = ajan(tahta, h, "oneri").json()
    assert (biten["oneri"]["ders_no"], biten["simdiki_ders_no"], biten["simdiki_bitti"]) == (2, 2, True)
    saat.ayarla(an(16, 9, 20))
    suren = ajan(tahta, h, "oneri").json()
    assert (suren["simdiki_ders_no"], suren["simdiki_bitti"]) == (2, False)
    saat.ayarla(an(16, 9, 56))
    # Kimlik: 2. dersin öğretmeni → biten ders; 3. dersin öğretmeni → başlayacak ders; programsız → öneri yok.
    ikinci_id, ikinci_kod = ogretmen_ekle(panel, "Can", "Deneme")
    ikinci = dict(hazir, kod=ikinci_kod, pin=pin_uret(panel, ikinci_id))
    ucuncu_id, ucuncu_kod = ogretmen_ekle(panel, "Ece", "Uydurma")
    ucuncu = dict(hazir, kod=ucuncu_kod, pin=pin_uret(panel, ucuncu_id))
    once = ajan(tahta, h, "oneri").text
    program_satiri(hazir["ogretmen_id"], "10/A", 2, "09:10", "09:50")
    program_satiri(ikinci_id, "10/A", 3, "10:00", "10:40")
    yanit = baslat(tahta, hazir)
    assert yanit.json()["oneri"] == {"sube": "10/A", "ders_no": 2, "ders_adaylari": []} and yanit.json()["subeler_once"] == ["10/A"]
    assert "Yapay Ders" not in yanit.text and "Örnek" not in yanit.text.replace("A. Örnek", "")  # ders adı ve tam ad yok
    assert baslat(tahta, ikinci).json()["oneri"] == {"sube": "10/A", "ders_no": 3, "ders_adaylari": []}
    programsiz = baslat(tahta, ucuncu).json()
    assert programsiz["oneri"] is None and programsiz["subeler_once"] == []
    # PIN'siz /oneri hiçbir öğretmene bağlı değildir: program eklenince ve öğretmenler değişince aynı kalır.
    assert ajan(tahta, h, "oneri").text == once
    with vt.islem() as b:
        b.execute("UPDATE ogretmen_program SET ogretmen_id = ? WHERE ders_no = 2", (ucuncu_id,))
    assert ajan(tahta, h, "oneri").text == once
    assert "Yapay Ders" not in once and "Deneme" not in once
    # Son dersten 20 dk sonra ön seçim yok.
    saat.ayarla(an(16, 11, 50))
    veri = ajan(tahta, h, "oneri").json()
    assert (veri["oneri"]["ders_no"], veri["oneri"]["ders_adaylari"], veri["simdiki_ders_no"]) == (None, [], None)
    # Eski ajan (yetenek yok): teneffüste yalnız başlayacak ders; yalnız biten ders tutuyorsa öneri yok.
    eski_ajan_yap(tahta, h)
    saat.ayarla(an(16, 9, 56))
    eski = ajan(tahta, h, "oneri").json()
    assert (eski["oneri"]["ders_no"], eski["oneri"]["ders_adaylari"]) == (3, [])
    saat.ayarla(an(16, 9, 52))
    assert ajan(tahta, h, "oneri").json()["oneri"]["ders_no"] is None
    yetenekli_yap(tahta, h)
    assert ajan(tahta, h, "oneri").json()["oneri"]["ders_no"] == 2  # yetenekli ajana biten ders tek aday


def test_ogretmen_programi_tahtadan_farkli_subeyi_onerir_ama_engellemez(panel, tahta, hazir, saat):
    ders_saatleri_yaz()
    saat.ayarla(an(16, 8, 30))
    h = hazir["basliklar"]
    yetenekli_yap(tahta, h)
    program_satiri(hazir["ogretmen_id"], "10/B", 1, "08:20", "09:00")
    program_satiri(hazir["ogretmen_id"], "10/A", 3, "10:00", "10:40")
    veri = baslat(tahta, hazir).json()
    assert veri["oneri"] == {"sube": "10/B", "ders_no": 1, "ders_adaylari": []} and veri["subeler_once"] == ["10/B", "10/A"]
    tahta_onerisi = ajan(tahta, h, "oneri").json()
    assert tahta_onerisi["oneri"]["sube"] == "10/A" and tahta_onerisi["subeler_once"] == ["10/A"]  # tahtanınki değişmez
    # Program yalnız ön seçimdir: programda olmayan şube/ders seçilip kaydedilir.
    kayit = ajan(tahta, h, "kaydet", {"belirtec": veri["belirtec"], "sube": "10/A", "ders_no": 1, "yok": [], "gec": []})
    assert kayit.status_code == 200 and sorgu("SELECT ders_adi, devre FROM yoklama")[0] == {"ders_adi": "", "devre": "normal"}


def test_yanit_anahtar_kumeleri_sozlesmeyle_ayni(panel, tahta, hazir, saat):
    ders_saatleri_yaz()
    saat.ayarla(an(16, 8, 30))
    h = hazir["basliklar"]
    uclar = SOZLESME["uclar"]
    for hazirla in (eski_ajan_yap, yetenekli_yap):  # anahtar kümesi yeteneğe göre DEĞİŞMEZ
        hazirla(tahta, h)
        oneri = ajan(tahta, h, "oneri").json()
        assert set(oneri) == set(uclar["/ajan/yoklama/oneri"]["yanit_anahtarlari"])
        assert set(oneri["oneri"]) == set(uclar["/ajan/yoklama/oneri"]["oneri_anahtarlari"])
        assert all(set(d) == set(uclar["/ajan/yoklama/oneri"]["ders_saati_anahtarlari"]) for d in oneri["ders_saatleri"])
        oturum = baslat(tahta, hazir).json()
        assert set(oturum) == set(uclar["/ajan/yoklama/baslat"]["yanit_anahtarlari"])
        liste = ajan(tahta, h, "liste", {"belirtec": oturum["belirtec"], "sube": "10/A", "ders_no": 1}).json()
        assert set(liste) == set(uclar["/ajan/yoklama/liste"]["yanit_anahtarlari"])
        assert all(set(o) == set(uclar["/ajan/yoklama/liste"]["ogrenci_anahtarlari"]) for o in liste["ogrenciler"])
        govde = {"belirtec": oturum["belirtec"], "sube": "10/A", "ders_no": 1, "yok": []}
        if hazirla is yetenekli_yap:
            govde["gec"] = []
        kayit = ajan(tahta, h, "kaydet", govde)
        assert set(kayit.json()) == set(uclar["/ajan/yoklama/kaydet"]["yanit_anahtarlari"]), kayit.text
    assert sorted(yk.MAZERET_TURLERI) == sorted(SOZLESME["durumlar"]["mazeret_turleri"])
    assert sorted(yk.MAZERET_DAYANAKLARI) == sorted(SOZLESME["durumlar"]["mazeret_dayanaklari"])
    assert yk.GEC_YETENEGI == SOZLESME["yetenek"]
    assert yk.ILETI_GEC_ILK_DERS == SOZLESME["hatalar"]["gec_ilk_ders_degil"]["govde"]["hata"]
    assert yk.ILETI_HEM_YOK_HEM_GEC == SOZLESME["hatalar"]["hem_yok_hem_gec"]["govde"]["hata"]


# ---- liste: okul no sırası ve yeni etiket -------------------------------------------------------------
def test_liste_okul_no_sirasinda_ve_yeni_etiketle_gelir(panel, tahta, hazir):
    ayar_kaydet(panel, yk_maske="no_ad_soyadbas")
    with vt.islem() as b:
        b.execute("DELETE FROM ogrenci")
        for no, ad, soyad in (("1047", "Ayşe Nur", "YILMAZ"), ("9", "Muhammed Emin", "YILDIRIM"), ("103", "Burak", "KAYA"),
                              ("47", "Elif Su", "DEMİR ÖZ"), ("", "Cemre", "DOĞAN")):  # fmt: skip
            b.execute("INSERT INTO ogrenci (sube, okul_no, ad, soyad, aktif, guncelleme) VALUES ('10/A', ?, ?, ?, 1, 0)", (no, ad, soyad))
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    yanit = ajan(tahta, hazir["basliklar"], "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1})
    etiketler = [o["etiket"] for o in yanit.json()["ogrenciler"]]
    assert etiketler == ["9 Muhammed Emin Y.", "47 Elif Su D. Ö.", "103 Burak K.", "1047 Ayşe Nur Y.", "Cemre D."]  # numarasız sonda
    for gizli in ("YILMAZ", "YILDIRIM", "KAYA", "DEMİR", "DOĞAN", "Yılmaz", "Kaya"):
        assert gizli not in yanit.text
    assert all(len(e) <= SOZLESME["sinirlar"]["etiket_en_uzun"] for e in etiketler)


# ---- "geç" ----------------------------------------------------------------------------------------------
def test_gec_yalniz_ilk_derste_kaydedilir_ve_yeniden_acilan_listede_gorunur(panel, tahta, hazir, saat):
    ders_saatleri_yaz()
    h = hazir["basliklar"]
    yetenekli_yap(tahta, h)
    saat.ayarla(an(16, 8, 30))
    a, c, d = ogrenci_id("1047"), ogrenci_id("1102"), ogrenci_id("0215")
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    liste = ajan(tahta, h, "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1}).json()
    assert liste["gec_secilebilir"] is True and liste["gec"] == []
    hem = ajan(tahta, h, "kaydet", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1, "yok": [a], "gec": [a]})
    assert (hem.status_code, hem.json()) == (400, SOZLESME["hatalar"]["hem_yok_hem_gec"]["govde"])
    anahtarsiz = ajan(tahta, h, "kaydet", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1, "yok": [a]})
    assert (anahtarsiz.status_code, anahtarsiz.json()) == (400, SOZLESME["hatalar"]["gec_anahtari_eksik"]["govde"])
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama")[0]["n"] == 0
    kayit = ajan(tahta, h, "kaydet", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1, "yok": [c], "gec": [a, d]})
    assert kayit.json() == {"tamam": True, "yok_sayisi": 1, "gec_sayisi": 2, "mevcut": 4}
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yoklama alındı'")[0]["ayrinti"] == f"10/A 1. ders, 1 yok, 2 geç, öğretmen kodu {hazir['kod']}"
    assert [s["ogrenci_id"] for s in sorgu("SELECT ogrenci_id FROM yoklama_gec ORDER BY ogrenci_id")] == sorted([a, d])
    iz = sorgu("SELECT gec_eklenen, gec_cikarilan FROM yoklama_iz")[0]
    assert json.loads(iz["gec_eklenen"]) == sorted([a, d]) and iz["gec_cikarilan"] == "[]"
    # Yeniden açılan listede var olan durum görünür (YOK ve GEÇ ayrı ayrı).
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    liste = ajan(tahta, h, "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1}).json()
    assert (liste["yok"], liste["gec"]) == ([c], sorted([a, d]))
    # 3. derste geç sunulmaz ve sunucu reddeder.
    saat.ayarla(an(16, 10, 5))
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    liste = ajan(tahta, h, "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 3}).json()
    assert liste["gec_secilebilir"] is False and liste["gec"] == []
    red = ajan(tahta, h, "kaydet", {"belirtec": belirtec, "sube": "10/A", "ders_no": 3, "yok": [], "gec": [a]})
    assert (red.status_code, red.json()) == (400, SOZLESME["hatalar"]["gec_ilk_ders_degil"]["govde"])
    tamam = ajan(tahta, h, "kaydet", {"belirtec": belirtec, "sube": "10/A", "ders_no": 3, "yok": [a], "gec": []})
    assert tamam.json()["gec_sayisi"] == 0
    # Değişmez: bir (yoklama, öğrenci) aynı anda yok ve geç tablosunda olamaz.
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama_yok y JOIN yoklama_gec g ON g.yoklama_id = y.yoklama_id AND g.ogrenci_id = y.ogrenci_id")[0]["n"] == 0
    with vt.islem() as b, pytest.raises(ValueError, match="hem yok hem geç"):
        yk.yoklama_yaz(b, tarih="2026-11-16", sube="10/A", ders_no=1, ogretmen_id=None, kaynak="panel", kaydeden="x", tahta_id=None,
                       yok=[a], gec=[a], kim="x", an=vt.simdi())  # fmt: skip


def test_eski_ajan_geci_silmez_ve_gec_ogrenci_ekli_etiketle_gider(panel, tahta, hazir, saat):
    ders_saatleri_yaz()
    h = hazir["basliklar"]
    saat.ayarla(an(16, 8, 30))
    a, c, d = ogrenci_id("1047"), ogrenci_id("1102"), ogrenci_id("0215")
    yetenekli_yap(tahta, h)
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    ajan(tahta, h, "kaydet", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1, "yok": [], "gec": [a, d]})
    eski_ajan_yap(tahta, h)
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    liste = ajan(tahta, h, "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1}).json()
    etiket = {o["id"]: o["etiket"] for o in liste["ogrenciler"]}
    assert etiket[a].endswith(" (geç)") and etiket[d].endswith(" (geç)") and not etiket[c].endswith(" (geç)")
    assert all(len(e) <= 40 for e in etiket.values()) and liste["yok"] == []
    # Gövdede `gec` yok: geç korunur; yalnız yeni "yok"a giren geçten çıkar.
    kayit = ajan(tahta, h, "kaydet", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1, "yok": [c, d]})
    assert kayit.json() == {"tamam": True, "yok_sayisi": 2, "gec_sayisi": 1, "mevcut": 4}
    assert [s["ogrenci_id"] for s in sorgu("SELECT ogrenci_id FROM yoklama_gec")] == [a]
    assert sorted(s["ogrenci_id"] for s in sorgu("SELECT ogrenci_id FROM yoklama_yok")) == sorted([c, d])


# ---- 0.13.1 ajanının çözücülerinin SABİTLENMİŞ kopyası (tahta_ajan/servis.py, 9a30004) -------------------
def _eski_tamsayi_mi(deger) -> bool:
    return isinstance(deger, int) and not isinstance(deger, bool)


def _eski_kes(deger, sinir: int) -> str:
    return str(deger or "")[:sinir]


def _eski_oneri_coz(deger) -> dict:
    deger = deger if isinstance(deger, dict) else {}
    saatler = []
    for s in deger.get("ders_saatleri") if isinstance(deger.get("ders_saatleri"), list) else []:
        no = s.get("ders_no") if isinstance(s, dict) else None
        if _eski_tamsayi_mi(no) and 1 <= no <= 20 and len(saatler) < 20:
            saatler.append({"ders_no": no, "baslangic": _eski_kes(s.get("baslangic"), 5), "bitis": _eski_kes(s.get("bitis"), 5),
                            "secilebilir": bool(s.get("secilebilir", True))})  # fmt: skip
    en_cok = deger.get("ders_no_en_cok")
    if not (_eski_tamsayi_mi(en_cok) and 1 <= en_cok <= 20):
        en_cok = max((s["ders_no"] for s in saatler), default=12)
    subeler = [s[:16] for s in deger.get("subeler") or [] if isinstance(s, str) and s.strip()][:200]
    oneri = deger.get("oneri") if isinstance(deger.get("oneri"), dict) else {}
    sube = oneri.get("sube") if isinstance(oneri.get("sube"), str) and oneri.get("sube") else None
    ders_no = oneri.get("ders_no") if _eski_tamsayi_mi(oneri.get("ders_no")) and 1 <= oneri["ders_no"] <= en_cok else None
    return {"tarih_yazi": _eski_kes(deger.get("tarih_yazi"), 40), "ders_saatleri": saatler, "ders_no_en_cok": en_cok,
            "subeler": subeler, "sube": sube[:16] if sube else None, "ders_no": ders_no}  # fmt: skip


def _eski_yoklama_listesi_coz(deger) -> list[dict]:
    liste, gorulen = [], set()
    for oge in deger if isinstance(deger, list) else []:
        if len(liste) >= 300:
            break
        if isinstance(oge, dict) and _eski_tamsayi_mi(oge.get("id")) and oge["id"] not in gorulen:
            gorulen.add(oge["id"])
            liste.append({"id": oge["id"], "etiket": _eski_kes(oge.get("etiket"), 40)})
    return liste


def test_0_13_1_ajan_cozuculeri_0_14_0_yanitlarini_okur(panel, tahta, hazir, saat):
    ayar_kaydet(panel, yk_maske="no_ad_soyadbas")
    ders_saatleri_yaz()
    saat.ayarla(an(16, 9, 56))  # teneffüs
    h = hazir["basliklar"]
    eski_ajan_yap(tahta, h)
    oneri = _eski_oneri_coz(ajan(tahta, h, "oneri").json())
    assert (oneri["sube"], oneri["ders_no"], len(oneri["ders_saatleri"])) == ("10/A", 3, 4) and oneri["subeler"] == ["10/A", "10/B"]
    oturum = baslat(tahta, hazir).json()
    assert isinstance(oturum["belirtec"], str) and oturum["ogretmen"]["etiket"]
    yanit = ajan(tahta, h, "liste", {"belirtec": oturum["belirtec"], "sube": "10/A", "ders_no": 3}).json()
    liste = _eski_yoklama_listesi_coz(yanit["ogrenciler"])
    assert [o["etiket"] for o in liste] == ["0215 Cemre D.", "1047 Ayşe Y.", "1102 Burak K.", "1150 Ayşe Y."]
    kayit = ajan(tahta, h, "kaydet", {"belirtec": oturum["belirtec"], "sube": "10/A", "ders_no": 3, "yok": [liste[0]["id"]]})
    assert kayit.status_code == 200 and kayit.json()["yok_sayisi"] == 1
    # Sözleşmedeki uydurma örnekler de eski çözücülerden düşmeden geçer.
    for ornek in SOZLESME["uclar"]["/ajan/yoklama/oneri"]["ornekler"].values():
        assert set(_eski_oneri_coz(ornek["yanit"])) == {"tarih_yazi", "ders_saatleri", "ders_no_en_cok", "subeler", "sube", "ders_no"}
    for ornek in SOZLESME["uclar"]["/ajan/yoklama/liste"]["ornekler"].values():
        assert all(len(o["etiket"]) <= 40 for o in _eski_yoklama_listesi_coz(ornek["yanit"]["ogrenciler"]))


# ---- ikili eğitim -----------------------------------------------------------------------------------------
def test_ikili_egitimde_devre_gec_ve_subesiz_pencere(panel, tahta, hazir, saat):
    h = hazir["basliklar"]
    ikili_kur(kimlik(h))
    yetenekli_yap(tahta, h)
    bos = tahta_ekle(panel, tahta, "Şubesiz Tahta", durum=YENI_DURUM)  # şubesi ve programı olmayan tahta
    # Şubesiz açılış, yalnız sabah penceresi: sabah saatleri, devre adı ve "şimdi" işareti gelir; ders önerilmez.
    saat.ayarla(an(16, 9, 20))
    veri = ajan(tahta, bos, "oneri").json()
    assert veri["oneri"]["sube"] is None and veri["oneri"]["ders_no"] is None and veri["subeler_once"] == []
    assert (veri["devre_adi"], veri["simdiki_ders_no"], veri["ders_saatleri"][0]["baslangic"]) == ("Sabah", 3, "07:30")
    # Devir saati (iki pencere çakışıyor): ders saatleri boş, hiçbir ders ön seçili değil.
    saat.ayarla(an(16, 12, 27))
    veri = ajan(tahta, bos, "oneri").json()
    assert (veri["ders_saatleri"], veri["simdiki_ders_no"], veri["devre_adi"], veri["ders_no_en_cok"]) == ([], None, "", 12)
    # Şube seçilince o şubenin devresi ve ders önerisi gelir (kural 25).
    ogle = ajan(tahta, bos, "oneri", {"sube": "10/B"}).json()
    assert (ogle["devre_adi"], ogle["ders_saatleri"][0]["baslangic"], ogle["oneri"]["ders_no"]) == ("Öğle", "12:30", 1)
    # Geç: sabah ve öğle devresinin İLK dersi ayrı ayrı.
    saat.ayarla(an(16, 12, 40))
    belirtec = baslat(tahta, hazir).json()["belirtec"]

    def gec_sec(sube, ders_no):
        return ajan(tahta, h, "liste", {"belirtec": belirtec, "sube": sube, "ders_no": ders_no}).json()["gec_secilebilir"]

    assert gec_sec("10/B", 1) is True and gec_sec("10/A", 1) is True and gec_sec("10/A", 2) is False
    kayit = ajan(tahta, h, "kaydet", {"belirtec": belirtec, "sube": "10/B", "ders_no": 1, "yok": [], "gec": [ogrenci_id("2001")]})
    assert kayit.json()["gec_sayisi"] == 1 and sorgu("SELECT devre FROM yoklama")[0]["devre"] == "ogle"


def test_devre_derslik_programi_yoksa_ogretmen_programi_saatlerinden_bulunur(panel, tahta, hazir, saat):
    ikili_kur()  # derslik programı yok: şubelerin devresi bilinmiyor
    h = hazir["basliklar"]
    yetenekli_yap(tahta, h)
    saat.ayarla(an(16, 13, 30))
    assert ajan(tahta, h, "oneri", {"sube": "10/B"}).json()["ders_saatleri"] == []  # belirlenemedi: saatsiz 1–12
    program_satiri(hazir["ogretmen_id"], "10/B", 2, "13:20", "14:00", ders_adi="Uydurma Ders")
    program_satiri(hazir["ogretmen_id"], "10/B", 3, "14:10", "14:50", ders_adi="Uydurma Ders")
    yanit = ajan(tahta, h, "oneri", {"sube": "10/B"})
    veri = yanit.json()
    assert (veri["devre_adi"], veri["oneri"]["ders_no"], veri["ders_saatleri"][0]["baslangic"]) == ("Öğle", 2, "12:30")
    assert "Uydurma Ders" not in yanit.text
    plan = {"dersler": [], "program_gunu": 0}
    assert yk.program_devresi(plan, [(1, "08:00")]) is None and yk.devre_sec(plan, set(), []) is None


# ---- tahtaya mazeret ve geçmiş gün gitmez -------------------------------------------------------------------
def test_mazeret_ve_duzeltme_notu_tahta_yanitina_girmez(panel, tahta, hazir, saat):
    ders_saatleri_yaz()
    h = hazir["basliklar"]
    yetenekli_yap(tahta, h)
    saat.ayarla(an(16, 8, 30))
    a = ogrenci_id("1047")
    belirtec = baslat(tahta, hazir).json()["belirtec"]
    govde = {"belirtec": belirtec, "sube": "10/A", "ders_no": 1}
    once = ajan(tahta, h, "liste", govde).json()
    with vt.islem() as b:
        for bas, bit in (("2026-11-16", "2026-11-16"), ("2026-11-20", "2026-11-25")):  # bugünkü ve gelecek mazeret
            b.execute("INSERT INTO yoklama_mazeret (ogrenci_id, bas_tarih, bit_tarih, tur, dayanak, giren, olusturma) "
                      "VALUES (?, ?, ?, 'raporlu', 'belge', 'yonetici', ?)", (a, bas, bit, vt.simdi()))  # fmt: skip
    yanit = ajan(tahta, h, "liste", govde)
    sonra = yanit.json()
    assert {k: v for k, v in sonra.items() if k != "kalan_sn"} == {k: v for k, v in once.items() if k != "kalan_sn"}
    for sizinti in ("raporlu", "mazeret", "belge", "özür", "2026-11-20"):
        assert sizinti not in yanit.text
