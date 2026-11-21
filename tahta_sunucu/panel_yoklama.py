"""Ders yoklaması uçları (Aşama 5): panel sayfaları ve tahtanın yoklama uçları (/ajan/yoklama/*).

Yetki (ortak sözlük §3): yoklama görme/düzeltme/icmal, panelden yoklama, PIN üret/kilit aç iki role
(yonetici, idareci) açık; öğretmen ekleme/düzenleme/pasifleştirme, toplu PIN, öğrenci aktarma ve yıl
sonu silme yalnız yöneticinin. Her yazma işlemi işlem kaydına düşer; kayda öğrenci adı ve okul no
YAZILMAZ (M6), öğretmen için yalnız kod yazılır. PIN düz metni yalnız pusula yanıtında görünür
(Cache-Control: no-store, ara katman); adres satırına, kayda, veritabanına girmez.
Yüklenen dosya diske yazılmaz (`bellekte_form`: geçici dosyaya taşma yok); önizleme yalnız bellekte, 15 dk.

Şablon bağlamları modül sonundaki SÖZLEŞME'dedir.
"""

from __future__ import annotations

import json
from datetime import timedelta

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from starlette.datastructures import UploadFile

from . import acil, eokul, maske, metin, panel_defter, sinav, usb_anahtar, vt
from . import yoklama as yk
from .panel_program import bellekte_form, govde_uzunlugu

YETKI_ILETISI = "Bu işlem için yönetici yetkisi gerekir."


def _tamsayi(deger, varsayilan=None):
    s = str(deger if deger is not None else "").strip()
    return int(s) if metin.rakam_mi(s) and len(s) <= 9 else varsayilan


def ogretmen_secenekleri(b) -> list[dict]:
    return [
        {"id": o["id"], "etiket": f"{yk.ogretmen_tam_ad(o)} (kod {o['kod']})"}
        for o in sorted(
            b.execute("SELECT o.*, p.kod FROM ogretmen o JOIN ogretmen_pin p ON p.ogretmen_id = o.id WHERE o.aktif = 1").fetchall(),
            key=lambda o: (metin.tr_sirala_anahtari(o["soyad"]), metin.tr_sirala_anahtari(o["ad"])),
        )
    ]


def eksik_tahtalar(b) -> list[dict]:
    """Yoklama alamayacak ya da şubesi bilinmeyen onaylı tahtalar (günlük görünümdeki kapalı bölüm)."""
    sonuc = []
    for t in b.execute("SELECT * FROM tahta WHERE durum = 'onayli' ORDER BY derslik COLLATE NOCASE, ad COLLATE NOCASE"):
        nedenler = []
        if yk.YOKLAMA_YETENEGI not in acil.yetenekler(t):
            nedenler.append("Yoklama: ajan güncellenmeli")
        if not yk.tahta_subeleri_(t):
            nedenler.append("şube alanı boş")
        if nedenler:
            sonuc.append({"id": t["id"], "ad": t["ad"], "derslik": t["derslik"], "neden": " · ".join(nedenler)})
    return sonuc


def ayar_baglami(b) -> dict:
    """Ayarlar sayfasındaki "Ders yoklaması" bölümünün bağlamı (web.bolum_baglami çağırır)."""
    return {
        "yoklama_ayari": yk.ayar_al(b),
        "yoklama_maskeleri": maske.SINIF_BICIMLERI,
        "yoklama_maske_secenekleri": [
            {"kod": kod, "ad": maske.bicim_parcalari(kod)[0], "ornek": maske.bicim_parcalari(kod)[1]}
            for kod in maske.SINIF_BICIMLERI
        ],
        "yoklama_sinirlari": yk.SINIRLAR,
        "yoklama_ogrenci_sayisi": b.execute("SELECT COUNT(*) FROM ogrenci WHERE aktif = 1").fetchone()[0],
        # 0.21.0: yalnız not için (ayar USB anahtar bölümündedir; bu form onu YAZMAZ)
        "yoklama_baskan_acik": usb_anahtar.baskan_acik(usb_anahtar.ayar_al(b)),
    }


def kaydet(uygulama, y) -> None:
    kapi = yk.PinKapisi()
    depo = yk.OnizlemeDeposu()
    uygulama.state.yoklama_pin_kapisi = kapi
    uygulama.state.yoklama_onizleme = depo

    def ip(istek: Request) -> str:
        return y.istemci_ip(istek)

    def yonetici_gerek(istek: Request, k, islem: str, donus: str):
        """Yönetici değilse işlem kaydına düşürüp reddeder; yöneticiyse None."""
        if k["rol"] == "yonetici":
            return None
        with vt.islem() as b:
            vt.kayit_dus(b, k["ad"], "Yetkisiz işlem reddedildi", islem, ip(istek))
        return y.yonlendir(donus, YETKI_ILETISI, hata=True)

    def gun_al(deger, an: int):
        return yk.tarih_coz(deger) or yk.bugun(an)

    # Şube defteri, son günler, mazeret/izin ve öğrenci görünümü (0.14.0) ayrı dosyadadır; önizleme deposu ortaktır.
    panel_defter.kaydet(uygulama, y, depo)

    # ---- günlük görünüm --------------------------------------------------------------------------
    @uygulama.get("/yoklama", response_class=HTMLResponse)
    async def yoklama_sayfasi(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        an = vt.simdi()
        gun = gun_al(istek.query_params.get("tarih"), an)
        with vt.islem() as b:
            g = yk.gunluk_gorunum(b, gun, an)
            ayar_ = yk.ayar_al(b)
            tahtalar = eksik_tahtalar(b)
            ogrenci_var = bool(b.execute("SELECT 1 FROM ogrenci WHERE aktif = 1 LIMIT 1").fetchone())
        return y.sayfa(istek, "yoklama.html", k, g=g, yoklama_etkin=ayar_["etkin"], eksik_tahtalar=tahtalar,
                       ogrenci_var=ogrenci_var, adli_not=yk.ILETI_ADLI_SAYFA, bugun_iso=yk.bugun(an).isoformat())  # fmt: skip

    # ---- kayıt ayrıntısı ve düzeltme ----------------------------------------------------------------
    @uygulama.get("/yoklama/kayit/{yoklama_id}", response_class=HTMLResponse)
    async def kayit_sayfasi(istek: Request, yoklama_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        with vt.islem() as b:
            ayrinti = yk.kayit_ayrintisi(b, yoklama_id)
        if not ayrinti:
            return y.yonlendir("/yoklama", "Yoklama kaydı bulunamadı.", hata=True)
        return y.sayfa(istek, "yoklama_kayit.html", k, kayit=ayrinti, adli_not=yk.ILETI_ADLI_SAYFA)

    @uygulama.post("/yoklama/kayit/{yoklama_id}")
    async def kayit_islem(istek: Request, yoklama_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        eylem = str(form.get("eylem", ""))
        an = vt.simdi()
        donus = f"/yoklama/kayit/{yoklama_id}"
        try:
            aciklama = yk.aciklama_denetle(form.get("aciklama", ""))
            with vt.islem() as b:
                kayit_ = b.execute(
                    "SELECT y.*, p.kod FROM yoklama y LEFT JOIN ogretmen_pin p ON p.ogretmen_id = y.ogretmen_id WHERE y.id = ?",
                    (yoklama_id,),
                ).fetchone()
                if not kayit_:
                    return y.yonlendir("/yoklama", "Yoklama kaydı bulunamadı.", hata=True)
                gun = yk.tarih_coz(kayit_["tarih"])
                if eylem == "duzelt":
                    gecerli = {o["id"] for o in yk.sube_ogrencileri(b, kayit_["sube"])} | set(yk.yok_listesi(b, yoklama_id))
                    onceki_gec = set(yk.gec_listesi(b, yoklama_id))
                    gecerli |= onceki_gec
                    yok = yk.yok_idleri_coz([str(x) for x in form.getlist("yok")], gecerli)
                    gec = yk.yok_idleri_coz([str(x) for x in form.getlist("gec")], gecerli)
                    # Geç yalnız devrenin ilk dersinde eklenir; kayıtta zaten duran geç işareti korunabilir.
                    if set(gec) - onceki_gec and not (gun and yk.gec_secilebilir(b, gun, kayit_["sube"], kayit_["ders_no"])):
                        raise ValueError(yk.ILETI_GEC_ILK_DERS)
                    yk.yoklama_yaz(
                        b, tarih=kayit_["tarih"], sube=kayit_["sube"], ders_no=kayit_["ders_no"], ogretmen_id=kayit_["ogretmen_id"],
                        kaynak=kayit_["kaynak"], kaydeden=kayit_["kaydeden"], tahta_id=None, yok=yok, gec=gec, kim=k["ad"], an=an,
                        islem="duzelt", aciklama=aciklama,
                    )  # fmt: skip
                    vt.kayit_dus(b, k["ad"], "Yoklama düzeltildi", yk.kayit_metni(kayit_["sube"], kayit_["ders_no"], len(yok),
                                 kayit_["kod"], gun, len(gec)), ip(istek))  # fmt: skip
                    mesaj = "Düzeltme kaydedildi."
                elif eylem == "sil":
                    n = len(yk.yok_listesi(b, yoklama_id))
                    b.execute("DELETE FROM yoklama WHERE id = ?", (yoklama_id,))
                    # Ders saatinin başka kaydı kalmadıysa panel düzeltmeleri de gider: yetim düzeltme, sonradan yeniden
                    # alınan yoklamanın üstünde durmasın (birleşim kuralı da kayıttan eski düzeltmeyi yok sayar).
                    hucre = (kayit_["tarih"], kayit_["sube"], kayit_["ders_no"])
                    if not b.execute("SELECT 1 FROM yoklama WHERE tarih = ? AND sube = ? AND ders_no = ? LIMIT 1", hucre).fetchone():
                        b.execute("DELETE FROM yoklama_duzeltme WHERE tarih = ? AND sube = ? AND ders_no = ?", hucre)
                    # yoklama_iz kayıtla birlikte silindiği için gerekçe işlem kaydına yazılır (tc_kimlik_var'dan geçti).
                    vt.kayit_dus(b, k["ad"], "Yoklama silindi", yk.kayit_metni(kayit_["sube"], kayit_["ders_no"], n, kayit_["kod"], gun)
                                 + f" · gerekçe: {aciklama}", ip(istek))  # fmt: skip
                    donus, mesaj = f"/yoklama?tarih={kayit_['tarih']}", "Yoklama kaydı silindi."
                else:
                    raise ValueError("Bilinmeyen işlem.")
        except ValueError as hata:
            return y.yonlendir(donus, str(hata), hata=True)
        if eylem == "sil":
            vt.wal_buda()
        return y.yonlendir(donus, mesaj)

    # ---- panelden yoklama ---------------------------------------------------------------------------
    def gir_tarihleri(an: int) -> list[dict]:
        bugun = yk.bugun(an)
        return [{"iso": (bugun - timedelta(days=i)).isoformat(), "yazi": yk.tarih_yazi(bugun - timedelta(days=i))}
                for i in range(yk.PANEL_GERI_GUN + 1)]  # fmt: skip

    def gir_tarihi(deger, an: int):
        gun = yk.tarih_coz(deger)
        bugun = yk.bugun(an)
        if not gun or not bugun - timedelta(days=yk.PANEL_GERI_GUN) <= gun <= bugun:
            raise ValueError(f"Panelden yoklama yalnız bugün ve son {yk.PANEL_GERI_GUN} gün için girilebilir.")
        return gun

    @uygulama.get("/yoklama/gir", response_class=HTMLResponse)
    async def gir_formu(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        an = vt.simdi()
        q = istek.query_params
        try:
            gun = gir_tarihi(q.get("tarih") or yk.bugun(an).isoformat(), an)
        except ValueError as hata:
            return y.yonlendir("/yoklama", str(hata), hata=True)
        sube = metin.sube_duzelt(q.get("sube", "")) if q.get("sube") else None
        ders_no = _tamsayi(q.get("ders_no"))
        ogretmen_id = _tamsayi(q.get("ogretmen_id"))
        with vt.islem() as b:
            subeler = yk.aktif_subeler(b)
            saatler = yk.program_ders_saatleri(b, gun, sube) if sube else []
            ogrenciler, onceki, baska = [], [], False
            if sube and sube in subeler:
                ogrenciler = [{"id": o["id"], "okul_no": o["okul_no"], "ad_soyad": yk.ad_soyad(o)}
                              for o in yk.ogrenci_sirala(yk.sube_ogrencileri(b, sube))]  # fmt: skip
                if ders_no:
                    # 0.14.0: form ders saatinin GEÇERLİ durumuyla açılır (en son kaydedilen kayıt + panel düzeltmesi);
                    # kaydedilen gövde tam durum olduğu için başka kayıttaki işaretler kaybolmaz.
                    onceki = sorted(yk.gecerli_durum(b, gun.isoformat(), sube, ders_no)[0] & {o["id"] for o in ogrenciler})
                    baska = yk.baska_yoklama_var(b, gun.isoformat(), sube, ders_no, ogretmen_id, "panel")
            ogretmenler = ogretmen_secenekleri(b)
        return y.sayfa(
            istek, "yoklama_gir.html", k,
            tarihler=gir_tarihleri(an), tarih=gun.isoformat(), tarih_yazi=yk.tarih_yazi(gun), subeler=subeler, sube=sube or "",
            ders_saatleri=[{"ders_no": s["ders_no"], "metin": f"{s['ders_no']}. ders ({s['baslangic']}–{s['bitis']})"} for s in saatler]
            or [{"ders_no": n, "metin": f"{n}. ders"} for n in range(1, yk.DERS_NO_EN_COK + 1)],
            ders_no=ders_no, ogretmenler=ogretmenler, ogretmen_id=ogretmen_id, ogrenciler=ogrenciler, yok=set(onceki),
            baska_yoklama=baska, adli_not=yk.ILETI_ADLI_SAYFA,
        )  # fmt: skip

    @uygulama.post("/yoklama/gir")
    async def gir_kaydet(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        an = vt.simdi()
        donus = "/yoklama/gir"
        try:
            gun = gir_tarihi(form.get("tarih"), an)
            sube = metin.sube_duzelt(form.get("sube", ""))
            ders_no = _tamsayi(form.get("ders_no"))
            donus = f"/yoklama/gir?tarih={gun.isoformat()}" + (f"&sube={sube}" if sube else "")
            if not sube:
                raise ValueError("Şubeyi seçin.")
            ogretmen_id = _tamsayi(form.get("ogretmen_id")) if str(form.get("ogretmen_id", "")).strip() else None
            with vt.islem() as b:
                ogrenciler = yk.sube_ogrencileri(b, sube)
                if not ogrenciler:
                    raise ValueError(yk.ILETI_LISTE_YOK)
                hata = yk.ders_no_denetle(b, gun, sube, ders_no, an)
                if hata:
                    raise ValueError(hata)
                kod = None
                if ogretmen_id is not None:
                    ogr = b.execute("SELECT p.kod FROM ogretmen o JOIN ogretmen_pin p ON p.ogretmen_id = o.id WHERE o.id = ?",
                                    (ogretmen_id,)).fetchone()  # fmt: skip
                    if not ogr:
                        raise ValueError("Öğretmen bulunamadı.")
                    kod = ogr["kod"]
                yok = yk.yok_idleri_coz([str(x) for x in form.getlist("yok")], {o["id"] for o in ogrenciler})
                yk.yoklama_yaz(b, tarih=gun.isoformat(), sube=sube, ders_no=ders_no, ogretmen_id=ogretmen_id, kaynak="panel",
                               kaydeden=k["ad"], tahta_id=None, yok=yok, kim=k["ad"], an=an)  # fmt: skip
                vt.kayit_dus(b, k["ad"], "Yoklama girildi (panel)", yk.kayit_metni(sube, ders_no, len(yok), kod, gun), ip(istek))
        except ValueError as hata:
            return y.yonlendir(donus, str(hata), hata=True)
        return y.yonlendir(f"/yoklama?tarih={gun.isoformat()}",
                           f"{sube} {ders_no}. ders: yoklama kaydedildi, {len(yok)} öğrenci yok ({len(ogrenciler)} mevcut).")  # fmt: skip

    # ---- icmal ve e-Okul işareti ----------------------------------------------------------------------
    @uygulama.get("/yoklama/icmal", response_class=HTMLResponse)
    async def icmal_sayfasi(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        an = vt.simdi()
        gun = gun_al(istek.query_params.get("tarih"), an)
        sube = metin.sube_duzelt(istek.query_params.get("sube", "")) if istek.query_params.get("sube") else None
        with vt.islem() as b:
            veri = yk.icmal(b, gun, sube)
            subeler = yk.aktif_subeler(b)
            vt.kayit_dus(b, k["ad"], "Devamsızlık icmali açıldı", f"{yk.tarih_kisa(gun)}, {sube or 'tüm şubeler'}", ip(istek))
        return y.sayfa(istek, "yoklama_icmal.html", k, icmal=veri, metin=yk.icmal_metni(veri), sube=sube or "",
                       subeler=subeler, uretim=yk.an_yazi(an), adli_not=yk.ILETI_ADLI_SAYFA)  # fmt: skip

    @uygulama.get("/yoklama/icmal.csv")
    async def icmal_csv(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        an = vt.simdi()
        gun = gun_al(istek.query_params.get("tarih"), an)
        sube = metin.sube_duzelt(istek.query_params.get("sube", "")) if istek.query_params.get("sube") else None
        with vt.islem() as b:
            veri = yk.icmal(b, gun, sube)
            vt.kayit_dus(b, k["ad"], "Devamsızlık icmali indirildi (CSV)", f"{yk.tarih_kisa(gun)}, {sube or 'tüm şubeler'}", ip(istek))
        return Response(
            yk.icmal_csv(veri),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="yoklama-icmali-{gun.isoformat()}.csv"'},
        )

    @uygulama.post("/yoklama/islendi")
    async def islendi(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        an = vt.simdi()
        gun = yk.tarih_coz(form.get("tarih"))
        sube = metin.sube_duzelt(form.get("sube", ""))
        if not gun or not sube:
            return y.yonlendir("/yoklama", "Tarih ya da şube geçersiz.", hata=True)
        deger = str(form.get("deger", "")) == "1"
        with vt.islem() as b:
            if deger:
                b.execute(
                    "INSERT INTO eokul_islendi (tarih, sube, kullanici, zaman) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(tarih, sube) DO UPDATE SET kullanici = excluded.kullanici, zaman = excluded.zaman",
                    (gun.isoformat(), sube, k["ad"], an),
                )
            else:
                b.execute("DELETE FROM eokul_islendi WHERE tarih = ? AND sube = ?", (gun.isoformat(), sube))
            vt.kayit_dus(b, k["ad"], "e-Okul'a işlendi işaretlendi" if deger else "e-Okul işareti kaldırıldı",
                         f"{yk.tarih_kisa(gun)}, {sube}", ip(istek))  # fmt: skip
        return y.yonlendir(f"/yoklama?tarih={gun.isoformat()}#e-okul",
                           f"{sube}: e-Okul'a işlendi." if deger else f"{sube}: e-Okul işareti kaldırıldı.")  # fmt: skip

    # ---- öğretmenler ve PIN ---------------------------------------------------------------------------
    @uygulama.get("/ogretmenler", response_class=HTMLResponse)
    async def ogretmenler_sayfasi(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        with vt.islem() as b:
            liste = yk.ogretmen_listesi(b, vt.simdi())
            usb_sayilari = usb_anahtar.ogretmen_sayilari(b)  # 0.11.0: "USB anahtar" sütunu
        return y.sayfa(istek, "ogretmenler.html", k, ogretmenler=liste, yonetici=k["rol"] == "yonetici", usb_sayilari=usb_sayilari,
                       pin_yok_sayisi=sum(1 for o in liste if o["aktif"] and o["pin_durumu"] == "yok"))  # fmt: skip

    def pusula_sayfasi(istek: Request, k, pusulalar: list[dict]) -> HTMLResponse:
        return y.sayfa(istek, "ogretmen_pusula.html", k, pusulalar=pusulalar)

    @uygulama.post("/ogretmenler")
    async def ogretmen_islem(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        eylem = str(form.get("eylem", ""))
        an = vt.simdi()
        donus = "/ogretmenler"
        if eylem in ("ekle", "duzenle", "durum", "toplu_pin"):
            red = yonetici_gerek(istek, k, f"Öğretmen işlemi ({eylem})", donus)
            if red:
                return red
        try:
            with vt.islem() as b:
                if eylem == "ekle":
                    ad, soyad = yk.ogretmen_adi_coz(form.get("ad"), form.get("soyad"))
                    kod = str(form.get("kod", "")).strip() or yk.kod_uret(b)
                    if not yk.kod_gecerli(kod):
                        raise ValueError("Öğretmen kodu 101–999 arasında 3 haneli olmalı.")
                    if b.execute("SELECT 1 FROM ogretmen_pin WHERE kod = ?", (kod,)).fetchone():
                        raise ValueError(f"{kod} kodu başka bir öğretmende.")
                    oid = b.execute("INSERT INTO ogretmen (ad, soyad, aktif) VALUES (?, ?, 1)", (ad, soyad)).lastrowid
                    b.execute("INSERT INTO ogretmen_pin (ogretmen_id, kod) VALUES (?, ?)", (oid, kod))
                    vt.kayit_dus(b, k["ad"], "Öğretmen eklendi", f"kod {kod}", ip(istek))
                    return y.yonlendir(donus, f"Öğretmen eklendi (kod {kod}). PIN üretmeyi unutmayın.")
                if eylem == "toplu_pin":
                    satirlar = b.execute(
                        "SELECT o.*, p.kod FROM ogretmen o JOIN ogretmen_pin p ON p.ogretmen_id = o.id "
                        "WHERE o.aktif = 1 AND p.pin_ozet IS NULL"
                    ).fetchall()
                    if not satirlar:
                        raise ValueError("PIN'i olmayan etkin öğretmen yok.")
                    pusulalar = []
                    for o in sorted(satirlar, key=lambda o: (metin.tr_sirala_anahtari(o["soyad"]), metin.tr_sirala_anahtari(o["ad"]))):
                        pin = yk.pin_ver(b, o["id"], an)
                        pusulalar.append({"ad_soyad": yk.ogretmen_tam_ad(o), "kod": o["kod"], "pin": yk.pin_bicimli(pin)})
                    vt.kayit_dus(b, k["ad"], "Toplu PIN üretildi", f"{len(pusulalar)} öğretmen", ip(istek))
                    return pusula_sayfasi(istek, k, pusulalar)
                o = b.execute(
                    "SELECT o.*, p.kod FROM ogretmen o JOIN ogretmen_pin p ON p.ogretmen_id = o.id WHERE o.id = ?",
                    (_tamsayi(form.get("id"), -1),),
                ).fetchone()
                if not o:
                    raise ValueError("Öğretmen bulunamadı.")
                if eylem == "pin_uret":
                    if not o["aktif"]:
                        raise ValueError("Pasif öğretmene PIN üretilmez; önce etkinleştirin.")
                    pin = yk.pin_ver(b, o["id"], an)
                    vt.kayit_dus(b, k["ad"], "Öğretmen PIN'i üretildi", f"kod {o['kod']}", ip(istek))
                    return pusula_sayfasi(istek, k, [{"ad_soyad": yk.ogretmen_tam_ad(o), "kod": o["kod"], "pin": yk.pin_bicimli(pin)}])
                if eylem == "pin_kilit_ac":
                    b.execute("UPDATE ogretmen_pin SET kilitli = 0, hatali_sayi = 0, hatali_ilk = NULL WHERE ogretmen_id = ?", (o["id"],))
                    vt.kayit_dus(b, k["ad"], "Öğretmen PIN kilidi açıldı", f"kod {o['kod']}", ip(istek))
                    return y.yonlendir(donus, f"Kod {o['kod']}: PIN kilidi açıldı (aynı PIN geçerli).")
                if eylem == "duzenle":
                    ad, soyad = yk.ogretmen_adi_coz(form.get("ad"), form.get("soyad"))
                    kod = str(form.get("kod", "")).strip() or o["kod"]
                    if not yk.kod_gecerli(kod):
                        raise ValueError("Öğretmen kodu 101–999 arasında 3 haneli olmalı.")
                    if kod != o["kod"] and b.execute("SELECT 1 FROM ogretmen_pin WHERE kod = ?", (kod,)).fetchone():
                        raise ValueError(f"{kod} kodu başka bir öğretmende.")
                    b.execute("UPDATE ogretmen SET ad = ?, soyad = ? WHERE id = ?", (ad, soyad, o["id"]))
                    b.execute("UPDATE ogretmen_pin SET kod = ? WHERE ogretmen_id = ?", (kod, o["id"]))
                    if kod != o["kod"]:
                        yk.oturumlari_dusur(b, o["id"])
                    vt.kayit_dus(b, k["ad"], "Öğretmen düzenlendi", f"kod {o['kod']}" + (f" → {kod}" if kod != o["kod"] else ""), ip(istek))
                    return y.yonlendir(donus, "Öğretmen kaydedildi.")
                if eylem == "durum":
                    yeni = 0 if o["aktif"] else 1
                    b.execute("UPDATE ogretmen SET aktif = ? WHERE id = ?", (yeni, o["id"]))
                    if not yeni:
                        yk.oturumlari_dusur(b, o["id"])
                    vt.kayit_dus(b, k["ad"], "Öğretmen etkinleştirildi" if yeni else "Öğretmen pasifleştirildi", f"kod {o['kod']}", ip(istek))
                    return y.yonlendir(donus, f"Kod {o['kod']}: {'etkinleştirildi' if yeni else 'pasifleştirildi; tahtadan PIN girişi reddedilir'}.")
                raise ValueError("Bilinmeyen işlem.")
        except ValueError as hata:
            return y.yonlendir(donus, str(hata), hata=True)

    # ---- öğrenciler ve aktarma ------------------------------------------------------------------------
    def ogrenciler_sayfasi(istek: Request, k, sube: str | None, durum_kodu: int = 200, **ek) -> HTMLResponse:
        with vt.islem() as b:
            subeler = sorted(
                ({"sube": s["sube"], "sayi": s["n"]} for s in
                 b.execute("SELECT sube, COUNT(*) AS n FROM ogrenci WHERE aktif = 1 GROUP BY sube")),
                key=lambda x: yk.sube_anahtari(x["sube"]),
            )  # fmt: skip
            ogrenciler = []
            if sube:
                ogrenciler = [{"okul_no": o["okul_no"], "ad": o["ad"], "soyad": o["soyad"]}
                              for o in yk.ogrenci_sirala(yk.sube_ogrencileri(b, sube))]  # fmt: skip
            aktarimlar = [
                {"zaman": yk.an_yazi(a["zaman"]), "kullanici": a["kullanici"], "bicim": eokul.BICIM_ADI.get(a["bicim"], a["bicim"]),
                 "sube_sayisi": a["sube_sayisi"], "eklenen": a["eklenen"], "guncellenen": a["guncellenen"], "pasif": a["pasif"],
                 "atlanan": a["atlanan"]}  # fmt: skip
                for a in b.execute("SELECT * FROM ogrenci_aktarim ORDER BY id DESC LIMIT 5")
            ]
            toplam = b.execute("SELECT COUNT(*) FROM ogrenci WHERE aktif = 1").fetchone()[0]
            pasif = b.execute("SELECT COUNT(*) FROM ogrenci WHERE aktif = 0").fetchone()[0]
        return y.sayfa(istek, "ogrenciler.html", k, durum_kodu=durum_kodu, subeler=subeler, sube=sube or "", ogrenciler=ogrenciler,
                       aktarimlar=aktarimlar, toplam=toplam, pasif=pasif, yonetici=k["rol"] == "yonetici",
                       dosya_siniri_mb=eokul.DOSYA_SINIRI // (1024 * 1024), satir_siniri=eokul.SATIR_SINIRI,
                       adli_not=yk.ILETI_ADLI_SAYFA, **ek)  # fmt: skip

    @uygulama.get("/ogrenciler", response_class=HTMLResponse)
    async def ogrenciler(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        sube = metin.sube_duzelt(istek.query_params.get("sube", "")) if istek.query_params.get("sube") else None
        return ogrenciler_sayfasi(istek, k, sube)

    @uygulama.post("/ogrenciler/onizle")
    async def ogrenci_onizle(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        donus = "/ogrenciler"
        red = yonetici_gerek(istek, k, "Öğrenci listesi aktarma", donus)  # yetki, form ayrıştırılmadan önce
        if red:
            return red
        uzunluk = govde_uzunlugu(istek)
        if uzunluk is None:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        if uzunluk > eokul.DOSYA_SINIRI + 64 * 1024:
            return y.yonlendir(donus, f"Dosya en çok {eokul.DOSYA_SINIRI // (1024 * 1024)} MB olabilir.", hata=True)
        try:
            form = await bellekte_form(istek, eokul.DOSYA_SINIRI + 64 * 1024)
        except Exception:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        try:
            dosya = form.get("dosya")
            if not isinstance(dosya, UploadFile) or not dosya.filename:
                return y.yonlendir(donus, "Dosya seçilmedi.", hata=True)
            veri = await dosya.read(eokul.DOSYA_SINIRI + 1)
        finally:
            await form.close()
        try:
            ayristirma = eokul.ogrenci_listesi_oku(veri)
        except ValueError as hata:
            with vt.islem() as b:
                vt.kayit_dus(b, k["ad"], "Öğrenci listesi reddedildi", str(hata)[:200], ip(istek))
            return y.yonlendir(donus, str(hata), hata=True)
        finally:
            del veri
        if not ayristirma["satirlar"]:
            return y.yonlendir(donus, f"Dosyada aktarılabilecek öğrenci satırı yok ({len(ayristirma['atlanan'])} satır atlandı).", hata=True)
        with vt.islem() as b:
            plan = yk.aktarim_plani(b, ayristirma)
            vt.kayit_dus(b, k["ad"], "Öğrenci listesi önizlendi",
                         f"{len(plan['subeler'])} şube, {plan['toplam']['dosyada']} satır, {len(ayristirma['atlanan'])} atlandı", ip(istek))  # fmt: skip
        belirtec = depo.koy(k["id"], ayristirma)
        return y.sayfa(istek, "ogrenci_onizleme.html", k, plan=plan, ayristirma=ayristirma, onizleme=belirtec,
                       omur_dk=yk.ONIZLEME_OMRU_SN // 60, adli_not=yk.ILETI_ADLI_SAYFA)  # fmt: skip

    @uygulama.post("/ogrenciler/aktar")
    async def ogrenci_aktar(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        donus = "/ogrenciler"
        red = yonetici_gerek(istek, k, "Öğrenci listesi aktarma", donus)
        if red:
            return red
        form = await istek.form()
        ayristirma = depo.al(str(form.get("onizleme", "")), k["id"])
        if not ayristirma or "satirlar" not in ayristirma:  # depo mazeret önizlemesiyle ortaktır
            return y.yonlendir(donus, "Önizlemenin süresi doldu; dosyayı yeniden yükleyin.", hata=True)
        with vt.islem() as b:
            s = yk.ogrenci_aktar(b, ayristirma, k["ad"], vt.simdi())
            vt.kayit_dus(b, k["ad"], "Öğrenci listesi aktarıldı",
                         f"{s['sube_sayisi']} şube · {s['eklenen']} eklendi, {s['guncellenen']} güncellendi, {s['pasif']} pasif, "
                         f"{s['atlanan']} satır atlandı", ip(istek))  # fmt: skip
        return y.yonlendir(donus, f"Aktarıldı: {s['sube_sayisi']} şube, {s['eklenen']} öğrenci eklendi, {s['guncellenen']} güncellendi, "
                                  f"{s['pasif']} pasifleşti, {s['atlanan']} satır atlandı.")  # fmt: skip

    @uygulama.post("/ogrenciler/temizle")
    async def ogrenci_temizle(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        donus = "/ogrenciler"
        red = yonetici_gerek(istek, k, "Öğrenci ve yoklama verisini silme", donus)
        if red:
            return red
        form = await istek.form()
        if str(form.get("onay", "")).strip() != "SİL":
            return y.yonlendir(donus, "Silmek için onay kutusuna büyük harflerle SİL yazın.", hata=True)
        with vt.islem() as b:
            ogrenci, yoklama_ = yk.hepsini_sil(b)
            vt.kayit_dus(b, k["ad"], "Tüm öğrenci ve yoklama verisi silindi", f"{ogrenci} öğrenci, {yoklama_} yoklama", ip(istek))
        depo.bosalt()
        vt.wal_buda()
        return y.yonlendir(donus, f"Silindi: {ogrenci} öğrenci, {yoklama_} yoklama kaydı.")

    # ---- tahta (ajan) uçları -------------------------------------------------------------------------
    async def ajan_govdesi(istek: Request, etkinlik_gerek: bool = True):
        tahta = y.tahta_dogrula(istek)
        if not tahta:
            return None, JSONResponse({"hata": "Tahta tanınmıyor."}, status_code=401)
        if tahta["durum"] != "onayli":
            return None, JSONResponse({"hata": "Tahta onaylı değil."}, status_code=403)
        uzunluk = istek.headers.get("content-length", "")
        if uzunluk and (not metin.rakam_mi(uzunluk) or int(uzunluk) > yk.GOVDE_SINIRI):
            return None, JSONResponse({"hata": "İstek çok büyük."}, status_code=413)
        govde_bayt = await istek.body()
        if len(govde_bayt) > yk.GOVDE_SINIRI:
            return None, JSONResponse({"hata": "İstek çok büyük."}, status_code=413)
        try:
            govde = json.loads(govde_bayt or b"{}")
        except (ValueError, UnicodeDecodeError):
            return None, JSONResponse({"hata": "Geçersiz istek."}, status_code=400)
        if not isinstance(govde, dict):
            return None, JSONResponse({"hata": "Geçersiz istek."}, status_code=400)
        if etkinlik_gerek:
            with vt.islem() as b:
                if not yk.etkin(b):
                    return None, JSONResponse({"hata": yk.ILETI_ETKIN_DEGIL}, status_code=409)
        return (tahta, govde), None

    def sinavda(b, tahta, an: int) -> bool:
        return sinav.tahta_sinav_penceresinde(b, tahta["id"], an)

    def yetenekli(tahta) -> bool:
        """Tahta yoklama_gec bildiriyor mu? Karar istekteki anahtara göre değil, yeteneğe göre verilir."""
        return yk.GEC_YETENEGI in acil.yetenekler(tahta)

    @uygulama.post("/ajan/yoklama/oneri")
    async def ajan_oneri(istek: Request):
        cozulen, hata = await ajan_govdesi(istek)
        if hata:
            return hata
        tahta, govde = cozulen
        an = vt.simdi()
        with vt.islem() as b:
            if sinavda(b, tahta, an):
                return JSONResponse({"hata": yk.ILETI_SINAV}, status_code=409)
            istek_sube = govde.get("sube") if isinstance(govde.get("sube"), str) else None
            return yk.oneri(b, tahta, an, istek_sube, yetenekli(tahta))

    @uygulama.post("/ajan/yoklama/baslat")
    async def ajan_baslat(istek: Request):
        cozulen, hata = await ajan_govdesi(istek)
        if hata:
            return hata
        tahta, govde = cozulen
        an = vt.simdi()
        kod = str(govde.get("kod", ""))[:8]
        kayit_kodu = kod if yk.kod_gecerli(kod) else "?"
        kim = f"tahta:{tahta['ad']}"
        with vt.islem() as b:
            if sinavda(b, tahta, an):
                return JSONResponse({"hata": yk.ILETI_SINAV}, status_code=409)
            durum, ogr, bekleme = yk.pin_dogrula(b, kapi, kod, govde.get("pin", ""), tahta["id"], an)
            if durum == "bekle":
                # İleti kapının güncel durumundan: tahta düzeyinde kapanma sürerken de "10 dakika kapalı" denir.
                ileti = kapi.bekleme(tahta["id"], kod, an)[1] or yk.ILETI_BEKLE
                neden = "tahta kapalı" if ileti == yk.ILETI_TAHTA_KAPALI else "öğretmen kodu bekletmede"
                vt.kayit_dus(b, kim, "Yoklama PIN girişi bekletildi", f"öğretmen kodu {kayit_kodu}, {bekleme} sn, {neden}", ip(istek))
                return JSONResponse({"hata": ileti, "bekleme_sn": bekleme}, status_code=429)
            if durum == "kilitli":
                vt.kayit_dus(b, kim, "Kilitli PIN ile yoklama denemesi", f"öğretmen kodu {kayit_kodu}", ip(istek))
                return JSONResponse({"hata": yk.ILETI_KILITLI, "bekleme_sn": 0}, status_code=423)
            if durum != "tamam":
                vt.kayit_dus(b, kim, "Hatalı yoklama PIN'i", f"öğretmen kodu {kayit_kodu}", ip(istek))
                return JSONResponse({"hata": yk.ILETI_HATALI, "bekleme_sn": 0}, status_code=403)
            ayar_ = yk.ayar_al(b)
            belirtec, bitis = yk.oturum_ac(b, ogr["id"], tahta["id"], an, ayar_["oturum_dk"])
            vt.kayit_dus(b, kim, "Yoklama oturumu açıldı", f"öğretmen kodu {ogr['kod']}", ip(istek))
            # PIN doğrulandı: öğretmenin programından ön seçim (yalnız şube ve ders no; ad ve ders adı yok).
            program = yk.ogretmen_onerisi(b, ogr["id"], tahta, an, yetenekli(tahta))
        return {"belirtec": belirtec, "kalan_sn": bitis - an, "bosta_sn": ayar_["bosta_dk"] * 60,
                "ogretmen": {"kod": ogr["kod"], "etiket": yk.ogretmen_etiketi(ogr["ad"], ogr["soyad"])},
                "oneri": program["oneri"], "subeler_once": program["subeler_once"]}  # fmt: skip

    def liste_denetimi(b, tahta, govde, an: int):
        """(oturum, şube, ders_no) ya da JSONResponse (hata). Sınıf başkanı oturumunda (0.21.0) ayrıca
        `yk.baskan_denetle`: kendi şubesi, kendi dersliği, şu anki ders, öğretmen önceliği (/liste ve /kaydet)."""
        oturum = yk.oturum_coz(b, govde.get("belirtec"), tahta["id"], an)
        if not oturum:
            return JSONResponse({"hata": yk.ILETI_OTURUM_BITTI}, status_code=401)
        sube = metin.sube_duzelt(govde.get("sube")) if isinstance(govde.get("sube"), str) else None
        if not sube:
            return JSONResponse({"hata": "Şubeyi seçin."}, status_code=400)
        ders_no = govde.get("ders_no")
        hata = yk.ders_no_denetle(b, yk.bugun(an), sube, ders_no, an)
        if hata:
            return JSONResponse({"hata": hata}, status_code=400)
        if oturum["tur"] == "baskan":
            red = yk.baskan_denetle(b, tahta, oturum, sube, int(ders_no), an)
            if red:
                return JSONResponse({"hata": red[1]}, status_code=red[0])
        return oturum, sube, int(ders_no)

    @uygulama.post("/ajan/yoklama/liste")
    async def ajan_liste(istek: Request):
        cozulen, hata = await ajan_govdesi(istek)
        if hata:
            return hata
        tahta, govde = cozulen
        an = vt.simdi()
        with vt.islem() as b:
            sonuc = liste_denetimi(b, tahta, govde, an)
            if isinstance(sonuc, JSONResponse):
                return sonuc
            oturum, sube, ders_no = sonuc
            gun = yk.bugun(an)
            tarih = gun.isoformat()
            # Sıra okul numarasıdır (sayısal; numarasız öğrenci sonda); ajan sırayı korur.
            ogrenciler = yk.ogrenci_sirala(sorted(yk.sube_ogrencileri(b, sube), key=lambda o: o["id"]))
            etiketler = maske.sinif_etiketleri(ogrenciler, yk.ayar_al(b)["maske"])
            gecerli = {o["id"] for o in ogrenciler}
            ogretmen_id = oturum["ogretmen_id"] if oturum["tur"] == "ogretmen" else None  # idare oturumu öğretmensizdir
            # Ders saatinin GEÇERLİ durumu (en son kaydedilen kayıt + panel düzeltmesi); kimin kaydı olduğu yanıtta yok.
            # Mazeret bu yanıtı değiştirmez (tahtaya mazeret, geçmiş gün ve tür gitmez).
            yok_k, gec_k, _alindi = yk.gecerli_durum(b, tarih, sube, ders_no)
            gec_sec = yk.gec_secilebilir(b, gun, sube, ders_no)
            yok = sorted(yok_k & gecerli)
            gec = sorted(gec_k & gecerli) if gec_sec else []
            eski_ajan = not yetenekli(tahta)
            liste = [{"id": o["id"], "etiket": maske.gec_ekli(etiketler[o["id"]]) if eski_ajan and o["id"] in gec else etiketler[o["id"]]}
                     for o in ogrenciler]  # fmt: skip
            baska = yk.baska_yoklama_var(b, tarih, sube, ders_no, ogretmen_id, yk.oturum_kaynagi(oturum))
        yanit = {"sube": sube, "ders_no": ders_no, "ders_adi": "", "ogrenciler": liste, "yok": yok, "gec": gec,
                 "gec_secilebilir": gec_sec, "baska_yoklama": baska, "kalan_sn": oturum["bitis"] - an, "mevcut": len(liste)}  # fmt: skip
        if not liste:
            yanit["ileti"] = yk.ILETI_LISTE_YOK
        return yanit

    @uygulama.post("/ajan/yoklama/kaydet")
    async def ajan_kaydet(istek: Request):
        cozulen, hata = await ajan_govdesi(istek)
        if hata:
            return hata
        tahta, govde = cozulen
        an = vt.simdi()
        with vt.islem() as b:
            sonuc = liste_denetimi(b, tahta, govde, an)
            if isinstance(sonuc, JSONResponse):
                return sonuc
            oturum, sube, ders_no = sonuc
            ogrenciler = yk.sube_ogrencileri(b, sube)
            if not ogrenciler:
                return JSONResponse({"hata": yk.ILETI_LISTE_YOK}, status_code=409)
            if not isinstance(govde.get("yok"), list) or len(govde["yok"]) > yk.YOK_EN_COK:
                return JSONResponse({"hata": "Geçersiz istek."}, status_code=400)
            idler = {o["id"] for o in ogrenciler}
            gun = yk.bugun(an)
            gec_sec = yk.gec_secilebilir(b, gun, sube, ders_no)
            gec_bilir = yetenekli(tahta)
            # Yetenekli ajanda gec zorunludur (boş liste dahil): gövde öğretmenin gördüğü TAM durumdur.
            if gec_bilir and (not isinstance(govde.get("gec"), list) or len(govde["gec"]) > yk.YOK_EN_COK):
                return JSONResponse({"hata": "Geçersiz istek."}, status_code=400)
            try:
                yok = yk.yok_idleri_coz(govde["yok"], idler)
                gec = yk.yok_idleri_coz(govde["gec"], idler) if gec_bilir else None
            except ValueError as hata_:
                return JSONResponse({"hata": str(hata_)}, status_code=409)
            if gec is None:
                # Eski ajan geçi bilmez: geçerli durumdaki geç öğrenciler bu kayda da geç yazılır; yalnız yeni
                # "yok"a girenler geçten çıkar.
                gec = sorted((yk.gecerli_durum(b, gun.isoformat(), sube, ders_no)[1] & idler) - set(yok)) if gec_sec else []
            if set(yok) & set(gec):
                return JSONResponse({"hata": yk.ILETI_HEM_YOK_HEM_GEC}, status_code=400)
            if gec and not gec_sec:
                return JSONResponse({"hata": yk.ILETI_GEC_ILK_DERS}, status_code=400)
            # 0.11.0: idare USB anahtarıyla açılan oturumda öğretmen yoktur; kayıt "kullanici:<ad>" adına yazılır.
            # 0.21.0: sınıf başkanı oturumu kaynak='baskan', kaydeden 'baskan:10/A' (kişi adı yok).
            ogretmen_id, kaydeden, kim = yk.oturum_kaydedeni(oturum, tahta["ad"])
            yk.yoklama_yaz(b, tarih=gun.isoformat(), sube=sube, ders_no=ders_no, ogretmen_id=ogretmen_id,
                           kaynak=yk.oturum_kaynagi(oturum), kaydeden=kaydeden, tahta_id=tahta["id"], yok=yok, gec=gec, kim=kim,
                           an=an)  # fmt: skip
            b.execute("DELETE FROM yoklama_belirtec WHERE belirtec_ozet = ?", (oturum["belirtec_ozet"],))  # kaydet tek seferliktir
            ayrinti = yk.kayit_metni(sube, ders_no, len(yok), oturum["kod"] if oturum["tur"] == "ogretmen" else None,
                                     gec_sayisi=len(gec))  # fmt: skip
            if oturum["tur"] == "idare":
                ayrinti += f", kullanıcı {oturum['kullanici_ad']}"
            elif oturum["tur"] == "baskan":
                ayrinti += ", sınıf başkanı anahtarı"
            if oturum["anahtar_kimlik"]:
                ayrinti += f" · USB {oturum['anahtar_kimlik'][:4]}-{oturum['anahtar_kimlik'][4:]}"
            vt.kayit_dus(b, f"tahta:{tahta['ad']}", "Yoklama alındı", ayrinti, ip(istek))
        return {"tamam": True, "yok_sayisi": len(yok), "gec_sayisi": len(gec), "mevcut": len(ogrenciler)}

    @uygulama.post("/ajan/yoklama/bitir")
    async def ajan_bitir(istek: Request):
        cozulen, hata = await ajan_govdesi(istek, etkinlik_gerek=False)
        if hata:
            return hata
        tahta, govde = cozulen
        with vt.islem() as b:
            oturum = yk.oturum_coz(b, govde.get("belirtec"), tahta["id"], vt.simdi())
            if oturum:
                b.execute("DELETE FROM yoklama_belirtec WHERE belirtec_ozet = ?", (oturum["belirtec_ozet"],))
        return {"tamam": True}


# =================================================================================================
# SÖZLEŞME — şablon bağlamları (sonraki uygulayıcı için; ayrıntı raporda)
#
# Ortak: adli_not (öğrenci adı içeren her sayfanın başındaki `not` metni).
# yoklama.html: g (yoklama.gunluk_gorunum), yoklama_etkin, eksik_tahtalar[{id,ad,derslik,neden}], ogrenci_var, bugun_iso.
#   g = {tarih, tarih_yazi, bugun, onceki, sonraki, sutunlar[int], tatil,
#        satirlar[{sube, islendi, islendi_metni, hucreler[{ders_no, durum: alindi|alinmadi|bos, yok, kayit_id, kayit_sayisi, baslik}]}],
#        ozet{alinan, beklenen|None, yok_ogrenci, butun_gun_yok, islenen, sube_sayisi},
#        ogrenciler[{sube, okul_no, ad_soyad, saatler_metni, sayi, alinan, butun_gun}]}.
#   Hücre bağlantısı: alindi → /yoklama/kayit/{kayit_id}; alinmadi → /yoklama/gir?tarih=&sube=&ders_no=.
#   e-Okul formu: POST /yoklama/islendi {tarih, sube, deger=1|0}.
# yoklama_kayit.html: kayit (yoklama.kayit_ayrintisi) = {id, tarih, tarih_yazi, sube, ders_no, ders_adi, ogretmen, ogretmen_kod,
#   kaynak, kaynak_turu, olusturma, guncelleme, mevcut, yok_sayisi, ogrenciler[{id, okul_no, ad_soyad, yok, pasif}],
#   izler[{zaman, kim, islem, eklenen[ad], cikarilan[ad], aciklama}]}.
#   Formlar: POST /yoklama/kayit/{id} {eylem=duzelt, yok=<ogrenci_id> (çoklu), aciklama} · {eylem=sil, aciklama}.
# yoklama_gir.html: tarihler[{iso,yazi}], tarih, tarih_yazi, subeler[str], sube, ders_saatleri[{ders_no,metin}], ders_no,
#   ogretmenler[{id,etiket}], ogretmen_id, ogrenciler[{id,okul_no,ad_soyad}], yok (set id), baska_yoklama.
#   Seçim: GET /yoklama/gir?tarih&sube&ders_no&ogretmen_id · Kayıt: POST /yoklama/gir {tarih, sube, ders_no, ogretmen_id?, yok*}.
# yoklama_icmal.html: icmal (yoklama.icmal) = {tarih, tarih_yazi, tarih_kisa, subeler[{sube, mevcut, sutunlar, alinan,
#   alinan_metni, alinmayan, alinan_sayisi, sutun_sayisi, ogrenciler[{okul_no, ad, soyad, ad_soyad, hucreler[Y|.|-], sayi}],
#   alanlar[{ders_no, metin}]}]}, metin (kopyalanacak düz metin), sube, subeler[str], uretim.
#   CSV: GET /yoklama/icmal.csv?tarih[&sube].
# ogretmenler.html: ogretmenler[{id, ad, soyad, ad_soyad, kod, aktif, pin_durumu: var|yok|kilitli, pin_metni, hatali, kilitli}],
#   yonetici, pin_yok_sayisi. POST /ogretmenler {eylem: ekle(ad,soyad,kod?) · duzenle(id,ad,soyad,kod?) · durum(id) ·
#   toplu_pin · pin_uret(id) · pin_kilit_ac(id)}.
# ogretmen_pusula.html: pusulalar[{ad_soyad, kod, pin ("482 913")}] (yalnız POST yanıtı; no-store).
# ogrenciler.html: subeler[{sube,sayi}], sube, ogrenciler[{okul_no,ad,soyad}], aktarimlar[{zaman,kullanici,bicim,sube_sayisi,
#   eklenen,guncellenen,pasif,atlanan}], toplam, pasif, yonetici, dosya_siniri_mb, satir_siniri.
#   POST /ogrenciler/onizle multipart <input type=file name=dosya accept=".xls,.xlsx,.csv"> · POST /ogrenciler/temizle {onay=SİL}.
# ogrenci_onizleme.html: plan{subeler[{sube,dosyada,eklenecek[metin],sube_degisecek[metin],pasiflesecek[metin],guncellenecek}],
#   toplam{dosyada,eklenecek,sube_degisecek,pasiflesecek,guncellenecek}}, ayristirma{bicim,bicim_adi,notlar[],uyarilar[],
#   atlanan[{satir,neden}]}, onizleme (belirteç), omur_dk. Onay: POST /ogrenciler/aktar {onizleme}.
# _ayar_yoklama.html (/ayarlar/yoklama; bolum=yoklama): yoklama_ayari{etkin,maske,oturum_dk,bosta_dk}, yoklama_maskeleri{kod:ad},
#   yoklama_sinirlari{alan:(en_az,en_cok)}, yoklama_ogrenci_sayisi. Alanlar: yk_etkin=1, yk_maske, yk_oturum_dk, yk_bosta_dk.
#   Saklama 0.8.0'dan beri ayrı bölümdür (bolum=saklama, `saklama.py`).
#
# 0.14.0 ekleri (tahta uçlarının sözleşmesi tests/yoklama_sozlesme.json'dadır; şube defteri, son günler, mazeret/izin ve
#   öğrenci görünümü panel_defter.py'dedir):
#   g.satirlar[] += bayat (e-Okul'a işlendikten sonra değişti); hücre += gec (geç sayısı); kayit_id = en son kaydedilen kayıt.
#   kayit += gec_sayisi, gec_secilebilir; kayit.ogrenciler[] += gec; kayit.izler[] += gec_eklenen[ad], gec_cikarilan[ad].
#     Düzeltme formu: {eylem=duzelt, yok*, gec*, aciklama} (geç yalnız devrenin ilk dersinde eklenir).
#   icmal.subeler[].ogrenciler[] += gec_saatler, gec_sayisi, ozurlu_saatler, ozurlu_sayisi; hucreler[Y|Ö|G|.|-];
#     CSV'nin SONUNA iki sütun: "Geç Sayısı", "Özürlü Yok Sayısı". Mazeret türü hiçbir çıktıda yoktur.
#   Bütün sayılar tek birleşim kuralından gelir (yoklama_defter.Veri.kumeler): hücrede panel düzeltmesi varsa o, yoksa o ders
#     saatinin EN SON KAYDEDİLEN kaydı. /yoklama/gir formu ders saatinin geçerli durumuyla açılır.
#   /ajan/yoklama/oneri += subeler_once, devre_adi, simdiki_ders_no, simdiki_bitti, oneri.ders_adaylari · /baslat += oneri, subeler_once ·
#     /liste += gec, gec_secilebilir (sıra okul no) · /kaydet isteği += gec (yetenekli ajanda zorunlu), yanıtı += gec_sayisi.
# =================================================================================================
