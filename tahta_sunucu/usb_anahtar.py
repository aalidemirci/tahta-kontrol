"""USB anahtar (0.11.0): iş mantığı (FastAPI'siz; testle sınanır).

Anahtar, belleğin kök dizinindeki tek küçük metin dosyasıdır (`tahta-kontrol.anahtar`). Dosyada kişi
verisi YOKTUR: yalnız kimlik (gizli değil), sunucu parmak izinin ilk 16 hanesi ve 32 baytlık gizli değer.
Sunucu gizlinin yalnız SHA-256 özetini saklar; gizli değer sunucudan yalnız bir kez, dosya olarak çıkar
(`Bekleyen` → indirme). Tahtada dosyayı yalnız kök yetkili servis okur (kural 5).

Kapsam dardır: ders yoklaması ve (ayar açıksa) kilit açma. Panel oturumu açmaz, ayar değiştirmez, komut
vermez, sınav penceresinde hiçbir şey yapmaz.

0.21.0 — sınıf başkanı anahtarı (`sahip_turu='sube'`): anahtar KİŞİYE değil ŞUBEYE bağlıdır; sistemde başkanın adı
tutulmaz. Yalnız kendi şubesinin, o şubenin dersliğindeki tahtada, şu anki dersinin yoklamasını alır; hiçbir zaman
kilit açmaz; o ders saatinde öğretmen/idare/panel kaydı varsa yazamaz (öğretmen önceliği). Ayrı ayarla (`baskan`,
varsayılan kapalı) açılır; ders yoklaması kapalıyken çalışmaz. Kayıt `yoklama.kaynak='baskan'` olarak yazılır. Her işlem (yoklama, kilit açma) ve reddedilen her deneme işlem
kaydına anahtar kimliği ve sahip koduyla (öğretmen kodu ya da panel kullanıcı adı) düşer; kişi adı yazılmaz.
Kendiliğinden yapılan başarılı tanıma kayda düşmez (yalnız son kullanım tutulur, §7).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import io
import secrets
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import guvenlik, metin, vt
from . import yoklama as yk

ISTANBUL = ZoneInfo("Europe/Istanbul")
YETENEK = "usb_anahtar"
AYAR_ANAHTARI = "usb_anahtar"
VARSAYILAN_AYAR = {"etkin": False, "kilit_acar": True, "pin_idare": True, "pin_ogretmen": False, "baskan": False,
                   "pin_baskan": True}  # fmt: skip

DOSYA_ADI = "tahta-kontrol.anahtar"
BASLIK = "TAHTA-KONTROL-ANAHTAR"
DOSYA_SURUMU = "1"
DOSYA_EN_BUYUK = 1024
KIMLIK_ALFABESI = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # karışan I, L, O, 0, 1 yok
KIMLIK_UZUNLUGU = 8
SUNUCU_UZUNLUGU = 16
GIZLI_UZUNLUGU = 52  # 32 bayt, base32, dolgusuz
_BASE32 = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")

KISI_BASI_EN_COK = 2
SUBE_BASI_EN_COK = 2        # 0.21.0: şube başına etkin sınıf başkanı anahtarı (başkan + yardımcısı)
TOPLU_EN_COK = 80           # bir toplu üretimde en çok şube
TANI_OMRU_SN = 600          # tahta, tanınan anahtarı en çok bu kadar tutar (ajan da aynı değeri kullanır)
KOPYA_PENCERE_SN = 60
KOPYA_ROZET_SN = 7 * 86400  # listede "kopyalanmış olabilir" rozeti
GOVDE_SINIRI = 4096
GECERSIZ_ADET, GECERSIZ_PENCERE_SN, GECERSIZ_KAPALI_SN = 5, 600, 600
ISTEK_ADET, ISTEK_PENCERE_SN = 60, 600
BEKLEYEN_OMRU_SN = 300      # üretilen anahtarın indirilme süresi
ETIKET_EN_UZUN = 30
PIN_HATA_ADET, PIN_PENCERE_SN = yk.OGRETMEN_HATA_ADET, yk.OGRETMEN_PENCERE_SN  # 24 saatte 10 hata → kilit

ILETI_KAPALI = "USB anahtar bu okulda kullanılmıyor."
ILETI_SINAV = "Sınav sürüyor; USB anahtar kullanılamaz."
ILETI_GECERSIZ = "Bu USB anahtar geçerli değil."
ILETI_IPTAL = "Bu USB anahtar iptal edilmiş. Okul idaresine başvurun."
ILETI_KILITLI = "Bu USB anahtar çok sayıda hatalı PIN nedeniyle kilitlendi. Okul idaresine başvurun."
ILETI_OGRETMEN_PIN_KILITLI = "PIN'iniz kilitli. Okul idaresine başvurun."
ILETI_TAHTA_KAPALI = "Bu tahtada çok fazla geçersiz anahtar denendi. 10 dakika bekleyin."
ILETI_COK_ISTEK = "Bu tahtadan çok fazla USB anahtar isteği geldi. Biraz bekleyin."
ILETI_PIN_GEREK = "PIN'inizi girin."
ILETI_PIN_HATALI = "PIN hatalı."
ILETI_KILIT_KAPALI = "USB anahtarla kilit açma bu okulda kapalı."
ILETI_SINIR = f"Bu kişinin {KISI_BASI_EN_COK} etkin anahtarı var. Önce birini iptal edin."
ILETI_INDIRME_YOK = "Bu indirme bağlantısı kullanıldı ya da süresi doldu; yeni anahtar üretin."
# Etiket yalnız panelde görünür (tahtaya inmez): genel "Tahta herkese açık ekrandır" iletisi yanıltırdı.
ILETI_ETIKET_TC = "Etikette T.C. kimlik numarasına benzeyen bir sayı var; kişi bilgisi yazmayın."
ILETI_KAPALI_PANEL = "USB anahtar Ayarlar'da kapalı; üretilen anahtarlar tahtalarda çalışmaz."
# 0.21.0 — sınıf başkanı anahtarı
ILETI_BASKAN_KAPALI = "Sınıf başkanı anahtarları şu an kapalı."
ILETI_BASKAN_KILIT = "Sınıf başkanı anahtarı kilit açmaz."
ILETI_BASKAN_KAPALI_PANEL = "Sınıf başkanı anahtarları Ayarlar'da kapalı; üretilen anahtarlar tahtalarda çalışmaz."
BASKAN_NOTU = "Sınıf başkanı kaydı deneme amaçlı yardımcı kayıttır; öğretmenin yoklamasının yerine geçmez."

DURUM_ADI = {"etkin": "Etkin", "kilitli": "PIN kilitli", "iptal": "İptal"}
TUR_ADI = {"idare": "idare", "ogretmen": "öğretmen", "baskan": "sınıf başkanı"}


# ---- ayar --------------------------------------------------------------------------------------
def ayar_al(b) -> dict:
    deger = vt.ayar_al(b, AYAR_ANAHTARI)
    sonuc = dict(VARSAYILAN_AYAR)
    if isinstance(deger, dict):
        sonuc.update({k: v for k, v in deger.items() if k in VARSAYILAN_AYAR and isinstance(v, bool)})
    return sonuc


def ayar_coz(form) -> dict:
    """Ayarlar › USB anahtar formu (bolum=usb_anahtar): ua_etkin, ua_kilit_acar, ua_pin_idare, ua_pin_ogretmen, ua_baskan,
    ua_pin_baskan (=1). Altı kutu da AYNI formdadır: işaretsiz kutu gönderilmez, eksik alan "kapalı" sayılır."""
    return {anahtar: form.get(f"ua_{anahtar}") == "1" for anahtar in VARSAYILAN_AYAR}


def ayar_ozeti(a: dict) -> str:
    """İşlem kaydı: "açık · kilit açar · PIN: idare" / "kapalı · PIN: yok"; başkan anahtarları açıksa
    "açık · kilit açar · sınıf başkanı · PIN: idare, başkan"."""
    pinler = [ad for ad, alan in (("idare", "pin_idare"), ("öğretmen", "pin_ogretmen")) if a[alan]]
    if a["baskan"] and a["pin_baskan"]:
        pinler.append("başkan")
    parca = ["açık" if a["etkin"] else "kapalı"]
    if a["kilit_acar"]:
        parca.append("kilit açar")
    if a["baskan"]:
        parca.append("sınıf başkanı")
    parca.append("PIN: " + (", ".join(pinler) if pinler else "yok"))
    return " · ".join(parca)


def ajan_gorunumu(b) -> dict:
    """`ayar.usb_anahtar`: tahtaya YALNIZ açık/kapalı iner (anahtar listesi, özet, PIN ayarı inmez)."""
    return {"etkin": ayar_al(b)["etkin"]}


def baskan_acik(a: dict) -> bool:
    """Sınıf başkanı anahtarları çalışıyor mu (USB anahtar ve başkan ayarı birlikte açık)? Ders yoklaması ayrıca gerekir."""
    return bool(a["etkin"] and a["baskan"])


def izinler(b, a: dict | None = None, satir=None) -> list[str]:
    """Tahtaya inen izinler. Şube (sınıf başkanı) anahtarı hiçbir zaman `kilit_ac` almaz."""
    a = a or ayar_al(b)
    sonuc = []
    if yk.etkin(b):
        sonuc.append("yoklama")
    if a["kilit_acar"] and not (satir is not None and satir["sahip_turu"] == "sube"):
        sonuc.append("kilit_ac")
    return sonuc


def yetenekli(tahta) -> bool:
    from . import acil

    return YETENEK in acil.yetenekler(tahta)


# ---- kimlik, gizli, dosya ------------------------------------------------------------------------
def kimlik_bicimli(kimlik: str) -> str:
    """'K7Q2M9XA' → 'K7Q2-M9XA' (panel ve işlem kaydı)."""
    return f"{kimlik[:4]}-{kimlik[4:]}" if len(kimlik) == KIMLIK_UZUNLUGU else kimlik


def kimlik_duzelt(deger) -> str | None:
    """Gelen kimlik: büyük harf, '-' ve boşluk atılır; biçimsizse None."""
    if not isinstance(deger, str) or len(deger) > 20:
        return None
    s = deger.strip().replace("-", "").replace(" ", "").upper()
    if len(s) != KIMLIK_UZUNLUGU or any(c not in KIMLIK_ALFABESI for c in s):
        return None
    return s


def gizli_duzelt(deger) -> str | None:
    """Gelen gizli: büyük harfe çevrilir; 52 karakter base32 ve 32 bayta çözülmüyorsa None."""
    if not isinstance(deger, str) or len(deger) > 100:
        return None
    s = deger.strip().upper()
    if len(s) != GIZLI_UZUNLUGU or any(c not in _BASE32 for c in s):
        return None
    try:
        if len(base64.b32decode(s + "====")) != 32:
            return None
    except ValueError:
        return None
    return s


def gizli_ozeti(gizli: str) -> str:
    return hashlib.sha256(gizli.upper().encode("ascii")).hexdigest()


def gizli_uret() -> str:
    return base64.b32encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


def kimlik_uret(b, ayrica: set[str] | None = None) -> str:
    kullanilan = {s["kimlik"] for s in b.execute("SELECT kimlik FROM usb_anahtar")} | (ayrica or set())
    while True:
        aday = "".join(secrets.choice(KIMLIK_ALFABESI) for _ in range(KIMLIK_UZUNLUGU))
        if aday not in kullanilan:
            return aday


def sunucu_kisa(parmak_izi: str) -> str:
    return str(parmak_izi or "").lower()[:SUNUCU_UZUNLUGU]


@dataclass
class Bekleyen:
    """Üretilmiş ama henüz indirilmemiş anahtar (yalnız sunucu belleğinde, en çok 5 dk).

    PIN'in düz hâli burada TUTULMAZ (yalnız özeti); düz PIN yalnız üretim yanıtında bir kez görünür.
    """

    kimlik: str
    gizli: str
    sahip_turu: str
    kullanici_id: int | None
    ogretmen_id: int | None
    etiket: str
    olusturan: str
    olusturan_id: int
    sunucu: str
    pin_ozet: str | None
    bitis: int
    sahip_kodu: str
    sube: str | None = None  # 0.21.0: yalnız şube (sınıf başkanı) anahtarında


@dataclass
class BekleyenPaket:
    """0.21.0: toplu üretilen sınıf başkanı anahtarları; tek belirteçle, tek seferde (zip) indirilir."""

    anahtarlar: list[Bekleyen]
    olusturan_id: int
    bitis: int


def dosya_metni(bekleyen: Bekleyen) -> bytes:
    """§1.2 biçimi (ASCII, LF). Kişi adı, kullanıcı adı, okul adı, öğretmen kodu YOK."""
    satirlar = [
        "# Tahta Kontrol USB anahtari. Bu dosyayi kimseyle paylasmayin.",
        "# Kaybederseniz okul idaresine bildirin; anahtar panelden iptal edilir.",
        BASLIK,
        f"surum={DOSYA_SURUMU}",
        f"kimlik={bekleyen.kimlik}",
        f"sunucu={bekleyen.sunucu}",
        f"gizli={bekleyen.gizli}",
    ]
    return ("\n".join(satirlar) + "\n").encode("ascii")


PAKET_ADI = "tahta-kontrol-baskan-anahtarlari.zip"
PAKET_OKUBENI = (
    "Tahta Kontrol - sinif baskani USB anahtarlari\n\n"
    "Her klasor bir subenindir (ornek: 10-A = 10/A). Klasordeki tahta-kontrol.anahtar dosyasini o subenin\n"
    "bellegine, bellegin EN UST klasorune, adini degistirmeden kopyalayin. Bellekteki diger dosyalar kalir.\n"
    "PIN'ler yalniz uretim sayfasindaki pusulada yazar. Kopyalamadan sonra bu zip dosyasini ve acilmis\n"
    "klasorleri bilgisayardan silin (Indirilenler ve cop kutusu). Kaybolan bellek panelden iptal edilir.\n"
)


def klasor_adi(sube: str) -> str:
    """Zip içindeki şube klasörü: "10/A" → "10-A", "Hazırlık/B" → "Hazırlık-B" (harf, rakam ve '-' dışındakiler '-')."""
    ad = "".join(c if c.isalnum() else "-" for c in str(sube or "").replace("/", "-")).strip("-")
    return ad or "sube"


def paket_klasorleri(anahtarlar: list) -> list[str]:
    """Her anahtarın klasörü (aynı adı alan iki şube olursa ikincisine "-2" eklenir; aynı şubenin ikinci anahtarı da)."""
    sonuc: list[str] = []
    for a in anahtarlar:
        aday = klasor_adi(a.sube)
        ad, n = aday, 1
        while ad in sonuc:
            n += 1
            ad = f"{aday}-{n}"
        sonuc.append(ad)
    return sonuc


def paket_zip(anahtarlar: list, an: int) -> bytes:
    """Toplu başkan anahtarlarının tek seferlik zip'i: "<klasör>/tahta-kontrol.anahtar" + OKUBENI.txt (kişi verisi YOK)."""
    zaman = datetime.fromtimestamp(int(an), ISTANBUL).timetuple()[:6]
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo("OKUBENI.txt", date_time=zaman), PAKET_OKUBENI.encode("ascii"))
        for anahtar, klasor in zip(anahtarlar, paket_klasorleri(anahtarlar), strict=True):
            z.writestr(zipfile.ZipInfo(f"{klasor}/{DOSYA_ADI}", date_time=zaman), dosya_metni(anahtar))
    return tampon.getvalue()


class DosyaHatasi(ValueError):
    """`neden`: 'boyut' | 'ascii' | 'baslik' | 'bicim' | 'surum' (tanılama sayacı için; yol/içerik taşımaz)."""

    def __init__(self, neden: str):
        super().__init__(neden)
        self.neden = neden


def dosya_coz(veri) -> dict:
    """Anahtar dosyasını katı kurallarla ayrıştırır: {"surum","kimlik","sunucu","gizli"} ya da DosyaHatasi.

    Ajandaki `tahta_ajan/usb_anahtar.dosya_coz` ile AYNI kurallar (test ikisini karşılaştırır):
    en çok 1024 bayt; ASCII dışı bayt → red; `#` ile başlayan ve boş satırlar yok sayılır; ilk anlamlı
    satır BASLIK olmalı; sonra `alan=değer` satırları (alan ve değerin iki yanındaki boşluk kırpılır);
    aynı alan iki kez → red; bilinmeyen sürüm → 'surum'; sürüm 1'de alan kümesi tam olarak
    {surum, kimlik, sunucu, gizli}; kimlik/gizli büyük harfe, sunucu küçük harfe çevrilip uzunluk ve
    alfabesi tam denetlenir.
    """
    if isinstance(veri, str):
        try:
            veri = veri.encode("ascii")
        except UnicodeEncodeError:
            raise DosyaHatasi("ascii") from None
    if not isinstance(veri, (bytes, bytearray)) or len(veri) > DOSYA_EN_BUYUK:
        raise DosyaHatasi("boyut")
    if any(c > 0x7F for c in veri):
        raise DosyaHatasi("ascii")
    satirlar = [s.strip() for s in bytes(veri).decode("ascii").replace("\r\n", "\n").split("\n")]
    anlamli = [s for s in satirlar if s and not s.startswith("#")]
    if not anlamli or anlamli[0] != BASLIK:
        raise DosyaHatasi("baslik")
    alanlar: dict[str, str] = {}
    for satir in anlamli[1:]:
        alan, esit, deger = satir.partition("=")
        alan, deger = alan.strip(), deger.strip()
        if not esit or not alan or alan in alanlar:
            raise DosyaHatasi("bicim")
        alanlar[alan] = deger
    if alanlar.get("surum") != DOSYA_SURUMU:
        raise DosyaHatasi("surum" if "surum" in alanlar else "bicim")
    if set(alanlar) != {"surum", "kimlik", "sunucu", "gizli"}:
        raise DosyaHatasi("bicim")
    kimlik = alanlar["kimlik"].upper()
    sunucu = alanlar["sunucu"].lower()
    gizli = alanlar["gizli"].upper()
    if len(kimlik) != KIMLIK_UZUNLUGU or any(c not in KIMLIK_ALFABESI for c in kimlik):
        raise DosyaHatasi("bicim")
    if len(sunucu) != SUNUCU_UZUNLUGU or any(c not in "0123456789abcdef" for c in sunucu):
        raise DosyaHatasi("bicim")
    if gizli_duzelt(gizli) is None:
        raise DosyaHatasi("bicim")
    return {"surum": 1, "kimlik": kimlik, "sunucu": sunucu, "gizli": gizli}


# ---- etiket ve sahip ---------------------------------------------------------------------------------
def etiket_coz(ham) -> str:
    etiket = " ".join(str(ham or "").split())
    if len(etiket) > ETIKET_EN_UZUN:
        raise ValueError(f"Etiket en çok {ETIKET_EN_UZUN} karakter olabilir.")
    if guvenlik.tc_kimlik_var(etiket):
        raise ValueError(ILETI_ETIKET_TC)
    return etiket


def idare_etiketi(gorunen_ad: str, kullanici_adi: str = "") -> str:
    """Panel kullanıcısının görünen adından tahtadaki kısa ad: "Ali Demir" → "İdare · A. Demir".

    Tahta herkese açık ekrandır: panel KULLANICI ADI tahtaya inmez (§3.2). Görünen ad boş bırakılınca
    kullanıcı adıyla doldurulur; bu yüzden görünen ad boşsa, kullanıcı adına eşitse ya da tek kelimeyse
    (ad soyad değilse) etiket yalnız "İdare" olur.
    """
    parcalar = str(gorunen_ad or "").split()
    ayni = " ".join(parcalar).casefold() == " ".join(str(kullanici_adi or "").split()).casefold()
    if len(parcalar) < 2 or ayni:
        return "İdare"
    return f"İdare · {yk.ogretmen_etiketi(' '.join(parcalar[:-1]), parcalar[-1])}"


def _sahip_satiri(b, satir):
    """Anahtarın sahibi: öğretmen ({aktif, ad, soyad, kod, kilitli, pin_ozet}), kullanıcı ({aktif, rol, ad, gorunen_ad})
    ya da şube ({sube, aktif}: aktif = şubede etkin öğrenci var; kişi verisi YOK)."""
    if satir["sahip_turu"] == "sube":
        var = b.execute("SELECT 1 FROM ogrenci WHERE sube = ? AND aktif = 1 LIMIT 1", (satir["sube"],)).fetchone()
        return {"sube": satir["sube"], "aktif": bool(var)}
    if satir["sahip_turu"] == "ogretmen":
        return b.execute(
            "SELECT o.id, o.ad, o.soyad, o.aktif, p.kod, p.kilitli, p.pin_ozet FROM ogretmen o "
            "JOIN ogretmen_pin p ON p.ogretmen_id = o.id WHERE o.id = ?",
            (satir["ogretmen_id"],),
        ).fetchone()
    return b.execute("SELECT id, ad, gorunen_ad, rol, aktif FROM kullanici WHERE id = ?", (satir["kullanici_id"],)).fetchone()


def sahip_kodu(b, satir, sahip=None) -> str:
    """İşlem kaydındaki sahip: "öğretmen kodu 112", "kullanıcı mdryrd" ya da "şube 10/A (başkan)" (ad soyad YAZILMAZ)."""
    if satir["sahip_turu"] == "sube":
        return f"şube {satir['sube']} (başkan)"
    sahip = sahip or _sahip_satiri(b, satir)
    if satir["sahip_turu"] == "ogretmen":
        return f"öğretmen kodu {sahip['kod'] if sahip else '?'}"
    return f"kullanıcı {sahip['ad'] if sahip else '?'}"


def kayit_ayrintisi(b, satir, sahip=None) -> str:
    return f"{kimlik_bicimli(satir['kimlik'])} · {sahip_kodu(b, satir, sahip)}"


def gorunum(b, satir, sahip=None) -> dict:
    """Tahtaya inen anahtar görünümü: {"tur": "idare"|"ogretmen"|"baskan", "etiket", "kod"} (kimlik, id, tam ad YOK).

    Şube anahtarında etiket yalnız "Sınıf başkanı · 10/A"dır (öğrenci adı tutulmaz; panel etiketi tahtaya inmez).
    Eski ajan bilinmeyen türü "öğretmen" sayar; kod boş olduğu için yalnız etiketi gösterir."""
    if satir["sahip_turu"] == "sube":
        return {"tur": "baskan", "etiket": f"Sınıf başkanı · {satir['sube']}", "kod": ""}
    sahip = sahip or _sahip_satiri(b, satir)
    if satir["sahip_turu"] == "ogretmen":
        return {"tur": "ogretmen", "etiket": yk.ogretmen_etiketi(sahip["ad"], sahip["soyad"]), "kod": sahip["kod"]}
    return {"tur": "idare", "etiket": idare_etiketi(sahip["gorunen_ad"], sahip["ad"]), "kod": ""}


def pin_gerek(satir, a: dict) -> bool:
    alan = {"kullanici": "pin_idare", "sube": "pin_baskan"}.get(satir["sahip_turu"], "pin_ogretmen")
    return bool(a[alan])


# ---- üretim ------------------------------------------------------------------------------------------
def etkin_sayisi(b, *, kullanici_id: int | None = None, ogretmen_id: int | None = None, sube: str | None = None) -> int:
    if sube is not None:
        return b.execute("SELECT COUNT(*) FROM usb_anahtar WHERE sahip_turu = 'sube' AND sube = ? AND durum != 'iptal'",
                         (sube,)).fetchone()[0]  # fmt: skip
    if kullanici_id is not None:
        return b.execute("SELECT COUNT(*) FROM usb_anahtar WHERE kullanici_id = ? AND durum != 'iptal'", (kullanici_id,)).fetchone()[0]
    return b.execute("SELECT COUNT(*) FROM usb_anahtar WHERE ogretmen_id = ? AND durum != 'iptal'", (ogretmen_id,)).fetchone()[0]


def sinir_iletisi(sube: str) -> str:
    return f"{sube} şubesinin {SUBE_BASI_EN_COK} etkin başkan anahtarı var. Önce birini iptal edin."


def uret(
    b, *, sahip_turu: str, kullanici_id: int | None, ogretmen_id: int | None, etiket: str, olusturan: str,
    olusturan_id: int, parmak_izi: str, an: int, bekleyen_kimlikler: set[str] | None = None, sube: str | None = None,
    bekleyen_sayisi: int = 0,
) -> tuple[Bekleyen, str | None]:  # fmt: skip
    """Bekleyen anahtar + (kullanıcı ve şube anahtarında) düz PIN. Satırı YAZMAZ (§4.3: indirme anında `kaydet`).

    Sahip denetimi: öğretmen etkin ve kodlu olmalı; kullanıcı etkin olmalı; kişi başı en çok 2 etkin. Şube
    (0.21.0): öğrenci listesinde etkin şube olmalı; şube başı en çok 2 etkin (`bekleyen_sayisi` = aynı şube için
    henüz indirilmemiş anahtarlar, sınır üretimde de denetlensin diye).
    """
    etiket = etiket_coz(etiket)
    if sahip_turu == "sube":
        sube = metin.sube_duzelt(sube or "")
        if not sube or sube not in yk.aktif_subeler(b):
            raise ValueError("Şube öğrenci listesinde yok.")
        kullanici_id = ogretmen_id = None
        kod = f"şube {sube} (başkan)"
        if etkin_sayisi(b, sube=sube) + bekleyen_sayisi >= SUBE_BASI_EN_COK:
            raise ValueError(sinir_iletisi(sube))
    elif sahip_turu == "ogretmen":
        sahip = b.execute(
            "SELECT o.id, o.aktif, p.kod FROM ogretmen o JOIN ogretmen_pin p ON p.ogretmen_id = o.id WHERE o.id = ?", (ogretmen_id,)
        ).fetchone()
        if not sahip or not sahip["aktif"]:
            raise ValueError("Öğretmen bulunamadı ya da pasif.")
        kullanici_id, kod = None, f"öğretmen kodu {sahip['kod']}"
        if etkin_sayisi(b, ogretmen_id=ogretmen_id) >= KISI_BASI_EN_COK:
            raise ValueError(ILETI_SINIR)
    elif sahip_turu == "kullanici":
        sahip = b.execute("SELECT id, ad, aktif FROM kullanici WHERE id = ?", (kullanici_id,)).fetchone()
        if not sahip or not sahip["aktif"]:
            raise ValueError("Kullanıcı bulunamadı ya da kapalı.")
        ogretmen_id, kod = None, f"kullanıcı {sahip['ad']}"
        if etkin_sayisi(b, kullanici_id=kullanici_id) >= KISI_BASI_EN_COK:
            raise ValueError(ILETI_SINIR)
    else:
        raise ValueError("Bilinmeyen sahip.")
    if sahip_turu != "sube":
        sube = None
    pin = yk.pin_uret() if sahip_turu in ("kullanici", "sube") else None
    bekleyen = Bekleyen(
        kimlik=kimlik_uret(b, bekleyen_kimlikler), gizli=gizli_uret(), sahip_turu=sahip_turu, kullanici_id=kullanici_id,
        ogretmen_id=ogretmen_id, etiket=etiket, olusturan=olusturan, olusturan_id=olusturan_id,
        sunucu=sunucu_kisa(parmak_izi), pin_ozet=guvenlik.parola_ozetle(pin) if pin else None,
        bitis=an + BEKLEYEN_OMRU_SN, sahip_kodu=kod, sube=sube,
    )  # fmt: skip
    return bekleyen, pin


def kaydet(b, bekleyen: Bekleyen, an: int) -> int:
    """İndirme anında satırı yazar (kişi/şube başı sınırı yeniden denetlenir: aynı anda iki üretim olabilir)."""
    if bekleyen.sahip_turu == "sube":
        if etkin_sayisi(b, sube=bekleyen.sube) >= SUBE_BASI_EN_COK:
            raise ValueError(sinir_iletisi(bekleyen.sube))
    else:
        if bekleyen.sahip_turu == "ogretmen":
            sayi = etkin_sayisi(b, ogretmen_id=bekleyen.ogretmen_id)
        else:
            sayi = etkin_sayisi(b, kullanici_id=bekleyen.kullanici_id)
        if sayi >= KISI_BASI_EN_COK:
            raise ValueError(ILETI_SINIR)
    return b.execute(
        "INSERT INTO usb_anahtar (kimlik, gizli_ozet, sahip_turu, kullanici_id, ogretmen_id, etiket, pin_ozet, olusturan, olusturma, "
        "sube) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (bekleyen.kimlik, gizli_ozeti(bekleyen.gizli), bekleyen.sahip_turu, bekleyen.kullanici_id, bekleyen.ogretmen_id,
         bekleyen.etiket, bekleyen.pin_ozet, bekleyen.olusturan, an, bekleyen.sube),
    ).lastrowid  # fmt: skip


class BekleyenDepo:
    """Üretilip indirilmeyen anahtarlar: tek kullanımlık belirteç (yalnız özeti tutulur) → Bekleyen; 5 dk.

    Yalnız üreten kullanıcının oturumu indirebilir. Sunucu yeniden başlarsa bekleyenler düşer (zararsız).
    Zaman `vt.simdi()` ile verilir (testte ilerletilebilsin).
    """

    def __init__(self):
        self.kayitlar: dict[str, Bekleyen | BekleyenPaket] = {}

    @staticmethod
    def _tekler(deger) -> list[Bekleyen]:
        return list(deger.anahtarlar) if isinstance(deger, BekleyenPaket) else [deger]

    def temizle(self, an: int) -> list[Bekleyen]:
        """Süresi dolanları çıkarır ve döndürür (paketin her anahtarı ayrı; çağıran "indirilmedi" kaydı düşer)."""
        dusen = [t for v in self.kayitlar.values() if v.bitis <= an for t in self._tekler(v)]
        self.kayitlar = {k: v for k, v in self.kayitlar.items() if v.bitis > an}
        return dusen

    def kimlikler(self) -> set[str]:
        return {t.kimlik for v in self.kayitlar.values() for t in self._tekler(v)}

    def sube_sayilari(self) -> dict[str, int]:
        """Henüz indirilmemiş şube anahtarları: şube → sayı (şube başı sınır üretimde de denetlensin)."""
        sonuc: dict[str, int] = {}
        for v in self.kayitlar.values():
            for t in self._tekler(v):
                if t.sahip_turu == "sube" and t.sube:
                    sonuc[t.sube] = sonuc.get(t.sube, 0) + 1
        return sonuc

    def koy(self, bekleyen: Bekleyen | BekleyenPaket) -> str:
        belirtec = guvenlik.belirtec()
        self.kayitlar[guvenlik.ozet(belirtec)] = bekleyen
        return belirtec

    def al(self, belirtec, kullanici_id: int, an: int) -> Bekleyen | BekleyenPaket | None:
        """Tek kullanımlık: bulunursa depodan çıkar. Başka kullanıcının belirteci bulunmuş sayılmaz (silinmez de)."""
        if not isinstance(belirtec, str) or not belirtec or len(belirtec) > 200:
            return None
        anahtar = guvenlik.ozet(belirtec)
        kayit = self.kayitlar.get(anahtar)
        if not kayit or kayit.bitis <= an or kayit.olusturan_id != kullanici_id:
            return None
        del self.kayitlar[anahtar]
        return kayit


# ---- tanıma, PIN, kopya ------------------------------------------------------------------------------
_SAHTE_OZET = hashlib.sha256(b"tahta-kontrol-usb-yok").hexdigest()


def tani(b, kimlik, gizli, tahta_id: int, an: int):
    """Anahtarı doğrular. (durum, satır|None, sahip|None).

    durum: 'tamam' · 'gecersiz' (bilinmeyen kimlik, yanlış gizli, biçimsiz; AYNI yanıt) · 'iptal' ·
    'kilitli' (anahtarın PIN'i ya da öğretmenin PIN'i kilitli) · 'sahip_pasif' · 'kapali' (özellik kapalı) ·
    'baskan_kapali' (0.21.0: şube anahtarı, başkan ayarı kapalı).
    İptal/kilit/pasif ayrımı yalnız gizli değer DOĞRUYSA yapılır (yalnız kimliği bilen bilgi alamasın).
    """
    a = ayar_al(b)
    if not a["etkin"]:
        return "kapali", None, None
    kimlik_ = kimlik_duzelt(kimlik)
    gizli_ = gizli_duzelt(gizli)
    satir = b.execute("SELECT * FROM usb_anahtar WHERE kimlik = ?", (kimlik_,)).fetchone() if kimlik_ else None
    ozet = gizli_ozeti(gizli_) if gizli_ else ""
    dogru = hmac.compare_digest(ozet, satir["gizli_ozet"] if satir else _SAHTE_OZET) and bool(satir) and bool(gizli_)
    if not dogru:
        return "gecersiz", None, None
    if satir["durum"] == "iptal":
        return "iptal", satir, None
    if satir["durum"] == "kilitli":
        return "kilitli", satir, None
    if satir["sahip_turu"] == "sube" and not baskan_acik(a):
        return "baskan_kapali", satir, None
    sahip = _sahip_satiri(b, satir)
    if satir["sahip_turu"] == "sube":
        if not sahip["aktif"]:  # şubede etkin öğrenci kalmadı
            return "sahip_pasif", satir, sahip
    elif satir["sahip_turu"] == "ogretmen":
        if not sahip or not sahip["aktif"]:
            return "sahip_pasif", satir, sahip
        if sahip["kilitli"]:
            return "kilitli", satir, sahip
    elif not sahip or not sahip["aktif"] or sahip["rol"] not in ("yonetici", "idareci"):
        return "sahip_pasif", satir, sahip
    return "tamam", satir, sahip


def kullanildi(b, satir, tahta_id: int, an: int) -> None:
    """Başarılı tanıma/işlem: yalnız SON kullanım ve tahtası tutulur (geçmiş tablo yok, §7)."""
    b.execute("UPDATE usb_anahtar SET son_kullanim = ?, son_tahta_id = ? WHERE id = ?", (an, tahta_id, satir["id"]))


class KopyaIzleyici:
    """Bellekte anahtar → (tahta, zaman). 60 sn içinde farklı tahtada → uyarı (engellemez)."""

    def __init__(self):
        self.son_gorulen: dict[int, tuple[int, int]] = {}

    def denetle(self, b, satir, tahta_id: int, an: int) -> bool:
        onceki = self.son_gorulen.get(satir["id"])
        self.son_gorulen[satir["id"]] = (tahta_id, an)
        if not onceki or onceki[0] == tahta_id or an - onceki[1] > KOPYA_PENCERE_SN:
            return False
        adlar = {s["id"]: s["ad"] for s in b.execute("SELECT id, ad FROM tahta WHERE id IN (?, ?)", (onceki[0], tahta_id))}
        b.execute("UPDATE usb_anahtar SET kopya_uyarisi = ? WHERE id = ?", (an, satir["id"]))
        vt.kayit_dus(
            b, "sistem", "USB anahtar kısa sürede iki tahtada kullanıldı",
            f"{kimlik_bicimli(satir['kimlik'])}: {adlar.get(onceki[0], '?')} → {adlar.get(tahta_id, '?')} ({an - onceki[1]} sn)",
        )  # fmt: skip
        return True


def pin_dogrula(b, kapi: yk.PinKapisi, satir, sahip, pin, tahta_id: int, an: int) -> tuple[str, int]:
    """USB anahtarla birlikte PIN. (durum, bekleme_sn); durum: 'tamam' | 'hatali' | 'bekle' | 'kilitli'.

    Öğretmen anahtarı → öğretmenin kendi yoklama PIN'i (`yoklama.pin_dogrula`, aynı sayaçlar ve kilit).
    Kullanıcı ve şube (başkan) anahtarı → anahtarın PIN'i; `PinKapisi` katmanları ("usb:"+kimlik çifti) + 24 saatte 10 hata →
    anahtar `kilitli` (açık oturumları düşer).
    """
    if satir["sahip_turu"] == "ogretmen":
        durum, _, bekleme = yk.pin_dogrula(b, kapi, sahip["kod"], pin, tahta_id, an)
        return durum, bekleme
    cift = "usb:" + satir["kimlik"]
    bekleme, _ = kapi.bekleme(tahta_id, cift, an)
    if bekleme:
        return "bekle", bekleme
    pin = str(pin or "")[:16]
    gecerli_bicim = len(pin) == 6 and metin.rakam_mi(pin)
    if gecerli_bicim and satir["pin_ozet"] and guvenlik.parola_dogrula(pin, satir["pin_ozet"]):
        kapi.basarili(tahta_id, cift)
        return "tamam", 0
    bekleme = kapi.hata(tahta_id, cift, an)
    ilk = satir["hatali_ilk"]
    if not ilk or an - ilk >= PIN_PENCERE_SN:
        sayi, ilk = 1, an
    else:
        sayi = satir["hatali_sayi"] + 1
    if sayi >= PIN_HATA_ADET:
        b.execute("UPDATE usb_anahtar SET hatali_sayi = ?, hatali_ilk = ?, durum = 'kilitli' WHERE id = ?", (sayi, ilk, satir["id"]))
        b.execute("DELETE FROM yoklama_belirtec WHERE anahtar_id = ?", (satir["id"],))
        return "kilitli", 0  # işlem kaydını çağıran düşer ("USB anahtar kilitlendi", tahta adıyla)
    b.execute("UPDATE usb_anahtar SET hatali_sayi = ?, hatali_ilk = ? WHERE id = ?", (sayi, ilk, satir["id"]))
    return ("bekle", bekleme) if bekleme else ("hatali", 0)


class TahtaSiniri:
    """Tahta başına bellek sınırları: bütün /ajan/usb/* 60 istek / 10 dk; 'gecersiz' 5 / 10 dk → tahta 10 dk kapalı."""

    def __init__(self):
        self.istekler: dict[int, list[int]] = {}
        self.gecersizler: dict[int, list[int]] = {}
        self.kapali: dict[int, int] = {}

    def istek(self, tahta_id: int, an: int) -> tuple[int, str]:
        """İsteği sayar; (bekleme_sn, ileti), 0 ise serbest."""
        kalan = self.kapali.get(tahta_id, 0) - an
        if kalan > 0:
            return kalan, ILETI_TAHTA_KAPALI
        liste = [z for z in self.istekler.get(tahta_id, []) if an - z < ISTEK_PENCERE_SN]
        if len(liste) >= ISTEK_ADET:
            self.istekler[tahta_id] = liste
            return max(1, ISTEK_PENCERE_SN - (an - liste[0])), ILETI_COK_ISTEK
        self.istekler[tahta_id] = liste + [an]
        return 0, ""

    def gecersiz(self, tahta_id: int, an: int) -> bool:
        """Geçersiz anahtarı sayar; tahta kapandıysa True."""
        liste = [z for z in self.gecersizler.get(tahta_id, []) if an - z < GECERSIZ_PENCERE_SN] + [an]
        if len(liste) >= GECERSIZ_ADET:
            self.gecersizler[tahta_id] = []
            self.kapali[tahta_id] = an + GECERSIZ_KAPALI_SN
            return True
        self.gecersizler[tahta_id] = liste
        return False


# ---- iptal, liste, yıl sonu ------------------------------------------------------------------------
def iptal(b, anahtar_id: int, kim: str, an: int, ip: str = "") -> bool:
    """Anlık ve geri alınmaz: durum='iptal', o anahtarla açılmış yoklama oturumları silinir, işlem kaydı."""
    satir = b.execute("SELECT * FROM usb_anahtar WHERE id = ?", (anahtar_id,)).fetchone()
    if not satir or satir["durum"] == "iptal":
        return False
    b.execute("UPDATE usb_anahtar SET durum = 'iptal', iptal_eden = ?, iptal_zamani = ? WHERE id = ?", (kim, an, anahtar_id))
    b.execute("DELETE FROM yoklama_belirtec WHERE anahtar_id = ?", (anahtar_id,))
    vt.kayit_dus(b, kim, "USB anahtar iptal edildi", kimlik_bicimli(satir["kimlik"]), ip)
    return True


def _an_yazi(epoch) -> str:
    return datetime.fromtimestamp(int(epoch), ISTANBUL).strftime("%d.%m.%Y %H:%M") if epoch else ""


def liste(b, an: int, kullanici_id: int | None = None) -> list[dict]:
    """Panel tablosu. kullanici_id verilirse yalnız o kullanıcının anahtarları (idareci görünümü)."""
    kosul, arg = ("WHERE a.kullanici_id = ?", (kullanici_id,)) if kullanici_id is not None else ("", ())
    satirlar = b.execute(
        "SELECT a.*, o.ad AS o_ad, o.soyad AS o_soyad, p.kod AS o_kod, k.ad AS k_ad, k.gorunen_ad AS k_gorunen, "
        "t.ad AS tahta_ad FROM usb_anahtar a LEFT JOIN ogretmen o ON o.id = a.ogretmen_id "
        "LEFT JOIN ogretmen_pin p ON p.ogretmen_id = a.ogretmen_id LEFT JOIN kullanici k ON k.id = a.kullanici_id "
        f"LEFT JOIN tahta t ON t.id = a.son_tahta_id {kosul}",
        arg,
    ).fetchall()
    sonuc = []
    for a in satirlar:
        if a["sahip_turu"] == "sube":
            sahip = f"{a['sube']} sınıf başkanı"
        elif a["sahip_turu"] == "ogretmen":
            sahip = f"{yk.ogretmen_etiketi(a['o_ad'], a['o_soyad'])} ({a['o_kod']})" if a["o_ad"] is not None else "?"
        else:
            sahip = a["k_gorunen"] or a["k_ad"] or "?"
        son = "Hiç kullanılmadı"
        if a["son_kullanim"]:
            son = _an_yazi(a["son_kullanim"]) + (f" · {a['tahta_ad']}" if a["tahta_ad"] else "")
        sonuc.append({
            "id": a["id"], "kimlik": kimlik_bicimli(a["kimlik"]), "sahip_turu": a["sahip_turu"],
            "tur": {"ogretmen": "ogretmen", "sube": "baskan"}.get(a["sahip_turu"], "idare"), "sahip": sahip, "etiket": a["etiket"],
            "sube": a["sube"] or "",
            "olusturma": _an_yazi(a["olusturma"]), "olusturan": a["olusturan"], "son_kullanim": son,
            "durum": a["durum"], "durum_adi": DURUM_ADI.get(a["durum"], a["durum"]),
            "iptal": _an_yazi(a["iptal_zamani"]) + (f" · {a['iptal_eden']}" if a["iptal_eden"] else "") if a["durum"] == "iptal" else "",
            "kopya_uyarisi": bool(a["kopya_uyarisi"] and an - a["kopya_uyarisi"] < KOPYA_ROZET_SN and a["durum"] != "iptal"),
            "kullanici_id": a["kullanici_id"], "ogretmen_id": a["ogretmen_id"],
        })  # fmt: skip
    # Önce etkin/kilitli, sonra iptal; her grupta en yeni üstte.
    return sorted(sonuc, key=lambda x: (x["durum"] == "iptal", -x["id"]))


def ogretmen_sayilari(b) -> dict[int, int]:
    """Öğretmen id → iptal olmayan anahtar sayısı (Öğretmenler sayfasındaki sütun)."""
    return {
        s["ogretmen_id"]: s["n"]
        for s in b.execute(
            "SELECT ogretmen_id, COUNT(*) AS n FROM usb_anahtar WHERE ogretmen_id IS NOT NULL AND durum != 'iptal' GROUP BY ogretmen_id"
        )
    }


def tahta_destegi(b) -> dict:
    """{"onayli": n, "destekleyen": m, "eski": n - m} — `yetenekler` içinde `usb_anahtar`."""
    onayli = destekleyen = 0
    for t in b.execute("SELECT durum_json FROM tahta WHERE durum = 'onayli'"):
        onayli += 1
        if yetenekli(t):
            destekleyen += 1
    return {"onayli": onayli, "destekleyen": destekleyen, "eski": onayli - destekleyen}


def yil_sonu(b, sinir: date) -> dict:
    """§7 saklama: iptal zamanı sınır günü bitmeden olan satırlar SİLİNİR; diğerlerinin son kullanım bilgisi
    (son_kullanim, son_tahta_id, kopya_uyarisi) sınırdan önceyse boşaltılır. Etkin idare/öğretmen anahtarları yeni
    yıla geçer. 0.21.0: sınır günü bitmeden ÜRETİLMİŞ şube (sınıf başkanı) anahtarları etkin olsalar da silinir
    (başkan her yıl değişir; açık oturumları CASCADE ile düşer). Bitiş tarihi henüz güncellenmemişken yeni yılda
    üretilenler korunur (imha saatte bir çalışır). Çağıran işlemden sonra `vt.wal_buda()`."""
    son_an = int(datetime.combine(sinir + timedelta(days=1), time(0, 0), ISTANBUL).timestamp())
    baskan = b.execute("DELETE FROM usb_anahtar WHERE sahip_turu = 'sube' AND olusturma < ?", (son_an,)).rowcount
    silinen = b.execute("DELETE FROM usb_anahtar WHERE durum = 'iptal' AND iptal_zamani < ?", (son_an,)).rowcount
    bosaltilan = b.execute(
        "UPDATE usb_anahtar SET son_kullanim = NULL, son_tahta_id = NULL WHERE durum != 'iptal' AND son_kullanim < ?", (son_an,)
    ).rowcount
    b.execute("UPDATE usb_anahtar SET kopya_uyarisi = NULL WHERE kopya_uyarisi < ?", (son_an,))
    return {"silinen": silinen, "bosaltilan": bosaltilan, "baskan": baskan}
