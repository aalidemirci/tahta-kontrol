"""Tahta envanteri (A6, ajan yanı): donanım ve yazılım özetini §5.4 biçiminde kurar.

İşletim sistemine dokunan okumalar `sistem.donanim_bilgisi()`'ndedir; burada yalnız alanlar
seçilir, yer tutucu seri numaraları boşaltılır ve özet hesaplanır. Envanter CİHAZ verisidir:
kullanıcı/hesap adı, ev dizini, dosya adı, makine adı ve açık kalma süresi GİRMEZ (kural 6).
Oynak değer girmediği için özet yalnız donanım ya da yazılım değişince değişir.
"""

from __future__ import annotations

import hashlib
import json

from . import __version__

BICIM = 1
# Üreticilerin doldurmadığı seri numarası alanlarında görülen yer tutucular (büyük-küçük harf duyarsız).
YER_TUTUCULAR = {
    "to be filled by o.e.m.", "default string", "system serial number", "none", "0",
    "not specified", "not applicable", "n/a", "unknown",
}  # fmt: skip


def seri_temizle(deger) -> str:
    """Yer tutucuyu ve yalnız 0/boşluk/nokta içeren değeri boş sayar (sunucudaki kuralın aynısı)."""
    s = " ".join(str(deger or "").split())[:80]
    if not s or s.lower() in YER_TUTUCULAR or not s.strip("0 .").strip():
        return ""
    return s


def _birlestir(*parcalar) -> str:
    return " ".join(p for p in (" ".join(str(x or "").split()) for x in parcalar) if p)[:120]


def topla(ham: dict, ekran: str = "") -> dict:
    """Ham okumalardan (sistem.donanim_bilgisi) gönderilecek envanteri kurar.

    `ekran`: bağlı ekran yardımcısının bildirdiği çözünürlük ("1920x1080"); yardımcı yoksa boş.
    Linux dışında yalnız bicim, isletim_sistemi ve ajan_surumu (ve python) bulunur.
    """
    ham = ham if isinstance(ham, dict) else {}
    env: dict = {"bicim": BICIM}
    if ham.get("linux_disi"):
        env.update(isletim_sistemi=str(ham.get("isletim_sistemi") or ""), ajan_surumu=__version__)
        return env
    bios_tarih = str(ham.get("bios_date") or "")
    bios = _birlestir(ham.get("bios_vendor"), ham.get("bios_version"))
    if bios and bios_tarih:
        bios = f"{bios} ({bios_tarih})"
    env.update(
        uretici=_birlestir(ham.get("sys_vendor")),
        model=_birlestir(ham.get("product_name")),
        model_surumu=_birlestir(ham.get("product_version"))[:40],
        urun_seri=seri_temizle(ham.get("product_serial")),
        anakart=_birlestir(ham.get("board_vendor"), ham.get("board_name")),
        anakart_seri=seri_temizle(ham.get("board_serial")),
        bios=bios[:120],
        islemci=_birlestir(ham.get("islemci")),
        cekirdek_sayisi=int(ham.get("cekirdek_sayisi") or 0),
        bellek_mb=int(ham.get("bellek_mb") or 0),
        diskler=[d for d in (ham.get("diskler") or []) if isinstance(d, dict)][:8],
        ekran=str(ekran or "")[:20],
        dokunmatik=[str(d)[:80] for d in (ham.get("dokunmatik") or [])][:10],
        ag=[a for a in (ham.get("ag") or []) if isinstance(a, dict)][:8],
        isletim_sistemi=_birlestir(ham.get("isletim_sistemi")),
        cekirdek=_birlestir(ham.get("cekirdek"))[:60],
        etap_paketleri=[str(p)[:80] for p in (ham.get("etap_paketleri") or [])][:30],
        python=str(ham.get("python") or "")[:20],
        ajan_surumu=__version__,
    )
    return env


def ozet(env: dict) -> str:
    """`durum.envanter_ozet`: sha256(json.dumps(env, sort_keys=True, ensure_ascii=False))'in ilk 16 hanesi."""
    return hashlib.sha256(json.dumps(env, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def ekran_cozunurlugu(ekranlar: list[dict]) -> str:
    """Bağlı ekran yardımcılarından ilk çözünürlük ("GxY"); yoksa boş."""
    for e in ekranlar or []:
        g, y = e.get("genislik"), e.get("yukseklik")
        if isinstance(g, int) and isinstance(y, int) and g > 0 and y > 0 and not isinstance(g, bool):
            return f"{g}x{y}"
    return ""
