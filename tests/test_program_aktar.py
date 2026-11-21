"""0.10.0 — ders programını içe aktarma: aSc XML (uydurma, testte üretilir), şablon CSV/XLSX, yapay zekâ çıktısı,
eşleme, önizleme farkı, kapsamlı onay, hatırlanan eşlemeler, geri yükleme, yetkiler.

Örnek veriler UYDURMADIR: derslikler Z-04, Z-05, Fizik Lab, Spor Salonu; sınıflar 9-A, 9A Şubesi, 10/B, Hazırlık A;
öğretmenler Ö1, Ö2 (çıktıda hiç geçmediği ayrıca doğrulanır). Saat `saat` fikstürüyle sabittir (pazartesi 16.11.2026).
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from test_program_panel import ELLE, durum
from yardimci import (
    SAHTE_TC,
    gir,
    ileti,
    kimlik,
    kullanici_ekle,
    kur_ve_gir,
    sorgu,
    tahta_ekle,
    zil_elle,
    zil_kur,
    zil_satirlari,
)

from tahta_sunucu import metin, program, program_aktar, vt

SAATLER = zil_satirlari(ELLE)  # Pzt–Cum, 8 ders: 08:20, 09:10, 10:00, 10:50, 12:15, 13:05, 13:55, 14:45
BASLAR = ["08:20", "09:10", "10:00", "10:50", "12:15", "13:05", "13:55", "14:45"]
GUNLER_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma"]


def gun_maskesi(gun: int, uzunluk: int = 5) -> str:
    return "".join("1" if i == gun else "0" for i in range(uzunluk))


def asc_xml(kartlar, dersler, *, siniflar=None, gruplar="", donemler=None, gun_adlari=GUNLER_TR, displayname="aSc Timetables 2012 XML",
            ek="", kok="timetable", kodlama="UTF-8") -> bytes:  # fmt: skip
    """kartlar: [(lessonid, gun, period, classroomids, weeks, terms)]; dersler: [(id, classids, classroomids, ppw, ppc, groupids)]."""
    siniflar = siniflar if siniflar is not None else [("c1", "9-A", "9-A", ""), ("c2", "9A Şubesi", "", ""), ("c3", "10/B", "", "r2"),
                                                       ("c4", "Hazırlık A", "", "")]  # fmt: skip
    donemler = donemler or [("t1", "Bütün yıl", "1")]
    p = [f'<period period="{i + 1}" name="{i + 1}" short="{i + 1}" starttime="{b}" endtime="{program.saat_metni(program.dk(b) + 40)}"/>'
         for i, b in enumerate(BASLAR)]  # fmt: skip
    p.append('<period period="0" name="0" short="0" starttime="07:30" endtime="08:10"/>')
    gunler = [f'<daysdef id="d{i}" name="{ad}" short="{ad[:3]}" days="{gun_maskesi(i)}"/>' for i, ad in enumerate(gun_adlari)]
    donem_xml = "".join(f'<termsdef id="{i}" name="{a}" terms="{m}"/>' for i, a, m in donemler)
    sinif_xml = "".join(f'<class id="{i}" name="{n}" short="{s}" classroomids="{r}" teacherid="o1"/>' for i, n, s, r in siniflar)
    gunler.append('<daysdef id="dx" name="Her gün" short="X" days="10000,01000,00100,00010,00001"/>')
    xml = (
        f'<?xml version="1.0" encoding="{kodlama}"?>\n<{kok} importtype="database" displayname="{displayname}">'
        f"<periods>{''.join(p)}</periods><daysdefs>{''.join(gunler)}</daysdefs>"
        '<weeksdefs><weeksdef id="w1" name="Her hafta" weeks="1"/></weeksdefs>'
        f"<termsdefs>{donem_xml}</termsdefs>"
        '<subjects><subject id="s1" name="Matematik" short="MAT"/></subjects>'
        '<teachers><teacher id="o1" name="Ö1" short="Ö1"/><teacher id="o2" name="Ö2" short="Ö2"/></teachers>'
        '<classrooms><classroom id="r1" name="Z-04" short="Z04"/><classroom id="r2" name="Z-05" short="Z05"/>'
        '<classroom id="r3" name="Fizik Lab" short="FL"/><classroom id="r4" name="Spor Salonu" short="SS"/></classrooms>'
        f"<classes>{sinif_xml}</classes>"
        f"<groups>{gruplar}</groups>"
        "<lessons>" + "".join(
            f'<lesson id="{i}" classids="{c}" groupids="{g}" subjectid="s1" teacherids="o1,o2" classroomids="{r}" '
            f'periodsperweek="{ppw}" periodspercard="{ppc}" weeksdefid="w1" termsdefid="t1"/>'
            for i, c, r, ppw, ppc, g in dersler
        ) + "</lessons><cards>" + "".join(
            f'<card lessonid="{l_}" classroomids="{r}" period="{p_}" days="{gun_maskesi(g) if isinstance(g, int) else g}" '
            f'weeks="{w}" terms="{t}"/>'
            for l_, g, p_, r, w, t in kartlar
        ) + f"</cards>{ek}</{kok}>"
    )  # fmt: skip
    return xml.encode("utf-8" if kodlama.upper() == "UTF-8" else "cp1254")


def kart(ders, gun, period, oda="", weeks="1", terms=""):
    return (ders, gun, str(period), oda, weeks, terms)


TEMEL_DERSLER = [("L1", "c1", "", "3", "1", ""), ("L2", "c3", "", "2", "1", ""), ("L3", "c4", "r3", "1", "1", ""),
                 ("L4", "c1,c2", "", "1", "1", "")]  # fmt: skip
TEMEL_KARTLAR = [kart("L1", 0, 1, "r1"), kart("L1", 0, 2, "r1"), kart("L1", 1, 3, "r1"),  # 9-A Z-04'te
                 kart("L2", 0, 1), kart("L2", 2, 4),                                      # 10/B: sınıfın dersliği (Z-05)
                 kart("L3", 4, 5),                                                        # Hazırlık A: dersin tek dersliği Fizik Lab
                 kart("L4", 3, 6, "r1")] * 2  # fmt: skip
TEMEL_KARTLAR = TEMEL_KARTLAR[:7] + [kart("L1", 2, 7, "r1"), kart("L1", 2, 8, "r1"), kart("L2", 3, 1), kart("L2", 3, 2), kart("L3", 4, 6)]


def ara(asc_bayt, secimler=None):
    return program_aktar.asc_ara(program_aktar.asc_oku(asc_bayt), secimler or {})


def tahtalar():
    return [{"id": 1, "ad": "Z-04 tahtası", "derslik": "Z-04", "subeler": "9/A"},
            {"id": 2, "ad": "Z-05", "derslik": "", "subeler": "10/B"},
            {"id": 3, "ad": "Fizik Lab", "derslik": "Fizik Lab", "subeler": ""}]  # fmt: skip


def esle_asc(asc_bayt, secimler=None, saatler=SAATLER, tahta=None, hatirlanan=None):
    secimler = secimler or {}
    okunan = ara(asc_bayt, secimler)
    return okunan, program_aktar.esle({"kaynak": "asc", "ara": okunan["ara"], "bilgi": okunan["bilgi"]}, saatler,
                                      tahta or tahtalar(), hatirlanan or {}, secimler)  # fmt: skip


# ---- aSc ayrıştırma ve çözüm (saf) ----------------------------------------------------------------------------
# 1
def test_asc_temel_kart_cozumu():
    okunan, cozum = esle_asc(asc_xml(TEMEL_KARTLAR, TEMEL_DERSLER))
    assert okunan["hata_sayisi"] == 0 and okunan["kart_sayisi"] == 12
    z04 = cozum["satirlar"][1]
    assert z04[(0, "normal", 1)] == "9/A" and z04[(0, "normal", 2)] == "9/A" and z04[(1, "normal", 3)] == "9/A"
    assert cozum["satirlar"][2][(0, "normal", 1)] == "10/B"  # (c) sınıfın kendi dersliği Z-05 → tahta adı
    assert cozum["satirlar"][3][(4, "normal", 5)] == "Hazırlık/A"  # (b) dersin tek dersliği
    durumlar = {e["ad"]: e["durum"] for e in cozum["eslesme"]["derslik"]}
    assert durumlar["Z-04 (Z04)"] == "otomatik"
    assert {e["anahtar"].split("|")[0]: e["deger"] for e in cozum["eslesme"]["saat"]}["5"] == "normal|5"


# 2
def test_asc_ogretmen_ve_ders_adi_hic_okunmaz(uygulama, panel):
    kur_ve_gir(panel)
    zil_kur(SAATLER)
    bayt = asc_xml(TEMEL_KARTLAR, TEMEL_DERSLER)
    asc = program_aktar.asc_oku(bayt)
    assert "teachers" not in asc and "subjects" not in asc
    assert all("teacherids" not in d and "subjectid" not in d for d in asc["lessons"].values())
    yanit = panel.post("/program/aktar/asc", files={"dosya": ("p.xml", bayt, "text/xml")})
    assert yanit.headers["location"] == "/program/aktar?adim=esleme"
    with vt.islem() as b:
        onizleme = json.dumps(vt.ayar_al(b, "program_onizleme"), ensure_ascii=False)
    sayfa = panel.get("/program/aktar?adim=onizleme").text
    for yasak in ("Ö1", "Ö2", "Matematik", "MAT"):
        assert yasak not in onizleme and yasak not in sayfa and yasak not in json.dumps(sorgu("SELECT * FROM kayit"), ensure_ascii=False)
    assert program_aktar.ozet(bayt) in onizleme  # yalnız özet; dosya saklanmaz


# 3
def test_asc_gun_adlari_daysdef_ten():
    # gün adları ters sırada verilirse sıra adlardan kurulur
    okunan = ara(asc_xml([kart("L1", 0, 1, "r1")], TEMEL_DERSLER, gun_adlari=list(reversed(GUNLER_TR))))
    assert okunan["ara"][0]["g"] == 4 and not any("varsayıldı" in u for u in okunan["uyarilar"])
    okunan = ara(asc_xml([kart("L1", 1, 1, "r1")], TEMEL_DERSLER, gun_adlari=["Mo", "Tu", "We", "Th", "Fr"]))
    assert okunan["ara"][0]["g"] == 1 and any("Pazartesi'den başlar varsayıldı" in u for u in okunan["uyarilar"])
    okunan = ara(asc_xml([kart("L1", "00000", 1, "r1"), kart("L1", "10100", 2, "r1")], TEMEL_DERSLER))
    assert okunan["hata_sayisi"] == 1 and sorted(y["g"] for y in okunan["ara"]) == [0, 2]
    assert any("birden çok gün" in u for u in okunan["uyarilar"])


# 4
def test_asc_iki_haftalik_kart_her_hafta_dolu_ve_uyari():
    okunan, cozum = esle_asc(asc_xml([kart("L1", 0, 1, "r1", weeks="10"), kart("L1", 0, 2, "r1", weeks="01")], TEMEL_DERSLER))
    assert len(okunan["ara"]) == 2 and set(cozum["satirlar"][1]) == {(0, "normal", 1), (0, "normal", 2)}
    assert any("2 ders iki haftada bir" in u for u in okunan["uyarilar"])


# 5
def test_asc_donem_secimi():
    donemler = [("t1", "1. dönem", "10"), ("t2", "2. dönem", "01"), ("t3", "Bütün yıl", "11")]
    bayt = asc_xml([kart("L1", 0, 1, "r1", terms="10"), kart("L1", 0, 2, "r1", terms="01"), kart("L1", 0, 3, "r1", terms="11")],
                   TEMEL_DERSLER, donemler=donemler)  # fmt: skip
    okunan = ara(bayt)
    assert okunan["donemler"] == [(0, "1. dönem"), (1, "2. dönem")] and okunan["secili_donem"] == 0
    assert sorted(y["p"].split("|")[0] for y in okunan["ara"]) == ["1", "3"]
    okunan = ara(bayt, {"donem": "1"})
    assert sorted(y["p"].split("|")[0] for y in okunan["ara"]) == ["2", "3"]


# 6
def test_asc_blok_ders_genisleme_kart_sayisina_gore():
    # kart başına saat: periodsperweek = kart sayısı (2), periodspercard 2 → tek saat sayılır
    okunan = ara(asc_xml([kart("L1", 0, 1, "r1"), kart("L1", 1, 1, "r1")], [("L1", "c1", "", "2", "2", "")]))
    assert len(okunan["ara"]) == 2
    # blok kart: 2 kart × 2 saat = 4 → her kart iki ardışık saate genişler
    okunan = ara(asc_xml([kart("L1", 0, 1, "r1"), kart("L1", 1, 3, "r1")], [("L1", "c1", "", "4", "2", "")]))
    assert sorted((y["g"], y["p"].split("|")[0]) for y in okunan["ara"]) == [(0, "1"), (0, "2"), (1, "3"), (1, "4")]
    okunan = ara(asc_xml([kart("L1", 0, 1, "r1")], [("L1", "c1", "", "5", "2", "")]))
    assert len(okunan["ara"]) == 1 and any("Blok ders sayısı tutarsız" in u for u in okunan["uyarilar"])


# 7
def test_asc_bolunmus_grup_iki_derslik_ayni_sube():
    gruplar = '<group id="g1" classid="c1" name="Grup 1" entireclass="0" divisiontag="1"/><group id="g2" classid="c1" name="Grup 2"/>'
    dersler = [("L1", "", "", "1", "1", "g1"), ("L2", "", "", "1", "1", "g2")]
    _, cozum = esle_asc(asc_xml([kart("L1", 0, 1, "r1"), kart("L2", 0, 1, "r3")], dersler, gruplar=gruplar))
    assert cozum["satirlar"][1][(0, "normal", 1)] == "9/A" and cozum["satirlar"][3][(0, "normal", 1)] == "9/A"
    assert "Grup 1" not in str(program_aktar.asc_oku(asc_xml([kart("L1", 0, 1, "r1")], dersler, gruplar=gruplar)))  # grup adı okunmaz


# 8
def test_asc_birlesik_ders_ilk_sube_ve_uyari():
    _, cozum = esle_asc(asc_xml([kart("L1", 0, 3, "r1")], [("L1", "c3,c1", "", "1", "1", "")]))
    assert cozum["satirlar"][1][(0, "normal", 3)] == "9/A"  # Türkçe abece sırasındaki ilk şube
    assert "Z-04 (Z04) Pzt 3. ders: 9/A + 10/B birleşik; 9/A yazıldı." in cozum["uyarilar"]


# 9
def test_asc_dersliksiz_ders_sinif_dersligi_ve_subeler_alani_yedegi():
    dersler = [("L1", "c1", "", "1", "1", ""), ("L2", "c4", "", "1", "1", ""), ("L3", "c3", "r1,r2", "1", "1", "")]
    _, cozum = esle_asc(asc_xml([kart("L1", 0, 1), kart("L2", 0, 2), kart("L3", 0, 3)], dersler))
    assert cozum["satirlar"][1][(0, "normal", 1)] == "9/A"  # (d) şubenin tahtası: tahta.subeler
    assert cozum["satirlar"][2][(0, "normal", 3)] == "10/B"  # (b) iki derslik → (c) sınıfın dersliği Z-05
    assert cozum["dersliksiz_sayi"] == 1 and "Hazırlık/A" in cozum["dersliksiz"][0]  # (e) hiçbiri yok
    assert {e["anahtar"]: e["durum"] for e in cozum["eslesme"]["sube"]} == {"9/A": "otomatik", "Hazırlık/A": "eslesmedi"}


# 10
def test_asc_ikili_egitim_saatten_devre_ve_dosya_devresi_secimi():
    sabah = zil_satirlari({**ELLE, "devre_adi": "Sabah", "ilk_ders": "07:00", "ders_sayisi": "6", "ogle_sonra": "0"})
    ogle = zil_satirlari({**ELLE, "devre_adi": "Öğleden sonra", "ilk_ders": "13:00", "ders_sayisi": "6", "ogle_sonra": "0"})
    saatler = sabah + ogle
    bayt = asc_xml([kart("L1", 0, 1, "r1"), kart("L1", 0, 2, "r1")], TEMEL_DERSLER)  # period 1 08:20, 2 09:10: saatler tutmaz
    _, cozum = esle_asc(bayt, saatler=saatler)
    assert cozum["satirlar"] == {} and any("eşlenemedi" in u for u in cozum["uyarilar"])
    assert [(e["anahtar"], e["durum"], e.get("tek")) for e in cozum["eslesme"]["devre"]] == [("tek", "eslesmedi", True)]
    # 0.21.0: eski tek "devre_secimi" sorusu, tek gruplu dosyada grubun devre seçimidir (g_0)
    _, cozum = esle_asc(bayt, {"devre": {"tek": "ogle"}}, saatler=saatler)
    assert set(cozum["satirlar"][1]) == {(0, "ogle", 1), (0, "ogle", 2)}
    # starttime sabah devresinin 2. dersine (08:20) ±5 dk içinde: saatten sabah 2 önerilir
    sabah = zil_satirlari({**ELLE, "devre_adi": "Sabah", "ilk_ders": "07:30", "ders_sayisi": "6", "ogle_sonra": "0"})
    bayt = asc_xml([kart("L1", 0, 1, "r1")], TEMEL_DERSLER)
    _, cozum = esle_asc(bayt, saatler=sabah + ogle)
    assert set(cozum["satirlar"][1]) == {(0, "sabah", 2)}


# 11
def test_asc_cuma_farkli_saat_ve_zilde_olmayan_ders_hata_satiri():
    saatler = [s for s in SAATLER if not (s[0] == 4 and s[3] == 8)]  # Cuma 7 ders
    _, cozum = esle_asc(asc_xml([kart("L1", 4, 8, "r1"), kart("L1", 4, 7, "r1"), kart("L1", 0, "0", "r1")], TEMEL_DERSLER),
                        saatler=saatler)  # fmt: skip
    assert cozum["hata_sayisi"] == 1 and "Cuma 8. ders zil çizelgesinde yok" in cozum["hatalar"][0]
    assert set(cozum["satirlar"][1]) == {(4, "normal", 7)} and cozum["atlanan"] == 1  # period 0 → yok say


# 12
def test_asc_deneme_surumu_10_kart_uyarisi():
    assert any("aSc deneme sürümü" in u for u in program_aktar.asc_oku(asc_xml(TEMEL_KARTLAR[:3], TEMEL_DERSLER))["uyarilar"])
    kartlar = [kart("L1", g % 5, 1 + g // 5, "r1") for g in range(11)]
    assert not any("deneme" in u for u in program_aktar.asc_oku(asc_xml(kartlar, TEMEL_DERSLER))["uyarilar"])


# 13
def test_asc_kok_ogesi_ve_displayname():
    with pytest.raises(ValueError, match="aSc Timetables XML dosyası değil"):
        program_aktar.asc_oku(asc_xml(TEMEL_KARTLAR, TEMEL_DERSLER, kok="ders_programi"))
    uyarilar = program_aktar.asc_oku(asc_xml(TEMEL_KARTLAR, TEMEL_DERSLER, displayname="Baska Program"))["uyarilar"]
    assert any("aSc Timetables'tan gelmiyor olabilir" in u for u in uyarilar)
    cp = program_aktar.asc_oku(asc_xml(TEMEL_KARTLAR, TEMEL_DERSLER, kodlama="windows-1254"))
    assert cp["classes"]["c4"]["name"] == "Hazırlık A"
    with pytest.raises(ValueError, match="güvenli olmayan"):
        program_aktar.asc_oku(b'<?xml version="1.0"?><!DOCTYPE t [<!ENTITY x "y">]><timetable/>')


# 16
def test_asc_sinirlar_oge_derinlik_oznitelik_boyut(monkeypatch):
    with pytest.raises(ValueError, match="beklenenden büyük"):
        program_aktar.asc_oku(asc_xml(TEMEL_KARTLAR, TEMEL_DERSLER, ek="<a><b><c><d><e><f><g><h/></g></f></e></d></c></b></a>"))
    uzun = asc_xml(TEMEL_KARTLAR, [("L1", "c1", "x" * 5000, "1", "1", "")])
    with pytest.raises(ValueError, match="beklenenden büyük"):
        program_aktar.asc_oku(uzun)
    monkeypatch.setattr(program_aktar, "ASC_EN_COK_KART", 5)
    with pytest.raises(ValueError, match="beklenenden büyük"):
        program_aktar.asc_oku(asc_xml(TEMEL_KARTLAR, TEMEL_DERSLER))
    monkeypatch.setattr(program_aktar, "ASC_EN_COK_BAYT", 100)
    with pytest.raises(ValueError, match="en çok"):
        program_aktar.asc_oku(asc_xml(TEMEL_KARTLAR, TEMEL_DERSLER))
    # öğretmen bölümündeki uzun öznitelik okunmadığı için sınır dışıdır (içi atlanır)
    monkeypatch.setattr(program_aktar, "ASC_EN_COK_KART", 30_000)
    monkeypatch.setattr(program_aktar, "ASC_EN_COK_BAYT", 10 * 1024 * 1024)
    program_aktar.asc_oku(asc_xml(TEMEL_KARTLAR, TEMEL_DERSLER).replace(b'name="\xc3\x961"', b'name="' + b"x" * 5000 + b'"'))


# ---- şablon ve yapay zekâ (saf) ------------------------------------------------------------------------------
def tablo(metin_: str, saatler=SAATLER):
    basliklar, satirlar = metin.csv_oku(metin_.encode("utf-8"), 1024 * 1024, 10_000)
    return program_aktar.tablo_oku([basliklar, *satirlar], saatler)


def esle_tablo(okunan, tahta=None, secimler=None):
    return program_aktar.esle({"kaynak": "tablo", "ara": okunan["ara"], "bilgi": okunan["bilgi"]}, SAATLER,
                              tahta or tahtalar(), {}, secimler or {})  # fmt: skip


# 18
def test_tablo_v2_derslik_bos_subenin_tahtasi():
    okunan = tablo("sube;gun;ders;devre;derslik\n9/A;Pazartesi;1-2;;\n10/B;Salı;3;;\n11/C;Salı;4;;\n12/A;Salı;5;;Z-04\n")
    cozum = esle_tablo(okunan, tahta=[*tahtalar(), {"id": 4, "ad": "T-4", "derslik": "", "subeler": "11/C"},
                                      {"id": 5, "ad": "T-5", "derslik": "", "subeler": "11/C"}])  # fmt: skip
    assert set(cozum["satirlar"][1]) == {(0, "normal", 1), (0, "normal", 2), (1, "normal", 5)}
    assert cozum["satirlar"][2] == {(1, "normal", 3): "10/B"}
    sube = {e["anahtar"]: e["durum"] for e in cozum["eslesme"]["sube"]}
    assert sube == {"9/A": "otomatik", "10/B": "otomatik", "11/C": "eslesmedi"}
    cozum = esle_tablo(okunan, secimler={"sube": {"11/C": "3"}})
    assert cozum["satirlar"][3] == {(1, "normal", 4): "11/C"}
    hatali = tablo("sube;gun;ders;derslik\n;Pazartesi;1;\nX1;Salı;1;\n")
    assert hatali["hatalar"] == ["2. satır: şube ve derslik boş.", "3. satır: şube 'X1' anlaşılamadı ve derslik boş."]


# 19
def test_tablo_v1_dosyasi_aynen_okunur():
    """v1 (derslik;gun;ders;devre;sube) program.derslik_csv_oku üzerinden test_program.py'de de doğrulanır."""
    okunan = tablo("derslik;gun;ders;devre;sube\nZ-04;Pzt;1-4;;9/A\nZ-04;Pazartesi;2;;9/B\n")
    cozum = esle_tablo(okunan)
    assert cozum["satirlar"][1] == {(0, "normal", 1): "9/A", (0, "normal", 2): "9/B", (0, "normal", 3): "9/A", (0, "normal", 4): "9/A"}
    assert any("son satır geçerli" in u for u in cozum["uyarilar"])
    with pytest.raises(ValueError, match="sütunlar yok"):
        tablo("gun;ders\nPazartesi;1\n")
    with pytest.raises(ValueError, match="zil saatlerini"):
        tablo("sube;gun;ders\n9/A;Pzt;1\n", saatler=[])


def xlsx_yap(satirlar) -> bytes:
    def hucre(r, c, v):
        return f'<c r="{chr(65 + c)}{r}" t="inlineStr"><is><t>{v}</t></is></c>'

    sayfa = "".join(f'<row r="{r}">' + "".join(hucre(r, c, v) for c, v in enumerate(s)) + "</row>" for r, s in enumerate(satirlar, 1))
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                   'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'
                   '<sheet name="Program" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                   f"<sheetData>{sayfa}</sheetData></worksheet>")
    return tampon.getvalue()


# 20
def test_tablo_xlsx_ve_xls_ilk_baytlardan():
    bicim, matris = program_aktar.tablo_matrisi(xlsx_yap([["sube", "gun", "ders", "derslik"], [], ["9/A", "Salı", "2", "Z-04"]]))
    assert bicim == "xlsx" and program_aktar.tablo_oku(matris, SAATLER)["ara"][0]["g"] == 1
    bicim, _ = program_aktar.tablo_matrisi(b"sube;gun;ders\n9/A;Pzt;1\n")
    assert bicim == "csv"
    with pytest.raises(ValueError):
        program_aktar.tablo_matrisi(program_aktar.OLE2 + b"\x00" * 100)  # bozuk .xls: okunamadı iletisi


# 21
def test_tablo_tc_kimlik_benzeri_hucre_reddedilir():
    with pytest.raises(ValueError, match="kimlik numarasına benzeyen"):
        tablo(f"sube;gun;ders;not\n9/A;Pzt;1;{SAHTE_TC}\n")
    # Başlık satırındaki değer de denetlenir (yok sayılan sütun uyarısına ve önizleme kaydına girmesin).
    with pytest.raises(ValueError, match="kimlik numarasına benzeyen"):
        tablo(f"sube;gun;ders;{SAHTE_TC}\n9/A;Pzt;1;\n")


def test_yz_metni_hatasinda_metin_korunur_ve_hata_kartta_gorunur(uygulama, panel):
    kur_ve_gir(panel)
    zil_elle(ELLE)
    metin_ = "Sınıf;Gün;Saat\n9/A;Pazartesi;1-3"
    yanit = panel.post("/program/aktar/tablo", data={"bicim": "yz", "metin": metin_})
    assert yanit.status_code == 422
    assert 'id="yz-hata"' in yanit.text and 'aria-invalid="true"' in yanit.text
    assert "9/A;Pazartesi;1-3</textarea>" in yanit.text
    # Kimlik numarasına benzeyen değer içeren metin geri yazılmaz (yönlendirme, metin yok)
    yanit = panel.post("/program/aktar/tablo", data={"bicim": "yz", "metin": f"sube;gun;ders\n9/A;Pzt;{SAHTE_TC}"})
    assert yanit.status_code == 303 and SAHTE_TC not in yanit.headers["location"]


# 22
def test_tablo_bilinmeyen_sutun_okunmaz_saklanmaz():
    okunan = tablo("sube;gun;ders;ogretmen;derslik\n9/A;Pzt;1;Uydurma Öğretmen;Z-04\n")
    assert okunan["yok_sayilan"] == ["ogretmen"] and "Uydurma" not in json.dumps(okunan, ensure_ascii=False)


# 23
def test_yz_metni_kod_blogu_ve_aciklama_satirlari_atilir():
    metin_ = ("İşte dönüştürülmüş program:\n```csv\nsube;gun;ders;devre;derslik\n9/A;Pazartesi;1-6;;\n"
              "Umarım yardımcı olur\n10/B;Salı;1-3,5;;Z-04\n```\nBaşka bir şey?\n")  # fmt: skip
    temiz, uyarilar = program_aktar.yz_metni_temizle(metin_)
    assert temiz == "sube;gun;ders;devre;derslik\n9/A;Pazartesi;1-6;;\n10/B;Salı;1-3,5;;Z-04\n"
    assert uyarilar == ["Başlıktan önceki 1 satır (açıklama) atıldı.", "Ayraç içermeyen 2 satır (açıklama) atıldı."]
    with pytest.raises(ValueError, match="başlık"):
        program_aktar.yz_metni_temizle("Program okunamadı.")
    with pytest.raises(ValueError, match="512 KB"):
        program_aktar.yz_metni_temizle("x" * (512 * 1024 + 1))


# 24
def test_istem_metni_tek_ve_iki_devre():
    tek = program_aktar.istem_metni(SAATLER)
    assert "Bu okulda tek devre var; bu sütunu BOŞ bırak." in tek and "9/A;Pazartesi;1-6;;" in tek
    assert "Ders saatleri: 1. ders 08:20-09:00, 2. ders 09:10-09:50" in tek and "Yalnız CSV yaz." in tek
    sabah = zil_satirlari({**ELLE, "devre_adi": "Sabah", "ilk_ders": "07:30", "ders_sayisi": "6", "ogle_sonra": "0"})
    ogle = zil_satirlari({**ELLE, "devre_adi": "Öğleden sonra", "ilk_ders": "13:00", "ders_sayisi": "6", "ogle_sonra": "0"})
    cuma = [s for s in ogle if not (s[0] == 4 and s[3] == 6)]
    iki = program_aktar.istem_metni(sabah + cuma)
    assert 'Sabahçı şubeler için "Sabah", öğlenci şubeler için "Öğleden sonra" yaz.' in iki
    assert "9/A;Pazartesi;1-6;Sabah;" in iki and "10/B;Salı;1-3,5;Öğleden sonra;" in iki
    assert "Öğleden sonra (Cuma): 1. ders 13:00-13:40" in iki
    for yasak in ("Örnek Anadolu", "Z-04 tahtası", "Lisesi"):
        assert yasak not in iki


# ---- panel uçları --------------------------------------------------------------------------------------------
def okul(panel, tahta):
    kur_ve_gir(panel)
    zil_elle(ELLE)
    z04 = kimlik(tahta_ekle(panel, tahta, "Z-04 tahtası", durum()))
    z05 = kimlik(tahta_ekle(panel, tahta, "Z-05", durum()))
    lab = kimlik(tahta_ekle(panel, tahta, "Fizik Lab", durum()))
    panel.post(f"/tahta/{z04}/kaydet", data={"ad": "Z-04 tahtası", "derslik": "Z-04", "eylem": "kaydet"})
    return z04, z05, lab


def onizleme_kimligi() -> str:
    with vt.islem() as b:
        return vt.ayar_al(b, "program_onizleme")["kimlik"]


def yukle_tablo(panel, csv: str, bicim="tablo"):
    return panel.post("/program/aktar/tablo", data={"bicim": bicim}, files={"dosya": ("p.csv", csv.encode("utf-8"), "text/csv")})


# 25
def test_onizleme_fark_ekle_sil_degistir_ve_dokunulmayan(uygulama, panel, tahta, saat):
    z04, z05, lab = okul(panel, tahta)
    panel.post(f"/tahta/{z04}/program", data={"d_0_normal_1": "1", "sube_0_normal_1": "9/B", "d_0_normal_2": "1"})
    panel.post(f"/tahta/{lab}/program", data={"d_1_normal_1": "1"})
    yanit = yukle_tablo(panel, "derslik;gun;ders;sube\nZ-04;Pzt;1;9/A\nZ-04;Pzt;3;9/A\n")
    assert yanit.headers["location"] == "/program/aktar?adim=onizleme"
    sayfa = panel.get("/program/aktar?adim=onizleme").text
    assert "1 tahtanın programı değişecek · 1 ders saati eklenecek · 1 silinecek · 1 şubesi değişecek" in sayfa
    assert f'name="temizle_tahta" value="{lab}"' in sayfa  # dosyada geçmeyen ama programı olan tahta
    assert "~ Pazartesi · Normal · 1. ders · 9/B → 9/A" in sayfa


# 26
def test_onay_yalniz_kapsamdaki_tahta_devre_ciftini_degistirir(uygulama, panel, tahta, saat):
    kur_ve_gir(panel)
    sabah = zil_satirlari({**ELLE, "devre_adi": "Sabah", "ilk_ders": "07:30", "ders_sayisi": "6", "ogle_sonra": "0"})
    ogle = zil_satirlari({**ELLE, "devre_adi": "Öğleden sonra", "ilk_ders": "13:00", "ders_sayisi": "6", "ogle_sonra": "0"})
    zil_kur(sabah + ogle)
    t = kimlik(tahta_ekle(panel, tahta, "Z-04", durum()))
    panel.post(f"/tahta/{t}/program", data={"d_0_sabah_1": "1", "d_0_ogle_1": "1", "sube_0_ogle_1": "11/C"})
    yukle_tablo(panel, "derslik;gun;ders;devre;sube\nZ-04;Salı;2-3;Sabah;9/A\n")
    assert "1 tahtanın programı güncellendi" in ileti(panel.post("/program/aktar/onayla", data={"onizleme": onizleme_kimligi()}))
    satirlar = {(s["gun"], s["devre"], s["ders_no"]): s["sube"] for s in sorgu("SELECT * FROM tahta_ders WHERE tahta_id = ?", t)}
    assert satirlar == {(1, "sabah", 2): "9/A", (1, "sabah", 3): "9/A", (0, "ogle", 1): "11/C"}  # öğle satırı kaldı
    kayit = sorgu("SELECT * FROM kayit WHERE islem = 'Ders programı içe aktarıldı'")[0]["ayrinti"]
    assert kayit == "CSV · 1 tahta · +2 −1 ~0 · 0 hatalı satır atlandı" and "9/A" not in kayit


# 27
def test_onay_temizle_kutusu_dosyada_olmayan_tahtanin_devresini_siler(uygulama, panel, tahta, saat):
    z04, z05, lab = okul(panel, tahta)
    panel.post(f"/tahta/{lab}/program", data={"d_1_normal_1": "1"})
    yukle_tablo(panel, "derslik;gun;ders\nZ-04;Pzt;1\n")
    panel.post("/program/aktar/onayla", data={"onizleme": onizleme_kimligi(), "temizle_tahta": [str(lab), str(z05)]})
    assert sorgu("SELECT * FROM tahta_ders WHERE tahta_id = ?", lab) == []
    assert len(sorgu("SELECT * FROM tahta_ders WHERE tahta_id = ?", z04)) == 1


# 28
def test_eslesme_hatirlanir_ve_sonraki_aktarimda_uygulanir(uygulama, panel, tahta, saat):
    z04, z05, lab = okul(panel, tahta)
    bayt = asc_xml([kart("L1", 0, 1, "r4"), kart("L1", 0, 2, "r1")], TEMEL_DERSLER)  # Spor Salonu'nun tahtası yok
    panel.post("/program/aktar/asc", files={"dosya": ("p.xml", bayt, "text/xml")})
    sayfa = panel.get("/program/aktar?adim=esleme").text
    assert "Spor Salonu" in sayfa and 'name="d_0"' in sayfa and 'name="p_0"' in sayfa
    with vt.islem() as b:
        derslikler = program_aktar.coz(b, vt.ayar_al(b, "program_onizleme")["veri"])["cozum"]["eslesme"]["derslik"]
    n = next(i for i, e in enumerate(derslikler) if e["ad"].startswith("Spor Salonu"))
    yanit = panel.post("/program/aktar/esle", data={"onizleme": onizleme_kimligi(), f"d_{n}": str(z05)})
    assert yanit.headers["location"] == "/program/aktar?adim=onizleme"
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Ders programı eşlemesi değişti'")[0]["ayrinti"] == "1 eşleme"
    panel.post("/program/aktar/onayla", data={"onizleme": onizleme_kimligi()})
    assert len(sorgu("SELECT * FROM tahta_ders WHERE tahta_id = ?", z05)) == 1
    hatirlanan = sorgu("SELECT * FROM program_eslesme WHERE tur = 'derslik' AND anahtar = 'spor'")  # derslik_anahtari: sondaki \" salonu\" atılır
    assert hatirlanan[0]["tahta_id"] == z05 and hatirlanan[0]["kaynak"] == "asc"
    panel.post("/program/aktar/asc", files={"dosya": ("p.xml", bayt, "text/xml")})
    with vt.islem() as b:
        cozum = program_aktar.coz(b, vt.ayar_al(b, "program_onizleme")["veri"])["cozum"]
    assert next(e for e in cozum["eslesme"]["derslik"] if e["ad"].startswith("Spor"))["durum"] == "hatirlanan"
    # kaldırılan (iptal) tahtanın eşlemesi yok sayılır
    panel.post(f"/tahta/{z05}/kaydet", data={"ad": "Z-05", "eylem": "sil"})
    with vt.islem() as b:
        cozum = program_aktar.coz(b, vt.ayar_al(b, "program_onizleme")["veri"])["cozum"]
    assert next(e for e in cozum["eslesme"]["derslik"] if e["ad"].startswith("Spor"))["durum"] == "eslesmedi"


# 29
def test_geri_yukleme_ve_geri_yuklemenin_geri_alinmasi(uygulama, panel, tahta, saat):
    z04, z05, lab = okul(panel, tahta)
    panel.post(f"/tahta/{z04}/program", data={"d_0_normal_1": "1", "sube_0_normal_1": "9/A"})
    yukle_tablo(panel, "derslik;gun;ders\nZ-04;Salı;5\n")
    panel.post("/program/aktar/onayla", data={"onizleme": onizleme_kimligi()})
    surumler = sorgu("SELECT * FROM program_surum ORDER BY id")
    assert len(surumler) == 1 and json.loads(surumler[0]["veri_json"]) == [[z04, 0, "normal", 1, "9/A"]]
    onay = panel.post(f"/program/gecmis/{surumler[0]['id']}/geri-yukle")
    assert onay.status_code == 200 and "tarihli sürüme döndürür" in onay.text and 'name="onay" value="1"' in onay.text
    assert sorgu("SELECT gun FROM tahta_ders") == [{"gun": 1}]  # onaysız değişmez
    yanit = panel.post(f"/program/gecmis/{surumler[0]['id']}/geri-yukle", data={"onay": "1"})
    assert "tarihli sürüme döndürüldü" in ileti(yanit)
    assert [(s["gun"], s["ders_no"], s["sube"]) for s in sorgu("SELECT * FROM tahta_ders")] == [(0, 1, "9/A")]
    son = sorgu("SELECT * FROM program_surum ORDER BY id DESC")[0]
    assert son["neden"] == "geri_yukleme" and json.loads(son["veri_json"]) == [[z04, 1, "normal", 5, ""]]
    panel.post(f"/program/gecmis/{son['id']}/geri-yukle", data={"onay": "1"})  # geri almanın geri alınması
    assert [(s["gun"], s["ders_no"]) for s in sorgu("SELECT * FROM tahta_ders")] == [(1, 5)]
    # 0.19.0: sürüm listesi ve "Geri yükle" formu "Önceki programlar" sekmesindedir (Derslik'te yalnız şerit bağlantısı).
    derslik = panel.get("/program?bolum=derslik").text
    assert 'href="/program/gecmis">Önceki programlar' in derslik and 'action="/program/gecmis/' not in derslik
    gecmis = panel.get("/program/gecmis").text
    assert '<a href="/program/gecmis" aria-current="page">Önceki programlar' in gecmis
    kalan = [s["id"] for s in sorgu("SELECT id FROM program_surum ORDER BY id")]
    assert kalan and all(f'action="/program/gecmis/{i}/geri-yukle"' in gecmis for i in kalan)
    assert gecmis.count("<button>Geri yükle</button>") == len(kalan)
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Ders programı geri yüklendi'")[0]["ayrinti"].startswith("sürüm #")


def test_surum_en_cok_10(uygulama, panel, tahta, saat):
    okul(panel, tahta)
    with vt.islem() as b:
        for _ in range(12):
            program_aktar.surum_yaz(b, "yonetici", "aktarim", "csv")
        assert b.execute("SELECT COUNT(*) FROM program_surum").fetchone()[0] == 10


# 30
def test_mevcut_csv_formul_kacisi_ve_geri_yuklemede_aynisi(uygulama, panel, tahta, saat):
    z04, z05, lab = okul(panel, tahta)
    panel.post(f"/tahta/{lab}/kaydet", data={"ad": "Fizik Lab", "derslik": "-1 Lab", "eylem": "kaydet"})
    panel.post(f"/tahta/{lab}/program", data={"d_2_normal_3": "1", "sube_2_normal_3": "10/B"})
    indir = panel.get("/program/aktar/mevcut.csv")
    assert indir.status_code == 200 and "'-1 Lab" in indir.content.decode("utf-8-sig")
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Mevcut ders programı indirildi'")[0]["ayrinti"] == "1 satır"
    yukle_tablo(panel, indir.content.decode("utf-8-sig"))
    with vt.islem() as b:
        sonuc = program_aktar.coz(b, vt.ayar_al(b, "program_onizleme")["veri"])
    assert sonuc["fark"]["toplam"]["tahta"] == 0 and sonuc["cozum"]["satirlar"] == {lab: {(2, "normal", 3): "10/B"}}
    assert panel.get("/program/aktar/istem.txt").text.startswith("Sen bir veri dönüştürücüsün.")
    assert panel.get("/program/aktar/sablon.csv").content.startswith(b"\xef\xbb\xbfsube;gun;ders;devre;derslik")


# 31
def test_idareci_sihirbazi_kullanamaz_kayda_duser(uygulama, panel, tahta, saat):
    okul(panel, tahta)
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    assert "yönetici yetkisi" in ileti(panel.get("/program/aktar"))
    assert "yönetici yetkisi" in ileti(panel.get("/program/aktar/mevcut.csv"))
    assert "yönetici yetkisi" in ileti(panel.get("/program/gecmis"))
    for yol in ("/program/aktar/esle", "/program/aktar/onayla", "/program/gecmis/1/geri-yukle"):
        assert "yönetici yetkisi" in ileti(panel.post(yol, data={})), yol
    assert "yönetici yetkisi" in ileti(panel.post("/program/aktar/asc", files={"dosya": ("a.xml", b"<a/>", "text/xml")}))
    assert "yönetici yetkisi" in ileti(yukle_tablo(panel, "x"))
    assert len(sorgu("SELECT * FROM kayit WHERE islem = 'Yetkisiz işlem reddedildi'")) == 8
    assert panel.get("/program/aktar/sablon.csv").status_code == 200  # oturumlu herkes
    assert 'href="/program/aktar?yeni=1"' not in panel.get("/program?bolum=derslik").text


def test_onizleme_baska_kullanici_onaylayamaz(uygulama, panel, tahta, saat):
    okul(panel, tahta)
    kullanici_ekle(panel, "yonetici2", "yonetici")
    yukle_tablo(panel, "derslik;gun;ders\nZ-04;Pzt;1\n")
    kimlik_ = onizleme_kimligi()
    gir(panel, "yonetici2")
    assert "başka bir kullanıcıya" in ileti(panel.post("/program/aktar/onayla", data={"onizleme": kimlik_}))
    assert sorgu("SELECT * FROM tahta_ders") == []


# 32
def test_eski_derslik_uclari_sihirbaza_yonlendirir(uygulama, panel, tahta, saat):
    okul(panel, tahta)
    for yol in ("/program/derslik/yukle", "/program/derslik/onayla"):
        yanit = panel.post(yol, data={})
        assert yanit.status_code == 303 and yanit.headers["location"].startswith("/program/aktar?"), yol


def test_yz_yapistirma_onizleme_bandi_ve_cok_hata_ek_onayi(uygulama, panel, tahta, saat):
    z04, z05, lab = okul(panel, tahta)
    metin_ = "Tabii!\n```\nsube;gun;ders;devre;derslik\n9/A;Pazartesi;1-2;;Z-04\n9/A;Funday;1;;\n9/A;Pzt;99;;\n```"
    yanit = panel.post("/program/aktar/tablo", data={"bicim": "yz", "metin": metin_})
    assert yanit.headers["location"] == "/program/aktar?adim=onizleme"
    sayfa = panel.get("/program/aktar?adim=onizleme").text
    assert "yapay zekâ aracından geldi" in sayfa and "9/A: 2 saat" in sayfa and 'name="onay_hatali"' in sayfa
    assert "Satırların çoğu okunamadı" in ileti(panel.post("/program/aktar/onayla", data={"onizleme": onizleme_kimligi()}))
    assert "güncellendi" in ileti(panel.post("/program/aktar/onayla", data={"onizleme": onizleme_kimligi(), "onay_hatali": "1"}))
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Ders programı içe aktarıldı'")[0]["ayrinti"].startswith(
        "Yapay zekâ çıktısı (yapıştırma) · 1 tahta · +2")
    tc = panel.post("/program/aktar/tablo", data={"bicim": "yz", "metin": f"sube;gun;ders\n9/A;Pzt;1 {SAHTE_TC}\n"})
    assert "kimlik numarasına benzeyen" in ileti(tc) and SAHTE_TC not in json.dumps(sorgu("SELECT * FROM kayit"))
    assert "Önce zil" not in panel.get("/program/aktar").text


# 33
def test_goc_mevcut_veritabanina_uygulanir_program_aktarma_tablolari(tmp_path, monkeypatch):
    import sqlite3

    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    b = sqlite3.connect(tmp_path / "tahta-kontrol.db")
    for sira in range(8):
        b.executescript(vt.GOCLER[sira])
    b.execute("PRAGMA user_version = 8")
    b.commit()
    b.close()
    vt.hazirla()
    with vt.islem() as b:
        assert b.execute("PRAGMA user_version").fetchone()[0] == len(vt.GOCLER) >= 9
        assert b.execute("SELECT COUNT(*) FROM program_eslesme").fetchone()[0] == 0
        assert b.execute("SELECT COUNT(*) FROM program_surum").fetchone()[0] == 0


# 34
def test_sube_duzelt_subesi_eki():
    assert metin.sube_duzelt("9. Sınıf A Şubesi") == "9/A" and metin.sube_duzelt("9A Şubesi") == "9/A"
    assert metin.sube_duzelt("Hazırlık Sınıfı B Şubesi") == "Hazırlık/B" and metin.sube_duzelt("12 C şube") == "12/C"
    for eski, beklenen in (("9-A", "9/A"), ("9A", "9/A"), ("9/a", "9/A"), ("hazırlık b", "Hazırlık/B"), ("10/İ", "10/İ"),
                           ("10-c", "10/C"), ("x", None), ("şube", None)):  # fmt: skip
        assert metin.sube_duzelt(eski) == beklenen, eski


def test_sihirbaz_arayuzu_adimlar_kopyala_ve_sube_sirasi(uygulama, panel, tahta, saat):
    okul(panel, tahta)
    kaynak = panel.get("/program/aktar?yeni=1").text
    assert '<li aria-current="step">Kaynak</li>' in kaynak
    # İstemi kopyala: JS yoksa gizli kalır, pano yoksa metin seçilir (data-kopyala-yedek); hedef istem alanı
    assert 'data-kopyala="istem" data-kopyala-yedek hidden' in kaynak and '<textarea id="istem"' in kaynak
    metin_ = "sube;gun;ders;devre;derslik\n10/B;Salı;1;;Z-05\n9/A;Pazartesi;1-2;;Z-04\n"
    panel.post("/program/aktar/tablo", data={"bicim": "yz", "metin": metin_})
    sayfa = panel.get("/program/aktar?adim=onizleme").text
    assert '<li aria-current="step">Önizleme ve onay</li>' in sayfa
    assert sayfa.index("9/A: 2 saat") < sayfa.index("10/B: 1 saat")  # düzey sırası (abece değil)
    assert program_aktar.sube_sayilari({"satirlar": {1: {(0, "normal", 1): "10/B"}, 2: {(0, "normal", 1): "9/A"}}}) == [
        ("9/A", 1), ("10/B", 1)]


# ---- 0.21.0: ikili eğitimli aSc dosyası (bir okulun gerçek dışa aktarımının YAPISI; içerik UYDURMA) -----------------
# Yapı: 16 ders saati "S1…S8" (sabah, 08:00'den) + "Ö1…Ö8" (öğle, 13:30'dan), aralarında `breaks` (devre arası);
# derslikler "DERSLİK-101" (kısa ad "D-101"); sabahçı 11/A, 11/B ve öğlenci 9/I, 9/İ aynı iki dersliği paylaşır;
# her ders saati ayrı kart (ppc=2, kart sayısı = ppw); kartın dersliği çoğunlukla boş (sınıfın ana dersliği);
# bir bölünmüş grup kartı; bir kart Görsel Sanatlar atölyesinde (tahtası yok). Öğretmen ve ders adları uydurmadır.
IKILI_SABAH = ["08:00", "08:35", "09:25", "10:00", "10:45", "11:20", "12:05", "12:40"]
IKILI_OGLE = ["13:30", "14:05", "14:50", "15:25", "16:15", "16:50", "17:35", "18:10"]
IKILI_SINIFLAR = [("c1", "11/A", "r1", "s"), ("c2", "9/I", "r1", "o"), ("c3", "11/B", "r2", "s"), ("c4", "9/İ", "r2", "o")]


def ikili_xml(*, adlar="onek", ara=True, yayil=False, kart_sayisi=8) -> bytes:
    """adlar: "onek" (S1…Ö8) | "sayi" (1…16) | "tekrar" (1…8, 1…8). yayil: her sınıf iki devrenin saatlerini de
    kullanır (tek devreli okul). kart_sayisi: sınıfın günlük ders saati (≤ 8)."""
    p = []
    for i, bas in enumerate(IKILI_SABAH + IKILI_OGLE, start=1):
        ad = {"onek": ("S" if i <= 8 else "Ö") + str((i - 1) % 8 + 1), "sayi": str(i), "tekrar": str((i - 1) % 8 + 1)}[adlar]
        p.append(f'<period name="{ad}" short="{ad}" period="{i}" starttime="{bas}" endtime="{program.saat_metni(program.dk(bas) + 35)}"/>')
    aralar = '<breaks><break name="DEVRE ARASI" short="ARA" break="9" starttime="13:15" endtime="13:30"/></breaks>' if ara else ""
    gunler = "".join(f'<daysdef id="d{i}" name="{ad}" short="{ad[:3]}" days="{gun_maskesi(i)}"/>' for i, ad in enumerate(GUNLER_TR))
    siniflar = "".join(f'<class id="{c}" name="{ad}" short="{ad}" classroomids="{r}" teacherid="o1"/>' for c, ad, r, _d in IKILI_SINIFLAR)
    gruplar = ('<group id="g1" classid="c3" name="Grup 1" entireclass="0" divisiontag="1" studentids=""/>'
               '<group id="g2" classid="c3" name="Grup 2" entireclass="0" divisiontag="1" studentids=""/>')  # fmt: skip
    dersler, kartlar = [], []
    for c, _ad, _r, devre in IKILI_SINIFLAR:
        say = 0
        for gun in range(5):
            for n in range(1, kart_sayisi + 1):
                period = n + (8 if devre == "o" else 0)
                if yayil and n % 2 == 0:
                    period = n + (0 if devre == "o" else 8)
                ders, oda = f"L{c}", ""
                if c == "c1" and gun == 4 and n == 8:
                    ders, oda = "Lgs", "r9"  # Görsel Sanatlar atölyesi: tahtası yok, atlanır
                elif c == "c3" and gun == 0 and n == 1:
                    ders = "Lgr"  # bölünmüş grup dersi: sınıfın ana dersliğine düşer
                else:
                    say += 1
                kartlar.append(f'<card lessonid="{ders}" classroomids="{oda}" period="{period}" days="{gun_maskesi(gun)}" weeks="1" terms="1"/>')
        dersler.append(f'<lesson id="L{c}" classids="{c}" groupids="" subjectid="s1" teacherids="o1" classroomids="" '
                       f'periodsperweek="{say}" periodspercard="2" weeksdefid="w1" termsdefid="t1"/>')  # fmt: skip
    dersler.append('<lesson id="Lgs" classids="c1" groupids="" subjectid="s1" teacherids="o2" classroomids="r9" periodsperweek="1" '
                   'periodspercard="1" weeksdefid="w1" termsdefid="t1"/>')  # fmt: skip
    dersler.append('<lesson id="Lgr" classids="" groupids="g1" subjectid="s1" teacherids="o2" classroomids="" periodsperweek="1" '
                   'periodspercard="1" weeksdefid="w1" termsdefid="t1"/>')  # fmt: skip
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<timetable importtype="database" displayname="aSc Timetables 2012 XML">'
        f"<periods>{''.join(p)}</periods>{aralar}<daysdefs>{gunler}</daysdefs>"
        '<weeksdefs><weeksdef id="w1" name="Her hafta" weeks="1"/></weeksdefs>'
        '<termsdefs><termsdef id="t1" name="Bütün yıl" terms="1"/></termsdefs>'
        '<subjects><subject id="s1" name="Uydurma Ders" short="UYD"/></subjects>'
        '<teachers><teacher id="o1" firstname="Uydurma" lastname="Öğretmenoğlu" name="Uydurma Öğretmenoğlu" short="UÖ"/>'
        '<teacher id="o2" firstname="Deneme" lastname="Kişi" name="Deneme Kişi" short="DK"/></teachers>'
        '<buildings><building id="b1" name="Ana bina"/></buildings>'
        '<classrooms><classroom id="r1" name="DERSLİK-101" short="D-101"/><classroom id="r2" name="DERSLİK-102" short="D-102"/>'
        '<classroom id="r3" name="DERSLİK-501" short="D-501"/><classroom id="r9" name="Görsel Sanatlar Atölyesi" short="GSA"/></classrooms>'
        f"<classes>{siniflar}</classes><groups>{gruplar}</groups><lessons>{''.join(dersler)}</lessons>"
        f"<cards>{''.join(kartlar)}</cards></timetable>"
    )  # fmt: skip
    return xml.encode("utf-8")


def ikili_zil(kaydir: int = 0, devreler=(("Sabah", IKILI_SABAH), ("Öğleden sonra", IKILI_OGLE))) -> list[tuple]:
    satirlar = []
    for adi, baslar in devreler:
        for no, bas in enumerate(baslar, start=1):
            b = program.dk(bas) + kaydir
            satirlar += [(g, program.devre_kimligi(adi), adi, no, program.saat_metni(b), program.saat_metni(b + 35)) for g in range(5)]
    return satirlar


def ikili_tahtalar(derslik=("D-101", "D-102"), ad="ETAP"):
    return [{"id": 7, "ad": ad, "derslik": derslik[0], "subeler": ""}, {"id": 3, "ad": ad, "derslik": derslik[1], "subeler": ""}]


def ikili_esle(bayt=None, secimler=None, saatler=None, tahta=None, hatirlanan=None):
    return esle_asc(bayt or ikili_xml(), secimler, saatler if saatler is not None else ikili_zil(), tahta or ikili_tahtalar(), hatirlanan)


def test_asc_ikili_onekli_dosya_devre_gruplari_ve_ders_numaralari():
    okunan, cozum = ikili_esle()
    assert [(g["anahtar"], g["kaynak"], g["ad"], len(g["dersler"])) for g in okunan["devre_gruplari"]] == [
        ("onek:s", "onek", "S1–S8", 8), ("onek:ö", "onek", "Ö1–Ö8", 8)]
    assert okunan["hata_sayisi"] == 0 and not any("Blok ders" in u for u in okunan["uyarilar"])  # her saat ayrı kart
    d101, d102 = cozum["satirlar"][7], cozum["satirlar"][3]
    assert {n for (_g, d, n) in d101 if d == "sabah"} == set(range(1, 9)) == {n for (_g, d, n) in d101 if d == "ogle"}
    assert d101[(0, "sabah", 1)] == "11/A" and d101[(0, "ogle", 1)] == "9/I" and d102[(0, "ogle", 8)] == "9/İ"
    assert d102[(0, "sabah", 1)] == "11/B"  # bölünmüş grup kartı sınıfın ana dersliğine
    assert (4, "sabah", 8) not in d101 and cozum["atlanan"] == 1  # Görsel Sanatlar: tahtası yok
    assert sum(len(v) for v in cozum["satirlar"].values()) == 4 * 40 - 1
    assert [(e["durum"], e["deger"]) for e in cozum["eslesme"]["devre"]] == [("otomatik", "sabah"), ("otomatik", "ogle")]
    assert not cozum["saat_farki"] and cozum["hata_sayisi"] == 0


def test_asc_I_ve_İ_subeleri_ayri_kalir_eski_hatirlanan_anahtar_yok_sayilir():
    okunan, cozum = ikili_esle()
    assert {"9/I", "9/İ"} <= set(okunan["bilgi"]["sinif"])
    sinif = {e["ad"]: e["deger"] for e in cozum["eslesme"]["sinif"]}
    assert sinif["9/I"] == "9/I" and sinif["9/İ"] == "9/İ"
    assert set(cozum["satirlar"][7].values()) == {"11/A", "9/I"} and set(cozum["satirlar"][3].values()) == {"11/B", "9/İ"}
    # 0.20.0 katlanmış anahtarla ("9/i") hatırlanan eşleşme yeni anahtarla eşleşmez: 9/İ yine 9/İ
    _, cozum = ikili_esle(hatirlanan={("sinif", "9/i"): {"tahta_id": None, "deger": "9/I"}})
    assert set(cozum["satirlar"][3].values()) == {"11/B", "9/İ"}


def test_asc_ikili_zil_kaymis_numara_dogru_devreye_ve_uyari():
    _, cozum = ikili_esle(saatler=ikili_zil(10))
    assert sum(len(v) for v in cozum["satirlar"].values()) == 159
    assert cozum["satirlar"][7][(2, "ogle", 3)] == "9/I"  # Ö3 → öğlenin 3. dersi (saat tutmasa da)
    assert set(cozum["saat_farki"]) == {"onek:s", "onek:ö"}
    assert any(u.startswith("Ö1–Ö8: dosyadaki 8 ders saati zil çizelgesinden 5 dakikadan çok farklı") for u in cozum["uyarilar"])


def test_asc_ikili_tek_devreli_zilde_grup_sorusu_ve_secim():
    tek = ikili_zil(devreler=(("Normal", IKILI_SABAH),))
    _, cozum = ikili_esle(saatler=tek)
    assert [(e["anahtar"], e["durum"], e["deger"]) for e in cozum["eslesme"]["devre"]] == [
        ("onek:s", "otomatik", "normal"), ("onek:ö", "eslesmedi", "")]  # S1 saati tutar, Ö tutmaz
    assert {d for v in cozum["satirlar"].values() for (_g, d, _n) in v} == {"normal"} and cozum["eslesmedi_sayisi"] > 0
    _, cozum = ikili_esle(secimler={"devre": {"onek:ö": "yok"}}, saatler=tek)
    assert cozum["eslesme"]["devre"][1]["durum"] == "secildi" and not any(e["durum"] == "eslesmedi" for e in cozum["eslesme"]["saat"])
    assert sum(len(v) for v in cozum["satirlar"].values()) == 79  # yalnız sabah (öğle yok sayıldı)


def test_asc_oneksiz_dosya_siniflardan_ve_aradan_bolunur_tek_devreli_okul_bolunmez():
    okunan, cozum = ikili_esle(ikili_xml(adlar="sayi"))
    assert [(g["kaynak"], g["dersler"][0][0], len(g["dersler"])) for g in okunan["devre_gruplari"]] == [("ara", 1, 8), ("ara", 1, 8)]
    assert cozum["satirlar"][7][(0, "ogle", 1)] == "9/I"  # period 9 → öğlenin 1. dersi
    okunan = ara(ikili_xml(adlar="tekrar", ara=False))
    assert [g["kaynak"] for g in okunan["devre_gruplari"]] == ["ara", "ara"]
    # tek devreli okul: sınıflar iki yarıyı da kullanır → bölünmez (önekli adlar yalnız etiket sayılır)
    for adlar in ("sayi", "onek"):
        okunan = ara(ikili_xml(adlar=adlar, yayil=True))
        assert [g["kaynak"] for g in okunan["devre_gruplari"]] == ["tek"], adlar
        assert okunan["bilgi"]["saat"]["9|13:30"]["no"] == 9  # period numarası (bugünkü davranış)
    # az kartlı dosya (her sınıf günde 2 saat) önek olmadan bölünmez
    assert [g["kaynak"] for g in ara(ikili_xml(adlar="sayi", kart_sayisi=2))["devre_gruplari"]] == ["tek"]


def test_asc_breaks_yalniz_saatleri_okunur_ogretmen_ve_ders_adi_okunmaz():
    asc = program_aktar.asc_oku(ikili_xml())
    assert asc["breaks"] == [{"break": "9", "starttime": "13:15", "endtime": "13:30"}]
    metin_ = json.dumps(asc, ensure_ascii=False)
    for yasak in ("Uydurma", "Öğretmenoğlu", "Deneme Kişi", "UÖ", "Uydurma Ders", "UYD", "Grup 1", "DEVRE ARASI", "Ana bina"):
        assert yasak not in metin_, yasak
    assert "teachers" not in asc and "subjects" not in asc


def test_asc_derslik_rakam_kumesiyle_ikinci_aday_yalniz_tek_adayda():
    assert [metin.rakam_anahtari(x) for x in ("DERSLİK-101", "D-101", "101", "Z-04", "ETAP", "Blok 2 / 101")] == [
        "101", "101", "101", "4", "", "2-101"]
    _, cozum = ikili_esle(tahta=ikili_tahtalar(("101", "DERSLİK-102")))
    durum = {e["ad"]: (e["durum"], e["deger"]) for e in cozum["eslesme"]["derslik"]}
    assert durum["DERSLİK-101 (D-101)"] == ("rakam", "7") and durum["DERSLİK-102 (D-102)"] == ("otomatik", "3")
    # tahta adı da aday: derslik alanı boş, ad "101"
    _, cozum = ikili_esle(tahta=[{"id": 7, "ad": "101", "derslik": "", "subeler": ""}])
    assert next(e for e in cozum["eslesme"]["derslik"] if e["ad"].startswith("DERSLİK-101"))["deger"] == "7"
    # iki tahta aynı rakamı taşırsa eşlenmez
    _, cozum = ikili_esle(tahta=[{"id": 7, "ad": "ETAP", "derslik": "101", "subeler": ""},
                                 {"id": 8, "ad": "101", "derslik": "", "subeler": ""}])  # fmt: skip
    assert next(e for e in cozum["eslesme"]["derslik"] if e["ad"].startswith("DERSLİK-101"))["durum"] == "eslesmedi"
    # dosyada aynı rakamlı iki derslik varsa da eşlenmez (biri öbürünün tahtasına düşmesin)
    bayt = ikili_xml().replace(b'name="DERSL\xc4\xb0K-501" short="D-501"', b'name="LAB-101" short="L-101"')
    bayt = bayt.replace(b'lessonid="Lgs" classroomids="r9"', b'lessonid="Lgs" classroomids="r3"')
    _, cozum = ikili_esle(bayt, tahta=[{"id": 7, "ad": "ETAP", "derslik": "101", "subeler": ""}])
    assert all(e["durum"] == "eslesmedi" for e in cozum["eslesme"]["derslik"] if "101" in e["ad"])


def test_asc_sube_guncellemesi_ana_derslikten():
    okunan, cozum = ikili_esle(tahta=ikili_tahtalar(("", "D-102")))
    assert cozum["satirlar"] == {3: cozum["satirlar"][3]}  # derslik alanı boş tahta (7) eşlenmedi
    _, cozum = ikili_esle(secimler={"derslik": {"derslik-101": "7"}}, tahta=ikili_tahtalar(("", "D-102")))
    g = program_aktar.sube_guncellemesi(okunan["bilgi"], cozum, ikili_tahtalar(("", "D-102")))
    assert [(x["id"], x["subeler"], x["derslik"]) for x in g] == [(3, "9/İ,11/B", "D-102"), (7, "9/I,11/A", "D-101")]


# ---- 0.21.0: panel uçları (zilsiz okul, eşleme ekranı, unut, şube güncellemesi) ------------------------------------
def ikili_okul(panel, tahta, derslikler=("D-101", "")):
    kur_ve_gir(panel)
    idler = []
    for d in derslikler:
        t = kimlik(tahta_ekle(panel, tahta, "ETAP", durum()))
        panel.post(f"/tahta/{t}/kaydet", data={"ad": "ETAP", "derslik": d, "eylem": "kaydet"})
        idler.append(t)
    return idler


def test_asc_zilsiz_okulda_dosyadan_zil_cizelgesi_ve_ucdan_uca_onay(uygulama, panel, tahta, saat):
    t1, t2 = ikili_okul(panel, tahta)
    kaynak = panel.get("/program/aktar").text
    assert 'action="/program/aktar/asc"' in kaynak and "Sınanıyor" not in kaynak and "aSc Timetables 2012 dosyasıyla denendi" in kaynak
    yanit = panel.post("/program/aktar/asc", files={"dosya": ("p.xml", ikili_xml(), "text/xml")})
    assert yanit.headers["location"] == "/program/aktar?adim=esleme"
    sayfa = panel.get("/program/aktar?adim=esleme").text
    assert 'action="/program/aktar/asc/zil"' in sayfa and "Sabah</strong> · 8 ders · 08:00–13:15" in sayfa
    assert "Öğleden sonra</strong> · 8 ders · 13:30–18:45" in sayfa and 'name="g_0"' in sayfa
    assert "Aynı adı taşıyan tahtalar var; numaralarına bakın" in sayfa
    assert f'<option value="{t1}">No {t1} · ETAP · D-101</option>' in sayfa and f'<option value="{t2}">No {t2} · ETAP</option>' in sayfa
    assert sayfa.index(f">No {t1} · ETAP") < sayfa.index(f">No {t2} · ETAP")  # ad, sonra numara sırası
    assert "süresi geçmiş" in ileti(panel.post("/program/aktar/asc/zil", data={"onizleme": "yok", "onay": "1"}))
    assert "onay kutusunu" in ileti(panel.post("/program/aktar/asc/zil", data={"onizleme": onizleme_kimligi()}))
    assert sorgu("SELECT COUNT(*) AS n FROM ders_saati")[0]["n"] == 0
    yanit = panel.post("/program/aktar/asc/zil", data={"onizleme": onizleme_kimligi(), "onay": "1"})
    assert "“aSc · Pzt–Cum” zil çizelgesi oluşturuldu" in ileti(yanit)
    assert sorgu("SELECT COUNT(*) AS n FROM ders_saati")[0]["n"] == 80
    assert {(s["devre"], s["ders_no"], s["baslangic"]) for s in sorgu("SELECT * FROM ders_saati WHERE gun = 0")} >= {
        ("sabah", 1, "08:00"), ("ogle", 1, "13:30"), ("ogle", 8, "18:10")}
    assert sorgu("SELECT kaynak FROM zil_cizelgesi")[0]["kaynak"] == "asc"
    assert "aSc dosyasından" in sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Zil çizelgesi oluşturuldu'")[0]["ayrinti"]
    # zil kuruldu: devreler otomatik eşlenir, D-101'in iki devresi yazılır; D-102'nin tahtası seçilir
    with vt.islem() as b:
        derslikler = program_aktar.coz(b, vt.ayar_al(b, "program_onizleme")["veri"])["cozum"]["eslesme"]["derslik"]
    n = next(i for i, e in enumerate(derslikler) if e["ad"].startswith("DERSLİK-102"))
    panel.post("/program/aktar/esle", data={"onizleme": onizleme_kimligi(), f"d_{n}": str(t2)})
    onizleme = panel.get("/program/aktar?adim=onizleme").text
    assert 'name="subeleri_guncelle" value="1">' in onizleme and "checked" not in onizleme.split('name="subeleri_guncelle"')[1][:40]
    assert f"No {t1} · ETAP: şubeler boş → 9/I,11/A" in onizleme and f"No {t2} · ETAP: şubeler boş → 9/İ,11/B · derslik D-102" in onizleme
    yanit = panel.post("/program/aktar/onayla", data={"onizleme": onizleme_kimligi()})
    assert "2 tahtanın programı güncellendi" in ileti(yanit) and "şube bilgisi" not in ileti(yanit)
    assert len(sorgu("SELECT * FROM tahta_ders")) == 159
    assert {(s["devre"], s["sube"]) for s in sorgu("SELECT * FROM tahta_ders WHERE tahta_id = ?", t2)} == {("sabah", "11/B"), ("ogle", "9/İ")}
    assert sorgu("SELECT subeler, derslik FROM tahta WHERE id = ?", t2) == [{"subeler": "", "derslik": ""}]  # kutu işaretsiz
    # hatırlanan: derslik ve sınıf; otomatik devre ve saat eşlemeleri hatırlanmaz
    turler = {s["tur"] for s in sorgu("SELECT tur FROM program_eslesme WHERE kaynak = 'asc'")}
    assert {"derslik", "sinif"} <= turler and not turler & {"saat", "devre"}
    # ikinci aktarım, şube kutusu işaretli
    panel.post("/program/aktar/asc", files={"dosya": ("p.xml", ikili_xml(), "text/xml")})
    assert "Değişecek tahta yok" in ileti(panel.post("/program/aktar/onayla", data={"onizleme": onizleme_kimligi()}))
    yanit = panel.post("/program/aktar/onayla", data={"onizleme": onizleme_kimligi(), "subeleri_guncelle": "1"})
    assert ileti(yanit) == "Derslik programları değişmedi. 2 tahtanın şube bilgisi programdan güncellendi."
    assert sorgu("SELECT subeler, derslik FROM tahta WHERE id = ?", t2) == [{"subeler": "9/İ,11/B", "derslik": "D-102"}]
    assert sorgu("SELECT subeler, derslik FROM tahta WHERE id = ?", t1) == [{"subeler": "9/I,11/A", "derslik": "D-101"}]
    assert "2 tahtanın şube bilgisi güncellendi" in sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Ders programı içe aktarıldı' "
                                                          "ORDER BY id DESC")[0]["ayrinti"]  # fmt: skip


def test_asc_zil_kaymissa_yalniz_fark_notu_ve_satirlar_yazilir(uygulama, panel, tahta, saat):
    ikili_okul(panel, tahta, ("D-101", "D-102"))
    zil_kur(ikili_zil(10))
    panel.post("/program/aktar/asc", files={"dosya": ("p.xml", ikili_xml(), "text/xml")})
    sayfa = panel.get("/program/aktar?adim=esleme").text
    assert "Zil çizelgeniz bu dosyaya uyuyor; yalnız bazı ders saatleri 5 dakikadan çok farklı" in sayfa
    assert "Devreler: S1–S8 → Sabah · Ö1–Ö8 → Öğleden sonra (otomatik" in sayfa  # kesin eşleşme: soru açılır içinde
    assert "159 ders saati eklenecek" in panel.get("/program/aktar?adim=onizleme").text


def test_asc_hatirlanan_eslesmeleri_unut(uygulama, panel, tahta, saat):
    t1, t2 = ikili_okul(panel, tahta, ("D-101", "D-102"))
    zil_kur(ikili_zil())
    panel.post("/program/aktar/asc", files={"dosya": ("p.xml", ikili_xml(), "text/xml")})
    assert 'action="/program/aktar/unut"' not in panel.get("/program/aktar?adim=esleme").text  # hatırlanan yok
    panel.post("/program/aktar/onayla", data={"onizleme": onizleme_kimligi()})
    with vt.islem() as b:
        b.execute("INSERT INTO program_eslesme (kaynak, tur, anahtar, tahta_id, deger, guncelleme) VALUES ('tablo', 'sube', '9/A', ?, '', 0)", (t1,))
    hatirlanan = len(sorgu("SELECT * FROM program_eslesme WHERE kaynak = 'asc'"))
    panel.post("/program/aktar/asc", files={"dosya": ("p.xml", ikili_xml(), "text/xml")})
    sayfa = panel.get("/program/aktar?adim=esleme").text
    assert 'action="/program/aktar/unut"' in sayfa and f"bu kaynak için {hatirlanan} eşleşme hatırlanıyor" in sayfa
    assert "onay kutusunu" in ileti(panel.post("/program/aktar/unut", data={"onizleme": onizleme_kimligi()}))
    assert len(sorgu("SELECT * FROM program_eslesme WHERE kaynak = 'asc'")) == hatirlanan
    yanit = panel.post("/program/aktar/unut", data={"onizleme": onizleme_kimligi(), "onay": "1"})
    assert f"Hatırlanan {hatirlanan} eşleşme silindi" in ileti(yanit)
    assert sorgu("SELECT kaynak FROM program_eslesme") == [{"kaynak": "tablo"}]  # yalnız o kaynak
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Hatırlanan ders programı eşleşmeleri silindi'") == [
        {"ayrinti": f"aSc · {hatirlanan} eşleşme"}]
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    assert "yönetici yetkisi" in ileti(panel.post("/program/aktar/unut", data={"onay": "1"}))
    assert "yönetici yetkisi" in ileti(panel.post("/program/aktar/asc/zil", data={"onay": "1"}))


# ---- 0.21.0 inceleme düzeltmeleri ---------------------------------------------------------------------------------
def test_goc_0_21_0_eski_asc_saat_eslesmeleri_silinir_surumde_tahta_bilgisi_alani(tmp_path, monkeypatch):
    import sqlite3

    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    onceki = len(vt.GOCLER) - 1
    assert "tur = 'saat'" in vt.GOCLER[onceki] and "tahta_json" in vt.GOCLER[onceki]
    b = sqlite3.connect(tmp_path / "tahta-kontrol.db")
    for sira in range(onceki):
        b.executescript(vt.GOCLER[sira])
    b.execute(f"PRAGMA user_version = {onceki}")
    # 0.20.0'ın yazdığı otomatik saat eşlemeleri ('ogle|1' sabahın ilk saatine) ve dokunulmaması gerekenler
    b.executemany("INSERT INTO program_eslesme (kaynak, tur, anahtar, tahta_id, deger, guncelleme) VALUES (?, ?, ?, NULL, ?, 0)",
                  [("asc", "saat", "1|08:00", "ogle|1"), ("asc", "saat", "9|13:30", "yok"), ("asc", "sinif", "9/a", "9/A"),
                   ("tablo", "saat", "x", "normal|1"), ("eokul", "saat", "y", "normal|1")])  # fmt: skip
    b.commit()
    b.close()
    vt.hazirla()
    with vt.islem() as b:
        kalan = {(s["kaynak"], s["tur"]) for s in b.execute("SELECT * FROM program_eslesme")}
        assert kalan == {("asc", "sinif"), ("tablo", "saat"), ("eokul", "saat")}
        assert "tahta_json" in {s["name"] for s in b.execute("PRAGMA table_info(program_surum)")}


def test_asc_hatirlanan_saat_eslemesi_yoksa_devre_grubu_eslemesi_gecerli():
    # göçten sonra eski otomatik saat eşlemesi yoktur; elle seçilen (0.21.0) saat eşlemesi yine öncelikli
    _, cozum = ikili_esle(saatler=ikili_zil(10))
    assert sum(len(v) for v in cozum["satirlar"].values()) == 159 and cozum["satirlar"][7][(0, "sabah", 1)] == "11/A"
    _, cozum = ikili_esle(saatler=ikili_zil(10), hatirlanan={("saat", "9|13:30"): {"tahta_id": None, "deger": "yok"}})
    assert (0, "ogle", 1) not in cozum["satirlar"][7] and cozum["satirlar"][7][(0, "ogle", 2)] == "9/I"


def saat_eslesmedi(cozum) -> bool:
    return any(e["durum"] == "eslesmedi" for e in cozum["eslesme"]["saat"] + cozum["eslesme"]["devre"])


def _saatsiz_period(bayt: bytes, kullan: bool = False) -> bytes:
    bayt = bayt.replace(b"</periods>", b'<period name="Et" short="Et" period="17" starttime="" endtime=""/></periods>')
    if kullan:  # 11/A'nın Cuma 1. kartı saatsiz period'a
        bayt = bayt.replace(b'<card lessonid="Lc1" classroomids="" period="1" days="00001"',
                            b'<card lessonid="Lc1" classroomids="" period="17" days="00001"', 1)  # fmt: skip
    return bayt


def _saatsiz_dosya() -> bytes:
    bayt = ikili_xml()
    for bas in IKILI_SABAH + IKILI_OGLE:
        bayt = bayt.replace(f'starttime="{bas}"'.encode(), b'starttime=""')
    return bayt


def test_asc_baslangic_saati_olmayan_period_gruplamayi_kapatmaz():
    okunan, cozum = ikili_esle(_saatsiz_period(ikili_xml()), saatler=ikili_zil(10))
    assert [g["anahtar"] for g in okunan["devre_gruplari"]] == ["onek:s", "onek:ö"]
    assert sum(len(v) for v in cozum["satirlar"].values()) == 159 and not saat_eslesmedi(cozum)
    assert not any("Başlangıç saati yazılmamış" in u for u in okunan["uyarilar"])  # kullanılmıyor: sessiz
    # kullanılan saatsiz period: bölme yine yapılır, o saat uyarıyla eşleme adımına kalır
    okunan, cozum = ikili_esle(_saatsiz_period(ikili_xml(adlar="sayi"), kullan=True), saatler=ikili_zil(10))
    assert [g["kaynak"] for g in okunan["devre_gruplari"]] == ["ara", "ara"]
    assert any(u.startswith("Başlangıç saati yazılmamış 1 ders saati (Et)") for u in okunan["uyarilar"])
    assert next(e for e in cozum["eslesme"]["saat"] if e["ad"] == "Et")["durum"] == "eslesmedi"
    assert sum(len(v) for v in cozum["satirlar"].values()) == 158
    # hiçbir period'un saati yok: öneri çıkamaz, ama kullanıcıya söylenir (çıkmaz yok)
    okunan, cozum = ikili_esle(_saatsiz_dosya(), saatler=ikili_zil())
    assert okunan["devre_gruplari"] == []
    zil = program_aktar.asc_zil_hazirla(okunan, ikili_zil(), cozum)
    assert zil["zil_gerekli"] and zil["zil_onerisi"] is None and "başlangıç saati yazılmamış" in zil["zil_onerilemez"]


def test_asc_saatsiz_dosya_zilsiz_okulda_yuklemede_reddedilir(uygulama, panel, tahta, saat):
    ikili_okul(panel, tahta)
    yanit = panel.post("/program/aktar/asc", files={"dosya": ("p.xml", _saatsiz_dosya(), "text/xml")})
    assert ileti(yanit) == program_aktar.ASC_SAATSIZ and yanit.headers["location"].startswith("/program/aktar")
    # tek saatsiz period zilsiz okulda yüklemeyi engellemez ve zil önerisi çıkar
    panel.post("/program/aktar/asc", files={"dosya": ("p.xml", _saatsiz_period(ikili_xml()), "text/xml")})
    assert 'action="/program/aktar/asc/zil"' in panel.get("/program/aktar?adim=esleme").text


def test_asc_tek_gruplu_dosyada_devre_secimi_hatirlanir_ve_okunur():
    bayt = ikili_xml(adlar="sayi", yayil=True)
    _, cozum = ikili_esle(bayt, saatler=ikili_zil(10))
    assert cozum["eslesme"]["devre"][0]["durum"] == "eslesmedi" and saat_eslesmedi(cozum)
    _, secilen = ikili_esle(bayt, secimler={"devre": {"tek": "sabah"}}, saatler=ikili_zil(10))
    assert (secilen["eslesme"]["devre"][0]["durum"], secilen["eslesme"]["devre"][0]["deger"]) == ("secildi", "sabah")
    _, cozum = ikili_esle(bayt, saatler=ikili_zil(10), hatirlanan={("devre", "tek"): {"tahta_id": None, "deger": "sabah"}})
    e = cozum["eslesme"]["devre"][0]
    assert (e["anahtar"], e["durum"], e["deger"]) == ("tek", "hatirlanan", "sabah") and not saat_eslesmedi(cozum)
    assert cozum["satirlar"] == secilen["satirlar"]
    # zilde karşılığı olmayan hatırlanan değer yok sayılır; bu oturumda açıkça "saatlerden eşle" seçilirse o geçerli
    _, cozum = ikili_esle(bayt, saatler=ikili_zil(10), hatirlanan={("devre", "tek"): {"tahta_id": None, "deger": "aksam"}})
    assert cozum["eslesme"]["devre"][0]["durum"] == "eslesmedi"
    _, cozum = ikili_esle(bayt, secimler={"devre": {"tek": ""}}, saatler=ikili_zil(10),
                          hatirlanan={("devre", "tek"): {"tahta_id": None, "deger": "sabah"}})  # fmt: skip
    assert (cozum["eslesme"]["devre"][0]["durum"], cozum["eslesme"]["devre"][0]["deger"]) == ("secildi", "")


def test_asc_rakam_adayi_sube_adli_tahtaya_dusmez_ve_hatirlanmaz(uygulama):
    bayt = ikili_xml().replace(b'name="DERSL\xc4\xb0K-501" short="D-501"', b'name="Kimya Lab 12" short="KL12"')
    bayt = bayt.replace(b'lessonid="Lgs" classroomids="r9"', b'lessonid="Lgs" classroomids="r3"')
    for ad in ("12/A", "Tahta 12", "12 A"):
        _, cozum = ikili_esle(bayt, tahta=[{"id": 1, "ad": ad, "derslik": "", "subeler": ""}])
        e = next(e for e in cozum["eslesme"]["derslik"] if e["ad"].startswith("Kimya Lab 12"))
        assert e["durum"] == "eslesmedi" and 1 not in cozum["satirlar"], ad
    _, cozum = ikili_esle(bayt, tahta=[{"id": 1, "ad": "12", "derslik": "", "subeler": ""}])  # yalnız numara: aday
    assert next(e for e in cozum["eslesme"]["derslik"] if e["ad"].startswith("Kimya Lab 12"))["durum"] == "rakam"
    # numarasından öneri onayda hatırlanmaz
    with vt.islem() as b:
        b.execute("DELETE FROM program_eslesme")
        program_aktar.eslesmeleri_yaz(b, "asc", cozum)
        assert not b.execute("SELECT * FROM program_eslesme WHERE tur = 'derslik'").fetchall()


def test_asc_sube_guncellemesi_geri_yuklemede_doner_sonradan_degisen_korunur(uygulama, panel, tahta, saat):
    t1, t2 = ikili_okul(panel, tahta, ("D-101", "D-102"))
    with vt.islem() as b:
        b.execute("UPDATE tahta SET subeler = '9/A' WHERE id = ?", (t1,))
    zil_kur(ikili_zil())
    panel.post("/program/aktar/asc", files={"dosya": ("p.xml", ikili_xml(), "text/xml")})
    assert "Önceki programlar”dan geri yüklenirse" in panel.get("/program/aktar?adim=onizleme").text
    panel.post("/program/aktar/onayla", data={"onizleme": onizleme_kimligi(), "subeleri_guncelle": "1"})
    assert sorgu("SELECT subeler FROM tahta WHERE id IN (?, ?) ORDER BY id", t1, t2) == [
        {"subeler": "9/I,11/A"}, {"subeler": "9/İ,11/B"}]
    surum = sorgu("SELECT * FROM program_surum ORDER BY id DESC")[0]
    assert {g["id"]: g["subeler"] for g in json.loads(surum["tahta_json"])} == {t1: "9/A", t2: ""}
    with vt.islem() as b:  # t2 onaydan sonra elle değişti: geri yükleme onu ezmez
        b.execute("UPDATE tahta SET subeler = '10/C' WHERE id = ?", (t2,))
    yanit = panel.post(f"/program/gecmis/{surum['id']}/geri-yukle", data={"onay": "1"})
    assert "1 tahtanın şube bilgisi de eski hâline döndü" in ileti(yanit)
    assert "1 tahtanın şube bilgisi o zamandan beri değiştirildiği için" in ileti(yanit)
    assert sorgu("SELECT subeler FROM tahta WHERE id IN (?, ?) ORDER BY id", t1, t2) == [{"subeler": "9/A"}, {"subeler": "10/C"}]
    assert sorgu("SELECT COUNT(*) AS n FROM tahta_ders")[0]["n"] == 0
    assert "şube bilgisi geri döndü" in sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Ders programı geri yüklendi'")[0]["ayrinti"]
    # geri yüklemenin geri alınması: şube bilgisi de onayın yazdığına döner
    son = sorgu("SELECT * FROM program_surum ORDER BY id DESC")[0]
    assert son["neden"] == "geri_yukleme"
    panel.post(f"/program/gecmis/{son['id']}/geri-yukle", data={"onay": "1"})
    assert sorgu("SELECT subeler FROM tahta WHERE id = ?", t1) == [{"subeler": "9/I,11/A"}]
    assert sorgu("SELECT COUNT(*) AS n FROM tahta_ders")[0]["n"] == 159
