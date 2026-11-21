"""Bildirim alanı (durum simgesi) için üç küçük .ico üretir; yalnız standart kitaplık (Pillow yok).

    uv run python scripts/durum_simgeleri.py            # packaging/windows/durum-*.ico yazar
    uv run python scripts/durum_simgeleri.py --hedef D  # başka klasöre yazar (test)

Çizim ürün işaretinin (tahta_sunucu/statik/isaret.svg) sade biçimidir: koyu zemin, beyaz tahta ve onay
işareti; sağ alt köşede durum noktası (yeşil: çalışıyor, gri: bekleniyor/bilinmiyor, kırmızı: durdu).
Altın çubuk küçük boyda okunmadığı için çizilmez. Her dosyada 16, 24 ve 32 px'lik 32 bit (BGRA) görüntü
vardır. Çıktı belirlenimcidir: aynı betik aynı baytları üretir (test, depodaki dosyalarla karşılaştırır).
Var olan packaging/windows/tahta-kontrol.ico'ya dokunmaz.
"""

from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
HEDEF = KOK / "packaging" / "windows"
BOYUTLAR = (16, 24, 32)
ORNEK = 4  # piksel başına 4x4 alt örnek (kenar yumuşatma)

ZEMIN = (0x16, 0x4E, 0x57)
TAHTA = (0xFF, 0xFF, 0xFF)
NOKTA = {
    "calisiyor": (0x16, 0xA3, 0x4A),
    "bekleniyor": (0x9C, 0xA3, 0xAF),
    "durdu": (0xDC, 0x26, 0x26),
}
DOSYA = {tur: f"durum-{tur}.ico" for tur in NOKTA}

# 64 birimlik çizim alanı (isaret.svg ile aynı ölçek)
NOKTA_MERKEZ = (48.0, 48.0)
NOKTA_YARICAP = 14.0
OYUK_YARICAP = 18.0  # noktanın çevresindeki saydam halka
ONAY = ((22.0, 26.0), (29.0, 33.0), (43.0, 19.0))
ONAY_KALINLIK = 3.75


def _yuvarlak_dikdortgen(x: float, y: float, x0: float, y0: float, x1: float, y1: float, r: float) -> bool:
    if not (x0 <= x <= x1 and y0 <= y <= y1):
        return False
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _dogru_uzakligi(px: float, py: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def renk(x: float, y: float, tur: str) -> tuple[int, int, int, int]:
    """64 birimlik alanda bir noktanın rengi (r, g, b, a); a 0 ya da 255."""
    uzaklik = math.hypot(x - NOKTA_MERKEZ[0], y - NOKTA_MERKEZ[1])
    if uzaklik <= NOKTA_YARICAP:
        return (*NOKTA[tur], 255)
    if uzaklik <= OYUK_YARICAP:
        return (0, 0, 0, 0)
    if not _yuvarlak_dikdortgen(x, y, 0, 0, 64, 64, 14):
        return (0, 0, 0, 0)
    if _yuvarlak_dikdortgen(x, y, 8, 12, 56, 40, 6):
        if min(_dogru_uzakligi(x, y, ONAY[i], ONAY[i + 1]) for i in range(len(ONAY) - 1)) <= ONAY_KALINLIK:
            return (*ZEMIN, 255)
        return (*TAHTA, 255)
    return (*ZEMIN, 255)


def goruntu(boyut: int, tur: str) -> list[list[tuple[int, int, int, int]]]:
    """Yukarıdan aşağı satırlar; her piksel (r, g, b, a), saydamlık kenarda yumuşatılmış."""
    olcek = 64.0 / boyut
    satirlar = []
    for py in range(boyut):
        satir = []
        for px in range(boyut):
            r = g = b = a = 0
            for sy in range(ORNEK):
                for sx in range(ORNEK):
                    x = (px + (sx + 0.5) / ORNEK) * olcek
                    y = (py + (sy + 0.5) / ORNEK) * olcek
                    cr, cg, cb, ca = renk(x, y, tur)
                    r += cr * ca
                    g += cg * ca
                    b += cb * ca
                    a += ca
            if a == 0:
                satir.append((0, 0, 0, 0))
            else:
                satir.append((round(r / a), round(g / a), round(b / a), round(a / (ORNEK * ORNEK))))
        satirlar.append(satir)
    return satirlar


def _dib(boyut: int, satirlar: list[list[tuple[int, int, int, int]]]) -> bytes:
    """ICO içindeki 32 bit DIB: BITMAPINFOHEADER (yükseklik iki kat), BGRA satırları alttan üste, AND maskesi."""
    renkler = bytearray()
    maske = bytearray()
    maske_satir = ((boyut + 31) // 32) * 4
    for satir in reversed(satirlar):
        bitler = bytearray(maske_satir)
        for i, (r, g, b, a) in enumerate(satir):
            renkler += bytes((b, g, r, a))
            if a == 0:
                bitler[i // 8] |= 0x80 >> (i % 8)
        maske += bitler
    baslik = struct.pack("<IiiHHIIiiII", 40, boyut, boyut * 2, 1, 32, 0, len(renkler) + len(maske), 0, 0, 0, 0)
    return baslik + bytes(renkler) + bytes(maske)


def ico(tur: str, boyutlar: tuple[int, ...] = BOYUTLAR) -> bytes:
    govdeler = [_dib(boyut, goruntu(boyut, tur)) for boyut in boyutlar]
    bas = struct.pack("<HHH", 0, 1, len(boyutlar))
    konum = 6 + 16 * len(boyutlar)
    dizin = b""
    for boyut, govde in zip(boyutlar, govdeler, strict=True):
        dizin += struct.pack("<BBBBHHII", boyut % 256, boyut % 256, 0, 0, 1, 32, len(govde), konum)
        konum += len(govde)
    return bas + dizin + b"".join(govdeler)


def yaz(hedef: Path = HEDEF) -> list[Path]:
    hedef.mkdir(parents=True, exist_ok=True)
    yazilan = []
    for tur, ad in DOSYA.items():
        yol = hedef / ad
        yol.write_bytes(ico(tur))
        yazilan.append(yol)
    return yazilan


def main() -> int:
    ayristirici = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayristirici.add_argument("--hedef", type=Path, default=HEDEF)
    ab = ayristirici.parse_args()
    for yol in yaz(ab.hedef):
        print(f"{yol} ({yol.stat().st_size} bayt)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
