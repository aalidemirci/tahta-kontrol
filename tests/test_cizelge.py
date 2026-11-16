"""0.10.0 — zil düzenleyici: saf işlevler (cizelge.py, program.plan_hesapla yerel), göç ve ilk taşıma.

Bütün veriler uydurmadır ("Normal gün", "Kısa gün"). Saatler sabit verilir; gerçek saate bağlı test yoktur.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from tahta_sunucu import cizelge, program


def taslak(*devreler, ad="Normal gün") -> dict:
    """taslak(("normal", [("08:20", "09:00"), ...]), ...) → cizelge taslağı."""
    t = {"ad": ad, "devreler": [{"devre": d, "devre_adi": cizelge.DEVRELER.get(d, d),
                                 "satirlar": [{"r": "", "bas": b, "bit": s, "sil": False} for b, s in satirlar]}
                                for d, satirlar in devreler]}  # fmt: skip
    return cizelge.kimlikleri_yenile(t)


def hizli(devre: str, **alanlar) -> dict:
    p = {f"{devre}_uret": "1"}
    for a in cizelge.HIZLI_ALANLAR:
        p[f"{devre}_{a}"] = str(alanlar.get(a, cizelge.HIZLI_VARSAYILAN[devre][a]))
    return p


def metinler(hatalar) -> list[str]:
    return [h["metin"] for h in hatalar]


# 1
def test_hizli_uret_tek_devre_varsayilan_8_ders_ogle_arasi_4ten_sonra():
    t = cizelge.varsayilan_taslak("Normal gün", "tek")
    dersler = cizelge.numarala(t)
    assert len(dersler) == 8 and {d[0] for d in dersler} == {"normal"}
    assert dersler[0][2:] == (1, "08:20", "09:00") and dersler[3][2:] == (4, "10:50", "11:30")
    assert dersler[4][2:] == (5, "12:15", "12:55")  # 4. dersten sonra 45 dk öğle
    yeni, hatalar = cizelge.hizli_uret(hizli("normal", ilk="08:30", sayi=6), t)
    assert not hatalar and cizelge.numarala(yeni)[0][3] == "08:30" and len(cizelge.numarala(yeni)) == 6
    # işaretsiz devre korunur
    korunan, _ = cizelge.hizli_uret({"normal_ilk": "07:00"}, t)
    assert cizelge.numarala(korunan) == dersler


# 2
def test_hizli_uret_ogle_devresi_baslangici_sabahtan_onerilir_5e_yuvarlanir():
    t = taslak(("sabah", []), ("ogle", []))
    p = {**hizli("sabah", ilk="07:40", sayi=6, teneffus_dk=10), **hizli("ogle")}
    yeni, hatalar = cizelge.hizli_uret(p, t)
    assert not hatalar
    ogle = [d for d in cizelge.numarala(yeni) if d[0] == "ogle"]
    assert ogle[0][3] == "12:50"  # sabah 12:30 biter + 20 dk = 12:50 (zaten 5'in katı)
    assert cizelge.ogle_onerisi("12:23") == "12:45" and cizelge.ogle_onerisi("23:50") is None
    _, hatalar = cizelge.hizli_uret(hizli("ogle"), taslak(("ogle", [])))
    assert hatalar == ["Öğleden sonra devresinin ilk dersini yazın."]


# 3
def test_hizli_uret_gece_yarisini_gecerse_hata():
    t = taslak(("normal", [("08:20", "09:00")]))
    ayni, hatalar = cizelge.hizli_uret(hizli("normal", ilk="22:00", sayi=5), t)
    assert hatalar == ["Normal: dersler gece yarısını geçiyor; ilk dersi ya da ders sayısını değiştirin."]
    assert ayni is t
    _, hatalar = cizelge.hizli_uret(hizli("normal", sayi=21, uzun_sonra=0), t)
    assert "1–20" in hatalar[0]


# 4
def test_dogrula_bitis_baslangictan_once_ve_sure_siniri():
    h, _ = cizelge.dogrula(taslak(("normal", [("09:00", "08:20"), ("10:00", "10:05"), ("11:00", "11:40")])))
    m = metinler(h)
    assert "Normal: 09:00–08:20 dersinin bitişi başlangıcından sonra olmalı; dersler gece yarısını aşamaz." in m
    assert "Normal: 1. ders 5 dakika; ders süresi 10–180 dakika olmalı." in m
    assert h[0]["alan"] == "r0_bit"
    h, _ = cizelge.dogrula(taslak(("normal", [("8.2x", "09:00")])))
    assert metinler(h) == ["Normal: 1. satırdaki saat SS:DD biçiminde olmalı (ör. 08:20)."]


# 5
def test_dogrula_ayni_devrede_cakisma_hata_sifir_teneffus_serbest():
    h, _ = cizelge.dogrula(taslak(("normal", [("08:20", "09:00"), ("08:50", "09:30")])))
    assert metinler(h) == ["Normal: 1. ders (08:20–09:00) ile 2. ders (08:50–09:30) çakışıyor."]
    h, _ = cizelge.dogrula(taslak(("normal", [("08:20", "09:00"), ("09:00", "09:40")])))
    assert h == []
    h, _ = cizelge.dogrula(taslak(("normal", [("08:20", "09:00"), ("08:20", "09:10")])))
    assert metinler(h) == ["Normal: 08:20 başlangıçlı iki ders var."]
    h, _ = cizelge.dogrula(taslak(("normal", [(f"{6 + i // 2:02d}:{30 * (i % 2):02d}", f"{6 + i // 2:02d}:{30 * (i % 2) + 20:02d}")
                                              for i in range(21)])))  # fmt: skip
    assert "Normal: en çok 20 ders olabilir." in metinler(h)
    h, _ = cizelge.dogrula(taslak(("normal", [])), "Normal gün", ["normal GÜN"])
    assert metinler(h) == ["Bu adda bir çizelge zaten var.", "Çizelgede en az bir ders olmalı."]
    h, _ = cizelge.dogrula(taslak(("normal", [("08:20", "09:00")])), "x" * 41)
    assert metinler(h) == ["Çizelge adı 1–40 karakter olmalı."]


# 6
def test_dogrula_devreler_arasi_cakisma_uyari_kaydi_engellemez():
    t = taslak(("sabah", [("07:40", "08:20"), ("12:00", "12:40")]), ("ogle", [("12:30", "13:10")]))
    h, u = cizelge.dogrula(t)
    assert h == []
    assert "Sabah ve Öğleden sonra devreleri 12:30–12:40 arasında çakışıyor; bu aralıkta teneffüs kilidi verilmez." in u
    _, u = cizelge.dogrula(taslak(("normal", [("08:20", "09:00")]), ("sabah", [("07:00", "07:40")])))
    assert any("ikili eğitimde Normal'i kullanmayın" in x for x in u)
    _, u = cizelge.dogrula(taslak(("normal", [("08:20", "09:00"), ("09:25", "10:05")])))
    assert u == ["Normal: 1. dersten sonraki 25 dakikalık ara öğle arası sayılacak."]


# 7
def test_numarala_satir_sirasindan_bagimsiz_baslangica_gore():
    t = taslak(("normal", [("10:00", "10:40"), ("08:20", "09:00"), ("09:10", "09:50")]))
    assert [d[2:] for d in cizelge.numarala(t)] == [(1, "08:20", "09:00"), (2, "09:10", "09:50"), (3, "10:00", "10:40")]
    t["devreler"][0]["satirlar"][1]["sil"] = True
    assert [d[2] for d in cizelge.numarala(t)] == [1, 2] and cizelge.numarala(t)[0][3] == "09:10"


# 8
def test_bos_satirlar_yok_sayilir_tek_alan_dolu_satir_hata():
    form = {"ad": "Normal gün", "devre": ["normal"], "satir": ["r0", "r1", "r2", "r9x"],
            "r0_devre": "normal", "r0_bas": "08:20", "r0_bit": "09:00",
            "r1_devre": "normal", "r1_bas": "", "r1_bit": "",
            "r2_devre": "normal", "r2_bas": "09:10", "r2_bit": "",
            "r9x_devre": "normal", "r9x_bas": "11:00", "r9x_bit": "11:40"}  # fmt: skip
    t = cizelge.taslak_formdan(form)
    # tanınmayan kimlik yok sayılır; tamamen boş satır taslağa girmez (yeniden çizimde boş satırlar birikmesin)
    assert [s["r"] for s in t["devreler"][0]["satirlar"]] == ["r0", "r2"]
    h, _ = cizelge.dogrula(t)
    assert metinler(h) == ["Normal: 2. satırda başlangıç ve bitiş birlikte girilmeli."] and h[0]["alan"] == "r2_bit"
    form["r2_bit"] = "09:50"
    assert len(cizelge.numarala(cizelge.taslak_formdan(form))) == 2


# 9
def test_araliklar_20_dk_esigi_teneffus_ogle_arasi():
    a = cizelge.araliklar([(1, "08:20", "09:00"), (2, "09:20", "10:00"), (3, "10:21", "11:00"), (4, "11:00", "11:40")])
    assert [(x["tur"], x["dk"]) for x in a] == [("ders", 40), ("teneffus", 20), ("ders", 40), ("ogle", 21), ("ders", 39),
                                                ("ders", 40)]  # fmt: skip
    assert cizelge.ara_metni(10) == "Teneffüs 10 dk" and cizelge.ara_metni(45) == "Öğle arası 45 dk"
    assert cizelge.ara_metni(None) == "—" and cizelge.ara_metni(0) == "Ara yok"


# 10
def test_gunlere_bol_ayni_imzali_gunler_tek_cizelge_ve_ad():
    pzt = [("normal", "Normal", 1, "08:20", "09:00"), ("normal", "Normal", 2, "09:10", "09:50")]
    satirlar = [(g, *d) for g in (0, 1, 2, 3) for d in pzt] + [(4, "normal", "Normal", 1, "08:20", "08:50")]
    gruplar = cizelge.gunlere_bol(satirlar)
    assert [g for g, _ in gruplar] == [[0, 1, 2, 3], [4]]
    assert cizelge.gun_araligi([0, 1, 2, 3]) == "Pzt–Per" and cizelge.gun_araligi([5, 6]) == "Cmt, Paz"
    assert cizelge.gun_araligi([0, 2, 4]) == "Pzt, Çar, Cum" and cizelge.gun_araligi([0, 1, 2, 4]) == "Pzt–Çar, Cum"


# 11
def test_plan_yerel_cizelge_haftaligi_ve_okulzili_kuralini_gecer_tatili_gecmez():
    saatler = [(0, "normal", "Normal", 1, "08:20", "09:00"), (3, "normal", "Normal", 1, "08:20", "09:00")]
    yerel = {"ad": "Kısa gün", "dersler": [("normal", "Normal", 1, "08:30", "09:00"), ("normal", "Normal", 2, "09:05", "09:35")],
             "ders_yok": False}  # fmt: skip
    takvim = {"ogretim": {"bas": "2026-09-07", "bit": "2027-06-25", "donemler": [], "aralar": []}, "resmi_tatiller": True,
              "kurallar": [{"ad": "Kısaltılmış", "tur": "kisaltilmis_gun", "bas": "2026-11-16", "bit": "2026-11-16",
                            "dersler": [["normal", 1, "08:20", "08:50"]]},
                           {"ad": "Okul tatili", "tur": "tatil", "bas": "2026-11-19", "bit": "2026-11-19"}]}  # fmt: skip
    plan = program.plan_hesapla(date(2026, 11, 16), saatler, takvim, yerel)
    assert [d[3].strftime("%H:%M") for d in plan["dersler"]] == ["08:30", "09:05"]
    assert plan["kaynak"] == "Kısa gün (tarihe özel çizelge)" and plan["program_gunu"] == 0
    assert program.plan_hesapla(date(2026, 11, 16), saatler, takvim)["kaynak"] == "Kısaltılmış (kısaltılmış gün)"
    tatil = program.plan_hesapla(date(2026, 11, 19), saatler, takvim, yerel)  # Okul Zili tatil kuralı üstte
    assert tatil["tatil"] == "Okul tatili" and tatil["dersler"] == []
    resmi = program.plan_hesapla(date(2026, 10, 29), saatler, takvim, yerel)  # takvim tatili üstte
    assert resmi["tatil"] == "Cumhuriyet Bayramı" and resmi["dersler"] == []


# 12
def test_plan_yerel_ders_yok_tatil_sayilir():
    saatler = [(0, "normal", "Normal", 1, "08:20", "09:00")]
    plan = program.plan_hesapla(date(2026, 11, 16), saatler, None, {"ad": "Okul gezisi", "dersler": [], "ders_yok": True})
    assert plan["tatil"] == "Okul gezisi" and plan["dersler"] == [] and "tarihe özel" in plan["kaynak"]


# 13
def test_csv_dis_ic_gidis_donus_ayni_taslak():
    t = cizelge.varsayilan_taslak("İkili", "ikili")
    dersler = cizelge.numarala(t)
    bayt = cizelge.csv_yaz(dersler)
    assert bayt.startswith(b"\xef\xbb\xbfdevre;ders;baslangic;bitis\r\n")
    devreler, hatalar = cizelge.csv_oku(bayt, {"sabah": "Sabah", "ogle": "Öğleden sonra"})
    assert hatalar == []
    assert cizelge.numarala({"ad": "x", "devreler": devreler}) == dersler
    # başlık eşanlamlısı ve Türkçe yazım; ders sütunu yok sayılır
    devreler, _ = cizelge.csv_oku("Oturum;Başlangıç;Bitiş\nNormal;08:20;09:00\n".encode(), {})
    assert cizelge.numarala({"ad": "x", "devreler": devreler}) == [("normal", "Normal", 1, "08:20", "09:00")]


# 14
def test_csv_tanınmayan_devre_satir_hatasi():
    _, hatalar = cizelge.csv_oku("devre;baslangic;bitis\nAkşamcı;18:00;18:40\nNormal;8:2;09:00\n".encode(), {})
    assert hatalar == ["2. satır: devre 'Akşamcı' tanınmıyor (Normal, Sabah, Öğleden sonra).",
                       "3. satır: saat SS:DD biçiminde olmalı (ör. 08:20)."]  # fmt: skip
    with pytest.raises(ValueError, match="sütunlar yok"):
        cizelge.csv_oku(b"devre;ders\nNormal;1\n", {})
    # çizelgedeki özel (taşınmış) devre adı tanınır
    devreler, hatalar = cizelge.csv_oku(b"devre;baslangic;bitis\n2. devre;13:00;13:40\n", {"2_devre": "2. devre"})
    assert not hatalar and devreler[0]["devre"] == "2_devre"


# 15
def test_zaman_cizgisi_olcek_ve_cakisma_dilimi():
    z = cizelge.zaman_cizgisi([("Sabah", [(1, "08:00", "09:00"), (2, "09:10", "10:00")]), ("Öğleden sonra", [(1, "09:40", "10:00")])])
    assert z["genislik"] == 1000 and z["yukseklik"] == 28 * 2 + 24 and (z["bas"], z["bit"]) == ("08:00", "10:00")
    sabah = z["seritler"][0]
    assert sabah["dersler"][0] == {"x": 0, "w": 500, "no": 1, "bas": "08:00", "bit": "09:00"}
    assert sabah["aralar"][0]["tur"] == "teneffus" and sabah["aralar"][0]["x"] == 500
    assert [t["metin"] for t in z["saatler"]] == ["08:00", "09:00", "10:00"] and z["saatler"][1]["x"] == 500
    assert z["cakismalar"] == [{"x": 833, "w": 167}]
    assert z["cakisma_metinleri"] == ["Sabah ve Öğleden sonra 09:40–10:00 arasında çakışıyor"]
    assert z["listeler"][0]["satirlar"] == ["08:00–09:00 · 1. ders", "09:00–09:10 · Teneffüs (10 dk)", "09:10–10:00 · 2. ders"]
    assert cizelge.zaman_cizgisi([])["bos"] is True


# ---- göç ve ilk taşıma ------------------------------------------------------------------------------
def eski_veritabani(tmp_path, ders_saati: list[tuple], tahta_ders: list[tuple] = ()):
    """0.8.0/0.9.0 şemasıyla (7 göç) doldurulmuş veritabanı."""
    from tahta_sunucu import vt

    b = sqlite3.connect(tmp_path / "tahta-kontrol.db")
    for sira in range(7):
        b.executescript(vt.GOCLER[sira])
    b.execute("PRAGMA user_version = 7")
    b.execute("INSERT INTO tahta (ad, anahtar_ozet, kayit_zamani, durum) VALUES ('10-A dersliği', 'x', 1, 'onayli')")
    b.executemany("INSERT INTO ders_saati VALUES (?, ?, ?, ?, ?, ?)", ders_saati)
    b.executemany("INSERT INTO tahta_ders VALUES (?, ?, ?, ?, ?)", tahta_ders)
    b.execute("INSERT INTO ayar VALUES ('zil_kaynagi', ?)", ('{"tur": "elle"}',))
    b.commit()
    b.close()


def ikili_cuma_farkli() -> list[tuple]:
    satirlar = []
    for g in range(4):
        satirlar += [(g, "sabah", "Sabah", n, f"{7 + n:02d}:00", f"{7 + n:02d}:40") for n in range(1, 7)]
        satirlar += [(g, "ogle", "Öğleden sonra", n, f"{12 + n:02d}:30", f"{13 + n:02d}:10") for n in range(1, 7)]
    satirlar += [(4, "sabah", "Sabah", n, f"{7 + n:02d}:00", f"{7 + n:02d}:40") for n in range(1, 7)]
    satirlar += [(4, "ogle", "Öğleden sonra", n, f"{12 + n:02d}:30", f"{13 + n:02d}:10") for n in range(1, 6)]
    satirlar += [(5, "sabah", "Sabah", n, f"{8 + n:02d}:00", f"{8 + n:02d}:30") for n in range(1, 4)]
    return satirlar


# 16
def test_goc_ders_saati_cizelgelere_tasinir_ders_saati_ayni_kalir(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    from tahta_sunucu import vt

    satirlar = ikili_cuma_farkli()
    program_ = [(1, 0, "sabah", 1, "9/A"), (1, 4, "ogle", 5, "11/C")]
    eski_veritabani(tmp_path, satirlar, program_)
    with vt.islem() as b:
        once = sorted(tuple(s) for s in b.execute("SELECT * FROM ders_saati"))
    vt.hazirla()
    with vt.islem() as b:
        assert b.execute("PRAGMA user_version").fetchone()[0] == len(vt.GOCLER) >= 9
        assert sorted(tuple(s) for s in b.execute("SELECT * FROM ders_saati")) == once
        assert sorted(tuple(s) for s in b.execute("SELECT * FROM tahta_ders")) == sorted(program_)
        cizelgeler = b.execute("SELECT * FROM zil_cizelgesi ORDER BY id").fetchall()
        assert [c["ad"] for c in cizelgeler] == ["Ders saatleri · Pzt–Per", "Ders saatleri · Cum", "Ders saatleri · Cmt"]
        assert {c["kaynak"] for c in cizelgeler} == {"elle"} and {c["olusturan"] for c in cizelgeler} == {"sistem"}
        assert cizelge.haftalik_oku(b) == {0: 1, 1: 1, 2: 1, 3: 1, 4: 2, 5: 3}
        assert vt.ayar_al(b, "zil_tasima_bekliyor") is None
        kayit = b.execute("SELECT * FROM kayit WHERE islem = 'Zil saatleri çizelgelere taşındı'").fetchall()
        assert len(kayit) == 1 and kayit[0]["ayrinti"] == "3 çizelge · 6 gün"
        # yeniden yazınca da aynı (türetilmiş tablo)
        cizelge.haftalik_yaz(b)
        assert sorted(tuple(s) for s in b.execute("SELECT * FROM ders_saati")) == once
    assert len(list((tmp_path / "goc-oncesi").glob("tahta-kontrol-v7-*.db"))) == 1


# 17
def test_tasima_yarida_kalirsa_yeniden_calisir_ve_bir_kez_yapar(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    from tahta_sunucu import vt

    eski_veritabani(tmp_path, ikili_cuma_farkli())
    asil = cizelge.cizelge_ekle
    sayac = {"n": 0}

    def bozuk(*a, **k):
        sayac["n"] += 1
        if sayac["n"] == 2:
            raise RuntimeError("elektrik kesildi")
        return asil(*a, **k)

    monkeypatch.setattr(cizelge, "cizelge_ekle", bozuk)
    with pytest.raises(RuntimeError):
        vt.hazirla()
    with vt.islem() as b:
        assert b.execute("SELECT COUNT(*) FROM zil_cizelgesi").fetchone()[0] == 0  # yarım iş geri alındı
        assert vt.ayar_al(b, "zil_tasima_bekliyor") is True
    monkeypatch.setattr(cizelge, "cizelge_ekle", asil)
    vt.hazirla()
    vt.hazirla()
    with vt.islem() as b:
        assert b.execute("SELECT COUNT(*) FROM zil_cizelgesi").fetchone()[0] == 3
        assert b.execute("SELECT COUNT(*) FROM kayit WHERE islem = 'Zil saatleri çizelgelere taşındı'").fetchone()[0] == 1


# 18
def test_bos_veritabaninda_tasima_bayragi_yazilmaz(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    from tahta_sunucu import vt

    eski_veritabani(tmp_path, [])  # 0.9.0 veritabanı, ders saati yok
    vt.hazirla()
    with vt.islem() as b:
        assert vt.ayar_al(b, "zil_tasima_bekliyor") is None
        assert b.execute("SELECT COUNT(*) FROM zil_cizelgesi").fetchone()[0] == 0
        assert b.execute("SELECT COUNT(*) FROM kayit WHERE islem LIKE 'Zil saatleri%'").fetchone()[0] == 0
