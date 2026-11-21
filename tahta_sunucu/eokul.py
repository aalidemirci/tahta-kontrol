"""Öğrenci listesi okuma (Aşama 5): e-Okul OOG01001R020 `.XLS`, düz `.xlsx` ve `.csv`.

Saf işlevler (veritabanı yok). Dosya diske yazılmaz; baytlar bellekte ayrıştırılır.
Okunan alanlar yalnız şube, okul no, ad, soyad (KVKK md. 4/2-ç: amaçla sınırlı); T.C. kimlik no,
cinsiyet, pansiyon ve tanınmayan her sütun okunmaz.

e-Okul sınıf listesi blok düzenlidir (şube bilgisi yalnız blok başlığında, ör. "10. Sınıf / A Şubesi");
düzleştirme Kelebek Sınav'ın `apps/okul/eokul.py` mantığının sadeleştirilmiş uyarlamasıdır ve
satır sayısını korur (atlanan satır Excel satır numarasıyla bildirilir).
"""

from __future__ import annotations

import re

from . import metin, xlsx

DOSYA_SINIRI = 5 * 1024 * 1024
SATIR_SINIRI = 5000
BASLIK_TARAMA = 20
AD_EN_UZUN = 60
OKUL_NO_EN_UZUN = 12

OLE2 = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP = b"PK\x03\x04"
BICIM_ADI = {"eokul_xls": "Excel 97-2003 (.xls)", "xlsx": "Excel (.xlsx)", "csv": "CSV"}

XLS_BOZUK = "Excel 97-2003 (.xls) dosyası okunamadı; dosya eksik inmiş ya da bozuk olabilir. e-Okul'dan yeniden indirip deneyin."
XLSX_BOZUK = "Excel (.xlsx) dosyası okunamadı; dosyayı yeniden kaydedip deneyin."
SINIF_SUTUNU = "Sınıf/Şube"

_ASCII = str.maketrans({"ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u", "â": "a", "î": "i", "û": "u",
                        "Ç": "C", "Ğ": "G", "İ": "I", "Ö": "O", "Ş": "S", "Ü": "U", "Â": "A", "Î": "I", "Û": "U"})  # fmt: skip
_BLOK = re.compile(r"(\d{1,2})\s*\.?\s*SINIF\w*\s*/\s*([^\s/()]+)\s*SUBESI")
_HAZ_BLOK = re.compile(r"HAZIRLIK\s*SINIF\w*\s*/\s*([^\s/()]+)\s*SUBESI")
_DIPNOT = re.compile(r"(OGRENCI|PERSONEL|TOPLAM)\s*\w*\s*SAYISI")
_RAPOR_KODU = re.compile(r"\bOO[A-Z]\d+R\d+\b")
_ALFASAYI_DISI = re.compile(r"[^a-z0-9]+")

# Mantıksal alan → başlık eş anlamlıları (katlanmış; alt dize eşlemesi; SIRA ÖNEMLİ:
# "adi soyadi" önce, soyad addan önce — "soyadi" "adi"yi içerir).
ES_ANLAMLILAR = [
    ("ad_soyad", ["ogrenci adi soyadi", "adi soyadi", "ad soyad"]),
    ("soyad", ["ogrenci soyadi", "soyadi"]),
    ("ad", ["ogrenci adi", "adi"]),
    ("sube", ["sinif sube", "sinif", "sube"]),
    ("okul_no", ["okul no", "okul numarasi", "ogrenci no", "ogrenci numarasi", "numara"]),
]


class OkumaHatasi(ValueError):
    """Kullanıcıya gösterilecek Türkçe iletiyle okuma/ayrıştırma hatası."""


def _metin(deger) -> str:
    return "" if deger is None else str(deger).strip()


def _ascii_buyuk(s: str) -> str:
    return s.translate(_ASCII).upper()


def baslik_katla(s) -> str:
    """'Öğrenci No' → 'ogrenci no'; 'Sınıf/Şube' → 'sinif sube'."""
    return _ALFASAYI_DISI.sub(" ", metin.katla(s)).strip()


def _bos(satir) -> bool:
    return all(_metin(h) == "" for h in satir)


# ---- dosya okuma ---------------------------------------------------------------------------------
def _sayi_metni(deger) -> str:
    if isinstance(deger, float) and deger.is_integer() and abs(deger) < 1e15:
        return str(int(deger))
    return _metin(deger)


def xls_oku(veri: bytes, asiri_ileti: str | None = None) -> list[list[str]]:
    """Excel 97-2003 (BIFF) ilk sayfa. Her bozukluk Türkçe OkumaHatasi'na döner (500 düşmesin).
    `asiri_ileti`: sayfa sınırı aşınca gösterilecek ileti (varsayılan öğrenci listesi iletisi)."""
    try:
        return _xls_oku(veri, asiri_ileti, None)
    except UnicodeDecodeError:
        # 0.21.0: kod sayfası kaydı olmayan eski (BIFF5) dosyada xlrd ASCII varsayar; Türkçe Excel'in kod sayfasıyla
        # yeniden denenir. BIFF8 metinleri Unicode'dur, bu yola düşmez.
        try:
            return _xls_oku(veri, asiri_ileti, "cp1254")
        except UnicodeDecodeError as hata:
            raise OkumaHatasi("Excel 97-2003 (.xls) dosyasının içeriği okunamadı; dosya bozuk olabilir.") from hata


def _xls_oku(veri: bytes, asiri_ileti: str | None, kodlama: str | None) -> list[list[str]]:
    import xlrd  # yerel: yalnız .xls yolunda yüklensin

    try:
        kitap = xlrd.open_workbook(file_contents=veri, on_demand=True, encoding_override=kodlama)
    except UnicodeDecodeError:
        raise
    except Exception as hata:  # xlrd bozuk kapta struct.error, IndexError, AssertionError da atar
        raise OkumaHatasi(XLS_BOZUK) from hata
    try:
        if kitap.nsheets == 0:
            raise OkumaHatasi("Excel dosyasında sayfa yok.")
        sayfa = kitap.sheet_by_index(0)
        if sayfa.nrows > SATIR_SINIRI * 3 or sayfa.ncols > 200:
            raise OkumaHatasi(asiri_ileti or f"Dosyada en çok {SATIR_SINIRI} öğrenci satırı olabilir.")
        return [[_sayi_metni(sayfa.cell_value(r, c)) for c in range(sayfa.ncols)] for r in range(sayfa.nrows)]
    except (OkumaHatasi, UnicodeDecodeError):
        raise
    except Exception as hata:
        raise OkumaHatasi("Excel 97-2003 (.xls) dosyasının içeriği okunamadı; dosya bozuk olabilir.") from hata
    finally:
        kitap.release_resources()


def matris_oku(veri: bytes, asiri_ileti: str | None = None) -> tuple[str, list[list[str]]]:
    """(biçim, satırlar). Biçim uzantıdan değil ilk baytlardan anlaşılır: OLE2 → .xls, ZIP → .xlsx, yoksa CSV.
    `asiri_ileti`: .xls sayfa sınırı aşılınca gösterilecek ileti (`xls_oku`; varsayılan öğrenci iletisi)."""
    if len(veri) > DOSYA_SINIRI:
        raise OkumaHatasi(f"Dosya en çok {DOSYA_SINIRI // (1024 * 1024)} MB olabilir.")
    if not veri:
        raise OkumaHatasi("Dosya boş.")
    if veri[:8] == OLE2:
        return "eokul_xls", xls_oku(veri, asiri_ileti)
    if veri[:4] == ZIP:
        try:
            return "xlsx", xlsx.oku(veri)
        except ValueError as hata:
            raise OkumaHatasi(str(hata) if "güvenli" in str(hata) or "parça" in str(hata) else XLSX_BOZUK) from hata
    try:
        basliklar, satirlar = metin.csv_oku(veri, DOSYA_SINIRI, SATIR_SINIRI * 2)
    except ValueError as hata:
        raise OkumaHatasi(str(hata)) from hata
    return "csv", [basliklar, *satirlar]


# ---- e-Okul blok düzleştirme -------------------------------------------------------------------
def blok_subesi(satir) -> str | None:
    """Satır bir şube bloğunun başlığıysa kanonik şube ('10/İ', 'Hazırlık/A'); değilse None.

    Eşleme ASCII'ye katlanmış metinde, şube harfi HAM metinden kesilir ('İ' 'I'ya çökmesin).
    """
    for hucre in satir:
        ham = _metin(hucre)
        if not ham:
            continue
        katli = _ascii_buyuk(ham)
        if len(katli) != len(ham):
            continue
        m = _BLOK.search(katli)
        if m:
            return metin.sube_duzelt(f"{int(m.group(1))}/{ham[m.start(2):m.end(2)]}")  # fmt: skip
        h = _HAZ_BLOK.search(katli)
        if h:
            return metin.sube_duzelt(f"Hazırlık/{ham[h.start(1):h.end(1)]}")  # fmt: skip
    return None


def _blok_baslik_mi(satir) -> bool:
    """Herhangi bir hücrede blok başlığı deseni var mı (şube çözülemese de)?"""
    for hucre in satir:
        katli = _ascii_buyuk(_metin(hucre))
        if _BLOK.search(katli) or _HAZ_BLOK.search(katli):
            return True
    return False


def _veri_basligi_mi(satir) -> bool:
    basliklar = {baslik_katla(h) for h in satir if _metin(h)}
    numarali = any(b in {"ogrenci no", "okul no", "ogrenci numarasi"} for b in basliklar)
    adli = any(b in {"adi", "adi soyadi", "soyadi", "ogrenci adi soyadi"} for b in basliklar)
    return numarali and adli


def _imza_mi(satir) -> bool:
    """Metinsel rapor imzası: sayaç dipnotu ('Toplam Öğrenci Sayısı') ya da rapor kodu ('OOG01001R020')."""
    for hucre in satir:
        katli = _ascii_buyuk(_metin(hucre))
        if katli and (_DIPNOT.search(katli) or _RAPOR_KODU.search(katli)):
            return True
    return False


def _yalniz_sayi(satir) -> bool:
    dolu = [_metin(h) for h in satir if _metin(h)]
    if not dolu:
        return False
    try:
        for h in dolu:
            float(h.replace(",", "."))
    except ValueError:
        return False
    return True


def sinif_listesi_mi(matris) -> bool:
    return any(_blok_baslik_mi(s) for s in matris)


def duzlestir(matris: list[list[str]]) -> tuple[list[list[str]], list[str]]:
    """Blok düzenli sınıf listesini tek başlıklı düz matrise indirger (satır sayısı korunur).

    Başlık/dipnot/ara satırlar boşaltılır, veri satırlarının başına bloğun şubesi eklenir.
    Başlığı çözülemeyen blok önceki şubeyi DEVRALMAZ (şube hücresi boş kalır, satır atlanır).
    """
    cikti: list[list[str]] = []
    sube = ""
    baslik_sonrasi = False
    ilk_baslik = False
    blok = veri = subesiz = 0
    for satir in matris:
        if _blok_baslik_mi(satir):
            sube = blok_subesi(satir) or ""
            blok += 1
            baslik_sonrasi = False
            cikti.append([])
            continue
        if _veri_basligi_mi(satir):
            baslik_sonrasi = True
            cikti.append([] if ilk_baslik else [SINIF_SUTUNU, *satir])
            ilk_baslik = True
            continue
        if _imza_mi(satir) or (not baslik_sonrasi and _yalniz_sayi(satir)):
            baslik_sonrasi = False
            sube = ""
            cikti.append([])
            continue
        if baslik_sonrasi and not _bos(satir):
            cikti.append([sube, *satir])
            veri += 1
            subesiz += 0 if sube else 1
            continue
        cikti.append([])
    if veri == 0:
        return matris, []
    notlar = [f"e-Okul sınıf listesi biçimi algılandı: {blok} şube bloğu, {veri} öğrenci satırı."]
    if subesiz:
        notlar.append(f"{subesiz} satırın bloğunda şube başlığı çözülemedi; bu satırlar atlandı.")
    return cikti, notlar


def dipnot_temizle(matris: list[list[str]]) -> tuple[list[list[str]], list[str]]:
    """Düz tabloda e-Okul imzası varsa sayaç/rapor kodu/yalnız-sayı satırlarını boşaltır."""
    if not any(_imza_mi(s) for s in matris):
        return matris, []
    cikti, n = [], 0
    for s in matris:
        if not _bos(s) and (_imza_mi(s) or _yalniz_sayi(s)):
            cikti.append([])
            n += 1
        else:
            cikti.append(list(s))
    return cikti, ([f"e-Okul rapor dipnotu olarak {n} satır atlandı."] if n else [])


# ---- başlık eşleme ve satır ayrıştırma ---------------------------------------------------------
def _alan(norm: str) -> str | None:
    for alan, esler in ES_ANLAMLILAR:
        for es in esler:
            if es == norm or es in norm:
                return alan
    return None


def _kimlik_sutunu_mu(norm: str) -> bool:
    return "kimlik" in norm or norm.startswith(("t c ", "tc ")) or norm in ("tc", "t c", "tckn")


def baslik_esle(matris: list[list[str]], alan_bul=None, kullanilir_mi=None) -> tuple[int, dict[str, int], list[str]]:
    """İlk 20 satırda en iyi başlık satırı. (satır sırası, {alan: sütun}, okunmayan sütun adları).

    `alan_bul` (katlanmış başlık → alan adı ya da None) ve `kullanilir_mi` ({alan: sütun} → bool) verilmezse
    öğrenci listesinin eş anlamlıları kullanılır (0.21.0: öğretmen listesi `ogretmen_aktar` kendi eşlemesini verir).
    T.C. kimlik sütunu her durumda hiçbir alana eşlenmez."""
    alan_bul = alan_bul or _alan
    kullanilir_mi = kullanilir_mi or _kullanilir
    en_iyi: tuple[int, dict[str, int], list[str]] | None = None
    for r in range(min(BASLIK_TARAMA, len(matris))):
        alanlar: dict[str, int] = {}
        okunmayan: list[str] = []
        for i, h in enumerate(matris[r]):
            norm = baslik_katla(h)
            if not norm:
                continue
            alan = None if _kimlik_sutunu_mu(norm) else alan_bul(norm)
            if alan and alan not in alanlar:
                alanlar[alan] = i
            elif not alan:
                okunmayan.append(_metin(h)[:40])
        if not alanlar:
            continue
        kullanilir = kullanilir_mi(alanlar)
        if en_iyi is None or (kullanilir, len(alanlar)) > (kullanilir_mi(en_iyi[1]), len(en_iyi[1])):
            en_iyi = (r, alanlar, okunmayan)
        if kullanilir:
            break
    return en_iyi or (0, {}, [])


def _kullanilir(alanlar: dict[str, int]) -> bool:
    return "sube" in alanlar and "okul_no" in alanlar and ("ad_soyad" in alanlar or ("ad" in alanlar and "soyad" in alanlar))


def _ad(s) -> str:
    return " ".join(_metin(s).split())[:AD_EN_UZUN]


def _okul_no(s) -> str:
    no = _metin(s)
    if no.endswith(".0") and metin.rakam_mi(no[:-2]):
        no = no[:-2]
    return no


def ogrenci_listesi_oku(veri: bytes) -> dict:
    """Dosyayı ayrıştırır. Döndürür:
    {"bicim", "bicim_adi", "notlar": [..], "uyarilar": [..], "satirlar": [{"satir","sube","okul_no","ad","soyad"}],
     "atlanan": [{"satir","neden"}]}. Başlık bulunamazsa OkumaHatasi.
    """
    bicim, matris = matris_oku(veri)
    if sinif_listesi_mi(matris):
        matris, notlar = duzlestir(matris)
    else:
        matris, notlar = dipnot_temizle(matris)
    r, alanlar, okunmayan = baslik_esle(matris)
    if not _kullanilir(alanlar):
        raise OkumaHatasi(
            "Dosyada şube, okul no ve ad-soyad sütunları bulunamadı. e-Okul'un sınıf listesini (OOG01001R020) "
            "ya da 'Sınıf/Şube; Okul No; Adı; Soyadı' başlıklı bir tablo yükleyin."
        )
    uyarilar = []
    if any(_kimlik_sutunu_mu(baslik_katla(h)) for h in matris[r]):
        uyarilar.append("T.C. Kimlik No sütunu bulundu, okunmadı.")
    okunmayan = [o for o in okunmayan if o and not _kimlik_sutunu_mu(baslik_katla(o)) and o != SINIF_SUTUNU]
    if okunmayan:
        uyarilar.append("Okunmayan sütunlar: " + ", ".join(dict.fromkeys(okunmayan)) + ".")

    def hucre(satir, alan):
        i = alanlar.get(alan)
        return satir[i] if i is not None and i < len(satir) else ""

    adaylar, atlanan = [], []
    for i in range(r + 1, len(matris)):
        satir = matris[i]
        if _bos(satir):
            continue
        no_satir = i + 1
        if len(adaylar) >= SATIR_SINIRI:
            raise OkumaHatasi(f"Dosyada en çok {SATIR_SINIRI} öğrenci satırı olabilir.")
        okul_no = _okul_no(hucre(satir, "okul_no"))
        if "ad_soyad" in alanlar and _ad(hucre(satir, "ad_soyad")):
            parcalar = _ad(hucre(satir, "ad_soyad")).split()
            ad, soyad = (" ".join(parcalar[:-1]), parcalar[-1]) if len(parcalar) > 1 else (parcalar[0], "")
        else:
            ad, soyad = _ad(hucre(satir, "ad")), _ad(hucre(satir, "soyad"))
        sube = metin.sube_duzelt(hucre(satir, "sube"))
        if not okul_no:
            atlanan.append({"satir": no_satir, "neden": "okul no boş"})
        elif not metin.rakam_mi(okul_no) or len(okul_no) > OKUL_NO_EN_UZUN:
            atlanan.append({"satir": no_satir, "neden": "okul no rakam dışı karakter içeriyor"})
        elif not ad and not soyad:
            atlanan.append({"satir": no_satir, "neden": "ad ve soyad boş"})
        elif not sube:
            atlanan.append({"satir": no_satir, "neden": "şube çözülemedi"})
        else:
            adaylar.append({"satir": no_satir, "sube": sube, "okul_no": okul_no, "ad": ad, "soyad": soyad})
    sayac: dict[str, int] = {}
    for a in adaylar:
        sayac[a["okul_no"]] = sayac.get(a["okul_no"], 0) + 1
    satirlar = []
    for a in adaylar:
        if sayac[a["okul_no"]] > 1:
            atlanan.append({"satir": a["satir"], "neden": "aynı okul no dosyada birden çok kez geçiyor"})
        else:
            satirlar.append(a)
    atlanan.sort(key=lambda x: x["satir"])
    return {"bicim": bicim, "bicim_adi": BICIM_ADI[bicim], "notlar": notlar, "uyarilar": uyarilar,
            "satirlar": satirlar, "atlanan": atlanan}  # fmt: skip
