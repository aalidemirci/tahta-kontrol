"""Acil durum / tatbikat yayını: yetki, parola, durum tabanlı iletim, yedek yol, rapor, bant."""

from __future__ import annotations

import pytest
from yardimci import (
    PAROLA,
    SAHTE_TC,
    an,
    bekle,
    gir,
    ileti,
    kimlik,
    kullanici_ekle,
    kur_ve_gir,
    sorgu,
    tahta_ekle,
    yeni_ajan_durumu,
)


@pytest.fixture()
def okul(panel, tahta):
    kur_ve_gir(panel)
    yeni = tahta_ekle(panel, tahta, "Yeni ajanlı", durum=yeni_ajan_durumu())
    eski = tahta_ekle(panel, tahta, "Eski ajanlı", durum={"kilitli": True, "ekranlar": [{"arayuz": "gtk3"}]}, surum="0.2.0")
    return yeni, eski


def baslat(panel, **alanlar):
    form = {"tur": "acil", "sablon": "tahliye", "baslik": "TAHLİYE", "metin": "Sakin biçimde toplanma alanına gidiniz.",
            "sure_dk": "30", "onay": "1", "parola": PAROLA}  # fmt: skip
    form.update(alanlar)
    return panel.post("/acil/baslat", data={k: v for k, v in form.items() if v is not None})


def test_idareci_ayri_yetki_olmadan_baslatir_ve_bitirir_parola_ve_onay_ister(okul, panel):
    """16.11.2026 kararı K4: bütün idareciler (ve yöneticiler) başlatır; parola ve onay kutusu yine istenir."""
    kullanici_ekle(panel, "idareci1")
    from tahta_sunucu import vt

    with vt.islem() as b:  # eski sürümde yetkisi alınmış idareci: sütun artık okunmaz
        b.execute("UPDATE kullanici SET acil_yetki = 0 WHERE ad = 'idareci1'")
    gir(panel, "idareci1")
    sayfa = panel.get("/acil").text
    assert 'action="/acil/baslat"' in sayfa and "yetkiniz yok" not in sayfa
    assert ileti(baslat(panel, parola="yanlis")) == "Parola hatalı; yayın başlatılmadı."
    assert "Onay kutusunu" in ileti(baslat(panel, onay=None))
    assert sorgu("SELECT * FROM acil_yayin") == []
    yanit = baslat(panel)
    assert yanit.headers["location"].startswith("/acil/")
    acil_id = sorgu("SELECT id, baslatan FROM acil_yayin")[0]
    assert acil_id["baslatan"] == "idareci1"
    assert "bitirildi" in ileti(panel.post(f"/acil/{acil_id['id']}/bitir"))
    assert sorgu("SELECT bitiren FROM acil_yayin")[0]["bitiren"] == "idareci1"


def test_bilinmeyen_roldeki_kullanici_baslatamaz_ve_kayda_duser(okul, panel):
    kullanici_ekle(panel, "gozlemci1")
    from tahta_sunucu import vt

    with vt.islem() as b:  # elle bozulmuş/ileride eklenecek bir rol: yetki rolden gelir
        b.execute("UPDATE kullanici SET rol = 'gozlemci', acil_yetki = 1 WHERE ad = 'gozlemci1'")
    gir(panel, "gozlemci1")
    sayfa = panel.get("/acil").text
    assert "Acil yayın yetkiniz yok." in sayfa and 'action="/acil/baslat"' not in sayfa
    assert "yetkiniz yok" in ileti(baslat(panel)) and sorgu("SELECT * FROM acil_yayin") == []
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Acil yayın reddedildi'")[0]["ayrinti"] == "Acil yetkisi yok"


def test_acil_parola_hatasi_reddedilir(okul, panel):
    yanit = baslat(panel, parola="yanlis")
    assert ileti(yanit) == "Parola hatalı; yayın başlatılmadı." and sorgu("SELECT * FROM acil_yayin") == []
    assert sorgu("SELECT * FROM kayit WHERE islem = 'Acil yayın: parola hatalı'")


def test_acil_hiz_siniri(okul, panel):
    for _ in range(10):
        baslat(panel, parola="yanlis")
    assert "Çok fazla deneme" in ileti(baslat(panel))
    assert sorgu("SELECT * FROM acil_yayin") == []


def test_acil_tur_secilmeden_ya_da_onaysiz_baslatilamaz(okul, panel):
    assert "türünü seçin" in ileti(baslat(panel, tur=None))
    assert "türünü seçin" in ileti(baslat(panel, tur="yangin"))
    assert "Onay kutusunu" in ileti(baslat(panel, onay=None))
    assert "boş olamaz" in ileti(baslat(panel, metin=" "))
    assert "5-120" in ileti(baslat(panel, sure_dk="121"))
    assert "T.C." in ileti(baslat(panel, metin=f"Öğrenci {SAHTE_TC} aranıyor"))
    assert sorgu("SELECT * FROM acil_yayin") == []


def test_acil_ayar_ile_tum_onayli_tahtalara_iner_teslim_kaydedilir(okul, panel, tahta, saat):
    yeni, _ = okul
    yanit = baslat(panel)
    acil_id = sorgu("SELECT id FROM acil_yayin")[0]["id"]
    assert yanit.headers["location"].startswith(f"/acil/{acil_id}")
    saat.ilerlet(3)
    cevap = bekle(tahta, yeni, yeni_ajan_durumu())
    assert cevap["ayar"]["acil"] == {"id": acil_id, "tur": "acil", "baslik": "TAHLİYE",
                                     "metin": "Sakin biçimde toplanma alanına gidiniz.", "kalan_sn": 1797}  # fmt: skip
    assert cevap["komutlar"] == []  # yeni ajana komut değil, durum gider
    assert sorgu("SELECT * FROM acil_teslim") == []
    bekle(tahta, yeni, yeni_ajan_durumu(acil_id=acil_id))
    bekle(tahta, yeni, yeni_ajan_durumu(acil_id=acil_id))  # ikinci bildirim yeni satır yazmaz
    teslim = sorgu("SELECT * FROM acil_teslim")
    assert len(teslim) == 1 and (teslim[0]["yol"], teslim[0]["ekran_var"]) == ("acil", 1)
    durum = panel.get("/api/durum").json()
    assert durum["acil"]["id"] == acil_id and durum["acil"]["teslim"] == 1 and durum["acil"]["hedef"] == 2
    gorundu = {t["ad"]: t["acil_gorundu"] for t in durum["tahtalar"]}
    assert gorundu == {"Yeni ajanlı": True, "Eski ajanlı": False}
    assert sorgu("SELECT islem FROM kayit WHERE islem LIKE 'ACİL%'")[0]["islem"] == "ACİL DURUM YAYINI başlatıldı"
    assert sorgu("SELECT sablon, hedef_sayisi FROM acil_yayin")[0] == {"sablon": "tahliye", "hedef_sayisi": 2}


def test_acil_bitince_ayarda_null_doner(okul, panel, tahta):
    yeni, _ = okul
    assert bekle(tahta, yeni, yeni_ajan_durumu())["ayar"]["acil"] is None  # anahtar her zaman var
    baslat(panel)
    acil_id = sorgu("SELECT id FROM acil_yayin")[0]["id"]
    yanit = panel.post(f"/acil/{acil_id}/bitir", data={"donus": "/duyurular"})
    assert yanit.headers["location"].startswith("/duyurular?") and "bitirildi" in ileti(yanit)
    assert bekle(tahta, yeni, yeni_ajan_durumu())["ayar"]["acil"] is None
    satir = sorgu("SELECT * FROM acil_yayin")[0]
    assert (satir["bitis_nedeni"], satir["bitiren"]) == ("panel", "yonetici") and satir["bitis"]
    assert "zaten bitmiş" in ileti(panel.post(f"/acil/{acil_id}/bitir"))
    # Dış adrese dönüş yapılmaz.
    assert panel.post(f"/acil/{acil_id}/bitir", data={"donus": "//kotu.example"}).headers["location"].startswith(f"/acil/{acil_id}")


def test_acil_suresi_dolunca_kendiliginden_biter(okul, panel, tahta, saat):
    yeni, _ = okul
    baslat(panel, sure_dk="5", tur="tatbikat")
    assert panel.app.state.acil_denetim() == 1
    saat.ilerlet(5 * 60 + 1)
    assert panel.app.state.acil_denetim() == 0
    satir = sorgu("SELECT * FROM acil_yayin")[0]
    assert satir["bitis_nedeni"] == "sure" and satir["bitis"] == satir["bitis_plan"] and satir["bitiren"] == "sistem"
    assert bekle(tahta, yeni, yeni_ajan_durumu())["ayar"]["acil"] is None
    assert sorgu("SELECT * FROM kayit WHERE islem = 'Tatbikat yayını bitti'")


def test_eski_ajana_acil_yedek_duyuru_ile_gider_ve_bitince_kaldirilir(okul, panel, tahta):
    yeni, eski = okul
    baslat(panel)
    acil_id = sorgu("SELECT id FROM acil_yayin")[0]["id"]
    cevap = bekle(tahta, eski, {"kilitli": True, "ekranlar": [{"arayuz": "gtk3"}]}, surum="0.2.0")
    komut = cevap["komutlar"][0]
    assert komut["tur"] == "duyuru" and komut["veri"]["baslik"] == "ACİL DURUM — TAHLİYE"
    assert komut["veri"]["kapatilabilir"] is False and komut["veri"]["acil_id"] == acil_id
    assert 1790 <= komut["veri"]["sure_sn"] <= 1800
    bekle(tahta, eski, {"kilitli": True}, sonuclar=[{"komut_id": komut["id"], "basarili": True, "cikti": "Duyuru gösteriliyor."}])
    teslim = sorgu("SELECT yol, ekran_var FROM acil_teslim WHERE tahta_id = ?", kimlik(eski))
    assert teslim == [{"yol": "yedek_duyuru", "ekran_var": 0}]
    assert "Yedek duyuru" in panel.get(f"/acil/{acil_id}").text
    # Yeni ajana yedek duyuru gitmez.
    assert all(k["tur"] != "duyuru" for k in bekle(tahta, yeni, yeni_ajan_durumu())["komutlar"])
    panel.post(f"/acil/{acil_id}/bitir")
    kaldir = bekle(tahta, eski, {"kilitli": True}, surum="0.2.0")["komutlar"]
    assert [(k["tur"], k["veri"]) for k in kaldir] == [("duyuru_kaldir", {})]


def test_yedek_duyuru_beklerken_ajan_guncellenirse_iptal_edilir(okul, panel, tahta):
    _, eski = okul
    baslat(panel)
    cevap = bekle(tahta, eski, yeni_ajan_durumu())  # tahta bu arada 0.3.0'a güncellendi
    assert cevap["komutlar"] == [] and cevap["ayar"]["acil"]["tur"] == "acil"
    assert sorgu("SELECT durum FROM komut WHERE tur = 'duyuru'")[0]["durum"] == "iptal"


def test_acil_surerken_otomatik_kapatma_verilmez(okul, panel, tahta, saat):
    panel.post("/ayarlar", data={"bolum": "genel", "okul_adi": "x", "ok_etkin": "1", "ok_saatler": "19:15"})
    baslat(panel)
    zaman = an(16, 19, 16)
    saat.ayarla(an(16, 9, 1))  # acil sürüyor
    for b_ in okul:
        bekle(tahta, b_, yeni_ajan_durumu())
    assert panel.app.state.zamanlayici(zaman) == 0
    assert panel.app.state.zamanlayici(zaman) == 0
    assert len(sorgu("SELECT * FROM kayit WHERE islem = 'Otomatik kapatma acil yayın nedeniyle atlandı'")) == 1
    assert sorgu("SELECT * FROM komut WHERE tur = 'kapat'") == []
    acil_id = sorgu("SELECT id FROM acil_yayin")[0]["id"]
    panel.post(f"/acil/{acil_id}/bitir")
    assert panel.app.state.zamanlayici(an(16, 19, 17)) == 0  # aynı saat işaretlendi; geç kapatma yok


def test_yeni_acil_eskisinin_yerine_gecer(okul, panel, tahta):
    yeni, _ = okul
    baslat(panel, tur="tatbikat", baslik="TATBİKAT")
    baslat(panel, baslik="DEPREM", sablon="deprem")
    satirlar = sorgu("SELECT id, bitis_nedeni, bitis FROM acil_yayin ORDER BY id")
    assert satirlar[0]["bitis_nedeni"] == "yenisi" and satirlar[0]["bitis"] and satirlar[1]["bitis"] is None
    assert bekle(tahta, yeni, yeni_ajan_durumu())["ayar"]["acil"]["id"] == satirlar[1]["id"]


def test_acil_rapor_sayfasi_ve_panel_bandi(okul, panel, tahta, saat):
    yeni, eski = okul
    baslat(panel, tur="tatbikat", baslik="TATBİKAT")
    acil_id = sorgu("SELECT id FROM acil_yayin")[0]["id"]
    saat.ilerlet(4)
    bekle(tahta, yeni, yeni_ajan_durumu(acil_id=acil_id))
    for yol in ("/", "/tahtalar", "/duyurular", "/kayit", "/gruplar"):
        sayfa = panel.get(yol).text
        assert 'class="acil-bant" data-tur="tatbikat" role="alert"' in sayfa and "TATBİKAT YAYINI SÜRÜYOR" in sayfa, yol
        assert f'action="/acil/{acil_id}/bitir"' in sayfa
    rapor = panel.get(f"/acil/{acil_id}").text
    assert "Tatbikat yayını raporu" in rapor and "Yeni ajanlı" in rapor and "Eski ajanlı" in rapor
    assert "1/2 tahtada görüntülendi" in rapor and "<td data-etiket=\"Gecikme (sn)\">4</td>" in rapor
    assert "tahliyenin kendisini değil" in rapor
    acil_sayfasi = panel.get("/acil").text
    assert "1/2" in acil_sayfasi and 'data-onay="acil_bitir"' in acil_sayfasi
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    sayfa = panel.get("/").text  # K4: idareci de bantta "Yayını bitir"i görür
    assert "TATBİKAT YAYINI SÜRÜYOR" in sayfa and f'action="/acil/{acil_id}/bitir"' in sayfa


# ---- 0.19.0: sekmeler (Yayın başlat · Geçmiş ve raporlar | Şablonlar) ---------------------------------------------------
def acil_seridi(sayfa: str) -> str:
    assert sayfa.count('aria-label="Acil durum bölümleri"') == 1
    return sayfa.split('aria-label="Acil durum bölümleri"', 1)[1].split("</nav>", 1)[0]


def test_acil_sekmeleri_icerik(okul, panel):
    baslat(panel, tur="tatbikat", baslik="TATBİKAT")
    acil_id = sorgu("SELECT id FROM acil_yayin")[0]["id"]
    panel.post(f"/acil/{acil_id}/bitir", data={})
    ilk = panel.get("/acil").text
    assert 'id="acil-formu"' in ilk and 'id="acil-gecmis"' not in ilk and f'href="/acil/{acil_id}"' not in ilk
    assert '<a href="/acil" aria-current="page">Yayın başlat</a>' in acil_seridi(ilk)
    assert '<a href="/acil?sekme=gecmis">Geçmiş ve raporlar</a>' in acil_seridi(ilk)
    # Parola ve onay kutusu başlatma formunda (kural 26); geçmiş sekmesinde form yok.
    assert 'name="parola"' in ilk and 'name="onay"' in ilk
    gecmis = panel.get("/acil?sekme=gecmis").text
    assert 'id="acil-gecmis"' in gecmis and f'href="/acil/{acil_id}"' in gecmis and 'id="acil-formu"' not in gecmis
    assert 'name="parola"' not in gecmis
    assert '<a href="/acil?sekme=gecmis" aria-current="page">Geçmiş ve raporlar</a>' in acil_seridi(gecmis)
    for deger in ("yok-boyle", "", "//kotu.example", "<b>"):  # bilinmeyen değer: Yayın başlat, yönlendirme yok, yansıma yok
        yanit = panel.get("/acil", params={"sekme": deger})
        assert yanit.status_code == 200 and 'id="acil-formu"' in yanit.text and "kotu.example" not in yanit.text
        assert '<a href="/acil" aria-current="page">' in acil_seridi(yanit.text)
    rapor = panel.get(f"/acil/{acil_id}").text
    assert '<a href="/acil?sekme=gecmis" aria-current="page">' in acil_seridi(rapor)


def test_acil_surerken_iki_sekmede_aktif_kutu_ve_bitirme_donusu(okul, panel):
    baslat(panel)
    acil_id = sorgu("SELECT id FROM acil_yayin")[0]["id"]
    for yol in ("/acil", "/acil?sekme=gecmis"):
        sayfa = panel.get(yol).text
        assert sayfa.count('id="acil-aktif"') == 1 and sayfa.count('id="acil-teslim"') == 1, yol
        kutu = sayfa.split('id="acil-aktif"', 1)[1].split("</section>", 1)[0]
        assert f'action="/acil/{acil_id}/bitir"' in kutu and f'name="donus" value="{yol}"' in kutu, yol
        assert 'type="button" class="tehlike-dolu" data-onay="acil_bitir"' in kutu, yol  # JS'siz gönderilmez (bilerek)
    yanit = panel.post(f"/acil/{acil_id}/bitir", data={"donus": "/acil?sekme=gecmis"})
    assert yanit.status_code == 303 and yanit.headers["location"].startswith("/acil?sekme=gecmis")
    assert sorgu("SELECT bitis FROM acil_yayin")[0]["bitis"]
    # Dış adres dönüş olarak kabul edilmez.
    baslat(panel)
    yeni_id = sorgu("SELECT MAX(id) AS id FROM acil_yayin")[0]["id"]
    yer = panel.post(f"/acil/{yeni_id}/bitir", data={"donus": "//kotu.example/x"}).headers["location"]
    assert "kotu.example" not in yer and yer.startswith("/")


def test_acil_baslatma_hatasi_baslat_sekmesinde(okul, panel):
    for alanlar in ({"parola": "yanlis"}, {"onay": None}, {"parola": None}):
        yanit = baslat(panel, baslik="DENEME BAŞLIĞI", **alanlar)
        assert yanit.status_code == 400 and sorgu("SELECT * FROM acil_yayin") == [], alanlar
        assert '<a href="/acil" aria-current="page">Yayın başlat</a>' in acil_seridi(yanit.text)
        assert 'id="acil-formu"' in yanit.text and "DENEME BAŞLIĞI" in yanit.text and 'id="acil-gecmis"' not in yanit.text
        assert 'value="yanlis"' not in yanit.text  # parola geri yazılmaz


def test_ayri_acil_yetkisi_kaldirildi(okul, panel):
    """K4: kullanıcılar sayfasında acil yetkisi sütunu ve düğmesi yok; eski sekmeden gelen istek reddedilip kayda düşer."""
    sayfa = panel.get("/ayarlar/kullanicilar").text
    assert "Acil yetkisi ver" not in sayfa and "Acil yetkisini al" not in sayfa
    assert "bütün yönetici ve idareciler başlatabilir" in sayfa
    kullanici_ekle(panel, "yonetici2", "yonetici")
    diger = sorgu("SELECT id, acil_yetki FROM kullanici WHERE ad = 'yonetici2'")[0]
    assert diger["acil_yetki"] == 1  # eski sürüme dönülürse de yetkili kalsın
    assert "artık ayrı verilmez" in ileti(panel.post("/kullanicilar", data={"eylem": "acil_yetki", "id": diger["id"]}))
    assert sorgu("SELECT acil_yetki FROM kullanici WHERE id = ?", diger["id"])[0]["acil_yetki"] == 1
    islemler = [s["islem"] for s in sorgu("SELECT islem FROM kayit WHERE islem LIKE 'Acil yetkisi%' ORDER BY id")]
    assert islemler == ["Acil yetkisi değişikliği reddedildi"]


def test_acil_sablonlari_ayri_bolumde_kaydedilir(okul, panel):
    sayfa = panel.get("/acil?sekme=sablonlar").text
    assert 'value="acil_sablonlari"' in sayfa and "Çök — kapan — tutun." in sayfa
    panel.post("/ayarlar", data={"bolum": "genel", "okul_adi": "Örnek Anadolu Lisesi"})
    yanit = panel.post("/ayarlar", data={"bolum": "acil_sablonlari", "s_ad": ["Tahliye", "", "Sel baskını"],
                                         "s_baslik": ["TAHLİYE", "", "SEL"], "s_metin": ["Çıkınız.", "", "Üst kata çıkınız."]})  # fmt: skip
    assert ileti(yanit) == "Acil şablonları kaydedildi."
    from tahta_sunucu import acil, vt

    with vt.islem() as b:
        assert [(s["kod"], s["ad"]) for s in acil.sablonlar(b)] == [("tahliye", "Tahliye"), ("sel_baskini", "Sel baskını")]
        assert vt.ayar_al(b, "okul_adi") == "Örnek Anadolu Lisesi"  # genel bölüm ezilmedi
    assert "T.C." in ileti(panel.post("/ayarlar", data={"bolum": "acil_sablonlari", "s_ad": "X", "s_metin": SAHTE_TC}))
    panel.post("/ayarlar", data={"bolum": "genel", "okul_adi": "Başka"})
    with vt.islem() as b:
        assert len(acil.sablonlar(b)) == 2  # genel kayıt şablonlara dokunmaz
    panel.post("/ayarlar", data={"bolum": "acil_sablonlari", "eylem": "varsayilan"})
    with vt.islem() as b:
        assert len(acil.sablonlar(b)) == 5
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    assert "yönetici" in ileti(panel.post("/ayarlar", data={"bolum": "acil_sablonlari", "s_ad": "X", "s_metin": "y"}))


def test_zamanlayici_isleri_ayri_ayri_calisir(uygulama):
    from types import SimpleNamespace

    from tahta_sunucu import sunucu

    assert [ad for ad, _ in uygulama.state.zamanlayicilar][:3] == ["acil_denetim", "otomatik_kapatma", "duyuru_planlari"]
    cagrilan = []

    def bozuk():
        raise RuntimeError("deneme")

    sahte = SimpleNamespace(uygulama=SimpleNamespace(state=SimpleNamespace(
        zamanlayicilar=[("a", bozuk), ("b", lambda: cagrilan.append("b"))])))  # fmt: skip
    sunucu.Sunucu.zamanlayici_turu(sahte)
    assert cagrilan == ["b"]


def test_ajan_ayarinda_logo_ozeti_onbellekten(okul, panel, tahta, monkeypatch):
    import struct
    import zlib

    from tahta_sunucu import marka

    def parca(tur, veri):
        return struct.pack(">I", len(veri)) + tur + veri + struct.pack(">I", zlib.crc32(tur + veri))

    png = b"\x89PNG\r\n\x1a\n" + parca(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0)) + parca(
        b"IDAT", zlib.compress(b"\x00" + b"\x10\x20\x30" * 64)
    ) + parca(b"IEND", b"")  # fmt: skip
    panel.post("/ayarlar/logo", files={"logo": ("l.png", png, "image/png")})
    yeni, _ = okul
    ilk = bekle(tahta, yeni, yeni_ajan_durumu())["ayar"]["logo_sha256"]
    sayac = []
    gercek = marka.logo_oku
    monkeypatch.setattr(marka, "logo_oku", lambda b: sayac.append(1) or gercek(b))
    for _ in range(3):
        assert bekle(tahta, yeni, yeni_ajan_durumu())["ayar"]["logo_sha256"] == ilk
    assert sayac == []  # özet her bekle çağrısında yeniden hesaplanmadı
