"""Duyuru planlarının takvim hesabı (saf işlevler; veritabanına dokunmaz).

Plan alanları `duyuru_plani` sütunlarıyla aynıdır: tekrar ('tek'|'gunluk'|'haftalik'),
saat 'SS:DD', baslangic/bitis 'YYYY-MM-DD', gunler '0,1,2,3,4' (Pzt=0 … Paz=6),
gecerlilik (epoch). Anlamı Europe/Istanbul yerel saatidir; epoch'a her seferinde
zoneinfo ile çevrilir (el ile +3 eklenmez).
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import guvenlik

ISTANBUL = ZoneInfo("Europe/Istanbul")
GUN_KISA = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]
DUYURU_SURE_DK = (1, 240)
PLAN_EN_UZUN_GUN = 366
METIN_EN_UZUN = 4000
BASLIK_EN_UZUN = 200
HAFTA_ICI = "0,1,2,3,4"
HER_GUN = "0,1,2,3,4,5,6"


def saat_coz(deger, bos_iletisi: str = "Saati seçin.") -> str:
    s = str(deger or "").strip().replace(".", ":")
    if not s:
        raise ValueError(bos_iletisi)
    eslesme = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if not eslesme or int(eslesme.group(1)) > 23 or int(eslesme.group(2)) > 59:
        raise ValueError("Saat SS:DD biçiminde olmalı (ör. 08:25).")
    return f"{int(eslesme.group(1)):02d}:{eslesme.group(2)}"


def tarih_coz(deger, bos_iletisi: str = "Tarihi seçin.") -> date:
    """'YYYY-MM-DD' (input type=date) ya da 'gg.aa.yyyy' kabul eder. Boşsa alana özgü ileti."""
    s = str(deger or "").strip()
    if not s:
        raise ValueError(bos_iletisi)
    for bicim in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, bicim).date()
        except ValueError:
            continue
    raise ValueError("Tarih gg.aa.yyyy biçiminde olmalı.")


def tarih_yaz(d) -> str:
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return d.strftime("%d.%m.%Y")


def an_hesapla(gun: date, saat: str) -> int:
    return int(datetime.combine(gun, time(int(saat[:2]), int(saat[3:])), ISTANBUL).timestamp())


def an_yaz(an) -> str:
    return datetime.fromtimestamp(int(an), ISTANBUL).strftime("%d.%m.%Y %H:%M") if an else "—"


def gunler_kumesi(plan) -> set[int]:
    return {int(g) for g in str(plan["gunler"]).split(",") if g.strip().isdigit()}


def anlar(plan, bas: datetime, son: datetime) -> list[int]:
    """Planın [bas, son] aralığına düşen gösterim anları (epoch, artan). gecerlilik'e bakmaz."""
    gunler = gunler_kumesi(plan)
    ilk = max(date.fromisoformat(plan["baslangic"]), bas.astimezone(ISTANBUL).date())
    sonuncu = min(date.fromisoformat(plan["bitis"]), son.astimezone(ISTANBUL).date())
    alt, ust = int(bas.timestamp()), int(son.timestamp())
    sonuc = []
    gun = ilk
    while gun <= sonuncu:
        if gun.weekday() in gunler:
            an = an_hesapla(gun, plan["saat"])
            if alt <= an <= ust:
                sonuc.append(an)
        gun += timedelta(days=1)
    return sonuc


def sonraki(plan, simdi: int, adet: int = 3) -> list[int]:
    """Şu andan sonraki (ve gecerlilik'ten önce olmayan) en çok `adet` gösterim anı."""
    gunler = gunler_kumesi(plan)
    if not gunler:
        return []
    gun = max(date.fromisoformat(plan["baslangic"]), datetime.fromtimestamp(simdi, ISTANBUL).date())
    sonuncu = date.fromisoformat(plan["bitis"])
    alt = max(simdi + 1, int(plan["gecerlilik"] or 0))
    sonuc: list[int] = []
    while gun <= sonuncu and len(sonuc) < adet:
        if gun.weekday() in gunler:
            an = an_hesapla(gun, plan["saat"])
            if an >= alt:
                sonuc.append(an)
        gun += timedelta(days=1)
    return sonuc


def ozet(plan) -> str:
    """"Her gün (hafta içi) 08:25 · 17.11.2026–19.06.2027", "Her hafta Pzt, Per 13:00 · …", "Bir kez 24.11.2026 10:40"."""
    aralik = f"{tarih_yaz(plan['baslangic'])}–{tarih_yaz(plan['bitis'])}"
    if plan["tekrar"] == "tek":
        return f"Bir kez {tarih_yaz(plan['baslangic'])} {plan['saat']}"
    if plan["tekrar"] == "gunluk":
        tur = "Her gün" if plan["gunler"] == HER_GUN else "Her gün (hafta içi)"
        return f"{tur} {plan['saat']} · {aralik}"
    gunler = ", ".join(GUN_KISA[g] for g in sorted(gunler_kumesi(plan)))
    return f"Her hafta {gunler} {plan['saat']} · {aralik}"


def form_coz(form, simdi: int) -> dict:
    """Duyuru formunu doğrular; plan/yayın sözlüğü döndürür, hatada iletiyle ValueError.

    Form alanları: baslik, metin, sure_dk, kapatilabilir=1, zaman=hemen|bir_kez|tekrarli;
    bir kez: bir_tarih, bir_saat; tekrarlı: siklik=gunluk|haftalik, hafta_sonu=1, gun (çoklu 0-6),
    tekrar_saat, baslangic, bitis. Hedef ayrıca hedef.formdan ile okunur.
    """
    metin_ = str(form.get("metin", "")).strip()
    baslik = str(form.get("baslik", "")).strip()[:BASLIK_EN_UZUN]
    if not metin_:
        raise ValueError("Duyuru metni boş olamaz.")
    if len(metin_) > METIN_EN_UZUN:
        raise ValueError(f"Duyuru metni en çok {METIN_EN_UZUN} karakter olabilir.")
    try:
        sure_dk = int(str(form.get("sure_dk", "")).strip())
    except ValueError:
        sure_dk = 0
    if not DUYURU_SURE_DK[0] <= sure_dk <= DUYURU_SURE_DK[1]:
        raise ValueError("Süre 1-240 dakika olmalı.")
    if guvenlik.tc_kimlik_var(metin_) or guvenlik.tc_kimlik_var(baslik):
        raise ValueError(guvenlik.TC_KIMLIK_ILETISI)
    zaman = str(form.get("zaman", "hemen"))
    sonuc = {
        "baslik": baslik,
        "metin": metin_,
        "sure_sn": sure_dk * 60,
        "kapatilabilir": 1 if form.get("kapatilabilir") == "1" else 0,
        "zaman": zaman,
    }
    bugun = datetime.fromtimestamp(simdi, ISTANBUL).date()
    if zaman == "hemen":
        return sonuc
    if zaman == "bir_kez":
        gun = tarih_coz(form.get("bir_tarih"), "Duyurunun tarihini seçin.")
        saat = saat_coz(form.get("bir_saat"), "Duyurunun saatini seçin.")
        an = an_hesapla(gun, saat)
        if an <= simdi + 60:
            raise ValueError("Duyuru zamanı geçmişte olamaz.")
        if an > simdi + PLAN_EN_UZUN_GUN * 86400:
            raise ValueError("En çok bir yıl sonrası planlanabilir.")
        sonuc.update(tekrar="tek", saat=saat, baslangic=gun.isoformat(), bitis=gun.isoformat(), gunler=HER_GUN)
        return sonuc
    if zaman != "tekrarli":
        raise ValueError("Duyurunun ne zaman yayımlanacağını seçin.")
    siklik = str(form.get("siklik", ""))
    if siklik not in ("gunluk", "haftalik"):
        raise ValueError("Tekrarlı duyuru için günlük ya da haftalık seçin.")
    saat = saat_coz(form.get("tekrar_saat"), "Tekrarlı duyurunun saatini seçin.")
    baslangic = tarih_coz(form.get("baslangic") or bugun.isoformat())
    bitis = tarih_coz(form.get("bitis"), "Bitiş tarihini seçin.")
    if bitis < baslangic:
        raise ValueError("Bitiş tarihi başlangıçtan önce olamaz.")
    if bitis < bugun:
        raise ValueError("Bitiş tarihi geçmişte olamaz.")
    if (bitis - baslangic).days > PLAN_EN_UZUN_GUN:
        raise ValueError("Tekrarlı duyuru en çok bir yıl sürebilir.")
    if siklik == "gunluk":
        gunler = HER_GUN if form.get("hafta_sonu") == "1" else HAFTA_ICI
    else:
        secili = sorted({int(g) for g in form.getlist("gun") if str(g) in ("0", "1", "2", "3", "4", "5", "6")})
        if not secili:
            raise ValueError("Haftalık duyuru için en az bir gün seçin.")
        gunler = ",".join(str(g) for g in secili)
    sonuc.update(
        tekrar=siklik, saat=saat, baslangic=baslangic.isoformat(), bitis=bitis.isoformat(), gunler=gunler
    )
    return sonuc
