"""Okul logosu: doğrulama, saklama ve okuma.

Yalnız PNG ve JPEG kabul edilir; tür sihirli baytlardan, ölçü dosya başlığından
okunur (Pillow gerekmez). Dosya veri dizininde sabit bir adla durur; kullanıcının
dosya adı hiçbir yerde kullanılmaz. /statik altına yazılmaz: kurulu programın
klasörü salt okunurdur ve güncellemede silinir.
"""

from __future__ import annotations

import hashlib
import os
import struct
from pathlib import Path

from . import ayar, vt

LOGO_SINIRI = 256 * 1024
EN_KUCUK, EN_BUYUK = 64, 2048
PNG_IMZA = b"\x89PNG\r\n\x1a\n"
TURLER = {"png": "image/png", "jpeg": "image/jpeg"}

# SOFn işaretçileri (C4 DHT, C8 JPG, CC DAC değildir).
_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def _jpeg_olcu(veri: bytes) -> tuple[int, int]:
    s = 2
    boy_ = len(veri)
    while s < boy_:
        if veri[s] != 0xFF:
            raise ValueError("Logo dosyası okunamadı.")
        while s < boy_ and veri[s] == 0xFF:  # dolgu baytları
            s += 1
        if s >= boy_:
            break
        isaret = veri[s]
        s -= 1  # s yeniden işaretçinin 0xFF konumunu gösterir
        if isaret == 0xD8 or isaret == 0x01 or 0xD0 <= isaret <= 0xD7:
            s += 2
            continue
        if isaret == 0xDA or isaret == 0xD9:
            break
        if s + 4 > boy_:
            break
        uzunluk = struct.unpack(">H", veri[s + 2 : s + 4])[0]
        if isaret in _SOF:
            if s + 9 > boy_:
                break
            boy, en = struct.unpack(">HH", veri[s + 5 : s + 9])
            return en, boy
        if uzunluk < 2:
            break
        s += 2 + uzunluk
    raise ValueError("Logo dosyası okunamadı.")


def logo_dogrula(veri: bytes) -> tuple[str, int, int]:
    """(tür, en, boy) döndürür; geçersizse kullanıcıya gösterilecek iletiyle ValueError."""
    if veri.startswith(PNG_IMZA):
        if len(veri) < 24 or veri[12:16] != b"IHDR":
            raise ValueError("Logo dosyası okunamadı.")
        en, boy = struct.unpack(">II", veri[16:24])
        tur = "png"
    elif veri.startswith(b"\xff\xd8\xff"):
        en, boy = _jpeg_olcu(veri)
        tur = "jpeg"
    else:
        raise ValueError("Logo PNG ya da JPEG olmalı.")
    if not (EN_KUCUK <= en <= EN_BUYUK and EN_KUCUK <= boy <= EN_BUYUK):
        raise ValueError("Logonun kenarları 64–2048 piksel olmalı.")
    if en > 4 * boy or boy > 4 * en:
        raise ValueError("Logo çok uzun ya da çok dar (en-boy oranı 1:4 ile 4:1 arasında olmalı).")
    return tur, en, boy


def logo_yolu() -> Path:
    return ayar.veri_dizini() / "marka" / "logo"


def logo_yaz(veri: bytes) -> None:
    hedef = logo_yolu()
    hedef.parent.mkdir(parents=True, exist_ok=True)
    gecici = hedef.with_name("logo.yeni")
    gecici.write_bytes(veri)
    os.replace(gecici, hedef)


def logo_sil() -> None:
    try:
        logo_yolu().unlink()
    except FileNotFoundError:
        pass


def _bilgi(b) -> dict | None:
    bilgi = vt.ayar_al(b, "logo")
    if not isinstance(bilgi, dict) or bilgi.get("tur") not in TURLER:
        return None
    sha = str(bilgi.get("sha256", ""))
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        return None
    return bilgi


def logo_oku(b) -> tuple[bytes, dict] | None:
    """(baytlar, ayar bilgisi); logo yoksa, dosya eksikse ya da özet tutmuyorsa None."""
    bilgi = _bilgi(b)
    if not bilgi:
        return None
    try:
        veri = logo_yolu().read_bytes()
    except OSError:
        return None
    if hashlib.sha256(veri).hexdigest() != bilgi["sha256"]:
        return None
    return veri, bilgi


_surum_onbellegi: dict = {}


def logo_surumu(b) -> str:
    """Sayfalardaki logo adresinin sürümü (sha256'nın ilk 12 hanesi); logo kullanılamıyorsa boş.

    /marka/logo ile aynı ölçüt (logo_oku: dosya var ve özeti ayardakiyle tutuyor); yoksa sayfa
    404 dönen bir adres ister ve kırık resim görünür. Özet her sayfada yeniden hesaplanmasın diye
    dosyanın (yol, boyut, mtime) ve beklenen özete göre önbelleklenir.
    """
    bilgi = _bilgi(b)
    if not bilgi:
        return ""
    yol = logo_yolu()
    try:
        d = yol.stat()
    except OSError:
        return ""
    anahtar = (str(yol), d.st_size, d.st_mtime_ns, bilgi["sha256"])
    if anahtar not in _surum_onbellegi:
        _surum_onbellegi.clear()
        _surum_onbellegi[anahtar] = logo_oku(b) is not None
    return bilgi["sha256"][:12] if _surum_onbellegi[anahtar] else ""
