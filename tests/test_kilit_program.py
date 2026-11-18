"""Kilit programı yalnız sınıf/ders/saat gösterir; gerçek okul verisi yoktur."""

from __future__ import annotations

import pytest

from tahta_ajan import ekran

BUGUN = "2026-11-17"


def ders(no=1, bas="08:00", bit="08:40", sube="9/A", adi="Örnek Ders", **ek):
    return {"ders_no": no, "baslangic": bas, "bitis": bit, "sube": sube, "ders_adi": adi, **ek}


def durum(satirlar, **ek):
    return {"gun_programi": {"tarih": BUGUN, "dersler": satirlar, **ek}}


def test_eski_sunucu_ve_bozuk_program_paneli_gizler():
    for veri in ({}, {"gun_programi": None}, {"gun_programi": []}, {"gun_programi": {"tarih": "bozuk"}}):
        assert not ekran.gunluk_program_gorunumu(veri, bugun=BUGUN)["gorunur"]


def test_sunucu_null_gonderirse_ya_da_anahtar_yoksa_kutu_hic_gosterilmez():
    """Program/şube yokken sunucu `null` gönderir; eski sunucuda anahtar hiç yoktur: ikisinde de kutu yok."""
    for veri in ({"gun_programi": None}, {"kilitli": True}):
        g = ekran.gunluk_program_gorunumu(veri, sayfa=None, bugun=BUGUN, simdi="09:00")
        assert not g["gorunur"] and not g["satirlar"] and not g["ileti"]


def test_tahtanin_tarihi_farkliysa_program_kaybolmaz_baslik_sunucunun_tarihini_tasir():
    """Tahtanın saati yanlış olabilir: esas sunucunun tarihidir (eskiyeni servis `gecerli_sn` ile kaldırır)."""
    ayni = ekran.gunluk_program_gorunumu(durum([ders()]), bugun=BUGUN)
    assert ayni["gorunur"] and ayni["baslik"] == "Bugünün ders programı"
    farkli = ekran.gunluk_program_gorunumu(durum([ders()]), bugun="2026-11-18")
    assert farkli["gorunur"] and len(farkli["satirlar"]) == 1
    assert farkli["baslik"] == "17 Kasım Salı ders programı" and "Bugün" not in farkli["baslik"]


def test_dersler_varken_de_sunucunun_iletisi_gosterilir():
    g = ekran.gunluk_program_gorunumu(durum([ders()], ileti="Bugün program değişti."), bugun=BUGUN)
    assert len(g["satirlar"]) == 1 and g["ileti"] == "Bugün program değişti."
    assert ekran.gunluk_program_gorunumu(durum([ders()]), bugun=BUGUN)["ileti"] == ""
    # Servisin kabul ettiği en uzun ileti (160) ekranda da atılmaz.
    uzun = "a" * ekran.KILIT_PROGRAM_ILETI_SINIRI
    assert ekran.gunluk_program_gorunumu(durum([ders()], ileti=uzun), bugun=BUGUN)["ileti"] == uzun


def _on_ders():
    # 08:00–08:40, 08:50–09:30, … on ders: üç sayfa (4 + 4 + 2).
    return [ders(no=i + 1, bas=f"{8 + (i * 50) // 60:02d}:{(i * 50) % 60:02d}",
                 bit=f"{8 + (i * 50 + 40) // 60:02d}:{(i * 50 + 40) % 60:02d}") for i in range(10)]


@pytest.mark.parametrize(("simdi", "sayfa"), [
    ("07:30", 0),  # gün başlamadı: ilk ders
    ("08:10", 0),  # 1. ders sürüyor
    ("11:15", 1),  # 4. ders bitti (11:10), teneffüs: sıradaki 5. ders ikinci sayfada
    ("11:30", 1),  # 5. ders sürüyor
    ("15:00", 2),  # 9. ders (14:40–15:20) üçüncü sayfada
    ("18:00", 2),  # bütün dersler bitti: son sayfa
])
def test_program_simdiki_ya_da_siradaki_dersin_sayfasindan_acilir(simdi, sayfa):
    g = ekran.gunluk_program_gorunumu(durum(_on_ders()), sayfa=None, bugun=BUGUN, simdi=simdi)
    assert g["sayfa"] == sayfa and g["sayfa_sayisi"] == 3


def test_otomatik_sayfa_tarih_farkliysa_ilk_sayfadir_elle_secim_korunur():
    assert ekran.gunluk_program_gorunumu(durum(_on_ders()), sayfa=None, bugun="2026-11-18", simdi="15:00")["sayfa"] == 0
    assert ekran.gunluk_program_gorunumu(durum(_on_ders()), sayfa=0, bugun=BUGUN, simdi="15:00")["sayfa"] == 0
    assert ekran.gunluk_program_gorunumu(durum([]), sayfa=None, bugun=BUGUN, simdi="15:00")["sayfa"] == 0


def test_ogretmen_ve_ogrenci_alanlari_kopyalanmaz():
    g = ekran.gunluk_program_gorunumu(durum([ders(ogretmen="Yapay Öğretmen", ogrenci="Yapay Öğrenci")]), bugun=BUGUN)
    assert g["gorunur"] and g["satirlar"] == [{"ders_no": 1, "baslangic": "08:00", "bitis": "08:40",
                                              "sube": "9/A", "ders": "Örnek Ders"}]
    assert "Yapay" not in str(g)


@pytest.mark.parametrize("degisiklik", [
    {"ders_no": True}, {"ders_no": 0}, {"ders_no": "1"}, {"baslangic": "25:00"},
    {"bitis": "08:00"}, {"sube": ""}, {"ders_adi": "a" * 81}, {"ders_adi": "bir\nik i"},
    {"ders_adi": "12345678901"}, {"sube": "a" * 17},
])
def test_bozuk_satirlar_gosterilmez(degisiklik):
    satir = ders()
    satir.update(degisiklik)
    assert not ekran.gunluk_program_gorunumu(durum([satir]), bugun=BUGUN)["satirlar"]


def test_bos_gun_ve_tatil_iletisi():
    g = ekran.gunluk_program_gorunumu(durum([], ileti="Bugün ders yok."), bugun=BUGUN)
    assert g["gorunur"] and g["ileti"] == "Bugün ders yok." and g["sayfa_sayisi"] == 1


def test_ikili_egitimde_saatle_siralar_ayni_ders_no_karismaz():
    g = ekran.gunluk_program_gorunumu(durum([ders(bas="13:00", bit="13:40", sube="10/A"),
                                           ders(), ders()]), bugun=BUGUN)
    assert [(s["sube"], s["baslangic"]) for s in g["satirlar"]] == [("9/A", "08:00"), ("10/A", "13:00")]


def test_yirmi_dort_satir_sinirli_dortlu_sayfalanir():
    satirlar = [ders(no=i % 12 + 1, sube=f"{9 + i // 12}/A",
                     bas=f"{8 + i // 2:02d}:{i % 2 * 30:02d}",
                     bit=f"{8 + i // 2:02d}:{i % 2 * 30 + 20:02d}") for i in range(25)]
    ilk = ekran.gunluk_program_gorunumu(durum(satirlar), bugun=BUGUN)
    son = ekran.gunluk_program_gorunumu(durum(satirlar), sayfa=999, bugun=BUGUN)
    assert len(ilk["satirlar"]) == len(son["satirlar"]) == 4
    assert ilk["sayfa_sayisi"] == 6 and son["sayfa"] == 5
    assert son["sayfa_metni"] == "6 / 6"
    assert ekran.gunluk_program_gorunumu(durum(satirlar), sayfa=-9, bugun=BUGUN)["sayfa"] == 0


def test_satir_metni_isaretleme_dili_olarak_islenmez():
    g = ekran.gunluk_program_gorunumu(durum([ders(adi="<b>Örnek Ders</b>")]), bugun=BUGUN)
    assert g["satirlar"][0]["ders"] == "<b>Örnek Ders</b>"
    # GTK çağrısı set_text'tir; metin set_markup'a verilmez.


def test_olcekli_yazi_ve_sabit_dort_satir():
    assert ekran.KILIT_PROGRAM_SAYFA_SATIRI == 4
    for en, boy in ((1024, 768), (1366, 768), (1920, 1080), (3840, 2160)):
        olcek = ekran.ekran_olcegi(en, boy)
        assert f"font-size: {ekran.olcekle(24, olcek)}px".encode() in ekran.olcekli_stil(ekran.STIL_OLCU, olcek)


def test_program_saat_sutununa_degil_tus_takiminin_altina_eklenir():
    """GTK olmayan ortamda yerleşim sözleşmesi; gerçek render ölçümü değildir."""
    from pathlib import Path

    kaynak = Path(ekran.__file__).read_text(encoding="utf-8")
    sayfa = kaynak.split("        def _kilit_sayfasi(self):", 1)[1].split("        def _kilit_program_gec", 1)[0]
    assert "self._ekle(sol, self.kilit_program_kutu" not in sayfa
    assert sayfa.index("sag.pack_start(self.kod_kutusu") < sayfa.index("sag.pack_start(self.kilit_usb_dugmesi")
    assert sayfa.index("sag.pack_start(self.kilit_usb_dugmesi") < sayfa.index("self._ekle(sag, self.kilit_program_kutu")
    # Kod ve USB yokken de program varsa sütun görünür; gece yarısı
    # program kaybolunca yalnız boş panel sütunu açık tutmaz.
    assert 'or self.kilit_program_kutu.get_visible())' in kaynak
    assert 'or gorunum["gorunur"])' in kaynak


def test_sayfa_degisince_yerlesim_sabit_kalir_ve_elle_secim_gecicidir():
    """GTK olmayan ortamda yerleşim sözleşmesi (gerçek ölçüm: scripts/ekran_olcum.py, kilit-program-*)."""
    from pathlib import Path

    kaynak = Path(ekran.__file__).read_text(encoding="utf-8")
    sayfa = kaynak.split("        def _kilit_sayfasi(self):", 1)[1].split("        def _kilit_program_gec", 1)[0]
    # Satırların doğal eni sabit: sayfadan sayfaya metin uzunluğu sütunu (ve tuş takımını) kaydırmaz.
    assert "etiket.set_width_chars(44)" in sayfa and "etiket.set_max_width_chars(44)" in sayfa
    ciz = kaynak.split("        def _kilit_program_ciz(self):", 1)[1].split("        def _duyuru_sayfasi", 1)[0]
    # Çok sayfalı programda son sayfanın boş satırları da yer tutar: düğmeler ve tuş takımı oynamaz.
    assert "etiket.set_visible(bool(satir) or cok_sayfa)" in ciz
    # Elle seçim yokken şimdiki/sıradaki dersin sayfası; Önceki/Sonraki seçimi süreyle korunur.
    assert "self.kilit_program_sayfa if elle else None" in ciz
    assert "self.kilit_program_baslik.set_text(gorunum[\"baslik\"])" in ciz
    gec = kaynak.split("        def _kilit_program_gec(self, fark):", 1)[1].split("        def _kilit_program_ciz", 1)[0]
    assert "KILIT_PROGRAM_ELLE_SN" in gec
