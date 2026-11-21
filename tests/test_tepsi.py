"""Bildirim alanı durum simgesi (0.21.0): saf işlevler, yoklama, gizli kip, simge dosyaları, paketleme.

pywin32 ve Tk açılmaz; Win32 kısmı yalnız kaynak taramasıyla bağlanır. Gerçek simge yalnız gerçek Windows
oturumunda elle denenir.
"""

from __future__ import annotations

import ast
import importlib.util
import queue
import re
import sys
from pathlib import Path

import pytest

from tahta_sunucu import pencere, tepsi

KOK = Path(__file__).resolve().parent.parent
DURUM = {
    "surum": "0.21.0",
    "ag_adresleri": ["https://10.20.30.40:8788"],
    "parmak_izi_kisa": "abcdef0123456789",
    "yedek_parolasi_var": True,
    "son_yedek": {"zaman": None, "basarili": None},
    "paket_imzali": False,
    "hizmet": True,
}
HIZMET_DURUMLARI = (None, "yok", *pencere.DURUMLAR)


# ---- tepsi_durumu -------------------------------------------------------------------------
def test_tepsi_durumu_simge_turu_ve_ipucu():
    assert tepsi.tepsi_durumu(DURUM, None) == ("calisiyor", "Tahta Kontrol: sunucu çalışıyor · sürüm 0.21.0")
    assert tepsi.tepsi_durumu(None, "START_PENDING") == ("bekleniyor", "Tahta Kontrol: sunucu başlatılıyor")
    assert tepsi.tepsi_durumu(None, "RUNNING")[0] == "bekleniyor"
    assert tepsi.tepsi_durumu(None, "STOPPED") == ("durdu", "Tahta Kontrol: sunucu hizmeti durdu")
    assert tepsi.tepsi_durumu(None, "STOP_PENDING")[0] == "durdu"
    assert tepsi.tepsi_durumu(None, "yok") == ("durdu", "Tahta Kontrol: sunucu hizmeti kurulu değil")
    assert tepsi.tepsi_durumu(None, None) == ("bekleniyor", "Tahta Kontrol: sunucunun durumu okunamadı")
    assert tepsi.tepsi_durumu(None, None, okundu=False) == ("bekleniyor", "Tahta Kontrol: durum okunuyor")


def test_ipucunda_ag_adresi_parmak_izi_ve_okul_adi_yok_ve_127_karakteri_gecmez():
    sahte = {
        **DURUM,
        "okul_adi": "Uydurma Deneme Lisesi",
        "surum": "0.21.0 https://10.20.30.40:8788 " + "x" * 300,  # kalıba uymayan sürüm kullanılmaz
    }
    for durum in (DURUM, sahte, None):
        for hizmet in HIZMET_DURUMLARI:
            tur, ipucu = tepsi.tepsi_durumu(durum, hizmet)
            assert tur in tepsi.TURLER
            assert len(ipucu) <= tepsi.IPUCU_EN_UZUN
            assert ipucu.startswith("Tahta Kontrol: ")
            assert not re.search(r"\d+\.\d+\.\d+\.\d+|https?:|abcdef|Uydurma|Lisesi", ipucu), ipucu
    assert tepsi.tepsi_durumu(sahte, None)[1].endswith(f"sürüm {pencere.__version__}")
    assert len(tepsi._ipucu("ş" * 400)) == tepsi.IPUCU_EN_UZUN


# ---- menü ---------------------------------------------------------------------------------
def test_menu_ogeleri_hizmeti_baslat_yalniz_durmusken():
    def anahtarlar(kip, hizmet=None):
        return [a for a, _, _ in tepsi.menu_ogeleri(kip, hizmet)]

    assert anahtarlar("calisiyor") == ["panel", "goster", "-", "cik"]
    assert anahtarlar("hizmet_calismiyor", "STOPPED") == ["panel", "goster", "baslat", "-", "cik"]
    for hizmet in ("RUNNING", "START_PENDING", "STOP_PENDING", None):
        assert "baslat" not in anahtarlar("hizmet_calismiyor", hizmet)
    for kip in ("okunuyor", "bekleniyor", "kurulu_degil", "calisiyor"):
        assert "baslat" not in anahtarlar(kip, "STOPPED")
    etiketler = {a: (e, etkin) for a, e, etkin in tepsi.menu_ogeleri("calisiyor")}
    assert etiketler["panel"] == ("Paneli aç", True) and etiketler["goster"] == ("Durumu göster", True)
    assert etiketler["cik"] == ("Çık", True)
    assert dict((a, etkin) for a, _, etkin in tepsi.menu_ogeleri("kurulu_degil"))["panel"] is False


def test_tepsi_paneli_yalniz_yerel_adresle_acar():
    assert tepsi.PANEL_ADRESI == "http://127.0.0.1:8787"


# ---- geçiş bildirimi ----------------------------------------------------------------------
def test_gecis_bildirimi_yalniz_calisiyordan_durduya_bir_kez():
    kararli = None
    balonlar = []
    for tur in ["bekleniyor", "calisiyor", "calisiyor", "bekleniyor", "durdu", "durdu", "bekleniyor", "durdu",
                "calisiyor", "durdu"]:
        metin = tepsi.gecis_bildirimi(kararli, tur)
        if metin:
            balonlar.append(metin)
        kararli = tepsi.kararli_tur(kararli, tur)
    # çalışıyor → (bekleniyor) → durdu: bir balon; durdu → durdu tekrar etmez; yeniden çalışıp durunca bir daha
    assert balonlar == [tepsi.BALON_DURDU, tepsi.BALON_DURDU]
    assert tepsi.gecis_bildirimi(None, "durdu") is None  # açılışta zaten durmuşsa balon yok
    assert tepsi.gecis_bildirimi("durdu", "calisiyor") is None
    assert tepsi.gecis_bildirimi("calisiyor", "calisiyor") is None


# ---- yoklama ------------------------------------------------------------------------------
class Saat:
    def __init__(self):
        self.an = 1000.0

    def __call__(self):
        return self.an


def test_izleyici_degisimi_kuyruga_tek_olay_olarak_koyar():
    olaylar: queue.Queue = queue.Queue()
    sira = [None, None, DURUM, DURUM, dict(DURUM), None]
    hizmetler = ["START_PENDING", "START_PENDING", "STOPPED"]
    saat = Saat()
    izleyici = tepsi.DurumIzleyici(olaylar, lambda: sira.pop(0), lambda: hizmetler.pop(0), saat=saat)

    a = izleyici.yokla()
    assert a == tepsi.Anlik(None, "START_PENDING", True) and izleyici.bekleme() == tepsi.HIZLI_SN
    assert izleyici.yokla() is None  # aynı durum: olay yok
    assert izleyici.yokla().durum == DURUM and izleyici.bekleme() == tepsi.YOKLAMA_SN
    assert izleyici.yokla() is None and izleyici.yokla() is None
    saat.an += tepsi.ACILIS_BEKLEME_SN + 1
    assert izleyici.yokla() == tepsi.Anlik(None, "STOPPED", False)
    turler = []
    while not olaylar.empty():
        tur, anlik = olaylar.get_nowait()
        turler.append((tur, tepsi.tepsi_durumu(anlik.durum, anlik.hizmet)[0]))
    assert turler == [("durum", "bekleniyor"), ("durum", "calisiyor"), ("durum", "durdu")]


def test_izleyici_acilis_suresi_dolunca_yanitsiz_hizmet_beklenmiyor_sayilir():
    olaylar: queue.Queue = queue.Queue()
    saat = Saat()
    izleyici = tepsi.DurumIzleyici(olaylar, lambda: None, lambda: "RUNNING", saat=saat)
    assert pencere.pencere_kipi(izleyici.yokla()) == "bekleniyor"
    saat.an += tepsi.ACILIS_BEKLEME_SN + 1
    anlik = izleyici.yokla()  # 20 sn geçti, hâlâ yanıt yok: kip değişir (pencere yeniden çizilir)
    assert anlik is not None and pencere.pencere_kipi(anlik) == "hizmet_calismiyor"
    assert izleyici.bekleme() == tepsi.YOKLAMA_SN
    izleyici.hizlandir()  # "Hizmeti başlat"tan sonra yine 1 sn
    assert izleyici.bekleme() == tepsi.HIZLI_SN


def test_sonraki_bekleme():
    assert tepsi.sonraki_bekleme(False, True) == 1.0
    assert tepsi.sonraki_bekleme(True, True) == 15.0
    assert tepsi.sonraki_bekleme(False, False) == 15.0


def test_durum_uygulamasi_hicbir_durumda_gelistirme_kipine_gecmez():
    """Durum uygulaması (simgeli pencere) kip_sec'e paketli=True verir: sunucu açan kipe düşmez."""
    assert pencere.pencere_kipi(None) == "okunuyor"
    for durum in (None, DURUM):
        for hizmet in HIZMET_DURUMLARI:
            for bekleniyor in (False, True):
                kip = pencere.pencere_kipi(tepsi.Anlik(durum, hizmet, bekleniyor))
                assert kip != "gelistirme"


# ---- gizli kip ve kural 28 ------------------------------------------------------------------
@pytest.fixture()
def sunucu_engelli(monkeypatch):
    """tahta_sunucu.sunucu içe aktarılamaz; geliştirme penceresi çağrılırsa test düşer."""
    monkeypatch.setitem(sys.modules, "tahta_sunucu.sunucu", None)

    def yasak():
        raise AssertionError("geliştirme penceresi (sunucu) açıldı")

    monkeypatch.setattr(pencere, "_gelistirme_penceresi", yasak)
    monkeypatch.setattr(pencere, "_gunluk_kur", lambda: None)
    monkeypatch.setattr(pencere, "yerel_durum_oku", lambda *a, **k: None)
    monkeypatch.setattr(pencere, "hizmet_durumu", lambda: "yok")  # geliştirmede "gelistirme" kipi olurdu
    cagrilar = []
    monkeypatch.setattr(pencere, "_durum_uygulamasi", lambda gizli, tepsi_acik: cagrilar.append((gizli, tepsi_acik)) or 0)
    return cagrilar


def test_gizli_kip_paketli_programda_yalniz_simge_acar_sunucu_acmaz(monkeypatch, sunucu_engelli):
    monkeypatch.setattr(pencere.ayar, "paketli_windows", lambda: True)
    assert pencere.calistir(gizli=True) == 0
    assert sunucu_engelli == [(True, True)]


def test_gizli_kip_gelistirmede_hicbir_sey_acmaz(monkeypatch, sunucu_engelli, capsys):
    monkeypatch.setattr(pencere.ayar, "paketli_windows", lambda: False)
    monkeypatch.delenv(tepsi.DENEME_DEGISKENI, raising=False)
    assert pencere.calistir(gizli=True) == 2
    assert sunucu_engelli == [] and "--gizli" in capsys.readouterr().err


def test_deneme_kipi_gelistirmede_simge_acar_sunucu_acmaz(monkeypatch, sunucu_engelli):
    monkeypatch.setattr(pencere.ayar, "paketli_windows", lambda: False)
    monkeypatch.setattr(tepsi.sys, "platform", "win32")
    monkeypatch.setenv(tepsi.DENEME_DEGISKENI, "1")
    assert pencere.calistir() == 0 and pencere.calistir(gizli=True) == 0
    assert sunucu_engelli == [(False, True), (True, True)]


def test_main_pencere_gizli_bagimsiz_degiskenini_gecirir(monkeypatch):
    from tahta_sunucu.__main__ import main

    gelen = []
    monkeypatch.setattr(pencere, "calistir", lambda gizli=False: gelen.append(gizli) or 0)
    assert main(["pencere", "--gizli"]) == 0 and main(["pencere"]) == 0
    assert gelen == [True, False]


def _ust_duzey_ice_aktarmalar(kaynak: str) -> set[str]:
    adlar = set()
    for dugum in ast.parse(kaynak).body:
        if isinstance(dugum, ast.Import):
            adlar |= {a.name.split(".")[0] for a in dugum.names}
        elif isinstance(dugum, ast.ImportFrom):
            adlar.add((dugum.module or "").split(".")[0])
            adlar |= {a.name for a in dugum.names}
    return adlar


def test_pywin32_ve_sunucu_modul_duzeyinde_ice_aktarilmaz():
    for ad in ("pencere.py", "tepsi.py"):
        kaynak = (KOK / "tahta_sunucu" / ad).read_text(encoding="utf-8")
        ust = _ust_duzey_ice_aktarmalar(kaynak)
        assert not {a for a in ust if a.startswith("win32") or a in ("pywintypes", "sunucu", "Sunucu")}, ad
    # Sunucu yalnız geliştirme penceresinde (hizmet yokken, uv run) içe aktarılır ve çağrılır.
    def sunucuya_dokunanlar(ad: str) -> set[str]:
        agac = ast.parse((KOK / "tahta_sunucu" / ad).read_text(encoding="utf-8"))
        sahipler = set()
        for dugum in ast.walk(agac):
            if isinstance(dugum, ast.ImportFrom) and (dugum.module or "").split(".")[-1] == "sunucu":
                sahipler.add("?")
            if isinstance(dugum, ast.Name | ast.Attribute) and "Sunucu" in (
                getattr(dugum, "id", None),
                getattr(dugum, "attr", None),
            ):
                sahipler.add("?")
        for islev in ast.walk(agac):
            if isinstance(islev, ast.FunctionDef | ast.ClassDef):
                for alt in ast.walk(islev):
                    if (isinstance(alt, ast.ImportFrom) and (alt.module or "").split(".")[-1] == "sunucu") or (
                        isinstance(alt, ast.Name) and alt.id == "Sunucu"
                    ):
                        sahipler.add(islev.name)
        return sahipler

    assert sunucuya_dokunanlar("pencere.py") == {"?", "_gelistirme_penceresi"}
    assert sunucuya_dokunanlar("tepsi.py") == set()


def test_tek_ornek_adi_sabit():
    assert tepsi.MUTEX_ADI == "Local\\TahtaKontrolDurum"


# ---- simge dosyaları ve paketleme ----------------------------------------------------------
def _uretici():
    yol = KOK / "scripts" / "durum_simgeleri.py"
    tanim = importlib.util.spec_from_file_location("durum_simgeleri", yol)
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    return modul


def test_durum_simgeleri_betikle_ayni_ve_gecerli_ico(tmp_path):
    uretici = _uretici()
    assert set(uretici.DOSYA) == set(tepsi.TURLER)
    assert uretici.DOSYA == tepsi.SIMGE_DOSYALARI
    for yol in uretici.yaz(tmp_path):
        depodaki = KOK / "packaging" / "windows" / yol.name
        assert depodaki.read_bytes() == yol.read_bytes(), f"{yol.name}: betiği yeniden çalıştırın"
        veri = yol.read_bytes()
        ayrilmis, tip, sayi = __import__("struct").unpack_from("<HHH", veri)
        assert (ayrilmis, tip, sayi) == (0, 1, 3)
        boyutlar = [veri[6 + 16 * i] for i in range(3)]
        assert boyutlar == [16, 24, 32]
    # Durum noktası renkleri farklı; ana simge betikçe değiştirilmez.
    assert len({uretici.ico(t) for t in tepsi.TURLER}) == 3


def test_simge_adaylari_durum_simgesinden_ana_simgeye_duser(tmp_path):
    windows = tmp_path / "packaging" / "windows"
    windows.mkdir(parents=True)
    (windows / "tahta-kontrol.ico").write_bytes(b"x")
    assert tepsi.simge_adaylari("durdu", tmp_path) == [windows / "tahta-kontrol.ico"]
    paketli = tmp_path / "tahta_sunucu" / "simgeler"
    paketli.mkdir(parents=True)
    (paketli / "durum-durdu.ico").write_bytes(b"x")
    assert tepsi.simge_adaylari("durdu", tmp_path)[0] == paketli / "durum-durdu.ico"
    assert tepsi.simge_adaylari("durdu", tmp_path / "yok") == []
    # depoda üç durum simgesi de var (geliştirmede packaging/windows'tan)
    for tur in tepsi.TURLER:
        assert tepsi.simge_adaylari(tur, KOK)[0].name == f"durum-{tur}.ico"


def test_spec_simgeleri_ve_pywin32_modullerini_tasir():
    spec = (KOK / "packaging" / "windows" / "tahta-kontrol.spec").read_text(encoding="utf-8")
    for ad in ("win32gui", "win32con", "win32api", "win32event", "tahta_sunucu.tepsi"):
        assert f'"{ad}"' in spec
    assert 'glob("durum-*.ico")' in spec and '"tahta_sunucu/simgeler"' in spec


def test_giris_noktasi_pencere_bagimsiz_degiskenlerini_gecirir():
    giris = (KOK / "packaging" / "windows" / "giris.py").read_text(encoding="utf-8")
    assert 'main(sys.argv[1:] or ["pencere"])' in giris and "pencere --gizli" in giris
