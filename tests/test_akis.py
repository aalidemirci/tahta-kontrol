"""Uçtan uca akış: kurulum, giriş, tahta kaydı, onay, komut, sonuç."""

from __future__ import annotations

import io
import json
import tarfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    from tahta_sunucu import web

    uygulama = web.uygulama_olustur("ab" * 32)
    panel = TestClient(uygulama, client=("127.0.0.1", 50000), follow_redirects=False)
    tahta = TestClient(uygulama, client=("10.0.0.20", 40000))
    return panel, tahta


def kur_ve_gir(panel):
    yanit = panel.post(
        "/kurulum",
        data={"okul_adi": "Deneme Lisesi", "gorunen_ad": "Deneme Yönetici", "ad": "yonetici", "parola": "gizli-parola", "parola2": "gizli-parola"},
    )
    assert yanit.status_code == 303
    yanit = panel.post("/giris", data={"ad": "yonetici", "parola": "gizli-parola"})
    assert yanit.status_code == 303 and "tk_oturum" in panel.cookies


def kod_al(panel) -> str:
    panel.post("/ekle", data={"eylem": "ac"})
    sayfa = panel.get("/ekle").text
    return sayfa.split('class="buyuk-kod">')[1].split("<")[0]


def kaydol(tahta, kod) -> dict:
    yanit = tahta.post("/ajan/kaydol", json={"kod": kod, "makine_adi": "etap-01", "mac": "aa:bb:cc:dd:ee:ff", "surum": "0.1.0"})
    assert yanit.status_code == 200, yanit.text
    veri = yanit.json()
    return {"X-Tahta-Id": str(veri["tahta_id"]), "X-Tahta-Anahtar": veri["anahtar"]}


def test_kurulum_yalniz_sunucu_bilgisayarindan(ortam):
    _, tahta = ortam
    yanit = tahta.post(
        "/kurulum", data={"ad": "saldirgan", "parola": "12345678", "parola2": "12345678"}, follow_redirects=False
    )
    assert yanit.status_code == 303
    assert tahta.get("/giris", follow_redirects=False).headers["location"].startswith("/kurulum")


def test_giris_olmadan_panel_acilmaz(ortam):
    panel, _ = ortam
    kur_ve_gir(panel)
    panel.cookies.clear()
    assert panel.get("/").status_code == 303
    assert panel.get("/api/durum").status_code == 401
    assert panel.post("/islem", data={"tur": "kapat", "tahta": "1"}).headers["location"].startswith("/giris")


def test_kayit_kodu_olmadan_tahta_kaydolamaz(ortam):
    panel, tahta = ortam
    kur_ve_gir(panel)
    assert tahta.post("/ajan/kaydol", json={"kod": "00000000"}).status_code == 403
    kod = kod_al(panel)
    assert tahta.post("/ajan/kaydol", json={"kod": "yanlis"}).status_code == 403
    assert tahta.post("/ajan/kaydol", json={"kod": kod}).status_code == 200


def test_onaysiz_tahta_komut_almaz_onayli_alir(ortam):
    panel, tahta = ortam
    kur_ve_gir(panel)
    basliklar = kaydol(tahta, kod_al(panel))
    kimlik = basliklar["X-Tahta-Id"]

    yanit = tahta.post("/ajan/bekle", headers=basliklar, json={"surum": "0.1.0", "durum": {"kilitli": False}, "bekle": 0})
    assert yanit.json()["durum"] == "bekliyor"
    # Onaysız tahtaya komut verilemez.
    panel.post("/islem", data={"tur": "kilitle", "tahta": kimlik})
    assert "komutlar" not in tahta.post("/ajan/bekle", headers=basliklar, json={"bekle": 0}).json()

    panel.post(f"/tahta/{kimlik}/kaydet", data={"ad": "11/A tahtası", "derslik": "2. kat", "eylem": "onayla"})
    panel.post("/islem", data={"tur": "kilitle", "tahta": kimlik})
    yanit = tahta.post("/ajan/bekle", headers=basliklar, json={"surum": "0.1.0", "durum": {"kilitli": False}, "bekle": 0}).json()
    assert [k["tur"] for k in yanit["komutlar"]] == ["kilitle"]
    komut_id = yanit["komutlar"][0]["id"]

    # Aynı komut ikinci kez verilmez; sonuç bildirilince kayda geçer.
    yanit = tahta.post(
        "/ajan/bekle",
        headers=basliklar,
        json={"durum": {"kilitli": True}, "sonuclar": [{"komut_id": komut_id, "basarili": True, "cikti": "Kilitlendi."}], "bekle": 0},
    ).json()
    assert yanit["komutlar"] == []
    durum = panel.get("/api/durum").json()["tahtalar"][0]
    assert durum["cevrimici"] and durum["kilitli"] and durum["ad"] == "11/A tahtası"
    assert "Kilitlendi." in panel.get(f"/tahta/{kimlik}").text


def test_yanlis_anahtar_reddedilir_ve_kaldirilan_tahta_baglanamaz(ortam):
    panel, tahta = ortam
    kur_ve_gir(panel)
    basliklar = kaydol(tahta, kod_al(panel))
    kimlik = basliklar["X-Tahta-Id"]
    assert tahta.post("/ajan/bekle", headers={**basliklar, "X-Tahta-Anahtar": "baska"}, json={}).status_code == 401
    panel.post(f"/tahta/{kimlik}/kaydet", data={"ad": "x", "eylem": "sil"})
    assert tahta.post("/ajan/bekle", headers=basliklar, json={}).status_code == 401


def test_duyuru_kalan_sureyle_iletilir_ve_tani_raporu_saklanir(ortam):
    panel, tahta = ortam
    kur_ve_gir(panel)
    basliklar = kaydol(tahta, kod_al(panel))
    kimlik = basliklar["X-Tahta-Id"]
    panel.post(f"/tahta/{kimlik}/kaydet", data={"ad": "Tahta", "eylem": "onayla"})
    panel.post("/islem", data={"tur": "duyuru", "tahta": kimlik, "metin": "Tören 10.00'da.", "sure_dk": "3", "kapatilabilir": "1"})
    panel.post("/islem", data={"tur": "tani", "tahta": kimlik})
    komutlar = tahta.post("/ajan/bekle", headers=basliklar, json={"bekle": 0}).json()["komutlar"]
    duyuru = next(k for k in komutlar if k["tur"] == "duyuru")
    assert 170 <= duyuru["veri"]["sure_sn"] <= 180 and duyuru["veri"]["kapatilabilir"] is True
    tani = next(k for k in komutlar if k["tur"] == "tani")
    rapor = {"ajan_surumu": "0.1.0", "zaman": 1, "denetimler": [{"ad": "Python", "sonuc": "tamam", "ayrinti": "Python 3.11"}]}
    tahta.post(
        "/ajan/bekle",
        headers=basliklar,
        json={"sonuclar": [{"komut_id": tani["id"], "basarili": True, "cikti": json.dumps(rapor)}], "bekle": 0},
    )
    assert "Python 3.11" in panel.get(f"/tahta/{kimlik}").text
    assert "Tören 10.00" in panel.get("/duyurular").text


def test_idareci_yonetici_islemlerini_yapamaz(ortam):
    panel, _ = ortam
    kur_ve_gir(panel)
    panel.post("/kullanicilar", data={"eylem": "ekle", "ad": "idareci1", "gorunen_ad": "İdareci", "parola": "uzun-parola", "rol": "idareci"})
    panel.post("/cikis")
    panel.cookies.clear()
    panel.post("/giris", data={"ad": "idareci1", "parola": "uzun-parola"})
    assert panel.get("/ayarlar").headers["location"].startswith("/?m=")
    assert panel.get("/kullanicilar").headers["location"].startswith("/?m=")
    panel.post("/ekle", data={"eylem": "ac"})
    assert "buyuk-kod" not in panel.get("/ekle").text


def test_baska_siteden_gelen_istek_reddedilir(ortam):
    panel, _ = ortam
    kur_ve_gir(panel)
    yanit = panel.post("/islem", data={"tur": "kapat", "tahta": "1"}, headers={"Origin": "https://kotu.example"})
    assert yanit.status_code == 403


def test_ajan_paketi_gecerli_bir_deb(ortam):
    from tahta_sunucu import paket

    p = paket.ajan_paketi()
    assert p.icerik.startswith(b"!<arch>\ndebian-binary")
    konum = 8
    uyeler = {}
    while konum < len(p.icerik):
        baslik = p.icerik[konum : konum + 60]
        ad = baslik[:16].decode().strip()
        boyut = int(baslik[48:58].decode().strip())
        uyeler[ad] = p.icerik[konum + 60 : konum + 60 + boyut]
        konum += 60 + boyut + (boyut % 2)
    assert list(uyeler) == ["debian-binary", "control.tar.gz", "data.tar.gz"]
    with tarfile.open(fileobj=io.BytesIO(uyeler["data.tar.gz"])) as arsiv:
        adlar = arsiv.getnames()
        betik = arsiv.extractfile("./usr/bin/tahta-ajan").read()
    assert "./opt/tahta-kontrol/tahta_ajan/servis.py" in adlar
    assert "./etc/xdg/autostart/tahta-ekran.desktop" in adlar
    assert b"\r" not in betik
    with tarfile.open(fileobj=io.BytesIO(uyeler["control.tar.gz"])) as arsiv:
        kontrol = arsiv.extractfile("./control").read().decode()
    assert f"Version: {p.surum}" in kontrol
    betik = paket.kurulum_betigi("https://10.0.0.5:8788", "ab" * 32).decode()
    assert p.sha256 in betik and "@" not in betik.split("<<'PY'")[0].replace("$@", "")


def test_surumler_tutarli():
    from pathlib import Path

    import tahta_ajan
    import tahta_sunucu

    surum = (Path(__file__).resolve().parent.parent / "VERSION").read_text(encoding="utf-8").strip()
    assert tahta_ajan.__version__ == tahta_sunucu.__version__ == surum
