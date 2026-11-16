"""Ortak fikstürler. Eski test dosyaları kendi yerel `ortam` fikstürlerini kullanmayı sürdürür."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def saat(monkeypatch):
    """vt.simdi()'yi elle ilerletilen sabit bir saate bağlar (pazartesi 16.11.2026 09:00)."""
    from yardimci import an

    from tahta_sunucu import vt

    class Saat:
        def __init__(self):
            self.t = int(an(16, 9).timestamp())

        def ayarla(self, zaman) -> None:
            self.t = int(zaman.timestamp())

        def ilerlet(self, saniye: int) -> None:
            self.t += saniye

    s = Saat()
    monkeypatch.setattr(vt, "simdi", lambda: s.t)
    return s


@pytest.fixture()
def uygulama(tmp_path, monkeypatch, saat):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    from tahta_sunucu import web

    return web.uygulama_olustur("ab" * 32)


@pytest.fixture()
def panel(uygulama):
    return TestClient(uygulama, client=("127.0.0.1", 50000), follow_redirects=False)


@pytest.fixture()
def tahta(uygulama):
    return TestClient(uygulama, client=("10.0.0.20", 40000))
