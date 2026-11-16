"""Hedef çözümleme, tahta nitelikleri ve ortak metin yardımcıları."""

from __future__ import annotations

import json
from urllib.parse import quote

import pytest
from yardimci import SAHTE_TC, kur_ve_gir, sorgu, tahta_ekle


@pytest.fixture()
def tahtalar(panel, tahta):
    """Uydurma okul: A Blok zemin (9, sabah), A Blok 1. kat (10, öğle), B Blok 1. kat (9/10, her ikisi), niteliksiz."""
    kur_ve_gir(panel)
    a = tahta_ekle(panel, tahta, "Z-01", bina="A Blok", kat="0", duzey="9", devre="sabah")
    b = tahta_ekle(panel, tahta, "101", bina="A Blok", kat="1", duzey="10", devre="ogle")
    panel.post("/ekle", data={"eylem": "ac"})
    c = tahta_ekle(panel, tahta, "Fizik lab", bina="b blok ", kat="1", duzey=["9", "10"], devre="her_ikisi")
    d = tahta_ekle(panel, tahta, "Niteliksiz")
    return {ad: int(h["X-Tahta-Id"]) for ad, h in (("a", a), ("b", b), ("c", c), ("d", d))}


def coz(hedef_):
    from tahta_sunucu import hedef, vt

    with vt.islem() as b:
        return [t["ad"] for t in hedef.coz(b, hedef.dogrula(hedef_))]


def test_hedef_tumu_yalniz_onayli_tahtalar(tahtalar, panel, tahta):
    # Onay bekleyen ve kaldırılan tahta hedefe girmez.
    panel.post("/ekle", data={"eylem": "ac"})
    kod = panel.get("/ekle").text.split('class="buyuk-kod">')[1].split("<")[0]
    tahta.post("/ajan/kaydol", json={"kod": kod, "makine_adi": "bekleyen"})
    panel.post(f"/tahta/{tahtalar['d']}/kaydet", data={"ad": "x", "eylem": "sil"})
    assert sorted(coz({"tumu": True})) == ["101", "Fizik lab", "Z-01"]


def test_hedef_suzgec_ayni_satirda_veya_farkli_satirda_ve(tahtalar):
    assert sorted(coz({"bina": ["A Blok"]})) == ["101", "Z-01"]
    assert sorted(coz({"bina": ["a blok", "B BLOK"], "kat": [1]})) == ["101", "Fizik lab"]
    assert coz({"bina": ["A Blok"], "kat": [1], "duzey": ["9"]}) == []
    assert sorted(coz({"kat": [0, 1]})) == ["101", "Fizik lab", "Z-01"]


def test_hedef_grup_ve_acik_tahtalar_birlesime_eklenir(tahtalar, panel):
    panel.post("/gruplar", data={"eylem": "ekle", "ad": "Fen laboratuvarları"})
    grup = sorgu("SELECT id FROM tahta_grubu")[0]["id"]
    panel.post("/gruplar", data={"eylem": "uyeler", "id": grup, "tahta": [tahtalar["c"]]})
    assert sorted(coz({"gruplar": [grup], "tahtalar": [tahtalar["d"]], "bina": ["A Blok"], "kat": [0]})) == [
        "Fizik lab", "Niteliksiz", "Z-01"
    ]  # fmt: skip
    # Silinen grup ve bilinmeyen tahta kimliği sessizce düşer.
    assert coz({"gruplar": [999], "tahtalar": [999]}) == []


def test_hedef_her_ikisi_devresi_sabah_ve_ogleye_uyar(tahtalar):
    assert sorted(coz({"devre": ["sabah"]})) == ["Fizik lab", "Z-01"]
    assert sorted(coz({"devre": ["ogle"]})) == ["101", "Fizik lab"]
    assert sorted(coz({"duzey": ["9"]})) == ["Fizik lab", "Z-01"]


def test_hedef_bos_alan_hicbir_olcute_uymaz(tahtalar):
    for olcut in ({"bina": ["A Blok", "B Blok"]}, {"kat": list(range(-2, 21))}, {"duzey": ["hazirlik", "9", "10", "11", "12"]},
                  {"devre": ["sabah", "ogle", "her_ikisi"]}):  # fmt: skip
        assert "Niteliksiz" not in coz(olcut)


def test_hedef_dogrula_bozuk_json_reddeder():
    from tahta_sunucu import hedef

    for bozuk in ("{", "[]", "null", {}, {"tahtalar": []}, {"tumu": "evet"}, {"bilinmeyen": [1]},
                  {"kat": [99]}, {"duzey": ["13"]}, {"devre": ["gece"]}, {"tahtalar": ["x"]}, {"bina": "A"}):  # fmt: skip
        with pytest.raises(ValueError):
            hedef.dogrula(bozuk)
    assert hedef.dogrula('{"tumu": true, "kat": [1]}') == {"tumu": True}
    assert hedef.dogrula({"tahtalar": ["3", 3], "bina": [" A ", ""]}) == {"tahtalar": [3], "bina": ["A"]}


def test_hedef_onizleme_ucu_sayi_ve_ozet_dondurur(tahtalar, panel):
    yanit = panel.get("/api/hedef-onizleme?hedef=" + quote(json.dumps({"bina": ["A Blok"], "kat": [1, 0]})))
    veri = yanit.json()
    assert yanit.status_code == 200 and veri["sayi"] == 2
    assert veri["ozet"] == "A Blok · Zemin kat, 1. kat"
    assert {t["ad"] for t in veri["tahtalar"]} == {"Z-01", "101"} and "cevrimici" in veri["tahtalar"][0]
    assert panel.get("/api/hedef-onizleme?hedef=%7B").status_code == 400
    panel.cookies.clear()
    assert panel.get("/api/hedef-onizleme?hedef=" + quote('{"tumu":true}')).status_code == 401


def test_hedef_ozeti():
    from tahta_sunucu import hedef

    assert hedef.kat_adi(None) == "—" and hedef.kat_adi(-2) == "2. bodrum" and hedef.kat_adi(-1) == "Bodrum"
    assert hedef.kat_adi(0) == "Zemin kat" and hedef.kat_adi(3) == "3. kat"
    for metin_, beklenen in (("Zemin", 0), ("bodrum", -1), ("2. bodrum", -2), ("-2", -2), ("3. kat", 3), ("3", 3),
                             ("", None), ("'-1", -1)):  # fmt: skip
        assert hedef.kat_coz(metin_) == beklenen, metin_
    for bozuk in ("çatı", "25", "-3"):
        with pytest.raises(ValueError):
            hedef.kat_coz(bozuk)
    assert hedef.duzey_coz("Hazırlık|9") == ["hazirlik", "9"] and hedef.duzey_coz("10, 9. sınıf") == ["9", "10"]
    assert hedef.devre_coz("Öğleden sonra") == "ogle" and hedef.devre_coz("Sabah ve öğle") == "her_ikisi"
    assert hedef.subeler_coz("9-a, hazırlık b|10/İ") == ["9/A", "Hazırlık/B", "10/İ"]


def test_metin_yardimcilari():
    from tahta_sunucu import metin

    assert metin.katla("  Düzeyler  İÇ ") == "duzeyler ic"
    assert metin.sube_duzelt("10-a") == "10/A" and metin.sube_duzelt("10 ı") == "10/I" and metin.sube_duzelt("10/i") == "10/İ"
    assert metin.sube_duzelt("13/A") is None and metin.sube_duzeyi("Hazırlık/C") == "hazirlik"
    assert metin.derslik_anahtari("  D-204   Dersliği") == "d-204"
    assert sorted(["ıslak", "inci", "çam", "cam"], key=metin.tr_sirala_anahtari) == ["cam", "çam", "ıslak", "inci"]
    yazilan = metin.csv_yaz(["a", "b"], [["=1+1", "Öğle"], ["-2", "@x"]])
    assert yazilan.startswith("﻿".encode()) and b"\r\n" in yazilan
    basliklar, satirlar = metin.csv_oku(yazilan, 10_000, 10)
    assert basliklar == ["a", "b"] and satirlar == [["'=1+1", "Öğle"], ["'-2", "'@x"]]
    with pytest.raises(ValueError):
        metin.csv_oku(b"a;b\n" + b"1;2\n" * 5, 10_000, 3)


def test_tc_kimlik_denetimi():
    from tahta_sunucu import guvenlik

    assert guvenlik.tc_kimlik_var(f"Öğrenci {SAHTE_TC} derse gelsin")
    assert not guvenlik.tc_kimlik_var("Tel 12345678951")  # denetim hanesi tutmuyor
    assert not guvenlik.tc_kimlik_var("02345678950") and not guvenlik.tc_kimlik_var("123" + SAHTE_TC)
