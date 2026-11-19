"""Aşama 6A sunucu yanı: şifreli yedek, geri yükleme, adres listesi, envanter, arıza (uydurma veriyle)."""

from __future__ import annotations

import io
import json
import sqlite3
import struct
import threading
import zipfile

import pytest
from fastapi.testclient import TestClient
from yardimci import (
    PAROLA,
    SAHTE_TC,
    bekle,
    gir,
    ileti,
    kimlik,
    kullanici_ekle,
    kur_ve_gir,
    sorgu,
    tahta_ekle,
)

YEDEK_PAROLASI = "uzun-yedek-parolasi-1"
ENV = {
    "bicim": 1, "uretici": "Örnek Teknoloji", "model": "ET-75 Etkileşimli Tahta", "urun_seri": "ORN75X000123",
    "anakart_seri": "MB0000456", "islemci": "Örnek İşlemci", "cekirdek_sayisi": 8, "bellek_mb": 7843,
    "diskler": [{"ad": "sda", "model": "ÖRNEK SSD 256", "boyut_gb": 238, "ssd": True}], "ekran": "3840x2160",
    "dokunmatik": ["Örnek TouchScreen"], "ag": [{"arayuz": "enp2s0", "mac": "02:00:00:aa:bb:01", "kablosuz": False}],
    "isletim_sistemi": "Pardus 23 ETAP", "cekirdek": "6.1.0-00-amd64", "ajan_surumu": "0.7.0",
}  # fmt: skip
YENI_YETENEKLER = ["acil", "duyuru_id", "adres_listesi", "envanter", "ariza"]


@pytest.fixture(autouse=True)
def hizli_kdf(monkeypatch):
    from tahta_sunucu import yedek

    monkeypatch.setattr(yedek, "KDF_VARSAYILAN", {"n": 2**12, "r": 8, "p": 1})


@pytest.fixture()
def kurulu(panel, uygulama):
    """Kurulum + sunucu sertifikası (yedek sertifikayı da taşır; testte Sunucu() çalışmadığı için üretilir)."""
    from tahta_sunucu import ayar, guvenlik

    guvenlik.sertifika_hazirla(ayar.veri_dizini())
    kur_ve_gir(panel)
    return panel


def parola_belirle(panel, parola=YEDEK_PAROLASI):
    return panel.post("/yedekler/parola", data={"hesap_parolasi": PAROLA, "parola": parola, "parola2": parola})


def yeni_durum(**ek) -> dict:
    return {"kilitli": False, "yetenekler": YENI_YETENEKLER, "ekranlar": [{"arayuz": "gtk3"}], **ek}


def yedek_dosyasi() -> tuple[str, bytes]:
    from tahta_sunucu import yedek

    son = yedek.listele()[0]
    return son["ad"], (yedek.dizin() / son["ad"]).read_bytes()


# ---- veri dizini ve yerel durum --------------------------------------------------------
def test_veri_dizini_ortam_degiskeni_her_seyi_ezer(tmp_path, monkeypatch):
    from tahta_sunucu import ayar

    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path / "x"))
    assert ayar.veri_dizini() == tmp_path / "x"


def test_yerel_durum_yalniz_yerelden(kurulu, uygulama):
    yanit = kurulu.get("/yerel/durum")
    assert yanit.status_code == 200
    veri = yanit.json()
    assert set(veri) == {"surum", "ag_adresleri", "parmak_izi_kisa", "yedek_parolasi_var", "son_yedek", "paket_imzali", "hizmet"}
    assert veri["hizmet"] is False and veri["yedek_parolasi_var"] is False and len(veri["parmak_izi_kisa"]) == 16
    uzak = TestClient(uygulama, client=("10.0.0.20", 40000))
    assert uzak.get("/yerel/durum").status_code == 404


# ---- yedek parolası ve yedek alma ---------------------------------------------------------
def test_yedek_parolasi_hesap_parolasi_olmadan_belirlenemez(kurulu):
    yanit = kurulu.post("/yedekler/parola", data={"hesap_parolasi": "yanlis", "parola": YEDEK_PAROLASI, "parola2": YEDEK_PAROLASI})
    assert "doğrulanamadı" in ileti(yanit)
    assert "en az 12" in ileti(parola_belirle(kurulu, "kisa-parola"))
    assert sorgu("SELECT * FROM ayar WHERE anahtar = 'yedek'") == []
    assert "belirlendi" in ileti(parola_belirle(kurulu))
    assert any(k["islem"] == "Yedek parolası belirlendi" for k in sorgu("SELECT islem FROM kayit"))


def test_yedek_parolasi_sunucuda_saklanmaz(kurulu):
    parola_belirle(kurulu)
    deger = json.loads(sorgu("SELECT deger FROM ayar WHERE anahtar = 'yedek'")[0]["deger"])
    assert set(deger) == {"acik_anahtar", "tuz", "n", "r", "p", "parola_zamani", "saklama", "kopya_dizini"}
    hepsi = json.dumps(sorgu("SELECT * FROM ayar")) + json.dumps(sorgu("SELECT * FROM kayit"))
    assert YEDEK_PAROLASI not in hepsi


def test_yedek_al_ve_ayni_parolayla_coz(kurulu):
    from tahta_sunucu import yedek

    assert "parolası belirlenmedi" in ileti(kurulu.post("/yedekler/al"))
    parola_belirle(kurulu)
    assert "Yedek alındı" in ileti(kurulu.post("/yedekler/al"))
    ad, veri = yedek_dosyasi()
    assert yedek.AD_DESENI.match(ad) and ad.startswith("tahta-kontrol-elle-2026-11-16-090000")
    assert "Örnek Anadolu".encode() not in veri  # okul adı yalnız şifreli içerikte
    bilgi, dosyalar = yedek.coz(veri, YEDEK_PAROLASI)
    assert sorted(dosyalar) == sorted(yedek.ZIP_DOSYALARI)
    assert bilgi["okul_adi"] == "Örnek Anadolu Lisesi" and bilgi["kullanici_sayisi"] == 1
    assert "Yedek alındı" in kurulu.get("/kayit").text


def test_yanlis_parola_net_ileti_verir_ve_dosya_yazilmaz(kurulu):
    from tahta_sunucu import yedek

    parola_belirle(kurulu)
    kurulu.post("/yedekler/al")
    ad, veri = yedek_dosyasi()
    with pytest.raises(yedek.YedekHatasi, match="parolası yanlış"):
        yedek.coz(veri, "baska-parola-12345")
    yanit = kurulu.post("/yedekler/geri-yukle", files={"dosya": (ad, veri)}, data={"parola": "baska-parola-12345"})
    assert "parolası yanlış" in ileti(yanit)
    assert yedek.bekleyen_oku() is None and not (yedek.bekleyen_dizini() / "bekleyen").exists()
    assert sorgu("SELECT COUNT(*) AS n FROM kayit WHERE islem = 'Başarısız geri yükleme denemesi'")[0]["n"] == 1


def test_bozulmus_yedek_reddedilir(kurulu):
    from tahta_sunucu import yedek

    parola_belirle(kurulu)
    kurulu.post("/yedekler/al")
    _, veri = yedek_dosyasi()
    bozuk = bytearray(veri)
    bozuk[-5] ^= 1
    with pytest.raises(yedek.YedekHatasi, match="bozuk ya da değiştirilmiş"):
        yedek.coz(bytes(bozuk), YEDEK_PAROLASI)
    # başlıktaki sürümü değiştir: AAD tutmaz
    baslik_uzunluk = struct.unpack(">I", veri[8:12])[0]
    baslik = json.loads(veri[12 : 12 + baslik_uzunluk])
    baslik["surum"] = "9.9.9"
    yeni = json.dumps(baslik, separators=(",", ":")).encode()
    with pytest.raises(yedek.YedekHatasi, match="bozuk ya da değiştirilmiş"):
        yedek.coz(veri[:8] + struct.pack(">I", len(yeni)) + yeni + veri[12 + baslik_uzunluk :], YEDEK_PAROLASI)
    with pytest.raises(yedek.YedekHatasi, match="Tahta Kontrol yedeği değil"):
        yedek.coz(b"PK\x03\x04" + veri[4:], YEDEK_PAROLASI)


def _yeniden_sifrele(veri: bytes, zip_degistir=None, baslik_degistir=None) -> bytes:
    """Testlerde kötü niyetli dosya üretmek için: çözüp içeriği/başlığı değiştirerek aynı açık anahtarla şifreler."""
    from tahta_sunucu import vt, yedek

    baslik, _, _ = yedek.baslik_oku(veri)
    _, dosyalar = yedek.coz(veri, YEDEK_PAROLASI)
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as arsiv:
        for ad, icerik in dosyalar.items():
            arsiv.writestr(ad, icerik)
        if zip_degistir:
            zip_degistir(arsiv)
    with vt.islem() as b:
        ayar_ = yedek.ayarlar(b)
    if baslik_degistir:
        ayar_ = {**ayar_, **baslik_degistir}
    return yedek.sifrele(tampon.getvalue(), ayar_, "elle", baslik["olusturma"], baslik["sema"])


def test_kotu_kdf_parametreli_dosya_reddedilir(kurulu):
    from tahta_sunucu import yedek

    parola_belirle(kurulu)
    kurulu.post("/yedekler/al")
    _, veri = yedek_dosyasi()
    kotu = _yeniden_sifrele(veri, baslik_degistir={"n": 2**30})
    with pytest.raises(yedek.YedekHatasi, match="sınırların dışında"):
        yedek.coz(kotu, YEDEK_PAROLASI)


def test_zip_icinde_beklenmeyen_dosya_reddedilir(kurulu):
    from tahta_sunucu import yedek

    parola_belirle(kurulu)
    kurulu.post("/yedekler/al")
    _, veri = yedek_dosyasi()
    for ek in ("../x", "fazla.txt"):
        kotu = _yeniden_sifrele(veri, zip_degistir=lambda arsiv, ad=ek: arsiv.writestr(ad, b"x"))
        with pytest.raises(yedek.YedekHatasi, match="beklenmeyen dosya"):
            yedek.coz(kotu, YEDEK_PAROLASI)


def test_daha_yeni_semali_yedek_reddedilir(kurulu, monkeypatch):
    from tahta_sunucu import vt, yedek

    parola_belirle(kurulu)
    kurulu.post("/yedekler/al")
    _, veri = yedek_dosyasi()
    monkeypatch.setattr(vt, "GOCLER", vt.GOCLER[:-1])
    with pytest.raises(yedek.YedekHatasi, match="daha yeni bir Tahta Kontrol"):
        yedek.coz(veri, YEDEK_PAROLASI)


def test_gunluk_yedek_ayni_gun_yeniden_uretilmez(kurulu):
    from tahta_sunucu import yedek

    parola_belirle(kurulu)
    ilk = yedek.yedek_al("gunluk")
    assert ilk["yeni"] and ilk["dosya"] == "tahta-kontrol-gunluk-2026-11-16.tkyedek"
    assert yedek.yedek_al("gunluk")["yeni"] is False


def test_saklama_sayisi_eski_gunlukleri_siler_elle_alinanlar_ayri(kurulu, saat):
    from tahta_sunucu import yedek

    parola_belirle(kurulu)
    assert "kaydedildi" in ileti(kurulu.post("/yedekler/ayar", data={"saklama": "3", "kopya_dizini": ""}))
    assert "3–90" in ileti(kurulu.post("/yedekler/ayar", data={"saklama": "2", "kopya_dizini": ""}))
    for _ in range(5):
        yedek.yedek_al("gunluk")
        yedek.yedek_al("elle")
        saat.ilerlet(86400)
    adlar = [y["ad"] for y in yedek.listele()]
    gunlukler = [a for a in adlar if "-gunluk-" in a]
    assert gunlukler == [f"tahta-kontrol-gunluk-2026-11-{g}.tkyedek" for g in (20, 19, 18)]
    # Elle alınanlar da yaşa göre budanır: saklama (3) günden eski olan (16.11) silindi.
    assert sorted(a[19:29] for a in adlar if "-elle-" in a) == [f"2026-11-{g}" for g in (17, 18, 19, 20)]


def test_eski_elle_yedek_ikinci_kopyada_da_silinir(kurulu, saat, tmp_path):
    """KVKK: seyrek alınan elle yedek süreli silinen kişisel veriyi saklama süresinden uzun taşımaz."""
    from tahta_sunucu import yedek

    parola_belirle(kurulu)
    kopya = tmp_path / "ikinci"
    kopya.mkdir()
    kurulu.post("/yedekler/ayar", data={"saklama": "14", "kopya_dizini": str(kopya)})
    eski = yedek.yedek_al("elle")["dosya"]
    saat.ilerlet(10 * 86400)
    yedek.yedek_al("gunluk")
    assert (yedek.dizin() / eski).exists() and (kopya / eski).exists()  # 10 gün: süre dolmadı
    saat.ilerlet(5 * 86400)
    yedek.yedek_al("gunluk")
    assert not (yedek.dizin() / eski).exists() and not (kopya / eski).exists()
    assert [y["tur"] for y in yedek.listele()] == ["gunluk", "gunluk"]


def test_geri_yukleme_kalintilari_budanir(kurulu, uygulama, saat):
    """Onaysız bekleyen (şifresiz) 1 gün sonra, geri yükleme öncesi kopyalar saklama süresi sonra silinir."""
    from tahta_sunucu import ayar, yedek

    parola_belirle(kurulu)
    yedek.yedek_al("elle")
    _, veri = yedek_dosyasi()
    yedek.bekleyeni_hazirla(veri, YEDEK_PAROLASI)
    bekleyen = ayar.veri_dizini() / "geri-yukleme" / "bekleyen"
    assert yedek.kalintilari_temizle(14, saat.t + 3600) == [] and bekleyen.exists()
    assert yedek.kalintilari_temizle(14, saat.t + 25 * 3600) == ["geri-yukleme/bekleyen"]
    assert not bekleyen.exists() and yedek.bekleyen_oku() is None
    # Onaylanmış olan (açılışta uygulanacak) silinmez.
    yedek.bekleyeni_hazirla(veri, YEDEK_PAROLASI)
    yedek.bekleyeni_onayla()
    assert yedek.kalintilari_temizle(14, saat.t + 30 * 3600) == [] and bekleyen.exists()
    yedek.bekleyeni_sil()
    # geri-yukleme-oncesi: yalnız en yeni klasör kalır; o da saklama gününden eskiyse silinir.
    kok = ayar.veri_dizini() / "geri-yukleme-oncesi"
    for ad in ("01.11.2026-100000", "10.11.2026-100000"):
        (kok / ad).mkdir(parents=True)
        (kok / ad / "tahta-kontrol.db").write_bytes(b"x")
    assert yedek.kalintilari_temizle(14, saat.t) == ["geri-yukleme-oncesi/01.11.2026-100000"]
    assert yedek.kalintilari_temizle(14, saat.t + 10 * 86400) == ["geri-yukleme-oncesi/10.11.2026-100000"]
    assert list(kok.iterdir()) == []
    # Zamanlayıcı da budar ve işlem kaydına düşer.
    yedek.bekleyeni_hazirla(veri, YEDEK_PAROLASI)
    saat.ilerlet(2 * 86400)
    uygulama.state.yedek_zamanlayici()
    assert yedek.bekleyen_oku() is None
    assert "Geri yükleme kalıntıları silindi" in [k["islem"] for k in sorgu("SELECT islem FROM kayit")]


def test_izin_komutu_programi_calistiran_hesaba_verilir(kurulu, monkeypatch):
    from tahta_sunucu import ayar, yedek

    monkeypatch.setenv("USERNAME", "ornekkullanici")
    monkeypatch.setenv("USERDOMAIN", "ORNEKPC")
    monkeypatch.setattr(ayar, "HIZMET", False)
    assert yedek.izin_komutu(r"D:\TahtaYedek") == r'icacls "D:\TahtaYedek" /grant "ORNEKPC\ornekkullanici:(OI)(CI)M"'
    assert r"ORNEKPC\ornekkullanici" in kurulu.get("/yedekler").text
    monkeypatch.setattr(ayar, "HIZMET", True)  # 6B hizmet kipi: LocalService
    assert "*S-1-5-19" in yedek.izin_komutu(r"D:\TahtaYedek")


def test_ikinci_kopya_klasoru_denetlenir_ve_yazilir(kurulu, tmp_path):
    from tahta_sunucu import yedek

    parola_belirle(kurulu)
    assert "tam yol" in ileti(kurulu.post("/yedekler/ayar", data={"saklama": "14", "kopya_dizini": "goreli\\klasor"}))
    assert "bulunamadı" in ileti(kurulu.post("/yedekler/ayar", data={"saklama": "14", "kopya_dizini": str(tmp_path / "yok")}))
    kopya = tmp_path / "ikinci"
    kopya.mkdir()
    assert "kaydedildi" in ileti(kurulu.post("/yedekler/ayar", data={"saklama": "14", "kopya_dizini": str(kopya)}))
    sonuc = yedek.yedek_al("gunluk")
    assert (kopya / sonuc["dosya"]).read_bytes() == (yedek.dizin() / sonuc["dosya"]).read_bytes()
    assert not (kopya / yedek.YAZMA_DENEMESI).exists()


def test_parola_yoksa_otomatik_yedek_alinmaz_pano_uyarir(kurulu, uygulama, saat):
    from tahta_sunucu import yedek

    zamanlayici = uygulama.state.yedek_zamanlayici
    saat.ilerlet(600)
    assert zamanlayici() is False and yedek.listele() == []
    assert "Yedek parolası belirlenmedi; otomatik yedek alınmıyor." in kurulu.get("/").text
    parola_belirle(kurulu)
    assert "Yedek parolası belirlenmedi" not in kurulu.get("/").text
    uygulama.state.acilis = saat.t - 60  # program yeni açıldı: 5 dk beklenir
    assert zamanlayici() is False
    saat.ilerlet(300)
    assert zamanlayici() is True
    assert zamanlayici() is False  # bugünün günlüğü var
    assert [y["tur"] for y in yedek.listele()] == ["gunluk"]


def test_yavas_ikinci_diskte_normal_islem_surer_elle_yedek_cakismaz(kurulu, uygulama, saat, tmp_path, monkeypatch):
    from tahta_sunucu import vt, yedek
    from tahta_sunucu.yedek_is import YedekIsleyici

    parola_belirle(kurulu)
    kopya = tmp_path / "ikinci-disk"
    kopya.mkdir()
    with vt.islem() as b:
        ayarlar = yedek.ayarlar(b)
        ayarlar["kopya_dizini"] = str(kopya)
        vt.ayar_yaz(b, "yedek", ayarlar)
    asil_yaz = yedek._atomik_yaz
    basladi, birak = threading.Event(), threading.Event()

    def yavas_yaz(hedef, veri):
        if hedef.parent == kopya:
            basladi.set()
            assert birak.wait(5)
        return asil_yaz(hedef, veri)

    monkeypatch.setattr(yedek, "_atomik_yaz", yavas_yaz)
    saat.ilerlet(600)
    isleyici = YedekIsleyici()
    try:
        assert isleyici.baslat(uygulama.state.yedek_zamanlayici)
        assert basladi.wait(3)
        with vt.islem() as b:
            vt.ayar_yaz(b, "deneme", "program işlemi tamamlandı")
        with pytest.raises(yedek.YedekMesgul):
            yedek.yedek_al("elle", bekle=False)
        assert not isleyici.baslat(uygulama.state.yedek_zamanlayici)
    finally:
        birak.set()
        assert isleyici.durdur(3)
    son = yedek.listele()[0]
    assert (kopya / son["ad"]).read_bytes() == (yedek.dizin() / son["ad"]).read_bytes()
    assert not vt.KILIT.locked()


def test_yedek_indirme_yol_disina_cikamaz(kurulu, uygulama):
    from tahta_sunucu import ayar

    parola_belirle(kurulu)
    kurulu.post("/yedekler/al")
    ad, veri = yedek_dosyasi()
    yanit = kurulu.get(f"/yedekler/indir/{ad}")
    assert yanit.status_code == 200 and yanit.content == veri and "attachment" in yanit.headers["content-disposition"]
    (ayar.veri_dizini() / "tahta-kontrol-elle-2026-11-16.tkyedek").write_bytes(b"x")
    for kotu in ("..%5ctahta-kontrol.db", "..%2f..%2ftahta-kontrol.db", "C:%5cWindows%5cwin.ini",
                 "tahta-kontrol.db", "..%5ctahta-kontrol-elle-2026-11-16.tkyedek"):  # fmt: skip
        assert kurulu.get(f"/yedekler/indir/{kotu}").status_code in (404, 307, 308), kotu
    assert "Yedek indirildi" in kurulu.get("/kayit").text
    kullanici_ekle(kurulu, "idareci")
    gir(kurulu, "idareci")
    assert kurulu.get(f"/yedekler/indir/{ad}").status_code == 303


# ---- geri yükleme ----------------------------------------------------------------------
def test_geri_yukleme_yalniz_yerelden_ve_yoneticiyle(kurulu, uygulama):
    parola_belirle(kurulu)
    kurulu.post("/yedekler/al")
    ad, veri = yedek_dosyasi()
    uzak = TestClient(uygulama, client=("10.0.0.30", 40000), follow_redirects=False)
    uzak.cookies.update(kurulu.cookies)
    yanit = uzak.post("/yedekler/geri-yukle", files={"dosya": (ad, veri)}, data={"parola": YEDEK_PAROLASI})
    assert "yalnız sunucunun kurulu olduğu bilgisayardan" in ileti(yanit)
    kullanici_ekle(kurulu, "idareci")
    gir(kurulu, "idareci")
    yanit = kurulu.post("/yedekler/geri-yukle", files={"dosya": (ad, veri)}, data={"parola": YEDEK_PAROLASI})
    assert "yönetici yetkisi" in ileti(yanit)
    gir(kurulu, "yonetici")
    yanit = kurulu.post("/yedekler/geri-yukle", files={"dosya": (ad, veri)}, data={"parola": YEDEK_PAROLASI})
    assert yanit.headers["location"] == "/yedekler/geri-yukle/onay"
    onay = kurulu.get("/yedekler/geri-yukle/onay")
    assert onay.status_code == 200 and "Örnek Anadolu Lisesi" in onay.text
    # 6A: program kendini yeniden başlatmaz; düğme bunu vaat etmez.
    assert "Geri yüklemeyi onayla" in onay.text and "yeniden başlat<" not in onay.text
    assert "kapatıp yeniden açın" in ileti(kurulu.post("/yedekler/geri-yukle/uygula", data={"eylem": "uygula"}))


def test_hizmet_kipinde_geri_yukleme_sureci_yeniden_baslatir(kurulu, monkeypatch):
    from tahta_sunucu import ayar, hizmet, yedek

    planlanan = []
    monkeypatch.setattr(hizmet, "yeniden_baslat_planla", lambda gecikme=2.0: planlanan.append(gecikme))
    monkeypatch.setattr(ayar, "HIZMET", True)
    parola_belirle(kurulu)
    kurulu.post("/yedekler/al")
    ad, veri = yedek_dosyasi()
    kurulu.post("/yedekler/geri-yukle", files={"dosya": (ad, veri)}, data={"parola": YEDEK_PAROLASI})
    assert "Geri yükle ve yeniden başlat" in kurulu.get("/yedekler/geri-yukle/onay").text
    yanit = kurulu.post("/yedekler/geri-yukle/uygula", data={"eylem": "uygula"})
    assert "hizmeti birkaç saniye içinde yeniden başlıyor" in ileti(yanit)
    assert planlanan == [2.0] and yedek.bekleyen_oku()["onaylandi"] is True


def test_kurulumda_yedekten_geri_yukleme_oturumsuz_yerelde_calisir(kurulu, tmp_path, monkeypatch):
    from tahta_sunucu import ayar, guvenlik, web, yedek

    parola_belirle(kurulu)
    kurulu.post("/yedekler/al")
    ad, veri = yedek_dosyasi()
    yeni_dizin = tmp_path / "yeni-bilgisayar"
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(yeni_dizin))
    _, _, yeni_iz = guvenlik.sertifika_hazirla(ayar.veri_dizini())
    yeni = TestClient(web.uygulama_olustur(yeni_iz), client=("127.0.0.1", 50001), follow_redirects=False)
    assert 'href="/yedekler/geri-yukle"' in yeni.get("/kurulum").text
    assert yeni.get("/yedekler/geri-yukle").status_code == 200
    uzak = TestClient(yeni.app, client=("10.0.0.30", 40000), follow_redirects=False)
    assert "yalnız sunucunun" in ileti(uzak.post("/yedekler/geri-yukle", files={"dosya": (ad, veri)}, data={"parola": YEDEK_PAROLASI}))
    yanit = yeni.post("/yedekler/geri-yukle", files={"dosya": (ad, veri)}, data={"parola": YEDEK_PAROLASI})
    assert yanit.headers["location"] == "/yedekler/geri-yukle/onay"
    assert "data-sertifika-farkli" in yeni.get("/yedekler/geri-yukle/onay").text  # yeni bilgisayarın sertifikası başka
    yeni.post("/yedekler/geri-yukle/uygula", data={"eylem": "uygula"})
    assert yedek.bekleyen_oku()["onaylandi"] is True


def test_bekleyen_geri_yukleme_acilista_uygulanir_eskiler_tasinir(kurulu):
    from tahta_sunucu import ayar, guvenlik, vt, yedek

    parola_belirle(kurulu)
    kurulu.post("/yedekler/al")
    _, veri = yedek_dosyasi()
    eski_iz = yedek.parmak_izi_hesapla((ayar.veri_dizini() / "sunucu-sertifika.pem").read_bytes())
    kullanici_ekle(kurulu, "sonradan")  # yedekte yok
    yedek.bekleyeni_hazirla(veri, YEDEK_PAROLASI)
    assert yedek.bekleyeni_uygula() is None  # onaysız: dokunulmaz
    yedek.bekleyeni_onayla()
    assert "Yedekten geri yüklendi" in yedek.bekleyeni_uygula()
    assert [k["ad"] for k in sorgu("SELECT ad FROM kullanici")] == ["yonetici"]
    assert sorgu("SELECT COUNT(*) AS n FROM oturum")[0]["n"] == 0
    assert any(k["islem"] == "Yedekten geri yüklendi" for k in sorgu("SELECT islem FROM kayit"))
    oncesi = list((ayar.veri_dizini() / "geri-yukleme-oncesi").iterdir())
    assert len(oncesi) == 1 and (oncesi[0] / "tahta-kontrol.db").exists() and (oncesi[0] / "sunucu-sertifika.pem").exists()
    assert guvenlik.sertifika_hazirla(ayar.veri_dizini())[2] == eski_iz
    assert yedek.bekleyen_oku() is None
    vt.hazirla()


def test_geri_yukleme_hatasinda_eski_dosyalar_geri_konur(kurulu, monkeypatch):
    from tahta_sunucu import ayar, yedek

    parola_belirle(kurulu)
    kurulu.post("/yedekler/al")
    _, veri = yedek_dosyasi()
    kullanici_ekle(kurulu, "sonradan")
    yedek.bekleyeni_hazirla(veri, YEDEK_PAROLASI)
    yedek.bekleyeni_onayla()
    once = (ayar.veri_dizini() / "sunucu-anahtar.pem").read_bytes()

    def bozuk_kopya(kaynak, hedef):
        raise OSError("disk dolu (deneme)")

    monkeypatch.setattr(yedek.shutil, "copyfile", bozuk_kopya)
    assert yedek.bekleyeni_uygula() is None
    assert "sonradan" in [k["ad"] for k in sorgu("SELECT ad FROM kullanici")]
    assert (ayar.veri_dizini() / "sunucu-anahtar.pem").read_bytes() == once
    bekleyen = yedek.bekleyen_oku()
    assert bekleyen["onaylandi"] is False and "disk dolu" in bekleyen["hata"]


def test_geri_yukleme_basarisiz_deneme_hiz_siniri(kurulu):
    parola_belirle(kurulu)
    kurulu.post("/yedekler/al")
    ad, veri = yedek_dosyasi()
    for _ in range(5):
        kurulu.post("/yedekler/geri-yukle", files={"dosya": (ad, veri)}, data={"parola": "yanlis-parola-123"})
    yanit = kurulu.post("/yedekler/geri-yukle", files={"dosya": (ad, veri)}, data={"parola": YEDEK_PAROLASI})
    assert "Çok fazla başarısız" in ileti(yanit)


def test_goc_vt_kilidi_altinda(tmp_path, monkeypatch):
    from tahta_sunucu import vt

    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    vt.hazirla()
    with vt.islem() as b:
        assert b.execute("PRAGMA user_version").fetchone()[0] == len(vt.GOCLER)
        sutunlar = {s["name"] for s in b.execute("PRAGMA table_info(tahta)")}
    assert {"envanter_json", "envanter_ozet", "envanter_zamani", "donanim_kimligi", "demirbas_no", "envanter_notu"} <= sutunlar
    assert not vt.KILIT.locked()


# ---- adres listesi ---------------------------------------------------------------------
def test_sunucu_adresleri_dogrulanir(kurulu):
    from tahta_sunucu import adresler

    assert adresler.dogrula("https://10.0.0.5:8788/\n\nhttps://tahta.okul.local:8788\nhttps://10.0.0.5:8788") == [
        "https://10.0.0.5:8788", "https://tahta.okul.local:8788"]  # fmt: skip
    for kotu in ("http://10.0.0.5:8788", "https://localhost:8788", "https://127.0.0.1:8788", "https://10.0.0.5:8788/yol",
                 "https://10.0.0.5:99999", "https://:8788", "https://10.0.0.5:8788?x=1",
                 # kur.sh root yetkisiyle çalışır: kabuk metakarakteri taşıyan ad asla geçmez
                 "https://a$(id)b:8788", "https://tahta`id`.okul.local:8788", 'https://a";id;".okul:8788',
                 "https://a;id:8788", "https://-tahta.okul.local:8788", "https://tahta_okul:8788"):  # fmt: skip
        with pytest.raises(ValueError):
            adresler.dogrula(kotu)
    with pytest.raises(ValueError, match="En çok 5"):
        adresler.dogrula("\n".join(f"https://10.0.0.{i}:8788" for i in range(1, 7)))
    yanit = kurulu.post("/ayarlar", data={"bolum": "adresler", "sunucu_adresleri": "http://10.0.0.5:8788"})
    assert yanit.status_code == 400 and "https://" in ileti(yanit) and "http://10.0.0.5:8788" in yanit.text
    yanit = kurulu.post("/ayarlar", data={"bolum": "adresler", "sunucu_adresleri": "https://10.0.0.5:8788\r\nhttps://tahta.okul.local:8788"})
    assert "kaydedildi" in ileti(yanit)
    assert json.loads(sorgu("SELECT deger FROM ayar WHERE anahtar = 'sunucu_adresleri'")[0]["deger"]) == [
        "https://10.0.0.5:8788", "https://tahta.okul.local:8788"]  # fmt: skip
    kurulu.post("/ayarlar", data={"bolum": "genel", "okul_adi": "Başka"})  # genel bölüm listeye dokunmaz
    assert "https://tahta.okul.local:8788" in kurulu.get("/ayarlar/sunucu").text


def test_eski_sunucu_adresi_anahtari_listeye_donusur(kurulu, tahta):
    from tahta_sunucu import vt

    with vt.islem() as b:
        vt.ayar_yaz(b, "sunucu_adresi", "https://10.0.0.9:8788")
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    assert bekle(tahta, basliklar, yeni_durum())["ayar"]["sunucu_adresleri"] == ["https://10.0.0.9:8788"]
    assert "https://10.0.0.9:8788" in kurulu.get("/kur").text
    kurulu.post("/ayarlar", data={"bolum": "adresler", "sunucu_adresleri": "https://10.0.0.5:8788"})
    with vt.islem() as b:
        assert vt.ayar_al(b, "sunucu_adresi") == ""
    kurulu.post("/ayarlar", data={"bolum": "adresler", "sunucu_adresleri": ""})
    assert "sunucu_adresleri" not in bekle(tahta, basliklar, yeni_durum())["ayar"]


def test_kabuk_metakarakterli_adres_betige_girmez(kurulu, tahta):
    from tahta_sunucu import adresler, paket, vt

    assert adresler.dogrula("https://[fd00::5]:8788") == ["https://[fd00::5]:8788"]
    with vt.islem() as b:  # elle bozulmuş ya da eski sürümden kalma kayıtlar okunurken atılır
        vt.ayar_yaz(b, "sunucu_adresi", "https://a$(id)b:8788")
        assert adresler.al(b) == []
        vt.ayar_yaz(b, "sunucu_adresleri", ["https://10.0.0.5:8788", "https://a$(id)b:8788"])
        assert adresler.al(b) == ["https://10.0.0.5:8788"]
    betik = kurulu.get("/kur").text
    assert "$(id)" not in betik and 'SUNUCULAR="https://10.0.0.5:8788"' in betik
    with pytest.raises(ValueError):
        paket.kurulum_betigi("https://a$(id)b:8788", "ab" * 32)
    assert "$(id)" not in paket.kurulum_betigi("https://10.0.0.5:8788", "ab" * 32, ["https://x`id`:1"]).decode()
    # Ağdan (https) gelen istekte kötü Host başlığı betiğe yazılmaz; kayıtlı liste kullanılır.
    assert 'SUNUCU="https://10.0.0.7:8788"' in tahta.get("https://10.0.0.7:8788/kur").text  # geçerli Host kullanılır
    yanit = tahta.get("https://10.0.0.7:8788/kur", headers={"host": "a$(id)b:8788"})
    assert "$(id)" not in yanit.text and 'SUNUCU="https://10.0.0.5:8788"' in yanit.text


def test_kur_betigi_adres_listesini_yazar(kurulu):
    kurulu.post("/ayarlar", data={"bolum": "adresler", "sunucu_adresleri": "https://10.0.0.5:8788\nhttps://tahta.okul.local:8788"})
    betik = kurulu.get("/kur").text
    assert 'SUNUCU="https://10.0.0.5:8788"' in betik
    assert 'SUNUCULAR="https://10.0.0.5:8788 https://tahta.okul.local:8788"' in betik
    assert '"sunucular"' in betik and all(ord(c) < 128 for c in betik)


def test_pano_adres_listede_yoksa_uyarir(kurulu, monkeypatch):
    from tahta_sunucu import guvenlik

    monkeypatch.setattr(guvenlik, "yerel_ipler", lambda: ["10.0.0.9"])
    assert "tahtalara bildirilen listede yok" not in kurulu.get("/").text  # liste boş
    kurulu.post("/ayarlar", data={"bolum": "adresler", "sunucu_adresleri": "https://10.0.0.5:8788"})
    assert "Bu bilgisayarın adresi (10.0.0.9) tahtalara bildirilen listede yok" in kurulu.get("/").text
    kurulu.post("/ayarlar", data={"bolum": "adresler", "sunucu_adresleri": "https://10.0.0.5:8788\nhttps://tahta.okul.local:8788"})
    assert "listede yok" not in kurulu.get("/").text  # DNS adı var


def test_ayarlar_adres_listesini_alan_tahta_sayisi(kurulu, tahta):
    from tahta_sunucu import adresler

    kurulu.post("/ayarlar", data={"bolum": "adresler", "sunucu_adresleri": "https://10.0.0.5:8788"})
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    assert "0/1 tahta güncel adres listesini aldı" in kurulu.get("/ayarlar/sunucu").text
    bekle(tahta, basliklar, yeni_durum(adres_listesi_ozet=adresler.ozet(["https://10.0.0.5:8788"]),
                                       sunucu_adresi="https://10.0.0.5:8788"))  # fmt: skip
    assert "1/1 tahta güncel adres listesini aldı" in kurulu.get("/ayarlar/sunucu").text
    sayfa = kurulu.get(f"/tahta/{kimlik(basliklar)}?sekme=bakim").text
    assert "https://10.0.0.5:8788" in sayfa and "güncel" in sayfa


# ---- envanter --------------------------------------------------------------------------
def test_envanter_yalniz_istenince_gonderilir_ve_saklanir(kurulu, tahta):
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    assert bekle(tahta, basliklar, yeni_durum(envanter_ozet="a1b2c3d4e5f60718"))["envanter_iste"] is True
    yanit = tahta.post("/ajan/bekle", headers=basliklar, json={
        "surum": "0.7.0", "bekle": 0, "durum": yeni_durum(envanter_ozet="a1b2c3d4e5f60718"), "envanter": ENV})  # fmt: skip
    assert yanit.json()["envanter_iste"] is False
    satir = sorgu("SELECT * FROM tahta WHERE id = ?", kimlik(basliklar))[0]
    assert satir["envanter_ozet"] == "a1b2c3d4e5f60718" and satir["donanim_kimligi"] == "ORN75X000123"
    assert bekle(tahta, basliklar, yeni_durum(envanter_ozet="ffffffffffffffff"))["envanter_iste"] is True
    eski = bekle(tahta, basliklar, {"kilitli": False})  # yeteneksiz (eski) ajana alan gitmez
    assert "envanter_iste" not in eski
    sayfa = kurulu.get(f"/tahta/{kimlik(basliklar)}?sekme=bakim").text
    assert "ORN75X000123" in sayfa and "7,7 GB" in sayfa
    assert "ET-75 Etkileşimli Tahta" in kurulu.get("/envanter").text


def test_envanter_komutu_ve_sonucu(kurulu, tahta):
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum={"kilitli": False})
    yanit = kurulu.post("/islem", data={"tur": "envanter", "tahta": kimlik(basliklar)})
    assert "ajanı envanter göndermiyor" in ileti(yanit)
    bekle(tahta, basliklar, yeni_durum())
    assert "Envanteri yenile: 1 tahtaya" in ileti(kurulu.post("/islem", data={"tur": "envanter", "tahta": kimlik(basliklar)}))
    komut = bekle(tahta, basliklar, yeni_durum())["komutlar"][0]
    assert komut["tur"] == "envanter" and komut["veri"] == {}
    bekle(tahta, basliklar, yeni_durum(), sonuclar=[{"komut_id": komut["id"], "basarili": True, "cikti": json.dumps(ENV)}])
    assert sorgu("SELECT sonuc FROM komut WHERE id = ?", komut["id"])[0]["sonuc"] == "Envanter alındı."
    assert sorgu("SELECT donanim_kimligi FROM tahta")[0]["donanim_kimligi"] == "ORN75X000123"


def test_yer_tutucu_seri_numarasi_bos_sayilir():
    from tahta_sunucu import envanter

    for yer in ("To be filled by O.E.M.", "Default string", "System Serial Number", "None", "0", "000 .0", " ", ""):
        assert envanter.seri_temizle(yer) == "", yer
    assert envanter.donanim_kimligi({"urun_seri": "Default string", "anakart_seri": "MB0000456"}) == "MB0000456"


def test_donanim_kimligi_degisince_islem_kaydi_dusulur(kurulu, tahta):
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    govde = {"surum": "0.7.0", "bekle": 0, "durum": yeni_durum(envanter_ozet="1111111111111111"), "envanter": ENV}
    tahta.post("/ajan/bekle", headers=basliklar, json=govde)
    govde = {**govde, "durum": yeni_durum(envanter_ozet="2222222222222222"), "envanter": {**ENV, "urun_seri": "BASKA999"}}
    tahta.post("/ajan/bekle", headers=basliklar, json=govde)
    assert any(k["islem"] == "Tahtanın donanım kimliği değişti" for k in sorgu("SELECT islem FROM kayit"))
    sayfa = kurulu.get(f"/tahta/{kimlik(basliklar)}?sekme=bakim").text
    assert "donanım kimliği (seri no) değişti" in sayfa
    assert kurulu.get("/api/durum").json()["tahtalar"][0]["donanim_degisti"] is True
    kurulu.post(f"/tahta/{kimlik(basliklar)}/donanim-goruldu")
    assert kurulu.get("/api/durum").json()["tahtalar"][0]["donanim_degisti"] is False


def test_envanter_csv_bom_ayrac_ve_formul_kacisi(kurulu, tahta):
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    tahta.post("/ajan/bekle", headers=basliklar, json={"surum": "0.7.0", "bekle": 0, "durum": yeni_durum(), "envanter": ENV})
    kurulu.post(f"/tahta/{kimlik(basliklar)}/envanter", data={"demirbas_no": "=TS-2026-0001", "envanter_notu": "Örnek not"})
    yanit = kurulu.get("/envanter.csv")
    assert yanit.content.startswith(b"\xef\xbb\xbf") and "tahta-envanteri-2026-11-16.csv" in yanit.headers["content-disposition"]
    metin = yanit.content.decode("utf-8-sig")
    satirlar = metin.split("\r\n")
    assert satirlar[0].startswith("Tahta;Derslik;Demirbaş no;Üretici;Model;Seri no;")
    assert "'=TS-2026-0001" in satirlar[1] and "ORN75X000123" in satirlar[1]
    assert "Envanter dışa aktarıldı" in kurulu.get("/kayit").text


def test_onay_bekleyen_tahtanin_envanteri_kabul_edilmez(kurulu, tahta):
    kurulu.post("/ekle", data={"eylem": "ac"})
    kod = kurulu.get("/ekle").text.split('class="buyuk-kod">')[1].split("<")[0]
    veri = tahta.post("/ajan/kaydol", json={"kod": kod, "makine_adi": "etap", "surum": "0.7.0"}).json()
    basliklar = {"X-Tahta-Id": str(veri["tahta_id"]), "X-Tahta-Anahtar": veri["anahtar"]}
    yanit = tahta.post("/ajan/bekle", headers=basliklar, json={
        "surum": "0.7.0", "bekle": 0, "durum": yeni_durum(), "envanter": ENV,
        "arizalar": [{"yerel_id": "9c1e4b7a2f0d8e63", "kategori": "ses", "aciklama": "x"}]})  # fmt: skip
    assert yanit.json()["durum"] == "bekliyor" and "ariza_alindi" not in yanit.json()
    assert sorgu("SELECT envanter_json FROM tahta")[0]["envanter_json"] is None
    assert sorgu("SELECT COUNT(*) AS n FROM ariza")[0]["n"] == 0


def test_demirbas_bilgisi_yalniz_yonetici(kurulu, tahta):
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    kullanici_ekle(kurulu, "idareci")
    gir(kurulu, "idareci")
    assert "yönetici yetkisi" in ileti(kurulu.post(f"/tahta/{kimlik(basliklar)}/envanter", data={"demirbas_no": "X"}))
    assert kurulu.get("/envanter").status_code == 200
    gir(kurulu, "yonetici")
    assert "T.C." in ileti(kurulu.post(f"/tahta/{kimlik(basliklar)}/envanter", data={"envanter_notu": SAHTE_TC}))
    assert "en çok 40" in ileti(kurulu.post(f"/tahta/{kimlik(basliklar)}/envanter", data={"demirbas_no": "x" * 41}))


# ---- arıza -----------------------------------------------------------------------------
def test_tahtadan_ariza_iletilir_ve_tekrar_kayit_olusmaz(kurulu, tahta):
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    oge = {"yerel_id": "9c1e4b7a2f0d8e63", "kategori": "dokunmatik", "aciklama": "Sol alt köşe\x07 algılamıyor.",
           "oturum_sinifi": "ogretmen", "tahta_zamani": 1794810000}  # fmt: skip
    for _ in range(2):
        yanit = tahta.post("/ajan/bekle", headers=basliklar,
                           json={"surum": "0.7.0", "bekle": 0, "komut_al": False, "durum": yeni_durum(), "arizalar": [oge]})  # fmt: skip
        assert yanit.json()["ariza_alindi"] == ["9c1e4b7a2f0d8e63"]
    kayitlar = sorgu("SELECT * FROM ariza")
    assert len(kayitlar) == 1
    assert (kayitlar[0]["kaynak"], kayitlar[0]["bildiren"], kayitlar[0]["oturum_sinifi"]) == ("tahta", "tahta", "ogretmen")
    assert kayitlar[0]["aciklama"] == "Sol alt köşe algılamıyor."
    liste = kurulu.get("/arizalar").text
    assert "Tahtadan · öğretmen hesabı" in liste and "Dokunmatik" in liste
    assert kurulu.get("/api/durum").json()["tahtalar"][0]["ariza_sayisi"] == 1
    assert 'class="sayi-rozet">1<' in kurulu.get("/").text


def test_tahtadan_bilinmeyen_kategori_ve_tc_numarasi(kurulu, tahta):
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    arizalar = [
        {"yerel_id": "aaaaaaaaaaaaaaaa", "kategori": "yeni_tur", "aciklama": "Bir şey"},
        {"yerel_id": "bbbbbbbbbbbbbbbb", "kategori": "acilis", "aciklama": ""},
        {"yerel_id": "cccccccccccccccc", "kategori": "ses", "aciklama": f"No {SAHTE_TC}"},
        {"yerel_id": "bozuk", "kategori": "ses"},
    ]
    yanit = tahta.post("/ajan/bekle", headers=basliklar,
                       json={"surum": "0.7.0", "bekle": 0, "durum": yeni_durum(), "arizalar": arizalar})  # fmt: skip
    assert yanit.json()["ariza_alindi"] == ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb", "cccccccccccccccc"]
    kayit = {s["yerel_id"]: s for s in sorgu("SELECT * FROM ariza")}
    assert kayit["aaaaaaaaaaaaaaaa"]["kategori"] == "diger" and kayit["aaaaaaaaaaaaaaaa"]["aciklama"].startswith("[kategori: yeni_tur]")
    assert kayit["bbbbbbbbbbbbbbbb"]["kategori"] == "diger"
    assert SAHTE_TC not in json.dumps(sorgu("SELECT * FROM ariza")) + json.dumps(sorgu("SELECT * FROM kayit"))


def test_ariza_durum_gecisleri_kurala_uyar(kurulu, tahta):
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    yanit = kurulu.post("/arizalar", data={"tahta_id": kimlik(basliklar), "kategori": "ses", "aciklama": "Cızırtı"})
    ariza_id = int(yanit.headers["location"].split("/ariza/")[1].split("?")[0])
    assert kurulu.post(f"/ariza/{ariza_id}", data={"durum": "iptal"}).status_code == 303
    yanit = kurulu.post(f"/ariza/{ariza_id}", data={"durum": "acik"})
    assert yanit.status_code == 400 and "yapılamaz" in ileti(yanit)
    yanit = kurulu.post("/arizalar", data={"tahta_id": kimlik(basliklar), "kategori": "ses"})
    ikinci = int(yanit.headers["location"].split("/ariza/")[1].split("?")[0])
    for durum, kod in (("cozuldu", 303), ("inceleniyor", 400), ("acik", 303), ("inceleniyor", 303), ("cozuldu", 303)):
        assert kurulu.post(f"/ariza/{ikinci}", data={"durum": durum}).status_code == kod, durum
    assert "Değişiklik yok" in ileti(kurulu.post(f"/ariza/{ikinci}", data={}))


def test_ariza_hareketleri_ve_islem_kaydi_tutulur(kurulu, tahta):
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    yanit = kurulu.post("/arizalar", data={"tahta_id": kimlik(basliklar), "kategori": "kalem", "aciklama": "Kalem yazmıyor"})
    ariza_id = int(yanit.headers["location"].split("/ariza/")[1].split("?")[0])
    kurulu.post(f"/ariza/{ariza_id}", data={"durum": "inceleniyor", "not_metni": "Firma arandı"})
    kurulu.post(f"/ariza/{ariza_id}", data={"durum": "cozuldu", "cozum_notu": "Kalem değiştirildi"})
    hareketler = sorgu("SELECT * FROM ariza_hareket WHERE ariza_id = ? ORDER BY id", ariza_id)
    assert [(h["eski_durum"], h["yeni_durum"]) for h in hareketler] == [("", "acik"), ("acik", "inceleniyor"), ("inceleniyor", "cozuldu")]
    assert hareketler[1]["not_metni"] == "Firma arandı"
    assert sorgu("SELECT cozum_notu FROM ariza")[0]["cozum_notu"] == "Kalem değiştirildi"
    islemler = [k["islem"] for k in sorgu("SELECT islem FROM kayit")]
    assert islemler.count("Arıza kaydı güncellendi") == 2 and "Arıza kaydı açıldı" in islemler
    sayfa = kurulu.get(f"/ariza/{ariza_id}").text
    assert "Firma arandı" in sayfa and "İnceleniyor → Çözüldü" in sayfa
    assert "T.C." in ileti(kurulu.post(f"/ariza/{ariza_id}", data={"not_metni": SAHTE_TC}))
    assert "Arıza notu reddedildi" in [k["islem"] for k in sorgu("SELECT islem FROM kayit")]


def test_reddedilen_ariza_notu_ve_secim_korunur(kurulu, tahta):
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    yanit = kurulu.post("/arizalar", data={"tahta_id": kimlik(basliklar), "kategori": "kalem", "aciklama": ""})
    ariza_id = int(yanit.headers["location"].split("/ariza/")[1].split("?")[0])
    yanit = kurulu.post(f"/ariza/{ariza_id}", data={"durum": "inceleniyor", "not_metni": "Firma arandı " + SAHTE_TC,
                                                     "cozum_notu": "Kalem değişecek"})  # fmt: skip
    assert yanit.status_code == 400
    assert f"Firma arandı {SAHTE_TC}</textarea>" in yanit.text and "Kalem değişecek</textarea>" in yanit.text
    assert 'value="inceleniyor" checked' in yanit.text and 'value="" checked' not in yanit.text
    assert sorgu("SELECT durum FROM ariza WHERE id = ?", ariza_id)[0]["durum"] == "acik"
    sayfa = kurulu.get(f"/ariza/{ariza_id}").text  # normal açılış: boş not, "Değiştirme" seçili
    assert 'value="" checked' in sayfa and SAHTE_TC not in sayfa


def test_idareci_ariza_acip_kapatabilir(kurulu, tahta):
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    kullanici_ekle(kurulu, "idareci")
    gir(kurulu, "idareci")
    yanit = kurulu.post("/arizalar", data={"tahta_id": kimlik(basliklar), "kategori": "acilis", "aciklama": ""})
    ariza_id = int(yanit.headers["location"].split("/ariza/")[1].split("?")[0])
    assert kurulu.post(f"/ariza/{ariza_id}", data={"durum": "cozuldu"}).status_code == 303
    assert sorgu("SELECT durum, bildiren FROM ariza")[0] == {"durum": "cozuldu", "bildiren": "idareci"}
    assert "Panelden · Idareci" in kurulu.get("/arizalar?durum=hepsi").text
    assert kurulu.get("/yedekler").status_code == 303  # yedekler yalnız yönetici
    assert "T.C." in ileti(kurulu.post("/arizalar", data={"tahta_id": kimlik(basliklar), "kategori": "ses", "aciklama": SAHTE_TC}))


def test_ariza_aciklamasi_kacisli_basilir(kurulu, tahta):
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    yanit = kurulu.post("/arizalar", data={"tahta_id": kimlik(basliklar), "kategori": "diger", "aciklama": "<script>alert(1)</script>"})
    ariza_id = int(yanit.headers["location"].split("/ariza/")[1].split("?")[0])
    for yol in (f"/ariza/{ariza_id}", "/arizalar", f"/tahta/{kimlik(basliklar)}"):
        metin = kurulu.get(yol).text
        assert "<script>alert(1)" not in metin, yol


def test_kaldirilan_tahtanin_arizasi_kalir(kurulu, tahta):
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    kurulu.post("/arizalar", data={"tahta_id": kimlik(basliklar), "kategori": "ses"})
    kurulu.post(f"/tahta/{kimlik(basliklar)}/kaydet", data={"ad": "x", "eylem": "sil"})
    assert "(kaldırıldı)" in kurulu.get("/arizalar").text


# ---- menü ve uyum ----------------------------------------------------------------------
def test_menu_altyapi_ogeleri(kurulu):
    # 0.18.0: "/" Bugün'dür. Yedekler yan menüde (her sayfa); Envanter ve Arızalar Tahtalar bölümünün sekme şeridinde.
    assert 'href="/yedekler"' in kurulu.get("/").text
    sayfa = kurulu.get("/tahtalar").text
    for yol in ('href="/envanter"', 'href="/arizalar"', 'href="/yedekler"'):
        assert yol in sayfa
    kullanici_ekle(kurulu, "idareci")
    gir(kurulu, "idareci")
    sayfa = kurulu.get("/tahtalar").text
    assert 'href="/yedekler"' not in sayfa and 'href="/arizalar"' in sayfa
    sayfa = kurulu.get("/").text
    assert 'href="/yedekler"' not in sayfa
    assert "Yedek alınmıyor; yöneticiye bildirin." in sayfa


def test_eski_ajan_yeni_sunucuyla_calisir(kurulu, tahta):
    basliklar = tahta_ekle(kurulu, tahta, "Tahta 9-A", durum={"kilitli": False}, surum="0.1.2")
    kurulu.post("/ayarlar", data={"bolum": "adresler", "sunucu_adresleri": "https://10.0.0.5:8788"})
    yanit = bekle(tahta, basliklar, {"kilitli": False}, surum="0.1.2")
    assert yanit["durum"] == "onayli" and "envanter_iste" not in yanit and "ariza_alindi" not in yanit
    assert yanit["ayar"]["sunucu_adresleri"] == ["https://10.0.0.5:8788"]
    assert "Envanter ve arıza bildirimi için ajanı güncelleyin" in kurulu.get(f"/tahta/{kimlik(basliklar)}?sekme=bakim").text
    assert "Ajan güncellenmeli" in kurulu.get("/envanter").text


def test_yeni_sablonlar_hatasiz_cizilir(kurulu, tahta):
    from tahta_sunucu import ayar_bolumleri

    tahta_ekle(kurulu, tahta, "Tahta 9-A", durum=yeni_durum())
    parola_belirle(kurulu)
    kurulu.post("/yedekler/al")
    for yol in ("/yedekler", "/envanter", "/arizalar", "/arizalar?durum=hepsi", "/ayarlar",
                *(f"/ayarlar/{b}" for b in ayar_bolumleri.ANAHTARLAR), "/acil?sekme=sablonlar"):
        yanit = kurulu.get(yol)
        assert yanit.status_code == 200, yol


def test_yedekte_sqlite_goruntusu_tutarli(kurulu):
    from tahta_sunucu import yedek

    parola_belirle(kurulu)
    kurulu.post("/yedekler/al")
    _, veri = yedek_dosyasi()
    _, dosyalar = yedek.coz(veri, YEDEK_PAROLASI)
    yol = yedek.bekleyen_dizini() / "kontrol.db"
    yol.write_bytes(dosyalar["tahta-kontrol.db"])
    b = sqlite3.connect(yol)
    try:
        assert b.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert b.execute("SELECT ad FROM kullanici").fetchall() == [("yonetici",)]
    finally:
        b.close()
