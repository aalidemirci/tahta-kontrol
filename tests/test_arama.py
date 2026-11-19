"""Genel aramanın dizini (0.20.0, arama.py): tek tanımlardan türeme, rol süzmesi, eşleştirme ve sıralama.

Dizin ikinci bir sayfa/sekme/ayar listesi DEĞİLDİR: web.MENU, bolum_serit.SERITLER, ayar_bolumleri ve
tahta_liste.SUZGECLER'den türer ve burada onlarla eşlenir. Uçlar ve gizlilik testleri test_arama_sayfasi.py'dedir.
Bütün veriler uydurmadır.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from tahta_sunucu import arama, ayar_bolumleri, bolum_serit, tahta_liste, vt, web

SABIT = web.ARAMA_SABIT
KAYNAK = Path(arama.__file__).read_text(encoding="utf-8")
MENU_OGELERI = [o for k in web.MENU for o in k["ogeler"]] + [web.MENU_ACIL]
SEKMELER = [(ad, s) for ad, t in bolum_serit.SERITLER.items() for kume in t["kumeler"] for s in kume]
YONETICI_YOL_PARCALARI = ("/ayarlar", "/yedekler", "/ekle", "/gruplar", "/tahtalar/ice-aktar", "/ogretmen-programi",
                          "/program/aktar", "/program/gecmis", "sekme=sablonlar")  # fmt: skip


def tur(ad: str) -> list[dict]:
    return [g for g in SABIT if g["tur"] == ad]


def coz(yol: str) -> tuple[str, str]:
    return arama.yer_coz(yol, web.MENU, web.MENU_ACIL, web._secili)


@pytest.fixture()
def devingen(uygulama):
    """Uydurma tahtalar, şubeler ve bir grup; role göre devingen dizin."""
    with vt.islem() as b:
        vt.ayar_yaz(b, "yoklama", {"etkin": True})
        for ad, bina, kat, sube, durum in (
            ("9-A", "A Blok", 1, "9/A", "onayli"),
            ("Fizik Lab", "B Blok", 0, "", "onayli"),
            ("10A Tahtası", "", None, "10/A|10/B", "onayli"),
            ("Bekleyen Tahta", "A Blok", 2, "", "bekliyor"),
        ):
            b.execute(
                "INSERT INTO tahta (ad, anahtar_ozet, durum, kayit_zamani, bina, kat, subeler, ip, makine_adi, demirbas_no, "
                "envanter_notu) VALUES (?, 'x', ?, 0, ?, ?, ?, '10.9.8.7', 'etap-uydurma', 'DMB-77', 'uydurmanot')",
                (ad, durum, bina, kat, sube),
            )
        for sube, no in (("9/A", "1"), ("10/A", "2"), ("10/B", "3")):
            b.execute("INSERT INTO ogrenci (okul_no, ad, soyad, sube, aktif, guncelleme) VALUES (?, 'Uydurma', 'KİŞİ', ?, 1, 0)", (no, sube))
        b.execute("INSERT INTO tahta_grubu (ad, aciklama, olusturan, olusturma) VALUES ('Laboratuvarlar', 'uydurmaaciklama', 'x', 0)")
        return {rol: arama.devingen_dizin(b, rol, web.ARAMA) for rol in ("yonetici", "idareci")}


def bul(sorgu: str, rol: str = "yonetici", devingen: dict | None = None, en_cok: int = 50) -> list[dict]:
    return arama.ara(sorgu, SABIT, (devingen or {}).get(rol, []), rol, en_cok)["sonuclar"]


def yollar(sorgu: str, rol: str = "yonetici", devingen: dict | None = None) -> list[str]:
    return [s["yol"] for s in bul(sorgu, rol, devingen)]


# ---- dizin tek tanımlardan türer -----------------------------------------------------------------------------
def test_dizin_menu_ile_eslenir():
    assert [(g["ad"], g["yol"], g["rol"], g["yer"]) for g in tur("sayfa")] == [
        (o["ad"], o["yol"], o.get("rol", ""), "") for o in MENU_OGELERI
    ]
    assert len(tur("sayfa")) == 11  # 10 menü öğesi + Acil durum; "Ara" diye sayfa girdisi yok


def test_dizin_seritlerle_eslenir():
    beklenen = []
    for serit, s in SEKMELER:
        if s.get("dis"):
            continue
        ust = arama.serit_ust_ogesi(serit, web.MENU, web.MENU_ACIL, web._secili)
        beklenen.append((s["ad"], s["yol"], s.get("rol") or ust.get("rol") or "", ust["ad"]))
    assert [(g["ad"], g["yol"], g["rol"], g["yer"]) for g in tur("sekme")] == beklenen
    dis = [s["yol"] for _, s in SEKMELER if s.get("dis")]
    assert dis and not [g for g in tur("sekme") if g["yol"] in dis]  # dış sekmeyi Ayarlar girdisi karşılar
    assert arama.serit_ust_ogesi("acil", web.MENU, web.MENU_ACIL, web._secili) is web.MENU_ACIL


def test_dizin_ayar_bolumleriyle_eslenir():
    assert [(g["ad"], g["yol"], g["alt"]) for g in tur("ayar")] == [
        (b["baslik"], f"/ayarlar/{b['anahtar']}", b["aciklama"]) for b in ayar_bolumleri.BOLUMLER
    ]
    assert all(g["rol"] == "yonetici" and g["yer"].startswith("Ayarlar › ") for g in tur("ayar"))
    assert {g["yer"].split(" › ")[1] for g in tur("ayar")} == set(ayar_bolumleri.KUMELER)
    isler = [(g["ad"], g["yol"], g["yer"]) for g in tur("is")]
    assert isler[: len(ayar_bolumleri.BASKA_YERDE)] == [(o["ad"], o["yol"], o["yer"]) for o in ayar_bolumleri.BASKA_YERDE]
    assert [g["ad"] for g in tur("is")][len(ayar_bolumleri.BASKA_YERDE) :] == [o["ad"] for o in arama.SIK_ISLER]


def test_dizin_suzgeclerle_eslenir():
    assert [g["yol"] for g in tur("suzgec")] == [f"/tahtalar?durum={a}" for a in tahta_liste.SUZGECLER]
    # Ad "<liste>: <etiket>" kalıbıdır (etikete çoğul eki yapıştırılmaz: "Güncelleme tahtalar" bozuk okunuyordu);
    # başlık öneki kademesi etiketten sayılır ("cev" → Çevrimdışı ilk sırada kalır).
    assert [g["ad"] for g in tur("suzgec")] == [f"Tahtalar: {etiket}" for etiket in tahta_liste.SUZGECLER.values()]
    assert [g["ad_sozcuk"] for g in tur("suzgec")] == [arama.sozcukler(e) for e in tahta_liste.SUZGECLER.values()]
    assert not [g["ad"] for g in SABIT if g["ad"].endswith(" tahtalar") and g["tur"] == "suzgec"]
    assert all(tahta_liste.suzgec_coz(g["yol"].split("=")[1]) for g in tur("suzgec")) and {g["rol"] for g in tur("suzgec")} == {""}


def test_dizinde_elle_yazilmis_sayfa_adi_yok():
    """İkinci liste kilidi: arama.py'de menü, sekme, ayar bölümü, küme ya da süzgeç adı düz metin olarak geçmez
    (yalnız SIK_ISLER'in kendi iş adlarında geçebilir; onlar başlık değil, işin adıdır)."""
    agac = ast.parse(KAYNAK)
    atla: set[int] = set()
    for dugum in ast.walk(agac):
        if isinstance(dugum, (ast.Module, ast.FunctionDef)) and ast.get_docstring(dugum) is not None:
            atla.add(id(dugum.body[0].value))
        hedefler = [getattr(dugum, "target", None)] + list(getattr(dugum, "targets", []))
        if isinstance(dugum, (ast.Assign, ast.AnnAssign)) and any(getattr(h, "id", "") == "SIK_ISLER" for h in hedefler):
            atla.update(id(alt) for alt in ast.walk(dugum))
    sabitler = [d.value for d in ast.walk(agac) if isinstance(d, ast.Constant) and isinstance(d.value, str) and id(d) not in atla]
    adlar = {o["ad"] for o in MENU_OGELERI} | {s["ad"] for _, s in SEKMELER} | {b["baslik"] for b in ayar_bolumleri.BOLUMLER}
    adlar |= set(ayar_bolumleri.KUMELER) | set(tahta_liste.SUZGECLER.values()) | {o["ad"] for o in ayar_bolumleri.BASKA_YERDE}
    assert len(adlar) > 50 and len(sabitler) > 40
    for ad in adlar:
        for sabit in sabitler:
            assert ad not in sabit, (ad, sabit)


def test_her_yol_var_olan_get_adresidir(uygulama):
    rotalar = [r for r in uygulama.routes if "GET" in (getattr(r, "methods", None) or ())]
    for g in SABIT:
        duz = g["yol"].split("#")[0].split("?")[0]
        assert g["yol"].startswith("/") and not g["yol"].startswith("//") and "\\" not in g["yol"], g["yol"]
        assert any(r.path_regex.match(duz) for r in rotalar), g["yol"]
        assert not duz.endswith((".csv", ".txt", ".deb")) and "/indir/" not in duz and not duz.startswith(("/kur", "/api", "/ajan")), g["yol"]
    assert len({(g["tur"], g["yol"]) for g in SABIT}) == len(SABIT)  # aynı tür ve yol iki kez yok


def test_sabit_dizin_her_cagrida_ayni_ve_ic_alanlari_tam():
    yeniden = arama.sabit_dizin(web.MENU, web.MENU_ACIL, web._secili)
    assert yeniden == SABIT and 70 <= len(SABIT) <= 110
    for g in SABIT:
        assert set(g) == {"tur", "ad", "yer", "yol", "rol", "alt", "saman", "saman_kat", "ad_sozcuk", "ad_saman", "sira"}
        assert g["saman"] == g["saman"].lower() and g["saman_kat"] == ayar_bolumleri.katla(g["saman"])
        assert g["tur"] in arama.TUR_SIRASI and g["rol"] in ("", "yonetici")


# ---- rol: hedef sayfadan türer -------------------------------------------------------------------------------
def test_rol_hedef_sayfadan_turer():
    acik = {o["yol"]: o["rol"] for o in arama.SIK_ISLER if o.get("rol")}
    assert set(acik.values()) <= {"yonetici"}
    for g in SABIT:
        turetilen = coz(g["yol"])[1]
        if g["tur"] == "is" and g["yol"] in acik:
            assert turetilen == "" and g["rol"] == "yonetici", g["ad"]  # açık rol yalnız DARALTIR
        else:
            assert g["rol"] == turetilen, g["ad"]
    assert coz("/yedekler") == ("Yedekler", "yonetici") and coz("/ayarlar/veri") == ("Ayarlar › Veri saklama ve yedek", "yonetici")
    assert coz("/acil?sekme=sablonlar") == ("Acil durum › Şablonlar", "yonetici") and coz("/acil") == ("Acil durum › Yayın başlat", "")
    assert coz("/yoklama/sube?sube=9%2FA") == ("Yoklama", "") and coz("/yoklama/sube") == ("Yoklama › Şube defteri", "")
    assert coz("/tahtalar?durum=acik") == ("Tahtalar", "") and coz("/tahtalar#onay-bekleyen") == ("Tahtalar", "")
    assert coz("/ogretmen-programi?x=1") == ("Program", "yonetici")  # o yoldaki her sekme yöneticiye özel
    assert coz("/") == ("Bugün", "") and coz("/kayit") == ("İşlem kaydı", "")


@pytest.mark.parametrize("yol", ["/bilinmeyen", "//dis.ornek/x", "http://dis.ornek/", "ayarlar", "", "/api/durum"])
def test_sahipsiz_hedef_dizini_patlatir(yol):
    """Menüde yeri olmayan hedef sessizce "herkese açık" olmaz."""
    with pytest.raises(ValueError):
        coz(yol)


def test_sik_iste_bilinmeyen_rol_ve_sahipsiz_yol_reddedilir(monkeypatch):
    monkeypatch.setattr(arama, "SIK_ISLER", [{"ad": "Deneme", "yol": "/bilinmeyen-sayfa", "sozcukler": "deneme"}])
    with pytest.raises(ValueError):
        arama.sabit_dizin(web.MENU, web.MENU_ACIL, web._secili)
    monkeypatch.setattr(arama, "SIK_ISLER", [{"ad": "Deneme", "yol": "/kayit", "sozcukler": "deneme", "rol": "idareci"}])
    with pytest.raises(ValueError):
        arama.sabit_dizin(web.MENU, web.MENU_ACIL, web._secili)
    monkeypatch.setattr(arama, "SIK_ISLER", [{"ad": "Deneme", "yol": "/kayit", "sozcukler": "a"}, {"ad": "İkinci", "yol": "/kayit", "sozcukler": "b"}])
    with pytest.raises(ValueError):
        arama.sabit_dizin(web.MENU, web.MENU_ACIL, web._secili)


def test_idareci_dizininde_yonetici_girdisi_yok(devingen):
    adaylar = [g for g in SABIT if not g["rol"]] + devingen["idareci"]
    yonetici_adlari = {o["ad"] for o in MENU_OGELERI if o.get("rol")} | {s["ad"] for _, s in SEKMELER if s.get("rol")}
    yonetici_adlari |= {b["baslik"] for b in ayar_bolumleri.BOLUMLER} | {"Laboratuvarlar"}
    assert {"Yedekler", "Ayarlar", "Gruplar", "Şablonlar", "İçe aktar", "Ajan kurulum paketi"} <= yonetici_adlari
    for g in adaylar:
        for parca in YONETICI_YOL_PARCALARI:
            assert parca not in g["yol"], g["yol"]
        for ad in yonetici_adlari:
            assert ad != g["ad"] and ad not in g["yer"].split(" › "), (ad, g["ad"], g["yer"])
    assert not [g for g in devingen["idareci"] if g["tur"] == "grup"]
    assert [g["ad"] for g in devingen["yonetici"] if g["tur"] == "grup"] == ["Laboratuvarlar"]
    # Sorgu sonucu da aynı: yöneticinin gördüğü, idarecinin görmediği.
    for sorgu in ("ayar", "yedek", "kilit kodu", "grup", "ajan", "kvkk", "kullanıcı", "şablon", "içe aktar", "laboratuvar", "onay"):
        y, i = yollar(sorgu, "yonetici", devingen), yollar(sorgu, "idareci", devingen)
        assert any(p in yol for yol in y for p in (*YONETICI_YOL_PARCALARI, "#onay-bekleyen")), sorgu
        assert not any(p in yol for yol in i for p in (*YONETICI_YOL_PARCALARI, "#onay-bekleyen")), (sorgu, i)
        assert arama.ara(sorgu, SABIT, devingen["idareci"], "idareci")["toplam"] < arama.ara(sorgu, SABIT, devingen["yonetici"], "yonetici")["toplam"]
    # Rolü bilinmeyen (None) istek yalnız herkese açık girdileri görür.
    assert yollar("yedek", None, devingen) == [] and yollar("ayar", "baska", devingen) == []


# ---- devingen dizin: yalnız tahta, şube, grup adı ----------------------------------------------------------
def test_devingen_dizin_yalniz_onayli_tahta_sube_ve_grup(devingen):
    y = devingen["yonetici"]
    assert [(g["tur"], g["ad"], g["yol"]) for g in y] == [
        ("tahta", "Fizik Lab", "/tahta/2"),  # Türk abecesi; rakam harften sonra (metin.tr_sirala_anahtari)
        ("tahta", "10A Tahtası", "/tahta/3"),
        ("tahta", "9-A", "/tahta/1"),
        ("sube", "9/A şube defteri", "/yoklama/sube?sube=9%2FA"),
        ("sube", "10/A şube defteri", "/yoklama/sube?sube=10%2FA"),
        ("sube", "10/B şube defteri", "/yoklama/sube?sube=10%2FB"),
        ("grup", "Laboratuvarlar", "/gruplar#grup-1"),
    ]
    assert [g["yer"] for g in y] == ["Tahta · B Blok · Zemin kat", "Tahta", "Tahta · A Blok · 1. kat"] + ["Yoklama › Şube defteri"] * 3 + ["Tahtalar › Gruplar"]
    hepsi = " ".join(f"{g['ad']} {g['yer']} {g['yol']} {g['saman']} {g['alt']}" for g in y).lower()
    for yasak in ("bekleyen", "10.9.8.7", "etap-uydurma", "dmb-77", "uydurmanot", "uydurmaaciklama", "uydurma", "kişi"):
        assert yasak not in hepsi, yasak
    assert yollar("10/b", "idareci", devingen) == ["/yoklama/sube?sube=10%2FB", "/tahta/3"]  # tahtanın şubeleri aranır
    # Şubenin samanlığı yalnız şubedir: "10/d" ("defteri"), "10/s" ("şube") öbür şubeleri getirmez.
    assert yollar("10/d", "idareci", devingen) == [] and yollar("10 ş", "idareci", devingen) == []
    assert yollar("şube defteri", "idareci", devingen)[0] == "/yoklama/sube"
    assert yollar("a blok", "idareci", devingen) == ["/tahta/1"] and yollar("zemin", "idareci", devingen) == ["/tahta/2"]


def test_yoklama_kapaliyken_sube_girdisi_yok(devingen):
    with vt.islem() as b:
        vt.ayar_yaz(b, "yoklama", {"etkin": False})
        kapali = arama.devingen_dizin(b, "yonetici", web.ARAMA)
    assert not [g for g in kapali if g["tur"] == "sube"] and len([g for g in kapali if g["tur"] == "tahta"]) == 3


def test_bozuk_sube_degeri_dizini_patlatmaz(uygulama):
    with vt.islem() as b:
        b.execute("INSERT INTO tahta (ad, anahtar_ozet, durum, kayit_zamani, subeler) VALUES ('T', 'x', 'onayli', 0, 'bozuk|99/ZZ|')")
        assert [g["ad"] for g in arama.devingen_dizin(b, "idareci", web.ARAMA)] == ["T"]


# ---- eşleştirme --------------------------------------------------------------------------------------------
def test_esleme_kurali(devingen):
    # Sözcük BAŞI: ortadan eşleşme yok.
    assert "/ayarlar/kilit" not in yollar("ilit") and "/yedekler" not in yollar("edek")
    # Çok sözcük VE.
    assert yollar("kilit kodu") == ["/ayarlar/kilit"] and yollar("kilit kodu qqq") == []
    # Harf katlama: Türkçe harfsiz yazım bulur.
    assert yollar("yuzer")[0] == "/ayarlar/yuzer" and yollar("cevrimdisi") == ["/tahtalar?durum=cevrimdisi"]
    assert yollar("ogretmen pin")[0] == "/ogretmenler" and "/ayarlar/kilit" in yollar("sifre")
    # Kesin eşleşme üstte, yalnız katlanınca eşleşen altta: "acil" → Acil durum; "Açılışta kilit" (kilit bölümü) en sonda.
    acil = yollar("acil")
    assert acil[0] == "/acil" and acil[-1] == "/ayarlar/kilit" and "/ayarlar/kilit" not in yollar("acil", "idareci")
    # Büyük harf: İ → i, I → ı (Türkçe küçültme); "ISTISNA" yalnız katlanarak bulur.
    assert yollar("İSTİSNA") == yollar("istisna") == ["/program?bolum=istisnalar"]
    assert yollar("ISTISNA") == ["/program?bolum=istisnalar"]
    # Şube ve tahta: bölü, tire ve bitişik yazım aynı ikisini bulur.
    for sorgu in ("9/a", "9-a", "9a", "9/A", "9 a"):
        assert set(yollar(sorgu, "idareci", devingen)) == {"/yoklama/sube?sube=9%2FA", "/tahta/1"}, sorgu
    assert yollar("9/a", "idareci", devingen)[0] == "/yoklama/sube?sube=9%2FA"  # şube tahtadan önce


def test_siralama_kademe_ve_tur(devingen):
    # Başlık öneki (sayfa) > başlık öneki (iş) > süzgeç; aynı hedef tek satır ("Duyurular ve planlar", "Yeni duyuru" yinelenmez).
    assert yollar("duy") == ["/duyurular", "/duyurular/yeni", "/tahtalar?durum=duyuru"]
    assert [s["ad"] for s in bul("duy")] == ["Duyurular", "Duyuru yap", "Tahtalar: Duyuruda"]
    assert [s["ad"] for s in bul("güncelleme")] == ["Tahtalar: Güncelleme", "Güncelleme denetimi"]
    # Başlığın ilk sözcüğü > başlıktaki başka sözcük > yalnız anahtar sözcük.
    yedek = [s["ad"] for s in bul("yedek")]
    assert yedek == ["Yedekler", "Veri saklama ve yedek"]
    pin = bul("pin")
    assert [s["yol"] for s in pin] == ["/ogretmenler", "/ayarlar/yoklama", "/ayarlar/usb"]
    for sorgu in ("tahta", "program", "a", "ders", "kilit"):
        sonuc = yollar(sorgu, "yonetici", devingen)
        assert len(sonuc) == len(set(sonuc)), sorgu
    # Tür sırası aynı kademede: grup adı öneki ile tahta adındaki ikinci sözcük.
    assert [s["tur"] for s in bul("lab", "yonetici", devingen)] == ["grup", "tahta", "is"]


def test_genel_arama_ayar_aramasini_kapsar():
    for sorgu in ("kvkk", "kayar buton", "KAYAR", "yuzer", "renk", "pin", "yedek", "kilit", "zil", "temizlik", "kapanış",
                  "kisisel", "şifre", "idareci ekle", "müdür yardımcısı", "usb", "sınav", "sürüm", "ip", "logo", "ikili"):  # fmt: skip
        ayar = ayar_bolumleri.ara(sorgu)
        genel = yollar(sorgu)
        assert ayar["sayi"], sorgu
        for anahtar in ayar["bolumler"]:
            assert f"/ayarlar/{anahtar}" in genel, (sorgu, anahtar)
        for sira in ayar["baska"]:
            assert ayar_bolumleri.BASKA_YERDE[sira]["yol"] in genel, (sorgu, sira)


def test_bos_tek_harf_ve_uzun_sorgu(devingen):
    for bos in ("", "   ", "?!.,", None, "///", "\x00"):
        sonuc = arama.ara(bos, SABIT, devingen["yonetici"], "yonetici")
        assert sonuc["etkin"] is False and sonuc["sonuclar"] == [] and sonuc["toplam"] == 0 and sonuc["fazla"] is False
    assert {"/yoklama/sube?sube=9%2FA", "/tahta/1"} <= set(yollar("9", "idareci", devingen))  # tek karakter sayfada çalışır
    uzun = arama.ara("zil " * 200, SABIT, [], "yonetici")
    assert len(uzun["sorgu"]) <= ayar_bolumleri.SORGU_EN_UZUN == 60 and uzun["etkin"]
    assert arama.sorgu_duzelt("  a   b \n c ") == "a b c" and len(arama.sorgu_duzelt("x" * 5000)) == 60
    # İlk 6 sözcük kullanılır: yedincisi anlamsız olsa da sonuç değişmez.
    assert yollar("zil saatleri zil saatleri zil saatleri qqqq") == yollar("zil saatleri")
    sinirli = arama.ara("a", SABIT, devingen["yonetici"], "yonetici", 8)
    assert len(sinirli["sonuclar"]) == 8 and sinirli["toplam"] > 8 and sinirli["fazla"] is True


def test_sonuc_sozlugunde_ic_alan_yok(devingen):
    sonuc = arama.ara("tahta", SABIT, devingen["yonetici"], "yonetici")
    assert set(sonuc) == {"sorgu", "etkin", "sonuclar", "toplam", "fazla"} and sonuc["sonuclar"]
    for s in sonuc["sonuclar"] + arama.sik_isler(SABIT, "yonetici"):
        assert set(s) == {"tur", "ad", "yer", "yol", "alt"}
    assert [s for s in sonuc["sonuclar"] if s["alt"]] == [s for s in sonuc["sonuclar"] if s["tur"] == "ayar"]


def test_gruplu_sabit_sira_ve_bos_grup_yok(devingen):
    gruplar = arama.gruplu(bul("a", "yonetici", devingen) + bul("laboratuvarlar", "yonetici", devingen))
    assert [g["anahtar"] for g in gruplar] == ["sayfa", "ayar", "sube", "tahta", "grup"]
    assert [g["anahtar"] for g in arama.gruplu(bul("fizik", "idareci", devingen))] == ["tahta"]
    assert arama.gruplu([]) == []


def test_sik_isler_role_gore():
    """Sorgu boşken gösterilen liste bütün kısa yolların dökümü değildir: `one` taşıyanlar, günlük iş sırasıyla, ≤ 8."""
    y, i = arama.sik_isler(SABIT, "yonetici"), arama.sik_isler(SABIT, "idareci")
    one = sorted((o for o in arama.SIK_ISLER if o.get("one")), key=lambda o: o["one"])
    assert [o["one"] for o in one] == list(range(1, len(one) + 1)) and len(one) == arama.SIK_EN_COK == 8
    assert [s["yol"] for s in y] == [o["yol"] for o in one] and y[0]["yol"] == "/duyurular/yeni" and y[1]["yol"] == "/tahtalar"
    assert {s["tur"] for s in y} == {"is"} and 1 <= len(i) <= len(y) <= 8 and i[0]["yol"] == "/duyurular/yeni"
    assert not [s for s in i if any(p in s["yol"] for p in (*YONETICI_YOL_PARCALARI, "#onay-bekleyen"))]
    # Öne alınmayan kısa yol listede yoktur ama aranınca çıkar.
    assert "/kayit" not in [s["yol"] for s in y] and "/kayit" in yollar("işlem kaydı")


EKLI_SORGULAR = [
    # (sorgu, rol, ilk sonuç) — bağımsız incelemede sonuçsuz kalan ya da yanlış yere giden gündelik aramalar.
    ("pin pusulası", "ikisi", "/ogretmenler"),
    ("pusulası", "ikisi", "/ogretmenler"),
    ("kapat", "ikisi", "/tahtalar"),
    ("tahtaları kapat", "ikisi", "/tahtalar"),
    ("tahta kapat", "ikisi", "/tahtalar"),
    ("kilidi aç", "ikisi", "/tahtalar"),
    ("kilit aç", "ikisi", "/tahtalar"),
    ("yeniden başlat", "ikisi", "/tahtalar"),
    ("ders programı", "ikisi", "/program?bolum=derslik"),
    ("haftalık", "ikisi", "/program?bolum=derslik"),
    ("sınıf listesi", "ikisi", "/ogrenciler"),
    ("öğrenci ekle", "ikisi", "/ogrenciler"),
    ("son günler", "ikisi", "/yoklama/son-gunler"),
    ("bayram", "ikisi", "/program?bolum=istisnalar"),
    ("yoklama ayarları", "yonetici", "/ayarlar/yoklama"),  # Yoklama şeridindeki dış sekmenin birebir adı
    ("parolamı değiştir", "yonetici", "/ayarlar/kilit"),
]


@pytest.mark.parametrize("sorgu, rol, hedef", EKLI_SORGULAR)
def test_ekli_ve_gundelik_sorgular_hedefi_bulur(devingen, sorgu, rol, hedef):
    assert yollar(sorgu, "yonetici", devingen)[0] == hedef, sorgu
    idareci = yollar(sorgu, "idareci", devingen)
    if rol == "ikisi":
        assert idareci[0] == hedef, sorgu
    else:
        assert not [y for y in idareci if any(p in y for p in YONETICI_YOL_PARCALARI)], sorgu


def test_ekli_esleme_en_alt_kademedir_ve_gurultu_uretmez(devingen):
    # Ekli eşleşme kesin ve katlı eşleşmenin ALTINDADIR: "tahtaları" önce o sözcüğü taşıyan işi, sonra "tahta"ları verir.
    tahtalari = bul("tahtaları", "idareci", devingen)
    assert [s["yol"] for s in tahtalari[:2]] == ["/#bugun-tahtalar", "/tahtalar"]  # sözcüğü taşıyan iki iş (kesin)
    # Sonra yalnız ekli eşleşenler ("tahtalar", "tahta" köküyle): süzgeçler, sekmeler ve üç tahta; kesinlerin altında.
    assert {s["tur"] for s in tahtalari[2:]} == {"sekme", "suzgec", "tahta"} and len([s for s in tahtalari if s["tur"] == "tahta"]) == 3
    # Kök en az 4 harftir: "kodu" → "kod" sayılmaz (kilit kodu yalnız kendi bölümünü bulur); 3 harfli sorgu ek sayılmaz.
    assert arama.EK_KOK_EN_KISA == 4 and yollar("kilit kodu") == ["/ayarlar/kilit"]
    assert arama._ekli_uyar(["pusulası"], "pin pusula") and not arama._ekli_uyar(["kodu"], "pin kod")
    assert not arama._ekli_uyar(["pusulası", "qqq"], "pin pusula") and not arama._ekli_uyar(["sulası"], "pin pusula")
    # Kökten artan kısım yalnız harftir: sonuna rakam eklenmiş sözcük (kullanıcı adı, numara) ek sayılmaz.
    assert not arama._ekli_uyar(["idareci1"], "idareci") and not arama._ekli_uyar(["tahta-12"], "tahta")
    assert yollar("idareci1", "yonetici", devingen) == [] and yollar("yedekler2", "yonetici", devingen) == []
    # Ekli eşleşme de rol süzmesinden SONRA çalışır: idareci "ayarları", "yedeklerim" yazınca yönetici sayfası çıkmaz.
    for sorgu in ("ayarları", "yedeklerim", "gruplarım", "kullanıcıları", "şablonları"):
        assert not [y for y in yollar(sorgu, "idareci", devingen) if any(p in y for p in YONETICI_YOL_PARCALARI)], sorgu
    assert "/yedekler" in yollar("yedeklerim", "yonetici", devingen)
    # Kişi adına benzeyen sözcük ekli eşleşmeyle de bir şey bulmaz (dizinde kişi yok).
    for sorgu in ("Uydurma", "Uydurmanın", "Uydurma KİŞİ", "uydurmaaciklama"):
        assert yollar(sorgu, "yonetici", devingen) == [], sorgu


def test_sorgudan_yazdirilamayan_karakterler_atilir():
    assert arama.sorgu_duzelt("zil\x00\x01 saat\u202ei\u200b") == "zil saati"
    assert arama.sorgu_duzelt("\x00\u202e") == "" and arama.sorgu_duzelt("9/A\tşube\n") == "9/A şube"
    assert arama.ara("\u202ezil", SABIT, [], "yonetici")["sorgu"] == "zil"


ORNEK_GOREVLER = [
    ("9/a", "ikisi", "/yoklama/sube?sube=9%2FA", 1),
    ("pus", "ikisi", "/ogretmenler", 1),
    ("yed", "yonetici", "/yedekler", 1),
    ("duy", "ikisi", "/duyurular/yeni", 3),
    ("kvk", "yonetici", "/ayarlar/veri", 1),
    ("yuz", "yonetici", "/ayarlar/yuzer", 1),
    ("zil", "ikisi", "/program?bolum=zil", 1),
    ("cev", "ikisi", "/tahtalar?durum=cevrimdisi", 1),
    ("maz", "ikisi", "/yoklama/mazeret", 1),
    ("aja", "yonetici", "/ekle", 1),
    ("fiz", "ikisi", "/tahta/2", 1),
    ("usb", "ikisi", "/usb-anahtarlar", 1),
    ("acil", "ikisi", "/acil", 1),
    ("kilit kodu", "yonetici", "/ayarlar/kilit", 1),
    ("ogretmen", "ikisi", "/ogretmenler", 1),
    ("sifre", "yonetici", "/ayarlar/kilit", 3),
    ("mazeret", "ikisi", "/yoklama/mazeret", 1),
    ("yedek", "yonetici", "/yedekler", 1),
    ("duyuru", "ikisi", "/duyurular", 1),
]


@pytest.mark.parametrize("sorgu, rol, hedef, sira", ORNEK_GOREVLER)
def test_ornek_gorevler_ilk_uc_sonucta(devingen, sorgu, rol, hedef, sira):
    """Şartname §7 ölçüt 9: en çok üç karakterle hedef ilk üç sonuçtadır; yöneticiye özel hedef idarecide hiç çıkmaz."""
    assert hedef in yollar(sorgu, "yonetici", devingen)[:sira], sorgu
    idareci = yollar(sorgu, "idareci", devingen)
    if rol == "ikisi":
        assert hedef in idareci[:sira], sorgu
    else:
        assert hedef not in idareci and not [y for y in idareci if any(p in y for p in YONETICI_YOL_PARCALARI)], sorgu


def test_sik_isler_metninde_kisi_kurum_adres_yok():
    assert len(arama.SIK_ISLER) == 23
    for o in arama.SIK_ISLER:
        assert set(o) <= {"ad", "yol", "sozcukler", "rol", "one"}, o["ad"]
        metin = f"{o['ad']} {o['sozcukler']}"
        assert not re.search(r"\d{1,3}\.\d{1,3}\.\d{1,3}", metin) and "@" not in metin, o["ad"]
        for yasak in ("Lisesi", "lisesi", "Ortaokulu", "Müdür", "müdür", "http", "www."):
            assert yasak not in metin, (o["ad"], yasak)


def test_metin_ilkelleri_ayar_bolumlerinden_gelir():
    """Tek harita: arama.py küçültme, katlama, sözcük ayırma ve "sözcük başı" kuralını yeniden yazmaz."""
    for ad in ("katla", "kucult", "samanlik", "sozcukler", "uyar", "SORGU_EN_UZUN"):
        assert getattr(arama, ad) is getattr(ayar_bolumleri, ad), ad
    for yasak in ("maketrans", "çğıöşü", "re.compile", ".lower()", "startswith(q"):
        assert yasak not in KAYNAK, yasak
    assert arama._saman("9/A", "e-Okul") == "9 a 9-a e-okul 9a e okul eokul"
