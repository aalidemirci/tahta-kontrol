"""Yoklama 0.14.0 — şube defteri: birleşim kuralı, düzeltme katmanı, beş gün kipi, "N gündür" rozeti,
sorgu bütçesi, saklama/imha, yetki. Bütün adlar ve numaralar UYDURMADIR."""

# ruff: noqa: F811  (içe aktarılan fikstürler test parametresi olarak yeniden adlandırılır)
from __future__ import annotations

import re
import sqlite3
import time
from datetime import date, timedelta

import pytest
from test_altyapi import YEDEK_PAROLASI, hizli_kdf, parola_belirle, yedek_dosyasi  # noqa: F401
from test_yoklama import ajan, baslat, hazir, ogrenci_id, ogrenci_yukle, ogretmen_ekle, pin_uret  # noqa: F401
from yardimci import an, gir, ileti, kullanici_ekle, sorgu

from tahta_sunucu import program, vt
from tahta_sunucu import yoklama as yk
from tahta_sunucu import yoklama_defter as yd

SAATLER = [("08:20", "09:00"), ("09:10", "09:50"), ("10:00", "10:40"), ("10:50", "11:30")]
JSON = {"Accept": "application/json"}


def zil_yaz(gunler=range(5), devre: str = "normal", ad: str = "Normal", saatler=SAATLER) -> None:
    with vt.islem() as b:
        b.executemany("INSERT INTO ders_saati (gun, devre, devre_adi, ders_no, baslangic, bitis) VALUES (?, ?, ?, ?, ?, ?)",
                      [(g, devre, ad, no, bas, bit) for g in gunler for no, (bas, bit) in enumerate(saatler, 1)])  # fmt: skip


def kayit(gun: int, sube: str, ders_no: int, yok=(), gec=(), ogretmen_id=None, kaynak="tahta", zaman=None) -> int:
    """Kasım 2026'nın `gun`. günü için uydurma yoklama kaydı (yok/geç: okul numaraları)."""
    with vt.islem() as b:
        return yk.yoklama_yaz(
            b, tarih=date(2026, 11, gun).isoformat(), sube=sube, ders_no=ders_no, ogretmen_id=ogretmen_id, kaynak=kaynak,
            kaydeden="deneme", tahta_id=None, yok=[ogrenci_id(n) for n in yok], gec=[ogrenci_id(n) for n in gec], kim="deneme",
            an=zaman if zaman is not None else int(an(gun, 12).timestamp()),
        )[0]  # fmt: skip


def hucre(panel, sube: str, tarih: str, okul_no: str, ders_no: int, durum: str, aciklama: str = "", basliklar=None):
    return panel.post("/yoklama/sube/hucre", headers=basliklar or {}, data={
        "tarih": tarih, "sube": sube, "durum": durum, "aciklama": aciklama, "hucre": f"{ogrenci_id(okul_no)}:{ders_no}"})  # fmt: skip


def durum_(sube: str, tarih: str, okul_no: str, ders_no: int) -> str:
    with vt.islem() as b:
        return yd.hucre_durumu(b, tarih, sube, ders_no, ogrenci_id(okul_no))["durum"]


@pytest.fixture()
def defterli(hazir, panel, saat):  # noqa: F811
    """hazir + hafta içi dört derslik zil düzeni; saat çarşamba 18.11.2026 12:00."""
    zil_yaz()
    saat.ayarla(an(18, 12))
    gir(panel, "yonetici")  # panel oturumu 12 saatte biter; saat iki gün ilerledi
    return hazir


# ---- birleşim kuralı -----------------------------------------------------------------------------------
def test_birlesim_en_son_kayit_gecerli_panel_duzeltmesi_ezer_kaldirilinca_geri_gelir(panel, defterli):
    ikinci, _ = ogretmen_ekle(panel, "Can", "Deneme")
    a_kaydi = kayit(18, "10/A", 1, yok=["1047"], ogretmen_id=defterli["ogretmen_id"], zaman=int(an(18, 8, 30).timestamp()))
    b_kaydi = kayit(18, "10/A", 1, gec=["1047"], ogretmen_id=ikinci, zaman=int(an(18, 8, 40).timestamp()))
    assert durum_("10/A", "2026-11-18", "1047", 1) == "gec"  # A yok, sonra B geç → G
    assert [s["ogrenci_id"] for s in sorgu("SELECT ogrenci_id FROM yoklama_yok WHERE yoklama_id = ?", a_kaydi)] == [ogrenci_id("1047")]
    assert hucre(panel, "10/A", "2026-11-18", "1047", 1, "yok", basliklar=JSON).json()["durum"] == "yok"  # düzeltme ikisini de ezer
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama_yok WHERE yoklama_id = ?", b_kaydi)[0]["n"] == 0  # kayıtlar değişmedi
    assert [s["ogrenci_id"] for s in sorgu("SELECT ogrenci_id FROM yoklama_gec WHERE yoklama_id = ?", b_kaydi)] == [ogrenci_id("1047")]
    with vt.islem() as b:
        assert yk.gecerli_durum(b, "2026-11-18", "10/A", 1) == ({ogrenci_id("1047")}, set(), True)
        g = yk.gunluk_gorunum(b, date(2026, 11, 18), vt.simdi())
    h = next(s for s in g["satirlar"] if s["sube"] == "10/A")["hucreler"][0]
    assert (h["yok"], h["gec"], h["kayit_sayisi"], h["kayit_id"]) == (1, 0, 2, b_kaydi)
    # Aynı duruma yeniden dokunmak düzeltmeyi kaldırır: alttaki kayıt (G) geri görünür.
    assert hucre(panel, "10/A", "2026-11-18", "1047", 1, "yok", basliklar=JSON).json()["durum"] == "gec"
    assert durum_("10/A", "2026-11-18", "1047", 1) == "gec"
    assert durum_("10/A", "2026-11-18", "1047", 2) == "alinmadi" and durum_("10/A", "bozuk", "1047", 1) == "alinmadi"


# ---- fırça: JS'li ve JS'siz aynı; düzeltme katmanı --------------------------------------------------------
def test_firca_jsli_ve_jssiz_ayni_sonucu_verir_ogretmen_kaydi_degismez(panel, defterli, saat):
    kayit(18, "10/A", 1, yok=["1047"])
    kayit(18, "10/A", 2)
    oncesi = sorgu("SELECT * FROM yoklama ORDER BY id"), sorgu("SELECT * FROM yoklama_yok"), sorgu("SELECT * FROM yoklama_iz")
    jsli = hucre(panel, "10/A", "2026-11-18", "1102", 1, "yok", basliklar=JSON)
    assert jsli.status_code == 200 and jsli.headers["cache-control"] == "no-store"
    veri = jsli.json()
    assert set(veri) == {"durum", "ozurlu", "kapsam", "duzeltme", "simge", "durum_metni", "satir_ozeti", "sutun_ozeti", "degisti", "ileti",
                         "satir_duzeltme"}  # fmt: skip
    assert veri["satir_duzeltme"] is True  # satırın "Temizle" düğmesi JS ile hemen görünür
    assert (veri["durum"], veri["simge"], veri["satir_ozeti"], veri["sutun_ozeti"]) == ("yok", "Y", {"yok": 1, "gec": 0}, {"yok": 2, "gec": 0})
    for gizli in ("Burak", "KAYA", "1102", "Ayşe"):
        assert gizli not in jsli.text  # JSON yanıtı ad ve numara içermez
    jssiz = hucre(panel, "10/A", "2026-11-18", "1150", 1, "yok")
    assert jssiz.status_code == 303 and jssiz.headers["location"].startswith("/yoklama/sube?sube=10%2FA&tarih=2026-11-18&firca=yok")
    assert durum_("10/A", "2026-11-18", "1102", 1) == durum_("10/A", "2026-11-18", "1150", 1) == "yok"
    duzeltmeler = sorgu("SELECT ogrenci_id, durum, giren FROM yoklama_duzeltme ORDER BY id")
    assert duzeltmeler == [{"ogrenci_id": ogrenci_id("1102"), "durum": "yok", "giren": "yonetici"},
                           {"ogrenci_id": ogrenci_id("1150"), "durum": "yok", "giren": "yonetici"}]  # fmt: skip
    assert (sorgu("SELECT * FROM yoklama ORDER BY id"), sorgu("SELECT * FROM yoklama_yok"), sorgu("SELECT * FROM yoklama_iz")) == oncesi
    sayfa = panel.get("/yoklama/sube?sube=10/A&tarih=2026-11-18")
    assert sayfa.status_code == 200 and sayfa.headers["cache-control"] == "no-store"
    assert re.search(rf'<td class="yh" data-d="yok" data-duz><button name="hucre" value="{ogrenci_id("1102")}:1"', sayfa.text)
    assert 'name="id"' not in sayfa.text and sayfa.text.count("<form") == sayfa.text.count("</form>")
    # 60 sn içinde aynı hücre: yeni iz satırı açılmaz, son satır güncellenir; 60 sn sonra yeni satır.
    saat.ilerlet(20)
    assert hucre(panel, "10/A", "2026-11-18", "1102", 1, "yok", basliklar=JSON).json()["durum"] == "var"  # kaldırıldı
    assert sorgu("SELECT durum FROM yoklama_duzeltme WHERE ogrenci_id = ?", ogrenci_id("1102")) == [{"durum": "kaldir"}]
    saat.ilerlet(61)
    hucre(panel, "10/A", "2026-11-18", "1102", 1, "yok", basliklar=JSON)
    assert [s["durum"] for s in sorgu("SELECT durum FROM yoklama_duzeltme WHERE ogrenci_id = ? ORDER BY id", ogrenci_id("1102"))] == ["kaldir", "yok"]
    # Kayıttaki durumla aynı fırça ve düzeltme yokken: hiçbir şey yazılmaz.
    ayni = hucre(panel, "10/A", "2026-11-18", "0215", 2, "var", basliklar=JSON).json()
    assert ayni["degisti"] is False and sorgu("SELECT COUNT(*) AS n FROM yoklama_duzeltme WHERE ders_no = 2")[0]["n"] == 0
    # İşlem kaydı: istek başına tek satır, ad/no/kimlik yok.
    kayitlar = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Şube defteri düzeltmesi'")
    assert kayitlar and all(k["ayrinti"] == "18.11.2026 10/A, 1 hücre" for k in kayitlar)
    tum_kayit = " ".join(f"{k['islem']} {k['ayrinti']}" for k in sorgu("SELECT islem, ayrinti FROM kayit WHERE islem LIKE 'Şube defteri%'"))
    for gizli in ("Burak", "KAYA", "1102", "1150", "Ayşe"):
        assert gizli not in tum_kayit


def test_alinmamis_saatte_hucre_409_var_a_cevirmede_not_zorunlu_gec_siniri(panel, defterli):
    kayit(18, "10/A", 1, yok=["1047"], gec=["1102"])
    kayit(18, "10/A", 2, yok=["1047"])
    # Yoklaması alınmamış saat: 409, satır oluşmaz (JSON'da da formda da).
    red = hucre(panel, "10/A", "2026-11-18", "1047", 3, "yok", basliklar=JSON)
    assert red.status_code == 409 and "alınmamış" in red.json()["hata"]
    red = hucre(panel, "10/A", "2026-11-18", "1047", 3, "yok")
    assert red.status_code == 409 and "Bu ders saatinin yoklaması alınmamış" in red.text
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama_duzeltme")[0]["n"] == 0 and sorgu("SELECT COUNT(*) AS n FROM yoklama")[0]["n"] == 2
    # Öğretmenin yok/geç işaretini "var"a çevirmek not ister; yok/geç eklemek istemez.
    for no, ders in (("1047", 1), ("1102", 1)):
        notsuz = hucre(panel, "10/A", "2026-11-18", no, ders, "var", basliklar=JSON)
        assert notsuz.status_code == 400 and "düzeltme notu" in notsuz.json()["hata"]
    assert hucre(panel, "10/A", "2026-11-18", "1047", 1, "var", "kısa", JSON).status_code == 400
    tc = hucre(panel, "10/A", "2026-11-18", "1047", 1, "var", "veli 12345678950 bildirdi", JSON)
    assert tc.status_code == 400 and sorgu("SELECT COUNT(*) AS n FROM yoklama_duzeltme")[0]["n"] == 0
    notlu = hucre(panel, "10/A", "2026-11-18", "1047", 1, "var", "öğretmen yanlış işaretledi", JSON)
    assert notlu.status_code == 200 and notlu.json()["durum"] == "var" and notlu.json()["duzeltme"] is True
    assert sorgu("SELECT aciklama FROM yoklama_duzeltme")[0]["aciklama"] == "öğretmen yanlış işaretledi"
    assert "öğretmen yanlış işaretledi" not in " ".join(k["ayrinti"] for k in sorgu("SELECT ayrinti FROM kayit"))
    # Geç yalnız devrenin ilk dersinde.
    assert hucre(panel, "10/A", "2026-11-18", "1150", 1, "gec", basliklar=JSON).json()["durum"] == "gec"
    ikinci = hucre(panel, "10/A", "2026-11-18", "1150", 2, "gec", basliklar=JSON)
    assert ikinci.status_code == 400 and ikinci.json()["hata"] == yk.ILETI_GEC_ILK_DERS
    # Başka şubenin öğrencisi ve bozuk hücre reddedilir.
    assert hucre(panel, "10/A", "2026-11-18", "2001", 1, "yok", basliklar=JSON).status_code == 400
    bozuk = panel.post("/yoklama/sube/hucre", headers=JSON, data={"tarih": "2026-11-18", "sube": "10/A", "durum": "yok", "hucre": "x"})
    assert bozuk.status_code == 400
    # JS'siz gönderimde not bellekte tutulur ve sayfada hazır gelir (adrese yazılmaz).
    yanit = hucre(panel, "10/A", "2026-11-18", "1047", 2, "var", "veli bildirdi, geldi")
    assert yanit.status_code == 303 and "veli" not in yanit.headers["location"]
    assert 'value="veli bildirdi, geldi"' in panel.get("/yoklama/sube?sube=10/A&tarih=2026-11-18").text


def test_sekizinci_gun_salt_okunur_ve_gelecek_ders_reddedilir(panel, defterli, saat):
    kayit(10, "10/A", 1, yok=["1047"])  # 8 gün önce
    kayit(11, "10/A", 1, yok=["1047"])  # 7 gün önce: düzenlenebilir
    assert hucre(panel, "10/A", "2026-11-11", "1102", 1, "yok", basliklar=JSON).status_code == 200
    eski = hucre(panel, "10/A", "2026-11-10", "1102", 1, "yok", basliklar=JSON)
    assert eski.status_code == 400 and "salt okunur" in eski.json()["hata"]
    sayfa = panel.get("/yoklama/sube?sube=10/A&tarih=2026-11-10").text
    assert "Bu gün salt okunur" in sayfa and 'name="hucre"' not in sayfa and "Y</span>" in sayfa
    saat.ayarla(an(18, 9, 20))  # 3. ders 10:00'da: henüz başlamadı
    with vt.islem() as b, pytest.raises(ValueError, match="henüz başlamadı"):
        yd.sutun_alindi(b, gun=date(2026, 11, 18), sube="10/A", ders_no=3, giren="yonetici", an=vt.simdi())


def test_toplu_butun_gun_yok_yalniz_kayitli_saatlere_alindi_onay_ister(panel, defterli):
    kayit(18, "10/A", 1, yok=["1047"])
    kayit(18, "10/A", 3)
    govde = {"tarih": "2026-11-18", "sube": "10/A", "durum": "yok", "aciklama": ""}
    yanit = panel.post("/yoklama/sube/toplu", data={**govde, "satir": f"{ogrenci_id('1102')}:butun_gun"})
    assert yanit.status_code == 303 and ileti(yanit) == '2 ders saati "yok" yapıldı. Yoklaması alınmamış 2 ders saati atlandı.'
    assert [durum_("10/A", "2026-11-18", "1102", n) for n in (1, 2, 3, 4)] == ["yok", "alinmadi", "yok", "alinmadi"]
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama")[0]["n"] == 2  # alınmamış saatte kayıt açılmadı
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Şube defteri düzeltmesi'")[-1]["ayrinti"] == "18.11.2026 10/A, 2 hücre"
    temiz = panel.post("/yoklama/sube/toplu", data={**govde, "satir": f"{ogrenci_id('1102')}:temizle"})
    assert ileti(temiz).startswith("2 düzeltme kaldırıldı") and durum_("10/A", "2026-11-18", "1102", 1) == "var"
    # "Alındı (herkes var)" iki adımlıdır: sütun düğmesi hiçbir şey yazmaz, onay sorusunu tablonun üstünde açar;
    # onay düğmesi panel kaynaklı boş kayıt açar.
    onaysiz = panel.post("/yoklama/sube/toplu", data={**govde, "sutun": "2"})
    assert onaysiz.status_code == 303 and onaysiz.headers["location"].endswith("&alindi=2#alindi-onay")
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama")[0]["n"] == 2
    soru = panel.get("/yoklama/sube?sube=10/A&tarih=2026-11-18&alindi=2").text
    assert 'id="alindi-onay"' in soru and 'name="alindi" value="2" formaction="/yoklama/sube/toplu"' in soru
    assert "işaretlenmeyen herkes derste sayılacak" in soru and 'name="alindi_yoklar"' not in soru  # gün boyu yok olan yok
    assert 'id="alindi-onay"' not in panel.get("/yoklama/sube?sube=10/A&tarih=2026-11-18&alindi=1").text  # alınmış saat
    onayli = panel.post("/yoklama/sube/toplu", data={**govde, "alindi": "2"})
    assert "t=hata" not in onayli.headers["location"], ileti(onayli)
    assert ileti(onayli) == "2. ders alındı sayıldı: herkes derste. Olmayanları fırçayla işaretleyin."
    yeni = sorgu("SELECT kaynak, ogretmen_id, kaydeden, devre FROM yoklama WHERE ders_no = 2")[0]
    assert yeni == {"kaynak": "panel", "ogretmen_id": None, "kaydeden": "yonetici", "devre": "normal"}
    assert durum_("10/A", "2026-11-18", "1102", 2) == "var" and hucre(panel, "10/A", "2026-11-18", "1102", 2, "yok", basliklar=JSON).status_code == 200
    assert "zaten alınmış" in ileti(panel.post("/yoklama/sube/toplu", data={**govde, "alindi": "2"}))
    sayfa = panel.get("/yoklama/sube?sube=10/A&tarih=2026-11-18").text
    assert 'name="sutun" value="4" formaction="/yoklama/sube/toplu"' in sayfa and 'name="sutun" value="2"' not in sayfa


# ---- beş gün kipi ve "N gündür" -----------------------------------------------------------------------------
def bes_gun_verisi() -> None:
    """Çar 11, Cum 13, Pzt 16 ve Çar 18'de yoklama; Per 12 tarihe özel "ders yok"; Sal 17 hiç alınmadı.
    1047: 13, 16 ve 18'de alınan bütün derslerde yok (mazeretsiz). 1102: aynısı ama görevli (mazeretli)."""
    with vt.islem() as b:
        b.execute("INSERT INTO zil_tarihli (ad, bas, bit, gunler, cizelge_id, olusturan, olusturma) VALUES "
                  "('Okul gezisi', '2026-11-12', '2026-11-12', '0,1,2,3,4', NULL, 'yonetici', 0)")  # fmt: skip
        b.execute("INSERT INTO yoklama_mazeret (ogrenci_id, bas_tarih, bit_tarih, tur, dayanak, giren, olusturma) "
                  "VALUES (?, '2026-11-13', '2026-11-18', 'gorevli', 'yazi', 'yonetici', 0)", (ogrenci_id("1102"),))  # fmt: skip
    kayit(11, "10/A", 1, yok=["1150"])
    for gun in (13, 16, 18):
        for ders in (1, 2):
            kayit(gun, "10/A", ders, yok=["1047", "1102"])
    kayit(16, "10/A", 9, yok=["0215", "1047", "1102"])  # programda olmayan 9. derse yazılmış kayıt


def test_bes_gun_kipi_ogretim_gunleri_rozet_ve_plan_disi_kayit(panel, defterli):
    bes_gun_verisi()
    with vt.islem() as b:
        d = yd.sube_defteri(b, "10/A", date(2026, 11, 18), vt.simdi())
        okul = yd.son_gunler(b, vt.simdi())
        okul_hepsi = yd.son_gunler(b, vt.simdi(), ozurluler=True)
        gun16 = yd.sube_gunu(b, "10/A", date(2026, 11, 16), vt.simdi())
    # Hafta sonu (14–15) ve "ders yok" günü (12) atlanır; 10, 11, 13, 16, 17, 18'den son beşi.
    assert [g["tarih"] for g in d["gunler"]] == ["2026-11-11", "2026-11-13", "2026-11-16", "2026-11-17", "2026-11-18"]
    pzt = d["gunler"][2]
    assert [(x["ders_no"], x["plan"]) for x in pzt["dersler"]] == [(1, True), (2, True), (3, True), (4, True), (9, False)]
    assert d["plan_disi_var"] and [(s["ders_no"], s["plan"]) for s in gun16["sutunlar"]][-1] == (9, False)
    satir = {s["okul_no"]: s for s in d["satirlar"]}
    assert [s["okul_no"] for s in d["satirlar"]] == ["0215", "1047", "1102", "1150"]  # okul no sırası
    # Yoklama alınmamış gün (17) zinciri kırmaz ve sayılmaz: 13, 16, 18 → N = 3.
    assert (satir["1047"]["n"], satir["1047"]["rozet"]["tur"], satir["1047"]["rozet"]["kisa"]) == (3, "vurgulu", "3 gündür")
    assert satir["1047"]["rozet"]["metin"] == "alınan yoklamalara göre 3 gündür derste görülmedi"
    assert (satir["1102"]["n"], satir["1102"]["rozet"]["tur"]) == (3, "ozurlu") and "özürlü" in satir["1102"]["rozet"]["metin"]
    assert "görevli" not in str(satir["1102"]).lower()  # tür hiçbir alanda yok
    assert satir["0215"]["rozet"] is None and satir["1150"]["rozet"] is None
    assert [s["durum"] for s in satir["1047"]["serit"]] == ["tam", "hep", "hep", "alinmadi", "hep"]
    assert [s["durum"] for s in satir["0215"]["serit"]] == ["tam", "tam", "kismen", "alinmadi", "tam"]  # yalnız plan dışı 9. derste yok
    # Mazeretli gün şeritte mazeretsiz günle aynı görünmez (tür yazılmaz).
    assert [(s["durum"], s["simge"]) for s in satir["1102"]["serit"]][1] == ("ozurlu", "□") and "özürlü" in satir["1102"]["serit"][1]["metin"]
    h = satir["1102"]["gunler"][1][0]
    assert (h["durum"], h["ozurlu"], h["simge"]) == ("yok", True, "Ö") and h["etiket"] == "Burak KAYA, 13.11 Cuma 1. ders: yok, özürlü"
    assert satir["1047"]["gunler"][3][0]["durum"] == "alinmadi" and (satir["1047"]["yok"], satir["1047"]["gec"]) == (7, 0)
    # Okul geneli liste: varsayılan olarak yalnız mazeretsiz günü olanlar.
    assert [(s["okul_no"], s["n"]) for s in okul["satirlar"]] == [("1047", 3)] and okul["ozurlu_gizlenen"] == 1
    assert [s["okul_no"] for s in okul_hepsi["satirlar"]] == ["1047", "1102"]


def test_zincir_alinan_butun_derslerde_yok_ister(panel, defterli):
    """16'da plan dışı 9. derste "var" olan öğrencinin o günü zincire girmez (alınan BÜTÜN derslerde yok değil)."""
    for gun in (16, 17, 18):
        kayit(gun, "10/A", 1, yok=["1047"])
    kayit(17, "10/A", 2)  # 17'de 2. derste var
    with vt.islem() as b:
        veri = yd.Veri(b, date(2026, 10, 4), date(2026, 11, 18), "10/A")
        gunler = yd.ogretim_gunleri(veri, "10/A", date(2026, 11, 18), 30, 45)
        assert yd.ardisik_yok(veri, "10/A", ogrenci_id("1047"), gunler) == (1, True)  # yalnız 18; 17 zinciri kırar
        assert yd.rozet(1, True) is None and yd.rozet(2, True)["tur"] == "duz" and yd.rozet(2, False)["tur"] == "ozurlu"
        assert yd.gun_ozeti(veri, date(2026, 11, 17), "10/A", ogrenci_id("1047")) == "kismen"


def test_bes_gun_sayfasi_varsayilan_kip_erisilebilirlik_ve_kayit(panel, defterli):
    bes_gun_verisi()
    yanit = panel.get("/yoklama/sube?sube=10/A")  # tarihsiz: beş gün kipi
    sayfa = yanit.text
    assert yanit.status_code == 200 and yanit.headers["cache-control"] == "no-store"
    assert 'class="defter defter-bes"' in sayfa and "<caption" in sayfa and sayfa.count('class="c-gun"') == 5
    assert 'scope="colgroup"' in sayfa and 'scope="row"' in sayfa and 'tabindex="0"' in sayfa
    assert 'aria-label="Burak KAYA, 13.11 Cuma 1. ders: yok, özürlü"' in sayfa
    assert "alınan yoklamalara göre 3 gündür derste görülmedi" in sayfa and "e-Okul devamsızlık günü değildir" in sayfa
    assert f'href="/yoklama/sube?sube=10/A&amp;tarih=2026-11-13#h-{ogrenci_id("1102")}-1"' in sayfa
    assert "9*" in sayfa and "programda yok" in sayfa
    for yasak in ("Görevli", "gorevli", "raporlu", "resmî devamsızlık", 'name="hucre"'):
        assert yasak not in sayfa
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Şube defteri (5 gün) açıldı'") == [{"ayrinti": "10/A"}]
    suzulmus = panel.get("/yoklama/sube?sube=10/A&yalniz_yok=1").text
    assert "Cemre" in suzulmus and "Ayşe YURT" in suzulmus  # 0215 ve 1150'nin de yokluğu var
    onceki = panel.get("/yoklama/sube?sube=10/A&bitis=2026-11-10").text
    assert "Sal 10.11" in onceki and "Çar 11.11" not in onceki
    # Gezgin simetriktir: "önceki 5 gün"den "sonraki 5 gün" başlangıç penceresine döner (gün yinelenmez, atlanmaz).
    with vt.islem() as b:
        ilk = yd.sube_defteri(b, "10/A", date(2026, 11, 18), vt.simdi())
        geri = yd.sube_defteri(b, "10/A", date.fromisoformat(ilk["onceki"]), vt.simdi())
        ileri = yd.sube_defteri(b, "10/A", date.fromisoformat(geri["sonraki"]), vt.simdi())
    assert ilk["sonraki"] == "" and geri["gunler"][-1]["tarih"] == "2026-11-10" and geri["sonraki"] == "2026-11-18"
    assert [g["tarih"] for g in ileri["gunler"]] == [g["tarih"] for g in ilk["gunler"]]
    assert not {g["tarih"] for g in geri["gunler"]} & {g["tarih"] for g in ilk["gunler"]}
    # Lejant ve notlar tablonun ALTINDADIR (ilk ekranda tablo görünsün); özürlü gün şeritte ayrı simgeyle.
    assert sayfa.index("</table>") < sayfa.index('aria-label="Simgeler"') and "□" in sayfa
    assert panel.get("/yoklama/sube").status_code == 200 and panel.get("/yoklama/sube?sube=12/Z").status_code == 200
    son = panel.get("/yoklama/son-gunler")
    assert son.status_code == 200 and "Ayşe YILMAZ" in son.text and "Burak KAYA" not in son.text and "Görevli" not in son.text
    assert "Burak KAYA" in panel.get("/yoklama/son-gunler?ozurluler=1").text
    ogrenci = panel.get(f"/yoklama/ogrenci/{ogrenci_id('1102')}")
    assert ogrenci.status_code == 200 and "Görevli" in ogrenci.text and "<title>Öğrenci devam görünümü" in ogrenci.text
    assert panel.get("/yoklama/ogrenci/99999").status_code == 303
    islemler = [k["islem"] for k in sorgu("SELECT islem FROM kayit")]
    assert "Son günler listesi açıldı" in islemler and "Öğrenci devam görünümü açıldı" in islemler
    kayit_metni = " ".join(f"{k['islem']} {k['ayrinti']}" for k in sorgu("SELECT islem, ayrinti FROM kayit WHERE islem LIKE '%açıldı'"))
    for gizli in ("Burak", "KAYA", "1102", "1047", "görevli"):
        assert gizli not in kayit_metni
    gunluk = panel.get("/yoklama?tarih=2026-11-18").text
    assert 'href="/yoklama/sube?sube=10/A"' in gunluk and 'href="/yoklama/son-gunler"' in gunluk


# ---- sorgu bütçesi --------------------------------------------------------------------------------------------
def _sorgu_say(islev) -> tuple[int, float]:
    with vt.islem() as b:
        sayac: list[str] = []
        b.set_trace_callback(lambda s: sayac.append(s) if s.lstrip().upper().startswith("SELECT") else None)
        bas = time.perf_counter()
        islev(b)
        sure = time.perf_counter() - bas
        b.set_trace_callback(None)
    return len(sayac), sure


def test_sorgu_sayisi_ogrenci_ve_sube_sayisindan_bagimsiz(panel, defterli):
    bes_gun_verisi()
    an_ = vt.simdi()
    kucuk_defter, _ = _sorgu_say(lambda b: yd.sube_defteri(b, "10/A", date(2026, 11, 18), an_))
    kucuk_liste, _ = _sorgu_say(lambda b: yd.son_gunler(b, an_))
    # 40 şube × 30 öğrenci (1200) + üç günlük yoklama: uydurma toplu veri.
    with vt.islem() as b:
        idler: dict[str, list[int]] = {}
        no = 50000
        for duzey in (9, 10, 11, 12):
            for harf in "ABCDEFGHIJ":
                sube = f"{duzey}/{harf}"
                if sube in ("10/A", "10/B"):
                    sube = f"{duzey}/{harf}X"
                for _ in range(30):
                    no += 1
                    idler.setdefault(sube, []).append(b.execute(
                        "INSERT INTO ogrenci (sube, okul_no, ad, soyad, aktif, guncelleme) VALUES (?, ?, 'Deneme', 'UYDURMA', 1, 0)",
                        (sube, str(no))).lastrowid)  # fmt: skip
        for sube, liste in idler.items():
            for gun in (16, 17, 18):
                for ders in (1, 2, 3, 4):
                    yk.yoklama_yaz(b, tarih=date(2026, 11, gun).isoformat(), sube=sube, ders_no=ders, ogretmen_id=None, kaynak="panel",
                                   kaydeden="deneme", tahta_id=None, yok=liste[:3], gec=[], kim="deneme", an=an_ - 1000)  # fmt: skip
    buyuk_defter, _ = _sorgu_say(lambda b: yd.sube_defteri(b, "9/A", date(2026, 11, 18), an_))
    buyuk_liste, sure = _sorgu_say(lambda b: yd.son_gunler(b, an_))
    assert buyuk_defter == kucuk_defter <= 7 + 5, (kucuk_defter, buyuk_defter)  # ≤ 7 + gün sayısı
    assert buyuk_liste == kucuk_liste <= 7 + 45, (kucuk_liste, buyuk_liste)
    with vt.islem() as b:
        liste = yd.son_gunler(b, an_)
    assert len(liste["satirlar"]) == 40 * 3 + 1 and sure < 1.5, sure  # hedef < 500 ms; yavaş makine payı


def test_gun_planlari_gun_plani_ile_ayni_sonucu_verir(panel, defterli):
    with vt.islem() as b:
        b.execute("INSERT INTO zil_tarihli (ad, bas, bit, gunler, cizelge_id, olusturan, olusturma) VALUES "
                  "('Gezi', '2026-11-12', '2026-11-13', '3', NULL, 'yonetici', 0)")  # fmt: skip
        gunler = [date(2026, 11, 1) + timedelta(days=i) for i in range(20)]
        toplu = program.gun_planlari(b, gunler)
        for gun in gunler:
            tek = program.gun_plani(b, gun)
            assert {k: toplu[gun][k] for k in ("tatil", "dersler", "program_gunu")} == {k: tek[k] for k in ("tatil", "dersler", "program_gunu")}
        assert toplu[date(2026, 11, 12)]["tatil"] == "Gezi" and toplu[date(2026, 11, 13)]["dersler"] and program.gun_planlari(b, []) == {}


# ---- ikili eğitim -----------------------------------------------------------------------------------------------
def test_ikili_egitimde_devre_yazili_eski_gunun_sutunlari_program_degisse_de_kaymaz(panel, hazir, saat):  # noqa: F811
    """Tek devreli okulda devre adı hiçbir yerde görünmez; ikili eğitimde sabah ve öğle sütunları karışmaz."""
    sabah = [("07:30", "08:10"), ("08:20", "09:00"), ("09:10", "09:50")]
    ogle = [("13:00", "13:40"), ("13:50", "14:30")]
    zil_yaz(devre="sabah", ad="Sabah", saatler=sabah)
    zil_yaz(devre="ogle", ad="Öğle", saatler=ogle)
    tahta_id = int(hazir["basliklar"]["X-Tahta-Id"])
    with vt.islem() as b:
        for gun in range(5):
            b.execute("INSERT INTO tahta_ders (tahta_id, gun, devre, ders_no, sube) VALUES (?, ?, 'sabah', 1, '10/A')", (tahta_id, gun))
            b.execute("INSERT INTO tahta_ders (tahta_id, gun, devre, ders_no, sube) VALUES (?, ?, 'ogle', 1, '10/B')", (tahta_id, gun))
    saat.ayarla(an(18, 16))
    gir(panel, "yonetici")
    kayit(17, "10/A", 1, yok=["1047"])
    assert sorgu("SELECT devre FROM yoklama")[0]["devre"] == "sabah"
    with vt.islem() as b:
        d = yd.sube_defteri(b, "10/A", date(2026, 11, 18), vt.simdi())
        obur = yd.sube_defteri(b, "10/B", date(2026, 11, 18), vt.simdi())
    assert [len(g["dersler"]) for g in d["gunler"]] == [3] * 5 and d["devre_adi"] == "Sabah"
    assert [len(g["dersler"]) for g in obur["gunler"]] == [2] * 5 and obur["devre_adi"] == "Öğle"  # sütunlar karışmaz
    with vt.islem() as b:  # program değişti: 10/A artık öğlenci
        b.execute("UPDATE tahta_ders SET devre = 'ogle', ders_no = 2 WHERE sube = '10/A'")
        d = yd.sube_defteri(b, "10/A", date(2026, 11, 18), vt.simdi())
    sutun = {g["tarih"]: len(g["dersler"]) for g in d["gunler"]}
    assert sutun["2026-11-17"] == 3 and sutun["2026-11-18"] == 2  # devre yazılmış gün kaymadı; bugün yeni devre
    # Mazeret ders aralığı yalnız aynı devrenin numaralarına uygulanır.
    m = {"tur": "izinli", "bas_tarih": "2026-11-17", "bit_tarih": "2026-11-17", "ders_bas": 1, "ders_bit": 2, "devre": "ogle"}
    assert yd.mazeret_kapsar(m, "2026-11-17", 1, "ogle") and not yd.mazeret_kapsar(m, "2026-11-17", 1, "sabah")
    assert yd.mazeret_kapsar(m, "2026-11-17", 2, None) and not yd.mazeret_kapsar(m, "2026-11-17", 3, "ogle")
    assert not yd.mazeret_kapsar({**m, "tur": "iptal"}, "2026-11-17", 1, "ogle") and not yd.mazeret_kapsar(m, "2026-11-18", 1, "ogle")


# ---- icmal, CSV, e-Okul işareti ----------------------------------------------------------------------------------
def test_icmal_g_ve_o_gosterir_tur_gostermez_islendi_sonrasi_degisiklik_rozeti(panel, defterli):
    kayit(18, "10/A", 1, yok=["1047", "1102"], gec=["0215"])
    kayit(18, "10/A", 2, yok=["1047"])
    with vt.islem() as b:
        b.execute("INSERT INTO yoklama_mazeret (ogrenci_id, bas_tarih, bit_tarih, tur, dayanak, giren, olusturma) "
                  "VALUES (?, '2026-11-18', '2026-11-18', 'raporlu', 'belge', 'yonetici', 0)", (ogrenci_id("1047"),))  # fmt: skip
        veri = yk.icmal(b, date(2026, 11, 18), "10/A")
    s = veri["subeler"][0]
    hucreler = {o["okul_no"]: (o["hucreler"][:3], o["sayi"], o["gec_sayisi"], o["ozurlu_sayisi"]) for o in s["ogrenciler"]}
    assert hucreler["1047"] == (["Ö", "Ö", "-"], 2, 0, 2)  # yok toplamı özürlü yokları da sayar
    assert hucreler["1102"] == (["Y", ".", "-"], 1, 0, 0) and hucreler["0215"] == (["G", ".", "-"], 0, 1, 0)
    metin_ = yk.icmal_metni(veri)
    assert "1047\tAyşe YILMAZ\t1,2\t2\tözürlü: 1,2\n" in metin_ and "0215\tCemre DOĞAN\t\t0\tgeç: 1\n" in metin_
    govde = panel.get("/yoklama/icmal.csv?tarih=2026-11-18&sube=10/A").content.decode("utf-8")
    assert "18.11.2026;10/A;1047;Ayşe;YILMAZ;1,2;2;2;0;2\r\n" in govde and "18.11.2026;10/A;0215;Cemre;DOĞAN;;0;2;1;0\r\n" in govde
    sayfa = panel.get("/yoklama/icmal?tarih=2026-11-18&sube=10/A").text
    assert "ozurlu-isaret" in sayfa and "gec-isaret" in sayfa
    for cikti in (metin_, govde, sayfa, panel.get("/yoklama?tarih=2026-11-18").text):
        assert "raporlu" not in cikti.lower() and "Belge sunuldu" not in cikti
    # e-Okul işareti: işlendikten sonra düzeltme yapılınca rozet "İşlendikten sonra değişti" olur.
    panel.post("/yoklama/islendi", data={"tarih": "2026-11-18", "sube": "10/A", "deger": "1"})
    assert "İşlendikten sonra değişti" not in panel.get("/yoklama?tarih=2026-11-18").text
    vt_simdi = vt.simdi()
    with vt.islem() as b:
        b.execute("UPDATE eokul_islendi SET zaman = ?", (vt_simdi - 60,))
    hucre(panel, "10/A", "2026-11-18", "1150", 1, "yok", basliklar=JSON)
    assert "İşlendikten sonra değişti" in panel.get("/yoklama?tarih=2026-11-18").text
    assert "e-Okul'a işlendikten sonra değişti" in panel.get("/yoklama/sube?sube=10/A&tarih=2026-11-18").text


def test_kayit_sayfasinda_gec_kutusu_ve_iz_sutunu(panel, defterli):
    yid = kayit(18, "10/A", 1, yok=["1047"], gec=["1102"])
    sayfa = panel.get(f"/yoklama/kayit/{yid}").text
    assert f'name="gec" value="{ogrenci_id("1102")}" checked' in sayfa and "1 geç" in sayfa
    yanit = panel.post(f"/yoklama/kayit/{yid}", data={"eylem": "duzelt", "aciklama": "geç geldi, öğretmen bildirdi",
                                                       "yok": [], "gec": [str(ogrenci_id("1047")), str(ogrenci_id("1102"))]})  # fmt: skip
    assert "t=hata" not in yanit.headers["location"], ileti(yanit)
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama_gec")[0]["n"] == 2 and sorgu("SELECT COUNT(*) AS n FROM yoklama_yok")[0]["n"] == 0
    assert "Ayşe YILMAZ" in panel.get(f"/yoklama/kayit/{yid}").text
    ikinci = kayit(18, "10/A", 2)
    red = panel.post(f"/yoklama/kayit/{ikinci}", data={"eylem": "duzelt", "aciklama": "deneme gerekçesi", "gec": [str(ogrenci_id("1047"))]})
    assert ileti(red) == yk.ILETI_GEC_ILK_DERS
    # Panelden gir formu ders saatinin GEÇERLİ durumuyla açılır; geç bilgisi taşımayan form geçi korur.
    form = panel.get("/yoklama/gir?tarih=2026-11-18&sube=10/A&ders_no=1").text
    assert f'name="yok" value="{ogrenci_id("1047")}" checked' not in form
    panel.post("/yoklama/gir", data={"tarih": "2026-11-18", "sube": "10/A", "ders_no": "1", "yok": [str(ogrenci_id("0215"))]})
    with vt.islem() as b:
        assert yk.gecerli_durum(b, "2026-11-18", "10/A", 1) == ({ogrenci_id("0215")}, {ogrenci_id("1047"), ogrenci_id("1102")}, True)


# ---- saklama, imha, yedek --------------------------------------------------------------------------------------------
def test_imha_yeni_tablolari_kapsar_pasif_ogrenci_yil_icinde_silinmez(panel, defterli, saat, uygulama):
    kayit(18, "10/A", 1, gec=["1047"])
    hucre(panel, "10/A", "2026-11-18", "1102", 1, "yok", basliklar=JSON)
    with vt.islem() as b:
        b.execute("INSERT INTO yoklama_mazeret (ogrenci_id, bas_tarih, bit_tarih, tur, dayanak, giren, olusturma) "
                  "VALUES (?, '2026-11-18', '2026-12-05', 'izinli', '', 'yonetici', 0)", (ogrenci_id("1150"),))  # fmt: skip
    # Üçü de listeden çıkıyor (pasif): yalnız geç, düzeltme ya da mazeret kaydı olan öğrenci yıl içinde silinmez.
    ogrenci_yukle(panel, "Şube;Okul No;Adı;Soyadı\n10/A;0215;Cemre;DOĞAN\n".encode())
    with vt.islem() as b:
        vt.ayar_yaz(b, "yoklama_imha_son_tur", 0)
    uygulama.state.yoklama_zamanlayici()
    assert {s["okul_no"] for s in sorgu("SELECT okul_no FROM ogrenci WHERE aktif = 0")} == {"1047", "1102", "1150"}
    # Öğretim yılı bitişi geçince üç tablo da boşalır (aralığı sınırı aşan mazeret de bütünüyle silinir).
    with vt.islem() as b:
        vt.ayar_yaz(b, "ogretim_yili_bitis", "2026-11-20")
        vt.ayar_yaz(b, "yoklama_imha_son_tur", 0)
    saat.ayarla(an(22, 9))
    assert uygulama.state.yoklama_zamanlayici() is True
    for tablo in ("yoklama", "yoklama_gec", "yoklama_duzeltme", "yoklama_mazeret"):
        assert sorgu(f"SELECT COUNT(*) AS n FROM {tablo}")[0]["n"] == 0, tablo
    assert sorgu("SELECT COUNT(*) AS n FROM ogrenci WHERE aktif = 0")[0]["n"] == 0
    assert "düzeltme/mazeret" in sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yoklama imhası'")[0]["ayrinti"]


def test_tumunu_sil_yeni_tablolari_da_bosaltir(panel, defterli):
    kayit(18, "10/A", 1, yok=["1047"], gec=["1102"])
    hucre(panel, "10/A", "2026-11-18", "1150", 1, "yok", basliklar=JSON)
    with vt.islem() as b:
        b.execute("INSERT INTO yoklama_mazeret (ogrenci_id, bas_tarih, bit_tarih, tur, dayanak, giren, olusturma) "
                  "VALUES (?, '2026-11-18', '2026-11-18', 'izinli', '', 'yonetici', 0)", (ogrenci_id("0215"),))  # fmt: skip
    yanit = panel.post("/ogrenciler/temizle", data={"onay": "SİL"})
    assert "t=hata" not in yanit.headers["location"], ileti(yanit)
    for tablo in ("ogrenci", "yoklama", "yoklama_yok", "yoklama_gec", "yoklama_duzeltme", "yoklama_mazeret"):
        assert sorgu(f"SELECT COUNT(*) AS n FROM {tablo}")[0]["n"] == 0, tablo


def test_yedek_geri_yukleme_yeni_tablolari_tasir(panel, defterli, hizli_kdf):  # noqa: F811
    from tahta_sunucu import ayar, guvenlik, yedek

    guvenlik.sertifika_hazirla(ayar.veri_dizini())  # yedek sertifikayı da taşır (testte Sunucu() çalışmaz)
    kayit(18, "10/A", 1, yok=["1047"], gec=["1102"])
    hucre(panel, "10/A", "2026-11-18", "1150", 1, "yok", basliklar=JSON)
    with vt.islem() as b:
        b.execute("INSERT INTO yoklama_mazeret (ogrenci_id, bas_tarih, bit_tarih, tur, dayanak, giren, olusturma) "
                  "VALUES (?, '2026-11-18', '2026-11-18', 'izinli', 'dilekce', 'yonetici', 0)", (ogrenci_id("0215"),))  # fmt: skip
    oncesi = {t: sorgu(f"SELECT * FROM {t}") for t in ("yoklama", "yoklama_gec", "yoklama_duzeltme", "yoklama_mazeret")}
    parola_belirle(panel)
    panel.post("/yedekler/al")
    _, veri = yedek_dosyasi()
    with vt.islem() as b:
        for tablo in ("yoklama_gec", "yoklama_duzeltme", "yoklama_mazeret"):
            b.execute(f"DELETE FROM {tablo}")
    yedek.bekleyeni_hazirla(veri, YEDEK_PAROLASI)
    yedek.bekleyeni_onayla()
    assert "Yedekten geri yüklendi" in yedek.bekleyeni_uygula()
    vt.hazirla()
    assert {t: sorgu(f"SELECT * FROM {t}") for t in oncesi} == oncesi


# ---- yetki ve şema ------------------------------------------------------------------------------------------------------
def test_yeni_sayfalar_oturumsuz_ve_tahta_kimligiyle_acilmaz_idareciye_aciktir(panel, tahta, defterli):
    kayit(18, "10/A", 1, yok=["1047"])
    oid = ogrenci_id("1047")
    getler = ["/yoklama/sube?sube=10/A", "/yoklama/sube?sube=10/A&tarih=2026-11-18", "/yoklama/son-gunler", "/yoklama/mazeret",
              f"/yoklama/ogrenci/{oid}"]  # fmt: skip
    postlar = ["/yoklama/sube/hucre", "/yoklama/sube/toplu", "/yoklama/mazeret/onizle", "/yoklama/mazeret/onayla", "/yoklama/mazeret/1/iptal"]
    kullanici_ekle(panel, "mudur_yrd", "idareci")
    gir(panel, "mudur_yrd")
    for adres in getler:
        assert panel.get(adres).status_code == 200, adres
    assert hucre(panel, "10/A", "2026-11-18", "1102", 1, "yok", basliklar=JSON).status_code == 200  # idareci düzeltebilir
    panel.cookies.clear()
    for adres in getler:
        yanit = panel.get(adres)
        assert yanit.status_code == 303 and yanit.headers["location"] == "/giris", adres
    for adres in postlar:
        yanit = panel.post(adres, data={"tarih": "2026-11-18", "sube": "10/A", "hucre": f"{oid}:1", "durum": "var", "eylem": "iptal"})
        assert yanit.status_code == 303 and yanit.headers["location"] == "/giris", adres
    oturumsuz_json = panel.post("/yoklama/sube/hucre", headers=JSON, data={"hucre": f"{oid}:1"})
    assert oturumsuz_json.status_code == 401
    for adres in getler:  # tahta anahtarı panel sayfası açmaz
        assert tahta.get(adres, headers=defterli["basliklar"], follow_redirects=False).status_code == 303, adres
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama_duzeltme")[0]["n"] == 1
    baska_kaynak = panel.post("/yoklama/sube/hucre", headers={"Origin": "http://kotu.example"}, data={})
    assert baska_kaynak.status_code == 403


def test_duzeltme_ve_mazeret_tablolari_kisitlari(panel, defterli):
    with vt.islem() as b:
        oid = b.execute("SELECT id FROM ogrenci LIMIT 1").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError):
            b.execute("INSERT INTO yoklama_duzeltme (tarih, sube, ders_no, ogrenci_id, durum, giren, zaman) VALUES ('2026-11-18', '10/A', 1, ?, 'tam', 'x', 0)", (oid,))
        with pytest.raises(sqlite3.IntegrityError):
            b.execute("INSERT INTO yoklama_mazeret (ogrenci_id, bas_tarih, bit_tarih, tur, dayanak, giren, olusturma) VALUES (?, '2026-11-18', '2026-11-18', 'hasta', '', 'x', 0)", (oid,))
        sutunlar = {s["name"] for s in b.execute("PRAGMA table_info(yoklama_mazeret)")}
    assert not sutunlar & {"aciklama", "not", "nott", "metin", "gerekce"}  # serbest metin sütunu yok
    assert yd.simge({"durum": "yok", "ozurlu": True}) == "Ö" and yd.simge({"durum": "alinmadi"}) == "–"
    assert yd.durum_metni({"durum": "var", "kapsam": True}) == "derste, özür kapsamında"


# ---- inceleme bulguları (18.11.2026): "en son işlem geçerli", yetim düzeltme, Alındı, okunaklılık -------------
def test_duzeltmeden_sonra_tahtadan_kaydedilen_yoklama_gecerlidir(panel, tahta, defterli, saat):
    """Öğretmen kaydetti → idare düzeltti → öğretmen listeyi yeniden açıp (düzeltmeyi görerek) kaydetti: en son kayıt
    geçerlidir; "Kaydedildi" deyip veriyi göstermemek olmaz. Düzeltme kendisinden ESKİ kayıtları ezmeyi sürdürür."""
    kayit(18, "10/A", 1, yok=["1047"], ogretmen_id=defterli["ogretmen_id"], zaman=int(an(18, 8, 30).timestamp()))
    # İdare: 1047'yi notla "var", 1102'yi "yok" yapar.
    assert hucre(panel, "10/A", "2026-11-18", "1047", 1, "var", "veli bildirdi, derste", JSON).json()["durum"] == "var"
    assert hucre(panel, "10/A", "2026-11-18", "1102", 1, "yok", basliklar=JSON).json()["durum"] == "yok"
    with vt.islem() as b:
        assert yk.gecerli_durum(b, "2026-11-18", "10/A", 1)[:2] == ({ogrenci_id("1102")}, set())
    # Öğretmen 10 dk sonra tahtadan: liste geçerli durumu gösterir; 1047 yeniden yok, 1102 var olarak kaydeder.
    saat.ilerlet(600)
    belirtec = baslat(tahta, defterli).json()["belirtec"]
    istek = {"belirtec": belirtec, "sube": "10/A", "ders_no": 1}
    liste = ajan(tahta, defterli["basliklar"], "liste", istek).json()
    assert liste["yok"] == [ogrenci_id("1102")]
    yanit = ajan(tahta, defterli["basliklar"], "kaydet", {**istek, "yok": [ogrenci_id("1047")]})
    assert yanit.status_code == 200 and yanit.json()["yok_sayisi"] == 1
    assert (durum_("10/A", "2026-11-18", "1047", 1), durum_("10/A", "2026-11-18", "1102", 1)) == ("yok", "var")
    with vt.islem() as b:
        assert yk.gecerli_durum(b, "2026-11-18", "10/A", 1)[:2] == ({ogrenci_id("1047")}, set())
        g = yd.sube_gunu(b, "10/A", date(2026, 11, 18), vt.simdi())
    satir = {s["okul_no"]: s for s in g["satirlar"]}
    assert not satir["1047"]["duzeltme_var"] and not satir["1102"]["duzeltme_var"]  # bayat düzeltme işaret de taşımaz
    assert g["sutunlar"][0]["yok_sayisi"] == 1
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama_duzeltme")[0]["n"] == 2  # iz satırları duruyor
    # Yeniden açılan listede öğretmen kendi kaydettiğini görür.
    istek["belirtec"] = baslat(tahta, defterli).json()["belirtec"]  # kaydedince oturum kapanır
    assert ajan(tahta, defterli["basliklar"], "liste", istek).json()["yok"] == [ogrenci_id("1047")]
    # Kayıttan SONRA yapılan düzeltme yine geçerlidir ve kaldırılınca kayıt geri görünür (ölçüt 11 bozulmadı).
    saat.ilerlet(120)
    assert hucre(panel, "10/A", "2026-11-18", "1102", 1, "yok", basliklar=JSON).json()["durum"] == "yok"
    assert hucre(panel, "10/A", "2026-11-18", "1102", 1, "yok", basliklar=JSON).json()["durum"] == "var"


def test_silinen_kaydin_duzeltmesi_yeniden_alinan_yoklamayi_ezmez(panel, defterli, saat):
    yid = kayit(18, "10/A", 1, zaman=int(an(18, 8, 30).timestamp()))
    kayit(18, "10/A", 2, zaman=int(an(18, 9, 30).timestamp()))
    hucre(panel, "10/A", "2026-11-18", "1047", 1, "yok", basliklar=JSON)
    hucre(panel, "10/A", "2026-11-18", "1047", 2, "yok", basliklar=JSON)
    sil = panel.post(f"/yoklama/kayit/{yid}", data={"eylem": "sil", "aciklama": "yanlış şubeye alınmış"})
    assert "t=hata" not in sil.headers["location"], ileti(sil)
    # Ders saatinin başka kaydı kalmadı: düzeltmesi de gitti; öbür ders saatinin düzeltmesi duruyor.
    assert [d["ders_no"] for d in sorgu("SELECT ders_no FROM yoklama_duzeltme")] == [2]
    assert durum_("10/A", "2026-11-18", "1047", 1) == "alinmadi"
    saat.ilerlet(3600)
    kayit(18, "10/A", 1, zaman=vt.simdi())  # yeniden alındı: herkes var
    assert durum_("10/A", "2026-11-18", "1047", 1) == "var" and durum_("10/A", "2026-11-18", "1047", 2) == "yok"
    # Tabloda yetim satır kalsa bile (eski sürüm, elle silme) birleşim kuralı kayıttan eski düzeltmeyi yok sayar.
    with vt.islem() as b:
        b.execute("INSERT INTO yoklama_duzeltme (tarih, sube, ders_no, ogrenci_id, durum, aciklama, giren, zaman) "
                  "VALUES ('2026-11-18', '10/A', 1, ?, 'yok', '', 'yonetici', ?)", (ogrenci_id("1102"), vt.simdi() - 1800))  # fmt: skip
    assert durum_("10/A", "2026-11-18", "1102", 1) == "var"
    with vt.islem() as b:
        assert yk.gecerli_durum(b, "2026-11-18", "10/A", 1)[:2] == (set(), set())


def test_alindi_gun_boyu_yok_olanlari_sessizce_derste_saymaz(panel, defterli):
    """Günün alınan bütün derslerinde yok olan öğrenci "Alındı (herkes var)" ile sessizce derste sayılmaz: onay
    sorusu sayıyı söyler ve (varsayılan işaretli) seçenekle bu derste de yok yazar; "N gündür" zinciri kırılmaz."""
    for gun in (16, 17, 18):
        kayit(gun, "10/A", 1, yok=["1047"])
    kayit(18, "10/A", 2, yok=["1047", "1102"])
    with vt.islem() as b:
        g = yd.sube_gunu(b, "10/A", date(2026, 11, 18), vt.simdi())
        assert g["gun_boyu_yok"] == 1 and yd.sube_defteri(b, "10/A", date(2026, 11, 18), vt.simdi())["satirlar"][1]["n"] == 3
    soru = panel.get("/yoklama/sube?sube=10/A&tarih=2026-11-18&alindi=3").text
    assert 'name="alindi_yoklar" value="1" checked' in soru and "yok yazılan 1 öğrenci" in soru
    govde = {"tarih": "2026-11-18", "sube": "10/A", "durum": "yok", "aciklama": ""}
    yanit = panel.post("/yoklama/sube/toplu", data={**govde, "alindi": "3", "alindi_yoklar": "1"})
    assert "yok yazılan 1 öğrenci bu derste de yok yazıldı" in ileti(yanit) and yanit.headers["location"].endswith("#ileti")
    assert (durum_("10/A", "2026-11-18", "1047", 3), durum_("10/A", "2026-11-18", "1102", 3)) == ("yok", "var")
    with vt.islem() as b:
        assert yd.sube_defteri(b, "10/A", date(2026, 11, 18), vt.simdi())["satirlar"][1]["n"] == 3  # rozet düşmedi
    # Seçenek kaldırılırsa eski davranış: herkes derste.
    panel.post("/yoklama/sube/toplu", data={**govde, "alindi": "4"})
    assert durum_("10/A", "2026-11-18", "1047", 4) == "var"
    kayit_metni = " ".join(k["ayrinti"] for k in sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yoklama girildi (panel)'"))
    assert "1047" not in kayit_metni and "Ayşe" not in kayit_metni


def test_gun_kipi_firca_seridi_temizle_dugmesi_ve_okunakli_simgeler(panel, defterli, saat):
    saat.ayarla(an(18, 9, 20))  # 3. ve 4. ders henüz başlamadı
    gir(panel, "yonetici")
    kayit(18, "10/A", 1, yok=["1047"], zaman=int(an(18, 8, 30).timestamp()))
    veri = hucre(panel, "10/A", "2026-11-18", "1047", 1, "var", "öğretmen bildirdi, geldi", JSON).json()
    # İdarenin "var" yaptığı hücre "·" + alt çizgi değil "V" görünür ("–" yoklama alınmadı ile karışmasın).
    assert (veri["durum"], veri["simge"], veri["satir_duzeltme"]) == ("var", "V", True)
    notsuz = hucre(panel, "10/A", "2026-11-18", "1047", 1, "yok", basliklar=JSON).json()  # aynı kayıt durumu: düzeltme kalkar
    assert notsuz["satir_duzeltme"] is False and notsuz["simge"] == "Y"
    red = hucre(panel, "10/A", "2026-11-18", "1047", 1, "var", basliklar=JSON)
    assert red.status_code == 400 and red.json()["not_gerek"] is True  # JS odağı not alanına götürür
    sayfa = panel.get("/yoklama/sube?sube=10/A&tarih=2026-11-18").text
    # Fırça tek satırlık yapışkan şerittir; ipuçları açılır kutuda; lejant tablonun altında; onay kutusu yok.
    assert 'class="firca-serit yazdirma"' in sayfa and "<details class=\"firca-yardim\">" in sayfa
    assert 'name="alindi_onay"' not in sayfa and sayfa.index("</table>") < sayfa.index('aria-label="Simgeler"')
    assert sayfa.index('class="firca-serit') < sayfa.index("Notu kaydet") < sayfa.index('name="hucre"')  # Enter notu kaydeder
    # "Temizle" her satırda çizilir; düzeltme yoksa gizlidir (JS yanıttaki satir_duzeltme ile açar).
    assert sayfa.count("data-temizle hidden") == sayfa.count("data-temizle") == 4
    # Bugünün henüz başlamamış dersi "–" (alınmadı) ile aynı görünmez.
    with vt.islem() as b:
        g = yd.sube_gunu(b, "10/A", date(2026, 11, 18), vt.simdi())
    h = g["satirlar"][0]["hucreler"]
    assert [(x["simge"], x["gelecek"]) for x in h] == [("·", False), ("–", False), ("", True), ("", True)]
    assert h[3]["etiket"].endswith("4. ders: henüz başlamadı") and "data-gelecek" in sayfa
    assert yd.simge({"durum": "var", "duzeltme": True}) == "V" and yd.simge({"durum": "var"}) == "·"


def test_mazeret_listesi_yazdirmada_tur_gizli_ileti_aralik_tasimaz(panel, defterli):
    with vt.islem() as b:
        b.execute("INSERT INTO yoklama_mazeret (ogrenci_id, bas_tarih, bit_tarih, tur, dayanak, giren, olusturma) "
                  "VALUES (?, '2026-11-17', '2026-11-19', 'raporlu', 'belge', 'yonetici', 0)", (ogrenci_id("1047"),))  # fmt: skip
    sayfa = panel.get("/yoklama/mazeret").text
    # Tür ve dayanak sütunları yazdırmada gizlidir (öğrenci görünümüyle aynı; "raporlu" kâğıda çıkmaz).
    assert '<th scope="col" class="yazdirma">Tür</th><th scope="col" class="yazdirma">Dayanak</th>' in sayfa
    assert '<td data-etiket="Tür" class="yazdirma">Raporlu</td>' in sayfa and '<td data-etiket="Dayanak" class="yazdirma">' in sayfa
    # Kaldırma onayı hangi kaydın kaldırılacağını söyler (No + tarih aralığı).
    assert 'data-onay="mazeret_kaldir" data-onay-ad="No 1047, 17.11.2026–19.11.2026"' in sayfa
    onizle = panel.post("/yoklama/mazeret/onizle", data={"nolar": "1102", "bas": "2026-11-18", "bit": "2026-11-19", "kapsam": "tam",
                                                          "tur": "izinli", "dayanak": ""})  # fmt: skip
    belirtec = re.search(r'name="onizleme" value="([^"]+)"', onizle.text).group(1)
    yanit = panel.post("/yoklama/mazeret/onayla", data={"onizleme": belirtec})
    assert ileti(yanit) == "Mazeret kaydedildi: 1 öğrenci." and "2026" not in yanit.headers["location"]


def test_defter_stili_tek_kaydirma_yatay_yazdirma_ve_ozet_hucresi():
    """Tarayıcıda görülen kusurların stil kuralları yerinde mi (18.11.2026 incelemesi; 1366x768 ve PDF ile denendi)."""
    from pathlib import Path

    import tahta_sunucu

    kok = Path(tahta_sunucu.__file__).parent
    css = (kok / "statik" / "stil.css").read_text(encoding="utf-8")
    js = (kok / "statik" / "panel.js").read_text(encoding="utf-8")
    # Geniş ekranda sığan tabloda iç kaydırma yok (iç içe iki dikey kaydırma çubuğu olmasın); fırça şeridi yapışkan.
    assert ".defter-kap.sigar { overflow: visible; max-block-size: none; }" in css and "max-block-size: 80vh" not in css
    assert re.search(r"\.firca-serit \{ position: sticky; inset-block-start: 0;", css)
    # Şube defteri yatay basılır: beş günün tamamı ve Y / G sütunu sayfaya girsin.
    assert "@page genis { size: A4 landscape;" in css and "body.genis-sayfa { page: genis; }" in css
    # Panonun genel .ozet kuralı (flex) defterin özet hücresini bozmasın (alt satır sayıları alt alta diziliyordu).
    assert ".defter .ozet { display: table-cell;" in css
    assert ".defter-bes td.ozet { position: sticky; inset-inline-end: 0;" in css
    # JS: satırın Temizle düğmesi yanıtla açılır, not gerektiren hatada odak not alanına gider, ok tuşlarıyla gezilir.
    for parca in ("v.satir_duzeltme", "hata.notGerek", "ArrowDown", 'data-onay-ad'):
        assert parca in js, parca
