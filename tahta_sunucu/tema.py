"""Okul kimliği teması: iki renkten (ana, vurgu) bütün panel ve tahta tonlarını üretir.

Bütün renkler burada, OKLCH uzayında hesaplanır ve sRGB gamutuna sığdırılır; her
metin/zemin çifti için kontrast eşiği (metin 4.5, tahtada uzaktan okuma 7, kenar
ve simge 3) burada tutturulur. Tarayıcıya ve tahtaya yalnız doğrulanmış hex iner;
tarayıcının yeni renk özellikleri yalnız Ayarlar'daki kayıt öncesi önizlemededir.

Yalnız standart kitaplık kullanılır.
"""

from __future__ import annotations

import hashlib
import math
import re
from functools import lru_cache

from . import vt

# Formül değişince artırılır: tema.css önbellek sürümüne girer.
TEMA_MOTORU = 1

VARSAYILAN_ANA = "#24507a"  # lacivert
VARSAYILAN_VURGU = "#b45309"  # kehribar

RENK = re.compile(r"#[0-9a-fA-F]{6}")

# Panelin açık ve koyu görünümünde üretilen anahtarlar (CSS'te -a ve -k ekiyle).
WEB_ANAHTARLARI = (
    "zemin", "yuzey", "yuzey2", "cizgi", "metin", "soluk", "ana", "ana-uzerine", "ana-yazi",
    "ana-hafif", "serit", "serit-yazi", "serit-soluk", "vurgu", "vurgu-serit",
)  # fmt: skip
# Tahta ekranının paleti (her zaman koyu).
TAHTA_ANAHTARLARI = (
    "zemin", "yuzey", "serit", "metin", "soluk", "dugme", "dugme_kenar", "ana", "ana_metin", "vurgu", "bilgi",
)  # fmt: skip


def renk_dogrula(deger) -> str | None:
    """#rrggbb biçimindeki rengi küçük harfle döndürür; başka her şey None."""
    deger = str(deger or "").strip()
    return deger.lower() if RENK.fullmatch(deger) else None


# ---- renk matematiği (OKLab / OKLCH, WCAG 2 bağıl parlaklık) ---------------------
def _dogrusal(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _gama(c: float) -> float:
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def _rgb(h: str) -> list[float]:
    return [int(h[i : i + 2], 16) / 255 for i in (1, 3, 5)]


def _hex(r) -> str:
    return "#" + "".join(f"{round(min(1.0, max(0.0, c)) * 255):02x}" for c in list(r))


def oklch(h: str) -> tuple[float, float, float]:
    r, g, b = (_dogrusal(c) for c in _rgb(h))
    l_ = math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    m_ = math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    s_ = math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    L = 0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_
    A = 1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_
    B = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_
    return L, math.hypot(A, B), math.atan2(B, A)


def _lch_dogrusal(L: float, C: float, h: float) -> list[float]:
    a, b = C * math.cos(h), C * math.sin(h)
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    return [
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    ]


def _icinde(v: list[float]) -> bool:
    return all(-1e-4 <= c <= 1 + 1e-4 for c in v)


def ton(L: float, C: float, h: float) -> str:
    """L sabit; renk sRGB gamutuna sığana kadar C ikili aramayla düşer (gamut eşlemesi burada)."""
    if not _icinde(_lch_dogrusal(L, C, h)):
        alt, ust = 0.0, C
        for _ in range(24):
            orta = (alt + ust) / 2
            alt, ust = (orta, ust) if _icinde(_lch_dogrusal(L, orta, h)) else (alt, orta)
        C = alt
    return _hex([_gama(c) for c in _lch_dogrusal(L, C, h)])


def parlaklik(h: str) -> float:
    r, g, b = (_dogrusal(c) for c in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def kontrast(x: str, y: str) -> float:
    a, b = parlaklik(x), parlaklik(y)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def uzerine(arka: str) -> str:
    return "#ffffff" if kontrast(arka, "#ffffff") >= 4.5 else "#000000"


def uydur(L: float, C: float, h: float, zeminler: list[str], esik: float, yon: int) -> str:
    """L'yi yon (+1 açar, -1 koyulaştırır) yönünde 0.005 adımla kaydırır; tüm zeminlere karşı esik tutunca durur."""
    for _ in range(200):
        x = ton(L, C, h)
        if all(kontrast(x, z) >= esik for z in zeminler):
            return x
        L = min(0.99, max(0.01, L + yon * 0.005))
    return "#000000" if yon < 0 else "#ffffff"


# ---- tema üretimi ----------------------------------------------------------------
@lru_cache(maxsize=32)
def uret(ana: str, vurgu: str | None) -> dict:
    """Ana ve vurgu renginden bütün tonları, kontrast raporunu ve notları üretir (saf işlev)."""
    L, C, h = oklch(ana)
    vL, vC, vh = oklch(vurgu or ana)

    def n(x: float) -> float:
        return min(C, x)

    a: dict[str, str] = {}
    a["zemin"] = ton(0.975, n(0.010), h)
    a["yuzey"] = "#ffffff"
    a["yuzey2"] = ton(0.955, n(0.016), h)
    a["cizgi"] = ton(0.90, n(0.02), h)
    a["metin"] = ton(0.21, n(0.02), h)
    a["soluk"] = uydur(0.50, n(0.025), h, [a["zemin"], a["yuzey"], a["yuzey2"]], 4.5, -1)
    a["ana"] = ana
    a["ana-uzerine"] = uzerine(ana)
    a["ana-hafif"] = ton(0.95, n(0.035), h)
    a["ana-yazi"] = uydur(min(L, 0.55), C, h, [a["yuzey"], a["zemin"], a["ana-hafif"]], 4.5, -1)
    a["serit"] = ton(0.27, n(0.08), h)
    a["serit-yazi"] = "#ffffff"
    a["serit-soluk"] = uydur(0.86, n(0.03), h, [a["serit"]], 4.5, +1)
    a["vurgu"] = vurgu or ana
    a["vurgu-serit"] = uydur(max(vL, 0.70), vC, vh, [a["serit"]], 3, +1)

    k: dict[str, str] = {}
    k["zemin"] = ton(0.165, n(0.018), h)
    k["yuzey"] = ton(0.205, n(0.02), h)
    k["yuzey2"] = ton(0.24, n(0.022), h)
    k["cizgi"] = ton(0.33, n(0.025), h)
    k["metin"] = ton(0.95, n(0.01), h)
    k["soluk"] = uydur(0.74, n(0.02), h, [k["zemin"], k["yuzey"], k["yuzey2"]], 4.5, +1)
    k["ana"] = uydur(max(L, 0.62), C, h, [k["yuzey"], k["zemin"]], 3, +1)
    k["ana-uzerine"] = uzerine(k["ana"])
    k["ana-hafif"] = ton(0.27, n(0.05), h)
    k["ana-yazi"] = uydur(max(L, 0.72), C, h, [k["yuzey"], k["zemin"], k["ana-hafif"]], 4.5, +1)
    k["serit"] = ton(0.14, n(0.05), h)
    k["serit-yazi"] = "#ffffff"
    k["serit-soluk"] = uydur(0.80, n(0.03), h, [k["serit"]], 4.5, +1)
    k["vurgu"] = uydur(max(vL, 0.70), vC, vh, [k["yuzey"]], 3, +1)
    k["vurgu-serit"] = uydur(max(vL, 0.70), vC, vh, [k["serit"]], 3, +1)

    t: dict[str, str] = {}
    t["zemin"] = ton(0.17, n(0.04), h)
    t["yuzey"] = ton(0.21, n(0.04), h)
    t["serit"] = ton(0.24, n(0.07), h)
    t["metin"] = "#f8fafc"
    t["soluk"] = uydur(0.80, n(0.02), h, [t["zemin"], t["yuzey"], t["serit"]], 7, +1)
    t["dugme"] = ton(0.31, n(0.03), h)
    t["dugme_kenar"] = uydur(0.42, n(0.03), h, [t["zemin"]], 3, +1)
    t["ana"] = ana if kontrast(ana, t["zemin"]) >= 3 else uydur(L, C, h, [t["zemin"]], 3, +1)
    t["ana_metin"] = uzerine(t["ana"])
    t["vurgu"] = uydur(max(vL, 0.70), vC, vh, [t["zemin"], t["serit"]], 4.5, +1)
    t["bilgi"] = uydur(0.86, 0.16, 1.45, [t["zemin"]], 7, +1)  # kehribar; sabit anlam

    rapor: list[dict] = []

    def olc(ad: str, palet: dict, on: str, arka: str, esik: float) -> None:
        oran = kontrast(palet[on], palet[arka])
        rapor.append({"ad": ad, "on": palet[on], "arka": palet[arka], "esik": esik, "oran": round(oran, 2)})

    for palet, gorunum in ((a, "Açık"), (k, "Koyu")):
        olc(f"{gorunum}: metin / sayfa zemini", palet, "metin", "zemin", 4.5)
        olc(f"{gorunum}: metin / kart", palet, "metin", "yuzey", 4.5)
        olc(f"{gorunum}: soluk metin / sayfa zemini", palet, "soluk", "zemin", 4.5)
        olc(f"{gorunum}: soluk metin / kart", palet, "soluk", "yuzey", 4.5)
        olc(f"{gorunum}: soluk metin / ikinci yüzey", palet, "soluk", "yuzey2", 4.5)
        olc(f"{gorunum}: düğme yazısı / ana renk", palet, "ana-uzerine", "ana", 4.5)
        olc(f"{gorunum}: bağlantı rengi / kart", palet, "ana-yazi", "yuzey", 4.5)
        olc(f"{gorunum}: bağlantı rengi / sayfa zemini", palet, "ana-yazi", "zemin", 4.5)
        olc(f"{gorunum}: bağlantı rengi / seçili kart", palet, "ana-yazi", "ana-hafif", 4.5)
        olc(f"{gorunum}: üst şerit yazısı / şerit", palet, "serit-yazi", "serit", 4.5)
        olc(f"{gorunum}: üst şerit soluk yazı / şerit", palet, "serit-soluk", "serit", 4.5)
        olc(f"{gorunum}: vurgu çizgisi / şerit", palet, "vurgu-serit", "serit", 3)
    olc("Tahta: metin / zemin", t, "metin", "zemin", 7)
    olc("Tahta: soluk metin / zemin", t, "soluk", "zemin", 7)
    olc("Tahta: soluk metin / yüzey", t, "soluk", "yuzey", 7)
    olc("Tahta: soluk metin / üst bant", t, "soluk", "serit", 7)
    olc("Tahta: tuş yazısı / tuş", t, "metin", "dugme", 4.5)
    olc("Tahta: tuş kenarı / zemin", t, "dugme_kenar", "zemin", 3)
    olc("Tahta: “Aç” yazısı / “Aç” tuşu", t, "ana_metin", "ana", 4.5)
    olc("Tahta: duyuru başlığı / zemin", t, "vurgu", "zemin", 4.5)
    olc("Tahta: vurgu çizgisi / üst bant", t, "vurgu", "serit", 4.5)
    olc("Tahta: bilgi yazısı / zemin", t, "bilgi", "zemin", 7)
    olc("Tahta: okul adı / üst bant", t, "metin", "serit", 4.5)

    notlar = []
    if a["ana-yazi"] != ana:
        notlar.append("Bağlantı ve odak rengi okunurluk için koyulaştırıldı.")
    if k["ana"] != ana:
        notlar.append("Koyu görünümde ana renk okunurluk için açıldı.")
    if t["ana"] != ana:
        notlar.append("Tahta ekranında “Aç” tuşunun rengi okunurluk için açıldı.")
    if a["ana-uzerine"] == "#000000":
        notlar.append("Ana renk açık olduğu için düğme yazısı siyah.")

    return {"acik": a, "koyu": k, "tahta": t, "rapor": rapor, "notlar": notlar}


def varsayilan() -> dict:
    """Ayar yokken kullanılan temanın çıktısı (stil.css ve ajanın varsayılan paleti bununla aynıdır)."""
    return uret(VARSAYILAN_ANA, VARSAYILAN_VURGU)


def tema_al(b) -> tuple[str, str | None]:
    """Ayardaki temayı doğrulayarak okur; yoksa ya da bozuksa varsayılan renkler."""
    kayit = vt.ayar_al(b, "tema")
    if isinstance(kayit, dict):
        ana = renk_dogrula(kayit.get("ana"))
        if ana:
            return ana, renk_dogrula(kayit.get("vurgu"))
    return VARSAYILAN_ANA, VARSAYILAN_VURGU


def surum(ana: str, vurgu: str | None) -> str:
    return hashlib.sha256(f"{TEMA_MOTORU}|{ana}|{vurgu}".encode()).hexdigest()[:12]


def css_degiskenleri(t: dict) -> list[tuple[str, str]]:
    """Tema çıktısını (CSS adı, hex) çiftlerine çevirir: -a açık, -k koyu, --t-* tahta."""
    ciftler = [(f"--{ad}-a", t["acik"][ad]) for ad in WEB_ANAHTARLARI]
    ciftler += [(f"--{ad}-k", t["koyu"][ad]) for ad in WEB_ANAHTARLARI]
    ciftler += [("--t-" + ad.replace("_", "-"), t["tahta"][ad]) for ad in TAHTA_ANAHTARLARI]
    return ciftler


def css_metni(ana: str, vurgu: str | None) -> str:
    ciftler = css_degiskenleri(uret(ana, vurgu))
    # Değerler yalnız uret() çıktısıdır; yine de hex olmayan hiçbir şey yazılmaz.
    govde = ";".join(f"{ad}:{deger}" for ad, deger in ciftler if RENK.fullmatch(deger))
    return "/* Tahta Kontrol teması: sunucu üretir, elle düzenlenmez. */\n:root{" + govde + "}\n"


def bas_harfler(okul_adi: str | None) -> str:
    """Okul adının ilk iki sözcüğünün baş harfleri (Türkçe büyük harf); en çok 2 karakter."""
    harfler = []
    for sozcuk in str(okul_adi or "").split():
        if sozcuk[0].isalpha():
            harfler.append(sozcuk[0])
        if len(harfler) == 2:
            break
    metin = "".join(harfler).replace("i", "İ").replace("ı", "I").upper()
    return metin[:2]
