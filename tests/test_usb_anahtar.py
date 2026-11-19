"""USB anahtar (0.11.0): sunucu uçları, tek seferlik indirme, tanıma, PIN, yoklama, iptal, saklama.

Bütün veriler UYDURMADIR (ad, kod, anahtar dosyaları testte üretilir).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date

import pytest
from test_yoklama import ajan, ayar_kaydet, baslat, hazir, ogrenci_id, ogretmen_ekle, pin_uret, tum_metin  # noqa: F401
from yardimci import an, bekle, gir, ileti, kimlik, kullanici_ekle, sorgu, tahta_ekle, yeni_ajan_durumu

from tahta_sunucu import sinav, vt
from tahta_sunucu import usb_anahtar as ua
from tahta_sunucu import yoklama as yk

USB_DURUMU = yeni_ajan_durumu(yetenekler=["acil", "duyuru_id", "yoklama", "usb_anahtar"])


def usb_ayar(panel, **alanlar):
    form = {"bolum": "usb_anahtar", "ua_etkin": "1", "ua_kilit_acar": "1", "ua_pin_idare": "1"}
    form.update({k: v for k, v in alanlar.items()})
    return panel.post("/ayarlar", data={k: v for k, v in form.items() if v is not None})


def uret(panel, sahip: str = "kendim", ogretmen_id: int | None = None, etiket: str = "Mavi bellek"):
    """Üretim yanıtı: (yanıt, indirme adresi, düz PIN|None)."""
    veri = {"eylem": "uret", "sahip": sahip, "etiket": etiket}
    if ogretmen_id is not None:
        veri["ogretmen_id"] = str(ogretmen_id)
    yanit = panel.post("/usb-anahtarlar", data=veri)
    if yanit.status_code != 200:
        return yanit, None, None
    adres = re.search(r'href="(/usb-anahtarlar/indir/[^"]+)"', yanit.text).group(1)
    pin = re.search(r'class="pusula-pin">(\d{3}) (\d{3})<', yanit.text)
    return yanit, adres, pin.expand(r"\1\2") if pin else None


def anahtar_al(panel, sahip: str = "kendim", ogretmen_id: int | None = None) -> tuple[dict, str | None]:
    """Üretir ve indirir: (ayrıştırılmış dosya, PIN|None)."""
    yanit, adres, pin = uret(panel, sahip, ogretmen_id)
    assert adres, ileti(yanit)
    indirme = panel.get(adres)
    assert indirme.status_code == 200, ileti(indirme)
    return ua.dosya_coz(indirme.content), pin


def usb(tahta, basliklar, uc: str, anahtar: dict, **ek):
    return tahta.post(f"/ajan/usb/{uc}", headers=basliklar, json={"kimlik": anahtar["kimlik"], "gizli": anahtar["gizli"], **ek})


@pytest.fixture()
def usb_hazir(panel, tahta, hazir):  # noqa: F811
    assert "t=hata" not in usb_ayar(panel).headers["location"]
    bekle(tahta, hazir["basliklar"], USB_DURUMU)
    return hazir


def liste_ve_kaydet(tahta, basliklar, belirtec: str, yok: list[int] | None = None, ders_no: int = 1):
    liste = ajan(tahta, basliklar, "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": ders_no})
    assert liste.status_code == 200, liste.text
    return ajan(tahta, basliklar, "kaydet", {"belirtec": belirtec, "sube": "10/A", "ders_no": ders_no, "yok": yok or []})


# ---- göç ve ayar ---------------------------------------------------------------------------------------
def test_usb_goc_tablolari_ve_belirtec_yeniden_kurulur(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    b = sqlite3.connect(tmp_path / "tahta-kontrol.db")
    # Yeni göçler eklense de bu test USB göçünün HEMEN öncesinden yükseltir.
    onceki = next(i for i, sql in enumerate(vt.GOCLER) if "CREATE TABLE usb_anahtar" in sql)
    for sira in range(onceki):
        b.executescript(vt.GOCLER[sira])
    b.execute(f"PRAGMA user_version = {onceki}")
    b.execute("INSERT INTO tahta (id, ad, anahtar_ozet, kayit_zamani) VALUES (1, 'T', 'x', 0)")
    b.execute("INSERT INTO ogretmen (id, ad, soyad) VALUES (1, 'Deneme', 'Öğretmen')")
    b.execute("INSERT INTO yoklama_belirtec (belirtec_ozet, ogretmen_id, tahta_id, bitis, olusturma) VALUES ('o', 1, 1, 9, 0)")
    b.commit()
    b.close()
    vt.hazirla()
    with vt.islem() as b:
        assert b.execute("PRAGMA user_version").fetchone()[0] == len(vt.GOCLER)
        assert b.execute("SELECT COUNT(*) FROM yoklama_belirtec").fetchone()[0] == 0  # eski oturum göçte düştü
        assert b.execute("SELECT COUNT(*) FROM usb_anahtar").fetchone()[0] == 0
        sutunlar = {s["name"] for s in b.execute("PRAGMA table_info(yoklama_belirtec)")}
        assert {"kullanici_id", "anahtar_id"} <= sutunlar
        with pytest.raises(sqlite3.IntegrityError):  # öğretmen ve kullanıcı birlikte boş olamaz
            b.execute("INSERT INTO yoklama_belirtec (belirtec_ozet, tahta_id, bitis, olusturma) VALUES ('y', 1, 9, 0)")
        with pytest.raises(sqlite3.IntegrityError):
            b.execute("INSERT INTO usb_anahtar (kimlik, gizli_ozet, sahip_turu, ogretmen_id, olusturan, olusturma) "
                      "VALUES ('AAAAAAAA', 'x', 'kullanici', 1, 'y', 0)")  # fmt: skip


def test_usb_ayar_varsayilan_kapali_ve_ajana_yalniz_etkin_iner(panel, tahta, hazir):  # noqa: F811
    with vt.islem() as b:
        assert ua.ayar_al(b) == {"etkin": False, "kilit_acar": True, "pin_idare": True, "pin_ogretmen": False}
    assert bekle(tahta, hazir["basliklar"])["ayar"]["usb_anahtar"] == {"etkin": False}
    yanit = usb_ayar(panel, ua_pin_ogretmen="1")
    assert "USB anahtar ayarı kaydedildi" in ileti(yanit)
    assert bekle(tahta, hazir["basliklar"])["ayar"]["usb_anahtar"] == {"etkin": True}
    with vt.islem() as b:
        assert ua.ayar_al(b)["pin_ogretmen"] is True
        assert vt.ayar_al(b, "yoklama")["etkin"] is True  # bölüm yalnız kendi anahtarını yazar
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'USB anahtar ayarı kaydedildi'")[0]["ayrinti"] == (
        "açık · kilit açar · PIN: idare, öğretmen"
    )
    assert panel.get("/ayarlar/usb").status_code == 200


def test_usb_ayar_yalniz_yonetici(panel, tahta, hazir):  # noqa: F811
    kullanici_ekle(panel, "mdryrd")
    gir(panel, "mdryrd")
    yanit = usb_ayar(panel)
    with vt.islem() as b:
        assert ua.ayar_al(b)["etkin"] is False
    assert yanit.status_code in (303, 403)


# ---- üretim ve indirme ----------------------------------------------------------------------------------
def test_usb_uretim_satiri_indirmeden_once_yazilmaz(panel, tahta, usb_hazir):
    yanit, adres, pin = uret(panel)
    assert yanit.headers["cache-control"] == "no-store"
    assert pin and len(pin) == 6
    assert sorgu("SELECT COUNT(*) AS n FROM usb_anahtar")[0]["n"] == 0
    indirme = panel.get(adres)
    assert indirme.headers["content-disposition"] == 'attachment; filename="tahta-kontrol.anahtar"'
    assert indirme.headers["cache-control"] == "no-store"
    assert indirme.headers["content-type"] == "application/octet-stream"
    satir = sorgu("SELECT * FROM usb_anahtar")[0]
    assert satir["sahip_turu"] == "kullanici" and satir["pin_ozet"].startswith("scrypt$") and satir["durum"] == "etkin"
    assert pin not in tum_metin()


def test_usb_indirme_tek_seferlik_ve_bes_dakika(panel, tahta, usb_hazir, saat):
    _, adres, _ = uret(panel)
    assert panel.get(adres).status_code == 200
    ikinci = panel.get(adres)
    assert ileti(ikinci) == ua.ILETI_INDIRME_YOK
    _, adres, _ = uret(panel)
    saat.ilerlet(ua.BEKLEYEN_OMRU_SN + 1)
    assert ileti(panel.get(adres)) == ua.ILETI_INDIRME_YOK
    assert sorgu("SELECT COUNT(*) AS n FROM usb_anahtar")[0]["n"] == 1
    kayit = sorgu("SELECT * FROM kayit WHERE islem = 'USB anahtar indirilmedi'")
    assert len(kayit) == 1 and "5 dk içinde indirilmedi; kaydedilmedi" in kayit[0]["ayrinti"]


def test_usb_bekleyen_zamanlayicida_temizlenir(panel, tahta, usb_hazir, saat, uygulama):
    uret(panel)
    saat.ilerlet(ua.BEKLEYEN_OMRU_SN + 1)
    assert ("usb_bekleyen", uygulama.state.usb_bekleyen_temizle) in uygulama.state.zamanlayicilar
    assert uygulama.state.usb_bekleyen_temizle() == 1
    assert uygulama.state.usb_bekleyen.kayitlar == {}


def test_usb_indirme_yalniz_ureten_oturuma(panel, tahta, usb_hazir):
    kullanici_ekle(panel, "mdryrd")
    _, adres, _ = uret(panel)
    gir(panel, "mdryrd")
    assert ileti(panel.get(adres)) == ua.ILETI_INDIRME_YOK
    gir(panel, "yonetici")
    assert panel.get(adres).status_code == 200


def test_usb_dosya_bicimi_ascii_kisi_verisi_icermez(panel, tahta, usb_hazir):
    _, adres, _ = uret(panel)
    veri = panel.get(adres).content
    assert len(veri) <= ua.DOSYA_EN_BUYUK
    veri.decode("ascii")
    metin_ = veri.decode("ascii")
    for yasak in ("yonetici", "Yonetici", "Deneme", "Örnek", "Ornek", "Lisesi", "Ayşe", hazir_kod(usb_hazir)):
        assert yasak not in metin_
    cozulen = ua.dosya_coz(veri)
    assert cozulen["sunucu"] == ("ab" * 32)[:16]
    assert len(cozulen["gizli"]) == 52 and len(cozulen["kimlik"]) == 8
    assert metin_.splitlines()[2] == "TAHTA-KONTROL-ANAHTAR"


def hazir_kod(h) -> str:
    return f"kod={h['kod']}"


def test_usb_sunucuda_yalniz_ozet_saklanir(panel, tahta, usb_hazir):
    anahtar, _ = anahtar_al(panel)
    dokum = tum_metin()
    assert anahtar["gizli"] not in dokum and anahtar["gizli"].lower() not in dokum
    assert ua.gizli_ozeti(anahtar["gizli"]) in dokum


def test_usb_kisi_basi_en_cok_iki_etkin(panel, tahta, usb_hazir):
    anahtar_al(panel)
    anahtar_al(panel)
    yanit, adres, _ = uret(panel)
    assert adres is None and ileti(yanit) == ua.ILETI_SINIR
    # Aynı anda üretilen iki bekleyen: indirme anında sınır yeniden denetlenir.
    panel.post("/usb-anahtarlar", data={"eylem": "iptal", "id": str(sorgu("SELECT id FROM usb_anahtar")[0]["id"])})
    _, adres1, _ = uret(panel)
    _, adres2, _ = uret(panel)
    assert panel.get(adres1).status_code == 200
    assert ileti(panel.get(adres2)) == ua.ILETI_SINIR
    # Öğretmen için de kişi başı iki.
    anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    yanit, adres, _ = uret(panel, "ogretmen", usb_hazir["ogretmen_id"])
    assert adres is None and ileti(yanit) == ua.ILETI_SINIR


def test_usb_ogretmen_anahtarinda_pin_gosterilmez(panel, tahta, usb_hazir):
    yanit, adres, pin = uret(panel, "ogretmen", usb_hazir["ogretmen_id"])
    assert adres and pin is None
    assert "kendi yoklama PIN" in yanit.text
    panel.get(adres)
    assert sorgu("SELECT pin_ozet, sahip_turu FROM usb_anahtar")[0] == {"pin_ozet": None, "sahip_turu": "ogretmen"}


def test_usb_idareci_ogretmen_anahtari_uretemez(panel, tahta, usb_hazir):
    kullanici_ekle(panel, "mdryrd")
    gir(panel, "mdryrd")
    yanit, adres, _ = uret(panel, "ogretmen", usb_hazir["ogretmen_id"])
    assert adres is None and "yönetici yetkisi" in ileti(yanit)
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yetkisiz işlem reddedildi'")[-1]["ayrinti"] == "USB anahtar üretme (öğretmen)"
    # Kendi anahtarını üretebilir; sayfada yalnız kendininkiler görünür.
    anahtar_al(panel)
    sayfa = panel.get("/usb-anahtarlar")
    assert sayfa.status_code == 200 and 'name="ogretmen_id"' not in sayfa.text


def test_usb_idareci_baskasinin_anahtarini_iptal_edemez(panel, tahta, usb_hazir):
    yonetici_dosyasi, _ = anahtar_al(panel)
    yonetici_anahtari = sorgu("SELECT id FROM usb_anahtar")[0]["id"]
    kullanici_ekle(panel, "mdryrd")
    gir(panel, "mdryrd")
    yanit = panel.post("/usb-anahtarlar", data={"eylem": "iptal", "id": str(yonetici_anahtari)})
    assert "yönetici yetkisi" in ileti(yanit)
    assert sorgu("SELECT durum FROM usb_anahtar WHERE id = ?", yonetici_anahtari)[0]["durum"] == "etkin"
    assert ua.kimlik_bicimli(yonetici_dosyasi["kimlik"]) not in panel.get("/usb-anahtarlar").text  # başkasınınki listede yok
    anahtar_al(panel)
    kendi = sorgu("SELECT id FROM usb_anahtar WHERE kullanici_id != 1")[0]["id"]
    assert "iptal edildi" in ileti(panel.post("/usb-anahtarlar", data={"eylem": "iptal", "id": str(kendi)}))
    # Yönetici herkesinkini iptal eder.
    gir(panel, "yonetici")
    assert "iptal edildi" in ileti(panel.post("/usb-anahtarlar", data={"eylem": "iptal", "id": str(yonetici_anahtari)}))


# ---- tanıma -------------------------------------------------------------------------------------------
def test_usb_tani_gecersiz_ve_bilinmeyen_ayni_yanit(panel, tahta, usb_hazir):
    anahtar, _ = anahtar_al(panel)
    h = usb_hazir["basliklar"]
    yanlis = usb(tahta, h, "tani", {**anahtar, "gizli": ua.gizli_uret()})
    bilinmeyen = usb(tahta, h, "tani", {**anahtar, "kimlik": "ZZZZ2222"})
    bicimsiz = usb(tahta, h, "tani", {"kimlik": "x", "gizli": "y"})
    assert yanlis.status_code == bilinmeyen.status_code == bicimsiz.status_code == 403
    assert yanlis.json() == bilinmeyen.json() == bicimsiz.json() == {"hata": ua.ILETI_GECERSIZ, "neden": "gecersiz"}
    ayrintilar = [s["ayrinti"] for s in sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Geçersiz USB anahtar'")]
    assert ayrintilar == [f"kimlik {ua.kimlik_bicimli(anahtar['kimlik'])}", "kimlik ZZZZ-2222", "kimlik biçimsiz"]


def test_usb_tani_iptal_ayri_ileti(panel, tahta, usb_hazir):
    anahtar, _ = anahtar_al(panel)
    panel.post("/usb-anahtarlar", data={"eylem": "iptal", "id": str(sorgu("SELECT id FROM usb_anahtar")[0]["id"])})
    yanit = usb(tahta, usb_hazir["basliklar"], "tani", anahtar)
    assert yanit.status_code == 410 and yanit.json() == {"hata": ua.ILETI_IPTAL, "neden": "iptal"}
    # Yalnız kimliği bilen (gizli yanlış) iptal bilgisini alamaz.
    assert usb(tahta, usb_hazir["basliklar"], "tani", {**anahtar, "gizli": ua.gizli_uret()}).status_code == 403


def test_usb_tani_yaniti_yalniz_rol_etiket_kod(panel, tahta, usb_hazir):
    idare, _ = anahtar_al(panel)
    ogretmen, _ = anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    h = usb_hazir["basliklar"]
    yanit = usb(tahta, h, "tani", idare).json()
    assert yanit == {"anahtar": {"tur": "idare", "etiket": "İdare · D. Yönetici", "kod": ""}, "pin_gerek": True,
                     "izinler": ["yoklama", "kilit_ac"], "omur_sn": ua.TANI_OMRU_SN}  # fmt: skip
    yanit = usb(tahta, h, "tani", ogretmen).json()
    assert yanit["anahtar"] == {"tur": "ogretmen", "etiket": "A. Örnek", "kod": usb_hazir["kod"]}
    assert yanit["pin_gerek"] is False
    metin_ = str(yanit) + str(usb(tahta, h, "tani", idare).json())
    for yasak in (idare["kimlik"], ogretmen["kimlik"], "yonetici", "Deneme Yönetici", "Ayşe", "kullanici_id", "ogretmen_id"):
        assert yasak not in metin_
    # Kendiliğinden yapılan başarılı tanıma işlem kaydında konum geçmişi biriktirmez (§7): yalnız son kullanım.
    assert sorgu("SELECT COUNT(*) AS n FROM kayit WHERE islem = 'USB anahtar tanındı'")[0]["n"] == 0
    assert sorgu("SELECT son_tahta_id FROM usb_anahtar")[0]["son_tahta_id"] == kimlik(h)


def test_usb_tanima_kayda_konum_yazmaz_islem_yazar(panel, tahta, usb_hazir):
    anahtar, _ = anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    h = usb_hazir["basliklar"]
    onceki = sorgu("SELECT COALESCE(MAX(id), 0) AS n FROM kayit")[0]["n"]
    for _ in range(3):
        assert usb(tahta, h, "tani", anahtar).status_code == 200
    assert sorgu("SELECT COUNT(*) AS n FROM kayit WHERE id > ?", onceki)[0]["n"] == 0
    assert usb(tahta, h, "yoklama", anahtar).status_code == 200  # kullanıcının işlemi kayda düşer
    satirlar = sorgu("SELECT islem FROM kayit WHERE id > ?", onceki)
    assert [s["islem"] for s in satirlar] == ["Yoklama oturumu açıldı (USB anahtar)"]


def test_usb_idare_etiketi_kullanici_adini_tahtaya_indirmez(panel, tahta, usb_hazir):
    # Görünen ad boş bırakılınca kullanıcı adıyla doldurulur; tahtaya yine de yalnız "İdare" iner.
    assert ua.idare_etiketi("mdryrd", "mdryrd") == "İdare"
    assert ua.idare_etiketi("MdrYrd ", "mdryrd") == "İdare"
    assert ua.idare_etiketi("", "mdryrd") == "İdare"
    assert ua.idare_etiketi("Müdür", "mdryrd") == "İdare"
    assert ua.idare_etiketi("Ali Demir", "mdryrd") == "İdare · A. Demir"
    with vt.islem() as b:
        b.execute("UPDATE kullanici SET gorunen_ad = ad WHERE ad = 'yonetici'")
    idare, _ = anahtar_al(panel)
    yanit = usb(tahta, usb_hazir["basliklar"], "tani", idare).json()
    assert yanit["anahtar"] == {"tur": "idare", "etiket": "İdare", "kod": ""}
    assert "yonetici" not in str(yanit)


def test_usb_izinler_ayara_gore(panel, tahta, usb_hazir):
    anahtar, _ = anahtar_al(panel)
    usb_ayar(panel, ua_kilit_acar=None)
    ayar_kaydet(panel, yk_etkin=None)
    assert usb(tahta, usb_hazir["basliklar"], "tani", anahtar).json()["izinler"] == []


def test_usb_kapaliyken_ajan_uclari_409(panel, tahta, usb_hazir):
    anahtar, _ = anahtar_al(panel)
    usb_ayar(panel, ua_etkin=None)
    for uc in ("tani", "yoklama", "kilit_ac"):
        yanit = usb(tahta, usb_hazir["basliklar"], uc, anahtar, pin="000000")
        assert yanit.status_code == 409 and yanit.json() == {"hata": ua.ILETI_KAPALI, "neden": "kapali"}


def test_usb_sinav_penceresinde_409(panel, tahta, usb_hazir, monkeypatch):
    anahtar, _ = anahtar_al(panel)
    monkeypatch.setattr(sinav, "tahta_sinav_penceresinde", lambda *a, **k: True)
    for uc in ("tani", "yoklama", "kilit_ac"):
        yanit = usb(tahta, usb_hazir["basliklar"], uc, anahtar)
        assert yanit.status_code == 409 and yanit.json()["neden"] == "sinav"


def test_usb_onaysiz_tahta_ve_buyuk_govde(panel, tahta, usb_hazir):
    assert tahta.post("/ajan/usb/tani", json={}).status_code == 401
    yanit = tahta.post("/ajan/usb/tani", headers=usb_hazir["basliklar"], content=b"{" + b" " * 5000 + b"}")
    assert yanit.status_code == 413


def test_usb_gecersiz_anahtar_hiz_siniri_tahtayi_kapatir(panel, tahta, usb_hazir, saat):
    anahtar, _ = anahtar_al(panel)
    h = usb_hazir["basliklar"]
    for _ in range(ua.GECERSIZ_ADET - 1):
        assert usb(tahta, h, "tani", {**anahtar, "gizli": ua.gizli_uret()}).status_code == 403
    yanit = usb(tahta, h, "tani", {**anahtar, "gizli": ua.gizli_uret()})
    assert yanit.status_code == 429 and yanit.json()["hata"] == ua.ILETI_TAHTA_KAPALI
    assert usb(tahta, h, "tani", anahtar).status_code == 429  # doğru anahtar da 10 dk bekler
    saat.ilerlet(ua.GECERSIZ_KAPALI_SN + 1)
    assert usb(tahta, h, "tani", anahtar).status_code == 200


def test_usb_istek_siniri(panel, tahta, usb_hazir):
    anahtar, _ = anahtar_al(panel)
    for _ in range(ua.ISTEK_ADET):
        assert usb(tahta, usb_hazir["basliklar"], "tani", anahtar).status_code == 200
    yanit = usb(tahta, usb_hazir["basliklar"], "tani", anahtar)
    assert yanit.status_code == 429 and yanit.json()["neden"] == "cok_istek"


# ---- PIN ------------------------------------------------------------------------------------------------
def test_usb_ogretmen_anahtari_pin_ogretmen_pinidir_ve_sayaci_paylasir(panel, tahta, usb_hazir):
    usb_ayar(panel, ua_pin_ogretmen="1")
    anahtar, _ = anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    h = usb_hazir["basliklar"]
    yanlis = "000000" if usb_hazir["pin"] != "000000" else "111111"
    assert usb(tahta, h, "tani", anahtar).json()["pin_gerek"] is True
    yanit = usb(tahta, h, "yoklama", anahtar)
    assert yanit.status_code == 403 and yanit.json()["neden"] == "pin_gerek"
    for _ in range(2):
        yanit = usb(tahta, h, "yoklama", anahtar, pin=yanlis)
        assert yanit.status_code == 403 and yanit.json() == {"hata": ua.ILETI_PIN_HATALI, "neden": "pin", "bekleme_sn": 0}
    # Üçüncü ardışık hata kod + PIN yolundan gelir: aynı (tahta, öğretmen kodu) çifti bekletilir.
    assert baslat(tahta, usb_hazir, pin=yanlis).status_code == 429
    assert sorgu("SELECT hatali_sayi FROM ogretmen_pin")[0]["hatali_sayi"] == 3
    assert usb(tahta, h, "yoklama", anahtar, pin=usb_hazir["pin"]).status_code == 429


def test_usb_ogretmen_pini_dogruysa_oturum_acilir(panel, tahta, usb_hazir):
    usb_ayar(panel, ua_pin_ogretmen="1")
    anahtar, _ = anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    yanit = usb(tahta, usb_hazir["basliklar"], "yoklama", anahtar, pin=usb_hazir["pin"])
    assert yanit.status_code == 200 and yanit.json()["ogretmen"] == {"kod": usb_hazir["kod"], "etiket": "A. Örnek"}


def test_usb_idare_pin_on_hata_anahtari_kilitler(panel, tahta, usb_hazir, saat):
    anahtar, pin = anahtar_al(panel)
    h = usb_hazir["basliklar"]
    yanlis = "000000" if pin != "000000" else "111111"
    ilk = usb(tahta, h, "yoklama", anahtar, pin=pin)
    assert ilk.status_code == 200
    belirtec = ilk.json()["belirtec"]
    for sira in range(ua.PIN_HATA_ADET):
        saat.ilerlet(ua.GECERSIZ_KAPALI_SN + 1)  # tahta ve çift bekletmeleri geçsin; 24 saatlik sayaç sürer
        yanit = usb(tahta, h, "kilit_ac", anahtar, pin=yanlis)
        if sira < ua.PIN_HATA_ADET - 1:
            assert yanit.status_code in (403, 429), yanit.text
    assert yanit.status_code == 423 and yanit.json()["hata"] == ua.ILETI_KILITLI
    assert sorgu("SELECT durum FROM usb_anahtar")[0]["durum"] == "kilitli"
    assert usb(tahta, h, "tani", anahtar).status_code == 423
    assert usb(tahta, h, "yoklama", anahtar, pin=pin).status_code == 423
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama_belirtec")[0]["n"] == 0  # açık oturum düştü
    assert ajan(tahta, h, "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1}).status_code == 401
    assert sorgu("SELECT kullanici FROM kayit WHERE islem = 'USB anahtar kilitlendi'")[0]["kullanici"] == "tahta:10A Tahtası"


def test_usb_pin_ayari_kapaliyken_pin_sorulmaz(panel, tahta, usb_hazir):
    idare, _ = anahtar_al(panel)
    ogretmen, _ = anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    h = usb_hazir["basliklar"]
    assert usb(tahta, h, "yoklama", idare).json()["neden"] == "pin_gerek"
    assert usb(tahta, h, "yoklama", ogretmen).status_code == 200  # öğretmende varsayılan PIN yok
    usb_ayar(panel, ua_pin_idare=None)
    assert usb(tahta, h, "yoklama", idare).status_code == 200
    assert usb(tahta, h, "kilit_ac", idare).json() == {"tamam": True}
    usb_ayar(panel, ua_pin_idare=None, ua_pin_ogretmen="1")
    assert usb(tahta, h, "kilit_ac", ogretmen).json()["neden"] == "pin_gerek"


# ---- yoklama -------------------------------------------------------------------------------------------
def test_usb_yoklama_idare_kaydi_ogretmensiz_kaydeden_kullanici(panel, tahta, usb_hazir):
    anahtar, pin = anahtar_al(panel)
    h = usb_hazir["basliklar"]
    yanit = usb(tahta, h, "yoklama", anahtar, pin=pin)
    assert yanit.status_code == 200
    veri = yanit.json()
    assert veri["ogretmen"] == {"kod": "", "etiket": "İdare · D. Yönetici"} and veri["tur"] == "idare"
    assert set(veri) == {"belirtec", "kalan_sn", "bosta_sn", "ogretmen", "tur", "oneri", "subeler_once"}
    assert veri["oneri"] is None and veri["subeler_once"] == []  # idare anahtarı: öğretmen programı önerisi yok
    assert ajan(tahta, h, "oneri", {}).status_code == 200
    kayit = liste_ve_kaydet(tahta, h, veri["belirtec"], [ogrenci_id("1047")])
    assert kayit.status_code == 200, kayit.text
    y = sorgu("SELECT * FROM yoklama")[0]
    assert (y["ogretmen_id"], y["kaydeden"], y["kaynak"], y["tahta_id"]) == (None, "kullanici:yonetici", "tahta", kimlik(h))
    assert sorgu("SELECT kim FROM yoklama_iz")[0]["kim"] == f"kullanici:yonetici (tahta:10A Tahtası) USB {anahtar['kimlik']}"
    with vt.islem() as b:
        ayrinti = yk.kayit_ayrintisi(b, y["id"])
        gunluk = yk.gunluk_gorunum(b, yk.bugun(vt.simdi()), vt.simdi())
    assert ayrinti["kaynak"] == "tahta: 10A Tahtası · idare (yonetici) · USB anahtar"
    hucre = next(r for r in gunluk["satirlar"] if r["sube"] == "10/A")["hucreler"][0]
    assert "Alan: idare (yonetici)" in hucre["baslik"]
    alindi = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yoklama alındı'")[0]["ayrinti"]
    assert alindi == f"10/A 1. ders, 1 yok, kullanıcı yonetici · USB {ua.kimlik_bicimli(anahtar['kimlik'])}"
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yoklama oturumu açıldı (USB anahtar)'")[0]["ayrinti"].endswith(
        "kullanıcı yonetici"
    )


def test_usb_yoklama_ogretmen_kaydi_kod_pin_ile_ayni_satir(panel, tahta, usb_hazir):
    anahtar, _ = anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    h = usb_hazir["basliklar"]
    belirtec = usb(tahta, h, "yoklama", anahtar).json()["belirtec"]
    assert liste_ve_kaydet(tahta, h, belirtec, [ogrenci_id("1047")]).status_code == 200
    belirtec = baslat(tahta, usb_hazir).json()["belirtec"]
    liste = ajan(tahta, h, "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1}).json()
    assert liste["yok"] == [ogrenci_id("1047")]  # aynı satır: öncekiler işaretli gelir
    assert liste_ve_kaydet(tahta, h, belirtec, []).status_code == 200
    satirlar = sorgu("SELECT * FROM yoklama")
    assert len(satirlar) == 1
    assert (satirlar[0]["ogretmen_id"], satirlar[0]["kaydeden"]) == (usb_hazir["ogretmen_id"], f"ogretmen:{usb_hazir['kod']}")
    izler = [s["kim"] for s in sorgu("SELECT kim FROM yoklama_iz ORDER BY id")]
    assert izler[0].endswith(f"USB {anahtar['kimlik']}") and "USB" not in izler[1]


def test_usb_yoklama_kapaliyken_409(panel, tahta, usb_hazir):
    anahtar, _ = anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    ayar_kaydet(panel, yk_etkin=None)
    yanit = usb(tahta, usb_hazir["basliklar"], "yoklama", anahtar)
    assert yanit.status_code == 409 and yanit.json()["neden"] == "yoklama_kapali"


def test_usb_iptal_acik_oturumu_dusurur(panel, tahta, usb_hazir):
    anahtar, _ = anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    h = usb_hazir["basliklar"]
    belirtec = usb(tahta, h, "yoklama", anahtar).json()["belirtec"]
    kod_pin = baslat(tahta, usb_hazir).json()["belirtec"]  # aynı öğretmen-tahta: önceki oturum yenisiyle değişir
    belirtec = usb(tahta, h, "yoklama", anahtar).json()["belirtec"]
    assert ajan(tahta, h, "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1}).status_code == 200
    panel.post("/usb-anahtarlar", data={"eylem": "iptal", "id": str(sorgu("SELECT id FROM usb_anahtar")[0]["id"])})
    yanit = ajan(tahta, h, "kaydet", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1, "yok": []})
    assert yanit.status_code == 401
    assert kod_pin  # kod + PIN oturumu bu testte zaten yenisiyle değişmişti
    assert sorgu("SELECT kullanici, ayrinti FROM kayit WHERE islem = 'USB anahtar iptal edildi'")[0] == {
        "kullanici": "yonetici", "ayrinti": ua.kimlik_bicimli(anahtar["kimlik"])}  # fmt: skip


def test_usb_pasif_ogretmen_ve_kilitli_pin_reddedilir(panel, tahta, usb_hazir):
    anahtar, _ = anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    h = usb_hazir["basliklar"]
    with vt.islem() as b:
        b.execute("UPDATE ogretmen_pin SET kilitli = 1")
    yanit = usb(tahta, h, "tani", anahtar)
    assert yanit.status_code == 423 and yanit.json()["hata"] == ua.ILETI_OGRETMEN_PIN_KILITLI
    with vt.islem() as b:
        b.execute("UPDATE ogretmen_pin SET kilitli = 0")
    panel.post("/ogretmenler", data={"eylem": "durum", "id": str(usb_hazir["ogretmen_id"])})
    yanit = usb(tahta, h, "tani", anahtar)
    assert yanit.status_code == 403 and yanit.json()["hata"] == ua.ILETI_GECERSIZ


def test_usb_pasif_kullanici_reddedilir(panel, tahta, usb_hazir):
    kullanici_ekle(panel, "mdryrd")
    gir(panel, "mdryrd")
    anahtar, pin = anahtar_al(panel)
    h = usb_hazir["basliklar"]
    belirtec = usb(tahta, h, "yoklama", anahtar, pin=pin).json()["belirtec"]
    gir(panel, "yonetici")
    kid = sorgu("SELECT id FROM kullanici WHERE ad = 'mdryrd'")[0]["id"]
    panel.post("/kullanicilar", data={"eylem": "durum", "id": str(kid)})
    assert usb(tahta, h, "tani", anahtar).status_code == 403
    assert ajan(tahta, h, "liste", {"belirtec": belirtec, "sube": "10/A", "ders_no": 1}).status_code == 401


# ---- kilit ---------------------------------------------------------------------------------------------------
def test_usb_kilit_ac_ayar_kapaliyken_409(panel, tahta, usb_hazir):
    anahtar, _ = anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    h = usb_hazir["basliklar"]
    assert usb(tahta, h, "kilit_ac", anahtar).json() == {"tamam": True}
    kayit = sorgu("SELECT kullanici, ayrinti FROM kayit WHERE islem = 'Kilit USB anahtarla açıldı'")[0]
    assert kayit == {"kullanici": "tahta:10A Tahtası",
                     "ayrinti": f"{ua.kimlik_bicimli(anahtar['kimlik'])} · öğretmen kodu {usb_hazir['kod']}"}  # fmt: skip
    usb_ayar(panel, ua_kilit_acar=None)
    yanit = usb(tahta, h, "kilit_ac", anahtar)
    assert yanit.status_code == 409 and yanit.json()["neden"] == "kilit_kapali"


# ---- kopya -----------------------------------------------------------------------------------------------------
def test_usb_kopya_uyarisi_altmis_saniyede_iki_tahta(panel, tahta, usb_hazir, saat):
    anahtar, _ = anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    h2 = tahta_ekle(panel, tahta, "10B Tahtası", durum=USB_DURUMU, subeler="10/B")
    assert usb(tahta, usb_hazir["basliklar"], "tani", anahtar).status_code == 200
    saat.ilerlet(40)
    assert usb(tahta, h2, "tani", anahtar).status_code == 200  # engellenmez
    kayit = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'USB anahtar kısa sürede iki tahtada kullanıldı'")
    assert kayit[0]["ayrinti"] == f"{ua.kimlik_bicimli(anahtar['kimlik'])}: 10A Tahtası → 10B Tahtası (40 sn)"
    assert sorgu("SELECT kopya_uyarisi FROM usb_anahtar")[0]["kopya_uyarisi"] == vt.simdi()
    assert "kopyalanmış olabilir" in panel.get("/usb-anahtarlar").text
    saat.ilerlet(ua.KOPYA_PENCERE_SN + 1)
    usb(tahta, usb_hazir["basliklar"], "tani", anahtar)
    assert len(sorgu("SELECT 1 FROM kayit WHERE islem = 'USB anahtar kısa sürede iki tahtada kullanıldı'")) == 1


def test_usb_ayni_tahtada_uyari_yok(panel, tahta, usb_hazir, saat):
    anahtar, _ = anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    for _ in range(3):
        usb(tahta, usb_hazir["basliklar"], "tani", anahtar)
        saat.ilerlet(10)
    assert sorgu("SELECT kopya_uyarisi FROM usb_anahtar")[0]["kopya_uyarisi"] is None


# ---- KVKK ve saklama ------------------------------------------------------------------------------------------
def test_usb_islem_kaydinda_gizli_ve_ad_yok(panel, tahta, usb_hazir):
    idare, pin = anahtar_al(panel)
    ogretmen, _ = anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    h = usb_hazir["basliklar"]
    usb(tahta, h, "tani", {**idare, "gizli": ua.gizli_uret()})
    usb(tahta, h, "yoklama", idare, pin="999999" if pin != "999999" else "888888")
    belirtec = usb(tahta, h, "yoklama", idare, pin=pin).json()["belirtec"]
    liste_ve_kaydet(tahta, h, belirtec, [ogrenci_id("1047")])
    usb(tahta, h, "kilit_ac", ogretmen)
    kayitlar = "\n".join(f"{s['kullanici']} {s['islem']} {s['ayrinti']}" for s in sorgu("SELECT * FROM kayit"))
    for yasak in (idare["gizli"], ogretmen["gizli"], pin, "Deneme Yönetici", "D. Yönetici", "Örnek", "Ayşe", "YILMAZ", "1047"):
        assert yasak not in kayitlar, yasak


def test_usb_yil_sonu_iptalleri_siler_son_kullanimi_bosaltir(panel, tahta, usb_hazir, saat, uygulama):
    idare, _ = anahtar_al(panel)
    ogretmen, _ = anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    usb(tahta, usb_hazir["basliklar"], "tani", ogretmen)
    with vt.islem() as b:
        b.execute("UPDATE usb_anahtar SET kopya_uyarisi = son_kullanim WHERE sahip_turu = 'ogretmen'")
    panel.post("/usb-anahtarlar", data={"eylem": "iptal", "id": str(sorgu("SELECT id FROM usb_anahtar WHERE sahip_turu = 'kullanici'")[0]["id"])})
    with vt.islem() as b:
        vt.ayar_yaz(b, "ogretim_yili_bitis", "2026-11-16")
    saat.ayarla(an(17, 9))
    assert uygulama.state.yoklama_zamanlayici() is True
    satirlar = sorgu("SELECT * FROM usb_anahtar")
    assert len(satirlar) == 1 and satirlar[0]["sahip_turu"] == "ogretmen" and satirlar[0]["durum"] == "etkin"
    assert (satirlar[0]["son_kullanim"], satirlar[0]["son_tahta_id"], satirlar[0]["kopya_uyarisi"]) == (None, None, None)
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'USB anahtar yıl sonu temizliği'")
    # Sınırdan sonraki kullanım silinmez; ikinci tur bir şey yapmaz.
    usb(tahta, usb_hazir["basliklar"], "tani", ogretmen)
    with vt.islem() as b:
        assert ua.yil_sonu(b, date(2026, 11, 16)) == {"silinen": 0, "bosaltilan": 0}
    assert sorgu("SELECT son_kullanim FROM usb_anahtar")[0]["son_kullanim"] == vt.simdi()


# ---- dosya ayrıştırıcı ve ajanla ortak sabitler ---------------------------------------------------------------
GECERLI_GIZLI = "MFRGGZDFMZTWQ2LKNNWG23TPOBYXE43UOV3HO6DZPJ4HK2LZMVZXI5DF"[:52]
GECERLI = (
    "# Tahta Kontrol USB anahtari.\n\nTAHTA-KONTROL-ANAHTAR\nsurum=1\nkimlik=K7Q2M9XA\nsunucu=3f9a1c0b7e2d4a51\n"
    f"gizli={GECERLI_GIZLI}\n"
)
ORNEKLER = [
    (GECERLI, None),
    (GECERLI.replace("\n", "\r\n"), None),
    (GECERLI.replace("kimlik=K7Q2M9XA", "kimlik = k7q2m9xa"), None),
    (GECERLI.replace("sunucu=3f9a1c0b7e2d4a51", "sunucu=3F9A1C0B7E2D4A51"), None),
    (GECERLI.replace(GECERLI_GIZLI, GECERLI_GIZLI.lower()), None),
    (GECERLI + "kimlik=K7Q2M9XA\n", "bicim"),
    (GECERLI.replace("TAHTA-KONTROL-ANAHTAR\n", ""), "baslik"),
    (GECERLI.replace("surum=1", "surum=2"), "surum"),
    (GECERLI.replace("kimlik=K7Q2M9XA", "kimlik=K7Q2M9XI"), "bicim"),  # I alfabede yok
    (GECERLI.replace("kimlik=K7Q2M9XA", "kimlik=K7Q2M9X"), "bicim"),
    (GECERLI.replace("sunucu=3f9a1c0b7e2d4a51", "sunucu=3f9a1c0b7e2d4a5"), "bicim"),
    (GECERLI.replace(GECERLI_GIZLI, GECERLI_GIZLI[:-1]), "bicim"),
    (GECERLI.replace(GECERLI_GIZLI, GECERLI_GIZLI[:-1] + "1"), "bicim"),
    (GECERLI + "fazla=1\n", "bicim"),
    (GECERLI + "satir\n", "bicim"),
    (GECERLI.replace("# Tahta", "# Tahta ğ"), "ascii"),
    (GECERLI + "#" * 1100, "boyut"),
    ("", "baslik"),
]


@pytest.mark.parametrize(("ornek", "beklenen"), ORNEKLER)
def test_usb_dosya_coz_katilik(ornek, beklenen):
    veri = ornek.encode("utf-8")
    if beklenen is None:
        sonuc = ua.dosya_coz(veri)
        assert sonuc == {"surum": 1, "kimlik": "K7Q2M9XA", "sunucu": "3f9a1c0b7e2d4a51", "gizli": GECERLI_GIZLI}
    else:
        with pytest.raises(ua.DosyaHatasi) as hata:
            ua.dosya_coz(veri)
        assert hata.value.neden == beklenen


def test_usb_dosya_coz_sunucu_ve_ajan_ayni_sonucu_verir():
    ajan_mod = pytest.importorskip("tahta_ajan.usb_anahtar")
    for ornek, _ in ORNEKLER:
        veri = ornek.encode("utf-8")
        try:
            sunucu = ("tamam", ua.dosya_coz(veri))
        except ua.DosyaHatasi as hata:
            sunucu = ("red", hata.neden)
        try:
            ajandaki = ("tamam", ajan_mod.dosya_coz(veri))
        except ValueError as hata:
            ajandaki = ("red", getattr(hata, "neden", str(hata)))
        assert sunucu == ajandaki, ornek


def test_usb_tani_omru_sunucu_ve_ajan_ayni():
    ajan_mod = pytest.importorskip("tahta_ajan.usb_anahtar")
    assert ajan_mod.TANI_OMRU_SN == ua.TANI_OMRU_SN == 600
    assert ajan_mod.DOSYA_ADI == ua.DOSYA_ADI


def test_usb_uretilen_dosya_geri_cozulur(panel, tahta, usb_hazir):
    _, adres, _ = uret(panel)
    veri = panel.get(adres).content
    assert ua.dosya_coz(veri.replace(b"\n", b"\r\n"))["kimlik"] == ua.dosya_coz(veri)["kimlik"]


# ---- regresyon ve panel ---------------------------------------------------------------------------------------------
def test_yoklama_mevcut_kod_pin_akisi_degismedi(panel, tahta, usb_hazir):
    h = usb_hazir["basliklar"]
    veri = baslat(tahta, usb_hazir).json()
    assert set(veri) == {"belirtec", "kalan_sn", "bosta_sn", "ogretmen", "oneri", "subeler_once"}  # 0.14.0: iki yeni alan
    assert liste_ve_kaydet(tahta, h, veri["belirtec"], [ogrenci_id("1102")]).status_code == 200
    y = sorgu("SELECT * FROM yoklama")[0]
    assert (y["ogretmen_id"], y["kaydeden"]) == (usb_hazir["ogretmen_id"], f"ogretmen:{usb_hazir['kod']}")
    assert sorgu("SELECT kim FROM yoklama_iz")[0]["kim"] == f"ogretmen:{usb_hazir['kod']} (tahta:10A Tahtası)"
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Yoklama alındı'")[0]["ayrinti"] == (
        f"10/A 1. ders, 1 yok, öğretmen kodu {usb_hazir['kod']}"
    )
    with vt.islem() as b:  # eski konumsal çağrı biçimi
        belirtec, _ = yk.oturum_ac(b, usb_hazir["ogretmen_id"], kimlik(h), vt.simdi(), 8)
        assert yk.oturum_coz(b, belirtec, kimlik(h), vt.simdi())["tur"] == "ogretmen"


def test_usb_ogretmenler_sayfasi_ve_menu(panel, tahta, usb_hazir):
    anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    with vt.islem() as b:
        assert ua.ogretmen_sayilari(b) == {usb_hazir["ogretmen_id"]: 1}
        assert ua.tahta_destegi(b) == {"onayli": 1, "destekleyen": 1, "eski": 0}
    assert panel.get("/ogretmenler").status_code == 200
    sayfa = panel.get("/usb-anahtarlar")
    assert sayfa.status_code == 200 and 'href="/usb-anahtarlar" aria-current="page"' in sayfa.text
    assert [t["usb_anahtar_yetenegi"] for t in panel.get("/api/durum").json()["tahtalar"]] == [True]


# ---- panel arayüzü (0.11.0 arayüz uygulayıcısı) ------------------------------------------------------------------
def test_usb_ayarlar_bolumu_cizilir_ve_ileti_bolumde(panel, tahta, hazir):  # noqa: F811
    sayfa = panel.get("/ayarlar/usb").text
    assert 'id="usb_anahtar"' in sayfa and 'name="bolum" value="usb_anahtar"' in sayfa
    for alan in ("ua_etkin", "ua_kilit_acar", "ua_pin_idare", "ua_pin_ogretmen"):
        assert f'name="{alan}"' in sayfa
    assert "Kapalıyken tahtalar takılan belleklere hiç bakmaz." in sayfa
    assert "PIN, kopyalanan dosyayı tek başına işe yaramaz kılar." in sayfa
    konum = usb_ayar(panel).headers["location"]
    assert konum.startswith("/ayarlar/usb?yer=usb_anahtar")
    sayfa = panel.get(konum.split("#")[0]).text
    # İleti bölümün içinde bir kez, odaklanabilir bant olarak çizilir.
    assert sayfa.count("USB anahtar ayarı kaydedildi.") == 1
    assert sayfa.index('id="ileti"') > sayfa.index('id="usb_anahtar"')


def test_usb_ayarlar_yoklama_kapaliyken_uyari(panel, tahta, hazir):  # noqa: F811
    usb_ayar(panel)
    ayar_kaydet(panel, yk_etkin=None)
    assert "USB anahtar yalnız kilit açmada işe yarar" in panel.get("/ayarlar/usb").text


def test_usb_sayfasi_iptal_dialog_tetigi_ve_kopya_rozeti(panel, tahta, usb_hazir):
    anahtar, _ = anahtar_al(panel)
    sayfa = panel.get("/usb-anahtarlar").text
    satir_id = sorgu("SELECT id FROM usb_anahtar")[0]["id"]
    # Tetik type="button": JS yoksa hiçbir şey gönderilmez; onay düğmesi formu id ile gönderir.
    assert f'id="usb-iptal-{satir_id}"' in sayfa
    assert re.search(r'<button type="button" class="tehlike" data-onay="usb_iptal" data-onay-ad="[A-Z0-9]{4}-[A-Z0-9]{4}"', sayfa)
    assert anahtar["gizli"] not in sayfa and "Hiç kullanılmadı" in sayfa
    js = (vt.__file__.rsplit("vt.py", 1)[0] + "statik/panel.js")
    metin = open(js, encoding="utf-8").read()
    assert 'usb_iptal: {' in metin and 'ad: "eylem", deger: "iptal"' in metin
    # Onaylı gönderim (dialog düğmesi eylem=iptal ekler) anahtarı iptal eder.
    yanit = panel.post("/usb-anahtarlar", data={"eylem": "iptal", "id": str(satir_id)})
    assert "iptal edildi" in ileti(yanit)
    assert "data-onay=\"usb_iptal\"" not in panel.get("/usb-anahtarlar").text


def test_usb_sayfasi_ozellik_kapaliyken_uyari_bandi(panel, tahta, hazir):  # noqa: F811
    sayfa = panel.get("/usb-anahtarlar").text
    assert ua.ILETI_KAPALI_PANEL.replace("'", "&#39;") in sayfa and 'href="/ayarlar/usb"' in sayfa


def test_usb_uretildi_sayfasi_gizli_icermez(panel, tahta, usb_hazir):
    yanit, adres, pin = uret(panel)
    assert "tahta-kontrol (1).anahtar" in yanit.text and "en üst klasörüne" in yanit.text
    gizli = ua.dosya_coz(panel.get(adres).content)["gizli"]
    assert gizli not in yanit.text and pin


def test_usb_ogretmenler_sutunu(panel, tahta, usb_hazir):
    sayfa = panel.get("/ogretmenler").text
    assert '<th scope="col">USB anahtar</th>' in sayfa
    assert f'href="/usb-anahtarlar?ogretmen_id={usb_hazir["ogretmen_id"]}#ogretmen"' in sayfa
    anahtar_al(panel, "ogretmen", usb_hazir["ogretmen_id"])
    assert "1 anahtar" in panel.get("/ogretmenler").text
    secili = panel.get(f"/usb-anahtarlar?ogretmen_id={usb_hazir['ogretmen_id']}").text
    assert f'<option value="{usb_hazir["ogretmen_id"]}" selected>' in secili


def test_usb_tahta_sayfasi_eski_ajan_rozeti(panel, tahta, hazir):  # noqa: F811
    tahta_id = kimlik(hazir["basliklar"])
    assert "USB anahtar: ajan güncellenmeli" not in panel.get(f"/tahta/{tahta_id}?sekme=bakim").text  # özellik kapalı
    usb_ayar(panel)
    assert "USB anahtar: ajan güncellenmeli" in panel.get(f"/tahta/{tahta_id}?sekme=bakim").text
    bekle(tahta, hazir["basliklar"], USB_DURUMU)
    sayfa = panel.get(f"/tahta/{tahta_id}?sekme=bakim").text
    assert "USB anahtar: ajan güncellenmeli" not in sayfa and "USB anahtar: destekleniyor" in sayfa



def test_usb_iz_eki_tahta_adindan_cikarilmaz():
    """Kaydın 'USB anahtar' eki iz metninin SONUNDAKİ kimlikten anlaşılır; adında USB geçen tahta yanıltmaz."""
    ogretmen = {"tur": "ogretmen", "ogretmen_id": 1, "kod": "112", "anahtar_kimlik": None}
    _, _, kim = yk.oturum_kaydedeni(ogretmen, "Lab USB 2")
    assert not yk._USB_IZ_EKI.search(kim)
    _, _, kim = yk.oturum_kaydedeni(ogretmen, "x) USB ABCDEFGH")
    assert not yk._USB_IZ_EKI.search(kim)
    _, _, kim = yk.oturum_kaydedeni({**ogretmen, "anahtar_kimlik": "K7Q2M9XA"}, "Lab USB 2")
    assert yk._USB_IZ_EKI.search(kim)


def test_usb_panel_js_onay_form_kimligini_golgelenmeden_okur():
    """İptal formunda name="id" alanı var: form.id o alanı döndürür; onay düğmesi forma bağlanmazdı."""
    from pathlib import Path

    js = (Path(__file__).resolve().parents[1] / "tahta_sunucu" / "statik" / "panel.js").read_text(encoding="utf-8")
    assert not re.search(r"\bform\.id\b", js)
    assert 'form.getAttribute("id")' in js


def test_usb_iptal_formu_kimligi_ve_onay_tetigi(panel, tahta, usb_hazir):
    anahtar_al(panel)
    anahtar_id = sorgu("SELECT id FROM usb_anahtar")[0]["id"]
    sayfa = panel.get("/usb-anahtarlar").text
    form = re.search(rf'<form[^>]*id="usb-iptal-{anahtar_id}"[^>]*>(.*?)</form>', sayfa, re.S)
    assert form and 'data-onay="usb_iptal"' in form.group(1)


def test_usb_indirme_baglantisinda_download_ozniteligi_yok(panel, tahta, usb_hazir):
    yanit, adres, _ = uret(panel)
    bag = re.search(r'<a [^>]*href="' + re.escape(adres) + r'"[^>]*>', yanit.text).group(0)
    assert "download" not in bag and 'data-tek-indirme="indir-bilgi"' in bag
    assert 'id="indir-bilgi"' in yanit.text


def test_usb_ogretmen_uretim_hatasi_secimi_korur_ve_kutuda_gosterir(panel, tahta, usb_hazir):
    oid = usb_hazir["ogretmen_id"]
    anahtar_al(panel, "ogretmen", oid)
    anahtar_al(panel, "ogretmen", oid)
    yanit = panel.post("/usb-anahtarlar", data={"eylem": "uret", "sahip": "ogretmen", "ogretmen_id": str(oid), "etiket": ""})
    adres = yanit.headers["location"]
    assert adres.startswith(f"/usb-anahtarlar?yer=ogretmen&ogretmen_id={oid}&m=") and adres.endswith("#ogretmen")
    sayfa = panel.get(adres.split("#")[0]).text
    assert f'<option value="{oid}" selected>' in sayfa
    kutu = sayfa.split('id="ogretmen"', 1)[1]
    assert ua.ILETI_SINIR in kutu and ua.ILETI_SINIR not in sayfa.split('id="ogretmen"', 1)[0]


def test_usb_etiket_tc_iletisi_tahtayi_anmaz(panel, tahta, usb_hazir):
    yanit, adres, _ = uret(panel, etiket="10000000146")
    assert adres is None and ileti(yanit) == ua.ILETI_ETIKET_TC
    assert "Tahta herkese açık" not in ua.ILETI_ETIKET_TC
