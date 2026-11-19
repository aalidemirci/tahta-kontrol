"""Aşama 2 uçtan uca: gerçek ajan servisi ↔ sunucu (acil, kimlikli duyuru) ve panel şablon kancaları."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from yardimci import (
    PAROLA,
    bekle,
    gir,
    kimlik,
    kullanici_ekle,
    kur_ve_gir,
    sorgu,
    tahta_ekle,
    yeni_ajan_durumu,
)


@pytest.fixture
def ajan(tmp_path, monkeypatch, panel, tahta):
    """Sunucuya onaylı tahta olarak bağlı GERÇEK ajan servisi (ağ yerine test istemcisi)."""
    monkeypatch.setenv("TAHTA_AJAN_DIZIN", str(tmp_path / "ajan-ayar"))
    monkeypatch.setenv("TAHTA_AJAN_DURUM", str(tmp_path / "ajan-durum"))
    from tahta_ajan import servis as servis_mod

    monkeypatch.setattr(servis_mod.sistem, "etkin_oturum", lambda: {"sinif": "ogretmen"})
    monkeypatch.setattr(servis_mod.sistem, "acik_sure", lambda: 60)
    monkeypatch.setattr(servis_mod.sistem, "ag_bilgisi", lambda *_: {})
    kur_ve_gir(panel)
    basliklar = tahta_ekle(panel, tahta, "Gerçek ajan", durum=yeni_ajan_durumu())
    s = servis_mod.Servis()
    s.yapi = {"tahta_id": kimlik(basliklar)}
    s.bildir = lambda: None  # arka plan iş parçacığı açılmasın
    s.ekranlar[1] = {"gonder": lambda _m: None, "bilgi": {"arayuz": "gtk3"}}

    def tur():
        """Ajanın bir uzun bekleme turu: durum + sonuçlar gider, yanıt işlenir, komutlar uygulanır."""
        sonuclar, s.sonuclar = s.sonuclar, []
        yanit = bekle(tahta, basliklar, s.durum_ozeti(), sonuclar=sonuclar)
        s._yanit_isle(yanit)
        for komut in yanit.get("komutlar") or []:
            basarili, cikti = s.komut_uygula(komut)
            s.sonuclar.append({"komut_id": komut["id"], "basarili": basarili, "cikti": cikti})
        return yanit

    return s, tur, basliklar


def test_gercek_ajan_acili_alir_teslimi_bildirir_bitince_birakir(ajan, panel):
    s, tur, basliklar = ajan
    yanit = panel.post("/acil/baslat", data={"tur": "tatbikat", "sablon": "", "baslik": "TATBİKAT", "metin": "Toplanma alanına gidiniz.",
                                              "sure_dk": "10", "onay": "1", "parola": PAROLA})  # fmt: skip
    assert yanit.status_code == 303
    acil_id = sorgu("SELECT id FROM acil_yayin")[0]["id"]

    tur()  # ayar.acil iner
    assert s.gorunum()["acil"]["tur"] == "tatbikat" and s.durum_ozeti()["acil_id"] == acil_id
    # Yeni ajana yedek duyuru komutu gitmez.
    assert not sorgu("SELECT * FROM komut WHERE tur = 'duyuru' AND tahta_id = ?", kimlik(basliklar))
    tur()  # acil_id sunucuya gider
    teslim = sorgu("SELECT * FROM acil_teslim")
    assert len(teslim) == 1 and teslim[0]["yol"] == "acil" and teslim[0]["ekran_var"] == 1

    # Acil sürerken uyarılı kapatma ajanda da atlanır.
    from tahta_sunucu import komut, vt

    with vt.islem() as b:
        komut.komut_ekle(b, kimlik(basliklar), "kapat", {"uyari_sn": 60, "neden": "Otomatik kapatma"}, "sistem")
    tur()
    tur()
    sonuc = sorgu("SELECT durum, sonuc FROM komut WHERE tur = 'kapat'")[0]
    assert sonuc == {"durum": "tamam", "sonuc": "Acil yayın sürüyor; otomatik kapatma uygulanmadı."}

    panel.post(f"/acil/{acil_id}/bitir", data={"donus": "/acil"})
    tur()
    assert s.gorunum()["acil"] is None and s.durum_ozeti()["acil_id"] is None


def test_gercek_ajan_durdurulan_yayini_kimligiyle_kaldirir(ajan, panel):
    s, tur, basliklar = ajan
    panel.post("/islem", data={"tur": "duyuru", "tahta": str(kimlik(basliklar)), "metin": "Birinci", "sure_dk": "5"})
    tur()
    tur()  # sonuç bildirilir
    birinci = sorgu("SELECT id FROM duyuru ORDER BY id")[0]["id"]
    assert s.duyuru["id"] == birinci
    panel.post("/islem", data={"tur": "duyuru", "tahta": str(kimlik(basliklar)), "metin": "İkinci", "sure_dk": "5"})
    tur()
    tur()
    assert s.duyuru["metin"] == "İkinci"

    # Birinci yayın durdurulur: ekranda ikinci olduğu için ajan dokunmaz.
    assert panel.post(f"/duyurular/yayin/{birinci}/durdur").status_code == 303
    tur()
    tur()
    assert s.duyuru["metin"] == "İkinci"
    sonuc = sorgu("SELECT sonuc FROM komut WHERE tur = 'duyuru_kaldir'")[0]["sonuc"]
    assert sonuc == "Ekrandaki duyuru başka; dokunulmadı."


def veri_blogu(sayfa: str, kimlik: str) -> str:
    return sayfa.split(f'<script id="{kimlik}" type="application/json">', 1)[1].split("</script>", 1)[0]


def test_panel_kancalari_ve_salt_okunur_plan(panel, tahta):
    kur_ve_gir(panel)
    tahta_ekle(panel, tahta, "Z-01", durum=yeni_ajan_durumu())
    sayfa = panel.get("/").text
    assert '<aside class="yan-menu" id="menu"' in sayfa and 'class="acil-dugme" href="/acil"' in sayfa
    assert '"acil": false' in veri_blogu(sayfa, "bugun-veri")  # Bugün: toplu kilit ve "Sayfayı yenile" bandı için
    liste = panel.get("/tahtalar").text
    assert '"acil": false' in veri_blogu(liste, "pano-veri")  # liste: acil rozetleri için
    form = panel.get("/duyurular/yeni").text
    for kanca in ('id="duyuru-formu"', 'data-kosul="zaman" data-deger="bir_kez"', 'id="hedef-onizleme"',
                  'data-sayac="metin"', 'data-hemen="Şimdi yayımla"'):  # fmt: skip
        assert kanca in form, kanca
    acil = panel.get("/acil").text
    assert 'class="tur-kart" data-tur="acil"' in acil and 'name="tur" value="acil" required>' in acil
    assert "checked" not in acil.split('name="tur" value="acil"')[1].split(">")[0]  # tür varsayılansız

    yanit = panel.post("/duyurular", data={"metin": "Plan", "sure_dk": "3", "zaman": "tekrarli", "siklik": "gunluk",
                                           "tekrar_saat": "08:25", "baslangic": str(date.today()),
                                           "bitis": str(date.today() + timedelta(days=30)), "kime": "tumu"})  # fmt: skip
    assert yanit.status_code == 303
    plan_id = sorgu("SELECT id FROM duyuru_plani")[0]["id"]
    kullanici_ekle(panel, "idareci1")
    gir(panel, "idareci1")
    plan = panel.get(f"/duyurular/plan/{plan_id}").text
    assert '<fieldset class="duz" disabled>' in plan and 'id="duyuru-gonder"' not in plan

    panel.post("/acil/baslat", data={})  # yetkisiz: reddedilir, kayda düşer
    assert sorgu("SELECT COUNT(*) AS n FROM acil_yayin")[0]["n"] == 0
