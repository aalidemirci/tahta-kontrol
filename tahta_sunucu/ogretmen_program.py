"""Öğretmen programı aktarımı: dosyalar bellekte, kimlik eşlemesi açık onayla.

Bu program bilgilendirme ve yoklama önerisi içindir; öğretmenin başka sınıfta
yoklama almasını engellemez. Eski dolu/boş derslik okuyucusu değiştirilmez.
"""

from __future__ import annotations

import io
import re
from collections import defaultdict

from . import eokul_program, metin, vt

PDF_EN_COK_BAYT = 8 * 1024 * 1024
PDF_EN_COK_SAYFA = eokul_program.EN_COK_BLOK
METIN_EN_COK = 160
GUNLER = {"pazartesi": 0, "sali": 1, "carsamba": 2, "persembe": 3, "cuma": 4,
          "cumartesi": 5, "pazar": 6}


def ad_anahtari(deger: str) -> str:
    return metin.katla(deger)


def _metin(deger: str) -> str:
    sonuc = " ".join(str(deger or "").split())
    if len(sonuc) > METIN_EN_COK:
        raise ValueError("Ders veya öğretmen alanı çok uzun; raporu kontrol edin.")
    return sonuc


_PARCA = re.compile(r"[,;\t]|\s{2,}")
_AYIRAC = re.compile(r"\s-\s")
GENEL_BASLIK = "Ders"


def hucre_coz(hucre: str) -> tuple[str, list[tuple[str, str]], int]:
    """Hücre → (genel başlık, [(kaynak kişi, ders adı)], belirsiz giriş sayısı).

    İlk satır dersin (ya da "SEÇMELİ DERS" gibi grubun) başlığıdır; sonraki satırlar kişilerdir.
    e-Okul aynı saatteki seçmeli grupları TEK satırda en az iki boşlukla ayırır
    ("KİŞİ - DERS  KİŞİ - DERS"); bu yüzden satır, boşluklar sadeleştirilmeden ÖNCE bölünür.
    Kapalı hata: bölündükten sonra bir parçada hâlâ birden çok " - " varsa kişi ile dersin sınırı
    bilinemez; ders adı genel başlığa iner ve kişi eşlemeye alınmaz (ders adı tahtanın kilit
    ekranında görünür). Hücre tek başına her sapmayı yakalayamaz (tek " - " sonrasına eklenmiş ikinci
    kişi, ilk satırı ad olan hücre); bunlar için `matris_oku` bütün rapor okunduktan sonra ders
    adlarını rapordaki kişi adlarıyla karşılaştırır (`_adli_dersleri_indir`) ve önizleme aktarılacak
    FARKLI ders adlarının tamamını gösterir.
    """
    satirlar = [s for s in str(hucre or "").splitlines() if s.strip()]
    if not satirlar:
        return "", [], 0
    belirsiz = 0
    baslik = satirlar[0].strip()
    # Başlık satırı da "kişi - ders" kalıbındaysa başlık sayılmaz.
    if _AYIRAC.search(baslik):
        baslik, belirsiz = GENEL_BASLIK, 1
    baslik = _metin(baslik)
    girisler = []
    for satir in satirlar[1:]:
        for parca in (p.strip() for p in _PARCA.split(satir)):
            if not parca:
                continue
            bolumler = _AYIRAC.split(parca)
            if len(bolumler) > 2:
                belirsiz += 1
                girisler.append(("", baslik))
                continue
            kisi = _metin(bolumler[0])
            ders = _metin(bolumler[1]) if len(bolumler) == 2 else ""
            girisler.append((kisi, ders or baslik))
    return baslik, girisler or [("", baslik)], belirsiz


_SOZCUK_DISI = re.compile(r"[^0-9a-z]+")


def _sozcukler(deger: str) -> str:
    return " ".join(_SOZCUK_DISI.sub(" ", ad_anahtari(deger)).split())


def _adli_dersleri_indir(dersler: list[dict], ogretmenler: dict) -> int:
    """Ders adı, raporda kişi olarak görülen bir adı (en az iki sözcük) içeriyorsa genel başlığa iner.

    Kapalı hata: o satır öğretmen eşlemesine de alınmaz. Dönen sayı etkilenen ders satırıdır.
    """
    adlar = {f" {a} " for a in (_sozcukler(ad) for ad in ogretmenler.values()) if " " in a}
    supheli = {}
    sayi = 0
    for d in dersler:
        ad = d["ders_adi"]
        if ad not in supheli:
            aranan = f" {_sozcukler(ad)} "
            supheli[ad] = any(a in aranan for a in adlar)
        if supheli[ad]:
            d["ders_adi"], d["ogretmen_anahtari"] = GENEL_BASLIK, ""
            sayi += 1
    return sayi


def pdf_oku(bayt: bytes) -> tuple[list[str], list[str]]:
    """Her PDF sayfasından tek şube ve doğrulama metni; ikisi de yalnız bellekte."""
    if not bayt or len(bayt) > PDF_EN_COK_BAYT or not bayt.startswith(b"%PDF-"):
        raise ValueError("PDF dosyası geçersiz veya 8 MB sınırını aşıyor.")
    from pypdf import PdfReader

    try:
        pdf = PdfReader(io.BytesIO(bayt))
        if pdf.is_encrypted or not 1 <= len(pdf.pages) <= PDF_EN_COK_SAYFA:
            raise ValueError("PDF şifreli veya sayfa sayısı sınırların dışında.")
        subeler, metinler = [], []
        for no, sayfa in enumerate(pdf.pages, 1):
            ham = sayfa.extract_text() or ""
            if len(ham) > 200_000:
                raise ValueError(f"PDF'nin {no}. sayfası çok büyük.")
            bulunan, _ = eokul_program.sube_listesi_coz(ham)
            if len(bulunan) != 1:
                raise ValueError(f"PDF'nin {no}. sayfasında tek bir şube başlığı okunamadı.")
            subeler.append(bulunan[0])
            metinler.append(ad_anahtari(ham))
    except ValueError:
        raise
    except Exception as hata:
        raise ValueError("PDF okunamadı; şube listesini sıralı olarak elle yapıştırabilirsiniz.") from hata
    if len(set(subeler)) != len(subeler):
        raise ValueError("PDF'de aynı şube birden çok sayfada görünüyor; şube eşlemesini kontrol edin.")
    return subeler, metinler


def matris_oku(matris: list[list[str]], subeler: list[str], pdf_metinleri: list[str] | None = None) -> dict:
    """e-Okul matrisinden şube/gün/saat/ders ve geçici kaynak öğretmen adlarını alır."""
    rapor = eokul_program.rapor_oku(matris)
    if rapor["hata_sayisi"]:
        raise ValueError("Programda okunamayan ders saatleri var; aktarım yapılmadı.")
    if len(subeler) != len(rapor["bloklar"]):
        raise ValueError(f"Programda {len(rapor['bloklar'])} blok var; aynı sayıda sıralı şube gerekir.")
    subeler = [metin.sube_duzelt(s) for s in subeler]
    if not all(subeler) or len(set(subeler)) != len(subeler):
        raise ValueError("Şubeler geçerli ve birbirinden farklı olmalı.")
    if pdf_metinleri is not None and len(pdf_metinleri) != len(subeler):
        raise ValueError("PDF sayfa sayısı program bloklarıyla aynı değil.")
    sutunlar = next(
        ({c: GUNLER[metin.katla(h).strip(' .:')] for c, h in enumerate(satir)
          if metin.katla(h).strip(' .:') in GUNLER} for satir in matris[:eokul_program.BASLIK_TARAMA]
         if sum(metin.katla(h).strip(' .:') in GUNLER for h in satir) >= 2), {})
    dersler, ogretmenler, gorulen = [], {}, set()
    yerler: dict[str, dict[tuple, set[str]]] = defaultdict(dict)
    ogretmensiz = bos_blok = belirsiz = 0
    for i, blok in enumerate(rapor["bloklar"]):
        son = rapor["bloklar"][i + 1]["satir"] - 1 if i + 1 < len(rapor["bloklar"]) else len(matris)
        saatler = {no: (bas, bit) for no, bas, bit in blok["dersler"]}
        parmaklar = set()
        if not blok["dolu"]:
            bos_blok += 1
        for satir in matris[blok["satir"] - 1:son]:
            no_m = eokul_program._DERS_NO.match(satir[0] if satir else "")
            if not no_m or int(no_m.group(1)) not in saatler:
                continue
            no = int(no_m.group(1))
            bas, bit = saatler[no]
            for c, gun in sutunlar.items():
                ders_adi, girisler, sorunlu = hucre_coz(str(satir[c] if c < len(satir) else ""))
                if not ders_adi:
                    continue
                belirsiz += sorunlu
                for kisi, ders in girisler:
                    anahtar = ad_anahtari(kisi)
                    if anahtar:
                        ogretmenler.setdefault(anahtar, kisi)
                        parmaklar.add(ad_anahtari(kisi if ders == ders_adi else f"{kisi} - {ders}"))
                        yerler[anahtar].setdefault((gun, bas), set()).add(ad_anahtari(ders))
                    else:
                        ogretmensiz += 1
                    kimlik = (subeler[i], gun, no, bas, bit, ders, anahtar)
                    if kimlik in gorulen:
                        continue
                    gorulen.add(kimlik)
                    dersler.append({"sube": subeler[i], "gun": gun, "ders_no": no, "baslangic": bas,
                                    "bitis": bit, "ders_adi": ders, "ogretmen_anahtari": anahtar})
        if pdf_metinleri is not None and any(p not in pdf_metinleri[i] for p in parmaklar):
            raise ValueError(f"{i + 1}. Excel bloğundaki öğretmen satırları aynı PDF sayfasıyla uyuşmuyor. "
                             "Dosyaların aynı rapordan geldiğini ve sırasını kontrol edin.")
    if not dersler:
        raise ValueError("Programda aktarılabilecek dolu ders bulunamadı.")
    belirsiz += _adli_dersleri_indir(dersler, ogretmenler)
    # Aynı ad aynı gün ve saatte FARKLI derslerde: aynı adı taşıyan iki kişi tek ada katlanmış olabilir
    # (şubeleri birleştirilen seçmeli grup aynı dersi taşır; o sayılmaz).
    cakisan = sorted(a for a, y in yerler.items() if any(len(s) > 1 for s in y.values()))
    return {"dersler": dersler, "ogretmenler": ogretmenler, "ogretmensiz": ogretmensiz,
            "belirsiz": belirsiz, "cakisan_adlar": cakisan,
            "blok_sayisi": len(subeler), "bos_blok": bos_blok,
            "bloklar": [{"no": b["no"], "sube": subeler[i], "dolu": len(b["dolu"]),
                         "bas": b["dersler"][0][1], "bit": b["dersler"][-1][2]}
                        for i, b in enumerate(rapor["bloklar"])]}


def dosya_oku(xls: bytes, *, pdf: bytes | None = None, sube_metni: str = "") -> dict:
    matris = eokul_program.matris_oku(xls)
    pdf_metinleri = None
    if pdf:
        subeler, pdf_metinleri = pdf_oku(pdf)
    else:
        subeler, uyarilar = eokul_program.sube_listesi_coz(sube_metni)
        if uyarilar:
            raise ValueError("Sıralı şube listesinde tanınmayan veya tekrarlı girişler var.")
    return matris_oku(matris, subeler, pdf_metinleri)


def ogretmen_secenekleri(b) -> list[dict]:
    return [{"id": o["id"], "ad": " ".join((o["ad"], o["soyad"]))}
            for o in b.execute("SELECT id, ad, soyad FROM ogretmen WHERE aktif = 1 ORDER BY soyad, ad, id")]


def onizle(b, veri: dict, secimler: dict | None = None) -> dict:
    """Yalnız tek ve tam ad eşleşmesi önerilir; belirsizlikte insan seçer."""
    secimler = secimler or {}
    secenekler = ogretmen_secenekleri(b)
    adlar = defaultdict(list)
    for o in secenekler:
        adlar[ad_anahtari(o["ad"])].append(o["id"])
    etkin_idler = {str(o["id"]) for o in secenekler}
    cakisan = set(veri.get("cakisan_adlar", ()))
    eslesmeler = []
    for no, (anahtar, ad) in enumerate(sorted(veri["ogretmenler"].items())):
        onerilen = str(adlar[anahtar][0]) if len(adlar[anahtar]) == 1 else ""
        secilen = str(secimler.get(anahtar, onerilen))
        if secilen != "yok" and secilen not in etkin_idler:
            secilen = ""
        eslesmeler.append({"no": no, "anahtar": anahtar, "ad": ad, "secilen": secilen,
                           "otomatik": bool(onerilen), "belirsiz": len(adlar[anahtar]) > 1,
                           "cakisan": anahtar in cakisan})
    return {"ogretmenler": eslesmeler, "secenekler": secenekler,
            "ders_sayisi": len(veri["dersler"]), "sube_sayisi": len({d['sube'] for d in veri['dersler']}),
            "bos_blok": veri["bos_blok"], "ogretmensiz": veri["ogretmensiz"],
            "belirsiz": veri.get("belirsiz", 0), "cakisan_sayisi": len(cakisan),
            "eslesmeyen": sum(not e["secilen"] for e in eslesmeler),
            "bloklar": veri["bloklar"], "ornek_dersler": veri["dersler"][:80],
            # Kilit ekranına gidecek metnin TAMAMI onaydan önce insan gözünden geçsin.
            "ders_adlari": sorted({d["ders_adi"] for d in veri["dersler"]}, key=metin.katla)}


def surum(b) -> int:
    return int(vt.ayar_al(b, "ogretmen_program_surum", 0) or 0)


def uygula(b, veri: dict, beklenen_surum: int, secimler: dict, *, ogretmensiz_onay: bool = False) -> int:
    """Sürüm, etkin öğretmen ve açık eşleme onaylarını doğrulayıp atomik değiştirir."""
    if not b.in_transaction:
        b.execute("BEGIN IMMEDIATE")
    if surum(b) != beklenen_surum:
        raise ValueError("Öğretmen programı bu sırada değişti; dosyaları yeniden yükleyip önizleyin.")
    ozet = onizle(b, veri, secimler)
    if ozet["eslesmeyen"]:
        raise ValueError("Bütün kaynak öğretmenleri eşleyin veya açıkça öğretmensiz aktarılacağını seçin.")
    esleme = {e["anahtar"]: None if e["secilen"] == "yok" else int(e["secilen"]) for e in ozet["ogretmenler"]}
    if (veri["ogretmensiz"] or any(v is None for v in esleme.values())) and not ogretmensiz_onay:
        raise ValueError("Öğretmen eşlemesi olmayan dersler için ayrı onay gerekir.")
    an = vt.simdi()
    satirlar = [(d["sube"], d["gun"], d["ders_no"], d["baslangic"], d["bitis"], d["ders_adi"],
                 esleme.get(d["ogretmen_anahtari"]), an) for d in veri["dersler"]]
    satirlar = list(dict.fromkeys(satirlar))
    b.execute("DELETE FROM ogretmen_program")
    b.executemany("INSERT INTO ogretmen_program "
                  "(sube, gun, ders_no, baslangic, bitis, ders_adi, ogretmen_id, guncelleme) "
                  "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", satirlar)
    vt.ayar_yaz(b, "ogretmen_program_surum", beklenen_surum + 1)
    return len(satirlar)
