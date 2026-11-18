"""Testlerde ortak yardımcılar (uydurma veriyle). conftest.py'deki fikstürlerle birlikte kullanılır."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")
PAROLA = "gizli-parola"
# Denetim haneleri tutan UYDURMA numara (gerçek kişiye ait değildir; algoritmayla üretildi).
SAHTE_TC = "12345678950"


def an(gun: int, saat: int, dakika: int = 0, saniye: int = 0, ay: int = 11, yil: int = 2026) -> datetime:
    return datetime(yil, ay, gun, saat, dakika, saniye, tzinfo=TZ)


def kur_ve_gir(panel) -> None:
    panel.post(
        "/kurulum",
        data={"okul_adi": "Örnek Anadolu Lisesi", "gorunen_ad": "Deneme Yönetici", "ad": "yonetici",
              "parola": PAROLA, "parola2": PAROLA},
    )  # fmt: skip
    gir(panel, "yonetici")


def gir(panel, ad: str, parola: str = PAROLA) -> None:
    panel.cookies.clear()
    yanit = panel.post("/giris", data={"ad": ad, "parola": parola})
    assert yanit.status_code == 303 and "tk_oturum" in panel.cookies, yanit.headers.get("location")


def kullanici_ekle(panel, ad: str, rol: str = "idareci") -> None:
    panel.post("/kullanicilar", data={"eylem": "ekle", "ad": ad, "gorunen_ad": ad.title(), "parola": PAROLA, "rol": rol})


def ileti(yanit) -> str:
    """Sunucu iletisi: yönlendirmede adresteki `m`, aynı yanıtta yeniden çizilen sayfada ileti bandı."""
    if "location" in yanit.headers:
        return parse_qs(urlsplit(yanit.headers["location"]).query).get("m", [""])[0]
    bant = re.search(r'<div class="bant(?: hata)?" role="(?:alert|status)"[^>]*>(.*?)</div>', yanit.text, re.S)
    if not bant:
        return ""
    return html.unescape(re.sub(r"<[^>]+>", "", bant.group(1)).replace("Hata: ", "", 1)).strip()


def ayar_sayfasi(panel, bolum: str) -> str:
    """Ayarlar'ın bir bölüm sayfasının HTML'i (0.16.0: /ayarlar/<bölüm>; `panel` yönlendirme izlemez)."""
    yanit = panel.get(f"/ayarlar/{bolum}")
    assert yanit.status_code == 200, (bolum, yanit.status_code, yanit.headers.get("location"))
    return yanit.text


def tahta_ekle(panel, tahta, ad: str = "Tahta", durum: dict | None = None, surum: str = "0.3.0", **alanlar) -> dict:
    """Kaydolur, onaylar, bir kez bekle çağırır; ajan başlıklarını döndürür. alanlar: bina, kat, duzey, devre…"""
    panel.post("/ekle", data={"eylem": "ac"})
    kod = panel.get("/ekle").text.split('class="buyuk-kod">')[1].split("<")[0]
    veri = tahta.post("/ajan/kaydol", json={"kod": kod, "makine_adi": "etap", "surum": surum}).json()
    basliklar = {"X-Tahta-Id": str(veri["tahta_id"]), "X-Tahta-Anahtar": veri["anahtar"]}
    form = {"ad": ad, "derslik": "", "eylem": "onayla"}
    if alanlar:
        form["alanlar"] = "1"
        form.update(alanlar)
    yanit = panel.post(f"/tahta/{veri['tahta_id']}/kaydet", data=form)
    assert "t=hata" not in yanit.headers["location"], ileti(yanit)
    bekle(tahta, basliklar, durum if durum is not None else {"kilitli": False}, surum=surum)
    return basliklar


def bekle(tahta, basliklar, durum: dict | None = None, sonuclar=None, surum: str = "0.3.0") -> dict:
    govde: dict = {"surum": surum, "bekle": 0}
    if durum is not None:
        govde["durum"] = durum
    if sonuclar:
        govde["sonuclar"] = sonuclar
    yanit = tahta.post("/ajan/bekle", headers=basliklar, json=govde)
    assert yanit.status_code == 200, yanit.text
    return yanit.json()


def kimlik(basliklar) -> int:
    return int(basliklar["X-Tahta-Id"])


def sorgu(sql: str, *arg):
    from tahta_sunucu import vt

    with vt.islem() as b:
        return [dict(s) for s in b.execute(sql, arg).fetchall()]


def yeni_ajan_durumu(**ek) -> dict:
    return {"kilitli": False, "yetenekler": ["acil", "duyuru_id"], "ekranlar": [{"arayuz": "gtk3"}], **ek}


def plan_formu(**alanlar) -> dict:
    form = {"baslik": "Günaydın", "metin": "Ders başlamadan telefonlarınızı kapatınız.", "sure_dk": "3",
            "kapatilabilir": "1", "kime": "tumu"}  # fmt: skip
    form.update(alanlar)
    return form


def komut_verisi(satir) -> dict:
    return json.loads(satir["veri_json"])


# ---- zil saatleri (0.10.0: /program/zil/elle kaldırıldı; testler zil düzenini doğrudan kurar) ----------------
def zil_satirlari(form: dict) -> list[tuple]:
    """Eski "elle giriş" formundan haftalık satırlar [(gun, devre, devre_adi, no, bas, bit)] (yalnız testler için).

    form: devre_adi, ilk_ders, ders_sayisi, ders_dk, teneffus_dk, ogle_sonra (0 = yok), ogle_dk, gunler."""
    from tahta_sunucu import program

    devre_adi = form.get("devre_adi") or "Normal"
    devre = program.devre_kimligi(devre_adi)
    imlec = program.dk(form["ilk_ders"])
    ogle_sonra, ogle_dk = int(form.get("ogle_sonra") or 0), int(form.get("ogle_dk") or 0)
    satirlar = []
    for no in range(1, int(form["ders_sayisi"]) + 1):
        bitis = imlec + int(form["ders_dk"])
        for gun in sorted({int(g) for g in form["gunler"]}):
            satirlar.append((gun, devre, devre_adi, no, program.saat_metni(imlec), program.saat_metni(bitis)))
        imlec = bitis + (ogle_dk if ogle_sonra and no == ogle_sonra else int(form["teneffus_dk"]))
    return satirlar


def zil_kur(satirlar) -> None:
    """Haftalık satırlardan zil düzenini kurar: çizelgeler + haftalık düzen + ders_saati (ilk taşımayla aynı yol)."""
    from tahta_sunucu import cizelge, vt

    with vt.islem() as b:
        b.execute("DELETE FROM zil_haftalik")
        b.execute("DELETE FROM zil_cizelgesi WHERE id NOT IN (SELECT cizelge_id FROM zil_tarihli WHERE cizelge_id IS NOT NULL)")
        b.execute("DELETE FROM ders_saati")
        b.executemany("INSERT INTO ders_saati (gun, devre, devre_adi, ders_no, baslangic, bitis) VALUES (?, ?, ?, ?, ?, ?)",
                      list(satirlar))  # fmt: skip
        vt.ayar_yaz(b, "zil_tasima_bekliyor", True)
        cizelge.ilk_tasima(b)
        cizelge.haftalik_yaz(b)


def zil_elle(form: dict) -> str:
    """Eski `/program/zil/elle` (eylem=uret) karşılığı: seçili günlerde o devrenin satırları yeniden yazılır."""
    from tahta_sunucu import program, vt

    yeni = zil_satirlari(form)
    devre = yeni[0][1]
    gunler = {s[0] for s in yeni}
    with vt.islem() as b:
        eski = [s for s in program.ders_saatleri_oku(b) if not (s[1] == devre and s[0] in gunler)]
    zil_kur(eski + yeni)
    return "Zil saatleri kaydedildi."
