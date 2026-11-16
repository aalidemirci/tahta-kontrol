"""16.11.2026 kararları (0.8.0): K3 öğretim yılı sonuna kadar saklama, K4 acil yetkisi göçü, K5 yardımcı kayıt
metinleri, K6 boş ders uyarısı varsayılan açık + geçmiş ve rapor. Saat `saat` fikstürüyle sabittir
(pazartesi 16.11.2026). Bütün veriler UYDURMADIR."""

from __future__ import annotations

import json
import sqlite3

from yardimci import an, gir, ileti, kimlik, kullanici_ekle, kur_ve_gir, sorgu, tahta_ekle, zil_elle

from tahta_sunucu import vt


def saklama_kaydet(panel, tarih: str, onay: bool = False, **ek):
    form = {"bolum": "saklama", "ogretim_yili_bitis": tarih, **ek}
    if onay:
        form["sk_onay"] = "1"
    return panel.post("/ayarlar", data=form)


# ---- K3: öğretim yılı bitiş tarihi ---------------------------------------------------------------------
def test_tarih_girilmemisse_ayarlarda_uyari_cikar_ve_kaydedilir(panel, tahta, saat):
    kur_ve_gir(panel)
    sayfa = panel.get("/ayarlar").text
    assert "Öğretim yılı bitiş tarihi girilmedi" in sayfa and 'name="ogretim_yili_bitis"' in sayfa
    assert 'name="yk_saklama_gun"' not in sayfa  # gün sayılı saklama ayarı kalktı
    assert "Şifreli yedekler bu verinin kopyasını" in sayfa
    assert ileti(saklama_kaydet(panel, "2027-06-25")) == "Öğretim yılı bitiş tarihi kaydedildi: 25.06.2027."
    assert vt_ayar("ogretim_yili_bitis") == "2027-06-25"
    sayfa = panel.get("/ayarlar").text
    assert "Öğretim yılı bitiş tarihi girilmedi" not in sayfa and 'value="2027-06-25"' in sayfa
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Öğretim yılı bitiş tarihi kaydedildi'")[0]["ayrinti"] == (
        "yok → 25.06.2027"
    )
    assert ileti(saklama_kaydet(panel, "2027-06-25")) == "Öğretim yılı bitiş tarihi değişmedi."
    assert "kendiliğinden silinmeyecek" in ileti(saklama_kaydet(panel, ""))
    assert vt_ayar("ogretim_yili_bitis") is None


def vt_ayar(anahtar: str):
    with vt.islem() as b:
        return vt.ayar_al(b, anahtar)


def test_gecmis_tarih_onay_ister_ve_silinecekleri_sayar(panel, tahta, saat):
    kur_ve_gir(panel)
    with vt.islem() as b:
        b.execute("INSERT INTO yoklama (tarih, ders_no, sube, kaynak, kaydeden, mevcut, olusturma, guncelleme) "
                  "VALUES ('2026-06-20', 1, '9/A', 'panel', 'yonetici', 30, 1, 1)")  # fmt: skip
    yanit = saklama_kaydet(panel, "2026-06-26")
    assert "1 yoklama, 0 sınavın öğrenci listesi ve 0 boş ders uyarısı" in ileti(yanit) and "t=hata" in yanit.headers["location"]
    assert vt_ayar("ogretim_yili_bitis") is None
    assert sorgu("SELECT * FROM kayit WHERE islem = 'Saklama tarihi reddedildi'")
    assert ileti(saklama_kaydet(panel, "2026-06-26", onay=True)).startswith("Öğretim yılı bitiş tarihi kaydedildi")
    sayfa = panel.get("/ayarlar").text
    assert "26.06.2026) geçti" in sayfa and "Yeni öğretim yılının bitiş tarihini girin" in sayfa
    assert panel.app.state.yoklama_zamanlayici() is True
    assert sorgu("SELECT * FROM yoklama") == []


def test_cok_uzak_tarih_ve_yetkisiz_kullanici_reddedilir(panel, tahta, saat):
    kur_ve_gir(panel)
    assert "18 ay" in ileti(saklama_kaydet(panel, "2207-06-25"))
    assert "geçerli bir tarih" in ileti(saklama_kaydet(panel, "25.06.2027x"))
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    assert "yönetici yetkisi" in ileti(saklama_kaydet(panel, "2027-06-25"))
    assert vt_ayar("ogretim_yili_bitis") is None


def test_okul_zili_takviminden_tarih_onerilir(panel, tahta, saat):
    kur_ve_gir(panel)
    with vt.islem() as b:
        vt.ayar_yaz(b, "zil_takvimi", {"ogretim": {"bas": "2026-09-07", "bit": "2027-06-25"}})
    sayfa = panel.get("/ayarlar").text
    assert "Okul Zili takviminde öğretimin bitişi: 25.06.2027" in sayfa and 'name="oneri_kullan" value="2027-06-25"' in sayfa
    yanit = panel.post("/ayarlar", data={"bolum": "saklama", "ogretim_yili_bitis": "", "oneri_kullan": "2027-06-25"})
    assert ileti(yanit) == "Öğretim yılı bitiş tarihi kaydedildi: 25.06.2027."
    assert "Bu tarihi kullan" not in panel.get("/ayarlar").text


def test_onceki_tarih_gecmeden_ileri_tasinirsa_uyarir(panel, tahta, saat):
    kur_ve_gir(panel)
    saklama_kaydet(panel, "2027-06-25")
    assert "henüz geçmemişti" in ileti(saklama_kaydet(panel, "2028-01-20"))


def test_saklama_notlari_arayuzde_tarihe_gore_yazilir(panel, tahta, saat):
    kur_ve_gir(panel)
    assert "bitiş tarihi girilmediği için kendiliğinden silinmez" in panel.get("/sinavlar").text
    saklama_kaydet(panel, "2027-06-25")
    assert "öğretim yılı bitiş tarihi (25.06.2027) geçince kendiliğinden silinir" in panel.get("/sinavlar").text
    assert "(25.06.2027) geçince kendiliğinden silinir" in panel.get("/program/uyarilar").text


# ---- göç (0.7 → 0.8) ------------------------------------------------------------------------------------
def test_goc_acil_yetkisini_herkese_verir_ve_gun_sayili_saklamayi_kaldirir(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    b = sqlite3.connect(tmp_path / "tahta-kontrol.db")
    for sira in range(6):  # 0.7.x şeması (0.8.0 göçü 7. öğedir)
        b.executescript(vt.GOCLER[sira])
    b.execute("PRAGMA user_version = 6")
    b.execute("INSERT INTO kullanici (ad, gorunen_ad, parola_ozet, rol, olusturma, acil_yetki) VALUES ('i1', 'I', 'x', 'idareci', 1, 0)")
    b.execute("INSERT INTO ayar VALUES ('yoklama', ?)", (json.dumps({"etkin": True, "maske": "ad_soyadbas", "saklama_gun": 60}),))
    b.execute("INSERT INTO ayar VALUES ('bos_ders_uyarisi', ?)", (json.dumps({"etkin": False, "esik_dk": 10}),))
    b.commit()
    b.close()
    vt.hazirla()
    with vt.islem() as b:
        assert b.execute("SELECT acil_yetki FROM kullanici").fetchone()[0] == 1
        assert vt.ayar_al(b, "yoklama") == {"etkin": True, "maske": "ad_soyadbas"}
        # Yöneticinin açıkça kapattığı boş ders uyarısı göçle açılmaz; yalnız varsayılan açıktır.
        assert vt.ayar_al(b, "bos_ders_uyarisi")["etkin"] is False
        assert vt.ayar_al(b, "ogretim_yili_bitis") is None  # tarih kendiliğinden konmaz (yanlış silmeyi önler)
        assert b.execute("SELECT 1 FROM sqlite_master WHERE name = 'bos_ders_uyari_tarih'").fetchone()
    vt.hazirla()


# ---- K5: yardımcı kayıt metinleri ----------------------------------------------------------------------
def test_yoklama_sayfalari_kagidin_yaninda_yardimci_kayit_der(panel, tahta, saat):
    kur_ve_gir(panel)
    assert "kâğıt yoklamanın yanında tutulan yardımcı kayıttır" in panel.get("/yoklama").text
    assert "kâğıt yoklamanın yanında tutulan yardımcı kayıttır" in panel.get("/ayarlar").text
    with vt.islem() as b:
        b.execute("INSERT INTO ogrenci (sube, okul_no, ad, soyad, guncelleme) VALUES ('9/A', '901', 'Ali', 'ÖRNEK', 1)")
    assert "yerine geçmez" in panel.get("/yoklama/icmal?tarih=2026-11-16").text


# ---- K6: boş ders uyarısı varsayılan açık, geçmiş ve rapor ---------------------------------------------
def test_bos_ders_uyarisi_varsayilan_acik(panel, tahta, saat):
    kur_ve_gir(panel)
    assert panel.get("/api/durum").json()["program"]["bos_ders_etkin"] is True
    sayfa = panel.get("/program?bolum=kurallar").text
    assert 'name="bd_etkin" value="1" checked' in sayfa
    assert "Öğretmenlerin önceden bilgilendirilmesi okul idaresinin sorumluluğundadır" in sayfa


def uyari_ekle(tahta_id: int, tarih: str, ders_no: int, neden: str = "kapali", goruldu: str | None = None) -> None:
    with vt.islem() as b:
        b.execute(
            "INSERT INTO bos_ders_uyari (tahta_id, tarih, devre, ders_no, ders_bas, neden, olusturma, goruldu_kullanici, "
            "goruldu_zaman) VALUES (?, ?, 'normal', ?, ?, ?, 1, ?, ?)",
            (tahta_id, tarih, ders_no, int(an(int(tarih[8:]), 8 + ders_no, 0, ay=int(tarih[5:7])).timestamp()), neden,
             goruldu, 1 if goruldu else None),
        )  # fmt: skip


def test_bos_ders_raporu_tarih_araligi_tahta_ve_ders_suzgeci_kisi_adi_yok(panel, tahta, saat):
    kur_ve_gir(panel)
    zil_elle({"eylem": "uret", "devre_adi": "Normal", "ilk_ders": "08:20", "ders_sayisi": "8",
                                          "ders_dk": "40", "teneffus_dk": "10", "ogle_sonra": "4", "ogle_dk": "45",
                                          "gunler": ["0", "1", "2", "3", "4"]})  # fmt: skip
    t1 = kimlik(tahta_ekle(panel, tahta, "Z-04"))
    t2 = kimlik(tahta_ekle(panel, tahta, "Z-05"))
    uyari_ekle(t1, "2026-11-02", 1, goruldu="mudur.yrd")
    uyari_ekle(t1, "2026-11-10", 3, "kilitli")
    uyari_ekle(t2, "2026-11-12", 3, "oturumsuz")
    uyari_ekle(t2, "2026-09-01", 2)  # aralık dışı
    sayfa = panel.get("/program/uyarilar").text  # bugün: tek gün, kayda düşmez
    assert "Bu tarihte boş ders uyarısı yok" in sayfa
    assert sorgu("SELECT * FROM kayit WHERE islem = 'Boş ders raporu görüntülendi'") == []
    sayfa = panel.get("/program/uyarilar?bas=2026-11-01&bit=2026-11-16").text
    assert sayfa.count('data-etiket="Tarih"') == 3 and "02.11.2026" in sayfa and "01.09.2026" not in sayfa
    assert "Uyarı (16 gün)" in sayfa and "Tahta ve dersliğe göre" in sayfa and "3. ders" in sayfa
    assert "mudur.yrd" not in sayfa  # görüldü yalnız saattir; kişi adı yok
    kayit = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Boş ders raporu görüntülendi'")
    assert kayit[0]["ayrinti"] == "01.11.2026–16.11.2026"  # uyarının içeriği (tahta, sayı) kayda girmez
    sayfa = panel.get(f"/program/uyarilar?bas=2026-11-01&bit=2026-11-16&tahta={t2}").text
    assert sayfa.count('data-etiket="Tarih"') == 1 and "12.11.2026" in sayfa
    son = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Boş ders raporu görüntülendi' ORDER BY id DESC")[0]["ayrinti"]
    assert son == "01.11.2026–16.11.2026 · tahta süzgeci" and f"#{t2}" not in son
    sayfa = panel.get("/program/uyarilar?bas=2026-11-01&bit=2026-11-16&ders=3").text
    assert sayfa.count('data-etiket="Tarih"') == 2
    # Eski bağlantı (?tarih=) ve gelecek tarih bugüne kırpılır.
    assert "10.11.2026" in panel.get("/program/uyarilar?tarih=10.11.2026").text
    assert "Boş ders uyarıları · 16.11.2026" in panel.get("/program/uyarilar?tarih=2027-01-01").text


def test_idareci_raporu_gorur_goruldu_isaretler(panel, tahta, saat):
    kur_ve_gir(panel)
    t1 = kimlik(tahta_ekle(panel, tahta, "Z-04"))
    uyari_ekle(t1, "2026-11-16", 2)
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    sayfa = panel.get("/program/uyarilar").text
    assert "Ders boyunca boş" in sayfa
    uyari = sorgu("SELECT id FROM bos_ders_uyari")[0]["id"]
    assert ileti(panel.post(f"/program/uyarilar/{uyari}/goruldu")) == "Görüldü olarak işaretlendi."
    assert sorgu("SELECT goruldu_kullanici FROM bos_ders_uyari")[0]["goruldu_kullanici"] == "idareci1"
