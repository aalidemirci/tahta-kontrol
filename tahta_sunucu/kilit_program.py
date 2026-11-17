"""Tahtanın bugünkü programı: yalnız şube, ders ve saat; kişi bilgisi içermez."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import metin, program, yoklama

ISTANBUL = ZoneInfo("Europe/Istanbul")
EN_COK_SATIR = 24


def ajan_gorunumu(b, tahta, an: int) -> dict:
    simdi = datetime.fromtimestamp(an, ISTANBUL)
    gun = simdi.date()
    bitis = datetime.combine(gun + timedelta(days=1), time.min, ISTANBUL)
    sonuc = {"tarih": gun.isoformat(), "dersler": [], "ileti": "", "gecerli_sn": int(bitis.timestamp()) - an}
    plan = program.gun_plani(b, gun)
    if plan.get("tatil"):
        sonuc["ileti"] = "Bugün tatil; ders programı yok."
        return sonuc
    if not plan.get("dersler") and program.ders_saatleri_oku(b):
        sonuc["ileti"] = "Bugün için ders saati tanımlı değil."
        return sonuc
    subeler = {s for ham in str(tahta["subeler"] or "").split(",") if (s := metin.sube_duzelt(ham))}
    if not subeler:
        sonuc["ileti"] = "Bu tahtaya şube atanmamış."
        return sonuc
    satirlar = [dict(s) for s in b.execute(
        "SELECT sube, ders_no, baslangic, bitis, ders_adi FROM ogretmen_program WHERE gun = ?",
        (plan["program_gunu"],),
    ) if s["sube"] in subeler]
    saatler = {s: {d["ders_no"]: d for d in yoklama.program_ders_saatleri(b, gun, s, plan)} for s in subeler}
    belirsiz = set()
    if plan.get("dersler"):
        for sube in subeler:
            if saatler[sube]:
                continue
            kaynak = sorted((s for s in satirlar if s["sube"] == sube), key=lambda s: s["baslangic"])
            if not kaynak:
                continue
            ilk = kaynak[0]
            adaylar = {d[0] for d in plan["dersler"] if d[2] == ilk["ders_no"]
                       and abs(program.dk(f"{d[3]:%H:%M}") - program.dk(ilk["baslangic"])) <= 5}
            if len(adaylar) != 1:
                belirsiz.add(sube)
                continue
            devre = next(iter(adaylar))
            saatler[sube] = {d[2]: {"baslangic": f"{d[3]:%H:%M}", "bitis": f"{d[4]:%H:%M}"}
                            for d in plan["dersler"] if d[0] == devre}
    birlesik: dict[tuple, set[str]] = {}
    for satir in satirlar:
        sube = satir["sube"]
        if sube in belirsiz:
            continue
        ders_no = satir["ders_no"]
        saat = saatler[sube].get(ders_no)
        # Tanımlı bir çizelgede o ders yoksa eski rapor satırını gösterme.
        if saatler[sube] and saat is None:
            continue
        bas = saat["baslangic"] if saat else satir["baslangic"]
        bit = saat["bitis"] if saat else satir["bitis"]
        anahtar = (bas, bit, sube, ders_no)
        birlesik.setdefault(anahtar, set()).add(str(satir["ders_adi"])[:100])
    for (bas, bit, sube, no), adlar in sorted(birlesik.items()):
        sonuc["dersler"].append({"sube": sube, "ders_no": no, "baslangic": bas, "bitis": bit,
                                 "ders_adi": " / ".join(sorted(adlar))[:80]})
    if not sonuc["dersler"]:
        sonuc["ileti"] = "Bugün için aktarılmış ders programı yok."
    if belirsiz:
        sonuc["ileti"] = "Şube devresi günün çizelgesiyle eşleştirilemedi; idare derslik programını kontrol etsin."
    if len(sonuc["dersler"]) > EN_COK_SATIR:
        sonuc["dersler"] = sonuc["dersler"][:EN_COK_SATIR]
        sonuc["ileti"] = "Programın ilk 24 dersi gösteriliyor."
    return sonuc
