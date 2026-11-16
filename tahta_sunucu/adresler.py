"""Sunucu adres listesi (A6): tahtalara her yanıtta iletilen, en çok 5 adreslik liste.

Ajan sunucuya ulaşamazsa listede sırayla dener (parmak izi her adreste aynı denetlenir;
bu yüzden listeyi sunucunun itmesi güvenlidir). Eski tek adreslik `sunucu_adresi` ayarı
okunur: `sunucu_adresleri` yoksa ve eski anahtar doluysa liste `[sunucu_adresi]` sayılır.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from urllib.parse import urlsplit

from . import vt

EN_COK = 5
# Ana makine adı izin listesi: geçerli bir IP ya da yalnız [a-z0-9-] etiketlerinden oluşan DNS adı.
# Adres kur.sh'e (root yetkili kabuk betiği) yazıldığı için $ ( ) ` " ; gibi karakterler asla geçmez.
_DNS_ETIKET = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_DNS_ADI = re.compile(rf"{_DNS_ETIKET}(?:\.{_DNS_ETIKET})*")
_NETLOC = re.compile(r"[a-z0-9.\-\[\]:]+")


def makine_gecerli_mi(makine: str, netloc: str) -> bool:
    """Ana makine adı geçerli IP ya da DNS adı mı; netloc yalnız güvenli karakterlerden mi oluşuyor."""
    if not _NETLOC.fullmatch(netloc or "") or len(netloc) > 200:
        return False
    try:
        ipaddress.ip_address(makine)
        return True
    except ValueError:
        pass
    return len(makine) <= 253 and bool(_DNS_ADI.fullmatch(makine))


def betige_yazilabilir_mi(adres: str) -> bool:
    """kur.sh'e yazılacak her adres için son savunma: https, ayrıştırılabilir, yalnız güvenli karakterler."""
    adres = str(adres or "")
    if not adres.startswith("https://"):
        return False
    try:
        parca = urlsplit(adres)
        _ = parca.port  # geçersiz port ValueError verir
    except ValueError:
        return False
    if parca.path or parca.query or parca.fragment or parca.username or parca.password:
        return False
    return makine_gecerli_mi((parca.hostname or "").lower(), parca.netloc)


def dogrula_tek(adres: str) -> str:
    """Tek adresi denetleyip kanonik biçimini (sondaki / atılmış) döndürür; hata: ValueError."""
    adres = str(adres or "").strip().rstrip("/")
    if not adres.lower().startswith("https://"):
        raise ValueError(f"{adres or '(boş)'}: adres https:// ile başlamalı.")
    try:
        parca = urlsplit(adres)
        port = parca.port
    except ValueError as hata:
        raise ValueError(f"{adres}: bağlantı noktası 1–65535 arasında olmalı.") from hata
    makine = (parca.hostname or "").lower()
    if not makine:
        raise ValueError(f"{adres}: sunucu adı ya da IP adresi yok.")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError(f"{adres}: bağlantı noktası 1–65535 arasında olmalı.")
    if makine == "localhost" or makine.startswith("127.") or makine in ("::1", "0.0.0.0"):
        raise ValueError(f"{adres}: tahtalar bu bilgisayarın yerel adresine ulaşamaz; okul ağındaki adresi yazın.")
    if parca.path not in ("", "/") or parca.query or parca.fragment or parca.username or parca.password:
        raise ValueError(f"{adres}: adreste yol ya da sorgu olmamalı (ör. https://10.0.0.5:8788).")
    if any(c.isspace() for c in adres):
        raise ValueError(f"{adres}: adreste boşluk olmamalı.")
    if not makine_gecerli_mi(makine, parca.netloc.lower()):
        raise ValueError(f"{adres}: sunucu adı yalnız harf, rakam, nokta ve tire içerebilir (ya da geçerli bir IP adresi olmalı).")
    return f"https://{parca.netloc.lower()}"


def dogrula(metin) -> list[str]:
    """Çok satırlı metni (ya da listeyi) doğrular: en çok 5 satır, tekrarlar atılır. Boş liste geçerlidir."""
    satirlar = metin if isinstance(metin, list) else str(metin or "").replace("\r", "\n").split("\n")
    sonuc: list[str] = []
    for satir in satirlar:
        if not str(satir).strip():
            continue
        adres = dogrula_tek(satir)
        if adres not in sonuc:
            sonuc.append(adres)
    if len(sonuc) > EN_COK:
        raise ValueError(f"En çok {EN_COK} adres yazılabilir.")
    return sonuc


def _gecerli_mi(adres: str) -> bool:
    try:
        dogrula_tek(adres)
    except ValueError:
        return False
    return True


def al(b) -> list[str]:
    """Kayıtlı liste; doğrulamadan geçmeyen öğe (ör. elle bozulmuş ya da eski sürümden kalma
    `sunucu_adresi`) atılır: liste kur.sh'e ve tahtalara gider."""
    liste = vt.ayar_al(b, "sunucu_adresleri")
    if isinstance(liste, list):
        return [str(a) for a in liste if isinstance(a, str) and _gecerli_mi(a)][:EN_COK]
    eski = str(vt.ayar_al(b, "sunucu_adresi", "") or "").strip().rstrip("/")
    return [eski] if eski and _gecerli_mi(eski) else []


def yaz(b, liste: list[str]) -> None:
    """Yeni anahtarı yazar, eski tek adres anahtarını boşaltır (kod içi geçiş)."""
    vt.ayar_yaz(b, "sunucu_adresleri", list(liste))
    if vt.ayar_al(b, "sunucu_adresi", ""):
        vt.ayar_yaz(b, "sunucu_adresi", "")


def ozet(liste: list[str]) -> str:
    """Ajanın `adres_listesi_ozet`'iyle karşılaştırılan özet: "\\n".join SHA-256'sının ilk 12 hanesi."""
    return hashlib.sha256("\n".join(liste).encode("utf-8")).hexdigest()[:12]


def makine(adres: str) -> str:
    try:
        return (urlsplit(adres).hostname or "").lower()
    except ValueError:
        return ""


def ip_mi(ad: str) -> bool:
    try:
        ipaddress.ip_address(ad)
    except ValueError:
        return False
    return True


def bu_bilgisayar_listede_mi(liste: list[str], yerel_ipler: list[str]) -> bool:
    """Pano uyarısı için: liste boşsa ya da listede DNS adı varsa True (uyarı yok);
    yoksa bu bilgisayarın IPv4 adreslerinden biri listede IP olarak geçiyor mu."""
    if not liste:
        return True
    makineler = [makine(a) for a in liste]
    if any(m and not ip_mi(m) for m in makineler):
        return True
    return any(ip in makineler for ip in yerel_ipler)
