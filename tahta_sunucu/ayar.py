"""Sunucunun yolları ve bağlantı noktaları."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Panel bu bilgisayardan şifresiz HTTP ile (yalnız 127.0.0.1), okul ağından
# HTTPS ile açılır. Tahtalar yalnız HTTPS kapısını kullanır.
HTTP_MAKINE = os.environ.get("TAHTA_HTTP_MAKINE", "127.0.0.1")
HTTP_PORT = int(os.environ.get("TAHTA_HTTP_PORT", "8787"))
HTTPS_MAKINE = os.environ.get("TAHTA_HTTPS_MAKINE", "0.0.0.0")
HTTPS_PORT = int(os.environ.get("TAHTA_HTTPS_PORT", "8788"))

CEVRIMICI_ESIK_SN = 70  # ajan en geç 25 saniyede bir yeniden bağlanır
OTURUM_SAAT = 12
KAYIT_PENCERESI_DK = 60
# Windows hizmeti olarak mı çalışıyor (giriş noktası hizmet kipinde TAHTA_HIZMET=1 yapar).
HIZMET = os.environ.get("TAHTA_HIZMET") == "1"
HIZMET_ADI = "TahtaKontrol"

PAKET_KOKU = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
SUNUCU_DIZINI = PAKET_KOKU / "tahta_sunucu"
AJAN_DIZINI = PAKET_KOKU / "tahta_ajan"


def paketli_windows() -> bool:
    """Kurucuyla kurulmuş (PyInstaller) Windows programı mı?"""
    return sys.platform.startswith("win") and bool(getattr(sys, "frozen", False))


def eski_veri_dizini() -> Path:
    """0.1.x–0.8 öncesi kurulumların (oturum programı) veri dizini: o kullanıcının %LOCALAPPDATA%'sı."""
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TahtaKontrol"


def hizmet_veri_dizini() -> Path:
    """Kurulu programın (Windows hizmeti) veri dizini: %PROGRAMDATA%/TahtaKontrol."""
    return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "TahtaKontrol"


def veri_dizini_sec() -> Path:
    """Veri dizini kuralı (dizin oluşturmaz).

    1. TAHTA_VERI_DIZINI her şeyi ezer (deneme, duman testi).
    2. Paketli Windows programı → %PROGRAMDATA%/TahtaKontrol (hizmet hesabının yazdığı yer).
    3. Windows'ta geliştirme (uv run) → %LOCALAPPDATA%/TahtaKontrol (eskisi gibi).
    4. Diğer → XDG yolu.
    """
    ortam = os.environ.get("TAHTA_VERI_DIZINI")
    if ortam:
        return Path(ortam)
    if paketli_windows():
        return hizmet_veri_dizini()
    if sys.platform.startswith("win"):
        return eski_veri_dizini()
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "tahta-kontrol"


def veri_dizini() -> Path:
    yol = veri_dizini_sec()
    yol.mkdir(parents=True, exist_ok=True)
    return yol
