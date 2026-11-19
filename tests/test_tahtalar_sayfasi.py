"""Tahtalar listesi ve /islem (0.17.0, panel arayüzü 3. aşama): komut güvenliği (`tek`, `kapsam`), süzgeç, seçim
çubuğu, rol görünürlüğü, /api/durum sözleşmesi, sekme şeridi. Uydurma veriyle."""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest
from yardimci import (
    gir,
    ileti,
    kimlik,
    komut_verisi,
    kullanici_ekle,
    kur_ve_gir,
    sorgu,
    tahta_ekle,
    yeni_ajan_durumu,
)

from tahta_sunucu import ayar, paket, tahta_liste, vt
from tahta_sunucu.komut import KOMUT_ADI, KOMUT_OMRU

KOK = Path(__file__).resolve().parent.parent / "tahta_sunucu"
STIL = (KOK / "statik" / "stil.css").read_text(encoding="utf-8")
BETIK = (KOK / "statik" / "panel.js").read_text(encoding="utf-8")
ONAY_ANAHTARLARI = set(re.findall(r"^    ([a-z_]+): \{\n      ad: ", BETIK.split("var ONAY = {")[1].split("\n  };")[0], re.M))
SERIT_SAYFALARI = ("/tahtalar", "/arizalar", "/envanter", "/gruplar", "/tahtalar/ice-aktar", "/ekle")


def komutlar() -> list[tuple[int, str]]:
    return [(k["tahta_id"], k["tur"]) for k in sorgu("SELECT tahta_id, tur FROM komut ORDER BY id")]


def cevrimdisi_yap(*idler) -> None:
    with vt.islem() as b:
        for i in idler:
            b.execute("UPDATE tahta SET son_gorulme = ? WHERE id = ?", (vt.simdi() - 10 * ayar.CEVRIMICI_ESIK_SN, i))


def bekleyen_ekle(panel, tahta, makine="etap-yeni") -> int:
    panel.post("/ekle", data={"eylem": "ac"})
    kod = panel.get("/ekle").text.split('class="buyuk-kod">')[1].split("<")[0]
    return tahta.post("/ajan/kaydol", json={"kod": kod, "makine_adi": makine, "surum": "0.17.0"}).json()["tahta_id"]


def satir(sayfa: str, tahta_id: int) -> str:
    return sayfa.split(f'<tr class="tahta-satir" id="t-{tahta_id}"')[1].split("</tr>")[0]


def satir_ozniteligi(sayfa: str, tahta_id: int) -> str:
    return re.search(rf'<tr class="tahta-satir" id="t-{tahta_id}"[^>]*>', sayfa).group(0)


@pytest.fixture()
def okul(panel, tahta):
    """Üç onaylı tahta (1, 2, 3; hepsi çevrimiçi), bir idareci hesabı."""
    kur_ve_gir(panel)
    kullanici_ekle(panel, "idareci1")
    return [kimlik(tahta_ekle(panel, tahta, ad, yeni_ajan_durumu())) for ad in ("T-1", "T-2", "T-3")]


# ---- komut güvenliği: /islem -------------------------------------------------------------------------------
def test_tek_ile_isaretli_liste_birlikte_yalniz_tek_uygulanir(panel, okul):
    yanit = panel.post("/islem", data={"tek": "kilitle:2", "tahta": ["1", "2", "3"], "tur": "kapat", "donus": "/tahtalar"})
    assert komutlar() == [(2, "kilitle")]
    assert ileti(yanit) == "Kilitle: T-2 tahtasına gönderildi."


def test_tek_formdaki_tur_alanini_ezer(panel, okul):
    for tur in ("kapat", "yeniden_baslat", "temizlik", "duyuru", "bilinmeyen"):
        panel.post("/islem", data={"tek": "kilit_ac:3", "tur": tur, "tahta": ["1", "2"]})
    assert komutlar() == [(3, "kilit_ac")] * 5


def test_tek_bilinmeyen_tur_reddedilir_ve_listeye_dusulmez(panel, okul):
    for bozuk in ("sil:2", "kapat", ":2", "kilitle:2:3", "", "kilitle:x", "kilitle:2;kapat:1", "kapat:2 "):
        yanit = panel.post("/islem", data={"tek": bozuk, "tur": "kilitle", "tahta": ["1", "2", "3"], "donus": "/tahtalar"})
        assert ileti(yanit) == "Bilinmeyen işlem." and "t=hata" in yanit.headers["location"], bozuk
    assert komutlar() == [] and not sorgu("SELECT 1 FROM kayit WHERE islem IN ('Kilitle', 'Kapat')")


def test_tek_bilinmeyen_onaysiz_ve_iptal_kimlik_reddedilir(panel, tahta, okul):
    bekleyen = bekleyen_ekle(panel, tahta)
    panel.post("/tahta/3/kaydet", data={"ad": "T-3", "eylem": "sil"})  # iptal
    for hedef in (99, bekleyen, 3, 9999999999):
        yanit = panel.post("/islem", data={"tek": f"kilitle:{hedef}", "tahta": ["1", "2"], "tur": "kilitle"})
        assert ileti(yanit) == "Tahta bulunamadı." and "t=hata" in yanit.headers["location"], hedef
    # Biçim tam tutmalı: sondaki satır sonu, baştaki sıfır ve 0 kimliği de reddedilir (listeye düşülmez).
    for bozuk in ("kilitle:1\n", "kilitle:01", "kilitle:0", "kilitle:1 "):
        yanit = panel.post("/islem", data={"tek": bozuk, "tahta": ["1", "2"], "tur": "kilitle"})
        assert ileti(yanit) == "Bilinmeyen işlem." and "t=hata" in yanit.headers["location"], repr(bozuk)
    assert komutlar() == []


def test_tek_duyuru_ve_temizlik_reddedilir(panel, okul):
    yanit = panel.post("/islem", data={"tek": "duyuru:1", "metin": "Deneme", "tahta": ["1"]})
    assert ileti(yanit) == "Bilinmeyen işlem."
    yanit = panel.post("/islem", data={"tek": "temizlik:1", "tahta": ["1"]})
    assert ileti(yanit) == "Oturum temizliği tahta sayfasından başlatılır."
    assert komutlar() == [] and not sorgu("SELECT 1 FROM duyuru")


def test_tek_birden_cok_deger_reddedilir(panel, okul):
    yanit = panel.post("/islem", data={"tek": ["kilitle:1", "kilitle:2"]})
    assert ileti(yanit) == "Geçersiz istek." and komutlar() == []


def test_tek_envanter_yetenegi_olmayan_tahtada_bugunku_ileti(panel, okul):
    yanit = panel.post("/islem", data={"tek": "envanter:1", "donus": "/tahta/1?sekme=bakim#envanter"})
    assert ileti(yanit).startswith("Seçilen tahtaların ajanı envanter göndermiyor") and komutlar() == []
    assert yanit.headers["location"].startswith("/tahta/1?sekme=bakim&m=") and yanit.headers["location"].endswith("#envanter")


def test_tek_uyandir_komut_yazmaz(panel, okul):
    yanit = panel.post("/islem", data={"tek": "uyandir:1", "tahta": ["2", "3"]})
    assert "MAC adresi bilinmiyor" in ileti(yanit) and "T-1" in ileti(yanit) and "T-2" not in ileti(yanit)
    assert komutlar() == []
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Uzaktan aç'")[-1]["ayrinti"] == "1 tahta: T-1"


def test_kapsam_hepsi_cevrimdisi_ve_onaysizi_atlar(panel, tahta, okul):
    dorduncu = kimlik(tahta_ekle(panel, tahta, "T-4", yeni_ajan_durumu()))
    bekleyen = bekleyen_ekle(panel, tahta)
    panel.post(f"/tahta/{dorduncu}/kaydet", data={"ad": "T-4", "eylem": "sil"})  # iptal
    cevrimdisi_yap(3)
    yanit = panel.post("/islem", data={"kapsam": "hepsi", "tur": "kilitle", "donus": "/"})
    assert komutlar() == [(1, "kilitle"), (2, "kilitle")]
    assert ileti(yanit) == "Kilitle: 2 tahtaya gönderildi. 1 çevrimdışı tahtaya gönderilmedi."
    assert bekleyen not in {k[0] for k in komutlar()}


def test_kapsam_hepsi_yalniz_kilitle(panel, okul):
    for tur in ("kapat", "yeniden_baslat", "kilit_ac", "guncelle", "duyuru", "temizlik", "tani", "uyandir", "", "x"):
        yanit = panel.post("/islem", data={"kapsam": "hepsi", "tur": tur, "metin": "Deneme"})
        assert ileti(yanit) == "Bu işlem bütün tahtalara birden verilemez." and "t=hata" in yanit.headers["location"], tur
    assert komutlar() == [] and not sorgu("SELECT 1 FROM duyuru")


def test_kapsam_tek_ya_da_liste_ile_birlikte_reddedilir(panel, okul):
    for ek in ({"tek": "kilitle:1"}, {"tahta": ["1"]}, {"tahta": ["1", "2", "3"]}, {"tahta": ["yok"]}):
        yanit = panel.post("/islem", data={"kapsam": "hepsi", "tur": "kilitle", **ek})
        assert ileti(yanit) == "Geçersiz istek.", ek
    assert komutlar() == []


def test_kapsam_bilinmeyen_deger_reddedilir(panel, okul):
    for deger in ("", "tumu", "Hepsi", "secili", "1"):
        yanit = panel.post("/islem", data={"kapsam": deger, "tur": "kilitle"})
        assert ileti(yanit) == "Geçersiz istek.", deger
    assert komutlar() == []


def test_kapsam_hepsi_cevrimici_yoksa_komut_yok(panel, okul):
    cevrimdisi_yap(1, 2, 3)
    yanit = panel.post("/islem", data={"kapsam": "hepsi", "tur": "kilitle"})
    assert ileti(yanit) == "Çevrimiçi tahta yok; komut gönderilmedi." and "t=hata" in yanit.headers["location"]
    assert komutlar() == [] and not sorgu("SELECT 1 FROM kayit WHERE islem = 'Kilitle'")


def test_islem_kaydi_tek_ve_kapsam(panel, okul):
    panel.post("/islem", data={"tek": "tani:2", "tahta": ["1"]})
    panel.post("/islem", data={"kapsam": "hepsi", "tur": "kilitle"})
    panel.post("/islem", data={"tur": "kilit_ac", "tahta": ["1", "3"]})
    kayitlar = [(k["kullanici"], k["islem"], k["ayrinti"]) for k in sorgu("SELECT * FROM kayit WHERE islem IN ('Tanılama', 'Kilitle', 'Kilidi aç') ORDER BY id")]
    assert kayitlar == [
        ("yonetici", "Tanılama", "1 tahta: T-2"),
        ("yonetici", "Kilitle", "bütün çevrimiçi tahtalar · 3 tahta: T-1, T-2, T-3"),
        ("yonetici", "Kilidi aç", "2 tahta: T-1, T-3"),
    ]


def test_islem_donus_adresi_suzgeci_ve_satir_capasini_korur(panel, okul):
    yanit = panel.post("/islem", data={"tek": "kilitle:2", "donus": "/tahtalar?durum=kilitli"})
    adres = yanit.headers["location"]
    assert adres.startswith("/tahtalar?durum=kilitli&s=2&m=Kilitle") and adres.endswith("#t-2") and "t=hata" not in adres
    # 0.18.0: "/" Bugün'dür; oraya dönen tek komuta satır çapası ve s= EKLENMEZ (ileti Bugün'ün başında çıkar).
    kok = panel.post("/islem", data={"tek": "kilitle:2", "donus": "/"}).headers["location"]
    assert kok.startswith("/?m=Kilitle") and "#" not in kok and "s=2" not in kok
    # Liste dışı dönüşe ve zaten parça taşıyan adrese çapa eklenmez; liste dalında da eklenmez.
    assert "#" not in panel.post("/islem", data={"tek": "kilitle:2", "donus": "/tahta/2?sekme=bakim"}).headers["location"]
    assert panel.post("/islem", data={"tek": "kilitle:2", "donus": "/tahtalar#ust"}).headers["location"].endswith("#ust")
    assert "#" not in panel.post("/islem", data={"tur": "kilitle", "tahta": ["2"], "donus": "/tahtalar"}).headers["location"]
    # Varsayılan dönüş /tahtalar'dır.
    assert panel.post("/islem", data={"tur": "kilitle", "tahta": ["2"]}).headers["location"].startswith("/tahtalar?m=")


def test_islem_donus_cift_egik_cizgi_reddedilir(panel, okul):
    for kotu in ("//ornek.invalid/x", "/\\ornek.invalid", "https://ornek.invalid", "javascript:alert(1)", "tahtalar"):
        for veri in ({"tek": "kilitle:1"}, {"tur": "kilitle", "tahta": ["1"]}, {"tur": "bilinmeyen", "tahta": ["1"]}, {"tur": "kilitle"}):
            adres = panel.post("/islem", data={**veri, "donus": kotu}).headers["location"]
            assert re.match(r"/tahtalar\?(s=1&)?m=", adres) and "ornek.invalid" not in adres, (kotu, veri)


def test_islem_hata_donusu_donus_adresine_gider(panel, okul):
    donus = "/tahta/1?sekme=bakim"
    for veri in ({"tur": "kilitle"}, {"tur": "bilinmeyen", "tahta": ["1"]}, {"tur": "kilitle", "tahta": ["99"]}, {"tek": "kilitle:99"},
                 {"tek": "bozuk"}, {"kapsam": "x", "tur": "kilitle"}, {"tur": "temizlik", "tahta": ["1"]}):  # fmt: skip
        adres = panel.post("/islem", data={**veri, "donus": donus}).headers["location"]
        assert adres.startswith("/tahta/1?sekme=bakim&m=") and adres.endswith("&t=hata"), veri
    assert komutlar() == []


def test_islem_komut_omurleri_degismedi(panel, okul):
    panel.post("/islem", data={"tek": "kapat:1"})
    panel.post("/islem", data={"tek": "kilitle:1"})
    panel.post("/islem", data={"tek": "tani:1"})
    panel.post("/islem", data={"kapsam": "hepsi", "tur": "kilitle"})
    panel.post("/islem", data={"tur": "yeniden_baslat", "tahta": ["2"]})
    omurler = [(k["tur"], k["bitis"] - k["olusturma"]) for k in sorgu("SELECT * FROM komut ORDER BY id")]
    assert omurler == [("kapat", 120), ("kilitle", 600), ("tani", 86400), ("kilitle", 600), ("kilitle", 600), ("kilitle", 600), ("yeniden_baslat", 120)]
    assert all(omur == KOMUT_OMRU[tur] for tur, omur in omurler)


def test_islem_program_kaynakli_veri_yazmaz(panel, okul):
    # Eski ajana program komutu gitmez kuralının gerilemesi: /islem hiçbir komuta kaynak=program koymaz.
    for veri in ({"tek": "kilitle:1"}, {"tek": "kilit_ac:1"}, {"kapsam": "hepsi", "tur": "kilitle"}, {"tur": "kilit_ac", "tahta": ["1", "2"]}):
        panel.post("/islem", data=veri)
    assert len(komutlar()) == 7
    assert all(komut_verisi(k) == {} for k in sorgu("SELECT veri_json FROM komut"))
    panel.post("/islem", data={"tek": "guncelle:1"})
    assert set(komut_verisi(sorgu("SELECT veri_json FROM komut ORDER BY id DESC LIMIT 1")[0])) == {"sha256", "surum"}


def test_islem_oturumsuz_komut_yazmaz(panel, okul):
    panel.cookies.clear()
    for veri in ({"tek": "kilitle:1"}, {"kapsam": "hepsi", "tur": "kilitle"}, {"tur": "kapat", "tahta": ["1"]}):
        assert panel.post("/islem", data=veri).headers["location"] == "/giris"
    assert komutlar() == []


def test_idareci_de_tek_ve_kapsam_komutu_verir(panel, okul):
    gir(panel, "idareci1")
    assert ileti(panel.post("/islem", data={"tek": "kilitle:1"})) == "Kilitle: T-1 tahtasına gönderildi."
    assert ileti(panel.post("/islem", data={"kapsam": "hepsi", "tur": "kilitle"})) == "Kilitle: 3 tahtaya gönderildi."
    assert len(komutlar()) == 4


# ---- liste ve şablon ---------------------------------------------------------------------------------------
def test_durum_suzgeci_js_siz(panel, tahta, okul):
    with vt.islem() as b:  # 2: kilitli; 3: çevrimdışı
        b.execute("""UPDATE tahta SET durum_json = '{"kilitli": true, "ekranlar": [{"arayuz": "gtk3"}]}' WHERE id = 2""")
    cevrimdisi_yap(3)
    beklenen = {"": {1, 2, 3}, "acik": {1}, "kilitli": {2}, "cevrimdisi": {3}, "duyuru": set(), "sorun": set(), "ariza": set()}
    for deger, gorunen in beklenen.items():
        sayfa = panel.get("/tahtalar" + (f"?durum={deger}" if deger else "")).text
        for i in (1, 2, 3):
            oz = satir_ozniteligi(sayfa, i)
            kutu = re.search(rf'<input type="checkbox" name="tahta" value="{i}"[^>]*>', sayfa).group(0)
            assert (" hidden" not in oz) == (i in gorunen), (deger, i)
            assert ("disabled" not in kutu) == (i in gorunen), (deger, i)  # gizli satır forma girmez
        # Sayılar süzgeçten bağımsızdır.
        haplar = sayfa.split('id="haplar"')[1].split("</nav>")[0]
        assert re.findall(r"<b>(\d+)</b>", haplar)[:3] == ["3", "1", "1"], deger
        assert haplar.count('aria-current="true"') == 1
        etkin = re.search(r'<a class="hap[^"]*" href="([^"]+)"[^>]*aria-current="true"', haplar).group(1)
        assert etkin == "/tahtalar" + (f"?durum={deger}" if deger else "")
        assert f'name="donus" value="{etkin}"' in sayfa
        assert ('id="suzgec-bos" hidden' not in sayfa) == (not gorunen), deger
    # Geçersiz değer = Hepsi; değer HTML'e yansımaz.
    sayfa = panel.get('/tahtalar?durum=%22%3E%3Cscript%3Ealert(1)%3C/script%3E').text
    assert "alert(1)" not in sayfa and 'name="donus" value="/tahtalar"' in sayfa and sayfa.count('<tr class="tahta-satir"') == 3
    assert not re.search(r'<tr class="tahta-satir"[^>]* hidden', sayfa)
    assert "durum=acil_ekranda" not in panel.get("/tahtalar?durum=acil_ekranda").text


def test_panodaki_her_komut_yeni_listede_var(panel, okul):
    sayfa = panel.get("/tahtalar").text
    cubuk = sayfa.split('id="secim-cubugu"')[1].split('<noscript>')[0]
    assert set(re.findall(r'<button type="submit" name="tur" value="([a-z_]+)"', cubuk)) == {"kilitle", "kilit_ac", "duyuru_kaldir", "tani", "guncelle"}
    assert set(re.findall(r'<button type="button" class="tehlike" data-onay="([a-z_]+)"', cubuk)) == {"kapat", "yeniden_baslat"}
    assert cubuk.count('formmethod="get" formaction="/duyurular/yeni"') == 2  # geniş ekranda düğme, dar ekranda Diğer'in ilk öğesi
    assert 'name="tur" value="duyuru"' not in sayfa and 'name="metin"' not in sayfa
    # Satır menüsü: aynı komut kümesi + uzaktan aç; hepsi tek=<tur>:<id> ile.
    with vt.islem() as b:  # her komut etkin görünsün: kilitli, duyurulu, sürümü eski, çevrimiçi → yalnız uzaktan aç pasif
        b.execute("""UPDATE tahta SET surum = '0.1.0', durum_json = '{"kilitli": true, "duyuru_var": true, "ekranlar": [{"arayuz": "gtk3"}]}' WHERE id = 1""")
    menu = satir(panel.get("/tahtalar").text, 1)
    assert set(re.findall(r'name="tek" value="([a-z_]+):1"', menu)) == {"kilitle", "kilit_ac", "duyuru_kaldir", "tani", "guncelle"}
    assert set(re.findall(r'data-onay="([a-z_]+)" data-tek="\1:1"', menu)) == {"kapat", "yeniden_baslat"}
    assert 'href="/duyurular/yeni?tahta=1"' in menu and 'href="/tahta/1"' in menu
    cevrimdisi_yap(1)
    assert 'name="tek" value="uyandir:1"' in satir(panel.get("/tahtalar").text, 1)
    # Her komut türü (duyuru ve tahta sayfasına özgü temizlik/envanter dışında) listede en az bir yoldan verilebilir.
    hepsi = panel.get("/tahtalar").text
    for tur in set(KOMUT_ADI) - {"duyuru", "temizlik", "envanter"}:
        assert f'value="{tur}"' in hepsi or f'value="{tur}:' in hepsi or f'data-onay="{tur}"' in hepsi, tur


def test_satir_birincil_dugmesi_ve_menu_pasifligi(panel, okul):
    with vt.islem() as b:
        b.execute("""UPDATE tahta SET durum_json = '{"kilitli": true, "ekranlar": [{"arayuz": "gtk3"}]}' WHERE id = 2""")
        b.execute("UPDATE tahta SET surum = ? WHERE id = 1", (paket.ajan_paketi().surum,))
    cevrimdisi_yap(3)
    sayfa = panel.get("/tahtalar").text
    birincil = {i: re.search(r'<span class="birincil" data-alan="dugme">(.*?)</span><details', satir(sayfa, i), re.S).group(1) for i in (1, 2, 3)}
    assert 'name="tek" value="kilitle:1"' in birincil[1] and "Kilitle" in birincil[1] and "(T-1)" in birincil[1]
    assert 'name="tek" value="kilit_ac:2"' in birincil[2] and "Kilidi aç" in birincil[2]
    assert birincil[3].strip() == ""  # çevrimdışı: birincil düğme yok, menü durur
    assert all(b_.count("<button") <= 1 for b_ in birincil.values())
    # Pasif öğe name/value taşımaz, gerekçesi yazar.
    pasifler = re.findall(r"<button[^>]*disabled[^>]*>.*?</button>", satir(sayfa, 1), re.S)
    assert len(pasifler) == 4 and all(" name=" not in p and " value=" not in p for p in pasifler)
    metin = " ".join(pasifler)
    for gerekce in ("kilitli değil", "ekranda duyuru yok", f"güncel ({paket.ajan_paketi().surum})", "tahta açık"):
        assert gerekce in metin, gerekce
    kapali = re.findall(r"<button[^>]*disabled[^>]*>.*?</button>", satir(sayfa, 3), re.S)
    assert len(kapali) == 2 and all('type="button"' in p and "çevrimdışı" in p for p in kapali)
    assert "bağlanınca çalışır" in satir(sayfa, 3) and 'name="tek" value="tani:3"' in satir(sayfa, 3)


def test_acil_surerken_birincil_dugme_yok_menu_durur(panel, okul, saat):
    from tahta_sunucu import acil

    with vt.islem() as b:
        acil.baslat(b, tur="tatbikat", sablon="", baslik="TATBİKAT", metin="Deneme yayını.", sure_sn=300, baslatan="yonetici")
    sayfa = panel.get("/tahtalar").text
    assert 'name="tek" value="kilitle:1"' in satir(sayfa, 1)  # menüde
    assert re.search(r'<span class="birincil" data-alan="dugme">\s*</span>', satir(sayfa, 1))
    assert panel.get("/api/durum").json()["tahtalar"][0]["liste"]["dugme"] is None


def test_data_onay_tasiyan_dugme_submit_degildir(panel, tahta, okul):
    bekleyen = bekleyen_ekle(panel, tahta)
    # "/" (Bugün): "Hepsini kilitle…" da kapsanır.
    yollar = [*SERIT_SAYFALARI, "/", "/tahtalar?durum=kilitli",
              *(f"/tahta/1{s}" for s in ("", "?sekme=program", "?sekme=bakim", "?sekme=bilgiler")),
              f"/tahta/{bekleyen}", f"/tahta/{bekleyen}?sekme=bakim", f"/tahta/{bekleyen}?sekme=bilgiler"]  # fmt: skip
    for rol in ("yonetici", "idareci1"):
        gir(panel, rol)
        for yol in yollar:
            yanit = panel.get(yol)
            if rol != "yonetici" and yanit.status_code == 303:  # yöneticiye özel sayfa (CSV içe aktarma)
                continue
            assert yanit.status_code == 200, (rol, yol)
            sayfa = yanit.text
            form_kimlikleri = set(re.findall(r'<form[^>]* id="([^"]+)"', sayfa))
            for dugme in re.findall(r"<button[^>]*data-onay=[^>]*>", sayfa):
                assert 'type="button"' in dugme and " name=" not in dugme and " value=" not in dugme, (yol, dugme)
                assert re.search(r'data-onay="([a-z_]+)"', dugme).group(1) in ONAY_ANAHTARLARI, (yol, dugme)
                bagli = re.search(r' form="([^"]+)"', dugme)
                if bagli:
                    assert bagli.group(1) in form_kimlikleri, (yol, dugme)
            # Onay tetikleri kimlikli bir formun içindedir ve o formda name="id" alanı yoktur.
            for form in re.findall(r"<form[^>]*>.*?</form>", sayfa, re.S):
                if "data-onay=" in form:
                    assert re.match(r'<form[^>]* id="[^"]+"', form) and 'name="id"' not in form, (yol, form[:120])
            # Yıkıcı komut hiçbir gönderim düğmesinin değeri değildir (JS'siz onaysız gitmez).
            for dugme in re.findall(r"<button[^>]*>", sayfa):
                if 'type="button"' in dugme:
                    continue
                assert not re.search(r'name="(tur|tek)" value="(kapat|yeniden_baslat|temizlik)[":]', dugme), (yol, dugme)
                if yol.startswith("/tahta"):
                    assert not re.search(r'name="eylem" value="(sil|temizle)"', dugme), (yol, dugme)
    assert ONAY_ANAHTARLARI >= {"kapat", "yeniden_baslat", "temizlik", "sil"}


def test_idareci_htmlinde_yonetici_ogesi_yok(panel, tahta, okul):
    bekleyen = bekleyen_ekle(panel, tahta, "etap-gizli-makine")
    with vt.islem() as b:
        b.execute("UPDATE tahta SET ad = 'Bekleyen-Gizli', ip = '10.9.8.7' WHERE id = ?", (bekleyen,))
    yasaklar = ("Tahta ekle", "Bilgiler ve düzenle", "Gruplar", "CSV ile", "Ajan kurulum paketi", 'href="/ekle"', 'href="/gruplar"',
                "/tahtalar/ice-aktar", "sekme=bilgiler", "/ayarlar", "Bekleyen-Gizli", "10.9.8.7", "etap-gizli-makine", "sekme-ayrac")  # fmt: skip
    yollar = ["/", "/tahtalar", "/tahtalar?durum=acik", "/arizalar", "/envanter", "/tahta/1", "/tahta/1?sekme=program", "/tahta/1?sekme=bakim",
              "/tahta/1?sekme=bilgiler"]  # fmt: skip
    yonetici = panel.get("/tahtalar").text
    for parca in ("Tahta ekle", "Gruplar", "CSV ile içe/dışa aktar", "Ajan kurulum paketi", "sekme=bilgiler", "Bekleyen-Gizli", "10.9.8.7"):
        assert parca in yonetici, parca
    assert f'href="/tahta/{bekleyen}?sekme=bilgiler"' in yonetici and "1 yeni tahta onay bekliyor." in yonetici
    gir(panel, "idareci1")
    for yol in yollar:
        sayfa = panel.get(yol).text
        govde = sayfa.split('<main id="icerik"')[1]
        for yasak in yasaklar:
            if yol == "/envanter" and yasak in ("Bekleyen-Gizli", "10.9.8.7"):
                continue  # envanter sayfası bekleyen tahtayı bugün de listeler (0.16.0 davranışı; bu aşamada değişmedi)
            assert yasak not in govde, (yol, yasak)
    liste = panel.get("/tahtalar").text
    assert "1 yeni tahta yöneticinin onayını bekliyor; onaylanınca bu listeye girer." in liste
    assert 'id="tahta-bilgi"' not in panel.get("/tahta/1?sekme=bilgiler").text  # Genel'e iner
    assert "yönetici yetkisi" in ileti(panel.post("/tahta/1/kaydet", data={"ad": "x", "eylem": "sil"}))  # uç denetimi ayrı


def test_onay_bandi_yalniz_yoneticiye(panel, tahta, okul):
    assert 'id="onay-bekleyen"' not in panel.get("/tahtalar").text
    bekleyen = bekleyen_ekle(panel, tahta)
    sayfa = panel.get("/tahtalar").text
    bant = sayfa.split('id="onay-bekleyen"')[1].split("</div>")[0]
    assert "1 yeni tahta onay bekliyor." in bant and f'href="/tahta/{bekleyen}?sekme=bilgiler"' in bant
    assert f'id="t-{bekleyen}"' not in sayfa and f'value="{bekleyen}"' not in sayfa  # satır olmaz, seçilemez
    assert panel.get("/api/durum").json()["bekleyen"] == 1
    gir(panel, "idareci1")
    sayfa = panel.get("/tahtalar").text
    bant = sayfa.split('id="onay-bekleyen"')[1].split("</p>")[0]
    assert "yöneticinin onayını bekliyor" in bant and "href" not in bant


def test_bos_durumlar_role_gore(panel, tahta):
    kur_ve_gir(panel)
    kullanici_ekle(panel, "idareci1")
    bos = panel.get("/tahtalar").text
    assert "Henüz tahta yok." in bos and '<a class="dugme ana" href="/ekle">Tahta ekle</a>' in bos
    for kanca in ('id="islem"', 'id="haplar"', 'id="secim-cubugu"', 'id="ilk-veri"'):
        assert kanca not in bos, kanca
    gir(panel, "idareci1")
    bos = panel.get("/tahtalar").text
    assert "Henüz tahta yok. Yönetici tahta ekleyince burada görünür." in bos and 'href="/ekle"' not in bos
    gir(panel, "yonetici")
    bekleyen_ekle(panel, tahta)
    for rol in ("yonetici", "idareci1"):
        gir(panel, rol)
        sayfa = panel.get("/tahtalar").text
        assert "Onaylanan tahtalar burada listelenir." in sayfa and "Henüz tahta yok" not in sayfa and 'id="islem"' not in sayfa
    # Süzgeç sonucu boş
    gir(panel, "yonetici")
    tahta_ekle(panel, tahta, "T-1", yeni_ajan_durumu())
    sayfa = panel.get("/tahtalar?durum=sorun").text
    bos = sayfa.split('id="suzgec-bos"')[1].split("</p>")[0]
    assert "hidden" not in bos and "Bu durumda tahta yok." in bos and 'href="/tahtalar"' in bos


def test_kok_bugun_tahtalar_liste(panel, okul):
    """0.18.0: "/" Bugün'dür (liste, seçim formu yok); "/tahtalar" listedir. Eski süzgeçli "/" adresi listeye yönlenir."""
    kok, liste = panel.get("/"), panel.get("/tahtalar")
    assert kok.status_code == liste.status_code == 200
    assert "<title>Bugün · Tahta Kontrol</title>" in kok.text and "<h1>Bugün</h1>" in kok.text
    assert 'id="islem"' not in kok.text and '<tr class="tahta-satir"' not in kok.text and 'name="tahta"' not in kok.text
    assert liste.text.count('<tr class="tahta-satir"') == 3 and 'id="islem"' in liste.text
    assert "<title>Tahtalar · Tahta Kontrol</title>" in liste.text and 'name="donus" value="/tahtalar"' in liste.text
    assert 'href="/tahtalar?durum=kilitli"' in liste.text and 'data-liste-yolu="/tahtalar"' in liste.text
    assert 'href="/?durum=' not in liste.text and 'href="/?durum=' not in kok.text
    yanit = panel.get("/?durum=kilitli")
    assert yanit.status_code == 303 and yanit.headers["location"] == "/tahtalar?durum=kilitli"
    # Oturumsuz: giriş sayfasına.
    panel.cookies.clear()
    assert panel.get("/tahtalar").headers["location"] == "/giris" and panel.get("/").headers["location"] == "/giris"


ESKI_ANAHTARLAR = {
    "bina", "kat", "duzeyler", "devre", "subeler", "gruplar", "alanlar", "yetenekler", "acil_yetenegi", "acil_gorundu", "id", "ad",
    "derslik", "durum", "cevrimici", "kilitli", "duyuru_var", "ekran_bagli", "oturum", "oturum_acik", "son_gorulme", "surum", "guncel",
    "ip", "program", "sinav", "sinav_ekran", "sinav_yetenegi", "yoklama_yetenegi", "yoklama_acik", "ariza_sayisi", "donanim_degisti",
    "envanter_yetenegi", "ariza_yetenegi", "adres_listesi_yetenegi", "dugme_yetenegi", "usb_anahtar_yetenegi", "bagli_adres",
}  # fmt: skip


def test_api_durum_sozlesmesi_eski_anahtarlar_ve_liste(panel, okul):
    veri = panel.get("/api/durum").json()
    # 0.18.0: sözleşme yalnız eklemeli değişti (`bekleyen_is`); eski dört anahtar aynı adla ve türle duruyor.
    assert set(veri) == {"tahtalar", "bekleyen", "acil", "program", "bekleyen_is"} and len(veri["tahtalar"]) == 3
    assert isinstance(veri["bekleyen"], int) and veri["acil"] is None and isinstance(veri["program"], dict)
    assert set(veri["bekleyen_is"]) == {"sayi", "imza"}
    t = veri["tahtalar"][0]
    assert set(t) == ESKI_ANAHTARLAR | {"liste"}  # tek ek: liste
    assert set(t["liste"]) == {"birincil", "durumlar", "rozetler", "dugme", "pasif", "ipucu", "oturum"}
    assert isinstance(t["cevrimici"], bool) and isinstance(t["program"], dict) and t["sinav"] is None
    # Şablon aynı sözlüğü çizer: satırın öznitelikleri ve birincil düğmesi API'deki `liste` ile aynıdır.
    sayfa = panel.get("/tahtalar").text
    for t in veri["tahtalar"]:
        oz = satir_ozniteligi(sayfa, t["id"])
        assert f'data-birincil="{t["liste"]["birincil"]}"' in oz and f'data-durumlar="{" ".join(t["liste"]["durumlar"])}"' in oz
        assert f'name="tek" value="{t["liste"]["dugme"]["tur"]}:{t["id"]}"' in satir(sayfa, t["id"])
        for r in t["liste"]["rozetler"]:
            # V1: `liste: False` taşıyan (düz "Güncelleme var") rozet API'de durur, satırda çizilmez.
            assert (html.escape(r["m"]) in satir(sayfa, t["id"])) == (r.get("liste") is not False), r
    assert veri["tahtalar"][0]["liste"] == tahta_liste.durum_ozeti({a: d for a, d in veri["tahtalar"][0].items() if a != "liste"})
    # ilk-veri /api/durum ile aynı biçimdedir (menü yükü taşımaz).
    ilk = sayfa.split('id="ilk-veri" type="application/json">')[1].split("</script>")[0]
    assert '"liste"' in ilk and '"menu"' not in ilk
    panel.cookies.clear()
    assert panel.get("/api/durum").status_code == 401


def test_liste_formunda_metin_alani_yok(panel, okul):
    form = panel.get("/tahtalar").text.split('<form method="post" action="/islem" id="islem"')[1].split("</form>")[0]
    assert "<textarea" not in form and "<select" not in form
    assert set(re.findall(r'<input type="([a-z]+)"', form)) == {"hidden", "checkbox"}
    assert re.findall(r'<input type="hidden" name="([a-z]+)"', form) == ["donus", "secimden"]


def test_satirlarda_yinelenen_id_yok(panel, tahta, okul):
    bekleyen_ekle(panel, tahta)
    for yol in ("/tahtalar", "/tahtalar?durum=acik", "/tahta/1", "/tahta/1?sekme=program", "/tahta/1?sekme=bakim", "/tahta/1?sekme=bilgiler"):
        kimlikler = re.findall(r'\sid="([^"]+)"', panel.get(yol).text.split("</svg>", 1)[1])
        yinelenen = {k for k in kimlikler if kimlikler.count(k) > 1}
        assert not yinelenen, (yol, yinelenen)


def test_gruplu_liste_konuma_gore(panel, tahta):
    kur_ve_gir(panel)
    tahta_ekle(panel, tahta, "B-1", yeni_ajan_durumu(), bina="B Blok", kat="1")
    tahta_ekle(panel, tahta, "A-2", yeni_ajan_durumu(), bina="A Blok", kat="2")
    tahta_ekle(panel, tahta, "A-1", yeni_ajan_durumu(), bina="a blok", kat="2")
    tahta_ekle(panel, tahta, "Kütüphane", yeni_ajan_durumu())
    sayfa = panel.get("/tahtalar").text
    assert re.findall(r'<span class="grup-ad">([^<]+)</span>', sayfa) == ["A Blok · 2. kat", "B Blok · 1. kat", "Konumu belirtilmemiş"]
    assert re.findall(r'<tr class="tahta-satir" id="t-\d+" data-id="\d+" data-ad="([^"]+)"', sayfa) == ["A-1", "A-2", "B-1", "Kütüphane"]
    assert sayfa.count('<tr class="grup"') == 3 and "(2 tahta)" in re.sub(r"<[^>]+>", "", sayfa) and " / " not in sayfa.split("<table")[1].split("</table>")[0]
    # Süzgeçte bütün satırları gizlenen grubun başlığı da gizlenir.
    cevrimdisi_yap(2)  # A-2: iki tahtalı grubun biri
    suzulmus = panel.get("/tahtalar?durum=cevrimdisi").text
    assert len(re.findall(r'<tr class="grup" hidden>', suzulmus)) == 2 and suzulmus.count('<tr class="grup">') == 1
    # Süzgeçliyken görünen grubun başlığı "1 / 2 tahta" der ("grubu seç" yalnız görüneni seçer); toplam data-toplam'da.
    assert '<span class="not" data-alan="grup-sayi" data-toplam="2">(1 / 2 tahta)</span>' in suzulmus


def test_tahtalar_seridi_sayfalar_ve_etkin_sekme(panel, okul):
    panel.post("/arizalar", data={"tahta_id": "1", "kategori": "acilis", "aciklama": ""})
    ariza = sorgu("SELECT id FROM ariza")[0]["id"]
    beklenen = {
        "/tahtalar": "/tahtalar", "/arizalar": "/arizalar", f"/ariza/{ariza}": "/arizalar", "/envanter": "/envanter",
        "/gruplar": "/gruplar", "/tahtalar/ice-aktar": "/tahtalar/ice-aktar", "/ekle": "/ekle",
    }  # fmt: skip
    for yol, etkin in beklenen.items():
        yanit = panel.get(yol)
        assert yanit.status_code == 200, yol
        assert yanit.text.count('aria-label="Tahtalar bölümü"') == 1, yol
        serit = yanit.text.split('aria-label="Tahtalar bölümü"')[1].split("</nav>")[0]
        assert re.findall(r'<a href="([^"]+)"', serit) == ["/tahtalar", "/arizalar", "/envanter", "/gruplar", "/tahtalar/ice-aktar", "/ekle"], yol
        assert re.findall(r'<a href="([^"]+)" aria-current="page">', serit) == [etkin], yol
        assert '<span class="sayi-rozet">1</span><span class="gizli"> süren arıza</span>' in serit, yol
        # Şeridi çizen sayfa menüde Tahtalar bölümündedir (vurgu başka bölüme zıplamaz).
        menu = yanit.text.split('<aside class="yan-menu"')[1].split("</aside>")[0]
        assert '<a href="/tahtalar" aria-current="page">' in menu, yol
    # Tahta sayfası kendi şeridini çizer; bölüm şeridi orada yoktur.
    assert 'aria-label="Tahtalar bölümü"' not in panel.get("/tahta/1").text
    assert "← Gruplar" not in panel.get("/tahtalar/ice-aktar").text and "/tahtalar.csv" not in panel.get("/gruplar").text
    assert 'href="/tahtalar.csv"' in panel.get("/tahtalar/ice-aktar").text  # dışa aktarma bu sayfada
    gir(panel, "idareci1")
    serit = panel.get("/arizalar").text.split('aria-label="Tahtalar bölümü"')[1].split("</nav>")[0]
    assert re.findall(r'<a href="([^"]+)"', serit) == ["/tahtalar", "/arizalar", "/envanter"]
    # İdareci yönetici sayfasını adresle açarsa (sekmesi çizilmez) şeritte "Tahtalar" etkin görünür.
    for yol in ("/gruplar", "/ekle"):
        yanit = panel.get(yol)
        if yanit.status_code == 200 and 'aria-label="Tahtalar bölümü"' in yanit.text:
            serit = yanit.text.split('aria-label="Tahtalar bölümü"')[1].split("</nav>")[0]
            assert re.findall(r'<a href="([^"]+)" aria-current="page">', serit) == ["/tahtalar"], yol


# ---- stil ve betik (metin denetimi) --------------------------------------------------------------------------
def kural(secici: str) -> str:
    """stil.css'te `secici {` ile başlayan ilk kuralın gövdesi."""
    return STIL.split(secici + " {", 1)[1].split("}", 1)[0]


def test_secim_cubugu_ve_liste_stili():
    blok = STIL.split("/* ---- 0.17.0: tahtalar")[1].split("/* ---- 0.17.0 sonu ---- */")[0]
    blok = re.sub(r"/\*.*?\*/", "", blok.split("---- */", 1)[1], flags=re.S)  # açıklamalar dışında kalan kurallar
    # Liste kabı kaydırma kabı değildir ve kap sorgusu taşımaz (satır menüsü kesilmesin, çift kaydırma olmasın).
    assert "overflow" not in kural("  .tahta-liste-kap") and "container-type" not in kural("  .tahta-liste-kap")
    assert "max-block-size" not in kural("  .tahta-liste-kap") and "container" not in blok
    # Yapışkan başlık üst çubuğun payını belirteçten alır.
    assert "inset-block-start: var(--yapiskan-ust)" in kural("  .tahta-liste thead th")
    # Seçim çubuğu JS'liyken yapışır, sarmaz, alt çubuğun üstünde durur; seçim yokken gizlidir.
    yapiskan = kural("  .js-secim .secim-cubugu")
    assert "position: sticky" in yapiskan and "flex-wrap: nowrap" in yapiskan
    assert "inset-block-end: calc(var(--alt-cubuk-pay, 0px) + var(--b3))" in yapiskan
    assert ".js-secim:not(.secili) .secim-cubugu { display: none; }" in blok
    assert ".js-secim .secim-cubugu > * { min-inline-size: 0; }" in blok
    kabuk = STIL.split("@layer kabuk {")[1].split("/* ---- 0.15.0 sonu ---- */")[0]
    assert "body.kabuklu { --alt-cubuk-pay: calc(var(--alt-boy) + env(safe-area-inset-bottom)); }" in kabuk
    # Çubuğun katmanı: içerikteki yapışkanların üstünde, yan menü çekmecesinin (51), perdenin (50) ve alt çubuğun (40) altında.
    assert int(re.search(r"z-index: (\d+)", yapiskan).group(1)) < 40
    # body/html/main'e taşma ya da yükseklik verilmez; baskıda çubuk gizlidir.
    assert not re.search(r"(^|[\s,])(body|html|main)[^{]*\{[^}]*(overflow|block-size)", blok)
    assert ".secim-cubugu" in blok.split("@media print {")[1].split("}")[0]
    # Yeni belirteç adları -a / -k ile bitmez, t- ile başlamaz (tema.py'nin ham marka renkleri değildir).
    for ad in set(re.findall(r"(--[a-z0-9-]+)\s*:", blok)) | {"--alt-cubuk-pay"}:
        assert not ad.endswith(("-a", "-k")) and not ad.startswith("--t-"), ad
    # Yeni renk kodu yok.
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", blok.replace("#999", ""))
    # 0.16.0 pano kartı kuralları kalktı.
    for olu in (".tahta .bas", ".tahta:has(input:checked)", "#islem .arac-cubugu", ".ozet button", "\n  .izgara {"):
        assert olu not in STIL, olu


def test_panel_js_durum_kurali_sunucuda():
    for olu in ("durumHesapla", "kilitMetni", "programRozetleri", "altyapiRozetleri", "programAjaniEski", "sinavRozeti", "panoKur",
                "PROGRAM_KILIT_ADI", "article.tahta", "form.id", "seritDonus", "seritYaz", "pano-program"):  # fmt: skip
        assert olu not in BETIK, olu
    for metin in ("Teneffüs kilidi", "Ekran yardımcısı yok", "Güncelleme var", "Boş ders:", "kilitli değil", "bağlanınca çalışır"):
        assert metin not in BETIK, metin  # rozet ve gerekçe metinleri yalnız sunucuda (tahta_liste.py)
    tahtalar = BETIK.split("function tahtalarKur")[1].split("function tahtaEskiParcaKur")[0]
    # 0.18.0: yoklama döngüsü Tahtalar ve Bugün için ortaktır (durumYoklayici); istek tek yerde atılır.
    assert "t.liste" in tahtalar and "durumYoklayici(" in tahtalar and BETIK.count('fetch("/api/durum"') == 2  # öbürü acil sayfasının teslim sayacı
    assert ".innerHTML" not in BETIK
    bugun = BETIK.split("function bugunKur")[1].split("// Tahta sayfasının eski parça adresleri")[0]
    assert "t.liste" in bugun and "durumYoklayici(" in bugun and "programYazici(" in bugun
    for yasak in ("innerWidth", "max-width", "matchMedia", "ekran_bagli", "duyuru_var", "t.kilitli"):
        assert yasak not in bugun, yasak  # durum kuralı ve genişlik eşiği Bugün'de de JS'e kopyalanmaz
    assert "if (r.liste === false) return;" in tahtalar  # V1: sunucunun bayrağı uygulanır, kural hesaplanmaz
    # data-tek dalı: satır menüsündeki onay yalnız o tahtayı gönderir; seçili satırlar dalına girilmez.
    onay = BETIK.split("function onayKur")[1].split("/* ---- tahtalar:")[0]
    tek = onay.split('tetik.getAttribute("data-tek")')[1]
    assert 'ac(form, tanim.baslik(null' in tek and '"tek", tekDeger, tanim.evet);\n          return;' in tek
    assert tek.index("return;") < tek.index("pano.seciliSatirlar()")
    assert 'gonderen.name === "tek"' in onay  # satır düğmesinde de sınav ek onayı
    # Canlı tazelemede değişen düğme korunur; açık menü yeniden çizilmez; genişlik eşiği JS'e kopyalanmaz.
    assert "DUGME_KORUMA_MS = 700" in BETIK and "data-degisti" in tahtalar and "menu.open" in tahtalar
    assert "innerWidth" not in tahtalar and "max-width" not in tahtalar
    # Gizlenen satırın kutusu işaretsiz ve devre dışı olur.
    assert "if (gizle) k.checked = false;\n          k.disabled = gizle;" in tahtalar
    # Eski parça adresleri sekmeye taşınır.
    eski = BETIK.split("var TAHTA_ESKI_PARCA = {")[1].split("};")[0]
    for parca, sekme in (("program", "program"), ("envanter", "bakim"), ("arizalar", "bakim"), ("temizlik", "bakim"), ("baglanti", "bakim"),
                         ('"tani-baslik"', "bakim"), ('"komut-baslik"', "bakim"), ('"tahta-bilgi"', "bilgiler")):  # fmt: skip
        assert f'{parca}: "{sekme}"' in eski, parca


# ---- inceleme düzeltmeleri (0.17.0): Enter ile örtük gönderim, satır iletisi, onay iletisi ------------------------
def islem_formu(sayfa: str) -> str:
    return sayfa.split('<form method="post" action="/islem" id="islem"')[1].split("</form>")[0]


def test_liste_formunun_ilk_gonder_dugmesi_devre_disi_nobetcidir(panel, okul):
    """Seçim kutusunda Enter formu örtük gönderir ve tarayıcı ağaç sırasındaki İLK gönder düğmesini tıklar; o düğme
    ilk satırın `tek=` düğmesi olursa seçilmemiş tahtaya komut gider. İlk düğme zararsız nöbetçidir (`nobetci=1`);
    devre dışı OLMAZ (Chromium seçim kutusundaki Enter'da devre dışı düğmeyi atlar, sıradaki etkin düğmeyi tıklar)."""
    cevrimdisi_yap(3)  # ilk gönder düğmesi satır menüsünde de olabilir
    assert 'id="islem"' not in panel.get("/").text  # 0.18.0: "/" Bugün'dür; liste formu yalnız /tahtalar'da
    for yol in ("/tahtalar", "/tahtalar?durum=acik", "/tahtalar?durum=cevrimdisi", "/tahtalar?durum=kilitli"):
        form = islem_formu(panel.get(yol).text)
        dugmeler = re.findall(r"<button\b[^>]*>", form)
        gonderenler = [d for d in dugmeler if 'type="button"' not in d]  # type yoksa da gönder düğmesidir
        ilk = gonderenler[0]
        assert ilk == '<button type="submit" name="nobetci" value="1" hidden tabindex="-1" aria-hidden="true" data-nobetci>', (yol, ilk)
        assert form.index(ilk) < form.index("<input"), yol  # formun ilk denetimi
        assert sum(1 for d in gonderenler if "data-nobetci" in d) == 1, yol
        # Formda Enter ile gönderim tetikleyen metin alanı yok; yalnız onay kutuları ve gizli alanlar.
        assert set(re.findall(r'<input type="([a-z]+)"', form)) <= {"hidden", "checkbox"} and "<textarea" not in form and "<select" not in form
    # Nöbetçiyle gelen istek, yanında ne gelirse gelsin komut yazmaz.
    for ek in ({"tahta": ["1", "2"]}, {"tek": "kilitle:1"}, {"kapsam": "hepsi", "tur": "kilitle"}, {"tur": "kapat", "tahta": ["1"]}, {}):
        yanit = panel.post("/islem", data={"nobetci": "1", "donus": "/tahtalar", **ek})
        assert ileti(yanit) == tahta_liste.NOBETCI_ILETISI and "t=hata" in yanit.headers["location"] and "#" not in yanit.headers["location"], ek
    assert komutlar() == []
    # İkinci kat: panel.js seçim kutusunda Enter'ı yutar.
    assert 'if (h && h.tagName === "INPUT" && h.type === "checkbox") olay.preventDefault();' in BETIK
    # Tahta sayfasının formunda seçim kutusu yoktur (örtük gönderim yolu yok).
    assert 'type="checkbox"' not in panel.get("/tahta/1").text.split('id="tahta-islem"')[1].split("</form>")[0]


def test_satir_komutunun_iletisi_satirda_da_cizilir(panel, okul):
    """Dönüş `#t-<id>` ile satıra kayar; sayfa başındaki ileti ekran dışında kalır. İleti o satırda da çizilir."""
    adres = panel.post("/islem", data={"tek": "kilitle:2", "donus": "/tahtalar"}).headers["location"]
    sayfa = panel.get(adres.split("#")[0]).text
    assert 'class="satir-ileti" role="status" tabindex="-1" data-odakla>' in satir(sayfa, 2) and "Kilitle: T-2 tahtasına gönderildi." in satir(sayfa, 2)
    assert "satir-ileti" not in satir(sayfa, 1) and "satir-ileti" not in satir(sayfa, 3) and sayfa.count('class="satir-ileti"') == 1
    assert sayfa.count("Kilitle: T-2 tahtasına gönderildi.") == 2  # sayfa başındaki bant da durur
    # Hata iletisi, geçersiz ya da eksik satır kimliği satıra yazılmaz; toplu komut satır kimliği taşımaz.
    for sorgu_ in ("?s=2&m=Olmad%C4%B1&t=hata", "?s=abc&m=x", "?s=99&m=x", "?s=-2&m=x", "?m=x", "?s=2"):
        assert 'class="satir-ileti"' not in panel.get("/tahtalar" + sorgu_).text, sorgu_
    assert "s=" not in panel.post("/islem", data={"tur": "kilitle", "tahta": ["1", "2"], "donus": "/tahtalar"}).headers["location"]
    assert "s=" not in panel.post("/islem", data={"tek": "kilitle:2", "donus": "/tahta/2"}).headers["location"]
    # Yansıma yok: ileti kaçışlıdır.
    assert "<script>" not in panel.get("/tahtalar?s=2&m=%3Cscript%3Ealert(1)%3C/script%3E").text
    # panel.js satır iletisini odaklar (ekran okuyucu okur), sayfayı yeniden kaydırmaz.
    assert '.satir-ileti[data-odakla], .bant[data-odakla]' in BETIK and ".satir-ileti {" in STIL


def test_cevrimdisi_satir_menusu_komutun_akibetini_soyler(panel, okul):
    cevrimdisi_yap(3)
    kapali = satir(panel.get("/tahtalar").text, 3)
    assert kapali.count("10 dk bağlanmazsa düşer") == 3 and kapali.count("bağlanınca çalışır") == 2
    assert KOMUT_OMRU["kilitle"] == KOMUT_OMRU["kilit_ac"] == KOMUT_OMRU["duyuru_kaldir"] == 600  # metin ömürden türetilir
    # "Uzaktan aç (deneysel)" açıklaması (0.16.0'daki title) alt yazı olarak durur.
    assert re.search(r'value="uyandir:3" data-komut="uyandir"><span>Uzaktan aç \(deneysel\)</span><small>çoğu cihazda çalışmaz</small>', kapali)
    acik = satir(panel.get("/tahtalar").text, 1)
    assert "bağlanmazsa düşer" not in acik and "bağlanınca çalışır" not in acik


def test_onay_iletisi_tahtanin_komut_aldigini_ve_siradakini_soyler(panel, tahta, okul):
    ilk = bekleyen_ekle(panel, tahta, "etap-a")
    ikinci = bekleyen_ekle(panel, tahta, "etap-b")
    assert ileti(panel.post(f"/tahta/{ilk}/kaydet", data={"ad": "12-C", "eylem": "onayla"})) == (
        "12-C onaylandı; artık komut alır. 1 tahta daha onay bekliyor (Tahtalar sayfasında)."
    )
    assert ileti(panel.post(f"/tahta/{ikinci}/kaydet", data={"ad": "12-D", "eylem": "onayla"})) == "12-D onaylandı; artık komut alır."
    # Zaten onaylı tahtada "onayla" eylemi yeniden onay iletisi vermez; düzenleme "Kaydedildi." der.
    assert ileti(panel.post(f"/tahta/{ilk}/kaydet", data={"ad": "12-C", "eylem": "onayla"})) == "Kaydedildi."
    assert ileti(panel.post(f"/tahta/{ilk}/kaydet", data={"ad": "12-C"})) == "Kaydedildi."


def test_onay_ve_menu_betigi_kapali_hata_verir():
    # data-tek taşıyan tetik hiçbir koşulda genel dala (tur=…, işaretli bütün tahtalar) düşmez.
    dal = BETIK.split('if (tetik.hasAttribute("data-tek")) {')[1].split("ac(form, tanim.baslik(null, tekAd)")[0]
    assert dal.lstrip().startswith("if (!pano || form !== pano.form || !/^[a-z_]+:[1-9][0-9]*$/.test(tekDeger)) return;")
    assert "var sinavUyarisi" not in dal and 'tekDeger && pano' not in BETIK
    # Onay başlığı tahta adını taşır; tahta sayfasında oturum / çevrimdışı uyarısı forma yazılan durumdan gelir.
    assert 'ad ? "“" + ad + "” tahtası" : "Bu tahta") + " kapatılsın mı?"' in BETIK
    assert 'form.hasAttribute("data-oturum-acik")' in BETIK and 'form.hasAttribute("data-cevrimdisi")' in BETIK
    # Birincil düğme koruması satırın bütününe değil düğmenin hücresine bakar (seçim kutusundaki odak dondurmaz).
    assert "tr.contains(document.activeElement)" not in BETIK and "kap.contains(document.activeElement)" in BETIK
    # Satır menüsü görüntü alanına göre yön seçer ve sığmazsa kendi içinde kayar ("Kapat…" ekran dışında kalmaz).
    assert "liste.style.maxBlockSize" in BETIK and 'document.querySelector(".alt-cubuk")' in BETIK
    menu = STIL.split("  .menu-liste { position: absolute;")[1].split("}")[0]
    assert "overflow-y: auto" in menu
    # Kalkan yan menü alt listesinin ölü kuralları temizlendi.
    for olu in (".yan-alt", "data-icinde", "--kb-alt", ".alanlar-satiri"):
        assert olu not in STIL and olu not in BETIK, olu
    # Telefonda boş süzgeç hapları çizilmez; ad hücresinin tamamı dokunma hedefidir.
    assert ".hap.bos:not([aria-current]) { display: none; }" in STIL and ".tahta-liste .c-ad a::after" in STIL
    dar = STIL.split("@media (max-width: 47.99rem) {")[-1]
    assert ".haplar { flex-wrap: nowrap;" in dar and "overflow-x: auto" in dar.split(".haplar {")[1].split("}")[0]


def test_program_kilidini_durdur_bugune_doner(panel, tahta):
    """0.18.0: "Program kilidini durdur" Bugün › Şu an kartındadır ve Bugün'e döner; listede form yoktur."""
    from test_program_panel import durum, hazirla

    hazirla(panel)
    tahta_ekle(panel, tahta, "T-1", durum())
    kart = panel.get("/").text.split('id="bugun-simdi"')[1].split("</section>")[0]
    assert 'action="/program/istisna"' in kart and 'name="donus" value="/"' in kart
    for yol in ("/tahtalar", "/tahtalar?durum=acik"):
        liste = panel.get(yol).text
        assert 'action="/program/istisna"' not in liste and 'id="pano-program"' not in liste, yol
    assert "seritDonus" not in BETIK
    yanit = panel.post("/program/istisna", data={"donus": "/", "sure": "1sa"})
    assert yanit.headers["location"].startswith("/?m=Program%20kilidi%20durduruldu")
    sayfa = panel.get(yanit.headers["location"]).text
    assert "Program kilidi durduruldu (tüm tahtalar)" in sayfa.split('id="bugun-bas"')[0]  # ileti sayfa başında
    kart = sayfa.split('id="bugun-simdi"')[1].split("</section>")[0]
    assert "Program kilidi durduruldu · bitiş" in kart and re.search(r'data-alan="durdur"\s*hidden', kart)
    assert re.search(r'data-alan="istisnalar" href="/program\?bolum=istisnalar">', kart)


def test_pano_sozu_kullaniciya_gorunen_metinde_kalmadi(panel, okul):
    yanit = panel.post("/islem", data={"tek": "uyandir:1", "donus": "/tahta/1"})
    assert "Tahtalar sayfasından izleyin" in ileti(yanit)
    for yol in ("/", "/tahtalar", "/ekle", "/envanter", "/acil", "/ayarlar/guncelleme", "/program?bolum=derslik", "/ayarlar"):
        metin = re.sub(r"<script.*?</script>|<[^>]+>", " ", panel.get(yol).text, flags=re.S).lower()
        assert not re.search(r"\bpano(da|dan|ya|su|nun)?\b", metin), yol
