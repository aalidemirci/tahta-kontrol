"""Bugün sayfası (0.18.0, panel arayüzü 4. aşama), HTTP düzeyi: bölümler, ileti, rol, gizlilik, "Hepsini kilitle…"
(V2: sınavdaki tahta atlanır), "/" ↔ "/tahtalar" ayrımı, /api/durum eki, V1 (güncelleme rozeti). Uydurma veriyle."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest
from test_bugun import SINAV, bekleyen_tahta, surum_bildir
from test_program_panel import calistir, ders_isaretle, hazirla
from test_program_panel import durum as program_durumu
from test_yoklama import hazir, ogrenci_id  # noqa: F401
from test_yoklama_defter import kayit, zil_yaz
from yardimci import an, gir, ileti, kimlik, kullanici_ekle, kur_ve_gir, sorgu, tahta_ekle, yeni_ajan_durumu

from tahta_sunucu import ayar, bugun, paket, sinav, tahta_liste, vt

KOK = Path(__file__).resolve().parent.parent / "tahta_sunucu"
STIL = (KOK / "statik" / "stil.css").read_text(encoding="utf-8")
BETIK = (KOK / "statik" / "panel.js").read_text(encoding="utf-8")
BOLUMLER = ("bugun-bas", "bugun-simdi", "bekleyenler", "bugun-tahtalar", "bugun-yoklama", "bugun-duyuru")
TASINAN_BANT_METINLERI = (
    "Yedek parolası belirlenmedi", "Yedek alınmıyor", "tahtalara bildirilen listede yok", "zamanlanmış duyuru kaçırıldı",
    "yayımlandı (kurulu sürüm", "Son deneme başarısız", "Yedek 2 günden eski", "ikinci kopyası yazılamadı",
)  # fmt: skip


def govde(sayfa: str) -> str:
    return sayfa.split('<main id="icerik"')[1].split("</main>")[0]


def bolum(sayfa: str, kimlik_: str) -> str:
    return sayfa.split(f'id="{kimlik_}"')[1].split("</section>")[0]


def komutlar() -> list[tuple[int, str]]:
    return [(k["tahta_id"], k["tur"]) for k in sorgu("SELECT tahta_id, tur FROM komut ORDER BY id")]


def cevrimdisi_yap(*idler) -> None:
    with vt.islem() as b:
        for i in idler:
            b.execute("UPDATE tahta SET son_gorulme = ? WHERE id = ?", (vt.simdi() - 10 * ayar.CEVRIMICI_ESIK_SN, i))


def sinava_al(monkeypatch, *idler) -> None:
    """Verilen tahtaları sınav penceresinde gösterir (satır rozetiyle aynı kaynak: sinav.pencere_haritasi)."""
    monkeypatch.setattr(sinav, "pencere_haritasi", lambda b, an_: {i: dict(SINAV) for i in idler})


@pytest.fixture()
def okul(panel, tahta):
    """Üç onaylı, çevrimiçi tahta (1, 2, 3) ve bir idareci."""
    kur_ve_gir(panel)
    kullanici_ekle(panel, "idareci1")
    return [kimlik(tahta_ekle(panel, tahta, ad, yeni_ajan_durumu())) for ad in ("T-1", "T-2", "T-3")]


# ---- sayfa iskeleti, ileti, menü ---------------------------------------------------------------------------
def test_bugun_bolumleri_ve_sirasi(panel, okul):
    yanit = panel.get("/")
    assert yanit.status_code == 200 and yanit.headers["cache-control"] == "no-store"
    sayfa = yanit.text
    assert "<title>Bugün · Tahta Kontrol</title>" in sayfa and "<h1>Bugün</h1>" in sayfa
    sira = [sayfa.index(f'id="{k}"') for k in BOLUMLER]
    assert sira == sorted(sira)
    for k in BOLUMLER:
        assert sayfa.count(f'id="{k}"') == 1, k
    kimlikler = re.findall(r'\sid="([^"]+)"', sayfa)
    assert len(kimlikler) == len(set(kimlikler)), [k for k in kimlikler if kimlikler.count(k) > 1]
    assert "Pazartesi, 16.11.2026" in bolum(sayfa, "bugun-bas") or "Pazartesi, 16.11.2026" in sayfa
    assert '<a class="dugme ana" href="/duyurular/yeni">' in sayfa and 'id="canli"' in sayfa and 'id="canli-bolge"' in sayfa
    veri = json.loads(sayfa.split('id="bugun-veri" type="application/json">')[1].split("</script>")[0])
    assert veri["acil"] is False and veri["cip_kipi"] == "cip" and veri["bekleyen"] == 0 and sorted(veri["tahtalar"]) == ["1", "2", "3"]
    with vt.islem() as b:
        assert veri["imza"] == bugun.imza(bugun.bekleyenler(b, {"rol": "yonetici"}, ipler=[]))


def test_bugun_iletiyi_cizer(panel, okul):
    sayfa = panel.get("/?m=Uydurma%20ileti&t=hata").text
    bant = re.search(r'<div class="bant hata" role="alert" id="ileti" tabindex="-1" data-odakla>(.*?)</div>', sayfa, re.S)
    assert bant and "Uydurma ileti" in bant.group(1)
    assert sayfa.index('id="ileti"') < sayfa.index('id="bugun-simdi"')
    iyi = panel.get("/?m=Tamam").text
    assert '<div class="bant" role="status" id="ileti" tabindex="-1" data-odakla>' in iyi
    assert 'id="ileti"' not in panel.get("/").text


def test_yetkisiz_donus_bugunde_ileti_gosterir(panel, okul):
    gir(panel, "idareci1")
    for yol in ("/ayarlar", "/ayarlar/kilit", "/yedekler", "/kullanicilar"):
        yanit = panel.get(yol)
        assert yanit.status_code == 303 and yanit.headers["location"].startswith("/?m="), yol
        sayfa = panel.get(yanit.headers["location"]).text
        assert "<h1>Bugün</h1>" in sayfa and 'role="alert"' in sayfa and "yönetici yetkisi gerekir" in sayfa, yol
    yanit = panel.post("/ayarlar/gorunum", data={"ana_renk": "#112233"})
    assert "yönetici yetkisi gerekir" in panel.get(yanit.headers["location"]).text


def test_menu_bugun_ogesi_ve_alt_cubuk(panel, okul):
    sayfa = panel.get("/").text
    menu = sayfa.split('id="menu"')[1].split("</aside>")[0]
    yollar = re.findall(r'<li(?: data-secili)?>\s*<a href="([^"]+)"', menu)
    assert yollar[:4] == ["/", "/tahtalar", "/duyurular", "/yoklama"] and len(yollar) == 10
    assert '<a href="/" aria-current="page"><svg class="simge" aria-hidden="true"><use href="#m-bugun"/></svg><span>Bugün</span></a>' in menu
    assert '<symbol id="m-bugun"' in sayfa
    cubuk = sayfa.split('class="alt-cubuk"')[1].split("</nav>")[0]
    assert re.findall(r'<a (?:class="menu-ac" )?href="([^"]+)"', cubuk) == ["/", "/tahtalar", "/duyurular", "/yoklama", "#menu"]
    assert '<a href="/" aria-current="page">' in cubuk and cubuk.count("aria-current") == 1
    gir(panel, "idareci1")
    menu = panel.get("/").text.split('id="menu"')[1].split("</aside>")[0]
    assert len(re.findall(r'<li(?: data-secili)?>\s*<a href="([^"]+)"', menu)) == 8
    assert 'href="/yedekler"' not in menu and 'href="/ayarlar"' not in menu


def test_menu_rozeti_bugundeki_satirlarla_ayni(panel, tahta, okul):
    bekleyen_tahta(panel, tahta)
    panel.post("/arizalar", data={"tahta_id": "1", "kategori": "acilis", "aciklama": ""})

    def rozetler(sayfa: str) -> dict[str, str]:
        menu = sayfa.split('id="menu"')[1].split("</aside>")[0]
        return dict(re.findall(r'<span>([^<]+)</span><span class="sayi-rozet">(\d+)</span>', menu))

    # Yönetici: Tahtalar = 1 arıza + 1 onay bekleyen; Yedekler = "yedek parolası yok" satırı. Bugün rozet taşımaz.
    for yol in ("/", "/tahtalar", "/duyurular", "/kayit"):
        assert rozetler(panel.get(yol).text) == {"Tahtalar": "2", "Yedekler": "1"}, yol
    assert 'Arızalar <span class="sayi-rozet">1</span>' in panel.get("/tahtalar").text  # sekme şeridi: yalnız arıza
    gir(panel, "idareci1")
    assert rozetler(panel.get("/").text) == {"Tahtalar": "1"}  # idareci: yalnız arıza


# ---- rol ve gizlilik ---------------------------------------------------------------------------------------
def test_bugun_idareci_htmlinde_yonetici_adresi_yok(panel, tahta, okul, monkeypatch):
    from tahta_sunucu import guvenlik

    bekleyen = bekleyen_tahta(panel, tahta)
    with vt.islem() as b:
        b.execute("UPDATE tahta SET ad = 'Bekleyen-Gizli', ip = '10.9.8.7', makine_adi = 'etap-gizli-makine' WHERE id = ?", (bekleyen,))
    surum_bildir()
    monkeypatch.setattr(guvenlik, "yerel_ipler", lambda: ["10.0.0.9"])
    panel.post("/ayarlar", data={"bolum": "adresler", "sunucu_adresleri": "https://10.0.0.5:8788"})
    yonetici = govde(panel.get("/").text)
    for parca in ('href="/yedekler"', 'href="/ayarlar/kilit"', 'href="/ayarlar/sunucu#adresler"', 'href="/ayarlar/veri#saklama"',
                  'href="/ayarlar#kurulum"', 'href="/tahtalar#onay-bekleyen"', "data-yeni-surum=", "1 yeni tahta onay bekliyor."):  # fmt: skip
        assert parca in yonetici, parca
    gir(panel, "idareci1")
    idareci = govde(panel.get("/").text)
    for yasak in ("/ayarlar", "/yedekler", "/ekle", "sekme=bilgiler", "data-yeni-surum", "github.com", "yayımlandı", "Bekleyen-Gizli",
                  "10.9.8.7", "etap-gizli-makine", "Tahta ekle", "Kurulumda", "onay bekliyor.", 'href="/ogrenciler"'):  # fmt: skip
        assert yasak not in idareci, yasak
    # İdareciye bilgi satırları: bağlantısız, ama koşul kaybolmaz.
    for bilgi in ("1 yeni tahta yöneticinin onayını bekliyor.", "Yedek alınmıyor; yöneticiye bildirin.",
                  "Bu bilgisayarın adresi (10.0.0.9) tahtalara bildirilen listede yok.",
                  "Kilit kodu tanımlı değil: kilitlenen tahta yalnız panelden açılır."):  # fmt: skip
        assert bilgi in idareci, bilgi
    satirlar = re.findall(r"<li data-is=.*?</li>", idareci, re.S)
    assert len(satirlar) == 5 and sum("<a " in s for s in satirlar) == 1  # yalnız "ajan güncellenebilir" bağlantılı
    assert "Sizi bekleyenler <span class=\"not\">· 5 iş</span>" in idareci


def test_bugun_onay_bekleyenin_adi_ve_ipsi_yonetici_sayfasinda_da_yok(panel, tahta, okul):
    bekleyen = bekleyen_tahta(panel, tahta)
    with vt.islem() as b:
        b.execute("UPDATE tahta SET ad = 'Bekleyen-Gizli', ip = '10.9.8.7' WHERE id = ?", (bekleyen,))
    sayfa = panel.get("/").text
    assert "1 yeni tahta onay bekliyor." in sayfa and "Bekleyen-Gizli" not in sayfa and "10.9.8.7" not in sayfa
    assert f"/tahta/{bekleyen}" not in sayfa  # çip ve bağlantı yok: adlar yalnız Tahtalar'daki bantta
    liste = panel.get("/tahtalar").text
    assert "Bekleyen-Gizli" in liste and 'id="onay-bekleyen"' in liste


def test_her_bekleyen_satirinin_baglantisi_var_olan_sayfadir(panel, tahta, okul, monkeypatch):
    from tahta_sunucu import guvenlik
    from tahta_sunucu import yedek as yedek_mod

    bekleyen_tahta(panel, tahta)
    panel.post("/arizalar", data={"tahta_id": "1", "kategori": "acilis", "aciklama": ""})
    surum_bildir()
    monkeypatch.setattr(guvenlik, "yerel_ipler", lambda: ["10.0.0.9"])
    monkeypatch.setattr(yedek_mod, "bekleyen_oku", lambda: {"onaylandi": False})
    panel.post("/ayarlar", data={"bolum": "adresler", "sunucu_adresleri": "https://10.0.0.5:8788"})
    with vt.islem() as b:
        b.execute("INSERT INTO duyuru (baslik, metin, sure_sn, kapatilabilir, hedef, olusturan, olusturma, durum) "
                  "VALUES ('D', 'm', 60, 1, '', 'x', ?, 'kacirildi')", (vt.simdi() - 60,))  # fmt: skip
    sayfa = panel.get("/").text
    satirlar = dict(re.findall(r'<li data-is="([a-z_]+)".*?(?:<a class="dugme" href="([^"]+)"[^>]*>|</li>)', bolum(sayfa, "bekleyenler"), re.S))
    assert set(satirlar) == {"yedek_parola", "geri_yukleme", "adres", "ogretim_yili", "onay", "ariza", "kacirilan", "kilit_kodu",
                             "guncelleme_tahta", "yeni_surum", "kurulum"}  # fmt: skip
    # Tehlike ve uyarı satırları (burada yedi) HEP açıktır; yalnız bilgi satırları aynı HTML'de, JS'siz açılan
    # "Diğer N iş" içindedir (kesilmez).
    assert '<summary class="dugme">Diğer 4 iş' in sayfa and sayfa.count("<li data-is=") == 11
    acik, katli = bolum(sayfa, "bekleyenler").split('<details class="acilir is-diger">')
    assert acik.count("<li data-is=") == 7 and 'data-durum="bilgi"' not in acik
    assert set(re.findall(r'<li data-is="[a-z_]+" data-durum="([a-z]+)"', katli)) == {"bilgi"}
    # Yeni sürüm satırı: dış bağlantının yanında denetimi kapatmanın yolu (0.17.0 bandındaki ikinci bağlantı).
    assert '<a class="is-ek" href="/ayarlar/guncelleme">Ayarlar</a>' in katli
    for anahtar, yol in satirlar.items():
        assert yol, anahtar
        if anahtar == "yeni_surum":
            assert yol == "https://github.com/aalidemirci/tahta-kontrol/releases/tag/v99.0.1"
            continue
        yanit = panel.get(html.unescape(yol).split("#")[0])
        assert yanit.status_code == 200, (anahtar, yol, yanit.status_code)
        parca = yol.partition("#")[2]
        if parca:
            assert f'id="{parca}"' in yanit.text, (anahtar, yol)


def test_bugunde_ders_basligi_ve_ogretmen_yok(panel, tahta, hazir, saat):  # noqa: F811
    """Soru 75 onaylanmadı: öğretmen programı yüklüyken de Bugün'de ders başlığı, öğretmen adı ve kodu yok."""
    zil_yaz()
    with vt.islem() as b:
        b.execute("INSERT INTO ogretmen_program(sube,gun,ders_no,baslangic,bitis,ders_adi,ogretmen_id,guncelleme) "
                  "VALUES('10/A',0,1,'08:20','09:00','Yapay Ders Başlığı',?,?)", (hazir["ogretmen_id"], vt.simdi()))  # fmt: skip
    saat.ayarla(an(16, 8, 30))
    for rol in ("yonetici", "idareci1"):
        if rol != "yonetici":
            kullanici_ekle(panel, rol)
        gir(panel, rol)
        sayfa = govde(panel.get("/").text)
        for yasak in ("Yapay Ders", "Örnek", hazir["kod"], "Ayşe"):
            assert yasak not in sayfa, (rol, yasak)
        assert "1. ders · 08:20–09:00" in sayfa  # yalnız ders numarası ve saat


def test_yoklama_kutusunda_kisi_adi_yok_ve_not_var(panel, tahta, hazir, saat):  # noqa: F811
    zil_yaz()
    saat.ayarla(an(18, 12))
    gir(panel, "yonetici")
    kayit(18, "10/A", 1, yok=["1047", "1102"], gec=["1150"], ogretmen_id=hazir["ogretmen_id"])
    kayit(18, "10/A", 2, yok=["1047"])
    with vt.islem() as b:
        vt.ayar_yaz(b, "ogretim_yili_bitis", "2027-06-18")  # yoksa saklama uyarısının metni ("mazeret/izin kayıtları…") çizilir
        b.execute("INSERT INTO yoklama_mazeret (ogrenci_id, bas_tarih, bit_tarih, tur, dayanak, giren, olusturma) "
                  "VALUES (?, '2026-11-18', '2026-11-18', 'raporlu', 'belge', 'yonetici', ?)", (ogrenci_id("1047"), vt.simdi()))  # fmt: skip
    once = sorgu("SELECT COUNT(*) AS n FROM kayit")[0]["n"]
    sayfa = panel.get("/").text
    kutu = bolum(sayfa, "bugun-yoklama")
    assert "Tahtadan alınan yoklama kâğıdın yanında yardımcı kayıttır. Burada görünmemesi dersin işlenmediği anlamına gelmez." in kutu
    assert "Bugün biten 8 dersin <b>2</b> tanesinde yoklama alındı" in kutu and "(her şubenin her dersi ayrı sayılır)" in kutu
    assert "şube-ders" not in kutu
    assert '<progress class="ilerleme" id="yk-ilerleme" max="8" value="2">' in kutu
    assert "<b>2</b> öğrenci en az bir derste yok · <b>1</b> geç" in kutu  # mazeretli öğrenci de "yok" sayısında
    assert '<a class="hap" href="/yoklama/sube?sube=10/A">10/A <span class="hap-sayi" aria-hidden="true">2/4</span><span class="gizli">: 4 dersin 2 tanesi alındı</span></a>' in kutu
    assert 'href="/yoklama">Günlük görünüm</a>' in kutu
    metin = re.sub(r"<[^>]+>", " ", govde(sayfa)).lower()
    for yasak in ("ayşe", "yılmaz", "burak", "kaya", "yurt", "1047", "1102", "1150", "örnek", hazir["kod"].lower(), "raporlu", "izinli",
                  "mazeret", "görevli", "özürlü", "devamsızlık", "yarım gün", "tam gün", "alınmadı", "gündür", "yönetmeli", "madde"):  # fmt: skip
        assert yasak not in metin, yasak
    assert sorgu("SELECT COUNT(*) AS n FROM kayit")[0]["n"] == once  # görüntüleme işlem kaydına yazılmaz
    assert "yoklama" not in json.dumps(panel.get("/api/durum").json()["bekleyen_is"])  # sayılar /api/durum'a girmez
    # Hedef sayfa yetkisini ve no-store'u korur.
    assert panel.get("/yoklama/sube?sube=10/A").headers["cache-control"] == "no-store"


def test_yoklama_kutusu_kapaliyken_sayi_ve_not_yok(panel, okul):
    kutu = bolum(panel.get("/").text, "bugun-yoklama")
    assert "Ders yoklaması kapalı." in kutu and 'href="/ayarlar/yoklama"' in kutu
    assert "yardımcı kayıt" not in kutu and "<progress" not in kutu and 'class="hap"' not in kutu
    gir(panel, "idareci1")
    kutu = bolum(panel.get("/").text, "bugun-yoklama")
    assert "Ders yoklaması kapalı." in kutu and "/ayarlar" not in kutu


def test_yoklama_kutusu_liste_yokken(panel, okul):
    panel.post("/ayarlar", data={"bolum": "yoklama", "yk_etkin": "1", "yk_maske": "ad_soyadbas", "yk_oturum_dk": "8", "yk_bosta_dk": "3"})
    kutu = bolum(panel.get("/").text, "bugun-yoklama")
    assert "Öğrenci listesi yüklenmedi." in kutu and 'href="/ogrenciler"' in kutu and "yardımcı kayıttır" in kutu
    gir(panel, "idareci1")
    kutu = bolum(panel.get("/").text, "bugun-yoklama")
    assert "Öğrenci listesi yüklenmedi." in kutu and 'href="/ogrenciler"' not in kutu


def test_duyuru_kutusunda_metin_ve_olusturan_yok(panel, okul):
    bos = bolum(panel.get("/").text, "bugun-duyuru")
    assert "Ekranda duyuru yok; bugün için planlı duyuru yok." in bos and 'href="/duyurular/yeni">Duyuru gönder</a>' in bos
    simdi = vt.simdi()
    with vt.islem() as b:
        b.execute(
            "INSERT INTO duyuru (baslik, metin, sure_sn, kapatilabilir, hedef, olusturan, olusturma, an, bitis, durum, tahta_sayisi) "
            "VALUES ('Kermes', 'GİZLİ DUYURU METNİ', 600, 1, '', 'Uydurma Kişi', ?, ?, ?, 'gonderildi', 3)", (simdi, simdi, simdi + 600))  # fmt: skip
        b.execute(
            "INSERT INTO duyuru_plani (baslik, metin, sure_sn, kapatilabilir, hedef_json, tekrar, saat, baslangic, bitis, gunler, "
            "gecerlilik, olusturan, olusturma) VALUES ('Öğle arası', 'GİZLİ PLAN METNİ', 60, 1, '{}', 'gunluk', '12:20', '2026-11-16', "
            "'2026-11-20', '0,1,2,3,4', 0, 'Uydurma Kişi', 0)")  # fmt: skip
    sayfa = panel.get("/").text
    kutu = bolum(sayfa, "bugun-duyuru")
    # "3 tahta" gönderim hedefidir (o an gösteren tahta sayısı değil): söz de bunu söyler.
    assert "<strong>Kermes</strong><span>3 tahtaya gönderildi · 09:10'da biter</span>" in kutu.replace("&#39;", "'")
    assert 'href="/duyurular#yayinda-baslik">Yönet<span class="gizli">: Kermes</span></a>' in kutu
    assert '<span class="olay-saat">12:20</span>' in kutu and "<strong>Öğle arası</strong>" in kutu and "Planlı" in kutu
    assert 'href="/duyurular">Tümü</a>' in kutu and "<form" not in kutu and "<button" not in kutu  # "Kaldır" düğmesi yok
    assert "GİZLİ" not in sayfa and "Uydurma Kişi" not in govde(sayfa)
    assert 'id="yayinda-baslik"' in panel.get("/duyurular").text


# ---- şu an: durdur, boş ders -------------------------------------------------------------------------------
def test_bugun_su_an_durdur_formu(uygulama, panel, tahta, saat):
    hazirla(panel)
    saat.ayarla(an(16, 9, 15))  # 2. ders (09:10–09:50)
    kullanici_ekle(panel, "idareci1")
    tahta_ekle(panel, tahta, "T-1", program_durumu())
    kart = bolum(panel.get("/").text, "bugun-simdi")
    form = kart.split('<form method="post" action="/program/istisna"')[1].split("</form>")[0]
    assert '<input type="hidden" name="donus" value="/">' in form
    assert '<button name="sure" value="1sa">1 saat durdur</button><button name="sure" value="bugun">Gün sonuna kadar durdur</button>' in form
    assert "Bütün tahtalarda; program kaynaklı kilitli tahtalar hemen açılır." in form
    assert "data-onay" not in form and 'name="tahta"' not in form  # onaysız (0.17.0 davranışı), bütün tahtalar
    assert '<details class="acilir durdur-menu" data-alan="durdur">' in kart
    assert 'href="/program/gun"' in kart and '<ol class="akis"' in kart and 'aria-current="time"' in kart
    assert "kaldı" not in kart  # geri sayım yazılmaz (istemci saatine güvenilmez)
    # İdareci de durdurur; ileti Bugün'de, rozet "durduruldu", "Durdur" gizli, "İstisnalar" bağlantısı açık.
    gir(panel, "idareci1")
    yanit = panel.post("/program/istisna", data={"donus": "/", "sure": "1sa"})
    assert yanit.status_code == 303 and yanit.headers["location"].startswith("/?m=") and "t=hata" not in yanit.headers["location"]
    assert ileti(yanit).startswith("Program kilidi durduruldu (tüm tahtalar); bitiş:")
    sayfa = panel.get(yanit.headers["location"]).text
    assert 'role="status" id="ileti"' in sayfa and "Program kilidi durduruldu (tüm tahtalar)" in sayfa
    kart = bolum(sayfa, "bugun-simdi")
    assert "Program kilidi durduruldu · bitiş 10:15" in kart
    assert re.search(r'data-alan="durdur"\s*hidden', kart) and '<a class="an-bag" data-alan="istisnalar" href="/program?bolum=istisnalar">' in kart
    assert len(sorgu("SELECT * FROM program_istisna")) == 1


def test_bugun_bos_ders_rozeti_ve_notu(uygulama, panel, tahta, saat):
    hazirla(panel, kilit=False, bos=True)
    saat.ayarla(an(16, 8, 0))
    t = kimlik(tahta_ekle(panel, tahta, "Gizli-Tahta-Adı", program_durumu()))
    ders_isaretle(panel, t, [1, 2])
    kart = bolum(panel.get("/").text, "bugun-simdi")
    assert re.search(r'data-alan="uyari" href="/program/uyarilar"\s*hidden', kart)  # uyarı yokken rozet ve not gizli
    assert re.search(r'data-alan="uyari-notu"\s*hidden', kart)
    for zaman in (an(16, 8, 21), an(16, 8, 30, 30), an(16, 8, 31)):  # 1. ders (08:20) + 10 dk eşik: kapalı tahta → uyarı
        calistir(uygulama, saat, zaman, canli=False)
    assert len(sorgu("SELECT * FROM bos_ders_uyari")) == 1
    once = sorgu("SELECT COUNT(*) AS n FROM kayit")[0]["n"]
    sayfa = panel.get("/").text
    kart = bolum(sayfa, "bugun-simdi")
    assert '<a class="rozet" data-durum="sorun" data-alan="uyari" href="/program/uyarilar">' in kart and "1 boş ders uyarısı" in kart
    assert '<span class="not" data-alan="uyari-notu">Dersin işlenmediği anlamına gelmez.</span>' in kart
    # Tahta adı, ders numarası, neden Bugün'ün hiçbir yerinde boş dersle birlikte yazılmaz; çipin okunur metninde de yok.
    assert "Boş ders:" not in sayfa and "1. ders (" not in sayfa and "kapalı)" not in sayfa
    assert "Boş ders:" in panel.get("/tahtalar").text  # satır rozeti listede durur
    assert sorgu("SELECT COUNT(*) AS n FROM kayit")[0]["n"] == once  # görüntüleme kayda yazılmaz (kural 13)
    # Bekleyenler listesine girmez (rozet olarak Şu an kartında kalır).
    assert not [s["anahtar"] for s in _isler(panel) if "bos" in s["anahtar"] or "boş ders uyarısı" in s["baslik"]]


def _isler(panel) -> list[dict]:
    with vt.islem() as b:
        return bugun.bekleyenler(b, {"rol": "yonetici"}, ipler=[])


def test_ders_saati_tanimsizken_su_an_karti(panel, okul):
    kart = bolum(panel.get("/").text, "bugun-simdi")
    assert "Ders saatleri tanımlı değil." in kart and 'href="/program"' in kart
    assert "akis" not in kart and "durdur" not in kart and 'data-alan="kilit"' not in kart
    gir(panel, "idareci1")
    kart = bolum(panel.get("/").text, "bugun-simdi")
    assert "Ders saatleri tanımlı değil." in kart and "<a " not in kart and "Zil saatlerini yönetici girer." in kart


# ---- tahtalar şu an ----------------------------------------------------------------------------------------
def test_bugun_tahta_sayilari_baglantilari(panel, tahta, okul):
    with vt.islem() as b:
        b.execute("""UPDATE tahta SET durum_json = '{"kilitli": true, "ekranlar": [{"arayuz": "gtk3"}]}' WHERE id = 2""")
        b.execute("UPDATE tahta SET surum = ? WHERE id = 1", (paket.ajan_paketi().surum,))
    cevrimdisi_yap(3)
    panel.post("/arizalar", data={"tahta_id": "1", "kategori": "acilis", "aciklama": ""})
    sayfa = panel.get("/").text
    kart = bolum(sayfa, "bugun-tahtalar")
    kutular = re.findall(r'<a href="/tahtalar\?durum=([a-z]+)" data-sayi="([a-z]+)" data-durum="([a-z]+)"(?: class="bos")?>.*?<b>(\d+)</b><span>([^<]+)</span></a>', kart, re.S)
    assert [(k[0], k[4]) for k in kutular] == [("acik", "Açık"), ("kilitli", "Kilitli"), ("duyuru", "Duyuruda"), ("sorun", "Ekran sorunu"),
                                              ("cevrimdisi", "Çevrimdışı"), ("guncelleme", "Güncelleme")]  # fmt: skip
    assert all(k[0] == k[1] == k[2] for k in kutular)
    sayilar = tahta_liste.sayilar(panel.get("/api/durum").json()["tahtalar"])
    assert {k[0]: int(k[3]) for k in kutular} == {a: sayilar[a] for a in bugun.KUTULAR} == {
        "acik": 1, "kilitli": 1, "duyuru": 0, "sorun": 0, "cevrimdisi": 1, "guncelleme": 2}  # fmt: skip
    # Aynı sayılar /tahtalar haplarında.
    liste = panel.get("/tahtalar").text
    for anahtar, n in sayilar.items():
        if anahtar in tahta_liste.SUZGECLER:
            assert re.search(rf'data-suzgec="{anahtar}"[^>]*>[^<]+<b>{n}</b>', liste), anahtar
    assert kart.count('class="bos"') == 2 and 'href="/tahtalar">Liste</a>' in kart
    assert "3</span> tahta, <span data-alan=\"cevrimici\">2</span> çevrimiçi" in sayfa
    # Çipler: tahta sayfasına gider; durum renk + şekil + (gizli) sözcük; arıza eki; güncelleme simgesi yok.
    cipler = dict(re.findall(r'<a class="cip" href="/tahta/(\d)" data-id="\d" data-durum="([a-z]+)">', kart))
    assert cipler == {"1": "acik", "2": "kilitli", "3": "cevrimdisi"}
    assert re.search(r'data-id="1".*?<span class="cip-ek" data-durum="sorun">.*?<span data-alan="okunur">Açık, Arıza</span>', kart, re.S)
    assert '<span data-alan="okunur">Kilitli, Güncelleme var</span>' in kart and "s-guncel" not in kart.split('class="harita"')[1]
    assert "Öğretmen hesabı" not in kart and "Oturum" not in kart  # oturum sınıfı çipte yok


def test_cip_grup_baglantisi_listede_var(panel, tahta):
    kur_ve_gir(panel)
    for ad, alanlar in (("A1", {"bina": "A Blok", "kat": "1"}), ("A2", {"bina": "A Blok", "kat": "2"}), ("B", {"bina": "B Blok"}), ("Z", {})):
        tahta_ekle(panel, tahta, ad, yeni_ajan_durumu(), **alanlar)
    kart = bolum(panel.get("/").text, "bugun-tahtalar")
    gruplar = re.findall(r'<a class="harita-ad" href="/tahtalar#grup-(\d+)">([^<]+)</a>', kart)
    assert [g[1] for g in gruplar] == ["A Blok · 1. kat", "A Blok · 2. kat", "B Blok", "Konumu belirtilmemiş"]
    liste = panel.get("/tahtalar").text
    for no, ad in gruplar:
        govde_ = liste.split(f'<tbody data-grup="{no}" id="grup-{no}">')[1].split("</tbody>")[0]
        assert f'<span class="grup-ad">{html.escape(ad)}</span>' in govde_, (no, ad)
    assert '.tahta-liste tbody[id] { scroll-margin-block-start:' in STIL
    # Tek ve adsız grupta başlık ve grup bağlantısı çizilmez.


def test_tek_adsiz_grupta_grup_basligi_yok(panel, okul):
    kart = bolum(panel.get("/").text, "bugun-tahtalar")
    assert 'class="harita-ad"' not in kart and kart.count('class="cip"') == 3


def test_altmistan_cok_tahtada_grup_kipi_sayfasi(panel, okul):
    with vt.islem() as b:
        simdi = vt.simdi()
        b.executemany("INSERT INTO tahta (ad, anahtar_ozet, durum, kayit_zamani, son_gorulme, surum, bina, kat) "
                      "VALUES (?, 'x', 'onayli', ?, ?, '0.3.0', ?, ?)", [(f"X-{i}", simdi, simdi, f"Blok {i % 2}", i % 3) for i in range(60)])  # fmt: skip
    sayfa = panel.get("/").text
    kart = bolum(sayfa, "bugun-tahtalar")
    assert 'class="cip"' not in kart and kart.count('data-alan="grup-ozet"') == 7
    assert re.search(r'<a class="harita-ad" href="/tahtalar#grup-1">Blok 0 · Zemin kat</a>\s*<span class="not">10 tahta: <span data-alan="grup-ozet">10 çevrimdışı</span>', kart) or \
        re.search(r'<a class="harita-ad" href="/tahtalar#grup-1">Blok 0 · Zemin kat</a>\s*<span class="not">10 tahta: <span data-alan="grup-ozet">10 ekran sorunu</span>', kart)  # fmt: skip
    veri = json.loads(sayfa.split('id="bugun-veri" type="application/json">')[1].split("</script>")[0])
    assert veri["cip_kipi"] == "grup" and len(veri["gruplar"]) == 63


def test_bos_durumlar_role_gore_bugunde(panel):
    kur_ve_gir(panel)
    kullanici_ekle(panel, "idareci1")
    kart = bolum(panel.get("/").text, "bugun-tahtalar")
    assert "Henüz onaylı tahta yok." in kart and 'href="/ekle"' in kart and 'id="hepsini-kilitle"' not in kart and "durum-ozet" not in kart
    assert 'href="/tahtalar">Liste</a>' not in kart and "bugun-ozet-kisa" not in panel.get("/").text  # boş listeye bağlantı yok
    gir(panel, "idareci1")
    kart = bolum(panel.get("/").text, "bugun-tahtalar")
    assert "Yönetici tahta ekleyince burada görünür." in kart and "/ekle" not in kart and "hepsini-kilitle" not in kart
    with vt.islem() as b:
        for anahtar, deger in (("yedek", {"acik_anahtar": "x", "parola_zamani": vt.simdi()}), ("son_yedek", {"basarili": True, "son_basarili": vt.simdi()}),
                               ("kilit_kodu", "x")):  # fmt: skip
            vt.ayar_yaz(b, anahtar, deger)
    sayfa = panel.get("/").text
    assert '<p class="not" id="bekleyen-yok">Bekleyen iş yok.</p>' in sayfa and "<li data-is=" not in sayfa
    assert "Sizi bekleyenler</h2>" in sayfa  # "· N iş" yazılmaz


# ---- hepsini kilitle ---------------------------------------------------------------------------------------
def kilit_formu(sayfa: str) -> str:
    return sayfa.split('<form method="post" action="/islem" id="hepsini-kilitle"')[1].split("</form>")[0]


def test_hepsini_kilitle_dugmesi_submit_degildir(panel, okul, monkeypatch):
    cevrimdisi_yap(3)
    sinava_al(monkeypatch, 2)
    for rol in ("yonetici", "idareci1"):
        gir(panel, rol)
        sayfa = panel.get("/").text
        form = kilit_formu(sayfa)
        assert form.startswith(' class="kutu-ayak" data-hedef="1" data-sinavda="1" data-cevrimdisi="1">'), form[:120]
        assert re.findall(r'<input type="([a-z]+)" name="([a-z]+)" value="([^"]*)">', form) == [("hidden", "donus", "/"), ("hidden", "kapsam", "hepsi")]
        dugmeler = re.findall(r"<button\b[^>]*>", form)
        assert dugmeler == ['<button type="button" class="dugme" data-onay="hepsini_kilitle" aria-haspopup="dialog">']
        for yasak in ('type="submit"', 'type="text"', 'name="tur"', 'name="tek"', 'name="tahta"', "<select", "<textarea", "kilit_ac"):
            assert yasak not in form, yasak
        assert "Hepsini kilitle…" in form and "<noscript>" in bolum(sayfa, "bugun-tahtalar")
        assert '<span data-alan="sinav-sayi">1</span> tahta sınav kipinde.' in sayfa
        # Bugün'de komut veren hiçbir gönder düğmesi yok: yalnız "Program kilidini durdur" ve "Çıkış" formları gönderir.
        gonderen = [d for d in re.findall(r"<button\b[^>]*>", govde(sayfa)) if 'type="button"' not in d]
        assert all('name="sure"' in d for d in gonderen), gonderen
    assert komutlar() == []


def test_hepsini_kilitle_tursuz_istek_reddedilir(panel, okul):
    """JS'siz olası tek gönderim (form alanları: donus + kapsam): komut yazılmaz."""
    yanit = panel.post("/islem", data={"donus": "/", "kapsam": "hepsi"})
    assert yanit.headers["location"].startswith("/?m=") and "t=hata" in yanit.headers["location"]
    assert ileti(yanit) == "Bu işlem bütün tahtalara birden verilemez." and komutlar() == []
    for tur in ("kilit_ac", "kapat", "yeniden_baslat", "tani"):  # "Hepsinin kilidini aç" yapılmadı
        assert "t=hata" in panel.post("/islem", data={"donus": "/", "kapsam": "hepsi", "tur": tur}).headers["location"], tur
    assert komutlar() == [] and tahta_liste.KAPSAM_HEPSI_TURLERI == {"kilitle"}


def test_hepsini_kilitle_acilde_ve_tahta_yokken_cizilmez(panel, okul):
    assert 'id="hepsini-kilitle"' in panel.get("/").text
    yanit = panel.post("/acil/baslat", data={"tur": "tatbikat", "sablon": "tahliye", "baslik": "TATBİKAT",
                                             "metin": "Uydurma tatbikat metni.", "sure_dk": "5", "parola": "gizli-parola", "onay": "1"})  # fmt: skip
    assert yanit.status_code == 303 and "t=hata" not in yanit.headers["location"], ileti(yanit)
    sayfa = panel.get("/").text
    assert 'id="hepsini-kilitle"' not in sayfa and "Acil yayın sürüyor; toplu kilit kapalı." in sayfa and 'class="acil-bant"' in sayfa
    assert '"acil": true' in sayfa.split('id="bugun-veri"')[1].split("</script>")[0]


def test_kapsam_hepsi_sinavdakini_atlar(panel, okul, monkeypatch):
    sinava_al(monkeypatch, 2)
    yanit = panel.post("/islem", data={"donus": "/", "kapsam": "hepsi", "tur": "kilitle"})
    assert ileti(yanit) == "Kilitle: 2 tahtaya gönderildi. 1 tahta sınav kipinde olduğu için atlandı."
    assert yanit.headers["location"].startswith("/?m=") and "t=hata" not in yanit.headers["location"]
    assert komutlar() == [(1, "kilitle"), (3, "kilitle")]
    kayit_ = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Kilitle'")[0]["ayrinti"]
    assert kayit_ == "bütün çevrimiçi tahtalar · 2 tahta: T-1, T-3 · 1 tahta sınavda atlandı" and "Uydurma Sınav" not in kayit_
    assert "Kilitle: 2 tahtaya gönderildi." in panel.get(yanit.headers["location"]).text


def test_kapsam_hepsi_hepsi_sinavdaysa_komut_yok(panel, okul, monkeypatch):
    sinava_al(monkeypatch, 1, 2, 3)
    once = sorgu("SELECT COUNT(*) AS n FROM kayit")[0]["n"]
    yanit = panel.post("/islem", data={"donus": "/", "kapsam": "hepsi", "tur": "kilitle"})
    assert ileti(yanit) == "Çevrimiçi tahtaların hepsi sınav kipinde; komut gönderilmedi." and "t=hata" in yanit.headers["location"]
    assert komutlar() == [] and sorgu("SELECT COUNT(*) AS n FROM kayit")[0]["n"] == once


def test_kapsam_hepsi_sinav_ve_cevrimdisi_birlikte(panel, okul, monkeypatch):
    cevrimdisi_yap(3)
    sinava_al(monkeypatch, 2, 3)  # 3 hem sınavda hem çevrimdışı: çevrimdışı sayılır, sınav sayısına girmez
    yanit = panel.post("/islem", data={"donus": "/", "kapsam": "hepsi", "tur": "kilitle"})
    assert ileti(yanit) == "Kilitle: 1 tahtaya gönderildi. 1 tahta sınav kipinde olduğu için atlandı. 1 çevrimdışı tahtaya gönderilmedi."
    assert komutlar() == [(1, "kilitle")]
    # Sayfadaki sayılar sunucunun işlediğiyle aynı.
    assert ' data-hedef="1" data-sinavda="1" data-cevrimdisi="1">' in kilit_formu(panel.get("/").text)[:120]
    # Çevrimiçi yokken eski ileti değişmedi.
    cevrimdisi_yap(1, 2)
    assert ileti(panel.post("/islem", data={"kapsam": "hepsi", "tur": "kilitle"})) == "Çevrimiçi tahta yok; komut gönderilmedi."


def test_tek_ve_liste_dallari_sinavdakine_bugunku_gibi_gider(panel, okul, monkeypatch):
    """V2 yalnız kapsam dalındadır: sınavdaki tahtaya tek tek ya da işaretli listeyle kilit 0.17.0'daki gibi gider."""
    sinava_al(monkeypatch, 2)
    assert ileti(panel.post("/islem", data={"tek": "kilitle:2"})) == "Kilitle: T-2 tahtasına gönderildi."
    assert ileti(panel.post("/islem", data={"tur": "kilitle", "tahta": ["2", "3"]})) == "Kilitle: 2 tahtaya gönderildi."
    assert komutlar() == [(2, "kilitle"), (2, "kilitle"), (3, "kilitle")]


def test_idareci_hepsini_kilitler(panel, okul):
    gir(panel, "idareci1")
    yanit = panel.post("/islem", data={"donus": "/", "kapsam": "hepsi", "tur": "kilitle"})
    assert ileti(yanit) == "Kilitle: 3 tahtaya gönderildi." and len(komutlar()) == 3


# ---- "/" ↔ "/tahtalar" -------------------------------------------------------------------------------------
def test_tahtalar_sayfasinda_tasinan_bantlar_yok(panel, tahta, okul, monkeypatch):
    from tahta_sunucu import guvenlik

    bekleyen_tahta(panel, tahta)
    surum_bildir()
    monkeypatch.setattr(guvenlik, "yerel_ipler", lambda: ["10.0.0.9"])
    panel.post("/ayarlar", data={"bolum": "adresler", "sunucu_adresleri": "https://10.0.0.5:8788"})
    with vt.islem() as b:
        b.execute("INSERT INTO duyuru (baslik, metin, sure_sn, kapatilabilir, hedef, olusturan, olusturma, durum) "
                  "VALUES ('D', 'm', 60, 1, '', 'x', ?, 'kacirildi')", (vt.simdi() - 60,))  # fmt: skip
    bugun_ = govde(panel.get("/").text)
    liste = govde(panel.get("/tahtalar").text)
    for metin in ("Yedek parolası belirlenmedi", "tahtalara bildirilen listede yok", "zamanlanmış duyuru kaçırıldı", "yayımlandı (kurulu sürüm"):
        assert metin in bugun_, metin
    for metin in TASINAN_BANT_METINLERI:
        assert metin not in liste, metin
    for yok in ('id="pano-program"', "data-yeni-surum", "data-altyapi-uyari", 'action="/program/istisna"', "github.com"):
        assert yok not in liste, yok
    # Listede kalanlar: onay bekleyen bandı, kilit kodu bandı, otomatik kapatma özeti, yenile bandı.
    assert 'id="onay-bekleyen"' in liste and "1 yeni tahta onay bekliyor." in liste
    assert "Kilit kodu tanımlı değil: kilitlenen tahta yalnız panelden açılır." in liste and 'href="/ayarlar/kilit"' in liste
    assert "otomatik kapatma: kapalı" in liste and 'id="yenile-bandi"' in liste
    assert not (KOK / "sablonlar" / "_pano_bantlar.html").exists()


def test_kok_eski_suzgec_adresi_listeye_yonlenir(panel, okul):
    def hedef(yol: str) -> str:
        yanit = panel.get(yol)
        assert yanit.status_code == 303, yol
        return yanit.headers["location"]

    assert hedef("/?durum=kilitli") == "/tahtalar?durum=kilitli"
    assert hedef("/?durum=bilinmeyen") == "/tahtalar"  # bilinmeyen süzgeç atılır
    assert hedef("/?s=2&m=Kilitle%3A%20T-2") == "/tahtalar?s=2&m=Kilitle%3A+T-2"
    assert hedef("/?durum=acik&s=2&m=x&t=hata&baska=1") == "/tahtalar?durum=acik&s=2&m=x&t=hata"
    assert hedef("/?s=bozuk") == "/tahtalar" and hedef("/?durum=acik&t=hata") == "/tahtalar?durum=acik"
    assert "Kilitle: T-2" in panel.get(hedef("/?s=2&m=Kilitle%3A%20T-2")).text
    assert panel.get("/?m=x").status_code == 200  # yalnız ileti: Bugün çizilir
    # Parça (#t-3) sunucuya gelmez: panel.js listeye taşır.
    assert 'location.replace("/tahtalar#t-" + eskiParca[1])' in BETIK
    panel.cookies.clear()
    assert panel.get("/?durum=kilitli").headers["location"] == "/giris"


def test_api_durum_bekleyen_is_eklemeli(panel, tahta, okul):
    bekleyen_tahta(panel, tahta)
    veri = panel.get("/api/durum").json()
    assert set(veri) == {"tahtalar", "bekleyen", "acil", "program", "bekleyen_is"} and veri["bekleyen"] == 1
    sayfa = panel.get("/").text
    assert veri["bekleyen_is"]["sayi"] == sayfa.count("<li data-is=")
    sayfa_verisi = json.loads(sayfa.split('id="bugun-veri" type="application/json">')[1].split("</script>")[0])
    assert veri["bekleyen_is"]["imza"] == sayfa_verisi["imza"] and "onay:1" in sayfa_verisi["imza"] and sayfa_verisi["bekleyen"] == 1
    assert f"· {veri['bekleyen_is']['sayi']} iş</span>" in sayfa
    gir(panel, "idareci1")
    idareci = panel.get("/api/durum").json()["bekleyen_is"]
    assert idareci["imza"] != veri["bekleyen_is"]["imza"] and "onay_i:1" in idareci["imza"] and "yeni_surum" not in idareci["imza"]
    assert idareci["sayi"] == panel.get("/").text.count("<li data-is=")
    # İmza yalnız anahtar ve sayıdır: metin, ad, adres taşımaz.
    assert re.fullmatch(r"[a-z_]+:\d+(,[a-z_]+:\d+)*", idareci["imza"])


# ---- V1: "Güncelleme var" rozeti ---------------------------------------------------------------------------
def test_guncelleme_rozeti_satirda_yok_hapta_ve_tahta_sayfasinda_var(panel, okul):
    liste = panel.get("/tahtalar").text
    satir = liste.split('<tr class="tahta-satir" id="t-1"')[1].split("</tr>")[0]
    assert "Güncelleme var" not in liste and "s-guncel" not in satir.split('data-alan="oturum"')[0]
    assert '<td class="c-surum eski" data-etiket="Sürüm" data-alan="surum">0.3.0<span class="gizli"> · güncelleme var</span></td>' in satir
    assert re.search(r'data-suzgec="guncelleme"[^>]*>Güncelleme <b>3</b>', liste) and 'data-durumlar="acik guncelleme"' in liste
    # Süzgeç ve API değişmedi: rozet API listesinde `liste: false` ile durur.
    assert 'data-durumlar="acik guncelleme"' in panel.get("/tahtalar?durum=guncelleme").text
    rozetler = panel.get("/api/durum").json()["tahtalar"][0]["liste"]["rozetler"]
    assert {"d": "guncelleme", "m": "Güncelleme var", "s": "s-guncel", "liste": False} in rozetler
    # Tahta sayfası (Genel › Ajan sürümü), menüdeki "Ajanı güncelle" ve Bugün (sayı kutusu + bekleyen iş satırı) durur.
    assert "Güncelleme var" in panel.get("/tahta/1").text and 'name="tek" value="guncelle:1"' in liste
    bugun_ = panel.get("/").text
    assert re.search(r'data-sayi="guncelleme"[^>]*>.*?<b>3</b>', bugun_, re.S) and "3 tahtada ajan güncellenebilir." in bugun_
    # Güncel tahtada hücre düz.
    with vt.islem() as b:
        b.execute("UPDATE tahta SET surum = ? WHERE id = 1", (paket.ajan_paketi().surum,))
    guncel = panel.get("/tahtalar").text.split('<tr class="tahta-satir" id="t-1"')[1].split("</tr>")[0]
    assert f'<td class="c-surum" data-etiket="Sürüm" data-alan="surum">{paket.ajan_paketi().surum}</td>' in guncel


def test_program_ajani_eski_rozeti_satirda_kalir(uygulama, panel, tahta):
    """Program kilidi açıkken program yeteneği olmayan (eski) ajanın "Ajan güncellenmeli" rozeti satırda KALIR."""
    hazirla(panel)
    tahta_ekle(panel, tahta, "T-1", yeni_ajan_durumu(oturum={"sinif": "ogretmen"}), surum="0.3.0")
    satir = panel.get("/tahtalar").text.split('<tr class="tahta-satir" id="t-1"')[1].split("</tr>")[0]
    assert "Ajan güncellenmeli" in satir and "Güncelleme var" not in satir
    rozet = [r for r in panel.get("/api/durum").json()["tahtalar"][0]["liste"]["rozetler"] if r["m"] == "Ajan güncellenmeli"]
    assert rozet and "liste" not in rozet[0]


# ---- stil ve betik -----------------------------------------------------------------------------------------
def test_stil_ve_betik_bugun_kancalari():
    onay = BETIK.split("var ONAY = {")[1].split("\n  };")[0]
    assert 'hepsini_kilitle: {\n      ad: "tur", deger: "kilitle", evet: "Hepsini kilitle",' in onay
    assert "function bugunKur()" in BETIK and "\n  bugunKur();\n" in BETIK
    assert "function durumYoklayici(" in BETIK and "function canliGostergesi(" in BETIK and "function programYazici(" in BETIK
    for olu in ("seritDonus", "seritYaz", "pano-program"):
        assert olu not in BETIK, olu
    # "Hepsini kilitle…" ayrı daldır: data-tek ve seçili satır dallarından ÖNCE döner; sayılar formun özniteliklerinden.
    dal = BETIK.split('tetik.getAttribute("data-onay") === "hepsini_kilitle"')[1].split("// data-tek (satır menüsü)")[0]
    for parca in ('form.getAttribute("data-hedef")', 'form.getAttribute("data-sinavda")', 'form.getAttribute("data-cevrimdisi")',
                  "if (!kilitHedef) {", "tahta sınav kipinde; atlanacak.", "tahta çevrimdışı; onlara gönderilmez.",
                  "ac(form, tanim.baslik(kilitHedef), tanim.metin, tanim.ad, tanim.deger, tanim.evet);\n          return;"):  # fmt: skip
        assert parca in dal, parca
    assert "pano.seciliSatirlar" not in dal and "liste.appendChild" not in dal  # tahta adı listelenmez
    assert dal.index("if (!kilitHedef) {") < dal.index("ac(form")
    # Kip ve eşik CSS'tedir: Bugün betiğinde genişlik eşiği yok; innerHTML hiç yok.
    bugun_js = BETIK.split("function bugunKur")[1].split("// Tahta sayfasının eski parça adresleri")[0]
    for yasak in ("innerWidth", "matchMedia", "--kb-kip", "rem", "innerHTML", "localStorage"):
        assert yasak not in bugun_js, yasak
    blok = STIL.split("/* ---- 0.18.0: Bugün")[1].split("/* ---- 0.18.0 sonu ---- */")[0]
    assert "@layer bilesen {" in blok and "@layer kabuk" not in blok
    for secici in (".bugun-izgara", ".an-kilit", ".akis li.simdi", ".is-listesi li", ".durum-ozet a", ".harita-kat", ".cip {", ".olay-listesi li"):
        assert secici in blok, secici
    assert "@media (min-width: 85rem) {\n    .bugun-izgara {" in blok  # eşik görüntü alanına göre (sabit menü 15rem)
    # Yeni renk kodu ve yasak ad yok; yapışkan öğe ve gövde taşması yok.
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", blok) and "position: sticky" not in blok
    for ad in re.findall(r"(--[a-z0-9-]+)\s*:", blok):
        assert not ad.endswith(("-a", "-k")) and not ad.startswith("--t-"), ad
    assert not re.search(r"\b(body|html|main)\s*\{[^}]*(overflow|block-size)", blok)
    assert ".cip, .harita-ad { min-block-size: var(--dokunma); }" in blok  # dar ekranda 44 px


def test_bugun_sablonlari_satir_ici_stil_ve_betik_tasimaz():
    for ad in ("bugun.html", "_bugun.html"):
        metin = (KOK / "sablonlar" / ad).read_text(encoding="utf-8")
        assert "style=" not in metin and "<style" not in metin and not re.search(r"\son[a-z]+=", metin), ad
        for etiket in re.findall(r"<script\b[^>]*>", metin):
            assert 'type="application/json"' in etiket, (ad, etiket)
        assert not re.search(r"<p[^>]*>\s*<form", metin), ad
    sablon = (KOK / "sablonlar" / "bugun.html").read_text(encoding="utf-8")
    liste = sablon.split('id="bekleyenler"')[1].split("</section>")[0]
    assert "kullanici.rol" not in liste and "yonetici" not in liste  # rol süzmesi sunucuda (bugun.bekleyenler)
    assert "pano" not in sablon.lower()


# ---- inceleme düzeltmeleri (0.18.0) ------------------------------------------------------------------------
def test_yedek_hatasinin_ham_metni_ve_yolu_sayfada_yok(panel, okul):
    """Ham istisna metni (sunucu yolu, ikinci kopya klasörü) iki rolde de Bugün'e ve /api/durum'a çıkmaz."""
    gizli = ("PermissionError", "Errno", "Uydurma", "tkyedek", "ProgramData", "ag-diski", "WinError")
    with vt.islem() as b:
        vt.ayar_yaz(b, "yedek", {"acik_anahtar": "x", "parola_zamani": vt.simdi()})
    for son, metin in (
        ({"basarili": False, "son_basarili": 0, "hata": "PermissionError: [Errno 13] Permission denied: 'C:/ProgramData/Uydurma/x.tkyedek'"},
         "Son yedek alınamadı (henüz başarılı yedek yok)."),
        ({"basarili": True, "son_basarili": vt.simdi(), "kopya_hata": "FileNotFoundError: [WinError 3] '//ag-diski/Uydurma/yedek'"},
         "Yedeğin ikinci kopyası yazılamadı."),
    ):  # fmt: skip
        with vt.islem() as b:
            vt.ayar_yaz(b, "son_yedek", son)
        for rol in ("yonetici", "idareci1"):
            gir(panel, rol)
            sayfa = panel.get("/").text
            kutu = bolum(sayfa, "bekleyenler")
            assert metin in kutu, (rol, metin)
            assert ("Ayrıntı Yedekler sayfasında." in kutu) == (rol == "yonetici") and ("Yöneticiye bildirin." in kutu) == (rol != "yonetici")
            assert ('href="/yedekler"' in kutu) == (rol == "yonetici")
            for parca in gizli:
                assert parca not in sayfa and parca not in panel.get("/api/durum").text, (rol, parca)
        gir(panel, "yonetici")


def test_durum_kutulari_telefon_kopyasi_ayni_sayilar(panel, okul):
    """Telefonda tahta durumu ilk ekranda kalsın diye sayı kutuları "Şu an"ın hemen altında da çizilir; ikisi aynıdır."""
    cevrimdisi_yap(3)
    sayfa = govde(panel.get("/").text)
    kisa = sayfa.split('id="bugun-ozet-kisa"')[1].split("</nav>")[0]
    kart = sayfa.split('id="bugun-ozet">')[1].split("</div>")[0]
    assert kisa.split(">", 1)[1] == kart and kart.count("data-sayi=") == 6
    assert sayfa.index('id="bugun-simdi"') < sayfa.index('id="bugun-ozet-kisa"') < sayfa.index('id="bekleyenler"')
    blok = STIL.split("/* ---- 0.18.0: Bugün")[1].split("/* ---- 0.18.0 sonu ---- */")[0]
    assert ".durum-ozet.kisa { display: none;" in blok  # geniş ekranda yalnız karttaki
    dar = blok.split("@media (max-width: 39.99rem) {")[1].split("\n  }")[0]
    assert ".durum-ozet.kisa { display: grid; }" in dar and "#bugun-ozet { display: none; }" in dar
    assert ".bugun-eylem { display: none; }" not in blok and ".an-gun { display: none; }" not in blok  # telefonda da görünür
    assert ".akis-saat { display: none; }" in blok and "@media (min-width: 48rem) { .an-akis { flex-basis: 22rem; } .akis-saat { display: block; } }" in blok
    assert "text-overflow" not in blok.split(".durum-ozet span {")[1].split("}")[0]  # "Ekran sorunu" kesilmez, sarar
    assert '.durum-ozet a[data-sayi="guncelleme"] { border-style: dashed; }' in blok
    # Canlı tazeleme iki kopyaya da yazar.
    assert 'document.querySelectorAll("#bugun-ozet a[data-sayi], #bugun-ozet-kisa a[data-sayi]")' in BETIK


def test_cip_ek_isaretleri_durum_simgesinden_ayri_ve_lejantli(panel, okul, monkeypatch):
    """Arıza eki "ekran sorunu" üçgeniyle, sınav eki onay dairesiyle aynı şekil değildir; lejant gören kullanıcıya açıklar."""
    panel.post("/arizalar", data={"tahta_id": "1", "kategori": "acilis", "aciklama": ""})
    sinava_al(monkeypatch, 2)
    sayfa = panel.get("/").text
    kart = bolum(sayfa, "bugun-tahtalar")
    harita = kart.split('class="harita"')[1].split('id="cip-lejant"')[0]
    assert re.search(r'data-id="1".*?<span class="cip-ek" data-durum="sorun"><svg class="simge" aria-hidden="true"><use href="#s-ariza"/>', harita, re.S)
    assert re.search(r'data-id="2".*?<span class="cip-ek" data-durum="uyari"><svg class="simge" aria-hidden="true"><use href="#m-sinav"/>', harita, re.S)
    assert harita.count('href="#s-sorun"') == 0 and harita.count('href="#s-onay"') == 0  # ek işaret durum simgesi değil
    lejant = kart.split('id="cip-lejant"')[1].split("</p>")[0]
    assert '<use href="#s-ariza"/></svg>açık arıza kaydı' in lejant and '<use href="#m-sinav"/></svg>sınav kipinde' in lejant
    assert '<symbol id="s-ariza"' in sayfa and '<symbol id="m-sinav"' in sayfa
    assert 'simge(e === "ariza" ? "s-ariza" : "m-sinav")' in BETIK  # canlı tazeleme aynı şekilleri yazar


def test_canli_gostergesi_betiksiz_gizli_ve_acilde_toplu_kilit_kapanir(panel, okul):
    sayfa = panel.get("/").text
    # JS'siz sayfa "Canlı" demez (sayılar tazelenmez); gösterge betikle açılır.
    assert '<span class="canli" id="canli" data-durum="cevrimici" hidden>' in sayfa
    bugun_js = BETIK.split("function bugunKur")[1].split("// Tahta sayfasının eski parça adresleri")[0]
    assert "if (canliEl) canliEl.hidden = false;" in bugun_js
    # Sayfa açıkken acil başlarsa: düğme kapanır, not yazılır, bant acili söyler (genel "bekleyen işler" sözü değil).
    for parca in ("if (dugme) dugme.disabled = suruyor;", '"Acil yayın sürüyor; toplu kilit kapalı."', '"Acil yayın başladı."',
                  '"Acil yayın bitti."', "acilYaz(!!v.acil);"):  # fmt: skip
        assert parca in bugun_js, parca
    assert '<span data-alan="yenile-metni">Bekleyen işler değişti.</span> <a href="/">Sayfayı yenile</a>' in sayfa
    assert '<span class="not" id="kilit-notu" role="status"></span>' in sayfa
    # Program kilidi rozetinin canlı metni şablondakiyle aynı sözcükleri kullanır.
    assert 'return "Program kilidi etkin"; }]' in BETIK and "Program kilidi açık" not in BETIK
    for ad in ("bugun.html", "_program_bas.html"):
        sablon = (KOK / "sablonlar" / ad).read_text(encoding="utf-8")
        assert "Program kilidi etkin</span>" in sablon and "Program kilidi açık" not in sablon, ad


def test_program_kilidi_durdurulunca_geri_alma_baglantisi(uygulama, panel, tahta, saat):
    hazirla(panel)
    saat.ayarla(an(16, 9, 15))
    tahta_ekle(panel, tahta, "T-1", program_durumu())
    kart = bolum(panel.get("/").text, "bugun-simdi")
    assert re.search(r'data-alan="istisnalar" href="/program\?bolum=istisnalar" hidden>Geri al \(İstisnalar\)</a>', kart)
    panel.post("/program/istisna", data={"sure": "1sa", "donus": "/"})
    kart = bolum(panel.get("/").text, "bugun-simdi")
    assert 'data-alan="istisnalar" href="/program?bolum=istisnalar">Geri al (İstisnalar)</a>' in kart


def test_api_durum_kurulum_satirini_bellekten_alir(panel, okul, monkeypatch):
    """Canlı tazeleme `kurulum` üreticisini her 4 sn'de çalıştırmaz; Bugün her yüklemede taze hesaplar ve belleği yeniler."""
    from tahta_sunucu import ayar_bolumleri

    sayfa = panel.get("/").text
    imza = json.loads(sayfa.split('id="bugun-veri" type="application/json">')[1].split("</script>")[0])["imza"]
    assert "kurulum:" in imza
    asil = ayar_bolumleri.kurulum
    cagri = []
    monkeypatch.setattr(ayar_bolumleri, "kurulum", lambda *a, **k: (cagri.append(1), asil(*a, **k))[1])
    for _ in range(3):
        assert panel.get("/api/durum").json()["bekleyen_is"]["imza"] == imza
    assert cagri == []  # bellekten
    panel.get("/")
    assert len(cagri) == 1  # sayfa taze hesaplar
    gir(panel, "idareci1")  # idarecide kurulum satırı hiç yok; bellek ona sızmaz
    assert "kurulum" not in panel.get("/api/durum").json()["bekleyen_is"]["imza"] and len(cagri) == 1


def test_bugun_menu_rozetini_ayni_listeden_cizer(panel, tahta, okul, monkeypatch):
    """Bugün tam listeyi zaten hesaplar: menü rozeti için `yalniz_rozet` ikinci kez çalışmaz, sayılar yine aynıdır."""
    bekleyen_tahta(panel, tahta)
    panel.post("/arizalar", data={"tahta_id": "1", "kategori": "acilis", "aciklama": ""})
    asil = bugun.bekleyenler
    cagri = []
    monkeypatch.setattr(bugun, "bekleyenler", lambda *a, **k: (cagri.append(k.get("yalniz_rozet", False)), asil(*a, **k))[1])
    sayfa = panel.get("/").text
    assert cagri == [False]
    assert '<span>Tahtalar</span><span class="sayi-rozet">2</span>' in sayfa and '<span>Yedekler</span><span class="sayi-rozet">1</span>' in sayfa
    cagri.clear()
    assert '<span>Tahtalar</span><span class="sayi-rozet">2</span>' in panel.get("/tahtalar").text and cagri == [True]
