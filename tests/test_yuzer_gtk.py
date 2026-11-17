"""ETAP olay akışı: GTK taklidiyle gerçek geri çağrılar; sistem girdisi tutulmaz."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from tahta_ajan import yuzer


class Parca:
    def __init__(self, *args, **kwargs):
        self.tur = kwargs.get("type")
        self.etiket = kwargs.get("label")
        self.cocuklar = []
        self.sinyaller = {}
        self.ozellikler = {}
        self.xy = (0, 0)
        self.gorunur = False

    def __getattr__(self, ad):
        if ad.startswith("set_"):
            return lambda *deger: self.ozellikler.update({ad: deger})
        if ad in ("add_events", "add_class", "remove_class", "load_from_data", "resize", "raise_"):
            return lambda *args: None
        raise AttributeError(ad)

    def get_style_context(self):
        return self

    def connect(self, sinyal, islev):
        self.sinyaller[sinyal] = islev

    def get_screen(self):
        return SimpleNamespace(get_rgba_visual=lambda: None)

    def add(self, cocuk):
        self.cocuklar.append(cocuk)

    def pack_start(self, cocuk, *args):
        self.add(cocuk)

    def get_children(self):
        return list(self.cocuklar)

    def get_child(self):
        return self

    def destroy(self):
        pass

    def move(self, x, y):
        self.xy = (x, y)

    def get_position(self):
        return self.xy

    def get_preferred_size(self):
        return None, SimpleNamespace(width=260, height=300)

    def show_all(self):
        self.gorunur = True

    def hide(self):
        self.gorunur = False

    def get_window(self):
        return self


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
                          WindowTypeHint=SimpleNamespace(UTILITY=1),
                          EventMask=SimpleNamespace(BUTTON_PRESS_MASK=1, BUTTON_RELEASE_MASK=2,
                                                    POINTER_MOTION_MASK=4, TOUCH_MASK=8))
    gtk = SimpleNamespace(Window=Parca, Button=Parca, Box=Parca, Label=Parca, CssProvider=Parca,
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


def test_menu_alt_penceresine_basma_menuyu_erkenden_kapatmaz(dugme):
    nesne, _, _ = dugme
    nesne.menu_ac()
    assert nesne._menu_basildi(None, SimpleNamespace(window=object(), x=9999, y=9999)) is False
    assert nesne.menu_acik


def test_silik_dugme_fareyle_tiklanabilir(dugme):
    nesne, _, olaylar = dugme
    nesne._soluk(True)
    nesne._basildi(None, SimpleNamespace(type=olaylar.BUTTON_PRESS, button=1, x_root=1800, y_root=900))
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
    def olay(tur, dizi):
        return SimpleNamespace(type=tur, x_root=1800, y_root=900, get_event_sequence=lambda: dizi)
    nesne._dokunuldu(None, olay(olaylar.TOUCH_BEGIN, "ilk"))
    nesne._dokunuldu(None, olay(olaylar.TOUCH_BEGIN, "ikinci"))
    nesne._dokunuldu(None, olay(olaylar.TOUCH_END, "ikinci"))
    assert not nesne.menu_acik
    nesne._dokunuldu(None, olay(olaylar.TOUCH_END, "ilk"))
    assert nesne.menu_acik and nesne.dokunma_dizisi is None


def test_iptal_edilen_dokunma_islem_baslatmaz(dugme):
    nesne, _, olaylar = dugme
    def olay(tur):
        return SimpleNamespace(type=tur, x_root=1800, y_root=900, get_event_sequence=lambda: "ilk")
    nesne._dokunuldu(None, olay(olaylar.TOUCH_BEGIN))
    nesne._dokunuldu(None, olay(olaylar.TOUCH_CANCEL))
    assert nesne.basili is None and not nesne.menu_acik


def test_suruklenen_dokunma_menu_acmaz(dugme):
    nesne, _, olaylar = dugme
    def olay(tur, x):
        return SimpleNamespace(type=tur, x_root=x, y_root=900, get_event_sequence=lambda: "ilk")
    nesne._dokunuldu(None, olay(olaylar.TOUCH_BEGIN, 1800))
    nesne._dokunuldu(None, olay(olaylar.TOUCH_UPDATE, 300))
    nesne._dokunuldu(None, olay(olaylar.TOUCH_END, 300))
    assert nesne.kenar == "sol" and not nesne.menu_acik
