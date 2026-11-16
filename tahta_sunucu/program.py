"""Ders programı: zil saatleri, takvim, derslik programı ve kilit aralıkları (saf işlevler).

Bu modül veritabanı bilmez (yalnız en altta `ders_saatleri_oku`, `gun_plani` ve
`simdiki_ders` bağlantı alır; Aşama 5 bunları okur). Saatler `SS:DD` metni, günler
0=Pazartesi … 6=Pazar (Okul Zili ile aynı). Bütün hesap Europe/Istanbul saatiyle yapılır;
tahtanın saatine güvenilmez.

Okul Zili'nden yalnız ders saatleri ve takvim alınır; ses, okul adı, cihaz gibi alanlar
okunmaz ve saklanmaz. Öğretmen ve ders adı hiçbir yerde tutulmaz (KVKK md. 4/2-ç).
"""

from __future__ import annotations

import hashlib
import hmac
import io
import json
import re
import zipfile
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import metin

ISTANBUL = ZoneInfo("Europe/Istanbul")

# ---- sabitler (ayar değil: seçenek azaltmak için) ---------------------------------------
PROGRAM_YETENEGI = "program_kilidi"  # sürüm karşılaştırması yapılmaz (ortak sözlük §5.2)
EN_KISA_KILIT_SN = 180
KILIT_KOMUT_OMRU_SN = 120
ISARET_SAKLAMA_GUN = 2
ISTISNA_SAKLAMA_GUN = 400
ISTISNA_EN_UZUN_GUN = 400
ISTISNA_NEDEN_EN_UZUN = 200
TENEFFUS_EN_UZUN_SN = 20 * 60
BOS_DERS_SUREKLILIK_SN = 120
ONIZLEME_OMRU_SN = 30 * 60
JSON_EN_COK_BAYT = 2 * 1024 * 1024
ZIP_EN_COK_BAYT = 200 * 1024 * 1024
ZIP_EN_COK_UYE = 10_000
CSV_EN_COK_BAYT = 1024 * 1024
CSV_EN_COK_SATIR = 10_000
HATA_GOSTERIM = 50
SUBE_EN_UZUN = 20
OKULZILI_SURUMLERI = (6, 7)

GUN_ADLARI = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
VARSAYILAN_DEVRE_ADI = {"normal": "Normal", "sabah": "Sabah", "ogle": "Öğleden sonra"}
NEDEN_TENEFFUS = "Teneffüs"
NEDEN_OGLE = "Öğle arası"
NEDEN_DERS_YOK = "Bu saatte bu derslikte ders yok"
BOS_NEDENLERI = {"kapali": "Kapalı", "kilitli": "Kilitli", "oturumsuz": "Oturum yok", "bosta": "Dokunulmadı"}

VARSAYILAN_KILIT = {"etkin": False, "gecikme_dk": 2, "bos_saatte_kilitle": True}
# Boş ders uyarısı varsayılan açıktır ve geçmişiyle saklanır (16.11.2026 kararı K6; saklama K3, `saklama.py`).
VARSAYILAN_BOS_DERS = {"etkin": True, "esik_dk": 10, "dokunma_yoksa": False}

# Okul Zili `holidays.py::FIXED_HOLIDAYS` listesinin kopyası; ikisi birlikte güncellenir
# (test_resmi_tatiller_okul_zili_ile_ayni). (ay, gün, ad)
RESMI_TATILLER: tuple[tuple[int, int, str], ...] = (
    (1, 1, "Yılbaşı"),
    (4, 23, "Ulusal Egemenlik ve Çocuk Bayramı"),
    (5, 1, "Emek ve Dayanışma Günü"),
    (5, 19, "Atatürk'ü Anma, Gençlik ve Spor Bayramı"),
    (7, 15, "Demokrasi ve Millî Birlik Günü"),
    (8, 30, "Zafer Bayramı"),
    (10, 29, "Cumhuriyet Bayramı"),
)
ARIFE_SAATI = time(13, 0)

# Tarih kuralı öncelikleri (Okul Zili ile aynı sıra); tören ders saatini değiştirmez, alınmaz.
KURAL_ONCELIGI = {"tarihe_ozel_program": 60, "sinav": 50, "telafi": 40, "kisaltilmis_gun": 30, "tatil": 20}
KURAL_ADI = {
    "tatil": "tatil", "tarihe_ozel_program": "tarihe özel program", "telafi": "telafi",
    "kisaltilmis_gun": "kısaltılmış gün", "sinav": "sınav", "sinav_plani": "planlı sınav",
}  # fmt: skip


# ---- saat yardımcıları ------------------------------------------------------------------
def dk(saat: str) -> int:
    return int(saat[:2]) * 60 + int(saat[3:5])


def saat_metni(dakika: int) -> str:
    return f"{dakika // 60:02d}:{dakika % 60:02d}"


def saat_dogrula(deger) -> str | None:
    """'8:20', '08.20', '08:20:00' → '08:20'; geçersizse None."""
    s = str(deger or "").strip().replace(".", ":")
    e = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", s)
    if not e or int(e.group(1)) > 23 or int(e.group(2)) > 59:
        return None
    return f"{int(e.group(1)):02d}:{e.group(2)}"


# Saatin okunuşundaki son sözcüğün bulunma eki ("10:40'ta", "10:30'da", "11:00'de").
# tahta_ajan/ekran.py::saat_eki ile aynıdır (test ikisini karşılaştırır).
_BIRLER_EKI = {1: "de", 2: "de", 3: "te", 4: "te", 5: "te", 6: "da", 7: "de", 8: "de", 9: "da"}
_ONLAR_EKI = {1: "da", 2: "de", 3: "da", 4: "ta", 5: "de"}


def saat_eki(saat: str) -> str:
    """'SS:DD' saatine Türkçe bulunma ekini ekler: '10:40' → "10:40'ta"."""
    try:
        ss, dd = (int(p) for p in str(saat).split(":"))
    except ValueError:
        return str(saat)
    sayi = dd if dd else ss
    if sayi == 0:
        ek = "da"  # sıfır
    elif sayi % 10:
        ek = _BIRLER_EKI[sayi % 10]
    else:
        ek = _ONLAR_EKI.get(sayi // 10, "de")
    return f"{saat}'{ek}"


def an_dt(gun: date, saat: str) -> datetime:
    return datetime.combine(gun, time(int(saat[:2]), int(saat[3:5])), ISTANBUL)


def devre_adi_varsayilan(devre: str) -> str:
    return VARSAYILAN_DEVRE_ADI.get(devre, devre)


def devre_kimligi(ad: str) -> str:
    """Elle girişte görünen addan kimlik: "Normal" → "normal", "Öğleden sonra" → "ogle"."""
    k = metin.katla(ad)
    if k in ("", "normal"):
        return "normal"
    if k.startswith("ogle"):
        return "ogle"
    if k.startswith("sabah"):
        return "sabah"
    return re.sub(r"[^a-z0-9]+", "_", k).strip("_")[:30] or "normal"


# ---- Okul Zili olaylarından ders saati türetme --------------------------------------------
_BLOK = re.compile(r"(\d+)\s*-\s*(\d+)\.\s*ders")
_TEK = re.compile(r"(\d+)\.\s*ders")


def ders_saatleri(olaylar: list[dict], uyarilar: list[str] | None = None, onek: str = "") -> list[tuple[str, int, str, str]]:
    """Olay listesinden (tek gün) ders saatleri: [(devre, ders_no, bas, bit)].

    Her `ders_baslangici` aynı devreli bir sonraki `ders_bitisi` ile eşlenir; aradaki
    `blok_ici_gecis`'ler bölme noktasıdır. "N-M. ders bloğu" etiketi okunur ve bölme noktası
    yoksa blok M-N+1 eşit parçaya bölünür. Etiket okunamazsa sıra numarası verilir.
    Eşi olmayan başlangıç/bitiş ve bitişi başlangıçtan önce olan ders uyarı olur.
    """
    uyarilar = uyarilar if uyarilar is not None else []
    devreler: dict[str, list[tuple[str, str, str]]] = {}
    for olay in olaylar or []:
        if not isinstance(olay, dict):
            continue
        tur = str(olay.get("event_type", ""))
        if tur not in ("ders_baslangici", "blok_ici_gecis", "ders_bitisi"):
            continue
        saat = saat_dogrula(olay.get("at"))
        if not saat:
            uyarilar.append(f"{onek}Saati okunamayan bir zil olayı atlandı.")
            continue
        devre = str(olay.get("session") or "normal").strip() or "normal"
        devreler.setdefault(devre, []).append((saat, tur, str(olay.get("label", ""))))
    sonuc: list[tuple[str, int, str, str]] = []
    sira = {"ders_bitisi": 0, "blok_ici_gecis": 1, "ders_baslangici": 2}  # aynı saatte önce bitiş
    for devre, liste in devreler.items():
        liste.sort(key=lambda o: (o[0], sira[o[1]]))
        bas: tuple[str, str] | None = None
        bolmeler: list[str] = []
        son_no = 0
        for saat, tur, etiket in liste:
            if tur == "ders_baslangici":
                if bas:
                    uyarilar.append(f"{onek}{bas[0]} ders başlangıcının bitişi yok; ders üretilmedi.")
                bas, bolmeler = (saat, etiket), []
            elif tur == "blok_ici_gecis":
                if bas:
                    bolmeler.append(saat)
            else:
                if not bas:
                    uyarilar.append(f"{onek}{saat} ders bitişinin başlangıcı yok; yok sayıldı.")
                    continue
                noktalar = [bas[0], *bolmeler, saat]
                blok = _BLOK.search(bas[1])
                tek = _TEK.search(bas[1])
                if blok and not bolmeler:
                    ilk, son = int(blok.group(1)), int(blok.group(2))
                    parca = max(1, son - ilk + 1)
                    toplam = dk(saat) - dk(bas[0])
                    noktalar = [saat_metni(dk(bas[0]) + toplam * i // parca) for i in range(parca + 1)]
                    ilk_no = ilk
                elif blok:
                    ilk_no = int(blok.group(1))
                elif tek:
                    ilk_no = int(tek.group(1))
                else:
                    ilk_no = son_no + 1
                for i in range(len(noktalar) - 1):
                    no, b_, s_ = ilk_no + i, noktalar[i], noktalar[i + 1]
                    if dk(s_) <= dk(b_):
                        uyarilar.append(f"{onek}{no}. ders: bitiş başlangıçtan önce ya da aynı; ders üretilmedi.")
                        continue
                    if not 1 <= no <= 20:
                        uyarilar.append(f"{onek}{no}. ders: ders numarası 1-20 dışında; ders üretilmedi.")
                        continue
                    sonuc.append((devre, no, b_, s_))
                    son_no = no
                bas, bolmeler = None, []
        if bas:
            uyarilar.append(f"{onek}{bas[0]} ders başlangıcının bitişi yok; ders üretilmedi.")
    sonuc.sort(key=lambda d: (d[0], d[2], d[1]))
    return sonuc


def dogrula(satirlar: list[tuple], hatalar: list[str], uyarilar: list[str]) -> None:
    """Haftalık satırlar [(gun, devre, devre_adi, no, bas, bit)] için K1–K4 denetimi.

    Aynı gün ve devrede aynı numara ya da çakışan dersler hatadır (onay engellenir);
    iki devrenin çakışması uyarıdır.
    """
    gruplar: dict[tuple[int, str], list[tuple]] = {}
    for s in satirlar:
        gruplar.setdefault((s[0], s[1]), []).append(s)
    for (gun, _devre), liste in sorted(gruplar.items()):
        liste.sort(key=lambda s: s[4])
        nolar = [s[3] for s in liste]
        if len(nolar) != len(set(nolar)):
            hatalar.append(f"{GUN_ADLARI[gun]} · {liste[0][2]}: aynı ders numarası birden çok kez geçiyor.")
        for once, sonra in zip(liste, liste[1:], strict=False):
            if dk(sonra[4]) < dk(once[5]):
                hatalar.append(
                    f"{GUN_ADLARI[gun]} · {once[2]}: {once[3]}. ders ({once[4]}–{once[5]}) ile "
                    f"{sonra[3]}. ders ({sonra[4]}–{sonra[5]}) çakışıyor."
                )
    gunler: dict[int, list[tuple]] = {}
    for (gun, devre), liste in gruplar.items():
        gunler.setdefault(gun, []).append((devre, min(dk(s[4]) for s in liste), max(dk(s[5]) for s in liste), liste[0][2]))
    for gun, aralik in sorted(gunler.items()):
        aralik.sort(key=lambda a: a[1])
        for once, sonra in zip(aralik, aralik[1:], strict=False):
            if sonra[1] < once[2]:
                uyarilar.append(f"{GUN_ADLARI[gun]}: {once[3]} ve {sonra[3]} devreleri çakışıyor; kilit hesabında birleştirilir.")


# ---- Okul Zili dosyası ----------------------------------------------------------------------
def _okulzili_zip(veri) -> bytes:
    """`.okulzili` ZIP'inden yalnız `ayarlar.json`'ı (manifestteki özetle doğrulanmış) döndürür."""
    try:
        arsiv = zipfile.ZipFile(veri)
    except (zipfile.BadZipFile, OSError) as hata:
        raise ValueError("Okul Zili yedeği okunamadı: ZIP dosyası değil.") from hata
    with arsiv:
        uyeler = arsiv.infolist()
        if len(uyeler) > ZIP_EN_COK_UYE:
            raise ValueError("Okul Zili yedeği okunamadı: dosyada çok fazla öğe var.")
        adlar = {}
        for uye in uyeler:
            ad = uye.filename
            ham = getattr(uye, "orig_filename", ad)  # Windows'ta zipfile ters bölüyü "/" yapar
            if "\\" in ham or ":" in ad or ad.startswith("/") or ".." in ad.split("/"):
                raise ValueError("Okul Zili yedeği okunamadı: güvenli olmayan dosya yolu.")
            adlar[ad] = uye
        if "manifest.json" not in adlar or "ayarlar.json" not in adlar:
            raise ValueError("Okul Zili yedeği okunamadı: manifest.json ya da ayarlar.json yok.")
        if adlar["manifest.json"].file_size > 1024 * 1024 or adlar["ayarlar.json"].file_size > JSON_EN_COK_BAYT:
            raise ValueError("Okul Zili yedeği okunamadı: yapılandırma dosyası çok büyük.")
        try:
            with arsiv.open(adlar["manifest.json"]) as f:
                manifest = json.loads(f.read(1024 * 1024 + 1).decode("utf-8"))
            with arsiv.open(adlar["ayarlar.json"]) as f:
                ayarlar = f.read(JSON_EN_COK_BAYT + 1)
        except (ValueError, UnicodeDecodeError, zipfile.BadZipFile, OSError, RuntimeError) as hata:
            raise ValueError("Okul Zili yedeği okunamadı: içerik bozuk.") from hata
    if len(ayarlar) > JSON_EN_COK_BAYT:
        raise ValueError("Okul Zili yedeği okunamadı: yapılandırma dosyası çok büyük.")
    if not isinstance(manifest, dict) or manifest.get("format") != 1:
        raise ValueError("Okul Zili yedeği okunamadı: yedek biçimi tanınmıyor.")
    beklenen = str((manifest.get("files") or {}).get("ayarlar.json", "")) if isinstance(manifest.get("files"), dict) else ""
    if not beklenen or not hmac.compare_digest(hashlib.sha256(ayarlar).hexdigest(), beklenen.lower()):
        raise ValueError("Okul Zili yedeği okunamadı: ayarlar.json özeti tutmuyor.")
    return ayarlar


def okulzili_oku(veri, dosya_adi: str = "ayarlar.json") -> dict:
    """Okul Zili `ayarlar.json` baytlarını ya da `.okulzili`/`.zip` dosyasını (bayt ya da dosya
    nesnesi) önizlemeye çevirir: {"dersler", "takvim", "uyarilar", "hatalar", "okulzili_surumu", "ozet"}.

    Okunamazsa kullanıcıya gösterilecek iletiyle ValueError. Yalnız şu alanlar okunur:
    schema_version, weekly_schedule, day_schedules (devre adları), academic_calendar, date_rules.
    """
    ad = (dosya_adi or "").lower()
    if ad.endswith(".okulzili") or ad.endswith(".zip"):
        if isinstance(veri, (bytes, bytearray)):
            veri = io.BytesIO(veri)
        ham = _okulzili_zip(veri)
    else:
        ham = veri if isinstance(veri, (bytes, bytearray)) else veri.read(JSON_EN_COK_BAYT + 1)
        if len(ham) > JSON_EN_COK_BAYT:
            raise ValueError("Okul Zili dosyası en çok 2 MB olabilir.")
    try:
        yapi = json.loads(bytes(ham).decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError) as hata:
        raise ValueError("Okul Zili dosyası okunamadı: geçerli bir JSON değil.") from hata
    if not isinstance(yapi, dict):
        raise ValueError("Okul Zili dosyası okunamadı: beklenen yapıda değil.")
    surum = yapi.get("schema_version")
    if not isinstance(surum, int) or surum not in OKULZILI_SURUMLERI:
        raise ValueError(
            f"Okul Zili yapılandırma sürümü desteklenmiyor ({surum}). Okul Zili'ni güncelleyip yeniden kaydedin."
        )
    return okulzili_yapisindan(yapi, surum)


def _devre_adlari(yapi: dict) -> dict[str, str]:
    adlar: dict[str, str] = {}
    gunluk = yapi.get("day_schedules")
    if isinstance(gunluk, dict):
        for deger in gunluk.values():
            for oturum in (deger or {}).get("sessions", []) if isinstance(deger, dict) else []:
                if isinstance(oturum, dict) and oturum.get("session_id"):
                    adlar.setdefault(str(oturum["session_id"]), " ".join(str(oturum.get("name") or "").split())[:40])
    return {k: (v or devre_adi_varsayilan(k)) for k, v in adlar.items()}


def _tarih(deger) -> str | None:
    try:
        return date.fromisoformat(str(deger)[:10]).isoformat() if deger else None
    except ValueError:
        return None


def okulzili_yapisindan(yapi: dict, surum: int = 7) -> dict:
    uyarilar: list[str] = []
    hatalar: list[str] = []
    adlar = _devre_adlari(yapi)

    def ad_bul(devre: str) -> str:
        return adlar.get(devre) or devre_adi_varsayilan(devre)

    haftalik = yapi.get("weekly_schedule") if isinstance(yapi.get("weekly_schedule"), dict) else {}
    dersler: list[tuple] = []
    for gun in range(7):
        olaylar = haftalik.get(str(gun)) or haftalik.get(gun) or []
        for devre, no, bas, bit in ders_saatleri(olaylar if isinstance(olaylar, list) else [], uyarilar, f"{GUN_ADLARI[gun]}: "):
            dersler.append((gun, devre, ad_bul(devre), no, bas, bit))
    dogrula(dersler, hatalar, uyarilar)
    tanimli = {d[0] for d in dersler}
    if not dersler:
        hatalar.append("Dosyada ders saati bulunamadı (ders başlangıç/bitiş zili yok).")
    for gun in (5, 6):
        if gun not in tanimli:
            uyarilar.append(f"{GUN_ADLARI[gun]} tanımlı değil.")

    takvim: dict = {"ogretim": None, "resmi_tatiller": False, "kurallar": []}
    ak = yapi.get("academic_calendar")
    if isinstance(ak, dict):
        donemler = [
            [_tarih(ak.get(f"term{i}_start")), _tarih(ak.get(f"term{i}_end"))]
            for i in (1, 2)
            if _tarih(ak.get(f"term{i}_start")) and _tarih(ak.get(f"term{i}_end"))
        ]
        aralar = [
            {"ad": " ".join(str(a.get("name") or "Ara tatil").split())[:60], "bas": _tarih(a.get("start")), "bit": _tarih(a.get("end"))}
            for a in (ak.get("breaks") or [])
            if isinstance(a, dict) and _tarih(a.get("start")) and _tarih(a.get("end"))
        ]

        def aralik(bas, bit):
            return [_tarih(ak.get(bas)), _tarih(ak.get(bit))] if _tarih(ak.get(bas)) and _tarih(ak.get(bit)) else None

        takvim["ogretim"] = {
            "bas": _tarih(ak.get("teaching_start")),
            "bit": _tarih(ak.get("teaching_end")),
            "donemler": donemler,
            "aralar": aralar,
            "ramazan": aralik("ramadan_start", "ramadan_end"),
            "kurban": aralik("sacrifice_start", "sacrifice_end"),
        }
        takvim["resmi_tatiller"] = bool(ak.get("official_holidays_enabled", True))
    else:
        uyarilar.append("Öğretim takvimi yok: resmî tatiller ve ara tatiller tanınmayacak; her tanımlı gün ders günü sayılır.")

    toren = 0
    for kural in yapi.get("date_rules") or []:
        if not isinstance(kural, dict) or kural.get("enabled") is False:
            continue
        tur = str(kural.get("kind", ""))
        ad = " ".join(str(kural.get("name") or "").split())[:80] or "Kural"
        bas, bit = _tarih(kural.get("start")), _tarih(kural.get("end"))
        if not bas or not bit:
            uyarilar.append(f"'{ad}' kuralının tarihi okunamadı; yok sayıldı.")
            continue
        yeni: dict = {"ad": ad, "tur": tur, "bas": bas, "bit": bit}
        if tur == "toren":
            toren += 1
            continue
        if tur == "sinav" and isinstance(kural.get("exam_plan"), dict):
            plan = kural["exam_plan"]
            try:
                onde = int(plan.get("lead_minutes", 5))
                pencereler = []
                for slot in plan.get("slots") or []:
                    s = saat_dogrula(slot.get("start"))
                    if not s:
                        continue
                    pencereler.append([saat_metni(max(0, dk(s) - onde)), saat_metni(min(24 * 60 - 1, dk(s) + int(slot.get("minutes", 0))))])
                gunler = sorted({int(g) for g in plan.get("weekdays", [0, 1, 2, 3, 4]) if 0 <= int(g) <= 6})
            except (TypeError, ValueError, AttributeError):
                uyarilar.append(f"'{ad}' sınav planı okunamadı; yok sayıldı.")
                continue
            yeni.update(tur="sinav_plani", gunler=gunler, pencereler=pencereler, tum_gun=not bool(plan.get("keep_lesson_bells", True)))
        elif tur == "telafi":
            hedef = kural.get("target_weekday")
            if not isinstance(hedef, int) or not 0 <= hedef <= 6:
                uyarilar.append(f"'{ad}' telafi kuralının hedef günü yok; yok sayıldı.")
                continue
            yeni["hedef_gun"] = hedef
        elif tur in ("tarihe_ozel_program", "kisaltilmis_gun", "sinav"):
            olaylar = kural.get("events") or []
            yeni["dersler"] = [
                [d, n, b_, s_] for d, n, b_, s_ in ders_saatleri(olaylar if isinstance(olaylar, list) else [], uyarilar, f"'{ad}': ")
            ]
            for d, *_ in yeni["dersler"]:
                adlar.setdefault(d, devre_adi_varsayilan(d))
        elif tur != "tatil":
            uyarilar.append(f"'{ad}' kuralının türü tanınmıyor ({tur}); yok sayıldı.")
            continue
        takvim["kurallar"].append(yeni)
    if toren:
        uyarilar.append(
            f"{toren} tören kuralı yok sayıldı (ders saatini değiştirmez; değiştiriyorsa Okul Zili'nde 'tarihe özel program' kullanın)."
        )
    takvim["devre_adlari"] = {**adlar, **{d[1]: d[2] for d in dersler}}
    return {
        "dersler": [list(d) for d in sorted(dersler)],
        "takvim": takvim,
        "uyarilar": uyarilar,
        "hatalar": hatalar,
        "okulzili_surumu": yapi.get("schema_version", surum),
        "ozet": takvim_ozeti(takvim),
    }


def takvim_ozeti(takvim: dict | None) -> str:
    """"Öğretim yılı: 08.09.2026–18.06.2027 · Ara tatiller: 2 · Tarih kuralları: 5 (2 tatil, …)"."""
    if not takvim:
        return ""
    parcalar = []
    og = takvim.get("ogretim")
    if og and og.get("bas") and og.get("bit"):
        parcalar.append(f"Öğretim yılı: {_gay(og['bas'])}–{_gay(og['bit'])}")
        for sira, (b, s) in enumerate(og.get("donemler") or [], start=1):
            parcalar.append(f"{sira}. dönem {_gay(b)}–{_gay(s)}")
        parcalar.append(f"Ara tatiller: {len(og.get('aralar') or [])}")
    kurallar = takvim.get("kurallar") or []
    if kurallar:
        sayilar: dict[str, int] = {}
        for k in kurallar:
            sayilar[k["tur"]] = sayilar.get(k["tur"], 0) + 1
        ayrinti = ", ".join(f"{n} {KURAL_ADI.get(t, t)}" for t, n in sorted(sayilar.items()))
        parcalar.append(f"Tarih kuralları: {len(kurallar)} ({ayrinti})")
    return " · ".join(parcalar)


def _gay(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d.%m.%Y")


# ---- elle giriş -------------------------------------------------------------------------------
def elle_uret(p: dict) -> list[tuple]:
    """Ders akışı parametrelerinden haftalık satırlar [(gun, devre, devre_adi, no, bas, bit)].

    p: devre_adi, ilk_ders (SS:DD), ders_sayisi (1–20), ders_dk (10–120), teneffus_dk (0–60),
    ogle_sonra (0 = yok, 1..ders_sayisi-1), ogle_dk (0–180), gunler (0–6 listesi).
    Hatalıysa kullanıcıya gösterilecek iletiyle ValueError.
    """
    devre_adi = " ".join(str(p.get("devre_adi") or "Normal").split())[:40] or "Normal"
    ilk = saat_dogrula(p.get("ilk_ders"))
    if not ilk:
        raise ValueError("İlk ders saati SS:DD biçiminde olmalı (ör. 08:20).")

    def sayi(ad: str, alt: int, ust: int, aciklama: str) -> int:
        try:
            deger = int(str(p.get(ad, "")).strip())
        except ValueError:
            raise ValueError(f"{aciklama} {alt}–{ust} arasında bir sayı olmalı.") from None
        if not alt <= deger <= ust:
            raise ValueError(f"{aciklama} {alt}–{ust} arasında olmalı.")
        return deger

    ders_sayisi = sayi("ders_sayisi", 1, 20, "Ders sayısı")
    ders_dk = sayi("ders_dk", 10, 120, "Ders süresi (dk)")
    teneffus = sayi("teneffus_dk", 0, 60, "Teneffüs (dk)")
    ogle_sonra = sayi("ogle_sonra", 0, 19, "Öğle arası sırası")
    ogle_dk = sayi("ogle_dk", 0, 180, "Öğle arası (dk)")
    gunler = sorted({int(g) for g in p.get("gunler") or [] if str(g).isdigit() and 0 <= int(g) <= 6})
    if not gunler:
        raise ValueError("En az bir gün seçin.")
    devre = devre_kimligi(devre_adi)
    satirlar = []
    an = dk(ilk)
    for no in range(1, ders_sayisi + 1):
        bitis = an + ders_dk
        if bitis >= 24 * 60:
            raise ValueError("Dersler gece yarısını geçiyor; ilk ders saatini ya da ders sayısını değiştirin.")
        for gun in gunler:
            satirlar.append((gun, devre, devre_adi, no, saat_metni(an), saat_metni(bitis)))
        an = bitis + (ogle_dk if ogle_sonra and no == ogle_sonra else teneffus)
    return satirlar


# ---- takvim: günün planı ------------------------------------------------------------------
def _icinde(gun: date, bas: str | None, bit: str | None) -> bool:
    return bool(bas and bit) and date.fromisoformat(bas) <= gun <= date.fromisoformat(bit)


def tatil_adi(takvim: dict, an: datetime) -> str | None:
    """Okul Zili `holiday_name` karşılığı: ara tatil, (açıksa) resmî tatil, bayram ve arife."""
    og = takvim.get("ogretim") or {}
    gun = an.date()
    for ara in og.get("aralar") or []:
        if _icinde(gun, ara.get("bas"), ara.get("bit")):
            return ara.get("ad") or "Ara tatil"
    if not takvim.get("resmi_tatiller"):
        return None
    for ay, gun_no, ad in RESMI_TATILLER:
        if (gun.month, gun.day) == (ay, gun_no):
            return ad
    if gun.month == 10 and gun.day == 28 and an.time() >= ARIFE_SAATI:
        return "Cumhuriyet Bayramı arifesi"
    for ad, aralik in (("Ramazan Bayramı", og.get("ramazan")), ("Kurban Bayramı", og.get("kurban"))):
        if aralik and aralik[0] and aralik[1]:
            bas = date.fromisoformat(aralik[0])
            if bas <= gun <= date.fromisoformat(aralik[1]):
                return ad
            if gun == bas - timedelta(days=1) and an.time() >= ARIFE_SAATI:
                return f"{ad} arifesi"
    return None


def ogretim_gunu(takvim: dict, gun: date) -> bool:
    og = takvim.get("ogretim") or {}
    if og.get("bas") and og.get("bit") and not _icinde(gun, og["bas"], og["bit"]):
        return False
    donemler = og.get("donemler") or []
    return not donemler or any(_icinde(gun, b, s) for b, s in donemler)


def plan_hesapla(gun: date, saatler: list[tuple], takvim: dict | None) -> dict:
    """Bir günün planı (saf işlev).

    saatler: haftalık satırlar [(gun, devre, devre_adi, no, bas, bit)]; takvim: `zil_takvimi`.
    Döndürür: {"tatil": ad|None, "dersler": [(devre, devre_adi, no, bas_dt, bit_dt)],
    "sinav": [(bas_dt, bit_dt)], "tum_gun_sinav": bool, "program_gunu": 0..6, "kaynak": metin}.
    `program_gunu`: derslik programının hangi haftanın gününe göre eşleneceği (telafide hedef gün).
    """
    takvim = takvim or {}
    adlar = dict(takvim.get("devre_adlari") or {})
    for s in saatler:
        adlar.setdefault(s[1], s[2])

    def haftalik(gun_no: int) -> list[tuple[str, int, str, str]]:
        return [(s[1], s[3], s[4], s[5]) for s in saatler if s[0] == gun_no]

    eslesen = [k for k in takvim.get("kurallar") or [] if _icinde(gun, k.get("bas"), k.get("bit"))]
    temel = sorted(
        (k for k in eslesen if k.get("tur") in KURAL_ONCELIGI),
        key=lambda k: (KURAL_ONCELIGI[k["tur"]], k.get("ad", "")),
        reverse=True,
    )
    tatil = None
    program_gunu = gun.weekday()
    kaynak = "Haftalık program"
    if temel:
        kazanan = temel[0]
        kaynak = f"{kazanan.get('ad')} ({KURAL_ADI.get(kazanan['tur'], kazanan['tur'])})"
        if kazanan["tur"] == "tatil":
            ham, tatil = [], kazanan.get("ad") or "Tatil"
        elif kazanan["tur"] == "telafi":
            program_gunu = int(kazanan.get("hedef_gun", gun.weekday()))
            ham = haftalik(program_gunu)
        else:
            ham = [tuple(d) for d in kazanan.get("dersler") or []]
    else:
        ham = haftalik(gun.weekday())
        if takvim.get("ogretim"):
            if not ogretim_gunu(takvim, gun):
                tatil = "Öğretim dönemi dışında" if ham else None
                ham = []
            else:
                suzulen = []
                for d in ham:
                    ad = tatil_adi(takvim, an_dt(gun, d[2]))
                    if ad:
                        tatil = tatil or ad
                    else:
                        suzulen.append(d)
                if suzulen:
                    tatil = None  # gün kısmen ders günü (ör. arife sabahı)
                ham = suzulen
    dersler = sorted(
        ((d, adlar.get(d) or devre_adi_varsayilan(d), int(n), an_dt(gun, b), an_dt(gun, s)) for d, n, b, s in ham),
        key=lambda x: (x[3], x[0], x[2]),
    )
    sinav: list[tuple[datetime, datetime]] = []
    tum_gun = False
    for k in eslesen:
        if k.get("tur") == "sinav_plani" and gun.weekday() in (k.get("gunler") or []):
            if k.get("tum_gun"):
                tum_gun = True
            for b, s in k.get("pencereler") or []:
                sinav.append((an_dt(gun, b), an_dt(gun, s)))
    return {"tatil": tatil, "dersler": dersler, "sinav": sorted(sinav), "tum_gun_sinav": tum_gun,
            "program_gunu": program_gunu, "kaynak": kaynak}  # fmt: skip


# ---- kilit aralıkları ------------------------------------------------------------------------
def birlestir(araliklar) -> list[tuple[int, int]]:
    sonuc: list[list[int]] = []
    for a, b in sorted(araliklar):
        if sonuc and a <= sonuc[-1][1]:
            sonuc[-1][1] = max(sonuc[-1][1], b)
        else:
            sonuc.append([a, b])
    return [(a, b) for a, b in sonuc]


def kilit_araliklari(plan: dict, dersli: list[tuple[int, int]]) -> list[dict]:
    """[günün ilk ders başı, son ders sonu] − dersli aralıklar (epoch).

    dersli: tahtanın derste sayıldığı aralıklar. Döndürür: [{"bas","bit","neden"}].
    Neden: iki dersli aralık arasında ve ≤ 20 dk "Teneffüs"; günün ders akışında iki ardışık
    ders arasındaki daha uzun boşluk "Öğle arası"; aksi "Bu saatte bu derslikte ders yok".
    """
    tum = [(int(d[3].timestamp()), int(d[4].timestamp())) for d in plan["dersler"]]
    if not tum:
        return []
    gun_bas, gun_bit = min(a for a, _ in tum), max(b for _, b in tum)
    tum_b = birlestir(tum)
    dolu = birlestir((max(a, gun_bas), min(b, gun_bit)) for a, b in dersli if b > gun_bas and a < gun_bit)
    bosluklar = [(tum_b[i][1], tum_b[i + 1][0]) for i in range(len(tum_b) - 1)]
    sonuc = []
    imlec = gun_bas
    for a, b in dolu + [(gun_bit, gun_bit)]:
        if a > imlec:
            ders_sonu = any(d[1] == imlec for d in dolu)
            ders_basi = any(d[0] == a for d in dolu)
            if ders_sonu and ders_basi and a - imlec <= TENEFFUS_EN_UZUN_SN:
                neden = NEDEN_TENEFFUS
            elif ders_sonu and ders_basi and (imlec, a) in bosluklar:
                neden = NEDEN_OGLE
            else:
                neden = NEDEN_DERS_YOK
            sonuc.append({"bas": imlec, "bit": a, "neden": neden})
        imlec = max(imlec, b)
    return sonuc


def simdiki_durum(plan: dict, an: datetime) -> dict:
    """Şerit için şu anki durum: {"tur": "ders"|"teneffus"|"ogle"|"ara"|"disi"|"tatil"|"yok", "metin", "bas", "bit"}."""
    if plan.get("tatil"):
        return {"tur": "tatil", "metin": f"Tatil: {plan['tatil']}", "bas": None, "bit": None}
    dersler = plan["dersler"]
    if not dersler:
        return {"tur": "yok", "metin": "Bugün ders yok", "bas": None, "bit": None}
    cok_devre = len({d[0] for d in dersler}) > 1
    simdi = [d for d in dersler if d[3] <= an < d[4]]
    if simdi:
        d = simdi[0]
        onek = f"{d[1]} · " if cok_devre else ""
        return {"tur": "ders", "metin": f"{onek}{d[2]}. ders · {d[3]:%H:%M}–{d[4]:%H:%M}", "bas": d[3], "bit": d[4], "ders": d}
    once = [d for d in dersler if d[4] <= an]
    sonra = [d for d in dersler if d[3] > an]
    if not once or not sonra:
        return {"tur": "disi", "metin": "Ders dışı", "bas": None, "bit": None}
    bas, bit = max(d[4] for d in once), min(d[3] for d in sonra)
    uzunluk = (bit - bas).total_seconds()
    if uzunluk <= TENEFFUS_EN_UZUN_SN:
        tur, ad = "teneffus", NEDEN_TENEFFUS
    else:
        tur, ad = "ogle", NEDEN_OGLE
    return {"tur": tur, "metin": f"{ad} · {bas:%H:%M}–{bit:%H:%M}", "bas": bas, "bit": bit}


# ---- derslik programı CSV ---------------------------------------------------------------------
_GUNLER = {
    "pazartesi": 0, "pzt": 0, "pts": 0, "sali": 1, "sal": 1, "carsamba": 2, "car": 2, "crs": 2,
    "persembe": 3, "per": 3, "prs": 3, "cuma": 4, "cum": 4, "cumartesi": 5, "cmt": 5, "pazar": 6, "paz": 6,
}  # fmt: skip
_CSV_BASLIK = {"derslik": "derslik", "gun": "gun", "ders": "ders", "devre": "devre", "oturum": "devre",
               "sube": "sube"}  # fmt: skip


def gun_coz(deger) -> int | None:
    s = metin.katla(deger).rstrip(".")
    if s.isdigit() and 1 <= int(s) <= 7:
        return int(s) - 1
    return _GUNLER.get(s)


def ders_nolari_coz(deger) -> list[int] | None:
    """'3', '1-4', '1,2,5', '1-3,6' → sıralı numaralar; anlaşılamazsa None."""
    sonuc: set[int] = set()
    s = str(deger or "").replace(" ", "").replace(";", ",")
    if not s:
        return None
    for parca in s.split(","):
        if not parca:
            continue
        e = re.fullmatch(r"(\d{1,2})(?:-(\d{1,2}))?", parca)
        if not e:
            return None
        a, b = int(e.group(1)), int(e.group(2) or e.group(1))
        if a > b or not 1 <= a <= 20 or not 1 <= b <= 20:
            return None
        sonuc.update(range(a, b + 1))
    return sorted(sonuc) or None


def derslik_csv_oku(bayt: bytes, saatler: list[tuple], tahtalar: list[dict]) -> dict:
    """Derslik programı CSV'sini çözer; veritabanına yazmaz.

    saatler: ders_saati satırları; tahtalar: [{"id","ad","derslik"}] (onaylı/bekleyen, kaldırılmamış).
    Döndürür: {"tahtalar": {id: [[gun, devre, no, sube], ...]}, "eslesen": [{"id","ad","derslik","satir"}],
    "eslesmeyen": [ad], "hatalar": ["12. satır: …"] (ilk 50), "hata_sayisi", "uyarilar", "yok_sayilan": [başlık],
    "satir_sayisi"}. Dosya okunamazsa ValueError.
    """
    if not saatler:
        raise ValueError("Önce zil saatlerini girin; derslik programı ders saatlerine göre okunur.")
    basliklar, satirlar = metin.csv_oku(bayt, CSV_EN_COK_BAYT, CSV_EN_COK_SATIR)
    konum: dict[str, int] = {}
    yok_sayilan = []
    for sira, baslik in enumerate(basliklar):
        alan = _CSV_BASLIK.get(metin.katla(baslik).replace("_", " "))
        if alan and alan not in konum:
            konum[alan] = sira
        elif baslik.strip():
            yok_sayilan.append(baslik.strip()[:40])
    eksik = [a for a in ("derslik", "gun", "ders") if a not in konum]
    if eksik:
        raise ValueError("Dosyada şu sütunlar yok: " + ", ".join(eksik) + ". Örnek dosyayı indirip doldurun.")
    gun_devreleri: dict[int, dict[str, str]] = {}
    nolar: set[tuple[int, str, int]] = set()
    for s in saatler:
        gun_devreleri.setdefault(s[0], {})[s[1]] = s[2]
        nolar.add((s[0], s[1], s[3]))
    derslige: dict[str, list[dict]] = {}
    ada: dict[str, list[dict]] = {}
    for t in tahtalar:
        if t.get("derslik"):
            derslige.setdefault(metin.derslik_anahtari(t["derslik"]), []).append(t)
        ada.setdefault(metin.derslik_anahtari(t["ad"]), []).append(t)
    hatalar: list[str] = []
    uyarilar: list[str] = []
    eslesmeyen: dict[str, str] = {}
    sonuc: dict[int, dict[tuple[int, str, int], str]] = {}
    eslesen: dict[int, dict] = {}
    cift_uyarildi: set[str] = set()
    tekrar = 0
    for sira, satir in enumerate(satirlar, start=2):
        def hucre(alan: str, satir=satir) -> str:
            return metin.csv_hucre_coz(satir[konum[alan]]).strip() if alan in konum else ""

        derslik = hucre("derslik")
        if not derslik:
            hatalar.append(f"{sira}. satır: derslik boş.")
            continue
        gun = gun_coz(hucre("gun"))
        if gun is None:
            hatalar.append(f"{sira}. satır: gün anlaşılamadı.")
            continue
        dersler = ders_nolari_coz(hucre("ders"))
        if not dersler:
            hatalar.append(f"{sira}. satır: ders numarası anlaşılamadı (ör. 3, 1-4 ya da 1,2,5).")
            continue
        devreler = gun_devreleri.get(gun, {})
        if not devreler:
            hatalar.append(f"{sira}. satır: {GUN_ADLARI[gun]} için ders saati tanımlı değil.")
            continue
        ham_devre = hucre("devre")
        if ham_devre:
            k = metin.katla(ham_devre)
            devre = next((d for d, a in devreler.items() if metin.katla(d) == k or metin.katla(a) == k), None)
            if devre is None:
                hatalar.append(f"{sira}. satır: '{ham_devre[:30]}' devresi {GUN_ADLARI[gun]} günü tanımlı değil.")
                continue
        elif len(devreler) == 1:
            devre = next(iter(devreler))
        else:
            hatalar.append(f"{sira}. satır: bu gün iki devreli; devre (oturum) sütununu doldurun.")
            continue
        olmayan = [n for n in dersler if (gun, devre, n) not in nolar]
        if olmayan:
            hatalar.append(f"{sira}. satır: {GUN_ADLARI[gun]} günü {', '.join(map(str, olmayan))}. ders tanımlı değil.")
            continue
        sube = ""
        ham_sube = hucre("sube")
        if ham_sube:
            sube = metin.sube_duzelt(ham_sube) or ""
            if not sube or len(sube) > SUBE_EN_UZUN:
                uyarilar.append(f"{sira}. satır: şube '{ham_sube[:20]}' anlaşılamadı; boş bırakıldı.")
                sube = ""
        anahtar = metin.derslik_anahtari(derslik)
        hedefler = derslige.get(anahtar) or ada.get(anahtar) or []
        if not hedefler:
            eslesmeyen.setdefault(anahtar, derslik[:60])
            continue
        if len(hedefler) > 1 and anahtar not in cift_uyarildi:
            cift_uyarildi.add(anahtar)
            uyarilar.append(
                f"Aynı dersliğe bağlı {len(hedefler)} tahta: {', '.join(t['ad'] for t in hedefler)} (ikisine de uygulanacak)."
            )
        for t in hedefler:
            kayit = sonuc.setdefault(t["id"], {})
            eslesen.setdefault(t["id"], {"id": t["id"], "ad": t["ad"], "derslik": t.get("derslik", ""), "satir": 0})
            for n in dersler:
                if (gun, devre, n) in kayit:
                    tekrar += 1
                kayit[(gun, devre, n)] = sube
    if tekrar:
        uyarilar.append(f"{tekrar} ders saati dosyada birden çok kez geçiyor; son satır geçerli sayıldı.")
    if yok_sayilan:
        uyarilar.append("Şu sütunlar yok sayıldı (okunmaz ve saklanmaz): " + ", ".join(yok_sayilan))
    tahtalar_sonuc = {}
    for tahta_id, kayit in sonuc.items():
        tahtalar_sonuc[tahta_id] = [[g, d, n, s] for (g, d, n), s in sorted(kayit.items())]
        eslesen[tahta_id]["satir"] = len(kayit)
    return {
        "tahtalar": tahtalar_sonuc,
        "eslesen": sorted(eslesen.values(), key=lambda e: metin.tr_sirala_anahtari(e["ad"])),
        "eslesmeyen": sorted(eslesmeyen.values(), key=metin.tr_sirala_anahtari),
        "hatalar": hatalar[:HATA_GOSTERIM],
        "hata_sayisi": len(hatalar),
        "uyarilar": uyarilar,
        "yok_sayilan": yok_sayilan,
        "satir_sayisi": len(satirlar),
    }


def ornek_csv(saatler: list[tuple]) -> bytes:
    """Uydurma örnek derslik programı; gün/ders sütunları mevcut ders saati yapısına göre."""
    satirlar = []
    gunler = sorted({s[0] for s in saatler}) or [0, 1, 2]
    ornekler = [("Z-04", "9/A"), ("Z-04", "10/B"), ("1-12", "11/C"), ("Fizik Lab", "12/A")]
    for sira, (derslik, sube) in enumerate(ornekler):
        gun = gunler[sira % len(gunler)]
        devreler = sorted({s[1] for s in saatler if s[0] == gun}) or ["normal"]
        devre = devreler[sira % len(devreler)]
        nolar = sorted(s[3] for s in saatler if s[0] == gun and s[1] == devre) or [1, 2, 3, 4]
        if sira == 1 and len(nolar) > 5:
            ders = f"{nolar[4]}-{nolar[-1]}"
        elif sira == 2 and len(nolar) >= 3:
            ders = ",".join(str(n) for n in nolar[:3])
        else:
            ders = f"{nolar[0]}-{nolar[min(3, len(nolar) - 1)]}" if len(nolar) > 1 else str(nolar[0])
        satirlar.append([derslik, GUN_ADLARI[gun], ders, devre if len(devreler) > 1 else "", sube])
    return metin.csv_yaz(["derslik", "gun", "ders", "devre", "sube"], satirlar)


# ---- ikili eğitim: devre türleri ------------------------------------------------------------------
def devre_turleri(saatler: list[tuple]) -> dict[str, str]:
    """İkili eğitimde ders saati devrelerinin sabah/öğle karşılığı: {devre: "sabah"|"ogle"}; tek devrede {}.

    Önce kimlik ya da ad okunur ("sabah…", "öğle…"); iki devreli okulda adlar bunu söylemiyorsa günün
    erken başlayan devresi sabah, geç başlayanı öğle sayılır. Üç ve daha çok devrede yalnız adı tanınanlar döner.
    """
    ilk: dict[str, int] = {}
    adlar: dict[str, str] = {}
    for _gun, devre, devre_adi, _no, bas, _bit in saatler:
        ilk[devre] = min(ilk.get(devre, 24 * 60), dk(bas))
        adlar.setdefault(devre, devre_adi)
    if len(ilk) < 2:
        return {}
    sonuc: dict[str, str] = {}
    for devre in ilk:
        for aday in (devre_kimligi(devre), devre_kimligi(adlar.get(devre) or "")):
            if aday in ("sabah", "ogle"):
                sonuc[devre] = aday
                break
    if len(ilk) == 2 and set(sonuc.values()) != {"sabah", "ogle"}:
        erken, gec = sorted(ilk, key=lambda d: (ilk[d], d))
        sonuc = {erken: "sabah", gec: "ogle"}
    return sonuc


def tahta_devreleri(b) -> dict[int, str]:
    """Derslik programından tahtanın devresi: {tahta_id: "sabah"|"ogle"|"her_ikisi"} (ikili eğitimde).

    Duyuru hedefindeki "Sabahçılar/Öğlenciler" süzgeci, tahtanın "devre" alanı boşsa bunu kullanır.
    """
    turler = devre_turleri(ders_saatleri_oku(b))
    if not turler:
        return {}
    kume: dict[int, set[str]] = {}
    for s in b.execute("SELECT DISTINCT tahta_id, devre FROM tahta_ders"):
        if s["devre"] in turler:
            kume.setdefault(s["tahta_id"], set()).add(turler[s["devre"]])
    return {t: ("her_ikisi" if len(v) > 1 else next(iter(v))) for t, v in kume.items()}


# ---- veritabanı okuyan yardımcılar (Aşama 5 de kullanır) --------------------------------------
def ders_saatleri_oku(b) -> list[tuple]:
    return [
        (s["gun"], s["devre"], s["devre_adi"], s["ders_no"], s["baslangic"], s["bitis"])
        for s in b.execute("SELECT * FROM ders_saati ORDER BY gun, devre, baslangic")
    ]


def gun_plani(b, tarih: date) -> dict:
    """Veritabanındaki ders saatleri ve `zil_takvimi` ile günün planı (bkz. plan_hesapla)."""
    from . import vt

    return plan_hesapla(tarih, ders_saatleri_oku(b), vt.ayar_al(b, "zil_takvimi"))


def simdiki_ders(b, tahta, an: datetime) -> dict | None:
    """Tahtanın derslik programına göre şu anki dersi: {"devre","devre_adi","ders_no","bas","bit","sube"} ya da None.

    Yalnız `tahta_ders` satırı olan derslerde döner (programı olmayan tahtada None).
    """
    plan = gun_plani(b, an.date())
    satirlar = {
        (s["devre"], s["ders_no"]): s["sube"]
        for s in b.execute(
            "SELECT devre, ders_no, sube FROM tahta_ders WHERE tahta_id = ? AND gun = ?", (tahta["id"], plan["program_gunu"])
        )
    }
    for d in plan["dersler"]:
        if d[3] <= an < d[4] and (d[0], d[2]) in satirlar:
            return {"devre": d[0], "devre_adi": d[1], "ders_no": d[2], "bas": d[3], "bit": d[4], "sube": satirlar[(d[0], d[2])]}
    return None


def ayar_kilit(b) -> dict:
    from . import vt

    deger = vt.ayar_al(b, "program_kilidi")
    return {**VARSAYILAN_KILIT, **(deger if isinstance(deger, dict) else {})}


def ayar_bos_ders(b) -> dict:
    from . import vt

    deger = vt.ayar_al(b, "bos_ders_uyarisi")
    return {**VARSAYILAN_BOS_DERS, **(deger if isinstance(deger, dict) else {}), "dokunma_yoksa": False}
