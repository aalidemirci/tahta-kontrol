"""Ajan servisi: sunucuyla konuşur, komutları uygular, ekran yardımcılarını besler.

Yönetici (root) yetkisiyle sistem servisi olarak çalışır. Ekrandaki pencereyi
kendisi çizmez; her oturumda başlayan ekran yardımcısı (ekran.py) yerel bir
sokete bağlanır ve ne göstereceğini buradan öğrenir. Sır (tahta anahtarı,
kilit kodu özeti) ekran yardımcısına hiç gitmez.
"""

from __future__ import annotations

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


class Servis:
    def __init__(self):
        self.kilit = threading.RLock()
        self.dur = threading.Event()
        kayitli = ayar.durum_oku()
        self.kilitli = bool(kayitli.get("kilitli", False))
        self.duyuru = None  # {"baslik","metin","bitis","kapatilabilir"}
        self.kapatma = None  # {"bitis","neden"}: uyarılı kapatma geri sayımı
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

    # ---- durum -----------------------------------------------------------
    def cevrimdisi(self) -> bool:
        return (time.time() - self.son_temas) > ayar.CEVRIMDISI_SN

    def kayitli(self) -> bool:
        return bool(self.yapi.get("tahta_id"))

    def _kaydet(self):
        ayar.durum_yaz({"kilitli": self.kilitli, "okul_adi": self.okul_adi, "kilit_kodu": self.kilit_kodu})

    def gorunum(self) -> dict:
        with self.kilit:
            duyuru = self.duyuru
            if duyuru and duyuru["bitis"] <= time.time():
                self.duyuru = duyuru = None
            return {
                "tur": "durum",
                "surum": __version__,
                "kilitli": self.kilitli,
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
                "okul_adi": self.okul_adi,
                "kod_var": bool(self.kilit_kodu),
                "cevrimdisi": self.cevrimdisi(),
                "kayitli": self.kayitli(),
                "bekleme": max(0, int(self.bekleme_bitis - time.time())),
            }

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
        return {
            "kilitli": self.kilitli,
            "duyuru_var": self.duyuru is not None,
            "kapatma_bekliyor": self.kapatma is not None,
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
            if self.cevrimdisi() or not self.kayitli():
                with self.kilit:
                    self.kilitli = False
                    self.olaylar.append("Kilit sunucuya ulaşılamadığı için tahtadan açıldı.")
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

    def _kod_dene(self, kod: str):
        with self.kilit:
            if time.time() < self.bekleme_bitis or not self.kilit_kodu:
                pass
            else:
                beklenen = self.kilit_kodu
                ozet = hashlib.pbkdf2_hmac(
                    "sha256", kod.encode("utf-8"), bytes.fromhex(beklenen["tuz"]), int(beklenen["tur"])
                ).hex()
                if hmac.compare_digest(ozet, beklenen["ozet"]):
                    self.kilitli = False
                    self.hatali_deneme = 0
                    self.olaylar.append("Kilit tahtadan kodla açıldı.")
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
            with self.kilit:
                self.kilitli = True
                self._kaydet()
            self.yayinla()
            return True, self._ekran_notu("Kilitlendi.")
        if tur == "kilit_ac":
            with self.kilit:
                self.kilitli = False
                self._kaydet()
            self.yayinla()
            return True, "Kilit açıldı."
        if tur == "duyuru":
            with self.kilit:
                self.duyuru = {
                    "baslik": str(veri.get("baslik", ""))[:200],
                    "metin": str(veri.get("metin", ""))[:4000],
                    "bitis": time.time() + max(5, int(veri.get("sure_sn", 60))),
                    "kapatilabilir": bool(veri.get("kapatilabilir", True)),
                }
            self.yayinla()
            return True, self._ekran_notu("Duyuru gösterildi.")
        if tur == "duyuru_kaldir":
            with self.kilit:
                self.duyuru = None
            self.yayinla()
            return True, "Duyuru kaldırıldı."
        if tur == "tani":
            parca = urlsplit(self.yapi.get("sunucu", ""))
            with self.kilit:
                ekranlar = [dict(e["bilgi"]) for e in self.ekranlar.values()]
            rapor = tani.topla(parca.hostname or "", parca.port or 443, self.sunucu_saat, ekranlar)
            return True, json.dumps(rapor, ensure_ascii=False)
        if tur == "guncelle":
            return self._guncelle(veri)
        if tur == "kapat" and int(veri.get("uyari_sn", 0) or 0) > 0:
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
            self.sunucu_saat = ayarlar.get("sunucu_saat", self.sunucu_saat)
            if "okul_adi" in ayarlar and ayarlar["okul_adi"] != self.okul_adi:
                self.okul_adi, degisti = ayarlar["okul_adi"], True
            if "kilit_kodu" in ayarlar and ayarlar["kilit_kodu"] != self.kilit_kodu:
                self.kilit_kodu, degisti = ayarlar["kilit_kodu"], True
            if degisti:
                self._kaydet()
        if degisti:
            self.yayinla()

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
            durum = (self.cevrimdisi(), self.duyuru is not None and self.duyuru["bitis"] <= time.time())
            if durum != self._son_cevrimdisi or durum[1]:
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


def calistir() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    servis = Servis()
    try:
        servis.calistir()
    except KeyboardInterrupt:
        pass
    return 0
