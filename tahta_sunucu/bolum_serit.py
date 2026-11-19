"""Bölüm sekme şeritlerinin TEK tanımı (0.19.0, FastAPI'siz, saf).

Yoklama, Kişiler ve anahtarlar, Program, Duyurular, Acil durum ve Tahtalar bölümlerinin sayfa içi sekme şeridi
buradan çıkar; çizim `sablonlar/_serit.html`'dedir. Şablona ya da `web.py`'ye ikinci bir sekme listesi yazılmaz.

Şerit YALNIZ görünümdür: yetki denetimi uçlardadır. Rolle gizlenen sekme görünümde hiç dönmez (CSS ile gizlenmez).
Etkin sekmeyi şablon verir (sayfa hangi sekmeyse o anahtar); istek yolundan çıkarılmaz, çünkü aynı şablon başka
uçta yeniden çizilir (POST /duyurular 400, POST /acil/baslat 400, POST /program/gecmis/{id}/geri-yukle).

Sekme: {"anahtar", "ad", "yol", "rol"?, "sayi"?, "sayi_eki"?, "dis"?}
  rol       "yonetici" ise yalnız yöneticiye çizilir.
  sayi      rozet sayısının `sayilar` sözlüğündeki anahtarı; `sayi_eki` rozetin ekran okuyucu eki.
  dis       başka bölüme giden bağlantı (↗); hiçbir zaman etkin olmaz.
"""

from __future__ import annotations

YONETICI = "yonetici"

SERITLER: dict[str, dict] = {
    "yoklama": {
        "etiket": "Yoklama bölümleri",
        "kumeler": [
            [
                {"anahtar": "gunluk", "ad": "Günlük", "yol": "/yoklama"},
                {"anahtar": "sube", "ad": "Şube defteri", "yol": "/yoklama/sube"},
                {"anahtar": "mazeret", "ad": "Mazeret ve izin", "yol": "/yoklama/mazeret"},
                {"anahtar": "gir", "ad": "Panelden gir", "yol": "/yoklama/gir"},
                {"anahtar": "icmal", "ad": "Devamsızlık icmali", "yol": "/yoklama/icmal"},
            ],
            [
                {"anahtar": "ayarlar", "ad": "Yoklama ayarları", "yol": "/ayarlar/yoklama", "rol": YONETICI,
                 "dis": "Ayarlar bölümüne gider"},
            ],
        ],
    },
    "kisiler": {
        "etiket": "Kişiler ve anahtarlar bölümü",
        "kumeler": [
            [
                {"anahtar": "ogrenciler", "ad": "Öğrenciler", "yol": "/ogrenciler"},
                {"anahtar": "ogretmenler", "ad": "Öğretmenler ve PIN", "yol": "/ogretmenler"},
                {"anahtar": "usb", "ad": "USB anahtarlar", "yol": "/usb-anahtarlar"},
            ],
        ],
    },
    "program": {
        "etiket": "Program bölümleri",
        "kumeler": [
            [
                {"anahtar": "gun", "ad": "Günü önizle", "yol": "/program/gun"},
                {"anahtar": "zil", "ad": "Zil saatleri", "yol": "/program?bolum=zil"},
                {"anahtar": "derslik", "ad": "Derslik programları", "yol": "/program?bolum=derslik"},
                {"anahtar": "ogretmen_program", "ad": "Öğretmen programı", "yol": "/ogretmen-programi", "rol": YONETICI},
            ],
            [
                {"anahtar": "kurallar", "ad": "Kurallar", "yol": "/program?bolum=kurallar"},
                {"anahtar": "istisnalar", "ad": "İstisnalar", "yol": "/program?bolum=istisnalar"},
                {"anahtar": "uyarilar", "ad": "Uyarılar", "yol": "/program/uyarilar", "sayi": "uyari",
                 "sayi_eki": "boş ders uyarısı"},
            ],
            [
                {"anahtar": "aktar", "ad": "İçe aktar", "yol": "/program/aktar", "rol": YONETICI},
                {"anahtar": "gecmis", "ad": "Önceki programlar", "yol": "/program/gecmis", "rol": YONETICI},
            ],
        ],
    },
    "duyurular": {
        "etiket": "Duyurular bölümü",
        "kumeler": [
            [
                {"anahtar": "liste", "ad": "Duyurular ve planlar", "yol": "/duyurular"},
                {"anahtar": "yeni", "ad": "Yeni duyuru", "yol": "/duyurular/yeni"},
            ],
        ],
    },
    "acil": {
        "etiket": "Acil durum bölümleri",
        "kumeler": [
            [
                {"anahtar": "baslat", "ad": "Yayın başlat", "yol": "/acil"},
                {"anahtar": "gecmis", "ad": "Geçmiş ve raporlar", "yol": "/acil?sekme=gecmis"},
            ],
            [
                {"anahtar": "sablonlar", "ad": "Şablonlar", "yol": "/acil?sekme=sablonlar", "rol": YONETICI},
            ],
        ],
    },
    "tahtalar": {
        "etiket": "Tahtalar bölümü",
        "kumeler": [
            [
                {"anahtar": "tahtalar", "ad": "Tahtalar", "yol": "/tahtalar"},
                {"anahtar": "arizalar", "ad": "Arızalar", "yol": "/arizalar", "sayi": "ariza", "sayi_eki": "süren arıza"},
                {"anahtar": "envanter", "ad": "Envanter", "yol": "/envanter"},
            ],
            [
                {"anahtar": "gruplar", "ad": "Gruplar", "yol": "/gruplar", "rol": YONETICI},
                {"anahtar": "csv", "ad": "CSV ile içe/dışa aktar", "yol": "/tahtalar/ice-aktar", "rol": YONETICI},
                {"anahtar": "ekle", "ad": "Ajan kurulum paketi", "yol": "/ekle", "rol": YONETICI},
            ],
        ],
    },
}


def _gorunur(sekme: dict, rol: str | None) -> bool:
    return not sekme.get("rol") or sekme["rol"] == rol


def gorunum(ad: str, rol: str | None, etkin: str | None, sayilar: dict | None = None) -> dict:
    """Role göre süzülmüş şerit: {"etiket", "kumeler": [[{"anahtar","ad","yol","etkin","sayi","sayi_eki","dis"}]]}.

    Rolle gizlenen sekme hiç dönmez; boş kalan küme düşer (ayraç yalnız iki dolu küme arasında çizilir). `etkin`
    rolle gizlenen, bilinmeyen ya da dış bir sekmenin anahtarıysa şeridin İLK sekmesi etkin olur (idareci yönetici
    sayfasını adresle açarsa). Dönen sekmelerde tam bir tane `etkin` vardır.
    """
    tanim = SERITLER[ad]
    sayilar = sayilar or {}
    kumeler = []
    for kume in tanim["kumeler"]:
        sekmeler = []
        for sekme in kume:
            if not _gorunur(sekme, rol):
                continue
            try:
                sayi = max(0, int(sayilar.get(sekme.get("sayi"), 0) or 0)) if sekme.get("sayi") else 0
            except (TypeError, ValueError):
                sayi = 0
            sekmeler.append({
                "anahtar": sekme["anahtar"],
                "ad": sekme["ad"],
                "yol": sekme["yol"],
                "etkin": False,
                "sayi": sayi,
                "sayi_eki": sekme.get("sayi_eki", ""),
                "dis": sekme.get("dis", ""),
            })
        if sekmeler:
            kumeler.append(sekmeler)
    secilebilir = [s for kume in kumeler for s in kume if not s["dis"]]
    secilen = next((s for s in secilebilir if s["anahtar"] == etkin), None) or (secilebilir[0] if secilebilir else None)
    if secilen:
        secilen["etkin"] = True
    return {"etiket": tanim["etiket"], "kumeler": kumeler}


def sayfa_onekleri(ad: str) -> list[str]:
    """Şeridin (dış bağlantı olmayan) sekmelerinin sorgusuz yolları, tekrarsız ve tanım sırasıyla."""
    yollar: list[str] = []
    for kume in SERITLER[ad]["kumeler"]:
        for sekme in kume:
            if sekme.get("dis"):
                continue
            yol = sekme["yol"].split("?", 1)[0]
            if yol not in yollar:
                yollar.append(yol)
    return yollar
