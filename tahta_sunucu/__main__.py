"""Tahta Kontrol sunucusu.

  python -m tahta_sunucu            Sunucuyu uçbirimde çalıştırır.
  python -m tahta_sunucu pencere    Durum penceresi: hizmet varsa durumunu gösterir; geliştirmede sunucuyu
                                    pencere içinde çalıştırır.
  python -m tahta_sunucu paket YOL  Ajan paketini (.deb) dosyaya yazar.
  python -m tahta_sunucu hizmet     Windows hizmeti olarak çalışır (yalnız Hizmet Denetim Yöneticisi başlatır).
  python -m tahta_sunucu hizmet --konsol
                                    Hizmet kipini uçbirimde dener (Ctrl+C ile durur).
  python -m tahta_sunucu tasi --hedef DIZIN [--tercih DIZIN] [--kaynak DIZIN]
                                    Eski veri dizinini hizmetin veri dizinine kopyalar (kurucu çağırır,
                                    yönetici yetkisi gerekir). Çıkış kodu: 0 taşındı, 10 eski veri yok,
                                    11 hedefte veri var, 20 belirsiz, 21 hata.
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
    if komut == "hizmet":
        from . import hizmet

        if argv[1:] == ["--konsol"]:
            return hizmet.konsol()
        return hizmet.calistir()
    if komut == "tasi":
        return _tasi(argv[1:])
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


def _tasi(argv: list[str]) -> int:
    import argparse
    from pathlib import Path

    from . import tasima

    ayristirici = argparse.ArgumentParser(prog="tahta_sunucu tasi")
    ayristirici.add_argument("--hedef", required=True)
    ayristirici.add_argument("--tercih")
    ayristirici.add_argument("--kaynak")
    ab = ayristirici.parse_args(argv)
    sonuc = tasima.calistir(
        Path(ab.hedef),
        tercih=Path(ab.tercih) if ab.tercih else None,
        kaynak=Path(ab.kaynak) if ab.kaynak else None,
    )
    print(sonuc.ileti)
    return sonuc.kod


if __name__ == "__main__":
    raise SystemExit(main())
