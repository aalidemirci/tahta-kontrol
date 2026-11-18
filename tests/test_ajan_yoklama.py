"""Tahta ajanının ders yoklaması (Aşama 5 şartnamesi, testler 43-48 ve ekleri).

Ağ çağrıları sahte istemciyle yapılır; arka plan işleri eşzamanlı çalışır. Ad, numara, kod ve PIN uydurmadır.
"""

from __future__ import annotations

import io
import json
import socket
import tarfile
import time
from pathlib import Path

import pytest

BELIRTEC = "GIZLI-YOKLAMA-BELIRTECI-xyz789"
ONERI = {
    "etkin": True,
    "tarih": "2026-11-16",
    "tarih_yazi": "16.11.2026 Pazartesi",
    "ders_saatleri": [
        {"ders_no": 1, "baslangic": "08:20", "bitis": "09:00", "secilebilir": True},
        {"ders_no": 2, "baslangic": "09:10", "bitis": "09:50", "secilebilir": True},
        {"ders_no": 3, "baslangic": "10:00", "bitis": "10:40", "secilebilir": False},
    ],
    "ders_no_en_cok": 3,
    "oneri": {"sube": "10/A", "ders_no": 2, "ders_adi": "", "ogretmen": None},
    "subeler": ["9/B", "10/A"],
}
BASLAT = {"belirtec": BELIRTEC, "kalan_sn": 480, "bosta_sn": 180, "ogretmen": {"kod": "112", "etiket": "A. Örnek"}}
LISTE = {
    "sube": "10/A",
    "ders_no": 2,
    "ders_adi": "",
    "ogrenciler": [{"id": 381, "etiket": "Ayşe Y."}, {"id": 402, "etiket": "Burak K."}, {"id": 405, "etiket": "Cemre D."}],
    "yok": [],
    "baska_yoklama": False,
    "kalan_sn": 470,
    "mevcut": 3,
}


class SahteIstemci:
    """Yol → (durum kodu, yanıt) eşlemesiyle yanıt verir; gönderilen istekleri saklar. None = ağ hatası."""

    def __init__(self):
        self.yanitlar: dict[str, tuple[int | None, dict]] = {}
        self.istekler: list[tuple[str, dict]] = []

    def istek(self, yontem, yol, govde=None, zaman_asimi=15, ham=False):
        from tahta_ajan.baglanti import BaglantiHatasi

        self.istekler.append((yol, govde))
        yanit = self.yanitlar.get(yol, (200, {}))
        kod, yanit = yanit(govde) if callable(yanit) else yanit  # işlev: gövdeye göre yanıt (şubeye göre öneri)
        if kod is None:
            raise BaglantiHatasi("bağlantı koptu")
        return kod, yanit, {}

    def yollar(self) -> list[str]:
        return [y for y, _ in self.istekler]


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
    s.istemci.yanitlar.update({
        "/ajan/yoklama/oneri": (200, ONERI),
        "/ajan/yoklama/baslat": (200, BASLAT),
        "/ajan/yoklama/liste": (200, LISTE),
        "/ajan/yoklama/kaydet": (200, {"tamam": True, "yok_sayisi": 1, "mevcut": 3}),
        "/ajan/yoklama/bitir": (200, {"tamam": True}),
    })  # fmt: skip
    s.yapi = {"tahta_id": 1, "sunucu": "https://10.0.0.5:8788"}
    s.son_temas = time.time()
    s.yoklama_etkin = True
    s.arka_plan = lambda is_: is_()  # eşzamanlı
    s.bildir = lambda: None
    return s


def ac_ve_pin(servis, kod="112", pin="482913"):
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    servis.ekran_mesaji(1, {"tur": "yoklama_pin", "kod": kod, "pin": pin})
    return servis.gorunum()["yoklama"]


def metin(*iletiler) -> str:
    return json.dumps(iletiler, ensure_ascii=False)


# ---- 43 --------------------------------------------------------------------------------------
def test_ajan_yoklama_gorunumu_belirteci_icermez(servis):
    y = ac_ve_pin(servis)
    assert y["asama"] == "liste" and y["liste_yuklu"] and y["sube"] == "10/A" and y["ders_no"] == 2
    assert [o["etiket"] for o in y["ogrenciler"]] == ["Ayşe Y.", "Burak K.", "Cemre D."]
    assert y["ogretmen"] == {"kod": "112", "etiket": "A. Örnek"} and y["ders_metni"] == "2. ders (09:10–09:50)"
    assert servis.istemci.istekler[1] == ("/ajan/yoklama/baslat", {"kod": "112", "pin": "482913"})
    assert servis.istemci.istekler[2][1] == {"belirtec": BELIRTEC, "sube": "10/A", "ders_no": 2}
    # Belirteç ve PIN ekrana giden hiçbir iletide, durum özetinde ve tanılama metninde yoktur.
    tum = metin(*servis.gelen, servis.gorunum(), servis.durum_ozeti())
    assert BELIRTEC not in tum and "482913" not in tum


# ---- 44 --------------------------------------------------------------------------------------
def test_ajan_yoklama_durum_dosyasina_yazilmaz(servis, tmp_path):
    ac_ve_pin(servis)
    servis.ekran_mesaji(1, {"tur": "yoklama_isaret", "id": 402})
    servis._kaydet()
    servis._yanit_isle({"durum": "onayli", "ayar": {"okul_adi": "Deneme Anadolu Lisesi", "yoklama_etkin": True}})
    for dosya in (tmp_path / "durum").rglob("*"):
        if dosya.is_file():
            icerik = dosya.read_text(encoding="utf-8", errors="replace")
            assert "Burak" not in icerik and BELIRTEC not in icerik and "yoklama" not in icerik, dosya


# ---- 45 --------------------------------------------------------------------------------------
def test_ajan_yoklama_bosta_kalinca_kapanir(servis):
    ac_ve_pin(servis)
    servis._yoklama_denetle()
    assert servis.yoklama is not None
    servis.yoklama["son_dokunma"] -= 179
    servis._yoklama_denetle()
    assert servis.yoklama is not None  # 3 dk dolmadı
    servis.ekran_mesaji(1, {"tur": "yoklama_isaret", "id": 381})  # dokunma süreyi yeniler
    assert time.monotonic() - servis.yoklama["son_dokunma"] < 1
    servis.yoklama["son_dokunma"] -= 181
    servis._yoklama_denetle()
    # Sessizce kapanır: ileti yok, liste bellekten silinir, sunucuda oturum kapatılır.
    assert servis.yoklama is None and servis._yoklama_belirtec is None and servis.gorunum()["yoklama"] is None
    assert servis.istemci.istekler[-1] == ("/ajan/yoklama/bitir", {"belirtec": BELIRTEC})


def test_ajan_yoklama_oturum_suresi_dolunca_kapanir_ve_once_uyarir(servis):
    ac_ve_pin(servis)
    servis.yoklama["bitis"] = time.monotonic() + 50
    servis._yoklama_denetle()
    assert servis.gorunum()["yoklama"]["uyari"] is True and servis.gelen[-1]["yoklama"]["uyari"] is True
    servis.yoklama["bitis"] = time.monotonic() - 1
    servis._yoklama_denetle()
    assert servis.yoklama is None


# ---- 46 --------------------------------------------------------------------------------------
def test_ajan_cevrimdisiyken_yoklama_acilmaz_ileti_verir(servis):
    servis.son_temas = time.time() - 1000
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    y = servis.gorunum()["yoklama"]
    # K5: tahtadaki yoklama yardımcı kayıttır; sunucu yoksa öğretmen kâğıda yönlendirilir (e-Okul'a değil).
    assert y["asama"] == "ileti" and "kâğıda alın" in y["ileti"] and "e-Okul" not in y["ileti"]
    assert servis.istemci.istekler == [] and servis.durum_ozeti()["yoklama_acik"] is False
    servis.yoklama["ileti_bitis"] = time.monotonic() - 1
    servis._yoklama_denetle()
    assert servis.yoklama is None


def test_ajan_sinav_ve_acil_sururken_ve_kapaliyken_yoklama_acilmaz(servis):
    servis._yanit_isle({"durum": "onayli", "ayar": {"yoklama_etkin": False}})
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    assert servis.gorunum()["yoklama"]["ileti"] == "Ders yoklaması bu okulda etkin değil."
    assert servis.gorunum()["yoklama_etkin"] is False
    servis.yoklama = None
    servis.yoklama_etkin = True
    servis.acil = {"id": 1, "tur": "tatbikat", "baslik": "", "metin": "", "bitis": time.time() + 60}
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    assert servis.gorunum()["yoklama"]["ileti"].startswith("Acil yayın sürüyor")
    servis.yoklama, servis.acil = None, None
    servis._yanit_isle({"durum": "onayli", "ayar": {"sinav": {"kimlik": "sinav-1-salon-1", "salon": 1, "basla_sn": -60, "bitis_sn": 600}}})
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    assert servis.gorunum()["yoklama"]["ileti"] == "Sınav sürüyor; ders yoklaması açılamaz."
    assert servis.istemci.istekler == []


def test_ajan_ekran_yoksa_yoklama_acilmaz(servis):
    servis.ekranlar[1]["bilgi"]["arayuz"] = "yok"
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    assert servis.yoklama is None and servis.istemci.istekler == []


# ---- 47 --------------------------------------------------------------------------------------
def test_ajan_durum_ozeti_yalniz_yoklama_acik_bilgisini_tasir(servis):
    assert servis.durum_ozeti()["yoklama_acik"] is False and "yoklama" in servis.durum_ozeti()["yetenekler"]
    ac_ve_pin(servis)
    ozet = servis.durum_ozeti()
    assert ozet["yoklama_acik"] is True
    tum = metin(ozet)
    for gizli in ("10/A", "Ayşe", "A. Örnek", "112", BELIRTEC):
        assert gizli not in tum, gizli


# ---- 48 --------------------------------------------------------------------------------------
def test_ajan_paketi_yoklama_kisayolunu_icerir():
    from tahta_sunucu import paket

    paket.ajan_paketi.cache_clear()
    icerik = paket.ajan_paketi().icerik
    veri = icerik[icerik.index(b"data.tar.gz") + 60 :]
    with tarfile.open(fileobj=io.BytesIO(veri), mode="r:gz") as arsiv:
        uye = arsiv.getmember("./usr/share/applications/tahta-yoklama.desktop")
        kisayol = arsiv.extractfile(uye).read().decode("utf-8")
    assert uye.mode == 0o644
    assert "Name=Yoklama Al" in kisayol and "Exec=/usr/bin/tahta-ajan yoklama" in kisayol and "Categories=Education;" in kisayol


# ---- ekler -----------------------------------------------------------------------------------
def test_ajan_yoklama_tam_akis_isaret_onay_kaydet(servis):
    ac_ve_pin(servis)
    servis.ekran_mesaji(1, {"tur": "yoklama_isaret", "id": 402})
    servis.ekran_mesaji(1, {"tur": "yoklama_isaret", "id": 999})  # listede olmayan id yok sayılır
    assert servis.gorunum()["yoklama"]["yok"] == [402]
    servis.ekran_mesaji(1, {"tur": "yoklama_kaydet"})
    assert servis.gorunum()["yoklama"]["asama"] == "onay"
    servis.ekran_mesaji(1, {"tur": "yoklama_geri"})
    assert servis.gorunum()["yoklama"]["asama"] == "liste"
    servis.ekran_mesaji(1, {"tur": "yoklama_kaydet"})
    servis.ekran_mesaji(1, {"tur": "yoklama_onayla"})
    assert servis.istemci.istekler[-1] == ("/ajan/yoklama/kaydet", {"belirtec": BELIRTEC, "sube": "10/A", "ders_no": 2, "yok": [402]})
    y = servis.gorunum()["yoklama"]
    # Kaydedilince liste ve işaretler ekrandan ve bellekten silinir (M3); 3 sn ileti kalır.
    assert y["asama"] == "ileti" and y["ileti"] == "Kaydedildi: 1 öğrenci yok." and y["ogrenciler"] == [] and y["yok"] == []
    assert servis._yoklama_belirtec is None and servis.durum_ozeti()["yoklama_acik"] is False
    assert "Burak" not in metin(servis.gelen[-1])


def test_ajan_yoklama_kaydet_ag_hatasinda_liste_korunur_sonra_401_uyarir(servis):
    ac_ve_pin(servis)
    servis.ekran_mesaji(1, {"tur": "yoklama_isaret", "id": 381})
    servis.ekran_mesaji(1, {"tur": "yoklama_kaydet"})
    servis.istemci.yanitlar["/ajan/yoklama/kaydet"] = (None, {})
    servis.ekran_mesaji(1, {"tur": "yoklama_onayla"})
    y = servis.gorunum()["yoklama"]
    assert y["asama"] == "onay" and y["hata"] == "Kaydedilemedi; yeniden deneyin." and y["yok"] == [381]
    # Sunucu ilk isteği almış ve belirteci silmiş olabilir: yeniden denemede 401 → "kaydedilmiş olabilir".
    servis.istemci.yanitlar["/ajan/yoklama/kaydet"] = (401, {"hata": "Yoklama oturumu sona erdi; PIN'i yeniden girin."})
    servis.ekran_mesaji(1, {"tur": "yoklama_onayla"})
    y = servis.gorunum()["yoklama"]
    assert y["asama"] == "ileti" and "kaydedilmiş olabilir" in y["ileti"] and servis._yoklama_belirtec is None


def test_ajan_yoklama_pin_hatalari_ve_bekleme(servis):
    servis.istemci.yanitlar["/ajan/yoklama/baslat"] = (403, {"hata": "Öğretmen kodu ya da PIN hatalı.", "bekleme_sn": 0})
    y = ac_ve_pin(servis)
    assert y["asama"] == "pin" and y["hata"] == "Öğretmen kodu ya da PIN hatalı." and y["ogrenciler"] == []
    servis.ekran_mesaji(1, {"tur": "yoklama_pin", "kod": "11", "pin": "482913"})
    assert servis.gorunum()["yoklama"]["hata"] == "Öğretmen kodu 3 hanelidir."
    servis.istemci.yanitlar["/ajan/yoklama/baslat"] = (429, {"hata": "Çok fazla hatalı deneme. Biraz bekleyip yeniden deneyin.", "bekleme_sn": 120})
    servis.ekran_mesaji(1, {"tur": "yoklama_pin", "kod": "112", "pin": "000000"})
    y = servis.gorunum()["yoklama"]
    assert 118 <= y["bekleme"] <= 120
    istek_sayisi = len(servis.istemci.istekler)
    servis.ekran_mesaji(1, {"tur": "yoklama_pin", "kod": "112", "pin": "482913"})
    assert len(servis.istemci.istekler) == istek_sayisi  # beklemede sunucuya gidilmez
    servis.yoklama["bekleme_bitis"] = time.monotonic() - 1
    servis._yoklama_denetle()
    assert servis.gorunum()["yoklama"]["bekleme"] == 0 and servis.gorunum()["yoklama"]["hata"] == ""
    servis.istemci.yanitlar["/ajan/yoklama/baslat"] = (423, {"hata": "PIN'iniz kilitlendi.", "bekleme_sn": 0})
    servis.ekran_mesaji(1, {"tur": "yoklama_pin", "kod": "112", "pin": "482913"})
    assert servis.gorunum()["yoklama"]["asama"] == "ileti"


def test_ajan_yoklama_secim_sube_degisince_ders_saatleri_yenilenir(servis):
    oneri = dict(ONERI, oneri={"sube": None, "ders_no": None, "ders_adi": "", "ogretmen": None})
    servis.istemci.yanitlar["/ajan/yoklama/oneri"] = (200, oneri)
    y = ac_ve_pin(servis)
    assert y["asama"] == "liste" and not y["liste_yuklu"] and "/ajan/yoklama/liste" not in servis.istemci.yollar()
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "9/B"})
    assert servis.istemci.istekler[-1] == ("/ajan/yoklama/oneri", {"sube": "9/B"})
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "9/B", "ders_no": 3})  # başlamamış ders saati seçilemez
    assert servis.gorunum()["yoklama"]["ders_no"] is None
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "Uydurma/Z", "ders_no": 1})  # listede olmayan şube
    assert servis.gorunum()["yoklama"]["sube"] == "9/B"
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "9/B", "ders_no": 1})
    assert servis.istemci.istekler[-1] == ("/ajan/yoklama/liste", {"belirtec": BELIRTEC, "sube": "9/B", "ders_no": 1})
    servis.istemci.yanitlar["/ajan/yoklama/liste"] = (400, {"hata": "Bu ders saati henüz başlamadı."})
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "ders_no": 2})
    y = servis.gorunum()["yoklama"]
    assert y["ders_no"] is None and y["hata"] == "Bu ders saati henüz başlamadı." and not y["liste_yuklu"]


def test_ajan_yoklama_kapat_sunucuda_oturumu_bitirir(servis):
    ac_ve_pin(servis)
    servis.ekran_mesaji(1, {"tur": "yoklama_kapat"})
    assert servis.yoklama is None and servis.istemci.istekler[-1] == ("/ajan/yoklama/bitir", {"belirtec": BELIRTEC})


def test_ajan_eski_sunucu_yoklama_anahtari_gondermezse_dokunmaz(servis):
    servis.yoklama_etkin = None
    servis._yanit_isle({"durum": "onayli", "ayar": {"okul_adi": "Deneme"}})
    assert servis.yoklama_etkin is None and servis.gorunum()["yoklama_etkin"] is False
    servis.istemci.yanitlar["/ajan/yoklama/oneri"] = (404, {"detail": "Not Found"})
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    assert "desteklemiyor" in servis.gorunum()["yoklama"]["ileti"]


def test_ajan_yoklama_acikken_kilitli_tahtada_uyarili_kapatma_once_uyarir(servis):
    servis.kilitli = True
    ac_ve_pin(servis)
    basarili, cikti = servis.komut_uygula({"tur": "kapat", "veri": {"uyari_sn": 60, "neden": "Otomatik kapatma"}})
    assert basarili and "uyarısı gösterildi" in cikti and servis.kapatma is not None


def test_ajan_komut_istemcisine_durum_yayini_gitmez(servis, monkeypatch):
    from tahta_ajan import ayar
    from tahta_ajan.__main__ import yoklama as yoklama_komutu

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setattr(ayar, "YEREL_PORT", port)
    servis.ekranlar.clear()
    yerel = servis._yerel_sunucu()
    try:
        # Gerçek ekran yardımcısı gibi bağlanan istemci durum alır.
        ekran = socket.create_connection(("127.0.0.1", port), timeout=5)
        ekran.sendall(b'{"tur":"merhaba","arayuz":"gtk3","surum":"0.6.0"}\n')
        akis = ekran.makefile("rb")
        assert json.loads(akis.readline())["tur"] == "durum"
        # Kısa ömürlü komut istemcisi: "yoklama aç" der; ona hiçbir şey yazılmaz, ekran sayılmaz.
        komut = socket.create_connection(("127.0.0.1", port), timeout=5)
        komut.sendall(b'{"tur":"merhaba","arayuz":"komut"}\n')
        bitis = time.time() + 5
        while time.time() < bitis and not any(e["bilgi"].get("arayuz") == "komut" for e in servis.ekranlar.values()):
            time.sleep(0.05)
        servis.yayinla()
        komut.settimeout(0.5)
        with pytest.raises(socket.timeout):
            komut.recv(1)
        assert [e["arayuz"] for e in servis.durum_ozeti()["ekranlar"]] == ["gtk3"]
        komut.close()
        assert yoklama_komutu() == 0
        bitis = time.time() + 5
        while time.time() < bitis and (servis.yoklama is None or servis.yoklama["asama"] == "yukleniyor"):
            time.sleep(0.05)
        assert servis.yoklama is not None and servis.yoklama["asama"] == "pin"
        ekran.close()
    finally:
        yerel.shutdown()
        yerel.server_close()


def test_tani_raporunda_yoklama_kisayolu_satiri_var_listesi_yok(servis, monkeypatch):
    from tahta_ajan import tani

    ac_ve_pin(servis)
    monkeypatch.setattr(tani.sistem, "LINUX", True)
    for ad in dir(tani):
        if ad.startswith("_") and callable(getattr(tani, ad)) and ad not in ("_yoklama_kisayolu", "_oku", "_erisim"):
            monkeypatch.setattr(tani, ad, lambda *a, **k: ("bilgi", "-"))
    monkeypatch.setattr(tani.sistem, "ag_bilgisi", lambda *a: {})
    rapor = tani.topla("", 0, None, [], servis.sinav_tani_metni())
    satir = next(d for d in rapor["denetimler"] if d["ad"] == "Yoklama kısayolu")
    assert "tahta-yoklama.desktop" in satir["ayrinti"]
    assert "Ayşe" not in metin(rapor) and BELIRTEC not in metin(rapor)


# ---- 0.14.0: seçim ekranı, numara sırası, geç, sayfalama (sözleşme: tests/yoklama_sozlesme.json) ----------
# Sunucu yanıtları sözleşme dosyasındaki UYDURMA örneklerdir; sunucu çalıştırılmaz.
SOZLESME = json.loads(Path(__file__).with_name("yoklama_sozlesme.json").read_text(encoding="utf-8"))
UCLAR = SOZLESME["uclar"]
BELIRTEC1 = "UYDURMA-BELIRTEC-0001"


def ornek(uc: str, ad: str) -> dict:
    return UCLAR[uc]["ornekler"][ad]["yanit"]


def yeni_sunucu(servis, oneri="ders_suruyor", baslat="program_tahtayla_ayni", liste="ilk_ders"):
    """Sahte istemciyi 0.14.0 sunucusunun sözleşme yanıtlarıyla kurar."""
    servis.istemci.yanitlar.update({
        "/ajan/yoklama/oneri": (200, ornek("/ajan/yoklama/oneri", oneri)),
        "/ajan/yoklama/baslat": (200, ornek("/ajan/yoklama/baslat", baslat)),
        "/ajan/yoklama/liste": (200, ornek("/ajan/yoklama/liste", liste)),
        "/ajan/yoklama/kaydet": (200, {"tamam": True, "yok_sayisi": 1, "gec_sayisi": 2, "mevcut": 5}),
    })  # fmt: skip


def gorunum(servis) -> dict:
    return servis.gorunum()["yoklama"]


def kalabalik_liste(n: int, **ek) -> dict:
    """n kişilik uydurma liste (okul no sırasıyla; id = 1000 + sıra)."""
    liste = {"sube": "10/A", "ders_no": 3, "ders_adi": "", "yok": [], "gec": [], "gec_secilebilir": False,
             "baska_yoklama": False, "kalan_sn": 455, "mevcut": n,
             "ogrenciler": [{"id": 1000 + i, "etiket": f"{100 + i} Deneme Ö."} for i in range(n)]}  # fmt: skip
    liste.update(ek)
    return liste


def test_yetenek_yoklama_gec_bildirilir(servis):
    assert SOZLESME["yetenek"] == "yoklama_gec" and "yoklama_gec" in servis.durum_ozeti()["yetenekler"]


def test_sonraki_durum_ve_yerlesim_sozlesme_tablosuyla_ayni():
    from tahta_ajan import ekran
    from tahta_ajan import yoklama as kural
    from tahta_sunucu import maske

    for satir in SOZLESME["dongu"]["tablo"]:
        assert kural.sonraki_durum(satir["durum"], satir["gec_secilebilir"]) == satir["sonraki"], satir
    assert ekran.sonraki_durum is kural.sonraki_durum  # ekran dokunuşu ve servis AYNI işlevi kullanır
    for satir in SOZLESME["yerlesim"]["tablo"]:
        assert ekran.yoklama_yerlesim(satir["n"]) == (satir["sutun"], satir["satir"]), satir
        assert kural.sayfa_sayisi(satir["n"]) == satir["sayfa_sayisi"], satir
    # İki taraftaki tablo aynıdır (sunucu ad eşiğini, ajan ızgarayı buradan seçer).
    for n in range(0, 130):
        assert kural.yerlesim(min(n, kural.SAYFA_BOYU)) == maske.yoklama_yerlesim(n), n
        assert kural.sayfa_sayisi(n) == maske.yoklama_sayfa_sayisi(n), n
    assert kural.SAYFA_BOYU == SOZLESME["sinirlar"]["sayfa_boyu"] == ekran.YOKLAMA_SAYFA_BOYU
    assert kural.sayfa_dilimi(70, 0) == (0, 56) and kural.sayfa_dilimi(70, 1) == (56, 70) and kural.sayfa_dilimi(70, 9) == (56, 70)


def test_etiket_ayirma_sozlesme_ornekleri():
    from tahta_ajan import ekran

    for o in SOZLESME["etiket_ayirma"]["ornekler"]:
        assert ekran.ogrenci_dugme_metni(o["etiket"]) == (o["no"], o["ad"]), o
    # Eski "ad + soyad baş harfi" biçiminin çakışma eki üst satıra alınır (ad kısalsa da ek kesilmez).
    assert ekran.ogrenci_dugme_satirlari("Mehmet Ali Y. (23)") == ("(23)", "Mehmet Ali Y.")
    assert ekran.ogrenci_dugme_satirlari("123 Ayşe Y.") == ("123", "Ayşe Y.")
    assert ekran.ogrenci_dugme_satirlari("Ayşe (Su) Y.") == ("", "Ayşe (Su) Y.")


def test_liste_sunucu_sirasini_korur_ve_gec_gorunur(servis):
    yeni_sunucu(servis)
    y = ac_ve_pin(servis)
    # Öneri tam ve tek: PIN'den sonra liste doğrudan açılır; sıra sunucununki (okul no), ajan sıralamaz.
    assert y["asama"] == "liste" and y["liste_yuklu"] and (y["sube"], y["ders_no"]) == ("10/A", 3)
    assert [o["id"] for o in y["ogrenciler"]] == [14, 11, 12, 13, 15]
    assert [o["etiket"] for o in y["ogrenciler"]][:2] == ["9 Muhammed Emin Y.", "0215 Elif Su D. Ö."]
    assert y["yok"] == [13] and y["gec"] == [11] and y["gec_secilebilir"] is True
    assert (y["sayfa"], y["sayfa_sayisi"], y["tum_sayfalar_goruldu"]) == (0, 1, True)
    assert servis.istemci.istekler[2] == ("/ajan/yoklama/liste", {"belirtec": BELIRTEC1, "sube": "10/A", "ders_no": 3})


def test_ilk_derste_dongu_var_yok_gec_var_ve_kaydet_gec_gonderir(servis):
    yeni_sunucu(servis)
    ac_ve_pin(servis)

    def dokun(kimlik):
        servis.ekran_mesaji(1, {"tur": "yoklama_isaret", "id": kimlik})
        y = gorunum(servis)
        return "yok" if kimlik in y["yok"] else "gec" if kimlik in y["gec"] else "var"

    assert [dokun(12), dokun(12), dokun(12)] == ["yok", "gec", "var"]
    # Yeniden açılan listede: YOK kayıtlı öğrenci tek dokunuşla GEÇ, GEÇ kayıtlı öğrenci tek dokunuşla var olur.
    assert dokun(13) == "gec" and dokun(11) == "var"
    assert dokun(12) == "yok" and dokun(14) == "yok" and dokun(14) == "gec"
    y = gorunum(servis)
    assert y["yok"] == [12] and y["gec"] == [13, 14]
    servis.ekran_mesaji(1, {"tur": "yoklama_kaydet"})
    servis.ekran_mesaji(1, {"tur": "yoklama_onayla"})
    assert servis.istemci.istekler[-1] == (
        "/ajan/yoklama/kaydet", {"belirtec": BELIRTEC1, "sube": "10/A", "ders_no": 3, "yok": [12], "gec": [13, 14]},
    )  # fmt: skip
    assert set(servis.istemci.istekler[-1][1]) == set(UCLAR["/ajan/yoklama/kaydet"]["istek_anahtarlari"])
    y = gorunum(servis)
    assert y["asama"] == "ileti" and y["ileti"] == "Kaydedildi: 1 yok, 2 geç." and y["gec"] == [] and y["ogrenciler"] == []
    assert servis.yoklama["gec"] == set() and servis.yoklama["subeler_once"] == [] and servis.yoklama["oneri"] is None


def test_ilk_ders_disinda_gec_sunulmaz_ama_bos_gec_gonderilir(servis):
    yeni_sunucu(servis, liste="ucuncu_ders")
    y = ac_ve_pin(servis)
    assert y["gec_secilebilir"] is False and y["gec"] == []
    for _ in range(3):
        servis.ekran_mesaji(1, {"tur": "yoklama_isaret", "id": 13})
    assert gorunum(servis)["yok"] == [13] and gorunum(servis)["gec"] == []  # var → yok → var → yok
    servis.ekran_mesaji(1, {"tur": "yoklama_kaydet"})
    servis.ekran_mesaji(1, {"tur": "yoklama_onayla"})
    # Yetenekli ajan yeni sunucuya gec anahtarını boş liste dahil HER ZAMAN yollar (yoksa 400 alır).
    assert servis.istemci.istekler[-1][1] == {"belirtec": BELIRTEC1, "sube": "10/A", "ders_no": 3, "yok": [13], "gec": []}


def test_gec_secilemeyen_derste_sunucunun_gec_listesi_alinmaz(servis):
    yeni_sunucu(servis)
    servis.istemci.yanitlar["/ajan/yoklama/liste"] = (200, dict(ornek("/ajan/yoklama/liste", "ilk_ders"), gec_secilebilir=False))
    y = ac_ve_pin(servis)
    assert y["gec"] == [] and y["gec_secilebilir"] is False and y["yok"] == [13]


def test_eski_sunucu_yanitlariyla_dusmez_gec_sunmaz_gec_gondermez(servis):
    eski = SOZLESME["eski_sunucu"]
    servis.istemci.yanitlar.update({
        "/ajan/yoklama/oneri": (200, eski["/ajan/yoklama/oneri"]),
        "/ajan/yoklama/baslat": (200, eski["/ajan/yoklama/baslat"]),
        "/ajan/yoklama/liste": (200, eski["/ajan/yoklama/liste"]),
        "/ajan/yoklama/kaydet": (200, eski["/ajan/yoklama/kaydet"]["yanit"]),
    })  # fmt: skip
    y = ac_ve_pin(servis)
    # Bugünkü davranış: tahtanın önerisi tam → liste doğrudan; yeni alanlar boş.
    assert y["liste_yuklu"] and (y["sube"], y["ders_no"]) == ("10/A", 2)
    assert (y["gec"], y["gec_secilebilir"], y["subeler_once"], y["ders_adaylari"], y["devre_adi"]) == ([], False, [], [], "")
    assert y["simdiki_ders_no"] is None and y["sayfa_sayisi"] == 1
    for _ in range(2):  # geç yok: var ↔ yok
        servis.ekran_mesaji(1, {"tur": "yoklama_isaret", "id": 12})
    assert gorunum(servis)["yok"] == [13] and gorunum(servis)["gec"] == []
    servis.ekran_mesaji(1, {"tur": "yoklama_kaydet"})
    servis.ekran_mesaji(1, {"tur": "yoklama_onayla"})
    govde = servis.istemci.istekler[-1][1]
    assert govde == eski["/ajan/yoklama/kaydet"]["istek"] and "gec" not in govde
    assert gorunum(servis)["ileti"] == "Kaydedildi: 1 öğrenci yok."


def test_sube_secince_sunucunun_ders_onerisi_uygulanir_ve_liste_tek_dokunusla_acilir(servis):
    """0.13.1 kusuru: şube elle seçilince ajan öneri.ders_no'yu atıyordu; ders için ikinci dokunuş gerekiyordu."""
    yeni_sunucu(servis, oneri="subesiz_devir_saati", baslat="programsiz_ogretmen")
    cagrilar = {"10/B": dict(ornek("/ajan/yoklama/oneri", "ders_suruyor"), subeler_once=[]),
                "11/C": ornek("/ajan/yoklama/oneri", "ikili_egitim_subeli")}  # fmt: skip
    servis.istemci.yanitlar["/ajan/yoklama/oneri"] = lambda g: (200, cagrilar.get((g or {}).get("sube"), ornek("/ajan/yoklama/oneri", "subesiz_devir_saati")))
    y = ac_ve_pin(servis, kod="113")
    # Devir saati, şubesiz: ders saatleri gelmedi (saatsiz 1–12 görünür), hiçbir ders ön seçili değil, liste yok.
    assert y["asama"] == "liste" and not y["liste_yuklu"] and y["sube"] is None and y["ders_no"] is None
    assert all(d["baslangic"] == "" for d in y["ders_saatleri"]) and len(y["ders_saatleri"]) == 12
    assert "/ajan/yoklama/liste" not in servis.istemci.yollar()
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "10/B"})  # TEK dokunuş
    assert servis.istemci.istekler[-2] == ("/ajan/yoklama/oneri", {"sube": "10/B"})
    assert servis.istemci.istekler[-1] == ("/ajan/yoklama/liste", {"belirtec": "UYDURMA-BELIRTEC-0003", "sube": "10/B", "ders_no": 3})
    y = gorunum(servis)
    assert y["liste_yuklu"] and y["ders_no"] == 3 and y["ders_metni"] == "3. ders (10:00–10:40)" and y["simdiki_ders_no"] == 3
    # İkili eğitim: öğle şubesine geçince ders saatleri ve devre adı o şubeninkidir; öğlenin 1. dersi önerilir.
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "secim": True})
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "11/C"})
    y = gorunum(servis)
    assert (y["sube"], y["ders_no"], y["devre_adi"]) == ("11/C", 1, "Öğle") and y["ders_metni"] == "1. ders (13:30–14:10)"
    assert servis.istemci.istekler[-1][1] == {"belirtec": "UYDURMA-BELIRTEC-0003", "sube": "11/C", "ders_no": 1}


def test_subesiz_acilista_simdiki_ders_on_secilidir(servis):
    """Ders sürerken, öneri şubesi olmayan tahta: seçim görünümünde şimdiki ders seçili; şubeye tek dokunuş."""
    subesiz = dict(ornek("/ajan/yoklama/oneri", "ders_suruyor"), subeler_once=[],
                   oneri={"sube": None, "ders_no": None, "ders_adi": "", "ogretmen": None, "ders_adaylari": []})  # fmt: skip
    yeni_sunucu(servis, baslat="programsiz_ogretmen", liste="ucuncu_ders")
    servis.istemci.yanitlar["/ajan/yoklama/oneri"] = lambda g: (200, ornek("/ajan/yoklama/oneri", "ders_suruyor") if g else subesiz)
    y = ac_ve_pin(servis, kod="113")
    assert not y["liste_yuklu"] and y["sube"] is None and y["ders_no"] == 3 and y["simdiki_ders_no"] == 3
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "9/B"})
    assert servis.istemci.istekler[-1][1] == {"belirtec": "UYDURMA-BELIRTEC-0003", "sube": "9/B", "ders_no": 3}


def test_teneffuste_iki_aday_varken_liste_acilmaz_ders_sorulur(servis):
    yeni_sunucu(servis, oneri="teneffus_iki_aday", baslat="programsiz_ogretmen", liste="ucuncu_ders")
    y = ac_ve_pin(servis, kod="113")
    # Kimlik hangi dersin öğretmeni olduğunu göstermiyor: liste DOĞRUDAN AÇILMAZ, iki aday vurgulanır.
    assert y["asama"] == "liste" and not y["liste_yuklu"] and y["sube"] == "10/A" and y["ders_no"] is None
    assert y["ders_adaylari"] == [2, 3] and "/ajan/yoklama/liste" not in servis.istemci.yollar()
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "ders_no": 2})  # "biten 2. ders"
    assert servis.istemci.istekler[-1][1] == {"belirtec": "UYDURMA-BELIRTEC-0003", "sube": "10/A", "ders_no": 2}
    assert gorunum(servis)["liste_yuklu"] and gorunum(servis)["ders_adaylari"] == []


def test_teneffuste_ogretmen_programi_dersi_belirler(servis):
    """Tahta iki aday veriyor; /baslat yanıtındaki program önerisi aynı şube ve tek ders: liste doğrudan açılır."""
    yeni_sunucu(servis, oneri="teneffus_iki_aday", baslat="program_tahtayla_ayni", liste="ucuncu_ders")
    y = ac_ve_pin(servis)
    assert y["liste_yuklu"] and (y["sube"], y["ders_no"]) == ("10/A", 3)
    assert servis.istemci.yollar() == ["/ajan/yoklama/oneri", "/ajan/yoklama/baslat", "/ajan/yoklama/liste"]


def test_tahta_ile_ogretmen_programi_farkliysa_liste_acilmaz_ikisi_one_alinir(servis):
    yeni_sunucu(servis, baslat="program_tahtadan_farkli")
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    # PIN'den ÖNCE yalnız tahtanın şubeleri: öğretmene bağlı hiçbir bilgi doğrulanmadan görünüme girmez.
    assert gorunum(servis)["asama"] == "pin" and gorunum(servis)["subeler_once"] == ["10/A"]
    servis.ekran_mesaji(1, {"tur": "yoklama_pin", "kod": "112", "pin": "482913"})
    y = gorunum(servis)
    # Karar liste isteğinden ÖNCE: vekâlet/ders değişimi olağandır; tahtanın şubesi seçili kalır, liste açılmaz.
    assert "/ajan/yoklama/liste" not in servis.istemci.yollar()
    assert y["asama"] == "liste" and not y["liste_yuklu"] and (y["sube"], y["ders_no"]) == ("10/A", 3)
    assert y["subeler_once"] == ["10/A", "11/C", "9/B"]
    # Programda olmayan şube ve ders de seçilip açılabilir (program yalnız ön seçimdir).
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "10/A"})  # "Listeyi aç": seçili şubeye dokunuş
    assert servis.istemci.istekler[-1][1] == {"belirtec": "UYDURMA-BELIRTEC-0002", "sube": "10/A", "ders_no": 3}
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "secim": True})
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "9/A"})
    assert servis.istemci.istekler[-1][1]["sube"] == "9/A" and gorunum(servis)["liste_yuklu"]


def test_yalniz_ogretmen_onerisi_varsa_sube_ders_saatleri_istenir_sonra_liste(servis):
    yeni_sunucu(servis, oneri="subesiz_devir_saati", baslat="program_tahtadan_farkli")
    servis.istemci.yanitlar["/ajan/yoklama/oneri"] = lambda g: (
        200, ornek("/ajan/yoklama/oneri", "ikili_egitim_subeli" if g else "subesiz_devir_saati"))  # fmt: skip
    y = ac_ve_pin(servis)
    # Tahtanın şubesi yok, öğretmenin programı 11/C: o şubenin (öğle devresi) ders saatleri istenir, liste açılır.
    assert servis.istemci.yollar() == ["/ajan/yoklama/oneri", "/ajan/yoklama/baslat", "/ajan/yoklama/oneri", "/ajan/yoklama/liste"]
    assert servis.istemci.istekler[2][1] == {"sube": "11/C"}
    assert y["liste_yuklu"] and (y["sube"], y["ders_no"], y["devre_adi"]) == ("11/C", 1, "Öğle")
    assert y["subeler_once"] == ["11/C", "9/B"]


def test_elle_ders_secimi_devre_degisince_korunmaz_ayni_saatte_korunur(servis):
    """Kural 25: sabah saatleri görünürken 3. derse (10:00) dokunup öğle şubesi seçilince seçim öğlenin
    3. dersine (15:10) DÖNÜŞMEZ; sunucunun önerisine (öğlenin 1. dersi) dönülür."""
    sabah = dict(ornek("/ajan/yoklama/oneri", "ders_suruyor"), subeler_once=[],
                 oneri={"sube": None, "ders_no": None, "ders_adi": "", "ogretmen": None, "ders_adaylari": []})  # fmt: skip
    ogle = ornek("/ajan/yoklama/oneri", "ikili_egitim_subeli")
    ogle = dict(ogle, ders_saatleri=[dict(d, secilebilir=True) for d in ogle["ders_saatleri"]])
    yanitlar = {"11/C": ogle, "9/A": dict(sabah, oneri=dict(sabah["oneri"], ders_no=3))}
    yeni_sunucu(servis, baslat="programsiz_ogretmen", liste="ucuncu_ders")
    servis.istemci.yanitlar["/ajan/yoklama/oneri"] = lambda g: (200, yanitlar.get((g or {}).get("sube"), sabah))
    ac_ve_pin(servis, kod="113")
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "ders_no": 2})  # önce ders saatine dokunuldu (şube yok): elle
    assert gorunum(servis)["ders_no"] == 2 and servis.yoklama["ders_elle"] and "/ajan/yoklama/liste" not in servis.istemci.yollar()
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "9/A"})  # aynı devre: 2. ders 09:10 yine var → korunur
    assert servis.istemci.istekler[-1][1] == {"belirtec": "UYDURMA-BELIRTEC-0003", "sube": "9/A", "ders_no": 2}
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "secim": True})
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "11/C"})  # öğle: 2. ders 14:20 ≠ 09:10 → korunmaz
    assert servis.istemci.istekler[-1][1] == {"belirtec": "UYDURMA-BELIRTEC-0003", "sube": "11/C", "ders_no": 1}
    assert servis.yoklama["ders_elle"] is False and gorunum(servis)["ders_metni"] == "1. ders (13:30–14:10)"


def test_saatsiz_gorunumden_saatli_gorunume_elle_secim_korunmaz(servis):
    yeni_sunucu(servis, oneri="subesiz_devir_saati", baslat="programsiz_ogretmen", liste="ucuncu_ders")
    teneffus = ornek("/ajan/yoklama/oneri", "teneffus_iki_aday")
    servis.istemci.yanitlar["/ajan/yoklama/oneri"] = lambda g: (200, teneffus if g else ornek("/ajan/yoklama/oneri", "subesiz_devir_saati"))
    ac_ve_pin(servis, kod="113")
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "ders_no": 1})  # saatsiz 1–12 görünümünde "1"
    assert servis.yoklama["ders_elle"] and servis.yoklama["elle_saat"] == ""
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "10/A"})
    y = gorunum(servis)
    assert y["ders_no"] is None and y["ders_adaylari"] == [2, 3] and not y["liste_yuklu"]
    assert "/ajan/yoklama/liste" not in servis.istemci.yollar()


def test_secim_gorunumune_donup_ayni_sube_ve_derse_gelince_isaretler_korunur(servis):
    yeni_sunucu(servis)
    ac_ve_pin(servis)
    servis.ekran_mesaji(1, {"tur": "yoklama_isaret", "id": 12})
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "secim": True})
    y = gorunum(servis)
    # Seçim görünümünde liste ekrana gitmez; şube ve ders seçili kalır.
    assert not y["liste_yuklu"] and y["ogrenciler"] == [] and y["yok"] == [] and (y["sube"], y["ders_no"]) == ("10/A", 3)
    servis.ekran_mesaji(1, {"tur": "yoklama_isaret", "id": 14})  # seçim görünümünde işaret kabul edilmez
    servis.ekran_mesaji(1, {"tur": "yoklama_kaydet"})
    assert gorunum(servis)["asama"] == "liste"
    istek_sayisi = len(servis.istemci.istekler)
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "10/A"})
    y = gorunum(servis)
    assert y["liste_yuklu"] and y["yok"] == [12, 13] and len(servis.istemci.istekler) == istek_sayisi  # yeniden istenmedi


def test_sayfalama_butun_sayfalar_gorulmeden_kaydet_cikmaz_isaretler_korunur(servis):
    from tahta_ajan import ekran

    yeni_sunucu(servis, liste="ucuncu_ders")
    servis.istemci.yanitlar["/ajan/yoklama/liste"] = (200, kalabalik_liste(70))
    y = ac_ve_pin(servis)
    assert (y["sayfa"], y["sayfa_sayisi"], y["tum_sayfalar_goruldu"]) == (0, 2, False) and len(y["ogrenciler"]) == 70
    assert ekran.yoklama_ana_dugme(y) == ("Sonraki sayfa ›", "yoklama_sayfa")
    servis.ekran_mesaji(1, {"tur": "yoklama_isaret", "id": 1003})
    servis.ekran_mesaji(1, {"tur": "yoklama_kaydet"})  # ikinci sayfa görülmedi: onaya geçilmez
    assert gorunum(servis)["asama"] == "liste"
    servis.ekran_mesaji(1, {"tur": "yoklama_sayfa", "yon": -1})
    assert gorunum(servis)["sayfa"] == 0
    servis.ekran_mesaji(1, {"tur": "yoklama_sayfa", "yon": 5})  # geçersiz yön yok sayılır
    assert gorunum(servis)["sayfa"] == 0
    servis.ekran_mesaji(1, {"tur": "yoklama_sayfa", "yon": 1})
    y = gorunum(servis)
    assert (y["sayfa"], y["tum_sayfalar_goruldu"]) == (1, True) and ekran.yoklama_ana_dugme(y) == ("KAYDET", "yoklama_kaydet")
    servis.ekran_mesaji(1, {"tur": "yoklama_isaret", "id": 1069})
    servis.ekran_mesaji(1, {"tur": "yoklama_sayfa", "yon": 1})  # son sayfadan öteye gidilmez
    servis.ekran_mesaji(1, {"tur": "yoklama_sayfa", "yon": -1})
    y = gorunum(servis)
    assert y["sayfa"] == 0 and y["yok"] == [1003, 1069] and y["tum_sayfalar_goruldu"]  # işaretler sayfa değişince korunur
    servis.ekran_mesaji(1, {"tur": "yoklama_kaydet"})
    assert gorunum(servis)["asama"] == "onay"
    servis.ekran_mesaji(1, {"tur": "yoklama_geri"})
    servis.ekran_mesaji(1, {"tur": "yoklama_temizle"})
    y = gorunum(servis)
    assert y["yok"] == [] and y["gec"] == [] and len(y["ogrenciler"]) == 70 and y["tum_sayfalar_goruldu"]


def test_cozuculer_yeni_alanlari_sinirli_okur(servis):
    from tahta_ajan import servis as servis_mod

    sinir = SOZLESME["ajan"]["cozucu_sinirlari"]
    ham = dict(ornek("/ajan/yoklama/oneri", "ders_suruyor"))
    ham["subeler"] = [f"{d}/{h}" for d in (9, 10, 11, 12) for h in "ABCDEF"]
    ham["subeler_once"] = ham["subeler"][:10] + ["Uydurma/Z", 7, None, "9/A"]
    ham["oneri"] = dict(ham["oneri"], ders_adaylari=[2, 3, 4, "x", 99, 2])
    ham["simdiki_ders_no"] = 17  # ders saatlerinde yok
    ham["devre_adi"] = "S" * 80
    ham["ogretmen_adi"], ham["ders_adi"] = "Uydurma Öğretmen", "Uydurma Dersi"  # bilinmeyen alan yok sayılır
    oneri = servis_mod._oneri_coz(ham)
    assert oneri["subeler_once"] == ham["subeler"][: sinir["subeler_once"]] and len(oneri["subeler_once"]) == 6
    assert oneri["ders_adaylari"] == [2, 3] and len(oneri["ders_adaylari"]) == sinir["ders_adaylari"]
    assert oneri["simdiki_ders_no"] is None and len(oneri["devre_adi"]) == 20
    # simdiki_bitti yalnız geçerli bir "şimdiki ders" varken ve tam `true` ise okunur; eski sunucuda yoktur (False).
    assert oneri["simdiki_bitti"] is False and servis_mod._oneri_coz(dict(ham, simdiki_ders_no=3, simdiki_bitti=True))["simdiki_bitti"] is True
    assert servis_mod._oneri_coz(dict(ham, simdiki_ders_no=3, simdiki_bitti="evet"))["simdiki_bitti"] is False
    assert servis_mod._oneri_coz(dict(ham, simdiki_ders_no=3))["simdiki_bitti"] is False
    assert "Uydurma" not in metin(oneri)
    # /baslat önerisi: yalnız şube + ders no + adaylar; listede olmayan şube alınmaz; önerinin şubesi başa gelir.
    yanit = {"oneri": {"sube": "11/C", "ders_no": 3, "ders_adaylari": [], "ders_adi": "Uydurma Dersi", "ogretmen": "Uydurma"},
             "subeler_once": ["9/B", "11/C", "Uydurma/Z"] + ham["subeler"][:12]}  # fmt: skip
    ogretmen_oneri, once = servis_mod._baslat_oneri_coz(yanit, ham["subeler"])
    assert ogretmen_oneri == {"sube": "11/C", "ders_no": 3, "ders_adaylari": []}
    assert once[:2] == ["11/C", "9/B"] and len(once) == 6 and "Uydurma/Z" not in once
    assert servis_mod._baslat_oneri_coz({"oneri": {"sube": "Uydurma/Z", "ders_no": 1}}, ham["subeler"]) == (None, [])
    assert servis_mod._baslat_oneri_coz({}, []) == (None, []) and servis_mod._baslat_oneri_coz(None, []) == (None, [])
    # Geç id'leri listede olmalı; yok ile çakışan geç sayılmaz.
    yeni_sunucu(servis)
    servis.istemci.yanitlar["/ajan/yoklama/liste"] = (200, dict(ornek("/ajan/yoklama/liste", "ilk_ders"), gec=[11, 13, 999, "x", True]))
    y = ac_ve_pin(servis)
    assert y["gec"] == [11] and y["yok"] == [13] and sinir["gec_idleri_listede_olmali"]
    assert servis_mod.YOKLAMA_LISTE_SINIRI == sinir["gec"] == SOZLESME["sinirlar"]["liste_siniri"]


def test_gorunum_sozlesmedeki_ek_anahtarlari_tasir_belirtec_tasimaz(servis):
    yeni_sunucu(servis)
    y = ac_ve_pin(servis)
    assert set(SOZLESME["ajan"]["gorunum_ek_anahtarlar"]) <= set(y)
    yeni = servis._yoklama_yeni("yukleniyor")
    for anahtar, deger in SOZLESME["ajan"]["yoklama_yeni_ek_alanlar"].items():
        assert yeni[anahtar] == (set() if deger == "set()" else deger), anahtar
    for ileti in SOZLESME["ajan"]["ekran_iletileri"].values():
        servis.ekran_mesaji(1, ileti)  # üç ileti de tanınır (düşmez)
    tum = metin(*servis.gelen, servis.gorunum(), servis.durum_ozeti())
    assert BELIRTEC1 not in tum and "482913" not in tum


def test_yeni_alanlar_durum_dosyasina_gunluge_ve_ozete_yazilmaz(servis, tmp_path, caplog):
    yeni_sunucu(servis, baslat="program_tahtadan_farkli")
    with caplog.at_level("DEBUG"):
        ac_ve_pin(servis)
        servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "10/A"})
        servis.ekran_mesaji(1, {"tur": "yoklama_isaret", "id": 12})
        servis.ekran_mesaji(1, {"tur": "yoklama_isaret", "id": 12})
        assert gorunum(servis)["gec"] == [11, 12]
        servis._kaydet()
        ozet = metin(servis.durum_ozeti(), list(servis.olaylar))
    for dosya in (tmp_path / "durum").rglob("*"):
        if dosya.is_file():
            icerik = dosya.read_text(encoding="utf-8", errors="replace")
            for gizli in ("Elif", "0215", "subeler_once", "11/C", "ders_adaylari", "gec", BELIRTEC1, "UYDURMA-BELIRTEC"):
                assert gizli not in icerik, (dosya, gizli)
    for gizli in ("Elif", "0215", "11/C", "9/B", "UYDURMA-BELIRTEC", "subeler_once"):
        assert gizli not in ozet and gizli not in caplog.text, gizli
    # Kapanınca hepsi bellekten atılır.
    servis.ekran_mesaji(1, {"tur": "yoklama_kapat"})
    assert servis.yoklama is None and servis._yoklama_belirtec is None


def test_ekran_yoklama_yardimcilari():
    from tahta_ajan import ekran

    y = {"sube": "10/A", "ders_no": 3, "ders_metni": "3. ders (09:50–10:30)", "ders_adi": "",
         "ogretmen": {"kod": "112", "etiket": "A. Örnek"},
         "ders_saatleri": [{"ders_no": 3, "baslangic": "09:50", "bitis": "10:30", "secilebilir": True}]}  # fmt: skip
    assert ekran.yoklama_ust_metni(y) == "10/A · 3. ders (09:50–10:30) · A. Örnek"
    assert ekran.yoklama_ders_basligi(y) == "3. ders 09:50–10:30"
    assert ekran.yoklama_ders_basligi({"ders_no": 4}) == "4. ders" and ekran.yoklama_ders_basligi({}) == "Ders seçilmedi"
    assert ekran.yoklama_sayi_metni(2, 1, 34) == "Yok: 2 · Geç: 1 · Derste: 32/34"
    assert ekran.yoklama_sayi_metni(2, 0, 34, gec_goster=False) == "Yok: 2 · Derste: 32/34"
    assert ekran.yoklama_onay_metni(["123 Ayşe Y.", "47 Burak K."], ["9 Cemre D."], 34) == (
        "Yok: 2 · Geç: 1 · Derste: 32/34", "YOK (2): 123 Ayşe Y., 47 Burak K.\n\nGEÇ (1): 9 Cemre D.")  # fmt: skip
    assert ekran.yoklama_onay_metni([], [], 70, 2, gec_goster=False) == ("Yok: 0 · Derste: 70/70\n2 sayfa · 70 öğrenci", "Bütün öğrenciler derste.")
    assert ekran.DURUM_YAZISI == {"var": "", "yok": "YOK", "gec": "GEÇ"}
    assert ekran.yoklama_liste_bilgisi({"ogrenciler": [1], "gec_secilebilir": True}) == "Olmayan öğrenciye dokunun. İkinci dokunuş: geç."
    assert ekran.yoklama_liste_bilgisi({"ogrenciler": [1]}) == "Olmayan öğrenciye dokunun."
    assert ekran.yoklama_pin_hatasi({"istek": True}) == "Doğrulanıyor…"
    assert ekran.yoklama_pin_hatasi({"bekleme": 30}).endswith("30 saniye bekleyin.")
    assert b"#yoklama-baslik" in ekran.STIL_OLCU and b"#ogrenci" in ekran.STIL_OLCU and b"#yoklama-ders" in ekran.STIL_OLCU
    assert ekran.YOKLAMA_RENKLERI in ekran.renk_stili({})
    assert "#ogrenci.gec" in ekran.YOKLAMA_RENKLERI and "#ogrenci.yok" in ekran.YOKLAMA_RENKLERI
    assert "#secim.secili" in ekran.renk_stili({})


def test_ekran_secim_gorunumu_yardimcilari():
    from tahta_ajan import ekran

    # 15 şubeye kadar düzey sütunu yok; hepsi 5 sütunda.
    az = [f"{d}/{h}" for d in (9, 10, 11) for h in "ABCDE"]
    assert ekran.sube_izgarasi(az) == (az, 5, 4, [])
    # 60 şube (5 düzey x 12): yalnız seçili düzey gösterilir; sütun/satır bütün düzeylerde aynı (düğmeler oynamaz).
    cok = [f"{d}/{h}" for d in ("Hz", 9, 10, 11, 12) for h in "ABCDEFGHIJKL"]
    gosterilen, sutun, satir, duzeyler = ekran.sube_izgarasi(cok, "10")
    assert gosterilen == [f"10/{h}" for h in "ABCDEFGHIJKL"] and (sutun, satir) == (5, 4) and duzeyler == ["Hz", "9", "10", "11", "12"]
    assert ekran.sube_izgarasi(cok, "yok")[0][0] == "Hz/A"  # bilinmeyen düzey: ilk düzey
    # Bir düzeyde 20'den çok şube: 6 sütun; kaydırma yok.
    kalabalik = [f"9/{i}" for i in range(26)] + [f"10/{i}" for i in range(4)]
    assert ekran.sube_izgarasi(kalabalik, "9")[1:3] == (6, 5)
    assert ekran.sube_duzeyi("AMP 11/A") == "AMP 11" and ekran.sube_duzeyi("Rehberlik") == "Diğer"
    assert ekran.sube_duzeyleri(["9/A", "10/A", "9/B", "Kurs"]) == [("9", ["9/A", "9/B"]), ("10", ["10/A"]), ("Diğer", ["Kurs"])]
    assert ekran.ders_izgarasi(12) == (2, 6) and ekran.ders_izgarasi(8) == (2, 5) and ekran.ders_izgarasi(16) == (3, 6)
    d = {"ders_no": 3, "baslangic": "10:00", "bitis": "10:40"}
    assert ekran.ders_dugme_metni(d) == "3. ders\n10:00–10:40"
    assert ekran.ders_dugme_metni(d, 3) == "● 3. ders · şimdi\n10:00–10:40"
    # Az önce biten ders ön seçiliyse "şimdi" yazılmaz (sunucunun simdiki_bitti bayrağı).
    assert ekran.ders_dugme_metni(d, 3, (), True) == "● 3. ders · bitti\n10:00–10:40"
    assert ekran.ders_dugme_metni(d, 4, (), True) == "3. ders\n10:00–10:40"
    # Üst satırdaki dar düğmelerde uzun düzey adı kısalır (yalnız gösterim): iki Hazırlık şubesi ayırt edilir.
    assert (ekran.sube_kisa("Hazırlık/G"), ekran.sube_kisa("Hazırlık/C")) == ("Hz/G", "Hz/C")
    assert ekran.sube_kisa("10/A") == "10/A" and ekran.sube_kisa("AMP11/B") == "AMP./B" and ekran.sube_kisa("Rehberlik") == "Rehberlik"
    # [Temizle] iki dokunuş ister: ilk dokunuştan sonra kaç işaretin silineceğini sorar.
    assert ekran.yoklama_temizle_metni(3, False) == ekran.yoklama_temizle_metni(0, True) == "Temizle"
    assert ekran.yoklama_temizle_metni(3, True) == "Hepsini sil (3)" and ekran.YOKLAMA_TEMIZLE_ONAY_SN >= 3
    assert ekran.ders_dugme_metni(d, None, [2, 3]) == "başlayacak 3. ders\n10:00–10:40"
    assert ekran.ders_dugme_metni(dict(d, ders_no=2), None, [2, 3]).startswith("biten 2. ders")
    assert ekran.ders_dugme_metni({"ders_no": 7, "baslangic": "", "bitis": ""}) == "7. ders"
    assert ekran.yoklama_secim_bilgisi({"subeler": ["10/A"], "sube": "10/A", "ders_adaylari": [2, 3]}).startswith(
        "Teneffüs: biten 2. ders mi, başlayacak 3. ders mi?")  # fmt: skip
    assert ekran.yoklama_secim_bilgisi({"subeler": ["10/A"]}) == "Şubeye dokununca liste açılır."
    assert ekran.yoklama_secim_bilgisi({"subeler": []}).startswith("Öğrenci listesi yüklenmemiş")
    # Portre ekran: 3 sütun; yatayda sözleşme tablosu. Yazı boyu sınıfı ızgaraya göre.
    assert ekran.yoklama_izgara_olcusu(42) == (6, 7) and ekran.yoklama_izgara_olcusu(70) == (7, 8)
    assert ekran.yoklama_izgara_olcusu(56, dikey=True) == (4, 14) and ekran.yoklama_izgara_olcusu(10, dikey=True) == (3, 7)
    assert ekran.yoklama_izgara_olcusu(48, dikey=True) == (3, 16)
    assert [ekran.yoklama_yogunluk(*o) for o in ((6, 7), (6, 8), (7, 8), (3, 16))] == ["", "orta", "sik", "sik"]


def test_ekran_yoklama_sayfasinda_kaydirma_ve_sabit_dugme_olcusu_yok():
    """Seçim ve liste görünümü kaydırmasızdır: ScrolledWindow, FlowBox ve alana göre hesaplanan düğme boyu yok."""
    import re

    from tahta_ajan import ekran

    kaynak = Path(ekran.__file__).read_text(encoding="utf-8")
    sayfa = kaynak[kaynak.index("def _yoklama_liste_sayfasi") : kaynak.index("def _yoklama_onay_sayfasi")]
    assert "_kaydirma(" not in sayfa and "ScrolledWindow" not in sayfa and "FlowBox" not in kaynak
    for eski in ("yoklama_dugme_boyu", "YOKLAMA_HUCRE_PAYI", "yoklama_sutun(", "ToggleButton(label=ogrenci"):
        assert eski not in kaynak, eski
    # Öğrenci düğmesinde set_label yok (etiket yeniden kurulup hizalama kaybolmasın); durum yazısı ayrı etikette.
    dugme = kaynak[kaynak.index("def _ogrenci_etiketi") : kaynak.index("def _yoklama_gorunum")]
    assert "set_label" not in re.sub(r'""".*?"""', "", dugme, flags=re.S)
    # Ajanda maske/kısaltma/sıralama kodu yoktur: etiket yalnız sunucuda üretilir.
    assert "sorted(ogrenciler" not in kaynak and "kisalt" not in kaynak.lower().replace("kısalt", "")
