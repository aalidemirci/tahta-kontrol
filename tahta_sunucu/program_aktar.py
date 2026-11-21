"""Ders programını içe aktarma sihirbazı (0.10.0): aSc Timetables XML, Tahta Kontrol şablonu (CSV/XLSX/XLS)
ve yapay zekâ çıktısı (yapıştırılan CSV). 0.12.0: e-Okul "Haftalık Ders Programları" raporu (OOK11002_R01, .XLS;
ayrıştırma ve şube/devre eşlemesi `eokul_program.py`'de, sonrası buradaki ortak yol).

Yalnız derslik programı (`tahta_ders`) değişir; zil saatleri değişmez. Bütün kaynaklar aynı ara biçime iner:

    yerleşim = {"d": derslik anahtarı ('' = belli değil), "s": [sınıf anahtarları], "g": gün 0..6,
                "p": saat anahtarı (aSc: 'period|starttime'; tablo: 'devre|no'), "n": kaynak satır/kart no}

ve ayrı `bilgi` sözlükleri ({"derslik": {anahtar: {"ad","adaylar"}}, "sinif": {...}, "saat": {...}}) taşır.
Öğretmen, ders adı, öğrenci ve kişi verisi HİÇBİR aşamada okunmaz ve saklanmaz: aSc'nin `teachers`,
`subjects`, `students`, `studentsubjects`, `classroomsupervisions` bölümleri ayrıştırılırken içleri atlanır,
`lesson@teacherids` ve `lesson@subjectid` okunmaz; tablodaki bilinmeyen sütunlar (ör. öğretmen) okunmaz.

Veritabanına yalnız `uygula` ve `geri_yukle` yazar (+ işlem kaydını çağıran düşer). Tahta Kontrol hiçbir dış
hizmete bağlanmaz; yapay zekâ yolu yalnız istemi gösterir ve kullanıcının yapıştırdığı sonucu okur.

aSc varsayımları (0.21.0'da bir okulun gerçek "aSc Timetables 2012 XML" dışa aktarımıyla doğrulandı; dosya depoya
girmez): gün maskesi Pazartesi'den başlar (tek günlük `daysdef` adlarından da kurulur), blok derste de her ders saati
ayrı karttır (`n*ppc == ppw` genişlemesi yalnız eski/başka dışa aktarımlar için durur), `class@classroomids` sınıfın
kendi (ana) dersliğidir. İkili eğitimde ders saatleri "S1…S8" / "Ö1…Ö8" gibi önekle adlandırılır; önek devre, sayı
devre içindeki ders numarasıdır (K1, kural 25; `asc_devre_gruplari`).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime

from . import cizelge, eokul, eokul_program, guvenli_xml, guvenlik, hedef, metin, program, vt, xlsx, zamanlama

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
ASC_EN_COK_ARA = 50
DEVRE_HAPSI_ORANI = 0.9  # ikili eğitim: sınıfların en az %90'ı tek devrenin saatlerini kullanır
DEVRE_KAPSAMA = 0.6  # önek yoksa: tek devrede kalan sınıflar o devrenin saatlerinin ortalama en az %60'ını kullanır
DENEME_SINIRI = 10

BICIM_ADI = {"asc": "aSc Timetables XML", "csv": "CSV", "xlsx": "Excel (.xlsx)", "xls": "Excel 97-2003 (.xls)",
             "yz": "Yapay zekâ çıktısı (yapıştırma)", "yz_dosya": "Yapay zekâ çıktısı (dosya)",
             "eokul": "e-Okul raporu (OOK11002_R01)", "": "—"}  # fmt: skip
NEDEN_ADI = {"aktarim": "İçe aktarma öncesi", "geri_yukleme": "Geri yükleme öncesi"}
ASC_DEGIL = "Bu bir aSc Timetables XML dosyası değil."
ASC_OKUNAMADI = "aSc XML dosyası okunamadı; aSc'den yeniden dışa aktarıp deneyin."
ASC_BUYUK = "Dosya beklenenden büyük; aSc'den yalnız bu okulun programını dışa aktarın."
TC_RET = "Dosyada kimlik numarasına benzeyen değer var; silip yeniden yükleyin."
ZIL_YOK = "Önce zil saatlerini girin; derslik programı ders saatlerine göre okunur."
ASC_SAATSIZ = ("Dosyadaki ders saatlerinin başlangıç saati yazılmamış ve zil saatleri tanımlı değil; zil çizelgesi bu "
               "dosyadan oluşturulamıyor. Önce zil saatlerini girin, sonra dosyayı yeniden yükleyin.")

# aSc: okunan bölümler ve öğe başına izinli öznitelikler (geri kalanı okunmaz).
ASC_IZINLI = {
    ("periods", "period"): ("period", "name", "short", "starttime", "endtime"),
    ("breaks", "break"): ("break", "starttime", "endtime"),  # 0.21.0: devre arası ipucu (ad okunmaz)
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

    {"periods": {no: {name, short, starttime, endtime}}, "breaks": [{break, starttime, endtime}], "daysdefs": [..],
    "weeksdefs": {id: weeks},
    "termsdefs": [{id, name, terms}], "classrooms": {id: {name, short}}, "classes": {id: {name, short, classroomids}},
    "groups": {id: {classid}}, "lessons": {id: {...}}, "cards": [{...}], "uyarilar": [..]}
    """
    if len(bayt) > ASC_EN_COK_BAYT:
        raise ValueError(f"Dosya en çok {ASC_EN_COK_BAYT // (1024 * 1024)} MB olabilir.")
    veri = guvenli_xml.kodlama_duzelt(bayt)
    guvenli_xml.on_denetim(veri)
    sonuc: dict = {"periods": {}, "breaks": [], "daysdefs": [], "weeksdefs": {}, "termsdefs": [], "classrooms": {}, "classes": {},
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
        elif ad == "break":
            if len(sonuc["breaks"]) < ASC_EN_COK_ARA:
                sonuc["breaks"].append(kayit)
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


# Ders saati adı: harf öneki + devre içindeki numara ("S1", "Ö 3", "S-8", "Ö.2"); önek en çok 8 harf.
_RAKAMLI_AD = re.compile(r"\d+(?:\s*[-./]\s*\d+)*")  # yalnız numaradan oluşan tahta adı (rakam adayı)
_ONEK = re.compile(r"\s*([^\W\d_]{1,8})\s*[-.]?\s*(\d{1,2})\s*\.?\s*")


def _hapis_orani(sinif_saatleri: dict[str, set[str]], bolumler: list[set[str]]) -> float | None:
    """Ders saati kullanan sınıfların kaçta kaçı yalnız TEK bir bölümün saatlerini kullanıyor (ikili eğitimde sabahçı
    şube öğle saatini kullanmaz). Herhangi bir bölüme hiç sınıf düşmüyorsa 0; dersi olan sınıf yoksa None."""
    return _hapis(sinif_saatleri, bolumler)[0]


def _hapis(sinif_saatleri: dict[str, set[str]], bolumler: list[set[str]]) -> tuple[float | None, float]:
    """(_hapis_orani, kapsama): kapsama = tek bölümde kalan sınıfların o bölümün saatlerinin ortalama ne kadarını
    kullandığı. Gerçek ikili eğitimde sabahçı şube sabahın hemen bütün saatlerini kullanır; az kartlı dosyada her
    sınıf "tek bölümde" görünür ama saatlerin küçük bir kısmını kullanır (önek olmadan bölmek için ikisi de gerekir)."""
    dolu = [s for s in sinif_saatleri.values() if s]
    if not dolu:
        return None, 0.0
    bolume = [0] * len(bolumler)
    hapis = 0
    kapsama = 0.0
    for saatler_ in dolu:
        icinde = next((i for i, b in enumerate(bolumler) if saatler_ <= b), None)
        if icinde is not None:
            hapis += 1
            bolume[icinde] += 1
            kapsama += len(saatler_) / len(bolumler[icinde])
    if not all(bolume):
        return 0.0, 0.0
    return hapis / len(dolu), kapsama / hapis


def asc_devre_gruplari(asc: dict, sinif_saatleri: dict[str, set[str]] | None = None) -> dict:
    """aSc ders saatlerini devrelere ayırır (0.21.0; K1, kural 25: ders numarası devre başınadır).

    1. Önek: bütün ders saati adları "S1…S8", "Ö1…Ö8" gibi harf öneki + sayıysa önek devre, sayı ders numarasıdır.
       Birden çok önekte, sınıfların en az %90'ı tek önekin saatlerini kullanmalıdır (yoksa önek yalnız etikettir:
       tek devreli okulda "Ö" öğleden önce olabilir).
    2. Önek yoksa: saatler başlangıca göre sıralanıp iki parçaya bölünür; sınıfların en az %90'ını tek parçada tutan
       bölme seçilir (eşitlikte arasında `breaks` aralığı olan, sonra boşluğu büyük olan). Ders numarası parçadaki sıradır.
    3. Hiçbiri tutmazsa tek grup (bugünkü davranış: numara period numarası; tek önekte önekin sayısı).
    period "0" gruplanmaz; başlangıç saati olmayan period da gruplamaya katılmaz ("saatsiz"; eşleme adımında elle
    seçilir) ama öbür saatlerin gruplanmasını engellemez (0.21.0 inceleme: tek saatsiz period bütün dosyayı gruplamasız
    bırakıyordu). Döndürür {"gruplar": [{"anahtar", "ad", "kaynak": onek|ara|tek, "bas", "bit", "dersler": [(no, bas,
    bit)]}] (başlangıca göre sıralı), "period": {period: (grup anahtarı, no)}, "saatsiz": [period]}.
    """
    periods = asc.get("periods") or {}
    sirali = []
    saatsiz: list[str] = []
    for pid, k in periods.items():
        if pid == "0":
            continue
        bas = program.saat_dogrula(k.get("starttime"))
        if not bas:
            saatsiz.append(pid)
            continue
        sirali.append((program.dk(bas), _sayi(pid, 0), pid, bas, program.saat_dogrula(k.get("endtime")) or ""))
    sirali.sort()
    if not sirali:
        return {"gruplar": [], "period": {}, "saatsiz": saatsiz}
    pidler = [s[2] for s in sirali]
    # sınıfların saatsiz period kullanımı bölmeyi bozmasın: yalnız gruplanan saatler sayılır
    sinif_saatleri = {c: set(s) & set(pidler) for c, s in (sinif_saatleri or {}).items()}
    bilgi_ = {s[2]: s for s in sirali}

    def grup(anahtar: str, ad: str, kaynak: str, uyeler: list[tuple[str, int]]) -> dict:
        dersler = sorted((no, bilgi_[p][3], bilgi_[p][4]) for p, no in uyeler)
        return {"anahtar": anahtar, "ad": ad, "kaynak": kaynak, "bas": bilgi_[uyeler[0][0]][3],
                "bit": max((bilgi_[p][4] for p, _ in uyeler), default=""), "dersler": dersler, "_uyeler": uyeler}  # fmt: skip

    def sonuc_(gruplar: list[dict]) -> dict:
        harita = {p: (g["anahtar"], no) for g in gruplar for p, no in g.pop("_uyeler")}
        return {"gruplar": gruplar, "period": harita, "saatsiz": saatsiz}

    # 1. önek
    onekler: dict[str, tuple[str, str, int]] = {}
    for pid in pidler:
        for ad in (periods[pid].get("name"), periods[pid].get("short")):
            m = _ONEK.fullmatch(str(ad or ""))
            if m:
                onekler[pid] = (metin.tr_kucuk(m.group(1)), m.group(1), int(m.group(2)))
                break
    onek_gecerli = len(onekler) == len(pidler) and len({(o[0], o[2]) for o in onekler.values()}) == len(pidler)
    if onek_gecerli:
        sira: list[str] = []
        for pid in pidler:  # her önek bitişik bir dilim olmalı (S1…S8 sonra Ö1…Ö8; iç içe geçmez)
            if not sira or sira[-1] != onekler[pid][0]:
                sira.append(onekler[pid][0])
        onek_gecerli = len(sira) == len(set(sira))
    if onek_gecerli:
        dilimler = [[p for p in pidler if onekler[p][0] == o] for o in sira]
        oran = _hapis_orani(sinif_saatleri, [set(d) for d in dilimler]) if len(dilimler) > 1 else None
        if len(dilimler) == 1 or oran is None or oran >= DEVRE_HAPSI_ORANI:
            gruplar = []
            for dilim in dilimler:
                gorunen = onekler[dilim[0]][1]
                nolar = [onekler[p][2] for p in dilim]
                gruplar.append(grup(f"onek:{onekler[dilim[0]][0]}", f"{gorunen}{min(nolar)}–{gorunen}{max(nolar)}",
                                    "onek" if len(dilimler) > 1 else "tek", [(p, onekler[p][2]) for p in dilim]))  # fmt: skip
            return sonuc_(gruplar)
    # 2. önek yok: sınıfları tek parçada tutan iki parçalı bölme
    if len(pidler) >= 2 and sinif_saatleri:
        en_iyi = None
        for i in range(len(pidler) - 1):
            oran, kapsama = _hapis(sinif_saatleri, [set(pidler[: i + 1]), set(pidler[i + 1 :])])
            if oran is None or oran < DEVRE_HAPSI_ORANI or kapsama < DEVRE_KAPSAMA:
                continue
            bitis = program.dk(sirali[i][4] or sirali[i][3])
            baslangic = sirali[i + 1][0]
            ara_var = any(
                program.saat_dogrula(a.get("starttime")) and program.saat_dogrula(a.get("endtime"))
                and program.dk(program.saat_dogrula(a["starttime"])) >= bitis - SAAT_TOLERANS_DK
                and program.dk(program.saat_dogrula(a["endtime"])) <= baslangic + SAAT_TOLERANS_DK
                for a in asc.get("breaks") or []
            )  # fmt: skip
            puan = (oran, ara_var, baslangic - bitis, -i)
            if en_iyi is None or puan > en_iyi[0]:
                en_iyi = (puan, i)
        if en_iyi is not None:
            i = en_iyi[1]
            gruplar = []
            for dilim in (pidler[: i + 1], pidler[i + 1 :]):
                adlar = [" ".join(str(periods[p].get("name") or p).split())[:30] for p in (dilim[0], dilim[-1])]
                gruplar.append(grup(f"bas:{bilgi_[dilim[0]][3]}", f"{adlar[0]}–{adlar[1]}", "ara",
                                    [(p, n) for n, p in enumerate(dilim, start=1)]))  # fmt: skip
            return sonuc_(gruplar)
    # 3. tek grup: tek önekte önekin sayısı, yoksa period numarası (bugünkü davranış), o da yoksa sıra
    tek_onek = onek_gecerli and len({onekler[p][0] for p in pidler}) == 1
    if tek_onek:
        uyeler = [(p, onekler[p][2]) for p in pidler]
    elif all(metin.rakam_mi(p) for p in pidler) and len({int(p) for p in pidler}) == len(pidler):
        uyeler = [(p, int(p)) for p in pidler]
    else:
        uyeler = [(p, n) for n, p in enumerate(pidler, start=1)]
    return sonuc_([grup("tek", "Bütün ders saatleri", "tek", uyeler)])


def asc_ara(asc: dict, secimler: dict) -> dict:
    """aSc kartlarını ara biçime çevirir (şartname §3.3). Döndürür {"ara", "bilgi", "hatalar", "hata_sayisi",
    "uyarilar", "kart_sayisi", "donemler", "secili_donem", "devre_gruplari", "gunler"}; `bilgi["saat"]` girdileri
    devre grubunu ("grup") ve devre içindeki numarayı ("no") taşır, `bilgi["devre_grup"]` grupların listesidir,
    `bilgi["sinif_dersligi"]` sınıf anahtarı → ana derslik anahtarıdır (yalnız tek ana dersliği olan sınıflar)."""
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
    # devre ayrımı için sınıf → kullandığı ders saatleri (yalnız kartın kendi saati; blok genişlemesi gerekmez)
    sinif_saatleri: dict[str, set[str]] = {}
    for _sira, kart, ders in kartlar:
        period = str(kart.get("period", "")).strip()
        if period in ("", "0"):
            continue
        sinif_idleri_ = set(_ids(ders.get("classids")))
        sinif_idleri_.update((groups.get(g) or {}).get("classid") for g in _ids(ders.get("groupids")))
        for cid in sinif_idleri_ - {None, ""}:
            sinif_saatleri.setdefault(cid, set()).add(period)
    devre = asc_devre_gruplari(asc, sinif_saatleri)
    kullanilan = set().union(*sinif_saatleri.values()) if sinif_saatleri else set()
    saatsiz = [p for p in devre["saatsiz"] if p in kullanilan]
    if saatsiz and len(devre["gruplar"]) > 1:  # tek gruplu dosyada görünüm değişmez (period numarasıyla eşlenir)
        adlar = ", ".join(" ".join(str((periods.get(p) or {}).get("name") or p).split())[:30] for p in saatsiz[:8])
        uyarilar.append(f"Başlangıç saati yazılmamış {len(saatsiz)} ders saati ({adlar}) devrelere ayrılmadı; "
                        "eşleme adımında zil çizelgesindeki karşılığını seçin.")  # fmt: skip
    bilgi: dict ={"derslik": {}, "sinif": {}, "saat": {}, "devre_grup": devre["gruplar"], "sinif_dersligi": {}}
    grup_adi = {g["anahtar"]: g["ad"] for g in devre["gruplar"]}
    ara: list[dict] = []
    gunler: set[int] = set()
    iki_haftalik = 0
    coklu_gun = 0
    tutarsiz_blok: set[str] = set()
    period_sirasi = sorted(periods, key=lambda p: (_sayi(p, 0), p))

    def sinif_anahtari(cid: str) -> str | None:
        c = classes.get(cid)
        if not c:
            return None
        ad = " ".join(str(c.get("name") or c.get("short") or "").split())[:60]
        # 0.21.0: önce kanonik şube ("9/I" ile "9/İ" AYRI kalır; katla ikisini birleştiriyordu), yoksa katlanmış ad.
        # Eski sürümün hatırladığı katlanmış şube anahtarları ("9/i") yeni anahtarla eşleşmez, yok sayılır.
        anahtar = metin.sube_duzelt(ad) or metin.katla(ad) or f"#{cid}"
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
                                              "adaylar": [x for x in (ad, kisa) if x], "kisa": kisa or ad})  # fmt: skip
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
            gunler.add(gun)
            for period in donemler_:
                kayit = periods.get(period) or {}
                bas = program.saat_dogrula(kayit.get("starttime"))
                anahtar = f"{period}|{bas or ''}"
                if anahtar not in bilgi["saat"]:
                    grup_, no = devre["period"].get(period, ("", None))
                    bilgi["saat"][anahtar] = {"period": period, "ad": " ".join(str(kayit.get("name") or period).split())[:30],
                                              "bas": bas or "", "bit": program.saat_dogrula(kayit.get("endtime")) or "",
                                              "grup": grup_, "grup_adi": grup_adi.get(grup_, ""), "no": no}  # fmt: skip
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
    # sınıfın ana dersliği (class@classroomids, tek derslik): onayda isteğe bağlı şube bilgisi güncellemesi için.
    # Yalnız programda geçen sınıf ve derslikler (eşleme ekranına yeni satır eklenmez).
    for cid, c in classes.items():
        odalar = _ids(c.get("classroomids"))
        if len(odalar) != 1 or odalar[0] not in rooms:
            continue
        ad = " ".join(str(c.get("name") or c.get("short") or "").split())[:60]
        s_anahtar = metin.sube_duzelt(ad) or metin.katla(ad) or f"#{cid}"
        r = rooms[odalar[0]]
        d_anahtar = metin.derslik_anahtari(" ".join(str(r.get("name") or r.get("short") or "").split())[:60]) or f"#{odalar[0]}"
        if s_anahtar in bilgi["sinif"] and d_anahtar in bilgi["derslik"]:
            bilgi["sinif_dersligi"][s_anahtar] = d_anahtar
    return {"ara": ara, "bilgi": bilgi, "hatalar": hatalar[:HATA_GOSTERIM], "hata_sayisi": len(hatalar),
            "uyarilar": uyarilar, "kart_sayisi": len(asc["cards"]), "donemler": donemler, "secili_donem": secili_donem,
            "devre_gruplari": devre["gruplar"], "gunler": sorted(gunler)}  # fmt: skip


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
            satirlar = eokul.xls_oku(bayt, asiri_ileti="Dosya beklenenden büyük; programı devre devre ya da ayrı dosyalarla yükleyin.")
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
    """Etkin tahtalar; ad, sonra numara (kimlik) sırasıyla: aynı adlı tahtalar da her seferinde aynı sırada gelir."""
    return [dict(t) for t in b.execute("SELECT id, ad, derslik, subeler FROM tahta WHERE durum != 'iptal' ORDER BY ad, id")]


def tahta_etiketi(t: dict) -> str:
    """Eşleme ekranında tahta seçeneği: "No 7 · ETAP · D-101" (aynı adlı tahtalar numarasıyla ayırt edilir; ağ adresi yok)."""
    return " · ".join([f"No {t['id']}", str(t["ad"]), *([str(t["derslik"])] if t.get("derslik") else [])])


def ayni_adli_tahta_var(tahtalar: list[dict]) -> bool:
    adlar = [metin.katla(t["ad"]) for t in tahtalar]
    return len(set(adlar)) < len(adlar)


def hatirlanan_oku(b, kaynak: str) -> dict[tuple[str, str], dict]:
    gecerli = {t["id"] for t in b.execute("SELECT id FROM tahta WHERE durum != 'iptal'")}
    sonuc = {}
    for s in b.execute("SELECT * FROM program_eslesme WHERE kaynak = ?", (kaynak,)):
        if s["tur"] in ("derslik", "sube") and s["tahta_id"] is not None and s["tahta_id"] not in gecerli:
            continue  # tahta kaldırıldı: satır yok sayılır
        sonuc[(s["tur"], s["anahtar"])] = {"tahta_id": s["tahta_id"], "deger": s["deger"]}
    return sonuc


def hatirlananlari_unut(b, kaynak: str) -> int:
    """Bir kaynağın (asc | eokul | tablo) hatırlanan bütün eşleşmelerini siler (0.21.0); silinen satır sayısı."""
    return b.execute("DELETE FROM program_eslesme WHERE kaynak = ?", (kaynak,)).rowcount


def hatirlanan_sayisi(b, kaynak: str) -> int:
    return b.execute("SELECT COUNT(*) FROM program_eslesme WHERE kaynak = ?", (kaynak,)).fetchone()[0]


def _saat_onerisi(bilgi_: dict, saatler: list[tuple], devre_secimi: str) -> str | None:
    """Tek gruplu aSc ders saati → 'devre|no' önerisi (şartname §3.5; ikili eğitimde önekli/bölünmüş dosya için
    `esle`'nin grup yolu kullanılır); bulunamazsa None, '0' ya da karşılıksızsa 'yok'. Önce başlangıç saati (±5 dk, tek
    devre), olmazsa numara: tek önekli dosyada önekin sayısı ("Ö3" → 3), yoksa period numarası."""
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
    if isinstance(bilgi_.get("no"), int):
        no = bilgi_["no"]
    elif period.isdigit():
        no = int(period)
    else:
        return None
    if len(devreler) == 1:
        devre = devreler[0]
    elif devre_secimi in devreler:
        devre = devre_secimi
    else:
        return None
    return f"{devre}|{no}" if any(s[1] == devre and s[3] == no for s in saatler) else "yok"


def zil_devreleri(saatler: list[tuple]) -> list[tuple[str, str]]:
    """Zil çizelgesindeki devreler [(kimlik, ad)], en erken başlangıca göre sıralı (e-Okul ile aynı kural)."""
    return eokul_program.mevcut_devreler(saatler)


def esle(veri: dict, saatler: list[tuple], tahtalar: list[dict], hatirlanan: dict, secimler: dict) -> dict:
    """Ara biçimi eşleme ile `tahta_ders` satırlarına çevirir (saf işlev).

    veri: {"kaynak": "asc"|"tablo"|"eokul", "ara", "bilgi"}; secimler: {"derslik": {anahtar: "id"|""}, "sinif": {anahtar:
    şube}, "saat": {anahtar: "devre|no"|"yok"}, "sube": {şube: "id"|""}, "devre": {grup anahtarı: devre|"yok"|""}}.
    Döndürür {"satirlar": {tahta_id: {(gun, devre, no): sube}}, "kapsam": {(tahta_id, devre)}, "hatalar", "hata_sayisi",
    "uyarilar", "eslesme": {tur: [satır]}, "dersliksiz": [..], "dersliksiz_sayi", "atlanan", "yerlesim_sayisi",
    "derslik_tahtalari": {derslik anahtarı: [tahta id]}, "sinif_subeleri": {sınıf anahtarı: şube},
    "saat_farki": {grup anahtarı: [(ad, bas)]} (zil çizelgesinden 5 dk'dan çok farklı ders saatleri)}.

    aSc'de ders saati → (devre, no) (0.21.0): dosya birden çok devre grubuna ayrıldıysa (`asc_devre_gruplari`) her grup
    bir zil devresine eşlenir (seçim > hatırlanan > devre sayıları eşitse başlangıç sırası > ilk dersin saati), ders
    numarası grup içindeki numaradır; saat ±5 dk tutmasa da numara doğru devreye düşer. Tek grupta bugünkü yol
    (`_saat_onerisi`; grup seçimi eski "bu dosya hangi devrenin" sorusudur).
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
    rakama: dict[str, set[int]] = {}
    for t in tahtalar:
        if t.get("derslik"):
            derslige.setdefault(metin.derslik_anahtari(t["derslik"]), []).append(t["id"])
        ada.setdefault(metin.derslik_anahtari(t["ad"]), []).append(t["id"])
        # rakam adayı (0.21.0): derslik alanından; addan YALNIZ ad baştan sona numaraysa ("101", "1-01"). "12/A" gibi
        # şube ya da "Tahta 3" gibi sıra numarası taşıyan ad aday olmaz ("Kimya Lab 12" 12/A tahtasına düşüyordu).
        for alan in (t.get("derslik"), t["ad"] if _RAKAMLI_AD.fullmatch(str(t["ad"] or "").strip()) else ""):
            if metin.rakam_anahtari(alan):
                rakama.setdefault(metin.rakam_anahtari(alan), set()).add(t["id"])
    subeye: dict[str, list[int]] = {}
    for t in tahtalar:
        for s in str(t.get("subeler") or "").split(","):
            if s.strip():
                subeye.setdefault(s.strip(), []).append(t["id"])

    def sec(tur: str, anahtar: str):
        return (secimler.get(tur) or {}).get(anahtar)

    eslesme: dict[str, list[dict]] = {"derslik": [], "sinif": [], "saat": [], "sube": [], "devre": []}
    # derslik → tahta(lar)
    # 0.21.0: ad/kısa ad tutmazsa ikinci aday rakam kümesidir ("DERSLİK-101", "D-101" ↔ tahtada "101"); yalnız dosyada
    # o rakamlı TEK derslik ve sistemde o rakamlı TEK tahta varsa (yoksa iki derslik aynı tahtaya düşebilirdi).
    derslik_rakami = {a: {metin.rakam_anahtari(x) for x in b_["adaylar"]} - {""} for a, b_ in bilgi["derslik"].items()}
    rakam_sayisi: dict[str, int] = {}
    for kumesi in derslik_rakami.values():
        for r in kumesi:
            rakam_sayisi[r] = rakam_sayisi.get(r, 0) + 1
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
            if deger is None and len(derslik_rakami[anahtar]) == 1:
                r = next(iter(derslik_rakami[anahtar]))
                if rakam_sayisi.get(r) == 1 and len(rakama.get(r, ())) == 1:
                    deger, durum = sorted(rakama[r]), "rakam"  # öneri: onayda hatırlanmaz, her seferinde yeniden hesaplanır
            if deger is None:
                durum = "eslesmedi"
            elif len(deger) > 1:
                uyarilar.append(
                    f"Aynı dersliğe bağlı {len(deger)} tahta: {', '.join(tahta_etiketi(aktif[i]) for i in deger)} "
                    "(ikisine de uygulanacak)."
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
    # aSc devre grubu → zil devresi (0.21.0)
    zil_dv = zil_devreleri(saatler)
    zil_kimlikleri = {d for d, _a in zil_dv}
    zil_saatleri: dict[tuple[str, int], set[int]] = {}
    for _g, devre, _a, no, bas, _b in saatler:
        zil_saatleri.setdefault((devre, no), set()).add(program.dk(bas))
    gecerli_saat = {f"{d}|{n}" for d, n in zil_saatleri} | {"yok"}
    gruplar = (bilgi.get("devre_grup") or []) if kaynak == "asc" else []
    cok_grup = len(gruplar) > 1
    grup_devresi: dict[str, str | None] = {}
    tek_grup_secimi = ""
    tek_grup_durumu = ""
    if len(gruplar) == 1:
        # "Bu dosya hangi devrenin programı?" seçimi: bu oturumun seçimi > hatırlanan (0.21.0 inceleme: hatırlanan
        # yazılıyor ama okunmuyordu; türeyen saat eşlemeleri de hatırlanmadığı için soru her aktarımda geri geliyordu)
        secim = sec("devre", gruplar[0]["anahtar"])
        h = hatirlanan.get(("devre", gruplar[0]["anahtar"]))
        if secim is not None:
            tek_grup_secimi = str(secim) if secim in zil_kimlikleri else ""
            tek_grup_durumu = "secildi" if tek_grup_secimi or secim == "" else ""  # "": açıkça "saatlerden eşle"
        elif h and h["deger"] in zil_kimlikleri:
            tek_grup_secimi, tek_grup_durumu = h["deger"], "hatirlanan"
    elif cok_grup:
        alinan: set[str] = set()
        for sira, g in enumerate(gruplar):
            secim, durum = sec("devre", g["anahtar"]), "otomatik"
            h = hatirlanan.get(("devre", g["anahtar"]))
            if secim is not None:
                deger = secim if secim in zil_kimlikleri or secim == "yok" else None
                durum = "secildi" if deger else "eslesmedi"
            elif h and (h["deger"] in zil_kimlikleri or h["deger"] == "yok"):
                deger, durum = h["deger"], "hatirlanan"
            elif len(gruplar) == len(zil_dv):
                deger = zil_dv[sira][0]  # devre sayıları eşit: başlangıç sırasıyla (sabah ↔ ilk grup)
            else:
                ilk_no, ilk_bas, _ = g["dersler"][0]
                adaylar = sorted({d for (d, n), dk in zil_saatleri.items() if n == ilk_no and d not in alinan
                                  and any(abs(x - program.dk(ilk_bas)) <= SAAT_TOLERANS_DK for x in dk)})  # fmt: skip
                deger = adaylar[0] if len(adaylar) == 1 else None
                if deger is None:
                    durum = "eslesmedi"
            if deger and deger != "yok":
                alinan.add(deger)
            grup_devresi[g["anahtar"]] = deger
            eslesme["devre"].append({"anahtar": g["anahtar"], "ad": g["ad"], "bas": g["bas"], "bit": g["bit"],
                                     "sayi": len(g["dersler"]), "durum": durum, "deger": deger or ""})  # fmt: skip
    # aSc ders saati → (devre, no)
    saat_sonuc: dict[str, str | None] = {}
    saat_farki: dict[str, list[tuple[str, str]]] = {}
    for anahtar, b_ in sorted(bilgi["saat"].items(), key=lambda x: (_sayi(x[1].get("period"), 99), x[0])):
        if kaynak != "asc":
            saat_sonuc[anahtar] = anahtar
            continue
        secim, durum = sec("saat", anahtar), "otomatik"
        h = hatirlanan.get(("saat", anahtar))
        if secim is not None:
            deger, durum = (secim if secim == "yok" or "|" in str(secim) else None), "secildi"
        elif h and h["deger"] in gecerli_saat:  # zil değiştiyse karşılığı kalmayan hatırlanan değer yok sayılır
            deger, durum = h["deger"], "hatirlanan"
        elif cok_grup and b_.get("grup") in grup_devresi:
            devre = grup_devresi[b_["grup"]]
            if devre is None:
                deger, durum = None, "eslesmedi"
            elif devre == "yok":
                deger = "yok"
            elif f"{devre}|{b_['no']}" in gecerli_saat:
                deger = f"{devre}|{b_['no']}"
            else:
                deger = "yok"
                uyarilar.append(f"aSc'deki “{b_['ad']}” ders saatinin {devre_adlari.get(devre, devre)} devresinde "
                                f"karşılığı yok ({b_['no']}. ders); yok sayıldı.")  # fmt: skip
        else:
            deger = _saat_onerisi(b_, saatler, tek_grup_secimi)
            if deger is None:
                durum = "eslesmedi"
            elif deger == "yok":
                uyarilar.append(f"aSc'deki “{b_['ad']}” ders saatinin zil çizelgesinde karşılığı yok; yok sayıldı.")
        saat_sonuc[anahtar] = deger
        if deger and deger != "yok" and b_.get("bas"):
            d_, _, n_ = deger.partition("|")
            zil_dk = zil_saatleri.get((d_, int(n_)) if n_.isdigit() else ("", 0), set())
            if zil_dk and not any(abs(x - program.dk(b_["bas"])) <= SAAT_TOLERANS_DK for x in zil_dk):
                saat_farki.setdefault(b_.get("grup") or "", []).append((b_["ad"], b_["bas"]))
        eslesme["saat"].append({"anahtar": anahtar, "ad": b_["ad"], "bas": b_.get("bas", ""), "bit": b_.get("bit", ""),
                                "grup_adi": b_.get("grup_adi", "") if cok_grup else "", "durum": durum,
                                "deger": deger or ""})  # fmt: skip
    if len(gruplar) == 1 and len(zil_dv) > 1 and (tek_grup_durumu or any(e["durum"] == "eslesmedi" for e in eslesme["saat"])):
        g = gruplar[0]
        eslesme["devre"].append({"anahtar": g["anahtar"], "ad": g["ad"], "bas": g["bas"], "bit": g["bit"],
                                 "sayi": len(g["dersler"]), "durum": tek_grup_durumu or "eslesmedi",
                                 "deger": tek_grup_secimi, "tek": True})  # fmt: skip
    for g in gruplar if cok_grup else []:  # tek gruplu dosyada (tek devreli okul) uyarı ve görünüm değişmez (kural 25)
        farkli = saat_farki.get(g["anahtar"])
        if farkli:
            ornek = ", ".join(f"{ad} {bas}" for ad, bas in farkli[:8])
            uyarilar.append(f"{g['ad']}: dosyadaki {len(farkli)} ders saati zil çizelgesinden 5 dakikadan çok farklı ({ornek}). "
                            "Dersler yine ders numarasına göre yazılır.")  # fmt: skip
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
            hatalar.append(f"{y['n']}. {'blok' if kaynak == 'eokul' else 'kart'}: {program.GUN_ADLARI[gun]} {no}. ders "
                           "zil çizelgesinde yok.")
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
                # Öncelik: bu oturumda seçilen > tahta.subeler'de TEK tahta (güncel gerçek) > hatırlanan > yok.
                # Hatırlanan, tahta.subeler'in önüne geçmez: şube başka dersliğe taşınınca eski tahtaya yazılmasın.
                secim = sec("sube", sube)
                adaylar = subeye.get(sube) or []
                if secim is not None:
                    sube_ihtiyaci[sube] = [int(secim)] if str(secim).isdigit() and int(secim) in aktif else []
                    durum = "secildi"
                elif len(adaylar) == 1:
                    sube_ihtiyaci[sube], durum = adaylar, "otomatik"
                elif ("sube", sube) in hatirlanan:
                    h = hatirlanan[("sube", sube)]
                    sube_ihtiyaci[sube] = [h["tahta_id"]] if h["tahta_id"] in aktif else []
                    durum = "hatirlanan"
                else:
                    sube_ihtiyaci[sube], durum = None, "eslesmedi"
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
        "derslik_tahtalari": {a: list(d) for a, d in derslik_sonuc.items() if d},
        "sinif_subeleri": {a: s for a, s in sinif_sonuc.items() if s},
        "saat_farki": saat_farki,
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
    sonuc.sort(key=lambda t: (metin.tr_sirala_anahtari(t["ad"]), t["id"]))
    dokunulmayan.sort(key=lambda t: (metin.tr_sirala_anahtari(t["ad"]), t["id"]))
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


def sube_guncellemesi(bilgi: dict, cozum: dict, tahtalar: list[dict]) -> list[dict]:
    """aSc onayındaki isteğe bağlı "Tahtaların şube bilgisini programdan güncelle" (0.21.0; kutu işaretsiz gelir).

    Eşlenen her tahtanın şubeleri = ana dersliği (class@classroomids, tek derslik) o tahtaya eşlenen dersliklerden biri
    olan aSc sınıflarının eşlemedeki şubeleri (`hedef.subeler_coz` biçimi: "9/A,10/B", düzey sırasıyla). Tahtanın derslik
    alanı boşsa ve ona tek bir aSc dersliği eşlendiyse dersliğin kısa adı ("D-101") yazılır; dolu derslik değişmez.
    Hiç sınıfı düşmeyen eşlenmiş tahtanın (ör. atölye) şubeleri silinmez; YALNIZ bu aktarımda yeni ana tahtası BAŞKA bir
    eşlenmiş tahta olarak belirlenen şubeler ondan çıkarılır (yoksa aynı şube iki tahtada kalır: başkan anahtarının oda
    kısıtı, e-Okul/tablo otomatik eşlemesi ve şube hedefli duyurular bozulur). Yeni tahtası belirlenmemiş (elle girilmiş)
    şubeye ve eşlenmemiş tahtaya dokunulmaz. Yalnız DEĞİŞECEK tahtalar döner:
    [{"id", "ad", "eski_subeler", "subeler", "eski_derslik", "derslik"}] (ad, sonra numara sırasıyla)."""
    tahta_derslikleri: dict[int, list[str]] = {}
    for d_anahtar, idler in (cozum.get("derslik_tahtalari") or {}).items():
        for tid in idler:
            tahta_derslikleri.setdefault(tid, []).append(d_anahtar)
    dersligin_subeleri: dict[str, set[str]] = {}
    for s_anahtar, d_anahtar in (bilgi.get("sinif_dersligi") or {}).items():
        sube = (cozum.get("sinif_subeleri") or {}).get(s_anahtar)
        if sube:
            dersligin_subeleri.setdefault(d_anahtar, set()).add(sube)
    # Önce eşlenen tahtaların yeni şubeleri ve şube → yeni ana tahta(lar) haritası (bir derslik birden çok tahtaya
    # eşlenebilir; şube o tahtaların hepsinde kalır).
    yeni_kume: dict[int, set[str]] = {}
    sube_tahtalari: dict[str, set[int]] = {}
    for t in tahtalar:
        derslikler = tahta_derslikleri.get(t["id"])
        if not derslikler:
            continue
        yeni_kume[t["id"]] = set().union(*(dersligin_subeleri.get(d, set()) for d in derslikler))
        for sube in yeni_kume[t["id"]]:
            sube_tahtalari.setdefault(sube, set()).add(t["id"])
    sonuc = []
    for t in sorted(tahtalar, key=lambda t: (metin.tr_sirala_anahtari(t["ad"]), t["id"])):
        if t["id"] not in yeni_kume:
            continue
        derslikler = tahta_derslikleri[t["id"]]
        yeni = yeni_kume[t["id"]]
        eski_subeler = str(t.get("subeler") or "")
        if yeni:
            subeler = ",".join(sorted(yeni, key=sube_sira_anahtari))
        else:
            try:
                eski_liste = hedef.subeler_coz(eski_subeler)
            except ValueError:
                eski_liste = hedef.kume(eski_subeler)
            kalan = [s for s in eski_liste if not (sube_tahtalari.get(s, set()) - {t["id"]})]
            subeler = ",".join(kalan) if len(kalan) < len(eski_liste) else eski_subeler
        eski_derslik = str(t.get("derslik") or "")
        derslik = eski_derslik
        if not eski_derslik and len(derslikler) == 1:
            derslik = str((bilgi["derslik"].get(derslikler[0]) or {}).get("kisa") or "")[:60]
        if subeler != eski_subeler or derslik != eski_derslik:
            sonuc.append({"id": t["id"], "ad": t["ad"], "eski_subeler": eski_subeler, "subeler": subeler,
                          "eski_derslik": eski_derslik, "derslik": derslik})  # fmt: skip
    return sonuc


# ==== 4. Uygulama, sürümler, geri yükleme =====================================================================
def _anlik(b) -> list[list]:
    return [[s["tahta_id"], s["gun"], s["devre"], s["ders_no"], s["sube"]]
            for s in b.execute("SELECT * FROM tahta_ders ORDER BY tahta_id, gun, devre, ders_no")]  # fmt: skip


def surum_yaz(b, kullanici: str, neden: str, bicim: str, tahta_bilgisi: list[dict] | None = None) -> int:
    """Mevcut `tahta_ders`'in tamamını `program_surum`'e yazar; en yeni SURUM_SAKLA sürüm kalır. `tahta_bilgisi`
    (0.21.0): bu işlemin değiştireceği tahta şube/derslik alanları [{"id", "subeler", "derslik", "yeni_subeler",
    "yeni_derslik"}]; geri yüklemede eski değerler döner (`geri_yukle`)."""
    veri = _anlik(b)
    kimlik = b.execute(
        "INSERT INTO program_surum (zaman, kullanici, neden, bicim, satir_sayisi, tahta_sayisi, veri_json, tahta_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (vt.simdi(), kullanici, neden, bicim, len(veri), len({s[0] for s in veri}), json.dumps(veri),
         json.dumps(tahta_bilgisi, ensure_ascii=False) if tahta_bilgisi else ""),
    ).lastrowid  # fmt: skip
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
            if tur == "sube" and e["durum"] == "otomatik":
                continue  # tahta.subeler'den gelen eşleme hatırlanmaz; kaynak her seferinde tahta.subeler'dir
            if tur in ("saat", "devre") and e["durum"] == "otomatik":
                continue  # 0.21.0: zilden/önekten türeyen eşleme hatırlanmaz (zil değişince bayat kalmasın)
            if e["durum"] == "rakam":
                continue  # 0.21.0: yalnız numarası tutan derslik önerisi hatırlanmaz (yanlışsa kalıcı olmasın)
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


def uygula(b, cozum: dict, kullanici: str, bicim: str, kaynak: str, temizle: list[int] | None = None,
           subeler: list[dict] | None = None) -> dict:  # fmt: skip
    """Onay (tek işlem; çağıran `vt.islem()` içinde): önce bütün `tahta_ders` sürüm olarak saklanır, sonra yalnız
    kapsamdaki (tahta, devre) çiftleri silinip yeniden yazılır; `temizle` verilen (dosyada geçmeyen) tahtaların aynı
    devre satırları da silinir; eşlemeler hatırlanır. `subeler` (0.21.0, `sube_guncellemesi`; yalnız kutu
    işaretliyse) tahtaların şube ve boş derslik alanını yazar; eski değerler sürümle saklanır ve "Önceki programlar"dan
    geri yüklenince döner. Döndürür {"surum_id","tahta","satir","temizlenen","sube_tahta"}."""
    gecerli = {t["id"] for t in b.execute("SELECT id FROM tahta WHERE durum != 'iptal'")}
    tahta_yazilacak = []
    for g in subeler or []:
        if g["id"] not in gecerli:
            continue
        try:
            yeni_subeler = ",".join(hedef.subeler_coz(g["subeler"]))
        except ValueError:
            continue
        eski = b.execute("SELECT subeler, derslik FROM tahta WHERE id = ?", (g["id"],)).fetchone()
        tahta_yazilacak.append({"id": g["id"], "subeler": eski["subeler"] or "", "derslik": eski["derslik"] or "",
                                "yeni_subeler": yeni_subeler, "yeni_derslik": str(g["derslik"])[:60]})  # fmt: skip
    surum_id = surum_yaz(b, kullanici, "aktarim", bicim, tahta_yazilacak)
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
    for g in tahta_yazilacak:
        b.execute("UPDATE tahta SET subeler = ?, derslik = ? WHERE id = ?", (g["yeni_subeler"], g["yeni_derslik"], g["id"]))
    return {"surum_id": surum_id, "tahta": len(tahtalar), "satir": satir, "temizlenen": temizlenen,
            "sube_tahta": len(tahta_yazilacak)}  # fmt: skip


def _tahta_bilgisi_oku(ham) -> list[dict]:
    """`program_surum.tahta_json` → doğrulanmış liste (bozuk ya da eski sürümde boş)."""
    try:
        liste = json.loads(ham) if ham else []
    except ValueError:
        return []
    alanlar = ("subeler", "derslik", "yeni_subeler", "yeni_derslik")
    return [g for g in liste if isinstance(g, dict) and isinstance(g.get("id"), int)
            and all(isinstance(g.get(a), str) for a in alanlar)] if isinstance(liste, list) else []  # fmt: skip


def geri_yukle(b, surum_id: int, kullanici: str) -> dict | None:
    """Önce mevcut durum yeni sürüm olarak saklanır (geri almanın da geri alınabilmesi için), sonra `tahta_ders`
    tümüyle silinip anlık görüntü yazılır; kaldırılmış (iptal) tahtaların satırları atlanır, artık olmayan ders
    saatleri yazılır (yetim olarak görünür). Sürüm yoksa None.

    0.21.0: sürüm, onaydaki "şube bilgisini güncelle" adımının eski değerlerini taşıyorsa tahtanın şube ve derslik
    alanı da eski hâline döner; yalnız alan o onaydan beri DEĞİŞMEDİYSE (sonradan elle girilen bilgi ezilmez).
    Dönüşte "tahta_bilgisi" (geri dönen) ve "tahta_bilgisi_atlanan" (sonradan değiştiği için dokunulmayan) sayıları."""
    satir = b.execute("SELECT * FROM program_surum WHERE id = ?", (surum_id,)).fetchone()
    if not satir:
        return None
    try:
        veri = json.loads(satir["veri_json"])
    except ValueError:
        return None
    zaman, kaynak_id = satir["zaman"], satir["id"]
    gecerli = {t["id"] for t in b.execute("SELECT id FROM tahta WHERE durum != 'iptal'")}
    geri_donecek, atlanan = [], 0
    for g in _tahta_bilgisi_oku(satir["tahta_json"]):
        simdi = b.execute("SELECT subeler, derslik FROM tahta WHERE id = ?", (g["id"],)).fetchone()
        if g["id"] not in gecerli or simdi is None:
            continue
        if ((simdi["subeler"] or ""), (simdi["derslik"] or "")) != (g["yeni_subeler"], g["yeni_derslik"]):
            atlanan += 1
            continue
        # geri yüklemenin de geri alınabilmesi için ters yön saklanır
        geri_donecek.append({"id": g["id"], "subeler": g["yeni_subeler"], "derslik": g["yeni_derslik"],
                             "yeni_subeler": g["subeler"], "yeni_derslik": g["derslik"]})  # fmt: skip
    surum_yaz(b, kullanici, "geri_yukleme", "", geri_donecek)
    for g in geri_donecek:
        b.execute("UPDATE tahta SET subeler = ?, derslik = ? WHERE id = ?", (g["yeni_subeler"], g["yeni_derslik"], g["id"]))
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
    return {"satir": yazilan, "zaman": zaman, "id": kaynak_id, "tahta_bilgisi": len(geri_donecek),
            "tahta_bilgisi_atlanan": atlanan}  # fmt: skip


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


# ==== 6. aSc'den zil çizelgesi önerisi (0.21.0) =====================================================================
def asc_zil_hazirla(okunan: dict, saatler: list[tuple], cozum: dict) -> dict:
    """aSc ders saatlerinden zil çizelgesi önerisi (e-Okul `zil_onerisi`/`zil_yaz` kalıbı; onaysız yazılmaz).

    Zil yoksa, dosyanın ders saatleri zile eşlenemiyorsa ya da (ikili eğitimde) zilden 5 dk'dan çok farklıysa önerilir: devre
    grupları (en çok iki) → Sabah + Öğleden sonra (tek grupta Normal); zilde aynı sayıda devre varsa onların kimlik ve
    adları kullanılır (mevcut derslik programı yetim kalmasın). aSc'de tek saat dizisi vardır: bütün günler aynı saatle.
    {"zil_onerisi": eokul_program.zil_onerisi biçimi | None, "zil_gerekli", "zil_onerilemez", "zil_yalniz_fark"}."""
    gruplar = okunan.get("devre_gruplari") or []
    eslesmedi = any(e["durum"] == "eslesmedi" for liste in (cozum["eslesme"]["saat"], cozum["eslesme"]["devre"]) for e in liste)
    fark_var = len(gruplar) > 1 and any(cozum.get("saat_farki", {}).values())  # tek grupta yalnız zilsizlik/eşleşmeme
    zil_gerekli = not saatler or eslesmedi or fark_var
    oneri = None
    onerilemez = ""
    if zil_gerekli:
        if not gruplar:  # hiçbir ders saatinin başlangıcı yok: öneri çıkamaz, kullanıcı çıkmazda kalmasın (0.21.0 inceleme)
            onerilemez = ("Dosyadaki ders saatlerinin başlangıç saati yazılmamış; zil çizelgesi bu dosyadan oluşturulamıyor. "
                          "Zil saatlerini zil düzenleyicisinde (Program › Zil saatleri) girin.")  # fmt: skip
        elif len(gruplar) > 2:
            onerilemez = "Dosyada ikiden çok devre var; zil saatlerini zil düzenleyicisinde (Program › Zil saatleri) girin."
        elif any(not bit for g in gruplar for _n, _b, bit in g["dersler"]):
            onerilemez = "Dosyadaki ders saatlerinin bitişi yazılmamış; zil saatlerini zil düzenleyicisinde girin."
        else:
            oneri = eokul_program.zil_onerisi(gruplar, okunan.get("gunler") or [0, 1, 2, 3, 4], zil_devreleri(saatler))
            if oneri:
                oneri["hatalar"] = [h.replace("Rapordaki", "Dosyadaki") for h in oneri["hatalar"]]
                if oneri["hatalar"]:
                    onerilemez = "Bu dosyadaki saatlerden zil çizelgesi oluşturulamıyor; zil saatlerini zil düzenleyicisinde girin."
    return {"zil_onerisi": oneri, "zil_gerekli": zil_gerekli, "zil_onerilemez": onerilemez,
            "zil_yalniz_fark": bool(saatler) and fark_var and not eslesmedi}  # fmt: skip


def asc_zil_yaz(b, oneri: dict, kullanici: str) -> tuple[int, str]:
    """Öneriyi yeni çizelge olarak yazar (kaynak 'asc'), dosyadaki günlere haftalık düzende atar ve `ders_saati`'ni
    yeniden türetir (`cizelge.haftalik_yaz`; elle INSERT yok). Diğer günler ve mevcut çizelgeler değişmez. (id, ad)."""
    ad = cizelge.benzersiz_ad(b, "aSc · " + oneri["gun_metni"])
    kimlik = cizelge.cizelge_ekle(b, ad, [tuple(d) for d in oneri["dersler"]], "asc", kullanici)
    b.executemany("INSERT OR REPLACE INTO zil_haftalik (gun, cizelge_id) VALUES (?, ?)", [(g, kimlik) for g in oneri["gunler"]])
    cizelge.haftalik_yaz(b)
    kaynak = vt.ayar_al(b, "zil_kaynagi")
    if isinstance(kaynak, dict):
        if kaynak.get("tur") == "okulzili":
            vt.ayar_yaz(b, "zil_kaynagi", {**kaynak, "duzenlendi": True})
    else:
        vt.ayar_yaz(b, "zil_kaynagi", {"tur": "elle", "dosya_ozet": "", "dosya_yolu": "", "dosya_zamani": None,
                                       "yukleme": vt.simdi(), "yukleyen": kullanici, "duzenlendi": False})  # fmt: skip
    return kimlik, ad


# ==== 7. Önizleme kaydı ==========================================================================================
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
        "secimler": {"derslik": {}, "sinif": {}, "saat": {}, "sube": {}, "devre": {}, "donem": ""},
    }
    if len(json.dumps(veri, ensure_ascii=False).encode("utf-8")) > ONIZLEME_EN_COK_BAYT:
        raise ValueError("Program çok büyük; devre devre yükleyin.")
    return veri


def hatirlanan_kaynagi(veri: dict) -> str:
    """`program_eslesme.kaynak`: asc | eokul | tablo (CSV/XLSX/yapay zekâ ortak)."""
    return veri["kaynak"] if veri["kaynak"] in ("asc", "eokul") else "tablo"


def coz(b, veri: dict) -> dict:
    """Önizleme verisinden güncel çözüm + fark + gösterim alanları (her istekte yeniden hesaplanır)."""
    saatler = program.ders_saatleri_oku(b)
    secimler = veri.get("secimler") or {}
    hatirlanan = hatirlanan_oku(b, hatirlanan_kaynagi(veri))
    eokul_ = None
    okunan = None
    if veri["kaynak"] == "eokul":
        eokul_ = eokul_program.hazirla(veri["eokul"], saatler, secimler, hatirlanan, eokul_program.sistem_subeleri(b))
        girdi = eokul_["girdi"]
        kaynak_hatalari, kaynak_hata_sayisi = veri["kaynak_hatalari"], veri["kaynak_hata_sayisi"]
        kaynak_uyarilari = veri["kaynak_uyarilari"] + eokul_["uyarilar"]
        donemler, secili_donem = [], None
    elif veri["kaynak"] == "asc":
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
    tahtalar = tahta_listesi(b)
    cozum = esle(girdi, saatler, tahtalar, hatirlanan, secimler)
    if eokul_ is not None:  # onayda hatırlanacak blok → şube eşlemesi (eslesmeleri_yaz) ve blok sayısı
        cozum["eslesme"]["blok"] = eokul_["bloklar"]
        cozum["eslesme"]["blok_sayisi"] = [{"anahtar": "-", "deger": str(len(eokul_["bloklar"])), "durum": "otomatik"}]
    asc_zil = asc_zil_hazirla(okunan, saatler, cozum) if okunan is not None else None
    f = fark(b, cozum, saatler)
    hata_sayisi = kaynak_hata_sayisi + cozum["hata_sayisi"]
    toplam = max(1, cozum["yerlesim_sayisi"] + kaynak_hata_sayisi)
    devreler = zil_devreleri(saatler)
    ilk_saat: dict[tuple[str, int], tuple[str, str]] = {}
    for _g, devre, adi, no, bas, _b in sorted(saatler):
        ilk_saat.setdefault((devre, no), (adi, bas))
    saat_secenekleri = [{"deger": f"{d}|{n}", "ad": f"{adi} · {n}. ders ({bas})"}
                        for (d, n), (adi, bas) in sorted(ilk_saat.items(), key=lambda x: (x[1][1], x[0]))]  # fmt: skip
    program_degisir = f["toplam"]["tahta"] > 0 or bool(f["dokunulmayan_programli"] and cozum["kapsam"])
    subeler = sube_guncellemesi(okunan["bilgi"], cozum, tahtalar) if okunan is not None else []
    return {
        "cozum": cozum,
        "fark": f,
        "ozet_metni": ozet_metni(f),
        "hatalar": (kaynak_hatalari + cozum["hatalar"])[:HATA_GOSTERIM],
        "hata_sayisi": hata_sayisi,
        "uyarilar": kaynak_uyarilari + cozum["uyarilar"],
        "cok_hata": hata_sayisi > HATA_ORANI * toplam,
        # 0.21.0: program aynıysa da yalnız şube bilgisi güncellenebilsin (onayda kutu işaretli değilse reddedilir)
        "onaylanabilir": (program_degisir or bool(subeler)) and not (eokul_ and eokul_["ciftler"]),
        "program_degisir": program_degisir,
        "donemler": donemler,
        "secili_donem": secili_donem,
        "devre_secenekleri": devreler,
        "saat_secenekleri": saat_secenekleri,
        "tahta_secenekleri": [(t["id"], tahta_etiketi(t)) for t in tahtalar],
        "ayni_adli_tahta": ayni_adli_tahta_var(tahtalar),
        "sube_sayilari": sube_sayilari(cozum) if veri["bicim"] in ("yz", "yz_dosya", "eokul", "asc") else [],
        "esleme_gerekli": veri["kaynak"] in ("asc", "eokul") or cozum["eslesmedi_sayisi"] > 0,
        "eokul": eokul_,
        "asc_zil": asc_zil,
        "sube_guncellemesi": subeler,
    }
