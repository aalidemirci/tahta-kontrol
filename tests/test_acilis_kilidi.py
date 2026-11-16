"""Açılışta kilit (0.9.0, G2): tahta açılınca ya da oturum açılınca, sunucuya ulaşılabiliyorsa kilitlenir.

Kararı sunucu verir (yeni `oturum_no` + genç oturum); ajan tarafı test_ajan_dugme.py'de. Veriler UYDURMADIR.
"""

from __future__ import annotations

import pytest
from test_program_panel import calistir, hazirla
from test_program_panel import durum as program_durumu
from yardimci import an, bekle, ileti, kimlik, kur_ve_gir, sorgu, tahta_ekle

YENI = {"kilitli": False, "yetenekler": ["acil", "duyuru_id", "program_kilidi", "dugme", "acilis_kilidi"],
        "ekranlar": [{"arayuz": "gtk3"}], "oturum": {"sinif": "ogretmen"}}  # fmt: skip


def kilit_kodu(panel, kod="4826"):
    panel.post("/ayarlar", data={"bolum": "genel", "okul_adi": "Örnek", "ok_saatler": "", "kilit_kodu": kod})


def oturum(no, yas=20, **ek):
    return dict(YENI, oturum_no=no, oturum_yasi_sn=yas, **ek)


def kilitler(yanit) -> list[dict]:
    return [k for k in yanit["komutlar"] if k["tur"] == "kilitle"]


@pytest.fixture
def okul(panel, tahta, saat):
    kur_ve_gir(panel)
    kilit_kodu(panel)
    return tahta_ekle(panel, tahta, "T-01", YENI, surum="0.9.0")


def test_yeni_oturumda_bir_kez_kilitlenir_ve_kayda_duser(panel, tahta, okul):
    yanit = bekle(tahta, okul, oturum("a1b2c3"), surum="0.9.0")
    assert kilitler(yanit) == [{"id": kilitler(yanit)[0]["id"], "tur": "kilitle", "veri": {}}]
    kayit = sorgu("SELECT * FROM kayit WHERE islem = 'Açılışta kilit'")
    assert len(kayit) == 1 and kayit[0]["kullanici"] == "sistem" and "T-01" in kayit[0]["ayrinti"]
    # Aynı oturum: kodla açıldıktan sonra (kilitli=False) yeniden kilitlenmez.
    assert kilitler(bekle(tahta, okul, oturum("a1b2c3", yas=60), surum="0.9.0")) == []
    assert kilitler(bekle(tahta, okul, oturum("a1b2c3", yas=30), surum="0.9.0")) == []
    # Oturum kapatılıp açıldı ya da tahta yeniden başladı: yeni kimlik, yeniden kilitlenir.
    assert len(kilitler(bekle(tahta, okul, oturum("d4e5f6", yas=5), surum="0.9.0"))) == 1
    assert len(sorgu("SELECT * FROM kayit WHERE islem = 'Açılışta kilit'")) == 2


def test_eski_ajan_ve_alan_yoksa_davranis_yok(panel, tahta, okul):
    assert kilitler(bekle(tahta, okul, YENI, surum="0.8.0")) == []
    assert kilitler(bekle(tahta, okul, oturum(None), surum="0.9.0")) == []
    assert not sorgu("SELECT * FROM kayit WHERE islem = 'Açılışta kilit'")


@pytest.mark.parametrize(
    "durum",
    [
        oturum("y1", yas=121),  # ağ geç geldi: ders başlamış olabilir
        oturum("y2", yas=None),
        dict(oturum("y3"), oturum={"sinif": "etapadmin"}),  # bakım oturumu
        dict(oturum("y4"), oturum={"sinif": "yok"}),
        oturum("y5", kilitli=True, kilit_kaynak="idare"),  # zaten kilitli (kalıcı kilit)
    ],
)
def test_uygulanmayan_oturumlar(panel, tahta, okul, durum):
    assert kilitler(bekle(tahta, okul, durum, surum="0.9.0")) == []
    assert not sorgu("SELECT * FROM kayit WHERE islem = 'Açılışta kilit'")


def test_kilit_kodu_yoksa_uygulanmaz_ve_ayarlarda_uyari(panel, tahta, okul):
    panel.post("/ayarlar", data={"bolum": "genel", "okul_adi": "Örnek", "ok_saatler": "", "kilit_kodu_sil": "1"})
    assert kilitler(bekle(tahta, okul, oturum("k1"), surum="0.9.0")) == []
    sayfa = panel.get("/ayarlar").text
    assert 'id="acilis-kilidi"' in sayfa and "açılışta kilit uygulanmıyor" in sayfa
    assert 'name="ak_acik" value="1" checked' in sayfa
    yanit = panel.post("/ayarlar", data={"bolum": "acilis_kilidi", "ak_acik": "1"})
    assert "kilit kodu belirlenmediği için uygulanmaz" in ileti(yanit)
    kilit_kodu(panel)
    assert "açılışta kilit uygulanmıyor" not in panel.get("/ayarlar").text


def test_ayar_kapatilinca_uygulanmaz_ve_kayda_duser(panel, tahta, okul):
    yanit = panel.post("/ayarlar", data={"bolum": "acilis_kilidi"})
    assert yanit.headers["location"].startswith("/ayarlar?yer=acilis")
    assert ileti(yanit) == "Açılışta kilit kapatıldı; tahtalar açılınca açık başlar."
    assert kilitler(bekle(tahta, okul, oturum("c1"), surum="0.9.0")) == []
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Açılışta kilit ayarı kaydedildi'")[-1]["ayrinti"] == "kapalı"
    assert 'name="ak_acik" value="1" checked' not in panel.get("/ayarlar").text
    panel.post("/ayarlar", data={"bolum": "acilis_kilidi", "ak_acik": "1"})
    assert len(kilitler(bekle(tahta, okul, oturum("c2"), surum="0.9.0"))) == 1


def test_eski_ajan_sayisi_ayarlarda(panel, tahta, okul):
    tahta_ekle(panel, tahta, "T-02", {"kilitli": False, "yetenekler": ["acil"], "ekranlar": []}, surum="0.8.0")
    assert "1 tahtada ajan güncellenmeli (eski ajan açılışta kilitlenmez)." in panel.get("/ayarlar").text


def test_acil_yayin_ve_sinav_penceresinde_uygulanmaz(panel, tahta, okul, monkeypatch):
    from tahta_sunucu import acilis_kilidi as ak

    asil = ak.acil.aktif
    monkeypatch.setattr(ak.acil, "aktif", lambda b, an=None: {"id": 1, "tur": "tatbikat", "baslik": "Deneme", "metin": "Deneme",
                                                              "bitis_plan": 10**10})  # fmt: skip
    assert kilitler(bekle(tahta, okul, oturum("ac1"), surum="0.9.0")) == []
    monkeypatch.setattr(ak.acil, "aktif", asil)
    monkeypatch.setattr(ak.sinav, "tahta_sinav_penceresinde", lambda b, tahta_id, an, on_pay=0: True)
    assert kilitler(bekle(tahta, okul, oturum("ac2"), surum="0.9.0")) == []
    assert not sorgu("SELECT * FROM kayit WHERE islem = 'Açılışta kilit'")


def test_program_kilidi_yonettigi_saatte_uygulanmaz_disinda_uygulanir(uygulama, panel, tahta, saat):
    hazirla(panel)
    kilit_kodu(panel)
    b = tahta_ekle(panel, tahta, "T-1", program_durumu(), surum="0.9.0")
    pdurum = dict(program_durumu(), yetenekler=program_durumu()["yetenekler"] + ["acilis_kilidi"])
    saat.ayarla(an(16, 10, 5))  # pazartesi 3. ders: program "derste açık" der
    assert kilitler(bekle(tahta, b, dict(pdurum, oturum_no="p1", oturum_yasi_sn=10), surum="0.9.0")) == []
    saat.ayarla(an(16, 18, 0))  # son dersten sonra: program yönetmiyor
    assert len(kilitler(bekle(tahta, b, dict(pdurum, oturum_no="p2", oturum_yasi_sn=10), surum="0.9.0"))) == 1
    # Program muaf tahta ders saatinde de açılışta kilitlenir.
    from tahta_sunucu import vt

    with vt.islem() as bag:
        bag.execute("UPDATE tahta SET program_muaf = 1 WHERE id = ?", (kimlik(b),))
    saat.ayarla(an(16, 10, 5))
    assert len(kilitler(bekle(tahta, b, dict(pdurum, oturum_no="p3", oturum_yasi_sn=10), surum="0.9.0"))) == 1
    calistir(uygulama, saat, an(16, 10, 6))  # program turu bozulmaz


def test_karar_islevleri_saf():
    from tahta_sunucu import acilis_kilidi as ak

    assert ak.yeni_oturum({"oturum_no": "x"}, {"oturum_no": "x"}) is None
    assert ak.yeni_oturum({}, {"oturum_no": "x"}) == "x"
    assert ak.yeni_oturum({}, {"oturum_no": "x" * 33}) is None
    assert ak.yeni_oturum({}, {"oturum_no": 5}) is None
    tamam = oturum("z")
    assert ak.neden_uygulanmaz(tamam, ayar_acik=True, kod_var=True) is None
    assert ak.neden_uygulanmaz(tamam, ayar_acik=False, kod_var=True) == "ayar kapalı"
    assert ak.neden_uygulanmaz(tamam, ayar_acik=True, kod_var=False) == "kilit kodu belirlenmemiş"
    assert ak.neden_uygulanmaz(dict(tamam, oturum_yasi_sn=True), ayar_acik=True, kod_var=True) == "oturum yaşlı"
    assert ak.neden_uygulanmaz(dict(tamam, oturum_yasi_sn=120), ayar_acik=True, kod_var=True) is None


def _program_okulu(panel, tahta):
    hazirla(panel)
    kilit_kodu(panel)
    b = tahta_ekle(panel, tahta, "T-1", program_durumu(), surum="0.9.0")
    pdurum = dict(program_durumu(), yetenekler=program_durumu()["yetenekler"] + ["acilis_kilidi"])
    return b, pdurum


def test_program_kilidi_varken_ilk_dersten_once_acilan_tahta_derste_kendiliginden_acilir(uygulama, panel, tahta, saat):
    """İnceleme bulgusu: ilk dersten önce süresiz idare kilidi verilirse program derste açmaz, ders bölünür."""
    b, pdurum = _program_okulu(panel, tahta)
    saat.ayarla(an(16, 8, 5))  # ilk ders 08:20
    inen = kilitler(bekle(tahta, b, dict(pdurum, oturum_no="s1", oturum_yasi_sn=10), surum="0.9.0"))
    assert len(inen) == 1
    veri = inen[0]["veri"]
    assert veri["kaynak"] == "program" and veri["acilis"] == "08:20" and veri["sure_sn"] == 15 * 60
    assert veri["neden"] == "Bu saatte bu derslikte ders yok" and "bitis_sunucu" not in veri
    assert "08:20'de açılır" in sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Açılışta kilit'")[0]["ayrinti"]
    # Süresiz idare kilidi verilmedi: 1. dersin başında ajan kendi süresiyle açar (program açma yedeği de var).
    assert not [k for k in sorgu("SELECT * FROM komut WHERE tahta_id = ? AND tur = 'kilitle'", kimlik(b))
                if '"kaynak"' not in k["veri_json"]]  # fmt: skip
    # Aynı tahta 1. derste yeniden açılırsa kilitlenmez (derste açık).
    saat.ayarla(an(16, 8, 30))
    assert kilitler(bekle(tahta, b, dict(pdurum, oturum_no="s2", oturum_yasi_sn=10), surum="0.9.0")) == []


def test_program_kilidi_varken_tenefuste_yeniden_acilan_tahta_kilitlenir(uygulama, panel, tahta, saat):
    """İnceleme bulgusu: öğle arasında yeniden açılan tahta ne açılışta ne program kilidiyle kilitleniyordu."""
    b, pdurum = _program_okulu(panel, tahta)
    saat.ayarla(an(16, 9, 5))
    bekle(tahta, b, dict(pdurum, oturum_no="o1", oturum_yasi_sn=15), surum="0.9.0")  # sabah oturumu (teneffüste)
    calistir(uygulama, saat, an(16, 11, 33))  # öğle arası program kilidi verilir (işaret yazılır)
    saat.ayarla(an(16, 11, 34))
    assert len(kilitler(bekle(tahta, b, dict(pdurum, oturum_no="o1", oturum_yasi_sn=9000), surum="0.9.0"))) == 1
    saat.ayarla(an(16, 11, 40))  # tahta yeniden açıldı: program kilidi ajan yeniden başlayınca düştü
    inen = kilitler(bekle(tahta, b, dict(pdurum, oturum_no="o2", oturum_yasi_sn=15), surum="0.9.0"))
    assert len(inen) == 1 and inen[0]["veri"]["kaynak"] == "program"
    assert inen[0]["veri"]["neden"] == "Öğle arası" and inen[0]["veri"]["acilis"] == "12:15"
    assert calistir(uygulama, saat, an(16, 11, 41)) == []  # program turu aynı aralıkta ikinci kez vermez
    # Ders başlamak üzereyse (3 dk'dan az) ve derste kilitlenmez.
    saat.ayarla(an(16, 12, 13))
    assert kilitler(bekle(tahta, b, dict(pdurum, oturum_no="o3", oturum_yasi_sn=15), surum="0.9.0")) == []
    saat.ayarla(an(16, 12, 20))
    assert kilitler(bekle(tahta, b, dict(pdurum, oturum_no="o4", oturum_yasi_sn=15), surum="0.9.0")) == []
    # o1 (09:05, teneffüs) ve o2 (11:40, öğle arası) kilitlendi; o3 ve o4 kilitlenmedi.
    assert len(sorgu("SELECT * FROM kayit WHERE islem = 'Açılışta kilit'")) == 2


def test_ayni_oturum_eszamanli_isteklerde_bir_kez_degerlendirilir(panel, tahta, okul):
    """İki istek aynı eski durumu okusa da (eşzamanlı) açılışta kilit bir kez yazılır."""
    from datetime import datetime

    from tahta_sunucu import acilis_kilidi as ak
    from tahta_sunucu import vt

    with vt.islem() as b:
        t = b.execute("SELECT * FROM tahta WHERE id = ?", (kimlik(okul),)).fetchone()
        simdi = datetime.fromtimestamp(vt.simdi(), ak.ISTANBUL)
        assert ak.degerlendir(b, t, {}, oturum("es1"), simdi) == "kilitlendi"
        assert ak.degerlendir(b, t, {}, oturum("es1"), simdi) is None
    assert len(sorgu("SELECT * FROM kayit WHERE islem = 'Açılışta kilit'")) == 1
