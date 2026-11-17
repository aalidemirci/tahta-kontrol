"""Yavaş yedek ana zamanlayıcıyı bekletmez; iş ve kapanış yarışları."""

from __future__ import annotations

import threading
from types import SimpleNamespace

import pytest

from tahta_sunucu.sunucu import Sunucu
from tahta_sunucu.yedek_is import YedekIsleyici


def test_is_parcacigi_baslatilamazsa_kapanis_bozulmaz(monkeypatch):
    def baslatilamadi(self):
        raise RuntimeError("iş parçacığı ayrılamadı")

    isleyici = YedekIsleyici()
    monkeypatch.setattr(threading.Thread, "start", baslatilamadi)
    with pytest.raises(RuntimeError, match="ayrılamadı"):
        isleyici.baslat(lambda: None)
    assert isleyici.durdur()


def test_yavas_yedekte_diger_isler_ve_sonraki_tur_surer():
    basladi, birak = threading.Event(), threading.Event()
    cagrilar = []

    def yavas():
        cagrilar.append("yedek")
        basladi.set()
        assert birak.wait(5)

    sunucu = Sunucu.__new__(Sunucu)
    sunucu._yedek_isleyici = YedekIsleyici()
    sunucu.uygulama = SimpleNamespace(state=SimpleNamespace(zamanlayicilar=[
        ("acil", lambda: cagrilar.append("acil")),
        ("yedek", yavas),
        ("program", lambda: cagrilar.append("program")),
        ("usb", lambda: cagrilar.append("usb")),
    ]))
    try:
        sunucu.zamanlayici_turu()
        assert basladi.wait(2)
        sunucu.zamanlayici_turu()
        assert cagrilar.count("yedek") == 1
        assert cagrilar.count("acil") == cagrilar.count("program") == cagrilar.count("usb") == 2
    finally:
        birak.set()
        assert sunucu._yedek_isleyici.durdur(2)


def test_hata_sonrasi_yeni_tur_calisebilir(caplog):
    isleyici = YedekIsleyici()

    def bozuk():
        raise OSError("sahte disk hatası")

    assert isleyici.baslat(bozuk)
    isleyici._parca.join(2)
    bitti = threading.Event()
    assert isleyici.baslat(bitti.set)
    assert bitti.wait(2)
    assert isleyici.durdur(2)
    assert "sahte disk hatası" in caplog.text


def test_kapanis_yeni_isi_engeller_ve_suren_isi_bekleyebilir():
    isleyici = YedekIsleyici()
    basladi, birak = threading.Event(), threading.Event()

    def yavas():
        basladi.set()
        assert birak.wait(5)

    try:
        assert isleyici.baslat(yavas)
        assert basladi.wait(2)
        assert not isleyici.durdur(0)
        assert not isleyici.baslat(lambda: None)
    finally:
        birak.set()
        assert isleyici.durdur(2)
    assert not isleyici.baslat(lambda: None)


def test_sunucu_kapanisi_zamanlayiciyi_uyandirir():
    sunucu = Sunucu.__new__(Sunucu)
    sunucu._durdu = threading.Event()
    sunucu._yedek_isleyici = YedekIsleyici()
    sunucu.sunucular = [SimpleNamespace(should_exit=False)]
    sunucu.is_parcalari = []
    tur = threading.Event()
    sunucu.uygulama = SimpleNamespace(state=SimpleNamespace(zamanlayicilar=[("is", tur.set)]))
    sunucu._zamanlayici_parcasi = threading.Thread(target=sunucu._zamanlayici, daemon=True)
    sunucu._zamanlayici_parcasi.start()
    assert tur.wait(2)
    sunucu.durdur()
    assert not sunucu._zamanlayici_parcasi.is_alive()
    assert sunucu.sunucular[0].should_exit
