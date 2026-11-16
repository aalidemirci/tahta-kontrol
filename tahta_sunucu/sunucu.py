"""Sunucuyu başlatır: panel için yerel HTTP, okul ağı ve tahtalar için HTTPS."""

from __future__ import annotations

import logging
import socket
import threading
import time

import uvicorn

from . import ayar, guvenlik, paket, web, yedek

gunluk = logging.getLogger("tahta-sunucu")


class Sunucu:
    def __init__(self):
        veri = ayar.veri_dizini()
        # A6: onaylanmış geri yükleme, veritabanı ve sertifika açılmadan ÖNCE yerleştirilir.
        self.geri_yukleme_iletisi = yedek.bekleyeni_uygula(veri)
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
        threading.Thread(target=self._zamanlayici, daemon=True).start()
        gunluk.info("Panel (bu bilgisayar): %s", self.yerel_adres)
        for adres in self.ag_adresleri():
            gunluk.info("Panel (okul ağı)     : %s", adres)

    def zamanlayici_turu(self) -> None:
        """Zamanlayıcı işlerini sırayla çalıştırır; biri çökerse diğerleri sürer (ortak sözlük §2.3)."""
        for ad, is_ in self.uygulama.state.zamanlayicilar:
            try:
                is_()
            except Exception:  # zamanlayıcı hatası sunucuyu düşürmez
                gunluk.exception("Zamanlayıcı işi başarısız: %s", ad)

    def _zamanlayici(self) -> None:
        """Acil denetimi, otomatik kapatma ve duyuru planlarını 20 sn'de bir işletir.

        İlk tur sunucu açılır açılmaz çalışır: kapalıyken kaçırılan gösterimler hemen
        yayımlanır ya da "kaçırıldı" yazılır.
        """
        while not any(s.should_exit for s in self.sunucular):
            self.zamanlayici_turu()
            time.sleep(20)

    def calisiyor_mu(self) -> bool:
        return bool(self.is_parcalari) and all(p.is_alive() for p in self.is_parcalari)

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
