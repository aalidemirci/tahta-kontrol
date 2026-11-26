"""Açılışta otomatik giriş (0.22.0, kural 39): ajan tarafı.

LightDM yapılandırmasının okunma sırası, Tahta Kontrol dosyasının yazılması/silinmesi ve servis akışı. Bütün
işlemler geçici bir kök klasörde yapılır; hesap adları UYDURMADIR.
"""

from __future__ import annotations

import os

import pytest

from tahta_ajan import otomatik_giris as og

HESAP_DOSYASI = (
    "root:x:0:0:root:/root:/bin/bash\n"
    "lightdm:x:110:115::/var/lib/lightdm:/bin/false\n"
    "etapadmin:x:1000:1000::/home/etapadmin:/bin/bash\n"
    "ogretmen:x:1001:1001::/home/ogretmen:/bin/bash\n"
    "ogrenci:x:1002:1002::/home/ogrenci:/bin/bash\n"
    "deneme.kisi:x:1003:1003::/home/deneme.kisi:/bin/bash\n"
)


def yaz(kok, goreli: str, metin: str):
    yol = os.path.join(kok, *goreli.split("/"))
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    with open(yol, "w", encoding="utf-8", newline="\n") as f:
        f.write(metin)
    return yol


@pytest.fixture
def kok(tmp_path):
    k = str(tmp_path)
    yaz(k, "etc/passwd", HESAP_DOSYASI)
    yaz(k, "etc/group", "autologin:x:990:\nsudo:x:27:etapadmin\n")
    yaz(k, "etc/lightdm/lightdm.conf", "[LightDM]\n#autologin-user=\n")
    return k


# ---- okuma sırası ---------------------------------------------------------------------------------
def test_lightdm_yoksa_hicbir_sey_yazilmaz(tmp_path):
    assert og.uygula("ogretmen", str(tmp_path)) == (
        False,
        "Giriş ekranı LightDM değil; otomatik giriş ayarlanmadı.",
    )
    assert og.durum(str(tmp_path))["lightdm"] is False


def test_sonraki_dosya_ezer_ozel_koltuk_genelin_onune_gecer(kok):
    yaz(kok, "usr/share/lightdm/lightdm.conf.d/01-paket.conf", "[Seat:*]\nautologin-user=ogrenci\n")
    assert og.etkin_ayar(kok)["hesap"] == "ogrenci"
    og.uygula("ogretmen", kok)
    assert og.etkin_ayar(kok) == {"hesap": "ogretmen", "kaynak": og.dosya_yolu(kok)}
    # Ana dosya en son okunur; boş değer otomatik girişi kapatır.
    yaz(kok, "etc/lightdm/lightdm.conf", "[Seat:*]\nautologin-user=\n")
    assert og.etkin_ayar(kok)["hesap"] == ""
    d = og.durum(kok)
    assert d == {"lightdm": True, "etkin": "", "bizim": True, "ezilmis": True, "hata": ""}
    # Koltuğa özel bölüm (en önce okunan dosyada da olsa) genel bölümün önüne geçer; eski [SeatDefaults] adı genel sayılır.
    yaz(kok, "etc/lightdm/lightdm.conf", "[SeatDefaults]\nautologin-user=ogrenci\n")
    assert og.etkin_ayar(kok)["hesap"] == "ogrenci"
    yaz(kok, "usr/share/lightdm/lightdm.conf.d/01-paket.conf", "[Seat:seat*]\nautologin-user=deneme.kisi\n")
    assert og.etkin_ayar(kok)["hesap"] == "deneme.kisi"
    # Rapor hesap adı taşımaz.
    assert og.durum(kok)["etkin"] == "kisisel"
    assert "deneme.kisi" not in repr(og.durum(kok))


def test_xdg_dizini_de_okunur_yorum_satiri_okunmaz(kok):
    yaz(
        kok,
        "etc/xdg/lightdm/lightdm.conf.d/50-eta.conf",
        "[Seat:*]\n# autologin-user=etapadmin\n; x\nautologin-user=ogrenci\n",
    )
    assert og.etkin_ayar(kok)["hesap"] == "ogrenci"


# ---- yazma ve silme ---------------------------------------------------------------------------------
def test_ogretmen_yazilir_ayni_icerik_yeniden_yazilmaz_grup_eklenir(kok):
    komutlar = []
    assert og.uygula("ogretmen", kok, komutlar.append) == (True, "")
    with open(og.dosya_yolu(kok), encoding="ascii") as f:
        assert f.read() == og.icerik("ogretmen")
    assert komutlar == [["usermod", "-a", "-G", "autologin", "ogretmen"]]
    assert og.uygula("ogretmen", kok) == (False, "")
    assert not os.path.exists(og.dosya_yolu(kok) + ".yeni")
    assert og.durum(kok) == {
        "lightdm": True,
        "etkin": "ogretmen",
        "bizim": True,
        "ezilmis": False,
        "hata": "",
    }


@pytest.mark.parametrize("hesap", ["etapadmin", "root", "ogrenci", "deneme.kisi", "../etc", "ogretmen\nx=1"])
def test_listede_olmayan_hesap_yazilmaz(kok, hesap):
    degisti, hata = og.uygula(hesap, kok)
    assert not degisti and "uygulanmadı" in hata
    assert not os.path.exists(og.dosya_yolu(kok))


def test_hesap_yoksa_ya_da_sistem_hesabiysa_yazilmaz(kok):
    yaz(kok, "etc/passwd", "root:x:0:0::/root:/bin/sh\n")
    assert "bu tahtada yok" in og.uygula("ogretmen", kok)[1]
    yaz(kok, "etc/passwd", "ogretmen:x:999:999::/home/o:/bin/sh\n")
    assert "Sistem hesabıyla" in og.uygula("ogretmen", kok)[1]
    assert not os.path.exists(og.dosya_yolu(kok))


def test_kaldir_yalniz_kendi_dosyamizi_siler(kok):
    assert og.uygula(None, kok) == (False, "")
    og.uygula("ogretmen", kok)
    assert og.uygula(None, kok) == (True, "")
    assert not os.path.exists(og.dosya_yolu(kok))
    # Aynı adlı ama imzasız dosya (elle yazılmış) kaldırmada silinmez.
    yaz(kok, "etc/lightdm/lightdm.conf.d/" + og.DOSYA_ADI, "[Seat:*]\nautologin-user=ogrenci\n")
    degisti, hata = og.uygula(None, kok)
    assert not degisti and "Tahta Kontrol'ün değil" in hata
    assert os.path.exists(og.dosya_yolu(kok))
    # Başka dosyadaki ayara hiç dokunulmaz.
    baska = yaz(kok, "etc/lightdm/lightdm.conf.d/60-baska.conf", "[Seat:*]\nautologin-user=ogrenci\n")
    os.remove(og.dosya_yolu(kok))
    assert og.uygula(None, kok) == (False, "")
    assert os.path.exists(baska)


def test_hedef_dosya_degilse_yazilmaz(kok):
    os.makedirs(og.dosya_yolu(kok))
    assert "beklenen türde değil" in og.uygula("ogretmen", kok)[1]


def test_sembolik_bag_izlenmez(kok, tmp_path):
    hedef = tmp_path / "baska.txt"
    hedef.write_text("dokunma\n", encoding="utf-8")
    os.makedirs(os.path.dirname(og.dosya_yolu(kok)), exist_ok=True)
    try:
        os.symlink(hedef, og.dosya_yolu(kok))
    except (OSError, NotImplementedError):
        pytest.skip("sembolik bağ oluşturulamıyor")
    assert "beklenen türde değil" in og.uygula("ogretmen", kok)[1]
    assert og.uygula(None, kok)[0] is False
    assert hedef.read_text(encoding="utf-8") == "dokunma\n"


# ---- servis akışı -------------------------------------------------------------------------------------
@pytest.fixture
def servis(tmp_path, monkeypatch, kok):
    monkeypatch.setenv("TAHTA_AJAN_DIZIN", str(tmp_path / "ayar"))
    monkeypatch.setenv("TAHTA_AJAN_DURUM", str(tmp_path / "durum"))
    from tahta_ajan import servis as servis_mod

    monkeypatch.setattr(servis_mod.sistem, "etkin_oturum", lambda: {"sinif": "yok", "tur": ""})
    s = servis_mod.Servis()
    s.otomatik_giris_kok = kok
    s.otomatik_giris_calistir = None
    s.bildir = lambda: None
    return s, servis_mod


def test_servis_alan_yoksa_dokunmaz_yetenek_bildirir(servis, kok):
    s, _ = servis
    s._yanit_isle({"ayar": {}})
    assert not os.path.exists(og.dosya_yolu(kok))
    ozet = s.durum_ozeti()
    assert "otomatik_giris" in ozet["yetenekler"]
    assert ozet["otomatik_giris"] == {
        "lightdm": True,
        "etkin": "",
        "bizim": False,
        "ezilmis": False,
        "hata": "",
    }


def test_servis_istegi_uygular_olay_yazar_tekrarlamaz(servis, kok, monkeypatch):
    s, servis_mod = servis
    s._yanit_isle({"ayar": {"otomatik_giris": {"hesap": "ogretmen"}}})
    assert os.path.exists(og.dosya_yolu(kok))
    assert any("Otomatik giriş ayarlandı (ogretmen)" in o for o in s.olaylar)
    assert s.durum_ozeti()["otomatik_giris"]["etkin"] == "ogretmen"
    cagri = []
    monkeypatch.setattr(servis_mod.otomatik_giris, "uygula", lambda *a: cagri.append(a) or (False, ""))
    s._yanit_isle({"ayar": {"otomatik_giris": {"hesap": "ogretmen"}}})
    assert cagri == []  # aynı istek 10 dk içinde yeniden uygulanmaz
    s._og_zaman -= servis_mod.OTOMATIK_GIRIS_YENILE_SN
    s._yanit_isle({"ayar": {"otomatik_giris": {"hesap": "ogretmen"}}})
    assert len(cagri) == 1  # süre dolunca yeniden (elle silinen dosya geri gelsin)


def test_servis_kaldirir_bozuk_deger_yok_sayilir(servis, kok):
    s, _ = servis
    s._yanit_isle({"ayar": {"otomatik_giris": {"hesap": "ogretmen"}}})
    for bozuk in ("ogretmen", {"hesap": 5}, {}, None):
        s._yanit_isle({"ayar": {"otomatik_giris": bozuk}})
        assert os.path.exists(og.dosya_yolu(kok))
    s._yanit_isle({"ayar": {"otomatik_giris": {"hesap": None}}})
    assert not os.path.exists(og.dosya_yolu(kok))
    assert s.durum_ozeti()["otomatik_giris"]["bizim"] is False


def test_servis_listede_olmayan_hesabi_hata_olarak_bildirir(servis, kok):
    s, _ = servis
    s._yanit_isle({"ayar": {"otomatik_giris": {"hesap": "etapadmin"}}})
    assert not os.path.exists(og.dosya_yolu(kok))
    d = s.durum_ozeti()["otomatik_giris"]
    assert "uygulanmadı" in d["hata"] and "etapadmin" not in d["hata"]
