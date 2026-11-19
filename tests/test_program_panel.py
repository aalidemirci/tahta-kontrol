"""Aşama 3 — program uçları, yetkiler, zamanlayıcı (program kilidi, açma, boş ders uyarısı), göç.

Saat `saat` fikstürüyle sabittir (pazartesi 16.11.2026); zamanlayıcıya aynı an verilir. Veriler uydurmadır.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from yardimci import (
    SAHTE_TC,
    an,
    bekle,
    gir,
    ileti,
    kimlik,
    komut_verisi,
    kullanici_ekle,
    kur_ve_gir,
    sorgu,
    tahta_ekle,
    zil_elle,
)

ORNEK = Path(__file__).parent / "ornek" / "okulzili-ornek.json"
YETENEKLER = ["acil", "duyuru_id", "program_kilidi"]
ELLE = {"eylem": "uret", "devre_adi": "Normal", "ilk_ders": "08:20", "ders_sayisi": "8", "ders_dk": "40",
        "teneffus_dk": "10", "ogle_sonra": "4", "ogle_dk": "45", "gunler": ["0", "1", "2", "3", "4"]}  # fmt: skip
# Üretilen dersler: 1 08:20–09:00 · 2 09:10–09:50 · 3 10:00–10:40 · 4 10:50–11:30 · öğle · 5 12:15–12:55 …


def durum(**ek) -> dict:
    return {"kilitli": False, "yetenekler": YETENEKLER, "ekranlar": [{"arayuz": "gtk3"}],
            "oturum": {"sinif": "ogretmen"}, **ek}  # fmt: skip


def hazirla(panel, kilit=True, bos=False, **kural) -> None:
    kur_ve_gir(panel)
    assert zil_elle(ELLE) == "Zil saatleri kaydedildi."
    form = {"pk_gecikme_dk": "2", "pk_bos_saatte": "1", "bd_esik_dk": "10", **kural}
    if kilit:
        form["pk_etkin"] = "1"
    if bos:
        form["bd_etkin"] = "1"
    assert ileti(panel.post("/program/kurallar", data=form)) == "Kurallar kaydedildi."


def calistir(uygulama, saat, zaman, canli: bool = True) -> list[int]:
    """Zamanlayıcıyı `zaman`da çalıştırır; canli=True ise bütün tahtalar uzun beklemede (çevrimiçi) sayılır."""
    from tahta_sunucu import vt

    saat.ayarla(zaman)
    if canli:
        with vt.islem() as b:
            b.execute("UPDATE tahta SET son_gorulme = ?", (vt.simdi(),))
    return uygulama.state.program_zamanlayici(zaman)


def program_komutlari(tahta_id: int, tur: str | None = None) -> list[dict]:
    satirlar = sorgu("SELECT * FROM komut WHERE tahta_id = ? ORDER BY id", tahta_id)
    return [s for s in satirlar if json.loads(s["veri_json"]).get("kaynak") == "program" and (tur is None or s["tur"] == tur)]


def ders_isaretle(panel, tahta_id: int, dersler: list[int], gun: int = 0, **ek) -> None:
    form = {f"d_{gun}_normal_{n}": "1" for n in dersler} | ek
    assert ileti(panel.post(f"/tahta/{tahta_id}/program", data=form)) == "Program kaydedildi."


# 17
def test_program_kilidi_tenefuste_bir_kez_verilir(uygulama, panel, tahta, saat):
    hazirla(panel)
    saat.ayarla(an(16, 9, 0, 30))
    b = tahta_ekle(panel, tahta, "T-1", durum())
    t = kimlik(b)
    assert calistir(uygulama, saat, an(16, 9, 1, 30)) == []  # gecikme (2 dk) dolmadı
    assert calistir(uygulama, saat, an(16, 9, 2, 10)) == [t]
    komut = program_komutlari(t, "kilitle")
    assert len(komut) == 1
    veri = komut_verisi(komut[0])
    assert veri["neden"] == "Teneffüs" and veri["acilis"] == "09:10"
    assert komut[0]["bitis"] - komut[0]["olusturma"] == 120 and komut[0]["olusturan"] == "sistem"
    assert calistir(uygulama, saat, an(16, 9, 3)) == []  # aynı aralıkta bir kez
    saat.ayarla(an(16, 9, 3, 20))
    inen = bekle(tahta, b, durum())["komutlar"]
    assert inen[0]["tur"] == "kilitle" and inen[0]["veri"]["sure_sn"] == 400 and "bitis_sunucu" not in inen[0]["veri"]
    assert sorgu("SELECT COUNT(*) AS n FROM kayit WHERE islem = 'Program kilidi'")[0]["n"] == 1
    assert calistir(uygulama, saat, an(16, 9, 8)) == []  # aralık bitimine 3 dk'dan az


# 18
def test_program_kilidi_dersi_olmayan_saatte_ve_ogle_arasinda(uygulama, panel, tahta, saat):
    hazirla(panel)
    b = tahta_ekle(panel, tahta, "T-1", durum())
    t = kimlik(b)
    ders_isaretle(panel, t, [1, 4, 5])
    calistir(uygulama, saat, an(16, 9, 5))
    veri = komut_verisi(program_komutlari(t, "kilitle")[0])
    assert veri["neden"] == "Bu saatte bu derslikte ders yok" and veri["acilis"] == "10:50"
    calistir(uygulama, saat, an(16, 11, 35))
    veri = komut_verisi(program_komutlari(t, "kilitle")[1])
    assert veri["neden"] == "Öğle arası" and veri["acilis"] == "12:15"
    # Dersi olmayan saatte kilit kapalıysa yalnız teneffüs/öğle arası kilitlenir.
    panel.post("/program/kurallar", data={"pk_etkin": "1", "pk_gecikme_dk": "2", "bd_esik_dk": "10"})
    calistir(uygulama, saat, an(16, 13, 47))
    assert komut_verisi(program_komutlari(t, "kilitle")[2])["neden"] == "Teneffüs"


# 19
def test_program_kilidi_eski_ajana_verilmez(uygulama, panel, tahta, saat):
    hazirla(panel)
    b = tahta_ekle(panel, tahta, "Eski", {"kilitli": False, "yetenekler": ["acil", "duyuru_id"]})
    assert calistir(uygulama, saat, an(16, 9, 3)) == []
    assert program_komutlari(kimlik(b)) == []
    tahta_gorunum = panel.get("/api/durum").json()["tahtalar"][0]
    assert tahta_gorunum["program"]["program_yetenegi"] is False
    assert "program_kilidi" not in tahta_gorunum["yetenekler"]


# 20
def test_program_kilidi_muaf_istisna_sinav_tatilde_verilmez(uygulama, panel, tahta, saat):
    from tahta_sunucu import vt

    hazirla(panel)
    muaf = kimlik(tahta_ekle(panel, tahta, "Kütüphane", durum()))
    ders_isaretle(panel, muaf, [], program_muaf="1")
    diger = kimlik(tahta_ekle(panel, tahta, "T-2", durum()))
    saat.ayarla(an(16, 9, 0))
    panel.post("/program/istisna", data={"sure": "1sa", "tahta": str(diger)})
    assert calistir(uygulama, saat, an(16, 9, 3)) == []
    # sınav penceresi (Okul Zili'nin planlı sınavı) ve tatil kuralı
    with vt.islem() as b:
        vt.ayar_yaz(b, "zil_takvimi", {"ogretim": None, "resmi_tatiller": False, "kurallar": [
            {"ad": "Deneme", "tur": "sinav_plani", "bas": "2026-11-17", "bit": "2026-11-17", "gunler": [1],
             "pencereler": [["08:55", "09:45"]], "tum_gun": False},
            {"ad": "Okul tatili", "tur": "tatil", "bas": "2026-11-18", "bit": "2026-11-18"}]})  # fmt: skip
    yeni = kimlik(tahta_ekle(panel, tahta, "T-3", durum()))
    saat.ayarla(an(17, 9, 2))
    with vt.islem() as b:
        b.execute("UPDATE tahta SET son_gorulme = ?", (vt.simdi(),))
    assert calistir(uygulama, saat, an(17, 9, 3)) == []  # sınavda
    with vt.islem() as b:
        b.execute("UPDATE tahta SET son_gorulme = ?", (int(an(18, 9, 3).timestamp()),))
    assert calistir(uygulama, saat, an(18, 9, 3)) == []  # tatil
    with vt.islem() as b:
        b.execute("UPDATE tahta SET son_gorulme = ?", (int(an(19, 9, 3).timestamp()),))
    assert sorted(calistir(uygulama, saat, an(19, 9, 3))) == sorted([diger, yeni])  # muaf yine yok


# 21
def test_program_kilidi_idare_kilitli_tahtaya_verilmez(uygulama, panel, tahta, saat):
    hazirla(panel)
    t = kimlik(tahta_ekle(panel, tahta, "T-1", durum(kilitli=True, kilit_kaynak="idare")))
    assert calistir(uygulama, saat, an(16, 9, 3)) == []
    assert program_komutlari(t) == []
    assert sorgu("SELECT anahtar FROM program_isaret WHERE tahta_id = ?", t) == [{"anahtar": "2026-11-16|kilit|09:00"}]


# 22
def test_istisna_eklenince_program_kilitli_tahtaya_acma_gider(uygulama, panel, tahta, saat):
    hazirla(panel)
    saat.ayarla(an(16, 9, 4))
    b = tahta_ekle(panel, tahta, "T-1", durum(kilitli=True, kilit_kaynak="program", kilit_kalan=360))
    t = kimlik(b)
    assert panel.get("/api/durum").json()["tahtalar"][0]["program"]["acilis"] == "09:10"
    yanit = panel.post("/program/istisna", data={"sure": "bugun"})
    assert "durduruldu" in ileti(yanit)
    acma = program_komutlari(t, "kilit_ac")
    assert len(acma) == 1 and acma[0]["bitis"] - acma[0]["olusturma"] == 120
    ozet = panel.get("/api/durum").json()["program"]
    assert ozet["kilit"] == "durduruldu" and ozet["durduruldu_bitis"] == "23:59" and ozet["askida"] is True
    istisna = sorgu("SELECT * FROM program_istisna")[0]
    assert istisna["tahta_ids"] == "" and istisna["olusturan"] == "yonetici"
    panel.post(f"/program/istisna/{istisna['id']}/iptal", data={})
    assert sorgu("SELECT iptal FROM program_istisna")[0]["iptal"] is not None
    assert panel.get("/api/durum").json()["program"]["kilit"] == "acik"
    # geçersiz istisnalar
    assert "Bitiş" in ileti(panel.post("/program/istisna", data={"bas_tarih": "2026-11-17", "bit_tarih": "2026-11-16"}))
    assert "400" in ileti(panel.post("/program/istisna", data={"bas_tarih": "2026-11-17", "bit_tarih": "2028-11-16"}))
    assert "T.C." in ileti(panel.post("/program/istisna", data={"bas_tarih": "2026-11-17", "bit_tarih": "2026-11-17",
                                                              "neden": SAHTE_TC}))  # fmt: skip
    assert SAHTE_TC not in json.dumps(sorgu("SELECT * FROM kayit"))
    tamam = panel.post("/program/istisna", data={"bas_tarih": "2026-11-17", "bas_saat": "10:00", "bit_tarih": "2026-11-17",
                                                 "bit_saat": "12:00", "tahta": str(t), "neden": "Deneme sınavı"})  # fmt: skip
    assert "İstisna eklendi (1 tahta)" in ileti(tamam)  # ileri tarihli: "durduruldu" denmez
    assert sorgu("SELECT tahta_ids FROM program_istisna ORDER BY id DESC")[0]["tahta_ids"] == f"[{t}]"


# 23
def test_kural_kapaninca_acma_gider(uygulama, panel, tahta, saat):
    hazirla(panel)
    t = kimlik(tahta_ekle(panel, tahta, "T-1", durum(kilitli=True, kilit_kaynak="program", kilit_kalan=300)))
    calistir(uygulama, saat, an(16, 9, 3))  # tahta zaten program kilitli: komut (kilitle) yazılabilir
    panel.post("/program/kurallar", data={"pk_gecikme_dk": "2", "bd_esik_dk": "10"})
    assert len(program_komutlari(t, "kilit_ac")) == 1
    assert all(k["durum"] == "iptal" for k in program_komutlari(t, "kilitle"))  # bekleyen kilit düştü
    # zil verisi silinince kural kapanır (K30)
    hazirla_tekrar = panel.post("/program/kurallar", data={"pk_etkin": "1"})
    assert ileti(hazirla_tekrar) == "Kurallar kaydedildi."
    assert "kapatıldı" in ileti(panel.post("/program/zil/sil"))
    from tahta_sunucu import program, vt

    with vt.islem() as b:
        assert program.ayar_kilit(b)["etkin"] is False and program.ders_saatleri_oku(b) == []
    assert "önce zil" in ileti(panel.post("/program/kurallar", data={"pk_etkin": "1"}))


def test_acma_yedegi_aralik_disinda_bir_kez(uygulama, panel, tahta, saat):
    hazirla(panel)
    t = kimlik(tahta_ekle(panel, tahta, "T-1", durum()))
    saat.ayarla(an(16, 9, 30))  # ders saati: tahta hâlâ program kilidinde (saat kayması)
    from tahta_sunucu import vt

    with vt.islem() as b:
        b.execute("UPDATE tahta SET son_gorulme = ?, durum_json = ? WHERE id = ?",
                  (vt.simdi(), json.dumps(durum(kilitli=True, kilit_kaynak="program")), t))  # fmt: skip
    assert calistir(uygulama, saat, an(16, 9, 30, 20)) == [t]
    assert calistir(uygulama, saat, an(16, 9, 31)) == []
    assert len(program_komutlari(t, "kilit_ac")) == 1


def test_kilit_araligi_gecen_komut_tahtaya_inmez(uygulama, panel, tahta, saat):
    hazirla(panel)
    b = tahta_ekle(panel, tahta, "T-1", durum())
    from tahta_sunucu import vt

    calistir(uygulama, saat, an(16, 9, 2, 30))
    with vt.islem() as b_:  # ömrü içinde ama kilit aralığının sonuna 30 sn'den az kala inen komut
        b_.execute("UPDATE komut SET bitis = ?", (int(an(16, 9, 30).timestamp()),))
    saat.ayarla(an(16, 9, 9, 40))
    assert bekle(tahta, b, durum())["komutlar"] == []
    assert program_komutlari(kimlik(b), "kilitle")[0]["durum"] == "iptal"


# 24
def test_bos_ders_uyarisi_esikten_sonra_bir_kez(uygulama, panel, tahta, saat):

    hazirla(panel, kilit=False, bos=True)
    saat.ayarla(an(16, 8, 0))
    kapali = tahta_ekle(panel, tahta, "Kapalı", durum())
    idare = tahta_ekle(panel, tahta, "İdare", durum(kilitli=True, kilit_kaynak="idare"))
    programsiz = tahta_ekle(panel, tahta, "Programsız", durum(oturum={"sinif": "yok"}))
    for b in (kapali, idare):
        ders_isaretle(panel, kimlik(b), [1, 2])

    def tur(zaman, canli=(idare, programsiz)):
        saat.ayarla(zaman)
        for b in canli:
            bekle(tahta, b, durum(kilitli=True, kilit_kaynak="idare") if b is idare else durum(oturum={"sinif": "yok"}))
        calistir(uygulama, saat, zaman, canli=False)

    tur(an(16, 8, 21))
    tur(an(16, 8, 29))  # eşik (10 dk) dolmadı
    assert sorgu("SELECT * FROM bos_ders_uyari") == []
    tur(an(16, 8, 30, 30))
    tur(an(16, 8, 31))
    uyarilar = sorgu("SELECT * FROM bos_ders_uyari")
    assert [(u["tahta_id"], u["neden"], u["ders_no"]) for u in uyarilar] == [(kimlik(kapali), "kapali", 1)]
    ozet = panel.get("/api/durum").json()
    assert ozet["program"]["uyari_sayisi"] == 1
    kart = {t["ad"]: t for t in ozet["tahtalar"]}
    assert kart["Kapalı"]["program"]["bos_ders"] == "1. ders (kapalı)" and kart["İdare"]["program"]["bos_ders"] is None
    # tahta açılır: uyarı silinmez, çözülür
    saat.ayarla(an(16, 8, 40))
    bekle(tahta, kapali, durum())
    calistir(uygulama, saat, an(16, 8, 40), canli=False)
    assert sorgu("SELECT cozulme FROM bos_ders_uyari")[0]["cozulme"] == int(an(16, 8, 40).timestamp())
    sayfa = panel.get("/program/uyarilar")
    assert "08:40&#39;ta kullanılmaya başlandı" in sayfa.text or "08:40'ta kullanılmaya başlandı" in sayfa.text
    # görüldü (idareci de yapabilir); kayda tahta/ders yazılmaz
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    uyari_id = sorgu("SELECT id FROM bos_ders_uyari")[0]["id"]
    assert ileti(panel.post(f"/program/uyarilar/{uyari_id}/goruldu")) == "Görüldü olarak işaretlendi."
    assert sorgu("SELECT goruldu_kullanici FROM bos_ders_uyari")[0]["goruldu_kullanici"] == "idareci1"
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Boş ders uyarısı görüldü'")[0]["ayrinti"] == f"#{uyari_id}"
    # uyarının kendisi işlem kaydına yazılmaz (yalnız "görüldü" eylemi, kimlikle)
    assert [k["islem"] for k in sorgu("SELECT islem FROM kayit WHERE islem LIKE '%oş ders%'")] == ["Boş ders uyarısı görüldü"]


def test_bos_ders_sunucu_ders_ortasinda_baslarsa_uyari_yok(uygulama, panel, tahta, saat):
    hazirla(panel, kilit=False, bos=True)
    saat.ayarla(an(16, 8, 0))
    b = tahta_ekle(panel, tahta, "T-1", durum())
    ders_isaretle(panel, kimlik(b), [1])
    calistir(uygulama, saat, an(16, 8, 35), canli=False)  # ilk gözlem dersin 2. dakikasından sonra
    calistir(uygulama, saat, an(16, 8, 36), canli=False)
    assert sorgu("SELECT * FROM bos_ders_uyari") == []


# 26
def test_uyarilar_ogretim_yili_sonunda_silinir(uygulama, panel, tahta, saat):
    """K3: uyarılar 30 gün değil, öğretim yılı bitiş tarihi geçince (o tarihe kadar oluşanlar) silinir."""
    from tahta_sunucu import vt

    hazirla(panel, kilit=False, bos=True)
    t = kimlik(tahta_ekle(panel, tahta, "T-1", durum()))
    simdi = int(an(16, 3, 30).timestamp())
    with vt.islem() as b:
        for tarih in ("2026-06-20", "2026-07-01", "2026-10-02"):
            b.execute(
                "INSERT INTO bos_ders_uyari (tahta_id, tarih, devre, ders_no, ders_bas, neden, olusturma) "
                "VALUES (?, ?, 'normal', 1, ?, 'kapali', ?)",
                (t, tarih, simdi - 90 * 86400, simdi - 90 * 86400),
            )
        b.execute("INSERT INTO program_isaret VALUES (?, 'eski', ?)", (t, simdi - 3 * 86400))
    calistir(uygulama, saat, an(16, 3, 30))  # tarih girilmedi: hiçbiri silinmez (eskiden 30 günde silinirdi)
    assert len(sorgu("SELECT * FROM bos_ders_uyari")) == 3
    assert sorgu("SELECT * FROM program_isaret WHERE anahtar = 'eski'") == []
    with vt.islem() as b:
        vt.ayar_yaz(b, "ogretim_yili_bitis", "2026-06-26")
    calistir(uygulama, saat, an(16, 9, 0))  # bakım saatini beklemez
    assert [u["tarih"] for u in sorgu("SELECT tarih FROM bos_ders_uyari ORDER BY tarih")] == ["2026-07-01", "2026-10-02"]
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Boş ders uyarısı imhası'")[0]["ayrinti"] == (
        "1 uyarı (öğretim yılı bitişi 26.06.2026)"
    )
    calistir(uygulama, saat, an(16, 9, 1))
    assert len(sorgu("SELECT * FROM kayit WHERE islem = 'Boş ders uyarısı imhası'")) == 1  # silinecek yoksa yazmaz


# 28
def test_api_durum_program_alanlari(uygulama, panel, tahta, saat):
    kur_ve_gir(panel)
    ozet = panel.get("/api/durum").json()["program"]
    assert ozet["simdi"] == "Ders saatleri tanımlı değil" and ozet["kilit"] == "kapali" and not ozet["ders_saati_var"]
    zil_elle(ELLE)
    saat.ayarla(an(16, 9, 20))
    tahta_ekle(panel, tahta, "T-1", durum())
    yanit = panel.get("/api/durum").json()
    assert yanit["program"]["bugun"] == "Pazartesi, 16.11.2026"
    assert yanit["program"]["simdi"] == "2. ders · 09:10–09:50" and yanit["program"]["simdi_tur"] == "ders"
    assert yanit["tahtalar"][0]["program"] == {"kilit_kaynak": None, "acilis": None, "neden": None, "muaf": False,
                                               "bos_ders": None, "program_yetenegi": True}  # fmt: skip
    saat.ayarla(an(16, 11, 40))
    assert panel.get("/api/durum").json()["program"]["simdi"] == "Öğle arası · 11:30–12:15"
    saat.ayarla(an(16, 18))
    assert panel.get("/api/durum").json()["program"]["simdi"] == "Ders dışı"
    from tahta_sunucu import program_is, vt

    with vt.islem() as b:  # cumartesi (oturum çerezi 12 saatte biter; özet doğrudan)
        assert program_is.program_ozeti(b, an(21, 10))["simdi"] == "Bugün ders yok"
    assert "Program" in panel.get("/").text  # menüde


# 13
def test_onizleme_baska_kullanici_ya_da_suresi_gecmis_onaylanamaz(uygulama, panel, saat):
    from tahta_sunucu import vt

    kur_ve_gir(panel)
    kullanici_ekle(panel, "yonetici2", "yonetici")
    yanit = panel.post("/program/zil/yukle", files={"dosya": ("ayarlar.json", ORNEK.read_bytes(), "application/json")})
    assert yanit.headers["location"] == "/program?bolum=zil&onizleme=1"
    sayfa = panel.get("/program?bolum=zil&onizleme=1").text
    assert "Onayla ve kaydet" in sayfa and "Cumartesi tanımlı değil" in sayfa
    with vt.islem() as b:
        kimlik_ = vt.ayar_al(b, "program_onizleme")["kimlik"]
    assert kimlik_ in sayfa
    gir(panel, "yonetici2")
    assert "başka bir kullanıcıya" in ileti(panel.post("/program/zil/onayla", data={"onizleme": kimlik_}))
    gir(panel, "yonetici")
    assert "başka" in ileti(panel.post("/program/zil/onayla", data={"onizleme": "yanlis"}))
    saat.ilerlet(31 * 60)
    assert "süresi geçmiş" in ileti(panel.post("/program/zil/onayla", data={"onizleme": kimlik_}))
    saat.ilerlet(-31 * 60)
    panel.post("/program/zil/yukle", files={"dosya": ("ayarlar.json", ORNEK.read_bytes(), "application/json")})
    with vt.islem() as b:
        kimlik_ = vt.ayar_al(b, "program_onizleme")["kimlik"]
    assert ileti(panel.post("/program/zil/onayla", data={"onizleme": kimlik_})).startswith("Zil saatleri kaydedildi.")
    with vt.islem() as b:
        assert len(b.execute("SELECT * FROM ders_saati").fetchall()) == 3
        kaynak = vt.ayar_al(b, "zil_kaynagi")
        assert kaynak["tur"] == "okulzili" and kaynak["yukleyen"] == "yonetici" and vt.ayar_al(b, "program_onizleme") is None
        assert vt.ayar_al(b, "zil_takvimi")["kurallar"][0]["tur"] == "kisaltilmis_gun"
    sayfa = panel.get("/program").text
    assert "Okul Zili&#39;nden alındı" in sayfa or "Okul Zili'nden alındı" in sayfa
    assert "Öğretim yılı: 07.09.2026–25.06.2027" in sayfa
    # hatalı dosya: önizleme açılmaz
    assert "desteklenmiyor" in ileti(panel.post("/program/zil/yukle", files={"dosya": ("ayarlar.json", b'{"schema_version": 9}', "application/json")}))
    assert "seçin" in ileti(panel.post("/program/zil/yukle", files={"dosya": ("x.txt", b"x", "text/plain")}))


def test_yerel_okul_zili_salt_okunur_ve_sabit_yoldan(uygulama, panel, tmp_path, monkeypatch):
    dizin = tmp_path / "okulzili-veri"
    dizin.mkdir()
    (dizin / "ayarlar.json").write_bytes(ORNEK.read_bytes())
    monkeypatch.setenv("OKUL_ZILI_DATA_DIR", str(dizin))
    kur_ve_gir(panel)
    assert "Bu bilgisayardaki Okul Zili" in panel.get("/program").text
    assert panel.post("/program/zil/yerel", data={"yol": "C:/baska"}).headers["location"].endswith("onizleme=1")
    from tahta_sunucu import vt

    with vt.islem() as b:
        kayit = vt.ayar_al(b, "program_onizleme")
    assert kayit["veri"]["kaynak"]["dosya_yolu"] == str((dizin / "ayarlar.json").resolve())
    panel.post("/program/zil/onayla", data={"onizleme": kayit["kimlik"]})
    assert "değişmiş görünüyor" not in panel.get("/program").text
    import os

    (dizin / "ayarlar.json").write_bytes(ORNEK.read_bytes().replace(b"08:20:00", b"08:25:00"))
    os.utime(dizin / "ayarlar.json", (1, 1))
    assert "değişmiş görünüyor" in panel.get("/program").text


# 14
def test_idareci_zil_ve_kural_degistiremez_istisna_ekleyebilir(uygulama, panel, tahta, saat):
    hazirla(panel)
    t = kimlik(tahta_ekle(panel, tahta, "T-1", durum()))
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    for yol, veri in (
        ("/program/haftalik", {"gun_0": ""}),
        ("/program/cizelge", {"ad": "X"}),
        ("/program/tarihli", {"ad": "X"}),
        ("/program/aktar/esle", {"onizleme": "x"}),
        ("/program/aktar/onayla", {"onizleme": "x"}),
        ("/program/zil/sil", {}),
        ("/program/kurallar", {"pk_etkin": "1"}),
        ("/program/derslik/onayla", {"onizleme": "x"}),
        ("/program/derslik/yetim-temizle", {}),
        (f"/tahta/{t}/program", {"program_muaf": "1"}),
        ("/program/zil/onayla", {"onizleme": "x"}),
        ("/program/zil/yerel", {}),
    ):
        assert "yönetici yetkisi" in ileti(panel.post(yol, data=veri)), yol
    assert "yönetici yetkisi" in ileti(panel.post("/program/zil/yukle", files={"dosya": ("a.json", b"{}", "application/json")}))
    assert "yönetici yetkisi" in ileti(panel.post("/program/derslik/yukle", files={"dosya": ("a.csv", b"x", "text/csv")}))
    assert len(sorgu("SELECT * FROM kayit WHERE islem = 'Yetkisiz işlem reddedildi'")) == 14
    assert "durduruldu" in ileti(panel.post("/program/istisna", data={"sure": "1sa", "donus": "/"}))
    assert panel.post("/program/istisna", data={"sure": "1sa", "donus": "//kotu.example"}).headers["location"].startswith("/program")
    sayfa = panel.get("/program").text
    assert 'action="/program/zil/yukle"' not in sayfa and 'data-onay="zil_sil"' not in sayfa
    sayfa = panel.get("/program?bolum=istisnalar").text
    assert 'action="/program/istisna"' in sayfa
    assert panel.get("/program/uyarilar").status_code == 200


def test_derslik_csv_yukleme_onizleme_ve_onay(uygulama, panel, tahta, saat):
    hazirla(panel, kilit=False)
    t1 = kimlik(tahta_ekle(panel, tahta, "T-1", durum()))
    t2 = kimlik(tahta_ekle(panel, tahta, "T-2", durum()))
    panel.post(f"/tahta/{t1}/kaydet", data={"ad": "T-1", "derslik": "Z-04", "eylem": "kaydet"})
    ders_isaretle(panel, t2, [1, 2, 3])  # dosyada geçmeyen tahtaya dokunulmaz
    ornek = panel.get("/program/aktar/sablon.csv")  # 0.10.0: içe aktarma sihirbazı
    assert ornek.status_code == 200 and ornek.content.startswith(b"\xef\xbb\xbfsube;gun;ders;devre;derslik")
    assert panel.get("/program/derslik/ornek.csv").status_code == 200  # eski örnek bağlantısı kalır
    csv = "derslik;gun;ders;sube;ogretmen\nZ-04;Pazartesi;1-4;9/A;Uydurma Ad\nZ-04;Salı;2;;\nYok;Pzt;1;;\n"
    eski = panel.post("/program/derslik/yukle", files={"dosya": ("p.csv", csv.encode("utf-8"), "text/csv")})
    assert eski.headers["location"].startswith("/program/aktar?")  # eski uç sihirbaza yönlendirir
    yanit = panel.post("/program/aktar/tablo", files={"dosya": ("p.csv", csv.encode("utf-8"), "text/csv")})
    assert yanit.headers["location"] == "/program/aktar?adim=esleme"  # "Yok" dersliği eşleşmedi
    sayfa = panel.get(yanit.headers["location"]).text
    assert "Yok" in sayfa and "Uydurma" not in sayfa
    from tahta_sunucu import vt

    with vt.islem() as b:
        kimlik_ = vt.ayar_al(b, "program_onizleme")["kimlik"]
    assert "1 tahtanın programı güncellendi" in ileti(panel.post("/program/aktar/onayla", data={"onizleme": kimlik_}))
    assert len(sorgu("SELECT * FROM tahta_ders WHERE tahta_id = ?", t1)) == 5
    assert sorgu("SELECT sube FROM tahta_ders WHERE tahta_id = ? AND ders_no = 1", t1)[0]["sube"] == "9/A"
    assert len(sorgu("SELECT * FROM tahta_ders WHERE tahta_id = ?", t2)) == 3
    assert "Uydurma" not in json.dumps(sorgu("SELECT * FROM kayit"), ensure_ascii=False)
    # tahta sayfası ızgarası ve yetimler (K6)
    sayfa = panel.get(f"/tahta/{t1}?sekme=program").text
    assert 'name="d_0_normal_1" value="1" checked' in sayfa and 'name="sube_0_normal_1" value="9/A"' in sayfa
    with vt.islem() as b:
        b.execute("DELETE FROM ders_saati WHERE ders_no = 8")
        b.execute("INSERT INTO tahta_ders VALUES (?, 0, 'normal', 8, '')", (t1,))
    assert "1 tahtada artık olmayan" in panel.get("/program?bolum=derslik").text
    assert "1 satır" in ileti(panel.post("/program/derslik/yetim-temizle"))
    # tahta kaldırılınca programı da silinir (K34)
    panel.post(f"/tahta/{t1}/kaydet", data={"ad": "T-1", "eylem": "sil"})
    assert sorgu("SELECT * FROM tahta_ders WHERE tahta_id = ?", t1) == []


def test_tahta_programi_kaydi_ve_muaf_acmasi(uygulama, panel, tahta, saat):
    hazirla(panel)
    t = kimlik(tahta_ekle(panel, tahta, "T-1", durum(kilitli=True, kilit_kaynak="program", kilit_kalan=100)))
    assert "anlaşılamadı" in ileti(panel.post(f"/tahta/{t}/program", data={"d_0_normal_1": "1", "sube_0_normal_1": "zz"}))
    ders_isaretle(panel, t, [1, 2], sube_0_normal_2="10-c")
    assert [(s["ders_no"], s["sube"]) for s in sorgu("SELECT * FROM tahta_ders ORDER BY ders_no")] == [(1, ""), (2, "10/C")]
    ders_isaretle(panel, t, [1], program_muaf="1")
    assert len(program_komutlari(t, "kilit_ac")) == 1
    assert sorgu("SELECT program_muaf FROM tahta WHERE id = ?", t)[0]["program_muaf"] == 1
    assert "Muaf" in panel.get(f"/tahta/{t}").text


# 29
def test_goc_mevcut_veritabanina_uygulanir(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    from tahta_sunucu import vt

    yol = tmp_path / "tahta-kontrol.db"
    b = sqlite3.connect(yol)
    b.executescript(vt.GOCLER[0])
    b.executescript(vt.GOCLER[1])
    b.execute("PRAGMA user_version = 2")
    b.execute("INSERT INTO tahta (ad, anahtar_ozet, kayit_zamani, durum) VALUES ('Eski tahta', 'x', 1, 'onayli')")
    b.commit()
    b.close()
    vt.hazirla()
    with vt.islem() as b:
        assert b.execute("PRAGMA user_version").fetchone()[0] == len(vt.GOCLER) >= 3
        satir = b.execute("SELECT * FROM tahta").fetchone()
        assert satir["ad"] == "Eski tahta" and satir["program_muaf"] == 0
        for tablo in ("ders_saati", "tahta_ders", "program_istisna", "program_isaret", "bos_ders_uyari"):
            assert b.execute(f"SELECT COUNT(*) FROM {tablo}").fetchone()[0] == 0
    assert len(list((tmp_path / "goc-oncesi").glob("tahta-kontrol-v2-*.db"))) == 1
