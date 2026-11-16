"""Oturum temizliği (K7, 0.8.0): ajan tarafı.

Sahte ev dizini ve sahte /proc ile hangi dosyaların silinip hangilerinin KALDIĞI, sembolik bağ ve yol
geçişi koruması, hesap sınıfı koruması (etapadmin ve kişisel hesap asla), benzetim ve servis akışı
(60 sn uyarı, Vazgeç, ertelenmiş sonuç). Bütün adlar ve dosyalar UYDURMADIR.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
import types

import pytest

from tahta_ajan import temizlik

# Silinmesi gerekenler (ev dizinine göre) ve DOKUNULMAMASI gerekenler.
SILINECEK = [
    ".mozilla/firefox/abcd1234.default-esr/cookies.sqlite",
    ".mozilla/firefox/abcd1234.default-esr/cookies.sqlite-wal",
    ".mozilla/firefox/abcd1234.default-esr/sessionstore.jsonlz4",
    ".mozilla/firefox/abcd1234.default-esr/sessionstore-backups/recovery.jsonlz4",
    ".mozilla/firefox/abcd1234.default-esr/sessionstore-backups/previous.jsonlz4",
    ".config/chromium/Default/Cookies",
    ".config/chromium/Default/Network/Cookies",
    ".config/chromium/Default/Network/Cookies-journal",
    ".config/chromium/Default/Current Session",
    ".config/chromium/Default/Last Tabs",
    ".config/chromium/Default/Sessions/Session_13340000000000001",
    ".config/chromium/Default/Sessions/Tabs_13340000000000001",
    ".config/chromium/Default/Session Storage/000003.log",
    ".config/chromium/Profile 1/Cookies",
    ".config/google-chrome/Default/Cookies",
]
KALACAK = [
    # Firefox: geçmiş/yer imleri, kayıtlı parolalar, form geçmişi, site depolaması, ayarlar
    ".mozilla/firefox/abcd1234.default-esr/places.sqlite",
    ".mozilla/firefox/abcd1234.default-esr/favicons.sqlite",
    ".mozilla/firefox/abcd1234.default-esr/logins.json",
    ".mozilla/firefox/abcd1234.default-esr/key4.db",
    ".mozilla/firefox/abcd1234.default-esr/formhistory.sqlite",
    ".mozilla/firefox/abcd1234.default-esr/prefs.js",
    ".mozilla/firefox/abcd1234.default-esr/webappsstore.sqlite",
    ".mozilla/firefox/abcd1234.default-esr/storage/default/https+++ornek.test/ls/data.sqlite",
    ".mozilla/firefox/profiles.ini",
    # Chromium: geçmiş, yer imleri, parolalar, otomatik doldurma, yerel depolama, uzantılar
    ".config/chromium/Default/History",
    ".config/chromium/Default/Bookmarks",
    ".config/chromium/Default/Login Data",
    ".config/chromium/Default/Web Data",
    ".config/chromium/Default/Preferences",
    ".config/chromium/Default/Local Storage/leveldb/000005.ldb",
    ".config/chromium/Default/IndexedDB/https_ornek.test_0.indexeddb.leveldb/LOG",
    ".config/chromium/Default/Sessions/alt-dizin/dokunulmaz",  # dizinlerde alt dizine inilmez
    ".config/chromium/Local State",
    ".config/chromium/System Profile/Cookies",  # Default / "Profile N" dışı profil
    # Ev dizinindeki dosyalar
    "İndirilenler/ödev.pdf",
    "Downloads/sunum.odp",
    "Masaüstü/ders-notu.txt",
    "Belgeler/plan.odt",
    ".bash_history",
]


def agac(kok, yollar):
    for yol in yollar:
        tam = os.path.join(kok, *yol.split("/"))
        os.makedirs(os.path.dirname(tam), exist_ok=True)
        with open(tam, "w", encoding="utf-8") as dosya:
            dosya.write("uydurma")


def var_olanlar(kok) -> set[str]:
    sonuc = set()
    for dizin, _, dosyalar in os.walk(kok):
        for ad in dosyalar:
            sonuc.add(os.path.relpath(os.path.join(dizin, ad), kok).replace(os.sep, "/"))
    return sonuc


@pytest.fixture
def ev(tmp_path):
    kok = tmp_path / "ev" / "ogretmen"
    kok.mkdir(parents=True)
    agac(str(kok), SILINECEK + KALACAK)
    return str(kok)


def bag(hedef, ad):
    try:
        os.symlink(hedef, ad, target_is_directory=os.path.isdir(hedef))
    except (OSError, NotImplementedError):
        pytest.skip("Bu sistemde sembolik bağ oluşturulamıyor.")


# ---- dosya beyaz listesi ------------------------------------------------------------------------
def test_temizlik_yalniz_cerez_ve_oturum_dosyalarini_siler(ev):
    sonuc = temizlik.tarayici_verisini_sil(ev)
    kalan = var_olanlar(ev)
    assert kalan == set(KALACAK), "silinen/kalan küme beklenenden farklı"
    assert sonuc["aileler"] == {
        "Firefox": {"profil": 1, "dosya": 5},
        "Chromium": {"profil": 2, "dosya": 9},
        "Chrome": {"profil": 1, "dosya": 1},
    }
    assert sonuc["hata"] == 0
    # Oturum dizinlerinin kendisi kalır (tarayıcı yeniden açılınca yerinde bulur).
    assert os.path.isdir(os.path.join(ev, ".config", "chromium", "Default", "Sessions"))
    # Rapor özeti ad ve yol içermez.
    ozet = temizlik.tarayici_ozeti({**sonuc, "surecler": {"bulunan": 2, "zorla": 0, "kalan_aileler": []}})
    assert "abcd1234" not in ozet and "ogretmen" not in ozet and "Default" not in ozet and ".config" not in ozet
    assert "Firefox 1 profil, 5 çerez/oturum dosyası silindi" in ozet


def test_temizlik_kuru_hicbir_seyi_silmez_ama_sayar(ev):
    once = var_olanlar(ev)
    sonuc = temizlik.tarayici_verisini_sil(ev, kuru=True)
    assert var_olanlar(ev) == once
    assert sonuc["aileler"]["Chromium"]["dosya"] == 9
    ozet = temizlik.tarayici_ozeti({**sonuc, "kuru": True, "surecler": {"bulunan": 1}})
    assert "silinecek" in ozet and "kapatılacak" in ozet


def test_temizlik_kapanmayan_tarayicinin_verisine_dokunmaz(ev):
    temizlik.tarayici_verisini_sil(ev, haric_aileler=["Firefox"])
    kalan = var_olanlar(ev)
    assert ".mozilla/firefox/abcd1234.default-esr/cookies.sqlite" in kalan
    assert ".config/chromium/Default/Cookies" not in kalan


# ---- sembolik bağ ve yol geçişi -------------------------------------------------------------------
def test_temizlik_sembolik_baglari_izlemez(tmp_path, ev):
    disari = tmp_path / "disari"
    disari.mkdir()
    (disari / "gizli.db").write_text("dokunulmaz", encoding="utf-8")
    (disari / "Sessions").mkdir()
    (disari / "Sessions" / "onemli").write_text("dokunulmaz", encoding="utf-8")
    profil = os.path.join(ev, ".mozilla", "firefox", "abcd1234.default-esr")
    os.remove(os.path.join(profil, "cookies.sqlite"))
    bag(str(disari / "gizli.db"), os.path.join(profil, "cookies.sqlite"))  # dosya bağı
    krom = os.path.join(ev, ".config", "chromium", "Default")
    shutil.rmtree(os.path.join(krom, "Sessions"))
    bag(str(disari / "Sessions"), os.path.join(krom, "Sessions"))  # dizin bağı
    bag(str(disari), os.path.join(ev, ".config", "chromium", "Profile 7"))  # profil bağı
    sonuc = temizlik.tarayici_verisini_sil(ev)
    assert (disari / "gizli.db").read_text(encoding="utf-8") == "dokunulmaz"
    assert (disari / "Sessions" / "onemli").exists()
    assert os.path.islink(os.path.join(profil, "cookies.sqlite"))  # bağın kendisi de silinmez
    assert sonuc["atlanan"] >= 2


def test_temizlik_bagli_kok_ve_ev_dizini_izlenmez(tmp_path):
    gercek = tmp_path / "gercek"
    agac(str(gercek), [".mozilla/firefox/x.default/cookies.sqlite"])
    ev = tmp_path / "ev2"
    ev.mkdir()
    bag(str(gercek / ".mozilla"), str(ev / ".mozilla"))  # kök dizin bağı
    temizlik.tarayici_verisini_sil(str(ev))
    assert (gercek / ".mozilla" / "firefox" / "x.default" / "cookies.sqlite").exists()
    ev_bagi = tmp_path / "ev-bagi"
    bag(str(gercek), str(ev_bagi))  # ev dizininin kendisi bağ
    sonuc = temizlik.tarayici_verisini_sil(str(ev_bagi))
    assert sonuc.get("ev_gecersiz") and (gercek / ".mozilla" / "firefox" / "x.default" / "cookies.sqlite").exists()


def test_temizlik_yol_gecisini_reddeder(tmp_path, ev):
    assert temizlik.guvenli_dizin(ev, ["..", "ogretmen"]) is None
    assert temizlik.guvenli_dizin(ev, [".config/../.."]) is None
    assert temizlik.guvenli_dizin(ev, ["."]) is None
    assert temizlik.guvenli_dizin(ev, [".config", "chromium"]) is not None
    assert not temizlik.ev_gecerli("goreli/yol") and not temizlik.ev_gecerli("")
    assert not temizlik.ev_gecerli(os.path.abspath(os.sep))  # kök dizin ev dizini olamaz
    assert not temizlik.ev_gecerli(str(tmp_path / "yok"))


@pytest.mark.skipif(not temizlik._FD_DESTEGI, reason="dosya tanıtıcısıyla dizin işlemleri yalnız Linux'ta (ajanın sistemi)")
def test_temizlik_denetimden_sonra_baga_cevrilen_dizin_belgeleri_sildirmez(ev, monkeypatch):
    """Yarış (0.8.0 incelemesi): oturum dizini denetlendikten SONRA Belgeler'e giden bir bağla değiştirilir.
    Silme açık dizin tanıtıcısına göre yapıldığı için Belgeler'e dokunulmaz."""
    krom = os.path.join(ev, ".config", "chromium", "Default")
    belgeler = os.path.join(ev, "Belgeler")
    for ad in ("Session_13340000000000001", "Tabs_13340000000000001"):  # aynı adlı ödev dosyaları
        with open(os.path.join(belgeler, ad), "w", encoding="utf-8") as dosya:
            dosya.write("ödev")
    asil = temizlik._Dizin.adlar

    def degistir(self):
        adlar = asil(self)
        if self.yol.endswith(os.path.join("Default", "Sessions")):
            os.rename(self.yol, self.yol + ".eski")
            os.symlink(belgeler, self.yol, target_is_directory=True)
        return adlar

    monkeypatch.setattr(temizlik._Dizin, "adlar", degistir)
    temizlik.tarayici_verisini_sil(ev)
    assert sorted(os.listdir(belgeler)) == ["Session_13340000000000001", "Tabs_13340000000000001", "plan.odt"]
    assert sorted(os.listdir(os.path.join(krom, "Sessions.eski"))) == ["alt-dizin"]  # asıl oturum dosyaları silindi


# ---- tarayıcı süreçleri (sahte /proc) -------------------------------------------------------------
def sahte_proc(kok, surecler):
    for pid, (ad, uid, *durum) in surecler.items():
        dizin = kok / str(pid)
        dizin.mkdir(parents=True)
        hal = durum[0] if durum else "S (sleeping)"
        (dizin / "status").write_text(f"Name:\t{ad}\nUmask:\t0022\nState:\t{hal}\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n", encoding="utf-8")


def test_temizlik_zombi_sureci_kapanmis_sayar(tmp_path):
    proc = tmp_path / "proc"
    sahte_proc(proc, {501: ("firefox-esr", 1001, "Z (zombie)"), 502: ("chromium", 1001)})
    assert temizlik.tarayici_surecleri(1001, str(proc)) == [(502, "Chromium")]


@pytest.fixture
def hizli(monkeypatch):
    for ad in ("KENDILIGINDEN_KAPANMA_SN", "SIGTERM_BEKLEME_SN", "SIGKILL_BEKLEME_SN"):
        monkeypatch.setattr(temizlik, ad, 0)


def test_temizlik_yalniz_o_hesabin_tarayici_sureclerini_kapatir(tmp_path, hizli):
    proc = tmp_path / "proc"
    sahte_proc(proc, {101: ("firefox-esr", 1001), 102: ("chromium", 1001), 103: ("xfce4-terminal", 1001),
                      104: ("firefox-esr", 1002), 105: ("libreoffice", 1001)})  # fmt: skip
    gonderilen = []

    def oldur(pid, sinyal):
        gonderilen.append((pid, sinyal))
        shutil.rmtree(proc / str(pid))  # SIGTERM ile kapandı

    sonuc = temizlik.tarayicilari_kapat(1001, proc=str(proc), oldur=oldur)
    assert sorted(p for p, _ in gonderilen) == [101, 102]  # başka hesap ve tarayıcı olmayan süreç yok
    assert sonuc == {"bulunan": 2, "zorla": 0, "kalan_aileler": []}


def test_temizlik_kapanmayan_tarayiciya_sigkill_sonra_veriye_dokunmaz(tmp_path, ev, hizli):
    proc = tmp_path / "proc"
    sahte_proc(proc, {201: ("firefox", 1001)})
    gonderilen = []
    sonuc = temizlik.tarayicilari_kapat(1001, proc=str(proc), oldur=lambda p, s: gonderilen.append(s))
    assert len(gonderilen) == 2 and sonuc["zorla"] == 1 and sonuc["kalan_aileler"] == ["Firefox"]
    veri = temizlik.tarayici_verisini_sil(ev, haric_aileler=sonuc["kalan_aileler"])
    assert "Firefox" not in veri["aileler"] and "Chromium" in veri["aileler"]
    ozet = temizlik.tarayici_ozeti({**veri, "surecler": sonuc})
    assert "Firefox kapanmadı, verisine dokunulmadı" in ozet


def test_temizlik_kuru_surec_kapatmaz(tmp_path, ev, hizli):
    proc = tmp_path / "proc"
    sahte_proc(proc, {301: ("chrome", 1001)})
    once = var_olanlar(ev)
    sonuc = temizlik.tarayici_temizligi(ev, 1001, kuru=True, proc=str(proc))
    assert (proc / "301").exists() and var_olanlar(ev) == once
    assert sonuc["surecler"]["bulunan"] == 1 and sonuc["kuru"] is True


# ---- hesap sınıfı koruması ------------------------------------------------------------------------
@pytest.fixture
def sahte_pwd(monkeypatch):
    kayitlar = {
        "ogretmen": types.SimpleNamespace(pw_uid=1001, pw_gid=1001, pw_dir="/home/ogretmen"),
        "ogrenci": types.SimpleNamespace(pw_uid=1002, pw_gid=1002, pw_dir="/home/ogrenci"),
        "etapadmin": types.SimpleNamespace(pw_uid=1000, pw_gid=1000, pw_dir="/home/etapadmin"),
        "ayse": types.SimpleNamespace(pw_uid=1003, pw_gid=1003, pw_dir="/home/ayse"),
    }
    modul = types.ModuleType("pwd")
    modul.getpwnam = lambda ad: kayitlar[ad]
    monkeypatch.setitem(sys.modules, "pwd", modul)
    return kayitlar


def test_temizlik_kisisel_ve_etapadmin_hesapta_calismaz(monkeypatch, sahte_pwd):
    from tahta_ajan import sistem

    def oturum(ad):
        monkeypatch.setattr(sistem, "_etkin_oturum_ham", lambda: {"ad": ad, "tur": "x11"})

    oturum("etapadmin")
    assert sistem.ortak_oturum() is None
    assert sistem.ortak_oturum(["etapadmin", "ogretmen"]) is None  # sunucu listesi genişletemez
    oturum("ayse")  # kişisel hesap
    assert sistem.ortak_oturum() is None and sistem.ortak_oturum(["ayse"]) is None
    oturum("root")
    assert sistem.ortak_oturum(["root"]) is None
    oturum("ogrenci")
    assert sistem.ortak_oturum(["ogretmen"]) is None  # sunucu daraltabilir
    oturum("ogretmen")
    assert sistem.ortak_oturum() == {"sinif": "ogretmen", "tur": "x11", "uid": 1001, "gid": 1001, "ev": "/home/ogretmen"}
    monkeypatch.setattr(sistem, "_etkin_oturum_ham", lambda: None)
    assert sistem.ortak_oturum() is None
    assert temizlik.TEMIZLENEBILIR_HESAPLAR == ("ogretmen", "ogrenci")


# ---- servis akışı -------------------------------------------------------------------------------
OTURUM = {"sinif": "ogretmen", "tur": "x11", "uid": 1001, "gid": 1001, "ev": "/home/ogretmen"}


@pytest.fixture
def servis(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_AJAN_DIZIN", str(tmp_path / "ayar"))
    monkeypatch.setenv("TAHTA_AJAN_DURUM", str(tmp_path / "durum"))
    monkeypatch.delenv("TAHTA_AJAN_BENZETIM", raising=False)
    from tahta_ajan import servis as servis_mod

    monkeypatch.setattr(servis_mod.sistem, "ortak_oturum", lambda izinli=None: dict(OTURUM))
    cagrilar = []

    def tarayici(oturum, kuru):
        cagrilar.append((oturum["uid"], kuru))
        return {"surecler": {"bulunan": 1, "zorla": 0, "kalan_aileler": []},
                "aileler": {"Firefox": {"profil": 1, "dosya": 4}}, "atlanan": 0, "hata": 0, "kuru": kuru}  # fmt: skip

    monkeypatch.setattr(servis_mod.sistem, "tarayici_temizligi", tarayici)
    s = servis_mod.Servis()
    s.arka_plan = lambda is_: is_()
    s.bildir = lambda: None
    s.gelen = []

    def gonder(mesaj):
        s.gelen.append(mesaj)
        if mesaj.get("tur") == "pencereleri_kapat":  # ekran yardımcısı yanıtı
            s.ekran_mesaji(1, {"tur": "pencere_sonucu", "istenen": 3, "atlanan": 1})

    s.ekranlar[1] = {"gonder": gonder, "bilgi": {"arayuz": "gtk3"}, "uid": 1001}
    s.cagrilar = cagrilar
    return s


def test_temizlik_kullanilan_tahtada_once_60_sn_uyari_verir_sonuc_ertelenir(servis):
    assert servis.komut_uygula({"id": 7, "tur": "temizlik", "veri": {"hesaplar": ["ogretmen", "ogrenci"]}}) is None
    assert 55 <= servis.gorunum()["temizlik"]["kalan"] <= 60
    assert servis.gelen[-1]["temizlik"] is not None and servis.durum_ozeti()["temizlik_bekliyor"] is True
    assert servis.sonuclar == [] and servis.cagrilar == []
    servis.temizlik["bitis"] = time.time() - 1  # süre doldu
    assert servis._temizlik_suresi_denetle() is True
    assert servis.gorunum()["temizlik"] is None
    assert any(m.get("tur") == "pencereleri_kapat" and m.get("kuru") is False for m in servis.gelen)
    (sonuc,) = servis.sonuclar
    assert sonuc["komut_id"] == 7 and sonuc["basarili"] is True
    assert sonuc["cikti"].startswith("Tamamlandı · Pencereler: 3 pencereye kapatma istendi, 1 pencere atlandı")
    assert "Firefox 1 profil, 4 çerez/oturum dosyası silindi" in sonuc["cikti"]
    assert "ogretmen" not in sonuc["cikti"] and "/home" not in sonuc["cikti"]  # kural 6
    assert servis.cagrilar == [(1001, False)] and servis.durum_ozeti()["temizlik_bekliyor"] is False


def test_temizlik_vazgec_ile_iptal_edilir(servis):
    servis.komut_uygula({"id": 8, "tur": "temizlik", "veri": {}})
    servis.ekran_mesaji(1, {"tur": "temizlik_iptal"})
    assert servis.temizlik is None and servis.cagrilar == []
    assert servis.sonuclar == [{"komut_id": 8, "basarili": True,
                                "cikti": "Vazgeçildi: tahtayı kullanan kişi temizliği iptal etti (tahta kullanılıyor)."}]  # fmt: skip
    servis.temizlik = None
    assert servis._temizlik_suresi_denetle() is False


def test_kapatma_uyarisi_temizlik_geri_sayimini_durdurur_vazgec_ikisini_de_iptal_eder(servis):
    """Kapatma uyarısı temizlik sayfasını örter (öncelik kapatma > temizlik): temizlik görünmeden çalışmasın."""
    servis.komut_uygula({"id": 22, "tur": "temizlik", "veri": {}})
    servis.kapatma = {"bitis": time.time() + 60, "neden": "Otomatik kapatma"}
    servis.temizlik["bitis"] = time.time() - 1  # geri sayım arkada bitmiş olurdu
    assert servis._temizlik_suresi_denetle() is False and servis.cagrilar == []
    assert servis.temizlik["bitis"] > time.time() + 50  # kapatma kalkınca 60 sn baştan
    servis.ekran_mesaji(1, {"tur": "kapatma_iptal"})  # kapatma sayfasındaki Vazgeç
    assert servis.kapatma is None and servis.temizlik is None and servis.cagrilar == []
    assert servis.sonuclar[-1]["komut_id"] == 22 and servis.sonuclar[-1]["cikti"].startswith("Vazgeçildi")


def test_temizlik_kilitli_tahtada_uyarisiz_calisir(servis):
    servis.kilitli = True
    assert servis.komut_uygula({"id": 9, "tur": "temizlik", "veri": {}}) is None
    assert servis.temizlik is None and servis.cagrilar == [(1001, False)]
    assert servis.sonuclar[0]["komut_id"] == 9 and servis.sonuclar[0]["cikti"].startswith("Tamamlandı")


def test_temizlik_ortak_olmayan_hesapta_hemen_atlanir(servis, monkeypatch):
    from tahta_ajan import servis as servis_mod

    monkeypatch.setattr(servis_mod.sistem, "ortak_oturum", lambda izinli=None: None)
    basarili, cikti = servis.komut_uygula({"id": 10, "tur": "temizlik", "veri": {}})
    assert basarili and cikti.startswith("Atlandı: oturum ortak hesap değil") and servis.cagrilar == []


def test_temizlik_acil_sinav_yoklama_ve_tekrar_durumunda_atlanir(servis):
    servis.komut_uygula({"id": 11, "tur": "temizlik", "veri": {}})
    assert servis.komut_uygula({"id": 12, "tur": "temizlik", "veri": {}}) == (True, "Atlandı: temizlik zaten sürüyor.")
    # Geri sayım sırasında acil yayın gelirse temizlik iptal edilir.
    servis._yanit_isle({"durum": "onayli", "ayar": {"acil": {"id": 3, "tur": "tatbikat", "baslik": "T", "metin": "M", "kalan_sn": 60}}})
    assert servis.temizlik is None and servis.sonuclar[-1]["komut_id"] == 11
    assert "acil yayın" in servis.sonuclar[-1]["cikti"]
    assert servis.komut_uygula({"id": 13, "tur": "temizlik", "veri": {}}) == (True, "Atlandı: acil yayın sürüyor.")
    assert servis.cagrilar == []


def test_temizlik_benzetimde_kuru_calisir(servis, monkeypatch):
    monkeypatch.setenv("TAHTA_AJAN_BENZETIM", "1")
    servis.kilitli = True
    servis.komut_uygula({"id": 14, "tur": "temizlik", "veri": {}})
    assert servis.cagrilar == [(1001, True)]
    assert any(m.get("tur") == "pencereleri_kapat" and m.get("kuru") is True for m in servis.gelen)
    assert "BENZETİM: hiçbir şey kapatılmadı ve silinmedi" in servis.sonuclar[0]["cikti"]


def test_temizlik_benzetimde_gercek_agacta_hicbir_sey_silinmez(servis, monkeypatch, ev, tmp_path, hizli):
    """Servis → (sahte oturum) → gerçek temizlik işlevleri; benzetimde ağaç ve süreçler aynen kalır."""
    from tahta_ajan import servis as servis_mod

    proc = tmp_path / "proc"
    sahte_proc(proc, {401: ("firefox-esr", 1001)})
    monkeypatch.setattr(servis_mod.sistem, "ortak_oturum", lambda izinli=None: dict(OTURUM, ev=ev))
    monkeypatch.setattr(servis_mod.sistem, "tarayici_temizligi",
                        lambda o, kuru: temizlik.tarayici_temizligi(o["ev"], o["uid"], kuru, proc=str(proc)))  # fmt: skip
    monkeypatch.setenv("TAHTA_AJAN_BENZETIM", "1")
    once = var_olanlar(ev)
    servis.kilitli = True
    servis.komut_uygula({"id": 15, "tur": "temizlik", "veri": {}})
    assert var_olanlar(ev) == once and (proc / "401").exists()
    cikti = servis.sonuclar[0]["cikti"]
    assert "1 tarayıcı süreci kapatılacak" in cikti and "Chromium 2 profil, 9 çerez/oturum dosyası silinecek" in cikti
    # Aynı akış benzetimsiz: dosyalar gerçekten silinir (süreç sahte /proc'ta kapanmaz → Firefox atlanır).
    monkeypatch.delenv("TAHTA_AJAN_BENZETIM")
    servis.komut_uygula({"id": 16, "tur": "temizlik", "veri": {}})
    kalan = var_olanlar(ev)
    assert ".config/chromium/Default/Cookies" not in kalan and ".mozilla/firefox/abcd1234.default-esr/cookies.sqlite" in kalan
    assert set(KALACAK) <= kalan


def test_temizlik_pencere_yaniti_gelmezse_atlanir_ve_wayland_desteklenmez(servis, monkeypatch):
    from tahta_ajan import servis as servis_mod

    monkeypatch.setattr(servis_mod, "TEMIZLIK_PENCERE_BEKLEME_SN", 0.01)
    servis.ekranlar[1]["gonder"] = servis.gelen.append  # yanıt vermeyen (eski) yardımcı
    servis.kilitli = True
    servis.komut_uygula({"id": 17, "tur": "temizlik", "veri": {}})
    assert "Pencereler: atlandı (ekran yardımcısı yanıt vermedi)" in servis.sonuclar[-1]["cikti"]
    monkeypatch.setattr(servis_mod.sistem, "ortak_oturum", lambda izinli=None: dict(OTURUM, tur="wayland"))
    servis.komut_uygula({"id": 18, "tur": "temizlik", "veri": {}})
    assert "Pencereler: atlandı (yalnız X11 oturumunda yapılır)" in servis.sonuclar[-1]["cikti"]


def test_temizlik_pencere_istegi_yalniz_temizlenen_oturumun_yardimcisina_gider(servis):
    """Kullanıcı değiştirmede arka planda etapadmin oturumu açık kalabilir; onun yardımcısı önce bağlanmış olsa
    da pencere isteği yalnız temizlenen ortak oturumun (uid 1001) yardımcısına gider."""
    yonetici = []
    servis.ekranlar = {0: {"gonder": yonetici.append, "bilgi": {"arayuz": "gtk3"}, "uid": 1000}, **servis.ekranlar}
    servis.kilitli = True
    servis.komut_uygula({"id": 19, "tur": "temizlik", "veri": {}})
    assert yonetici == [] or all(m.get("tur") != "pencereleri_kapat" for m in yonetici)
    assert any(m.get("tur") == "pencereleri_kapat" and m.get("uid") == 1001 for m in servis.gelen)
    # Ortak oturumun yardımcısı bağlı değilse (yalnız arka plandaki oturumunki varsa) adım atlanır.
    del servis.ekranlar[1]
    servis.komut_uygula({"id": 20, "tur": "temizlik", "veri": {}})
    assert all(m.get("tur") != "pencereleri_kapat" for m in yonetici)
    assert "Pencereler: atlandı (oturumun ekran yardımcısı bağlı değil)" in servis.sonuclar[-1]["cikti"]
    # Kimliği okunamayan bağlantı da hedef olmaz.
    servis.ekranlar[2] = {"gonder": yonetici.append, "bilgi": {"arayuz": "gtk3"}, "uid": None}
    servis.komut_uygula({"id": 21, "tur": "temizlik", "veri": {}})
    assert all(m.get("tur") != "pencereleri_kapat" for m in yonetici)


def test_yerel_baglanti_uid_proc_net_tcp_satirindan_okunur(tmp_path):
    from tahta_ajan import sistem

    (tmp_path / "net").mkdir()
    baslik = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode\n"
    (tmp_path / "net" / "tcp").write_text(
        baslik
        + "   0: 0100007F:1F9B 0100007F:D431 01 00000000:00000000 00:00000000 00000000     0        0 1 1\n"  # servis tarafı
        + "   1: 0100007F:D431 0100007F:1F9B 01 00000000:00000000 00:00000000 00000000  1001        0 2 1\n"  # yardımcı
        + "   2: 0100007F:D432 0100007F:1F9B 01 00000000:00000000 00:00000000 00000000  1000        0 3 1\n",
        encoding="ascii",
    )
    assert sistem.yerel_baglanti_uid(0xD431, 0x1F9B, proc=str(tmp_path)) == 1001
    assert sistem.yerel_baglanti_uid(0xD432, 0x1F9B, proc=str(tmp_path)) == 1000
    assert sistem.yerel_baglanti_uid(0xD433, 0x1F9B, proc=str(tmp_path)) is None


def test_temizlik_yetenegi_bildirilir(servis):
    assert "temizlik" in servis.durum_ozeti()["yetenekler"]


def test_temizlik_sureci_guvenli_bayraklarla_baslar():
    from tahta_ajan import sistem

    komut = sistem.temizlik_sureci_komutu("tarayici", "--ev", "/home/ogretmen")
    assert komut[0] == sys.executable and "-s" in komut and komut[-4:-2] == ["tahta_ajan.temizlik", "tarayici"]


def test_temizlik_komut_satiri_root_olarak_tarayici_adimini_reddeder(monkeypatch, capsys, ev):
    monkeypatch.setattr(os, "getuid", lambda: 0, raising=False)
    temizlik.main(["tarayici", "--ev", ev])
    assert "yönetici hesabıyla çalıştırılmaz" in capsys.readouterr().out
    assert ".config/chromium/Default/Cookies" in var_olanlar(ev)
