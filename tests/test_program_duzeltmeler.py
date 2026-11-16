"""Aşama 3 inceleme düzeltmeleri: yetim satırlı tahta, açma yedeği gürültüsü, istisna nedeni ve
işlem kaydı, önizleme ömrü, yükleme boyu, tahta sayfası "Şu an", gün kısaltmaları. Veriler uydurmadır.
"""

from __future__ import annotations

import json
from pathlib import Path

from test_program_panel import ELLE, calistir, ders_isaretle, durum, hazirla, program_komutlari
from yardimci import an, bekle, ileti, kimlik, sorgu, tahta_ekle, zil_elle

KOK = Path(__file__).resolve().parent.parent


def test_yalniz_yetim_satiri_kalan_tahta_programsiz_sayilir(uygulama, panel, tahta, saat):
    hazirla(panel)
    t = kimlik(tahta_ekle(panel, tahta, "T-1", durum()))
    ders_isaretle(panel, t, [1, 2, 3, 4, 5, 6, 7, 8])
    # Zil saatleri başka devre kimliğiyle yeniden alınır; eski "normal" satırları yetim kalır.
    assert zil_elle({**ELLE, "devre_adi": "Sabah"}) == "Zil saatleri kaydedildi."
    from tahta_sunucu import vt

    with vt.islem() as b:
        b.execute("DELETE FROM ders_saati WHERE devre = 'normal'")
        assert b.execute("SELECT COUNT(*) FROM ders_saati").fetchone()[0] > 0
    calistir(uygulama, saat, an(16, 10, 5))  # 3. ders sırasında
    assert program_komutlari(t, "kilitle") == []
    calistir(uygulama, saat, an(16, 10, 43))  # teneffüste programsız tahta gibi kilitlenir
    assert json.loads(program_komutlari(t, "kilitle")[0]["veri_json"])["neden"] == "Teneffüs"
    assert "Program yok" in panel.get("/program?bolum=derslik").text


def test_acma_yedegi_ajanin_kendi_acmasini_bekler(uygulama, panel, tahta, saat):
    hazirla(panel)
    saat.ayarla(an(16, 9, 0, 30))
    b = tahta_ekle(panel, tahta, "T-1", durum())
    t = kimlik(b)
    calistir(uygulama, saat, an(16, 9, 2, 10))
    saat.ayarla(an(16, 9, 9, 50))
    bekle(tahta, b, durum(kilitli=True, kilit_kaynak="program", kilit_kalan=10))
    # Ajan 09:10'da kendisi açar; yeni durumu henüz gelmemişken çalışan tur komut vermez.
    calistir(uygulama, saat, an(16, 9, 10, 5), canli=False)
    assert program_komutlari(t, "kilit_ac") == []
    assert len(sorgu("SELECT * FROM kayit WHERE islem = 'Program kilidi'")) == 1  # yalnız kilitleme
    # Ajan geç kaldıysa (pay doldu, tahta hâlâ kilitli bildiriyor) yedek devreye girer.
    calistir(uygulama, saat, an(16, 9, 10, 40), canli=False)
    assert len(program_komutlari(t, "kilit_ac")) == 1


def test_istisna_nedeni_islem_kaydina_yazilmaz_ve_ileri_tarih_iletisi(uygulama, panel, tahta, saat):
    hazirla(panel)
    saat.ayarla(an(16, 9, 0))
    tahta_ekle(panel, tahta, "T-1", durum())
    yanit = panel.post(
        "/program/istisna",
        data={"bas_tarih": "2026-11-19", "bas_saat": "09:00", "bit_tarih": "2026-11-19", "bit_saat": "12:00",
              "neden": "Uydurma Kişi veli görüşmesi"},
    )  # fmt: skip
    metin = ileti(yanit)
    assert "durduruldu" not in metin and "19.11.2026 09:00 – 19.11.2026 12:00" in metin and "uygulanmaz" in metin
    kayitlar = json.dumps(sorgu("SELECT * FROM kayit"), ensure_ascii=False)
    assert "Uydurma" not in kayitlar and "neden var" in kayitlar
    assert sorgu("SELECT neden FROM program_istisna")[0]["neden"] == "Uydurma Kişi veli görüşmesi"
    assert "durduruldu" in ileti(panel.post("/program/istisna", data={"sure": "1sa"}))


def test_suresi_gecen_onizleme_zamanlayicida_silinir(uygulama, panel, tahta, saat):
    hazirla(panel, kilit=False)
    saat.ayarla(an(16, 9, 0))
    csv = "derslik;gun;ders\nUydurma Ad;Pazartesi;1\n"
    panel.post("/program/aktar/tablo", files={"dosya": ("p.csv", csv.encode("utf-8"), "text/csv")})
    from tahta_sunucu import vt

    with vt.islem() as b:
        assert vt.ayar_al(b, "program_onizleme") is not None
    calistir(uygulama, saat, an(16, 9, 20))  # 30 dk dolmadı
    with vt.islem() as b:
        assert vt.ayar_al(b, "program_onizleme") is not None
    calistir(uygulama, saat, an(16, 9, 31))
    with vt.islem() as b:
        assert vt.ayar_al(b, "program_onizleme") is None
        assert "Uydurma" not in json.dumps([dict(s) for s in b.execute("SELECT * FROM ayar")], ensure_ascii=False)


def test_content_length_olmayan_yukleme_reddedilir(uygulama, panel, saat):
    hazirla(panel, kilit=False)
    govde = b'--x\r\nContent-Disposition: form-data; name="dosya"; filename="a.csv"\r\n\r\nderslik;gun;ders\r\n--x--\r\n'
    for yol in ("/program/aktar/tablo", "/program/aktar/asc", "/program/zil/yukle"):
        yanit = panel.post(
            yol, content=iter([govde]), headers={"content-type": "multipart/form-data; boundary=x"}
        )  # parça parça (chunked) gövde: Content-Length yok
        assert ileti(yanit) == "Dosya okunamadı.", yol


def test_tahta_sayfasi_su_an_gercek_durumu_yazar(uygulama, panel, tahta, saat):
    hazirla(panel, kilit=False)
    saat.ayarla(an(16, 9, 0))
    acik = kimlik(tahta_ekle(panel, tahta, "Açık", durum()))
    idare = kimlik(tahta_ekle(panel, tahta, "İdare", durum(kilitli=True, kilit_kaynak="idare")))
    kapali = kimlik(tahta_ekle(panel, tahta, "Kapalı", durum()))
    for t in (acik, idare, kapali):
        ders_isaretle(panel, t, [2])
    from tahta_sunucu import vt

    saat.ayarla(an(16, 9, 20))
    with vt.islem() as b:
        b.execute("UPDATE tahta SET son_gorulme = ? WHERE id != ?", (vt.simdi(), kapali))
        b.execute("UPDATE tahta SET son_gorulme = ? WHERE id = ?", (vt.simdi() - 3600, kapali))
    assert "Ders saatinde (2. ders), açık" in panel.get(f"/tahta/{acik}").text
    assert "Ders saatinde (2. ders), idare kilidinde" in panel.get(f"/tahta/{idare}").text
    sayfa = panel.get(f"/tahta/{kapali}").text
    assert "Ders saatinde (2. ders), tahta kapalı" in sayfa and "2. ders), açık" not in sayfa


def test_elle_giris_gun_kisaltmalari_tekil(uygulama, panel, saat):
    hazirla(panel, kilit=False)
    sayfa = panel.get("/program?bolum=zil").text
    for kisa in ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"):
        assert f'<span aria-hidden="true">{kisa}</span>' in sayfa


def test_pano_bos_ders_rozeti_cevrimdisi_tahtada_da_cizilir():
    js = (KOK / "tahta_sunucu" / "statik" / "panel.js").read_text(encoding="utf-8")
    assert "t.cevrimici && p.bos_ders" not in js and "if (p.bos_ders)" in js
