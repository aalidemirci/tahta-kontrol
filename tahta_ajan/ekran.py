"""Ekran yardımcısı: kilit, duyuru, kapatma uyarısı, acil yayın, sınav ve gözetmen ekranlarını çizer.

Her masaüstü oturumunda (otomatik başlatma ile) kullanıcının yetkisiyle
çalışır; ne göstereceğini ajan servisinden yerel soket üzerinden öğrenir.
Servisle bağlantı koparsa pencere kapanır: yardımcı tek başına tahtayı
kilitli tutmaz.

Görünüm: her sayfanın üstünde okulun logosu ve adı olan bir bant durur. Renkler
sunucuda hesaplanır (okunurluk eşikleri orada tutturulur) ve servis üzerinden
hex olarak gelir; burada yalnız doğrulanıp GTK stiline yazılır. Logo baytları
servisten "marka" mesajıyla gelir; yüklenemezse ekran logosuz çalışır.

Acil yayın sayfası okulun renginden bağımsız sabit renklerle (acil kırmızı, tatbikat
kehribar) tam ekran çizilir; her şeyin üstündedir ve kilitli tahtada klavye kilidi sürer.

Sınav kipi (Aşama 4): giriş ekranı (maskeli oturma listesi, yalnız başlangıçtan önceki 10 dk),
sınav ekranı (büyük geri sayım, bitiş, kurallar) ve gözetmen sayfaları (kod, menü, yoklama
ızgarası). Hepsinde klavye ve fare pencereye bağlıdır; ortak kilit kodu kabul edilmez. Gözetmen
belirteci bu yardımcıya hiç gelmez; kod servise iletilir ve sunucuda doğrulanır.

Ders yoklaması (Aşama 5): PIN sayfası (öğretmen kodu + PIN, tuş takımı), sınıf listesi (maskeli
etiketli düğmeler; yalnız "yok" olanlara dokunulur), onay ve ileti sayfaları. Liste yalnız servisten
gelen durum iletisinde ve düğmelerde durur; yoklama kapanınca düğmeler yok edilir. Yoklama belirteci
bu yardımcıya hiç gelmez; PIN servise iletilir, burada saklanmaz. Öncelik: acil > kapatma > gözetmen >
yoklama > duyuru > sınav > kilit. Klavye kilidi yalnız tahta kilitliyse alınır.
"""

from __future__ import annotations

import base64
import json
import os
import socket
import sys
import threading
import time

from . import __version__, ayar

# Ölçüler, ağırlıklar ve boşluklar: renk YOK (renkler renk_stili() ile ayrı sağlayıcıda).
STIL_OLCU = b"""
#okul { font-size: 40px; font-weight: 600; }
#bant-sag { font-size: 26px; }
#ust-bant { padding: 28px 48px; border-bottom-width: 6px; border-bottom-style: solid; }
#logo-kutu { border-radius: 16px; padding: 10px; }
#saat { font-size: 150px; font-weight: 700; }
#tarih { font-size: 30px; }
#kilit-yazi { font-size: 40px; font-weight: 600; margin-top: 24px; }
#program-bilgi { font-size: 32px; font-weight: 600; }
#bilgi { font-size: 24px; }
#kod { font-size: 56px; letter-spacing: 12px; }
#duyuru-baslik { font-size: 72px; font-weight: 700; }
#duyuru-metin { font-size: 52px; }
#duyuru-metin.uzun { font-size: 40px; }
#duyuru-metin.cok-uzun { font-size: 32px; }
#duyuru-ust { font-size: 34px; font-weight: 600; }
#kapatma-baslik { font-size: 64px; font-weight: 700; }
#kapatma-sayac { font-size: 170px; font-weight: 700; }
#kapatma-neden { font-size: 30px; }
#acil-bant { font-size: 60px; font-weight: 800; }
#acil-baslik { font-size: 84px; font-weight: 800; }
#acil-metin { font-size: 54px; }
#acil-metin.uzun { font-size: 40px; }
#acil-metin.cok-uzun { font-size: 32px; }
#acil-alt { font-size: 28px; }
#acil-kapat { border-width: 3px; }
#sinav-adi { font-size: 56px; font-weight: 700; }
#sinav-salon { font-size: 36px; font-weight: 600; }
#sinav-bilgi { font-size: 32px; }
#sinav-sayac { font-size: 220px; font-weight: 700; }
#sinav-bitis { font-size: 36px; font-weight: 600; }
#sinav-kurallar { font-size: 28px; }
#sinav-durum { font-size: 28px; font-weight: 600; }
#sinav-saat { font-size: 34px; font-weight: 600; }
#sinav-fazla { font-size: 26px; }
#sinav-cevrimdisi { font-size: 24px; }
#gozetmen-baslik { font-size: 52px; font-weight: 700; }
#gozetmen-bilgi { font-size: 28px; }
#gozetmen-hata { font-size: 28px; font-weight: 600; }
#koltuk { font-size: 22px; font-weight: 600; padding: 6px 8px; }
#yoklama-baslik { font-size: 52px; font-weight: 700; }
#yoklama-bilgi { font-size: 28px; }
#yoklama-adim { font-size: 32px; font-weight: 600; }
#yoklama-hata { font-size: 28px; font-weight: 600; }
#yoklama-ust { font-size: 34px; font-weight: 600; }
#yoklama-kalan { font-size: 34px; font-weight: 600; }
#yoklama-sayi { font-size: 32px; font-weight: 600; }
#yoklama-onay-liste { font-size: 34px; }
#yoklama-ileti { font-size: 52px; font-weight: 600; }
#ogrenci { font-size: 26px; font-weight: 600; padding: 8px 10px; }
#ogrenci.uzun { font-size: 20px; }
#secim { font-size: 30px; padding: 10px 16px; }
.liste-no { font-weight: 700; }
#ana-dugme:disabled, button:disabled { opacity: 0.45; }
button { font-size: 34px; font-weight: 600; padding: 14px 26px; border-radius: 12px; background-image: none;
         border-width: 1px; border-style: solid; box-shadow: none; text-shadow: none; }
"""

# Acil yayın renkleri SABİTTİR (okulun renginden bağımsız; kapatma başlığı gibi). Anlam:
# acil = koyu kırmızı zemin, beyaz yazı; tatbikat = koyu kehribar zemin, açık sarı bant.
# Yanıp sönme ya da animasyon YOK. Beyaz/açık sarı yazı her iki zeminde 7:1'i aşar.
ACIL_RENKLERI = (
    "window.acil { background-color: #7f1d1d; }\n"
    "window.acil label { color: #ffffff; }\n"
    "window.acil #acil-bant { color: #fecaca; }\n"
    "window.tatbikat { background-color: #713f12; }\n"
    "window.tatbikat label { color: #ffffff; }\n"
    "window.tatbikat #acil-bant { color: #fde68a; }\n"
    "#acil-kapat { background-color: #1c1917; border-color: #ffffff; }\n"
    "window.acil scrolledwindow, window.acil viewport, window.tatbikat scrolledwindow, "
    "window.tatbikat viewport { background-color: transparent; border-width: 0; }\n"
)

ACIL_BANT = {"acil": "ACİL DURUM", "tatbikat": "TATBİKAT — BU BİR TATBİKATTIR"}

# Sınav ekranı renkleri: son 5 dakikada sayaç kehribar (#fbbf24, markadan bağımsız; koyu zeminde
# 7:1'i aşar); gelmedi işaretli koltuk koyu kırmızı zemin + beyaz yazı; gözetmen hatası açık kırmızı.
SINAV_RENKLERI = (
    "#sinav-sayac.son { color: #fbbf24; }\n"
    "#gozetmen-hata { color: #fca5a5; }\n"
    "#koltuk:checked { background-color: #991b1b; border-color: #fca5a5; }\n"
    "#koltuk:checked label { color: #ffffff; }\n"
)
# Ders yoklaması: "yok" işaretli öğrenci düğmesi koyu kırmızı zemin + beyaz yazı + "YOK" satırı
# (renk tek başına anlam taşımaz); hata ve süre uyarısı açık kırmızı. Markadan bağımsız sabit renkler.
YOKLAMA_RENKLERI = (
    "#ogrenci:checked { background-color: #991b1b; border-color: #fca5a5; }\n"
    "#ogrenci:checked label { color: #ffffff; }\n"
    "#yoklama-hata { color: #fca5a5; }\n"
)
SINAV_SON_DAKIKALAR_SN = 300
GOZETMEN_KOD_ZAMAN_ASIMI_SN = 60  # gözetmen kodu sayfası dokunulmazsa kapanır (öğrenci önünde açık kalmasın)


def sayac_metni(saniye: int) -> str:
    """Geri sayım: bir saatten kısa "DD:ss", uzun "S:DD:ss"."""
    saniye = max(0, int(saniye))
    saat, kalan = divmod(saniye, 3600)
    dakika, sn = divmod(kalan, 60)
    return f"{saat}:{dakika:02d}:{sn:02d}" if saat else f"{dakika:02d}:{sn:02d}"


def baslama_metni(baslangic_saat: str, kalan_sn: int) -> str:
    """Giriş ekranı satırı: "Başlangıç 10:00 — 7 dk sonra"."""
    dakika = (max(0, int(kalan_sn)) + 59) // 60
    sonra = f"{dakika} dk sonra" if dakika > 1 else "1 dakika içinde"
    return f"Başlangıç {baslangic_saat} — {sonra}" if baslangic_saat else f"Sınav {sonra} başlıyor"


def bitis_metni(sinav: dict) -> str:
    """Tek ders: "Bitiş 10:40"; karma salonda her ders için "Matematik — 9. Sınıf: 10:40"."""
    dersler = [d for d in sinav.get("dersler") or [] if d.get("bitis_saat")]
    if len(dersler) > 1 and len({d["bitis_saat"] for d in dersler}) > 1:
        return "\n".join(f"{d.get('ad', '')}: {d['bitis_saat']}" for d in dersler[:6])
    return f"Bitiş {sinav.get('bitis_saat', '')}".strip()


def liste_sutun_sayisi(n: int) -> int:
    """Giriş ekranındaki liste: ≤ 20 kişi tek sütun, ≤ 40 iki, fazlası üç sütun."""
    return 1 if n <= 20 else 2 if n <= 40 else 3


def liste_punto(satir_sayisi: int, ekran_boyu: int) -> int:
    """Liste yazı boyu (px): ekran yüksekliğinden; 22–44 arası (arka sıradan okunabilsin)."""
    kullanilir = (ekran_boyu or 1080) - 430  # bant, başlık satırları ve alt satır
    return max(22, min(44, int(kullanilir / max(1, satir_sayisi) / 1.38)))


def liste_hucreleri(oge: dict) -> tuple[str, str, str, str]:
    """Bir liste satırının hücreleri: koltuk · maske · …no · şube (tam no ve ders yok)."""
    no = str(oge.get("n") or "")
    return str(oge.get("k", "")), str(oge.get("a") or ""), f"…{no}" if no else "", str(oge.get("s") or "")


def izgara_sutun(n: int) -> int:
    """Yoklama ızgarasının sütun sayısı: ceil(sqrt(n·16/9)) — düğmeler 16:9 ekrana yayılır."""
    import math

    return max(1, math.ceil(math.sqrt(max(1, n) * 16 / 9)))


def koltuk_etiketi(oge: dict, gelmedi: bool) -> str:
    koltuk, maske, no, _ = liste_hucreleri(oge)
    ust = f"{koltuk} · GELMEDİ" if gelmedi else koltuk
    return "\n".join(p for p in (ust, maske, no) if p)


def gozetmen_kod_hatasi(gozetmen: dict) -> str:
    """Kod sayfasındaki hata satırı. Bekleme sürerken servis hatayı silmiş olsa da (Vazgeç ile
    çıkılıp yeniden girildiğinde) pasif tuş takımının nedeni yazılır."""
    if gozetmen.get("durum") == "dogrulaniyor":
        return "Doğrulanıyor…"
    bekleme = int(gozetmen.get("bekleme") or 0)
    if bekleme > 0:
        dk = max(1, -(-bekleme // 60))
        return f"Çok fazla hatalı deneme. {dk} dakika sonra yeniden deneyin."
    return str(gozetmen.get("hata") or "")


def yoklama_engeli(gozetmen: dict) -> str:
    """"Yoklama al" düğmesi pasifse nedeni; değilse ""."""
    if not gozetmen.get("tahtadan_yoklama"):
        return "Bu salonun yoklaması panelden alınır."
    if not gozetmen.get("basladi"):
        return "Sınav başlayınca açılır."
    return ""


def acil_basligi(baslik, tatbikat: bool) -> str:
    """Acil sayfasındaki büyük başlık. Bant sözcüğünü tekrarlayan ya da boş başlık
    gösterilmez ("ACİL DURUM" alt alta iki kez yazılmasın); boş metin = etiket gizli."""
    metin = " ".join(str(baslik or "").split())

    def katla(s: str) -> str:  # Türkçe büyük/küçük harf duyarsız karşılaştırma
        return s.replace("İ", "I").replace("ı", "i").upper().rstrip(".!")

    tekrar = {katla(s) for s in ("ACİL DURUM", "TATBİKAT", ACIL_BANT["tatbikat"])}
    return "" if katla(metin) in tekrar else metin


# ---- ders yoklaması (A5): saf yardımcılar (test edilir) -------------------------------------
YOKLAMA_SUTUN_EN_COK = 6
YOKLAMA_DUGME_EN = 260
YOKLAMA_DUGME_BOY = 96
YOKLAMA_DUGME_SIGAN = 14  # 260 px düğmede 26 px kalın yazıyla kısalmadan sığan harf sayısı (yaklaşık)
YOKLAMA_KOD_HANE = 3
YOKLAMA_PIN_HANE = 6


def yoklama_ust_metni(yoklama: dict) -> str:
    """Liste sayfasının üst satırı: "10/A · 3. ders (09:50–10:30) · A. Örnek"."""
    ogretmen = (yoklama.get("ogretmen") or {}).get("etiket") or ""
    parcalar = [yoklama.get("sube") or "Şube seçilmedi", yoklama.get("ders_metni") or "", yoklama.get("ders_adi") or "", ogretmen]
    return " · ".join(p for p in parcalar if p)


def yoklama_sayi_metni(yok_sayisi: int, mevcut: int) -> str:
    """Alt çubuk: "Yok: 2 · Mevcut: 32/34" (mevcut = derste olan / listedeki)."""
    return f"Yok: {yok_sayisi} · Mevcut: {max(0, mevcut - yok_sayisi)}/{mevcut}"


def yoklama_onay_metni(etiketler: list[str]) -> tuple[str, str]:
    """Onay sayfası: başlık ve yok yazılacakların etiketleri."""
    if not etiketler:
        return "Bütün öğrenciler derste.", ""
    return f"{len(etiketler)} öğrenci yok yazılacak:", ", ".join(etiketler)


def ogrenci_etiket_parcalari(etiket: str) -> tuple[str, str]:
    """Sunucunun çakışma eki adın sonundan ayrılır: "Mehmet Ali Y. (23)" → ("Mehmet Ali Y.", "(23)").

    Uzun ad düğmede üç noktayla kısalırsa adaşları ayıran ek kesilmesin diye ek ayrı satıra gider.
    """
    ana, _, ek = str(etiket).rpartition(" ")
    if ana and len(ek) >= 3 and ek[0] == "(" and ek[-1] == ")" and all(c in "0123456789" for c in ek[1:-1]):
        return ana, ek
    return str(etiket), ""


def ogrenci_dugme_metni(etiket: str, yok: bool) -> str:
    """Öğrenci düğmesi: ilk satır ad, ikinci satır çakışma eki ve işaretliyse "YOK" (renk tek
    başına anlam taşımaz). En çok iki satır; üç noktayla kısalabilen yalnız ilk satırdır."""
    ana, ek = ogrenci_etiket_parcalari(etiket)
    alt = " · ".join(p for p in (ek, "YOK" if yok else "") if p)
    return f"{ana}\n{alt}" if alt else ana


def ogrenci_uzun_mu(ad: str) -> bool:
    """Düğmede 26 px yazıyla sığmayan ad: daha küçük yazıyla gösterilir (#ogrenci.uzun)."""
    return len(ad) > YOKLAMA_DUGME_SIGAN


def yoklama_sutun(ekran_eni: int) -> int:
    """Liste ızgarasının sütun sayısı: ekran enine göre, en çok 6."""
    return max(1, min(YOKLAMA_SUTUN_EN_COK, ((ekran_eni or 1920) - 120) // (YOKLAMA_DUGME_EN + 16)))


def yoklama_pin_hatasi(yoklama: dict) -> str:
    """PIN sayfasındaki hata/bilgi satırı."""
    if yoklama.get("istek"):
        return "Doğrulanıyor…"
    bekleme = int(yoklama.get("bekleme") or 0)
    if bekleme > 0:
        return f"Çok fazla hatalı deneme. {bekleme} saniye bekleyin."
    return str(yoklama.get("hata") or "")


DUYURU_SUTUN_ESIGI = 12  # bundan çok satırlı duyuru (ör. şube oturma listesi) sütunlara bölünür
KURALLAR_EKRAN_SATIRI = 8  # sınav kuralları ekranda en çok bu kadar satır (alt satır ekranda kalsın)


def kurallar_metni(metin: str) -> str:
    """Sınav ekranındaki kurallar: en çok KURALLAR_EKRAN_SATIRI dolu satır; fazlası "…" ile kesilir.

    Pango'nun satır sınırı paragraf başınadır; toplam satır sayısı burada sınırlanır (eski sunucu
    ya da elle yazılmış uzun metin de alt satırı — Gözetmen, kural 3 "Kilidi aç" — ekrandan itmesin).
    """
    satirlar = [x.strip() for x in str(metin or "").splitlines() if x.strip()]
    if len(satirlar) <= KURALLAR_EKRAN_SATIRI:
        return "\n".join(satirlar)
    return "\n".join(satirlar[: KURALLAR_EKRAN_SATIRI - 1] + [satirlar[KURALLAR_EKRAN_SATIRI - 1] + " …"])


def duyuru_duzeni(metin: str, ekran_boyu: int) -> dict:
    """Duyuru metninin ekran düzeni (saf; test edilir).

    Kısa metin: {"ust": "", "sutunlar": [], "sinif": ""|"uzun"|"cok-uzun", "punto": 0} ve metin
    tek etikette. Çok satırlı metin (şube oturma listesi gibi): baştaki ilk boş satıra kadarki
    en çok 3 satır "ust" olur, kalanlar 1–3 sütuna bölünür, yazı boyu ekran yüksekliğinden
    hesaplanır (20–40 px). Uzun liste sığmazsa sayfa kaydırılır; Kapat düğmesi hep ekrandadır.
    """
    satirlar = (metin or "").split("\n")
    if len(satirlar) <= DUYURU_SUTUN_ESIGI:
        uzunluk = len(metin or "")
        sinif = "" if uzunluk <= 300 and len(satirlar) <= 6 else "uzun" if uzunluk <= 600 else "cok-uzun"
        return {"ust": "", "sutunlar": [], "sinif": sinif, "punto": 0}
    ust: list[str] = []
    if "" in satirlar[:4]:
        bos = satirlar.index("")
        ust, satirlar = satirlar[:bos], satirlar[bos + 1 :]
    while satirlar and not satirlar[0].strip():
        satirlar = satirlar[1:]
    n = max(1, len(satirlar))
    sutun = 1 if n <= 16 else 2 if n <= 40 else 3
    boy = -(-n // sutun)
    kullanilir = (ekran_boyu or 1080) - 480  # bant, başlık, üst satır ve Kapat
    punto = max(20, min(40, int(kullanilir / boy / 1.38)))
    parcalar = [satirlar[i * boy : (i + 1) * boy] for i in range(sutun)]
    return {"ust": "\n".join(ust), "sutunlar": ["\n".join(p) for p in parcalar if p], "sinif": "", "punto": punto}


def acil_metin_sinifi(metin: str) -> str:
    """Uzun acil metninde yazı küçülür (1920x1080'de 1000 karakter sığsın): "", "uzun", "cok-uzun"."""
    uzunluk = len(metin or "")
    return "" if uzunluk <= 300 else "uzun" if uzunluk <= 600 else "cok-uzun"

LOGO_BOY = 96  # piksel; genişlik oran korunarak en çok LOGO_EN
LOGO_EN = 320
LOGO_METIN_SINIRI = 400_000  # base64 karakter (256 KB logo yaklaşık 350 000)


def renk_stili(palet: dict) -> str:
    """Tahta paletinden GTK renk kurallarını üretir (ASCII; değerler doğrulanmış hex).

    "label" genel kuralı düğme içindeki etiketi de yakalar; bu yüzden "button label" ve
    "#ana-dugme label" kuralları zorunludur. Kapatma başlığı markadan bağımsız sabit renktir.
    """
    p = ayar.palet_dogrula(palet) or dict(ayar.VARSAYILAN_PALET)
    return (
        f"window {{ background-color: {p['zemin']}; }}\n"
        f"label {{ color: {p['metin']}; }}\n"
        f"#ust-bant {{ background-color: {p['serit']}; border-bottom-color: {p['vurgu']}; }}\n"
        "#logo-kutu { background-color: #ffffff; }\n"
        f"#bant-sag, #tarih, #kapatma-neden {{ color: {p['soluk']}; }}\n"
        f"#bilgi {{ color: {p['bilgi']}; }}\n"
        f"#program-bilgi {{ color: {p['metin']}; }}\n"
        f"#duyuru-baslik {{ color: {p['vurgu']}; }}\n"
        "#kapatma-baslik { color: #fca5a5; }\n"
        f"button {{ background-color: {p['dugme']}; border-color: {p['dugme_kenar']}; }}\n"
        f"button label {{ color: {p['metin']}; }}\n"
        f"button:active {{ background-color: {p['yuzey']}; }}\n"
        f"#ana-dugme {{ background-color: {p['ana']}; border-color: {p['ana']}; }}\n"
        f"#ana-dugme label {{ color: {p['ana_metin']}; }}\n"
        f"#sinav-salon, #sinav-bilgi, #sinav-fazla, #sinav-cevrimdisi, #gozetmen-bilgi {{ color: {p['soluk']}; }}\n"
        f"#sinav-durum {{ color: {p['bilgi']}; }}\n"
        f".liste-no {{ color: {p['vurgu']}; }}\n"
        + f"#yoklama-bilgi, #yoklama-kalan {{ color: {p['soluk']}; }}\n"
        + SINAV_RENKLERI
        + YOKLAMA_RENKLERI
        + ACIL_RENKLERI
        # Kaydırılabilir duyuru/sınav ortası pencere zeminini örtmesin.
        + "scrolledwindow, viewport { background-color: transparent; border-width: 0; }\n"
    )


# Saatin okunuşundaki son sözcüğün bulunma eki: 10:40 "kırk" → 'ta, 10:30 "otuz" → 'da.
# tahta_sunucu/program.py::saat_eki ile aynıdır (ajan sunucu paketini içe aktarmaz).
_BIRLER_EKI = {0: "", 1: "de", 2: "de", 3: "te", 4: "te", 5: "te", 6: "da", 7: "de", 8: "de", 9: "da"}
_ONLAR_EKI = {1: "da", 2: "de", 3: "da", 4: "ta", 5: "de"}


def saat_eki(saat: str) -> str:
    """'SS:DD' saatine Türkçe bulunma ekini ekler: '10:40' → "10:40'ta", '11:00' → "11:00'de"."""
    try:
        ss, dd = (int(p) for p in saat.split(":"))
    except ValueError:
        return saat
    sayi = dd if dd else ss
    if sayi == 0:
        ek = "da"  # sıfır
    elif sayi % 10:
        ek = _BIRLER_EKI[sayi % 10]
    else:
        ek = _ONLAR_EKI.get(sayi // 10, "de")
    return f"{saat}'{ek}"


def program_bilgisi(durum: dict) -> str:
    """Program kilidinde kilit sayfasındaki satır: "Teneffüs · Tahta 10:40'ta açılır."

    Yalnız neden ve açılış saati yazılır; şube, ders, öğretmen yazılmaz (kural 6).
    """
    if durum.get("kilit_kaynak") != "program":
        return ""
    neden = str(durum.get("kilit_neden") or "Teneffüs")
    acilis = str(durum.get("kilit_acilis") or "")
    if not acilis:
        return f"{neden} · Tahta ders saatinde kendiliğinden açılır."
    return f"{neden} · Tahta {saat_eki(acilis)} açılır."


def logo_olcusu(en: int, boy: int) -> tuple[int, int]:
    """Logoyu bant yüksekliğine (96 px) ölçekler; genişlik 320 px'i aşarsa ona göre küçültür."""
    if en <= 0 or boy <= 0:
        return 0, 0
    yeni_en, yeni_boy = round(en * LOGO_BOY / boy), LOGO_BOY
    if yeni_en > LOGO_EN:
        yeni_en, yeni_boy = LOGO_EN, max(1, round(boy * LOGO_EN / en))
    return max(1, yeni_en), yeni_boy


AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


class Baglanti:
    """Servise bağlanır, kopunca yeniden dener; gelen her satırı işleve verir."""

    def __init__(self, gelen, koptu):
        self.gelen, self.koptu = gelen, koptu
        self.soket = None
        self.kilit = threading.Lock()
        self.merhaba = {}

    def gonder(self, mesaj: dict):
        with self.kilit:
            if self.soket is None:
                return
            try:
                self.soket.sendall((json.dumps(mesaj, ensure_ascii=False) + "\n").encode("utf-8"))
            except OSError:
                pass

    def calis(self):
        while True:
            try:
                soket = socket.create_connection(("127.0.0.1", ayar.YEREL_PORT), timeout=5)
                soket.settimeout(None)
            except OSError:
                self.koptu()
                time.sleep(3)
                continue
            with self.kilit:
                self.soket = soket
            self.gonder(dict(self.merhaba, tur="merhaba"))
            try:
                with soket.makefile("rb") as akis:
                    for satir in akis:
                        try:
                            mesaj = json.loads(satir.decode("utf-8"))
                        except ValueError:
                            continue
                        self.gelen(mesaj)
            except OSError:
                pass
            with self.kilit:
                self.soket = None
            self.koptu()
            time.sleep(2)


def _ortam_bilgisi() -> dict:
    return {
        "surum": __version__,
        "oturum_turu": os.environ.get("XDG_SESSION_TYPE", ""),
        "masaustu": os.environ.get("XDG_CURRENT_DESKTOP", ""),
        "wayland": bool(os.environ.get("WAYLAND_DISPLAY")),
    }


def calistir() -> int:
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        gi.require_version("GdkPixbuf", "2.0")
        gi.require_version("Pango", "1.0")
        from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango
    except Exception as hata:  # kitaplık yoksa servise bildirilir, tanılamada görünür
        bilgi = dict(_ortam_bilgisi(), arayuz="yok", hata=f"{type(hata).__name__}: {hata}")
        baglanti = Baglanti(lambda m: None, lambda: None)
        baglanti.merhaba = bilgi
        print(f"Ekran kitaplığı yüklenemedi: {hata}", file=sys.stderr)
        baglanti.calis()
        return 2

    class Ekran:
        def __init__(self):
            self.durum = None
            self.girilen = ""
            self.gorunur = False
            self.klavye_kilidi = "denenmedi"
            self.kilit_modu = False
            self.kopma_zamani = None
            self.bantlar = []  # her sayfanın üst bandı: (logo_kutu, logo_resmi, okul, sag)
            self.logo_pixbuf = None
            self.logo_sha = None
            # Sınav / gözetmen (A4): kod sayfası yalnız bu yardımcıda açılır (servise kod gidene dek);
            # yoklama işaretleri ızgara açıkken yalnız burada tutulur, sayfadan çıkınca silinir.
            self.gozetmen_kod_acik = False
            self.gozetmen_girilen = ""
            self.gozetmen_dokunma = 0.0
            self.izgara_oturum = None
            self.izgara_isaret: set[int] = set()
            self.izgara_dugmeleri: dict[int, tuple] = {}
            self.liste_imza = None
            self.sinav_altlari = []  # her sınav sayfasının alt satırı: (saat, bilgi, çevrimdışı düğmesi)
            # Ders yoklaması (A5): girilen kod/PIN yalnız gönderilene dek burada; liste düğmeleri
            # yoklama kapanınca yok edilir (etiketler bellekte kalmaz).
            self.yk_oturum = None
            self.yk_adim = "kod"  # "kod" | "pin"
            self.yk_kod = ""
            self.yk_pin = ""
            self.yk_liste_imza = None
            self.yk_secim_imza = None
            self.yk_dugmeler: dict[int, tuple] = {}  # id -> (düğme, etiket)
            self.yk_guncelleniyor = False

            # İki sağlayıcı: ölçüler bir kez yüklenir; renkler tema değişince yenilenir.
            ekran = Gdk.Screen.get_default()
            olcu = Gtk.CssProvider()
            olcu.load_from_data(STIL_OLCU)
            Gtk.StyleContext.add_provider_for_screen(ekran, olcu, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            self.palet = dict(ayar.VARSAYILAN_PALET)
            self.renk_saglayici = Gtk.CssProvider()
            self.renk_saglayici.load_from_data(renk_stili(self.palet).encode("ascii"))
            Gtk.StyleContext.add_provider_for_screen(
                ekran, self.renk_saglayici, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            # Giriş ekranı listesinin yazı boyu satır sayısına göre değişir (yalnız ölçü, ASCII).
            self.liste_saglayici = Gtk.CssProvider()
            self.liste_saglayici.load_from_data(b".liste-hucre { font-size: 32px; }")
            Gtk.StyleContext.add_provider_for_screen(
                ekran, self.liste_saglayici, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            # Çok satırlı duyurunun (şube oturma listesi) sütun yazı boyu da satır sayısına göre değişir.
            self.duyuru_saglayici = Gtk.CssProvider()
            self.duyuru_saglayici.load_from_data(b".duyuru-sutun { font-size: 32px; }")
            Gtk.StyleContext.add_provider_for_screen(
                ekran, self.duyuru_saglayici, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
            self.duyuru_imza = None
            self.pencere = Gtk.Window(title="Tahta Kontrol")
            self.pencere.set_decorated(False)
            self.pencere.set_keep_above(True)
            self.pencere.set_skip_taskbar_hint(True)
            self.pencere.set_skip_pager_hint(True)
            self.pencere.stick()
            self.pencere.connect("delete-event", lambda *_: True)

            self.yigin = Gtk.Stack()
            self.pencere.add(self.yigin)
            self.yigin.add_named(self._kilit_sayfasi(), "kilit")
            self.yigin.add_named(self._duyuru_sayfasi(), "duyuru")
            self.yigin.add_named(self._kapatma_sayfasi(), "kapatma")
            self.yigin.add_named(self._acil_sayfasi(), "acil")
            # Sınav ve gözetmen sayfaları da show_all()'dan ÖNCE eklenir (GtkStack tuzağı).
            self.yigin.add_named(self._sinav_giris_sayfasi(), "sinav-giris")
            self.yigin.add_named(self._sinav_sayfasi(), "sinav")
            self.yigin.add_named(self._gozetmen_kod_sayfasi(), "gozetmen-kod")
            self.yigin.add_named(self._gozetmen_menu_sayfasi(), "gozetmen-menu")
            self.yigin.add_named(self._gozetmen_yoklama_sayfasi(), "gozetmen-yoklama")
            # Ders yoklaması sayfaları (A5) da show_all()'dan ÖNCE eklenir (GtkStack tuzağı).
            self.yigin.add_named(self._yoklama_pin_sayfasi(), "yoklama-pin")
            self.yigin.add_named(self._yoklama_liste_sayfasi(), "yoklama-liste")
            self.yigin.add_named(self._yoklama_onay_sayfasi(), "yoklama-onay")
            self.yigin.add_named(self._yoklama_ileti_sayfasi(), "yoklama-ileti")
            # Fiziksel klavyeden rakam (yalnız yoklama PIN sayfasında; kilit davranışı değişmez).
            self.pencere.connect("key-press-event", self._tus_basildi)
            self.pencere_sinifi = None  # "acil" | "tatbikat" | None
            # Sayfalar pencere açılmadan görünür kılınır: GtkStack, görünür olmayan
            # bir sayfaya geçiş isteğini yok sayar ve ilk sayfada (kilit) kalır.
            self.yigin.show_all()
            # Logo gelene kadar logo kutuları gizli (pencere show() ile açılır, show_all() değil).
            for logo_kutu, *_ in self.bantlar:
                logo_kutu.set_visible(False)

            geometri = self._geometri()
            self.baglanti = Baglanti(
                lambda m: GLib.idle_add(self._mesaj, m), lambda: GLib.idle_add(self._koptu)
            )
            self.baglanti.merhaba = dict(
                _ortam_bilgisi(), arayuz="gtk3", genislik=geometri[0], yukseklik=geometri[1]
            )
            threading.Thread(target=self.baglanti.calis, daemon=True).start()
            GLib.timeout_add(1000, self._saniye)

        def _geometri(self):
            try:
                ekran = Gdk.Display.get_default().get_monitor(0).get_geometry()
                return ekran.width, ekran.height
            except Exception:
                return 0, 0

        def _etiket(self, ad, metin=""):
            etiket = Gtk.Label(label=metin)
            etiket.set_name(ad)
            etiket.set_line_wrap(True)
            etiket.set_justify(Gtk.Justification.CENTER)
            return etiket

        def _ust_bant(self):
            """Okul kimliği bandı: solda logo, yanında okul adı, sağda tahta adı · derslik."""
            bant = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=28)
            bant.set_name("ust-bant")
            logo_kutu = Gtk.Box()
            logo_kutu.set_name("logo-kutu")
            logo_kutu.set_valign(Gtk.Align.CENTER)
            logo_resmi = Gtk.Image()
            logo_kutu.pack_start(logo_resmi, False, False, 0)
            okul = Gtk.Label(label="Tahta Kontrol")
            okul.set_name("okul")
            okul.set_xalign(0)
            okul.set_line_wrap(False)
            okul.set_ellipsize(Pango.EllipsizeMode.END)
            okul.set_hexpand(True)
            sag = Gtk.Label(label="")
            sag.set_name("bant-sag")
            sag.set_xalign(1)
            sag.set_ellipsize(Pango.EllipsizeMode.END)
            sag.set_max_width_chars(40)
            bant.pack_start(logo_kutu, False, False, 0)
            bant.pack_start(okul, True, True, 0)
            bant.pack_end(sag, False, False, 0)
            self.bantlar.append((logo_kutu, logo_resmi, okul, sag))
            return bant

        def _sayfa(self, govde):
            """Sayfa iskeleti: üstte bant, altında ortalanmış gövde."""
            sayfa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            sayfa.pack_start(self._ust_bant(), False, False, 0)
            govde.set_valign(Gtk.Align.CENTER)
            govde.set_halign(Gtk.Align.CENTER)
            sayfa.pack_start(govde, True, True, 0)
            return sayfa

        def _kilit_sayfasi(self):
            govde = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=140)
            sol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            sol.set_valign(Gtk.Align.CENTER)
            self.saat = self._etiket("saat")
            self.tarih = self._etiket("tarih")
            self.kilit_yazi = self._etiket("kilit-yazi", "Bu tahta kilitlidir")
            # Program kilidinde neden ve açılış saati; idare kilidinde boş ve gizli.
            self.program_bilgi = self._etiket("program-bilgi")
            self.program_bilgi.set_max_width_chars(36)
            self.bilgi = self._etiket("bilgi")
            self.bilgi.set_max_width_chars(40)
            for parca in (self.saat, self.tarih, self.kilit_yazi, self.program_bilgi, self.bilgi):
                sol.pack_start(parca, False, False, 0)
            govde.pack_start(sol, False, False, 0)

            # Sunucuya ulaşılamayınca çıkan düğme sol sütunda, bilgi yazısının altındadır
            # ("aşağıdaki düğmeyle" metni doğru kalsın).
            self.cevrimdisi_dugmesi = Gtk.Button(label="Kilidi aç")
            self.cevrimdisi_dugmesi.set_name("ana-dugme")
            self.cevrimdisi_dugmesi.set_halign(Gtk.Align.CENTER)
            self.cevrimdisi_dugmesi.set_can_focus(False)
            self.cevrimdisi_dugmesi.connect("clicked", lambda *_: self.baglanti.gonder({"tur": "cevrimdisi_ac"}))
            sol.pack_start(self.cevrimdisi_dugmesi, False, False, 16)
            # Ders yoklaması (A5): yoklama etkin, tahta çevrimiçi ve kayıtlıysa görünür. Kilidi AÇMAZ;
            # yoklama bitince kilit ekranı geri gelir.
            self.kilit_yoklama = Gtk.Button(label="Yoklama al")
            self.kilit_yoklama.set_halign(Gtk.Align.CENTER)
            self.kilit_yoklama.set_can_focus(False)
            self.kilit_yoklama.connect("clicked", lambda *_: self.baglanti.gonder({"tur": "yoklama_ac"}))
            sol.pack_start(self.kilit_yoklama, False, False, 16)

            self.kod_kutusu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.kod_kutusu.set_halign(Gtk.Align.CENTER)
            self.kod_kutusu.set_valign(Gtk.Align.CENTER)
            self.kod_etiketi = self._etiket("kod", "")
            self.kod_kutusu.pack_start(self.kod_etiketi, False, False, 6)
            izgara = Gtk.Grid(row_spacing=10, column_spacing=10)
            tuslar = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "Sil", "0", "Aç"]
            for sira, tus in enumerate(tuslar):
                dugme = Gtk.Button(label=tus)
                dugme.set_size_request(150, 96)
                dugme.set_can_focus(False)
                if tus == "Aç":
                    dugme.set_name("ana-dugme")
                dugme.connect("clicked", self._tus, tus)
                izgara.attach(dugme, sira % 3, sira // 3, 1, 1)
            self.kod_kutusu.pack_start(izgara, False, False, 0)
            govde.pack_start(self.kod_kutusu, False, False, 0)
            return self._sayfa(govde)

        def _duyuru_sayfasi(self):
            """Bant, ortada kaydırılabilir başlık + metin (çok satırlıysa sütunlar), altta Kapat.

            Uzun metin ortayı büyütemez: Kapat düğmesi her metin uzunluğunda ekranda kalır.
            """
            kutu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30)
            kutu.set_margin_start(80)
            kutu.set_margin_end(80)
            kutu.set_valign(Gtk.Align.CENTER)
            kutu.set_halign(Gtk.Align.CENTER)
            self.duyuru_baslik = self._etiket("duyuru-baslik")
            self.duyuru_metin = self._etiket("duyuru-metin")
            self.duyuru_metin.set_max_width_chars(48)
            self.duyuru_ust = self._etiket("duyuru-ust")
            self.duyuru_sutunlar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=70)
            self.duyuru_sutunlar.set_halign(Gtk.Align.CENTER)
            for parca in (self.duyuru_baslik, self.duyuru_metin, self.duyuru_ust, self.duyuru_sutunlar):
                kutu.pack_start(parca, False, False, 0)
            kaydirma = Gtk.ScrolledWindow()
            kaydirma.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            kaydirma.set_shadow_type(Gtk.ShadowType.NONE)
            kaydirma.add(kutu)
            self.duyuru_kapat = Gtk.Button(label="Kapat")
            self.duyuru_kapat.set_halign(Gtk.Align.CENTER)
            self.duyuru_kapat.set_can_focus(False)
            self.duyuru_kapat.set_margin_top(16)
            self.duyuru_kapat.set_margin_bottom(32)
            self.duyuru_kapat.connect("clicked", lambda *_: self.baglanti.gonder({"tur": "duyuru_kapat"}))
            sayfa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            sayfa.pack_start(self._ust_bant(), False, False, 0)
            sayfa.pack_start(kaydirma, True, True, 0)
            sayfa.pack_end(self.duyuru_kapat, False, False, 0)
            return sayfa

        def _duyuru_metni_yaz(self, metin):
            if metin == self.duyuru_imza:
                return
            self.duyuru_imza = metin
            duzen = duyuru_duzeni(metin, self._geometri()[1])
            baglam = self.duyuru_metin.get_style_context()
            for sinif in ("uzun", "cok-uzun"):
                baglam.remove_class(sinif)
            for cocuk in self.duyuru_sutunlar.get_children():
                cocuk.destroy()
            if not duzen["sutunlar"]:
                if duzen["sinif"]:
                    baglam.add_class(duzen["sinif"])
                self.duyuru_metin.set_text(metin)
                self.duyuru_metin.set_visible(bool(metin))
                self.duyuru_ust.set_visible(False)
                self.duyuru_sutunlar.set_visible(False)
                return
            self.duyuru_metin.set_visible(False)
            self.duyuru_ust.set_text(duzen["ust"])
            self.duyuru_ust.set_visible(bool(duzen["ust"]))
            self.duyuru_saglayici.load_from_data(f".duyuru-sutun {{ font-size: {duzen['punto']}px; }}".encode("ascii"))
            for parca in duzen["sutunlar"]:
                etiket = Gtk.Label(label=parca)
                etiket.get_style_context().add_class("duyuru-sutun")
                etiket.set_xalign(0)
                etiket.set_valign(Gtk.Align.START)
                self.duyuru_sutunlar.pack_start(etiket, False, False, 0)
            self.duyuru_sutunlar.show_all()  # yalnız sütun kutusu; yığın sayfaları değil

        def _kapatma_sayfasi(self):
            kutu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
            kutu.set_margin_start(80)
            kutu.set_margin_end(80)
            baslik = self._etiket("kapatma-baslik", "Bu tahta kapatılacak")
            self.kapatma_sayac = self._etiket("kapatma-sayac")
            self.kapatma_neden = self._etiket("kapatma-neden")
            vazgec = Gtk.Button(label="Vazgeç — tahtayı kullanıyorum")
            vazgec.set_name("ana-dugme")
            vazgec.set_halign(Gtk.Align.CENTER)
            vazgec.set_can_focus(False)
            vazgec.connect("clicked", lambda *_: self.baglanti.gonder({"tur": "kapatma_iptal"}))
            for parca in (baslik, self.kapatma_sayac, self.kapatma_neden, vazgec):
                kutu.pack_start(parca, False, False, 0)
            return self._sayfa(kutu)

        def _acil_sayfasi(self):
            """Acil durum / tatbikat: tam ekran, okul bandı yok; renk pencere sınıfından gelir.

            Yerleşim üç kattır: üstte bant, ortada kaydırılabilir başlık + metin, altta okul ·
            saat satırı ve "yayını kapat" düğmesi. Uzun metin ortayı büyütemez: alt kat (kural 3
            düğmesi) her metin uzunluğunda ekranda kalır.
            """
            sayfa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
            sayfa.set_margin_start(80)
            sayfa.set_margin_end(80)
            sayfa.set_margin_top(40)
            sayfa.set_margin_bottom(40)
            self.acil_bant = self._etiket("acil-bant")
            self.acil_baslik = self._etiket("acil-baslik")
            self.acil_baslik.set_lines(2)
            self.acil_baslik.set_ellipsize(Pango.EllipsizeMode.END)
            self.acil_metin = self._etiket("acil-metin")
            self.acil_alt = self._etiket("acil-alt")
            # Yalnız sunucuya ulaşılamıyorken görünür; tek çevrimdışı iletisini gönderir (kural 3).
            self.acil_kapat = Gtk.Button(label="Sunucuya ulaşılamıyor — yayını kapat")
            self.acil_kapat.set_name("acil-kapat")
            self.acil_kapat.set_halign(Gtk.Align.CENTER)
            self.acil_kapat.set_can_focus(False)
            self.acil_kapat.connect("clicked", lambda *_: self.baglanti.gonder({"tur": "cevrimdisi_ac"}))

            orta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30)
            orta.set_valign(Gtk.Align.CENTER)
            orta.pack_start(self.acil_baslik, False, False, 0)
            orta.pack_start(self.acil_metin, False, False, 0)
            kaydirma = Gtk.ScrolledWindow()
            kaydirma.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            kaydirma.set_shadow_type(Gtk.ShadowType.NONE)
            kaydirma.add(orta)  # kendi Viewport'unu ekler

            alt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            alt.pack_start(self.acil_alt, False, False, 0)
            alt.pack_start(self.acil_kapat, False, False, 0)

            sayfa.pack_start(self.acil_bant, False, False, 0)
            sayfa.pack_start(kaydirma, True, True, 0)
            sayfa.pack_end(alt, False, False, 0)
            return sayfa

        # ---- sınav ve gözetmen sayfaları (A4) ------------------------------------------
        def _sayfa_dolu(self, govde):
            """Bant + ekranı dolduran gövde (liste ve ızgara sayfaları için)."""
            sayfa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            sayfa.pack_start(self._ust_bant(), False, False, 0)
            govde.set_margin_start(60)
            govde.set_margin_end(60)
            govde.set_margin_top(24)
            govde.set_margin_bottom(28)
            sayfa.pack_start(govde, True, True, 0)
            return sayfa

        def _dugme(self, metin, islev, ana=False, en=0, boy=0):
            dugme = Gtk.Button(label=metin)
            dugme.set_can_focus(False)
            if ana:
                dugme.set_name("ana-dugme")
            if en or boy:
                dugme.set_size_request(en, boy)
            dugme.connect("clicked", lambda *_: islev())
            return dugme

        def _sinav_alt(self):
            """Sınav sayfalarının alt satırı: solda saat, ortada çevrimdışı bilgisi ve düğmesi
            (kural 3), sağda "Gözetmen"."""
            alt = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
            saat = Gtk.Label(label="")
            saat.set_name("sinav-saat")
            bilgi = Gtk.Label(label="Sunucuya ulaşılamıyor. Sınav ekranı süre bitince kendiliğinden kalkar.")
            bilgi.set_name("sinav-cevrimdisi")
            bilgi.set_line_wrap(True)
            bilgi.set_max_width_chars(48)
            cevrimdisi = self._dugme("Kilidi aç", lambda: self.baglanti.gonder({"tur": "cevrimdisi_ac"}), ana=True)
            gozetmen = self._dugme("Gözetmen", self._gozetmen_ac)
            alt.pack_start(saat, False, False, 0)
            alt.pack_start(bilgi, True, True, 0)
            alt.pack_start(cevrimdisi, False, False, 0)
            alt.pack_end(gozetmen, False, False, 0)
            self.sinav_altlari.append((saat, bilgi, cevrimdisi))
            return alt

        def _sinav_giris_sayfasi(self):
            govde = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.sg_ad = self._etiket("sinav-adi")
            self.sg_ad.set_max_width_chars(60)
            self.sg_salon = self._etiket("sinav-salon")
            self.sg_bilgi = self._etiket("sinav-bilgi")
            self.sg_liste = Gtk.Grid(column_spacing=22, row_spacing=2)
            self.sg_liste.set_halign(Gtk.Align.CENTER)
            self.sg_liste.set_valign(Gtk.Align.START)
            self.sg_fazla = self._etiket("sinav-fazla")
            for parca in (self.sg_ad, self.sg_salon, self.sg_bilgi):
                govde.pack_start(parca, False, False, 0)
            govde.pack_start(self.sg_liste, True, True, 12)
            govde.pack_start(self.sg_fazla, False, False, 0)
            govde.pack_end(self._sinav_alt(), False, False, 0)
            return self._sayfa_dolu(govde)

        def _sinav_sayfasi(self):
            govde = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
            self.ss_ad = self._etiket("sinav-adi")
            self.ss_ad.set_max_width_chars(60)
            self.ss_salon = self._etiket("sinav-salon")
            self.ss_sayac = self._etiket("sinav-sayac")
            self.ss_bitis = self._etiket("sinav-bitis")
            self.ss_kurallar = self._etiket("sinav-kurallar")
            self.ss_kurallar.set_max_width_chars(80)
            # Uzun kurallar alt satırı (Gözetmen, kural 3 "Kilidi aç") ekrandan itmesin: satır sınırı
            # ve kaydırılabilir orta; alt satır her metin uzunluğunda ekranda kalır.
            self.ss_kurallar.set_lines(2)  # paragraf (kural) başına en çok 2 satır
            self.ss_kurallar.set_ellipsize(Pango.EllipsizeMode.END)
            self.ss_durum = self._etiket("sinav-durum")
            orta = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            orta.set_valign(Gtk.Align.CENTER)
            for parca in (self.ss_ad, self.ss_salon, self.ss_sayac, self.ss_bitis, self.ss_kurallar, self.ss_durum):
                orta.pack_start(parca, False, False, 0)
            kaydirma = Gtk.ScrolledWindow()
            kaydirma.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            kaydirma.set_shadow_type(Gtk.ShadowType.NONE)
            kaydirma.add(orta)
            govde.pack_start(kaydirma, True, True, 0)
            govde.pack_end(self._sinav_alt(), False, False, 0)
            return self._sayfa_dolu(govde)

        def _gozetmen_kod_sayfasi(self):
            govde = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=120)
            sol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            sol.set_valign(Gtk.Align.CENTER)
            sol.set_size_request(640, -1)  # hata metni gelince tuş takımı kaymasın
            sol.pack_start(self._etiket("gozetmen-baslik", "Gözetmen kodu"), False, False, 0)
            self.gk_salon = self._etiket("sinav-salon")
            self.gk_bilgi = self._etiket("gozetmen-bilgi", "Salon fişindeki 6 haneli kodu girin.")
            self.gk_bilgi.set_max_width_chars(34)
            self.gk_hata = self._etiket("gozetmen-hata")
            self.gk_hata.set_max_width_chars(34)
            for parca in (self.gk_salon, self.gk_bilgi, self.gk_hata):
                sol.pack_start(parca, False, False, 0)
            sol.pack_start(self._dugme("Vazgeç", self._gozetmen_vazgec), False, False, 24)
            sag = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            sag.set_valign(Gtk.Align.CENTER)
            self.gk_kod = self._etiket("kod", "")
            sag.pack_start(self.gk_kod, False, False, 6)
            self.gk_tuslar = Gtk.Grid(row_spacing=10, column_spacing=10)
            self.gk_tuslar.set_column_homogeneous(True)
            for sira, tus in enumerate(["1", "2", "3", "4", "5", "6", "7", "8", "9", "Sil", "0", "Tamam"]):
                dugme = self._dugme(tus, lambda t=tus: self._gozetmen_tus(t), ana=tus == "Tamam", en=150, boy=96)
                self.gk_tuslar.attach(dugme, sira % 3, sira // 3, 1, 1)
            sag.pack_start(self.gk_tuslar, False, False, 0)
            govde.pack_start(sol, False, False, 0)
            govde.pack_start(sag, False, False, 0)
            return self._sayfa(govde)

        def _gozetmen_menu_sayfasi(self):
            govde = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
            govde.pack_start(self._etiket("gozetmen-baslik", "Gözetmen"), False, False, 0)
            self.gm_salon = self._etiket("sinav-salon")
            govde.pack_start(self.gm_salon, False, False, 0)
            self.gm_yoklama = self._dugme("Yoklama al", lambda: self.baglanti.gonder({"tur": "gozetmen_yoklama"}),
                                          ana=True, en=560, boy=110)  # fmt: skip
            self.gm_yoklama.set_halign(Gtk.Align.CENTER)
            govde.pack_start(self.gm_yoklama, False, False, 20)
            self.gm_neden = self._etiket("gozetmen-bilgi")
            self.gm_hata = self._etiket("gozetmen-hata")
            govde.pack_start(self.gm_neden, False, False, 0)
            govde.pack_start(self.gm_hata, False, False, 0)
            cik = self._dugme("Çık", lambda: self.baglanti.gonder({"tur": "gozetmen_cikis"}), en=300, boy=90)
            cik.set_halign(Gtk.Align.CENTER)
            govde.pack_start(cik, False, False, 20)
            return self._sayfa(govde)

        def _gozetmen_yoklama_sayfasi(self):
            govde = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            self.gy_baslik = self._etiket("sinav-adi")
            self.gy_hata = self._etiket("gozetmen-hata")
            self.gy_izgara = Gtk.Grid(row_spacing=10, column_spacing=10)
            self.gy_izgara.set_row_homogeneous(True)
            self.gy_izgara.set_column_homogeneous(True)
            self.gy_izgara.set_halign(Gtk.Align.CENTER)
            self.gy_izgara.set_valign(Gtk.Align.CENTER)
            alt = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
            alt.set_halign(Gtk.Align.CENTER)
            self.gy_kaydet = self._dugme("Kaydet", self._gozetmen_kaydet, ana=True, en=320, boy=90)
            self.gy_vazgec = self._dugme("Vazgeç", lambda: self.baglanti.gonder({"tur": "gozetmen_cikis"}), en=240, boy=90)
            alt.pack_start(self.gy_kaydet, False, False, 0)
            alt.pack_start(self.gy_vazgec, False, False, 0)
            govde.pack_start(self.gy_baslik, False, False, 0)
            govde.pack_start(self.gy_hata, False, False, 0)
            govde.pack_start(self.gy_izgara, True, True, 8)
            govde.pack_end(alt, False, False, 0)
            return self._sayfa_dolu(govde)

        # ---- ders yoklaması sayfaları (A5) -----------------------------------------------
        def _yoklama_pin_sayfasi(self):
            """Öğretmen kodu (3 hane) ve PIN (6 hane): kilit tuş takımıyla aynı ölçüde 12 tuş."""
            govde = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=120)
            sol = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            sol.set_valign(Gtk.Align.CENTER)
            sol.set_size_request(720, -1)  # hata metni gelince tuş takımı kaymasın
            sol.pack_start(self._etiket("yoklama-baslik", "Ders yoklaması"), False, False, 0)
            self.yp_bilgi = self._etiket("yoklama-bilgi")
            self.yp_bilgi.set_max_width_chars(40)
            self.yp_sube = self._etiket("yoklama-bilgi")
            self.yp_adim = self._etiket("yoklama-adim")
            self.yp_adim.set_max_width_chars(36)
            self.yp_hata = self._etiket("yoklama-hata")
            self.yp_hata.set_max_width_chars(36)
            ipucu = self._etiket("yoklama-bilgi", "PIN'i girerken tuş takımını elinizle kapatın.")
            ipucu.set_max_width_chars(40)
            for parca in (self.yp_bilgi, self.yp_sube, self.yp_adim, self.yp_hata, ipucu):
                sol.pack_start(parca, False, False, 0)
            vazgec = self._dugme("Vazgeç", lambda: self.baglanti.gonder({"tur": "yoklama_kapat"}), en=300, boy=90)
            vazgec.set_halign(Gtk.Align.CENTER)
            sol.pack_start(vazgec, False, False, 24)
            sag = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            sag.set_valign(Gtk.Align.CENTER)
            self.yp_kod = self._etiket("kod", "")
            sag.pack_start(self.yp_kod, False, False, 6)
            self.yp_tuslar = Gtk.Grid(row_spacing=10, column_spacing=10)
            self.yp_tuslar.set_column_homogeneous(True)
            for sira, tus in enumerate(["1", "2", "3", "4", "5", "6", "7", "8", "9", "Sil", "0", "Tamam"]):
                dugme = self._dugme(tus, lambda t=tus: self._yoklama_tus(t), ana=tus == "Tamam", en=150, boy=96)
                self.yp_tuslar.attach(dugme, sira % 3, sira // 3, 1, 1)
            sag.pack_start(self.yp_tuslar, False, False, 0)
            govde.pack_start(sol, False, False, 0)
            govde.pack_start(sag, False, False, 0)
            return self._sayfa(govde)

        def _yoklama_liste_sayfasi(self):
            """Üst satır (şube · ders · öğretmen · kalan süre), ortada kaydırılabilir öğrenci düğmeleri
            ya da şube/ders saati seçimi, altta "Yok: 2 · Mevcut: 32/34" [Vazgeç] [Kaydet]."""
            govde = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            ust = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
            self.yl_ust = Gtk.Label(label="")
            self.yl_ust.set_name("yoklama-ust")
            self.yl_ust.set_xalign(0)
            self.yl_ust.set_ellipsize(Pango.EllipsizeMode.END)
            self.yl_degistir = self._dugme("Şube / saat", lambda: self.baglanti.gonder({"tur": "yoklama_sec", "ders_no": None}))
            self.yl_kalan = Gtk.Label(label="")
            self.yl_kalan.set_name("yoklama-kalan")
            ust.pack_start(self.yl_ust, True, True, 0)
            ust.pack_end(self.yl_kalan, False, False, 0)
            ust.pack_end(self.yl_degistir, False, False, 0)
            self.yl_bilgi = Gtk.Label(label="")
            self.yl_bilgi.set_name("yoklama-bilgi")
            self.yl_bilgi.set_xalign(0)
            self.yl_bilgi.set_line_wrap(True)
            self.yl_hata = Gtk.Label(label="")
            self.yl_hata.set_name("yoklama-hata")
            self.yl_hata.set_xalign(0)
            self.yl_hata.set_line_wrap(True)

            self.yl_akis = Gtk.FlowBox()
            self.yl_akis.set_selection_mode(Gtk.SelectionMode.NONE)
            self.yl_akis.set_homogeneous(True)
            self.yl_akis.set_max_children_per_line(YOKLAMA_SUTUN_EN_COK)
            self.yl_akis.set_row_spacing(12)
            self.yl_akis.set_column_spacing(12)
            self.yl_akis.set_valign(Gtk.Align.START)
            self.yl_kaydirma = Gtk.ScrolledWindow()
            self.yl_kaydirma.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self.yl_kaydirma.set_shadow_type(Gtk.ShadowType.NONE)
            self.yl_kaydirma.add(self.yl_akis)

            secim = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            self.yl_sube_baslik = Gtk.Label(label="Şube")
            self.yl_sube_baslik.set_name("yoklama-adim")
            self.yl_sube_baslik.set_xalign(0)
            self.yl_subeler = Gtk.FlowBox()
            self.yl_dersler = Gtk.FlowBox()
            for akis in (self.yl_subeler, self.yl_dersler):
                akis.set_selection_mode(Gtk.SelectionMode.NONE)
                akis.set_homogeneous(True)
                akis.set_max_children_per_line(8)
                akis.set_row_spacing(10)
                akis.set_column_spacing(10)
                akis.set_valign(Gtk.Align.START)
            ders_baslik = Gtk.Label(label="Ders saati")
            ders_baslik.set_name("yoklama-adim")
            ders_baslik.set_xalign(0)
            for parca in (self.yl_sube_baslik, self.yl_subeler, ders_baslik, self.yl_dersler):
                secim.pack_start(parca, False, False, 0)
            self.yl_secim = Gtk.ScrolledWindow()
            self.yl_secim.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            self.yl_secim.set_shadow_type(Gtk.ShadowType.NONE)
            self.yl_secim.add(secim)

            alt = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
            self.yl_sayi = Gtk.Label(label="")
            self.yl_sayi.set_name("yoklama-sayi")
            self.yl_sayi.set_xalign(0)
            self.yl_kaydet = self._dugme("Kaydet", lambda: self.baglanti.gonder({"tur": "yoklama_kaydet"}), ana=True, en=300, boy=90)
            vazgec = self._dugme("Vazgeç", lambda: self.baglanti.gonder({"tur": "yoklama_kapat"}), en=240, boy=90)
            alt.pack_start(self.yl_sayi, True, True, 0)
            alt.pack_end(self.yl_kaydet, False, False, 0)
            alt.pack_end(vazgec, False, False, 0)

            govde.pack_start(ust, False, False, 0)
            govde.pack_start(self.yl_bilgi, False, False, 0)
            govde.pack_start(self.yl_hata, False, False, 0)
            govde.pack_start(self.yl_kaydirma, True, True, 4)
            govde.pack_start(self.yl_secim, True, True, 4)
            govde.pack_end(alt, False, False, 0)
            return self._sayfa_dolu(govde)

        def _yoklama_onay_sayfasi(self):
            govde = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
            self.yo_ust = self._etiket("yoklama-bilgi")
            self.yo_baslik = self._etiket("yoklama-baslik")
            self.yo_liste = self._etiket("yoklama-onay-liste")
            self.yo_liste.set_max_width_chars(60)
            self.yo_hata = self._etiket("yoklama-hata")
            self.yo_hata.set_max_width_chars(50)
            dugmeler = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=24)
            dugmeler.set_halign(Gtk.Align.CENTER)
            self.yo_geri = self._dugme("Geri", lambda: self.baglanti.gonder({"tur": "yoklama_geri"}), en=300, boy=96)
            self.yo_onayla = self._dugme("Onayla", lambda: self.baglanti.gonder({"tur": "yoklama_onayla"}), ana=True, en=300, boy=96)
            dugmeler.pack_start(self.yo_geri, False, False, 0)
            dugmeler.pack_start(self.yo_onayla, False, False, 0)
            for parca in (self.yo_ust, self.yo_baslik, self.yo_liste, self.yo_hata):
                govde.pack_start(parca, False, False, 0)
            govde.pack_start(dugmeler, False, False, 16)
            return self._sayfa(govde)

        def _yoklama_ileti_sayfasi(self):
            govde = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=40)
            self.yi_metin = self._etiket("yoklama-ileti")
            self.yi_metin.set_max_width_chars(40)
            self.yi_kapat = self._dugme("Kapat", lambda: self.baglanti.gonder({"tur": "yoklama_kapat"}), en=300, boy=90)
            self.yi_kapat.set_halign(Gtk.Align.CENTER)
            govde.pack_start(self.yi_metin, False, False, 0)
            govde.pack_start(self.yi_kapat, False, False, 0)
            return self._sayfa(govde)

        def _pencere_sinifi(self, sinif):
            """Acil/tatbikat rengini pencereye verir; başka sayfaya geçince kaldırır."""
            if sinif == self.pencere_sinifi:
                return
            baglam = self.pencere.get_style_context()
            if self.pencere_sinifi:
                baglam.remove_class(self.pencere_sinifi)
            if sinif:
                baglam.add_class(sinif)
            self.pencere_sinifi = sinif

        def _acil_alt_yaz(self):
            okul = (self.durum or {}).get("okul_adi") or "Tahta Kontrol"
            self.acil_alt.set_text(f"{okul} · {time.strftime('%H:%M')}")

        # ---- olaylar ---------------------------------------------------------
        def _tus(self, _dugme, tus):
            if tus == "Sil":
                self.girilen = self.girilen[:-1]
            elif tus == "Aç":
                if self.girilen:
                    self.baglanti.gonder({"tur": "kod", "kod": self.girilen})
                self.girilen = ""
            elif len(self.girilen) < 8:
                self.girilen += tus
            self.kod_etiketi.set_text("●" * len(self.girilen))

        # ---- gözetmen (A4) ------------------------------------------------------------
        def _gozetmen_ac(self):
            self.gozetmen_kod_acik = True
            self.gozetmen_girilen = ""
            self.gozetmen_dokunma = time.time()
            self.gk_kod.set_text("")
            self._ciz()

        def _gozetmen_vazgec(self):
            self.gozetmen_kod_acik = False
            self.gozetmen_girilen = ""
            self.gk_kod.set_text("")
            self.baglanti.gonder({"tur": "gozetmen_cikis"})  # servis eski hata metnini de siler
            self._ciz()

        def _gozetmen_tus(self, tus):
            self.gozetmen_dokunma = time.time()
            if tus == "Sil":
                self.gozetmen_girilen = self.gozetmen_girilen[:-1]
            elif tus == "Tamam":
                if self.gozetmen_girilen:
                    # Kod servise iletilir, sunucuda doğrulanır; burada saklanmaz.
                    self.baglanti.gonder({"tur": "gozetmen_kod", "kod": self.gozetmen_girilen})
                self.gozetmen_girilen = ""
            elif len(self.gozetmen_girilen) < 6:
                self.gozetmen_girilen += tus
            self.gk_kod.set_text("●" * len(self.gozetmen_girilen))

        def _gozetmen_kaydet(self):
            self.baglanti.gonder({"tur": "gozetmen_kaydet", "gelmeyen": sorted(self.izgara_isaret)})

        def _koltuk_degisti(self, dugme, oge):
            koltuk = oge["k"]
            if dugme.get_active():
                self.izgara_isaret.add(koltuk)
            else:
                self.izgara_isaret.discard(koltuk)
            dugme.set_label(koltuk_etiketi(oge, dugme.get_active()))
            self._izgara_basligi()

        def _izgara_basligi(self):
            self.gy_baslik.set_text(f"Gelmeyenlere dokunun · Gelmeyen: {len(self.izgara_isaret)}")

        def _izgara_temizle(self):
            """Yoklama ızgarası kapanınca düğmeler ve işaretler silinir (ekranda iz kalmaz)."""
            for cocuk in self.gy_izgara.get_children():
                cocuk.destroy()
            self.izgara_dugmeleri = {}
            self.izgara_isaret = set()
            self.izgara_oturum = None

        def _izgara_kur(self, gozetmen):
            self._izgara_temizle()
            liste = gozetmen.get("liste") or []
            self.izgara_isaret = {k for k in gozetmen.get("gelmeyen") or [] if isinstance(k, int)}
            n = len(liste)
            sutun = izgara_sutun(n)
            satir = max(1, -(-n // sutun))
            en, boy = self._geometri()
            en, boy = en or 1920, boy or 1080
            dugme_en = max(120, min(260, (en - 120) // sutun - 10))
            dugme_boy = max(80, min(170, (boy - 430) // satir - 10))
            for sira, oge in enumerate(liste):
                gelmedi = oge["k"] in self.izgara_isaret
                dugme = Gtk.ToggleButton(label=koltuk_etiketi(oge, gelmedi))
                dugme.set_name("koltuk")
                dugme.set_can_focus(False)
                dugme.set_size_request(dugme_en, dugme_boy)
                dugme.set_active(gelmedi)
                etiket = dugme.get_child()
                if isinstance(etiket, Gtk.Label):
                    etiket.set_justify(Gtk.Justification.CENTER)
                dugme.connect("toggled", self._koltuk_degisti, oge)
                self.gy_izgara.attach(dugme, sira % sutun, sira // sutun, 1, 1)
                self.izgara_dugmeleri[oge["k"]] = (dugme, oge)
            self.gy_izgara.show_all()  # yalnız ızgaranın içi (pencere değil)
            self.izgara_oturum = gozetmen.get("oturum")
            self._izgara_basligi()

        def _liste_kur(self, liste):
            imza = json.dumps(liste, ensure_ascii=False, sort_keys=True)
            if imza == self.liste_imza:
                return
            self.liste_imza = imza
            for cocuk in self.sg_liste.get_children():
                cocuk.destroy()
            if not liste:
                return
            n = len(liste)
            sutun = liste_sutun_sayisi(n)
            satir = -(-n // sutun)
            punto = liste_punto(satir, self._geometri()[1])
            self.liste_saglayici.load_from_data(f".liste-hucre {{ font-size: {punto}px; }}".encode("ascii"))
            for sira, oge in enumerate(liste):
                kolon, satir_no = divmod(sira, satir)  # koltuk sırası sütun sütun yukarıdan aşağı
                for j, metin in enumerate(liste_hucreleri(oge)):
                    etiket = Gtk.Label(label=metin)
                    baglam = etiket.get_style_context()
                    baglam.add_class("liste-hucre")
                    if j == 0:
                        baglam.add_class("liste-no")
                    etiket.set_xalign(1 if j == 0 else 0)
                    self.sg_liste.attach(etiket, kolon * 5 + j, satir_no, 1, 1)
                if satir_no == 0 and kolon < sutun - 1:
                    ara = Gtk.Label(label="")
                    ara.set_size_request(56, -1)
                    self.sg_liste.attach(ara, kolon * 5 + 4, 0, 1, 1)
            self.sg_liste.show_all()

        # ---- ders yoklaması (A5) ------------------------------------------------------------
        def _tus_basildi(self, _pencere, olay):
            """Fiziksel klavye: yalnız yoklama PIN sayfasında rakam, BackSpace (Sil), Enter (Tamam)."""
            if self.yigin.get_visible_child_name() != "yoklama-pin" or not self.yp_tuslar.get_sensitive():
                return False
            ad = Gdk.keyval_name(olay.keyval) or ""
            ad = ad[3:] if ad.startswith("KP_") else ad
            if len(ad) == 1 and ad.isdigit():
                self._yoklama_tus(ad)
            elif ad == "BackSpace":
                self._yoklama_tus("Sil")
            elif ad in ("Return", "Enter"):
                self._yoklama_tus("Tamam")
            else:
                return False
            return True

        def _yoklama_tus(self, tus):
            if tus == "Sil":
                if self.yk_adim == "pin" and not self.yk_pin:
                    self.yk_adim = "kod"  # boş PIN'de Sil: öğretmen kodunu düzeltmeye dön
                elif self.yk_adim == "pin":
                    self.yk_pin = self.yk_pin[:-1]
                else:
                    self.yk_kod = self.yk_kod[:-1]
            elif tus == "Tamam":
                if self.yk_adim == "kod" and len(self.yk_kod) == YOKLAMA_KOD_HANE:
                    self.yk_adim = "pin"
                elif self.yk_adim == "pin" and len(self.yk_pin) == YOKLAMA_PIN_HANE:
                    # PIN servise iletilir ve sunucuda doğrulanır; burada saklanmaz.
                    self.baglanti.gonder({"tur": "yoklama_pin", "kod": self.yk_kod, "pin": self.yk_pin})
                    self.yk_pin = ""
            elif self.yk_adim == "kod":
                self.yk_kod = (self.yk_kod + tus)[:YOKLAMA_KOD_HANE]
                if len(self.yk_kod) == YOKLAMA_KOD_HANE:
                    self.yk_adim = "pin"  # üçüncü haneden sonra PIN'e geçilir
            elif len(self.yk_pin) < YOKLAMA_PIN_HANE:
                self.yk_pin += tus
            self._yoklama_pin_yaz()

        def _yoklama_pin_yaz(self):
            if self.yk_adim == "kod":
                self.yp_adim.set_text("Öğretmen kodunuz (3 hane)")
                # Öğretmen kodu gizli değildir; PIN yalnız nokta olarak görünür.
                self.yp_kod.set_text(self.yk_kod + "_" * (YOKLAMA_KOD_HANE - len(self.yk_kod)))
            else:
                self.yp_adim.set_text(f"PIN (6 hane) · öğretmen kodu {self.yk_kod}")
                self.yp_kod.set_text("●" * len(self.yk_pin) + "○" * (YOKLAMA_PIN_HANE - len(self.yk_pin)))

        def _yoklama_liste_temizle(self):
            """Öğrenci düğmeleri yok edilir: etiketler pencerede ve bellekte kalmaz."""
            for cocuk in self.yl_akis.get_children():
                cocuk.destroy()
            self.yk_dugmeler = {}
            self.yk_liste_imza = None

        def _yoklama_temizle(self):
            self._yoklama_liste_temizle()
            for akis in (self.yl_subeler, self.yl_dersler):
                for cocuk in akis.get_children():
                    cocuk.destroy()
            self.yk_secim_imza = None
            self.yk_oturum = None
            self.yk_adim, self.yk_kod, self.yk_pin = "kod", "", ""
            self.yp_kod.set_text("")
            # Onay ve liste sayfasındaki etiketler (yok yazılanların maskeli adları) de bellekte kalmaz.
            for etiket in (self.yo_ust, self.yo_baslik, self.yo_liste, self.yl_ust, self.yl_bilgi):
                etiket.set_text("")

        def _ogrenci_etiketi(self, dugme, metin):
            """Düğme metni; set_label etiketi yeniden kurduğu için ortalama her seferinde yeniden verilir."""
            dugme.set_label(metin)
            baglam = dugme.get_style_context()
            if ogrenci_uzun_mu(metin.split("\n", 1)[0]):
                baglam.add_class("uzun")
            else:
                baglam.remove_class("uzun")
            etiket = dugme.get_child()
            if isinstance(etiket, Gtk.Label):
                etiket.set_justify(Gtk.Justification.CENTER)
                etiket.set_ellipsize(Pango.EllipsizeMode.END)  # satır satır: ek ve "YOK" ikinci satırda kesilmez

        def _ogrenci_degisti(self, dugme, oge):
            if self.yk_guncelleniyor:
                return
            self._ogrenci_etiketi(dugme, ogrenci_dugme_metni(oge["etiket"], dugme.get_active()))
            self.baglanti.gonder({"tur": "yoklama_isaret", "id": oge["id"]})
            yok = sum(1 for d, _ in self.yk_dugmeler.values() if d.get_active())
            self.yl_sayi.set_text(yoklama_sayi_metni(yok, len(self.yk_dugmeler)))

        def _yoklama_izgara_kur(self, yoklama, imza):
            self._yoklama_liste_temizle()
            yok = set(yoklama.get("yok") or [])
            self.yl_akis.set_min_children_per_line(yoklama_sutun(self._geometri()[0]))
            for oge in yoklama.get("ogrenciler") or []:
                isaretli = oge["id"] in yok
                dugme = Gtk.ToggleButton(label=ogrenci_dugme_metni(oge["etiket"], isaretli))
                dugme.set_name("ogrenci")
                dugme.set_can_focus(False)
                dugme.set_size_request(YOKLAMA_DUGME_EN, YOKLAMA_DUGME_BOY)
                dugme.set_active(isaretli)
                self._ogrenci_etiketi(dugme, ogrenci_dugme_metni(oge["etiket"], isaretli))
                dugme.connect("toggled", self._ogrenci_degisti, oge)
                self.yl_akis.add(dugme)
                self.yk_dugmeler[oge["id"]] = (dugme, oge["etiket"])
            self.yl_akis.show_all()  # yalnız akışın içi (yığın sayfaları değil)
            self.yk_liste_imza = imza

        def _yoklama_isaretleri_esitle(self, yok: set):
            """Servisin işaretleriyle düğmeleri eşitler; ızgara yeniden kurulmaz."""
            self.yk_guncelleniyor = True
            try:
                for kimlik, (dugme, etiket) in self.yk_dugmeler.items():
                    if dugme.get_active() != (kimlik in yok):
                        dugme.set_active(kimlik in yok)
                        self._ogrenci_etiketi(dugme, ogrenci_dugme_metni(etiket, kimlik in yok))
            finally:
                self.yk_guncelleniyor = False

        def _yoklama_secim_kur(self, yoklama):
            subeler = yoklama.get("subeler") or []
            dersler = yoklama.get("ders_saatleri") or []
            sube, ders_no, istek = yoklama.get("sube"), yoklama.get("ders_no"), bool(yoklama.get("istek"))
            imza = (yoklama.get("oturum"), sube, ders_no, istek, tuple(subeler),
                    tuple((d.get("ders_no"), d.get("secilebilir"), d.get("metin")) for d in dersler))  # fmt: skip
            if imza == self.yk_secim_imza:
                return
            self.yk_secim_imza = imza
            for akis in (self.yl_subeler, self.yl_dersler):
                for cocuk in akis.get_children():
                    cocuk.destroy()
            self.yl_sube_baslik.set_text("Şube" if subeler else "Şube · öğrenci listesi yüklenmemiş; okul idaresine bildirin.")
            for s in subeler:
                dugme = self._dugme(s, lambda s=s: self.baglanti.gonder({"tur": "yoklama_sec", "sube": s}), ana=s == sube, en=200, boy=80)
                if s != sube:
                    dugme.set_name("secim")
                dugme.set_sensitive(not istek)
                self.yl_subeler.add(dugme)
            for d in dersler:
                no = d.get("ders_no")
                dugme = self._dugme(str(d.get("metin") or f"{no}. ders"),
                                    lambda no=no: self.baglanti.gonder({"tur": "yoklama_sec", "sube": sube, "ders_no": no}),
                                    ana=no == ders_no, en=330, boy=80)  # fmt: skip
                if no != ders_no:
                    dugme.set_name("secim")
                dugme.set_sensitive(bool(sube) and bool(d.get("secilebilir")) and not istek)
                self.yl_dersler.add(dugme)
            self.yl_subeler.show_all()
            self.yl_dersler.show_all()

        def _yoklama_liste_ciz(self, yoklama):
            istek = bool(yoklama.get("istek"))
            self.yl_ust.set_text(yoklama_ust_metni(yoklama))
            kalan = yoklama.get("kalan")
            self.yl_kalan.set_text(f"Kalan {sayac_metni(kalan)}" if kalan is not None else "")
            hata = yoklama.get("hata") or ("Süre dolmak üzere; kaydedin." if yoklama.get("uyari") else "")
            self.yl_hata.set_text(hata)
            self.yl_hata.set_visible(bool(hata))
            liste_yuklu = bool(yoklama.get("liste_yuklu"))
            if liste_yuklu:
                ogrenciler = yoklama.get("ogrenciler") or []
                imza = (yoklama.get("oturum"), yoklama.get("sube"), yoklama.get("ders_no"), tuple(o.get("id") for o in ogrenciler))
                if imza != self.yk_liste_imza:
                    self._yoklama_izgara_kur(yoklama, imza)
                else:
                    self._yoklama_isaretleri_esitle(set(yoklama.get("yok") or []))
                bilgi = [yoklama.get("liste_ileti") or ("Yalnız derste olmayan öğrencilere dokunun; dokunulmayanlar “var” sayılır."
                                                         if ogrenciler else "")]  # fmt: skip
                if yoklama.get("baska_yoklama"):
                    bilgi.append("Bu ders saatinde başka bir yoklama da var; ikisi birleştirilir.")
                self.yl_bilgi.set_text("  ".join(p for p in bilgi if p))
                self.yl_sayi.set_text(yoklama_sayi_metni(len(yoklama.get("yok") or []), len(ogrenciler)) if ogrenciler else "")
                self.yl_kaydet.set_sensitive(bool(ogrenciler) and not istek)
            else:
                self._yoklama_liste_temizle()
                self._yoklama_secim_kur(yoklama)
                self.yl_bilgi.set_text("Liste yükleniyor…" if istek else "Şubeyi ve ders saatini seçin.")
                self.yl_sayi.set_text("")
                self.yl_kaydet.set_sensitive(False)
            self.yl_bilgi.set_visible(bool(self.yl_bilgi.get_text()))
            self.yl_kaydirma.set_visible(liste_yuklu)
            self.yl_secim.set_visible(not liste_yuklu)
            self.yl_degistir.set_visible(liste_yuklu)
            self.yl_degistir.set_sensitive(not istek)

        def _yoklama_ciz(self, yoklama):
            asama = yoklama.get("asama")
            if yoklama.get("oturum") != self.yk_oturum:
                self._yoklama_temizle()
                self.yk_oturum = yoklama.get("oturum")
            if asama in ("yukleniyor", "ileti"):
                self._yoklama_liste_temizle()
                self.yi_metin.set_text(yoklama.get("ileti") or "Yoklama açılıyor…")
                self.yi_kapat.set_label("Kapat" if asama == "ileti" else "Vazgeç")
                self.yigin.set_visible_child_name("yoklama-ileti")
            elif asama == "pin":
                self._yoklama_liste_temizle()
                bilgi = " · ".join(p for p in (yoklama.get("tarih_yazi"), yoklama.get("ders_metni")) if p)
                self.yp_bilgi.set_text(bilgi or "Ders yoklaması")
                self.yp_sube.set_text(f"Şube: {yoklama['sube']}" if yoklama.get("sube") else "Şube ve ders saati PIN'den sonra seçilir.")
                hata = yoklama_pin_hatasi(yoklama)
                self.yp_hata.set_text(hata)
                self.yp_hata.set_visible(bool(hata))
                self.yp_tuslar.set_sensitive(not yoklama.get("istek") and not int(yoklama.get("bekleme") or 0))
                self._yoklama_pin_yaz()
                self.yigin.set_visible_child_name("yoklama-pin")
            elif asama == "liste":
                self._yoklama_liste_ciz(yoklama)
                self.yigin.set_visible_child_name("yoklama-liste")
            else:  # onay | kaydediliyor
                yok = set(yoklama.get("yok") or [])
                baslik, liste = yoklama_onay_metni([o["etiket"] for o in yoklama.get("ogrenciler") or [] if o.get("id") in yok])
                self.yo_ust.set_text(yoklama_ust_metni(yoklama))
                self.yo_baslik.set_text(baslik)
                self.yo_liste.set_text(liste)
                self.yo_liste.set_visible(bool(liste))
                kaydediliyor = asama == "kaydediliyor"
                hata = "Kaydediliyor…" if kaydediliyor else yoklama.get("hata") or ""
                self.yo_hata.set_text(hata)
                self.yo_hata.set_visible(bool(hata))
                self.yo_geri.set_sensitive(not kaydediliyor)
                self.yo_onayla.set_sensitive(not kaydediliyor)
                self.yigin.set_visible_child_name("yoklama-onay")

        def _sinav_alt_ciz(self):
            durum = self.durum or {}
            cevrimdisi = bool(durum.get("cevrimdisi")) or not durum.get("kayitli", True)
            for saat, bilgi, dugme in self.sinav_altlari:
                saat.set_text(time.strftime("%H:%M"))
                bilgi.set_visible(cevrimdisi)
                dugme.set_visible(cevrimdisi)

        def _sinav_sayaclari(self, sinav):
            if sinav.get("evre") == "giris":
                self.sg_bilgi.set_text(baslama_metni(sinav.get("baslangic_saat", ""), sinav.get("kalan_baslama", 0)))
            else:
                kalan = int(sinav.get("kalan_bitis", 0))
                self.ss_sayac.set_text(sayac_metni(kalan))
                baglam = self.ss_sayac.get_style_context()
                if kalan <= SINAV_SON_DAKIKALAR_SN:
                    baglam.add_class("son")
                else:
                    baglam.remove_class("son")
            self._sinav_alt_ciz()

        def _sinav_ciz(self, sinav):
            if sinav.get("evre") == "giris":
                self.sg_ad.set_text(sinav.get("sinav_adi") or "Sınav")
                self.sg_salon.set_text(sinav.get("salon_adi") or "")
                liste = sinav.get("liste") or []
                self._liste_kur(liste)
                fazla = int(sinav.get("liste_fazla") or 0)
                self.sg_fazla.set_text(f"ve {fazla} kişi daha — salon listesine bakın" if fazla else "")
                self.sg_fazla.set_visible(bool(fazla))
                self.yigin.set_visible_child_name("sinav-giris")
            else:
                self._liste_kur([])  # sınav başladı: liste ekrandan silinir
                self.ss_ad.set_text(sinav.get("sinav_adi") or "Sınav")
                self.ss_salon.set_text(sinav.get("salon_adi") or "")
                self.ss_bitis.set_text(bitis_metni(sinav))
                kurallar = kurallar_metni(sinav.get("kurallar") or "")
                self.ss_kurallar.set_text(kurallar)
                self.ss_kurallar.set_visible(bool(kurallar))
                durum_metni = sinav.get("bildirim") or ("Yoklama alındı" if sinav.get("yoklama_alindi") else "")
                self.ss_durum.set_text(durum_metni)
                self.ss_durum.set_visible(bool(durum_metni))
                self.yigin.set_visible_child_name("sinav")
            self._sinav_sayaclari(sinav)
            self._goster(kilit=True)

        def _gozetmen_ciz(self, sinav, gozetmen):
            durum = gozetmen.get("durum")
            salon = sinav.get("salon_adi") or ""
            if durum in ("yoklama", "kaydediliyor"):
                self.gozetmen_kod_acik = False
                if self.izgara_oturum != gozetmen.get("oturum"):
                    self._izgara_kur(gozetmen)
                kaydediliyor = durum == "kaydediliyor"
                self.gy_hata.set_text("Kaydediliyor…" if kaydediliyor else gozetmen.get("hata") or "")
                self.gy_kaydet.set_sensitive(not kaydediliyor)
                self.gy_vazgec.set_sensitive(not kaydediliyor)
                self.gy_izgara.set_sensitive(not kaydediliyor)
                self.yigin.set_visible_child_name("gozetmen-yoklama")
            elif durum == "menu":
                self.gozetmen_kod_acik = False
                self._izgara_temizle()
                engel = yoklama_engeli(gozetmen)
                self.gm_salon.set_text(salon)
                self.gm_yoklama.set_sensitive(not engel)
                self.gm_neden.set_text(engel)
                self.gm_neden.set_visible(bool(engel))
                self.gm_hata.set_text(gozetmen.get("hata") or "")
                self.gm_hata.set_visible(bool(gozetmen.get("hata")))
                self.yigin.set_visible_child_name("gozetmen-menu")
            else:
                self._izgara_temizle()
                dogrulaniyor = durum == "dogrulaniyor"
                bekleme = int(gozetmen.get("bekleme") or 0)
                self.gk_salon.set_text(salon)
                hata = gozetmen_kod_hatasi(gozetmen)
                self.gk_hata.set_text(hata)
                self.gk_hata.set_visible(bool(hata))
                self.gk_tuslar.set_sensitive(not dogrulaniyor and not bekleme)
                self.yigin.set_visible_child_name("gozetmen-kod")
            self._goster(kilit=True)

        def _mesaj(self, mesaj):
            if mesaj.get("tur") == "yeniden_baslat":
                os.execv(sys.executable, [sys.executable, "-m", "tahta_ajan", "ekran"])
            if mesaj.get("tur") == "marka":
                self._marka(mesaj)
                if self.durum:
                    self._ciz()
            if mesaj.get("tur") == "durum":
                self.kopma_zamani = None
                self.durum = mesaj
                self._renkleri_uygula(mesaj.get("tema"))
                self._ciz()
            return False

        def _marka(self, mesaj):
            """Servisten gelen logoyu yükler. Her hata yutulur: ekran logosuz ama çalışır."""
            self.logo_pixbuf, self.logo_sha = None, None
            metin, sha = mesaj.get("logo"), mesaj.get("sha256")
            if not (isinstance(metin, str) and isinstance(sha, str)) or len(metin) > LOGO_METIN_SINIRI:
                return
            try:
                veri = base64.b64decode(metin, validate=True)
                if not ayar.logo_gecerli(veri):
                    return
                yukleyici = GdkPixbuf.PixbufLoader()
                yukleyici.write(veri)
                yukleyici.close()
                resim = yukleyici.get_pixbuf()
                en, boy = logo_olcusu(resim.get_width(), resim.get_height())
                if not en:
                    return
                self.logo_pixbuf = resim.scale_simple(en, boy, GdkPixbuf.InterpType.BILINEAR)
                self.logo_sha = sha
            except Exception as hata:
                print(f"Logo yüklenemedi: {hata}", file=sys.stderr)
                self.logo_pixbuf, self.logo_sha = None, None

        def _renkleri_uygula(self, tema):
            palet = ayar.palet_dogrula(tema) or dict(ayar.VARSAYILAN_PALET)
            if palet != self.palet:
                self.palet = palet
                # Aynı sağlayıcıya yeniden yüklemek önceki renk kurallarının yerine geçer.
                self.renk_saglayici.load_from_data(renk_stili(palet).encode("ascii"))

        def _bantlari_ciz(self, durum):
            okul = durum.get("okul_adi") or "Tahta Kontrol"
            sag = " · ".join(p for p in (durum.get("tahta_adi"), durum.get("derslik")) if p)
            sha = durum.get("logo_sha256")
            logo_var = bool(sha) and sha == self.logo_sha and self.logo_pixbuf is not None
            for logo_kutu, logo_resmi, okul_etiketi, sag_etiketi in self.bantlar:
                okul_etiketi.set_text(okul)
                sag_etiketi.set_text(sag)
                if logo_var:
                    logo_resmi.set_from_pixbuf(self.logo_pixbuf)
                logo_kutu.set_visible(logo_var)

        def _koptu(self):
            if self.kopma_zamani is None:
                self.kopma_zamani = time.time()
            return False

        def _saniye(self):
            simdi = time.localtime()
            self.saat.set_text(time.strftime("%H:%M", simdi))
            self.tarih.set_text(f"{simdi.tm_mday} {AYLAR[simdi.tm_mon - 1]} {simdi.tm_year} {GUNLER[simdi.tm_wday]}")
            # Servis 10 saniyedir yoksa pencere kapanır (kilit rehin tutmaz).
            if self.kopma_zamani and time.time() - self.kopma_zamani > 10 and self.gorunur:
                self.durum = None
                self._ciz()
            if self.durum and self.durum.get("kapatma"):
                self.durum["kapatma"]["kalan"] = max(0, self.durum["kapatma"]["kalan"] - 1)
                self.kapatma_sayac.set_text(str(self.durum["kapatma"]["kalan"]))
            if self.durum and self.durum.get("acil"):
                self.durum["acil"]["kalan"] -= 1
                if self.durum["acil"]["kalan"] <= 0:
                    self.durum["acil"] = None  # bir alt önceliğe düşer
                    self._ciz()
                else:
                    self._acil_alt_yaz()
            if self.durum and self.durum.get("duyuru"):
                self.durum["duyuru"]["kalan"] -= 1
                if self.durum["duyuru"]["kalan"] <= 0:
                    self.durum["duyuru"] = None
                    self._ciz()
            sinav = self.durum.get("sinav") if self.durum else None
            if sinav:
                # Sayaç saniyede bir azalır; kaynak her "durum" iletisinde servisten gelen kalan süredir.
                sinav["kalan_bitis"] = int(sinav.get("kalan_bitis", 0)) - 1
                sinav["kalan_baslama"] = max(0, int(sinav.get("kalan_baslama", 0)) - 1)
                if sinav["kalan_bitis"] <= 0:
                    self.durum["sinav"] = None  # servisten bağımsız: süre bitince ekran kalkar
                    self._ciz()
                elif sinav.get("evre") == "giris" and sinav["kalan_baslama"] <= 0:
                    sinav["evre"], sinav["liste"] = "suruyor", []  # başlangıç: liste kalkar, sayaç gelir
                    self._ciz()
                else:
                    self._sinav_sayaclari(sinav)
                    # Gözetmen kodu beklemesi de yerelde azalır; bitince tuş takımı açılır.
                    gozetmen = sinav.get("gozetmen") or {}
                    if int(gozetmen.get("bekleme") or 0) > 0:
                        gozetmen["bekleme"] = int(gozetmen["bekleme"]) - 1
                        if self.gozetmen_kod_acik and gozetmen["bekleme"] % 60 in (0, 59):
                            self._ciz()
            yoklama = self.durum.get("yoklama") if self.durum and isinstance(self.durum.get("yoklama"), dict) else None
            if yoklama:
                # Kalan süre ve PIN beklemesi yerelde azalır; kaynak her durum iletisinde servisten gelir.
                if yoklama.get("kalan") is not None:
                    yoklama["kalan"] = max(0, int(yoklama["kalan"]) - 1)
                    self.yl_kalan.set_text(f"Kalan {sayac_metni(yoklama['kalan'])}")
                    if yoklama["kalan"] <= 60 and not yoklama.get("uyari"):
                        yoklama["uyari"] = True
                        self._ciz()
                if int(yoklama.get("bekleme") or 0) > 0:
                    yoklama["bekleme"] = int(yoklama["bekleme"]) - 1
                    self._ciz()
            if self.gozetmen_kod_acik and time.time() - self.gozetmen_dokunma > GOZETMEN_KOD_ZAMAN_ASIMI_SN:
                self._gozetmen_vazgec()
            if self.gorunur:
                self.pencere.present()
                self.pencere.fullscreen()
                # Pencere ekrana yerleşmeden yapılan ilk deneme "not-viewable" ile
                # düşer; kilit sürdükçe klavye kilidi alınana kadar yeniden denenir.
                if self.kilit_modu and self.klavye_kilidi != "alındı":
                    self._klavye_kilitle()
            return True

        def _ciz(self):
            durum = self.durum or {}
            duyuru = durum.get("duyuru")
            kapatma = durum.get("kapatma")
            acil = durum.get("acil")
            # Eski servis "sinav" alanını göndermez: sınav yok sayılır (eski davranış sürer).
            sinav = durum.get("sinav") if isinstance(durum.get("sinav"), dict) else None
            gozetmen = (sinav or {}).get("gozetmen") or {}
            if not sinav:
                self.gozetmen_kod_acik = False
                self._izgara_temizle()
                self._liste_kur([])
            gozetmen_sayfasi = bool(sinav) and (bool(gozetmen.get("durum")) or self.gozetmen_kod_acik)
            if not gozetmen_sayfasi and self.izgara_oturum is not None:
                self._izgara_temizle()
            # Ders yoklaması (A5). Eski servis "yoklama" alanını göndermez: yoklama yok sayılır.
            yoklama = durum.get("yoklama") if isinstance(durum.get("yoklama"), dict) else None
            if not yoklama and self.yk_oturum is not None:
                self._yoklama_temizle()
            self._bantlari_ciz(durum)
            # Öncelik (ortak sözlük §5.5): acil > kapatma > gozetmen-* > yoklama-* > duyuru > sinav-giris/sinav > kilit > gizli.
            if acil:
                tatbikat = acil.get("tur") == "tatbikat"
                self.acil_bant.set_text(ACIL_BANT["tatbikat" if tatbikat else "acil"])
                baslik = acil_basligi(acil.get("baslik"), tatbikat)
                self.acil_baslik.set_text(baslik)
                self.acil_baslik.set_visible(bool(baslik))
                metin = acil.get("metin") or ""
                self.acil_metin.set_text(metin)
                metin_baglam = self.acil_metin.get_style_context()
                for sinif in ("uzun", "cok-uzun"):
                    metin_baglam.remove_class(sinif)
                if acil_metin_sinifi(metin):
                    metin_baglam.add_class(acil_metin_sinifi(metin))
                self._acil_alt_yaz()
                self.acil_kapat.set_visible(bool(acil.get("kapatilabilir")))
                self._pencere_sinifi("tatbikat" if tatbikat else "acil")
                self.yigin.set_visible_child_name("acil")
                # Kilitli tahtada klavye kilidi sürer: acil ekranı kilidi atlatma yolu olmasın.
                self._goster(kilit=bool(durum.get("kilitli")))
                return
            self._pencere_sinifi(None)
            if kapatma:
                self.kapatma_sayac.set_text(str(kapatma.get("kalan", 0)))
                self.kapatma_neden.set_text(
                    (kapatma.get("neden") or "Otomatik kapatma")
                    + "\nTahtayı kullanıyorsanız Vazgeç düğmesine dokunun; yoksa süre sonunda kapanır."
                )
                self.yigin.set_visible_child_name("kapatma")
                self._goster(kilit=False)
            elif gozetmen_sayfasi:
                self._gozetmen_ciz(sinav, gozetmen)
            elif yoklama:
                # Öğretmenin başlattığı kısa etkileşim: duyuru serviste bekler, yoklama kapanınca görünür.
                # Klavye kilidi yalnız tahta kilitliyse (yoklama kilidi açmaz).
                self._yoklama_ciz(yoklama)
                self._goster(kilit=bool(durum.get("kilitli")))
            elif duyuru:
                self.duyuru_baslik.set_text(duyuru.get("baslik") or "DUYURU")
                self._duyuru_metni_yaz(duyuru.get("metin") or "")
                self.duyuru_kapat.set_visible(bool(duyuru.get("kapatilabilir")))
                self.yigin.set_visible_child_name("duyuru")
                # Sınav sürerken üstte görünen duyuru da klavyeyi bağlar (alttaki sınav ekranı aşılmasın).
                self._goster(kilit=bool(sinav))
            elif sinav:
                self._sinav_ciz(sinav)
            elif durum.get("kilitli"):
                kod_var = bool(durum.get("kod_var"))
                bekleme = int(durum.get("bekleme") or 0)
                cevrimdisi = bool(durum.get("cevrimdisi")) or not durum.get("kayitli", True)
                if cevrimdisi:
                    self.bilgi.set_text("Sunucuya ulaşılamıyor. Kilidi aşağıdaki düğmeyle açabilirsiniz.")
                elif bekleme:
                    self.bilgi.set_text(f"Kod art arda hatalı girildi. {bekleme} saniye bekleyin.")
                elif kod_var:
                    self.bilgi.set_text("Açmak için kilit kodunu girin.")
                elif durum.get("kilit_kaynak") == "program":
                    self.bilgi.set_text("Okul idaresi de açabilir.")
                else:
                    self.bilgi.set_text("Kilit okul idaresince açılır.")
                program = program_bilgisi(durum)
                # Uzun neden ("Bu saatte bu derslikte ders yok") saatin ortasından bölünmesin: iki satır.
                self.program_bilgi.set_text(program.replace(" · ", "\n", 1) if len(program) > 40 else program)
                self.program_bilgi.set_visible(bool(program))
                self.kod_kutusu.set_visible(kod_var and not bekleme and not cevrimdisi)
                self.cevrimdisi_dugmesi.set_visible(cevrimdisi)
                self.kilit_yoklama.set_visible(bool(durum.get("yoklama_etkin")) and not cevrimdisi)
                self.yigin.set_visible_child_name("kilit")
                self._goster(kilit=True)
            else:
                self._gizle()

        def _goster(self, kilit: bool):
            ilk = not self.gorunur
            self.gorunur = True
            self.pencere.show()
            self.pencere.fullscreen()
            self.pencere.present()
            self.kilit_modu = kilit
            if kilit:
                self._klavye_kilitle()
            else:
                self._klavye_birak()
            if ilk:
                self._durum_bildir()

        def _durum_bildir(self):
            genislik, yukseklik = self._geometri()
            self.baglanti.gonder(
                {
                    "tur": "ekran_durumu",
                    "genislik": genislik,
                    "yukseklik": yukseklik,
                    "klavye_kilidi": self.klavye_kilidi,
                }
            )

        def _gizle(self):
            if self.gorunur:
                self._klavye_birak()
                self.pencere.hide()
            self.gorunur = False
            self.kilit_modu = False
            self.girilen = ""
            self.kod_etiketi.set_text("")
            self.gozetmen_kod_acik = False
            self.gozetmen_girilen = ""
            self.gk_kod.set_text("")
            self._izgara_temizle()
            self._liste_kur([])
            self._yoklama_temizle()

        def _klavye_kilitle(self):
            """Klavye ve fareyi bu pencereye bağlar (X11'de Alt+Tab'ı keser)."""
            onceki = self.klavye_kilidi
            try:
                koltuk = Gdk.Display.get_default().get_default_seat()
                pencere = self.pencere.get_window()
                if pencere is None:
                    return
                if not pencere.is_viewable():
                    self.klavye_kilidi = "bekliyor (pencere henüz görünür değil)"
                    return
                sonuc = koltuk.grab(pencere, Gdk.SeatCapabilities.ALL, True, None, None, None)
                self.klavye_kilidi = "alındı" if sonuc == Gdk.GrabStatus.SUCCESS else f"alınamadı ({sonuc.value_nick})"
            except Exception as hata:
                self.klavye_kilidi = f"hata: {hata}"
            if self.klavye_kilidi != onceki:
                self._durum_bildir()

        def _klavye_birak(self):
            try:
                Gdk.Display.get_default().get_default_seat().ungrab()
            except Exception:
                pass

    Ekran()
    Gtk.main()
    return 0
