"""Sunucuyla konuşan istemci.

Sunucu kendi ürettiği sertifikayı kullanır; ajan sertifika zincirine değil,
kurulumda kaydedilen parmak izine (SHA-256) güvenir. Parmak izi tutmayan
sunucuya tek bayt gönderilmez.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import ssl
from urllib.parse import urlsplit


class BaglantiHatasi(Exception):
    pass


class ParmakIziHatasi(BaglantiHatasi):
    pass


class Istemci:
    def __init__(self, sunucu: str, parmak_izi: str = "", tahta_id=None, anahtar: str = ""):
        self.sunucu = sunucu.rstrip("/")
        self.parmak_izi = (parmak_izi or "").lower().replace(":", "")
        self.tahta_id = tahta_id
        self.anahtar = anahtar
        parca = urlsplit(self.sunucu)
        self.guvenli = parca.scheme == "https"
        self.ana_makine = parca.hostname or ""
        self.port = parca.port or (443 if self.guvenli else 80)

    def _baglan(self, zaman_asimi: float):
        if not self.guvenli:
            return http.client.HTTPConnection(self.ana_makine, self.port, timeout=zaman_asimi)
        if not self.parmak_izi:
            raise ParmakIziHatasi("Sunucu parmak izi tanımlı değil.")
        baglam = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        baglam.check_hostname = False
        baglam.verify_mode = ssl.CERT_NONE
        baglanti = http.client.HTTPSConnection(
            self.ana_makine, self.port, timeout=zaman_asimi, context=baglam
        )
        baglanti.connect()
        sertifika = baglanti.sock.getpeercert(binary_form=True)
        if not sertifika or hashlib.sha256(sertifika).hexdigest() != self.parmak_izi:
            baglanti.close()
            raise ParmakIziHatasi("Sunucu sertifikası kayıtlı parmak iziyle uyuşmuyor.")
        return baglanti

    def istek(self, yontem: str, yol: str, govde=None, zaman_asimi: float = 15, ham: bool = False):
        """(durum kodu, veri, başlıklar) döndürür. ham=True ise veri bayttır."""
        basliklar = {"Accept": "application/json", "User-Agent": "tahta-ajan"}
        if self.tahta_id is not None:
            basliklar["X-Tahta-Id"] = str(self.tahta_id)
            basliklar["X-Tahta-Anahtar"] = self.anahtar
        veri = None
        if govde is not None:
            veri = json.dumps(govde, ensure_ascii=False).encode("utf-8")
            basliklar["Content-Type"] = "application/json; charset=utf-8"
        baglanti = None
        try:
            baglanti = self._baglan(zaman_asimi)
            baglanti.request(yontem, yol, body=veri, headers=basliklar)
            yanit = baglanti.getresponse()
            icerik = yanit.read()
            yanit_basliklari = {k.lower(): v for k, v in yanit.getheaders()}
            if ham:
                return yanit.status, icerik, yanit_basliklari
            try:
                cozulmus = json.loads(icerik.decode("utf-8")) if icerik else {}
            except ValueError:
                cozulmus = {"hata": icerik[:200].decode("utf-8", "replace")}
            return yanit.status, cozulmus, yanit_basliklari
        except BaglantiHatasi:
            raise
        except (OSError, http.client.HTTPException, ssl.SSLError) as hata:
            raise BaglantiHatasi(f"{type(hata).__name__}: {hata}") from hata
        finally:
            if baglanti is not None:
                try:
                    baglanti.close()
                except OSError:
                    pass
