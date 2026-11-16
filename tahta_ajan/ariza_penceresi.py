"""Arıza bildirim penceresi (A6): öğretmen tahtanın arızasını menüdeki "Arıza bildir" ile bildirir.

Kullanıcının yetkisiyle çalışan kısa ömürlü bir GTK3 penceresidir; `ekran.py`'den ayrı süreçtir
(ekran yardımcısının sayfa yığınına dokunmaz). Servise yerel soketle bağlanır, önce kendini
`{"tur":"merhaba","arayuz":"komut"}` ile tanıtır (servis bu bağlantıyı ekran saymaz ve ona durum
yayını göndermez), sonra tek bir `ariza` iletisi yollar ve `ariza_sonuc` yanıtını bekler.

Pencere tahtanın adını, dersliğini, eski arıza kayıtlarını BİLMEZ ve göstermez: tahta herkese
açık ekrandır. Sır (tahta anahtarı, kilit kodu özeti) pencereye hiç gelmez; yalnız sonuç iletisi.
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time

from . import __version__, ayar

# Tahtadan bildirilebilen türler (sunucudaki ARIZA_KATEGORI ile aynı ad ve sıra; "acilis" yalnız panelden).
KATEGORILER = (
    ("dokunmatik", "Dokunmatik çalışmıyor / kayıyor"),
    ("goruntu", "Görüntü sorunu"),
    ("ses", "Ses yok / bozuk"),
    ("kalem", "Kalem / uzaktan kumanda"),
    ("ag", "Ağ / internet yok"),
    ("yazilim", "Program ya da hesap sorunu"),
    ("fiziksel", "Fiziksel hasar (kırık, kablo, bağlantı)"),
    ("diger", "Diğer"),
)
ACIKLAMA_EN_UZUN = 300
BASLIK = "Tahtanın arızasını bildir"
NOT_METNI = "Kişi adı yazmayın. Bu kayıt yalnız tahtanın bakımı içindir."
ILETI_SERVIS_YOK = "Tahta Kontrol servisi çalışmıyor; arıza bildirilemedi."
ILETI_YANIT_YOK = "Tahta Kontrol servisi yanıt vermedi; arıza bildirilemedi. Biraz sonra yeniden deneyin."
YANIT_SN = 10  # servis en çok 5 sn sunucunun "aldım" yanıtını bekler; 10 sn yeter
KAPANMA_SN = 6  # başarılı bildirimden sonra pencere bu kadar saniye sonra kendiliğinden kapanır

# Ölçüler (renkler ekran.renk_stili ile ayrı sağlayıcıda; ASCII).
STIL_OLCU = b"""
#ariza-baslik { font-size: 40px; font-weight: 700; }
#ariza-ipucu { font-size: 26px; font-weight: 600; }
#ariza-sayac, #ariza-not { font-size: 22px; }
#ariza-sonuc { font-size: 28px; font-weight: 600; }
#kategori { font-size: 26px; font-weight: 600; padding: 18px 14px; border-radius: 12px; border-width: 2px;
            border-style: solid; background-image: none; box-shadow: none; text-shadow: none; }
textview { font-size: 26px; }
textview text { padding: 8px; }
button { font-size: 30px; font-weight: 600; padding: 12px 28px; border-radius: 12px; background-image: none;
         border-width: 1px; border-style: solid; box-shadow: none; text-shadow: none; }
button:disabled { opacity: 0.45; }
"""


def renkler(palet: dict) -> str:
    """Pencereye özgü renk kuralları (ekran.renk_stili'nin üstüne). Seçili tür ana renkle dolar;
    renk tek başına anlam taşımasın diye seçili düğmenin metnine "✓" de eklenir (pencere yapar)."""
    p = ayar.palet_dogrula(palet) or dict(ayar.VARSAYILAN_PALET)
    return (
        f"#kategori {{ background-color: {p['dugme']}; border-color: {p['dugme_kenar']}; }}\n"
        f"#kategori:checked {{ background-color: {p['ana']}; border-color: {p['vurgu']}; }}\n"
        f"#kategori:checked label {{ color: {p['ana_metin']}; }}\n"
        f"textview, textview text {{ background-color: {p['yuzey']}; color: {p['metin']}; }}\n"
        f"#ariza-cerceve {{ border: 1px solid {p['dugme_kenar']}; border-radius: 8px; }}\n"
        f"#ariza-sayac {{ color: {p['soluk']}; }}\n"
        f"#ariza-not {{ color: {p['bilgi']}; }}\n"
        f"#ariza-sonuc {{ color: {p['metin']}; }}\n"
        "#ariza-sonuc.hata { color: #fca5a5; }\n"
        # Klavyeyle gezinirken odaktaki düğme görünsün.
        f"button:focus {{ outline-color: {p['vurgu']}; outline-style: solid; outline-width: 3px; outline-offset: 2px; }}\n"
    )


def aciklama_kes(metin: str) -> str:
    return str(metin or "")[:ACIKLAMA_EN_UZUN]


def gonder(kategori: str, aciklama: str, zaman_asimi: float = YANIT_SN) -> tuple[bool, str]:
    """Servise arıza iletisini gönderir; (başarılı, ileti). Bağlantı reddi → servis çalışmıyor (K-E7)."""
    try:
        soket = socket.create_connection(("127.0.0.1", ayar.YEREL_PORT), timeout=5)
    except OSError:
        return False, ILETI_SERVIS_YOK
    try:
        with soket:
            soket.settimeout(zaman_asimi)
            for mesaj in (
                {"tur": "merhaba", "arayuz": "komut", "surum": __version__},
                {"tur": "ariza", "kategori": str(kategori), "aciklama": aciklama_kes(aciklama)},
            ):
                soket.sendall((json.dumps(mesaj, ensure_ascii=False) + "\n").encode("utf-8"))
            bitis = time.monotonic() + zaman_asimi
            with soket.makefile("rb") as akis:
                for satir in akis:
                    try:
                        mesaj = json.loads(satir.decode("utf-8"))
                    except ValueError:
                        mesaj = None
                    if isinstance(mesaj, dict) and mesaj.get("tur") == "ariza_sonuc":
                        return bool(mesaj.get("basarili")), str(mesaj.get("mesaj") or "")[:300]
                    if time.monotonic() > bitis:
                        break
    except OSError:
        pass
    return False, ILETI_YANIT_YOK


def calistir() -> int:
    try:
        import gi

        gi.require_version("Gtk", "3.0")
        gi.require_version("Gdk", "3.0")
        from gi.repository import Gdk, GLib, Gtk
    except Exception as hata:  # kitaplık yoksa komut satırına yazılır
        print(f"Arıza penceresi açılamadı (GTK3 yok): {hata}", file=sys.stderr)
        return 2

    from .ekran import renk_stili

    ekran = Gdk.Screen.get_default()
    for metin in (STIL_OLCU, (renk_stili(ayar.VARSAYILAN_PALET) + renkler(ayar.VARSAYILAN_PALET)).encode("ascii")):
        saglayici = Gtk.CssProvider()
        saglayici.load_from_data(metin)
        Gtk.StyleContext.add_provider_for_screen(ekran, saglayici, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    pencere = Gtk.Window(title=BASLIK)
    pencere.set_default_size(1240, 860)
    pencere.set_position(Gtk.WindowPosition.CENTER)
    pencere.connect("destroy", Gtk.main_quit)
    kutu = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    for kenar in ("top", "bottom", "start", "end"):
        getattr(kutu, f"set_margin_{kenar}")(40)
    pencere.add(kutu)

    def etiket(ad: str, metin: str = "", hiza=0.0) -> Gtk.Label:
        e = Gtk.Label(label=metin)
        e.set_name(ad)
        e.set_xalign(hiza)
        e.set_line_wrap(True)
        return e

    kutu.pack_start(etiket("ariza-baslik", BASLIK), False, False, 0)
    kutu.pack_start(etiket("ariza-ipucu", "Arıza türünü seçin:"), False, False, 0)

    izgara = Gtk.Grid(column_spacing=14, row_spacing=14, column_homogeneous=True, row_homogeneous=True)
    kutu.pack_start(izgara, False, False, 0)
    # Gizli "seçilmedi" düğmesi: radyo grubunda başlangıçta hiçbir tür seçili görünmesin.
    hicbiri = Gtk.RadioButton.new_from_widget(None)
    secim = {"kod": ""}
    dugmeler = {}

    def tur_degisti(dugme, kod, ad):
        if dugme.get_active():
            secim["kod"] = kod
        dugme.get_child().set_text(("✓ " if dugme.get_active() else "") + ad)
        gonder_dugmesi.set_sensitive(bool(secim["kod"]) and not durum["gonderiliyor"])

    for sira, (kod, ad) in enumerate(KATEGORILER):
        dugme = Gtk.RadioButton.new_from_widget(hicbiri)
        dugme.set_mode(False)  # radyo işareti yerine iri, dokunmaya uygun düğme
        dugme.set_name("kategori")
        yazi = Gtk.Label(label=ad)
        yazi.set_line_wrap(True)
        yazi.set_justify(Gtk.Justification.CENTER)
        dugme.add(yazi)
        dugme.set_size_request(-1, 104)
        dugme.set_can_focus(True)  # dokunmatiği bozuk tahtada klavyeyle de seçilebilsin
        izgara.attach(dugme, sira % 4, sira // 4, 1, 1)
        dugmeler[kod] = dugme

    kutu.pack_start(etiket("ariza-ipucu", f"Açıklama (isteğe bağlı, en çok {ACIKLAMA_EN_UZUN} karakter)"), False, False, 0)
    cerceve = Gtk.ScrolledWindow()
    cerceve.set_name("ariza-cerceve")
    cerceve.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    cerceve.set_size_request(-1, 150)
    metin_alani = Gtk.TextView()
    metin_alani.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    metin_alani.set_accepts_tab(False)  # Tab odağı düğmelere taşır
    cerceve.add(metin_alani)
    kutu.pack_start(cerceve, True, True, 0)
    sayac = etiket("ariza-sayac", f"0/{ACIKLAMA_EN_UZUN}", 1.0)
    kutu.pack_start(sayac, False, False, 0)
    tampon = metin_alani.get_buffer()

    def metin_degisti(_tampon):
        n = tampon.get_char_count()
        if n > ACIKLAMA_EN_UZUN:  # yapıştırılan uzun metin kesilir
            tampon.set_text(tampon.get_text(tampon.get_start_iter(), tampon.get_end_iter(), False)[:ACIKLAMA_EN_UZUN])
            return
        sayac.set_text(f"{n}/{ACIKLAMA_EN_UZUN}")

    tampon.connect("changed", metin_degisti)
    kutu.pack_start(etiket("ariza-not", NOT_METNI), False, False, 0)
    sonuc = etiket("ariza-sonuc")
    kutu.pack_start(sonuc, False, False, 0)

    satir = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
    satir.set_halign(Gtk.Align.END)
    vazgec = Gtk.Button(label="Vazgeç")
    vazgec.set_can_focus(True)
    vazgec.connect("clicked", lambda *_: pencere.destroy())
    gonder_dugmesi = Gtk.Button(label="Gönder")
    gonder_dugmesi.set_name("ana-dugme")
    gonder_dugmesi.set_can_focus(True)
    gonder_dugmesi.set_sensitive(False)
    satir.pack_start(vazgec, False, False, 0)
    satir.pack_start(gonder_dugmesi, False, False, 0)
    kutu.pack_start(satir, False, False, 0)
    durum = {"gonderiliyor": False}

    for kod, ad in KATEGORILER:
        dugmeler[kod].connect("toggled", tur_degisti, kod, ad)

    def sonuc_goster(basarili: bool, ileti: str):
        durum["gonderiliyor"] = False
        sonuc.set_text(ileti)
        baglam = sonuc.get_style_context()
        (baglam.remove_class if basarili else baglam.add_class)("hata")
        sonuc.set_visible(True)
        if basarili:
            # Kayıt alındı: yeniden gönderilmesin; pencere birkaç saniye sonra kapanır.
            gonder_dugmesi.set_visible(False)
            vazgec.set_label("Kapat")
            vazgec.set_sensitive(True)
            GLib.timeout_add_seconds(KAPANMA_SN, lambda: (pencere.destroy(), False)[1])
        else:
            gonder_dugmesi.set_sensitive(bool(secim["kod"]))
            vazgec.set_sensitive(True)
        return False

    def gonder_tikla(_dugme):
        if not secim["kod"] or durum["gonderiliyor"]:
            return
        durum["gonderiliyor"] = True
        gonder_dugmesi.set_sensitive(False)
        vazgec.set_sensitive(False)
        sonuc.get_style_context().remove_class("hata")
        sonuc.set_text("Gönderiliyor…")
        sonuc.set_visible(True)
        aciklama = tampon.get_text(tampon.get_start_iter(), tampon.get_end_iter(), False)
        kategori = secim["kod"]

        def is_():
            basarili, ileti = gonder(kategori, aciklama)
            GLib.idle_add(sonuc_goster, basarili, ileti)

        threading.Thread(target=is_, daemon=True).start()

    gonder_dugmesi.connect("clicked", gonder_tikla)

    def tus(_pencere, olay):
        # Klavye ve kumanda: Escape kapatır (gönderim sürerken değil), Ctrl+Enter gönderir.
        if olay.keyval == Gdk.KEY_Escape:
            if not durum["gonderiliyor"]:
                pencere.destroy()
            return True
        if olay.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and olay.state & Gdk.ModifierType.CONTROL_MASK:
            if gonder_dugmesi.get_visible() and gonder_dugmesi.get_sensitive():
                gonder_tikla(gonder_dugmesi)
            return True
        return False

    pencere.connect("key-press-event", tus)
    pencere.show_all()
    sonuc.set_visible(False)
    Gtk.main()
    return 0
