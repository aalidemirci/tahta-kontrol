"""GitHub'dan yeni sürüm denetimi: yanıt doğrulama, giden veri, zamanlama, panel. Gerçek ağa çıkılmaz."""

from __future__ import annotations

import io
import json
import re
import ssl
import threading
import urllib.error

import pytest
from fastapi.testclient import TestClient
from yardimci import gir, ileti, kullanici_ekle, kur_ve_gir, sorgu

from tahta_sunucu import __version__, guncelleme, vt, web


def yanit(etiket="v9.9.9", **ek) -> bytes:
    veri = {"tag_name": etiket, "draft": False, "prerelease": False,
            "html_url": "https://kotu.example/indir", "body": "<script>alert(1)</script> sürüm notu"}  # fmt: skip
    veri.update(ek)
    return json.dumps(veri).encode()


class Getirici:
    """Sahte getirici: sıradaki yanıtı döndürür ya da hatayı atar; çağrıları sayar."""

    def __init__(self, *yanitlar):
        self.yanitlar = list(yanitlar)
        self.cagri = 0

    def __call__(self) -> bytes:
        self.cagri += 1
        y = self.yanitlar[0] if len(self.yanitlar) == 1 else self.yanitlar.pop(0)
        if isinstance(y, BaseException):
            raise y
        return y


def panel_kur(tmp_path, monkeypatch, getirici):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    uygulama = web.uygulama_olustur("ab" * 32, guncelleme_getirici=getirici)
    panel = TestClient(uygulama, client=("127.0.0.1", 50000), follow_redirects=False)
    kur_ve_gir(panel)
    return uygulama, panel


def kayitlar() -> list[str]:
    return [s["islem"] for s in sorgu("SELECT islem FROM kayit ORDER BY id")]


# ---- sürüm ve yanıt -----------------------------------------------------------------------------------
def test_surum_karsilastirma_sayisaldir():
    assert guncelleme.yeni_mi("0.13.10", "0.13.9")
    assert guncelleme.yeni_mi("v0.14", "0.13.9")
    assert guncelleme.yeni_mi("1.0.0.1", "1.0.0")
    assert not guncelleme.yeni_mi("0.13", "0.13.0")
    assert not guncelleme.yeni_mi("0.13.0", "0.13.1")
    assert not guncelleme.yeni_mi("bozuk", "0.13.1")


@pytest.mark.parametrize(
    "etiket",
    ["v9<script>", "9", "v1.2.3.4.5", "1.2.3-rc1", "v1.2.3 ", " v1.2.3", "v1.2.3\n", "V1.2.3", "v١.٢.٣", "", None, 12,
     "1." + "9" * 60, ["v1.2.3"]],
)  # fmt: skip
def test_bozuk_etiket_yok_sayilir(etiket):
    assert guncelleme.surum_coz(etiket) is None
    assert guncelleme.yanit_coz(yanit(etiket)) == ""


def test_on_surum_ve_taslak_yok_sayilir():
    assert guncelleme.yanit_coz(yanit("v9.9.9")) == "9.9.9"
    assert guncelleme.yanit_coz(yanit("9.9")) == "9.9"
    assert guncelleme.yanit_coz(yanit(prerelease=True)) == ""
    assert guncelleme.yanit_coz(yanit(draft=True)) == ""
    assert guncelleme.yanit_coz(json.dumps({"tag_name": "v9.9.9"}).encode()) == ""  # alanlar eksikse de yok sayılır


@pytest.mark.parametrize("ham", [b"", b"{bozuk", b"[1, 2]", b'"v9.9.9"', b"\xff\xfe", b"[" * 100000])
def test_bozuk_json_ulasilamadi_sayilir(ham):
    with pytest.raises(guncelleme.GuncellemeHatasi):
        guncelleme.yanit_coz(ham)
    assert guncelleme.denetle(lambda: ham) == {"sonuc": "ulasilamadi", "surum": ""}


def test_denetle_hicbir_hatayi_disari_vermez():
    for hata in (guncelleme.GuncellemeHatasi("x"), TimeoutError(), OSError("ağ yok"), RuntimeError("beklenmedik")):
        assert guncelleme.denetle(Getirici(hata)) == {"sonuc": "ulasilamadi", "surum": ""}
    assert guncelleme.denetle(Getirici(yanit("v1.2.3"))) == {"sonuc": "tamam", "surum": "1.2.3"}


def test_baglanti_sabit_kaliptan_kurulur():
    assert guncelleme.surum_adresi("0.14.0") == "https://github.com/aalidemirci/tahta-kontrol/releases/tag/v0.14.0"
    assert guncelleme.surum_adresi("v0.14.0").endswith("/tag/v0.14.0")
    with pytest.raises(ValueError):
        guncelleme.surum_adresi("0.14.0/../../x")


# ---- ağ kapısı (sahte açıcıyla) -----------------------------------------------------------------------
class SahteYanit(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def test_istekte_giden_veri_yok():
    gorulen = []

    def ac(istek, zaman_asimi):
        gorulen.append((istek, zaman_asimi))
        return SahteYanit(yanit())

    assert guncelleme.github_getir.__name__ == "yasak"  # conftest: modül adı testlerde sahtedir
    assert gercek_getir(ac) == yanit()
    istek, zaman_asimi = gorulen[0]
    assert istek.full_url == "https://api.github.com/repos/aalidemirci/tahta-kontrol/releases/latest"
    assert "?" not in istek.full_url and istek.get_method() == "GET" and istek.data is None
    assert dict(istek.header_items()) == {"User-agent": "tahta-kontrol", "Accept": "application/vnd.github+json"}
    assert 0 < zaman_asimi <= 5
    assert __version__ not in istek.full_url + repr(istek.header_items())


def gercek_getir(ac):
    """conftest `github_getir` adını değiştirdiği için asıl işleve modül sözlüğündeki özgün koddan ulaşılır."""
    return _OZGUN_GETIR(ac)


_OZGUN_GETIR = guncelleme.github_getir  # içe aktarma anında (fikstürden önce) özgün işlev


def test_dev_yanit_reddedilir():
    with pytest.raises(guncelleme.GuncellemeHatasi, match="büyük"):
        gercek_getir(lambda i, z: SahteYanit(b" " * (guncelleme.YANIT_SINIRI + 1)))
    assert len(gercek_getir(lambda i, z: SahteYanit(b" " * guncelleme.YANIT_SINIRI))) == guncelleme.YANIT_SINIRI
    assert guncelleme.YANIT_SINIRI <= 256 * 1024


@pytest.mark.parametrize(
    "hata",
    [
        TimeoutError("zaman aşımı"),
        ssl.SSLCertVerificationError("sertifika doğrulanamadı"),
        urllib.error.URLError("ad çözülemedi"),
        urllib.error.HTTPError("https://api.github.com/x", 302, "Found", {}, None),  # yönlendirme izlenmez
        urllib.error.HTTPError("https://api.github.com/x", 403, "rate limit", {}, None),
        ConnectionResetError(),
    ],
)
def test_ag_hatalari_tek_hataya_iner(hata):
    def ac(istek, zaman_asimi):
        raise hata

    with pytest.raises(guncelleme.GuncellemeHatasi):
        gercek_getir(ac)


def test_200_disi_yanit_reddedilir():
    y = SahteYanit(yanit())
    y.status = 204
    with pytest.raises(guncelleme.GuncellemeHatasi):
        gercek_getir(lambda i, z: y)


def test_yonlendirme_izlenmez():
    assert guncelleme._YonlendirmeYok().redirect_request(None, None, 302, "Found", {}, "https://kotu.example/") is None


# ---- testler ağa çıkmaz ---------------------------------------------------------------------------------
def test_test_takimi_gercek_aga_cikmaz(uygulama, panel, ag_kapali):
    """Varsayılan uygulamada (getirici verilmeden) zamanlayıcı ve "Şimdi denetle" yalnız sahte kapıya ulaşır."""
    assert guncelleme.github_getir.__name__ == "yasak" and guncelleme._ac.__name__ == "yasak"
    kur_ve_gir(panel)
    isler = dict(uygulama.state.zamanlayicilar)
    assert isler["guncelleme"]() is True
    assert uygulama.state.guncelleme.bekle()
    assert ag_kapali == ["ag"]
    with vt.islem() as b:
        assert guncelleme.durum_al(b)["sonuc"] == "ulasilamadi"
    # Özgün işlev de sahte açıcıya düşer: urllib'e hiç ulaşılmaz.
    with pytest.raises(guncelleme.GuncellemeHatasi, match="ağ kapalı"):
        _OZGUN_GETIR()
    assert ag_kapali == ["ag", "ag"]


# ---- zamanlama --------------------------------------------------------------------------------------------
def test_gunde_en_cok_bir_kez(tmp_path, monkeypatch, saat):
    getirici = Getirici(yanit("v9.9.9"))
    uygulama, _ = panel_kur(tmp_path, monkeypatch, getirici)
    d = uygulama.state.guncelleme
    assert d.zamanla() is True and d.bekle()
    assert getirici.cagri == 1
    for _ in range(5):
        saat.ilerlet(20)
        assert d.zamanla() is False
    saat.ilerlet(86400 - 200)
    assert d.zamanla() is False
    saat.ilerlet(200)
    assert d.zamanla() is True and d.bekle()
    assert getirici.cagri == 2
    assert "Güncelleme denetimi yapıldı" not in kayitlar()  # kendiliğinden denetim işlem kaydına yazılmaz


def test_basarisizlikta_firtina_yok_ve_sonraki_deneme_ertesi_gun(tmp_path, monkeypatch, saat):
    getirici = Getirici(TimeoutError("zaman aşımı"))
    uygulama, panel = panel_kur(tmp_path, monkeypatch, getirici)
    d = uygulama.state.guncelleme
    assert d.zamanla() is True and d.bekle()
    for _ in range(10):
        saat.ilerlet(20)
        assert d.zamanla() is False
    assert getirici.cagri == 1
    # Yeniden başlatma (yeni Denetleyici) da aynı gün yeniden denemez: son deneme veritabanındadır.
    assert guncelleme.Denetleyici(getirici).zamanla() is False
    assert "ulaşılamadı" not in panel.get("/").text  # panoda hata yok
    assert "GitHub'a ulaşılamadı." in panel.get("/ayarlar/guncelleme").text.replace("&#39;", "'")
    saat.ilerlet(86400)
    assert d.zamanla() is True and d.bekle()
    assert getirici.cagri == 2


def test_ag_cagrisi_zamanlayiciyi_ve_veritabanini_tutmaz(tmp_path, monkeypatch, saat):
    basladi, birak = threading.Event(), threading.Event()

    def yavas():
        basladi.set()
        assert birak.wait(5)
        return yanit("v9.9.9")

    uygulama, panel = panel_kur(tmp_path, monkeypatch, yavas)
    d = uygulama.state.guncelleme
    try:
        assert d.zamanla() is True  # hemen döner
        assert basladi.wait(2)
        assert d.zamanla() is False  # süren iş varken ikincisi başlamaz
        assert vt.KILIT.acquire(blocking=False)  # yedek/göç kilidi tutulmuyor
        vt.KILIT.release()
        with vt.islem() as b:  # ağ çağrısı sürerken veritabanı yazılabilir
            vt.ayar_yaz(b, "deneme", 1)
        assert panel.get("/").status_code == 200
    finally:
        birak.set()
    assert d.bekle()
    with vt.islem() as b:
        assert guncelleme.durum_al(b)["surum"] == "9.9.9"


def test_kapanis_beklemez_ve_sonuc_yazilmaz(tmp_path, monkeypatch, saat):
    basladi, birak = threading.Event(), threading.Event()

    def yavas():
        basladi.set()
        assert birak.wait(5)
        return yanit("v9.9.9")

    uygulama, _ = panel_kur(tmp_path, monkeypatch, yavas)
    d = uygulama.state.guncelleme
    assert d.zamanla() is True and basladi.wait(2)
    d.durdur()  # hemen döner
    assert d.zamanla() is False
    birak.set()
    assert d.bekle()
    with vt.islem() as b:
        assert guncelleme.durum_al(b) == {}


def test_sunucu_kapanisi_denetleyiciyi_durdurur():
    from types import SimpleNamespace

    from tahta_sunucu.sunucu import Sunucu
    from tahta_sunucu.yedek_is import YedekIsleyici

    d = guncelleme.Denetleyici(lambda: yanit())
    sunucu = Sunucu.__new__(Sunucu)
    sunucu._durdu = threading.Event()
    sunucu._yedek_isleyici = YedekIsleyici()
    sunucu.sunucular, sunucu.is_parcalari, sunucu._zamanlayici_parcasi = [], [], None
    sunucu.uygulama = SimpleNamespace(state=SimpleNamespace(guncelleme=d))
    sunucu.durdur()
    assert d._kapandi


# ---- ayar ve panel ----------------------------------------------------------------------------------------
def test_ayar_kapaliyken_hic_istek_cikmaz(tmp_path, monkeypatch, saat):
    getirici = Getirici(yanit("v9.9.9"))
    uygulama, panel = panel_kur(tmp_path, monkeypatch, getirici)
    y = panel.post("/ayarlar", data={"bolum": "guncelleme"})  # kutu işaretsiz → kapalı
    assert "kapalı" in ileti(y)
    assert uygulama.state.guncelleme.zamanla() is False
    y = panel.post("/ayarlar/guncelleme/denetle")
    assert "kapalı" in ileti(y) and "t=hata" in y.headers["location"]
    assert getirici.cagri == 0
    sayfa = panel.get("/ayarlar/guncelleme").text
    assert "Şimdi denetle" not in sayfa and "Denetim kapalı" in sayfa
    assert kayitlar().count("Güncelleme denetimi ayarı kaydedildi") == 1
    assert "Güncelleme denetimi yapıldı" not in kayitlar()
    # Yeniden açılınca çalışır.
    panel.post("/ayarlar", data={"bolum": "guncelleme", "gd_acik": "1"})
    assert uygulama.state.guncelleme.zamanla() is True and uygulama.state.guncelleme.bekle()
    assert getirici.cagri == 1


def test_varsayilan_acik(uygulama, panel):
    kur_ve_gir(panel)
    with vt.islem() as b:
        assert guncelleme.etkin(b) and guncelleme.gorunum(b)["sonuc"] == "Henüz denetlenmedi."
    sayfa = panel.get("/ayarlar/guncelleme").text
    assert "Şimdi denetle" in sayfa and 'name="gd_acik" value="1" checked' in sayfa


def test_simdi_denetle_yeni_surum(tmp_path, monkeypatch, saat):
    getirici = Getirici(yanit("v99.0.1"))
    _, panel = panel_kur(tmp_path, monkeypatch, getirici)
    y = panel.post("/ayarlar/guncelleme/denetle")
    assert y.status_code == 303 and ileti(y) == "Yeni sürüm 99.0.1 yayımlanmış."
    assert kayitlar()[-1] == "Güncelleme denetimi yapıldı"
    adres = "https://github.com/aalidemirci/tahta-kontrol/releases/tag/v99.0.1"
    for yol in ("/", "/ayarlar/guncelleme"):
        sayfa = panel.get(yol).text
        sinif = 'class="dugme" ' if yol == "/" else ""  # Bugün'de bekleyen iş satırının düğmesi
        assert f'<a {sinif}href="{adres}" rel="noopener noreferrer">Sürüm sayfası</a>' in sayfa, yol
        assert "kotu.example" not in sayfa and "alert(1)" not in sayfa and "sürüm notu" not in sayfa
        dis = set(re.findall(r'(?:href|src|action)="(https?://[^"]+)"', sayfa))
        assert dis == {adres}, yol
    assert "Son denetim: 16.11.2026 09:00" in panel.get("/ayarlar/guncelleme").text
    # Art arda basış yeni istek çıkarmaz ve işlem kaydını şişirmez.
    y = panel.post("/ayarlar/guncelleme/denetle")
    assert "Az önce denetlendi" in ileti(y) and getirici.cagri == 1
    assert kayitlar().count("Güncelleme denetimi yapıldı") == 1
    saat.ilerlet(61)
    panel.post("/ayarlar/guncelleme/denetle")
    assert getirici.cagri == 2


@pytest.mark.parametrize("etiket", [f"v{__version__}", "v0.0.1"])
def test_ayni_ve_eski_surum_guncel(tmp_path, monkeypatch, saat, etiket):
    _, panel = panel_kur(tmp_path, monkeypatch, Getirici(yanit(etiket)))
    assert ileti(panel.post("/ayarlar/guncelleme/denetle")) == "Kurulu sürüm güncel."
    assert "data-yeni-surum" not in panel.get("/").text


@pytest.mark.parametrize(
    "ham",
    [yanit(prerelease=True), yanit(draft=True), yanit("v9<script>"), yanit("v99.0.0-beta")],
)
def test_yok_sayilan_yanit_not_uretmez(tmp_path, monkeypatch, saat, ham):
    _, panel = panel_kur(tmp_path, monkeypatch, Getirici(ham))
    assert ileti(panel.post("/ayarlar/guncelleme/denetle")) == "Kurulu sürüm güncel."
    for yol in ("/", "/ayarlar/guncelleme"):
        sayfa = panel.get(yol).text
        assert "data-yeni-surum" not in sayfa and "Sürüm sayfası" not in sayfa
        assert "v9<script>" not in sayfa and "v9&lt;script&gt;" not in sayfa


def test_ulasilamayinca_bilinen_surum_korunur_ve_pano_sessiz(tmp_path, monkeypatch, saat):
    getirici = Getirici(yanit("v99.0.0"), OSError("ağ yok"))
    _, panel = panel_kur(tmp_path, monkeypatch, getirici)
    panel.post("/ayarlar/guncelleme/denetle")
    saat.ilerlet(120)
    y = panel.post("/ayarlar/guncelleme/denetle")
    assert ileti(y) == "GitHub'a ulaşılamadı." and "t=hata" in y.headers["location"]
    pano = panel.get("/").text
    assert 'data-yeni-surum="99.0.0"' in pano and "ulaşılamadı" not in pano


def test_not_yalniz_yoneticiye_ve_denetim_yalniz_yoneticiden(tmp_path, monkeypatch, saat):
    getirici = Getirici(yanit("v99.0.0"))
    _, panel = panel_kur(tmp_path, monkeypatch, getirici)
    panel.post("/ayarlar/guncelleme/denetle")
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    assert "data-yeni-surum" not in panel.get("/").text
    saat.ilerlet(120)
    y = panel.post("/ayarlar/guncelleme/denetle")
    assert y.status_code in (303, 403) and getirici.cagri == 1
    assert panel.post("/ayarlar", data={"bolum": "guncelleme"}).status_code in (303, 403)
    with vt.islem() as b:
        assert guncelleme.etkin(b)
    panel.cookies.clear()
    panel.post("/ayarlar/guncelleme/denetle")
    assert getirici.cagri == 1


def test_baska_kaynaktan_istek_reddedilir(tmp_path, monkeypatch, saat):
    getirici = Getirici(yanit("v99.0.0"))
    _, panel = panel_kur(tmp_path, monkeypatch, getirici)
    y = panel.post("/ayarlar/guncelleme/denetle", headers={"Origin": "https://kotu.example"})
    assert y.status_code == 403 and getirici.cagri == 0


def test_saklanan_durum_yeniden_dogrulanir(uygulama, panel):
    kur_ve_gir(panel)
    with vt.islem() as b:
        vt.ayar_yaz(b, guncelleme.DURUM_ANAHTARI, {"zaman": vt.simdi(), "sonuc": "tamam", "surum": '99"><script>'})
        assert guncelleme.gorunum(b)["yeni"] is None
    assert "data-yeni-surum" not in panel.get("/").text


def test_guncellenince_not_kalkar(uygulama, panel):
    kur_ve_gir(panel)
    with vt.islem() as b:
        vt.ayar_yaz(b, guncelleme.DURUM_ANAHTARI, {"zaman": vt.simdi(), "sonuc": "tamam", "surum": "0.13.0"})
        assert guncelleme.gorunum(b, "0.12.0")["yeni"]["surum"] == "0.13.0"
        assert guncelleme.gorunum(b, "0.13.0")["yeni"] is None
        assert guncelleme.gorunum(b, "0.13.1")["sonuc"] == "Kurulu sürüm güncel."


def test_modul_ajana_ve_tarayiciya_dokunmaz():
    """Denetim yalnız sunucudadır: ajan kodunda ve panel betiğinde GitHub adresi geçmez; yeni bağımlılık yok."""
    from pathlib import Path

    kok = Path(guncelleme.__file__).resolve().parent
    for dosya in [*(kok.parent / "tahta_ajan").glob("*.py"), kok / "statik" / "panel.js"]:
        assert "github" not in dosya.read_text(encoding="utf-8").lower(), dosya.name
    kaynak = Path(guncelleme.__file__).read_text(encoding="utf-8")
    assert not re.search(r"^\s*(import|from) (requests|httpx|certifi|aiohttp)\b", kaynak, re.M)
    assert "html_url" not in kaynak.split('"""', 2)[2]  # yanıttaki bağlantı kodda hiç okunmaz


# ---- toplam süre sınırı, kapanış, yarış ve bozuk durum (inceleme bulguları) -----------------------------
class DamlayanYanit(SahteYanit):
    """Gövdeyi bayt bayt, her baytı gecikmeyle verir (yavaş damlatan ağ aygıtı)."""

    def read(self, n=-1):
        import time

        time.sleep(0.2)
        return super().read(1)

    read1 = read


def test_damlayan_govde_toplam_sureyi_asamaz():
    import time

    basla = time.monotonic()
    sonuc = guncelleme.denetle(lambda: gercek_getir(lambda i, z: DamlayanYanit(yanit())), sure=0.6)
    assert sonuc == {"sonuc": "ulasilamadi", "surum": ""}
    assert time.monotonic() - basla < 2  # ~150 bayt × 0,2 sn = 30 sn sürecek yanıt beklenmez


def test_baslik_asamasi_da_toplam_sureye_tabidir():
    import time

    birak = threading.Event()

    def ac(istek, zaman_asimi):  # bağlantı/başlık aşamasında asılı kalan ağ (ad çözümlemesi dahil)
        birak.wait(10)
        return SahteYanit(yanit())

    basla = time.monotonic()
    try:
        assert guncelleme.denetle(lambda: gercek_getir(ac), sure=0.3)["sonuc"] == "ulasilamadi"
        assert time.monotonic() - basla < 2
    finally:
        birak.set()
    assert guncelleme.ZAMAN_ASIMI_SN <= 5


def test_elle_denetim_kapanisi_tutmaz_ve_sonuc_yazilmaz(tmp_path, monkeypatch, saat):
    import time

    basladi, birak = threading.Event(), threading.Event()

    def yavas():
        basladi.set()
        birak.wait(10)
        return yanit("v9.9.9")

    uygulama, _ = panel_kur(tmp_path, monkeypatch, yavas)
    d = uygulama.state.guncelleme
    sonuclar = []
    parca = threading.Thread(target=lambda: sonuclar.append(d.simdi_denetle()), daemon=True)
    try:
        parca.start()
        assert basladi.wait(2)
        basla = time.monotonic()
        d.durdur()
        parca.join(2)
        assert not parca.is_alive() and time.monotonic() - basla < 2
    finally:
        birak.set()
    assert sonuclar[0]["taze"] and sonuclar[0]["sonuc"] == "ulasilamadi"
    with vt.islem() as b:
        assert guncelleme.durum_al(b) == {}
    # Kapanıştan sonra ağ çağrısına hiç başlanmaz.
    basladi.clear()
    assert d.simdi_denetle()["taze"] and not basladi.is_set()


def test_suren_denetim_varken_simdi_denetle_ikinci_istek_cikarmaz(tmp_path, monkeypatch, saat):
    basladi, birak = threading.Event(), threading.Event()
    cagri = []

    def yavas():
        cagri.append(1)
        basladi.set()
        assert birak.wait(5)
        return yanit("v9.9.9")

    uygulama, _ = panel_kur(tmp_path, monkeypatch, yavas)
    d = uygulama.state.guncelleme
    sonuclar = []
    eller = [threading.Thread(target=lambda: sonuclar.append(d.simdi_denetle()), daemon=True) for _ in range(2)]
    try:
        assert d.zamanla() is True and basladi.wait(2)
        for p in eller:
            p.start()
    finally:
        birak.set()
    for p in eller:
        p.join(5)
    assert d.bekle()
    assert len(cagri) == 1  # kilitte bekleyen elle denetimler süren işin sonucunu kullanır
    assert [s["taze"] for s in sonuclar] == [True, True] and sonuclar[0]["surum"] == "9.9.9"


def test_eszamanli_zamanla_tek_is_baslatir(tmp_path, monkeypatch, saat):
    getirici = Getirici(yanit("v9.9.9"))
    uygulama, _ = panel_kur(tmp_path, monkeypatch, getirici)
    d = uygulama.state.guncelleme
    engel = threading.Barrier(8)
    donenler = []

    def cagir():
        engel.wait(5)
        donenler.append(d.zamanla())

    parcalar = [threading.Thread(target=cagir) for _ in range(8)]
    for p in parcalar:
        p.start()
    for p in parcalar:
        p.join(5)
    assert d.bekle()
    assert donenler.count(True) == 1 and getirici.cagri == 1


@pytest.mark.parametrize("zaman", ["abc", 10**18, -5, True, None, [1], 1e400, float("nan")])
def test_bozuk_saklanan_zaman_panoyu_dusurmez(uygulama, panel, zaman):
    kur_ve_gir(panel)
    with vt.islem() as b:
        b.execute(
            "INSERT OR REPLACE INTO ayar (anahtar, deger) VALUES (?, ?)",
            (guncelleme.DURUM_ANAHTARI, json.dumps({"zaman": zaman, "sonuc": "tamam", "surum": "99.0.0"})),
        )
    with vt.islem() as b:
        assert guncelleme.durum_al(b)["zaman"] == 0
        assert guncelleme.gorunum(b)["zaman"] == ""
    assert panel.get("/").status_code == 200
    assert panel.get("/ayarlar").status_code == 200
    assert uygulama.state.guncelleme.zamanla() is True and uygulama.state.guncelleme.bekle()  # yeniden denetlenir


def test_araligin_disindaki_zaman_metni_bos():
    assert guncelleme._zaman_metni(10**18) == "" and guncelleme._zaman_metni(0) == ""
