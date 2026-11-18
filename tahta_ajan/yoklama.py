"""Ders yoklamasının servis ile ekran yardımcısı arasında ORTAK saf kuralları (0.14.0); yalnız standart kitaplık.

Etiket (maske, kısaltma, sıra) sunucuda üretilir; burada yalnız dokunuş döngüsü ve ızgara yerleşimi vardır.
Tablolar `tests/yoklama_sozlesme.json` ile ve sunucudaki `maske.yoklama_yerlesim` ile testte eşlenir.
"""

from __future__ import annotations

DURUMLAR = ("var", "yok", "gec")
SAYFA_BOYU = 56  # bir sayfadaki en çok öğrenci (7 x 8)


def sonraki_durum(durum: str, gec_secilebilir: bool) -> str:
    """Öğrenci düğmesine dokunuş: var → yok → (yalnız devrenin ilk dersinde) geç → var."""
    if durum == "var":
        return "yok"
    if durum == "yok" and gec_secilebilir:
        return "gec"
    return "var"


def yerlesim(n: int) -> tuple[int, int]:
    """Bir sayfadaki ızgara (sütun, satır): 42'ye kadar 6x7, 48'e kadar 6x8, fazlası 7x8 (56'lık sayfalar)."""
    if n <= 42:
        return 6, 7
    if n <= 48:
        return 6, 8
    return 7, 8


def sayfa_sayisi(n: int) -> int:
    return max(1, -(-max(0, n) // SAYFA_BOYU))


def sayfa_dilimi(n: int, sayfa: int) -> tuple[int, int]:
    """`sayfa` numaralı (0'dan) sayfanın [baş, son) sıra aralığı."""
    sayfa = max(0, min(sayfa_sayisi(n) - 1, sayfa))
    return sayfa * SAYFA_BOYU, min(n, (sayfa + 1) * SAYFA_BOYU)
