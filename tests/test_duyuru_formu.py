"""Duyuru formu (0.19.0): tek sayfa, Ne · Kime · Ne zaman. Tamamı JS'siz: yalnız formun ÇİZDİĞİ alanlar gönderilir.

Formun gönderdiği alan kümesi sayfanın HTML'inden, tarayıcının yapacağı gibi çıkarılır (işaretsiz kutu ve radyo
gönderilmez; kapalı <details> ve JS'siz görünen bütün koşullu alanlar gönderilir). Böylece şablon değişirse yanlış
hedefe ya da yanlış zamanda yayın bu testlerde görünür.
"""

from __future__ import annotations

import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

import pytest
from yardimci import TZ, an, bekle, gir, ileti, kimlik, kullanici_ekle, kur_ve_gir, sorgu, tahta_ekle

ALANLAR = {
    "baslik", "metin", "sure_dk", "kapatilabilir", "kime", "bina", "kat", "duzey", "devre", "grup", "hedef_tahta",
    "zaman", "bir_tarih", "bir_saat", "siklik", "hafta_sonu", "gun", "tekrar_saat", "baslangic", "bitis",
}  # fmt: skip
KVKK = "Tahta bütün sınıfa açık ekrandır. Öğrenci adı, numarası ya da kişisel bilgi yazmayın."
YETENEK = {"kilitli": False, "yetenekler": ["acil", "duyuru_id"]}


class Form(HTMLParser):
    """`id="duyuru-formu"` formunun alanları: adlar, tarayıcının göndereceği (ad, değer) çiftleri, iç içe form."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.formlar = 0  # duyuru-formu sayısı
        self.ic_ice = 0
        self.icinde = False
        self.adlar: list[str] = []
        self.ciftler: list[tuple[str, str]] = []
        self.isaretli: dict[str, list[str]] = {}
        self.dugmeler: list[dict] = []
        self.eylem = ""
        self._metin_alani: str | None = None
        self._metin: list[str] = []
        self._devre_disi = 0
        self.details: list[dict] = []  # form içindeki <details> öznitelikleri
        self.metin: list[str] = []  # form içindeki düz metin (not cümleleri için)

    def handle_starttag(self, etiket, oz):
        oz = dict(oz)
        if etiket == "form":
            if self.icinde:
                self.ic_ice += 1
            elif oz.get("id") == "duyuru-formu":
                self.formlar += 1
                self.icinde = True
                self.eylem = oz.get("action", "")
            return
        if not self.icinde:
            return
        if etiket == "fieldset" and "disabled" in oz:
            self._devre_disi += 1
        if etiket == "details":
            self.details.append(oz)
        ad = oz.get("name")
        if etiket == "button":
            self.dugmeler.append(oz)
        if not ad or etiket not in ("input", "textarea", "select"):
            return
        self.adlar.append(ad)
        if etiket == "textarea":
            self._metin_alani, self._metin = ad, []
            return
        tur = oz.get("type", "text")
        if tur in ("checkbox", "radio"):
            if "checked" in oz:
                self.isaretli.setdefault(ad, []).append(oz.get("value", "on"))
                if not self._devre_disi and "disabled" not in oz:
                    self.ciftler.append((ad, oz.get("value", "on")))
        elif not self._devre_disi and "disabled" not in oz:
            self.ciftler.append((ad, oz.get("value", "")))

    def handle_data(self, veri):
        if self._metin_alani is not None:
            self._metin.append(veri)
        elif self.icinde:
            self.metin.append(veri)

    def handle_endtag(self, etiket):
        if etiket == "textarea" and self._metin_alani is not None:
            if not self._devre_disi:
                self.ciftler.append((self._metin_alani, "".join(self._metin)))
            self._metin_alani = None
        elif etiket == "form" and self.icinde:
            self.icinde = False

    def deger(self, ad: str) -> list[str]:
        return [d for a, d in self.ciftler if a == ad]


def html_metni(parca: str) -> str:
    import html as html_

    return html_.unescape(re.sub(r"<[^>]+>", "", parca.split(">", 1)[1] if ">" in parca else parca)).strip()


def form_oku(sayfa: str) -> Form:
    f = Form()
    f.feed(sayfa)
    return f


def gonderim(sayfa: str, **degisen) -> list[tuple[str, str]]:
    """JS'siz tarayıcının göndereceği alanlar; `degisen` alanları kullanıcının değiştirdiği gibi ezer.

    Değer liste ise o adla birden çok kutu işaretlenir; None ise alan hiç gönderilmez (işareti kaldırılmış kutu).
    Ezilen ad formda YOKSA hata verir (test formun çizmediği alanı gönderemez).
    """
    f = form_oku(sayfa)
    assert f.formlar == 1
    ciftler = list(f.ciftler)
    for ad, deger in degisen.items():
        assert ad in f.adlar, f"formda '{ad}' alanı yok"
        ciftler = [(a, d) for a, d in ciftler if a != ad]
        if deger is None:
            continue
        for d in deger if isinstance(deger, list) else [deger]:
            ciftler.append((ad, str(d)))
    return ciftler


def gonder(panel, sayfa: str, adres: str = "/duyurular", **degisen):
    from urllib.parse import urlencode

    return panel.post(adres, content=urlencode(gonderim(sayfa, **degisen)),
                      headers={"content-type": "application/x-www-form-urlencoded"})  # fmt: skip


def serit(sayfa: str) -> str:
    return sayfa.split('aria-label="Duyurular bölümü"', 1)[1].split("</nav>", 1)[0]


@pytest.fixture()
def okul(panel, tahta):
    """İki onaylı tahta (bina, kat, düzey, devre dolu) ve bir grup: her ölçütten en az bir seçenek çizilir."""
    kur_ve_gir(panel)
    t1 = tahta_ekle(panel, tahta, "9-A", durum=YETENEK, bina="A Blok", kat="1", duzey="9", devre="sabah")
    t2 = tahta_ekle(panel, tahta, "10-A", durum=YETENEK, bina="B Blok", kat="2", duzey="10", devre="ogle")
    panel.post("/gruplar", data={"eylem": "ekle", "ad": "Dokuzlar", "aciklama": ""})
    grup = sorgu("SELECT id FROM tahta_grubu")[0]["id"]
    panel.post("/gruplar", data={"eylem": "uyeler", "id": str(grup), "tahta": [str(kimlik(t1))]})
    assert sorgu("SELECT COUNT(*) AS n FROM tahta_grubu_uye")[0]["n"] == 1
    return {"t1": t1, "t2": t2, "grup": grup}


def yeni(panel, sorgu_metni: str = "") -> str:
    yanit = panel.get("/duyurular/yeni" + sorgu_metni)
    assert yanit.status_code == 200
    return yanit.text


def plan_olustur(panel, **degisen) -> int:
    yanit = gonder(panel, yeni(panel), **degisen)
    assert yanit.status_code == 303 and "t=hata" not in yanit.headers["location"], ileti(yanit)
    return sorgu("SELECT MAX(id) AS id FROM duyuru_plani")[0]["id"]


def komutlar():
    return sorgu("SELECT * FROM komut WHERE tur = 'duyuru' ORDER BY id")


# ---- 16–19: biçim sözleşmesi -----------------------------------------------------------------------------------------
def test_form_tek_form_ve_alan_adlari_sozlesme(okul, panel):
    f = form_oku(yeni(panel))
    assert f.formlar == 1 and f.ic_ice == 0 and f.eylem == "/duyurular"
    assert set(f.adlar) == ALANLAR
    plan_id = plan_olustur(panel, metin="Plan", zaman="bir_kez", bir_tarih="2026-11-17", bir_saat="10:00")
    p = form_oku(panel.get(f"/duyurular/plan/{plan_id}").text)
    assert p.formlar == 1 and p.ic_ice == 0 and p.eylem == f"/duyurular/plan/{plan_id}"
    assert set(p.adlar) == ALANLAR | {"eylem"} and p.deger("eylem") == ["kaydet"]


def test_bolum_sirasi_ne_kime_ne_zaman(okul, panel):
    sayfa = yeni(panel)
    sira = [sayfa.index(f'name="{ad}"') for ad in ("baslik", "metin", "sure_dk", "kapatilabilir", "kime", "zaman")]
    assert sira == sorted(sira)
    # Bütün hedef alanları "kime" ile "zaman" arasındadır; bütün zaman alanları "zaman"dan sonra.
    kime, zaman = sayfa.index('name="kime"'), sayfa.index('name="zaman"')
    for ad in ("bina", "kat", "duzey", "devre", "grup", "hedef_tahta"):
        assert kime < sayfa.index(f'name="{ad}"') < zaman, ad
    for ad in ("bir_tarih", "bir_saat", "siklik", "hafta_sonu", "gun", "tekrar_saat", "baslangic", "bitis"):
        assert sayfa.index(f'name="{ad}"') > zaman, ad
    basliklar = re.findall(r"<h2[^>]*>([^<]+)</h2>", sayfa.split('id="duyuru-formu"', 1)[1])
    assert basliklar[:3] == ["1. Ne yazılsın?", "2. Kime?", "3. Ne zaman?"]


def test_varsayilanlar_birebir(okul, panel):
    f = form_oku(yeni(panel))
    assert f.isaretli["kime"] == ["tumu"] and f.isaretli["zaman"] == ["hemen"]
    assert f.deger("sure_dk") == ["5"] and f.isaretli["kapatilabilir"] == ["1"]
    assert f.isaretli["siklik"] == ["gunluk"] and f.isaretli["gun"] == ["0", "1", "2", "3", "4"]
    assert "hafta_sonu" not in f.isaretli
    # "Başlangıç"ın varsayılanı sunucunun bugünüdür (panel_duyuru._bugun: gerçek saat; test saati değil).
    assert f.deger("baslangic") == [datetime.now(TZ).date().isoformat()] and f.deger("bitis") == [""]
    assert f.deger("bir_tarih") == [""] and f.deger("bir_saat") == [""] and f.deger("tekrar_saat") == [""]
    for ad in ("bina", "kat", "duzey", "devre", "grup", "hedef_tahta"):
        assert ad not in f.isaretli, ad
    # Plan sayfasında da zaman radyolarından tam biri işaretlidir ("Hemen" çizilmez).
    plan_id = plan_olustur(panel, metin="Plan", zaman="tekrarli", tekrar_saat="09:30", baslangic="2026-11-16",
                           bitis="2026-12-18")  # fmt: skip
    plan_sayfasi = panel.get(f"/duyurular/plan/{plan_id}").text
    assert form_oku(plan_sayfasi).isaretli["zaman"] == ["tekrarli"]
    assert 'name="zaman" value="hemen"' not in plan_sayfasi
    kopya = form_oku(yeni(panel, f"?kopya={plan_id}"))
    assert kopya.isaretli["zaman"] == ["tekrarli"]


def test_kvkk_notu_ve_kapatilabilir_formda(okul, panel):
    plan_id = plan_olustur(panel, metin="Plan", zaman="bir_kez", bir_tarih="2026-11-17", bir_saat="10:00")
    for sayfa in (yeni(panel), panel.get(f"/duyurular/plan/{plan_id}").text):
        f = form_oku(sayfa)
        govde = re.sub(r"\s+", " ", "".join(f.metin))
        assert KVKK in govde and "Öğretmen tahtadan kapatabilsin" in govde
        assert "kapatilabilir" in f.adlar


# ---- 20–24: JS'siz uçtan uca -----------------------------------------------------------------------------------------
def test_js_siz_hemen_uctan_uca(okul, panel, tahta):
    yanit = gonder(panel, yeni(panel), metin="Tören 10.00'da bahçede.")
    assert yanit.status_code == 303 and yanit.headers["location"].startswith("/duyurular?")
    assert ileti(yanit) == "Duyuru 2 tahtaya gönderildi."
    yayin = sorgu("SELECT * FROM duyuru")
    assert len(yayin) == 1 and (yayin[0]["durum"], yayin[0]["tahta_sayisi"]) == ("gonderildi", 2)
    assert sorgu("SELECT COUNT(*) AS n FROM duyuru_plani")[0]["n"] == 0
    assert {k["tahta_id"] for k in komutlar()} == {kimlik(okul["t1"]), kimlik(okul["t2"])}
    komut = bekle(tahta, okul["t1"])["komutlar"][0]
    assert komut["tur"] == "duyuru" and komut["veri"]["metin"] == "Tören 10.00'da bahçede."
    assert komut["veri"]["kapatilabilir"] is True and komut["veri"]["sure_sn"] == 300
    # İşareti kaldırılmış kutu gönderilmez: tahtadan kapatılamaz.
    gonder(panel, yeni(panel), metin="Kapatılamaz", kapatilabilir=None)
    komut = bekle(tahta, okul["t1"])["komutlar"][0]
    assert komut["veri"]["metin"] == "Kapatılamaz" and komut["veri"]["kapatilabilir"] is False


def test_js_siz_bir_kez_uctan_uca(okul, panel, saat):
    # JS'siz tarayıcı tekrarlı alanlarını da varsayılan değerleriyle gönderir; plan yine "tek"tir.
    yanit = gonder(panel, yeni(panel), metin="Veli toplantısı", zaman="bir_kez", bir_tarih="2026-11-16", bir_saat="10:00")
    assert yanit.status_code == 303 and yanit.headers["location"].startswith("/duyurular?"), ileti(yanit)
    plan = sorgu("SELECT * FROM duyuru_plani")
    assert len(plan) == 1 and plan[0]["tekrar"] == "tek" and plan[0]["durum"] == "etkin"
    assert (plan[0]["baslangic"], plan[0]["saat"]) == ("2026-11-16", "10:00")
    assert sorgu("SELECT COUNT(*) AS n FROM duyuru")[0]["n"] == 0 and komutlar() == []
    # Zamanlayıcı o anda bir kez yayımlar; öncesinde ve sonrasında yayımlamaz.
    zamanlayici = panel.app.state.duyuru_zamanlayici
    saat.ayarla(an(16, 9, 59))
    zamanlayici(an(16, 9, 59))
    assert komutlar() == []
    saat.ayarla(an(16, 10, 0, 5))
    zamanlayici(an(16, 10, 0, 5))
    assert len(sorgu("SELECT * FROM duyuru WHERE durum = 'gonderildi'")) == 1 and len(komutlar()) == 2
    saat.ayarla(an(17, 10, 0, 5))
    zamanlayici(an(17, 10, 0, 5))
    assert len(sorgu("SELECT * FROM duyuru")) == 1


def test_js_siz_tekrarli_gunluk_ve_haftalik_uctan_uca(okul, panel):
    # Başlangıç açıkça verilir: formun varsayılanı gerçek bugündür, test saati ise 16.11.2026'dır.
    gunluk = plan_olustur(panel, metin="Günlük", zaman="tekrarli", tekrar_saat="08:20", baslangic="2026-11-16",
                          bitis="2026-12-18")  # fmt: skip
    hafta_sonu = plan_olustur(panel, metin="Her gün", zaman="tekrarli", tekrar_saat="08:25", hafta_sonu="1",
                              baslangic="2026-11-16", bitis="2026-11-30")  # fmt: skip
    haftalik = plan_olustur(panel, metin="Haftalık", zaman="tekrarli", siklik="haftalik", gun=["1", "3"],
                            tekrar_saat="12:20", baslangic="2026-11-17", bitis="2026-12-01")  # fmt: skip
    # Bitiş boşsa plan kaydedilmez (var olan doğrulama): JS'siz kullanıcı da aynı iletiyi görür.
    eksik = gonder(panel, yeni(panel), metin="Bitişsiz", zaman="tekrarli", tekrar_saat="08:30")
    assert eksik.status_code == 400 and ileti(eksik) == "Bitiş tarihini seçin."
    p = {s["id"]: s for s in sorgu("SELECT * FROM duyuru_plani")}
    assert (p[gunluk]["tekrar"], p[gunluk]["saat"], p[gunluk]["baslangic"], p[gunluk]["bitis"]) == (
        "gunluk", "08:20", "2026-11-16", "2026-12-18")  # fmt: skip
    assert p[gunluk]["gunler"] == "0,1,2,3,4"  # hafta sonu kutusu işaretsiz: yalnız hafta içi
    assert (p[hafta_sonu]["tekrar"], p[hafta_sonu]["gunler"]) == ("gunluk", "0,1,2,3,4,5,6")
    assert (p[haftalik]["tekrar"], p[haftalik]["gunler"], p[haftalik]["saat"], p[haftalik]["baslangic"],
            p[haftalik]["bitis"]) == ("haftalik", "1,3", "12:20", "2026-11-17", "2026-12-01")  # fmt: skip
    assert len(p) == 3
    assert sorgu("SELECT COUNT(*) AS n FROM duyuru")[0]["n"] == 0 and komutlar() == []


def test_secili_olmayan_zamanin_alanlari_yok_sayilir(okul, panel):
    yanit = gonder(panel, yeni(panel), metin="Şimdi", bir_tarih="2026-11-20", bir_saat="10:00", tekrar_saat="09:00",
                   siklik="haftalik", gun=["2"])  # fmt: skip
    assert ileti(yanit) == "Duyuru 2 tahtaya gönderildi."
    assert sorgu("SELECT COUNT(*) AS n FROM duyuru_plani")[0]["n"] == 0 and len(komutlar()) == 2
    plan_id = plan_olustur(panel, metin="Bir kez", zaman="bir_kez", bir_tarih="2026-11-20", bir_saat="10:00",
                           tekrar_saat="09:00", siklik="haftalik", gun=["2"], hafta_sonu="1")  # fmt: skip
    plan = sorgu("SELECT * FROM duyuru_plani WHERE id = ?", plan_id)[0]
    assert (plan["tekrar"], plan["baslangic"], plan["saat"]) == ("tek", "2026-11-20", "10:00")
    assert len(komutlar()) == 2  # plan yayın üretmedi


def test_secime_gore_bos_hedef_reddedilir_tumu_olcutleri_yok_sayar(okul, panel):
    yanit = gonder(panel, yeni(panel), metin="Kime?", kime="secim")
    assert yanit.status_code == 400 and ileti(yanit) == "Duyurunun hangi tahtalara gideceğini seçin."
    assert komutlar() == [] and sorgu("SELECT COUNT(*) AS n FROM duyuru")[0]["n"] == 0
    # "Tüm tahtalar" seçiliyken işaretli kalan ölçütler yok sayılır: bütün onaylı tahtalar.
    yanit = gonder(panel, yeni(panel), metin="Herkese", hedef_tahta=[str(kimlik(okul["t1"]))], bina=["B Blok"])
    assert ileti(yanit) == "Duyuru 2 tahtaya gönderildi." and len(komutlar()) == 2


@pytest.mark.parametrize(
    ("alan", "deger", "beklenen"),
    [("hedef_tahta", "t2", "t2"), ("grup", "grup", "t1"), ("bina", "B Blok", "t2"), ("kat", "1", "t1"),
     ("duzey", "10", "t2"), ("devre", "sabah", "t1")],
)  # fmt: skip
def test_secime_gore_her_olcut_yalniz_kendi_tahtasina(okul, panel, alan, deger, beklenen):
    deger = {"t2": str(kimlik(okul["t2"])), "grup": str(okul["grup"])}.get(deger, deger)
    yanit = gonder(panel, yeni(panel), metin="Seçime göre", kime="secim", **{alan: [deger]})
    assert ileti(yanit) == "Duyuru 1 tahtaya gönderildi.", alan
    assert [k["tahta_id"] for k in komutlar()] == [kimlik(okul[beklenen])]


# ---- 25–28: yeniden çizim, ön seçim, düğme, plan -----------------------------------------------------------------------
def test_hata_ciziminde_degerler_ve_acik_bolumler(okul, panel):
    t2 = str(kimlik(okul["t2"]))
    yanit = gonder(panel, yeni(panel), baslik="Başlık", metin="Geçmişe plan", sure_dk="7", kapatilabilir=None,
                   zaman="bir_kez", bir_tarih="2026-11-10", bir_saat="10:00", siklik="haftalik", gun=["2", "5"],
                   tekrar_saat="11:15", kime="secim", bina=["A Blok"], grup=[str(okul["grup"])], hedef_tahta=[t2])  # fmt: skip
    assert yanit.status_code == 400 and komutlar() == [] and sorgu("SELECT COUNT(*) AS n FROM duyuru_plani")[0]["n"] == 0
    assert '<div class="bant hata" role="alert">' in yanit.text
    f = form_oku(yanit.text)
    assert f.deger("baslik") == ["Başlık"] and f.deger("metin") == ["Geçmişe plan"] and f.deger("sure_dk") == ["7"]
    assert "kapatilabilir" not in f.isaretli
    assert f.isaretli["zaman"] == ["bir_kez"] and f.deger("bir_tarih") == ["2026-11-10"] and f.deger("bir_saat") == ["10:00"]
    assert f.isaretli["siklik"] == ["haftalik"] and f.isaretli["gun"] == ["2", "5"] and f.deger("tekrar_saat") == ["11:15"]
    assert f.isaretli["kime"] == ["secim"] and f.isaretli["bina"] == ["A Blok"]
    assert f.isaretli["grup"] == [str(okul["grup"])] and f.isaretli["hedef_tahta"] == [t2]
    # Korunan seçim görünür: iki açılır da açık çizilir.
    assert len(f.details) >= 2 and all("open" in d for d in f.details if d.get("class") != "onizleme-liste")
    assert re.findall(r'<a href="([^"]+)" aria-current="page">', serit(yanit.text)) == ["/duyurular/yeni"]
    # Varsayılan formda ikisi de kapalıdır (seçim yok).
    assert not any("open" in d for d in form_oku(yeni(panel)).details)


def test_on_secim_tek_tek_acik_ve_ozet(okul, panel):
    t1, t2 = kimlik(okul["t1"]), kimlik(okul["t2"])
    sayfa = yeni(panel, f"?tahta={t1}&tahta={t2}&secimden=1")
    f = form_oku(sayfa)
    assert f.isaretli["kime"] == ["secim"] and sorted(f.isaretli["hedef_tahta"]) == sorted([str(t1), str(t2)])
    assert f.isaretli["zaman"] == ["hemen"] and f.isaretli["kapatilabilir"] == ["1"]
    tek = next(d for d in f.details if d.get("class") == "tek-tek")
    assert "open" in tek and 'data-on-secim="2"' in sayfa
    ozet = sayfa.split('data-alan="gonder-ozet"', 1)[1].split("</p>", 1)[0]
    assert "2 tahtaya" in ozet and "hemen" in ozet
    # Gönderilince yalnız seçilen iki tahta.
    assert ileti(gonder(panel, sayfa, metin="Seçimden")) == "Duyuru 2 tahtaya gönderildi."
    bos = yeni(panel, "?secimden=1")
    f = form_oku(bos)
    assert f.isaretli["kime"] == ["secim"] and "hedef_tahta" not in f.isaretli
    assert "Tahta seçilmedi" in bos.split('data-alan="gonder-ozet"', 1)[1].split("</p>", 1)[0]
    assert gonder(panel, bos, metin="Boş seçim").status_code == 400


def test_gonder_dugmesi_metni_ve_noscript(okul, panel):
    def dugme(sayfa):
        return re.search(r'<button([^>]*id="duyuru-gonder"[^>]*)>([^<]*)</button>', sayfa)

    # JS'siz düğme metni YANSIZDIR: sunucu "Şimdi yayımla" çizseydi kullanıcı "Bir kez"i seçince yazı yanlış kalırdı
    # (ve kopyada "Planı kaydet" yazarken "Hemen" seçilirse duyuru hemen giderdi). Kesin metni panel.js yazar.
    sayfa = yeni(panel)
    d = dugme(sayfa)
    assert d.group(2).strip() == "Yayımla ya da planı kaydet"
    assert 'type="button"' not in d.group(1) and "data-onay" not in d.group(1)
    assert 'data-hemen="Şimdi yayımla"' in d.group(1) and 'data-plan="Planı kaydet"' in d.group(1)
    form_ici = sayfa.split('id="duyuru-formu"', 1)[1].split("</form>", 1)[0]
    assert "<noscript>" in form_ici and "Seçili olmayan zamanın alanları dikkate alınmaz." in form_ici
    assert "data-kirli-izle" not in form_ici and "data-onay" not in form_ici
    plan_id = plan_olustur(panel, metin="Plan", zaman="bir_kez", bir_tarih="2026-11-17", bir_saat="10:00")
    assert dugme(yeni(panel, f"?kopya={plan_id}")).group(2).strip() == "Yayımla ya da planı kaydet"  # Hemen de seçilebilir
    plan_sayfasi = panel.get(f"/duyurular/plan/{plan_id}").text
    assert dugme(plan_sayfasi).group(2).strip() == "Planı kaydet"
    assert 'name="zaman" value="hemen"' not in plan_sayfasi


def test_plan_duzenleme_seridi_ve_salt_okunur(okul, panel):
    plan_id = plan_olustur(panel, metin="Yöneticinin planı", zaman="bir_kez", bir_tarih="2026-11-17", bir_saat="10:00")
    sayfa = panel.get(f"/duyurular/plan/{plan_id}").text
    assert re.findall(r'<a href="([^"]+)" aria-current="page">', serit(sayfa)) == ["/duyurular"]
    assert 'id="duyuru-gonder"' in sayfa and '<fieldset class="duz" disabled>' not in sayfa
    # Plan JS'siz kaydedilir: sayfanın çizdiği alanlar + değişen metin.
    yanit = gonder(panel, sayfa, f"/duyurular/plan/{plan_id}", metin="Düzeltildi", bir_saat="11:30")
    assert yanit.status_code == 303 and "t=hata" not in yanit.headers["location"], ileti(yanit)
    plan = sorgu("SELECT * FROM duyuru_plani WHERE id = ?", plan_id)[0]
    assert (plan["metin"], plan["saat"], plan["tekrar"]) == ("Düzeltildi", "11:30", "tek")
    kullanici_ekle(panel, "mudur.yrd")
    gir(panel, "mudur.yrd")
    salt = panel.get(f"/duyurular/plan/{plan_id}").text
    assert '<fieldset class="duz" disabled>' in salt and 'id="duyuru-gonder"' not in salt
    assert 'class="gonder-cubugu"' not in salt
    assert re.findall(r'<a href="([^"]+)" aria-current="page">', serit(salt)) == ["/duyurular"]


def test_gonder_ozeti_js_siz_gizli_ve_bayat_kalmaz(okul, panel):
    """Özet yanlış hedef/zaman riskine karşı son denetimdir: JS'siz güncellenemeyeceği için gizli çizilir."""
    sayfa = yeni(panel)
    assert re.search(r'<p class="gonder-ozet" data-alan="gonder-ozet" hidden>', sayfa)
    css = (Path(__file__).parent.parent / "tahta_sunucu" / "statik" / "stil.css").read_text(encoding="utf-8")
    assert ".gonder-ozet[hidden] { display: none; }" in css  # display: grid `hidden`ı ezmesin
    js = (Path(__file__).parent.parent / "tahta_sunucu" / "statik" / "panel.js").read_text(encoding="utf-8")
    govde = js.split("function duyuruFormuKur()", 1)[1].split("\n  function acilKur()", 1)[0]
    assert "ozetKutusu.hidden = false" in govde
    # Hedef değişince eski sayı gecikme + istek süresince görünmez; ağ hatası sessizce yutulmaz.
    gecikmeli = govde.split("function gecikmeliOnizle()", 1)[1].split("}", 1)[0]
    assert "sira++" in gecikmeli and 'alanYaz("ozet-hedef", "Tahta sayısı hesaplanıyor…")' in gecikmeli
    assert gecikmeli.index("alanYaz") < gecikmeli.index("setTimeout")
    assert ".catch(function () {})" not in govde and 'alanYaz("ozet-hedef", "Tahta sayısı alınamadı")' in govde
    # Zaman özeti seçilen tarih ve saati yazar; eksik alan açıkça söylenir.
    for parca in ('"tarih ve saat seçilmedi"', '"bitiş seçilmedi"', '"her gün (hafta içi)"', 'deger("bir_saat")', 'deger("bitis")'):
        assert parca in govde, parca


@pytest.mark.parametrize(
    "degisen, beklenen_ileti, yer, baslik",
    [
        ({"metin": ""}, "Duyuru metni boş olamaz.", "icerik", "icerik-baslik"),
        ({"metin": "x", "sure_dk": "999"}, "Süre 1-240 dakika olmalı.", "icerik", "icerik-baslik"),
        ({"metin": "x", "kime": "secim"}, None, "kime", "kime-baslik"),
        ({"metin": "x", "zaman": "bir_kez"}, "Duyurunun tarihini seçin.", "zaman", "zaman-baslik"),
        ({"metin": "x", "zaman": "tekrarli", "tekrar_saat": "08:20"}, "Bitiş tarihini seçin.", "zaman", "zaman-baslik"),
    ],
)
def test_hata_iletisi_ilgili_bolumde_de_cizilir(okul, panel, degisen, beklenen_ileti, yer, baslik):
    """Tek sayfalık formda sayfa başındaki ileti alandan uzak kalır: aynı ileti ilgili bölümün içinde de durur."""
    yanit = gonder(panel, yeni(panel), **degisen)
    assert yanit.status_code == 400
    metin = ileti(yanit)
    assert metin and (beklenen_ileti is None or metin == beklenen_ileti)
    sayfa = yanit.text
    assert sayfa.count('id="hata-yeri"') == 1 and sayfa.count('role="alert"') == 1
    assert 'href="#hata-yeri"' in sayfa
    # İleti doğru bölümün başlığından sonra, bir sonraki bölümden önce.
    bolumler = ["icerik-baslik", "kime-baslik", "zaman-baslik"]
    konum = sayfa.index('id="hata-yeri"')
    bas = sayfa.index(f'<h2 id="{baslik}"')
    sonrakiler = [sayfa.index(f'<h2 id="{b}"') for b in bolumler if sayfa.index(f'<h2 id="{b}"') > bas]
    assert bas < konum and all(konum < s for s in sonrakiler), yer
    kutu = sayfa[konum:].split("</p>", 1)[0]
    assert html_metni(kutu).endswith(metin)
    assert sorgu("SELECT COUNT(*) AS n FROM duyuru")[0]["n"] == 0 and sorgu("SELECT COUNT(*) AS n FROM duyuru_plani")[0]["n"] == 0
    # Hatasız sayfada kutu ve bağlantı yok.
    assert 'id="hata-yeri"' not in yeni(panel) and "#hata-yeri" not in yeni(panel)


def test_tekrarli_bitis_zorunlu_yazar_ama_required_degil(okul, panel):
    sayfa = yeni(panel)
    assert '<label for="bitis">Bitiş (zorunlu)</label>' in sayfa and 'aria-describedby="bitis-not"' in sayfa
    assert "Bitiş tarihi seçilmeden tekrarlı plan kaydedilmez" in sayfa
    # `required` yok: JS'siz üç zaman bloğu da görünür; "Hemen" gönderimi boş bitişe takılmamalı.
    form_ici = sayfa.split('id="duyuru-formu"', 1)[1].split("</form>", 1)[0]
    assert " required" not in form_ici


def test_duyurular_listesinde_bolum_seridi(okul, panel):
    sayfa = panel.get("/duyurular").text
    assert sayfa.count('aria-label="Duyurular bölümü"') == 1
    assert re.findall(r'<a href="([^"]+)" aria-current="page">', serit(sayfa)) == ["/duyurular"]
    assert '<a href="/duyurular/yeni">Yeni duyuru</a>' in serit(sayfa)
    assert 'class="dugme ana" href="/duyurular/yeni"' in sayfa  # sağ üstteki ana düğme durur


# ---- 29: panel.js kancaları -------------------------------------------------------------------------------------------
def test_panel_js_duyuru_kancalari():
    js = (Path(__file__).parent.parent / "tahta_sunucu" / "statik" / "panel.js").read_text(encoding="utf-8")
    govde = js.split("function duyuruFormuKur()", 1)[1].split("\n  function acilKur()", 1)[0]
    assert "data-bugun" in govde and "data-sure" in govde and "data-gun" in govde
    # "Bugün" sunucunun verdiği tarihten hesaplanır; tarayıcının saati kullanılmaz.
    assert "new Date()" not in govde and "Date.now" not in govde
    assert "textContent" in govde and "innerHTML" not in govde
    assert "form.id" not in govde
    # Hedef kuralı ve koşullu alanlar yerinde (0.3.0'dan beri aynı): gizlenen alan silinmez, yalnız `hidden` olur.
    assert "function hedefTopla()" in govde and "function kosullariUygula()" in govde
    assert "/api/hedef-onizleme?hedef=" in govde
