"""Okul kimliği: renk ayarı, logo yükleme/sunma, ajana inen tema, güvenlik başlıkları, şablon kuralları."""

from __future__ import annotations

import hashlib
import os
import re
import struct
import zlib
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

SABLONLAR = Path(__file__).resolve().parent.parent / "tahta_sunucu" / "sablonlar"


# ---- yardımcılar (test_akis.py değişmesin diye burada yerel) ----------------------
@pytest.fixture()
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    from tahta_sunucu import web

    uygulama = web.uygulama_olustur("ab" * 32)
    panel = TestClient(uygulama, client=("127.0.0.1", 50000), follow_redirects=False)
    tahta = TestClient(uygulama, client=("10.0.0.20", 40000))
    return panel, tahta


def kur_ve_gir(panel):
    panel.post(
        "/kurulum",
        data={"okul_adi": "Deneme Anadolu Lisesi", "gorunen_ad": "Deneme Yönetici", "ad": "yonetici",
              "parola": "gizli-parola", "parola2": "gizli-parola"},
    )  # fmt: skip
    yanit = panel.post("/giris", data={"ad": "yonetici", "parola": "gizli-parola"})
    assert yanit.status_code == 303 and "tk_oturum" in panel.cookies


def ileti(yanit) -> str:
    sorgu = urlsplit(yanit.headers["location"]).query
    return parse_qs(sorgu).get("m", [""])[0]


def onayli_tahta(panel, tahta, durum=None) -> dict:
    panel.post("/ekle", data={"eylem": "ac"})
    kod = panel.get("/ekle").text.split('class="buyuk-kod">')[1].split("<")[0]
    veri = tahta.post("/ajan/kaydol", json={"kod": kod, "makine_adi": "etap-01", "surum": "0.1.0"}).json()
    basliklar = {"X-Tahta-Id": str(veri["tahta_id"]), "X-Tahta-Anahtar": veri["anahtar"]}
    panel.post(f"/tahta/{veri['tahta_id']}/kaydet", data={"ad": "11-A", "derslik": "2. kat", "eylem": "onayla"})
    tahta.post("/ajan/bekle", headers=basliklar, json={"surum": "0.1.0", "durum": durum or {"kilitli": False}, "bekle": 0})
    return basliklar


def png(en: int, boy: int, ek: int = 0) -> bytes:
    def parca(tur: bytes, veri: bytes) -> bytes:
        return struct.pack(">I", len(veri)) + tur + veri + struct.pack(">I", zlib.crc32(tur + veri) & 0xFFFFFFFF)

    ham = b"".join(b"\x00" + b"\x30\x60\x90" * en for _ in range(boy)) if en * boy <= 1_000_000 else b"\x00"
    govde = parca(b"IHDR", struct.pack(">IIBBBBB", en, boy, 8, 2, 0, 0, 0))
    if ek:
        govde += parca(b"teXt", os.urandom(ek))
    govde += parca(b"IDAT", zlib.compress(ham)) + parca(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + govde


def jpeg(en: int, boy: int) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 17, 8, boy, en, 3) + b"\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    return b"\xff\xd8" + app0 + b"\xff\xff" + sof0 + b"\xff\xd9"


def yukle(panel, veri: bytes, ad: str = "logo.png", tur: str = "image/png", **kw):
    return panel.post("/ayarlar/logo", files={"logo": (ad, veri, tur)}, **kw)


# ---- renkler ---------------------------------------------------------------------
def test_gorunum_kaydedilir_ve_tema_css_sunulur(ortam):
    from tahta_sunucu import tema

    panel, _ = ortam
    kur_ve_gir(panel)
    yanit = panel.post("/ayarlar/gorunum", data={"eylem": "kaydet", "ana_renk": "#7A1F2B", "vurgu_kullan": "1", "vurgu_renk": "#d4a017"})
    assert yanit.status_code == 303 and ileti(yanit) == "Renkler kaydedildi."
    assert yanit.headers["location"].startswith("/ayarlar/okul?yer=kimlik&m=") and yanit.headers["location"].endswith("#ileti")
    sayfa = panel.get("/").text
    v = tema.surum("#7a1f2b", "#d4a017")
    assert f'/marka/tema.css?v={v}"' in sayfa
    css = panel.get(f"/marka/tema.css?v={v}")
    assert css.status_code == 200 and css.headers["content-type"].startswith("text/css")
    assert "--ana-a:#7a1f2b" in css.text and "--vurgu-a:#d4a017" in css.text
    assert "immutable" in css.headers["cache-control"]
    assert panel.get("/marka/tema.css?v=eski").headers["cache-control"] == "no-cache"
    assert "Görünüm değiştirildi" in panel.get("/kayit").text
    # Ayarlar sayfası seçili renkleri ve raporu gösterir.
    ayarlar = panel.get("/ayarlar/okul").text
    assert 'value="#7a1f2b"' in ayarlar and "Kontrast raporu" in ayarlar


def test_gorunum_varsayilana_doner(ortam):
    from tahta_sunucu import tema

    panel, _ = ortam
    kur_ve_gir(panel)
    panel.post("/ayarlar/gorunum", data={"eylem": "kaydet", "ana_renk": "#0e7490"})
    assert "--ana-a:#0e7490" in panel.get("/marka/tema.css").text
    yanit = panel.post("/ayarlar/gorunum", data={"eylem": "varsayilan", "ana_renk": "#0e7490"})
    assert yanit.status_code == 303
    css = panel.get("/marka/tema.css").text
    assert f"--ana-a:{tema.VARSAYILAN_ANA}" in css and f"--vurgu-a:{tema.VARSAYILAN_VURGU}" in css


def test_gecersiz_renk_kaydedilmez(ortam):
    panel, _ = ortam
    kur_ve_gir(panel)
    once = panel.get("/marka/tema.css").text
    for veri in (
        {"eylem": "kaydet", "ana_renk": "#123456;}body{"},
        {"eylem": "kaydet", "ana_renk": "red"},
        {"eylem": "kaydet", "ana_renk": "#123456", "vurgu_kullan": "1", "vurgu_renk": "url(x)"},
    ):
        yanit = panel.post("/ayarlar/gorunum", data=veri)
        assert ileti(yanit) == "Renk #rrggbb biçiminde olmalı."
    assert panel.get("/marka/tema.css").text == once


# ---- logo ------------------------------------------------------------------------
def test_logo_png_yuklenir_ve_sunulur(ortam):
    panel, _ = ortam
    kur_ve_gir(panel)
    veri = png(128, 128)
    yanit = yukle(panel, veri)
    assert yanit.status_code == 303 and ileti(yanit) == "Logo yüklendi.", ileti(yanit)
    sha = hashlib.sha256(veri).hexdigest()
    logo = panel.get(f"/marka/logo?v={sha[:12]}")
    assert logo.status_code == 200 and logo.content == veri
    assert logo.headers["content-type"] == "image/png"
    assert logo.headers["content-security-policy"] == "default-src 'none'; sandbox"
    assert logo.headers["x-content-type-options"] == "nosniff"
    assert "immutable" in logo.headers["cache-control"] and logo.headers["etag"] == f'"{sha}"'
    assert panel.get("/marka/logo?v=baska").headers["cache-control"] == "no-cache"
    panel.cookies.clear()
    giris = panel.get("/giris").text
    assert f'<img src="/marka/logo?v={sha[:12]}"' in giris
    # Oturumsuz da sunulur (giriş sayfasında görünür).
    assert panel.get("/marka/logo").status_code == 200


def test_logo_jpeg_yuklenir(ortam):
    panel, _ = ortam
    kur_ve_gir(panel)
    veri = jpeg(300, 120)
    yanit = yukle(panel, veri, "okul.jpg", "image/jpeg")
    assert ileti(yanit) == "Logo yüklendi.", ileti(yanit)
    logo = panel.get("/marka/logo")
    assert logo.content == veri and logo.headers["content-type"] == "image/jpeg"
    assert "JPEG · 300×120 px" in panel.get("/ayarlar/okul").text


def test_logo_svg_gif_ve_sahte_uzanti_reddedilir(ortam):
    panel, _ = ortam
    kur_ve_gir(panel)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><script>alert(1)</script></svg>'
    gif = b"GIF89a" + struct.pack("<HH", 100, 100) + b"\x00" * 20
    html = b"<!doctype html><html><body>merhaba</body></html>"
    for veri in (svg, gif, html):
        yanit = yukle(panel, veri, "logo.png", "image/png")
        assert ileti(yanit) == "Logo PNG ya da JPEG olmalı."
    assert panel.get("/marka/logo").status_code == 404


def test_logo_boyut_ve_olcu_siniri(ortam):
    panel, _ = ortam
    kur_ve_gir(panel)
    assert ileti(yukle(panel, png(128, 128, ek=300 * 1024))) == "Logo dosyası en çok 256 KB olabilir."
    assert ileti(yukle(panel, png(32, 32))) == "Logonun kenarları 64–2048 piksel olmalı."
    assert ileti(yukle(panel, png(2048, 100))) == "Logo çok uzun ya da çok dar (en-boy oranı 1:4 ile 4:1 arasında olmalı)."
    assert ileti(yukle(panel, png(4096, 4096))) == "Logonun kenarları 64–2048 piksel olmalı."
    assert ileti(yukle(panel, b"\xff\xd8\xff\xe0\x00\x10JFIF")) == "Logo dosyası okunamadı."
    assert ileti(yukle(panel, png(128, 128)[:20])) == "Logo dosyası okunamadı."
    assert ileti(panel.post("/ayarlar/logo", data={"x": "1"})) == "Logo dosyası seçilmedi."
    assert panel.get("/marka/logo").status_code == 404


def test_logo_yetki_ve_kaynak(ortam):
    panel, _ = ortam
    kur_ve_gir(panel)
    panel.post("/kullanicilar", data={"eylem": "ekle", "ad": "idareci1", "gorunen_ad": "İdareci", "parola": "uzun-parola", "rol": "idareci"})
    yanit = yukle(panel, png(128, 128), headers={"Origin": "https://kotu.example"})
    assert yanit.status_code == 403
    assert panel.post("/ayarlar/gorunum", data={"eylem": "kaydet", "ana_renk": "#000000"}, headers={"Origin": "https://kotu.example"}).status_code == 403

    panel.post("/cikis")
    panel.cookies.clear()
    assert yukle(panel, png(128, 128)).headers["location"].startswith("/giris")
    assert panel.post("/ayarlar/gorunum", data={"ana_renk": "#000000"}).headers["location"].startswith("/giris")

    panel.post("/giris", data={"ad": "idareci1", "parola": "uzun-parola"})
    yanit = yukle(panel, png(128, 128))
    assert yanit.headers["location"].startswith("/?m=") and "yönetici" in ileti(yanit)
    assert panel.post("/ayarlar/gorunum", data={"eylem": "kaydet", "ana_renk": "#000000"}).headers["location"].startswith("/?m=")
    assert panel.post("/ayarlar/logo/sil").headers["location"].startswith("/?m=")
    assert panel.get("/marka/logo").status_code == 404
    assert "--ana-a:#000000" not in panel.get("/marka/tema.css").text


def test_logo_kaldirilir(ortam):
    panel, _ = ortam
    kur_ve_gir(panel)
    yukle(panel, png(128, 128))
    assert panel.get("/marka/logo").status_code == 200
    yanit = panel.post("/ayarlar/logo/sil")
    assert ileti(yanit) == "Logo kaldırıldı."
    assert panel.get("/marka/logo").status_code == 404
    sayfa = panel.get("/").text
    assert "/marka/logo" not in sayfa
    assert 'class="logo-rozet monogram" aria-hidden="true">DA<' in sayfa


# ---- ajan -------------------------------------------------------------------------
def test_ajan_tema_ve_logo_ozeti_iner(ortam):
    panel, tahta = ortam
    kur_ve_gir(panel)
    basliklar = onayli_tahta(panel, tahta)
    ayar = tahta.post("/ajan/bekle", headers=basliklar, json={"bekle": 0}).json()["ayar"]
    from tahta_sunucu import tema

    assert set(ayar["tema"]) == set(tema.TAHTA_ANAHTARLARI) and len(ayar["tema"]) == 11
    assert all(re.fullmatch(r"#[0-9a-f]{6}", d) for d in ayar["tema"].values())
    assert ayar["logo_sha256"] is None
    assert ayar["tahta"] == {"ad": "11-A", "derslik": "2. kat"}

    veri = png(128, 128)
    yukle(panel, veri)
    panel.post("/ayarlar/gorunum", data={"eylem": "kaydet", "ana_renk": "#7a1f2b"})
    ayar = tahta.post("/ajan/bekle", headers=basliklar, json={"bekle": 0}).json()["ayar"]
    assert ayar["logo_sha256"] == hashlib.sha256(veri).hexdigest()
    assert ayar["tema"] == tema.uret("#7a1f2b", None)["tahta"]
    assert "logo" not in ayar  # baytlar uzun bekleme yanıtına girmez

    # Onaysız tahtaya yalnız sunucu saati iner.
    panel.post("/ekle", data={"eylem": "ac"})
    kod = panel.get("/ekle").text.split('class="buyuk-kod">')[1].split("<")[0]
    yeni = tahta.post("/ajan/kaydol", json={"kod": kod}).json()
    onaysiz = {"X-Tahta-Id": str(yeni["tahta_id"]), "X-Tahta-Anahtar": yeni["anahtar"]}
    assert list(tahta.post("/ajan/bekle", headers=onaysiz, json={"bekle": 0}).json()["ayar"]) == ["sunucu_saat"]


def test_ajan_logo_ucu_kimlik_ister(ortam):
    panel, tahta = ortam
    kur_ve_gir(panel)
    basliklar = onayli_tahta(panel, tahta)
    assert tahta.get("/ajan/logo").status_code == 401
    assert tahta.get("/ajan/logo", headers={**basliklar, "X-Tahta-Anahtar": "yanlis"}).status_code == 401
    assert tahta.get("/ajan/logo", headers=basliklar).status_code == 404
    veri = jpeg(256, 256)
    yukle(panel, veri, "a.jpg", "image/jpeg")
    yanit = tahta.get("/ajan/logo", headers=basliklar)
    assert yanit.status_code == 200 and yanit.content == veri
    assert yanit.headers["x-sha256"] == hashlib.sha256(veri).hexdigest()
    assert yanit.headers["cache-control"] == "no-store"


# ---- başlıklar ve şablonlar -----------------------------------------------------
def test_guvenlik_basliklari(ortam):
    panel, _ = ortam
    kur_ve_gir(panel)
    sayfa = panel.get("/")
    csp = sayfa.headers["content-security-policy"]
    assert "default-src 'self'" in csp and "style-src 'self'" in csp and "script-src 'self'" in csp
    assert "unsafe-inline" not in csp and "frame-ancestors 'none'" in csp
    assert sayfa.headers["referrer-policy"] == "same-origin"
    assert sayfa.headers["x-frame-options"] == "DENY"
    assert sayfa.headers["cache-control"] == "no-store"
    assert "camera=()" in sayfa.headers["permissions-policy"]
    assert sayfa.headers["cross-origin-opener-policy"] == "same-origin"
    assert "strict-transport-security" not in sayfa.headers
    yukle(panel, png(128, 128))
    assert panel.get("/marka/logo").headers["content-security-policy"] == "default-src 'none'; sandbox"


def test_sablonlarda_satir_ici_betik_ve_stil_yok():
    for yol in SABLONLAR.glob("*.html"):
        metin = yol.read_text(encoding="utf-8")
        assert "style=" not in metin, yol.name
        assert "<style" not in metin, yol.name
        assert not re.search(r"\son[a-z]+=", metin), yol.name
        for etiket in re.findall(r"<script\b[^>]*>", metin):
            assert "src=" in etiket or 'type="application/json"' in etiket, (yol.name, etiket)


def test_pano_kancalari_yerinde(ortam):
    panel, tahta = ortam
    kur_ve_gir(panel)
    onayli_tahta(panel, tahta, {"kilitli": False, "oturum": {"sinif": "ogretmen"}, "ekranlar": [{"arayuz": "gtk3"}]})
    sayfa = panel.get("/").text
    for kanca in (
        'id="islem"',
        'id="secim-sayisi"',
        'id="ilk-veri"',
        'id="pano-veri"',
        'data-alan="rozetler"',
        'name="tahta"',
        'name="tur" value="kilitle"',
        'formaction="/duyurular/yeni"',  # 0.17.0: satır içi duyuru formu kalktı; seçimle duyuru formuna gidilir
        'class="tahta-satir"',
        'id="secim-cubugu"',
        'id="haplar"',
        'id="canli"',
        'data-onay="kapat"',
        'data-onay="yeniden_baslat"',
        'id="onay-diyalog"',
        'id="onay-evet"',
        'id="canli-bolge"',
    ):
        assert kanca in sayfa, kanca
    assert 'name="tur" value="duyuru"' not in sayfa and "article" not in sayfa
    assert re.search(r'<input type="checkbox" id="hepsini-sec">', sayfa)
    # Tehlikeli tetikler kendi başına form göndermez.
    for tetik in re.findall(r"<button[^>]*data-onay=[^>]*>", sayfa):
        assert 'type="button"' in tetik and " name=" not in tetik
    assert "<script>" not in sayfa
    durum = panel.get("/api/durum").json()["tahtalar"][0]
    assert durum["oturum_acik"] is True
    assert 'data-onay="sil"' in panel.get(f"/tahta/{durum['id']}?sekme=bilgiler").text


# ---- inceleme düzeltmeleri ----------------------------------------------------------
def test_bozuk_logo_dosyasi_sayfada_istenmez(ortam):
    """Dosya özeti ayardakiyle tutmazsa sayfalar /marka/logo istemez (kırık resim yerine monogram)."""
    from tahta_sunucu import marka

    panel, _ = ortam
    kur_ve_gir(panel)
    yukle(panel, png(128, 128))
    assert "/marka/logo?v=" in panel.get("/").text
    with marka.logo_yolu().open("ab") as f:
        f.write(b"\x00")
    assert panel.get("/marka/logo").status_code == 404
    sayfa = panel.get("/").text
    assert "/marka/logo" not in sayfa and "logo-rozet monogram" in sayfa
    assert 'href="/statik/isaret.svg"' in sayfa


def test_hata_iletisi_hata_gorunumunde(ortam):
    panel, _ = ortam
    kur_ve_gir(panel)
    yanit = panel.post("/ayarlar/gorunum", data={"eylem": "kaydet", "ana_renk": "red"})
    assert "t=hata" in yanit.headers["location"] and ileti(yanit) == "Renk #rrggbb biçiminde olmalı."
    sayfa = panel.get(yanit.headers["location"].split("#", 1)[0]).text
    assert re.search(r'<div class="bant hata" role="alert"[^>]*>', sayfa)
    basari = panel.post("/ayarlar/gorunum", data={"eylem": "kaydet", "ana_renk": "#0e7490"})
    assert "t=hata" not in basari.headers["location"]
    sayfa = panel.get(basari.headers["location"].split("#", 1)[0]).text
    assert re.search(r'<div class="bant" role="status"[^>]*>Renkler kaydedildi\.', sayfa)
    # Giriş sayfasındaki hata da hata görünümündedir.
    panel.post("/cikis")
    panel.cookies.clear()
    yanit = panel.post("/giris", data={"ad": "yonetici", "parola": "yanlis-parola"})
    assert 'class="bant hata" role="alert"' in panel.get(yanit.headers["location"]).text


def test_kimlik_iletisi_kimlik_bolumunde(ortam):
    """Okul kimliği iletisi yönlendirmenin kaydığı #kimlik bölümünde, odaklanacak biçimde çizilir."""
    panel, _ = ortam
    kur_ve_gir(panel)
    yanit = yukle(panel, png(3000, 3000))
    konum = yanit.headers["location"]
    assert konum.startswith("/ayarlar/okul?yer=logo&") and konum.endswith("#ileti")
    sayfa = panel.get(konum.split("#", 1)[0]).text
    kimlik = sayfa.index('id="logo-karti"')
    bant = sayfa.index('class="bant hata" role="alert" id="ileti" tabindex="-1" data-odakla')
    assert bant > kimlik and sayfa.count("Logonun kenarları 64–2048 piksel olmalı.") == 1
    # Genel ayarların iletisi yine sayfa başında çizilir.
    sayfa = panel.get(panel.post("/ayarlar", data={"okul_adi": "Deneme"}).headers["location"]).text
    assert sayfa.index("Ayarlar kaydedildi.") < sayfa.index('id="ayar-kapsam"')  # 0.16.0: genel → giriş sayfası
    assert "data-odakla" not in sayfa
