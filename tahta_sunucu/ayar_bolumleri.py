"""Ayarlar'ın bölüm listesi (0.16.0, FastAPI'siz): tek kaynak.

Bölüm menüsü, giriş sayfasındaki kartlar, değer özetleri, kurulum kontrol listesi, Ayarlar içi arama dizini ve
eski adres eşlemeleri YALNIZ buradan üretilir (`web.py` ve şablonlar bu listeyi çizer; kopyası yazılmaz).

Özet ve arama dizini sır taşımaz: kilit kodu (kendisi, özeti, uzunluğu), parola, PIN, kişi adı, ağ adresi,
klasör yolu, tahta ve şube adı buraya girmez. Sayfa çizimi ağ çağrısı yapmaz: güncelleme özeti saklanan
durumdan okunur (kural 32).
"""

from __future__ import annotations

import re
from datetime import date

from . import (
    acilis_kilidi,
    adresler,
    dugme,
    guncelleme,
    guvenlik,
    maske,
    saklama,
    temizlik,
    usb_anahtar,
    vt,
    yedek,
    yoklama,
)

KUMELER = ["Okul", "Tahta davranışı", "Özellikler", "Veri ve sistem"]

# anahtar: adresteki ad (/ayarlar/<anahtar>) ve şablon parçası (_ayar_<anahtar>.html).
# yerler: o sayfadaki kartların ileti anahtarları (?yer=…#ileti); ileti o kartın başında çizilir.
BOLUMLER: list[dict] = [
    {"anahtar": "okul", "baslik": "Okul kimliği", "kume": "Okul", "simge": "a-kimlik",
     "aciklama": "Okul adı, renkler, logo ve önizleme", "yerler": ["ad", "kimlik", "logo"],
     "sozcukler": "okul adı renk logo marka tema görünüm amblem kontrast önizleme"},
    {"anahtar": "kilit", "baslik": "Kilit ve güvenlik", "kume": "Tahta davranışı", "simge": "s-kilit",
     "aciklama": "Ortak kilit kodu, açılışta kilit", "yerler": ["kod", "acilis"],
     "sozcukler": "kilit kodu şifre parola açılışta kilit güvenlik kodu kaldır değiştir"},
    {"anahtar": "gunsonu", "baslik": "Kapatma ve gün sonu", "kume": "Tahta davranışı", "simge": "a-guc",
     "aciklama": "Otomatik kapatma, oturum temizliği", "yerler": ["kapatma", "temizlik"],
     "sozcukler": "otomatik kapatma kapanma kapanış kapat enerji tasarruf saat saati hafta sonu oturum temizliği temizlik çerez tarayıcı gün sonu"},
    {"anahtar": "yuzer", "baslik": "Yüzer düğme", "kume": "Tahta davranışı", "simge": "a-dugme",
     "aciklama": "Tahtadaki yüzer düğme ve menüsü", "yerler": ["dugme"],
     "sozcukler": "kayar buton yüzer düğme menü tahtadaki düğme kilitle kapat yeniden başlat arıza"},
    {"anahtar": "yoklama", "baslik": "Ders yoklaması", "kume": "Özellikler", "simge": "m-yoklama",
     "aciklama": "Açık/kapalı, tahtada ad gösterimi, süreler", "yerler": ["yoklama"],
     "sozcukler": "yoklama maske pin süre öğrenci adı görünümü oturum"},
    {"anahtar": "usb", "baslik": "USB anahtar", "kume": "Özellikler", "simge": "a-usb",
     "aciklama": "USB anahtarla yoklama ve kilit açma", "yerler": ["usb_anahtar"],
     "sozcukler": "usb bellek anahtar flash pin kilit açar"},
    {"anahtar": "sinav", "baslik": "Sınav ekranı", "kume": "Özellikler", "simge": "m-sinav",
     "aciklama": "Sınav ekranındaki kurallar metni", "yerler": ["sinav"],
     "sozcukler": "sınav kuralları sınav ekranı metin"},
    {"anahtar": "veri", "baslik": "Veri saklama ve yedek", "kume": "Veri ve sistem", "simge": "a-kalkan",
     "aciklama": "Öğretim yılı bitişi (KVKK), yedek parolası, yedek saklama", "yerler": ["saklama", "parola", "ayar"],
     "sozcukler": "kvkk kişisel veri saklama öğretim yılı bitişi bitiş tarihi yıl sonu silme imha yedek parola şifre ikinci kopya klasör"},
    {"anahtar": "sunucu", "baslik": "Sunucu ve ağ", "kume": "Veri ve sistem", "simge": "a-sunucu",
     "aciklama": "Tahtaların bağlandığı adresler, bu sunucu", "yerler": ["adresler"],
     "sozcukler": "ip adres sunucu ağ parmak izi sertifika veri klasörü dns"},
    {"anahtar": "guncelleme", "baslik": "Güncelleme denetimi", "kume": "Veri ve sistem", "simge": "s-guncel",
     "aciklama": "GitHub'dan yeni sürüm haberi", "yerler": ["guncelleme"],
     "sozcukler": "güncelleme sürüm github yeni sürüm denetle"},
    {"anahtar": "kullanicilar", "baslik": "Panel kullanıcıları", "kume": "Veri ve sistem", "simge": "m-kullanici",
     "aciklama": "Panele giren idareciler ve roller", "yerler": ["hesaplar", "ekle"],
     "sozcukler": "kullanıcı hesap ekle idareci müdür yardımcısı yönetici parola şifre rol yetki"},
]  # fmt: skip
ANAHTARLAR = [b["anahtar"] for b in BOLUMLER]

# Ayarlar'da OLMAYAN ama orada aranan işler: hepsi var olan GET adresidir (test eder).
BASKA_YERDE: list[dict] = [
    {"ad": "Program kilidi (teneffüste ve boş derste kilit)", "yer": "Program › Kurallar", "yol": "/program?bolum=kurallar",
     "sozcukler": "program kilidi teneffüs boş ders kilitle durdur"},
    {"ad": "Program kilidini durdur (1 saat, bugün)", "yer": "Bugün › Şu an", "yol": "/",
     "sozcukler": "program kilidi durdur tören etkinlik"},
    {"ad": "Boş ders uyarısı", "yer": "Program › Uyarılar · kuralı Kurallar'da", "yol": "/program/uyarilar",
     "sozcukler": "boş ders uyarısı rapor"},
    {"ad": "Zil saatleri ve çizelgeler", "yer": "Program › Zil saatleri", "yol": "/program?bolum=zil",
     "sozcukler": "zil ders saati teneffüs çizelge okul zili ikili eğitim devre sabah öğle"},
    {"ad": "Acil durum şablonları", "yer": "Acil durum › Şablonlar", "yol": "/acil?sekme=sablonlar",
     "sozcukler": "acil şablon yangın deprem tahliye tatbikat"},
    {"ad": "Öğrenci listesi (e-Okul)", "yer": "Kişiler ve anahtarlar › Öğrenciler", "yol": "/ogrenciler",
     "sozcukler": "öğrenci listesi sınıf eokul e-okul yükle ekle"},
    {"ad": "Öğretmenler ve PIN", "yer": "Kişiler ve anahtarlar", "yol": "/ogretmenler",
     "sozcukler": "öğretmen pin kod pusula"},
    {"ad": "USB anahtarlar (üret, iptal)", "yer": "Kişiler ve anahtarlar", "yol": "/usb-anahtarlar",
     "sozcukler": "usb anahtar bellek üret iptal"},
    {"ad": "Yedek al, indir, geri yükle", "yer": "Yedekler", "yol": "/yedekler",
     "sozcukler": "yedek geri yükle indir"},
]  # fmt: skip

# Eski `GET /ayarlar?yer=<eski>` (yer imi, açık sekmedeki eski yönlendirme) → bölüm anahtarı ya da tam yol.
ESKI_YER = {
    "kimlik": "okul",
    "acilis": "kilit",
    "temizlik": "gunsonu",
    "yoklama": "yoklama",
    "usb_anahtar": "usb",
    "saklama": "veri",
    "adresler": "sunucu",
    "guncelleme": "guncelleme",
    "dugme": "yuzer",
    "sinav": "sinav",
    "acil": "/acil?sekme=sablonlar",
}
# Eski `/ayarlar#<parça>` (parça sunucuya gitmez): giriş sayfasındaki JSON bloğundan panel.js yönlendirir.
ESKI_PARCA = {
    "adresler": "/ayarlar/sunucu#adresler",
    "acil-sablonlari": "/acil?sekme=sablonlar",
    "sinav-ekrani": "/ayarlar/sinav",
    "ders-yoklamasi": "/ayarlar/yoklama",
    "usb-anahtar": "/ayarlar/usb",
    "usb_anahtar": "/ayarlar/usb",
    "saklama": "/ayarlar/veri#saklama",
    "oturum-temizligi": "/ayarlar/gunsonu#temizlik",
    "acilis-kilidi": "/ayarlar/kilit#acilis",
    "guncelleme-denetimi": "/ayarlar/guncelleme",
    "guncelleme": "/ayarlar/guncelleme",
    "yuzer-dugme": "/ayarlar/yuzer",
    "kimlik": "/ayarlar/okul",
    "okul_adi": "/ayarlar/okul",
    "onizleme": "/ayarlar/okul",
}

# Harf katlama: panel.js'teki AYAR_KATLA_KAYNAK / AYAR_KATLA_HEDEF ile AYNI dizgiler (test karşılaştırır).
KATLA_KAYNAK = "çğıöşüâîû"
KATLA_HEDEF = "cgiosuaiu"
_KATLAMA = str.maketrans(KATLA_KAYNAK, KATLA_HEDEF)
_AYIRICI = re.compile(r"[^0-9a-zçğıöşüâîû-]+")
SORGU_EN_UZUN = 60


def bolum(anahtar: str) -> dict | None:
    for b in BOLUMLER:
        if b["anahtar"] == anahtar:
            return b
    return None


def kucult(metin: str) -> str:
    """Türkçe küçük harf (JS: toLocaleLowerCase("tr")): I→ı, İ→i, sonra lower()."""
    return str(metin).replace("I", "ı").replace("İ", "i").lower()


def katla(metin: str) -> str:
    return metin.translate(_KATLAMA)


def sozcukler(metin: str) -> list[str]:
    return [s for s in _AYIRICI.split(kucult(metin)) if s]


def samanlik(*parcalar: str) -> str:
    """Arama samanlığı: boşlukla ayrılmış, yinelenmeyen küçük harfli sözcükler (HTML'de `data-ara`)."""
    gorulen: dict[str, None] = {}
    for parca in parcalar:
        for s in sozcukler(parca):
            gorulen.setdefault(s, None)
    return " ".join(gorulen)


def _dizin() -> tuple[list[tuple[str, str]], list[tuple[int, str]]]:
    bolumler = [(b["anahtar"], samanlik(b["baslik"], b["aciklama"], b["sozcukler"], b["kume"])) for b in BOLUMLER]
    baska = [(sira, samanlik(o["ad"], o["yer"], o["sozcukler"])) for sira, o in enumerate(BASKA_YERDE)]
    return bolumler, baska


def uyar(sorgu_sozcukleri: list[str], saman: str) -> bool:
    saman_sozcukleri = saman.split()
    return all(any(s.startswith(q) for s in saman_sozcukleri) for q in sorgu_sozcukleri)


def ara(sorgu: str) -> dict:
    """Ayarlar içi arama: {"sorgu", "etkin", "bolumler": [anahtar], "baska": [BASKA_YERDE sırası], "sayi"}.

    Sorgu sözcüklere ayrılır; her sözcük samanlıktaki bir sözcüğün BAŞINDA geçmelidir. Önce Türkçe küçük harfle;
    hiçbir satır eşleşmezse harf katlanarak ("yuzer" → "yüzer"). panel.js AYNI kuralı uygular.
    """
    sorgu = " ".join(str(sorgu or "")[:SORGU_EN_UZUN].split())
    q = sozcukler(sorgu)
    bolumler, baska = _dizin()
    if not q:
        return {"sorgu": "", "etkin": False, "bolumler": [a for a, _ in bolumler], "baska": [], "sayi": 0}
    b_es = [a for a, s in bolumler if uyar(q, s)]
    o_es = [i for i, s in baska if uyar(q, s)]
    if not b_es and not o_es:
        qk = [katla(s) for s in q]
        b_es = [a for a, s in bolumler if uyar(qk, katla(s))]
        o_es = [i for i, s in baska if uyar(qk, katla(s))]
    return {"sorgu": sorgu, "etkin": True, "bolumler": b_es, "baska": o_es, "sayi": len(b_es) + len(o_es)}


def _adres_listede_yok(b, ipler: list[str] | None) -> bool:
    """Adres uyarısının koşulu (bugun.bekleyenler `adres` satırıyla aynı işlevler)."""
    ipler = guvenlik.yerel_ipler() if ipler is None else ipler
    return bool(ipler) and not adresler.bu_bilgisayar_listede_mi(adresler.al(b), ipler)


def _ozet(metin: str, uyari: bool = False, kisa: str = "") -> dict:
    """metin: giriş sayfasındaki kartın özeti; kisa: dar yan menüdeki karşılığı (verilmezse metin)."""
    return {"metin": metin, "ton": "uyari" if uyari else "", "kisa": kisa or metin}


def kapatma_ozeti(kapatma) -> str:
    """Otomatik kapatmanın kısa özeti: hafta içi saatleri ve/veya "hafta sonu"; ikisi de kapalıysa "Kapatma kapalı".
    Kartın rozetiyle aynı koşul (etkin ya da hafta_sonu): yalnız hafta sonu açıkken "kapalı" denmez."""
    kapatma = kapatma if isinstance(kapatma, dict) else {}
    saatler = [str(s) for s in (kapatma.get("saatler") or [])]
    parcalar = [", ".join(saatler)] if kapatma.get("etkin") and saatler else []
    if kapatma.get("hafta_sonu"):
        parcalar.append("hafta sonu")
    return " · ".join(parcalar).capitalize() if parcalar else "Kapatma kapalı"


def ozetler(b, bugun: date, ipler: list[str] | None = None) -> dict[str, dict]:
    """Her bölümün o anki değer özeti: {anahtar: {"metin", "ton", "kisa"}}; ton "" ya da "uyari"."""
    sonuc: dict[str, dict] = {}
    okul_adi = str(vt.ayar_al(b, "okul_adi", "") or "").strip()
    sonuc["okul"] = _ozet(okul_adi) if okul_adi else _ozet("Ad girilmedi", True)
    if vt.ayar_al(b, "kilit_kodu"):
        acilis = "açık" if acilis_kilidi.ayar_al(b) else "kapalı"
        sonuc["kilit"] = _ozet(f"Kod tanımlı · açılışta kilit {acilis}", kisa="Tanımlı")
    else:  # kod yokken açılışta kilit uygulanmaz; ayrıca yazılmaz
        sonuc["kilit"] = _ozet("Kod tanımsız", True, kisa="Tanımsız")

    metin = kapatma_ozeti(vt.ayar_al(b, "otomatik_kapatma"))
    if temizlik.ayar_al(b)["etkin"]:
        metin += " · temizlik açık"
    sonuc["gunsonu"] = _ozet(metin)

    dg = dugme.ayar_al(b)
    if not dg["acik"]:
        sonuc["yuzer"] = _ozet("Kapalı")
    elif not any(dg["islemler"].values()):
        sonuc["yuzer"] = _ozet("İşlem seçilmedi", True)
    else:
        sonuc["yuzer"] = _ozet("Açık")
    yk = yoklama.ayar_al(b)
    ornek = maske.bicim_parcalari(yk["maske"])[1]  # sabit örnek ("123 Ayşe Y."); gerçek öğrenci adı değildir
    sonuc["yoklama"] = _ozet(f"Açık · {ornek}" if ornek else "Açık", kisa="Açık") if yk["etkin"] else _ozet("Kapalı")
    sonuc["usb"] = _ozet("Açık" if usb_anahtar.ayar_al(b)["etkin"] else "Kapalı")
    sonuc["sinav"] = _ozet("Özel metin" if isinstance(vt.ayar_al(b, "sinav_kurallari"), str) else "Varsayılan")

    sk = saklama.durum(b, bugun)
    eksikler = []
    if not yedek.ayarlar(b)["parola_var"]:
        eksikler.append("Yedek parolası yok")
    if not sk["girildi"]:
        eksikler.append("Tarih yok")
    elif sk["gecti"]:
        eksikler.append("Tarih geçti")
    if len(eksikler) > 1:
        sonuc["veri"] = _ozet(f"{len(eksikler)} eksik", True)
    elif eksikler:
        sonuc["veri"] = _ozet(eksikler[0], True)
    else:
        sonuc["veri"] = _ozet(sk["bitis_metni"])

    liste = adresler.al(b)
    if _adres_listede_yok(b, ipler):
        sonuc["sunucu"] = _ozet("Adres listede yok", True)
    elif not liste:
        sonuc["sunucu"] = _ozet("Adres: otomatik", kisa="Otomatik")
    else:
        sonuc["sunucu"] = _ozet(f"{len(liste)} adres")

    g = guncelleme.gorunum(b)
    ham = guncelleme.durum_al(b)
    if not g["acik"]:
        sonuc["guncelleme"] = _ozet("Kapalı")
    elif g["yeni"]:
        sonuc["guncelleme"] = _ozet(f"Yeni sürüm {g['yeni']['surum']}")
    elif not g["denetlendi"]:
        sonuc["guncelleme"] = _ozet("Denetlenmedi")
    elif ham.get("sonuc") != "tamam":
        sonuc["guncelleme"] = _ozet("Ulaşılamadı")
    else:
        sonuc["guncelleme"] = _ozet("Güncel")

    kisi = b.execute("SELECT COUNT(*) FROM kullanici WHERE aktif = 1").fetchone()[0]
    sonuc["kullanicilar"] = _ozet(f"{kisi} kişi")
    return sonuc


def kurulum(b, bugun: date, ipler: list[str] | None = None) -> dict:
    """Kurulum kontrol listesi: {"zorunlu": [madde], "oneri": [madde], "toplam", "tamam", "zorunlu_eksik", "oneri_eksik"}.

    Madde: {"anahtar", "ad", "tamam", "neden", "yol", "eylem"}. Koşullar pano bantlarının ve Ayarlar uyarılarının
    okuduğu işlevlerden gelir (kopya koşul yoktur). Adresin kendisi, kişi adı, yol yazılmaz.
    """
    sk = saklama.durum(b, bugun)
    zorunlu = [
        {"anahtar": "yedek_parolasi", "ad": "Yedek parolası", "tamam": bool(yedek.ayarlar(b)["parola_var"]),
         "neden": "Parola yoksa otomatik yedek alınmaz.", "yol": "/ayarlar/veri#yedek", "eylem": "Parola belirle"},
        {"anahtar": "ogretim_yili", "ad": "Öğretim yılı bitişi", "tamam": sk["uyari"] is None,
         "neden": ("Tarih geçti; yeni öğretim yılının bitişini girin." if sk["gecti"]
                   else "Öğrenci verisi yıl sonunda silinmez (KVKK)."),
         "yol": "/ayarlar/veri#saklama", "eylem": "Tarihi gir"},
        {"anahtar": "okul_adi", "ad": "Okul adı", "tamam": bool(str(vt.ayar_al(b, "okul_adi", "") or "").strip()),
         "neden": "Kilit ve duyuru ekranında okul adı görünmez.", "yol": "/ayarlar/okul", "eylem": "Adı yaz"},
        {"anahtar": "sunucu_adresi", "ad": "Sunucu adresi", "tamam": not _adres_listede_yok(b, ipler),
         "neden": "Bu bilgisayarın adresi tahtalara bildirilen listede yok.", "yol": "/ayarlar/sunucu#adresler",
         "eylem": "Adresleri aç"},
    ]  # fmt: skip
    oneri = [
        {"anahtar": "kilit_kodu", "ad": "Ortak kilit kodu", "tamam": bool(vt.ayar_al(b, "kilit_kodu")),
         "neden": "Kilitlenen tahta yalnız panelden açılır.", "yol": "/ayarlar/kilit", "eylem": "Kod belirle"},
        {"anahtar": "zil", "ad": "Zil saatleri", "tamam": bool(b.execute("SELECT 1 FROM ders_saati LIMIT 1").fetchone()),
         "neden": "Program kilidi ve ders önerisi çalışmaz.", "yol": "/program", "eylem": "Program"},
        {"anahtar": "derslik", "ad": "Derslik programı", "tamam": bool(b.execute("SELECT 1 FROM tahta_ders LIMIT 1").fetchone()),
         "neden": "Boş ders uyarısı ve program kilidi tahtayı tanımaz.", "yol": "/program/aktar", "eylem": "İçe aktar"},
    ]  # fmt: skip
    if yoklama.ayar_al(b)["etkin"]:  # Ayarlar'daki "öğrenci listesi yüklenmedi" bandının koşulu
        oneri.append({
            "anahtar": "ogrenci", "ad": "Öğrenci listesi",
            "tamam": bool(b.execute("SELECT 1 FROM ogrenci WHERE aktif = 1 LIMIT 1").fetchone()),
            "neden": "Tahtada liste boş görünür.", "yol": "/ogrenciler", "eylem": "Listeyi yükle",
        })  # fmt: skip
    yonetici = b.execute("SELECT COUNT(*) FROM kullanici WHERE aktif = 1 AND rol = 'yonetici'").fetchone()[0]
    oneri.append({
        "anahtar": "ikinci_yonetici", "ad": "İkinci yönetici hesabı", "tamam": yonetici >= 2,
        "neden": "Tek yönetici parolasını unutursa panele girilemez.", "yol": "/ayarlar/kullanicilar",
        "eylem": "Kullanıcı ekle",
    })  # fmt: skip
    hepsi = zorunlu + oneri
    return {
        "zorunlu": zorunlu,
        "oneri": oneri,
        "toplam": len(hepsi),
        "tamam": sum(1 for m in hepsi if m["tamam"]),
        "zorunlu_eksik": [m for m in zorunlu if not m["tamam"]],
        "oneri_eksik": [m for m in oneri if not m["tamam"]],
        "tamamlanan": [m for m in hepsi if m["tamam"]],
    }


def menu(ozet: dict[str, dict], eslesen: list[str] | None = None) -> list[dict]:
    """Kümelenmiş bölüm listesi (giriş kartları ve yan menü): [{"ad", "bolumler": [{…bölüm, "ozet", "ara", "ara_kat", "gizli"}]}]."""
    kumeler = []
    for ad in KUMELER:
        satirlar = []
        for b in BOLUMLER:
            if b["kume"] != ad:
                continue
            saman = samanlik(b["baslik"], b["aciklama"], b["sozcukler"], b["kume"])
            satirlar.append({
                **b, "ozet": ozet.get(b["anahtar"], _ozet("")), "ara": saman, "ara_kat": katla(saman),
                "gizli": eslesen is not None and b["anahtar"] not in eslesen,
            })  # fmt: skip
        kumeler.append({"ad": ad, "bolumler": satirlar, "gizli": all(s["gizli"] for s in satirlar)})
    return kumeler


def baska_yerde(eslesen: list[int] | None = None) -> list[dict]:
    sonuc = []
    for sira, o in enumerate(BASKA_YERDE):
        saman = samanlik(o["ad"], o["yer"], o["sozcukler"])
        sonuc.append({**o, "ara": saman, "ara_kat": katla(saman), "gizli": eslesen is None or sira not in eslesen})
    return sonuc
