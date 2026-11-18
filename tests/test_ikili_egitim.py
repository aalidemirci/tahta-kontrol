"""İkili eğitim (16.11.2026 kararı K1) ve ders saati bazında icmal (K2): uçtan uca senaryolar.

Okulda sabahçı ve öğlenci devre vardır; zil çizelgeleri ayrıdır ve aynı tahtada sabah 9/A, öğle 11/C ders
görür. Saat `saat` fikstürüyle sabittir (pazartesi 16.11.2026). Bütün veriler UYDURMADIR.

Zil çizelgesi (her iki devrede 6 ders, 40 dk ders, 10 dk teneffüs):
  Sabah:          1 07:30–08:10 · 2 08:20–09:00 · 3 09:10–09:50 · 4 10:00–10:40 · 5 10:50–11:30 · 6 11:40–12:20
  Öğleden sonra:  1 13:00–13:40 · 2 13:50–14:30 · 3 14:40–15:20 · 4 15:30–16:10 · 5 16:20–17:00 · 6 17:10–17:50
Tahtalar: Z-04 sabah 1–6 9/A, öğle 1–6 11/C · Z-05 yalnız sabah 1–3 10/B · Z-06 programsız, şubeleri "9/A,11/C".
"""

from __future__ import annotations

import json
import re

import pytest
from yardimci import an, bekle, ileti, kimlik, kur_ve_gir, sorgu, tahta_ekle, zil_elle

from tahta_sunucu import vt
from tahta_sunucu import yoklama as yk

YETENEKLER = ["acil", "duyuru_id", "program_kilidi", "yoklama"]
GUNLER = ["0", "1", "2", "3", "4"]
SABAH = {"eylem": "uret", "devre_adi": "Sabah", "ilk_ders": "07:30", "ders_sayisi": "6", "ders_dk": "40",
         "teneffus_dk": "10", "ogle_sonra": "0", "ogle_dk": "0", "gunler": GUNLER}  # fmt: skip
OGLE = {**SABAH, "devre_adi": "Öğleden sonra", "ilk_ders": "13:00"}
OGRENCILER = (
    "Sınıf/Şube;Okul No;Adı;Soyadı\n9/A;901;Ali;ÖRNEK\n9/A;902;Banu;DENEME\n11/C;1101;Can;UYDURMA\n"
    "11/C;1102;Dila;SAHTE\n10/B;1001;Ece;FARAZİ\n"
).encode()


def durum(**ek) -> dict:
    return {"kilitli": False, "yetenekler": YETENEKLER, "ekranlar": [{"arayuz": "gtk3"}], "oturum": {"sinif": "ogretmen"}, **ek}


def program_formu(dersler: dict[str, tuple[range, str]]) -> dict:
    form = {}
    for devre, (nolar, sube) in dersler.items():
        for n in nolar:
            form[f"d_0_{devre}_{n}"] = "1"
            form[f"sube_0_{devre}_{n}"] = sube
    return form


@pytest.fixture()
def okul(panel, tahta, saat):
    kur_ve_gir(panel)
    assert zil_elle(SABAH) == "Zil saatleri kaydedildi."
    assert zil_elle(OGLE) == "Zil saatleri kaydedildi."
    form = {"pk_etkin": "1", "pk_gecikme_dk": "2", "pk_bos_saatte": "1", "bd_etkin": "1", "bd_esik_dk": "10"}
    assert ileti(panel.post("/program/kurallar", data=form)) == "Kurallar kaydedildi."
    saat.ayarla(an(16, 7, 0))
    z04 = tahta_ekle(panel, tahta, "Z-04", durum())
    z05 = tahta_ekle(panel, tahta, "Z-05", durum())
    z06 = tahta_ekle(panel, tahta, "Z-06", durum(), subeler="9/A,11/C")
    form = program_formu({"sabah": (range(1, 7), "9/A"), "ogle": (range(1, 7), "11/C")})
    assert ileti(panel.post(f"/tahta/{kimlik(z04)}/program", data=form)) == "Program kaydedildi."
    form = program_formu({"sabah": (range(1, 4), "10/B")})
    assert ileti(panel.post(f"/tahta/{kimlik(z05)}/program", data=form)) == "Program kaydedildi."
    return {"z04": z04, "z05": z05, "z06": z06}


def calistir(uygulama, saat, zaman, canli=True) -> list[int]:
    saat.ayarla(zaman)
    if canli:
        with vt.islem() as b:
            b.execute("UPDATE tahta SET son_gorulme = ?", (vt.simdi(),))
    return uygulama.state.program_zamanlayici(zaman)


def kilitler(tahta_id: int) -> list[dict]:
    return [json.loads(s["veri_json"]) for s in sorgu("SELECT * FROM komut WHERE tahta_id = ? AND tur = 'kilitle' ORDER BY id", tahta_id)]


# ---- zil çizelgesi ve şerit ----------------------------------------------------------------------
def test_iki_devre_ayri_zil_cizelgesiyle_kaydedilir_ve_serit_devreyi_yazar(panel, okul, saat):
    satirlar = sorgu("SELECT devre, devre_adi, ders_no, baslangic, bitis FROM ders_saati WHERE gun = 0 ORDER BY baslangic")
    assert {s["devre"] for s in satirlar} == {"sabah", "ogle"} and len(satirlar) == 12
    assert (satirlar[0]["devre"], satirlar[0]["baslangic"]) == ("sabah", "07:30")
    assert (satirlar[6]["devre"], satirlar[6]["ders_no"], satirlar[6]["baslangic"]) == ("ogle", 1, "13:00")
    saat.ayarla(an(16, 9, 20))
    assert panel.get("/api/durum").json()["program"]["simdi"] == "Sabah · 3. ders · 09:10–09:50"
    saat.ayarla(an(16, 12, 40))
    assert panel.get("/api/durum").json()["program"]["simdi"] == "Öğle arası · 12:20–13:00"
    saat.ayarla(an(16, 14, 0))
    assert panel.get("/api/durum").json()["program"]["simdi"] == "Öğleden sonra · 2. ders · 13:50–14:30"


# ---- program kilidi ------------------------------------------------------------------------------
def test_program_kilidi_her_devrenin_kendi_teneffusunu_ve_ogle_arasini_kullanir(uygulama, okul, saat):
    z04, z05 = kimlik(okul["z04"]), kimlik(okul["z05"])
    calistir(uygulama, saat, an(16, 8, 12))  # sabah 1–2 arası teneffüs
    assert [(k["neden"], k["acilis"]) for k in kilitler(z04)] == [("Teneffüs", "08:20")]
    calistir(uygulama, saat, an(16, 12, 22))  # devre geçişi: sabahın son dersi bitti, öğlenin ilki 13:00
    assert [(k["neden"], k["acilis"]) for k in kilitler(z04)][-1] == ("Öğle arası", "13:00")
    calistir(uygulama, saat, an(16, 13, 42))  # öğle devresinin teneffüsü
    assert [(k["neden"], k["acilis"]) for k in kilitler(z04)][-1] == ("Teneffüs", "13:50")
    calistir(uygulama, saat, an(16, 14, 2))  # öğle 2. dersi sürüyor: yeni kilit yok
    assert len(kilitler(z04)) == 3
    # Yalnız sabah 1–3'te dersi olan tahta: 3. dersten sonra gün sonuna kadar "ders yok" (öğle devresi dahil).
    z05_kilit = kilitler(z05)
    assert ("Teneffüs", "08:20") in [(k["neden"], k["acilis"]) for k in z05_kilit]
    calistir(uygulama, saat, an(16, 9, 52))
    assert (kilitler(z05)[-1]["neden"], kilitler(z05)[-1]["acilis"]) == ("Bu saatte bu derslikte ders yok", "17:50")


def test_bos_saatte_kilit_kapaliyken_iki_devrenin_teneffusleri_kilitlenir(uygulama, panel, okul, saat):
    form = {"pk_etkin": "1", "pk_gecikme_dk": "2", "bd_esik_dk": "10"}  # bos_saatte kapalı
    assert ileti(panel.post("/program/kurallar", data=form)) == "Kurallar kaydedildi."
    z05 = kimlik(okul["z05"])
    calistir(uygulama, saat, an(16, 9, 52))  # Z-05'in dersi bitti ama devre sürüyor: teneffüs kadar kilit
    assert (kilitler(z05)[-1]["neden"], kilitler(z05)[-1]["acilis"]) == ("Teneffüs", "10:00")
    calistir(uygulama, saat, an(16, 13, 42))
    assert (kilitler(z05)[-1]["neden"], kilitler(z05)[-1]["acilis"]) == ("Teneffüs", "13:50")


# ---- boş ders uyarısı --------------------------------------------------------------------------------
def test_bos_ders_uyarisi_dogru_devrenin_dersine_bakar(uygulama, panel, okul, saat):
    z04 = kimlik(okul["z04"])
    calistir(uygulama, saat, an(16, 13, 1), canli=False)  # bütün tahtalar kapalı (çevrimdışı)
    calistir(uygulama, saat, an(16, 13, 12), canli=False)
    uyarilar = sorgu("SELECT tahta_id, devre, ders_no FROM bos_ders_uyari")
    assert uyarilar == [{"tahta_id": z04, "devre": "ogle", "ders_no": 1}]  # Z-05'in öğlede dersi yok
    sayfa = panel.get("/program/uyarilar").text
    assert "Öğleden sonra · 1. ders · 11/C" in sayfa


# ---- yoklama önerisi --------------------------------------------------------------------------------
@pytest.fixture()
def yoklamali(panel, okul):
    form = {"bolum": "yoklama", "yk_etkin": "1", "yk_maske": "ad_soyadbas", "yk_oturum_dk": "8", "yk_bosta_dk": "3"}
    assert "t=hata" not in panel.post("/ayarlar", data=form).headers["location"]
    yanit = panel.post("/ogrenciler/onizle", files={"dosya": ("liste.csv", OGRENCILER, "text/csv")})
    belirtec = re.search(r'name="onizleme" value="([^"]+)"', yanit.text).group(1)
    assert "t=hata" not in panel.post("/ogrenciler/aktar", data={"onizleme": belirtec}).headers["location"]
    return okul


def oneri(tahta, basliklar, sube=None) -> dict:
    return tahta.post("/ajan/yoklama/oneri", headers=basliklar, json={"sube": sube} if sube else {}).json()


@pytest.mark.parametrize(
    ("saat_", "sube", "ders_no", "ilk_baslangic"),
    [
        ((9, 20), "9/A", 3, "07:30"),     # sabah 3. ders sürüyor
        ((12, 30), "9/A", 6, "07:30"),    # öğle arası: 15 dk içinde biten sabah 6. dersi
        ((12, 57), "11/C", 1, "13:00"),   # öğle 1. dersi 5 dk içinde başlıyor
        ((13, 45), "11/C", 2, "13:00"),   # öğle teneffüsü: başlamak üzere olan 2. ders
        ((14, 0), "11/C", 2, "13:00"),    # öğle 2. ders sürüyor (sabahın 2. dersiyle karışmaz)
    ],
)
def test_yoklama_onerisi_saate_gore_dogru_devrenin_subesini_ve_dersini_secer(tahta, yoklamali, saat, saat_, sube, ders_no,
                                                                                ilk_baslangic):  # fmt: skip
    saat.ayarla(an(16, *saat_))
    veri = oneri(tahta, yoklamali["z04"])
    # 0.14.0: yoklama_gec bildirmeyen eski ajana "biten ders" önerilmez (şube önerisi kalır, ders seçilmez).
    eski_ajan_dersi = None if saat_ == (12, 30) else ders_no
    assert (veri["oneri"]["sube"], veri["oneri"]["ders_no"]) == (sube, eski_ajan_dersi)
    bekle(tahta, yoklamali["z04"], durum(yetenekler=[*YETENEKLER, "yoklama_gec"]), surum="0.14.0")
    yeni = oneri(tahta, yoklamali["z04"])["oneri"]
    # Yetenekli ajan: teneffüste biten ve başlayacak ders birlikte tutuyorsa ders seçilmez, iki aday döner.
    beklenen = (sube, None, [1, 2]) if saat_ == (13, 45) else (sube, ders_no, [])
    assert (yeni["sube"], yeni["ders_no"], yeni["ders_adaylari"]) == beklenen
    assert veri["ders_saatleri"][0]["baslangic"] == ilk_baslangic and len(veri["ders_saatleri"]) == 6


def test_programsiz_iki_subeli_tahtada_devresi_suren_sube_onerilir(tahta, yoklamali, saat):
    saat.ayarla(an(16, 9, 20))
    assert oneri(tahta, yoklamali["z06"])["oneri"] == {"sube": "9/A", "ders_no": 3, "ders_adi": "", "ogretmen": None,
                                                       "ders_adaylari": []}  # fmt: skip
    saat.ayarla(an(16, 15, 0))
    assert oneri(tahta, yoklamali["z06"])["oneri"]["sube"] == "11/C"
    saat.ayarla(an(16, 20, 0))  # iki devre de bitti: öneri yok, öğretmen seçer
    assert oneri(tahta, yoklamali["z06"])["oneri"]["sube"] is None


def test_sube_degisince_ders_saatleri_ve_ders_no_o_subenin_devresinden(tahta, yoklamali, saat):
    saat.ayarla(an(16, 9, 20))
    veri = oneri(tahta, yoklamali["z04"], "11/C")
    assert veri["ders_saatleri"][0]["baslangic"] == "13:00"
    assert [d["secilebilir"] for d in veri["ders_saatleri"]] == [False] * 6  # öğle dersleri henüz başlamadı
    assert veri["oneri"]["ders_no"] is None
    veri = oneri(tahta, yoklamali["z04"], "10/B")
    assert veri["ders_saatleri"][0]["baslangic"] == "07:30" and veri["oneri"]["ders_no"] == 3


# ---- K2: ders saati bazında icmal, devreler karışmaz ---------------------------------------------------
def test_icmal_ders_saati_bazinda_ve_devreler_karismaz(panel, yoklamali, saat):
    saat.ayarla(an(16, 14, 0))
    ali = sorgu("SELECT id FROM ogrenci WHERE okul_no = '901'")[0]["id"]
    can = sorgu("SELECT id FROM ogrenci WHERE okul_no = '1101'")[0]["id"]
    for sube, no, yok in (("9/A", 3, ali), ("11/C", 1, can)):
        yanit = panel.post("/yoklama/gir", data={"tarih": "2026-11-16", "sube": sube, "ders_no": str(no), "yok": [str(yok)]})
        assert "t=hata" not in yanit.headers["location"], ileti(yanit)
    # 11/C'nin 3. dersi (14:40) henüz başlamadı: sabahın 3. dersi geçmiş olsa da reddedilir.
    yanit = panel.post("/yoklama/gir", data={"tarih": "2026-11-16", "sube": "11/C", "ders_no": "3"})
    assert ileti(yanit) == yk.ILETI_GELECEK
    with vt.islem() as b:
        g = yk.gunluk_gorunum(b, yk.bugun(), vt.simdi())
        satir = {s["sube"]: s for s in g["satirlar"]}
        assert (satir["9/A"]["devre_adi"], satir["11/C"]["devre_adi"]) == ("Sabah", "Öğleden sonra")
        # 9/A sabah 1. dersi bitti, alınmadı; 11/C'nin 1. dersi alındı, 2. dersi sürüyor (alınmadı değil).
        assert satir["9/A"]["hucreler"][0]["durum"] == "alinmadi" and satir["9/A"]["hucreler"][2]["durum"] == "alindi"
        assert satir["11/C"]["hucreler"][0]["durum"] == "alindi" and satir["11/C"]["hucreler"][1]["durum"] == "bos"
        assert satir["11/C"]["hucreler"][0]["baslik"].startswith("13:00–13:40")
        assert satir["9/A"]["hucreler"][0]["baslik"].startswith("07:30–08:10")
        icmal = {s["sube"]: s for s in yk.icmal(b, yk.bugun())["subeler"]}
    assert icmal["9/A"]["ogrenciler"][0]["saatler"] == [3] and icmal["11/C"]["ogrenciler"][0]["saatler"] == [1]
    assert icmal["11/C"]["devre_adi"] == "Öğleden sonra" and icmal["11/C"]["sutun_sayisi"] == 6
    metin = panel.get("/yoklama/icmal?tarih=2026-11-16").text
    assert "Öğleden sonra" in metin and "9/A · Sabah (yoklama alınan: 3" in metin


# ---- duyuru hedefi: devre ------------------------------------------------------------------------------
def test_duyuru_devre_suzgeci_programdan_turetilir_ve_alan_onceliklidir(panel, okul):
    from tahta_sunucu import hedef, panel_duyuru

    z04, z05, z06 = (kimlik(okul[a]) for a in ("z04", "z05", "z06"))
    with vt.islem() as b:
        assert {t["id"] for t in hedef.coz(b, {"devre": ["sabah"]})} == {z04, z05}
        assert {t["id"] for t in hedef.coz(b, {"devre": ["ogle"]})} == {z04}
        assert [d for d, _ in panel_duyuru.secenekler(b)["devreler"]] == ["sabah", "ogle"]
        b.execute("UPDATE tahta SET devre = 'ogle' WHERE id = ?", (z06,))  # elle atanan alan geçerli
        b.execute("UPDATE tahta SET devre = 'ogle' WHERE id = ?", (z05,))  # program sabah dese de alan kazanır
        assert {t["id"] for t in hedef.coz(b, {"devre": ["ogle"]})} == {z04, z05, z06}
    sayfa = panel.get("/duyurular/yeni").text
    assert 'name="devre" value="sabah"' in sayfa and 'name="devre" value="ogle"' in sayfa


def test_tek_devreli_okulda_devre_turetilmez(panel, tahta, saat):
    from tahta_sunucu import program

    kur_ve_gir(panel)
    zil_elle({**SABAH, "devre_adi": "Normal"})
    with vt.islem() as b:
        assert program.devre_turleri(program.ders_saatleri_oku(b)) == {}
        assert program.tahta_devreleri(b) == {}


def test_devre_adlari_tanimsizsa_erken_baslayan_sabah_sayilir():
    from tahta_sunucu import program

    saatler = [(0, "s2", "2. devre", 1, "12:40", "13:20"), (0, "s1", "1. devre", 1, "07:20", "08:00")]
    assert program.devre_turleri(saatler) == {"s1": "sabah", "s2": "ogle"}
    saatler = [(0, "ogle", "Öğle", 1, "12:40", "13:20"), (0, "sabah", "Sabah", 1, "07:20", "08:00"),
               (0, "aksam", "Akşam", 1, "18:00", "18:40")]  # fmt: skip
    assert program.devre_turleri(saatler) == {"sabah": "sabah", "ogle": "ogle"}


# ---- sınav şube duyurusu -------------------------------------------------------------------------------
def test_sinav_sube_duyurusu_subeler_alani_yoksa_programdaki_tahtaya_gider(okul, saat):
    from tahta_sunucu import sinav

    z04, z05 = kimlik(okul["z04"]), kimlik(okul["z05"])
    an_ = vt.simdi()
    with vt.islem() as b:
        sinav_id = b.execute(
            "INSERT INTO sinav (ad, baslangic, durum, olusturan, olusturma, guncelleme) VALUES ('Deneme', ?, 'yayinda', 'y', ?, ?)",
            (an_ + 86400, an_, an_),
        ).lastrowid
        ders = b.execute("INSERT INTO sinav_ders (sinav_id, ad, sure_dk) VALUES (?, 'Matematik', 40)", (sinav_id,)).lastrowid
        salon = b.execute("INSERT INTO sinav_salon (sinav_id, ad, gozetmen_kodu) VALUES (?, 'Salon 1', '1234')", (sinav_id,)).lastrowid
        for koltuk, (no, sube) in enumerate((("901", "9/A"), ("1101", "11/C"), ("1001", "10/B"), ("1201", "12/D")), 1):
            b.execute(
                "INSERT INTO sinav_ogrenci (sinav_id, salon_id, ders_id, koltuk, okul_no, sube, maske) VALUES (?, ?, ?, ?, ?, ?, 'Ah*')",
                (sinav_id, salon, ders, koltuk, no, sube),
            )
        satir = b.execute("SELECT * FROM sinav WHERE id = ?", (sinav_id,)).fetchone()
        gonderilen, tahtasiz, _ = sinav.sube_duyurusu(b, satir, 10, "yonetici", an_)
    assert (gonderilen, tahtasiz) == (3, 1)  # 12/D'nin ne alanı ne programı var
    hedefler = {s["metin"]: json.loads(s["hedef_json"]) for s in sorgu("SELECT metin, hedef_json FROM duyuru")}
    # Z-06'nın subeler alanı 9/A ve 11/C'yi taşır; alan varken program kullanılmaz.
    assert hedefler["Sınav oturma listesi · 9/A"]["tahtalar"] == [kimlik(okul["z06"])]
    assert hedefler["Sınav oturma listesi · 10/B"]["tahtalar"] == [z05]
    assert z04 not in hedefler["Sınav oturma listesi · 10/B"]["tahtalar"]


def test_bos_ders_raporu_uyarinin_olustugu_andaki_subeyi_yazar(uygulama, panel, okul, saat):
    """Uyarı yıl sonuna kadar saklanır (K3/K6): sonradan değişen program eski uyarıyı başka şubeye yazmaz."""
    z04 = kimlik(okul["z04"])
    for z in (an(16, 9, 11), an(16, 9, 22)):  # sabah 3. ders, bütün tahtalar kapalı
        calistir(uygulama, saat, z, canli=False)
    assert sorgu("SELECT sube FROM bos_ders_uyari WHERE tahta_id = ?", z04) == [{"sube": "9/A"}]
    form = program_formu({"sabah": (range(1, 7), "9/B"), "ogle": (range(1, 7), "11/C")})
    assert ileti(panel.post(f"/tahta/{z04}/program", data=form)) == "Program kaydedildi."
    sayfa = panel.get(f"/program/uyarilar?tahta={z04}").text
    assert "Sabah · 3. ders · 9/A" in sayfa and "9/B" not in sayfa
    # 0.8.0 öncesi satır (şube saklanmamış): güncel programdan bulunur ve bu açıkça yazılır.
    with vt.islem() as b:
        b.execute("UPDATE bos_ders_uyari SET sube = NULL")
    assert "Sabah · 3. ders · 9/B (güncel programa göre)" in panel.get(f"/program/uyarilar?tahta={z04}").text


def test_bos_ders_raporu_ders_suzgeci_devreleri_karistirmaz(uygulama, panel, okul, saat):
    for z in (an(16, 9, 11), an(16, 9, 22), an(16, 14, 41), an(16, 14, 52)):  # sabah ve öğle 3. ders
        calistir(uygulama, saat, z, canli=False)
    assert len(sorgu("SELECT * FROM bos_ders_uyari WHERE ders_no = 3")) == 3
    sayfa = panel.get("/program/uyarilar").text
    assert '<option value="sabah-3" >Sabah · 3. ders</option>' in sayfa
    assert '<option value="ogle-3" >Öğleden sonra · 3. ders</option>' in sayfa
    sayfa = panel.get("/program/uyarilar?ders=sabah-3").text
    assert sayfa.count('/goruldu"') == 2 and "Öğleden sonra · 3. ders · 11/C" not in sayfa
    assert '<option value="sabah-3" selected>' in sayfa
    sayfa = panel.get("/program/uyarilar?ders=ogle-3").text
    assert sayfa.count('/goruldu"') == 1 and "Öğleden sonra · 3. ders · 11/C" in sayfa
    assert panel.get("/program/uyarilar?ders=3").text.count('/goruldu"') == 3  # eski bağlantı: iki devre
    assert panel.get("/program/uyarilar?ders=yok-3").text.count('/goruldu"') == 3  # bilinmeyen devre yok sayılır


def test_tek_devreli_okul_davranisi_degismez(uygulama, panel, tahta, saat):
    """Tek devreli okulda şerit devre adı yazmaz, ızgarada devre etiketi çıkmaz, kilit eski gibi çalışır."""
    kur_ve_gir(panel)
    zil_elle({**SABAH, "devre_adi": "Normal", "ilk_ders": "08:20"})
    panel.post("/program/kurallar", data={"pk_etkin": "1", "pk_gecikme_dk": "2", "pk_bos_saatte": "1", "bd_esik_dk": "10"})
    saat.ayarla(an(16, 8, 0))
    t = kimlik(tahta_ekle(panel, tahta, "T-1", durum(), subeler="9/A"))
    saat.ayarla(an(16, 9, 20))
    assert panel.get("/api/durum").json()["program"]["simdi"] == "2. ders · 09:10–09:50"
    calistir(uygulama, saat, an(16, 9, 2))
    assert [(k["neden"], k["acilis"]) for k in kilitler(t)] == [("Teneffüs", "09:10")]
    with vt.islem() as b:
        plan = yk._plan(b, yk.bugun())
        assert yk.sube_devre_adi(b, plan, "9/A") == ""
