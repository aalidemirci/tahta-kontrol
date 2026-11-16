"""Oturum temizliği (K7, 0.8.0): gün sonunda ortak hesap oturumunun hafif temizliği.

Sunucu yalnız ZAMANI belirler ve `temizlik` komutunu verir; ne yapılacağına tahtadaki ajan karar verir
(yalnız öğretmen/öğrenci ortak hesabında: açık pencerelere kibar kapatma, tarayıcı süreçlerini
kapatma, tarayıcı profillerinde YALNIZ çerez ve oturum dosyalarını silme). Dosyalara (İndirilenler,
Masaüstü, Belgeler), tarayıcı geçmişine ve kayıtlı parolalara dokunulmaz.

- Varsayılan KAPALI (`ayar.oturum_temizligi`).
- Zaman: otomatik kapatma saatlerinden 5 dk önce ("kapatma_oncesi"), günün son dersi bittikten 10 dk
  sonra ("gun_sonu"; ikili eğitimde son devrenin sonu) ya da belirli bir saat ("saat"). Yalnız hafta içi.
- Kaçan iş sonradan çalışmaz: zamanından sonraki `PENCERE_SN` içinde sunucu çalışmıyorsa o günün
  temizliği yapılmaz; komut ömrü de kısadır (`KOMUT_OMRU_SN`), sonradan açılan tahta eski komutu almaz.
- Yalnız o an çevrimiçi ve `temizlik` yeteneği bildiren tahtaya verilir; acil yayın sürerken ve sınav
  penceresindeki tahtaya verilmez.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta

from . import acil, ayar, program, vt
from .komut import komut_ekle

YETENEK = "temizlik"
AYAR_ANAHTARI = "oturum_temizligi"
ZAMANLAR = {
    "kapatma_oncesi": "Otomatik kapatmadan 5 dakika önce",
    "gun_sonu": "Günün son dersi bittikten 10 dakika sonra (ikili eğitimde son devrenin sonu)",
    "saat": "Belirli bir saatte",
}
VARSAYILAN = {"etkin": False, "zaman": "kapatma_oncesi", "saat": "17:30"}
HESAPLAR = ["ogretmen", "ogrenci"]  # ajan bunun dışındaki hesapları zaten temizlemez (etapadmin, kişisel)
KAPATMA_ONCESI_DK = 5
GUN_SONU_DK = 10
PENCERE_SN = 240  # zamanından sonra bu süre içinde verilmeyen temizlik o gün yapılmaz
KOMUT_OMRU_SN = 120
ISARET_TAHTA = 0  # program_isaret'te okul geneli işaret (tahta kimliği 0)
SAAT_DESENI = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


def ayar_al(b) -> dict:
    deger = vt.ayar_al(b, AYAR_ANAHTARI)
    sonuc = dict(VARSAYILAN)
    if isinstance(deger, dict):
        sonuc["etkin"] = bool(deger.get("etkin"))
        if deger.get("zaman") in ZAMANLAR:
            sonuc["zaman"] = deger["zaman"]
        if isinstance(deger.get("saat"), str) and SAAT_DESENI.fullmatch(deger["saat"]):
            sonuc["saat"] = deger["saat"]
    return sonuc


def ayar_coz(form) -> dict:
    """Ayarlar › Oturum temizliği formu; hatada iletiyle ValueError."""
    zaman = str(form.get("tm_zaman", "kapatma_oncesi"))
    if zaman not in ZAMANLAR:
        raise ValueError("Temizlik zamanı geçersiz.")
    saat = str(form.get("tm_saat", "") or "").strip().replace(".", ":")
    if zaman == "saat" and not SAAT_DESENI.fullmatch(saat):
        raise ValueError("Temizlik saati SS:DD biçiminde olmalı (ör. 17:30).")
    return {
        "etkin": form.get("tm_etkin") == "1",
        "zaman": zaman,
        "saat": saat if SAAT_DESENI.fullmatch(saat) else VARSAYILAN["saat"],
    }


def yetenekli(tahta) -> bool:
    return YETENEK in acil.yetenekler(tahta)


def _an(gun: date, saat: str) -> datetime:
    return program.an_dt(gun, saat)


def gunun_zamanlari(b, gun: date, ayar_: dict | None = None) -> list[tuple[datetime, str]]:
    """O günün temizlik anları [(an, etiket)] (hafta sonu ve kapalıyken boş)."""
    ayar_ = ayar_ or ayar_al(b)
    if gun.weekday() >= 5:
        return []
    if ayar_["zaman"] == "saat":
        return [(_an(gun, ayar_["saat"]), f"saat {ayar_['saat']}")]
    if ayar_["zaman"] == "kapatma_oncesi":
        kural = vt.ayar_al(b, "otomatik_kapatma") or {}
        if not kural.get("etkin"):
            return []
        return [
            (_an(gun, s) - timedelta(minutes=KAPATMA_ONCESI_DK), f"otomatik kapatma ({s}) öncesi")
            for s in sorted(kural.get("saatler") or [])
            if isinstance(s, str) and SAAT_DESENI.fullmatch(s)
        ]
    saatler = program.ders_saatleri_oku(b)
    if not saatler:
        return []
    plan = program.plan_hesapla(gun, saatler, vt.ayar_al(b, "zil_takvimi"))
    if not plan["dersler"]:
        return []
    son = max(d[4] for d in plan["dersler"]) + timedelta(minutes=GUN_SONU_DK)
    return [(son, "gün sonu")]


def zaman_ozeti(b, bugun: date) -> dict:
    """Ayarlar sayfası için: {"uyari": metin|"", "bugun": "17:25, 17:55"|""}."""
    ayar_ = ayar_al(b)
    uyari = ""
    if ayar_["etkin"]:
        if ayar_["zaman"] == "kapatma_oncesi" and not (vt.ayar_al(b, "otomatik_kapatma") or {}).get("etkin"):
            uyari = "Otomatik kapatma kapalı ya da saati yok: bu seçenekle temizlik yapılmaz."
        elif ayar_["zaman"] == "gun_sonu" and not program.ders_saatleri_oku(b):
            uyari = "Zil saatleri tanımlı değil: bu seçenekle temizlik yapılmaz (Program sayfası)."
    anlar = gunun_zamanlari(b, bugun, ayar_) if ayar_["etkin"] else []
    return {"uyari": uyari, "bugun": ", ".join(a.strftime("%H:%M") for a, _ in anlar)}


def temizlik_komutu(b, tahta_id: int, olusturan: str, an: int | None = None) -> int:
    veri = {"hesaplar": list(HESAPLAR), "neden": "Gün sonu oturum temizliği"}
    return komut_ekle(b, tahta_id, "temizlik", veri, olusturan, KOMUT_OMRU_SN, simdi=an)


def zamanlayici(b, simdi: datetime, sinavdaki=lambda b, an: set()) -> list[int]:
    """20 sn'lik tur (web.py `oturum_temizligi`): zamanı gelen temizliği çevrimiçi tahtalara verir.

    Aynı an için okul genelinde bir kez (`program_isaret`, tahta 0). Uyandırılacak kimlikler döner.
    """
    ayar_ = ayar_al(b)
    if not ayar_["etkin"]:
        return []
    an = int(simdi.timestamp())
    tarih = simdi.date().isoformat()
    uyandir: list[int] = []
    for zaman, etiket in gunun_zamanlari(b, simdi.date(), ayar_):
        if not 0 <= (simdi - zaman).total_seconds() < PENCERE_SN:
            continue
        anahtar = f"{tarih}|temizlik|{zaman:%H:%M}"
        if b.execute(
            "INSERT OR IGNORE INTO program_isaret (tahta_id, anahtar, zaman) VALUES (?, ?, ?)", (ISARET_TAHTA, anahtar, an)
        ).rowcount != 1:  # fmt: skip
            continue
        if acil.aktif(b, an) is not None:
            vt.kayit_dus(b, "sistem", "Oturum temizliği acil yayın nedeniyle atlandı", etiket)
            continue
        cevrimici = [
            t for t in b.execute("SELECT * FROM tahta WHERE durum = 'onayli'").fetchall()
            if t["son_gorulme"] and an - t["son_gorulme"] < ayar.CEVRIMICI_ESIK_SN
        ]  # fmt: skip
        sinavda = sinavdaki(b, an)
        hedefler = [t for t in cevrimici if yetenekli(t) and t["id"] not in sinavda]
        eski = sum(1 for t in cevrimici if not yetenekli(t))
        for t in hedefler:
            temizlik_komutu(b, t["id"], "sistem", an)
            uyandir.append(t["id"])
        ayrinti = f"{etiket}: {len(hedefler)} tahta"
        if eski:
            ayrinti += f"; {eski} tahtada ajan güncellenmeli (temizlik yapılmadı)"
        sinavdaki_sayi = sum(1 for t in cevrimici if t["id"] in sinavda and yetenekli(t))
        if sinavdaki_sayi:
            ayrinti += f"; {sinavdaki_sayi} tahta sınavda (atlandı)"
        vt.kayit_dus(b, "sistem", "Oturum temizliği", ayrinti)
    return uyandir


def tahta_ozeti(b, tahta) -> dict:
    """Tahta sayfası: yetenek, son sonuçlanan temizlik ve bekleyen komut."""
    son = b.execute(
        "SELECT * FROM komut WHERE tahta_id = ? AND tur = 'temizlik' AND durum IN ('tamam', 'hata') "
        "ORDER BY id DESC LIMIT 1",
        (tahta["id"],),
    ).fetchone()
    bekleyen = b.execute(
        "SELECT 1 FROM komut WHERE tahta_id = ? AND tur = 'temizlik' AND durum IN ('bekliyor', 'gonderildi') "
        "AND olusturma > ? LIMIT 1",
        (tahta["id"], vt.simdi() - 3600),
    ).fetchone()
    durum = json.loads(tahta["durum_json"] or "{}")
    return {
        "yetenekli": yetenekli(tahta),
        "son": {"zaman": son["tamamlanma"] or son["olusturma"], "sonuc": son["sonuc"] or "", "basarili": son["durum"] == "tamam",
                "olusturan": son["olusturan"]} if son else None,  # fmt: skip
        "bekleyen": bool(bekleyen) or bool(durum.get("temizlik_bekliyor")),
        "ayar": ayar_al(b),
    }
