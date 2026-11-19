"""Panel kabuğu (0.15.0): sol yan menü, dar ekranda çekmece ve üst çubuk, telefonda alt çubuk.

Kabuk yalnız çerçevedir: sayfa içerikleri, adresler ve POST uçları değişmez. Bütün veriler uydurmadır.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest
from test_yoklama import ogrenci_yukle
from yardimci import gir, kullanici_ekle, kur_ve_gir, sorgu, tahta_ekle

from tahta_sunucu import tema, web

KOK = Path(web.__file__).resolve().parent
STIL = (KOK / "statik" / "stil.css").read_text(encoding="utf-8")
BETIK = (KOK / "statik" / "panel.js").read_text(encoding="utf-8")
TABAN = (KOK / "sablonlar" / "taban.html").read_text(encoding="utf-8")

YONETICI = {"rol": "yonetici"}
IDARECI = {"rol": "idareci"}
# Menüden çıkmayan (sayfa olmayan ya da kabuksuz) GET rotaları.
SAYFA_DISI_ON_EK = ("/api", "/ajan", "/marka", "/statik", "/kur", "/saglik", "/yerel", "/giris", "/kurulum")


def ust_ogeler(menu: dict) -> list[dict]:
    return [o for k in menu["kumeler"] for o in k["ogeler"]]


def yan_menu(sayfa: str) -> str:
    return sayfa.split('id="menu"')[1].split("</aside>")[0]


def alt_cubuk(sayfa: str) -> str:
    return sayfa.split('class="alt-cubuk"')[1].split("</nav>")[0]


def get_yollari(uygulama) -> list[str]:
    return [r.path for r in uygulama.routes if "GET" in (getattr(r, "methods", None) or ())]


def sayfa_yollari(uygulama) -> list[str]:
    yollar = []
    for yol in get_yollari(uygulama):
        if yol.startswith(SAYFA_DISI_ON_EK) or yol.endswith((".csv", ".txt")) or "/indir/" in yol:
            continue
        yollar.append(re.sub(r"\{[^}]+\}", "1", yol))
    return yollar


def ortam_blogu(stil: str, sorgu: str) -> str:
    """`sorgu` ile başlayan ilk @media bloğunun gövdesi (dengeli süslü ayraç)."""
    bas = stil.index(sorgu)
    ac = stil.index("{", bas)
    derinlik, i = 1, ac + 1
    while derinlik:
        derinlik += {"{": 1, "}": -1}.get(stil[i], 0)
        i += 1
    return stil[ac + 1 : i - 1]


# ---- MENU veri yapısı ---------------------------------------------------------------
def test_menu_uc_kume_ve_en_cok_on_oge():
    assert [k["kume"] for k in web.MENU] == ["Her gün", "Dönemlik", "Yönetim"]
    ogeler = [o for k in web.MENU for o in k["ogeler"]]
    assert len(ogeler) <= 10, "menüye öğe eklenirse biri çıkar"
    for oge in ogeler:
        assert f'id="m-{oge["simge"]}"' in TABAN, oge["ad"]
        for alt in oge.get("alt", []):
            assert not {"simge", "alt", "alt_cubuk"} & set(alt), alt["ad"]
    for kimlik in ("m-menu", "m-kapat", "m-cikis"):
        assert f'id="{kimlik}"' in TABAN


def test_menu_yollari_var_olan_adreslerdir(uygulama):
    yollar = set(get_yollari(uygulama))
    for kume in web.MENU:
        for oge in kume["ogeler"]:
            for o in [oge, *oge.get("alt", [])]:
                assert o["yol"] in yollar, o["ad"]
    assert web.MENU_ACIL["yol"] in yollar


def test_her_sayfada_tek_etkin_oge(uygulama):
    yollar = sayfa_yollari(uygulama)
    assert len(yollar) > 35
    yalniz_yonetici = [o for k in web.MENU for o in k["ogeler"] if o.get("rol") == "yonetici"]
    for yol in yollar:
        acil = web._secili(web.MENU_ACIL, yol)
        ogeler = ust_ogeler(web.menu_gorunumu(YONETICI, yol))
        secili = sum(o["secili"] for o in ogeler) + acil
        if yol == "/ara":  # 0.20.0: genel arama menü öğesi DEĞİLDİR; sonuç sayfasında hiçbir öğe vurgulanmaz
            assert secili == 0 and not any(o["secili"] for o in ust_ogeler(web.menu_gorunumu(IDARECI, yol)))
            continue
        assert secili == 1, yol
        # İdareci: yöneticiye özel sayfalar (ona zaten açılmaz) dışında her sayfada bir üst öğe vurguludur.
        if any(web._secili(o, yol) for o in yalniz_yonetici):
            continue
        ogeler = ust_ogeler(web.menu_gorunumu(IDARECI, yol))
        assert sum(o["secili"] for o in ogeler) + acil >= 1, yol


def test_menu_gorunumu_rol_sayi_ve_esler():
    yonetici = web.menu_gorunumu(YONETICI, "/arizalar", {"tahtalar": 3, "yedekler": 1})
    idareci = web.menu_gorunumu(IDARECI, "/gruplar", {"tahtalar": 3})
    assert len(ust_ogeler(yonetici)) == 10 and len(ust_ogeler(idareci)) == 8  # 0.18.0: Bugün eklendi (üst sınır 10)
    # 0.17.0: alt liste yok; bölümün sekme şeridindeki sayfalar üst öğeyi seçer. 0.18.0: rozet "tahtalar" sayısıdır
    # (süren arıza + yöneticide onay bekleyen tahta); Bugün rozet taşımaz; Yedekler yedek uyarısı sayısını taşır.
    bugun, tahtalar = ust_ogeler(yonetici)[:2]
    assert (bugun["ad"], bugun["yol"], bugun["secili"], bugun["sayi"]) == ("Bugün", "/", False, 0)
    assert (tahtalar["ad"], tahtalar["yol"], tahtalar["secili"], tahtalar["sayi"]) == ("Tahtalar", "/tahtalar", True, 3)
    assert next(o for o in ust_ogeler(yonetici) if o["ad"] == "Yedekler")["sayi"] == 1
    assert "alt" not in tahtalar and all("alt" not in o for k in web.MENU for o in k["ogeler"])
    # İdareci: rolle gizlenen sekmenin (Gruplar) sayfasında da üst öğe vurgulu.
    assert ust_ogeler(idareci)[1]["secili"] and not ust_ogeler(idareci)[0]["secili"]
    for yol in ("/tahtalar", "/tahtalar/ice-aktar", "/tahta/3", "/ariza/2", "/envanter", "/ekle"):
        ogeler = ust_ogeler(web.menu_gorunumu(IDARECI, yol))
        assert ogeler[1]["secili"] and not ogeler[0]["secili"], yol
    # "/" yalnız Bugün'ü seçer (0.17.0'da Tahtalar'ı seçerdi); "/" eşi önek olarak eşleşmez.
    kok = ust_ogeler(web.menu_gorunumu(IDARECI, "/"))
    assert kok[0]["secili"] and sum(o["secili"] for o in kok) == 1
    assert "/" not in next(o for k in web.MENU for o in k["ogeler"] if o["ad"] == "Tahtalar")["esler"]
    assert not ust_ogeler(web.menu_gorunumu(YONETICI, "/tahtalar.csv"))[1]["secili"]  # sayfa değil
    assert [k["ad"] for k in idareci["kumeler"]] == ["Her gün", "Dönemlik", "Yönetim"]
    assert [o["ad"] for o in idareci["kumeler"][2]["ogeler"]] == ["İşlem kaydı"]
    assert [o["ad"] for o in yonetici["alt_cubuk"]] == ["Bugün", "Tahtalar", "Duyurular", "Yoklama"]


# ---- HTML iskeleti -------------------------------------------------------------------
def test_idareci_menusunde_yonetici_ogesi_yok(uygulama, panel):
    kur_ve_gir(panel)
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    sayfa = panel.get("/").text
    for parca in (yan_menu(sayfa), alt_cubuk(sayfa)):
        for yol in ("/ayarlar", "/yedekler", "/kullanicilar", "/ekle", "/gruplar"):
            assert f'href="{yol}"' not in parca, yol
    menu = yan_menu(sayfa)
    for yol in ("/tahtalar", "/kayit", "/acil"):
        assert f'href="{yol}"' in menu, yol
    # 0.17.0: Arızalar ve Envanter yan menüde değil, Tahtalar bölümünün sekme şeridindedir.
    assert 'href="/arizalar"' not in menu and 'class="yan-alt"' not in sayfa
    serit = panel.get("/tahtalar").text.split('aria-label="Tahtalar bölümü"')[1].split("</nav>")[0]
    assert 'href="/arizalar"' in serit and 'href="/envanter"' in serit and "/gruplar" not in serit and "/ekle" not in serit
    assert menu.count('<use href="#m-') - menu.count("#m-kapat") - menu.count("#m-cikis") == 8  # 0.18.0: + Bugün
    assert ">Yönetim<" in menu and ">İdareci<" in menu


def test_kabuk_iskeleti(uygulama, panel):
    kur_ve_gir(panel)
    sayfa = panel.get("/").text
    sira = [sayfa.index(p) for p in ('class="atla"', 'class="ust-cubuk"', 'id="menu"', 'class="perde"', '<main id="icerik"',
                                     'class="alt-cubuk"', 'id="onay-diyalog"')]  # fmt: skip
    assert sira == sorted(sira)
    assert sayfa.count('href="#menu"') == 2 and sayfa.count('aria-controls="menu"') == 2
    assert '<a class="perde" href="#icerik" tabindex="-1" aria-hidden="true">' in sayfa
    assert '<a class="yan-kapat" href="#icerik">' in sayfa
    assert '<main id="icerik" tabindex="-1">' in sayfa
    menu = yan_menu(sayfa)
    assert 'action="/cikis"' in menu and sayfa.count('action="/cikis"') == 1
    assert menu.index('class="acil-dugme" href="/acil"') < menu.index('<form class="genel-ara"') < menu.index("<nav")
    assert sayfa.count('aria-label="Ana menü"') == 1 and '<nav class="yan-gezinme" aria-label="Ana menü">' in sayfa
    assert [k for k in re.findall(r'<p class="yan-kume" id="kume-\d">([^<]+)</p>', menu)] == ["Her gün", "Dönemlik", "Yönetim"]
    assert "Deneme Yönetici" in menu and ">Yönetici<" in menu
    # Üst çubukta okul adı ve (0.20.0) aramaya giden simge: Menü · kimlik · Ara · Acil. Arama KUTUSU yalnız yan
    # menüdedir (sayfada tek arama girdisi); üst çubukta kutu yoktur.
    ust = sayfa.split('class="ust-cubuk"')[1].split("</header>")[0]
    assert "Örnek Anadolu Lisesi" in ust and 'type="search"' not in ust
    sira = [ust.index(p) for p in ('class="menu-ac"', 'class="kimlik"', '<a class="ust-ara" href="/ara">', 'class="acil-dugme"')]
    assert sira == sorted(sira)
    assert sayfa.count('type="search"') == 1 and 'type="search" id="genel-ara" name="q"' in menu


def test_etkin_oge_isaretleri(uygulama, panel, tahta):
    kur_ve_gir(panel)
    kimlik = tahta_ekle(panel, tahta, "T-1")["X-Tahta-Id"]

    def menu(yol: str) -> str:
        yanit = panel.get(yol)
        assert yanit.status_code == 200, yol
        return yan_menu(yanit.text)

    for yol in ("/arizalar", f"/tahta/{kimlik}", "/tahtalar", "/envanter", "/gruplar", "/tahtalar/ice-aktar", "/ekle"):
        m = menu(yol)
        assert '<a href="/tahtalar" aria-current="page">' in m and m.count('aria-current="page"') == 1, yol
        assert "<li data-secili>" in m and "data-icinde" not in m, yol
    m = menu("/")  # 0.18.0: "/" Bugün'dür
    assert '<a href="/" aria-current="page">' in m and m.count('aria-current="page"') == 1 and '<a href="/tahtalar">' in m
    yanit = panel.get("/acil").text
    assert yanit.count('class="acil-dugme" href="/acil" aria-current="page"') == 2
    assert yan_menu(yanit).count('aria-current="page"') == 1  # yalnız Acil; kümelerde etkin öğe yok
    # 0.19.0: üç kişi sayfası kendi şeridini çizer (Yoklama şeridini değil) ve menüde aynı bölümdedir: şeritte
    # sekmeden sekmeye geçince vurgu başka bölüme zıplamaz. Öğretmen programı Program şeridindedir.
    for yol in ("/usb-anahtarlar", "/ogretmenler", "/ogrenciler"):
        yanit = panel.get(yol).text
        assert 'aria-label="Kişiler ve anahtarlar bölümü"' in yanit and "Yoklama bölümleri" not in yanit, yol
        m = yan_menu(yanit)
        assert re.search(r'<a href="/ogrenciler" aria-current="page">.*?<span>Kişiler ve anahtarlar</span>', m, re.S), yol
        assert m.count('aria-current="page"') == 1, yol
        assert '<a href="/yoklama">' in m and '<a href="/program">' in m, yol  # öteki bölümler etkin değil
    for yol in ("/program", "/program/uyarilar", "/program/gun", "/program/aktar", "/program/gecmis", "/ogretmen-programi"):
        yanit = panel.get(yol).text
        m = yan_menu(yanit)
        assert 'aria-label="Program bölümleri"' in yanit and "Yoklama bölümleri" not in yanit, yol
        assert '<a href="/program" aria-current="page">' in m and m.count('aria-current="page"') == 1, yol
        assert '<a href="/ogrenciler">' in m, yol  # Kişiler etkin değil


def test_her_menu_adresinde_html_de_tek_etkin_oge(uygulama, panel, tahta):
    # menu_gorunumu verisi ayrıca sınanır; burada ÜRETİLEN sayfa denetlenir (şablon işareti düşürmesin).
    kur_ve_gir(panel)
    kimlik = tahta_ekle(panel, tahta, "T-1")["X-Tahta-Id"]
    assert panel.post("/arizalar", data={"tahta_id": kimlik, "kategori": "acilis", "aciklama": ""}).status_code == 303
    yollar = [o["yol"] for k in web.MENU for o in k["ogeler"]] + [web.MENU_ACIL["yol"]]
    assert len(yollar) == 11
    for yol in yollar:
        sayfa = panel.get(yol)
        assert sayfa.status_code == 200, yol
        menu = yan_menu(sayfa.text)
        assert menu.count('aria-current="page"') == 1, yol
        assert re.search(rf'href="{re.escape(yol)}"[^>]* aria-current="page"', menu), yol
        # Rozet: sayı + ekran okuyucu metni; yan menüde ve (0.18.0) telefon alt çubuğundaki Tahtalar'da aynı sayı.
        # 0.18.0: Tahtalar rozeti süren arıza (1) + onay bekleyen tahta (0); Yedekler rozeti "yedek parolası yok" satırı.
        for oge in ("Tahtalar", "Yedekler"):
            assert f'<span>{oge}</span><span class="sayi-rozet">1</span><span class="gizli"> bekleyen iş</span></a>' in menu, (yol, oge)
        assert menu.count('class="sayi-rozet"') == 2, yol
        cubuk = alt_cubuk(sayfa.text)
        assert '<span>Tahtalar</span><span class="sayi-rozet">1</span><span class="gizli"> bekleyen iş</span></a>' in cubuk, yol
        assert cubuk.count('class="sayi-rozet"') == 1, yol  # Yedekler alt çubukta yok
    # İki açıcı da aynı adı taşır.
    assert sayfa.text.count('<use href="#m-menu"/></svg><span>Menü</span></a>') == 2 and "Tümü" not in sayfa.text


def test_idareci_gizli_sekmenin_sayfasinda_ust_oge_vurgulu(uygulama, panel):
    kur_ve_gir(panel)
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    for yol in ("/gruplar", "/ekle"):
        yanit = panel.get(yol)
        assert yanit.status_code == 200, yol
        menu = yan_menu(yanit.text)
        assert re.search(r'<li data-secili>\s*<a href="/tahtalar" aria-current="page">', menu), yol
        assert f'href="{yol}"' not in yanit.text, yol  # ne menüde ne sekme şeridinde
        assert '<a href="/tahtalar" aria-current="page">' in alt_cubuk(yanit.text), yol


def test_alt_cubuk_ogeleri(uygulama, panel):
    kur_ve_gir(panel)
    cubuk = alt_cubuk(panel.get("/duyurular").text)
    assert re.findall(r'<a (?:class="menu-ac" )?href="([^"]+)"', cubuk) == ["/", "/tahtalar", "/duyurular", "/yoklama", "#menu"]
    assert '<a href="/duyurular" aria-current="page">' in cubuk and cubuk.count("aria-current") == 1
    cubuk = alt_cubuk(panel.get("/yoklama/sube").text)
    assert '<a href="/yoklama" aria-current="page">' in cubuk
    # Bölümün sekme sayfasındayken (Arızalar) alt çubukta Tahtalar etkindir.
    assert '<a href="/tahtalar" aria-current="page">' in alt_cubuk(panel.get("/arizalar").text)


def test_giris_ve_kurulum_kabuksuz(uygulama, panel):
    kabuk = ('id="menu"', "ust-cubuk", "alt-cubuk", "kabuklu", "yan-menu")
    for yol in ("/kurulum", "/yedekler/geri-yukle"):  # ilk kurulum ve ilk kurulum çerçevesindeki geri yükleme
        yanit = panel.get(yol)
        assert yanit.status_code == 200 and 'class="giris-sayfasi"' in yanit.text, yol
        assert not [p for p in kabuk if p in yanit.text], yol
    kur_ve_gir(panel)
    assert '<body class="kabuklu ">' in panel.get("/").text
    # Şube defteri: geniş (çekmece kipli) gövde yalnız tablo çizilince; öğrenci listesi boşken olağan kabuk.
    assert '<body class="kabuklu ">' in panel.get("/yoklama/sube").text
    ogrenci_yukle(panel)
    assert '<body class="kabuklu genis-sayfa">' in panel.get("/yoklama/sube").text
    assert '<body class="kabuklu rapor-sayfasi">' in panel.get("/yoklama/icmal").text
    panel.cookies.clear()
    giris = panel.get("/giris")
    assert giris.status_code == 200 and not [p for p in kabuk if p in giris.text]


def test_oturumlu_giris_sayfasi_govdesi_de_kabuksuz():
    """Kabuk koşulu gövde sınıfını ALT şablonun bloğundan okur (self.govde_sinifi()): tam ekran çerçeve çizen
    sayfa oturum açıkken de kabuksuz kalır (yanına menü gelirse çerçeve taşar)."""
    from jinja2 import ChainableUndefined, Environment, FileSystemLoader

    ortam = Environment(loader=FileSystemLoader(KOK / "sablonlar"), autoescape=True, undefined=ChainableUndefined)
    ortam.filters.update(saat=str, zaman=str, tarih=str, gecen=str, kat_adi=str)
    baglam = {
        "kullanici": {"gorunen_ad": "Deneme Yönetici", "rol": "yonetici"},
        "roller": web.ROLLER,
        "menu": web.menu_gorunumu(YONETICI, "/"),
        "menu_acil": {**web.MENU_ACIL, "secili": False},
        "okul_adi": "Örnek Anadolu Lisesi",
    }
    cerceveli = ortam.get_template("yedek_onay.html").render(**baglam, kurulum=True)
    assert '<body class="giris-sayfasi">' in cerceveli and 'id="menu"' not in cerceveli and "alt-cubuk" not in cerceveli
    assert 'id="onay-diyalog"' in cerceveli  # onay diyaloğu oturuma bağlıdır, kabuğa değil
    kabuklu = ortam.get_template("yedek_onay.html").render(**baglam, kurulum=False)
    assert '<body class="kabuklu ">' in kabuklu and 'id="menu"' in kabuklu


def test_sablonlarda_form_p_icinde_degil_taban():
    # Tarayıcı <p> içindeki <form>'da <p>'yi kapatır; çıkış formu div.yan-son içindedir.
    for parca in re.findall(r"<p\b.*?</p>", TABAN, re.S):
        assert "<form" not in parca, parca[:60]
    assert re.search(r'<div class="yan-son">.*?<form method="post" action="/cikis">', TABAN, re.S)
    assert "{% if kabuklu %}" in TABAN and "'giris-sayfasi' not in govde" in TABAN


# ---- stil.css ------------------------------------------------------------------------
def test_stil_katman_ve_belirtecler():
    assert "@layer sifirla, temel, bilesen, kabuk, yardimci;" in STIL
    assert STIL.count("@layer kabuk {") == 1
    adlar = [f"--yazi-{a}" for a in ("xs", "s", "m", "l", "xl", "2xl")] + [f"--b{i}" for i in range(1, 8)]
    adlar += ["--kose-s", "--kose-m", "--kose-l", "--kose-hap", "--golge-1", "--golge-2", "--dokunma", "--dokunma-kucuk",
              "--d-yazi", "--yan-en", "--ust-boy", "--alt-boy", "--yapiskan-ust"]  # fmt: skip
    for ad in adlar:
        assert re.search(re.escape(ad) + r"\s*:", STIL), ad
    for olu in (".ana-menu", ".menu-grup", ".menu-alt", ".menu-acil", ".ust-ic"):
        assert olu not in STIL, olu
    for korunan in (".kimlik {", ".logo-rozet {", ".sayi-rozet {", ".komut-kap { --odak: var(--serit-yazi); }"):
        assert korunan in STIL, korunan
    # Şube defteri 100rem'in altında çekmece kipinde kalır (beş günlük tablo sabit menüyle taşar).
    assert "body.kabuklu.genis-sayfa" in ortam_blogu(STIL, "@media (min-width: 100rem)")
    assert "body.kabuklu:not(.genis-sayfa)" in ortam_blogu(STIL, "@media (min-width: 64rem)")
    assert STIL.count("body.kabuklu.genis-sayfa {") == 1
    # Kip JS'te değil CSS'te durur; yapışkan içerik üst çubuğun payını belirteçten alır.
    assert "--kb-kip: cekmece" in STIL and STIL.count("--kb-kip: sabit") == 2
    assert ".firca-serit { inset-block-start: var(--yapiskan-ust); }" in STIL and "#islem .arac-cubugu" not in STIL


def test_ust_cubuk_cekmece_kipinin_her_genisliginde_yapiskan():
    # "Acil" ve "Menü" şube defterinin 64–100rem arasındaki çekmece kipinde de kaydırınca ekranda kalır: yapışkanlık
    # ve pay bir genişlik sorgusuna değil kipe bağlıdır (sabit kipte çubuk çizilmez, pay 0).
    kabuk = STIL.split("@layer kabuk {")[1]
    duz = re.sub(r"@media[^{]*\{(?:[^{}]|\{[^{}]*\})*\}", "", kabuk)  # @media blokları dışında kalan kurallar
    assert ".ust-cubuk { position: sticky; inset-block-start: 0; }" in duz
    assert ".firca-serit { inset-block-start: var(--yapiskan-ust); }" in duz
    assert "--yapiskan-ust: var(--ust-boy);" in duz and kabuk.count("--yapiskan-ust: 0px;") == 3  # iki sabit kip + baskı
    assert "html:has(body.kabuklu.genis-sayfa) { scroll-padding-block-start:" in ortam_blogu(kabuk, "@media (max-width: 99.99rem)")
    # Defterin yapışkan başlık satırı üst çubuğun altında kalmaz.
    assert ".defter-kap.sigar .defter thead th { inset-block-start: var(--yapiskan-ust); }" in kabuk
    assert "thead th { inset-block-start: calc(var(--yapiskan-ust) + 3.25rem); }" in kabuk


def test_sekme_seridi_ve_firca_seridi_dar_icerikte_sarar():
    kabuk = STIL.split("@layer kabuk {")[1]
    # Sarma eşiği içeriğin enine göre: sabit menülü sayfa 85rem, tam genişlikli şube defteri 70rem.
    assert "body:not(.genis-sayfa) .sekmeler { flex-wrap: wrap;" in ortam_blogu(kabuk, "@media (max-width: 84.99rem)")
    assert ".genis-sayfa .sekmeler { flex-wrap: wrap;" in ortam_blogu(kabuk, "@media (max-width: 69.99rem)")
    assert not re.search(r"^\s*\.sekmeler \{ flex-wrap: wrap", kabuk, re.M)
    # Telefonda fırça şeridi sayfayı (ve sabit konumlu alt çubuğu) genişletmez.
    assert "@media (max-width: 63.99rem) { .firca-serit .firca { flex-wrap: wrap; } }" in kabuk
    # Dar telefonda "Menü" yazısı gizlenir ama erişilebilir ad kalır (display: none değil).
    dar = ortam_blogu(kabuk, "@media (max-width: 27rem)")
    assert ".ust-cubuk .menu-ac span {" in dar and "clip-path: inset(50%)" in dar and "display: none" not in dar
    # Liste kayıyorsa ipucu; betikle odaklanan main halka çizmez.
    assert "--kb-ipucu" in kabuk and "no-repeat local" in kabuk
    assert ".yan-menu:focus, main:focus { outline: none; }" in kabuk


def test_stilde_yeni_belirtec_adlari_tema_adlarina_benzemez():
    # test_stil_varsayilanlari_motorla_ayni, -a / -k ile biten ya da t- ile başlayan her #renk bildirimini
    # tema.varsayilan() ile karşılaştırır; ölçek belirteçleri bu ad kalıbına girmez.
    olcek = STIL.split("4) Ölçek belirteçleri")[1].split("}")[0]
    adlar = re.findall(r"(--[a-z0-9-]+)\s*:", olcek)
    assert len(adlar) > 25
    assert not [a for a in adlar if re.fullmatch(r"--(?:[a-z0-9-]+-[ak]|t-[a-z0-9-]+)", a)]


def test_durum_yazisi_kontrasti():
    acik_yazi, koyu_yazi = re.search(r"--d-yazi:light-dark\((#[0-9a-f]{6}), (#[0-9a-f]{6})\)", STIL).groups()
    assert (acik_yazi, koyu_yazi) == ("#ffffff", "#0d1117")
    assert f"--d-yazi:{acik_yazi};" in STIL and f"--d-yazi:{koyu_yazi};" in STIL
    renkler = re.findall(r"--d-(acik|kilit|duyuru|kapali|sorun|guncel):light-dark\((#[0-9a-f]{6}), (#[0-9a-f]{6})\)", STIL)
    assert len(renkler) == 6
    for ad, acik, koyu in renkler:
        assert tema.kontrast(acik_yazi, acik) >= 4.5, ad
        assert tema.kontrast(koyu_yazi, koyu) >= 4.5, ad


def _oklab(renk: str) -> tuple[float, float, float]:
    L, C, h = tema.oklch(renk)
    return L, C * math.cos(h), C * math.sin(h)


def karistir(ust: str, zemin: str, oran: float) -> str:
    """`zemin` üstüne `oran` kadar `ust`, CSS'teki gibi OKLab'da (color-mix(in oklab, …): yarı saydam vurgunun rengi)."""
    L, a, b = (u * oran + z * (1 - oran) for u, z in zip(_oklab(ust), _oklab(zemin), strict=True))
    return tema.ton(L, math.hypot(a, b), math.atan2(b, a))


def test_karistir_oklabda_karistirir():
    assert karistir("#ffffff", "#000000", 1.0) == "#ffffff" and karistir("#ffffff", "#000000", 0.0) == "#000000"
    # OKLab'da siyah-beyazın yarısı sRGB ortalamasından (#808080) belirgin koyudur.
    assert karistir("#ffffff", "#000000", 0.5) == "#636363"


@pytest.mark.parametrize("ana, vurgu", [(None, None), ("#7a1f2b", "#0f766e"), ("#f2c200", None), ("#e8f0fb", "#ffd9a8"),
                                        ("#ffffff", None), ("#101010", "#00ff88")])  # fmt: skip
def test_menu_yazisi_kontrasti(ana, vurgu):
    uretilen = tema.uret(ana, vurgu) if ana else tema.varsayilan()
    for kip in ("acik", "koyu"):
        serit, yazi, soluk = (uretilen[kip][a] for a in ("serit", "serit-yazi", "serit-soluk"))
        assert tema.kontrast(yazi, serit) >= 7, kip
        assert tema.kontrast(yazi, karistir(yazi, serit, 0.16)) >= 4.5, kip  # etkin öğenin zemini
        assert tema.kontrast(soluk, serit) >= 4.5, kip  # küme başlığı, rol


def test_yazdirmada_kabuk_gizli():
    kabuk = STIL.split("@layer kabuk {")[1]
    baski = ortam_blogu(kabuk, "@media print")
    assert ".yan-menu, .ust-cubuk, .alt-cubuk, .perde { display: none !important; }" in baski
    assert "body.kabuklu { padding: 0; --yapiskan-ust: 0px; }" in baski and "body.kabuklu main { padding: 0; }" in baski
    # Genişlik sorguları baskıda da geçerlidir (A4 dikey ≈ 794 px): ekrana özgü kurallar "screen" ile sınırlanır.
    assert "@media screen { body.genis-sayfa { font-size: .9375rem; } }" in kabuk
    assert "@media screen and (max-width: 63.99rem), screen and (pointer: coarse)" in kabuk
    assert "@page genis { size: A4 landscape;" in STIL and "body.genis-sayfa { page: genis; }" in STIL


def test_sekilli_rozet_ve_dokunma_hedefi():
    kabuk = STIL.split("@layer kabuk {")[1]
    assert '.rozet[data-durum]:not(:has(.simge))::before { content: "";' in kabuk
    for durum in ("kilitli", "sorun", "guncelleme", "cevrimdisi", "uyari"):
        assert f'[data-durum="{durum}"]' in kabuk, durum
    # Izgara hücresi ve onu anlatan açıklama satırı aynı görünür (ikisinde de şekil yok).
    assert ":is(.yoklama-izgara, .yk-lejant) .rozet[data-durum]:not(:has(.simge))::before { content: none; }" in kabuk
    dokunma = ortam_blogu(kabuk, "@media screen and (max-width: 63.99rem), screen and (pointer: coarse)")
    assert "min-block-size: var(--dokunma);" in dokunma and ".sekmeler a" in dokunma
    assert re.search(r"--dokunma:2\.75rem; --dokunma-kucuk:2\.25rem;", STIL)


def test_daralan_icerikte_tablo_ve_sayfa_basi():
    kabuk = STIL.split("@layer kabuk {")[1]
    # Sabit menülü orta genişlikte tablo sıkılaşır; işlem düğmeleri tek satırda kalır (kap yeterince genişse).
    orta = ortam_blogu(kabuk, "@media (min-width: 64rem) and (max-width: 99.99rem)")
    assert ".tablo-kap :is(th, td) { padding-inline: .5rem; }" in orta and ".tablo-kap th[data-sirala] { padding: 0; }" in orta
    assert "@container (inline-size >= 60rem) { .tablo-kap .islemler { flex-wrap: nowrap; } }" in kabuk
    # Yana kayan tabloda kenar gölgesi yalnız ekranda (baskıda tablo kabının zemini beyaz kalır).
    ekran = ortam_blogu(kabuk.split("işlem düğmeleri tek satırda kalır")[1], "@media screen {")
    assert ekran.strip().startswith(".tablo-kap {")
    assert ekran.count("no-repeat local") == 2 and ekran.count("no-repeat scroll") == 2 and "var(--yuzey); }" in ekran
    # Dar ekranda araç çubuğu ayırıcısı çizilmez (0.17.0: pano özet çipleri kalktı, kuralları da).
    assert ".sayfa-bas > .ozet" not in STIL
    assert "@media (max-width: 84.99rem) { .arac-cubugu .ayrac { display: none; } }" in kabuk


# ---- panel.js ------------------------------------------------------------------------
def test_panel_js_kabuk_kancalari():
    for parca in ("function kabukKur", ".inert = ", '"Escape"', '"--kb-kip"', '"aria-expanded"', "  kabukKur();"):
        assert parca in BETIK, parca
    kabuk = BETIK.split("function kabukKur")[1].split("function menuKur")[0]
    # Geri tuşu sayfayı önbellekten çekmece açık getirmesin; kayan listede etkin öğe görünür alana gelsin.
    assert 'window.addEventListener("pagehide", function () { kapat(false); });' in kabuk
    assert '"pageshow"' in kabuk and "olay.persisted" in kabuk
    assert 'scrollIntoView({ block: "nearest" })' in kabuk and kabuk.count("etkiniGoster();") == 2

    assert "details.menu-grup" not in BETIK
    # Kip yalnız CSS'tedir: JS'te genişlik eşiği, dış adres, kalıcı depo yok.
    for yasak in ("matchMedia", "localStorage", "http", "innerWidth", "form.id"):
        assert yasak not in kabuk, yasak


def test_eski_kabuk_artigi_metin_yok(uygulama, panel, tahta):
    kur_ve_gir(panel)
    kimlik = tahta_ekle(panel, tahta, "T-1")["X-Tahta-Id"]
    assert 'class="kirinti" aria-label="Konum"><a href="/tahtalar">Tahtalar</a>' in panel.get(f"/tahta/{kimlik}").text
    assert "<title>Bugün · Tahta Kontrol</title>" in panel.get("/").text
    assert "<title>Tahtalar · Tahta Kontrol</title>" in panel.get("/tahtalar").text
    ayarlar = panel.get("/ayarlar/okul").text
    assert "üst şeritte" not in ayarlar and "Ana renk panelin menüsünde" in ayarlar
    assert sorgu("SELECT count(*) AS n FROM tahta")[0]["n"] == 1
