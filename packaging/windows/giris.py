"""Paketlenmiş programın giriş noktası.

Bağımsız değişken verilmezse denetim penceresiyle açılır (kısayolların yaptığı);
"sunucu" verilirse penceresiz çalışır (derleme duman testi ve ileride servis için).
"""

import os
import sys

if sys.stdout is None:  # pencereli derlemede uçbirim yoktur
    sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115

from tahta_sunucu.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["pencere"]))
