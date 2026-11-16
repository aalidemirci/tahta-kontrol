"""Ders programını içe aktarma sihirbazı (0.10.0): aSc Timetables XML, Tahta Kontrol şablonu (CSV/XLSX/XLS)
ve yapay zekâ çıktısı (yapıştırılan CSV). e-Okul kaynağı YOKTUR (biçimi doğrulanamadı; şartname §1.2).

Yalnız derslik programı (`tahta_ders`) değişir; zil saatleri değişmez. Bütün kaynaklar aynı ara biçime iner:

    yerleşim = {"d": derslik anahtarı ('' = belli değil), "s": [sınıf anahtarları], "g": gün 0..6,
                "p": saat anahtarı (aSc: 'period|starttime'; tablo: 'devre|no'), "n": kaynak satır/kart no}

ve ayrı `bilgi` sözlükleri ({"derslik": {anahtar: {"ad","adaylar"}}, "sinif": {...}, "saat": {...}}) taşır.
Öğretmen, ders adı, öğrenci ve kişi verisi HİÇBİR aşamada okunmaz ve saklanmaz: aSc'nin `teachers`,
`subjects`, `students`, `studentsubjects`, `classroomsupervisions` bölümleri ayrıştırılırken içleri atlanır,
`lesson@teacherids` ve `lesson@subjectid` okunmaz; tablodaki bilinmeyen sütunlar (ör. öğretmen) okunmaz.

Veritabanına yalnız `uygula` ve `geri_yukle` yazar (+ işlem kaydını çağıran düşer). Tahta Kontrol hiçbir dış
hizmete bağlanmaz; yapay zekâ yolu yalnız istemi gösterir ve kullanıcının yapıştırdığı sonucu okur.

İşaretler (şartname): aSc'de gün maskesinin Pazartesi'den başlaması, blok derste kart sayısı ve
`class@classroomids`'in sınıfın kendi dersliği olması DOĞRULANMALI varsayımlardır (gerçek örnek dosya yok).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

from . import eokul, guvenli_xml, guvenlik, metin, program, vt, xlsx, zamanlama

ASC_EN_COK_BAYT = 10 * 1024 * 1024
ASC_EN_COK_OGE = 300_000
ASC_EN_COK_KART = 30_000
ASC_EN_COK_DERS = 20_000
ASC_OZNITELIK_EN_UZUN = 4096
ASC_EN_DERIN = 8
YZ_METIN_EN_COK = 512 * 1024
TABLO_EN_COK_BAYT = program.CSV_EN_COK_BAYT
TABLO_EN_COK_SATIR = program.CSV_EN_COK_SATIR
ESLEME_EN_COK = 2000
SURUM_SAKLA = 10
ONIZLEME_EN_COK_BAYT = 2 * 1024 * 1024
HATA_GOSTERIM = program.HATA_GOSTERIM
HATA_ORANI = 0.2  # hatalı satır yerleşimlerin %20'sini aşarsa onay için ek kutu
SAAT_TOLERANS_DK = 5
DENEME_SINIRI = 10

BICIM_ADI = {"asc": "aSc Timetables XML", "csv": "CSV", "xlsx": "Excel (.xlsx)", "xls": "Excel 97-2003 (.xls)",
             "yz": "Yapay zekâ çıktısı (yapıştırma)", "yz_dosya": "Yapay zekâ çıktısı (dosya)", "": "—"}  # fmt: skip
NEDEN_ADI = {"aktarim": "İçe aktarma öncesi", "geri_yukleme": "Geri yükleme öncesi"}
ASC_DEGIL = "Bu bir aSc Timetables XML dosyası değil."
ASC_OKUNAMADI = "aSc XML dosyası okunamadı; aSc'den yeniden dışa aktarıp deneyin."
ASC_BUYUK = "Dosya beklenenden büyük; aSc'den yalnız bu okulun programını dışa aktarın."
TC_RET = "Dosyada kimlik numarasına benzeyen değer var; silip yeniden yükleyin."
ZIL_YOK = "Önce zil saatlerini girin; derslik programı ders saatlerine göre okunur."

# aSc: okunan bölümler ve öğe başına izinli öznitelikler (geri kalanı okunmaz).
ASC_IZINLI = {
    ("periods", "period"): ("period", "name", "short", "starttime", "endtime"),
    ("daysdefs", "daysdef"): ("id", "name", "short", "days"),
    ("weeksdefs", "weeksdef"): ("id", "name", "weeks"),
    ("termsdefs", "termsdef"): ("id", "name", "terms"),
    ("classrooms", "classroom"): ("id", "name", "short"),
    ("classes", "class"): ("id", "name", "short", "classroomids"),
    ("groups", "group"): ("id", "classid", "entireclass", "divisiontag"),
    ("lessons", "lesson"): ("id", "classids", "groupids", "classroomids", "periodsperweek", "periodspercard",
                            "weeksdefid", "termsdefid"),
    ("cards", "card"): ("lessonid", "classroomids", "days", "period", "weeks", "terms"),
}  # fmt: skip
# İçi hiç okunmayan bölümler (kişi ve ders adı taşır).
ASC_ATLA = {"teachers", "subjects", "students", "studentsubjects", "classroomsupervisions"}


def _ids(deger) -> list[str]:
    return [p.strip() for p in str(deger or "").split(",") if p.strip()]


def ozet(bayt: bytes) -> str:
    return hashlib.sha256(bayt).hexdigest()


# ==== 1. aSc Timetables XML ==========================================================================
def asc_oku(bayt: bytes) -> dict:
    """aSc XML → yalnız izinli öznitelikleri taşıyan sözlük (JSON'a yazılabilir). Okunamazsa ValueError.

    {"periods": {no: {name, short, starttime, endtime}}, "daysdefs": [..], "weeksdefs": {id: weeks},
    "termsdefs": [{id, name, terms}], "classrooms": {id: {name, short}}, "classes": {id: {name, short, classroomids}},
    "groups": {id: {classid}}, "lessons": {id: {...}}, "cards": [{...}], "uyarilar": [..]}
    """
    if len(bayt) > ASC_EN_COK_BAYT:
        raise ValueError(f"Dosya en çok {ASC_EN_COK_BAYT // (1024 * 1024)} MB olabilir.")
    veri = guvenli_xml.kodlama_duzelt(bayt)
    guvenli_xml.on_denetim(veri)
    sonuc: dict = {"periods": {}, "daysdefs": [], "weeksdefs": {}, "termsdefs": [], "classrooms": {}, "classes": {},
                   "groups": {}, "lessons": {}, "cards": [], "uyarilar": []}  # fmt: skip
    durum = {"yigin": [], "atla": 0, "oge": 0, "kok": None, "displayname": ""}

    class _Buyuk(Exception):
        pass

    def basla(ad: str, oznitelik: dict) -> None:
        yigin = durum["yigin"]
        durum["oge"] += 1
        if durum["oge"] > ASC_EN_COK_OGE or len(yigin) >= ASC_EN_DERIN:
            raise _Buyuk
        ust = yigin[-1] if yigin else None
        yigin.append(ad)
        if durum["atla"]:
            durum["atla"] += 1
            return
        if ust is None:
            durum["kok"] = ad
            durum["displayname"] = str(oznitelik.get("displayname", ""))[:200]
            return
        if len(yigin) == 2 and ad in ASC_ATLA:
            durum["atla"] = 1
            return
        izinli = ASC_IZINLI.get((ust, ad))
        if not izinli or len(yigin) != 3:
            return
        kayit = {}
        for a in izinli:
            deger = oznitelik.get(a)
            if deger is None:
                continue
            if len(deger) > ASC_OZNITELIK_EN_UZUN:
                raise _Buyuk
            kayit[a] = deger
        if ad == "period":
            if kayit.get("period", "").strip():
                sonuc["periods"][kayit["period"].strip()] = kayit
        elif ad == "daysdef":
            sonuc["daysdefs"].append(kayit)
        elif ad == "weeksdef":
            sonuc["weeksdefs"][kayit.get("id", "")] = kayit.get("weeks", "")
        elif ad == "termsdef":
            sonuc["termsdefs"].append(kayit)
        elif ad == "classroom":
            sonuc["classrooms"][kayit.get("id", "")] = kayit
        elif ad == "class":
            sonuc["classes"][kayit.get("id", "")] = kayit
        elif ad == "group":
            sonuc["groups"][kayit.get("id", "")] = kayit
        elif ad == "lesson":
            if len(sonuc["lessons"]) >= ASC_EN_COK_DERS:
                raise _Buyuk
            sonuc["lessons"][kayit.get("id", "")] = kayit
        elif ad == "card":
            if len(sonuc["cards"]) >= ASC_EN_COK_KART:
                raise _Buyuk
            sonuc["cards"].append(kayit)

    def bitir(_ad: str) -> None:
        durum["yigin"].pop()
        if durum["atla"]:
            durum["atla"] -= 1

    p = guvenli_xml.ayristirici()
    p.StartElementHandler = basla
    p.EndElementHandler = bitir
    try:
        guvenli_xml.ayristir(p, veri, ASC_OKUNAMADI)
    except _Buyuk as hata:
        raise ValueError(ASC_BUYUK) from hata
    if durum["kok"] != "timetable":
        raise ValueError(ASC_DEGIL)
    if not durum["displayname"].lower().startswith("asc timetables"):
        sonuc["uyarilar"].append("Dosya aSc Timetables'tan gelmiyor olabilir; önizlemeyi dikkatle kontrol edin.")
    if len(sonuc["cards"]) <= DENEME_SINIRI and len(sonuc["lessons"]) <= DENEME_SINIRI:
        sonuc["uyarilar"].append(
            f"Dosyada yalnız {len(sonuc['cards'])} ders var; aSc deneme sürümü dışa aktarımı sınırlar."
        )
    if not sonuc["cards"]:
        raise ValueError("Dosyada program kartı (cards) yok; aSc'de programın oluşturulduğundan emin olun.")
    return sonuc


def asc_gunleri(asc: dict) -> tuple[dict[int, int], str | None]:
    """Gün maskesindeki konum → gün (0 = Pazartesi). Tek günlük `daysdef` adları Türkçe gün adına çözülürse
    eşleme adlardan kurulur; çözülmezse konum varsayılır ve uyarı döner (DOĞRULANMALI varsayım)."""
    harita: dict[int, int] = {}
    for d in asc.get("daysdefs") or []:
        maskeler = [m for m in str(d.get("days", "")).split(",") if m]
        if len(maskeler) != 1 or maskeler[0].count("1") != 1:
            continue
        konum = maskeler[0].index("1")
        for ad in (d.get("name"), d.get("short")):
            gun = program.gun_coz(ad) if ad and not str(ad).strip().isdigit() else None
            if gun is not None:
                harita[konum] = gun
                break
    if harita:
        for konum in range(7):
            if konum not in harita and konum not in harita.values():
                harita[konum] = konum
        return harita, None
    return {i: i for i in range(7)}, "Günler sırayla Pazartesi'den başlar varsayıldı (aSc gün adları okunamadı)."


def asc_donemleri(asc: dict) -> list[tuple[int, str]]:
    """Tek dönemlik `termsdef`'ler: [(konum, ad)]; ikiden azsa dönem sorusu çıkmaz."""
    sonuc = []
    for t in asc.get("termsdefs") or []:
        maske = str(t.get("terms", "")).strip()
        if maske.count("1") == 1 and set(maske) <= {"0", "1"}:
            sonuc.append((maske.index("1"), " ".join(str(t.get("name") or "").split())[:60] or f"{maske.index('1') + 1}. dönem"))
    return sorted(set(sonuc))


def _sayi(deger, varsayilan: float) -> float:
    try:
        return float(str(deger).replace(",", ".").strip())
    except ValueError:
        return varsayilan


def asc_ara(asc: dict, secimler: dict) -> dict:
    """aSc kartlarını ara biçime çevirir (şartname §3.3). Döndürür {"ara", "bilgi", "hatalar", "hata_sayisi",
    "uyarilar", "kart_sayisi", "dersliksiz": [..], "dersliksiz_sayi", "iki_haftalik"}."""
    hatalar: list[str] = []
    uyarilar: list[str] = list(asc.get("uyarilar") or [])
    gun_haritasi, gun_uyarisi = asc_gunleri(asc)
    if gun_uyarisi:
        uyarilar.append(gun_uyarisi)
    donemler = asc_donemleri(asc)
    secili_donem = None
    if len(donemler) >= 2:
        try:
            secili_donem = int(secimler.get("donem", donemler[0][0]))
        except (TypeError, ValueError):
            secili_donem = donemler[0][0]
        if secili_donem not in {k for k, _ in donemler}:
            secili_donem = donemler[0][0]
    lessons, classes, groups = asc["lessons"], asc["classes"], asc["groups"]
    rooms, periods = asc["classrooms"], asc["periods"]
    termsdefs = {t.get("id", ""): t.get("terms", "") for t in asc.get("termsdefs") or []}

    def donemde(kart, ders) -> bool:
        if secili_donem is None:
            return True
        maske = str(kart.get("terms") or termsdefs.get(ders.get("termsdefid", ""), "") or "")
        return not maske or (secili_donem < len(maske) and maske[secili_donem] == "1")

    kartlar = []
    kart_sayilari: dict[str, int] = {}
    for sira, kart in enumerate(asc["cards"], start=1):
        ders = lessons.get(kart.get("lessonid", ""))
        if ders is None:
            hatalar.append(f"{sira}. kart: kart bilinmeyen derse bağlı; atlandı.")
            continue
        if not donemde(kart, ders):
            continue
        kartlar.append((sira, kart, ders))
        kart_sayilari[ders.get("id", "")] = kart_sayilari.get(ders.get("id", ""), 0) + 1
    bilgi: dict = {"derslik": {}, "sinif": {}, "saat": {}}
    ara: list[dict] = []
    iki_haftalik = 0
    coklu_gun = 0
    tutarsiz_blok: set[str] = set()
    dersliksiz: list[str] = []
    dersliksiz_sayi = 0
    period_sirasi = sorted(periods, key=lambda p: (_sayi(p, 0), p))

    def sinif_anahtari(cid: str) -> str | None:
        c = classes.get(cid)
        if not c:
            return None
        ad = " ".join(str(c.get("name") or c.get("short") or "").split())[:60]
        anahtar = metin.katla(ad) or f"#{cid}"
        bilgi["sinif"].setdefault(anahtar, {"ad": ad or cid, "adaylar": [x for x in (c.get("short"), c.get("name")) if x]})
        return anahtar

    def derslik_anahtari(rid: str) -> str | None:
        r = rooms.get(rid)
        if not r:
            return None
        ad = " ".join(str(r.get("name") or r.get("short") or "").split())[:60]
        kisa = " ".join(str(r.get("short") or "").split())[:30]
        anahtar = metin.derslik_anahtari(ad) or f"#{rid}"
        bilgi["derslik"].setdefault(anahtar, {"ad": f"{ad} ({kisa})" if kisa and kisa != ad else ad,
                                              "adaylar": [x for x in (ad, kisa) if x]})  # fmt: skip
        return anahtar

    for sira, kart, ders in kartlar:
        maske = str(kart.get("days", ""))
        konumlar = [i for i, h in enumerate(maske) if h == "1"]
        if not konumlar:
            hatalar.append(f"{sira}. kart: günü yok; atlandı.")
            continue
        if len(konumlar) > 1:
            coklu_gun += 1
        haftalar = str(kart.get("weeks") or asc["weeksdefs"].get(ders.get("weeksdefid", ""), "") or "")
        if "0" in haftalar and "1" in haftalar:
            iki_haftalik += 1
        # blok ders genişlemesi (DOĞRULANMALI: örnek dosyayla kesinleşecek)
        ppc = max(1, int(_sayi(ders.get("periodspercard"), 1)))
        donemler_ = [str(kart.get("period", "")).strip()]
        if ppc > 1:
            n = kart_sayilari.get(ders.get("id", ""), 1)
            ppw = round(_sayi(ders.get("periodsperweek"), n))
            if n * ppc == ppw and donemler_[0] in period_sirasi:
                i = period_sirasi.index(donemler_[0])
                donemler_ = period_sirasi[i : i + ppc]
            elif n != ppw:
                tutarsiz_blok.add(ders.get("id", ""))
        # derslik(ler): kart → ders (tek) → sınıfın kendi dersliği (tek) → '' (şubenin tahtası ya da dersliksiz)
        derslikler = [a for a in (derslik_anahtari(r) for r in _ids(kart.get("classroomids"))) if a]
        sinif_idleri = _ids(ders.get("classids"))
        for gid in _ids(ders.get("groupids")):
            cid = (groups.get(gid) or {}).get("classid")
            if cid and cid not in sinif_idleri:
                sinif_idleri.append(cid)
        if not derslikler:
            ders_odalari = _ids(ders.get("classroomids"))
            if len(ders_odalari) == 1 and derslik_anahtari(ders_odalari[0]):
                derslikler = [derslik_anahtari(ders_odalari[0])]
        if not derslikler and len(sinif_idleri) == 1:
            sinif_odalari = _ids((classes.get(sinif_idleri[0]) or {}).get("classroomids"))
            if len(sinif_odalari) == 1 and derslik_anahtari(sinif_odalari[0]):
                derslikler = [derslik_anahtari(sinif_odalari[0])]
        siniflar = [a for a in (sinif_anahtari(c) for c in sinif_idleri) if a]
        for konum in konumlar:
            gun = gun_haritasi.get(konum, konum)
            if not 0 <= gun <= 6:
                hatalar.append(f"{sira}. kart: gün maskesi anlaşılamadı; atlandı.")
                continue
            for period in donemler_:
                kayit = periods.get(period) or {}
                bas = program.saat_dogrula(kayit.get("starttime"))
                anahtar = f"{period}|{bas or ''}"
                bilgi["saat"].setdefault(anahtar, {"period": period, "ad": " ".join(str(kayit.get("name") or period).split())[:30],
                                                   "bas": bas or "", "bit": program.saat_dogrula(kayit.get("endtime")) or ""})  # fmt: skip
                for d in derslikler or [""]:
                    ara.append({"d": d, "s": siniflar, "g": gun, "p": anahtar, "n": sira})
    if coklu_gun:
        uyarilar.append(f"{coklu_gun} kartın gün maskesinde birden çok gün var; her gün ayrı sayıldı.")
    if iki_haftalik:
        uyarilar.append(
            f"{iki_haftalik} ders iki haftada bir; Tahta Kontrol hafta ayrımı yapmaz, her hafta dolu sayıldı "
            "(o saatte kilit verilmez, boş ders uyarısı yanlış çıkabilir)."
        )
    if tutarsiz_blok:
        uyarilar.append(f"Blok ders sayısı tutarsız ({len(tutarsiz_blok)} ders); kartlar tek saat sayıldı.")
    return {"ara": ara, "bilgi": bilgi, "hatalar": hatalar[:HATA_GOSTERIM], "hata_sayisi": len(hatalar),
            "uyarilar": uyarilar, "kart_sayisi": len(asc["cards"]), "dersliksiz": dersliksiz,
            "dersliksiz_sayi": dersliksiz_sayi, "donemler": donemler, "secili_donem": secili_donem}  # fmt: skip


# ==== 2. Tahta Kontrol şablonu (CSV/XLSX/XLS) ve yapay zekâ çıktısı ========================================
_TABLO_BASLIK = {"derslik": "derslik", "gun": "gun", "ders": "ders", "devre": "devre", "oturum": "devre", "sube": "sube"}
OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def tablo_matrisi(bayt: bytes) -> tuple[str, list[list[str]]]:
    """Biçim uzantıdan değil ilk baytlardan: OLE2 → .xls, ZIP → .xlsx, değilse CSV. (biçim, satırlar; ilk = başlık)."""
    if len(bayt) > TABLO_EN_COK_BAYT:
        raise ValueError(f"Dosya en çok {TABLO_EN_COK_BAYT // (1024 * 1024)} MB olabilir.")
    if not bayt.strip():
        raise ValueError("Dosya boş.")
    if bayt[:8] == OLE2:
        try:
            satirlar = eokul.xls_oku(bayt)
        except eokul.OkumaHatasi as hata:
            raise ValueError(str(hata)) from hata
        bicim = "xls"
    elif bayt[:4] == b"PK\x03\x04":
        satirlar = xlsx.oku(bayt)
        bicim = "xlsx"
    else:
        basliklar, satirlar = metin.csv_oku(bayt, TABLO_EN_COK_BAYT, TABLO_EN_COK_SATIR)
        return "csv", [basliklar, *satirlar]
    satirlar = [[str(h or "").strip() for h in s] for s in satirlar if any(str(h or "").strip() for h in s)]
    if not satirlar:
        raise ValueError("Dosyada başlık satırı yok.")
    if len(satirlar) - 1 > TABLO_EN_COK_SATIR:
        raise ValueError(f"Dosyada en çok {TABLO_EN_COK_SATIR} satır olabilir.")
    genislik = len(satirlar[0])
    return bicim, [satirlar[0]] + [s + [""] * (genislik - len(s)) for s in satirlar[1:]]


def tablo_oku(matris: list[list[str]], saatler: list[tuple]) -> dict:
    """Şablon v2 (v1 ile uyumlu) satırlarını ara biçime çevirir; veritabanına yazmaz.

    Sütunlar (sıra serbest, başlık zorunlu): sube, gun, ders, devre (oturum), derslik. Zorunlu: gun, ders ve
    (sube ya da derslik sütunu). `derslik` boşsa şubenin dersliği kullanılır (eşlemede şube → tahta).
    Herhangi bir hücrede T.C. kimlik numarasına benzeyen değer varsa dosya reddedilir. Okunamazsa ValueError.
    Döndürür {"ara","bilgi","hatalar","hata_sayisi","uyarilar","yok_sayilan","satir_sayisi"}.
    """
    if not saatler:
        raise ValueError(ZIL_YOK)
    if not matris:
        raise ValueError("Dosyada başlık satırı yok.")
    basliklar, satirlar = matris[0], matris[1:]
    for satir in matris:  # başlık satırı da (yanlış dosyada ilk satır kimlik numarası olabilir)
        for h in satir:
            if guvenlik.tc_kimlik_var(h):
                raise ValueError(TC_RET)
    konum: dict[str, int] = {}
    yok_sayilan = []
    for sira, baslik in enumerate(basliklar):
        alan = _TABLO_BASLIK.get(metin.katla(baslik).replace("_", " "))
        if alan and alan not in konum:
            konum[alan] = sira
        elif str(baslik).strip():
            yok_sayilan.append(str(baslik).strip()[:40])
    eksik = [a for a in ("gun", "ders") if a not in konum]
    if "sube" not in konum and "derslik" not in konum:
        eksik.append("sube ya da derslik")
    if eksik:
        raise ValueError("Dosyada şu sütunlar yok: " + ", ".join(eksik) + ". Boş şablonu indirip doldurun.")
    gun_devreleri: dict[int, dict[str, str]] = {}
    nolar: set[tuple[int, str, int]] = set()
    for s in saatler:
        gun_devreleri.setdefault(s[0], {})[s[1]] = s[2]
        nolar.add((s[0], s[1], s[3]))
    hatalar: list[str] = []
    uyarilar: list[str] = []
    bilgi: dict = {"derslik": {}, "sinif": {}, "saat": {}}
    ara: list[dict] = []
    for sira, satir in enumerate(satirlar, start=2):
        def hucre(alan: str, satir=satir) -> str:
            return metin.csv_hucre_coz(satir[konum[alan]]).strip() if alan in konum and konum[alan] < len(satir) else ""

        derslik = hucre("derslik")[:60]
        ham_sube = hucre("sube")
        if not derslik and not ham_sube:
            hatalar.append(f"{sira}. satır: şube ve derslik boş.")
            continue
        gun = program.gun_coz(hucre("gun"))
        if gun is None:
            hatalar.append(f"{sira}. satır: gün anlaşılamadı.")
            continue
        dersler = program.ders_nolari_coz(hucre("ders"))
        if not dersler:
            hatalar.append(f"{sira}. satır: ders numarası anlaşılamadı (ör. 3, 1-4 ya da 1,2,5).")
            continue
        devreler = gun_devreleri.get(gun, {})
        if not devreler:
            hatalar.append(f"{sira}. satır: {program.GUN_ADLARI[gun]} için ders saati tanımlı değil.")
            continue
        ham_devre = hucre("devre")
        if ham_devre:
            k = metin.katla(ham_devre)
            devre = next((d for d, a in devreler.items() if metin.katla(d) == k or metin.katla(a) == k), None)
            if devre is None:
                hatalar.append(f"{sira}. satır: '{ham_devre[:30]}' devresi {program.GUN_ADLARI[gun]} günü tanımlı değil.")
                continue
        elif len(devreler) == 1:
            devre = next(iter(devreler))
        else:
            hatalar.append(f"{sira}. satır: bu gün iki devreli; devre (oturum) sütununu doldurun.")
            continue
        olmayan = [n for n in dersler if (gun, devre, n) not in nolar]
        if olmayan:
            hatalar.append(f"{sira}. satır: {program.GUN_ADLARI[gun]} günü {', '.join(map(str, olmayan))}. ders tanımlı değil.")
            continue
        sube = ""
        if ham_sube:
            sube = metin.sube_duzelt(ham_sube) or ""
            if not sube or len(sube) > program.SUBE_EN_UZUN:
                sube = ""
                if not derslik:
                    hatalar.append(f"{sira}. satır: şube '{ham_sube[:20]}' anlaşılamadı ve derslik boş.")
                    continue
                uyarilar.append(f"{sira}. satır: şube '{ham_sube[:20]}' anlaşılamadı; boş bırakıldı.")
        d_anahtar = ""
        if derslik:
            d_anahtar = metin.derslik_anahtari(derslik)
            bilgi["derslik"].setdefault(d_anahtar, {"ad": derslik, "adaylar": [derslik]})
        siniflar = []
        if sube:
            bilgi["sinif"].setdefault(sube, {"ad": sube, "adaylar": [sube]})
            siniflar = [sube]
        for n in dersler:
            anahtar = f"{devre}|{n}"
            bilgi["saat"].setdefault(anahtar, {"period": str(n), "ad": f"{gun_devreleri[gun][devre]} · {n}. ders",
                                               "bas": "", "bit": ""})  # fmt: skip
            ara.append({"d": d_anahtar, "s": siniflar, "g": gun, "p": anahtar, "n": sira})
    if yok_sayilan:
        uyarilar.append("Şu sütunlar yok sayıldı (okunmaz ve saklanmaz): " + ", ".join(yok_sayilan))
    return {"ara": ara, "bilgi": bilgi, "hatalar": hatalar[:HATA_GOSTERIM], "hata_sayisi": len(hatalar),
            "uyarilar": uyarilar, "yok_sayilan": yok_sayilan, "satir_sayisi": len(satirlar)}  # fmt: skip


def yz_metni_temizle(metin_: str) -> tuple[str, list[str]]:
    """Yapıştırılan yapay zekâ çıktısını CSV'ye indirger (şartname §5.5): kod bloğu işaretleri, başlıktan önceki ve
    sonraki açıklama satırları atılır. Başlık = `gun` ve (`sube` ya da `derslik`) içeren ilk satır. Döndürür
    (temiz CSV metni, uyarılar). Başlık yoksa ya da 512 KB'ı aşarsa ValueError."""
    if len(metin_.encode("utf-8")) > YZ_METIN_EN_COK:
        raise ValueError(f"Yapıştırılan metin en çok {YZ_METIN_EN_COK // 1024} KB olabilir.")
    satirlar = metin_.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    satirlar = [s for s in satirlar if not s.strip().startswith("```")]
    baslik = None
    for i, s in enumerate(satirlar):
        parcalar = {metin.katla(p).strip(" \"'") for p in re.split(r"[;\t,]", s)}
        if "gun" in parcalar and parcalar & {"sube", "derslik"}:
            baslik = i
            break
    if baslik is None:
        raise ValueError("Metinde başlık satırı (sube;gun;ders;devre;derslik) bulunamadı.")
    uyarilar = []
    if baslik:
        uyarilar.append(f"Başlıktan önceki {baslik} satır (açıklama) atıldı.")
    govde = [s for s in satirlar[baslik + 1 :] if s.strip()]
    kalan = [s for s in govde if re.search(r"[;\t,]", s)]
    if len(govde) != len(kalan):
        uyarilar.append(f"Ayraç içermeyen {len(govde) - len(kalan)} satır (açıklama) atıldı.")
    return "\n".join([satirlar[baslik], *kalan]) + "\n", uyarilar


# ==== 3. Eşleme ve çözüm =================================================================================
def sube_sira_anahtari(sube: str) -> tuple:
    """Şubeleri düzey sırasıyla dizer: Hazırlık/A, 9/A, 9/B, 10/A… (birleşik derste "ilk şube" budur)."""
    duzey, _, harf = sube.partition("/")
    return (0 if duzey == "Hazırlık" else int(duzey) if duzey.isdigit() else 99, metin.tr_sirala_anahtari(harf))


def tahta_listesi(b) -> list[dict]:
    return [dict(t) for t in b.execute("SELECT id, ad, derslik, subeler FROM tahta WHERE durum != 'iptal' ORDER BY ad")]


def hatirlanan_oku(b, kaynak: str) -> dict[tuple[str, str], dict]:
    gecerli = {t["id"] for t in b.execute("SELECT id FROM tahta WHERE durum != 'iptal'")}
    sonuc = {}
    for s in b.execute("SELECT * FROM program_eslesme WHERE kaynak = ?", (kaynak,)):
        if s["tur"] in ("derslik", "sube") and s["tahta_id"] is not None and s["tahta_id"] not in gecerli:
            continue  # tahta kaldırıldı: satır yok sayılır
        sonuc[(s["tur"], s["anahtar"])] = {"tahta_id": s["tahta_id"], "deger": s["deger"]}
    return sonuc


def _saat_onerisi(bilgi_: dict, saatler: list[tuple], devre_secimi: str) -> str | None:
    """aSc ders saati → 'devre|no' önerisi (şartname §3.5); bulunamazsa None, '0' ya da karşılıksızsa 'yok'."""
    period = str(bilgi_.get("period", ""))
    devreler = sorted({s[1] for s in saatler})
    if period in ("0", ""):
        return "yok"
    if bilgi_.get("bas"):
        hedef = program.dk(bilgi_["bas"])
        adaylar: dict[tuple[str, int], int] = {}
        for _g, devre, _a, no, bas, _b in saatler:
            if abs(program.dk(bas) - hedef) <= SAAT_TOLERANS_DK:
                adaylar[(devre, no)] = adaylar.get((devre, no), 0) + 1
        if len({d for d, _n in adaylar}) == 1:
            devre, no = max(adaylar, key=lambda a: (adaylar[a], -a[1]))
            return f"{devre}|{no}"
    if not period.isdigit():
        return None
    no = int(period)
    if len(devreler) == 1:
        devre = devreler[0]
    elif devre_secimi in devreler:
        devre = devre_secimi
    else:
        return None
    return f"{devre}|{no}" if any(s[1] == devre and s[3] == no for s in saatler) else "yok"


def esle(veri: dict, saatler: list[tuple], tahtalar: list[dict], hatirlanan: dict, secimler: dict) -> dict:
    """Ara biçimi eşleme ile `tahta_ders` satırlarına çevirir (saf işlev).

    veri: {"kaynak": "asc"|"tablo", "ara", "bilgi"}; secimler: {"derslik": {anahtar: "id"|""}, "sinif": {anahtar: şube},
    "saat": {anahtar: "devre|no"|"yok"}, "sube": {şube: "id"|""}, "devre_secimi": devre}.
    Döndürür {"satirlar": {tahta_id: {(gun, devre, no): sube}}, "kapsam": {(tahta_id, devre)}, "hatalar", "hata_sayisi",
    "uyarilar", "eslesme": {tur: [satır]}, "dersliksiz": [..], "dersliksiz_sayi", "atlanan", "yerlesim_sayisi"}.
    """
    kaynak = veri["kaynak"]
    bilgi = veri["bilgi"]
    devre_adlari = {s[1]: s[2] for s in saatler}
    nolar = {(s[0], s[1], s[3]) for s in saatler}
    hatalar: list[str] = []
    uyarilar: list[str] = []
    aktif = {t["id"]: t for t in tahtalar}
    derslige: dict[str, list[int]] = {}
    ada: dict[str, list[int]] = {}
    for t in tahtalar:
        if t.get("derslik"):
            derslige.setdefault(metin.derslik_anahtari(t["derslik"]), []).append(t["id"])
        ada.setdefault(metin.derslik_anahtari(t["ad"]), []).append(t["id"])
    subeye: dict[str, list[int]] = {}
    for t in tahtalar:
        for s in str(t.get("subeler") or "").split(","):
            if s.strip():
                subeye.setdefault(s.strip(), []).append(t["id"])

    def sec(tur: str, anahtar: str):
        return (secimler.get(tur) or {}).get(anahtar)

    eslesme: dict[str, list[dict]] = {"derslik": [], "sinif": [], "saat": [], "sube": []}
    # derslik → tahta(lar)
    derslik_sonuc: dict[str, list[int] | None] = {}
    for anahtar, b_ in sorted(bilgi["derslik"].items(), key=lambda x: metin.tr_sirala_anahtari(x[1]["ad"])):
        secim, durum = sec("derslik", anahtar), "otomatik"
        if secim is not None:
            deger = [int(secim)] if str(secim).isdigit() and int(secim) in aktif else []
            durum = "secildi"
        elif ("derslik", anahtar) in hatirlanan:
            h = hatirlanan[("derslik", anahtar)]
            deger = [h["tahta_id"]] if h["tahta_id"] in aktif else []
            durum = "hatirlanan"
        else:
            deger = None
            for aday in b_["adaylar"]:
                k = metin.derslik_anahtari(aday)
                if derslige.get(k) or ada.get(k):
                    deger = derslige.get(k) or ada.get(k)
                    break
            if deger is None:
                durum = "eslesmedi"
            elif len(deger) > 1:
                uyarilar.append(
                    f"Aynı dersliğe bağlı {len(deger)} tahta: {', '.join(aktif[i]['ad'] for i in deger)} (ikisine de uygulanacak)."
                )
        derslik_sonuc[anahtar] = deger
        eslesme["derslik"].append({"anahtar": anahtar, "ad": b_["ad"], "durum": durum,
                                   "deger": "" if not deger else str(deger[0]), "coklu": bool(deger and len(deger) > 1)})  # fmt: skip
    # sınıf → şube
    sinif_sonuc: dict[str, str] = {}
    for anahtar, b_ in sorted(bilgi["sinif"].items(), key=lambda x: metin.tr_sirala_anahtari(x[1]["ad"])):
        secim, durum = sec("sinif", anahtar), "otomatik"
        if secim is not None:
            deger = metin.sube_duzelt(secim) or ""
            durum = "secildi"
        elif ("sinif", anahtar) in hatirlanan:
            deger, durum = hatirlanan[("sinif", anahtar)]["deger"], "hatirlanan"
        else:
            deger = next((metin.sube_duzelt(a) for a in b_["adaylar"] if metin.sube_duzelt(a)), None)
            if deger is None:
                deger, durum = "", "eslesmedi"
        sinif_sonuc[anahtar] = deger
        if kaynak == "asc":
            eslesme["sinif"].append({"anahtar": anahtar, "ad": b_["ad"], "durum": durum, "deger": deger})
    # aSc ders saati → (devre, no)
    saat_sonuc: dict[str, str | None] = {}
    for anahtar, b_ in sorted(bilgi["saat"].items(), key=lambda x: (_sayi(x[1].get("period"), 99), x[0])):
        if kaynak != "asc":
            saat_sonuc[anahtar] = anahtar
            continue
        secim, durum = sec("saat", anahtar), "otomatik"
        if secim is not None:
            deger, durum = (secim if secim == "yok" or "|" in str(secim) else None), "secildi"
        elif ("saat", anahtar) in hatirlanan:
            deger, durum = hatirlanan[("saat", anahtar)]["deger"], "hatirlanan"
        else:
            deger = _saat_onerisi(b_, saatler, str(secimler.get("devre_secimi") or ""))
            if deger is None:
                durum = "eslesmedi"
            elif deger == "yok":
                uyarilar.append(f"aSc {b_['ad']}. ders saatinin zil çizelgesinde karşılığı yok; yok sayıldı.")
        saat_sonuc[anahtar] = deger
        eslesme["saat"].append({"anahtar": anahtar, "ad": b_["ad"], "bas": b_.get("bas", ""), "bit": b_.get("bit", ""),
                                "durum": durum, "deger": deger or ""})  # fmt: skip
    # yerleşimler
    sonuc: dict[int, dict[tuple[int, str, int], str]] = {}
    kapsam: set[tuple[int, str]] = set()
    sube_ihtiyaci: dict[str, list[int] | None] = {}
    dersliksiz: list[str] = []
    dersliksiz_sayi = 0
    atlanan = 0
    birlesik: set[str] = set()
    cakisma = 0
    tekrar = 0
    eslesmeyen_saat = 0
    for y in veri["ara"]:
        hedef = saat_sonuc.get(y["p"])
        if not hedef:
            eslesmeyen_saat += 1
            continue
        if hedef == "yok":
            atlanan += 1
            continue
        devre, _, no_s = hedef.partition("|")
        if not no_s.isdigit():
            eslesmeyen_saat += 1
            continue
        no = int(no_s)
        gun = int(y["g"])
        if (gun, devre, no) not in nolar:
            hatalar.append(f"{y['n']}. kart: {program.GUN_ADLARI[gun]} {no}. ders zil çizelgesinde yok.")
            continue
        subeler = sorted({sinif_sonuc.get(s) or "" for s in y["s"]} - {""}, key=sube_sira_anahtari)
        sube = subeler[0] if subeler else ""
        if y["d"]:
            idler = derslik_sonuc.get(y["d"])
            if idler is None or not idler:
                atlanan += 1
                continue
        else:
            if not sube:
                dersliksiz_sayi += 1
                if len(dersliksiz) < HATA_GOSTERIM:
                    sinif_adi = ", ".join(bilgi["sinif"].get(s, {}).get("ad", s) for s in y["s"]) or "şubesiz"
                    dersliksiz.append(f"{sinif_adi} · {program.GUN_ADLARI[gun]} {devre_adlari.get(devre, devre)} {no}. ders")
                continue
            if sube not in sube_ihtiyaci:
                secim = sec("sube", sube)
                if secim is not None:
                    sube_ihtiyaci[sube] = [int(secim)] if str(secim).isdigit() and int(secim) in aktif else []
                    durum = "secildi"
                elif ("sube", sube) in hatirlanan:
                    h = hatirlanan[("sube", sube)]
                    sube_ihtiyaci[sube] = [h["tahta_id"]] if h["tahta_id"] in aktif else []
                    durum = "hatirlanan"
                else:
                    adaylar = subeye.get(sube) or []
                    sube_ihtiyaci[sube] = adaylar if len(adaylar) == 1 else None
                    durum = "otomatik" if len(adaylar) == 1 else "eslesmedi"
                deger = sube_ihtiyaci[sube]
                eslesme["sube"].append({"anahtar": sube, "ad": sube, "durum": durum, "deger": str(deger[0]) if deger else ""})
            idler = sube_ihtiyaci[sube]
            if idler is None:  # (e) şubenin tahtası da yok: dersliksiz (eşleme adımında tahta seçilebilir)
                dersliksiz_sayi += 1
                if len(dersliksiz) < HATA_GOSTERIM:
                    dersliksiz.append(f"{sube} · {program.GUN_ADLARI[gun]} {devre_adlari.get(devre, devre)} {no}. ders")
                continue
            if not idler:
                atlanan += 1
                continue
        if len(subeler) > 1:
            yer = bilgi["derslik"].get(y["d"], {}).get("ad", "") if y["d"] else sube
            etiket = f"{yer} {zamanlama.GUN_KISA[gun]} {no}. ders: {' + '.join(subeler)} birleşik; {sube} yazıldı."
            if len(birlesik) < HATA_GOSTERIM:
                birlesik.add(etiket)
        for tahta_id in idler:
            kayit = sonuc.setdefault(tahta_id, {})
            anahtar = (gun, devre, no)
            if anahtar in kayit and kayit[anahtar] != sube:
                if kaynak == "tablo":
                    tekrar += 1
                    kayit[anahtar] = sube  # v1 ile aynı: son satır geçerli
                else:
                    cakisma += 1
                continue
            if anahtar in kayit:
                if kaynak == "tablo":
                    tekrar += 1
                continue
            kayit[anahtar] = sube
            kapsam.add((tahta_id, devre))
    if tekrar:
        uyarilar.append(f"{tekrar} ders saati dosyada birden çok kez geçiyor; son satır geçerli sayıldı.")
    if cakisma:
        uyarilar.append(f"{cakisma} ders saatinde aynı tahtaya farklı şubeler düştü; ilk şube yazıldı.")
    if birlesik:
        uyarilar.extend(sorted(birlesik))
    if eslesmeyen_saat:
        uyarilar.append(f"{eslesmeyen_saat} ders saati zil çizelgesiyle eşlenemedi; eşleme adımında devresini seçin.")
    for liste in eslesme.values():
        del liste[ESLEME_EN_COK:]
    return {
        "satirlar": sonuc,
        "kapsam": kapsam,
        "hatalar": hatalar[:HATA_GOSTERIM],
        "hata_sayisi": len(hatalar),
        "uyarilar": uyarilar,
        "eslesme": eslesme,
        "dersliksiz": dersliksiz,
        "dersliksiz_sayi": dersliksiz_sayi,
        "atlanan": atlanan,
        "yerlesim_sayisi": len(veri["ara"]),
        "eslesmedi_sayisi": sum(1 for liste in eslesme.values() for e in liste if e["durum"] == "eslesmedi"),
    }


def fark(b, cozum: dict, saatler: list[tuple] | None = None) -> dict:
    """Çözümü mevcut `tahta_ders` ile karşılaştırır. Yalnız kapsamdaki (tahta, devre) çiftleri değişir.

    Döndürür {"tahtalar": [{"id","ad","derslik","devreler","eklenen","silinen","degisen","degisiklikler":[..]}],
    "toplam": {"tahta","eklenen","silinen","degisen","dokunulmayan"}, "dokunulmayan_programli": [{"id","ad","derslik",
    "devreler"}], "devreler": [devre]}.
    """
    saatler = saatler if saatler is not None else program.ders_saatleri_oku(b)
    devre_adlari = {s[1]: s[2] for s in saatler}
    tahtalar = {t["id"]: t for t in tahta_listesi(b)}
    mevcut: dict[int, dict[tuple[int, str, int], str]] = {}
    for s in b.execute("SELECT * FROM tahta_ders"):
        mevcut.setdefault(s["tahta_id"], {})[(s["gun"], s["devre"], s["ders_no"])] = s["sube"]
    kapsam_devre: dict[int, set[str]] = {}
    for tahta_id, devre in cozum["kapsam"]:
        kapsam_devre.setdefault(tahta_id, set()).add(devre)
    sonuc = []
    toplam = {"tahta": 0, "eklenen": 0, "silinen": 0, "degisen": 0, "dokunulmayan": 0}
    for tahta_id, devreler in kapsam_devre.items():
        if tahta_id not in tahtalar:
            continue
        yeni = cozum["satirlar"].get(tahta_id, {})
        eski = {a: s for a, s in mevcut.get(tahta_id, {}).items() if a[1] in devreler}
        degisiklikler = []
        for a in sorted(set(yeni) | set(eski)):
            if a in yeni and a not in eski:
                isaret = "+"
            elif a in eski and a not in yeni:
                isaret = "−"
            elif eski[a] != yeni[a]:
                isaret = "~"
            else:
                continue
            degisiklikler.append({"isaret": isaret, "gun": a[0], "gun_adi": program.GUN_ADLARI[a[0]],
                                  "devre": a[1], "devre_adi": devre_adlari.get(a[1], a[1]), "no": a[2],
                                  "sube_eski": eski.get(a, ""), "sube_yeni": yeni.get(a, "")})  # fmt: skip
        say = {i: sum(1 for d in degisiklikler if d["isaret"] == i) for i in "+−~"}
        if not degisiklikler:
            continue
        t = tahtalar[tahta_id]
        sonuc.append({"id": tahta_id, "ad": t["ad"], "derslik": t["derslik"],
                      "devreler": ", ".join(devre_adlari.get(d, d) for d in sorted(devreler)),
                      "eklenen": say["+"], "silinen": say["−"], "degisen": say["~"],
                      "degisiklikler": degisiklikler[:400]})  # fmt: skip
        toplam["tahta"] += 1
        toplam["eklenen"] += say["+"]
        toplam["silinen"] += say["−"]
        toplam["degisen"] += say["~"]
    tum_devreler = {d for _t, d in cozum["kapsam"]}
    dokunulmayan = []
    for tahta_id, satirlar in mevcut.items():
        if tahta_id in kapsam_devre or tahta_id not in tahtalar:
            continue
        devreler = sorted({a[1] for a in satirlar} & tum_devreler)
        if devreler:
            t = tahtalar[tahta_id]
            dokunulmayan.append({"id": tahta_id, "ad": t["ad"], "derslik": t["derslik"],
                                 "devreler": ", ".join(devre_adlari.get(d, d) for d in devreler)})  # fmt: skip
    toplam["dokunulmayan"] = len([t for t in tahtalar if t not in kapsam_devre])
    sonuc.sort(key=lambda t: metin.tr_sirala_anahtari(t["ad"]))
    dokunulmayan.sort(key=lambda t: metin.tr_sirala_anahtari(t["ad"]))
    return {"tahtalar": sonuc, "toplam": toplam, "dokunulmayan_programli": dokunulmayan,
            "devreler": sorted(tum_devreler)}  # fmt: skip


def ozet_metni(fark_: dict) -> str:
    t = fark_["toplam"]
    return (f"{t['tahta']} tahtanın programı değişecek · {t['eklenen']} ders saati eklenecek · {t['silinen']} silinecek · "
            f"{t['degisen']} şubesi değişecek · dokunulmayacak {t['dokunulmayan']} tahta")  # fmt: skip


def sube_sayilari(cozum: dict) -> list[tuple[str, int]]:
    """Yapay zekâ kaynağında gözle denetim için şube başına haftalık ders sayısı: [("9/A", 40), …]."""
    sayi: dict[str, set] = {}
    for tahta_satirlari in cozum["satirlar"].values():
        for (g, d, n), s in tahta_satirlari.items():
            if s:
                sayi.setdefault(s, set()).add((g, d, n))
    return sorted(((s, len(v)) for s, v in sayi.items()), key=lambda x: sube_sira_anahtari(x[0]))


# ==== 4. Uygulama, sürümler, geri yükleme =====================================================================
def _anlik(b) -> list[list]:
    return [[s["tahta_id"], s["gun"], s["devre"], s["ders_no"], s["sube"]]
            for s in b.execute("SELECT * FROM tahta_ders ORDER BY tahta_id, gun, devre, ders_no")]  # fmt: skip


def surum_yaz(b, kullanici: str, neden: str, bicim: str) -> int:
    """Mevcut `tahta_ders`'in tamamını `program_surum`'e yazar; en yeni SURUM_SAKLA sürüm kalır."""
    veri = _anlik(b)
    kimlik = b.execute(
        "INSERT INTO program_surum (zaman, kullanici, neden, bicim, satir_sayisi, tahta_sayisi, veri_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (vt.simdi(), kullanici, neden, bicim, len(veri), len({s[0] for s in veri}), json.dumps(veri)),
    ).lastrowid
    b.execute(
        "DELETE FROM program_surum WHERE id NOT IN (SELECT id FROM program_surum ORDER BY zaman DESC, id DESC LIMIT ?)",
        (SURUM_SAKLA,),
    )
    return kimlik


def eslesmeleri_yaz(b, kaynak: str, cozum: dict) -> int:
    """Onayda kullanılan eşlemeler hatırlanır (`program_eslesme`). Yazılan satır sayısını döndürür."""
    an = vt.simdi()
    sayi = 0
    for tur, liste in cozum["eslesme"].items():
        for e in liste:
            if e["durum"] == "eslesmedi" or e.get("coklu"):
                continue
            if tur in ("derslik", "sube"):
                tahta_id, deger = (int(e["deger"]) if str(e["deger"]).isdigit() else None), ""
            else:
                tahta_id, deger = None, str(e["deger"] or "")
            b.execute(
                "INSERT INTO program_eslesme (kaynak, tur, anahtar, tahta_id, deger, guncelleme) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(kaynak, tur, anahtar) DO UPDATE SET tahta_id = excluded.tahta_id, deger = excluded.deger, "
                "guncelleme = excluded.guncelleme",
                (kaynak, tur, e["anahtar"], tahta_id, deger, an),
            )
            sayi += 1
    return sayi


def uygula(b, cozum: dict, kullanici: str, bicim: str, kaynak: str, temizle: list[int] | None = None) -> dict:
    """Onay (tek işlem; çağıran `vt.islem()` içinde): önce bütün `tahta_ders` sürüm olarak saklanır, sonra yalnız
    kapsamdaki (tahta, devre) çiftleri silinip yeniden yazılır; `temizle` verilen (dosyada geçmeyen) tahtaların aynı
    devre satırları da silinir; eşlemeler hatırlanır. Döndürür {"surum_id","tahta","satir","temizlenen"}."""
    surum_id = surum_yaz(b, kullanici, "aktarim", bicim)
    gecerli = {t["id"] for t in b.execute("SELECT id FROM tahta WHERE durum != 'iptal'")}
    satir = 0
    tahtalar = set()
    for tahta_id, devre in sorted(cozum["kapsam"]):
        if tahta_id not in gecerli:
            continue
        b.execute("DELETE FROM tahta_ders WHERE tahta_id = ? AND devre = ?", (tahta_id, devre))
        tahtalar.add(tahta_id)
    for tahta_id, kayit in cozum["satirlar"].items():
        if tahta_id not in gecerli:
            continue
        for (gun, devre, no), sube in sorted(kayit.items()):
            b.execute(
                "INSERT OR REPLACE INTO tahta_ders (tahta_id, gun, devre, ders_no, sube) VALUES (?, ?, ?, ?, ?)",
                (tahta_id, gun, devre, no, sube),
            )
            satir += 1
    temizlenen = 0
    devreler = sorted({d for _t, d in cozum["kapsam"]})
    kapsamdakiler = {t for t, _d in cozum["kapsam"]}
    for tahta_id in sorted(set(temizle or [])):
        if tahta_id in kapsamdakiler or tahta_id not in gecerli or not devreler:
            continue
        temizlenen += b.execute(
            f"DELETE FROM tahta_ders WHERE tahta_id = ? AND devre IN ({','.join('?' * len(devreler))})",
            (tahta_id, *devreler),
        ).rowcount
    eslesmeleri_yaz(b, kaynak, cozum)
    return {"surum_id": surum_id, "tahta": len(tahtalar), "satir": satir, "temizlenen": temizlenen}


def geri_yukle(b, surum_id: int, kullanici: str) -> dict | None:
    """Önce mevcut durum yeni sürüm olarak saklanır (geri almanın da geri alınabilmesi için), sonra `tahta_ders`
    tümüyle silinip anlık görüntü yazılır; kaldırılmış (iptal) tahtaların satırları atlanır, artık olmayan ders
    saatleri yazılır (yetim olarak görünür). Sürüm yoksa None."""
    satir = b.execute("SELECT * FROM program_surum WHERE id = ?", (surum_id,)).fetchone()
    if not satir:
        return None
    try:
        veri = json.loads(satir["veri_json"])
    except ValueError:
        return None
    zaman, kaynak_id = satir["zaman"], satir["id"]
    surum_yaz(b, kullanici, "geri_yukleme", "")
    gecerli = {t["id"] for t in b.execute("SELECT id FROM tahta WHERE durum != 'iptal'")}
    b.execute("DELETE FROM tahta_ders")
    yazilan = 0
    for tahta_id, gun, devre, no, sube in veri:
        if tahta_id not in gecerli:
            continue
        b.execute(
            "INSERT OR REPLACE INTO tahta_ders (tahta_id, gun, devre, ders_no, sube) VALUES (?, ?, ?, ?, ?)",
            (int(tahta_id), int(gun), str(devre), int(no), str(sube or "")),
        )
        yazilan += 1
    return {"satir": yazilan, "zaman": zaman, "id": kaynak_id}


def surum_listesi(b) -> list[dict]:
    """Program › Derslik programları "Önceki programlar": [{"id","zaman_metni","kullanici","neden_adi","bicim_adi",
    "tahta_sayisi","satir_sayisi"}], en yeni önce."""
    return [
        {"id": s["id"], "zaman_metni": datetime.fromtimestamp(s["zaman"], program.ISTANBUL).strftime("%d.%m.%Y %H:%M"),
         "kullanici": s["kullanici"], "neden": s["neden"], "neden_adi": NEDEN_ADI.get(s["neden"], s["neden"]),
         "bicim_adi": BICIM_ADI.get(s["bicim"], s["bicim"]) if s["bicim"] else "",
         "tahta_sayisi": s["tahta_sayisi"], "satir_sayisi": s["satir_sayisi"]}
        for s in b.execute("SELECT id, zaman, kullanici, neden, bicim, tahta_sayisi, satir_sayisi FROM program_surum "
                           "ORDER BY zaman DESC, id DESC")
    ]  # fmt: skip


# ==== 5. Şablon, mevcut program ve istem =======================================================================
SABLON_BASLIK = ["sube", "gun", "ders", "devre", "derslik"]


def sablon_csv(saatler: list[tuple]) -> bytes:
    """Boş şablon: başlık + mevcut zil yapısına göre 3 UYDURMA satır (şubeler 9/A, 10/B; derslikler Z-04, Fizik Lab)."""
    gunler = sorted({s[0] for s in saatler}) or [0, 1, 2]
    ornekler = [("9/A", ""), ("10/B", "Z-04"), ("9/A", "Fizik Lab")]
    satirlar = []
    for sira, (sube, derslik) in enumerate(ornekler):
        gun = gunler[sira % len(gunler)]
        devreler = sorted({s[1] for s in saatler if s[0] == gun}) or ["normal"]
        devre = devreler[sira % len(devreler)]
        nolar = sorted(s[3] for s in saatler if s[0] == gun and s[1] == devre) or [1, 2, 3, 4]
        if sira == 0:
            ders = f"{nolar[0]}-{nolar[min(3, len(nolar) - 1)]}" if len(nolar) > 1 else str(nolar[0])
        elif sira == 1:
            ders = ",".join(str(n) for n in nolar[1:3]) or str(nolar[0])
        else:
            ders = str(nolar[-1])
        adi = next((s[2] for s in saatler if s[1] == devre), "")
        satirlar.append([sube, program.GUN_ADLARI[gun], ders, adi if len(devreler) > 1 else "", derslik])
    return metin.csv_yaz(SABLON_BASLIK, satirlar)


def mevcut_csv(b) -> bytes:
    """Mevcut derslik programının v2 dökümü: bir satır = tahta·gün·devre·ders (derslik = tahta.derslik ya da ad).
    Formül kaçışlı (`metin.csv_yaz`); geri yüklenince `csv_hucre_coz` kaçışı geri alır."""
    saatler = program.ders_saatleri_oku(b)
    devre_adlari = {s[1]: s[2] for s in saatler}
    cok_devre = len(devre_adlari) > 1
    satirlar = []
    for s in b.execute(
        "SELECT d.*, t.ad, t.derslik FROM tahta_ders d JOIN tahta t ON t.id = d.tahta_id WHERE t.durum != 'iptal' "
        "ORDER BY t.ad, d.gun, d.devre, d.ders_no"
    ):
        satirlar.append([s["sube"], program.GUN_ADLARI[s["gun"]], str(s["ders_no"]),
                         devre_adlari.get(s["devre"], s["devre"]) if cok_devre else "", s["derslik"] or s["ad"]])  # fmt: skip
    return metin.csv_yaz(SABLON_BASLIK, satirlar)


ISTEM = """Sen bir veri dönüştürücüsün. Sana bir okulun haftalık ders programını vereceğim (Excel, PDF,
tablo ya da fotoğraf). Görevin bu programı aşağıdaki CSV biçimine dönüştürmek. Yalnız CSV yaz.

ÇIKTI KURALLARI
1. Çıktın YALNIZ CSV metni olsun: açıklama, başlık cümlesi, not, özet, kod bloğu işareti (```)
   YAZMA. İlk satır tam olarak şu başlık olsun:
   sube;gun;ders;devre;derslik
2. Ayraç noktalı virgüldür (;). Her satır bir şubenin bir günde art arda gelen dersleridir.
3. sube: sınıf ve şube, "9/A" biçiminde (düzey, eğik çizgi, büyük harf şube). Hazırlık sınıfı
   "Hazırlık/A". Programda böyle yazılmamışsa (9-A, 9A, 9. Sınıf A Şubesi) bu biçime çevir.
4. gun: şu yazımlardan biri, aynen: Pazartesi, Salı, Çarşamba, Perşembe, Cuma, Cumartesi.
5. ders: o gün o şubenin dersi OLAN ders saatlerinin numaraları. Art arda olanları aralıkla yaz
   (1-4), arada boş varsa virgülle (1-3,5,7). Numara, okulun aşağıdaki ders saati tablosundaki
   numaradır; programda yalnız saat yazıyorsa saati tablodan numaraya çevir. Boş (dersi olmayan)
   saatleri YAZMA.
6. devre: {DEVRE_KURALI}
7. derslik: programda dersin yapıldığı derslik/laboratuvar/atölye adı açıkça yazıyorsa onu yaz
   (ör. "Fizik Lab", "Z-04"). Şube kendi sınıfında ders görüyorsa ya da derslik yazmıyorsa BOŞ bırak.
   Aynı gün farklı dersliklerde yapılan dersler için her derslik ayrı satır olsun.
8. Ders adı, öğretmen adı, öğretmen kısaltması, öğrenci adı, numara ya da başka hiçbir kişisel bilgi
   YAZMA. Bu bilgiler için sütun yoktur; kaynakta olsalar bile çıktıya koyma.
9. Bilmediğin, okuyamadığın ya da emin olmadığın bir değeri UYDURMA. Okuyamadığın hücreyi atla.
   Bir şubenin programını hiç okuyamadıysan o şubeyi hiç yazma. Tahmin etme.
10. Programda olmayan bir şube, gün ya da ders saati EKLEME.
11. Bir şube aynı gün aynı saatte iki gruba ayrılıp iki farklı derslikte ders görüyorsa her derslik
    için ayrı satır yaz (sube aynı, derslik farklı).

OKULUN DERS SAATİ TABLOSU
{DEVRE_TABLOSU}

ÖRNEK (uydurma; biçimi göstermek içindir, içeriğini kopyalama)
sube;gun;ders;devre;derslik
9/A;Pazartesi;1-6;{ORNEK_DEVRE_1};
9/A;Pazartesi;7-8;{ORNEK_DEVRE_1};Fizik Lab
10/B;Salı;1-3,5;{ORNEK_DEVRE_2};
Hazırlık/A;Cuma;2,4-6;{ORNEK_DEVRE_1};Z-04

Şimdi sana vereceğim programı bu kurallarla dönüştür. Yalnız CSV yaz.
"""


def istem_metni(saatler: list[tuple]) -> str:
    """Okulun zil yapısıyla doldurulmuş istem (şartname §5.3). Okul adı, kurum kodu, kişi, derslik ve tahta adı içermez."""
    devreler: dict[str, str] = {}
    ilk: dict[str, int] = {}
    for _g, devre, adi, _n, bas, _b in saatler:
        devreler.setdefault(devre, adi)
        ilk[devre] = min(ilk.get(devre, 24 * 60), program.dk(bas))
    sirali = sorted(devreler, key=lambda d: (ilk[d], d))
    turler = program.devre_turleri(saatler)
    tek = len(sirali) <= 1
    satirlar = []
    for devre in sirali:
        gunluk: dict[tuple, list[int]] = {}
        for g in sorted({s[0] for s in saatler if s[1] == devre}):
            imza = tuple((s[3], s[4], s[5]) for s in sorted(saatler, key=lambda s: s[3]) if s[0] == g and s[1] == devre)
            gunluk.setdefault(imza, []).append(g)
        gruplar = sorted(gunluk.items(), key=lambda x: (-len(x[1]), x[1][0]))
        onek = "Ders saatleri" if tek else devreler[devre]
        for sira, (imza, gunler) in enumerate(gruplar):
            dersler = ", ".join(f"{n}. ders {b_}-{s_}" for n, b_, s_ in imza)
            ek = "" if sira == 0 else f" ({', '.join(program.GUN_ADLARI[g] for g in gunler)})"
            satirlar.append(f"{onek}{ek}: {dersler}")
    if tek:
        kural = "Bu okulda tek devre var; bu sütunu BOŞ bırak."
        ornek1 = ornek2 = ""
    else:
        sabah = next((devreler[d] for d in sirali if turler.get(d) == "sabah"), devreler[sirali[0]])
        ogle = next((devreler[d] for d in sirali if turler.get(d) == "ogle"), devreler[sirali[-1]])
        kural = (f"Bu okulda ikili eğitim var. Sabahçı şubeler için \"{sabah}\", öğlenci şubeler için \"{ogle}\" yaz. "
                 "Hangi devre olduğu programdan anlaşılmıyorsa ders saatlerine bak; yine anlaşılmıyorsa o satırı YAZMA.")  # fmt: skip
        ornek1, ornek2 = sabah, ogle
    return (ISTEM.replace("{DEVRE_KURALI}", kural).replace("{DEVRE_TABLOSU}", "\n".join(satirlar) or "(tanımlı değil)")
            .replace("{ORNEK_DEVRE_1}", ornek1).replace("{ORNEK_DEVRE_2}", ornek2))  # fmt: skip


# ==== 6. Önizleme kaydı ==========================================================================================
def onizleme_verisi(kaynak: str, bicim: str, bayt_ozeti: str, okunan: dict, asc: dict | None = None) -> dict:
    """`program_onizleme` (tur='aktar') içine yazılacak veri. Kişi, öğretmen, ders adı içermez; JSON 2 MB'ı aşarsa
    ValueError. okunan: tablo_oku sonucu (tablo) ya da asc_ara sonucu (asc; ara yeniden hesaplanır, saklanmaz)."""
    veri = {
        "kaynak": kaynak,
        "bicim": bicim,
        "ozet": {"sha256": bayt_ozeti, "satir_sayisi": okunan.get("satir_sayisi"), "kart_sayisi": okunan.get("kart_sayisi")},
        "asc": asc,
        "ara": None if asc is not None else okunan["ara"],
        "bilgi": None if asc is not None else okunan["bilgi"],
        "kaynak_hatalari": [] if asc is not None else okunan["hatalar"],
        "kaynak_hata_sayisi": 0 if asc is not None else okunan["hata_sayisi"],
        "kaynak_uyarilari": [] if asc is not None else okunan["uyarilar"],
        "secimler": {"derslik": {}, "sinif": {}, "saat": {}, "sube": {}, "donem": "", "devre_secimi": ""},
    }
    if len(json.dumps(veri, ensure_ascii=False).encode("utf-8")) > ONIZLEME_EN_COK_BAYT:
        raise ValueError("Program çok büyük; devre devre yükleyin.")
    return veri


def coz(b, veri: dict) -> dict:
    """Önizleme verisinden güncel çözüm + fark + gösterim alanları (her istekte yeniden hesaplanır)."""
    saatler = program.ders_saatleri_oku(b)
    secimler = veri.get("secimler") or {}
    if veri["kaynak"] == "asc":
        okunan = asc_ara(veri["asc"], secimler)
        girdi = {"kaynak": "asc", "ara": okunan["ara"], "bilgi": okunan["bilgi"]}
        kaynak_hatalari, kaynak_hata_sayisi = okunan["hatalar"], okunan["hata_sayisi"]
        kaynak_uyarilari = okunan["uyarilar"]
        donemler, secili_donem = okunan["donemler"], okunan["secili_donem"]
    else:
        girdi = {"kaynak": "tablo", "ara": veri["ara"], "bilgi": veri["bilgi"]}
        kaynak_hatalari, kaynak_hata_sayisi = veri["kaynak_hatalari"], veri["kaynak_hata_sayisi"]
        kaynak_uyarilari = veri["kaynak_uyarilari"]
        donemler, secili_donem = [], None
    hatirlanan = hatirlanan_oku(b, "asc" if veri["kaynak"] == "asc" else "tablo")
    tahtalar = tahta_listesi(b)
    cozum = esle(girdi, saatler, tahtalar, hatirlanan, secimler)
    f = fark(b, cozum, saatler)
    hata_sayisi = kaynak_hata_sayisi + cozum["hata_sayisi"]
    toplam = max(1, cozum["yerlesim_sayisi"] + kaynak_hata_sayisi)
    devreler = sorted({s[1] for s in saatler})
    ilk_saat: dict[tuple[str, int], tuple[str, str]] = {}
    for _g, devre, adi, no, bas, _b in sorted(saatler):
        ilk_saat.setdefault((devre, no), (adi, bas))
    saat_secenekleri = [{"deger": f"{d}|{n}", "ad": f"{adi} · {n}. ders ({bas})"}
                        for (d, n), (adi, bas) in sorted(ilk_saat.items(), key=lambda x: (x[1][1], x[0]))]  # fmt: skip
    return {
        "cozum": cozum,
        "fark": f,
        "ozet_metni": ozet_metni(f),
        "hatalar": (kaynak_hatalari + cozum["hatalar"])[:HATA_GOSTERIM],
        "hata_sayisi": hata_sayisi,
        "uyarilar": kaynak_uyarilari + cozum["uyarilar"],
        "cok_hata": hata_sayisi > HATA_ORANI * toplam,
        "onaylanabilir": f["toplam"]["tahta"] > 0 or bool(f["dokunulmayan_programli"] and cozum["kapsam"]),
        "donemler": donemler,
        "secili_donem": secili_donem,
        "devre_sorusu": veri["kaynak"] == "asc" and len(devreler) > 1
                        and any(e["durum"] == "eslesmedi" for e in cozum["eslesme"]["saat"]),  # fmt: skip
        "devre_secenekleri": [(d, next(s[2] for s in saatler if s[1] == d)) for d in devreler],
        "saat_secenekleri": saat_secenekleri,
        "tahta_secenekleri": [(t["id"], t["ad"] + (f" · {t['derslik']}" if t["derslik"] else "")) for t in tahtalar],
        "sube_sayilari": sube_sayilari(cozum) if veri["bicim"] in ("yz", "yz_dosya") else [],
        "esleme_gerekli": veri["kaynak"] == "asc" or cozum["eslesmedi_sayisi"] > 0,
    }
