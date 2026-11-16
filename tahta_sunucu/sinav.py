"""Kelebek sınav duyurusu, sınav kipi ve sınav yoklaması (Aşama 4) — iş mantığı.

Kaynak: Kelebek Sınav'ın R5 Toplu Dağıtım Çizelgesi (.xlsx). Ad soyad SAKLANMAZ:
maske içe aktarma anında hesaplanır, ad bellekte atılır (KVKK md. 4/2-ç).

Sınav kipi komut değil DURUMDUR: `tahta_sinavi()` her `/ajan/bekle` yanıtında
`ayar.sinav` olarak yeniden hesaplanır; kalan süreler sunucu saatinden gelir.
Pencere: [başlangıç − GIRIS_ONCESI_SN, salon bitişi). Gözetmen kodu yalnız o
pencerede ve yalnız salonun eşli tahtasında geçerlidir; sunucuda doğrulanır.

İşlevler veritabanı işlemi (`b`) içinde çağrılır; uyandırmayı çağıran yapar. Kişisel
veri silen işlerden sonra çağıran `vt.wal_buda()` çalıştırır.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

from . import acil, maske, metin, vt, xlsx
from . import duyuru as duyuru_mod

ISTANBUL = ZoneInfo("Europe/Istanbul")

SINAV_YETENEGI = "sinav"
GIRIS_ONCESI_SN = 600
PROGRAM_ONCESI_SN = 600  # program işi pencereden önceki 10 dk'da yeni program kilidi vermez (§0-7)
SAKLAMA_GUN = 30
GOZETMEN_OTURUM_SN = 900
KOD_DENEME = 5
KOD_PENCERE_SN = 600
KOD_BEKLEME_SN = 300
DOSYA_SINIRI = 5 * 1024 * 1024
SATIR_SINIRI = 5000
SALON_LISTE_SINIRI = 60
VARSAYILAN_SURE_DK = 40
SURE_ARALIGI = (1, 300)
UZATMA_SECENEKLERI = (5, 10, 15, 20, 30)
UZATMA_EN_COK_DK = 120
DUYURU_SURE_ARALIGI = (1, 240)
DUYURU_VARSAYILAN_DK = 10
KURALLAR_EN_UZUN = 1500
KURALLAR_EN_COK_SATIR = 8  # tahtadaki sınav ekranı da en çok 8 satır gösterir (ekran.KURALLAR_EKRAN_SATIRI)
GOZETMEN_ADI_EN_UZUN = 60
SINAV_ADI_EN_UZUN = 200
HATA_GOSTERIM = 20
# Bir sınavın en uzun süresi (sorgu sınırı): en uzun ders + en çok uzatma.
EN_UZUN_SN = (SURE_ARALIGI[1] + UZATMA_EN_COK_DK) * 60

R5_IMZA = "TOPLU DAĞITIM ÇİZELGESİ"
R5_SAYFA = "Dagitim"
R5_BASLIKLAR = ("Okul No", "Ad Soyad", "Şube", "Ders", "Salon", "Koltuk No", "Durum")
R5_BASLIK_SATIRI = 4  # 1'den sayılır

# Okulun tercihi; mevzuat alıntısı değildir, ekranda dayanak gösterilmez.
SINAV_KURALLARI_VARSAYILAN = (
    "Cep telefonu ve akıllı saat gibi cihazlar kapalı olarak gözetmene teslim edilir.\n"
    "Sınav süresince konuşulmaz, araç gereç alışverişi yapılmaz.\n"
    "Sınavın ilk ve son 10 dakikasında salondan çıkılmaz.\n"
    "Kâğıdınıza adınızı, numaranızı ve şubenizi yazmayı unutmayın."
)

EVRE_ADI = {
    "taslak": "Taslak",
    "yayinda": "Yayında",
    "giris": "Giriş",
    "suruyor": "Sürüyor",
    "bitti": "Bitti",
    "kaldirildi": "Sınav kipi kaldırıldı",
    "silindi": "Kişisel veri silindi",
}
EKRAN_EVRE_ADI = {"giris": "Giriş ekranında", "suruyor": "Sınav ekranında", "yoklama": "Gözetmen yoklamasında"}


class IceAktarmaHatasi(ValueError):
    """Satır hataları: ilk HATA_GOSTERIM tanesi `hatalar`'da, toplam `toplam`'da. Ad içermez."""

    def __init__(self, hatalar: list[str], toplam: int):
        super().__init__(f"Dosyada {toplam} hata var; hiçbir şey kaydedilmedi.")
        self.hatalar = hatalar
        self.toplam = toplam


# ---- küçük yardımcılar --------------------------------------------------------------------
def saat_metni(epoch) -> str:
    return datetime.fromtimestamp(int(epoch), ISTANBUL).strftime("%H:%M") if epoch else ""


def tarih_metni(epoch) -> str:
    return datetime.fromtimestamp(int(epoch), ISTANBUL).strftime("%d.%m.%Y") if epoch else ""


def tarih_iso(epoch) -> str:
    """input type=date değeri (YYYY-AA-GG); boş başlangıçta ''."""
    return datetime.fromtimestamp(int(epoch), ISTANBUL).strftime("%Y-%m-%d") if epoch else ""


def an_metni(epoch) -> str:
    return datetime.fromtimestamp(int(epoch), ISTANBUL).strftime("%d.%m.%Y %H:%M") if epoch else ""


def kod_uret(kullanilan: set[str] | None = None) -> str:
    kullanilan = kullanilan or set()
    while True:
        kod = f"{secrets.randbelow(10**6):06d}"
        if kod not in kullanilan:
            return kod


def kurallar(b) -> str:
    deger = vt.ayar_al(b, "sinav_kurallari")
    return deger if isinstance(deger, str) and deger.strip() else SINAV_KURALLARI_VARSAYILAN


def sirala_anahtari(ad: str) -> tuple:
    """Salon/şube adları için doğal sıra: "9/A" < "10/A"; Türk abecesi."""
    parcalar = re.split(r"(\d+)", str(ad))
    return tuple((0, int(p), ()) if metin.rakam_mi(p) else (1, 0, metin.tr_sirala_anahtari(p)) for p in parcalar if p)


def no_anahtari(okul_no: str) -> tuple:
    return (0, int(okul_no), "") if metin.rakam_mi(str(okul_no)) else (1, 0, str(okul_no))


# ---- R5 ayrıştırma ----------------------------------------------------------------------------
_TARIH_SAAT = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4}) (\d{2}):(\d{2})$")


def kunye_ayristir(a2: str) -> dict:
    """A2: "<sınav adı> · <gg.aa.yyyy SS:DD> · <yıl dönem> · Üretim: …".

    Tarih-saat parçası bulunamaz ya da geçersizse künye boş döner (ad '', baslangic 0).
    """
    parcalar = [p.strip() for p in str(a2 or "").split(" · ")]
    for sira, parca in enumerate(parcalar):
        eslesme = _TARIH_SAAT.match(parca)
        if not eslesme:
            continue
        g, a, y, s, d = (int(x) for x in eslesme.groups())
        try:
            baslangic = int(datetime(y, a, g, s, d, tzinfo=ISTANBUL).timestamp())
        except ValueError:
            break
        sonraki = parcalar[sira + 1] if sira + 1 < len(parcalar) else ""
        return {
            "ad": " · ".join(parcalar[:sira]).strip()[:SINAV_ADI_EN_UZUN],
            "baslangic": baslangic,
            "donem": "" if sonraki.startswith("Üretim:") else sonraki[:80],
        }
    return {"ad": "", "baslangic": 0, "donem": ""}


def r5_ayristir(sayfa_adi: str, satirlar: list[list[str]]) -> dict:
    """R5 satırlarını doğrular. Döndürür: {ad, baslangic, donem, kayitlar, uyarilar}.

    kayitlar: [{okul_no, maske, sube, ders, salon, koltuk}] — ad soyad burada atılır.
    Biçim hatasında ValueError, satır hatalarında IceAktarmaHatasi (metinlerde ad yok).
    """

    def hucre(satir_no: int, sutun: int) -> str:
        satir = satirlar[satir_no - 1] if 0 < satir_no <= len(satirlar) else []
        return str(satir[sutun]).strip() if sutun < len(satir) else ""

    if R5_IMZA not in metin.tr_buyuk(hucre(1, 0)) and R5_IMZA not in hucre(1, 0):
        raise ValueError("Bu dosya Kelebek Sınav'ın Toplu Dağıtım Çizelgesi değil.")
    basliklar = tuple(hucre(R5_BASLIK_SATIRI, s) for s in range(len(R5_BASLIKLAR)))
    if basliklar != R5_BASLIKLAR:
        raise ValueError("Sütunlar beklenen sırada değil (Kelebek sürümü değişmiş olabilir).")
    kunye = kunye_ayristir(hucre(2, 0))
    uyarilar = []
    if sayfa_adi != R5_SAYFA:
        uyarilar.append(f"Çizelge sayfasının adı '{R5_SAYFA}' değil; dosyanın ilk sayfası okundu.")
    if not kunye["baslangic"]:
        uyarilar.append("Çizelgenin başlığından sınav adı, tarihi ve saati okunamadı; yayına almadan önce künyeyi doldurun.")
    hatalar: list[str] = []
    kayitlar: list[dict] = []
    gorulen_no: dict[str, int] = {}
    gorulen_koltuk: dict[tuple[str, int], int] = {}
    satir_no = R5_BASLIK_SATIRI
    for satir in satirlar[R5_BASLIK_SATIRI:]:
        satir_no += 1
        if not any(str(h).strip() for h in satir):
            break  # boş satıra kadar
        if len(kayitlar) + len(hatalar) >= SATIR_SINIRI:
            raise ValueError(f"Dosyada en çok {SATIR_SINIRI} öğrenci satırı olabilir.")
        okul_no, ad_soyad, sube, ders, salon, koltuk_ham = (hucre(satir_no, s) for s in range(6))
        etiket = f"Satır {satir_no}" + (f" (Okul No {okul_no})" if okul_no and len(okul_no) <= 20 else "")
        sorun = None
        koltuk = 0
        if not okul_no:
            sorun = "okul numarası boş"
        elif len(okul_no) > 20:
            sorun = "okul numarası 20 karakterden uzun"
        elif not ad_soyad:
            sorun = "ad soyad boş"
        elif not sube or len(sube) > 12:
            sorun = "şube boş ya da çok uzun"
        elif not ders or len(ders) > 120:
            sorun = "ders boş ya da 120 karakterden uzun"
        elif not salon or len(salon) > 60:
            sorun = "salon boş ya da 60 karakterden uzun"
        else:
            try:
                koltuk = int(koltuk_ham)
            except ValueError:
                koltuk = 0
            if not 1 <= koltuk <= 999:
                sorun = "koltuk numarası geçersiz"
            elif okul_no in gorulen_no:
                sorun = f"okul numarası satır {gorulen_no[okul_no]}'de de var"
            elif (salon, koltuk) in gorulen_koltuk:
                sorun = f"koltuk numarası bu salonda satır {gorulen_koltuk[(salon, koltuk)]}'de de var"
        if sorun:
            hatalar.append(f"{etiket}: {sorun}.")
            continue
        gorulen_no[okul_no] = satir_no
        gorulen_koltuk[(salon, koltuk)] = satir_no
        kayitlar.append(
            {
                "okul_no": okul_no,
                "maske": maske.kalabalik(ad_soyad),
                "sube": metin.sube_duzelt(sube) or sube,
                "ders": ders,
                "salon": salon,
                "koltuk": koltuk,
            }
        )
        del ad_soyad
    if hatalar:
        raise IceAktarmaHatasi(hatalar[:HATA_GOSTERIM], len(hatalar))
    if not kayitlar:
        raise ValueError("Dosyada öğrenci satırı yok.")
    sayilar: dict[str, int] = {}
    for k in kayitlar:
        sayilar[k["salon"]] = sayilar.get(k["salon"], 0) + 1
    kalabalik = sorted((s for s, n in sayilar.items() if n > SALON_LISTE_SINIRI), key=sirala_anahtari)
    if kalabalik:
        uyarilar.append(
            f"{len(kalabalik)} salonda {SALON_LISTE_SINIRI}'tan fazla öğrenci var ({', '.join(kalabalik[:5])}); "
            f"tahtada ilk {SALON_LISTE_SINIRI} kişi gösterilir, o salonların yoklaması panelden alınır."
        )
    return {**kunye, "kayitlar": kayitlar, "uyarilar": uyarilar}


# ---- eşleştirme ------------------------------------------------------------------------------
def eslesme_onerisi(b, salon_adi: str, kullanilan: set[int] | None = None) -> int | None:
    """(1) hatırlanan eşleşme (tahta onaylıysa); (2) derslik/ad anahtarı birebir ve tek aday."""
    kullanilan = kullanilan or set()
    hafiza = b.execute(
        "SELECT e.tahta_id FROM sinav_eslesme e JOIN tahta t ON t.id = e.tahta_id "
        "WHERE e.tur = 'salon' AND e.ad = ? AND t.durum = 'onayli'",
        (salon_adi,),
    ).fetchone()
    if hafiza:
        return hafiza["tahta_id"] if hafiza["tahta_id"] not in kullanilan else None
    anahtar = metin.derslik_anahtari(salon_adi)
    if not anahtar:
        return None
    adaylar = {
        t["id"]
        for t in b.execute("SELECT id, ad, derslik FROM tahta WHERE durum = 'onayli'")
        if metin.derslik_anahtari(t["derslik"]) == anahtar or metin.derslik_anahtari(t["ad"]) == anahtar
    }
    if len(adaylar) != 1:
        return None
    aday = adaylar.pop()
    return aday if aday not in kullanilan else None


def eslesme_hatirla(b, salon_adi: str, tahta_id: int | None) -> None:
    if tahta_id:
        b.execute(
            "INSERT INTO sinav_eslesme (tur, ad, tahta_id) VALUES ('salon', ?, ?) "
            "ON CONFLICT(tur, ad) DO UPDATE SET tahta_id = excluded.tahta_id",
            (salon_adi, tahta_id),
        )


# ---- içe aktarma -----------------------------------------------------------------------------
def ice_aktar(b, veri: bytes, kullanici: str, an: int, ip: str = "") -> dict:
    """R5'i okur; yeni taslak sınav açar ya da aynı sınavın (ad + başlangıç) listesini yeniler.

    Döndürür: {"sinav_id", "mesaj", "uyarilar", "ayni_dosya": bool}. Hata: ValueError /
    IceAktarmaHatasi (hiçbir şey yazılmaz).
    """
    if len(veri) > DOSYA_SINIRI:
        raise ValueError(f"Dosya en çok {DOSYA_SINIRI // (1024 * 1024)} MB olabilir.")
    ozet = hashlib.sha256(veri).hexdigest()
    ayni = b.execute(
        "SELECT id FROM sinav WHERE kaynak_ozet = ? AND kisisel_silinme IS NULL ORDER BY id DESC", (ozet,)
    ).fetchone()
    if ayni:
        return {"sinav_id": ayni["id"], "mesaj": "Bu dosya zaten aktarılmış.", "uyarilar": [], "ayni_dosya": True}
    sayfa_adi, satirlar = xlsx.oku_ayrintili(veri)
    cozum = r5_ayristir(sayfa_adi, satirlar)
    kayitlar = cozum["kayitlar"]
    salon_adlari = sorted({k["salon"] for k in kayitlar}, key=sirala_anahtari)
    ders_adlari = sorted({k["ders"] for k in kayitlar}, key=metin.tr_sirala_anahtari)
    uyarilar = list(cozum["uyarilar"])
    mevcut = None
    if cozum["baslangic"] and cozum["ad"]:
        mevcut = b.execute(
            "SELECT * FROM sinav WHERE ad = ? AND baslangic = ? AND kisisel_silinme IS NULL ORDER BY id DESC",
            (cozum["ad"], cozum["baslangic"]),
        ).fetchone()
    if mevcut:
        if an >= mevcut["baslangic"] - GIRIS_ONCESI_SN or mevcut["bitirme"]:
            raise ValueError("Sınav başladı; liste değiştirilemez.")
        sinav_id = mevcut["id"]
        sure = mevcut["sure_dk"]
        b.execute("DELETE FROM sinav_ogrenci WHERE sinav_id = ?", (sinav_id,))
        eski_dersler = {s["ad"]: s["id"] for s in b.execute("SELECT id, ad FROM sinav_ders WHERE sinav_id = ?", (sinav_id,))}
        for ad, ders_id in eski_dersler.items():
            if ad not in ders_adlari:
                b.execute("DELETE FROM sinav_ders WHERE id = ?", (ders_id,))
        eski_salonlar = {s["ad"]: s for s in b.execute("SELECT * FROM sinav_salon WHERE sinav_id = ?", (sinav_id,))}
        for ad, s in eski_salonlar.items():
            if ad not in salon_adlari:
                b.execute("DELETE FROM sinav_salon WHERE id = ?", (s["id"],))
        b.execute("UPDATE sinav SET kaynak_ozet = ?, guncelleme = ? WHERE id = ?", (ozet, an, sinav_id))
        islem_adi = "Sınav listesi yenilendi"
        mesaj = f"Liste yenilendi: {len(kayitlar)} öğrenci, {len(salon_adlari)} salon."
    else:
        sinav_id = b.execute(
            "INSERT INTO sinav (ad, baslangic, sure_dk, durum, donem, kaynak_ozet, olusturan, olusturma, guncelleme) "
            "VALUES (?, ?, ?, 'taslak', ?, ?, ?, ?, ?)",
            (cozum["ad"], cozum["baslangic"], VARSAYILAN_SURE_DK, cozum["donem"], ozet, kullanici, an, an),
        ).lastrowid
        sure = VARSAYILAN_SURE_DK
        eski_dersler, eski_salonlar = {}, {}
        islem_adi = "Sınav içe aktarıldı"
        mesaj = f"Sınav taslak olarak açıldı: {len(kayitlar)} öğrenci, {len(salon_adlari)} salon."
        # Tanıma anahtarı ad + başlangıçtır; künyesi panelde değiştirilmiş sınav tanınmaz. Sessizce
        # ikinci sınav açılmasın diye benzer sınav (aynı ad ya da aynı başlangıç) uyarıyla anılır.
        if cozum["baslangic"] or cozum["ad"]:
            benzer = b.execute(
                "SELECT ad, baslangic FROM sinav WHERE id != ? AND kisisel_silinme IS NULL "
                "AND ((? > 0 AND baslangic = ?) OR (? != '' AND ad = ?)) ORDER BY id DESC",
                (sinav_id, cozum["baslangic"] or 0, cozum["baslangic"] or 0, cozum["ad"] or "", cozum["ad"] or ""),
            ).fetchone()
            if benzer:
                uyarilar.append(
                    f"Dikkat: benzer bir sınav zaten var ({benzer['ad'] or 'künye eksik'}"
                    f"{' · ' + tarih_metni(benzer['baslangic']) + ' ' + saat_metni(benzer['baslangic']) if benzer['baslangic'] else ''})."
                    " Künyesi panelde değiştirildiği için o sınavın listesi yenilenmedi; bu dosya yeni taslak olarak açıldı."
                    " Aynı sınavsa eskisini taslağa alıp silin ya da bu taslağı silin."
                )
    ders_idleri = {}
    for ad in ders_adlari:
        if ad in eski_dersler:
            ders_idleri[ad] = eski_dersler[ad]
        else:
            ders_idleri[ad] = b.execute(
                "INSERT INTO sinav_ders (sinav_id, ad, sure_dk) VALUES (?, ?, ?)", (sinav_id, ad, sure)
            ).lastrowid
    salon_idleri = {}
    kullanilan_tahta = {s["tahta_id"] for ad, s in eski_salonlar.items() if ad in salon_adlari and s["tahta_id"]}
    kodlar = {s["gozetmen_kodu"] for ad, s in eski_salonlar.items() if ad in salon_adlari}
    yayinda = bool(mevcut) and mevcut["durum"] == "yayinda"
    yeni_salon = 0
    for ad in salon_adlari:
        if ad in eski_salonlar:
            salon_idleri[ad] = eski_salonlar[ad]["id"]
            continue
        # Yayındaki sınava eklenen salona tahta önerilmez: öneri, zamanı çakışan başka bir
        # yayımlanmış sınavın tahtası olabilir (yayına alma/eşleme denetimi bu yolu görmez).
        oneri = None if yayinda else eslesme_onerisi(b, ad, kullanilan_tahta)
        yeni_salon += 1
        if oneri:
            kullanilan_tahta.add(oneri)
        kod = kod_uret(kodlar)
        kodlar.add(kod)
        salon_idleri[ad] = b.execute(
            "INSERT INTO sinav_salon (sinav_id, ad, tahta_id, gozetmen_kodu) VALUES (?, ?, ?, ?)",
            (sinav_id, ad, oneri, kod),
        ).lastrowid
    b.executemany(
        "INSERT INTO sinav_ogrenci (sinav_id, salon_id, ders_id, koltuk, okul_no, sube, maske) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (sinav_id, salon_idleri[k["salon"]], ders_idleri[k["ders"]], k["koltuk"], k["okul_no"], k["sube"], k["maske"])
            for k in kayitlar
        ],
    )
    vt.kayit_dus(
        b,
        kullanici,
        islem_adi,
        f"{cozum['ad'] or 'Künyesiz sınav'} · {len(kayitlar)} öğrenci, {len(salon_adlari)} salon, {len(ders_adlari)} ders",
        ip,
    )
    if yayinda and yeni_salon:
        uyarilar.append(f"Listeye {yeni_salon} yeni salon eklendi; tahtalarını sınav sayfasında eşleyin.")
    return {"sinav_id": sinav_id, "mesaj": mesaj, "uyarilar": uyarilar, "ayni_dosya": False}


# ---- zaman hesapları ---------------------------------------------------------------------------
def zamanlar(b, sinav) -> dict:
    """{"salon_bitis": {salon_id: epoch}, "salon_dersler": {salon_id: [{"id","ad","sure_dk","bitis"}]},
    "bitis": en geç salon bitişi (0 = künye eksik)}. Karma salonda bitiş en uzun dersin bitişi + uzatma."""
    bas = int(sinav["baslangic"] or 0)
    dersler = {s["id"]: s for s in b.execute("SELECT * FROM sinav_ders WHERE sinav_id = ?", (sinav["id"],))}
    salon_ders: dict[int, set[int]] = {}
    for s in b.execute("SELECT DISTINCT salon_id, ders_id FROM sinav_ogrenci WHERE sinav_id = ?", (sinav["id"],)):
        salon_ders.setdefault(s["salon_id"], set()).add(s["ders_id"])
    sonuc_bitis: dict[int, int] = {}
    sonuc_ders: dict[int, list[dict]] = {}
    for salon in b.execute("SELECT id, uzatma_dk FROM sinav_salon WHERE sinav_id = ?", (sinav["id"],)):
        idler = salon_ders.get(salon["id"]) or set(dersler)  # kişisel veri silindiyse bütün dersler
        uzatma = int(salon["uzatma_dk"] or 0) * 60
        liste = []
        for ders_id in sorted(idler, key=lambda i: metin.tr_sirala_anahtari(dersler[i]["ad"]) if i in dersler else ()):
            if ders_id not in dersler:
                continue
            bitis = bas + int(dersler[ders_id]["sure_dk"]) * 60 + uzatma
            if sinav["bitirme"]:
                bitis = min(bitis, int(sinav["bitirme"]))
            liste.append({"id": ders_id, "ad": dersler[ders_id]["ad"], "sure_dk": dersler[ders_id]["sure_dk"], "bitis": bitis})
        if liste:
            bitis = max(d["bitis"] for d in liste)
        else:
            bitis = bas + int(sinav["sure_dk"]) * 60 + uzatma
            if sinav["bitirme"]:
                bitis = min(bitis, int(sinav["bitirme"]))
        sonuc_bitis[salon["id"]] = bitis if bas else 0
        sonuc_ders[salon["id"]] = liste
    return {
        "salon_bitis": sonuc_bitis,
        "salon_dersler": sonuc_ders,
        "bitis": max(sonuc_bitis.values(), default=bas + int(sinav["sure_dk"]) * 60) if bas else 0,
    }


def sinav_evresi(sinav, bitis: int, an: int) -> str:
    if sinav["kisisel_silinme"]:
        return "silindi"
    if sinav["durum"] != "yayinda" or not sinav["baslangic"]:
        return "taslak"
    if an >= bitis:
        return "bitti"
    if an < sinav["baslangic"] - GIRIS_ONCESI_SN:
        return "yayinda"
    if an < sinav["baslangic"]:
        return "giris"
    return "suruyor"


def salon_evresi(sinav, salon, bitis: int, an: int) -> str:
    evre = sinav_evresi(sinav, bitis, an)
    if evre in ("giris", "suruyor", "yayinda") and salon["kip_kapanma"]:
        return "kaldirildi"
    return evre


def giris_oncesi_mi(sinav, an: int) -> bool:
    """Künye/eşleşme/kod düzenlenebilir mi: giriş penceresi henüz başlamadı (ya da künye eksik)."""
    return not sinav["baslangic"] or (an < int(sinav["baslangic"]) - GIRIS_ONCESI_SN and not sinav["bitirme"])


# ---- tahta penceresi -------------------------------------------------------------------------
def aktif_salonlar(b, an: int, on_pay: int = 0) -> list[dict]:
    """Şu an penceresinde olan (yayında, kip kaldırılmamış, kişisel veri silinmemiş) eşli salonlar.

    on_pay: pencerenin başına eklenen saniye (program kilidi engeli için). Her öğe:
    {"sinav", "salon", "bitis", "dersler"}.
    """
    adaylar = b.execute(
        "SELECT s.id AS sinav_id, sl.id AS salon_id FROM sinav s JOIN sinav_salon sl ON sl.sinav_id = s.id "
        "JOIN tahta t ON t.id = sl.tahta_id "
        "WHERE s.durum = 'yayinda' AND s.kisisel_silinme IS NULL AND s.baslangic > 0 AND sl.kip_kapanma IS NULL "
        "AND t.durum = 'onayli' AND s.baslangic <= ? AND s.baslangic >= ?",
        (an + GIRIS_ONCESI_SN + on_pay, an - EN_UZUN_SN - 60),
    ).fetchall()
    sonuc = []
    onbellek: dict[int, tuple] = {}
    for a in adaylar:
        if a["sinav_id"] not in onbellek:
            sinav = b.execute("SELECT * FROM sinav WHERE id = ?", (a["sinav_id"],)).fetchone()
            onbellek[a["sinav_id"]] = (sinav, zamanlar(b, sinav))
        sinav, z = onbellek[a["sinav_id"]]
        bitis = z["salon_bitis"].get(a["salon_id"], 0)
        if sinav["baslangic"] - GIRIS_ONCESI_SN - on_pay <= an < bitis:
            salon = b.execute("SELECT * FROM sinav_salon WHERE id = ?", (a["salon_id"],)).fetchone()
            sonuc.append({"sinav": sinav, "salon": salon, "bitis": bitis, "dersler": z["salon_dersler"].get(salon["id"], [])})
    sonuc.sort(key=lambda x: (x["sinav"]["baslangic"], x["salon"]["id"]))
    return sonuc


def pencere_haritasi(b, an: int) -> dict[int, dict]:
    """tahta_id → {"sinav_id","salon_id","sinav_adi","salon_adi","evre": "giris"|"suruyor","bitis_saat"}.

    Pano kartı ve /api/durum `t.sinav` alanı (sunucunun hesabı; ajan sürümünden bağımsız).
    """
    sonuc: dict[int, dict] = {}
    for a in aktif_salonlar(b, an):
        tahta_id = a["salon"]["tahta_id"]
        if tahta_id in sonuc:
            continue
        sonuc[tahta_id] = {
            "sinav_id": a["sinav"]["id"],
            "salon_id": a["salon"]["id"],
            "sinav_adi": a["sinav"]["ad"],
            "salon_adi": a["salon"]["ad"],
            "evre": "giris" if an < a["sinav"]["baslangic"] else "suruyor",
            "bitis_saat": saat_metni(a["bitis"]),
        }
    return sonuc


_PENCERE_ONBELLEK: list = [None, None]  # [(b, an, on_pay), küme]: zamanlayıcı turunda tahta başına sorgu olmasın


def pencere_tahtalari(b, an: int, on_pay: int = 0) -> set[int]:
    """Şu an sınav penceresinde (on_pay kadar erken başlatılmış) olan eşli tahtalar."""
    anahtar = _PENCERE_ONBELLEK[0]
    if anahtar and anahtar[0] is b and anahtar[1:] == (an, on_pay):
        return _PENCERE_ONBELLEK[1]
    kume = {a["salon"]["tahta_id"] for a in aktif_salonlar(b, an, on_pay)}
    _PENCERE_ONBELLEK[:] = [(b, an, on_pay), kume]
    return kume


def tahta_sinav_penceresinde(b, tahta_id: int, an: int, on_pay: int = 0) -> bool:
    """Ortak sözlük §2.2: otomatik kapatma ve program işi bu tahtayı atlar mı."""
    return tahta_id in pencere_tahtalari(b, an, on_pay)


def kimlik_metni(sinav_id: int, salon_id: int) -> str:
    return f"sinav-{sinav_id}-salon-{salon_id}"


def salon_listesi(b, salon_id: int, sinir: int | None = SALON_LISTE_SINIRI) -> tuple[list[dict], int]:
    """Tahtaya giden maskeli liste (koltuk sırasıyla) ve sığmayan kişi sayısı.

    Öğe: {"k": koltuk, "a": maske, "n": okul no son 2 hane, "s": şube}. Tam no ve ders YOK.
    """
    satirlar = b.execute(
        "SELECT koltuk, maske, okul_no, sube FROM sinav_ogrenci WHERE salon_id = ? ORDER BY koltuk", (salon_id,)
    ).fetchall()
    liste = [{"k": s["koltuk"], "a": s["maske"], "n": maske.no_son(s["okul_no"]), "s": s["sube"]} for s in satirlar]
    if sinir is None or len(liste) <= sinir:
        return liste, 0
    return liste[:sinir], len(liste) - sinir


def tahta_sinavi(b, tahta_id: int, an: int) -> dict | None:
    """`ayar.sinav` (§5.1): pencere dışında None. `liste` yalnız giriş evresinde (basla_sn > 0)."""
    for a in aktif_salonlar(b, an):
        if a["salon"]["tahta_id"] != tahta_id:
            continue
        sinav, salon = a["sinav"], a["salon"]
        basla_sn = int(sinav["baslangic"]) - an
        veri = {
            "kimlik": kimlik_metni(sinav["id"], salon["id"]),
            "salon": salon["id"],
            "sinav_adi": sinav["ad"],
            "salon_adi": salon["ad"],
            "basla_sn": basla_sn,
            "bitis_sn": a["bitis"] - an,
            "baslangic_saat": saat_metni(sinav["baslangic"]),
            "bitis_saat": saat_metni(a["bitis"]),
            "dersler": [{"ad": d["ad"], "bitis_saat": saat_metni(d["bitis"])} for d in a["dersler"]],
            "kurallar": kurallar(b),
            "yoklama_alindi": salon["yoklama_zamani"] is not None,
        }
        if basla_sn > 0:
            veri["liste"], veri["liste_fazla"] = salon_listesi(b, salon["id"])
        return veri
    return None


# ---- gözetmen kodu ve tahtadan yoklama --------------------------------------------------------
class GozetmenKapisi:
    """Gözetmen kodu denemeleri ve belirteçler (yalnız bellekte; sunucu yeniden başlarsa kod yeniden girilir).

    Belirteç sunucuda yalnız özetiyle durur: {özet: (tahta_id, salon_id, bitiş epoch)}.
    """

    def __init__(self):
        self.hatalar: dict[int, list[int]] = {}
        self.bekleme: dict[int, int] = {}
        self.belirtecler: dict[str, tuple[int, int, int]] = {}

    def bekleme_kalan(self, tahta_id: int, an: int) -> int:
        return max(0, self.bekleme.get(tahta_id, 0) - an)

    def hata_say(self, tahta_id: int, an: int) -> tuple[int, int]:
        """Hatalı denemeyi sayar. Döndürür: (kalan deneme, bekleme sn — 0 ise bekleme yok)."""
        liste = [z for z in self.hatalar.get(tahta_id, []) if an - z < KOD_PENCERE_SN] + [an]
        if len(liste) >= KOD_DENEME:
            self.hatalar[tahta_id] = []
            self.bekleme[tahta_id] = an + KOD_BEKLEME_SN
            return 0, KOD_BEKLEME_SN
        self.hatalar[tahta_id] = liste
        return KOD_DENEME - len(liste), 0

    def belirtec_ver(self, tahta_id: int, salon_id: int, an: int) -> str:
        self.belirtecler = {o: d for o, d in self.belirtecler.items() if d[2] > an}
        belirtec = secrets.token_urlsafe(32)
        self.belirtecler[hashlib.sha256(belirtec.encode()).hexdigest()] = (tahta_id, salon_id, an + GOZETMEN_OTURUM_SN)
        return belirtec

    def belirtec_coz(self, belirtec: str, tahta_id: int, an: int) -> int | None:
        """Geçerli ve bu tahtanınsa salon kimliği; değilse None."""
        if not isinstance(belirtec, str) or not belirtec:
            return None
        kayit = self.belirtecler.get(hashlib.sha256(belirtec.encode()).hexdigest())
        if not kayit or kayit[0] != tahta_id or kayit[2] <= an:
            return None
        return kayit[1]

    def salon_belirtecleri_dusur(self, salon_idler) -> None:
        idler = set(salon_idler)
        self.belirtecler = {o: d for o, d in self.belirtecler.items() if d[1] not in idler}


def gecerli_salon(b, tahta_id: int, salon_id, an: int):
    """Tahtadan iş için salon: bu tahtaya eşli ve şu an penceresinde. (sinav, salon, bitis) ya da None."""
    if not isinstance(salon_id, int) or isinstance(salon_id, bool):
        return None
    for a in aktif_salonlar(b, an):
        if a["salon"]["id"] == salon_id and a["salon"]["tahta_id"] == tahta_id:
            return a["sinav"], a["salon"], a["bitis"]
    return None


def gozetmen_verisi(b, sinav, salon, an: int) -> dict:
    """Kod doğrulanınca ve yoklamadan sonra tahtaya giden salon verisi (belirteç hariç)."""
    liste, fazla = salon_listesi(b, salon["id"])
    gelmeyen = [s["koltuk"] for s in b.execute(
        "SELECT koltuk FROM sinav_ogrenci WHERE salon_id = ? AND gelmedi = 1 ORDER BY koltuk", (salon["id"],))]  # fmt: skip
    return {
        "salon": salon["id"],
        "liste": liste,
        "liste_fazla": fazla,
        "gelmeyen": gelmeyen,
        "basladi": an >= int(sinav["baslangic"]),
        "tahtadan_yoklama": fazla == 0,
    }


def yoklama_yaz(b, salon, gelmeyen, isaretleyen: str, kaynak: str, an: int) -> tuple[int, int]:
    """Salonun bütün satırlarını yazar (listede olan gelmedi=1, olmayan 0). Döndürür: (gelmeyen, mevcut).

    Salonda olmayan koltuk ya da sayı olmayan değer varsa ValueError; hiçbir şey yazılmaz.
    """
    koltuklar = {s["koltuk"] for s in b.execute("SELECT koltuk FROM sinav_ogrenci WHERE salon_id = ?", (salon["id"],))}
    secilen: set[int] = set()
    for k in gelmeyen or []:
        if isinstance(k, bool) or not str(k).strip().isdigit() or len(str(k).strip()) > 4:
            raise ValueError("Koltuk numarası geçersiz.")
        secilen.add(int(str(k).strip()))
    disarida = sorted(secilen - koltuklar)
    if disarida:
        raise ValueError(f"Bu salonda olmayan koltuk: {', '.join(map(str, disarida[:10]))}.")
    b.execute("UPDATE sinav_ogrenci SET gelmedi = 0, isaretleyen = ?, isaret_zamani = ? WHERE salon_id = ?",
              (isaretleyen, an, salon["id"]))  # fmt: skip
    if secilen:
        isaret = ",".join("?" * len(secilen))
        b.execute(
            f"UPDATE sinav_ogrenci SET gelmedi = 1 WHERE salon_id = ? AND koltuk IN ({isaret})", (salon["id"], *sorted(secilen))
        )
    b.execute("UPDATE sinav_salon SET yoklama_zamani = ?, yoklama_kaynak = ? WHERE id = ?", (an, kaynak, salon["id"]))
    return len(secilen), len(koltuklar)


def yoklama_kayit_metni(salon_adi: str, gelmeyen: list[int]) -> str:
    """İşlem kaydı ayrıntısı: salon adı, sayı ve koltuk numaraları (ad, maske, okul no YOK)."""
    if not gelmeyen:
        return f"{salon_adi}: herkes geldi"
    koltuklar = ", ".join(str(k) for k in sorted(gelmeyen)[:60])
    return f"{salon_adi}: {len(gelmeyen)} gelmedi (koltuk {koltuklar})"


# ---- yayın, çakışma ----------------------------------------------------------------------------
def cakisan_sinav(b, sinav, eslesmeler: dict[int, int | None]) -> str | None:
    """Aynı tahta zaman aralığı örtüşen başka yayımlanmış sınavda mı? Çakışan sınavın adı ya da None.

    eslesmeler: salon_id → tahta_id (bu sınavın yeni/olası eşleşmeleri). Aralık [b − 10 dk, bitiş].
    """
    if not sinav["baslangic"]:
        return None
    z = zamanlar(b, sinav)
    bu = {}
    for salon_id, tahta_id in eslesmeler.items():
        if tahta_id:
            bu.setdefault(tahta_id, []).append((int(sinav["baslangic"]) - GIRIS_ONCESI_SN, z["salon_bitis"].get(salon_id, 0)))
    if not bu:
        return None
    isaret = ",".join("?" * len(bu))
    digerleri = b.execute(
        "SELECT DISTINCT s.* FROM sinav s JOIN sinav_salon sl ON sl.sinav_id = s.id "
        f"WHERE s.durum = 'yayinda' AND s.kisisel_silinme IS NULL AND s.id != ? AND s.baslangic > 0 AND sl.tahta_id IN ({isaret})",
        (sinav["id"], *bu),
    ).fetchall()
    for diger in digerleri:
        dz = zamanlar(b, diger)
        for sl in b.execute(
            f"SELECT id, tahta_id, kip_kapanma FROM sinav_salon WHERE sinav_id = ? AND tahta_id IN ({isaret})", (diger["id"], *bu)
        ):
            if sl["kip_kapanma"]:
                continue  # o salonda sınav kipi kaldırıldı: tahta artık o sınava bağlı değil
            d_bas, d_bit = int(diger["baslangic"]) - GIRIS_ONCESI_SN, dz["salon_bitis"].get(sl["id"], 0)
            for bas, bit in bu[sl["tahta_id"]]:
                if bas <= d_bit and d_bas <= bit:
                    return diger["ad"]
    return None


def yetersiz_tahtalar(b, sinav_id: int) -> list[str]:
    """Eşli olup `sinav` yeteneğini bildirmeyen tahtaların adları ("Ajan güncellenmeli")."""
    return [
        t["ad"]
        for t in b.execute(
            "SELECT DISTINCT t.* FROM tahta t JOIN sinav_salon sl ON sl.tahta_id = t.id WHERE sl.sinav_id = ?", (sinav_id,)
        )
        if SINAV_YETENEGI not in acil.yetenekler(t)
    ]


def eslesmis_tahtalar(b, sinav_id: int) -> list[int]:
    return [s["tahta_id"] for s in b.execute(
        "SELECT DISTINCT tahta_id FROM sinav_salon WHERE sinav_id = ? AND tahta_id IS NOT NULL", (sinav_id,))]  # fmt: skip


def yayina_al_denetimi(b, sinav, an: int) -> list[str]:
    """Yayına alma koşulları; ValueError ile reddeder, uyarı listesi döndürür."""
    if sinav["kisisel_silinme"]:
        raise ValueError("Kişisel verisi silinmiş sınav yayına alınamaz.")
    if not sinav["ad"].strip() or not sinav["baslangic"]:
        raise ValueError("Künye eksik: sınav adı, tarihi ve saati girilmeli.")
    sureler = [s["sure_dk"] for s in b.execute("SELECT sure_dk FROM sinav_ders WHERE sinav_id = ?", (sinav["id"],))]
    if not SURE_ARALIGI[0] <= sinav["sure_dk"] <= SURE_ARALIGI[1] or any(
        not SURE_ARALIGI[0] <= s <= SURE_ARALIGI[1] for s in sureler
    ):
        raise ValueError(f"Süreler {SURE_ARALIGI[0]}–{SURE_ARALIGI[1]} dakika arasında olmalı.")
    if zamanlar(b, sinav)["bitis"] <= an:
        raise ValueError("Sınavın bitiş saati geçmiş; künyeyi düzeltin.")
    eslesmeler = {s["id"]: s["tahta_id"] for s in b.execute("SELECT id, tahta_id FROM sinav_salon WHERE sinav_id = ?", (sinav["id"],))}
    cakisan = cakisan_sinav(b, sinav, eslesmeler)
    if cakisan:
        raise ValueError(f"Aynı tahta, zamanı çakışan başka bir yayımlanmış sınavda: {cakisan}.")
    uyarilar = []
    if not any(eslesmeler.values()):
        uyarilar.append("Hiçbir salon bir tahtaya eşlenmedi; tahtalarda sınav ekranı açılmayacak.")
    eski = yetersiz_tahtalar(b, sinav["id"])
    if eski:
        uyarilar.append(f"{len(eski)} tahtada ajan güncellenmeli; bu tahtalarda sınav ekranı açılmaz ({', '.join(eski[:5])}).")
    return uyarilar


# ---- kişisel veri silme ve saklama ------------------------------------------------------------
def kisisel_veri_sil(b, sinav_id: int, kullanici: str, islem_adi: str, an: int, ip: str = "") -> None:
    """Salon özetlerini yazar, öğrenci satırlarını siler, kodları ve gözetmen adlarını boşaltır,
    bu sınavın şube duyurusu komutlarının verisini boşaltır. Çağıran işlemden sonra vt.wal_buda()."""
    sinav = b.execute("SELECT * FROM sinav WHERE id = ?", (sinav_id,)).fetchone()
    if not sinav or sinav["kisisel_silinme"]:
        return
    b.execute(
        "UPDATE sinav_salon SET ozet_mevcut = (SELECT COUNT(*) FROM sinav_ogrenci o WHERE o.salon_id = sinav_salon.id), "
        "ozet_gelmeyen = (SELECT COUNT(*) FROM sinav_ogrenci o WHERE o.salon_id = sinav_salon.id AND o.gelmedi = 1), "
        "gozetmen_kodu = '', gozetmen_adi = '' WHERE sinav_id = ?",
        (sinav_id,),
    )
    b.execute("DELETE FROM sinav_ogrenci WHERE sinav_id = ?", (sinav_id,))
    duyuru_verisini_sil(b, sinav_id)
    b.execute("UPDATE sinav SET kisisel_silinme = ?, guncelleme = ? WHERE id = ?", (an, an, sinav_id))
    vt.kayit_dus(b, kullanici, islem_adi, sinav["ad"] or f"Sınav #{sinav_id}", ip)


def duyuru_verisini_sil(b, sinav_id: int) -> None:
    b.execute(
        "UPDATE komut SET veri_json = '{}' WHERE duyuru_id IN (SELECT id FROM duyuru WHERE sinav_id = ?)", (sinav_id,)
    )


def sinav_sil(b, sinav_id: int, kullanici: str, an: int, ip: str = "") -> None:
    sinav = b.execute("SELECT * FROM sinav WHERE id = ?", (sinav_id,)).fetchone()
    if not sinav:
        return
    duyuru_verisini_sil(b, sinav_id)
    b.execute("DELETE FROM sinav WHERE id = ?", (sinav_id,))  # ders, salon, öğrenci: ON DELETE CASCADE
    vt.kayit_dus(b, kullanici, "Sınav silindi", sinav["ad"] or f"Sınav #{sinav_id}", ip)


def saklama_temizligi(b, an: int) -> list[int]:
    """Saklama süresi (SAKLAMA_GUN) dolan sınavların kişisel verisini siler; silinen sınavlar."""
    sinir = an - SAKLAMA_GUN * 86400
    idler = [
        s["id"]
        for s in b.execute(
            "SELECT id FROM sinav WHERE kisisel_silinme IS NULL AND (CASE WHEN baslangic > 0 THEN baslangic ELSE olusturma END) < ?",
            (sinir,),
        )
    ]
    for sinav_id in idler:
        kisisel_veri_sil(b, sinav_id, "sistem", "Sınav kişisel verisi saklama süresi dolduğu için silindi", an)
    return idler


def silinme_tarihi(sinav) -> str:
    """Kişisel verinin kendiliğinden silineceği tarih (gg.aa.yyyy)."""
    dayanak = sinav["baslangic"] or sinav["olusturma"]
    return tarih_metni(int(dayanak) + SAKLAMA_GUN * 86400 + 1) if dayanak else ""


# ---- şube duyurusu --------------------------------------------------------------------------
def sube_duyurusu_suresi(sinav, sure_dk: int, an: int) -> int:
    """Duyuru süresi (sn), sınav başlangıcına kırpılır: liste sınav sürerken görünmez (M3). ≤0: gönderilemez."""
    sure_sn = sure_dk * 60
    if sinav["baslangic"]:
        sure_sn = min(sure_sn, int(sinav["baslangic"]) - an)
    return sure_sn


def sube_duyurusu(b, sinav, sure_dk: int, kullanici: str, an: int, ip: str = "") -> tuple[int, int, list[int]]:
    """Her şubeye (tahta.subeler'inde şubeyi taşıyan onaylı tahtalara) bir duyuru.

    duyuru.metin'e özet ("Sınav oturma listesi · 11/A"), komut verisine maskeli liste yazılır.
    Süre sınav başlangıcına kırpılır (sube_duyurusu_suresi); çağıran ≤0 durumunu önceden reddeder.
    Döndürür: (gönderilen şube, tahtası olmayan şube, uyandırılacak tahtalar).
    """
    salon_adlari = {s["id"]: s["ad"] for s in b.execute("SELECT id, ad FROM sinav_salon WHERE sinav_id = ?", (sinav["id"],))}
    subeler: dict[str, list] = {}
    for s in b.execute("SELECT * FROM sinav_ogrenci WHERE sinav_id = ?", (sinav["id"],)):
        subeler.setdefault(s["sube"], []).append(s)
    tahtalar = b.execute("SELECT id, subeler FROM tahta WHERE durum = 'onayli'").fetchall()
    gonderilen, tahtasiz, uyandir = 0, 0, set()
    baslik = f"{sinav['ad']} · {tarih_metni(sinav['baslangic'])} {saat_metni(sinav['baslangic'])}".strip(" ·")
    for sube in sorted(subeler, key=sirala_anahtari):
        hedefler = [t["id"] for t in tahtalar if sube in [x.strip() for x in (t["subeler"] or "").split(",")]]
        if not hedefler:
            tahtasiz += 1
            continue
        ogrenciler = sorted(subeler[sube], key=lambda o: (metin.tr_sirala_anahtari(o["maske"]), o["koltuk"]))
        satirlar = [f"{o['maske']}  …{maske.no_son(o['okul_no'])}  →  {salon_adlari.get(o['salon_id'], '')}, koltuk {o['koltuk']}"
                    for o in ogrenciler]  # fmt: skip
        ozet = f"Sınav oturma listesi · {sube}"
        _, idler = duyuru_mod.duyuru_yayimla(
            b,
            baslik=baslik[:200],
            metin=ozet,
            komut_metni=ozet + "\n\n" + "\n".join(satirlar),
            sure_sn=max(1, sube_duyurusu_suresi(sinav, sure_dk, an)),
            kapatilabilir=True,
            hedef={"tahtalar": hedefler},
            olusturan=kullanici,
            an=an,
            simdi=an,
            ip=ip,
            kayit_ayrintisi=f"Sınav şube duyurusu · {sube}",
            sinav_id=sinav["id"],
        )
        gonderilen += 1
        uyandir.update(idler)
    vt.kayit_dus(
        b, kullanici, "Sınav şube duyurusu", f"{sinav['ad']} · {gonderilen} şubeye gönderildi, {tahtasiz} şubenin tahtası yok", ip
    )
    return gonderilen, tahtasiz, sorted(uyandir)


# ---- görünümler (panel) -------------------------------------------------------------------------
def liste_ozeti(b, an: int) -> tuple[list[dict], list[dict]]:
    """Sınavlar sayfası: (gelecek ve bugünkü, geçmiş en çok 50)."""
    bugun_basi = int(datetime.fromtimestamp(an, ISTANBUL).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    yaklasan, gecmis = [], []
    for s in b.execute("SELECT * FROM sinav ORDER BY baslangic DESC, id DESC").fetchall():
        z = zamanlar(b, s)
        ogrenci = b.execute("SELECT COUNT(*) FROM sinav_ogrenci WHERE sinav_id = ?", (s["id"],)).fetchone()[0]
        if s["kisisel_silinme"]:
            ogrenci = b.execute("SELECT COALESCE(SUM(ozet_mevcut), 0) FROM sinav_salon WHERE sinav_id = ?", (s["id"],)).fetchone()[0]
        evre = sinav_evresi(s, z["bitis"], an)
        oge = {
            "id": s["id"],
            "ad": s["ad"] or "(künye eksik)",
            "tarih": tarih_metni(s["baslangic"]) or "—",
            "saat": saat_metni(s["baslangic"]) or "—",
            "salon_sayisi": len(z["salon_bitis"]),
            "ogrenci_sayisi": ogrenci,
            "evre": evre,
            "evre_adi": EVRE_ADI[evre],
        }
        if not s["baslangic"] or s["baslangic"] >= bugun_basi or evre in ("giris", "suruyor"):
            yaklasan.append(oge)
        elif len(gecmis) < 50:
            gecmis.append(oge)
    yaklasan.reverse()  # en yakın sınav üstte
    return yaklasan, gecmis


def tahta_durum_ozeti(tahta, sinav_id: int, salon_id: int, an_esik: int) -> dict:
    """Canlı durum için tahtanın bildirdiği sınav evresi (yalnız bu salonun kimliğiyle eşleşirse)."""
    try:
        durum = json.loads(tahta["durum_json"] or "{}")
    except ValueError:
        durum = {}
    cevrimici = bool(tahta["son_gorulme"]) and tahta["son_gorulme"] >= an_esik
    bildirilen = durum.get("sinav") if isinstance(durum.get("sinav"), dict) else None
    ekran = None
    # Tahtadan (çevrimdışıyken, kural 3) kapatılmış sınav ekranı "ekranda" sayılmaz.
    if cevrimici and bildirilen and bildirilen.get("kimlik") == kimlik_metni(sinav_id, salon_id) and not bildirilen.get("yerel_kapali"):
        ekran = bildirilen.get("evre") if bildirilen.get("evre") in EKRAN_EVRE_ADI else None
        if not acil.ekran_var(durum):
            ekran = None
    return {"cevrimici": cevrimici, "ekran": ekran, "ekran_metni": EKRAN_EVRE_ADI.get(ekran, "Ekranda değil")}


def icmal_verisi(b, sinav) -> dict:
    """Sınav Yoklama İcmali: salon özeti + gelmeyenler (şube, sonra okul no sırasıyla)."""
    z = zamanlar(b, sinav)
    salonlar = []
    toplam = {"mevcut": 0, "gelen": 0, "gelmeyen": 0}
    silindi = bool(sinav["kisisel_silinme"])
    salon_satirlari = sorted(b.execute("SELECT * FROM sinav_salon WHERE sinav_id = ?", (sinav["id"],)).fetchall(),
                             key=lambda s: sirala_anahtari(s["ad"]))  # fmt: skip
    for sl in salon_satirlari:
        if silindi:
            mevcut, gelmeyen = sl["ozet_mevcut"] or 0, sl["ozet_gelmeyen"] or 0
        else:
            mevcut = b.execute("SELECT COUNT(*) FROM sinav_ogrenci WHERE salon_id = ?", (sl["id"],)).fetchone()[0]
            gelmeyen = b.execute("SELECT COUNT(*) FROM sinav_ogrenci WHERE salon_id = ? AND gelmedi = 1", (sl["id"],)).fetchone()[0]
        alindi = sl["yoklama_zamani"] is not None
        salonlar.append(
            {
                "id": sl["id"],
                "ad": sl["ad"],
                "gozetmen": sl["gozetmen_adi"],
                "mevcut": mevcut,
                "gelen": mevcut - gelmeyen if alindi else None,
                "gelmeyen": gelmeyen if alindi else None,
                "yoklama_alindi": alindi,
                "yoklama": f"{kaynak_metni(sl['yoklama_kaynak'])} · {saat_metni(sl['yoklama_zamani'])}" if alindi else "ALINMADI",
                "bitis_saat": saat_metni(z["salon_bitis"].get(sl["id"])),
            }
        )
        toplam["mevcut"] += mevcut
        if alindi:
            toplam["gelen"] += mevcut - gelmeyen
            toplam["gelmeyen"] += gelmeyen
    gelmeyenler = []
    if not silindi:
        adlar = {s["id"]: s["ad"] for s in salon_satirlari}
        dersler = {s["id"]: s["ad"] for s in b.execute("SELECT id, ad FROM sinav_ders WHERE sinav_id = ?", (sinav["id"],))}
        for o in b.execute("SELECT * FROM sinav_ogrenci WHERE sinav_id = ? AND gelmedi = 1", (sinav["id"],)):
            gelmeyenler.append(
                {"sube": o["sube"], "okul_no": o["okul_no"], "maske": o["maske"], "ders": dersler.get(o["ders_id"], ""),
                 "salon": adlar.get(o["salon_id"], ""), "koltuk": o["koltuk"]}  # fmt: skip
            )
        gelmeyenler.sort(key=lambda g: (sirala_anahtari(g["sube"]), no_anahtari(g["okul_no"])))
    return {
        "salonlar": salonlar,
        "toplam": toplam,
        "alinmayan": sum(1 for s in salonlar if not s["yoklama_alindi"]),
        "gelmeyenler": gelmeyenler,
        "silindi": silindi,
        "silinme": tarih_metni(sinav["kisisel_silinme"]) if silindi else "",
        "baslangic_saat": saat_metni(sinav["baslangic"]),
        "bitis_saat": saat_metni(z["bitis"]),
        "tarih": tarih_metni(sinav["baslangic"]),
    }


def kaynak_metni(kaynak: str) -> str:
    """"tahta:10/B Tahtası" → "Tahta (10/B Tahtası)", "panel:ayse" → "Panel (ayse)"."""
    tur, _, ad = str(kaynak or "").partition(":")
    if tur == "tahta":
        return f"Tahta ({ad})"
    if tur == "panel":
        return f"Panel ({ad})"
    return kaynak or ""


def tarih_saat_coz(tarih: str, saat: str) -> int:
    """Künye formu: tarih gg.aa.yyyy (ya da YYYY-AA-GG), saat SS:DD → epoch; hatalıysa ValueError."""
    from . import zamanlama

    gun = zamanlama.tarih_coz(tarih, "Sınav tarihini girin.")
    s = zamanlama.saat_coz(saat, "Sınav saatini girin.")
    return zamanlama.an_hesapla(gun, s)


# ---- zamanlayıcı -------------------------------------------------------------------------------
class SinavZamanlayici:
    """Ortak sözlük §2.3 listesinde 5. iş ("sinav_saklama"): saklama temizliği ve evre geçişlerinde
    (pencere açıldı, sınav başladı, bitti) eşli tahtaları uyandırma — ajan 25 sn beklemeden görsün."""

    def __init__(self):
        self.onceki: dict[int, tuple[str, str]] = {}

    def calistir(self, b, an: int) -> tuple[list[int], bool]:
        silinen = saklama_temizligi(b, an)
        simdiki = {t: (f"{v['sinav_id']}-{v['salon_id']}", v["evre"]) for t, v in pencere_haritasi(b, an).items()}
        degisen = {t for t in set(simdiki) | set(self.onceki) if simdiki.get(t) != self.onceki.get(t)}
        self.onceki = simdiki
        return sorted(degisen), bool(silinen)


def hmac_esit(a: str, b_: str) -> bool:
    return hmac.compare_digest(str(a).encode(), str(b_).encode())
