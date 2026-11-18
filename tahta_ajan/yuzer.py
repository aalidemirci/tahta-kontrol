"""Tahtadaki yüzer düğme (0.9.0, saha bulgusu G3).

Ekran yardımcısı (ekran.py) tahta kilitli değilken ve tam ekran bir sayfa (kilit, duyuru, acil, sınav,
kapatma uyarısı, yoklama) gösterilmiyorken birincil ekranın köşesinde küçük, soluk, sürüklenebilir bir
düğme gösterir. Dokununca yanında küçük bir menü açılır: Kilitle, Kapat, Yeniden başlat, Arıza bildir,
Yoklama al. Hangi işlemlerin görüneceğini sunucu belirler (`ayar.dugme`, servis üzerinden); işlemi
servis doğrular ve uygular (yerel_kilitle / yerel_kapat / yerel_yeniden_baslat). Bu modül sır taşımaz.

- Odak çalmaz: iki pencere de çerçevesiz yardımcı penceredir; masaüstünün
  klavye, dokunma veya fare girişini ele geçirmez (girdi tutma — seat grab — GERİ GETİRİLMEZ).
  Menü düğmeyle, Kapat ile veya zaman aşımıyla kapanır; görev çubuğu menü açıkken de kullanılabilir.
- Pencere yönetilen (TOPLEVEL/UTILITY, keep_above) ve yapışkandır (stick: bütün çalışma alanlarında
  görünür). 18.11.2026 kap denemesi (Xvfb): xfwm4, Mutter ve Muffin'de odaklı tam ekran uygulamanın
  üstünde kalır ve tıklanır; DOCK ipucu Mutter/Muffin'de tam ekranın ALTINDA kalır, NOTIFICATION
  bir şey kazandırmaz — ipucu bu yüzden UTILITY kalır. Openbox'ta odaklı tam ekranın üstüne hiçbir
  yönetilen pencere çıkamaz; "masaüstünü göster" xfwm4'te düğmeyi gizlemez, Mutter/Muffin/Openbox'ta
  o kip sürdükçe gizler (pencere yöneticisi sınırı).
- Dokunma: aynı dokunuş hem touch-event hem (GTK'nın fare öykünmesiyle) button-press olarak
  gelebilir; dokunuştan hemen sonraki fare basışı yok sayılır (menü açılıp hemen kapanmasın).
  Dokunmada sürükleme eşiği farenin iki katıdır (parmak titrer).
- Ölçüler 1920x1080 için yazılır ve ekran_olcegi() ile ölçeklenir; sabit piksel yoktur.
- Konum oturum boyunca bellekte tutulur (kenar + dikey oran): çözünürlük değişse de aynı yere gelir.

Üstteki işlevler saftır (GTK'sız test edilir); GTK sınıfı kur() içinde kurulur.
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
import time

from .ekran import ekran_olcegi, olcekle, olcekli_stil

# 1920x1080 ölçüleri
DUGME_CAP = 60  # düğmenin eni ve boyu
KENAR_BOSLUGU = 18  # ekran kenarına yapışınca kalan boşluk
MENU_ARALIGI = 12  # düğme ile menü arasındaki boşluk
SURUKLEME_ESIGI = 14  # fare: bundan az kayan basış "tıklama" sayılır, sürükleme değil
DOKUNMA_ESIGI = 28  # dokunma: parmak ve kızılötesi çerçeve titrer; eşik farenin iki katıdır
DOKUNMA_GOLGESI_SN = 0.7  # dokunuştan sonra bu süre içinde gelen fare basışı aynı dokunuşun öykünmesidir
SOLUK_SAYDAMLIK = 0.55  # bileşikli (compositor) masaüstünde boştayken
BELIRGIN_SN = 4  # dokunuştan sonra bu kadar saniye belirgin kalır
MENU_KAPANMA_SN = 12  # dokunulmayan menü kendiliğinden kapanır
GERI_SAYIM_SN = 10  # Kapat / Yeniden başlat onayı

ETIKETLER = {
    "kilitle": "Kilitle",
    "kapat": "Kapat",
    "yeniden_baslat": "Yeniden başlat",
    "ariza": "Arıza bildir",
    "yoklama": "Yoklama al",
}
KILITLE_KODSUZ = "Kilitle (kilit kodu belirlenmemiş)"
ONAYLI = ("kapat", "yeniden_baslat")
GERI_SAYIM_BASLIK = {"kapat": "Tahta kapatılacak", "yeniden_baslat": "Tahta yeniden başlatılacak"}

STIL = b"""
#yd-pencere, #yd-menu-pencere { background-color: transparent; }
#yd-dugme { min-width: 60px; min-height: 60px; padding: 0px; border-radius: 30px; border-width: 2px;
            border-style: solid; font-size: 30px; font-weight: 700; background-image: none; box-shadow: none; }
#yd-menu { padding: 10px; border-radius: 14px; border-width: 2px; border-style: solid; }
#yd-menu button { font-size: 28px; font-weight: 600; padding: 14px 26px; min-height: 48px; border-radius: 10px;
                  border-width: 1px; border-style: solid; background-image: none; box-shadow: none; text-shadow: none; }
#yd-menu label { font-size: 28px; }
#yd-menu #yd-sayac { font-size: 64px; font-weight: 700; margin: 4px 0px; }
#yd-menu #yd-baslik { font-size: 28px; font-weight: 700; margin: 6px 12px 0px 12px; }
#yd-menu #yd-ileti { font-size: 24px; margin: 4px 8px; }
"""
# Renkler markadan bağımsız ve sabittir (koyu zemin, beyaz yazı; 7:1'i aşar).
RENK = b"""
#yd-dugme { background-color: #1f2937; border-color: #e5e7eb; color: #ffffff; }
#yd-dugme label { color: #ffffff; }
#yd-dugme.soluk { background-color: #374151; border-color: #6b7280; }
#yd-dugme.soluk label { color: #d1d5db; }
#yd-menu { background-color: #111827; border-color: #9ca3af; }
#yd-menu label { color: #f9fafb; }
#yd-menu button { background-color: #1f2937; border-color: #4b5563; }
#yd-menu button label { color: #f9fafb; }
#yd-menu button:active { background-color: #374151; }
#yd-menu button:disabled { opacity: 1; background-color: #111827; }
#yd-menu button:disabled label { color: #9ca3af; }
#yd-menu #yd-vazgec { background-color: #2563eb; border-color: #2563eb; }
#yd-menu #yd-vazgec label { color: #ffffff; }
#yd-menu #yd-ileti { color: #fde68a; }
#yd-pencere.kati, #yd-menu-pencere.kati { background-color: #111827; }
#yd-pencere.kati.soluk { background-color: #374151; }
#yd-dugme.kati { border-radius: 0px; border-width: 0px; }
"""


# ---- saf mantık (test edilir) ------------------------------------------------------------------
ILETI_SERVIS_YOK = "Tahta servisine ulaşılamıyor; işlem yapılmadı."


def dugme_ayari(durum: dict | None) -> dict:
    """Servisin durum iletisindeki `dugme` alanı; yoksa ya da bozuksa kapalı."""
    d = (durum or {}).get("dugme")
    if not isinstance(d, dict) or d.get("acik") is not True:
        return {"acik": False, "islemler": [], "kilitle_kullanilabilir": False}
    islemler = [i for i in d.get("islemler") or [] if i in ETIKETLER]
    return {"acik": bool(islemler), "islemler": islemler, "kilitle_kullanilabilir": bool(d.get("kilitle_kullanilabilir"))}


def gorunur_mu(durum: dict | None, ana_gorunur: bool) -> bool:
    """Düğme yalnız servis bağlıyken, ayar açıkken ve tam ekran sayfa yokken görünür.

    Tam ekran sayfalar (kilit, duyuru, acil, sınav, kapatma/temizlik uyarısı, yoklama) ana pencerededir:
    ana pencere görünürken düğme gizlenir. Kilitli tahtada ana pencere zaten açıktır.
    """
    if not durum or ana_gorunur or durum.get("kilitli"):
        return False
    return dugme_ayari(durum)["acik"]


def menu_ogeleri(ayar_: dict) -> list[dict]:
    """Menü düğmeleri: [{"islem","etiket","etkin"}] sunucunun sırasıyla. Kilit kodu yoksa Kilitle soluk."""
    ogeler = []
    for islem in ayar_.get("islemler") or []:
        if islem not in ETIKETLER:
            continue
        if islem == "kilitle" and not ayar_.get("kilitle_kullanilabilir"):
            ogeler.append({"islem": islem, "etiket": KILITLE_KODSUZ, "etkin": False})
        else:
            ogeler.append({"islem": islem, "etiket": ETIKETLER[islem], "etkin": True})
    return ogeler


def sinirla(x: int, y: int, cap: int, alan: tuple[int, int, int, int]) -> tuple[int, int]:
    """Düğmeyi çalışma alanının (x, y, en, boy) içinde tutar."""
    ax, ay, en, boy = alan
    return max(ax, min(ax + en - cap, int(x))), max(ay, min(ay + boy - cap, int(y)))


def yapis(x: int, y: int, cap: int, alan: tuple[int, int, int, int], bosluk: int) -> tuple[str, float]:
    """Bırakılan düğme en yakın yan kenara (sol/sağ) yapışır; dikey konum oran olarak saklanır (0 üst, 1 alt)."""
    ax, ay, en, boy = alan
    x, y = sinirla(x, y, cap, alan)
    kenar = "sol" if (x + cap / 2) < ax + en / 2 else "sag"
    yukseklik = max(1, boy - cap - 2 * bosluk)
    oran = (y - ay - bosluk) / yukseklik
    return kenar, round(max(0.0, min(1.0, oran)), 4)


def konum(kenar: str, oran: float, cap: int, alan: tuple[int, int, int, int], bosluk: int) -> tuple[int, int]:
    """Kenar + orandan pencere konumu. Varsayılan ("sag", 1.0): sağ alt köşe."""
    ax, ay, en, boy = alan
    x = ax + bosluk if kenar == "sol" else ax + en - cap - bosluk
    yukseklik = max(0, boy - cap - 2 * bosluk)
    y = ay + bosluk + round(max(0.0, min(1.0, oran)) * yukseklik)
    return sinirla(x, y, cap, alan)


def menu_konumu(dx: int, dy: int, cap: int, menu_en: int, menu_boy: int, alan: tuple[int, int, int, int],
                aralik: int) -> tuple[int, int]:  # fmt: skip
    """Menü düğmenin yanında, ekrana sığan yönde açılır: düğme sağ yarıdaysa soluna, değilse sağına;
    alt yarıdaysa menünün altı düğmenin altıyla, üst yarıdaysa üstü düğmenin üstüyle hizalanır.
    Sığmayan menü çalışma alanının içine itilir."""
    ax, ay, en, boy = alan
    if dx + cap / 2 >= ax + en / 2:
        x = dx - aralik - menu_en
        if x < ax:  # solda yer yok: düğmenin üstüne/altına taşmasın diye alanın soluna dayanır
            x = ax
    else:
        x = dx + cap + aralik
        if x + menu_en > ax + en:
            x = ax + en - menu_en
    y = dy + cap - menu_boy if dy + cap / 2 >= ay + boy / 2 else dy
    x = max(ax, min(ax + en - menu_en, x))
    y = max(ay, min(ay + boy - menu_boy, y))
    return int(x), int(y)


def surukleme_mi(dx: float, dy: float, esik: float) -> bool:
    """Basılan noktadan uzaklık (düz çizgi) eşiğe ulaştıysa sürüklemedir."""
    return math.hypot(dx, dy) >= esik


def fare_oykunmesi_mi(simdi: float, dokunma_suruyor: bool, son_dokunma: float) -> bool:
    """Fare basışı az önce işlenen (ya da süren) dokunuşun öykünmesi mi? Öyleyse yok sayılır."""
    return dokunma_suruyor or (simdi - son_dokunma) < DOKUNMA_GOLGESI_SN


def geri_sayim_metni(islem: str, kalan: int) -> tuple[str, str]:
    """Onay sayfası: başlık ve sayaç ("Tahta kapatılacak", "10")."""
    return GERI_SAYIM_BASLIK.get(islem, "Onaylayın"), str(max(0, int(kalan)))


def olcek_bul(en: int, boy: int) -> float:
    return ekran_olcegi(en, boy)


def ariza_komutu() -> list[str]:
    """Arıza bildirim penceresi ayrı süreçte açılır (menüdeki "Arıza bildir" kısayolla aynıdır)."""
    return [sys.executable, "-m", "tahta_ajan", "ariza"]


# ---- GTK ---------------------------------------------------------------------------------------
def kur(ekran):
    """Ekran yardımcısına bağlı yüzer düğmeyi kurar. `ekran`: ekran.py'deki Ekran nesnesi (baglanti ile)."""
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk, GLib, Gtk

    class YuzerDugme:
        def __init__(self):
            self.ekran = ekran
            self.ayar = dugme_ayari(None)
            self.istenen = False  # görünür olmalı mı (son guncelle çağrısı)
            self.kenar, self.oran = "sag", 1.0
            self.basili = None  # (kök x, kök y, pencere x, pencere y)
            self.suruklendi = False
            self.belirgin_bitis = 0.0
            self.menu_acik = False
            self.menu_dokunma = 0.0
            self.dokunma_dizisi = None
            self.dokunma_son = -DOKUNMA_GOLGESI_SN  # son dokunuşun bittiği an (monotonik)
            self.esik = SURUKLEME_ESIGI  # süren basışın sürükleme eşiği (fare ya da dokunma)
            self.geri_sayim = None  # (islem, bitis zamanı)
            self.ileti_bitis = 0.0
            self.olcek = None
            self.alan = (0, 0, 0, 0)
            self.cap = DUGME_CAP

            ekran_ = Gdk.Screen.get_default()
            self.bilesik = bool(ekran_.is_composited())
            self.olcu = Gtk.CssProvider()
            self.olcu.load_from_data(STIL)
            renk = Gtk.CssProvider()
            renk.load_from_data(RENK)
            # Ekran yardımcısının genel kurallarından (window, button, label) üstün olsun.
            for saglayici in (self.olcu, renk):
                Gtk.StyleContext.add_provider_for_screen(ekran_, saglayici, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)

            self.pencere = self._acilir_pencere("yd-pencere")
            self.dugme = Gtk.Button(label="☰")
            self.dugme.set_name("yd-dugme")
            self.dugme.set_can_focus(False)
            self.dugme.set_focus_on_click(False)
            self.dugme.set_relief(Gtk.ReliefStyle.NONE)
            self.dugme.get_style_context().add_class("soluk")
            if not self.bilesik:
                self.dugme.get_style_context().add_class("kati")
            # Basma/bırakma pencere düzeyinde izlenir (sürükleme ile dokunma ayrılsın diye).
            self.dugme.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK
                                  | Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.TOUCH_MASK)  # fmt: skip
            self.dugme.connect("button-press-event", self._basildi)
            self.dugme.connect("motion-notify-event", self._kaydi)
            self.dugme.connect("button-release-event", self._birakildi)
            self.dugme.connect("touch-event", self._dokunuldu)
            self.pencere.add(self.dugme)

            self.menu = self._acilir_pencere("yd-menu-pencere")
            self.menu_kutu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.menu_kutu.set_name("yd-menu")
            self.menu.add(self.menu_kutu)
            self.menu.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.TOUCH_MASK)
            self.menu.connect("button-press-event", self._menu_basildi)
            self._olcek_uygula()
            GLib.timeout_add(1000, self._saniye)

        def _acilir_pencere(self, ad):
            # POPUP + seat grab görev çubuğunun dokunma girdisini de ele
            # geçirebilir. Çerçevesiz olmak için override-redirect gerekmez.
            pencere = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
            pencere.set_name(ad)
            pencere.set_decorated(False)
            pencere.set_resizable(False)
            pencere.set_keep_above(True)
            pencere.set_accept_focus(False)
            pencere.set_focus_on_map(False)
            pencere.set_skip_taskbar_hint(True)
            pencere.set_skip_pager_hint(True)
            pencere.set_type_hint(Gdk.WindowTypeHint.UTILITY)
            # Yönetilen pencere yalnız açıldığı çalışma alanında görünürdü: bütün alanlarda dursun.
            pencere.stick()
            gorsel = pencere.get_screen().get_rgba_visual()
            if self.bilesik and gorsel is not None:
                pencere.set_visual(gorsel)  # köşeler saydam (yuvarlak düğme)
                pencere.set_app_paintable(True)
            else:
                # Bileşiksiz masaüstünde saydamlık yok: pencere zemini düğmeyle aynı renkte, köşeler düz.
                pencere.get_style_context().add_class("kati")
            return pencere

        # ---- ölçü ve konum ------------------------------------------------------------
        def _calisma_alani(self):
            """Birincil monitörün çalışma alanı (panel ve görev çubuğu dışı); çok ekranda yalnız birincil."""
            gosterge = Gdk.Display.get_default()
            monitor = gosterge.get_primary_monitor() or gosterge.get_monitor(0)
            alan = monitor.get_workarea()
            geo = monitor.get_geometry()
            return (alan.x, alan.y, alan.width, alan.height), (geo.width, geo.height)

        def _olcek_uygula(self):
            try:
                alan, (en, boy) = self._calisma_alani()
            except Exception:
                alan, (en, boy) = (0, 0, 1920, 1080), (1920, 1080)
            olcek = olcek_bul(en, boy)
            self.alan = alan
            if olcek != self.olcek:
                self.olcek = olcek
                self.olcu.load_from_data(olcekli_stil(STIL, olcek))
                self.cap = olcekle(DUGME_CAP, olcek)
                self.pencere.resize(self.cap, self.cap)
            self._yerlestir()

        def _o(self, piksel):
            return olcekle(piksel, self.olcek or 1.0)

        def _yerlestir(self):
            x, y = konum(self.kenar, self.oran, self.cap, self.alan, self._o(KENAR_BOSLUGU))
            self.pencere.move(x, y)

        def _konum(self):
            return self.pencere.get_position()

        # ---- görünürlük ----------------------------------------------------------------
        def guncelle(self, durum, ana_gorunur):
            """Ekran her çizimde çağırır."""
            yeni_ayar = dugme_ayari(durum)
            ayar_degisti = yeni_ayar != self.ayar
            self.ayar = yeni_ayar
            istenen = gorunur_mu(durum, ana_gorunur)
            if not istenen:
                self.gizle()
                return
            if self.menu_acik and not self.geri_sayim and ayar_degisti:
                self._menu_kur()  # ayar değişmiş olabilir (ör. kilit kodu kaldırıldı)
            if not self.istenen:
                self.istenen = True
                self._olcek_uygula()
                self.pencere.show_all()
                self._soluk(time.time() > self.belirgin_bitis)

        def gizle(self):
            """Tam ekran sayfa açılmadan önce yardımcı pencereleri gizler."""
            self.menu_kapat()
            if self.istenen:
                self.pencere.hide()
            self.istenen = False
            self.basili = None
            self.dokunma_dizisi = None

        def _soluk(self, soluk: bool):
            for baglam in (self.dugme.get_style_context(), self.pencere.get_style_context()):
                (baglam.add_class if soluk else baglam.remove_class)("soluk")
            if self.bilesik:
                self.pencere.set_opacity(SOLUK_SAYDAMLIK if soluk else 1.0)

        def ekran_degisti(self):
            self._olcek_uygula()
            if self.menu_acik:
                self._menu_yerlestir()

        # ---- dokunma ve sürükleme --------------------------------------------------------
        def _basildi(self, _w, olay):
            if fare_oykunmesi_mi(time.monotonic(), self.dokunma_dizisi is not None, self.dokunma_son):
                return True  # aynı dokunuş touch-event ile işlendi/işleniyor: ikinci kez sayılmaz
            if olay.type != Gdk.EventType.BUTTON_PRESS:
                return True  # çift tıklama olayları yok sayılır
            if olay.button != 1:
                return False
            return self._baslat(olay.x_root, olay.y_root)

        def _baslat(self, kok_x, kok_y, dokunma=False):
            x, y = self._konum()
            self.basili = (kok_x, kok_y, x, y)
            self.esik = DOKUNMA_ESIGI if dokunma else SURUKLEME_ESIGI
            self.suruklendi = False
            self.belirgin_bitis = time.time() + BELIRGIN_SN
            self._soluk(False)
            return True

        def _kaydi(self, _w, olay):
            if not self.basili:
                return False
            kx, ky, px, py = self.basili
            dx, dy = olay.x_root - kx, olay.y_root - ky
            if not self.suruklendi and not surukleme_mi(dx, dy, self._o(self.esik)):
                return True
            if not self.suruklendi:
                self.suruklendi = True
                self.menu_kapat()
            self.pencere.move(*sinirla(px + dx, py + dy, self.cap, self.alan))
            return True

        def _birakildi(self, _w, olay):
            if self.dokunma_dizisi is not None:
                return True
            if olay.button != 1:
                return False
            return self._bitir()

        def _dokunuldu(self, _w, olay):
            # XI2 dokunma dizisini doğrudan işleriz; fare öykünmesine bağlı
            # kalmayız. True, aynı dokunuşun iki kez düğme sayılmasını önler.
            dizi = olay.get_event_sequence()
            if olay.type == Gdk.EventType.TOUCH_BEGIN:
                if self.dokunma_dizisi is None:
                    self.dokunma_dizisi = dizi
                    # Öykünülmüş fare basışı dokunmadan önce geldiyse basış dokunma olarak yeniden başlar.
                    self._baslat(olay.x_root, olay.y_root, dokunma=True)
            elif dizi == self.dokunma_dizisi:
                if olay.type == Gdk.EventType.TOUCH_UPDATE:
                    self._kaydi(_w, olay)
                elif olay.type == Gdk.EventType.TOUCH_END:
                    self.dokunma_dizisi = None
                    self.dokunma_son = time.monotonic()
                    self._bitir()
                elif olay.type == Gdk.EventType.TOUCH_CANCEL:
                    self.dokunma_dizisi = None
                    self.dokunma_son = time.monotonic()
                    self._bitir(iptal=True)
            return True

        def _bitir(self, iptal=False):
            if not self.basili:
                return True
            self.basili = None
            self.belirgin_bitis = time.time() + BELIRGIN_SN
            if self.suruklendi:
                # İptal edilen sürüklemede de düğme ekranın ortasında kalmaz, kenara yapışır.
                x, y = self._konum()
                self.kenar, self.oran = yapis(x, y, self.cap, self.alan, self._o(KENAR_BOSLUGU))
                self._yerlestir()
                return True
            if iptal:
                return True
            if self.menu_acik:
                self.menu_kapat()
            else:
                self.menu_ac()
            return True

        # ---- menü -------------------------------------------------------------------------
        def menu_ac(self):
            self.menu_acik = True
            self.geri_sayim = None
            self.menu_dokunma = time.time()
            self._menu_kur()
            self.menu.show_all()
            self._ileti_gizle()
            self._menu_yerlestir()

        def menu_kapat(self):
            if self.menu_acik:
                self.menu.hide()
            self.menu_acik = False
            self.geri_sayim = None

        def _menu_basildi(self, _w, olay):
            # Olay child GdkWindow'dan gelebilir. Pencere kimliğiyle dışarı
            # sayıp press anında kapatmak GtkButton.clicked'i engeller.
            self.menu_dokunma = time.time()
            return False

        def _temizle(self):
            for cocuk in self.menu_kutu.get_children():
                cocuk.destroy()

        def _menu_dugmesi(self, metin, islev, ad=None, etkin=True):
            dugme = Gtk.Button(label=metin)
            dugme.set_can_focus(False)
            dugme.set_focus_on_click(False)
            if ad:
                dugme.set_name(ad)
            dugme.set_sensitive(etkin)
            dugme.connect("clicked", lambda *_: islev())
            dugme.get_child().set_xalign(0)
            return dugme

        def _menu_kur(self):
            self._temizle()
            self.menu_kutu.set_spacing(self._o(8))
            self.ileti = Gtk.Label(label="")
            self.ileti.set_name("yd-ileti")
            self.ileti.set_line_wrap(True)
            self.ileti.set_max_width_chars(28)
            self.menu_kutu.pack_start(self.ileti, False, False, 0)
            for oge in menu_ogeleri(self.ayar):
                dugme = self._menu_dugmesi(oge["etiket"], lambda i=oge["islem"]: self._sec(i), etkin=oge["etkin"])
                self.menu_kutu.pack_start(dugme, False, False, 0)
            self.menu_kutu.pack_start(self._menu_dugmesi("Menüyü kapat", self.menu_kapat), False, False, 0)
            self.menu_kutu.show_all()
            self._ileti_gizle()
            if self.menu_acik:
                self._menu_yerlestir()

        def _ileti_gizle(self):
            if getattr(self, "ileti", None) is not None and time.time() >= self.ileti_bitis:
                self.ileti.set_visible(False)

        def _menu_yerlestir(self):
            self.menu.resize(1, 1)  # içerik değişince küçülebilsin
            _, dogal = self.menu.get_preferred_size()
            en, boy = dogal.width, dogal.height
            x, y = self._konum()
            self.menu.move(*menu_konumu(x, y, self.cap, en, boy, self.alan, self._o(MENU_ARALIGI)))

        def _sec(self, islem):
            self.menu_dokunma = time.time()
            if islem == "kilitle":
                gitti = self.ekran.baglanti.gonder({"tur": "yerel_kilitle"})
                self.menu_kapat()
                if not gitti:
                    self.sonuc({"basarili": False, "mesaj": ILETI_SERVIS_YOK})
            elif islem in ONAYLI:
                self._geri_sayim_baslat(islem)
            elif islem == "ariza":
                self.menu_kapat()
                try:
                    subprocess.Popen(ariza_komutu(), start_new_session=True, close_fds=True, cwd="/",
                                     env=dict(os.environ), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
                except OSError as hata:
                    print(f"Arıza penceresi açılamadı: {hata}", file=sys.stderr)
            elif islem == "yoklama":
                self.menu_kapat()
                self.ekran.baglanti.gonder({"tur": "yoklama_ac"})

        def _geri_sayim_baslat(self, islem):
            self.geri_sayim = (islem, time.time() + GERI_SAYIM_SN)
            self._temizle()
            baslik, sayac = geri_sayim_metni(islem, GERI_SAYIM_SN)
            self.gs_baslik = Gtk.Label(label=baslik)
            self.gs_baslik.set_name("yd-baslik")
            self.gs_sayac = Gtk.Label(label=sayac)
            self.gs_sayac.set_name("yd-sayac")
            vazgec = self._menu_dugmesi("Vazgeç", self._vazgec, ad="yd-vazgec")
            vazgec.get_child().set_xalign(0.5)
            for parca in (self.gs_baslik, self.gs_sayac, vazgec):
                self.menu_kutu.pack_start(parca, False, False, 0)
            self.menu_kutu.show_all()
            self._menu_yerlestir()

        def _vazgec(self):
            self.menu_kapat()

        def sonuc(self, mesaj):
            """Servisin dugme_sonuc yanıtı: başarısızsa ileti düğmenin yanında kısa süre görünür."""
            if mesaj.get("basarili"):
                return
            if not self.istenen:
                return
            if not self.menu_acik:
                self.menu_ac()
            self.ileti.set_text(str(mesaj.get("mesaj") or "İşlem yapılamadı.")[:200])
            self.ileti.set_visible(True)
            self.ileti_bitis = time.time() + 6
            self.menu_dokunma = time.time()
            self._menu_yerlestir()

        # ---- saniye ----------------------------------------------------------------------
        def _saniye(self):
            simdi = time.time()
            if self.geri_sayim and self.menu_acik:
                islem, bitis = self.geri_sayim
                kalan = math.ceil(bitis - simdi - 0.05)
                if kalan <= 0:
                    self.geri_sayim = None
                    gitti = self.ekran.baglanti.gonder({"tur": "yerel_" + islem})
                    self.menu_kapat()
                    if not gitti:
                        self.sonuc({"basarili": False, "mesaj": ILETI_SERVIS_YOK})
                else:
                    self.gs_sayac.set_text(geri_sayim_metni(islem, kalan)[1])
            elif self.menu_acik and simdi - self.menu_dokunma > MENU_KAPANMA_SN:
                self.menu_kapat()
            elif self.menu_acik:
                self._ileti_gizle()
            if self.istenen and not self.basili:
                if not self.menu_acik:
                    self._soluk(simdi > self.belirgin_bitis)
                # Küçük yardımcı pencere, sonradan öne gelen pencerelerin altında kalmasın.
                gdk = self.pencere.get_window()
                if gdk is not None:
                    gdk.raise_()
                if self.menu_acik and self.menu.get_window() is not None:
                    self.menu.get_window().raise_()
            return True

    return YuzerDugme()
