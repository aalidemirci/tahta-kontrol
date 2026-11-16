"""Komut satırı: tahta-ajan servis | ekran | kaydol KOD | tani | durum | yoklama"""

from __future__ import annotations

import json
import socket
import sys
from urllib.parse import urlsplit

from . import __version__, ayar, sistem
from .baglanti import BaglantiHatasi, Istemci

KULLANIM = """Tahta Kontrol ajanı {surum}

  tahta-ajan servis        Ajan servisini çalıştırır (systemd bunu kullanır).
  tahta-ajan ekran         Kilit/duyuru ekranı yardımcısını çalıştırır (oturumda kendiliğinden başlar).
  tahta-ajan kaydol KOD    Tahtayı sunucuya kaydeder (kurulum betiği çağırır).
  tahta-ajan tani          Saha tanılamasını çalıştırıp ekrana yazar (sunucu gerekmez).
  tahta-ajan durum         Yapılandırmayı ve sunucu erişimini gösterir.
  tahta-ajan yoklama       Ders yoklaması ekranını açar ("Yoklama Al" kısayolu bunu çağırır).
"""


def kaydol(kod: str) -> int:
    yapi = ayar.oku()
    if not yapi.get("sunucu"):
        print("Sunucu adresi tanımlı değil; kurulum betiğini çalıştırın.", file=sys.stderr)
        return 2
    if yapi.get("tahta_id"):
        istemci = Istemci(yapi["sunucu"], yapi.get("parmak_izi", ""), yapi["tahta_id"], yapi.get("anahtar", ""))
        try:
            durum, _, _ = istemci.istek("POST", "/ajan/bekle", {"surum": __version__, "bekle": 0, "komut_al": False})
            if durum == 200:
                print("Bu tahta zaten kayıtlı; kayıt korunuyor.")
                return 0
        except BaglantiHatasi:
            pass
    istemci = Istemci(yapi["sunucu"], yapi.get("parmak_izi", ""))
    parca = urlsplit(yapi["sunucu"])
    ag = sistem.ag_bilgisi(parca.hostname or "", parca.port or 443)
    try:
        durum, yanit, _ = istemci.istek(
            "POST",
            "/ajan/kaydol",
            {
                "kod": kod.strip(),
                "makine_adi": socket.gethostname(),
                "mac": ag.get("mac", ""),
                "platform": sistem.platform_adi(),
                "surum": __version__,
            },
        )
    except BaglantiHatasi as hata:
        print(f"Sunucuya ulaşılamadı: {hata}", file=sys.stderr)
        return 3
    if durum != 200 or "tahta_id" not in yanit:
        print(f"Kayıt reddedildi: {yanit.get('hata', durum)}", file=sys.stderr)
        return 4
    yapi["tahta_id"] = yanit["tahta_id"]
    yapi["anahtar"] = yanit["anahtar"]
    ayar.yaz(yapi)
    print(f"Tahta kaydedildi (no {yanit['tahta_id']}). Okul idaresi panelden onaylayınca kullanılabilir.")
    return 0


def durum() -> int:
    yapi = ayar.oku()
    print(f"Ajan sürümü : {__version__}")
    print(f"Sunucu      : {yapi.get('sunucu') or '(tanımlı değil)'}")
    print(f"Tahta no    : {yapi.get('tahta_id') or '(kayıtlı değil)'}")
    if not yapi.get("sunucu"):
        return 1
    istemci = Istemci(yapi["sunucu"], yapi.get("parmak_izi", ""))
    try:
        kod, yanit, _ = istemci.istek("GET", "/saglik", zaman_asimi=6)
        print(f"Sunucu erişimi: HTTP {kod} {yanit}")
    except BaglantiHatasi as hata:
        print(f"Sunucu erişimi: BAŞARISIZ ({hata})")
        return 1
    return 0


def yoklama() -> int:
    """Servise yerel soketle "yoklama aç" der ve hemen kapanır (A5).

    İlk ileti `arayuz: komut` ile kendini tanıtır: servis bu bağlantıya durum yayını (ekrandaki
    liste dahil) göndermez ve onu ekran yardımcısı saymaz. Ekran yardımcı penceresinde açılır.
    """
    try:
        with socket.create_connection(("127.0.0.1", ayar.YEREL_PORT), timeout=5) as soket:
            for mesaj in ({"tur": "merhaba", "arayuz": "komut", "surum": __version__}, {"tur": "yoklama_ac"}):
                soket.sendall((json.dumps(mesaj) + "\n").encode("utf-8"))
    except OSError as hata:
        print(f"Tahta Kontrol servisine ulaşılamadı: {hata}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    komut = argv[0] if argv else ""
    if komut == "servis":
        from . import servis

        return servis.calistir()
    if komut == "ekran":
        from . import ekran

        return ekran.calistir()
    if komut == "kaydol" and len(argv) == 2:
        return kaydol(argv[1])
    if komut == "tani":
        from . import tani

        yapi = ayar.oku()
        parca = urlsplit(yapi.get("sunucu", ""))
        rapor = tani.topla(parca.hostname or "", parca.port or 443)
        if "--json" in argv:
            print(json.dumps(rapor, ensure_ascii=False, indent=1))
        else:
            for d in rapor["denetimler"]:
                print(f"[{d['sonuc'].upper():6}] {d['ad']}: {d['ayrinti']}")
        return 0
    if komut == "durum":
        return durum()
    if komut == "yoklama":
        return yoklama()
    if komut in ("--surum", "--version"):
        print(__version__)
        return 0
    print(KULLANIM.format(surum=__version__))
    return 0 if komut in ("", "-h", "--help", "yardim") else 64


if __name__ == "__main__":
    raise SystemExit(main())
