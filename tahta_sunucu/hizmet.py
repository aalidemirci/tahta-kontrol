"""Windows hizmeti kabuğu: `TahtaKontrol.exe hizmet` (Hizmet Denetim Yöneticisi başlatır).

Bu modülün içe aktarımı pywin32 İSTEMEZ (testler ve Linux için); pywin32 yalnız
`hizmet_sinifi()` ve `calistir()` içinde, gerçekten hizmet olarak çalışırken yüklenir.
Hizmetin işi `govde()`'dedir; o saf Python'dur ve testle denenir.

Hizmet hesabı Yerel Hizmet'tir (LocalService); veri `%PROGRAMDATA%\\TahtaKontrol`
(ayar.veri_dizini_sec), günlük `gunluk\\sunucu.log` (5 MB × 3).
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import threading
from collections.abc import Callable
from pathlib import Path

from . import ayar, tasima

gunluk = logging.getLogger("tahta-sunucu")

GUNLUK_BOYUT = 5 * 1024 * 1024
GUNLUK_SAYI = 3
DURDURMA_SURESI_MS = 20000  # Sunucu.durdur iki iş parçacığını en çok 8'er sn bekler

# govde() çıkış kodları
TAMAM = 0  # durduruldu (net stop, kapanış)
TASIMA_BEKLIYOR = 3  # eski veri taşınamadı: açılmadı, yeniden de denenmez
HATA = 1  # açılamadı ya da çöktü: hizmet yöneticisi yeniden başlatır (sc failure)


def hizmet_kipine_gec() -> None:
    """Bu süreç hizmettir: geri yüklemede süreç çıkışı ve /yerel/durum `hizmet` alanı buna bakar."""
    os.environ["TAHTA_HIZMET"] = "1"
    ayar.HIZMET = True


YENIDEN_BASLAT_KODU = 75


def _cik(kod: int) -> None:
    logging.shutdown()
    os._exit(kod)


def yeniden_baslat_planla(gecikme: float = 2.0) -> threading.Timer:
    """Onaylanan geri yüklemeden sonra hizmet kipinde süreci 75 koduyla bitirir.

    Yanıt tarayıcıya gitsin diye kısa bir gecikme verilir. Hizmet yöneticisi süreci
    beklenmedik çıkış sayar ve 5 sn sonra yeniden başlatır (sc failure); bekleyen yedek
    açılışta, veritabanı açılmadan yerleştirilir (yedek.bekleyeni_uygula).
    """
    zamanlayici = threading.Timer(gecikme, _cik, (YENIDEN_BASLAT_KODU,))
    zamanlayici.daemon = True
    zamanlayici.start()
    return zamanlayici


def gunluk_kur(veri: Path) -> logging.Handler:
    dizin = veri / "gunluk"
    dizin.mkdir(parents=True, exist_ok=True)
    isleyici = logging.handlers.RotatingFileHandler(
        dizin / "sunucu.log", maxBytes=GUNLUK_BOYUT, backupCount=GUNLUK_SAYI, encoding="utf-8"
    )
    isleyici.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    kok = logging.getLogger()
    kok.setLevel(logging.INFO)
    kok.addHandler(isleyici)
    return isleyici


def _varsayilan_sunucu():
    from .sunucu import Sunucu

    return Sunucu()


def govde(
    durdu: threading.Event,
    sunucu_uret: Callable[[], object] = _varsayilan_sunucu,
    bildir: Callable[[str, bool], None] | None = None,
    aralik: float = 1.0,
) -> int:
    """Hizmetin bütün işi: aç, durdurma isteğine ya da çökmeye kadar bekle, kapat.

    `bildir(metin, hata_mi)` Olay Görüntüleyicisi'ne yazar (hizmet kipinde).
    """
    hizmet_kipine_gec()
    veri = ayar.veri_dizini()

    def _bildir(metin: str, hata: bool) -> None:
        (gunluk.error if hata else gunluk.info)(metin)
        if bildir:
            try:
                bildir(metin, hata)
            except Exception:  # olay günlüğü yazılamasa da hizmet sürer
                pass

    if tasima.bekliyor_mu(veri):
        _bildir(
            f"Tahta Kontrol açılmadı: eski veri taşınmayı bekliyor ({veri / tasima.BEKLIYOR}) ya da taşıma "
            f"yarıda kalmış ({veri / tasima.SURUYOR}; kurucuyu yeniden çalıştırın). "
            "Yeni sertifika üretilip tahtalar koparılmasın diye sunucu başlatılmadı.",
            True,
        )
        return TASIMA_BEKLIYOR
    try:
        sunucu = sunucu_uret()
        sunucu.baslat()
    except Exception as hata:
        gunluk.exception("Sunucu başlatılamadı")
        _bildir(f"Tahta Kontrol sunucusu başlatılamadı: {hata}", True)
        return HATA
    _bildir(f"Tahta Kontrol sunucusu çalışıyor (veri: {veri}).", False)
    kod = TAMAM
    try:
        while not durdu.wait(aralik):
            if not sunucu.calisiyor_mu():
                _bildir("Tahta Kontrol sunucusu beklenmedik biçimde durdu.", True)
                kod = HATA
                break
    finally:
        sunucu.durdur()
    gunluk.info("Tahta Kontrol sunucusu durduruldu.")
    return kod


def konsol() -> int:
    """Hizmet kipini hizmet yöneticisi olmadan uçbirimde dener (Ctrl+C ile durur).

    Geliştirme ve saha tanısı içindir: ayrı veri dizini (TAHTA_VERI_DIZINI) ve
    kapılarla (TAHTA_HTTP_PORT/TAHTA_HTTPS_PORT) kurulu hizmete dokunmadan çalışır.
    """
    hizmet_kipine_gec()
    gunluk_kur(ayar.veri_dizini())
    logging.getLogger().addHandler(logging.StreamHandler())
    durdu = threading.Event()
    try:
        return govde(durdu)
    except KeyboardInterrupt:
        durdu.set()
        return TAMAM


# ---- pywin32 (yalnız Windows'ta, hizmet olarak çalışırken) -------------------------------
def hizmet_sinifi():
    import servicemanager
    import win32service
    import win32serviceutil

    class TahtaKontrolHizmeti(win32serviceutil.ServiceFramework):
        _svc_name_ = ayar.HIZMET_ADI
        _svc_display_name_ = "Tahta Kontrol Sunucusu"
        _svc_description_ = "Okul ağındaki etkileşimli tahtaların kontrol sunucusu."

        def __init__(self, args):
            super().__init__(args)
            self.durdu = threading.Event()

        def SvcStop(self):  # noqa: N802 - pywin32 adı
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING, waitHint=DURDURMA_SURESI_MS)
            self.durdu.set()

        def SvcShutdown(self):  # noqa: N802 - bilgisayar kapanıyor
            self.SvcStop()

        def SvcDoRun(self):  # noqa: N802
            def bildir(metin: str, hata: bool) -> None:
                (servicemanager.LogErrorMsg if hata else servicemanager.LogInfoMsg)(metin)

            try:
                gunluk_kur(ayar.veri_dizini())
            except OSError:
                pass  # günlük yazılamıyorsa olay günlüğü yine çalışır
            kod = govde(self.durdu, bildir=bildir)
            logging.shutdown()
            if kod == HATA:
                # Hatayla durur; hizmet yöneticisi "sc failure" eylemleriyle yeniden başlatır
                # (failureflag 1). pywin32 istisnayı yakalayıp hizmeti hata koduyla durdurur.
                raise RuntimeError("Tahta Kontrol sunucusu çalışamadı; ayrıntı: gunluk/sunucu.log")

    return TahtaKontrolHizmeti


def calistir() -> int:
    """Hizmet yöneticisinin başlattığı süreç. Elle çalıştırılırsa (1063) sessizce 2 döner."""
    hizmet_kipine_gec()
    import pywintypes
    import servicemanager

    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(hizmet_sinifi())
    try:
        servicemanager.StartServiceCtrlDispatcher()
    except pywintypes.error as hata:
        if getattr(hata, "winerror", None) == 1063:  # ERROR_FAILED_SERVICE_CONTROLLER_CONNECT
            return 2
        raise
    return 0
