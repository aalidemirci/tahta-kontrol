"""İşletim sistemine dokunan her şey bu modüldedir.

Ajanın geri kalanı platformdan habersizdir; yeni bir platform (ör. Windows'lu
tahta) eklemek bu dosyadaki işlevlerin karşılığını yazmaktır.
"""

from __future__ import annotations

import json
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


def _etkin_oturum_ham() -> dict | None:
    """Etkin grafik oturumun hesap adı ve türü: {"ad", "tur"} ya da None. Ad bu modülden ÇIKMAZ
    (yalnız `ortak_oturum` standart ortak hesap adını kullanır)."""
    if not LINUX or not shutil.which("loginctl"):
        return None
    kod, cikti = calistir(["loginctl", "list-sessions", "--no-legend"], 5)
    if kod != 0:
        return None
    for satir in cikti.splitlines():
        parcalar = satir.split()
        if not parcalar:
            continue
        kod2, ayrinti = calistir(
            ["loginctl", "show-session", parcalar[0], "-p", "Type", "-p", "Active", "-p", "Name", "-p", "Class", "-p", "User"],
            5,
        )
        if kod2 != 0:
            continue
        alan = dict(s.split("=", 1) for s in ayrinti.splitlines() if "=" in s)
        if alan.get("Active") == "yes" and alan.get("Class") == "user" and alan.get("Type") in ("x11", "wayland"):
            return {"ad": alan.get("Name", ""), "tur": alan.get("Type", ""), "uid": alan.get("User", "")}
    return None


def etkin_oturum_uid() -> int | None:
    """Etkin grafik oturumun sayısal kullanıcı kimliği; bilinmiyorsa (loginctl yok, oturum yok) None.

    Yerel soketten gelen yüzer düğme isteği ve oturum başlangıcı yalnız bu kimlikle bağlanan ekran
    yardımcısından kabul edilir (arka plandaki başka bir oturum ya da süreç tahtayı kapatamasın)."""
    ham = _etkin_oturum_ham()
    try:
        return int(ham["uid"]) if ham and ham.get("uid") not in (None, "") else None
    except (TypeError, ValueError):
        return None


def etkin_oturum() -> dict:
    """Ekrandaki oturum: tür (x11/wayland) ve hesap SINIFI.

    Kişisel hesap adları öğretmenin kimliğini taşıyabildiği için sunucuya ad
    gönderilmez; yalnız standart hesap adı ya da "kisisel" bildirilir.
    """
    if not LINUX:
        return {"sinif": "windows", "tur": ""}
    ham = _etkin_oturum_ham()
    if not ham:
        return {"sinif": "yok", "tur": ""}
    return {"sinif": ham["ad"] if ham["ad"] in STANDART_HESAPLAR else "kisisel", "tur": ham["tur"]}


# ---- oturum temizliği (K7): ortak hesap ve kullanıcı kimliğiyle çalışan ayrı süreç ----------------
TEMIZLIK_ZAMAN_ASIMI_SN = 60


def ortak_oturum(izinli=None) -> dict | None:
    """Etkin oturum temizlenebilir bir ORTAK hesapsa {"sinif","tur","uid","gid","ev"}; değilse None.

    Yalnız `temizlik.TEMIZLENEBILIR_HESAPLAR` (ogretmen, ogrenci); `izinli` (sunucunun listesi) bunu
    yalnız daraltır. etapadmin, kişisel hesap ve root hiçbir koşulda dönmez.
    """
    from .temizlik import TEMIZLENEBILIR_HESAPLAR

    ham = _etkin_oturum_ham()
    if not ham or ham["ad"] not in TEMIZLENEBILIR_HESAPLAR:
        return None
    if izinli is not None and ham["ad"] not in {str(h) for h in izinli}:
        return None
    try:
        import pwd

        kayit = pwd.getpwnam(ham["ad"])
    except (ImportError, KeyError):
        return None
    if kayit.pw_uid == 0:
        return None
    return {"sinif": ham["ad"], "tur": ham["tur"], "uid": kayit.pw_uid, "gid": kayit.pw_gid, "ev": kayit.pw_dir}


def _ajan_kok() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def temizlik_sureci_komutu(adim: str, *arg: str) -> list[str]:
    """`python3 -m tahta_ajan.temizlik ...`: -s kullanıcı site-packages'ını, -P (3.11+) çalışma dizinini
    yükleme yolundan çıkarır; süreç kök dizinde başlatılır (ev dizinindeki bir dosya içe aktarılmasın)."""
    bayraklar = ["-s", "-P"] if sys.version_info >= (3, 11) else ["-s"]
    return [sys.executable, *bayraklar, "-m", "tahta_ajan.temizlik", adim, *arg]


def tarayici_temizligi(oturum: dict, kuru: bool) -> dict:
    """Tarayıcı adımını oturum sahibinin kimliğiyle ayrı süreçte çalıştırır (root yetkisi düşürülür)."""
    if not LINUX:
        return {"hata_metni": "bu platformda tanımlı değil"}
    uid, gid, ev = int(oturum["uid"]), int(oturum["gid"]), str(oturum["ev"])
    komut = temizlik_sureci_komutu("tarayici", "--ev", ev, *(["--kuru"] if kuru else []))
    ortam = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": ev, "PYTHONPATH": _ajan_kok()}
    ek: dict = {}
    if os.geteuid() == 0:
        ek = {"user": uid, "group": gid, "extra_groups": []}
    elif os.geteuid() != uid:
        return {"hata_metni": "yetki yok"}
    try:
        sonuc = subprocess.run(
            komut, capture_output=True, text=True, timeout=TEMIZLIK_ZAMAN_ASIMI_SN, cwd="/", env=ortam,
            errors="replace", **ek,
        )  # fmt: skip
    except (OSError, subprocess.SubprocessError) as hata:
        return {"hata_metni": f"süreç başlatılamadı ({type(hata).__name__})"}
    try:
        veri = json.loads(sonuc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"hata_metni": f"süreç yanıtı okunamadı (çıkış {sonuc.returncode})"}
    return veri if isinstance(veri, dict) else {"hata_metni": "süreç yanıtı geçersiz"}


def yerel_baglanti_uid(istemci_port: int, sunucu_port: int, proc: str = "/proc") -> int | None:
    """127.0.0.1 üzerinden servise bağlanan sürecin kullanıcı kimliği (/proc/net/tcp{,6}: istemci tarafındaki
    satırda yerel kapı = istemci kapısı, karşı kapı = servis kapısı; "uid" sütunu). Bulunamazsa None.

    Ekran yardımcısı her oturumda (etapadmin ve kişisel hesaplar dahil) başlar; oturum temizliğinin pencere
    adımı yalnız temizlenen oturumun yardımcısına gönderilsin diye bağlantının sahibi buradan öğrenilir."""
    if not LINUX and proc == "/proc":
        return None
    for ad in ("tcp", "tcp6"):
        try:
            with open(os.path.join(proc, "net", ad), encoding="ascii", errors="replace") as dosya:
                next(dosya, None)  # başlık
                for satir in dosya:
                    alan = satir.split()
                    if len(alan) < 8 or ":" not in alan[1] or ":" not in alan[2]:
                        continue
                    try:
                        yerel = int(alan[1].rsplit(":", 1)[1], 16)
                        karsi = int(alan[2].rsplit(":", 1)[1], 16)
                        if yerel == int(istemci_port) and karsi == int(sunucu_port):
                            return int(alan[7])
                    except ValueError:
                        continue
        except OSError:
            continue
    return None


def pencereleri_kapat(haric_pid: int, kuru: bool) -> dict:
    """Ekran yardımcısı (oturumun içinde) çağırır: pencere kapatma ayrı süreçte (Xlib hata işleyicisi
    GTK'nınkini bozmasın). Döndürür: {"istenen","atlanan"} ya da {"hata"}."""
    if not LINUX:
        return {"hata": "bu platformda tanımlı değil"}
    komut = temizlik_sureci_komutu("pencereler", "--haric", str(int(haric_pid)), *(["--kuru"] if kuru else []))
    ortam = dict(os.environ)
    ortam["PYTHONPATH"] = _ajan_kok()
    try:
        sonuc = subprocess.run(komut, capture_output=True, text=True, timeout=15, cwd="/", env=ortam, errors="replace")
        veri = json.loads(sonuc.stdout.strip().splitlines()[-1])
    except (OSError, subprocess.SubprocessError, ValueError, IndexError) as hata:
        return {"hata": f"pencere süreci çalışmadı ({type(hata).__name__})"}
    return veri if isinstance(veri, dict) else {"hata": "yanıt geçersiz"}


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


def acik_sure_tam() -> float | None:
    """Açılıştan beri geçen saniye (/proc/uptime, tahta saatinden bağımsız). Okunamazsa None."""
    if not LINUX:
        return None
    try:
        with open("/proc/uptime", encoding="ascii") as dosya:
            return float(dosya.read().split()[0])
    except (OSError, ValueError, IndexError):
        return None


def surec_baslangici(stat_yolu: str = "/proc/self/stat") -> float | None:
    """Bu sürecin açılıştan kaç saniye sonra başladığı (/proc/self/stat 22. alan).

    Açılışta kilit (0.9.0) için oturumun başlangıcıdır: ekran yardımcısı oturum açılınca başlar. execv ile
    kendini yeniden başlatan yardımcıda (güncelleme) değer korunur; böylece güncelleme oturumu "yeni" saymaz.
    """
    if not LINUX:
        return None
    try:
        with open(stat_yolu, encoding="ascii", errors="replace") as dosya:
            metin = dosya.read()
        alanlar = metin[metin.rindex(")") + 2 :].split()
        return round(int(alanlar[19]) / os.sysconf("SC_CLK_TCK"), 2)
    except (OSError, ValueError, IndexError):
        return None


def acilis_kimligi() -> str:
    """Bu açılışın kimliği (/proc/sys/kernel/random/boot_id); yeniden başlatmada değişir. Okunamazsa ""."""
    if not LINUX:
        return ""
    try:
        with open("/proc/sys/kernel/random/boot_id", encoding="ascii") as dosya:
            return dosya.read().strip()[:64]
    except OSError:
        return ""


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
