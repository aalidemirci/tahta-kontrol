"""Ders yoklaması (Aşama 5): iş mantığı (FastAPI'siz; testle sınanır).

Güven modeli: öğretmen kod (3 hane, gizli değil) + PIN (6 hane) ile yalnız yoklama için kimlik
kanıtlar; PIN yalnız sunucuda scrypt özetiyle durur, tahtaya ne PIN ne özeti gider. Belirteç
sunucuda `guvenlik.ozet` ile saklanır, tahtada yalnız yönetici yetkili serviste durur.
Öğrenci verisi tahtaya yalnız PIN sonrası, yalnız seçilen şube için `maske.sinif_etiketleri`
etiketleriyle iner (ortak sözlük §6). İşlem kaydına (`kayit`) öğrenci adı ve numarası yazılmaz;
öğrenci kimliği gereken iz `yoklama_iz`'dedir ve yoklamayla birlikte imha edilir.

Aşama 3 sözleşmesi (ortak sözlük §8): A3 öğretmen ve ders adı vermez; ders saatleri ve "programda
ders var" bilgisi `ders_saati` + `tahta_ders`'ten okunur. Program yoksa öneri boş gelir, yoklama yine
çalışır.
"""

from __future__ import annotations

import json
import re
import secrets
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from . import guvenlik, maske, metin, saklama, vt
from . import program as program_mod

ISTANBUL = ZoneInfo("Europe/Istanbul")
YOKLAMA_YETENEGI = "yoklama"

# Saklama süresi 0.8.0'dan beri ayar değildir: kayıtlar öğretim yılı sonuna kadar durur (`saklama.py`).
VARSAYILAN_AYAR = {"etkin": False, "maske": maske.VARSAYILAN_SINIF_BICIMI, "oturum_dk": 8, "bosta_dk": 3}
SINIRLAR = {"oturum_dk": (3, 15), "bosta_dk": (1, 5)}

DERS_NO_EN_COK = 12            # zil saatleri bilinmiyorsa seçilebilen en büyük ders saati
GELECEK_PAYI_SN = 300          # başlangıcı şimdi + 5 dk'dan sonra olan ders saati seçilemez
ALINMADI_PAYI_SN = 900         # ders bitişinden 15 dk sonra yoklaması yoksa "alınmadı"
PANEL_GERI_GUN = 7             # panelden yoklama: bugün ve son 7 gün
IZGARA_EN_AZ = 8               # program bilinmiyorsa ızgaranın en az sütunu
YOK_EN_COK = 200
GOVDE_SINIRI = 64 * 1024
ONIZLEME_OMRU_SN = 15 * 60
IMHA_ARALIGI_SN = 3600
ACIKLAMA_EN_KISA = 5
ACIKLAMA_EN_UZUN = 300
AD_EN_UZUN = 60

# Deneme sınırları (şartname §4.3; bağlayıcı sayılar)
TAHTA_HATA_ADET, TAHTA_HATA_PENCERE_SN, TAHTA_KAPALI_SN = 10, 600, 600
CIFT_ARDISIK, CIFT_BEKLEME_SN = 3, 120
OGRETMEN_HATA_ADET, OGRETMEN_PENCERE_SN = 10, 86400

ILETI_ETKIN_DEGIL = "Ders yoklaması bu okulda etkin değil."
# `oturum_kaydedeni`nin USB eki: "...(tahta:X) USB K7Q2M9XA" (anahtar kimliği alfabesi, metnin sonunda).
_USB_IZ_EKI = re.compile(r"\) USB [ABCDEFGHJKMNPQRSTUVWXYZ2-9]{8}$")
ILETI_HATALI = "Öğretmen kodu ya da PIN hatalı."
ILETI_BEKLE = "Çok fazla hatalı deneme. Biraz bekleyip yeniden deneyin."
ILETI_TAHTA_KAPALI = "Bu tahtada çok fazla hatalı deneme yapıldı. Yoklama girişi 10 dakika kapalı."
ILETI_KILITLI = "PIN'iniz çok sayıda hatalı deneme nedeniyle kilitlendi. Okul idaresine başvurun."
ILETI_OTURUM_BITTI = "Yoklama oturumu sona erdi; PIN'i yeniden girin."
ILETI_LISTE_DEGISTI = "Sınıf listesi değişti; yoklamayı yeniden açın."
ILETI_LISTE_YOK = "Bu şubenin öğrenci listesi yüklenmemiş. Okul idaresine bildirin."
ILETI_SINAV = "Sınav sürüyor; ders yoklaması açılamaz."
ILETI_GELECEK = "Bu ders saati henüz başlamadı."
ILETI_ADLI_SAYFA = "Bu sayfa öğrenci adları içerir. Ekranı paylaşırken ya da yazdırırken dikkat edin."

GUN_ADLARI = program_mod.GUN_ADLARI
KAYNAK_ADI = {"tahta": "Tahta", "panel": "Panel"}
IZ_ISLEM_ADI = {"olustur": "Oluşturuldu", "guncelle": "Güncellendi", "duzelt": "Düzeltildi"}


# ---- ayar ------------------------------------------------------------------------------------
def ayar_al(b) -> dict:
    deger = vt.ayar_al(b, "yoklama")
    sonuc = dict(VARSAYILAN_AYAR)
    if isinstance(deger, dict):
        sonuc.update({k: v for k, v in deger.items() if k in VARSAYILAN_AYAR})
    if sonuc["maske"] not in maske.SINIF_BICIMLERI:  # eski/elle yazılmış değer ("tam" dahil) varsayılana düşer
        sonuc["maske"] = maske.VARSAYILAN_SINIF_BICIMI
    for anahtar, (en_az, en_cok) in SINIRLAR.items():
        try:
            sonuc[anahtar] = max(en_az, min(en_cok, int(sonuc[anahtar])))
        except (TypeError, ValueError):
            sonuc[anahtar] = VARSAYILAN_AYAR[anahtar]
    sonuc["etkin"] = bool(sonuc["etkin"])
    return sonuc


def ayar_coz(form) -> dict:
    """Ayarlar › Ders yoklaması formu (alanlar: yk_etkin, yk_maske, yk_oturum_dk, yk_bosta_dk).
    Geçersizde kullanıcıya gösterilecek iletiyle ValueError."""
    bicim = str(form.get("yk_maske", maske.VARSAYILAN_SINIF_BICIMI))
    if bicim not in maske.SINIF_BICIMLERI:
        raise ValueError("Tahtadaki ad görünümü geçersiz.")
    sonuc = {"etkin": form.get("yk_etkin") == "1", "maske": bicim}
    adlar = {"oturum_dk": "Yoklama oturumu", "bosta_dk": "Dokunulmazsa kapanma"}
    for anahtar, (en_az, en_cok) in SINIRLAR.items():
        ham = str(form.get(f"yk_{anahtar}", VARSAYILAN_AYAR[anahtar])).strip()
        if not metin.rakam_mi(ham) or not en_az <= int(ham) <= en_cok:
            raise ValueError(f"{adlar[anahtar]} {en_az}–{en_cok} arasında olmalı.")
        sonuc[anahtar] = int(ham)
    return sonuc


def etkin(b) -> bool:
    return ayar_al(b)["etkin"]


# ---- tarih ve şube -----------------------------------------------------------------------------
def bugun(simdi: int | None = None) -> date:
    return datetime.fromtimestamp(vt.simdi() if simdi is None else int(simdi), ISTANBUL).date()


def tarih_coz(deger) -> date | None:
    try:
        return date.fromisoformat(str(deger or "").strip())
    except ValueError:
        return None


def tarih_yazi(gun: date) -> str:
    return f"{gun:%d.%m.%Y} {GUN_ADLARI[gun.weekday()]}"


def tarih_kisa(gun: date) -> str:
    return f"{gun:%d.%m.%Y}"


def saat(epoch) -> str:
    return datetime.fromtimestamp(int(epoch), ISTANBUL).strftime("%H:%M") if epoch else ""


def an_yazi(epoch) -> str:
    return datetime.fromtimestamp(int(epoch), ISTANBUL).strftime("%d.%m.%Y %H:%M") if epoch else ""


def sube_anahtari(sube: str) -> tuple:
    """Şube sırası: Hazırlık, 9, 10, 11, 12; harf Türk abecesiyle (`10/I` < `10/İ`)."""
    duzey, _, harf = str(sube).partition("/")
    sira = 0 if duzey == "Hazırlık" else int(duzey) if metin.rakam_mi(duzey) else 99
    return (sira, metin.tr_sirala_anahtari(harf), str(sube))


def no_anahtari(okul_no: str) -> tuple:
    s = str(okul_no or "")
    return (0, int(s), s) if metin.rakam_mi(s) else (1, 0, s)


def aralik_yaz(sayilar) -> str:
    """[1,2,3,5,6,8] → "1-3, 5-6, 8" (icmal başlığı)."""
    liste = sorted(set(sayilar))
    parcalar, i = [], 0
    while i < len(liste):
        j = i
        while j + 1 < len(liste) and liste[j + 1] == liste[j] + 1:
            j += 1
        parcalar.append(str(liste[i]) if i == j else f"{liste[i]}-{liste[j]}")
        i = j + 1
    return ", ".join(parcalar)


def aktif_subeler(b) -> list[str]:
    return sorted((s["sube"] for s in b.execute("SELECT DISTINCT sube FROM ogrenci WHERE aktif = 1")), key=sube_anahtari)


def sube_ogrencileri(b, sube: str) -> list:
    return b.execute("SELECT * FROM ogrenci WHERE sube = ? AND aktif = 1", (sube,)).fetchall()


def ad_soyad(o) -> str:
    return " ".join(p for p in (o["ad"], o["soyad"]) if p)


def ogrenci_sirala(ogrenciler) -> list:
    return sorted(ogrenciler, key=lambda o: no_anahtari(o["okul_no"]))


# ---- Aşama 3 uyarlama işlevleri ---------------------------------------------------------------
def _plan(b, tarih: date) -> dict:
    try:
        return program_mod.gun_plani(b, tarih)
    except Exception:  # bozuk zil takvimi yoklamayı durdurmasın; öneri boş kalır
        return {"tatil": None, "dersler": [], "program_gunu": tarih.weekday()}


def _sube_devreleri(b, plan: dict, sube: str) -> set[str]:
    return {
        s["devre"]
        for s in b.execute("SELECT DISTINCT devre FROM tahta_ders WHERE gun = ? AND sube = ?", (plan["program_gunu"], sube))
    }


def program_ders_saatleri(b, tarih: date, sube: str | None, plan: dict | None = None) -> list[dict]:
    """O gün şubenin devresine ait ders saatleri: [{"ders_no","baslangic","bitis","bas","bit"}] (bas/bit epoch).

    Devre: o gün `tahta_ders.sube = sube` satırlarının devresi; satır yoksa ve günde tek devre varsa o.
    Belirlenemezse (ikili öğretimde programsız şube) boş liste: ders saati 1–12 serbest seçilir.
    """
    plan = plan or _plan(b, tarih)
    dersler = plan.get("dersler") or []
    if not dersler:
        return []
    tum_devreler = {d[0] for d in dersler}
    devreler = _sube_devreleri(b, plan, sube) & tum_devreler if sube else set()
    if not devreler:
        devreler = tum_devreler if len(tum_devreler) == 1 else set()
    if len(devreler) != 1:
        return []
    sonuc: dict[int, dict] = {}
    for d in dersler:
        if d[0] in devreler and d[2] not in sonuc:
            sonuc[d[2]] = {"ders_no": d[2], "baslangic": f"{d[3]:%H:%M}", "bitis": f"{d[4]:%H:%M}",
                           "bas": int(d[3].timestamp()), "bit": int(d[4].timestamp())}  # fmt: skip
    return [sonuc[n] for n in sorted(sonuc)]


def sube_devre_adi(b, plan: dict, sube: str) -> str:
    """İkili eğitimde şubenin o günkü devresinin adı ("Sabah"); tek devrede ya da belirlenemezse ""."""
    tum = {d[0]: d[1] for d in plan.get("dersler") or []}
    if len(tum) < 2:
        return ""
    devreler = _sube_devreleri(b, plan, sube) & set(tum)
    return tum[next(iter(devreler))] if len(devreler) == 1 else ""


def program_gunluk(b, tarih: date, sube: str, plan: dict | None = None) -> list[dict]:
    """Şubenin o günkü programdaki dersleri: [{"ders_no","ders_adi":"","ogretmen_id":None,"bit"}] (bit epoch|None).

    A3 öğretmen ve ders adı tutmaz; "programda ders var" = o gün o şube için `tahta_ders` satırı var.
    """
    plan = plan or _plan(b, tarih)
    if plan.get("tatil"):
        return []
    satirlar = b.execute(
        "SELECT DISTINCT devre, ders_no FROM tahta_ders WHERE gun = ? AND sube = ?", (plan["program_gunu"], sube)
    ).fetchall()
    bitisler = {(d[0], d[2]): int(d[4].timestamp()) for d in plan.get("dersler") or []}
    sonuc: dict[int, dict] = {}
    for s in satirlar:
        bit = bitisler.get((s["devre"], s["ders_no"]))
        if bit is None and plan.get("dersler"):
            continue  # o gün o ders saati yok (kısaltılmış gün, tatil yarısı)
        onceki = sonuc.get(s["ders_no"])
        if not onceki or (bit or 0) > (onceki["bit"] or 0):
            sonuc[s["ders_no"]] = {"ders_no": s["ders_no"], "ders_adi": "", "ogretmen_id": None, "bit": bit}
    return [sonuc[n] for n in sorted(sonuc)]


def program_su_an(b, tahta, an: int) -> dict | None:
    """Tahtanın şu anki dersi: {"sube","ders_no","ders_adi":"","ogretmen":None} ya da None."""
    an_dt = datetime.fromtimestamp(int(an), ISTANBUL)
    try:
        ders = program_mod.simdiki_ders(b, tahta, an_dt)
    except Exception:
        ders = None
    if not ders:
        return None
    sube = metin.sube_duzelt(ders.get("sube") or "")
    if not sube:
        tahta_subeleri = tahta_subeleri_(tahta)
        sube = tahta_subeleri[0] if len(tahta_subeleri) == 1 else None
    return {"sube": sube, "ders_no": ders["ders_no"], "ders_adi": "", "ogretmen": None}


def tahta_subeleri_(tahta) -> list[str]:
    return [s for s in (metin.sube_duzelt(x) for x in str(tahta["subeler"] or "").split(",")) if s]


def _tahtanin_dersleri(b, tahta, plan: dict) -> list[tuple]:
    """Tahtanın o günkü programlı dersleri: [(devre, devre_adi, no, bas_dt, bit_dt, sube)] (saat sırasıyla)."""
    satirlar = {
        (s["devre"], s["ders_no"]): s["sube"]
        for s in b.execute(
            "SELECT devre, ders_no, sube FROM tahta_ders WHERE tahta_id = ? AND gun = ?", (tahta["id"], plan["program_gunu"])
        )
    }
    return [(*d, satirlar[(d[0], d[2])]) for d in plan.get("dersler") or [] if (d[0], d[2]) in satirlar]


def _yakin_ders(b, tahta, plan: dict, an: int) -> dict | None:
    """Şu an ders yoksa: 5 dk içinde başlayacak ders (öğretmen erken geldi), yoksa 15 dk içinde bitmiş ders
    (yoklamayı teneffüste giriyor). {"sube", "ders_no"} ya da None. İkili eğitimde doğru devrenin dersini
    bulur: tahtanın programı devreyle birlikte tutulur."""
    dersler = _tahtanin_dersleri(b, tahta, plan)
    sonraki = [d for d in dersler if an < d[3].timestamp() <= an + GELECEK_PAYI_SN]
    onceki = [d for d in dersler if d[4].timestamp() <= an < d[4].timestamp() + ALINMADI_PAYI_SN]
    d = sonraki[0] if sonraki else (onceki[-1] if onceki else None)
    if not d:
        return None
    return {"sube": metin.sube_duzelt(d[5] or "") or None, "ders_no": d[2]}


def _devresi_suren_subeler(b, gun: date, subeler: list[str], an: int, plan: dict) -> list[str]:
    """İkili eğitimde tahtanın birden çok şubesinden, devresi şu an süren(ler) (ilk dersten 5 dk önce ile son
    dersten 15 dk sonrası arası). Devresi bilinmeyen şube elenmez."""
    sonuc = []
    for sube in subeler:
        saatler = program_ders_saatleri(b, gun, sube, plan)
        if not saatler or saatler[0]["bas"] - GELECEK_PAYI_SN <= an < saatler[-1]["bit"] + ALINMADI_PAYI_SN:
            sonuc.append(sube)
    return sonuc


def oneri(b, tahta, an: int, sube_istegi: str | None = None) -> dict:
    """/ajan/yoklama/oneri yanıtı (öğrenci verisi İÇERMEZ).

    Şube ve ders saati önerisi sırası: programdaki şu anki ders (`tahta_ders.sube`) → tahtada 5 dk içinde
    başlayacak ya da 15 dk içinde bitmiş ders → `tahta.subeler` tek şubeyse o (ikili eğitimde birden çok
    şube varsa devresi şu an süren tek şube) → None. Ders numarası şubenin kendi devresinin numarasıdır
    (sabahçının 3. dersi ile öğlencinin 3. dersi karışmaz).
    `sube_istegi` verilirse ders saatleri o şubenin devresine göre döner (öğretmen şubeyi değiştirdi).
    Ders saatlerinde `secilebilir`: başlangıcı şimdi + 5 dk'dan önce (tahtanın saatine güvenilmez).
    """
    gun = bugun(an)
    plan = _plan(b, gun)
    su_an = program_su_an(b, tahta, an)
    if not su_an:
        try:
            su_an = _yakin_ders(b, tahta, plan, an)
        except Exception:  # öneri yardımcıdır; bozuk program yoklamayı durdurmasın
            su_an = None
    tahta_subeleri = tahta_subeleri_(tahta)
    if len(tahta_subeleri) > 1:
        tahta_subeleri = _devresi_suren_subeler(b, gun, tahta_subeleri, an, plan)
    sube = (su_an or {}).get("sube") or (tahta_subeleri[0] if len(tahta_subeleri) == 1 else None)
    hedef_sube = metin.sube_duzelt(sube_istegi) if sube_istegi else sube
    saatler = program_ders_saatleri(b, gun, hedef_sube, plan)
    ders_no = (su_an or {}).get("ders_no") if hedef_sube == sube else None
    if ders_no is None and hedef_sube:
        ders_no = next((s["ders_no"] for s in saatler if s["bas"] <= an < s["bit"]), None)
    return {
        "etkin": True,
        "tarih": gun.isoformat(),
        "tarih_yazi": tarih_yazi(gun),
        "ders_saatleri": [
            {"ders_no": s["ders_no"], "baslangic": s["baslangic"], "bitis": s["bitis"], "secilebilir": s["bas"] <= an + GELECEK_PAYI_SN}
            for s in saatler
        ],
        "ders_no_en_cok": max((s["ders_no"] for s in saatler), default=DERS_NO_EN_COK),
        "oneri": {"sube": sube, "ders_no": ders_no, "ders_adi": "", "ogretmen": None},
        "subeler": aktif_subeler(b),
    }


def ders_no_denetle(b, gun: date, sube: str, ders_no, an: int, gelecek_reddet: bool = True) -> str | None:
    """Ders saati geçerli mi? Hata iletisi ya da None. Zil saatleri biliniyorsa onlardan, yoksa 1–12."""
    if isinstance(ders_no, bool) or not isinstance(ders_no, int):
        ders_no = int(ders_no) if metin.rakam_mi(str(ders_no).strip()) and len(str(ders_no).strip()) <= 2 else None
    if ders_no is None:
        return "Ders saatini seçin."
    saatler = program_ders_saatleri(b, gun, sube)
    if saatler:
        bulunan = next((s for s in saatler if s["ders_no"] == ders_no), None)
        if not bulunan:
            return "Bu şubenin bugünkü ders saatlerinde bu ders yok."
        if gelecek_reddet and gun == bugun(an) and bulunan["bas"] > an + GELECEK_PAYI_SN:
            return ILETI_GELECEK
    elif not 1 <= ders_no <= DERS_NO_EN_COK:
        return f"Ders saati 1–{DERS_NO_EN_COK} arasında olmalı."
    return None


# ---- öğretmen ve PIN ---------------------------------------------------------------------------
def ogretmen_etiketi(ad: str, soyad: str) -> str:
    """Tahtada ve pusulada öğretmen: "A. Yılmaz" (adın baş harfi + soyad)."""
    ad = " ".join(str(ad or "").split())
    soyad = " ".join(str(soyad or "").split())
    bas = metin.tr_buyuk(ad[:1]) + "." if ad else ""
    return " ".join(p for p in (bas, soyad) if p) or "?"


def ogretmen_tam_ad(o) -> str:
    return " ".join(p for p in (o["ad"], o["soyad"]) if p)


def kod_uret(b) -> str:
    kullanilan = {s["kod"] for s in b.execute("SELECT kod FROM ogretmen_pin")}
    for n in range(101, 1000):
        if str(n) not in kullanilan:
            return str(n)
    raise ValueError("Öğretmen kodu kalmadı (101–999 dolu).")


def kod_gecerli(kod) -> bool:
    kod = str(kod or "")
    return len(kod) == 3 and metin.rakam_mi(kod) and 101 <= int(kod) <= 999


def pin_uret() -> str:
    """6 haneli PIN; kolay tahmin edilenler (aynı rakamlar, ardışık dizi, iki rakamlı) üretilmez."""
    while True:
        pin = f"{secrets.randbelow(10**6):06d}"
        if len(set(pin)) <= 2 or pin in "0123456789" or pin in "9876543210":
            continue
        return pin


def pin_bicimli(pin: str) -> str:
    return f"{pin[:3]} {pin[3:]}"


_SAHTE_OZET: list[str] = []


def _sahte_ozet() -> str:
    """Bilinmeyen kodda da aynı süre harcansın diye karşılaştırılan özet (bir kez üretilir)."""
    if not _SAHTE_OZET:
        _SAHTE_OZET.append(guvenlik.parola_ozetle(secrets.token_hex(8)))
    return _SAHTE_OZET[0]


class PinKapisi:
    """Bellekteki iki deneme katmanı (tahta başına; öğretmen kodu + tahta çifti başına).

    Üçüncü katman (öğretmen başına 24 saatte 10 hata → kilit) veritabanındadır (`ogretmen_pin`).
    Zaman `vt.simdi()` ile verilir (testte saat ilerletilebilsin).
    """

    def __init__(self):
        self.tahta_hatalari: dict[int, list[int]] = {}
        self.tahta_kapali: dict[int, int] = {}
        self.cift_hatalari: dict[tuple[int, str], int] = {}
        self.cift_bekleme: dict[tuple[int, str], int] = {}

    def bekleme(self, tahta_id: int, kod: str, an: int) -> tuple[int, str]:
        """(bekleme sn, ileti); 0 ise deneme serbest."""
        kalan = self.tahta_kapali.get(tahta_id, 0) - an
        if kalan > 0:
            return kalan, ILETI_TAHTA_KAPALI
        kalan = self.cift_bekleme.get((tahta_id, kod), 0) - an
        if kalan > 0:
            return kalan, ILETI_BEKLE
        return 0, ""

    def hata(self, tahta_id: int, kod: str, an: int) -> int:
        """Hatalı denemeyi sayar; başlayan bekleme süresini (sn) döndürür (0: bekleme yok)."""
        liste = [z for z in self.tahta_hatalari.get(tahta_id, []) if an - z < TAHTA_HATA_PENCERE_SN] + [an]
        self.tahta_hatalari[tahta_id] = liste
        if len(liste) >= TAHTA_HATA_ADET:
            self.tahta_hatalari[tahta_id] = []
            self.tahta_kapali[tahta_id] = an + TAHTA_KAPALI_SN
            return TAHTA_KAPALI_SN
        anahtar = (tahta_id, kod)
        self.cift_hatalari[anahtar] = self.cift_hatalari.get(anahtar, 0) + 1
        if self.cift_hatalari[anahtar] >= CIFT_ARDISIK:
            self.cift_hatalari[anahtar] = 0
            self.cift_bekleme[anahtar] = an + CIFT_BEKLEME_SN
            return CIFT_BEKLEME_SN
        return 0

    def basarili(self, tahta_id: int, kod: str) -> None:
        self.cift_hatalari.pop((tahta_id, kod), None)
        self.cift_bekleme.pop((tahta_id, kod), None)


def pin_dogrula(b, kapi: PinKapisi, kod, pin, tahta_id: int, an: int) -> tuple[str, object, int]:
    """Kod + PIN doğrulaması. Döndürür: (durum, öğretmen satırı | None, bekleme_sn).

    durum: "tamam" · "hatali" (403) · "bekle" (429) · "kilitli" (423; bu denemeyle kilitlenen dahil).
    Bilinmeyen kod, pasif öğretmen, PIN'i olmayan öğretmen ve yanlış PIN aynı yanıtı alır ve
    aynı süreyi harcar (sahte özetle karşılaştırılır).
    """
    kod = str(kod or "")[:8]
    pin = str(pin or "")[:16]
    bekleme, _ = kapi.bekleme(tahta_id, kod, an)
    if bekleme:
        return "bekle", None, bekleme
    satir = None
    if kod_gecerli(kod):
        satir = b.execute(
            "SELECT o.*, p.kod, p.pin_ozet, p.hatali_sayi, p.hatali_ilk, p.kilitli FROM ogretmen o "
            "JOIN ogretmen_pin p ON p.ogretmen_id = o.id WHERE p.kod = ?",
            (kod,),
        ).fetchone()
    if satir and satir["kilitli"]:
        guvenlik.parola_dogrula(pin, _sahte_ozet())
        return "kilitli", satir, 0
    gecerli_bicim = len(pin) == 6 and metin.rakam_mi(pin)
    ozet = satir["pin_ozet"] if satir and satir["pin_ozet"] and satir["aktif"] else _sahte_ozet()
    dogru = guvenlik.parola_dogrula(pin if gecerli_bicim else "x", ozet) and gecerli_bicim and ozet != _sahte_ozet()
    if dogru:
        kapi.basarili(tahta_id, kod)
        return "tamam", satir, 0
    bekleme = kapi.hata(tahta_id, kod, an)
    if satir and satir["aktif"] and satir["pin_ozet"]:
        ilk = satir["hatali_ilk"]
        if not ilk or an - ilk >= OGRETMEN_PENCERE_SN:
            sayi, ilk = 1, an
        else:
            sayi = satir["hatali_sayi"] + 1
        kilit = sayi >= OGRETMEN_HATA_ADET
        b.execute(
            "UPDATE ogretmen_pin SET hatali_sayi = ?, hatali_ilk = ?, kilitli = ? WHERE ogretmen_id = ?",
            (sayi, ilk, int(kilit), satir["id"]),
        )
        if kilit:
            b.execute("DELETE FROM yoklama_belirtec WHERE ogretmen_id = ?", (satir["id"],))
            vt.kayit_dus(b, "sistem", "Öğretmen PIN'i kilitlendi", f"kod {kod}")
            return "kilitli", satir, 0
    if bekleme:
        return "bekle", satir, bekleme
    return "hatali", satir, 0


def oturum_ac(
    b, ogretmen_id: int | None = None, tahta_id: int | None = None, an: int | None = None, oturum_dk: int | None = None,
    *, kullanici_id: int | None = None, anahtar_id: int | None = None,
) -> tuple[str, int]:  # fmt: skip
    """Yoklama belirteci üretir; (belirteç, bitiş). Aynı kişi-tahta çiftinin eski oturumları silinir.

    Öğretmen oturumu (`ogretmen_id`; kod + PIN ya da öğretmen USB anahtarı) ya da idare oturumu
    (`kullanici_id`; yalnız idare USB anahtarı). `anahtar_id` doluysa oturum o anahtarla açılmıştır
    (anahtar iptal edilince düşer). 0.6.0'daki konumsal çağrı biçimi (ilk argüman ogretmen_id) korunur.
    """
    if (ogretmen_id is None) == (kullanici_id is None):
        raise ValueError("Oturum ya öğretmenin ya idarenin olmalı.")
    if ogretmen_id is not None:
        b.execute("DELETE FROM yoklama_belirtec WHERE (ogretmen_id = ? AND tahta_id = ?) OR bitis <= ?", (ogretmen_id, tahta_id, an))
    else:
        b.execute("DELETE FROM yoklama_belirtec WHERE (kullanici_id = ? AND tahta_id = ?) OR bitis <= ?", (kullanici_id, tahta_id, an))
    belirtec = guvenlik.belirtec()
    bitis = an + oturum_dk * 60
    b.execute(
        "INSERT INTO yoklama_belirtec (belirtec_ozet, ogretmen_id, kullanici_id, anahtar_id, tahta_id, bitis, olusturma) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (guvenlik.ozet(belirtec), ogretmen_id, kullanici_id, anahtar_id, tahta_id, bitis, an),
    )
    return belirtec, bitis


def oturum_coz(b, belirtec, tahta_id: int, an: int):
    """Geçerli (bu tahtanın, süresi dolmamış) oturum; değilse None.

    Öğretmen oturumu: öğretmen etkin ve PIN'i kilitsiz. İdare oturumu: kullanıcı etkin ve rolü yönetici/idareci.
    USB anahtarla açılmışsa anahtar `etkin` olmalı (iptal ya da PIN kilidi oturumu düşürür).
    Satır: belirtec_ozet, bitis, ogretmen_id, kullanici_id, anahtar_id, ad, soyad, kod, tur ('ogretmen'|'idare'),
    kullanici_ad, gorunen_ad, anahtar_kimlik.
    """
    if not isinstance(belirtec, str) or not belirtec or len(belirtec) > 200:
        return None
    return b.execute(
        "SELECT y.belirtec_ozet, y.bitis, y.ogretmen_id, y.kullanici_id, y.anahtar_id, o.ad, o.soyad, p.kod, "
        "CASE WHEN y.kullanici_id IS NOT NULL THEN 'idare' ELSE 'ogretmen' END AS tur, "
        "k.ad AS kullanici_ad, k.gorunen_ad, a.kimlik AS anahtar_kimlik FROM yoklama_belirtec y "
        "LEFT JOIN ogretmen o ON o.id = y.ogretmen_id LEFT JOIN ogretmen_pin p ON p.ogretmen_id = y.ogretmen_id "
        "LEFT JOIN kullanici k ON k.id = y.kullanici_id LEFT JOIN usb_anahtar a ON a.id = y.anahtar_id "
        "WHERE y.belirtec_ozet = ? AND y.tahta_id = ? AND y.bitis > ? "
        "AND ((y.ogretmen_id IS NOT NULL AND o.aktif = 1 AND p.kilitli = 0) "
        "  OR (y.kullanici_id IS NOT NULL AND k.aktif = 1 AND k.rol IN ('yonetici', 'idareci'))) "
        "AND (y.anahtar_id IS NULL OR a.durum = 'etkin')",
        (guvenlik.ozet(belirtec), tahta_id, an),
    ).fetchone()


def oturum_kaydedeni(oturum, tahta_ad: str) -> tuple[int | None, str, str]:
    """Tahtadan alınan yoklamanın (ogretmen_id, kaydeden, iz `kim`) üçlüsü, oturumun türüne göre.

    Öğretmen: (id, 'ogretmen:112', 'ogretmen:112 (tahta:X)'); idare: (None, 'kullanici:mdryrd', …).
    USB anahtarla açılan oturumda iz metnine ' USB K7Q2M9XA' eklenir (kayit_ayrintisi bunu okur).
    """
    if oturum["tur"] == "idare":
        ogretmen_id, kaydeden = None, f"kullanici:{oturum['kullanici_ad']}"
    else:
        ogretmen_id, kaydeden = oturum["ogretmen_id"], f"ogretmen:{oturum['kod']}"
    kim = f"{kaydeden} (tahta:{tahta_ad})"
    if oturum["anahtar_kimlik"]:
        kim += f" USB {oturum['anahtar_kimlik']}"
    return ogretmen_id, kaydeden, kim


def oturum_kapat(b, belirtec) -> None:
    if isinstance(belirtec, str) and belirtec:
        b.execute("DELETE FROM yoklama_belirtec WHERE belirtec_ozet = ?", (guvenlik.ozet(belirtec),))


def oturumlari_dusur(b, ogretmen_id: int) -> None:
    b.execute("DELETE FROM yoklama_belirtec WHERE ogretmen_id = ?", (ogretmen_id,))


# ---- yoklama yazma -----------------------------------------------------------------------------
def _yoklama_bul(b, tarih: str, sube: str, ders_no: int, ogretmen_id: int | None, kaynak: str):
    return b.execute(
        "SELECT * FROM yoklama WHERE tarih = ? AND sube = ? AND ders_no = ? AND IFNULL(ogretmen_id, 0) = ? AND kaynak = ?",
        (tarih, sube, ders_no, ogretmen_id or 0, kaynak),
    ).fetchone()


def yok_listesi(b, yoklama_id: int) -> list[int]:
    return sorted(s["ogrenci_id"] for s in b.execute("SELECT ogrenci_id FROM yoklama_yok WHERE yoklama_id = ?", (yoklama_id,)))


def onceki_yok(b, tarih: str, sube: str, ders_no: int, ogretmen_id: int | None, kaynak: str) -> list[int]:
    satir = _yoklama_bul(b, tarih, sube, ders_no, ogretmen_id, kaynak)
    return yok_listesi(b, satir["id"]) if satir else []


def baska_yoklama_var(b, tarih: str, sube: str, ders_no: int, ogretmen_id: int | None, kaynak: str) -> bool:
    return bool(
        b.execute(
            "SELECT 1 FROM yoklama WHERE tarih = ? AND sube = ? AND ders_no = ? AND NOT (IFNULL(ogretmen_id, 0) = ? AND kaynak = ?)",
            (tarih, sube, ders_no, ogretmen_id or 0, kaynak),
        ).fetchone()
    )


def yok_idleri_coz(ham, gecerli: set[int]) -> list[int]:
    """İstemciden gelen öğrenci kimlikleri; listede olmayan ya da sayı olmayan varsa ValueError."""
    if not isinstance(ham, list) or len(ham) > YOK_EN_COK:
        raise ValueError("Geçersiz istek.")
    idler: set[int] = set()
    for deger in ham:
        if isinstance(deger, bool):
            raise ValueError(ILETI_LISTE_DEGISTI)
        s = str(deger).strip()
        if not metin.rakam_mi(s) or len(s) > 12:
            raise ValueError(ILETI_LISTE_DEGISTI)
        idler.add(int(s))
    if idler - gecerli:
        raise ValueError(ILETI_LISTE_DEGISTI)
    return sorted(idler)


def yoklama_yaz(
    b, *, tarih: str, sube: str, ders_no: int, ogretmen_id: int | None, kaynak: str, kaydeden: str,
    tahta_id: int | None, yok: list[int], kim: str, an: int, islem: str | None = None, aciklama: str = "",
) -> tuple[int, bool]:  # fmt: skip
    """Upsert (tarih, şube, ders saati, öğretmen, kaynak) + `yoklama_yok` yeniden yazılır + `yoklama_iz` farkı.

    Döndürür: (yoklama_id, yeni_mi). `mevcut` kayıt anındaki şubenin etkin öğrenci sayısıdır.
    """
    mevcut = b.execute("SELECT COUNT(*) FROM ogrenci WHERE sube = ? AND aktif = 1", (sube,)).fetchone()[0]
    eski = _yoklama_bul(b, tarih, sube, ders_no, ogretmen_id, kaynak)
    if eski:
        yoklama_id = eski["id"]
        onceki = set(yok_listesi(b, yoklama_id))
        b.execute(
            "UPDATE yoklama SET kaydeden = ?, tahta_id = COALESCE(?, tahta_id), mevcut = ?, guncelleme = ? WHERE id = ?",
            (kaydeden, tahta_id, mevcut, an, yoklama_id),
        )
        b.execute("DELETE FROM yoklama_yok WHERE yoklama_id = ?", (yoklama_id,))
    else:
        onceki = set()
        yoklama_id = b.execute(
            "INSERT INTO yoklama (tarih, ders_no, sube, ogretmen_id, ders_adi, tahta_id, kaynak, kaydeden, mevcut, olusturma, guncelleme) "
            "VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?)",
            (tarih, ders_no, sube, ogretmen_id, tahta_id, kaynak, kaydeden, mevcut, an, an),
        ).lastrowid
    yeni = set(yok)
    b.executemany("INSERT INTO yoklama_yok (yoklama_id, ogrenci_id) VALUES (?, ?)", [(yoklama_id, i) for i in sorted(yeni)])
    b.execute(
        "INSERT INTO yoklama_iz (yoklama_id, zaman, kim, islem, eklenen, cikarilan, aciklama) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (yoklama_id, an, kim, islem or ("guncelle" if eski else "olustur"),
         json.dumps(sorted(yeni - onceki)), json.dumps(sorted(onceki - yeni)), aciklama[:ACIKLAMA_EN_UZUN]),
    )  # fmt: skip
    return yoklama_id, not eski


def aciklama_denetle(aciklama: str) -> str:
    """Düzeltme/silme gerekçesi: zorunlu, en az 5 karakter, T.C. kimlik numarası içermez."""
    aciklama = " ".join(str(aciklama or "").split())[:ACIKLAMA_EN_UZUN]
    if len(aciklama) < ACIKLAMA_EN_KISA:
        raise ValueError(f"Gerekçe yazın (en az {ACIKLAMA_EN_KISA} karakter). Öğrenci ya da kişi adı yazmayın.")
    if guvenlik.tc_kimlik_var(aciklama):
        raise ValueError(guvenlik.TC_KIMLIK_ILETISI)
    return aciklama


def kayit_metni(sube: str, ders_no: int, yok_sayisi: int, kod: str | None = None, tarih: date | None = None) -> str:
    """İşlem kaydı ayrıntısı: şube, ders saati, sayı, öğretmen kodu (ad ve okul no YOK)."""
    parca = [f"{tarih_kisa(tarih)} " if tarih else "", f"{sube} {ders_no}. ders, {yok_sayisi} yok"]
    if kod:
        parca.append(f", öğretmen kodu {kod}")
    return "".join(parca)


# ---- günlük görünüm ve icmal -------------------------------------------------------------------
def _gunun_yoklamalari(b, tarih: str) -> list:
    return b.execute(
        "SELECT y.*, o.ad AS ogretmen_ad, o.soyad AS ogretmen_soyad, p.kod AS ogretmen_kod, t.ad AS tahta_ad "
        "FROM yoklama y LEFT JOIN ogretmen o ON o.id = y.ogretmen_id LEFT JOIN ogretmen_pin p ON p.ogretmen_id = y.ogretmen_id "
        "LEFT JOIN tahta t ON t.id = y.tahta_id WHERE y.tarih = ? ORDER BY y.id",
        (tarih,),
    ).fetchall()


def _gunun_yoklari(b, tarih: str) -> dict[int, set[int]]:
    yoklar: dict[int, set[int]] = {}
    for s in b.execute(
        "SELECT yy.yoklama_id, yy.ogrenci_id FROM yoklama_yok yy JOIN yoklama y ON y.id = yy.yoklama_id WHERE y.tarih = ?", (tarih,)
    ):
        yoklar.setdefault(s["yoklama_id"], set()).add(s["ogrenci_id"])
    return yoklar


def alan_etiketi(y) -> str:
    """Yoklamayı alan: öğretmen etiketi, "idare (kullanıcı adı)" (idare USB anahtarı, 0.11.0) ya da "panel"."""
    if y["ogretmen_id"] and y["ogretmen_ad"] is not None:
        return ogretmen_etiketi(y["ogretmen_ad"], y["ogretmen_soyad"])
    kaydeden = str(y["kaydeden"] or "")
    if y["kaynak"] == "tahta" and not y["ogretmen_id"] and kaydeden.startswith("kullanici:"):
        return f"idare ({kaydeden.removeprefix('kullanici:')})"
    return "panel" if y["kaynak"] == "panel" else "?"


def gunluk_gorunum(b, gun: date, an: int) -> dict:
    """/yoklama sayfasının verisi (şube × ders saati ızgarası, özet, öğrenci bazında liste)."""
    tarih = gun.isoformat()
    plan = _plan(b, gun)
    yoklamalar = _gunun_yoklamalari(b, tarih)
    yoklar = _gunun_yoklari(b, tarih)
    subeler = set(aktif_subeler(b)) | {y["sube"] for y in yoklamalar}
    programli = {s: program_gunluk(b, gun, s, plan) for s in subeler}
    for s in b.execute("SELECT DISTINCT sube FROM tahta_ders WHERE gun = ? AND sube != ''", (plan["program_gunu"],)):
        kanonik = metin.sube_duzelt(s["sube"])
        if kanonik and kanonik not in subeler and not plan.get("tatil"):
            subeler.add(kanonik)
            programli[kanonik] = program_gunluk(b, gun, s["sube"], plan)
    subeler_sirali = sorted(subeler, key=sube_anahtari)
    program_var = any(programli.values())
    en_buyuk = max([d["ders_no"] for p in programli.values() for d in p] + [y["ders_no"] for y in yoklamalar] + [0])
    sutun = max(en_buyuk, 0 if program_var else IZGARA_EN_AZ) or IZGARA_EN_AZ
    kayitlar: dict[tuple[str, int], list] = {}
    for y in yoklamalar:
        kayitlar.setdefault((y["sube"], y["ders_no"]), []).append(y)
    islenen = {s["sube"]: s for s in b.execute("SELECT * FROM eokul_islendi WHERE tarih = ?", (tarih,))}
    saat_araliklari = {s: {d["ders_no"]: f"{d['baslangic']}–{d['bitis']}" for d in program_ders_saatleri(b, gun, s, plan)}
                       for s in subeler_sirali}  # fmt: skip
    satirlar = []
    alinan = beklenen = 0
    for s in subeler_sirali:
        dersli = {d["ders_no"]: d for d in programli.get(s, [])}
        beklenen += len(dersli)
        hucreler = []
        for n in range(1, sutun + 1):
            ks = kayitlar.get((s, n), [])
            aralik = saat_araliklari[s].get(n, "")
            if ks:
                alinan += 1
                birlesik = set().union(*(yoklar.get(k["id"], set()) for k in ks))
                ipucu = [aralik] if aralik else []
                if len(ks) > 1:
                    ipucu.append(f"{len(ks)} yoklama birleştirildi")
                ipucu.append("Alan: " + ", ".join(alan_etiketi(k) for k in ks))
                hucreler.append({"ders_no": n, "durum": "alindi", "yok": len(birlesik), "kayit_id": ks[0]["id"],
                                 "kayit_sayisi": len(ks), "baslik": " · ".join(ipucu)})  # fmt: skip
            elif n in dersli and dersli[n]["bit"] and dersli[n]["bit"] + ALINMADI_PAYI_SN <= an:
                hucreler.append({"ders_no": n, "durum": "alinmadi", "yok": None, "kayit_id": None, "kayit_sayisi": 0,
                                 "baslik": " · ".join(p for p in (aralik, "Programda ders var; yoklama alınmadı") if p)})  # fmt: skip
            else:
                hucreler.append({"ders_no": n, "durum": "bos", "yok": None, "kayit_id": None, "kayit_sayisi": 0, "baslik": aralik})
        satirlar.append({
            "sube": s,
            "devre_adi": sube_devre_adi(b, plan, s),
            "hucreler": hucreler,
            "islendi": s in islenen,
            "islendi_metni": f"{islenen[s]['kullanici']}, {an_yazi(islenen[s]['zaman'])}" if s in islenen else "",
        })  # fmt: skip
    # Öğrenci bazında: (şube, öğrenci) → yok olduğu ders saatleri; "bütün gün yok" = şubenin yoklaması alınan bütün saatlerde yok
    alinan_saatler: dict[str, set[int]] = {}
    for y in yoklamalar:
        alinan_saatler.setdefault(y["sube"], set()).add(y["ders_no"])
    ogrenci_saat: dict[tuple[str, int], set[int]] = {}
    for y in yoklamalar:
        for oid in yoklar.get(y["id"], ()):
            ogrenci_saat.setdefault((y["sube"], oid), set()).add(y["ders_no"])
    ogrenci_satirlari = _ogrenci_satirlari(b, ogrenci_saat, alinan_saatler)
    butun_gun = sum(1 for o in ogrenci_satirlari if o["butun_gun"])
    listedeki = set(aktif_subeler(b))  # bir kez sorgulanır (önceden her şube için yeniden sorgulanıyordu)
    sube_sayisi = len([s for s in subeler_sirali if s in alinan_saatler or programli.get(s) or s in listedeki])
    return {
        "tarih": tarih,
        "tarih_yazi": tarih_yazi(gun),
        "bugun": gun == bugun(an),
        "onceki": (gun - timedelta(days=1)).isoformat(),
        "sonraki": (gun + timedelta(days=1)).isoformat(),
        "sutunlar": list(range(1, sutun + 1)),
        "satirlar": satirlar,
        "ozet": {
            "alinan": alinan,
            "beklenen": beklenen if program_var else None,
            "yok_ogrenci": len({oid for (_, oid) in ogrenci_saat}),
            "butun_gun_yok": butun_gun,
            "islenen": len([s for s in subeler_sirali if s in islenen]),
            "sube_sayisi": sube_sayisi,
        },
        "ogrenciler": ogrenci_satirlari,
        "tatil": plan.get("tatil"),
    }


def _ogrenci_satirlari(b, ogrenci_saat: dict[tuple[str, int], set[int]], alinan_saatler: dict[str, set[int]]) -> list[dict]:
    if not ogrenci_saat:
        return []
    idler = sorted({oid for (_, oid) in ogrenci_saat})
    ogrenciler: dict[int, object] = {}
    for i in range(0, len(idler), 500):
        parca = idler[i : i + 500]
        for o in b.execute(f"SELECT * FROM ogrenci WHERE id IN ({','.join('?' * len(parca))})", parca):
            ogrenciler[o["id"]] = o
    satirlar = []
    for (sube, oid), saatler in ogrenci_saat.items():
        o = ogrenciler.get(oid)
        if not o:
            continue
        alinan = alinan_saatler.get(sube, set())
        satirlar.append({
            "sube": sube, "ogrenci_id": oid, "okul_no": o["okul_no"], "ad": o["ad"], "soyad": o["soyad"],
            "ad_soyad": ad_soyad(o), "saatler": sorted(saatler), "saatler_metni": ", ".join(map(str, sorted(saatler))),
            "sayi": len(saatler), "alinan": len(alinan), "butun_gun": bool(alinan) and saatler >= alinan,
        })  # fmt: skip
    return sorted(satirlar, key=lambda r: (sube_anahtari(r["sube"]), no_anahtari(r["okul_no"])))


def icmal(b, gun: date, sube: str | None = None) -> dict:
    """Gün sonu icmali: şube başına yok listesi (birleşim kuralı; `yoklama.sube`'ye göre)."""
    tarih = gun.isoformat()
    plan = _plan(b, gun)
    yoklamalar = _gunun_yoklamalari(b, tarih)
    yoklar = _gunun_yoklari(b, tarih)
    subeler = {y["sube"] for y in yoklamalar} | set(aktif_subeler(b))
    if sube:
        subeler = {sube} if sube in subeler else set()
    sonuc = []
    for s in sorted(subeler, key=sube_anahtari):
        ks = [y for y in yoklamalar if y["sube"] == s]
        alinan = sorted({y["ders_no"] for y in ks})
        programli = [d["ders_no"] for d in program_gunluk(b, gun, s, plan)]
        # Program bilinmiyorsa günlük ızgaradaki kural: en az IZGARA_EN_AZ saat. Yoksa payda "alınan son
        # saat" olur ("1-3 (3 / 3)") ve alınmayan dersler icmalde hiç görünmezdi.
        program_bilinir = bool(programli)
        sutun = max([*programli, *alinan, 0 if program_bilinir else IZGARA_EN_AZ]) or IZGARA_EN_AZ
        alinmayan = [n for n in range(1, sutun + 1) if n not in alinan]
        ogrenci_saat: dict[tuple[str, int], set[int]] = {}
        for y in ks:
            for oid in yoklar.get(y["id"], ()):
                ogrenci_saat.setdefault((s, oid), set()).add(y["ders_no"])
        ogrenciler = []
        for r in _ogrenci_satirlari(b, ogrenci_saat, {s: set(alinan)}):
            hucreler = ["Y" if n in r["saatler"] else ("." if n in alinan else "-") for n in range(1, sutun + 1)]
            ogrenciler.append({**r, "hucreler": hucreler})
        alanlar = []
        for n in range(1, sutun + 1):
            bu = [y for y in ks if y["ders_no"] == n]
            alanlar.append({"ders_no": n, "metin": ", ".join(dict.fromkeys(alan_etiketi(y) for y in bu)) if bu else "(alınmadı)"})
        mevcut = b.execute("SELECT COUNT(*) FROM ogrenci WHERE sube = ? AND aktif = 1", (s,)).fetchone()[0]
        mevcut = mevcut or max([y["mevcut"] for y in ks] + [0])
        sonuc.append({
            "sube": s, "devre_adi": sube_devre_adi(b, plan, s), "mevcut": mevcut, "sutunlar": list(range(1, sutun + 1)), "alinan": alinan,
            "alinan_metni": aralik_yaz(alinan) if alinan else "yok", "alinmayan": alinmayan,
            "alinan_sayisi": len(alinan), "sutun_sayisi": sutun, "ogrenciler": ogrenciler, "alanlar": alanlar,
            "program_bilinir": program_bilinir,
        })  # fmt: skip
    return {"tarih": tarih, "tarih_yazi": tarih_yazi(gun), "tarih_kisa": tarih_kisa(gun), "subeler": sonuc}


def icmal_metni(veri: dict) -> str:
    """Kopyalanabilir düz metin (sekmeyle ayrılmış; şube başlıklı)."""
    satirlar = [f"{veri['tarih_yazi']} — ders yoklaması icmali"]
    for s in veri["subeler"]:
        bas = f"{s['sube']}{' · ' + s['devre_adi'] if s.get('devre_adi') else ''} (yoklama alınan: {s['alinan_metni']}"
        if s["alinmayan"] and s["alinan"]:
            bas += f"; alınmayan: {aralik_yaz(s['alinmayan'])}"
            if not s.get("program_bilinir", True):
                bas += f"; ders programı yüklü değil, {s['sutun_sayisi']} saat varsayıldı"
        satirlar.append(bas + ")")
        if not s["ogrenciler"]:
            satirlar.append("yok yazılan öğrenci yok")
        for o in s["ogrenciler"]:
            satirlar.append("\t".join([o["okul_no"], o["ad_soyad"], ",".join(map(str, o["saatler"])), str(o["sayi"])]))
    return "\n".join(satirlar) + "\n"


ICMAL_CSV_BASLIKLARI = ["Tarih", "Şube", "Okul No", "Adı", "Soyadı", "Yok Ders Saatleri", "Yok Ders Saati Sayısı",
                        "Yoklama Alınan Ders Saati Sayısı"]  # fmt: skip


def icmal_csv(veri: dict) -> bytes:
    satirlar = [
        [veri["tarih_kisa"], s["sube"], o["okul_no"], o["ad"], o["soyad"], ",".join(map(str, o["saatler"])), o["sayi"], s["alinan_sayisi"]]
        for s in veri["subeler"]
        for o in s["ogrenciler"]
    ]
    return metin.csv_yaz(ICMAL_CSV_BASLIKLARI, satirlar)


def kayit_ayrintisi(b, yoklama_id: int) -> dict | None:
    """/yoklama/kayit/{id}: üst bilgi, şube listesi (etkin + bu kayıtta yok olan pasifler), iz geçmişi."""
    y = b.execute(
        "SELECT y.*, o.ad AS ogretmen_ad, o.soyad AS ogretmen_soyad, p.kod AS ogretmen_kod, t.ad AS tahta_ad "
        "FROM yoklama y LEFT JOIN ogretmen o ON o.id = y.ogretmen_id LEFT JOIN ogretmen_pin p ON p.ogretmen_id = y.ogretmen_id "
        "LEFT JOIN tahta t ON t.id = y.tahta_id WHERE y.id = ?",
        (yoklama_id,),
    ).fetchone()
    if not y:
        return None
    yoklar = set(yok_listesi(b, yoklama_id))
    liste = {o["id"]: o for o in sube_ogrencileri(b, y["sube"])}
    if yoklar - set(liste):
        eksik = sorted(yoklar - set(liste))
        for o in b.execute(f"SELECT * FROM ogrenci WHERE id IN ({','.join('?' * len(eksik))})", eksik):
            liste[o["id"]] = o
    adlar = {i: ad_soyad(o) for i, o in liste.items()}
    izler = []
    usb = False
    for iz in b.execute("SELECT * FROM yoklama_iz WHERE yoklama_id = ? ORDER BY id", (yoklama_id,)):
        # Ek yalnız iz metninin SONUNDA aranır: tahta adı serbest metindir ("Lab USB 2" gibi).
        usb = usb or bool(_USB_IZ_EKI.search(str(iz["kim"])))
        eklenen, cikarilan = json.loads(iz["eklenen"] or "[]"), json.loads(iz["cikarilan"] or "[]")
        izler.append({
            "zaman": an_yazi(iz["zaman"]), "kim": iz["kim"], "islem": IZ_ISLEM_ADI.get(iz["islem"], iz["islem"]),
            "eklenen": [adlar.get(i, f"#{i}") for i in eklenen], "cikarilan": [adlar.get(i, f"#{i}") for i in cikarilan],
            "aciklama": iz["aciklama"],
        })  # fmt: skip
    gun = tarih_coz(y["tarih"])
    if y["kaynak"] == "panel":
        kaynak = f"panel: {y['kaydeden']}"
    else:
        kaynak = f"tahta: {y['tahta_ad']}" if y["tahta_ad"] else "tahta (kaldırılmış)"
        if not y["ogretmen_id"] and str(y["kaydeden"]).startswith("kullanici:"):
            kaynak += f" · idare ({str(y['kaydeden']).removeprefix('kullanici:')})"
        if usb:
            kaynak += " · USB anahtar"
    return {
        "id": y["id"],
        "tarih": y["tarih"],
        "tarih_yazi": tarih_yazi(gun) if gun else y["tarih"],
        "sube": y["sube"],
        "ders_no": y["ders_no"],
        "ders_adi": y["ders_adi"],
        "ogretmen": f"{y['ogretmen_ad']} {y['ogretmen_soyad']}".strip() if y["ogretmen_ad"] is not None else "",
        "ogretmen_kod": y["ogretmen_kod"] or "",
        "kaynak": kaynak,
        "kaynak_turu": y["kaynak"],
        "olusturma": an_yazi(y["olusturma"]),
        "guncelleme": an_yazi(y["guncelleme"]),
        "mevcut": y["mevcut"],
        "yok_sayisi": len(yoklar),
        "ogrenciler": [
            {"id": o["id"], "okul_no": o["okul_no"], "ad_soyad": ad_soyad(o), "yok": o["id"] in yoklar, "pasif": not o["aktif"]}
            for o in ogrenci_sirala(liste.values())
        ],
        "izler": izler,
    }


# ---- öğretmen listesi --------------------------------------------------------------------------
def ogretmen_listesi(b, an: int) -> list[dict]:
    satirlar = b.execute(
        "SELECT o.*, p.kod, p.pin_ozet IS NOT NULL AS pin_var, p.pin_zamani, p.hatali_sayi, p.hatali_ilk, p.kilitli "
        "FROM ogretmen o LEFT JOIN ogretmen_pin p ON p.ogretmen_id = o.id"
    ).fetchall()
    sonuc = []
    for o in satirlar:
        hatali = o["hatali_sayi"] if o["hatali_ilk"] and an - o["hatali_ilk"] < OGRETMEN_PENCERE_SN else 0
        if o["kilitli"]:
            pin_durumu, pin_metni = "kilitli", "kilitli"
        elif o["pin_var"]:
            pin_durumu, pin_metni = "var", f"var · {an_yazi(o['pin_zamani'])[:10]}"
        else:
            pin_durumu, pin_metni = "yok", "yok"
        sonuc.append({
            "id": o["id"], "ad": o["ad"], "soyad": o["soyad"], "ad_soyad": ogretmen_tam_ad(o), "kod": o["kod"] or "",
            "aktif": bool(o["aktif"]), "pin_durumu": pin_durumu, "pin_metni": pin_metni, "hatali": hatali or 0,
            "kilitli": bool(o["kilitli"]),
        })  # fmt: skip
    return sorted(sonuc, key=lambda o: (not o["aktif"], metin.tr_sirala_anahtari(o["soyad"]), metin.tr_sirala_anahtari(o["ad"])))


def ogretmen_adi_coz(ad, soyad) -> tuple[str, str]:
    ad = " ".join(str(ad or "").split())[:AD_EN_UZUN]
    soyad = " ".join(str(soyad or "").split())[:AD_EN_UZUN]
    if not ad:
        raise ValueError("Öğretmenin adını yazın.")
    if guvenlik.tc_kimlik_var(ad) or guvenlik.tc_kimlik_var(soyad):
        raise ValueError(guvenlik.TC_KIMLIK_ILETISI)
    return ad, soyad


def pin_ver(b, ogretmen_id: int, an: int) -> str:
    """Yeni PIN üretir, özetini yazar; kilit ve sayaçları sıfırlar, açık oturumları düşürür. Düz PIN'i döndürür."""
    pin = pin_uret()
    b.execute(
        "UPDATE ogretmen_pin SET pin_ozet = ?, pin_zamani = ?, hatali_sayi = 0, hatali_ilk = NULL, kilitli = 0 WHERE ogretmen_id = ?",
        (guvenlik.parola_ozetle(pin), an, ogretmen_id),
    )
    oturumlari_dusur(b, ogretmen_id)
    return pin


# ---- öğrenci aktarma (önizleme bellekte; ayrıştırma eokul.py) ------------------------------------
class OnizlemeDeposu:
    """Ayrıştırılmış öğrenci listesi yalnız bellekte, rastgele belirteçle, 15 dk (ortak sözlük §7).

    Belirteç kullanıcıya bağlıdır ve tek kullanımlıktır; sunucuda yalnız özetiyle tutulur.
    """

    def __init__(self):
        self.kayitlar: dict[str, tuple[float, int, dict]] = {}

    def _temizle(self) -> None:
        simdi = time.monotonic()
        self.kayitlar = {k: v for k, v in self.kayitlar.items() if v[0] > simdi}

    def koy(self, kullanici_id: int, veri: dict) -> str:
        self._temizle()
        belirtec = guvenlik.belirtec()
        self.kayitlar[guvenlik.ozet(belirtec)] = (time.monotonic() + ONIZLEME_OMRU_SN, kullanici_id, veri)
        return belirtec

    def al(self, belirtec, kullanici_id: int) -> dict | None:
        self._temizle()
        if not isinstance(belirtec, str) or not belirtec:
            return None
        anahtar = guvenlik.ozet(belirtec)
        kayit = self.kayitlar.get(anahtar)
        if not kayit or kayit[1] != kullanici_id:
            return None
        del self.kayitlar[anahtar]
        return kayit[2]

    def bosalt(self) -> None:
        self.kayitlar.clear()


def aktarim_plani(b, ayristirma: dict) -> dict:
    """Önizleme: şube başına Dosyada · Eklenecek · Şubesi değişecek · Pasifleşecek (+ ad listeleri). Yazmaz."""
    mevcut = {o["okul_no"]: o for o in b.execute("SELECT * FROM ogrenci")}
    dosya_nolari = {s["okul_no"] for s in ayristirma["satirlar"]}
    dosya_subeleri = {s["sube"] for s in ayristirma["satirlar"]}
    subeler: dict[str, dict] = {}

    def sube(ad: str) -> dict:
        return subeler.setdefault(ad, {"sube": ad, "dosyada": 0, "eklenecek": [], "sube_degisecek": [], "pasiflesecek": [],
                                       "guncellenecek": 0})  # fmt: skip

    for s in ayristirma["satirlar"]:
        kayit = sube(s["sube"])
        kayit["dosyada"] += 1
        eski = mevcut.get(s["okul_no"])
        etiket = f"{s['okul_no']} {s['ad']} {s['soyad']}".strip()
        if not eski:
            kayit["eklenecek"].append(etiket)
        elif eski["sube"] != s["sube"] and eski["aktif"]:
            kayit["sube_degisecek"].append(f"{etiket} ({eski['sube']} → {s['sube']})")
        elif (eski["ad"], eski["soyad"], eski["sube"], eski["aktif"]) != (s["ad"], s["soyad"], s["sube"], 1):
            kayit["guncellenecek"] += 1
    for o in mevcut.values():
        if o["aktif"] and o["sube"] in dosya_subeleri and o["okul_no"] not in dosya_nolari:
            sube(o["sube"])["pasiflesecek"].append(f"{o['okul_no']} {ad_soyad(o)}")
    liste = sorted(subeler.values(), key=lambda x: sube_anahtari(x["sube"]))
    return {
        "subeler": liste,
        "toplam": {
            "dosyada": sum(x["dosyada"] for x in liste),
            "eklenecek": sum(len(x["eklenecek"]) for x in liste),
            "sube_degisecek": sum(len(x["sube_degisecek"]) for x in liste),
            "pasiflesecek": sum(len(x["pasiflesecek"]) for x in liste),
            "guncellenecek": sum(x["guncellenecek"] for x in liste),
        },
    }


def ogrenci_aktar(b, ayristirma: dict, kullanici: str, an: int) -> dict:
    """Tek işlemde uygular (çağıran `vt.islem()` içinde). Dosyadaki şube tam liste sayılır.

    Döndürür: {"sube_sayisi","eklenen","guncellenen","pasif","atlanan"} (yalnız sayılar).
    """
    mevcut = {o["okul_no"]: o for o in b.execute("SELECT * FROM ogrenci")}
    eklenen = guncellenen = 0
    for s in ayristirma["satirlar"]:
        eski = mevcut.get(s["okul_no"])
        if not eski:
            b.execute(
                "INSERT INTO ogrenci (sube, okul_no, ad, soyad, aktif, guncelleme) VALUES (?, ?, ?, ?, 1, ?)",
                (s["sube"], s["okul_no"], s["ad"], s["soyad"], an),
            )
            eklenen += 1
        elif (eski["ad"], eski["soyad"], eski["sube"], eski["aktif"]) != (s["ad"], s["soyad"], s["sube"], 1):
            b.execute(
                "UPDATE ogrenci SET sube = ?, ad = ?, soyad = ?, aktif = 1, guncelleme = ? WHERE id = ?",
                (s["sube"], s["ad"], s["soyad"], an, eski["id"]),
            )
            guncellenen += 1
    subeler = sorted({s["sube"] for s in ayristirma["satirlar"]})
    nolar = {s["okul_no"] for s in ayristirma["satirlar"]}
    pasif = 0
    for sube in subeler:
        for o in b.execute("SELECT id, okul_no FROM ogrenci WHERE sube = ? AND aktif = 1", (sube,)).fetchall():
            if o["okul_no"] not in nolar:
                b.execute("UPDATE ogrenci SET aktif = 0, guncelleme = ? WHERE id = ?", (an, o["id"]))
                pasif += 1
    sonuc = {"sube_sayisi": len(subeler), "eklenen": eklenen, "guncellenen": guncellenen, "pasif": pasif,
             "atlanan": len(ayristirma["atlanan"])}  # fmt: skip
    b.execute(
        "INSERT INTO ogrenci_aktarim (zaman, kullanici, bicim, sube_sayisi, eklenen, guncellenen, pasif, atlanan) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (an, kullanici, ayristirma["bicim"], sonuc["sube_sayisi"], eklenen, guncellenen, pasif, sonuc["atlanan"]),
    )
    return sonuc


def hepsini_sil(b) -> tuple[int, int]:
    """Yıl sonu: bütün yoklama, öğrenci, e-Okul işareti ve yoklama oturumları. (öğrenci, yoklama) sayıları.

    Çağıran işlemden sonra `vt.wal_buda()`.
    """
    ogrenci = b.execute("SELECT COUNT(*) FROM ogrenci").fetchone()[0]
    yoklama_ = b.execute("SELECT COUNT(*) FROM yoklama").fetchone()[0]
    b.execute("DELETE FROM yoklama")  # CASCADE: yoklama_yok, yoklama_iz
    b.execute("DELETE FROM yoklama_belirtec")
    b.execute("DELETE FROM eokul_islendi")
    b.execute("DELETE FROM ogrenci")
    return ogrenci, yoklama_


# ---- imha ----------------------------------------------------------------------------------------
def imha(b, an: int) -> dict:
    """Öğretim yılı bitiş tarihi geçtiyse o tarihe kadarki yoklamalar (+ iz, yok satırları, e-Okul işaretleri),
    referanssız pasif öğrenciler, süresi dolan oturumlar; 24 saati geçen hatalı deneme sayaçları sıfırlanır
    (kilit kalkmaz). Bitiş tarihi girilmemişse yoklama silinmez (K3, `saklama.py`).

    Silinen > 0 ise işlem kaydı (yalnız sayılar). Çağıran işlemden sonra `vt.wal_buda()`.
    """
    sinir = saklama.imha_siniri(b, bugun(an))
    kayit = 0
    usb = {"silinen": 0, "bosaltilan": 0}
    if sinir:
        from . import usb_anahtar  # döngüsel içe aktarma olmasın (usb_anahtar bu modülü kullanır)

        kayit = b.execute("DELETE FROM yoklama WHERE tarih <= ?", (sinir.isoformat(),)).rowcount
        b.execute("DELETE FROM eokul_islendi WHERE tarih <= ?", (sinir.isoformat(),))
        # 0.11.0 §7: iptal edilmiş USB anahtarları silinir, etkinlerin son kullanım bilgisi boşaltılır.
        usb = usb_anahtar.yil_sonu(b, sinir)
    ogrenci = b.execute(
        "DELETE FROM ogrenci WHERE aktif = 0 AND NOT EXISTS (SELECT 1 FROM yoklama_yok yy WHERE yy.ogrenci_id = ogrenci.id)"
    ).rowcount
    b.execute("DELETE FROM yoklama_belirtec WHERE bitis <= ?", (an,))
    b.execute(
        "UPDATE ogretmen_pin SET hatali_sayi = 0, hatali_ilk = NULL WHERE hatali_ilk IS NOT NULL AND hatali_ilk <= ?",
        (an - OGRETMEN_PENCERE_SN,),
    )
    if kayit or ogrenci:
        ayrinti = f"{kayit} kayıt, {ogrenci} öğrenci"
        if kayit:
            ayrinti += f" (öğretim yılı bitişi {saklama.tarih_metni(sinir)})"
        vt.kayit_dus(b, "sistem", "Yoklama imhası", ayrinti)
    if usb["silinen"] or usb["bosaltilan"]:
        vt.kayit_dus(b, "sistem", "USB anahtar yıl sonu temizliği",
                     f"{usb['silinen']} iptal edilmiş anahtar silindi, {usb['bosaltilan']} anahtarın son kullanım bilgisi silindi")  # fmt: skip
    return {"kayit": kayit, "ogrenci": ogrenci, "usb": usb["silinen"] + usb["bosaltilan"]}


class YoklamaZamanlayici:
    """Ortak sözlük §2.3 listesinde 6. iş ("yoklama_imha"): saatte en çok bir kez imha."""

    def calistir(self, b, an: int) -> bool:
        son = vt.ayar_al(b, "yoklama_imha_son_tur", 0) or 0
        if isinstance(son, (int, float)) and 0 <= an - son < IMHA_ARALIGI_SN:
            return False
        vt.ayar_yaz(b, "yoklama_imha_son_tur", an)
        sonuc = imha(b, an)
        return bool(sonuc["kayit"] or sonuc["ogrenci"] or sonuc["usb"])
