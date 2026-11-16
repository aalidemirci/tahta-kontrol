"""Tahtadaki yüzer düğme (0.9.0, G3) ve kurulum yönergesi (G1): sunucu tarafı.

Ayar (`ayar.dugme`, durum tabanlı), Ayarlar bölümü, tahtadan gelen olayların işlem kaydına düşmesi,
tahta sayfasındaki yetenek notu, "Tahta ekle" yönergesi ve kurulum betiğinin yetki alma sırası.
Bütün veriler UYDURMADIR.
"""

from __future__ import annotations

import io
import zipfile

import pytest
from yardimci import bekle, gir, ileti, kimlik, kullanici_ekle, kur_ve_gir, sorgu, tahta_ekle

from tahta_sunucu import paket, vt

YENI = {"kilitli": False, "yetenekler": ["acil", "duyuru_id", "program_kilidi", "ariza", "yoklama", "dugme"],
        "ekranlar": [{"arayuz": "gtk3"}], "oturum": {"sinif": "ogretmen"}}  # fmt: skip
ESKI = {"kilitli": False, "yetenekler": ["acil", "duyuru_id"], "ekranlar": [{"arayuz": "gtk3"}]}


@pytest.fixture
def okul(panel, tahta, saat):
    kur_ve_gir(panel)
    return {"yeni": tahta_ekle(panel, tahta, "T-01", YENI, surum="0.9.0"),
            "eski": tahta_ekle(panel, tahta, "T-02", ESKI, surum="0.8.0")}  # fmt: skip


def dugme_ayari(tahta, basliklar, durum=None) -> dict | None:
    return bekle(tahta, basliklar, durum or YENI, surum="0.9.0")["ayar"].get("dugme")


def kaydet(panel, **alanlar):
    return panel.post("/ayarlar", data={"bolum": "dugme", **alanlar})


def test_dugme_varsayilan_acik_yeniden_baslat_kapali_yoklama_ozellikle_birlikte(panel, tahta, okul):
    # Ders yoklaması varsayılan kapalıdır: "Yoklama al" kutusu işaretli olsa da tahtaya inmez.
    assert dugme_ayari(tahta, okul["yeni"]) == {"acik": True, "islemler": ["kilitle", "kapat", "ariza"]}
    panel.post("/ayarlar", data={"bolum": "yoklama", "yk_etkin": "1", "yk_maske": "ad_soyadbas",
                                 "yk_oturum_dk": "8", "yk_bosta_dk": "3"})  # fmt: skip
    assert dugme_ayari(tahta, okul["yeni"]) == {"acik": True, "islemler": ["kilitle", "kapat", "ariza", "yoklama"]}
    # Eski ajan da aynı alanı alır (durum tabanlı); yok sayması ajanın işidir.
    assert dugme_ayari(tahta, okul["eski"], ESKI)["acik"] is True


def test_dugme_ayari_yalniz_kendi_anahtarini_yazar_ve_kayda_duser(panel, tahta, okul):
    panel.post("/ayarlar", data={"bolum": "genel", "okul_adi": "Örnek Anadolu Lisesi", "ok_saatler": ""})
    yanit = kaydet(panel, dg_acik="1", dg_kilitle="1", dg_yeniden_baslat="1")
    assert yanit.headers["location"].startswith("/ayarlar?yer=dugme")
    assert ileti(yanit) == "Yüzer düğme ayarı kaydedildi."
    assert dugme_ayari(tahta, okul["yeni"]) == {"acik": True, "islemler": ["kilitle", "yeniden_baslat"]}
    with vt.islem() as b:
        assert vt.ayar_al(b, "okul_adi") == "Örnek Anadolu Lisesi"  # genel bölüm ezilmedi
        assert vt.ayar_al(b, "tahta_dugmesi")["islemler"]["kapat"] is False
    kayit = sorgu("SELECT * FROM kayit WHERE islem = 'Yüzer düğme ayarı kaydedildi'")
    assert kayit and kayit[-1]["ayrinti"] == "açık · Kilitle, Yeniden başlat"
    sayfa = panel.get("/ayarlar").text
    assert 'id="yuzer-dugme"' in sayfa and 'name="dg_yeniden_baslat" value="1" checked' in sayfa
    assert 'name="dg_kapat" value="1"' in sayfa and 'name="dg_kapat" value="1" checked' not in sayfa


def test_dugme_kapatilinca_ve_islem_secilmeyince_tahtada_gorunmez(panel, tahta, okul):
    assert ileti(kaydet(panel, dg_kilitle="1")) == "Yüzer düğme kapatıldı; tahtalarda görünmez."
    assert dugme_ayari(tahta, okul["yeni"]) == {"acik": False, "islemler": []}
    assert "Hiçbir işlem seçilmediği" in ileti(kaydet(panel, dg_acik="1"))
    assert dugme_ayari(tahta, okul["yeni"]) == {"acik": False, "islemler": []}
    # Bilinmeyen işlem adı ayara girmez.
    kaydet(panel, dg_acik="1", dg_kilitle="1", dg_sil="1")
    assert dugme_ayari(tahta, okul["yeni"])["islemler"] == ["kilitle"]


def test_dugme_ayarini_yalniz_yonetici_degistirir(panel, tahta, okul):
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    kaydet(panel, dg_kilitle="1")
    gir(panel, "yonetici")
    assert dugme_ayari(tahta, okul["yeni"])["acik"] is True


def test_dugme_ayarlar_notlari_kilit_kodu_yoklama_eski_ajan(panel, tahta, okul):
    sayfa = panel.get("/ayarlar").text
    assert "Kilit kodu belirlenmedi:" in sayfa
    assert "“Yoklama al” ders yoklaması kapalıyken görünmez" in sayfa
    assert "1 tahtada ajan güncellenmeli (eski ajan düğmeyi göstermez)." in sayfa
    panel.post("/ayarlar", data={"bolum": "genel", "okul_adi": "Örnek", "ok_saatler": "", "kilit_kodu": "4826"})
    assert "Kilit kodu belirlenmedi:" not in panel.get("/ayarlar").text


def test_tahtadan_kilitleme_ve_kapatma_olayi_kayda_ve_duruma_isler(panel, tahta, okul):
    durum = dict(YENI, kilitli=True, kilit_kaynak="idare",
                 olaylar=["Tahtadan kilitlendi (oturum: ogretmen).", "Tahtadan kapatıldı (oturum: ogretmen)."])  # fmt: skip
    bekle(tahta, okul["yeni"], durum, surum="0.9.0")
    satirlar = sorgu("SELECT * FROM kayit WHERE islem = 'Tahta olayı' ORDER BY id")
    assert [s["ayrinti"] for s in satirlar][-2:] == ["Tahtadan kilitlendi (oturum: ogretmen).",
                                                     "Tahtadan kapatıldı (oturum: ogretmen)."]  # fmt: skip
    assert satirlar[-1]["kullanici"] == "tahta:T-01"
    # Yerel kilit idare kilidiyle aynıdır: panelde "Kilitli" görünür, olaylar durum_json'a yazılmaz.
    t = panel.get("/api/durum").json()
    kart = next(x for x in (t["tahtalar"] if isinstance(t, dict) else t) if x["id"] == kimlik(okul["yeni"]))
    assert kart["kilitli"] is True and kart["dugme_yetenegi"] is True
    assert "olaylar" not in sorgu("SELECT durum_json FROM tahta WHERE id = ?", kimlik(okul["yeni"]))[0]["durum_json"]


def test_tahta_olayi_uzunlugu_ve_bicimi_sinirli(panel, tahta, okul):
    bekle(tahta, okul["yeni"], dict(YENI, olaylar=["x" * 5000] + ["o"] * 30), surum="0.9.0")
    satirlar = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Tahta olayı'")
    assert len(satirlar) == 20 and len(satirlar[0]["ayrinti"]) == 300
    once = len(sorgu("SELECT 1 FROM kayit WHERE islem = 'Tahta olayı'"))
    bekle(tahta, okul["yeni"], dict(YENI, olaylar="Tahtadan kilitlendi."), surum="0.9.0")  # liste değil: yok sayılır
    assert len(sorgu("SELECT 1 FROM kayit WHERE islem = 'Tahta olayı'")) == once


def test_tahta_sayfasi_dugme_yetenegi(panel, tahta, okul):
    assert "Yüzer düğme</dt><dd><span class=\"rozet\" data-durum=\"tamam\"" in panel.get(f"/tahta/{kimlik(okul['yeni'])}").text
    assert "Yüzer düğme için ajan güncellenmeli" in panel.get(f"/tahta/{kimlik(okul['eski'])}").text


def test_tahta_ekle_yonergesi_sudo_istemez_ve_etapadmin_notu(panel, okul):
    sayfa = panel.get("/ekle").text
    assert "\nbash tahta-kur.sh " in sayfa and "sudo bash tahta-kur.sh" not in sayfa
    assert "öğretmen parolası işe yaramaz" in sayfa and "etapadmin" in sayfa
    zip_ = zipfile.ZipFile(io.BytesIO(panel.get("/kur/usb.zip").content))
    okuyunuz = zip_.read("OKUYUNUZ.txt").decode("ascii")
    assert "    bash tahta-kur.sh ESLESTIRME_KODU" in okuyunuz and "sudo bash" not in okuyunuz


def test_kurulum_betigi_ascii_ve_yetki_sirasi():
    metin = paket.kurulum_betigi("https://10.0.0.5:8788", "ab" * 32).decode("utf-8")
    metin.encode("ascii")  # postinst/kur.sh iletileri bilerek ASCII (kural 9)
    sira = [metin.index(p) for p in ('if [ "$(id -u)" != "0" ]', "if sudo_yetkili; then", "pkexec \"$BASH_YOLU\"",
                                     "su --pty \"$YONETICI\"", "etapadmin_oturumunda \"$BETIK\"\n    exit 1")]  # fmt: skip
    assert sira == sorted(sira)
    assert "id etapadmin" in metin and "sudo -S" in metin
    # Parola betiğe yazılmaz ve okunmaz: read/chpasswd/echo ... | sudo yok.
    assert "read -s" not in metin and "chpasswd" not in metin and "| sudo" not in metin
    # Kod denetimi yetki istenmeden önce (yanlış kullanımda parola sorulmasın).
    assert metin.index('if [ -z "$KOD" ]') < metin.index("if sudo_yetkili; then")
