"""Tahta Kontrol sunucusu.

  python -m tahta_sunucu            Sunucuyu uçbirimde çalıştırır.
  python -m tahta_sunucu pencere    Küçük denetim penceresiyle çalıştırır (kurulu programın yaptığı).
  python -m tahta_sunucu paket YOL  Ajan paketini (.deb) dosyaya yazar.
"""

from __future__ import annotations

import logging
import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    komut = argv[0] if argv else ""
    if komut in ("-h", "--help", "yardim"):
        print(__doc__)
        return 0
    if komut == "paket" and len(argv) == 2:
        from . import paket

        p = paket.ajan_paketi()
        with open(argv[1], "wb") as dosya:
            dosya.write(p.icerik)
        print(f"{p.dosya_adi} ({len(p.icerik)} bayt, sha256 {p.sha256})")
        return 0
    if komut == "pencere":
        from . import pencere

        return pencere.calistir()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from .sunucu import Sunucu

    try:
        sunucu = Sunucu()
        sunucu.baslat()
    except RuntimeError as hata:
        print(f"Başlatılamadı: {hata}", file=sys.stderr)
        return 1
    sunucu.bekle()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
