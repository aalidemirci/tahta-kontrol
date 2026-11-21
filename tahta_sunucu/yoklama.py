"""Ders yoklaması (Aşama 5): iş mantığı (FastAPI'siz; testle sınanır).

Güven modeli: öğretmen kod (3 hane, gizli değil) + PIN (6 hane) ile yalnız yoklama için kimlik
kanıtlar; PIN yalnız sunucuda scrypt özetiyle durur, tahtaya ne PIN ne özeti gider. Belirteç
sunucuda `guvenlik.ozet` ile saklanır, tahtada yalnız yönetici yetkili serviste durur.
Öğrenci verisi tahtaya yalnız PIN sonrası, yalnız seçilen şube için `maske.sinif_etiketleri`
etiketleriyle iner (ortak sözlük §6). İşlem kaydına (`kayit`) öğrenci adı ve numarası yazılmaz;
öğrenci kimliği gereken iz `yoklama_iz`'dedir ve yoklamayla birlikte imha edilir.

0.14.0: "geç" ayrı tablodadır (`yoklama_gec`; yalnız devrenin ilk dersinde), kayıt anındaki devre `yoklama.devre`e
yazılır. Bir ders saatinin GEÇERLİ durumu tek kuraldan gelir (`gecerli_durum`, `yoklama_defter.Veri`): hücrede panel
düzeltmesi (en son kayıttan eski değilse) varsa o, yoksa en son kaydedilen kayıt. Şube defteri, son günler ve mazeret/izin `yoklama_defter.py`dedir.

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
GEC_YETENEGI = "yoklama_gec"  # 0.14.0: ajan "geç" işaretini ve yeni öneri alanlarını anlıyor (tests/yoklama_sozlesme.json)

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
ILETI_GEC_ILK_DERS = "Geç yalnız ilk derste işaretlenir."
ILETI_HEM_YOK_HEM_GEC = "Bir öğrenci hem yok hem geç işaretlenemez."

# 0.14.0 — öneri sınırları (tests/yoklama_sozlesme.json "sinirlar")
SUBELER_ONCE_ONERI = 3  # /oneri: yalnız tahtanın şubeleri
SUBELER_ONCE_BASLAT = 4  # /baslat, /ajan/usb/yoklama: öğretmenin bugünkü şubeleri
DEVRE_ESLEME_PAYI_DK = 5  # öğretmen programındaki başlangıç saati plan devresiyle bu payla eşlenir

# 0.14.0 — mazeret/izin katmanı. Serbest açıklama YOKTUR (sağlık verisi birikmesin); tür yalnız mazeret
# sayfasında ve öğrenci görünümünün mazeret bölümünde görünür, başka her yerde tek "özürlü" (Ö).
MAZERET_TURLERI = {"izinli": "İzinli", "raporlu": "Raporlu", "mazeretli": "Mazeretli",
                   "gorevli": "Görevli (nöbet, yarışma, gezi, okul görevi)"}  # fmt: skip
MAZERET_IPTAL = "iptal"
MAZERET_DAYANAKLARI = {"": "Belirtilmedi", "dilekce": "Veli dilekçesi", "yazi": "Kurum yazısı", "belge": "Belge sunuldu",
                       "idare": "İdare izni"}  # fmt: skip

GUN_ADLARI = program_mod.GUN_ADLARI
# 0.21.0: 'baskan' = sınıf başkanı USB anahtarıyla tahtadan alınan kayıt (deneme; yardımcı kayıt). Sütunda CHECK yoktur.
KAYNAK_ADI = {"tahta": "Tahta", "panel": "Panel", "baskan": "Sınıf başkanı"}
KAYNAK_BASKAN = "baskan"
BASKAN_NOTU = "Sınıf başkanı kaydı deneme amaçlı yardımcı kayıttır; öğretmenin yoklamasının yerine geçmez."
ILETI_BASKAN_OGRETMEN_ALDI = "Bu dersin yoklaması öğretmen tarafından alınmış."
ILETI_BASKAN_IDARE_DUZELTTI = "Bu dersin yoklaması idare tarafından düzeltilmiş."
ILETI_BASKAN_DERS = "Sınıf başkanı yalnız şu anki dersin yoklamasını alabilir."
ILETI_BASKAN_ZIL_YOK = "Zil saatleri tanımlı olmadığı için sınıf başkanı yoklama alamaz."
ILETI_BASKAN_DERS_YOK = "Bugün zil düzeninde ders yok; sınıf başkanı yoklama alamaz."
ILETI_BASKAN_DEVRE_YOK = (
    "Şubenin bugünkü devresi (sabah/öğle) belirlenemedi; derslik programı yüklenmeden sınıf başkanı yoklama alamaz."
)
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


def devre_saatleri(plan: dict, devre: str | None) -> list[dict]:
    """Planın bir devresinin ders saatleri: [{"ders_no","baslangic","bitis","bas","bit"}] (bas/bit epoch)."""
    sonuc: dict[int, dict] = {}
    for d in plan.get("dersler") or []:
        if d[0] == devre and d[2] not in sonuc:
            sonuc[d[2]] = {"ders_no": d[2], "baslangic": f"{d[3]:%H:%M}", "bitis": f"{d[4]:%H:%M}",
                           "bas": int(d[3].timestamp()), "bit": int(d[4].timestamp())}  # fmt: skip
    return [sonuc[n] for n in sorted(sonuc)]


def program_devresi(plan: dict, satirlar) -> str | None:
    """Öğretmen programı satırlarından ([(ders_no, "SS:DD")]) şubenin devresi: ders numarası ve başlangıç saati
    (±5 dk) tutan plan dersi en çok olan TEK devre; eşitlik ya da eşleşme yoksa None (saf)."""
    sayac: dict[str, int] = {}
    for no, baslangic in satirlar:
        try:
            dakika = program_mod.dk(str(baslangic))
        except (ValueError, TypeError, IndexError):
            continue
        for d in plan.get("dersler") or []:
            if d[2] == no and abs(d[3].hour * 60 + d[3].minute - dakika) <= DEVRE_ESLEME_PAYI_DK:
                sayac[d[0]] = sayac.get(d[0], 0) + 1
    if not sayac:
        return None
    en_cok = max(sayac.values())
    adaylar = [d for d, n in sayac.items() if n == en_cok]
    return adaylar[0] if len(adaylar) == 1 else None


def devre_sec(plan: dict, derslik_devreleri: set[str], program_satirlari) -> str | None:
    """Şubenin devresi (saf; kural 25). Sıra: derslik programındaki devre (tekse) → günde tek devre varsa o →
    öğretmen programı satırlarının saatleri (`program_devresi`). Belirlenemezse None.
    `program_satirlari` çağrılabilir de olabilir (yalnız gerekince okunsun)."""
    tum_devreler = {d[0] for d in plan.get("dersler") or []}
    if not tum_devreler:
        return None
    devreler = derslik_devreleri & tum_devreler
    if len(devreler) == 1:
        return next(iter(devreler))
    if devreler:
        return None  # şube iki devrede birden görünüyor: seçim yapılmaz
    if len(tum_devreler) == 1:
        return next(iter(tum_devreler))
    satirlar = program_satirlari() if callable(program_satirlari) else program_satirlari
    return program_devresi(plan, satirlar or [])


def sube_devresi(b, plan: dict, sube: str | None) -> str | None:
    """Şubenin o günkü devresi: `tahta_ders` → tek devre → öğretmen programındaki o şube-gün satırlarının saatleri
    (yalnız ders no ve başlangıç saati okunur; ders adı ve öğretmen sorguya girmez). Belirlenemezse None:
    ders saati 1–12 serbest seçilir."""

    def satirlar():
        if not sube:
            return []
        return [(s["ders_no"], s["baslangic"]) for s in b.execute(
            "SELECT DISTINCT ders_no, baslangic FROM ogretmen_program WHERE sube = ? AND gun = ?", (sube, plan["program_gunu"]))]  # fmt: skip

    return devre_sec(plan, _sube_devreleri(b, plan, sube) if sube else set(), satirlar)


def program_ders_saatleri(b, tarih: date, sube: str | None, plan: dict | None = None) -> list[dict]:
    """O gün şubenin devresine ait ders saatleri: [{"ders_no","baslangic","bitis","bas","bit"}] (bas/bit epoch).

    Devre `sube_devresi` ile bulunur; belirlenemezse (ikili öğretimde programsız şube) boş liste: ders saati
    1–12 serbest seçilir.
    """
    plan = plan or _plan(b, tarih)
    devre = sube_devresi(b, plan, sube)
    return devre_saatleri(plan, devre) if devre is not None else []


def pencere_devresi(plan: dict, an: int) -> str | None:
    """Şubesiz istekte devre: tek devreli günde o devre; ikili eğitimde penceresi (ilk ders − 5 dk … son ders
    + 15 dk) şu anı kapsayan TEK devre. İki pencere çakışıyorsa (devir saati) ya da hiçbiri kapsamıyorsa None."""
    sinirlar: dict[str, list[int]] = {}
    for d in plan.get("dersler") or []:
        bas, bit = int(d[3].timestamp()), int(d[4].timestamp())
        s = sinirlar.setdefault(d[0], [bas, bit])
        s[0], s[1] = min(s[0], bas), max(s[1], bit)
    if len(sinirlar) == 1:
        return next(iter(sinirlar))
    kapsayan = [d for d, (bas, bit) in sinirlar.items() if bas - GELECEK_PAYI_SN <= an <= bit + ALINMADI_PAYI_SN]
    return kapsayan[0] if len(kapsayan) == 1 else None


def ders_kurali(saatler: list[dict], an: int, biten_dahil: bool = True) -> tuple[int | None, list[int]]:
    """Ön seçilecek ders (saf): (ders_no | None, adaylar).

    1) süren ders; 2) yoksa 5 dk içinde başlayacak; 3) yoksa son 15 dk içinde bitmiş ders. 2 ve 3 birlikte
    tutuyorsa (teneffüs) ders seçilmez, adaylar = [biten, baslayacak] döner. `biten_dahil=False` (yoklama_gec
    yeteneği olmayan ajan): 3. kural ve adaylar uygulanmaz.
    """
    suren = next((s["ders_no"] for s in saatler if s["bas"] <= an < s["bit"]), None)
    if suren is not None:
        return suren, []
    baslayacak = next((s["ders_no"] for s in saatler if 0 < s["bas"] - an <= GELECEK_PAYI_SN), None)
    biten = None
    if biten_dahil:
        biten = next((s["ders_no"] for s in reversed(saatler) if 0 <= an - s["bit"] <= ALINMADI_PAYI_SN), None)
    if baslayacak is not None and biten is not None and baslayacak != biten:
        return None, [biten, baslayacak]
    return (baslayacak if baslayacak is not None else biten), []


def ilk_ders_mi(saatler: list[dict], ders_no: int) -> bool:
    """ "Geç" kuralı (saf): ders, devrenin o günkü EN KÜÇÜK numaralı dersi mi; ders saati bilinmiyorsa ders_no == 1."""
    return ders_no == (min(s["ders_no"] for s in saatler) if saatler else 1)


def gec_secilebilir(b, gun: date, sube: str, ders_no: int, plan: dict | None = None) -> bool:
    """ "Geç" yalnız şubenin devresinin o günkü İLK dersinde işaretlenir (sabah ve öğle devresi ayrı ayrı)."""
    return ilk_ders_mi(program_ders_saatleri(b, gun, sube, plan), ders_no)


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


def oneri(b, tahta, an: int, sube_istegi: str | None = None, yetenekli: bool = False) -> dict:
    """/ajan/yoklama/oneri yanıtı (öğrenci verisi İÇERMEZ; hiçbir öğretmene bağlı DEĞİLDİR).

    Şube önerisi sırası: programdaki şu anki ders (`tahta_ders.sube`) → tahtada 5 dk içinde başlayacak ya da
    15 dk içinde bitmiş ders → `tahta.subeler` tek şubeyse o (ikili eğitimde birden çok şube varsa devresi şu an
    süren tek şube) → None. Ders numarası şubenin kendi devresinin numarasıdır (kural 25) ve `ders_kurali` ile
    seçilir: süren → 5 dk içinde başlayacak → son 15 dk içinde biten; teneffüste iki aday varsa `ders_no` None,
    `ders_adaylari` = [biten, baslayacak]. `sube_istegi` verilirse ders saatleri ve ders önerisi o şubenindir
    (öğretmen şubeyi elle seçti). Şubesiz ve önerisiz istekte ders saatleri `pencere_devresi`nden gelir;
    belirsizse boş döner. `yetenekli` = tahta `yoklama_gec` bildiriyor; bildirmeyen eski ajana "biten ders"
    önerilmez ve `ders_adaylari` hep boştur (yanıtın anahtar kümesi yine aynıdır).
    Ders saatlerinde `secilebilir`: başlangıcı şimdi + 5 dk'dan önce (tahtanın saatine güvenilmez).
    """
    gun = bugun(an)
    plan = _plan(b, gun)
    su_an = program_su_an(b, tahta, an)
    if not su_an:
        try:
            su_an = _yakin_ders(b, tahta, plan, an)  # şube önerisi; ders numarası aşağıda ders_kurali ile
        except Exception:  # öneri yardımcıdır; bozuk program yoklamayı durdurmasın
            su_an = None
    tum_tahta_subeleri = tahta_subeleri_(tahta)
    tahta_subeleri = tum_tahta_subeleri
    if len(tahta_subeleri) > 1:
        tahta_subeleri = _devresi_suren_subeler(b, gun, tahta_subeleri, an, plan)
    sube = (su_an or {}).get("sube") or (tahta_subeleri[0] if len(tahta_subeleri) == 1 else None)
    hedef_sube = metin.sube_duzelt(sube_istegi) if sube_istegi else sube
    devre = sube_devresi(b, plan, hedef_sube) if hedef_sube else pencere_devresi(plan, an)
    saatler = devre_saatleri(plan, devre) if devre is not None else []
    simdiki, adaylar = ders_kurali(saatler, an, biten_dahil=yetenekli)
    ders_no = simdiki if hedef_sube else None
    if not hedef_sube:
        adaylar = []
    try:
        odanin_dersleri = _tahtanin_dersleri(b, tahta, plan)
    except Exception:
        odanin_dersleri = []
    if adaylar:
        # Bu derslikte o şubenin yalnız bir adayda dersi varsa (derslik programı) o derstir.
        odadaki = {d[2] for d in odanin_dersleri if d[0] == devre and metin.sube_duzelt(d[5] or "") == hedef_sube}
        kalan = [n for n in adaylar if n in odadaki]
        if len(kalan) == 1:
            ders_no, adaylar, simdiki = kalan[0], [], kalan[0]
    yakinlik: dict[str, int] = {}
    for d in odanin_dersleri:
        ad = metin.sube_duzelt(d[5] or "")
        if ad:
            bas, bit = int(d[3].timestamp()), int(d[4].timestamp())
            uzaklik = 0 if bas <= an < bit else min(abs(bas - an), abs(an - bit))
            yakinlik[ad] = min(yakinlik.get(ad, uzaklik), uzaklik)
    odadakiler = sorted(yakinlik, key=lambda x: (yakinlik[x], sube_anahtari(x)))
    subeler_once = list(dict.fromkeys(x for x in [sube, *odadakiler, *tum_tahta_subeleri] if x))[:SUBELER_ONCE_ONERI]
    cok_devre = len({d[0] for d in plan.get("dersler") or []}) > 1
    devre_adi = next((d[1] for d in plan.get("dersler") or [] if d[0] == devre), "") if cok_devre and saatler else ""
    return {
        "etkin": True,
        "tarih": gun.isoformat(),
        "tarih_yazi": tarih_yazi(gun),
        "ders_saatleri": [
            {"ders_no": s["ders_no"], "baslangic": s["baslangic"], "bitis": s["bitis"], "secilebilir": s["bas"] <= an + GELECEK_PAYI_SN}
            for s in saatler
        ],
        "ders_no_en_cok": max((s["ders_no"] for s in saatler), default=DERS_NO_EN_COK),
        "oneri": {"sube": sube, "ders_no": ders_no, "ders_adi": "", "ogretmen": None, "ders_adaylari": adaylar if yetenekli else []},
        "subeler": aktif_subeler(b),
        "subeler_once": subeler_once,
        "devre_adi": devre_adi,
        "simdiki_ders_no": simdiki,
        # "Şimdi" işaretli ders az önce bitmiş bir ders mi (kural 3): tahta "şimdi" yerine "bitti" yazar.
        "simdiki_bitti": simdiki is not None and any(s["ders_no"] == simdiki and s["bit"] <= an for s in saatler),
    }


def ogretmen_onerisi(b, ogretmen_id: int | None, tahta, an: int, yetenekli: bool = False) -> dict:
    """/baslat ve /ajan/usb/yoklama yanıtına eklenen, PIN/USB ile doğrulanan öğretmenin programından gelen ön seçim:
    {"oneri": {"sube","ders_no"|None,"ders_adaylari"} | None, "subeler_once": [≤ 4]}.

    `ogretmen_program`dan yalnız sube, gun, ders_no, baslangic, bitis SEÇİLİR; ders adı ve öğretmen adı sorguya
    girmez. Program yalnız ÖN SEÇİMDİR, hiçbir şube/ders seçimini engellemez. Kimlik eşleşmesi olmayan oturumda
    (idare USB anahtarı) ikisi de boştur.
    """
    bos = {"oneri": None, "subeler_once": []}
    if not ogretmen_id:
        return bos
    gun = bugun(an)
    plan = _plan(b, gun)
    if plan.get("tatil"):
        return bos
    satirlar = b.execute(
        "SELECT sube, gun, ders_no, baslangic, bitis FROM ogretmen_program WHERE ogretmen_id = ? AND gun = ? ORDER BY baslangic, ders_no",
        (ogretmen_id, plan["program_gunu"]),
    ).fetchall()
    dersler = []  # [{"sube","ders_no","bas","bit"}]: saatler şubenin devresinin planından; yoksa satırın kendi saatinden
    saat_onbellek: dict[str, dict[int, dict]] = {}
    for s in satirlar:
        sube = metin.sube_duzelt(s["sube"]) or s["sube"]
        if sube not in saat_onbellek:
            saat_onbellek[sube] = {x["ders_no"]: x for x in program_ders_saatleri(b, gun, sube, plan)}
        planli = saat_onbellek[sube].get(s["ders_no"])
        if planli:
            bas, bit = planli["bas"], planli["bit"]
        else:
            try:
                bas = int(program_mod.an_dt(gun, s["baslangic"]).timestamp())
                bit = int(program_mod.an_dt(gun, s["bitis"]).timestamp())
            except (ValueError, TypeError, IndexError):
                continue
        dersler.append({"sube": sube, "ders_no": s["ders_no"], "bas": bas, "bit": bit})
    if not dersler:
        return bos
    dersler.sort(key=lambda d: (d["bas"], d["ders_no"]))
    yakin: dict[str, int] = {}
    for d in dersler:
        uzaklik = 0 if d["bas"] <= an < d["bit"] else min(abs(d["bas"] - an), abs(an - d["bit"]))
        yakin[d["sube"]] = min(yakin.get(d["sube"], uzaklik), uzaklik)
    suren = next((d for d in dersler if d["bas"] <= an < d["bit"]), None)
    baslayacak = next((d for d in dersler if 0 < d["bas"] - an <= GELECEK_PAYI_SN), None)
    biten = next((d for d in reversed(dersler) if 0 <= an - d["bit"] <= ALINMADI_PAYI_SN), None) if yetenekli else None
    secilen = None
    if suren:
        secilen = {"sube": suren["sube"], "ders_no": suren["ders_no"], "ders_adaylari": []}
    elif baslayacak and biten:
        if baslayacak["sube"] == biten["sube"]:  # aynı şubede iki ders art arda: hangisi olduğu bilinemez
            secilen = {"sube": biten["sube"], "ders_no": None, "ders_adaylari": [biten["ders_no"], baslayacak["ders_no"]]}
        else:
            # Farklı şubeler: tahtanın (kişiden bağımsız) önerdiği şubeyle aynı olan; o da yoksa başlayacak ders.
            try:
                tahta_subesi = oneri(b, tahta, an, None, yetenekli)["oneri"]["sube"] if tahta is not None else None
            except Exception:
                tahta_subesi = None
            d = biten if tahta_subesi == biten["sube"] else baslayacak
            secilen = {"sube": d["sube"], "ders_no": d["ders_no"], "ders_adaylari": []}
    elif baslayacak or biten:
        d = baslayacak or biten
        secilen = {"sube": d["sube"], "ders_no": d["ders_no"], "ders_adaylari": []}
    sirali = sorted(yakin, key=lambda x: (x != (secilen or {}).get("sube"), yakin[x], sube_anahtari(x)))
    return {"oneri": secilen, "subeler_once": sirali[:SUBELER_ONCE_BASLAT]}


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

    Öğretmen oturumu (`ogretmen_id`; kod + PIN ya da öğretmen USB anahtarı), idare oturumu (`kullanici_id`; yalnız
    idare USB anahtarı) ya da (0.21.0) sınıf başkanı oturumu (ikisi de boş, yalnız `anahtar_id`: şube anahtarı).
    `anahtar_id` doluysa oturum o anahtarla açılmıştır (anahtar iptal edilince düşer). 0.6.0'daki konumsal çağrı
    biçimi (ilk argüman ogretmen_id) korunur.
    """
    if ogretmen_id is not None and kullanici_id is not None:
        raise ValueError("Oturum ya öğretmenin ya idarenin olmalı.")
    if ogretmen_id is None and kullanici_id is None and anahtar_id is None:
        raise ValueError("Oturum ya öğretmenin ya idarenin ya da bir şube anahtarının olmalı.")
    if ogretmen_id is not None:
        b.execute("DELETE FROM yoklama_belirtec WHERE (ogretmen_id = ? AND tahta_id = ?) OR bitis <= ?", (ogretmen_id, tahta_id, an))
    elif kullanici_id is not None:
        b.execute("DELETE FROM yoklama_belirtec WHERE (kullanici_id = ? AND tahta_id = ?) OR bitis <= ?", (kullanici_id, tahta_id, an))
    else:
        b.execute(
            "DELETE FROM yoklama_belirtec WHERE (anahtar_id = ? AND ogretmen_id IS NULL AND kullanici_id IS NULL AND tahta_id = ?) "
            "OR bitis <= ?",
            (anahtar_id, tahta_id, an),
        )
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
    Sınıf başkanı oturumu (0.21.0): anahtar şube anahtarı ve Ayarlar'da başkan anahtarları açık (kapatılınca açık
    oturum da anında geçersizdir). USB anahtarla açılmışsa anahtar `etkin` olmalı (iptal ya da PIN kilidi oturumu düşürür).
    Satır: belirtec_ozet, bitis, ogretmen_id, kullanici_id, anahtar_id, ad, soyad, kod, tur ('ogretmen'|'idare'|'baskan'),
    kullanici_ad, gorunen_ad, anahtar_kimlik, baskan_sube.
    """
    if not isinstance(belirtec, str) or not belirtec or len(belirtec) > 200:
        return None
    satir = b.execute(
        "SELECT y.belirtec_ozet, y.bitis, y.ogretmen_id, y.kullanici_id, y.anahtar_id, o.ad, o.soyad, p.kod, "
        "CASE WHEN y.kullanici_id IS NOT NULL THEN 'idare' WHEN y.ogretmen_id IS NOT NULL THEN 'ogretmen' ELSE 'baskan' END AS tur, "
        "k.ad AS kullanici_ad, k.gorunen_ad, a.kimlik AS anahtar_kimlik, a.sube AS baskan_sube FROM yoklama_belirtec y "
        "LEFT JOIN ogretmen o ON o.id = y.ogretmen_id LEFT JOIN ogretmen_pin p ON p.ogretmen_id = y.ogretmen_id "
        "LEFT JOIN kullanici k ON k.id = y.kullanici_id LEFT JOIN usb_anahtar a ON a.id = y.anahtar_id "
        "WHERE y.belirtec_ozet = ? AND y.tahta_id = ? AND y.bitis > ? "
        "AND ((y.ogretmen_id IS NOT NULL AND o.aktif = 1 AND p.kilitli = 0) "
        "  OR (y.kullanici_id IS NOT NULL AND k.aktif = 1 AND k.rol IN ('yonetici', 'idareci')) "
        "  OR (y.ogretmen_id IS NULL AND y.kullanici_id IS NULL AND a.sahip_turu = 'sube' AND a.sube IS NOT NULL)) "
        "AND (y.anahtar_id IS NULL OR a.durum = 'etkin')",
        (guvenlik.ozet(belirtec), tahta_id, an),
    ).fetchone()
    if satir is not None and satir["tur"] == "baskan":
        from . import usb_anahtar  # döngüsel içe aktarma olmasın (usb_anahtar bu modülü kullanır)

        if not usb_anahtar.baskan_acik(usb_anahtar.ayar_al(b)):
            return None
    return satir


def oturum_kaydedeni(oturum, tahta_ad: str) -> tuple[int | None, str, str]:
    """Tahtadan alınan yoklamanın (ogretmen_id, kaydeden, iz `kim`) üçlüsü, oturumun türüne göre.

    Öğretmen: (id, 'ogretmen:112', 'ogretmen:112 (tahta:X)'); idare: (None, 'kullanici:mdryrd', …); sınıf başkanı
    (0.21.0): (None, 'baskan:10/A', …). USB anahtarla açılan oturumda iz metnine ' USB K7Q2M9XA' eklenir
    (kayit_ayrintisi bunu okur).
    """
    if oturum["tur"] == "baskan":
        ogretmen_id, kaydeden = None, f"baskan:{oturum['baskan_sube']}"
    elif oturum["tur"] == "idare":
        ogretmen_id, kaydeden = None, f"kullanici:{oturum['kullanici_ad']}"
    else:
        ogretmen_id, kaydeden = oturum["ogretmen_id"], f"ogretmen:{oturum['kod']}"
    kim = f"{kaydeden} (tahta:{tahta_ad})"
    if oturum["anahtar_kimlik"]:
        kim += f" USB {oturum['anahtar_kimlik']}"
    return ogretmen_id, kaydeden, kim


def oturum_kaynagi(oturum) -> str:
    """Tahtadan yazılan kaydın `kaynak`ı: sınıf başkanı oturumunda 'baskan', öbürlerinde 'tahta'."""
    return KAYNAK_BASKAN if oturum["tur"] == "baskan" else "tahta"


def baskan_denetle(b, tahta, oturum, sube: str, ders_no: int, an: int) -> tuple[int, str] | None:
    """Sınıf başkanı oturumunun dar yetkisi (0.21.0; /liste ve /kaydet ikisinde de). (HTTP kodu, ileti) ya da None.

    Sıra: 1) yalnız anahtarın şubesi (400: ajan seçime döner); 2) yalnız bu şubenin tahtası: `tahta.subeler` şubeyi
    içeriyor ya da derslik programı bu ders saatinde şubeyi bu tahtaya koyuyor (409); 3) yalnız `ders_kurali`
    penceresindeki ders: süren, 5 dk içinde başlayacak ya da son 15 dk'da biten (pencere dışı 400; ders saati
    bulunamazsa 409, nedeni ayrı iletiyle: zil yok, bugün ders yok, şubenin devresi belirsiz); 4) öğretmen önceliği
    (C1): o ders saatinde başka kaynaklı (öğretmen, idare, panel) kayıt, şube defteri düzeltmesi ya da başkan
    kaydının kayıt sayfasından düzeltilmesi (`yoklama_iz.islem = 'duzelt'`) varsa 409. Başkanın kendi kaydı
    ('baskan') engel değildir. Kural 33'ün (program yalnız ön seçimdir) BİLİNÇLİ istisnasıdır; öğretmen, idare ve
    panel yolları değişmez.
    """
    baskan_sube = oturum["baskan_sube"]
    if sube != baskan_sube:
        return 400, f"Bu anahtar yalnız {baskan_sube} için yoklama alır."
    gun = bugun(an)
    plan = _plan(b, gun)
    tahta_subeleri = tahta_subeleri_(tahta)
    if sube not in tahta_subeleri:
        try:
            devre = sube_devresi(b, plan, sube)
            odadaki = any(
                d[2] == ders_no and metin.sube_duzelt(d[5] or "") == sube and (devre is None or d[0] == devre)
                for d in _tahtanin_dersleri(b, tahta, plan)
            )
        except Exception:  # bozuk program: yetki verilmez
            odadaki = False
        if not odadaki:
            if not tahta_subeleri:
                return 409, f"Bu tahtaya şube atanmamış; {sube} sınıf başkanı yoklamayı yalnız kendi dersliğindeki tahtada alır."
            return 409, f"Bu tahta {sube} şubesinin dersliği değil."
    saatler = program_ders_saatleri(b, gun, sube, plan)
    if not saatler:
        # Neden ayrı söylenir: zil hiç yok / bugün ders yok (tatil) / ikili eğitimde şubenin devresi belirsiz.
        if plan.get("dersler"):
            return 409, ILETI_BASKAN_DEVRE_YOK
        if b.execute("SELECT 1 FROM ders_saati LIMIT 1").fetchone():
            return 409, ILETI_BASKAN_DERS_YOK
        return 409, ILETI_BASKAN_ZIL_YOK
    pencere = {
        s["ders_no"] for s in saatler
        if s["bas"] <= an < s["bit"] or 0 < s["bas"] - an <= GELECEK_PAYI_SN or 0 <= an - s["bit"] <= ALINMADI_PAYI_SN
    }  # fmt: skip
    if ders_no not in pencere:
        return 400, ILETI_BASKAN_DERS
    tarih = gun.isoformat()
    if b.execute(
        "SELECT 1 FROM yoklama WHERE tarih = ? AND sube = ? AND ders_no = ? AND kaynak != ? LIMIT 1", (tarih, sube, ders_no, KAYNAK_BASKAN)
    ).fetchone():
        return 409, ILETI_BASKAN_OGRETMEN_ALDI
    if b.execute("SELECT 1 FROM yoklama_duzeltme WHERE tarih = ? AND sube = ? AND ders_no = ? LIMIT 1", (tarih, sube, ders_no)).fetchone():
        return 409, ILETI_BASKAN_IDARE_DUZELTTI
    # İdare başkan kaydını kayıt sayfasından ("Düzelt") düzelttiyse kayıt yine 'baskan' kaynaklıdır ve yoklama_duzeltme'ye
    # satır girmez; düzeltme yalnız izde görünür. O da şube defterindeki düzeltme gibi başkanı engeller.
    if b.execute(
        "SELECT 1 FROM yoklama_iz z JOIN yoklama y ON y.id = z.yoklama_id WHERE y.tarih = ? AND y.sube = ? AND y.ders_no = ? "
        "AND y.kaynak = ? AND z.islem = 'duzelt' LIMIT 1",
        (tarih, sube, ders_no, KAYNAK_BASKAN),
    ).fetchone():
        return 409, ILETI_BASKAN_IDARE_DUZELTTI
    return None


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


def gec_listesi(b, yoklama_id: int) -> list[int]:
    return sorted(s["ogrenci_id"] for s in b.execute("SELECT ogrenci_id FROM yoklama_gec WHERE yoklama_id = ?", (yoklama_id,)))


def gecerli_durum(b, tarih: str, sube: str, ders_no: int) -> tuple[set[int], set[int], bool]:
    """Bir ders saatinin GEÇERLİ durumu: (yok, geç, alındı mı). Tek birleşim kuralı (`yoklama_defter.Veri`):
    hücrede en yeni panel düzeltmesi (en son kayıttan eski değilse) varsa o; yoksa o ders saatinin EN SON KAYDEDİLEN
    yoklama kaydı.
    Mazeret durumu değiştirmez (ayrı katmandır). Tahtanın `/liste` yanıtı ve yeteneksiz ajanın kaydı bunu kullanır."""
    from . import yoklama_defter

    gun = tarih_coz(tarih)
    if not gun:
        return set(), set(), False
    veri = yoklama_defter.Veri(b, gun, gun, sube)
    yok, gec = veri.kumeler(tarih, sube, ders_no)
    return set(yok), set(gec), veri.alindi(tarih, sube, ders_no)


def yoklama_yaz(
    b, *, tarih: str, sube: str, ders_no: int, ogretmen_id: int | None, kaynak: str, kaydeden: str,
    tahta_id: int | None, yok: list[int], kim: str, an: int, islem: str | None = None, aciklama: str = "",
    gec: list[int] | None = None,
) -> tuple[int, bool]:  # fmt: skip
    """Upsert (tarih, şube, ders saati, öğretmen, kaynak) + `yoklama_yok` ve `yoklama_gec` yeniden yazılır +
    `yoklama_iz` farkı. Gövde, kaydedenin gördüğü TAM durumdur ve yalnız kendi kaydına yazılır; aynı ders saatinin
    başka kaydına dokunulmaz (geçerli durum = en son kaydedilen kayıt, `gecerli_durum`).

    `gec=None` (geç bilgisi taşımayan form ya da `yoklama_gec` yeteneği olmayan ajan): ders saatinin geçerli
    durumundaki geç öğrenciler bu kayda da geç yazılır; yalnız yeni `yok`a girenler geçten çıkar (geç yalnız
    devrenin ilk dersindeyse korunur). `devre` her yazmada şubenin o günkü devresiyle doldurulur (bulunamazsa '').
    Bir öğrenci aynı kayıtta hem yok hem geç olamaz (ValueError).
    Döndürür: (yoklama_id, yeni_mi). `mevcut` kayıt anındaki şubenin etkin öğrenci sayısıdır.
    """
    yeni = set(yok)
    gun = tarih_coz(tarih)
    plan = _plan(b, gun) if gun else {"dersler": [], "program_gunu": 0}
    devre = sube_devresi(b, plan, sube) or ""
    if gec is None:
        ilk = ilk_ders_mi(devre_saatleri(plan, devre) if devre else [], ders_no)
        yeni_gec = (gecerli_durum(b, tarih, sube, ders_no)[1] - yeni) if ilk else set()
    else:
        yeni_gec = set(gec)
    if yeni & yeni_gec:
        raise ValueError(ILETI_HEM_YOK_HEM_GEC)
    mevcut = b.execute("SELECT COUNT(*) FROM ogrenci WHERE sube = ? AND aktif = 1", (sube,)).fetchone()[0]
    eski = _yoklama_bul(b, tarih, sube, ders_no, ogretmen_id, kaynak)
    if eski:
        yoklama_id = eski["id"]
        onceki = set(yok_listesi(b, yoklama_id))
        onceki_gec = set(gec_listesi(b, yoklama_id))
        b.execute(
            "UPDATE yoklama SET kaydeden = ?, tahta_id = COALESCE(?, tahta_id), mevcut = ?, guncelleme = ?, devre = ? WHERE id = ?",
            (kaydeden, tahta_id, mevcut, an, devre, yoklama_id),
        )
        b.execute("DELETE FROM yoklama_yok WHERE yoklama_id = ?", (yoklama_id,))
        b.execute("DELETE FROM yoklama_gec WHERE yoklama_id = ?", (yoklama_id,))
    else:
        onceki, onceki_gec = set(), set()
        yoklama_id = b.execute(
            "INSERT INTO yoklama (tarih, ders_no, sube, ogretmen_id, ders_adi, tahta_id, kaynak, kaydeden, mevcut, olusturma, "
            "guncelleme, devre) VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?, ?)",
            (tarih, ders_no, sube, ogretmen_id, tahta_id, kaynak, kaydeden, mevcut, an, an, devre),
        ).lastrowid
    b.executemany("INSERT INTO yoklama_yok (yoklama_id, ogrenci_id) VALUES (?, ?)", [(yoklama_id, i) for i in sorted(yeni)])
    b.executemany("INSERT INTO yoklama_gec (yoklama_id, ogrenci_id) VALUES (?, ?)", [(yoklama_id, i) for i in sorted(yeni_gec)])
    b.execute(
        "INSERT INTO yoklama_iz (yoklama_id, zaman, kim, islem, eklenen, cikarilan, aciklama, gec_eklenen, gec_cikarilan) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (yoklama_id, an, kim, islem or ("guncelle" if eski else "olustur"),
         json.dumps(sorted(yeni - onceki)), json.dumps(sorted(onceki - yeni)), aciklama[:ACIKLAMA_EN_UZUN],
         json.dumps(sorted(yeni_gec - onceki_gec)), json.dumps(sorted(onceki_gec - yeni_gec))),
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


def kayit_metni(sube: str, ders_no: int, yok_sayisi: int, kod: str | None = None, tarih: date | None = None,
                gec_sayisi: int = 0) -> str:  # fmt: skip
    """İşlem kaydı ayrıntısı: şube, ders saati, sayı, öğretmen kodu (ad ve okul no YOK)."""
    parca = [f"{tarih_kisa(tarih)} " if tarih else "", f"{sube} {ders_no}. ders, {yok_sayisi} yok"]
    if gec_sayisi:
        parca.append(f", {gec_sayisi} geç")
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


def alan_etiketi(y) -> str:
    """Yoklamayı alan: öğretmen etiketi, "idare (kullanıcı adı)" (idare USB anahtarı, 0.11.0), "sınıf başkanı"
    (0.21.0) ya da "panel"."""
    if y["kaynak"] == KAYNAK_BASKAN:
        return "sınıf başkanı"
    if y["ogretmen_id"] and y["ogretmen_ad"] is not None:
        return ogretmen_etiketi(y["ogretmen_ad"], y["ogretmen_soyad"])
    kaydeden = str(y["kaydeden"] or "")
    if y["kaynak"] == "tahta" and not y["ogretmen_id"] and kaydeden.startswith("kullanici:"):
        return f"idare ({kaydeden.removeprefix('kullanici:')})"
    return "panel" if y["kaynak"] == "panel" else "?"


def gunluk_gorunum(b, gun: date, an: int) -> dict:
    """/yoklama sayfasının verisi (şube × ders saati ızgarası, özet, öğrenci bazında liste).

    Sayılar tek birleşim kuralından (`yoklama_defter.Veri.kumeler`) gelir: hücrede (kayıttan eski olmayan) panel düzeltmesi varsa o,
    yoksa o ders saatinin en son kaydedilen kaydı. Mazeretli yokluk da "yok" sayılır (yok toplamı değişmez)."""
    from . import yoklama_defter

    tarih = gun.isoformat()
    veri = yoklama_defter.Veri(b, gun, gun)
    plan = veri.plan(gun)
    yoklamalar = _gunun_yoklamalari(b, tarih)
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
    bayat = yoklama_defter.eokul_bayat(b, veri, tarih, islenen)
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
                yok_k, gec_k = veri.kumeler(tarih, s, n)
                ipucu = [aralik] if aralik else []
                if len(ks) > 1:
                    ipucu.append(f"{len(ks)} kayıt; en son kaydedilen geçerli")
                ipucu.append("Alan: " + ", ".join(alan_etiketi(k) for k in ks))
                en_son = max(ks, key=lambda k: (k["guncelleme"], k["id"]))
                hucreler.append({"ders_no": n, "durum": "alindi", "yok": len(yok_k), "gec": len(gec_k), "kayit_id": en_son["id"],
                                 "kayit_sayisi": len(ks), "baslik": " · ".join(ipucu)})  # fmt: skip
            elif n in dersli and dersli[n]["bit"] and dersli[n]["bit"] + ALINMADI_PAYI_SN <= an:
                hucreler.append({"ders_no": n, "durum": "alinmadi", "yok": None, "gec": 0, "kayit_id": None, "kayit_sayisi": 0,
                                 "baslik": " · ".join(p for p in (aralik, "Programda ders var; yoklama alınmadı") if p)})  # fmt: skip
            else:
                hucreler.append({"ders_no": n, "durum": "bos", "yok": None, "gec": 0, "kayit_id": None, "kayit_sayisi": 0,
                                 "baslik": aralik})  # fmt: skip
        satirlar.append({
            "sube": s,
            "devre_adi": sube_devre_adi(b, plan, s),
            "hucreler": hucreler,
            "islendi": s in islenen,
            "bayat": s in bayat,
            "islendi_metni": f"{islenen[s]['kullanici']}, {an_yazi(islenen[s]['zaman'])}" if s in islenen else "",
        })  # fmt: skip
    # Öğrenci bazında: (şube, öğrenci) → yok olduğu ders saatleri; "bütün gün yok" = şubenin yoklaması alınan bütün saatlerde yok
    alinan_saatler: dict[str, set[int]] = {}
    ogrenci_saat: dict[tuple[str, int], set[int]] = {}
    for sube, no in kayitlar:
        alinan_saatler.setdefault(sube, set()).add(no)
        for oid in veri.kumeler(tarih, sube, no)[0]:
            ogrenci_saat.setdefault((sube, oid), set()).add(no)
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


def _ogrenci_satirlari(b, ogrenci_saat: dict[tuple[str, int], set[int]], alinan_saatler: dict[str, set[int]],
                       gec_saat: dict[tuple[str, int], set[int]] | None = None,
                       ozurlu_saat: dict[tuple[str, int], set[int]] | None = None) -> list[dict]:  # fmt: skip
    """(şube, öğrenci) → yok olduğu ders saatleri kümelerinden satırlar; `gec_saat` verilirse yalnız geç kalan
    öğrenci de satır olur. `ozurlu_saat`: yok saatlerinden geçerli mazeret kapsamında olanlar (tür taşımaz)."""
    gec_saat, ozurlu_saat = gec_saat or {}, ozurlu_saat or {}
    anahtarlar = set(ogrenci_saat) | set(gec_saat)
    if not anahtarlar:
        return []
    idler = sorted({oid for (_, oid) in anahtarlar})
    ogrenciler: dict[int, object] = {}
    for i in range(0, len(idler), 500):
        parca = idler[i : i + 500]
        for o in b.execute(f"SELECT * FROM ogrenci WHERE id IN ({','.join('?' * len(parca))})", parca):
            ogrenciler[o["id"]] = o
    satirlar = []
    for sube, oid in anahtarlar:
        o = ogrenciler.get(oid)
        if not o:
            continue
        saatler = ogrenci_saat.get((sube, oid), set())
        gec = gec_saat.get((sube, oid), set())
        ozurlu = ozurlu_saat.get((sube, oid), set()) & saatler
        alinan = alinan_saatler.get(sube, set())
        satirlar.append({
            "sube": sube, "ogrenci_id": oid, "okul_no": o["okul_no"], "ad": o["ad"], "soyad": o["soyad"],
            "ad_soyad": ad_soyad(o), "saatler": sorted(saatler), "saatler_metni": ", ".join(map(str, sorted(saatler))),
            "sayi": len(saatler), "alinan": len(alinan), "butun_gun": bool(alinan) and bool(saatler) and saatler >= alinan,
            "gec_saatler": sorted(gec), "gec_sayisi": len(gec), "ozurlu_saatler": sorted(ozurlu), "ozurlu_sayisi": len(ozurlu),
        })  # fmt: skip
    return sorted(satirlar, key=lambda r: (sube_anahtari(r["sube"]), no_anahtari(r["okul_no"])))


def icmal(b, gun: date, sube: str | None = None) -> dict:
    """Gün sonu icmali: şube başına yok/geç listesi (tek birleşim kuralı; `yoklama.sube`'ye göre).

    Hücre: Y yok · Ö yok ve geçerli mazeret kapsamında ("özürlü"; tür hiçbir çıktıya girmez) · G geç · . derste ·
    - yoklama alınmadı. Yok toplamı özürlü yokları da sayar."""
    from . import yoklama_defter

    tarih = gun.isoformat()
    veri = yoklama_defter.Veri(b, gun, gun)
    plan = veri.plan(gun)
    yoklamalar = _gunun_yoklamalari(b, tarih)
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
        devre = veri.devre(gun, s)
        ogrenci_saat: dict[tuple[str, int], set[int]] = {}
        gec_saat: dict[tuple[str, int], set[int]] = {}
        ozurlu_saat: dict[tuple[str, int], set[int]] = {}
        for n in alinan:
            yok_k, gec_k = veri.kumeler(tarih, s, n)
            for oid in yok_k:
                ogrenci_saat.setdefault((s, oid), set()).add(n)
                if veri.mazeret_kapsar(oid, tarih, n, devre):
                    ozurlu_saat.setdefault((s, oid), set()).add(n)
            for oid in gec_k:
                gec_saat.setdefault((s, oid), set()).add(n)
        ogrenciler = []
        for r in _ogrenci_satirlari(b, ogrenci_saat, {s: set(alinan)}, gec_saat, ozurlu_saat):
            hucreler = []
            for n in range(1, sutun + 1):
                if n not in alinan:
                    hucreler.append("-")
                elif n in r["saatler"]:
                    hucreler.append("Ö" if n in r["ozurlu_saatler"] else "Y")
                else:
                    hucreler.append("G" if n in r["gec_saatler"] else ".")
            ogrenciler.append({**r, "hucreler": hucreler})
        alanlar = []
        for n in range(1, sutun + 1):
            bu = [y for y in ks if y["ders_no"] == n]
            alanlar.append({"ders_no": n, "metin": ", ".join(dict.fromkeys(alan_etiketi(y) for y in bu)) if bu else "(alınmadı)",
                            "baskan": any(y["kaynak"] == KAYNAK_BASKAN for y in bu)})  # fmt: skip
        mevcut = b.execute("SELECT COUNT(*) FROM ogrenci WHERE sube = ? AND aktif = 1", (s,)).fetchone()[0]
        mevcut = mevcut or max([y["mevcut"] for y in ks] + [0])
        sonuc.append({
            "sube": s, "devre_adi": sube_devre_adi(b, plan, s), "mevcut": mevcut, "sutunlar": list(range(1, sutun + 1)), "alinan": alinan,
            "alinan_metni": aralik_yaz(alinan) if alinan else "yok", "alinmayan": alinmayan,
            "alinan_sayisi": len(alinan), "sutun_sayisi": sutun, "ogrenciler": ogrenciler, "alanlar": alanlar,
            "program_bilinir": program_bilinir,
            "gec_var": any(o["gec_sayisi"] for o in ogrenciler), "ozurlu_var": any(o["ozurlu_sayisi"] for o in ogrenciler),
            "baskan_var": any(y["kaynak"] == KAYNAK_BASKAN for y in ks),
        })  # fmt: skip
    return {"tarih": tarih, "tarih_yazi": tarih_yazi(gun), "tarih_kisa": tarih_kisa(gun), "subeler": sonuc,
            "baskan_var": any(s["baskan_var"] for s in sonuc), "baskan_notu": BASKAN_NOTU}  # fmt: skip


def icmal_metni(veri: dict) -> str:
    """Kopyalanabilir düz metin (sekmeyle ayrılmış; şube başlıklı). Geç ve özürlü saatler varsa satır sonuna eklenir."""
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
            parcalar = [o["okul_no"], o["ad_soyad"], ",".join(map(str, o["saatler"])), str(o["sayi"])]
            if o.get("gec_saatler"):
                parcalar.append("geç: " + ",".join(map(str, o["gec_saatler"])))
            if o.get("ozurlu_saatler"):
                parcalar.append("özürlü: " + ",".join(map(str, o["ozurlu_saatler"])))
            satirlar.append("\t".join(parcalar))
    return "\n".join(satirlar) + "\n"


# Yeni sütunlar SONA eklenir (var olanların sırası değişmez). Mazeret türü CSV'ye girmez.
ICMAL_CSV_BASLIKLARI = ["Tarih", "Şube", "Okul No", "Adı", "Soyadı", "Yok Ders Saatleri", "Yok Ders Saati Sayısı",
                        "Yoklama Alınan Ders Saati Sayısı", "Geç Sayısı", "Özürlü Yok Sayısı"]  # fmt: skip


def icmal_csv(veri: dict) -> bytes:
    satirlar = [
        [veri["tarih_kisa"], s["sube"], o["okul_no"], o["ad"], o["soyad"], ",".join(map(str, o["saatler"])), o["sayi"], s["alinan_sayisi"],
         o.get("gec_sayisi", 0), o.get("ozurlu_sayisi", 0)]  # fmt: skip
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
    gecler = set(gec_listesi(b, yoklama_id))
    liste = {o["id"]: o for o in sube_ogrencileri(b, y["sube"])}
    if (yoklar | gecler) - set(liste):
        eksik = sorted((yoklar | gecler) - set(liste))
        for o in b.execute(f"SELECT * FROM ogrenci WHERE id IN ({','.join('?' * len(eksik))})", eksik):
            liste[o["id"]] = o
    adlar = {i: ad_soyad(o) for i, o in liste.items()}
    izler = []
    usb = False
    usb_kimlikleri = set()
    for iz in b.execute("SELECT * FROM yoklama_iz WHERE yoklama_id = ? ORDER BY id", (yoklama_id,)):
        # Ek yalnız iz metninin SONUNDA aranır: tahta adı serbest metindir ("Lab USB 2" gibi).
        usb = usb or bool(_USB_IZ_EKI.search(str(iz["kim"])))
        if _USB_IZ_EKI.search(str(iz["kim"])):
            usb_kimligi = str(iz["kim"]).rsplit(" ", 1)[1]
            usb_kimlikleri.add(usb_kimligi[:4] + "-" + usb_kimligi[4:])
        eklenen, cikarilan = json.loads(iz["eklenen"] or "[]"), json.loads(iz["cikarilan"] or "[]")
        izler.append({
            "zaman": an_yazi(iz["zaman"]), "kim": iz["kim"], "islem": IZ_ISLEM_ADI.get(iz["islem"], iz["islem"]),
            "eklenen": [adlar.get(i, f"#{i}") for i in eklenen], "cikarilan": [adlar.get(i, f"#{i}") for i in cikarilan],
            "gec_eklenen": [adlar.get(i, f"#{i}") for i in json.loads(iz["gec_eklenen"] or "[]")],
            "gec_cikarilan": [adlar.get(i, f"#{i}") for i in json.loads(iz["gec_cikarilan"] or "[]")],
            "aciklama": iz["aciklama"],
        })  # fmt: skip
    gun = tarih_coz(y["tarih"])
    beklenen = []
    if gun:
        program_gunu = program_mod.gun_plani(b, gun)["program_gunu"]
        beklenen = [dict(o) for o in b.execute(
            "SELECT DISTINCT o.id, o.ad, o.soyad FROM ogretmen_program p JOIN ogretmen o ON o.id = p.ogretmen_id "
            "WHERE p.sube = ? AND p.gun = ? AND p.ders_no = ? ORDER BY o.id",
            (y["sube"], program_gunu, y["ders_no"]),
        )]
    if y["kaynak"] == "panel":
        kaynak = f"panel: {y['kaydeden']}"
    elif y["kaynak"] == KAYNAK_BASKAN:
        kaynak = (f"tahta: {y['tahta_ad']}" if y["tahta_ad"] else "tahta (kaldırılmış)") + " · sınıf başkanı anahtarı"
        if usb:
            kaynak += " · USB anahtar"
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
        "usb_kimlikleri": sorted(usb_kimlikleri),
        "program_ogretmenleri": [" ".join((o["ad"], o["soyad"])) for o in beklenen],
        # Başkan kaydında öğretmen yoktur: "eşleşmiyor" (nöbet/ders değişimi) sayılmaz, şablon ayrı not çizer.
        "program_eslesiyor": (any(o["id"] == y["ogretmen_id"] for o in beklenen)
                              if beklenen and y["kaynak"] != KAYNAK_BASKAN else None),  # fmt: skip
        "kaynak": kaynak,
        "kaynak_turu": y["kaynak"],
        "baskan": y["kaynak"] == KAYNAK_BASKAN,
        "baskan_notu": BASKAN_NOTU,
        "olusturma": an_yazi(y["olusturma"]),
        "guncelleme": an_yazi(y["guncelleme"]),
        "mevcut": y["mevcut"],
        "yok_sayisi": len(yoklar),
        "gec_sayisi": len(gecler),
        # Geç kutusu yalnız devrenin ilk dersinde (ya da kayıtta zaten geç varsa) gösterilir.
        "gec_secilebilir": bool(gun and gec_secilebilir(b, gun, y["sube"], y["ders_no"])),
        "ogrenciler": [
            {"id": o["id"], "okul_no": o["okul_no"], "ad_soyad": ad_soyad(o), "yok": o["id"] in yoklar, "gec": o["id"] in gecler,
             "pasif": not o["aktif"]}  # fmt: skip
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
        # Yerinde silinir: zamanlayıcı iş parçacığı temizlerken panelin o an eklediği kayıt kaybolmasın.
        simdi = time.monotonic()
        for anahtar in [k for k, v in list(self.kayitlar.items()) if v[0] <= simdi]:
            self.kayitlar.pop(anahtar, None)

    def koy(self, kullanici_id: int, veri: dict, omur_sn: int = ONIZLEME_OMRU_SN) -> str:
        self._temizle()
        belirtec = guvenlik.belirtec()
        self.kayitlar[guvenlik.ozet(belirtec)] = (time.monotonic() + omur_sn, kullanici_id, veri)
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

    def suresi_dolanlari_sil(self) -> None:
        """Zamanlayıcıdan çağrılır: süresi dolan önizleme bir sonraki erişimi beklemeden bellekten düşer."""
        self._temizle()

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


def hepsini_sil(b) -> tuple[int, int, int]:
    """Yıl sonu: bütün yoklama, öğrenci, e-Okul işareti, yoklama oturumları ve sınıf başkanı USB anahtarları.
    (öğrenci, yoklama, başkan anahtarı) sayıları.

    0.21.0: şube (başkan) anahtarı yetkisini "şubede etkin öğrenci var mı" diye canlı hesaplar; silinmezse geçen
    yılın anahtarı yeni yılın aynı adlı şubesinde yeniden çalışırdı (`usb_anahtar.yil_sonu` ile aynı ilke: başkan her
    yıl değişir). Öğretmen ve idare anahtarlarına dokunulmaz. Çağıran işlemden sonra `vt.wal_buda()`.
    """
    ogrenci = b.execute("SELECT COUNT(*) FROM ogrenci").fetchone()[0]
    yoklama_ = b.execute("SELECT COUNT(*) FROM yoklama").fetchone()[0]
    baskan = b.execute("DELETE FROM usb_anahtar WHERE sahip_turu = 'sube'").rowcount  # CASCADE: başkan oturumları
    # Sıra bağlayıcıdır: öğrenciye giden yabancı anahtarlar CASCADE'siz (yok, geç, düzeltme, mazeret); önce onlar.
    b.execute("DELETE FROM yoklama_yok")
    b.execute("DELETE FROM yoklama_gec")
    b.execute("DELETE FROM yoklama")  # CASCADE: yoklama_iz
    b.execute("DELETE FROM yoklama_duzeltme")
    b.execute("DELETE FROM yoklama_mazeret")
    b.execute("DELETE FROM yoklama_belirtec")
    b.execute("DELETE FROM eokul_islendi")
    b.execute("DELETE FROM ogrenci")
    return ogrenci, yoklama_, baskan


# ---- imha ----------------------------------------------------------------------------------------
def imha(b, an: int) -> dict:
    """Öğretim yılı bitiş tarihi geçtiyse o tarihe kadarki yoklamalar (+ iz, yok satırları, e-Okul işaretleri),
    referanssız pasif öğrenciler, süresi dolan oturumlar; 24 saati geçen hatalı deneme sayaçları sıfırlanır
    (kilit kalkmaz). Bitiş tarihi girilmemişse yoklama silinmez (K3, `saklama.py`).

    Silinen > 0 ise işlem kaydı (yalnız sayılar). Çağıran işlemden sonra `vt.wal_buda()`.
    """
    sinir = saklama.imha_siniri(b, bugun(an))
    kayit = 0
    katman = 0
    program_sayisi = 0
    usb = {"silinen": 0, "bosaltilan": 0}
    if sinir:
        from . import usb_anahtar  # döngüsel içe aktarma olmasın (usb_anahtar bu modülü kullanır)

        kayit = b.execute("DELETE FROM yoklama WHERE tarih <= ?", (sinir.isoformat(),)).rowcount  # CASCADE: yok, geç, iz
        # 0.14.0: panel düzeltmeleri ve mazeretler de öğrenci kimliği taşır. Aralığı sınırı aşan mazeret de
        # bütünüyle silinir (başlangıcı eski yılda kalan kayıt yeni yıla taşınmaz).
        katman = b.execute("DELETE FROM yoklama_duzeltme WHERE tarih <= ?", (sinir.isoformat(),)).rowcount
        katman += b.execute("DELETE FROM yoklama_mazeret WHERE bas_tarih <= ?", (sinir.isoformat(),)).rowcount
        b.execute("DELETE FROM eokul_islendi WHERE tarih <= ?", (sinir.isoformat(),))
        # Öğretmen programında eski yılın kişi bağlantıları süresiz tutulmaz.
        program_sinir = int(datetime.combine(sinir + timedelta(days=1), datetime.min.time(), ISTANBUL).timestamp())
        program_sayisi = b.execute("DELETE FROM ogretmen_program WHERE guncelleme < ?", (program_sinir,)).rowcount
        if program_sayisi:
            vt.ayar_yaz(b, "ogretmen_program_surum", int(vt.ayar_al(b, "ogretmen_program_surum", 0)) + 1)
            vt.kayit_dus(b, "sistem", "Öğretmen programı yıl sonu temizliği", f"{program_sayisi} ders satırı")
        # 0.11.0 §7: iptal edilmiş USB anahtarları silinir, etkinlerin son kullanım bilgisi boşaltılır.
        usb = usb_anahtar.yil_sonu(b, sinir)
    ogrenci = b.execute(
        "DELETE FROM ogrenci WHERE aktif = 0 "
        "AND NOT EXISTS (SELECT 1 FROM yoklama_yok yy WHERE yy.ogrenci_id = ogrenci.id) "
        "AND NOT EXISTS (SELECT 1 FROM yoklama_gec yg WHERE yg.ogrenci_id = ogrenci.id) "
        "AND NOT EXISTS (SELECT 1 FROM yoklama_duzeltme yd WHERE yd.ogrenci_id = ogrenci.id) "
        "AND NOT EXISTS (SELECT 1 FROM yoklama_mazeret ym WHERE ym.ogrenci_id = ogrenci.id)"
    ).rowcount
    b.execute("DELETE FROM yoklama_belirtec WHERE bitis <= ?", (an,))
    b.execute(
        "UPDATE ogretmen_pin SET hatali_sayi = 0, hatali_ilk = NULL WHERE hatali_ilk IS NOT NULL AND hatali_ilk <= ?",
        (an - OGRETMEN_PENCERE_SN,),
    )
    if kayit or ogrenci or katman:
        ayrinti = f"{kayit} kayıt, {ogrenci} öğrenci"
        if katman:
            ayrinti += f", {katman} düzeltme/mazeret"
        if kayit or katman:
            ayrinti += f" (öğretim yılı bitişi {saklama.tarih_metni(sinir)})"
        vt.kayit_dus(b, "sistem", "Yoklama imhası", ayrinti)
    if usb["silinen"] or usb["bosaltilan"] or usb.get("baskan"):
        ayrinti = f"{usb['silinen']} iptal edilmiş anahtar silindi, {usb['bosaltilan']} anahtarın son kullanım bilgisi silindi"
        if usb.get("baskan"):
            ayrinti += f", {usb['baskan']} sınıf başkanı anahtarı silindi"
        vt.kayit_dus(b, "sistem", "USB anahtar yıl sonu temizliği", ayrinti)
    return {"kayit": kayit, "ogrenci": ogrenci, "usb": usb["silinen"] + usb["bosaltilan"] + usb.get("baskan", 0), "program": program_sayisi,
            "katman": katman}  # fmt: skip


class YoklamaZamanlayici:
    """Ortak sözlük §2.3 listesinde 6. iş ("yoklama_imha"): saatte en çok bir kez imha."""

    def calistir(self, b, an: int) -> bool:
        son = vt.ayar_al(b, "yoklama_imha_son_tur", 0) or 0
        if isinstance(son, (int, float)) and 0 <= an - son < IMHA_ARALIGI_SN:
            return False
        vt.ayar_yaz(b, "yoklama_imha_son_tur", an)
        sonuc = imha(b, an)
        return bool(sonuc["kayit"] or sonuc["ogrenci"] or sonuc["usb"] or sonuc["program"] or sonuc["katman"])
