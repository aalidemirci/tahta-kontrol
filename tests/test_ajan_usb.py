"""Tahta ajanının USB anahtarı (0.11.0; şartname §9.2).

GTK'sız: bağlama noktaları elle yazılmış mountinfo metni, sahte /sys ve sahte istemciyle sınanır; dosya okuma
korumaları (sembolik bağ, FIFO, yarış) yalnız Linux'ta çalışır (Docker denemesinde de koşturulur).
Kimlik, gizli değer, ad ve kodlar uydurmadır.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import sys
import time

import pytest

from tahta_ajan import ekran, sistem, tani
from tahta_ajan import usb_anahtar as ua

LINUX = sys.platform.startswith("linux")
PARMAK_IZI = "3f9a1c0b7e2d4a51" + "0" * 48
GIZLI = base64.b32encode(bytes(range(32))).decode("ascii").rstrip("=")
GIZLI2 = base64.b32encode(bytes(range(32, 64))).decode("ascii").rstrip("=")


def dosya(kimlik="K7Q2M9XA", sunucu="3f9a1c0b7e2d4a51", gizli=GIZLI) -> bytes:
    return (
        "# Tahta Kontrol USB anahtari. Bu dosyayi kimseyle paylasmayin.\n"
        f"TAHTA-KONTROL-ANAHTAR\nsurum=1\nkimlik={kimlik}\nsunucu={sunucu}\ngizli={gizli}\n"
    ).encode("ascii")


def baglama(kimlik=101, yol="/media/ogretmen/BELLEK", aygit=(8, 17)):
    return {"kimlik": kimlik, "yol": yol, "aygit": aygit}


TANI = {"anahtar": {"tur": "ogretmen", "etiket": "A. Yılmaz", "kod": "112"}, "pin_gerek": False,
        "izinler": ["yoklama", "kilit_ac"], "omur_sn": 600}  # fmt: skip
ONERI = {"tarih_yazi": "16.11.2026 Pazartesi", "ders_saatleri": [{"ders_no": 2, "baslangic": "09:10", "bitis": "09:50"}],
         "ders_no_en_cok": 8, "oneri": {"sube": "10/A", "ders_no": 2}, "subeler": ["10/A"]}  # fmt: skip
BASLAT = {"belirtec": "GIZLI-BELIRTEC-usb", "kalan_sn": 480, "bosta_sn": 180, "ogretmen": {"kod": "112", "etiket": "A. Yılmaz"},
          "tur": "ogretmen"}  # fmt: skip
LISTE = {"sube": "10/A", "ders_no": 2, "ogrenciler": [{"id": 1, "etiket": "Deniz Ö."}, {"id": 2, "etiket": "Ege D."}],
         "yok": [], "kalan_sn": 470, "mevcut": 2}  # fmt: skip


class SahteIstemci:
    def __init__(self):
        self.yanitlar: dict = {}
        self.istekler: list = []

    def istek(self, yontem, yol, govde=None, zaman_asimi=15, ham=False):
        from tahta_ajan.baglanti import BaglantiHatasi

        self.istekler.append((yol, govde))
        kod, yanit = self.yanitlar.get(yol, (200, {}))
        if kod is None:
            raise BaglantiHatasi("bağlantı koptu")
        return kod, yanit, {}

    def yollar(self):
        return [y for y, _ in self.istekler]


@pytest.fixture
def servis(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_AJAN_DIZIN", str(tmp_path / "ayar"))
    monkeypatch.setenv("TAHTA_AJAN_DURUM", str(tmp_path / "durum"))
    from tahta_ajan import servis as servis_mod

    monkeypatch.setattr(servis_mod.sistem, "kapat", lambda: "benzetim")
    s = servis_mod.Servis()
    s.gelen = []
    s.ekranlar[1] = {"gonder": s.gelen.append, "bilgi": {"arayuz": "gtk3"}}
    s.istemci = SahteIstemci()
    s.istemci.yanitlar.update({
        "/ajan/usb/tani": (200, TANI), "/ajan/usb/yoklama": (200, BASLAT), "/ajan/usb/kilit_ac": (200, {"tamam": True}),
        "/ajan/yoklama/oneri": (200, ONERI), "/ajan/yoklama/liste": (200, LISTE), "/ajan/yoklama/bitir": (200, {}),
        "/ajan/yoklama/kaydet": (200, {"tamam": True, "yok_sayisi": 0}),
    })  # fmt: skip
    s.yapi = {"tahta_id": 1, "sunucu": "https://10.0.0.5:8788", "parmak_izi": PARMAK_IZI}
    s.son_temas = time.time()
    s.yoklama_etkin = True
    s.arka_plan = lambda is_: is_()
    s.arka_plan_surekli = lambda is_: None  # izleme döngüsü yok; turlar test içinde _usb_tara ile
    s.bildir = lambda: None
    # Takılı bellekler ve dosyaları: test bunları değiştirir.
    s.takili, s.dosyalar, s.okunan = [], {}, []

    def okuyucu(b):
        s.okunan.append(b["kimlik"])
        return s.dosyalar.get(b["kimlik"], sistem.Red("yok"))

    monkeypatch.setattr(servis_mod.sistem, "cikarilabilir_baglamalar", lambda metin: (list(s.takili), {"cikarilabilir_degil": 1}))
    monkeypatch.setattr(servis_mod.sistem, "anahtar_oku", okuyucu)
    s._yanit_isle({"ayar": {"usb_anahtar": {"etkin": True}, "yoklama_etkin": True}})
    return s


def tak(s, kimlik=101, icerik=None):
    s.takili.append(baglama(kimlik))
    s.dosyalar[kimlik] = dosya() if icerik is None else icerik
    s._usb_tara("")


def cikar(s, kimlik=101):
    s.takili = [b for b in s.takili if b["kimlik"] != kimlik]
    s._usb_tara("")


def metin(*iletiler) -> str:
    return json.dumps(iletiler, ensure_ascii=False, default=str)


# ---- 1-5: bağlama ölçütleri ----------------------------------------------------------------------
MOUNTINFO = """\
22 1 259:2 / / rw,relatime shared:1 - ext4 /dev/nvme0n1p2 rw
101 30 8:17 / /media/ogretmen/MAVI\\040BELLEK rw,nosuid,nodev,relatime shared:60 - vfat /dev/sdb1 rw,uid=1001
102 30 8:33 / /run/media/ogretmen/KIRMIZI rw,nosuid shared:61 - exfat /dev/sdc1 rw
103 30 8:49 /alt /media/ogretmen/BAGLI rw shared:62 - ext4 /dev/sdd1 rw
104 30 0:55 / /media/ogretmen/NTFS rw shared:63 - fuseblk /dev/sde1 rw,user_id=0
105 30 7:0 / /media/ogretmen/KALIP rw shared:64 - vfat /dev/loop0 rw
106 30 8:65 / /media/baskasi/BELLEK rw shared:65 - vfat /dev/sdf1 rw
107 30 0:60 / /media/ogretmen/BELLEK2 rw shared:66 - tmpfs tmpfs rw
108 30 8:81 / /mnt/disk rw shared:67 - vfat /dev/sdg1 rw
"""
SYS = {  # (maj, min) → (gerçek yol, removable)
    (8, 17): ("/sys/devices/pci0000:00/0000:00:14.0/usb1/1-2/1-2:1.0/host6/target6:0:0/6:0:0:0/block/sdb/sdb1", "1"),
    (8, 33): ("/sys/devices/platform/kart/block/sdc/sdc1", "1"),
    (8, 49): ("/sys/devices/pci0000:00/usb1/block/sdd/sdd1", "1"),
    (8, 65): ("/sys/devices/pci0000:00/usb1/block/sdf/sdf1", "1"),
    (8, 69): ("/sys/devices/pci0000:00/usb2/block/sde/sde1", "1"),
    (7, 0): ("/sys/devices/virtual/block/loop0", "0"),
}


def baglamalar(hesap="ogretmen", benzetim=False):
    return sistem.cikarilabilir_baglamalar(MOUNTINFO, hesap=hesap, benzetim=benzetim, aygit_coz=SYS.get,
                                           kaynak_coz=lambda k: (8, 69) if k == "/dev/sde1" else None)  # fmt: skip


def test_mountinfo_cozumu_kacisli_bosluk():
    b = {x["kimlik"]: x for x in ua.mountinfo_coz(MOUNTINFO)}
    assert b[101]["yol"] == "/media/ogretmen/MAVI BELLEK" and b[101]["aygit"] == (8, 17) and b[101]["fs"] == "vfat"
    assert b[104]["kaynak"] == "/dev/sde1" and b[103]["kok"] == "/alt"
    assert ua.mountinfo_coz("bozuk satır\n12 x\n") == []


def test_yalniz_media_ve_run_media():
    adaylar, elenen = baglamalar()
    yollar = [a["yol"] for a in adaylar]
    assert "/media/ogretmen/MAVI BELLEK" in yollar and "/run/media/ogretmen/KIRMIZI" in yollar
    assert "/mnt/disk" not in yollar and "/" not in yollar
    assert elenen["dosya_sistemi"] == 1  # tmpfs


def test_bind_baglama_root_kok_degilse_red():
    adaylar, elenen = baglamalar()
    assert all(a["kimlik"] != 103 for a in adaylar) and elenen["alt_dizin"] == 1


def test_cikarilabilir_degil_red():
    assert not sistem.cikarilabilir_mi("/sys/devices/pci0000:00/ata1/block/sda/sda1", "0")
    assert not sistem.cikarilabilir_mi("/sys/devices/virtual/block/loop0", "0")
    assert not sistem.cikarilabilir_mi("/sys/devices/pci0000:00/nvme/nvme0/nvme0n1", "1")
    assert not sistem.cikarilabilir_mi("/sys/devices/virtual/block/dm-0", "1")
    assert sistem.cikarilabilir_mi("/sys/devices/virtual/block/loop0", "0", benzetim=True)  # yalnız Docker benzetimi
    adaylar, _ = baglamalar()
    assert 105 not in [a["kimlik"] for a in adaylar]
    assert 105 in [a["kimlik"] for a in baglamalar(benzetim=True)[0]]


def test_usb_yolu_kabul():
    assert sistem.cikarilabilir_mi("/sys/devices/pci0000:00/0000:00:14.0/usb1/1-2/block/sdb/sdb1", "0")
    assert sistem.cikarilabilir_mi("/sys/devices/platform/kart/block/mmcblk1/mmcblk1p1", "1")  # removable=1


def test_fuseblk_kaynak_aygittan_cozulur():
    adaylar, _ = baglamalar()
    ntfs = [a for a in adaylar if a["kimlik"] == 104]
    # Okuma denetimi (st_dev) dosya sisteminin aygıtıyla yapılır; çıkarılabilirlik /dev/sde1'den.
    assert ntfs and ntfs[0]["aygit"] == (0, 55)


def test_baska_oturumun_baglamasi_red():
    adaylar, elenen = baglamalar(hesap="ogretmen")
    assert 106 not in [a["kimlik"] for a in adaylar] and elenen["baska_oturum"] == 1
    assert 106 in [a["kimlik"] for a in baglamalar(hesap=None)[0]]  # hesap bilinmiyorsa ölçüt gevşer


def test_en_cok_sekiz_aday():
    satirlar = "".join(f"{200 + i} 30 8:17 / /media/ogretmen/B{i} rw - vfat /dev/sdb1 rw\n" for i in range(12))
    adaylar, _ = sistem.cikarilabilir_baglamalar(satirlar, hesap="ogretmen", aygit_coz=SYS.get)
    assert len(adaylar) == ua.ADAY_EN_COK


# ---- 6-11: dosya okuma korumaları (yalnız Linux) ------------------------------------------------
linux = pytest.mark.skipif(not LINUX, reason="O_NOFOLLOW/dir_fd/FIFO yalnız Linux'ta")


def kok_baglama(tmp_path):
    st = os.stat(tmp_path)
    return {"kimlik": 1, "yol": str(tmp_path), "aygit": (os.major(st.st_dev), os.minor(st.st_dev))}


@linux
def test_okuma_duz_dosya_ve_yok(tmp_path):
    assert sistem.anahtar_oku(kok_baglama(tmp_path)).neden == "yok"
    (tmp_path / ua.DOSYA_ADI).write_bytes(dosya())
    assert sistem.anahtar_oku(kok_baglama(tmp_path)) == dosya()
    (tmp_path / "alt").mkdir()
    (tmp_path / ua.DOSYA_ADI).unlink()
    (tmp_path / "alt" / ua.DOSYA_ADI).write_bytes(dosya())  # alt klasör taranmaz
    assert sistem.anahtar_oku(kok_baglama(tmp_path)).neden == "yok"


@linux
def test_sembolik_bag_red(tmp_path):
    hedef = tmp_path / "gizli-sistem-dosyasi"
    hedef.write_text("root:x:0:0")
    os.symlink(hedef, tmp_path / ua.DOSYA_ADI)
    assert sistem.anahtar_oku(kok_baglama(tmp_path)).neden == "sembolik"


@linux
def test_fifo_beklemeden_red(tmp_path):
    os.mkfifo(tmp_path / ua.DOSYA_ADI)
    bas = time.monotonic()
    assert sistem.anahtar_oku(kok_baglama(tmp_path)).neden == "duz_degil"
    assert time.monotonic() - bas < 1


@linux
def test_dizin_ve_aygit_red(tmp_path):
    (tmp_path / ua.DOSYA_ADI).mkdir()
    assert sistem.anahtar_oku(kok_baglama(tmp_path)).neden == "duz_degil"


@linux
def test_buyuk_dosya_red(tmp_path):
    (tmp_path / ua.DOSYA_ADI).write_bytes(b"#" * 1025)
    assert sistem.anahtar_oku(kok_baglama(tmp_path)).neden == "buyuk"


@linux
def test_okuma_yarisi_dosya_baga_donusurse_red(tmp_path):
    (tmp_path / ua.DOSYA_ADI).write_bytes(dosya())
    hedef = tmp_path / "baska"
    hedef.write_text("gizli")
    cagri = []

    def acici(yol, bayrak, dir_fd=None):
        cagri.append(yol)
        if len(cagri) == 2:  # kök açıldıktan sonra dosya sembolik bağa çevrilir
            (tmp_path / ua.DOSYA_ADI).unlink()
            os.symlink(hedef, tmp_path / ua.DOSYA_ADI)
        return os.open(yol, bayrak, dir_fd=dir_fd) if dir_fd is not None else os.open(yol, bayrak)

    assert sistem.anahtar_oku(kok_baglama(tmp_path), acici=acici).neden == "sembolik"


@linux
def test_baglama_degisirse_st_dev_uyusmazligi_red(tmp_path):
    (tmp_path / ua.DOSYA_ADI).write_bytes(dosya())
    b = dict(kok_baglama(tmp_path), aygit=(250, 250))
    assert sistem.anahtar_oku(b).neden == "aygit"


@linux
def test_okuma_zaman_asimi(tmp_path):
    (tmp_path / ua.DOSYA_ADI).write_bytes(dosya())

    def yavas(yol, bayrak, dir_fd=None):
        time.sleep(0.6)
        return os.open(yol, bayrak, dir_fd=dir_fd) if dir_fd is not None else os.open(yol, bayrak)

    assert sistem.anahtar_oku(kok_baglama(tmp_path), zaman_asimi=0.2, acici=yavas).neden == "zaman_asimi"
    # Önceki okuma sürerken yenisi başlatılmaz (iş parçacığı yığılmaz).
    assert sistem.anahtar_oku(kok_baglama(tmp_path), zaman_asimi=0.2).neden == "zaman_asimi"
    time.sleep(1.5)
    assert sistem.anahtar_oku(kok_baglama(tmp_path)) == dosya()


def test_okuma_zaman_asimi_baglamayi_bir_daha_denemez(servis):
    servis.takili.append(baglama(101))
    servis.dosyalar[101] = sistem.Red("zaman_asimi")
    servis._usb_tara("")
    servis._usb_tara("")
    assert servis.okunan == [101] and servis.usb["durum"] == "yok"
    assert servis.usb_tani_bilgisi()["son_okuma"] == "zaman_asimi"


# ---- 12: ayrıştırıcı ------------------------------------------------------------------------------
@pytest.mark.parametrize("bozuk, neden", [
    (dosya() + b"kimlik=K7Q2M9XA\n", "bicim"),  # yinelenen alan
    (dosya().replace(b"# Tahta", "# Tahta ğ".encode()), "ascii"),
    (dosya().replace(b"TAHTA-KONTROL-ANAHTAR\n", b""), "baslik"),
    (dosya(kimlik="K7Q2M9X"), "bicim"),
    (dosya(kimlik="K7Q2M9XI"), "bicim"),  # karışan I alfabede yok
    (dosya(sunucu="3f9a1c0b7e2d4a5"), "bicim"),
    (dosya(gizli=GIZLI[:-1]), "bicim"),
    (dosya().replace(b"surum=1", b"surum=2"), "surum"),
    (b"#" * 1025, "boyut"),
])  # fmt: skip
def test_dosya_coz_katilik(bozuk, neden):
    with pytest.raises(ua.DosyaHatasi) as hata:
        ua.dosya_coz(bozuk)
    assert hata.value.neden == neden and isinstance(hata.value, ValueError)


def test_dosya_coz_buyuk_kucuk_harf_ve_crlf():
    veri = dosya(kimlik="k7q2m9xa", sunucu="3F9A1C0B7E2D4A51", gizli=GIZLI.lower()).replace(b"\n", b"\r\n")
    assert ua.dosya_coz(veri) == {"surum": 1, "kimlik": "K7Q2M9XA", "sunucu": "3f9a1c0b7e2d4a51", "gizli": GIZLI}


# ---- 13-16: tanıma, kural 5, çevrimdışı, kilit ---------------------------------------------------
def test_parmak_izi_uymazsa_sunucuya_gonderilmez(servis):
    tak(servis, icerik=dosya(sunucu="0123456789abcdef"))
    assert servis.istemci.istekler == []
    assert servis.usb["durum"] == "yabanci" and servis._usb_gizli is None
    assert servis.gorunum()["usb"]["metin"] == ua.ILETI_YABANCI


def test_gizli_ekran_durumuna_durum_dosyasina_gunluge_girmez(servis, tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    tak(servis)
    assert servis.usb["durum"] == "tanindi" and servis._usb_gizli == ("K7Q2M9XA", GIZLI)
    assert servis.istemci.istekler[0] == ("/ajan/usb/tani", {"kimlik": "K7Q2M9XA", "gizli": GIZLI})
    servis._kaydet()
    tum = metin(*servis.gelen, servis.gorunum(), servis.durum_ozeti(), servis.usb_tani_bilgisi(), caplog.text)
    for yasak in (GIZLI, "K7Q2M9XA", "K7Q2-M9XA", "/media", "BELLEK", "ogretmen/"):
        assert yasak not in tum, yasak
    for f in (tmp_path / "durum").rglob("*"):
        if f.is_file():
            assert GIZLI not in f.read_text(encoding="utf-8", errors="replace")
    u = servis.gorunum()["usb"]
    assert u["metin"] == "USB anahtar tanındı · A. Yılmaz (kod 112)" and u["kilit_ac"] is False  # tahta kilitli değil
    assert servis.durum_ozeti()["usb_izleme"] in ("kapali", "izleniyor", "desteklenmiyor")


def test_cevrimdisiyken_usb_ileti_verir_kilit_acmaz(servis):
    servis.kilitli, servis.kilit_kaynak = True, "idare"
    servis.son_temas = time.time() - 1000
    tak(servis)
    assert servis.istemci.istekler == [] and servis.usb["durum"] == "cevrimdisi"
    assert servis.gorunum()["usb"]["metin"] == ua.ILETI_CEVRIMDISI and not servis.gorunum()["usb"]["kilit_ac"]
    servis.ekran_mesaji(1, {"tur": "usb_kilit_ac"})
    assert servis.kilitli is True
    # Bağlantı gelince bir kez yeniden dener.
    servis.son_temas = time.time()
    servis._usb_denetle()
    assert servis.usb["durum"] == "tanindi" and servis.istemci.yollar() == ["/ajan/usb/tani"]
    assert servis.gorunum()["usb"]["metin"] == "USB anahtar tanındı · A. Yılmaz (kod 112)"


def test_kayitsiz_tahtada_ileti(servis):
    servis.yapi = {"parmak_izi": PARMAK_IZI}
    tak(servis)
    assert servis.usb["durum"] == "cevrimdisi" and servis.gorunum()["usb"]["metin"] == ua.ILETI_KAYITSIZ


def test_usb_kilit_ac_basarida_kilidi_birakir_olay_yazar(servis):
    servis.kilitli, servis.kilit_kaynak = True, "idare"
    servis.hatali_deneme = 3
    tak(servis)
    assert servis.gorunum()["usb"]["kilit_ac"] is True
    servis.ekran_mesaji(1, {"tur": "usb_kilit_ac"})
    assert servis.kilitli is False and servis.hatali_deneme == 0
    assert "Kilit tahtadan USB anahtarla açıldı." in servis.olaylar
    assert servis.istemci.istekler[-1] == ("/ajan/usb/kilit_ac", {"kimlik": "K7Q2M9XA", "gizli": GIZLI})


def test_usb_kilit_ac_pin_sayfasi(servis):
    servis.istemci.yanitlar["/ajan/usb/tani"] = (200, dict(TANI, pin_gerek=True))
    servis.kilitli, servis.kilit_kaynak = True, "idare"
    tak(servis)
    servis.ekran_mesaji(1, {"tur": "usb_kilit_ac"})
    assert servis.gorunum()["usb"]["pin"] == {"hata": "", "istek": False, "bekleme": 0} and servis.kilitli
    servis.istemci.yanitlar["/ajan/usb/kilit_ac"] = (403, {"hata": "PIN hatalı.", "neden": "pin", "bekleme_sn": 0})
    servis.ekran_mesaji(1, {"tur": "usb_pin", "pin": "111111"})
    assert servis.gorunum()["usb"]["pin"]["hata"] == "PIN hatalı." and servis.kilitli
    servis.istemci.yanitlar["/ajan/usb/kilit_ac"] = (200, {"tamam": True})
    servis.ekran_mesaji(1, {"tur": "usb_pin", "pin": "482913"})
    assert not servis.kilitli and servis.gorunum()["usb"]["pin"] is None
    assert "482913" not in metin(*servis.gelen, servis.durum_ozeti())


def test_usb_kilit_ac_yalniz_ekrandaki_oturumun_yardimcisindan(servis, monkeypatch):
    """0.9.0 yüzer düğme daraltması: komut istemcisi ve başka hesabın süreci kilidi USB ile açamaz."""
    from tahta_ajan import servis as servis_mod

    servis.kilitli, servis.kilit_kaynak = True, "idare"
    tak(servis)
    servis.ekranlar[2] = {"gonder": servis.gelen.append, "bilgi": {"arayuz": "komut"}}
    servis.ekranlar[3] = {"gonder": servis.gelen.append, "bilgi": {"arayuz": "gtk3"}, "uid": 1002}
    servis.ekranlar[1]["uid"] = 1001
    monkeypatch.setattr(servis_mod.sistem, "etkin_oturum_uid", lambda: 1001)
    for no in (2, 3):
        servis.ekran_mesaji(no, {"tur": "usb_kilit_ac"})
        servis.ekran_mesaji(no, {"tur": "usb_pin", "pin": "482913"})
    assert servis.kilitli and "/ajan/usb/kilit_ac" not in servis.istemci.yollar()
    servis.ekran_mesaji(1, {"tur": "usb_kilit_ac"})
    assert servis.kilitli is False


def test_bellek_yokken_hesap_adi_sorulmaz(monkeypatch):
    """Bellek takılı değilken (izleme 5 sn'de bir uyanır) loginctl süreçleri başlatılmaz."""
    sayac = []
    monkeypatch.setattr(sistem, "_etkin_oturum_ham", lambda: sayac.append(1) or {"ad": "ogretmen"})
    sistem_disi = "22 1 259:2 / / rw,relatime shared:1 - ext4 /dev/nvme0n1p2 rw\n108 30 8:81 / /mnt/disk rw - vfat /dev/sdg1 rw\n"
    assert sistem.cikarilabilir_baglamalar(sistem_disi, aygit_coz=SYS.get) == ([], {})
    assert sayac == []
    sistem.cikarilabilir_baglamalar(MOUNTINFO, aygit_coz=SYS.get)
    assert sayac == [1]


def test_sinav_ekraninda_usb_kilit_ac_yok_sayilir(servis):
    servis.kilitli, servis.kilit_kaynak = True, "idare"
    tak(servis)
    servis._sinav_isle({"kimlik": "s1", "salon": 3, "basla_sn": 0, "bitis_sn": 1800})
    assert servis.sinav_ekrani_acik()
    assert servis.gorunum()["usb"]["kilit_ac"] is False
    servis.ekran_mesaji(1, {"tur": "usb_kilit_ac"})
    assert servis.kilitli and "/ajan/usb/kilit_ac" not in servis.istemci.yollar()


def test_kilit_izni_yoksa_dugme_yok(servis):
    servis.istemci.yanitlar["/ajan/usb/tani"] = (200, dict(TANI, izinler=["yoklama"]))
    servis.kilitli, servis.kilit_kaynak = True, "idare"
    tak(servis)
    assert servis.gorunum()["usb"]["kilit_ac"] is False


@pytest.mark.parametrize("kod, yanit, beklenen", [
    (403, {"hata": ua.ILETI_GECERSIZ, "neden": "gecersiz"}, ua.ILETI_GECERSIZ),
    (410, {"hata": ua.ILETI_IPTAL, "neden": "iptal"}, ua.ILETI_IPTAL),
    (423, {"neden": "kilitli"}, ua.ILETI_KILITLI),
    (409, {"hata": ua.ILETI_KAPALI, "neden": "kapali"}, ua.ILETI_KAPALI),
])  # fmt: skip
def test_reddedilen_anahtar_ileti_ve_gizli_silinir(servis, kod, yanit, beklenen):
    servis.istemci.yanitlar["/ajan/usb/tani"] = (kod, yanit)
    tak(servis)
    assert servis.usb["durum"] == "reddedildi" and servis._usb_gizli is None
    assert servis.gorunum()["usb"]["metin"] == beklenen and servis.gorunum()["usb"]["bildirim_no"] >= 1


# ---- 17-20: dokunuşla yoklama, çıkarma, ömür ------------------------------------------------------
def test_takilinca_yoklama_kendiliginden_acilmaz(servis):
    tak(servis)
    assert servis.yoklama is None and servis.gorunum()["yoklama"] is None
    assert servis.gorunum()["usb"]["bildirim_no"] == 1
    assert [y for y in servis.istemci.yollar() if y.startswith("/ajan/yoklama")] == []
    servis.ekran_mesaji(1, {"tur": "usb_bildirim_kapat", "bildirim_no": 1})
    assert servis.gorunum()["usb"]["bildirim_no"] == 0


def test_yoklama_al_anahtarla_pin_adimini_atlar(servis):
    tak(servis)
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    y = servis.gorunum()["yoklama"]
    assert y["asama"] == "liste" and y["liste_yuklu"] and y["ogretmen"] == {"kod": "112", "etiket": "A. Yılmaz"}
    assert servis.istemci.yollar()[-3:] == ["/ajan/yoklama/oneri", "/ajan/usb/yoklama", "/ajan/yoklama/liste"]
    assert servis.istemci.istekler[-2][1] == {"kimlik": "K7Q2M9XA", "gizli": GIZLI}
    assert "/ajan/yoklama/baslat" not in servis.istemci.yollar()
    assert "GIZLI-BELIRTEC-usb" not in metin(*servis.gelen)


def test_usb_pinsiz_akista_program_tahtadan_farkliysa_liste_acilmaz(servis):
    """0.14.0 §2.3: karar _yoklama_oturum_acildi içinde, liste isteğinden ÖNCE verilir (USB + PIN'siz akış dahil)."""
    servis.istemci.yanitlar["/ajan/yoklama/oneri"] = (200, dict(ONERI, subeler=["10/A", "11/C"], subeler_once=["10/A"]))
    servis.istemci.yanitlar["/ajan/usb/yoklama"] = (
        200, dict(BASLAT, oneri={"sube": "11/C", "ders_no": 2, "ders_adaylari": []}, subeler_once=["11/C"]))  # fmt: skip
    tak(servis)
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    y = servis.gorunum()["yoklama"]
    assert servis.istemci.yollar()[-2:] == ["/ajan/yoklama/oneri", "/ajan/usb/yoklama"]  # liste istenmedi
    assert y["asama"] == "liste" and not y["liste_yuklu"] and (y["sube"], y["ders_no"]) == ("10/A", 2)
    assert y["subeler_once"] == ["10/A", "11/C"]
    servis.ekran_mesaji(1, {"tur": "yoklama_sec", "sube": "11/C"})  # ★ 11/C: şubenin dersi istenir, liste açılır
    assert servis.istemci.yollar()[-2:] == ["/ajan/yoklama/oneri", "/ajan/yoklama/liste"]
    assert servis.istemci.istekler[-1][1] == {"belirtec": "GIZLI-BELIRTEC-usb", "sube": "11/C", "ders_no": 2}


def test_usb_idare_anahtarinda_oneri_yok_tahtanin_onerisi_gecerli(servis):
    servis.istemci.yanitlar["/ajan/usb/yoklama"] = (200, dict(BASLAT, tur="idare", oneri=None, subeler_once=[]))
    tak(servis)
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    y = servis.gorunum()["yoklama"]
    assert y["liste_yuklu"] and (y["sube"], y["ders_no"]) == ("10/A", 2) and y["subeler_once"] == []


def test_pin_gerekiyorsa_usb_kipi(servis):
    servis.istemci.yanitlar["/ajan/usb/tani"] = (200, dict(TANI, pin_gerek=True))
    tak(servis)
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    y = servis.gorunum()["yoklama"]
    assert y["asama"] == "pin" and y["pin_kipi"] == "usb" and y["usb_etiket"] == "A. Yılmaz (kod 112)"
    servis.ekran_mesaji(1, {"tur": "yoklama_pin", "kod": "", "pin": "482913"})
    assert servis.istemci.istekler[-2] == ("/ajan/usb/yoklama", {"kimlik": "K7Q2M9XA", "gizli": GIZLI, "pin": "482913"})
    assert servis.gorunum()["yoklama"]["asama"] == "liste"


def test_baska_ogretmen_kod_ve_pin(servis):
    servis.istemci.yanitlar["/ajan/usb/tani"] = (200, dict(TANI, pin_gerek=True))
    servis.istemci.yanitlar["/ajan/yoklama/baslat"] = (200, BASLAT)
    tak(servis)
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    servis.ekran_mesaji(1, {"tur": "yoklama_kod_pin"})
    assert servis.gorunum()["yoklama"]["pin_kipi"] == ""
    servis.ekran_mesaji(1, {"tur": "yoklama_pin", "kod": "204", "pin": "111222"})
    assert servis.istemci.istekler[-2] == ("/ajan/yoklama/baslat", {"kod": "204", "pin": "111222"})


def test_bellek_cikarilinca_liste_acik_kalir_pin_sayfasi_kapanir(servis):
    tak(servis)
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    cikar(servis)
    assert servis.gorunum()["yoklama"]["asama"] == "liste" and servis._usb_gizli is None
    assert servis.gorunum()["usb"]["metin"] == ua.ILETI_CIKARILDI
    servis.ekran_mesaji(1, {"tur": "yoklama_onay" if False else "yoklama_kaydet"})
    servis.ekran_mesaji(1, {"tur": "yoklama_onayla"})
    assert servis.istemci.yollar()[-1] == "/ajan/yoklama/kaydet"  # kaydetmek için bellek gerekmez
    # PIN bekleyen USB'li yoklama ve kilit açma PIN sayfası kapanır.
    servis.istemci.yanitlar["/ajan/usb/tani"] = (200, dict(TANI, pin_gerek=True))
    servis.kilitli, servis.kilit_kaynak = True, "idare"
    tak(servis, kimlik=102)
    servis.ekran_mesaji(1, {"tur": "usb_kilit_ac"})
    assert servis.gorunum()["usb"]["pin"] is not None
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    assert servis.gorunum()["yoklama"]["pin_kipi"] == "usb"
    cikar(servis, 102)
    assert servis.gorunum()["usb"]["pin"] is None
    assert servis.gorunum()["yoklama"]["asama"] == "ileti" and servis.gorunum()["yoklama"]["ileti"] == ua.ILETI_CIKARILDI


def test_tani_omru_dolunca_suresi_doldu(servis):
    tak(servis)
    servis.usb["omur_bitis"] = time.monotonic() - 1
    servis._usb_denetle()
    assert servis.usb["durum"] == "suresi_doldu" and servis._usb_gizli is None
    assert servis.gorunum()["usb"]["metin"] == ""  # kendiliğinden ekrana gelmez
    servis.ekran_mesaji(1, {"tur": "yoklama_ac"})
    y = servis.gorunum()["yoklama"]
    assert y["asama"] == "pin" and y["pin_kipi"] == "" and y["hata"] == ua.ILETI_SURESI_DOLDU


def test_cikarilinca_ileti_dort_saniye(servis):
    tak(servis)
    cikar(servis)
    assert servis.usb["durum"] == "cikarildi"
    servis.usb["ileti_bitis"] = time.monotonic() - 1
    servis._usb_denetle()
    assert servis.usb["durum"] == "yok" and servis.gorunum()["usb"]["metin"] == ""


# ---- 21-25 ------------------------------------------------------------------------------------------
def test_ozellik_kapaliyken_izleme_baslamaz_ve_bellek_okunmaz(servis):
    servis._yanit_isle({"ayar": {"usb_anahtar": {"etkin": False}}})
    assert servis._usb_izleme is None and servis.gorunum()["usb"] is None
    servis.takili.append(baglama())
    servis.dosyalar[101] = dosya()
    servis._usb_tara("")
    assert servis.okunan == [] and servis.istemci.istekler == []
    assert servis.durum_ozeti()["usb_izleme"] == "kapali"


def test_ozellik_kapaninca_gizli_silinir(servis):
    tak(servis)
    servis._yanit_isle({"ayar": {"usb_anahtar": {"etkin": False}}})
    assert servis._usb_gizli is None and servis.usb["durum"] == "yok"


def test_eski_sunucu_alan_yoksa_izleme_kapali(servis):
    servis._yanit_isle({"ayar": {"okul_adi": "Deneme Lisesi"}})
    assert servis.usb_etkin is None and servis._usb_izleme is None
    assert servis.usb_tani_bilgisi()["ozellik"] == "bildirmedi"


def test_iki_anahtar_takiliysa_ilki(servis):
    servis.takili += [baglama(101), baglama(102, "/media/ogretmen/IKINCI")]
    servis.dosyalar.update({101: dosya(), 102: dosya(kimlik="ABCDEFGH", gizli=GIZLI2)})
    servis._usb_tara("")
    assert servis._usb_gizli == ("K7Q2M9XA", GIZLI) and servis.istemci.yollar() == ["/ajan/usb/tani"]
    assert ua.ILETI_BIRDEN_COK in servis.gorunum()["usb"]["metin"]


def test_tani_raporu_yol_etiket_hesap_adi_icermez(servis):
    tak(servis)
    satirlar = tani.usb_satirlari(servis.usb_tani_bilgisi(), udisks=True)
    tum = metin(satirlar)
    assert "takılı çıkarılabilir bellek" in tum and "tanındı (öğretmen anahtarı)" in tum and "anahtar bulundu" in tum
    for yasak in ("/media", "BELLEK", "ogretmen/", "K7Q2", GIZLI, "Yılmaz"):
        assert yasak not in tum, yasak


def test_tani_servis_disindan_bellekleri_sayar_dosya_okumaz(monkeypatch):
    monkeypatch.setattr(sistem, "anahtar_oku", lambda b: pytest.fail("tanılama dosya okumamalı"))
    monkeypatch.setattr(sistem, "sys_aygit", lambda a, kok="/sys": SYS.get(a))
    monkeypatch.setattr(sistem, "_etkin_oturum_ham", lambda: None)
    disaridan = {a: d for a, _, d in tani.usb_satirlari(None, udisks=False, mountinfo=MOUNTINFO)}
    # Hesap bilinmiyor: 101, 102, 106 (fuseblk'in /dev/sde1 aygıtı bu makinede yok, sayılmaz).
    assert disaridan["USB anahtar: takılı çıkarılabilir bellek"] == "3"
    assert "çalışmıyor" in disaridan["USB anahtar: otomatik bağlama hizmeti (udisks2)"]
    assert "/media" not in json.dumps(disaridan, ensure_ascii=False)


def test_yetenekler_usb_anahtar_icerir(servis):
    assert "usb_anahtar" in servis.durum_ozeti()["yetenekler"]


def test_tani_omru_ve_dosya_adi_sunucuyla_ayni():
    from tahta_sunucu import usb_anahtar as sunucu

    assert ua.TANI_OMRU_SN == sunucu.TANI_OMRU_SN and ua.DOSYA_ADI == sunucu.DOSYA_ADI
    assert ua.KIMLIK_ALFABESI == sunucu.KIMLIK_ALFABESI


# ---- 26: ekran (GTK'sız) -----------------------------------------------------------------------------
def test_usb_bildirimi_olculeri_olceklenir():
    yarim = ekran.olcekli_stil(ekran.USB_BILDIRIM_STIL, 0.5)
    assert b"min-width: 320px" in yarim and b"padding: 12px" in yarim and b"font-size: 14px" in yarim
    assert re.findall(rb"(\d+)px", ekran.USB_BILDIRIM_STIL)  # ölçüler stilde, kodda sabit piksel yok
    kaynak = open(ekran.__file__, encoding="utf-8").read()
    assert "usb-pin" in kaynak and kaynak.index('add_named(self._usb_pin_sayfasi(), "usb-pin")') < kaynak.index("self.yigin.show_all()")


def test_usb_bildirim_konumu_yuzer_dugmeyle_cakismaz():
    alan = (0, 0, 1920, 1040)
    assert ekran.usb_bildirim_konumu(alan, 640, 200, 18) == (1262, 822)
    # Yüzer düğme sağ alt köşede: bildirim onun üstüne çıkar.
    x, y = ekran.usb_bildirim_konumu(alan, 640, 200, 18, yuzer=(1842, 962, 60))
    assert y + 200 <= 962 and x == 1262
    # Sol kenardaki düğme bildirimi etkilemez.
    assert ekran.usb_bildirim_konumu(alan, 640, 200, 18, yuzer=(18, 962, 60)) == (1262, 822)


def test_usb_bildirim_gosterim_kosullari():
    usb = {"durum": "tanindi", "metin": "USB anahtar tanındı · A. Yılmaz (kod 112)", "bildirim_no": 2, "izinler": ["yoklama"]}
    assert ekran.usb_bildirim_gosterilir(usb, False, False)
    assert not ekran.usb_bildirim_gosterilir(usb, True, False)  # tam ekran sayfa açık
    assert not ekran.usb_bildirim_gosterilir(usb, False, True)  # kilitli: bilgi kilit ekranında
    assert not ekran.usb_bildirim_gosterilir(dict(usb, bildirim_no=0), False, False)
    assert ekran.usb_bildirim_yoklama_dugmesi(usb) and not ekran.usb_bildirim_yoklama_dugmesi(dict(usb, izinler=["kilit_ac"]))
    assert not ekran.usb_bildirim_yoklama_dugmesi(dict(usb, durum="reddedildi"))


def test_ekran_metinleri():
    assert ua.ekran_metni({"durum": "tanindi", "tur": "idare", "etiket": "İdare · A. Demir", "kod": ""}) == (
        "USB anahtar tanındı · İdare · A. Demir"
    )
    assert ua.ekran_metni({"durum": "okunuyor"}) == "USB anahtar okunuyor…"
    assert ua.ekran_metni({"durum": "suresi_doldu", "ileti": ""}) == ""
