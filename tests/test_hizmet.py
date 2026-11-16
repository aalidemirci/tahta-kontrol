"""Windows hizmeti (K8): veri dizini kuralı, eski veriyi taşıma, hizmet kabuğu, durum penceresi mantığı.

Gerçek hizmet kurulmaz; her şey geçici dizinlerde ve sahte sunucuyla denenir.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import subprocess
import sys
import threading
import time
import types
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent


# ---- veri dizini -------------------------------------------------------------------------
def test_veri_dizini_paketli_windowsta_programdata(tmp_path, monkeypatch):
    from tahta_sunucu import ayar

    monkeypatch.delenv("TAHTA_VERI_DIZINI", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "ProgramData"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert ayar.paketli_windows()
    assert ayar.veri_dizini_sec() == tmp_path / "ProgramData" / "TahtaKontrol"
    assert ayar.eski_veri_dizini() == tmp_path / "Local" / "TahtaKontrol"


def test_veri_dizini_gelistirmede_localappdata_kalir(tmp_path, monkeypatch):
    from tahta_sunucu import ayar

    monkeypatch.delenv("TAHTA_VERI_DIZINI", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert not ayar.paketli_windows()
    assert ayar.veri_dizini_sec() == tmp_path / "Local" / "TahtaKontrol"


def test_veri_dizini_ortam_degiskeni_paketli_programi_da_ezer(tmp_path, monkeypatch):
    from tahta_sunucu import ayar

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path / "deneme"))
    assert ayar.veri_dizini() == tmp_path / "deneme" and (tmp_path / "deneme").is_dir()


def test_hizmet_modulu_pywin32_olmadan_ice_aktarilir():
    """Linux'ta ve testlerde tahta_sunucu.hizmet pywin32 istemez; pywin32 yalnız hizmet çalışırken yüklenir."""
    betik = (
        "import sys\n"
        "class Engel:\n"
        "    def find_spec(self, ad, yol=None, hedef=None):\n"
        "        if ad.split('.')[0] in ('win32service', 'win32serviceutil', 'servicemanager', 'pywintypes',"
        " 'win32api', 'win32event'):\n"
        "            raise ImportError('engellendi: ' + ad)\n"
        "sys.meta_path.insert(0, Engel())\n"
        "import tahta_sunucu.hizmet, tahta_sunucu.tasima, tahta_sunucu.pencere\n"
        "print('tamam')\n"
    )
    sonuc = subprocess.run([sys.executable, "-c", betik], cwd=KOK, capture_output=True, text=True, timeout=60)
    assert sonuc.returncode == 0, sonuc.stderr
    assert "tamam" in sonuc.stdout


@pytest.mark.skipif(not sys.platform.startswith("win"), reason="yalnız Windows (pywin32)")
def test_hizmet_elle_calistirilirsa_sessizce_2_doner(tmp_path):
    """Hizmet Denetim Yöneticisi dışından `hizmet` → StartServiceCtrlDispatcher 1063 → çıkış kodu 2."""
    ortam = {
        **os.environ,
        "TAHTA_VERI_DIZINI": str(tmp_path),
        "TAHTA_HTTP_PORT": "8797",
        "TAHTA_HTTPS_PORT": "8798",
    }
    sonuc = subprocess.run(
        [sys.executable, "-m", "tahta_sunucu", "hizmet"],
        cwd=KOK,
        env=ortam,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert sonuc.returncode == 2, sonuc.stderr
    assert not (tmp_path / "tahta-kontrol.db").exists()  # sunucu açılmadı


# ---- hizmet gövdesi ----------------------------------------------------------------------
class SahteSunucu:
    def __init__(self, baslarken_hata: Exception | None = None):
        self.hata = baslarken_hata
        self.basladi = False
        self.durduruldu = False
        self.cokmus = False

    def baslat(self):
        if self.hata:
            raise self.hata
        self.basladi = True

    def calisiyor_mu(self):
        return self.basladi and not self.cokmus and not self.durduruldu

    def durdur(self):
        self.durduruldu = True


@pytest.fixture()
def hizmet_ortami(tmp_path, monkeypatch):
    from tahta_sunucu import ayar

    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path / "veri"))
    monkeypatch.setattr(ayar, "HIZMET", False)
    monkeypatch.delenv("TAHTA_HIZMET", raising=False)
    return tmp_path / "veri"


def test_hizmet_govdesi_baslatir_durdurma_istegiyle_kapatir(hizmet_ortami):
    from tahta_sunucu import ayar, hizmet

    sunucu = SahteSunucu()
    durdu = threading.Event()
    bildirimler = []
    sonuc = []
    is_ = threading.Thread(
        target=lambda: sonuc.append(
            hizmet.govde(durdu, lambda: sunucu, lambda m, h: bildirimler.append((m, h)), aralik=0.01)
        )
    )
    is_.start()
    bekle_sn = time.time() + 5
    while not sunucu.basladi and time.time() < bekle_sn:
        time.sleep(0.01)
    assert sunucu.basladi and ayar.HIZMET is True and os.environ["TAHTA_HIZMET"] == "1"
    durdu.set()
    is_.join(5)
    assert sonuc == [hizmet.TAMAM] and sunucu.durduruldu
    assert bildirimler and bildirimler[0][1] is False and "çalışıyor" in bildirimler[0][0]


def test_hizmet_govdesi_baslatilamazsa_hata_kodu_doner(hizmet_ortami):
    from tahta_sunucu import hizmet

    bildirimler = []
    kod = hizmet.govde(
        threading.Event(),
        lambda: SahteSunucu(RuntimeError("8788 numaralı bağlantı noktası kullanımda.")),
        lambda m, h: bildirimler.append((m, h)),
    )
    assert kod == hizmet.HATA  # hizmet yöneticisi yeniden başlatır
    assert bildirimler == [
        ("Tahta Kontrol sunucusu başlatılamadı: 8788 numaralı bağlantı noktası kullanımda.", True)
    ]


def test_hizmet_govdesi_sunucu_cokerse_hata_kodu_doner_ve_kapatir(hizmet_ortami):
    from tahta_sunucu import hizmet

    sunucu = SahteSunucu()
    durdu = threading.Event()

    def uret():
        threading.Timer(0.05, lambda: setattr(sunucu, "cokmus", True)).start()
        return sunucu

    assert hizmet.govde(durdu, uret, aralik=0.01) == hizmet.HATA
    assert sunucu.durduruldu


def test_tasima_bekliyorsa_hizmet_sunucuyu_hic_acmaz(hizmet_ortami):
    """Eski veri taşınamadıysa hizmet yeni sertifika üretip tahtaları koparmasın."""
    from tahta_sunucu import hizmet, tasima

    hizmet_ortami.mkdir(parents=True)
    (hizmet_ortami / tasima.BEKLIYOR).write_text("x", encoding="utf-8")
    uretildi = []
    bildirimler = []
    kod = hizmet.govde(threading.Event(), lambda: uretildi.append(1), lambda m, h: bildirimler.append((m, h)))
    assert kod == hizmet.TASIMA_BEKLIYOR and uretildi == []
    assert bildirimler[0][1] is True and "taşınmayı bekliyor" in bildirimler[0][0]
    assert not (hizmet_ortami / "sunucu-sertifika.pem").exists()


def test_hizmet_gunlugu_dondurulur(hizmet_ortami):
    import logging

    from tahta_sunucu import hizmet

    isleyici = hizmet.gunluk_kur(hizmet_ortami)
    try:
        assert isleyici.baseFilename == str(hizmet_ortami / "gunluk" / "sunucu.log")
        assert isleyici.maxBytes == 5 * 1024 * 1024 and isleyici.backupCount == 3
    finally:
        logging.getLogger().removeHandler(isleyici)
        isleyici.close()


def test_geri_yukleme_cikisi_75_koduyla_planlanir(monkeypatch):
    from tahta_sunucu import hizmet

    cikislar = []
    olay = threading.Event()
    monkeypatch.setattr(hizmet, "_cik", lambda kod: (cikislar.append(kod), olay.set()))
    zamanlayici = hizmet.yeniden_baslat_planla(0.01)
    assert zamanlayici.daemon and olay.wait(5)
    assert cikislar == [75]


# ---- veri taşıma -------------------------------------------------------------------------
def eski_veri(dizin: Path, *, son_temas: int | None = None, tahta: int = 1, acik_birak: bool = False):
    """Uydurma 0.7 veri dizini: WAL'lı veritabanı, sertifika çifti, günlük, yedek klasörü."""
    dizin.mkdir(parents=True, exist_ok=True)
    b = sqlite3.connect(dizin / "tahta-kontrol.db")
    b.execute("PRAGMA journal_mode=WAL")
    b.execute("PRAGMA wal_autocheckpoint=0")
    b.execute("CREATE TABLE tahta (id INTEGER PRIMARY KEY, durum TEXT, son_gorulme INTEGER)")
    b.execute("CREATE TABLE kullanici (id INTEGER PRIMARY KEY, ad TEXT)")
    b.execute("INSERT INTO kullanici (ad) VALUES ('ornek')")
    for _ in range(tahta):
        b.execute("INSERT INTO tahta (durum, son_gorulme) VALUES ('onayli', ?)", (son_temas,))
    b.commit()
    (dizin / "sunucu-sertifika.pem").write_text(f"SERTIFIKA {dizin.name}", encoding="utf-8")
    (dizin / "sunucu-anahtar.pem").write_text(f"ANAHTAR {dizin.name}", encoding="utf-8")
    (dizin / "sunucu.log").write_text("gunluk", encoding="utf-8")
    (dizin / "yedekler").mkdir(exist_ok=True)
    (dizin / "yedekler" / "tahta-kontrol-gunluk-2026-11-15.tkyedek").write_bytes(b"\x00sifreli")
    if acik_birak:
        return b
    b.close()
    return None


def ozetler(dizin: Path) -> dict[str, str]:
    return {
        str(p.relative_to(dizin)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(dizin.rglob("*"))
        if p.is_file() and p.name != "TASINDI.txt"
    }


def profil(kok: Path, ad: str) -> Path:
    return kok / "Users" / ad


def eski_dizin(kok: Path, ad: str) -> Path:
    return profil(kok, ad) / "AppData" / "Local" / "TahtaKontrol"


def test_tasima_kopyalar_dogrular_kaynaga_dokunmaz(tmp_path):
    from tahta_sunucu import tasima

    kaynak = eski_dizin(tmp_path, "idare")
    acik = eski_veri(kaynak, son_temas=1_700_000_000, tahta=3, acik_birak=True)  # eski program zorla kapandı
    try:
        acik.execute("INSERT INTO tahta (durum, son_gorulme) VALUES ('onayli', 1700000500)")
        acik.commit()  # yalnız -wal dosyasında (otomatik denetim noktası kapalı)
        assert (kaynak / "tahta-kontrol.db-wal").stat().st_size > 0
        once = ozetler(kaynak)
        hedef = tmp_path / "ProgramData" / "TahtaKontrol"
        sonuc = tasima.calistir(hedef, tercih=kaynak, profiller=[profil(tmp_path, "idare")])
        sonra = ozetler(kaynak)  # bağlantı kapanınca SQLite kendi denetim noktasını yapar; önce bak
    finally:
        acik.close()
    assert sonuc.kod == tasima.TASINDI_KOD, sonuc.ileti
    assert sonuc.kaynak == kaynak
    # sertifika ve anahtar bayt bayt aynı: tahtalar aynı parmak iziyle bağlanır
    for ad in ("sunucu-sertifika.pem", "sunucu-anahtar.pem"):
        assert (hedef / ad).read_bytes() == (kaynak / ad).read_bytes()
    assert (hedef / "yedekler" / "tahta-kontrol-gunluk-2026-11-15.tkyedek").read_bytes() == b"\x00sifreli"
    assert not (hedef / "sunucu.log").exists()  # günlük taşınmaz
    b = sqlite3.connect(hedef / "tahta-kontrol.db")
    try:
        assert b.execute("SELECT COUNT(*), MAX(son_gorulme) FROM tahta").fetchone() == (
            4,
            1700000500,
        )  # WAL'daki son kayıt
    finally:
        b.close()
    # kaynak değişmedi; yalnız TASINDI.txt eklendi
    assert {k: v for k, v in sonra.items() if not k.endswith("-shm")} == {
        k: v for k, v in once.items() if not k.endswith("-shm")
    }
    assert "kopyalandı" in (kaynak / "TASINDI.txt").read_text(encoding="utf-8")
    assert "[0]" in (hedef / "gunluk" / "tasima.log").read_text(encoding="utf-8")


def test_tasima_hedefte_veri_varsa_dokunmaz(tmp_path):
    from tahta_sunucu import tasima

    kaynak = eski_dizin(tmp_path, "idare")
    eski_veri(kaynak)
    hedef = tmp_path / "ProgramData" / "TahtaKontrol"
    hedef.mkdir(parents=True)
    (hedef / "sunucu-sertifika.pem").write_text("YENI", encoding="utf-8")
    once = ozetler(kaynak)
    sonuc = tasima.calistir(hedef, tercih=kaynak, profiller=[profil(tmp_path, "idare")])
    assert sonuc.kod == tasima.HEDEF_DOLU
    assert (hedef / "sunucu-sertifika.pem").read_text(encoding="utf-8") == "YENI"
    assert not (hedef / "tahta-kontrol.db").exists()
    assert ozetler(kaynak) == once and not (kaynak / "TASINDI.txt").exists()


def test_tasima_eski_veri_yoksa_ilk_kurulum_sayilir(tmp_path):
    from tahta_sunucu import tasima

    (profil(tmp_path, "idare") / "AppData" / "Local").mkdir(parents=True)
    eski_dizin(tmp_path, "baska").mkdir(parents=True)  # boş klasör aday değil
    (eski_dizin(tmp_path, "baska") / "pencere.log").write_text("x", encoding="utf-8")
    hedef = tmp_path / "ProgramData" / "TahtaKontrol"
    sonuc = tasima.calistir(hedef, profiller=[profil(tmp_path, "idare"), profil(tmp_path, "baska")])
    assert sonuc.kod == tasima.ESKI_VERI_YOK
    assert not tasima.veri_var(hedef) and not tasima.bekliyor_mu(hedef)


def test_tasima_daha_once_tasinmis_klasoru_yeniden_almaz(tmp_path):
    from tahta_sunucu import tasima

    kaynak = eski_dizin(tmp_path, "idare")
    eski_veri(kaynak)
    (kaynak / "TASINDI.txt").write_text("önceden", encoding="utf-8")
    sonuc = tasima.calistir(tmp_path / "hedef", profiller=[profil(tmp_path, "idare")])
    assert sonuc.kod == tasima.ESKI_VERI_YOK


def test_birden_cok_eski_veride_tahtalarin_son_baglandigi_secilir(tmp_path):
    """Başlangıç kısayolu her oturumda programı açtığı için birden çok hesapta veri olabilir."""
    from tahta_sunucu import tasima

    eski_veri(eski_dizin(tmp_path, "idare"), son_temas=1_700_000_000)
    eski_veri(eski_dizin(tmp_path, "mudur"), son_temas=1_700_900_000)  # tahtalar en son buna bağlandı
    eski_veri(eski_dizin(tmp_path, "deneme"), son_temas=None, tahta=0)
    hedef = tmp_path / "ProgramData" / "TahtaKontrol"
    sonuc = tasima.calistir(
        hedef,
        tercih=eski_dizin(tmp_path, "idare"),
        profiller=[profil(tmp_path, a) for a in ("idare", "mudur", "deneme")],
    )
    assert sonuc.kod == tasima.TASINDI_KOD and sonuc.kaynak == eski_dizin(tmp_path, "mudur")
    assert (hedef / "sunucu-sertifika.pem").read_text(encoding="utf-8") == "SERTIFIKA TahtaKontrol"
    assert "Başka 2 eski veri dizinine dokunulmadı" in sonuc.ileti
    assert not (eski_dizin(tmp_path, "idare") / "TASINDI.txt").exists()


def test_tahta_kaydi_yoksa_kurucuyu_calistiranin_dizini_secilir(tmp_path):
    from tahta_sunucu import tasima

    eski_veri(eski_dizin(tmp_path, "idare"), tahta=0)
    eski_veri(eski_dizin(tmp_path, "baska"), tahta=0)
    sonuc = tasima.calistir(
        tmp_path / "hedef",
        tercih=eski_dizin(tmp_path, "baska"),
        profiller=[profil(tmp_path, "idare"), profil(tmp_path, "baska")],
    )
    assert sonuc.kod == tasima.TASINDI_KOD and sonuc.kaynak == eski_dizin(tmp_path, "baska")


def test_belirsiz_secimde_tasimaz_ve_hizmeti_bekletir_sonra_elle_cozulur(tmp_path):
    from tahta_sunucu import tasima

    eski_veri(eski_dizin(tmp_path, "idare"), tahta=0)
    eski_veri(eski_dizin(tmp_path, "baska"), tahta=0)
    hedef = tmp_path / "ProgramData" / "TahtaKontrol"
    profiller = [profil(tmp_path, "idare"), profil(tmp_path, "baska")]
    sonuc = tasima.calistir(hedef, tercih=tmp_path / "yok", profiller=profiller)
    assert sonuc.kod == tasima.BELIRSIZ
    assert tasima.bekliyor_mu(hedef) and not tasima.veri_var(hedef)
    metin = (hedef / tasima.BEKLIYOR).read_text(encoding="utf-8")
    assert str(eski_dizin(tmp_path, "idare")) in metin and "net stop TahtaKontrol" in metin
    # Yönetici doğru klasörü elle verir.
    sonuc = tasima.calistir(hedef, kaynak=eski_dizin(tmp_path, "baska"))
    assert sonuc.kod == tasima.TASINDI_KOD
    assert not tasima.bekliyor_mu(hedef)
    assert (hedef / "sunucu-anahtar.pem").read_text(encoding="utf-8") == "ANAHTAR TahtaKontrol"


def test_kopyalama_yarida_kalirsa_yarim_kopya_silinir_kaynak_kalir(tmp_path, monkeypatch):
    from tahta_sunucu import tasima

    kaynak = eski_dizin(tmp_path, "idare")
    eski_veri(kaynak)
    once = ozetler(kaynak)
    hedef = tmp_path / "ProgramData" / "TahtaKontrol"
    gercek = tasima.shutil.copyfile
    sayac = {"n": 0}

    def bozuk(a, b):
        sayac["n"] += 1
        if sayac["n"] == 3 and Path(b).parent == hedef / tasima.GECICI:
            raise OSError(28, "Aygıtta yer kalmadı")
        return gercek(a, b)

    monkeypatch.setattr(tasima.shutil, "copyfile", bozuk)
    sonuc = tasima.calistir(hedef, profiller=[profil(tmp_path, "idare")])
    assert sonuc.kod == tasima.HATA and "yer kalmadı" in sonuc.ileti
    assert not tasima.veri_var(hedef)
    assert [p.name for p in hedef.rglob("*") if p.is_file() and p.parent == hedef] == [tasima.BEKLIYOR]
    assert not (hedef / "yedekler").exists()
    assert ozetler(kaynak) == once and not (kaynak / "TASINDI.txt").exists()


def test_bozuk_veritabani_tasinmaz(tmp_path):
    from tahta_sunucu import tasima

    kaynak = eski_dizin(tmp_path, "idare")
    kaynak.mkdir(parents=True)
    (kaynak / "tahta-kontrol.db").write_bytes(b"SQLite format 3\x00" + b"\xff" * 4000)
    (kaynak / "sunucu-sertifika.pem").write_text("S", encoding="utf-8")
    (kaynak / "sunucu-anahtar.pem").write_text("A", encoding="utf-8")
    hedef = tmp_path / "hedef"
    sonuc = tasima.calistir(hedef, profiller=[profil(tmp_path, "idare")])
    assert sonuc.kod == tasima.HATA
    assert not tasima.veri_var(hedef) and tasima.bekliyor_mu(hedef)


def test_kopyalama_sirasinda_surec_olurse_sonraki_kurulum_gecici_kopyayi_siler_ve_tasir(tmp_path):
    """0.8.0 incelemesi: süreç dışarıdan öldürülür ya da elektrik gider (istisna yolu çalışmaz). Kopyalar
    geçici dizinde olduğundan hedef "dolu" sayılmaz; sonraki çalıştırma geçiciyi siler ve baştan taşır."""
    from tahta_sunucu import tasima

    kaynak = eski_dizin(tmp_path, "idare")
    eski_veri(kaynak, son_temas=1_700_000_000)
    hedef = tmp_path / "ProgramData" / "TahtaKontrol"
    (hedef / tasima.GECICI).mkdir(parents=True)  # ölen sürecin bıraktığı yarım kopya
    (hedef / tasima.GECICI / "sunucu-anahtar.pem").write_text("ANAHTAR TahtaKontrol", encoding="utf-8")
    (hedef / tasima.GECICI / "tahta-kontrol.db").write_bytes(b"SQLite format 3\x00yarim")
    assert not tasima.veri_var(hedef)
    sonuc = tasima.calistir(hedef, profiller=[profil(tmp_path, "idare")])
    assert sonuc.kod == tasima.TASINDI_KOD, sonuc.ileti
    assert not (hedef / tasima.GECICI).exists() and not tasima.bekliyor_mu(hedef)
    assert (hedef / "tahta-kontrol.db").read_bytes() == (kaynak / "tahta-kontrol.db").read_bytes()
    assert "yarım geçici kopyası silindi" in (hedef / "gunluk" / "tasima.log").read_text(encoding="utf-8")


def test_yerlestirme_yarida_kalirsa_hizmet_acilmaz_sonraki_kurulum_toparlar(tmp_path, monkeypatch):
    """Yerleştirme (geçiciden yerine taşıma) sırasında kesinti: sertifika yerinde, veritabanı yok. İşaret
    durdukça hizmet açılmaz (boş veritabanıyla tahtaları reddetmesin); kurucu yeniden çalışınca yarım
    dosyalar kenara kaldırılır (silinmez) ve taşıma baştan yapılır."""
    from tahta_sunucu import tasima

    kaynak = eski_dizin(tmp_path, "idare")
    eski_veri(kaynak, son_temas=1_700_000_000)
    hedef = tmp_path / "ProgramData" / "TahtaKontrol"
    gercek = tasima.os.replace

    def kesik(a, b):
        if Path(b).name == "tahta-kontrol.db":
            raise SystemExit("elektrik gitti")  # Exception değil: istisna yolu da çalışmaz
        return gercek(a, b)

    monkeypatch.setattr(tasima.os, "replace", kesik)
    with pytest.raises(SystemExit):
        tasima.calistir(hedef, profiller=[profil(tmp_path, "idare")])
    monkeypatch.setattr(tasima.os, "replace", gercek)
    assert (hedef / "sunucu-sertifika.pem").exists() and not (hedef / "tahta-kontrol.db").exists()
    assert tasima.veri_var(hedef) and tasima.bekliyor_mu(hedef)  # hizmet açılmaz
    sonuc = tasima.calistir(hedef, profiller=[profil(tmp_path, "idare")])
    assert sonuc.kod == tasima.TASINDI_KOD, sonuc.ileti
    assert not tasima.bekliyor_mu(hedef) and not (hedef / tasima.SURUYOR).exists()
    for ad in ("sunucu-sertifika.pem", "sunucu-anahtar.pem", "tahta-kontrol.db"):
        assert (hedef / ad).read_bytes() == (kaynak / ad).read_bytes()
    (kenar,) = [p for p in hedef.iterdir() if p.name.startswith(tasima.YARIM_ON_EKI)]
    assert (kenar / "sunucu-sertifika.pem").exists()  # yarım dosyalar silinmedi, kenara kaldırıldı


def test_geri_donusten_sonra_yeniden_yukseltmede_bayat_kopya_sessizce_kazanmaz(tmp_path):
    """0.8 → (kaldır, 0.7 kur, kullan) → 0.8: eski klasör taşımadan sonra değişti; hizmet beklemeye alınır."""
    from tahta_sunucu import tasima

    kaynak = eski_dizin(tmp_path, "idare")
    eski_veri(kaynak, son_temas=1_700_000_000)
    hedef = tmp_path / "ProgramData" / "TahtaKontrol"
    profiller = [profil(tmp_path, "idare")]
    assert tasima.calistir(hedef, tercih=kaynak, profiller=profiller).kod == tasima.TASINDI_KOD
    # Geri dönüş yapılmadan yeniden kurulum: hedef kazanır.
    assert tasima.calistir(hedef, tercih=kaynak, profiller=profiller).kod == tasima.HEDEF_DOLU
    # Eski sürüm iki hafta kullanıldı: veritabanı TASINDI.txt'den sonra değişti.
    isaret = (kaynak / "TASINDI.txt").stat().st_mtime
    os.utime(kaynak / "tahta-kontrol.db", (isaret + 14 * 86400, isaret + 14 * 86400))
    sonuc = tasima.calistir(hedef, tercih=kaynak, profiller=profiller)
    assert sonuc.kod == tasima.BELIRSIZ and sonuc.kod not in tasima.HIZMET_BASLATILABILIR
    assert tasima.bekliyor_mu(hedef)
    metin = (hedef / tasima.BEKLIYOR).read_text(encoding="utf-8")
    assert str(kaynak) in metin and "TASINDI.txt dosyasını silin" in metin and "TahtaKontrol-eski" in metin
    # B yolu: hedefteki veri doğru; eski klasörün adı değiştirilir, işaret silinir.
    kaynak.rename(kaynak.with_name("TahtaKontrol-eski"))
    (hedef / tasima.BEKLIYOR).unlink()
    assert tasima.calistir(hedef, profiller=profiller).kod == tasima.HEDEF_DOLU


def test_sembolik_bag_izlenmez(tmp_path):
    from tahta_sunucu import tasima

    kaynak = eski_dizin(tmp_path, "idare")
    eski_veri(kaynak)
    disari = tmp_path / "disari.txt"
    disari.write_text("gizli", encoding="utf-8")
    try:
        (kaynak / "bag.txt").symlink_to(disari)
    except OSError:
        pytest.skip("bu hesapta sembolik bağ oluşturulamıyor")
    hedef = tmp_path / "hedef"
    assert tasima.calistir(hedef, kaynak=kaynak).kod == tasima.TASINDI_KOD
    assert not (hedef / "bag.txt").exists()


def test_tasi_komutu_cikis_kodunu_dondurur(tmp_path, capsys):
    from tahta_sunucu.__main__ import main

    kaynak = tmp_path / "eski"
    eski_veri(kaynak)
    assert main(["tasi", "--hedef", str(tmp_path / "hedef"), "--kaynak", str(kaynak)]) == 0
    assert main(["tasi", "--hedef", str(tmp_path / "hedef"), "--kaynak", str(kaynak)]) == 11
    assert "taşındı" in capsys.readouterr().out


# ---- durum penceresi -----------------------------------------------------------------------
SC_CALISIYOR = """
SERVICE_NAME: TahtaKontrol
        TYPE               : 10  WIN32_OWN_PROCESS
        STATE              : 4  RUNNING
                                (STOPPABLE, NOT_PAUSABLE, ACCEPTS_SHUTDOWN)
        WIN32_EXIT_CODE    : 0  (0x0)
"""
SC_DURMUS = SC_CALISIYOR.replace("4  RUNNING", "1  STOPPED")


def test_sc_ciktisi_cozulur():
    from tahta_sunucu import pencere

    assert pencere.sc_durumu_coz(SC_CALISIYOR, 0) == "RUNNING"
    assert pencere.sc_durumu_coz(SC_DURMUS, 0) == "STOPPED"
    assert pencere.sc_durumu_coz("[SC] OpenService FAILED 1060:", 1060) == "yok"
    assert pencere.sc_durumu_coz("Erişim engellendi.", 5) is None


def test_hizmeti_baslat_basarisizligi_bildirilir(monkeypatch):
    """0.8.0 incelemesi: ShellExecuteW istisna fırlatmaz; UAC reddi (5) ve hemen duran hizmet sessiz kalmasın."""
    from tahta_sunucu import pencere

    sahte = types.SimpleNamespace(windll=types.SimpleNamespace(shell32=types.SimpleNamespace(ShellExecuteW=lambda *a: 5)))
    monkeypatch.setitem(sys.modules, "ctypes", sahte)
    with pytest.raises(OSError, match="yönetici onayı verilmedi"):
        pencere.hizmeti_baslat()
    sahte.windll.shell32.ShellExecuteW = lambda *a: 42
    pencere.hizmeti_baslat()  # 32'den büyük: başarı
    durmus = SC_DURMUS.replace("(0x0)\n", "(0x0)\n        SERVICE_EXIT_CODE  : 3  (0x3)\n")
    assert pencere.sc_cikis_kodu_coz(durmus) == 3 and pencere.sc_cikis_kodu_coz(SC_CALISIYOR) is None
    metin = pencere.baslatma_sonucu_metni("STOPPED", 3)
    assert "çıkış kodu: 3" in metin and "TASIMA-BEKLIYOR.txt" in metin and "sunucu.log" in metin
    assert pencere.baslatma_sonucu_metni("RUNNING", None) is None
    assert pencere.baslatma_sonucu_metni("STOPPED", None).startswith("Hizmet başlatılamadı ya da hemen durdu.")


def test_durum_penceresi_kipi():
    from tahta_sunucu import pencere

    assert pencere.kip_sec({"hizmet": True}, None, True) == "calisiyor"
    assert pencere.kip_sec({"hizmet": False}, None, False) == "calisiyor"  # K-A7: ikinci sunucu açılmaz
    assert pencere.kip_sec(None, "STOPPED", True) == "hizmet_calismiyor"
    assert pencere.kip_sec(None, "RUNNING", False) == "hizmet_calismiyor"
    # Paketli programda hizmet yoksa pencere sunucu AÇMAZ (hizmetle çift çalışma olmasın).
    assert pencere.kip_sec(None, "yok", True) == "kurulu_degil"
    assert pencere.kip_sec(None, None, True) == "kurulu_degil"
    assert pencere.kip_sec(None, "yok", False) == "gelistirme"


def test_durum_penceresi_uyarilari():
    from tahta_sunucu import pencere

    simdi = 1_800_000_000
    assert pencere.uyarilar({"yedek_parolasi_var": False, "hizmet": False}, simdi) == [
        "Yedek parolası belirlenmedi; otomatik yedek alınmıyor (Panel → Yedekler)."
    ]
    taze = {
        "yedek_parolasi_var": True,
        "son_yedek": {"zaman": simdi - 3600, "basarili": True},
        "hizmet": True,
    }
    assert pencere.uyarilar(taze, simdi) == [
        "Bu bilgisayar uykuya geçerse tahtalar çevrimdışı kalır; güç ayarlarında uykuyu kapatın."
    ]
    eski = {**taze, "son_yedek": {"zaman": simdi - 5 * 86400, "basarili": True}}
    assert "Son üç günde yedek alınmadı" in pencere.uyarilar(eski, simdi)[0]
    basarisiz = {**taze, "son_yedek": {"zaman": simdi, "basarili": False}}
    assert "Son yedek alınamadı" in pencere.uyarilar(basarisiz, simdi)[0]


# ---- kurucu betiği (derlemeden, metin denetimi) -----------------------------------------------
def test_kurucu_betigi_hizmeti_kurar_ve_eski_baslangic_kisayolunu_siler():
    ham = (KOK / "packaging" / "windows" / "tahta-kontrol.iss").read_bytes()
    assert ham.startswith(b"\xef\xbb\xbf")  # PowerShell 5.1 / Inno için UTF-8 BOM
    metin = ham.decode("utf-8-sig")
    assert "{commonstartup}\\Tahta Kontrol.lnk" in metin and "[InstallDelete]" in metin
    simgeler = metin.split("[Icons]")[1].split("\n[")[0]
    assert (
        "commonstartup" not in simgeler and "[Tasks]" in metin
    )  # oturum açılınca başlatma kısayolu artık yok
    assert 'obj= "NT AUTHORITY\\LocalService"' in metin
    assert "*S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F *S-1-5-19:(OI)(CI)M" in metin
    assert "'tasi --hedef" in metin and "TASIMA-BEKLIYOR.txt" in metin
    assert "uninsneveruninstall" in metin  # veri kaldırmada silinmez
    assert 'Parameters: "delete {#HizmetAdi}"' in metin and 'Parameters: "stop {#HizmetAdi}"' in metin
    assert (KOK / "packaging" / "windows" / "build.ps1").read_bytes().startswith(b"\xef\xbb\xbf")


def test_kurucu_tasima_kodlari_python_ile_ayni():
    from tahta_sunucu import tasima

    metin = (KOK / "packaging" / "windows" / "tahta-kontrol.iss").read_text(encoding="utf-8-sig")
    assert f"TASIMA_TAMAM = {tasima.TASINDI_KOD};" in metin
    assert f"TASIMA_YOK = {tasima.ESKI_VERI_YOK};" in metin
    assert f"TASIMA_HEDEF_DOLU = {tasima.HEDEF_DOLU};" in metin
    assert f"TASIMA_BELIRSIZ = {tasima.BELIRSIZ};" in metin
    assert tasima.HIZMET_BASLATILABILIR == {tasima.TASINDI_KOD, tasima.ESKI_VERI_YOK, tasima.HEDEF_DOLU}
