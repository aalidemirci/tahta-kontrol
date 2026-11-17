"""Ekrana giden günlük programın izinli alanları; yalnız standart kitaplık."""

from __future__ import annotations

import re
from datetime import date

SAAT = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def coz(deger) -> dict | None:
    if not isinstance(deger, dict):
        return None
    try:
        tarih = date.fromisoformat(str(deger.get("tarih", ""))).isoformat()
    except ValueError:
        return None
    dersler = []
    for d in (deger.get("dersler") if isinstance(deger.get("dersler"), list) else [])[:24]:
        if not isinstance(d, dict):
            continue
        no = d.get("ders_no")
        if isinstance(no, bool) or not isinstance(no, int) or not 1 <= no <= 20:
            continue
        bas, bit = d.get("baslangic"), d.get("bitis")
        if not isinstance(bas, str) or not isinstance(bit, str) or not SAAT.fullmatch(bas) or not SAAT.fullmatch(bit) or bit <= bas:
            continue
        dersler.append({"ders_no": no, "baslangic": bas, "bitis": bit,
                        "sube": temizle(d.get("sube"), 16), "ders_adi": temizle(d.get("ders_adi"), 80)})
    return {"tarih": tarih, "dersler": dersler, "ileti": temizle(deger.get("ileti"), 160)}


def temizle(deger, sinir: int) -> str:
    return " ".join(deger.split())[:sinir] if isinstance(deger, str) else ""
