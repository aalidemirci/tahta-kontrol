"""Bugün sayfasının iş mantığı (0.18.0, panel arayüzü 4. aşama): `bugun.bekleyenler` (tek işlev, rol içeride),
menü rozetleri, tahta özeti, yoklama ve duyuru kutuları, akış. Uydurma veriyle.

Kayıp denetimi: 0.17.0'da tahta listesinin üstündeki bantların her koşulu (B1–B9, arıza) ve yeni koşullar
(öğretim yılı bitişi, geri yükleme, güncel olmayan ajan, kurulum) burada bir satır üretir; her biri sınanır."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest
from test_yoklama import hazir, ogrenci_id, ogrenci_yukle  # noqa: F401
from test_yoklama_defter import kayit, zil_yaz
from yardimci import (
    an,
    gir,
    kimlik,
    kullanici_ekle,
    kur_ve_gir,
    sorgu,
    tahta_ekle,
    yeni_ajan_durumu,
    zil_elle,
)

from tahta_sunucu import adresler, ayar, bugun, guncelleme, paket, tahta_liste, vt, yedek
from tahta_sunucu import yoklama as yk

YONETICI = {"rol": "yonetici"}
IDARECI = {"rol": "idareci"}
YONETICI_ADRESLERI = ("/ayarlar", "/yedekler", "sekme=bilgiler", "/ekle")
YALNIZ_YONETICI = {"yedek_parola", "geri_yukleme", "ogretim_yili", "onay", "yeni_surum", "kurulum"}


def isler(kullanici=YONETICI, **kw) -> dict[str, dict]:
    with vt.islem() as b:
        return {s["anahtar"]: s for s in bugun.bekleyenler(b, kullanici, ipler=kw.pop("ipler", []), **kw)}


def liste(kullanici=YONETICI, **kw) -> list[dict]:
    with vt.islem() as b:
        return bugun.bekleyenler(b, kullanici, ipler=kw.pop("ipler", []), **kw)


def ayar_yaz(anahtar: str, deger) -> None:
    with vt.islem() as b:
        vt.ayar_yaz(b, anahtar, deger)


def yedek_tamam(**son) -> None:
    """Yedek parolası belirlenmiş, son yedek başarılı ve taze (yedek satırı üretmeyen durum) + istenen sapma."""
    simdi = vt.simdi()
    ayar_yaz("yedek", {"acik_anahtar": "uydurma", "parola_zamani": simdi})
    ayar_yaz("son_yedek", {"basarili": True, "son_basarili": simdi, **son})


def bekleyen_tahta(panel, tahta) -> int:
    panel.post("/ekle", data={"eylem": "ac"})
    kod = panel.get("/ekle").text.split('class="buyuk-kod">')[1].split("<")[0]
    return tahta.post("/ajan/kaydol", json={"kod": kod, "makine_adi": "etap-yeni", "surum": "0.17.0"}).json()["tahta_id"]


@pytest.fixture()
def temiz(panel, tahta, saat, monkeypatch):
    """Hiç bekleyen işi olmayan okul: her koşul karşılanmış. Tek onaylı, güncel ajanlı tahta (T-1)."""
    kur_ve_gir(panel)
    kullanici_ekle(panel, "idareci1")
    kullanici_ekle(panel, "yonetici2", rol="yonetici")
    basliklar = tahta_ekle(panel, tahta, "T-1", yeni_ajan_durumu(), surum=paket.ajan_paketi().surum)
    yedek_tamam()
    ayar_yaz("ogretim_yili_bitis", "2027-06-18")
    ayar_yaz("kilit_kodu", "uydurma-ozet")
    zil_elle({"devre_adi": "Normal", "ilk_ders": "08:20", "ders_sayisi": "4", "ders_dk": "40", "teneffus_dk": "10",
              "gunler": ["0", "1", "2", "3", "4"]})  # fmt: skip
    with vt.islem() as b:
        b.execute("INSERT INTO tahta_ders (tahta_id, gun, devre, ders_no, sube) VALUES (?, 0, 'normal', 1, '9/A')", (kimlik(basliklar),))
    monkeypatch.setattr(yedek, "bekleyen_oku", lambda: None)
    return {"panel": panel, "tahta": tahta, "basliklar": basliklar}


def test_bekleyenler_kosul_yokken_bos(temiz):
    assert liste(YONETICI) == [] and liste(IDARECI) == []
    assert liste(YONETICI, yalniz_rozet=True) == []
    assert bugun.rozet_sayilari([]) == {"tahtalar": 0, "yedekler": 0} and bugun.imza([]) == ""


# ---- her bant koşulu bir satır üretir (kayıp yok) --------------------------------------------------------
def test_b1_yedek_parolasi_yok_role_gore_iki_satir(temiz):
    ayar_yaz("yedek", {})
    y = isler(YONETICI)["yedek_parola"]
    assert (y["onem"], y["baslik"], y["yol"], y["eylem"], y["rozet"]) == (
        "tehlike", "Yedek parolası belirlenmedi; otomatik yedek alınmıyor.", "/yedekler", "Yedekler", "yedekler")  # fmt: skip
    i = isler(IDARECI)
    assert set(i) == {"yedek_parola_i"}
    assert (i["yedek_parola_i"]["baslik"], i["yedek_parola_i"]["yol"], i["yedek_parola_i"]["rozet"]) == (
        "Yedek alınmıyor; yöneticiye bildirin.", "", None)  # fmt: skip


def test_b2_son_deneme_basarisiz(temiz):
    yedek_tamam(basarili=False, hata="disk dolu")
    for k in (YONETICI, IDARECI):
        s = isler(k)["yedek_basarisiz"]
        assert s["onem"] == "uyari" and s["baslik"] == "Son yedek alınamadı (son başarılı: 16.11.2026 09:00)."
    assert isler(YONETICI)["yedek_basarisiz"]["alt"] == "Ayrıntı Yedekler sayfasında."
    assert isler(IDARECI)["yedek_basarisiz"]["alt"] == "Yöneticiye bildirin."
    assert isler(YONETICI)["yedek_basarisiz"]["yol"] == "/yedekler" and isler(IDARECI)["yedek_basarisiz"]["yol"] == ""
    assert isler(IDARECI)["yedek_basarisiz"]["rozet"] is None
    ayar_yaz("son_yedek", {"basarili": False})
    assert isler()["yedek_basarisiz"]["baslik"] == "Son yedek alınamadı (henüz başarılı yedek yok)."


def test_yedek_hata_metni_ve_yolu_bugune_yazilmaz(temiz):
    """Ham istisna metni sunucu yolunu ve ikinci kopya klasörünü taşır; Bugün omuz üstünden görülür ve idareciye açıktır."""
    gizli = ("PermissionError", "Errno", "Uydurma", "tkyedek", "ProgramData", "ag-diski", "WinError")
    yedek_tamam(basarili=False, hata="PermissionError: [Errno 13] Permission denied: 'C:/ProgramData/Uydurma/yedek/x.tkyedek'")
    for k in (YONETICI, IDARECI):
        assert "yedek_basarisiz" in isler(k)
        for parca in gizli:
            assert parca not in repr(list(isler(k).values())), (k["rol"], parca)
    yedek_tamam(kopya_hata="FileNotFoundError: [WinError 3] '//ag-diski/Uydurma/yedek'")
    for k in (YONETICI, IDARECI):
        s = isler(k)["yedek_kopya"]
        assert s["baslik"] == "Yedeğin ikinci kopyası yazılamadı."
        for parca in gizli:
            assert parca not in repr(s), (k["rol"], parca)


def test_b3_yedek_iki_gunden_eski(temiz):
    yedek_tamam(son_basarili=vt.simdi() - 3 * 86400)
    assert isler()["yedek_eski"]["baslik"] == "Son yedek: 13.11.2026 09:00. Yedek 2 günden eski."
    assert "yedek_basarisiz" not in isler()  # elif: ikisi birlikte çıkmaz
    ayar_yaz("yedek", {"acik_anahtar": "uydurma", "parola_zamani": vt.simdi() - 3 * 86400})
    ayar_yaz("son_yedek", {})
    assert isler(IDARECI)["yedek_eski"]["baslik"] == "Henüz yedek alınmadı. Yedek 2 günden eski."


def test_b4_ikinci_kopya_yazilamadi(temiz):
    yedek_tamam(kopya_hata="hedef klasör yok")
    s = isler()["yedek_kopya"]
    assert s["baslik"] == "Yedeğin ikinci kopyası yazılamadı." and s["onem"] == "uyari" and "hedef klasör" not in repr(s)
    assert s["alt"] == "Ayrıntı Yedekler sayfasında." and isler(IDARECI)["yedek_kopya"]["alt"] == "Yöneticiye bildirin."
    assert isler(IDARECI)["yedek_kopya"]["yol"] == ""


def test_b5_adres_listede_yok(temiz):
    with vt.islem() as b:
        adresler.yaz(b, ["https://10.0.0.5:8788"])
    assert "adres" not in isler(ipler=[])  # adres bilinmiyorsa uyarı yok
    y = isler(ipler=["10.0.0.9"])["adres"]
    assert y["baslik"] == ("Bu bilgisayarın adresi (10.0.0.9) tahtalara bildirilen listede yok. "
                           "Tahtalar eski adresi kullanıyor olabilir.")  # fmt: skip
    assert (y["yol"], y["eylem"]) == ("/ayarlar/sunucu#adresler", "Ayarlar")
    assert isler(IDARECI, ipler=["10.0.0.9"])["adres"]["yol"] == ""
    assert "adres" not in isler(ipler=["10.0.0.5"])


def surum_bildir(surum: str = "99.0.1", sonuc: str = "tamam") -> None:
    with vt.islem() as b:
        guncelleme.durum_yaz(b, {"sonuc": sonuc, "surum": surum}, vt.simdi())


def test_b6_yeni_surum_yalniz_yoneticide(temiz):
    surum_bildir()
    from tahta_sunucu import __version__

    s = isler()["yeni_surum"]
    assert s["baslik"] == f"Tahta Kontrol 99.0.1 yayımlandı (kurulu sürüm {__version__})." and s["alt"] == "Kendiliğinden indirilmez."
    assert s["dis"] is True and s["eylem"] == "Sürüm sayfası" and s["surum"] == "99.0.1" and s["onem"] == "bilgi"
    assert (s["ek_yol"], s["ek_eylem"]) == ("/ayarlar/guncelleme", "Ayarlar")  # denetimi kapatmanın yolu
    assert "yeni_surum" not in isler(IDARECI)


def test_yeni_surum_baglantisi_sabit_kaliptan(temiz):
    surum_bildir("v99.0.1")
    assert isler()["yeni_surum"]["yol"] == guncelleme.surum_adresi("99.0.1") == "https://github.com/aalidemirci/tahta-kontrol/releases/tag/v99.0.1"
    # Saklanan durum bozulmuşsa (doğrulanamayan sürüm) satır hiç çıkmaz; adres uydurulmaz.
    ayar_yaz("guncelleme_durumu", {"zaman": vt.simdi(), "sonuc": "tamam", "surum": "https://kotu.example/x"})
    assert "yeni_surum" not in isler()


def test_yeni_surum_satiri_ulasilamadiginda_yok(temiz):
    surum_bildir("", "ulasilamadi")
    assert "yeni_surum" not in isler()  # hiç bilinmiyorsa: satır yok, hata metni yok
    assert not [s for s in liste() if "laşılamadı" in s["baslik"] or "GitHub" in s["baslik"]]
    # Bilinen yeni sürüm varken sonraki deneme başarısızsa satır kalır (0.17.0 davranışı).
    surum_bildir("99.0.1")
    surum_bildir("", "ulasilamadi")
    assert isler()["yeni_surum"]["surum"] == "99.0.1"


def test_yeni_surum_satiri_ayar_kapaliyken_yok(temiz):
    surum_bildir()
    ayar_yaz("guncelleme_denetimi", False)
    assert "yeni_surum" not in isler()


def test_yeni_surum_notu_basilmaz(temiz):
    ayar_yaz("guncelleme_durumu", {"zaman": vt.simdi(), "sonuc": "tamam", "surum": "99.0.1", "body": "sürüm notu <script>",
                                   "html_url": "https://kotu.example/indir"})  # fmt: skip
    s = isler()["yeni_surum"]
    assert "sürüm notu" not in repr(s) and "kotu.example" not in repr(s)


def test_b7_kacirilan_duyuru(temiz):
    with vt.islem() as b:
        for i, yas in enumerate((3600, 7200, 2 * 86400)):  # üçüncüsü 24 saatten eski: sayılmaz
            b.execute(
                "INSERT INTO duyuru (baslik, metin, sure_sn, kapatilabilir, hedef, olusturan, olusturma, durum) "
                "VALUES (?, 'gizli metin', 60, 1, '', 'x', ?, 'kacirildi')", (f"D{i}", vt.simdi() - yas))  # fmt: skip
    for k in (YONETICI, IDARECI):
        s = isler(k)["kacirilan"]
        assert s["baslik"] == "Sunucu kapalıyken 2 zamanlanmış duyuru kaçırıldı." and s["sayi"] == 2
        assert s["alt"] == "Duyurular sayfasından yeniden gönderebilirsiniz." and s["yol"] == "/duyurular#gecmis-baslik"
        assert "gizli metin" not in repr(s)


def test_b8_kilit_kodu_yok(temiz):
    ayar_yaz("kilit_kodu", "")
    y, i = isler()["kilit_kodu"], isler(IDARECI)["kilit_kodu"]
    assert y["baslik"] == i["baslik"] == "Kilit kodu tanımlı değil: kilitlenen tahta yalnız panelden açılır."
    assert (y["yol"], y["eylem"], i["yol"], i["eylem"], y["onem"]) == ("/ayarlar/kilit", "Kod belirle", "", "", "bilgi")


def test_b9_onay_bekleyen_tahta_role_gore(temiz):
    bekleyen_tahta(temiz["panel"], temiz["tahta"])
    bekleyen_tahta(temiz["panel"], temiz["tahta"])
    y = isler()["onay"]
    assert (y["baslik"], y["sayi"], y["yol"], y["rozet"], y["onem"]) == (
        "2 yeni tahta onay bekliyor.", 2, "/tahtalar#onay-bekleyen", "tahtalar", "uyari")  # fmt: skip
    i = isler(IDARECI)
    assert "onay" not in i
    assert (i["onay_i"]["baslik"], i["onay_i"]["yol"], i["onay_i"]["rozet"], i["onay_i"]["onem"]) == (
        "2 yeni tahta yöneticinin onayını bekliyor.", "", None, "bilgi")  # fmt: skip
    # Bekleyen tahtanın adı ve adresi hiçbir satırda yok (yalnız sayı).
    assert "etap-yeni" not in repr(liste()) and "10.0.0.20" not in repr(liste()) and "etap-yeni" not in repr(liste(IDARECI))


def test_ariza_satiri_ve_metni(temiz):
    for _ in range(2):
        temiz["panel"].post("/arizalar", data={"tahta_id": "1", "kategori": "acilis", "aciklama": "Uydurma arıza açıklaması"})
    for k in (YONETICI, IDARECI):
        s = isler(k)["ariza"]
        assert (s["baslik"], s["sayi"], s["yol"], s["rozet"], s["alt"]) == ("2 arıza kaydı açık.", 2, "/arizalar", "tahtalar", "")
        assert "Uydurma" not in repr(s) and "T-1" not in repr(s)  # açıklama ve tahta adı yazılmaz


def test_ogretim_yili_girilmedi_ve_gecti(temiz, saat):
    ayar_yaz("ogretim_yili_bitis", "")
    s = isler()["ogretim_yili"]
    assert s["baslik"].startswith("Öğretim yılı bitiş tarihi girilmedi") and (s["yol"], s["eylem"]) == ("/ayarlar/veri#saklama", "Tarihi gir")
    # Bugün'de kısa hâli durur (uzun açıklama Ayarlar › Veri'de): tek cümle, ayrıntı listesi yok.
    assert s["baslik"] == "Öğretim yılı bitiş tarihi girilmedi; öğrenci kayıtları kendiliğinden silinmiyor." and s["alt"] == ""
    ayar_yaz("ogretim_yili_bitis", "2026-11-10")
    s = isler()["ogretim_yili"]
    assert s["baslik"] == "Öğretim yılı bitiş tarihi (10.11.2026) geçti." and s["alt"] == "Yeni öğretim yılının bitiş tarihini girin."
    assert "ogretim_yili" not in isler(IDARECI)


def test_geri_yukleme_bekliyor(temiz, monkeypatch):
    monkeypatch.setattr(yedek, "bekleyen_oku", lambda: {"onaylandi": False, "hazirlama": vt.simdi()})
    s = isler()["geri_yukleme"]
    assert s["baslik"] == "Denetlenmiş bir yedek geri yükleme onayı bekliyor." and s["yol"] == "/yedekler?yer=geri"
    monkeypatch.setattr(yedek, "bekleyen_oku", lambda: {"onaylandi": True})
    assert isler()["geri_yukleme"]["baslik"] == "Geri yükleme onaylandı; program yeniden açılınca uygulanacak."
    assert "geri_yukleme" not in isler(IDARECI)


def test_guncel_olmayan_ajan_satiri(temiz):
    tahta_ekle(temiz["panel"], temiz["tahta"], "T-2", yeni_ajan_durumu(), surum="0.3.0")
    for k in (YONETICI, IDARECI):
        s = isler(k)["guncelleme_tahta"]
        assert (s["baslik"], s["yol"], s["sayi"]) == ("1 tahtada ajan güncellenebilir.", "/tahtalar?durum=guncelleme", 1)


def test_guncelleme_satiri_sayisi_hap_sayisiyla_ayni(temiz):
    for ad, surum in (("T-2", "0.3.0"), ("T-3", "0.12.0"), ("T-4", paket.ajan_paketi().surum)):
        tahta_ekle(temiz["panel"], temiz["tahta"], ad, yeni_ajan_durumu(), surum=surum)
    bekleyen_tahta(temiz["panel"], temiz["tahta"])  # onaysız tahta sayılmaz
    api = temiz["panel"].get("/api/durum").json()["tahtalar"]
    hap = tahta_liste.sayilar(api)["guncelleme"]
    with vt.islem() as b:
        assert bugun.guncel_olmayan_sayisi(b) == hap == 2
    # İki yol (kendi COUNT'u ve verilen tahta sayıları) aynı satırı üretir.
    assert isler()["guncelleme_tahta"] == isler(tahta_sayilari=tahta_liste.sayilar(api))["guncelleme_tahta"]
    assert "guncelleme_tahta" not in isler(tahta_sayilari={"guncelleme": 0})


def test_kurulum_satiri_kendi_satiri_olan_maddeyi_saymaz(temiz):
    assert "kurulum" not in isler()
    ayar_yaz("okul_adi", "")
    with vt.islem() as b:
        b.execute("DELETE FROM tahta_ders")
    # Kendi satırı olan dört madde de eksik: sayıya ve ada katılmaz.
    ayar_yaz("yedek", {})
    ayar_yaz("ogretim_yili_bitis", "")
    ayar_yaz("kilit_kodu", "")
    with vt.islem() as b:
        adresler.yaz(b, ["https://10.0.0.5:8788"])
    hepsi = isler(ipler=["10.0.0.9"])
    s = hepsi["kurulum"]
    assert (s["baslik"], s["alt"], s["yol"], s["eylem"], s["sayi"]) == (
        "Kurulumda 2 adım eksik.", "Okul adı, Derslik programı", "/ayarlar#kurulum", "Tamamla", 2)  # fmt: skip
    assert {"yedek_parola", "ogretim_yili", "adres", "kilit_kodu"} <= set(hepsi)
    assert "kurulum" not in isler(IDARECI, ipler=["10.0.0.9"])


# ---- rol, sıra, sınır ---------------------------------------------------------------------------------------
def hepsini_boz(temiz, monkeypatch) -> None:
    ayar_yaz("yedek", {})
    ayar_yaz("ogretim_yili_bitis", "")
    ayar_yaz("kilit_kodu", "")
    ayar_yaz("okul_adi", "")
    with vt.islem() as b:
        adresler.yaz(b, ["https://10.0.0.5:8788"])
        b.execute("INSERT INTO duyuru (baslik, metin, sure_sn, kapatilabilir, hedef, olusturan, olusturma, durum) "
                  "VALUES ('D', 'm', 60, 1, '', 'x', ?, 'kacirildi')", (vt.simdi() - 60,))  # fmt: skip
    bekleyen_tahta(temiz["panel"], temiz["tahta"])
    temiz["panel"].post("/arizalar", data={"tahta_id": "1", "kategori": "acilis", "aciklama": ""})
    tahta_ekle(temiz["panel"], temiz["tahta"], "T-2", yeni_ajan_durumu(), surum="0.3.0")
    surum_bildir()
    monkeypatch.setattr(yedek, "bekleyen_oku", lambda: {"onaylandi": False})


def test_bekleyenler_idarecide_yonetici_satiri_ve_adresi_yok(temiz, monkeypatch):
    hepsini_boz(temiz, monkeypatch)
    yonetici, idareci = isler(ipler=["10.0.0.9"]), isler(IDARECI, ipler=["10.0.0.9"])
    assert set(yonetici) == {"yedek_parola", "geri_yukleme", "adres", "ogretim_yili", "onay", "ariza", "kacirilan", "kilit_kodu",
                             "guncelleme_tahta", "yeni_surum", "kurulum"}  # fmt: skip
    assert set(idareci) == {"yedek_parola_i", "adres", "onay_i", "ariza", "kacirilan", "kilit_kodu", "guncelleme_tahta"}
    assert not YALNIZ_YONETICI & set(idareci)
    for s in idareci.values():
        assert not [a for a in YONETICI_ADRESLERI if a in s["yol"]], s
        assert not s["yol"].startswith("http") and s["dis"] is False, s
        assert bool(s["yol"]) == bool(s["eylem"]), s
    # Yöneticide her satır bir yere götürür.
    assert all(s["yol"] and s["eylem"] for s in yonetici.values())


def test_bekleyenler_sira_onem_sonra_cizelge(temiz, monkeypatch):
    hepsini_boz(temiz, monkeypatch)
    sira = [s["anahtar"] for s in liste(ipler=["10.0.0.9"])]
    assert sira == ["yedek_parola", "geri_yukleme", "adres", "ogretim_yili", "onay", "ariza", "kacirilan", "kilit_kodu",
                    "guncelleme_tahta", "yeni_surum", "kurulum"]  # fmt: skip
    onemler = [s["onem"] for s in liste(ipler=["10.0.0.9"])]
    assert onemler == sorted(onemler, key=bugun.ONEM_SIRASI.get)
    # İdarecide onay satırı bilgi önemindedir: uyarıların ardına düşer.
    assert [s["anahtar"] for s in liste(IDARECI, ipler=["10.0.0.9"])] == [
        "yedek_parola_i", "adres", "ariza", "kacirilan", "onay_i", "kilit_kodu", "guncelleme_tahta"]  # fmt: skip


def test_bekleyenler_ucten_cok_uyari_kesilmez(temiz, monkeypatch):
    """0.17.0'da altyapı uyarıları en çok üç bantla sınırlıydı; artık hiçbir satır kesilmez."""
    hepsini_boz(temiz, monkeypatch)
    yedek_tamam(basarili=False, hata="disk dolu")
    uyarilar = [s for s in liste(ipler=["10.0.0.9"]) if s["onem"] in ("tehlike", "uyari")]
    assert len(uyarilar) == 7 and len(liste(ipler=["10.0.0.9"])) == 11
    assert all(s["sayi"] >= 1 and s["onem"] in bugun.ONEM_SIRASI and s["simge"] for s in liste(ipler=["10.0.0.9"]))


def test_rozet_sayilari_ayni_listeden(temiz, monkeypatch):
    hepsini_boz(temiz, monkeypatch)
    temiz["panel"].post("/arizalar", data={"tahta_id": "1", "kategori": "acilis", "aciklama": ""})
    for k, beklenen in ((YONETICI, {"tahtalar": 3, "yedekler": 1}), (IDARECI, {"tahtalar": 2, "yedekler": 0})):
        tam = liste(k, ipler=["10.0.0.9"])
        rozetli = liste(k, yalniz_rozet=True)
        assert rozetli == [s for s in tam if s["rozet"]]  # aynı üretici, aynı koşul, aynı sayı
        assert bugun.rozet_sayilari(rozetli) == bugun.rozet_sayilari(tam) == beklenen
        assert bugun.satir_sayisi(rozetli, "ariza") == 2
    assert bugun.imza(liste(ipler=[])) != bugun.imza(liste(IDARECI, ipler=[]))
    assert "ariza:2" in bugun.imza(liste()) and "onay:1" in bugun.imza(liste())


def test_bekleyenler_islem_kaydina_yazmaz(temiz, monkeypatch):
    hepsini_boz(temiz, monkeypatch)
    once = sorgu("SELECT COUNT(*) AS n FROM kayit")[0]["n"]
    liste(ipler=["10.0.0.9"])
    liste(IDARECI, yalniz_rozet=True)
    assert sorgu("SELECT COUNT(*) AS n FROM kayit")[0]["n"] == once


# ---- tahtalar şu an -----------------------------------------------------------------------------------------
def gorunum(kimlik_: int, ad: str, bina: str = "", kat=None, cevrimici: bool = True, kilitli: bool = False, sinav=None,
            ariza: int = 0, **ek) -> dict:  # fmt: skip
    t = {"id": kimlik_, "ad": ad, "derslik": "", "bina": bina, "kat": kat, "duzeyler": [], "devre": "", "cevrimici": cevrimici,
         "kilitli": kilitli, "duyuru_var": False, "ekran_bagli": True, "surum": "0.3.0", "guncel": True, "oturum": "",
         "sinav": sinav, "ariza_sayisi": ariza, "program": {}, **ek}  # fmt: skip
    t["liste"] = tahta_liste.durum_ozeti(t)
    return t


SINAV = {"sinav_id": 1, "salon_id": 1, "sinav_adi": "Uydurma Sınav", "salon_adi": "S", "evre": "suruyor", "bitis_saat": "10:00"}


def ornek_tahtalar() -> list[dict]:
    return [
        gorunum(1, "9-A", "A Blok", 1),
        gorunum(2, "9-B", "A Blok", 1, kilitli=True),
        gorunum(3, "10-A", "A Blok", 2, cevrimici=False),
        gorunum(4, "Lab", "B Blok", None, ariza=1, guncel=False),
        gorunum(5, "Salon", "", 0, sinav=SINAV),
        gorunum(6, "Kapalı salon", "", 0, cevrimici=False, sinav=SINAV),
    ]


def test_tahta_ozeti_sayilar_tahta_liste_ile_ayni():
    tahtalar = ornek_tahtalar()
    ozet = bugun.tahta_ozeti(tahtalar)
    assert ozet["sayilar"] == tahta_liste.sayilar(tahtalar) and ozet["hepsi"] == 6 and ozet["cevrimici"] == 4
    assert [(k["anahtar"], k["ad"], k["sayi"]) for k in ozet["kutular"]] == [
        ("acik", "Açık", 3), ("kilitli", "Kilitli", 1), ("duyuru", "Duyuruda", 0), ("sorun", "Ekran sorunu", 0),
        ("cevrimdisi", "Çevrimdışı", 2), ("guncelleme", "Güncelleme", 1)]  # fmt: skip
    assert all(k["simge"].startswith("s-") for k in ozet["kutular"]) and ozet["kip"] == "cip"


def test_tahta_ozeti_grup_sirasi_listeyle_ayni():
    ozet = bugun.tahta_ozeti(ornek_tahtalar())
    liste_gruplari = tahta_liste.gruplar(ornek_tahtalar())
    assert [(g["no"], g["ad"], g["baslik"]) for g in ozet["gruplar"]] == [
        (no, g["ad"], g["baslik"]) for no, g in enumerate(liste_gruplari, start=1)]  # fmt: skip
    assert [[t["id"] for t in g["tahtalar"]] for g in ozet["gruplar"]] == [[t["id"] for t in g["tahtalar"]] for g in liste_gruplari]
    cipler = {t["id"]: t for g in ozet["gruplar"] for t in g["tahtalar"]}
    assert cipler[2]["birincil"] == "kilitli" and cipler[2]["okunur"] == "Kilitli" and cipler[2]["simge"] == "s-kilit"
    assert cipler[4]["ek"] == ["ariza"] and "Arıza" in cipler[4]["okunur"] and cipler[5]["ek"] == ["sinav"]
    assert ozet["grup_haritasi"] == {str(t["id"]): g["no"] for g in ozet["gruplar"] for t in g["tahtalar"]}
    # Çip yalnız ad, durum ve ek simge taşır: ders, oturum, sınav adı sözlükte yok.
    assert set(cipler[5]) == {"id", "ad", "no", "birincil", "simge", "okunur", "ek"} and "Uydurma Sınav" not in repr(ozet["gruplar"])


def test_cipin_okunur_metninde_bos_ders_yok():
    t = gorunum(1, "9-A", program={"bos_ders": "3. ders (kapalı)", "muaf": True})
    assert "Boş ders: 3. ders (kapalı)" in [r["m"] for r in t["liste"]["rozetler"]]  # satır rozeti listede durur
    assert bugun.cip_okunur(t["liste"]) == "Açık"  # Bugün'de ders bilgisi yok (kural 13)


def test_tahta_ozeti_altmistan_cok_tahtada_grup_kipi():
    altmis = [gorunum(i, f"T-{i}", "A Blok", i % 3) for i in range(1, 61)]
    assert bugun.tahta_ozeti(altmis)["kip"] == "cip"
    cok = altmis + [gorunum(61, "T-61", "A Blok", 0, kilitli=True), gorunum(62, "T-62", "A Blok", 0, cevrimici=False)]
    ozet = bugun.tahta_ozeti(cok)
    assert ozet["kip"] == "grup" and bugun.CIP_EN_COK == 60
    zemin = next(g for g in ozet["gruplar"] if g["ad"] == "A Blok · Zemin kat")
    assert zemin["sayi"] == 22 and zemin["ozet"] == "20 açık · 1 kilitli · 1 çevrimdışı"


def test_kilit_hedefi_sinavdaki_ve_cevrimdisini_saymaz():
    ozet = bugun.tahta_ozeti(ornek_tahtalar())
    assert (ozet["kilit_hedefi"], ozet["kilit_sinavda"], ozet["kilit_cevrimdisi"], ozet["sinavda"]) == (3, 1, 2, 2)
    bos = bugun.tahta_ozeti([])
    assert (bos["hepsi"], bos["kilit_hedefi"], bos["gruplar"]) == (0, 0, [])


# ---- yoklama · bugün ----------------------------------------------------------------------------------------
def yoklama_ozeti(zaman) -> dict:
    with vt.islem() as b:
        return bugun.yoklama_ozeti(b, int(zaman.timestamp()))


@pytest.fixture()
def yoklamali(hazir, panel, saat):  # noqa: F811
    """hazir (10/A dört, 10/B iki öğrenci) + hafta içi dört derslik zil düzeni (08:20–11:30); çarşamba 18.11.2026."""
    zil_yaz()
    saat.ayarla(an(18, 12))
    gir(panel, "yonetici")  # panel oturumu 12 saatte biter; saat iki gün ilerledi
    return hazir


def test_yoklama_ozeti_sayilari(yoklamali):
    kayit(18, "10/A", 1, yok=["1047", "1102"], gec=["1150"])
    kayit(18, "10/A", 2, yok=["1047"])
    kayit(18, "10/B", 6, yok=["2001"])  # plan dışı ders numarası: paya ve paydaya birlikte girer
    kayit(17, "10/A", 1, yok=["0215"])  # dün: sayılmaz
    # 10:00 → 1. ders (09:00 + 15 dk) beklenir; 2. ders 09:50'de bitti, payı 10:05'te dolar.
    o = yoklama_ozeti(an(18, 10))
    assert (o["etkin"], o["tatil"], o["liste_var"], o["program_var"]) == (True, None, True, True)
    assert (o["beklenen"], o["alinan"]) == (3, 2)  # 10/A 1. ders (alındı), 10/B 1. ders (alınmadı), 10/B plan dışı 6
    assert o["subeler"] == [{"ad": "10/A", "alinan": 1, "beklenen": 1}, {"ad": "10/B", "alinan": 1, "beklenen": 2}]
    assert (o["yok"], o["gec"], o["kayit"]) == (3, 1, 3)  # ayrı öğrenci: 1047 iki derste yok ama bir kez sayılır
    o = yoklama_ozeti(an(18, 12))  # dört dersin de payı doldu
    assert (o["beklenen"], o["alinan"]) == (9, 3)
    assert o["nota"] == bugun.YOKLAMA_NOTU and set(o) == {
        "etkin", "tatil", "program_var", "liste_var", "beklenen", "alinan", "kayit", "yok", "gec", "subeler", "sube_fazla", "nota"}  # fmt: skip


def test_yoklama_ozeti_duzeltme_katmani_gecerli(yoklamali):
    """Sayılar tek birleşim kuralından (kural 34): panel düzeltmesi yok'u var'a çevirince sayı düşer."""
    from tahta_sunucu import yoklama_defter as yd

    kayit(18, "10/A", 1, yok=["1047", "1102"], zaman=int(an(18, 9).timestamp()))
    assert yoklama_ozeti(an(18, 12))["yok"] == 2
    with vt.islem() as b:
        yd.hucre_yaz(b, gun=date(2026, 11, 18), sube="10/A", ders_no=1, ogrenci_id=ogrenci_id("1102"), durum="var",
                     giren="yonetici", an=int(an(18, 11).timestamp()), aciklama="yanlış işaret")  # fmt: skip
    assert yoklama_ozeti(an(18, 12))["yok"] == 1


def test_yoklama_ozeti_mazeretli_ogrenci_yok_sayisinda_ve_tur_yok(yoklamali):
    kayit(18, "10/A", 1, yok=["1047"])
    with vt.islem() as b:
        b.execute("INSERT INTO yoklama_mazeret (ogrenci_id, bas_tarih, bit_tarih, tur, giren, olusturma) "
                  "VALUES (?, '2026-11-18', '2026-11-18', 'raporlu', 'yonetici', ?)", (ogrenci_id("1047"), vt.simdi()))  # fmt: skip
    o = yoklama_ozeti(an(18, 12))
    assert o["yok"] == 1 and "raporlu" not in repr(o) and "1047" not in repr(o)


def test_yoklama_ozeti_kapaliyken(yoklamali):
    with vt.islem() as b:
        vt.ayar_yaz(b, "yoklama", {**yk.ayar_al(b), "etkin": False})
    assert yoklama_ozeti(an(18, 12)) == {"etkin": False}


def test_yoklama_ozeti_tatilde(yoklamali):
    ayar_yaz("zil_takvimi", {"kurallar": [{"tur": "tatil", "ad": "Uydurma tatil", "bas": "2026-11-18", "bit": "2026-11-18"}]})
    o = yoklama_ozeti(an(18, 12))
    assert o["tatil"] == "Uydurma tatil" and o["beklenen"] == 0 and o["program_var"] is False


def test_yoklama_ozeti_liste_yokken(panel, saat):
    kur_ve_gir(panel)
    with vt.islem() as b:
        vt.ayar_yaz(b, "yoklama", {**yk.ayar_al(b), "etkin": True})
    o = yoklama_ozeti(an(16, 12))
    assert o["etkin"] and o["liste_var"] is False and o["subeler"] == [] and (o["beklenen"], o["kayit"]) == (0, 0)


def test_yoklama_ozeti_kirktan_cok_sube(yoklamali):
    with vt.islem() as b:
        b.executemany("INSERT INTO ogrenci (okul_no, ad, soyad, sube, aktif, guncelleme) VALUES (?, 'Uydurma', 'ÖĞRENCİ', ?, 1, 0)",
                      [(str(5000 + i), f"9/{chr(65 + i % 26)}{i // 26}") for i in range(45)])  # fmt: skip
    o = yoklama_ozeti(an(18, 12))
    assert len(o["subeler"]) == bugun.SUBE_HAPI_EN_COK == 40 and o["sube_fazla"] == 7


# ---- duyurular ---------------------------------------------------------------------------------------------
def test_duyuru_ozeti_ekranda_ve_bugun_planli(panel, tahta, saat):
    kur_ve_gir(panel)
    tahta_ekle(panel, tahta, "T-1", yeni_ajan_durumu())
    simdi = vt.simdi()  # pazartesi 16.11.2026 09:00
    with vt.islem() as b:
        for baslik, bitis, durum in (("Ekrandaki", simdi + 600, "gonderildi"), ("", simdi + 1200, "gonderildi"),
                                     ("Bitmiş", simdi - 60, "gonderildi"), ("Durdurulmuş", simdi + 600, "durduruldu")):  # fmt: skip
            b.execute(
                "INSERT INTO duyuru (baslik, metin, sure_sn, kapatilabilir, hedef, olusturan, olusturma, an, bitis, durum, tahta_sayisi) "
                "VALUES (?, 'GİZLİ DUYURU METNİ', 600, 1, '', 'Uydurma Kişi', ?, ?, ?, ?, 3)", (baslik, simdi, simdi, bitis, durum))  # fmt: skip
    with vt.islem() as b:
        # (başlık, saat, başlangıç, bitiş, durum): yarınki, saati geçmiş ve duraklatılan plan bugünün listesine girmez.
        for baslik, saat_, bas, bit, durum in (
            ("Bugünkü plan", "13:00", "2026-11-16", "2026-11-20", "etkin"), ("Yarınki plan", "08:00", "2026-11-17", "2026-11-20", "etkin"),
            ("Geçmiş saat", "08:00", "2026-11-16", "2026-11-16", "etkin"), ("Duraklatılan", "14:00", "2026-11-16", "2026-11-20", "duraklatildi"),
        ):  # fmt: skip
            b.execute(
                "INSERT INTO duyuru_plani (baslik, metin, sure_sn, kapatilabilir, hedef_json, tekrar, saat, baslangic, bitis, gunler, "
                "durum, gecerlilik, olusturan, olusturma) VALUES (?, 'GİZLİ PLAN METNİ', 60, 1, '{}', 'gunluk', ?, ?, ?, '0,1,2,3,4', ?, 0, "
                "'Uydurma Kişi', 0)", (baslik, saat_, bas, bit, durum))  # fmt: skip
        o = bugun.duyuru_ozeti(b, simdi)
    assert o["ekranda"] == [{"baslik": "Başlıksız duyuru", "tahta_sayisi": 3, "bitis": "09:20'de"},
                            {"baslik": "Ekrandaki", "tahta_sayisi": 3, "bitis": "09:10'da"}]  # fmt: skip
    assert o["planli"] == [{"saat": "13:00", "baslik": "Bugünkü plan"}]
    assert (o["ekranda_fazla"], o["planli_fazla"]) == (0, 0)
    assert "GİZLİ" not in repr(o) and "Uydurma Kişi" not in repr(o) and "metin" not in repr(o)


def test_duyuru_ozeti_fazlasi_sayilir(panel, saat):
    kur_ve_gir(panel)
    simdi = vt.simdi()
    with vt.islem() as b:
        for i in range(5):
            b.execute(
                "INSERT INTO duyuru (baslik, metin, sure_sn, kapatilabilir, hedef, olusturan, olusturma, an, bitis, durum, tahta_sayisi) "
                "VALUES (?, 'm', 600, 1, '', 'x', ?, ?, ?, 'gonderildi', 1)", (f"D{i}", simdi, simdi + i, simdi + 600))  # fmt: skip
        o = bugun.duyuru_ozeti(b, simdi)
    assert [d["baslik"] for d in o["ekranda"]] == ["D4", "D3", "D2"] and o["ekranda_fazla"] == 2 and o["planli"] == []


# ---- akış --------------------------------------------------------------------------------------------------
def test_akis_tek_ve_iki_devre(panel, saat):
    kur_ve_gir(panel)
    with vt.islem() as b:
        assert bugun.akis(b, an(16, 9, 30)) == []  # zil saati yok
    zil_yaz()
    with vt.islem() as b:
        tek = bugun.akis(b, an(16, 9, 30))
        assert bugun.akis(b, an(21, 9, 30)) == []  # cumartesi: ders yok
    assert len(tek) == 1 and tek[0]["devre"] == ""  # tek devrede devre adı gösterilmez (kural 25)
    assert tek[0]["dersler"] == [{"no": 1, "bas": "08:20", "durum": "gecti"}, {"no": 2, "bas": "09:10", "durum": "simdi"},
                                 {"no": 3, "bas": "10:00", "durum": "gelecek"}, {"no": 4, "bas": "10:50", "durum": "gelecek"}]  # fmt: skip
    zil_yaz(devre="ogle", ad="Öğleden sonra", saatler=[("13:00", "13:40"), ("13:50", "14:30")])
    with vt.islem() as b:
        iki = bugun.akis(b, an(16, 13, 10))
    assert [s["devre"] for s in iki] == ["Normal", "Öğleden sonra"]
    assert [d["durum"] for d in iki[0]["dersler"]] == ["gecti"] * 4 and [d["durum"] for d in iki[1]["dersler"]] == ["simdi", "gelecek"]
    assert set(iki[1]["dersler"][0]) == {"no", "bas", "durum"}  # ders adı, şube, öğretmen yok


# ---- performans --------------------------------------------------------------------------------------------
def _select_sayisi(islev) -> int:
    sayac = [0]

    def say(sql: str) -> None:
        if sql.lstrip().upper().startswith("SELECT"):
            sayac[0] += 1

    asil = sqlite3.connect

    def izli(*a, **kw):
        baglanti = asil(*a, **kw)
        baglanti.set_trace_callback(say)
        return baglanti

    sqlite3.connect = izli
    try:
        islev()
    finally:
        sqlite3.connect = asil
    return sayac[0]


def test_bugun_sorgu_sayisi_tahta_ve_ogrenci_sayisindan_bagimsiz(yoklamali, panel, tahta):
    kayit(18, "10/A", 1, yok=["1047"])

    def uretimler() -> None:
        with vt.islem() as b:
            bugun.bekleyenler(b, YONETICI, ipler=[])
            bugun.bekleyenler(b, IDARECI, ipler=[], yalniz_rozet=True)
            bugun.yoklama_ozeti(b, vt.simdi())
            bugun.duyuru_ozeti(b, vt.simdi())
            bugun.akis(b, an(18, 12))

    def sayfa() -> None:
        assert panel.get("/").status_code == 200

    def api() -> None:
        assert panel.get("/api/durum").status_code == 200

    az = (_select_sayisi(uretimler), _select_sayisi(sayfa), _select_sayisi(api))
    with vt.islem() as b:
        simdi = vt.simdi()
        b.executemany(
            "INSERT INTO tahta (ad, anahtar_ozet, durum, kayit_zamani, son_gorulme, surum, bina, kat, subeler) "
            "VALUES (?, 'x', 'onayli', ?, ?, '0.3.0', ?, ?, ?)",
            [(f"T-{i}", simdi, simdi if i % 4 else simdi - 10 * ayar.CEVRIMICI_ESIK_SN, f"Blok {i % 3}", i % 4, f"9/{chr(65 + i % 12)}")
             for i in range(60)])  # fmt: skip
        b.executemany("INSERT INTO ogrenci (okul_no, ad, soyad, sube, aktif, guncelleme) VALUES (?, 'Uydurma', 'ÖĞRENCİ', ?, 1, 0)",
                      [(str(6000 + i), f"9/{chr(65 + i % 12)}") for i in range(360)])  # fmt: skip
        b.executemany("INSERT INTO duyuru_plani (baslik, metin, sure_sn, kapatilabilir, hedef_json, tekrar, saat, baslangic, bitis, "
                      "gunler, gecerlilik, olusturan, olusturma) VALUES (?, 'm', 60, 1, '{}', 'gunluk', '13:00', '2026-11-16', "
                      "'2026-11-20', '0,1,2,3,4', 0, 'x', 0)", [(f"P{i}",) for i in range(20)])  # fmt: skip
    for i in range(12):
        kayit(18, f"9/{chr(65 + i)}", 1, yok=[str(6000 + i)])
    cok = (_select_sayisi(uretimler), _select_sayisi(sayfa), _select_sayisi(api))
    assert cok == az, (az, cok)
    assert az[0] <= 40 and az[1] <= 75 and az[2] <= 50, az


def test_acik_satir_sayisi_uyariyi_katlamaz():
    """Tehlike ve uyarı satırı "Diğer N iş" içine düşmez; yalnız bilgi satırı katlanır."""
    def satirlar(uyari: int, bilgi: int) -> list[dict]:
        return [{"onem": "uyari"}] * uyari + [{"onem": "bilgi"}] * bilgi

    assert bugun.acik_satir_sayisi(satirlar(2, 2)) == bugun.ACIK_SATIR == 6
    assert bugun.acik_satir_sayisi(satirlar(4, 5)) == 6  # dört uyarı + iki bilgi açık, üç bilgi katlı
    assert bugun.acik_satir_sayisi(satirlar(8, 3)) == 8  # sekiz uyarının hepsi açık
    assert bugun.acik_satir_sayisi([{"onem": "tehlike"}] * 7 + satirlar(2, 1)) == 9


def test_kurulum_satiri_disaridan_verilince_uretici_calismaz(temiz, monkeypatch):
    """/api/durum `kurulum` satırını bellekten verir: liste aynıdır, üretici (dokuz ayar okuması) yeniden çalışmaz."""
    from tahta_sunucu import ayar_bolumleri

    tam = liste()
    with vt.islem() as b:
        satir = bugun.kurulum_satiri(b, YONETICI, ipler=[])
        assert bugun.kurulum_satiri(b, IDARECI, ipler=[]) == []
    assert satir == [s for s in tam if s["anahtar"] == "kurulum"]
    monkeypatch.setattr(ayar_bolumleri, "kurulum", lambda *a, **k: pytest.fail("kurulum yeniden hesaplandı"))
    assert liste(kurulum=satir) == tam
