"""ETAP olay akışı: GTK taklidiyle gerçek geri çağrılar; sistem girdisi tutulmaz.

Taklit sınıflar yalnız `IZINLI` listesindeki ve kendi tanımladıkları yöntemleri kabul eder; yuzer.py
gerçek GTK'da olmayan bir yöntem çağırırsa test düşer. Listelerin gerçek GTK sınıflarıyla tutarlılığı ve
gerçek pencereyle duman testi dosyanın sonundadır: PyGObject (ve duman testi için X ekranı) yoksa
atlanır; Docker'da (debian:12 + python3-gi + xvfb) çalışır.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest

from tahta_ajan import yuzer


class Parca:
    """Gerçek sınıfta (GERCEK) bulunan yöntemlerin dar bir alt kümesi; fazlası AttributeError verir."""

    GERCEK = ""
    IZINLI: tuple[str, ...] = ()

    def __init__(self, *args, **kwargs):
        self.tur = kwargs.get("type")
        self.etiket = kwargs.get("label")
        self.cocuklar = []
        self.sinyaller = {}
        self.ozellikler = {}
        self.cagrilar = []
        self.siniflar = set()
        self.xy = (0, 0)
        self.gorunur = False
        self.ebeveyn = None

    def __getattr__(self, ad):
        if ad in type(self).IZINLI:
            def cagri(*deger):
                self.cagrilar.append(ad)
                if ad.startswith("set_"):
                    self.ozellikler[ad] = deger
            return cagri
        raise AttributeError(f"{type(self).__name__}.{ad}: taklitte yok (gerçek GTK'da var mı?)")

    def connect(self, sinyal, islev):
        self.sinyaller[sinyal] = islev

    def get_style_context(self):
        if not hasattr(self, "_baglam"):
            self._baglam = Baglam()
        return self._baglam

    def destroy(self):
        if self.ebeveyn is not None and self in self.ebeveyn.cocuklar:
            self.ebeveyn.cocuklar.remove(self)  # gerçek GTK'da yok edilen parça kapsayıcıdan çıkar

    def show_all(self):
        self.gorunur = True

    def hide(self):
        self.gorunur = False


class Baglam(Parca):
    GERCEK = "Gtk.StyleContext"

    def add_class(self, ad):
        self.siniflar.add(ad)

    def remove_class(self, ad):
        self.siniflar.discard(ad)


class GdkPencere(Parca):
    GERCEK = "Gdk.Window"
    IZINLI = ("raise_",)


class Pencere(Parca):
    GERCEK = "Gtk.Window"
    IZINLI = ("set_name", "set_decorated", "set_resizable", "set_keep_above", "set_accept_focus", "set_focus_on_map",
              "set_skip_taskbar_hint", "set_skip_pager_hint", "set_type_hint", "set_visual", "set_app_paintable",
              "set_opacity", "stick", "add_events", "resize")  # fmt: skip

    def get_screen(self):
        return SimpleNamespace(get_rgba_visual=lambda: None)

    def add(self, cocuk):
        self.cocuklar.append(cocuk)
        cocuk.ebeveyn = self

    def move(self, x, y):
        self.xy = (x, y)

    def get_position(self):
        return self.xy

    def get_preferred_size(self):
        return None, SimpleNamespace(width=260, height=300)

    def get_window(self):
        if not hasattr(self, "_gdk"):
            self._gdk = GdkPencere()
        return self._gdk


class Etiket(Parca):
    GERCEK = "Gtk.Label"
    IZINLI = ("set_name", "set_line_wrap", "set_max_width_chars", "set_text", "set_visible", "set_xalign")


class Dugme(Parca):
    GERCEK = "Gtk.Button"
    IZINLI = ("set_name", "set_can_focus", "set_focus_on_click", "set_relief", "set_sensitive", "add_events")

    def get_child(self):
        if not hasattr(self, "_etiket"):
            self._etiket = Etiket(label=self.etiket)
        return self._etiket


class Kutu(Parca):
    GERCEK = "Gtk.Box"
    IZINLI = ("set_name", "set_spacing")

    def pack_start(self, cocuk, genis, doldur, dolgu):
        self.cocuklar.append(cocuk)
        cocuk.ebeveyn = self

    def get_children(self):
        return list(self.cocuklar)


class Saglayici(Parca):
    GERCEK = "Gtk.CssProvider"
    IZINLI = ("load_from_data",)


TAKLITLER = (Baglam, GdkPencere, Pencere, Etiket, Dugme, Kutu, Saglayici)


@pytest.fixture
def dugme(monkeypatch):
    def sistem_girdisi_yasak():
        raise AssertionError("Yüzer düğme masaüstünün girdisini tutamaz")

    alan = SimpleNamespace(x=0, y=0, width=1920, height=1040)
    monitor = SimpleNamespace(get_workarea=lambda: alan,
                              get_geometry=lambda: SimpleNamespace(width=1920, height=1080))
    gosterge = SimpleNamespace(get_primary_monitor=lambda: monitor, get_monitor=lambda _: monitor,
                              get_default_seat=sistem_girdisi_yasak)
    olaylar = SimpleNamespace(BUTTON_PRESS="bas", TOUCH_BEGIN="dokun", TOUCH_UPDATE="kay",
                             TOUCH_END="birak", TOUCH_CANCEL="iptal")
    gdk = SimpleNamespace(Screen=SimpleNamespace(get_default=lambda: SimpleNamespace(is_composited=lambda: False)),
                          Display=SimpleNamespace(get_default=lambda: gosterge), EventType=olaylar,
                          WindowTypeHint=SimpleNamespace(UTILITY="yardimci-ipucu"),
                          EventMask=SimpleNamespace(BUTTON_PRESS_MASK=1, BUTTON_RELEASE_MASK=2,
                                                    POINTER_MOTION_MASK=4, TOUCH_MASK=8))
    gtk = SimpleNamespace(Window=Pencere, Button=Dugme, Box=Kutu, Label=Etiket, CssProvider=Saglayici,
                          WindowType=SimpleNamespace(TOPLEVEL="yardimci"),
                          StyleContext=SimpleNamespace(add_provider_for_screen=lambda *args: None),
                          STYLE_PROVIDER_PRIORITY_APPLICATION=600, Orientation=SimpleNamespace(VERTICAL=1),
                          ReliefStyle=SimpleNamespace(NONE=0))
    glib = SimpleNamespace(timeout_add=lambda *args: None)
    monkeypatch.setitem(sys.modules, "gi", SimpleNamespace(require_version=lambda *args: None))
    monkeypatch.setitem(sys.modules, "gi.repository", SimpleNamespace(Gtk=gtk, Gdk=gdk, GLib=glib))
    nesne = yuzer.kur(SimpleNamespace(baglanti=SimpleNamespace(gonder=lambda _: True)))
    durum = {"dugme": {"acik": True, "islemler": ["kilitle", "kapat"], "kilitle_kullanilabilir": True}}
    nesne.guncelle(durum, False)
    return nesne, durum, olaylar


def dokunma(tur, x=1800, y=900, dizi="ilk"):
    return SimpleNamespace(type=tur, x_root=x, y_root=y, get_event_sequence=lambda: dizi)


def gecir(nesne, saniye):
    """Son dokunuşun üzerinden `saniye` geçmiş gibi yapar (genel saati yamalamadan)."""
    nesne.dokunma_son -= saniye


def fare(olaylar, x=1800, y=900):
    return SimpleNamespace(type=olaylar.BUTTON_PRESS, button=1, x_root=x, y_root=y)


def test_menu_masaustu_girdisini_tutmadan_acilir_kapanir(dugme):
    nesne, _, _ = dugme
    for pencere in (nesne.pencere, nesne.menu):
        assert pencere.tur == "yardimci"
        assert pencere.ozellikler["set_accept_focus"] == (False,)
        assert pencere.ozellikler["set_decorated"] == (False,)
    nesne.menu_ac()
    assert nesne.menu_acik and nesne.menu.gorunur
    kapat = next(cocuk for cocuk in nesne.menu_kutu.cocuklar if cocuk.etiket == "Menüyü kapat")
    kapat.sinyaller["clicked"](kapat)
    assert not nesne.menu_acik and not nesne.menu.gorunur


def test_pencereler_butun_calisma_alanlarinda_ve_gorev_cubugu_disinda(dugme):
    """Yönetilen pencere yalnız açıldığı çalışma alanında görünürdü (0.13.0): stick + atlama ipuçları."""
    nesne, _, _ = dugme
    for pencere in (nesne.pencere, nesne.menu):
        assert "stick" in pencere.cagrilar
        assert pencere.ozellikler["set_skip_taskbar_hint"] == (True,)
        assert pencere.ozellikler["set_skip_pager_hint"] == (True,)
        assert pencere.ozellikler["set_keep_above"] == (True,)
        assert pencere.ozellikler["set_focus_on_map"] == (False,)
        assert pencere.ozellikler["set_type_hint"] == ("yardimci-ipucu",)


def test_girdi_tutma_geri_gelmez():
    from pathlib import Path

    kaynak = Path(yuzer.__file__).read_text(encoding="utf-8")
    for yasak in ("seat.grab", ".grab(", "grab_add", "WindowType.POPUP", ".present("):
        assert yasak not in kaynak, yasak


def test_menu_alt_penceresine_basma_menuyu_erkenden_kapatmaz(dugme):
    nesne, _, _ = dugme
    nesne.menu_ac()
    assert nesne._menu_basildi(None, SimpleNamespace(window=object(), x=9999, y=9999)) is False
    assert nesne.menu_acik


def test_silik_dugme_fareyle_tiklanabilir(dugme):
    nesne, _, olaylar = dugme
    nesne._soluk(True)
    nesne._basildi(None, fare(olaylar))
    nesne._birakildi(None, SimpleNamespace(button=1))
    assert nesne.menu_acik


def test_menu_zaman_asimi_islem_gondermeden_kapanir(dugme, monkeypatch):
    nesne, _, _ = dugme
    gonderilen = []
    nesne.ekran.baglanti.gonder = gonderilen.append
    nesne.menu_ac()
    monkeypatch.setattr(yuzer.time, "time", lambda: nesne.menu_dokunma + yuzer.MENU_KAPANMA_SN + 1)
    nesne._saniye()
    assert not nesne.menu_acik and not gonderilen


def test_ayni_durum_mesaji_menu_dugmelerini_yeniden_olusturmaz(dugme):
    nesne, durum, _ = dugme
    nesne.menu_ac()
    onceki = nesne.menu_kutu.get_children()
    nesne.guncelle(durum, False)
    assert nesne.menu_kutu.get_children() == onceki


def test_dokunma_fare_oykunmesi_olmadan_menuyu_acar_ikinci_parmak_karismaz(dugme):
    nesne, _, olaylar = dugme
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_BEGIN))
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_BEGIN, dizi="ikinci"))
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_END, dizi="ikinci"))
    assert not nesne.menu_acik
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_END))
    assert nesne.menu_acik and nesne.dokunma_dizisi is None


def test_dokunustan_sonra_gelen_fare_oykunmesi_menuyu_geri_kapatmaz(dugme):
    """GTK dokunmayı işaretçi olayına da çevirebilir: aynı dokunuş menüyü açıp hemen kapatmamalı."""
    nesne, _, olaylar = dugme
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_BEGIN))
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_END))
    assert nesne.menu_acik
    # Öykünülmüş basış/bırakış dokunuşun hemen ardından gelir.
    nesne._basildi(None, fare(olaylar))
    nesne._birakildi(None, SimpleNamespace(button=1))
    assert nesne.menu_acik and nesne.basili is None
    # Gölge süresi geçince gerçek fare tıklaması yine çalışır.
    gecir(nesne, yuzer.DOKUNMA_GOLGESI_SN + 0.1)
    nesne._basildi(None, fare(olaylar))
    nesne._birakildi(None, SimpleNamespace(button=1))
    assert not nesne.menu_acik


@pytest.mark.parametrize("sira", [
    ("bas", "dokun", "dokun-son", "birak"),  # öykünme dokunmayı sarar
    ("dokun", "bas", "birak", "dokun-son"),  # öykünme dokunmanın içinde
    ("bas", "dokun", "birak", "dokun-son"),
    ("dokun", "bas", "dokun-son", "birak"),
])
def test_ic_ice_gelen_dokunma_ve_fare_olaylari_tek_dokunus_sayilir(dugme, sira):
    nesne, _, olaylar = dugme
    adimlar = {
        "bas": lambda: nesne._basildi(None, fare(olaylar)),
        "birak": lambda: nesne._birakildi(None, SimpleNamespace(button=1)),
        "dokun": lambda: nesne._dokunuldu(None, dokunma(olaylar.TOUCH_BEGIN)),
        "dokun-son": lambda: nesne._dokunuldu(None, dokunma(olaylar.TOUCH_END)),
    }
    for adim in sira:
        adimlar[adim]()
    assert nesne.menu_acik and nesne.basili is None and nesne.dokunma_dizisi is None


def test_iptal_edilen_dokunma_islem_baslatmaz(dugme):
    nesne, _, olaylar = dugme
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_BEGIN))
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_CANCEL))
    assert nesne.basili is None and not nesne.menu_acik


def test_iptal_edilen_surukleme_dugmeyi_kenara_yapistirir(dugme):
    nesne, _, olaylar = dugme
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_BEGIN))
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_UPDATE, x=900))
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_CANCEL, x=900))
    assert not nesne.menu_acik and nesne.basili is None
    assert nesne.pencere.xy == yuzer.konum(nesne.kenar, nesne.oran, nesne.cap, nesne.alan, yuzer.KENAR_BOSLUGU)


def test_suruklenen_dokunma_menu_acmaz(dugme):
    nesne, _, olaylar = dugme
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_BEGIN))
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_UPDATE, x=300))
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_END, x=300))
    assert nesne.kenar == "sol" and not nesne.menu_acik


def test_parmak_titremesi_surukleme_sayilmaz_fare_esigi_daha_dardir(dugme):
    nesne, _, olaylar = dugme
    ilk = nesne.pencere.xy
    titreme = yuzer.SURUKLEME_ESIGI + 6  # fare eşiğini aşar, dokunma eşiğinin altındadır
    assert titreme < yuzer.DOKUNMA_ESIGI
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_BEGIN))
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_UPDATE, x=1800 + titreme))
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_UPDATE, x=1800 - 9, y=900 + 12))
    nesne._dokunuldu(None, dokunma(olaylar.TOUCH_END, x=1800 + 3))
    assert nesne.menu_acik and nesne.pencere.xy == ilk
    nesne.menu_kapat()
    gecir(nesne, 5)
    # Aynı kayma fareyle sürüklemedir.
    nesne._basildi(None, fare(olaylar))
    nesne._kaydi(None, SimpleNamespace(x_root=1800 - titreme, y_root=900))
    nesne._birakildi(None, SimpleNamespace(button=1))
    assert not nesne.menu_acik


def test_esik_saf_islevleri():
    assert not yuzer.surukleme_mi(10, 10, 28) and yuzer.surukleme_mi(20, 20, 28)
    assert yuzer.fare_oykunmesi_mi(10.0, True, -100.0)
    assert yuzer.fare_oykunmesi_mi(10.0, False, 10.0 - yuzer.DOKUNMA_GOLGESI_SN / 2)
    assert not yuzer.fare_oykunmesi_mi(10.0, False, 10.0 - yuzer.DOKUNMA_GOLGESI_SN - 0.1)


def test_taklit_olmayan_yontemi_reddeder():
    with pytest.raises(AttributeError):
        Pencere().set_olmayan_ozellik(True)


# ---- gerçek GTK (PyGObject yoksa atlanır) ------------------------------------------------------
def _gercek_gtk():
    for ad in ("gi", "gi.repository"):
        if isinstance(sys.modules.get(ad), SimpleNamespace):  # taklit fikstüründen kalmış olmasın
            del sys.modules[ad]
    gi = pytest.importorskip("gi")
    try:
        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, Gtk
    except (ValueError, ImportError):
        pytest.skip("GTK3 yok")
    return Gdk, Gtk


def test_taklit_siniflar_gercek_gtk_ile_tutarli():
    """Taklidin kabul ettiği her yöntem gerçek sınıfta da vardır (yazım hatası taklitte saklanmasın)."""
    Gdk, Gtk = _gercek_gtk()
    moduller = {"Gtk": Gtk, "Gdk": Gdk}
    for taklit in TAKLITLER:
        modul, ad = taklit.GERCEK.split(".")
        gercek = getattr(moduller[modul], ad)
        kendi = [a for a in vars(taklit) if not a.startswith("_") and callable(vars(taklit)[a])]
        ortak = () if modul == "Gdk" or ad in ("StyleContext", "CssProvider") else ("get_style_context", "destroy",
                                                                                 "show_all", "hide")  # fmt: skip
        for yontem in (*taklit.IZINLI, *kendi, *ortak, "connect"):
            assert hasattr(gercek, yontem), f"{taklit.GERCEK}.{yontem}"
    for sabit in ("BUTTON_PRESS", "TOUCH_BEGIN", "TOUCH_UPDATE", "TOUCH_END", "TOUCH_CANCEL"):
        assert hasattr(Gdk.EventType, sabit)
    for sabit in ("BUTTON_PRESS_MASK", "BUTTON_RELEASE_MASK", "POINTER_MOTION_MASK", "TOUCH_MASK"):
        assert hasattr(Gdk.EventMask, sabit)
    assert hasattr(Gdk.WindowTypeHint, "UTILITY") and hasattr(Gtk.WindowType, "TOPLEVEL")


def test_gercek_gtk_ile_duman():
    """Gerçek pencere: kurulur, görünür, menü açılıp kapanır, gerçek olay nesneleriyle basış işlenir."""
    Gdk, Gtk = _gercek_gtk()
    if not os.environ.get("DISPLAY"):
        pytest.skip("X ekranı yok")
    acildi = Gtk.init_check([])
    if not (acildi[0] if isinstance(acildi, tuple) else acildi):
        pytest.skip("X ekranı açılamadı")
    gonderilen = []
    nesne = yuzer.kur(SimpleNamespace(baglanti=SimpleNamespace(gonder=lambda m: gonderilen.append(m) or True)))

    def pompala():
        for _ in range(50):
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)

    durum = {"dugme": {"acik": True, "islemler": ["kilitle", "kapat", "ariza"], "kilitle_kullanilabilir": True}}
    try:
        nesne.guncelle(durum, False)
        pompala()
        for pencere in (nesne.pencere, nesne.menu):
            assert pencere.get_window_type() == Gtk.WindowType.TOPLEVEL
            assert pencere.get_type_hint() == Gdk.WindowTypeHint.UTILITY
            assert not pencere.get_decorated() and not pencere.get_accept_focus() and not pencere.get_focus_on_map()
            assert pencere.get_skip_taskbar_hint() and pencere.get_skip_pager_hint()
        assert nesne.pencere.get_visible() and not nesne.menu.get_visible()

        # Gerçek olay nesneleri (sinyal işleyicisine gelen üye yapılar): yuzer'in okuduğu alanlar vardır.
        # (Birleşim nesnesi değişkende tutulur: üye yapı onun belleğini gösterir.)
        bas_olayi = Gdk.Event.new(Gdk.EventType.BUTTON_PRESS)
        bas = bas_olayi.button
        bas.button, bas.x_root, bas.y_root = 1, 100.0, 100.0
        assert nesne._basildi(nesne.dugme, bas) is True and nesne.basili is not None
        birak_olayi = Gdk.Event.new(Gdk.EventType.BUTTON_RELEASE)
        birak = birak_olayi.button
        birak.button = 1
        nesne._birakildi(nesne.dugme, birak)
        pompala()
        assert nesne.menu_acik and nesne.menu.get_visible()
        dokun_olayi = Gdk.Event.new(Gdk.EventType.TOUCH_BEGIN)
        dokun = dokun_olayi.touch
        assert dokun.type == Gdk.EventType.TOUCH_BEGIN and dokun.x_root == 0.0 and dokun.y_root == 0.0
        dokun.get_event_sequence()

        etiketler = [c.get_label() for c in nesne.menu_kutu.get_children() if isinstance(c, Gtk.Button)]
        assert etiketler == ["Kilitle", "Kapat", "Arıza bildir", "Menüyü kapat"]
        nesne._saniye()
        kapat = next(c for c in nesne.menu_kutu.get_children() if isinstance(c, Gtk.Button) and c.get_label() == "Kapat")
        kapat.clicked()  # geri sayım sayfası
        pompala()
        assert nesne.geri_sayim and nesne.gs_sayac.get_text() == str(yuzer.GERI_SAYIM_SN)
        nesne._vazgec()
        nesne.menu_ac()
        next(c for c in nesne.menu_kutu.get_children()
             if isinstance(c, Gtk.Button) and c.get_label() == "Kilitle").clicked()
        assert gonderilen == [{"tur": "yerel_kilitle"}] and not nesne.menu_acik
        nesne.sonuc({"basarili": False, "mesaj": "Deneme iletisi"})
        pompala()
        assert nesne.menu_acik and nesne.ileti.get_visible()
        nesne.guncelle(durum, True)  # tam ekran sayfa açıldı
        pompala()
        assert not nesne.pencere.get_visible() and not nesne.menu.get_visible()
    finally:
        nesne.menu.destroy()
        nesne.pencere.destroy()
