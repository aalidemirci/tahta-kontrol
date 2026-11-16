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
import socket
import socketserver
import threading
import time
from urllib.parse import urlsplit

from . import __version__, ayar, sistem, tani
from .baglanti import BaglantiHatasi, Istemci

gunluk = logging.getLogger("tahta-ajan")

KOD_DENEME_SINIRI = 5
KOD_BEKLEME_SN = 60
LOGO_YENIDEN_DENEME_SN = 60
# Sunucunun bu ajana uygulayabileceği yetenekler (sürüm karşılaştırması yerine).
YETENEKLER = ["acil", "duyuru_id", "program_kilidi", "sinav"]
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
        # Ağ isteği atan işler ayrı iş parçacığında çalışır (ekran beklemez); testler eşzamanlı yapar.
        self.arka_plan = lambda is_: threading.Thread(target=is_, daemon=True).start()
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
        kod = "".join(c for c in str(kod) if c.isdigit())[: GOZETMEN_KOD_UZUNLUK + 2]
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
            }

    def marka_mesaji(self) -> dict:
        """Logo baytlarını ekran yardımcısına taşıyan satır (yardımcı root dosyasını okuyamaz)."""
        with self.kilit:
            logo, sha = self.logo, self.logo_sha
        if not logo:
            return {"tur": "marka", "sha256": None, "logo": None}
        return {"tur": "marka", "sha256": sha, "logo": base64.b64encode(logo).decode("ascii")}

    def marka_yayinla(self):
        mesaj = self.marka_mesaji()
        with self.kilit:
            hedefler = list(self.ekranlar.values())
        for hedef in hedefler:
            hedef["gonder"](mesaj)

    def yayinla(self):
        mesaj = self.gorunum()
        with self.kilit:
            hedefler = list(self.ekranlar.values())
        for hedef in hedefler:
            hedef["gonder"](mesaj)

    def durum_ozeti(self) -> dict:
        with self.kilit:
            ekranlar = [dict(e["bilgi"]) for e in self.ekranlar.values()]
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
            "yetenekler": list(YETENEKLER),
            "acil_id": acil_id,
            "sinav": self._sinav_durumu(),  # {kimlik, evre, yerel_kapali} | None — ad ve liste yok
            "ekranlar": ekranlar,
            "oturum": oturum,
            "acik_sure": sistem.acik_sure(),
            "makine_adi": socket.gethostname(),
            "ip": ag.get("ip", ""),
            "mac": ag.get("mac", ""),
            "platform": sistem.platform_adi(),
            "olaylar": olaylar,
        }

    # ---- ekran yardımcısından gelenler -------------------------------------
    def ekran_mesaji(self, no: int, mesaj: dict):
        tur = mesaj.get("tur")
        if tur in ("merhaba", "ekran_durumu"):
            with self.kilit:
                if no in self.ekranlar:
                    bilgi = {k: v for k, v in mesaj.items() if k != "tur"}
                    self.ekranlar[no]["bilgi"].update(bilgi)
            if tur == "merhaba" and mesaj.get("surum") not in (None, __version__):
                # Güncellemeden sonra eski sürümlü yardımcı kendini yeniden başlatır.
                self.ekranlar[no]["gonder"]({"tur": "yeniden_baslat"})
            self.bildir()
        elif tur == "kod":
            self._kod_dene(str(mesaj.get("kod", "")))
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
            self.yayinla()
            self.bildir()
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
    def komut_uygula(self, komut: dict) -> tuple[bool, str]:
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
            rapor = tani.topla(parca.hostname or "", parca.port or 443, self.sunucu_saat, ekranlar, self.sinav_tani_metni())
            return True, json.dumps(rapor, ensure_ascii=False)
        if tur == "guncelle":
            return self._guncelle(veri)
        if tur == "kapat" and int(veri.get("uyari_sn", 0) or 0) > 0:
            # Uyarılı (otomatik) kapatma acil yayın sürerken uygulanmaz: bilinçli atlama,
            # hata değildir. Panelden verilen uyarısız kapatma ise her durumda uygulanır.
            if self.acil is not None and self.acil["bitis"] > time.time():
                return True, "Acil yayın sürüyor; otomatik kapatma uygulanmadı."
            if self.sinav_ekrani_acik():
                return True, "Sınav sürüyor; otomatik kapatma uygulanmadı."
            # Uyarılı kapatma: tahta kullanılıyorsa (kilitli değil ve ekranı varsa)
            # önce geri sayım gösterilir; kullanan kişi vazgeçebilir. Kilitli ya da
            # oturumsuz tahtada uyaracak kimse yoktur, doğrudan kapanır.
            with self.kilit:
                gorunur = any(e["bilgi"].get("arayuz") not in (None, "yok") for e in self.ekranlar.values())
                if gorunur and not self.kilitli:
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

    def _ekran_notu(self, metin: str) -> str:
        with self.kilit:
            gorunur = [e for e in self.ekranlar.values() if e["bilgi"].get("arayuz") not in (None, "yok")]
        if not gorunur:
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
        self.yapi = ayar.oku()
        if not self.yapi.get("sunucu"):
            self.istemci = None
            return
        self.istemci = Istemci(
            self.yapi["sunucu"], self.yapi.get("parmak_izi", ""), self.yapi.get("tahta_id"), self.yapi.get("anahtar", "")
        )

    def _yanit_isle(self, yanit: dict):
        ayarlar = yanit.get("ayar") or {}
        degisti = False
        with self.kilit:
            # Tahtadan (çevrimdışıyken) kapatılan sınav yalnız çevrimdışılık sürdükçe kapalı kalır.
            yerel_sifirlandi = self.sinav_yerel_kapali is not None
            self.sinav_yerel_kapali = None
            self.sunucu_saat = ayarlar.get("sunucu_saat", self.sunucu_saat)
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
        # Acil yayın durumu: anahtar hiç yoksa (eski sunucu) dokunulmaz; null gelirse temizlenir.
        acil_degisti = "acil" in ayarlar and self._acil_isle(ayarlar["acil"])
        # Sınav durumu (A4): anahtar hiç yoksa (eski sunucu) dokunulmaz; null gelirse temizlenir.
        sinav_degisti = ("sinav" in ayarlar and self._sinav_isle(ayarlar["sinav"])) or yerel_sifirlandi
        acil_degisti = acil_degisti or sinav_degisti
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

        def _gonder():
            try:
                self.istemci.istek(
                    "POST",
                    "/ajan/bekle",
                    {"surum": __version__, "durum": self.durum_ozeti(), "sonuclar": [], "bekle": 0, "komut_al": False},
                    zaman_asimi=8,
                )
            except BaglantiHatasi:
                pass

        threading.Thread(target=_gonder, daemon=True).start()

    def _dongu(self):
        gecikme = 2
        while not self.dur.is_set():
            self._istemci_kur()
            if not (self.istemci and self.kayitli()):
                self.dur.wait(5)
                continue
            with self.kilit:
                gonderilen = list(self.sonuclar)
            try:
                kod, yanit, _ = self.istemci.istek(
                    "POST",
                    "/ajan/bekle",
                    {"surum": __version__, "durum": self.durum_ozeti(), "sonuclar": gonderilen, "bekle": 25},
                    zaman_asimi=45,
                )
            except BaglantiHatasi as hata:
                gunluk.warning("Sunucuya ulaşılamadı: %s", hata)
                self.dur.wait(gecikme)
                gecikme = min(gecikme * 2, 30)
                continue
            if kod in (401, 403):
                gunluk.warning("Sunucu bu tahtayı tanımıyor (HTTP %s); kayıt yenilenmeli.", kod)
                self.dur.wait(30)
                continue
            if kod != 200:
                gunluk.warning("Sunucu yanıtı: HTTP %s %s", kod, str(yanit)[:200])
                self.dur.wait(gecikme)
                gecikme = min(gecikme * 2, 30)
                continue
            gecikme = 2
            self.son_temas = time.time()
            with self.kilit:
                self.sonuclar = [s for s in self.sonuclar if s not in gonderilen]
            self._yanit_isle(yanit)
            if yanit.get("durum") == "bekliyor":
                self.dur.wait(8)
                continue
            for komut in yanit.get("komutlar") or []:
                try:
                    basarili, cikti = self.komut_uygula(komut)
                except Exception as hata:  # tek komutun hatası döngüyü düşürmez
                    gunluk.exception("Komut uygulanamadı")
                    basarili, cikti = False, f"{type(hata).__name__}: {hata}"
                with self.kilit:
                    self.sonuclar.append({"komut_id": komut.get("id"), "basarili": basarili, "cikti": cikti})

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
            self._program_suresi_denetle()
            with self.kilit:
                # Acil yayın süresi dolunca (sunucuya ulaşılamasa da) tahta kendiliğinden bırakır.
                acil_bitti = self.acil is not None and self.acil["bitis"] <= time.time()
                if acil_bitti:
                    self.acil = None
                    self.olaylar.append("Acil yayının süresi doldu.")
            self._sinav_denetle()
            durum = (self.cevrimdisi(), self.duyuru is not None and self.duyuru["bitis"] <= time.time())
            if durum != self._son_cevrimdisi or durum[1] or acil_bitti:
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

                with servis.kilit:
                    servis._ekran_no += 1
                    no = servis._ekran_no
                    servis.ekranlar[no] = {"gonder": gonder, "bilgi": {}}
                try:
                    # Logo önce gider: yardımcı ilk durumu çizerken logoyu zaten tanır.
                    if servis.logo_sha:
                        gonder(servis.marka_mesaji())
                    gonder(servis.gorunum())
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


def _kisa(deger) -> str:
    return str(deger or "").strip()[:60]


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
