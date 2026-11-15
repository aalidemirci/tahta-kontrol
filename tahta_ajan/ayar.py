"""Ajanın yapılandırma ve durum dosyaları.

ajan.json sunucu adresini, sunucu sertifikasının parmak izini ve tahtanın
kimliğini taşır; yalnız yönetici (root) okuyabilir.
"""

from __future__ import annotations

import json
import os
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
