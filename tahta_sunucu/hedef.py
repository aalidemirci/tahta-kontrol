"""Duyuru hedefi: şema doğrulaması, tahtalara çözümleme, özet metni ve tahta nitelikleri.

Hedef JSON'u (`duyuru_plani.hedef_json`, `duyuru.hedef_json`):
    {"tumu": true}
    {"tahtalar": [3, 7], "gruplar": [2], "bina": ["A Blok"], "kat": [1, 2], "duzey": ["9"], "devre": ["sabah"]}

Sonuç = açık tahtalar ∪ grup üyeleri ∪ süzgeç eşleşenleri. Süzgeçte dolu anahtarların
hepsi birden (VE), bir anahtarın değerlerinden biri (VEYA) sağlanmalıdır. Belirtilmemiş
alan hiçbir ölçüte uymaz. Yalnız onaylı tahtalar; hedef her gönderimde yeniden çözülür.
"""

from __future__ import annotations

import json
import re

from . import metin

DUZEYLER = {"hazirlik": "Hazırlık", "9": "9", "10": "10", "11": "11", "12": "12"}
DEVRELER = {"sabah": "Sabah", "ogle": "Öğle", "her_ikisi": "Sabah ve öğle"}
KAT_ARALIGI = (-2, 20)
BINA_EN_UZUN = 40
LISTE_EN_UZUN = 500
BOS_HEDEF_ILETISI = "Duyurunun hangi tahtalara gideceğini seçin."
_ANAHTARLAR = ("tumu", "tahtalar", "gruplar", "bina", "kat", "duzey", "devre")


# ---- tahta nitelikleri ---------------------------------------------------------------
def kat_adi(kat) -> str:
    if kat is None or kat == "":
        return "—"
    kat = int(kat)
    if kat == 0:
        return "Zemin kat"
    if kat == -1:
        return "Bodrum"
    if kat < -1:
        return f"{-kat}. bodrum"
    return f"{kat}. kat"


def kat_csv(kat) -> str:
    """CSV'ye yazılan kat değeri (kat_coz geri okur)."""
    if kat is None or kat == "":
        return ""
    kat = int(kat)
    return {0: "Zemin", -1: "Bodrum"}.get(kat, f"{-kat}. bodrum" if kat < 0 else f"{kat}. kat")


def kat_coz(deger) -> int | None:
    """"Zemin", "Bodrum", "2. bodrum", "-2", "3. kat", "3" → tamsayı; boş → None; tanınmazsa ValueError."""
    s = metin.katla(str(deger or "").lstrip("'"))
    if not s or s in ("-", "—", "belirtilmemis"):
        return None
    if s in ("zemin", "zemin kat", "z"):
        return 0
    if s in ("bodrum", "bodrum kat", "1. bodrum", "1 bodrum"):
        return -1
    eslesme = re.fullmatch(r"(\d+)\.?\s*bodrum(?: kat)?", s)
    if eslesme:
        kat = -int(eslesme.group(1))
    else:
        eslesme = re.fullmatch(r"(-?\d+)\.?(?:\s*kat)?", s)
        if not eslesme:
            raise ValueError(f"Kat tanınmadı: {deger}")
        kat = int(eslesme.group(1))
    if not KAT_ARALIGI[0] <= kat <= KAT_ARALIGI[1]:
        raise ValueError(f"Kat {KAT_ARALIGI[0]} ile {KAT_ARALIGI[1]} arasında olmalı: {deger}")
    return kat


def duzey_coz(deger) -> list[str]:
    """"9|10", "Hazırlık", "hazirlik,9" → ["hazirlik", "9"] (sıralı, tekrarsız); tanınmazsa ValueError."""
    sonuc: list[str] = []
    for parca in re.split(r"[|,;/]", str(deger or "")):
        s = metin.katla(parca)
        if not s:
            continue
        s = re.sub(r"\.?\s*sinif(lar)?$", "", s).strip(". ")
        if s in ("hazirlik", "haz", "hz"):
            s = "hazirlik"
        if s not in DUZEYLER:
            raise ValueError(f"Düzey tanınmadı: {parca.strip()} (Hazırlık, 9, 10, 11 ya da 12)")
        if s not in sonuc:
            sonuc.append(s)
    return [d for d in DUZEYLER if d in sonuc]


def devre_coz(deger) -> str:
    s = metin.katla(str(deger or "")).replace("_", " ")
    if not s or s in ("-", "—", "belirtilmemis"):
        return ""
    if s in ("sabah", "sabahci"):
        return "sabah"
    if s in ("ogle", "oglen", "ogleden sonra", "oglenci"):
        return "ogle"
    if s in ("sabah ve ogle", "her ikisi", "ikisi", "sabah ogle", "tam gun"):
        return "her_ikisi"
    raise ValueError(f"Devre tanınmadı: {deger} (Sabah, Öğle ya da Sabah ve öğle)")


def subeler_coz(deger) -> list[str]:
    """"9/A, 10-b" ya da "9/A|10/B" → ["9/A", "10/B"]; tanınmayan şube ValueError."""
    sonuc: list[str] = []
    for parca in re.split(r"[|,;]", str(deger or "")):
        if not parca.strip():
            continue
        sube = metin.sube_duzelt(parca)
        if not sube:
            raise ValueError(f"Şube tanınmadı: {parca.strip()} (ör. 9/A, Hazırlık/B)")
        if sube not in sonuc:
            sonuc.append(sube)
    return sonuc


def kume(deger: str) -> list[str]:
    return [p for p in str(deger or "").split(",") if p]


def alanlar_metni(tahta) -> str:
    """Kartlarda gösterilen kısa nitelik satırı: "A Blok · 2. kat · 11 · Sabah"; boşsa ""."""
    parcalar = []
    if tahta["bina"]:
        parcalar.append(tahta["bina"])
    if tahta["kat"] is not None:
        parcalar.append(kat_adi(tahta["kat"]))
    duzeyler = kume(tahta["duzeyler"])
    if duzeyler:
        parcalar.append(", ".join(DUZEYLER[d] for d in duzeyler if d in DUZEYLER))
    if tahta["devre"] in DEVRELER:
        parcalar.append(DEVRELER[tahta["devre"]])
    return " · ".join(parcalar)


def bina_anahtari(s) -> str:
    """Bina eşleme anahtarı: büyük/küçük harf, Türkçe harf ve fazla boşluk duyarsız."""
    return metin.katla(s)


# ---- hedef şeması ---------------------------------------------------------------------
KIMLIK_EN_BUYUK = 2**31 - 1  # SQLite tamsayısına sığar; daha büyüğü 500 yerine 400 ile reddedilir


def kimlik_mi(d) -> bool:
    """Sayısal kimlik (ya da kat) mı: işaretli rakam dizisi ve |değer| <= KIMLIK_EN_BUYUK."""
    s = str(d).strip()
    rakam = s[1:] if s.startswith("-") else s
    return rakam.isdigit() and len(rakam) <= 10 and abs(int(s)) <= KIMLIK_EN_BUYUK


def _tamsayilar(deger, ad: str) -> list[int]:
    if not isinstance(deger, list) or len(deger) > LISTE_EN_UZUN:
        raise ValueError(f"Hedefte '{ad}' bir liste olmalı.")
    sonuc = []
    for d in deger:
        if isinstance(d, bool) or not isinstance(d, (int, str)) or not str(d).lstrip("-").isdigit():
            raise ValueError(f"Hedefte '{ad}' yalnız sayı içerebilir.")
        if not kimlik_mi(d):
            raise ValueError(f"Hedefte '{ad}' geçersiz bir sayı içeriyor.")
        if int(d) not in sonuc:
            sonuc.append(int(d))
    return sonuc


def _metinler(deger, ad: str) -> list[str]:
    if not isinstance(deger, list) or len(deger) > LISTE_EN_UZUN:
        raise ValueError(f"Hedefte '{ad}' bir liste olmalı.")
    sonuc = []
    for d in deger:
        if not isinstance(d, str):
            raise ValueError(f"Hedefte '{ad}' yalnız metin içerebilir.")
        if d.strip() and d.strip() not in sonuc:
            sonuc.append(d.strip())
    return sonuc


def dogrula(ham) -> dict:
    """Hedefi şemaya göre doğrular ve temiz sözlük döndürür; uymayanı ValueError ile reddeder."""
    if isinstance(ham, (str, bytes)):
        try:
            ham = json.loads(ham or "null")
        except ValueError as hata:
            raise ValueError(BOS_HEDEF_ILETISI) from hata
    if not isinstance(ham, dict):
        raise ValueError(BOS_HEDEF_ILETISI)
    bilinmeyen = [a for a in ham if a not in _ANAHTARLAR]
    if bilinmeyen:
        raise ValueError(f"Hedefte bilinmeyen alan: {bilinmeyen[0]}")
    if ham.get("tumu") is True:
        return {"tumu": True}
    if "tumu" in ham and ham["tumu"] not in (False, None):
        raise ValueError("Hedefte 'tumu' true ya da false olmalı.")
    temiz: dict = {}
    for ad in ("tahtalar", "gruplar"):
        if ad in ham:
            temiz[ad] = _tamsayilar(ham[ad], ad)
    if "kat" in ham:
        katlar = _tamsayilar(ham["kat"], "kat")
        if any(not KAT_ARALIGI[0] <= k <= KAT_ARALIGI[1] for k in katlar):
            raise ValueError("Hedefteki kat geçersiz.")
        temiz["kat"] = katlar
    if "bina" in ham:
        binalar = _metinler(ham["bina"], "bina")
        if any(len(b) > BINA_EN_UZUN for b in binalar):
            raise ValueError("Hedefteki bina adı çok uzun.")
        temiz["bina"] = binalar
    for ad, gecerli in (("duzey", DUZEYLER), ("devre", DEVRELER)):
        if ad in ham:
            degerler = _metinler(ham[ad], ad)
            if any(d not in gecerli for d in degerler):
                raise ValueError(f"Hedefteki {ad} değeri geçersiz.")
            temiz[ad] = degerler
    temiz = {a: d for a, d in temiz.items() if d}
    if not temiz:
        raise ValueError(BOS_HEDEF_ILETISI)
    return temiz


def formdan(form) -> dict:
    """Duyuru formunun "Kime" bölümünden ham hedef sözlüğü (doğrulanmamış).

    Alanlar: kime=tumu|secim; bina, kat, duzey, devre, grup, hedef_tahta (çoklu).
    """
    if str(form.get("kime", "")) == "tumu":
        return {"tumu": True}
    ham: dict = {}
    for alan, anahtar in (("hedef_tahta", "tahtalar"), ("grup", "gruplar"), ("kat", "kat")):
        degerler = [str(d) for d in form.getlist(alan) if kimlik_mi(d)]
        if degerler:
            ham[anahtar] = [int(d) for d in degerler]
    for alan in ("bina", "duzey", "devre"):
        degerler = [str(d) for d in form.getlist(alan) if str(d).strip()]
        if degerler:
            ham[alan] = degerler
    return ham


def _suzgec_uyar(tahta, hedef: dict) -> bool:
    olcutler = [a for a in ("bina", "kat", "duzey", "devre") if hedef.get(a)]
    if not olcutler:
        return False
    if "bina" in hedef and (
        not tahta["bina"] or bina_anahtari(tahta["bina"]) not in {bina_anahtari(b) for b in hedef["bina"]}
    ):
        return False
    if "kat" in hedef and (tahta["kat"] is None or tahta["kat"] not in hedef["kat"]):
        return False
    if "duzey" in hedef and not set(kume(tahta["duzeyler"])) & set(hedef["duzey"]):
        return False
    if "devre" in hedef:
        devre = tahta["devre"]
        if not devre:
            return False
        if devre != "her_ikisi" and devre not in hedef["devre"]:
            return False
    return True


def coz(b, hedef: dict) -> list:
    """Hedefin şu an ulaştığı onaylı tahta satırları, ad sırasıyla."""
    tahtalar = b.execute("SELECT * FROM tahta WHERE durum = 'onayli'").fetchall()
    if hedef.get("tumu"):
        secilen = list(tahtalar)
    else:
        acik = set(hedef.get("tahtalar") or [])
        if hedef.get("gruplar"):
            isaret = ",".join("?" * len(hedef["gruplar"]))
            acik |= {
                s["tahta_id"]
                for s in b.execute(
                    f"SELECT tahta_id FROM tahta_grubu_uye WHERE grup_id IN ({isaret})", hedef["gruplar"]
                ).fetchall()
            }
        secilen = [t for t in tahtalar if t["id"] in acik or _suzgec_uyar(t, hedef)]
    return sorted(secilen, key=lambda t: (metin.tr_sirala_anahtari(t["ad"]), t["id"]))


def ozet(b, hedef: dict) -> str:
    """"Tüm tahtalar" | "A Blok · 1., 2. kat + Fen laboratuvarları + 3 tahta"."""
    if hedef.get("tumu"):
        return "Tüm tahtalar"
    parcalar = []
    suzgec = []
    if hedef.get("bina"):
        suzgec.append(", ".join(hedef["bina"]))
    if hedef.get("kat"):
        katlar = sorted(hedef["kat"])
        if len(katlar) > 1 and all(k > 0 for k in katlar):
            suzgec.append(", ".join(f"{k}." for k in katlar) + " kat")
        else:
            suzgec.append(", ".join(kat_adi(k) for k in katlar))
    if hedef.get("duzey"):
        suzgec.append("Düzey " + ", ".join(DUZEYLER[d] for d in DUZEYLER if d in hedef["duzey"]))
    if hedef.get("devre"):
        suzgec.append(", ".join(DEVRELER[d] for d in DEVRELER if d in hedef["devre"]))
    if suzgec:
        parcalar.append(" · ".join(suzgec))
    if hedef.get("gruplar"):
        isaret = ",".join("?" * len(hedef["gruplar"]))
        adlar = [
            s["ad"]
            for s in b.execute(f"SELECT ad FROM tahta_grubu WHERE id IN ({isaret}) ORDER BY ad", hedef["gruplar"])
        ]
        if adlar:
            parcalar.append(", ".join(adlar))
        else:
            parcalar.append("silinmiş grup")
    if hedef.get("tahtalar"):
        idler = hedef["tahtalar"]
        if len(idler) <= 3:
            isaret = ",".join("?" * len(idler))
            adlar = [
                s["ad"] for s in b.execute(f"SELECT ad FROM tahta WHERE id IN ({isaret}) ORDER BY ad", idler)
            ]
            parcalar.append(", ".join(adlar) if adlar else f"{len(idler)} tahta")
        else:
            parcalar.append(f"{len(idler)} tahta")
    return " + ".join(parcalar) or "—"


def plan_gruplari(b, durumlar=("etkin", "duraklatildi")) -> dict[int, list[str]]:
    """Grup kimliği → onu hedefinde kullanan planların başlıkları (silme engeli için)."""
    isaret = ",".join("?" * len(durumlar))
    sonuc: dict[int, list[str]] = {}
    for plan in b.execute(
        f"SELECT id, baslik, metin, hedef_json FROM duyuru_plani WHERE durum IN ({isaret})", tuple(durumlar)
    ):
        try:
            gruplar = json.loads(plan["hedef_json"]).get("gruplar") or []
        except (ValueError, AttributeError):
            continue
        ad = plan["baslik"] or plan["metin"][:40]
        for g in gruplar:
            sonuc.setdefault(int(g), []).append(ad)
    return sonuc
