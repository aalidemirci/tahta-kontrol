"""Türkçe metin yardımcıları ve CSV okuma/yazma (yalnız standart kitaplık).

Aşamalar arasında ortaktır: tahta CSV'si (A2), derslik CSV'si (A3), öğrenci ve
icmal CSV'leri (A5), envanter CSV'si (A6) bunları kullanır.
"""

from __future__ import annotations

import csv
import io
import re

_KATLA = str.maketrans(
    {"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u",
     "Ç": "c", "Ğ": "g", "İ": "i", "I": "i", "Ö": "o", "Ş": "s", "Ü": "u", "Â": "a", "Î": "i", "Û": "u"}
)  # fmt: skip
_ABECE = "abcçdefgğhıijklmnoöprsştuüvyz"
_SIRA = {h: i for i, h in enumerate(_ABECE)}


def rakam_mi(s) -> bool:
    """Yalnız ASCII 0-9'dan oluşan, boş olmayan metin. `str.isdigit()` "²", "١" gibi karakterleri de
    kabul eder ama `int()` onları çeviremez; sayı denetimleri bunu kullanır."""
    return isinstance(s, str) and s.isascii() and s.isdigit()


def katla(s) -> str:
    """Türkçe harfleri ASCII'ye indirip küçük harfe çevirir; boşlukları sadeleştirir.

    Başlık ve ad eşlemede kullanılır: "Düzeyler" == "duzeyler", "İÇ" == "ic".
    """
    return " ".join(str(s or "").translate(_KATLA).lower().split())


def tr_buyuk(s: str) -> str:
    return str(s).replace("i", "İ").replace("ı", "I").upper()


def tr_kucuk(s: str) -> str:
    return str(s).replace("I", "ı").replace("İ", "i").lower()


def tr_sirala_anahtari(s: str) -> tuple:
    """Türk abecesine göre sıralama anahtarı (ç c'den, ı i'den önce gelir)."""
    return tuple(_SIRA.get(h, 100 + ord(h)) for h in tr_kucuk(s or ""))


_SUBE = re.compile(r"^(hazırlık|hazirlik|haz|hz|9|10|11|12)\s*(?:\.?\s*sınıf|\.?\s*sinif)?\s*[-/ .]?\s*([a-zçğıöşü])$")


def sube_duzelt(s) -> str | None:
    """Şube yazımını kanonik biçime getirir: "10-a" → "10/A", "hazırlık b" → "Hazırlık/B".

    Harf Türkçe büyük harfle yazılır ("10/I" ile "10/İ" ayrı şubedir). Tanınmazsa None.
    """
    ham = tr_kucuk(" ".join(str(s or "").strip().split()))
    # 0.10.0 (program aktarma §3.4): sondaki "şubesi"/"şube" sözcüğü atılır, "sınıfı" eki "sınıf" sayılır
    # ("9. Sınıf A Şubesi" → "9/A", "9A Şubesi" → "9/A"); önceden kabul edilen yazımların sonucu değişmez.
    ham = re.sub(r"\s*\bşube(?:si)?$", "", ham).replace("sınıfı", "sınıf").replace("sinifi", "sinif")
    eslesme = _SUBE.match(ham)
    if not eslesme:
        return None
    duzey, harf = eslesme.groups()
    if duzey in ("hazırlık", "hazirlik", "haz", "hz"):
        duzey = "Hazırlık"
    return f"{duzey}/{tr_buyuk(harf)}"


def sube_duzeyi(sube) -> str | None:
    """Kanonik şubenin düzeyi: "Hazırlık/B" → "hazirlik", "10/A" → "10"; tanınmazsa None."""
    kanonik = sube_duzelt(sube)
    if not kanonik:
        return None
    duzey = kanonik.split("/", 1)[0]
    return "hazirlik" if duzey == "Hazırlık" else duzey


def derslik_anahtari(s) -> str:
    """Derslik adını eşleme için sadeleştirir: küçük harf, tek boşluk, sondaki " dersliği"/" salonu" atılır."""
    metin = " ".join(tr_kucuk(str(s or "")).split())
    for ek in (" dersliği", " salonu"):
        if metin.endswith(ek):
            metin = metin[: -len(ek)].rstrip()
    return metin


def csv_oku(bayt: bytes, en_cok_bayt: int, en_cok_satir: int) -> tuple[list[str], list[list[str]]]:
    """CSV baytlarını (başlıklar, satırlar) olarak döndürür.

    Kodlama önce UTF-8 (BOM'lu ya da BOM'suz), olmazsa cp1254 (Türkçe Excel'in ANSI kaydı).
    Ayraç ilk satırdan seçilir: `;` → sekme → `,`. Boş satırlar atlanır; satırlar başlık
    sayısına tamamlanır. Sınır aşılırsa ya da başlık yoksa kullanıcıya gösterilecek
    iletiyle ValueError.
    """
    if len(bayt) > en_cok_bayt:
        raise ValueError(f"Dosya en çok {en_cok_bayt // (1024 * 1024) or 1} MB olabilir.")
    try:
        metin = bayt.decode("utf-8-sig")
    except UnicodeDecodeError:
        metin = bayt.decode("cp1254", errors="replace")
    ilk = metin.split("\n", 1)[0]
    ayrac = ";" if ";" in ilk else "\t" if "\t" in ilk else ","
    okuyucu = csv.reader(io.StringIO(metin, newline=""), delimiter=ayrac)
    basliklar: list[str] | None = None
    satirlar: list[list[str]] = []
    try:
        for satir in okuyucu:
            if not any(h.strip() for h in satir):
                continue
            if basliklar is None:
                basliklar = [h.strip() for h in satir]
                continue
            if len(satirlar) >= en_cok_satir:
                raise ValueError(f"Dosyada en çok {en_cok_satir} satır olabilir.")
            satirlar.append([h.strip() for h in satir] + [""] * (len(basliklar) - len(satir)))
    except csv.Error as hata:
        raise ValueError("CSV dosyası okunamadı.") from hata
    if not basliklar:
        raise ValueError("Dosyada başlık satırı yok.")
    return basliklar, satirlar


_FORMUL_BASI = ("=", "+", "-", "@", "\t", "\r")


def _hucre(deger) -> str:
    metin = "" if deger is None else str(deger)
    # Excel'de formül olarak çalışmasın (CSV enjeksiyonu).
    if metin[:1] in _FORMUL_BASI:
        metin = "'" + metin
    return metin


def csv_hucre_coz(deger) -> str:
    """csv_yaz'ın formül kaçışını geri alır: "'-1 Lab" → "-1 Lab".

    Yalnız kaçış karakterinden sonra formül başı (= + - @ sekme satır başı) geliyorsa
    baştaki tek `'` atılır; dışa aktarılan dosya değiştirilmeden geri yüklenince değer bozulmaz.
    """
    metin = "" if deger is None else str(deger)
    if len(metin) > 1 and metin[0] == "'" and metin[1] in _FORMUL_BASI:
        return metin[1:]
    return metin


def csv_yaz(basliklar: list[str], satirlar) -> bytes:
    """UTF-8 BOM'lu, `;` ayraçlı, CRLF satır sonlu CSV (Türkçe Excel doğrudan açar)."""
    tampon = io.StringIO(newline="")
    yazici = csv.writer(tampon, delimiter=";", lineterminator="\r\n")
    yazici.writerow([_hucre(b) for b in basliklar])
    for satir in satirlar:
        yazici.writerow([_hucre(h) for h in satir])
    return ("﻿" + tampon.getvalue()).encode("utf-8")
