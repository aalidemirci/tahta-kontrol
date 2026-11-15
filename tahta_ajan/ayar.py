"""Ajanın yapılandırma ve durum dosyaları.

ajan.json sunucu adresini, sunucu sertifikasının parmak izini ve tahtanın
kimliğini taşır; yalnız yönetici (root) okuyabilir.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

YEREL_PORT = int(os.environ.get("TAHTA_AJAN_YEREL_PORT", "47811"))
# Sunucuyla bu kadar saniye konuşulamazsa tahta "çevrimdışı" sayılır ve kilit
# kodsuz açılabilir: sunucu arızası dersi rehin almaz.
CEVRIMDISI_SN = int(os.environ.get("TAHTA_AJAN_CEVRIMDISI_SN", "90"))


def _windows() -> bool:
    return sys.platform.startswith("win")


def ayar_dizini() -> Path:
    ortam = os.environ.get("TAHTA_AJAN_DIZIN")
    if ortam:
        return Path(ortam)
    if _windows():
        return Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "tahta-kontrol"
    return Path("/etc/tahta-kontrol")


def durum_dizini() -> Path:
    ortam = os.environ.get("TAHTA_AJAN_DURUM")
    if ortam:
        return Path(ortam)
    if _windows():
        return ayar_dizini() / "durum"
    return Path("/var/lib/tahta-kontrol")


def ayar_yolu() -> Path:
    return ayar_dizini() / "ajan.json"


def _json_oku(yol: Path) -> dict:
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return veri if isinstance(veri, dict) else {}


def _json_yaz(yol: Path, veri: dict, gizli: bool) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".yeni")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    if gizli and not _windows():
        os.chmod(gecici, 0o600)
    os.replace(gecici, yol)


def oku() -> dict:
    return _json_oku(ayar_yolu())


def yaz(veri: dict) -> None:
    _json_yaz(ayar_yolu(), veri, gizli=True)


def durum_oku() -> dict:
    return _json_oku(durum_dizini() / "durum.json")


def durum_yaz(veri: dict) -> None:
    _json_yaz(durum_dizini() / "durum.json", veri, gizli=True)


# ---- okul kimliği: tahta paleti ve logo -------------------------------------------
# Tonlar tahtada hesaplanmaz; sunucu (tahta_sunucu/tema.py) üretir ve hex olarak indirir.
# Bu palet, varsayılan temanın (lacivert + kehribar) tahta paletinin aynısıdır (test eder);
# eski sunucuya bağlı ya da henüz sunucuya ulaşmamış tahta bununla çizilir.
PALET_ANAHTARLARI = (
    "zemin", "yuzey", "serit", "metin", "soluk", "dugme", "dugme_kenar", "ana", "ana_metin", "vurgu", "bilgi",
)  # fmt: skip
VARSAYILAN_PALET = {
    "zemin": "#021020",
    "yuzey": "#08192a",
    "serit": "#00203e",
    "metin": "#f8fafc",
    "soluk": "#b4bfca",
    "dugme": "#25323f",
    "dugme_kenar": "#526170",
    "ana": "#36628e",
    "ana_metin": "#ffffff",
    "vurgu": "#e58044",
    "bilgi": "#ffc752",
}
_HEX = re.compile(r"#[0-9a-f]{6}")

LOGO_SINIRI = 256 * 1024


def palet_dogrula(palet) -> dict | None:
    """Sunucudan gelen paleti doğrular: bilinen anahtarlar, her biri #rrggbb (küçük harf).

    Eksik ya da geçersiz anahtar varsayılan paletin değeriyle doldurulur; sözlük değilse None.
    Doğrulanmamış hiçbir değer GTK stiline yazılmaz.
    """
    if not isinstance(palet, dict):
        return None
    sonuc = {}
    for ad in PALET_ANAHTARLARI:
        deger = palet.get(ad)
        sonuc[ad] = deger if isinstance(deger, str) and _HEX.fullmatch(deger) else VARSAYILAN_PALET[ad]
    return sonuc


def logo_gecerli(veri) -> bool:
    """Logo yalnız PNG ya da JPEG olabilir (sihirli baytlarla), en çok LOGO_SINIRI bayt."""
    if not isinstance(veri, (bytes, bytearray)) or not veri or len(veri) > LOGO_SINIRI:
        return False
    png = veri[:8] == b"\x89PNG\r\n\x1a\n" and veri[12:16] == b"IHDR"
    return png or veri[:3] == b"\xff\xd8\xff"


def logo_yolu() -> Path:
    """Logo yalnız servisin okuyabildiği yerde durur; ekran yardımcısına soketle gider."""
    return durum_dizini() / "logo"


def logo_oku() -> bytes | None:
    try:
        return logo_yolu().read_bytes()
    except OSError:
        return None


def logo_yaz(veri: bytes) -> None:
    yol = logo_yolu()
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name("logo.yeni")
    gecici.write_bytes(veri)
    if not _windows():
        os.chmod(gecici, 0o600)
    os.replace(gecici, yol)


def logo_sil() -> None:
    try:
        logo_yolu().unlink()
    except OSError:
        pass
