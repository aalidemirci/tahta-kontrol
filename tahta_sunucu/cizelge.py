"""Zil düzenleyici: adlandırılmış zil çizelgeleri, haftalık düzen ve tarihe özel çizelgeler (0.10.0).

Okul Zili'nin "gün programı + oturum + tarih kuralı" üçlüsünün Tahta Kontrol karşılığı. Zil çalınmaz;
yalnız ders aralıkları tutulur. `ders_saati` türetilmiş tablodur: haftalık düzen her değiştiğinde atanan
çizelgelerden yeniden yazılır (`haftalik_yaz`), böylece derslik programı, kilit, yoklama ve boş ders
uyarısı hiç değişmeden çalışır.

Kavramlar (şartname §3.1): çizelge = bir günün ders akışı (bir ya da iki devre, devre içinde sıralı
dersler); ders numarası elle girilmez, devre içinde başlangıç saatine göre 1'den kendiliğinden verilir;
teneffüs ve öğle arası ayrı satır değildir (iki dersin arasındaki boşluktur, ≤ 20 dk teneffüs).

Taslak biçimi (form ↔ sunucu): {"ad": str, "devreler": [{"devre": "sabah", "devre_adi": "Sabah",
"satirlar": [{"r": "r0", "bas": "07:40", "bit": "08:20", "sil": False}, ...]}, ...]}. Satır sırası
önemsizdir; kayıtta her devre başlangıca göre sıralanıp numaralanır.

Öğretmen, ders adı ve kişi verisi hiçbir yerde tutulmaz.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from . import guvenlik, metin, program, vt, zamanlama

DEVRELER = program.VARSAYILAN_DEVRE_ADI  # {"normal": "Normal", "sabah": "Sabah", "ogle": "Öğleden sonra"}
DEVRE_SIRA = {"sabah": 0, "normal": 1, "ogle": 2}
AD_EN_UZUN = 40
TARIHLI_AD_EN_UZUN = 60
TARIHLI_EN_UZUN_GUN = 366
EN_COK_DERS = 20
DERS_DK = (10, 180)
BOS_SATIR = 3  # JS'siz düzenleme için her devre tablosunun sonundaki boş satır sayısı
SATIR_EN_COK = 200  # formdan okunan satır sınırı (kötüye kullanım koruması)
CSV_EN_COK_BAYT = 64 * 1024
CSV_EN_COK_SATIR = 100
OGLE_GECIS_DK = 20  # Okul Zili suggest_next_session_start: sabah bitişi + 20 dk, 5'e yukarı yuvarla
TENEFFUS_ESIGI_DK = program.TENEFFUS_EN_UZUN_SN // 60
KAYNAK_ADI = {"elle": "Elle", "okulzili": "Okul Zili", "tasima": "Önceki sürümden"}
TC_ILETISI = "Adda T.C. kimlik numarasına benzeyen bir sayı var; kişi bilgisi yazmayın."

# Hızlı oluştur varsayılanları (şartname §5.3): ilk, sayı, ders dk, teneffüs dk, uzun ara sonrası, uzun ara dk.
HIZLI_VARSAYILAN = {
    "normal": {"ilk": "08:20", "sayi": 8, "ders_dk": 40, "teneffus_dk": 10, "uzun_sonra": 4, "uzun_dk": 45},
    "sabah": {"ilk": "07:40", "sayi": 6, "ders_dk": 40, "teneffus_dk": 10, "uzun_sonra": 0, "uzun_dk": 30},
    "ogle": {"ilk": "", "sayi": 6, "ders_dk": 40, "teneffus_dk": 10, "uzun_sonra": 0, "uzun_dk": 30},
}
HIZLI_ALANLAR = ("ilk", "sayi", "ders_dk", "teneffus_dk", "uzun_sonra", "uzun_dk")
_KIMLIK = re.compile(r"r\d{1,4}")
_DEVRE_KIMLIGI = re.compile(r"[a-z0-9_]{1,30}")


def bugun_tarihi() -> date:
    return datetime.fromtimestamp(vt.simdi(), program.ISTANBUL).date()


# ---- küçük yardımcılar ---------------------------------------------------------------------------
def _form_al(form, ad: str) -> str:
    deger = form.get(ad) if form is not None else None
    if isinstance(deger, (list, tuple)):
        deger = deger[-1] if deger else None
    return "" if deger is None else str(deger)


def _form_liste(form, ad: str) -> list[str]:
    if form is None:
        return []
    if hasattr(form, "getlist"):
        return [str(v) for v in form.getlist(ad)]
    deger = form.get(ad)
    if deger is None:
        return []
    return [str(v) for v in deger] if isinstance(deger, (list, tuple)) else [str(deger)]


def devre_adi(devre: str, adlar: dict | None = None) -> str:
    return (adlar or {}).get(devre) or DEVRELER.get(devre) or devre


def ad_temizle(ad) -> str:
    return " ".join(str(ad or "").split())


def ad_anahtari(ad: str) -> str:
    """Ad benzersizliği için: Türkçe küçük harf + boşluk sadeleştirme ("Cuma" == "CUMA")."""
    return metin.tr_kucuk(ad_temizle(ad))


def devre_sirala(devreler: list[dict]) -> list[dict]:
    """Devreleri ilk ders saatine (boşsa sabit sıraya: Sabah, Normal, Öğleden sonra) göre dizer."""

    def anahtar(d):
        saatler = [program.dk(s["bas"]) for s in d["satirlar"] if program.saat_dogrula(s.get("bas")) == s.get("bas")]
        return (min(saatler) if saatler else 24 * 60, DEVRE_SIRA.get(d["devre"], 1))

    return sorted(devreler, key=anahtar)


def kimlikleri_yenile(taslak: dict) -> dict:
    """Satır kimliklerini r0, r1… diye baştan verir (form alan adları benzersiz kalsın)."""
    sira = 0
    for d in taslak["devreler"]:
        for s in d["satirlar"]:
            s["r"] = f"r{sira}"
            sira += 1
    return taslak


def bos_satirlar_ekle(taslak: dict, adet: int = BOS_SATIR) -> dict:
    """JS'siz araya/sona ders ekleme için her devre tablosunun sonuna boş satırlar (görünüm içindir)."""
    sira = sum(len(d["satirlar"]) for d in taslak["devreler"])
    for d in taslak["devreler"]:
        for _ in range(adet):
            d["satirlar"].append({"r": f"r{sira}", "bas": "", "bit": "", "sil": False, "bos": True})
            sira += 1
    return taslak


# ---- taslak ↔ form / veritabanı ---------------------------------------------------------------
def taslak_formdan(form, adlar: dict | None = None) -> dict:
    """Çizelge formundan taslak. Alanlar: ad; devre (gizli, tablo başına); satir (sıra kimliği r0, r1…);
    {r}_devre, {r}_bas, {r}_bit, {r}_sil. Tanınmayan kimlik ve devre yok sayılır.

    adlar: çizelgedeki özel (taşınmış) devrelerin görünen adları {devre: ad}.
    """
    devreler: dict[str, dict] = {}
    for devre in _form_liste(form, "devre"):
        if _DEVRE_KIMLIGI.fullmatch(devre) and devre not in devreler:
            devreler[devre] = {"devre": devre, "devre_adi": devre_adi(devre, adlar), "satirlar": []}
    gorulen: set[str] = set()
    for r in _form_liste(form, "satir")[:SATIR_EN_COK]:
        if not _KIMLIK.fullmatch(r) or r in gorulen:
            continue
        gorulen.add(r)
        devre = _form_al(form, f"{r}_devre")
        if not _DEVRE_KIMLIGI.fullmatch(devre):
            continue
        d = devreler.setdefault(devre, {"devre": devre, "devre_adi": devre_adi(devre, adlar), "satirlar": []})
        bas, bit = _form_al(form, f"{r}_bas").strip()[:8], _form_al(form, f"{r}_bit").strip()[:8]
        if not bas and not bit:
            continue  # boş satır (JS'siz ekleme için çizilen): taslağa girmez, yeniden çizimde birikmez
        d["satirlar"].append({"r": r, "bas": bas, "bit": bit, "sil": _form_al(form, f"{r}_sil") == "1"})
    return {"ad": ad_temizle(_form_al(form, "ad"))[:200], "devreler": list(devreler.values())}


def dersler_taslaga(ad: str, dersler) -> dict:
    """[(devre, devre_adi, no, bas, bit)] → taslak (kimlikler r0, r1…)."""
    devreler: dict[str, dict] = {}
    for devre, adi, _no, bas, bit in sorted(dersler, key=lambda d: (d[0], d[3])):
        devreler.setdefault(devre, {"devre": devre, "devre_adi": adi, "satirlar": []})["satirlar"].append(
            {"r": "", "bas": bas, "bit": bit, "sil": False}
        )
    return kimlikleri_yenile({"ad": ad, "devreler": devre_sirala(list(devreler.values()))})


def cizelge_dersleri(b, cizelge_id: int) -> list[tuple]:
    return [
        (s["devre"], s["devre_adi"], s["ders_no"], s["baslangic"], s["bitis"])
        for s in b.execute(
            "SELECT * FROM zil_cizelge_ders WHERE cizelge_id = ? ORDER BY devre, ders_no", (cizelge_id,)
        )
    ]


def taslak_dbden(b, cizelge_id: int) -> dict | None:
    satir = b.execute("SELECT * FROM zil_cizelgesi WHERE id = ?", (cizelge_id,)).fetchone()
    if not satir:
        return None
    return dersler_taslaga(satir["ad"], cizelge_dersleri(b, cizelge_id))


# ---- numaralama ve doğrulama ------------------------------------------------------------------
def _gecerli_satirlar(d: dict) -> list[tuple[str, str, str]]:
    """Devrenin silinmemiş, iki saati geçerli ve bitişi başlangıçtan sonra satırları: [(bas, bit, r)]."""
    sonuc = []
    for s in d["satirlar"]:
        if s.get("sil"):
            continue
        bas, bit = program.saat_dogrula(s.get("bas")), program.saat_dogrula(s.get("bit"))
        if bas and bit and program.dk(bit) > program.dk(bas):
            sonuc.append((bas, bit, s.get("r", "")))
    return sorted(sonuc)


def numarala(taslak: dict) -> list[tuple]:
    """Taslağın geçerli dersleri: [(devre, devre_adi, no, bas, bit)]; no devre içinde başlangıca göre 1'den."""
    sonuc = []
    for d in taslak["devreler"]:
        for no, (bas, bit, _r) in enumerate(_gecerli_satirlar(d), start=1):
            sonuc.append((d["devre"], d["devre_adi"], no, bas, bit))
    return sonuc


def _hata(metin_: str, alan: str | None = None) -> dict:
    return {"metin": metin_, "alan": alan}


def dogrula(taslak: dict, ad: str | None = None, mevcut_adlar=()) -> tuple[list[dict], list[str]]:
    """Şartname §5.6. Hatalar kaydı engeller ({"metin","alan"}; alan = ilgili form alanı kimliği, ör. r3_bas);
    uyarılar kaydedilir. `ad` None ise ad denetlenmez (CSV/hızlı oluşturda yalnız satırlar)."""
    hatalar: list[dict] = []
    uyarilar: list[str] = []
    if ad is not None:
        ad = ad_temizle(ad)
        if not 1 <= len(ad) <= AD_EN_UZUN:
            hatalar.append(_hata(f"Çizelge adı 1–{AD_EN_UZUN} karakter olmalı.", "cizelge-ad"))
        elif ad_anahtari(ad) in {ad_anahtari(a) for a in mevcut_adlar}:
            hatalar.append(_hata("Bu adda bir çizelge zaten var.", "cizelge-ad"))
        elif guvenlik.tc_kimlik_var(ad):
            hatalar.append(_hata(TC_ILETISI, "cizelge-ad"))
    toplam = 0
    araliklar: list[tuple[str, int, int]] = []
    for d in taslak["devreler"]:
        adi = d["devre_adi"]
        sira = 0
        for s in d["satirlar"]:
            if s.get("sil"):
                continue
            ham_bas, ham_bit = str(s.get("bas") or "").strip(), str(s.get("bit") or "").strip()
            if not ham_bas and not ham_bit:
                continue
            sira += 1
            r = s.get("r", "")
            if not ham_bas or not ham_bit:
                eksik = "bas" if not ham_bas else "bit"
                hatalar.append(_hata(f"{adi}: {sira}. satırda başlangıç ve bitiş birlikte girilmeli.", f"{r}_{eksik}"))
                continue
            bas, bit = program.saat_dogrula(ham_bas), program.saat_dogrula(ham_bit)
            if not bas or not bit:
                hatalar.append(
                    _hata(f"{adi}: {sira}. satırdaki saat SS:DD biçiminde olmalı (ör. 08:20).", f"{r}_{'bas' if not bas else 'bit'}")
                )
                continue
            if program.dk(bit) <= program.dk(bas):
                hatalar.append(
                    _hata(f"{adi}: {bas}–{bit} dersinin bitişi başlangıcından sonra olmalı; dersler gece yarısını aşamaz.", f"{r}_bit")
                )
        gecerli = _gecerli_satirlar(d)
        toplam += len(gecerli)
        if len(gecerli) > EN_COK_DERS:
            hatalar.append(_hata(f"{adi}: en çok {EN_COK_DERS} ders olabilir."))
        ayni = set()
        for no, (bas, bit, r) in enumerate(gecerli, start=1):
            sure = program.dk(bit) - program.dk(bas)
            if not DERS_DK[0] <= sure <= DERS_DK[1]:
                hatalar.append(
                    _hata(f"{adi}: {no}. ders {sure} dakika; ders süresi {DERS_DK[0]}–{DERS_DK[1]} dakika olmalı.", f"{r}_bit")
                )
        for i in range(len(gecerli) - 1):
            (a, b_, _r1), (c, d_, r2) = gecerli[i], gecerli[i + 1]
            if a == c:
                if a not in ayni:
                    ayni.add(a)
                    hatalar.append(_hata(f"{adi}: {a} başlangıçlı iki ders var.", f"{r2}_bas"))
                continue
            if program.dk(c) < program.dk(b_):
                hatalar.append(
                    _hata(f"{adi}: {i + 1}. ders ({a}–{b_}) ile {i + 2}. ders ({c}–{d_}) çakışıyor.", f"{r2}_bas")
                )
            else:
                ara = program.dk(c) - program.dk(b_)
                if TENEFFUS_ESIGI_DK < ara <= 30:
                    uyarilar.append(f"{adi}: {i + 1}. dersten sonraki {ara} dakikalık ara öğle arası sayılacak.")
        if gecerli:
            araliklar.append((adi, program.dk(gecerli[0][0]), max(program.dk(g[1]) for g in gecerli)))
    if not toplam and not any(h["alan"] and h["alan"] != "cizelge-ad" for h in hatalar):
        hatalar.append(_hata("Çizelgede en az bir ders olmalı."))
    for i in range(len(araliklar)):
        for j in range(i + 1, len(araliklar)):
            (ad1, b1, s1), (ad2, b2, s2) = araliklar[i], araliklar[j]
            a, b_ = max(b1, b2), min(s1, s2)
            if a < b_:
                uyarilar.append(
                    f"{ad1} ve {ad2} devreleri {program.saat_metni(a)}–{program.saat_metni(b_)} arasında çakışıyor; "
                    "bu aralıkta teneffüs kilidi verilmez."
                )
    kimlikler = {d["devre"] for d in taslak["devreler"] if _gecerli_satirlar(d)}
    if "normal" in kimlikler and kimlikler & {"sabah", "ogle"}:
        uyarilar.append("Normal devre, Sabah ya da Öğleden sonra ile aynı çizelgede; ikili eğitimde Normal'i kullanmayın.")
    return hatalar, uyarilar


# ---- aralıklar ve zaman çizgisi -------------------------------------------------------------------
def ara_turu(dakika: int) -> str:
    return "teneffus" if dakika <= TENEFFUS_ESIGI_DK else "ogle"


def ara_metni(dakika: int | None) -> str:
    """"Sonraki ara" sütunu: "Teneffüs 10 dk", "Öğle arası 45 dk"; ara yoksa "—"."""
    if dakika is None:
        return "—"
    if dakika <= 0:
        return "Ara yok"
    return f"{program.NEDEN_TENEFFUS if ara_turu(dakika) == 'teneffus' else program.NEDEN_OGLE} {dakika} dk"


def araliklar(dersler) -> list[dict]:
    """[(no, bas, bit)] → ders ve aradaki boşluklar: [{"tur": "ders"|"teneffus"|"ogle", "bas", "bit", "dk", "no"}].

    Boşluk ≤ 20 dk teneffüs, daha uzunu öğle arası (sunucu kilidiyle aynı eşik); 0 dk boşluk yazılmaz.
    """
    sirali = sorted(dersler, key=lambda d: (program.dk(d[1]), d[0]))
    sonuc: list[dict] = []
    for i, (no, bas, bit) in enumerate(sirali):
        if i:
            onceki_bit = sirali[i - 1][2]
            ara = program.dk(bas) - program.dk(onceki_bit)
            if ara > 0:
                sonuc.append({"tur": ara_turu(ara), "bas": onceki_bit, "bit": bas, "dk": ara, "no": None})
        sonuc.append({"tur": "ders", "bas": bas, "bit": bit, "dk": program.dk(bit) - program.dk(bas), "no": no})
    return sonuc


def _liste_satiri(a: dict) -> str:
    if a["tur"] == "ders":
        return f"{a['bas']}–{a['bit']} · {a['no']}. ders"
    ad = program.NEDEN_TENEFFUS if a["tur"] == "teneffus" else program.NEDEN_OGLE
    return f"{a['bas']}–{a['bit']} · {ad} ({a['dk']} dk)"


def _birlesik(araliklar_: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return program.birlestir(araliklar_)


def zaman_cizgisi(devreler) -> dict:
    """Günün zaman çizgisi (şartname §5.5). Girdi: [(devre_adi, [(no, bas, bit)…])…].

    Döndürür: {"bos", "genislik": 1000, "yukseklik", "seritler": [{"ad","y","yukseklik","dersler":[{x,w,no,bas,bit}],
    "aralar": [{x,w,tur,dk,bas,bit}]}], "saatler": [{x, metin}], "cakismalar": [{x,w}], "cakisma_metinleri": [..],
    "listeler": [{"ad", "satirlar": [metin], "ogeler": [{"tur": "ders"|"teneffus"|"ogle", "metin"}]}], "bas", "bit"}. Konum ve genişlik tam sayıdır (SVG öznitelikleri; style yok).
    """
    devreler = [(ad, sorted(d, key=lambda x: program.dk(x[1]))) for ad, d in devreler if d]
    if not devreler:
        return {"bos": True, "genislik": 1000, "yukseklik": 24, "seritler": [], "saatler": [], "cakismalar": [],
                "cakisma_metinleri": [], "listeler": [], "bas": None, "bit": None}  # fmt: skip
    t0 = min(program.dk(x[1]) for _a, d in devreler for x in d)
    t1 = max(program.dk(x[2]) for _a, d in devreler for x in d)
    olcek = 1000 / max(1, t1 - t0)

    def x(dakika: int) -> int:
        return round((dakika - t0) * olcek)

    seritler, listeler = [], []
    for sira, (ad, dersler) in enumerate(devreler):
        ara = araliklar(dersler)
        seritler.append(
            {
                "ad": ad,
                "y": 4 + sira * 28,
                "yukseklik": 20,
                "dersler": [
                    {"x": x(program.dk(a["bas"])), "w": max(1, x(program.dk(a["bit"])) - x(program.dk(a["bas"]))),
                     "no": a["no"], "bas": a["bas"], "bit": a["bit"]}
                    for a in ara if a["tur"] == "ders"
                ],
                "aralar": [
                    {"x": x(program.dk(a["bas"])), "w": max(1, x(program.dk(a["bit"])) - x(program.dk(a["bas"]))),
                     "tur": a["tur"], "dk": a["dk"], "bas": a["bas"], "bit": a["bit"]}
                    for a in ara if a["tur"] != "ders"
                ],
            }
        )  # fmt: skip
        listeler.append({"ad": ad, "satirlar": [_liste_satiri(a) for a in ara],
                         "ogeler": [{"tur": a["tur"], "metin": _liste_satiri(a)} for a in ara]})  # fmt: skip
    cakismalar, cakisma_metinleri = [], []
    birlesikler = [(ad, _birlesik([(program.dk(b_), program.dk(s_)) for _n, b_, s_ in d])) for ad, d in devreler]
    for i in range(len(birlesikler)):
        for j in range(i + 1, len(birlesikler)):
            for a1, b1 in birlesikler[i][1]:
                for a2, b2 in birlesikler[j][1]:
                    a, b_ = max(a1, a2), min(b1, b2)
                    if a < b_:
                        cakismalar.append({"x": x(a), "w": max(1, x(b_) - x(a))})
                        cakisma_metinleri.append(
                            f"{birlesikler[i][0]} ve {birlesikler[j][0]} {program.saat_metni(a)}–{program.saat_metni(b_)} arasında çakışıyor"
                        )
    saatler = [{"x": x(s * 60), "metin": f"{s:02d}:00"} for s in range(t0 // 60 + (1 if t0 % 60 else 0), t1 // 60 + 1)]
    return {
        "bos": False,
        "genislik": 1000,
        "yukseklik": 28 * len(devreler) + 24,
        "seritler": seritler,
        "saatler": saatler,
        "cakismalar": cakismalar,
        "cakisma_metinleri": cakisma_metinleri,
        "listeler": listeler,
        "bas": program.saat_metni(t0),
        "bit": program.saat_metni(t1),
    }


def zaman_cizgisi_derslerden(dersler) -> dict:
    """[(devre, devre_adi, no, bas, bit)] → zaman_cizgisi (devreler ilk derse göre sıralı)."""
    gruplar: dict[str, tuple[str, list]] = {}
    for devre, adi, no, bas, bit in dersler:
        gruplar.setdefault(devre, (adi, []))[1].append((no, bas, bit))
    sirali = sorted(gruplar.items(), key=lambda g: (min(program.dk(x[1]) for x in g[1][1]), DEVRE_SIRA.get(g[0], 1)))
    return zaman_cizgisi([(adi, liste) for _d, (adi, liste) in sirali])


def zaman_cizgisi_plandan(plan: dict) -> dict:
    """program.gun_plani sonucundan zaman çizgisi."""
    return zaman_cizgisi_derslerden(
        [(d[0], d[1], d[2], d[3].strftime("%H:%M"), d[4].strftime("%H:%M")) for d in plan.get("dersler") or []]
    )


# ---- hızlı oluştur ---------------------------------------------------------------------------------
def ogle_onerisi(sabah_bitis: str) -> str | None:
    """Sabah devresinin son bitişi + 20 dk, dakika 5'e yukarı yuvarlanır (Okul Zili ile aynı); gün aşarsa None."""
    dakika = program.dk(sabah_bitis) + OGLE_GECIS_DK
    dakika = -(-dakika // 5) * 5
    return program.saat_metni(dakika) if dakika < 24 * 60 else None


def hizli_degerleri(taslak: dict, p=None) -> list[dict]:
    """Hızlı oluştur formunun devre başına alanları (gönderilmişse gönderilen değerlerle)."""
    sonuc = []
    for d in taslak["devreler"]:
        varsayilan = HIZLI_VARSAYILAN.get(d["devre"], HIZLI_VARSAYILAN["normal"])
        alanlar = {}
        for a in HIZLI_ALANLAR:
            gelen = _form_al(p, f"{d['devre']}_{a}") if p is not None else ""
            alanlar[a] = gelen if p is not None and (gelen or a == "ilk") else str(varsayilan[a])
        uret = True if p is None else _form_al(p, f"{d['devre']}_uret") == "1"
        sonuc.append({"devre": d["devre"], "devre_adi": d["devre_adi"], "uret": uret, **alanlar})
    return sonuc


def _sayi(p, ad: str, alt: int, ust: int, aciklama: str, hatalar: list[str]) -> int | None:
    try:
        deger = int(_form_al(p, ad).strip())
    except ValueError:
        hatalar.append(f"{aciklama} {alt}–{ust} arasında bir sayı olmalı.")
        return None
    if not alt <= deger <= ust:
        hatalar.append(f"{aciklama} {alt}–{ust} arasında olmalı.")
        return None
    return deger


def hizli_uret(p, taslak: dict) -> tuple[dict, list[str]]:
    """Şartname §5.3: işaretli (`{devre}_uret=1`) devrelerin satırlarını parametrelerden yeniden üretir;
    işaretsiz devrenin satırları korunur. Kaydetmez. Döndürür (yeni taslak, hatalar); hata varsa taslak değişmez.

    Alanlar: {devre}_ilk (SS:DD; öğle devresinde boşsa sabahın son bitişi + 20 dk, 5'e yuvarlanır),
    {devre}_sayi (1–20), {devre}_ders_dk (10–180), {devre}_teneffus_dk (0–60),
    {devre}_uzun_sonra (0 = yok, en çok sayı−1), {devre}_uzun_dk (0–180).
    """
    hatalar: list[str] = []
    yeni = {"ad": taslak["ad"], "devreler": [dict(d, satirlar=list(d["satirlar"])) for d in taslak["devreler"]]}
    # Sabah önce üretilir ki öğle önerisi yeni sabah bitişinden hesaplansın.
    sira = sorted(range(len(yeni["devreler"])), key=lambda i: (yeni["devreler"][i]["devre"] == "ogle", i))
    for i in sira:
        d = yeni["devreler"][i]
        devre, adi = d["devre"], d["devre_adi"]
        if _form_al(p, f"{devre}_uret") != "1":
            continue
        onceki = len(hatalar)
        ham_ilk = _form_al(p, f"{devre}_ilk").strip()
        ilk = program.saat_dogrula(ham_ilk) if ham_ilk else None
        if ham_ilk and not ilk:
            hatalar.append(f"{adi}: ilk ders SS:DD biçiminde olmalı (ör. 08:20).")
        elif not ham_ilk:
            sabah = next((x for x in yeni["devreler"] if x["devre"] == "sabah"), None)
            sabah_dersleri = _gecerli_satirlar(sabah) if sabah else []
            if devre == "ogle" and sabah_dersleri:
                ilk = ogle_onerisi(max(sabah_dersleri, key=lambda s: program.dk(s[1]))[1])
                if not ilk:
                    hatalar.append(f"{adi}: dersler gece yarısını geçiyor; ilk dersi ya da ders sayısını değiştirin.")
            elif devre == "ogle":
                hatalar.append("Öğleden sonra devresinin ilk dersini yazın.")
            else:
                hatalar.append(f"{adi}: ilk ders SS:DD biçiminde olmalı (ör. 08:20).")
        sayi = _sayi(p, f"{devre}_sayi", 1, EN_COK_DERS, f"{adi}: ders sayısı", hatalar)
        ders_dk = _sayi(p, f"{devre}_ders_dk", DERS_DK[0], DERS_DK[1], f"{adi}: ders süresi (dk)", hatalar)
        teneffus = _sayi(p, f"{devre}_teneffus_dk", 0, 60, f"{adi}: teneffüs (dk)", hatalar)
        uzun_sonra = _sayi(p, f"{devre}_uzun_sonra", 0, max(0, (sayi or EN_COK_DERS) - 1),
                           f"{adi}: uzun aranın yeri (kaçıncı dersten sonra)", hatalar)  # fmt: skip
        uzun_dk = _sayi(p, f"{devre}_uzun_dk", 0, 180, f"{adi}: uzun ara (dk)", hatalar)
        if len(hatalar) > onceki or not ilk:
            continue
        satirlar = []
        imlec = program.dk(ilk)
        for no in range(1, sayi + 1):
            bitis = imlec + ders_dk
            if bitis >= 24 * 60:
                hatalar.append(f"{adi}: dersler gece yarısını geçiyor; ilk dersi ya da ders sayısını değiştirin.")
                break
            satirlar.append({"r": "", "bas": program.saat_metni(imlec), "bit": program.saat_metni(bitis), "sil": False})
            imlec = bitis + (uzun_dk if uzun_sonra and no == uzun_sonra else teneffus)
        else:
            d["satirlar"] = satirlar
    if hatalar:
        return taslak, hatalar
    return kimlikleri_yenile(yeni), []


def varsayilan_taslak(ad: str, duzen: str) -> dict:
    """"Yeni çizelge": tek devre (Normal 8 ders) ya da ikili (Sabah 6 + Öğleden sonra 6, öğle önerilir)."""
    devreler = ["sabah", "ogle"] if duzen == "ikili" else ["normal"]
    taslak = {"ad": ad, "devreler": [{"devre": d, "devre_adi": DEVRELER[d], "satirlar": []} for d in devreler]}
    p = {}
    for d in devreler:
        p[f"{d}_uret"] = "1"
        for a in HIZLI_ALANLAR:
            p[f"{d}_{a}"] = str(HIZLI_VARSAYILAN[d][a])
    yeni, hatalar = hizli_uret(p, taslak)
    if hatalar:  # varsayılanlar sabittir; olmamalı
        raise ValueError(hatalar[0])
    return yeni


# ---- günlere bölme, haftalık düzen ---------------------------------------------------------------
def gun_araligi(gunler) -> str:
    """Ardışık üç ve daha çok gün "Pzt–Per", diğerleri virgülle: [0,1,2,3] → "Pzt–Per"; [5,6] → "Cmt, Paz"."""
    gunler = sorted(set(int(g) for g in gunler))
    parcalar, i = [], 0
    while i < len(gunler):
        j = i
        while j + 1 < len(gunler) and gunler[j + 1] == gunler[j] + 1:
            j += 1
        if j - i >= 2:
            parcalar.append(f"{zamanlama.GUN_KISA[gunler[i]]}–{zamanlama.GUN_KISA[gunler[j]]}")
        else:
            parcalar.extend(zamanlama.GUN_KISA[g] for g in gunler[i : j + 1])
        i = j + 1
    return ", ".join(parcalar)


def gunlere_bol(satirlar) -> list[tuple[list[int], list[tuple]]]:
    """Haftalık satırlar [(gun, devre, devre_adi, no, bas, bit)] → aynı imzalı günler tek çizelge:
    [(gunler, [(devre, devre_adi, no, bas, bit)])], ilk güne göre sıralı."""
    gunluk: dict[int, list[tuple]] = {}
    for gun, devre, adi, no, bas, bit in satirlar:
        gunluk.setdefault(int(gun), []).append((devre, adi, int(no), bas, bit))
    gruplar: dict[tuple, list[int]] = {}
    for gun in sorted(gunluk):
        imza = tuple(sorted(gunluk[gun]))
        gruplar.setdefault(imza, []).append(gun)
    return sorted(((gunler, list(imza)) for imza, gunler in gruplar.items()), key=lambda g: g[0][0])


def benzersiz_ad(b, ad: str, haric: int | None = None) -> str:
    """Ad başka bir çizelgede varsa sonuna " (2)", " (3)"… ekler (40 karakteri aşmadan)."""
    mevcut = {ad_anahtari(s["ad"]) for s in b.execute("SELECT id, ad FROM zil_cizelgesi") if s["id"] != haric}
    aday, sira = ad[:AD_EN_UZUN], 1
    while ad_anahtari(aday) in mevcut:
        sira += 1
        ek = f" ({sira})"
        aday = ad[: AD_EN_UZUN - len(ek)].rstrip() + ek
    return aday


def cizelge_ekle(b, ad: str, dersler, kaynak: str, kullanici: str) -> int:
    kimlik = b.execute(
        "INSERT INTO zil_cizelgesi (ad, kaynak, olusturan, olusturma) VALUES (?, ?, ?, ?)",
        (ad, kaynak, kullanici, vt.simdi()),
    ).lastrowid
    dersler_yaz(b, kimlik, dersler)
    return kimlik


def dersler_yaz(b, cizelge_id: int, dersler) -> None:
    b.execute("DELETE FROM zil_cizelge_ders WHERE cizelge_id = ?", (cizelge_id,))
    b.executemany(
        "INSERT INTO zil_cizelge_ders (cizelge_id, devre, devre_adi, ders_no, baslangic, bitis) VALUES (?, ?, ?, ?, ?, ?)",
        [(cizelge_id, d[0], d[1], d[2], d[3], d[4]) for d in dersler],
    )


def haftalik_oku(b) -> dict[int, int | None]:
    return {s["gun"]: s["cizelge_id"] for s in b.execute("SELECT gun, cizelge_id FROM zil_haftalik")}


def haftalik_yaz(b) -> int:
    """`ders_saati`'ni haftalık düzenden baştan yazar (türetilmiş tablo). Yazılan satır sayısını döndürür."""
    b.execute("DELETE FROM ders_saati")
    return b.execute(
        "INSERT INTO ders_saati (gun, devre, devre_adi, ders_no, baslangic, bitis) "
        "SELECT h.gun, d.devre, d.devre_adi, d.ders_no, d.baslangic, d.bitis "
        "FROM zil_haftalik h JOIN zil_cizelge_ders d ON d.cizelge_id = h.cizelge_id"
    ).rowcount


# ---- tarihe özel çizelgeler ---------------------------------------------------------------------------
def gunler_coz(metin_: str) -> list[int]:
    return sorted({int(g) for g in str(metin_ or "").split(",") if g.strip().isdigit() and 0 <= int(g) <= 6})


def tarihli_kural(b, tarih: date) -> dict | None:
    """O günü kapsayan tarihe özel çizelge: {"id","ad","dersler":[(devre, devre_adi, no, bas, bit)],"ders_yok","cizelge_id",
    "cizelge_adi"} ya da None. Çakışan kayıt eklenemez; yine de birden çoksa en son eklenen geçerlidir."""
    iso = tarih.isoformat()
    for s in b.execute(
        "SELECT t.*, c.ad AS cizelge_adi FROM zil_tarihli t LEFT JOIN zil_cizelgesi c ON c.id = t.cizelge_id "
        "WHERE t.bas <= ? AND t.bit >= ? ORDER BY t.id DESC",
        (iso, iso),
    ):
        if tarih.weekday() not in gunler_coz(s["gunler"]):
            continue
        dersler = cizelge_dersleri(b, s["cizelge_id"]) if s["cizelge_id"] else []
        return {"id": s["id"], "ad": s["ad"], "dersler": dersler, "ders_yok": s["cizelge_id"] is None,
                "cizelge_id": s["cizelge_id"], "cizelge_adi": s["cizelge_adi"]}  # fmt: skip
    return None


def tarihli_durumu(satir, bugun: date) -> str:
    if satir["bit"] < bugun.isoformat():
        return "bitti"
    if satir["bas"] > bugun.isoformat():
        return "ileride"
    return "suruyor"


TARIHLI_DURUMU = {"suruyor": "Sürüyor", "ileride": "İleride", "bitti": "Bitti"}


def aralik_metni(bas: str, bit: str) -> str:
    return f"{zamanlama.tarih_yaz(bas)}–{zamanlama.tarih_yaz(bit)}" if bas != bit else zamanlama.tarih_yaz(bas)


def tarihli_dogrula(b, ad, bas, bit, gunler, bugun: date) -> tuple[dict | None, list[str]]:
    """Tarihe özel çizelge formu: (değerler, hatalar). Değerler: {"ad","bas","bit","gunler"} (ISO tarihler)."""
    hatalar: list[str] = []
    ad = ad_temizle(ad)
    if not 1 <= len(ad) <= TARIHLI_AD_EN_UZUN:
        hatalar.append(f"Ad 1–{TARIHLI_AD_EN_UZUN} karakter olmalı.")
    elif guvenlik.tc_kimlik_var(ad):
        hatalar.append(TC_ILETISI)
    try:
        bas_t = zamanlama.tarih_coz(bas, "Başlangıç tarihini seçin.")
        bit_t = zamanlama.tarih_coz(bit, "Bitiş tarihini seçin.")
    except ValueError as hata:
        return None, [*hatalar, str(hata)]
    gunler = sorted({int(g) for g in gunler if str(g).isdigit() and 0 <= int(g) <= 6})
    if bit_t < bas_t:
        hatalar.append("Bitiş tarihi başlangıçtan önce olamaz.")
    elif (bit_t - bas_t).days + 1 > TARIHLI_EN_UZUN_GUN:
        hatalar.append(f"Aralık en çok {TARIHLI_EN_UZUN_GUN} gün olabilir.")
    if bit_t < bugun:
        hatalar.append("Bitişi geçmiş bir aralık eklenemez.")
    if not gunler:
        hatalar.append("En az bir gün seçin.")
    if not hatalar:
        for s in b.execute("SELECT * FROM zil_tarihli WHERE bas <= ? AND bit >= ?", (bit_t.isoformat(), bas_t.isoformat())):
            ortak = set(gunler) & set(gunler_coz(s["gunler"]))
            # Aralıklar kesişiyor; ortak hafta günlerinden biri kesişimde gerçekten var mı?
            ilk, son = max(bas_t, date.fromisoformat(s["bas"])), min(bit_t, date.fromisoformat(s["bit"]))
            if ortak and any((ilk + timedelta(days=i)).weekday() in ortak for i in range(min(7, (son - ilk).days + 1))):
                hatalar.append(
                    f"Bu aralık '{s['ad']}' ({aralik_metni(s['bas'], s['bit'])}) ile aynı günlere düşüyor; önce onu silin."
                )
                break
    return {"ad": ad, "bas": bas_t.isoformat(), "bit": bit_t.isoformat(), "gunler": gunler}, hatalar


# ---- kullanım ---------------------------------------------------------------------------------------
def kullanim_bilgisi(b, cizelge_id: int, bugun: date | None = None) -> dict:
    """{"gunler": [..], "tarihli": n (hepsi), "tarihli_etkin": n (bitmemiş), "tarihli_gunler": set, "metin",
    "kullaniliyor" (silinemez), "etkin" (haftalık ya da bitmemiş tarihe özelde)}."""
    bugun = bugun or bugun_tarihi()
    gunler = sorted(g for g, c in haftalik_oku(b).items() if c == cizelge_id)
    tarihli = b.execute("SELECT * FROM zil_tarihli WHERE cizelge_id = ?", (cizelge_id,)).fetchall()
    etkin = [t for t in tarihli if t["bit"] >= bugun.isoformat()]
    parcalar = []
    if gunler:
        parcalar.append(gun_araligi(gunler))
    if etkin:
        parcalar.append(f"{len(etkin)} tarihe özel")
    if len(tarihli) > len(etkin):
        parcalar.append(f"{len(tarihli) - len(etkin)} bitmiş tarihe özel")
    tarihli_gunler: set[int] = set()
    for t in etkin:
        tarihli_gunler.update(gunler_coz(t["gunler"]))
    return {
        "gunler": gunler,
        "tarihli": len(tarihli),
        "tarihli_etkin": len(etkin),
        "tarihli_gunler": tarihli_gunler,
        "metin": " · ".join(parcalar) or "Kullanılmıyor",
        "kullaniliyor": bool(gunler or tarihli),
        "etkin": bool(gunler or etkin),
    }


def kullanim(b, cizelge_id: int) -> str:
    """"Pzt–Per · 1 tarihe özel" ya da "Kullanılmıyor"."""
    return kullanim_bilgisi(b, cizelge_id)["metin"]


def devre_ozeti(dersler) -> str:
    """"Normal · 8 ders" ya da "Sabah 6 · Öğleden sonra 6"."""
    sayilar: dict[str, list] = {}
    for devre, adi, _no, bas, _bit in dersler:
        k = sayilar.setdefault(devre, [adi, 0, bas])
        k[1] += 1
        k[2] = min(k[2], bas)
    sirali = sorted(sayilar.values(), key=lambda k: k[2])
    if len(sirali) == 1:
        return f"{sirali[0][0]} · {sirali[0][1]} ders"
    return " · ".join(f"{k[0]} {k[1]}" for k in sirali)


def saat_araligi(dersler) -> str:
    if not dersler:
        return "—"
    return f"{min(d[3] for d in dersler)}–{max(d[4] for d in dersler)}"


def numara_kaymasi(b, cizelge_id: int, eski, yeni) -> list[tuple[str, int, int, int]]:
    """Kullanımdaki çizelgede ders sayısı değişen ve derslik programı olan devreler:
    [(devre_adi, eski_sayi, yeni_sayi, tahta_sayisi)]. Kullanılmayan çizelgede boş."""
    bilgi = kullanim_bilgisi(b, cizelge_id)
    if not bilgi["etkin"]:
        return []
    gunler = sorted(set(bilgi["gunler"]) | bilgi["tarihli_gunler"])
    say_eski: dict[str, list] = {}
    for d in eski:
        say_eski.setdefault(d[0], [d[1], 0])[1] += 1
    say_yeni: dict[str, list] = {}
    for d in yeni:
        say_yeni.setdefault(d[0], [d[1], 0])[1] += 1
    sonuc = []
    for devre in sorted(set(say_eski) | set(say_yeni)):
        e = say_eski.get(devre, [None, 0])[1]
        y = say_yeni.get(devre, [None, 0])[1]
        if e == y or not gunler:
            continue
        tahta = b.execute(
            f"SELECT COUNT(DISTINCT tahta_id) FROM tahta_ders WHERE devre = ? AND gun IN ({','.join('?' * len(gunler))})",
            (devre, *gunler),
        ).fetchone()[0]
        if tahta:
            sonuc.append(((say_yeni.get(devre) or say_eski.get(devre))[0], e, y, tahta))
    return sonuc


def yetim_sayilari(b) -> tuple[int, int]:
    """(artık olmayan ders saatine bağlı derslik programı satırı olan tahta sayısı, satır sayısı)."""
    satir = b.execute(
        "SELECT COUNT(DISTINCT tahta_id), COUNT(*) FROM tahta_ders d WHERE NOT EXISTS (SELECT 1 FROM ders_saati s "
        "WHERE s.gun = d.gun AND s.devre = d.devre AND s.ders_no = d.ders_no)"
    ).fetchone()
    return int(satir[0]), int(satir[1])


# ---- Okul Zili'nden içe aktarma ve ilk taşıma ------------------------------------------------------------
def okulzili_yaz(b, veri: dict, k) -> int:
    """Okul Zili önizlemesini çizelgelere yazar (şartname §7.1). Yazılan çizelge sayısını döndürür.

    Okul Zili kaynaklı eski çizelgelerden tarihe özel kayıtta kullanılmayanlar silinir; haftalık düzen
    baştan yazılır (Okul Zili'nde tanımsız gün = ders yok); elle çizelgeler silinmez. `ders_saati` yeniden
    yazılır; `zil_takvimi` ve `zil_kaynagi`'nı çağıran yazar.
    """
    kullanici = k["ad"] if not isinstance(k, str) else k
    b.execute("DELETE FROM zil_haftalik")
    b.execute(
        "DELETE FROM zil_cizelgesi WHERE kaynak = 'okulzili' AND id NOT IN "
        "(SELECT cizelge_id FROM zil_tarihli WHERE cizelge_id IS NOT NULL)"
    )
    sayi = 0
    for gunler, dersler in gunlere_bol([tuple(d) for d in veri.get("dersler") or []]):
        ad = benzersiz_ad(b, "Okul Zili · " + gun_araligi(gunler))
        kimlik = cizelge_ekle(b, ad, dersler, "okulzili", kullanici)
        b.executemany("INSERT INTO zil_haftalik (gun, cizelge_id) VALUES (?, ?)", [(g, kimlik) for g in gunler])
        sayi += 1
    haftalik_yaz(b)
    return sayi


def ilk_tasima(b) -> None:
    """0.10.0 göçünden sonra bir kez: mevcut `ders_saati` aynı imzalı günlere göre çizelgelere taşınır.

    Yalnız `ayar.zil_tasima_bekliyor` varsa çalışır; tek işlem içinde çağrılır; sonunda bayrak silinir
    (yarıda kalırsa bir sonraki açılışta yeniden çalışır). `ders_saati` yeniden yazılmaz (zaten aynı);
    devre kimlikleri ve adları korunur (derslik programı, uyarı ve yoklama aynı anahtarla sürer).
    """
    if not b.execute("SELECT 1 FROM ayar WHERE anahtar = 'zil_tasima_bekliyor'").fetchone():
        return
    satirlar = program.ders_saatleri_oku(b)
    kaynak_ayar = vt.ayar_al(b, "zil_kaynagi")
    tur = kaynak_ayar.get("tur") if isinstance(kaynak_ayar, dict) else None
    kaynak = tur if tur in ("okulzili", "elle") else "tasima"
    gruplar = gunlere_bol(satirlar)
    for gunler, dersler in gruplar:
        ad = benzersiz_ad(b, "Ders saatleri · " + gun_araligi(gunler))
        kimlik = cizelge_ekle(b, ad, dersler, kaynak, "sistem")
        b.executemany(
            "INSERT OR REPLACE INTO zil_haftalik (gun, cizelge_id) VALUES (?, ?)", [(g, kimlik) for g in gunler]
        )
    b.execute("DELETE FROM ayar WHERE anahtar = 'zil_tasima_bekliyor'")
    gun_sayisi = sum(len(g) for g, _ in gruplar)
    vt.kayit_dus(b, "sistem", "Zil saatleri çizelgelere taşındı", f"{len(gruplar)} çizelge · {gun_sayisi} gün")


# ---- CSV ---------------------------------------------------------------------------------------------
_CSV_BASLIK = {"devre": "devre", "oturum": "devre", "ders": "ders", "baslangic": "baslangic", "bitis": "bitis"}


def csv_yaz(dersler) -> bytes:
    """[(devre, devre_adi, no, bas, bit)] → `devre;ders;baslangic;bitis` (devre sütununa ad yazılır)."""
    sirali = sorted(dersler, key=lambda d: (d[3], d[0], d[2]))
    return metin.csv_yaz(["devre", "ders", "baslangic", "bitis"], [[d[1], d[2], d[3], d[4]] for d in sirali])


def csv_oku(bayt: bytes, devreler: dict[str, str]) -> tuple[list[dict], list[str]]:
    """Çizelge CSV'si → (taslak devreleri, satır hataları). Kaydetmez.

    devreler: çizelgedeki devreler {kimlik: ad}. Devre adı önce bunlarla, sonra `program.devre_kimligi` ile
    eşlenir; sabit kümede ya da çizelgede değilse satır hatası. `ders` sütunu yok sayılır (numara kendiliğinden).
    Okunamazsa ValueError.
    """
    basliklar, satirlar = metin.csv_oku(bayt, CSV_EN_COK_BAYT, CSV_EN_COK_SATIR)
    konum: dict[str, int] = {}
    for sira, baslik in enumerate(basliklar):
        alan = _CSV_BASLIK.get(metin.katla(baslik))
        if alan and alan not in konum:
            konum[alan] = sira
    eksik = [a for a in ("devre", "baslangic", "bitis") if a not in konum]
    if eksik:
        raise ValueError("Dosyada şu sütunlar yok: " + ", ".join(eksik) + ". Çizelgeyi CSV olarak indirip örnek alın.")
    adlar = {metin.katla(a): d for d, a in devreler.items()}
    sonuc: dict[str, dict] = {}
    hatalar: list[str] = []
    for no, satir in enumerate(satirlar, start=2):
        def hucre(alan: str, satir=satir) -> str:
            return metin.csv_hucre_coz(satir[konum[alan]]).strip() if alan in konum and konum[alan] < len(satir) else ""

        ham_devre = hucre("devre")
        devre = adlar.get(metin.katla(ham_devre)) or (ham_devre if ham_devre in devreler else None)
        if devre is None:
            aday = program.devre_kimligi(ham_devre)
            devre = aday if aday in DEVRELER or aday in devreler else None
        if devre is None:
            hatalar.append(f"{no}. satır: devre '{ham_devre[:30]}' tanınmıyor (Normal, Sabah, Öğleden sonra).")
            continue
        bas, bit = program.saat_dogrula(hucre("baslangic")), program.saat_dogrula(hucre("bitis"))
        if not bas or not bit:
            hatalar.append(f"{no}. satır: saat SS:DD biçiminde olmalı (ör. 08:20).")
            continue
        sonuc.setdefault(devre, {"devre": devre, "devre_adi": devre_adi(devre, devreler), "satirlar": []})["satirlar"].append(
            {"r": "", "bas": bas, "bit": bit, "sil": False}
        )
    return devre_sirala(list(sonuc.values())), hatalar


def ascii_ad(ad: str) -> str:
    """Dosya adı için: "Normal gün (kopya)" → "normal-gun-kopya"."""
    return re.sub(r"[^a-z0-9]+", "-", metin.katla(ad)).strip("-")[:40] or "cizelge"
