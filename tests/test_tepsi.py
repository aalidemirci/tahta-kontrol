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


# ---- inceleme düzeltmeleri: simge kaydı, istenmeden kapanma, ikinci örnek, kip metinleri ----------------
class SahteKabuk:
    """Shell_NotifyIcon'un benzeri: `var` simgenin bildirim alanında olup olmadığıdır. `zaman_asimi` listesindeki
    işlem bir kez UYGULANIR ama hata verir (Explorer meşgulken belgelenmiş durum); `hazir` False iken her işlem
    düşer (görev çubuğu yok)."""

    NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
    NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 1, 2, 4, 16
    NIIF_INFO, NIIF_WARNING = 1, 2

    def __init__(self):
        self.var = False
        self.hazir = True
        self.zaman_asimi: list[int] = []
        self.islemler: list[int] = []
        self.ipucu = None
        self.balonlar: list[str] = []
        self.iletiler: list[int] = []
        self.pencere = 0
        self.bulma = 0

    def Shell_NotifyIcon(self, islem, kayit):  # noqa: N802 - pywin32 adı
        self.islemler.append(islem)
        if not self.hazir:
            raise OSError("görev çubuğu yok")
        uygula = {
            self.NIM_ADD: not self.var,
            self.NIM_MODIFY: self.var,
            self.NIM_DELETE: self.var,
        }[islem]
        if uygula:
            if islem == self.NIM_ADD:
                self.var = True
            elif islem == self.NIM_DELETE:
                self.var = False
            elif len(kayit) > 6:
                self.balonlar.append(kayit[6])
            if islem != self.NIM_DELETE:
                self.ipucu = kayit[5]
        if islem in self.zaman_asimi:
            self.zaman_asimi.remove(islem)
            raise OSError("zaman aşımı")
        if not uygula:
            raise OSError("geçersiz işlem")

    def PostMessage(self, hwnd, ileti, wparam, lparam):  # noqa: N802
        self.iletiler.append(ileti)

    def PostQuitMessage(self, kod):  # noqa: N802
        pass

    def DestroyIcon(self, tutamac):  # noqa: N802
        pass

    def FindWindow(self, sinif, ad):  # noqa: N802
        self.bulma += 1
        return self.pencere if self.bulma >= 3 else 0


@pytest.fixture()
def kabuk(monkeypatch):
    sahte = SahteKabuk()
    monkeypatch.setitem(sys.modules, "win32gui", sahte)
    return sahte


def _tepsi(olaylar=None) -> tepsi.Tepsi:
    t = tepsi.Tepsi(olaylar if olaylar is not None else queue.Queue())
    t._hwnd = 4242
    t._simge = lambda tur: 0  # LoadImage yok
    return t


def test_tek_modify_hatasi_simgeyi_kalici_eklenmedi_durumuna_kilitlemez(kabuk):
    t = _tepsi()
    t._ekle()
    assert kabuk.var and t._eklendi
    kabuk.zaman_asimi.append(kabuk.NIM_MODIFY)  # MODIFY uygulandı ama hata döndü
    t.guncelle("calisiyor", "Tahta Kontrol: sunucu çalışıyor", tepsi.menu_ogeleri("calisiyor"))
    t._guncelle_ileti(0, 0, 0, 0)
    assert t._eklendi, "ADD 'zaten var' diye düşünce MODIFY ile varlık sınanmalı"
    t.guncelle("durdu", "Tahta Kontrol: sunucu hizmeti durdu", tepsi.menu_ogeleri("hizmet_calismiyor", "STOPPED"))
    t._guncelle_ileti(0, 0, 0, 0)
    assert kabuk.ipucu == "Tahta Kontrol: sunucu hizmeti durdu"  # simge eski durumda donmadı
    t.balon(tepsi.BALON_DURDU, uyari=True)
    t._balon_ileti(0, 0, 0, 0)
    assert kabuk.balonlar == [tepsi.BALON_DURDU]  # "durdu" balonu atılmadı


def test_zaman_asimina_dusen_ilk_ekleme_simgeyi_eklenmis_sayar(kabuk):
    t = _tepsi()
    kabuk.zaman_asimi.append(kabuk.NIM_ADD)  # oturum açılışında: ADD uygulandı ama hata döndü
    t._ekle()
    assert kabuk.var and t._eklendi
    assert kabuk.islemler == [kabuk.NIM_ADD, kabuk.NIM_MODIFY]


def test_gorev_cubugu_hazir_degilse_sonraki_guncellemede_yeniden_eklenir(kabuk):
    t = _tepsi()
    kabuk.hazir = False
    t._ekle()
    assert not t._eklendi
    t.balon("deneme")
    t._balon_ileti(0, 0, 0, 0)  # alan yokken balon sessizce düşer, hata çıkmaz
    assert kabuk.balonlar == []
    kabuk.hazir = True
    t._guncelle_ileti(0, 0, 0, 0)
    assert kabuk.var and t._eklendi
    t.balon("deneme")
    t._balon_ileti(0, 0, 0, 0)
    assert kabuk.balonlar == ["deneme"]


def test_kapanista_simge_eklenmedi_sanilsa_da_kaldirilir(kabuk):
    t = _tepsi()
    kabuk.var = True  # alanda duruyor ama nesne bilmiyor (zaman aşımı)
    t._eklendi = False
    t._yok_edildi(4242, 0, 0, 0)
    assert not kabuk.var and kabuk.islemler[-1] == kabuk.NIM_DELETE and t._hwnd == 0


class SahteWin32Con:
    WM_DESTROY = 0x0002
    WM_CLOSE = 0x0010
    WM_NULL = 0
    WS_OVERLAPPED = 0
    WS_SYSMENU = 0x80000
    CW_USEDEFAULT = -1


class SahteWin32Api:
    @staticmethod
    def GetModuleHandle(ad):  # noqa: N802
        return 1


def _sahte_ileti_dongusu(monkeypatch, kabuk, dongu):
    """Tepsi._calis'i Windows'suz çalıştırır: pencere sınıfının ileti haritası yakalanır, `dongu(harita)`
    PumpMessages'ın yerine geçer."""
    kap = {}

    class Sinif:
        pass

    def sinif_kaydet(sinif):
        kap["harita"] = sinif.lpfnWndProc
        return 77

    kabuk.WNDCLASS = Sinif
    kabuk.RegisterWindowMessage = lambda ad: 0xC123
    kabuk.RegisterClass = sinif_kaydet
    kabuk.CreateWindow = lambda *a: 4242
    kabuk.UnregisterClass = lambda atom, h: None
    kabuk.PumpMessages = lambda: dongu(kap["harita"])
    monkeypatch.setitem(sys.modules, "win32con", SahteWin32Con)
    monkeypatch.setitem(sys.modules, "win32api", SahteWin32Api)


def test_wm_close_simge_penceresini_yok_etmez_duzgun_cikis_ister(monkeypatch, kabuk):
    olaylar: queue.Queue = queue.Queue()
    t = tepsi.Tepsi(olaylar)
    t._simge = lambda tur: 0
    goruldu = []

    def dongu(harita):
        assert SahteWin32Con.WM_CLOSE in harita  # DefWindowProc pencereyi yok etmesin
        assert harita[SahteWin32Con.WM_CLOSE](4242, SahteWin32Con.WM_CLOSE, 0, 0) == 0
        goruldu.append(olaylar.get_nowait())
        t.kapat()  # Tk "Çık"ı işledi
        harita[SahteWin32Con.WM_DESTROY](4242, SahteWin32Con.WM_DESTROY, 0, 0)

    _sahte_ileti_dongusu(monkeypatch, kabuk, dongu)
    t._calis()
    assert goruldu == [("menu", "cik")]
    assert olaylar.empty()  # istenen kapanışta "simge_kapandi" yok
    assert not kabuk.var and t._hwnd == 0


def test_istenmeden_biten_ileti_dongusu_tk_tarafina_haber_verir(monkeypatch, kabuk):
    olaylar: queue.Queue = queue.Queue()
    t = tepsi.Tepsi(olaylar)
    t._simge = lambda tur: 0

    def dongu(harita):  # pencere dışarıdan yok edildi (WM_DESTROY), kapat() çağrılmadı
        harita[SahteWin32Con.WM_DESTROY](4242, SahteWin32Con.WM_DESTROY, 0, 0)

    _sahte_ileti_dongusu(monkeypatch, kabuk, dongu)
    t._calis()
    assert olaylar.get_nowait() == ("simge_kapandi",) and t._hwnd == 0


class SahteKok:
    def __init__(self, durum):
        self.durum = durum
        self.kapanis = None
        self.yok_edildi = False

    def state(self):
        return self.durum

    def protocol(self, ad, islev):
        self.kapanis = islev

    def destroy(self):
        self.yok_edildi = True


class SahteIzleyici:
    def durdur(self):
        pass


def _uygulama(kok_durumu: str):
    uyg = object.__new__(pencere.DurumUygulamasi)
    uyg.kok = SahteKok(kok_durumu)
    uyg.simge = None
    uyg.izleyici = SahteIzleyici()
    uyg.cizimler = 0

    def ciz():
        uyg.cizimler += 1

    uyg._ciz = ciz
    return uyg


def test_simge_kapaninca_gizli_pencere_sureci_kapatir_gorunur_pencere_simgesiz_kalir():
    gizli = _uygulama("withdrawn")
    gizli._olay(("simge_kapandi",))
    assert gizli.simge is None and gizli.kok.yok_edildi  # görünmez süreç tek örnek engelini tutmaz

    acik = _uygulama("normal")
    acik._olay(("simge_kapandi",))
    assert acik.simge is None and not acik.kok.yok_edildi and acik.cizimler == 1
    assert acik.kok.kapanis == acik.cik  # X artık gizlemez, kapatır


def test_ikinci_ornek_pencereyi_kisa_sure_arar_bulamazsa_uyarir(monkeypatch, kabuk):
    kabuk.pencere = 99
    uykular = []
    assert tepsi.var_olani_goster(deneme=5, ara_sn=0.2, uyu=uykular.append) is True
    assert kabuk.bulma == 3 and uykular == [0.2, 0.2] and kabuk.iletiler == [tepsi.WM_GOSTER]

    kabuk.pencere, kabuk.bulma = 0, 0
    assert tepsi.var_olani_goster(deneme=3, uyu=lambda s: None) is False

    uyarilar = []
    monkeypatch.setattr(pencere, "_gunluk_kur", lambda: None)
    monkeypatch.setattr(tepsi, "tek_ornek_al", lambda: (None, False))
    monkeypatch.setattr(tepsi, "uyari_kutusu", uyarilar.append)
    for gizli, bulundu, beklenen in ((False, False, 1), (True, False, 0), (False, True, 0)):
        uyarilar.clear()
        monkeypatch.setattr(tepsi, "var_olani_goster", lambda b=bulundu: b)
        assert pencere._durum_uygulamasi(gizli, tepsi_acik=True) == 0
        assert len(uyarilar) == beklenen, (gizli, bulundu)
    assert "sunucuyu durdurmaz" in tepsi.IKINCI_ORNEK_UYARISI


def test_sc_okunamayinca_kurulu_degil_denmez():
    assert pencere.pencere_kipi(tepsi.Anlik(None, None, False)) == "okunamadi"
    assert pencere.pencere_kipi(tepsi.Anlik(None, "yok", False)) == "kurulu_degil"
    assert pencere.pencere_kipi(tepsi.Anlik(None, "STOPPED", False)) == "hizmet_calismiyor"
    assert "baslat" not in [a for a, _, _ in tepsi.menu_ogeleri("okunamadi")]
    # geliştirmenin kip seçimi değişmedi (orada hizmet yok + okunamadı "gelistirme"dir)
    assert pencere.kip_sec(None, None, False) == "gelistirme"


def test_acilista_yanitsiz_running_hizmet_icin_yeni_basladi_denmez():
    baslik, alt = pencere.bekleniyor_metni("RUNNING", baslatildi=False)
    assert "yeni başladı" not in alt and "başlatılıyor" not in baslik
    for hizmet in ("START_PENDING", "CONTINUE_PENDING"):
        assert "yeni başladı" in pencere.bekleniyor_metni(hizmet, baslatildi=False)[1]
    assert "yeni başladı" in pencere.bekleniyor_metni("RUNNING", baslatildi=True)[1]
