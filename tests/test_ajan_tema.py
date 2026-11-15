"""Tahta ajanının okul kimliği (tema, logo, tahta adı) davranışı."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import struct
import zlib

import pytest


def png(en: int = 128, boy: int = 128, boyut: int | None = None) -> bytes:
    """Testte üretilen en küçük geçerli PNG (tek renk); boyut verilirse sona dolgu parçası eklenir."""

    def parca(tur: bytes, veri: bytes) -> bytes:
        return struct.pack(">I", len(veri)) + tur + veri + struct.pack(">I", zlib.crc32(tur + veri))

    ham = b"".join(b"\x00" + b"\x24\x50\x7a" * en for _ in range(boy))
    veri = (
        b"\x89PNG\r\n\x1a\n"
        + parca(b"IHDR", struct.pack(">IIBBBBB", en, boy, 8, 2, 0, 0, 0))
        + parca(b"IDAT", zlib.compress(ham))
        + parca(b"IEND", b"")
    )
    if boyut and boyut > len(veri):
        veri = veri[:-12] + parca(b"teSt", b"\x00" * (boyut - len(veri) - 12)) + veri[-12:]
    return veri


class SahteIstemci:
    def __init__(self, yanitlar: dict):
        self.yanitlar = yanitlar
        self.istekler = []

    def istek(self, yontem, yol, govde=None, zaman_asimi=15, ham=False):
        self.istekler.append((yontem, yol))
        kod, veri = self.yanitlar.get(yol, (404, b""))
        return kod, veri, {}


@pytest.fixture
def servis_ortami(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_AJAN_DIZIN", str(tmp_path / "ayar"))
    monkeypatch.setenv("TAHTA_AJAN_DURUM", str(tmp_path / "durum"))
    from tahta_ajan import ayar, servis

    def yeni(logo: bytes | None = None):
        s = servis.Servis()
        s.istemci = SahteIstemci({"/ajan/logo": (200, logo)} if logo is not None else {})
        return s

    return yeni, ayar


def tema_yaniti(palet=None, sha=None, ad="9-A", derslik="Z-12") -> dict:
    from tahta_ajan import ayar

    return {
        "durum": "onayli",
        "ayar": {
            "okul_adi": "Deneme Lisesi",
            "tema": palet if palet is not None else dict(ayar.VARSAYILAN_PALET, ana="#9e4148"),
            "logo_sha256": sha,
            "tahta": {"ad": ad, "derslik": derslik},
        },
    }


def test_ajan_tema_ve_logo_isler(servis_ortami):
    yeni, ayar = servis_ortami
    logo = png()
    sha = hashlib.sha256(logo).hexdigest()
    s = yeni(logo)
    gelen = []
    s.ekranlar[1] = {"gonder": gelen.append, "bilgi": {"arayuz": "gtk3"}}

    s._yanit_isle(tema_yaniti(sha=sha))

    assert ayar.logo_yolu().read_bytes() == logo
    gorunum = s.gorunum()
    assert gorunum["tema"]["ana"] == "#9e4148" and set(gorunum["tema"]) == set(ayar.PALET_ANAHTARLARI)
    assert gorunum["logo_sha256"] == sha
    assert (gorunum["tahta_adi"], gorunum["derslik"]) == ("9-A", "Z-12")
    marka = s.marka_mesaji()
    assert marka["sha256"] == sha and base64.b64decode(marka["logo"]) == logo
    # Ekrana önce logo, sonra durum gider.
    assert [m["tur"] for m in gelen] == ["marka", "durum"]

    # Yeniden açılan servis logoyu ve temayı diskten tanır.
    s2 = yeni()
    assert s2.logo == logo and s2.logo_sha == sha and s2.tema["ana"] == "#9e4148"
    assert s2.gorunum()["tahta_adi"] == "9-A"

    # Aynı özet yeniden gelirse indirilmez; logo kaldırılınca dosya silinir.
    s._yanit_isle(tema_yaniti(sha=sha))
    assert len(s.istemci.istekler) == 1
    s._yanit_isle(tema_yaniti(sha=None))
    assert not ayar.logo_yolu().exists() and s.gorunum()["logo_sha256"] is None
    assert s.marka_mesaji() == {"tur": "marka", "sha256": None, "logo": None}


@pytest.mark.parametrize(
    "bozuk",
    ["sha_tutmaz", "svg", "buyuk"],
)
def test_ajan_bozuk_logo_saklanmaz(servis_ortami, bozuk):
    yeni, ayar = servis_ortami
    eski = png(96, 96)
    eski_sha = hashlib.sha256(eski).hexdigest()
    s = yeni(eski)
    s._yanit_isle(tema_yaniti(sha=eski_sha))
    assert s.logo_sha == eski_sha

    if bozuk == "sha_tutmaz":
        veri, sha = png(64, 64), "0" * 64
    elif bozuk == "svg":
        veri = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
        sha = hashlib.sha256(veri).hexdigest()
    else:
        veri = png(boyut=300 * 1024)
        sha = hashlib.sha256(veri).hexdigest()
    s.istemci = SahteIstemci({"/ajan/logo": (200, veri)})
    s._yanit_isle(tema_yaniti(sha=sha))

    assert s.logo_sha == eski_sha and s.logo == eski
    assert ayar.logo_yolu().read_bytes() == eski
    # Başarısız denemeden sonra 60 sn içinde yeniden indirilmez.
    s._yanit_isle(tema_yaniti(sha=sha))
    assert len(s.istemci.istekler) == 1


def test_ajan_gecersiz_tema_varsayilana_duser(servis_ortami):
    _, ayar = servis_ortami
    palet = ayar.palet_dogrula({"zemin": "red", "ana": "#12345g", "metin": "#ABCDEF;}", "vurgu": "#00ff00"})
    assert palet["zemin"] == ayar.VARSAYILAN_PALET["zemin"]
    assert palet["ana"] == ayar.VARSAYILAN_PALET["ana"]
    assert palet["metin"] == ayar.VARSAYILAN_PALET["metin"]
    assert palet["vurgu"] == "#00ff00"
    assert set(palet) == set(ayar.PALET_ANAHTARLARI)
    assert ayar.palet_dogrula("#123456") is None and ayar.palet_dogrula(None) is None


def test_gorunume_sir_girmez(servis_ortami):
    yeni, _ = servis_ortami
    logo = png()
    s = yeni(logo)
    s.kilit_kodu = {"tuz": "aa" * 16, "ozet": "bb" * 32, "tur": 1000}
    s.yapi = {"anahtar": "gizli-anahtar-degeri", "tahta_id": 1}
    s._yanit_isle(tema_yaniti(sha=hashlib.sha256(logo).hexdigest()))
    for metin in (json.dumps(s.gorunum()), json.dumps(s.marka_mesaji())):
        for yasak in ("tuz", "ozet", "anahtar", "kilit_kodu", "aa" * 16, "bb" * 32, "gizli-anahtar-degeri"):
            assert yasak not in metin
    assert s.gorunum()["kod_var"] is True


def test_ajan_varsayilan_paleti_sunucuyla_ayni():
    from tahta_ajan import ayar
    from tahta_sunucu import tema

    assert ayar.VARSAYILAN_PALET == tema.varsayilan()["tahta"]
    assert ayar.PALET_ANAHTARLARI == tema.TAHTA_ANAHTARLARI


def test_ekran_renk_stili_ascii_ve_tam():
    from tahta_ajan import ayar, ekran  # gi gerekmeden içe aktarılabilmeli

    palet = dict(ayar.VARSAYILAN_PALET, ana="#9e4148", vurgu="#d4a017")
    stil = ekran.renk_stili(palet)
    stil.encode("ascii")
    ekran.STIL_OLCU.decode("ascii")
    for deger in palet.values():
        assert deger in stil
    assert re.search(r"^button label \{", stil, re.M)
    assert re.search(r"^#ana-dugme label \{", stil, re.M)
    assert "#fca5a5" in stil  # kapatma başlığı markadan bağımsız
    assert "color" not in ekran.STIL_OLCU.decode().replace("border-bottom-width", "")
    # Geçersiz palet stile sızmaz.
    assert "red" not in ekran.renk_stili({"zemin": "red;}"})
    assert ekran.logo_olcusu(512, 512) == (96, 96)
    assert ekran.logo_olcusu(2048, 512) == (320, 80)
    assert ekran.logo_olcusu(0, 10) == (0, 0)


def test_ajan_eski_sunucu_yanitinda_temaya_dokunmaz(servis_ortami):
    yeni, ayar = servis_ortami
    logo = png()
    sha = hashlib.sha256(logo).hexdigest()
    s = yeni(logo)
    s._yanit_isle(tema_yaniti(sha=sha))
    tema, bilgi = dict(s.tema), dict(s.tahta_bilgi)

    s._yanit_isle({"durum": "onayli", "ayar": {"okul_adi": "Deneme Lisesi", "kilit_kodu": None}})

    assert s.tema == tema and s.tahta_bilgi == bilgi and s.logo_sha == sha
    assert ayar.logo_yolu().read_bytes() == logo
    # Hiç tema almamış ajan varsayılan paletle çizer.
    s.tema = None
    assert s.gorunum()["tema"] == ayar.VARSAYILAN_PALET


def test_ajan_logo_bekleme_saat_geri_alininca_takilmaz(servis_ortami, monkeypatch):
    """Yeniden deneme süresi duvar saatiyle değil time.monotonic() ile ölçülür."""
    import time as zaman

    yeni, ayar = servis_ortami
    logo = png()
    sha = hashlib.sha256(logo).hexdigest()
    s = yeni()  # ilk deneme 404: başarısız
    s._yanit_isle(tema_yaniti(sha=sha))
    assert s.logo_sha is None and len(s.istemci.istekler) == 1

    # Tahta saati bir yıl geri alınır (NTP düzeltmesi); tekdüze saat 61 sn ilerler.
    duvar, tekduze = zaman.time(), zaman.monotonic()
    monkeypatch.setattr(zaman, "time", lambda: duvar - 365 * 86400)
    monkeypatch.setattr(zaman, "monotonic", lambda: tekduze + 61)
    s.istemci = SahteIstemci({"/ajan/logo": (200, logo)})
    s._yanit_isle(tema_yaniti(sha=sha))
    assert s.logo_sha == sha and ayar.logo_yolu().read_bytes() == logo
