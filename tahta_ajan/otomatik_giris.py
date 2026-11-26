"""Açılışta ortak hesaba otomatik giriş (0.22.0; sunucudaki tahta_sunucu/otomatik_giris.py, kural 39).

İşletim sistemine dokunan ÜÇÜNCÜ dosyadır (sistem.py ve temizlik.py'den sonra): yalnız LightDM yapılandırmasını
okur ve Tahta Kontrol'ün TEK dosyasını yazar/siler. Hepsi `kok` parametresiyle çalışır (testler geçici klasörle).

- Yazılan dosya `araclar/otomatik-giris.sh` ile AYNI ad ve içeriktir: elle denenmiş tahta da aynı dosyayı taşır.
- Hesap listesi sabittir (`HESAPLAR`); sunucu başka bir ad gönderse de yazılmaz. Hesap tahtada yoksa, kimliği
  1000'den küçükse (sistem hesabı, root) yazılmaz.
- Silme yalnız ilk satırı Tahta Kontrol imzası taşıyan KENDİ dosyamızı siler; başka dosyadaki ayara dokunulmaz.
- Giriş ekranı (lightdm) yeniden BAŞLATILMAZ: ayar bir sonraki açılışta geçerli olur, açık ders bölünmez.
- Durum raporu hesap ADI taşımaz: standart hesap adı ya da "kisisel"; dosya yolu ve içerik sunucuya gitmez.
"""

from __future__ import annotations

import fnmatch
import os
import stat

DOSYA_ADI = "50-tahta-otomatik-giris.conf"
HESAPLAR = ("ogretmen",)  # sunucudaki otomatik_giris.HESAPLAR ile aynı (test karşılaştırır)
STANDART_HESAPLAR = ("etapadmin", "ogretmen", "ogrenci")  # sistem.STANDART_HESAPLAR ile aynı
IMZA = "# Tahta Kontrol tarafindan yazildi."
DOSYA_EN_BUYUK = 64 * 1024
KOLTUK = "seat0"
# LightDM'in okuma sırası (sonraki kazanır): paket varsayılanları → xdg → /etc dizini → ana dosya.
DIZINLER = (
    "usr/share/lightdm/lightdm.conf.d",
    "etc/xdg/lightdm/lightdm.conf.d",
    "etc/lightdm/lightdm.conf.d",
)
ANA_DOSYA = "etc/lightdm/lightdm.conf"
YAZMA_DIZINI = "etc/lightdm/lightdm.conf.d"


def _yol(kok: str, goreli: str) -> str:
    return os.path.join(kok, *goreli.split("/"))


def dosya_yolu(kok: str = "/") -> str:
    return os.path.join(_yol(kok, YAZMA_DIZINI), DOSYA_ADI)


def icerik(hesap: str) -> str:
    """Yazılan dosyanın tam metni (ASCII; betikle aynı)."""
    return (
        f"{IMZA} Geri almak icin:\n"
        "#   sh otomatik-giris.sh kaldir   (ya da bu dosyayi silin)\n"
        "[Seat:*]\n"
        f"autologin-user={hesap}\n"
        "autologin-user-timeout=0\n"
    )


def _oku(yol: str) -> str | None:
    """Düz dosyayı (sembolik bağ izlemeden, ≤ 64 KB) okur; yoksa ya da uygun değilse None."""
    try:
        bilgi = os.lstat(yol)
    except OSError:
        return None
    if not stat.S_ISREG(bilgi.st_mode) or bilgi.st_size > DOSYA_EN_BUYUK:
        return None
    try:
        fd = os.open(yol, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0))
    except OSError:
        return None
    with os.fdopen(fd, "rb") as dosya:
        return dosya.read(DOSYA_EN_BUYUK).decode("utf-8", "replace")


def ayristir(metin: str) -> list[tuple[str, str, str]]:
    """GKeyFile benzeri basit okuyucu: [(bölüm, anahtar, değer)] dosya sırasıyla."""
    sonuc = []
    bolum = ""
    for satir in metin.splitlines():
        temiz = satir.strip()
        if not temiz or temiz[0] in "#;":
            continue
        if temiz.startswith("[") and temiz.endswith("]"):
            bolum = temiz[1:-1].strip()
            continue
        anahtar, esit, deger = temiz.partition("=")
        if esit:
            sonuc.append((bolum, anahtar.strip(), deger.strip()))
    return sonuc


def okunan_dosyalar(kok: str = "/") -> list[str]:
    """LightDM'in okuduğu dosyalar, okuma sırasıyla (dizin içinde ada göre sıralı .conf'lar)."""
    dosyalar = []
    for goreli in DIZINLER:
        dizin = _yol(kok, goreli)
        try:
            adlar = sorted(a for a in os.listdir(dizin) if a.endswith(".conf"))
        except OSError:
            continue
        dosyalar += [os.path.join(dizin, a) for a in adlar]
    dosyalar.append(_yol(kok, ANA_DOSYA))
    return dosyalar


def _koltuk_bolumu(bolum: str) -> str | None:
    """'genel' ([Seat:*], eski adı [SeatDefaults]) | 'ozel' (seat0'a uyan [Seat:<desen>]) | None."""
    if bolum in ("Seat:*", "SeatDefaults"):
        return "genel"
    if bolum.startswith("Seat:") and fnmatch.fnmatchcase(KOLTUK, bolum[len("Seat:") :]):
        return "ozel"
    return None


def etkin_ayar(kok: str = "/") -> dict:
    """Birleşik yapılandırmada seat0'ın otomatik giriş hesabı: {"hesap": str ("" = yok), "kaynak": yol | None}.

    LightDM kuralı: dosyalar sırayla okunur, sonraki değer öncekini ezer; koltuğa özel bölümdeki değer genel
    bölümdekinin önüne geçer. Boş değer ("autologin-user=") otomatik girişi kapatır.
    """
    genel = ozel = None
    for yol in okunan_dosyalar(kok):
        metin = _oku(yol)
        if metin is None:
            continue
        for bolum, anahtar, deger in ayristir(metin):
            if anahtar != "autologin-user":
                continue
            tur = _koltuk_bolumu(bolum)
            if tur == "genel":
                genel = (deger, yol)
            elif tur == "ozel":
                ozel = (deger, yol)
    secilen = ozel or genel
    if secilen is None:
        return {"hesap": "", "kaynak": None}
    return {"hesap": secilen[0], "kaynak": secilen[1]}


def sinif(hesap: str) -> str:
    if not hesap:
        return ""
    return hesap if hesap in STANDART_HESAPLAR else "kisisel"


def bizim_mi(kok: str = "/") -> bool:
    metin = _oku(dosya_yolu(kok))
    return metin is not None and metin.startswith(IMZA)


def lightdm_var(kok: str = "/") -> bool:
    return os.path.isdir(_yol(kok, "etc/lightdm"))


def durum(kok: str = "/", hata: str = "") -> dict:
    """Sunucuya giden özet: {"lightdm", "etkin" (sınıf), "bizim", "ezilmis", "hata"}; ad ve yol yok."""
    if not lightdm_var(kok):
        return {"lightdm": False, "etkin": "", "bizim": False, "ezilmis": False, "hata": hata}
    etkin = etkin_ayar(kok)
    bizim = bizim_mi(kok)
    return {
        "lightdm": True,
        "etkin": sinif(etkin["hesap"]),
        "bizim": bizim,
        "ezilmis": bizim and etkin["kaynak"] != dosya_yolu(kok),
        "hata": hata,
    }


def _hesap_kimligi(kok: str, hesap: str) -> int | None:
    metin = _oku(_yol(kok, "etc/passwd"))
    for satir in (metin or "").splitlines():
        alan = satir.split(":")
        if len(alan) >= 3 and alan[0] == hesap:
            try:
                return int(alan[2])
            except ValueError:
                return None
    return None


def _grup_uyeleri(kok: str, grup: str) -> list[str] | None:
    """Grup yoksa None, varsa üye adları."""
    for satir in (_oku(_yol(kok, "etc/group")) or "").splitlines():
        alan = satir.split(":")
        if len(alan) >= 4 and alan[0] == grup:
            return [u for u in alan[3].split(",") if u]
    return None


def _yaz(yol: str, metin: str):
    """Atomik yazım: aynı dizinde geçici dosya (O_EXCL + O_NOFOLLOW) → fsync → os.replace; 0644."""
    gecici = yol + ".yeni"
    try:
        os.unlink(gecici)
    except FileNotFoundError:
        pass
    bayrak = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)
    fd = os.open(gecici, bayrak, 0o644)
    try:
        with os.fdopen(fd, "wb") as dosya:
            dosya.write(metin.encode("ascii"))
            dosya.flush()
            os.fsync(dosya.fileno())
        os.chmod(gecici, 0o644)
        os.replace(gecici, yol)
    except BaseException:
        try:
            os.unlink(gecici)
        except OSError:
            pass
        raise


def uygula(hesap: str | None, kok: str = "/", calistir=None) -> tuple[bool, str]:
    """İstenen durumu uygular. hesap=None: kendi dosyamızı sil. Dönüş: (değişti mi, hata metni "" = yok).

    calistir: grup üyeliği için komut çalıştırıcı (sistem.calistir); None ise grup adımı atlanır (testler).
    """
    if not lightdm_var(kok):
        return False, "Giriş ekranı LightDM değil; otomatik giriş ayarlanmadı."
    yol = dosya_yolu(kok)
    if hesap is None:
        if not os.path.lexists(yol):
            return False, ""
        if not bizim_mi(kok):
            return False, "Otomatik giriş dosyası Tahta Kontrol'ün değil; silinmedi."
        os.unlink(yol)
        return True, ""
    if hesap not in HESAPLAR:
        return False, "Bu hesapla otomatik giriş yapılmaz; uygulanmadı."
    kimlik = _hesap_kimligi(kok, hesap)
    if kimlik is None:
        return False, f"'{hesap}' hesabı bu tahtada yok; uygulanmadı."
    if kimlik < 1000:
        return False, "Sistem hesabıyla otomatik giriş yapılmaz; uygulanmadı."
    dizin = _yol(kok, YAZMA_DIZINI)
    try:
        bilgi = os.lstat(dizin)
    except FileNotFoundError:
        os.mkdir(dizin, 0o755)
        bilgi = os.lstat(dizin)
    if not stat.S_ISDIR(bilgi.st_mode):
        return False, "Yapılandırma dizini beklenen türde değil; uygulanmadı."
    try:
        hedef = os.lstat(yol)
    except FileNotFoundError:
        hedef = None
    if hedef is not None and not stat.S_ISREG(hedef.st_mode):
        return False, "Otomatik giriş dosyası beklenen türde değil; uygulanmadı."
    istenen = icerik(hesap)
    degisti = _oku(yol) != istenen
    if degisti:
        _yaz(yol, istenen)
    # Bazı kurulumlarda otomatik giriş için hesap "autologin" grubunda olmalıdır (betikle aynı).
    uyeler = _grup_uyeleri(kok, "autologin")
    if calistir is not None and uyeler is not None and hesap not in uyeler:
        calistir(["usermod", "-a", "-G", "autologin", hesap])
    return degisti, ""
