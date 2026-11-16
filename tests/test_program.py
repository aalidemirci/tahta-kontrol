"""Aşama 3 — ders programının saf işlevleri: Okul Zili okuma, takvim, elle üretim, derslik CSV'si,
kilit aralıkları. Saatler sabit verilir; gerçek saate bağlı test yoktur. Veriler uydurmadır."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import date
from pathlib import Path

import pytest

ORNEK = Path(__file__).parent / "ornek" / "okulzili-ornek.json"


def ornek() -> dict:
    return json.loads(ORNEK.read_text(encoding="utf-8"))


def olay(saat, tur, etiket, devre="normal"):
    return {"at": saat + ":00", "event_type": tur, "label": etiket, "session": devre, "sequence": 0}


def zip_yap(ayarlar: bytes, ozet: str | None = None, ekler: dict | None = None) -> bytes:
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        manifest = {"format": 1, "created_at": "2026-11-16T09:00:00", "files": {"ayarlar.json": ozet or hashlib.sha256(ayarlar).hexdigest()}}
        z.writestr("manifest.json", json.dumps(manifest))
        z.writestr("ayarlar.json", ayarlar)
        for ad, veri in (ekler or {}).items():
            bilgi = zipfile.ZipInfo("x")
            bilgi.filename = ad  # zipfile adı düzeltmesin (ters bölü, sürücü harfi)
            z.writestr(bilgi, veri)
    return tampon.getvalue()


# 1
def test_okulzili_json_ders_saatleri_turetilir():
    from tahta_sunucu import program

    cozum = program.okulzili_oku(ORNEK.read_bytes(), "ayarlar.json")
    pazartesi = [(d[3], d[4], d[5]) for d in cozum["dersler"] if d[0] == 0]
    assert pazartesi == [(1, "08:20", "09:00"), (2, "09:10", "09:50"), (3, "09:50", "10:30")]
    assert {d[2] for d in cozum["dersler"]} == {"Normal"}
    assert not cozum["hatalar"]
    assert any("Cumartesi" in u for u in cozum["uyarilar"])
    kural = cozum["takvim"]["kurallar"][0]
    assert kural["tur"] == "kisaltilmis_gun" and kural["dersler"] == [["normal", 1, "08:20", "08:50"]]


# 2
def test_okulzili_blok_bolme_noktasiz_esit_bolunur():
    from tahta_sunucu import program

    dersler = program.ders_saatleri(
        [olay("09:10", "ders_baslangici", "2-4. ders bloğu öğretmen zili"), olay("11:10", "ders_bitisi", "2-4. ders bloğu bitişi")]
    )
    assert dersler == [("normal", 2, "09:10", "09:50"), ("normal", 3, "09:50", "10:30"), ("normal", 4, "10:30", "11:10")]
    uyarilar: list[str] = []
    assert program.ders_saatleri([olay("10:00", "ders_bitisi", "x"), olay("10:10", "ders_baslangici", "5. ders")], uyarilar) == []
    assert len(uyarilar) == 2  # eşi olmayan bitiş ve başlangıç


# 3
def test_okulzili_ikili_egitim_oturum_adlari():
    from tahta_sunucu import program

    yapi = ornek()
    yapi["weekly_schedule"] = {
        "1": [
            olay("07:30", "ders_baslangici", "Sabah · 1. ders öğretmen zili", "sabah"),
            olay("08:10", "ders_bitisi", "Sabah · 1. ders bitişi", "sabah"),
            olay("13:00", "ders_baslangici", "Öğle · 1. ders öğretmen zili", "ogle"),
            olay("13:40", "ders_bitisi", "Öğle · 1. ders bitişi", "ogle"),
            olay("14:00", "ders_baslangici", "Kurs · 1. ders", "kurs1"),
            olay("14:30", "ders_bitisi", "Kurs bitişi", "kurs1"),
        ]
    }
    yapi["day_schedules"] = {"1": {"sessions": [{"session_id": "kurs1", "name": "Etüt"}]}}
    cozum = program.okulzili_yapisindan(yapi)
    adlar = {d[1]: d[2] for d in cozum["dersler"]}
    assert adlar == {"sabah": "Sabah", "ogle": "Öğleden sonra", "kurs1": "Etüt"}
    assert all(d[3] == 1 for d in cozum["dersler"])
    assert not cozum["hatalar"]


# 4
def test_okulzili_zip_yalniz_ayarlar_okunur_ve_ozet_denetlenir(monkeypatch):
    from tahta_sunucu import program

    ham = ORNEK.read_bytes()
    with pytest.raises(ValueError, match="özeti tutmuyor"):
        program.okulzili_oku(zip_yap(ham, ozet="0" * 64), "yedek.okulzili")
    yedek = zip_yap(ham, ekler={"dosyalar/zil.wav": b"RIFF" * 10})
    acilan = []
    gercek = zipfile.ZipFile.open
    monkeypatch.setattr(zipfile.ZipFile, "open", lambda self, ad, *a, **k: acilan.append(getattr(ad, "filename", ad)) or gercek(self, ad, *a, **k))
    cozum = program.okulzili_oku(yedek, "yedek.okulzili")
    assert len(cozum["dersler"]) == 3
    assert sorted(acilan) == ["ayarlar.json", "manifest.json"]


# 5
def test_okulzili_zip_tehlikeli_yol_reddedilir():
    from tahta_sunucu import program

    for ad in ("../kotu.txt", "/mutlak.txt", "a\\b.txt", "c:x.txt"):
        with pytest.raises(ValueError, match="güvenli olmayan"):
            program.okulzili_oku(zip_yap(ORNEK.read_bytes(), ekler={ad: b"x"}), "yedek.zip")
    with pytest.raises(ValueError, match="ZIP"):
        program.okulzili_oku(b"zip degil", "yedek.okulzili")


# 6
def test_okulzili_desteklenmeyen_surum_reddedilir():
    from tahta_sunucu import program

    for surum in (5, 8):
        yapi = ornek() | {"schema_version": surum}
        with pytest.raises(ValueError, match=f"desteklenmiyor \\({surum}\\)"):
            program.okulzili_oku(json.dumps(yapi).encode(), "ayarlar.json")
    for surum in (6, 7):
        assert program.okulzili_oku(json.dumps(ornek() | {"schema_version": surum}).encode(), "ayarlar.json")["dersler"]


# 7
def test_okulzili_kullanilmayan_alanlar_saklanmaz():
    from tahta_sunucu import program

    cozum = program.okulzili_oku(ORNEK.read_bytes(), "ayarlar.json")
    metin = json.dumps(cozum, ensure_ascii=False)
    for yasak in ("Örnek Anadolu Lisesi", "school_name", "sound", "ogretmen", "selected_device", "varsayilan"):
        assert yasak not in metin, yasak


# 8
def test_gun_plani_ara_tatil_resmi_tatil_arife():
    from tahta_sunucu import program

    saatler = [(g, "normal", "Normal", n, b, s) for g in range(5) for n, b, s in ((1, "08:20", "09:00"), (6, "13:05", "13:45"))]
    takvim = program.okulzili_oku(ORNEK.read_bytes(), "ayarlar.json")["takvim"]
    assert program.plan_hesapla(date(2026, 11, 10), saatler, takvim)["tatil"] == "1. ara tatil"
    resmi = program.plan_hesapla(date(2026, 10, 29), saatler, takvim)
    assert resmi["dersler"] == [] and resmi["tatil"] == "Cumhuriyet Bayramı"
    arife = program.plan_hesapla(date(2026, 10, 28), saatler, takvim)
    assert [d[2] for d in arife["dersler"]] == [1] and arife["tatil"] is None  # 13:05 dersi düştü
    assert len(program.plan_hesapla(date(2026, 11, 16), saatler, takvim)["dersler"]) == 2
    assert program.plan_hesapla(date(2027, 1, 28), saatler, takvim)["tatil"] == "Öğretim dönemi dışında"
    takvimsiz = program.plan_hesapla(date(2026, 10, 29), saatler, {"ogretim": None, "resmi_tatiller": False, "kurallar": []})
    assert len(takvimsiz["dersler"]) == 2  # takvim yoksa her tanımlı gün ders günü (K31)


# 9
def test_gun_plani_kural_onceligi():
    from tahta_sunucu import program

    saatler = [(g, "normal", "Normal", 1, "08:20", "09:00") for g in range(5)] + [(2, "normal", "Normal", 2, "09:10", "09:50")]
    takvim = {"ogretim": None, "resmi_tatiller": False, "kurallar": [
        {"ad": "Tatil", "tur": "tatil", "bas": "2026-12-01", "bit": "2026-12-31"},
        {"ad": "Kısa", "tur": "kisaltilmis_gun", "bas": "2026-12-02", "bit": "2026-12-03", "dersler": [["normal", 1, "08:20", "08:40"]]},
        {"ad": "Özel", "tur": "tarihe_ozel_program", "bas": "2026-12-03", "bit": "2026-12-03", "dersler": [["normal", 1, "10:00", "10:40"]]},
        {"ad": "Telafi", "tur": "telafi", "bas": "2026-12-05", "bit": "2026-12-05", "hedef_gun": 2},
    ]}  # fmt: skip
    assert program.plan_hesapla(date(2026, 12, 1), saatler, takvim)["tatil"] == "Tatil"
    assert program.plan_hesapla(date(2026, 12, 2), saatler, takvim)["dersler"][0][3].strftime("%H:%M") == "08:20"
    assert program.plan_hesapla(date(2026, 12, 2), saatler, takvim)["dersler"][0][4].strftime("%H:%M") == "08:40"
    assert program.plan_hesapla(date(2026, 12, 3), saatler, takvim)["dersler"][0][3].strftime("%H:%M") == "10:00"
    telafi = program.plan_hesapla(date(2026, 12, 5), saatler, takvim)  # cumartesi, çarşamba programı
    assert [d[2] for d in telafi["dersler"]] == [1, 2] and telafi["program_gunu"] == 2


# 10
def test_gun_plani_sinav_pencereleri():
    from tahta_sunucu import program

    yapi = ornek()
    yapi["date_rules"] = [{"name": "Deneme", "kind": "sinav", "start": "2026-11-16", "end": "2026-11-20", "enabled": True,
                           "exam_plan": {"slots": [{"start": "10:00", "minutes": 40}], "weekdays": [0, 1],
                                         "lead_minutes": 5, "keep_lesson_bells": True}}]  # fmt: skip
    takvim = program.okulzili_yapisindan(yapi)["takvim"]
    assert takvim["kurallar"][0] == {"ad": "Deneme", "tur": "sinav_plani", "bas": "2026-11-16", "bit": "2026-11-20",
                                     "gunler": [0, 1], "pencereler": [["09:55", "10:40"]], "tum_gun": False}  # fmt: skip
    saatler = [(0, "normal", "Normal", 1, "08:20", "09:00")]
    plan = program.plan_hesapla(date(2026, 11, 16), saatler, takvim)
    assert [(b.strftime("%H:%M"), s.strftime("%H:%M")) for b, s in plan["sinav"]] == [("09:55", "10:40")]
    assert program.plan_hesapla(date(2026, 11, 18), saatler, takvim)["sinav"] == []  # çarşamba planda yok
    takvim["kurallar"][0]["tum_gun"] = True
    assert program.plan_hesapla(date(2026, 11, 16), saatler, takvim)["tum_gun_sinav"] is True


# 11
def test_resmi_tatiller_okul_zili_ile_ayni():
    from tahta_sunucu import program

    # Okul Zili holidays.py::FIXED_HOLIDAYS listesinin elle eşitlenmiş kopyası (depoya bağımlılık kurulmaz).
    assert [(a, g) for a, g, _ in program.RESMI_TATILLER] == [(1, 1), (4, 23), (5, 1), (5, 19), (7, 15), (8, 30), (10, 29)]


# 12
def test_elle_zil_uretimi_ve_dogrulama():
    from tahta_sunucu import program

    satirlar = program.elle_uret({"devre_adi": "Normal", "ilk_ders": "08:20", "ders_sayisi": "8", "ders_dk": "40",
                                  "teneffus_dk": "10", "ogle_sonra": "4", "ogle_dk": "45", "gunler": ["0", "4"]})  # fmt: skip
    pzt = [(s[3], s[4], s[5]) for s in satirlar if s[0] == 0]
    assert pzt[3] == (4, "10:50", "11:30") and pzt[4] == (5, "12:15", "12:55") and len(pzt) == 8
    assert {s[0] for s in satirlar} == {0, 4} and {s[1] for s in satirlar} == {"normal"}
    with pytest.raises(ValueError, match="gece yarısı"):
        program.elle_uret({"ilk_ders": "22:00", "ders_sayisi": "5", "ders_dk": "40", "teneffus_dk": "10",
                           "ogle_sonra": "0", "ogle_dk": "0", "gunler": ["0"]})  # fmt: skip
    hatalar: list[str] = []
    program.dogrula([(0, "normal", "Normal", 1, "08:20", "09:00"), (0, "normal", "Normal", 2, "08:50", "09:30")], hatalar, [])
    assert hatalar and "çakışıyor" in hatalar[0]
    hatalar = []
    uyarilar: list[str] = []
    program.dogrula([(0, "sabah", "Sabah", 1, "08:20", "13:00"), (0, "ogle", "Öğle", 1, "12:30", "13:10")], hatalar, uyarilar)
    assert not hatalar and uyarilar  # devreler arası çakışma yalnız uyarı (K3)
    uyarilar = []
    assert program.ders_saatleri([olay("10:00", "ders_baslangici", "1. ders"), olay("09:00", "blok_ici_gecis", ""),
                                  olay("09:50", "ders_bitisi", "")], uyarilar) == []  # fmt: skip


def test_kilit_araliklari_ve_nedenler():
    from tahta_sunucu import program

    saatler = program.elle_uret({"ilk_ders": "08:20", "ders_sayisi": "6", "ders_dk": "40", "teneffus_dk": "10",
                                 "ogle_sonra": "4", "ogle_dk": "45", "gunler": ["0"]})  # fmt: skip
    plan = program.plan_hesapla(date(2026, 11, 16), saatler, None)
    ts = {d[2]: (int(d[3].timestamp()), int(d[4].timestamp())) for d in plan["dersler"]}
    hepsi = program.kilit_araliklari(plan, list(ts.values()))
    assert [a["neden"] for a in hepsi] == ["Teneffüs", "Teneffüs", "Teneffüs", "Öğle arası", "Teneffüs"]
    yalniz = program.kilit_araliklari(plan, [ts[1], ts[4], ts[5]])
    assert [a["neden"] for a in yalniz] == ["Bu saatte bu derslikte ders yok", "Öğle arası", "Bu saatte bu derslikte ders yok"]
    assert yalniz[0]["bas"] == ts[1][1] and yalniz[0]["bit"] == ts[4][0]
    assert yalniz[-1]["bit"] == ts[6][1]


# 15
def test_derslik_csv_eslesme_ve_hatalar():
    from tahta_sunucu import program

    saatler = [(g, "normal", "Normal", n, "08:00", "08:40") for g in range(5) for n in range(1, 9)]
    saatler += [(2, "ogle", "Öğleden sonra", 1, "13:00", "13:40")]
    tahtalar = [{"id": 1, "ad": "T-1", "derslik": "Z-04"}, {"id": 2, "ad": "İnkılap Odası", "derslik": ""},
                {"id": 3, "ad": "T-3", "derslik": "Z-04 Dersliği"}]  # fmt: skip
    csv = (
        "derslik,gün,ders,devre,şube\n"
        "z-04,Pazartesi,1-4,,9/A\n"
        "İNKILAP ODASI,Salı,\"1,2,5\",,10-b\n"
        "Z-04,Pzt,6,,11/X1\n"
        "Fizik Lab,Perşembe,5-6,,12/A\n"
        "Z-04,Funday,1,,\n"
        "Z-04,3,1,,\n"
        "Z-04,Çarşamba,2,Öğleden sonra,\n"
        "Z-04,1,9,,\n"
        "Z-04,Pazartesi,2,,9/B\n"
    )
    cozum = program.derslik_csv_oku(("﻿" + csv).encode("utf-8"), saatler, tahtalar)
    assert cozum["eslesmeyen"] == ["Fizik Lab"]
    assert set(cozum["tahtalar"]) == {1, 2, 3}  # "Z-04 Dersliği" de Z-04 sayılır; iki tahtaya uygulanır
    assert [1, 2, 5] == [s[2] for s in cozum["tahtalar"][2]] and cozum["tahtalar"][2][0][3] == "10/B"
    pzt = {s[2]: s[3] for s in cozum["tahtalar"][1] if s[0] == 0}
    assert pzt == {1: "9/A", 2: "9/B", 3: "9/A", 4: "9/A", 6: ""}  # son satır kazanır; anlaşılmayan şube boş
    hata = " | ".join(cozum["hatalar"])
    assert "6. satır: gün anlaşılamadı" in hata and "iki devreli" in hata and "9. ders tanımlı değil" in hata
    assert "8. satır" in hata  # Öğleden sonra devresinde 2. ders yok
    assert any("Aynı dersliğe bağlı 2 tahta" in u for u in cozum["uyarilar"])
    noktali = program.derslik_csv_oku("derslik;gun;ders\nZ-04;Cuma;1\n".encode("cp1254"), saatler, tahtalar)
    assert noktali["tahtalar"][1] == [[4, "normal", 1, ""]]
    with pytest.raises(ValueError, match="zil saatlerini"):
        program.derslik_csv_oku(b"derslik;gun;ders\n", [], tahtalar)


# 16
def test_derslik_csv_ogretmen_sutunu_yok_sayilir():
    from tahta_sunucu import program

    saatler = [(0, "normal", "Normal", 1, "08:20", "09:00")]
    cozum = program.derslik_csv_oku(
        "derslik;gun;ders;ogretmen\nZ-04;Pazartesi;1;Ayşe Örnek\n".encode(), saatler, [{"id": 1, "ad": "T", "derslik": "Z-04"}]
    )
    assert cozum["yok_sayilan"] == ["ogretmen"]
    assert "Ayşe" not in json.dumps(cozum, ensure_ascii=False)
    assert any("ogretmen" in u for u in cozum["uyarilar"])
