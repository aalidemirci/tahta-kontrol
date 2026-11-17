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
    ogretmensiz = bos_blok = 0
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
                hucre = str(satir[c] if c < len(satir) else "")
                satirlar = [_metin(s) for s in hucre.splitlines() if s.strip()]
                if not satirlar:
                    continue
                ders_adi = satirlar[0]
                kisiler = satirlar[1:] or [""]
                for kaynak in (parca.strip() for s in kisiler for parca in re.split(r"[,;]", s)):
                    # Seçmeli hücreler: "AD SOYAD - DERS". Tireli soyad bölünmez.
                    kisi, ayirac, secmeli = kaynak.partition(" - ")
                    kisi = _metin(kisi)
                    ders = _metin(secmeli) if ayirac and secmeli.strip() else ders_adi
                    anahtar = ad_anahtari(kisi)
                    if anahtar:
                        ogretmenler.setdefault(anahtar, kisi)
                        parmaklar.add(ad_anahtari(kaynak))
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
    return {"dersler": dersler, "ogretmenler": ogretmenler, "ogretmensiz": ogretmensiz,
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
    eslesmeler = []
    for no, (anahtar, ad) in enumerate(sorted(veri["ogretmenler"].items())):
        onerilen = str(adlar[anahtar][0]) if len(adlar[anahtar]) == 1 else ""
        secilen = str(secimler.get(anahtar, onerilen))
        if secilen != "yok" and secilen not in etkin_idler:
            secilen = ""
        eslesmeler.append({"no": no, "anahtar": anahtar, "ad": ad, "secilen": secilen,
                           "otomatik": bool(onerilen), "belirsiz": len(adlar[anahtar]) > 1})
    return {"ogretmenler": eslesmeler, "secenekler": secenekler,
            "ders_sayisi": len(veri["dersler"]), "sube_sayisi": len({d['sube'] for d in veri['dersler']}),
            "bos_blok": veri["bos_blok"], "ogretmensiz": veri["ogretmensiz"],
            "eslesmeyen": sum(not e["secilen"] for e in eslesmeler),
            "bloklar": veri["bloklar"], "ornek_dersler": veri["dersler"][:80]}


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
