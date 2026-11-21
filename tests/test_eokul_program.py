"""0.12.0 — ders programı içe aktarmanın beşinci kaynağı: e-Okul "Haftalık Ders Programları" raporu (OOK11002_R01).

Depoya ikili .XLS konmaz ve gerçek rapor KULLANILMAZ: ayrıştırıcı satır matrisi alan saf işlevdir; testler rapor
yerleşimini (gün başlığı satırı, art arda şube blokları, altbilgi) UYDURMA verilerle kurar. Uç testlerinde
`eokul_program.matris_oku` yerine bu matris verilir; .XLS okuma yolu (xlrd) bozuk OLE2 ile ayrıca sınanır.
Öğretmen adları uydurmadır ("Öğretmen Bir", "Kişi Sahte"); hiçbir çıktıda, kayıtta, veritabanında geçmediği doğrulanır.
"""

from __future__ import annotations

import json

import pytest
from test_program_panel import durum
from yardimci import SAHTE_TC, gir, ileti, kimlik, kullanici_ekle, kur_ve_gir, sorgu, tahta_ekle, zil_kur

from tahta_sunucu import eokul, eokul_program, program_aktar, vt

OGRETMENLER = ("Öğretmen Bir", "Kişi Sahte", "Uydurma Üç")
SABAH = ["08:00-08:35", "08:45-09:20", "09:30-10:05", "10:15-10:50"]
OGLE = ["13:30-14:05", "14:15-14:50", "15:00-15:35", "15:45-16:20"]
SUTUN = {0: 2, 1: 6, 2: 10, 3: 14, 4: 18}
GUN_BASLIGI = ["PAZARTESİ", "SALI", "ÇARSAMBA", "PERŞEMBE", "CUMA"]  # e-Okul'daki Ş'siz yazım dahil


def hucre_varsayilan(gun: int, no: int) -> str:
    if (gun, no) == (4, 4):
        return ""  # Cuma 4. ders boş
    if (gun, no) == (1, 2):
        return "SEÇMELİ DERS\nKişi Sahte - SEÇMELİ TARİH"
    if (gun, no) == (2, 3):
        return "BEDEN EĞİTİMİ"  # tek satırlı hücre
    return f"{'MATEMATİK' if no % 2 else 'FİZİK'}\nÖğretmen Bir, Uydurma Üç"


def rapor_matrisi(bloklar, altbilgi: bool = True, no_bicimi=str) -> list[list[str]]:
    """bloklar: [(saatler, hücre işlevi)]. Satır 0 gün başlıkları, sonra bloklar, sonda iki altbilgi satırı."""
    m = [[""] * 22]
    for gun, sutun in SUTUN.items():
        m[0][sutun] = GUN_BASLIGI[gun]
    for saatler, hucre in bloklar:
        for no, saat in enumerate(saatler, start=1):
            satir = [""] * 22
            satir[0], satir[1] = no_bicimi(no), saat
            for gun, sutun in SUTUN.items():
                satir[sutun] = hucre(gun, no)
            m.append(satir)
    if altbilgi:
        m.append([""] * 9 + ["Rapor tarihi 16.11.2026"] + [""] * 12)
        m.append([""] * 17 + ["Müdür Yardımcısı", "", "Uydurma Üç", "", "Okul Müdürü"])
    return m


UC_BLOK = [(OGLE, hucre_varsayilan), (OGLE, lambda g, n: "" if n == 1 else hucre_varsayilan(g, n)), (SABAH, hucre_varsayilan)]


def oku(bloklar=UC_BLOK, **ek) -> dict:
    return eokul_program.rapor_oku(rapor_matrisi(bloklar, **ek))


# ---- ayrıştırma ---------------------------------------------------------------------------------------------
def test_bloklar_gunler_bos_hucre_altbilgi_ve_tek_satirli_hucre():
    r = oku(no_bicimi=lambda n: f"{n}.0")  # xlrd sayıyı "1.0" de verebilir
    assert [b["no"] for b in r["bloklar"]] == [1, 2, 3]
    assert r["gunler"] == [0, 1, 2, 3, 4]  # ÇARSAMBA (Ş'siz) Çarşamba sayıldı
    assert r["atlanan_satir"] == 2 and r["hata_sayisi"] == 0
    b1, b2, b3 = r["bloklar"]
    assert b1["dersler"][0] == [1, "13:30", "14:05"] and b3["dersler"][-1] == [4, "10:15", "10:50"]
    assert [4, 4] not in b1["dolu"] and b1["bos"] == 1 and len(b1["dolu"]) == 19  # boş hücre = ders yok
    assert [2, 3] in b1["dolu"]  # tek satırlı hücre de dolu sayılır
    assert len(b2["dolu"]) == 14 and b2["bos"] == 6
    assert r["dolu_sayisi"] == 19 + 14 + 19 and r["bos_sayisi"] == 1 + 6 + 1


def test_ders_no_bire_donunce_yeni_blok_ve_bozuk_saat_hata_satiri():
    m = rapor_matrisi([(SABAH, hucre_varsayilan)], altbilgi=False)
    m[2][1] = "08:45 08:50"  # okunamayan saat
    m.append(["1", "13:30-14:05"] + [""] * 20)
    r = eokul_program.rapor_oku(m)
    assert len(r["bloklar"]) == 2 and r["hata_sayisi"] == 1 and "saat aralığı okunamadı" in r["hatalar"][0]
    assert [d[0] for d in r["bloklar"][0]["dersler"]] == [1, 3, 4]


def test_gun_basligi_yoksa_ve_ders_satiri_yoksa_reddedilir():
    with pytest.raises(ValueError, match="gün başlıkları bulunamadı"):
        eokul_program.rapor_oku([["Ad", "Soyad"], ["1", "x"]])
    with pytest.raises(ValueError, match="ders saati satırı bulunamadı"):
        eokul_program.rapor_oku(rapor_matrisi([]))


def test_ogretmen_adi_saklanmaz_ipucu_yalniz_ilk_satir_tek_satirli_hucreden_ipucu_yok():
    r = oku()
    duz = json.dumps(r, ensure_ascii=False)
    for ad in OGRETMENLER:
        assert ad not in duz
    assert "SEÇMELİ TARİH" not in duz  # seçmelinin ikinci satırı (öğretmen - ders) hiç alınmaz
    assert r["bloklar"][0]["ipucu"] == ["Pzt 1: MATEMATİK", "Sal 1: MATEMATİK", "Çar 1: MATEMATİK"]
    assert len(r["bloklar"][0]["ipucu"]) == eokul_program.IPUCU_SAYISI
    tek = eokul_program.rapor_oku(rapor_matrisi([(SABAH, lambda g, n: "BEDEN EĞİTİMİ" if n == 1 else "")]))
    assert tek["bloklar"][0]["ipucu"] == [] and len(tek["bloklar"][0]["dolu"]) == 5
    secmeli = eokul_program.rapor_oku(rapor_matrisi([(SABAH, lambda g, n: hucre_varsayilan(1, 2) if g == 1 else "")]))
    assert secmeli["bloklar"][0]["ipucu"][0] == "Sal 1: SEÇMELİ DERS"


def test_tc_kimlik_benzeri_hucre_reddedilir_ve_dosya_bicimleri():
    m = rapor_matrisi(UC_BLOK)
    m[3][6] = f"FİZİK\n{SAHTE_TC}"
    with pytest.raises(ValueError, match="kimlik numarasına benzeyen"):
        eokul_program.rapor_oku(m)
    with pytest.raises(ValueError, match="PDF okunmaz"):
        eokul_program.matris_oku(b"%PDF-1.7\n...")
    with pytest.raises(ValueError, match="Excel 97-2003"):  # xlrd hatası Türkçe iletiye döner (500 değil)
        eokul_program.matris_oku(eokul.OLE2 + b"\x00" * 600)
    with pytest.raises(ValueError, match="Excel"):
        eokul_program.matris_oku(b"sube;gun\n9/A;1\n")
    with pytest.raises(ValueError, match="en çok 2 MB"):
        eokul_program.matris_oku(eokul.OLE2 + b"\x00" * eokul_program.EN_COK_BAYT)


# ---- devreler ve zil çizelgesi ----------------------------------------------------------------------------------
def zil_satirlari_(devre: str, adi: str, saatler, gunler=range(5), kayma: int = 0):
    from tahta_sunucu import program

    satirlar = []
    for g in gunler:
        for no, s in enumerate(saatler, start=1):
            bas, bit = s.split("-")
            satirlar.append((g, devre, adi, no, program.saat_metni(program.dk(bas) + kayma), bit))
    return satirlar


def test_ikili_egitim_devre_gruplari_esleme_ve_zil_onerisi():
    r = oku()
    gruplar = eokul_program.devre_gruplari(r["bloklar"])
    assert [(g["bas"], g["bit"], g["bloklar"]) for g in gruplar] == [("08:00", "10:50", [3]), ("13:30", "16:20", [1, 2])]
    saatler = zil_satirlari_("sabah", "Sabah", SABAH, kayma=3) + zil_satirlari_("ogle", "Öğleden sonra", OGLE)
    esle = eokul_program.devre_esle(gruplar, saatler)
    assert esle["g1"]["devre"] == "sabah" and esle["g1"]["farkli"] == 0  # 3 dk fark ±5 içinde
    assert esle["g2"]["devre"] == "ogle"
    assert eokul_program.devre_esle(gruplar, zil_satirlari_("normal", "Normal", SABAH, kayma=20))["g1"]["devre"] is None
    oneri = eokul_program.zil_onerisi(gruplar, [0, 1, 2, 3, 4])
    assert [(d["ad"], d["sayi"], d["aralik"]) for d in oneri["devreler"]] == [("Sabah", 4, "08:00–10:50"),
                                                                             ("Öğleden sonra", 4, "13:30–16:20")]  # fmt: skip
    assert oneri["hatalar"] == [] and oneri["gun_metni"] == "Pzt–Cum"
    tek = eokul_program.zil_onerisi(eokul_program.devre_gruplari(oku([(SABAH, hucre_varsayilan)])["bloklar"]), [0])
    assert tek["dersler"][0][:2] == ("normal", "Normal")


def test_ikiden_cok_devre_grubunda_oneri_yok_ve_uyari_olmayan_dugmeye_yonlendirmez():
    erken = ["07:50-08:25", "08:35-09:10", "09:20-09:55", "10:05-10:40"]
    r = oku([(SABAH, hucre_varsayilan), (erken, hucre_varsayilan), (OGLE, hucre_varsayilan)])
    h = eokul_program.hazirla(r, [], {}, {}, ["9/A", "9/B", "9/C"])
    assert len(h["gruplar"]) == 3 and h["zil_gerekli"] and h["zil_onerisi"] is None
    assert "3 farklı başlangıç saati var (07:50, 08:00, 13:30)" in h["zil_onerilemez"]
    devresiz = next(u for u in h["uyarilar"] if "hiçbir devreye uymayan" in u)
    assert "rapordan oluşturun" not in devresiz and "zil düzenleyicisinde" in devresiz
    # iki grupta öneri var: uyarı rapordan oluşturmayı söyler, açıklama bandı çıkmaz
    h = eokul_program.hazirla(oku(), [], {}, {}, ["9/A", "9/B", "11/A"])
    assert h["zil_onerilemez"] == "" and any("rapordan oluşturun" in u for u in h["uyarilar"])


def test_zil_uyuyor_yalniz_bazi_dersler_farkli_ve_mevcut_devre_kimligi_korunur():
    saatler = zil_satirlari_("sabah", "Sabah", SABAH[:3] + ["10:30-11:05"]) + zil_satirlari_("ogle", "Öğle", OGLE)
    h = eokul_program.hazirla(oku(), saatler, {}, {}, ["9/A", "9/B", "11/A"])
    assert h["zil_gerekli"] and h["zil_yalniz_fark"] and h["sayilar"]["devresiz"] == 0
    fark = next(u for u in h["uyarilar"] if "5 dakikadan çok" in u)
    assert "(4. ders 10:15)" in fark and "yine programa yazılır" in fark
    # zil çizelgesinde rapordakiyle aynı sayıda devre var: öneri kimlik ve adları korur (program yetim kalmaz)
    assert {(d[0], d[1]) for d in h["zil_onerisi"]["dersler"]} == {("sabah", "Sabah"), ("ogle", "Öğle")}
    assert h["zil_onerisi"]["mevcut_kimlikler"]
    tek = eokul_program.hazirla(oku(), zil_satirlari_("gunduz", "Gündüz", SABAH), {}, {}, ["9/A"])
    assert {d[0] for d in tek["zil_onerisi"]["dersler"]} == {"sabah", "ogle"} and not tek["zil_onerisi"]["mevcut_kimlikler"]


def test_tasinan_sube_hatirlanan_eski_tahtaya_degil_tahta_subelerdeki_yeni_tahtaya_yazilir():
    r = oku()
    saatler = zil_satirlari_("sabah", "Sabah", SABAH) + zil_satirlari_("ogle", "Öğleden sonra", OGLE)
    h = eokul_program.hazirla(r, saatler, {"sube_listesi": ["9/A", "9/B", "11/A"]}, {}, [])
    tahtalar = [{"id": 1, "ad": "Eski", "derslik": "", "subeler": "9/B"}, {"id": 2, "ad": "Yeni", "derslik": "", "subeler": "9/A,11/A"}]
    hatirlanan = {("sube", "9/A"): {"tahta_id": 1, "deger": ""}}  # önceki aktarımda 9/A, 1. tahtadaydı
    cozum = program_aktar.esle(h["girdi"], saatler, tahtalar, hatirlanan, {})
    durum_ = {e["anahtar"]: (e["durum"], e["deger"]) for e in cozum["eslesme"]["sube"]}
    assert durum_["9/A"] == ("otomatik", "2")
    assert {s for (_g, d, _n), s in cozum["satirlar"][1].items() if d == "ogle"} == {"9/B"}
    # tahta.subeler'de yoksa (ya da birden çok tahtada) hatırlanan kullanılır
    tahtalar[1]["subeler"] = "11/A"
    cozum = program_aktar.esle(h["girdi"], saatler, tahtalar, hatirlanan, {})
    assert {e["anahtar"]: e["durum"] for e in cozum["eslesme"]["sube"]}["9/A"] == "hatirlanan"


def test_xls_sayfa_siniri_iletisi_ders_programina_gore(monkeypatch):
    import xlrd

    class Sayfa:
        nrows, ncols = 10, 201

    class Kitap:
        nsheets = 1

        def sheet_by_index(self, _i):
            return Sayfa()

        def release_resources(self):
            pass

    monkeypatch.setattr(xlrd, "open_workbook", lambda **_k: Kitap())
    with pytest.raises(ValueError, match="Haftalık Ders Programları") as hata:
        eokul_program.matris_oku(eokul.OLE2 + b"\x00" * 64)
    assert "öğrenci" not in str(hata.value)
    with pytest.raises(eokul.OkumaHatasi, match="öğrenci satırı"):  # öğrenci listesi aktarımı eski iletiyi korur
        eokul.xls_oku(eokul.OLE2 + b"\x00" * 64)


def test_hazirla_zil_yoksa_bloklar_yazilmaz_ve_oneri_gelir():
    r = oku()
    h = eokul_program.hazirla(r, [], {}, {}, ["9/A", "9/B", "11/A"])
    assert h["zil_gerekli"] and h["zil_onerisi"] and h["girdi"]["ara"] == []
    assert h["sayilar"]["devresiz"] == 3 and any("hiçbir devreye uymayan 3 blok" in u for u in h["uyarilar"])
    bos = oku([(SABAH, hucre_varsayilan), (SABAH, lambda g, n: "")])  # e-Okul'da programı girilmemiş şube
    h = eokul_program.hazirla(bos, zil_satirlari_("normal", "Normal", SABAH), {}, {}, ["9/A", "9/B"])
    assert any(u.startswith("1 blokta hiç ders yok (2. blok)") for u in h["uyarilar"]) and len(h["girdi"]["ara"]) == 19


# ---- şube listesi, sıralama, öneri -----------------------------------------------------------------------------
def test_sube_listesi_pdf_basliklari_ve_farkli_yazimlar():
    ham = "AL -  9. Sınıf / A Şubesi\nAL - 9. Sınıf / İ Şubesi\nHAFTALIK DERS PROGRAMI\n9-b, 10A; 11/ı\t12. Sınıf / Ö Şubesi\n9/A"
    liste, uyarilar = eokul_program.sube_listesi_coz(ham)
    assert liste == ["9/A", "9/İ", "9/B", "10/A", "11/I", "12/Ö"]
    assert any("anlaşılamayan 1 parça" in u for u in uyarilar) and any("iki kez" in u for u in uyarilar)
    assert "HAFTALIK" not in json.dumps(liste)


def test_turk_alfabesi_sirasi_i_ve_i_noktali():
    subeler = ["9/İ", "9/J", "10/A", "9/I", "9/H", "9/Ö", "9/O", "9/Z", "Hazırlık/A", "9/Ç", "9/C"]
    beklenen = ["Hazırlık/A", "9/C", "9/Ç", "9/H", "9/I", "9/İ", "9/J", "9/O", "9/Ö", "9/Z", "10/A"]
    assert sorted(subeler, key=eokul_program.sube_sira_anahtari) == beklenen
    assert sorted(["9/İ", "9/J", "9/I"]) != ["9/I", "9/İ", "9/J"]  # kod noktası sırası yanlış olurdu (İ, Z'den sonra)


def test_sube_onerisi_oncelik_ve_sayi_uyusmazligi_ve_ayni_sube_iki_blokta():
    bloklar = oku()["bloklar"]
    o = eokul_program.blok_subeleri(bloklar, {}, {}, ["9/A", "9/B"])
    assert o["atama"] == {1: "9/A", 2: "9/B", 3: ""} and o["kaynak"] == "sistem" and o["durum"][3] == "eslesmedi"
    assert "Raporda 3 blok var, sistemde kayıtlı 2 şube var" in o["uyarilar"][0]
    o = eokul_program.blok_subeleri(bloklar, {"sube_listesi": ["10/A", "10/B", "12/A"]}, {}, ["9/A", "9/B"])
    assert o["atama"] == {1: "10/A", 2: "10/B", 3: "12/A"} and o["kaynak"] == "liste" and not o["uyarilar"]
    o = eokul_program.blok_subeleri(bloklar, {"sube_listesi": ["10/A", "10/B", "12/A"], "blok": {"2": "", "3": "10/A"}}, {}, [])
    assert o["atama"] == {1: "10/A", 2: "", 3: "10/A"} and o["durum"][2] == "secildi" and o["ciftler"] == {"10/A": [1, 3]}
    hatirlanan = {("blok_sayisi", "-"): {"tahta_id": None, "deger": "3"}, ("blok", "1"): {"tahta_id": None, "deger": "9/C"},
                  ("blok", "2"): {"tahta_id": None, "deger": ""}, ("blok", "3"): {"tahta_id": None, "deger": "11/B"}}  # fmt: skip
    o = eokul_program.blok_subeleri(bloklar, {}, hatirlanan, ["9/A"])
    assert o["atama"] == {1: "9/C", 2: "", 3: "11/B"} and o["kaynak"] == "hatirlanan"
    hatirlanan[("blok_sayisi", "-")]["deger"] = "4"  # blok sayısı değişti: hatırlanan sıra kullanılmaz
    assert eokul_program.blok_subeleri(bloklar, {}, hatirlanan, ["9/A"])["kaynak"] == "sistem"
    assert eokul_program.blok_subeleri(bloklar, {}, {}, [])["uyarilar"][0].startswith("Sistemde kayıtlı şube yok")


# ---- panel uçları ------------------------------------------------------------------------------------------------
@pytest.fixture()
def rapor(monkeypatch):
    """Yüklenen dosya yerine uydurma matris (ikili .XLS üretici yok; gerçek dosya depoya girmez)."""
    durum_ = {"matris": rapor_matrisi(UC_BLOK)}
    monkeypatch.setattr(eokul_program, "matris_oku", lambda bayt: durum_["matris"])
    return durum_


def yukle(panel):
    return panel.post("/program/aktar/eokul", files={"dosya": ("OOK11002_R01.XLS", eokul.OLE2 + b"\x00" * 64, "application/vnd.ms-excel")})


def onizleme_kimligi() -> str:
    with vt.islem() as b:
        return vt.ayar_al(b, "program_onizleme")["kimlik"]


def veritabani_metni() -> str:
    parcalar = []
    with vt.islem() as b:
        for (tablo,) in b.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
            for satir in b.execute(f'SELECT * FROM "{tablo}"').fetchall():
                parcalar.append(json.dumps([str(x) for x in tuple(satir)], ensure_ascii=False))
    return "\n".join(parcalar)


def test_bos_sistemde_rapordan_zil_cizelgesi_ikili_egitim_sube_esleme_ve_onay(uygulama, panel, tahta, saat, rapor):
    kur_ve_gir(panel)
    kaynak = panel.get("/program/aktar").text
    assert "Zil saatleri tanımlı değil" in kaynak and 'action="/program/aktar/eokul"' in kaynak
    # zil yokken e-Okul ve aSc kaynağı (0.21.0: aSc dosyasından da zil çizelgesi önerilir); şablon ve yapay zekâ yok
    assert 'action="/program/aktar/asc"' in kaynak and 'action="/program/aktar/tablo"' not in kaynak
    assert "Haftalık Ders Programları (OOK11002_R01)" in kaynak
    yanit = yukle(panel)
    assert yanit.headers["location"] == "/program/aktar?adim=esleme"
    sayfa = panel.get("/program/aktar?adim=esleme").text
    assert "Bu rapordaki saatlerden zil çizelgesi oluştur" in sayfa and "Uyan devre yok" in sayfa
    assert "Pzt 1: MATEMATİK" in sayfa and 'name="b_3"' in sayfa
    assert "Sistemde kayıtlı şube yok" in sayfa
    # onaysız oluşturulmaz
    assert "onay kutusunu" in ileti(panel.post("/program/aktar/eokul/zil", data={"onizleme": onizleme_kimligi()}))
    yanit = panel.post("/program/aktar/eokul/zil", data={"onizleme": onizleme_kimligi(), "onay": "1"})
    assert "“e-Okul · Pzt–Cum” zil çizelgesi oluşturuldu" in ileti(yanit)
    assert sorgu("SELECT kaynak FROM zil_cizelgesi") == [{"kaynak": "eokul"}]
    assert len(sorgu("SELECT * FROM zil_haftalik")) == 5
    saatler = sorgu("SELECT devre, ders_no, baslangic FROM ders_saati WHERE gun = 0 ORDER BY baslangic")
    assert [(s["devre"], s["baslangic"]) for s in saatler][::4] == [("sabah", "08:00"), ("ogle", "13:30")]
    assert "e-Okul raporundan · Pzt–Cum" in sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Zil çizelgesi oluşturuldu'")[0]["ayrinti"]
    sayfa = panel.get("/program/aktar?adim=esleme").text
    assert "Bu rapordaki saatlerden zil çizelgesi oluştur" not in sayfa and "Öğleden sonra" in sayfa
    # tahtalar: ikili eğitimde T1 sabah 11/A, öğle 9/A taşır; 9/B'nin tahtası yok
    t1 = kimlik(tahta_ekle(panel, tahta, "T1", durum(), subeler="9/A,11/A"))
    t2 = kimlik(tahta_ekle(panel, tahta, "T2", durum()))
    yanit = panel.post("/program/aktar/esle", data={"onizleme": onizleme_kimligi(), "sube_listesi": "AL - 9. Sınıf / A Şubesi\n9/B\n11-A"})
    assert "Şube listesi uygulandı (3 şube, 3 blok)" in ileti(yanit) and yanit.headers["location"].startswith("/program/aktar?adim=esleme")
    sayfa = panel.get("/program/aktar?adim=esleme").text
    assert 'name="b_1" value="9/A"' in sayfa and 'name="b_3" value="11/A"' in sayfa and "Listeden" in sayfa
    assert "Tahtası belli olmayan şubeler (1)" in sayfa and 'name="t_0"' in sayfa  # 9/B
    assert "Tahtası bulunan şubeler (2)" in sayfa  # 9/A ve 11/A (T1) ayrı, kapalı bölümde
    with vt.islem() as b:
        subeler = program_aktar.coz(b, vt.ayar_al(b, "program_onizleme")["veri"])["cozum"]["eslesme"]["sube"]
    n = next(i for i, e in enumerate(subeler) if e["anahtar"] == "9/B")
    yanit = panel.post("/program/aktar/esle", data={"onizleme": onizleme_kimligi(), "sube_listesi": "9/A, 9/B, 11/A",
                                                    "b_1": "9/A", "b_2": "9-b", "b_3": "11/A", f"t_{n}": str(t2)})  # fmt: skip
    assert yanit.headers["location"] == "/program/aktar?adim=onizleme"
    sayfa = panel.get("/program/aktar?adim=onizleme").text
    assert "2 tahtanın programı değişecek · 52 ders saati eklenecek" in sayfa
    assert "yazılacak 52 dolu ders saati · 8 boş ders saati" in sayfa and "9/A: 19 saat" in sayfa
    yanit = panel.post("/program/aktar/onayla", data={"onizleme": onizleme_kimligi()})
    assert "2 tahtanın programı güncellendi" in ileti(yanit)
    t1_satir = sorgu("SELECT gun, devre, ders_no, sube FROM tahta_ders WHERE tahta_id = ?", t1)
    assert {(s["devre"], s["sube"]) for s in t1_satir} == {("sabah", "11/A"), ("ogle", "9/A")} and len(t1_satir) == 38
    assert (4, "ogle", 4) not in {(s["gun"], s["devre"], s["ders_no"]) for s in t1_satir}  # boş hücre yazılmaz
    t2_satir = sorgu("SELECT * FROM tahta_ders WHERE tahta_id = ?", t2)
    assert len(t2_satir) == 14 and {s["sube"] for s in t2_satir} == {"9/B"}
    kayit = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Ders programı içe aktarıldı'")[0]["ayrinti"]
    assert kayit.startswith("e-Okul raporu (OOK11002_R01) · 2 tahta · +52")
    onizlendi = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Ders programı önizlendi'")[0]["ayrinti"]
    assert "3 blok (1. devre 1, 2. devre 2) · 52 dolu, 8 boş ders saati" in onizlendi
    eslesme = {(s["tur"], s["anahtar"]): (s["tahta_id"], s["deger"]) for s in sorgu("SELECT * FROM program_eslesme WHERE kaynak = 'eokul'")}
    assert eslesme[("blok", "2")] == (None, "9/B") and eslesme[("blok_sayisi", "-")] == (None, "3")
    assert eslesme[("sube", "9/B")] == (t2, "")
    assert ("sube", "9/A") not in eslesme  # tahta.subeler'den bulunan hatırlanmaz (kaynak her seferinde tahta.subeler)
    # önizleme silindi; öğretmen adı ve ders adı veritabanının HİÇBİR yerinde yok
    assert sorgu("SELECT * FROM ayar WHERE anahtar = 'program_onizleme' AND deger != 'null'") == []
    dump = veritabani_metni()
    for ad in (*OGRETMENLER, "MATEMATİK", "FİZİK", "SEÇMELİ"):
        assert ad not in dump, ad


def test_ikinci_aktarimda_eslesme_hatirlanir_ve_ogretmen_adi_hicbir_sayfada_yok(uygulama, panel, tahta, saat, rapor):
    kur_ve_gir(panel)
    zil_kur(zil_satirlari_("sabah", "Sabah", SABAH) + zil_satirlari_("ogle", "Öğleden sonra", OGLE))
    t1 = kimlik(tahta_ekle(panel, tahta, "T1", durum(), subeler="9/C,12/A"))
    kimlik(tahta_ekle(panel, tahta, "T2", durum(), subeler="9/D"))
    yukle(panel)
    sayfalar = [panel.get("/program/aktar?adim=esleme").text]
    assert "Bu rapordaki saatlerden zil çizelgesi oluştur" not in sayfalar[0]  # zil uyuyor
    panel.post("/program/aktar/esle", data={"onizleme": onizleme_kimligi(), "b_1": "9/C", "b_2": "9/D", "b_3": "12/A"})
    sayfalar.append(panel.get("/program/aktar?adim=onizleme").text)
    panel.post("/program/aktar/onayla", data={"onizleme": onizleme_kimligi()})
    assert len(sorgu("SELECT * FROM tahta_ders WHERE tahta_id = ?", t1)) == 38
    yukle(panel)
    sayfalar.append(panel.get("/program/aktar?adim=esleme").text)
    assert 'name="b_2" value="9/D"' in sayfalar[-1] and "Hatırlanan" in sayfalar[-1]
    sayfalar.append(panel.get("/program?bolum=derslik").text)
    sayfalar.append(panel.get("/kayit").text)
    for sayfa in sayfalar:
        for ad in OGRETMENLER:
            assert ad not in sayfa, ad
        assert "SEÇMELİ TARİH" not in sayfa


def test_rapordan_zil_onayi_ezilecek_atamalari_ve_yetim_kalacak_programi_once_gosterir(uygulama, panel, tahta, saat, rapor):
    kur_ve_gir(panel)
    # okulun zili tek devre "normal"; Cuma 10 dk kaydırılmış ayrı çizelge; bir tahtada 8 satırlık program
    zil_kur(zil_satirlari_("normal", "Normal", SABAH, gunler=range(4)) + zil_satirlari_("normal", "Normal", SABAH, gunler=[4], kayma=10))
    t1 = kimlik(tahta_ekle(panel, tahta, "T1", durum(), subeler="11/A"))
    with vt.islem() as b:
        b.executemany("INSERT INTO tahta_ders (tahta_id, gun, devre, ders_no, sube) VALUES (?, ?, 'normal', ?, '11/A')",
                      [(t1, g, n) for g in (0, 4) for n in range(1, 5)])  # fmt: skip
        atamalar = sorted({s["cizelge_id"] for s in b.execute("SELECT cizelge_id FROM zil_haftalik")})
    assert len(atamalar) == 2  # Pzt–Per ve Cuma ayrı çizelgeler
    yukle(panel)
    sayfa = panel.get("/program/aktar?adim=esleme").text
    assert "Onaylamadan önce bilin" in sayfa and "Pzt–Per: " in sayfa and " · Cum: " in sayfa
    assert "1 tahtanın 8 ders saatinin yeni çizelgede karşılığı kalmayacak" in sayfa
    assert len(sorgu("SELECT * FROM zil_cizelgesi")) == 2  # yalnız gösterildi, yazılmadı


def test_ayni_sube_iki_bloga_atanirsa_onaylanamaz(uygulama, panel, tahta, saat, rapor):
    kur_ve_gir(panel)
    zil_kur(zil_satirlari_("sabah", "Sabah", SABAH) + zil_satirlari_("ogle", "Öğleden sonra", OGLE))
    kimlik(tahta_ekle(panel, tahta, "T1", durum(), subeler="9/A"))
    yukle(panel)
    panel.post("/program/aktar/esle", data={"onizleme": onizleme_kimligi(), "b_1": "9/A", "b_2": "9/A", "b_3": ""})
    sayfa = panel.get("/program/aktar?adim=onizleme").text
    assert "9/A şubesi 1, 2. bloklara atanmış" in sayfa
    assert 'value="onayla" disabled' in sayfa
    assert "eşlemeyi kontrol edin" in ileti(panel.post("/program/aktar/onayla", data={"onizleme": onizleme_kimligi()}))
    assert sorgu("SELECT * FROM tahta_ders") == []
    sayfa = panel.get("/program/aktar?adim=esleme").text
    assert "İki blokta" in sayfa
    yanit = panel.post("/program/aktar/esle", data={"onizleme": onizleme_kimligi(), "b_1": "x-y"})
    assert "Şube anlaşılamadı (1. blok)" in ileti(yanit)
    panel.post("/program/aktar/esle", data={"onizleme": onizleme_kimligi(), "b_1": ""})  # öneriyi boşaltmak = atla
    sayfa = panel.get("/program/aktar?adim=esleme").text
    assert "Atlanacak" in sayfa and "İki blokta" not in sayfa


def test_tc_benzeri_deger_pdf_bozuk_xls_ve_yetki(uygulama, panel, tahta, saat, rapor):
    kur_ve_gir(panel)
    rapor["matris"] = rapor_matrisi(UC_BLOK)
    rapor["matris"][2][2] = f"KİMYA\n{SAHTE_TC}"
    assert "kimlik numarasına benzeyen" in ileti(yukle(panel))
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Ders programı reddedildi'")[0]["ayrinti"].startswith("e-Okul raporu")
    assert SAHTE_TC not in veritabani_metni()


def test_gercek_okuma_yolu_pdf_ve_bozuk_xls_turkce_ileti(uygulama, panel, tahta, saat):
    kur_ve_gir(panel)
    yanit = panel.post("/program/aktar/eokul", files={"dosya": ("rapor.pdf", b"%PDF-1.4\n%...", "application/pdf")})
    assert "PDF okunmaz" in ileti(yanit)
    yanit = panel.post("/program/aktar/eokul", files={"dosya": ("r.XLS", eokul.OLE2 + b"\x00" * 600, "application/vnd.ms-excel")})
    assert "Excel 97-2003 (.xls) dosyası okunamadı" in ileti(yanit)
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    yanit = panel.post("/program/aktar/eokul", files={"dosya": ("r.XLS", b"x", "application/vnd.ms-excel")})
    assert "yönetici yetkisi" in ileti(yanit)
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yetkisiz işlem reddedildi'")[-1]["ayrinti"] == "Ders programı e-Okul raporu yükleme"
