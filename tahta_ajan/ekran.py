"""Ekran yardımcısı: kilit, duyuru, kapatma uyarısı ve acil yayın penceresini çizer.

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
#bilgi { font-size: 24px; }
#kod { font-size: 56px; letter-spacing: 12px; }
#duyuru-baslik { font-size: 72px; font-weight: 700; }
#duyuru-metin { font-size: 52px; }
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


def acil_basligi(baslik, tatbikat: bool) -> str:
    """Acil sayfasındaki büyük başlık. Bant sözcüğünü tekrarlayan ya da boş başlık
    gösterilmez ("ACİL DURUM" alt alta iki kez yazılmasın); boş metin = etiket gizli."""
    metin = " ".join(str(baslik or "").split())

    def katla(s: str) -> str:  # Türkçe büyük/küçük harf duyarsız karşılaştırma
        return s.replace("İ", "I").replace("ı", "i").upper().rstrip(".!")

    tekrar = {katla(s) for s in ("ACİL DURUM", "TATBİKAT", ACIL_BANT["tatbikat"])}
    return "" if katla(metin) in tekrar else metin


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
        f"#duyuru-baslik {{ color: {p['vurgu']}; }}\n"
        "#kapatma-baslik { color: #fca5a5; }\n"
        f"button {{ background-color: {p['dugme']}; border-color: {p['dugme_kenar']}; }}\n"
        f"button label {{ color: {p['metin']}; }}\n"
        f"button:active {{ background-color: {p['yuzey']}; }}\n"
        f"#ana-dugme {{ background-color: {p['ana']}; border-color: {p['ana']}; }}\n"
        f"#ana-dugme label {{ color: {p['ana_metin']}; }}\n"
        + ACIL_RENKLERI
    )


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
            self.bilgi = self._etiket("bilgi")
            self.bilgi.set_max_width_chars(40)
            for parca in (self.saat, self.tarih, self.kilit_yazi, self.bilgi):
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
            kutu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=30)
            kutu.set_margin_start(80)
            kutu.set_margin_end(80)
            self.duyuru_baslik = self._etiket("duyuru-baslik")
            self.duyuru_metin = self._etiket("duyuru-metin")
            self.duyuru_metin.set_max_width_chars(48)
            self.duyuru_kapat = Gtk.Button(label="Kapat")
            self.duyuru_kapat.set_halign(Gtk.Align.CENTER)
            self.duyuru_kapat.set_can_focus(False)
            self.duyuru_kapat.connect("clicked", lambda *_: self.baglanti.gonder({"tur": "duyuru_kapat"}))
            for parca in (self.duyuru_baslik, self.duyuru_metin, self.duyuru_kapat):
                kutu.pack_start(parca, False, False, 0)
            return self._sayfa(kutu)

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
            self._bantlari_ciz(durum)
            # Öncelik (ortak sözlük §5.5): acil > kapatma > duyuru > kilit > gizli.
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
            elif duyuru:
                self.duyuru_baslik.set_text(duyuru.get("baslik") or "DUYURU")
                self.duyuru_metin.set_text(duyuru.get("metin") or "")
                self.duyuru_kapat.set_visible(bool(duyuru.get("kapatilabilir")))
                self.yigin.set_visible_child_name("duyuru")
                self._goster(kilit=False)
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
                else:
                    self.bilgi.set_text("Kilit okul idaresince açılır.")
                self.kod_kutusu.set_visible(kod_var and not bekleme and not cevrimdisi)
                self.cevrimdisi_dugmesi.set_visible(cevrimdisi)
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
