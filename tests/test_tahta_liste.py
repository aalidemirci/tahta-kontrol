"""Tahtalar listesinin saf kuralları (0.17.0; tahta_liste.py): satırın durumu ve birincil düğmesi, menü pasiflikleri,
gruplama, süzgeç, /islem hedef seçimi, dönüş adresi, tahta sayfası sekmesi. Uydurma veriyle."""

from __future__ import annotations

import pytest
from starlette.datastructures import FormData

from tahta_sunucu import tahta_liste
from tahta_sunucu.komut import KOMUT_ADI, KOMUT_OMRU


def gorunum(**ek) -> dict:
    """web.tahta_gorunumu çıktısının durum kuralına giren alanları (çevrimiçi, açık, güncel tahta)."""
    t = {
        "id": 7, "ad": "9-A", "derslik": "A-101", "bina": "", "kat": None, "cevrimici": True, "kilitli": False,
        "duyuru_var": False, "ekran_bagli": True, "oturum": "Öğretmen hesabı (ortak)", "son_gorulme": "şimdi",
        "surum": "0.17.0", "guncel": True, "acil_gorundu": False, "acil_yetenegi": True, "sinav": None,
        "sinav_yetenegi": True, "yoklama_acik": False, "ariza_sayisi": 0, "donanim_degisti": False,
        "program": {"kilit_kaynak": None, "acilis": None, "neden": None, "muaf": False, "bos_ders": None, "program_yetenegi": True},
    }  # fmt: skip
    t.update(ek)
    return t


def ozet(acil=False, kilit=False, **ek) -> dict:
    return tahta_liste.durum_ozeti(gorunum(**ek), acil, kilit)


def metinler(liste: dict) -> list[str]:
    return [r["m"] for r in liste["rozetler"]]


PROGRAM_KILIDI = {"kilit_kaynak": "program", "acilis": "10:40", "neden": "Teneffüs", "muaf": False, "bos_ders": None,
                  "program_yetenegi": True}  # fmt: skip
SINAV = {"sinav_id": 3, "salon_id": 1, "sinav_adi": "Deneme", "salon_adi": "Salon 1", "evre": "suruyor", "bitis_saat": "11:00"}


@pytest.mark.parametrize(
    ("ek", "acil", "birincil", "dugme", "durumlar", "ilk_rozet"),
    [
        # §1.5 çizelgesi (ilk uyan satır)
        ({}, True, "acik", None, ["acik"], "Açık"),  # 1: acil sürerken birincil düğme yok
        ({"sinav": SINAV}, False, "acik", {"yol": "/sinav/3", "ad": "Sınavı aç"}, ["acik"], "Açık"),  # 2: sınav → bağlantı
        ({"cevrimici": False, "kilitli": None}, False, "cevrimdisi", None, ["cevrimdisi"], "Çevrimdışı"),  # 3
        ({"ekran_bagli": False}, False, "sorun", {"tur": "tani", "ad": "Tanıla"}, ["sorun"], "Ekran yardımcısı yok"),  # 4
        ({"duyuru_var": True}, False, "duyuru", {"tur": "duyuru_kaldir", "ad": "Duyuruyu kaldır"}, ["duyuru"], "Duyuru ekranda"),  # 5
        ({"kilitli": True}, False, "kilitli", {"tur": "kilit_ac", "ad": "Kilidi aç"}, ["kilitli"], "Kilitli"),  # 6
        ({}, False, "acik", {"tur": "kilitle", "ad": "Kilitle"}, ["acik"], "Açık"),  # 7
        # ikincil durumlar süzgeç kümesine girer
        ({"duyuru_var": True, "kilitli": True}, False, "duyuru", {"tur": "duyuru_kaldir", "ad": "Duyuruyu kaldır"},
         ["duyuru", "kilitli"], "Duyuru ekranda"),
        ({"surum": "0.12.0", "guncel": False, "ariza_sayisi": 2}, False, "acik", {"tur": "kilitle", "ad": "Kilitle"},
         ["acik", "guncelleme", "ariza"], "Açık"),
        ({"kilitli": True, "program": PROGRAM_KILIDI}, False, "kilitli", {"tur": "kilit_ac", "ad": "Kilidi aç"},
         ["kilitli"], "Teneffüs kilidi · 10:40"),
        # sınav + çevrimdışı: bağlantı yine çıkar (komut değil); acil + sınav: düğme yok
        ({"sinav": SINAV, "cevrimici": False}, False, "cevrimdisi", {"yol": "/sinav/3", "ad": "Sınavı aç"}, ["cevrimdisi"], "Çevrimdışı"),
        ({"sinav": SINAV}, True, "acik", None, ["acik"], "Açık"),
    ],
)  # fmt: skip
def test_durum_ozeti_cizelgesi(ek, acil, birincil, dugme, durumlar, ilk_rozet):
    liste = ozet(acil, **ek)
    assert (liste["birincil"], liste["dugme"], liste["durumlar"]) == (birincil, dugme, durumlar)
    assert metinler(liste)[0] == ilk_rozet
    # Birincil düğme hiçbir durumda yıkıcı komut değildir.
    assert not liste["dugme"] or liste["dugme"].get("tur") not in ("kapat", "yeniden_baslat", "temizlik")


def test_rozet_metinleri_0160_panosuyla_ayni():
    assert metinler(ozet(True, acil_gorundu=True)) == ["Acil yayın ekranda", "Açık"]
    assert metinler(ozet(True, acil_yetenegi=False)) == ["Açık", "Eski ajan (yedek duyuru)"]
    assert metinler(ozet(True, acil_gorundu=True, cevrimici=False)) == ["Çevrimdışı"]  # çevrimdışında "ekranda" denmez
    assert metinler(ozet(ariza_sayisi=1, donanim_degisti=True)) == ["Açık", "Arıza", "Donanım değişti"]
    assert metinler(ozet(ariza_sayisi=3))[1] == "3 arıza"
    assert metinler(ozet(sinav=dict(SINAV, evre="giris"))) == ["Açık", "Sınav: giriş"]
    assert metinler(ozet(sinav=SINAV, sinav_yetenegi=False)) == ["Açık", "Sınav sürüyor · ajan güncellenmeli"]
    assert metinler(ozet(yoklama_acik=True)) == ["Açık", "Yoklama alınıyor"]
    program = {"kilit_kaynak": None, "muaf": True, "bos_ders": "3. ders (kapalı)", "program_yetenegi": True}
    assert metinler(ozet(cevrimici=False, program=program)) == ["Çevrimdışı", "Boş ders: 3. ders (kapalı)", "Programdan muaf"]
    eski = {"kilit_kaynak": None, "muaf": False, "bos_ders": None, "program_yetenegi": False}
    assert metinler(ozet(False, True, program=eski)) == ["Açık", "Ajan güncellenmeli"]  # sürümü güncel ama yeteneksiz
    assert metinler(ozet(False, True, program=eski, guncel=False)) == ["Açık", "Ajan güncellenmeli"]  # güncelleme rozeti bu metne döner
    assert metinler(ozet(False, False, program=eski, guncel=False)) == ["Açık", "Güncelleme var"]
    assert metinler(ozet(kilitli=True, program=dict(PROGRAM_KILIDI, neden="", acilis=None))) == ["Program kilidi"]
    # Arıza rozeti arıza listesine bağlanır; başka rozet bağlantı taşımaz.
    rozetler = ozet(ariza_sayisi=1, donanim_degisti=True)["rozetler"]
    assert [r.get("yol") for r in rozetler] == [None, "/arizalar?durum=hepsi&tahta=7", None]
    # Sınır: en çok 4 durum + 3 ek rozet; süzgeç kümesi (durumlar) kesilmez.
    cok = ozet(True, True, acil_gorundu=True, ekran_bagli=False, kilitli=True, guncel=False, ariza_sayisi=1, donanim_degisti=True,
               sinav=SINAV, yoklama_acik=True)  # fmt: skip
    assert len(cok["rozetler"]) == 7 and cok["durumlar"] == ["sorun", "kilitli", "guncelleme", "ariza"]
    assert ozet(cevrimici=False)["oturum"] == "" and "alt" not in ozet()  # kullanılmayan alan /api/durum'a gitmez


def test_menu_pasiflikleri():
    def menu(rol="idareci", **ek):
        t = gorunum(**ek)
        t["liste"] = tahta_liste.durum_ozeti(t)
        return {o["tur"]: o for o in tahta_liste.menu_ogeleri(t, rol)}

    acik = menu()
    assert {tur: o["pasif"] for tur, o in acik.items() if o["pasif"]} == {
        "kilit_ac": "kilitli değil", "duyuru_kaldir": "ekranda duyuru yok", "guncelle": "güncel (0.17.0)", "uyandir": "tahta açık",
    }  # fmt: skip
    assert not acik["kilitle"]["pasif"] and not acik["tani"]["pasif"] and not acik["kapat"]["pasif"]
    kilitli = menu(kilitli=True, duyuru_var=True, surum="0.12.0", guncel=False)
    assert [tur for tur, o in kilitli.items() if o["pasif"]] == ["uyandir"]
    # Çevrimdışı: kısa ömürlü yıkıcı komutlar pasif; tanılama ve güncelleme kuyrukta bekler (etkin), uzaktan aç etkin.
    kapali = menu(cevrimici=False, kilitli=None, surum="0.12.0", guncel=False)
    assert {tur for tur, o in kapali.items() if o["pasif"]} == {"kapat", "yeniden_baslat"}
    assert kapali["kapat"]["pasif"] == "çevrimdışı" and kapali["tani"]["alt"] == "bağlanınca çalışır" and not acik["tani"]["alt"]
    # Çevrimdışı tahtada etkin kalan HER komut akıbetini söyler (komut ömründen): kısa ömürlü düşer, uzun ömürlü bekler.
    assert {tur: o["alt"] for tur, o in kapali.items() if o["alt"]} == {
        "kilitle": "10 dk bağlanmazsa düşer", "kilit_ac": "10 dk bağlanmazsa düşer",
        "duyuru_kaldir": "10 dk bağlanmazsa düşer", "tani": "bağlanınca çalışır", "guncelle": "bağlanınca çalışır",
        "uyandir": "çoğu cihazda çalışmaz",
    }  # fmt: skip
    assert not any(o["alt"] for o in acik.values())
    assert not kapali["kilit_ac"]["pasif"] and not kapali["duyuru_kaldir"]["pasif"]  # bayat durumla engellenmez
    hic = menu(cevrimici=False, surum="", guncel=False)  # hiç bağlanmamış tahta: güncelle etkin
    assert not hic["guncelle"]["pasif"]
    # Sıra ve rol: "Bilgiler ve düzenle" idareciye hiç çizilmez; bugünkü 8 komut eksiksiz.
    sira = [o["tur"] for o in tahta_liste.menu_ogeleri(dict(gorunum(), liste=ozet()), "yonetici")]
    assert sira == ["duyuru", "kilitle", "kilit_ac", "duyuru_kaldir", "tani", "guncelle", "uyandir", "ayrinti", "bilgiler", "",
                    "kapat", "yeniden_baslat"]  # fmt: skip
    assert "bilgiler" not in acik and "bilgiler" in menu("yonetici")
    assert menu("yonetici")["bilgiler"]["yol"] == "/tahta/7?sekme=bilgiler" and acik["duyuru"]["yol"] == "/duyurular/yeni?tahta=7"
    assert [o["bicim"] for o in acik.values() if o["tur"] in ("kapat", "yeniden_baslat")] == ["onay", "onay"]


def test_gruplama_ve_siralama():
    def t(ad, bina="", kat=None, derslik=""):
        return gorunum(ad=ad, bina=bina, kat=kat, derslik=derslik)

    tahtalar = [
        t("Kütüphane"), t("Z-2", "Çınar Blok", 0), t("b-1", "a blok", 1, "A-102"), t("A-1", "A Blok", 1, "A-101"),
        t("Ç-1", "A  Blok", 2), t("I-1", "C Blok"), t("Kat-3", "", 3), t("ç-2", "A Blok", 1, "A-101"),
    ]  # fmt: skip
    gruplar = tahta_liste.gruplar(tahtalar)
    assert [g["ad"] for g in gruplar] == [
        "a blok · 1. kat", "A  Blok · 2. kat".replace("  ", " "), "C Blok", "Çınar Blok · Zemin kat", "3. kat", "Konumu belirtilmemiş",
    ]  # fmt: skip
    assert all(g["baslik"] for g in gruplar)
    # Bina anahtarı büyük/küçük harf ve boşluk duyarsız; grup içi derslik, sonra ad (Türk abecesi: A < Ç).
    assert [x["ad"] for x in gruplar[0]["tahtalar"]] == ["A-1", "ç-2", "b-1"]
    # Tek grup ve o da konumsuzsa başlık çizilmez (düz liste).
    duz = tahta_liste.gruplar([t("B"), t("a")])
    assert len(duz) == 1 and duz[0]["baslik"] is False and [x["ad"] for x in duz[0]["tahtalar"]] == ["a", "B"]
    assert tahta_liste.gruplar([t("X", "A Blok")])[0]["baslik"] is True and tahta_liste.gruplar([]) == []


def test_sayilar_ve_suzgec_cozumu():
    tahtalar = [gorunum(), gorunum(kilitli=True), gorunum(cevrimici=False, ariza_sayisi=1), gorunum(duyuru_var=True, kilitli=True)]
    for t in tahtalar:
        t["liste"] = tahta_liste.durum_ozeti(t)
    assert tahta_liste.sayilar(tahtalar) == {
        "hepsi": 4, "cevrimici": 3, "acik": 1, "kilitli": 2, "duyuru": 1, "sorun": 0, "cevrimdisi": 1, "guncelleme": 0, "ariza": 1,
    }  # fmt: skip
    assert list(tahta_liste.SUZGECLER) == ["acik", "kilitli", "duyuru", "sorun", "cevrimdisi", "guncelleme", "ariza"]
    for deger in tahta_liste.SUZGECLER:
        assert tahta_liste.suzgec_coz(deger) == deger
    for deger in ("", None, "hepsi", "ACIK", "acik ", "<script>", "acil_ekranda", 5):
        assert tahta_liste.suzgec_coz(deger) == ""


def hedef(*ciftler) -> dict:
    return tahta_liste.islem_hedefi(FormData(list(ciftler)))


def test_islem_hedefi_dallari_sirali_ve_dusmesiz():
    isaretli = [("tahta", "1"), ("tahta", "2"), ("tahta", "3")]
    # tek: yalnız o tahta; formdaki tur ve işaretli liste okunmaz
    assert hedef(("tek", "kilitle:2"), ("tur", "kapat"), *isaretli) == {"dal": "tek", "tur": "kilitle", "id": 2}
    assert tahta_liste.TEK_TURLERI == set(KOMUT_ADI) - {"duyuru", "temizlik"}
    for tur in tahta_liste.TEK_TURLERI:
        assert hedef(("tek", f"{tur}:5"))["dal"] == "tek"
    # tek bozuksa listeye düşülmez
    for bozuk in ("sil:2", "kapat", ":2", "kilitle:2:3", "", "kilitle:", "kilitle:-1", "kilitle: 2", "KILITLE:2", "kilitle:2 ",
                  "duyuru:2", "kilitle:12345678901", "kilitle:2\n", "kilitle:2\r\n", "\nkilitle:2", "kilitle:02", "kilitle:0",
                  "kilitle:٢", "kilitle:²"):  # fmt: skip
        assert hedef(("tek", bozuk), ("tur", "kilitle"), *isaretli) == {"hata": "Bilinmeyen işlem."}, bozuk
    assert hedef(("tek", "temizlik:2"), *isaretli) == {"hata": "Oturum temizliği tahta sayfasından başlatılır."}
    assert hedef(("tek", "kilitle:9999999999")) == {"hata": "Tahta bulunamadı."}  # SQLite tamsayısını aşan kimlik
    assert hedef(("tek", "kilitle:1"), ("tek", "kilitle:2")) == {"hata": "Geçersiz istek."}
    assert hedef(("tek", "kilitle:1"), ("kapsam", "hepsi")) == {"hata": "Geçersiz istek."}
    # kapsam: yalnız hepsi, yalnız kilitle, yalnız başına
    assert hedef(("kapsam", "hepsi"), ("tur", "kilitle")) == {"dal": "kapsam", "tur": "kilitle"}
    assert tahta_liste.KAPSAM_HEPSI_TURLERI == {"kilitle"}
    for tur in sorted(set(KOMUT_ADI) - {"kilitle"}) + ["", "bilinmeyen"]:
        assert hedef(("kapsam", "hepsi"), ("tur", tur)) == {"hata": "Bu işlem bütün tahtalara birden verilemez."}, tur
    for deger in ("", "Hepsi", "secili", "hepsi "):
        assert hedef(("kapsam", deger), ("tur", "kilitle")) == {"hata": "Geçersiz istek."}, deger
    assert hedef(("kapsam", "hepsi"), ("kapsam", "hepsi"), ("tur", "kilitle")) == {"hata": "Geçersiz istek."}
    assert hedef(("kapsam", "hepsi"), ("tur", "kilitle"), ("tahta", "1")) == {"hata": "Geçersiz istek."}
    # liste (0.16.0 yolu): önce seçim, sonra tür
    assert hedef(("tur", "kapat"), *isaretli, ("tahta", "x"), ("tahta", "99999999999")) == {"dal": "liste", "tur": "kapat", "idler": [1, 2, 3]}
    assert hedef(("tur", "kilitle")) == {"hata": "Önce en az bir tahta seçin."}
    assert hedef(("tur", "sil"), *isaretli) == {"hata": "Bilinmeyen işlem."}
    # Komut ömürleri bu sürümde değişmedi (kural 8).
    assert (KOMUT_OMRU["kapat"], KOMUT_OMRU["yeniden_baslat"], KOMUT_OMRU["kilitle"], KOMUT_OMRU["temizlik"]) == (120, 120, 600, 120)


def test_guvenli_donus_ve_liste_yolu():
    for iyi in ("/", "/tahtalar", "/tahtalar?durum=kilitli", "/tahta/3?sekme=bakim#envanter"):
        assert tahta_liste.guvenli_donus(iyi) == iyi
    for kotu in ("//ornek.invalid", "/\\ornek.invalid", "https://ornek.invalid/", "tahtalar", "", None, "/a\nb", "/a\x7f", "/" + "a" * 200, 5):
        assert tahta_liste.guvenli_donus(kotu) == "/tahtalar", kotu
    assert tahta_liste.guvenli_donus("//x", "/program") == "/program"
    for yol in ("/", "/tahtalar", "/tahtalar?durum=acik", "/?durum=acik", "/tahtalar#t-2"):
        assert tahta_liste.liste_yolu_mu(yol), yol
    for yol in ("/tahta/3", "/tahtalar/ice-aktar", "/duyurular"):
        assert not tahta_liste.liste_yolu_mu(yol), yol


@pytest.mark.parametrize(
    ("deger", "rol", "durum", "yer", "beklenen"),
    [
        ("", "yonetici", "onayli", "", "genel"),
        ("genel", "idareci", "onayli", "", "genel"),
        ("program", "idareci", "onayli", "", "program"),
        ("bakim", "idareci", "bekliyor", "", "bakim"),
        ("bilgiler", "yonetici", "onayli", "", "bilgiler"),
        ("bilgiler", "idareci", "onayli", "", "genel"),  # sekme idareciye çizilmez
        ("bilgiler", None, "onayli", "", "genel"),
        ("program", "yonetici", "bekliyor", "", "genel"),  # program kutusu yalnız onaylıda
        ("", "yonetici", "bekliyor", "", "bilgiler"),  # onay formu ilk ekranda
        ("bilinmeyen", "yonetici", "bekliyor", "", "bilgiler"),
        ("", "idareci", "bekliyor", "", "genel"),
        ("BAKIM", "yonetici", "onayli", "", "genel"),
        ("", "idareci", "onayli", "temizlik", "bakim"),  # eski dönüş adresi ?yer=temizlik
        ("genel", "idareci", "onayli", "temizlik", "genel"),
        ("<script>", "yonetici", "onayli", "", "genel"),
    ],
)
def test_sekme_dogrulama(deger, rol, durum, yer, beklenen):
    assert tahta_liste.sekme_coz(deger, rol, durum, yer) == beklenen


def test_tek_coz_tam_eslesme_ister():
    assert tahta_liste.tek_coz("kilitle:1") == ("kilitle", 1) and tahta_liste.tek_coz("yeniden_baslat:1234567890") == ("yeniden_baslat", 1234567890)
    for bozuk in ("kilitle:1\n", "kilitle:01", "kilitle:0", " kilitle:1", "kilitle:1 ", "kilitle:", None, 5, b"kilitle:1", ["kilitle:1"]):
        assert tahta_liste.tek_coz(bozuk) is None, bozuk
