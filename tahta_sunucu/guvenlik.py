"""Parola özetleri, belirteçler ve sunucu sertifikası."""

from __future__ import annotations

import datetime
import hashlib
import hmac
import ipaddress
import secrets
import socket
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

_N, _R, _P = 2**14, 8, 1
KILIT_KODU_TUR = 120_000


def parola_ozetle(parola: str) -> str:
    tuz = secrets.token_bytes(16)
    ozet_degeri = hashlib.scrypt(parola.encode("utf-8"), salt=tuz, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${tuz.hex()}${ozet_degeri.hex()}"


def parola_dogrula(parola: str, kayitli: str) -> bool:
    try:
        tur, tuz, ozet_degeri = kayitli.split("$")
        if tur != "scrypt":
            return False
        hesap = hashlib.scrypt(parola.encode("utf-8"), salt=bytes.fromhex(tuz), n=_N, r=_R, p=_P, dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(hesap.hex(), ozet_degeri)


def belirtec() -> str:
    return secrets.token_urlsafe(32)


def ozet(metin: str) -> str:
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


def kilit_kodu_ozetle(kod: str) -> dict:
    """Tahtaya gönderilen kilit kodu özeti; kodun kendisi tahtaya gitmez."""
    tuz = secrets.token_bytes(16)
    deger = hashlib.pbkdf2_hmac("sha256", kod.encode("utf-8"), tuz, KILIT_KODU_TUR).hex()
    return {"tuz": tuz.hex(), "ozet": deger, "tur": KILIT_KODU_TUR}


def kayit_kodu() -> str:
    return f"{secrets.randbelow(10**8):08d}"


def yerel_ipler() -> list[str]:
    adresler: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as soket:
            soket.connect(("10.255.255.255", 1))
            adresler.append(soket.getsockname()[0])
    except OSError:
        pass
    try:
        for bilgi in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            adres = bilgi[4][0]
            if adres not in adresler:
                adresler.append(adres)
    except OSError:
        pass
    return [a for a in adresler if not a.startswith("127.")]


def sertifika_hazirla(dizin: Path) -> tuple[Path, Path, str]:
    """Sunucu sertifikasını bir kez üretir.

    Tahtalar bu sertifikanın parmak izine bağlanır; bu yüzden sertifika
    SONRADAN YENİLENMEZ. Yenilenirse bütün tahtalar yeniden kurulmak zorunda
    kalır. Yedeklenmesi gereken dosyalardandır.
    """
    sertifika_yolu, anahtar_yolu = dizin / "sunucu-sertifika.pem", dizin / "sunucu-anahtar.pem"
    if not (sertifika_yolu.exists() and anahtar_yolu.exists()):
        anahtar = ec.generate_private_key(ec.SECP256R1())
        ad = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Tahta Kontrol Sunucusu")])
        alternatifler: list[x509.GeneralName] = [x509.DNSName("localhost")]
        for adres in ["127.0.0.1", *yerel_ipler()]:
            alternatifler.append(x509.IPAddress(ipaddress.ip_address(adres)))
        simdi = datetime.datetime.now(datetime.UTC)
        sertifika = (
            x509.CertificateBuilder()
            .subject_name(ad)
            .issuer_name(ad)
            .public_key(anahtar.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(simdi - datetime.timedelta(days=1))
            .not_valid_after(simdi + datetime.timedelta(days=365 * 20))
            .add_extension(x509.SubjectAlternativeName(alternatifler), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(anahtar, hashes.SHA256())
        )
        anahtar_yolu.write_bytes(
            anahtar.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        sertifika_yolu.write_bytes(sertifika.public_bytes(serialization.Encoding.PEM))
    yuklu = x509.load_pem_x509_certificate(sertifika_yolu.read_bytes())
    parmak_izi = hashlib.sha256(yuklu.public_bytes(serialization.Encoding.DER)).hexdigest()
    return sertifika_yolu, anahtar_yolu, parmak_izi
