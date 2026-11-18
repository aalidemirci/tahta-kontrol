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
- ders yoklaması (0.14.0; "ky" işaretli senaryolar): seçim ve liste görünümü KAYDIRMASIZDIR. Sayfada
  görünen kaydırma alanı olmamalı; her düğmenin yerleşimi sayfanın içinde ve alt çubuğun üstünde kalmalı,
  düğme boyu en küçük dokunma ölçüsünün altına inmemeli, hiçbir etiket "…" ile kesilmemeli. Aksi "TAŞTI"dır
  ve neden satırın sonuna yazılır; en küçük düğmenin eni x boyu (px) da yazılır. Liste senaryolarında bir
  düğmeye gerçekten dokunulur: var → YOK → (ilk derste) GEÇ → var döngüsü yazı ve renkle birlikte denetlenir.

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


def ders_saatleri(n=10, ilk=8 * 60 + 30, baslamamis=0, saatsiz=False) -> list:
    """Servisin görünümündeki ders saatleri (40 dk ders, 10 dk teneffüs); son `baslamamis` ders seçilemez."""
    dersler = []
    for i in range(n):
        bas, bit = ilk + i * 50, ilk + i * 50 + 40
        b, t = ("", "") if saatsiz else (f"{bas // 60:02d}:{bas % 60:02d}", f"{bit // 60:02d}:{bit % 60:02d}")
        dersler.append({"ders_no": i + 1, "baslangic": b, "bitis": t, "secilebilir": i < n - baslamamis,
                        "metin": f"{i + 1}. ders" + (f" ({b}–{t})" if b else "")})  # fmt: skip
    return dersler


def subeler(duzeyler=(9, 10, 11, 12), harfler="ABC") -> list:
    return [f"{d}/{h}" for d in duzeyler for h in harfler]


def yoklama(asama, **ek) -> dict:
    """Servisin `_yoklama_gorunumu` çıktısı biçiminde uydurma görünüm (0.14.0 alanlarıyla)."""
    y = {
        "asama": asama, "oturum": 1, "tarih_yazi": "16.11.2026 Pazartesi", "ogretmen": {"kod": "101", "etiket": "A. Örnek"},
        "sube": "10/A", "ders_no": 3, "ders_adi": "", "ders_metni": "3. ders (10:10–10:50)",
        "ders_saatleri": ders_saatleri(10, baslamamis=6), "subeler": subeler(), "liste_yuklu": False, "ogrenciler": [],
        "yok": [], "gec": [], "gec_secilebilir": False, "subeler_once": [], "ders_adaylari": [], "devre_adi": "",
        "simdiki_ders_no": 3, "sayfa": 0, "sayfa_sayisi": 1, "tum_sayfalar_goruldu": True,
        "mevcut": 0, "baska_yoklama": False, "liste_ileti": "", "kalan": 300, "uyari": False, "ileti": "", "hata": "",
        "bekleme": 0, "istek": False,
    }  # fmt: skip
    y.update(ek)
    return y


# Uydurma öğrenci adları. Etiketi SUNUCU üretir (maske.sinif_etiketi: numara + ad + soyadın baş harfi, ad sütun
# sayısına göre kısaltılır); betik aynı işlevi kullanır ki ölçülen etiketler tahtaya gidecek olanlarla aynı olsun.
KISA_ADLAR = [("Ayşe", "YILMAZ"), ("Can", "DEMİR"), ("Elif Naz", "AKSOY"), ("Mehmet Ali", "YILDIRIM"), ("Zeynep Su", "KAYA"),
              ("Ahmet Yasin", "TOPRAK"), ("Fatma Nur", "ÖZTÜRK"), ("Defne", "KURT"), ("Burak", "ÇELİK"), ("İpek", "IŞIK")]  # fmt: skip
UZUN_ADLAR = [("Muhammed Emin", "YILDIRIM"), ("Abdurrahman Muhammed Emin", "KAYA"), ("Abdülkadir Selahattin", "ÖZDEMİR"),
              ("Zeynep Gülsüm Nur", "KARA ÖZ"), ("Muhammed Mustafa", "ÇALIŞKAN"), ("Hatice Kübra", "ŞAHİNOĞLU")]  # fmt: skip


def ogrenci_listesi(n, adlar=None, ilk_no=101) -> list:
    """n kişilik liste, okul no sırasıyla; etiket sunucunun işleviyle (yoksa aynı biçimde elle)."""
    adlar = adlar or KISA_ADLAR
    try:
        from tahta_sunucu import maske

        esik = maske.ad_esigi(maske.yoklama_yerlesim(n)[0])

        def etiket(ad, soyad, no):
            return maske.sinif_etiketi(ad, soyad, no, "no_ad_soyadbas", esik)
    except Exception:  # sunucu paketi yoksa (yalnız ajan kopyalanmışsa) aynı biçim elle

        def etiket(ad, soyad, no):
            return f"{no} {ad} {soyad[0]}."[:40]

    return [{"id": i + 1, "etiket": etiket(*adlar[i % len(adlar)], str(ilk_no + i * 3))} for i in range(n)]


def liste(n, sayfa=0, goruldu=True, adlar=None, ilk_no=101, **ek) -> dict:
    """Liste görünümü: n öğrenci; yok/geç işaretleri verilmezse birkaç uydurma işaret."""
    ek.setdefault("yok", [2, 5] if n >= 5 else [])
    return yoklama("liste", liste_yuklu=True, ogrenciler=ogrenci_listesi(n, adlar, ilk_no), mevcut=n, sayfa=sayfa,
                   sayfa_sayisi=max(1, -(-n // 56)), tum_sayfalar_goruldu=goruldu, **ek)  # fmt: skip


def gun_programi(ders_sayisi=10, ileti="") -> dict:
    """Kilit ekranındaki gün programı (0.13.0): yalnız şube/ders/saat; tarih bugündür ("Bugünün ..." başlığı)."""
    adlar = ["Türk Dili ve Edebiyatı", "Seçmeli Peygamberimizin Hayatı / Seçmeli Temel Dini Bilgiler", "Coğrafya",
             "Beden Eğitimi ve Spor", "Matematik"]  # fmt: skip
    dersler = [{"ders_no": i + 1, "baslangic": f"{8 + (i * 50) // 60:02d}:{(i * 50) % 60:02d}",
                "bitis": f"{8 + (i * 50 + 40) // 60:02d}:{(i * 50 + 40) % 60:02d}",
                "sube": f"{9 + i % 4}/{'ABC'[i % 3]}", "ders_adi": adlar[i % len(adlar)]} for i in range(ders_sayisi)]  # fmt: skip
    return {"tarih": time.strftime("%Y-%m-%d"), "dersler": dersler, "ileti": ileti}


ESKI_BICIM = [{"id": i + 1, "etiket": ADLAR[i % len(ADLAR)]} for i in range(40)]  # "ad + soyad baş harfi" (çakışma ekli)
# Çok şubeli okul: 5 düzey x 12. Hazırlık sınıfı sunucunun kanonik adıyla ("Hazırlık/G"; metin.sube_duzelt):
# "Hz/C" gibi kısa uydurma ad, üst satırdaki ★ düğmelerinin kesilmesini gizliyordu.
SUBE_60 = subeler(("Hazırlık", 9, 10, 11, 12), "ABCDEFGHIJKL")
SUBE_40 = subeler((9, 10, 11, 12), "ABCDEFGHIJ")
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
    # ---- ders yoklaması 0.14.0: "ky" = kaydırmasız görünüm denetimi (bkz. yoklama_denetle) ----
    # Seçim: az şubeli okul (düzey sütunu yok), şube seçili değil, şimdiki ders ön seçili.
    ("yk-secim-az", taban(yoklama=yoklama("liste", sube=None, ders_no=3)), "yoklama-liste", False, "ky"),
    # Kabul ölçütü 1: 40 şube + 12 ders saati; tahtanın şubesi ve öğretmenin şubeleri öne alınmış, öneri düğmesi.
    ("yk-secim-40", taban(yoklama=yoklama("liste", subeler=SUBE_40, ders_saatleri=ders_saatleri(12, baslamamis=8),
                                          simdiki_ders_no=4, ders_no=4, subeler_once=["10/A", "11/C", "9/B"])),
     "yoklama-liste", False, "ky"),  # fmt: skip
    # Çok şubeli okul: 60 şube (5 düzey x 12), 6 öne alınan şube, uzun gün (12 ders).
    ("yk-secim-60", taban(yoklama=yoklama("liste", subeler=SUBE_60, sube="11/G", ders_saatleri=ders_saatleri(12, baslamamis=3),
                                          simdiki_ders_no=9, ders_no=9,
                                          subeler_once=["11/G", "12/A", "9/B", "10/K", "Hazırlık/C", "12/L"])),
     "yoklama-liste", False, "ky"),  # fmt: skip
    # Hazırlık şubesi seçili + 6 öne alınan (ikisi Hazırlık): öneri düğmesi ve ★ düğmeleri kesilmemeli, ayırt edilmeli.
    ("yk-secim-hazirlik", taban(yoklama=yoklama("liste", subeler=SUBE_60, sube="Hazırlık/G",
                                                ders_saatleri=ders_saatleri(12, baslamamis=3), simdiki_ders_no=9, ders_no=9,
                                                subeler_once=["Hazırlık/G", "Hazırlık/C", "12/A", "9/B", "10/K", "12/L"])),
     "yoklama-liste", False, "ky"),  # fmt: skip
    # Az önce biten ders ön seçili: "şimdi" değil "bitti" yazar.
    ("yk-secim-bitti", taban(yoklama=yoklama("liste", subeler=SUBE_40, ders_saatleri=ders_saatleri(12, baslamamis=7),
                                             simdiki_ders_no=5, simdiki_bitti=True, ders_no=5, subeler_once=["10/A"])),
     "yoklama-liste", False, "ky"),  # fmt: skip
    # Teneffüs: biten / başlayacak iki aday vurgulu, liste açılmadı.
    ("yk-secim-teneffus", taban(yoklama=yoklama("liste", subeler=SUBE_40, ders_no=None, simdiki_ders_no=None,
                                                ders_adaylari=[2, 3], subeler_once=["10/A"])),
     "yoklama-liste", False, "ky"),  # fmt: skip
    # İkili eğitim, devir saati: şubesiz açılış, ders saatleri bilinmiyor ("Önce şubeyi seçin").
    ("yk-secim-ikili-bos", taban(yoklama=yoklama("liste", subeler=SUBE_40, sube=None, ders_no=None, simdiki_ders_no=None,
                                                 ders_saatleri=ders_saatleri(12, saatsiz=True))),
     "yoklama-liste", False, "ky"),  # fmt: skip
    # İkili eğitim: öğle şubesi seçildi; devre adı başlıkta, öğlenin dersleri (hepsi başlamamış: soluk).
    ("yk-secim-ikili-ogle", taban(yoklama=yoklama("liste", subeler=SUBE_40, sube="11/C", ders_no=None, simdiki_ders_no=None,
                                                  devre_adi="Öğle", ders_saatleri=ders_saatleri(7, ilk=13 * 60 + 30, baslamamis=7),
                                                  hata="Bu ders saati henüz başlamadı.")),
     "yoklama-liste", False, "ky"),  # fmt: skip
    # Devresi bulunamayan şube: saatsiz 1–12.
    ("yk-secim-saatsiz", taban(yoklama=yoklama("liste", ders_no=None, simdiki_ders_no=None,
                                               ders_saatleri=ders_saatleri(12, saatsiz=True))),
     "yoklama-liste", False, "ky"),  # fmt: skip
    # Liste: 30 / 42 (6x7), 48 (6x8), 56 (7x8), 70 (iki sayfa).
    ("yk-liste-30", taban(yoklama=liste(30)), "yoklama-liste", False, "ky"),
    ("yk-liste-42", taban(yoklama=liste(42, baska_yoklama=True)), "yoklama-liste", False, "ky"),
    ("yk-liste-48", taban(yoklama=liste(48)), "yoklama-liste", False, "ky"),
    ("yk-liste-56", taban(yoklama=liste(56)), "yoklama-liste", False, "ky"),
    # 4 haneli okul no + iki/üç adlı 56 öğrenci (sunucu adı 7 sütuna göre kısaltır).
    ("yk-liste-56-uzun", taban(yoklama=liste(56, adlar=UZUN_ADLAR, ilk_no=1003, yok=[1, 9, 30], uyari=True)),
     "yoklama-liste", False, "ky"),  # fmt: skip
    ("yk-liste-48-uzun", taban(yoklama=liste(48, adlar=UZUN_ADLAR, ilk_no=1003)), "yoklama-liste", False, "ky"),
    # Devrenin ilk dersi: geç seçilebilir; yok ve geç işaretli öğrenciler.
    ("yk-liste-gec", taban(yoklama=liste(34, sube="9/B", ders_no=1, gec_secilebilir=True, yok=[2, 5, 20], gec=[3, 8, 14, 33],
                                         simdiki_ders_no=1, ders_metni="1. ders (08:30–09:10)")),
     "yoklama-liste", False, "ky"),  # fmt: skip
    ("yk-liste-70-s1", taban(yoklama=liste(70, sayfa=0, goruldu=False)), "yoklama-liste", False, "ky"),
    ("yk-liste-70-s2", taban(yoklama=liste(70, sayfa=1, goruldu=True, yok=[2, 5, 60])), "yoklama-liste", False, "ky"),
    # Eski sunucu / eski biçim ("ad + soyad baş harfi", çakışma ekli): ek numara satırında görünür.
    ("yk-liste-eski", taban(yoklama=yoklama("liste", liste_yuklu=True, ogrenciler=ESKI_BICIM, yok=[1, 2, 5], mevcut=40)),
     "yoklama-liste", False, "ky"),  # fmt: skip
    ("yoklama-onay", taban(yoklama=dict(liste(40, gec_secilebilir=True, yok=list(range(1, 9)), gec=[20, 21, 22]), asama="onay")),
     "yoklama-onay", False, None),  # fmt: skip
    ("yoklama-onay-70", taban(yoklama=dict(liste(70, yok=list(range(1, 19))), asama="onay")), "yoklama-onay", True, None),
    ("yoklama-ileti", taban(yoklama=yoklama("ileti", ileti="Kaydedildi: 3 yok, 2 geç.")), "yoklama-ileti", False, None),
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


def torunlar(oge) -> list:
    bulunan = [oge]
    if isinstance(oge, Gtk.Container):
        for cocuk in oge.get_children():
            bulunan.extend(torunlar(cocuk))
    return bulunan


def yoklama_denetle(nesne, sayfa) -> tuple[list[str], tuple[int, int]]:
    """Ders yoklaması görünümü kaydırmasız mı? (sorunlar, en küçük düğmenin eni x boyu).

    - sayfada görünen ScrolledWindow yok;
    - ızgaralardaki her düğme sayfanın içinde, alt çubuğun (Vazgeç/KAYDET satırı) üstünde;
    - düğme boyu en küçük dokunma ölçüsünden (ölçekli) küçük değil;
    - gövdede (okul bandı dışında) hiçbir etiket "…" ile kesilmemiş (numara, ad, şube, ders saati, sayılar, üst satır).
    """
    sorunlar = []
    if any(k.get_mapped() for k in kaydirmalar(sayfa)):
        sorunlar.append("kaydırma alanı var")
    sayfa_en, sayfa_boy = sayfa.get_allocated_width(), sayfa.get_allocated_height()
    alt = nesne.yl_alt
    alt_ust = alt.translate_coordinates(sayfa, 0, 0)[1]
    en_az = ekran.olcekle(ekran.YOKLAMA_DOKUNMA_EN_AZ, nesne.olcek)
    en_kucuk, disarida, kisa, kesik = None, 0, 0, 0
    for kap in (nesne.yl_izgara, nesne.yl_once, nesne.yl_duzeyler, nesne.yl_subeler, nesne.yl_dersler):  # yl_once: öneri + ★
        for oge in torunlar(kap):
            if not isinstance(oge, Gtk.Button) or not oge.get_mapped():
                continue
            x, y = oge.translate_coordinates(sayfa, 0, 0)
            en, boy = oge.get_allocated_width(), oge.get_allocated_height()
            if en_kucuk is None or (boy, en) < (en_kucuk[1], en_kucuk[0]):
                en_kucuk = (en, boy)
            disarida += x < 0 or y < 0 or x + en > sayfa_en or y + boy > alt_ust
            kisa += boy < en_az
    for oge in torunlar(alt.get_parent()):
        if isinstance(oge, Gtk.Label) and oge.get_mapped() and oge.get_text() and oge.get_layout().is_ellipsized():
            kesik += 1
    if alt_ust + alt.get_allocated_height() > sayfa_boy:
        sorunlar.append("alt çubuk sayfanın dışında")
    for sayi, ad in ((disarida, "düğme alanın dışında"), (kisa, f"düğme {en_az} px'ten kısa"), (kesik, "etiket kesik")):
        if sayi:
            sorunlar.append(f"{sayi} {ad}")
    return sorunlar, en_kucuk or (0, 0)


def dokunus_denetle(nesne) -> list[str]:
    """Liste görünümünde gerçek düğmeye dokunur (clicked): yazı ve renk sınıfı servis beklenmeden değişmeli,
    servise her dokunuşta `yoklama_isaret` gitmeli. Geç seçilebiliyorsa var → YOK → GEÇ → var, değilse var ↔ YOK."""
    yoklama = nesne.durum.get("yoklama") or {}
    isaretli = set(yoklama.get("yok") or []) | set(yoklama.get("gec") or [])
    kimlik = next((k for k in nesne.yk_dugmeler if k not in isaretli), None)
    if kimlik is None:
        return ["dokunulacak düğme yok"]
    kayit, giden = nesne.yk_dugmeler[kimlik], []
    asil, nesne.baglanti.gonder = nesne.baglanti.gonder, giden.append
    beklenen = ["YOK", "GEÇ", ""] if yoklama.get("gec_secilebilir") else ["YOK", "", "YOK", ""]
    gorulen = []
    try:
        for _ in beklenen:
            kayit["dugme"].clicked()
            pompala(0.1)
            sinif = [c for c in ("yok", "gec") if kayit["dugme"].get_style_context().has_class(c)]
            gorulen.append((kayit["durum"].get_text(), sinif))
    finally:
        nesne.baglanti.gonder = asil
    sorunlar = []
    if [g[0] for g in gorulen] != beklenen:
        sorunlar.append(f"dokunuş döngüsü {[g[0] for g in gorulen]}")
    if [g[1] for g in gorulen] != [[{"YOK": "yok", "GEÇ": "gec"}[b]] if b else [] for b in beklenen]:
        sorunlar.append("renk sınıfı yazıyla uyuşmuyor")
    if giden != [{"tur": "yoklama_isaret", "id": kimlik}] * len(beklenen):
        sorunlar.append("servise giden ileti yanlış")
    return sorunlar


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
            if arg.yalniz and arg.yalniz not in ad:
                continue
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
            ek = ""
            if is_ == "ky":
                sorunlar, (d_en, d_boy) = yoklama_denetle(nesne, nesne.yigin.get_visible_child())
                if nesne.yk_dugmeler:
                    sorunlar += dokunus_denetle(nesne)
                ek = f"  en küçük düğme {d_en}x{d_boy}" + ("  [" + "; ".join(sorunlar) + "]" if sorunlar else "")
                if sorunlar or sonuc != "sığdı":
                    sonuc = "TAŞTI"
            ekran_goruntusu(arg.cikti, en, boy, ad)
            if is_ == "program_sayfalari":
                if not nesne.kilit_program_kutu.get_mapped():
                    sonuc = "TAŞTI"  # program kutusu görünmeliydi
                elif program_sayfalari_oynadi_mi(nesne) and sonuc == "sığdı":
                    sonuc = "OYNADI"
                ad_son = ad + "-son"
                ekran_goruntusu(arg.cikti, en, boy, ad_son)
            sonuclar.append((ad, sayfa_adi, en, boy, nesne.olcek, p_en, p_boy, gerekli_en, gerekli_boy, sonuc, ek))
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
    for ad, sayfa_adi, en, boy, olcek, p_en, p_boy, g_en, g_boy, sonuc, ek in sonuclar:
        print(f"{ad:<21} {sayfa_adi:<17} {en:>4}x{boy:<5} {olcek:>6.3f} {p_en:>4}x{p_boy:<5} {g_en:>4}x{g_boy:<5}  {sonuc}{ek}")
    return 1 if any(s[-2] in ("TAŞTI", "OYNADI") for s in sonuclar) else 0


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
    arg.add_argument("--yalniz", default="", help="yalnız adında bu metin geçen senaryoları ölç (ör. yk-)")
    a = arg.parse_args()
    if a.cikti:
        os.makedirs(a.cikti, exist_ok=True)
    return ariza_olc(a) if a.ariza else ekran_olc(a)


if __name__ == "__main__":
    sys.exit(main())
