"""Tahta sayfasının sekmeleri (0.17.0): Genel · Program · Bakım · Bilgiler. Bölünen sayfada hiçbir form alanı ve uç
kaybolmaz; POST dönüşleri doğru sekmeye gider; idareciye yönetici öğesi, tahtaya ait olmayan ders/öğretmen bilgisi
çizilmez. Uydurma veriyle."""

from __future__ import annotations

import re

import pytest
from test_program_panel import durum, hazirla
from yardimci import gir, ileti, kimlik, kullanici_ekle, sorgu, tahta_ekle

from tahta_sunucu import vt

SEKMELER = ("", "?sekme=program", "?sekme=bakim", "?sekme=bilgiler")
YETENEKLI = dict(durum(), yetenekler=["program_kilidi", "temizlik", "envanter", "ariza", "dugme"])


@pytest.fixture()
def okul(panel, tahta):
    """Zil saatleri kurulu okul, yetenekli ve çevrimiçi bir tahta (kimliği 1), bir idareci."""
    hazirla(panel)
    kullanici_ekle(panel, "idareci1")
    return kimlik(tahta_ekle(panel, tahta, "T-1", YETENEKLI, bina="A Blok", kat="1", subeler="9/A"))


def sayfalar(panel, t: int) -> dict[str, str]:
    sonuc = {}
    for ek in SEKMELER:
        yanit = panel.get(f"/tahta/{t}{ek}")
        assert yanit.status_code == 200, ek
        sonuc[ek] = yanit.text.split('<main id="icerik"')[1].split("</main>")[0]
    return sonuc


def etkin_sekme(sayfa: str) -> str:
    serit = sayfa.split('aria-label="Tahta bölümleri"')[1].split("</nav>")[0]
    etkinler = re.findall(r'<a href="[^"]*"\s+aria-current="page">\s*([^<]+?)\s*<', serit)
    assert len(etkinler) == 1, serit
    return etkinler[0]


def test_tahta_sayfasindaki_her_name_hala_var(panel, okul):
    t = okul
    panel.post("/program/istisna", data={"tahta": str(t), "sure": "1sa", "donus": f"/tahta/{t}"})
    with vt.islem() as b:  # donanım uyarısı bandı ("Gördüm" formu) çizilsin
        b.execute("INSERT INTO ayar (anahtar, deger) VALUES ('donanim_uyarilari', ?) ON CONFLICT(anahtar) DO UPDATE SET deger = excluded.deger", (f"[{t}]",))
    parcalar = sayfalar(panel, t)
    birlesik = "\n".join(parcalar.values())
    adlar = set(re.findall(r'\sname="([^"]+)"', birlesik))
    sabit = {"ad", "derslik", "alanlar", "bina", "kat", "duzey", "devre", "subeler", "eylem", "tahta", "donus", "tur", "sure", "program_muaf",
             "demirbas_no", "envanter_notu", "tahta_id", "kategori", "aciklama"}  # fmt: skip
    assert sabit <= adlar, sabit - adlar
    assert any(a.startswith("d_0_normal_") for a in adlar) and any(a.startswith("sube_0_normal_") for a in adlar)
    assert "d_4_normal_8" in adlar and "sube_4_normal_8" in adlar
    eylemler = set(re.findall(r'<form[^>]* action="([^"]+)"', birlesik))
    istisna = sorgu("SELECT id FROM program_istisna")[0]["id"]
    beklenen = {"/islem", f"/tahta/{t}/kaydet", f"/tahta/{t}/program", f"/tahta/{t}/temizlik", f"/tahta/{t}/envanter", "/arizalar",
                "/program/istisna", f"/program/istisna/{istisna}/iptal"}  # fmt: skip
    assert beklenen <= eylemler, beklenen - eylemler
    # 0.16.0'daki her komut türü sayfa başında (birincil + Diğer) ve Bakım'da (envanter) duruyor.
    for tur in ("kilitle", "kilit_ac", "duyuru_kaldir", "tani", "guncelle", "uyandir", "envanter"):
        assert f'name="tur" value="{tur}"' in birlesik or f'data-komut="{tur}"' in birlesik, tur
    for onay in ("kapat", "yeniden_baslat", "temizlik", "sil"):
        assert f'data-onay="{onay}"' in birlesik, onay
    assert 'name="eylem" value="kaydet"' in parcalar["?sekme=bilgiler"]
    # Bölüm kimlikleri yeni sekmelerde korunur (eski parça adresleri panel.js ile sekmeye taşınır).
    for kimlik_, sekme in (("program", "?sekme=program"), ("temizlik", "?sekme=bakim"), ("envanter", "?sekme=bakim"), ("arizalar", "?sekme=bakim"),
                           ("baglanti", "?sekme=bakim"), ("tani-baslik", "?sekme=bakim"), ("komut-baslik", "?sekme=bakim"),
                           ("tahta-bilgi", "?sekme=bilgiler")):  # fmt: skip
        assert f'id="{kimlik_}"' in parcalar[sekme], kimlik_
        assert sum(f'id="{kimlik_}"' in p for p in parcalar.values()) == 1, kimlik_
    # Bilgiler: 0.16.0'da Durum kutusundaki satırlar Genel ve Bakım'a dağıldı; hiçbiri kaybolmadı.
    for metin, sekme in (("Son görülme", ""), ("Ekran yardımcısı", ""), ("Ajan sürümü", ""), ("Kayıt zamanı", "?sekme=bakim"), ("IP · MAC", "?sekme=bakim"),
                         ("Makine adı", "?sekme=bakim"), ("İşletim sistemi", "?sekme=bakim"), ("Yüzer düğme", "?sekme=bakim"),
                         ("Ders yoklaması", "?sekme=bakim"), ("Paket imzası", "?sekme=bakim"), ("Demirbaş bilgisi", "?sekme=bakim"),
                         ("Haftalık dersli saat", "?sekme=program"), ("Bu tahtanın istisnaları", "?sekme=program"),
                         ("Hedefleme nitelikleri", "?sekme=bilgiler")):  # fmt: skip
        assert metin in parcalar[sekme], (metin, sekme)


def test_sekme_cizimi_ve_dogrulama(panel, tahta, okul):
    t = okul
    assert [etkin_sekme(p) for p in sayfalar(panel, t).values()] == ["Genel", "Program", "Bakım", "Bilgiler ve düzenle"]
    for bozuk in ("?sekme=yok", "?sekme=BAKIM", "?sekme=%3Cscript%3E", "?sekme="):
        yanit = panel.get(f"/tahta/{t}{bozuk}")
        assert yanit.status_code == 200 and etkin_sekme(yanit.text) == "Genel" and "<script>" not in yanit.text  # yönlendirme yok
    assert etkin_sekme(panel.get(f"/tahta/{t}?yer=temizlik").text) == "Bakım"  # eski dönüş adresi
    # Sayfa başı her sekmede aynı: kırıntı, komutlar, dönüş adresi etkin sekme.
    for ek, donus in (("", f"/tahta/{t}"), ("?sekme=program", f"/tahta/{t}?sekme=program"), ("?sekme=bakim", f"/tahta/{t}?sekme=bakim")):
        sayfa = panel.get(f"/tahta/{t}{ek}").text
        bas = sayfa.split('class="tahta-eylem"')[1].split("</nav>")[0]
        assert bas.count(f'name="donus" value="{donus}"') == 2 and f'href="/duyurular/yeni?tahta={t}"' in bas  # /islem ve durdur
        assert 'id="tahta-islem"' in bas and 'name="tur" value="kilitle"' in bas
    # İdareci: Bilgiler sekmesi çizilmez; adresle gelirse Genel açılır.
    gir(panel, "idareci1")
    sayfa = panel.get(f"/tahta/{t}?sekme=bilgiler").text
    assert etkin_sekme(sayfa) == "Genel" and "Bilgiler ve düzenle" not in sayfa and 'id="tahta-bilgi"' not in sayfa
    assert "A Blok · 1. kat" in sayfa and "9/A" in sayfa  # derslik ve nitelikler sayfa başında
    # Bekleyen tahta: yönetici doğrudan Bilgiler'i (onay formu) görür; idareci Genel'i.
    gir(panel, "yonetici")
    panel.post("/ekle", data={"eylem": "ac"})
    kod = panel.get("/ekle").text.split('class="buyuk-kod">')[1].split("<")[0]
    bekleyen = tahta.post("/ajan/kaydol", json={"kod": kod, "makine_adi": "etap", "surum": "0.17.0"}).json()["tahta_id"]
    sayfa = panel.get(f"/tahta/{bekleyen}").text
    assert etkin_sekme(sayfa) == "Bilgiler ve düzenle" and 'name="eylem" value="onayla"' in sayfa
    assert etkin_sekme(panel.get(f"/tahta/{bekleyen}?sekme=program").text) == "Genel"
    assert etkin_sekme(panel.get(f"/tahta/{bekleyen}?sekme=genel").text) == "Genel"
    gir(panel, "idareci1")
    sayfa = panel.get(f"/tahta/{bekleyen}").text
    assert etkin_sekme(sayfa) == "Genel" and "Yöneticinin onayını bekliyor." in sayfa


def test_bekleyen_tahtada_komut_ve_program_yok(panel, tahta, okul):
    panel.post("/ekle", data={"eylem": "ac"})
    kod = panel.get("/ekle").text.split('class="buyuk-kod">')[1].split("<")[0]
    bekleyen = tahta.post("/ajan/kaydol", json={"kod": kod, "makine_adi": "etap", "surum": "0.17.0"}).json()["tahta_id"]
    for ek in ("?sekme=genel", "?sekme=program", "?sekme=bakim", "?sekme=bilgiler"):
        sayfa = panel.get(f"/tahta/{bekleyen}{ek}").text.split('<main id="icerik"')[1].split("</main>")[0]
        assert "Onay bekliyor" in sayfa, ek
        for yok in ('action="/islem"', 'id="tahta-islem"', "tahta-eylem", 'name="tur"', 'data-onay="kapat"', 'data-onay="temizlik"',
                    'id="program"', "sekme=program", 'action="/program/istisna"', "/duyurular/yeni", "Arıza kaydı aç"):  # fmt: skip
            assert yok not in sayfa, (ek, yok)
    bakim = panel.get(f"/tahta/{bekleyen}?sekme=bakim").text
    assert 'id="envanter"' in bakim and 'id="baglanti"' in bakim and 'id="tani-baslik"' in bakim and 'id="komut-baslik"' in bakim
    assert 'data-onay="sil"' in panel.get(f"/tahta/{bekleyen}?sekme=bilgiler").text
    # Onaylanınca Genel açılır ve komutlar gelir.
    yanit = panel.post(f"/tahta/{bekleyen}/kaydet", data={"ad": "Yeni", "eylem": "onayla"})
    assert yanit.headers["location"].startswith(f"/tahta/{bekleyen}?m=")
    assert 'id="tahta-islem"' in panel.get(f"/tahta/{bekleyen}").text


def test_tahta_sayfasi_diger_menusu_sekiz_komut_ve_temizlik(panel, okul):
    t = okul
    sayfa = panel.get(f"/tahta/{t}").text
    bas = sayfa.split('class="tahta-eylem"')[1].split('<nav class="sekmeler"')[0]
    menu = bas.split('<ul class="menu-liste">')[1].split("</ul>")[0]
    assert re.findall(r'data-komut="([a-z_]+)"', menu) == ["kilitle", "kilit_ac", "duyuru_kaldir", "tani", "guncelle", "uyandir", "kapat", "yeniden_baslat"]
    # Komutlar formun `tur` alanıdır (tek= değil) ve tahta-islem formuna bağlıdır; bağlantı öğeleri menüde yoktur.
    assert 'name="tek"' not in bas and "data-tek" not in bas and "<a " not in menu
    for etkin in ("kilitle", "tani", "guncelle"):
        assert f'<button type="submit" name="tur" value="{etkin}" data-komut="{etkin}" form="tahta-islem">' in menu, etkin
    for onay in ("kapat", "yeniden_baslat"):
        assert re.search(rf'<button type="button" class="tehlike" data-komut="{onay}" data-onay="{onay}" data-onay-ad="T-1" form="tahta-islem"', menu), onay
    # Pasifler gerekçeli ve değersiz (çevrimiçi, kilitsiz, duyurusuz tahta).
    pasifler = re.findall(r"<button[^>]*disabled[^>]*>.*?</button>", menu, re.S)
    assert len(pasifler) == 3 and all(" name=" not in p for p in pasifler)
    assert "kilitli değil" in menu and "ekranda duyuru yok" in menu and "tahta açık" in menu
    # Oturum temizliği: ayrı boş forma bağlı onay düğmesi.
    assert 'data-onay="temizlik" data-onay-ad="T-1" form="tahta-temizlik-menu"' in menu
    assert f'<form method="post" action="/tahta/{t}/temizlik" id="tahta-temizlik-menu" hidden></form>' in bas
    # Sayfa başı: birincil düğme tek ve yıkıcı değil; "Program kilidini durdur" iki süreyle.
    form = bas.split('id="tahta-islem"')[1].split("</form>")[0]
    assert form.count("<button") == 1 and 'name="tur" value="kilitle"' in form
    assert "Bu tahtada durdur<" not in bas  # eski etiket neyin duracağını söylemiyordu
    durdur = bas.split("Program kilidini durdur")[1].split("</details>")[0]
    assert 'action="/program/istisna"' in durdur and f'name="tahta" value="{t}"' in durdur and 'value="1sa"' in durdur and 'value="bugun"' in durdur
    # Yeteneksiz ya da çevrimdışı tahtada temizlik öğesi pasif ve gerekçeli.
    with vt.islem() as b:
        b.execute("UPDATE tahta SET son_gorulme = son_gorulme - 100000 WHERE id = ?", (t,))
    kapali = panel.get(f"/tahta/{t}").text.split('<ul class="menu-liste">')[1].split("</ul>")[0]
    assert 'data-onay="temizlik"' not in kapali and re.search(r"Oturumu şimdi temizle</span><small>çevrimdışı</small>", kapali)
    assert re.search(r'data-onay="kapat"[^>]* disabled', kapali)


@pytest.mark.parametrize(
    ("yol", "veri", "beklenen", "hata"),
    [
        ("/islem", {"tur": "kilitle", "tahta": "1", "donus": "/tahta/1?sekme=bakim"}, "/tahta/1?sekme=bakim&m=", False),
        ("/islem", {"tur": "kilitle", "tahta": "1", "donus": "/tahta/1"}, "/tahta/1?m=", False),
        ("/islem", {"tur": "bilinmeyen", "tahta": "1", "donus": "/tahta/1?sekme=program"}, "/tahta/1?sekme=program&m=", True),
        ("/islem", {"tur": "envanter", "tahta": "1", "donus": "/tahta/1?sekme=bakim#envanter"}, "/tahta/1?sekme=bakim&m=", False),
        ("/tahta/1/kaydet", {"ad": "T-1", "eylem": "kaydet"}, "/tahta/1?sekme=bilgiler&m=", False),
        ("/tahta/1/kaydet", {"ad": "", "eylem": "kaydet"}, "/tahta/1?sekme=bilgiler&m=", True),
        ("/tahta/1/kaydet", {"ad": "T-1", "eylem": "kaydet", "alanlar": "1", "kat": "çatı"}, "/tahta/1?sekme=bilgiler&m=", True),
        ("/tahta/1/kaydet", {"ad": "T-1", "eylem": "sil"}, "/tahtalar?m=", False),
        ("/tahta/99/kaydet", {"ad": "x", "eylem": "kaydet"}, "/tahtalar?m=", True),
        ("/tahta/1/program", {"d_0_normal_1": "1"}, "/tahta/1?sekme=program&m=", False),
        ("/tahta/1/program", {"d_0_normal_1": "1", "sube_0_normal_1": "13/Z"}, "/tahta/1?sekme=program&m=", True),
        ("/tahta/99/program", {}, "/tahtalar?m=", True),
        ("/program/istisna", {"tahta": "1", "sure": "1sa", "donus": "/tahta/1?sekme=program"}, "/tahta/1?sekme=program&m=", False),
        ("/program/istisna", {"tahta": "1", "sure": "bugun", "donus": "/tahta/1?sekme=bakim"}, "/tahta/1?sekme=bakim&m=", False),
        ("/tahta/1/temizlik", {"eylem": "temizle"}, "/tahta/1?sekme=bakim&yer=temizlik&m=", False),
        ("/tahta/1/temizlik", {}, "/tahta/1?sekme=bakim&yer=temizlik&m=", True),
        ("/tahta/99/temizlik", {"eylem": "temizle"}, "/tahtalar?m=", True),
        ("/tahta/1/envanter", {"demirbas_no": "TS-1", "envanter_notu": ""}, "/tahta/1?sekme=bakim&m=", False),
        ("/tahta/1/envanter", {"demirbas_no": "x" * 80}, "/tahta/1?sekme=bakim&m=", True),
        ("/tahta/99/envanter", {"demirbas_no": "TS-1"}, "/tahtalar?m=", True),
        ("/tahta/1/donanim-goruldu", {}, "/tahta/1?sekme=bakim&m=", False),
        ("/arizalar", {"tahta_id": "1", "kategori": "", "donus": "/tahta/1?sekme=bakim#arizalar"}, "/tahta/1?sekme=bakim&m=", True),
        ("/arizalar", {"tahta_id": "1", "kategori": "acilis", "donus": "/tahta/1?sekme=bakim#arizalar"}, "/ariza/1", False),
    ],
)  # fmt: skip
def test_her_postun_donus_sekmesi(panel, okul, yol, veri, beklenen, hata):
    yanit = panel.post(yol, data=veri)
    adres = yanit.headers["location"]
    assert yanit.status_code == 303 and adres.startswith(beklenen), adres
    assert ("t=hata" in adres) == hata, (adres, ileti(yanit))
    if "#" in veri.get("donus", "") and beklenen.startswith("/tahta/"):
        assert adres.endswith("#" + veri["donus"].split("#")[1])  # ileti parçadan önce, parça sonda
    if "temizlik" in yol and beklenen.startswith("/tahta/"):
        assert adres.endswith("#ileti")
    if yol.endswith(("/envanter", "/donanim-goruldu")) and beklenen.startswith("/tahta/"):
        assert adres.endswith("#envanter")


def test_temizlik_iletisi_bakimda_cizilir_ve_istisna_iptali_programa_doner(panel, okul):
    t = okul
    yanit = panel.post(f"/tahta/{t}/temizlik", data={"eylem": "temizle"})
    sayfa = panel.get(yanit.headers["location"].split("#")[0]).text
    bolum = sayfa.split('id="temizlik"')[1].split("</section>")[0]
    assert 'id="ileti" tabindex="-1" data-odakla' in bolum and "Oturum temizliği tahtaya gönderildi." in bolum
    assert sayfa.count("Oturum temizliği tahtaya gönderildi.") == 1  # sayfa başında ikinci kez çizilmez
    # Başka sekmede (ya da bekleyen tahtada) ileti kaybolmaz: sayfa başında çizilir.
    assert "Deneme iletisi" in panel.get(f"/tahta/{t}?sekme=program&yer=temizlik&m=Deneme+iletisi").text
    panel.post("/program/istisna", data={"tahta": str(t), "sure": "1sa", "donus": f"/tahta/{t}?sekme=program"})
    program = panel.get(f"/tahta/{t}?sekme=program").text
    iptal = re.search(r'<form method="post" action="(/program/istisna/\d+/iptal)"[^>]*><input type="hidden" name="donus" value="([^"]+)">', program)
    assert iptal and iptal.group(2) == f"/tahta/{t}?sekme=program"
    assert panel.post(iptal.group(1), data={"donus": iptal.group(2)}).headers["location"].startswith(f"/tahta/{t}?sekme=program&m=")


def test_idareci_tahta_sayfasi_salt_okunur_ve_yonetici_ogesi_yok(panel, okul):
    t = okul
    panel.post(f"/tahta/{t}/program", data={"d_0_normal_1": "1", "sube_0_normal_1": "9/A"})
    gir(panel, "idareci1")
    parcalar = sayfalar(panel, t)
    birlesik = "\n".join(parcalar.values())
    for yok in (f'action="/tahta/{t}/kaydet"', f'action="/tahta/{t}/program"', f'action="/tahta/{t}/envanter"', "donanim-goruldu",
                "/ayarlar", "/gruplar", "/tahtalar/ice-aktar", "sekme=bilgiler", "Tahtayı kaldır", 'data-onay="sil"'):  # fmt: skip
        assert yok not in birlesik, yok
    # İdarecinin bugün yapabildiği her şey yerinde: komutlar, durdurma, temizlik, envanter yenileme, arıza açma.
    for var in ('action="/islem"', 'action="/program/istisna"', f'action="/tahta/{t}/temizlik"', 'name="tur" value="envanter"',
                'action="/arizalar"', "Ders · 9/A", "Demirbaş no"):  # fmt: skip
        assert var in birlesik, var
    assert etkin_sekme(parcalar["?sekme=bilgiler"]) == "Genel"


def test_tahta_sayfasinda_ders_basligi_ve_ogretmen_yok(panel, okul):
    """Soru 75 onaylanmadı (kural 12): öğretmen programı yüklü olsa da tahta listesine ve sayfasına ders başlığı,
    öğretmen adı ya da "Bugün bu tahtada" şeridi eklenmez."""
    t = okul
    with vt.islem() as b:
        ogretmen = b.execute("INSERT INTO ogretmen(ad,soyad) VALUES('Uydurmaad','Uydurmasoyad')").lastrowid
        for no in range(1, 9):
            b.execute("INSERT INTO ogretmen_program(sube,gun,ders_no,baslangic,bitis,ders_adi,ogretmen_id,guncelleme) "
                      "VALUES('9/A',0,?,'08:20','09:00','Uydurma Dersi',?,?)", (no, ogretmen, vt.simdi()))  # fmt: skip
    for yol in ("/tahtalar", "/", *(f"/tahta/{t}{ek}" for ek in SEKMELER)):
        govde = panel.get(yol).text.split('<main id="icerik"')[1]
        for yasak in ("Uydurma Dersi", "Uydurmaad", "Uydurmasoyad", "Bugün bu tahtada", "ogretmen"):
            assert yasak not in govde, (yol, yasak)
    veri = panel.get("/api/durum").text
    assert "Uydurma Dersi" not in veri and "Uydurmaad" not in veri
    # Genel'de yalnız bugünkü program durum metni vardır.
    assert "<dt>Program</dt>" in panel.get(f"/tahta/{t}").text


def test_uygulama_ici_baglantilar_sekmeye_gider(panel, okul):
    t = okul
    assert f'href="/tahta/{t}?sekme=program"' in panel.get("/program?bolum=derslik").text
    assert f'href="/tahta/{t}?sekme=bakim#envanter"' in panel.get("/envanter").text
    genel = panel.get(f"/tahta/{t}").text
    for bag in (f'href="/tahta/{t}?sekme=bakim#baglanti"', f'href="/tahta/{t}?sekme=bakim#arizalar"', f'href="/tahta/{t}?sekme=bakim#komut-baslik"',
                f'href="/tahta/{t}?sekme=program"', 'class="kirinti" aria-label="Konum"><a href="/tahtalar">Tahtalar</a>'):  # fmt: skip
        assert bag in genel, bag
    # Olmayan ya da kaldırılmış tahta listeye döner.
    assert panel.get("/tahta/99").headers["location"].startswith("/tahtalar?m=")


def test_sayfa_basinda_durdur_yalniz_program_kilidi_acikken_ve_muaf_degilken(panel, okul):
    t = okul

    def bas() -> str:
        return panel.get(f"/tahta/{t}").text.split('class="tahta-eylem"')[1].split('<nav class="sekmeler"')[0]

    assert "Program kilidini durdur" in bas()
    # Tahta muafsa sayfa başında çizilmez; Program sekmesindeki düğmeler durur (işlev kaybı yok).
    panel.post(f"/tahta/{t}/program", data={"program_muaf": "1"})
    assert "Program kilidini durdur" not in bas() and 'action="/program/istisna"' not in bas()
    assert "Bu tahtada 1 saat durdur" in panel.get(f"/tahta/{t}?sekme=program").text
    panel.post(f"/tahta/{t}/program", data={})
    assert "Program kilidini durdur" in bas()
    # Program kilidi kapalıyken de çizilmez.
    panel.post("/program/kurallar", data={"pk_gecikme_dk": "2", "bd_esik_dk": "10"})
    assert "Program kilidini durdur" not in bas() and "Bu tahtada 1 saat durdur" in panel.get(f"/tahta/{t}?sekme=program").text


def test_tahta_sayfasi_onay_uyarisi_icin_durum_forma_yazilir_ve_rozet_yinelenmez(panel, okul):
    t = okul
    form = re.search(r'<form method="post" action="/islem" id="tahta-islem"[^>]*>', panel.get(f"/tahta/{t}").text).group(0)
    assert "data-cevrimdisi" not in form
    with vt.islem() as b:
        b.execute("UPDATE tahta SET son_gorulme = son_gorulme - 100000, surum = '0.1.0' WHERE id = ?", (t,))
    sayfa = panel.get(f"/tahta/{t}").text
    form = re.search(r'<form method="post" action="/islem" id="tahta-islem"[^>]*>', sayfa).group(0)
    assert 'data-cevrimdisi="1"' in form and "data-oturum-acik" not in form
    # "Güncelleme var" Genel'de yalnız Ajan sürümü satırında yazar (rozet şeridinde yinelenmez).
    genel = sayfa.split('<main id="icerik"')[1].split("</main>")[0]
    assert genel.count("Güncelleme var") == 1
