"""Tahtadaki yüzer düğme (0.9.0, G3) ve kilit kalıcılığı (G2): servis akışı ve GTK'sız saf mantık."""

from __future__ import annotations

import json

import pytest

ACIK = {"acik": True, "islemler": ["kilitle", "kapat", "ariza"]}
KOD = {"tuz": "00", "ozet": "ab", "tur": 1000}


@pytest.fixture
def ortam(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_AJAN_DIZIN", str(tmp_path / "ayar"))
    monkeypatch.setenv("TAHTA_AJAN_DURUM", str(tmp_path / "durum"))
    from tahta_ajan import servis as servis_mod

    guc = []
    monkeypatch.setattr(servis_mod.sistem, "kapat", lambda: guc.append("kapat") or (True, "benzetim"))
    monkeypatch.setattr(servis_mod.sistem, "yeniden_baslat", lambda: guc.append("yeniden") or (True, "benzetim"))
    monkeypatch.setattr(servis_mod.sistem, "etkin_oturum", lambda: {"sinif": "ogretmen", "tur": "x11"})
    monkeypatch.setattr(servis_mod.sistem, "acik_sure", lambda: 100)

    def yeni():
        s = servis_mod.Servis()
        s.gelen = []
        s.ekranlar[1] = {"gonder": s.gelen.append, "bilgi": {"arayuz": "gtk3"}}
        s.bildirilen = 0
        s.zamanlanan = []

        def bildir():
            s.bildirilen += 1

        s.bildir = bildir
        s.zamanla = lambda sn, is_: s.zamanlanan.append((sn, is_))
        return s

    return yeni, guc, servis_mod


def ayarla(servis, dugme=ACIK, kod=KOD):
    servis._yanit_isle({"ayar": {"dugme": dugme, "kilit_kodu": kod}})


# ---- ayar ---------------------------------------------------------------------------------------
def test_ayar_yoksa_dugme_kapali_ve_yetenek_bildirilir(ortam):
    yeni, _, _ = ortam
    servis = yeni()
    assert servis.dugme is None
    assert servis.gorunum()["dugme"] == {"acik": False, "islemler": [], "kilitle_kullanilabilir": False}
    assert "dugme" in servis.durum_ozeti()["yetenekler"]


def test_ayar_dogrulanir_sirasi_sabit_bilinmeyen_atilir(ortam):
    _, _, servis_mod = ortam
    coz = servis_mod._dugme_coz
    assert coz(None) is None
    assert coz({"acik": True, "islemler": ["ariza", "sil", "kilitle"]}) == {"acik": True, "islemler": ["kilitle", "ariza"]}
    assert coz({"acik": True, "islemler": []}) == {"acik": False, "islemler": []}
    assert coz({"acik": "evet", "islemler": ["kilitle"]}) == {"acik": False, "islemler": []}
    assert coz("bozuk") == {"acik": False, "islemler": []}


def test_ayar_kalici_sunucusuz_yeniden_baslatmada_kalir(ortam):
    yeni, _, servis_mod = ortam
    servis = yeni()
    ayarla(servis)
    assert servis.gorunum()["dugme"] == {"acik": True, "islemler": ["kilitle", "kapat", "ariza"], "kilitle_kullanilabilir": True}
    kayit = servis_mod.ayar.durum_oku()
    assert kayit["dugme"] == ACIK
    yeniden = yeni()  # sunucuya hiç ulaşılmadan
    assert yeniden.gorunum()["dugme"]["acik"] is True


def test_eski_sunucu_alan_gondermezse_dugme_kalkar(ortam):
    yeni, _, _ = ortam
    servis = yeni()
    ayarla(servis)
    servis._yanit_isle({"ayar": {"okul_adi": "Deneme"}})
    assert servis.dugme is None and servis.gorunum()["dugme"]["acik"] is False


def test_kilit_kodu_ozeti_ekrana_gitmez(ortam):
    yeni, _, _ = ortam
    servis = yeni()
    ayarla(servis)
    metin = json.dumps(servis.gorunum())
    assert "ozet" not in metin and "tuz" not in metin


# ---- yerel kilit ----------------------------------------------------------------------------------
def test_tahtadan_kilitleme_idare_kilidi_olay_ve_kalicilik(ortam):
    yeni, _, servis_mod = ortam
    servis = yeni()
    ayarla(servis)
    servis.ekran_mesaji(1, {"tur": "yerel_kilitle"})
    assert servis.kilitli and servis.kilit_kaynak == "idare"
    assert servis.olaylar[-1] == "Tahtadan kilitlendi (oturum: ogretmen)."
    assert servis.gelen[-1] == {"tur": "dugme_sonuc", "islem": "kilitle", "basarili": True, "mesaj": "Kilitlendi."}
    assert any(m.get("tur") == "durum" and m["kilitli"] for m in servis.gelen)
    assert servis.bildirilen >= 1
    ozet = servis.durum_ozeti()
    assert ozet["kilitli"] and ozet["kilit_kaynak"] == "idare"
    # G2: oturum kapanıp açılınca (yeni yardımcı) ya da servis yeniden başlayınca kilit sürer.
    assert servis_mod.ayar.durum_oku()["kilitli"] is True
    yeniden = yeni()
    assert yeniden.kilitli and yeniden.gorunum()["kilitli"]


def test_tahtadan_kilitleme_sunucusuz_calisir(ortam):
    yeni, _, _ = ortam
    servis = yeni()
    ayarla(servis)
    servis.istemci = None
    servis.son_temas = 0  # çevrimdışı
    basarili, _ = servis.dugme_islemi("kilitle")
    assert basarili and servis.kilitli


def test_kilit_kodu_yoksa_kilitlemez(ortam):
    yeni, _, _ = ortam
    servis = yeni()
    ayarla(servis, kod=None)
    assert servis.gorunum()["dugme"]["kilitle_kullanilabilir"] is False
    servis.ekran_mesaji(1, {"tur": "yerel_kilitle"})
    assert not servis.kilitli
    assert servis.gelen[-1]["basarili"] is False and "kilit kodu" in servis.gelen[-1]["mesaj"].lower()
    assert not servis.olaylar


def test_ayarda_olmayan_islem_reddedilir(ortam):
    yeni, guc, _ = ortam
    servis = yeni()
    ayarla(servis, dugme={"acik": True, "islemler": ["ariza"]})
    assert servis.dugme_islemi("kilitle")[0] is False and not servis.kilitli
    assert servis.dugme_islemi("yeniden_baslat")[0] is False
    assert servis.dugme_islemi("bilinmeyen")[0] is False
    assert not servis.zamanlanan and not guc
    ayarla(servis, dugme={"acik": False, "islemler": ["kilitle"]})
    assert servis.dugme_islemi("kilitle")[0] is False


def test_sinav_ve_acil_sirasinda_reddedilir(ortam):
    yeni, _, _ = ortam
    servis = yeni()
    ayarla(servis)
    servis.acil = {"id": 1, "tur": "tatbikat", "baslik": "", "metin": "", "bitis": 10**12}
    assert servis.dugme_islemi("kilitle") == (False, "Acil yayın sürüyor; işlem yapılamaz.")
    servis.acil = None
    servis._sinav_aktif = lambda: {"kimlik": "s1"}
    assert servis.dugme_islemi("kapat")[0] is False


def test_kilitliyken_dugme_islemi_kilidi_degistirmez_kapatmaz(ortam):
    """İnceleme bulgusu: düğme kilit ekranında gizlidir; yine de gelen istek süreli program kilidini süresiz
    idare kilidine çevirmez, kilitli tahtayı onaysız kapatmaz."""
    yeni, guc, _ = ortam
    servis = yeni()
    ayarla(servis)
    servis.komut_uygula({"tur": "kilitle", "veri": {"kaynak": "program", "sure_sn": 300, "neden": "Teneffüs"}})
    assert servis.kilit_kaynak == "program"
    assert servis.dugme_islemi("kilitle") == (True, "Tahta zaten kilitli.")
    assert servis.kilit_kaynak == "program" and servis.kilit_bitis is not None
    assert servis.dugme_islemi("kapat")[0] is False and not servis.zamanlanan and not guc


def test_yerel_istek_yalniz_ekrandaki_oturumun_yardimcisindan(ortam, monkeypatch):
    yeni, guc, servis_mod = ortam
    servis = yeni()
    ayarla(servis)
    monkeypatch.setattr(servis_mod.sistem, "etkin_oturum_uid", lambda: 1001)
    servis.ekranlar[1]["uid"] = 1002  # arka plandaki başka bir hesabın süreci
    servis.ekran_mesaji(1, {"tur": "yerel_kapat"})
    assert servis.gelen[-1]["basarili"] is False and not servis.zamanlanan and not servis.olaylar
    servis.ekranlar[2] = {"gonder": servis.gelen.append, "bilgi": {"arayuz": "komut"}, "uid": 1001}
    servis.ekran_mesaji(2, {"tur": "yerel_kilitle"})  # kısa ömürlü komut istemcisi düğme kullanamaz
    assert not servis.kilitli and servis.gelen[-1]["basarili"] is False
    servis.ekranlar[1]["uid"] = 1001
    servis.ekran_mesaji(1, {"tur": "yerel_kilitle"})
    assert servis.kilitli


def test_kodla_acilinca_dugme_geri_gelir_kilit_kodu_ile(ortam):
    import hashlib

    yeni, _, _ = ortam
    servis = yeni()
    tuz = "0011"
    kod = {"tuz": tuz, "tur": 1000, "ozet": hashlib.pbkdf2_hmac("sha256", b"4826", bytes.fromhex(tuz), 1000).hex()}
    ayarla(servis, kod=kod)
    servis.dugme_islemi("kilitle")
    servis.ekran_mesaji(1, {"tur": "kod", "kod": "4826"})
    assert not servis.kilitli
    assert servis.gorunum()["dugme"]["acik"] is True


# ---- yerel kapatma / yeniden başlatma -----------------------------------------------------------------
def test_tahtadan_kapatma_olay_once_sonra_uygulanir(ortam):
    yeni, guc, servis_mod = ortam
    servis = yeni()
    ayarla(servis)
    servis.ekran_mesaji(1, {"tur": "yerel_kapat"})
    assert servis.olaylar[-1] == "Tahtadan kapatıldı (oturum: ogretmen)."
    assert servis.bildirilen >= 1 and not guc  # henüz kapanmadı: olay önce gider
    (sn, is_), = servis.zamanlanan
    assert sn == servis_mod.DUGME_GUC_GECIKME_SN
    is_()
    assert guc == ["kapat"]


def test_yeniden_baslatma_ayarla_acilir(ortam):
    yeni, guc, _ = ortam
    servis = yeni()
    ayarla(servis)
    assert servis.dugme_islemi("yeniden_baslat")[0] is False
    ayarla(servis, dugme={"acik": True, "islemler": ["kilitle", "yeniden_baslat"]})
    assert servis.dugme_islemi("yeniden_baslat")[0] is True
    servis.zamanlanan[0][1]()
    assert guc == ["yeniden"] and servis.olaylar[-1].startswith("Tahtadan yeniden başlatıldı")


def test_tani_metinleri_sir_tasimaz(ortam):
    yeni, _, _ = ortam
    servis = yeni()
    ayarla(servis)
    servis.ekranlar[1]["bilgi"].update(dugme=True, bilesik=False)
    metin = servis.dugme_tani_metni()
    assert "açık" in metin and "1 düğmeli" in metin and "ozet" not in metin
    assert servis.kilit_tani_metni().startswith("açık · oturum yok")
    servis.dugme_islemi("kilitle")
    assert servis.kilit_tani_metni().startswith("kilitli (idare) · ")


def test_tani_kilit_kaliciligi_satiri(ortam, tmp_path):
    from tahta_ajan import tani

    yeni, _, _ = ortam
    servis = yeni()
    ayarla(servis)
    servis.dugme_islemi("kilitle")
    sonuc, ayrinti = tani._kilit_kaliciligi(servis.kilit_tani_metni())
    assert sonuc == tani.TAMAM and "durum.json: kilitli (idare)" in ayrinti
    assert "ozet" not in ayrinti and "tuz" not in ayrinti  # özet rapora girmez


def test_tani_otomatik_baslatma_kapatilmis_hesap(monkeypatch):
    from tahta_ajan import tani

    dosyalar = {
        "/sistem/tahta-ekran.desktop": "[Desktop Entry]\nExec=/usr/bin/tahta-ajan ekran\n",
        "/passwd": "ogretmen:x:1001:1001::/ev/ogretmen:/bin/bash\nayse:x:1002:1002::/ev/ayse:/bin/bash\n"
        "daemon:x:1:1::/usr/sbin:/usr/sbin/nologin\n",
        "/ev/ogretmen/.config/autostart/tahta-ekran.desktop": "[Desktop Entry]\nHidden=true\n",
        "/ev/ayse/.config/autostart/tahta-ekran.desktop": "[Desktop Entry]\nX-GNOME-Autostart-enabled=false\n",
    }
    monkeypatch.setattr(tani, "OTOMATIK_BASLATMA", "/sistem/tahta-ekran.desktop")
    monkeypatch.setattr(tani, "_oku", lambda yol, sinir=3000: dosyalar.get(str(yol).replace("\\", "/"), ""))
    sonuc, ayrinti = tani._otomatik_baslatma("/passwd")
    assert sonuc == tani.SORUN and "ogretmen" in ayrinti and "1 kişisel hesap" in ayrinti
    assert "ayse" not in ayrinti and "/ev/" not in ayrinti  # kişisel hesap adı ve ev dizini rapora girmez
    del dosyalar["/ev/ogretmen/.config/autostart/tahta-ekran.desktop"], dosyalar["/ev/ayse/.config/autostart/tahta-ekran.desktop"]
    assert tani._otomatik_baslatma("/passwd")[0] == tani.TAMAM
    dosyalar["/sistem/tahta-ekran.desktop"] += "Hidden=true\n"
    assert tani._otomatik_baslatma("/passwd")[0] == tani.SORUN
    del dosyalar["/sistem/tahta-ekran.desktop"]
    assert tani._otomatik_baslatma("/passwd")[0] == tani.SORUN


def test_tani_oturum_acik_yardimci_yoksa_sorun():
    from tahta_ajan import tani

    assert tani._ekran([], "ogretmen")[0] == tani.SORUN
    assert tani._ekran([], "yok")[0] == tani.UYARI


# ---- ekran tarafı: saf mantık -----------------------------------------------------------------------
def test_menu_ogeleri_sira_ve_kodsuz_kilitle():
    from tahta_ajan import yuzer

    ayar_ = {"acik": True, "islemler": ["kilitle", "kapat", "yeniden_baslat", "ariza", "yoklama"], "kilitle_kullanilabilir": True}
    assert [o["etiket"] for o in yuzer.menu_ogeleri(ayar_)] == ["Kilitle", "Kapat", "Yeniden başlat", "Arıza bildir", "Yoklama al"]
    ogeler = yuzer.menu_ogeleri(dict(ayar_, kilitle_kullanilabilir=False))
    assert ogeler[0] == {"islem": "kilitle", "etiket": "Kilitle (kilit kodu belirlenmemiş)", "etkin": False}
    assert all(o["etkin"] for o in ogeler[1:])


def test_gorunurluk_kurallari():
    from tahta_ajan import yuzer

    durum = {"kilitli": False, "dugme": {"acik": True, "islemler": ["kapat"], "kilitle_kullanilabilir": False}}
    assert yuzer.gorunur_mu(durum, ana_gorunur=False)
    assert not yuzer.gorunur_mu(durum, ana_gorunur=True)  # kilit/duyuru/acil/sınav/yoklama sayfası açık
    assert not yuzer.gorunur_mu(dict(durum, kilitli=True), ana_gorunur=False)
    assert not yuzer.gorunur_mu(None, ana_gorunur=False)  # servis yok
    assert not yuzer.gorunur_mu({"kilitli": False}, ana_gorunur=False)  # eski servis: alan yok
    assert not yuzer.gorunur_mu(dict(durum, dugme={"acik": True, "islemler": []}), ana_gorunur=False)
    assert not yuzer.gorunur_mu(dict(durum, dugme={"acik": False, "islemler": ["kapat"]}), ana_gorunur=False)


def test_varsayilan_konum_sag_alt_ve_yapisma():
    from tahta_ajan import yuzer

    alan = (0, 0, 1920, 1040)  # alt panel 40 px
    assert yuzer.konum("sag", 1.0, 60, alan, 18) == (1920 - 60 - 18, 1040 - 60 - 18)
    assert yuzer.konum("sol", 0.0, 60, alan, 18) == (18, 18)
    assert yuzer.yapis(300, 500, 60, alan, 18)[0] == "sol"
    assert yuzer.yapis(1500, 500, 60, alan, 18)[0] == "sag"
    kenar, oran = yuzer.yapis(1500, 5000, 60, alan, 18)  # alan dışına bırakılsa da içeri alınır
    assert kenar == "sag" and oran == 1.0
    kenar, oran = yuzer.yapis(100, 18 + (1040 - 60 - 36) // 2, 60, alan, 18)
    assert abs(oran - 0.5) < 0.01
    # Çözünürlük değişse de aynı kenar ve oran
    x, y = yuzer.konum(kenar, oran, 40, (0, 0, 1366, 768), 13)
    assert x == 13 and 768 * 0.4 < y < 768 * 0.6


def test_ikinci_monitor_kaydirmasi():
    from tahta_ajan import yuzer

    alan = (1920, 0, 1366, 768)  # birincil monitör sağdaysa çalışma alanı kaydırılmıştır
    x, y = yuzer.konum("sol", 0.0, 43, alan, 13)
    assert x == 1933 and y == 13
    assert yuzer.sinirla(0, 0, 43, alan) == (1920, 0)


def test_menu_konumu_ekrana_sigar():
    from tahta_ajan import yuzer

    alan = (0, 0, 1366, 768)
    # Sağ altta düğme: menü soluna, altı düğmenin altıyla hizalı
    x, y = yuzer.menu_konumu(1310, 712, 43, 177, 196, alan, 9)
    assert x + 177 <= 1310 and y + 196 == 712 + 43
    # Sol üstte düğme: menü sağına, üstü hizalı
    x, y = yuzer.menu_konumu(13, 13, 43, 421, 196, alan, 9)
    assert x == 13 + 43 + 9 and y == 13
    # Menü düğmeden büyükse ve aşağı taşacaksa yukarı itilir
    x, y = yuzer.menu_konumu(13, 600, 43, 421, 400, alan, 9)
    assert y + 400 <= 768 and y >= 0
    # Dar ekranda menü ekrandan geniş olamaz; sol kenara dayanır
    x, y = yuzer.menu_konumu(300, 10, 43, 600, 100, (0, 0, 640, 480), 9)
    assert 0 <= x and x + 600 <= 640


def test_olcek_sabit_piksel_yok():
    from tahta_ajan import ekran, yuzer

    assert yuzer.olcekle(yuzer.DUGME_CAP, ekran.ekran_olcegi(1920, 1080)) == 60
    assert yuzer.olcekle(yuzer.DUGME_CAP, ekran.ekran_olcegi(1366, 768)) == 43
    assert yuzer.olcekle(yuzer.DUGME_CAP, ekran.ekran_olcegi(3840, 2160)) == 120
    olcekli = ekran.olcekli_stil(yuzer.STIL, 0.5).decode()
    assert "min-width: 30px" in olcekli and "font-size: 14px" in olcekli


def test_geri_sayim_metni():
    from tahta_ajan import yuzer

    assert yuzer.geri_sayim_metni("kapat", 10) == ("Tahta kapatılacak", "10")
    assert yuzer.geri_sayim_metni("yeniden_baslat", -3) == ("Tahta yeniden başlatılacak", "0")
    assert set(yuzer.ONAYLI) == {"kapat", "yeniden_baslat"} and "kilitle" not in yuzer.ONAYLI


def test_tek_ornek_yolu_yalniz_ozel_dizinde(tmp_path):
    from tahta_ajan import ekran

    assert ekran.tek_ornek_yolu({"DISPLAY": ":0"}) is None  # XDG_RUNTIME_DIR yok: /tmp kullanılmaz
    yol = ekran.tek_ornek_yolu({"XDG_RUNTIME_DIR": str(tmp_path), "DISPLAY": ":0"})
    assert yol.startswith(str(tmp_path)) and yol.endswith("tahta-ekran-_0.kilit")
    import os

    kotu = ekran.tek_ornek_yolu({"XDG_RUNTIME_DIR": str(tmp_path), "DISPLAY": "../../x"})
    assert os.path.dirname(kotu) == str(tmp_path)


def test_yuzer_modulu_pakete_girer():
    import gzip
    import io
    import tarfile

    from tahta_sunucu import paket

    icerik = paket.ajan_paketi().icerik
    bas = icerik.index(b"data.tar.gz")
    boy = int(icerik[bas + 48 : bas + 58].decode("ascii").strip())
    veri = icerik[bas + 60 : bas + 60 + boy]
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(veri))) as arsiv:
        assert "./opt/tahta-kontrol/tahta_ajan/yuzer.py" in arsiv.getnames()


# ---- açılışta kilit: oturum kimliği (0.9.0) ----------------------------------------------------------
@pytest.fixture
def acilis(ortam, monkeypatch):
    yeni, _, servis_mod = ortam
    saat = {"simdi": 100.0, "acilis": "acilis-1"}
    monkeypatch.setattr(servis_mod.sistem, "acik_sure_tam", lambda: saat["simdi"])
    monkeypatch.setattr(servis_mod.sistem, "acilis_kimligi", lambda: saat["acilis"])
    return yeni, saat


def merhaba(servis, baslangic, arayuz="gtk3", no=1):
    servis.ekranlar.setdefault(no, {"gonder": servis.gelen.append, "bilgi": {}})
    servis.ekran_mesaji(no, {"tur": "merhaba", "arayuz": arayuz, "oturum_baslangic": baslangic})


def test_oturum_yardimci_baglaninca_acilir_yasi_acilis_sayaciyla(acilis):
    yeni, _ = acilis
    servis = yeni()
    assert servis.oturum_ozeti() == {"oturum_no": None, "oturum_yasi_sn": None}
    merhaba(servis, 90.0)
    ozet = servis.durum_ozeti()
    assert len(ozet["oturum_no"]) == 12 and ozet["oturum_yasi_sn"] == 10
    # Başlangıç ekranlar listesine (sunucuya giden bilgi) girmez; hesap adı hiç yoktur.
    assert all("oturum_baslangic" not in e for e in ozet["ekranlar"])


def test_ayni_yardimci_yeniden_baglaninca_oturum_degismez(acilis):
    yeni, saat = acilis
    servis = yeni()
    merhaba(servis, 90.0)
    no = servis.oturum["no"]
    merhaba(servis, 90.0, no=2)  # soket koptu, yeniden bağlandı (ya da execv ile güncellendi)
    merhaba(servis, 50.0, no=3)  # eski oturumdan kalan yardımcı
    merhaba(servis, 95.0, arayuz="komut", no=4)  # kısa ömürlü istemci oturum açmaz
    merhaba(servis, None, no=5)  # eski yardımcı alanı göndermez
    merhaba(servis, "95", no=6)
    assert servis.oturum["no"] == no
    # Oturum kapatılıp açıldı: yeni yardımcı daha geç başladı.
    saat["simdi"] = 400.0
    merhaba(servis, 380.0, no=7)
    assert servis.oturum["no"] != no and servis.oturum_ozeti()["oturum_yasi_sn"] == 20


def test_oturum_servis_yeniden_baslayinca_korunur_yeni_acilista_duser(acilis):
    yeni, saat = acilis
    servis = yeni()
    merhaba(servis, 90.0)
    no = servis.oturum["no"]
    yeniden = yeni()  # aynı açılışta servis yeniden başladı
    assert yeniden.oturum == {"no": no, "baslangic": 90.0}
    merhaba(yeniden, 90.0)
    assert yeniden.oturum["no"] == no  # sunucu aynı oturumu yeniden kilitlemez
    saat["acilis"] = "acilis-2"  # tahta yeniden başladı
    yeniden = yeni()
    assert yeniden.oturum is None
    merhaba(yeniden, 30.0)  # yeni açılışta sayaç küçük olsa da yeni oturum
    assert yeniden.oturum["no"] != no


def test_surec_baslangici_stat_ayristirma(tmp_path, monkeypatch):
    from tahta_ajan import sistem

    yol = tmp_path / "stat"
    alanlar = ["S"] + ["0"] * 18 + ["12345"] + ["0"] * 10  # 22. alan (starttime) = 12345 tık
    yol.write_text("4242 (tahta ajan (x)) " + " ".join(alanlar), encoding="ascii")
    monkeypatch.setattr(sistem, "LINUX", True)
    monkeypatch.setattr(sistem.os, "sysconf", lambda ad: 100, raising=False)
    assert sistem.surec_baslangici(str(yol)) == 123.45
    assert sistem.surec_baslangici(str(tmp_path / "yok")) is None


def test_gelecekteki_oturum_baslangici_reddedilir(acilis, monkeypatch):
    """İnceleme bulgusu: açılış sayacından ileride bir başlangıç, sonraki gerçek oturumları eski göstermesin;
    başka bir hesabın süreci de oturum açamasın."""
    yeni, saat = acilis
    servis = yeni()
    merhaba(servis, 999999999)
    assert servis.oturum is None
    merhaba(servis, 90.0)
    assert servis.oturum is not None and servis.oturum["baslangic"] == 90.0
    from tahta_ajan import servis as servis_mod

    monkeypatch.setattr(servis_mod.sistem, "etkin_oturum_uid", lambda: 1001)
    no = servis.oturum["no"]
    servis.ekranlar[8] = {"gonder": servis.gelen.append, "bilgi": {}, "uid": 1002}
    merhaba(servis, 99.0, no=8)
    assert servis.oturum["no"] == no
