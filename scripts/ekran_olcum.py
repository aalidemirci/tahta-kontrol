"""Tahta ekranı ölçüm betiği: her sayfanın ekrana sığıp sığmadığını ölçer (GTK3 + X sunucusu gerekir).

Ekran yardımcısını (tahta_ajan.ekran) servis OLMADAN, aynı süreçte kurar; her senaryo için servisin
göndereceği biçimde UYDURMA bir durum iletisi verir, sayfa çizilince şunları ölçer:

- pencere: pencerenin gerçek boyu (tam ekranda monitöre eşit olmalı),
- gerekli: sayfanın kaydırmasız en küçük eni x boyu (kaydırma alanlarının içeriği dahil;
  ekranın eninde boy, height-for-width ile),
- sonuç: "sığdı" (en ve boy ekrana sığar), "kaydırma" (en sığar, uzun içerik dikey kaydırılır;
  yalnız uzun liste/metin senaryolarında kabul), "TAŞTI" (en sığmaz ya da kısa içerik kaydırılıyor),
  "OYNADI" (kilit ekranındaki gün programında sayfa değişince tuş takımı ya da Önceki/Sonraki
  düğmeleri yer değiştirdi; kilit-program-* senaryoları bütün sayfaları gezerek ölçer).

Kullanım (Docker'da: debian:12 + python3-gi gir1.2-gtk-3.0 xvfb openbox imagemagick):
    Xvfb :9 -screen 0 1366x768x24 & DISPLAY=:9 openbox &
    DISPLAY=:9 python3 scripts/ekran_olcum.py [--cikti DIZIN] [--ariza]
Çıkış kodu: taşan senaryo varsa 1. --cikti verilirse her senaryonun ekran görüntüsü
(<en>x<boy>-<senaryo>.png, ImageMagick `import`) o dizine yazılır. Bütün veriler uydurmadır.
"""

from __future__ import annotations

import argparse
import gc
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from tahta_ajan import __version__, ekran  # noqa: E402

OKUL = "Örnek Mesleki ve Teknik Anadolu Lisesi"
UZUN_METIN = (
    "Değerli öğretmenlerimiz, bugün saat 15:30'da konferans salonunda zümre başkanları toplantısı "
    "yapılacaktır. Toplantıya katılacak öğretmenlerimizin ders programlarını buna göre düzenlemeleri, "
    "gerekli belgeleri yanlarında getirmeleri rica olunur. Toplantı gündemi idare odasındaki panoda "
    "asılıdır; sorularınız için müdür yardımcılarına başvurabilirsiniz. Katılımınız için teşekkür ederiz."
)
ACIL_METIN = (
    "Binada yangın alarmı verilmiştir. Öğretmenler sınıflarını en yakın acil çıkıştan, koşmadan ve "
    "eşyalarını almadan bahçedeki toplanma alanına götürsün. Asansör kullanılmaz. Toplanma alanında "
    "sınıf mevcutları sayılır ve eksik öğrenci nöbetçi müdür yardımcısına bildirilir. "
) * 4
MASKE = ["Ah*** Yı****", "Ay** De***", "Mu****** Em** Ka****", "El** Su Ço****", "Ze**** Ar****"]
ADLAR = ["Mehmet Ali Y. (23)", "Mehmet Ali Y. (57)", "Fatma Nur Ö.", "Muhammed Emin Ç.", "Ayşe Y.",
         "Elif Naz A.", "Ahmet Yasin T.", "Zeynep Su K.", "Can D.", "Defne K."]  # fmt: skip


def taban(**ek) -> dict:
    durum = {
        "tur": "durum", "surum": __version__, "kilitli": False, "kilit_kaynak": None, "kilit_neden": "",
        "kilit_acilis": "", "duyuru": None, "kapatma": None, "acil": None, "sinav": None, "yoklama": None,
        "yoklama_etkin": True, "okul_adi": OKUL, "kod_var": True, "cevrimdisi": False, "kayitli": True,
        "bekleme": 0, "tema": None, "logo_sha256": None, "tahta_adi": "Tahta 12-C Fen Bilimleri",
        "derslik": "12/C Dersliği (2. kat, B blok)",
    }  # fmt: skip
    durum.update(ek)
    return durum


def sinav(evre="suruyor", gozetmen=None, liste=0) -> dict:
    return {
        "kimlik": "sinav-1-salon-1", "evre": evre, "sinav_adi": "1. Dönem 1. Ortak Sınav · Coğrafya",
        "salon_adi": "12/C Dersliği", "baslangic_saat": "10:00", "bitis_saat": "10:40",
        "dersler": [{"ad": "Coğrafya — 12. Sınıf", "bitis_saat": "10:40"}, {"ad": "Tarih — 11. Sınıf", "bitis_saat": "10:50"},
                    {"ad": "Felsefe — 10. Sınıf", "bitis_saat": "11:00"}],
        "kurallar": "\n".join(f"{i}. Sınav süresince cep telefonu ve akıllı saat kapalı tutulur, sıraya konmaz." for i in range(1, 9)),
        "kalan_baslama": 300 if evre == "giris" else 0, "kalan_bitis": 2400,
        "liste": [{"k": i, "a": MASKE[i % 5], "n": f"{i:02d}", "s": "12/C"} for i in range(1, liste + 1)],
        "liste_fazla": 0, "yoklama_alindi": False, "bildirim": "",
        "gozetmen": gozetmen or {"durum": None, "hata": "", "oturum": 0, "basladi": False, "tahtadan_yoklama": False,
                                 "liste": [], "gelmeyen": [], "bekleme": 0},
    }  # fmt: skip


def yoklama(asama, **ek) -> dict:
    y = {
        "asama": asama, "oturum": 1, "tarih_yazi": "16.11.2026 Pazartesi", "ogretmen": {"kod": "101", "etiket": "A. Örnek"},
        "sube": "10/A", "ders_no": 3, "ders_adi": "Coğrafya", "ders_metni": "3. ders (09:50–10:30)",
        "ders_saatleri": [{"ders_no": i, "metin": f"{i}. ders ({8 + i}:10–{8 + i}:50)", "secilebilir": True} for i in range(1, 11)],
        "subeler": [f"{s}/{h}" for s in (9, 10, 11, 12) for h in "ABC"], "liste_yuklu": False, "ogrenciler": [], "yok": [],
        "mevcut": 0, "baska_yoklama": False, "liste_ileti": "", "kalan": 300, "uyari": False, "ileti": "", "hata": "",
        "bekleme": 0, "istek": False,
    }  # fmt: skip
    y.update(ek)
    return y


def gun_programi(ders_sayisi=10, ileti="") -> dict:
    """Kilit ekranındaki gün programı (0.13.0): yalnız şube/ders/saat; tarih bugündür ("Bugünün ..." başlığı)."""
    adlar = ["Türk Dili ve Edebiyatı", "Seçmeli Peygamberimizin Hayatı / Seçmeli Temel Dini Bilgiler", "Coğrafya",
             "Beden Eğitimi ve Spor", "Matematik"]  # fmt: skip
    dersler = [{"ders_no": i + 1, "baslangic": f"{8 + (i * 50) // 60:02d}:{(i * 50) % 60:02d}",
                "bitis": f"{8 + (i * 50 + 40) // 60:02d}:{(i * 50 + 40) % 60:02d}",
                "sube": f"{9 + i % 4}/{'ABC'[i % 3]}", "ders_adi": adlar[i % len(adlar)]} for i in range(ders_sayisi)]  # fmt: skip
    return {"tarih": time.strftime("%Y-%m-%d"), "dersler": dersler, "ileti": ileti}


OGRENCILER = [{"id": i + 1, "etiket": ADLAR[i % len(ADLAR)]} for i in range(40)]
GOZETMEN_LISTE = [{"k": i, "a": MASKE[i % 5], "n": f"{i:02d}", "s": "12/C"} for i in range(1, 36)]
OTURMA = "Sınav oturma listesi · 9/A\n\n" + "\n".join(f"Ab*** Cd**** …{i:02d}  →  10/B Dersliği, koltuk {i}" for i in range(60))

# (ad, durum, beklenen sayfa, uzun içerik mi (dikey kaydırma kabul), ekranda yapılacak yerel iş)
SENARYOLAR = [
    ("kilit", taban(kilitli=True, kilit_kaynak="program", kilit_neden="Bu saatte bu derslikte ders yok",
                    kilit_acilis="10:40"), "kilit", False, None),  # fmt: skip
    ("kilit-cevrimdisi", taban(kilitli=True, cevrimdisi=True), "kilit", False, None),
    ("kilit-program", taban(kilitli=True, gun_programi=gun_programi()), "kilit", False, "program_sayfalari"),
    ("kilit-program-tam", taban(kilitli=True, kilit_kaynak="program", kilit_neden="Bu saatte bu derslikte ders yok",
                                kilit_acilis="10:40", usb={"metin": "USB anahtar tanındı · A. Örnek (kod 112)",
                                                           "kilit_ac": True},
                                gun_programi=gun_programi(10, "Bugün 5. ve 6. derslerde ortak sınav vardır; sınav salonları "
                                                              "ve oturma düzeni için koridordaki listeye bakınız.")),
     "kilit", False, "program_sayfalari"),  # fmt: skip
    ("kilit-program-kodsuz", taban(kilitli=True, kod_var=False, gun_programi=gun_programi(3)), "kilit", False,
     "program_sayfalari"),
    ("duyuru", taban(duyuru={"baslik": "Zümre toplantısı", "metin": UZUN_METIN, "kalan": 600, "kapatilabilir": True}),
     "duyuru", False, None),
    ("duyuru-liste", taban(duyuru={"baslik": "Oturma listesi", "metin": OTURMA, "kalan": 600, "kapatilabilir": True}),
     "duyuru", True, None),
    ("kapatma", taban(kapatma={"kalan": 120, "neden": "Otomatik kapatma (17:30)"}), "kapatma", False, None),
    ("acil", taban(kilitli=True, acil={"id": 1, "tur": "acil", "baslik": "Yangın — binayı boşaltın", "metin": ACIL_METIN,
                                       "kalan": 600, "kapatilabilir": True}), "acil", True, None),  # fmt: skip
    ("tatbikat", taban(acil={"id": 2, "tur": "tatbikat", "baslik": "Deprem tatbikatı",
                             "metin": "Çök, kapan, tutun. Sarsıntı bitince sınıfça bahçeye çıkın.", "kalan": 600,
                             "kapatilabilir": False}), "acil", False, None),  # fmt: skip
    ("sinav-giris", taban(sinav=sinav("giris", liste=40)), "sinav-giris", True, None),
    ("sinav", taban(sinav=sinav("suruyor"), cevrimdisi=True), "sinav", False, None),
    ("gozetmen-kod", taban(sinav=sinav("suruyor", gozetmen={"durum": None, "hata": "", "oturum": 0, "basladi": True,
                                                         "tahtadan_yoklama": True, "liste": [], "gelmeyen": [],
                                                         "bekleme": 130})),
     "gozetmen-kod", False, "gozetmen_ac"),  # fmt: skip
    ("gozetmen-menu", taban(sinav=sinav("suruyor", gozetmen={"durum": "menu", "hata": "Sunucuya ulaşılamadı; yeniden deneyin.",
                                                          "oturum": 1, "basladi": True, "tahtadan_yoklama": False,
                                                          "liste": [], "gelmeyen": [], "bekleme": 0})),
     "gozetmen-menu", False, None),  # fmt: skip
    ("gozetmen-yoklama", taban(sinav=sinav("suruyor", gozetmen={"durum": "yoklama", "hata": "", "oturum": 2, "basladi": True,
                                                             "tahtadan_yoklama": True, "liste": GOZETMEN_LISTE,
                                                             "gelmeyen": [3, 7], "bekleme": 0})),
     "gozetmen-yoklama", False, None),  # fmt: skip
    ("yoklama-pin", taban(kilitli=True, yoklama=yoklama("pin", hata="PIN hatalı. Kalan deneme: 2")), "yoklama-pin", False, None),
    ("yoklama-secim", taban(yoklama=yoklama("liste", sube="", ders_no=None)), "yoklama-liste", False, None),
    ("yoklama-liste", taban(yoklama=yoklama("liste", liste_yuklu=True, ogrenciler=OGRENCILER, yok=[1, 2, 5], mevcut=40,
                                            baska_yoklama=True)), "yoklama-liste", True, None),  # fmt: skip
    ("yoklama-onay", taban(yoklama=yoklama("onay", liste_yuklu=True, ogrenciler=OGRENCILER, yok=list(range(1, 16)),
                                           mevcut=40)), "yoklama-onay", False, None),  # fmt: skip
    ("yoklama-ileti", taban(yoklama=yoklama("ileti", ileti="Yoklama kaydedildi. 3 öğrenci yok yazıldı; e-Okul'a idare işler.")),
     "yoklama-ileti", False, None),  # fmt: skip
]


def pompala(saniye: float):
    bitis = time.monotonic() + saniye
    while time.monotonic() < bitis:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        time.sleep(0.02)


def kaydirmalar(oge) -> list:
    bulunan = []
    if isinstance(oge, Gtk.ScrolledWindow):
        bulunan.append(oge)
    if isinstance(oge, Gtk.Container):
        for cocuk in oge.get_children():
            bulunan.extend(kaydirmalar(cocuk))
    return bulunan


def olc_sayfa(sayfa) -> tuple[int, int, bool]:
    """(gerekli en, gerekli boy, kaydırma alanı içeriği en olarak taştı mı)."""
    sayfa_en, sayfa_boy = sayfa.get_allocated_width(), sayfa.get_allocated_height()
    gerekli_en = sayfa.get_preferred_width()[0]
    gerekli_boy = sayfa.get_preferred_height_for_width(sayfa_en)[0]
    yatay_tasti = False
    for kaydirma in kaydirmalar(sayfa):
        if not kaydirma.get_mapped():
            continue
        icerik = kaydirma.get_child()
        if isinstance(icerik, Gtk.Viewport):
            icerik = icerik.get_child()
        if icerik is None:
            continue
        k_en, k_boy = kaydirma.get_allocated_width(), kaydirma.get_allocated_height()
        icerik_en = icerik.get_preferred_width()[0]
        icerik_boy = icerik.get_preferred_height_for_width(max(k_en, icerik_en))[0]
        yatay_tasti |= icerik_en > k_en
        gerekli_en = max(gerekli_en, sayfa_en - k_en + icerik_en)
        gerekli_boy = max(gerekli_boy, sayfa_boy - k_boy + icerik_boy)
    return gerekli_en, gerekli_boy, yatay_tasti


def program_sayfalari_oynadi_mi(nesne) -> bool:
    """Gün programının bütün sayfalarını gezer; tuş takımı, program kutusu ya da gezgin yer değiştirdiyse True."""

    def yerler():
        return [(p.get_allocation().x, p.get_allocation().y, p.get_allocation().width, p.get_allocation().height)
                for p in (nesne.kod_kutusu, nesne.kilit_program_kutu, nesne.kilit_program_gezgin,
                          nesne.kilit_program_onceki, nesne.kilit_program_sonraki) if p.get_mapped()]  # fmt: skip

    nesne.kilit_program_sayfa = 0
    nesne._kilit_program_gec(0)  # elle seçim: ölçüm sırasında otomatik sayfaya dönmesin
    pompala(0.4)
    ilk, gezilen = yerler(), 0
    while nesne.kilit_program_sonraki.get_mapped() and nesne.kilit_program_sonraki.get_sensitive() and gezilen < 12:
        nesne._kilit_program_gec(1)
        gezilen += 1
        pompala(0.4)
        if yerler() != ilk:
            return True
    nesne.kilit_program_elle_bitis = 0.0
    return False


def ekran_goruntusu(dizin, en, boy, ad):
    if dizin:
        subprocess.run(["import", "-window", "root", os.path.join(dizin, f"{en}x{boy}-{ad}.png")], check=False)


def ekran_olc(arg) -> int:
    sonuclar = []

    def calis():
        nesne = next(o for o in gc.get_objects() if type(o).__name__ == "Ekran" and hasattr(o, "yigin"))
        for ad, durum, beklenen, uzun, is_ in SENARYOLAR:
            nesne.gozetmen_kod_acik = False
            nesne._mesaj(taban())  # önce gizle: senaryolar birbirini etkilemesin
            pompala(0.3)
            nesne._mesaj(durum)
            if is_ == "gozetmen_ac":
                nesne._gozetmen_ac()
            pompala(1.2)
            en, boy = nesne.ekran_en, nesne.ekran_boy
            pencere = nesne.pencere.get_window()
            p_en, p_boy = (pencere.get_width(), pencere.get_height()) if pencere else (0, 0)
            sayfa_adi = nesne.yigin.get_visible_child_name()
            gerekli_en, gerekli_boy, yatay_tasti = olc_sayfa(nesne.yigin.get_visible_child())
            if sayfa_adi != beklenen or (p_en, p_boy) != (en, boy) or gerekli_en > en or yatay_tasti:
                sonuc = "TAŞTI"
            elif gerekli_boy > boy:
                sonuc = "kaydırma" if uzun else "TAŞTI"
            else:
                sonuc = "sığdı"
            ekran_goruntusu(arg.cikti, en, boy, ad)
            if is_ == "program_sayfalari":
                if not nesne.kilit_program_kutu.get_mapped():
                    sonuc = "TAŞTI"  # program kutusu görünmeliydi
                elif program_sayfalari_oynadi_mi(nesne) and sonuc == "sığdı":
                    sonuc = "OYNADI"
                ad_son = ad + "-son"
                ekran_goruntusu(arg.cikti, en, boy, ad_son)
            sonuclar.append((ad, sayfa_adi, en, boy, nesne.olcek, p_en, p_boy, gerekli_en, gerekli_boy, sonuc))
        Gtk.main_quit()

    ekran.Baglanti.calis = lambda self: None  # servis yok: ileti gönderilmez, kopma bildirilmez
    asil_main = Gtk.main

    def main():
        from gi.repository import GLib

        GLib.idle_add(lambda: (calis(), False)[1])
        asil_main()

    Gtk.main = main
    ekran.calistir()
    print(f"{'senaryo':<21} {'sayfa':<17} {'ekran':>10} {'ölçek':>6} {'pencere':>10} {'gerekli':>10}  sonuç")
    for ad, sayfa_adi, en, boy, olcek, p_en, p_boy, g_en, g_boy, sonuc in sonuclar:
        print(f"{ad:<21} {sayfa_adi:<17} {en:>4}x{boy:<5} {olcek:>6.3f} {p_en:>4}x{p_boy:<5} {g_en:>4}x{g_boy:<5}  {sonuc}")
    return 1 if any(s[-1] in ("TAŞTI", "OYNADI") for s in sonuclar) else 0


def ariza_olc(arg) -> int:
    """Arıza penceresi: pencere monitörden büyük olmamalı, içerik eni sığmalı."""
    from tahta_ajan import ariza_penceresi

    sonuc = {}

    def calis():
        pencere = next(p for p in Gtk.Window.list_toplevels() if p.get_title() == ariza_penceresi.BASLIK)
        pompala(1.0)
        alan = Gdk.Display.get_default().get_monitor_at_window(pencere.get_window()).get_geometry()
        gdk = pencere.get_window()
        x, y = gdk.get_root_origin()
        gerekli_en, gerekli_boy, yatay_tasti = olc_sayfa(pencere.get_child())
        sonuc.update(ekran=(alan.width, alan.height), pencere=(gdk.get_width(), gdk.get_height()), konum=(x, y),
                     gerekli=(gerekli_en, gerekli_boy), yatay_tasti=yatay_tasti)  # fmt: skip
        ekran_goruntusu(arg.cikti, alan.width, alan.height, "ariza")
        pencere.destroy()

    asil_main = Gtk.main

    def main():
        from gi.repository import GLib

        GLib.timeout_add(300, lambda: (calis(), False)[1])
        asil_main()

    Gtk.main = main
    ariza_penceresi.calistir()
    (en, boy), (p_en, p_boy), (x, _) = sonuc["ekran"], sonuc["pencere"], sonuc["konum"]
    g_en, g_boy = sonuc["gerekli"]
    sigdi = p_en <= en and p_boy <= boy and 0 <= x and x + p_en <= en + 2 and g_en <= p_en and not sonuc["yatay_tasti"]
    durum = "sığdı" if sigdi and g_boy <= p_boy else "kaydırma" if sigdi else "TAŞTI"
    print(f"{'ariza':<18} {'(pencere)':<17} {en:>4}x{boy:<5} {'':>6} {p_en:>4}x{p_boy:<5} {g_en:>4}x{g_boy:<5}  {durum}")
    return 0 if sigdi else 1


def main() -> int:
    arg = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    arg.add_argument("--cikti", default="", help="ekran görüntülerinin yazılacağı dizin")
    arg.add_argument("--ariza", action="store_true", help="tahta ekranı yerine arıza penceresini ölç")
    a = arg.parse_args()
    if a.cikti:
        os.makedirs(a.cikti, exist_ok=True)
    return ariza_olc(a) if a.ariza else ekran_olc(a)


if __name__ == "__main__":
    sys.exit(main())
