"""Yoklama 0.14.0 — mazeret/izin katmanı: giriş (önizle → onayla), liste, kaldırma, sınırlar, gizlilik.
Bütün adlar ve numaralar UYDURMADIR."""

# ruff: noqa: F811  (içe aktarılan fikstürler test parametresi olarak yeniden adlandırılır)
from __future__ import annotations

import re
from datetime import date

import pytest
from test_yoklama import OGRENCI_CSV, hazir, ogrenci_id  # noqa: F401
from test_yoklama_defter import JSON, defterli, durum_, hucre, kayit, zil_yaz  # noqa: F401
from yardimci import an, gir, ileti, kullanici_ekle, sorgu

from tahta_sunucu import vt
from tahta_sunucu import yoklama as yk
from tahta_sunucu import yoklama_defter as yd

FORM = {"nolar": "1047", "bas": "2026-11-17", "bit": "2026-11-18", "kapsam": "tam", "ders_bas": "", "ders_bit": "",
        "tur": "raporlu", "dayanak": "belge"}  # fmt: skip


def onizle(panel, **alanlar):
    return panel.post("/yoklama/mazeret/onizle", data={**FORM, **alanlar})


def belirtec_(yanit) -> str:
    return re.search(r'name="onizleme" value="([^"]+)"', yanit.text).group(1)


def gir_mazeret(panel, **alanlar):
    yanit = onizle(panel, **alanlar)
    assert yanit.status_code == 200, ileti(yanit)
    return panel.post("/yoklama/mazeret/onayla", data={"onizleme": belirtec_(yanit)})


def test_mazeret_formunda_serbest_metin_alani_yok_turler_sabit(panel, defterli):
    sayfa = panel.get("/yoklama/mazeret")
    form = sayfa.text.split('action="/yoklama/mazeret/onizle"')[1].split("</form>")[0]
    assert sayfa.status_code == 200 and sayfa.headers["cache-control"] == "no-store"
    assert re.findall(r'<(?:input|textarea|select)[^>]* name="([^"]+)"', form) == [
        "nolar", "bas", "bit", "kapsam", "kapsam", "ders_bas", "ders_bit", "tur", "dayanak"]  # fmt: skip
    assert 'type="text"' not in form and form.count("<textarea") == 1  # tek metin alanı okul numaralarıdır
    for kod, ad in yk.MAZERET_TURLERI.items():
        assert f'value="{kod}"' in form and ad in form
    assert "rehber" not in form.lower() and "yerini tutmaz" in sayfa.text
    assert set(yk.MAZERET_TURLERI) == {"izinli", "raporlu", "mazeretli", "gorevli"}
    assert set(yk.MAZERET_DAYANAKLARI) == {"", "dilekce", "yazi", "belge", "idare"}


def test_mazeret_onizle_onayla_yok_hucresi_o_olur_iptalde_asil_durum_doner(panel, defterli):
    kayit(17, "10/A", 1, yok=["1047", "1102"])
    kayit(18, "10/A", 1, yok=["1047"])
    kayit(18, "10/A", 2)
    oncesi = sorgu("SELECT * FROM yoklama ORDER BY id"), sorgu("SELECT * FROM yoklama_yok"), sorgu("SELECT * FROM yoklama_iz")
    yanit = onizle(panel, nolar="1047, 9999\n1047")
    assert yanit.status_code == 200 and "Ayşe YILMAZ" in yanit.text and "9999" in yanit.text and "10 dakika" in yanit.text
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama_mazeret")[0]["n"] == 0  # önizleme hiçbir şey yazmaz
    assert not [k for k in sorgu("SELECT islem FROM kayit") if "azeret" in k["islem"]]  # önizleme işlem kaydına da yazılmaz
    ozet = re.sub(r"<[^>]+>", " ", yanit.text)
    assert re.search(r"Kapsanan öğretim günü\s+2\b", ozet) and re.search(r"Kapsanan ders saati\s+8\b", ozet)
    assert re.search(r'Şu an "yok" kayıtlı\s+2 ders saati', ozet)
    onay = panel.post("/yoklama/mazeret/onayla", data={"onizleme": belirtec_(yanit)})
    assert ileti(onay) == "Mazeret kaydedildi: 1 öğrenci."
    m = sorgu("SELECT * FROM yoklama_mazeret")[0]
    assert (m["ogrenci_id"], m["tur"], m["dayanak"], m["ders_bas"], m["devre"], m["giren"]) == (ogrenci_id("1047"), "raporlu", "belge", None, "", "yonetici")
    # İşlem kaydı: tür ve tarih aralığı YOK; yalnız sayılar.
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Mazeret girildi'") == [{"ayrinti": "1 öğrenci, 2 gün"}]
    tum_kayit = " ".join(f"{k['islem']} {k['ayrinti']}" for k in sorgu("SELECT islem, ayrinti FROM kayit")).lower()
    for gizli in ("raporlu", "17.11", "1047", "ayşe", "belge"):
        assert gizli not in tum_kayit
    # Öğretmenin kaydı hiç değişmez; hücre Ö olur, var olan saat köşe noktasıyla işaretlenir.
    assert (sorgu("SELECT * FROM yoklama ORDER BY id"), sorgu("SELECT * FROM yoklama_yok"), sorgu("SELECT * FROM yoklama_iz")) == oncesi
    with vt.islem() as b:
        h1 = yd.hucre_durumu(b, "2026-11-18", "10/A", 1, ogrenci_id("1047"))
        h2 = yd.hucre_durumu(b, "2026-11-18", "10/A", 2, ogrenci_id("1047"))
        h3 = yd.hucre_durumu(b, "2026-11-18", "10/A", 3, ogrenci_id("1047"))
        diger = yd.hucre_durumu(b, "2026-11-17", "10/A", 1, ogrenci_id("1102"))
    assert (h1["durum"], h1["ozurlu"], yd.simge(h1)) == ("yok", True, "Ö")
    assert (h2["durum"], h2["ozurlu"], h2["kapsam"]) == ("var", False, True) and (h3["durum"], h3["kapsam"]) == ("alinmadi", True)
    assert (diger["durum"], diger["ozurlu"]) == ("yok", False)
    defter = panel.get("/yoklama/sube?sube=10/A&tarih=2026-11-18").text
    assert 'data-d="yok" data-ozurlu' in defter and 'data-d="var" data-kapsam' in defter and "Raporlu" not in defter
    # Tür yalnız mazeret sayfasında ve öğrenci görünümünün mazeret bölümünde.
    assert "Raporlu" in panel.get("/yoklama/mazeret").text and "Belge sunuldu" in panel.get(f"/yoklama/ogrenci/{ogrenci_id('1047')}").text
    for adres in ("/yoklama?tarih=2026-11-18", "/yoklama/sube?sube=10/A", "/yoklama/icmal?tarih=2026-11-18", "/yoklama/son-gunler?ozurluler=1"):
        assert "aporlu" not in panel.get(adres).text, adres
    assert "aporlu" not in panel.get("/yoklama/icmal.csv?tarih=2026-11-18").content.decode("utf-8")
    # Kaldırma: tür 'iptal', dayanak boş; asıl durum geri görünür; kayıt 30 gün "kaldırıldı" diye durur.
    bilinmeyen = panel.post(f"/yoklama/mazeret/{m['id']}/iptal", data={})
    assert ileti(bilinmeyen) == "Bilinmeyen işlem." and sorgu("SELECT tur FROM yoklama_mazeret")[0]["tur"] == "raporlu"
    iptal = panel.post(f"/yoklama/mazeret/{m['id']}/iptal", data={"eylem": "iptal"})
    assert "t=hata" not in iptal.headers["location"], ileti(iptal)
    m2 = sorgu("SELECT * FROM yoklama_mazeret")[0]
    assert (m2["tur"], m2["dayanak"], m2["iptal_eden"], m2["giren"]) == ("iptal", "", "yonetici", "yonetici") and m2["iptal_zamani"]
    with vt.islem() as b:
        h1 = yd.hucre_durumu(b, "2026-11-18", "10/A", 1, ogrenci_id("1047"))
    assert (h1["durum"], h1["ozurlu"], h1["kapsam"]) == ("yok", False, False)
    liste = panel.get("/yoklama/mazeret").text.split('id="liste"')[1]
    assert "kaldırıldı" in liste and "Raporlu" not in liste and "Belge sunuldu" not in liste and 'data-onay="mazeret_kaldir"' not in liste
    assert "zaten kaldırılmış" in ileti(panel.post(f"/yoklama/mazeret/{m['id']}/iptal", data={"eylem": "iptal"}))
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Mazeret kaldırıldı'") == [{"ayrinti": ""}]


def test_mazeret_onizlemesi_bellekte_tek_kullanimlik_ve_kullaniciya_bagli(panel, defterli, uygulama):
    yanit = onizle(panel)
    belirtec = belirtec_(yanit)
    assert belirtec not in " ".join(str(k) for k in sorgu("SELECT * FROM kayit"))
    assert len(uygulama.state.yoklama_onizleme.kayitlar) == 1
    # Öğrenci aktarım ucu mazeret önizlemesini kabul etmez (depo ortaktır) ve belirteci tüketir.
    assert ileti(panel.post("/ogrenciler/aktar", data={"onizleme": belirtec})).startswith("Önizlemenin süresi doldu")
    assert ileti(panel.post("/yoklama/mazeret/onayla", data={"onizleme": belirtec})).startswith("Önizlemenin süresi doldu")
    # Başka kullanıcı kullanamaz.
    belirtec = belirtec_(onizle(panel))
    kullanici_ekle(panel, "idareci2", "idareci")
    gir(panel, "idareci2")
    assert ileti(panel.post("/yoklama/mazeret/onayla", data={"onizleme": belirtec})).startswith("Önizlemenin süresi doldu")
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama_mazeret")[0]["n"] == 0
    # Öğrenci aktarım önizlemesi de mazeret ucunda geçmez.
    gir(panel, "yonetici")
    aktarim = panel.post("/ogrenciler/onizle", files={"dosya": ("l.csv", OGRENCI_CSV, "text/csv")})
    assert ileti(panel.post("/yoklama/mazeret/onayla", data={"onizleme": belirtec_(aktarim)})).startswith("Önizlemenin süresi doldu")
    # Onay tek kullanımlıktır; idareci de girebilir.
    gir(panel, "idareci2")
    yanit = onizle(panel, tur="izinli", dayanak="")
    belirtec = belirtec_(yanit)
    assert "t=hata" not in panel.post("/yoklama/mazeret/onayla", data={"onizleme": belirtec}).headers["location"]
    assert ileti(panel.post("/yoklama/mazeret/onayla", data={"onizleme": belirtec})).startswith("Önizlemenin süresi doldu")
    assert sorgu("SELECT giren, tur, dayanak FROM yoklama_mazeret") == [{"giren": "idareci2", "tur": "izinli", "dayanak": ""}]


def test_mazeret_tarih_ve_sayi_sinirlari(panel, defterli):
    def hata(**alanlar) -> str:
        yanit = onizle(panel, **alanlar)
        assert yanit.status_code == 400, alanlar
        return ileti(yanit)

    assert "en çok 31 gün" in hata(bas="2026-11-18", bit="2026-12-19")
    assert "en geç 19.12.2026" in hata(bas="2026-12-01", bit="2026-12-20")  # bitiş tarihi boşken bugün + 31 gün
    assert "7 gün geriye" in hata(bas="2026-11-10", bit="2026-11-12")
    assert "başlangıçtan önce" in hata(bas="2026-11-18", bit="2026-11-17")
    assert "türünü seçin" in hata(tur="hasta") and "Dayanak" in hata(dayanak="rapor no 12")
    assert "En az bir okul numarası" in hata(nolar=" , ") and "eşleşen etkin öğrenci yok" in hata(nolar="9999")
    assert "en çok 50" in hata(nolar=" ".join(str(n) for n in range(3000, 3051)))
    assert "ilk ve son ders" in hata(kapsam="ders") and "1–20" in hata(kapsam="ders", ders_bas="3", ders_bit="2")
    assert "kimlik" in hata(nolar="12345678950").lower()
    assert sorgu("SELECT COUNT(*) AS n FROM yoklama_mazeret")[0]["n"] == 0
    # Öğretim yılı bitişi girilmişse üst sınır odur.
    with vt.islem() as b:
        vt.ayar_yaz(b, "ogretim_yili_bitis", "2026-11-25")
    assert "en geç 25.11.2026" in hata(bas="2026-11-24", bit="2026-11-26")
    assert onizle(panel, bas="2026-11-24", bit="2026-11-25").status_code == 200
    # Hatalı formda girilen değerler geri gelir.
    assert 'value="2026-11-26"' in onizle(panel, bas="2026-11-24", bit="2026-11-26").text


def test_ders_aralikli_mazeret_devreyi_yazar_karisik_devre_reddedilir(panel, hazir, saat):  # noqa: F811
    sabah = [("07:30", "08:10"), ("08:20", "09:00"), ("09:10", "09:50")]
    zil_yaz(devre="sabah", ad="Sabah", saatler=sabah)
    zil_yaz(devre="ogle", ad="Öğle", saatler=[("13:00", "13:40"), ("13:50", "14:30")])
    tahta_id = int(hazir["basliklar"]["X-Tahta-Id"])
    with vt.islem() as b:
        for gun in range(5):
            b.execute("INSERT INTO tahta_ders (tahta_id, gun, devre, ders_no, sube) VALUES (?, ?, 'sabah', 1, '10/A')", (tahta_id, gun))
            b.execute("INSERT INTO tahta_ders (tahta_id, gun, devre, ders_no, sube) VALUES (?, ?, 'ogle', 1, '10/B')", (tahta_id, gun))
    saat.ayarla(an(18, 16))
    gir(panel, "yonetici")
    karisik = onizle(panel, nolar="1047 2001", kapsam="ders", ders_bas="1", ders_bit="2", bas="2026-11-18", bit="2026-11-18")
    assert karisik.status_code == 400 and ileti(karisik) == yd.ILETI_KARISIK_DEVRE
    assert onizle(panel, nolar="1047 2001", bas="2026-11-18", bit="2026-11-18").status_code == 200  # tam günde devre sorulmaz
    kayit(18, "10/A", 1, yok=["1047"])
    kayit(18, "10/A", 3, yok=["1047"])
    yanit = gir_mazeret(panel, nolar="1047", kapsam="ders", ders_bas="1", ders_bit="2", bas="2026-11-18", bit="2026-11-18", tur="gorevli")
    assert "t=hata" not in yanit.headers["location"], ileti(yanit)
    m = sorgu("SELECT ders_bas, ders_bit, devre FROM yoklama_mazeret")[0]
    assert m == {"ders_bas": 1, "ders_bit": 2, "devre": "sabah"}
    with vt.islem() as b:
        assert yd.hucre_durumu(b, "2026-11-18", "10/A", 1, ogrenci_id("1047"))["ozurlu"] is True
        assert yd.hucre_durumu(b, "2026-11-18", "10/A", 3, ogrenci_id("1047"))["ozurlu"] is False  # aralık dışı
    assert "1–2. ders" in panel.get("/yoklama/mazeret").text


def test_mazeret_sonrasi_islendi_rozeti_degisir_ve_defterden_mazerete_gecis(panel, defterli):
    kayit(18, "10/A", 1, yok=["1047"])
    panel.post("/yoklama/islendi", data={"tarih": "2026-11-18", "sube": "10/A", "deger": "1"})
    with vt.islem() as b:
        b.execute("UPDATE eokul_islendi SET zaman = ?", (vt.simdi() - 60,))
        b.execute("UPDATE yoklama SET guncelleme = ?", (vt.simdi() - 120,))
    assert "İşlendikten sonra değişti" not in panel.get("/yoklama?tarih=2026-11-18").text
    assert "t=hata" not in gir_mazeret(panel, bas="2026-11-18", bit="2026-11-18").headers["location"]
    assert "İşlendikten sonra değişti" in panel.get("/yoklama?tarih=2026-11-18").text
    with vt.islem() as b:
        veri = yd.Veri(b, date(2026, 11, 17), date(2026, 11, 17))
        assert yd.eokul_bayat(b, veri, "2026-11-17", {"10/A": {"zaman": 0}}) == set()  # mazeret 17'yi kapsamıyor
    # Şube defterindeki "Mazeret gir" bağlantısı formu öğrenci ve tarihle dolu açar; okul no adrese yazılmaz.
    defter = panel.get("/yoklama/sube?sube=10/A&tarih=2026-11-18").text
    baglanti = f'/yoklama/mazeret?ogrenci={ogrenci_id("1102")}&amp;bas=2026-11-18'
    assert baglanti in defter
    form = panel.get(baglanti.replace("&amp;", "&")).text
    assert ">1102</textarea>" in form and 'name="bas" value="2026-11-18"' in form and 'name="bit" value="2026-11-18"' in form


def test_ayni_saate_iki_mazeret_ve_gec_ozurlu_olmaz(panel, defterli):
    kayit(18, "10/A", 1, yok=["1047"], gec=["1102"])
    gir_mazeret(panel, nolar="1047 1102", bas="2026-11-18", bit="2026-11-18", tur="izinli")
    gir_mazeret(panel, nolar="1047", bas="2026-11-18", bit="2026-11-18", tur="gorevli")
    idler = [m["id"] for m in sorgu("SELECT id FROM yoklama_mazeret WHERE ogrenci_id = ? ORDER BY id", ogrenci_id("1047"))]
    panel.post(f"/yoklama/mazeret/{idler[1]}/iptal", data={"eylem": "iptal"})
    with vt.islem() as b:
        assert yd.hucre_durumu(b, "2026-11-18", "10/A", 1, ogrenci_id("1047"))["ozurlu"] is True  # öbür kayıt geçerli
        gec = yd.hucre_durumu(b, "2026-11-18", "10/A", 1, ogrenci_id("1102"))
    assert (gec["durum"], gec["ozurlu"], yd.simge(gec)) == ("gec", False, "G")  # özürlü yalnız "yok" içindir
    with pytest.raises(ValueError, match="Öğrenci listesi değişti"):
        with vt.islem() as b:
            yd.mazeret_yaz(b, {"girdi": {**FORM, "ders_bas": None, "ders_bit": None, "devre": ""}, "ogrenci_idleri": [99999]}, "x", 0)
