"""Tahta arıza kayıtları (A6): panelden ya da tahtadan açılır, durumu izlenir, silinmez.

Açıklama serbest metindir: 300 karakter sınırı, denetim karakterleri atılır, T.C. kimlik
numarasına benzeyen sayı reddedilir (panel) ya da metin kaydedilmez (tahta; kayıt yine
alınır ki tahtanın kuyruğu tıkanmasın). Tahtada arıza metni hiçbir zaman gösterilmez.
"""

from __future__ import annotations

import re
import unicodedata

from . import guvenlik, vt

ARIZA_KATEGORI = {
    "dokunmatik": "Dokunmatik çalışmıyor / kayıyor",
    "goruntu": "Görüntü sorunu",
    "ses": "Ses yok / bozuk",
    "kalem": "Kalem / uzaktan kumanda",
    "ag": "Ağ / internet yok",
    "yazilim": "Program ya da hesap sorunu",
    "acilis": "Açılmıyor / geç açılıyor",  # tahtadan bildirilemez; yalnız panel
    "fiziksel": "Fiziksel hasar (kırık, kablo, bağlantı)",
    "diger": "Diğer",
}
TAHTADAN_KATEGORI = [k for k in ARIZA_KATEGORI if k != "acilis"]
ARIZA_DURUM = {"acik": "Açık", "inceleniyor": "İnceleniyor", "cozuldu": "Çözüldü", "iptal": "İptal"}
GECISLER = {
    "acik": ("inceleniyor", "cozuldu", "iptal"),
    "inceleniyor": ("acik", "cozuldu", "iptal"),
    "cozuldu": ("acik",),
    "iptal": (),
}
SURUYOR = ("acik", "inceleniyor")
METIN_EN_UZUN = 300
TAHTADAN_EN_COK = 10
OTURUM_SINIFLARI = ("etapadmin", "ogretmen", "ogrenci", "kisisel", "yok")
KAYNAK_ADI = {"tahta": "Tahtadan", "panel": "Panelden"}
OTURUM_KISA = {"etapadmin": "yönetici hesabı", "ogretmen": "öğretmen hesabı", "ogrenci": "öğrenci hesabı",
               "kisisel": "kişisel hesap", "yok": "oturum yok"}  # fmt: skip
YEREL_ID = re.compile(r"^[0-9a-f]{8,32}$")
TC_ILETISI_TAHTA = "[Açıklama T.C. kimlik numarasına benzeyen sayı içerdiği için kaydedilmedi.]"
YETENEK = "ariza"


def temizle(metin) -> str:
    """Denetim karakterlerini atar (satır sonu boşluğa döner), boşlukları sadeleştirir, 300'e keser."""
    duz = "".join(" " if c in "\r\n\t" else c for c in str(metin or "") if unicodedata.category(c)[0] != "C" or c in "\r\n\t")
    return " ".join(duz.split())[:METIN_EN_UZUN]


def kaynak_metni(satir) -> str:
    if satir["kaynak"] == "tahta":
        sinif = OTURUM_KISA.get(satir["oturum_sinifi"] or "", "")
        return "Tahtadan" + (f" · {sinif}" if sinif else "")
    return f"Panelden · {satir['bildiren_adi'] if 'bildiren_adi' in satir.keys() and satir['bildiren_adi'] else satir['bildiren']}"


def _hareket(b, ariza_id: int, kullanici: str, eski: str, yeni: str, not_metni: str = "", zaman: int | None = None):
    b.execute(
        "INSERT INTO ariza_hareket (ariza_id, zaman, kullanici, eski_durum, yeni_durum, not_metni) VALUES (?, ?, ?, ?, ?, ?)",
        (ariza_id, vt.simdi() if zaman is None else zaman, kullanici, eski, yeni, not_metni[:METIN_EN_UZUN]),
    )


def panelden_ac(b, tahta_id: int, kategori: str, aciklama: str, kullanici: str, ip: str = "") -> int:
    """Panelden kayıt; hata: ValueError (ileti; ret kaydını çağıran ayrı işlemle düşer). Kimliği döndürür."""
    if kategori not in ARIZA_KATEGORI:
        raise ValueError("Arıza türünü seçin.")
    aciklama = temizle(aciklama)
    if guvenlik.tc_kimlik_var(aciklama):
        raise ValueError(guvenlik.TC_KIMLIK_ILETISI)
    tahta = b.execute("SELECT id, ad FROM tahta WHERE id = ? AND durum = 'onayli'", (tahta_id,)).fetchone()
    if not tahta:
        raise ValueError("Tahta bulunamadı.")
    simdi = vt.simdi()
    imlec = b.execute(
        "INSERT INTO ariza (tahta_id, kaynak, yerel_id, kategori, aciklama, bildiren, oturum_sinifi, durum, olusturma, guncelleme) "
        "VALUES (?, 'panel', NULL, ?, ?, ?, '', 'acik', ?, ?)",
        (tahta_id, kategori, aciklama, kullanici, simdi, simdi),
    )
    _hareket(b, imlec.lastrowid, kullanici, "", "acik", "", simdi)
    vt.kayit_dus(b, kullanici, "Arıza kaydı açıldı", f"#{imlec.lastrowid} · {tahta['ad']} · {ARIZA_KATEGORI[kategori]}", ip)
    return imlec.lastrowid


def tahtadan_al(b, tahta, liste, ip: str = "") -> list[str]:
    """`/ajan/bekle` gövdesindeki `arizalar` (≤ 10). Yazılan ya da zaten var olan yerel_id'ler döner.

    Bilinmeyen kategori (ve tahtadan gelemeyecek `acilis`) `diger` olarak, açıklamanın başına
    "[kategori: x]" eklenerek kaydedilir (K-E6). Biçimi bozuk öğe (yerel_id yok) atlanır.
    """
    if not isinstance(liste, list):
        return []
    alinan: list[str] = []
    for oge in liste[:TAHTADAN_EN_COK]:
        if not isinstance(oge, dict):
            continue
        yerel_id = str(oge.get("yerel_id") or "").lower()
        if not YEREL_ID.match(yerel_id):
            continue
        var = b.execute("SELECT id FROM ariza WHERE tahta_id = ? AND yerel_id = ?", (tahta["id"], yerel_id)).fetchone()
        if var:
            alinan.append(yerel_id)
            continue
        kategori = str(oge.get("kategori") or "")[:40]
        aciklama = temizle(oge.get("aciklama"))
        if kategori not in TAHTADAN_KATEGORI:
            aciklama = temizle(f"[kategori: {temizle(kategori)[:20] or '?'}] {aciklama}")
            kategori = "diger"
        if guvenlik.tc_kimlik_var(aciklama):
            aciklama = TC_ILETISI_TAHTA
        sinif = str(oge.get("oturum_sinifi") or "")
        sinif = sinif if sinif in OTURUM_SINIFLARI else ""
        simdi = vt.simdi()
        imlec = b.execute(
            "INSERT OR IGNORE INTO ariza (tahta_id, kaynak, yerel_id, kategori, aciklama, bildiren, oturum_sinifi, durum, "
            "olusturma, guncelleme) VALUES (?, 'tahta', ?, ?, ?, 'tahta', ?, 'acik', ?, ?)",
            (tahta["id"], yerel_id, kategori, aciklama, sinif, simdi, simdi),
        )
        if imlec.rowcount:
            _hareket(b, imlec.lastrowid, "tahta", "", "acik", "", simdi)
            vt.kayit_dus(
                b, f"tahta:{tahta['ad']}", "Tahtadan arıza bildirildi",
                f"#{imlec.lastrowid} · {ARIZA_KATEGORI[kategori]}" + (f" · {OTURUM_KISA.get(sinif, '')}" if sinif else ""), ip,
            )  # fmt: skip
        alinan.append(yerel_id)
    return alinan


def guncelle(b, ariza_id: int, kullanici: str, durum: str, not_metni: str, cozum_notu: str | None, ip: str = "") -> str:
    """Durum değişikliği ve/veya not; hareket + işlem kaydı. Hata: ValueError (ileti). İleti döner.

    `durum` boş ya da şimdikiyle aynıysa yalnız not/çözüm notu yazılır. İzinsiz geçiş reddedilir.
    """
    satir = b.execute("SELECT a.*, t.ad AS tahta_adi FROM ariza a JOIN tahta t ON t.id = a.tahta_id WHERE a.id = ?",
                      (ariza_id,)).fetchone()  # fmt: skip
    if not satir:
        raise LookupError("Arıza kaydı bulunamadı.")
    eski = satir["durum"]
    yeni = durum or eski
    if yeni not in ARIZA_DURUM:
        raise ValueError("Geçersiz durum.")
    if yeni != eski and yeni not in GECISLER[eski]:
        raise ValueError(f"'{ARIZA_DURUM[eski]}' durumundaki kayıt '{ARIZA_DURUM[yeni]}' yapılamaz.")
    not_metni = temizle(not_metni)
    cozum = temizle(cozum_notu) if cozum_notu is not None else None
    if guvenlik.tc_kimlik_var(not_metni) or (cozum and guvenlik.tc_kimlik_var(cozum)):
        raise ValueError(guvenlik.TC_KIMLIK_ILETISI)  # ret kaydını çağıran ayrı işlemle düşer
    cozum_degisti = cozum is not None and cozum != satir["cozum_notu"]
    if yeni == eski and not not_metni and not cozum_degisti:
        raise ValueError("Değişiklik yok: durum seçin ya da not yazın.")
    simdi = vt.simdi()
    b.execute(
        "UPDATE ariza SET durum = ?, guncelleme = ?, cozum_notu = ? WHERE id = ?",
        (yeni, simdi, cozum if cozum is not None else satir["cozum_notu"], ariza_id),
    )
    hareket_notu = not_metni
    if cozum_degisti and not hareket_notu:
        hareket_notu = f"Çözüm notu: {cozum}"[:METIN_EN_UZUN]
    _hareket(b, ariza_id, kullanici, eski, yeni, hareket_notu, simdi)
    ayrinti = f"#{ariza_id} · {satir['tahta_adi']} · " + (
        f"{ARIZA_DURUM[eski]} → {ARIZA_DURUM[yeni]}" if yeni != eski else "not eklendi"
    )
    vt.kayit_dus(b, kullanici, "Arıza kaydı güncellendi", ayrinti, ip)
    return f"Arıza #{ariza_id}: {ARIZA_DURUM[yeni]}." if yeni != eski else f"Arıza #{ariza_id}: not eklendi."


def suren_sayilari(b) -> dict[int, int]:
    """Tahta kimliği → açık + inceleniyor arıza sayısı."""
    return {
        s["tahta_id"]: s["sayi"]
        for s in b.execute(
            "SELECT tahta_id, COUNT(*) AS sayi FROM ariza WHERE durum IN ('acik', 'inceleniyor') GROUP BY tahta_id"
        )
    }


def suren_toplam(b) -> int:
    return b.execute("SELECT COUNT(*) FROM ariza WHERE durum IN ('acik', 'inceleniyor')").fetchone()[0]


def durum_sayilari(b) -> dict[str, int]:
    sayilar = dict.fromkeys(ARIZA_DURUM, 0)
    for s in b.execute("SELECT durum, COUNT(*) AS sayi FROM ariza GROUP BY durum"):
        sayilar[s["durum"]] = s["sayi"]
    sayilar["hepsi"] = sum(sayilar.values())
    return sayilar


def satir_gorunumu(s) -> dict:
    """Liste ve ayrıntı için düz sözlük (Jinja kaçışı korunur; |safe kullanılmaz)."""
    aciklama = s["aciklama"] or ""
    return {
        "id": s["id"],
        "tahta_id": s["tahta_id"],
        "tahta_adi": s["tahta_adi"],
        "derslik": s["derslik"],
        "tahta_kaldirildi": s["tahta_durum"] == "iptal",
        "kategori": s["kategori"],
        "kategori_adi": ARIZA_KATEGORI.get(s["kategori"], s["kategori"]),
        "aciklama": aciklama,
        "aciklama_kisa": aciklama if len(aciklama) <= 80 else aciklama[:79] + "…",
        "kaynak": s["kaynak"],
        "kaynak_metni": kaynak_metni(s),
        "durum": s["durum"],
        "durum_adi": ARIZA_DURUM.get(s["durum"], s["durum"]),
        "olusturma": s["olusturma"],
        "guncelleme": s["guncelleme"],
        "cozum_notu": s["cozum_notu"],
        "izinli_gecisler": [(d, ARIZA_DURUM[d]) for d in GECISLER.get(s["durum"], ())],
    }


LISTE_SORGUSU = (
    "SELECT a.*, t.ad AS tahta_adi, t.derslik AS derslik, t.durum AS tahta_durum, "
    "COALESCE(k.gorunen_ad, '') AS bildiren_adi "
    "FROM ariza a JOIN tahta t ON t.id = a.tahta_id LEFT JOIN kullanici k ON k.ad = a.bildiren AND a.kaynak = 'panel' "
)


def listele(b, durum: str = "", tahta_id: int | None = None, sinir: int = 500) -> list[dict]:
    kosullar, degerler = [], []
    if durum in ARIZA_DURUM:
        kosullar.append("a.durum = ?")
        degerler.append(durum)
    elif durum != "hepsi":
        kosullar.append("a.durum IN ('acik', 'inceleniyor')")
    if tahta_id is not None:
        kosullar.append("a.tahta_id = ?")
        degerler.append(tahta_id)
    sql = LISTE_SORGUSU + ("WHERE " + " AND ".join(kosullar) + " " if kosullar else "") + "ORDER BY a.id DESC LIMIT ?"
    return [satir_gorunumu(s) for s in b.execute(sql, (*degerler, sinir))]


def ayrinti(b, ariza_id: int) -> tuple[dict, list[dict]] | None:
    s = b.execute(LISTE_SORGUSU + "WHERE a.id = ?", (ariza_id,)).fetchone()
    if not s:
        return None
    hareketler = [
        {
            "zaman": h["zaman"],
            "kullanici": h["kullanici"],
            "eski": ARIZA_DURUM.get(h["eski_durum"], h["eski_durum"]),
            "yeni": ARIZA_DURUM.get(h["yeni_durum"], h["yeni_durum"]),
            "degisti": h["eski_durum"] != h["yeni_durum"],
            "not_metni": h["not_metni"],
        }
        for h in b.execute("SELECT * FROM ariza_hareket WHERE ariza_id = ? ORDER BY id", (ariza_id,))
    ]
    return satir_gorunumu(s), hareketler
