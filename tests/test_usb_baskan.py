"""Sınıf başkanı USB anahtarı (0.21.0): şubeye bağlı anahtar, dar yetki, öğretmen önceliği, toplu üretim, göç.

Bütün veriler UYDURMADIR (öğrenci, öğretmen ve kullanıcı adları, anahtar dosyaları testte üretilir).
"""

# ruff: noqa: F811  (içe aktarılan fikstürler test parametresi olarak yeniden adlandırılır)
from __future__ import annotations

import io
import re
import sqlite3
import zipfile
from datetime import date

import pytest
from test_usb_anahtar import USB_DURUMU, usb, usb_ayar, usb_hazir  # noqa: F401
from test_yoklama import ajan, ayar_kaydet, baslat, ders_saatleri_yaz, hazir, ogrenci_id, tum_metin  # noqa: F401
from yardimci import an, bekle, gir, ileti, kullanici_ekle, sorgu, tahta_ekle

from tahta_sunucu import usb_anahtar as ua
from tahta_sunucu import vt
from tahta_sunucu import yoklama as yk

# Uydurma öğrencilerin (test_yoklama.OGRENCI_CSV) adları ve okul numaraları: işlem kaydında hiçbiri geçmemeli.
OGRENCI_IZLERI = ["Ayşe", "YILMAZ", "Burak", "KAYA", "YURT", "Cemre", "DOĞAN", "Deniz", "ÇELİK", "Ege", "TUNA",
                  "1047", "1102", "1150", "0215", "2001", "2002"]  # fmt: skip


def baskan_ayar(panel, pin: bool = False, **ek):
    """USB anahtar + başkan anahtarları açık; başkan PIN'i varsayılan KAPALI (testler PIN'i ayrıca açar)."""
    return usb_ayar(panel, ua_baskan="1", ua_pin_baskan="1" if pin else None, **ek)


def baskan_uret(panel, *subeler: str, etiket: str = ""):
    """Üretim yanıtı: (yanıt, indirme adresi|None, [düz PIN])."""
    yanit = panel.post("/usb-anahtarlar", data={"eylem": "uret", "sahip": "baskan", "sube": list(subeler), "etiket": etiket})
    if yanit.status_code != 200:
        return yanit, None, []
    adres = re.search(r'href="(/usb-anahtarlar/indir/[^"]+)"', yanit.text).group(1)
    return yanit, adres, ["".join(p) for p in re.findall(r'class="pusula-pin">(\d{3}) (\d{3})<', yanit.text)]


def baskan_anahtar(panel, sube: str = "10/A") -> tuple[dict, str]:
    yanit, adres, pinler = baskan_uret(panel, sube)
    assert adres, ileti(yanit)
    indirme = panel.get(adres)
    assert indirme.status_code == 200, ileti(indirme)
    return ua.dosya_coz(indirme.content), pinler[0]


@pytest.fixture()
def baskan_hazir(panel, tahta, usb_hazir, saat):
    """USB + başkan açık (PIN'siz), Pazartesi zil saatleri, saat 08:30 (1. ders sürüyor), 10/A anahtarı."""
    assert "t=hata" not in baskan_ayar(panel).headers["location"]
    ders_saatleri_yaz()
    saat.ayarla(an(16, 8, 30))
    anahtar, pin = baskan_anahtar(panel)
    return {**usb_hazir, "anahtar": anahtar, "baskan_pin": pin}


def oturum_ac(tahta, h, **ek):
    yanit = usb(tahta, h["basliklar"], "yoklama", h["anahtar"], **ek)
    assert yanit.status_code == 200, yanit.text
    return yanit.json()


def liste(tahta, h, belirtec, sube="10/A", ders_no=1):
    return ajan(tahta, h["basliklar"], "liste", {"belirtec": belirtec, "sube": sube, "ders_no": ders_no})


def kaydet(tahta, h, belirtec, yok=(), sube="10/A", ders_no=1):
    return ajan(tahta, h["basliklar"], "kaydet", {"belirtec": belirtec, "sube": sube, "ders_no": ders_no, "yok": list(yok)})


# ---- göç ---------------------------------------------------------------------------------------------------
def test_goc_eski_anahtarlari_korur_yeni_kisitlari_kurar(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    b = sqlite3.connect(tmp_path / "tahta-kontrol.db")
    onceki = next(i for i, g in enumerate(vt.GOCLER) if "CREATE TABLE usb_anahtar_yeni" in g)  # 0.20.0 şeması
    for sira in range(onceki):
        b.executescript(vt.GOCLER[sira])
    b.execute(f"PRAGMA user_version = {onceki}")
    b.execute("INSERT INTO tahta (id, ad, anahtar_ozet, kayit_zamani) VALUES (1, 'T', 'x', 0)")
    b.execute("INSERT INTO kullanici (id, ad, gorunen_ad, parola_ozet, rol, olusturma) VALUES (1, 'deneme', 'Deneme', 'x', 'yonetici', 0)")
    b.execute("INSERT INTO ogretmen (id, ad, soyad) VALUES (1, 'Uydurma', 'Öğretmen')")
    b.execute("INSERT INTO usb_anahtar (id, kimlik, gizli_ozet, sahip_turu, kullanici_id, etiket, pin_ozet, olusturan, olusturma, "
              "son_kullanim, son_tahta_id) VALUES (1, 'AAAAAAAA', 'o1', 'kullanici', 1, 'Mavi', 'p', 'deneme', 5, 7, 1)")  # fmt: skip
    b.execute("INSERT INTO usb_anahtar (id, kimlik, gizli_ozet, sahip_turu, ogretmen_id, olusturan, olusturma, durum, iptal_eden, "
              "iptal_zamani) VALUES (2, 'BBBBBBBB', 'o2', 'ogretmen', 1, 'deneme', 6, 'iptal', 'deneme', 9)")  # fmt: skip
    b.execute("INSERT INTO yoklama_belirtec (belirtec_ozet, kullanici_id, anahtar_id, tahta_id, bitis, olusturma) VALUES ('k', 1, 1, 1, 9, 0)")
    b.execute("INSERT INTO yoklama_belirtec (belirtec_ozet, ogretmen_id, tahta_id, bitis, olusturma) VALUES ('o', 1, 1, 9, 0)")
    b.commit()
    b.close()
    vt.hazirla()
    with vt.islem() as b:
        assert b.execute("PRAGMA user_version").fetchone()[0] == len(vt.GOCLER)
        assert b.execute("PRAGMA foreign_key_check").fetchall() == []
        satirlar = [dict(s) for s in b.execute("SELECT * FROM usb_anahtar ORDER BY id")]
        assert [(s["kimlik"], s["sahip_turu"], s["kullanici_id"], s["ogretmen_id"], s["sube"]) for s in satirlar] == [
            ("AAAAAAAA", "kullanici", 1, None, None), ("BBBBBBBB", "ogretmen", None, 1, None)]  # fmt: skip
        assert (satirlar[0]["etiket"], satirlar[0]["pin_ozet"], satirlar[0]["son_kullanim"], satirlar[0]["son_tahta_id"]) == ("Mavi", "p", 7, 1)
        assert (satirlar[1]["durum"], satirlar[1]["iptal_zamani"]) == ("iptal", 9)
        assert b.execute("SELECT COUNT(*) FROM yoklama_belirtec").fetchone()[0] == 0  # eski oturumlar göçte düştü
        dizinler = {s["name"] for s in b.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'usb_anahtar'")}
        assert {"usb_anahtar_kullanici", "usb_anahtar_ogretmen", "usb_anahtar_sube"} <= dizinler
        # Şube anahtarı: yalnız sube dolu
        b.execute("INSERT INTO usb_anahtar (id, kimlik, gizli_ozet, sahip_turu, sube, olusturan, olusturma) "
                  "VALUES (3, 'CCCCCCCC', 'o3', 'sube', '10/A', 'deneme', 0)")  # fmt: skip
        for sql in (
            "INSERT INTO usb_anahtar (kimlik, gizli_ozet, sahip_turu, kullanici_id, sube, olusturan, olusturma) VALUES ('D1', 'x', 'sube', 1, '10/A', 'd', 0)",
            "INSERT INTO usb_anahtar (kimlik, gizli_ozet, sahip_turu, olusturan, olusturma) VALUES ('D2', 'x', 'sube', 'd', 0)",
            "INSERT INTO usb_anahtar (kimlik, gizli_ozet, sahip_turu, sube, olusturan, olusturma) VALUES ('D3', 'x', 'sube', '', 'd', 0)",
            "INSERT INTO usb_anahtar (kimlik, gizli_ozet, sahip_turu, kullanici_id, sube, olusturan, olusturma) VALUES ('D4', 'x', 'kullanici', 1, '10/A', 'd', 0)",
            "INSERT INTO usb_anahtar (kimlik, gizli_ozet, sahip_turu, ogretmen_id, sube, olusturan, olusturma) VALUES ('D5', 'x', 'ogretmen', 1, '10/A', 'd', 0)",
        ):  # fmt: skip
            with pytest.raises(sqlite3.IntegrityError):
                b.execute(sql)
        # Başkan oturumu: öğretmen ve kullanıcı boş, anahtar dolu
        b.execute("INSERT INTO yoklama_belirtec (belirtec_ozet, anahtar_id, tahta_id, bitis, olusturma) VALUES ('b', 3, 1, 9, 0)")
        b.execute("INSERT INTO yoklama_belirtec (belirtec_ozet, kullanici_id, tahta_id, bitis, olusturma) VALUES ('i', 1, 1, 9, 0)")
        for sql in (
            "INSERT INTO yoklama_belirtec (belirtec_ozet, tahta_id, bitis, olusturma) VALUES ('y1', 1, 9, 0)",
            "INSERT INTO yoklama_belirtec (belirtec_ozet, ogretmen_id, kullanici_id, tahta_id, bitis, olusturma) VALUES ('y2', 1, 1, 1, 9, 0)",
        ):  # fmt: skip
            with pytest.raises(sqlite3.IntegrityError):
                b.execute(sql)
        b.execute("DELETE FROM usb_anahtar WHERE id = 3")  # CASCADE: başkan oturumu
        assert b.execute("SELECT COUNT(*) FROM yoklama_belirtec WHERE belirtec_ozet = 'b'").fetchone()[0] == 0


def test_oturum_ac_sahipsiz_oturum_acmaz(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    vt.hazirla()
    with vt.islem() as b, pytest.raises(ValueError):
        yk.oturum_ac(b, tahta_id=1, an=0, oturum_dk=8)


# ---- ayar ----------------------------------------------------------------------------------------------------
def test_ayar_varsayilan_kapali_ayni_formda_ve_ozet(panel, tahta, hazir):
    with vt.islem() as b:
        a = ua.ayar_al(b)
        assert (a["baskan"], a["pin_baskan"]) == (False, True)
    sayfa = panel.get("/ayarlar/usb").text
    form = re.search(r'<form method="post" action="/ayarlar"[^>]*>.*?</form>', sayfa, re.S).group(0)
    for alan in ("ua_etkin", "ua_kilit_acar", "ua_pin_idare", "ua_pin_ogretmen", "ua_baskan", "ua_pin_baskan"):
        assert f'name="{alan}"' in form  # onay kutusu tuzağı: altısı tek formda
    assert "Sınıf başkanı anahtarları (deneme)" in form and ua.BASKAN_NOTU in form
    baskan_ayar(panel, pin=True)
    with vt.islem() as b:
        assert ua.ayar_al(b)["baskan"] is True and ua.ayar_al(b)["pin_baskan"] is True
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'USB anahtar ayarı kaydedildi' ORDER BY id DESC")[0]["ayrinti"] == (
        "açık · kilit açar · sınıf başkanı · PIN: idare, başkan")
    assert bekle(tahta, hazir["basliklar"])["ayar"]["usb_anahtar"] == {"etkin": True}  # tahtaya yine yalnız açık/kapalı
    assert "Sınıf başkanı anahtarları (deneme): açık" in panel.get("/ayarlar/yoklama").text
    assert "sınıf başkanı" in panel.get("/ayarlar").text


# ---- üretim ve indirme -------------------------------------------------------------------------------------------
def test_tek_sube_uretimi_pusula_ve_duz_dosya(panel, tahta, usb_hazir):
    baskan_ayar(panel)
    yanit, adres, pinler = baskan_uret(panel, "10/A", etiket="Deneme")
    assert yanit.headers["cache-control"] == "no-store" and len(pinler) == 1
    assert "Şube: <strong>10/A</strong>" in yanit.text and "belleğin en üst klasörüne" in yanit.text
    assert sorgu("SELECT COUNT(*) AS n FROM usb_anahtar")[0]["n"] == 0  # indirilmeden yazılmaz
    indirme = panel.get(adres)
    assert indirme.headers["content-disposition"] == 'attachment; filename="tahta-kontrol.anahtar"'
    assert indirme.headers["cache-control"] == "no-store"
    satir = sorgu("SELECT * FROM usb_anahtar")[0]
    assert (satir["sahip_turu"], satir["sube"], satir["kullanici_id"], satir["ogretmen_id"]) == ("sube", "10/A", None, None)
    assert satir["pin_ozet"].startswith("scrypt$") and satir["etiket"] == "Deneme"
    assert pinler[0] not in tum_metin()
    kayitlar = [s["ayrinti"] for s in sorgu("SELECT ayrinti FROM kayit WHERE islem LIKE 'USB anahtar %'")]
    assert any("şube 10/A (başkan)" in k for k in kayitlar)


def test_toplu_uretim_tek_zip_ve_tek_seferlik(panel, tahta, usb_hazir):
    baskan_ayar(panel)
    yanit, adres, pinler = baskan_uret(panel, "10/A", "10/B")
    assert len(pinler) == 2 and "10-A" in yanit.text and "10-B" in yanit.text
    indirme = panel.get(adres)
    assert indirme.headers["content-type"] == "application/zip" and indirme.headers["cache-control"] == "no-store"
    assert indirme.headers["content-disposition"] == f'attachment; filename="{ua.PAKET_ADI}"'
    z = zipfile.ZipFile(io.BytesIO(indirme.content))
    assert sorted(z.namelist()) == ["10-A/tahta-kontrol.anahtar", "10-B/tahta-kontrol.anahtar", "OKUBENI.txt"]
    kimlikler = {ua.dosya_coz(z.read(ad))["kimlik"] for ad in z.namelist() if ad.endswith(".anahtar")}
    satirlar = sorgu("SELECT kimlik, sube FROM usb_anahtar ORDER BY sube")
    assert [s["sube"] for s in satirlar] == ["10/A", "10/B"] and {s["kimlik"] for s in satirlar} == kimlikler
    assert ileti(panel.get(adres)) == ua.ILETI_INDIRME_YOK


def test_klasor_adlari():
    assert ua.klasor_adi("10/A") == "10-A" and ua.klasor_adi("Hazırlık/B") == "Hazırlık-B"
    anahtarlar = [ua.Bekleyen("K", "G", "sube", None, None, "", "y", 1, "s", None, 0, "", sube=s) for s in ("10/A", "10/A", "9/İ")]
    assert ua.paket_klasorleri(anahtarlar) == ["10-A", "10-A-2", "9-İ"]


def test_sube_basina_en_cok_iki_bekleyenler_dahil(panel, tahta, usb_hazir):
    baskan_ayar(panel)
    baskan_anahtar(panel, "10/A")
    _, adres, _ = baskan_uret(panel, "10/A")  # indirilmedi: yine sayılır
    assert adres
    yanit, adres2, _ = baskan_uret(panel, "10/A", "10/B")
    assert adres2 is None and ileti(yanit) == ua.sinir_iletisi("10/A")
    assert "yer=baskan" in yanit.headers["location"]
    assert sorgu("SELECT COUNT(*) AS n FROM kayit WHERE islem = 'USB anahtar üretildi'")[0]["n"] == 2  # yarım üretim kaydı yok
    assert 'value="10/A" disabled' in panel.get("/usb-anahtarlar").text


def test_sube_listede_yoksa_ve_secimsiz_red(panel, tahta, usb_hazir):
    baskan_ayar(panel)
    yanit, adres, _ = baskan_uret(panel, "12/Z")
    assert adres is None and ileti(yanit) == "Şube öğrenci listesinde yok."
    yanit = panel.post("/usb-anahtarlar", data={"eylem": "uret", "sahip": "baskan"})
    assert ileti(yanit) == "En az bir şube seçin."


def test_etiket_tc_reddi(panel, tahta, usb_hazir):
    baskan_ayar(panel)
    yanit, adres, _ = baskan_uret(panel, "10/A", etiket="10000000146")
    assert adres is None and ileti(yanit) == ua.ILETI_ETIKET_TC


def test_idareci_uretemez_goremez_iptal_edemez(panel, tahta, usb_hazir):
    baskan_ayar(panel)
    dosya, _ = baskan_anahtar(panel)
    kimlik = ua.kimlik_bicimli(dosya["kimlik"])
    sayfa = panel.get("/usb-anahtarlar").text
    assert 'id="baskan"' in sayfa and "10/A sınıf başkanı" in sayfa and kimlik in sayfa
    kullanici_ekle(panel, "mdryrd")
    gir(panel, "mdryrd")
    sayfa = panel.get("/usb-anahtarlar").text
    assert 'id="baskan"' not in sayfa and "Sınıf başkanı anahtarları" not in sayfa and "sınıf başkanı" not in sayfa
    assert kimlik not in sayfa
    yanit, adres, _ = baskan_uret(panel, "10/B")
    assert adres is None and sorgu("SELECT COUNT(*) AS n FROM usb_anahtar")[0]["n"] == 1
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yetkisiz işlem reddedildi'")[0]["ayrinti"] == (
        "USB anahtar üretme (sınıf başkanı)")
    anahtar_id = sorgu("SELECT id FROM usb_anahtar")[0]["id"]
    panel.post("/usb-anahtarlar", data={"eylem": "iptal", "id": str(anahtar_id)})
    assert sorgu("SELECT durum FROM usb_anahtar")[0]["durum"] == "etkin"


# ---- tanıma, ayar, kilit, PIN ----------------------------------------------------------------------------------
def test_tani_yaniti_baskan_ve_kilit_izni_yok(panel, tahta, baskan_hazir):
    yanit = usb(tahta, baskan_hazir["basliklar"], "tani", baskan_hazir["anahtar"])
    assert yanit.status_code == 200
    assert yanit.json() == {"anahtar": {"tur": "baskan", "etiket": "Sınıf başkanı · 10/A", "kod": ""}, "pin_gerek": False,
                            "izinler": ["yoklama"], "omur_sn": ua.TANI_OMRU_SN}  # fmt: skip


def test_ayar_kapaliyken_tani_reddi_ve_ana_yoklama_kapaliyken_calismaz(panel, tahta, baskan_hazir):
    usb_ayar(panel)  # başkan kapalı
    yanit = usb(tahta, baskan_hazir["basliklar"], "tani", baskan_hazir["anahtar"])
    assert yanit.status_code == 409 and yanit.json()["neden"] == "baskan_kapali" and yanit.json()["hata"] == ua.ILETI_BASKAN_KAPALI
    assert "sınıf başkanı anahtarları kapalı" in sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Reddedilen USB anahtar'")[0]["ayrinti"]
    baskan_ayar(panel)
    ayar_kaydet(panel, yk_etkin=None)  # ders yoklaması kapalı
    yanit = usb(tahta, baskan_hazir["basliklar"], "yoklama", baskan_hazir["anahtar"])
    assert yanit.status_code == 409 and yanit.json()["neden"] == "yoklama_kapali"
    assert usb(tahta, baskan_hazir["basliklar"], "tani", baskan_hazir["anahtar"]).json()["izinler"] == []


def test_kilit_ac_reddedilir_pin_sayaci_tuketilmez(panel, tahta, baskan_hazir):
    baskan_ayar(panel, pin=True)
    yanit = usb(tahta, baskan_hazir["basliklar"], "kilit_ac", baskan_hazir["anahtar"], pin="000000")
    assert yanit.status_code == 403 and yanit.json() == {"hata": ua.ILETI_BASKAN_KILIT, "neden": "kilit_yetkisiz"}
    assert sorgu("SELECT hatali_sayi FROM usb_anahtar")[0]["hatali_sayi"] == 0
    assert "kilit açmaz" in sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Reddedilen USB anahtar'")[0]["ayrinti"]
    assert not sorgu("SELECT 1 FROM kayit WHERE islem = 'Kilit USB anahtarla açıldı'")


def test_pin_anahtarin_kendi_pini(panel, tahta, baskan_hazir):
    baskan_ayar(panel, pin=True)
    h = baskan_hazir
    assert usb(tahta, h["basliklar"], "tani", h["anahtar"]).json()["pin_gerek"] is True
    assert usb(tahta, h["basliklar"], "yoklama", h["anahtar"]).json()["neden"] == "pin_gerek"
    assert usb(tahta, h["basliklar"], "yoklama", h["anahtar"], pin="000000").json()["neden"] == "pin"
    assert sorgu("SELECT hatali_sayi FROM usb_anahtar")[0]["hatali_sayi"] == 1
    assert usb(tahta, h["basliklar"], "yoklama", h["anahtar"], pin=h["baskan_pin"]).status_code == 200


# ---- yoklama -------------------------------------------------------------------------------------------------------
def test_yoklama_akisi_kaynak_baskan_ve_islem_kaydi(panel, tahta, baskan_hazir):
    h = baskan_hazir
    oturum = oturum_ac(tahta, h)
    assert oturum["tur"] == "baskan" and oturum["ogretmen"] == {"kod": "", "etiket": "Sınıf başkanı · 10/A"}
    assert oturum["oneri"]["sube"] == "10/A" and oturum["oneri"]["ders_no"] == 1 and oturum["subeler_once"] == ["10/A"]
    yanit = liste(tahta, h, oturum["belirtec"])
    assert yanit.status_code == 200 and yanit.json()["baska_yoklama"] is False
    yok = ogrenci_id("1047")
    assert kaydet(tahta, h, oturum["belirtec"], [yok]).status_code == 200
    kayit = sorgu("SELECT * FROM yoklama")[0]
    assert (kayit["kaynak"], kayit["kaydeden"], kayit["ogretmen_id"], kayit["sube"]) == ("baskan", "baskan:10/A", None, "10/A")
    assert sorgu("SELECT kim FROM yoklama_iz")[0]["kim"].endswith(f"USB {h['anahtar']['kimlik']}")
    ayrinti = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yoklama alındı'")[0]["ayrinti"]
    assert ayrinti.startswith("10/A 1. ders, 1 yok, sınıf başkanı anahtarı · USB ")
    metin = " ".join(f"{s['kullanici']} {s['islem']} {s['ayrinti']}" for s in sorgu("SELECT * FROM kayit"))
    for iz in OGRENCI_IZLERI:
        assert iz not in metin, iz
    with vt.islem() as b:
        assert yk.gecerli_durum(b, "2026-11-16", "10/A", 1)[0] == {yok}


def test_baska_sube_400_secime_doner(panel, tahta, baskan_hazir):
    oturum = oturum_ac(tahta, baskan_hazir)
    yanit = liste(tahta, baskan_hazir, oturum["belirtec"], sube="10/B")
    assert yanit.status_code == 400 and yanit.json()["hata"] == "Bu anahtar yalnız 10/A için yoklama alır."
    assert kaydet(tahta, baskan_hazir, oturum["belirtec"], sube="10/B").status_code == 400
    assert not sorgu("SELECT 1 FROM yoklama")


def test_baska_tahta_409_derslik_programi_izin_verir(panel, tahta, baskan_hazir):
    h = baskan_hazir
    diger = tahta_ekle(panel, tahta, "10B Tahtası", durum=USB_DURUMU, subeler="10/B")
    bos = tahta_ekle(panel, tahta, "Lab", durum=USB_DURUMU)
    oturum = usb(tahta, diger, "yoklama", h["anahtar"]).json()
    yanit = ajan(tahta, diger, "liste", {"belirtec": oturum["belirtec"], "sube": "10/A", "ders_no": 1})
    assert yanit.status_code == 409 and yanit.json()["hata"] == "Bu tahta 10/A şubesinin dersliği değil."
    oturum2 = usb(tahta, bos, "yoklama", h["anahtar"]).json()
    yanit = ajan(tahta, bos, "liste", {"belirtec": oturum2["belirtec"], "sube": "10/A", "ders_no": 1})
    assert yanit.status_code == 409 and "şube atanmamış" in yanit.json()["hata"]
    # Derslik programı 10/A'yı bu ders saatinde Lab'a koyuyorsa izin verilir (başka ders saatinde değil).
    lab_id = sorgu("SELECT id FROM tahta WHERE ad = 'Lab'")[0]["id"]
    with vt.islem() as b:
        b.execute("INSERT INTO tahta_ders (tahta_id, gun, devre, ders_no, sube) VALUES (?, 0, 'normal', 1, '10/A')", (lab_id,))
    assert ajan(tahta, bos, "liste", {"belirtec": oturum2["belirtec"], "sube": "10/A", "ders_no": 1}).status_code == 200


def test_yalniz_su_anki_ders_penceresi(panel, tahta, baskan_hazir, saat):
    h = baskan_hazir
    saat.ayarla(an(16, 10, 20))  # 3. ders sürüyor
    oturum = oturum_ac(tahta, h)
    yanit = liste(tahta, h, oturum["belirtec"], ders_no=1)
    assert yanit.status_code == 400 and yanit.json()["hata"] == yk.ILETI_BASKAN_DERS
    assert liste(tahta, h, oturum["belirtec"], ders_no=3).status_code == 200
    saat.ayarla(an(16, 9, 55))  # teneffüs: biten 2. ders ve başlayacak 3. ders
    oturum = oturum_ac(tahta, h)
    assert liste(tahta, h, oturum["belirtec"], ders_no=2).status_code == 200
    assert liste(tahta, h, oturum["belirtec"], ders_no=3).status_code == 200
    assert liste(tahta, h, oturum["belirtec"], ders_no=1).status_code == 400


def test_zil_saati_yoksa_409(panel, tahta, baskan_hazir):
    with vt.islem() as b:
        b.execute("DELETE FROM ders_saati")
    oturum = oturum_ac(tahta, baskan_hazir)
    yanit = liste(tahta, baskan_hazir, oturum["belirtec"])
    assert yanit.status_code == 409 and yanit.json()["hata"] == yk.ILETI_BASKAN_ZIL_YOK


def test_ogretmen_kaydi_varken_baskan_yazamaz(panel, tahta, baskan_hazir):
    h = baskan_hazir
    ogr = baslat(tahta, h).json()["belirtec"]
    assert kaydet(tahta, h, ogr, [ogrenci_id("1102")]).status_code == 200
    oturum = oturum_ac(tahta, h)
    yanit = liste(tahta, h, oturum["belirtec"])
    assert yanit.status_code == 409 and yanit.json()["hata"] == yk.ILETI_BASKAN_OGRETMEN_ALDI
    assert kaydet(tahta, h, oturum["belirtec"]).status_code == 409
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama WHERE kaynak = 'baskan'")[0]["n"] == 0


def test_kaydet_aninda_yeniden_denetlenir(panel, tahta, baskan_hazir):
    h = baskan_hazir
    oturum = oturum_ac(tahta, h)
    assert liste(tahta, h, oturum["belirtec"]).status_code == 200
    ogr = baslat(tahta, h).json()["belirtec"]  # öğretmen bu arada kaydetti
    assert kaydet(tahta, h, ogr).status_code == 200
    yanit = kaydet(tahta, h, oturum["belirtec"], [ogrenci_id("1047")])
    assert yanit.status_code == 409 and yanit.json()["hata"] == yk.ILETI_BASKAN_OGRETMEN_ALDI


def test_baskan_kendi_kaydini_gunceller_ogretmen_sonra_gecerli(panel, tahta, baskan_hazir, saat):
    h = baskan_hazir
    a, b_ = ogrenci_id("1047"), ogrenci_id("1102")
    assert kaydet(tahta, h, oturum_ac(tahta, h)["belirtec"], [a]).status_code == 200
    saat.ilerlet(60)
    assert kaydet(tahta, h, oturum_ac(tahta, h)["belirtec"], [a, b_]).status_code == 200  # kendi kaydı güncellenir
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama")[0]["n"] == 1
    saat.ilerlet(60)
    ogr = baslat(tahta, h).json()["belirtec"]
    assert kaydet(tahta, h, ogr, [b_]).status_code == 200
    with vt.islem() as b:
        assert yk.gecerli_durum(b, "2026-11-16", "10/A", 1)[0] == {b_}  # kural 34: en son kaydedilen
    saat.ilerlet(60)
    assert liste(tahta, h, oturum_ac(tahta, h)["belirtec"]).status_code == 409


def test_idare_duzeltmesi_varsa_baskan_yazamaz(panel, tahta, baskan_hazir):
    h = baskan_hazir
    assert kaydet(tahta, h, oturum_ac(tahta, h)["belirtec"]).status_code == 200
    with vt.islem() as b:
        b.execute("INSERT INTO yoklama_duzeltme (tarih, sube, ders_no, ogrenci_id, durum, giren, zaman) "
                  "VALUES ('2026-11-16', '10/A', 1, ?, 'yok', 'deneme', ?)", (ogrenci_id("1047"), vt.simdi()))  # fmt: skip
    yanit = liste(tahta, h, oturum_ac(tahta, h)["belirtec"])
    assert yanit.status_code == 409 and yanit.json()["hata"] == yk.ILETI_BASKAN_IDARE_DUZELTTI


def test_ayar_kapatilinca_acik_oturum_aninda_duser(panel, tahta, baskan_hazir):
    h = baskan_hazir
    oturum = oturum_ac(tahta, h)
    usb_ayar(panel)  # başkan kapatıldı
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama_belirtec")[0]["n"] == 0
    assert liste(tahta, h, oturum["belirtec"]).status_code == 401
    # İkinci kat: ayar silme yolundan geçmeden kapansa da oturum geçersizdir.
    baskan_ayar(panel)
    oturum = oturum_ac(tahta, h)
    with vt.islem() as b:
        vt.ayar_yaz(b, ua.AYAR_ANAHTARI, {**ua.ayar_al(b), "baskan": False})
    assert liste(tahta, h, oturum["belirtec"]).status_code == 401


def test_iptal_oturumu_dusurur(panel, tahta, baskan_hazir):
    h = baskan_hazir
    oturum = oturum_ac(tahta, h)
    anahtar_id = sorgu("SELECT id FROM usb_anahtar")[0]["id"]
    panel.post("/usb-anahtarlar", data={"eylem": "iptal", "id": str(anahtar_id)})
    assert liste(tahta, h, oturum["belirtec"]).status_code == 401
    assert usb(tahta, h["basliklar"], "tani", h["anahtar"]).json()["neden"] == "iptal"


# ---- panel görünümü --------------------------------------------------------------------------------------------------
def test_panelde_sinif_baskani_olarak_gorunur(panel, tahta, baskan_hazir):
    h = baskan_hazir
    assert kaydet(tahta, h, oturum_ac(tahta, h)["belirtec"], [ogrenci_id("1047")]).status_code == 200
    kayit_id = sorgu("SELECT id FROM yoklama")[0]["id"]
    with vt.islem() as b:
        y = b.execute("SELECT *, NULL AS ogretmen_ad FROM yoklama").fetchone()
        assert yk.alan_etiketi(y) == "sınıf başkanı"
        ayrinti = yk.kayit_ayrintisi(b, kayit_id)
        assert ayrinti["kaynak"].startswith("tahta: 10A Tahtası · sınıf başkanı anahtarı") and ayrinti["baskan"] is True
    sayfa = panel.get(f"/yoklama/kayit/{kayit_id}").text
    assert "sınıf başkanı anahtarı" in sayfa and yk.BASKAN_NOTU in sayfa and "#s-acik" in sayfa
    assert "Alan: sınıf başkanı" in panel.get("/yoklama?tarih=2026-11-16").text
    icmal = panel.get("/yoklama/icmal?tarih=2026-11-16&sube=10/A").text
    assert "1. sınıf başkanı" in icmal and yk.BASKAN_NOTU in icmal
    gun = panel.get("/yoklama/sube?sube=10/A&tarih=2026-11-16").text
    assert "<sup>b</sup>" in gun and yk.BASKAN_NOTU in gun
    bes = panel.get("/yoklama/sube?sube=10/A").text
    assert "<sup>b</sup>" in bes and yk.BASKAN_NOTU in bes
    # Öğretmen kaydı ders saatinin geçerli kaydı olunca işaret kalkar.
    ogr = baslat(tahta, h).json()["belirtec"]
    kaydet(tahta, h, ogr)
    assert "<sup>b</sup>" not in panel.get("/yoklama/sube?sube=10/A&tarih=2026-11-16").text


def test_arama_dizininde_baskan_anahtari_yok(panel, tahta, baskan_hazir):
    _, adres, _ = baskan_uret(panel, "10/B", etiket="Zümrüt bellek")
    panel.get(adres)
    kimlikler = [ua.kimlik_bicimli(s["kimlik"]) for s in sorgu("SELECT kimlik FROM usb_anahtar")]
    for q in ("Zümrüt", "bellek", "başkan", "10/B", kimlikler[0], kimlikler[0].replace("-", "")):
        sonuclar = repr(panel.get("/api/ara", params={"q": q}).json()["sonuclar"])
        assert "Zümrüt" not in sonuclar and "anahtar ·" not in sonuclar
        for k in kimlikler:
            assert k not in sonuclar and k.replace("-", "") not in sonuclar
    # "başkan" yalnız ayar bölümünü (USB anahtar) bulur; anahtar ya da şube anahtarı satırı yoktur.
    yollar = {s["yol"] for s in panel.get("/api/ara", params={"q": "sınıf başkanı"}).json()["sonuclar"]}
    assert yollar and all(y.startswith("/ayarlar") for y in yollar)


# ---- yıl sonu --------------------------------------------------------------------------------------------------------
def test_yil_sonu_eski_yilin_baskan_anahtarlari_silinir(panel, tahta, baskan_hazir, saat, uygulama):
    h = baskan_hazir
    oturum_ac(tahta, h)
    with vt.islem() as b:
        vt.ayar_yaz(b, "ogretim_yili_bitis", "2026-11-16")
    saat.ayarla(an(17, 9))
    gir(panel, "yonetici")  # panel oturumu bir gün sonra düşmüş olabilir
    yeni, _ = baskan_anahtar(panel, "10/B")  # yeni yılda (bitiş tarihi güncellenmeden) üretildi
    assert uygulama.state.yoklama_zamanlayici() is True
    assert [s["kimlik"] for s in sorgu("SELECT kimlik FROM usb_anahtar")] == [yeni["kimlik"]]
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama_belirtec")[0]["n"] == 0
    assert "1 sınıf başkanı anahtarı silindi" in sorgu("SELECT ayrinti FROM kayit WHERE islem = 'USB anahtar yıl sonu temizliği'")[0]["ayrinti"]
    with vt.islem() as b:
        assert ua.yil_sonu(b, date(2026, 11, 16))["baskan"] == 0
