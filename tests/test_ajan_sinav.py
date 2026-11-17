"""Tahta ajanının sınav kipi ve gözetmen yoklaması (Aşama 4 şartnamesi, testler 30-36 ve ekleri).

Ağ çağrıları sahte istemciyle yapılır; arka plan işleri eşzamanlı çalışır. Veriler uydurmadır.
"""

from __future__ import annotations

import json
import time

import pytest


class SahteIstemci:
    """Yol → (durum kodu, yanıt) eşlemesiyle yanıt verir; gönderilen istekleri saklar."""

    def __init__(self):
        self.yanitlar: dict[str, tuple[int, dict]] = {}
        self.istekler: list[tuple[str, dict]] = []

    def istek(self, yontem, yol, govde=None, zaman_asimi=15, ham=False):
        self.istekler.append((yol, govde))
        kod, yanit = self.yanitlar.get(yol, (200, {}))
        return kod, yanit, {}


@pytest.fixture
def servis(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_AJAN_DIZIN", str(tmp_path / "ayar"))
    monkeypatch.setenv("TAHTA_AJAN_DURUM", str(tmp_path / "durum"))
    from tahta_ajan import servis as servis_mod

    monkeypatch.setattr(servis_mod.sistem, "kapat", lambda: "benzetim")
    monkeypatch.setattr(servis_mod.sistem, "yeniden_baslat", lambda: "benzetim")
    s = servis_mod.Servis()
    s.gelen = []
    s.ekranlar[1] = {"gonder": s.gelen.append, "bilgi": {"arayuz": "gtk3"}}
    s.istemci = SahteIstemci()
    s.yapi = {"tahta_id": 1, "sunucu": "https://10.0.0.5:8788"}
    s.son_temas = time.time()
    s.arka_plan = lambda is_: is_()  # eşzamanlı
    s.bildir = lambda: None  # bildirimi ağsız tut
    return s


LISTE = [
    {"k": 1, "a": "De*** Ka**", "n": "01", "s": "9/A"},
    {"k": 2, "a": "Ah*** Yı****", "n": "47", "s": "9/B"},
    {"k": 3, "a": "El** S* De***", "n": "03", "s": "10/A"},
]


def sinav(basla_sn=420, bitis_sn=2820, liste=True, **ek) -> dict:
    veri = {
        "kimlik": "sinav-12-salon-3",
        "salon": 3,
        "sinav_adi": "1. Dönem 1. Ortak Sınav",
        "salon_adi": "10/B Dersliği",
        "basla_sn": basla_sn,
        "bitis_sn": bitis_sn,
        "baslangic_saat": "10:00",
        "bitis_saat": "10:40",
        "dersler": [{"ad": "Matematik — 9. Sınıf", "bitis_saat": "10:40"}],
        "kurallar": "Sınav süresince konuşulmaz.",
        "yoklama_alindi": False,
    }
    if liste and basla_sn > 0:
        veri["liste"], veri["liste_fazla"] = [dict(o) for o in LISTE], 0
    veri.update(ek)
    return veri


def yanit(sinav_degeri, **ek) -> dict:
    return {"durum": "onayli", "ayar": {"okul_adi": "Deneme Anadolu Lisesi", "sinav": sinav_degeri, **ek}}


KOD_YANITI = {"belirtec": "GIZLI-BELIRTEC-abc123", "sure_sn": 900, "salon": 3, "liste": LISTE, "liste_fazla": 0,
              "gelmeyen": [], "basladi": True, "tahtadan_yoklama": True}  # fmt: skip


def gozetmen_ac(servis, yanit_=None):
    servis.istemci.yanitlar["/ajan/sinav/kod"] = (200, yanit_ or KOD_YANITI)
    servis.ekran_mesaji(1, {"tur": "gozetmen_kod", "kod": "123456"})
    return servis.gorunum()["sinav"]["gozetmen"]


# ---- 30 --------------------------------------------------------------------------------------
def test_servis_ayar_sinavi_ekrana_yayinlar_belirteci_yayinlamaz(servis):
    servis._yanit_isle(yanit(sinav()))
    g = servis.gorunum()["sinav"]
    assert g["evre"] == "giris" and g["sinav_adi"] == "1. Dönem 1. Ortak Sınav"
    assert 410 <= g["kalan_baslama"] <= 420 and g["liste"][1]["a"] == "Ah*** Yı****"
    assert servis.gelen and servis.gelen[-1]["sinav"]["salon_adi"] == "10/B Dersliği"
    assert "sinav" in servis.durum_ozeti()["yetenekler"]
    assert servis.durum_ozeti()["sinav"] == {"kimlik": "sinav-12-salon-3", "evre": "giris", "yerel_kapali": False}

    # Sınav sürerken gözetmen kodu doğrulanır; belirteç ekrana giden hiçbir iletide yoktur.
    servis._yanit_isle(yanit(sinav(basla_sn=-60)))
    gozetmen = gozetmen_ac(servis)
    assert gozetmen["durum"] == "menu" and gozetmen["basladi"] and gozetmen["tahtadan_yoklama"]
    assert servis.istemci.istekler[-1] == ("/ajan/sinav/kod", {"salon": 3, "kod": "123456"})
    servis.ekran_mesaji(1, {"tur": "gozetmen_yoklama"})
    assert servis.gorunum()["sinav"]["gozetmen"]["liste"][0]["k"] == 1
    for ileti in servis.gelen + [servis.gorunum(), servis.durum_ozeti()]:
        assert "GIZLI-BELIRTEC" not in json.dumps(ileti, ensure_ascii=False)
    assert servis.durum_ozeti()["sinav"]["evre"] == "yoklama"

    # Durum özetinde (sunucuya giden) ad ya da liste yoktur.
    assert "Ah***" not in json.dumps(servis.durum_ozeti(), ensure_ascii=False)

    # null gelince sınav ekranı ve gözetmen oturumu kalkar.
    servis._yanit_isle(yanit(None))
    assert servis.gorunum()["sinav"] is None and servis.gozetmen is None


def test_servis_eski_sunucu_sinav_anahtari_gondermezse_dokunmaz_bozuk_deger_acmaz(servis):
    servis._yanit_isle(yanit(sinav()))
    servis._yanit_isle({"durum": "onayli", "ayar": {"okul_adi": "Deneme"}})
    assert servis.gorunum()["sinav"] is not None
    servis._yanit_isle(yanit(None))
    for bozuk in ({"kimlik": 3, "salon": 3, "basla_sn": 1, "bitis_sn": 9}, {"kimlik": "x", "salon": "3", "basla_sn": 1,
                  "bitis_sn": 9}, {"kimlik": "x", "salon": 3, "basla_sn": 1, "bitis_sn": 0}, "sinav"):  # fmt: skip
        servis._yanit_isle(yanit(bozuk))
        assert servis.gorunum()["sinav"] is None


def test_servis_giris_bitince_liste_bellekten_silinir(servis):
    servis._yanit_isle(yanit(sinav(basla_sn=2)))
    assert servis.gorunum()["sinav"]["liste"]
    servis.sinav["basla_mono"] = time.monotonic() - 1  # başlangıç geçti (sunucuya ulaşılamasa da)
    servis._sinav_denetle()
    assert servis.sinav["liste"] is None
    g = servis.gorunum()["sinav"]
    assert g["evre"] == "suruyor" and g["liste"] == []


# ---- 31 --------------------------------------------------------------------------------------
def test_servis_sinav_suresi_bitince_cevrimdisiyken_de_kaldirir(servis):
    servis._yanit_isle(yanit(sinav(basla_sn=-600, bitis_sn=5)))
    assert servis.sinav_ekrani_acik()
    servis.son_temas = time.time() - 300  # sunucu yok
    servis.sinav["bitis_mono"] = time.monotonic() - 0.1
    assert servis.gorunum()["sinav"] is None  # ekran süresinde kalkar
    servis._sinav_denetle()
    assert servis.sinav is None
    assert "Sınav süresi doldu; sınav ekranı kalktı." in servis.olaylar


def test_servis_sinav_suresi_tahtada_sekiz_saati_gecmez(servis):
    servis._yanit_isle(yanit(sinav(basla_sn=-1, bitis_sn=10**9)))
    assert servis.gorunum()["sinav"]["kalan_bitis"] <= 8 * 3600


# ---- 32 --------------------------------------------------------------------------------------
def test_servis_cevrimdisi_ac_sinav_ekranini_da_kapatir_kural_3(servis):
    servis.kilitli = True
    servis._yanit_isle(yanit(sinav(basla_sn=-60)))
    servis.ekran_mesaji(1, {"tur": "cevrimdisi_ac"})
    assert servis.sinav_ekrani_acik() and servis.kilitli  # sunucu ulaşılabilir: yok sayılır

    servis.son_temas = time.time() - 120
    servis.ekran_mesaji(1, {"tur": "cevrimdisi_ac"})
    assert not servis.sinav_ekrani_acik() and servis.kilitli is False
    assert servis.gorunum()["sinav"] is None
    assert "Sınav ekranı sunucuya ulaşılamadığı için tahtadan kapatıldı." in servis.olaylar
    assert servis.durum_ozeti()["sinav"]["yerel_kapali"] is True

    # Sunucu dönünce sınav hâlâ sürüyorsa ekran geri gelir.
    servis.son_temas = time.time()
    servis._yanit_isle(yanit(sinav(basla_sn=-200)))
    assert servis.sinav_ekrani_acik() and servis.gorunum()["sinav"]["evre"] == "suruyor"


# ---- 33 --------------------------------------------------------------------------------------
def test_servis_sinav_ekraninda_kilit_kodunu_kabul_etmez(servis):
    import hashlib

    tuz = "00" * 16
    servis.kilit_kodu = {"tuz": tuz, "tur": 1000,
                         "ozet": hashlib.pbkdf2_hmac("sha256", b"4321", bytes.fromhex(tuz), 1000).hex()}  # fmt: skip
    servis.kilitli = True
    servis._yanit_isle(yanit(sinav(basla_sn=-60)))
    servis.ekran_mesaji(1, {"tur": "kod", "kod": "4321"})
    assert servis.kilitli is True and servis.hatali_deneme == 0
    # Sınav bitince kod yine çalışır; alttaki kilit durumu korunmuştur.
    servis._yanit_isle(yanit(None))
    servis.ekran_mesaji(1, {"tur": "kod", "kod": "4321"})
    assert servis.kilitli is False


# ---- 34 --------------------------------------------------------------------------------------
def test_servis_sinavda_uyarili_kapatmayi_uygulamaz(servis):
    basarili, cikti = servis.komut_uygula({"tur": "kapat", "veri": {"uyari_sn": 60, "neden": "Otomatik kapatma"}})
    assert basarili and servis.kapatma is not None
    servis._yanit_isle(yanit(sinav()))  # sınav kipi gelince geri sayım iptal
    assert servis.kapatma is None
    basarili, cikti = servis.komut_uygula({"tur": "kapat", "veri": {"uyari_sn": 60, "neden": "Otomatik kapatma"}})
    assert (basarili, cikti) == (True, "Sınav sürüyor; otomatik kapatma uygulanmadı.")
    assert servis.kapatma is None
    basarili, cikti = servis.komut_uygula({"tur": "kapat", "veri": {}})  # idarenin açık isteği
    assert basarili and "uygulanacak" in cikti


# ---- 35 --------------------------------------------------------------------------------------
def test_servis_sinav_listesini_durum_dosyasina_yazmaz(servis, tmp_path):
    servis._yanit_isle(yanit(sinav(), kilit_kodu=None))
    servis.komut_uygula({"tur": "kilitle", "veri": {}})  # durum.json yazılır
    servis._yanit_isle(yanit(sinav(basla_sn=-30)))
    gozetmen_ac(servis)
    icerik = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "durum").rglob("*") if p.is_file())
    assert icerik  # dosya yazıldı
    for parca in ("Ah***", "sinav-12", "GIZLI-BELIRTEC", "10/B Dersliği", "123456"):
        assert parca not in icerik


# ---- 36 --------------------------------------------------------------------------------------
def test_servis_yoklama_kaydinda_isaretleri_bellekten_siler(servis):
    servis._yanit_isle(yanit(sinav(basla_sn=-60)))
    gozetmen_ac(servis)
    servis.ekran_mesaji(1, {"tur": "gozetmen_yoklama"})
    servis.istemci.yanitlar["/ajan/sinav/yoklama"] = (200, {"gelmeyen_sayisi": 1, "mevcut": 3, "gelen": 2})
    servis.ekran_mesaji(1, {"tur": "gozetmen_kaydet", "gelmeyen": [2, 99, "3", True]})
    yol, govde = servis.istemci.istekler[-1]
    assert yol == "/ajan/sinav/yoklama" and govde == {"belirtec": "GIZLI-BELIRTEC-abc123", "gelmeyen": [2]}
    assert servis.gozetmen is None  # belirteç, liste, işaretler bellekten atıldı
    g = servis.gorunum()["sinav"]
    assert g["bildirim"] == "Yoklama kaydedildi: 1 öğrenci gelmedi." and g["yoklama_alindi"] is True
    assert g["gozetmen"]["durum"] is None and g["gozetmen"]["liste"] == [] and g["liste"] == []


def test_servis_yoklama_hatasinda_isaretler_korunur(servis):
    servis._yanit_isle(yanit(sinav(basla_sn=-60)))
    gozetmen_ac(servis)
    servis.ekran_mesaji(1, {"tur": "gozetmen_yoklama"})
    servis.istemci.yanitlar["/ajan/sinav/yoklama"] = (400, {"hata": "Koltuk numarası geçersiz."})
    servis.ekran_mesaji(1, {"tur": "gozetmen_kaydet", "gelmeyen": [1, 3]})
    g = servis.gorunum()["sinav"]["gozetmen"]
    assert g["durum"] == "yoklama" and g["gelmeyen"] == [1, 3] and g["hata"] == "Koltuk numarası geçersiz."
    # Oturum sona erdiyse (401) işaretler tutulamaz; ekranda bildirim kalır.
    servis.istemci.yanitlar["/ajan/sinav/yoklama"] = (401, {"hata": "Gözetmen oturumu sona erdi; kodu yeniden girin."})
    servis.ekran_mesaji(1, {"tur": "gozetmen_kaydet", "gelmeyen": [1]})
    assert servis.gozetmen is None
    assert servis.gorunum()["sinav"]["bildirim"].startswith("Gözetmen oturumu sona erdi")


def test_servis_gozetmen_kodu_hatalari_ve_bekleme(servis, monkeypatch):
    # Aynı anda yanıt ve tekrar deneme: kayan nokta saat hassasiyetinden bağımsız.
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0)
    servis._yanit_isle(yanit(sinav(basla_sn=-60)))
    servis.istemci.yanitlar["/ajan/sinav/kod"] = (403, {"hata": "Kod geçersiz.", "kalan_deneme": 3})
    servis.ekran_mesaji(1, {"tur": "gozetmen_kod", "kod": "000000"})
    g = servis.gorunum()["sinav"]["gozetmen"]
    assert g["durum"] is None and g["hata"] == "Kod geçersiz. 3 deneme hakkı kaldı."

    servis.istemci.yanitlar["/ajan/sinav/kod"] = (429, {"hata": "…", "bekleme_sn": 300})
    servis.ekran_mesaji(1, {"tur": "gozetmen_kod", "kod": "000001"})
    istek_sayisi = len(servis.istemci.istekler)
    servis.ekran_mesaji(1, {"tur": "gozetmen_kod", "kod": "000002"})  # beklerken istek atılmaz
    assert len(servis.istemci.istekler) == istek_sayisi
    assert "5 dakika" in servis.gorunum()["sinav"]["gozetmen"]["hata"]

    servis.gozetmen_bekleme_bitis = 0
    servis.ekran_mesaji(1, {"tur": "gozetmen_kod", "kod": "12"})  # eksik hane: istek yok
    assert len(servis.istemci.istekler) == istek_sayisi
    servis.son_temas = time.time() - 300  # çevrimdışı: istek yok, kâğıda yönlendirir
    servis.ekran_mesaji(1, {"tur": "gozetmen_kod", "kod": "123456"})
    assert len(servis.istemci.istekler) == istek_sayisi
    assert "kâğıda" in servis.gorunum()["sinav"]["gozetmen"]["hata"]
    servis.ekran_mesaji(1, {"tur": "gozetmen_cikis"})
    assert servis.gorunum()["sinav"]["gozetmen"]["hata"] == ""


def test_servis_kalabalik_salonda_ve_baslamadan_tahtadan_yoklama_acilmaz(servis):
    servis._yanit_isle(yanit(sinav(basla_sn=300)))
    g = gozetmen_ac(servis, dict(KOD_YANITI, basladi=False))
    assert g["durum"] == "menu" and g["basladi"] is False
    servis.ekran_mesaji(1, {"tur": "gozetmen_yoklama"})
    assert servis.gorunum()["sinav"]["gozetmen"]["durum"] == "menu"  # "Sınav başlayınca açılır"
    servis.sinav["basla_mono"] = time.monotonic() - 1  # sınav başladı
    assert servis.gorunum()["sinav"]["gozetmen"]["basladi"] is True
    servis.ekran_mesaji(1, {"tur": "gozetmen_yoklama"})
    assert servis.gorunum()["sinav"]["gozetmen"]["durum"] == "yoklama"

    servis.ekran_mesaji(1, {"tur": "gozetmen_cikis"})
    g = gozetmen_ac(servis, dict(KOD_YANITI, liste_fazla=12, tahtadan_yoklama=False))
    assert g["tahtadan_yoklama"] is False
    servis.ekran_mesaji(1, {"tur": "gozetmen_yoklama"})
    assert servis.gorunum()["sinav"]["gozetmen"]["durum"] == "menu"


def test_servis_acil_sururken_gozetmen_kodu_istek_yapmaz(servis):
    servis._yanit_isle(yanit(sinav(basla_sn=-60), acil={"id": 4, "tur": "tatbikat", "baslik": "", "metin": "m",
                                                       "kalan_sn": 600}))  # fmt: skip
    servis.ekran_mesaji(1, {"tur": "gozetmen_kod", "kod": "123456"})
    assert not servis.istemci.istekler
    assert servis.gorunum()["sinav"]["gozetmen"]["hata"] == "Acil yayın sürüyor."


def test_tani_raporunda_sinav_kipi_satiri_kimlikle_listesiz(servis, monkeypatch):
    from tahta_ajan import tani

    alinan = {}
    monkeypatch.setattr(tani, "topla", lambda *a, **k: alinan.setdefault("arg", a) and {"denetimler": []})
    servis._yanit_isle(yanit(sinav()))
    servis.komut_uygula({"tur": "tani", "veri": {}})
    assert alinan["arg"][-1] == "giris (sinav-12-salon-3)"
    assert servis.sinav_tani_metni() == "giris (sinav-12-salon-3)"
    servis._yanit_isle(yanit(None))
    assert servis.sinav_tani_metni() == "yok"


def test_ekran_sinav_yardimcilari():
    from tahta_ajan import ayar, ekran

    assert ekran.sayac_metni(2812) == "46:52" and ekran.sayac_metni(3725) == "1:02:05" and ekran.sayac_metni(-3) == "00:00"
    assert ekran.baslama_metni("10:00", 412) == "Başlangıç 10:00 — 7 dk sonra"
    assert ekran.baslama_metni("10:00", 30) == "Başlangıç 10:00 — 1 dakika içinde"
    assert ekran.bitis_metni({"bitis_saat": "10:40", "dersler": [{"ad": "Matematik", "bitis_saat": "10:40"}]}) == "Bitiş 10:40"
    karma = {"bitis_saat": "11:00", "dersler": [{"ad": "Matematik — 9. Sınıf", "bitis_saat": "10:40"},
                                                {"ad": "Fizik — 10. Sınıf", "bitis_saat": "11:00"}]}  # fmt: skip
    assert ekran.bitis_metni(karma) == "Matematik — 9. Sınıf: 10:40\nFizik — 10. Sınıf: 11:00"
    assert [ekran.liste_sutun_sayisi(n) for n in (1, 20, 21, 40, 41, 60)] == [1, 1, 2, 2, 3, 3]
    assert 22 <= ekran.liste_punto(20, 1080) <= 44 and ekran.liste_punto(1, 0) == 44
    assert ekran.liste_hucreleri({"k": 2, "a": "Ah*** Yı****", "n": "47", "s": "9/B"}) == ("2", "Ah*** Yı****", "…47", "9/B")
    assert ekran.izgara_sutun(40) == 9 and ekran.izgara_sutun(60) == 11 and ekran.izgara_sutun(0) == 2
    assert ekran.koltuk_etiketi({"k": 5, "a": "Ah*** Yı****", "n": "47"}, True) == "5 · GELMEDİ\nAh*** Yı****\n…47"
    assert ekran.yoklama_engeli({"tahtadan_yoklama": False, "basladi": True}) == "Bu salonun yoklaması panelden alınır."
    assert ekran.yoklama_engeli({"tahtadan_yoklama": True, "basladi": False}) == "Sınav başlayınca açılır."
    assert ekran.yoklama_engeli({"tahtadan_yoklama": True, "basladi": True}) == ""
    stil = ekran.renk_stili(dict(ayar.VARSAYILAN_PALET))
    stil.encode("ascii")
    assert "#sinav-sayac.son { color: #fbbf24; }" in stil and "#koltuk:checked" in stil
    for ad in ("#sinav-adi", "#sinav-sayac", "#koltuk", "#gozetmen-baslik"):
        assert ad.encode() in ekran.STIL_OLCU


def test_servis_gozetmen_beklemesi_bitince_yayinlar_ve_iletiyi_siler(servis):
    servis._yanit_isle(yanit(sinav(basla_sn=-60)))
    servis.istemci.yanitlar["/ajan/sinav/kod"] = (429, {"hata": "…", "bekleme_sn": 300})
    servis.ekran_mesaji(1, {"tur": "gozetmen_kod", "kod": "000001"})
    assert servis.gorunum()["sinav"]["gozetmen"]["bekleme"] > 0
    servis.gozetmen_bekleme_bitis = time.monotonic() - 1
    servis._sinav_denetle()
    g = servis.gorunum()["sinav"]["gozetmen"]
    assert g["bekleme"] == 0 and g["hata"] == "" and servis.gozetmen_bekleme_bitis == 0.0


def test_ekran_gozetmen_kod_hatasi_beklemede_nedeni_yazar():
    from tahta_ajan import ekran

    # Vazgeç ile çıkılınca servis hatayı siler; bekleme sürüyorsa ekran nedeni yine yazar.
    assert ekran.gozetmen_kod_hatasi({"hata": "", "bekleme": 130}) == "Çok fazla hatalı deneme. 3 dakika sonra yeniden deneyin."
    assert ekran.gozetmen_kod_hatasi({"hata": "Kod geçersiz.", "bekleme": 0}) == "Kod geçersiz."
    assert ekran.gozetmen_kod_hatasi({"durum": "dogrulaniyor", "bekleme": 0}) == "Doğrulanıyor…"


def test_ekran_duyuru_duzeni_uzun_listeyi_sutunlara_boler():
    from tahta_ajan import ekran

    kisa = ekran.duyuru_duzeni("Toplantı 15:00'te.", 1080)
    assert kisa["sutunlar"] == [] and kisa["sinif"] == ""
    assert ekran.duyuru_duzeni("x" * 500, 1080)["sinif"] == "uzun"
    satirlar = [f"Ab*** Cd**** …{i:02d}  →  10/B Dersliği, koltuk {i}" for i in range(32)]
    duzen = ekran.duyuru_duzeni("Sınav oturma listesi · 9/A\n\n" + "\n".join(satirlar), 1080)
    assert duzen["ust"] == "Sınav oturma listesi · 9/A" and len(duzen["sutunlar"]) == 2
    assert sum(len(s.split("\n")) for s in duzen["sutunlar"]) == 32 and 20 <= duzen["punto"] <= 40
    assert len(ekran.duyuru_duzeni("\n".join(satirlar * 2), 1080)["sutunlar"]) == 3
    assert ekran.KURALLAR_EKRAN_SATIRI <= 8


def test_ekran_kurallar_metni_satir_sinirli():
    from tahta_ajan import ekran

    assert ekran.kurallar_metni("a\n\nb\n") == "a\nb"
    uzun = ekran.kurallar_metni("\n".join(f"Kural {i}" for i in range(18)))
    assert uzun.split("\n") == [f"Kural {i}" for i in range(7)] + ["Kural 7 …"]
