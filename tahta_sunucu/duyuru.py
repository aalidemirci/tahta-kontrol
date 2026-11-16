"""Duyuru yayını ve planları: tek yayın yolu, plan zamanlayıcısı, yayın durdurma.

Her duyuru gösterimi (panodan hemen, plandan, "yeniden gönder") `duyuru_yayimla` ile
çıkar. İşlevler veritabanı işlemi içinde çağrılır ve uyandırılacak tahta kimliklerini
döndürür; uyandırmayı çağıran işlem bittikten sonra yapar.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta

from . import hedef as hedef_mod
from . import vt, zamanlama
from .komut import komut_ekle

KACIRMA_GERIYE_GUN = 7
YAYIN_DURUMU = {
    "gonderildi": "Gönderildi",
    "durduruldu": "Durduruldu",
    "kacirildi": "Kaçırıldı — sunucu kapalıydı",
    "hedefsiz": "Hedefsiz",
}
PLAN_DURUMU = {"etkin": "Etkin", "duraklatildi": "Duraklatıldı", "bitti": "Bitti", "silindi": "Silindi"}
UZUN_KESINTI = "Sunucu 7 günden uzun kapalı kaldı; daha eski zamanlanmış duyurular raporlanmadı."


def duyuru_yayimla(
    b,
    *,
    baslik: str,
    metin: str,
    sure_sn: int,
    kapatilabilir: bool,
    hedef: dict,
    olusturan: str,
    an: int,
    plan_id: int | None = None,
    simdi: int | None = None,
    ip: str = "",
    kayit_ayrintisi: str = "",
) -> tuple[int | None, list[int]]:
    """Yayın satırını yazar, hedefi çözer, her tahtaya 'duyuru' komutu ekler.

    Döndürür: (duyuru_id, tahta_idleri). Planlı yayın aynı an için ikinci kez yazılmaz
    (benzersiz dizin); o durumda (None, []) döner. Komut çevrimdışı tahtalara da yazılır:
    süre içinde açılan tahta kalan süreyle alır.
    """
    simdi = vt.simdi() if simdi is None else int(simdi)
    bitis = int(an) + int(sure_sn)
    if bitis <= simdi:
        raise ValueError("Yayının süresi geçmiş.")
    tahtalar = hedef_mod.coz(b, hedef)
    ozet = hedef_mod.ozet(b, hedef)
    imlec = b.execute(
        f"INSERT {'OR IGNORE ' if plan_id else ''}INTO duyuru "
        "(baslik, metin, sure_sn, kapatilabilir, hedef, olusturan, olusturma, plan_id, an, bitis, durum, "
        "hedef_json, tahta_sayisi) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            baslik,
            metin,
            int(sure_sn),
            int(bool(kapatilabilir)),
            ozet,
            olusturan,
            simdi,
            plan_id,
            int(an),
            bitis,
            "gonderildi" if tahtalar else "hedefsiz",
            json.dumps(hedef, ensure_ascii=False),
            len(tahtalar),
        ),
    )
    if imlec.rowcount == 0:
        return None, []
    duyuru_id = imlec.lastrowid
    veri = {
        "duyuru_id": duyuru_id,
        "baslik": baslik,
        "metin": metin,
        "sure_sn": int(sure_sn),
        "kapatilabilir": bool(kapatilabilir),
        "bitis_sunucu": bitis,
    }
    for t in tahtalar:
        komut_ekle(b, t["id"], "duyuru", veri, olusturan, omur=bitis - simdi, duyuru_id=duyuru_id, simdi=simdi)
    islem = "Zamanlanmış duyuru" if plan_id else "Duyuru"
    ayrinti = f"{len(tahtalar)} tahta: {ozet}" if tahtalar else f"Hedefsiz (şu an hiçbir tahtaya ulaşmıyor): {ozet}"
    if kayit_ayrintisi:
        ayrinti = f"{kayit_ayrintisi} · {ayrinti}"
    vt.kayit_dus(b, olusturan, islem, ayrinti, ip)
    return duyuru_id, [t["id"] for t in tahtalar]


def kacirildi_yaz(b, plan, an: int, simdi: int) -> None:
    imlec = b.execute(
        "INSERT OR IGNORE INTO duyuru (baslik, metin, sure_sn, kapatilabilir, hedef, olusturan, olusturma, "
        "plan_id, an, bitis, durum, hedef_json, tahta_sayisi) VALUES (?, ?, ?, ?, ?, 'sistem', ?, ?, ?, ?, "
        "'kacirildi', ?, 0)",
        (
            plan["baslik"],
            plan["metin"],
            plan["sure_sn"],
            plan["kapatilabilir"],
            hedef_mod.ozet(b, _hedef(plan)),
            simdi,
            plan["id"],
            an,
            an + plan["sure_sn"],
            plan["hedef_json"],
        ),
    )
    if imlec.rowcount:
        vt.kayit_dus(
            b,
            "sistem",
            "Zamanlanmış duyuru kaçırıldı",
            f"{plan['baslik'] or plan['metin'][:60]} · {zamanlama.an_yaz(an)} · sunucu o saatte çalışmıyordu",
        )


def _hedef(plan) -> dict:
    try:
        return hedef_mod.dogrula(plan["hedef_json"])
    except ValueError:
        return {"tahtalar": []}


def planlari_isle(b, simdi_yerel: datetime) -> tuple[int, set[int]]:
    """Plan zamanlayıcısının bir turu (tek veritabanı işlemi içinde çağrılır).

    Son 7 günün henüz işlenmemiş anları: süresi içindeyse kalan süreyle yayımlanır,
    geçmişse "kaçırıldı" yazılır. gecerlilik'ten önceki anlar hiç işlenmez. Kalan
    gösterimi olmayan plan "bitti" olur. Döndürür: (yayın sayısı, uyandırılacak tahtalar).
    """
    simdi = int(simdi_yerel.timestamp())
    son_tur = vt.ayar_al(b, "duyuru_son_tur")
    if isinstance(son_tur, int) and simdi - son_tur > KACIRMA_GERIYE_GUN * 86400:
        vt.kayit_dus(b, "sistem", "Zamanlanmış duyurular: uzun kesinti", UZUN_KESINTI)
    alt_sinir = simdi_yerel - timedelta(days=KACIRMA_GERIYE_GUN)
    yayin, uyandir = 0, set()
    for plan in b.execute("SELECT * FROM duyuru_plani WHERE durum = 'etkin' ORDER BY id").fetchall():
        hedef = _hedef(plan)
        for an in zamanlama.anlar(plan, alt_sinir, simdi_yerel):
            if an < plan["gecerlilik"]:
                continue
            if b.execute("SELECT 1 FROM duyuru WHERE plan_id = ? AND an = ?", (plan["id"], an)).fetchone():
                continue
            if simdi < an + plan["sure_sn"]:
                duyuru_id, idler = duyuru_yayimla(
                    b,
                    baslik=plan["baslik"],
                    metin=plan["metin"],
                    sure_sn=plan["sure_sn"],
                    kapatilabilir=bool(plan["kapatilabilir"]),
                    hedef=hedef,
                    olusturan="sistem",
                    an=an,
                    plan_id=plan["id"],
                    simdi=simdi,
                    kayit_ayrintisi=f"plan #{plan['id']} ({plan['olusturan']})",
                )
                if duyuru_id:
                    yayin += 1
                    uyandir.update(idler)
            else:
                kacirildi_yaz(b, plan, an, simdi)
        if not zamanlama.sonraki(plan, simdi, 1):
            b.execute("UPDATE duyuru_plani SET durum = 'bitti' WHERE id = ?", (plan["id"],))
    vt.ayar_yaz(b, "duyuru_son_tur", simdi)
    return yayin, uyandir


def sahip(b, yayin) -> str:
    """Yayını durdurma yetkisi için sahibi: plandan doğduysa planı oluşturan."""
    if yayin["plan_id"]:
        plan = b.execute("SELECT olusturan FROM duyuru_plani WHERE id = ?", (yayin["plan_id"],)).fetchone()
        if plan:
            return plan["olusturan"]
    return yayin["olusturan"]


def yayin_durdur(b, duyuru_id: int, kullanici_ad: str, simdi: int | None = None) -> list[int]:
    """Yayındaki gösterimi durdurur; uyandırılacak tahtaları döndürür.

    Bekleyen komutlar iptal edilir (sonradan açılan tahta almaz); tahtaya ulaşmış olanlara
    kimlikli `duyuru_kaldir` gider (ekrandaki başka duyuruya dokunulmaz).
    """
    simdi = vt.simdi() if simdi is None else simdi
    yayin = b.execute("SELECT * FROM duyuru WHERE id = ?", (duyuru_id,)).fetchone()
    if not yayin or yayin["durum"] != "gonderildi" or (yayin["bitis"] or 0) <= simdi:
        raise ValueError("Bu duyuru şu an yayında değil.")
    b.execute("UPDATE duyuru SET durum = 'durduruldu', durduran = ? WHERE id = ?", (kullanici_ad, duyuru_id))
    b.execute(
        "UPDATE komut SET durum = 'iptal', tamamlanma = ?, sonuc = 'Yayın durduruldu.' "
        "WHERE duyuru_id = ? AND durum = 'bekliyor'",
        (simdi, duyuru_id),
    )
    ulasan = [
        s["tahta_id"]
        for s in b.execute(
            "SELECT DISTINCT tahta_id FROM komut WHERE duyuru_id = ? AND tur = 'duyuru' AND durum IN ('gonderildi', 'tamam')",
            (duyuru_id,),
        )
    ]
    for tahta_id in ulasan:
        komut_ekle(b, tahta_id, "duyuru_kaldir", {"duyuru_id": duyuru_id}, kullanici_ad)
    vt.kayit_dus(
        b, kullanici_ad, "Duyuru durduruldu", f"#{duyuru_id} {yayin['baslik'] or yayin['metin'][:60]} · {len(ulasan)} tahtadan kaldırılıyor"
    )
    return ulasan


def teslimler(b, duyuru_idler) -> dict[int, tuple[int, int]]:
    """Yayın → (tahtaya ulaşan komut sayısı, toplam komut sayısı)."""
    idler = [int(i) for i in duyuru_idler]
    if not idler:
        return {}
    isaret = ",".join("?" * len(idler))
    return {
        s["duyuru_id"]: (s["ulasan"] or 0, s["toplam"])
        for s in b.execute(
            "SELECT duyuru_id, COUNT(*) AS toplam, SUM(durum IN ('gonderildi', 'tamam')) AS ulasan FROM komut "
            f"WHERE tur = 'duyuru' AND duyuru_id IN ({isaret}) GROUP BY duyuru_id",
            idler,
        )
    }
