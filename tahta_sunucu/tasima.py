"""Eski veri dizinini hizmetin veri dizinine taşır (0.8 öncesinden yükseltme).

0.8 öncesi program oturumda çalışıyordu ve verisini o kullanıcının
`%LOCALAPPDATA%\\TahtaKontrol` dizinine yazıyordu. 0.8'den sonra sunucu Windows
hizmeti (Yerel Hizmet hesabı) olarak çalışır ve verisi `%PROGRAMDATA%\\TahtaKontrol`
dizinindedir. Hizmet hesabı kullanıcı profillerini okuyamaz; taşımayı kurucu
yönetici yetkisiyle `TahtaKontrol.exe tasi --hedef ...` diyerek yaptırır.

Kurallar (sertifika değişirse BÜTÜN tahtalar kopar; kural 4):
- Kaynağa dokunulmaz: dosyalar KOPYALANIR, özetleri karşılaştırılır, veritabanı
  bütünlük denetiminden geçer; kaynağa yalnız `TASINDI.txt` bırakılır. Eski sürüm
  yeniden kurulursa eski veri yerindedir (geri alınabilir).
- Hedefte veri varsa (veritabanı ya da sertifika) taşınmaz: hedef kazanır.
- Birden çok aday ve seçim belirsizse ya da kopyalama başarısızsa taşınmaz;
  hedefe `TASIMA-BEKLIYOR.txt` yazılır ve hizmet bu dosya durdukça AÇILMAZ (yeni
  sertifika üretip tahtaları koparmasın). Yarım kopyalanan dosyalar silinir.
- Kesintiye dayanıklı: dosyalar önce hedefteki `.tasima-gecici` dizinine kopyalanıp
  doğrulanır, sonra `TASIMA-SURUYOR.txt` işaretiyle yerlerine taşınır (önce sertifika
  çifti, en son veritabanı). Süreç ölür ya da elektrik giderse sonraki çalıştırma
  geçici dizini siler; işaret kalmışsa hedefteki yarım dosyaları `yarim-tasima-*`
  klasörüne kaldırıp taşımayı baştan yapar. İşaret durdukça hizmet de açılmaz.
- Geri dönüşten sonra yeniden yükseltme: taşınmış (TASINDI.txt) eski klasördeki
  veritabanı taşımadan SONRA değişmişse (eski sürüm yeniden kurulup kullanılmış),
  hedef "dolu" olsa da hangisinin doğru olduğu bilinemez: BELIRSIZ döner, hizmet açılmaz.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import sqlite3
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

VERI_DOSYALARI = ("tahta-kontrol.db", "sunucu-sertifika.pem", "sunucu-anahtar.pem")
TASINDI = "TASINDI.txt"
BEKLIYOR = "TASIMA-BEKLIYOR.txt"
SURUYOR = "TASIMA-SURUYOR.txt"
GECICI = ".tasima-gecici"
YARIM_ON_EKI = "yarim-tasima-"
# TASINDI.txt'den bu kadar sonra değişen eski veritabanı "geri dönüşte kullanılmış" sayılır.
GERI_DONUS_PAYI_SN = 120
# Taşınmayanlar: günlükler (yeni yerde yeniden başlar), SQLite paylaşımlı bellek dosyası
# (açılışta yeniden kurulur), işaret dosyaları.
_ATLANAN_ON_EKLER = ("sunucu.log", "pencere.log")
_ATLANAN_SON_EKLER = ("-shm",)
_ATLANAN_ADLAR = {TASINDI, BEKLIYOR, SURUYOR}

# Çıkış kodları (kurucu bunlara göre ileti gösterir ve hizmeti başlatır ya da başlatmaz).
TASINDI_KOD = 0
ESKI_VERI_YOK = 10
HEDEF_DOLU = 11
BELIRSIZ = 20
HATA = 21
HIZMET_BASLATILABILIR = {TASINDI_KOD, ESKI_VERI_YOK, HEDEF_DOLU}


class TasimaHatasi(Exception):
    pass


@dataclass
class Aday:
    yol: Path
    son_temas: int | None = None  # tahtalardan birinin sunucuyu en son gördüğü an
    tahta_sayisi: int = 0
    kullanici_sayisi: int = 0
    okunamadi: str = ""


@dataclass
class Sonuc:
    kod: int
    ileti: str
    kaynak: Path | None = None
    kopyalanan: list[str] = field(default_factory=list)


# ---- yardımcılar --------------------------------------------------------------------------
def veri_var(dizin: Path) -> bool:
    return any((dizin / ad).is_file() for ad in VERI_DOSYALARI)


def aday_mi(dizin: Path) -> bool:
    return dizin.is_dir() and not dizin.is_symlink() and veri_var(dizin) and not (dizin / TASINDI).exists()


def atlanir_mi(ad: str) -> bool:
    return ad in _ATLANAN_ADLAR or ad.startswith(_ATLANAN_ON_EKLER) or ad.endswith(_ATLANAN_SON_EKLER)


def _ozet(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        for parca in iter(lambda: f.read(1 << 20), b""):
            h.update(parca)
    return h.hexdigest()


def aday_oku(dizin: Path) -> Aday:
    """Adayın veritabanını GEÇİCİ BİR KOPYADA okur (kaynağa yazılmasın diye)."""
    aday = Aday(dizin)
    db = dizin / "tahta-kontrol.db"
    if not db.is_file():
        return aday
    try:
        with tempfile.TemporaryDirectory(prefix="tk-tasima-") as gecici:
            kopya = Path(gecici) / "t.db"
            shutil.copyfile(db, kopya)
            wal = dizin / "tahta-kontrol.db-wal"
            if wal.is_file():
                shutil.copyfile(wal, Path(gecici) / "t.db-wal")
            baglanti = sqlite3.connect(kopya)
            try:
                son, sayi = baglanti.execute(
                    "SELECT MAX(son_gorulme), COUNT(*) FROM tahta WHERE durum = 'onayli'"
                ).fetchone()
                aday.son_temas = int(son) if son else None
                aday.tahta_sayisi = int(sayi or 0)
                aday.kullanici_sayisi = int(baglanti.execute("SELECT COUNT(*) FROM kullanici").fetchone()[0])
            finally:
                baglanti.close()
    except (OSError, sqlite3.Error) as hata:
        aday.okunamadi = type(hata).__name__
    return aday


def aday_sec(adaylar: list[Aday], tercih: Path | None = None) -> tuple[Aday | None, str]:
    """Hangi eski dizin taşınacak? Belirsizse (None, neden).

    Tahtaların bağlı olduğu sertifika, tahtaların en son konuştuğu dizindedir: en yeni
    tahta teması kazanır. Hiçbirinde tahta teması yoksa kurucuyu çalıştıran hesabın
    dizini (tercih) seçilir; o da yoksa seçim yapılmaz.
    """
    if not adaylar:
        return None, "eski veri yok"
    if len(adaylar) == 1:
        return adaylar[0], "tek eski veri dizini"
    temasli = [a for a in adaylar if a.son_temas]
    if temasli:
        en_yeni = max(a.son_temas or 0 for a in temasli)
        enler = [a for a in temasli if a.son_temas == en_yeni]
        if len(enler) == 1:
            return enler[0], "tahtaların en son bağlandığı veri dizini"
        return None, "birden çok veri dizininde tahtalar aynı anda görülmüş"
    if tercih is not None:
        for a in adaylar:
            if _ayni(a.yol, tercih):
                return a, "hiçbirinde tahta yok; kurucuyu çalıştıran hesabın veri dizini"
    return None, "birden çok eski veri dizini var ve hiçbirinde tahta kaydı yok"


def _ayni(a: Path, b: Path) -> bool:
    try:
        return os.path.normcase(str(a.resolve())) == os.path.normcase(str(b.resolve()))
    except OSError:
        return os.path.normcase(str(a)) == os.path.normcase(str(b))


def profil_dizinleri() -> list[Path]:
    """Bu bilgisayardaki kullanıcı profilleri (yalnız okunur: kayıt defteri ProfileList + Users klasörü)."""
    bulunan: list[Path] = []
    try:
        import winreg  # yalnız Windows

        anahtar_yolu = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList"
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, anahtar_yolu) as kok:
            i = 0
            while True:
                try:
                    alt = winreg.EnumKey(kok, i)
                except OSError:
                    break
                i += 1
                with contextlib.suppress(OSError), winreg.OpenKey(kok, alt) as k:
                    deger, _ = winreg.QueryValueEx(k, "ProfileImagePath")
                    bulunan.append(Path(os.path.expandvars(str(deger))))
    except (ImportError, OSError):
        pass
    ev = os.environ.get("USERPROFILE")
    if ev:
        with contextlib.suppress(OSError):
            bulunan.extend(p for p in Path(ev).parent.iterdir() if p.is_dir())
    return bulunan


def aday_dizinleri(profiller: list[Path], tercih: Path | None, hedef: Path) -> list[Path]:
    """Taşınabilecek eski veri dizinleri (tercih önce, yinelenmeden, hedef hariç)."""
    yollar = ([tercih] if tercih else []) + [p / "AppData" / "Local" / "TahtaKontrol" for p in profiller]
    sonuc: list[Path] = []
    for yol in yollar:
        if _ayni(yol, hedef) or any(_ayni(yol, s) for s in sonuc):
            continue
        with contextlib.suppress(OSError):
            if aday_mi(yol):
                sonuc.append(yol)
    return sonuc


# ---- kopyalama ---------------------------------------------------------------------------
def _yerlesim_sirasi(goreli: Path) -> tuple[int, str]:
    """Yerleştirme sırası: önce diğer dosyalar ve sertifika çifti, sonra -wal, EN SON veritabanı."""
    ad = goreli.name
    if len(goreli.parts) == 1 and ad == "tahta-kontrol.db":
        return 2, str(goreli)
    if len(goreli.parts) == 1 and ad.startswith("tahta-kontrol.db"):
        return 1, str(goreli)
    return 0, str(goreli)


def kopyala(kaynak: Path, hedef: Path) -> list[str]:
    """Kaynağı hedefe kopyalar ve doğrular; hata olursa yarım kopyayı siler ve TasimaHatasi fırlatır.

    Kaynakta hiçbir dosya değiştirilmez. Sembolik bağlar izlenmez. Kopyalama ve doğrulama hedefteki
    geçici dizinde yapılır; dosyalar ancak hepsi doğrulanınca `SURUYOR` işaretiyle yerlerine taşınır.
    """
    if not hedef.exists():
        hedef.mkdir(parents=True)
    gecici = hedef / GECICI
    if gecici.exists():
        shutil.rmtree(gecici)
    try:
        gecici.mkdir()
        ozetler: dict[Path, str] = {}
        for kok, dizinler, dosyalar in os.walk(kaynak, followlinks=False):
            kok_yol = Path(kok)
            dizinler[:] = [d for d in dizinler if not (kok_yol / d).is_symlink()]
            for ad in sorted(dosyalar):
                kaynak_dosya = kok_yol / ad
                if atlanir_mi(ad) or kaynak_dosya.is_symlink() or not kaynak_dosya.is_file():
                    continue
                goreli = kaynak_dosya.relative_to(kaynak)
                if (hedef / goreli).exists():
                    raise TasimaHatasi(f"hedefte zaten var: {goreli}")
                gecici_dosya = gecici / goreli
                gecici_dosya.parent.mkdir(parents=True, exist_ok=True)
                ozet = _ozet(kaynak_dosya)
                shutil.copyfile(kaynak_dosya, gecici_dosya)  # izinler kopyalanmaz: hedefinkini devralır
                with contextlib.suppress(OSError):
                    st = kaynak_dosya.stat()
                    os.utime(gecici_dosya, (st.st_atime, st.st_mtime))
                ozetler[goreli] = ozet
        for goreli, ozet in ozetler.items():
            if _ozet(gecici / goreli) != ozet:
                raise TasimaHatasi(f"kopya özeti tutmuyor: {goreli}")
        db = gecici / "tahta-kontrol.db"
        if db.is_file():
            baglanti = sqlite3.connect(db)
            try:
                durum = baglanti.execute("PRAGMA integrity_check").fetchone()[0]
            finally:
                baglanti.close()
            if durum != "ok":
                raise TasimaHatasi(f"veritabanı bütünlük denetimi: {durum}")
        sert, anahtar = gecici / "sunucu-sertifika.pem", gecici / "sunucu-anahtar.pem"
        if sert.is_file() != anahtar.is_file():
            raise TasimaHatasi("sertifika ile anahtardan yalnız biri var")
        # Yerleştirme: işaret yazılır, dosyalar aynı birim içinde yeniden adlandırılır (kısa bir adım;
        # kesilirse sonraki çalıştırma toparlar), işaret en son silinir.
        (hedef / SURUYOR).write_text(
            "Tahta Kontrol: eski veri bu klasöre yerleştiriliyor. Bu dosya kalmışsa yerleştirme yarıda\n"
            "kesilmiştir; sunucu hizmeti açılmaz. Kurucuyu yeniden çalıştırın: yarım dosyalar\n"
            "yarim-tasima-* klasörüne kaldırılır ve taşıma baştan yapılır.\n",
            encoding="utf-8",
        )
        yerlesen = []
        for goreli in sorted((p.relative_to(gecici) for p in gecici.rglob("*") if p.is_file()), key=_yerlesim_sirasi):
            if goreli.name.endswith(_ATLANAN_SON_EKLER):
                continue  # bütünlük denetiminin bıraktığı paylaşımlı bellek dosyası
            (hedef / goreli).parent.mkdir(parents=True, exist_ok=True)
            os.replace(gecici / goreli, hedef / goreli)
            yerlesen.append(goreli)
        shutil.rmtree(gecici, ignore_errors=True)
        (hedef / SURUYOR).unlink()
        return [str(g) for g in yerlesen if g in ozetler]
    except Exception as hata:
        if (hedef / SURUYOR).exists():  # yerleştirme sırasında hata: yarım dosyalar kenara kaldırılır
            _yarim_kaldir(hedef)
        shutil.rmtree(gecici, ignore_errors=True)
        if isinstance(hata, TasimaHatasi):
            raise
        raise TasimaHatasi(f"{type(hata).__name__}: {hata}") from hata


def _yarim_kaldir(hedef: Path) -> Path | None:
    """Yarıda kalmış yerleştirmeden hedefte kalanları (günlük, işaretler ve geçici dizin dışında her şey)
    bir `yarim-tasima-<zaman>` klasörüne kaldırır (SİLMEZ) ve `SURUYOR` işaretini siler."""
    kenar = hedef / (YARIM_ON_EKI + time.strftime("%Y%m%d-%H%M%S"))
    sira = 1
    while kenar.exists():
        sira += 1
        kenar = hedef / (YARIM_ON_EKI + time.strftime("%Y%m%d-%H%M%S") + f"-{sira}")
    for girdi in sorted(hedef.iterdir()):
        if girdi.name in ("gunluk", BEKLIYOR, SURUYOR, GECICI) or girdi.name.startswith(YARIM_ON_EKI):
            continue
        kenar.mkdir(exist_ok=True)
        with contextlib.suppress(OSError):
            os.replace(girdi, kenar / girdi.name)
    with contextlib.suppress(OSError):
        (hedef / SURUYOR).unlink()
    return kenar if kenar.exists() else None


def kesinti_toparla(hedef: Path) -> str:
    """Önceki taşımanın kesintiye uğramış izlerini toparlar; ne yapıldıysa açıklaması (yoksa "")."""
    if (hedef / SURUYOR).exists():
        kenar = _yarim_kaldir(hedef)
        shutil.rmtree(hedef / GECICI, ignore_errors=True)
        return (
            "Önceki taşıma yerleştirme sırasında kesilmiş; yarım dosyalar "
            f"{kenar.name if kenar else '-'} klasörüne kaldırıldı, taşıma baştan yapılıyor."
        )
    if (hedef / GECICI).exists():
        shutil.rmtree(hedef / GECICI, ignore_errors=True)
        return "Önceki taşımanın yarım geçici kopyası silindi."
    return ""


def _gunluge_yaz(hedef: Path, satir: str) -> None:
    with contextlib.suppress(OSError):
        (hedef / "gunluk").mkdir(parents=True, exist_ok=True)
        with open(hedef / "gunluk" / "tasima.log", "a", encoding="utf-8") as f:
            f.write(time.strftime("%d.%m.%Y %H:%M:%S") + " " + satir + "\n")


def _bekliyor_yaz(hedef: Path, neden: str, adaylar: list[Aday]) -> None:
    hedef.mkdir(parents=True, exist_ok=True)
    satirlar = [
        "Tahta Kontrol: eski veri taşınamadı; sunucu hizmeti bu dosya durdukça açılmaz.",
        f"Neden: {neden}",
        "",
        "Bulunan eski veri dizinleri:",
        *[
            f"- {a.yol}  (onaylı tahta: {a.tahta_sayisi}, kullanıcı: {a.kullanici_sayisi}, "
            f"son tahta teması: {time.strftime('%d.%m.%Y %H:%M', time.localtime(a.son_temas)) if a.son_temas else 'yok'})"
            for a in adaylar
        ],
        "",
        "Çözüm (yönetici komut istemi):",
        "  net stop TahtaKontrol",
        '  "<Program klasörü>\\TahtaKontrol.exe" tasi --hedef "<bu klasör>" --kaynak "<doğru eski klasör>"',
        "  (ya da doğru eski klasördeki dosyaları bu klasöre elle kopyalayın)",
        "  bu dosyayı silin; net start TahtaKontrol",
        "Eski veri gerçekten istenmiyorsa (yeni sertifika üretilir, bütün tahtalara ajan yeniden kurulur)",
        "yalnız bu dosyayı silip hizmeti başlatın.",
    ]
    (hedef / BEKLIYOR).write_text("\n".join(satirlar) + "\n", encoding="utf-8")


def bekliyor_mu(hedef: Path) -> bool:
    """Hizmet açılmamalı mı: taşıma bekliyor ya da yerleştirme yarıda kalmış."""
    return (hedef / BEKLIYOR).exists() or (hedef / SURUYOR).exists()


def _degisme_zamani(dizin: Path) -> float | None:
    zamanlar = []
    for ad in ("tahta-kontrol.db", "tahta-kontrol.db-wal"):
        with contextlib.suppress(OSError):
            zamanlar.append((dizin / ad).stat().st_mtime)
    return max(zamanlar) if zamanlar else None


def geri_donus_kopyalari(profiller: list[Path], tercih: Path | None, hedef: Path) -> list[Aday]:
    """Taşınmış (TASINDI.txt) ama taşımadan SONRA veritabanı değişmiş eski klasörler: eski sürüme dönülüp
    orada kullanılmış demektir; hedefteki kopya o dönemin değişikliklerini içermez."""
    yollar = ([tercih] if tercih else []) + [p / "AppData" / "Local" / "TahtaKontrol" for p in profiller]
    sonuc: list[Aday] = []
    gorulen: list[Path] = []
    for yol in yollar:
        if _ayni(yol, hedef) or any(_ayni(yol, g) for g in gorulen):
            continue
        gorulen.append(yol)
        with contextlib.suppress(OSError):
            isaret = yol / TASINDI
            if yol.is_symlink() or not isaret.is_file() or not veri_var(yol):
                continue
            degisme = _degisme_zamani(yol)
            if degisme is not None and degisme > isaret.stat().st_mtime + GERI_DONUS_PAYI_SN:
                sonuc.append(aday_oku(yol))
    return sonuc


def _geri_donus_bekliyor_yaz(hedef: Path, eskiler: list[Aday]) -> None:
    mevcut = aday_oku(hedef)

    def satir(a: Aday) -> str:
        temas = time.strftime("%d.%m.%Y %H:%M", time.localtime(a.son_temas)) if a.son_temas else "yok"
        return f"- {a.yol}  (onaylı tahta: {a.tahta_sayisi}, kullanıcı: {a.kullanici_sayisi}, son tahta teması: {temas})"

    satirlar = [
        "Tahta Kontrol: sunucu hizmeti bu dosya durdukça açılmaz.",
        "Neden: daha önce bu klasöre taşınmış eski veri klasörü taşımadan SONRA kullanılmış (eski sürüme",
        "dönülmüş olabilir). Hangi verinin doğru olduğu kendiliğinden anlaşılamaz.",
        "",
        "Hizmetin klasörü (bu klasör):",
        satir(mevcut),
        "Taşımadan sonra değişen eski klasör(ler):",
        *[satir(a) for a in eskiler],
        "",
        "Çözüm (yönetici komut istemi, önce: net stop TahtaKontrol):",
        "A) Eski klasördeki veri doğruysa (tahtalar en son ona bağlandıysa): bu klasördeki tahta-kontrol.db*,",
        "   sunucu-sertifika.pem ve sunucu-anahtar.pem dosyalarını bir yedek klasörüne taşıyın; eski klasördeki",
        "   TASINDI.txt dosyasını silin; sonra:",
        '   "<Program klasörü>\\TahtaKontrol.exe" tasi --hedef "<bu klasör>" --kaynak "<eski klasör>"',
        "B) Bu klasördeki veri doğruysa: eski klasörün adını değiştirin (ör. TahtaKontrol-eski) ya da silin.",
        "Sonra bu dosyayı silin; net start TahtaKontrol",
    ]
    (hedef / BEKLIYOR).write_text("\n".join(satirlar) + "\n", encoding="utf-8")


# ---- ana akış ----------------------------------------------------------------------------
def calistir(
    hedef: Path,
    tercih: Path | None = None,
    profiller: list[Path] | None = None,
    kaynak: Path | None = None,
) -> Sonuc:
    """Kurucunun çağırdığı taşıma. `kaynak` verilirse seçim yapılmaz (elle çözüm)."""
    hedef = Path(hedef)
    toparlama = kesinti_toparla(hedef) if hedef.is_dir() else ""
    if toparlama:
        _gunluge_yaz(hedef, toparlama)
    if veri_var(hedef):
        if kaynak is None:
            eskiler = geri_donus_kopyalari(profil_dizinleri() if profiller is None else profiller, tercih, hedef)
            if eskiler:
                _geri_donus_bekliyor_yaz(hedef, eskiler)
                sonuc = Sonuc(BELIRSIZ, "Taşınmış eski veri klasörü taşımadan sonra kullanılmış; hangi verinin "
                                        "doğru olduğu anlaşılamadı, hizmet başlatılmadı.")  # fmt: skip
                _gunluge_yaz(hedef, f"[{sonuc.kod}] {sonuc.ileti} Eski: " + "; ".join(str(a.yol) for a in eskiler))
                return sonuc
        if (hedef / BEKLIYOR).exists():
            (hedef / BEKLIYOR).unlink()
        sonuc = Sonuc(
            HEDEF_DOLU, "Hizmetin veri dizininde veri var; taşıma yapılmadı (eski klasörlere dokunulmadı)."
        )
        _gunluge_yaz(hedef, f"[{sonuc.kod}] {sonuc.ileti}")
        return sonuc
    if kaynak is not None:
        kaynak = Path(kaynak)
        if not aday_mi(kaynak):
            sonuc = Sonuc(HATA, f"Kaynakta taşınacak veri yok ya da daha önce taşınmış: {kaynak}")
            _gunluge_yaz(hedef, f"[{sonuc.kod}] {sonuc.ileti}")
            return sonuc
        secilen, neden = aday_oku(kaynak), "elle verilen kaynak"
        adaylar = [secilen]
    else:
        yollar = aday_dizinleri(profil_dizinleri() if profiller is None else profiller, tercih, hedef)
        adaylar = [aday_oku(y) for y in yollar]
        secilen, neden = aday_sec(adaylar, tercih)
        if not adaylar:
            if (hedef / BEKLIYOR).exists():
                (hedef / BEKLIYOR).unlink()
            sonuc = Sonuc(ESKI_VERI_YOK, "Taşınacak eski veri bulunmadı; ilk kurulum.")
            _gunluge_yaz(hedef, f"[{sonuc.kod}] {sonuc.ileti}")
            return sonuc
        if secilen is None:
            _bekliyor_yaz(hedef, neden, adaylar)
            sonuc = Sonuc(BELIRSIZ, f"Eski veri taşınmadı: {neden}.")
            _gunluge_yaz(
                hedef, f"[{sonuc.kod}] {sonuc.ileti} Adaylar: " + "; ".join(str(a.yol) for a in adaylar)
            )
            return sonuc
    try:
        kopyalanan = kopyala(secilen.yol, hedef)
    except TasimaHatasi as hata:
        _bekliyor_yaz(hedef, f"kopyalama başarısız ({hata})", adaylar)
        sonuc = Sonuc(HATA, f"Eski veri kopyalanamadı: {hata}", secilen.yol)
        _gunluge_yaz(hedef, f"[{sonuc.kod}] {sonuc.ileti} Kaynak: {secilen.yol}")
        return sonuc
    with contextlib.suppress(OSError):
        (secilen.yol / TASINDI).write_text(
            "Bu klasördeki Tahta Kontrol verisi "
            f"{time.strftime('%d.%m.%Y %H:%M')} tarihinde {hedef} klasörüne kopyalandı.\n"
            "Sunucu artık Windows hizmeti olarak oradaki veriyle çalışır. Bu klasör geri dönüş için\n"
            "bırakıldı; burada yapılan değişiklikler sunucuya yansımaz.\n",
            encoding="utf-8",
        )
    if (hedef / BEKLIYOR).exists():
        (hedef / BEKLIYOR).unlink()
    digerleri = [a for a in adaylar if a is not secilen]
    ileti = f"Eski veri taşındı ({len(kopyalanan)} dosya; {neden})."
    if digerleri:
        ileti += f" Başka {len(digerleri)} eski veri dizinine dokunulmadı."
    _gunluge_yaz(hedef, f"[0] {ileti} Kaynak: {secilen.yol}")
    return Sonuc(TASINDI_KOD, ileti, secilen.yol, kopyalanan)
