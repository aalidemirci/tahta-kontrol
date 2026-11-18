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

Ders yoklaması (Aşama 5; 0.14.0'da yeniden): PIN sayfası (öğretmen kodu + PIN, tuş takımı); kaydırmasız seçim
görünümü (solda düzey, ortada şube ızgarası, sağda ders saatleri; şubeye tek dokunuşla liste); sınıf listesi
(sunucunun sırasıyla iki satırlı düğmeler: üstte numara + YOK/GEÇ, altta ad; alanı paylaşan ızgara, 56'dan
kalabalık listede sayfalar); onay ve ileti sayfaları. Dokunuş: var → yok → (devrenin ilk dersinde) geç → var.
Liste yalnız servisten gelen durum iletisinde ve düğmelerde durur; yoklama kapanınca düğmeler yok edilir.
Etiketi sunucu üretir (burada maske, kısaltma, sıralama yoktur). Yoklama belirteci
bu yardımcıya hiç gelmez; PIN servise iletilir, burada saklanmaz. Öncelik: acil > kapatma > temizlik >
gözetmen > yoklama > duyuru > sınav > kilit. Klavye kilidi yalnız tahta kilitliyse alınır.

USB anahtar (0.11.0): kilit ekranında anahtarın bilgi satırı ve "USB anahtarla aç" düğmesi, kilit açma PIN
sayfası (usb-pin), yoklama PIN sayfasının USB kipi (öğretmen kodu sorulmaz) ve köşede odak çalmayan küçük
bildirim penceresi (UsbBildirimi). Takılınca hiçbir tam ekran sayfa kendiliğinden açılmaz; anahtar dosyası ve
gizli değer bu yardımcıya hiç gelmez (yalnız rol, kısa ad, kod ve izinler).

Oturum temizliği (K7, 0.8.0): kapatma uyarısı sayfası 60 sn geri sayımlı temizlik uyarısı olarak da
kullanılır; servisin "pencereleri_kapat" isteğinde pencere kapatma ayrı süreçte yapılır
(sistem.pencereleri_kapat) ve yalnız sayılar servise döner.
"""

from __future__ import annotations

import base64
import json
import math
import os
import re
import socket
import sys
import threading
import time
from datetime import date

from . import __version__, ayar, sistem, usb_anahtar
from .yoklama import SAYFA_BOYU as YOKLAMA_SAYFA_BOYU
from .yoklama import sayfa_dilimi as yoklama_sayfa_dilimi
from .yoklama import sonraki_durum
from .yoklama import yerlesim as yoklama_yerlesim

# Oturum temizliği uyarısı (K7): neyin yapılıp neye dokunulmadığı açıkça yazılır.
TEMIZLIK_UYARI_METNI = (
    "Gün sonu oturum temizliği: açık pencereler kapanır, tarayıcı oturumları ve çerezler silinir.\n"
    "Dosyalarınıza, tarayıcı geçmişine ve kayıtlı parolalara dokunulmaz.\n"
    "Tahtayı kullanıyorsanız Vazgeç düğmesine dokunun."
)

# ---- ekran ölçeği (saf; test edilir) -----------------------------------------------------------
# Bütün piksel ölçüleri (yazı boyları, boşluklar, tuş takımı, düğmeler) 1920x1080 yatay ekran için
# yazılır ve pencerenin bulunduğu ekranın boyutuna göre orantılı büyütülür/küçültülür. Sabit piksel
# genişlik VERMEYİN: GtkStack en geniş sayfasına göre boyutlanır; bir sayfadaki tek bir sabit ölçü
# bütün pencereyi ekrandan taşırır (0.7.0'da 1280x800 ve 1366x768 ekranda kilit ekranı sağa kaydı).
OLCEK_TABAN_EN = 1920
OLCEK_TABAN_BOY = 1080
OLCEK_EN_AZ = 0.4  # 768 px'ten dar ekranda yazı okunmaz olmasın (sığmayan içerik kaydırılır)
OLCEK_EN_COK = 3.0


def ekran_olcegi(en: int, boy: int) -> float:
    """1920x1080 için yazılmış ölçülerin bu ekrandaki çarpanı.

    Yatay ekran 1920x1080'e, dikey (portre) ekran 1080x1920'ye göre ölçülür; iki eksenden küçük
    oran alınır ki hiçbir yönde taşmasın (4:3 ekranda genişlik, 16:10'da yükseklik belirler).
    Ekran boyu bilinmiyorsa 1.
    """
    if not en or not boy or en <= 0 or boy <= 0:
        return 1.0
    uzun, kisa = max(en, boy), min(en, boy)
    olcek = min(uzun / OLCEK_TABAN_EN, kisa / OLCEK_TABAN_BOY)
    return round(min(OLCEK_EN_COK, max(OLCEK_EN_AZ, olcek)), 4)


def dikey_mi(en: int, boy: int) -> bool:
    """Portre ekran: yan yana iki sütunlu sayfalar (kilit, kod ve PIN) alt alta dizilir."""
    return bool(en and boy) and 0 < en < boy


def olcekle(piksel: int, olcek: float) -> int:
    """Bir piksel ölçüsünü ölçekler. 0 ve eksi değerler (GTK'da -1 = "doğal boy") olduğu gibi kalır;
    artı bir ölçü en az 1 px olur (ince kenarlıklar kaybolmasın)."""
    if piksel <= 0:
        return piksel
    return max(1, round(piksel * olcek))


def olcekli_stil(stil: bytes, olcek: float) -> bytes:
    """CSS'teki bütün `<sayı>px` değerlerini ölçekler (yazı boyu, dolgu, kenarlık, harf aralığı)."""
    return re.sub(rb"(\d+)px", lambda m: b"%dpx" % olcekle(int(m.group(1)), olcek), stil)


def pencere_olcusu(taban_en: int, taban_boy: int, ekran_en: int, ekran_boy: int, olcek: float) -> tuple[int, int]:
    """Tam ekran olmayan pencere (arıza bildirimi): ölçekli taban boyu, ekranın %94 x %90'ını aşmaz."""
    en, boy = olcekle(taban_en, olcek), olcekle(taban_boy, olcek)
    if ekran_en > 0:
        en = min(en, int(ekran_en * 0.94))
    if ekran_boy > 0:
        boy = min(boy, int(ekran_boy * 0.90))
    return max(1, en), max(1, boy)


# Ölçüler, ağırlıklar ve boşluklar: renk YOK (renkler renk_stili() ile ayrı sağlayıcıda).
# Değerler 1920x1080 içindir; ekranda olcekli_stil() ile ekran ölçeğine çevrilerek yüklenir.
STIL_OLCU = b"""
#okul { font-size: 40px; font-weight: 600; }
#bant-sag { font-size: 26px; }
#ust-bant { padding: 28px 48px; border-bottom-width: 6px; border-bottom-style: solid; }
#logo-kutu { border-radius: 16px; padding: 10px; }
#saat { font-size: 150px; font-weight: 700; }
#tarih { font-size: 30px; }
#kilit-yazi { font-size: 40px; font-weight: 600; margin-top: 24px; }
#program-bilgi { font-size: 32px; font-weight: 600; }
#gunluk-program-baslik { font-size: 26px; font-weight: 600; }
#gunluk-program-satir, #gunluk-program-sayfa { font-size: 24px; }
#gunluk-program-gezgin button { font-size: 22px; padding: 4px 14px; }
#usb-bilgi { font-size: 26px; font-weight: 600; }
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
#yoklama-ust { font-size: 30px; font-weight: 600; }
#yoklama-sube { font-size: 50px; font-weight: 800; }
#yoklama-ders { font-size: 42px; font-weight: 800; padding: 4px 22px; }
#yoklama-kalan { font-size: 34px; font-weight: 600; }
#yoklama-sayi { font-size: 32px; font-weight: 600; }
#yoklama-sayfa { font-size: 30px; font-weight: 600; }
#yoklama-onay-liste { font-size: 34px; }
#yoklama-onay-liste.uzun { font-size: 26px; }
#yoklama-ileti { font-size: 52px; font-weight: 600; }
#ogrenci { padding: 3px 7px; border-width: 3px; }
#ogrenci.gec { padding: 0px 4px; border-width: 6px; }
#ogrenci-no { font-size: 24px; font-weight: 800; }
#ogrenci-durum { font-size: 22px; font-weight: 800; }
#ogrenci-ad { font-size: 23px; font-weight: 600; }
.orta #ogrenci-no, .sik #ogrenci-no { font-size: 21px; }
.orta #ogrenci-durum, .sik #ogrenci-durum { font-size: 19px; }
#secim { font-size: 30px; padding: 4px 12px; border-width: 3px; }
#secim.ders { font-size: 24px; }
#secim.oneri { font-size: 30px; font-weight: 700; padding: 8px 18px; }
#secim-baslik { font-size: 26px; font-weight: 600; }
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
# Ders yoklaması: "yok" işaretli öğrenci düğmesi koyu kırmızı zemin + beyaz yazı + "YOK" yazısı; "geç" koyu
# kehribar zemin + kalın açık sarı kenar + "GEÇ" yazısı (renk tek başına anlam taşımaz; yanıp sönme yok); hata ve
# süre uyarısı açık kırmızı. Markadan bağımsız sabit renkler; beyaz yazı iki zeminde de 7:1'i aşar.
YOKLAMA_RENKLERI = (
    "#ogrenci.yok { background-color: #991b1b; border-color: #fca5a5; }\n"
    "#ogrenci.yok label { color: #ffffff; }\n"
    "#ogrenci.gec { background-color: #92400e; border-color: #fde68a; }\n"
    "#ogrenci.gec label { color: #ffffff; }\n"
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


def liste_sutun_sayisi(n: int, ekran_eni: int = 0, olcek: float = 1.0, karakter: int = 0) -> int:
    """Giriş ekranındaki liste: ≤ 20 kişi tek sütun, ≤ 40 iki, fazlası üç sütun. Ekran eni verilirse
    en küçük yazıyla bile sığmayan sütun sayısı azaltılır (portre ekran; liste kaydırılır).
    karakter: en uzun satırın harf sayısı (liste_satir_karakteri); verilmezse LISTE_SATIR_KARAKTER."""
    sutun = 1 if n <= 20 else 2 if n <= 40 else 3
    karakter = max(LISTE_SATIR_KARAKTER, karakter)
    if ekran_eni > 0:
        while sutun > 1 and (sutun * karakter * 0.6 * olcekle(22, olcek)
                             + (120 + 56 * (sutun - 1) + 88 * sutun) * olcek) > ekran_eni:  # fmt: skip
            sutun -= 1
    return sutun


LISTE_SATIR_KARAKTER = 34  # giriş listesinin bir sütun grubu: koltuk + maskeli ad + …no + şube (en az)


def liste_satir_karakteri(liste: list) -> int:
    """Listenin en uzun satırının harf sayısı (koltuk + maske + …no + şube). Uzun maskeli ad
    ("Mu****** Em** Ka*************") 34 harflik tahmini aşar; 1024x768'de şube sütunu ekrandan
    taşıyordu (0.7.1 denetimi). En az LISTE_SATIR_KARAKTER."""
    return max([LISTE_SATIR_KARAKTER] + [sum(len(h) for h in liste_hucreleri(oge)) for oge in liste or []])


def liste_punto(
    satir_sayisi: int, ekran_boyu: int, olcek: float = 1.0, ekran_eni: int = 0, sutun: int = 1, karakter: int = 0
) -> int:
    """Liste yazı boyu (px): ekran yüksekliğinden; 1920x1080'de 22–44 arası (arka sıradan okunabilsin),
    başka ekranda bu sınırlar da ölçeklenir. Ekran eni verilirse sütun grupları ene de sığdırılır
    (portre ekranda yazı büyüyüp yana taşmasın; en uzun satır `karakter` harf). Sığmayan uzun liste
    kaydırılır."""
    karakter = max(LISTE_SATIR_KARAKTER, karakter)
    kullanilir = (ekran_boyu or 1080) - 430 * olcek  # bant, başlık satırları ve alt satır
    punto = int(kullanilir / max(1, satir_sayisi) / 1.38)
    if ekran_eni > 0:
        sutun = max(1, sutun)
        serbest = ekran_eni - (120 + 56 * (sutun - 1) + 4 * 22 * sutun) * olcek  # kenarlar, ara, hücre boşluğu
        punto = min(punto, int(serbest / sutun / karakter / 0.6))
    return max(olcekle(22, olcek), min(olcekle(44, olcek), punto))


def liste_hucreleri(oge: dict) -> tuple[str, str, str, str]:
    """Bir liste satırının hücreleri: koltuk · maske · …no · şube (tam no ve ders yok)."""
    no = str(oge.get("n") or "")
    return str(oge.get("k", "")), str(oge.get("a") or ""), f"…{no}" if no else "", str(oge.get("s") or "")


def izgara_sutun(n: int, en: int = 0, boy: int = 0) -> int:
    """Yoklama ızgarasının sütun sayısı: ceil(sqrt(n·oran)) — düğmeler ekrana yayılır (oran ekranın
    en/boy oranı; bilinmiyorsa 16:9)."""
    oran = en / boy if en > 0 and boy > 0 else 16 / 9
    return max(1, math.ceil(math.sqrt(max(1, n) * oran)))


def izgara_dugme_olcusu(n: int, en: int, boy: int, olcek: float = 1.0) -> tuple[int, int]:
    """Gözetmen yoklama ızgarasındaki koltuk düğmesinin en küçük eni ve boyu (px). 1920x1080'de
    120–260 x 80–170; sınırlar ölçeklenir. Izgara ekrana sığmazsa kaydırılır."""
    en, boy = en or 1920, boy or 1080
    sutun = izgara_sutun(n, en, boy)
    satir = max(1, -(-max(1, n) // sutun))
    dugme_en = max(olcekle(120, olcek), min(olcekle(260, olcek), int((en - 120 * olcek) // sutun - 10 * olcek)))
    dugme_boy = max(olcekle(80, olcek), min(olcekle(170, olcek), int((boy - 430 * olcek) // satir - 10 * olcek)))
    return dugme_en, dugme_boy


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


# ---- ders yoklaması (A5; 0.14.0'da yeniden): saf yardımcılar (test edilir) -------------------
# Etiket (maske, kısaltma, sıra) SUNUCUDA üretilir; burada yalnız gösterim ve yerleşim vardır. Izgaralar homojen
# Gtk.Grid'dir: sabit en/boy verilmez, yalnız sütun x satır sayısı seçilir ve alan paylaşılır (kaydırma yok).
YOKLAMA_KOD_HANE = 3
YOKLAMA_PIN_HANE = 6
YOKLAMA_DOKUNMA_EN_AZ = 60  # düğmelerin en küçük boyu (1920x1080 birimi; ızgara genellikle daha büyüğünü verir)
YOKLAMA_TEMIZLE_ONAY_SN = 4  # [Temizle]'nin ikinci dokunuşu bu sürede gelmezse soru geri alınır
YOKLAMA_ONERI_BOY = 84  # seçim görünümünün üst satırı (öneri düğmesi ve ★ şubeler)
YOKLAMA_DUZEY_ESIGI = 15  # şube sayısı bunu aşarsa solda düzey sütunu çıkar
YOKLAMA_SUBE_SATIR_EN_AZ = 4  # az şubeli okulda düğmeler bütün alanı kaplayıp devleşmesin
YOKLAMA_DERS_SATIR_EN_AZ = 5
YOKLAMA_DIKEY_SUTUN = 3  # portre ekranda öğrenci ızgarası dar ve uzundur (16 harflik ad sığsın); 48 üstü 4 sütun
DURUM_YAZISI = {"var": "", "yok": "YOK", "gec": "GEÇ"}


def yoklama_ust_metni(yoklama: dict) -> str:
    """Onay sayfasının üst satırı: "10/A · 3. ders (09:50–10:30) · A. Örnek"."""
    ogretmen = (yoklama.get("ogretmen") or {}).get("etiket") or ""
    parcalar = [yoklama.get("sube") or "Şube seçilmedi", yoklama.get("ders_metni") or "", yoklama.get("ders_adi") or "", ogretmen]
    return " · ".join(p for p in parcalar if p)


def yoklama_ders_basligi(yoklama: dict) -> str:
    """Listenin üstündeki büyük ders yazısı: "3. ders 09:50–10:30" (yanlış ön seçimin tek savunması)."""
    no = yoklama.get("ders_no")
    if not no:
        return "Ders seçilmedi"
    saat = next((d for d in yoklama.get("ders_saatleri") or [] if d.get("ders_no") == no), None) or {}
    return f"{no}. ders {saat['baslangic']}–{saat['bitis']}" if saat.get("baslangic") and saat.get("bitis") else f"{no}. ders"


def yoklama_sayi_metni(yok_sayisi: int, gec_sayisi: int, mevcut: int, gec_goster: bool = True) -> str:
    """Alt çubuk: "Yok: 2 · Geç: 1 · Derste: 32/34". Geç gelen derstedir; "Geç" yalnız geç seçilebilen derste
    (devrenin ilk dersi) ya da geç işareti varken yazılır."""
    parcalar = [f"Yok: {yok_sayisi}"]
    if gec_goster or gec_sayisi:
        parcalar.append(f"Geç: {gec_sayisi}")
    parcalar.append(f"Derste: {max(0, mevcut - yok_sayisi)}/{mevcut}")
    return " · ".join(parcalar)


def yoklama_onay_metni(yok: list[str], gec: list[str], mevcut: int, sayfa_sayisi: int = 1,
                       gec_goster: bool = True) -> tuple[str, str]:  # fmt: skip
    """Onay sayfası: (üç sayı [+ "2 sayfa · 70 öğrenci"], yok ve geç etiketleri iki öbekte)."""
    baslik = yoklama_sayi_metni(len(yok), len(gec), mevcut, gec_goster)
    if sayfa_sayisi > 1:
        baslik += f"\n{sayfa_sayisi} sayfa · {mevcut} öğrenci"
    obekler = [f"{ad} ({len(liste)}): " + ", ".join(liste) for ad, liste in (("YOK", yok), ("GEÇ", gec)) if liste]
    return baslik, "\n\n".join(obekler) if obekler else "Bütün öğrenciler derste."


def ogrenci_etiket_parcalari(etiket: str) -> tuple[str, str]:
    """Sunucunun çakışma eki adın sonundan ayrılır: "Mehmet Ali Y. (23)" → ("Mehmet Ali Y.", "(23)").

    Yalnız eski "ad + soyad baş harfi" biçiminde görülür; ek üst satıra alınır ki ad kısalsa da kesilmesin.
    """
    ana, _, ek = str(etiket).rpartition(" ")
    if ana and len(ek) >= 3 and ek[0] == "(" and ek[-1] == ")" and all(c in "0123456789" for c in ek[1:-1]):
        return ana, ek
    return str(etiket), ""


def ogrenci_dugme_metni(etiket: str) -> tuple[str, str]:
    """Etiketi (numara, ad) diye ayırır (sözleşme `etiket_ayirma`): ilk belirteç rakamla başlıyorsa VE ardından
    en az bir belirteç varsa o numaradır (üst satır, kalın), kalanı addır. Değilse numara boş, tamamı addır.
    Ajan etiketi kısaltmaz, sıralamaz, maskelemez."""
    etiket = str(etiket or "")
    ilk, _, kalan = etiket.partition(" ")
    if ilk[:1] in "0123456789" and ilk[:1] and kalan.strip():
        return ilk, kalan.strip()
    return "", etiket


def ogrenci_dugme_satirlari(etiket: str) -> tuple[str, str]:
    """Düğmenin (üst satır, alt satır) metni: numara + ad; numara yoksa eski biçimin çakışma eki üstte."""
    no, ad = ogrenci_dugme_metni(etiket)
    if not no:
        ad, no = ogrenci_etiket_parcalari(ad)
    return no, ad


def yoklama_izgara_olcusu(n: int, dikey: bool = False) -> tuple[int, int]:
    """Bir sayfadaki öğrenci ızgarası (sütun, satır): yatay ekranda sözleşme tablosu (6x7 / 6x8 / 7x8);
    portre ekranda 3 sütun (48 üstü 4), satır sayısı sayfadaki öğrenciye göre."""
    n = min(max(0, n), YOKLAMA_SAYFA_BOYU)
    if dikey:
        sutun = YOKLAMA_DIKEY_SUTUN + (1 if n > 48 else 0)  # 48 üstünde sunucu adı 13 harfe kısaltır: 4 sütun sığar
        return sutun, max(7, -(-n // sutun))
    return yoklama_yerlesim(n)


def yoklama_yogunluk(sutun: int, satir: int) -> str:
    """Izgaranın yazı boyu sınıfı: 6x7 "" (tam boy), 6x8 "orta", 7x8 ve portre "sik"."""
    if sutun >= 7 or satir > 8:
        return "sik"
    return "orta" if satir >= 8 else ""


def sube_duzeyi(sube: str) -> str:
    """Şubenin düzeyi: adın "/" öncesi ("10/A" → "10", "Hz/B" → "Hz"); "/" yoksa "Diğer"."""
    bas, ayrac, _ = str(sube).partition("/")
    return bas.strip() if ayrac and bas.strip() else "Diğer"


def sube_kisa(sube: str) -> str:
    """Üst satırdaki dar düğmeler (öneri düğmesi ve ★ şubeler) için kısa şube adı: "Hazırlık/G" → "Hz/G".
    Yalnız GÖSTERİMDİR (servise giden ad değişmez); şube ızgarasındaki düğmeler tam adı yazar. Uzun düzey adı
    kesilince iki ★ düğmesi aynı ("★ Hazırlı…") görünüyor, yanlış şubenin listesi açılabiliyordu."""
    bas, ayrac, son = str(sube).partition("/")
    if ayrac and len(bas.strip()) > 4:
        bas = "Hz" if bas.strip().casefold().startswith("haz") else bas.strip()[:3] + "."
    return f"{bas}{ayrac}{son}"


def sube_duzeyleri(subeler: list[str]) -> list[tuple[str, list[str]]]:
    """Şubeleri düzeye göre öbekler; düzeyler ve şubeler sunucunun gönderdiği sırayla kalır."""
    obekler: dict[str, list[str]] = {}
    for s in subeler:
        obekler.setdefault(sube_duzeyi(s), []).append(s)
    return list(obekler.items())


def sube_izgarasi(subeler: list[str], duzey: str | None = None) -> tuple[list[str], int, int, list[str]]:
    """Seçim görünümündeki şube ızgarası: (gösterilen şubeler, sütun, satır, düzeyler).

    15 şubeye kadar düzey sütunu yoktur (düzeyler boş), hepsi 5 sütunda görünür. Fazlasında yalnız seçili düzeyin
    şubeleri gösterilir; bir düzeyde 20'den çok şube varsa 6 sütun. Sütun ve satır sayısı en kalabalık düzeye göre
    seçilir ki düzey değişince düğmeler yer ve boy değiştirmesin. Kaydırma yoktur."""
    if len(subeler) <= YOKLAMA_DUZEY_ESIGI:
        return list(subeler), 5, max(YOKLAMA_SUBE_SATIR_EN_AZ, -(-len(subeler) // 5)), []
    obekler = sube_duzeyleri(subeler)
    en_cok = max(len(liste) for _, liste in obekler)
    sutun = 6 if en_cok > 20 else 5
    gosterilen = dict(obekler).get(duzey) or obekler[0][1]
    return list(gosterilen), sutun, max(YOKLAMA_SUBE_SATIR_EN_AZ, -(-en_cok // sutun)), [d for d, _ in obekler]


def ders_izgarasi(n: int) -> tuple[int, int]:
    """Ders saati sütunu (sütun, satır): 12 derse kadar 2 sütun (en çok 6 satır); fazlasında 3, 4 sütun."""
    sutun = 2 if n <= 12 else 3 if n <= 18 else 4
    return sutun, max(YOKLAMA_DERS_SATIR_EN_AZ, -(-n // sutun))


def ders_dugme_metni(ders: dict, simdiki_ders_no=None, adaylar=(), bitti: bool = False) -> str:
    """Ders saati düğmesi: üstte "3. ders" ("● 3. ders · şimdi", teneffüste "biten 2. ders" / "başlayacak
    3. ders"), altta saat aralığı. İşaret yazıyladır; renk tek başına anlam taşımaz. `bitti`: ön seçilen ders az
    önce bitmiş derstir (sunucunun `simdiki_bitti` bayrağı): "şimdi" yerine "bitti" yazılır."""
    no = ders.get("ders_no")
    adaylar = list(adaylar or [])
    if no in adaylar and len(adaylar) == 2:
        ust = f"{'biten' if adaylar.index(no) == 0 else 'başlayacak'} {no}. ders"
    elif no in adaylar:
        ust = f"● {no}. ders"
    elif no == simdiki_ders_no and no is not None:
        ust = f"● {no}. ders · {'bitti' if bitti else 'şimdi'}"
    else:
        ust = f"{no}. ders"
    return f"{ust}\n{ders['baslangic']}–{ders['bitis']}" if ders.get("baslangic") and ders.get("bitis") else ust


def yoklama_temizle_metni(isaret_sayisi: int, onay_bekliyor: bool) -> str:
    """[Temizle] düğmesinin yazısı: ilk dokunuştan sonra kaç işaretin (bütün sayfalarda) silineceğini sorar."""
    return f"Hepsini sil ({isaret_sayisi})" if onay_bekliyor and isaret_sayisi else "Temizle"


def yoklama_secim_bilgisi(yoklama: dict) -> str:
    """Seçim görünümünün yönerge satırı."""
    adaylar = yoklama.get("ders_adaylari") or []
    if yoklama.get("istek"):
        return "Yükleniyor…"
    if not yoklama.get("subeler"):
        return "Öğrenci listesi yüklenmemiş; okul idaresine bildirin."
    if yoklama.get("sube") and not yoklama.get("ders_no") and len(adaylar) == 2:
        return f"Teneffüs: biten {adaylar[0]}. ders mi, başlayacak {adaylar[1]}. ders mi? Ders saatine dokunun."
    if yoklama.get("sube") and not yoklama.get("ders_no"):
        return "Ders saatine dokunun; liste açılır."
    return "Şubeye dokununca liste açılır."


def yoklama_liste_bilgisi(yoklama: dict) -> str:
    """Liste görünümünün yönerge satırı (dokunulmayan öğrenci "var" sayılır)."""
    if yoklama.get("liste_ileti"):
        return str(yoklama["liste_ileti"])
    if not yoklama.get("ogrenciler"):
        return ""
    parcalar = ["Olmayan öğrenciye dokunun."]
    if yoklama.get("gec_secilebilir"):
        parcalar.append("İkinci dokunuş: geç.")
    if yoklama.get("baska_yoklama"):
        parcalar.append("Bu ders saatinin kayıtlı yoklaması işaretli geldi.")
    return " ".join(parcalar)


def yoklama_ana_dugme(yoklama: dict) -> tuple[str, str]:
    """Alt çubuktaki ana düğme: (metin, ileti türü). Bütün sayfalar görülene kadar "Sonraki sayfa ›"
    (görülmeyen sayfadaki öğrenciler bakılmadan "var" sayılmasın); sonra "KAYDET"."""
    if int(yoklama.get("sayfa_sayisi") or 1) > 1 and not yoklama.get("tum_sayfalar_goruldu"):
        return "Sonraki sayfa ›", "yoklama_sayfa"
    return "KAYDET", "yoklama_kaydet"


def yoklama_pin_hatasi(yoklama: dict) -> str:
    """PIN sayfasındaki hata/bilgi satırı."""
    if yoklama.get("istek"):
        return "Doğrulanıyor…"
    bekleme = int(yoklama.get("bekleme") or 0)
    if bekleme > 0:
        return f"Çok fazla hatalı deneme. {bekleme} saniye bekleyin."
    return str(yoklama.get("hata") or "")


# ---- USB anahtar bildirimi (0.11.0; saf, test edilir) -------------------------------------------
# Ölçüler 1920x1080 içindir ve olcekli_stil() ile ölçeklenir; renkler yüzer düğmenin sabit koyu paletinden
# (koyu zemin, açık yazı; 7:1 üstü), markadan bağımsız.
USB_BILDIRIM_SN = 10
USB_BILDIRIM_BOSLUK = 18  # ekran kenarından ve yüzer düğmeden uzaklık
USB_BILDIRIM_STIL = b"""
#ub-kutu { min-width: 640px; padding: 24px; border-radius: 16px; border-width: 2px; border-style: solid; }
#ub-kutu label { font-size: 28px; }
#ub-kutu button { font-size: 28px; font-weight: 600; padding: 10px 24px; min-height: 48px; border-radius: 10px;
                  border-width: 1px; border-style: solid; background-image: none; box-shadow: none; text-shadow: none; }
"""
USB_BILDIRIM_RENK = b"""
#ub-pencere { background-color: #111827; }
#ub-kutu { background-color: #111827; border-color: #9ca3af; }
#ub-kutu label { color: #f9fafb; }
#ub-kutu button { background-color: #1f2937; border-color: #6b7280; }
#ub-kutu button label { color: #f9fafb; }
#ub-kutu #ub-yoklama { background-color: #1e40af; border-color: #93c5fd; }
#ub-kutu #ub-yoklama label { color: #ffffff; }
"""


def usb_bildirim_gosterilir(usb, ana_gorunur: bool, kilitli: bool) -> bool:
    """Bildirim yalnız tahta kilitli değilken ve tam ekran sayfa (kilit, duyuru, acil, sınav, kapatma, yoklama)
    yokken, gösterilecek metin ve yeni bir bildirim numarası varken çıkar."""
    if not isinstance(usb, dict) or ana_gorunur or kilitli:
        return False
    return bool(usb.get("bildirim_no")) and bool(usb.get("metin"))


def usb_bildirim_yoklama_dugmesi(usb) -> bool:
    """[Yoklama al] yalnız anahtar tanınmış ve yoklama izni varken."""
    return isinstance(usb, dict) and usb.get("durum") == "tanindi" and "yoklama" in (usb.get("izinler") or [])


def usb_bildirim_konumu(alan: tuple[int, int, int, int], en: int, boy: int, bosluk: int,
                        yuzer: tuple[int, int, int] | None = None) -> tuple[int, int]:  # fmt: skip
    """Sağ alt köşe; yüzer düğme (x, y, çap) sağ kenarda ve bildirimin dikey aralığındaysa onun üstüne çıkar."""
    ax, ay, alan_en, alan_boy = alan
    x = ax + alan_en - en - bosluk
    y = ay + alan_boy - boy - bosluk
    if yuzer is not None:
        dx, dy, cap = yuzer
        if dx + cap / 2 >= ax + alan_en / 2 and dy + cap > y and dy < y + boy:
            y = dy - boy - bosluk
    return max(ax, int(x)), max(ay, int(y))


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


def duyuru_duzeni(metin: str, ekran_boyu: int, olcek: float = 1.0, ekran_eni: int = 0) -> dict:
    """Duyuru metninin ekran düzeni (saf; test edilir).

    Kısa metin: {"ust": "", "sutunlar": [], "sinif": ""|"uzun"|"cok-uzun", "punto": 0} ve metin
    tek etikette. Çok satırlı metin (şube oturma listesi gibi): baştaki ilk boş satıra kadarki
    en çok 3 satır "ust" olur, kalanlar 1–3 sütuna bölünür, yazı boyu ekran yüksekliğinden
    hesaplanır (1920x1080'de 20–40 px; sınırlar ölçeklenir). Ekran eni verilirse en uzun satır da
    sütunlara sığacak kadar küçültülür (sütun satırları kırılmaz). Uzun liste sığmazsa sayfa
    kaydırılır; Kapat düğmesi hep ekrandadır.
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
    en_uzun = max(1, max((len(s) for s in satirlar), default=1))

    def serbest(sutun_sayisi: int) -> float:  # kenar boşlukları ve sütun araları dışında kalan en
        return ekran_eni - (160 + 70 * (sutun_sayisi - 1)) * olcek

    if ekran_eni > 0:
        # Dar (portre) ekranda en küçük yazıyla bile sığmayan sütun sayısı azaltılır (liste kaydırılır).
        while sutun > 1 and sutun * en_uzun * 0.6 * olcekle(20, olcek) > serbest(sutun):
            sutun -= 1
    boy = -(-n // sutun)
    kullanilir = (ekran_boyu or 1080) - 480 * olcek  # bant, başlık, üst satır ve Kapat
    punto = int(kullanilir / boy / 1.38)
    if ekran_eni > 0:
        # Sütun içi satır kırılmaz: en uzun satır (ortalama harf eni ≈ 0,6 punto) sütuna sığsın.
        punto = min(punto, int(serbest(sutun) / sutun / en_uzun / 0.6))
    punto = max(olcekle(20, olcek), min(olcekle(40, olcek), punto))
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
        + f"#yoklama-bilgi, #yoklama-kalan, #yoklama-ust, #yoklama-sayfa, #secim-baslik {{ color: {p['soluk']}; }}\n"
        # Seçim görünümü (0.14.0): seçili şube/ders ana renkte; teneffüsteki iki aday ders vurgu renginde kenarlı.
        + f"#secim.secili {{ background-color: {p['ana']}; border-color: {p['ana']}; }}\n"
        + f"#secim.secili label {{ color: {p['ana_metin']}; }}\n"
        + f"#secim.aday, #secim.simdi {{ border-color: {p['vurgu']}; }}\n"
        + f"#yoklama-ders {{ border-color: {p['vurgu']}; }}\n"
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


KILIT_PROGRAM_SATIR_SINIRI = 24
KILIT_PROGRAM_SAYFA_SATIRI = 4
KILIT_PROGRAM_ILETI_SINIRI = 160  # gun_programi.coz ile aynı
KILIT_PROGRAM_ELLE_SN = 60  # Önceki/Sonraki ile seçilen sayfa bu kadar kalır, sonra şimdiki derse döner
KILIT_PROGRAM_BASLIK = "Bugünün ders programı"


def gunluk_program_gorunumu(durum: dict, sayfa: int | None = 0, bugun: str | None = None,
                            simdi: str | None = None) -> dict:  # fmt: skip
    """Kilit için yalnız ders/sınıf/saat alanlarından oluşan, sınırlı ve sayfalı görünüm.

    Öğretmen/öğrenci alanları kopyalanmaz. Sunucu programı göndermezse (anahtar yok: eski sunucu;
    `null`: program ya da şube yok) kutu hiç gösterilmez. Esas alınan tarih SUNUCUNUN gönderdiğidir:
    tahtanın saati yanlışsa program kaybolmaz, başlık "Bugünün" yerine o tarihi taşır. Eskimiş
    programı servis kaldırır (`gecerli_sn`, gece yarısı); burada tahtanın saatine göre gizlenmez.

    `sayfa=None`: şimdiki ya da sıradaki dersin sayfası (`simdi` "SS:DD", verilmezse tahtanın saati);
    bütün dersler bittiyse son sayfa, tarih tahtanınkinden farklıysa ilk sayfa.
    """
    bos = {"gorunur": False, "baslik": KILIT_PROGRAM_BASLIK, "satirlar": [],
           "ileti": "", "sayfa": 0, "sayfa_sayisi": 1, "sayfa_metni": ""}
    veri = durum.get("gun_programi") if isinstance(durum, dict) else None
    if not isinstance(veri, dict):
        return bos
    tarih = veri.get("tarih")
    try:
        if not isinstance(tarih, str):
            return bos
        gun = date.fromisoformat(tarih)
    except ValueError:
        return bos
    bugun_mu = gun.isoformat() == (bugun or time.strftime("%Y-%m-%d"))
    baslik = KILIT_PROGRAM_BASLIK if bugun_mu else f"{gun.day} {AYLAR[gun.month - 1]} {GUNLER[gun.weekday()]} ders programı"

    def metin(deger, en_cok):
        if not isinstance(deger, str) or any(ord(h) < 32 or ord(h) == 127 for h in deger):
            return ""
        sonuc = " ".join(deger.split())
        if len(sonuc) > en_cok or re.search(r"(?<!\d)\d{11}(?!\d)", sonuc):
            return ""
        return sonuc

    satirlar, gorulen = [], set()
    kaynak = veri.get("dersler")
    if isinstance(kaynak, list):
        for satir in kaynak[:KILIT_PROGRAM_SATIR_SINIRI]:
            if not isinstance(satir, dict):
                continue
            no = satir.get("ders_no")
            bas, bit = satir.get("baslangic"), satir.get("bitis")
            sube, ders = metin(satir.get("sube"), 16), metin(satir.get("ders_adi"), 80)
            saat_deseni = r"(?:[01]\d|2[0-3]):[0-5]\d"
            if (isinstance(no, bool) or not isinstance(no, int) or not 1 <= no <= 20
                    or not isinstance(bas, str) or not re.fullmatch(saat_deseni, bas)
                    or not isinstance(bit, str) or not re.fullmatch(saat_deseni, bit)
                    or bit <= bas or not sube or not ders):
                continue
            kimlik = (bas, bit, no, sube, ders)
            if kimlik in gorulen:
                continue
            gorulen.add(kimlik)
            satirlar.append({"ders_no": no, "baslangic": bas, "bitis": bit, "sube": sube, "ders": ders})
    satirlar.sort(key=lambda s: (s["baslangic"], s["ders_no"], s["sube"], s["ders"]))
    sayfa_sayisi = max(1, math.ceil(len(satirlar) / KILIT_PROGRAM_SAYFA_SATIRI))
    if sayfa is None:
        sayfa = 0
        if bugun_mu and satirlar:
            an = simdi if isinstance(simdi, str) else time.strftime("%H:%M")
            sira = next((i for i, s in enumerate(satirlar) if s["bitis"] > an), len(satirlar) - 1)
            sayfa = sira // KILIT_PROGRAM_SAYFA_SATIRI
    sayfa = min(max(sayfa if isinstance(sayfa, int) and not isinstance(sayfa, bool) else 0, 0), sayfa_sayisi - 1)
    bas = sayfa * KILIT_PROGRAM_SAYFA_SATIRI
    # Sunucunun iletisi dersler varken de gösterilir (ör. "Bugün program değişti").
    ileti = metin(veri.get("ileti"), KILIT_PROGRAM_ILETI_SINIRI)
    return {"gorunur": True, "baslik": baslik, "satirlar": satirlar[bas:bas + KILIT_PROGRAM_SAYFA_SATIRI],
            "ileti": ileti or ("" if satirlar else "Bugün için ders programı yok."), "sayfa": sayfa,
            "sayfa_sayisi": sayfa_sayisi, "sayfa_metni": f"{sayfa + 1} / {sayfa_sayisi}"}


def logo_olcusu(en: int, boy: int, olcek: float = 1.0) -> tuple[int, int]:
    """Logoyu bant yüksekliğine (1920x1080'de 96 px) ölçekler; genişlik 320 px'i aşarsa ona göre
    küçültür. İki sınır da ekran ölçeğiyle çarpılır."""
    if en <= 0 or boy <= 0:
        return 0, 0
    sinir_boy, sinir_en = olcekle(LOGO_BOY, olcek), olcekle(LOGO_EN, olcek)
    yeni_en, yeni_boy = round(en * sinir_boy / boy), sinir_boy
    if yeni_en > sinir_en:
        yeni_en, yeni_boy = sinir_en, max(1, round(boy * sinir_en / en))
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

    def gonder(self, mesaj: dict) -> bool:
        """Servise satır yollar; servis bağlı değilse ya da yazılamadıysa False."""
        with self.kilit:
            if self.soket is None:
                return False
            try:
                self.soket.sendall((json.dumps(mesaj, ensure_ascii=False) + "\n").encode("utf-8"))
                return True
            except OSError:
                return False

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
        # Açılışta kilit (0.9.0): yardımcının başladığı an (açılıştan saniye); servis oturumun yaşını bundan bulur.
        "oturum_baslangic": sistem.surec_baslangici(),
    }


def tek_ornek_yolu(ortam: dict | None = None) -> str | None:
    """Aynı oturumda (aynı kullanıcı + aynı ekran) tek yardımcı çalışsın diye kilit dosyasının yolu.

    Yalnız kullanıcıya özel XDG_RUNTIME_DIR kullanılır (/run/user/UID, 0700): /tmp'de başka bir hesap
    aynı adlı dosyayı önceden açıp kilit ekranını engelleyemesin. Dizin yoksa tek örnek denetimi yapılmaz.
    """
    ortam = os.environ if ortam is None else ortam
    dizin = ortam.get("XDG_RUNTIME_DIR") or ""
    if not dizin or not os.path.isdir(dizin):
        return None
    ekran_adi = re.sub(r"[^A-Za-z0-9_.-]", "_", ortam.get("WAYLAND_DISPLAY") or ortam.get("DISPLAY") or "yok")[:40]
    return os.path.join(dizin, f"tahta-ekran-{ekran_adi}.kilit")


def _tek_ornek_al():
    """Kilidi alır ve dosyayı açık tutar (süreç bitince çekirdek bırakır; eski dosya sorun değildir).
    Başka bir yardımcı tutuyorsa None döner. Denetim yapılamıyorsa (dizin yok, fcntl yok) True."""
    yol = tek_ornek_yolu()
    if yol is None:
        return True
    try:
        import fcntl

        dosya = open(yol, "a")  # noqa: SIM115 — süreç boyunca açık kalır
        fcntl.flock(dosya.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return dosya
    except BlockingIOError:
        return None
    except (OSError, ImportError):
        return True


def calistir() -> int:
    tek = _tek_ornek_al()
    if tek is None:
        # Bu oturumda yardımcı zaten çalışıyor (otomatik başlatma + elle başlatma): ikinci pencere/düğme açılmaz.
        print("Ekran yardımcısı bu oturumda zaten çalışıyor.", file=sys.stderr)
        return 0
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
    # Otomatik başlatma görüntü sunucusu hazır olmadan çalışırsa (oturum açılışında yarış) hemen
    # çökmeden bir süre beklenir; yardımcı hiç başlamazsa kilit yeni oturumda geri gelmezdi (G2).
    for _ in range(30):
        if Gdk.Screen.get_default() is not None:
            break
        sonuc = Gtk.init_check(sys.argv)
        if (sonuc[0] if isinstance(sonuc, tuple) else sonuc) and Gdk.Screen.get_default() is not None:
            break
        time.sleep(2)
    if Gdk.Screen.get_default() is None:
        print("Görüntü sunucusuna bağlanılamadı (DISPLAY).", file=sys.stderr)
        return 3

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
            self.yk_dugmeler: dict[int, dict] = {}  # id -> düğme kaydı (yalnız görünen sayfa)
            self.yk_durumlar: dict[int, str] = {}  # id -> "yok" | "gec" (bütün sayfalar; yoklama kapanınca silinir)
            self.yk_gec_secilebilir = False
            self.yk_duzey = None  # seçim görünümünde gösterilen düzey (yerel; servise gitmez)
            self.yk_duzey_sube = None
            self.yk_usb = False  # PIN sayfası USB kipinde (öğretmen kodu sorulmaz)
            self.usb_girilen = ""  # kilit açma PIN'i: yalnız gönderilene dek burada
            self.yk_guncelleniyor = False
            self.kilit_program_sayfa = 0
            self.kilit_program_tarih = None
            self.kilit_program_elle_bitis = 0.0  # Önceki/Sonraki seçimi bu ana dek (monotonik) korunur
            # Ekran ölçeği: pencerenin bulunduğu ekranın (monitör) boyutundan. Piksel ölçüleri
            # _olcu() ile kaydedilir; ölçek değişince (başka monitör, çözünürlük değişimi) yeniden uygulanır.
            self.pencere = None
            self.monitor = None
            self.ekran_en, self.ekran_boy = 0, 0
            self.olcek, self.dikey = None, False
            self._olcu_islevleri = []  # (işlev, 1920x1080 pikselleri)
            self._yon_kutulari = []  # dikey ekranda alt alta dizilen iki sütunlu gövdeler
            self.logo_olcekli = None  # (ölçek, pixbuf)

            # Sağlayıcılar: ölçüler ekran ölçeğiyle yüklenir; renkler tema değişince yenilenir.
            ekran = Gdk.Screen.get_default()
            self.olcu_saglayici = Gtk.CssProvider()
            self.olcu_saglayici.load_from_data(STIL_OLCU)
            Gtk.StyleContext.add_provider_for_screen(ekran, self.olcu_saglayici, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
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
            # Ölçek sayfalar kurulmadan hesaplanır: pencere henüz yokken birincil monitör esas alınır,
            # pencere o monitörde tam ekran açılır (_tam_ekran); sonra pencerenin bulunduğu monitör izlenir.
            self._ekran_denetle()
            ekran.connect("monitors-changed", lambda *_: self._ekran_degisti())
            ekran.connect("size-changed", lambda *_: self._ekran_degisti())
            self.pencere = Gtk.Window(title="Tahta Kontrol")
            self.pencere.set_decorated(False)
            self.pencere.set_keep_above(True)
            self.pencere.set_skip_taskbar_hint(True)
            self.pencere.set_skip_pager_hint(True)
            self.pencere.stick()
            self.pencere.connect("delete-event", lambda *_: True)

            self.yigin = Gtk.Stack()
            # GtkStack varsayılan olarak bütün sayfaların EN BÜYÜĞÜNE göre boyutlanır: bir sayfadaki
            # sığmayan öğe görünmediği hâlde kilit ve duyuru ekranını da taşırırdı. Yalnız görünen
            # sayfa ölçülür; ölçek de her sayfanın ekrana sığmasını sağlar (scripts/ekran_olcum.py).
            self.yigin.set_hhomogeneous(False)
            self.yigin.set_vhomogeneous(False)
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
            # USB anahtar (0.11.0): kilit açma PIN sayfası da show_all()'dan ÖNCE eklenir (GtkStack tuzağı).
            self.yigin.add_named(self._usb_pin_sayfasi(), "usb-pin")
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
            # Yüzer düğme (0.9.0, G3): kurulamazsa ekran düğmesiz çalışır (kilit ve duyuru etkilenmez).
            self.yuzer = None
            try:
                from . import yuzer

                self.yuzer = yuzer.kur(self)
            except Exception as hata:
                print(f"Yüzer düğme kurulamadı: {type(hata).__name__}: {hata}", file=sys.stderr)
            # USB anahtar bildirimi (0.11.0): kurulamazsa ekran bildirimsiz çalışır (kilit ekranındaki düğme yeter).
            self.usb_bildirim = None
            try:
                self.usb_bildirim = UsbBildirimi(self)
            except Exception as hata:
                print(f"USB bildirimi kurulamadı: {type(hata).__name__}: {hata}", file=sys.stderr)
            self.baglanti.merhaba = dict(
                _ortam_bilgisi(), arayuz="gtk3", genislik=geometri[0], yukseklik=geometri[1],
                dugme=self.yuzer is not None, bilesik=bool(ekran.is_composited()),
            )  # fmt: skip
            threading.Thread(target=self.baglanti.calis, daemon=True).start()
            GLib.timeout_add(1000, self._saniye)

        def _geometri(self):
            """Pencerenin bulunduğu (ya da açılacağı) monitörün boyutu."""
            return self.ekran_en, self.ekran_boy

        # ---- ekran ölçeği ve monitör --------------------------------------------------------
        def _monitor_bul(self):
            """Pencere ekrandaysa bulunduğu monitör; değilse birincil (yoksa ilk) monitör."""
            gosterge = Gdk.Display.get_default()
            monitor = None
            gdk_pencere = self.pencere.get_window() if self.pencere is not None else None
            if gdk_pencere is not None and gdk_pencere.is_viewable():
                monitor = gosterge.get_monitor_at_window(gdk_pencere)
            if monitor is None:
                monitor = gosterge.get_primary_monitor() or gosterge.get_monitor(0)
            return monitor

        def _ekran_denetle(self) -> bool:
            """Monitörü ve ölçeği yeniden hesaplar; ölçek ya da yön değiştiyse bütün ölçüleri yeniden
            uygular ve True döner."""
            try:
                monitor = self._monitor_bul()
                alan = monitor.get_geometry()
                en, boy = alan.width, alan.height
            except Exception:
                monitor, en, boy = None, 0, 0
            self.monitor, self.ekran_en, self.ekran_boy = monitor, en, boy
            olcek, dikey = ekran_olcegi(en, boy), dikey_mi(en, boy)
            if (olcek, dikey) == (self.olcek, self.dikey):
                return False
            self.olcek, self.dikey = olcek, dikey
            self.olcu_saglayici.load_from_data(olcekli_stil(STIL_OLCU, olcek))
            for islev, pikseller in self._olcu_islevleri:
                islev(*(olcekle(p, olcek) for p in pikseller))
            yon = Gtk.Orientation.VERTICAL if dikey else Gtk.Orientation.HORIZONTAL
            for kutu in self._yon_kutulari:
                kutu.set_orientation(yon)
            # Sonradan kurulan içerik yeni ölçüyle yeniden kurulur ya da yeniden boyutlanır.
            self.liste_imza = self.duyuru_imza = self.yk_secim_imza = None
            self.logo_olcekli = None
            if getattr(self, "izgara_dugmeleri", None):
                olcu = izgara_dugme_olcusu(len(self.izgara_dugmeleri), en, boy, olcek)
                for dugme, _ in self.izgara_dugmeleri.values():
                    dugme.set_size_request(*olcu)
            self.yk_liste_imza = None  # öğrenci ızgarası yeni ölçekle (ve yönle) yeniden kurulur
            if self.durum:
                GLib.idle_add(self._yeniden_ciz)
            return True

        def _yeniden_ciz(self):
            self._ciz()
            return False

        def _ekran_degisti(self):
            """Monitör eklendi/çıkarıldı ya da çözünürlük değişti."""
            self._ekran_denetle()
            if self.gorunur:
                self._tam_ekran()
            if getattr(self, "yuzer", None) is not None:
                self.yuzer.ekran_degisti()
            if self.ekran_en:
                self.baglanti.gonder({"tur": "ekran_durumu", "genislik": self.ekran_en, "yukseklik": self.ekran_boy,
                                      "klavye_kilidi": self.klavye_kilidi})  # fmt: skip

        def _monitor_sirasi(self) -> int:
            gosterge = Gdk.Display.get_default()
            for sira in range(gosterge.get_n_monitors()):
                if gosterge.get_monitor(sira) == self.monitor:
                    return sira
            return 0

        def _tam_ekran(self):
            """Pencere ölçeğin hesaplandığı monitörde tam ekran olur (çok ekranlı kurulumda başka
            monitöre geçip yanlış boyla çizilmesin)."""
            try:
                self.pencere.fullscreen_on_monitor(self.pencere.get_screen(), self._monitor_sirasi())
            except Exception:
                self.pencere.fullscreen()

        def _o(self, piksel):
            return olcekle(piksel, self.olcek)

        def _olcu(self, islev, *pikseller):
            """1920x1080 pikselleriyle bir ölçü ayarı (boşluk, kenar, en küçük boy): şimdi ölçekli
            uygulanır, ölçek değişince yeniden uygulanır. Sabit piksel doğrudan VERİLMEZ."""
            self._olcu_islevleri.append((islev, pikseller))
            islev(*(olcekle(p, self.olcek) for p in pikseller))

        def _kutu(self, yon, aralik=0, iki_sutun=False):
            kutu = Gtk.Box(orientation=yon)
            if aralik:
                self._olcu(kutu.set_spacing, aralik)
            if iki_sutun:
                # Yan yana iki sütun (bilgi + tuş takımı): portre ekranda alt alta dizilir.
                self._yon_kutulari.append(kutu)
                if self.dikey:
                    kutu.set_orientation(Gtk.Orientation.VERTICAL)
            return kutu

        def _izgara(self, satir_araligi, sutun_araligi):
            izgara = Gtk.Grid()
            self._olcu(izgara.set_row_spacing, satir_araligi)
            self._olcu(izgara.set_column_spacing, sutun_araligi)
            return izgara

        def _kenar(self, oge, bas=0, son=0, ust=0, alt=0):
            for islev, piksel in ((oge.set_margin_start, bas), (oge.set_margin_end, son),
                                  (oge.set_margin_top, ust), (oge.set_margin_bottom, alt)):  # fmt: skip
                if piksel:
                    self._olcu(islev, piksel)

        def _ekle(self, kutu, cocuk, dolgu=0, genis=False, son=False):
            """pack_start/pack_end; dolgu (padding) 1920x1080 pikseliyle verilir ve ölçeklenir."""
            (kutu.pack_end if son else kutu.pack_start)(cocuk, genis, genis, 0)
            if dolgu:
                self._olcu(lambda p: kutu.child_set_property(cocuk, "padding", p), dolgu)

        def _kaydirma(self, icerik):
            """Uzun içerik dikey kaydırılır. Yatay kaydırma yalnız güvenlik ağıdır: ölçekli içerik
            normalde sığar; sığmazsa da pencere ekrandan taşmaz (kaydırma alanının en küçük eni
            içeriğe bağlı değildir), içerik kaydırılır. Ölçüm betiği bunu "taştı" sayar."""
            kaydirma = Gtk.ScrolledWindow()
            kaydirma.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
            kaydirma.set_shadow_type(Gtk.ShadowType.NONE)
            kaydirma.add(icerik)
            return kaydirma

        def _etiket(self, ad, metin=""):
            etiket = Gtk.Label(label=metin)
            etiket.set_name(ad)
            etiket.set_line_wrap(True)
            etiket.set_justify(Gtk.Justification.CENTER)
            return etiket

        def _ust_bant(self):
            """Okul kimliği bandı: solda logo, yanında okul adı, sağda tahta adı · derslik."""
            bant = self._kutu(Gtk.Orientation.HORIZONTAL, 28)
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
            sag.set_max_width_chars(64)  # yer varken tahta adı · derslik kısaltılmasın (dar ekranda kısalır)
            bant.pack_start(logo_kutu, False, False, 0)
            bant.pack_start(okul, True, True, 0)
            bant.pack_end(sag, False, False, 0)
            self.bantlar.append((logo_kutu, logo_resmi, okul, sag))
            return bant

        def _sayfa(self, govde):
            """Sayfa iskeleti: üstte bant, altında ortalanmış gövde (sığmazsa kaydırılır)."""
            sayfa = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            sayfa.pack_start(self._ust_bant(), False, False, 0)
            govde.set_valign(Gtk.Align.CENTER)
            govde.set_halign(Gtk.Align.CENTER)
            self._kenar(govde, 48, 48, 24, 24)
            sayfa.pack_start(self._kaydirma(govde), True, True, 0)
            return sayfa

        def _tus_takimi(self, tuslar, islev):
            """12 tuşlu takım (1920x1080'de 150x96 tuş): kilit, gözetmen kodu ve yoklama PIN'i."""
            izgara = self._izgara(10, 10)
            izgara.set_column_homogeneous(True)
            izgara.set_row_homogeneous(True)
            for sira, tus in enumerate(tuslar):
                dugme = self._dugme(tus, lambda t=tus: islev(t), ana=tus in ("Aç", "Tamam"), en=150, boy=96)
                izgara.attach(dugme, sira % 3, sira // 3, 1, 1)
            return izgara

        def _kilit_sayfasi(self):
            govde = self._kutu(Gtk.Orientation.HORIZONTAL, 140, iki_sutun=True)
            sol = self._kutu(Gtk.Orientation.VERTICAL, 8)
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
            self._ekle(sol, self.cevrimdisi_dugmesi, 16)
            # Ders yoklaması (A5): yoklama etkin, tahta çevrimiçi ve kayıtlıysa görünür. Kilidi AÇMAZ;
            # yoklama bitince kilit ekranı geri gelir.
            self.kilit_yoklama = Gtk.Button(label="Yoklama al")
            self.kilit_yoklama.set_halign(Gtk.Align.CENTER)
            self.kilit_yoklama.set_can_focus(False)
            self.kilit_yoklama.connect("clicked", lambda *_: self.baglanti.gonder({"tur": "yoklama_ac"}))
            self._ekle(sol, self.kilit_yoklama, 16)

            # USB anahtar (0.11.0): anahtarın durumu ("USB anahtar tanındı · A. Yılmaz (kod 112)" ya da ileti).
            self.kilit_usb_bilgi = self._etiket("usb-bilgi")
            self.kilit_usb_bilgi.set_max_width_chars(40)
            self._ekle(sol, self.kilit_usb_bilgi, 8)

            # Dört kısa satır aynı anda görünür; uzun/ikili eğitim programı
            # sayfalanır. Aşağıda tuş takımından sonra sağ sütuna eklenir;
            # büyük saat ve kilit açıklamasının bulunduğu sol sütunu uzatmaz.
            # Satır etiketlerinin doğal eni sabittir (44 karakter) ve çok sayfalı programda dört satır
            # da yer tutar: sayfa değişince kutunun eni/boyu, dolayısıyla tuş takımının ve
            # Önceki/Sonraki düğmelerinin yeri değişmez.
            # İleti dersler varken de göründüğü için (0.13.1) aralıklar dardır: tuş takımı + USB düğmesi +
            # dört satır + iki satırlık ileti + gezgin 1366x768 ve 1920x1080'e kaydırmasız sığar.
            self.kilit_program_kutu = self._kutu(Gtk.Orientation.VERTICAL, 4)
            self.kilit_program_baslik = self._etiket("gunluk-program-baslik", "Bugünün ders programı")
            self.kilit_program_kutu.pack_start(self.kilit_program_baslik, False, False, 0)
            self.kilit_program_satirlari = []
            for _ in range(KILIT_PROGRAM_SAYFA_SATIRI):
                etiket = self._etiket("gunluk-program-satir")
                etiket.set_line_wrap(False)
                etiket.set_ellipsize(Pango.EllipsizeMode.END)
                etiket.set_width_chars(44)
                etiket.set_max_width_chars(44)
                self.kilit_program_kutu.pack_start(etiket, False, False, 0)
                self.kilit_program_satirlari.append(etiket)
            self.kilit_program_ileti = self._etiket("gunluk-program-satir")
            self.kilit_program_ileti.set_max_width_chars(44)
            self.kilit_program_ileti.set_lines(2)  # uzun ileti iki satırda kesilir; kutunun boyu sınırlı kalır
            self.kilit_program_ileti.set_ellipsize(Pango.EllipsizeMode.END)
            self.kilit_program_kutu.pack_start(self.kilit_program_ileti, False, False, 0)
            self.kilit_program_gezgin = self._kutu(Gtk.Orientation.HORIZONTAL, 12)
            self.kilit_program_gezgin.set_name("gunluk-program-gezgin")
            self.kilit_program_gezgin.set_halign(Gtk.Align.CENTER)
            self.kilit_program_onceki = self._dugme("Önceki", lambda: self._kilit_program_gec(-1))
            self.kilit_program_sayfa_etiketi = self._etiket("gunluk-program-sayfa")
            self.kilit_program_sayfa_etiketi.set_width_chars(7)  # sayfa numarası uzayınca düğmeler kaymasın
            self.kilit_program_sonraki = self._dugme("Sonraki", lambda: self._kilit_program_gec(1))
            for parca in (self.kilit_program_onceki, self.kilit_program_sayfa_etiketi, self.kilit_program_sonraki):
                self.kilit_program_gezgin.pack_start(parca, False, False, 0)
            self.kilit_program_kutu.pack_start(self.kilit_program_gezgin, False, False, 0)

            sag = self._kutu(Gtk.Orientation.VERTICAL, 24)
            sag.set_valign(Gtk.Align.CENTER)
            self.kod_kutusu = self._kutu(Gtk.Orientation.VERTICAL, 10)
            self.kod_kutusu.set_halign(Gtk.Align.CENTER)
            self.kod_kutusu.set_valign(Gtk.Align.CENTER)
            self.kod_etiketi = self._etiket("kod", "")
            self._ekle(self.kod_kutusu, self.kod_etiketi, 6)
            tuslar = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "Sil", "0", "Aç"]
            self.kod_kutusu.pack_start(self._tus_takimi(tuslar, lambda t: self._tus(None, t)), False, False, 0)
            sag.pack_start(self.kod_kutusu, False, False, 0)
            # Anahtar tanınmış ve kilit açma izni varken kod kutusunun altında ana düğme (show()/hide() ile).
            self.kilit_usb_dugmesi = self._dugme("USB anahtarla aç", lambda: self.baglanti.gonder({"tur": "usb_kilit_ac"}),
                                                 ana=True, boy=96)  # fmt: skip
            self.kilit_usb_dugmesi.set_halign(Gtk.Align.CENTER)
            sag.pack_start(self.kilit_usb_dugmesi, False, False, 0)
            self._ekle(sag, self.kilit_program_kutu)
            govde.pack_start(sag, False, False, 0)
            self.kilit_sag = sag
            return self._sayfa(govde)

        def _kilit_program_gec(self, fark):
            self.kilit_program_sayfa += fark
            self.kilit_program_elle_bitis = time.monotonic() + KILIT_PROGRAM_ELLE_SN
            self._kilit_program_ciz()

        def _kilit_program_ciz(self):
            veri = (self.durum or {}).get("gun_programi")
            tarih = veri.get("tarih") if isinstance(veri, dict) else None
            if tarih != self.kilit_program_tarih:
                self.kilit_program_tarih = tarih
                self.kilit_program_elle_bitis = 0.0
            # Elle seçim yoksa (ya da süresi dolduysa) şimdiki/sıradaki dersin sayfası gösterilir.
            elle = time.monotonic() < self.kilit_program_elle_bitis
            gorunum = gunluk_program_gorunumu(self.durum or {}, self.kilit_program_sayfa if elle else None)
            self.kilit_program_sayfa = gorunum["sayfa"]
            self.kilit_program_kutu.set_visible(gorunum["gorunur"])
            self.kilit_program_baslik.set_text(gorunum["baslik"])
            cok_sayfa = gorunum["sayfa_sayisi"] > 1
            for i, etiket in enumerate(self.kilit_program_satirlari):
                satir = gorunum["satirlar"][i] if i < len(gorunum["satirlar"]) else None
                yazi = (f"{satir['ders_no']}. {satir['baslangic']}–{satir['bitis']} · {satir['sube']} · {satir['ders']}"
                        if satir else "")
                etiket.set_text(yazi)
                etiket.set_tooltip_text(yazi or None)
                etiket.set_visible(bool(satir) or cok_sayfa)  # son sayfanın boş satırları da yer tutar
            self.kilit_program_ileti.set_text(gorunum["ileti"])
            self.kilit_program_ileti.set_tooltip_text(gorunum["ileti"] or None)
            self.kilit_program_ileti.set_visible(bool(gorunum["ileti"]))
            self.kilit_program_gezgin.set_visible(gorunum["sayfa_sayisi"] > 1)
            self.kilit_program_sayfa_etiketi.set_text(gorunum["sayfa_metni"])
            self.kilit_program_onceki.set_sensitive(gorunum["sayfa"] > 0)
            self.kilit_program_sonraki.set_sensitive(gorunum["sayfa"] + 1 < gorunum["sayfa_sayisi"])
            # Gece yarısında program gizlenince boş sağ sütun da kalkar;
            # kod veya USB açma görünüyorsa sütun korunur.
            self.kilit_sag.set_visible(self.kod_kutusu.get_visible() or self.kilit_usb_dugmesi.get_visible()
                                       or gorunum["gorunur"])

        def _duyuru_sayfasi(self):
            """Bant, ortada kaydırılabilir başlık + metin (çok satırlıysa sütunlar), altta Kapat.

            Uzun metin ortayı büyütemez: Kapat düğmesi her metin uzunluğunda ekranda kalır.
            """
            kutu = self._kutu(Gtk.Orientation.VERTICAL, 30)
            self._kenar(kutu, 80, 80, 24, 24)
            kutu.set_valign(Gtk.Align.CENTER)
            kutu.set_halign(Gtk.Align.CENTER)
            self.duyuru_baslik = self._etiket("duyuru-baslik")
            self.duyuru_metin = self._etiket("duyuru-metin")
            self.duyuru_metin.set_max_width_chars(48)
            self.duyuru_ust = self._etiket("duyuru-ust")
            self.duyuru_sutunlar = self._kutu(Gtk.Orientation.HORIZONTAL, 70)
            self.duyuru_sutunlar.set_halign(Gtk.Align.CENTER)
            for parca in (self.duyuru_baslik, self.duyuru_metin, self.duyuru_ust, self.duyuru_sutunlar):
                kutu.pack_start(parca, False, False, 0)
            kaydirma = self._kaydirma(kutu)
            self.duyuru_kapat = Gtk.Button(label="Kapat")
            self.duyuru_kapat.set_halign(Gtk.Align.CENTER)
            self.duyuru_kapat.set_can_focus(False)
            self._kenar(self.duyuru_kapat, ust=16, alt=32)
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
            duzen = duyuru_duzeni(metin, self.ekran_boy, self.olcek, self.ekran_en)
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
            kutu = self._kutu(Gtk.Orientation.VERTICAL, 18)
            self._kenar(kutu, 80, 80)
            # Aynı sayfa oturum temizliği uyarısında da kullanılır (K7): başlık ve Vazgeç'in gönderdiği
            # ileti `kapatma_kipi`ne göre değişir.
            self.kapatma_kipi = "kapatma"
            self.kapatma_baslik = self._etiket("kapatma-baslik", "Bu tahta kapatılacak")
            self.kapatma_sayac = self._etiket("kapatma-sayac")
            self.kapatma_neden = self._etiket("kapatma-neden")
            vazgec = Gtk.Button(label="Vazgeç — tahtayı kullanıyorum")
            vazgec.set_name("ana-dugme")
            vazgec.set_halign(Gtk.Align.CENTER)
            vazgec.set_can_focus(False)
            vazgec.connect(
                "clicked",
                lambda *_: self.baglanti.gonder(
                    {"tur": "temizlik_iptal" if self.kapatma_kipi == "temizlik" else "kapatma_iptal"}
                ),
            )
            for parca in (self.kapatma_baslik, self.kapatma_sayac, self.kapatma_neden, vazgec):
                kutu.pack_start(parca, False, False, 0)
            return self._sayfa(kutu)

        def _acil_sayfasi(self):
            """Acil durum / tatbikat: tam ekran, okul bandı yok; renk pencere sınıfından gelir.

            Yerleşim üç kattır: üstte bant, ortada kaydırılabilir başlık + metin, altta okul ·
            saat satırı ve "yayını kapat" düğmesi. Uzun metin ortayı büyütemez: alt kat (kural 3
            düğmesi) her metin uzunluğunda ekranda kalır.
            """
            sayfa = self._kutu(Gtk.Orientation.VERTICAL, 24)
            self._kenar(sayfa, 80, 80, 40, 40)
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

            orta = self._kutu(Gtk.Orientation.VERTICAL, 30)
            orta.set_valign(Gtk.Align.CENTER)
            orta.pack_start(self.acil_baslik, False, False, 0)
            orta.pack_start(self.acil_metin, False, False, 0)
            kaydirma = self._kaydirma(orta)  # kendi Viewport'unu ekler

            alt = self._kutu(Gtk.Orientation.VERTICAL, 16)
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
            self._kenar(govde, 60, 60, 24, 28)
            sayfa.pack_start(govde, True, True, 0)
            return sayfa

        def _dugme(self, metin, islev, ana=False, en=0, boy=0, gecici=False):
            """Düğme; en/boy 1920x1080 pikseliyle verilir ve ekran ölçeğiyle küçülür/büyür. Sonradan
            kurulup yok edilen (gecici) düğmenin ölçüsü kaydedilmez: ölçek değişince yeniden kurulur."""
            dugme = Gtk.Button(label=metin)
            dugme.set_can_focus(False)
            if ana:
                dugme.set_name("ana-dugme")
            if gecici and (en or boy):
                dugme.set_size_request(self._o(en or -1), self._o(boy or -1))
            elif en or boy:
                self._olcu(dugme.set_size_request, en or -1, boy or -1)
            dugme.connect("clicked", lambda *_: islev())
            return dugme

        def _sinav_alt(self):
            """Sınav sayfalarının alt satırı: solda saat, ortada çevrimdışı bilgisi ve düğmesi
            (kural 3), sağda "Gözetmen"."""
            alt = self._kutu(Gtk.Orientation.HORIZONTAL, 24)
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
            govde = self._kutu(Gtk.Orientation.VERTICAL, 10)
            self.sg_ad = self._etiket("sinav-adi")
            self.sg_ad.set_max_width_chars(60)
            self.sg_salon = self._etiket("sinav-salon")
            self.sg_bilgi = self._etiket("sinav-bilgi")
            self.sg_liste = self._izgara(2, 22)
            self.sg_liste.set_halign(Gtk.Align.CENTER)
            self.sg_liste.set_valign(Gtk.Align.START)
            self.sg_fazla = self._etiket("sinav-fazla")
            for parca in (self.sg_ad, self.sg_salon, self.sg_bilgi):
                govde.pack_start(parca, False, False, 0)
            self._ekle(govde, self._kaydirma(self.sg_liste), 12, genis=True)
            govde.pack_start(self.sg_fazla, False, False, 0)
            govde.pack_end(self._sinav_alt(), False, False, 0)
            return self._sayfa_dolu(govde)

        def _sinav_sayfasi(self):
            govde = self._kutu(Gtk.Orientation.VERTICAL, 8)
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
            orta = self._kutu(Gtk.Orientation.VERTICAL, 10)
            orta.set_valign(Gtk.Align.CENTER)
            for parca in (self.ss_ad, self.ss_salon, self.ss_sayac, self.ss_bitis, self.ss_kurallar, self.ss_durum):
                orta.pack_start(parca, False, False, 0)
            govde.pack_start(self._kaydirma(orta), True, True, 0)
            govde.pack_end(self._sinav_alt(), False, False, 0)
            return self._sayfa_dolu(govde)

        def _gozetmen_kod_sayfasi(self):
            govde = self._kutu(Gtk.Orientation.HORIZONTAL, 120, iki_sutun=True)
            sol = self._kutu(Gtk.Orientation.VERTICAL, 12)
            sol.set_valign(Gtk.Align.CENTER)
            # Hata metni gelince tuş takımı kaymasın: sol sütunun eni ölçekli sabittir (1920'de 640).
            self._olcu(sol.set_size_request, 640, -1)
            sol.pack_start(self._etiket("gozetmen-baslik", "Gözetmen kodu"), False, False, 0)
            self.gk_salon = self._etiket("sinav-salon")
            self.gk_bilgi = self._etiket("gozetmen-bilgi", "Salon fişindeki 6 haneli kodu girin.")
            self.gk_bilgi.set_max_width_chars(34)
            self.gk_hata = self._etiket("gozetmen-hata")
            self.gk_hata.set_max_width_chars(34)
            for parca in (self.gk_salon, self.gk_bilgi, self.gk_hata):
                sol.pack_start(parca, False, False, 0)
            vazgec = self._dugme("Vazgeç", self._gozetmen_vazgec)
            vazgec.set_halign(Gtk.Align.CENTER)
            self._ekle(sol, vazgec, 24)
            sag = self._kutu(Gtk.Orientation.VERTICAL, 10)
            sag.set_valign(Gtk.Align.CENTER)
            self.gk_kod = self._etiket("kod", "")
            self._ekle(sag, self.gk_kod, 6)
            self.gk_tuslar = self._tus_takimi(["1", "2", "3", "4", "5", "6", "7", "8", "9", "Sil", "0", "Tamam"],
                                              self._gozetmen_tus)  # fmt: skip
            sag.pack_start(self.gk_tuslar, False, False, 0)
            govde.pack_start(sol, False, False, 0)
            govde.pack_start(sag, False, False, 0)
            return self._sayfa(govde)

        def _gozetmen_menu_sayfasi(self):
            govde = self._kutu(Gtk.Orientation.VERTICAL, 16)
            govde.pack_start(self._etiket("gozetmen-baslik", "Gözetmen"), False, False, 0)
            self.gm_salon = self._etiket("sinav-salon")
            govde.pack_start(self.gm_salon, False, False, 0)
            self.gm_yoklama = self._dugme("Yoklama al", lambda: self.baglanti.gonder({"tur": "gozetmen_yoklama"}),
                                          ana=True, en=560, boy=110)  # fmt: skip
            self.gm_yoklama.set_halign(Gtk.Align.CENTER)
            self._ekle(govde, self.gm_yoklama, 20)
            self.gm_neden = self._etiket("gozetmen-bilgi")
            self.gm_hata = self._etiket("gozetmen-hata")
            govde.pack_start(self.gm_neden, False, False, 0)
            govde.pack_start(self.gm_hata, False, False, 0)
            cik = self._dugme("Çık", lambda: self.baglanti.gonder({"tur": "gozetmen_cikis"}), en=300, boy=90)
            cik.set_halign(Gtk.Align.CENTER)
            self._ekle(govde, cik, 20)
            return self._sayfa(govde)

        def _gozetmen_yoklama_sayfasi(self):
            govde = self._kutu(Gtk.Orientation.VERTICAL, 10)
            self.gy_baslik = self._etiket("sinav-adi")
            self.gy_hata = self._etiket("gozetmen-hata")
            self.gy_izgara = self._izgara(10, 10)
            self.gy_izgara.set_row_homogeneous(True)
            self.gy_izgara.set_column_homogeneous(True)
            self.gy_izgara.set_halign(Gtk.Align.CENTER)
            self.gy_izgara.set_valign(Gtk.Align.CENTER)
            alt = self._kutu(Gtk.Orientation.HORIZONTAL, 24)
            alt.set_halign(Gtk.Align.CENTER)
            self.gy_kaydet = self._dugme("Kaydet", self._gozetmen_kaydet, ana=True, en=320, boy=90)
            self.gy_vazgec = self._dugme("Vazgeç", lambda: self.baglanti.gonder({"tur": "gozetmen_cikis"}), en=240, boy=90)
            alt.pack_start(self.gy_kaydet, False, False, 0)
            alt.pack_start(self.gy_vazgec, False, False, 0)
            govde.pack_start(self.gy_baslik, False, False, 0)
            govde.pack_start(self.gy_hata, False, False, 0)
            self._ekle(govde, self._kaydirma(self.gy_izgara), 8, genis=True)
            govde.pack_end(alt, False, False, 0)
            return self._sayfa_dolu(govde)

        # ---- ders yoklaması sayfaları (A5) -----------------------------------------------
        def _yoklama_pin_sayfasi(self):
            """Öğretmen kodu (3 hane) ve PIN (6 hane): kilit tuş takımıyla aynı ölçüde 12 tuş."""
            govde = self._kutu(Gtk.Orientation.HORIZONTAL, 120, iki_sutun=True)
            sol = self._kutu(Gtk.Orientation.VERTICAL, 12)
            sol.set_valign(Gtk.Align.CENTER)
            # Hata metni gelince tuş takımı kaymasın: sol sütunun eni ölçekli sabittir (1920'de 720).
            self._olcu(sol.set_size_request, 720, -1)
            self.yp_baslik = self._etiket("yoklama-baslik", "Ders yoklaması")
            self.yp_baslik.set_max_width_chars(28)
            sol.pack_start(self.yp_baslik, False, False, 0)
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
            self._ekle(sol, vazgec, 24)
            # USB kipinde: bellek takılıyken başka öğretmen kendi kodu ve PIN'iyle yoklama alabilsin.
            self.yp_kodpin = self._dugme("Başka öğretmen (kod ve PIN)", lambda: self.baglanti.gonder({"tur": "yoklama_kod_pin"}))
            self.yp_kodpin.set_halign(Gtk.Align.CENTER)
            sol.pack_start(self.yp_kodpin, False, False, 0)
            sag = self._kutu(Gtk.Orientation.VERTICAL, 10)
            sag.set_valign(Gtk.Align.CENTER)
            self.yp_kod = self._etiket("kod", "")
            self._ekle(sag, self.yp_kod, 6)
            self.yp_tuslar = self._tus_takimi(["1", "2", "3", "4", "5", "6", "7", "8", "9", "Sil", "0", "Tamam"],
                                              self._yoklama_tus)  # fmt: skip
            sag.pack_start(self.yp_tuslar, False, False, 0)
            govde.pack_start(sol, False, False, 0)
            govde.pack_start(sag, False, False, 0)
            return self._sayfa(govde)

        def _usb_pin_sayfasi(self):
            """USB anahtarla kilit açma PIN'i (0.11.0): yoklama PIN sayfasıyla aynı yerleşim, 12 tuş."""
            govde = self._kutu(Gtk.Orientation.HORIZONTAL, 120, iki_sutun=True)
            sol = self._kutu(Gtk.Orientation.VERTICAL, 12)
            sol.set_valign(Gtk.Align.CENTER)
            self._olcu(sol.set_size_request, 720, -1)
            sol.pack_start(self._etiket("yoklama-baslik", "USB anahtarla aç"), False, False, 0)
            self.up_sahip = self._etiket("yoklama-bilgi")
            self.up_sahip.set_max_width_chars(40)
            self.up_adim = self._etiket("yoklama-adim", "PIN'inizi girin")
            self.up_hata = self._etiket("yoklama-hata")
            self.up_hata.set_max_width_chars(36)
            ipucu = self._etiket("yoklama-bilgi", "PIN'i girerken tuş takımını elinizle kapatın.")
            ipucu.set_max_width_chars(40)
            for parca in (self.up_sahip, self.up_adim, self.up_hata, ipucu):
                sol.pack_start(parca, False, False, 0)
            vazgec = self._dugme("Vazgeç", self._usb_vazgec, en=300, boy=90)
            vazgec.set_halign(Gtk.Align.CENTER)
            self._ekle(sol, vazgec, 24)
            sag = self._kutu(Gtk.Orientation.VERTICAL, 10)
            sag.set_valign(Gtk.Align.CENTER)
            self.up_kod = self._etiket("kod", "")
            self._ekle(sag, self.up_kod, 6)
            self.up_tuslar = self._tus_takimi(["1", "2", "3", "4", "5", "6", "7", "8", "9", "Sil", "0", "Tamam"], self._usb_tus)
            sag.pack_start(self.up_tuslar, False, False, 0)
            govde.pack_start(sol, False, False, 0)
            govde.pack_start(sag, False, False, 0)
            return self._sayfa(govde)

        def _usb_tus(self, tus):
            if tus == "Sil":
                self.usb_girilen = self.usb_girilen[:-1]
            elif tus == "Tamam":
                if len(self.usb_girilen) == YOKLAMA_PIN_HANE:
                    # PIN servise iletilir ve sunucuda doğrulanır; burada saklanmaz.
                    self.baglanti.gonder({"tur": "usb_pin", "pin": self.usb_girilen})
                    self.usb_girilen = ""
            elif len(self.usb_girilen) < YOKLAMA_PIN_HANE:
                self.usb_girilen += tus
            self.up_kod.set_text("●" * len(self.usb_girilen) + "○" * (YOKLAMA_PIN_HANE - len(self.usb_girilen)))

        def _usb_vazgec(self):
            self.usb_girilen = ""
            self.baglanti.gonder({"tur": "usb_vazgec"})

        def _yoklama_izgarasi(self, aralik=8):
            """Alanı eşit paylaşan ızgara: sabit en/boy yok, yalnız sütun x satır seçilir (kaydırma yok)."""
            izgara = self._izgara(aralik, aralik)
            izgara.set_row_homogeneous(True)
            izgara.set_column_homogeneous(True)
            izgara.set_hexpand(True)
            izgara.set_vexpand(True)
            return izgara

        def _yoklama_basligi(self, metin):
            baslik = Gtk.Label(label=metin)
            baslik.set_name("secim-baslik")
            baslik.set_xalign(0)
            baslik.set_ellipsize(Pango.EllipsizeMode.END)
            return baslik

        def _yoklama_liste_sayfasi(self):
            """Liste görünümü: üstte şube + BÜYÜK ders/saat düğmesi + öğretmen + kalan süre, ortada alanı paylaşan
            öğrenci ızgarası, altta "Yok · Geç · Derste" [‹] Sayfa 1/2 [›] [Temizle] [Vazgeç] [KAYDET].
            Seçim görünümü (aynı sayfa): üstte öneri düğmesi + ★ öne alınan şubeler; solda düzey, ortada şube
            ızgarası, sağda ders saati sütunu. İki görünümde de KAYDIRMA YOKTUR."""
            def gonder(mesaj):  # bağlantı sayfalardan sonra kurulur: dokunuş anında okunur
                self.baglanti.gonder(mesaj)

            govde = self._kutu(Gtk.Orientation.VERTICAL, 10)
            ust = self._kutu(Gtk.Orientation.HORIZONTAL, 20, iki_sutun=True)  # portre ekranda iki satır
            ust_sol = self.yl_ust_sol = self._kutu(Gtk.Orientation.HORIZONTAL, 20)
            ust_sag = self._kutu(Gtk.Orientation.HORIZONTAL, 20)
            self.yl_sube = Gtk.Label(label="")
            self.yl_sube.set_name("yoklama-sube")
            self.yl_ders = self._dugme("", lambda: gonder({"tur": "yoklama_sec", "secim": True}))
            self.yl_ders.set_name("yoklama-ders")
            self.yl_ust = Gtk.Label(label="")
            self.yl_ust.set_name("yoklama-ust")
            self.yl_ust.set_xalign(0)
            self.yl_ust.set_ellipsize(Pango.EllipsizeMode.END)
            self.yl_degistir = self._dugme("Şube değiştir", lambda: gonder({"tur": "yoklama_sec", "secim": True}))
            self.yl_kalan = Gtk.Label(label="")
            self.yl_kalan.set_name("yoklama-kalan")
            ust_sol.pack_start(self.yl_sube, False, False, 0)
            ust_sol.pack_start(self.yl_ders, False, False, 0)
            ust_sag.pack_start(self.yl_ust, True, True, 0)
            ust_sag.pack_end(self.yl_kalan, False, False, 0)
            ust_sag.pack_end(self.yl_degistir, False, False, 0)
            ust.pack_start(ust_sol, False, False, 0)
            ust.pack_start(ust_sag, True, True, 0)
            self.yl_bilgi = Gtk.Label(label="")
            self.yl_bilgi.set_name("yoklama-bilgi")
            self.yl_bilgi.set_xalign(0)
            self.yl_bilgi.set_line_wrap(True)  # dar (portre) ekranda ikinci satıra iner; pencereyi genişletmez
            self.yl_bilgi.set_lines(2)
            self.yl_bilgi.set_ellipsize(Pango.EllipsizeMode.END)
            self.yl_hata = Gtk.Label(label="")
            self.yl_hata.set_name("yoklama-hata")
            self.yl_hata.set_xalign(0)
            self.yl_hata.set_line_wrap(True)
            self.yl_hata.set_lines(2)
            self.yl_hata.set_ellipsize(Pango.EllipsizeMode.END)

            self.yl_izgara = self._yoklama_izgarasi()

            self.yl_secim = self._kutu(Gtk.Orientation.VERTICAL, 14)
            self.yl_once = self._kutu(Gtk.Orientation.HORIZONTAL, 12, iki_sutun=True)  # öneri düğmesi + ★ şubeler
            self.yl_oneri_kutu = self._kutu(Gtk.Orientation.HORIZONTAL, 12)
            self.yl_yildizlar = self._kutu(Gtk.Orientation.HORIZONTAL, 12)
            self.yl_once.pack_start(self.yl_oneri_kutu, False, False, 0)
            self.yl_once.pack_start(self.yl_yildizlar, False, False, 0)
            orta = self._kutu(Gtk.Orientation.HORIZONTAL, 28, iki_sutun=True)
            self.yl_duzey_kutu = self._kutu(Gtk.Orientation.VERTICAL, 8)
            self.yl_duzeyler = self._yoklama_izgarasi()
            self.yl_duzeyler.set_hexpand(False)
            self.yl_duzey_kutu.pack_start(self._yoklama_basligi("Düzey"), False, False, 0)
            self.yl_duzey_kutu.pack_start(self.yl_duzeyler, True, True, 0)
            sube_kutu = self._kutu(Gtk.Orientation.VERTICAL, 8)
            self.yl_sube_baslik = self._yoklama_basligi("Şube")
            self.yl_subeler = self._yoklama_izgarasi()
            sube_kutu.pack_start(self.yl_sube_baslik, False, False, 0)
            sube_kutu.pack_start(self.yl_subeler, True, True, 0)
            ders_kutu = self._kutu(Gtk.Orientation.VERTICAL, 8)
            self.yl_ders_baslik = self._yoklama_basligi("Ders saati")
            self.yl_dersler = self._yoklama_izgarasi()
            self.yl_dersler.set_hexpand(False)
            self.yl_ders_bos = self._etiket("yoklama-bilgi", "Önce şubeyi seçin.")
            self.yl_ders_bos.set_valign(Gtk.Align.START)
            ders_kutu.pack_start(self.yl_ders_baslik, False, False, 0)
            ders_kutu.pack_start(self.yl_dersler, True, True, 0)
            ders_kutu.pack_start(self.yl_ders_bos, True, True, 0)
            orta.pack_start(self.yl_duzey_kutu, False, False, 0)
            orta.pack_start(sube_kutu, True, True, 0)
            orta.pack_start(ders_kutu, False, False, 0)
            self.yl_secim.pack_start(self.yl_once, False, False, 0)
            self.yl_secim.pack_start(orta, True, True, 0)

            alt = self.yl_alt = self._kutu(Gtk.Orientation.HORIZONTAL, 16, iki_sutun=True)  # portre ekranda iki satır
            alt_sol = self._kutu(Gtk.Orientation.HORIZONTAL, 16)
            alt_sag = self._kutu(Gtk.Orientation.HORIZONTAL, 16)
            self.yl_sayi = Gtk.Label(label="")
            self.yl_sayi.set_name("yoklama-sayi")
            self.yl_sayi.set_xalign(0)
            self.yl_sayi.set_ellipsize(Pango.EllipsizeMode.END)  # dar ekranda düğmeleri ekrandan itmesin
            self.yl_geri = self._dugme("‹", lambda: gonder({"tur": "yoklama_sayfa", "yon": -1}), en=90, boy=90)
            self.yl_ileri = self._dugme("›", lambda: gonder({"tur": "yoklama_sayfa", "yon": 1}), en=90, boy=90)
            self.yl_sayfa = Gtk.Label(label="")
            self.yl_sayfa.set_name("yoklama-sayfa")
            # [Temizle] bütün sayfalardaki işaretleri siler ve geri alınamaz: KAYDET/Vazgeç'ten uzakta (en solda) durur
            # ve iki dokunuş ister (ilk dokunuş "Hepsini sil (n)" diye sorar, birkaç saniyede kendiliğinden vazgeçer).
            self.yk_temizle_onay = None  # (monotonik bitiş, o andaki işaret sayısı) | None
            self.yl_temizle = self._dugme("Temizle", self._yoklama_temizle_dokun, boy=90)
            self.yl_kaydet = self._dugme("KAYDET", self._yoklama_ana_dugme, ana=True, en=300, boy=90)
            vazgec = self._dugme("Vazgeç", lambda: gonder({"tur": "yoklama_kapat"}), boy=90)
            alt_sol.pack_start(self.yl_temizle, False, False, 0)
            alt_sol.pack_start(self.yl_sayi, True, True, 0)
            for parca in (self.yl_ileri, self.yl_sayfa, self.yl_geri):
                alt_sol.pack_end(parca, False, False, 0)
            for parca in (self.yl_kaydet, vazgec):
                alt_sag.pack_end(parca, False, False, 0)
            alt.pack_start(alt_sol, True, True, 0)
            alt.pack_start(alt_sag, False, False, 0)

            govde.pack_start(ust, False, False, 0)
            govde.pack_start(self.yl_bilgi, False, False, 0)
            govde.pack_start(self.yl_hata, False, False, 0)
            govde.pack_start(self.yl_izgara, True, True, 0)
            govde.pack_start(self.yl_secim, True, True, 0)
            govde.pack_end(alt, False, False, 0)
            return self._sayfa_dolu(govde)

        def _yoklama_onay_sayfasi(self):
            govde = self._kutu(Gtk.Orientation.VERTICAL, 24)
            self.yo_ust = self._etiket("yoklama-bilgi")
            self.yo_baslik = self._etiket("yoklama-baslik")
            self.yo_liste = self._etiket("yoklama-onay-liste")
            self.yo_liste.set_max_width_chars(70)
            self.yo_hata = self._etiket("yoklama-hata")
            self.yo_hata.set_max_width_chars(50)
            dugmeler = self._kutu(Gtk.Orientation.HORIZONTAL, 24)
            dugmeler.set_halign(Gtk.Align.CENTER)
            self.yo_geri = self._dugme("Geri", lambda: self.baglanti.gonder({"tur": "yoklama_geri"}), en=300, boy=96)
            self.yo_onayla = self._dugme("Onayla", lambda: self.baglanti.gonder({"tur": "yoklama_onayla"}), ana=True, en=300, boy=96)
            dugmeler.pack_start(self.yo_geri, False, False, 0)
            dugmeler.pack_start(self.yo_onayla, False, False, 0)
            for parca in (self.yo_ust, self.yo_baslik, self.yo_liste, self.yo_hata):
                govde.pack_start(parca, False, False, 0)
            self._ekle(govde, dugmeler, 16)
            return self._sayfa(govde)

        def _yoklama_ileti_sayfasi(self):
            govde = self._kutu(Gtk.Orientation.VERTICAL, 40)
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
            self._koltuk_etiketi_hizala(dugme)  # set_label etiketi yeniden kurar
            self._izgara_basligi()

        def _koltuk_etiketi_hizala(self, dugme):
            """Ortalı ve satır satır kısaltılabilir: uzun maskeli ad düğmeyi (ve ızgarayı) genişletmesin;
            koltuk numarası ilk satırdadır, kısalan yalnız adın sonu olur."""
            etiket = dugme.get_child()
            if isinstance(etiket, Gtk.Label):
                etiket.set_justify(Gtk.Justification.CENTER)
                etiket.set_ellipsize(Pango.EllipsizeMode.END)

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
            sutun = izgara_sutun(n, self.ekran_en, self.ekran_boy)
            dugme_en, dugme_boy = izgara_dugme_olcusu(n, self.ekran_en, self.ekran_boy, self.olcek)
            for sira, oge in enumerate(liste):
                gelmedi = oge["k"] in self.izgara_isaret
                dugme = Gtk.ToggleButton(label=koltuk_etiketi(oge, gelmedi))
                dugme.set_name("koltuk")
                dugme.set_can_focus(False)
                dugme.set_size_request(dugme_en, dugme_boy)
                dugme.set_active(gelmedi)
                self._koltuk_etiketi_hizala(dugme)
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
            karakter = liste_satir_karakteri(liste)
            sutun = liste_sutun_sayisi(n, self.ekran_en, self.olcek, karakter)
            satir = -(-n // sutun)
            punto = liste_punto(satir, self.ekran_boy, self.olcek, self.ekran_en, sutun, karakter)
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
                    ara.set_size_request(self._o(56), -1)
                    self.sg_liste.attach(ara, kolon * 5 + 4, 0, 1, 1)
            self.sg_liste.show_all()

        # ---- ders yoklaması (A5) ------------------------------------------------------------
        def _tus_basildi(self, _pencere, olay):
            """Fiziksel klavye: yalnız yoklama PIN sayfasında rakam, BackSpace (Sil), Enter (Tamam)."""
            sayfa = self.yigin.get_visible_child_name()
            if sayfa == "yoklama-pin" and self.yp_tuslar.get_sensitive():
                islev = self._yoklama_tus
            elif sayfa == "usb-pin" and self.up_tuslar.get_sensitive():
                islev = self._usb_tus
            else:
                return False
            ad = Gdk.keyval_name(olay.keyval) or ""
            ad = ad[3:] if ad.startswith("KP_") else ad
            if len(ad) == 1 and ad.isdigit():
                islev(ad)
            elif ad == "BackSpace":
                islev("Sil")
            elif ad in ("Return", "Enter"):
                islev("Tamam")
            else:
                return False
            return True

        def _yoklama_tus(self, tus):
            if tus == "Sil":
                if self.yk_adim == "pin" and not self.yk_pin and not self.yk_usb:
                    self.yk_adim = "kod"  # boş PIN'de Sil: öğretmen kodunu düzeltmeye dön
                elif self.yk_adim == "pin":
                    self.yk_pin = self.yk_pin[:-1]
                else:
                    self.yk_kod = self.yk_kod[:-1]
            elif tus == "Tamam":
                if self.yk_adim == "kod" and len(self.yk_kod) == YOKLAMA_KOD_HANE:
                    self.yk_adim = "pin"
                elif self.yk_adim == "pin" and len(self.yk_pin) == YOKLAMA_PIN_HANE:
                    # PIN servise iletilir ve sunucuda doğrulanır; burada saklanmaz. USB kipinde kod boş gider.
                    kod = "" if self.yk_usb else self.yk_kod
                    self.baglanti.gonder({"tur": "yoklama_pin", "kod": kod, "pin": self.yk_pin})
                    self.yk_pin = ""
            elif self.yk_adim == "kod":
                self.yk_kod = (self.yk_kod + tus)[:YOKLAMA_KOD_HANE]
                if len(self.yk_kod) == YOKLAMA_KOD_HANE:
                    self.yk_adim = "pin"  # üçüncü haneden sonra PIN'e geçilir
            elif len(self.yk_pin) < YOKLAMA_PIN_HANE:
                self.yk_pin += tus
            self._yoklama_pin_yaz()

        def _yoklama_pin_yaz(self):
            if self.yk_usb:
                self.yp_adim.set_text("PIN'inizi girin")
                self.yp_kod.set_text("●" * len(self.yk_pin) + "○" * (YOKLAMA_PIN_HANE - len(self.yk_pin)))
            elif self.yk_adim == "kod":
                self.yp_adim.set_text("Öğretmen kodunuz (3 hane)")
                # Öğretmen kodu gizli değildir; PIN yalnız nokta olarak görünür.
                self.yp_kod.set_text(self.yk_kod + "_" * (YOKLAMA_KOD_HANE - len(self.yk_kod)))
            else:
                self.yp_adim.set_text(f"PIN (6 hane) · öğretmen kodu {self.yk_kod}")
                self.yp_kod.set_text("●" * len(self.yk_pin) + "○" * (YOKLAMA_PIN_HANE - len(self.yk_pin)))

        def _yoklama_liste_temizle(self):
            """Öğrenci düğmeleri yok edilir: etiketler ve işaretler pencerede ve bellekte kalmaz."""
            for cocuk in self.yl_izgara.get_children():
                cocuk.destroy()
            self.yk_dugmeler = {}
            self.yk_durumlar = {}
            self.yk_liste_imza = None

        def _yoklama_secim_temizle(self):
            for kap in (self.yl_oneri_kutu, self.yl_yildizlar, self.yl_duzeyler, self.yl_subeler, self.yl_dersler):
                for cocuk in kap.get_children():
                    cocuk.destroy()
            self.yk_secim_imza = None

        def _yoklama_temizle(self):
            self._yoklama_liste_temizle()
            self._yoklama_secim_temizle()
            self.yk_oturum = None
            self.yk_duzey = self.yk_duzey_sube = None
            self.yk_adim, self.yk_kod, self.yk_pin, self.yk_usb = "kod", "", "", False
            self.yp_kod.set_text("")
            # Onay ve liste sayfasındaki etiketler (yok/geç yazılanların maskeli adları) de bellekte kalmaz.
            for etiket in (self.yo_ust, self.yo_baslik, self.yo_liste, self.yl_ust, self.yl_bilgi, self.yl_sube, self.yl_sayi):
                etiket.set_text("")
            self.yl_ders.set_label("")

        def _izgara_doldur(self, izgara, sutun, satir, dolu):
            """Homojen ızgaranın boş hücrelerine boş etiket koyar: satır/sütun sayısı sabit kalsın (boş satır
            sıfıra inmesin), az öğeli ızgarada düğmeler bütün alanı kaplamasın."""
            for sira in range(dolu, sutun * satir):
                izgara.attach(Gtk.Label(label=""), sira % sutun, sira // sutun, 1, 1)

        def _ogrenci_etiketi(self, kayit, durum):
            """Düğmenin durum yazısı ("YOK" / "GEÇ") ve rengi. Düğmenin içi kendi etiketlerimizdir (üstte numara +
            durum, altta ad): set_label çağrılmaz, hizalama ve kısaltma ayarı değişimlerde kaybolmaz."""
            kayit["durum"].set_text(DURUM_YAZISI.get(durum, ""))
            baglam = kayit["dugme"].get_style_context()
            for sinif in ("yok", "gec"):
                (baglam.add_class if durum == sinif else baglam.remove_class)(sinif)

        def _ogrenci_dugmesi(self, oge):
            ust_metin, alt_metin = ogrenci_dugme_satirlari(oge.get("etiket") or "")
            dugme = Gtk.Button()
            dugme.set_name("ogrenci")
            dugme.set_can_focus(False)
            dugme.set_size_request(-1, self._o(YOKLAMA_DOKUNMA_EN_AZ))  # geçici düğme: ölçek değişince yeniden kurulur
            ic = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            ic.set_valign(Gtk.Align.CENTER)
            ust = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            no = Gtk.Label(label=ust_metin)
            no.set_name("ogrenci-no")
            no.set_xalign(0)
            no.set_ellipsize(Pango.EllipsizeMode.END)
            durum = Gtk.Label(label="")
            durum.set_name("ogrenci-durum")
            durum.set_xalign(1)
            ust.pack_start(no, True, True, 0)
            ust.pack_end(durum, False, False, 0)
            ad = Gtk.Label(label=alt_metin)
            ad.set_name("ogrenci-ad")
            ad.set_xalign(0)
            ad.set_ellipsize(Pango.EllipsizeMode.END)  # güvenlik ağı: sunucu adı sütuna göre zaten kısaltır
            ic.pack_start(ust, False, False, 0)
            ic.pack_start(ad, False, False, 0)
            dugme.add(ic)
            kimlik = oge["id"]
            dugme.connect("clicked", lambda *_: self._ogrenci_dokunuldu(kimlik))
            return {"dugme": dugme, "no": no, "durum": durum, "ad": ad}

        def _yoklama_gorunum(self):
            y = self.durum.get("yoklama") if self.durum else None
            return y if isinstance(y, dict) else None

        def _ogrenci_dokunuldu(self, kimlik):
            """Dokunuş servisle AYNI saf işlevle (sonraki_durum) hemen çizilir; soket gidiş-dönüşü beklenmez.
            Servisin görünümü gelince düğmeler onunla eşitlenir."""
            kayit = self.yk_dugmeler.get(kimlik)
            if kayit is None:
                return
            yeni = sonraki_durum(self.yk_durumlar.get(kimlik, "var"), self.yk_gec_secilebilir)
            if yeni == "var":
                self.yk_durumlar.pop(kimlik, None)
            else:
                self.yk_durumlar[kimlik] = yeni
            self._ogrenci_etiketi(kayit, yeni)
            self.baglanti.gonder({"tur": "yoklama_isaret", "id": kimlik})
            yoklama = self._yoklama_gorunum()
            if yoklama is not None:  # yerel görünüm de güncel kalsın (saniye sayacı yeniden çizerse geri dönmesin)
                yoklama["yok"] = sorted(k for k, d in self.yk_durumlar.items() if d == "yok")
                yoklama["gec"] = sorted(k for k, d in self.yk_durumlar.items() if d == "gec")
                self._yoklama_alt_ciz(yoklama)

        def _yoklama_ana_dugme(self):
            yoklama = self._yoklama_gorunum() or {}
            _, tur = yoklama_ana_dugme(yoklama)
            self.baglanti.gonder({"tur": tur, "yon": 1} if tur == "yoklama_sayfa" else {"tur": tur})

        def _yoklama_izgara_kur(self, yoklama, imza):
            """Görünen sayfanın düğmeleri, sunucunun gönderdiği sırayla (okul no), soldan sağa satır satır."""
            for cocuk in self.yl_izgara.get_children():
                cocuk.destroy()
            self.yk_dugmeler = {}
            ogrenciler = yoklama.get("ogrenciler") or []
            bas, son = yoklama_sayfa_dilimi(len(ogrenciler), int(yoklama.get("sayfa") or 0))
            sutun, satir = yoklama_izgara_olcusu(len(ogrenciler), self.dikey)
            baglam = self.yl_izgara.get_style_context()
            yogunluk = yoklama_yogunluk(sutun, satir)
            for sinif in ("orta", "sik"):
                (baglam.add_class if sinif == yogunluk else baglam.remove_class)(sinif)
            for sira, oge in enumerate(ogrenciler[bas:son]):
                kayit = self._ogrenci_dugmesi(oge)
                self._ogrenci_etiketi(kayit, self.yk_durumlar.get(oge["id"], "var"))
                self.yl_izgara.attach(kayit["dugme"], sira % sutun, sira // sutun, 1, 1)
                self.yk_dugmeler[oge["id"]] = kayit
            self._izgara_doldur(self.yl_izgara, sutun, satir, son - bas)
            self.yl_izgara.show_all()  # yalnız ızgaranın içi (yığın sayfaları değil)
            self.yk_liste_imza = imza

        def _secim_dugmesi(self, metin, mesaj, sinif="", secili=False, duyarli=True, islev=None):
            boy = YOKLAMA_ONERI_BOY if "oneri" in sinif.split() else YOKLAMA_DOKUNMA_EN_AZ
            dugme = self._dugme(metin, islev or (lambda: self.baglanti.gonder(mesaj)), boy=boy, gecici=True)
            dugme.set_name("secim")
            baglam = dugme.get_style_context()
            for ad in sinif.split():
                baglam.add_class(ad)
            if secili:
                baglam.add_class("secili")
            dugme.set_sensitive(duyarli)
            etiket = dugme.get_child()
            if isinstance(etiket, Gtk.Label):
                etiket.set_justify(Gtk.Justification.CENTER)
                etiket.set_ellipsize(Pango.EllipsizeMode.END)
            return dugme

        def _duzey_sec(self, duzey):
            self.yk_duzey = duzey
            yoklama = self._yoklama_gorunum()
            if yoklama is not None:
                self._yoklama_secim_kur(yoklama)

        def _yoklama_secim_kur(self, yoklama):
            subeler = yoklama.get("subeler") or []
            dersler = yoklama.get("ders_saatleri") or []
            once = [s for s in yoklama.get("subeler_once") or [] if not subeler or s in subeler]
            adaylar = yoklama.get("ders_adaylari") or []
            simdiki, bitti = yoklama.get("simdiki_ders_no"), bool(yoklama.get("simdiki_bitti"))
            sube, ders_no, istek = yoklama.get("sube"), yoklama.get("ders_no"), bool(yoklama.get("istek"))
            # Gösterilen düzey: seçili şube değişince onun düzeyi; yoksa öne alınan ilk şubenin düzeyi.
            if sube != self.yk_duzey_sube:
                self.yk_duzey_sube = sube
                if sube:
                    self.yk_duzey = sube_duzeyi(sube)
            if self.yk_duzey is None and once:
                self.yk_duzey = sube_duzeyi(once[0])
            gosterilen, sutun, satir, duzeyler = sube_izgarasi(subeler, self.yk_duzey)
            if duzeyler and self.yk_duzey not in duzeyler:
                self.yk_duzey = duzeyler[0]
            imza = (yoklama.get("oturum"), sube, ders_no, istek, tuple(subeler), tuple(once), tuple(adaylar), simdiki, bitti,
                    yoklama.get("devre_adi"), self.yk_duzey, self.olcek, self.dikey,
                    tuple((d.get("ders_no"), d.get("secilebilir"), d.get("baslangic"), d.get("bitis")) for d in dersler))  # fmt: skip
            if imza == self.yk_secim_imza:
                return
            self._yoklama_secim_temizle()
            self.yk_secim_imza = imza

            # Üst satır: seçim tamamsa tek dokunuşla listeyi açan düğme; yanında öne alınan şubeler (yalnız ★ işareti).
            if sube and ders_no:
                metin = f"{sube_kisa(sube)} · {yoklama_ders_basligi(yoklama)}  →  Listeyi aç"
                self.yl_oneri_kutu.pack_start(self._secim_dugmesi(metin, {"tur": "yoklama_sec", "sube": sube}, "oneri",
                                                                  secili=True, duyarli=not istek), False, False, 0)  # fmt: skip
            for s in once:
                dugme = self._secim_dugmesi(f"★ {sube_kisa(s)}", {"tur": "yoklama_sec", "sube": s}, "oneri", secili=s == sube,
                                            duyarli=not istek)  # fmt: skip
                self.yl_yildizlar.pack_start(dugme, False, False, 0)
            for kap in (self.yl_oneri_kutu, self.yl_yildizlar):
                kap.show_all()
                kap.set_visible(bool(kap.get_children()))
            self.yl_once.set_visible(bool(sube and ders_no) or bool(once))

            self.yl_duzey_kutu.set_visible(bool(duzeyler))
            duzey_sutun = 1 if len(duzeyler) <= 6 else 2
            for sira, d in enumerate(duzeyler):
                dugme = self._secim_dugmesi(d, None, secili=d == self.yk_duzey, islev=lambda d=d: self._duzey_sec(d))
                self.yl_duzeyler.attach(dugme, sira % duzey_sutun, sira // duzey_sutun, 1, 1)
            self._izgara_doldur(self.yl_duzeyler, duzey_sutun, max(YOKLAMA_SUBE_SATIR_EN_AZ, -(-len(duzeyler) // duzey_sutun)),
                                len(duzeyler))  # fmt: skip
            self.yl_duzeyler.show_all()

            self.yl_sube_baslik.set_text(f"Şube · {self.yk_duzey}" if duzeyler else "Şube")
            for sira, s in enumerate(gosterilen):
                dugme = self._secim_dugmesi(s, {"tur": "yoklama_sec", "sube": s}, secili=s == sube, duyarli=not istek)
                self.yl_subeler.attach(dugme, sira % sutun, sira // sutun, 1, 1)
            self._izgara_doldur(self.yl_subeler, sutun, max(satir, -(-len(gosterilen) // sutun)), len(gosterilen))
            self.yl_subeler.show_all()

            # Ders saati sütunu: devre bilinmiyorsa (şube yok, saat yok) "Önce şubeyi seçin"; devresi bulunamayan
            # şubede saatsiz 1–12. Başlamamış ders soluk ve dokunulamaz. Hiçbir ders programa göre kapatılmaz.
            saatli = any(d.get("baslangic") for d in dersler)
            devre_belli = bool(sube) or saatli
            devre = yoklama.get("devre_adi") or ""
            self.yl_ders_baslik.set_text(f"Ders saati · {devre}" if devre and devre_belli else "Ders saati")
            d_sutun, d_satir = ders_izgarasi(len(dersler))
            for sira, d in enumerate(dersler if devre_belli else []):
                no = d.get("ders_no")
                sinif = "ders" + (" aday" if no in adaylar else " simdi" if no == simdiki else "")
                dugme = self._secim_dugmesi(ders_dugme_metni(d, simdiki, adaylar, bitti), {"tur": "yoklama_sec", "ders_no": no}, sinif,
                                            secili=no == ders_no, duyarli=bool(d.get("secilebilir")) and not istek)  # fmt: skip
                self.yl_dersler.attach(dugme, sira % d_sutun, sira // d_sutun, 1, 1)
            if devre_belli:
                self._izgara_doldur(self.yl_dersler, d_sutun, d_satir, len(dersler))
            self.yl_dersler.show_all()
            self.yl_dersler.set_visible(devre_belli)
            self.yl_ders_bos.set_visible(not devre_belli)

        def _yoklama_temizle_dokun(self):
            """[Temizle]: ilk dokunuş yalnız sorar; ikinci dokunuş (süresi içinde) bütün sayfalardaki işaretleri siler."""
            yoklama = self._yoklama_gorunum() or {}
            n = len(yoklama.get("yok") or []) + len(yoklama.get("gec") or [])
            if not n:
                return
            onay = self.yk_temizle_onay
            if onay is not None and time.monotonic() < onay[0] and onay[1] == n:
                self.yk_temizle_onay = None
                self.baglanti.gonder({"tur": "yoklama_temizle"})
            else:
                self.yk_temizle_onay = (time.monotonic() + YOKLAMA_TEMIZLE_ONAY_SN, n)
            self._yoklama_alt_ciz(yoklama)

        def _yoklama_alt_ciz(self, yoklama):
            """Alt çubuk: sayılar, sayfa gezgini, Temizle ve ana düğme (liste görünümünde)."""
            liste_yuklu = bool(yoklama.get("liste_yuklu"))
            ogrenciler = yoklama.get("ogrenciler") or []
            istek = bool(yoklama.get("istek"))
            yok, gec = len(yoklama.get("yok") or []), len(yoklama.get("gec") or [])
            sayfa_sayisi = int(yoklama.get("sayfa_sayisi") or 1)
            sayfa = int(yoklama.get("sayfa") or 0)
            dolu = liste_yuklu and bool(ogrenciler)
            self.yl_sayi.set_text(yoklama_sayi_metni(yok, gec, len(ogrenciler), bool(yoklama.get("gec_secilebilir"))) if dolu else "")
            cok_sayfa = dolu and sayfa_sayisi > 1
            for parca in (self.yl_geri, self.yl_ileri, self.yl_sayfa):
                parca.set_visible(cok_sayfa)
            self.yl_sayfa.set_text(f"Sayfa {sayfa + 1}/{sayfa_sayisi}" if cok_sayfa else "")
            self.yl_geri.set_sensitive(sayfa > 0 and not istek)
            self.yl_ileri.set_sensitive(sayfa < sayfa_sayisi - 1 and not istek)
            self.yl_temizle.set_visible(liste_yuklu)
            self.yl_temizle.set_sensitive(bool(yok or gec) and not istek)
            # Onay yalnız süresi içinde ve işaret sayısı değişmediyse geçerlidir (durum iletisi her saniye gelir).
            onay = self.yk_temizle_onay
            if onay is not None and (not liste_yuklu or time.monotonic() >= onay[0] or onay[1] != yok + gec):
                onay = self.yk_temizle_onay = None
            temizle_metni = yoklama_temizle_metni(yok + gec, onay is not None)
            if self.yl_temizle.get_label() != temizle_metni:
                self.yl_temizle.set_label(temizle_metni)
            self.yl_kaydet.set_visible(liste_yuklu)
            metin, _ = yoklama_ana_dugme(yoklama)
            if self.yl_kaydet.get_label() != metin:
                self.yl_kaydet.set_label(metin)
            self.yl_kaydet.set_sensitive(dolu and not istek)

        def _yoklama_liste_ciz(self, yoklama):
            istek = bool(yoklama.get("istek"))
            kalan = yoklama.get("kalan")
            self.yl_kalan.set_text(f"Kalan {sayac_metni(kalan)}" if kalan is not None else "")
            hata = yoklama.get("hata") or ("Süre dolmak üzere; kaydedin." if yoklama.get("uyari") else "")
            self.yl_hata.set_text(hata)
            self.yl_hata.set_visible(bool(hata))
            liste_yuklu = bool(yoklama.get("liste_yuklu"))
            ogretmen = (yoklama.get("ogretmen") or {}).get("etiket") or ""
            if liste_yuklu:
                ogrenciler = yoklama.get("ogrenciler") or []
                self.yk_gec_secilebilir = bool(yoklama.get("gec_secilebilir"))
                self.yk_durumlar = {k: "yok" for k in yoklama.get("yok") or []}
                self.yk_durumlar.update({k: "gec" for k in yoklama.get("gec") or [] if k not in self.yk_durumlar})
                # Izgara yalnız (oturum, şube, ders, sayfa, id listesi) değişince yeniden kurulur; ara durum
                # iletilerinde yalnız işaretler eşitlenir.
                imza = (yoklama.get("oturum"), yoklama.get("sube"), yoklama.get("ders_no"), int(yoklama.get("sayfa") or 0),
                        tuple(o.get("id") for o in ogrenciler), self.olcek, self.dikey)  # fmt: skip
                if imza != self.yk_liste_imza:
                    self._yoklama_izgara_kur(yoklama, imza)
                else:
                    for kimlik, kayit in self.yk_dugmeler.items():
                        self._ogrenci_etiketi(kayit, self.yk_durumlar.get(kimlik, "var"))
                self._yoklama_secim_temizle()
                self.yl_sube.set_text(yoklama.get("sube") or "")
                self.yl_ders.set_label(yoklama_ders_basligi(yoklama) + "  ▾")
                self.yl_ust.set_text(ogretmen)
                self.yl_bilgi.set_text(yoklama_liste_bilgisi(yoklama))
            else:
                self._yoklama_liste_temizle()
                self._yoklama_secim_kur(yoklama)
                self.yl_ust.set_text(" · ".join(p for p in ("Yoklama", ogretmen, yoklama.get("tarih_yazi") or "") if p))
                self.yl_bilgi.set_text(yoklama_secim_bilgisi(yoklama))
            self._yoklama_alt_ciz(yoklama)
            self.yl_bilgi.set_visible(bool(self.yl_bilgi.get_text()))
            self.yl_izgara.set_visible(liste_yuklu)
            self.yl_secim.set_visible(not liste_yuklu)
            for parca in (self.yl_ust_sol, self.yl_sube, self.yl_ders, self.yl_degistir):
                parca.set_visible(liste_yuklu)
            self.yl_ders.set_sensitive(not istek)
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
                # USB anahtar kipi (0.11.0): öğretmen kodu adımı yok, yalnız 6 haneli PIN.
                usb_kip = yoklama.get("pin_kipi") == "usb"
                if usb_kip != self.yk_usb:
                    self.yk_usb, self.yk_pin = usb_kip, ""
                    self.yk_adim = "pin" if usb_kip else "kod"
                # Başlık kısa kalır (52 px yazı dar sütunda iki satıra bölünmesin); sahip bilgi satırının başında.
                sahip = yoklama.get("usb_etiket") or ""
                self.yp_baslik.set_text("Yoklama · USB anahtar" if usb_kip else "Ders yoklaması")
                if usb_kip and sahip:
                    self.yp_bilgi.set_text(" · ".join(p for p in (sahip, bilgi) if p))
                self.yp_kodpin.set_visible(usb_kip)
                self.yp_kodpin.set_sensitive(not yoklama.get("istek"))
                self._yoklama_pin_yaz()
                self.yigin.set_visible_child_name("yoklama-pin")
            elif asama == "liste":
                self._yoklama_liste_ciz(yoklama)
                self.yigin.set_visible_child_name("yoklama-liste")
            else:  # onay | kaydediliyor
                yok, gec = set(yoklama.get("yok") or []), set(yoklama.get("gec") or [])
                ogrenciler = yoklama.get("ogrenciler") or []
                baslik, liste = yoklama_onay_metni(
                    [o["etiket"] for o in ogrenciler if o.get("id") in yok],
                    [o["etiket"] for o in ogrenciler if o.get("id") in gec and o.get("id") not in yok],
                    len(ogrenciler), int(yoklama.get("sayfa_sayisi") or 1), bool(yoklama.get("gec_secilebilir")),
                )  # fmt: skip
                self.yo_ust.set_text(yoklama_ust_metni(yoklama))
                self.yo_baslik.set_text(baslik)
                self.yo_liste.set_text(liste)
                self.yo_liste.set_visible(bool(liste))
                baglam = self.yo_liste.get_style_context()
                (baglam.add_class if len(yok) + len(gec) > 10 else baglam.remove_class)("uzun")
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
            if mesaj.get("tur") == "pencereleri_kapat":
                # Oturum temizliği (K7): pencere kapatma ayrı süreçte çalışır; sonuç yalnız sayılardır.
                kuru = bool(mesaj.get("kuru"))
                hedef_uid = mesaj.get("uid")

                def _kapat():
                    # İkinci güvence: istek başka oturumun kullanıcısı içinse hiçbir pencereye dokunulmaz.
                    if not isinstance(hedef_uid, int) or not hasattr(os, "getuid") or os.getuid() != hedef_uid:
                        sonuc = {"hata": "başka oturumun ekran yardımcısı"}
                    else:
                        sonuc = sistem.pencereleri_kapat(os.getpid(), kuru)
                    self.baglanti.gonder(dict(sonuc, tur="pencere_sonucu"))

                threading.Thread(target=_kapat, daemon=True).start()
            if mesaj.get("tur") == "dugme_sonuc" and self.yuzer is not None:
                self.yuzer.sonuc(mesaj)
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
                if not logo_olcusu(resim.get_width(), resim.get_height())[0]:
                    return
                # Özgün çözünürlük saklanır; bant için ekran ölçeğine göre _logo_resmi() küçültür.
                self.logo_pixbuf, self.logo_olcekli = resim, None
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
            resim = self._logo_resmi() if logo_var else None
            for logo_kutu, logo_resmi, okul_etiketi, sag_etiketi in self.bantlar:
                okul_etiketi.set_text(okul)
                sag_etiketi.set_text(sag)
                if resim is not None and logo_resmi.get_pixbuf() is not resim:
                    logo_resmi.set_from_pixbuf(resim)
                logo_kutu.set_visible(resim is not None)

        def _logo_resmi(self):
            """Bant logosu ekran ölçeğinde (1920x1080'de 96 px boy); ölçek değişene dek önbellekte."""
            if self.logo_olcekli and self.logo_olcekli[0] == self.olcek:
                return self.logo_olcekli[1]
            try:
                en, boy = logo_olcusu(self.logo_pixbuf.get_width(), self.logo_pixbuf.get_height(), self.olcek)
                resim = self.logo_pixbuf.scale_simple(en, boy, GdkPixbuf.InterpType.BILINEAR)
            except Exception as hata:
                print(f"Logo ölçeklenemedi: {hata}", file=sys.stderr)
                return None
            self.logo_olcekli = (self.olcek, resim)
            return resim

        def _koptu(self):
            if self.kopma_zamani is None:
                self.kopma_zamani = time.time()
            return False

        def _saniye(self):
            simdi = time.localtime()
            self.saat.set_text(time.strftime("%H:%M", simdi))
            self.tarih.set_text(f"{simdi.tm_mday} {AYLAR[simdi.tm_mon - 1]} {simdi.tm_year} {GUNLER[simdi.tm_wday]}")
            if self.durum and self.durum.get("kilitli"):
                self._kilit_program_ciz()
            # Servis 10 saniyedir yoksa pencere kapanır (kilit rehin tutmaz); masaüstündeyken de eski durum
            # silinir ki yüzer düğme gizlensin (servis yokken "Kilitle" sessizce hiçbir şey yapmasın).
            if self.kopma_zamani and time.time() - self.kopma_zamani > 10 and (self.gorunur or self.durum is not None):
                self.durum = None
                self._ciz()
            if self.durum and self.durum.get("kapatma"):
                self.durum["kapatma"]["kalan"] = max(0, self.durum["kapatma"]["kalan"] - 1)
                self.kapatma_sayac.set_text(str(self.durum["kapatma"]["kalan"]))
            elif self.durum and isinstance(self.durum.get("temizlik"), dict):
                self.durum["temizlik"]["kalan"] = max(0, int(self.durum["temizlik"].get("kalan") or 0) - 1)
                self.kapatma_sayac.set_text(str(self.durum["temizlik"]["kalan"]))
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
            if getattr(self, "usb_bildirim", None) is not None:
                self.usb_bildirim.saniye()
            if self.gozetmen_kod_acik and time.time() - self.gozetmen_dokunma > GOZETMEN_KOD_ZAMAN_ASIMI_SN:
                self._gozetmen_vazgec()
            if self.gorunur:
                # Pencere başka monitöre geçtiyse ölçü o monitörün boyutuna uyarlanır.
                self._ekran_denetle()
                self.pencere.present()
                self._tam_ekran()
                # Pencere ekrana yerleşmeden yapılan ilk deneme "not-viewable" ile
                # düşer; kilit sürdükçe klavye kilidi alınana kadar yeniden denenir.
                if self.kilit_modu and self.klavye_kilidi != "alındı":
                    self._klavye_kilitle()
            return True

        def _ciz(self):
            self._sayfayi_ciz()
            # Yüzer düğme yalnız tam ekran sayfa yokken (ana pencere gizliyken) görünür.
            if self.yuzer is not None:
                self.yuzer.guncelle(self.durum, self.gorunur)
            if self.usb_bildirim is not None:
                self.usb_bildirim.guncelle(self.durum, self.gorunur)

        def _sayfayi_ciz(self):
            durum = self.durum or {}
            duyuru = durum.get("duyuru")
            kapatma = durum.get("kapatma")
            # Eski servis "temizlik" alanını göndermez: uyarı yok sayılır.
            temizlik = durum.get("temizlik") if isinstance(durum.get("temizlik"), dict) else None
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
            # USB anahtar (0.11.0). Eski servis "usb" alanını göndermez: düğme ve satır gizli kalır.
            usb = durum.get("usb") if isinstance(durum.get("usb"), dict) else None
            usb_pin = usb.get("pin") if usb and isinstance(usb.get("pin"), dict) else None
            if usb_pin is None:
                self.usb_girilen = ""
            self._bantlari_ciz(durum)
            # Öncelik (ortak sözlük §5.5; K7 temizlik uyarısı kapatmanın hemen altında): acil > kapatma > temizlik > gozetmen-* > yoklama-* > duyuru > sinav-giris/sinav > kilit > gizli.
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
                self.kapatma_kipi = "kapatma"
                self.kapatma_baslik.set_text("Bu tahta kapatılacak")
                self.kapatma_sayac.set_text(str(kapatma.get("kalan", 0)))
                self.kapatma_neden.set_text(
                    (kapatma.get("neden") or "Otomatik kapatma")
                    + "\nTahtayı kullanıyorsanız Vazgeç düğmesine dokunun; yoksa süre sonunda kapanır."
                )
                self.yigin.set_visible_child_name("kapatma")
                self._goster(kilit=False)
            elif temizlik:
                # Oturum temizliği uyarısı (K7): kapatma uyarısıyla aynı sayfa ve dil.
                self.kapatma_kipi = "temizlik"
                self.kapatma_baslik.set_text("Açık pencereler kapatılacak")
                self.kapatma_sayac.set_text(str(temizlik.get("kalan", 0)))
                self.kapatma_neden.set_text(TEMIZLIK_UYARI_METNI)
                self.yigin.set_visible_child_name("kapatma")
                self._goster(kilit=False)
            elif gozetmen_sayfasi:
                self._gozetmen_ciz(sinav, gozetmen)
            elif yoklama:
                # Öğretmenin başlattığı kısa etkileşim: duyuru serviste bekler, yoklama kapanınca görünür.
                # Klavye kilidi yalnız tahta kilitliyse (yoklama kilidi açmaz).
                self._yoklama_ciz(yoklama)
                self._goster(kilit=bool(durum.get("kilitli")))
            elif usb_pin is not None and durum.get("kilitli"):
                # USB anahtarla kilit açma PIN'i (0.11.0): yoklama-* ile aynı basamak; tahta kilitli kalır.
                self.up_sahip.set_text(usb_anahtar.sahip_metni(usb))
                hata = yoklama_pin_hatasi(usb_pin)
                self.up_hata.set_text(hata)
                self.up_hata.set_visible(bool(hata))
                self.up_tuslar.set_sensitive(not usb_pin.get("istek") and not int(usb_pin.get("bekleme") or 0))
                self.up_kod.set_text("●" * len(self.usb_girilen) + "○" * (YOKLAMA_PIN_HANE - len(self.usb_girilen)))
                self.yigin.set_visible_child_name("usb-pin")
                self._goster(kilit=True)
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
                elif usb and usb.get("kilit_ac"):
                    self.bilgi.set_text("Kilidi USB anahtarla açabilirsiniz.")
                else:
                    self.bilgi.set_text("Kilit okul idaresince açılır.")
                program = program_bilgisi(durum)
                # Uzun neden ("Bu saatte bu derslikte ders yok") saatin ortasından bölünmesin: iki satır.
                self.program_bilgi.set_text(program.replace(" · ", "\n", 1) if len(program) > 40 else program)
                self.program_bilgi.set_visible(bool(program))
                self._kilit_program_ciz()
                self.kod_kutusu.set_visible(kod_var and not bekleme and not cevrimdisi)
                self.cevrimdisi_dugmesi.set_visible(cevrimdisi)
                usb_metin = (usb or {}).get("metin") or ""
                self.kilit_usb_bilgi.set_text(usb_metin)
                self.kilit_usb_bilgi.set_visible(bool(usb_metin))
                usb_ac = bool(usb and usb.get("kilit_ac")) and not cevrimdisi
                self.kilit_usb_dugmesi.set_visible(usb_ac)
                self.kilit_sag.set_visible(usb_ac or (kod_var and not bekleme and not cevrimdisi)
                                           or self.kilit_program_kutu.get_visible())
                self.kilit_yoklama.set_visible(bool(durum.get("yoklama_etkin")) and not cevrimdisi)
                self.yigin.set_visible_child_name("kilit")
                self._goster(kilit=True)
            else:
                self._gizle()

        def _goster(self, kilit: bool):
            # Tam ekran görünmeden önce yüzer düğme ve menü gizlenir.
            if self.yuzer is not None:
                self.yuzer.gizle()
            ilk = not self.gorunur
            self.gorunur = True
            self._ekran_denetle()
            self._tam_ekran()  # show()'dan önce: pencere ölçeğin hesaplandığı monitörde açılır
            self.pencere.show()
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

    class UsbBildirimi:
        """Köşedeki USB anahtar bildirimi: odak çalmayan (override-redirect) küçük pencere, klavye almaz.

        "USB anahtar tanındı · A. Yılmaz (kod 112)" [Yoklama al] [Kapat]; 10 sn sonra ya da Kapat ile kapanır;
        tahta kilitlenince, tam ekran sayfa ya da yoklama açılınca hemen kapanır. Yeni bildirim numarası
        gelmedikçe yeniden açılmaz. Ölçüler 1920x1080 içindir ve ekran ölçeğiyle büyür/küçülür.
        """

        def __init__(self, ekran):
            self.ekran = ekran
            self.gosterilen_no = 0
            self.bitis = 0.0
            self.acik = False
            self.olcek = None
            gdk_ekran = Gdk.Screen.get_default()
            self.olcu = Gtk.CssProvider()
            self.olcu.load_from_data(USB_BILDIRIM_STIL)
            renk = Gtk.CssProvider()
            renk.load_from_data(USB_BILDIRIM_RENK)
            for saglayici in (self.olcu, renk):
                Gtk.StyleContext.add_provider_for_screen(gdk_ekran, saglayici, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
            self.pencere = Gtk.Window(type=Gtk.WindowType.POPUP)
            self.pencere.set_name("ub-pencere")
            self.pencere.set_accept_focus(False)
            self.pencere.set_focus_on_map(False)
            self.pencere.set_skip_taskbar_hint(True)
            self.pencere.set_skip_pager_hint(True)
            self.pencere.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
            self.kutu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.kutu.set_name("ub-kutu")
            self.metin = Gtk.Label(label="")
            self.metin.set_line_wrap(True)
            self.metin.set_xalign(0)
            self.metin.set_max_width_chars(36)
            self.dugmeler = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            self.dugmeler.set_halign(Gtk.Align.END)
            self.yoklama = Gtk.Button(label="Yoklama al")
            self.yoklama.set_name("ub-yoklama")
            self.kapat = Gtk.Button(label="Kapat")
            for dugme in (self.yoklama, self.kapat):
                dugme.set_can_focus(False)
                dugme.set_focus_on_click(False)
            self.yoklama.connect("clicked", lambda *_: self._yoklama())
            self.kapat.connect("clicked", lambda *_: self._kapat())
            self.dugmeler.pack_start(self.yoklama, False, False, 0)
            self.dugmeler.pack_start(self.kapat, False, False, 0)
            self.kutu.pack_start(self.metin, False, False, 0)
            self.kutu.pack_start(self.dugmeler, False, False, 0)
            self.pencere.add(self.kutu)
            self._olcek_uygula()

        def _alan(self):
            gosterge = Gdk.Display.get_default()
            monitor = gosterge.get_primary_monitor() or gosterge.get_monitor(0)
            alan, geo = monitor.get_workarea(), monitor.get_geometry()
            return (alan.x, alan.y, alan.width, alan.height), (geo.width, geo.height)

        def _olcek_uygula(self):
            try:
                alan, (en, boy) = self._alan()
            except Exception:
                alan, (en, boy) = (0, 0, 1920, 1080), (1920, 1080)
            olcek = ekran_olcegi(en, boy)
            if olcek != self.olcek:
                self.olcek = olcek
                self.olcu.load_from_data(olcekli_stil(USB_BILDIRIM_STIL, olcek))
                self.kutu.set_spacing(olcekle(16, olcek))
                self.dugmeler.set_spacing(olcekle(16, olcek))
            return alan

        def _yerlestir(self):
            alan = self._olcek_uygula()
            _, dogal = self.pencere.get_preferred_size()
            yuzer = None
            y_ = getattr(self.ekran, "yuzer", None)
            if y_ is not None and getattr(y_, "istenen", False):
                try:
                    dx, dy = y_.pencere.get_position()
                    yuzer = (dx, dy, int(y_.cap))
                except Exception:
                    yuzer = None
            x, y = usb_bildirim_konumu(alan, dogal.width, dogal.height, olcekle(USB_BILDIRIM_BOSLUK, self.olcek), yuzer)
            self.pencere.move(x, y)

        def guncelle(self, durum, ana_gorunur):
            usb = (durum or {}).get("usb")
            if not usb_bildirim_gosterilir(usb, ana_gorunur, bool((durum or {}).get("kilitli"))):
                if isinstance(usb, dict) and (ana_gorunur or (durum or {}).get("kilitli")):
                    # Tam ekran sayfa ya da kilit açıktı: bu numaralı bildirim tüketildi, sonra yeniden açılmaz.
                    self.gosterilen_no, self.bitis = int(usb.get("bildirim_no") or 0), 0.0
                self.gizle()
                return
            no = int(usb.get("bildirim_no") or 0)
            if no != self.gosterilen_no:
                self.gosterilen_no, self.bitis = no, time.monotonic() + USB_BILDIRIM_SN
            if time.monotonic() >= self.bitis:
                self.gizle()
                return
            self.metin.set_text(str(usb.get("metin") or ""))
            self.yoklama.set_visible(usb_bildirim_yoklama_dugmesi(usb))
            if not self.acik:
                self.kutu.show_all()
                self.yoklama.set_visible(usb_bildirim_yoklama_dugmesi(usb))
                self.pencere.show()
                self.acik = True
            self.pencere.resize(1, 1)
            self._yerlestir()

        def saniye(self):
            if self.acik and time.monotonic() >= self.bitis:
                self.gizle()

        def gizle(self):
            if self.acik:
                self.pencere.hide()
            self.acik = False

        def _yoklama(self):
            self.bitis = 0.0
            self.gizle()
            self.ekran.baglanti.gonder({"tur": "yoklama_ac"})

        def _kapat(self):
            self.bitis = 0.0
            self.gizle()
            self.ekran.baglanti.gonder({"tur": "usb_bildirim_kapat", "bildirim_no": self.gosterilen_no})

    Ekran()
    Gtk.main()
    return 0
