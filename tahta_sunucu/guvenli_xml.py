"""Güvenilmeyen XML için ortak denetimler (yalnız standart kitaplık; defusedxml eklenmez).

Kullananlar: `xlsx.py` (Kelebek R5, öğrenci listesi) ve `program_aktar.py` (aSc Timetables XML).
Yöntem: (1) UTF-16/32 BOM ve NUL baytı ret, (2) bildirilen kodlama yalnız UTF-8, (3) bayt düzeyinde
`<!DOCTYPE` / `<!ENTITY` ret, (4) expat ayrıştırıcısında DTD, varlık bildirimi ve dış varlık başvurusu
işleyicileri hata atar, parametre varlıkları hiç ayrıştırılmaz. DTD olmadan iç varlık tanımlanamaz;
"billion laughs" ve XXE olanaksızdır.
"""

from __future__ import annotations

import re
from xml.parsers import expat

GUVENSIZ = "Dosya güvenli olmayan XML içeriyor."
_BILDIRIM = re.compile(rb"\s*<\?xml[^>]*?encoding\s*=\s*[\"']([^\"']+)[\"']")
TURKCE_KODLAMALAR = (b"windows-1254", b"iso-8859-9", b"cp1254", b"latin5", b"iso8859-9")


class _Dtd(Exception):
    pass


def _reddet(*_):
    raise _Dtd


def on_denetim(veri: bytes, guvensiz: str = GUVENSIZ) -> None:
    """Ayrıştırmadan önceki bayt denetimleri; güvensizse ValueError(guvensiz)."""
    if veri.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff")) or b"\x00" in veri:
        raise ValueError(guvensiz)
    bildirim = _BILDIRIM.match(veri.removeprefix(b"\xef\xbb\xbf"))
    if bildirim and bildirim.group(1).lower().replace(b"_", b"-") not in (b"utf-8", b"utf8"):
        raise ValueError(guvensiz)
    if re.search(rb"<!DOCTYPE|<!ENTITY", veri, re.I):
        raise ValueError(guvensiz)


def ayristirici() -> expat.XMLParserType:
    """DTD ve varlık işleyicileri hata atan expat ayrıştırıcısı (`_Dtd`; `ayristir` bunu ValueError'a çevirir)."""
    p = expat.ParserCreate()
    p.StartDoctypeDeclHandler = _reddet
    p.EntityDeclHandler = _reddet
    p.UnparsedEntityDeclHandler = _reddet
    p.ExternalEntityRefHandler = _reddet
    p.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    return p


def ayristir(p: expat.XMLParserType, veri: bytes, okunamadi: str, guvensiz: str = GUVENSIZ) -> None:
    """Belgeyi bir kez baştan sona geçirir; DTD/varlık → ValueError(guvensiz), bozuk XML → ValueError(okunamadi)."""
    try:
        p.Parse(veri, True)
    except _Dtd as hata:
        raise ValueError(guvensiz) from hata
    except expat.ExpatError as hata:
        raise ValueError(okunamadi) from hata


def dtd_reddet(veri: bytes, okunamadi: str, guvensiz: str = GUVENSIZ) -> None:
    """DOCTYPE/ENTITY bildirimini kodlamadan bağımsız reddeder; bozuk XML'de ValueError(okunamadi)."""
    on_denetim(veri, guvensiz)
    ayristir(ayristirici(), veri, okunamadi, guvensiz)


def kodlama_duzelt(veri: bytes, ileti: str = "Dosya UTF-8 değil; aSc'den UTF-8 olarak kaydedin.") -> bytes:
    """BOM'lu/BOM'suz UTF-8 aynen; bildirimi windows-1254 / iso-8859-9 / cp1254 olan belge Python kodlayıcısıyla
    çözülüp bildirim `encoding="UTF-8"` yazılarak UTF-8'e çevrilir. UTF-16/32 ve başka bildirimler ValueError(ileti).
    Dönen baytlar yine `on_denetim`den geçirilmelidir."""
    if veri.startswith((b"\xff\xfe", b"\xfe\xff", b"\x00\x00\xfe\xff")):
        raise ValueError(ileti)
    govde = veri.removeprefix(b"\xef\xbb\xbf")
    bildirim = _BILDIRIM.match(govde)
    if not bildirim:
        return govde
    kodlama = bildirim.group(1).lower().replace(b"_", b"-")
    if kodlama in (b"utf-8", b"utf8"):
        return govde
    if kodlama not in TURKCE_KODLAMALAR:
        raise ValueError(ileti)
    if b"\x00" in govde:
        raise ValueError(ileti)
    try:
        metin = govde.decode("cp1254" if kodlama in (b"windows-1254", b"cp1254") else "iso-8859-9", errors="strict")
    except UnicodeDecodeError as hata:
        raise ValueError(ileti) from hata
    bas, son = bildirim.span(1)
    return (govde[:bas].decode("ascii", errors="strict") + "UTF-8" + metin[son:]).encode("utf-8")
