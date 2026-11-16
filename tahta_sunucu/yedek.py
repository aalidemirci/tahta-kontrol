"""Şifreli yedek (A6): parola, yedek alma, saklama, ikinci kopya ve geri yükleme.

Dosya biçimi (`.tkyedek`, biçim 1):
    0      8 bayt   MAGIC = b"TKYEDEK\\x01"
    8      4 bayt   başlık uzunluğu (big-endian, ≤ 4096)
    12     n bayt   başlık (UTF-8 JSON; okul adı GİRMEZ)
    12+n   kalan    AES-256-GCM şifreli ZIP + 16 bayt etiket (AAD = ilk 12+n bayt)

Anahtar: yedek parolası → scrypt → 32 bayt → X25519 özel anahtar. Sunucuda YALNIZ açık
anahtar (ve tuz, KDF değiştirgeleri) durur; parola ve özel anahtar hiçbir yere yazılmaz.
Her yedek için geçici bir X25519 anahtarı üretilir; ortak sır HKDF-SHA256 ile AES anahtarına
dönüşür. Böylece sunucu, parolayı bilmeden yedek alabilir ama aldığı yedeği açamaz.

Şifreli ZIP'te tam olarak dört dosya vardır: veritabanı görüntüsü, sunucu sertifikası ve
anahtarı (kural 4: sertifika kaybı = bütün tahtalara yeniden kurulum) ve `bilgi.json`.

Geri yükleme iki adımlıdır: (1) dosya ve parola doğrulanır, çözülen dosyalar veri dizinindeki
`geri-yukleme/bekleyen/` altına yazılır (canlı veritabanıyla aynı klasör izinleri), önizleme
`bekleyen.json`'a; (2) onaylanınca program yeniden açılırken `bekleyeni_uygula()` eski
dosyaları `geri-yukleme-oncesi/<an>/`'a taşıyıp yedektekileri yerleştirir.
"""

from __future__ import annotations

import getpass
import hashlib
import hmac
import io
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import struct
import zipfile
from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath
from zoneinfo import ZoneInfo

from cryptography import x509
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from . import __version__, ayar, vt

gunluk = logging.getLogger("tahta-sunucu")
ISTANBUL = ZoneInfo("Europe/Istanbul")

MAGIC = b"TKYEDEK\x01"
BICIM = 1
BASLIK_EN_UZUN = 4096
HKDF_BILGI = b"TahtaKontrol/yedek/v1"
# Parola belirlenirken kullanılan değiştirgeler (testler daha küçük n ile çalışır).
KDF_VARSAYILAN = {"n": 2**17, "r": 8, "p": 1}
# Kötü niyetli dosya bellek tüketmesin: çözerken kabul edilen üst sınırlar.
KDF_SINIR = {"n": 2**20, "r": 16, "p": 4}
KDF_BELLEK = 2**28 + 2**20
PAROLA_EN_KISA = 12
SAKLAMA_VARSAYILAN = 14
SAKLAMA_ARALIK = (3, 90)
ELLE_SAKLAMA = 10
DOSYA_EN_BUYUK = 200 * 1024 * 1024
ACILMIS_EN_BUYUK = 1024 * 1024 * 1024
OTOMATIK_GECIKME_SN = 300  # program açıldıktan en az 5 dk sonra
OTOMATIK_YENIDEN_SN = 1800  # başarısız denemeden sonra 30 dk
YAZMA_DENEMESI = ".tk-yazma-denemesi"
VT_ADI = "tahta-kontrol.db"
SERTIFIKA_ADI = "sunucu-sertifika.pem"
ANAHTAR_ADI = "sunucu-anahtar.pem"
ZIP_DOSYALARI = (VT_ADI, SERTIFIKA_ADI, ANAHTAR_ADI, "bilgi.json")
AD_DESENI = re.compile(r"^tahta-kontrol-(gunluk|elle)-(\d{4})-(\d{2})-(\d{2})(?:-(\d{6}))?\.tkyedek$")
TUR_ADI = {"gunluk": "Günlük", "elle": "Elle"}
# Windows'ta ikinci kopya klasörüne yazma izni verme komutu; Yedekler sayfasında ve hata iletisinde
# gösterilir. Hizmet kipinde (6B, LocalService) SID biçimi; 6A'da program oturum açmış kullanıcının
# hesabıyla çalıştığı için izin o hesaba verilir (izin_komutu()).
IZIN_KOMUTU = 'icacls "{yol}" /grant *S-1-5-19:(OI)(CI)M'
IZIN_KOMUTU_KULLANICI = 'icacls "{yol}" /grant "{hesap}:(OI)(CI)M"'
BEKLEYEN_OMRU_SN = 24 * 3600  # onaylanmamış (çözülmüş, şifresiz) geri yükleme en çok 1 gün durur

PAROLA_YANLIS = "Yedek parolası yanlış ya da bu yedek başka bir parolayla alınmış."
DOSYA_BOZUK = "Yedek dosyası bozuk ya da değiştirilmiş."
DOSYA_GECERSIZ = "Bu dosya bir Tahta Kontrol yedeği değil."
DAHA_YENI = "Bu yedek daha yeni bir Tahta Kontrol sürümünden; önce programı güncelleyin."
PAROLA_YOK = "Yedek parolası belirlenmedi; yedek alınamaz."


class YedekHatasi(Exception):
    """Kullanıcıya gösterilebilir yedek/geri yükleme hatası (parola ya da sır içermez)."""


class YedekMesgul(YedekHatasi):
    """Başka bir yedek, göç ya da geri yükleme sürüyor."""


def izin_komutu(yol: str) -> str:
    """Programı çalıştıran hesaba (hizmet kipinde LocalService'e) yazma izni veren icacls komutu."""
    if ayar.HIZMET:
        return IZIN_KOMUTU.format(yol=yol)
    kullanici = os.environ.get("USERNAME") or ""
    if not kullanici:
        try:
            kullanici = getpass.getuser()
        except Exception:  # noqa: BLE001 - ortamda kullanıcı adı yoksa genel ad
            kullanici = "%USERNAME%"
    alan = os.environ.get("USERDOMAIN") or ""
    hesap = alan + "\\" + kullanici if alan and kullanici != "%USERNAME%" else kullanici
    return IZIN_KOMUTU_KULLANICI.format(yol=yol, hesap=hesap.replace('"', ""))


# ---- yollar ve ayar --------------------------------------------------------------------
def dizin() -> Path:
    yol = ayar.veri_dizini() / "yedekler"
    yol.mkdir(parents=True, exist_ok=True)
    return yol


def bekleyen_dizini() -> Path:
    return ayar.veri_dizini() / "geri-yukleme"


def ayarlar(b) -> dict:
    """`ayar.yedek` + varsayılanlar. `parola_var` türetilmiş alandır (yazılmaz)."""
    kayitli = vt.ayar_al(b, "yedek") or {}
    if not isinstance(kayitli, dict):
        kayitli = {}
    sonuc = {"saklama": SAKLAMA_VARSAYILAN, "kopya_dizini": "", **kayitli}
    sonuc["parola_var"] = bool(kayitli.get("acik_anahtar"))
    return sonuc


def _ayar_yaz(b, deger: dict) -> None:
    vt.ayar_yaz(b, "yedek", {k: v for k, v in deger.items() if k != "parola_var"})


def son_yedek(b) -> dict:
    return vt.ayar_al(b, "son_yedek") or {}


def _an(simdi: int | None = None) -> datetime:
    return datetime.fromtimestamp(vt.simdi() if simdi is None else simdi, ISTANBUL)


def gunluk_adi(an: datetime) -> str:
    return f"tahta-kontrol-gunluk-{an:%Y-%m-%d}.tkyedek"


def elle_adi(an: datetime) -> str:
    return f"tahta-kontrol-elle-{an:%Y-%m-%d-%H%M%S}.tkyedek"


# ---- anahtarlar ------------------------------------------------------------------------
def _ozel_anahtar(parola: str, tuz: bytes, kdf: dict) -> X25519PrivateKey:
    try:
        tohum = hashlib.scrypt(
            parola.encode("utf-8"), salt=tuz, n=int(kdf["n"]), r=int(kdf["r"]), p=int(kdf["p"]),
            maxmem=KDF_BELLEK, dklen=32,
        )  # fmt: skip
    except (ValueError, MemoryError) as hata:
        raise YedekHatasi("Yedek dosyasının anahtar değiştirgeleri desteklenmiyor.") from hata
    return X25519PrivateKey.from_private_bytes(tohum)


def _acik_hex(anahtar) -> str:
    return anahtar.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def parola_dogrula(parola: str, parola2: str) -> None:
    if len(parola) < PAROLA_EN_KISA:
        raise YedekHatasi(f"Yedek parolası en az {PAROLA_EN_KISA} karakter olmalı.")
    if parola != parola2:
        raise YedekHatasi("İki yedek parolası aynı girilmeli.")


def parola_belirle(b, parola: str) -> bool:
    """Yeni tuzla açık anahtarı üretip `ayar.yedek`'e yazar; daha önce parola varsa True (değişti)."""
    onceki = ayarlar(b)
    tuz = secrets.token_bytes(16)
    kdf = dict(KDF_VARSAYILAN)
    ozel = _ozel_anahtar(parola, tuz, kdf)
    yeni = {
        "acik_anahtar": _acik_hex(ozel),
        "tuz": tuz.hex(),
        **kdf,
        "parola_zamani": vt.simdi(),
        "saklama": int(onceki.get("saklama") or SAKLAMA_VARSAYILAN),
        "kopya_dizini": str(onceki.get("kopya_dizini") or ""),
    }
    _ayar_yaz(b, yeni)
    return onceki["parola_var"]


def _hkdf(ortak: bytes, gecici: bytes, alici: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=HKDF_BILGI + gecici + alici).derive(ortak)


# ---- şifreleme -------------------------------------------------------------------------
def sifrele(icerik: bytes, ayar_: dict, tur: str, olusturma: int, sema: int) -> bytes:
    alici = bytes.fromhex(ayar_["acik_anahtar"])
    gecici_ozel = X25519PrivateKey.generate()
    gecici = bytes.fromhex(_acik_hex(gecici_ozel))
    anahtar = _hkdf(gecici_ozel.exchange(X25519PublicKey.from_public_bytes(alici)), gecici, alici)
    nonce = secrets.token_bytes(12)
    baslik = json.dumps(
        {
            "bicim": BICIM, "uygulama": "tahta-kontrol", "surum": __version__, "sema": sema, "tur": tur,
            "olusturma": olusturma,
            "kdf": {"ad": "scrypt", "n": ayar_["n"], "r": ayar_["r"], "p": ayar_["p"], "tuz": ayar_["tuz"]},
            "alici": alici.hex(), "gecici": gecici.hex(), "nonce": nonce.hex(),
        },
        ensure_ascii=False, separators=(",", ":"),
    ).encode("utf-8")  # fmt: skip
    on = MAGIC + struct.pack(">I", len(baslik)) + baslik
    return on + AESGCM(anahtar).encrypt(nonce, icerik, on)


def _hex(deger, uzunluk: int) -> bytes:
    if not isinstance(deger, str) or not re.fullmatch(rf"[0-9a-f]{{{uzunluk * 2}}}", deger):
        raise YedekHatasi(DOSYA_GECERSIZ)
    return bytes.fromhex(deger)


def baslik_oku(veri: bytes) -> tuple[dict, bytes, bytes]:
    """(başlık, AAD, şifreli metin); biçim hatasında YedekHatasi."""
    if len(veri) < 12 or veri[:8] != MAGIC:
        raise YedekHatasi(DOSYA_GECERSIZ)
    (uzunluk,) = struct.unpack(">I", veri[8:12])
    if uzunluk > BASLIK_EN_UZUN or len(veri) < 12 + uzunluk + 16:
        raise YedekHatasi(DOSYA_GECERSIZ)
    try:
        baslik = json.loads(veri[12 : 12 + uzunluk].decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as hata:
        raise YedekHatasi(DOSYA_GECERSIZ) from hata
    if not isinstance(baslik, dict) or baslik.get("bicim") != BICIM or baslik.get("uygulama") != "tahta-kontrol":
        raise YedekHatasi(DOSYA_GECERSIZ)
    return baslik, veri[: 12 + uzunluk], veri[12 + uzunluk :]


def coz(veri: bytes, parola: str) -> tuple[dict, dict[str, bytes]]:
    """Yedeği çözer ve doğrular; (bilgi.json, {dosya adı: bayt}) döndürür.

    Sıra (§8.2): MAGIC → başlık → KDF sınırları → parola/açık anahtar eşleşmesi → GCM →
    ZIP üyeleri (tam dört ad, toplam ≤ 1 GB) → integrity_check → şema sürümü → sertifika/anahtar.
    """
    baslik, aad, sifreli = baslik_oku(veri)
    kdf = baslik.get("kdf")
    if not isinstance(kdf, dict) or kdf.get("ad") != "scrypt":
        raise YedekHatasi(DOSYA_GECERSIZ)
    for alan, sinir in KDF_SINIR.items():
        deger = kdf.get(alan)
        if not isinstance(deger, int) or isinstance(deger, bool) or not 1 <= deger <= sinir:
            raise YedekHatasi("Yedek dosyasının anahtar değiştirgeleri izin verilen sınırların dışında.")
    if kdf["n"] & (kdf["n"] - 1) or kdf["n"] < 2:
        raise YedekHatasi(DOSYA_GECERSIZ)
    tuz = _hex(kdf.get("tuz"), 16)
    alici = _hex(baslik.get("alici"), 32)
    gecici = _hex(baslik.get("gecici"), 32)
    nonce = _hex(baslik.get("nonce"), 12)
    ozel = _ozel_anahtar(parola, tuz, kdf)
    if not hmac.compare_digest(bytes.fromhex(_acik_hex(ozel)), alici):
        raise YedekHatasi(PAROLA_YANLIS)
    try:
        anahtar = _hkdf(ozel.exchange(X25519PublicKey.from_public_bytes(gecici)), gecici, alici)
        icerik = AESGCM(anahtar).decrypt(nonce, sifreli, aad)
    except (InvalidTag, ValueError) as hata:
        raise YedekHatasi(DOSYA_BOZUK) from hata
    dosyalar = _zip_ac(icerik)
    try:
        bilgi = json.loads(dosyalar["bilgi.json"].decode("utf-8"))
        if not isinstance(bilgi, dict):
            raise ValueError
    except (UnicodeDecodeError, ValueError) as hata:
        raise YedekHatasi(DOSYA_BOZUK) from hata
    sema = _veritabani_denetle(dosyalar[VT_ADI])
    bilgi["sema"] = sema
    bilgi["parmak_izi"] = _sertifika_denetle(dosyalar[SERTIFIKA_ADI], dosyalar[ANAHTAR_ADI])
    bilgi.setdefault("olusturma", baslik.get("olusturma"))
    bilgi.setdefault("surum", baslik.get("surum"))
    return bilgi, dosyalar


def _zip_ac(icerik: bytes) -> dict[str, bytes]:
    try:
        arsiv = zipfile.ZipFile(io.BytesIO(icerik))
        uyeler = arsiv.infolist()
    except zipfile.BadZipFile as hata:
        raise YedekHatasi(DOSYA_BOZUK) from hata
    adlar = [u.filename for u in uyeler]
    if sorted(adlar) != sorted(ZIP_DOSYALARI):
        raise YedekHatasi("Yedeğin içinde beklenmeyen dosya var; geri yüklenmedi.")
    if sum(u.file_size for u in uyeler) > ACILMIS_EN_BUYUK:
        raise YedekHatasi("Yedeğin açılmış boyutu sınırı aşıyor; geri yüklenmedi.")
    sonuc = {}
    try:
        for u in uyeler:
            with arsiv.open(u) as akis:
                parca = akis.read(u.file_size + 1)
            if len(parca) != u.file_size:
                raise YedekHatasi(DOSYA_BOZUK)
            sonuc[u.filename] = parca
    except (zipfile.BadZipFile, OSError) as hata:
        raise YedekHatasi(DOSYA_BOZUK) from hata
    return sonuc


def _veritabani_denetle(vt_baytlari: bytes) -> int:
    """Geçici dosyada integrity_check ve şema sürümü; şema sürümünü döndürür."""
    hedef = bekleyen_dizini()
    hedef.mkdir(parents=True, exist_ok=True)
    gecici = hedef / f".denetim-{secrets.token_hex(6)}.db"
    try:
        gecici.write_bytes(vt_baytlari)
        baglanti = sqlite3.connect(gecici)
        try:
            sonuc = baglanti.execute("PRAGMA integrity_check").fetchone()[0]
            sema = baglanti.execute("PRAGMA user_version").fetchone()[0]
        finally:
            baglanti.close()
    except sqlite3.Error as hata:
        raise YedekHatasi("Yedekteki veritabanı açılamadı; geri yüklenmedi.") from hata
    finally:
        for ek in ("", "-wal", "-shm", "-journal"):
            try:
                Path(str(gecici) + ek).unlink()
            except OSError:
                pass
    if sonuc != "ok":
        raise YedekHatasi("Yedekteki veritabanı bozuk (bütünlük denetimi geçmedi); geri yüklenmedi.")
    if sema > len(vt.GOCLER):
        raise YedekHatasi(DAHA_YENI)
    if sema < 1:
        raise YedekHatasi("Yedekteki veritabanı boş; geri yüklenmedi.")
    return int(sema)


def parmak_izi_hesapla(sertifika_pem: bytes) -> str:
    yuklu = x509.load_pem_x509_certificate(sertifika_pem)
    return hashlib.sha256(yuklu.public_bytes(serialization.Encoding.DER)).hexdigest()


def _sertifika_denetle(sertifika_pem: bytes, anahtar_pem: bytes) -> str:
    try:
        sertifika = x509.load_pem_x509_certificate(sertifika_pem)
        anahtar = serialization.load_pem_private_key(anahtar_pem, password=None)
        bicim = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        if sertifika.public_key().public_bytes(*bicim) != anahtar.public_key().public_bytes(*bicim):
            raise ValueError("eşleşmiyor")
    except (ValueError, TypeError) as hata:
        raise YedekHatasi("Yedekteki sunucu sertifikası ve anahtarı birbirine ait değil; geri yüklenmedi.") from hata
    return parmak_izi_hesapla(sertifika_pem)


# ---- yedek alma ------------------------------------------------------------------------
def _atomik_yaz(hedef: Path, veri: bytes) -> None:
    gecici = hedef.with_name(f".{hedef.name}.yeni")
    try:
        with open(gecici, "wb") as dosya:
            dosya.write(veri)
            dosya.flush()
            os.fsync(dosya.fileno())
        os.replace(gecici, hedef)
    finally:
        try:
            gecici.unlink()
        except OSError:
            pass


def _icerik_uret(okul_adi: str, tahta_sayisi: int, kullanici_sayisi: int, olusturma: int) -> tuple[bytes, int]:
    """Şifrelenecek ZIP ve şema sürümü. Veritabanı SQLite yedek API'siyle tutarlı alınır."""
    veri = ayar.veri_dizini()
    gecici = dizin() / f".gecici-{secrets.token_hex(6)}.db"
    try:
        kaynak = vt.baglan()
        try:
            sema = kaynak.execute("PRAGMA user_version").fetchone()[0]
            hedef = sqlite3.connect(gecici)
            try:
                kaynak.backup(hedef)
            finally:
                hedef.close()
        finally:
            kaynak.close()
        vt_baytlari = gecici.read_bytes()
    finally:
        for ek in ("", "-wal", "-shm", "-journal"):
            try:
                Path(str(gecici) + ek).unlink()
            except OSError:
                pass
    sertifika = (veri / SERTIFIKA_ADI).read_bytes()
    anahtar = (veri / ANAHTAR_ADI).read_bytes()
    bilgi = {
        "surum": __version__, "sema": sema, "olusturma": olusturma, "okul_adi": okul_adi,
        "tahta_sayisi": tahta_sayisi, "kullanici_sayisi": kullanici_sayisi,
        "parmak_izi": parmak_izi_hesapla(sertifika),
    }  # fmt: skip
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as arsiv:
        arsiv.writestr(VT_ADI, vt_baytlari)
        arsiv.writestr(SERTIFIKA_ADI, sertifika)
        arsiv.writestr(ANAHTAR_ADI, anahtar)
        arsiv.writestr("bilgi.json", json.dumps(bilgi, ensure_ascii=False))
    return tampon.getvalue(), sema


def dondur(klasor: Path, saklama: int, simdi: int | None = None) -> list[str]:
    """Saklama: günlüklerden en yeni `saklama`, elle alınanlardan en yeni 10 kalır (AD sırasına göre).

    Elle alınan yedekler ayrıca YAŞA göre budanır: adındaki (İstanbul) tarihi `saklama` günden eski
    olan silinir. Yedekler süreli silinen kişisel verinin kopyasını taşır (KVKK notu); seyrek alınan
    elle yedekler bu süreyi aşmasın.
    """
    sinir = (_an(simdi) - timedelta(days=max(1, int(saklama)))).strftime("%Y%m%d")
    silinen = []
    for tur, kalan in (("gunluk", saklama), ("elle", ELLE_SAKLAMA)):
        adlar = sorted(
            (y.name for y in klasor.glob(f"tahta-kontrol-{tur}-*.tkyedek") if AD_DESENI.match(y.name)), reverse=True
        )
        silinecek = adlar[max(1, kalan) :]
        if tur == "elle":
            for ad in adlar[: max(1, kalan)]:
                yil, ay, gun = AD_DESENI.match(ad).groups()[1:4]
                if f"{yil}{ay}{gun}" < sinir:
                    silinecek.append(ad)
        for ad in silinecek:
            try:
                (klasor / ad).unlink()
                silinen.append(ad)
            except OSError:
                pass
    return silinen


def yedek_al(tur: str, *, kullanici: str = "sistem", ip: str = "", bekle: bool = True, simdi: int | None = None) -> dict:
    """Yedek alır: {"dosya", "yeni", "boyut", "kopya_hata"}. Aynı günün günlüğü varsa yeniden üretilmez.

    bekle=False (zamanlayıcı): kilit doluysa YedekMesgul. Hata: `son_yedek` yazılır, YedekHatasi.
    """
    if tur not in TUR_ADI:
        raise ValueError(tur)
    if not vt.KILIT.acquire(timeout=30 if bekle else 0):
        raise YedekMesgul("Başka bir yedek ya da geri yükleme sürüyor; biraz sonra yeniden deneyin.")
    try:
        return _yedek_al(tur, kullanici, ip, simdi)
    finally:
        vt.KILIT.release()


def _yedek_al(tur: str, kullanici: str, ip: str, simdi: int | None) -> dict:
    zaman = vt.simdi() if simdi is None else int(simdi)
    an = _an(zaman)
    with vt.islem() as b:
        ayar_ = ayarlar(b)
        okul_adi = vt.ayar_al(b, "okul_adi", "") or ""
        tahta_sayisi = b.execute("SELECT COUNT(*) FROM tahta WHERE durum != 'iptal'").fetchone()[0]
        kullanici_sayisi = b.execute("SELECT COUNT(*) FROM kullanici").fetchone()[0]
        onceki = son_yedek(b)
    if not ayar_["parola_var"]:
        raise YedekHatasi(PAROLA_YOK)
    ad = gunluk_adi(an) if tur == "gunluk" else elle_adi(an)
    hedef = dizin() / ad
    if hedef.exists():
        return {"dosya": ad, "yeni": False, "boyut": hedef.stat().st_size, "kopya_hata": ""}
    try:
        icerik, sema = _icerik_uret(okul_adi, tahta_sayisi, kullanici_sayisi, zaman)
        veri = sifrele(icerik, ayar_, tur, zaman, sema)
        _atomik_yaz(hedef, veri)
    except (OSError, sqlite3.Error, ValueError) as hata:
        neden = f"{type(hata).__name__}: {hata}"[:300]
        gunluk.warning("Yedek alınamadı: %s", neden)
        with vt.islem() as b:
            vt.ayar_yaz(b, "son_yedek", {**onceki, "zaman": zaman, "dosya": ad, "basarili": False, "hata": neden})
            vt.kayit_dus(b, kullanici, "Yedek alınamadı", f"{TUR_ADI[tur]} · {neden}", ip)
        raise YedekHatasi(f"Yedek alınamadı: {neden}") from hata
    kopya_hata = ""
    kopya_dizini = str(ayar_.get("kopya_dizini") or "")
    if kopya_dizini:
        try:
            klasor = Path(kopya_dizini)
            _atomik_yaz(klasor / ad, veri)
            dondur(klasor, int(ayar_["saklama"]), zaman)
        except OSError as hata:
            kopya_hata = f"{type(hata).__name__}: {hata}"[:300]
    dondur(dizin(), int(ayar_["saklama"]), zaman)
    with vt.islem() as b:
        vt.ayar_yaz(
            b, "son_yedek",
            {"zaman": zaman, "dosya": ad, "basarili": True, "hata": "", "kopya_hata": kopya_hata,
             "son_basarili": zaman, "son_basarili_dosya": ad},
        )  # fmt: skip
        ayrinti = f"{TUR_ADI[tur]} · {ad} · {len(veri)} bayt"
        if kopya_hata:
            ayrinti += f" · ikinci kopya yazılamadı: {kopya_hata}"
        vt.kayit_dus(b, kullanici, "Yedek alındı", ayrinti, ip)
    return {"dosya": ad, "yeni": True, "boyut": len(veri), "kopya_hata": kopya_hata}


def listele() -> list[dict]:
    """Yedek klasöründeki yedekler, yeniden eskiye (ad sırası belirlenimlidir)."""
    sonuc = []
    for yol in dizin().glob("tahta-kontrol-*.tkyedek"):
        eslesme = AD_DESENI.match(yol.name)
        if not eslesme:
            continue
        tur, yil, ay, gun, saat = eslesme.groups()
        tarih = f"{gun}.{ay}.{yil}" + (f" {saat[:2]}:{saat[2:4]}:{saat[4:]}" if saat else "")
        try:
            boyut = yol.stat().st_size
        except OSError:
            continue
        sonuc.append({"ad": yol.name, "tur": tur, "tur_adi": TUR_ADI[tur], "tarih": tarih, "boyut": boyut,
                      "boyut_metni": boyut_metni(boyut), "sira": f"{yil}{ay}{gun}{saat or '999999'}"})  # fmt: skip
    return sorted(sonuc, key=lambda y: (y["sira"], y["ad"]), reverse=True)


def boyut_metni(bayt: int) -> str:
    if bayt < 1024 * 1024:
        return f"{max(1, round(bayt / 1024))} KB"
    return f"{bayt / (1024 * 1024):.1f} MB".replace(".", ",")


def indirilecek_yol(ad: str) -> Path | None:
    """Ad desene uyuyor ve dosya yedek klasörünün içindeyse yol; yoksa None."""
    if not AD_DESENI.match(ad or ""):
        return None
    kok = dizin().resolve()
    yol = (kok / ad).resolve()
    if yol.parent != kok or not yol.is_file():
        return None
    return yol


def otomatik_gerekli_mi(b, acilis: int, simdi: int | None = None) -> bool:
    """Parola var, program ≥ 5 dk açık, bugünün günlüğü yok, son başarısız deneme 30 dk'dan eski."""
    zaman = vt.simdi() if simdi is None else int(simdi)
    if not ayarlar(b)["parola_var"] or zaman - acilis < OTOMATIK_GECIKME_SN:
        return False
    if (dizin() / gunluk_adi(_an(zaman))).exists():
        return False
    son = son_yedek(b)
    if son and not son.get("basarili") and zaman - int(son.get("zaman") or 0) < OTOMATIK_YENIDEN_SN:
        return False
    return True


def bugunun_gunlugu_var(simdi: int | None = None) -> bool:
    return (dizin() / gunluk_adi(_an(simdi))).exists()


def kopya_dizini_dogrula(metin: str) -> str:
    """Boş ya da mutlak yol; doluysa klasöre deneme dosyası yazıp siler. Hata: YedekHatasi."""
    yol = str(metin or "").strip().strip('"')
    if not yol:
        return ""
    if len(yol) > 260 or not (PureWindowsPath(yol).is_absolute() or Path(yol).is_absolute()):
        raise YedekHatasi("İkinci kopya klasörü tam yol olmalı (ör. D:\\TahtaYedek).")
    klasor = Path(yol)
    try:
        if klasor.resolve() == dizin().resolve():
            raise YedekHatasi("İkinci kopya klasörü yedek klasörünün kendisi olamaz.")
        if not klasor.is_dir():
            raise YedekHatasi("İkinci kopya klasörü bulunamadı. Klasörü oluşturup yeniden deneyin.")
        deneme = klasor / YAZMA_DENEMESI
        deneme.write_bytes(b"tahta-kontrol")
        deneme.unlink()
    except OSError as hata:
        raise YedekHatasi(
            "İkinci kopya klasörüne yazılamadı. Yönetici olarak açılmış komut isteminde şu komutu çalıştırıp "
            f"yeniden deneyin: {izin_komutu(yol)}"
        ) from hata
    return yol


# ---- geri yükleme ----------------------------------------------------------------------
def _bekleyen_json() -> Path:
    return bekleyen_dizini() / "bekleyen.json"


def bekleyen_oku() -> dict | None:
    try:
        veri = json.loads(_bekleyen_json().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return veri if isinstance(veri, dict) else None


def bekleyeni_sil() -> None:
    hedef = bekleyen_dizini()
    shutil.rmtree(hedef / "bekleyen", ignore_errors=True)
    try:
        _bekleyen_json().unlink()
    except OSError:
        pass


def kalintilari_temizle(saklama: int = SAKLAMA_VARSAYILAN, simdi: int | None = None) -> list[str]:
    """Geri yükleme kalıntılarını budar (KVKK: şifresiz kopyalar süresiz durmasın).

    - Onaylanmamış bekleyen geri yükleme (çözülmüş veritabanı ve sunucu anahtarı) 24 saatten eskiyse
      ya da önizlemesi yoksa silinir. Onaylanmış olan, program yeniden açılınca uygulanacağı için kalır.
    - `geri-yukleme-oncesi/` altında yalnız en yeni klasör tutulur; o da `saklama` günden eskiyse silinir.
    Kilit doluysa (yedek ya da geri yükleme sürüyor) hiçbir şey yapılmaz. Silinenlerin göreli adları döner.
    """
    zaman = vt.simdi() if simdi is None else int(simdi)
    silinen: list[str] = []
    if not vt.KILIT.acquire(timeout=0):
        return silinen
    try:
        bekleyen_klasor = bekleyen_dizini() / "bekleyen"
        bekleyen = bekleyen_oku()
        if bekleyen_klasor.exists() or bekleyen is not None:
            eski = not bekleyen or (
                not bekleyen.get("onaylandi") and zaman - int(bekleyen.get("hazirlama") or 0) > BEKLEYEN_OMRU_SN
            )
            if eski:
                bekleyeni_sil()
                silinen.append("geri-yukleme/bekleyen")
        kok = ayar.veri_dizini() / "geri-yukleme-oncesi"
        if kok.is_dir():
            klasorler = []
            for alt in kok.iterdir():
                if not alt.is_dir():
                    continue
                try:
                    an = datetime.strptime(alt.name, "%d.%m.%Y-%H%M%S").replace(tzinfo=ISTANBUL)
                    zamani = int(an.timestamp())
                except ValueError:
                    zamani = int(alt.stat().st_mtime)
                klasorler.append((zamani, alt))
            klasorler.sort(key=lambda k: (k[0], k[1].name), reverse=True)
            for i, (zamani, alt) in enumerate(klasorler):
                if i > 0 or zaman - zamani > max(1, int(saklama)) * 86400:
                    shutil.rmtree(alt, ignore_errors=True)
                    silinen.append(f"geri-yukleme-oncesi/{alt.name}")
    finally:
        vt.KILIT.release()
    return silinen


def _json_yaz(yol: Path, veri: dict) -> None:
    _atomik_yaz(yol, json.dumps(veri, ensure_ascii=False, indent=1).encode("utf-8"))


def bekleyeni_hazirla(veri: bytes, parola: str, simdi_parmak_izi: str = "") -> dict:
    """Yedeği çözüp doğrular; geçerse çözülen dosyaları bekletir ve önizlemeyi döndürür.

    Hata (parola, bozuk dosya…) YedekHatasi; o durumda hiçbir dosya yazılmaz.
    """
    if len(veri) > DOSYA_EN_BUYUK:
        raise YedekHatasi("Yedek dosyası en çok 200 MB olabilir.")
    if not vt.KILIT.acquire(timeout=30):
        raise YedekMesgul("Başka bir yedek ya da geri yükleme sürüyor; biraz sonra yeniden deneyin.")
    try:
        bilgi, dosyalar = coz(veri, parola)
        bekleyeni_sil()
        klasor = bekleyen_dizini() / "bekleyen"
        klasor.mkdir(parents=True, exist_ok=True)
        for ad in (VT_ADI, SERTIFIKA_ADI, ANAHTAR_ADI):
            _atomik_yaz(klasor / ad, dosyalar[ad])
        onizleme = {
            "bicim": 1,
            "yedek_olusturma": int(bilgi.get("olusturma") or 0),
            "surum": str(bilgi.get("surum") or ""),
            "sema": int(bilgi.get("sema") or 0),
            "okul_adi": str(bilgi.get("okul_adi") or ""),
            "tahta_sayisi": int(bilgi.get("tahta_sayisi") or 0),
            "kullanici_sayisi": int(bilgi.get("kullanici_sayisi") or 0),
            "parmak_izi": bilgi["parmak_izi"],
            "simdiki_parmak_izi": simdi_parmak_izi,
            "dosya_boyutu": len(veri),
            "hazirlama": vt.simdi(),
            "onaylandi": False,
            "hata": "",
        }
        _json_yaz(_bekleyen_json(), onizleme)
        return onizleme
    finally:
        vt.KILIT.release()


def bekleyeni_onayla() -> dict | None:
    bekleyen = bekleyen_oku()
    if not bekleyen or not (bekleyen_dizini() / "bekleyen" / VT_ADI).exists():
        return None
    bekleyen.update(onaylandi=True, onay_zamani=vt.simdi(), hata="")
    _json_yaz(_bekleyen_json(), bekleyen)
    return bekleyen


def bekleyeni_uygula(veri_dizini: Path | None = None) -> str | None:
    """Açılışta (vt.hazirla ve sertifika hazırlığından ÖNCE) onaylı bekleyen geri yüklemeyi uygular.

    Mevcut veritabanı (-wal/-shm dahil) ve sertifika `geri-yukleme-oncesi/<an>/`'a TAŞINIR,
    yedektekiler yerleştirilir, oturumlar silinir, işlem kaydına not düşülür. Herhangi bir
    adımda hata: taşınanlar geri konur, `bekleyen.json`'a hata yazılır (onay kalkar), açılış sürer.
    Uygulandıysa ileti, uygulanacak bir şey yoksa ya da hata olduysa None.
    """
    d = Path(veri_dizini) if veri_dizini else ayar.veri_dizini()
    json_yolu = d / "geri-yukleme" / "bekleyen.json"
    try:
        bekleyen = json.loads(json_yolu.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(bekleyen, dict) or not bekleyen.get("onaylandi"):
        return None
    kaynak = d / "geri-yukleme" / "bekleyen"
    an = datetime.now(ISTANBUL).strftime("%d.%m.%Y-%H%M%S")
    onceki = d / "geri-yukleme-oncesi" / an
    tasinan: list[str] = []
    yerlesen: list[str] = []
    with vt.KILIT:
        try:
            for ad in (VT_ADI, SERTIFIKA_ADI, ANAHTAR_ADI):
                if not (kaynak / ad).is_file():
                    raise FileNotFoundError(f"bekleyen dosya yok: {ad}")
            onceki.mkdir(parents=True, exist_ok=True)
            for ad in (VT_ADI, VT_ADI + "-wal", VT_ADI + "-shm", SERTIFIKA_ADI, ANAHTAR_ADI):
                if (d / ad).exists():
                    os.replace(d / ad, onceki / ad)
                    tasinan.append(ad)
            for ad in (VT_ADI, SERTIFIKA_ADI, ANAHTAR_ADI):
                shutil.copyfile(kaynak / ad, d / ad)
                yerlesen.append(ad)
            tarih = datetime.fromtimestamp(int(bekleyen.get("yedek_olusturma") or 0), ISTANBUL).strftime("%d.%m.%Y %H:%M")
            baglanti = sqlite3.connect(d / VT_ADI)
            try:
                baglanti.execute("DELETE FROM oturum")  # yedekteki oturumlar geçersiz (çerezler tutmasın)
                baglanti.execute(
                    "INSERT INTO kayit (zaman, kullanici, islem, ayrinti, ip) VALUES (?, 'sistem', ?, ?, '')",
                    (vt.simdi(), "Yedekten geri yüklendi", f"yedek tarihi {tarih}; önceki dosyalar geri-yukleme-oncesi/{an}"),
                )
                baglanti.commit()
            finally:
                baglanti.close()
        except Exception as hata:  # her hatada eski düzen geri kurulur
            for ad in yerlesen:
                try:
                    (d / ad).unlink()
                except OSError:
                    pass
            for ad in tasinan:
                try:
                    os.replace(onceki / ad, d / ad)
                except OSError:
                    gunluk.exception("Geri yükleme geri alınırken %s yerine konamadı", ad)
            bekleyen.update(onaylandi=False, hata=f"{type(hata).__name__}: {hata}"[:300])
            try:
                _json_yaz(json_yolu, bekleyen)
            except OSError:
                pass
            gunluk.error("Geri yükleme uygulanamadı: %s", hata)
            return None
        shutil.rmtree(kaynak, ignore_errors=True)
        try:
            json_yolu.unlink()
        except OSError:
            pass
    gunluk.info("Yedekten geri yüklendi (yedek tarihi %s).", tarih)
    return f"Yedekten geri yüklendi (yedek tarihi {tarih})."
