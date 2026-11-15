"""Sunucuyu başlatır: panel için yerel HTTP, okul ağı ve tahtalar için HTTPS."""

from __future__ import annotations

import logging
import socket
import threading
import time

import uvicorn

from . import ayar, guvenlik, paket, web

gunluk = logging.getLogger("tahta-sunucu")


class Sunucu:
    def __init__(self):
        veri = ayar.veri_dizini()
        self.sertifika, self.anahtar, self.parmak_izi = guvenlik.sertifika_hazirla(veri)
        self.uygulama = web.uygulama_olustur(self.parmak_izi)
        self.paket = paket.ajan_paketi()
        ortak = {"log_level": "warning", "access_log": False, "timeout_keep_alive": 30}
        self.sunucular = [
            uvicorn.Server(uvicorn.Config(self.uygulama, host=ayar.HTTP_MAKINE, port=ayar.HTTP_PORT, **ortak)),
            uvicorn.Server(
                uvicorn.Config(
                    self.uygulama,
                    host=ayar.HTTPS_MAKINE,
                    port=ayar.HTTPS_PORT,
                    ssl_certfile=str(self.sertifika),
                    ssl_keyfile=str(self.anahtar),
                    **ortak,
                )
            ),
        ]
        self.is_parcalari: list[threading.Thread] = []

    @property
    def yerel_adres(self) -> str:
        return f"http://127.0.0.1:{ayar.HTTP_PORT}"

    def ag_adresleri(self) -> list[str]:
        return [f"https://{ip}:{ayar.HTTPS_PORT}" for ip in guvenlik.yerel_ipler()]

    @staticmethod
    def port_bos(makine: str, port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as soket:
            try:
                soket.bind(("127.0.0.1" if makine == "0.0.0.0" else makine, port))
            except OSError:
                return False
        return True

    def baslat(self) -> None:
        for makine, port in ((ayar.HTTP_MAKINE, ayar.HTTP_PORT), (ayar.HTTPS_MAKINE, ayar.HTTPS_PORT)):
            if not self.port_bos(makine, port):
                raise RuntimeError(
                    f"{port} numaralı bağlantı noktası kullanımda. Tahta Kontrol zaten çalışıyor olabilir."
                )
        for sunucu in self.sunucular:
            parca = threading.Thread(target=sunucu.run, daemon=True)
            parca.start()
            self.is_parcalari.append(parca)
        bitis = time.time() + 15
        while time.time() < bitis and not all(s.started for s in self.sunucular):
            time.sleep(0.1)
        if not all(s.started for s in self.sunucular):
            raise RuntimeError("Sunucu 15 saniyede açılamadı.")
        gunluk.info("Panel (bu bilgisayar): %s", self.yerel_adres)
        for adres in self.ag_adresleri():
            gunluk.info("Panel (okul ağı)     : %s", adres)

    def durdur(self) -> None:
        for sunucu in self.sunucular:
            sunucu.should_exit = True
        for parca in self.is_parcalari:
            parca.join(timeout=8)

    def bekle(self) -> None:
        try:
            while all(p.is_alive() for p in self.is_parcalari):
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.durdur()
