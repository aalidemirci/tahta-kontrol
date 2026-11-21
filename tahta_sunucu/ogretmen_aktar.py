"""Toplu öğretmen listesi aktarımı (0.21.0; FastAPI'siz). Uçlar `panel_yoklama.py`'dedir.

Kaynaklar (içerikten tanınır, uzantıdan değil):
- aSc Timetables XML: YALNIZ `<teachers><teacher>` öğesinin `firstname`, `lastname` (biri boşsa `name`)
  öznitelikleri okunur; kısa ad, cinsiyet, renk, e-posta, telefon, ortak kimliği OKUNMAZ. Derslik sihirbazının
  okuyucusu (`program_aktar.asc_oku`, `ASC_ATLA`) değişmedi: bu ayrı bir okuyucudur.
- e-Okul personel listesi (OOK01001R1, .XLS): başlık satırında "ADI SOYADI", "GÖREVİ" ve "KADRO DURUMU" ya da
  "BRANŞI" olup "Kod" sütunu YOKSA rapor sayılır (sütun yeri dosyadan dosyaya değişir; okulun kendi "Adı Soyadı;
  Görevi;Kod" tablosu düz tablodur). Görev yalnız önizlemede gösterilir; KADRO DURUMU ve BRANŞI okunmaz. Görevi boş
  satır rapor altbilgisidir: adı da boşsa sessizce, adı doluysa "Atlanan satırlar"da nedeniyle atlanır.
- Düz tablo (.xlsx, .xls, .csv): "Adı; Soyadı" (ya da tek "Adı Soyadı") ve isteğe bağlı "Kod".

T.C. kimlik sütunu hiçbir kaynakta okunmaz (uyarılır); adında T.C. no geçen satır atlanır. Tek "Adı Soyadı"
sütununda son sözcük soyad sayılır; üç ve daha çok sözcüklü ad önizlemede "bölmeyi denetleyin" diye işaretlenir.
Tamamı BÜYÜK HARFLİ ad Türkçe kurallarla baş harfi büyük biçime çevrilir ("ŞULE İPEK" → "Şule İpek"); küçük harf
içeren ad olduğu gibi kalır.

Plan (yazmaz) ve uygulama aynı işlevden çıkar (`plan`); uygulama planı işlem içinde YENİDEN hesaplar (önizlemedeki
kodlar "öngörülen"dir). Dosyada olmayan mevcut öğretmene DOKUNULMAZ (pasifleştirilmez). PIN üretilmez: eklenen
öğretmenin `ogretmen_pin.pin_ozet`'i NULL'dır; PIN mevcut "toplu PIN" düğmesiyle pusulada verilir (kural 19).
"""

from __future__ import annotations

from . import eokul, guvenli_xml, guvenlik, metin, program_aktar
from . import yoklama as yk

SATIR_SINIRI = 899  # öğretmen kodu 101–999: en çok 899 öğretmen
TABLO_SINIRI = eokul.DOSYA_SINIRI
DOSYA_SINIRI = program_aktar.ASC_EN_COK_BAYT  # aSc XML ders kartlarını da taşıdığı için tablodan büyük olabilir
GOREV_EN_UZUN = 60

KAYNAK_ADI = {
    "asc": "aSc Timetables XML",
    "eokul": "e-Okul personel listesi (OOK01001R1)",
    "eokul_xls": "Excel 97-2003 (.xls)",
    "xlsx": "Excel (.xlsx)",
    "csv": "CSV",
}
DURUM_ADI = {"ekle": "Eklenecek", "var": "Zaten var", "pasif": "Pasif olarak var", "yinelenen": "Dosyada yinelenen"}
ASIRI_ILETI = f"Dosyada en çok {SATIR_SINIRI} öğretmen satırı olabilir."
BASLIK_YOK = (
    "Dosyada öğretmen adı sütunları bulunamadı. aSc Timetables XML'ini, e-Okul personel listesini (OOK01001R1) "
    "ya da 'Adı; Soyadı; Kod' başlıklı bir tablo yükleyin."
)
GOREVSIZ_NEDEN = "görevi boş: e-Okul rapor altbilgisi sayıldı (personelse tek tek ekleyin)"
ASC_OGRETMEN_YOK ="aSc dosyasında öğretmen listesi bulunamadı; aSc'den 'aSc Timetables 2012 XML' olarak dışa aktarın."
SABLON_BASLIKLAR = ["Adı", "Soyadı", "Kod"]
SABLON_ORNEK = ["Ayşe", "Örnek", ""]  # uydurma; plan bu satırı tanır ve varsayılan olarak eklemez
_SABLON_ANAHTAR = metin.katla(" ".join(SABLON_ORNEK[:2]))

# Mantıksal alan → başlık eş anlamlıları (katlanmış, SÖZCÜK sınırıyla aranır: "ad" "kadro durumu"na takılmaz).
# Sıra önemli: "adi soyadi" "soyadi"dan, o da "adi"dan önce.
ES_ANLAMLILAR = [
    ("ad_soyad", ("adi soyadi", "ad soyad", "ad soyadi", "adi ve soyadi", "ad ve soyad", "isim soyisim")),
    ("soyad", ("soyadi", "soyad", "soyisim", "soyismi")),
    ("ad", ("adi", "ad", "isim", "ismi")),
    ("kod", ("kod", "kodu")),
    ("gorev", ("gorevi", "gorev")),
]


class OkumaHatasi(eokul.OkumaHatasi):
    """Kullanıcıya gösterilecek Türkçe iletiyle okuma hatası."""


# ---- metin ---------------------------------------------------------------------------------------
def ad_bicimle(ad: str, soyad: str) -> tuple[str, str]:
    """Adın tamamı büyük ya da tamamı küçük harfse (ad ve soyad birlikte) Türkçe baş harf büyük biçime çevrilir;
    karışık yazılmış ad aynen kalır ("McKenzie", "Ayşe nur" elle düzeltilir)."""
    tam = f"{ad} {soyad}"
    if metin.tamami_buyuk_mu(tam) or (any(h.isalpha() for h in tam) and not any(h.isupper() for h in tam)):
        return metin.tr_bas_buyuk(ad), metin.tr_bas_buyuk(soyad)
    return ad, soyad


def _sade(s) -> str:
    return " ".join(str(s or "").split())


def _kod(s) -> str:
    kod = _sade(s)
    if kod.endswith(".0") and metin.rakam_mi(kod[:-2]):
        kod = kod[:-2]
    return kod


def _anahtar(ad: str, soyad: str) -> str:
    return metin.katla(f"{ad} {soyad}")


def _satir(satir: int, ad: str, soyad: str, kod: str = "", gorev: str = "", bolme: bool = False) -> dict | str:
    """Bir öğretmen satırı ya da atlama nedeni (str)."""
    ad, soyad = ad_bicimle(_sade(ad), _sade(soyad))
    try:
        ad, soyad = yk.ogretmen_adi_coz(ad, soyad)
    except ValueError:
        if guvenlik.tc_kimlik_var(ad) or guvenlik.tc_kimlik_var(soyad):
            return "adda T.C. kimlik numarasına benzeyen değer var"
        return "ad boş"
    gorev = _sade(gorev)[:GOREV_EN_UZUN]
    if guvenlik.tc_kimlik_var(gorev):
        gorev = ""
    return {"satir": satir, "ad": ad, "soyad": soyad, "kod": _kod(kod)[:6], "gorev": gorev, "bolme": bolme}


def _tek_sutun_bol(ad_soyad: str) -> tuple[str, str, bool]:
    """Tek sütundaki adı böler: son sözcük soyad. Üç ve daha çok sözcükte bölme belirsizdir (işaretlenir)."""
    parcalar = _sade(ad_soyad).split()
    if not parcalar:
        return "", "", False
    if len(parcalar) == 1:
        return parcalar[0], "", False
    return " ".join(parcalar[:-1]), parcalar[-1], len(parcalar) >= 3


# ---- aSc XML -------------------------------------------------------------------------------------
def _asc_ad(k: dict) -> tuple[str, str, bool]:
    """aSc öğretmeninin (ad, soyad, bölme işareti). firstname ve lastname ikisi de doluysa onlar; biri ya da ikisi
    boşsa tam ad olan `name` bölünür (son sözcük soyad), `name` de boşsa dolu olan alan bölünür. Yarım alanla
    eklemek "Can Ok" adını soyadsız yazar, yalnız lastname dolu satırı "ad boş" diye atlardı."""
    ad, soyad, tam = _sade(k["firstname"]), _sade(k["lastname"]), _sade(k["name"])
    if ad and soyad:
        return ad, soyad, False
    return _tek_sutun_bol(tam or ad or soyad)


def asc_ogretmenleri(bayt: bytes) -> dict:
    """aSc XML'den yalnız öğretmen ad ve soyadı. Okunamazsa ValueError (Türkçe ileti)."""
    if len(bayt) > program_aktar.ASC_EN_COK_BAYT:
        raise OkumaHatasi(f"Dosya en çok {program_aktar.ASC_EN_COK_BAYT // (1024 * 1024)} MB olabilir.")
    veri = guvenli_xml.kodlama_duzelt(bayt)
    guvenli_xml.on_denetim(veri)
    ham: list[dict] = []
    durum = {"yigin": [], "oge": 0, "kok": None, "bolum": 0}

    class _Buyuk(Exception):
        pass

    def basla(ad: str, oznitelik: dict) -> None:
        yigin = durum["yigin"]
        durum["oge"] += 1
        if durum["oge"] > program_aktar.ASC_EN_COK_OGE or len(yigin) >= program_aktar.ASC_EN_DERIN:
            raise _Buyuk
        yigin.append(ad)
        if len(yigin) == 1:
            durum["kok"] = ad
        elif len(yigin) == 2 and ad == "teachers":
            durum["bolum"] += 1
        elif len(yigin) == 3 and ad == "teacher" and yigin[1] == "teachers":
            if len(ham) >= SATIR_SINIRI:
                raise OkumaHatasi(ASIRI_ILETI)
            # İZİNLİ öznitelikler: yalnız bunlar okunur (short, gender, email, mobile, partner_id… okunmaz).
            kayit = {a: str(oznitelik.get(a) or "")[:200] for a in ("firstname", "lastname", "name")}
            ham.append(kayit)

    def bitir(_ad: str) -> None:
        durum["yigin"].pop()

    p = guvenli_xml.ayristirici()
    p.StartElementHandler = basla
    p.EndElementHandler = bitir
    try:
        guvenli_xml.ayristir(p, veri, program_aktar.ASC_OKUNAMADI)
    except _Buyuk as hata:
        raise OkumaHatasi(program_aktar.ASC_BUYUK) from hata
    if durum["kok"] != "timetable":
        raise OkumaHatasi(program_aktar.ASC_DEGIL)
    if not durum["bolum"] or not ham:
        raise OkumaHatasi(ASC_OGRETMEN_YOK)
    ogretmenler, atlanan = [], []
    for i, k in enumerate(ham, start=1):
        ad, soyad, bolme = _asc_ad(k)
        sonuc = _satir(i, ad, soyad, bolme=bolme)
        if isinstance(sonuc, str):
            atlanan.append({"satir": i, "neden": sonuc})
        else:
            ogretmenler.append(sonuc)
    return {
        "kaynak": "asc", "kaynak_adi": KAYNAK_ADI["asc"], "satir_adi": "Sıra",
        "notlar": [f"aSc dosyasında {len(ham)} öğretmen bulundu. Yalnız ad ve soyad okundu; kısa ad, e-posta, telefon okunmadı."],
        "uyarilar": [], "ogretmenler": ogretmenler, "atlanan": atlanan,
    }  # fmt: skip


# ---- tablo (e-Okul personel listesi ve şablon) -------------------------------------------------------
def _alan_bul(norm: str) -> str | None:
    sozcukler = f" {norm} "
    if " kisa " in sozcukler:  # aSc'nin "Kısa ad" sütunu ad değildir
        return None
    for alan, esler in ES_ANLAMLILAR:
        if any(f" {e} " in sozcukler for e in esler):
            return alan
    return None


def _kullanilir(alanlar: dict[str, int]) -> bool:
    return "ad_soyad" in alanlar or ("ad" in alanlar and "soyad" in alanlar)


def _eokul_raporu_mu(baslik: list[str], alanlar: dict[str, int]) -> bool:
    """e-Okul OOK01001R1 mi? "Adı Soyadı" + "Görevi" tek başına yetmez (okulun kendi tablosu da böyle olabilir):
    raporun öbür sütunlarından biri (KADRO DURUMU, BRANŞI) da başlıkta olmalı ve "Kod" sütunu OLMAMALI (raporda
    öğretmen kodu yoktur; kod taşıyan tablo düz tablodur, kodu da okunur)."""
    if not ("ad_soyad" in alanlar and "gorev" in alanlar) or "kod" in alanlar:
        return False
    katli = [f" {eokul.baslik_katla(h)} " for h in baslik]
    return any(" kadro " in h or " bransi " in h or " brans " in h for h in katli)


def matris_coz(bicim: str, matris: list[list[str]]) -> dict:
    """Tablo matrisi (ilk satırlarda başlık) → öğretmen satırları. Başlık bulunamazsa OkumaHatasi."""
    r, alanlar, okunmayan = eokul.baslik_esle(matris, _alan_bul, _kullanilir)
    if not _kullanilir(alanlar):
        raise OkumaHatasi(BASLIK_YOK)
    eokul_mu = _eokul_raporu_mu(matris[r], alanlar)
    if not eokul_mu and "gorev" in alanlar:
        okunmayan.append(_sade(matris[r][alanlar.pop("gorev")])[:40])
    uyarilar = []
    if any(eokul._kimlik_sutunu_mu(eokul.baslik_katla(h)) for h in matris[r]):
        uyarilar.append("T.C. Kimlik No sütunu bulundu, okunmadı.")
    okunmayan = [o for o in okunmayan if o and not eokul._kimlik_sutunu_mu(eokul.baslik_katla(o))]
    if okunmayan:
        uyarilar.append("Okunmayan sütunlar: " + ", ".join(dict.fromkeys(okunmayan)) + ".")

    def hucre(satir, alan):
        i = alanlar.get(alan)
        return satir[i] if i is not None and i < len(satir) else ""

    ogretmenler, atlanan = [], []
    altbilgi = gorevsiz = 0
    for i in range(r + 1, len(matris)):
        satir = matris[i]
        if all(not _sade(h) for h in satir):
            continue
        no = i + 1
        if eokul_mu and not _sade(hucre(satir, "gorev")):
            # e-Okul rapor altbilgisi (okul adı, tarih, sayfa no): her personel satırında görev doludur. Adı boş
            # altbilgi sessizce geçilir; adı dolu satır (okul adı ya da görevi girilmemiş personel) nedeniyle
            # "Atlanan satırlar"a yazılır (sessizce düşmesin; ad sayfaya basılmaz, yalnız satır numarası).
            if _sade(hucre(satir, "ad_soyad")):
                gorevsiz += 1
                atlanan.append({"satir": no, "neden": GOREVSIZ_NEDEN})
            else:
                altbilgi += 1
            continue
        if len(ogretmenler) + len(atlanan) - gorevsiz >= SATIR_SINIRI:
            raise OkumaHatasi(ASIRI_ILETI)
        if "ad_soyad" in alanlar and _sade(hucre(satir, "ad_soyad")):
            ad, soyad, bolme = _tek_sutun_bol(hucre(satir, "ad_soyad"))
        else:
            ad, soyad, bolme = hucre(satir, "ad"), hucre(satir, "soyad"), False
            if not _sade(soyad) and len(_sade(ad).split()) > 1:  # Soyadı boş, Adı'nda tam ad: tek sütun gibi böl
                ad, soyad, bolme = _tek_sutun_bol(ad)
        sonuc = _satir(no, ad, soyad, kod=hucre(satir, "kod"), gorev=hucre(satir, "gorev") if eokul_mu else "", bolme=bolme)
        if isinstance(sonuc, str):
            atlanan.append({"satir": no, "neden": sonuc})
        else:
            ogretmenler.append(sonuc)
    notlar = []
    if eokul_mu:
        notlar.append(f"e-Okul personel listesi algılandı: {len(ogretmenler) + len(atlanan) - gorevsiz} personel satırı"
                      + (f", {altbilgi} altbilgi satırı atlandı" if altbilgi else "")
                      + (f", görevi boş {gorevsiz} satır eklenmedi (rapor altbilgisi sayıldı; Atlanan satırlara bakın)"
                         if gorevsiz else "") + ".")  # fmt: skip
        notlar.append("Kadro durumu ve branş okunmadı. Görev yalnız bu önizlemede gösterilir, saklanmaz.")
    kaynak = "eokul" if eokul_mu else bicim
    return {"kaynak": kaynak, "kaynak_adi": KAYNAK_ADI[kaynak], "satir_adi": "Satır", "notlar": notlar,
            "uyarilar": uyarilar, "ogretmenler": ogretmenler, "atlanan": atlanan}  # fmt: skip


def _xml_mi(veri: bytes) -> bool:
    return veri.removeprefix(b"\xef\xbb\xbf").lstrip()[:1] == b"<"


def dosya_oku(veri: bytes, ad: str = "") -> dict:
    """Yüklenen dosyayı tanır ve ayrıştırır. Döndürür: {kaynak, kaynak_adi, satir_adi, notlar, uyarilar,
    ogretmenler[{satir, ad, soyad, kod, gorev, bolme}], atlanan[{satir, neden}]}. Okunamazsa ValueError."""
    if not veri:
        raise OkumaHatasi("Dosya boş.")
    if len(veri) > DOSYA_SINIRI:
        raise OkumaHatasi(f"Dosya en çok {DOSYA_SINIRI // (1024 * 1024)} MB olabilir.")
    if _xml_mi(veri):
        return asc_ogretmenleri(veri)
    if str(ad or "").lower().endswith(".xml"):
        raise OkumaHatasi(program_aktar.ASC_DEGIL)
    bicim, matris = eokul.matris_oku(veri, ASIRI_ILETI)
    return matris_coz(bicim, matris)


# ---- plan ve uygulama ----------------------------------------------------------------------------
def _mevcut(b) -> dict[str, list[dict]]:
    sonuc: dict[str, list[dict]] = {}
    for o in b.execute(
        "SELECT o.id, o.ad, o.soyad, o.aktif, p.kod FROM ogretmen o LEFT JOIN ogretmen_pin p ON p.ogretmen_id = o.id ORDER BY o.id"
    ):
        sonuc.setdefault(_anahtar(o["ad"], o["soyad"]), []).append(dict(o))
    return sonuc


def onerilen_mi(s: dict, kaynak: str) -> bool:
    """Eklenecek satır varsayılan olarak işaretli mi? Şablon örneği ve (e-Okul'da) öğretmen ya da müdür olmayan
    görev (memur, hizmetli…) işaretsiz gelir; yönetici isterse işaretler."""
    if _anahtar(s["ad"], s["soyad"]) == _SABLON_ANAHTAR:
        return False
    if kaynak == "eokul" and s["gorev"]:
        g = metin.katla(s["gorev"])
        return "ogretmen" in g or "mudur" in g
    return True


def plan(b, ayristirma: dict, secilen: set[int] | None = None) -> dict:
    """Önizleme ve uygulamanın ortak planı (yazmaz).

    `secilen`: eklenecek satırlardan eklenmesi istenenlerin dosya satırı numaraları; None ise önerilen varsayılan
    (`onerilen_mi`). Kod yalnız seçilen satırlara verilir: önce dosyadaki geçerli ve boş kodlar ayrılır, kalanlara
    101'den ilk boş kod (yk.kod_uret mantığı). Dönen satırlar: {satir, ad, soyad, ad_soyad, gorev, bolme,
    dosya_kod, durum: ekle|var|pasif|yinelenen, secili, kod, kod_kaynagi: dosya|otomatik|mevcut|'', ogretmen_id,
    isaretler[]}.
    """
    mevcut = _mevcut(b)
    kullanilan = {s["kod"] for s in b.execute("SELECT kod FROM ogretmen_pin") if s["kod"]}
    kaynak = ayristirma.get("kaynak", "")
    gorulen: set[str] = set()
    satirlar: list[dict] = []
    for s in ayristirma["ogretmenler"]:
        anahtar = _anahtar(s["ad"], s["soyad"])
        x = {"satir": s["satir"], "ad": s["ad"], "soyad": s["soyad"], "ad_soyad": yk.ogretmen_tam_ad(s),
             "gorev": s.get("gorev", ""), "bolme": bool(s.get("bolme")), "dosya_kod": s.get("kod", ""),
             "secili": False, "kod": "", "kod_kaynagi": "", "ogretmen_id": None, "isaretler": []}  # fmt: skip
        if x["bolme"]:
            x["isaretler"].append("Üç ya da daha çok sözcük: ad ve soyad bölmesini denetleyin (son sözcük soyad sayıldı).")
        kayitlar = mevcut.get(anahtar, [])
        aktifler = [o for o in kayitlar if o["aktif"]]
        if anahtar in gorulen:
            x["durum"] = "yinelenen"
            x["isaretler"].append("Bu ad dosyada daha önce geçiyor; ikinci kez eklenmez.")
        elif aktifler:
            x.update(durum="var", ogretmen_id=aktifler[0]["id"], kod=aktifler[0]["kod"] or "", kod_kaynagi="mevcut")
        elif kayitlar:
            x.update(durum="pasif", ogretmen_id=kayitlar[-1]["id"], kod=kayitlar[-1]["kod"] or "", kod_kaynagi="mevcut")
        else:
            x["durum"] = "ekle"
            x["secili"] = onerilen_mi(s, kaynak) if secilen is None else s["satir"] in secilen
            if _anahtar(s["ad"], s["soyad"]) == _SABLON_ANAHTAR:
                x["isaretler"].append("Şablondaki örnek satır; eklemek için işaretleyin.")
        if x["durum"] in ("var", "pasif") and x["dosya_kod"] and x["dosya_kod"] != x["kod"]:
            x["isaretler"].append(f"Dosyadaki kod ({x['dosya_kod']}) yok sayılır; mevcut kod kalır.")
        gorulen.add(anahtar)
        satirlar.append(x)

    # Kodlar: önce dosyadaki geçerli kodlar ayrılır (sonra gelen otomatik kod onları almasın).
    ayrilan: set[str] = set()
    otomatik: list[dict] = []
    for x in satirlar:
        if x["durum"] != "ekle" or not x["secili"]:
            continue
        kod = x["dosya_kod"]
        if not kod:
            otomatik.append(x)
        elif not yk.kod_gecerli(kod):
            x["isaretler"].append(f"Dosyadaki kod ({kod}) 101–999 arasında değil; otomatik kod verilecek.")
            otomatik.append(x)
        elif kod in kullanilan:
            x["isaretler"].append(f"Dosyadaki kod ({kod}) başka bir öğretmende; otomatik kod verilecek.")
            otomatik.append(x)
        elif kod in ayrilan:
            x["isaretler"].append(f"Dosyadaki kod ({kod}) dosyada başka satırda da var; otomatik kod verilecek.")
            otomatik.append(x)
        else:
            ayrilan.add(kod)
            x.update(kod=kod, kod_kaynagi="dosya")
    sayac = 101
    for x in otomatik:
        while sayac <= 999 and (str(sayac) in kullanilan or str(sayac) in ayrilan):
            sayac += 1
        if sayac > 999:
            x["isaretler"].append("Öğretmen kodu kalmadı (101–999 dolu).")
            continue
        ayrilan.add(str(sayac))
        x.update(kod=str(sayac), kod_kaynagi="otomatik")

    sayilar = {d: sum(1 for x in satirlar if x["durum"] == d) for d in DURUM_ADI}
    sayilar.update(
        dosyada=len(satirlar), atlanan=len(ayristirma["atlanan"]), bolme=sum(1 for x in satirlar if x["bolme"]),
        secili=sum(1 for x in satirlar if x["durum"] == "ekle" and x["secili"]),
    )  # fmt: skip
    return {"satirlar": satirlar, "sayilar": sayilar, "gorev_var": kaynak == "eokul"}


def uygula(b, ayristirma: dict, secilen: set[int], etkinlestir: set[int]) -> dict:
    """Tek işlemde (çağıranın `vt.islem()`'i) seçilen satırları ekler, seçilen pasifleri etkinleştirir.

    Plan işlem içinde yeniden hesaplanır; önizlemeden sonra başkasının eklediği ad "zaten var" olur, kod yeniden
    verilir. Eklenen öğretmenin PIN'i yoktur (pin_ozet NULL). Yalnız sayılar döner (işlem kaydına ad yazılmaz)."""
    p = plan(b, ayristirma, secilen)
    eklenecek = [x for x in p["satirlar"] if x["durum"] == "ekle" and x["secili"]]
    if any(not x["kod"] for x in eklenecek):
        raise ValueError("Öğretmen kodu kalmadı (101–999 dolu).")
    for x in eklenecek:
        oid = b.execute("INSERT INTO ogretmen (ad, soyad, aktif) VALUES (?, ?, 1)", (x["ad"], x["soyad"])).lastrowid
        b.execute("INSERT INTO ogretmen_pin (ogretmen_id, kod) VALUES (?, ?)", (oid, x["kod"]))
    etkin = 0
    for oid in {x["ogretmen_id"] for x in p["satirlar"] if x["durum"] == "pasif" and x["ogretmen_id"] in etkinlestir}:
        etkin += b.execute("UPDATE ogretmen SET aktif = 1 WHERE id = ? AND aktif = 0", (oid,)).rowcount
    s = p["sayilar"]
    return {"eklenen": len(eklenecek), "etkinlestirilen": etkin, "var": s["var"], "yinelenen": s["yinelenen"],
            "secilmeyen": s["ekle"] - len(eklenecek), "pasif_kalan": s["pasif"] - etkin, "atlanan": s["atlanan"]}  # fmt: skip


def sablon_csv() -> bytes:
    return metin.csv_yaz(SABLON_BASLIKLAR, [SABLON_ORNEK])
