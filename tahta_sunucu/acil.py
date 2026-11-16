"""Acil durum / tatbikat yayını.

Acil yayın komut değil DURUMDUR: her `/ajan/bekle` yanıtında `ayar.acil` olarak
yeniden hesaplanır (`ajan_gorunumu`). Çevrimdışıyken kaçıran, yeniden başlayan ya da
bitişi duymayan tahta bir sonraki turda kendiliğinden doğru duruma gelir. `acil`
yeteneğini bildirmeyen (eski) ajanlara yedek yol olarak kapatılamaz bir `duyuru`
komutu gider. Kayıtlar silinmez.
"""

from __future__ import annotations

import json
import re

from . import ayar, vt
from . import metin as metin_mod
from .komut import komut_ekle

ACIL_YETENEK = "acil"
ACIL_SURE_DK = (5, 120)
ACIL_VARSAYILAN_DK = 30
BASLIK_EN_UZUN = 120
METIN_EN_UZUN = 1000
SABLON_EN_COK = 10
TURLER = {"acil": "Acil durum", "tatbikat": "Tatbikat"}
BITIS_NEDENI = {"panel": "Panelden", "sure": "Süre doldu", "yenisi": "Yeni yayın"}
YEDEK_ONEK = {"acil": "ACİL DURUM — ", "tatbikat": "TATBİKAT — "}
# 16.11.2026 kararı K4: yayını bütün yöneticiler ve idareciler başlatıp bitirebilir (parola + onay kutusu
# yine istenir). `kullanici.acil_yetki` sütunu eski sürüme dönüş için durur ama okunmaz.
YETKILI_ROLLER = ("yonetici", "idareci")


def yetkili(kullanici) -> bool:
    """Acil/tatbikat yayınını başlatıp bitirebilir mi? (etkin oturumu olan yönetici ya da idareci)"""
    return bool(kullanici) and kullanici["rol"] in YETKILI_ROLLER

# İlk kurulumda kullanılan ÖRNEK şablonlar: mevzuat metni değildir; okulun acil durum
# planına göre Ayarlar'dan düzenlenmelidir.
VARSAYILAN_SABLONLAR = [
    {"kod": "deprem", "ad": "Deprem", "baslik": "DEPREM",
     "metin": "Çök — kapan — tutun. Sarsıntı bitene kadar yerinizden kalkmayınız. Öğretmeninizin yönlendirmesini bekleyiniz."},
    {"kod": "tahliye", "ad": "Tahliye", "baslik": "TAHLİYE",
     "metin": "Öğretmeninizle birlikte, koşmadan ve sakin biçimde sınıfı terk ediniz. Belirlenen toplanma alanına gidiniz."},
    {"kod": "yangin", "ad": "Yangın", "baslik": "YANGIN — TAHLİYE",
     "metin": "Asansör kullanmayınız. Öğretmeninizle birlikte en yakın çıkıştan toplanma alanına gidiniz."},
    {"kod": "iceride_kal", "ad": "Sınıfta kalın", "baslik": "SINIFTA KALINIZ",
     "metin": "Sınıflarınızdan çıkmayınız, kapıyı kapatınız. Yeni bir duyuru gelene kadar öğretmeninizin yönlendirmesini izleyiniz."},
    {"kod": "genel", "ad": "Genel", "baslik": "DİKKAT", "metin": "Öğretmeninizin yönlendirmesini izleyiniz."},
]  # fmt: skip


# ---- yardımcılar ------------------------------------------------------------------------
def yetenekler(tahta) -> list[str]:
    try:
        degerler = json.loads(tahta["durum_json"] or "{}").get("yetenekler") or []
    except (ValueError, AttributeError):
        return []
    return [str(y) for y in degerler if isinstance(y, str)] if isinstance(degerler, list) else []


def ekran_var(durum: dict) -> bool:
    ekranlar = durum.get("ekranlar") if isinstance(durum, dict) else None
    return any(isinstance(e, dict) and e.get("arayuz") not in (None, "yok", "komut") for e in (ekranlar or []))


def baslangic_durumu(tahta, simdi: int) -> str:
    """Yayın başlarken tahtanın durumu: "cevrimdisi", "ekran_yok" ya da "" (ulaşılabilir)."""
    if not tahta["son_gorulme"] or simdi - tahta["son_gorulme"] >= ayar.CEVRIMICI_ESIK_SN:
        return "cevrimdisi"
    try:
        durum = json.loads(tahta["durum_json"] or "{}")
    except ValueError:
        durum = {}
    return "" if ekran_var(durum) else "ekran_yok"


def _yedek_komutlar(b, acil_id: int):
    return b.execute(
        "SELECT * FROM komut WHERE tur = 'duyuru' AND duyuru_id IS NULL AND json_extract(veri_json, '$.acil_id') = ?",
        (acil_id,),
    ).fetchall()


# ---- yaşam döngüsü ----------------------------------------------------------------------
def aktif(b, simdi: int | None = None):
    """Süren yayın satırı ya da None. Süresi geçmiş yayın önce 'sure' nedeniyle kapatılır."""
    simdi = vt.simdi() if simdi is None else simdi
    satirlar = b.execute("SELECT * FROM acil_yayin WHERE bitis IS NULL ORDER BY id DESC").fetchall()
    sonuc = None
    for satir in satirlar:
        if sonuc is None and satir["bitis_plan"] > simdi:
            sonuc = satir
        elif satir["bitis_plan"] <= simdi:
            bitir(b, satir["id"], bitiren="sistem", neden="sure", simdi=simdi)
        else:  # birden çok açık yayın olmamalı; eskisi kapanır
            bitir(b, satir["id"], bitiren="sistem", neden="yenisi", simdi=simdi)
    return sonuc


def baslat(
    b, *, tur: str, sablon: str, baslik: str, metin: str, sure_sn: int, baslatan: str, ip: str = "",
    simdi: int | None = None,
) -> tuple[int, list[int]]:  # fmt: skip
    """Yayını başlatır (sürmekte olanı 'yenisi' nedeniyle bitirir).

    Döndürür: (acil_id, uyandırılacak tahta kimlikleri = bütün onaylı tahtalar).
    Eski ajanlara (durumunda 'acil' yeteneği yok) yedek duyuru komutu yazılır.
    """
    if tur not in TURLER:
        raise ValueError("Yayın türünü seçin.")
    simdi = vt.simdi() if simdi is None else simdi
    uyandir: set[int] = set()
    eski = aktif(b, simdi)
    if eski:
        uyandir.update(bitir(b, eski["id"], bitiren=baslatan, neden="yenisi", simdi=simdi))
    tahtalar = b.execute("SELECT * FROM tahta WHERE durum = 'onayli'").fetchall()
    acil_id = b.execute(
        "INSERT INTO acil_yayin (tur, sablon, baslik, metin, baslangic, bitis_plan, baslatan, ip, hedef_sayisi, "
        "hedef_durum_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            tur, sablon, baslik, metin, simdi, simdi + int(sure_sn), baslatan, ip, len(tahtalar),
            json.dumps({str(t["id"]): baslangic_durumu(t, simdi) for t in tahtalar}),
        ),
    ).lastrowid  # fmt: skip
    eski_ajan = 0
    for t in tahtalar:
        uyandir.add(t["id"])
        if ACIL_YETENEK in yetenekler(t):
            continue
        eski_ajan += 1
        veri = {
            "baslik": YEDEK_ONEK[tur] + baslik,
            "metin": metin,
            "sure_sn": int(sure_sn),
            "kapatilabilir": False,
            "bitis_sunucu": simdi + int(sure_sn),
            "acil_id": acil_id,
        }
        komut_ekle(b, t["id"], "duyuru", veri, baslatan, omur=int(sure_sn), simdi=simdi)
    islem = "ACİL DURUM YAYINI başlatıldı" if tur == "acil" else "Tatbikat yayını başlatıldı"
    ayrinti = f"#{acil_id} {baslik} · {int(sure_sn) // 60} dk · {len(tahtalar)} tahta"
    if eski_ajan:
        ayrinti += f" ({eski_ajan} tahtaya eski ajan için yedek duyuru)"
    vt.kayit_dus(b, baslatan, islem, ayrinti, ip)
    return acil_id, sorted(uyandir)


def bitir(b, acil_id: int, *, bitiren: str, neden: str, simdi: int | None = None, ip: str = "") -> list[int]:
    """Yayını bitirir; yedek yoldaki eski ajanların uyandırılacak kimliklerini döndürür."""
    simdi = vt.simdi() if simdi is None else simdi
    yayin = b.execute("SELECT * FROM acil_yayin WHERE id = ?", (acil_id,)).fetchone()
    if not yayin or yayin["bitis"] is not None:
        return []
    b.execute(
        "UPDATE acil_yayin SET bitis = ?, bitis_nedeni = ?, bitiren = ? WHERE id = ? AND bitis IS NULL",
        (min(simdi, yayin["bitis_plan"]) if neden == "sure" else simdi, neden, bitiren, acil_id),
    )
    uyandir = []
    for k in _yedek_komutlar(b, acil_id):
        if k["durum"] == "bekliyor":
            b.execute(
                "UPDATE komut SET durum = 'iptal', tamamlanma = ?, sonuc = 'Acil yayın bitti.' WHERE id = ?",
                (simdi, k["id"]),
            )
        elif k["durum"] in ("gonderildi", "tamam") and neden != "sure":
            # Süre dolunca eski ajandaki yedek duyuru da aynı anda kendiliğinden kalkar.
            komut_ekle(b, k["tahta_id"], "duyuru_kaldir", {}, bitiren, simdi=simdi)
            uyandir.append(k["tahta_id"])
    tur = "ACİL DURUM YAYINI" if yayin["tur"] == "acil" else "Tatbikat yayını"
    vt.kayit_dus(b, bitiren, f"{tur} bitti", f"#{acil_id} {yayin['baslik']} · {BITIS_NEDENI.get(neden, neden)}", ip)
    return uyandir


def ajan_gorunumu(b, simdi: int | None = None) -> dict | None:
    """`/ajan/bekle` yanıtındaki `ayar.acil`: {"id","tur","baslik","metin","kalan_sn"} ya da None."""
    simdi = vt.simdi() if simdi is None else simdi
    yayin = aktif(b, simdi)
    if not yayin:
        return None
    return {
        "id": yayin["id"],
        "tur": yayin["tur"],
        "baslik": yayin["baslik"],
        "metin": yayin["metin"],
        "kalan_sn": max(0, yayin["bitis_plan"] - simdi),
    }


def teslim_yaz(b, acil_id: int, tahta_id: int, durum: dict, yol: str = "acil", simdi: int | None = None) -> None:
    b.execute(
        "INSERT OR IGNORE INTO acil_teslim (acil_id, tahta_id, ilk_gorulme, ekran_var, yol) VALUES (?, ?, ?, ?, ?)",
        (acil_id, tahta_id, vt.simdi() if simdi is None else simdi, int(ekran_var(durum)), yol),
    )


def yedek_teslim_acil_id(veri: dict) -> int | None:
    """Yedek duyuru komutunun verisinden acil yayın kimliği (yoksa None)."""
    deger = veri.get("acil_id") if isinstance(veri, dict) else None
    return int(deger) if isinstance(deger, int) and not isinstance(deger, bool) else None


# ---- şablonlar ---------------------------------------------------------------------------
def sablonlar(b) -> list[dict]:
    kayitli = vt.ayar_al(b, "acil_sablonlar")
    if not isinstance(kayitli, list):
        return [dict(s) for s in VARSAYILAN_SABLONLAR]
    return [
        {k: str(s.get(k, "")) for k in ("kod", "ad", "baslik", "metin")}
        for s in kayitli
        if isinstance(s, dict) and s.get("ad")
    ][:SABLON_EN_COK]


def sablon_kodu(ad: str, kullanilan: set[str]) -> str:
    kok = re.sub(r"[^a-z0-9]+", "_", metin_mod.katla(ad)).strip("_")[:30] or "sablon"
    kod, sira = kok, 2
    while kod in kullanilan:
        kod, sira = f"{kok}_{sira}", sira + 1
    kullanilan.add(kod)
    return kod


# ---- panel görünümleri ----------------------------------------------------------------------
def teslim_sayilari(b, acil_idler) -> dict[int, int]:
    idler = [int(i) for i in acil_idler]
    if not idler:
        return {}
    isaret = ",".join("?" * len(idler))
    return {
        s["acil_id"]: s["sayi"]
        for s in b.execute(
            f"SELECT acil_id, COUNT(*) AS sayi FROM acil_teslim WHERE acil_id IN ({isaret}) GROUP BY acil_id", idler
        )
    }


def rapor_satirlari(b, yayin, cevrimici_esik: int) -> list[dict]:
    """Rapordaki tahta tablosu: hedefteki ve teslim alan her tahta için bir satır.

    Hedef kümesi ve "neden" sütunu yayın başlarken dondurulan durumdan (`hedef_durum_json`)
    gelir: sonradan açılan ya da eklenen tahta eski raporu değiştirmez. Dondurulmuş durum
    yoksa (boş) bugünkü onaylı tahtalar ve bugünkü durum kullanılır.
    """
    from .hedef import kat_adi

    teslim = {
        s["tahta_id"]: s for s in b.execute("SELECT * FROM acil_teslim WHERE acil_id = ?", (yayin["id"],))
    }
    try:
        donuk = json.loads(yayin["hedef_durum_json"] or "{}")
    except (ValueError, IndexError, KeyError):
        donuk = {}
    donuk = {int(a): str(d) for a, d in donuk.items() if str(a).isdigit()} if isinstance(donuk, dict) else {}
    if donuk:
        idler = sorted(set(donuk) | set(teslim))
        tahtalar = b.execute(
            f"SELECT * FROM tahta WHERE id IN ({','.join('?' * len(idler))}) "
            "ORDER BY derslik COLLATE NOCASE, ad COLLATE NOCASE",
            idler,
        ).fetchall()
    else:
        tahtalar = b.execute(
            "SELECT * FROM tahta WHERE durum = 'onayli' OR id IN (SELECT tahta_id FROM acil_teslim WHERE acil_id = ?) "
            "ORDER BY derslik COLLATE NOCASE, ad COLLATE NOCASE",
            (yayin["id"],),
        ).fetchall()
    bitti = yayin["bitis"] is not None
    satirlar = []
    for t in tahtalar:
        s = teslim.get(t["id"])
        neden = "—"
        if not s:
            ilk = donuk.get(t["id"])
            if ilk == "cevrimdisi":
                neden = "Çevrimdışıydı"
            elif ilk == "ekran_yok":
                neden = "Ekran yardımcısı yok"
            elif bitti:
                neden = "Görüntülendiği kaydedilmedi"
            # Süren yayında (ya da dondurulmuş durum yoksa) bugünkü durum: yayın başladıktan
            # sonra sunucuya hiç bağlanmadıysa çevrimdışıdır.
            elif (t["son_gorulme"] or 0) < yayin["baslangic"] - cevrimici_esik:
                neden = "Çevrimdışıydı"
            elif not ekran_var(json.loads(t["durum_json"] or "{}")):
                neden = "Ekran yardımcısı yok"
        satirlar.append(
            {
                "tahta_id": t["id"],
                "ad": t["ad"],
                "derslik": t["derslik"],
                "bina_kat": " · ".join(p for p in (t["bina"], kat_adi(t["kat"]) if t["kat"] is not None else "") if p),
                "ilk_gorulme": s["ilk_gorulme"] if s else None,
                "gecikme_sn": (s["ilk_gorulme"] - yayin["baslangic"]) if s else None,
                "ekran_var": bool(s["ekran_var"]) if s else None,
                "yol": ("Acil" if s["yol"] == "acil" else "Yedek duyuru") if s else "",
                "neden": neden,
            }
        )
    return satirlar
