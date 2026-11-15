"""Tema motoru: kontrast güvencesi, renk doğrulama, tema.css ve stil.css varsayılanları."""

from __future__ import annotations

import random
import re
from pathlib import Path

from tahta_sunucu import tema

HEX = re.compile(r"^#[0-9a-f]{6}$")
UC_RENKLER = ["#000000", "#ffffff", "#ffff00", "#00ffff", "#ff0000", "#808080", "#fde047", "#f59e0b"]


def test_tema_her_renkte_kontrast_guvenli():
    zar = random.Random(2026)  # noqa: S311 (test verisi; şifreleme değil)
    renkler = UC_RENKLER + [f"#{zar.randrange(0x1000000):06x}" for _ in range(300)]
    for ana in renkler:
        for vurgu in (None, "#b45309", "#fde047", "#0e7490"):
            t = tema.uret(ana, vurgu)
            for satir in t["rapor"]:
                assert satir["oran"] >= satir["esik"] - 1e-9, (ana, vurgu, satir)
                # rapor 2 haneye yuvarlar; asıl ölçüm de eşiği tutmalı
                assert tema.kontrast(satir["on"], satir["arka"]) >= satir["esik"] - 1e-9, (ana, vurgu, satir)
            for bolum in ("acik", "koyu", "tahta"):
                for ad, deger in t[bolum].items():
                    assert HEX.match(deger), (ana, vurgu, bolum, ad, deger)
            assert set(t["tahta"]) == set(tema.TAHTA_ANAHTARLARI)
            assert len(t["rapor"]) == 35


def test_renk_dogrulama_enjeksiyonu_reddeder():
    assert tema.renk_dogrula("#abc") is None
    assert tema.renk_dogrula("red") is None
    assert tema.renk_dogrula("#12345g") is None
    assert tema.renk_dogrula("#123456;}body{x:y}") is None
    assert tema.renk_dogrula(" #123456 ") == "#123456"
    assert tema.renk_dogrula("#ABCDEF") == "#abcdef"
    assert tema.renk_dogrula(None) is None


def test_tema_css_yalniz_hex_icerir():
    for ana, vurgu in (("#24507a", "#b45309"), ("#fde047", None), ("#000000", "#ffffff")):
        metin = tema.css_metni(ana, vurgu)
        govde = re.sub(r"/\*.*?\*/", "", metin, flags=re.S).strip()
        assert govde.startswith(":root{") and govde.endswith("}")
        ic = govde[len(":root{") : -1]
        assert "{" not in ic and "}" not in ic
        bildirimler = ic.split(";")
        assert len(bildirimler) == 2 * len(tema.WEB_ANAHTARLARI) + len(tema.TAHTA_ANAHTARLARI)
        for bildirim in bildirimler:
            ad, deger = bildirim.split(":")
            assert re.fullmatch(r"--[a-z0-9-]+", ad), bildirim
            assert HEX.match(deger), bildirim


def test_bas_harfler_turkce():
    assert tema.bas_harfler("Deneme Anadolu Lisesi") == "DA"
    assert tema.bas_harfler("ilçe imam hatip") == "İİ"
    assert tema.bas_harfler("ırmak lisesi") == "IL"
    assert tema.bas_harfler("100. Yıl Ortaokulu") == "YO"
    assert tema.bas_harfler("") == ""
    assert tema.bas_harfler(None) == ""


def test_stil_varsayilanlari_motorla_ayni():
    stil = (Path(tema.__file__).resolve().parent / "statik" / "stil.css").read_text(encoding="utf-8")
    bulunan = dict(re.findall(r"(--(?:[a-z0-9-]+-[ak]|t-[a-z0-9-]+))\s*:\s*(#[0-9a-f]{6})\b", stil))
    beklenen = dict(tema.css_degiskenleri(tema.varsayilan()))
    assert bulunan == beklenen


def test_tema_surumu_renge_bagli():
    assert tema.surum("#24507a", None) != tema.surum("#24507a", "#b45309")
    assert len(tema.surum("#24507a", None)) == 12
