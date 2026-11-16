"""Aşama 4: Kelebek R5 içe aktarma, sınav kipi (ayar.sinav), gözetmen kodu, yoklama, icmal, saklama.

Bütün veriler uydurmadır (tests/r5_uret.py).
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from r5_uret import SATIRLAR, r5
from yardimci import (
    an,
    bekle,
    gir,
    ileti,
    kimlik,
    kullanici_ekle,
    kur_ve_gir,
    sorgu,
    tahta_ekle,
    yeni_ajan_durumu,
)

SINAVLI = ["acil", "duyuru_id", "program_kilidi", "sinav"]


def sinavli_durum(**ek) -> dict:
    return yeni_ajan_durumu(yetenekler=SINAVLI, oturum={"sinif": "ogretmen"}, **ek)


def yukle(panel, veri: bytes, ad: str = "r5.xlsx"):
    return panel.post("/sinavlar/ice-aktar", files={"dosya": (ad, veri, "application/octet-stream")})


def sinav_id_al(yanit) -> int:
    assert yanit.status_code == 303, yanit.text
    return int(yanit.headers["location"].split("/sinav/")[1].split("?")[0].split("#")[0])


def salonlar(sinav_id: int) -> dict[str, dict]:
    return {s["ad"]: s for s in sorgu("SELECT * FROM sinav_salon WHERE sinav_id = ?", sinav_id)}


@pytest.fixture()
def ortam(panel, tahta, saat):
    """İki salon tahtası + bir şube tahtası (hepsi sınav yetenekli). Saat 18.11.2026 08:00 (panel oturumu 12 sa)."""
    saat.ayarla(an(18, 8))
    kur_ve_gir(panel)
    t10b = tahta_ekle(panel, tahta, "10/B Tahtası", sinavli_durum(), derslik="10/B")
    t11a = tahta_ekle(panel, tahta, "11/A Tahtası", sinavli_durum(), derslik="11/A Dersliği")
    t9a = tahta_ekle(panel, tahta, "9/A Tahtası", sinavli_durum(), derslik="9/A", subeler="9/A")
    sinav_id = sinav_id_al(yukle(panel, r5()))
    return {"panel": panel, "tahta": tahta, "saat": saat, "10b": t10b, "11a": t11a, "9a": t9a, "sinav": sinav_id}


def yayinla(o) -> None:
    yanit = o["panel"].post(f"/sinav/{o['sinav']}/durum", data={"eylem": "yayinla"})
    assert "t=hata" not in yanit.headers["location"], ileti(yanit)


def ayar_sinav(o, anahtar: str, **durum):
    return bekle(o["tahta"], o[anahtar], sinavli_durum(**durum))["ayar"]["sinav"]


def kod_al(o, salon_adi: str = "10/B Dersliği") -> tuple[int, str]:
    s = salonlar(o["sinav"])[salon_adi]
    return s["id"], s["gozetmen_kodu"]


# ---- 1–8: okuyucu ve maske ----------------------------------------------------------------------
def test_r5_okunur_kunye_ve_satirlar_dogru():
    from tahta_sunucu import sinav, xlsx

    sayfa, satirlar = xlsx.oku_ayrintili(r5())
    cozum = sinav.r5_ayristir(sayfa, satirlar)
    assert cozum["ad"] == "1. Dönem 1. Ortak Sınav" and cozum["donem"] == "2026-2027 1. Dönem"
    assert cozum["baslangic"] == int(an(18, 10).timestamp())
    assert [k["okul_no"] for k in cozum["kayitlar"]] == ["5501", "5547", "6603", "5512"]
    assert cozum["kayitlar"][1] == {"okul_no": "5547", "maske": "Ah*** Yı****", "sube": "9/B",
                                    "ders": "Matematik — 9. Sınıf", "salon": "10/B Dersliği", "koltuk": 2}  # fmt: skip
    assert cozum["uyarilar"] == []
    assert sinav.kunye_ayristir("Sınav · ara · 01.12.2026 09:30 · Üretim: x")["ad"] == "Sınav · ara"


def test_r5_inline_ve_sayisal_hucreler_okunur():
    from tahta_sunucu import sinav, xlsx

    cozum = sinav.r5_ayristir(*xlsx.oku_ayrintili(r5(satir_ici=True, sayisal_no=True, sayfa="Sayfa1")))
    assert [k["okul_no"] for k in cozum["kayitlar"]] == ["5501", "5547", "6603", "5512"]
    assert cozum["kayitlar"][0]["maske"] == "De*** Ka**"
    assert any("Dagitim" in u for u in cozum["uyarilar"])


def test_r5_degil_ise_reddedilir(ortam):
    yanit = yukle(ortam["panel"], r5(a1="Deneme — SALON YOKLAMA LİSTESİ"))
    assert "t=hata" in yanit.headers["location"] and "Toplu Dağıtım Çizelgesi değil" in ileti(yanit)
    yanit = yukle(ortam["panel"], b"PK\x03\x04bozuk")
    assert "Dosya okunamadı" in ileti(yanit)


def test_r5_sutun_sirasi_degismisse_reddedilir(ortam):
    basliklar = ("Okul No", "Şube", "Ad Soyad", "Ders", "Salon", "Koltuk No", "Durum")
    yanit = yukle(ortam["panel"], r5(basliklar=basliklar))
    assert "Sütunlar beklenen sırada değil" in ileti(yanit)


def test_r5_doctype_ve_zip_bombasi_reddedilir():
    from tahta_sunucu import xlsx

    with pytest.raises(ValueError, match="güvenli olmayan"):
        xlsx.oku(r5(ek_xml=b'<!DOCTYPE x [<!ENTITY a "b">]>'))
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("xl/workbook.xml", b"<a/>")
        zf.writestr("xl/worksheets/sheet1.xml", b" " * (xlsx.ACILMIS_SINIR + 10))
    with pytest.raises(ValueError, match="açılmış boyutu"):
        xlsx.oku(tampon.getvalue())
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as zf:
        for i in range(xlsx.UYE_SINIRI + 1):
            zf.writestr(f"x{i}", b"")
    with pytest.raises(ValueError, match="çok fazla parça"):
        xlsx.oku(tampon.getvalue())


def _uye_degistir(veri: bytes, ad: str, yeni: bytes) -> bytes:
    tampon = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(veri)) as eski, zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as zf:
        for uye in eski.infolist():
            zf.writestr(uye.filename, yeni if uye.filename == ad else eski.read(uye))
    return tampon.getvalue()


def test_r5_utf16_ile_gizlenen_doctype_reddedilir():
    from tahta_sunucu import xlsx

    veri = r5()
    with zipfile.ZipFile(io.BytesIO(veri)) as zf:
        sst = zf.read("xl/sharedStrings.xml").decode()
    govde = sst.split("?>", 1)[1]
    sinsi = '<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE sst [<!ENTITY a "AAAA">]>' + govde.replace(
        "<t>", "<t>&a;", 1
    )
    with pytest.raises(ValueError, match="güvenli olmayan"):
        xlsx.oku(_uye_degistir(veri, "xl/sharedStrings.xml", sinsi.encode("utf-16")))
    # BOM'suz UTF-16LE de (bayt aramasıyla görünmez) reddedilir.
    with pytest.raises(ValueError, match="güvenli olmayan"):
        xlsx.oku(_uye_degistir(veri, "xl/sharedStrings.xml", sinsi.encode("utf-16-le")))


def test_bozuk_sikistirilmis_uye_okunamadi_iletisi_verir(ortam):
    from tahta_sunucu import xlsx

    veri = bytearray(r5())
    # sayfa üyesinin sıkıştırılmış verisinin ortasını boz
    with zipfile.ZipFile(io.BytesIO(bytes(veri))) as zf:
        bilgi = zf.getinfo("xl/worksheets/sheet1.xml")
    bas = bilgi.header_offset + 30 + len(bilgi.filename.encode()) + len(bilgi.extra)
    for i in range(bas + 5, bas + min(bilgi.compress_size, 40)):
        veri[i] ^= 0x5A
    with pytest.raises(ValueError, match="Dosya okunamadı"):
        xlsx.oku(bytes(veri))
    yanit = yukle(ortam["panel"], bytes(veri))
    assert yanit.status_code == 303
    assert "Dosya okunamadı" in ileti(yanit)


def test_r5_tekrarli_koltuk_ve_okul_no_satir_numarasiyla_reddedilir_ad_gecmez(ortam):
    satirlar = SATIRLAR + [
        ("5547", "Zeynep Tekrar", "9/B", "Matematik — 9. Sınıf", "11/A Dersliği", 2, ""),
        ("7001", "Kerem Koltuk", "9/C", "Matematik — 9. Sınıf", "10/B Dersliği", 1, ""),
        ("", "Boş Numara", "9/C", "Matematik — 9. Sınıf", "11/A Dersliği", 5, ""),
    ]
    yanit = yukle(ortam["panel"], r5(satirlar))
    assert yanit.status_code == 400
    metin = yanit.text
    assert "Satır 9 (Okul No 5547): okul numarası satır 6&#39;de de var." in metin or "Satır 9 (Okul No 5547)" in metin
    assert "Satır 10 (Okul No 7001): koltuk numarası bu salonda satır 5" in metin
    assert "Satır 11: okul numarası boş" in metin
    for ad in ("Zeynep", "Kerem", "Boş Numara"):
        assert ad not in metin
    assert metin.count('role="alert"') == 1 and metin.count("hiçbir şey kaydedilmedi") == 1  # tek uyarı bandı
    assert sorgu("SELECT COUNT(*) AS n FROM sinav")[0]["n"] == 1  # yalnız fikstürün sınavı
    kayit = sorgu("SELECT * FROM kayit WHERE islem = 'Sınav içe aktarma reddedildi'")[-1]
    assert "5547" not in kayit["ayrinti"] and "3 satır" in kayit["ayrinti"]


def test_ad_soyad_veritabanina_yazilmaz(ortam, tmp_path):
    ham = b"".join(p.read_bytes() for p in tmp_path.glob("tahta-kontrol.db*"))
    for ad in ("Deniz Kaya", "Yılmaz", "Elif Su", "Demir"):
        assert ad.encode() not in ham
    assert "Ah*** Yı****".encode() in ham


def test_maskeleme_kurallari():
    from tahta_sunucu import maske

    assert maske.kalabalik("Ahmet Yılmaz") == "Ah*** Yı****"
    assert maske.kalabalik("Can Ak") == "Ca* A*"
    assert maske.kalabalik("Elif Su Demir") == "El** S* De***"
    assert maske.kalabalik("İsmail Özgür Çağlar") == "İs**** Öz*** Ça****"
    assert maske.kalabalik("A " * 50).count("*") <= 60 and len(maske.kalabalik("Abcdef " * 20)) == 60
    assert maske.no_son("1047") == "47" and maske.no_son("A-9") == "9" and maske.no_son("x") == "x"


# ---- 9–13: aktarma, eşleştirme, yayın ---------------------------------------------------------------
def test_ayni_sinav_yeniden_aktarilinca_liste_yenilenir_eslesme_korunur(ortam):
    panel, sinav_id = ortam["panel"], ortam["sinav"]
    assert "zaten aktarılmış" in ileti(yukle(panel, r5()))
    once = salonlar(sinav_id)
    panel.post(f"/sinav/{sinav_id}/eslestir", data={f"gozetmen_{once['10/B Dersliği']['id']}": "Deneme Öğretmen"})
    yeni = SATIRLAR[:3] + [("5599", "Yeni Öğrenci", "9/A", "Fizik — 9. Sınıf", "12/C Dersliği", 1, "")]
    yanit = yukle(panel, r5(yeni))
    assert sinav_id_al(yanit) == sinav_id and "Liste yenilendi: 4 öğrenci, 2 salon." in ileti(yanit)
    sonra = salonlar(sinav_id)
    assert set(sonra) == {"10/B Dersliği", "12/C Dersliği"}
    assert sonra["10/B Dersliği"]["gozetmen_kodu"] == once["10/B Dersliği"]["gozetmen_kodu"]
    assert sonra["10/B Dersliği"]["gozetmen_adi"] == "Deneme Öğretmen"
    assert sonra["10/B Dersliği"]["tahta_id"] == kimlik(ortam["10b"])
    assert {d["ad"] for d in sorgu("SELECT ad FROM sinav_ders WHERE sinav_id = ?", sinav_id)} == {
        "Matematik — 9. Sınıf", "Matematik — 10. Sınıf", "Fizik — 9. Sınıf"}  # fmt: skip
    ortam["saat"].ayarla(an(18, 9, 55))
    assert "Sınav başladı" in ileti(yukle(panel, r5(SATIRLAR)))


def test_eslestirme_onerisi_derslik_adindan_ve_hafizadan(ortam):
    panel, sinav_id = ortam["panel"], ortam["sinav"]
    s = salonlar(sinav_id)
    assert s["10/B Dersliği"]["tahta_id"] == kimlik(ortam["10b"])  # derslik "10/B" ↔ "10/B Dersliği"
    assert s["11/A Dersliği"]["tahta_id"] == kimlik(ortam["11a"])  # derslik birebir
    # Hafıza: elle başka tahtaya eşlenen salon sonraki sınavda o tahtayı önerir.
    panel.post(f"/sinav/{sinav_id}/eslestir", data={f"salon_{s['11/A Dersliği']['id']}": str(kimlik(ortam["9a"]))})
    ikinci = sinav_id_al(yukle(panel, r5(a2="Deneme Sınavı · 25.11.2026 10:00 · 2026-2027 1. Dönem")))
    assert salonlar(ikinci)["11/A Dersliği"]["tahta_id"] == kimlik(ortam["9a"])


def test_ayni_tahta_iki_salona_eslenemez(ortam):
    s = salonlar(ortam["sinav"])
    t = str(kimlik(ortam["10b"]))
    yanit = ortam["panel"].post(f"/sinav/{ortam['sinav']}/eslestir",
                                data={f"salon_{s['10/B Dersliği']['id']}": t, f"salon_{s['11/A Dersliği']['id']}": t})  # fmt: skip
    assert "iki salona seçilemez" in ileti(yanit)
    assert salonlar(ortam["sinav"])["11/A Dersliği"]["tahta_id"] == kimlik(ortam["11a"])


def test_yayina_alma_cakisan_sinavi_reddeder(ortam):
    panel = ortam["panel"]
    yayinla(ortam)
    ikinci = sinav_id_al(yukle(panel, r5(a2="Ara Sınav · 18.11.2026 10:30 · 2026-2027 1. Dönem")))
    yanit = panel.post(f"/sinav/{ikinci}/durum", data={"eylem": "yayinla"})
    assert "çakışan" in ileti(yanit) and "1. Dönem 1. Ortak Sınav" in ileti(yanit)
    s = salonlar(ikinci)
    panel.post(f"/sinav/{ikinci}/eslestir", data={f"salon_{x['id']}": "" for x in s.values()})
    yanit = panel.post(f"/sinav/{ikinci}/durum", data={"eylem": "yayinla"})
    assert "t=hata" not in yanit.headers["location"] and "sınav ekranı açılmayacak" in ileti(yanit)
    assert sorgu("SELECT islem FROM kayit WHERE islem = 'Sınav yayına alındı'")


def test_taslak_sinav_tahtaya_gitmez(ortam):
    ortam["saat"].ayarla(an(18, 9, 55))
    assert ayar_sinav(ortam, "10b") is None
    yanit = ortam["tahta"].post("/ajan/sinav/kod", headers=ortam["10b"], json={"salon": kod_al(ortam)[0], "kod": kod_al(ortam)[1]})
    assert yanit.status_code == 403


# ---- 14–17: ayar.sinav ve süreler ----------------------------------------------------------------------
def test_giris_evresinde_liste_gider_sinav_basinca_gitmez(ortam):
    yayinla(ortam)
    ortam["saat"].ayarla(an(18, 9, 49))
    assert ayar_sinav(ortam, "10b") is None  # pencere 09:50'de açılır
    ortam["saat"].ayarla(an(18, 9, 53))
    veri = ayar_sinav(ortam, "10b")
    salon_id = kod_al(ortam)[0]
    assert veri["kimlik"] == f"sinav-{ortam['sinav']}-salon-{salon_id}" and veri["salon"] == salon_id
    assert veri["basla_sn"] == 420 and veri["bitis_sn"] == 420 + 40 * 60
    assert (veri["baslangic_saat"], veri["bitis_saat"]) == ("10:00", "10:40")
    assert [x["k"] for x in veri["liste"]] == [1, 2, 3] and veri["liste_fazla"] == 0
    assert veri["liste"][1] == {"k": 2, "a": "Ah*** Yı****", "n": "47", "s": "9/B"}
    assert "Cep telefonu" in veri["kurallar"] and veri["yoklama_alindi"] is False
    ortam["saat"].ayarla(an(18, 10, 1))
    veri = ayar_sinav(ortam, "10b")
    assert veri["basla_sn"] == -60 and "liste" not in veri
    assert ayar_sinav(ortam, "9a") is None  # şube tahtası salon değil
    ortam["saat"].ayarla(an(18, 10, 40))
    assert ayar_sinav(ortam, "10b") is None


def test_tahtaya_tam_okul_no_ve_ders_gitmez(ortam):
    yayinla(ortam)
    ortam["saat"].ayarla(an(18, 9, 55))
    metin = json.dumps(ayar_sinav(ortam, "10b"), ensure_ascii=False)
    for no in ("5501", "5547", "6603"):
        assert no not in metin
    veri = json.loads(metin)
    assert all(set(x) == {"k", "a", "n", "s"} for x in veri["liste"])
    assert [d["ad"] for d in veri["dersler"]] == ["Matematik — 10. Sınıf", "Matematik — 9. Sınıf"]  # yalnız salon düzeyinde


def test_sure_uzatma_ve_bitirme_kalan_sureye_yansir(ortam):
    panel, sinav_id = ortam["panel"], ortam["sinav"]
    yayinla(ortam)
    assert "süren sınavda" in ileti(panel.post(f"/sinav/{sinav_id}/uzat", data={"dk": "10", "salon": "hepsi"}))
    ortam["saat"].ayarla(an(18, 10, 10))
    salon_id = kod_al(ortam)[0]
    panel.post(f"/sinav/{sinav_id}/uzat", data={"dk": "10", "salon": str(salon_id)})
    veri = ayar_sinav(ortam, "10b")
    assert veri["bitis_sn"] == 40 * 60 and veri["bitis_saat"] == "10:50"
    assert ayar_sinav(ortam, "11a")["bitis_saat"] == "10:40"
    assert "Uzatma süresini seçin" in ileti(panel.post(f"/sinav/{sinav_id}/uzat", data={"dk": "7", "salon": "hepsi"}))
    yanit = panel.post(f"/sinav/{sinav_id}/durum", data={"eylem": "bitir"})
    assert "bitirildi" in ileti(yanit)
    assert ayar_sinav(ortam, "10b") is None and ayar_sinav(ortam, "11a") is None
    assert "Sınav süresi uzatıldı" in {k["islem"] for k in sorgu("SELECT islem FROM kayit")}


def test_karma_salonda_bitis_en_uzun_ders_suresi(ortam):
    panel, sinav_id = ortam["panel"], ortam["sinav"]
    dersler = {d["ad"]: d["id"] for d in sorgu("SELECT * FROM sinav_ders WHERE sinav_id = ?", sinav_id)}
    yanit = panel.post(
        f"/sinav/{sinav_id}/kunye",
        data={"ad": "1. Dönem 1. Ortak Sınav", "tarih": "18.11.2026", "saat": "10:00", "sure_dk": "40",
              f"ders_sure_{dersler['Matematik — 10. Sınıf']}": "60"},
    )  # fmt: skip
    assert "t=hata" not in yanit.headers["location"], ileti(yanit)
    yayinla(ortam)
    ortam["saat"].ayarla(an(18, 10, 5))
    veri = ayar_sinav(ortam, "10b")
    assert veri["bitis_saat"] == "11:00"
    assert {d["ad"]: d["bitis_saat"] for d in veri["dersler"]} == {"Matematik — 10. Sınıf": "11:00", "Matematik — 9. Sınıf": "10:40"}
    assert ayar_sinav(ortam, "11a")["bitis_saat"] == "10:40"


# ---- 18–24: gözetmen kodu ve yoklama --------------------------------------------------------------
def test_gozetmen_kodu_dogru_tahtada_ve_pencerede_gecerli(ortam):
    yayinla(ortam)
    ortam["saat"].ayarla(an(18, 9, 55))
    salon_id, kod = kod_al(ortam)
    yanit = ortam["tahta"].post("/ajan/sinav/kod", headers=ortam["10b"], json={"salon": salon_id, "kod": kod})
    assert yanit.status_code == 200, yanit.text
    veri = yanit.json()
    assert veri["sure_sn"] == 900 and veri["belirtec"] and veri["gelmeyen"] == [] and veri["basladi"] is False
    assert [x["k"] for x in veri["liste"]] == [1, 2, 3] and veri["tahtadan_yoklama"] is True
    # Başlamadan yoklama reddedilir.
    yanit = ortam["tahta"].post("/ajan/sinav/yoklama", headers=ortam["10b"], json={"belirtec": veri["belirtec"], "gelmeyen": [2]})
    assert yanit.status_code == 400 and "henüz başlamadı" in yanit.json()["hata"]
    assert sorgu("SELECT * FROM kayit WHERE islem = 'Gözetmen kodu girildi'")


def test_gozetmen_kodu_baska_tahtada_ve_pencere_disinda_gecersiz(ortam):
    yayinla(ortam)
    salon_id, kod = kod_al(ortam)
    ortam["saat"].ayarla(an(18, 9, 45))
    assert ortam["tahta"].post("/ajan/sinav/kod", headers=ortam["10b"], json={"salon": salon_id, "kod": kod}).status_code == 403
    ortam["saat"].ayarla(an(18, 9, 55))
    yanit = ortam["tahta"].post("/ajan/sinav/kod", headers=ortam["11a"], json={"salon": salon_id, "kod": kod})
    assert yanit.status_code == 403 and yanit.json()["kalan_deneme"] == 4  # 10b'nin denemesi ayrı sayılır
    assert ortam["tahta"].post("/ajan/sinav/kod", headers={"X-Tahta-Id": "1", "X-Tahta-Anahtar": "yanlis"},
                               json={"salon": salon_id, "kod": kod}).status_code == 401  # fmt: skip
    ortam["saat"].ayarla(an(18, 10, 40))
    assert ortam["tahta"].post("/ajan/sinav/kod", headers=ortam["10b"], json={"salon": salon_id, "kod": kod}).status_code == 403
    kayitlar = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Hatalı gözetmen kodu'")
    assert kayitlar and all(kod not in k["ayrinti"] for k in kayitlar)


def test_gozetmen_kodu_bes_hatada_bekletilir(ortam):
    yayinla(ortam)
    ortam["saat"].ayarla(an(18, 9, 55))
    salon_id, kod = kod_al(ortam)
    yanlis = "000000" if kod != "000000" else "111111"
    durumlar = [ortam["tahta"].post("/ajan/sinav/kod", headers=ortam["10b"], json={"salon": salon_id, "kod": yanlis}).status_code
                for _ in range(5)]  # fmt: skip
    assert durumlar == [403, 403, 403, 403, 429]
    yanit = ortam["tahta"].post("/ajan/sinav/kod", headers=ortam["10b"], json={"salon": salon_id, "kod": kod})
    assert yanit.status_code == 429 and 0 < yanit.json()["bekleme_sn"] <= 300
    ortam["saat"].ilerlet(301)
    assert ortam["tahta"].post("/ajan/sinav/kod", headers=ortam["10b"], json={"salon": salon_id, "kod": kod}).status_code == 200


def gozetmen_belirteci(o) -> str:
    salon_id, kod = kod_al(o)
    yanit = o["tahta"].post("/ajan/sinav/kod", headers=o["10b"], json={"salon": salon_id, "kod": kod})
    assert yanit.status_code == 200, yanit.text
    return yanit.json()["belirtec"]


def test_tahtadan_yoklama_salonu_butunuyle_yazar_ve_kayda_ad_dusmez(ortam):
    yayinla(ortam)
    ortam["saat"].ayarla(an(18, 10, 5))
    belirtec = gozetmen_belirteci(ortam)
    yanit = ortam["tahta"].post("/ajan/sinav/yoklama", headers=ortam["10b"], json={"belirtec": belirtec, "gelmeyen": [1, 3]})
    assert yanit.json() == {"gelmeyen_sayisi": 2, "mevcut": 3, "gelen": 1}
    yanit = ortam["tahta"].post("/ajan/sinav/yoklama", headers=ortam["10b"], json={"belirtec": belirtec, "gelmeyen": [2]})
    assert yanit.json()["gelmeyen_sayisi"] == 1
    gelmeyen = sorgu("SELECT koltuk, isaretleyen FROM sinav_ogrenci WHERE gelmedi = 1")
    assert [g["koltuk"] for g in gelmeyen] == [2] and gelmeyen[0]["isaretleyen"] == "tahta:10/B Tahtası (gözetmen kodu)"
    salon = salonlar(ortam["sinav"])["10/B Dersliği"]
    assert salon["yoklama_kaynak"] == "tahta:10/B Tahtası" and salon["yoklama_zamani"]
    kayit = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Sınav yoklaması (tahta)'")[-1]["ayrinti"]
    assert "10/B Dersliği: 1 gelmedi (koltuk 2)" in kayit
    for parca in ("5547", "Ah***", "Yılmaz"):
        assert parca not in json.dumps(sorgu("SELECT * FROM kayit"), ensure_ascii=False)
    assert ayar_sinav(ortam, "10b")["yoklama_alindi"] is True
    # Başka tahtanın belirteci kullanılamaz.
    yanit = ortam["tahta"].post("/ajan/sinav/yoklama", headers=ortam["11a"], json={"belirtec": belirtec, "gelmeyen": []})
    assert yanit.status_code == 401


def test_yoklama_salonda_olmayan_koltugu_reddeder(ortam):
    yayinla(ortam)
    ortam["saat"].ayarla(an(18, 10, 5))
    belirtec = gozetmen_belirteci(ortam)
    for gelmeyen in ([2, 9], ["x"], [True]):
        yanit = ortam["tahta"].post("/ajan/sinav/yoklama", headers=ortam["10b"], json={"belirtec": belirtec, "gelmeyen": gelmeyen})
        assert yanit.status_code == 400
    assert sorgu("SELECT COUNT(*) AS n FROM sinav_ogrenci WHERE gelmedi = 1")[0]["n"] == 0
    assert salonlar(ortam["sinav"])["10/B Dersliği"]["yoklama_zamani"] is None


def test_panelden_yoklama_tahta_yoklamasinin_uzerine_yazar(ortam):
    panel, sinav_id = ortam["panel"], ortam["sinav"]
    yayinla(ortam)
    salon_id = kod_al(ortam)[0]
    assert "henüz başlamadı" in ileti(panel.post(f"/sinav/{sinav_id}/salon/{salon_id}/yoklama", data={"gelmedi": "1"}))
    ortam["saat"].ayarla(an(18, 10, 5))
    belirtec = gozetmen_belirteci(ortam)
    ortam["tahta"].post("/ajan/sinav/yoklama", headers=ortam["10b"], json={"belirtec": belirtec, "gelmeyen": [1]})
    sayfa = panel.get(f"/sinav/{sinav_id}/salon/{salon_id}/yoklama")
    assert sayfa.status_code == 200 and "5547" in sayfa.text and "Tahta (10/B Tahtası)" in sayfa.text
    yanit = panel.post(f"/sinav/{sinav_id}/salon/{salon_id}/yoklama", data={"gelmedi": ["2", "3"]})
    assert "2 öğrenci gelmedi" in ileti(yanit)
    assert [g["koltuk"] for g in sorgu("SELECT koltuk FROM sinav_ogrenci WHERE gelmedi = 1 ORDER BY koltuk")] == [2, 3]
    assert salonlar(sinav_id)["10/B Dersliği"]["yoklama_kaynak"] == "panel:yonetici"
    assert panel.post(f"/sinav/{sinav_id}/salon/{salon_id}/yoklama", data={"gelmedi": "77"}).headers["location"].count("t=hata")


def test_sinav_kipi_kaldirilinca_tahtaya_sinav_gitmez(ortam):
    panel, sinav_id = ortam["panel"], ortam["sinav"]
    yayinla(ortam)
    ortam["saat"].ayarla(an(18, 10, 5))
    belirtec = gozetmen_belirteci(ortam)
    salon_id = kod_al(ortam)[0]
    yanit = panel.post(f"/sinav/{sinav_id}/salon/{salon_id}/kip-kaldir")
    assert "kaldırıldı" in ileti(yanit)
    assert ayar_sinav(ortam, "10b") is None and ayar_sinav(ortam, "11a") is not None
    yanit = ortam["tahta"].post("/ajan/sinav/yoklama", headers=ortam["10b"], json={"belirtec": belirtec, "gelmeyen": []})
    assert yanit.status_code == 401  # belirteç düştü
    assert "açık değil" in ileti(panel.post(f"/sinav/{sinav_id}/salon/{salon_id}/kip-kaldir"))


# ---- 25–29 --------------------------------------------------------------------------------------------
def test_otomatik_kapatma_sinavdaki_tahtaya_komut_vermez(ortam):
    panel = ortam["panel"]
    panel.post("/ayarlar", data={"bolum": "genel", "okul_adi": "Örnek", "ok_etkin": "1", "ok_saatler": "10:05"})
    yayinla(ortam)
    ortam["saat"].ayarla(an(18, 10, 6))
    for anahtar in ("10b", "11a", "9a"):
        bekle(ortam["tahta"], ortam[anahtar], sinavli_durum())
    assert panel.app.state.zamanlayici(an(18, 10, 6)) == 1
    kapat = sorgu("SELECT tahta_id FROM komut WHERE tur = 'kapat'")
    assert [k["tahta_id"] for k in kapat] == [kimlik(ortam["9a"])]
    assert sorgu("SELECT * FROM kayit WHERE islem = 'Otomatik kapatma sınav nedeniyle atlandı'")


def test_program_isi_sinavdaki_tahtaya_kilit_vermez(ortam):
    from tahta_sunucu import sinav

    yayinla(ortam)
    kancalar = ortam["panel"].app.state.program_askida_kancalari
    from tahta_sunucu import vt

    with vt.islem() as b:
        bas = int(an(18, 10).timestamp())
        assert kancalar[-1](b, kimlik(ortam["10b"]), bas - 300)
        assert not kancalar[-1](b, kimlik(ortam["10b"]), bas - 900)
        assert sinav.tahta_sinav_penceresinde(b, kimlik(ortam["10b"]), bas - 900, sinav.PROGRAM_ONCESI_SN)
        assert not kancalar[-1](b, kimlik(ortam["9a"]), bas)


def test_program_zamanlayicisi_sinav_penceresinde_ve_oncesinde_kilit_vermez(ortam):
    """Uçtan uca (§0-7): kancalar web.py'de gerçekten kayıtlı ve program işi onlara uyuyor."""
    panel, saat = ortam["panel"], ortam["saat"]
    from tahta_sunucu import vt

    elle = {"eylem": "uret", "devre_adi": "Normal", "ilk_ders": "08:20", "ders_sayisi": "8", "ders_dk": "40",
            "teneffus_dk": "10", "ogle_sonra": "4", "ogle_dk": "45", "gunler": ["0", "1", "2", "3", "4"]}  # fmt: skip
    assert ileti(panel.post("/program/zil/elle", data=elle)) == "Zil saatleri kaydedildi."
    kural = {"pk_etkin": "1", "pk_gecikme_dk": "2", "pk_bos_saatte": "1", "bd_esik_dk": "10", "bd_etkin": "1"}
    assert ileti(panel.post("/program/kurallar", data=kural)) == "Kurallar kaydedildi."
    yayinla(ortam)  # sınav 10:00; giriş penceresi 09:50; program engeli 09:40'tan itibaren

    def calistir(zaman):
        saat.ayarla(zaman)
        with vt.islem() as b:
            b.execute("UPDATE tahta SET son_gorulme = ?", (vt.simdi(),))
        panel.app.state.program_zamanlayici(zaman)

    def kilitler(tahta_id):
        return [k for k in sorgu("SELECT * FROM komut WHERE tahta_id = ? AND tur = 'kilitle'", tahta_id)
                if json.loads(k["veri_json"]).get("kaynak") == "program"]  # fmt: skip

    calistir(an(18, 9, 43))  # ders 2 sürüyor, dersliklerde ders yok → boş saat kilidi (sınavdan 10 dk önceki aralık)
    calistir(an(18, 9, 53))  # teneffüs; salon tahtaları giriş penceresinde
    calistir(an(18, 10, 20))  # sınav sürüyor
    for salon in ("10b", "11a"):
        assert kilitler(kimlik(ortam[salon])) == []
    assert kilitler(kimlik(ortam["9a"]))  # sınav dışındaki tahta kilit alır


def test_icmal_gelmeyenleri_sube_ve_no_sirasiyla_listeler(ortam):
    panel, sinav_id = ortam["panel"], ortam["sinav"]
    yayinla(ortam)
    ortam["saat"].ayarla(an(18, 10, 5))
    s = salonlar(sinav_id)
    panel.post(f"/sinav/{sinav_id}/salon/{s['10/B Dersliği']['id']}/yoklama", data={"gelmedi": ["1", "2", "3"]})
    from tahta_sunucu import sinav as sinav_mod
    from tahta_sunucu import vt

    with vt.islem() as b:
        veri = sinav_mod.icmal_verisi(b, b.execute("SELECT * FROM sinav WHERE id = ?", (sinav_id,)).fetchone())
    assert [(g["sube"], g["okul_no"]) for g in veri["gelmeyenler"]] == [("9/A", "5501"), ("9/B", "5547"), ("10/A", "6603")]
    assert veri["toplam"] == {"mevcut": 4, "gelen": 0, "gelmeyen": 3} and veri["alinmayan"] == 1
    assert [x["yoklama"] for x in veri["salonlar"]][1] == "ALINMADI"
    sayfa = panel.get(f"/sinav/{sinav_id}/icmal").text
    assert "SINAV YOKLAMA İCMALİ" in sayfa and "ALINMADI" in sayfa and "5547" in sayfa


def test_saklama_suresi_dolunca_kisisel_veri_silinir_ozet_kalir(ortam, tmp_path):
    panel, sinav_id = ortam["panel"], ortam["sinav"]
    yayinla(ortam)
    ortam["saat"].ayarla(an(18, 9))
    yanit = panel.post(f"/sinav/{sinav_id}/duyuru", data={"sure_dk": "10"})
    assert "1 şubeye gönderildi, 2 şubenin tahtası yok" in ileti(yanit)
    komut = sorgu("SELECT * FROM komut WHERE tur = 'duyuru'")[0]
    veri = json.loads(komut["veri_json"])
    assert komut["tahta_id"] == kimlik(ortam["9a"]) and "De*** Ka**" in veri["metin"] and "…01" in veri["metin"]
    assert "5501" not in veri["metin"] and "Ca* A*" in veri["metin"]
    duyuru = sorgu("SELECT * FROM duyuru WHERE sinav_id = ?", sinav_id)[0]
    assert duyuru["metin"] == "Sınav oturma listesi · 9/A"
    ortam["saat"].ayarla(an(18, 10, 5))
    s = salonlar(sinav_id)
    panel.post(f"/sinav/{sinav_id}/salon/{s['10/B Dersliği']['id']}/yoklama", data={"gelmedi": "2"})
    ortam["saat"].ayarla(an(18, 10, 1, ay=12))
    panel.app.state.sinav_zamanlayici()
    gir(panel, "yonetici")  # panel oturumu 12 saatte biter
    assert sorgu("SELECT COUNT(*) AS n FROM sinav_ogrenci")[0]["n"] == 0
    s = salonlar(sinav_id)
    assert (s["10/B Dersliği"]["ozet_mevcut"], s["10/B Dersliği"]["ozet_gelmeyen"]) == (3, 1)
    assert s["10/B Dersliği"]["gozetmen_kodu"] == "" and sorgu("SELECT kisisel_silinme FROM sinav")[0]["kisisel_silinme"]
    assert sorgu("SELECT veri_json FROM komut WHERE tur = 'duyuru'")[0]["veri_json"] == "{}"
    ham = b"".join(p.read_bytes() for p in tmp_path.glob("tahta-kontrol.db*"))
    assert b"De*** Ka**" not in ham
    sayfa = panel.get(f"/sinav/{sinav_id}/icmal").text
    assert "yalnız sayılar gösterilir" in sayfa


def test_kisisel_veri_elle_yalniz_sinav_bitince_silinir(ortam):
    panel, sinav_id = ortam["panel"], ortam["sinav"]
    yayinla(ortam)
    assert "bittikten sonra" in ileti(panel.post(f"/sinav/{sinav_id}/durum", data={"eylem": "kisisel_sil"}))
    assert "bittikten sonra" in ileti(panel.post(f"/sinav/{sinav_id}/durum", data={"eylem": "sil"}))
    ortam["saat"].ayarla(an(18, 11))
    assert "silindi" in ileti(panel.post(f"/sinav/{sinav_id}/durum", data={"eylem": "kisisel_sil"}))
    assert sorgu("SELECT COUNT(*) AS n FROM sinav_ogrenci")[0]["n"] == 0
    assert "Sınav silindi" in ileti(panel.post(f"/sinav/{sinav_id}/durum", data={"eylem": "sil"}))
    assert sorgu("SELECT COUNT(*) AS n FROM sinav_salon")[0]["n"] == 0


def test_idareci_sinav_islemlerini_yapabilir_ama_kurallari_degistiremez(ortam):
    panel = ortam["panel"]
    kullanici_ekle(panel, "idareci1")
    yanit = panel.post("/ayarlar", data={"bolum": "sinav", "sinav_kurallari": "Yeni kural."})
    assert "Sınav kuralları kaydedildi" in ileti(yanit)
    yanit = panel.post("/ayarlar", data={"bolum": "sinav", "sinav_kurallari": "Numara 12345678950 yazmayın"})
    assert yanit.status_code == 400 and "T.C. kimlik" in ileti(yanit)
    assert "Numara 12345678950 yazmayın</textarea>" in yanit.text  # yazılan metin kaybolmaz
    dokuz = "\n".join(f"Kural {i}." for i in range(9))
    yanit = panel.post("/ayarlar", data={"bolum": "sinav", "sinav_kurallari": dokuz})
    assert yanit.status_code == 400 and "en çok 8 satır" in ileti(yanit) and "Kural 8.</textarea>" in yanit.text
    gir(panel, "idareci1")
    ikinci = sinav_id_al(yukle(panel, r5(a2="İdareci Sınavı · 20.11.2026 10:00 · 2026-2027 1. Dönem")))
    assert "Sınav yayına alındı" in ileti(panel.post(f"/sinav/{ikinci}/durum", data={"eylem": "yayinla"}))
    yanit = panel.post("/ayarlar", data={"bolum": "sinav", "sinav_kurallari": "Başka kural."})
    assert "yönetici yetkisi" in ileti(yanit)
    assert sorgu("SELECT * FROM kayit WHERE islem = 'Yetkisiz işlem reddedildi' AND kullanici = 'idareci1'")
    ortam["saat"].ayarla(an(20, 9, 55))
    assert ayar_sinav(ortam, "10b")["kurallar"] == "Yeni kural."


def test_sinav_sayfasi_okul_no_gostermez(ortam):
    panel, sinav_id = ortam["panel"], ortam["sinav"]
    yayinla(ortam)
    sayfa = panel.get(f"/sinav/{sinav_id}")
    assert sayfa.status_code == 200
    api = panel.get(f"/api/sinav/{sinav_id}")
    assert api.status_code == 200 and api.json()["salonlar"][0]["ad"] == "10/B Dersliği"
    for no in ("5501", "5547", "6603", "5512"):
        assert no not in sayfa.text and no not in api.text
    assert panel.get("/sinavlar").status_code == 200
    kodlar = panel.get(f"/sinav/{sinav_id}/kodlar").text
    assert salonlar(sinav_id)["10/B Dersliği"]["gozetmen_kodu"] in kodlar
    panel.cookies.clear()
    assert panel.get(f"/api/sinav/{sinav_id}").status_code == 401
    assert panel.get(f"/sinav/{sinav_id}").status_code == 303


def test_pano_ve_api_durum_sinav_penceresini_gosterir(ortam):
    panel = ortam["panel"]
    yayinla(ortam)
    ortam["saat"].ayarla(an(18, 9, 55))
    bekle(ortam["tahta"], ortam["10b"], sinavli_durum(sinav={"kimlik": "x", "evre": "giris", "yerel_kapali": False}))
    tahtalar = {t["ad"]: t for t in panel.get("/api/durum").json()["tahtalar"]}
    assert tahtalar["10/B Tahtası"]["sinav"]["evre"] == "giris" and tahtalar["10/B Tahtası"]["sinav_ekran"] == "giris"
    assert tahtalar["9/A Tahtası"]["sinav"] is None and tahtalar["9/A Tahtası"]["sinav_yetenegi"] is True
    assert panel.get("/").status_code == 200 and panel.get(f"/tahta/{kimlik(ortam['10b'])}").status_code == 200
    # Evre geçişinde zamanlayıcı eşli tahtaları uyandırır.
    assert set(panel.app.state.sinav_zamanlayici()) == {kimlik(ortam["10b"]), kimlik(ortam["11a"])}
    assert panel.app.state.sinav_zamanlayici() == []


def test_goc_mevcut_veritabanina_sinav_tablolarini_ekler(tmp_path, monkeypatch):
    import sqlite3

    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    from tahta_sunucu import vt

    b = sqlite3.connect(tmp_path / "tahta-kontrol.db")
    for goc in vt.GOCLER[:3]:
        b.executescript(goc)
    b.execute("PRAGMA user_version = 3")
    b.commit()
    b.close()
    vt.hazirla()
    with vt.islem() as b:
        assert b.execute("PRAGMA user_version").fetchone()[0] == len(vt.GOCLER) >= 4
        assert "sinav_id" in {s["name"] for s in b.execute("PRAGMA table_info(duyuru)")}
        assert b.execute("PRAGMA secure_delete").fetchone()[0] == 1
        for tablo in ("sinav", "sinav_ders", "sinav_salon", "sinav_ogrenci", "sinav_eslesme"):
            assert b.execute(f"SELECT COUNT(*) FROM {tablo}").fetchone()[0] == 0


def test_kipi_kaldirilan_salonun_tahtasi_cakisma_sayilmaz(ortam):
    """Sınav kipi kaldırılan salonun tahtası o sınava bağlı değildir; çakışan başka sınava yayımlanabilir."""
    from tahta_sunucu import sinav as sinav_mod
    from tahta_sunucu import vt

    panel = ortam["panel"]
    yayinla(ortam)
    ikinci = sinav_id_al(yukle(panel, r5(a2="Ara Sınav · 18.11.2026 10:30 · 2026-2027 1. Dönem")))
    with vt.islem() as b:
        b.execute("UPDATE sinav_salon SET kip_kapanma = 1 WHERE sinav_id = ?", (ortam["sinav"],))
        s2 = b.execute("SELECT * FROM sinav WHERE id = ?", (ikinci,)).fetchone()
        eslesme = {x["id"]: x["tahta_id"] for x in b.execute("SELECT id, tahta_id FROM sinav_salon WHERE sinav_id = ?", (ikinci,))}
        assert any(eslesme.values()) and sinav_mod.cakisan_sinav(b, s2, eslesme) is None


def test_sinav_sayfasi_arayuz_kancalari_ve_pano_sinav_alani(ortam):
    """Tehlikeli işlemler onay penceresiyle (type=button + data-onay), canlı durum kancası, pano verisi."""
    panel, sinav_id = ortam["panel"], ortam["sinav"]
    sayfa = panel.get(f"/sinav/{sinav_id}").text
    assert 'data-onay="kodlar_yenile"' in sayfa and 'data-onay="sinav_sil"' in sayfa
    assert 'data-onay="sinav_bitir"' not in sayfa  # taslakta bitirme yok
    yayinla(ortam)
    ortam["saat"].ayarla(an(18, 10, 5))
    ayar_sinav(ortam, "10b")  # tahta çevrimiçi
    sayfa = panel.get(f"/sinav/{sinav_id}").text
    assert 'id="sinav-canli"' in sayfa and f'data-api="/api/sinav/{sinav_id}"' in sayfa
    assert 'data-onay="sinav_bitir"' in sayfa and 'data-onay="kip_kaldir"' in sayfa
    assert 'type="button" class="tehlike" data-onay="sinav_bitir"' in sayfa  # JS'siz gönderilemez
    s = salonlar(sinav_id)
    assert f'id="kip-kaldir-{s["10/B Dersliği"]["id"]}"' in sayfa
    durum = panel.get("/api/durum").json()
    t10b = next(t for t in durum["tahtalar"] if t["ad"] == "10/B Tahtası")
    assert t10b["sinav"]["evre"] == "suruyor" and t10b["sinav_yetenegi"] is True
    tahta_sayfasi = panel.get(f"/tahta/{t10b['id']}").text
    assert 'data-sinavdaki="1"' in tahta_sayfasi and "Sınav sürüyor" in tahta_sayfasi


def test_sube_duyurusu_sinav_baslangicina_kirpilir_ve_son_dakikada_reddedilir(ortam):
    panel, sinav_id = ortam["panel"], ortam["sinav"]
    yayinla(ortam)
    ortam["saat"].ayarla(an(18, 9, 55))  # giriş evresi; sınav 10:00
    yanit = panel.post(f"/sinav/{sinav_id}/duyuru", data={"sure_dk": "240"})
    assert "1 şubeye gönderildi" in ileti(yanit) and "sınav başlayınca kalkar (10:00)" in ileti(yanit)
    duyuru = sorgu("SELECT * FROM duyuru WHERE sinav_id = ?", sinav_id)[0]
    assert duyuru["bitis"] <= an(18, 10).timestamp() and duyuru["sure_sn"] == 300
    veri = json.loads(sorgu("SELECT veri_json FROM komut WHERE tur = 'duyuru'")[0]["veri_json"])
    assert veri["sure_sn"] == 300
    ortam["saat"].ayarla(an(18, 9, 59, 30))
    yanit = panel.post(f"/sinav/{sinav_id}/duyuru", data={"sure_dk": "10"})
    assert "başlamak üzere" in ileti(yanit)
    assert len(sorgu("SELECT id FROM duyuru WHERE sinav_id = ?", sinav_id)) == 1


def test_yayindaki_sinava_yeniden_aktarmada_eklenen_salona_tahta_onerilmez(ortam):
    panel, sinav_id = ortam["panel"], ortam["sinav"]
    yayinla(ortam)
    yeni = SATIRLAR[:3] + [("5599", "Yeni Öğrenci", "9/A", "Fizik — 9. Sınıf", "9/A Dersliği", 1, "")]
    yanit = yukle(panel, r5(yeni))
    assert sinav_id_al(yanit) == sinav_id
    assert "1 yeni salon eklendi; tahtalarını sınav sayfasında eşleyin" in ileti(yanit)
    s = salonlar(sinav_id)
    assert s["9/A Dersliği"]["tahta_id"] is None  # derslik "9/A" önerilebilirdi; yayında öneri yok
    assert s["10/B Dersliği"]["tahta_id"] == kimlik(ortam["10b"])  # eski eşleşme korunur


def test_kunyesi_degisen_sinav_yeniden_aktarilinca_uyari_verir(ortam):
    panel, sinav_id = ortam["panel"], ortam["sinav"]
    yanit = panel.post(f"/sinav/{sinav_id}/kunye", data={"ad": "Kısa Ad", "tarih": "18.11.2026", "saat": "10:00", "sure_dk": "40"})
    assert yanit.status_code == 303
    yanit = yukle(panel, r5(SATIRLAR[:3]))
    assert "taslak olarak açıldı" in ileti(yanit) and "benzer bir sınav zaten var (Kısa Ad" in ileti(yanit)
