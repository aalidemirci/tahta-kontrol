"""Tahta ekranının ekran boyutuna orantılı ölçüsü (0.7.1): GTK olmadan çalışan saf işlevler.

0.7.0'da sabit piksel genişlikler (gözetmen kodu ve yoklama PIN'i sayfalarında 640/720 px sütun,
150 px tuşlar, sabit yazı boyları) pencereyi 1427 px'e zorluyordu; 1280x800 ve 1366x768 ekranda
pencere ekrandan taşıyor, kilit ve duyuru ekranı sağa kayıyordu. Ölçüler artık 1920x1080 için
yazılır ve ekran_olcegi() ile çarpılır.
"""

import re

import pytest

from tahta_ajan import ekran

# 1920x1080'de ölçülen en geniş sayfanın (yoklama PIN'i) en küçük eni; 0.7.0 kusur raporundan.
EN_GENIS_SAYFA_1920 = 1427


@pytest.mark.parametrize(
    ("en", "boy", "beklenen"),
    [
        (1920, 1080, 1.0),
        (3840, 2160, 2.0),
        (1366, 768, 0.7111),  # yükseklik ve genişlik aynı oranda
        (1280, 800, 0.6667),  # 16:10: genişlik belirler
        (1024, 768, 0.5333),  # 4:3: genişlik belirler
        (1080, 1920, 1.0),  # portre: 1080x1920'ye göre
        (800, 1280, 0.6667),
        (0, 0, 1.0),  # bilinmeyen ekran
        (320, 240, ekran.OLCEK_EN_AZ),
        (15360, 8640, ekran.OLCEK_EN_COK),
    ],
)
def test_ekran_olcegi(en, boy, beklenen):
    assert ekran.ekran_olcegi(en, boy) == pytest.approx(beklenen, abs=1e-4)


@pytest.mark.parametrize(("en", "boy"), [(1024, 768), (1280, 800), (1366, 768), (1920, 1080), (3840, 2160)])
def test_olcekli_en_genis_sayfa_ekrana_sigar(en, boy):
    """0.7.0'ın 1427 px'lik sayfası her ekranda ölçekle küçülür ve ekranın eninden dar kalır;
    1080 px'lik referans yüksekliği de ekranın boyunu aşmaz."""
    olcek = ekran.ekran_olcegi(en, boy)
    assert ekran.olcekle(EN_GENIS_SAYFA_1920, olcek) < en
    assert ekran.olcekle(ekran.OLCEK_TABAN_EN, olcek) <= en
    assert ekran.olcekle(ekran.OLCEK_TABAN_BOY, olcek) <= boy


def test_dikey_mi():
    assert ekran.dikey_mi(1080, 1920) and ekran.dikey_mi(768, 1024)
    assert not ekran.dikey_mi(1920, 1080) and not ekran.dikey_mi(1024, 768) and not ekran.dikey_mi(0, 0)


def test_olcekle_eksi_ve_sifir_degismez_en_az_bir_piksel():
    assert ekran.olcekle(-1, 0.5) == -1 and ekran.olcekle(0, 2.0) == 0
    assert ekran.olcekle(1, 0.4) == 1 and ekran.olcekle(150, 0.6667) == 100 and ekran.olcekle(96, 2.0) == 192


def test_olcekli_stil_butun_pikselleri_olcekler():
    stil = ekran.olcekli_stil(ekran.STIL_OLCU, 0.5)
    assert b"#saat { font-size: 75px;" in stil and b"#kod { font-size: 28px; letter-spacing: 6px; }" in stil
    assert b"padding: 14px 24px; border-bottom-width: 3px;" in stil  # üst bant
    assert b"border-width: 1px" in stil  # ince kenarlık kaybolmaz
    # Ölçek 1'de stil aynen kalır; hiçbir px değeri ölçeksiz kalmaz.
    assert ekran.olcekli_stil(ekran.STIL_OLCU, 1.0) == ekran.STIL_OLCU
    sayilar = [int(x) for x in re.findall(rb"(\d+)px", ekran.olcekli_stil(ekran.STIL_OLCU, 2.0))]
    asil = [int(x) for x in re.findall(rb"(\d+)px", ekran.STIL_OLCU)]
    assert sayilar == [2 * x for x in asil]


def test_ariza_stili_de_olceklenir():
    from tahta_ajan import ariza_penceresi

    assert b"#ariza-baslik { font-size: 20px;" in ekran.olcekli_stil(ariza_penceresi.STIL_OLCU, 0.5)


def test_pencere_olcusu_ekrani_asmaz():
    assert ekran.pencere_olcusu(1240, 860, 1920, 1080, 1.0) == (1240, 860)
    assert ekran.pencere_olcusu(1240, 860, 3840, 2160, 2.0) == (2480, 1720)
    en, boy = ekran.pencere_olcusu(1240, 860, 1024, 768, ekran.ekran_olcegi(1024, 768))
    assert en <= 1024 * 0.94 and boy <= 768 * 0.9
    assert ekran.pencere_olcusu(1240, 860, 0, 0, 1.0) == (1240, 860)


def test_liste_punto_olcekli_sinirlar():
    assert ekran.liste_punto(1, 1080) == 44 and ekran.liste_punto(40, 1080) == 22
    olcek = ekran.ekran_olcegi(1366, 768)
    assert ekran.liste_punto(1, 768, olcek) == ekran.olcekle(44, olcek)
    assert ekran.liste_punto(40, 768, olcek) == ekran.olcekle(22, olcek)
    # 20 satırlık liste 1366x768'de taşmaz: satır yüksekliği x satır, kullanılabilir alandan az.
    assert ekran.liste_punto(20, 768, olcek) * 1.38 * 20 <= 768 - 430 * olcek


def test_duyuru_duzeni_dar_ekranda_satir_sigar():
    satirlar = [f"Ab*** Cd**** …{i:02d}  →  10/B Dersliği, koltuk {i}" for i in range(60)]
    metin = "Sınav oturma listesi · 9/A\n\n" + "\n".join(satirlar)
    eski = ekran.duyuru_duzeni(metin, 1080)
    assert len(eski["sutunlar"]) == 3 and 20 <= eski["punto"] <= 40  # eski çağrı aynı kalır
    for en, boy in ((1024, 768), (1280, 800), (1366, 768), (1920, 1080), (3840, 2160)):
        olcek = ekran.ekran_olcegi(en, boy)
        duzen = ekran.duyuru_duzeni(metin, boy, olcek, en)
        en_uzun = max(len(s) for s in satirlar)
        sutun = len(duzen["sutunlar"])
        tahmin = sutun * en_uzun * duzen["punto"] * 0.6 + (160 + 70 * (sutun - 1)) * olcek
        assert tahmin <= en or duzen["punto"] == ekran.olcekle(20, olcek), (en, boy, duzen["punto"])
        assert ekran.olcekle(20, olcek) <= duzen["punto"] <= ekran.olcekle(40, olcek)


def test_portre_ekranda_duyuru_sutunu_ve_liste_yazisi_ene_sigar():
    satirlar = [f"Ab*** Cd**** …{i:02d}  →  10/B Dersliği, koltuk {i}" for i in range(60)]
    duzen = ekran.duyuru_duzeni("\n".join(satirlar), 1920, 1.0, 1080)
    assert len(duzen["sutunlar"]) < 3  # yatayda 3 sütun; portrede en küçük yazıyla bile sığmaz
    en_uzun = max(len(s) for s in satirlar)
    assert len(duzen["sutunlar"]) * en_uzun * 0.6 * duzen["punto"] <= 1080
    # Sınav giriş listesi: portrede ekran boyu yazıyı büyütür ama en sınırlar.
    assert ekran.liste_sutun_sayisi(40) == 2 and ekran.liste_sutun_sayisi(40, 1080, 1.0) == 1
    for en, boy in ((1024, 768), (1280, 800), (1366, 768), (1920, 1080), (3840, 2160)):
        assert ekran.liste_sutun_sayisi(60, en, ekran.ekran_olcegi(en, boy)) == 3  # yatay ekranda değişmez
    sutun = ekran.liste_sutun_sayisi(40, 1080, 1.0)
    punto = ekran.liste_punto(40, 1920, 1.0, 1080, sutun)
    assert sutun * ekran.LISTE_SATIR_KARAKTER * 0.6 * punto <= 1080


def test_yoklama_sutun_olcekli():
    assert ekran.yoklama_sutun(1920) == 6 and ekran.yoklama_sutun(800) == 2  # eski çağrı aynı
    for en, boy in ((1024, 768), (1280, 800), (1366, 768), (1920, 1080), (3840, 2160)):
        olcek = ekran.ekran_olcegi(en, boy)
        sutun = ekran.yoklama_sutun(en, olcek)
        assert sutun == 6
        # Akışın en küçük eni (sütun x düğme + aralık + kenarlar) ekrana sığar.
        assert sutun * ekran.olcekle(ekran.YOKLAMA_DUGME_EN + 12, olcek) + ekran.olcekle(120, olcek) <= en
    assert ekran.yoklama_sutun(1080, ekran.ekran_olcegi(1080, 1920)) == 3  # portre


@pytest.mark.parametrize(("en", "boy"), [(1024, 768), (1280, 800), (1366, 768), (1920, 1080), (3840, 2160), (1080, 1920)])
@pytest.mark.parametrize("n", [1, 12, 35, 60])
def test_gozetmen_izgarasi_ekrana_sigar(en, boy, n):
    olcek = ekran.ekran_olcegi(en, boy)
    sutun = ekran.izgara_sutun(n, en, boy)
    satir = -(-n // sutun)
    dugme_en, dugme_boy = ekran.izgara_dugme_olcusu(n, en, boy, olcek)
    assert sutun * (dugme_en + ekran.olcekle(10, olcek)) <= en
    if n <= 35:  # kalabalık salon (60) kaydırılabilir; olağan salon tek ekrana sığar
        assert satir * (dugme_boy + ekran.olcekle(10, olcek)) + ekran.olcekle(430, olcek) <= boy


def test_izgara_sutun_eski_cagri_ayni():
    assert ekran.izgara_sutun(40) == 9 and ekran.izgara_sutun(60) == 11 and ekran.izgara_sutun(0) == 2


def test_logo_olcusu_olcekli():
    assert ekran.logo_olcusu(400, 400) == (96, 96)
    assert ekran.logo_olcusu(400, 400, 0.5) == (48, 48)
    assert ekran.logo_olcusu(1000, 100, 2.0) == (640, 64)
    assert ekran.logo_olcusu(0, 10, 0.5) == (0, 0)


def test_ekran_kodunda_sabit_piksel_yok():
    """Sayfa kurucularında piksel ölçüsü yalnız _olcu/_kutu/_izgara/_kenar/_ekle/_dugme ile verilir;
    doğrudan set_size_request(<sayı>), spacing=<sayı>, set_margin_*(<sayı>) ve sıfırdan büyük
    pack dolgusu yazılmaz (GtkStack en geniş sayfaya göre boyutlanır; tek sabit ölçü pencereyi taşırır)."""
    from pathlib import Path

    kaynak = Path(ekran.__file__).read_text(encoding="utf-8")
    yasak = [
        r"set_size_request\(\s*\d",
        r"spacing=[1-9]",
        r"set_margin_(start|end|top|bottom)\(\s*\d",
        r"pack_(start|end)\([^()]*,\s*[1-9]\d*\)",
        r"Gtk\.Grid\([^)]*spacing",
    ]
    for desen in yasak:
        assert not re.search(desen, kaynak), desen


def test_yoklama_dugme_boyu_alan_olculmeden_tam_boy():
    assert ekran.yoklama_dugme_boyu(32, 6, 1) == ekran.YOKLAMA_DUGME_BOY
    assert ekran.yoklama_dugme_boyu(0, 6, 600) == ekran.YOKLAMA_DUGME_BOY
    assert ekran.yoklama_dugme_boyu(32, 6, 1, 0.7111) == ekran.olcekle(ekran.YOKLAMA_DUGME_BOY, 0.7111)


def test_yoklama_dugme_boyu_kisa_listede_tam_boy():
    assert ekran.yoklama_dugme_boyu(12, 6, 680) == ekran.YOKLAMA_DUGME_BOY


def test_yoklama_32_kisi_1366x768_alana_sigar():
    """1366x768'de 32 kişilik şubenin son satırı liste alanının altında yarım kalıyordu (0.7.1 denetimi)."""
    olcek = ekran.ekran_olcegi(1366, 768)
    sutun = ekran.yoklama_sutun(1366, olcek)
    alan = 470  # Xvfb 1366x768'de ölçülen liste alanı boyu (yaklaşık)
    boy = ekran.yoklama_dugme_boyu(32, sutun, alan, olcek)
    satir = -(-32 // sutun)
    aralik = ekran.olcekle(ekran.YOKLAMA_SATIR_ARALIGI, olcek)
    assert satir * (boy + ekran.YOKLAMA_HUCRE_PAYI) + (satir - 1) * aralik <= alan
    assert boy >= ekran.olcekle(ekran.YOKLAMA_DUGME_BOY_EN_AZ, olcek)


def test_yoklama_dugme_boyu_alt_sinir():
    """Çok uzun listede düğme iki satırlık yazının altına inmez; liste kaydırılır."""
    assert ekran.yoklama_dugme_boyu(60, 6, 500) == ekran.YOKLAMA_DUGME_BOY_EN_AZ


@pytest.mark.parametrize(("en", "boy"), [(1024, 768), (1280, 800), (1366, 768), (1920, 1080)])
def test_sinav_listesi_uzun_maskeyle_ene_sigar(en, boy):
    """Uzun maskeli adla 34 kişilik salon: 1024x768'de şube sütunu ekrandan taşıyordu (0.7.1 denetimi)."""
    liste = [{"k": i, "a": "Mu****** Em** Ka*************", "n": f"{i:02d}", "s": "12/C"} for i in range(1, 35)]
    olcek = ekran.ekran_olcegi(en, boy)
    karakter = ekran.liste_satir_karakteri(liste)
    assert karakter > ekran.LISTE_SATIR_KARAKTER
    sutun = ekran.liste_sutun_sayisi(len(liste), en, olcek, karakter)
    punto = ekran.liste_punto(-(-len(liste) // sutun), boy, olcek, en, sutun, karakter)
    gerekli = sutun * karakter * 0.6 * punto + (120 + 56 * (sutun - 1) + 88 * sutun) * olcek
    assert gerekli <= en


def test_liste_satir_karakteri_kisa_listede_tahmin():
    assert ekran.liste_satir_karakteri([]) == ekran.LISTE_SATIR_KARAKTER
    assert ekran.liste_satir_karakteri([{"k": 1, "a": "Ah*** Yı****", "n": "01", "s": "9/A"}]) == ekran.LISTE_SATIR_KARAKTER
