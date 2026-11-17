"""Gerçek HTTP ayrıştırıcısıyla sınırlı indirme; ağ bağlantısı kurulmaz."""

from __future__ import annotations

import io
from http.client import HTTPResponse

import pytest

from tahta_ajan import baglanti


class Soket:
    def __init__(self, veri):
        self.veri = io.BytesIO(veri)

    def makefile(self, *args):
        return self.veri


def yanit_uret(govde, baslik=b""):
    yanit = HTTPResponse(Soket(b"HTTP/1.1 200 OK\r\n" + baslik + b"\r\n" + govde))
    yanit.begin()
    return yanit


@pytest.mark.parametrize("baslik", [b"", b"Content-Length: 4\r\n"])
def test_sinirda_yanit_kabul_edilir(baslik):
    assert baglanti._yanit_oku(yanit_uret(b"1234", baslik), 4) == b"1234"


@pytest.mark.parametrize("baslik", [b"", b"Content-Length: 5\r\n"])
def test_buyuk_yanit_reddedilir(baslik):
    with pytest.raises(baglanti.BaglantiHatasi, match="boyutu"):
        baglanti._yanit_oku(yanit_uret(b"12345", baslik), 4)


def test_buyuk_baslik_govde_okunmadan_reddedilir():
    yanit = yanit_uret(b"", b"Content-Length: 999999999\r\n")
    with pytest.raises(baglanti.BaglantiHatasi, match="boyutu"):
        baglanti._yanit_oku(yanit, 4)
    assert yanit.length == 999999999


def test_kesik_yanit_reddedilir():
    with pytest.raises(baglanti.BaglantiHatasi, match="tamamlanmadan"):
        baglanti._yanit_oku(yanit_uret(b"12", b"Content-Length: 4\r\n"), 4)


@pytest.mark.parametrize("govde,basarili", [(b"4\r\n1234\r\n0\r\n\r\n", True),
                                         (b"5\r\n12345\r\n0\r\n\r\n", False)])
def test_chunked_yanit_siniri(govde, basarili):
    yanit = yanit_uret(govde, b"Transfer-Encoding: chunked\r\n")
    if basarili:
        assert baglanti._yanit_oku(yanit, 4) == b"1234"
    else:
        with pytest.raises(baglanti.BaglantiHatasi):
            baglanti._yanit_oku(yanit, 4)


@pytest.mark.parametrize("yol,ham,sinir", [("/ajan/bekle", False, "JSON_SINIRI"),
                                        ("/ajan/paket", True, "PAKET_SINIRI"),
                                        ("/ajan/logo", True, "LOGO_SINIRI")])
def test_istemci_siniri_uygular_ve_hatada_baglantiyi_kapatir(monkeypatch, yol, ham, sinir):
    class Baglanti:
        kapandi = False

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return yanit_uret(b"12345")

        def close(self):
            self.kapandi = True

    ag = Baglanti()
    istemci = baglanti.Istemci("https://ornek.invalid", "ab" * 32)
    monkeypatch.setattr(istemci, "_baglan", lambda _: ag)
    monkeypatch.setattr(baglanti, sinir, 4)
    with pytest.raises(baglanti.BaglantiHatasi, match="boyutu"):
        istemci.istek("GET", yol, ham=ham)
    assert ag.kapandi


@pytest.mark.parametrize("govde,ham,beklenen", [(b'{"durum":"onayli"}', False, {"durum": "onayli"}),
                                             (b"", False, {}), (b"paket", True, b"paket")])
def test_istemci_normal_yaniti_cozer(monkeypatch, govde, ham, beklenen):
    class Baglanti:
        kapandi = False

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return yanit_uret(govde, f"Content-Length: {len(govde)}\r\n".encode())

        def close(self):
            self.kapandi = True

    ag = Baglanti()
    istemci = baglanti.Istemci("https://ornek.invalid", "ab" * 32)
    monkeypatch.setattr(istemci, "_baglan", lambda _: ag)
    kod, veri, _ = istemci.istek("GET", "/ajan/paket" if ham else "/ajan/bekle", ham=ham)
    assert kod == 200 and veri == beklenen and ag.kapandi
