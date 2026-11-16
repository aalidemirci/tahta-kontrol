"""Tahta ajanının acil yayın ve kimlikli duyuru davranışı (şartname testleri 45-51)."""

from __future__ import annotations

import json
import time

import pytest


@pytest.fixture
def servis(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_AJAN_DIZIN", str(tmp_path / "ayar"))
    monkeypatch.setenv("TAHTA_AJAN_DURUM", str(tmp_path / "durum"))
    from tahta_ajan import servis as servis_mod

    # Kapatma komutu gerçek makineye dokunmasın.
    monkeypatch.setattr(servis_mod.sistem, "kapat", lambda: "benzetim")
    monkeypatch.setattr(servis_mod.sistem, "yeniden_baslat", lambda: "benzetim")
    s = servis_mod.Servis()
    s.gelen = []
    s.ekranlar[1] = {"gonder": s.gelen.append, "bilgi": {"arayuz": "gtk3"}}
    return s


def acil_yaniti(acil, **ek) -> dict:
    return {"durum": "onayli", "ayar": {"okul_adi": "Deneme Lisesi", "acil": acil, **ek}}


ACIL = {"id": 12, "tur": "acil", "baslik": "TAHLİYE", "metin": "Sınıfı sakin biçimde terk ediniz.", "kalan_sn": 1712}


def test_ajan_acil_ayarla_gelir_null_ile_kalkar(servis):
    servis._yanit_isle(acil_yaniti(ACIL))
    gorunum = servis.gorunum()
    assert gorunum["acil"]["id"] == 12 and gorunum["acil"]["tur"] == "acil"
    assert gorunum["acil"]["baslik"] == "TAHLİYE" and 1700 <= gorunum["acil"]["kalan"] <= 1712
    assert gorunum["acil"]["kapatilabilir"] is False  # sunucu ulaşılabilirken tahtadan kapatılamaz
    assert servis.gelen and servis.gelen[-1]["acil"]["id"] == 12
    assert any("Acil yayın alındı (#12, acil durum)" in o for o in servis.olaylar)

    # Aynı yayın yeniden gelince yalnız süre eşitlenir; yeni olay düşmez.
    olay_sayisi = len(servis.olaylar)
    servis._yanit_isle(acil_yaniti(dict(ACIL, kalan_sn=1690)))
    assert len(servis.olaylar) == olay_sayisi and servis.gorunum()["acil"]["kalan"] <= 1690

    servis._yanit_isle(acil_yaniti(None))
    assert servis.gorunum()["acil"] is None
    assert "Acil yayın sona erdi (sunucu)." in servis.olaylar

    # Bozuk değer ekran açmaz.
    for bozuk in ({"id": "12", "tur": "acil", "kalan_sn": 60}, {"id": 3, "tur": "yangin", "kalan_sn": 60}, "acil"):
        servis._yanit_isle(acil_yaniti(bozuk))
        assert servis.gorunum()["acil"] is None


def test_ajan_acil_suresi_tahtada_iki_saati_gecmez(servis):
    servis._yanit_isle(acil_yaniti(dict(ACIL, kalan_sn=10**9)))
    assert servis.gorunum()["acil"]["kalan"] <= 7200


def test_ajan_acil_kapatma_geri_sayimini_iptal_eder_uyarili_kapatmayi_reddeder(servis):
    basarili, cikti = servis.komut_uygula({"tur": "kapat", "veri": {"uyari_sn": 60, "neden": "Otomatik kapatma"}})
    assert basarili and servis.kapatma is not None

    servis._yanit_isle(acil_yaniti(ACIL))
    assert servis.kapatma is None
    assert "Kapatma geri sayımı acil yayın nedeniyle iptal edildi." in servis.olaylar

    # Acil sürerken uyarılı (otomatik) kapatma bilinçli olarak atlanır: başarılı + açıklama.
    basarili, cikti = servis.komut_uygula({"tur": "kapat", "veri": {"uyari_sn": 60, "neden": "Otomatik kapatma"}})
    assert basarili is True and cikti == "Acil yayın sürüyor; otomatik kapatma uygulanmadı."
    assert servis.kapatma is None

    # Panelden verilen uyarısız kapatma idarenin açık kararıdır: uygulanır.
    basarili, cikti = servis.komut_uygula({"tur": "kapat", "veri": {}})
    assert basarili is True and "uygulanacak" in cikti


def test_ajan_acil_yalniz_cevrimdisiyken_tahtadan_kapatilir(servis):
    servis.kilitli = True
    servis._yanit_isle(acil_yaniti(ACIL))
    servis.yapi = {"tahta_id": 1}  # kayıtlı tahta
    servis.son_temas = time.time()

    servis.ekran_mesaji(1, {"tur": "cevrimdisi_ac"})
    assert servis.acil is not None and servis.kilitli is True  # sunucu ulaşılabilir: yok sayılır

    servis.son_temas = time.time() - 120  # 90 sn'den uzun sunucu yok
    assert servis.gorunum()["acil"]["kapatilabilir"] is True
    servis.ekran_mesaji(1, {"tur": "cevrimdisi_ac"})
    assert servis.acil is None and servis.kilitli is False
    assert "Acil yayın sunucuya ulaşılamadığı için tahtadan kapatıldı." in servis.olaylar
    assert "Kilit sunucuya ulaşılamadığı için tahtadan açıldı." in servis.olaylar

    # Sunucu dönünce yayın hâlâ sürüyorsa tahta yeniden alır.
    servis.son_temas = time.time()
    servis._yanit_isle(acil_yaniti(ACIL))
    assert servis.gorunum()["acil"]["id"] == 12


def test_ajan_eski_sunucu_acil_anahtari_gondermezse_dokunmaz(servis):
    servis._yanit_isle(acil_yaniti(ACIL))
    servis._yanit_isle({"durum": "onayli", "ayar": {"okul_adi": "Deneme Lisesi", "kilit_kodu": None}})
    assert servis.gorunum()["acil"]["id"] == 12

    # Hiç acil görmemiş ajan da eski sunucuda acilsiz kalır; kimliksiz duyuru eski gibi çalışır.
    servis.acil = None
    servis._yanit_isle({"durum": "onayli", "ayar": {}})
    assert servis.gorunum()["acil"] is None
    servis.komut_uygula({"tur": "duyuru", "veri": {"baslik": "B", "metin": "M", "sure_sn": 60}})
    assert servis.duyuru["id"] is None
    assert servis.komut_uygula({"tur": "duyuru_kaldir", "veri": {}}) == (True, "Duyuru kaldırıldı.")
    assert servis.duyuru is None


def test_ajan_duyuru_kaldir_baska_kimlikli_duyuruya_dokunmaz(servis):
    servis.komut_uygula({"tur": "duyuru", "veri": {"duyuru_id": 7, "baslik": "Eski", "metin": "a", "sure_sn": 300}})
    servis.komut_uygula({"tur": "duyuru", "veri": {"duyuru_id": 8, "baslik": "Yeni", "metin": "b", "sure_sn": 300}})
    assert servis.duyuru["id"] == 8  # sonra gelen öncekinin yerine geçer

    basarili, cikti = servis.komut_uygula({"tur": "duyuru_kaldir", "veri": {"duyuru_id": 7}})
    assert basarili is True and cikti == "Ekrandaki duyuru başka; dokunulmadı."
    assert servis.duyuru["baslik"] == "Yeni"

    assert servis.komut_uygula({"tur": "duyuru_kaldir", "veri": {"duyuru_id": 8}}) == (True, "Duyuru kaldırıldı.")
    assert servis.duyuru is None
    # Ekranda duyuru yokken kimlikli kaldırma da zararsızdır.
    assert servis.komut_uygula({"tur": "duyuru_kaldir", "veri": {"duyuru_id": 8}})[0] is True


def test_ajan_acil_surerken_gelen_duyuru_bekler(servis):
    servis._yanit_isle(acil_yaniti(ACIL))
    basarili, cikti = servis.komut_uygula({"tur": "duyuru", "veri": {"duyuru_id": 3, "metin": "Toplantı", "sure_sn": 600}})
    assert basarili and "acil yayın bitince" in cikti
    gorunum = servis.gorunum()
    assert gorunum["acil"] and gorunum["duyuru"]["metin"] == "Toplantı"  # ekran önceliği acildedir
    servis._yanit_isle(acil_yaniti(None))
    assert servis.gorunum()["duyuru"]["metin"] == "Toplantı"


def test_ajan_durum_ozeti_yetenek_ve_acil_id_bildirir(servis, monkeypatch):
    from tahta_ajan import servis as servis_mod

    monkeypatch.setattr(servis_mod.sistem, "etkin_oturum", lambda: {"sinif": "ogretmen"})
    monkeypatch.setattr(servis_mod.sistem, "acik_sure", lambda: 100)
    ozet = servis.durum_ozeti()
    assert ozet["yetenekler"] == ["acil", "duyuru_id", "program_kilidi", "sinav", "yoklama"] and ozet["acil_id"] is None
    servis._yanit_isle(acil_yaniti(ACIL))
    assert servis.durum_ozeti()["acil_id"] == 12
    # Süresi dolmuş yayın bildirilmez.
    servis.acil["bitis"] = time.time() - 1
    assert servis.durum_ozeti()["acil_id"] is None


def test_ajan_tatbikat_gorunumde_tatbikat_turuyla(servis):
    servis.kilit_kodu = {"tuz": "aa" * 16, "ozet": "bb" * 32, "tur": 1000}
    servis.yapi = {"anahtar": "gizli-anahtar-degeri", "tahta_id": 1}
    servis._yanit_isle(acil_yaniti(dict(ACIL, id=13, tur="tatbikat", baslik="TATBİKAT")))
    gorunum = servis.gorunum()
    assert gorunum["acil"]["tur"] == "tatbikat" and gorunum["acil"]["baslik"] == "TATBİKAT"
    assert any("tatbikat" in o for o in servis.olaylar)
    # Ekran yardımcısına giden görünümde sır yoktur (kural 5).
    metin = json.dumps(gorunum)
    for yasak in ("aa" * 16, "bb" * 32, "gizli-anahtar-degeri", "kilit_kodu"):
        assert yasak not in metin


def test_ekran_acil_renkleri_sabit_ve_ascii():
    from tahta_ajan import ayar, ekran

    stil = ekran.renk_stili(dict(ayar.VARSAYILAN_PALET, ana="#9e4148"))
    stil.encode("ascii")
    for kural in ("window.acil {", "window.tatbikat {", "#acil-kapat {", "window.acil #acil-bant {"):
        assert kural in stil
    # Acil renkleri okulun renginden bağımsızdır.
    assert ekran.ACIL_RENKLERI in ekran.renk_stili(dict(ayar.VARSAYILAN_PALET, ana="#00ff00"))
    for ad in ("#acil-bant", "#acil-baslik", "#acil-metin", "#acil-alt"):
        assert ad.encode() in ekran.STIL_OLCU
