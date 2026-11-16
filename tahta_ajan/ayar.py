"""Ajanın yapılandırma ve durum dosyaları.

ajan.json sunucu adresini, sunucu sertifikasının parmak izini ve tahtanın
kimliğini taşır; yalnız yönetici (root) okuyabilir.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

YEREL_PORT = int(os.environ.get("TAHTA_AJAN_YEREL_PORT", "47811"))
# Sunucuyla bu kadar saniye konuşulamazsa tahta "çevrimdışı" sayılır ve kilit
# kodsuz açılabilir: sunucu arızası dersi rehin almaz.
CEVRIMDISI_SN = int(os.environ.get("TAHTA_AJAN_CEVRIMDISI_SN", "90"))


def _windows() -> bool:
    return sys.platform.startswith("win")


def ayar_dizini() -> Path:
    ortam = os.environ.get("TAHTA_AJAN_DIZIN")
    if ortam:
        return Path(ortam)
    if _windows():
        return Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "tahta-kontrol"
    return Path("/etc/tahta-kontrol")


def durum_dizini() -> Path:
    ortam = os.environ.get("TAHTA_AJAN_DURUM")
    if ortam:
        return Path(ortam)
    if _windows():
        return ayar_dizini() / "durum"
    return Path("/var/lib/tahta-kontrol")


def ayar_yolu() -> Path:
    return ayar_dizini() / "ajan.json"


def _json_oku(yol: Path) -> dict:
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return veri if isinstance(veri, dict) else {}


def _json_yaz(yol: Path, veri: dict, gizli: bool) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_suffix(".yeni")
    gecici.write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
    if gizli and not _windows():
        os.chmod(gecici, 0o600)
    os.replace(gecici, yol)


def oku() -> dict:
    return _json_oku(ayar_yolu())


def yaz(veri: dict) -> None:
    _json_yaz(ayar_yolu(), veri, gizli=True)


# ---- sunucu adres listesi (A6) ----------------------------------------------------
# ajan.json: "sunucu" (birincil, bağlanılan) + "sunucular" (sunucunun bildirdiği liste, en çok 5).
# Liste root'a özel ajan.json'da durur; ekran yardımcısına gitmez. Parmak izi her adreste aynı
# denetlendiği için listeyi sunucunun itmesi güvenlidir (yanlış adrese tek bayt veri gitmez).
ADRES_EN_COK = 5


# Ana makine adı izin listesi (sunucudaki adresler.makine_gecerli_mi ile aynı): geçerli IP ya da
# yalnız [a-z0-9-] etiketlerinden oluşan DNS adı. Kabuk metakarakteri ($ ( ) ` " ;) hiçbir yolda geçmez.
_DNS_ETIKET = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_DNS_ADI = re.compile(rf"{_DNS_ETIKET}(?:\.{_DNS_ETIKET})*")
_NETLOC = re.compile(r"[a-z0-9.\-\[\]:]+")


def _makine_gecerli_mi(makine: str, netloc: str) -> bool:
    if not _NETLOC.fullmatch(netloc or ""):
        return False
    try:
        ipaddress.ip_address(makine)
        return True
    except ValueError:
        pass
    return len(makine) <= 253 and bool(_DNS_ADI.fullmatch(makine))


def adres_dogrula(adres) -> str | None:
    """Sunucudaki adres kurallarının aynısı: https, ana makine dolu, port 1–65535, yerel adres
    değil, yol/sorgu yok. Geçerliyse sondaki / atılmış adres, değilse None."""
    adres = str(adres or "").strip().rstrip("/")
    if not adres.lower().startswith("https://") or any(c.isspace() for c in adres) or len(adres) > 200:
        return None
    try:
        parca = urlsplit(adres)
        port = parca.port
    except ValueError:
        return None
    makine = (parca.hostname or "").lower()
    if not makine or makine == "localhost" or makine.startswith("127.") or makine in ("::1", "0.0.0.0"):
        return None
    if not _makine_gecerli_mi(makine, parca.netloc.lower()):
        return None
    if port is not None and not 1 <= port <= 65535:
        return None
    if parca.path not in ("", "/") or parca.query or parca.fragment or parca.username or parca.password:
        return None
    return adres


def adresler_dogrula(liste) -> list[str]:
    """Sunucunun bildirdiği listeyi süzer: geçersiz öğe atılır, tekrarsız, en çok 5."""
    if not isinstance(liste, list):
        return []
    sonuc: list[str] = []
    for oge in liste:
        adres = adres_dogrula(oge)
        if adres and adres not in sonuc:
            sonuc.append(adres)
    return sonuc[:ADRES_EN_COK]


def adres_sirasi(yapi: dict) -> list[str]:
    """Deneme sırası: önce birincil ("sunucu"), sonra listedeki diğerleri (sıra korunur, tekrarsız)."""
    sira: list[str] = []
    for adres in [yapi.get("sunucu")] + list(yapi.get("sunucular") or []):
        adres = str(adres or "").rstrip("/")
        if adres and adres not in sira:
            sira.append(adres)
    return sira


def adres_listesi_ozet(liste) -> str:
    """Sunucunun karşılaştırdığı özet: "\\n".join(liste) SHA-256'sının ilk 12 hanesi (liste boşsa boş)."""
    if not liste:
        return ""
    return hashlib.sha256("\n".join(liste).encode("utf-8")).hexdigest()[:12]


def durum_oku() -> dict:
    return _json_oku(durum_dizini() / "durum.json")


def durum_yaz(veri: dict) -> None:
    _json_yaz(durum_dizini() / "durum.json", veri, gizli=True)


# ---- okul kimliği: tahta paleti ve logo -------------------------------------------
# Tonlar tahtada hesaplanmaz; sunucu (tahta_sunucu/tema.py) üretir ve hex olarak indirir.
# Bu palet, varsayılan temanın (lacivert + kehribar) tahta paletinin aynısıdır (test eder);
# eski sunucuya bağlı ya da henüz sunucuya ulaşmamış tahta bununla çizilir.
PALET_ANAHTARLARI = (
    "zemin", "yuzey", "serit", "metin", "soluk", "dugme", "dugme_kenar", "ana", "ana_metin", "vurgu", "bilgi",
)  # fmt: skip
VARSAYILAN_PALET = {
    "zemin": "#021020",
    "yuzey": "#08192a",
    "serit": "#00203e",
    "metin": "#f8fafc",
    "soluk": "#b4bfca",
    "dugme": "#25323f",
    "dugme_kenar": "#526170",
    "ana": "#36628e",
    "ana_metin": "#ffffff",
    "vurgu": "#e58044",
    "bilgi": "#ffc752",
}
_HEX = re.compile(r"#[0-9a-f]{6}")

LOGO_SINIRI = 256 * 1024


def palet_dogrula(palet) -> dict | None:
    """Sunucudan gelen paleti doğrular: bilinen anahtarlar, her biri #rrggbb (küçük harf).

    Eksik ya da geçersiz anahtar varsayılan paletin değeriyle doldurulur; sözlük değilse None.
    Doğrulanmamış hiçbir değer GTK stiline yazılmaz.
    """
    if not isinstance(palet, dict):
        return None
    sonuc = {}
    for ad in PALET_ANAHTARLARI:
        deger = palet.get(ad)
        sonuc[ad] = deger if isinstance(deger, str) and _HEX.fullmatch(deger) else VARSAYILAN_PALET[ad]
    return sonuc


def logo_gecerli(veri) -> bool:
    """Logo yalnız PNG ya da JPEG olabilir (sihirli baytlarla), en çok LOGO_SINIRI bayt."""
    if not isinstance(veri, (bytes, bytearray)) or not veri or len(veri) > LOGO_SINIRI:
        return False
    png = veri[:8] == b"\x89PNG\r\n\x1a\n" and veri[12:16] == b"IHDR"
    return png or veri[:3] == b"\xff\xd8\xff"


def logo_yolu() -> Path:
    """Logo yalnız servisin okuyabildiği yerde durur; ekran yardımcısına soketle gider."""
    return durum_dizini() / "logo"


def logo_oku() -> bytes | None:
    try:
        return logo_yolu().read_bytes()
    except OSError:
        return None


def logo_yaz(veri: bytes) -> None:
    yol = logo_yolu()
    yol.parent.mkdir(parents=True, exist_ok=True)
    gecici = yol.with_name("logo.yeni")
    gecici.write_bytes(veri)
    if not _windows():
        os.chmod(gecici, 0o600)
    os.replace(gecici, yol)


def logo_sil() -> None:
    try:
        logo_yolu().unlink()
    except OSError:
        pass
