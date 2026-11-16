"""Testler için Kelebek R5 Toplu Dağıtım Çizelgesi üretir (openpyxl çıktısını taklit eder; UYDURMA veri).

openpyxl metinleri paylaşılan dizgi (`t="s"`), sayıları `<v>` ile yazar; birleşik A1/A2 yalnız
ilk hücrede değer taşır, 3. satır boştur (XML'de hiç yer almaz).
"""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

A1 = "Deneme Anadolu Lisesi — TOPLU DAĞITIM ÇİZELGESİ"
A2 = "1. Dönem 1. Ortak Sınav · 18.11.2026 10:00 · 2026-2027 1. Dönem · Üretim: 16.11.2026 14:05"
BASLIKLAR = ("Okul No", "Ad Soyad", "Şube", "Ders", "Salon", "Koltuk No", "Durum")
# Uydurma öğrenciler (gerçek kişi değildir).
SATIRLAR = [
    ("5501", "Deniz Kaya", "9/A", "Matematik — 9. Sınıf", "10/B Dersliği", 1, ""),
    ("5547", "Ahmet Yılmaz", "9/B", "Matematik — 9. Sınıf", "10/B Dersliği", 2, ""),
    ("6603", "Elif Su Demir", "10/A", "Matematik — 10. Sınıf", "10/B Dersliği", 3, "Sabit"),
    ("5512", "Can Ak", "9/A", "Matematik — 9. Sınıf", "11/A Dersliği", 1, ""),
]
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def _harf(no: int) -> str:
    s = ""
    while no:
        no, kalan = divmod(no - 1, 26)
        s = chr(65 + kalan) + s
    return s


def r5(
    satirlar=None,
    a1: str = A1,
    a2: str = A2,
    basliklar=BASLIKLAR,
    sayfa: str = "Dagitim",
    sayisal_no: bool = False,
    satir_ici: bool = False,
    ek_xml: bytes = b"",
) -> bytes:
    """satir_ici: metinleri `inlineStr` olarak yazar; sayisal_no: okul no sayısal hücre ("5547.0")."""
    satirlar = SATIRLAR if satirlar is None else satirlar
    dizgiler: list[str] = []

    def hucre(r: int, c: int, deger) -> str:
        adres = f"{_harf(c)}{r}"
        if deger is None or deger == "":
            return ""
        if isinstance(deger, (int, float)) and not isinstance(deger, bool):
            return f'<c r="{adres}"><v>{deger}</v></c>'
        if satir_ici:
            return f'<c r="{adres}" t="inlineStr"><is><t>{escape(str(deger))}</t></is></c>'
        if deger not in dizgiler:
            dizgiler.append(deger)
        return f'<c r="{adres}" t="s"><v>{dizgiler.index(deger)}</v></c>'

    satir_xml = []
    for r, degerler in ((1, [a1]), (2, [a2]), (4, list(basliklar))):
        satir_xml.append(f'<row r="{r}">' + "".join(hucre(r, c + 1, d) for c, d in enumerate(degerler)) + "</row>")
    for i, satir in enumerate(satirlar):
        r = 5 + i
        degerler = list(satir)
        if sayisal_no and str(degerler[0]).isdigit():
            degerler[0] = float(degerler[0])
        satir_xml.append(f'<row r="{r}">' + "".join(hucre(r, c + 1, d) for c, d in enumerate(degerler)) + "</row>")
    sayfa_xml = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<worksheet xmlns="{NS}"><sheetData>'
        + "".join(satir_xml)
        + '</sheetData><mergeCells count="2"><mergeCell ref="A1:G1"/><mergeCell ref="A2:G2"/></mergeCells></worksheet>'
    ).encode()
    paylasilan = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<sst xmlns="{NS}" count="{len(dizgiler)}" '
        f'uniqueCount="{len(dizgiler)}">' + "".join(f"<si><t>{escape(d)}</t></si>" for d in dizgiler) + "</sst>"
    ).encode()
    kitap = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<workbook xmlns="{NS}" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{escape(sayfa)}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    ).encode()
    iliski = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        b'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        b'Target="/xl/worksheets/sheet1.xml"/>'
        b'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" '
        b'Target="sharedStrings.xml"/></Relationships>'
    )
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        zf.writestr("xl/workbook.xml", kitap)
        zf.writestr("xl/_rels/workbook.xml.rels", iliski)
        zf.writestr("xl/worksheets/sheet1.xml", ek_xml + sayfa_xml if ek_xml else sayfa_xml)
        if dizgiler:
            zf.writestr("xl/sharedStrings.xml", paylasilan)
    return tampon.getvalue()
