"""Bölüm sekme şeritleri (0.19.0): tek tanım (bolum_serit.py), rol süzme, her sayfada doğru etkin sekme ve menü öğesi.

Şerit YALNIZ görünümdür; uçların yetki denetimi kendi testlerindedir. Bütün veriler uydurmadır.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from test_yoklama import hazir, ogrenci_id  # noqa: F401 (fikstür)
from yardimci import PAROLA, gir, kullanici_ekle, sorgu

from tahta_sunucu import bolum_serit, vt, web

STIL = Path(__file__).parent.parent / "tahta_sunucu" / "statik" / "stil.css"
ETIKET = {ad: tanim["etiket"] for ad, tanim in bolum_serit.SERITLER.items()}
MENU_OGESI = {"yoklama": "/yoklama", "kisiler": "/ogrenciler", "program": "/program", "duyurular": "/duyurular",
              "tahtalar": "/tahtalar"}  # fmt: skip
YONETICI_YOLLARI = ("/ogretmen-programi", "/program/aktar", "/program/gecmis", "sekme=sablonlar")


def serit(sayfa: str, ad: str) -> str:
    assert sayfa.count(f'aria-label="{ETIKET[ad]}"') == 1, ad
    return sayfa.split(f'aria-label="{ETIKET[ad]}"', 1)[1].split("</nav>", 1)[0]


def yan_menu(sayfa: str) -> str:
    return sayfa.split('id="menu"')[1].split("</aside>")[0]


@pytest.fixture()
def dolu(hazir, panel):  # noqa: F811
    """Yoklama fikstürünün üstüne bir duyuru planı ve bitmiş bir acil yayını: her şerit sayfası açılabilsin."""
    yanit = panel.post("/duyurular", data={"metin": "Plan", "sure_dk": "5", "kime": "tumu", "zaman": "bir_kez",
                                           "bir_tarih": "2026-11-17", "bir_saat": "10:00"})  # fmt: skip
    assert yanit.status_code == 303 and "t=hata" not in yanit.headers["location"]
    panel.post("/acil/baslat", data={"tur": "tatbikat", "sablon": "tahliye", "baslik": "TATBİKAT", "metin": "Deneme.",
                                     "sure_dk": "30", "onay": "1", "parola": PAROLA})  # fmt: skip
    acil = sorgu("SELECT id FROM acil_yayin")[0]["id"]
    panel.post(f"/acil/{acil}/bitir", data={})
    assert sorgu("SELECT bitis FROM acil_yayin")[0]["bitis"]
    return {"plan": sorgu("SELECT id FROM duyuru_plani")[0]["id"], "acil": acil, "ogrenci": ogrenci_id("1047")}


def sayfalar(d: dict) -> list[tuple[str, str, str]]:
    """(adres, şerit, beklenen etkin sekme adresi)."""
    return [
        ("/yoklama", "yoklama", "/yoklama"),
        ("/yoklama/sube", "yoklama", "/yoklama/sube"),
        ("/yoklama/son-gunler", "yoklama", "/yoklama/sube"),
        (f"/yoklama/ogrenci/{d['ogrenci']}", "yoklama", "/yoklama/sube"),
        ("/yoklama/mazeret", "yoklama", "/yoklama/mazeret"),
        ("/yoklama/gir", "yoklama", "/yoklama/gir"),
        ("/yoklama/icmal", "yoklama", "/yoklama/icmal"),
        ("/ogrenciler", "kisiler", "/ogrenciler"),
        ("/ogretmenler", "kisiler", "/ogretmenler"),
        ("/usb-anahtarlar", "kisiler", "/usb-anahtarlar"),
        ("/program", "program", "/program?bolum=zil"),
        ("/program?bolum=zil", "program", "/program?bolum=zil"),
        ("/program?bolum=derslik", "program", "/program?bolum=derslik"),
        ("/program?bolum=kurallar", "program", "/program?bolum=kurallar"),
        ("/program?bolum=istisnalar", "program", "/program?bolum=istisnalar"),
        ("/program/uyarilar", "program", "/program/uyarilar"),
        ("/program/gun", "program", "/program/gun"),
        ("/program/aktar", "program", "/program/aktar"),
        ("/program/gecmis", "program", "/program/gecmis"),
        ("/ogretmen-programi", "program", "/ogretmen-programi"),
        ("/duyurular", "duyurular", "/duyurular"),
        ("/duyurular/yeni", "duyurular", "/duyurular/yeni"),
        (f"/duyurular/plan/{d['plan']}", "duyurular", "/duyurular"),
        ("/acil", "acil", "/acil"),
        ("/acil?sekme=gecmis", "acil", "/acil?sekme=gecmis"),
        ("/acil?sekme=sablonlar", "acil", "/acil?sekme=sablonlar"),
        ("/acil?sekme=bilinmeyen", "acil", "/acil"),
        (f"/acil/{d['acil']}", "acil", "/acil?sekme=gecmis"),
    ]


# ---- saf veri ---------------------------------------------------------------------------------------------------------
def test_her_sekme_yolu_var_olan_get_adresidir(uygulama):
    rotalar = {r.path for r in uygulama.routes if "GET" in getattr(r, "methods", ())}
    for ad, tanim in bolum_serit.SERITLER.items():
        for kume in tanim["kumeler"]:
            for sekme in kume:
                yol = sekme["yol"].split("?", 1)[0]
                assert yol in rotalar or (sekme.get("dis") and yol.startswith("/ayarlar/")), (ad, sekme["yol"])


def test_serit_gorunumu_rol_suzer_ve_tek_etkin():
    for ad, tanim in bolum_serit.SERITLER.items():
        hepsi = [s for kume in tanim["kumeler"] for s in kume]
        for rol in ("yonetici", "idareci"):
            for sekme in hepsi:
                g = bolum_serit.gorunum(ad, rol, sekme["anahtar"])
                duz = [s for kume in g["kumeler"] for s in kume]
                assert sum(1 for s in duz if s["etkin"]) == 1, (ad, rol, sekme["anahtar"])
                assert all(kume for kume in g["kumeler"]), (ad, rol)  # boş küme düşer (ayraç tek başına kalmaz)
                assert not any(s["etkin"] and s["dis"] for s in duz)
                if rol == "idareci":
                    yonetici = {s["anahtar"] for s in hepsi if s.get("rol") == "yonetici"}
                    assert not yonetici & {s["anahtar"] for s in duz}, (ad, sekme["anahtar"])
    assert len(bolum_serit.gorunum("program", "yonetici", "zil")["kumeler"]) == 3
    assert len(bolum_serit.gorunum("program", "idareci", "zil")["kumeler"]) == 2
    for ad in ("yoklama", "acil", "tahtalar"):
        assert len(bolum_serit.gorunum(ad, "idareci", None)["kumeler"]) == 1, ad
    # Rozet sayısı: yalnız sayısı olan sekmede; bozuk değer 0.
    g = bolum_serit.gorunum("program", "idareci", "uyarilar", {"uyari": 3})
    assert [s["sayi"] for kume in g["kumeler"] for s in kume if s["anahtar"] == "uyarilar"] == [3]
    g = bolum_serit.gorunum("program", "idareci", "uyarilar", {"uyari": "x"})
    assert sum(s["sayi"] for kume in g["kumeler"] for s in kume) == 0


@pytest.mark.parametrize("ad, anahtar", [("program", "ogretmen_program"), ("program", "aktar"), ("program", "gecmis"),
                                         ("acil", "sablonlar"), ("yoklama", "ayarlar"), ("yoklama", "yok-boyle")])  # fmt: skip
def test_gizli_ya_da_bilinmeyen_anahtar_ilk_sekmeyi_secer(ad, anahtar):
    g = bolum_serit.gorunum(ad, "idareci", anahtar)
    duz = [s for kume in g["kumeler"] for s in kume]
    assert duz[0]["etkin"] and sum(1 for s in duz if s["etkin"]) == 1


def test_serit_sayfalari_menude_esler_ile_kapsanir():
    """Şeridi çizen her sayfa menüde o bölümün `esler`'indedir (elle yazılan iki liste birbirinden kaymasın)."""
    ogeler = {o["yol"]: o for k in web.MENU for o in k["ogeler"]}
    ogeler[web.MENU_ACIL["yol"]] = web.MENU_ACIL
    for ad, menu_yolu in {**MENU_OGESI, "acil": "/acil"}.items():
        esler = ogeler[menu_yolu]["esler"]
        for yol in bolum_serit.sayfa_onekleri(ad):
            assert any(yol == e or yol.startswith(e + "/") for e in esler), (ad, yol)
    # Bir sayfa iki bölümün şeridinde olamaz (öğretmen programı yalnız Program'da).
    gorulen: dict[str, str] = {}
    for ad in bolum_serit.SERITLER:
        for yol in bolum_serit.sayfa_onekleri(ad):
            assert gorulen.setdefault(yol, ad) == ad, yol
    assert gorulen["/ogretmen-programi"] == "program"


# ---- üretilen sayfa ---------------------------------------------------------------------------------------------------
def test_her_serit_sayfasinda_etkin_sekme_ve_menu_dogru(panel, dolu):
    for yol, ad, etkin in sayfalar(dolu):
        yanit = panel.get(yol)
        assert yanit.status_code == 200, yol
        s = serit(yanit.text, ad)
        assert re.findall(r'<a href="([^"]+)" aria-current="page">', s) == [etkin], yol
        assert s.count("aria-current") == 1, yol
        for baska in ETIKET:  # sayfada yalnız kendi bölüm şeridi
            if baska != ad:
                assert f'aria-label="{ETIKET[baska]}"' not in yanit.text, (yol, baska)
        menu = yan_menu(yanit.text)
        assert menu.count('aria-current="page"') == 1, yol
        if ad == "acil":
            assert 'class="acil-dugme" href="/acil" aria-current="page"' in menu, yol
        else:
            assert f'<a href="{MENU_OGESI[ad]}" aria-current="page">' in menu, yol
        # Öğretmen programı yalnız Program şeridindedir.
        assert s.count('href="/ogretmen-programi"') == (1 if ad == "program" else 0), yol


def test_serit_icerigi_ve_sirasi(panel, dolu):
    def yollar(yol, ad):
        return re.findall(r'<a href="([^"]+)"', serit(panel.get(yol).text, ad))

    assert yollar("/yoklama", "yoklama") == ["/yoklama", "/yoklama/sube", "/yoklama/mazeret", "/yoklama/gir",
                                             "/yoklama/icmal", "/ayarlar/yoklama"]  # fmt: skip
    assert yollar("/ogrenciler", "kisiler") == ["/ogrenciler", "/ogretmenler", "/usb-anahtarlar"]
    assert yollar("/program", "program") == [
        "/program/gun", "/program?bolum=zil", "/program?bolum=derslik", "/ogretmen-programi", "/program?bolum=kurallar",
        "/program?bolum=istisnalar", "/program/uyarilar", "/program/aktar", "/program/gecmis"]  # fmt: skip
    assert yollar("/duyurular", "duyurular") == ["/duyurular", "/duyurular/yeni"]
    assert yollar("/acil", "acil") == ["/acil", "/acil?sekme=gecmis", "/acil?sekme=sablonlar"]
    assert serit(panel.get("/program").text, "program").count("sekme-ayrac") == 2
    assert serit(panel.get("/duyurular").text, "duyurular").count("sekme-ayrac") == 0


def test_yoklama_ayarlari_sekmesi_dis_baglantidir(panel, dolu):
    for yol in ("/yoklama", "/yoklama/sube", "/yoklama/icmal"):
        s = serit(panel.get(yol).text, "yoklama")
        assert s.index("sekme-ayrac") < s.index('href="/ayarlar/yoklama"'), yol
        dis = s.split('<a href="/ayarlar/yoklama"', 1)[1].split("</a>", 1)[0]
        assert "aria-current" not in dis and "(Ayarlar bölümüne gider)" in dis and "Yoklama ayarları" in dis, yol


def test_idareci_htmlinde_yonetici_sekmesi_yok(panel, dolu):
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    gezilen = 0
    for yol, ad, etkin in sayfalar(dolu):
        yanit = panel.get(yol)
        if any(y in yol for y in YONETICI_YOLLARI):
            assert yanit.status_code == 303, yol  # uç yetki denetimi aynen (şerit yalnız görünüm)
            continue
        assert yanit.status_code == 200, yol
        gezilen += 1
        for parca in (*YONETICI_YOLLARI, "Önceki programlar", "Yoklama ayarları"):
            assert parca not in yanit.text, (yol, parca)
        s = serit(yanit.text, ad)
        assert "/ayarlar/" not in s, yol
        assert s.count("sekme-ayrac") == (1 if ad == "program" else 0), yol
        assert re.findall(r'<a href="([^"]+)" aria-current="page">', s) == [etkin], yol
    assert gezilen == len(sayfalar(dolu)) - 4  # üç yönetici sayfası + şablonlar sekmesi
    # 0.20.0: genel arama yönetici sekmesinin adını da adresini de idareciye göstermez.
    for yol in ("/ara", "/ara?q=program", "/ara?q=ayar", "/ara?q=grup", "/ara?q=yedek", "/ara?q=tahta", "/ara?q=aktar", "/ara?q=şablon"):
        yanit = panel.get(yol)
        assert yanit.status_code == 200, yol
        for parca in (*YONETICI_YOLLARI, "Önceki programlar", "Yoklama ayarları", "/ayarlar", "/yedekler", "/gruplar", "Şablonlar"):
            assert parca not in yanit.text, (yol, parca)


def test_kisiler_sayfalari_yoklama_seridini_cizmez_kvkk_bandi_durur(panel, dolu):
    for yol in ("/ogrenciler", "/ogretmenler", "/usb-anahtarlar"):
        sayfa = panel.get(yol).text
        assert "Yoklama bölümleri" not in sayfa and 'aria-label="Kişiler ve anahtarlar bölümü"' in sayfa, yol
    assert "kvkk-bant" in panel.get("/ogrenciler").text  # öğrenci adı gösteren sayfanın notu taşınırken düşmedi
    assert "kvkk-bant" in panel.get("/yoklama").text  # Yoklama sayfalarının notu da yerinde


def test_gizlilik_basliklari_korunur(panel, dolu):
    """Taşınan ve kişi verisi gösteren sayfalar önbelleğe alınmaz (kural 19, 29, 31, 35)."""
    for yol in ("/ogretmenler", "/ogrenciler", "/usb-anahtarlar", "/yoklama", "/yoklama/sube", "/yoklama/son-gunler",
                "/yoklama/mazeret", "/yoklama/gir", "/yoklama/icmal", f"/yoklama/ogrenci/{dolu['ogrenci']}",
                "/ogretmen-programi"):  # fmt: skip
        yanit = panel.get(yol)
        assert yanit.status_code == 200 and "no-store" in yanit.headers.get("cache-control", ""), yol


def test_program_durdur_donusu_sekmeye_gore(panel, dolu):
    from test_program_panel import ELLE
    from yardimci import ileti, zil_elle

    assert zil_elle(ELLE) == "Zil saatleri kaydedildi."
    form = {"pk_gecikme_dk": "2", "pk_bos_saatte": "1", "bd_esik_dk": "10", "pk_etkin": "1"}
    assert ileti(panel.post("/program/kurallar", data=form)) == "Kurallar kaydedildi."
    beklenen = {
        "/program": "/program?bolum=zil", "/program?bolum=derslik": "/program?bolum=derslik",
        "/program?bolum=kurallar": "/program?bolum=kurallar", "/program?bolum=istisnalar": "/program?bolum=istisnalar",
        "/program/uyarilar": "/program/uyarilar", "/program/gun": "/program/gun", "/program/aktar": "/program/aktar",
        "/program/gecmis": "/program/gecmis", "/ogretmen-programi": "/ogretmen-programi",
    }  # fmt: skip
    for yol, donus in beklenen.items():
        sayfa = panel.get(yol).text
        bant = sayfa.split('id="program-serit"', 1)[1].split("</section>", 1)[0]
        assert 'action="/program/istisna"' in bant and f'name="donus" value="{donus}"' in bant, yol
    yanit = panel.post("/program/istisna", data={"sure": "1sa", "donus": "/ogretmen-programi"})
    assert yanit.status_code == 303 and yanit.headers["location"].startswith("/ogretmen-programi")


def test_program_uyari_sayisi_her_program_sayfasinda_ayni(panel, dolu):
    tahta_id = sorgu("SELECT id FROM tahta")[0]["id"]
    simdi = vt.simdi()
    with vt.islem() as b:
        b.execute(
            "INSERT INTO bos_ders_uyari (tahta_id, tarih, devre, ders_no, ders_bas, neden, olusturma) VALUES (?, ?, 'normal', 1, ?, 'kapali', ?)",
            (tahta_id, "2026-11-16", simdi - 600, simdi),
        )
    rozetler = set()
    for yol in ("/program", "/program?bolum=derslik", "/program?bolum=kurallar", "/program?bolum=istisnalar",
                "/program/uyarilar", "/program/gun", "/program/aktar", "/program/gecmis", "/ogretmen-programi"):  # fmt: skip
        s = serit(panel.get(yol).text, "program")
        uyari = s.split('href="/program/uyarilar"', 1)[1].split("</a>", 1)[0]
        rozetler.add(re.search(r'<span class="sayi-rozet">(\d+)</span><span class="gizli"> boş ders uyarısı</span>', uyari).group(1))
    assert len(rozetler) == 1


# ---- stil -------------------------------------------------------------------------------------------------------------
def test_bolum_seridi_stili_sarar_dar_ekranda_kume_satir_basi():
    css = STIL.read_text(encoding="utf-8")
    assert ".bolum-serit { flex-wrap: wrap; overflow-x: visible;" in css
    kural = css.split(".bolum-serit {", 1)[1].split("}", 1)[0]
    assert "sticky" not in kural
    # Dar ekranda ayraç satır başıdır (satır sonunda tek başına çizgi kalmaz); kural kabuk katmanındadır.
    kabuk = css.split("@layer kabuk {", 1)[1]
    assert ".bolum-serit .sekme-ayrac { flex: 0 0 100%;" in kabuk
    dar = kabuk.split(".bolum-serit .sekme-ayrac { flex: 0 0 100%;", 1)[0].rsplit("@media", 1)[1]
    assert dar.strip().startswith("(max-width: 39.99rem)")
    # Küme geniş ekranda birlikte sarar; dar/orta ekranda yalnız sarmalayıcıdır. Ayraç kümenin ilk çocuğudur.
    assert ".bolum-serit .sekme-kume { display: contents; }" in kabuk
    assert ".bolum-serit .sekme-kume { display: flex;" in kabuk and "overflow-x: clip" in kabuk


def test_serit_kumeleri_sarmalayicida_ayrac_kumenin_basinda(panel, dolu):
    s = serit(panel.get("/program").text, "program")
    kumeler = s.split('<span class="sekme-kume">')[1:]
    assert [len(re.findall(r"<a href=", k)) for k in kumeler] == [4, 3, 2]
    assert ["sekme-ayrac" in k.split("<a ", 1)[0] for k in kumeler] == [False, True, True]
