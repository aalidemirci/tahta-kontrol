"""Masaüstü durum penceresi (kısayolların açtığı).

Kurulu programda sunucu bir Windows hizmetidir (tahta_sunucu.hizmet); pencere onu
BAŞLATMAZ, yalnız durumunu gösterir ve paneli açar. Pencereyi kapatmak sunucuyu
durdurmaz. Kip, açılışta `/yerel/durum` yanıtına ve hizmetin durumuna göre seçilir:

- calisiyor          : sunucu yanıt veriyor (hizmet ya da geliştirme sunucusu) → bilgi.
- hizmet_calismiyor  : hizmet kurulu ama yanıt yok → "Hizmeti başlat" (UAC sorar).
- kurulu_degil       : paketli program ama hizmet yok → yeniden kurun (sunucu açılmaz;
                       hizmetle çift çalışma olmasın).
- gelistirme         : `uv run … pencere` → sunucuyu pencere içinde çalıştırır (eski davranış).

Pencere hizmetin veri dizinine (ProgramData) dokunmaz; kendi günlüğü
`%LOCALAPPDATA%\\TahtaKontrol\\pencere.log`'dur.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import sys
import time
import tkinter as tk
import urllib.request
import webbrowser
from tkinter import messagebox

from . import __version__, ayar

DURUMLAR = (
    "STOPPED",
    "START_PENDING",
    "STOP_PENDING",
    "RUNNING",
    "CONTINUE_PENDING",
    "PAUSE_PENDING",
    "PAUSED",
)
_DURUM_DESENI = re.compile(r":\s*(\d+)\s+(" + "|".join(DURUMLAR) + r")\b")
HIZMET_YOK_KODU = 1060  # ERROR_SERVICE_DOES_NOT_EXIST
DURUM_TURKCE = {
    "STOPPED": "durdurulmuş",
    "START_PENDING": "başlatılıyor",
    "STOP_PENDING": "durduruluyor",
    "RUNNING": "çalışıyor ama yanıt vermiyor",
    "PAUSED": "duraklatılmış",
}
SON_YEDEK_ESKI_SN = 3 * 86400
ACILIS_BEKLEME_SN = 20


# ---- saf mantık (testli) ----------------------------------------------------------------
def sc_durumu_coz(cikti: str, cikis_kodu: int) -> str | None:
    """`sc.exe query TahtaKontrol` çıktısından durum. Hizmet yoksa "yok", anlaşılmazsa None.

    sc.exe alan adları her dilde İngilizcedir ("STATE : 4 RUNNING"); yine de yalnız sayı +
    durum adı deseni aranır.
    """
    if cikis_kodu == HIZMET_YOK_KODU:
        return "yok"
    eslesme = _DURUM_DESENI.search(cikti or "")
    return eslesme.group(2) if eslesme else None


_CIKIS_DESENI = re.compile(r"SERVICE_EXIT_CODE\s*:\s*(\d+)")
# Hizmetin kendi çıkış kodları (hizmet.py) → durum penceresi açıklaması.
HIZMET_CIKIS_ACIKLAMASI = {
    3: "eski veri taşınmayı bekliyor ya da taşıma yarıda kalmış (TASIMA-BEKLIYOR.txt / TASIMA-SURUYOR.txt)",
}


def sc_cikis_kodu_coz(cikti: str) -> int | None:
    """`sc.exe query` çıktısındaki SERVICE_EXIT_CODE (hizmetin kendi çıkış kodu); yoksa None."""
    eslesme = _CIKIS_DESENI.search(cikti or "")
    return int(eslesme.group(1)) if eslesme else None


def kip_sec(durum: dict | None, hizmet_durumu: str | None, paketli: bool) -> str:
    if durum is not None:
        return "calisiyor"
    if hizmet_durumu not in (None, "yok"):
        return "hizmet_calismiyor"
    if paketli:
        return "kurulu_degil"
    return "gelistirme"


def uyarilar(durum: dict, simdi: float | None = None) -> list[str]:
    """Durum penceresinde gösterilecek uyarılar (sır içermez)."""
    simdi = time.time() if simdi is None else simdi
    sonuc = []
    if not durum.get("yedek_parolasi_var"):
        sonuc.append("Yedek parolası belirlenmedi; otomatik yedek alınmıyor (Panel → Yedekler).")
    else:
        son = durum.get("son_yedek") or {}
        if son.get("basarili") is False:
            sonuc.append("Son yedek alınamadı (Panel → Yedekler).")
        elif not son.get("zaman") or simdi - float(son["zaman"]) > SON_YEDEK_ESKI_SN:
            sonuc.append("Son üç günde yedek alınmadı (Panel → Yedekler).")
    if durum.get("hizmet"):
        sonuc.append(
            "Bu bilgisayar uykuya geçerse tahtalar çevrimdışı kalır; güç ayarlarında uykuyu kapatın."
        )
    return sonuc


# ---- işletim sistemi ----------------------------------------------------------------------
def yerel_durum_oku(zaman_asimi: float = 2.0) -> dict | None:
    adres = f"http://127.0.0.1:{ayar.HTTP_PORT}/yerel/durum"
    try:
        with urllib.request.urlopen(adres, timeout=zaman_asimi) as yanit:  # noqa: S310 - sabit yerel adres
            return json.loads(yanit.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def _sc_sorgu() -> tuple[str, int] | None:
    if not sys.platform.startswith("win"):
        return None
    try:
        sonuc = subprocess.run(
            ["sc.exe", "query", ayar.HIZMET_ADI],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return sonuc.stdout, sonuc.returncode


def hizmet_durumu() -> str | None:
    sorgu = _sc_sorgu()
    return sc_durumu_coz(*sorgu) if sorgu else None


def hizmet_cikis_kodu() -> int | None:
    sorgu = _sc_sorgu()
    return sc_cikis_kodu_coz(sorgu[0]) if sorgu else None


def hizmeti_baslat() -> None:
    """Yönetici onayı (UAC) isteyerek `sc start TahtaKontrol` çalıştırır. ShellExecuteW istisna fırlatmaz:
    32 ya da küçük dönüş başarısızlıktır (5: UAC'de "Hayır" ya da erişim reddi) → OSError."""
    import ctypes

    kod = int(ctypes.windll.shell32.ShellExecuteW(None, "runas", "sc.exe", f"start {ayar.HIZMET_ADI}", None, 0))
    if kod <= 32:
        neden = "yönetici onayı verilmedi" if kod == 5 else f"Windows hata kodu {kod}"
        raise OSError(f"sc.exe çalıştırılamadı ({neden}).")


def baslatma_sonucu_metni(durum: str | None, cikis_kodu: int | None) -> str | None:
    """"Hizmeti başlat"tan birkaç saniye sonra hizmet hâlâ çalışmıyorsa gösterilecek metin; çalışıyorsa None."""
    if durum in ("RUNNING", "START_PENDING"):
        return None
    metin = "Hizmet başlatılamadı ya da hemen durdu."
    if cikis_kodu:
        metin += f" Hizmetin çıkış kodu: {cikis_kodu}"
        if cikis_kodu in HIZMET_CIKIS_ACIKLAMASI:
            metin += f" ({HIZMET_CIKIS_ACIKLAMASI[cikis_kodu]})"
        metin += "."
    return metin + f"\n\nAyrıntı (yönetici olarak): {ayar.hizmet_veri_dizini()}\\gunluk\\sunucu.log"


# ---- pencere ------------------------------------------------------------------------------
def _gunluk_kur() -> None:
    if ayar.paketli_windows():
        dizin = ayar.eski_veri_dizini()  # kullanıcının kendi klasörü; hizmetin verisi değil
        dizin.mkdir(parents=True, exist_ok=True)
        dosya = dizin / "pencere.log"
    else:
        dosya = ayar.veri_dizini() / "sunucu.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        filename=str(dosya),
        encoding="utf-8",
    )


def _baslik(cerceve, metin: str, alt: str = "") -> None:
    tk.Label(cerceve, text=metin, font=("Segoe UI", 14, "bold"), justify="left").pack(anchor="w")
    if alt:
        tk.Label(cerceve, text=alt, fg="#555", justify="left").pack(anchor="w", pady=(0, 12))


def _adresler(cerceve, yerel: str, ag: list[str]) -> None:
    tk.Label(cerceve, text="Bu bilgisayardan panel adresi:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
    tk.Label(cerceve, text=yerel, fg="#1d4ed8").pack(anchor="w", pady=(0, 8))
    tk.Label(cerceve, text="Diğer idari bilgisayarlardan panel adresi:", font=("Segoe UI", 9, "bold")).pack(
        anchor="w"
    )
    for adres in ag or ["(ağ bağlantısı bulunamadı)"]:
        kutu = tk.Entry(cerceve, width=42, relief="flat", fg="#1d4ed8")
        kutu.insert(0, adres)
        kutu.configure(state="readonly")
        kutu.pack(anchor="w")
    tk.Label(
        cerceve,
        text=(
            "Diğer bilgisayarlarda tarayıcı ilk açılışta sertifika uyarısı gösterir;\n"
            '"Gelişmiş" → "siteye ilerle" ile devam edilir.'
        ),
        fg="#555",
        justify="left",
    ).pack(anchor="w", pady=(4, 10))


def calistir() -> int:
    _gunluk_kur()
    while True:
        sonuc = _bir_kez()
        if sonuc != "yeniden":
            return int(sonuc)


def _bir_kez() -> int | str:
    durum = yerel_durum_oku()
    hizmet = hizmet_durumu() if durum is None else None
    bitis = time.time() + ACILIS_BEKLEME_SN
    while durum is None and hizmet in ("START_PENDING", "RUNNING") and time.time() < bitis:
        # Hizmet yeni başladıysa sunucu birkaç saniyede yanıt verir (ilk açılışta sertifika üretir).
        time.sleep(1)
        durum = yerel_durum_oku()
        hizmet = hizmet_durumu() if durum is None else None
    kip = kip_sec(durum, hizmet, ayar.paketli_windows())
    logging.info("Durum penceresi: %s", kip)
    if kip == "gelistirme":
        return _gelistirme_penceresi()

    kok = tk.Tk()
    kok.title("Tahta Kontrol")
    kok.resizable(False, False)
    cerceve = tk.Frame(kok, padx=22, pady=18)
    cerceve.pack()
    yerel = f"http://127.0.0.1:{ayar.HTTP_PORT}"
    dugmeler = tk.Frame(cerceve)
    sonuc: list[int | str] = [0]

    def yeniden(gecikme_ms: int = 0) -> None:
        sonuc[0] = "yeniden"
        kok.after(gecikme_ms, kok.destroy)

    if kip == "calisiyor":
        assert durum is not None
        ek = " (Windows hizmeti)" if durum.get("hizmet") else ""
        _baslik(
            cerceve, f"Tahta Kontrol sunucusu çalışıyor{ek}", f"Sürüm {durum.get('surum') or __version__}"
        )
        _adresler(cerceve, yerel, list(durum.get("ag_adresleri") or []))
        for metin in uyarilar(durum):
            tk.Label(cerceve, text="• " + metin, fg="#92400e", justify="left", wraplength=420).pack(
                anchor="w"
            )
        tk.Label(cerceve, text="Bu pencereyi kapatmak sunucuyu durdurmaz.", fg="#555", justify="left").pack(
            anchor="w", pady=(10, 12)
        )
        dugmeler.pack(anchor="w")
        tk.Button(dugmeler, text="Paneli aç", width=16, command=lambda: webbrowser.open(yerel)).pack(
            side="left"
        )
    elif kip == "hizmet_calismiyor":
        _baslik(
            cerceve,
            "Sunucu hizmeti çalışmıyor",
            f"Hizmet durumu: {DURUM_TURKCE.get(hizmet or '', hizmet or 'bilinmiyor')} · pencere sürümü {__version__}",
        )
        tk.Label(
            cerceve,
            text=(
                "Tahtalar çevrimdışı; kilitler 90 saniye sonra tahtadan açılabilir.\n\n"
                "Ayrıntı: Olay Görüntüleyicisi > Windows Günlükleri > Uygulama, ya da yönetici olarak\n"
                f"{ayar.hizmet_veri_dizini()}\\gunluk\\sunucu.log\n"
                "Kurulumdan sonra hiç açılmadıysa eski veri taşınmayı bekliyor olabilir:\n"
                f"{ayar.hizmet_veri_dizini()}\\TASIMA-BEKLIYOR.txt"
            ),
            justify="left",
        ).pack(anchor="w", pady=(0, 12))
        dugmeler.pack(anchor="w")

        def baslat():
            try:
                hizmeti_baslat()
            except Exception as hata:  # UAC reddi ya da Windows dışı
                messagebox.showerror("Tahta Kontrol", f"Hizmet başlatılamadı:\n\n{hata}")
                return

            def denetle():
                if yerel_durum_oku(1.0) is None:
                    metin = baslatma_sonucu_metni(hizmet_durumu(), hizmet_cikis_kodu())
                    if metin:
                        messagebox.showwarning("Tahta Kontrol", metin)
                yeniden(0)

            kok.after(6000, denetle)

        tk.Button(dugmeler, text="Hizmeti başlat", width=16, command=baslat).pack(side="left")
        tk.Button(dugmeler, text="Yeniden dene", width=14, command=yeniden).pack(side="left", padx=8)
    else:  # kurulu_degil
        _baslik(
            cerceve,
            "Sunucu hizmeti kurulu değil",
            "Tahta Kontrol kurucusunu yeniden çalıştırın; kurucu hizmeti kaydeder ve başlatır.",
        )
        dugmeler.pack(anchor="w")
    tk.Button(dugmeler, text="Kapat", width=12, command=kok.destroy).pack(side="left", padx=(8, 0))
    kok.mainloop()
    return sonuc[0]


def _gelistirme_penceresi() -> int:
    """Hizmet yokken (geliştirme) sunucuyu pencere içinde çalıştırır; pencere kapanınca sunucu durur."""
    from .sunucu import Sunucu

    kok = tk.Tk()
    kok.title("Tahta Kontrol")
    kok.resizable(False, False)
    try:
        sunucu = Sunucu()
        sunucu.baslat()
    except Exception as hata:  # pencere açılamadan önce kullanıcıya gösterilir
        logging.exception("Sunucu başlatılamadı")
        kok.withdraw()
        messagebox.showerror("Tahta Kontrol", f"Sunucu başlatılamadı:\n\n{hata}")
        return 1

    cerceve = tk.Frame(kok, padx=22, pady=18)
    cerceve.pack()
    _baslik(cerceve, "Tahta Kontrol sunucusu çalışıyor (geliştirme)", f"Sürüm {__version__}")
    _adresler(cerceve, sunucu.yerel_adres, sunucu.ag_adresleri())
    dugmeler = tk.Frame(cerceve)
    dugmeler.pack(anchor="w")
    tk.Button(dugmeler, text="Paneli aç", width=16, command=lambda: webbrowser.open(sunucu.yerel_adres)).pack(
        side="left"
    )
    tk.Button(dugmeler, text="Simge durumuna küçült", width=22, command=kok.iconify).pack(side="left", padx=8)

    def kapat():
        if messagebox.askyesno(
            "Tahta Kontrol",
            "Sunucu durdurulursa tahtalar çevrimdışı kalır ve panel açılmaz.\n\nSunucu durdurulsun mu?",
        ):
            sunucu.durdur()
            kok.destroy()

    tk.Button(dugmeler, text="Sunucuyu durdur", width=16, command=kapat).pack(side="left")
    kok.protocol("WM_DELETE_WINDOW", kapat)
    kok.mainloop()
    return 0
