"""Tahta numarası (0.21.0): kurulumun sonunda tahtanın ekranında çıkan numara (= tahta.id) panelde görünür, yeni
kaydın adı "Tahta <no>" olur, aynı adlı tahtalar uyarılır ve toplu yeniden adlandırılır. Uydurma veriyle; ETAP'ta
bütün tahtaların makine adı aynıdır ("etap")."""

from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

import pytest
from yardimci import gir, ileti, kimlik, kullanici_ekle, kur_ve_gir, sorgu, tahta_ekle, yeni_ajan_durumu

from tahta_sunucu import metin as metin_mod
from tahta_sunucu import paket, tahta_liste, vt

KOK = Path(__file__).resolve().parent.parent / "tahta_sunucu"
BETIK = (KOK / "statik" / "panel.js").read_text(encoding="utf-8")


def kaydol(panel, tahta, makine: str = "etap") -> int:
    panel.post("/ekle", data={"eylem": "ac"})
    kod = panel.get("/ekle").text.split('class="buyuk-kod">')[1].split("<")[0]
    return tahta.post("/ajan/kaydol", json={"kod": kod, "makine_adi": makine, "surum": "0.20.0"}).json()["tahta_id"]


def ad_yaz(tahta_id: int, ad: str, derslik: str = "") -> None:
    with vt.islem() as b:
        b.execute("UPDATE tahta SET ad = ?, derslik = ? WHERE id = ?", (ad, derslik, tahta_id))


def metin(sayfa: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", sayfa)).split())


@pytest.fixture()
def okul(panel, tahta):
    """Üç onaylı tahta; ikisi eski sürümün verdiği "etap" adını taşır, biri kendi adını."""
    kur_ve_gir(panel)
    kullanici_ekle(panel, "idareci1")
    idler = [kimlik(tahta_ekle(panel, tahta, ad, yeni_ajan_durumu())) for ad in ("etap", "ETAP", "Kimya laboratuvarı")]
    ad_yaz(idler[0], "etap", "D-101")
    return idler


# ---- saf işlevler -----------------------------------------------------------------------------------------
def makine_yaz(tahta_id: int, makine_adi: str) -> None:
    with vt.islem() as b:
        b.execute("UPDATE tahta SET makine_adi = ? WHERE id = ?", (makine_adi, tahta_id))


def test_varsayilan_ad_ve_ayni_ad_kumesi():
    assert tahta_liste.varsayilan_ad(7) == "Tahta 7"
    satirlar = [(1, "etap"), (2, " ETAP "), (3, "Kimya"), (4, ""), (5, ""), (6, "Kimya lab"), (7, "Etap")]
    assert tahta_liste.ayni_adlilar(satirlar) == [1, 2, 7]  # boş ad sayılmaz; büyük/küçük harf ve boşluk farkı yok
    assert tahta_liste.ayni_adlilar([(1, "İzmir"), (2, "izmir")]) == [1, 2]
    assert tahta_liste.ayni_adlilar([]) == []


def test_adlandirilacaklar_yalniz_kurulumdan_gelen_ayni_adlar():
    """İnceleme bulgusu: toplu adlandırma elle verilmiş adı (okulun bilerek verdiği aynı ad ya da kendi "Tahta 12"
    numaralandırması) ezmez; yalnız adı bilgisayar adı ya da "Yeni tahta" olanlara dokunur."""
    satirlar = [
        (1, "etap", "etap"), (2, "ETAP", "etap"),  # kurulumdan: değişir (büyük/küçük harf farkı yok)
        (3, "Konferans salonu", "etap"), (4, "Konferans salonu", "etap"),  # elle, bilerek aynı: değişmez
        (5, "Yeni tahta", "Yeni tahta"), (6, "yeni tahta", ""),  # makine adı boş kayıtlar: değişir
        (7, "Tahta 9", "etap"), (9, "Tahta 9", "etap"),  # elle "Tahta 9" ile 9'un kendi adı: ikisi de değişmez
        (10, "Kimya", "Kimya"),  # kurulumdan ama tek: değişmez
    ]  # fmt: skip
    assert tahta_liste.adlandirilacaklar(satirlar) == [1, 2, 5, 6]
    assert tahta_liste.adlandirilabilir_mi("etap", "ETAP") and not tahta_liste.adlandirilabilir_mi("", "")
    assert not tahta_liste.adlandirilabilir_mi("D-101", "etap")


def test_dogal_sira_tahta_numarasi():
    """İnceleme bulgusu: harf harf sıralamada "Tahta 10" "Tahta 2"den önce geliyordu."""
    adlar = ["Tahta 10", "Tahta 2", "tahta 1", "Çalışma", "Cam", "9/A", "10/A", ""]
    beklenen = ["", "9/A", "10/A", "Cam", "Çalışma", "tahta 1", "Tahta 2", "Tahta 10"]
    assert sorted(adlar, key=metin_mod.dogal_sirala_anahtari) == beklenen
    gruplar = tahta_liste.gruplar([{"id": i, "ad": f"Tahta {i}", "derslik": ""} for i in (10, 2, 11, 1)])
    assert [t["id"] for t in gruplar[0]["tahtalar"]] == [1, 2, 10, 11]
    ayni = tahta_liste.gruplar([{"id": i, "ad": "etap", "derslik": ""} for i in (12, 3)])
    assert [t["id"] for t in ayni[0]["tahtalar"]] == [3, 12]  # ad da eşitse numara sırası


# ---- kayıt ------------------------------------------------------------------------------------------------
def test_yeni_kaydin_adi_tahta_no_makine_adi_ayri_sutunda(panel, tahta):
    kur_ve_gir(panel)
    birinci, ikinci = kaydol(panel, tahta), kaydol(panel, tahta)
    satirlar = {s["id"]: s for s in sorgu("SELECT id, ad, makine_adi, durum FROM tahta")}
    assert satirlar[birinci]["ad"] == f"Tahta {birinci}" and satirlar[ikinci]["ad"] == f"Tahta {ikinci}"
    assert satirlar[birinci]["makine_adi"] == "etap" and satirlar[birinci]["durum"] == "bekliyor"
    kayitlar = [s["kullanici"] for s in sorgu("SELECT kullanici FROM kayit WHERE islem = 'Tahta kaydoldu' ORDER BY id")]
    assert kayitlar == [f"tahta:Tahta {birinci}", f"tahta:Tahta {ikinci}"]


def test_makine_adi_yoksa_da_ad_tahta_no(panel, tahta):
    kur_ve_gir(panel)
    tid = kaydol(panel, tahta, makine="")
    assert sorgu("SELECT ad FROM tahta WHERE id = ?", tid)[0]["ad"] == f"Tahta {tid}"


# ---- numara panelde görünür -------------------------------------------------------------------------------
def test_onay_bandinda_ad_ve_numara(panel, tahta):
    kur_ve_gir(panel)
    tid = kaydol(panel, tahta)
    ad_yaz(tid, "etap")  # 0.20.0 ve öncesinin verdiği ad
    bant = panel.get("/tahtalar").text.split('id="onay-bekleyen"')[1].split("</div>")[0]
    assert f"etap · No {tid}" in bant
    assert "kurulumun sonunda tahtanın ekranında çıkan numaradır" in bant


def test_liste_satirinda_numara(panel, okul):
    sayfa = panel.get("/tahtalar").text
    for tid in okul:
        satir = sayfa.split(f'<tr class="tahta-satir" id="t-{tid}"')[1].split("</tr>")[0]
        assert f'<span class="alt-satir">No {tid} · ' in satir


def test_tahta_sayfasinda_numara(panel, okul):
    tid = okul[0]
    sayfa = panel.get(f"/tahta/{tid}").text
    assert f"<title>etap · No {tid} · Tahta Kontrol</title>" in sayfa
    assert f"<span>etap · No {tid}</span></nav>" in sayfa  # kırıntı
    assert f'<h1>etap <span class="not tahta-no">No {tid}</span>' in sayfa
    bakim = panel.get(f"/tahta/{tid}?sekme=bakim").text
    baglanti = bakim.split('id="baglanti"')[1].split("</section>")[0]
    assert f"<dt>Tahta no</dt><dd>No {tid} " in baglanti
    bilgi = panel.get(f"/tahta/{tid}?sekme=bilgiler").text
    assert f"Bu tahtanın numarası <strong>No {tid}</strong>" in bilgi and 'aria-describedby="ad-ipucu"' in bilgi


def test_ariza_sayfalarinda_numara(panel, okul):
    tid = okul[0]
    sayfa = panel.get("/arizalar").text
    assert f'<option value="{tid}" >etap · No {tid} · D-101</option>' in sayfa
    yanit = panel.post("/arizalar", data={"tahta_id": str(tid), "kategori": "goruntu", "aciklama": ""})
    assert "t=hata" not in yanit.headers.get("location", ""), ileti(yanit)
    liste = metin(panel.get("/arizalar").text)
    assert f"etap · No {tid}" in liste
    ariza_id = sorgu("SELECT id FROM ariza")[0]["id"]
    assert f"etap · No {tid}</a>" in panel.get(f"/ariza/{ariza_id}").text


def test_bugun_cipinde_numara_yalniz_ayni_adda(panel, okul):
    sayfa = panel.get("/").text
    cipler = {int(m.group(1)): m.group(0) for m in re.finditer(r'<a class="cip" href="/tahta/(\d+)".*?</a>', sayfa)}
    assert f'<span class="cip-no">No {okul[0]}</span>' in cipler[okul[0]]
    assert f'<span class="cip-no">No {okul[1]}</span>' in cipler[okul[1]]
    assert "cip-no" not in cipler[okul[2]]


def test_api_durum_adi_degistirmez(panel, okul):
    """Canlı tazeleme adı yazmaz; /api/durum sözlüğüne yeni alan da girmez (numara = var olan `id`)."""
    veri = panel.get("/api/durum").json()
    assert {t["id"]: t["ad"] for t in veri["tahtalar"]}[okul[0]] == "etap"
    assert "cip-ad" not in BETIK.split("function cipYaz")[1].split("function ciz")[0]


# ---- aynı ad: uyarı, reddetme yok -------------------------------------------------------------------------
def test_ayni_ad_kaydedilir_ama_uyarilir(panel, okul):
    yanit = panel.post(f"/tahta/{okul[2]}/kaydet", data={"ad": "Etap", "derslik": ""})
    assert "t=hata" not in yanit.headers["location"]
    assert ileti(yanit) == (
        f"Kaydedildi. Dikkat: bu adı taşıyan 2 tahta daha var (No {okul[0]}, No {okul[1]}); "
        "tahtaları ayırt etmek için farklı bir ad verin."
    )
    assert sorgu("SELECT ad FROM tahta WHERE id = ?", okul[2])[0]["ad"] == "Etap"
    tek = panel.post(f"/tahta/{okul[2]}/kaydet", data={"ad": "Fizik laboratuvarı", "derslik": ""})
    assert ileti(tek) == "Kaydedildi."


def test_onayda_ayni_ad_uyarisi(panel, tahta, okul):
    tid = kaydol(panel, tahta)
    yanit = panel.post(f"/tahta/{tid}/kaydet", data={"ad": "etap", "derslik": "", "eylem": "onayla"})
    assert ileti(yanit).startswith("etap onaylandı; artık komut alır. Dikkat: bu adı taşıyan 2 tahta daha var")
    assert sorgu("SELECT durum FROM tahta WHERE id = ?", tid)[0]["durum"] == "onayli"


def test_kaldirilan_tahta_ayni_ad_sayilmaz(panel, okul):
    panel.post(f"/tahta/{okul[1]}/kaydet", data={"eylem": "sil"})
    yanit = panel.post(f"/tahta/{okul[0]}/kaydet", data={"ad": "etap", "derslik": "D-101"})
    assert ileti(yanit) == "Kaydedildi."
    assert 'id="ayni-ad"' not in panel.get("/tahtalar").text


# ---- toplu yeniden adlandırma -----------------------------------------------------------------------------
def test_ayni_ad_bandi_yalniz_yoneticide(panel, okul):
    sayfa = panel.get("/tahtalar").text
    bant = sayfa.split('id="ayni-ad"')[1].split("</div>")[0]
    assert "Aynı adı taşıyan 2 tahta var." in bant
    form = bant.split("<form")[1].split("</form>")[0]
    assert 'action="/tahtalar/adlandir"' in form and 'id="ayni-ad-formu"' in form
    # Onaylı düğme kalıbı: JS'siz gönderilmez; formda gönder düğmesi ve `eylem` alanı yoktur (onay penceresi ekler).
    assert 'type="button" data-onay="adlandir" data-onay-ad="2"' in form
    assert 'type="submit"' not in form and 'name="eylem"' not in form and "<input" not in form
    assert "<noscript>" in bant
    assert "adlandir: {" in BETIK and 'deger: "adlandir"' in BETIK
    gir(panel, "idareci1")
    assert 'id="ayni-ad"' not in panel.get("/tahtalar").text


def test_toplu_adlandirma_yalniz_ayni_adlilari_degistirir(panel, tahta, okul):
    bekleyen = kaydol(panel, tahta)
    ad_yaz(bekleyen, "etap")
    once = {s["id"]: s for s in sorgu("SELECT * FROM tahta")}
    yanit = panel.post("/tahtalar/adlandir", data={"eylem": "adlandir"})
    assert ileti(yanit) == "3 tahta “Tahta <no>” biçiminde yeniden adlandırıldı. Derslikler ve elle verilen adlar değişmedi."
    sonra = {s["id"]: s for s in sorgu("SELECT * FROM tahta")}
    for tid in (okul[0], okul[1], bekleyen):
        assert sonra[tid]["ad"] == f"Tahta {tid}"
        degisen = {a for a in once[tid].keys() if once[tid][a] != sonra[tid][a]}
        assert degisen == {"ad"}  # derslik, durum, makine adı, nitelikler aynı
    assert sonra[okul[0]]["derslik"] == "D-101" and sonra[okul[0]]["makine_adi"] == "etap"
    assert sonra[okul[2]] == once[okul[2]]
    kayit = sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Aynı adlı tahtalar yeniden adlandırıldı'")
    assert kayit == [{"ayrinti": "3 tahta"}]
    assert 'id="ayni-ad"' not in panel.get("/tahtalar").text
    ikinci = panel.post("/tahtalar/adlandir", data={"eylem": "adlandir"})
    assert ileti(ikinci) == "Kurulumdan kalan aynı adı taşıyan tahta yok; hiçbir ad değişmedi."


def test_toplu_adlandirma_eylemsiz_ve_idarecide_hicbir_sey_yapmaz(panel, okul):
    once = sorgu("SELECT id, ad FROM tahta ORDER BY id")
    yanit = panel.post("/tahtalar/adlandir", data={})
    assert "t=hata" in yanit.headers["location"]
    gir(panel, "idareci1")
    yanit = panel.post("/tahtalar/adlandir", data={"eylem": "adlandir"})
    assert "t=hata" in yanit.headers["location"] and "yönetici yetkisi" in ileti(yanit)
    assert sorgu("SELECT id, ad FROM tahta ORDER BY id") == once


# ---- kurulum betiği ve Tahta ekle sayfası -----------------------------------------------------------------
def test_kurulum_betigi_tahta_noyu_cerceveli_basar():
    betik = paket.kurulum_betigi("https://10.0.0.5:8788", "ab" * 32).decode("utf-8")
    betik.encode("ascii")  # kur.sh iletileri bilerek ASCII (kural 9)
    satir = '  TAHTA NO: $TAHTA_NO  -> Bu numarayi sinifin adiyla birlikte not edin.'
    assert betik.count(satir) == 1
    kayit = betik.index("/usr/bin/tahta-ajan kaydol")
    assert kayit < betik.index(satir) < betik.index("Kurulum tamamlandi.")
    cerceve = betik.split(satir)[0].rsplit("\n", 2)[-2]
    assert set(cerceve.strip().strip('echo "')) == {"="}
    assert '"" | *[!0-9]*) ;;' in betik  # numara yoksa ya da sayı değilse hiçbir şey basılmaz


@pytest.mark.parametrize(
    ("icerik", "beklenen"),
    [('{"tahta_id": 7, "anahtar": "x"}', "7"), ("{}", ""), ("bozuk", ""), (None, "")],
)
def test_kurulum_betiginin_numara_okuyucusu(tmp_path, icerik, beklenen):
    """Betikteki python3 parçası ajan.json'dan yalnız sayıyı okur; dosya yoksa ya da bozuksa sessiz geçer."""
    betik = paket.kurulum_betigi("https://10.0.0.5:8788", "ab" * 32).decode("utf-8")
    parca = betik.split("TAHTA_NO=\"$(python3 -c '")[1].split("' 2>/dev/null")[0]
    yol = tmp_path / "ajan.json"
    if icerik is not None:
        yol.write_text(icerik, encoding="utf-8")
    parca = parca.replace("/etc/tahta-kontrol/ajan.json", yol.as_posix())
    sonuc = subprocess.run([sys.executable, "-I", "-c", parca], capture_output=True, text=True, timeout=30)
    assert sonuc.returncode == 0 and sonuc.stdout.strip() == beklenen


def test_ekle_sayfasinda_numara_notu(panel):
    kur_ve_gir(panel)
    sayfa = metin(panel.get("/ekle").text)
    assert "Tahta numarasını not edin." in sayfa
    assert "panelde her tahtanın yanında aynı numara görünür" in sayfa


# ---- inceleme düzeltmeleri ----------------------------------------------------------------------------------
def test_liste_ve_onay_bekleyen_numara_sirasiyla(panel):
    """İnceleme bulgusu: "Tahta 10" listede "Tahta 2"den önce çıkıyordu; onay bekleyenler adın abece sırasındaydı."""
    kur_ve_gir(panel)
    with vt.islem() as b:
        for i in range(1, 15):  # uydurma kayıtlar: 1–11 onaylı "Tahta <no>", 12–14 onay bekliyor
            durum = "onayli" if i <= 11 else "bekliyor"
            ad = {12: "zeytin", 13: "armut", 14: "Tahta 14"}.get(i, f"Tahta {i}")
            b.execute(
                "INSERT INTO tahta (id, ad, anahtar_ozet, durum, kayit_zamani, makine_adi) VALUES (?, ?, ?, ?, ?, 'etap')",
                (i, ad, f"ozet{i}", durum, vt.simdi()),
            )
    sayfa = panel.get("/tahtalar").text
    assert [int(i) for i in re.findall(r'<tr class="tahta-satir" id="t-(\d+)"', sayfa)] == list(range(1, 12))
    bant = sayfa.split('id="onay-bekleyen"')[1].split("</ul>")[0]
    assert [int(i) for i in re.findall(r'href="/tahta/(\d+)\?sekme=bilgiler"', bant)] == [12, 13, 14]


def test_onay_penceresi_ve_secim_numarayi_tasir(panel, okul):
    """İnceleme bulgusu: aynı adlı tahtalar Kapat/Yeniden başlat onayında ve seçim kutusunun adında ayırt edilmiyordu."""
    sayfa = panel.get("/tahtalar").text
    for tid, ad in zip(okul[:2], ("etap", "ETAP"), strict=True):
        acilis = sayfa.split(f'<tr class="tahta-satir" id="t-{tid}"')[1].split(">")[0]
        satir = sayfa.split(f'<tr class="tahta-satir" id="t-{tid}"')[1].split("</tr>")[0]
        assert f'data-ad="{ad} · No {tid}"' in acilis
        assert f'<span class="gizli">{ad} · No {tid} seç</span>' in satir
        assert f'aria-label="{ad} · No {tid} için diğer işlemler"' in satir
        for onay in ("kapat", "yeniden_baslat"):
            assert f'data-onay="{onay}" data-tek="{onay}:{tid}" data-onay-ad="{ad} · No {tid}"' in satir, onay
    tahta_sayfasi = panel.get(f"/tahta/{okul[0]}").text
    assert f'data-onay="kapat" data-onay-ad="etap · No {okul[0]}"' in tahta_sayfasi


def test_toplu_adlandirma_elle_verilen_ayni_adlara_dokunmaz(panel, okul):
    """İnceleme bulgusu: okulun bilerek verdiği aynı adlar (iki "Konferans salonu") geri alınamaz biçimde eziliyordu."""
    panel.post(f"/tahta/{okul[2]}/kaydet", data={"ad": "Konferans salonu", "derslik": ""})
    panel.post(f"/tahta/{okul[1]}/kaydet", data={"ad": "Konferans salonu", "derslik": ""})
    # Yalnız elle verilmiş aynı adlar kaldı ("etap" artık tek): bant çıkmaz, işlem hiçbir şeyi değiştirmez.
    assert 'id="ayni-ad"' not in panel.get("/tahtalar").text
    once = sorgu("SELECT id, ad FROM tahta ORDER BY id")
    yanit = panel.post("/tahtalar/adlandir", data={"eylem": "adlandir"})
    assert ileti(yanit) == "Kurulumdan kalan aynı adı taşıyan tahta yok; hiçbir ad değişmedi."
    assert sorgu("SELECT id, ad FROM tahta ORDER BY id") == once


def test_toplu_adlandirma_yeni_cakismayi_sabit_noktaya_kadar_cozer(panel, okul):
    """İnceleme bulgusu: verilen "Tahta <no>" adı, adını kurulumdan alan başka bir tahtayla çakışınca ikinci tıklama
    gerekiyordu. Üçüncü tahtanın bilgisayar adı (uydurma) ilk tahtanın varsayılan adıyla aynı."""
    birinci, ikinci, ucuncu = okul
    ad_yaz(ucuncu, f"Tahta {birinci}")
    makine_yaz(ucuncu, f"tahta {birinci}")  # adı kurulumdan (bilgisayar adından) gelmiş sayılır
    assert "Aynı adı taşıyan 2 tahta var." in panel.get("/tahtalar").text  # şimdilik yalnız iki "etap"
    yanit = panel.post("/tahtalar/adlandir", data={"eylem": "adlandir"})
    assert ileti(yanit) == "3 tahta “Tahta <no>” biçiminde yeniden adlandırıldı. Derslikler ve elle verilen adlar değişmedi."
    assert {s["id"]: s["ad"] for s in sorgu("SELECT id, ad FROM tahta")} == {i: f"Tahta {i}" for i in okul}
    assert 'id="ayni-ad"' not in panel.get("/tahtalar").text
    assert sorgu("SELECT ayrinti FROM kayit WHERE islem = 'Aynı adlı tahtalar yeniden adlandırıldı'") == [{"ayrinti": "3 tahta"}]


def test_toplu_adlandirma_elle_verilen_tahta_no_adini_ezmez_kalan_cakismayi_soyler(panel, okul):
    """İnceleme bulgusu: okul kendi numaralandırmasıyla bir tahtaya "Tahta <başka no>" demişse toplu adlandırma onu
    ezmez (zincirleme bozulma yok); oluşan çakışma iletide numaralarıyla söylenir."""
    birinci, ikinci, ucuncu = okul
    panel.post(f"/tahta/{ucuncu}/kaydet", data={"ad": f"Tahta {birinci}", "derslik": ""})
    yanit = panel.post("/tahtalar/adlandir", data={"eylem": "adlandir"})
    assert ileti(yanit) == (
        "2 tahta “Tahta <no>” biçiminde yeniden adlandırıldı. Derslikler ve elle verilen adlar değişmedi. "
        f"Dikkat: adı hâlâ aynı olan 2 tahta var (No {birinci}, No {ucuncu}); elle verilen ad değiştirilmedi, "
        "birini kendi sayfasının Bilgiler sekmesinden yeniden adlandırın."
    )
    assert sorgu("SELECT ad FROM tahta WHERE id = ?", ucuncu)[0]["ad"] == f"Tahta {birinci}"
    assert sorgu("SELECT ad FROM tahta WHERE id = ?", ikinci)[0]["ad"] == f"Tahta {ikinci}"
    # Kalan çakışma elle verilmiş adladır: bant yeniden çıkmaz (düğme onu çözemez).
    assert 'id="ayni-ad"' not in panel.get("/tahtalar").text
