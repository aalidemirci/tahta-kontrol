"""e-Okul "Haftalık Ders Programları" raporu (OOK11002_R01, .XLS) — ders programı içe aktarmanın beşinci kaynağı (0.12.0).

Rapor yerleşimi (gerçek bir örnekten gözlendi; örnek dosya depoda YOKTUR, testler uydurma matrisle çalışır):

- İlk satırlarda gün başlıkları: her gün bir sütunda ("PAZARTESİ", "SALI", "ÇARSAMBA" (Ş'siz yazım da olur), …).
- Sonra şube blokları art arda gelir; blok başlığı yoktur ve **şube adı raporda hiç yoktur**. Her satır bir ders
  saatidir: 1. sütun ders no (1, 2, …), 2. sütun saat aralığı ("13:30-14:05"), gün sütunlarında o saatin hücresi.
  Ders no 1'e (ya da öncekine eşit/küçük bir sayıya) dönünce yeni blok başlar.
- Dolu hücre çoğunlukla iki satırdır: "DERS ADI\\nÖĞRETMEN ADI" (seçmelide "SEÇMELİ DERS\\nÖĞRETMEN - DERS ADI");
  boş hücre = o saatte dersi yok. Ders no'su olmayan satırlar (rapor altbilgisi) atlanır.
- Derslik bilgisi yoktur: şubenin dersi şubenin kendi tahtasına (`tahta.subeler`) yazılır.

KVKK: hücrelerden YALNIZ "dolu mu" bilgisi alınır. Öğretmen adı (hücrenin ikinci ve sonraki satırları) hiç
saklanmaz, gösterilmez; ders adı da programa girmez. Eşleme ekranında blokları tanımaya yardım etsin diye blok başına
en çok `IPUCU_SAYISI` "Pzt 1: DERS ADI" ipucu (iki satırlı hücrenin İLK satırı) önizleme kaydında durur; önizleme
30 dakikada (`program_is.onizleme_temizle`) ya da onay/vazgeçte silinir. Tek satırlı hücreden ipucu alınmaz
(öğretmen adı olmadığı kesin değildir).

Saf işlevler; veritabanına yazmaz (zil çizelgesi yazımı `zil_yaz`, çağıran işlemin içinde).
"""

from __future__ import annotations

import re
from collections import Counter

from . import cizelge, eokul, guvenlik, metin, program, vt, xlsx, zamanlama

RAPOR_ADI = "Haftalık Ders Programları (OOK11002_R01)"
EN_COK_BAYT = 2 * 1024 * 1024
EN_COK_SATIR = 5000
EN_COK_SUTUN = 60
EN_COK_BLOK = 300
BASLIK_TARAMA = 10
IPUCU_SAYISI = 3
IPUCU_EN_UZUN = 40
SAAT_TOLERANS_DK = 5
SUBE_LISTESI_EN_COK = 64 * 1024
SUBE_LISTESI_EN_COK_OGE = 400

DEGIL = "Bu dosya e-Okul “Haftalık Ders Programları” raporuna benzemiyor: gün başlıkları bulunamadı."
PDF_DEGIL = "PDF okunmaz. e-Okul'da raporu Excel olarak kaydedip .XLS dosyasını yükleyin; PDF'i şube sırasını doğrulamak için kullanın."
BICIM_DEGIL = "e-Okul raporunu Excel (.XLS) olarak kaydedip yükleyin."
BUYUK = "Dosya beklenenden büyük; e-Okul'dan yalnız “Haftalık Ders Programları” raporunu kaydedin."
TC_RET = "Dosyada kimlik numarasına benzeyen değer var; silip yeniden yükleyin."

_GUN_ADLARI = {"pazartesi": 0, "sali": 1, "carsamba": 2, "persembe": 3, "cuma": 4, "cumartesi": 5, "pazar": 6}
_SAAT = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s*[-–—]\s*(\d{1,2})[:.](\d{2})\s*$")
_DERS_NO = re.compile(r"^\s*(\d{1,2})(?:[.,]0*)?\s*\.?\s*$")
_KONTROL = re.compile(r"[\x00-\x1f\x7f]")
# "AL - 9. Sınıf / A Şubesi", "9. Sınıf A Şubesi", "Hazırlık Sınıfı / B Şubesi" (küçük harfe çevrilmiş metinde)
_PDF_SUBE = re.compile(r"(hazırlık|hazirlik|\d{1,2})\s*\.?\s*(?:sınıf|sinif)\w*\s*/?\s*([a-zçğıöşü])\s*şube")


# ==== 1. Dosya → satır matrisi ===========================================================================
def matris_oku(bayt: bytes) -> list[list[str]]:
    """İlk baytlardan biçim: OLE2 → .xls (xlrd), ZIP → .xlsx. PDF ve diğerleri Türkçe iletiyle ValueError.
    Dosya diske yazılmaz; xlrd'nin her hatası `eokul.xls_oku` içinde yakalanır."""
    if len(bayt) > EN_COK_BAYT:
        raise ValueError(f"Dosya en çok {EN_COK_BAYT // (1024 * 1024)} MB olabilir.")
    if not bayt.strip():
        raise ValueError("Dosya boş.")
    if bayt[:5] == b"%PDF-":
        raise ValueError(PDF_DEGIL)
    if bayt[:8] == eokul.OLE2:
        try:
            satirlar = eokul.xls_oku(bayt, asiri_ileti=BUYUK)
        except eokul.OkumaHatasi as hata:
            raise ValueError(str(hata)) from hata
    elif bayt[:4] == eokul.ZIP:
        try:
            satirlar = xlsx.oku(bayt)
        except ValueError as hata:
            raise ValueError("Excel (.xlsx) dosyası okunamadı; e-Okul'dan .XLS olarak yeniden kaydedin.") from hata
    else:
        raise ValueError(BICIM_DEGIL)
    if len(satirlar) > EN_COK_SATIR or any(len(s) > EN_COK_SUTUN for s in satirlar):
        raise ValueError(BUYUK)
    return [[str(h if h is not None else "") for h in s] for s in satirlar]


# ==== 2. Ayrıştırma ======================================================================================
def _gun(hucre: str) -> int | None:
    return _GUN_ADLARI.get(metin.katla(hucre).strip(" .:"))


def _ipucu(hucre: str) -> str | None:
    """İki (ya da daha çok) satırlı hücrenin İLK satırı (ders adı); tek satırlı hücreden ipucu yok."""
    satirlar = [s for s in (" ".join(_KONTROL.sub(" ", x).split()) for x in str(hucre).splitlines()) if s]
    if len(satirlar) < 2:
        return None
    return satirlar[0][:IPUCU_EN_UZUN]


def rapor_oku(matris: list[list[str]]) -> dict:
    """Rapor matrisini bloklara ayırır (saf işlev). Okunamazsa Türkçe iletiyle ValueError.

    Döndürür {"bloklar": [{"no", "satir" (Excel satırı), "dersler": [[no, bas, bit]], "dolu": [[gun, no]],
    "bos": n, "ipucu": [metin]}], "gunler": [gun], "hatalar": [..], "hata_sayisi", "uyarilar": [..],
    "atlanan_satir", "dolu_sayisi", "bos_sayisi"}. Öğretmen ve ders adı (ipucu dışında) dönmez.
    """
    for satir in matris:
        for h in satir:
            if guvenlik.tc_kimlik_var(h):
                raise ValueError(TC_RET)
    baslik = None
    sutunlar: dict[int, int] = {}
    for r, satir in enumerate(matris[:BASLIK_TARAMA]):
        adaylar = {c: g for c, h in enumerate(satir) if (g := _gun(h)) is not None}
        if len(adaylar) >= 2 and len(set(adaylar.values())) == len(adaylar):
            baslik, sutunlar = r, adaylar
            break
    if baslik is None:
        raise ValueError(DEGIL)
    bloklar: list[dict] = []
    hatalar: list[str] = []
    uyarilar: list[str] = []
    atlanan = 0
    onceki = 0
    blok: dict | None = None
    for r in range(baslik + 1, len(matris)):
        satir = matris[r]
        hucre0 = satir[0] if satir else ""
        e = _DERS_NO.match(hucre0)
        if not e or not 1 <= int(e.group(1)) <= 20:
            if any(str(h).strip() for h in satir):
                atlanan += 1  # altbilgi ya da tanınmayan satır: hiçbir hücresi okunmaz
            continue
        no = int(e.group(1))
        if blok is None or no <= onceki:
            if len(bloklar) >= EN_COK_BLOK:
                raise ValueError(f"Raporda en çok {EN_COK_BLOK} şube bloğu olabilir.")
            blok = {"no": len(bloklar) + 1, "satir": r + 1, "dersler": [], "dolu": [], "bos": 0, "ipucu": []}
            bloklar.append(blok)
            if no != 1:
                uyarilar.append(f"{blok['no']}. blok {no}. dersle başlıyor (Excel satırı {r + 1}).")
        onceki = no
        s = _SAAT.match(satir[1] if len(satir) > 1 else "")
        bas = program.saat_dogrula(f"{s.group(1)}:{s.group(2)}") if s else None
        bit = program.saat_dogrula(f"{s.group(3)}:{s.group(4)}") if s else None
        if not bas or not bit or program.dk(bit) <= program.dk(bas):
            hatalar.append(f"Excel satırı {r + 1}: {blok['no']}. blok {no}. dersin saat aralığı okunamadı; satır atlandı.")
            continue
        blok["dersler"].append([no, bas, bit])
        for c, gun in sorted(sutunlar.items(), key=lambda x: x[1]):
            hucre = satir[c] if c < len(satir) else ""
            if not str(hucre).strip():
                blok["bos"] += 1
                continue
            blok["dolu"].append([gun, no])
            if len(blok["ipucu"]) < IPUCU_SAYISI and (ip := _ipucu(hucre)):
                blok["ipucu"].append(f"{zamanlama.GUN_KISA[gun]} {no}: {ip}")
    bloklar = [b for b in bloklar if b["dersler"]]
    if not bloklar:
        raise ValueError("Raporda ders saati satırı bulunamadı; e-Okul'dan “Haftalık Ders Programları” raporunu kaydedin.")
    return {
        "bloklar": bloklar,
        "gunler": sorted(set(sutunlar.values())),
        "hatalar": hatalar[: program.HATA_GOSTERIM],
        "hata_sayisi": len(hatalar),
        "uyarilar": uyarilar[: program.HATA_GOSTERIM],
        "atlanan_satir": atlanan,
        "dolu_sayisi": sum(len(b["dolu"]) for b in bloklar),
        "bos_sayisi": sum(b["bos"] for b in bloklar),
    }


# ==== 3. Devreler ve zil çizelgesi =======================================================================
def devre_gruplari(bloklar: list[dict]) -> list[dict]:
    """Blokları ilk dersin başlangıcına göre (±5 dk) devre gruplarına ayırır; başlangıca göre sıralı.

    [{"anahtar": "g1", "bas", "bit", "dersler": [(no, bas, bit)] (her no için en sık saat), "bloklar": [blok no]}]."""
    gruplar: list[dict] = []
    for b in sorted(bloklar, key=lambda b: (program.dk(b["dersler"][0][1]), b["no"])):
        ilk = program.dk(b["dersler"][0][1])
        g = next((g for g in gruplar if abs(g["_ilk"] - ilk) <= SAAT_TOLERANS_DK), None)
        if g is None:
            g = {"_ilk": ilk, "_saatler": {}, "bloklar": []}
            gruplar.append(g)
        g["bloklar"].append(b["no"])
        for no, bas, bit in b["dersler"]:
            g["_saatler"].setdefault(no, Counter())[(bas, bit)] += 1
    sonuc = []
    for i, g in enumerate(gruplar, start=1):
        dersler = [(no, *sayac.most_common(1)[0][0]) for no, sayac in sorted(g["_saatler"].items())]
        sonuc.append({"anahtar": f"g{i}", "bas": dersler[0][1], "bit": max(d[2] for d in dersler), "dersler": dersler,
                      "bloklar": sorted(g["bloklar"])})  # fmt: skip
    return sonuc


def devre_esle(gruplar: list[dict], saatler: list[tuple]) -> dict[str, dict]:
    """Grup → zil çizelgesindeki devre: ilk dersin başlangıcı ±5 dk tutan devreler arasından en çok dersi tutan.

    {anahtar: {"devre": kimlik | None, "devre_adi", "farkli": tutmayan ders sayısı, "farkli_dersler": [(no, bas)]}}."""
    devreler: dict[str, dict[int, set[int]]] = {}
    adlar: dict[str, str] = {}
    for _g, devre, adi, no, bas, _b in saatler:
        devreler.setdefault(devre, {}).setdefault(no, set()).add(program.dk(bas))
        adlar.setdefault(devre, adi)
    sonuc = {}
    for g in gruplar:
        en_iyi: tuple[str, int] | None = None
        for devre in sorted(devreler):
            def tutar(no: int, bas: str, devre=devre) -> bool:
                return any(abs(x - program.dk(bas)) <= SAAT_TOLERANS_DK for x in devreler[devre].get(no, ()))

            ilk_no, ilk_bas, _ = g["dersler"][0]
            if not tutar(ilk_no, ilk_bas):
                continue
            puan = sum(1 for no, bas, _b in g["dersler"] if tutar(no, bas))
            if en_iyi is None or puan > en_iyi[1]:
                en_iyi = (devre, puan)
        if en_iyi:
            devre = en_iyi[0]
            farkli = [(no, bas) for no, bas, _b in g["dersler"]
                      if not any(abs(x - program.dk(bas)) <= SAAT_TOLERANS_DK for x in devreler[devre].get(no, ()))]  # fmt: skip
            sonuc[g["anahtar"]] = {"devre": devre, "devre_adi": adlar[devre], "farkli": len(farkli), "farkli_dersler": farkli}
        else:
            sonuc[g["anahtar"]] = {"devre": None, "devre_adi": "", "farkli": len(g["dersler"]), "farkli_dersler": []}
    return sonuc


def mevcut_devreler(saatler: list[tuple]) -> list[tuple[str, str]]:
    """Zil çizelgesindeki devreler [(kimlik, ad)], en erken başlangıca göre sıralı."""
    ilk: dict[str, tuple[int, str]] = {}
    for _g, devre, adi, _no, bas, _b in saatler:
        dk = program.dk(bas)
        if devre not in ilk or dk < ilk[devre][0]:
            ilk[devre] = (dk, adi)
    return [(d, ilk[d][1]) for d in sorted(ilk, key=lambda d: (ilk[d][0], d))]


def zil_onerisi(gruplar: list[dict], gunler: list[int], mevcut: list[tuple[str, str]] | None = None) -> dict | None:
    """Rapordaki saatlerden zil çizelgesi önerisi: tek grup → Normal, iki grup → Sabah + Öğleden sonra.
    Zil çizelgesinde aynı sayıda devre varsa onların kimlik ve adları kullanılır (başlangıç sırasıyla): devre kimliği
    değişmesin, mevcut derslik programı karşılıksız (yetim) kalmasın.

    {"dersler": [(devre, devre_adi, no, bas, bit)], "gunler", "gun_metni", "devreler": [{"ad","sayi","aralik","saatler"}],
    "hatalar": [..], "mevcut_kimlikler": bool} ya da (ikiden çok grup, hiç grup yok) None."""
    if not gruplar or len(gruplar) > 2 or not gunler:
        return None
    mevcut_kimlikler = bool(mevcut) and len(mevcut) == len(gruplar)
    if mevcut_kimlikler:
        kimlikler = list(mevcut)
    else:
        kimlikler = [("normal", "Normal")] if len(gruplar) == 1 else [("sabah", "Sabah"), ("ogle", "Öğleden sonra")]
    dersler = []
    ozet = []
    for (devre, adi), g in zip(kimlikler, gruplar, strict=True):
        satirlar = [(devre, adi, no, bas, bit) for no, bas, bit in g["dersler"]]
        dersler.extend(satirlar)
        ozet.append({"ad": adi, "sayi": len(satirlar), "aralik": f"{g['bas']}–{g['bit']}",
                     "saatler": ", ".join(f"{no}. {bas}–{bit}" for no, bas, bit in g["dersler"])})  # fmt: skip
    taslak = cizelge.dersler_taslaga("e-Okul", dersler)
    hatalar, _ = cizelge.dogrula(taslak)
    # Numaralar rapordakiyle aynı kalmalı (1'den ardışık); değilse çizelge numaraları kayar.
    for devre, _adi in kimlikler:
        nolar = sorted(d[2] for d in dersler if d[0] == devre)
        if nolar != list(range(1, len(nolar) + 1)):
            hatalar.append({"metin": "Rapordaki ders numaraları 1'den ardışık değil; zil çizelgesini elle girin.", "alan": None})
            break
    return {"dersler": dersler, "gunler": gunler, "gun_metni": cizelge.gun_araligi(gunler), "devreler": ozet,
            "hatalar": [h["metin"] for h in hatalar], "mevcut_kimlikler": mevcut_kimlikler}  # fmt: skip


def zil_etkisi(b, oneri: dict) -> dict:
    """Öneri uygulanırsa ne olur (kuru çalıştırma; veritabanına yazmaz): onay kutusunun üstünde gösterilir.

    {"atamalar": ["Pzt–Per: Normal", "Cum: Cuma"] (rapordaki günlerin şu anki çizelgeleri; yeni çizelge bunların yerini
    alır), "yetim_satir", "yetim_tahta" (şu an karşılığı olan ama yeni çizelgede karşılığı kalmayacak derslik programı
    satırları: devre adı/numarası değişirse)}."""
    gunler = sorted(set(int(g) for g in oneri["gunler"]))
    yer = ",".join("?" * len(gunler))
    cizelgeye: dict[str, list[int]] = {}
    for s in b.execute(
        f"SELECT h.gun, c.ad FROM zil_haftalik h JOIN zil_cizelgesi c ON c.id = h.cizelge_id WHERE h.gun IN ({yer})",
        gunler,
    ):
        cizelgeye.setdefault(s["ad"], []).append(int(s["gun"]))
    atamalar = [f"{cizelge.gun_araligi(g)}: {ad}" for ad, g in sorted(cizelgeye.items(), key=lambda x: min(x[1]))]
    yeni = {(d[0], int(d[2])) for d in oneri["dersler"]}
    yetim_tahta: set[int] = set()
    yetim_satir = 0
    for s in b.execute(
        f"SELECT d.tahta_id, d.devre, d.ders_no FROM tahta_ders d WHERE d.gun IN ({yer}) AND EXISTS (SELECT 1 FROM "
        "ders_saati s WHERE s.gun = d.gun AND s.devre = d.devre AND s.ders_no = d.ders_no)",
        gunler,
    ):
        if (s["devre"], int(s["ders_no"])) not in yeni:
            yetim_satir += 1
            yetim_tahta.add(int(s["tahta_id"]))
    return {"atamalar": atamalar, "yetim_satir": yetim_satir, "yetim_tahta": len(yetim_tahta)}


def zil_yaz(b, oneri: dict, kullanici: str) -> tuple[int, str]:
    """Öneriyi yeni bir çizelge olarak yazar (kaynak 'eokul') ve rapordaki günlere haftalık düzende atar;
    `ders_saati` yeniden yazılır. Diğer günler ve mevcut çizelgeler değişmez. (çizelge id, ad)."""
    ad = cizelge.benzersiz_ad(b, "e-Okul · " + oneri["gun_metni"])
    kimlik = cizelge.cizelge_ekle(b, ad, [tuple(d) for d in oneri["dersler"]], "eokul", kullanici)
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


# ==== 4. Şube listesi ve öneriler ========================================================================
def sube_sira_anahtari(sube: str) -> tuple:
    """Hazırlık, 9, 10, 11, 12; harf Türk abecesiyle (… H, I, İ, J …). Python'un kod noktası sırası KULLANILMAZ
    (o sırada İ, Z'den sonra gelir)."""
    duzey, _, harf = str(sube).partition("/")
    return (0 if duzey == "Hazırlık" else int(duzey) if metin.rakam_mi(duzey) else 99, metin.tr_sirala_anahtari(harf))


def sube_listesi_coz(ham: str) -> tuple[list[str], list[str]]:
    """Yapıştırılan sıralı şube listesi → (kanonik şubeler, uyarılar). Ayraç virgül, noktalı virgül, sekme ya da
    satır sonu; "9/A", "9-A", "9A" ve PDF başlığı biçimi ("AL - 9. Sınıf / A Şubesi") kabul edilir. Tanınmayan
    parçalar atlanır (sayısı uyarıda; metinleri saklanmaz), tekrar eden şube bir kez alınır."""
    if len(ham.encode("utf-8")) > SUBE_LISTESI_EN_COK:
        raise ValueError(f"Şube listesi en çok {SUBE_LISTESI_EN_COK // 1024} KB olabilir.")
    sonuc: list[str] = []
    taninmayan = 0
    tekrar = 0
    for parca in re.split(r"[,;\t\r\n]+", ham):
        if not parca.strip():
            continue
        kucuk = metin.tr_kucuk(" ".join(parca.split()))
        e = _PDF_SUBE.search(kucuk)
        sube = metin.sube_duzelt(f"{e.group(1)}/{e.group(2)}") if e else metin.sube_duzelt(parca)
        if not sube:
            taninmayan += 1
            continue
        if sube in sonuc:
            tekrar += 1
            continue
        sonuc.append(sube)
        if len(sonuc) > SUBE_LISTESI_EN_COK_OGE:
            raise ValueError(f"Şube listesinde en çok {SUBE_LISTESI_EN_COK_OGE} şube olabilir.")
    uyarilar = []
    if taninmayan:
        uyarilar.append(f"Listede şube olarak anlaşılamayan {taninmayan} parça atlandı.")
    if tekrar:
        uyarilar.append(f"Listede {tekrar} şube iki kez geçiyordu; bir kez alındı.")
    return sonuc, uyarilar


def sistem_subeleri(b) -> list[str]:
    """Sistemde kayıtlı şubeler (tahtaların şubeleri + etkin öğrenci listesi), düzey ve Türk abecesi sırasıyla."""
    subeler: set[str] = set()
    for t in b.execute("SELECT subeler FROM tahta WHERE durum != 'iptal'"):
        subeler.update(p for p in str(t["subeler"] or "").split(",") if p)
    for s in b.execute("SELECT DISTINCT sube FROM ogrenci WHERE aktif = 1"):
        if s["sube"]:
            subeler.add(s["sube"])
    return sorted((s for s in subeler if metin.sube_duzelt(s) == s), key=sube_sira_anahtari)


def hatirlanan_bloklar(hatirlanan: dict, blok_sayisi: int) -> dict[int, str] | None:
    """Önceki onaydaki blok → şube eşlemesi; blok sayısı değiştiyse (şube eklenmiş/kapanmış olabilir) None."""
    sayi = hatirlanan.get(("blok_sayisi", "-"))
    if not sayi or str(sayi["deger"]) != str(blok_sayisi):
        return None
    sonuc = {}
    for (tur, anahtar), h in hatirlanan.items():
        if tur == "blok" and metin.rakam_mi(anahtar):
            sonuc[int(anahtar)] = str(h["deger"] or "")
    return sonuc


KAYNAK_ADI = {"liste": "yapıştırdığınız listede", "hatirlanan": "önceki aktarımda", "sistem": "sistemde kayıtlı", "": ""}


def blok_subeleri(bloklar: list[dict], secimler: dict, hatirlanan: dict, sistem: list[str]) -> dict:
    """Her blok için şube önerisi ve durum. Öncelik: bu oturumda seçilen > yapıştırılan liste > önceki onayda
    hatırlanan (blok sayısı aynıysa) > sistemdeki şubeler (sırayla) > boş.

    {"atama": {blok no: şube ('' = atlanır)}, "durum": {blok no: secildi|liste|hatirlanan|sistem|eslesmedi},
    "kaynak": liste|hatirlanan|sistem|'', "kaynak_sayisi", "ciftler": {şube: [blok no]}, "uyarilar": [..]}."""
    secili = secimler.get("blok") or {}
    liste = [s for s in (secimler.get("sube_listesi") or []) if isinstance(s, str)]
    eski = hatirlanan_bloklar(hatirlanan, len(bloklar))
    if liste:
        kaynak, sira = "liste", liste
    elif eski:
        kaynak, sira = "hatirlanan", [eski.get(b["no"], "") for b in bloklar]
    elif sistem:
        kaynak, sira = "sistem", sistem
    else:
        kaynak, sira = "", []
    atama: dict[int, str] = {}
    durum: dict[int, str] = {}
    for i, b in enumerate(bloklar):
        if str(b["no"]) in secili:
            atama[b["no"]], durum[b["no"]] = str(secili[str(b["no"])] or ""), "secildi"
        elif i < len(sira) and (kaynak == "hatirlanan" or sira[i]):
            atama[b["no"]], durum[b["no"]] = sira[i], kaynak
        else:
            atama[b["no"]], durum[b["no"]] = "", "eslesmedi"
    uyarilar = []
    if kaynak in ("liste", "sistem") and len(sira) != len(bloklar):
        uyarilar.append(
            f"Raporda {len(bloklar)} blok var, {KAYNAK_ADI[kaynak]} {len(sira)} şube var: sıra kayabilir. "
            "Her bloğun şubesini e-Okul PDF'indeki sayfa sırasıyla karşılaştırın."
        )
    elif not kaynak:
        uyarilar.append("Sistemde kayıtlı şube yok: şube listesini PDF'teki sırayla yapıştırın ya da her bloğa şube yazın.")
    gorulen: dict[str, list[int]] = {}
    for no, sube in atama.items():
        if sube:
            gorulen.setdefault(sube, []).append(no)
    ciftler = {s: n for s, n in gorulen.items() if len(n) > 1}
    return {"atama": atama, "durum": durum, "kaynak": kaynak, "kaynak_sayisi": len(sira), "ciftler": ciftler,
            "uyarilar": uyarilar}  # fmt: skip


# ==== 5. Ara biçim ve önizleme ===========================================================================
def onizleme_verisi(bayt_ozeti: str, rapor: dict) -> dict:
    """`program_onizleme` (tur='aktar') verisi. Öğretmen adı yok; ders adı yalnız ipucu olarak (30 dk)."""
    return {
        "kaynak": "eokul",
        "bicim": "eokul",
        "ozet": {"sha256": bayt_ozeti, "satir_sayisi": None, "kart_sayisi": None, "blok_sayisi": len(rapor["bloklar"])},
        "eokul": rapor,
        "asc": None,
        "ara": None,
        "bilgi": None,
        "kaynak_hatalari": rapor["hatalar"],
        "kaynak_hata_sayisi": rapor["hata_sayisi"],
        "kaynak_uyarilari": rapor["uyarilar"],
        "secimler": {"derslik": {}, "sinif": {}, "saat": {}, "sube": {}, "blok": {}, "sube_listesi": [], "donem": "",
                     "devre_secimi": ""},  # fmt: skip
    }


def hazirla(rapor: dict, saatler: list[tuple], secimler: dict, hatirlanan: dict, sistem: list[str]) -> dict:
    """Rapor + seçimler → `program_aktar.esle` girdisi ve eşleme ekranının satırları (saf işlev).

    Döndürür {"girdi": {"kaynak": "eokul", "ara", "bilgi"}, "uyarilar", "bloklar": [eşleme satırı], "gruplar",
    "devreler": {anahtar: {...}}, "zil_onerisi", "zil_gerekli", "ciftler", "kaynak", "kaynak_sayisi",
    "sayilar": {"blok","atanan","atlanan","devresiz","dolu","bos"}, "devre_dagilimi": [(ad, blok sayısı)]}."""
    bloklar = rapor["bloklar"]
    gruplar = devre_gruplari(bloklar)
    devreler = devre_esle(gruplar, saatler)
    blok_grubu = {no: g["anahtar"] for g in gruplar for no in g["bloklar"]}
    oneri = blok_subeleri(bloklar, secimler, hatirlanan, sistem)
    uyarilar = list(oneri["uyarilar"])
    ara: list[dict] = []
    bilgi: dict = {"derslik": {}, "sinif": {}, "saat": {}}
    satirlar = []
    sayilar = {"blok": len(bloklar), "atanan": 0, "atlanan": 0, "devresiz": 0, "dolu": 0, "bos": 0}
    grup_adi = {}
    for i, g in enumerate(gruplar, start=1):
        d = devreler[g["anahtar"]]
        grup_adi[g["anahtar"]] = d["devre_adi"] or (f"{i}. devre" if len(gruplar) > 1 else "Devre")
    for b in bloklar:
        g = blok_grubu[b["no"]]
        d = devreler[g]
        sube = oneri["atama"][b["no"]]
        satirlar.append({"anahtar": str(b["no"]), "no": b["no"], "devre_adi": grup_adi[g],
                         "saat": f"{b['dersler'][0][1]}–{b['dersler'][-1][2]}", "ders_sayisi": len(b["dersler"]),
                         "dolu": len(b["dolu"]), "ipucu": list(b.get("ipucu") or []), "deger": sube,
                         "durum": oneri["durum"][b["no"]], "cift": sube in oneri["ciftler"]})  # fmt: skip
        if not sube:
            sayilar["atlanan"] += 1
            continue
        if not d["devre"]:
            sayilar["devresiz"] += 1
            continue
        sayilar["atanan"] += 1
        if sube in oneri["ciftler"]:
            continue  # aynı şube iki blokta: hiçbiri yazılmaz (onay kapalı)
        sayilar["dolu"] += len(b["dolu"])
        sayilar["bos"] += b["bos"]
        bilgi["sinif"].setdefault(sube, {"ad": sube, "adaylar": [sube]})
        for gun, no in b["dolu"]:
            anahtar = f"{d['devre']}|{no}"
            bilgi["saat"].setdefault(anahtar, {"period": str(no), "ad": f"{d['devre_adi']} · {no}. ders", "bas": "", "bit": ""})
            ara.append({"d": "", "s": [sube], "g": int(gun), "p": anahtar, "n": b["no"]})
    for sube, nolar in sorted(oneri["ciftler"].items(), key=lambda x: sube_sira_anahtari(x[0])):
        uyarilar.append(f"{sube} şubesi {', '.join(map(str, nolar))}. bloklara atanmış; bir şube yalnız bir bloğa atanabilir.")
    zil_gerekli = not saatler or any(not devreler[g["anahtar"]]["devre"] or devreler[g["anahtar"]]["farkli"] for g in gruplar)
    oneri_zil = zil_onerisi(gruplar, rapor["gunler"], mevcut_devreler(saatler)) if zil_gerekli else None
    olusturulabilir = bool(oneri_zil and not oneri_zil["hatalar"])
    zil_onerilemez = ""
    if zil_gerekli and not olusturulabilir:
        if len(gruplar) > 2:
            zil_onerilemez = (f"Raporda {len(gruplar)} farklı başlangıç saati var ("
                              + ", ".join(g["bas"] for g in gruplar)
                              + "); otomatik zil çizelgesi en çok iki devre için oluşturulur. "
                              "Zil saatlerini zil düzenleyicisinde (Program › Zil saatleri) girin.")  # fmt: skip
        elif oneri_zil:
            zil_onerilemez = "Bu rapordaki saatlerden zil çizelgesi oluşturulamıyor; zil saatlerini zil düzenleyicisinde girin."
    if sayilar["devresiz"]:
        ne = "zil çizelgesini rapordan oluşturun ya da zil saatlerini düzeltin" if olusturulabilir else "zil saatlerini zil düzenleyicisinde düzeltin"
        uyarilar.append(f"Saatleri zil çizelgesindeki hiçbir devreye uymayan {sayilar['devresiz']} blok yazılmayacak; {ne}.")
    for g in gruplar:
        d = devreler[g["anahtar"]]
        if d["devre"] and d["farkli"]:
            ornek = ", ".join(f"{no}. ders {bas}" for no, bas in d["farkli_dersler"][:8])
            uyarilar.append(f"{grup_adi[g['anahtar']]}: rapordaki {d['farkli']} ders saati zil çizelgesinden 5 dakikadan çok "
                            f"farklı ({ornek}). Bu bloklar yine programa yazılır; ders numaraları zil çizelgenize göre "
                            "kullanılır.")  # fmt: skip
    if sayilar["atlanan"]:
        uyarilar.append(f"Şubesi seçilmeyen {sayilar['atlanan']} blok atlanacak.")
    bos_bloklar = [b["no"] for b in bloklar if not b["dolu"] and oneri["atama"][b["no"]]]
    if bos_bloklar:
        uyarilar.append(f"{len(bos_bloklar)} blokta hiç ders yok ({', '.join(map(str, bos_bloklar[:20]))}"
                        f"{'…' if len(bos_bloklar) > 20 else ''}. blok): bu şubelerin tahtasına bir şey yazılmaz, "
                        "eski programları da değişmez. e-Okul'da bu şubelerin programı girilmiş mi, bakın.")  # fmt: skip
    return {
        "girdi": {"kaynak": "eokul", "ara": ara, "bilgi": bilgi},
        "uyarilar": uyarilar,
        "bloklar": satirlar,
        "gruplar": [{**g, "ad": grup_adi[g["anahtar"]], "devre": devreler[g["anahtar"]]["devre"],
                     "farkli": devreler[g["anahtar"]]["farkli"], "blok_sayisi": len(g["bloklar"])} for g in gruplar],  # fmt: skip
        "zil_onerisi": oneri_zil,
        "zil_gerekli": zil_gerekli,
        "zil_onerilemez": zil_onerilemez,
        # zil var ve her grup bir devreye uyuyor; yalnız bazı ders saatleri farklı (bloklar yine yazılır)
        "zil_yalniz_fark": bool(saatler) and all(devreler[g["anahtar"]]["devre"] for g in gruplar),
        "ciftler": oneri["ciftler"],
        "kaynak": oneri["kaynak"],
        "kaynak_sayisi": oneri["kaynak_sayisi"],
        "sayilar": sayilar,
        "devre_dagilimi": [(grup_adi[g["anahtar"]], len(g["bloklar"])) for g in gruplar],
    }  # fmt: skip
