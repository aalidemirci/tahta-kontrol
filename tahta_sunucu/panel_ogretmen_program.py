"""Öğretmen programını yönetici önizlemesi ve açık onayla içe aktarır."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse
from starlette.datastructures import UploadFile

from . import eokul_program, vt, yoklama
from . import ogretmen_program as op
from .panel_program import bellekte_form, govde_uzunlugu, yetki_reddi

YOL = "/ogretmen-programi"
GOVDE_SINIRI = eokul_program.EN_COK_BAYT + op.PDF_EN_COK_BAYT + 256 * 1024


def kaydet(uygulama, y) -> None:
    depo = yoklama.OnizlemeDeposu()
    uygulama.state.ogretmen_program_onizleme = depo

    def sayfa(istek, k, *, veri=None, secimler=None, belirtec="", hata=""):
        with vt.islem() as b:
            onizleme = op.onizle(b, veri, secimler) if veri else None
            sayi = b.execute("SELECT COUNT(*) FROM ogretmen_program").fetchone()[0]
            gruplar = [dict(s) for s in b.execute(
                "SELECT p.ogretmen_id, o.ad, o.soyad, p.gun, p.sube, "
                "GROUP_CONCAT(p.ders_no || '. ' || p.ders_adi || ' (' || p.baslangic || '-' || p.bitis || ')', ' / ') AS dersler "
                "FROM ogretmen_program p LEFT JOIN ogretmen o ON o.id = p.ogretmen_id "
                "GROUP BY p.ogretmen_id, p.gun, p.sube ORDER BY o.soyad, o.ad, p.gun, p.sube LIMIT 251")]
        return y.sayfa(istek, "ogretmen_program.html", k, onizleme=onizleme, belirtec=belirtec,
                       mevcut_sayi=sayi, mevcut_gruplar=gruplar[:250], cok_grup=len(gruplar) > 250,
                       aktarim_hatasi=hata, kaynak_yolu=YOL)

    @uygulama.get(YOL, response_class=HTMLResponse)
    async def program_sayfasi(istek: Request):
        k = y.kullanici(istek)
        engel = yetki_reddi(y, istek, k, "Öğretmen programı içe aktarma", "/yoklama")
        return engel or sayfa(istek, k)

    @uygulama.post(YOL + "/onizle", response_class=HTMLResponse)
    async def onizle(istek: Request):
        k = y.kullanici(istek)
        engel = yetki_reddi(y, istek, k, "Öğretmen programı önizleme", "/yoklama")
        if engel:
            return engel
        uzunluk = govde_uzunlugu(istek)
        if uzunluk is None or uzunluk > GOVDE_SINIRI:
            return y.yonlendir(YOL, "Dosya gövdesi okunamadı veya boyut sınırını aşıyor.", hata=True)
        try:
            form = await bellekte_form(istek, GOVDE_SINIRI, max_files=2, max_fields=2)
            try:
                dosya, pdf = form.get("program"), form.get("pdf")
                if not isinstance(dosya, UploadFile):
                    raise ValueError("Program Excel dosyasını seçin.")
                xls_veri = await dosya.read(eokul_program.EN_COK_BAYT + 1)
                pdf_veri = await pdf.read(op.PDF_EN_COK_BAYT + 1) if isinstance(pdf, UploadFile) and pdf.filename else None
                veri = op.dosya_oku(xls_veri, pdf=pdf_veri, sube_metni=str(form.get("subeler") or ""))
            finally:
                await form.close()
            with vt.islem() as b:
                surum = op.surum(b)
            belirtec = depo.koy(k["id"], {"veri": veri, "surum": surum})
            return sayfa(istek, k, veri=veri, belirtec=belirtec)
        except ValueError as hata:
            return y.yonlendir(YOL, str(hata), hata=True)

    @uygulama.post(YOL + "/uygula", response_class=HTMLResponse)
    async def uygula(istek: Request):
        k = y.kullanici(istek)
        engel = yetki_reddi(y, istek, k, "Öğretmen programı aktarma", "/yoklama")
        if engel:
            return engel
        form = await istek.form()
        kayit = depo.al(str(form.get("belirtec") or ""), k["id"])
        if not kayit:
            return y.yonlendir(YOL, "Önizleme süresi dolmuş veya daha önce kullanılmış; dosyayı yeniden yükleyin.", hata=True)
        veri = kayit["veri"]
        secimler = {anahtar: str(form.get(f"esle_{no}") or "")
                    for no, anahtar in enumerate(sorted(veri["ogretmenler"]))}
        try:
            if str(form.get("onay") or "") != "1":
                raise ValueError("Eşlemeyi ve mevcut öğretmen programının değişeceğini onaylayın.")
            with vt.islem() as b:
                sayi = op.uygula(b, veri, kayit["surum"], secimler,
                                 ogretmensiz_onay=str(form.get("ogretmensiz_onay") or "") == "1")
                vt.kayit_dus(b, k["ad"], "Öğretmen programı aktarıldı",
                             f"{veri['blok_sayisi']} blok, {sayi} ders satırı", y.istemci_ip(istek))
            return y.yonlendir(YOL, f"Öğretmen programı aktarıldı: {sayi} ders satırı.")
        except ValueError as hata:
            belirtec = depo.koy(k["id"], kayit)
            return sayfa(istek, k, veri=veri, secimler=secimler, belirtec=belirtec, hata=str(hata))
