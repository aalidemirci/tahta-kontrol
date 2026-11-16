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
# Arıza bildirimi kısayolu (A6; paketle gelir). Menüde "Arıza bildir" adıyla görünür.
ARIZA_KISAYOLU = "/usr/share/applications/tahta-ariza.desktop"


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


# ---- envanter (A6): donanım ve yazılım okumaları ------------------------------------
# Yalnız CİHAZ verisi okunur: kullanıcı/hesap adları, ev dizinleri, dosya adları, makine adı
# ve açık kalma süresi gibi oynak değerler okunmaz (kural 6). `kok` yalnız testler içindir.
DMI_ALANLARI = (
    "sys_vendor", "product_name", "product_version", "product_serial", "board_vendor", "board_name",
    "board_serial", "bios_vendor", "bios_version", "bios_date",
)  # fmt: skip
ETAP_ONEKLERI = ("eta-", "etap", "pardus-lightdm", "pardus-eta", "ahenk")
ETAP_PAKET_EN_COK = 30


def _ilk_satir(yol: str, sinir: int = 200) -> str:
    try:
        with open(yol, encoding="utf-8", errors="replace") as dosya:
            return " ".join(dosya.readline(sinir).split())
    except OSError:
        return ""


def _yol(kok: str, *parcalar: str) -> str:
    return os.path.join(kok, *parcalar)


def etap_paketleri() -> list[str]:
    """ETAP'a özgü paketler ("ad sürüm"), en çok 30; dpkg-query yoksa boş liste."""
    if not shutil.which("dpkg-query"):
        return []
    kod, cikti = calistir(["dpkg-query", "-W", "-f", "${Package} ${Version}\n"], 15)
    if kod != 0:
        return []
    return [s.strip() for s in cikti.splitlines() if s.startswith(ETAP_ONEKLERI)][:ETAP_PAKET_EN_COK]


def donanim_bilgisi(kok: str = "/") -> dict:
    """Ham donanım okumaları. Her alan ayrı denenir; okunamayan alan boş kalır.

    Seri numaraları (product_serial, board_serial) yalnız root okuyabilir; servis root'tur.
    Yer tutucu seri numaralarının ayıklanması envanter.py'dedir (platformdan bağımsız kural).
    """
    if not LINUX and kok == "/":
        return {"linux_disi": True, "isletim_sistemi": platform_adi(), "python": platform.python_version()}
    ham: dict = {}
    for alan in DMI_ALANLARI:
        ham[alan] = _ilk_satir(_yol(kok, "sys/class/dmi/id", alan))
    try:
        with open(_yol(kok, "proc/cpuinfo"), encoding="utf-8", errors="replace") as dosya:
            for satir in dosya:
                if satir.lower().startswith("model name"):
                    ham["islemci"] = " ".join(satir.split(":", 1)[1].split())[:120]
                    break
    except (OSError, IndexError):
        pass
    ham["cekirdek_sayisi"] = os.cpu_count() or 0
    try:
        with open(_yol(kok, "proc/meminfo"), encoding="ascii", errors="replace") as dosya:
            for satir in dosya:
                if satir.startswith("MemTotal:"):
                    ham["bellek_mb"] = int(satir.split()[1]) // 1024
                    break
    except (OSError, ValueError, IndexError):
        pass
    diskler = []
    try:
        for ad in sorted(os.listdir(_yol(kok, "sys/block"))):
            if not ad.startswith(("sd", "nvme", "mmcblk", "vd", "hd")) or "boot" in ad or "rpmb" in ad:
                continue
            blok = _yol(kok, "sys/block", ad)
            if _ilk_satir(os.path.join(blok, "removable")) == "1":
                continue  # takılı USB bellek envantere girmez
            try:
                kesim = int(_ilk_satir(os.path.join(blok, "size")) or 0)
            except ValueError:
                kesim = 0
            if kesim <= 0:
                continue
            donen = _ilk_satir(os.path.join(blok, "queue", "rotational"))
            diskler.append({
                "ad": ad,
                "model": _ilk_satir(os.path.join(blok, "device", "model"), 80),
                "boyut_gb": round(kesim * 512 / 2**30),
                "ssd": donen == "0" if donen in ("0", "1") else None,
            })  # fmt: skip
    except OSError:
        pass
    ham["diskler"] = diskler[:8]
    dokunmatik: list[str] = []
    try:
        with open(_yol(kok, "proc/bus/input/devices"), encoding="utf-8", errors="replace") as dosya:
            for satir in dosya:
                if satir.startswith("N: Name="):
                    ad = satir.split("=", 1)[1].strip().strip('"')[:80]
                    if "touch" in ad.lower() and ad not in dokunmatik:
                        dokunmatik.append(ad)
    except OSError:
        pass
    ham["dokunmatik"] = dokunmatik[:10]
    ag = []
    try:
        for ad in sorted(os.listdir(_yol(kok, "sys/class/net"))):
            dizin = _yol(kok, "sys/class/net", ad)
            # Yalnız fiziksel arayüzler (device bağlantısı olanlar); lo, docker0, veth vb. girmez.
            if ad == "lo" or not os.path.exists(os.path.join(dizin, "device")):
                continue
            ag.append({
                "arayuz": ad[:20],
                "mac": _ilk_satir(os.path.join(dizin, "address"), 40)[:17],
                "kablosuz": os.path.isdir(os.path.join(dizin, "wireless")),
            })  # fmt: skip
    except OSError:
        pass
    ham["ag"] = ag[:8]
    ham["isletim_sistemi"] = platform_adi() if kok == "/" else _os_release(kok)
    try:
        ham["cekirdek"] = os.uname().release if kok == "/" else _ilk_satir(_yol(kok, "proc/sys/kernel/osrelease"))
    except AttributeError:
        ham["cekirdek"] = ""
    ham["etap_paketleri"] = etap_paketleri()
    ham["python"] = platform.python_version()
    return ham


def _os_release(kok: str) -> str:
    try:
        with open(_yol(kok, "etc/os-release"), encoding="utf-8") as dosya:
            for satir in dosya:
                if satir.startswith("PRETTY_NAME="):
                    return satir.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return ""


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
