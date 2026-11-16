"""0.10.0 — güvenilmeyen XML ortak denetimi (`guvenli_xml`): DTD/varlık/XXE reddi, kodlama düzeltme ve xlsx'in
taşınmadan sonra aynı davranması. Bütün örnekler uydurmadır."""

from __future__ import annotations

import pytest

from tahta_sunucu import guvenli_xml, xlsx

OKUNAMADI = "okunamadı"


@pytest.mark.parametrize(
    "veri",
    [
        b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY x "y">]><a>&x;</a>',  # iç alt küme
        b'<?xml version="1.0"?><!DOCTYPE a SYSTEM "file:///etc/passwd"><a/>',  # dış varlık
        b'<!DOCTYPE a [<!ENTITY % p SYSTEM "http://ornek.invalid/p.dtd"> %p;]><a/>',  # parametre varlığı
        b'<!DOCTYPE lol [<!ENTITY a "aaaa"><!ENTITY b "&a;&a;&a;&a;">]><lol>&b;</lol>',  # billion laughs
        "<?xml version='1.0' encoding='UTF-16'?><!DOCTYPE a><a/>".encode("utf-16"),  # UTF-16 ile gizlenmiş DOCTYPE
        b'<?xml version="1.0" encoding="UTF-16"?><a/>',  # UTF-8 dışı bildirim
        b"<a>\x00</a>",
    ],
)
def test_guvenli_xml_doctype_entity_xxe_billion_laughs_reddedilir(veri):
    with pytest.raises(ValueError, match="güvenli olmayan"):
        guvenli_xml.dtd_reddet(veri, OKUNAMADI)


def test_guvenli_xml_bom_lu_utf8_kabul_bozuk_xml_okunamadi():
    guvenli_xml.dtd_reddet(b'\xef\xbb\xbf<?xml version="1.0" encoding="utf-8"?><a b="\xc3\xa7"/>', OKUNAMADI)
    with pytest.raises(ValueError, match=OKUNAMADI):
        guvenli_xml.dtd_reddet(b"<a><b></a>", OKUNAMADI)


def test_guvenli_xml_windows_1254_cevrilir_utf16_reddedilir():
    ham = '<?xml version="1.0" encoding="windows-1254"?><timetable n="Çalışma Şubesi"/>'.encode("cp1254")
    duz = guvenli_xml.kodlama_duzelt(ham)
    assert duz.startswith(b'<?xml version="1.0" encoding="UTF-8"?>')
    assert "Çalışma Şubesi" in duz.decode("utf-8")
    guvenli_xml.dtd_reddet(duz, OKUNAMADI)
    iso = '<?xml version="1.0" encoding="ISO-8859-9"?><a n="ğ"/>'.encode("iso-8859-9")
    assert "ğ" in guvenli_xml.kodlama_duzelt(iso).decode("utf-8")
    assert guvenli_xml.kodlama_duzelt(b"\xef\xbb\xbf<a/>") == b"<a/>"
    for kotu in ("<a/>".encode("utf-16"), b'<?xml version="1.0" encoding="shift_jis"?><a/>'):
        with pytest.raises(ValueError, match="UTF-8"):
            guvenli_xml.kodlama_duzelt(kotu)


def test_xlsx_dtd_reddet_tasindiktan_sonra_davranis_ayni():
    with pytest.raises(ValueError) as hata:
        xlsx._dtd_reddet(b'<!DOCTYPE a [<!ENTITY x "y">]><a/>')
    assert str(hata.value) == xlsx.GUVENSIZ == "Dosya güvenli olmayan XML içeriyor."
    with pytest.raises(ValueError) as hata:
        xlsx._dtd_reddet(b"<a><b></a>")
    assert str(hata.value) == xlsx.OKUNAMADI
    xlsx._dtd_reddet(b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><a/>')
