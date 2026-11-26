"""Saha tanılaması: tahtanın bu yazılım için ne kadar hazır olduğunu ölçer.

Her denetim bağımsızdır; biri çökerse diğerleri sürer. Sonuç bir denetim
listesidir: {ad, sonuc: tamam|uyari|sorun|bilgi, ayrinti}.

Kişisel veri toplanmaz: kullanıcı adları, ev dizinleri ve dosya adları
rapora girmez; yalnız üç standart hesabın varlığı ve kişisel hesap SAYISI.
"""

from __future__ import annotations

import glob
import os
import shutil
import socket
import sys
import time
from urllib.parse import urlsplit

from . import __version__, otomatik_giris, sistem

TAMAM, UYARI, SORUN, BILGI = "tamam", "uyari", "sorun", "bilgi"


def _oku(yol: str, sinir: int = 3000) -> str:
    try:
        with open(yol, encoding="utf-8", errors="replace") as dosya:
            return dosya.read(sinir)
    except OSError:
        return ""


def _erisim(makine: str, port: int, zaman_asimi: float = 3) -> bool:
    try:
        with socket.create_connection((makine, port), timeout=zaman_asimi):
            return True
    except OSError:
        return False


def _isletim_sistemi():
    return BILGI, sistem.platform_adi() + " · çekirdek " + os.uname().release


def _etap_paketleri():
    if not shutil.which("dpkg-query"):
        return BILGI, "dpkg-query yok"
    kod, cikti = sistem.calistir(["dpkg-query", "-W", "-f", "${Package} ${Version}\n"], 15)
    if kod != 0:
        return UYARI, cikti[:300]
    secilen = [
        s for s in cikti.splitlines() if s.startswith(("eta-", "etap", "pardus-lightdm", "pardus-eta", "ahenk"))
    ]
    if not secilen:
        return BILGI, "eta-/etap/ahenk adlı paket bulunamadı (ETAP olmayabilir)."
    return BILGI, f"{len(secilen)} paket: " + "; ".join(secilen[:60])


def _python():
    surum = sys.version.split()[0]
    return (TAMAM if sys.version_info >= (3, 9) else SORUN), f"Python {surum}"


def _gtk():
    kod, cikti = sistem.calistir(
        [
            sys.executable,
            "-c",
            "import gi; gi.require_version('Gtk','3.0'); from gi.repository import Gtk;"
            "print(Gtk.get_major_version(), Gtk.get_minor_version())",
        ],
        10,
    )
    if kod == 0:
        return TAMAM, "PyGObject + GTK " + ".".join(cikti.split())
    return SORUN, "PyGObject/GTK3 içe aktarılamadı; kilit ekranı gösterilemez. " + cikti[-200:]


def _oturum(ekranlar):
    oturum = sistem.etkin_oturum()
    masaustu = ", ".join(sorted({e.get("masaustu", "") for e in ekranlar if e.get("masaustu")})) or "bilinmiyor"
    ayrinti = f"hesap sınıfı: {oturum['sinif']} · tür: {oturum['tur'] or 'bilinmiyor'} · masaüstü: {masaustu}"
    if oturum["tur"] == "wayland":
        return UYARI, ayrinti + " · Wayland'de pencereyi üstte tutma ve klavye kilidi garanti değildir."
    if oturum["tur"] == "x11":
        return TAMAM, ayrinti
    return BILGI, ayrinti


def _giris_ekrani():
    yonetici = ""
    try:
        yonetici = os.path.basename(os.readlink("/etc/systemd/system/display-manager.service"))
    except OSError:
        pass
    satirlar = []
    dosyalar = ["/etc/lightdm/lightdm.conf", "/etc/pardus/greeter.conf", "/etc/gdm3/daemon.conf"]
    dosyalar += sorted(glob.glob("/etc/lightdm/lightdm.conf.d/*.conf"))
    dosyalar += sorted(glob.glob("/etc/xdg/lightdm/lightdm.conf.d/*.conf"))
    dosyalar += sorted(glob.glob("/usr/share/lightdm/lightdm.conf.d/*.conf"))
    for yol in dosyalar:
        for satir in _oku(yol, 20000).splitlines():
            temiz = satir.strip()
            kucuk = temiz.lower()
            if temiz and not temiz.startswith("#") and ("autologin" in kucuk or "automaticlogin" in kucuk):
                # Otomatik giriş yapılan hesap standart değilse adı rapora yazılmaz.
                anahtar, _, deger = temiz.partition("=")
                deger = deger.strip()
                if "user" in anahtar.lower() and deger and deger not in sistem.STANDART_HESAPLAR:
                    deger = "(kişisel hesap)"
                satirlar.append(f"{os.path.basename(yol)}: {anahtar.strip()}={deger}")
    ayrinti = f"yönetici: {yonetici or 'bilinmiyor'} · otomatik giriş satırları: "
    ayrinti += "; ".join(satirlar[:12]) if satirlar else "yok"
    # 0.22.0: LightDM'in birleşik ayarına göre etkin hesap (sınıf) ve Tahta Kontrol dosyası.
    og = otomatik_giris.durum()
    if og["lightdm"]:
        ayrinti += f" · etkin: {og['etkin'] or 'yok'}"
        if og["bizim"]:
            ayrinti += " (Tahta Kontrol ayarı" + ("; başka bir ayar eziyor)" if og["ezilmis"] else ")")
    return BILGI, ayrinti


def _hesaplar():
    bulunan = []
    kisisel = 0
    for satir in _oku("/etc/passwd", 200000).splitlines():
        alan = satir.split(":")
        if len(alan) < 7:
            continue
        try:
            kimlik = int(alan[2])
        except ValueError:
            continue
        if alan[0] in sistem.STANDART_HESAPLAR:
            bulunan.append(alan[0])
        elif 1000 <= kimlik < 60000:
            kisisel += 1
    eksik = [h for h in sistem.STANDART_HESAPLAR if h not in bulunan]
    ayrinti = f"standart hesaplar: {', '.join(bulunan) or 'yok'} · kişisel hesap sayısı: {kisisel}"
    if eksik:
        return UYARI, ayrinti + f" · eksik: {', '.join(eksik)}"
    return TAMAM, ayrinti


def _ekran(ekranlar, oturum_sinifi=None):
    if not ekranlar:
        if oturum_sinifi not in (None, "", "yok", "windows"):
            # G2: oturum açık ama yardımcı bağlı değilse kilit bu oturumda gösterilemez.
            return SORUN, ("Oturum açık ama ekran yardımcısı bağlı değil: kilit ve duyuru bu oturumda görünmez. "
                           "Otomatik başlatma satırına bakın; oturumu kapatıp açın.")  # fmt: skip
        return UYARI, "Ekran yardımcısı bağlı değil (oturum açılmamış ya da otomatik başlatma çalışmıyor)."
    parcalar = []
    sonuc = TAMAM
    for e in ekranlar:
        if e.get("arayuz") == "yok":
            sonuc = SORUN
            parcalar.append("arayüz kitaplığı yok: " + str(e.get("hata", ""))[:120])
            continue
        parcalar.append(
            f"{e.get('arayuz', '?')} · {e.get('genislik', '?')}x{e.get('yukseklik', '?')}"
            f" · oturum türü {e.get('oturum_turu') or '?'}"
            f" · klavye kilidi: {e.get('klavye_kilidi', 'denenmedi')}"
        )
    return sonuc, " | ".join(parcalar)


def _guc():
    kok = hasattr(os, "geteuid") and os.geteuid() == 0
    araclar = [a for a in ("systemctl", "shutdown") if shutil.which(a)]
    ayrinti = f"servis yönetici yetkisiyle: {'evet' if kok else 'hayır'} · araçlar: {', '.join(araclar) or 'yok'}"
    return (TAMAM if kok and araclar else SORUN), ayrinti


def _wol(arayuz):
    if not arayuz:
        return BILGI, "Ağ arayüzü belirlenemedi."
    if shutil.which("ethtool"):
        kod, cikti = sistem.calistir(["ethtool", arayuz], 5)
        if kod == 0:
            satir = [s.strip() for s in cikti.splitlines() if "Wake-on" in s]
            metin = "; ".join(satir) or "Wake-on satırı yok"
            if any(s.startswith("Wake-on:") and "g" in s.split(":", 1)[1] for s in satir):
                return TAMAM, f"{arayuz}: {metin}"
            return UYARI, f"{arayuz}: {metin} · uzaktan açma kapalı görünüyor (BIOS/ethtool ayarı gerekir)."
    uyanma = _oku(f"/sys/class/net/{arayuz}/device/power/wakeup", 50).strip()
    return BILGI, f"{arayuz}: ethtool yok · power/wakeup={uyanma or 'okunamadı'}"


def _ag(ag):
    kablo = {True: "kablosuz", False: "kablolu", None: "bilinmiyor"}[ag.get("kablosuz")]
    return BILGI, f"arayüz {ag.get('arayuz') or '?'} ({kablo}) · IP {ag.get('ip') or '?'} · MAC {ag.get('mac') or '?'}"


def _saat(sunucu_saat):
    if not sunucu_saat:
        return BILGI, "Sunucu saati alınamadı."
    fark = time.time() - float(sunucu_saat)
    ayrinti = f"sunucuya göre fark {fark:+.0f} sn"
    return (TAMAM if abs(fark) < 60 else UYARI), ayrinti


def _depo():
    depo = _erisim("depo.pardus.org.tr", 443)
    genel = _erisim("1.1.1.1", 443)
    return BILGI, f"Pardus deposu: {'erişilebilir' if depo else 'erişilemiyor'} · genel internet: {'var' if genel else 'yok'}"


def _merkezi_yonetim():
    parcalar = []
    for servis in ("ahenk", "ahenk.service", "lider-ahenk"):
        kod, cikti = sistem.calistir(["systemctl", "is-active", servis], 4)
        ilk = cikti.splitlines()[0] if cikti else ""
        if ilk in ("active", "activating", "failed"):
            parcalar.append(f"{servis}: {ilk}")
    for yol in ("/etc/ahenk", "/usr/share/ahenk", "/opt/ahenk"):
        if os.path.exists(yol):
            parcalar.append(f"{yol} var")
    return BILGI, "; ".join(parcalar) if parcalar else "Ahenk (LiderAhenk istemcisi) izi bulunamadı."


def _disk():
    kullanim = shutil.disk_usage("/")
    bos = kullanim.free / 2**30
    return (TAMAM if bos > 1 else UYARI), f"kök dizinde boş alan {bos:.1f} GB / {kullanim.total / 2**30:.0f} GB"


def _araclar():
    adlar = ("chromium", "chromium-browser", "firefox", "firefox-esr", "wget", "curl", "ethtool", "xdotool", "wmctrl", "avahi-daemon")
    bulunan = [a for a in adlar if shutil.which(a)]
    return BILGI, "bulunan: " + (", ".join(bulunan) or "hiçbiri")


def _yoklama_kisayolu():
    """Yalnız kısayol dosyasının varlığı denetlenir; yoklama verisi (liste, belirteç) OKUNMAZ."""
    if os.path.exists(sistem.YOKLAMA_KISAYOLU):
        return TAMAM, f"{sistem.YOKLAMA_KISAYOLU} kurulu (menüde \"Yoklama Al\")"
    return UYARI, f"{sistem.YOKLAMA_KISAYOLU} yok; ajan paketini yeniden kurun"


def _ariza_kisayolu():
    if os.path.exists(sistem.ARIZA_KISAYOLU):
        return TAMAM, f"{sistem.ARIZA_KISAYOLU} kurulu (menüde \"Arıza bildir\")"
    return UYARI, f"{sistem.ARIZA_KISAYOLU} yok; ajan paketini yeniden kurun"


OTOMATIK_BASLATMA = "/etc/xdg/autostart/tahta-ekran.desktop"


def _baslatma_kapali_mi(metin: str) -> bool:
    """Masaüstü dosyası otomatik başlatmayı kapatıyor mu (Hidden=true ya da X-GNOME-Autostart-enabled=false)."""
    for satir in metin.splitlines():
        anahtar, _, deger = satir.partition("=")
        anahtar, deger = anahtar.strip(), deger.strip().lower()
        if (anahtar == "Hidden" and deger == "true") or (anahtar == "X-GNOME-Autostart-enabled" and deger == "false"):
            return True
    return False


def _otomatik_baslatma(hesap_dosyasi: str = "/etc/passwd"):
    """Ekran yardımcısının oturum açılışında başlaması (G2): sistem dosyası ve hesapların kendi kapatması.

    "Başlangıç uygulamaları" ayarından kapatılan yardımcı yalnız o hesabın ev dizinine
    ~/.config/autostart/tahta-ekran.desktop (Hidden=true) yazar; o hesapta kilit gelmez. Standart hesap
    adları yazılır, kişisel hesaplar yalnız SAYI olarak (ad ve ev dizini rapora girmez).
    """
    sistem_metni = _oku(OTOMATIK_BASLATMA, 4000)
    if not sistem_metni:
        return SORUN, f"{OTOMATIK_BASLATMA} yok; ajan paketini yeniden kurun (yardımcı oturumda başlamaz)."
    if _baslatma_kapali_mi(sistem_metni):
        return SORUN, f"{OTOMATIK_BASLATMA} otomatik başlatmayı kapatıyor; ajan paketini yeniden kurun."
    kapatan_standart, kapatan_kisisel = [], 0
    for satir in _oku(hesap_dosyasi, 200000).splitlines():
        alan = satir.split(":")
        if len(alan) < 7:
            continue
        try:
            kimlik = int(alan[2])
        except ValueError:
            continue
        standart = alan[0] in sistem.STANDART_HESAPLAR
        if not standart and not 1000 <= kimlik < 60000:
            continue
        metin = _oku(os.path.join(alan[5], ".config", "autostart", "tahta-ekran.desktop"), 4000)
        if metin and _baslatma_kapali_mi(metin):
            if standart:
                kapatan_standart.append(alan[0])
            else:
                kapatan_kisisel += 1
    if kapatan_standart or kapatan_kisisel:
        parcalar = kapatan_standart + ([f"{kapatan_kisisel} kişisel hesap"] if kapatan_kisisel else [])
        return SORUN, ("Yardımcı şu hesaplarda kapatılmış (~/.config/autostart/tahta-ekran.desktop): "
                       + ", ".join(parcalar) + ". Dosyayı silin; o hesapta kilit ekranı gelmez.")  # fmt: skip
    return TAMAM, f"{OTOMATIK_BASLATMA} kurulu; hiçbir hesapta kapatılmamış."


def _kilit_kaliciligi(servis_metni):
    """Kilit durumu kalıcılığı (G2): servisin bellekteki kilidi ile durum.json'daki aynı mı, dosya yazılabiliyor mu.

    Yalnız kilitli/kaynak okunur; dosyadaki kilit kodu özeti ve arıza kuyruğu rapora GİRMEZ.
    """
    import json

    from . import ayar

    dizin = ayar.durum_dizini()
    yol = dizin / "durum.json"
    try:
        veri = json.loads(yol.read_text(encoding="utf-8"))
        veri = veri if isinstance(veri, dict) else {}
        okundu = True
    except FileNotFoundError:
        veri, okundu = {}, None
    except (OSError, ValueError):
        veri, okundu = {}, False
    if veri.get("kilitli"):
        dosya = f"kilitli ({veri.get('kilit_kaynak') or 'idare'})"
    else:
        dosya = "açık" if okundu else ("dosya yok" if okundu is None else "okunamadı")
    yazilir = os.access(dizin, os.W_OK) if dizin.is_dir() else False
    ayrinti = f"servis: {servis_metni or 'bilinmiyor (servis dışından çalıştırıldı)'} · durum.json: {dosya} · dizin yazılabilir: {'evet' if yazilir else 'hayır'}"
    if okundu is False or (servis_metni and not yazilir):
        return SORUN, ayrinti + " · kilit yeniden başlatmada korunamaz."
    if servis_metni and servis_metni.startswith("kilitli (idare") and not veri.get("kilitli"):
        return SORUN, ayrinti + " · servisin kilidi dosyaya yazılmamış."
    if veri.get("kilit_kaynak") == "program":
        ayrinti += " · program kilidi yeniden başlatmada bilerek geri yüklenmez (süresi bilinmez)."
    return TAMAM, ayrinti


def _sunucu_adresleri(sunucular):
    """Listedeki her adres için ad çözümü ve TCP erişimi. Adresler rapora YAZILMAZ, yalnız sayılar (A6)."""
    if not sunucular:
        return BILGI, "Adres listesi yok (yalnız birincil adres kullanılıyor)."
    cozulen = erisilen = 0
    for adres in sunucular:
        parca = urlsplit(adres)
        makine, port = parca.hostname or "", parca.port or 443
        try:
            socket.getaddrinfo(makine, port, proto=socket.IPPROTO_TCP)
        except (OSError, UnicodeError):
            continue
        cozulen += 1
        if _erisim(makine, port):
            erisilen += 1
    n = len(sunucular)
    ayrinti = f"{n} adresten erişilebilen: {erisilen} · adı çözülen: {cozulen}"
    if erisilen == 0:
        return SORUN, ayrinti
    return (TAMAM if erisilen == n else UYARI), ayrinti


def usb_satirlari(usb: dict | None, udisks=None, mountinfo: str | None = None) -> list[tuple[str, str, str]]:
    """USB anahtar (0.11.0) bölümü: yalnız sayı ve evet/hayır. Bağlama yolu, bellek etiketi, hesap adı, anahtar
    kimliği ve gizli değer YAZILMAZ (§8). `usb`: servisin `usb_tani_bilgisi()`; servis dışından çalıştırılınca None."""
    from . import usb_anahtar

    if usb is None:  # servis dışından: bellekler bu anda sayılır (dosya okunmaz)
        usb = {"ozellik": None, "izleme": None, "takili": None, "elenen": {}, "son_okuma": "", "son_dogrulama": ""}
        if mountinfo is None and os.path.exists(sistem.MOUNTINFO):
            try:
                with open(sistem.MOUNTINFO, encoding="utf-8", errors="replace") as dosya:
                    mountinfo = dosya.read()
            except OSError:
                mountinfo = None
        if mountinfo is not None:
            adaylar, elenen = sistem.cikarilabilir_baglamalar(mountinfo)
            usb.update(takili=len(adaylar), elenen=elenen)
    ozellik = {"acik": (BILGI, "açık (sunucu ayarı)"), "kapali": (BILGI, "kapalı"),
               "bildirmedi": (BILGI, "sunucu bildirmedi (eski sunucu ya da henüz bağlanmadı)")}.get(
        usb.get("ozellik"), (BILGI, "servis dışından çalıştırıldı; servis raporunda görünür"))  # fmt: skip
    izleme = {"izleniyor": (TAMAM, "izleniyor"), "kapali": (BILGI, "kapalı"),
              "desteklenmiyor": (UYARI, "desteklenmiyor: /proc/self/mountinfo yok")}.get(
        usb.get("izleme"), (BILGI, "bilinmiyor"))  # fmt: skip
    udisks = sistem.udisks_calisiyor() if udisks is None else udisks
    if udisks is True:
        bagla = (TAMAM, "çalışıyor")
    elif udisks is False:
        bagla = (UYARI if usb.get("ozellik") == "acik" else BILGI, "çalışmıyor — bellekler bağlanmaz, USB anahtar çalışmaz")
    else:
        bagla = (BILGI, "bilinmiyor (systemctl yok)")
    takili = usb.get("takili")
    elenen = usb.get("elenen") or {}
    elenen_metni = ", ".join(f"{ad}: {int(elenen.get(k, 0))}" for k, ad in usb_anahtar.ELENME_ADLARI.items())
    son_okuma = usb_anahtar.OKUMA_ADLARI.get(usb.get("son_okuma") or "", "yok")
    if usb.get("son_okuma") == "surum":
        son_okuma = "reddedildi: sürüm"
    return [
        ("USB anahtar: özellik", *ozellik),
        ("USB anahtar: izleme", *izleme),
        ("USB anahtar: otomatik bağlama hizmeti (udisks2)", *bagla),
        ("USB anahtar: takılı çıkarılabilir bellek", BILGI, "bilinmiyor" if takili is None else str(int(takili))),
        ("USB anahtar: elenen bağlama", BILGI, f"{sum(int(v) for v in elenen.values())} ({elenen_metni})"),
        ("USB anahtar: son okuma sonucu", BILGI, son_okuma),
        ("USB anahtar: son sunucu doğrulaması", BILGI, usb.get("son_dogrulama") or "yok"),
    ]


def _servis():
    if not os.path.isdir("/run/systemd/system"):
        return UYARI, "systemd çalışmıyor; ajan servis olarak başlatılamaz."
    kod, etkin = sistem.calistir(["systemctl", "is-enabled", "tahta-ajan.service"], 4)
    kod2, calisiyor = sistem.calistir(["systemctl", "is-active", "tahta-ajan.service"], 4)
    ayrinti = f"etkin: {etkin.splitlines()[0] if etkin else '?'} · durum: {calisiyor.splitlines()[0] if calisiyor else '?'}"
    return (TAMAM if kod == 0 and kod2 == 0 else UYARI), ayrinti


def topla(
    sunucu_makine: str = "", sunucu_port: int = 0, sunucu_saat=None, ekranlar=None, sinav_kipi=None, sunucular=None,
    kilit=None, dugme=None, usb=None,
) -> dict:  # fmt: skip
    """sinav_kipi: servisin "yok" / "giris (kimlik)" / "suruyor (kimlik)" satırı (A4). Liste, ad, kod girmez.
    sunucular: ajanın deneme sırasındaki adresler (A6); rapora yalnız sayıları girer.
    kilit / dugme (0.9.0): servisin kilit ve yüzer düğme satırları; servis dışından çalıştırılınca None.
    usb (0.11.0): servisin `usb_tani_bilgisi()` sözlüğü (yalnız sayılar); servis dışından None."""
    ekranlar = ekranlar or []
    ag = sistem.ag_bilgisi(sunucu_makine, sunucu_port) if sunucu_makine else {}
    if not sistem.LINUX:
        denetimler = [
            {"ad": "İşletim sistemi", "sonuc": BILGI, "ayrinti": sistem.platform_adi()},
            {"ad": "Tanılama", "sonuc": UYARI, "ayrinti": "Ayrıntılı tanılama yalnız Linux/Pardus için yazıldı."},
        ]
        return {"ajan_surumu": __version__, "zaman": int(time.time()), "denetimler": denetimler}
    adimlar = [
        ("İşletim sistemi", _isletim_sistemi),
        ("ETAP paketleri", _etap_paketleri),
        ("Python", _python),
        ("Kilit ekranı kitaplığı (GTK3)", _gtk),
        ("Etkin oturum", lambda: _oturum(ekranlar)),
        ("Giriş ekranı ve otomatik giriş", _giris_ekrani),
        ("Hesaplar", _hesaplar),
        ("Ekran yardımcısı", lambda: _ekran(ekranlar, sistem.etkin_oturum().get("sinif"))),
        ("Ekran yardımcısı otomatik başlatma", _otomatik_baslatma),
        ("Kilit durumu kalıcılığı", lambda: _kilit_kaliciligi(kilit)),
        ("Yüzer düğme", lambda: (BILGI, dugme or "servis dışından çalıştırıldı; servis raporunda görünür")),
        ("Sınav kipi", lambda: (BILGI, sinav_kipi or "yok")),
        ("Yoklama kısayolu", _yoklama_kisayolu),
        ("Arıza bildirimi kısayolu", _ariza_kisayolu),
        ("Kapatma / yeniden başlatma yetkisi", _guc),
        ("Ağ", lambda: _ag(ag)),
        ("Sunucu adresleri", lambda: _sunucu_adresleri(sunucular or [])),
        ("Uzaktan açma (Wake-on-LAN)", lambda: _wol(ag.get("arayuz"))),
        ("Saat", lambda: _saat(sunucu_saat)),
        ("İnternet ve paket deposu", _depo),
        ("Merkezî yönetim (LiderAhenk)", _merkezi_yonetim),
        ("Disk", _disk),
        ("Yardımcı araçlar", _araclar),
        ("Ajan servisi", _servis),
    ]
    denetimler = []
    for ad, islev in adimlar:
        try:
            sonuc, ayrinti = islev()
        except Exception as hata:  # tanılama hiçbir koşulda ajanı düşürmez
            sonuc, ayrinti = UYARI, f"denetim çalışmadı: {type(hata).__name__}: {hata}"
        denetimler.append({"ad": ad, "sonuc": sonuc, "ayrinti": ayrinti})
    try:
        for ad, sonuc, ayrinti in usb_satirlari(usb):
            denetimler.append({"ad": ad, "sonuc": sonuc, "ayrinti": ayrinti})
    except Exception as hata:  # tanılama hiçbir koşulda ajanı düşürmez
        denetimler.append({"ad": "USB anahtar", "sonuc": UYARI, "ayrinti": f"denetim çalışmadı: {type(hata).__name__}"})
    return {"ajan_surumu": __version__, "zaman": int(time.time()), "denetimler": denetimler}
