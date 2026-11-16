"""Tahta ajanının süreli program kilidi (Aşama 3 şartnamesi testleri 30-34 ve ekleri)."""

from __future__ import annotations

import hashlib
import json

import pytest


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_AJAN_DIZIN", str(tmp_path / "ayar"))
    monkeypatch.setenv("TAHTA_AJAN_DURUM", str(tmp_path / "durum"))
    from tahta_ajan import servis as servis_mod

    monkeypatch.setattr(servis_mod.sistem, "kapat", lambda: "benzetim")
    monkeypatch.setattr(servis_mod.sistem, "yeniden_baslat", lambda: "benzetim")
    monkeypatch.setattr(servis_mod.sistem, "etkin_oturum", lambda: {"sinif": "ogretmen"})
    monkeypatch.setattr(servis_mod.sistem, "acik_sure", lambda: 100)
    saat = {"m": 1000.0}
    monkeypatch.setattr(servis_mod.time, "monotonic", lambda: saat["m"])

    def yeni():
        s = servis_mod.Servis()
        s.gelen = []
        s.ekranlar[1] = {"gonder": s.gelen.append, "bilgi": {"arayuz": "gtk3"}}
        s.bildirilen = 0

        def bildir():
            s.bildirilen += 1

        s.bildir = bildir
        return s

    return yeni, saat


PROGRAM = {"kaynak": "program", "sure_sn": 480, "neden": "Teneffüs", "acilis": "10:40"}


def kilitle(servis, **veri):
    return servis.komut_uygula({"tur": "kilitle", "veri": dict(PROGRAM, **veri)})


def test_program_kilidi_sure_dolunca_sunucusuz_acilir(ortam):
    yeni, saat = ortam
    servis = yeni()
    basarili, cikti = kilitle(servis)
    assert basarili and "Program kilidi" in cikti
    gorunum = servis.gorunum()
    assert gorunum["kilitli"] and gorunum["kilit_kaynak"] == "program"
    assert gorunum["kilit_neden"] == "Teneffüs" and gorunum["kilit_acilis"] == "10:40"
    ozet = servis.durum_ozeti()
    assert ozet["kilit_kaynak"] == "program" and ozet["kilit_kalan"] == 480
    assert "program_kilidi" in ozet["yetenekler"]

    saat["m"] += 479
    assert servis._program_suresi_denetle() is False and servis.kilitli
    saat["m"] += 1
    # Sunucu yok sayılır: istemci hiç kurulmadı, açma tamamen tahtadadır.
    assert servis._program_suresi_denetle() is True
    assert servis.kilitli is False and servis.kilit_kaynak is None
    assert "Program kilidi süresi doldu; tahta açıldı." in servis.olaylar
    assert servis.gelen[-1]["kilitli"] is False and servis.bildirilen == 1
    ozet = servis.durum_ozeti()
    assert ozet["kilit_kaynak"] is None and ozet["kilit_kalan"] is None


def test_program_kilidi_suresi_sekiz_saati_gecmez_ve_gecersiz_veri_suzulur(ortam):
    yeni, _ = ortam
    servis = yeni()
    kilitle(servis, sure_sn=10**9, neden="<b>9/A Ayşe</b>", acilis="25:99")
    assert servis.kilit_kalan() == 8 * 3600
    gorunum = servis.gorunum()
    assert gorunum["kilit_neden"] == "Teneffüs" and gorunum["kilit_acilis"] == ""

    servis2 = yeni()
    assert kilitle(servis2, sure_sn=0) == (True, "Kilit süresi geçmiş; uygulanmadı.")
    assert servis2.kilitli is False


def test_program_acmasi_idare_kilidine_dokunmaz(ortam):
    yeni, _ = ortam
    servis = yeni()
    servis.komut_uygula({"tur": "kilitle", "veri": {}})
    assert servis.kilit_kaynak == "idare"

    # Program kilidi idare kilidinin üstüne uygulanmaz.
    assert kilitle(servis) == (True, "Zaten idare kilidinde; uygulanmadı.")
    assert servis.kilit_kaynak == "idare" and servis.kilit_kalan() is None

    # Program açması idare kilidini açmaz.
    sonuc = servis.komut_uygula({"tur": "kilit_ac", "veri": {"kaynak": "program"}})
    assert sonuc == (True, "İdare kilidi var; uygulanmadı.")
    assert servis.kilitli is True

    # Kilit yokken program açması zararsızdır.
    servis.komut_uygula({"tur": "kilit_ac", "veri": {}})
    sonuc = servis.komut_uygula({"tur": "kilit_ac", "veri": {"kaynak": "program"}})
    assert sonuc == (True, "Program kilidi yok; uygulanmadı.")

    # Program kilidini program açması açar.
    kilitle(servis)
    assert servis.komut_uygula({"tur": "kilit_ac", "veri": {"kaynak": "program"}}) == (True, "Kilit açıldı.")
    assert servis.kilitli is False and servis.kilit_kaynak is None


def test_idare_kilidi_program_kilidini_ezer(ortam):
    yeni, saat = ortam
    servis = yeni()
    kilitle(servis)
    servis.komut_uygula({"tur": "kilitle", "veri": {}})
    assert servis.kilitli and servis.kilit_kaynak == "idare" and servis.kilit_bitis is None
    assert servis.gorunum()["kilit_neden"] == ""
    # Program süresi geçse de idare kilidi süresizdir.
    saat["m"] += 10_000
    assert servis._program_suresi_denetle() is False and servis.kilitli
    # Panelden açma her kilidi açar.
    servis.komut_uygula({"tur": "kilit_ac", "veri": {}})
    assert servis.kilitli is False


def test_program_kilidi_yeniden_baslatmada_geri_yuklenmez(ortam):
    yeni, _ = ortam
    servis = yeni()
    kilitle(servis)
    from tahta_ajan import ayar

    assert ayar.durum_oku()["kilit_kaynak"] == "program"
    yeniden = yeni()
    assert yeniden.kilitli is False and yeniden.kilit_kaynak is None

    # İdare kilidi (ve kaynaksız eski kayıt) geri yüklenir.
    yeniden.komut_uygula({"tur": "kilitle", "veri": {}})
    assert yeni().kilit_kaynak == "idare"
    durum = ayar.durum_oku()
    durum.pop("kilit_kaynak")
    ayar.durum_yaz(durum)
    eski = yeni()
    assert eski.kilitli is True and eski.kilit_kaynak == "idare"


def test_kodla_acma_program_kilidini_temizler(ortam):
    yeni, _ = ortam
    servis = yeni()
    tuz = "00" * 16
    servis.kilit_kodu = {
        "tuz": tuz,
        "tur": 1000,
        "ozet": hashlib.pbkdf2_hmac("sha256", b"2468", bytes.fromhex(tuz), 1000).hex(),
    }
    kilitle(servis)
    servis.ekran_mesaji(1, {"tur": "kod", "kod": "2468"})
    assert servis.kilitli is False and servis.kilit_kaynak is None and servis.kilit_bitis is None
    assert "Program kilidi tahtadan kodla açıldı." in servis.olaylar
    assert servis.gorunum()["kilit_neden"] == ""


def test_cevrimdisi_acma_program_kilidini_temizler(ortam):
    yeni, _ = ortam
    servis = yeni()
    kilitle(servis)
    servis.son_temas -= 1000  # sunucu 90 sn'den uzun yok
    servis.ekran_mesaji(1, {"tur": "cevrimdisi_ac"})
    assert servis.kilitli is False and servis.kilit_kaynak is None


def test_program_kilidi_ekran_gorunumunde_sir_ve_kisi_yok(ortam):
    yeni, _ = ortam
    servis = yeni()
    servis.kilit_kodu = {"tuz": "aa" * 16, "ozet": "bb" * 32, "tur": 1000}
    servis.yapi = {"anahtar": "gizli-anahtar-degeri", "tahta_id": 1}
    kilitle(servis, neden="Bu saatte bu derslikte ders yok")
    metin = json.dumps(servis.gorunum(), ensure_ascii=False)
    assert "Bu saatte bu derslikte ders yok" in metin
    for yasak in ("aa" * 16, "bb" * 32, "gizli-anahtar-degeri", "kilit_kodu"):
        assert yasak not in metin


def test_ekran_program_bilgisi_ve_saat_eki():
    from tahta_ajan import ekran

    assert ekran.saat_eki("10:40") == "10:40'ta"
    assert ekran.saat_eki("10:30") == "10:30'da"
    assert ekran.saat_eki("10:10") == "10:10'da"
    assert ekran.saat_eki("12:50") == "12:50'de"
    assert ekran.saat_eki("13:05") == "13:05'te"
    assert ekran.saat_eki("09:46") == "09:46'da"
    assert ekran.saat_eki("11:00") == "11:00'de"
    assert ekran.saat_eki("10:00") == "10:00'da"
    assert ekran.saat_eki("09:00") == "09:00'da"
    assert ekran.saat_eki("08:20") == "08:20'de"
    durum = {"kilit_kaynak": "program", "kilit_neden": "Teneffüs", "kilit_acilis": "10:40"}
    assert ekran.program_bilgisi(durum) == "Teneffüs · Tahta 10:40'ta açılır."
    assert ekran.program_bilgisi(dict(durum, kilit_acilis="")).startswith("Teneffüs · Tahta ders saatinde")
    assert ekran.program_bilgisi(dict(durum, kilit_kaynak="idare")) == ""
    assert ekran.program_bilgisi({}) == ""  # eski servis alanı göndermez
    assert b"#program-bilgi" in ekran.STIL_OLCU
