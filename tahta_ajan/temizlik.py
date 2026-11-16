"""Oturum temizliği (K7, 0.8.0): ortak hesapta gün sonu "hafif" temizlik.

Bu modül işletim sistemine dokunan ikinci dosyadır (sistem.py'nin yanında); yalnız standart
kitaplık kullanır (pencere kapatma, sistemde zaten bulunan libX11'i ctypes ile çağırır).
Servis (root) bu modülü kendi içinde DEĞİL, temizlenecek hesabın kullanıcı kimliğiyle ayrı bir
süreçte çalıştırır (`python3 -m tahta_ajan.temizlik tarayici ...`): yol oyunları ve sembolik bağlar
en kötü durumda yalnız o hesabın kendi dosyalarına ulaşabilir. Pencere kapatma ise oturumdaki ekran
yardımcısının başlattığı ayrı süreçte çalışır (`... pencereler ...`), çünkü X ekranına yalnız
oturumun kendisi bağlanabilir.

Yapılanlar (yalnız bunlar):
  1. Görev çubuğunda görünen pencerelere kibar kapatma isteği (_NET_CLOSE_WINDOW). Uygulama
     kaydedilmemiş belge için soru sorabilir ve açık kalabilir; pencere zorla kapatılmaz.
  2. Hesabın tarayıcı süreçleri: önce kendiliğinden kapanmaları beklenir, sonra SIGTERM, en son
     SIGKILL. Tarayıcı dışındaki hiçbir süreç sonlandırılmaz.
  3. Tarayıcı profillerinde YALNIZ çerez ve oturum dosyaları (TARAYICI_PROFILLERI beyaz listesi).
     Dizinler dosya tanıtıcısıyla, sembolik bağ izlenmeden açılır; silme açık dizine göre yapılır
     (denetimden sonra bir dizini bağla değiştirmek silmeyi başka yere yöneltemez).
Dokunulmayanlar: geçmiş, yer imleri, kayıtlı parolalar, form geçmişi, site depolaması (Local
Storage, IndexedDB), uzantılar, ayarlar ve ev dizinindeki bütün dosyalar (İndirilenler, Masaüstü,
Belgeler).

Rapor yalnız sayı içerir: kullanıcı adı, ev dizini, profil adı, dosya adı ve pencere başlığı
raporlanmaz (kural 6).
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import stat
import sys
import time

# Temizlenebilecek ORTAK hesaplar. etapadmin ve kişisel hesaplar hiçbir koşulda temizlenmez;
# sunucu bu listeyi daraltabilir ama genişletemez.
TEMIZLENEBILIR_HESAPLAR = ("ogretmen", "ogrenci")

# /proc/<pid>/status "Name:" alanı (comm, en çok 15 karakter) → tarayıcı ailesi.
TARAYICI_SURECLERI = {
    "firefox": "Firefox",
    "firefox-esr": "Firefox",
    "firefox-bin": "Firefox",
    "chromium": "Chromium",
    "chromium-browse": "Chromium",
    "chrome": "Chrome",
    "google-chrome": "Chrome",
    "yandex_browser": "Yandex",
    "yandex-browser": "Yandex",
    "opera": "Opera",
    "brave": "Brave",
    "vivaldi-bin": "Vivaldi",
    "msedge": "Edge",
}

# Profil kökleri (ev dizinine göre) ve her profilde silinecek dosyalar. "dosyalar": profil
# dizinindeki (ya da alt yoldaki) tek dosyalar; "dizinler": İÇİNDEKİ düzenli dosyalar silinir
# (alt dizine inilmez, dizinin kendisi kalır).
_FIREFOX = {
    "dosyalar": (
        ("cookies.sqlite",), ("cookies.sqlite-wal",), ("cookies.sqlite-shm",), ("cookies.sqlite-journal",),
        ("sessionstore.jsonlz4",), ("sessionstore.js",), ("sessionstore.bak",),
    ),
    "dizinler": (("sessionstore-backups",),),
}
_CHROMIUM = {
    "dosyalar": (
        ("Cookies",), ("Cookies-journal",), ("Network", "Cookies"), ("Network", "Cookies-journal"),
        ("Current Session",), ("Current Tabs",), ("Last Session",), ("Last Tabs",),
    ),
    "dizinler": (("Sessions",), ("Session Storage",)),
}
TARAYICI_PROFILLERI = (
    # (aile, kök yol parçaları, profil türü)
    ("Firefox", (".mozilla", "firefox"), "firefox"),
    ("Firefox", (".var", "app", "org.mozilla.firefox", ".mozilla", "firefox"), "firefox"),
    ("Chromium", (".config", "chromium"), "chromium"),
    ("Chromium", (".var", "app", "org.chromium.Chromium", "config", "chromium"), "chromium"),
    ("Chrome", (".config", "google-chrome"), "chromium"),
    ("Chrome", (".var", "app", "com.google.Chrome", "config", "google-chrome"), "chromium"),
    ("Yandex", (".config", "yandex-browser"), "chromium"),
    ("Opera", (".config", "opera"), "chromium"),
    ("Brave", (".config", "BraveSoftware", "Brave-Browser"), "chromium"),
    ("Vivaldi", (".config", "vivaldi"), "chromium"),
    ("Edge", (".config", "microsoft-edge"), "chromium"),
)
_PROFIL_TURLERI = {"firefox": _FIREFOX, "chromium": _CHROMIUM}

# Bilerek DOKUNULMAYAN tarayıcı dosyaları (belge ve testler için; kod bunları hiç aramaz).
DOKUNULMAYANLAR = (
    "places.sqlite", "favicons.sqlite", "formhistory.sqlite", "logins.json", "logins-backup.json", "key4.db",
    "cert9.db", "webappsstore.sqlite", "storage/", "History", "Bookmarks", "Login Data", "Web Data",
    "Preferences", "Local Storage/", "IndexedDB/", "Extensions/",
)  # fmt: skip

KENDILIGINDEN_KAPANMA_SN = 5  # pencere kapatma isteğinden sonra tarayıcıya tanınan süre
SIGTERM_BEKLEME_SN = 10
SIGKILL_BEKLEME_SN = 3


# ---- güvenli yol ------------------------------------------------------------------------------
def _parca_gecerli(parca: str) -> bool:
    return bool(parca) and parca not in (".", "..") and "/" not in parca and "\\" not in parca and "\0" not in parca


def ev_gecerli(ev: str) -> bool:
    """Ev dizini mutlak, sembolik bağ içermeyen gerçek bir dizin olmalı (kök dizin olamaz)."""
    if not ev or not os.path.isabs(ev):
        return False
    try:
        st = os.lstat(ev)
    except OSError:
        return False
    if not stat.S_ISDIR(st.st_mode):
        return False
    gercek = os.path.normcase(os.path.realpath(ev))
    return gercek == os.path.normcase(os.path.abspath(ev)) and os.path.dirname(gercek) != gercek


def guvenli_dizin(ev: str, parcalar) -> str | None:
    """`ev` altında `parcalar` yolunu, her adımda sembolik bağ ve dizin olmayanı reddederek izler
    (yalnız yol denetimi; silme işleri `_Dizin` ile dosya tanıtıcısı üzerinden yapılır)."""
    kok = _Dizin.kok(ev)
    if kok is None:
        return None
    with kok:
        alt = kok.yol_ac(parcalar)
        if alt is None:
            return None
        with alt:
            return alt.yol


# Linux'ta dizinler dosya tanıtıcısıyla açılır (O_NOFOLLOW | O_DIRECTORY) ve her işlem açık dizine göre
# (dir_fd) yapılır: denetim ile silme arasında yoldaki bir dizin sembolik bağla değiştirilse de işlem
# denetlenen dizinde kalır (yarış yok). Tanıtıcı desteği olmayan sistemde (Windows'taki testler) yol adı
# ve lstat ile çalışılır; ajan yalnız Linux'ta çalışır.
_FD_DESTEGI = (
    hasattr(os, "O_NOFOLLOW") and hasattr(os, "O_DIRECTORY") and os.open in os.supports_dir_fd
    and os.unlink in os.supports_dir_fd and os.stat in os.supports_dir_fd and os.listdir in os.supports_fd
)  # fmt: skip
_DIZIN_BAYRAKLARI = (
    os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
)


class _Dizin:
    """Açık bir dizin. `alt` sembolik bağı ve dizin olmayanı açmaz (None döner)."""

    def __init__(self, yol: str, fd: int | None = None):
        self.yol, self.fd = yol, fd

    @classmethod
    def kok(cls, ev: str) -> _Dizin | None:
        if not ev_gecerli(ev):
            return None
        if _FD_DESTEGI:
            try:
                return cls(ev, os.open(ev, _DIZIN_BAYRAKLARI))
            except OSError:
                return None
        return cls(ev)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.kapat()

    def kapat(self) -> None:
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    def alt(self, ad: str) -> _Dizin | None:
        if not _parca_gecerli(ad):
            return None
        yol = os.path.join(self.yol, ad)
        if self.fd is not None:
            try:
                return _Dizin(yol, os.open(ad, _DIZIN_BAYRAKLARI, dir_fd=self.fd))
            except OSError:  # yok, sembolik bağ (ELOOP) ya da dizin değil (ENOTDIR)
                return None
        try:
            return _Dizin(yol) if stat.S_ISDIR(os.lstat(yol).st_mode) else None
        except OSError:
            return None

    def yol_ac(self, parcalar) -> _Dizin | None:
        """Parça parça iner; ara dizinler kapatılır. Dönen dizini çağıran kapatır."""
        simdiki = self
        for parca in parcalar:
            sonraki = simdiki.alt(parca)
            if simdiki is not self:
                simdiki.kapat()
            if sonraki is None:
                return None
            simdiki = sonraki
        return simdiki if simdiki is not self else _Dizin(self.yol, os.dup(self.fd) if self.fd is not None else None)

    def tur(self, ad: str) -> str | None:
        """"dosya" (düzenli dosya), "dizin", "diger" (sembolik bağ…) ya da None (yok)."""
        try:
            if self.fd is not None:
                st = os.stat(ad, dir_fd=self.fd, follow_symlinks=False)
            else:
                st = os.lstat(os.path.join(self.yol, ad))
        except OSError:
            return None
        if stat.S_ISREG(st.st_mode):
            return "dosya"
        return "dizin" if stat.S_ISDIR(st.st_mode) else "diger"

    def adlar(self) -> list[str]:
        return sorted(os.listdir(self.fd if self.fd is not None else self.yol))

    def sil(self, ad: str) -> None:
        # unlink son bileşeni izlemez; dir_fd ile ara bileşen de sabittir.
        if self.fd is not None:
            os.unlink(ad, dir_fd=self.fd)
        else:
            os.unlink(os.path.join(self.yol, ad))


def _chromium_profili_mi(ad: str) -> bool:
    return ad == "Default" or (ad.startswith("Profile ") and ad[8:].isdigit())


def _dosya_sil(dizin: _Dizin, ad: str, kuru: bool, sayac: dict) -> int:
    """Yalnız düzenli dosyayı siler; silinen (kuruda: silinecek) sayısı."""
    tur = dizin.tur(ad)
    if tur is None:
        return 0
    if tur != "dosya":
        sayac["atlanan"] += 1  # sembolik bağ ya da beklenmeyen tür: dokunulmaz
        return 0
    if kuru:
        return 1
    try:
        dizin.sil(ad)
        return 1
    except OSError:
        sayac["hata"] += 1
        return 0


def profil_temizle(profil: _Dizin, tur: str, kuru: bool, sayac: dict) -> int:
    """Bir profildeki beyaz listeli dosyaları siler; silinen (kuruda: silinecek) dosya sayısı."""
    tanim = _PROFIL_TURLERI[tur]
    silinen = 0
    for parcalar in tanim["dosyalar"]:
        dizin = profil.yol_ac(parcalar[:-1])
        if dizin is None:
            continue
        with dizin:
            silinen += _dosya_sil(dizin, parcalar[-1], kuru, sayac)
    for parcalar in tanim["dizinler"]:
        dizin = profil.yol_ac(parcalar)
        if dizin is None:
            if len(parcalar) == 1 and profil.tur(parcalar[0]) == "diger":
                sayac["atlanan"] += 1  # dizin yerine sembolik bağ: izlenmez
            continue
        with dizin:
            try:
                adlar = dizin.adlar()
            except OSError:
                sayac["hata"] += 1
                continue
            for ad in adlar:
                if dizin.tur(ad) == "dizin":
                    continue  # alt dizine inilmez
                silinen += _dosya_sil(dizin, ad, kuru, sayac)
    return silinen


def tarayici_verisini_sil(ev: str, kuru: bool = False, haric_aileler=()) -> dict:
    """Ev dizinindeki tarayıcı profillerinden yalnız çerez ve oturum dosyalarını siler.

    Döndürür: {"aileler": {aile: {"profil": n, "dosya": m}}, "atlanan": k, "hata": h}.
    `haric_aileler`: süreci kapanmayan tarayıcılar (verisine dokunulmaz).
    """
    sayac = {"aileler": {}, "atlanan": 0, "hata": 0}
    ev_dizini = _Dizin.kok(ev)
    if ev_dizini is None:
        sayac["hata"] += 1
        sayac["ev_gecersiz"] = True
        return sayac
    with ev_dizini:
        for aile, kok_parcalari, tur in TARAYICI_PROFILLERI:
            if aile in haric_aileler:
                continue
            kok = ev_dizini.yol_ac(kok_parcalari)
            if kok is None:
                continue
            with kok:
                try:
                    adlar = kok.adlar()
                except OSError:
                    continue
                for ad in adlar:
                    if tur == "chromium" and not _chromium_profili_mi(ad):
                        continue
                    profil = kok.alt(ad)  # sembolik bağ profil açılmaz
                    if profil is None:
                        if kok.tur(ad) == "diger":
                            sayac["atlanan"] += 1
                        continue
                    with profil:
                        silinen = profil_temizle(profil, tur, kuru, sayac)
                    if silinen:
                        bilgi = sayac["aileler"].setdefault(aile, {"profil": 0, "dosya": 0})
                        bilgi["profil"] += 1
                        bilgi["dosya"] += silinen
    return sayac


# ---- tarayıcı süreçleri -----------------------------------------------------------------------
def tarayici_surecleri(uid: int, proc: str = "/proc") -> list[tuple[int, str]]:
    """`uid` kullanıcısının tarayıcı süreçleri: [(pid, aile)]. Kendi sürecimiz girmez."""
    sonuc = []
    try:
        adlar = os.listdir(proc)
    except OSError:
        return sonuc
    for ad in adlar:
        if not ad.isdigit() or int(ad) == os.getpid():
            continue
        try:
            with open(os.path.join(proc, ad, "status"), encoding="utf-8", errors="replace") as dosya:
                alan = {}
                for satir in dosya:
                    anahtar, _, deger = satir.partition(":")
                    if anahtar in ("Name", "State", "Uid"):
                        alan[anahtar] = deger.strip()
                    if len(alan) == 3:
                        break
        except OSError:
            continue
        if alan.get("State", "").startswith(("Z", "X")):
            continue  # ölmüş (zombi) süreç: kapanmış sayılır, verisi temizlenebilir
        aile = TARAYICI_SURECLERI.get(alan.get("Name", ""))
        uidler = alan.get("Uid", "").split()
        if aile and uidler and uidler[0].isdigit() and int(uidler[0]) == uid:
            sonuc.append((int(ad), aile))
    return sonuc


def _bekle(uid: int, sure: float, proc: str) -> list[tuple[int, str]]:
    bitis = time.monotonic() + sure
    kalan = tarayici_surecleri(uid, proc)
    while kalan and time.monotonic() < bitis:
        time.sleep(0.5)
        kalan = tarayici_surecleri(uid, proc)
    return kalan


def tarayicilari_kapat(uid: int, kuru: bool = False, proc: str = "/proc", oldur=os.kill) -> dict:
    """Tarayıcıları kapatır: önce kendiliğinden kapanma beklenir, sonra SIGTERM, en son SIGKILL.

    Döndürür: {"bulunan": n, "zorla": k, "kalan_aileler": [...]} (kuruda hiçbir sinyal gönderilmez).
    """
    ilk = tarayici_surecleri(uid, proc)
    sonuc = {"bulunan": len(ilk), "zorla": 0, "kalan_aileler": []}
    if kuru or not ilk:
        return sonuc
    kalan = _bekle(uid, KENDILIGINDEN_KAPANMA_SN, proc)
    for pid, _ in kalan:
        try:
            oldur(pid, signal.SIGTERM)
        except OSError:
            pass
    kalan = _bekle(uid, SIGTERM_BEKLEME_SN, proc) if kalan else []
    for pid, _ in kalan:
        try:
            oldur(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
            sonuc["zorla"] += 1
        except OSError:
            pass
    kalan = _bekle(uid, SIGKILL_BEKLEME_SN, proc) if kalan else []
    sonuc["kalan_aileler"] = sorted({aile for _, aile in kalan})
    return sonuc


def tarayici_temizligi(ev: str, uid: int, kuru: bool = False, proc: str = "/proc") -> dict:
    """Süreçleri kapatır, sonra kapanan tarayıcıların çerez ve oturum dosyalarını siler."""
    surecler = tarayicilari_kapat(uid, kuru, proc)
    veri = tarayici_verisini_sil(ev, kuru, haric_aileler=surecler["kalan_aileler"])
    return {"surecler": surecler, **veri, "kuru": kuru}


# ---- pencereler (X11, ctypes) -----------------------------------------------------------------
def x11_pencereleri_kapat(haric_pidler=(), kuru: bool = False) -> dict:
    """Görev çubuğunda görünen pencerelere EWMH `_NET_CLOSE_WINDOW` isteği gönderir.

    Atlananlar: masaüstü, panel, araç çubuğu, yardımcı ve bildirim gibi NORMAL/DIALOG dışı türler,
    `_NET_WM_STATE_SKIP_TASKBAR` (ekran klavyesi, kenar çubuğu), pid'i bilinmeyen pencere ve
    `haric_pidler` (ekran yardımcısının kendisi). Döndürür: {"istenen": n, "atlanan": m} ya da {"hata"}.
    """
    import ctypes
    import ctypes.util

    ad = ctypes.util.find_library("X11") or "libX11.so.6"
    try:
        x = ctypes.CDLL(ad)
    except OSError:
        return {"hata": "libX11 yok"}
    c_ulong, c_long, c_int, c_void_p = ctypes.c_ulong, ctypes.c_long, ctypes.c_int, ctypes.c_void_p

    class XClientMessageEvent(ctypes.Structure):
        _fields_ = [
            ("type", c_int), ("serial", c_ulong), ("send_event", c_int), ("display", c_void_p),
            ("window", c_ulong), ("message_type", c_ulong), ("format", c_int), ("data", c_long * 5),
        ]  # fmt: skip

    class XEvent(ctypes.Union):
        _fields_ = [("xclient", XClientMessageEvent), ("pad", c_long * 24)]

    hata_isleyici_turu = ctypes.CFUNCTYPE(c_int, c_void_p, c_void_p)
    x.XSetErrorHandler.argtypes = [hata_isleyici_turu]
    x.XSetErrorHandler.restype = c_void_p
    x.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x.XOpenDisplay.restype = c_void_p
    x.XDefaultRootWindow.argtypes = [c_void_p]
    x.XDefaultRootWindow.restype = c_ulong
    x.XInternAtom.argtypes = [c_void_p, ctypes.c_char_p, c_int]
    x.XInternAtom.restype = c_ulong
    x.XGetWindowProperty.argtypes = [
        c_void_p, c_ulong, c_ulong, c_long, c_long, c_int, c_ulong, ctypes.POINTER(c_ulong), ctypes.POINTER(c_int),
        ctypes.POINTER(c_ulong), ctypes.POINTER(c_ulong), ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte)),
    ]  # fmt: skip
    x.XGetWindowProperty.restype = c_int
    x.XFree.argtypes = [c_void_p]
    x.XSendEvent.argtypes = [c_void_p, c_ulong, c_int, c_long, ctypes.POINTER(XEvent)]
    x.XSync.argtypes = [c_void_p, c_int]
    x.XCloseDisplay.argtypes = [c_void_p]

    # Kapanmış pencere BadWindow hatası verir; varsayılan işleyici süreci sonlandırırdı.
    isleyici = hata_isleyici_turu(lambda _d, _e: 0)
    x.XSetErrorHandler(isleyici)
    ekran = x.XOpenDisplay(None)
    if not ekran:
        return {"hata": "X ekranına bağlanılamadı"}
    try:
        kok = x.XDefaultRootWindow(ekran)

        def atom(adi: str) -> int:
            return x.XInternAtom(ekran, adi.encode("ascii"), 0)

        def ozellik(pencere: int, adi: str) -> list[int]:
            tur, bicim, adet, kalan = c_ulong(), c_int(), c_ulong(), c_ulong()
            veri = ctypes.POINTER(ctypes.c_ubyte)()
            durum = x.XGetWindowProperty(
                ekran, pencere, atom(adi), 0, 4096, 0, 0, ctypes.byref(tur), ctypes.byref(bicim),
                ctypes.byref(adet), ctypes.byref(kalan), ctypes.byref(veri),
            )  # fmt: skip
            if durum != 0 or not veri:
                return []
            try:
                if bicim.value != 32:
                    return []
                dizi = ctypes.cast(veri, ctypes.POINTER(c_ulong))
                return [int(dizi[i]) for i in range(min(adet.value, 4096))]
            finally:
                x.XFree(veri)

        uygun_turler = {atom("_NET_WM_WINDOW_TYPE_NORMAL"), atom("_NET_WM_WINDOW_TYPE_DIALOG")}
        gorev_cubugu_disi = atom("_NET_WM_STATE_SKIP_TASKBAR")
        kapat_atomu = atom("_NET_CLOSE_WINDOW")
        haric = {int(p) for p in haric_pidler}
        istenen = atlanan = 0
        for pencere in ozellik(kok, "_NET_CLIENT_LIST"):
            turler = set(ozellik(pencere, "_NET_WM_WINDOW_TYPE"))
            pid = (ozellik(pencere, "_NET_WM_PID") or [0])[0]
            if (turler and not turler & uygun_turler) or gorev_cubugu_disi in ozellik(pencere, "_NET_WM_STATE") \
                    or not pid or pid in haric:  # fmt: skip
                atlanan += 1
                continue
            istenen += 1
            if kuru:
                continue
            olay = XEvent()
            olay.xclient.type = 33  # ClientMessage
            olay.xclient.send_event = 1
            olay.xclient.display = ekran
            olay.xclient.window = pencere
            olay.xclient.message_type = kapat_atomu
            olay.xclient.format = 32
            olay.xclient.data[0] = 0  # CurrentTime
            olay.xclient.data[1] = 2  # kaynak: kullanıcı aracı (pager)
            x.XSendEvent(ekran, kok, 0, (1 << 20) | (1 << 19), ctypes.byref(olay))
        x.XSync(ekran, 0)
        return {"istenen": istenen, "atlanan": atlanan}
    finally:
        x.XCloseDisplay(ekran)


# ---- rapor ------------------------------------------------------------------------------------
def tarayici_ozeti(sonuc: dict) -> str:
    """Tarayıcı adımının ad ve yol içermeyen özeti."""
    if sonuc.get("hata_metni"):
        return f"Tarayıcı: atlandı ({sonuc['hata_metni']})"
    if sonuc.get("ev_gecersiz"):
        return "Tarayıcı: atlandı (ev dizini güvenli değil)"
    surecler = sonuc.get("surecler") or {}
    parcalar = []
    bulunan = int(surecler.get("bulunan") or 0)
    if bulunan:
        parcalar.append(f"{bulunan} tarayıcı süreci {'kapatılacak' if sonuc.get('kuru') else 'kapatıldı'}"
                        + (f" ({surecler['zorla']} zorla)" if surecler.get("zorla") else ""))  # fmt: skip
    for aile in surecler.get("kalan_aileler") or []:
        parcalar.append(f"{aile} kapanmadı, verisine dokunulmadı")
    aileler = sonuc.get("aileler") or {}
    fiil = "silinecek" if sonuc.get("kuru") else "silindi"
    for aile in sorted(aileler):
        bilgi = aileler[aile]
        parcalar.append(f"{aile} {bilgi['profil']} profil, {bilgi['dosya']} çerez/oturum dosyası {fiil}")
    if not aileler and not (surecler.get("kalan_aileler")):
        parcalar.append("silinecek çerez/oturum dosyası yok")
    if sonuc.get("atlanan"):
        parcalar.append(f"{sonuc['atlanan']} öğe atlandı (sembolik bağ ya da beklenmeyen tür)")
    if sonuc.get("hata"):
        parcalar.append(f"{sonuc['hata']} öğe silinemedi")
    return "Tarayıcı: " + ", ".join(parcalar)


def pencere_ozeti(sonuc: dict | None, kuru: bool = False) -> str:
    if not sonuc:
        return "Pencereler: atlandı (ekran yardımcısı yanıt vermedi)"
    if sonuc.get("hata"):
        return f"Pencereler: atlandı ({str(sonuc['hata'])[:80]})"
    fiil = "kapatma istenecek" if kuru else "kapatma istendi"
    metin = f"Pencereler: {int(sonuc.get('istenen') or 0)} pencereye {fiil}"
    if sonuc.get("atlanan"):
        metin += f", {int(sonuc['atlanan'])} pencere atlandı (panel, klavye ya da ekran yardımcısı)"
    return metin


# ---- komut satırı (ayrı süreç) ----------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(prog="tahta_ajan.temizlik")
    alt = ayristirici.add_subparsers(dest="adim", required=True)
    t = alt.add_parser("tarayici")
    t.add_argument("--ev", required=True)
    t.add_argument("--kuru", action="store_true")
    p = alt.add_parser("pencereler")
    p.add_argument("--haric", type=int, action="append", default=[])
    p.add_argument("--kuru", action="store_true")
    arg = ayristirici.parse_args(argv)
    try:
        if arg.adim == "tarayici":
            uid = os.getuid() if hasattr(os, "getuid") else -1
            if uid == 0:
                sonuc = {"hata_metni": "yönetici hesabıyla çalıştırılmaz"}
            else:
                sonuc = tarayici_temizligi(arg.ev, uid, arg.kuru)
        else:
            sonuc = x11_pencereleri_kapat(arg.haric, arg.kuru)
    except Exception as hata:  # rapor her durumda tek satır JSON'dur
        sonuc = {"hata": type(hata).__name__, "hata_metni": "beklenmeyen hata"}
    sys.stdout.write(json.dumps(sonuc, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
