"""Şube defteri, son günler, mazeret/izin ve öğrenci görünümü uçları (0.14.0). İş mantığı `yoklama_defter.py`.

Yetki: bütün sayfa ve uçlar yönetici + idareciye açıktır (`y.kullanici`); öğretmen ve tahta erişemez. Kaynak
denetimi ve `Cache-Control: no-store` ortak ara katmandan gelir (web.py `kapilar`).
İşlem kaydına öğrenci adı, numarası, kimliği, mazeret TÜRÜ ve mazeret TARİH ARALIĞI yazılmaz; öğrenci kimlikli iz
yalnız `yoklama_duzeltme` ve `yoklama_mazeret` tablolarındadır ve yıl sonu imhasıyla gider.
Beş günlük görünüm, son günler listesi, öğrenci görünümü ve mazeret listesi dışa aktarılmaz; yalnız yazdırılır.

Şablon bağlamları modül sonundaki SÖZLEŞME'dedir.
"""

from __future__ import annotations

import time
from datetime import timedelta
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import metin, saklama, vt
from . import yoklama as yk
from . import yoklama_defter as yd

NOT_OMRU_SN = 30 * 60  # sayfadaki "Düzeltme notu" JS'siz gönderimler arasında bu kadar süre bellekte tutulur


def _tamsayi(deger, varsayilan=None):
    s = str(deger if deger is not None else "").strip()
    return int(s) if metin.rakam_mi(s) and len(s) <= 9 else varsayilan


def kaydet(uygulama, y, depo) -> None:
    # Düzeltme notu yalnız bellekte: {(kullanıcı id, şube, tarih): (bitiş, not)}. Adrese ve diske yazılmaz.
    notlar: dict[tuple[int, str, str], tuple[float, str]] = {}
    uygulama.state.defter_notlari = notlar

    def ip(istek: Request) -> str:
        return y.istemci_ip(istek)

    def not_al(k, sube: str, tarih: str) -> str:
        simdi = time.monotonic()
        for anahtar in [a for a, (bitis, _) in list(notlar.items()) if bitis <= simdi]:
            notlar.pop(anahtar, None)
        return notlar.get((k["id"], sube, tarih), (0, ""))[1]

    def not_koy(k, sube: str, tarih: str, aciklama: str) -> None:
        if aciklama:
            notlar[(k["id"], sube, tarih)] = (time.monotonic() + NOT_OMRU_SN, aciklama)
        else:
            notlar.pop((k["id"], sube, tarih), None)

    def sube_adresi(sube: str, **alanlar) -> str:
        return "/yoklama/sube?sube=" + quote(sube, safe="") + "".join(f"&{a}={quote(str(d), safe='')}" for a, d in alanlar.items() if d)

    # ---- şube defteri --------------------------------------------------------------------------------
    def gun_sayfasi(istek: Request, k, sube: str, gun, firca: str, durum_kodu: int = 200, **ek) -> HTMLResponse:
        an = vt.simdi()
        with vt.islem() as b:
            g = yd.sube_gunu(b, sube, gun, an)
            subeler = yk.aktif_subeler(b)
        if firca not in yd.FIRCA_DURUMLARI or (firca == "gec" and not g["gec_var"]):
            firca = "yok"
        # "Alındı" iki adımlıdır (JS'siz de): sütun düğmesi bu sayfayı ?alindi=<ders> ile yeniden açar, onay tablonun
        # hemen üstünde sorulur. Onay yalnız o an alınabilir sütun için çizilir.
        alindi = ek.pop("alindi", None)
        ek["alindi_onay"] = next((s for s in g["sutunlar"] if s["alinabilir"] and s["ders_no"] == alindi), None)
        return y.sayfa(istek, "yoklama_sube.html", k, durum_kodu=durum_kodu, kip="gun", g=g, sube=sube, subeler=subeler, firca=firca,
                       duzeltme_notu=not_al(k, sube, g["tarih"]), bugun_iso=yk.bugun(an).isoformat(), geri_gun=yk.PANEL_GERI_GUN,
                       not_en_kisa=yk.ACIKLAMA_EN_KISA, not_en_uzun=yk.ACIKLAMA_EN_UZUN, adli_not=yk.ILETI_ADLI_SAYFA,
                       n_gun_notu=yd.ILETI_N_GUN, **ek)  # fmt: skip

    @uygulama.get("/yoklama/sube", response_class=HTMLResponse)
    async def sube_sayfasi(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        an = vt.simdi()
        q = istek.query_params
        with vt.islem() as b:
            subeler = yk.aktif_subeler(b)
        sube = metin.sube_duzelt(q.get("sube", "")) if q.get("sube") else (subeler[0] if subeler else None)
        if not sube:
            return y.sayfa(istek, "yoklama_sube.html", k, kip="bos", sube="", subeler=subeler, bugun_iso=yk.bugun(an).isoformat(),
                           adli_not=None, n_gun_notu=yd.ILETI_N_GUN)  # fmt: skip
        gun = yk.tarih_coz(q.get("tarih")) if q.get("tarih") else None
        if gun:  # gün kipi
            return gun_sayfasi(istek, k, sube, min(gun, yk.bugun(an)), str(q.get("firca", "yok")), alindi=_tamsayi(q.get("alindi")))
        bitis = yk.tarih_coz(q.get("bitis")) or yk.bugun(an)
        yalniz_yok = q.get("yalniz_yok") == "1"
        with vt.islem() as b:
            d = yd.sube_defteri(b, sube, bitis, an, yd.DEFTER_GUN, yalniz_yok)
            vt.kayit_dus(b, k["ad"], "Şube defteri (5 gün) açıldı", sube, ip(istek))
        return y.sayfa(istek, "yoklama_sube.html", k, kip="bes", d=d, sube=sube, subeler=subeler, bugun_iso=yk.bugun(an).isoformat(),
                       adli_not=yk.ILETI_ADLI_SAYFA, n_gun_notu=yd.ILETI_N_GUN)  # fmt: skip

    def defter_formu(form):
        """(şube, gün) ya da ValueError."""
        gun = yk.tarih_coz(form.get("tarih"))
        sube = metin.sube_duzelt(form.get("sube", ""))
        if not gun or not sube:
            raise ValueError("Tarih ya da şube geçersiz.")
        return sube, gun

    @uygulama.post("/yoklama/sube/hucre")
    async def sube_hucre(istek: Request):
        """Fırça: `hucre=ogrenci:ders`, `durum=yok|gec|var`, `tarih`, `sube`, `aciklama` (düzeltme notu).
        `Accept: application/json` ise yerinde güncelleme için sayılar (ad/no içermez), değilse 303 aynı sayfa."""
        k = y.kullanici(istek)
        json_mi = "application/json" in istek.headers.get("accept", "")
        if not k:
            return JSONResponse({"hata": "Oturum sona erdi; sayfayı yenileyip yeniden girin."}, status_code=401) if json_mi else y.yonlendir("/giris")
        form = await istek.form()
        an = vt.simdi()
        durum = str(form.get("durum", "yok"))
        donus = "/yoklama/sube"
        try:
            sube, gun = defter_formu(form)
            donus = sube_adresi(sube, tarih=gun.isoformat(), firca=durum if durum in yd.FIRCA_DURUMLARI else "")
            aciklama = yd.not_coz(form.get("aciklama", ""))
            not_koy(k, sube, gun.isoformat(), aciklama)
            ogrenci_id, _, ders = str(form.get("hucre", "")).partition(":")
            ogrenci_id, ders_no = _tamsayi(ogrenci_id), _tamsayi(ders)
            if ogrenci_id is None or ders_no is None:
                if "hucre" not in form:  # "Notu kaydet": yalnız not belleğe alınır
                    return y.yonlendir(donus + "#ileti", "Düzeltme notu bu sayfadaki tıklamalara uygulanacak." if aciklama else "Düzeltme notu silindi.")
                raise ValueError("Hücre geçersiz.")
            with vt.islem() as b:
                degisti = yd.hucre_yaz(b, gun=gun, sube=sube, ders_no=ders_no, ogrenci_id=ogrenci_id, durum=durum, giren=k["ad"],
                                       an=an, aciklama=aciklama)  # fmt: skip
                if degisti:
                    vt.kayit_dus(b, k["ad"], "Şube defteri düzeltmesi", f"{yk.tarih_kisa(gun)} {sube}, 1 hücre", ip(istek))
                ozet = yd.hucre_ozetleri(b, sube, gun, ogrenci_id, ders_no)
        except yd.Alinmadi as hata:
            if json_mi:
                return JSONResponse({"hata": str(hata)}, status_code=409)
            return gun_sayfasi(istek, k, sube, gun, durum, durum_kodu=409, mesaj=str(hata), mesaj_hata=True)
        except ValueError as hata:
            if json_mi:
                return JSONResponse({"hata": str(hata), "not_gerek": str(hata) == yd.ILETI_NOT_GEREK}, status_code=400)
            return y.yonlendir(donus + "#ileti", str(hata), hata=True)
        ileti = f"{ders_no}. ders: {ozet['durum_metni']}." if degisti else "Değişiklik yok."
        if json_mi:
            return JSONResponse({**ozet, "degisti": degisti, "ileti": ileti})
        return y.yonlendir(donus + f"#h-{ogrenci_id}-{ders_no}", ileti)

    @uygulama.post("/yoklama/sube/toplu")
    async def sube_toplu(istek: Request):
        """Satır: `satir=ogrenci:butun_gun|temizle`. Sütun ("Alındı (herkes var)"): `sutun=ders_no` → onay sorusu
        (303 aynı sayfa `?alindi=<ders>#alindi-onay`); `alindi=<ders_no>` + isteğe bağlı `alindi_yoklar=1` → kayıt açılır."""
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        an = vt.simdi()
        donus = "/yoklama/sube"
        try:
            sube, gun = defter_formu(form)
            durum = str(form.get("durum", "yok"))
            donus = sube_adresi(sube, tarih=gun.isoformat(), firca=durum if durum in yd.FIRCA_DURUMLARI else "")
            aciklama = yd.not_coz(form.get("aciklama", ""))
            not_koy(k, sube, gun.isoformat(), aciklama)
            with vt.islem() as b:
                if "alindi" in form:  # onaylandı
                    ders_no = _tamsayi(form.get("alindi"))
                    if ders_no is None:
                        raise ValueError("Ders saati geçersiz.")
                    n = yd.sutun_alindi(b, gun=gun, sube=sube, ders_no=ders_no, giren=k["ad"], an=an,
                                        gun_boyu_yok=form.get("alindi_yoklar") == "1")  # fmt: skip
                    vt.kayit_dus(b, k["ad"], "Yoklama girildi (panel)", yk.kayit_metni(sube, ders_no, n, None, gun) + " · şube defteri",
                                 ip(istek))  # fmt: skip
                    mesaj = f"{ders_no}. ders alındı sayıldı: " + (
                        f"günün diğer derslerinde yok yazılan {n} öğrenci bu derste de yok yazıldı, diğer herkes derste."
                        if n else "herkes derste.") + " Olmayanları fırçayla işaretleyin."  # fmt: skip
                elif "sutun" in form:  # ilk adım: onay sorusu (hiçbir şey yazılmaz)
                    ders_no = _tamsayi(form.get("sutun"))
                    if ders_no is None:
                        raise ValueError("Ders saati geçersiz.")
                    return y.yonlendir(donus + f"&alindi={ders_no}#alindi-onay")
                else:
                    ogrenci_id, _, eylem = str(form.get("satir", "")).partition(":")
                    ogrenci_id = _tamsayi(ogrenci_id)
                    if ogrenci_id is None or eylem not in ("butun_gun", "temizle"):
                        raise ValueError("İşlem geçersiz.")
                    if eylem == "butun_gun":
                        n, atlanan = yd.satir_butun_gun_yok(b, gun=gun, sube=sube, ogrenci_id=ogrenci_id, giren=k["ad"], an=an,
                                                            aciklama=aciklama)  # fmt: skip
                        mesaj = f"{n} ders saati \"yok\" yapıldı."
                        if atlanan:
                            mesaj += f" Yoklaması alınmamış {atlanan} ders saati atlandı."
                    else:
                        n = yd.satir_temizle(b, gun=gun, sube=sube, ogrenci_id=ogrenci_id, giren=k["ad"], an=an)
                        mesaj = f"{n} düzeltme kaldırıldı; kayıttaki durum geri geldi." if n else "Bu satırda düzeltme yok."
                    if n:
                        vt.kayit_dus(b, k["ad"], "Şube defteri düzeltmesi", f"{yk.tarih_kisa(gun)} {sube}, {n} hücre", ip(istek))
        except ValueError as hata:
            return y.yonlendir(donus + "#ileti", str(hata), hata=True)
        return y.yonlendir(donus + "#ileti", mesaj)

    # ---- okul geneli son günler ve öğrenci görünümü ----------------------------------------------------
    @uygulama.get("/yoklama/son-gunler", response_class=HTMLResponse)
    async def son_gunler_sayfasi(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        ozurluler = istek.query_params.get("ozurluler") == "1"
        with vt.islem() as b:
            veri = yd.son_gunler(b, vt.simdi(), ozurluler)
            vt.kayit_dus(b, k["ad"], "Son günler listesi açıldı", "", ip(istek))
        return y.sayfa(istek, "yoklama_son_gunler.html", k, liste=veri, adli_not=yk.ILETI_ADLI_SAYFA, n_gun_notu=yd.ILETI_N_GUN,
                       esik=yd.SON_GUNLER_ESIK)  # fmt: skip

    @uygulama.get("/yoklama/ogrenci/{ogrenci_id}", response_class=HTMLResponse)
    async def ogrenci_sayfasi(istek: Request, ogrenci_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        with vt.islem() as b:
            veri = yd.ogrenci_gorunumu(b, ogrenci_id, vt.simdi())
            if veri:
                vt.kayit_dus(b, k["ad"], "Öğrenci devam görünümü açıldı", "", ip(istek))
        if not veri:
            return y.yonlendir("/yoklama/sube", "Öğrenci bulunamadı.", hata=True)
        return y.sayfa(istek, "yoklama_ogrenci.html", k, o=veri, adli_not=yk.ILETI_ADLI_SAYFA, n_gun_notu=yd.ILETI_N_GUN,
                       gun_sayisi=yd.OGRENCI_GUN)  # fmt: skip

    # ---- mazeret/izin -----------------------------------------------------------------------------------
    def mazeret_sayfasi(istek: Request, k, durum_kodu: int = 200, girdi: dict | None = None, **ek) -> HTMLResponse:
        an = vt.simdi()
        bugun = yk.bugun(an)
        with vt.islem() as b:
            liste = yd.mazeret_listesi(b, an)
            ust = yd.mazeret_ust_siniri(b, bugun)
            silinme = saklama.silinme_metni(b)
        varsayilan = {"nolar": "", "bas": bugun.isoformat(), "bit": bugun.isoformat(), "kapsam": "tam", "ders_bas": "", "ders_bit": "",
                      "tur": "", "dayanak": ""}  # fmt: skip
        return y.sayfa(istek, "yoklama_mazeret.html", k, durum_kodu=durum_kodu, liste=liste, girdi={**varsayilan, **(girdi or {})},
                       turler=yk.MAZERET_TURLERI, dayanaklar=yk.MAZERET_DAYANAKLARI, en_erken=(bugun - timedelta(days=yk.PANEL_GERI_GUN)).isoformat(),
                       en_gec=ust.isoformat(), en_gec_metni=saklama.tarih_metni(ust), no_en_cok=yd.MAZERET_NO_EN_COK,
                       gun_en_cok=yd.MAZERET_GUN_EN_COK, liste_gun=yd.MAZERET_LISTE_GUN, adli_not=yk.ILETI_ADLI_SAYFA, k5_notu=yd.ILETI_K5,
                       silinme=silinme, **ek)  # fmt: skip

    @uygulama.get("/yoklama/mazeret", response_class=HTMLResponse)
    async def mazeret(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        q = istek.query_params
        girdi: dict = {}
        ogrenci_id = _tamsayi(q.get("ogrenci"))
        if ogrenci_id is not None:  # şube defterindeki "Mazeret" bağlantısı: öğrenci ve tarih dolu gelir
            with vt.islem() as b:
                o = b.execute("SELECT okul_no FROM ogrenci WHERE id = ? AND aktif = 1", (ogrenci_id,)).fetchone()
            if o:
                girdi["nolar"] = o["okul_no"]
        gun = yk.tarih_coz(q.get("bas"))
        if gun:
            girdi["bas"] = girdi["bit"] = gun.isoformat()
        return mazeret_sayfasi(istek, k, girdi=girdi)

    @uygulama.post("/yoklama/mazeret/onizle")
    async def mazeret_onizle(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        an = vt.simdi()
        ham = {a: str(form.get(a, "")) for a in ("nolar", "bas", "bit", "kapsam", "ders_bas", "ders_bit", "tur", "dayanak")}
        try:
            with vt.islem() as b:
                onizleme = yd.mazeret_onizle(b, yd.mazeret_coz(b, form, an), an)
        except ValueError as hata:
            return mazeret_sayfasi(istek, k, durum_kodu=400, girdi=ham, mesaj=str(hata), mesaj_hata=True)
        # Önizleme yalnız bellekteki süreli depoda durur (kullanıcıya bağlı, tek kullanımlık); diske ve işlem kaydına yazılmaz.
        belirtec = depo.koy(k["id"], {"tur": "mazeret", "onizleme": onizleme}, yd.MAZERET_ONIZLEME_OMRU_SN)
        return y.sayfa(istek, "yoklama_mazeret_onizleme.html", k, o=onizleme, onizleme=belirtec,
                       omur_dk=yd.MAZERET_ONIZLEME_OMRU_SN // 60, adli_not=yk.ILETI_ADLI_SAYFA, k5_notu=yd.ILETI_K5)  # fmt: skip

    @uygulama.post("/yoklama/mazeret/onayla")
    async def mazeret_onayla(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        kayit = depo.al(str(form.get("onizleme", "")), k["id"])
        if not kayit or kayit.get("tur") != "mazeret":
            return y.yonlendir("/yoklama/mazeret", "Önizlemenin süresi doldu; mazereti yeniden girin.", hata=True)
        onizleme = kayit["onizleme"]
        try:
            with vt.islem() as b:
                n = yd.mazeret_yaz(b, onizleme, k["ad"], vt.simdi())
                # Tür ve tarih aralığı kayda YAZILMAZ ("raporlu" sağlık verisine işaret eder); yalnız sayılar.
                vt.kayit_dus(b, k["ad"], "Mazeret girildi", f"{n} öğrenci, {onizleme['takvim_gunu']} gün", ip(istek))
        except ValueError as hata:
            return y.yonlendir("/yoklama/mazeret", str(hata), hata=True)
        # Tarih aralığı iletiye (dolayısıyla adrese ve tarayıcı geçmişine) yazılmaz; aynı sayfadaki listede görünür.
        return y.yonlendir("/yoklama/mazeret#liste", f"Mazeret kaydedildi: {n} öğrenci.")

    @uygulama.post("/yoklama/mazeret/{mazeret_id}/iptal")
    async def mazeret_iptal(istek: Request, mazeret_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        if form.get("eylem") != "iptal":
            return y.yonlendir("/yoklama/mazeret", "Bilinmeyen işlem.", hata=True)
        with vt.islem() as b:
            tamam = yd.mazeret_iptal(b, mazeret_id, k["ad"], vt.simdi())
            if tamam:
                vt.kayit_dus(b, k["ad"], "Mazeret kaldırıldı", "", ip(istek))
        if not tamam:
            return y.yonlendir("/yoklama/mazeret#liste", "Mazeret kaydı bulunamadı ya da zaten kaldırılmış.", hata=True)
        return y.yonlendir("/yoklama/mazeret#liste", "Mazeret kaldırıldı; yoklamadaki asıl durum yeniden görünür.")


# =================================================================================================
# SÖZLEŞME — şablon bağlamları (ayrıntı: yoklama_defter.py işlevlerinin dönüşleri)
#
# Ortak: adli_not (KVKK bandı), n_gun_notu ("N gündür… e-Okul devamsızlık günü değildir"). Hücre gösterimi
#   `_yoklama_hucre.html` makrolarındadır: simge + data-d (var|yok|gec|alinmadi|bos) + data-ozurlu + data-kapsam +
#   data-duz; renk tek başına anlam taşımaz (harf + desen). Mazeret türü hücrede YOKTUR.
# yoklama_sube.html: kip = bes | gun | bos; sube, subeler[str], bugun_iso.
#   kip=bes: d (yoklama_defter.sube_defteri) = {sube, bitis, bitis_yazi, gunler[{tarih, kisa, yazi, bugun, dersler[{ders_no, plan}]}],
#     satirlar[{id, okul_no, ad_soyad, pasif, n, rozet{tur: vurgulu|duz|ozurlu, kisa, metin}|None, serit[{simge, durum, metin}],
#     gunler[[hucre]], yok, gec}], ogrenci_sayisi, yalniz_yok, onceki, sonraki ("" = ileri yok), bugun, ders_sayisi,
#     plan_disi_var, devre_adi}. Gezgin: GET /yoklama/sube?sube&bitis[&yalniz_yok=1]. Hücre ve gün başlığı gün kipine bağlanır.
#   kip=gun: g (yoklama_defter.sube_gunu) = {sube, tarih, tarih_yazi, bugun, onceki, sonraki, duzenlenebilir, tatil, gec_var,
#     alinan, plan_disi_var, devre_adi, alinabilir_var, gun_boyu_yok (o gün alınan bütün derslerde yok öğrenci sayısı),
#     islendi, bayat, islendi_metni,
#     sutunlar[{ders_no, aralik, plan, alindi, gelecek, gec, yok_sayisi, gec_sayisi, alinabilir}],
#     satirlar[{id, okul_no, ad_soyad, pasif, hucreler[hucre + tiklanir], yok, gec, duzeltme_var}]}, firca (yok|gec|var),
#     duzeltme_notu, geri_gun, not_en_kisa, not_en_uzun.
#     Form (tek form, JS'siz çalışır; JS panel.js::defterKur yalnız fetch + yerinde güncelleme ekler):
#       POST /yoklama/sube/hucre {tarih, sube, durum, aciklama, hucre=<ogrenci_id>:<ders_no>}
#         → 303 aynı sayfa · Accept: application/json → {durum, ozurlu, kapsam, duzeltme, simge, durum_metni,
#           satir_ozeti{yok,gec}, sutun_ozeti{yok,gec}, degisti, ileti} (ad/no yok) · alınmamış saat 409 · diğer hata 400.
#       POST /yoklama/sube/toplu {tarih, sube, satir=<ogrenci_id>:butun_gun|temizle} | {sutun=<ders_no>} (→ onay sorusu:
#         aynı sayfa ?alindi=<ders_no>, bağlamda alindi_onay = sütun | None) | {alindi=<ders_no>[, alindi_yoklar=1]}.
#       JSON yanıtında ayrıca satir_duzeltme (satırda geçerli düzeltme kaldı mı: "Temizle" düğmesi).
#   hucre = {durum, ozurlu, kapsam, duzeltme, ders_no, simge, etiket ("Ad Soyad, 16.11 Pazartesi 3. ders: yok, özürlü")}.
# yoklama_son_gunler.html: liste (yoklama_defter.son_gunler) = {satirlar[{id, sube, okul_no, ad_soyad, n, rozet, serit}],
#   ozurluler, ozurlu_gizlenen, tarih_yazi, bugun}, esik. GET /yoklama/son-gunler[?ozurluler=1].
# yoklama_ogrenci.html: o (yoklama_defter.ogrenci_gorunumu) = {id, okul_no, ad_soyad, sube, pasif, sutunlar[int],
#   satirlar[{tarih, yazi, hucreler[hucre], yok, gec}], rozet, mazeretler[mazeret satırı], yok, gec}, gun_sayisi.
# yoklama_mazeret.html: liste[mazeret satırı], girdi{nolar, bas, bit, kapsam, ders_bas, ders_bit, tur, dayanak},
#   turler{kod: ad}, dayanaklar{kod: ad}, en_erken, en_gec, en_gec_metni, no_en_cok, gun_en_cok, liste_gun, k5_notu, silinme.
#   mazeret satırı = {id, ogrenci_id, okul_no, ad_soyad, sube, aralik, kapsam, iptal, tur_adi ("" = kaldırıldı), dayanak_adi,
#     giren, zaman, iptal_metni, durum: gecerli|ileride|bitti|kaldirildi}.
#   Form: POST /yoklama/mazeret/onizle {nolar, bas, bit, kapsam=tam|ders, ders_bas, ders_bit, tur, dayanak} (serbest metin YOK).
#   Kaldırma: POST /yoklama/mazeret/{id}/iptal {eylem=iptal} (<dialog> onayı, data-onay="mazeret_kaldir").
# yoklama_mazeret_onizleme.html: o (yoklama_defter.mazeret_onizle) = {ogrenciler[{id, okul_no, ad_soyad, sube}], bulunamayan[str],
#   gun_sayisi, takvim_gunu, ders_saati_sayisi, yok_kayitli, aralik, kapsam, tur_adi, dayanak_adi, devre_adi}, onizleme (belirteç),
#   omur_dk. Onay: POST /yoklama/mazeret/onayla {onizleme}.
# =================================================================================================
