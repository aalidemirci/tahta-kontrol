"""Sınav uçları (Aşama 4): panel sayfaları ve tahtanın gözetmen uçları (/ajan/sinav/*).

Yetki (ortak sözlük §3): sınav içe aktarma, eşleştirme, yayın, yoklama, icmal iki role
(yonetici, idareci) açık; sınav kuralları metni yalnız yöneticinin (Ayarlar, web.py).
Her yazma işlemi işlem kaydına düşer; kayda ad, maske, okul no yazılmaz (M6).
`/sinav/{id}` ve `/api/sinav/{id}` okul no göstermez; okul no yalnız yoklama ve icmalde.
Yüklenen dosya diske kalıcı yazılmaz (`form.close()` `finally` içinde).

Şablon bağlamları modül sonundaki SÖZLEŞME'dedir.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.datastructures import UploadFile

from . import acil, ayar, guvenlik, metin, sinav, vt
from .panel_program import govde_uzunlugu

gunluk = logging.getLogger("tahta-sunucu")


def _tamsayi(deger, varsayilan=None):
    s = str(deger if deger is not None else "").strip()
    return int(s) if s.isdigit() and len(s) <= 6 else varsayilan


def rapor_kunyesi(s) -> dict:
    """Kod fişi, salon yoklaması ve icmal başlığı: künyesi eksik sınavda boş ad/ayraç basılmaz."""
    zaman = f"{sinav.tarih_metni(s['baslangic'])} {sinav.saat_metni(s['baslangic'])}".strip()
    return {"id": s["id"], "ad": s["ad"] or "(künye eksik)", "zaman": zaman,
            "tarih": sinav.tarih_metni(s["baslangic"]), "saat": sinav.saat_metni(s["baslangic"])}  # fmt: skip


def sinav_gorunumu(b, s, an: int) -> dict:
    """sinav.html'in `s` bağlamı (okul no İÇERMEZ)."""
    z = sinav.zamanlar(b, s)
    evre = sinav.sinav_evresi(s, z["bitis"], an)
    silindi = bool(s["kisisel_silinme"])
    giris_oncesi = sinav.giris_oncesi_mi(s, an)
    duzenlenebilir = giris_oncesi and not silindi
    ders_sayilari = {
        r["ders_id"]: r["n"]
        for r in b.execute("SELECT ders_id, COUNT(*) AS n FROM sinav_ogrenci WHERE sinav_id = ? GROUP BY ders_id", (s["id"],))
    }
    dersler = [
        {"id": d["id"], "ad": d["ad"], "ogrenci": ders_sayilari.get(d["id"], 0), "sure_dk": d["sure_dk"], "alan": f"ders_sure_{d['id']}"}
        for d in sorted(b.execute("SELECT * FROM sinav_ders WHERE sinav_id = ?", (s["id"],)).fetchall(),
                        key=lambda d: metin.tr_sirala_anahtari(d["ad"]))  # fmt: skip
    ]
    salon_sayilari = {
        r["salon_id"]: (r["n"], r["g"])
        for r in b.execute(
            "SELECT salon_id, COUNT(*) AS n, SUM(gelmedi) AS g FROM sinav_ogrenci WHERE sinav_id = ? GROUP BY salon_id", (s["id"],)
        )
    }
    tahta_satirlari = {t["id"]: t for t in b.execute("SELECT * FROM tahta")}
    esik = an - ayar.CEVRIMICI_ESIK_SN
    salonlar = []
    for sl in sorted(b.execute("SELECT * FROM sinav_salon WHERE sinav_id = ?", (s["id"],)).fetchall(),
                     key=lambda x: sinav.sirala_anahtari(x["ad"])):  # fmt: skip
        n, g = salon_sayilari.get(sl["id"], (0, 0))
        if silindi:
            n, g = sl["ozet_mevcut"] or 0, sl["ozet_gelmeyen"] or 0
        t = tahta_satirlari.get(sl["tahta_id"]) if sl["tahta_id"] else None
        bitis = z["salon_bitis"].get(sl["id"], 0)
        sevre = sinav.salon_evresi(s, sl, bitis, an)
        canli = sinav.tahta_durum_ozeti(t, s["id"], sl["id"], esik) if t else {"cevrimici": False, "ekran": None, "ekran_metni": "Tahta yok"}
        salonlar.append(
            {
                "id": sl["id"],
                "ad": sl["ad"],
                "ogrenci": n,
                "kalabalik": n > sinav.SALON_LISTE_SINIRI,
                "tahta_id": sl["tahta_id"],
                "tahta_ad": t["ad"] if t else "",
                "tahta_kaldirilmis": bool(t and t["durum"] != "onayli"),
                "ajan_guncellenmeli": bool(t and t["durum"] == "onayli" and sinav.SINAV_YETENEGI not in acil.yetenekler(t)),
                "gozetmen_adi": sl["gozetmen_adi"],
                "alan_tahta": f"salon_{sl['id']}",
                "alan_gozetmen": f"gozetmen_{sl['id']}",
                "uzatma_dk": sl["uzatma_dk"],
                "bitis_saat": sinav.saat_metni(bitis),
                "evre": sevre,
                "evre_adi": sinav.EVRE_ADI[sevre],
                "kip_kaldirildi": bool(sl["kip_kapanma"]),
                "kip_kapatan": sl["kip_kapatan"],
                "kip_kaldirilabilir": s["durum"] == "yayinda" and sevre in ("giris", "suruyor"),
                "yoklama_alindi": sl["yoklama_zamani"] is not None,
                "yoklama_metni": (f"{sinav.kaynak_metni(sl['yoklama_kaynak'])}, {sinav.saat_metni(sl['yoklama_zamani'])}"
                                  if sl["yoklama_zamani"] else ""),  # fmt: skip
                "gelmeyen": (g or 0) if sl["yoklama_zamani"] is not None else None,
                **canli,
            }
        )
    sube_sayilari: dict[str, int] = {}
    for r in b.execute("SELECT sube, COUNT(*) AS n FROM sinav_ogrenci WHERE sinav_id = ? GROUP BY sube", (s["id"],)):
        sube_sayilari[r["sube"]] = r["n"]
    onayli = [t for t in tahta_satirlari.values() if t["durum"] == "onayli"]
    subeler = [
        {
            "sube": sube,
            "ogrenci": n,
            "tahtalar": [{"id": t["id"], "ad": t["ad"]} for t in onayli
                         if sube in [x.strip() for x in (t["subeler"] or "").split(",")]],  # fmt: skip
        }
        for sube, n in sorted(sube_sayilari.items(), key=lambda x: sinav.sirala_anahtari(x[0]))
    ]
    yayinda = s["durum"] == "yayinda"
    basladi = bool(s["baslangic"]) and an >= s["baslangic"]
    bitti = bool(s["baslangic"]) and z["bitis"] <= an
    return {
        "id": s["id"],
        "ad": s["ad"],
        "gorunen_ad": s["ad"] or "(künye eksik)",
        "tarih": sinav.tarih_metni(s["baslangic"]),
        "tarih_iso": sinav.tarih_iso(s["baslangic"]),
        "saat": sinav.saat_metni(s["baslangic"]),
        "sure_dk": s["sure_dk"],
        "donem": s["donem"],
        "durum": s["durum"],
        "evre": evre,
        "evre_adi": sinav.EVRE_ADI[evre],
        "kunye_eksik": not (s["ad"] and s["baslangic"]),
        "duzenlenebilir": duzenlenebilir,
        "eslesme_duzenlenebilir": duzenlenebilir,
        "silindi": silindi,
        "silinme_tarihi": sinav.tarih_metni(s["kisisel_silinme"]) if silindi else sinav.silinme_tarihi(s),
        "bitis_saat": sinav.saat_metni(z["bitis"]),
        "bitirildi": bool(s["bitirme"]),
        "ogrenci_sayisi": sum(x["ogrenci"] for x in salonlar),
        "dersler": dersler,
        "salonlar": salonlar,
        "subeler": subeler,
        "canli": yayinda and not silindi and evre in ("yayinda", "giris", "suruyor"),
        "islemler": {
            "kunye": duzenlenebilir,
            "yayinla": s["durum"] == "taslak" and not silindi,
            "taslaga_al": yayinda and giris_oncesi and not silindi,
            "bitir": yayinda and evre in ("giris", "suruyor"),
            "uzat": yayinda and evre == "suruyor" and not s["bitirme"],
            "kodlar_yenile": duzenlenebilir,
            "kodlar_yazdir": not silindi,
            "duyuru": yayinda and evre in ("yayinda", "giris") and not silindi,
            "yoklama": basladi and not silindi,
            "icmal": basladi or silindi,
            "kisisel_sil": bitti and not silindi,
            "sil": s["durum"] == "taslak" or bitti or silindi,
        },
    }


def api_gorunumu(g: dict) -> dict:
    """/api/sinav/{id}: canlı durum (okul no ve öğrenci verisi YOK)."""
    return {
        "id": g["id"],
        "evre": g["evre"],
        "evre_adi": g["evre_adi"],
        "bitis_saat": g["bitis_saat"],
        "salonlar": [
            {k: sl[k] for k in ("id", "ad", "tahta_id", "tahta_ad", "cevrimici", "ekran", "ekran_metni", "yoklama_alindi",
                                "yoklama_metni", "gelmeyen", "bitis_saat", "uzatma_dk", "evre", "evre_adi",
                                "kip_kaldirildi", "ajan_guncellenmeli")}  # fmt: skip
            for sl in g["salonlar"]
        ],
    }


def kaydet(uygulama, y) -> None:
    kapi = sinav.GozetmenKapisi()
    uygulama.state.gozetmen_kapisi = kapi

    def ip(istek: Request) -> str:
        return y.istemci_ip(istek)

    def sinav_al(b, sinav_id: int):
        return b.execute("SELECT * FROM sinav WHERE id = ?", (sinav_id,)).fetchone()

    def adres(sinav_id: int, ek: str = "") -> str:
        return f"/sinav/{sinav_id}{ek}"

    def tahtalari_uyandir(b, sinav_id: int, ek=()) -> list[int]:
        return sorted(set(sinav.eslesmis_tahtalar(b, sinav_id)) | set(ek))

    # ---- liste ve içe aktarma ------------------------------------------------------------------
    def liste_sayfasi(istek: Request, k, durum_kodu: int = 200, **ek) -> HTMLResponse:
        with vt.islem() as b:
            yaklasan, gecmis = sinav.liste_ozeti(b, vt.simdi())
        return y.sayfa(
            istek,
            "sinavlar.html",
            k,
            durum_kodu=durum_kodu,
            yaklasan=yaklasan,
            gecmis=gecmis,
            dosya_siniri_mb=sinav.DOSYA_SINIRI // (1024 * 1024),
            saklama_gun=sinav.SAKLAMA_GUN,
            **ek,
        )

    @uygulama.get("/sinavlar", response_class=HTMLResponse)
    async def sinavlar(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        return liste_sayfasi(istek, k)

    @uygulama.post("/sinavlar/ice-aktar")
    async def ice_aktar(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        donus = "/sinavlar"
        uzunluk = govde_uzunlugu(istek)
        if uzunluk is None:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        if uzunluk > sinav.DOSYA_SINIRI + 64 * 1024:
            return y.yonlendir(donus, f"Dosya en çok {sinav.DOSYA_SINIRI // (1024 * 1024)} MB olabilir.", hata=True)
        try:
            form = await istek.form(max_files=1, max_fields=3)
        except Exception:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        try:
            dosya = form.get("dosya")
            if not isinstance(dosya, UploadFile) or not dosya.filename:
                return y.yonlendir(donus, "Dosya seçilmedi.", hata=True)
            veri = await dosya.read(sinav.DOSYA_SINIRI + 1)
        finally:
            await form.close()
        try:
            with vt.islem() as b:
                sonuc = sinav.ice_aktar(b, veri, k["ad"], vt.simdi(), ip(istek))
        except sinav.IceAktarmaHatasi as hata:
            with vt.islem() as b:  # satır hataları okul no içerir: kayda yalnız sayı yazılır
                vt.kayit_dus(b, k["ad"], "Sınav içe aktarma reddedildi", f"{hata.toplam} satır hatası", ip(istek))
            # Hatalar okul no içerebilir: adrese (?m=) değil, aynı yanıtta sayfaya yazılır.
            return liste_sayfasi(istek, k, 400, hatalar=hata.hatalar, hata_toplam=hata.toplam)
        except ValueError as hata:
            with vt.islem() as b:
                vt.kayit_dus(b, k["ad"], "Sınav içe aktarma reddedildi", str(hata)[:200], ip(istek))
            return y.yonlendir(donus, str(hata), hata=True)
        del veri
        mesaj = " ".join([sonuc["mesaj"], *sonuc["uyarilar"]])
        with vt.islem() as b:
            idler = tahtalari_uyandir(b, sonuc["sinav_id"])
        y.uyandir_hepsi(idler)
        return y.yonlendir(adres(sonuc["sinav_id"]), mesaj)

    # ---- sınav sayfası ---------------------------------------------------------------------------
    @uygulama.get("/sinav/{sinav_id}", response_class=HTMLResponse)
    async def sinav_sayfasi(istek: Request, sinav_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        an = vt.simdi()
        with vt.islem() as b:
            s = sinav_al(b, sinav_id)
            if not s:
                return y.yonlendir("/sinavlar", "Sınav bulunamadı.", hata=True)
            g = sinav_gorunumu(b, s, an)
            tahtalar = [
                {"id": t["id"], "ad": t["ad"], "derslik": t["derslik"]}
                for t in b.execute("SELECT id, ad, derslik FROM tahta WHERE durum = 'onayli' ORDER BY derslik COLLATE NOCASE, ad COLLATE NOCASE")
            ]
        return y.sayfa(
            istek,
            "sinav.html",
            k,
            s=g,
            tahtalar=tahtalar,
            uzatma_secenekleri=sinav.UZATMA_SECENEKLERI,
            sure_araligi=sinav.SURE_ARALIGI,
            duyuru_sure_araligi=sinav.DUYURU_SURE_ARALIGI,
            duyuru_varsayilan_dk=sinav.DUYURU_VARSAYILAN_DK,
            saklama_gun=sinav.SAKLAMA_GUN,
        )

    @uygulama.get("/api/sinav/{sinav_id}")
    async def api_sinav(istek: Request, sinav_id: int):
        if not y.kullanici(istek):
            return JSONResponse({"hata": "Oturum gerekli."}, status_code=401)
        with vt.islem() as b:
            s = sinav_al(b, sinav_id)
            if not s:
                return JSONResponse({"hata": "Sınav bulunamadı."}, status_code=404)
            return api_gorunumu(sinav_gorunumu(b, s, vt.simdi()))

    @uygulama.post("/sinav/{sinav_id}/kunye")
    async def kunye(istek: Request, sinav_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        an = vt.simdi()
        donus = adres(sinav_id, "#kunye")
        try:
            with vt.islem() as b:
                s = sinav_al(b, sinav_id)
                if not s:
                    return y.yonlendir("/sinavlar", "Sınav bulunamadı.", hata=True)
                if s["kisisel_silinme"] or not sinav.giris_oncesi_mi(s, an):
                    raise ValueError("Giriş penceresi başladı; künye artık değiştirilemez.")
                ad = " ".join(str(form.get("ad", "")).split())[: sinav.SINAV_ADI_EN_UZUN]
                if not ad:
                    raise ValueError("Sınav adı boş olamaz.")
                if guvenlik.tc_kimlik_var(ad):
                    raise ValueError(guvenlik.TC_KIMLIK_ILETISI)
                baslangic = sinav.tarih_saat_coz(form.get("tarih", ""), form.get("saat", ""))
                if s["durum"] == "yayinda" and baslangic - sinav.GIRIS_ONCESI_SN <= an:
                    raise ValueError("Yayındaki sınavın yeni başlangıcı giriş penceresinden (10 dk) sonra olmalı; önce taslağa alın.")
                if baslangic <= an:
                    raise ValueError("Başlangıç saati geçmiş olamaz.")
                sure = _tamsayi(form.get("sure_dk"))
                if sure is None or not sinav.SURE_ARALIGI[0] <= sure <= sinav.SURE_ARALIGI[1]:
                    raise ValueError(f"Süre {sinav.SURE_ARALIGI[0]}–{sinav.SURE_ARALIGI[1]} dakika olmalı.")
                ders_sureleri = {}
                for d in b.execute("SELECT id, sure_dk FROM sinav_ders WHERE sinav_id = ?", (sinav_id,)):
                    deger = form.get(f"ders_sure_{d['id']}")
                    if deger is None or str(deger).strip() == "":
                        ders_sureleri[d["id"]] = d["sure_dk"]
                        continue
                    ds = _tamsayi(deger)
                    if ds is None or not sinav.SURE_ARALIGI[0] <= ds <= sinav.SURE_ARALIGI[1]:
                        raise ValueError(f"Ders süreleri {sinav.SURE_ARALIGI[0]}–{sinav.SURE_ARALIGI[1]} dakika olmalı.")
                    ders_sureleri[d["id"]] = ds
                b.execute(
                    "UPDATE sinav SET ad = ?, baslangic = ?, sure_dk = ?, guncelleme = ? WHERE id = ?",
                    (ad, baslangic, sure, an, sinav_id),
                )
                for ders_id, ds in ders_sureleri.items():
                    b.execute("UPDATE sinav_ders SET sure_dk = ? WHERE id = ?", (ds, ders_id))
                guncel = sinav_al(b, sinav_id)
                if guncel["durum"] == "yayinda":
                    eslesmeler = {sl["id"]: sl["tahta_id"] for sl in b.execute(
                        "SELECT id, tahta_id FROM sinav_salon WHERE sinav_id = ?", (sinav_id,))}  # fmt: skip
                    cakisan = sinav.cakisan_sinav(b, guncel, eslesmeler)
                    if cakisan:
                        raise ValueError(f"Aynı tahta, zamanı çakışan başka bir yayımlanmış sınavda: {cakisan}.")
                vt.kayit_dus(
                    b, k["ad"], "Sınav künyesi değiştirildi",
                    f"{ad} · {sinav.an_metni(baslangic)} · {sure} dk · {len(ders_sureleri)} ders", ip(istek),
                )  # fmt: skip
                idler = tahtalari_uyandir(b, sinav_id)
        except ValueError as hata:
            return y.yonlendir(donus, str(hata), hata=True)
        y.uyandir_hepsi(idler)
        return y.yonlendir(donus, "Künye kaydedildi.")

    @uygulama.post("/sinav/{sinav_id}/eslestir")
    async def eslestir(istek: Request, sinav_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        an = vt.simdi()
        donus = adres(sinav_id, "#salonlar")
        try:
            with vt.islem() as b:
                s = sinav_al(b, sinav_id)
                if not s:
                    return y.yonlendir("/sinavlar", "Sınav bulunamadı.", hata=True)
                if s["kisisel_silinme"]:
                    raise ValueError("Kişisel verisi silinmiş sınav düzenlenemez.")
                duzenlenebilir = sinav.giris_oncesi_mi(s, an)
                onayli = {t["id"]: t["ad"] for t in b.execute("SELECT id, ad FROM tahta WHERE durum = 'onayli'")}
                salonlar = b.execute("SELECT * FROM sinav_salon WHERE sinav_id = ?", (sinav_id,)).fetchall()
                yeni_tahta: dict[int, int | None] = {}
                yeni_gozetmen: dict[int, str] = {}
                for sl in salonlar:
                    alan = form.get(f"salon_{sl['id']}")
                    if alan is None:
                        yeni_tahta[sl["id"]] = sl["tahta_id"]
                    else:
                        deger = _tamsayi(alan)
                        if str(alan).strip() and deger is None:
                            raise ValueError("Tahta seçimi geçersiz.")
                        if deger is not None and deger not in onayli and deger != sl["tahta_id"]:
                            raise ValueError("Seçilen tahta bulunamadı ya da onaylı değil.")
                        yeni_tahta[sl["id"]] = deger
                    gozetmen = form.get(f"gozetmen_{sl['id']}")
                    yeni_gozetmen[sl["id"]] = (
                        sl["gozetmen_adi"] if gozetmen is None else " ".join(str(gozetmen).split())[: sinav.GOZETMEN_ADI_EN_UZUN]
                    )
                    if guvenlik.tc_kimlik_var(yeni_gozetmen[sl["id"]]):
                        raise ValueError(guvenlik.TC_KIMLIK_ILETISI)
                degisen_tahta = [sl for sl in salonlar if yeni_tahta[sl["id"]] != sl["tahta_id"]]
                if degisen_tahta and not duzenlenebilir:
                    raise ValueError("Giriş penceresi başladı; tahta eşleşmesi değiştirilemez. Yalnız gözetmen adları kaydedilir.")
                secilen = [t for t in yeni_tahta.values() if t]
                cift = {t for t in secilen if secilen.count(t) > 1}
                if cift:
                    raise ValueError(f"Aynı tahta iki salona seçilemez: {', '.join(onayli.get(t, f'#{t}') for t in sorted(cift))}.")
                if s["durum"] == "yayinda" and degisen_tahta:
                    cakisan = sinav.cakisan_sinav(b, s, yeni_tahta)
                    if cakisan:
                        raise ValueError(f"Aynı tahta, zamanı çakışan başka bir yayımlanmış sınavda: {cakisan}.")
                eski_tahtalar = {sl["tahta_id"] for sl in degisen_tahta if sl["tahta_id"]}
                gozetmen_degisen = 0
                for sl in salonlar:
                    if yeni_gozetmen[sl["id"]] != sl["gozetmen_adi"]:
                        gozetmen_degisen += 1
                    b.execute(
                        "UPDATE sinav_salon SET tahta_id = ?, gozetmen_adi = ? WHERE id = ?",
                        (yeni_tahta[sl["id"]], yeni_gozetmen[sl["id"]], sl["id"]),
                    )
                    if sl in degisen_tahta:
                        sinav.eslesme_hatirla(b, sl["ad"], yeni_tahta[sl["id"]])
                b.execute("UPDATE sinav SET guncelleme = ? WHERE id = ?", (an, sinav_id))
                tahtali = sum(1 for t in yeni_tahta.values() if t)
                vt.kayit_dus(
                    b, k["ad"], "Sınav salon eşleştirmesi",
                    f"{s['ad'] or f'Sınav #{sinav_id}'} · {tahtali} salon tahtalı, {len(salonlar) - tahtali} tahtasız"
                    f" · {len(degisen_tahta)} eşleşme, {gozetmen_degisen} gözetmen adı değişti", ip(istek),
                )  # fmt: skip
                idler = tahtalari_uyandir(b, sinav_id, eski_tahtalar)
        except ValueError as hata:
            return y.yonlendir(donus, str(hata), hata=True)
        y.uyandir_hepsi(idler)
        return y.yonlendir(donus, "Eşleştirme kaydedildi.")

    @uygulama.post("/sinav/{sinav_id}/durum")
    async def durum(istek: Request, sinav_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        eylem = str(form.get("eylem", ""))
        an = vt.simdi()
        donus = adres(sinav_id)
        budanacak = False
        try:
            with vt.islem() as b:
                s = sinav_al(b, sinav_id)
                if not s:
                    return y.yonlendir("/sinavlar", "Sınav bulunamadı.", hata=True)
                z = sinav.zamanlar(b, s)
                evre = sinav.sinav_evresi(s, z["bitis"], an)
                idler = tahtalari_uyandir(b, sinav_id)
                bitti = bool(s["baslangic"]) and z["bitis"] <= an
                adi = s["ad"] or f"Sınav #{sinav_id}"
                if eylem == "yayinla":
                    if s["durum"] != "taslak":
                        raise ValueError("Sınav zaten yayında.")
                    uyarilar = sinav.yayina_al_denetimi(b, s, an)
                    b.execute("UPDATE sinav SET durum = 'yayinda', guncelleme = ? WHERE id = ?", (an, sinav_id))
                    vt.kayit_dus(b, k["ad"], "Sınav yayına alındı", f"{adi} · {sinav.an_metni(s['baslangic'])}", ip(istek))
                    mesaj = " ".join(["Sınav yayına alındı.", *uyarilar])
                elif eylem == "taslaga_al":
                    if s["durum"] != "yayinda" or not sinav.giris_oncesi_mi(s, an):
                        raise ValueError("Sınav yalnız giriş penceresinden önce taslağa alınabilir.")
                    b.execute("UPDATE sinav SET durum = 'taslak', guncelleme = ? WHERE id = ?", (an, sinav_id))
                    vt.kayit_dus(b, k["ad"], "Sınav taslağa alındı", adi, ip(istek))
                    mesaj = "Sınav taslağa alındı; tahtalara gönderilmez."
                elif eylem == "bitir":
                    if s["durum"] != "yayinda" or evre not in ("giris", "suruyor"):
                        raise ValueError("Yalnız süren sınav bitirilebilir.")
                    b.execute("UPDATE sinav SET bitirme = ?, guncelleme = ? WHERE id = ?", (an, an, sinav_id))
                    vt.kayit_dus(b, k["ad"], "Sınav bitirildi", f"{adi} · {sinav.saat_metni(an)}", ip(istek))
                    mesaj = "Sınav bitirildi; tahtalar sınav kipinden çıkıyor."
                elif eylem == "kisisel_sil":
                    if s["kisisel_silinme"]:
                        raise ValueError("Kişisel veri zaten silinmiş.")
                    if not bitti:
                        raise ValueError("Kişisel veri yalnız sınav bittikten sonra silinebilir.")
                    sinav.kisisel_veri_sil(b, sinav_id, k["ad"], "Sınav kişisel verisi silindi", an, ip(istek))
                    kapi.salon_belirtecleri_dusur(s_["id"] for s_ in b.execute("SELECT id FROM sinav_salon WHERE sinav_id = ?", (sinav_id,)))
                    budanacak = True
                    mesaj = "Kişisel veri silindi; salon başına sayılar kaldı."
                elif eylem == "sil":
                    if not (s["durum"] == "taslak" or bitti or s["kisisel_silinme"]):
                        raise ValueError("Yayındaki sınav ancak bittikten sonra silinebilir; önce taslağa alın.")
                    kapi.salon_belirtecleri_dusur(s_["id"] for s_ in b.execute("SELECT id FROM sinav_salon WHERE sinav_id = ?", (sinav_id,)))
                    sinav.sinav_sil(b, sinav_id, k["ad"], an, ip(istek))
                    budanacak = True
                    donus, mesaj = "/sinavlar", "Sınav silindi."
                else:
                    raise ValueError("Bilinmeyen işlem.")
        except ValueError as hata:
            return y.yonlendir(donus, str(hata), hata=True)
        if budanacak:
            vt.wal_buda()
        y.uyandir_hepsi(idler)
        return y.yonlendir(donus, mesaj)

    @uygulama.post("/sinav/{sinav_id}/uzat")
    async def uzat(istek: Request, sinav_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        an = vt.simdi()
        donus = adres(sinav_id)
        dk = _tamsayi(form.get("dk"))
        hedef = str(form.get("salon", "hepsi"))
        try:
            with vt.islem() as b:
                s = sinav_al(b, sinav_id)
                if not s:
                    return y.yonlendir("/sinavlar", "Sınav bulunamadı.", hata=True)
                if dk not in sinav.UZATMA_SECENEKLERI:
                    raise ValueError("Uzatma süresini seçin.")
                if s["durum"] != "yayinda" or s["bitirme"] or s["kisisel_silinme"]:
                    raise ValueError("Süre yalnız süren sınavda uzatılabilir.")
                z = sinav.zamanlar(b, s)
                salonlar = b.execute("SELECT * FROM sinav_salon WHERE sinav_id = ?", (sinav_id,)).fetchall()
                if hedef != "hepsi":
                    salon_id = _tamsayi(hedef)
                    salonlar = [sl for sl in salonlar if sl["id"] == salon_id]
                    if not salonlar:
                        raise ValueError("Salon bulunamadı.")
                suren = [sl for sl in salonlar if s["baslangic"] <= an < z["salon_bitis"].get(sl["id"], 0) and not sl["kip_kapanma"]]
                if not suren:
                    raise ValueError("Süre yalnız süren sınavda uzatılabilir.")
                asan = [sl["ad"] for sl in suren if sl["uzatma_dk"] + dk > sinav.UZATMA_EN_COK_DK]
                if asan:
                    raise ValueError(f"Salon başına toplam uzatma en çok {sinav.UZATMA_EN_COK_DK} dakika olabilir: {', '.join(asan[:5])}.")
                for sl in suren:
                    b.execute("UPDATE sinav_salon SET uzatma_dk = uzatma_dk + ? WHERE id = ?", (dk, sl["id"]))
                kapsam = "bütün salonlar" if hedef == "hepsi" else suren[0]["ad"]
                vt.kayit_dus(b, k["ad"], "Sınav süresi uzatıldı", f"{s['ad']} · {kapsam} · +{dk} dk", ip(istek))
                idler = sorted({sl["tahta_id"] for sl in suren if sl["tahta_id"]})
        except ValueError as hata:
            return y.yonlendir(donus, str(hata), hata=True)
        y.uyandir_hepsi(idler)
        return y.yonlendir(donus, f"Süre {dk} dakika uzatıldı ({len(suren)} salon).")

    @uygulama.post("/sinav/{sinav_id}/salon/{salon_id}/kip-kaldir")
    async def kip_kaldir(istek: Request, sinav_id: int, salon_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        an = vt.simdi()
        donus = adres(sinav_id, "#salonlar")
        try:
            with vt.islem() as b:
                s = sinav_al(b, sinav_id)
                sl = b.execute("SELECT * FROM sinav_salon WHERE id = ? AND sinav_id = ?", (salon_id, sinav_id)).fetchone()
                if not s or not sl:
                    return y.yonlendir("/sinavlar", "Salon bulunamadı.", hata=True)
                bitis = sinav.zamanlar(b, s)["salon_bitis"].get(salon_id, 0)
                if s["durum"] != "yayinda" or sinav.salon_evresi(s, sl, bitis, an) not in ("giris", "suruyor"):
                    raise ValueError("Bu salonda sınav kipi şu an açık değil.")
                b.execute("UPDATE sinav_salon SET kip_kapanma = ?, kip_kapatan = ? WHERE id = ?", (an, f"panel:{k['ad']}", salon_id))
                kapi.salon_belirtecleri_dusur([salon_id])
                vt.kayit_dus(b, k["ad"], "Sınav kipi kaldırıldı", f"{s['ad']} · {sl['ad']}", ip(istek))
                idler = [sl["tahta_id"]] if sl["tahta_id"] else []
        except ValueError as hata:
            return y.yonlendir(donus, str(hata), hata=True)
        y.uyandir_hepsi(idler)
        return y.yonlendir(donus, f"{sl['ad']}: sınav kipi kaldırıldı.")

    # ---- gözetmen kodları --------------------------------------------------------------------
    @uygulama.post("/sinav/{sinav_id}/kodlar")
    async def kodlar_yenile(istek: Request, sinav_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        an = vt.simdi()
        donus = adres(sinav_id)
        with vt.islem() as b:
            s = sinav_al(b, sinav_id)
            if not s:
                return y.yonlendir("/sinavlar", "Sınav bulunamadı.", hata=True)
            if s["kisisel_silinme"] or not sinav.giris_oncesi_mi(s, an):
                return y.yonlendir(donus, "Kodlar yalnız giriş penceresinden önce yenilenebilir.", hata=True)
            kullanilan: set[str] = set()
            salonlar = b.execute("SELECT id FROM sinav_salon WHERE sinav_id = ?", (sinav_id,)).fetchall()
            for sl in salonlar:
                kod = sinav.kod_uret(kullanilan)
                kullanilan.add(kod)
                b.execute("UPDATE sinav_salon SET gozetmen_kodu = ? WHERE id = ?", (kod, sl["id"]))
            kapi.salon_belirtecleri_dusur(sl["id"] for sl in salonlar)
            vt.kayit_dus(b, k["ad"], "Gözetmen kodları yenilendi", f"{s['ad']} · {len(salonlar)} salon", ip(istek))
        return y.yonlendir(donus, "Gözetmen kodları yenilendi; eski fişler geçersiz.")

    @uygulama.get("/sinav/{sinav_id}/kodlar", response_class=HTMLResponse)
    async def kodlar_sayfasi(istek: Request, sinav_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        with vt.islem() as b:
            s = sinav_al(b, sinav_id)
            if not s:
                return y.yonlendir("/sinavlar", "Sınav bulunamadı.", hata=True)
            if s["kisisel_silinme"]:
                return y.yonlendir(adres(sinav_id), "Kişisel veri silindiği için kodlar da silindi.", hata=True)
            fisler = [
                {"salon": sl["ad"], "kod": sl["gozetmen_kodu"], "gozetmen_adi": sl["gozetmen_adi"], "tahta_var": bool(sl["tahta_id"])}
                for sl in sorted(b.execute("SELECT * FROM sinav_salon WHERE sinav_id = ?", (sinav_id,)).fetchall(),
                                 key=lambda x: sinav.sirala_anahtari(x["ad"]))  # fmt: skip
            ]
            vt.kayit_dus(b, k["ad"], "Gözetmen kodları görüntülendi", f"{s['ad']} · {len(fisler)} salon", ip(istek))
        return y.sayfa(
            istek, "sinav_kodlar.html", k,
            s=rapor_kunyesi(s),
            fisler=fisler,
        )  # fmt: skip

    # ---- şube duyurusu -----------------------------------------------------------------------
    @uygulama.post("/sinav/{sinav_id}/duyuru")
    async def sube_duyurusu(istek: Request, sinav_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        an = vt.simdi()
        donus = adres(sinav_id, "#subeler")
        sure = _tamsayi(form.get("sure_dk"), sinav.DUYURU_VARSAYILAN_DK)
        if not sinav.DUYURU_SURE_ARALIGI[0] <= sure <= sinav.DUYURU_SURE_ARALIGI[1]:
            return y.yonlendir(donus, f"Süre {sinav.DUYURU_SURE_ARALIGI[0]}–{sinav.DUYURU_SURE_ARALIGI[1]} dakika olmalı.", hata=True)
        with vt.islem() as b:
            s = sinav_al(b, sinav_id)
            if not s:
                return y.yonlendir("/sinavlar", "Sınav bulunamadı.", hata=True)
            evre = sinav.sinav_evresi(s, sinav.zamanlar(b, s)["bitis"], an)
            if s["durum"] != "yayinda" or evre not in ("yayinda", "giris"):
                return y.yonlendir(donus, "Şube duyurusu yalnız yayındaki sınav için, sınav başlamadan gönderilebilir.", hata=True)
            sure_sn = sinav.sube_duyurusu_suresi(s, sure, an)
            if sure_sn < 60:
                return y.yonlendir(donus, "Sınav başlamak üzere; oturma listesi artık gönderilemez.", hata=True)
            gonderilen, tahtasiz, idler = sinav.sube_duyurusu(b, s, sure, k["ad"], an, ip(istek))
        y.uyandir_hepsi(idler)
        if not gonderilen:
            return y.yonlendir(donus, f"Hiçbir şubenin tahtası yok ({tahtasiz} şube); tahta sayfalarında şube alanını doldurun.", hata=True)
        kirpma = ""
        if sure_sn < sure * 60:
            kirpma = f" Liste sınav başlayınca kalkar ({sinav.saat_metni(s['baslangic'])})."
        return y.yonlendir(donus, f"{gonderilen} şubeye gönderildi, {tahtasiz} şubenin tahtası yok.{kirpma}")

    # ---- panelden yoklama ------------------------------------------------------------------------
    @uygulama.get("/sinav/{sinav_id}/salon/{salon_id}/yoklama", response_class=HTMLResponse)
    async def yoklama_sayfasi(istek: Request, sinav_id: int, salon_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        an = vt.simdi()
        with vt.islem() as b:
            s = sinav_al(b, sinav_id)
            sl = b.execute("SELECT * FROM sinav_salon WHERE id = ? AND sinav_id = ?", (salon_id, sinav_id)).fetchone()
            if not s or not sl:
                return y.yonlendir("/sinavlar", "Salon bulunamadı.", hata=True)
            if s["kisisel_silinme"]:
                return y.yonlendir(adres(sinav_id), "Kişisel veri silindi; yoklama listesi yok.", hata=True)
            dersler = {d["id"]: d["ad"] for d in b.execute("SELECT id, ad FROM sinav_ders WHERE sinav_id = ?", (sinav_id,))}
            ogrenciler = [
                {"koltuk": o["koltuk"], "okul_no": o["okul_no"], "maske": o["maske"], "sube": o["sube"],
                 "ders": dersler.get(o["ders_id"], ""), "gelmedi": bool(o["gelmedi"])}  # fmt: skip
                for o in b.execute("SELECT * FROM sinav_ogrenci WHERE salon_id = ? ORDER BY koltuk", (salon_id,))
            ]
            vt.kayit_dus(b, k["ad"], "Sınav yoklama listesi görüntülendi", f"{s['ad']} · {sl['ad']}", ip(istek))
        return y.sayfa(
            istek, "sinav_yoklama.html", k,
            s=rapor_kunyesi(s),
            salon={"id": sl["id"], "ad": sl["ad"], "gozetmen_adi": sl["gozetmen_adi"],
                   "yoklama_metni": (f"{sinav.kaynak_metni(sl['yoklama_kaynak'])}, {sinav.an_metni(sl['yoklama_zamani'])}"
                                     if sl["yoklama_zamani"] else "")},
            ogrenciler=ogrenciler,
            yazilabilir=bool(s["baslangic"]) and an >= s["baslangic"],
        )  # fmt: skip

    @uygulama.post("/sinav/{sinav_id}/salon/{salon_id}/yoklama")
    async def yoklama_kaydet(istek: Request, sinav_id: int, salon_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        an = vt.simdi()
        donus = adres(sinav_id, f"/salon/{salon_id}/yoklama")
        try:
            with vt.islem() as b:
                s = sinav_al(b, sinav_id)
                sl = b.execute("SELECT * FROM sinav_salon WHERE id = ? AND sinav_id = ?", (salon_id, sinav_id)).fetchone()
                if not s or not sl:
                    return y.yonlendir("/sinavlar", "Salon bulunamadı.", hata=True)
                if s["kisisel_silinme"]:
                    raise ValueError("Kişisel veri silindi; yoklama yazılamaz.")
                if not s["baslangic"] or an < s["baslangic"]:
                    raise ValueError("Sınav henüz başlamadı.")
                gelmeyen = [str(x) for x in form.getlist("gelmedi")]
                n, mevcut = sinav.yoklama_yaz(b, sl, gelmeyen, f"panel:{k['ad']}", f"panel:{k['ad']}", an)
                vt.kayit_dus(b, k["ad"], "Sınav yoklaması (panel)",
                             f"{s['ad']} · " + sinav.yoklama_kayit_metni(sl["ad"], [int(x) for x in gelmeyen]), ip(istek))  # fmt: skip
                idler = [sl["tahta_id"]] if sl["tahta_id"] else []
        except ValueError as hata:
            return y.yonlendir(donus, str(hata), hata=True)
        y.uyandir_hepsi(idler)
        return y.yonlendir(adres(sinav_id, "#salonlar"), f"{sl['ad']}: yoklama kaydedildi, {n} öğrenci gelmedi ({mevcut} mevcut).")

    @uygulama.get("/sinav/{sinav_id}/icmal", response_class=HTMLResponse)
    async def icmal(istek: Request, sinav_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        with vt.islem() as b:
            s = sinav_al(b, sinav_id)
            if not s:
                return y.yonlendir("/sinavlar", "Sınav bulunamadı.", hata=True)
            veri = sinav.icmal_verisi(b, s)
            vt.kayit_dus(b, k["ad"], "Sınav yoklama icmali görüntülendi", s["ad"] or f"Sınav #{sinav_id}", ip(istek))
        return y.sayfa(
            istek, "sinav_icmal.html", k,
            s=dict(rapor_kunyesi(s), donem=s["donem"]),
            icmal=veri,
            uretim=sinav.an_metni(vt.simdi()),
        )  # fmt: skip

    # ---- tahta (ajan) uçları ---------------------------------------------------------------------
    async def ajan_govdesi(istek: Request):
        tahta = y.tahta_dogrula(istek)
        if not tahta:
            return None, JSONResponse({"hata": "Tahta tanınmıyor."}, status_code=401)
        if tahta["durum"] != "onayli":
            return None, JSONResponse({"hata": "Tahta onaylı değil."}, status_code=403)
        try:
            govde = await istek.json()
        except (ValueError, UnicodeDecodeError):
            return None, JSONResponse({"hata": "Geçersiz istek."}, status_code=400)
        if not isinstance(govde, dict):
            return None, JSONResponse({"hata": "Geçersiz istek."}, status_code=400)
        return (tahta, govde), None

    @uygulama.post("/ajan/sinav/kod")
    async def ajan_kod(istek: Request):
        cozulen, hata = await ajan_govdesi(istek)
        if hata:
            return hata
        tahta, govde = cozulen
        an = vt.simdi()
        kalan = kapi.bekleme_kalan(tahta["id"], an)
        if kalan:
            return JSONResponse({"hata": f"Çok fazla hatalı deneme. {kalan // 60 + 1} dakika sonra yeniden deneyin.", "bekleme_sn": kalan},
                                status_code=429)  # fmt: skip
        kod = str(govde.get("kod", ""))[:12]
        with vt.islem() as b:
            bulunan = sinav.gecerli_salon(b, tahta["id"], govde.get("salon"), an)
            dogru = bool(bulunan) and bool(bulunan[1]["gozetmen_kodu"]) and sinav.hmac_esit(kod, bulunan[1]["gozetmen_kodu"])
            salon_adi = bulunan[1]["ad"] if bulunan else f"#{govde.get('salon')}"
            if not dogru:
                kalan_deneme, bekleme = kapi.hata_say(tahta["id"], an)
                vt.kayit_dus(b, f"tahta:{tahta['ad']}", "Hatalı gözetmen kodu", f"{salon_adi} · {tahta['ad']}", ip(istek))
                if bekleme:
                    return JSONResponse({"hata": "Çok fazla hatalı deneme. 5 dakika sonra yeniden deneyin.", "bekleme_sn": bekleme},
                                        status_code=429)  # fmt: skip
                return JSONResponse({"hata": "Kod geçersiz.", "kalan_deneme": kalan_deneme}, status_code=403)
            s, sl, _ = bulunan
            vt.kayit_dus(b, f"tahta:{tahta['ad']}", "Gözetmen kodu girildi", f"{s['ad']} · {sl['ad']} · {tahta['ad']}", ip(istek))
            veri = sinav.gozetmen_verisi(b, s, sl, an)
        belirtec = kapi.belirtec_ver(tahta["id"], sl["id"], an)
        return {"belirtec": belirtec, "sure_sn": sinav.GOZETMEN_OTURUM_SN, **veri}

    @uygulama.post("/ajan/sinav/yoklama")
    async def ajan_yoklama(istek: Request):
        cozulen, hata = await ajan_govdesi(istek)
        if hata:
            return hata
        tahta, govde = cozulen
        an = vt.simdi()
        salon_id = kapi.belirtec_coz(govde.get("belirtec"), tahta["id"], an)
        if salon_id is None:
            return JSONResponse({"hata": "Gözetmen oturumu sona erdi; kodu yeniden girin."}, status_code=401)
        gelmeyen = govde.get("gelmeyen")
        if not isinstance(gelmeyen, list) or len(gelmeyen) > 1000:
            return JSONResponse({"hata": "Geçersiz istek."}, status_code=400)
        try:
            with vt.islem() as b:
                bulunan = sinav.gecerli_salon(b, tahta["id"], salon_id, an)
                if not bulunan:
                    return JSONResponse({"hata": "Bu salonda sınav kipi sona erdi; yoklamayı kâğıda alıp idareye iletin."}, status_code=409)
                s, sl, _ = bulunan
                if an < s["baslangic"]:
                    raise ValueError("Sınav henüz başlamadı.")
                if b.execute("SELECT COUNT(*) FROM sinav_ogrenci WHERE salon_id = ?", (sl["id"],)).fetchone()[0] > sinav.SALON_LISTE_SINIRI:
                    raise ValueError("Bu salonun yoklaması panelden alınır.")
                kaynak = f"tahta:{tahta['ad']}"
                n, mevcut = sinav.yoklama_yaz(b, sl, gelmeyen, f"{kaynak} (gözetmen kodu)", kaynak, an)
                vt.kayit_dus(b, f"tahta:{tahta['ad']}", "Sınav yoklaması (tahta)",
                             f"{s['ad']} · " + sinav.yoklama_kayit_metni(sl["ad"], [int(x) for x in gelmeyen]), ip(istek))  # fmt: skip
        except ValueError as hata_:
            return JSONResponse({"hata": str(hata_)}, status_code=400)
        y.uyandir(tahta["id"])
        return {"gelmeyen_sayisi": n, "mevcut": mevcut, "gelen": mevcut - n}


# =================================================================================================
# SÖZLEŞME — şablon bağlamları (sonraki uygulayıcı için; ayrıntı raporda)
#
# sinavlar.html: yaklasan[], gecmis[] = {id, ad, tarih, saat, salon_sayisi, ogrenci_sayisi, evre, evre_adi};
#   dosya_siniri_mb; hata durumunda (400) hatalar[] (≤ 20 metin, okul no içerebilir), hata_toplam.
#   Form: POST /sinavlar/ice-aktar multipart, <input type=file name=dosya accept=".xlsx">.
# sinav.html: s (sinav_gorunumu), tahtalar[{id,ad,derslik}], uzatma_secenekleri, sure_araligi,
#   duyuru_sure_araligi, duyuru_varsayilan_dk, saklama_gun. Canlı: s.canli ise /api/sinav/{id} (4 sn).
# sinav_yoklama.html: s{id,ad,tarih,saat}, salon{id,ad,gozetmen_adi,yoklama_metni},
#   ogrenciler[{koltuk,okul_no,maske,sube,ders,gelmedi}], yazilabilir. Form: gelmedi=<koltuk> (çoklu).
# sinav_kodlar.html: s{id,ad,tarih,saat}, fisler[{salon,kod,gozetmen_adi,tahta_var}], okul_adi (taban).
# sinav_icmal.html: s{id,ad,donem}, icmal (sinav.icmal_verisi), uretim ("gg.aa.yyyy SS:DD"), surum (taban).
# =================================================================================================
