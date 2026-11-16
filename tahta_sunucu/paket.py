"""Tahta ajanının kurulum paketini (.deb) ve kurulum betiğini üretir.

Paket sunucunun içinde taşınan ajan kaynağından, dış araç (dpkg-deb) olmadan
üretilir; böylece Windows'ta çalışan sunucu tahtalara paket dağıtabilir ve
sunucu güncellenince ajan paketi de kendiliğinden yenilenir.

Üretim belirlenimlidir (sabit zaman damgası): içerik değişmedikçe paketin
özeti değişmez.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import tarfile
import zipfile
import zlib
from dataclasses import dataclass
from functools import lru_cache

import tahta_ajan

from . import adresler, ayar

SABIT_ZAMAN = 1767225600  # 01.01.2026 00:00 UTC
PAKET_ADI = "tahta-ajan"


@dataclass(frozen=True)
class Paket:
    surum: str
    icerik: bytes
    sha256: str
    dosya_adi: str


def _lf(veri: bytes) -> bytes:
    return veri.replace(b"\r\n", b"\n")


def _tar_gz(girdiler: list[tuple[str, int, bytes | None]]) -> bytes:
    """girdiler: (ad, kip, içerik); içerik None ise dizindir."""
    ham = io.BytesIO()
    with tarfile.open(fileobj=ham, mode="w", format=tarfile.GNU_FORMAT) as arsiv:
        for ad, kip, icerik in girdiler:
            bilgi = tarfile.TarInfo(name=ad)
            bilgi.mode = kip
            bilgi.uid = bilgi.gid = 0
            bilgi.uname = bilgi.gname = "root"
            # Zaman içerikten türetilir: Python derlenmiş önbelleği (pyc) dosya
            # zamanı ve boyutuyla doğrular; sabit zaman, güncellenen dosyanın
            # eski önbellekle çalışmasına yol açıyordu.
            bilgi.mtime = SABIT_ZAMAN + (zlib.crc32(icerik) % 31_536_000 if icerik else 0)
            if icerik is None:
                bilgi.type = tarfile.DIRTYPE
                arsiv.addfile(bilgi)
            else:
                bilgi.size = len(icerik)
                arsiv.addfile(bilgi, io.BytesIO(icerik))
    cikti = io.BytesIO()
    with gzip.GzipFile(fileobj=cikti, mode="wb", mtime=SABIT_ZAMAN) as sikistirici:
        sikistirici.write(ham.getvalue())
    return cikti.getvalue()


def _ar_uyesi(ad: str, veri: bytes) -> bytes:
    baslik = f"{ad:<16}{SABIT_ZAMAN:<12}{0:<6}{0:<6}{'100644':<8}{len(veri):<10}`\n".encode("ascii")
    return baslik + veri + (b"\n" if len(veri) % 2 else b"")


def _sablon(ad: str) -> bytes:
    return _lf((ayar.SUNUCU_DIZINI / "ajan_paket" / ad).read_bytes())


@lru_cache(maxsize=1)
def ajan_paketi() -> Paket:
    surum = tahta_ajan.__version__
    veri: list[tuple[str, int, bytes | None]] = [
        ("./", 0o755, None),
        ("./opt/", 0o755, None),
        ("./opt/tahta-kontrol/", 0o755, None),
        ("./opt/tahta-kontrol/tahta_ajan/", 0o755, None),
    ]
    boyut = 0
    for dosya in sorted(ayar.AJAN_DIZINI.glob("*.py")):
        icerik = _lf(dosya.read_bytes())
        boyut += len(icerik)
        veri.append((f"./opt/tahta-kontrol/tahta_ajan/{dosya.name}", 0o644, icerik))
    veri += [
        ("./usr/", 0o755, None),
        ("./usr/bin/", 0o755, None),
        ("./usr/bin/tahta-ajan", 0o755, _sablon("tahta-ajan")),
        ("./lib/", 0o755, None),
        ("./lib/systemd/", 0o755, None),
        ("./lib/systemd/system/", 0o755, None),
        ("./lib/systemd/system/tahta-ajan.service", 0o644, _sablon("tahta-ajan.service")),
        ("./etc/", 0o755, None),
        ("./etc/xdg/", 0o755, None),
        ("./etc/xdg/autostart/", 0o755, None),
        ("./etc/xdg/autostart/tahta-ekran.desktop", 0o644, _sablon("tahta-ekran.desktop")),
        # Ders yoklaması kısayolu (A5): menüde "Yoklama Al" → tahta-ajan yoklama.
        ("./usr/share/", 0o755, None),
        ("./usr/share/applications/", 0o755, None),
        ("./usr/share/applications/tahta-yoklama.desktop", 0o644, _sablon("tahta-yoklama.desktop")),
        # Arıza bildirimi kısayolu (A6): menüde "Arıza bildir" → tahta-ajan ariza.
        ("./usr/share/applications/tahta-ariza.desktop", 0o644, _sablon("tahta-ariza.desktop")),
    ]
    kontrol_metni = (
        _sablon("control").decode("utf-8").replace("@SURUM@", surum).replace("@BOYUT@", str(max(1, boyut // 1024)))
    )
    kontrol = [
        ("./", 0o755, None),
        ("./control", 0o644, kontrol_metni.encode("utf-8")),
        ("./postinst", 0o755, _sablon("postinst")),
        ("./prerm", 0o755, _sablon("prerm")),
    ]
    icerik = (
        b"!<arch>\n"
        + _ar_uyesi("debian-binary", b"2.0\n")
        + _ar_uyesi("control.tar.gz", _tar_gz(kontrol))
        + _ar_uyesi("data.tar.gz", _tar_gz(veri))
    )
    return Paket(surum, icerik, hashlib.sha256(icerik).hexdigest(), f"{PAKET_ADI}_{surum}_all.deb")


def kurulum_betigi(sunucu: str, parmak_izi: str, sunucular: list[str] | None = None) -> bytes:
    """Kurulum betiği. `sunucular` (A6 adres listesi; doğrulanmış https adresleri) ajan.json'a
    `sunucular` olarak yazılır; birincil adres `sunucu`'dur ve listenin başına konur."""
    # Betik root yetkisiyle çalışır: adresler çift tırnak içine yazıldığı için kabuk
    # metakarakteri taşıyan hiçbir değer betiğe girmez (birincil geçersizse üretim durur).
    if not adresler.betige_yazilabilir_mi(sunucu):
        raise ValueError("Kurulum betiği için sunucu adresi geçersiz.")
    if not all(c in "0123456789abcdefABCDEF:" for c in parmak_izi):
        raise ValueError("Kurulum betiği için parmak izi geçersiz.")
    sunucular = [a for a in (sunucular or []) if adresler.betige_yazilabilir_mi(a)] if sunucular else sunucular
    paket = ajan_paketi()
    liste = [sunucu] + [a for a in (sunucular or []) if a != sunucu]
    metin = (
        _sablon("kur.sh")
        .decode("utf-8")
        .replace("@SUNUCULAR@", " ".join(liste) if sunucular else "")
        .replace("@SUNUCU@", sunucu)
        .replace("@PARMAK_IZI@", parmak_izi)
        .replace("@PAKET_SHA256@", paket.sha256)
        .replace("@SURUM@", paket.surum)
    )
    return metin.encode("utf-8")


def usb_paketi(sunucu: str, parmak_izi: str, sunucular: list[str] | None = None) -> bytes:
    """Ağdan indiremeyen tahta için: betik + paket tek zip içinde."""
    cikti = io.BytesIO()
    with zipfile.ZipFile(cikti, "w", zipfile.ZIP_DEFLATED) as arsiv:
        arsiv.writestr("tahta-kur.sh", kurulum_betigi(sunucu, parmak_izi, sunucular))
        arsiv.writestr("tahta-ajan.deb", ajan_paketi().icerik)
        arsiv.writestr(
            "OKUYUNUZ.txt",
            "Bu klasoru tahtaya kopyalayin, ucbirimi bu klasorde acin ve su komutu calistirin:\n\n"
            "    sudo bash tahta-kur.sh ESLESTIRME_KODU\n\n"
            "Eslestirme kodu panelin 'Tahta ekle' sayfasinda yazar.\n",
        )
    return cikti.getvalue()
