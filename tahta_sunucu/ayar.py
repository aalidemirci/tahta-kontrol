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
# Windows hizmeti olarak mı çalışıyor (6B'de hizmet ayarlar; 6A'da her zaman False).
HIZMET = os.environ.get("TAHTA_HIZMET") == "1"

PAKET_KOKU = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
SUNUCU_DIZINI = PAKET_KOKU / "tahta_sunucu"
AJAN_DIZINI = PAKET_KOKU / "tahta_ajan"


def veri_dizini() -> Path:
    ortam = os.environ.get("TAHTA_VERI_DIZINI")
    if ortam:
        yol = Path(ortam)
    elif sys.platform.startswith("win"):
        yol = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TahtaKontrol"
    else:
        yol = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "tahta-kontrol"
    yol.mkdir(parents=True, exist_ok=True)
    return yol
