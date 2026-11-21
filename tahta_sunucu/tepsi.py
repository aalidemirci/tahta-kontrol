"""Bildirim alanı (sistem tepsisi) durum simgesi (0.21.0).

Kurulu programda durum penceresiyle (pencere.py) aynı süreçte çalışır ve YALNIZ DURUM GÖSTERİR: sunucu
açmaz, hizmeti kendiliğinden başlatmaz (kural 28; "Hizmeti başlat" yalnız kullanıcı seçince, UAC ile).
Durum `/yerel/durum` (127.0.0.1) ve `sc query` ile okunur; simgenin ipucuna ve balonuna ağ adresi, okul
adı, kişi verisi girmez (yalnız durum ve sürüm).

Düzen: Tk ana iş parçacığındadır (pencere.py). Bu modülde
- saf işlevler (testli): tepsi_durumu, menu_ogeleri, gecis_bildirimi, kararli_tur, sonraki_bekleme,
  anlik_imzasi, simge_adaylari;
- DurumIzleyici: ayrı iş parçacığında 15 sn arayla durum okur, değişince kuyruğa TEK olay koyar;
- Tepsi: kendi iş parçacığında gizli bir Win32 penceresi + ileti döngüsü (Shell_NotifyIcon); menü
  seçimleri kuyruğa gider, Tk `after` ile okur (tkinter iş parçacığı güvenli değildir);
- tek_ornek_al / var_olani_goster: oturum başına tek örnek ("Local\\TahtaKontrolDurum").
pywin32 YALNIZ işlevlerin içinde içe aktarılır (Linux'ta ve testlerde modül pywin32'siz yüklenir).
"""

from __future__ import annotations

import json
import logging
import os
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import __version__, ayar

MUTEX_ADI = "Local\\TahtaKontrolDurum"
PENCERE_SINIFI = "TahtaKontrolDurumSimgesi"
YOKLAMA_SN = 15.0
HIZLI_SN = 1.0
ACILIS_BEKLEME_SN = 20.0  # açılışta ve "Hizmeti başlat"tan sonra sunucunun yanıtı 1 sn arayla beklenir
IPUCU_EN_UZUN = 127  # NOTIFYICONDATA.szTip: 128 karakter, sonu boş karakter
BALON_BASLIK = "Tahta Kontrol"
BALON_GIZLENDI = "Tahta Kontrol bildirim alanında çalışmaya devam ediyor"
BALON_DURDU = "Sunucu durdu; tahtalar çevrimdışı kalır. Ayrıntı için simgeye çift tıklayın."
PANEL_ADRESI = f"http://127.0.0.1:{ayar.HTTP_PORT}"
DENEME_DEGISKENI = "TAHTA_TEPSI_DENE"

TURLER = ("calisiyor", "bekleniyor", "durdu")
SIMGE_DOSYALARI = {tur: f"durum-{tur}.ico" for tur in TURLER}
ANA_SIMGE = "tahta-kontrol.ico"
BEKLENEN_HIZMET = ("START_PENDING", "RUNNING", "CONTINUE_PENDING")

# hizmet durumu (sc query) → (simge türü, ipucu); sunucu yanıt vermiyorken
_HIZMET_GORUNUMU = {
    "START_PENDING": ("bekleniyor", "sunucu başlatılıyor"),
    "CONTINUE_PENDING": ("bekleniyor", "sunucu başlatılıyor"),
    "RUNNING": ("bekleniyor", "hizmet çalışıyor, sunucu yanıt vermiyor"),
    "STOP_PENDING": ("durdu", "sunucu durduruluyor"),
    "STOPPED": ("durdu", "sunucu hizmeti durdu"),
    "PAUSE_PENDING": ("durdu", "sunucu hizmeti duraklatılmış"),
    "PAUSED": ("durdu", "sunucu hizmeti duraklatılmış"),
    "yok": ("durdu", "sunucu hizmeti kurulu değil"),
}
_SURUM = re.compile(r"\d+(\.\d+){1,3}")

# Win32 ileti numaraları (WM_APP = 0x8000); win32con modül düzeyinde içe aktarılmaz.
WM_TEPSI = 0x8000 + 1  # simgeden gelen fare/klavye bildirimi
WM_GUNCELLE = 0x8000 + 2
WM_BALON = 0x8000 + 3
WM_KAPAT = 0x8000 + 4
WM_GOSTER = 0x8000 + 5  # ikinci açılış var olan pencereyi gösterir
_NIN_SELECT = 0x0400  # WM_USER + 0
_NIN_KEYSELECT = 0x0401
_ZATEN_VAR = 183  # ERROR_ALREADY_EXISTS
_SIMGE_KIMLIGI = 1
_KOMUT_TABANI = 100


# ---- saf mantık (testli) ----------------------------------------------------------------
def _ipucu(metin: str) -> str:
    metin = " ".join(metin.split())
    return metin if len(metin) <= IPUCU_EN_UZUN else metin[: IPUCU_EN_UZUN - 1] + "…"


def tepsi_durumu(durum: dict | None, hizmet: str | None, okundu: bool = True) -> tuple[str, str]:
    """(simge türü, ipucu). Tür: calisiyor | bekleniyor | durdu. İpucu ≤ 127 karakter; yalnız durum ve sürüm
    (sunucunun bildirdiği sürüm yalnız sayı kalıbındaysa kullanılır, yoksa pencerenin sürümü)."""
    if not okundu:
        return "bekleniyor", "Tahta Kontrol: durum okunuyor"
    if durum is not None:
        surum = str(durum.get("surum") or "")
        if not _SURUM.fullmatch(surum):
            surum = __version__
        return "calisiyor", _ipucu(f"Tahta Kontrol: sunucu çalışıyor · sürüm {surum}")
    tur, metin = _HIZMET_GORUNUMU.get(hizmet or "", ("bekleniyor", "sunucunun durumu okunamadı"))
    return tur, _ipucu(f"Tahta Kontrol: {metin}")


def menu_ogeleri(kip: str, hizmet: str | None = None) -> list[tuple[str, str, bool]]:
    """Sağ tık menüsü: (anahtar, etiket, etkin); "-" ayraçtır. "Hizmeti başlat" yalnız hizmet durmuşken
    (kip hizmet_calismiyor ve sc STOPPED) çıkar; "Paneli aç" yalnız sunucu yanıt verirken etkindir."""
    ogeler = [
        ("panel", "Paneli aç", kip == "calisiyor"),
        ("goster", "Durumu göster", True),
    ]
    if kip == "hizmet_calismiyor" and hizmet == "STOPPED":
        ogeler.append(("baslat", "Hizmeti başlat", True))
    ogeler += [("-", "", False), ("cik", "Çık", True)]
    return ogeler


def kararli_tur(onceki: str | None, simdi: str) -> str | None:
    """Geçiş bildirimi için son "kararlı" tür: ara "bekleniyor" durumları (durduruluyor değil; başlatılıyor,
    yanıt yok) önceki kararlı türü değiştirmez."""
    return onceki if simdi == "bekleniyor" else simdi


def gecis_bildirimi(onceki: str | None, simdi: str) -> str | None:
    """Balon metni yalnız "çalışıyor → durdu" geçişinde; `onceki` son kararlı türdür (kararli_tur). Aynı
    durumda ya da başka geçişlerde None; durdu → durdu tekrar etmez, yani bir duruşta bir kez."""
    if onceki == "calisiyor" and simdi == "durdu":
        return BALON_DURDU
    return None


def sonraki_bekleme(durum_var: bool, hizli: bool) -> float:
    """Yoklama aralığı: açılışta ve "Hizmeti başlat"tan sonraki kısa süre içinde sunucu yanıt verene kadar
    1 sn, sonra 15 sn."""
    return HIZLI_SN if hizli and not durum_var else YOKLAMA_SN


@dataclass(frozen=True)
class Anlik:
    """Bir yoklamanın sonucu. `bekleniyor`: hizmet yeni başladı, sunucunun yanıtı bekleniyor."""

    durum: dict | None
    hizmet: str | None
    bekleniyor: bool = False


def anlik_imzasi(anlik: Anlik) -> str:
    return json.dumps([anlik.durum, anlik.hizmet, anlik.bekleniyor], sort_keys=True, ensure_ascii=False)


def simge_adaylari(tur: str, kok: Path | None = None) -> list[Path]:
    """Simge dosyası adayları, sırayla: durum simgesi, sonra ana simge (paketli programda
    `tahta_sunucu/simgeler/`, geliştirmede `packaging/windows/`). Yalnız var olanlar döner."""
    kok = ayar.PAKET_KOKU if kok is None else kok
    adlar = [SIMGE_DOSYALARI[tur]] if tur in SIMGE_DOSYALARI else []
    adlar.append(ANA_SIMGE)
    sonuc = []
    for ad in adlar:
        for dizin in (kok / "tahta_sunucu" / "simgeler", kok / "packaging" / "windows"):
            if (dizin / ad).is_file():
                sonuc.append(dizin / ad)
    return sonuc


def deneme_kipi() -> bool:
    """Geliştirmede simgeyi elle denemek için (TAHTA_TEPSI_DENE=1): pencere sunucu AÇMAZ, yalnız durum gösterir."""
    return sys.platform.startswith("win") and os.environ.get(DENEME_DEGISKENI) == "1"


# ---- durum yoklaması ----------------------------------------------------------------------
class DurumIzleyici:
    """Durumu ayrı iş parçacığında okur; değişince kuyruğa ("durum", Anlik) koyar (aynı durum tekrar gitmez)."""

    def __init__(self, olaylar: queue.Queue, okuyucu, hizmet_okuyucu, saat=time.monotonic):
        self.olaylar = olaylar
        self.okuyucu = okuyucu
        self.hizmet_okuyucu = hizmet_okuyucu
        self.saat = saat
        self._hizli_bitis = saat() + ACILIS_BEKLEME_SN
        self._son_imza: str | None = None
        self._durum_var = False
        self._uyandir = threading.Event()
        self._dur = threading.Event()
        self._is: threading.Thread | None = None

    def yokla(self) -> Anlik | None:
        durum = self.okuyucu()
        hizmet = self.hizmet_okuyucu() if durum is None else None
        hizli = self.saat() < self._hizli_bitis
        anlik = Anlik(durum, hizmet, hizli and durum is None and hizmet in BEKLENEN_HIZMET)
        self._durum_var = durum is not None
        imza = anlik_imzasi(anlik)
        if imza == self._son_imza:
            return None
        self._son_imza = imza
        self.olaylar.put(("durum", anlik))
        return anlik

    def bekleme(self) -> float:
        return sonraki_bekleme(self._durum_var, self.saat() < self._hizli_bitis)

    def hizlandir(self, sure_sn: float = ACILIS_BEKLEME_SN) -> None:
        """"Hizmeti başlat"tan sonra: kısa süre 1 sn arayla yokla."""
        self._hizli_bitis = max(self._hizli_bitis, self.saat() + sure_sn)
        self._uyandir.set()

    def simdi(self) -> None:
        self._uyandir.set()

    def _calis(self) -> None:
        while not self._dur.is_set():
            self._uyandir.clear()
            try:
                self.yokla()
            except Exception:  # yoklama hatası simgeyi düşürmesin
                logging.exception("Durum okunamadı")
            self._uyandir.wait(self.bekleme())

    def baslat(self) -> None:
        self._is = threading.Thread(target=self._calis, name="durum-yoklama", daemon=True)
        self._is.start()

    def durdur(self) -> None:
        self._dur.set()
        self._uyandir.set()


# ---- tek örnek ----------------------------------------------------------------------------
def tek_ornek_al() -> tuple[object | None, bool]:
    """(mutex tutamacı, ilk örnek mi). pywin32 yoksa (None, True): engel yok sayılır. Tutamaç süreç
    boyunca saklanmalıdır (bırakılırsa mutex kalkar)."""
    try:
        import win32api
        import win32event
    except ImportError:
        return None, True
    tutamac = win32event.CreateMutex(None, False, MUTEX_ADI)
    return tutamac, win32api.GetLastError() != _ZATEN_VAR


def var_olani_goster(deneme: int = 10, ara_sn: float = 0.2, uyu=time.sleep) -> bool:
    """İkinci açılışta: var olan örneğin gizli penceresine "göster" iletisi yollar. Öbür örnek mutex'i alıp
    penceresini henüz kurmamış olabilir: pencere kısa süre (≈ 2 sn) aranır. Bulunamazsa False."""
    try:
        import win32gui
    except ImportError:
        return False
    try:
        hwnd = 0
        for sira in range(max(1, deneme)):
            hwnd = win32gui.FindWindow(PENCERE_SINIFI, None)
            if hwnd:
                break
            if sira + 1 < deneme:
                uyu(ara_sn)
        if not hwnd:
            return False
        try:
            import ctypes

            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY: öbür süreç pencereyi öne alabilsin
        except Exception:
            pass
        win32gui.PostMessage(hwnd, WM_GOSTER, 0, 0)
        return True
    except Exception:
        logging.exception("Var olan durum penceresine ulaşılamadı")
        return False


IKINCI_ORNEK_UYARISI = (
    "Tahta Kontrol durum simgesi bu oturumda zaten açık ama yanıt vermiyor.\n\n"
    "Görev Yöneticisi'nden TahtaKontrol.exe'yi (durum penceresi) kapatıp yeniden açın. "
    "Bu, sunucuyu durdurmaz."
)


def uyari_kutusu(metin: str) -> None:
    """Tk kurulmadan basit Windows uyarı kutusu (ikinci örnek var olana ulaşamazsa sessiz çıkmasın)."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, metin, BALON_BASLIK, 0x30)  # MB_ICONWARNING
    except Exception:
        logging.warning("Uyarı kutusu gösterilemedi.")


# ---- bildirim alanı simgesi (Win32) -------------------------------------------------------
class Tepsi:
    """Bildirim alanı simgesi. Kendi iş parçacığında gizli bir pencere ve Windows ileti döngüsü çalıştırır;
    öbür iş parçacıkları yalnız `guncelle`, `balon`, `kapat` çağırır (PostMessage)."""

    def __init__(self, olaylar: queue.Queue):
        self.olaylar = olaylar
        self._kilit = threading.Lock()
        self._tur, self._ipucu = tepsi_durumu(None, None, okundu=False)
        self._menu = menu_ogeleri("okunuyor")
        self._balon: tuple[str, bool] | None = None
        self._hwnd = 0
        self._eklendi = False
        self._taskbar = 0
        self._simgeler: dict[str, int] = {}
        self._hazir = threading.Event()
        self._kapatiliyor = False  # kapat() istendi mi (istenmeden biten ileti döngüsü Tk'ye haber verilir)
        self._is: threading.Thread | None = None

    # -- öbür iş parçacıklarından
    def baslat(self, zaman_asimi: float = 5.0) -> bool:
        self._is = threading.Thread(target=self._calis, name="tepsi", daemon=True)
        self._is.start()
        self._hazir.wait(zaman_asimi)
        return bool(self._hwnd)

    def guncelle(self, tur: str, ipucu: str, menu: list[tuple[str, str, bool]]) -> None:
        with self._kilit:
            self._tur, self._ipucu, self._menu = tur, _ipucu(ipucu), list(menu)
        self._gonder(WM_GUNCELLE)

    def balon(self, metin: str, uyari: bool = False) -> None:
        with self._kilit:
            self._balon = (metin, uyari)
        self._gonder(WM_BALON)

    def kapat(self, bekle_sn: float = 2.0) -> None:
        """Simgeyi kaldırır (NIM_DELETE) ve ileti döngüsünü bitirir; süreç simge kalkmadan çıkmasın diye bekler."""
        self._kapatiliyor = True
        self._gonder(WM_KAPAT)
        if self._is is not None and self._is is not threading.current_thread():
            self._is.join(bekle_sn)

    def _gonder(self, ileti: int) -> None:
        if not self._hwnd:
            return
        try:
            import win32gui

            win32gui.PostMessage(self._hwnd, ileti, 0, 0)
        except Exception:
            logging.exception("Simge iletisi gönderilemedi")

    # -- simgenin iş parçacığı
    def _calis(self) -> None:
        try:
            import win32api
            import win32con
            import win32gui

            self._taskbar = win32gui.RegisterWindowMessage("TaskbarCreated")
            harita = {
                self._taskbar: self._yeniden_ekle,
                win32con.WM_DESTROY: self._yok_edildi,
                # Dışarıdan kapatma isteği (ör. zorlamasız taskkill): pencereyi DefWindowProc'a yok ettirme
                # (simge iş parçacığı biter, süreç görünmez kalıp tek örnek engelini tutardı); düzgün çıkış iste.
                win32con.WM_CLOSE: self._kapatma_istegi,
                WM_TEPSI: self._bildirim,
                WM_GUNCELLE: self._guncelle_ileti,
                WM_BALON: self._balon_ileti,
                WM_KAPAT: self._kapat_ileti,
                WM_GOSTER: self._goster_ileti,
            }
            sinif = win32gui.WNDCLASS()
            sinif.hInstance = win32api.GetModuleHandle(None)
            sinif.lpszClassName = PENCERE_SINIFI
            sinif.lpfnWndProc = harita
            atom = win32gui.RegisterClass(sinif)
            # Görünmeyen üst düzey pencere: yalnız iletiler için (HWND_MESSAGE TaskbarCreated yayınını almaz).
            self._hwnd = win32gui.CreateWindow(
                atom,
                "Tahta Kontrol durum simgesi",
                win32con.WS_OVERLAPPED | win32con.WS_SYSMENU,
                0,
                0,
                win32con.CW_USEDEFAULT,
                win32con.CW_USEDEFAULT,
                0,
                0,
                sinif.hInstance,
                None,
            )
            self._ekle()
        except Exception:
            logging.exception("Bildirim alanı simgesi kurulamadı")
            self._hwnd = 0
            self._hazir.set()
            return
        self._hazir.set()
        try:
            win32gui.PumpMessages()
        finally:
            self._hwnd = 0
            try:  # sınıfın ileti haritası bu nesneye bağlı: aynı süreçte yeni bir Tepsi kurulabilsin
                win32gui.UnregisterClass(atom, sinif.hInstance)
            except Exception:
                pass
            if not self._kapatiliyor:
                # İleti döngüsü istenmeden bitti: simge yok. Tk tarafı bunu bilmezse gizli pencere ve süreç
                # görünmez kalır, tek örnek engeli de yeni açılışı engeller.
                logging.warning("Bildirim alanı simgesi beklenmedik biçimde kapandı.")
                self.olaylar.put(("simge_kapandi",))

    def _simge(self, tur: str) -> int:
        if tur in self._simgeler:
            return self._simgeler[tur]
        import win32api
        import win32con
        import win32gui

        boyut = win32api.GetSystemMetrics(win32con.SM_CXSMICON)
        tutamac = 0
        for yol in simge_adaylari(tur):
            try:
                tutamac = win32gui.LoadImage(0, str(yol), win32con.IMAGE_ICON, boyut, boyut, win32con.LR_LOADFROMFILE)
            except Exception:
                tutamac = 0
            if tutamac:
                break
        if not tutamac:
            tutamac = win32gui.LoadIcon(0, win32con.IDI_APPLICATION)
        self._simgeler[tur] = tutamac
        return tutamac

    def _kayit(self, bayraklar: int) -> tuple:
        with self._kilit:
            tur, ipucu = self._tur, self._ipucu
        return (self._hwnd, _SIMGE_KIMLIGI, bayraklar, WM_TEPSI, self._simge(tur), ipucu)

    def _ekle(self) -> None:
        """NIM_ADD; düşerse simge belki zaten vardır (Shell_NotifyIcon zaman aşımına düşüp yine de eklemiş ya da
        değiştirmiş olabilir): NIM_MODIFY tutarsa simge alandadır. İkisi de düşerse sonraki güncellemede,
        balonda ya da TaskbarCreated'da yeniden denenir (hiçbir hata simgeyi kalıcı "eklenmedi"ye kilitlemez)."""
        import win32gui

        kayit = self._kayit(win32gui.NIF_ICON | win32gui.NIF_MESSAGE | win32gui.NIF_TIP)
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_ADD, kayit)
            self._eklendi = True
            return
        except Exception:
            pass
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, kayit)
            self._eklendi = True
        except Exception:  # görev çubuğu henüz hazır değil
            self._eklendi = False
            logging.warning("Bildirim alanına simge eklenemedi; görev çubuğu hazır olunca yeniden denenecek.")

    def _yeniden_ekle(self, hwnd, ileti, wparam, lparam) -> int:
        self._ekle()  # Explorer yeniden başladı
        return 0

    def _guncelle_ileti(self, hwnd, ileti, wparam, lparam) -> int:
        import win32gui

        if self._eklendi:
            try:
                win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, self._kayit(win32gui.NIF_ICON | win32gui.NIF_TIP))
                return 0
            except Exception:  # tek hata "simge yok" demek değildir: _ekle önce ADD, sonra MODIFY dener
                pass
        self._ekle()
        return 0

    def _balon_ileti(self, hwnd, ileti, wparam, lparam) -> int:
        import win32gui

        with self._kilit:
            balon, self._balon = self._balon, None
        if not balon:
            return 0
        if not self._eklendi:
            self._ekle()
        if not self._eklendi:
            logging.warning("Simge alanda değil; balon bildirimi gösterilemedi.")
            return 0
        metin, uyari = balon
        kayit = self._kayit(win32gui.NIF_INFO) + (
            metin[:255],
            10000,
            BALON_BASLIK,
            win32gui.NIIF_WARNING if uyari else win32gui.NIIF_INFO,
        )
        try:
            win32gui.Shell_NotifyIcon(win32gui.NIM_MODIFY, kayit)
        except Exception:
            logging.warning("Balon bildirimi gösterilemedi.")
        return 0

    def _bildirim(self, hwnd, ileti, wparam, lparam) -> int:
        import win32con

        if lparam in (win32con.WM_LBUTTONDBLCLK, _NIN_SELECT, _NIN_KEYSELECT):
            self.olaylar.put(("menu", "goster"))
        elif lparam in (win32con.WM_RBUTTONUP, win32con.WM_CONTEXTMENU):
            self._menu_ac()
        return 0

    def _menu_ac(self) -> None:
        import win32con
        import win32gui

        with self._kilit:
            ogeler = list(self._menu)
        menu = win32gui.CreatePopupMenu()
        anahtarlar: dict[int, str] = {}
        try:
            for sira, (anahtar, etiket, etkin) in enumerate(ogeler):
                if anahtar == "-":
                    win32gui.AppendMenu(menu, win32con.MF_SEPARATOR, 0, "")
                    continue
                kimlik = _KOMUT_TABANI + sira
                anahtarlar[kimlik] = anahtar
                win32gui.AppendMenu(menu, win32con.MF_STRING | (0 if etkin else win32con.MF_GRAYED), kimlik, etiket)
                if anahtar == "goster":
                    win32gui.SetMenuDefaultItem(menu, kimlik, 0)
            x, y = win32gui.GetCursorPos()
            try:
                win32gui.SetForegroundWindow(self._hwnd)  # menü dışına tıklanınca kapansın
            except Exception:
                pass
            secim = win32gui.TrackPopupMenu(
                menu,
                win32con.TPM_LEFTALIGN | win32con.TPM_RIGHTBUTTON | win32con.TPM_BOTTOMALIGN
                | win32con.TPM_RETURNCMD | win32con.TPM_NONOTIFY,
                x,
                y,
                0,
                self._hwnd,
                None,
            )
            win32gui.PostMessage(self._hwnd, win32con.WM_NULL, 0, 0)
        finally:
            win32gui.DestroyMenu(menu)
        if secim in anahtarlar:
            self.olaylar.put(("menu", anahtarlar[secim]))

    def _goster_ileti(self, hwnd, ileti, wparam, lparam) -> int:
        self.olaylar.put(("menu", "goster"))
        return 0

    def _kapatma_istegi(self, hwnd, ileti, wparam, lparam) -> int:
        self.olaylar.put(("menu", "cik"))  # Tk "Çık" ile kapatır; o da kapat() → WM_KAPAT
        return 0

    def _kapat_ileti(self, hwnd, ileti, wparam, lparam) -> int:
        import win32gui

        win32gui.DestroyWindow(hwnd)
        return 0

    def _yok_edildi(self, hwnd, ileti, wparam, lparam) -> int:
        import win32gui

        try:  # _eklendi False olsa da simge alanda olabilir (zaman aşımı): her zaman kaldırmayı dene
            win32gui.Shell_NotifyIcon(win32gui.NIM_DELETE, (hwnd, _SIMGE_KIMLIGI))
        except Exception:
            pass
        self._eklendi = False
        for tutamac in self._simgeler.values():
            try:
                win32gui.DestroyIcon(tutamac)
            except Exception:
                pass
        self._simgeler.clear()
        self._hwnd = 0
        win32gui.PostQuitMessage(0)
        return 0
