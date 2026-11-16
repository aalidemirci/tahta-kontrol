"""USB anahtar (0.11.0): anahtar dosyasının ayrıştırıcısı, bağlama bilgisinin çözümü ve ekran metinleri.

Saf modüldür (yalnız standart kitaplık; dosya ve aygıt okumaz). Dosyayı ve bağlama noktalarını okuyan
kod `sistem.py`'dedir; durum makinesi `servis.py`'dedir. Anahtar dosyası kök yetkili servis dışında
hiçbir yere gitmez: gizli değer ekran yardımcısına, durum dosyasına, günlüğe, tanılamaya yazılmaz.

`dosya_coz` sunucudaki `tahta_sunucu/usb_anahtar.dosya_coz` ile AYNI kurallarla çalışır (testler
ikisini aynı örnek kümesiyle karşılaştırır); ajan sunucu paketini içe aktarmaz.
"""

from __future__ import annotations

import base64

DOSYA_ADI = "tahta-kontrol.anahtar"
BASLIK = "TAHTA-KONTROL-ANAHTAR"
DOSYA_SURUMU = "1"
DOSYA_EN_BUYUK = 1024
KIMLIK_ALFABESI = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
KIMLIK_UZUNLUGU = 8
SUNUCU_UZUNLUGU = 16
GIZLI_UZUNLUGU = 52
_BASE32 = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"

TANI_OMRU_SN = 600  # sunucuyla aynı (tanınan anahtar tahtada en çok bu kadar geçerli)
IZLEME_ZAMAN_ASIMI_SN = 5  # kaçan bağlama olayına karşı yedek yoklama aralığı
OKUMA_ZAMAN_ASIMI_SN = 3
ADAY_EN_COK = 8
DERINLIK_EN_COK = 3  # /media/<hesap>/<etiket> = 2; /run/media/<hesap>/<etiket> = 3 (kökten sonra)
DOSYA_SISTEMLERI = ("vfat", "exfat", "ntfs3", "ntfs", "fuseblk", "ext4")
BAGLAMA_KOKLERI = ("/media/", "/run/media/")

# Ekran metinleri (şartname §5.6; aynen).
ILETI_OKUNUYOR = "USB anahtar okunuyor…"
ILETI_GECERSIZ = "Bu USB anahtar geçerli değil."
ILETI_IPTAL = "Bu USB anahtar iptal edilmiş. Okul idaresine başvurun."
ILETI_KILITLI = "Bu USB anahtar çok sayıda hatalı PIN nedeniyle kilitlendi. Okul idaresine başvurun."
ILETI_KAPALI = "USB anahtar bu okulda kullanılmıyor."
ILETI_CEVRIMDISI = "USB anahtar şu an kullanılamıyor: sunucuya ulaşılamıyor."
ILETI_KAYITSIZ = "Bu tahta henüz sunucuya kayıtlı değil."
ILETI_YABANCI = "Bu USB anahtar bu okulun sunucusuna ait değil."
ILETI_SURESI_DOLDU = "USB anahtar çok uzun süredir takılı. Kullanmak için çıkarıp yeniden takın."
ILETI_CIKARILDI = "USB anahtar çıkarıldı."
ILETI_SINAV = "Sınav sürüyor; USB anahtar kullanılamaz."
ILETI_BIRDEN_COK = "Birden çok USB anahtar takılı; ilki kullanılıyor."
ILETI_SURUM = "Bu USB anahtar bu tahtanın sürümünde kullanılamıyor."
ILETI_TANINMIYOR = "Bu tahta sunucuda tanınmıyor; okul idaresine bildirin."
ILETI_PIN_HATALI = "PIN hatalı."
ILETI_KILIT_KAPALI = "USB anahtarla kilit açma bu okulda kapalı."
# Sunucunun hata `neden`i → ekrandaki metin (sunucu iletisi gelmezse ya da biçimsizse).
NEDEN_ILETISI = {
    "gecersiz": ILETI_GECERSIZ,
    "iptal": ILETI_IPTAL,
    "kilitli": ILETI_KILITLI,
    "kapali": ILETI_KAPALI,
    "sinav": ILETI_SINAV,
    "pin": ILETI_PIN_HATALI,
    "kilit_kapali": ILETI_KILIT_KAPALI,
}


class DosyaHatasi(ValueError):
    """`neden`: 'boyut' | 'ascii' | 'baslik' | 'bicim' | 'surum' (tanılama sayacı için; yol ve içerik taşımaz)."""

    def __init__(self, neden: str):
        super().__init__(neden)
        self.neden = neden


def _gizli_gecerli(s: str) -> bool:
    if len(s) != GIZLI_UZUNLUGU or any(c not in _BASE32 for c in s):
        return False
    try:
        return len(base64.b32decode(s + "====")) == 32
    except ValueError:
        return False


def dosya_coz(veri) -> dict:
    """Anahtar dosyası → {"surum": 1, "kimlik", "sunucu", "gizli"} ya da DosyaHatasi.

    En çok 1024 bayt; ASCII dışı bayt → red; `#` ile başlayan ve boş satırlar yok sayılır; ilk anlamlı
    satır başlık olmalı; sonra `alan=değer` satırları (iki yanındaki boşluk kırpılır); aynı alan iki kez
    → red; bilinmeyen sürüm → 'surum'; sürüm 1'de alan kümesi tam olarak {surum, kimlik, sunucu, gizli};
    kimlik/gizli büyük harfe, sunucu küçük harfe çevrilip uzunluk ve alfabesi tam denetlenir.
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
    kimlik, sunucu, gizli = alanlar["kimlik"].upper(), alanlar["sunucu"].lower(), alanlar["gizli"].upper()
    if len(kimlik) != KIMLIK_UZUNLUGU or any(c not in KIMLIK_ALFABESI for c in kimlik):
        raise DosyaHatasi("bicim")
    if len(sunucu) != SUNUCU_UZUNLUGU or any(c not in "0123456789abcdef" for c in sunucu):
        raise DosyaHatasi("bicim")
    if not _gizli_gecerli(gizli):
        raise DosyaHatasi("bicim")
    return {"surum": 1, "kimlik": kimlik, "sunucu": sunucu, "gizli": gizli}


def sahip_metni(usb: dict) -> str:
    """Tahtada anahtarın sahibi: öğretmende "A. Yılmaz (kod 112)", idarede "İdare · A. Demir" (sunucunun kısa adı)."""
    etiket = str(usb.get("etiket") or "")
    if usb.get("tur") == "ogretmen" and usb.get("kod"):
        return f"{etiket} (kod {usb['kod']})" if etiket else f"kod {usb['kod']}"
    return etiket


def ekran_metni(usb: dict) -> str:
    """Bildirimde ve kilit ekranının bilgi satırında görünen metin; gösterilecek bir şey yoksa ""."""
    durum, ileti = usb.get("durum"), str(usb.get("ileti") or "")
    if durum == "tanindi":
        ana = f"USB anahtar tanındı · {sahip_metni(usb)}".rstrip(" ·")
        return f"{ana}\n{ileti}" if ileti else ana
    if durum == "okunuyor":
        return ILETI_OKUNUYOR
    return ileti  # "suresi_doldu" kendiliğinden gösterilmez (yalnız bir dokunuşta)


def sunucu_uyar_mi(dosya_sunucu: str, parmak_izi: str) -> bool:
    """Dosyadaki `sunucu` alanı, tahtanın bağlı olduğu sertifikanın parmak izinin ilk 16 hanesi mi?
    Uymazsa gizli değer HİÇ gönderilmez (başka okulun ya da sahte sunucunun anahtarı)."""
    beklenen = str(parmak_izi or "").lower()[:SUNUCU_UZUNLUGU]
    return len(beklenen) == SUNUCU_UZUNLUGU and dosya_sunucu == beklenen


# ---- /proc/self/mountinfo --------------------------------------------------------------------------
def _kacis_coz(alan: str) -> str:
    """mountinfo kaçışları: boşluk \\040, sekme \\011, satır sonu \\012, ters bölü \\134 (sekizlik)."""
    sonuc, i = [], 0
    while i < len(alan):
        sekizlik = alan[i + 1 : i + 4]
        if alan[i] == "\\" and len(sekizlik) == 3 and all(c in "01234567" for c in sekizlik):
            sonuc.append(chr(int(sekizlik, 8)))
            i += 4
            continue
        sonuc.append(alan[i])
        i += 1
    return "".join(sonuc)


def mountinfo_coz(metin: str) -> list[dict]:
    """`/proc/self/mountinfo` satırları → [{"kimlik","aygit","kok","yol","fs","kaynak"}]. Bozuk satır atlanır.

    Biçim: `36 35 98:0 /kok /yol seçenekler [isteğe bağlı alanlar] - fs kaynak süper-seçenekler`.
    """
    sonuc = []
    for satir in (metin or "").splitlines():
        parca = satir.split()
        try:
            ayrac = parca.index("-", 6)
        except ValueError:
            continue
        if len(parca) < ayrac + 3 or ":" not in parca[2]:
            continue
        try:
            kimlik = int(parca[0])
            buyuk, kucuk = (int(x) for x in parca[2].split(":", 1))
        except ValueError:
            continue
        sonuc.append({
            "kimlik": kimlik, "aygit": (buyuk, kucuk), "kok": _kacis_coz(parca[3]), "yol": _kacis_coz(parca[4]),
            "fs": parca[ayrac + 1], "kaynak": _kacis_coz(parca[ayrac + 2]),
        })  # fmt: skip
    return sonuc


def aday_nedeni(baglama: dict, hesap: str | None) -> str:
    """Bağlama aday mı? "" = aday; değilse elenme nedeni ("yer" | "alt_dizin" | "dosya_sistemi" | "baska_oturum").

    Çıkarılabilirlik (ölçüt 4) /sys okuması gerektirdiği için `sistem.py`'dedir. `hesap`: etkin oturumun
    hesabı (bilinmiyorsa None: ölçüt gevşer). Hesap adı bu işlevden başka yere yazılmaz.
    """
    yol = baglama["yol"]
    kok = next((k for k in BAGLAMA_KOKLERI if yol.startswith(k)), None)
    if kok is None or ".." in yol.split("/"):
        return "yer"
    parcalar = [p for p in yol[len(kok):].split("/") if p]
    if not parcalar or len(parcalar) > DERINLIK_EN_COK:
        return "yer"
    if baglama["kok"] != "/":
        return "alt_dizin"
    if baglama["fs"] not in DOSYA_SISTEMLERI:
        return "dosya_sistemi"
    if hesap and parcalar[0] != hesap:
        return "baska_oturum"
    return ""


ELENME_ADLARI = {
    "cikarilabilir_degil": "çıkarılabilir değil",
    "dosya_sistemi": "desteklenmeyen dosya sistemi",
    "baska_oturum": "başka oturum",
    "alt_dizin": "alt dizin bağlaması",
}
OKUMA_ADLARI = {
    "bulundu": "anahtar bulundu",
    "yok": "dosya yok",
    "sembolik": "reddedildi: sembolik bağ",
    "duz_degil": "reddedildi: düz dosya değil",
    "buyuk": "reddedildi: çok büyük",
    "bicim": "reddedildi: biçim",
    "zaman_asimi": "reddedildi: zaman aşımı",
    "aygit": "reddedildi: bağlama değişti",
    "okunamadi": "okunamadı",
}
