"""Tahta ajanının altyapı işleri (Aşama 6A şartnamesi, testler 32–34, 36, 38, 47, 48, 50, 53 ve ekleri):
sunucu adres listesi, envanter ve tahtadan arıza bildirimi.

Ağ çağrıları sahte istemciyle yapılır. Adresler (10.0.0.x), seri numaraları ve hesap adları uydurmadır.
"""

from __future__ import annotations

import io
import json
import socket
import tarfile
import time

import pytest
from yardimci import kur_ve_gir, tahta_ekle

PARMAK = "ab" * 32
A1, A2, A3 = "https://10.0.0.5:8788", "https://10.0.0.6:8788", "https://tahta.okul.local:8788"


class AdresIstemcisi:
    """Istemci yerine geçer: adres → (kod, yanıt) ya da None (bağlantı hatası). Her isteği kaydeder."""

    yanitlar: dict = {}
    istekler: list = []

    def __init__(self, sunucu, parmak_izi="", tahta_id=None, anahtar=""):
        self.sunucu = sunucu

    def istek(self, yontem, yol, govde=None, zaman_asimi=15, ham=False):
        from tahta_ajan.baglanti import BaglantiHatasi, ParmakIziHatasi

        AdresIstemcisi.istekler.append((self.sunucu, yol, govde))
        sonuc = AdresIstemcisi.yanitlar.get(self.sunucu)
        if sonuc is None:
            raise BaglantiHatasi("bağlantı reddedildi")
        if sonuc == "parmak":
            raise ParmakIziHatasi("Sunucu sertifikası kayıtlı parmak iziyle uyuşmuyor.")
        kod, yanit = sonuc
        return kod, (yanit(govde) if callable(yanit) else yanit), {}


@pytest.fixture
def ajan(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_AJAN_DIZIN", str(tmp_path / "ayar"))
    monkeypatch.setenv("TAHTA_AJAN_DURUM", str(tmp_path / "durum"))
    from tahta_ajan import ayar
    from tahta_ajan import servis as servis_mod

    monkeypatch.setattr(servis_mod.sistem, "kapat", lambda: "benzetim")
    monkeypatch.setattr(servis_mod.sistem, "yeniden_baslat", lambda: "benzetim")
    monkeypatch.setattr(servis_mod.sistem, "ag_bilgisi", lambda *a: {})
    monkeypatch.setattr(servis_mod.sistem, "etkin_oturum", lambda: {"sinif": "ogretmen", "tur": "x11"})
    monkeypatch.setattr(servis_mod.sistem, "donanim_bilgisi", lambda: {"sys_vendor": "Örnek Teknoloji", "product_serial": "ORN75X000123"})
    monkeypatch.setattr(servis_mod, "Istemci", AdresIstemcisi)
    AdresIstemcisi.yanitlar, AdresIstemcisi.istekler = {}, []
    ayar.yaz({"sunucu": A1, "sunucular": [A1, A2], "parmak_izi": PARMAK, "tahta_id": 7, "anahtar": "gizli-anahtar"})
    return servis_mod


def onayli(govde=None):
    return {"durum": "onayli", "komutlar": [], "ayar": {}}


# ---- adres listesi ------------------------------------------------------------------------
def test_ajan_uc_hatadan_sonra_siradaki_adrese_gecer_ve_kalici_yapar(ajan):
    from tahta_ajan import ayar

    AdresIstemcisi.yanitlar = {A1: None, A2: (200, onayli)}
    s = ajan.Servis()
    for _ in range(3):
        assert s._tur() > 0  # bağlantı hatası: üstel bekleme sürer
    assert s._etkin_adres == A2 and ayar.oku()["sunucu"] == A1
    assert s._tur() == 0
    assert [a for a, _, _ in AdresIstemcisi.istekler] == [A1, A1, A1, A2]
    yapi = ayar.oku()
    assert yapi["sunucu"] == A2 and yapi["tahta_id"] == 7 and yapi["anahtar"] == "gizli-anahtar"
    assert any("yeni adresten" in o for o in s.olaylar)
    # Sonraki turlar yeni birincilde kalır.
    s._tur()
    assert AdresIstemcisi.istekler[-1][0] == A2


def test_ajan_parmak_izi_hatasi_da_adres_degistirir_ve_liste_doner(ajan):
    AdresIstemcisi.yanitlar = {A1: "parmak", A2: None}
    s = ajan.Servis()
    for _ in range(6):
        s._tur()
    # A1 ×3 (parmak izi), A2 ×3 (bağlantı) → yeniden A1
    assert [a for a, _, _ in AdresIstemcisi.istekler] == [A1] * 3 + [A2] * 3
    assert s._etkin_adres == A1


def test_ajan_http_401_de_adres_degistirmez(ajan):
    AdresIstemcisi.yanitlar = {A1: (401, {"hata": "Tahta tanınmadı."}), A2: (200, onayli)}
    s = ajan.Servis()
    for _ in range(5):
        assert s._tur() == 30
    assert {a for a, _, _ in AdresIstemcisi.istekler} == {A1}
    AdresIstemcisi.yanitlar[A1] = (503, {})
    for _ in range(4):
        s._tur()
    assert {a for a, _, _ in AdresIstemcisi.istekler} == {A1}


def test_ajan_gelen_listeyi_dogrular_ve_yazar(ajan):
    from tahta_ajan import ayar
    from tahta_sunucu import adresler

    gelen = [A3, "http://10.0.0.8:8788", "https://localhost:8788", "https://127.0.0.1:8788", f"{A3}/", "https://10.0.0.9:8788/yol"]
    AdresIstemcisi.yanitlar = {A1: (200, {"durum": "onayli", "komutlar": [], "ayar": {"sunucu_adresleri": [A1] + gelen}})}
    s = ajan.Servis()
    s._tur()
    yapi = ayar.oku()
    assert yapi["sunucular"] == [A1, A3] and yapi["sunucu"] == A1 and yapi["tahta_id"] == 7
    # Ajanın bildirdiği özet sunucunun hesapladığıyla aynı ("güncel" görünür).
    assert s.durum_ozeti()["adres_listesi_ozet"] == adresler.ozet([A1, A3])
    assert s.durum_ozeti()["sunucu_adresi"] == A1
    # Boş liste ya da anahtarı hiç olmayan yanıt (eski sunucu) mevcut listeye dokunmaz.
    s._yanit_isle({"ayar": {"sunucu_adresleri": []}})
    s._yanit_isle({"ayar": {}})
    assert ayar.oku()["sunucular"] == [A1, A3]
    # Etkin adres listede olmasa da çalıştığı sürece kullanılır.
    s._yanit_isle({"ayar": {"sunucu_adresleri": [A2]}})
    AdresIstemcisi.yanitlar[A1] = (200, onayli)
    s._tur()
    assert ayar.oku()["sunucular"] == [A2] and AdresIstemcisi.istekler[-1][0] == A1


def test_ajan_birincil_disaridan_degisince_ona_doner(ajan):
    from tahta_ajan import ayar

    AdresIstemcisi.yanitlar = {A1: None, A2: None, A3: (200, onayli)}
    s = ajan.Servis()
    s._tur()
    yapi = ayar.oku()
    yapi["sunucu"] = A3  # `tahta-ajan sunucu` yazdı
    ayar.yaz(yapi)
    s._tur()
    assert AdresIstemcisi.istekler[-1][0] == A3 and s._adres_hata == 0


def test_tahta_ajan_sunucu_komutu_parmak_izi_tutmazsa_yazmaz(ajan, monkeypatch, capsys):
    from tahta_ajan import __main__ as ana
    from tahta_ajan import ayar

    monkeypatch.setattr(ana, "Istemci", AdresIstemcisi)
    once = ayar.oku()
    AdresIstemcisi.yanitlar = {A3: "parmak"}
    assert ana.main(["sunucu", A3]) == 3
    assert ayar.oku() == once
    assert "hiçbir şey değiştirilmedi" in capsys.readouterr().err
    # Geçersiz adres: istek bile yapılmaz.
    AdresIstemcisi.istekler = []
    assert ana.main(["sunucu", "http://10.0.0.7:8788"]) == 2 and AdresIstemcisi.istekler == []
    # Ulaşılabilen ve parmak izi tutan adres: birincil olur, listenin başına girer.
    AdresIstemcisi.yanitlar = {A3: (200, {"durum": "ok"})}
    assert ana.main(["sunucu", A3 + "/"]) == 0
    yapi = ayar.oku()
    assert yapi["sunucu"] == A3 and yapi["sunucular"] == [A3, A1, A2] and yapi["tahta_id"] == 7
    assert AdresIstemcisi.istekler[-1][1] == "/saglik"


def test_tani_sunucu_adresleri_adres_yazmaz(monkeypatch):
    from tahta_ajan import tani

    monkeypatch.setattr(tani, "_erisim", lambda makine, port, zaman_asimi=3: makine == "10.0.0.5")
    sonuc, ayrinti = tani._sunucu_adresleri([A1, A2])
    assert sonuc == "uyari" and "2 adresten erişilebilen: 1" in ayrinti
    assert "10.0.0" not in ayrinti and "okul.local" not in ayrinti


# ---- envanter -----------------------------------------------------------------------------
def _sahte_kok(kok):
    def yaz(yol, metin):
        p = kok / yol
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(metin, encoding="utf-8")

    dmi = {
        "sys_vendor": "Örnek Teknoloji", "product_name": "ET-75 Etkileşimli Tahta", "product_version": "R2",
        "product_serial": "To be filled by O.E.M.", "board_vendor": "Örnek", "board_name": "ORN-MB-H610",
        "board_serial": "MB0000456", "bios_vendor": "ÖrnekBIOS", "bios_version": "1.07", "bios_date": "12.03.2024",
    }  # fmt: skip
    for ad, deger in dmi.items():
        yaz(f"sys/class/dmi/id/{ad}", deger + "\n")
    yaz("proc/cpuinfo", "processor\t: 0\nmodel name\t: Intel(R) Core(TM) i5-0000 CPU @ 2.00GHz\n")
    yaz("proc/meminfo", "MemTotal:        8031232 kB\nMemFree: 1 kB\n")
    yaz("sys/block/sda/size", str(500118192) + "\n")
    yaz("sys/block/sda/removable", "0\n")
    yaz("sys/block/sda/queue/rotational", "0\n")
    yaz("sys/block/sda/device/model", "ÖRNEK SSD 256\n")
    yaz("sys/block/sdb/size", "3000000\n")
    yaz("sys/block/sdb/removable", "1\n")  # USB bellek: girmez
    yaz("sys/block/loop0/size", "100\n")
    yaz("proc/bus/input/devices", 'I: Bus=0003\nN: Name="Örnek TouchScreen"\n\nN: Name="AT Translated Set 2 keyboard"\n')
    yaz("sys/class/net/enp2s0/address", "02:00:00:aa:bb:01\n")
    yaz("sys/class/net/enp2s0/device/uevent", "x\n")
    yaz("sys/class/net/docker0/address", "02:42:00:00:00:01\n")
    yaz("sys/class/net/lo/address", "00:00:00:00:00:00\n")
    yaz("etc/os-release", 'PRETTY_NAME="Pardus 23 ETAP"\n')
    yaz("proc/sys/kernel/osrelease", "6.1.0-00-amd64\n")
    # Kişisel veri içeren dosyalar: envantere GİRMEMELİ.
    yaz("etc/passwd", "root:x:0:0::/root:/bin/bash\nayse.ornekoglu:x:1001:1001:Ayşe Örnekoğlu:/home/ayse.ornekoglu:/bin/bash\n")
    yaz("home/ayse.ornekoglu/Belgeler/ogrenci-listesi-9A.ods", "gizli")
    yaz("etc/hostname", "ayse-ornekoglu-pc\n")


def test_envanter_kisisel_veri_icermez(tmp_path, monkeypatch):
    from tahta_ajan import envanter, sistem

    _sahte_kok(tmp_path)
    monkeypatch.setattr(sistem, "etap_paketleri", lambda: ["eta-ornek 1.2.3"])
    ham = sistem.donanim_bilgisi(str(tmp_path))
    env = envanter.topla(ham, "3840x2160")
    metin = json.dumps(env, ensure_ascii=False).lower()
    for yasak in ("ayse", "ayşe", "örnekoğlu", "ornekoglu", "/home", "ogrenci-listesi", "passwd"):
        assert yasak not in metin, yasak
    assert env["bicim"] == 1 and env["uretici"] == "Örnek Teknoloji" and env["model"] == "ET-75 Etkileşimli Tahta"
    assert env["urun_seri"] == "" and env["anakart_seri"] == "MB0000456"  # yer tutucu boş sayılır
    assert env["bios"] == "ÖrnekBIOS 1.07 (12.03.2024)"
    assert env["bellek_mb"] == 7843 and env["islemci"].startswith("Intel(R) Core(TM) i5-0000")
    assert env["diskler"] == [{"ad": "sda", "model": "ÖRNEK SSD 256", "boyut_gb": 238, "ssd": True}]
    assert env["dokunmatik"] == ["Örnek TouchScreen"] and env["ekran"] == "3840x2160"
    assert env["ag"] == [{"arayuz": "enp2s0", "mac": "02:00:00:aa:bb:01", "kablosuz": False}]
    assert env["isletim_sistemi"] == "Pardus 23 ETAP" and env["cekirdek"] == "6.1.0-00-amd64"
    assert env["etap_paketleri"] == ["eta-ornek 1.2.3"]
    for oynak in ("acik_sure", "makine_adi", "oturum", "hesaplar"):
        assert oynak not in env
    # Özet belirlenimli; ekran değişince değişir.
    assert envanter.ozet(env) == envanter.ozet(envanter.topla(ham, "3840x2160")) != envanter.ozet(envanter.topla(ham, ""))


def test_ajan_yer_tutucu_seri_numarasi_bos_sayilir():
    from tahta_ajan import envanter

    for deger in ("To be filled by O.E.M.", "Default string", "SYSTEM SERIAL NUMBER", "None", "0", "000 00", " . ", ""):
        assert envanter.seri_temizle(deger) == "", deger
    assert envanter.seri_temizle("  ORN75X000123 ") == "ORN75X000123"


def test_ajan_envanteri_yalniz_istenince_gonderir(ajan):
    from tahta_ajan import envanter

    sira = [{"durum": "onayli", "komutlar": [], "ayar": {}, "envanter_iste": True},
            {"durum": "onayli", "komutlar": [], "ayar": {}, "envanter_iste": False},
            {"durum": "onayli", "komutlar": [], "ayar": {}, "envanter_iste": False}]  # fmt: skip
    AdresIstemcisi.yanitlar = {A1: (200, lambda govde: sira.pop(0))}
    s = ajan.Servis()
    for _ in range(3):
        s._tur()
    govdeler = [g for _, _, g in AdresIstemcisi.istekler]
    assert "envanter" not in govdeler[0] and "envanter" in govdeler[1] and "envanter" not in govdeler[2]
    env = govdeler[1]["envanter"]
    assert govdeler[1]["durum"]["envanter_ozet"] == envanter.ozet(env) and env["urun_seri"] == "ORN75X000123"
    assert "envanter" in govdeler[0]["durum"]["yetenekler"]
    # Sunucu reddetse (hep "iste" dese) de aynı özet ikinci kez gönderilmez: döngü olmaz.
    sira[:] = [{"durum": "onayli", "komutlar": [], "ayar": {}, "envanter_iste": True}] * 3
    for _ in range(3):
        s._tur()
    assert sum("envanter" in g for _, _, g in AdresIstemcisi.istekler) == 1


def test_ajan_envanteri_sunucu_hala_isterse_bir_saat_sonra_yeniden_gonderir(ajan, monkeypatch):
    """Sunucudaki envanter kaybolursa (ör. yedekten geri yükleme) aynı özet de sonunda yeniden gider."""
    saat = {"t": 1000.0}
    monkeypatch.setattr(ajan.time, "monotonic", lambda: saat["t"])
    AdresIstemcisi.yanitlar = {A1: (200, {"durum": "onayli", "komutlar": [], "ayar": {}, "envanter_iste": True})}
    s = ajan.Servis()
    for _ in range(4):
        s._tur()
        saat["t"] += 60
    assert sum("envanter" in g for _, _, g in AdresIstemcisi.istekler) == 1
    saat["t"] += ajan.ENVANTER_YENIDEN_SN
    s._tur()
    s._tur()
    assert sum("envanter" in g for _, _, g in AdresIstemcisi.istekler) == 2


def test_ajan_kabuk_metakarakterli_adresi_kabul_etmez(ajan):
    from tahta_ajan import ayar

    for kotu in ("https://a$(id)b:8788", "https://tahta`id`.okul.local:8788", 'https://a";id;":8788', "https://a;b:8788"):
        assert ayar.adres_dogrula(kotu) is None
    assert ayar.adres_dogrula(A3) == A3 and ayar.adres_dogrula("https://[fd00::5]:8788") == "https://[fd00::5]:8788"
    assert ayar.adresler_dogrula([A1, "https://a$(id)b:8788"]) == [A1]


def test_ajan_envanter_komutu_json_dondurur(ajan):
    from tahta_ajan import envanter

    s = ajan.Servis()
    basarili, cikti = s.komut_uygula({"tur": "envanter", "veri": {}})
    env = json.loads(cikti)
    assert basarili and env["uretici"] == "Örnek Teknoloji" and env["ajan_surumu"]
    assert s.durum_ozeti()["envanter_ozet"] == envanter.ozet(env)


def test_ajan_govdesi_sunucuda_kabul_edilir(ajan, panel, tahta):
    """Ajanın gerçek gövdesi sunucuya gider: arıza kaydı ve envanter saklanır, ariza_alindi döner."""
    from tahta_sunucu import vt

    kur_ve_gir(panel)
    basliklar = tahta_ekle(panel, tahta, "Tahta 9-A", surum="0.7.0")

    def sunucuya(govde):
        return tahta.post("/ajan/bekle", headers=basliklar, json=dict(govde, bekle=0)).json()

    AdresIstemcisi.yanitlar = {A1: (200, sunucuya)}
    s = ajan.Servis()
    s._tur()  # ilk tur: sunucu envanter ister
    assert s._envanter_iste
    s._tur()  # ikinci tur: envanter gider
    with vt.islem() as b:
        satir = b.execute("SELECT envanter_json, envanter_ozet FROM tahta WHERE id = ?", (int(basliklar["X-Tahta-Id"]),)).fetchone()
    assert json.loads(satir["envanter_json"])["urun_seri"] == "ORN75X000123"
    assert not s._envanter_iste
    # Arıza: bildir() arka planda sunucuya iletir; ariza_alindi gelince kuyruk boşalır.
    s.yapi["tahta_id"] = int(basliklar["X-Tahta-Id"])
    basarili, metin = s.ariza_bildir("dokunmatik", "Sol alt köşe dokunmayı algılamıyor.")
    assert basarili and metin == ajan.ILETI_ARIZA_ILETILDI and s.ariza_kuyrugu == []
    with vt.islem() as b:
        kayit = b.execute("SELECT kaynak, kategori, oturum_sinifi, aciklama FROM ariza").fetchone()
    assert dict(kayit) == {"kaynak": "tahta", "kategori": "dokunmatik", "oturum_sinifi": "ogretmen",
                           "aciklama": "Sol alt köşe dokunmayı algılamıyor."}  # fmt: skip


# ---- arıza --------------------------------------------------------------------------------
def test_ajan_ariza_hiz_siniri_ve_kuyruk_siniri(ajan, monkeypatch):
    monkeypatch.setattr(ajan, "ARIZA_ONAY_BEKLEME_SN", 0.01)
    AdresIstemcisi.yanitlar = {A1: None}  # sunucuya ulaşılamıyor: kayıtlar tahtada bekler
    s = ajan.Servis()
    s._istemci_kur()
    for _ in range(3):
        basarili, metin = s.ariza_bildir("ses", "Hoparlörden cızırtı geliyor.")
        assert basarili and metin == ajan.ILETI_ARIZA_BEKLIYOR
    assert s.ariza_bildir("ses", "") == (False, ajan.ILETI_ARIZA_SINIR)
    assert len(s.ariza_kuyrugu) == 3
    # Kuyruk kalıcıdır (durum.json) ve en çok 10 öğe tutar; dolunca yenisi reddedilir, eskisi atılmaz.
    s._ariza_zamanlari.clear()
    s.ariza_kuyrugu += [dict(s.ariza_kuyrugu[0], yerel_id=f"{i:016x}") for i in range(7)]
    eski = [a["yerel_id"] for a in s.ariza_kuyrugu]
    assert s.ariza_bildir("ag", "") == (False, ajan.ILETI_ARIZA_KUYRUK)
    assert [a["yerel_id"] for a in s.ariza_kuyrugu] == eski
    yeni = ajan.Servis()
    assert [a["yerel_id"] for a in yeni.ariza_kuyrugu][:3] == eski[:3]
    # Açıklamadaki denetim karakterleri atılır, 300 karaktere kesilir.
    assert ajan.ariza_aciklamasi("a\x00b\nc" + "x" * 400) == ("ab c" + "x" * 400)[:300]


def test_ajan_ariza_kuyrugu_yedi_gunde_atilir_ve_sunucu_alinca_silinir(ajan):
    s = ajan.Servis()
    s.ariza_kuyrugu = [
        {"yerel_id": "a" * 16, "kategori": "ses", "aciklama": "", "oturum_sinifi": "ogretmen", "tahta_zamani": int(time.time()) - 8 * 86400},
        {"yerel_id": "b" * 16, "kategori": "ag", "aciklama": "", "oturum_sinifi": "ogretmen", "tahta_zamani": int(time.time())},
    ]  # fmt: skip
    AdresIstemcisi.yanitlar = {A1: (200, {"durum": "onayli", "komutlar": [], "ayar": {}, "ariza_alindi": ["b" * 16]})}
    s._tur()
    govde = AdresIstemcisi.istekler[-1][2]
    assert [a["yerel_id"] for a in govde["arizalar"]] == ["b" * 16]
    assert s.ariza_kuyrugu == [] and any("7 gün" in o for o in s.olaylar + govde["durum"]["olaylar"])


def test_acilis_kategorisi_tahtadan_reddedilir(ajan):
    s = ajan.Servis()
    s._istemci_kur()
    assert s.ariza_bildir("acilis", "") == (False, ajan.ILETI_ARIZA_KATEGORI)
    assert s.ariza_bildir("bilinmeyen", "") == (False, ajan.ILETI_ARIZA_KATEGORI)
    assert s.ariza_kuyrugu == []


def test_kayitsiz_ya_da_onaysiz_tahta_ariza_bildiremez(ajan):
    from tahta_ajan import ayar

    s = ajan.Servis()
    s._istemci_kur()
    s.onay_bekliyor = True
    assert s.ariza_bildir("ses", "") == (False, ajan.ILETI_ARIZA_KAYITSIZ)
    ayar.yaz({"sunucu": A1, "parmak_izi": PARMAK})
    s.onay_bekliyor = False
    s._istemci_kur()
    assert s.ariza_bildir("ses", "") == (False, ajan.ILETI_ARIZA_KAYITSIZ)
    assert s.ariza_kuyrugu == []


def test_ajan_ariza_baglantisi_ekran_sayilmaz(ajan, monkeypatch):
    """Arıza penceresi gerçek yerel sokete bağlanır: ekran sayılmaz, durum yayını almaz, yalnız sonuç alır."""
    from tahta_ajan import ariza_penceresi, ayar

    monkeypatch.setattr(ajan, "ARIZA_ONAY_BEKLEME_SN", 0.01)
    with socket.socket() as bos:
        bos.bind(("127.0.0.1", 0))
        port = bos.getsockname()[1]
    monkeypatch.setattr(ayar, "YEREL_PORT", port)
    AdresIstemcisi.yanitlar = {A1: None}
    s = ajan.Servis()
    s._istemci_kur()
    yerel = s._yerel_sunucu()
    try:
        assert ariza_penceresi.gonder("kalem", "Kalem yazmıyor.") == (True, ajan.ILETI_ARIZA_BEKLIYOR)
        # Ham soketle: bağlantıya ariza_sonuc dışında hiçbir ileti (durum, marka) gitmez.
        with socket.create_connection(("127.0.0.1", port), timeout=5) as soket:
            for m in ({"tur": "merhaba", "arayuz": "komut"}, {"tur": "ariza", "kategori": "goruntu", "aciklama": ""}):
                soket.sendall((json.dumps(m) + "\n").encode())
            with soket.makefile("rb") as akis:
                ilk = json.loads(akis.readline())
                assert ilk["tur"] == "ariza_sonuc" and ilk["basarili"] is True
                assert set(ilk) == {"tur", "basarili", "mesaj"}
                with s.kilit:
                    bilgiler = [e["bilgi"] for e in s.ekranlar.values()]
                assert bilgiler and all(b.get("arayuz") == "komut" for b in bilgiler)
                assert "(Uyarı: bağlı ekran yardımcısı yok" in s._ekran_notu("Kilitlendi.")
                assert s.durum_ozeti()["ekranlar"] == []
    finally:
        yerel.shutdown()
        yerel.server_close()
    assert len(s.ariza_kuyrugu) == 2
    assert {a["kategori"] for a in s.ariza_kuyrugu} == {"kalem", "goruntu"}


def test_ariza_penceresi_servis_yoksa_net_ileti(monkeypatch):
    from tahta_ajan import ariza_penceresi, ayar

    with socket.socket() as bos:
        bos.bind(("127.0.0.1", 0))
        port = bos.getsockname()[1]
    monkeypatch.setattr(ayar, "YEREL_PORT", port)  # dinleyen yok: bağlantı reddi
    assert ariza_penceresi.gonder("ses", "") == (False, ariza_penceresi.ILETI_SERVIS_YOK)
    assert [k for k, _ in ariza_penceresi.KATEGORILER] == list(__import__("tahta_ajan.servis", fromlist=["x"]).ARIZA_KATEGORILERI)


def test_ariza_penceresi_kategorileri_sunucuyla_ayni():
    from tahta_ajan import ariza_penceresi
    from tahta_sunucu import ariza

    assert dict(ariza_penceresi.KATEGORILER) == {k: v for k, v in ariza.ARIZA_KATEGORI.items() if k != "acilis"}
    assert [k for k, _ in ariza_penceresi.KATEGORILER] == ariza.TAHTADAN_KATEGORI


def test_ariza_penceresi_renkleri_ascii():
    from tahta_ajan import ariza_penceresi, ayar

    ariza_penceresi.renkler(ayar.VARSAYILAN_PALET).encode("ascii")
    ariza_penceresi.STIL_OLCU.decode("ascii")


def test_ajan_paketi_ariza_ve_envanter_dosyalarini_icerir():
    from tahta_sunucu import paket

    p = paket.ajan_paketi()
    konum, uyeler = 8, {}
    while konum < len(p.icerik):
        baslik = p.icerik[konum : konum + 60]
        boyut = int(baslik[48:58].decode().strip())
        uyeler[baslik[:16].decode().strip()] = p.icerik[konum + 60 : konum + 60 + boyut]
        konum += 60 + boyut + (boyut % 2)
    with tarfile.open(fileobj=io.BytesIO(uyeler["data.tar.gz"])) as arsiv:
        adlar = arsiv.getnames()
        masaustu = arsiv.extractfile("./usr/share/applications/tahta-ariza.desktop").read().decode("utf-8")
    for ad in ("ariza_penceresi.py", "envanter.py"):
        assert f"./opt/tahta-kontrol/tahta_ajan/{ad}" in adlar
    assert "Name=Arıza bildir" in masaustu and "Exec=/usr/bin/tahta-ajan ariza" in masaustu and "NoDisplay" not in masaustu
