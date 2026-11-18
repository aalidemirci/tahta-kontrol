"""Aşama 3 — program sayfası sekmeleri, pano şeridi, tahta ızgarası ve ajan ile uçtan uca program kilidi.

Saat `saat` fikstürüyle sabittir (pazartesi 16.11.2026); veriler uydurmadır.
"""

from __future__ import annotations

import re

import pytest
from test_program_panel import calistir, durum, hazirla
from yardimci import an, bekle, gir, kimlik, kullanici_ekle, kur_ve_gir, tahta_ekle


def test_saat_eki_sunucu_ve_ajan_ayni():
    from tahta_ajan import ekran
    from tahta_sunucu import program

    for ss in range(24):
        for dd in range(60):
            saat = f"{ss:02d}:{dd:02d}"
            assert program.saat_eki(saat) == ekran.saat_eki(saat), saat
    assert program.saat_eki("10:40") == "10:40'ta" and program.saat_eki("12:15") == "12:15'te"


def test_menu_sirasi_ortak_sozluge_uyar(uygulama, panel):
    kur_ve_gir(panel)
    sayfa = panel.get("/program").text
    menu = sayfa.split('aria-label="Ana menü"')[1].split("</nav>")[0]
    sira = [menu.index(f">{ad}<") for ad in ("Tahtalar", "Duyurular", "Yoklama", "Program", "Sınavlar", "İşlem kaydı")]
    assert sira == sorted(sira)
    assert re.search(r'<a href="/program" aria-current="page">.*?<span>Program</span>', menu, re.S)


@pytest.mark.parametrize(
    "bolum, beklenen",
    [
        ("zil", ['data-onay="zil_sil"', "08:20–09:00", 'action="/program/zil/yukle"', 'action="/program/haftalik"',
                 'action="/program/cizelge"', 'action="/program/tarihli"', 'action="/program/gun"']),
        ("derslik", ['href="/program/aktar?yeni=1"', 'href="/program/aktar/mevcut.csv"', "Program yok", "Önceki programlar"]),
        ("kurallar", ['name="pk_etkin"', "Kuralları kaydet", "öğretmen adı tutulmaz"]),
        ("istisnalar", ['name="bas_tarih"', 'value="1sa"', "Öğrenci ya da kişi adı yazmayın."]),
    ],
)
def test_program_sekmeleri_yonetici(uygulama, panel, tahta, bolum, beklenen):
    hazirla(panel)
    tahta_ekle(panel, tahta, "T-1", durum())
    sayfa = panel.get(f"/program?bolum={bolum}")
    assert sayfa.status_code == 200
    metin = sayfa.text
    assert f'href="/program?bolum={bolum}" aria-current="page"' in metin
    for parca in beklenen:
        assert parca in metin, (bolum, parca)
    assert 'id="program-serit"' in metin and "Program kilidi açık" in metin
    # Sekme yalnız kendi bölümünü çizer.
    if bolum != "kurallar":
        assert 'name="pk_etkin"' not in metin


def test_program_sayfasi_idareciye_salt_okunur(uygulama, panel, tahta):
    hazirla(panel)
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    zil = panel.get("/program").text
    assert "08:20–09:00" in zil and 'action="/program/zil/' not in zil and "zil_sil" not in zil
    kurallar = panel.get("/program?bolum=kurallar").text
    assert 'fieldset class="duz" disabled' in kurallar and "Kuralları kaydet" not in kurallar
    assert 'action="/program/istisna"' in panel.get("/program?bolum=istisnalar").text
    uyarilar = panel.get("/program/uyarilar").text
    assert 'href="/program/uyarilar" aria-current="page"' in uyarilar and "Bu tarihte boş ders uyarısı yok." in uyarilar


def test_pano_program_seridi_ve_durdur_menusu(uygulama, panel, tahta):
    kur_ve_gir(panel)
    tahta_ekle(panel, tahta, "T-1", durum())
    assert 'id="pano-program"' not in panel.get("/").text  # zil saati yokken şerit yok
    hazirla(panel)
    sayfa = panel.get("/").text
    serit = sayfa.split('id="pano-program"')[1].split("</section>")[0]
    assert "Program kilidi açık" in serit and 'data-alan="simdi"' in serit
    assert 'action="/program/istisna"' in serit and 'name="donus" value="/"' in serit
    assert '"program_kilidi": true' in sayfa
    # Kural kapalıyken durdur menüsü gizli gelir.
    panel.post("/program/kurallar", data={"pk_gecikme_dk": "2", "bd_esik_dk": "10"})
    serit = panel.get("/").text.split('id="pano-program"')[1].split("</section>")[0]
    assert "Program kilidi kapalı" in serit and re.search(r'data-alan="durdur"\s+hidden', serit)


def test_tahta_sayfasi_program_izgarasi(uygulama, panel, tahta):
    hazirla(panel)
    t = kimlik(tahta_ekle(panel, tahta, "T-1", durum()))
    panel.post(f"/tahta/{t}/program", data={"d_0_normal_1": "1", "sube_0_normal_1": "9/a"})
    sayfa = panel.get(f"/tahta/{t}").text
    kutu = sayfa.split('id="program"')[1].split("</section>")[0]
    assert 'name="d_0_normal_1" value="1" checked' in kutu and 'name="sube_0_normal_1" value="9/A"' in kutu
    assert 'name="d_4_normal_8"' in kutu and 'data-izgara="hepsi"' in kutu
    assert "1 / 40" in kutu
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    kutu = panel.get(f"/tahta/{t}").text.split('id="program"')[1].split("</section>")[0]
    assert 'action="/tahta/' not in kutu and "Ders · 9/A" in kutu and 'value="1sa"' in kutu


def test_program_kilidi_ajan_ile_uctan_uca(uygulama, panel, tahta, saat, tmp_path, monkeypatch):
    """Sunucunun verdiği program kilidi gerçek ajan servisinde uygulanır, durumu panele döner,
    istisna eklenince açma komutu gelir ve ajan kilidi açar."""
    monkeypatch.setenv("TAHTA_AJAN_DIZIN", str(tmp_path / "ajan"))
    monkeypatch.setenv("TAHTA_AJAN_DURUM", str(tmp_path / "ajan-durum"))
    from tahta_ajan import servis as servis_mod

    monkeypatch.setattr(servis_mod.sistem, "etkin_oturum", lambda: {"sinif": "ogretmen"})
    monkeypatch.setattr(servis_mod.sistem, "acik_sure", lambda: 100)
    monkeypatch.setattr(servis_mod.sistem, "ag_bilgisi", lambda *_: {})
    ajan = servis_mod.Servis()
    ajan.bildir = lambda: None
    ajan.ekranlar[1] = {"gonder": lambda _m: None, "bilgi": {"arayuz": "gtk3"}}

    hazirla(panel)
    saat.ayarla(an(16, 9, 0, 30))
    b = tahta_ekle(panel, tahta, "T-1", ajan.durum_ozeti())
    assert calistir(uygulama, saat, an(16, 9, 2, 10)) == [kimlik(b)]
    saat.ayarla(an(16, 9, 2, 20))
    komutlar = bekle(tahta, b, ajan.durum_ozeti())["komutlar"]
    assert [k["tur"] for k in komutlar] == ["kilitle"]
    basarili, cikti = ajan.komut_uygula(komutlar[0])
    assert basarili and ajan.kilit_kaynak == "program" and 455 <= ajan.kilit_kalan() <= 460
    ekran = ajan.gorunum()
    assert ekran["kilit_neden"] == "Teneffüs" and ekran["kilit_acilis"] == "09:10"

    sonuc = [{"komut_id": komutlar[0]["id"], "basarili": basarili, "cikti": cikti}]
    bekle(tahta, b, ajan.durum_ozeti(), sonuclar=sonuc)
    kart = panel.get("/api/durum").json()["tahtalar"][0]
    assert kart["kilitli"] is True
    assert kart["program"]["kilit_kaynak"] == "program" and kart["program"]["acilis"] == "09:10"
    assert kart["program"]["neden"] == "Teneffüs"
    assert "Program kilidi (Teneffüs), 09:10&#39;da açılır" in panel.get(f"/tahta/{kimlik(b)}").text

    # İstisna (1 saat durdur) eklenince program kaynaklı kilitli tahtaya açma gider.
    panel.post("/program/istisna", data={"sure": "1sa"})
    komutlar = bekle(tahta, b, ajan.durum_ozeti())["komutlar"]
    assert [(k["tur"], k["veri"]) for k in komutlar] == [("kilit_ac", {"kaynak": "program"})]
    assert ajan.komut_uygula(komutlar[0]) == (True, "Kilit açıldı.")
    assert ajan.kilitli is False
    bekle(tahta, b, ajan.durum_ozeti())
    assert panel.get("/api/durum").json()["tahtalar"][0]["program"]["kilit_kaynak"] is None


def test_elle_uretim_formu_alanlari_sunucuyla_uyumlu(uygulama, panel):
    """0.10.0: çizelge sayfasındaki hızlı oluştur formunun alan adları sunucunun beklediği adlarla aynıdır."""
    from tahta_sunucu import cizelge

    kur_ve_gir(panel)
    yer = panel.post("/program/cizelge", data={"ad": "Normal gün", "duzen": "tek"}).headers["location"]
    sayfa = panel.get(yer).text
    for alan in cizelge.HIZLI_ALANLAR:
        assert f'name="normal_{alan}"' in sayfa, alan
    assert 'name="normal_uret"' in sayfa and 'action="/program/cizelge/1/hizli"' in sayfa
