"""İşletim sistemine dokunan her şey bu modüldedir.

Ajanın geri kalanı platformdan habersizdir; yeni bir platform (ör. Windows'lu
tahta) eklemek bu dosyadaki işlevlerin karşılığını yazmaktır.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import uuid

LINUX = sys.platform.startswith("linux")
STANDART_HESAPLAR = ("etapadmin", "ogretmen", "ogrenci")
# Ders yoklaması kısayolu (A5; paketle gelir). Menüde "Yoklama Al" adıyla görünür.
YOKLAMA_KISAYOLU = "/usr/share/applications/tahta-yoklama.desktop"


def calistir(komut: list[str], zaman_asimi: float = 8) -> tuple[int | None, str]:
    """Komutu çalıştırır; (çıkış kodu, çıktı). Çalışmazsa kod None olur."""
    try:
        sonuc = subprocess.run(
            komut, capture_output=True, text=True, timeout=zaman_asimi, errors="replace"
        )
    except (OSError, subprocess.SubprocessError) as hata:
        return None, f"{type(hata).__name__}: {hata}"
    return sonuc.returncode, (sonuc.stdout + sonuc.stderr).strip()[:6000]


def platform_adi() -> str:
    if LINUX:
        try:
            with open("/etc/os-release", encoding="utf-8") as dosya:
                for satir in dosya:
                    if satir.startswith("PRETTY_NAME="):
                        return satir.split("=", 1)[1].strip().strip('"')
        except OSError:
            pass
    return f"{platform.system()} {platform.release()}"


def ag_bilgisi(sunucu_makine: str, sunucu_port: int) -> dict:
    """Sunucuya giden yolda kullanılan yerel IP, arayüz ve MAC."""
    bilgi = {"ip": "", "arayuz": "", "mac": "", "kablosuz": None}
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as soket:
            soket.connect((sunucu_makine, sunucu_port))
            bilgi["ip"] = soket.getsockname()[0]
    except OSError:
        pass
    if LINUX and bilgi["ip"]:
        try:
            for ad in os.listdir("/sys/class/net"):
                kod, cikti = calistir(["ip", "-o", "-4", "addr", "show", "dev", ad], 3)
                if kod == 0 and f" {bilgi['ip']}/" in cikti:
                    bilgi["arayuz"] = ad
                    with open(f"/sys/class/net/{ad}/address", encoding="ascii") as dosya:
                        bilgi["mac"] = dosya.read().strip()
                    bilgi["kablosuz"] = os.path.isdir(f"/sys/class/net/{ad}/wireless")
                    break
        except OSError:
            pass
    if not bilgi["mac"]:
        dugum = uuid.getnode()
        if not (dugum >> 40) & 1:  # rastgele üretilmiş değilse
            bilgi["mac"] = ":".join(f"{(dugum >> k) & 0xFF:02x}" for k in range(40, -8, -8))
    return bilgi


def etkin_oturum() -> dict:
    """Ekrandaki oturum: tür (x11/wayland) ve hesap SINIFI.

    Kişisel hesap adları öğretmenin kimliğini taşıyabildiği için sunucuya ad
    gönderilmez; yalnız standart hesap adı ya da "kisisel" bildirilir.
    """
    sonuc = {"sinif": "yok", "tur": ""}
    if not LINUX or not shutil.which("loginctl"):
        if not LINUX:
            sonuc["sinif"] = "windows"
        return sonuc
    kod, cikti = calistir(["loginctl", "list-sessions", "--no-legend"], 5)
    if kod != 0:
        return sonuc
    for satir in cikti.splitlines():
        parcalar = satir.split()
        if not parcalar:
            continue
        kod2, ayrinti = calistir(
            ["loginctl", "show-session", parcalar[0], "-p", "Type", "-p", "Active", "-p", "Name", "-p", "Class"],
            5,
        )
        if kod2 != 0:
            continue
        alan = dict(s.split("=", 1) for s in ayrinti.splitlines() if "=" in s)
        if alan.get("Active") == "yes" and alan.get("Class") == "user" and alan.get("Type") in ("x11", "wayland"):
            ad = alan.get("Name", "")
            sonuc["sinif"] = ad if ad in STANDART_HESAPLAR else "kisisel"
            sonuc["tur"] = alan.get("Type", "")
            break
    return sonuc


def acik_sure() -> int:
    if LINUX:
        try:
            with open("/proc/uptime", encoding="ascii") as dosya:
                return int(float(dosya.read().split()[0]))
        except (OSError, ValueError):
            pass
    return int(time.monotonic())


def _guc_komutu(eylem: str) -> tuple[bool, str]:
    if not LINUX:
        if os.environ.get("TAHTA_AJAN_GERCEK_GUC") != "1":
            return True, f"Benzetim: {eylem} komutu bu platformda uygulanmadı."
        bayrak = "/s" if eylem == "poweroff" else "/r"
        kod, cikti = calistir(["shutdown", bayrak, "/t", "5"], 10)
        return kod == 0, cikti
    if os.environ.get("TAHTA_AJAN_BENZETIM") == "1":
        return True, f"Benzetim: systemctl {eylem} çağrılmadı."
    if shutil.which("systemctl"):
        kod, cikti = calistir(["systemctl", eylem], 15)
        if kod == 0:
            return True, cikti or "Komut verildi."
        yedek = "-h" if eylem == "poweroff" else "-r"
        kod2, cikti2 = calistir(["shutdown", yedek, "now"], 15)
        return kod2 == 0, (cikti + "\n" + cikti2).strip()
    kod, cikti = calistir(["shutdown", "-h" if eylem == "poweroff" else "-r", "now"], 15)
    return kod == 0, cikti


def kapat() -> tuple[bool, str]:
    return _guc_komutu("poweroff")


def yeniden_baslat() -> tuple[bool, str]:
    return _guc_komutu("reboot")


def paket_kur(yol: str) -> tuple[bool, str]:
    """İndirilen ajan paketini kurar.

    Kurulum ajanı yeniden başlatır; bu yüzden işlem servisten bağımsız bir
    birimde koşturulur, yoksa servis durunca kurulum da yarıda kalır.
    """
    if not LINUX:
        return False, "Paket kurulumu bu platformda tanımlı değil."
    if not shutil.which("dpkg"):
        return False, "dpkg bulunamadı."
    if os.path.isdir("/run/systemd/system") and shutil.which("systemd-run"):
        birim = f"tahta-ajan-guncelle-{int(time.time())}"
        kod, cikti = calistir(["systemd-run", "--unit", birim, "--collect", "dpkg", "-i", yol], 20)
        return kod == 0, cikti or "Kurulum başlatıldı."
    try:
        subprocess.Popen(["dpkg", "-i", yol], start_new_session=True)
    except OSError as hata:
        return False, str(hata)
    return True, "Kurulum başlatıldı."
