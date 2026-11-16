"""Tahta ajanının ders yoklaması (Aşama 5 şartnamesi, testler 43-48 ve ekleri).

Ağ çağrıları sahte istemciyle yapılır; arka plan işleri eşzamanlı çalışır. Ad, numara, kod ve PIN uydurmadır.
"""

from __future__ import annotations

import io
import json
import socket
import tarfile
import time

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
        kod, yanit = self.yanitlar.get(yol, (200, {}))
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


def test_ekran_yoklama_yardimcilari():
    from tahta_ajan import ekran

    y = {"sube": "10/A", "ders_metni": "3. ders (09:50–10:30)", "ders_adi": "", "ogretmen": {"kod": "112", "etiket": "A. Örnek"}}
    assert ekran.yoklama_ust_metni(y) == "10/A · 3. ders (09:50–10:30) · A. Örnek"
    assert ekran.yoklama_sayi_metni(2, 34) == "Yok: 2 · Mevcut: 32/34"
    assert ekran.yoklama_onay_metni(["Ayşe Y.", "Burak K."]) == ("2 öğrenci yok yazılacak:", "Ayşe Y., Burak K.")
    assert ekran.yoklama_onay_metni([]) == ("Bütün öğrenciler derste.", "")
    assert ekran.ogrenci_dugme_metni("Ayşe Y.", True) == "Ayşe Y.\nYOK"
    assert ekran.ogrenci_dugme_metni("Ayşe Y.", False) == "Ayşe Y."
    # Çakışma eki ayrı satırda: uzun ad üç noktayla kısalsa da adaşları ayıran ek görünür.
    assert ekran.ogrenci_dugme_metni("Mehmet Ali Y. (23)", False) == "Mehmet Ali Y.\n(23)"
    assert ekran.ogrenci_dugme_metni("Mehmet Ali Y. (57)", True) == "Mehmet Ali Y.\n(57) · YOK"
    assert ekran.ogrenci_etiket_parcalari("1047 A. Y.") == ("1047 A. Y.", "")
    assert ekran.ogrenci_etiket_parcalari("Ayşe (Su) Y.") == ("Ayşe (Su) Y.", "")
    assert ekran.ogrenci_uzun_mu("Muhammed Emin Ç.") and not ekran.ogrenci_uzun_mu("Ayşe Y.")
    assert b"#ogrenci.uzun" in ekran.STIL_OLCU
    assert ekran.yoklama_sutun(1920) == 6 and ekran.yoklama_sutun(800) == 2
    assert ekran.yoklama_pin_hatasi({"istek": True}) == "Doğrulanıyor…"
    assert ekran.yoklama_pin_hatasi({"bekleme": 30}).endswith("30 saniye bekleyin.")
    assert b"#yoklama-baslik" in ekran.STIL_OLCU and b"#ogrenci" in ekran.STIL_OLCU
    assert ekran.YOKLAMA_RENKLERI in ekran.renk_stili({})
