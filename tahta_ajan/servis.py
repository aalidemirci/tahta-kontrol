"""Ajan servisi: sunucuyla konuşur, komutları uygular, ekran yardımcılarını besler.

Yönetici (root) yetkisiyle sistem servisi olarak çalışır. Ekrandaki pencereyi
kendisi çizmez; her oturumda başlayan ekran yardımcısı (ekran.py) yerel bir
sokete bağlanır ve ne göstereceğini buradan öğrenir. Sır (tahta anahtarı,
kilit kodu özeti) ekran yardımcısına hiç gitmez.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import select
import socket
import socketserver
import threading
import time
import unicodedata
from collections import deque
from urllib.parse import urlsplit

from . import __version__, ayar, envanter, gun_programi, sistem, tani, usb_anahtar
from .baglanti import BaglantiHatasi, Istemci

gunluk = logging.getLogger("tahta-ajan")

KOD_DENEME_SINIRI = 5
RAKAMLAR = "0123456789"  # str.isdigit() "²" gibi karakterleri de kabul eder
KOD_BEKLEME_SN = 60
LOGO_YENIDEN_DENEME_SN = 60
# Sunucunun bu ajana uygulayabileceği yetenekler (sürüm karşılaştırması yerine).
YETENEKLER = [
    "acil", "duyuru_id", "program_kilidi", "sinav", "yoklama", "adres_listesi", "envanter", "ariza", "temizlik",
    "dugme", "acilis_kilidi", "usb_anahtar", "gun_programi",
]  # fmt: skip
# Yüzer düğme (0.9.0, G3). Ayar sunucudan (`ayar.dugme`) gelir ve durum.json'da saklanır (sır değil): sunucu
# kapalıyken servis yeniden başlasa da düğme görünür ve tahtadan kilitlenebilir. Ekrandan gelen her işlem
# burada ayara göre yeniden doğrulanır (yerel soketi herhangi bir yerel süreç açabilir).
DUGME_ISLEMLERI = ("kilitle", "kapat", "yeniden_baslat", "ariza", "yoklama")
# Olay metinleri sunucudaki tahta_sunucu/dugme.py OLAY_* ile aynıdır (ajan sunucu paketini içe aktarmaz).
DUGME_OLAYLARI = {
    "kilitle": "Tahtadan kilitlendi",
    "kapat": "Tahtadan kapatıldı",
    "yeniden_baslat": "Tahtadan yeniden başlatıldı",
}
DUGME_GUC_GECIKME_SN = 3  # olay sunucuya gitsin diye kapatma/yeniden başlatma bu kadar sonra uygulanır
ILETI_DUGME_AYAR = "Bu işlem tahtadan yapılamıyor (okul ayarı)."
ILETI_DUGME_KOD_YOK = "Kilit kodu belirlenmemiş; tahta yalnız panelden kilitlenir."
ILETI_DUGME_SINAV = "Sınav sürüyor; işlem yapılamaz."
ILETI_DUGME_ACIL = "Acil yayın sürüyor; işlem yapılamaz."
ILETI_DUGME_KILITLI = "Tahta kilitliyken bu işlem yapılamaz."
ILETI_DUGME_YETKI = "Bu istek ekrandaki oturumdan gelmedi; işlem yapılmadı."
# Oturum temizliği (K7, 0.8.0): kullanılan tahtada uyarı süresi ve ekran yardımcısının pencere yanıtı.
TEMIZLIK_UYARI_SN = 60
TEMIZLIK_PENCERE_BEKLEME_SN = 15
ACIL_TURLERI = {"acil": "acil durum", "tatbikat": "tatbikat"}
ACIL_EN_UZUN_SN = 7200  # sunucu ne derse desin acil yayın tahtada en çok 2 saat kalır (kural 3)
# Program kilidi (teneffüs / boş ders saati) tahtada SÜRELİ tutulur ve süresi tahtanın kendi
# monotonic saatiyle sayılır: sunucu çökse de derse girilecek saatte tahta kendiliğinden açılır.
PROGRAM_KILIDI_EN_UZUN_SN = 8 * 3600
PROGRAM_NEDENLERI = ("Teneffüs", "Öğle arası", "Bu saatte bu derslikte ders yok")
# Sınav kipi (Aşama 4). Sınav ekranı tahtada en çok bu kadar kalır (sunucu ne derse desin; kural 3):
# en uzun ders 300 dk + 120 dk uzatma + 10 dk giriş penceresi 7 saati geçmez.
SINAV_EN_UZUN_SN = 8 * 3600
SINAV_LISTE_SINIRI = 60  # tahtaya en çok 60 kişilik maskeli liste iner (sunucuyla aynı)
GOZETMEN_OTURUM_EN_UZUN_SN = 900  # gözetmen belirteci (sunucu 15 dk verir)
GOZETMEN_KOD_UZUNLUK = 6
GOZETMEN_BILDIRIM_SN = 5  # "Yoklama kaydedildi: n öğrenci gelmedi" ekranda kalma süresi
# Ders yoklaması (Aşama 5). Öğrenci listesi ve yoklama belirteci YALNIZ bu süreçte, bellekte durur:
# durum.json'a, günlüğe, tanılama raporuna yazılmaz; belirteç ekran yardımcısına hiç gitmez (kural 5).
YOKLAMA_OTURUM_EN_UZUN_SN = 15 * 60  # sunucu en çok 15 dk verir (ayar 3–15 dk)
YOKLAMA_BOSTA_VARSAYILAN_SN = 180
YOKLAMA_PIN_BOSTA_SN = 90  # PIN sayfası (liste yok) dokunulmazsa kapanır
YOKLAMA_UYARI_SN = 60  # süre bitimine bu kadar kala "Süre dolmak üzere; kaydedin."
YOKLAMA_ILETI_SN = 5
YOKLAMA_KAYDEDILDI_SN = 3
YOKLAMA_ISTEK_SN = 10  # ağ isteklerinin zaman aşımı (uzun bekleme döngüsünü durdurmaz)
YOKLAMA_LISTE_SINIRI = 300
YOKLAMA_DERS_NO_EN_COK = 20
# K5: tahtadaki yoklama kâğıdın yanında yardımcı kayıttır; sunucu yoksa asıl dayanak kâğıt yoklamadır.
ILETI_YOKLAMA_SUNUCU_YOK = "Sunucuya ulaşılamıyor. Bu dersin yoklamasını kâğıda alın."
ILETI_YOKLAMA_SINAV = "Sınav sürüyor; ders yoklaması açılamaz."
ILETI_YOKLAMA_ACIL = "Acil yayın sürüyor; ders yoklaması açılamaz."
ILETI_YOKLAMA_KAPALI = "Ders yoklaması bu okulda etkin değil."
ILETI_YOKLAMA_DESTEK_YOK = "Sunucu ders yoklamasını desteklemiyor; okul idaresine bildirin."
# Altyapı (A6). Adres listesi: aynı adrese art arda bu kadar BAĞLANTI hatası (parmak izi hatası dahil;
# HTTP 401/403/5xx dahil değil) olunca sıradaki adres denenir.
ADRES_HATA_ESIGI = 3
ENVANTER_YENILEME_SN = 6 * 3600  # donanım okumaları (dpkg-query dahil) en çok bu sıklıkta yenilenir
ENVANTER_YENIDEN_SN = 3600  # sunucu aynı özeti hâlâ istiyorsa en erken bu kadar sonra yeniden gönderilir
# Arıza bildirimi: tahtadan bildirilebilen türler ("acilis" yalnız panelden), kuyruk ve hız sınırları.
ARIZA_KATEGORILERI = ("dokunmatik", "goruntu", "ses", "kalem", "ag", "yazilim", "fiziksel", "diger")
ARIZA_KUYRUK_EN_COK = 10
ARIZA_SAATLIK_EN_COK = 3
ARIZA_OMUR_SN = 7 * 86400
ARIZA_ACIKLAMA_EN_UZUN = 300
ARIZA_ONAY_BEKLEME_SN = 5  # pencere "iletildi" demeden önce sunucunun ariza_alindi yanıtını bu kadar bekler
ILETI_ARIZA_ILETILDI = "Arıza kaydı iletildi."
ILETI_ARIZA_BEKLIYOR = "Kayıt tahtada bekletiliyor; sunucuya ulaşınca iletilecek."
ILETI_ARIZA_KAYITSIZ = "Bu tahta henüz sunucuya kayıtlı değil."
ILETI_ARIZA_KATEGORI = "Geçersiz kategori."
ILETI_ARIZA_SINIR = "Bu tahtadan son bir saatte çok bildirim yapıldı; idareye başvurun."
ILETI_ARIZA_KUYRUK = "Bekleyen bildirim çok; sunucuya ulaşılınca yeniden deneyin."
# USB anahtar (0.11.0): "çıkarıldı" iletisi ekranda bu kadar kalır; kilit açma PIN sayfası dokunulmazsa kapanır.
USB_CIKARILDI_SN = 4
USB_ILETI_SN = 8
USB_PIN_BOSTA_SN = 90
# Ekran sayılmayan yerel bağlantılar: kitaplığı olmayan yardımcı ("yok") ve kısa ömürlü komut istemcisi.
GORUNMEZ_ARAYUZ = (None, "yok", "komut")


class Servis:
    def __init__(self):
        self.kilit = threading.RLock()
        self.dur = threading.Event()
        kayitli = ayar.durum_oku()
        self.kilitli = bool(kayitli.get("kilitli", False))
        # Kilidin kaynağı: "idare" (panelden, süresiz) ya da "program" (süreli). Kaynaksız eski
        # kayıt idare kilidi sayılır. Program kilidi yeniden başlatmada GERİ YÜKLENMEZ: monotonic
        # saat sıfırlandığı için süresi bilinmez; tahta açık kalır (kural 3).
        self.kilit_kaynak = None
        self.kilit_bitis = None  # time.monotonic() zamanı; yalnız program kilidinde
        self.kilit_neden = ""
        self.kilit_acilis = ""
        if self.kilitli:
            if kayitli.get("kilit_kaynak") == "program":
                self.kilitli = False
            else:
                self.kilit_kaynak = "idare"
        self.duyuru = None  # {"id","baslik","metin","bitis","kapatilabilir"}; id = sunucudaki duyuru_id ya da None
        self.kapatma = None  # {"bitis","neden"}: uyarılı kapatma geri sayımı
        # Oturum temizliği (K7): geri sayım {"komut_id","bitis"}; sürerken True; ekran yardımcısının
        # pencere yanıtı için olay. Komutun sonucu temizlik bitince (ertelenmiş) sonuçlara eklenir.
        self.temizlik = None
        self._temizlik_suruyor = False
        self._pencere_olayi = None
        self._pencere_sonucu = None
        # Acil yayın: sunucunun her yanıtta verdiği DURUM (ayar.acil). Yalnız bellekte tutulur;
        # ajan yeniden başlarsa ilk turda sunucudan yeniden alır. Sır değildir.
        self.acil = None  # {"id","tur","baslik","metin","bitis"}
        # Sınav kipi (Aşama 4): sunucunun her yanıtta verdiği DURUM (ayar.sinav). Yalnız bellekte;
        # durum.json'a ve günlüğe YAZILMAZ (maskeli liste kişisel veridir; sunucu her bağlantıda
        # yeniden gönderir). Süreler tahtanın monotonic saatiyle sayılır: sunucuya ulaşılamasa da
        # sınav ekranı süresinde kalkar (kural 3).
        self.sinav = None  # _sinav_coz() çıktısı + basla_mono, bitis_mono
        self.sinav_yerel_kapali = None  # çevrimdışı düğmesiyle tahtadan kapatılan sınavın kimliği
        # Gözetmen oturumu: belirteç YALNIZ burada durur, ekran yardımcısına gitmez (kural 5).
        self.gozetmen = None  # {"durum","belirtec","bitis_mono","oturum","liste","liste_fazla","gelmeyen",...}
        self.gozetmen_hata = ""
        self.gozetmen_bekleme_bitis = 0.0  # time.monotonic(); sunucunun 429 bekleme süresi
        self.gozetmen_bildirim = None  # (metin, bitis_mono)
        self._gozetmen_oturum_no = 0
        self._sinav_evre_son = None
        # Ders yoklaması (A5): None ya da _yoklama_yeni() sözlüğü. Belirteç sözlükte DEĞİL, ayrı alanda
        # durur; gorunum() sözlüğü kopyalarken belirteci yanlışlıkla taşıyamaz.
        self.yoklama = None
        self._yoklama_belirtec = None
        self._yoklama_oturum_no = 0
        # Sunucunun durum tabanlı `ayar.yoklama_etkin` bayrağı; None = sunucu bildirmedi (eski sunucu).
        self.yoklama_etkin = None
        # Yalnız bellekte: günlük program disk/günlük/tanılamaya yazılmaz.
        self.gun_programi = None
        self.gun_programi_bitis = 0.0
        # USB anahtar (0.11.0): sunucunun durum tabanlı `ayar.usb_anahtar.etkin` bayrağı (None = bildirmedi:
        # eski sunucu → izleme kapalı). Gizli değer YALNIZ `_usb_gizli`de, tanındıktan sonra en çok
        # TANI_OMRU_SN durur; görünüme, durum dosyasına, günlüğe, tanılamaya ve sunucuya giden duruma girmez.
        # Bağlama yolu da yalnız bu bellekte, okunurken kullanılır (kişisel hesap adı taşıyabilir).
        self.usb_etkin = None
        self.usb = _usb_bos()
        self._usb_gizli = None  # (kimlik, gizli)
        self._usb_baglama = None  # anahtarın okunduğu bağlamanın mountinfo kimliği
        self._usb_gorulen: set[int] = set()  # bir kez okunmuş bağlamalar (çıkarılıp takılan yeni kimlik alır)
        self._usb_izleme = None  # {"dur": Event} — izleme iş parçacığı yalnız özellik açıkken çalışır
        self._usb_izleme_durumu = "kapali"  # "kapali" | "izleniyor" | "desteklenmiyor"
        self._usb_pin = None  # kilit açma PIN sayfası: {"hata","istek","bekleme_bitis","son_dokunma"}
        self._usb_kilit_suruyor = False
        self._usb_istek_no = 0  # tanıma isteğinin sırası: geç gelen eski yanıt yeni durumu ezmesin
        self._usb_bildirim_no = 0
        self._usb_bildirim_kapali = 0
        self._usb_tani = {"takili": 0, "elenen": {}, "son_okuma": "", "son_dogrulama": "yok"}
        self.usb_izleyici_kur = sistem.baglama_izleyici  # testler değiştirir
        # Ağ isteği atan işler ayrı iş parçacığında çalışır (ekran beklemez); testler eşzamanlı yapar.
        self.arka_plan = lambda is_: threading.Thread(target=is_, daemon=True).start()
        self.zamanla = lambda sn, is_: threading.Timer(sn, is_).start()
        # Yüzer düğme ayarı: None = sunucu hiç bildirmedi (eski sunucu) → düğme yok.
        self.dugme = _dugme_coz(kayitli.get("dugme"))
        # Açılışta kilit (0.9.0): oturumun kimliği ve başlangıcı (açılıştan saniye). Kararı SUNUCU verir:
        # yeni oturum_no görünce ve oturum genç ise "kilitle" komutu iner; sunucuya ulaşılamazsa tahta açık
        # kalır (kural 3). Hesap adı değil, rastgele kimlik. Aynı açılışta servis yeniden başlarsa korunur.
        self.acilis = sistem.acilis_kimligi()
        self.oturum = _oturum_coz(kayitli.get("oturum"), self.acilis)
        self.okul_adi = kayitli.get("okul_adi", "")
        self.kilit_kodu = kayitli.get("kilit_kodu")  # {"tuz","ozet","tur"} ya da None
        # Açılışta sunucuya ulaşmak için süre tanınır; yoksa kilit ilk saniyede kodsuz açılabilirdi.
        self.son_temas = time.time()
        self.sunucu_saat = None
        self.sonuclar: list[dict] = []
        self.olaylar: list[str] = []
        self.ekranlar: dict[int, dict] = {}  # istemci no -> {"gonder": işlev, "bilgi": {...}}
        self._ekran_no = 0
        self.hatali_deneme = 0
        self.bekleme_bitis = 0.0
        self._son_cevrimdisi = None
        self.yapi = {}
        self.istemci = None
        # ---- altyapı (A6) ----
        # Arıza kuyruğu durum.json'da (root, 0600) en çok 7 gün bekler; tahtada hiçbir arıza metni gösterilmez.
        self.ariza_kuyrugu = _ariza_kuyrugu_coz(kayitli.get("ariza_kuyrugu"))
        self._ariza_zamanlari: deque = deque()  # kabul edilen bildirimlerin time.monotonic() zamanları
        self._ariza_olaylari: dict[str, threading.Event] = {}  # yerel_id → sunucu aldı olayı
        self.onay_bekliyor = False  # sunucu "bekliyor" dedi (onaylanmamış tahta arıza bildiremez)
        # Adres listesi: etkin adres (bağlanılan) ve ardışık bağlantı hatası sayısı. Bellekte.
        self._etkin_adres = None
        self._birincil_son = None
        self._adres_hata = 0
        self._gecikme = 2
        # Envanter: ham donanım okumaları önbellekte; gönderim yalnız sunucu isteyince (envanter_iste).
        self._donanim = None
        self._donanim_zamani = 0.0
        self._donanim_kilidi = threading.Lock()
        self._envanter_iste = False
        # Aynı özet hemen ikinci kez gönderilmez (sunucu reddetse de döngü olmasın); sunucu aynı özeti
        # ENVANTER_YENIDEN_SN sonra hâlâ istiyorsa (ör. yedekten geri yüklendi, envanter kayboldu) yeniden gider.
        self._envanter_gonderilen = None
        self._envanter_gonderim_zamani = 0.0
        # Okul kimliği: sunucunun hesapladığı tahta paleti, logo ve tahtanın adı/dersliği.
        # Logo yalnız bu serviste (root) durur; ekran yardımcısına soketle gider.
        self.tema = ayar.palet_dogrula(kayitli.get("tema"))
        tahta = kayitli.get("tahta") if isinstance(kayitli.get("tahta"), dict) else {}
        self.tahta_bilgi = {"ad": _kisa(tahta.get("ad")), "derslik": _kisa(tahta.get("derslik"))}
        self.logo, self.logo_sha = None, None
        sha = kayitli.get("logo_sha256")
        veri = ayar.logo_oku() if _sha_gecerli(sha) else None
        if veri and ayar.logo_gecerli(veri) and hashlib.sha256(veri).hexdigest() == sha:
            self.logo, self.logo_sha = veri, sha
        # Son başarısız denemenin time.monotonic() zamanı; None = bekleme yok. Duvar saati değil:
        # tahta saati geri alınırsa (bozuk RTC, NTP düzeltmesi) logo uzun süre indirilmez olurdu.
        self._logo_son_deneme = None

    # ---- durum -----------------------------------------------------------
    def cevrimdisi(self) -> bool:
        return (time.time() - self.son_temas) > ayar.CEVRIMDISI_SN

    def kayitli(self) -> bool:
        return bool(self.yapi.get("tahta_id"))

    def _kaydet(self):
        ayar.durum_yaz(
            {
                "kilitli": self.kilitli,
                "kilit_kaynak": self.kilit_kaynak if self.kilitli else None,
                "okul_adi": self.okul_adi,
                "kilit_kodu": self.kilit_kodu,
                "tema": self.tema,
                "logo_sha256": self.logo_sha,
                "tahta": self.tahta_bilgi,
                "ariza_kuyrugu": self.ariza_kuyrugu,
                "dugme": self.dugme,
                "oturum": dict(self.oturum, acilis=self.acilis) if self.oturum else None,
            }
        )

    def _kilit_birak(self):
        """Kilidi ve kaynak bilgisini temizler (çağıran self.kilit'i tutar)."""
        self.kilitli = False
        self.kilit_kaynak = None
        self.kilit_bitis = None
        self.kilit_neden = ""
        self.kilit_acilis = ""

    def _program_kilidi(self) -> bool:
        return self.kilitli and self.kilit_kaynak == "program"

    def kilit_kalan(self) -> int | None:
        """Program kilidinin kalan saniyesi; program kilidi yoksa None."""
        with self.kilit:
            if not self._program_kilidi() or self.kilit_bitis is None:
                return None
            return max(0, int(self.kilit_bitis - time.monotonic()))

    # ---- sınav kipi ---------------------------------------------------------
    def _sinav_aktif(self) -> dict | None:
        """Ekranda olması gereken sınav (çağıran self.kilit'i tutar): süresi dolmamış ve tahtadan
        kapatılmamış. Değilse None."""
        s = self.sinav
        if s is None or s["kimlik"] == self.sinav_yerel_kapali or time.monotonic() >= s["bitis_mono"]:
            return None
        return s

    def sinav_ekrani_acik(self) -> bool:
        with self.kilit:
            return self._sinav_aktif() is not None

    def _gozetmen_kapat(self):
        """Gözetmen oturumunu kapatır; belirteç, liste ve işaretler bellekten atılır (çağıran kilidi tutar)."""
        self.gozetmen = None

    def _sinav_durumu(self) -> dict | None:
        """Sunucuya giden `durum.sinav`: yalnız kimlik ve evre bayrakları (ad, liste, kod YOK)."""
        with self.kilit:
            s = self.sinav
            if s is None or time.monotonic() >= s["bitis_mono"]:
                return None
            yerel_kapali = s["kimlik"] == self.sinav_yerel_kapali
            if self.gozetmen is not None and not yerel_kapali:
                evre = "yoklama"
            else:
                evre = "giris" if time.monotonic() < s["basla_mono"] else "suruyor"
            return {"kimlik": s["kimlik"], "evre": evre, "yerel_kapali": yerel_kapali}

    def sinav_tani_metni(self) -> str:
        """Tanılama satırı "Sınav kipi": yok / giris / suruyor (kimlikle). Liste, ad, kod girmez."""
        durum = self._sinav_durumu()
        if not durum:
            return "yok"
        ek = " · tahtadan kapatıldı" if durum["yerel_kapali"] else ""
        return f"{durum['evre']} ({durum['kimlik']}){ek}"

    def _sinav_gorunumu(self) -> dict | None:
        """Ekran yardımcısına giden sınav görünümü (çağıran kilidi tutar). Belirteç GİRMEZ.

        Liste yalnız giriş evresinde ya da gözetmen yoklama ızgarası açıkken doludur (M3).
        """
        s = self._sinav_aktif()
        if s is None:
            return None
        simdi = time.monotonic()
        giris = simdi < s["basla_mono"]
        g = self.gozetmen
        izgara = bool(g) and g["durum"] in ("yoklama", "kaydediliyor")
        bildirim = self.gozetmen_bildirim
        return {
            "kimlik": s["kimlik"],
            "evre": "giris" if giris else "suruyor",
            "sinav_adi": s["sinav_adi"],
            "salon_adi": s["salon_adi"],
            "baslangic_saat": s["baslangic_saat"],
            "bitis_saat": s["bitis_saat"],
            "dersler": [dict(d) for d in s["dersler"]],
            "kurallar": s["kurallar"],
            "kalan_baslama": max(0, int(s["basla_mono"] - simdi)),
            "kalan_bitis": max(0, int(s["bitis_mono"] - simdi)),
            "liste": [dict(o) for o in s["liste"]] if giris and s["liste"] else [],
            "liste_fazla": s["liste_fazla"] if giris and s["liste"] else 0,
            "yoklama_alindi": s["yoklama_alindi"],
            "bildirim": bildirim[0] if bildirim and bildirim[1] > simdi else "",
            "gozetmen": {
                "durum": g["durum"] if g else None,
                "hata": self.gozetmen_hata,
                "oturum": g["oturum"] if g else 0,
                # Kod sınav başlamadan girildiyse "Yoklama al" sınav başlayınca kendiliğinden açılır.
                "basladi": bool(g) and (g["basladi"] or not giris),
                "tahtadan_yoklama": bool(g) and g["tahtadan_yoklama"],
                "liste": [dict(o) for o in g["liste"]] if izgara else [],
                "gelmeyen": list(g["gelmeyen"]) if izgara else [],
                "bekleme": max(0, int(self.gozetmen_bekleme_bitis - simdi)),
            },
        }

    def _sinav_isle(self, deger) -> bool:
        """Sunucunun verdiği sınav durumunu uygular; ekrana yansıyan bir değişiklik olduysa True."""
        yeni = _sinav_coz(deger, time.monotonic())
        with self.kilit:
            eski = self.sinav
            if yeni is None:
                if eski is None:
                    return False
                self.sinav = None
                self._gozetmen_kapat()
                self.olaylar.append("Sınav ekranı kalktı (sunucu).")
                return True
            if eski is None or eski["kimlik"] != yeni["kimlik"]:
                self._gozetmen_kapat()
                self.gozetmen_hata = ""
                self.sinav = yeni
                if self.kapatma is not None:
                    self.kapatma = None
                    self.olaylar.append("Kapatma geri sayımı sınav nedeniyle iptal edildi.")
                self.olaylar.append(f"Sınav kipi alındı ({yeni['kimlik']}).")
                return True
            # Aynı sınav: kalan süre sunucuyla eşitlenir (tahta saatine güvenilmez). Giriş evresi
            # bittiyse bekçinin kaldırdığı liste geri gelmez (sunucu da artık göndermez).
            if eski["liste"] is None and yeni["liste"] is not None and time.monotonic() >= eski["basla_mono"] - 2:
                yeni["liste"], yeni["liste_fazla"] = None, 0
            degisti = any(eski[k] != yeni[k] for k in _SINAV_ALANLARI) or any(
                abs(eski[k] - yeni[k]) > 2 for k in ("basla_mono", "bitis_mono")
            )
            self.sinav = yeni
            return degisti

    def _sinav_denetle(self):
        """Bekçi (1 sn): süre dolunca sınav ekranını, giriş bitince listeyi, süresi dolan gözetmen
        oturumunu kaldırır — sunucuya ulaşılamasa da. Evre değişince sunucuya hemen bildirir."""
        yayinla = False
        with self.kilit:
            simdi = time.monotonic()
            s = self.sinav
            if s is not None and simdi >= s["bitis_mono"]:
                self.sinav = None
                self.sinav_yerel_kapali = None
                self._gozetmen_kapat()
                self.olaylar.append("Sınav süresi doldu; sınav ekranı kalktı.")
                yayinla = True
            elif s is not None and s["liste"] is not None and simdi >= s["basla_mono"]:
                s["liste"], s["liste_fazla"] = None, 0  # sınav başladı: liste bellekten de silinir
                yayinla = True
            g = self.gozetmen
            if g is not None and simdi >= g["bitis_mono"]:
                self._gozetmen_kapat()
                if g["durum"] != "dogrulaniyor":
                    self.gozetmen_bildirim = ("Gözetmen oturumu sona erdi.", simdi + GOZETMEN_BILDIRIM_SN)
                yayinla = True
            if self.gozetmen_bildirim and simdi >= self.gozetmen_bildirim[1]:
                self.gozetmen_bildirim = None
                yayinla = True
            if self.gozetmen_bekleme_bitis and simdi >= self.gozetmen_bekleme_bitis:
                # Kod beklemesi bitti: ekran tuş takımını açsın, eski bekleme iletisi kalmasın.
                self.gozetmen_bekleme_bitis = 0.0
                if self.gozetmen_hata.startswith("Çok fazla hatalı deneme"):
                    self.gozetmen_hata = ""
                yayinla = True
        evre = self._sinav_durumu()
        evre_degisti = evre != self._sinav_evre_son
        self._sinav_evre_son = evre
        if yayinla or evre_degisti:
            self.yayinla()
        if evre_degisti:
            self.bildir()

    def _gozetmen_kod(self, kod: str):
        """Ekrandan gelen gözetmen kodu: sunucuda doğrulanır (tahtada özet yok, kod saklanmaz)."""
        kod = "".join(c for c in str(kod) if c in RAKAMLAR)[: GOZETMEN_KOD_UZUNLUK + 2]
        istek = None
        with self.kilit:
            s = self._sinav_aktif()
            simdi = time.monotonic()
            if s is None or self.gozetmen is not None:
                return
            if self.acil is not None and self.acil["bitis"] > time.time():
                self.gozetmen_hata = "Acil yayın sürüyor."
            elif self.istemci is None or self.cevrimdisi() or not self.kayitli():
                self.gozetmen_hata = "Sunucuya ulaşılamıyor; yoklamayı kâğıda alın."
            elif simdi < self.gozetmen_bekleme_bitis:
                dk = max(1, -int(-(self.gozetmen_bekleme_bitis - simdi) // 60))  # yukarı yuvarla
                self.gozetmen_hata = f"Çok fazla hatalı deneme. {dk} dakika sonra yeniden deneyin."
            elif len(kod) != GOZETMEN_KOD_UZUNLUK:
                self.gozetmen_hata = "Gözetmen kodu 6 hanelidir."
            else:
                self.gozetmen_hata = ""
                # Doğrulanırken oturum yer tutucusu (belirteç yok); istek zaman aşımından sonra düşer.
                self.gozetmen = {"durum": "dogrulaniyor", "bitis_mono": simdi + 30, "oturum": 0, "liste": [],
                                 "liste_fazla": 0, "gelmeyen": [], "basladi": False, "tahtadan_yoklama": False}  # fmt: skip
                istek = (s["kimlik"], s["salon"], kod)
        self.yayinla()
        if istek:
            self.arka_plan(lambda: self._gozetmen_kod_gonder(*istek))

    def _gozetmen_kod_gonder(self, kimlik: str, salon: int, kod: str):
        try:
            durum_kodu, yanit, _ = self.istemci.istek("POST", "/ajan/sinav/kod", {"salon": salon, "kod": kod}, zaman_asimi=15)
        except (BaglantiHatasi, AttributeError):
            durum_kodu, yanit = None, {}
        yanit = yanit if isinstance(yanit, dict) else {}
        with self.kilit:
            g, s = self.gozetmen, self._sinav_aktif()
            if g is None or g["durum"] != "dogrulaniyor" or s is None or s["kimlik"] != kimlik:
                pass  # bu arada vazgeçildi ya da sınav değişti
            elif durum_kodu == 200 and isinstance(yanit.get("belirtec"), str) and yanit["belirtec"]:
                liste = _liste_coz(yanit.get("liste"))
                koltuklar = {o["k"] for o in liste}
                try:
                    sure = min(GOZETMEN_OTURUM_EN_UZUN_SN, max(60, int(yanit.get("sure_sn") or GOZETMEN_OTURUM_EN_UZUN_SN)))
                except (TypeError, ValueError):
                    sure = GOZETMEN_OTURUM_EN_UZUN_SN
                fazla = _sayi(yanit.get("liste_fazla"))
                self._gozetmen_oturum_no += 1
                self.gozetmen = {
                    "durum": "menu",
                    "belirtec": yanit["belirtec"][:200],
                    "bitis_mono": time.monotonic() + sure,
                    "oturum": self._gozetmen_oturum_no,
                    "liste": liste,
                    "liste_fazla": fazla,
                    "gelmeyen": sorted({k for k in (yanit.get("gelmeyen") or []) if _tamsayi_mi(k) and k in koltuklar}),
                    "basladi": bool(yanit.get("basladi")),
                    # 60'tan kalabalık salonun yoklaması panelden alınır (tahtada sayfalı ızgara sonraya).
                    "tahtadan_yoklama": bool(yanit.get("tahtadan_yoklama", fazla == 0)) and bool(liste),
                }
                self.gozetmen_hata = ""
                self.olaylar.append("Gözetmen kodu tahtada doğrulandı.")
            else:
                self._gozetmen_kapat()
                if durum_kodu == 429:
                    bekleme = min(3600, max(1, _sayi(yanit.get("bekleme_sn")) or 300))
                    self.gozetmen_bekleme_bitis = time.monotonic() + bekleme
                    self.gozetmen_hata = f"Çok fazla hatalı deneme. {(bekleme + 59) // 60} dakika sonra yeniden deneyin."
                elif durum_kodu == 403:
                    kalan = yanit.get("kalan_deneme")
                    self.gozetmen_hata = "Kod geçersiz." + (f" {kalan} deneme hakkı kaldı." if _tamsayi_mi(kalan) else "")
                elif durum_kodu is None:
                    self.gozetmen_hata = "Sunucuya ulaşılamadı; yoklamayı kâğıda alın."
                else:
                    self.gozetmen_hata = f"Kod doğrulanamadı (HTTP {durum_kodu}); yoklamayı kâğıda alın."
        self.yayinla()
        self.bildir()

    def _gozetmen_yoklama_ac(self):
        with self.kilit:
            g, s = self.gozetmen, self._sinav_aktif()
            if g is None or s is None or g["durum"] != "menu" or not g["tahtadan_yoklama"]:
                return
            if not (g["basladi"] or time.monotonic() >= s["basla_mono"]):
                return  # "Sınav başlayınca açılır"
            g["durum"] = "yoklama"
            self.gozetmen_hata = ""
        self.yayinla()

    def _gozetmen_kaydet(self, gelmeyen):
        with self.kilit:
            g = self.gozetmen
            if g is None or g["durum"] != "yoklama" or not isinstance(gelmeyen, list):
                return
            koltuklar = {o["k"] for o in g["liste"]}
            secilen = sorted({k for k in gelmeyen if _tamsayi_mi(k) and k in koltuklar})
            g["durum"], g["gelmeyen"] = "kaydediliyor", secilen
            self.gozetmen_hata = ""
            istek = (g["oturum"], g["belirtec"], secilen)
        self.yayinla()
        self.arka_plan(lambda: self._gozetmen_kaydet_gonder(*istek))

    def _gozetmen_kaydet_gonder(self, oturum: int, belirtec: str, secilen: list[int]):
        try:
            durum_kodu, yanit, _ = self.istemci.istek(
                "POST", "/ajan/sinav/yoklama", {"belirtec": belirtec, "gelmeyen": secilen}, zaman_asimi=15
            )
        except (BaglantiHatasi, AttributeError):
            durum_kodu, yanit = None, {}
        yanit = yanit if isinstance(yanit, dict) else {}
        with self.kilit:
            g = self.gozetmen
            if g is None or g["oturum"] != oturum:
                pass
            elif durum_kodu == 200:
                n = _sayi(yanit.get("gelmeyen_sayisi")) if "gelmeyen_sayisi" in yanit else len(secilen)
                # İşaretler ve liste kaydedilince ekrandan ve bellekten silinir (M3).
                self._gozetmen_kapat()
                self.gozetmen_bildirim = (f"Yoklama kaydedildi: {n} öğrenci gelmedi.", time.monotonic() + GOZETMEN_BILDIRIM_SN)
                if self.sinav is not None:
                    self.sinav["yoklama_alindi"] = True
                self.olaylar.append(f"Sınav yoklaması tahtadan kaydedildi ({n} gelmedi).")
            elif durum_kodu in (401, 409):
                # Oturum ya da sınav kipi bitti: işaretler tutulamaz; gözetmen kâğıda alır.
                self._gozetmen_kapat()
                metin = str(yanit.get("hata") or "Gözetmen oturumu sona erdi; kodu yeniden girin.")[:200]
                self.gozetmen_bildirim = (metin, time.monotonic() + 3 * GOZETMEN_BILDIRIM_SN)
            else:
                g["durum"] = "yoklama"  # işaretler korunur, yeniden denenebilir
                self.gozetmen_hata = (
                    str(yanit.get("hata") or f"Kaydedilemedi (HTTP {durum_kodu}).")[:200]
                    if durum_kodu is not None
                    else "Sunucuya ulaşılamadı; yeniden deneyin ya da yoklamayı kâğıda alın."
                )
        self.yayinla()
        self.bildir()

    # ---- ders yoklaması (A5) --------------------------------------------------------------
    # Akış: yoklama_ac → /oneri (şube, ders saatleri; öğrenci verisi yok) → PIN sayfası → /baslat
    # (belirteç) → /liste → işaretler → onay → /kaydet. Belirteç ve liste yalnız bu süreçte, bellekte.
    def _gorunur_ekran_var(self) -> bool:
        with self.kilit:
            return any(e["bilgi"].get("arayuz") not in GORUNMEZ_ARAYUZ for e in self.ekranlar.values())

    def _yoklama_yeni(self, asama: str) -> dict:
        self._yoklama_oturum_no += 1
        return {
            "asama": asama,  # yukleniyor | pin | liste | onay | kaydediliyor | ileti
            "oturum": self._yoklama_oturum_no,
            "oneri": None,  # _oneri_coz() çıktısı
            "ogretmen": None,
            "sube": None,
            "ders_no": None,
            "ders_adi": "",
            "ogrenciler": [],  # [{"id","etiket"}] yalnız bellekte
            "yok": set(),
            "mevcut": 0,
            "baska_yoklama": False,
            "liste_ileti": "",
            "liste_yuklu": False,
            "bitis": None,  # time.monotonic(); sunucunun kalan_sn'sinden
            "bosta_sn": YOKLAMA_BOSTA_VARSAYILAN_SN,
            "son_dokunma": time.monotonic(),
            "ileti": "",
            "ileti_bitis": None,
            "hata": "",
            "bekleme_bitis": 0.0,
            "istek": False,  # sunucuya giden istek sürüyor
            "kaydet_denendi": False,
            "uyari_son": False,
            "usb": False,  # 0.11.0: oturum USB anahtarla açılacak (öğretmen kodu sorulmaz)
            "usb_not": "",  # PIN sayfasında gösterilecek USB bilgisi ("çok uzun süredir takılı")
        }

    def _yoklama_ileti_ver(self, metin: str, sure: int = YOKLAMA_ILETI_SN):
        """Yoklamayı yalnız bir iletiye indirir (çağıran kilidi tutar): liste, işaretler ve belirteç
        bellekten atılır. Sunucuda kapatılması gereken belirteci döndürür (/bitir kilit dışında gider)."""
        y = self.yoklama
        if y is None:
            y = self.yoklama = self._yoklama_yeni("ileti")
        belirtec, self._yoklama_belirtec = self._yoklama_belirtec, None
        y.update(asama="ileti", ogrenciler=[], yok=set(), liste_yuklu=False, ileti=str(metin)[:300],
                 ileti_bitis=time.monotonic() + sure, hata="", istek=False, bitis=None)  # fmt: skip
        return belirtec

    def _yoklama_kapat(self):
        """Yoklamayı tamamen kapatır (çağıran kilidi tutar); belirteci döndürür."""
        belirtec, self._yoklama_belirtec = self._yoklama_belirtec, None
        self.yoklama = None
        return belirtec

    def yoklama_acik(self) -> bool:
        with self.kilit:
            return self.yoklama is not None and self.yoklama["asama"] != "ileti"

    def _yoklama_istek(self, yol: str, govde: dict) -> tuple[int | None, dict]:
        try:
            kod, yanit, _ = self.istemci.istek("POST", yol, govde, zaman_asimi=YOKLAMA_ISTEK_SN)
        except (BaglantiHatasi, AttributeError):
            return None, {}
        return kod, yanit if isinstance(yanit, dict) else {}

    def _yoklama_bitir_gonder(self, belirtec):
        """Sunucudaki oturumu kapatır (arka planda; yanıt beklenmez)."""
        if not belirtec or self.istemci is None:
            return
        self.arka_plan(lambda: self._yoklama_istek("/ajan/yoklama/bitir", {"belirtec": belirtec}))

    def _yoklama_ac(self):
        oturum = None
        with self.kilit:
            y = self.yoklama
            if y is not None and y["asama"] != "ileti":
                y["son_dokunma"] = time.monotonic()  # zaten açık: yeniden açılmaz
            elif not any(e["bilgi"].get("arayuz") not in GORUNMEZ_ARAYUZ for e in self.ekranlar.values()):
                # Gösterecek pencere yoksa yoklama açılmaz (kısayol oturum dışından çağrılmış olabilir).
                self.olaylar.append("Yoklama açılamadı: ekran yardımcısı bağlı değil.")
                return
            else:
                self.yoklama = None
                if self._sinav_aktif() is not None:
                    self._yoklama_ileti_ver(ILETI_YOKLAMA_SINAV)
                elif self.acil is not None and self.acil["bitis"] > time.time():
                    self._yoklama_ileti_ver(ILETI_YOKLAMA_ACIL)  # acil üsttedir; iletiyi acil bitince görür
                elif self.istemci is None or not self.kayitli() or self.cevrimdisi():
                    self._yoklama_ileti_ver(ILETI_YOKLAMA_SUNUCU_YOK)
                elif self.yoklama_etkin is False:
                    self._yoklama_ileti_ver(ILETI_YOKLAMA_KAPALI)
                else:
                    self.yoklama = self._yoklama_yeni("yukleniyor")
                    self.yoklama["istek"] = True
                    oturum = self.yoklama["oturum"]
                    # USB anahtar (0.11.0): tanınmış ve yoklama izinli anahtar kod + PIN adımını atlatır.
                    if self._usb_gizli is not None and self.usb["durum"] == "tanindi" and "yoklama" in self.usb["izinler"]:
                        self.yoklama["usb"] = True
                    elif self.usb_etkin and self.usb["durum"] == "suresi_doldu":
                        self.yoklama["usb_not"] = usb_anahtar.ILETI_SURESI_DOLDU
        self.yayinla()
        self.bildir()
        if oturum is not None:
            self.arka_plan(lambda: self._yoklama_oneri_al(oturum))

    def _yoklama_oneri_al(self, oturum: int, sube: str | None = None):
        """İlk açılışta öneri (sube=None) ya da şube değişince o şubenin ders saatleri."""
        kod, yanit = self._yoklama_istek("/ajan/yoklama/oneri", {"sube": sube} if sube else {})
        belirtec, usb_baslat = None, None
        with self.kilit:
            y = self.yoklama
            if y is None or y["oturum"] != oturum or (sube is not None and y["sube"] != sube):
                return
            y["istek"] = False
            if kod == 200:
                oneri = _oneri_coz(yanit)
                if sube is None and y["usb"] and not self.usb["pin_gerek"]:
                    # USB anahtar, PIN sorulmuyor: PIN sayfası hiç açılmadan oturum istenir.
                    y.update(oneri=oneri, sube=oneri["sube"], ders_no=oneri["ders_no"], hata="", istek=True)
                    y["son_dokunma"] = time.monotonic()
                    usb_baslat = oturum
                elif sube is None:
                    y.update(oneri=oneri, sube=oneri["sube"], ders_no=oneri["ders_no"], asama="pin", hata=y["usb_not"])
                    y["son_dokunma"] = time.monotonic()
                elif y["oneri"] is not None:
                    y["oneri"]["ders_saatleri"] = oneri["ders_saatleri"]
                    y["oneri"]["ders_no_en_cok"] = oneri["ders_no_en_cok"]
            elif kod == 409:
                belirtec = self._yoklama_ileti_ver(str(yanit.get("hata") or ILETI_YOKLAMA_KAPALI))
            elif kod in (404, 405):
                belirtec = self._yoklama_ileti_ver(ILETI_YOKLAMA_DESTEK_YOK)
            elif sube is None or kod in (401, 403):
                belirtec = self._yoklama_ileti_ver(ILETI_YOKLAMA_SUNUCU_YOK)
            else:
                y["hata"] = "Ders saatleri alınamadı; yeniden deneyin."
        self._yoklama_bitir_gonder(belirtec)
        self.yayinla()
        self.bildir()
        if usb_baslat is not None:
            self._usb_yoklama_baslat(usb_baslat, None)

    def _yoklama_pin(self, kod, pin):
        """Ekrandan gelen öğretmen kodu + PIN: sunucuda doğrulanır. PIN saklanmaz, günlüğe yazılmaz."""
        kod = "".join(c for c in str(kod) if c in RAKAMLAR)[:4]
        pin = "".join(c for c in str(pin) if c in RAKAMLAR)[:7]
        istek = None
        with self.kilit:
            y = self.yoklama
            if y is None or y["asama"] != "pin" or y["istek"]:
                return
            simdi = time.monotonic()
            y["son_dokunma"] = simdi
            if simdi < y["bekleme_bitis"]:
                y["hata"] = f"Çok fazla hatalı deneme. {int(y['bekleme_bitis'] - simdi) + 1} saniye bekleyin."
            elif len(kod) != 3 and not y["usb"]:  # USB kipinde öğretmen kodu sorulmaz (gelirse yok sayılır)
                y["hata"] = "Öğretmen kodu 3 hanelidir."
            elif len(pin) != 6:
                y["hata"] = "PIN 6 hanelidir."
            else:
                y["hata"], y["istek"] = "", True
                istek = (y["oturum"], kod, pin, y["usb"])
        self.yayinla()
        if istek and istek[3]:
            self.arka_plan(lambda: self._usb_yoklama_baslat(istek[0], istek[2]))
        elif istek:
            self.arka_plan(lambda: self._yoklama_baslat(*istek[:3]))

    def _yoklama_baslat(self, oturum: int, kod: str, pin: str):
        durum_kodu, yanit = self._yoklama_istek("/ajan/yoklama/baslat", {"kod": kod, "pin": pin})
        del pin
        kapatilacak, liste = None, None
        with self.kilit:
            y = self.yoklama
            belirtec = yanit.get("belirtec") if durum_kodu == 200 and isinstance(yanit.get("belirtec"), str) else None
            if y is None or y["oturum"] != oturum or y["asama"] != "pin":
                kapatilacak = belirtec  # bu arada vazgeçildi: açılan oturum boşa kalmasın
            elif belirtec:
                liste = self._yoklama_oturum_acildi(y, yanit, oturum, belirtec)
                self.olaylar.append("Ders yoklaması oturumu açıldı.")
            else:
                y["istek"] = False
                hata = _kes(yanit.get("hata"), 200)
                if durum_kodu == 429:
                    y["bekleme_bitis"] = time.monotonic() + min(3600, max(1, _sayi(yanit.get("bekleme_sn")) or 120))
                    y["hata"] = hata or "Çok fazla hatalı deneme. Biraz bekleyip yeniden deneyin."
                elif durum_kodu == 403 and "bekleme_sn" in yanit:
                    y["hata"] = hata or "Öğretmen kodu ya da PIN hatalı."
                elif durum_kodu == 423:
                    kapatilacak = self._yoklama_ileti_ver(hata or "PIN'iniz kilitlendi. Okul idaresine başvurun.", 8)
                elif durum_kodu == 409:
                    kapatilacak = self._yoklama_ileti_ver(hata or ILETI_YOKLAMA_KAPALI)
                elif durum_kodu in (401, 403):
                    kapatilacak = self._yoklama_ileti_ver("Bu tahta sunucuda tanınmıyor; okul idaresine bildirin.")
                elif durum_kodu in (404, 405):
                    kapatilacak = self._yoklama_ileti_ver(ILETI_YOKLAMA_DESTEK_YOK)
                elif durum_kodu is None:
                    y["hata"] = "Sunucuya ulaşılamadı; yeniden deneyin."
                else:
                    y["hata"] = f"PIN doğrulanamadı (HTTP {durum_kodu})."
        self._yoklama_bitir_gonder(kapatilacak)
        self.yayinla()
        self.bildir()
        if liste:
            self._yoklama_liste_al(*liste)

    def _yoklama_oturum_acildi(self, y: dict, yanit: dict, oturum: int, belirtec: str):
        """Sunucu oturumu açtı (kod + PIN ya da USB anahtar; çağıran kilidi tutar). Liste isteğini döndürür."""
        self._yoklama_belirtec = belirtec[:200]
        kalan = min(YOKLAMA_OTURUM_EN_UZUN_SN, max(30, _sayi(yanit.get("kalan_sn")) or 480))
        ogretmen = yanit.get("ogretmen") if isinstance(yanit.get("ogretmen"), dict) else {}
        y.update(
            asama="liste", hata="", istek=False, bitis=time.monotonic() + kalan, son_dokunma=time.monotonic(),
            bosta_sn=min(600, max(30, _sayi(yanit.get("bosta_sn")) or YOKLAMA_BOSTA_VARSAYILAN_SN)),
            ogretmen={"kod": _kes(ogretmen.get("kod"), 4), "etiket": _kes(ogretmen.get("etiket"), 60)},
        )  # fmt: skip
        if y["sube"] and y["ders_no"]:
            y["istek"] = True
            return (oturum, y["sube"], y["ders_no"])
        return None

    def _yoklama_liste_al(self, oturum: int, sube: str, ders_no: int):
        with self.kilit:
            belirtec = self._yoklama_belirtec
        durum_kodu, yanit = self._yoklama_istek("/ajan/yoklama/liste", {"belirtec": belirtec, "sube": sube, "ders_no": ders_no})
        kapatilacak = None
        with self.kilit:
            y = self.yoklama
            if y is None or y["oturum"] != oturum or (y["sube"], y["ders_no"]) != (sube, ders_no):
                return
            y["istek"] = False
            hata = _kes(yanit.get("hata"), 200)
            if durum_kodu == 200:
                ogrenciler = _yoklama_listesi_coz(yanit.get("ogrenciler"))
                kimlikler = {o["id"] for o in ogrenciler}
                yok = {i for i in (yanit.get("yok") if isinstance(yanit.get("yok"), list) else []) if _tamsayi_mi(i) and i in kimlikler}
                y.update(ogrenciler=ogrenciler, yok=yok, mevcut=len(ogrenciler), liste_yuklu=True, hata="",
                         baska_yoklama=bool(yanit.get("baska_yoklama")), liste_ileti=_kes(yanit.get("ileti"), 200),
                         ders_adi=_kes(yanit.get("ders_adi"), 60), kaydet_denendi=False)  # fmt: skip
                if _sayi(yanit.get("kalan_sn")):
                    y["bitis"] = time.monotonic() + min(YOKLAMA_OTURUM_EN_UZUN_SN, _sayi(yanit.get("kalan_sn")))
            elif durum_kodu == 400:
                y["ders_no"], y["hata"] = None, hata or "Ders saatini yeniden seçin."  # seçime dön
            elif durum_kodu in (401, 403, 409):
                kapatilacak = self._yoklama_ileti_ver(hata or "Yoklama oturumu sona erdi; PIN'i yeniden girin.")
            elif durum_kodu is None:
                y["hata"] = "Liste alınamadı: sunucuya ulaşılamadı. Ders saatine yeniden dokunun."
                y["ders_no"] = None
            else:
                y["hata"] = f"Liste alınamadı (HTTP {durum_kodu})."
                y["ders_no"] = None
        self._yoklama_bitir_gonder(kapatilacak)
        self.yayinla()

    def _yoklama_sec(self, mesaj: dict):
        """Şube ve/veya ders saati seçimi. Seçim değişince liste ve işaretler bırakılır."""
        oneri_iste, liste_iste = None, None
        with self.kilit:
            y = self.yoklama
            if y is None or y["asama"] != "liste" or y["istek"] or not self._yoklama_belirtec:
                return
            y["son_dokunma"] = time.monotonic()
            oneri = y["oneri"] or {}
            sube_degisti = False
            if "sube" in mesaj:
                s = mesaj.get("sube")
                if isinstance(s, str) and s and (not oneri.get("subeler") or s in oneri["subeler"]) and s != y["sube"]:
                    y["sube"], y["ders_no"], sube_degisti = s[:16], None, True
            if "ders_no" in mesaj and not sube_degisti:
                d = mesaj.get("ders_no")
                if d is None:
                    y["ders_no"] = None
                elif _tamsayi_mi(d) and any(s["ders_no"] == d and s["secilebilir"] for s in _ders_secenekleri(oneri)):
                    y["ders_no"] = d
            y.update(ogrenciler=[], yok=set(), mevcut=0, liste_yuklu=False, liste_ileti="", baska_yoklama=False, hata="")
            if sube_degisti:
                y["istek"] = True
                oneri_iste = (y["oturum"], y["sube"])
            elif y["sube"] and y["ders_no"]:
                y["istek"] = True
                liste_iste = (y["oturum"], y["sube"], y["ders_no"])
        self.yayinla()
        if oneri_iste:
            self.arka_plan(lambda: self._yoklama_oneri_al(*oneri_iste))
        if liste_iste:
            self.arka_plan(lambda: self._yoklama_liste_al(*liste_iste))

    def _yoklama_isaret(self, kimlik):
        with self.kilit:
            y = self.yoklama
            if y is None or y["asama"] != "liste" or not y["liste_yuklu"] or not _tamsayi_mi(kimlik):
                return
            if not any(o["id"] == kimlik for o in y["ogrenciler"]):
                return
            y["son_dokunma"] = time.monotonic()
            y["yok"] ^= {kimlik}
        self.yayinla()

    def _yoklama_asama(self, eski: str, yeni: str):
        """Kaydet (liste → onay) ve Geri (onay → liste)."""
        with self.kilit:
            y = self.yoklama
            if y is None or y["asama"] != eski or y["istek"]:
                return
            if yeni == "onay" and not (y["liste_yuklu"] and y["ogrenciler"]):
                return
            y.update(asama=yeni, son_dokunma=time.monotonic(), hata="")
        self.yayinla()

    def _yoklama_onayla(self):
        with self.kilit:
            y = self.yoklama
            if y is None or y["asama"] != "onay" or y["istek"] or not self._yoklama_belirtec:
                return
            y.update(asama="kaydediliyor", istek=True, hata="", son_dokunma=time.monotonic())
            istek = (y["oturum"], self._yoklama_belirtec, y["sube"], y["ders_no"], sorted(y["yok"]))
        self.yayinla()
        self.arka_plan(lambda: self._yoklama_kaydet_gonder(*istek))

    def _yoklama_kaydet_gonder(self, oturum: int, belirtec: str, sube: str, ders_no: int, yok: list[int]):
        durum_kodu, yanit = self._yoklama_istek(
            "/ajan/yoklama/kaydet", {"belirtec": belirtec, "sube": sube, "ders_no": ders_no, "yok": yok}
        )
        kapatilacak = None
        with self.kilit:
            y = self.yoklama
            if y is None or y["oturum"] != oturum:
                return
            y["istek"] = False
            hata = _kes(yanit.get("hata"), 200)
            if durum_kodu == 200:
                n = _sayi(yanit.get("yok_sayisi")) if "yok_sayisi" in yanit else len(yok)
                self._yoklama_belirtec = None  # sunucu kaydet sonrası oturumu kapattı (tek seferlik)
                self._yoklama_ileti_ver(f"Kaydedildi: {n} öğrenci yok." if n else "Kaydedildi: bütün öğrenciler derste.",
                                        YOKLAMA_KAYDEDILDI_SN)  # fmt: skip
                self.olaylar.append(f"Ders yoklaması tahtadan kaydedildi ({n} yok).")
            elif durum_kodu == 401 and y["kaydet_denendi"]:
                # Önceki deneme sunucuya ulaşıp yanıtı yitirmiş olabilir; belirteç o anda silinmişti.
                kapatilacak = self._yoklama_ileti_ver("Yoklama kaydedilmiş olabilir; panelde kontrol edilir.", 8)
            elif durum_kodu in (400, 401, 403, 409):
                kapatilacak = self._yoklama_ileti_ver(hata or "Yoklama kaydedilemedi; PIN'i yeniden girin.", 8)
            else:
                # Ağ hatası: liste ve işaretler bellekte kalır, süre işlemeye devam eder.
                y.update(asama="onay", hata="Kaydedilemedi; yeniden deneyin.", kaydet_denendi=True)
        self._yoklama_bitir_gonder(kapatilacak)
        self.yayinla()
        self.bildir()

    def _yoklama_denetle(self):
        """Bekçi (1 sn): süre, dokunulmama, ileti süresi, sınav ve ayar değişikliği."""
        kapatilacak, degisti = None, False
        with self.kilit:
            y = self.yoklama
            if y is None:
                return
            simdi = time.monotonic()
            if y["asama"] == "ileti":
                if y["ileti_bitis"] is None or simdi >= y["ileti_bitis"]:
                    self.yoklama, degisti = None, True
            elif self._sinav_aktif() is not None:
                kapatilacak, degisti = self._yoklama_ileti_ver(ILETI_YOKLAMA_SINAV), True
            elif self.yoklama_etkin is False:
                kapatilacak, degisti = self._yoklama_ileti_ver(ILETI_YOKLAMA_KAPALI), True
            elif y["bitis"] is not None and simdi >= y["bitis"]:
                kapatilacak, degisti = self._yoklama_kapat(), True  # sessizce kapanır
            elif not y["istek"] and y["asama"] in ("pin", "liste", "onay") and simdi - y["son_dokunma"] >= (
                y["bosta_sn"] if self._yoklama_belirtec else YOKLAMA_PIN_BOSTA_SN
            ):
                kapatilacak, degisti = self._yoklama_kapat(), True
            else:
                uyari = y["bitis"] is not None and y["bitis"] - simdi <= YOKLAMA_UYARI_SN
                if uyari != y["uyari_son"]:
                    y["uyari_son"], degisti = uyari, True
                if y["bekleme_bitis"] and simdi >= y["bekleme_bitis"]:
                    y["bekleme_bitis"], degisti = 0.0, True
                    if y["hata"].startswith("Çok fazla hatalı deneme"):
                        y["hata"] = ""
        self._yoklama_bitir_gonder(kapatilacak)
        if degisti:
            self.yayinla()
            self.bildir()

    def _yoklama_gorunumu(self) -> dict | None:
        """Ekran yardımcısına giden yoklama görünümü (çağıran kilidi tutar). Belirteç GİRMEZ.
        Liste ve işaretler yalnız PIN sonrası ve liste sayfalarında doludur (M3)."""
        y = self.yoklama
        if y is None:
            return None
        simdi = time.monotonic()
        oneri = y["oneri"] or {}
        liste = y["asama"] in ("liste", "onay", "kaydediliyor") and y["liste_yuklu"] and self._yoklama_belirtec is not None
        secenekler = _ders_secenekleri(oneri)
        saat = next((s for s in secenekler if s["ders_no"] == y["ders_no"]), None)
        return {
            "asama": y["asama"],
            "oturum": y["oturum"],
            "tarih_yazi": oneri.get("tarih_yazi", ""),
            "ogretmen": dict(y["ogretmen"]) if y["ogretmen"] else None,
            "sube": y["sube"],
            "ders_no": y["ders_no"],
            "ders_adi": y["ders_adi"],
            "ders_metni": saat["metin"] if saat else (f"{y['ders_no']}. ders" if y["ders_no"] else ""),
            "ders_saatleri": secenekler,
            "subeler": list(oneri.get("subeler") or []),
            "liste_yuklu": liste,
            "ogrenciler": [dict(o) for o in y["ogrenciler"]] if liste else [],
            "yok": sorted(y["yok"]) if liste else [],
            "mevcut": y["mevcut"] if liste else 0,
            "baska_yoklama": y["baska_yoklama"] if liste else False,
            "liste_ileti": y["liste_ileti"] if liste else "",
            "kalan": max(0, int(y["bitis"] - simdi)) if y["bitis"] is not None else None,
            "uyari": y["bitis"] is not None and y["bitis"] - simdi <= YOKLAMA_UYARI_SN,
            "ileti": y["ileti"] if y["asama"] == "ileti" else "",
            "hata": y["hata"],
            "bekleme": max(0, int(y["bekleme_bitis"] - simdi + 0.999)) if y["bekleme_bitis"] else 0,
            "istek": y["istek"],
            # USB anahtar (0.11.0): "usb" ise PIN sayfasında öğretmen kodu sorulmaz (yalnız PIN).
            "pin_kipi": "usb" if y.get("usb") else "",
            "usb_etiket": usb_anahtar.sahip_metni(self.usb) if y.get("usb") else "",
        }

    # ---- USB anahtar (0.11.0) -------------------------------------------------------------
    # Akış: izleme (yalnız ayar açıkken) → yeni bağlamanın kökünde anahtar dosyası → parmak izi denetimi →
    # /ajan/usb/tani → "tanındı" (gizli bellekte, en çok TANI_OMRU_SN). Yoklama ve kilit açma DOKUNUŞLA başlar;
    # takılınca yalnız küçük bir bildirim çıkar. Bellek çıkarılınca gizli silinir, açık yoklama listesi kalır.
    def _usb_izlemeyi_ayarla(self, etkin) -> bool:
        """Sunucunun `ayar.usb_anahtar.etkin` bayrağı (None: alan yok = eski sunucu). Değiştiyse True."""
        baslat = None
        with self.kilit:
            if etkin == self.usb_etkin:
                return False
            self.usb_etkin = etkin
            if etkin and self._usb_izleme is None:
                baslat = threading.Event()
                self._usb_izleme = {"dur": baslat}
            elif not etkin and self._usb_izleme is not None:
                self._usb_izleme["dur"].set()
                self._usb_izleme = None
                self._usb_izleme_durumu = "kapali"
                self._usb_gorulen.clear()
                self._usb_baglama = None
                self._usb_istek_no += 1
                self._usb_sifirla()  # açık yoklama oturumu sürer (belirteç ayrı yetkidir)
        if baslat is not None:
            self.arka_plan_surekli(lambda: self._usb_izle(baslat))
        return True

    def arka_plan_surekli(self, is_):
        """Uzun süren iş (izleme döngüsü) her zaman ayrı iş parçacığında çalışır (testler `_usb_tara` çağırır)."""
        threading.Thread(target=is_, daemon=True).start()

    def _usb_izle(self, dur: threading.Event):
        izleyici = self.usb_izleyici_kur()
        with self.kilit:
            if self._usb_izleme is None or self._usb_izleme["dur"] is not dur:
                if izleyici is not None:
                    izleyici.kapat()
                return
            self._usb_izleme_durumu = "izleniyor" if izleyici is not None else "desteklenmiyor"
        if izleyici is None:
            gunluk.info("USB anahtar: bağlama noktaları izlenemiyor (desteklenmiyor).")
            return
        gunluk.info("USB anahtar: bağlama noktaları izleniyor.")
        try:
            while not dur.is_set() and not self.dur.is_set():
                try:
                    self._usb_tara(izleyici.oku())
                except Exception as hata:  # izleme hiçbir koşulda servisi düşürmez; yol/içerik günlüğe yazılmaz
                    gunluk.warning("USB anahtar izleme turu başarısız: %s", type(hata).__name__)
                izleyici.bekle(usb_anahtar.IZLEME_ZAMAN_ASIMI_SN)
        finally:
            izleyici.kapat()

    def _usb_sifirla(self, durum: str = "yok", ileti: str = "", ileti_sn: float | None = None):
        """Anahtar durumunu sıfırlar ve gizli değeri bellekten atar (çağıran kilidi tutar)."""
        self._usb_gizli = None
        self._usb_pin = None
        self.usb = _usb_bos(durum, ileti, time.monotonic() + ileti_sn if ileti_sn else None)

    def _usb_bildirim(self):
        """Ekranda küçük bildirim (tanındı/reddedildi). Yeni numara gelmedikçe kapanan bildirim yeniden açılmaz."""
        self._usb_bildirim_no += 1

    def _usb_tara(self, mountinfo: str):
        """Bir izleme turu: takılı bellekleri bulur, çıkarılanı düşürür, yeni bağlamanın kökündeki anahtarı okur."""
        adaylar, elenen = sistem.cikarilabilir_baglamalar(mountinfo)
        kimlikler = {a["kimlik"] for a in adaylar}
        kapatilacak, degisti = None, False
        with self.kilit:
            if self._usb_izleme is None:
                return
            self._usb_tani.update(takili=len(adaylar), elenen=dict(elenen))
            self._usb_gorulen &= kimlikler
            if self._usb_baglama is not None and self._usb_baglama not in kimlikler:
                kapatilacak, degisti = self._usb_cikarildi(), True
            yeniler = [a for a in adaylar if a["kimlik"] not in self._usb_gorulen]
            self._usb_gorulen |= {a["kimlik"] for a in yeniler}
        bulunan = []
        for baglama in yeniler:
            veri = sistem.anahtar_oku(baglama)
            if isinstance(veri, sistem.Red):
                with self.kilit:
                    self._usb_tani["son_okuma"] = veri.neden
                continue
            try:
                bulunan.append((baglama["kimlik"], usb_anahtar.dosya_coz(veri)))
                sonuc = "bulundu"
            except usb_anahtar.DosyaHatasi as hata:
                sonuc = "surum" if hata.neden == "surum" else "bicim"
            del veri
            with self.kilit:
                self._usb_tani["son_okuma"] = sonuc
                if sonuc == "surum" and self.usb["durum"] in ("yok", "cikarildi", "suresi_doldu"):
                    self._usb_baglama = baglama["kimlik"]
                    self._usb_sifirla("reddedildi", usb_anahtar.ILETI_SURUM)
                    self._usb_bildirim()
                    degisti = True
        tani_iste = False
        for baglama_kimlik, dosya in bulunan:
            with self.kilit:
                if self.usb["durum"] in ("okunuyor", "tanindi", "cevrimdisi") and self._usb_baglama is not None:
                    # İlk tanınan geçerlidir; ötekiler yok sayılır (gizli değerleri hiç saklanmaz).
                    self.usb.update(ileti=usb_anahtar.ILETI_BIRDEN_COK, ileti_bitis=time.monotonic() + USB_ILETI_SN)
                    self._usb_bildirim()
                    degisti = True
                    continue
                self._usb_baglama = baglama_kimlik
                self._usb_istek_no += 1
                if not usb_anahtar.sunucu_uyar_mi(dosya["sunucu"], self.yapi.get("parmak_izi", "")):
                    # Başka bir sunucunun anahtarı: gizli değer hiçbir yere gönderilmez.
                    self._usb_sifirla("yabanci", usb_anahtar.ILETI_YABANCI)
                    self._usb_tani["son_dogrulama"] = "başka sunucunun anahtarı"
                    self._usb_bildirim()
                    degisti = True
                    continue
                self._usb_sifirla("okunuyor")
                self._usb_gizli = (dosya["kimlik"], dosya["gizli"])
                tani_iste = True
            del dosya
        self._yoklama_bitir_gonder(kapatilacak)
        if tani_iste:
            self._usb_tani_iste()
        elif degisti:
            self.yayinla()

    def _usb_cikarildi(self):
        """Bellek çıkarıldı (çağıran kilidi tutar): gizli silinir; PIN bekleyen USB'li yoklama ve kilit açma
        PIN sayfası kapanır (PIN bellek olmadan girilmesin). Açık yoklama listesi KALIR. Kapatılacak belirteci döndürür."""
        kapatilacak = None
        y = self.yoklama
        if y is not None and y.get("usb") and y["asama"] in ("yukleniyor", "pin"):
            kapatilacak = self._yoklama_ileti_ver(usb_anahtar.ILETI_CIKARILDI)
        self._usb_baglama = None
        self._usb_istek_no += 1
        self._usb_kilit_suruyor = False
        self._usb_sifirla("cikarildi", usb_anahtar.ILETI_CIKARILDI, USB_CIKARILDI_SN)
        return kapatilacak

    def _usb_tani_iste(self):
        """Okunan anahtarı sunucuda doğrular (arka planda). Sunucuya ulaşılamıyorsa "cevrimdisi"."""
        istek = None
        with self.kilit:
            gizli = self._usb_gizli
            if gizli is None:
                return
            if self.istemci is None or not self.kayitli() or self.cevrimdisi():
                ileti = usb_anahtar.ILETI_KAYITSIZ if not self.kayitli() else usb_anahtar.ILETI_CEVRIMDISI
                if self.usb["durum"] != "cevrimdisi":
                    self._usb_bildirim()
                self.usb.update(durum="cevrimdisi", ileti=ileti)
                self._usb_tani["son_dogrulama"] = "sunucuya ulaşılamadı"
            else:
                self._usb_istek_no += 1
                self.usb["durum"] = "okunuyor"
                istek = (self._usb_istek_no, gizli)
        self.yayinla()
        if istek:
            self.arka_plan(lambda: self._usb_tani_gonder(*istek))

    def _usb_tani_gonder(self, no: int, gizli: tuple[str, str]):
        kod, yanit = self._yoklama_istek("/ajan/usb/tani", {"kimlik": gizli[0], "gizli": gizli[1]})
        with self.kilit:
            if no != self._usb_istek_no or self._usb_gizli != gizli:
                return  # bu arada bellek çıkarıldı ya da başka anahtar geldi
            anahtar = yanit.get("anahtar")
            if kod == 200 and isinstance(anahtar, dict):
                tur = "idare" if anahtar.get("tur") == "idare" else "ogretmen"
                omur = min(usb_anahtar.TANI_OMRU_SN, max(10, _sayi(yanit.get("omur_sn")) or usb_anahtar.TANI_OMRU_SN))
                izinler = yanit.get("izinler") if isinstance(yanit.get("izinler"), list) else []
                if self.usb["ileti_bitis"] is None:
                    self.usb["ileti"] = ""  # "sunucuya ulaşılamıyor" gibi durum iletisi kalkar; süreli ileti kalır
                self.usb.update(
                    durum="tanindi", tur=tur, etiket=_kes(anahtar.get("etiket"), 60),
                    kod=_kes(anahtar.get("kod"), 4) if tur == "ogretmen" else "", pin_gerek=bool(yanit.get("pin_gerek")),
                    izinler=[i for i in ("yoklama", "kilit_ac") if i in izinler], omur_bitis=time.monotonic() + omur,
                )  # fmt: skip
                self._usb_tani["son_dogrulama"] = f"tanındı ({'idare' if tur == 'idare' else 'öğretmen'} anahtarı)"
                self._usb_bildirim()
            elif kod is None:
                if self.usb.get("yeniden"):
                    self._usb_gizli = None  # bir kez yeniden denendi; çıkarıp takınca yeniden okunur
                self.usb.update(durum="cevrimdisi", ileti=usb_anahtar.ILETI_CEVRIMDISI)
                self._usb_tani["son_dogrulama"] = "sunucuya ulaşılamadı"
                self._usb_bildirim()
            else:
                self._usb_reddet(kod, yanit)
        self.yayinla()

    def _usb_reddet(self, kod, yanit: dict) -> str:
        """Sunucu anahtarı reddetti (çağıran kilidi tutar): gizli silinir, ileti verilir. İletiyi döndürür."""
        neden = yanit.get("neden") if isinstance(yanit.get("neden"), str) else ""
        if kod == 401:
            ileti = usb_anahtar.ILETI_TANINMIYOR
        else:
            ileti = _kes(yanit.get("hata"), 200) or usb_anahtar.NEDEN_ILETISI.get(neden) or f"USB anahtar doğrulanamadı (HTTP {kod})."
        self._usb_tani["son_dogrulama"] = {"iptal": "iptal edilmiş", "kilitli": "kilitli"}.get(neden, "geçersiz")
        self._usb_sifirla("reddedildi", ileti)
        self._usb_bildirim()
        return ileti

    def _usb_denetle(self):
        """Bekçi (1 sn): tanıma ömrü, ileti süresi, kilit açma PIN sayfasının durumu, çevrimdışı tanımanın yeniden denenmesi."""
        degisti, yeniden = False, False
        with self.kilit:
            u, simdi = self.usb, time.monotonic()
            if u["durum"] == "tanindi" and u["omur_bitis"] is not None and simdi >= u["omur_bitis"]:
                # Unutulan bellek kalıcı yetki bırakmaz; ileti yalnız bir dokunuşta gösterilir.
                self._usb_sifirla("suresi_doldu")
                self._usb_tani["son_dogrulama"] = "süresi doldu"
                degisti = True
            if u["ileti_bitis"] is not None and simdi >= u["ileti_bitis"]:
                u.update(ileti="", ileti_bitis=None)
                if u["durum"] == "cikarildi":
                    u["durum"] = "yok"
                degisti = True
            p = self._usb_pin
            if p is not None:
                if not self._usb_kilit_acilabilir() or (not p["istek"] and simdi - p["son_dokunma"] >= USB_PIN_BOSTA_SN):
                    self._usb_pin, degisti = None, True
                elif p["bekleme_bitis"] and simdi >= p["bekleme_bitis"]:
                    p["bekleme_bitis"], p["hata"], degisti = 0.0, "", True
            if (u["durum"] == "cevrimdisi" and self._usb_gizli is not None and not u.get("yeniden")
                    and self.istemci is not None and self.kayitli() and not self.cevrimdisi()):  # fmt: skip
                u["yeniden"], yeniden = True, True
        if yeniden:
            self._usb_tani_iste()
        elif degisti:
            self.yayinla()

    def _usb_kilit_acilabilir(self) -> bool:
        """"USB anahtarla aç" geçerli mi (çağıran kilidi tutar): tahta kilitli, sınav ve acil yok, anahtar tanınmış ve izinli."""
        return (
            self.kilitli and self._usb_gizli is not None and self.usb["durum"] == "tanindi"
            and "kilit_ac" in self.usb["izinler"] and self._sinav_aktif() is None
            and not (self.acil is not None and self.acil["bitis"] > time.time())
        )  # fmt: skip

    def _usb_kilit_iste(self):
        """Kilit ekranındaki "USB anahtarla aç": PIN gerekiyorsa PIN sayfası, değilse sunucuya onay isteği."""
        gonder = None
        with self.kilit:
            if self._usb_kilit_acilabilir() and not self._usb_kilit_suruyor and self._usb_pin is None:
                if self.usb["pin_gerek"]:
                    self._usb_pin = {"hata": "", "istek": False, "bekleme_bitis": 0.0, "son_dokunma": time.monotonic()}
                else:
                    self._usb_kilit_suruyor = True
                    gonder = self._usb_gizli
        self.yayinla()
        if gonder:
            self.arka_plan(lambda: self._usb_kilit_gonder(gonder, None))

    def _usb_pin_gir(self, pin):
        """usb-pin sayfasından PIN (yalnız sayfa açıkken). PIN saklanmaz, günlüğe yazılmaz."""
        pin = "".join(c for c in str(pin) if c in RAKAMLAR)[:7]
        gonder = None
        with self.kilit:
            p = self._usb_pin
            if p is None or p["istek"] or not self._usb_kilit_acilabilir():
                return
            simdi = time.monotonic()
            p["son_dokunma"] = simdi
            if simdi < p["bekleme_bitis"]:
                p["hata"] = f"Çok fazla hatalı deneme. {int(p['bekleme_bitis'] - simdi) + 1} saniye bekleyin."
            elif len(pin) != 6:
                p["hata"] = "PIN 6 hanelidir."
            else:
                p.update(istek=True, hata="")
                gonder = self._usb_gizli
        self.yayinla()
        if gonder:
            self.arka_plan(lambda: self._usb_kilit_gonder(gonder, pin))

    def _usb_kilit_gonder(self, gizli: tuple[str, str], pin):
        govde = {"kimlik": gizli[0], "gizli": gizli[1]}
        if pin:
            govde["pin"] = pin
        kod, yanit = self._yoklama_istek("/ajan/usb/kilit_ac", govde)
        del govde, pin
        with self.kilit:
            self._usb_kilit_suruyor = False
            p = self._usb_pin
            if p is not None:
                p["istek"] = False
            neden = yanit.get("neden") if isinstance(yanit.get("neden"), str) else ""
            hata = _kes(yanit.get("hata"), 200)
            if self._usb_gizli != gizli:
                pass  # bu arada bellek çıkarıldı: kilit açılmaz
            elif kod == 200 and yanit.get("tamam") is True:
                self._usb_pin = None
                if self._usb_kilit_acilabilir():
                    program = self._program_kilidi()
                    self._kilit_birak()
                    self.hatali_deneme = 0
                    self.olaylar.append(
                        "Program kilidi tahtadan USB anahtarla açıldı." if program else "Kilit tahtadan USB anahtarla açıldı."
                    )
                    self._kaydet()
            elif kod == 403 and neden == "pin_gerek":
                self.usb["pin_gerek"] = True  # ayar bu arada değişti
                self._usb_pin = {"hata": "", "istek": False, "bekleme_bitis": 0.0, "son_dokunma": time.monotonic()}
            elif kod == 403 and neden == "pin" and p is not None:
                p["hata"] = hata or usb_anahtar.ILETI_PIN_HATALI
            elif kod == 429 and neden == "bekle" and p is not None:
                p["bekleme_bitis"] = time.monotonic() + min(3600, max(1, _sayi(yanit.get("bekleme_sn")) or 120))
                p["hata"] = hata or "Çok fazla hatalı deneme. Biraz bekleyip yeniden deneyin."
            elif kod is None:
                if p is not None:
                    p["hata"] = "Sunucuya ulaşılamadı; yeniden deneyin."
                else:
                    self.usb.update(ileti=usb_anahtar.ILETI_CEVRIMDISI, ileti_bitis=time.monotonic() + USB_ILETI_SN)
            elif kod in (401, 403, 410, 423):
                self._usb_reddet(kod, yanit)
            else:  # 409 (kilit açma kapalı, sınav, özellik kapalı), 429 (tahta sınırı)
                self._usb_pin = None
                if neden == "kilit_kapali":
                    self.usb["izinler"] = [i for i in self.usb["izinler"] if i != "kilit_ac"]
                self.usb.update(ileti=hata or usb_anahtar.NEDEN_ILETISI.get(neden, ""), ileti_bitis=time.monotonic() + USB_ILETI_SN)
        self.yayinla()
        self.bildir()

    def _usb_yoklama_baslat(self, oturum: int, pin):
        """USB anahtarla yoklama oturumu: /ajan/usb/yoklama (yanıt /ajan/yoklama/baslat biçiminde)."""
        with self.kilit:
            y = self.yoklama
            if y is None or y["oturum"] != oturum:
                return
            gizli = self._usb_gizli if self.usb["durum"] == "tanindi" else None
            if gizli is None:
                metin = usb_anahtar.ILETI_SURESI_DOLDU if self.usb["durum"] == "suresi_doldu" else usb_anahtar.ILETI_CIKARILDI
                self._yoklama_ileti_ver(metin)
        if gizli is None:
            self.yayinla()
            return
        govde = {"kimlik": gizli[0], "gizli": gizli[1]}
        if pin:
            govde["pin"] = pin
        durum_kodu, yanit = self._yoklama_istek("/ajan/usb/yoklama", govde)
        del govde, pin
        kapatilacak, liste = None, None
        with self.kilit:
            y = self.yoklama
            belirtec = yanit.get("belirtec") if durum_kodu == 200 and isinstance(yanit.get("belirtec"), str) else None
            if y is None or y["oturum"] != oturum or y["asama"] not in ("yukleniyor", "pin"):
                kapatilacak = belirtec
            elif belirtec:
                liste = self._yoklama_oturum_acildi(y, yanit, oturum, belirtec)
                self.olaylar.append("Ders yoklaması oturumu USB anahtarla açıldı.")
            else:
                y["istek"] = False
                neden = yanit.get("neden") if isinstance(yanit.get("neden"), str) else ""
                hata = _kes(yanit.get("hata"), 200)
                if durum_kodu == 403 and neden == "pin_gerek":
                    self.usb["pin_gerek"] = True  # ayar bu arada değişti: PIN sorulur
                    y.update(asama="pin", hata="", son_dokunma=time.monotonic())
                elif durum_kodu == 403 and neden == "pin":
                    y.update(asama="pin", hata=hata or usb_anahtar.ILETI_PIN_HATALI)
                elif durum_kodu == 429 and neden == "bekle":
                    y["bekleme_bitis"] = time.monotonic() + min(3600, max(1, _sayi(yanit.get("bekleme_sn")) or 120))
                    y.update(asama="pin", hata=hata or "Çok fazla hatalı deneme. Biraz bekleyip yeniden deneyin.")
                elif durum_kodu in (401, 403, 410, 423):
                    kapatilacak = self._yoklama_ileti_ver(self._usb_reddet(durum_kodu, yanit), 8)
                elif durum_kodu == 409:
                    kapatilacak = self._yoklama_ileti_ver(hata or ILETI_YOKLAMA_KAPALI)
                elif durum_kodu is None and y["asama"] == "pin":
                    y["hata"] = "Sunucuya ulaşılamadı; yeniden deneyin."
                elif durum_kodu is None:
                    kapatilacak = self._yoklama_ileti_ver(ILETI_YOKLAMA_SUNUCU_YOK)
                else:
                    kapatilacak = self._yoklama_ileti_ver(hata or f"USB anahtar doğrulanamadı (HTTP {durum_kodu}).")
        self._yoklama_bitir_gonder(kapatilacak)
        self.yayinla()
        self.bildir()
        if liste:
            self._yoklama_liste_al(*liste)

    def _usb_gorunumu(self) -> dict | None:
        """Ekrana giden USB görünümü (çağıran kilidi tutar): gizli, kimlik, bağlama yolu, bellek etiketi GİRMEZ."""
        if not self.usb_etkin:
            return None
        u, p = self.usb, self._usb_pin
        simdi = time.monotonic()
        return {
            "durum": u["durum"],
            "tur": u["tur"],
            "etiket": u["etiket"],
            "kod": u["kod"],
            "pin_gerek": u["pin_gerek"],
            "izinler": list(u["izinler"]),
            "metin": usb_anahtar.ekran_metni(u),
            "kilit_ac": self._usb_kilit_acilabilir(),
            "bildirim_no": self._usb_bildirim_no if self._usb_bildirim_no != self._usb_bildirim_kapali else 0,
            "pin": (
                {"hata": p["hata"], "istek": p["istek"],
                 "bekleme": max(0, int(p["bekleme_bitis"] - simdi + 0.999)) if p["bekleme_bitis"] else 0}
                if p is not None else None
            ),  # fmt: skip
        }

    def usb_tani_bilgisi(self) -> dict:
        """Tanılama "USB anahtar" satırları için yalnız sayı ve evet/hayır (yol, etiket, hesap adı, kimlik YOK)."""
        with self.kilit:
            ozellik = "bildirmedi" if self.usb_etkin is None else ("acik" if self.usb_etkin else "kapali")
            return {"ozellik": ozellik, "izleme": self._usb_izleme_durumu, **{k: (dict(v) if isinstance(v, dict) else v)
                    for k, v in self._usb_tani.items()}}  # fmt: skip

    def gorunum(self) -> dict:
        with self.kilit:
            duyuru = self.duyuru
            if duyuru and duyuru["bitis"] <= time.time():
                self.duyuru = duyuru = None
            acil = self.acil
            if acil and acil["bitis"] <= time.time():
                self.acil = acil = None
            program = self._program_kilidi()
            return {
                "tur": "durum",
                "surum": __version__,
                "kilitli": self.kilitli,
                # Program kilidinde ekranda yalnız neden ve açılış saati görünür (şube, ders,
                # öğretmen yazılmaz; tahta herkese açık ekrandır).
                "kilit_kaynak": self.kilit_kaynak if self.kilitli else None,
                "kilit_neden": self.kilit_neden if program else "",
                "kilit_acilis": self.kilit_acilis if program else "",
                "duyuru": (
                    {
                        "baslik": duyuru["baslik"],
                        "metin": duyuru["metin"],
                        "kalan": max(0, int(duyuru["bitis"] - time.time())),
                        "kapatilabilir": duyuru["kapatilabilir"],
                    }
                    if duyuru
                    else None
                ),
                "kapatma": (
                    {"kalan": max(0, int(self.kapatma["bitis"] - time.time())), "neden": self.kapatma["neden"]}
                    if self.kapatma
                    else None
                ),
                # Oturum temizliği geri sayımı (K7): yalnız kalan süre; hesap ve dosya bilgisi yok.
                "temizlik": (
                    {"kalan": max(0, int(self.temizlik["bitis"] - time.time()))} if self.temizlik else None
                ),
                # Acil yayın yalnız gösterilecek metni taşır; tahtadan yalnız sunucuya
                # ulaşılamıyorken kapatılabilir (kural 3).
                "acil": (
                    {
                        "id": acil["id"],
                        "tur": acil["tur"],
                        "baslik": acil["baslik"],
                        "metin": acil["metin"],
                        "kalan": max(0, int(acil["bitis"] - time.time())),
                        "kapatilabilir": self.cevrimdisi(),
                    }
                    if acil
                    else None
                ),
                # Sınav kipi (A4): None ya da giriş/sınav ekranı görünümü. Gözetmen belirteci girmez.
                "sinav": self._sinav_gorunumu(),
                # Ders yoklaması (A5): None ya da yoklama sayfalarının görünümü. Belirteç girmez.
                "yoklama": self._yoklama_gorunumu(),
                "yoklama_etkin": bool(self.yoklama_etkin),
                "gun_programi": self._gun_programi_gorunumu(),
                "okul_adi": self.okul_adi,
                "kod_var": bool(self.kilit_kodu),
                "cevrimdisi": self.cevrimdisi(),
                "kayitli": self.kayitli(),
                "bekleme": max(0, int(self.bekleme_bitis - time.time())),
                # Görünüm: sır içermez (kilit kodu özeti, tahta anahtarı buraya girmez).
                "tema": self.tema or dict(ayar.VARSAYILAN_PALET),
                "logo_sha256": self.logo_sha,
                "tahta_adi": self.tahta_bilgi["ad"],
                "derslik": self.tahta_bilgi["derslik"],
                # Yüzer düğme (G3): görünecek işlemler; kilit kodu özeti GİTMEZ, yalnız var/yok sonucu.
                "dugme": self._dugme_gorunumu(),
                # USB anahtar (0.11.0): None (özellik kapalı) ya da durum, kısa ad/kod, izinler. Gizli değer GİRMEZ.
                "usb": self._usb_gorunumu(),
            }

    def _gun_programi_gorunumu(self):
        if self.gun_programi is not None and time.monotonic() < self.gun_programi_bitis:
            return self.gun_programi
        return None

    def _gun_programi_suresi_denetle(self) -> bool:
        """Günün programının ömrü (gecerli_sn; gece yarısı) dolduysa bellekten atar; True ise yayınlanmalı.

        Sunucuya ulaşılamazken yeni yanıt gelmez; ekran yardımcısı elindeki son durumu çizmeyi sürdürür.
        Bu yüzden süre dolduğunda bekçi bir kez yayın yapar (dünün programı kilit ekranında kalmasın).
        """
        with self.kilit:
            if self.gun_programi is None or time.monotonic() < self.gun_programi_bitis:
                return False
            self.gun_programi, self.gun_programi_bitis = None, 0.0
            return True

    def _oturum_gor(self, baslangic):
        """Ekran yardımcısı bağlandı: başlangıcı bilinen oturumdan yeniyse yeni oturum kimliği üretilir.

        Aynı yardımcının yeniden bağlanması (servis yeniden başladı, soket koptu) ya da güncellemede execv ile
        kendini yeniden başlatması aynı başlangıcı bildirir: oturum değişmez. Eski yardımcı alanı göndermez:
        oturum açılmaz (açılışta kilit uygulanmaz)."""
        if isinstance(baslangic, bool) or not isinstance(baslangic, (int, float)) or not 0 <= baslangic < 10**9:
            return
        baslangic = round(float(baslangic), 2)
        # Gelecekteki bir başlangıç kabul edilmez: büyük bir değer sonraki gerçek oturumları "eski" gösterip
        # açılışta kilidi o açılış boyunca kapatırdı (0.9.0 incelemesi).
        simdi = sistem.acik_sure_tam()
        if simdi is not None and baslangic > simdi + 2:
            gunluk.warning("Oturum başlangıcı reddedildi: açılış sayacından ileride.")
            return
        with self.kilit:
            if self.oturum is not None and baslangic <= self.oturum["baslangic"] + 1:
                return
            self.oturum = {"no": secrets.token_hex(6), "baslangic": baslangic}
            self._kaydet()
        gunluk.info("Yeni oturum (açılıştan %s sn sonra başladı).", int(baslangic))

    def oturum_ozeti(self) -> dict:
        with self.kilit:
            oturum = self.oturum
        if oturum is None:
            return {"oturum_no": None, "oturum_yasi_sn": None}
        simdi = sistem.acik_sure_tam()
        yas = None if simdi is None else max(0, int(simdi - oturum["baslangic"]))
        return {"oturum_no": oturum["no"], "oturum_yasi_sn": yas}

    def _dugme_gorunumu(self) -> dict:
        """Ekrana giden düğme görünümü (çağıran kilidi tutar ya da yalnız okur)."""
        d = self.dugme
        if not d or not d["acik"]:
            return {"acik": False, "islemler": [], "kilitle_kullanilabilir": False}
        return {"acik": True, "islemler": list(d["islemler"]), "kilitle_kullanilabilir": bool(self.kilit_kodu)}

    def dugme_tani_metni(self) -> str:
        """Tanılama satırı "Yüzer düğme": ayar ve bağlı yardımcıların desteği (hesap adı yok)."""
        with self.kilit:
            d = self.dugme
            yardimcilar = [e["bilgi"] for e in self.ekranlar.values() if e["bilgi"].get("arayuz") not in GORUNMEZ_ARAYUZ]
            kod = bool(self.kilit_kodu)
        if d is None:
            ayar_metni = "sunucu ayar göndermedi (eski sunucu ya da henüz bağlanmadı); düğme gösterilmez"
        elif not d["acik"]:
            ayar_metni = "kapalı (Ayarlar)"
        else:
            ayar_metni = "açık · " + ", ".join(d["islemler"])
            if "kilitle" in d["islemler"] and not kod:
                ayar_metni += " · Kilitle soluk (kilit kodu yok)"
        destek = sum(1 for b in yardimcilar if b.get("dugme"))
        bilesik = sum(1 for b in yardimcilar if b.get("bilesik"))
        return f"{ayar_metni} · ekran yardımcısı: {len(yardimcilar)} bağlı, {destek} düğmeli, {bilesik} bileşikli masaüstü"

    def kilit_tani_metni(self) -> str:
        """Tanılama satırı "Kilit durumu kalıcılığı" için servisin bellekteki kilit durumu."""
        with self.kilit:
            metin = "kilitli (" + ("program" if self._program_kilidi() else "idare") + ")" if self.kilitli else "açık"
        # Açılışta kilit (0.9.0): sunucu yeni oturumu bu yaşla görür; 120 sn'den yaşlıysa kilitlemez.
        yas = self.oturum_ozeti()["oturum_yasi_sn"]
        return metin + (" · oturum yok (yardımcı bu açılışta bağlanmadı)" if yas is None else f" · oturum {yas} sn önce başladı")

    def _etkin_oturumdan(self, no: int) -> bool:
        """Bağlantı ekrandaki oturumun görünür ekran yardımcısı mı? Kısa ömürlü komut istemcisi (`arayuz: komut`)
        ve arka plandaki başka bir hesabın süreci değildir. Kullanıcı kimliği çekirdekten okunur; etkin oturumun
        ya da bağlantının kimliği bilinemiyorsa (loginctl yok) denetim gevşer, düğme yine çalışır."""
        with self.kilit:
            ekran = self.ekranlar.get(no)
            if ekran is None or ekran["bilgi"].get("arayuz") in GORUNMEZ_ARAYUZ:
                return False
            uid = ekran.get("uid")
        etkin = sistem.etkin_oturum_uid()
        return uid is None or etkin is None or uid == etkin

    def dugme_islemi(self, islem: str) -> tuple[bool, str]:
        """Tahtadaki yüzer düğmeden gelen işlem (G3). Ayara ve tahtanın durumuna göre burada doğrulanır.

        Kilitle: idare kilidinin aynısıdır (süresiz, panelde "Kilitli"); kodla, panelden ya da sunucuya
        CEVRIMDISI_SN ulaşılamazsa kodsuz açılır. Kilit kodu yoksa kilitlemez: tahta panelden açılana dek
        kilitli kalırdı. Kapat / Yeniden başlat: ekrandaki 10 sn onaydan sonra gelir; olay önce bildirilir.
        Sunucuya hesap adı gitmez, yalnız hesap sınıfı (kural 6).
        """
        if islem not in DUGME_OLAYLARI:
            return False, ILETI_DUGME_AYAR
        sinif = sistem.etkin_oturum().get("sinif", "") or "bilinmiyor"
        with self.kilit:
            d = self.dugme
            if not d or not d["acik"] or islem not in d["islemler"]:
                return False, ILETI_DUGME_AYAR
            if self._sinav_aktif() is not None:
                return False, ILETI_DUGME_SINAV
            if self.acil is not None and self.acil["bitis"] > time.time():
                return False, ILETI_DUGME_ACIL
            olay = f"{DUGME_OLAYLARI[islem]} (oturum: {sinif})."
            if self.kilitli:
                # Düğme kilit ekranında gizlidir; buraya gelen istek ekrandan gelmemiştir. Süreli program
                # kilidi süresiz idare kilidine çevrilmez, kilitli tahta onaysız kapatılmaz.
                return (True, "Tahta zaten kilitli.") if islem == "kilitle" else (False, ILETI_DUGME_KILITLI)
            if islem == "kilitle":
                if not self.kilit_kodu:
                    return False, ILETI_DUGME_KOD_YOK
                self._kilit_birak()
                self.kilitli = True
                self.kilit_kaynak = "idare"
                self._kaydet()
            self.olaylar.append(olay)
        gunluk.info("Yüzer düğme: %s", olay)
        self.yayinla()
        self.bildir()
        if islem == "kilitle":
            return True, "Kilitlendi."
        islev = sistem.kapat if islem == "kapat" else sistem.yeniden_baslat
        self.zamanla(DUGME_GUC_GECIKME_SN, lambda: gunluk.info("%s (tahtadan): %s", islem, islev()))
        return True, "Komut alındı; üç saniye içinde uygulanacak."

    def marka_mesaji(self) -> dict:
        """Logo baytlarını ekran yardımcısına taşıyan satır (yardımcı root dosyasını okuyamaz)."""
        with self.kilit:
            logo, sha = self.logo, self.logo_sha
        if not logo:
            return {"tur": "marka", "sha256": None, "logo": None}
        return {"tur": "marka", "sha256": sha, "logo": base64.b64encode(logo).decode("ascii")}

    def _hedefler(self) -> list:
        """Yayın alacak ekran yardımcıları: kısa ömürlü komut istemcisine (`arayuz: komut`) yayın gitmez."""
        with self.kilit:
            return [e for e in self.ekranlar.values() if e["bilgi"].get("arayuz") != "komut"]

    def marka_yayinla(self):
        mesaj = self.marka_mesaji()
        for hedef in self._hedefler():
            hedef["gonder"](mesaj)

    def yayinla(self):
        mesaj = self.gorunum()
        for hedef in self._hedefler():
            hedef["gonder"](mesaj)

    def durum_ozeti(self, env: dict | None = None) -> dict:
        """Sunucuya giden durum. `env`: aynı istekte gönderilen envanter (özeti aynı olsun); verilmezse hesaplanır."""
        if env is None:
            env = self.envanter_al()
        with self.kilit:
            ekranlar = [dict(e["bilgi"]) for e in self.ekranlar.values() if e["bilgi"].get("arayuz") != "komut"]
            olaylar, self.olaylar = self.olaylar, []
        oturum = sistem.etkin_oturum()
        parca = urlsplit(self.yapi.get("sunucu", ""))
        ag = sistem.ag_bilgisi(parca.hostname or "", parca.port or 443) if parca.hostname else {}
        with self.kilit:
            acil = self.acil
            acil_id = acil["id"] if acil and acil["bitis"] > time.time() else None
        with self.kilit:
            kaynak = self.kilit_kaynak if self.kilitli else None
            neden = self.kilit_neden if self._program_kilidi() else ""
        return {
            "kilitli": self.kilitli,
            "kilit_kaynak": kaynak,
            "kilit_kalan": self.kilit_kalan(),
            "kilit_neden": neden,  # bilgi: "Teneffüs" | "Öğle arası" | "Bu saatte bu derslikte ders yok" | ""
            "duyuru_var": self.duyuru is not None,
            "kapatma_bekliyor": self.kapatma is not None,
            "temizlik_bekliyor": self.temizlik is not None or self._temizlik_suruyor,
            "yetenekler": list(YETENEKLER),
            "acil_id": acil_id,
            "sinav": self._sinav_durumu(),  # {kimlik, evre, yerel_kapali} | None — ad ve liste yok
            "yoklama_acik": self.yoklama_acik(),  # yalnız bayrak: şube, öğretmen, öğrenci yok (M4)
            # USB anahtar (0.11.0): yalnız izlemenin durumu; takılı bellek, etiket, kimlik GÖNDERİLMEZ.
            "usb_izleme": self._usb_izleme_durumu,
            "ekranlar": ekranlar,
            "oturum": oturum,
            "acik_sure": sistem.acik_sure(),
            "makine_adi": socket.gethostname(),
            "ip": ag.get("ip", ""),
            "mac": ag.get("mac", ""),
            "platform": sistem.platform_adi(),
            "olaylar": olaylar,
            # Açılışta kilit (0.9.0): oturum kimliği ve yaşı (açılış sayacıyla; tahta saatine dayanmaz).
            **self.oturum_ozeti(),
            # A6: bağlanılan adres, kayıtlı adres listesinin özeti, envanter özeti (envanter ancak istenince gider).
            "sunucu_adresi": self._etkin_adres or self.yapi.get("sunucu", ""),
            "adres_listesi_ozet": ayar.adres_listesi_ozet(self.yapi.get("sunucular") or []),
            "envanter_ozet": envanter.ozet(env) if env else "",
        }

    # ---- ekran yardımcısından gelenler -------------------------------------
    def ekran_mesaji(self, no: int, mesaj: dict):
        tur = mesaj.get("tur")
        if tur in ("merhaba", "ekran_durumu"):
            with self.kilit:
                if no in self.ekranlar:
                    bilgi = {k: v for k, v in mesaj.items() if k not in ("tur", "oturum_baslangic")}
                    self.ekranlar[no]["bilgi"].update(bilgi)
            if tur == "merhaba" and mesaj.get("arayuz") not in GORUNMEZ_ARAYUZ and self._etkin_oturumdan(no):
                self._oturum_gor(mesaj.get("oturum_baslangic"))
            if tur == "merhaba" and mesaj.get("arayuz") != "komut" and mesaj.get("surum") not in (None, __version__):
                # Güncellemeden sonra eski sürümlü yardımcı kendini yeniden başlatır.
                self.ekranlar[no]["gonder"]({"tur": "yeniden_baslat"})
            self.bildir()
        elif tur == "kod":
            self._kod_dene(str(mesaj.get("kod", "")))
        elif tur in ("yerel_kilitle", "yerel_kapat", "yerel_yeniden_baslat"):
            # Yüzer düğme (G3): ekran yalnız ister; ayar, durum ve isteğin kaynağı burada denetlenir.
            if self._etkin_oturumdan(no):
                basarili, metin = self.dugme_islemi(tur[len("yerel_"):])
            else:
                basarili, metin = False, ILETI_DUGME_YETKI
                gunluk.warning("Yüzer düğme isteği reddedildi (no %s): ekrandaki oturumun yardımcısı değil.", no)
            with self.kilit:
                hedef = self.ekranlar.get(no)
            if hedef:
                hedef["gonder"]({"tur": "dugme_sonuc", "islem": tur[len("yerel_"):], "basarili": basarili, "mesaj": metin})
        elif tur == "cevrimdisi_ac":
            # Tek çevrimdışı düğmesi: yalnız sunucuya ulaşılamıyorken kilidi açar ve acil
            # yayını kapatır (kural 3). Sunucu dönünce yayın sürüyorsa yeniden gelir.
            if self.cevrimdisi() or not self.kayitli():
                with self.kilit:
                    if self.kilitli:
                        self.olaylar.append("Kilit sunucuya ulaşılamadığı için tahtadan açıldı.")
                    if self.acil:
                        self.olaylar.append("Acil yayın sunucuya ulaşılamadığı için tahtadan kapatıldı.")
                    sinav = self._sinav_aktif()
                    if sinav is not None:
                        # Yalnız çevrimdışılık sürdükçe geçerli: ilk başarılı yanıtta sıfırlanır ve sınav
                        # hâlâ sürüyorsa ekran geri gelir.
                        self.sinav_yerel_kapali = sinav["kimlik"]
                        self._gozetmen_kapat()
                        self.olaylar.append("Sınav ekranı sunucuya ulaşılamadığı için tahtadan kapatıldı.")
                    self._kilit_birak()
                    self.acil = None
                    self._kaydet()
                self.yayinla()
        elif tur == "kapatma_iptal":
            with self.kilit:
                iptal = self.kapatma is not None
                self.kapatma = None
                if iptal:
                    self.olaylar.append("Otomatik kapatma tahtadan iptal edildi (tahta kullanılıyor).")
                # Kapatma uyarısı bekleyen temizliğin geri sayımını örtüyordu: "tahta kullanılıyor" kararı onu da
                # kapsar (temizlik uyarısı hiç görülmeden çalışmasın).
                bekleyen, self.temizlik = self.temizlik, None
                if bekleyen:
                    self.sonuclar.append({
                        "komut_id": bekleyen["komut_id"], "basarili": True,
                        "cikti": "Vazgeçildi: tahtayı kullanan kişi kapatma uyarısında Vazgeç'e dokundu (tahta kullanılıyor).",
                    })  # fmt: skip
            self.yayinla()
            self.bildir()
        elif tur == "temizlik_iptal":
            with self.kilit:
                bekleyen, self.temizlik = self.temizlik, None
                if bekleyen:
                    self.sonuclar.append({
                        "komut_id": bekleyen["komut_id"], "basarili": True,
                        "cikti": "Vazgeçildi: tahtayı kullanan kişi temizliği iptal etti (tahta kullanılıyor).",
                    })  # fmt: skip
            self.yayinla()
            self.bildir()
        elif tur == "pencere_sonucu":
            # Ekran yardımcısının pencere kapatma yanıtı (yalnız sayılar); bekleyen temizlik yoksa yok sayılır.
            with self.kilit:
                olay = self._pencere_olayi
                if olay is not None:
                    self._pencere_sonucu = {
                        k: (str(mesaj[k])[:80] if k == "hata" else _sayi(mesaj[k]))
                        for k in ("istenen", "atlanan", "hata") if k in mesaj
                    }  # fmt: skip
            if olay is not None:
                olay.set()
        elif tur == "duyuru_kapat":
            with self.kilit:
                if self.duyuru and self.duyuru["kapatilabilir"]:
                    self.duyuru = None
                    self.olaylar.append("Duyuru tahtadan kapatıldı.")
            self.yayinla()
            self.bildir()
        # ---- gözetmen (A4): yalnız sınav ekranı açıkken anlamlıdır --------------------------
        elif tur == "gozetmen_kod":
            self._gozetmen_kod(str(mesaj.get("kod", "")))
        elif tur == "gozetmen_yoklama":
            self._gozetmen_yoklama_ac()
        elif tur == "gozetmen_kaydet":
            self._gozetmen_kaydet(mesaj.get("gelmeyen"))
        elif tur == "gozetmen_cikis":
            with self.kilit:
                self._gozetmen_kapat()
                self.gozetmen_hata = ""
            self.yayinla()
        # "gozetmen_sinavi_kapat" sonraya bırakıldı (açık soru): bilinmeyen ileti yok sayılır.
        # ---- ders yoklaması (A5): ekran yardımcısı ve `tahta-ajan yoklama` kısayolu --------------
        elif tur == "yoklama_ac":
            self._yoklama_ac()
        elif tur == "yoklama_pin":
            self._yoklama_pin(mesaj.get("kod", ""), mesaj.get("pin", ""))
        elif tur == "yoklama_sec":
            self._yoklama_sec(mesaj)
        elif tur == "yoklama_isaret":
            self._yoklama_isaret(mesaj.get("id"))
        elif tur == "yoklama_kaydet":
            self._yoklama_asama("liste", "onay")
        elif tur == "yoklama_geri":
            self._yoklama_asama("onay", "liste")
        elif tur == "yoklama_onayla":
            self._yoklama_onayla()
        elif tur == "yoklama_kod_pin":
            # "Başka öğretmen (kod ve PIN)": takılı anahtar bu yoklamada yok sayılır.
            with self.kilit:
                y = self.yoklama
                if y is not None and y["usb"] and y["asama"] == "pin" and not y["istek"]:
                    y.update(usb=False, hata="", son_dokunma=time.monotonic())
            self.yayinla()
        # ---- USB anahtar (0.11.0): yetki bellekten gelir, iletiden değil (bellek takılı ve tanınmışken etkili) ----
        elif tur in ("usb_kilit_ac", "usb_pin"):
            # Kilit açma yalnız ekrandaki oturumun görünür yardımcısından (yüzer düğmeyle aynı daraltma, 0.9.0):
            # anahtar tanınmışken arka plandaki başka bir hesabın süreci ya da komut istemcisi kilidi açamasın.
            if not self._etkin_oturumdan(no):
                gunluk.warning("USB kilit açma isteği reddedildi (no %s): ekrandaki oturumun yardımcısı değil.", no)
            elif tur == "usb_kilit_ac":
                self._usb_kilit_iste()
            else:
                self._usb_pin_gir(mesaj.get("pin", ""))
        elif tur == "usb_vazgec":
            with self.kilit:
                self._usb_pin = None
            self.yayinla()
        elif tur == "usb_bildirim_kapat":
            with self.kilit:
                no = mesaj.get("bildirim_no")
                if _tamsayi_mi(no) and no == self._usb_bildirim_no:
                    self._usb_bildirim_kapali = no
            self.yayinla()
        elif tur == "yoklama_kapat":
            with self.kilit:
                belirtec = self._yoklama_kapat()
            self._yoklama_bitir_gonder(belirtec)
            self.yayinla()
            self.bildir()
        # ---- arıza bildirimi (A6): kısa ömürlü arıza penceresi (`arayuz: komut`) ----------------
        elif tur == "ariza":
            basarili, metin = self.ariza_bildir(mesaj.get("kategori"), mesaj.get("aciklama"))
            with self.kilit:
                hedef = self.ekranlar.get(no)
            if hedef:
                # Pencereye yalnız sonuç iletisi gider (sır ve kuyruk içeriği gitmez; kural 5).
                hedef["gonder"]({"tur": "ariza_sonuc", "basarili": basarili, "mesaj": metin})

    # ---- arıza bildirimi (A6) ----------------------------------------------------------
    def ariza_bildir(self, kategori, aciklama) -> tuple[bool, str]:
        """Tahtadan arıza kaydı: denetler, kuyruğa yazar, sunucuya hemen iletmeyi dener.

        Sunucu en çok ARIZA_ONAY_BEKLEME_SN içinde `ariza_alindi` ile aldığını söylerse "iletildi",
        demezse "tahtada bekletiliyor" denir; kayıt kuyrukta kalır ve sonraki bağlantıda iletilir.
        """
        kategori = str(kategori or "")
        if kategori not in ARIZA_KATEGORILERI:
            return False, ILETI_ARIZA_KATEGORI
        if not self.kayitli() or self.onay_bekliyor:
            return False, ILETI_ARIZA_KAYITSIZ
        aciklama = ariza_aciklamasi(aciklama)
        sinif = sistem.etkin_oturum().get("sinif", "")  # yalnız hesap SINIFI (kural 6)
        with self.kilit:
            simdi = time.monotonic()
            while self._ariza_zamanlari and simdi - self._ariza_zamanlari[0] >= 3600:
                self._ariza_zamanlari.popleft()
            if len(self._ariza_zamanlari) >= ARIZA_SAATLIK_EN_COK:
                return False, ILETI_ARIZA_SINIR
            self._ariza_kuyrugu_buda()
            if len(self.ariza_kuyrugu) >= ARIZA_KUYRUK_EN_COK:
                return False, ILETI_ARIZA_KUYRUK
            yerel_id = secrets.token_hex(8)
            self.ariza_kuyrugu.append({
                "yerel_id": yerel_id, "kategori": kategori, "aciklama": aciklama,
                "oturum_sinifi": sinif, "tahta_zamani": int(time.time()),
            })  # fmt: skip
            self._ariza_zamanlari.append(simdi)
            olay = threading.Event()
            self._ariza_olaylari[yerel_id] = olay
            self._kaydet()
        self.bildir()
        iletildi = olay.wait(ARIZA_ONAY_BEKLEME_SN)
        with self.kilit:
            self._ariza_olaylari.pop(yerel_id, None)
        return True, ILETI_ARIZA_ILETILDI if iletildi else ILETI_ARIZA_BEKLIYOR

    def _ariza_kuyrugu_buda(self):
        """7 günden eski bekleyen bildirimleri atar (çağıran self.kilit'i tutar)."""
        sinir = time.time() - ARIZA_OMUR_SN
        eski = [a for a in self.ariza_kuyrugu if a["tahta_zamani"] < sinir]
        if eski:
            self.ariza_kuyrugu = [a for a in self.ariza_kuyrugu if a["tahta_zamani"] >= sinir]
            self.olaylar.append(f"{len(eski)} arıza bildirimi 7 gün içinde sunucuya iletilemediği için silindi.")
            self._kaydet()

    def _gonderilecek_arizalar(self) -> list[dict]:
        with self.kilit:
            self._ariza_kuyrugu_buda()
            return [dict(a) for a in self.ariza_kuyrugu[:ARIZA_KUYRUK_EN_COK]]

    # ---- envanter (A6) ---------------------------------------------------------------
    def donanim_tazele(self, zorla: bool = False):
        """Ham donanım okumalarını açılışta ve 6 saatte bir (ya da `envanter` komutunda) yeniler."""
        with self._donanim_kilidi:
            if not zorla and self._donanim is not None and time.monotonic() - self._donanim_zamani < ENVANTER_YENILEME_SN:
                return
            try:
                ham = sistem.donanim_bilgisi()
            except Exception:  # envanter hiçbir koşulda ajanı düşürmez
                gunluk.exception("Donanım bilgisi okunamadı")
                ham = {}
            self._donanim, self._donanim_zamani = ham, time.monotonic()

    def envanter_al(self) -> dict | None:
        """Gönderilecek envanter (§5.4); donanım henüz okunmadıysa None."""
        if self._donanim is None:
            return None
        with self.kilit:
            ekranlar = [dict(e["bilgi"]) for e in self.ekranlar.values() if e["bilgi"].get("arayuz") not in GORUNMEZ_ARAYUZ]
        return envanter.topla(self._donanim, envanter.ekran_cozunurlugu(ekranlar))

    def _istek_govdesi(self, sonuclar: list, bekle: int, komut_al: bool = True) -> dict:
        """`/ajan/bekle` gövdesi: durum + (varsa) bekleyen arızalar + (istendiyse) envanter."""
        env = self.envanter_al()
        govde = {"surum": __version__, "durum": self.durum_ozeti(env), "sonuclar": sonuclar, "bekle": bekle}
        if not komut_al:
            govde["komut_al"] = False
        arizalar = self._gonderilecek_arizalar()
        if arizalar:
            govde["arizalar"] = arizalar
        ozet = govde["durum"]["envanter_ozet"]
        if komut_al and env is not None and self._envanter_iste and (
            ozet != self._envanter_gonderilen
            or time.monotonic() - self._envanter_gonderim_zamani >= ENVANTER_YENIDEN_SN
        ):
            govde["envanter"] = env
        return govde

    def _altyapi_yanit(self, yanit: dict, govde: dict):
        """Yanıttaki `ariza_alindi` (kuyruktan sil) ve `envanter_iste` alanlarını işler (eski sunucuda yoklar)."""
        alinan = yanit.get("ariza_alindi")
        if isinstance(alinan, list):
            alinan = {str(a) for a in alinan}
            with self.kilit:
                once = len(self.ariza_kuyrugu)
                self.ariza_kuyrugu = [a for a in self.ariza_kuyrugu if a["yerel_id"] not in alinan]
                if len(self.ariza_kuyrugu) != once:
                    self._kaydet()
                for yerel_id in alinan:
                    olay = self._ariza_olaylari.get(yerel_id)
                    if olay:
                        olay.set()
        if "envanter" in govde:
            self._envanter_gonderilen = govde["durum"].get("envanter_ozet")
            self._envanter_gonderim_zamani = time.monotonic()
        if "envanter_iste" in yanit:
            self._envanter_iste = bool(yanit["envanter_iste"])

    def _kod_dene(self, kod: str):
        if self.sinav_ekrani_acik():
            # Sınav ekranında ortak kilit kodu kabul edilmez (kod öğrencilerce görülebilir); deneme
            # sayılmaz. Sınav ekranı panelden, gözetmen koduyla değil, süre bitince ya da kural 3 ile kalkar.
            self.yayinla()
            return
        with self.kilit:
            if time.time() < self.bekleme_bitis or not self.kilit_kodu:
                pass
            else:
                beklenen = self.kilit_kodu
                ozet = hashlib.pbkdf2_hmac(
                    "sha256", kod.encode("utf-8"), bytes.fromhex(beklenen["tuz"]), int(beklenen["tur"])
                ).hex()
                if hmac.compare_digest(ozet, beklenen["ozet"]):
                    program = self._program_kilidi()
                    self._kilit_birak()
                    self.hatali_deneme = 0
                    self.olaylar.append(
                        "Program kilidi tahtadan kodla açıldı." if program else "Kilit tahtadan kodla açıldı."
                    )
                    self._kaydet()
                else:
                    self.hatali_deneme += 1
                    if self.hatali_deneme >= KOD_DENEME_SINIRI:
                        self.hatali_deneme = 0
                        self.bekleme_bitis = time.time() + KOD_BEKLEME_SN
                        self.olaylar.append("Kilit kodu art arda hatalı girildi; giriş bir dakika durduruldu.")
        self.yayinla()
        self.bildir()

    # ---- komutlar ----------------------------------------------------------
    def komut_uygula(self, komut: dict) -> tuple[bool, str] | None:
        """Komutu uygular: (başarılı, çıktı). None: sonuç sonra gelecek (oturum temizliği)."""
        tur = komut.get("tur")
        veri = komut.get("veri") or {}
        if tur == "kilitle":
            if veri.get("kaynak") == "program":
                return self._program_kilitle(veri)
            with self.kilit:
                # İdare kilidi süresizdir; program kilidinin üstüne gelirse onu ezer.
                self._kilit_birak()
                self.kilitli = True
                self.kilit_kaynak = "idare"
                self._kaydet()
            self.yayinla()
            return True, self._ekran_notu("Kilitlendi.")
        if tur == "kilit_ac":
            with self.kilit:
                if veri.get("kaynak") == "program" and not self._program_kilidi():
                    # Program açması idarenin elle koyduğu kilide dokunmaz.
                    neden = "İdare kilidi var" if self.kilitli else "Program kilidi yok"
                    return True, f"{neden}; uygulanmadı."
                self._kilit_birak()
                self._kaydet()
            self.yayinla()
            return True, "Kilit açıldı."
        if tur == "duyuru":
            kimlik = veri.get("duyuru_id")
            with self.kilit:
                # Tek duyuru tutulur: sonra gelen öncekinin yerine geçer.
                self.duyuru = {
                    "id": kimlik if isinstance(kimlik, int) and not isinstance(kimlik, bool) else None,
                    "baslik": str(veri.get("baslik", ""))[:200],
                    "metin": str(veri.get("metin", ""))[:4000],
                    "bitis": time.time() + max(5, int(veri.get("sure_sn", 60))),
                    "kapatilabilir": bool(veri.get("kapatilabilir", True)),
                }
                acil_suruyor = self.acil is not None
            self.yayinla()
            if acil_suruyor:
                return True, "Duyuru alındı; acil yayın bitince kalan süresiyle görünecek."
            return True, self._ekran_notu("Duyuru gösterildi.")
        if tur == "duyuru_kaldir":
            kimlik = veri.get("duyuru_id")
            with self.kilit:
                if kimlik is not None and (self.duyuru is None or self.duyuru.get("id") != kimlik):
                    # Panelde durdurulan yayın artık ekranda değil (yerine başka duyuru geçti).
                    return True, "Ekrandaki duyuru başka; dokunulmadı."
                self.duyuru = None
            self.yayinla()
            return True, "Duyuru kaldırıldı."
        if tur == "tani":
            parca = urlsplit(self.yapi.get("sunucu", ""))
            with self.kilit:
                ekranlar = [dict(e["bilgi"]) for e in self.ekranlar.values()]
            rapor = tani.topla(
                parca.hostname or "", parca.port or 443, self.sunucu_saat, ekranlar, self.sinav_tani_metni(),
                sunucular=ayar.adres_sirasi(self.yapi), kilit=self.kilit_tani_metni(), dugme=self.dugme_tani_metni(),
                usb=self.usb_tani_bilgisi(),
            )
            return True, json.dumps(rapor, ensure_ascii=False)
        if tur == "guncelle":
            return self._guncelle(veri)
        if tur == "envanter":
            # Çıktı envanterin kendisidir; sunucu onu saklar ("Envanter alındı."). Özet aynı önbellekten.
            self.donanim_tazele(zorla=True)
            env = self.envanter_al() or envanter.topla({})
            self._envanter_gonderilen = envanter.ozet(env)
            self._envanter_gonderim_zamani = time.monotonic()
            return True, json.dumps(env, ensure_ascii=False)
        if tur == "temizlik":
            return self._temizlik_baslat(komut.get("id"), veri)
        if tur == "kapat" and int(veri.get("uyari_sn", 0) or 0) > 0:
            # Uyarılı (otomatik) kapatma acil yayın sürerken uygulanmaz: bilinçli atlama,
            # hata değildir. Panelden verilen uyarısız kapatma ise her durumda uygulanır.
            if self.acil is not None and self.acil["bitis"] > time.time():
                return True, "Acil yayın sürüyor; otomatik kapatma uygulanmadı."
            if self.sinav_ekrani_acik():
                return True, "Sınav sürüyor; otomatik kapatma uygulanmadı."
            # Uyarılı kapatma: tahta kullanılıyorsa (kilitli değil ve ekranı varsa)
            # önce geri sayım gösterilir; kullanan kişi vazgeçebilir. Kilitli ya da
            # oturumsuz tahtada uyaracak kimse yoktur, doğrudan kapanır. Yoklama açıkken tahta
            # kilitli olsa da kullanılıyordur (A5): önce uyarı gösterilir.
            with self.kilit:
                gorunur = any(e["bilgi"].get("arayuz") not in GORUNMEZ_ARAYUZ for e in self.ekranlar.values())
                if gorunur and (not self.kilitli or self.yoklama_acik()):
                    self.kapatma = {
                        "bitis": time.time() + min(600, int(veri["uyari_sn"])),
                        "neden": str(veri.get("neden", ""))[:200],
                    }
            if self.kapatma:
                self.yayinla()
                return True, "Kapatma uyarısı gösterildi; vazgeçilmezse süre sonunda kapanacak."
        if tur in ("kapat", "yeniden_baslat"):
            # Sonuç önce bildirilir; makine kapanınca bildirecek kimse kalmaz.
            islev = sistem.kapat if tur == "kapat" else sistem.yeniden_baslat
            threading.Timer(3.0, lambda: gunluk.info("%s: %s", tur, islev())).start()
            return True, "Komut alındı; üç saniye içinde uygulanacak."
        return False, f"Bilinmeyen komut: {tur}"

    def _program_kilitle(self, veri: dict) -> tuple[bool, str]:
        """Süreli program kilidi. İdare kilidinin üstüne uygulanmaz (bilinçli atlama)."""
        try:
            sure = int(veri.get("sure_sn") or 0)
        except (TypeError, ValueError):
            sure = 0
        if sure <= 0:
            return True, "Kilit süresi geçmiş; uygulanmadı."
        sure = min(sure, PROGRAM_KILIDI_EN_UZUN_SN)
        neden = str(veri.get("neden") or "")
        neden = neden if neden in PROGRAM_NEDENLERI else "Teneffüs"
        acilis = str(veri.get("acilis") or "")
        acilis = acilis if _saat_gecerli(acilis) else ""
        with self.kilit:
            if self.kilitli and self.kilit_kaynak != "program":
                return True, "Zaten idare kilidinde; uygulanmadı."
            self.kilitli = True
            self.kilit_kaynak = "program"
            self.kilit_bitis = time.monotonic() + sure
            self.kilit_neden = neden
            self.kilit_acilis = acilis
            self._kaydet()
        self.yayinla()
        return True, self._ekran_notu(f"Program kilidi: {neden}, {sure // 60} dk.")

    # ---- oturum temizliği (K7) ---------------------------------------------------------------
    def _temizlik_baslat(self, komut_id, veri: dict) -> tuple[bool, str] | None:
        """Temizliği başlatır. Hemen sonuçlanan durumlarda (atlama) sonuç döner; temizlik başladıysa None
        döner ve sonuç temizlik bitince (ya da vazgeçilince) `sonuclar`a eklenir (komut "iletildi" kalır).

        Yalnız ORTAK hesapta (ogretmen/ogrenci) çalışır; etapadmin ve kişisel hesapta asla. Kullanılan
        tahtada (ekran var, kilitli değil) önce 60 sn geri sayım ve Vazgeç gösterilir; kilitli ya da
        ekransız tahtada uyarısız çalışır (kapatma uyarısıyla aynı kural).
        """
        if self.acil is not None and self.acil["bitis"] > time.time():
            return True, "Atlandı: acil yayın sürüyor."
        if self.sinav_ekrani_acik():
            return True, "Atlandı: sınav sürüyor."
        if self.yoklama_acik():
            return True, "Atlandı: ders yoklaması açık (tahta kullanılıyor)."
        hesaplar = veri.get("hesaplar")
        izinli = [str(h) for h in hesaplar] if isinstance(hesaplar, list) else None
        if sistem.ortak_oturum(izinli) is None:
            return True, "Atlandı: oturum ortak hesap değil (yalnız öğretmen/öğrenci hesabı temizlenir)."
        with self.kilit:
            if self.temizlik is not None or self._temizlik_suruyor:
                return True, "Atlandı: temizlik zaten sürüyor."
            gorunur = any(e["bilgi"].get("arayuz") not in GORUNMEZ_ARAYUZ for e in self.ekranlar.values())
            if gorunur and not self.kilitli:
                self.temizlik = {"komut_id": komut_id, "bitis": time.time() + TEMIZLIK_UYARI_SN, "izinli": izinli}
                uyarili = True
            else:
                self._temizlik_suruyor = True
                uyarili = False
        if uyarili:
            self.yayinla()
            self.bildir()
        else:
            self.arka_plan(lambda: self._temizlik_yap(komut_id, izinli))
        return None

    def _temizlik_suresi_denetle(self) -> bool:
        """Geri sayımı biten temizliği başlatır (bekçi çağırır); başlattıysa True."""
        with self.kilit:
            if self.temizlik is not None and self.kapatma is not None:
                # Kapatma uyarısı ekrandayken temizlik geri sayımı görünmez: süre durur; kapatma kalkınca temizlik
                # uyarısı baştan (60 sn) gösterilir.
                self.temizlik["bitis"] = max(self.temizlik["bitis"], time.time() + TEMIZLIK_UYARI_SN)
                return False
            if self.temizlik is None or self.temizlik["bitis"] > time.time():
                return False
            bekleyen, self.temizlik = self.temizlik, None
            self._temizlik_suruyor = True
        self.yayinla()
        self.arka_plan(lambda: self._temizlik_yap(bekleyen["komut_id"], bekleyen.get("izinli")))
        return True

    def _temizlik_yap(self, komut_id, izinli=None):
        """Adımları sırayla yapar ve sonucu ekler. Hiçbir adımın hatası diğerini durdurmaz."""
        try:
            basarili, cikti = self._temizlik_adimlari(izinli)
        except Exception as hata:  # rapor her durumda gider
            gunluk.exception("Oturum temizliği başarısız")
            basarili, cikti = False, f"Hata: {type(hata).__name__}"
        with self.kilit:
            self._temizlik_suruyor = False
            self.sonuclar.append({"komut_id": komut_id, "basarili": basarili, "cikti": cikti[:600]})
        self.bildir()

    def _temizlik_adimlari(self, izinli=None) -> tuple[bool, str]:
        from . import temizlik

        kuru = os.environ.get("TAHTA_AJAN_BENZETIM") == "1"
        # Oturum geri sayım sırasında değişmiş olabilir: yeniden denetlenir.
        oturum = sistem.ortak_oturum(izinli)
        if oturum is None:
            return True, "Atlandı: oturum ortak hesap değil (yalnız öğretmen/öğrenci hesabı temizlenir)."
        parcalar = []
        if oturum.get("tur") != "x11":
            parcalar.append("Pencereler: atlandı (yalnız X11 oturumunda yapılır)")
        else:
            parcalar.append(temizlik.pencere_ozeti(self._pencereleri_kapat(kuru, oturum.get("uid")), kuru))
        sonuc = sistem.tarayici_temizligi(oturum, kuru)
        parcalar.append(temizlik.tarayici_ozeti(sonuc))
        if kuru:
            parcalar.append("BENZETİM: hiçbir şey kapatılmadı ve silinmedi")
        hatali = bool(sonuc.get("hata_metni")) or bool(sonuc.get("hata")) \
            or bool((sonuc.get("surecler") or {}).get("kalan_aileler"))  # fmt: skip
        return not hatali, ("Tamamlandı" if not hatali else "Kısmen yapıldı") + " · " + " · ".join(parcalar)

    def _pencereleri_kapat(self, kuru: bool, uid=None) -> dict | None:
        """Temizlenen oturumun (kullanıcı kimliği `uid`) görünür ekran yardımcısından pencere kapatmayı ister
        ve yanıtını en çok 15 sn bekler. Kullanıcı değiştirmede arka planda açık kalan etapadmin ya da
        kişisel oturumun yardımcısı da bağlı olabilir: kimliği eşleşmeyen yardımcıya istek GİTMEZ."""
        if uid is None:
            return {"hata": "oturumun kullanıcı kimliği bilinmiyor"}
        with self.kilit:
            hedef = next(
                (e for e in self.ekranlar.values()
                 if e["bilgi"].get("arayuz") not in GORUNMEZ_ARAYUZ and e.get("uid") == uid), None
            )  # fmt: skip
            if hedef is None:
                return {"hata": "oturumun ekran yardımcısı bağlı değil"}
            olay = self._pencere_olayi = threading.Event()
            self._pencere_sonucu = None
        hedef["gonder"]({"tur": "pencereleri_kapat", "kuru": kuru, "uid": uid})
        olay.wait(TEMIZLIK_PENCERE_BEKLEME_SN)
        with self.kilit:
            sonuc, self._pencere_sonucu, self._pencere_olayi = self._pencere_sonucu, None, None
        return sonuc

    def _ekran_notu(self, metin: str) -> str:
        if not self._gorunur_ekran_var():
            return metin + " (Uyarı: bağlı ekran yardımcısı yok; ekranda görünmüyor olabilir.)"
        return metin

    def _guncelle(self, veri: dict) -> tuple[bool, str]:
        beklenen = str(veri.get("sha256", ""))
        if veri.get("surum") == __version__:
            return True, "Zaten güncel."
        try:
            kod, icerik, _ = self.istemci.istek("GET", "/ajan/paket", zaman_asimi=60, ham=True)
        except BaglantiHatasi as hata:
            return False, f"Paket indirilemedi: {hata}"
        if kod != 200:
            return False, f"Paket indirilemedi: HTTP {kod}"
        if not beklenen or hashlib.sha256(icerik).hexdigest() != beklenen:
            return False, "Paket özeti tutmuyor; kurulmadı."
        hedef = ayar.durum_dizini() / "tahta-ajan.deb"
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_bytes(icerik)
        return sistem.paket_kur(str(hedef))

    # ---- sunucu döngüsü ------------------------------------------------------
    def _istemci_kur(self):
        """ajan.json'u okur ve etkin adrese istemci kurar.

        Etkin adres önce birincildir ("sunucu"); art arda 3 bağlantı hatasında listedeki sıradakine
        geçilir (_adres_hatasi). Birincil dışarıdan değişirse (`tahta-ajan sunucu ADRES`) ona dönülür.
        """
        self.yapi = ayar.oku()
        sira = ayar.adres_sirasi(self.yapi)
        if not sira:
            self.istemci = None
            return
        if sira[0] != self._birincil_son or self._etkin_adres not in sira:
            self._birincil_son, self._etkin_adres, self._adres_hata = sira[0], sira[0], 0
        self.istemci = Istemci(
            self._etkin_adres, self.yapi.get("parmak_izi", ""), self.yapi.get("tahta_id"), self.yapi.get("anahtar", "")
        )

    def _adres_hatasi(self):
        """Bağlantı hatası (parmak izi dahil) sayar; eşikte listedeki sıradaki adrese geçer."""
        sira = ayar.adres_sirasi(self.yapi)
        self._adres_hata += 1
        if self._adres_hata < ADRES_HATA_ESIGI or len(sira) < 2:
            return
        konum = sira.index(self._etkin_adres) if self._etkin_adres in sira else -1
        self._etkin_adres = sira[(konum + 1) % len(sira)]
        self._adres_hata = 0
        gunluk.warning("Sunucuya %s kez ulaşılamadı; sıradaki adres denenecek: %s", ADRES_HATA_ESIGI, self._etkin_adres)

    def _adres_basarili(self):
        """Birincil olmayan adreste ilk başarılı yanıt: o adres kalıcı olarak birincil olur."""
        self._adres_hata = 0
        if not self._etkin_adres or self._etkin_adres == self.yapi.get("sunucu"):
            return
        yapi = ayar.oku()
        if not yapi.get("sunucu"):
            return
        yapi["sunucu"] = self._etkin_adres
        try:
            ayar.yaz(yapi)
        except OSError as hata:
            gunluk.warning("ajan.json yazılamadı: %s", hata)
            return
        self.yapi = yapi
        self._birincil_son = self._etkin_adres
        with self.kilit:
            self.olaylar.append(f"Sunucuya yeni adresten ulaşıldı: {self._etkin_adres}")

    def _adres_listesi_isle(self, deger):
        """Sunucunun bildirdiği adres listesi (durum tabanlı; anahtar yoksa dokunulmaz, boşsa silinmez)."""
        liste = ayar.adresler_dogrula(deger)
        if not liste or liste == self.yapi.get("sunucular"):
            return
        yapi = ayar.oku()
        if not yapi.get("sunucu"):
            return
        yapi["sunucular"] = liste
        try:
            ayar.yaz(yapi)
        except OSError as hata:
            gunluk.warning("ajan.json yazılamadı: %s", hata)
            return
        self.yapi = yapi
        gunluk.info("Sunucu adres listesi güncellendi (%s adres).", len(liste))

    def _yanit_isle(self, yanit: dict):
        ayarlar = yanit.get("ayar") or {}
        degisti = False
        with self.kilit:
            # Tahtadan (çevrimdışıyken) kapatılan sınav yalnız çevrimdışılık sürdükçe kapalı kalır.
            yerel_sifirlandi = self.sinav_yerel_kapali is not None
            self.sinav_yerel_kapali = None
            self.sunucu_saat = ayarlar.get("sunucu_saat", self.sunucu_saat)
            program = gun_programi.coz(ayarlar.get("gun_programi"))
            ham_program = ayarlar.get("gun_programi")
            omur = ham_program.get("gecerli_sn") if isinstance(ham_program, dict) else 0
            omur = min(86400, max(0, omur)) if type(omur) is int else 0
            if not omur:
                program = None
            if program != self.gun_programi:
                self.gun_programi, degisti = program, True
            self.gun_programi_bitis = time.monotonic() + omur if program is not None else 0.0
            if "okul_adi" in ayarlar and ayarlar["okul_adi"] != self.okul_adi:
                self.okul_adi, degisti = ayarlar["okul_adi"], True
            if "kilit_kodu" in ayarlar and ayarlar["kilit_kodu"] != self.kilit_kodu:
                self.kilit_kodu, degisti = ayarlar["kilit_kodu"], True
            # Okul kimliği: anahtar yoksa (0.1.x sunucu) mevcut görünüme dokunulmaz.
            if "tema" in ayarlar:
                tema = ayar.palet_dogrula(ayarlar["tema"])
                if tema != self.tema:
                    self.tema, degisti = tema, True
            if isinstance(ayarlar.get("tahta"), dict):
                bilgi = {"ad": _kisa(ayarlar["tahta"].get("ad")), "derslik": _kisa(ayarlar["tahta"].get("derslik"))}
                if bilgi != self.tahta_bilgi:
                    self.tahta_bilgi, degisti = bilgi, True
            # Yüzer düğme (G3): durum tabanlı. Alan yoksa (eski sunucu) düğme kalkar; yanıt hiç gelmezse
            # (sunucu kapalı) durum.json'daki son ayar geçerli kalır.
            dugme = _dugme_coz(ayarlar.get("dugme")) if "dugme" in ayarlar else None
            if dugme != self.dugme:
                self.dugme, degisti = dugme, True
        # Adres listesi (A6): durum tabanlı; anahtar yoksa (eski sunucu ya da boş liste) dokunulmaz.
        if "sunucu_adresleri" in ayarlar:
            self._adres_listesi_isle(ayarlar["sunucu_adresleri"])
        # Acil yayın durumu: anahtar hiç yoksa (eski sunucu) dokunulmaz; null gelirse temizlenir.
        acil_degisti = "acil" in ayarlar and self._acil_isle(ayarlar["acil"])
        # Sınav durumu (A4): anahtar hiç yoksa (eski sunucu) dokunulmaz; null gelirse temizlenir.
        sinav_degisti = ("sinav" in ayarlar and self._sinav_isle(ayarlar["sinav"])) or yerel_sifirlandi
        acil_degisti = acil_degisti or sinav_degisti
        # Ders yoklaması (A5): durum tabanlı, yalnız açık/kapalı. Anahtar yoksa (eski sunucu) dokunulmaz.
        # durum.json'a yazılmaz; ilk yanıtta yeniden gelir.
        if "yoklama_etkin" in ayarlar:
            etkin = bool(ayarlar["yoklama_etkin"])
            with self.kilit:
                if etkin != self.yoklama_etkin:
                    self.yoklama_etkin, acil_degisti = etkin, True
        # USB anahtar (0.11.0): durum tabanlı, yalnız açık/kapalı. Alan yoksa (eski sunucu) izleme kapalı kalır.
        usb = ayarlar.get("usb_anahtar")
        usb_etkin = (isinstance(usb, dict) and usb.get("etkin") is True) if "usb_anahtar" in ayarlar else None
        if self._usb_izlemeyi_ayarla(usb_etkin):
            acil_degisti = True
        logo_degisti = False
        if "logo_sha256" in ayarlar:
            sha = ayarlar["logo_sha256"]
            if sha is None and self.logo_sha is not None:
                ayar.logo_sil()
                with self.kilit:
                    self.logo, self.logo_sha = None, None
                logo_degisti = True
            elif _sha_gecerli(sha) and sha != self.logo_sha:
                # İndirme kilit tutulmadan yapılır: ekran ve komutlar beklemez.
                logo_degisti = self._logo_indir(sha)
        if degisti or logo_degisti:
            with self.kilit:
                self._kaydet()
        if logo_degisti:
            self.marka_yayinla()
        if degisti or logo_degisti or acil_degisti:
            self.yayinla()
        if acil_degisti:
            self.bildir()  # acil_id sunucuya beklemeden gitsin (teslim kaydı)

    def _acil_isle(self, deger) -> bool:
        """Sunucunun verdiği acil durumunu uygular; ekrana yansıyan bir değişiklik olduysa True."""
        yeni = _acil_coz(deger)
        with self.kilit:
            eski = self.acil
            if yeni is None:
                if eski is None:
                    return False
                self.acil = None
                self.olaylar.append("Acil yayın sona erdi (sunucu).")
                return True
            bitis = time.time() + min(ACIL_EN_UZUN_SN, max(5, yeni["kalan_sn"]))
            if eski is not None and eski["id"] == yeni["id"]:
                # Aynı yayın: yalnız kalan süre sunucuyla eşitlenir (tahta saatine güvenilmez).
                degisti = abs(eski["bitis"] - bitis) > 2 or eski["baslik"] != yeni["baslik"] or eski["metin"] != yeni["metin"]
                self.acil = dict(eski, bitis=bitis, baslik=yeni["baslik"], metin=yeni["metin"])
                return degisti
            self.acil = {k: yeni[k] for k in ("id", "tur", "baslik", "metin")}
            self.acil["bitis"] = bitis
            if self.kapatma is not None:
                self.kapatma = None
                self.olaylar.append("Kapatma geri sayımı acil yayın nedeniyle iptal edildi.")
            if self.temizlik is not None:
                self.sonuclar.append({"komut_id": self.temizlik["komut_id"], "basarili": True,
                                      "cikti": "Atlandı: acil yayın başladı; temizlik geri sayımı iptal edildi."})  # fmt: skip
                self.temizlik = None
            self.olaylar.append(f"Acil yayın alındı (#{yeni['id']}, {ACIL_TURLERI[yeni['tur']]}).")
            return True

    def _logo_indir(self, sha: str) -> bool:
        """Logoyu indirir, denetler ve saklar; başarılıysa True. Bozuk logo saklanmaz, eskisi kalır."""
        if self.istemci is None:
            return False
        if self._logo_son_deneme is not None and time.monotonic() - self._logo_son_deneme < LOGO_YENIDEN_DENEME_SN:
            return False
        self._logo_son_deneme = time.monotonic()
        try:
            kod, veri, _ = self.istemci.istek("GET", "/ajan/logo", zaman_asimi=30, ham=True)
        except BaglantiHatasi as hata:
            gunluk.warning("Logo indirilemedi: %s", hata)
            return False
        if kod != 200 or not ayar.logo_gecerli(veri) or hashlib.sha256(veri).hexdigest() != sha:
            gunluk.warning("Logo kabul edilmedi (HTTP %s, %s bayt).", kod, len(veri or b""))
            return False
        try:
            ayar.logo_yaz(bytes(veri))
        except OSError as hata:
            gunluk.warning("Logo yazılamadı: %s", hata)
            return False
        with self.kilit:
            self.logo, self.logo_sha = bytes(veri), sha
        self._logo_son_deneme = None
        return True

    def bildir(self):
        """Durum değişikliğini uzun beklemeyi beklemeden sunucuya iletir."""
        if not (self.istemci and self.kayitli()):
            return

        istemci = self.istemci

        def _gonder():
            try:
                govde = self._istek_govdesi([], 0, komut_al=False)
                kod, yanit, _ = istemci.istek("POST", "/ajan/bekle", govde, zaman_asimi=8)
            except BaglantiHatasi:
                return
            if kod == 200 and isinstance(yanit, dict):
                self._altyapi_yanit(yanit, govde)

        threading.Thread(target=_gonder, daemon=True).start()

    def _dongu(self):
        while not self.dur.is_set():
            bekle = self._tur()
            if bekle:
                self.dur.wait(bekle)

    def _tur(self) -> float:
        """Uzun beklemenin bir turu; sonraki turdan önce beklenecek saniyeyi döndürür (0 = hemen)."""
        self._istemci_kur()
        if not (self.istemci and self.kayitli()):
            return 5
        self.donanim_tazele()  # açılışta ve 6 saatte bir; arada önbellekten
        with self.kilit:
            gonderilen = list(self.sonuclar)
        govde = self._istek_govdesi(gonderilen, 25)
        try:
            kod, yanit, _ = self.istemci.istek("POST", "/ajan/bekle", govde, zaman_asimi=45)
        except BaglantiHatasi as hata:
            gunluk.warning("Sunucuya ulaşılamadı (%s): %s", self._etkin_adres, hata)
            self._adres_hatasi()
            bekle, self._gecikme = self._gecikme, min(self._gecikme * 2, 30)
            return bekle
        # Sunucuya ulaşıldı (parmak izi tuttu): HTTP hatası adres değiştirme sebebi değildir.
        self._adres_hata = 0
        if kod in (401, 403):
            gunluk.warning("Sunucu bu tahtayı tanımıyor (HTTP %s); kayıt yenilenmeli.", kod)
            return 30
        if kod != 200:
            gunluk.warning("Sunucu yanıtı: HTTP %s %s", kod, str(yanit)[:200])
            bekle, self._gecikme = self._gecikme, min(self._gecikme * 2, 30)
            return bekle
        self._gecikme = 2
        self.son_temas = time.time()
        self._adres_basarili()
        with self.kilit:
            self.sonuclar = [s for s in self.sonuclar if s not in gonderilen]
        self.onay_bekliyor = yanit.get("durum") == "bekliyor"
        self._altyapi_yanit(yanit, govde)
        self._yanit_isle(yanit)
        if self.onay_bekliyor:
            return 8
        for komut in yanit.get("komutlar") or []:
            try:
                sonuc = self.komut_uygula(komut)
            except Exception as hata:  # tek komutun hatası döngüyü düşürmez
                gunluk.exception("Komut uygulanamadı")
                sonuc = (False, f"{type(hata).__name__}: {hata}")
            if sonuc is None:
                continue  # ertelenmiş sonuç (oturum temizliği): iş bitince sonuçlara eklenir
            basarili, cikti = sonuc
            with self.kilit:
                self.sonuclar.append({"komut_id": komut.get("id"), "basarili": basarili, "cikti": cikti})
        return 0

    def _program_suresi_denetle(self) -> bool:
        """Süresi dolan program kilidini SUNUCUDAN BAĞIMSIZ açar; açtıysa True."""
        with self.kilit:
            doldu = (
                self._program_kilidi() and self.kilit_bitis is not None and time.monotonic() >= self.kilit_bitis
            )
            if doldu:
                self._kilit_birak()
                self.olaylar.append("Program kilidi süresi doldu; tahta açıldı.")
                self._kaydet()
        if doldu:
            self.yayinla()
            self.bildir()
        return doldu

    def _bekci(self):
        """Çevrimdışı geçişini ve duyuru süresinin dolmasını ekranlara yansıtır."""
        while not self.dur.wait(1):
            with self.kilit:
                suresi_doldu = self.kapatma is not None and self.kapatma["bitis"] <= time.time()
                if suresi_doldu:
                    self.kapatma = None
            if suresi_doldu:
                gunluk.info("Uyarı süresi doldu, kapatılıyor: %s", sistem.kapat())
                self.yayinla()
            self._temizlik_suresi_denetle()
            self._program_suresi_denetle()
            with self.kilit:
                # Acil yayın süresi dolunca (sunucuya ulaşılamasa da) tahta kendiliğinden bırakır.
                acil_bitti = self.acil is not None and self.acil["bitis"] <= time.time()
                if acil_bitti:
                    self.acil = None
                    self.olaylar.append("Acil yayının süresi doldu.")
            self._sinav_denetle()
            self._yoklama_denetle()
            self._usb_denetle()
            program_bitti = self._gun_programi_suresi_denetle()
            durum =(self.cevrimdisi(), self.duyuru is not None and self.duyuru["bitis"] <= time.time())
            if durum != self._son_cevrimdisi or durum[1] or acil_bitti or program_bitti:
                self._son_cevrimdisi = durum
                self.yayinla()

    # ---- yerel soket ----------------------------------------------------------
    def _yerel_sunucu(self):
        servis = self

        class Isleyici(socketserver.StreamRequestHandler):
            def handle(self):
                yazma_kilidi = threading.Lock()

                def gonder(mesaj: dict):
                    try:
                        with yazma_kilidi:
                            self.wfile.write((json.dumps(mesaj, ensure_ascii=False) + "\n").encode("utf-8"))
                            self.wfile.flush()
                    except OSError:
                        pass

                # İlk satır beklenir (yardımcılar bağlanır bağlanmaz "merhaba" yollar): kısa ömürlü komut
                # istemcisi (`arayuz: komut`, A5) kendini tanıtır ve ona durum yayını hiç gitmez. 3 sn
                # içinde satır gelmezse bağlantı ekran yardımcısı sayılır (eski davranış).
                ilk = None
                try:
                    if select.select([self.request], [], [], 3)[0]:
                        ilk = json.loads(self.rfile.readline().decode("utf-8") or "null")
                except (OSError, ValueError):
                    ilk = None
                komut = isinstance(ilk, dict) and ilk.get("tur") == "merhaba" and ilk.get("arayuz") == "komut"
                # Bağlananın kullanıcı kimliği çekirdekten okunur (yardımcının kendi beyanına güvenilmez):
                # oturum temizliği pencere adımını yalnız temizlenen oturumun yardımcısına yollar.
                try:
                    uid = sistem.yerel_baglanti_uid(self.client_address[1], ayar.YEREL_PORT)
                except Exception:  # bulunamazsa pencere adımı atlanır; bağlantı yine kurulur
                    uid = None
                with servis.kilit:
                    servis._ekran_no += 1
                    no = servis._ekran_no
                    servis.ekranlar[no] = {"gonder": gonder, "bilgi": {"arayuz": "komut"} if komut else {}, "uid": uid}
                    kilit_metni = "kilitli" if servis.kilitli else "açık"
                if not komut:
                    # Saha tanılaması (G2): oturum açılınca yardımcının bağlanıp bağlanmadığı ve o anki kilit
                    # durumu günlükte görünsün. Yalnız sayısal kullanıcı kimliği yazılır, hesap adı yazılmaz.
                    arayuz = ilk.get("arayuz") if isinstance(ilk, dict) else None
                    gunluk.info("Ekran yardımcısı bağlandı (no %s, uid %s, arayüz %s); tahta %s.", no, uid, arayuz, kilit_metni)
                try:
                    if not komut:
                        # Logo önce gider: yardımcı ilk durumu çizerken logoyu zaten tanır.
                        if servis.logo_sha:
                            gonder(servis.marka_mesaji())
                        gonder(servis.gorunum())
                    if isinstance(ilk, dict):
                        servis.ekran_mesaji(no, ilk)
                    for satir in self.rfile:
                        try:
                            mesaj = json.loads(satir.decode("utf-8"))
                        except ValueError:
                            continue
                        if isinstance(mesaj, dict):
                            servis.ekran_mesaji(no, mesaj)
                except OSError:
                    pass
                finally:
                    with servis.kilit:
                        servis.ekranlar.pop(no, None)
                    if not komut:
                        gunluk.info("Ekran yardımcısı ayrıldı (no %s).", no)
                    servis.bildir()

        class Sunucu(socketserver.ThreadingTCPServer):
            allow_reuse_address = True
            daemon_threads = True

        sunucu = Sunucu(("127.0.0.1", ayar.YEREL_PORT), Isleyici)
        threading.Thread(target=sunucu.serve_forever, daemon=True).start()
        return sunucu

    def calistir(self):
        gunluk.info("Tahta ajanı %s başlıyor (süreç %s).", __version__, os.getpid())
        yerel = self._yerel_sunucu()
        threading.Thread(target=self._bekci, daemon=True).start()
        try:
            self._dongu()
        finally:
            yerel.shutdown()


def _usb_bos(durum: str = "yok", ileti: str = "", ileti_bitis: float | None = None) -> dict:
    """USB anahtarın ekranda gösterilebilen durumu (gizli değer burada DEĞİL, `Servis._usb_gizli`de)."""
    return {"durum": durum, "tur": "", "etiket": "", "kod": "", "pin_gerek": False, "izinler": [], "ileti": ileti,
            "ileti_bitis": ileti_bitis, "omur_bitis": None, "yeniden": False}  # fmt: skip


def _kisa(deger) -> str:
    return str(deger or "").strip()[:60]


def ariza_aciklamasi(metin) -> str:
    """Arıza açıklaması: denetim karakterleri atılır (satır sonu boşluğa döner), en çok 300 karakter."""
    duz = "".join(" " if c in "\r\n\t" else c for c in str(metin or "") if unicodedata.category(c)[0] != "C" or c in "\r\n\t")
    return " ".join(duz.split())[:ARIZA_ACIKLAMA_EN_UZUN]


def _ariza_kuyrugu_coz(deger) -> list[dict]:
    """durum.json'daki kuyruğu doğrular (bozuk öğe atılır, en çok 10)."""
    sonuc: list[dict] = []
    for oge in deger if isinstance(deger, list) else []:
        if not isinstance(oge, dict):
            continue
        yerel_id = str(oge.get("yerel_id") or "")
        if not (8 <= len(yerel_id) <= 32 and all(c in "0123456789abcdef" for c in yerel_id)):
            continue
        sonuc.append({
            "yerel_id": yerel_id,
            "kategori": str(oge.get("kategori") or "diger")[:40],
            "aciklama": ariza_aciklamasi(oge.get("aciklama")),
            "oturum_sinifi": str(oge.get("oturum_sinifi") or "")[:20],
            "tahta_zamani": _sayi(oge.get("tahta_zamani")),
        })  # fmt: skip
    return sonuc[:ARIZA_KUYRUK_EN_COK]


def _oturum_coz(deger, acilis: str) -> dict | None:
    """durum.json'daki oturum: yalnız aynı açılışa aitse geçerlidir (yeniden başlatmada sayaç sıfırlanır)."""
    if not isinstance(deger, dict) or not acilis or deger.get("acilis") != acilis:
        return None
    no, baslangic = deger.get("no"), deger.get("baslangic")
    if not isinstance(no, str) or not 1 <= len(no) <= 32 or isinstance(baslangic, bool) or not isinstance(baslangic, (int, float)):
        return None
    return {"no": no, "baslangic": float(baslangic)}


def _dugme_coz(deger) -> dict | None:
    """`ayar.dugme` (ya da durum.json'daki kopyası): {"acik", "islemler"} — işlemler bilinenlerin sıralı
    alt kümesi. None → None (ayar yok). Bozuk değer ya da boş liste kapalı sayılır."""
    if deger is None:
        return None
    if not isinstance(deger, dict) or deger.get("acik") is not True or not isinstance(deger.get("islemler"), list):
        return {"acik": False, "islemler": []}
    istenen = {str(i) for i in deger["islemler"]}
    islemler = [i for i in DUGME_ISLEMLERI if i in istenen]
    return {"acik": bool(islemler), "islemler": islemler}


def _saat_gecerli(deger: str) -> bool:
    """'SS:DD' (00:00–23:59) biçimini doğrular."""
    if len(deger) != 5 or deger[2] != ":" or not (deger[:2].isdigit() and deger[3:].isdigit()):
        return False
    return int(deger[:2]) < 24 and int(deger[3:]) < 60


def _acil_coz(deger) -> dict | None:
    """`ayar.acil` değerini doğrular: {"id","tur","baslik","metin","kalan_sn"} ya da None.

    Biçimi bozuk değer yok sayılır (None): tahtada belirsiz bir acil ekranı açılmaz.
    """
    if not isinstance(deger, dict):
        return None
    kimlik, tur = deger.get("id"), deger.get("tur")
    if not isinstance(kimlik, int) or isinstance(kimlik, bool) or tur not in ACIL_TURLERI:
        return None
    try:
        kalan = int(deger.get("kalan_sn") or 0)
    except (TypeError, ValueError):
        return None
    if kalan <= 0:
        return None
    return {
        "id": kimlik,
        "tur": tur,
        "baslik": str(deger.get("baslik") or "")[:120],
        "metin": str(deger.get("metin") or "")[:1000],
        "kalan_sn": kalan,
    }


_SINAV_ALANLARI = ("salon", "sinav_adi", "salon_adi", "baslangic_saat", "bitis_saat", "dersler", "kurallar",
                   "yoklama_alindi", "liste", "liste_fazla")  # fmt: skip


def _tamsayi_mi(deger) -> bool:
    return isinstance(deger, int) and not isinstance(deger, bool)


def _sayi(deger) -> int:
    """Negatif olmayan tam sayı; okunamazsa 0."""
    try:
        return max(0, int(deger))
    except (TypeError, ValueError):
        return 0


def _kes(deger, sinir: int) -> str:
    return str(deger or "")[:sinir]


def _liste_coz(deger) -> list[dict]:
    """Maskeli oturma listesi: [{"k": koltuk, "a": maske, "n": no son 2 hane, "s": şube}], en çok 60.

    Yalnız bu dört alan alınır; tam okul no ya da ad gelse bile tutulmaz.
    """
    liste = []
    for oge in deger if isinstance(deger, list) else []:
        if len(liste) >= SINAV_LISTE_SINIRI:
            break
        if isinstance(oge, dict) and _tamsayi_mi(oge.get("k")) and 0 < oge["k"] < 10000:
            liste.append({"k": oge["k"], "a": _kes(oge.get("a"), 60), "n": _kes(oge.get("n"), 4), "s": _kes(oge.get("s"), 16)})
    return liste


def _sinav_coz(deger, simdi_mono: float) -> dict | None:
    """`ayar.sinav` değerini doğrular ve monotonic saate çapalar; geçersiz ya da bitmişse None.

    Biçimi bozuk değer yok sayılır: tahtada belirsiz bir sınav ekranı açılmaz.
    """
    if not isinstance(deger, dict):
        return None
    kimlik, salon = deger.get("kimlik"), deger.get("salon")
    if not isinstance(kimlik, str) or not kimlik or not _tamsayi_mi(salon):
        return None
    try:
        basla, bitis = int(deger.get("basla_sn")), int(deger.get("bitis_sn"))
    except (TypeError, ValueError):
        return None
    if bitis <= 0:
        return None
    bitis = min(bitis, SINAV_EN_UZUN_SN)
    basla = min(basla, bitis)
    dersler = []
    for d in deger.get("dersler") if isinstance(deger.get("dersler"), list) else []:
        if isinstance(d, dict) and len(dersler) < 20:
            saat = _kes(d.get("bitis_saat"), 5)
            dersler.append({"ad": _kes(d.get("ad"), 120), "bitis_saat": saat if _saat_gecerli(saat) else ""})
    liste = _liste_coz(deger.get("liste")) if basla > 0 and isinstance(deger.get("liste"), list) else None
    baslangic, bitis_saat = _kes(deger.get("baslangic_saat"), 5), _kes(deger.get("bitis_saat"), 5)
    return {
        "kimlik": kimlik[:80],
        "salon": salon,
        "sinav_adi": _kes(deger.get("sinav_adi"), 200),
        "salon_adi": _kes(deger.get("salon_adi"), 60),
        "baslangic_saat": baslangic if _saat_gecerli(baslangic) else "",
        "bitis_saat": bitis_saat if _saat_gecerli(bitis_saat) else "",
        "dersler": dersler,
        "kurallar": _kes(deger.get("kurallar"), 1500),
        "yoklama_alindi": bool(deger.get("yoklama_alindi")),
        "liste": liste,
        "liste_fazla": _sayi(deger.get("liste_fazla")) if liste is not None else 0,
        "basla_mono": simdi_mono + basla,
        "bitis_mono": simdi_mono + bitis,
    }


def _oneri_coz(deger) -> dict:
    """/ajan/yoklama/oneri yanıtını doğrular. Öğrenci verisi içermez; bozuk alan boş sayılır."""
    deger = deger if isinstance(deger, dict) else {}
    saatler = []
    for s in deger.get("ders_saatleri") if isinstance(deger.get("ders_saatleri"), list) else []:
        no = s.get("ders_no") if isinstance(s, dict) else None
        if _tamsayi_mi(no) and 1 <= no <= YOKLAMA_DERS_NO_EN_COK and len(saatler) < YOKLAMA_DERS_NO_EN_COK:
            bas, bit = _kes(s.get("baslangic"), 5), _kes(s.get("bitis"), 5)
            saatler.append({"ders_no": no, "baslangic": bas if _saat_gecerli(bas) else "", "bitis": bit if _saat_gecerli(bit) else "",
                            "secilebilir": bool(s.get("secilebilir", True))})  # fmt: skip
    en_cok = deger.get("ders_no_en_cok")
    if not (_tamsayi_mi(en_cok) and 1 <= en_cok <= YOKLAMA_DERS_NO_EN_COK):
        en_cok = max((s["ders_no"] for s in saatler), default=12)
    subeler = [s[:16] for s in deger.get("subeler") or [] if isinstance(s, str) and s.strip()][:200]
    oneri = deger.get("oneri") if isinstance(deger.get("oneri"), dict) else {}
    sube = oneri.get("sube") if isinstance(oneri.get("sube"), str) and oneri.get("sube") else None
    ders_no = oneri.get("ders_no") if _tamsayi_mi(oneri.get("ders_no")) and 1 <= oneri["ders_no"] <= en_cok else None
    return {"tarih_yazi": _kes(deger.get("tarih_yazi"), 40), "ders_saatleri": saatler, "ders_no_en_cok": en_cok,
            "subeler": subeler, "sube": sube[:16] if sube else None, "ders_no": ders_no}  # fmt: skip


def _ders_secenekleri(oneri: dict) -> list[dict]:
    """Seçilebilecek ders saatleri: zil saatleri biliniyorsa onlar (başlamamışlar seçilemez), yoksa 1..en_cok."""
    saatler = oneri.get("ders_saatleri") or []
    if saatler:
        return [{"ders_no": s["ders_no"], "secilebilir": s["secilebilir"],
                 "metin": f"{s['ders_no']}. ders ({s['baslangic']}–{s['bitis']})" if s["baslangic"] and s["bitis"] else f"{s['ders_no']}. ders"}
                for s in saatler]  # fmt: skip
    return [{"ders_no": n, "secilebilir": True, "metin": f"{n}. ders"} for n in range(1, int(oneri.get("ders_no_en_cok") or 12) + 1)]


def _yoklama_listesi_coz(deger) -> list[dict]:
    """Sınıf listesi: [{"id", "etiket"}] (etiket sunucuda maskelenmiştir). Başka alan tutulmaz."""
    liste, gorulen = [], set()
    for oge in deger if isinstance(deger, list) else []:
        if len(liste) >= YOKLAMA_LISTE_SINIRI:
            break
        if isinstance(oge, dict) and _tamsayi_mi(oge.get("id")) and oge["id"] not in gorulen:
            gorulen.add(oge["id"])
            liste.append({"id": oge["id"], "etiket": _kes(oge.get("etiket"), 40)})
    return liste


def _sha_gecerli(deger) -> bool:
    return isinstance(deger, str) and len(deger) == 64 and all(c in "0123456789abcdef" for c in deger)


def calistir() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    servis = Servis()
    try:
        servis.calistir()
    except KeyboardInterrupt:
        pass
    return 0
