"""Tahtada görünen öğrenci bilgisinin TEK maskeleme tanımı (ortak sözlük §6 M1).

Maske yalnız sunucuda üretilir. Kalabalık listesi (A4 salon giriş ekranı, şube sınav
duyurusu, gözetmen yoklama ızgarası): `kalabalik(ad_soyad)` + `no_son(okul_no)`.
Bir öğrencinin adı ve numarası tahtada hiçbir zaman ikisi birden açık görünmez (M2).
Aşama 5 bu modüle `sinif_etiketi` ekler.
"""

from __future__ import annotations

KALABALIK_EN_UZUN = 60


def kalabalik(ad_soyad: str) -> str:
    """"Ahmet Yılmaz" → "Ah*** Yı****"; ≤ 2 harfli sözcük → ilk harf + "*". Büyük/küçük harf korunur."""
    parcalar = str(ad_soyad or "").split()
    return " ".join(p[0] + "*" if len(p) <= 2 else p[:2] + "*" * (len(p) - 2) for p in parcalar)[:KALABALIK_EN_UZUN]


def no_son(okul_no: str) -> str:
    """Okul numarasının son 2 rakamı ("1047" → "47"); rakam yoksa metnin son 2 karakteri."""
    metin = str(okul_no or "")
    rakam = "".join(c for c in metin if c.isdigit()) or metin
    return rakam[-2:]
