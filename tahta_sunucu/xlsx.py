"""Standart kitaplıkla .xlsx okuyucu (yalnız ilk sayfanın hücre değerleri).

Aşama 4 (Kelebek R5) ve Aşama 5 (öğrenci listesi) kullanır; `openpyxl` eklenmez.
Biçim, formül ve tarih türleri okunmaz: her hücre metin olarak gelir. Güvenlik:
ZIP üye sayısı ve açılmış boyut sınırlıdır, XML'de `<!DOCTYPE` (varlık genişletme)
reddedilir, yalnız dört üye okunur.
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
import zlib
from xml.etree import ElementTree as ET
from xml.parsers import expat

UYE_SINIRI = 200
ACILMIS_SINIR = 50 * 1024 * 1024
SATIR_SINIRI = 100_000  # bellek koruması; asıl iş sınırını çağıran koyar
SUTUN_SINIRI = 200
OKUNAMADI = "Dosya okunamadı; Kelebek'ten indirilen .xlsx dosyasını yükleyin."

_ANA = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_REL_BELGE = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"
_ADRES = re.compile(r"^([A-Z]{1,3})(\d+)$")


def _sutun_no(harfler: str) -> int:
    no = 0
    for h in harfler:
        no = no * 26 + (ord(h) - 64)
    return no


def _uye_oku(zf: zipfile.ZipFile, ad: str, kalan: list[int]) -> bytes:
    try:
        bilgi = zf.getinfo(ad)
    except KeyError as hata:
        raise ValueError(OKUNAMADI) from hata
    if bilgi.flag_bits & 0x1:  # şifreli üye
        raise ValueError(OKUNAMADI)
    with zf.open(bilgi) as dosya:
        veri = dosya.read(kalan[0] + 1)  # başlıktaki boyuta güvenilmez
    if len(veri) > kalan[0]:
        raise ValueError("Dosyanın açılmış boyutu çok büyük.")
    kalan[0] -= len(veri)
    _dtd_reddet(veri)
    return veri


GUVENSIZ = "Dosya güvenli olmayan XML içeriyor."


def _dtd_reddet(veri: bytes) -> None:
    """DOCTYPE/ENTITY bildirimini kodlamadan bağımsız reddeder.

    Bayt araması UTF-16 gibi kodlamalarla atlatılabildiği için belge önce expat'ten,
    DTD işleyicileri hata atacak biçimde geçirilir. Ayrıca yalnız UTF-8 kabul edilir.
    """
    if veri.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in veri:
        raise ValueError(GUVENSIZ)
    bildirim = re.match(rb"\s*<\?xml[^>]*encoding\s*=\s*[\"']([^\"']+)", veri.removeprefix(b"\xef\xbb\xbf"))
    if bildirim and bildirim.group(1).lower().replace(b"_", b"-") not in (b"utf-8", b"utf8"):
        raise ValueError(GUVENSIZ)
    if re.search(rb"<!DOCTYPE|<!ENTITY", veri, re.I):
        raise ValueError(GUVENSIZ)

    class _Dtd(Exception):
        pass

    def reddet(*_):
        raise _Dtd

    ayristirici = expat.ParserCreate()
    ayristirici.StartDoctypeDeclHandler = reddet
    ayristirici.EntityDeclHandler = reddet
    try:
        ayristirici.Parse(veri, True)
    except _Dtd as hata:
        raise ValueError(GUVENSIZ) from hata
    except expat.ExpatError as hata:
        raise ValueError(OKUNAMADI) from hata


def _xml(veri: bytes):
    try:
        # DOCTYPE/ENTITY _uye_oku'da reddedildi; varlık genişletmesi olmadan expat güvenlidir.
        return ET.fromstring(veri)  # noqa: S314
    except ET.ParseError as hata:
        raise ValueError(OKUNAMADI) from hata


def _metin(oge) -> str:
    """<si>/<is> içindeki bütün <t>'leri birleştirir; fonetik (<rPh>) parçaları atlanır."""
    fonetik = {id(t) for r in oge.iter(_ANA + "rPh") for t in r.iter(_ANA + "t")}
    return "".join((t.text or "") for t in oge.iter(_ANA + "t") if id(t) not in fonetik)


def _sayi(deger: str) -> str:
    """Sayısal hücre: tam sayıysa ".0" atılır ("1047.0" → "1047", "1.047E3" → "1047")."""
    try:
        sayi = float(deger)
    except ValueError:
        return deger
    if sayi.is_integer() and abs(sayi) < 1e15:
        return str(int(sayi))
    return deger


def oku_ayrintili(veri: bytes) -> tuple[str, list[list[str]]]:
    """(ilk sayfanın adı, satırlar). satirlar[i] = (i+1). satır; eksik satır/hücre '' ile doldurulur.

    Okunamayan, şifreli, zip olmayan dosyada kullanıcıya gösterilecek iletiyle ValueError.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(veri))
    except (zipfile.BadZipFile, ValueError, OSError) as hata:
        raise ValueError(OKUNAMADI) from hata
    with zf:
        uyeler = zf.infolist()
        if len(uyeler) > UYE_SINIRI:
            raise ValueError("Dosyada çok fazla parça var.")
        if sum(u.file_size for u in uyeler) > ACILMIS_SINIR:
            raise ValueError("Dosyanın açılmış boyutu çok büyük.")
        kalan = [ACILMIS_SINIR]
        try:
            kitap = _xml(_uye_oku(zf, "xl/workbook.xml", kalan))
            iliskiler = _xml(_uye_oku(zf, "xl/_rels/workbook.xml.rels", kalan))
            sayfa = next(iter(kitap.iter(_ANA + "sheet")), None)
            if sayfa is None:
                raise ValueError(OKUNAMADI)
            sayfa_adi = sayfa.get("name", "")
            hedef = None
            for r in iliskiler.iter(_REL + "Relationship"):
                if r.get("Id") == sayfa.get(_REL_BELGE):
                    hedef = r.get("Target", "")
            if not hedef:
                raise ValueError(OKUNAMADI)
            yol = hedef.lstrip("/") if hedef.startswith("/") else posixpath.normpath(posixpath.join("xl", hedef))
            if yol.startswith("..") or not yol.startswith("xl/"):
                raise ValueError(OKUNAMADI)
            paylasilan: list[str] = []
            if "xl/sharedStrings.xml" in zf.namelist():
                for si in _xml(_uye_oku(zf, "xl/sharedStrings.xml", kalan)).iter(_ANA + "si"):
                    paylasilan.append(_metin(si))
            sayfa_xml = _xml(_uye_oku(zf, yol, kalan))
        except ValueError:
            raise
        except (zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError, OSError, EOFError) as hata:
            raise ValueError(OKUNAMADI) from hata
        except Exception as hata:  # bozuk dosyada 500 yerine kullanıcı iletisi
            raise ValueError(OKUNAMADI) from hata
    satirlar: dict[int, dict[int, str]] = {}
    sonraki_satir = 1
    for satir in sayfa_xml.iter(_ANA + "row"):
        try:
            no = int(satir.get("r") or sonraki_satir)
        except ValueError:
            no = sonraki_satir
        sonraki_satir = no + 1
        if no > SATIR_SINIRI:
            raise ValueError("Dosyada çok fazla satır var.")
        hucreler = satirlar.setdefault(no, {})
        sonraki_sutun = 1
        for c in satir.iter(_ANA + "c"):
            eslesme = _ADRES.match(c.get("r") or "")
            sutun = _sutun_no(eslesme.group(1)) if eslesme else sonraki_sutun
            sonraki_sutun = sutun + 1
            if sutun > SUTUN_SINIRI:
                continue
            tur = c.get("t", "n")
            v = c.find(_ANA + "v")
            ham = v.text if v is not None and v.text is not None else ""
            if tur == "s":
                try:
                    deger = paylasilan[int(ham)]
                except (ValueError, IndexError):
                    deger = ""
            elif tur == "inlineStr":
                ic = c.find(_ANA + "is")
                deger = _metin(ic) if ic is not None else ""
            elif tur in ("str", "b", "e"):
                deger = ham
            else:
                deger = _sayi(ham) if ham else ""
            hucreler[sutun] = deger
    if not satirlar:
        return sayfa_adi, []
    son = max(satirlar)
    sonuc = []
    for no in range(1, son + 1):
        hucreler = satirlar.get(no, {})
        genislik = max(hucreler) if hucreler else 0
        sonuc.append([hucreler.get(s, "") for s in range(1, genislik + 1)])
    return sayfa_adi, sonuc


def oku(veri: bytes) -> list[list[str]]:
    """İlk sayfa, satır satır (Aşama 5 arayüzü; değişmez)."""
    return oku_ayrintili(veri)[1]
