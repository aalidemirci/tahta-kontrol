"""0.10.0 — zil düzenleyici uçları: çizelge oluşturma/kaydetme/hızlı oluştur/CSV, haftalık düzen, tarihe özel
çizelge, günü önizle, yetkiler, işlem kaydı ve bugünkü saat değişikliğinin etkileri.

Saat `saat` fikstürüyle sabittir (pazartesi 16.11.2026 09:00). Veriler uydurmadır ("Normal gün", "Kısa gün",
tahta "10-A dersliği", şube "10/A").
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from test_program_panel import ELLE, calistir, durum, hazirla, program_komutlari
from yardimci import SAHTE_TC, an, gir, ileti, kimlik, kullanici_ekle, kur_ve_gir, sorgu, tahta_ekle, zil_elle

from tahta_sunucu import cizelge

ORNEK = Path(__file__).parent / "ornek" / "okulzili-ornek.json"


def form_yap(taslak: dict, **ek) -> dict:
    """Taslaktan çizelge formu (sunucunun beklediği alan adları)."""
    form: dict = {"ad": taslak["ad"], "devre": [d["devre"] for d in taslak["devreler"]], "satir": []}
    for d in taslak["devreler"]:
        for s in d["satirlar"]:
            form["satir"].append(s["r"])
            form[f"{s['r']}_devre"] = d["devre"]
            form[f"{s['r']}_bas"] = s["bas"]
            form[f"{s['r']}_bit"] = s["bit"]
            if s.get("sil"):
                form[f"{s['r']}_sil"] = "1"
    form.update(ek)
    return form


def yeni_cizelge(panel, ad="Normal gün", duzen="tek") -> int:
    yanit = panel.post("/program/cizelge", data={"ad": ad, "duzen": duzen})
    assert yanit.status_code == 303, ileti(yanit)
    return int(re.search(r"/program/cizelge/(\d+)", yanit.headers["location"]).group(1))


def kayitli_taslak(cizelge_id: int) -> dict:
    from tahta_sunucu import vt

    with vt.islem() as b:
        return cizelge.taslak_dbden(b, cizelge_id)


def islemler(ad: str) -> list[dict]:
    return sorgu("SELECT * FROM kayit WHERE islem = ? ORDER BY id", ad)


# 19
def test_yeni_cizelge_varsayilanla_olusur_haftalik_atanmadan_ders_saati_bos(uygulama, panel):
    kur_ve_gir(panel)
    yanit = panel.post("/program/cizelge", data={"ad": "Normal gün", "duzen": "tek"})
    assert "Haftalık düzende bir güne atanana kadar kullanılmaz" in ileti(yanit)
    assert yanit.headers["location"].startswith("/program/cizelge/1?yeni=1")
    sayfa = panel.get(yanit.headers["location"])
    assert sayfa.status_code == 200 and 'id="cizelge-formu"' in sayfa.text and "<details class=\"acilir\" open>" in sayfa.text
    assert len(sorgu("SELECT * FROM zil_cizelge_ders WHERE cizelge_id = 1")) == 8
    assert sorgu("SELECT * FROM ders_saati") == []
    assert islemler("Zil çizelgesi oluşturuldu")[0]["ayrinti"] == "Normal gün · Normal 8"
    ikili = yeni_cizelge(panel, "İkili gün", "ikili")
    devreler = {s["devre"] for s in sorgu("SELECT devre FROM zil_cizelge_ders WHERE cizelge_id = ?", ikili)}
    assert devreler == {"sabah", "ogle"}
    assert "zaten var" in ileti(panel.post("/program/cizelge", data={"ad": "normal GÜN"}))
    assert "T.C." in ileti(panel.post("/program/cizelge", data={"ad": f"X {SAHTE_TC}"}))


# 20
def test_haftalik_duzen_ders_saatini_yeniden_yazar_ve_isleme_kaydi(uygulama, panel):
    kur_ve_gir(panel)
    normal = yeni_cizelge(panel, "Normal gün")
    cuma = yeni_cizelge(panel, "Cuma")
    form = {f"gun_{g}": str(normal) for g in range(4)} | {"gun_4": str(cuma), "gun_5": "", "gun_6": ""}
    yanit = panel.post("/program/haftalik", data=form)
    assert ileti(yanit).startswith("Haftalık düzen kaydedildi.")
    assert len(sorgu("SELECT * FROM ders_saati")) == 5 * 8
    assert islemler("Haftalık zil düzeni kaydedildi")[0]["ayrinti"] == "Pzt–Per: Normal gün · Cum: Cuma · Cmt, Paz: ders yok"
    assert "bulunamadı" in ileti(panel.post("/program/haftalik", data={"gun_0": "999"}))
    yanit = panel.post("/program/haftalik", data={})
    assert "Hiçbir güne çizelge atanmadı" in ileti(yanit) and sorgu("SELECT * FROM ders_saati") == []
    # tek devre + ikili karışımı uyarısı
    ikili = yeni_cizelge(panel, "İkili", "ikili")
    assert "bazı günler ikili" in ileti(panel.post("/program/haftalik", data={"gun_0": str(normal), "gun_1": str(ikili)}))
    sayfa = panel.get("/program?bolum=zil").text
    assert 'name="gun_0"' in sayfa and f'<option value="{normal}" selected>Normal gün</option>' in sayfa


# 21
def test_kaydet_hatada_taslakla_422_ve_alan_degerleri_korunur(uygulama, panel):
    kur_ve_gir(panel)
    cid = yeni_cizelge(panel)
    t = kayitli_taslak(cid)
    t["devreler"][0]["satirlar"][1]["bit"] = "09:05"  # 2. ders 09:10–09:05
    t["ad"] = "Normal gün (yeni)"
    yanit = panel.post(f"/program/cizelge/{cid}", data=form_yap(t, eylem="kaydet"))
    assert yanit.status_code == 422
    assert "Taslak — henüz kaydedilmedi." in yanit.text and 'value="Normal gün (yeni)"' in yanit.text
    assert 'value="09:05"' in yanit.text and 'aria-invalid="true"' in yanit.text and 'href="#r1_bit"' in yanit.text
    assert sorgu("SELECT ad FROM zil_cizelgesi WHERE id = ?", cid)[0]["ad"] == "Normal gün"
    # boş satıra yazılan ders araya girer ve numaralar kendiliğinden kayar; silinen satır düşer
    t = kayitli_taslak(cid)
    t["devreler"][0]["satirlar"].append({"r": "r50", "bas": "07:30", "bit": "08:10", "sil": False})
    t["devreler"][0]["satirlar"][7]["sil"] = True
    yanit = panel.post(f"/program/cizelge/{cid}", data=form_yap(t, eylem="kaydet"))
    assert ileti(yanit) == "Çizelge kaydedildi."
    dersler = sorgu("SELECT ders_no, baslangic FROM zil_cizelge_ders WHERE cizelge_id = ? ORDER BY ders_no", cid)
    assert dersler[0] == {"ders_no": 1, "baslangic": "07:30"} and len(dersler) == 8
    assert islemler("Zil çizelgesi kaydedildi")[0]["ayrinti"] == "Normal gün · Normal 8 · kullanımda: Kullanılmıyor"
    # devre ekle: taslak yeniden çizilir (200), kaydedilmez
    yanit = panel.post(f"/program/cizelge/{cid}", data=form_yap(kayitli_taslak(cid), eylem="devre_ekle", yeni_devre="ogle"))
    assert yanit.status_code == 200 and "Öğleden sonra · 0 ders" in yanit.text and 'name="devre" value="ogle"' in yanit.text


# 22
def test_hizli_olustur_kaydetmez(uygulama, panel):
    kur_ve_gir(panel)
    cid = yeni_cizelge(panel)
    p = {"normal_uret": "1", "normal_ilk": "08:30", "normal_sayi": "6", "normal_ders_dk": "40", "normal_teneffus_dk": "10",
         "normal_uzun_sonra": "3", "normal_uzun_dk": "45"}  # fmt: skip
    yanit = panel.post(f"/program/cizelge/{cid}/hizli", data=p)
    assert yanit.status_code == 200 and "Satırlar üretildi" in yanit.text and 'value="08:30"' in yanit.text
    assert sorgu("SELECT baslangic FROM zil_cizelge_ders WHERE cizelge_id = ? AND ders_no = 1", cid)[0]["baslangic"] == "08:20"
    yanit = panel.post(f"/program/cizelge/{cid}/hizli", data={**p, "normal_ilk": "23:00"})
    assert yanit.status_code == 422 and "gece yarısını" in yanit.text
    # CSV'den doldur da taslaktır
    csv = b"devre;ders;baslangic;bitis\nNormal;1;09:00;09:40\n"
    yanit = panel.post(f"/program/cizelge/{cid}/csv", files={"dosya": ("c.csv", csv, "text/csv")})
    assert yanit.status_code == 200 and "dolduruldu" in yanit.text and 'value="09:00"' in yanit.text
    assert len(sorgu("SELECT * FROM zil_cizelge_ders WHERE cizelge_id = ?", cid)) == 8
    indir = panel.get(f"/program/cizelge/{cid}/csv")
    assert indir.headers["content-disposition"] == 'attachment; filename="cizelge-normal-gun.csv"'
    assert indir.content.startswith(b"\xef\xbb\xbfdevre;ders;baslangic;bitis")


def program_olan_okul(panel, tahta, saat, **kural):
    """Pzt–Cum 8 ders (Normal) + 10-A dersliğinde Pazartesi 1–8. dersler (şube 10/A)."""
    hazirla(panel, **kural)
    saat.ayarla(an(16, 9, 0, 30))
    b = tahta_ekle(panel, tahta, "10-A dersliği", durum())
    t = kimlik(b)
    form = {f"d_0_normal_{n}": "1" for n in range(1, 9)} | {f"sube_0_normal_{n}": "10/A" for n in range(1, 9)}
    assert ileti(panel.post(f"/tahta/{t}/program", data=form)) == "Program kaydedildi."
    return b, t


# 23
def test_kullanimdaki_cizelgede_ders_sayisi_degisirse_onay_istenir(uygulama, panel, tahta, saat):
    _, t = program_olan_okul(panel, tahta, saat, kilit=False)
    cid = sorgu("SELECT id FROM zil_cizelgesi")[0]["id"]
    taslak = kayitli_taslak(cid)
    taslak["devreler"][0]["satirlar"][7]["sil"] = True  # 8. ders silinir
    yanit = panel.post(f"/program/cizelge/{cid}", data=form_yap(taslak, eylem="kaydet"))
    assert yanit.status_code == 422
    assert "Normal: ders sayısı 8 → 7." in yanit.text and "(1 tahta etkilenir)" in yanit.text
    assert 'name="onay_numara"' in yanit.text and len(sorgu("SELECT * FROM ders_saati WHERE gun = 0")) == 8
    # yalnız saat değişikliği onay istemez
    saat_degisen = kayitli_taslak(cid)
    saat_degisen["devreler"][0]["satirlar"][7]["bit"] = "15:20"
    assert ileti(panel.post(f"/program/cizelge/{cid}", data=form_yap(saat_degisen, eylem="kaydet"))).startswith("Çizelge kaydedildi.")
    yanit = panel.post(f"/program/cizelge/{cid}", data=form_yap(taslak, eylem="kaydet", onay_numara="1"))
    metin = ileti(yanit)
    assert metin.startswith("Çizelge kaydedildi.") and "1 tahtanın derslik programında artık olmayan 1 ders saati var" in metin
    assert len(sorgu("SELECT * FROM ders_saati WHERE gun = 0")) == 7
    assert islemler("Zil çizelgesi kaydedildi")[-1]["ayrinti"].endswith("· numara kayması onaylandı")


# 24
def test_bugunu_degistiren_kayit_program_kilitli_tahtayi_acar(uygulama, panel, tahta, saat):
    from tahta_sunucu import vt

    b, t = program_olan_okul(panel, tahta, saat)
    with vt.islem() as b_:
        b_.execute("UPDATE tahta SET durum_json = ? WHERE id = ?",
                   (json.dumps(durum(kilitli=True, kilit_kaynak="program", kilit_kalan=300)), t))  # fmt: skip
    uygulama.state.program_isleyici.bos_baslangic[t] = 1
    saat.ayarla(an(16, 9, 4))
    cid = sorgu("SELECT id FROM zil_cizelgesi")[0]["id"]
    taslak = kayitli_taslak(cid)
    taslak["devreler"][0]["satirlar"][1]["bas"] = "09:15"  # 2. ders 09:15'e kayar
    metin = ileti(panel.post(f"/program/cizelge/{cid}", data=form_yap(taslak, eylem="kaydet")))
    assert "Bugünkü ders saatleri değişti; program kilitli tahtalar açıldı" in metin
    assert len(program_komutlari(t, "kilit_ac")) == 1
    assert uygulama.state.program_isleyici.bos_baslangic == {}
    # ileri tarihli, bugünü etkilemeyen tarihe özel çizelge açma göndermez
    kisa = yeni_cizelge(panel, "Kısa gün")
    yanit = panel.post("/program/tarihli", data={"ad": "Deneme sınavı haftası", "bas": "2026-11-23", "bit": "2026-11-27",
                                                 "gunler": ["0", "1", "2", "3", "4"], "cizelge": str(kisa)})  # fmt: skip
    assert "Bugünkü" not in ileti(yanit) and len(program_komutlari(t, "kilit_ac")) == 1
    calistir(uygulama, saat, an(16, 9, 5))  # zamanlayıcı yeni saatlerle çalışır (hata yok)


# 25
def test_tarihli_cakisan_aralik_ve_tc_kimlik_reddedilir(uygulama, panel):
    kur_ve_gir(panel)
    kisa = yeni_cizelge(panel, "Kısa gün")
    temel = {"ad": "Deneme sınavı haftası", "bas": "2026-11-23", "bit": "2026-11-27", "gunler": ["0", "1", "2", "3", "4"],
             "cizelge": str(kisa)}  # fmt: skip
    assert "eklendi (23.11.2026–27.11.2026)" in ileti(panel.post("/program/tarihli", data=temel))
    assert islemler("Tarihe özel çizelge eklendi")[0]["ayrinti"] == "Deneme sınavı haftası · 23.11.2026–27.11.2026 · Pzt–Cum · Kısa gün"
    cakisan = panel.post("/program/tarihli", data={**temel, "ad": "Gezi", "bas": "2026-11-25", "bit": "2026-11-25", "cizelge": ""})
    assert "ile aynı günlere düşüyor; önce onu silin." in ileti(cakisan)
    # aynı aralık ama ortak gün yok (Cumartesi) → kabul
    assert "eklendi" in ileti(panel.post("/program/tarihli", data={**temel, "ad": "Cumartesi etkinliği", "gunler": ["5"], "cizelge": ""}))
    tc = panel.post("/program/tarihli", data={**temel, "ad": f"Veli {SAHTE_TC}", "bas": "2026-12-01", "bit": "2026-12-01"})
    assert "T.C. kimlik" in ileti(tc) and SAHTE_TC not in json.dumps(sorgu("SELECT * FROM kayit"))
    assert islemler("Tarihe özel çizelge reddedildi")
    for alanlar, beklenen in (
        ({"bas": "2026-12-05", "bit": "2026-12-01"}, "Bitiş tarihi başlangıçtan önce olamaz."),
        ({"bas": "2026-12-01", "bit": "2028-01-01"}, "Aralık en çok 366 gün olabilir."),
        ({"bas": "2026-11-01", "bit": "2026-11-02"}, "Bitişi geçmiş bir aralık eklenemez."),
        ({"bas": "2026-12-01", "bit": "2026-12-01", "gunler": []}, "En az bir gün seçin."),
    ):
        assert beklenen in ileti(panel.post("/program/tarihli", data={**temel, **alanlar})), beklenen
    tid = sorgu("SELECT id FROM zil_tarihli WHERE ad = 'Deneme sınavı haftası'")[0]["id"]
    assert "silindi" in ileti(panel.post(f"/program/tarihli/{tid}/sil"))
    assert islemler("Tarihe özel çizelge silindi")[0]["ayrinti"] == "Deneme sınavı haftası · 23.11.2026–27.11.2026"


# 26
def test_kullanilan_cizelge_silinemez(uygulama, panel):
    kur_ve_gir(panel)
    cid = yeni_cizelge(panel)
    panel.post("/program/haftalik", data={"gun_0": str(cid), "gun_1": str(cid)})
    yanit = panel.post(f"/program/cizelge/{cid}/sil")
    assert ileti(yanit) == "Bu çizelge kullanılıyor: Pzt, Sal. Önce haftalık düzenden ve tarihe özel çizelgelerden kaldırın."
    kopya = int(re.search(r"/program/cizelge/(\d+)", panel.post(f"/program/cizelge/{cid}/kopyala").headers["location"]).group(1))
    assert sorgu("SELECT ad FROM zil_cizelgesi WHERE id = ?", kopya)[0]["ad"] == "Normal gün (kopya)"
    assert islemler("Zil çizelgesi kopyalandı")[0]["ayrinti"] == "Normal gün → Normal gün (kopya)"
    assert "silindi" in ileti(panel.post(f"/program/cizelge/{kopya}/sil"))
    assert len(sorgu("SELECT * FROM zil_cizelge_ders WHERE cizelge_id = ?", kopya)) == 0  # satırlar da gider
    panel.post("/program/haftalik", data={})
    panel.post("/program/tarihli", data={"ad": "Gezi", "bas": "2026-11-20", "bit": "2026-11-20", "gunler": ["4"], "cizelge": str(cid)})
    assert "1 tarihe özel" in ileti(panel.post(f"/program/cizelge/{cid}/sil"))


# 27
def test_idareci_cizelgeyi_gorur_degistiremez_yetkisiz_kaydi(uygulama, panel):
    kur_ve_gir(panel)
    cid = yeni_cizelge(panel)
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    sayfa = panel.get(f"/program/cizelge/{cid}")
    assert sayfa.status_code == 200 and 'id="cizelge-formu"' not in sayfa.text and "CSV olarak indir" in sayfa.text
    assert panel.get(f"/program/cizelge/{cid}/csv").status_code == 200
    assert panel.get("/program/gun?tarih=2026-11-17").status_code == 200
    for yol, veri in (
        ("/program/cizelge", {"ad": "X"}),
        (f"/program/cizelge/{cid}", {"eylem": "kaydet"}),
        (f"/program/cizelge/{cid}/hizli", {}),
        (f"/program/cizelge/{cid}/kopyala", {}),
        (f"/program/cizelge/{cid}/sil", {}),
        ("/program/haftalik", {}),
        ("/program/tarihli", {"ad": "X"}),
        ("/program/tarihli/1/sil", {}),
    ):
        assert "yönetici yetkisi" in ileti(panel.post(yol, data=veri)), yol
    assert "yönetici yetkisi" in ileti(panel.post(f"/program/cizelge/{cid}/csv", files={"dosya": ("c.csv", b"x", "text/csv")}))
    assert len(islemler("Yetkisiz işlem reddedildi")) == 9
    sayfa = panel.get("/program?bolum=zil").text
    assert 'action="/program/haftalik"' in sayfa and 'name="gun_0"' not in sayfa and 'action="/program/cizelge"' not in sayfa


# 28
def test_okulzili_onayi_cizelge_kurar_elle_cizelgeyi_silmez(uygulama, panel):
    from tahta_sunucu import vt

    kur_ve_gir(panel)
    elle = yeni_cizelge(panel, "Kendi çizelgem")

    def yukle_onayla():
        panel.post("/program/zil/yukle", files={"dosya": ("ayarlar.json", ORNEK.read_bytes(), "application/json")})
        with vt.islem() as b:
            kimlik_ = vt.ayar_al(b, "program_onizleme")["kimlik"]
        return ileti(panel.post("/program/zil/onayla", data={"onizleme": kimlik_}))

    assert yukle_onayla().startswith("Zil saatleri kaydedildi.")
    cizelgeler = sorgu("SELECT * FROM zil_cizelgesi ORDER BY id")
    oz = [c for c in cizelgeler if c["kaynak"] == "okulzili"]
    assert oz and all(c["ad"].startswith("Okul Zili · ") for c in oz) and any(c["id"] == elle for c in cizelgeler)
    assert islemler("Zil saatleri kaydedildi")[0]["ayrinti"].endswith(f"· {len(oz)} çizelge")
    with vt.islem() as b:
        assert set(cizelge.haftalik_oku(b).values()) <= {c["id"] for c in oz}
        assert len(b.execute("SELECT * FROM ders_saati").fetchall()) == 3
    # Okul Zili çizelgesi elle düzenlenir → "elle düzenlendi"; yeniden alınca yenisi kurulur, elle çizelge kalır
    t = kayitli_taslak(oz[0]["id"])
    panel.post(f"/program/cizelge/{oz[0]['id']}", data=form_yap(t, eylem="kaydet"))
    assert "Okul Zili · elle düzenlendi" in panel.get("/program?bolum=zil").text
    yukle_onayla()
    sonra = sorgu("SELECT * FROM zil_cizelgesi ORDER BY id")
    assert any(c["id"] == elle for c in sonra)
    yeni_oz = [c for c in sonra if c["kaynak"] == "okulzili"]
    assert len(yeni_oz) == len(oz) and all(c["guncelleme"] is None for c in yeni_oz)  # düzenlenen silinip yenisi kuruldu
    # bütün zil düzenini sil
    assert "kapatıldı" in ileti(panel.post("/program/zil/sil"))
    assert sorgu("SELECT * FROM zil_cizelgesi") == [] and sorgu("SELECT * FROM ders_saati") == []
    assert islemler("Zil düzeni silindi")


# 29
def test_gun_onizleme_tarihli_kaynak_ve_tatil(uygulama, panel, saat):
    kur_ve_gir(panel)
    zil_elle(ELLE)
    sayfa = panel.get("/program/gun?tarih=2026-11-17").text
    assert "Salı, 17.11.2026" in sayfa and "Haftalık düzen · Ders saatleri · Pzt–Cum" in sayfa
    assert "08:20–09:00 · 1. ders" in sayfa and "11:30–12:15 · Öğle arası (45 dk)" in sayfa
    kisa = yeni_cizelge(panel, "Kısa gün")
    panel.post("/program/tarihli", data={"ad": "Deneme sınavı haftası", "bas": "2026-11-23", "bit": "2026-11-27",
                                         "gunler": ["0", "1", "2", "3", "4"], "cizelge": str(kisa)})  # fmt: skip
    panel.post("/program/tarihli", data={"ad": "Okul gezisi", "bas": "2026-11-20", "bit": "2026-11-20", "gunler": ["4"], "cizelge": ""})
    assert "Deneme sınavı haftası (tarihe özel çizelge)" in panel.get("/program/gun?tarih=2026-11-24").text
    gezi = panel.get("/program/gun?tarih=2026-11-20").text
    assert "Tatil: Okul gezisi" in gezi and "1. ders" not in gezi
    assert "Pazartesi, 16.11.2026" in panel.get("/program/gun?tarih=bozuk").text  # geçersiz tarih → bugün
    assert "Bugünün ders akışı" in panel.get("/program?bolum=zil").text


# 30
def test_plan_hesapla_yalniz_program_modulunden_cagrilir():
    kok = Path(__file__).parent.parent / "tahta_sunucu"
    for yol in kok.rglob("*.py"):
        if yol.name != "program.py":
            assert "plan_hesapla(" not in yol.read_text(encoding="utf-8"), yol.name


# 31
def test_cizelge_sayfasi_satir_ici_betik_ve_stil_yok(uygulama, panel):
    kur_ve_gir(panel)
    zil_elle(ELLE)
    cid = yeni_cizelge(panel, "İkili", "ikili")
    for yol in (f"/program/cizelge/{cid}", "/program?bolum=zil", "/program/gun?tarih=2026-11-16"):
        metin = panel.get(yol).text
        assert "style=" not in metin and "onclick" not in metin, yol
        for govde in re.findall(r"<script\b[^>]*>(.*?)</script>", metin, re.S):
            assert not govde.strip() or govde.lstrip().startswith(("{", "[")), yol
    assert "<svg viewBox=\"0 0 1000" in panel.get(f"/program/cizelge/{cid}").text


# ---- arayüz (0.10.0 arayüz uygulayıcısı) ---------------------------------------------------------------
def test_hata_sonrasi_yeniden_cizimde_bos_satir_birikmez_kimlik_cakismaz(uygulama, panel):
    kur_ve_gir(panel)
    cid = yeni_cizelge(panel)
    t = kayitli_taslak(cid)
    # JS'li formdaki gibi: aralıklı kimlik (r40), gizli boş satırlar da gönderilir; bir saat hatalı.
    t["devreler"][0]["satirlar"][0]["r"] = "r40"
    t["devreler"][0]["satirlar"][1]["bit"] = "09:05"
    t["devreler"][0]["satirlar"] += [{"r": f"r{n}", "bas": "", "bit": "", "sil": False} for n in (8, 9, 10)]
    yanit = panel.post(f"/program/cizelge/{cid}", data=form_yap(t, eylem="kaydet"))
    assert yanit.status_code == 422
    kimlikler = re.findall(r'name="satir" value="(r\d+)"', yanit.text)
    assert len(kimlikler) == len(set(kimlikler)) == 8 + cizelge.BOS_SATIR  # 8 ders + yalnız 3 yeni boş satır
    assert 'class="hata-ileti goster" id="r1_bit-hata"' in yanit.text


def test_zil_sekmesi_bilesenleri_ve_bolum_iletisi(uygulama, panel):
    kur_ve_gir(panel)
    cid = yeni_cizelge(panel)
    kopya = int(re.search(r"/program/cizelge/(\d+)", panel.post(f"/program/cizelge/{cid}/kopyala").headers["location"]).group(1))
    yanit = panel.post("/program/haftalik", data={"gun_0": str(cid)})
    assert yanit.headers["location"].startswith("/program?bolum=zil&yer=haftalik") and yanit.headers["location"].endswith("#ileti")
    sayfa = panel.get(yanit.headers["location"]).text
    # ileti haftalık düzen bölümünün içinde ve odaklanır; sayfa başında ikinci kez çizilmez
    assert sayfa.count("Haftalık düzen kaydedildi.") == 1 and 'id="ileti" tabindex="-1" data-odakla' in sayfa
    assert sayfa.index('id="haftalik"') < sayfa.index('id="ileti"') < sayfa.index('id="cizelgeler"')
    # yalnız kullanılmayan çizelgede onaylı silme düğmesi; panel.js'te onay tanımı var
    assert f'id="cizelge-sil-{kopya}"' in sayfa and f'id="cizelge-sil-{cid}"' not in sayfa
    assert 'data-onay="cizelge_sil"' in sayfa and 'data-onay="zil_sil"' in sayfa
    js = (Path(__file__).parent.parent / "tahta_sunucu" / "statik" / "panel.js").read_text(encoding="utf-8")
    assert "cizelge_sil: {" in js and "function cizelgeKur()" in js and "cizelgeKur();" in js
    # çizelge sayfası: JS kancaları ve satır şablonu
    sayfa = panel.get(f"/program/cizelge/{cid}").text
    assert '<template id="cizelge-satir">' in sayfa and 'id="cizelge-duyuru" aria-live="polite"' in sayfa
    assert 'data-ders-ekle' in sayfa and 'id="hizli-formu"' in sayfa
    # Enter ile gönderimde varsayılan düğme Kaydet olsun ("Devre ekle" ondan sonra gelir)
    assert sayfa.index('value="kaydet"') < sayfa.index('value="devre_ekle"')


def test_zaman_cizgisi_liste_ogeleri_tur_tasir():
    zc = cizelge.zaman_cizgisi([("Normal", [(1, "08:20", "09:00"), (2, "09:10", "09:50"), (3, "10:40", "11:20")])])
    assert [o["tur"] for o in zc["listeler"][0]["ogeler"]] == ["ders", "teneffus", "ders", "ogle", "ders"]
    assert [o["metin"] for o in zc["listeler"][0]["ogeler"]] == zc["listeler"][0]["satirlar"]


# ---- 0.10.0 düzeltici ----------------------------------------------------------------------------
def test_tarihli_cizelgenin_devreleri_programla_uyusmazsa_tahta_bos_saatte_kilitlenmez(uygulama, panel, tahta, saat):
    """Haftalık düzen tek devre, tarihe özel çizelge ikili: derslik programı o güne uygulanamaz; tahta ders
    sürerken bütün gün kilitlenmez (yalnız teneffüs kilidi) ve eklerken uyarı çıkar."""
    _, t = program_olan_okul(panel, tahta, saat)
    kisa = yeni_cizelge(panel, "Kısa gün", "ikili")
    saat.ayarla(an(16, 7, 0))
    yanit = panel.post("/program/tarihli", data={"ad": "Kısa gün", "bas": "2026-11-16", "bit": "2026-11-16",
                                                 "gunler": ["0"], "cizelge": str(kisa)})  # fmt: skip
    assert yanit.status_code == 303 and "derslik programı uygulanmaz" in ileti(yanit)
    ilk = sorgu("SELECT baslangic, bitis FROM zil_cizelge_ders WHERE cizelge_id = ? ORDER BY baslangic", kisa)[0]
    h, m = map(int, ilk["baslangic"].split(":"))
    calistir(uygulama, saat, an(16, h, m + 15))  # ilk dersin ortası
    assert not any("ders yok" in json.loads(k["veri_json"]).get("neden", "") for k in program_komutlari(t, "kilitle"))


def test_tarihli_hatasinda_girilen_degerler_korunur(uygulama, panel):
    kur_ve_gir(panel)
    c = yeni_cizelge(panel, "Sınav günü")
    yanit = panel.post("/program/tarihli", data={"ad": "Sınav haftası", "bas": "2026-12-10", "bit": "2026-12-01",
                                                 "gunler": ["1", "3"], "cizelge": str(c)})  # fmt: skip
    assert yanit.status_code == 422
    assert "Bitiş tarihi başlangıçtan önce olamaz." in yanit.text
    assert 'value="Sınav haftası"' in yanit.text and 'value="2026-12-10"' in yanit.text and 'value="2026-12-01"' in yanit.text
    assert re.search(r'name="gunler" value="1" checked', yanit.text) and not re.search(r'name="gunler" value="0" checked', yanit.text)
    assert re.search(rf'<option value="{c}" selected>', yanit.text) and 'aria-invalid="true"' in yanit.text
    assert sorgu("SELECT COUNT(*) AS n FROM zil_tarihli")[0]["n"] == 0
    # Kimlik numarasına benzeyen ad geri yazılmaz
    yanit = panel.post("/program/tarihli", data={"ad": f"Not {SAHTE_TC}", "bas": "2026-12-01", "bit": "2026-12-01",
                                                 "gunler": ["1"], "cizelge": str(c)})  # fmt: skip
    assert yanit.status_code == 422 and SAHTE_TC not in yanit.text


def test_haftalik_bos_iken_tarihli_cizelge_program_kilidini_calistirir(uygulama, panel, tahta, saat):
    hazirla(panel)
    from tahta_sunucu import program, program_is, vt

    with vt.islem() as b:  # haftalık düzeni boşalt
        b.execute("DELETE FROM zil_haftalik")
        cizelge.haftalik_yaz(b)
    c = sorgu("SELECT id FROM zil_cizelgesi")[0]["id"]
    yanit = panel.post("/program/tarihli", data={"ad": "Telafi", "bas": "2026-11-21", "bit": "2026-11-21",
                                                 "gunler": ["5"], "cizelge": str(c)})  # fmt: skip
    assert yanit.status_code == 303, ileti(yanit)
    assert sorgu("SELECT COUNT(*) AS n FROM ders_saati")[0]["n"] == 0
    with vt.islem() as b:
        assert program.gun_plani(b, an(21, 9).date())["dersler"]
        assert program_is.program_ozeti(b, an(21, 9, 5))["simdi"] != "Ders saatleri tanımlı değil"


def test_jssiz_devre_ekle_sonra_hizli_olustur_devreyi_dusurmez(uygulama, panel):
    kur_ve_gir(panel)
    c = yeni_cizelge(panel, "İkili deneme", "tek")
    yanit = panel.post(f"/program/cizelge/{c}", data=form_yap(kayitli_taslak(c), eylem="devre_ekle", yeni_devre="sabah"))
    assert yanit.status_code == 200 and 'name="sabah_ilk"' in yanit.text
    hform = {"sabah_uret": "1", "sabah_ilk": "07:00", "sabah_sayi": "4", "sabah_ders_dk": "40", "sabah_teneffus_dk": "10",
             "sabah_uzun_sonra": "0", "sabah_uzun_dk": "0"}  # fmt: skip
    yanit = panel.post(f"/program/cizelge/{c}/hizli", data=hform)
    assert yanit.status_code == 200 and 'value="07:00"' in yanit.text


def test_hizli_olustur_hatasi_alana_baglanir_ve_basligi_dogru(uygulama, panel):
    kur_ve_gir(panel)
    c = yeni_cizelge(panel, "Normal gün", "tek")
    hform = {"normal_uret": "1", "normal_ilk": "08:20", "normal_sayi": "6", "normal_ders_dk": "40",
             "normal_teneffus_dk": "10", "normal_uzun_sonra": "7", "normal_uzun_dk": "30"}  # fmt: skip
    yanit = panel.post(f"/program/cizelge/{c}/hizli", data=hform)
    assert yanit.status_code == 422
    assert "Satırlar üretilemedi" in yanit.text and "Kaydedilemedi" not in yanit.text
    assert 'href="#h-normal-us"' in yanit.text
    assert re.search(r'id="h-normal-us" aria-invalid="true"', yanit.text)
