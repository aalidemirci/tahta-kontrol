"""USB anahtar uçları (0.11.0): panel sayfası, tek seferlik indirme ve tahtanın /ajan/usb/* uçları.

Yetki (şartname §4.1): kendi anahtarını üretme/indirme/iptal iki role (yonetici, idareci) açık; öğretmen için
anahtar üretme, bütün anahtarları görme ve başkasınınkini iptal etme yalnız yöneticinin. Ayarlar › USB anahtar
`web.py`'dedir (bolum=usb_anahtar, yalnız yönetici). Her yazma, her reddedilen tahta isteği ve her
tahtadaki işlem (yoklama, kilit açma) işlem kaydına düşer; kendiliğinden yapılan başarılı tanıma düşmez (§7);
kayda gizli değer, PIN ve kişi adı YAZILMAZ (anahtar kimliği + öğretmen kodu ya da panel kullanıcı adı).

Gizli değer sunucudan yalnız bir kez ve yalnız dosya olarak çıkar: üretim satırı yazmaz, bekleyen anahtar
bellekte 5 dk durur; `GET /usb-anahtarlar/indir/{belirtec}` satırı yazar ve dosyayı verir (no-store).

Şablon bağlamları ve ajan sözleşmesi modül sonundaki SÖZLEŞME'dedir.
"""

from __future__ import annotations

import json

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from . import acil, metin, sinav, vt
from . import usb_anahtar as ua
from . import yoklama as yk

YETKI_ILETISI = "Bu işlem için yönetici yetkisi gerekir."


def _tamsayi(deger, varsayilan=None):
    s = str(deger if deger is not None else "").strip()
    return int(s) if metin.rakam_mi(s) and len(s) <= 9 else varsayilan


def ogretmen_secenekleri(b) -> list[dict]:
    """Anahtar üretilebilecek öğretmenler: etkin ve kodlu (tam ad yalnız panelde)."""
    return [
        {"id": o["id"], "etiket": f"{yk.ogretmen_tam_ad(o)} (kod {o['kod']})"}
        for o in sorted(
            b.execute("SELECT o.*, p.kod FROM ogretmen o JOIN ogretmen_pin p ON p.ogretmen_id = o.id WHERE o.aktif = 1").fetchall(),
            key=lambda o: (metin.tr_sirala_anahtari(o["soyad"]), metin.tr_sirala_anahtari(o["ad"])),
        )
    ]


def ayar_baglami(b) -> dict:
    """Ayarlar › USB anahtar bölümünün bağlamı (web.ayarlar_sayfasi çağırır)."""
    return {
        "usb_ayari": ua.ayar_al(b),
        "usb_destek": ua.tahta_destegi(b),
        "usb_yoklama_kapali": not yk.etkin(b),
    }


def kaydet(uygulama, y) -> None:
    depo = ua.BekleyenDepo()
    sinir = ua.TahtaSiniri()
    kopya = ua.KopyaIzleyici()
    uygulama.state.usb_bekleyen = depo
    uygulama.state.usb_sinir = sinir
    uygulama.state.usb_kopya = kopya

    def ip(istek: Request) -> str:
        return y.istemci_ip(istek)

    def pin_kapisi() -> yk.PinKapisi:
        # Ders yoklamasıyla AYNI kapı: öğretmen anahtarının PIN'i öğretmen PIN'idir, sayaçlar paylaşılır.
        kapi = getattr(uygulama.state, "yoklama_pin_kapisi", None)
        if kapi is None:
            kapi = uygulama.state.yoklama_pin_kapisi = yk.PinKapisi()
        return kapi

    def bekleyenleri_temizle(an: int | None = None) -> int:
        """Süresi dolan (indirilmeyen) anahtarlar düşer ve işlem kaydına yazılır. Zamanlayıcı da çağırır."""
        an = vt.simdi() if an is None else an
        dusen = depo.temizle(an)
        if dusen:
            with vt.islem() as b:
                for d in dusen:
                    vt.kayit_dus(b, "sistem", "USB anahtar indirilmedi",
                                 f"{ua.kimlik_bicimli(d.kimlik)} · {ua.BEKLEYEN_OMRU_SN // 60} dk içinde indirilmedi; kaydedilmedi")  # fmt: skip
        return len(dusen)

    uygulama.state.usb_bekleyen_temizle = bekleyenleri_temizle

    def reddet(istek: Request, k, islem: str, donus: str):
        with vt.islem() as b:
            vt.kayit_dus(b, k["ad"], "Yetkisiz işlem reddedildi", islem, ip(istek))
        return y.yonlendir(donus, YETKI_ILETISI, hata=True)

    # ---- panel ------------------------------------------------------------------------------------
    @uygulama.get("/usb-anahtarlar", response_class=HTMLResponse)
    async def anahtarlar_sayfasi(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        bekleyenleri_temizle()
        an = vt.simdi()
        yonetici = k["rol"] == "yonetici"
        with vt.islem() as b:
            ayar_ = ua.ayar_al(b)
            tum = ua.liste(b, an, None if yonetici else k["id"])
            ogretmenler = ogretmen_secenekleri(b) if yonetici else []
            destek = ua.tahta_destegi(b)
            yoklama_kapali = not yk.etkin(b)
        kendi = [a for a in tum if a["kullanici_id"] == k["id"]]
        return y.sayfa(
            istek, "usb_anahtarlar.html", k,
            usb_ayari=ayar_, ozellik_kapali=not ayar_["etkin"], kapali_iletisi=ua.ILETI_KAPALI_PANEL, yonetici=yonetici,
            kendi_anahtarlar=kendi, kendi_dolu=sum(1 for a in kendi if a["durum"] != "iptal") >= ua.KISI_BASI_EN_COK,
            anahtarlar=tum, ogretmenler=ogretmenler, secili_ogretmen_id=_tamsayi(istek.query_params.get("ogretmen_id")),
            destek=destek, yoklama_kapali=yoklama_kapali, kisi_basi=ua.KISI_BASI_EN_COK,
            etiket_en_uzun=ua.ETIKET_EN_UZUN, dosya_adi=ua.DOSYA_ADI,
        )  # fmt: skip

    @uygulama.post("/usb-anahtarlar")
    async def anahtar_islem(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        eylem = str(form.get("eylem", ""))
        an = vt.simdi()
        donus = "/usb-anahtarlar"
        bekleyenleri_temizle(an)
        if eylem == "uret":
            sahip = str(form.get("sahip", "kendim"))
            if sahip == "ogretmen" and k["rol"] != "yonetici":
                return reddet(istek, k, "USB anahtar üretme (öğretmen)", donus)
            ogretmen_id = _tamsayi(form.get("ogretmen_id")) if sahip == "ogretmen" else None
            if sahip == "ogretmen":
                # Hata iletisi öğretmen kutusunda çizilir; seçilen öğretmen korunur.
                donus = "/usb-anahtarlar?yer=ogretmen" + (f"&ogretmen_id={ogretmen_id}" if ogretmen_id is not None else "") + "#ogretmen"
            try:
                with vt.islem() as b:
                    if sahip == "ogretmen":
                        if ogretmen_id is None:
                            raise ValueError("Öğretmeni seçin.")
                        bekleyen, pin = ua.uret(b, sahip_turu="ogretmen", kullanici_id=None, ogretmen_id=ogretmen_id,
                                                etiket=form.get("etiket", ""), olusturan=k["ad"], olusturan_id=k["id"],
                                                parmak_izi=y.parmak_izi, an=an, bekleyen_kimlikler=depo.kimlikler())  # fmt: skip
                    elif sahip == "kendim":
                        bekleyen, pin = ua.uret(b, sahip_turu="kullanici", kullanici_id=k["id"], ogretmen_id=None,
                                                etiket=form.get("etiket", ""), olusturan=k["ad"], olusturan_id=k["id"],
                                                parmak_izi=y.parmak_izi, an=an, bekleyen_kimlikler=depo.kimlikler())  # fmt: skip
                    else:
                        raise ValueError("Bilinmeyen işlem.")
                    vt.kayit_dus(b, k["ad"], "USB anahtar üretildi",
                                 f"{ua.kimlik_bicimli(bekleyen.kimlik)} · {bekleyen.sahip_kodu} (indirilmeyi bekliyor)", ip(istek))  # fmt: skip
                    sahip_metni = ""
                    if sahip == "ogretmen":
                        o = b.execute("SELECT o.*, p.kod FROM ogretmen o JOIN ogretmen_pin p ON p.ogretmen_id = o.id WHERE o.id = ?",
                                      (ogretmen_id,)).fetchone()  # fmt: skip
                        sahip_metni = f"{yk.ogretmen_tam_ad(o)} (kod {o['kod']})"
                    else:
                        sahip_metni = k["gorunen_ad"] or k["ad"]
                    ayar_ = ua.ayar_al(b)
            except ValueError as hata:
                return y.yonlendir(donus, str(hata), hata=True)
            belirtec = depo.koy(bekleyen)
            yanit = y.sayfa(
                istek, "usb_anahtar_uretildi.html", k,
                kimlik=ua.kimlik_bicimli(bekleyen.kimlik), tur="ogretmen" if bekleyen.sahip_turu == "ogretmen" else "idare",
                sahip_metni=sahip_metni, etiket=bekleyen.etiket, indir_adresi=f"/usb-anahtarlar/indir/{belirtec}",
                pin=yk.pin_bicimli(pin) if pin else None, pin_sorulur=ua.pin_gerek({"sahip_turu": bekleyen.sahip_turu}, ayar_),
                omur_dk=ua.BEKLEYEN_OMRU_SN // 60, dosya_adi=ua.DOSYA_ADI, ozellik_kapali=not ayar_["etkin"],
            )  # fmt: skip
            yanit.headers["Cache-Control"] = "no-store"
            return yanit
        if eylem == "iptal":
            anahtar_id = _tamsayi(form.get("id"), -1)
            with vt.islem() as b:
                satir = b.execute("SELECT * FROM usb_anahtar WHERE id = ?", (anahtar_id,)).fetchone()
            if not satir:
                return y.yonlendir(donus, "Anahtar bulunamadı.", hata=True)
            if k["rol"] != "yonetici" and satir["kullanici_id"] != k["id"]:
                return reddet(istek, k, f"USB anahtar iptali ({ua.kimlik_bicimli(satir['kimlik'])})", donus)
            with vt.islem() as b:
                yapildi = ua.iptal(b, anahtar_id, k["ad"], an, ip(istek))
            if not yapildi:
                return y.yonlendir(donus, "Anahtar zaten iptal edilmiş.", hata=True)
            return y.yonlendir(donus, f"{ua.kimlik_bicimli(satir['kimlik'])} iptal edildi; tahtalarda hemen geçersiz.")
        return y.yonlendir(donus, "Bilinmeyen işlem.", hata=True)

    @uygulama.get("/usb-anahtarlar/indir/{belirtec}")
    async def anahtar_indir(istek: Request, belirtec: str):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        an = vt.simdi()
        bekleyenleri_temizle(an)
        bekleyen = depo.al(belirtec, k["id"], an)
        if not bekleyen:
            return y.yonlendir("/usb-anahtarlar", ua.ILETI_INDIRME_YOK, hata=True)
        try:
            with vt.islem() as b:
                ua.kaydet(b, bekleyen, an)
                vt.kayit_dus(b, k["ad"], "USB anahtar indirildi", f"{ua.kimlik_bicimli(bekleyen.kimlik)} · {bekleyen.sahip_kodu}",
                             ip(istek))  # fmt: skip
        except ValueError as hata:
            return y.yonlendir("/usb-anahtarlar", str(hata), hata=True)
        return Response(
            ua.dosya_metni(bekleyen),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{ua.DOSYA_ADI}"', "Cache-Control": "no-store"},
        )

    # ---- tahta (ajan) uçları ------------------------------------------------------------------------
    def hata(ileti: str, neden: str, kod: int, **ek) -> JSONResponse:
        return JSONResponse({"hata": ileti, "neden": neden, **ek}, status_code=kod)

    async def ajan_on(istek: Request):
        """Ortak ön denetim: tahta, gövde (≤ 4 KB JSON), özellik açık, hız sınırı, sınav. ((tahta, govde), None) ya da (None, yanıt)."""
        tahta = y.tahta_dogrula(istek)
        if not tahta:
            return None, JSONResponse({"hata": "Tahta tanınmıyor."}, status_code=401)
        if tahta["durum"] != "onayli":
            return None, JSONResponse({"hata": "Tahta onaylı değil."}, status_code=403)
        uzunluk = istek.headers.get("content-length", "")
        if uzunluk and (not metin.rakam_mi(uzunluk) or int(uzunluk) > ua.GOVDE_SINIRI):
            return None, JSONResponse({"hata": "İstek çok büyük."}, status_code=413)
        govde_bayt = await istek.body()
        if len(govde_bayt) > ua.GOVDE_SINIRI:
            return None, JSONResponse({"hata": "İstek çok büyük."}, status_code=413)
        try:
            govde = json.loads(govde_bayt or b"{}")
        except (ValueError, UnicodeDecodeError):
            return None, JSONResponse({"hata": "Geçersiz istek."}, status_code=400)
        if not isinstance(govde, dict):
            return None, JSONResponse({"hata": "Geçersiz istek."}, status_code=400)
        an = vt.simdi()
        with vt.islem() as b:
            if not ua.ayar_al(b)["etkin"]:
                return None, hata(ua.ILETI_KAPALI, "kapali", 409)
        bekleme, ileti = sinir.istek(tahta["id"], an)
        if bekleme:
            return None, hata(ileti, "tahta_kapali" if ileti == ua.ILETI_TAHTA_KAPALI else "cok_istek", 429, bekleme_sn=bekleme)
        with vt.islem() as b:
            if sinav.tahta_sinav_penceresinde(b, tahta["id"], an):
                return None, hata(ua.ILETI_SINAV, "sinav", 409)
        return (tahta, govde), None

    def tanima(b, istek: Request, tahta, govde, an: int):
        """Anahtarı doğrular; (satır, sahip) ya da hata yanıtı. Reddedilen her deneme işlem kaydına düşer."""
        kim = f"tahta:{tahta['ad']}"
        durum, satir, sahip = ua.tani(b, govde.get("kimlik"), govde.get("gizli"), tahta["id"], an)
        if durum == "tamam":
            kopya.denetle(b, satir, tahta["id"], an)
            return satir, sahip
        if durum == "kapali":
            return hata(ua.ILETI_KAPALI, "kapali", 409)
        if durum == "gecersiz":
            kimlik = ua.kimlik_duzelt(govde.get("kimlik"))
            kapandi = sinir.gecersiz(tahta["id"], an)
            ayrinti = f"kimlik {ua.kimlik_bicimli(kimlik)}" if kimlik else "kimlik biçimsiz"
            vt.kayit_dus(b, kim, "Geçersiz USB anahtar", ayrinti + ("; tahta 10 dk kapatıldı" if kapandi else ""), ip(istek))
            if kapandi:
                return hata(ua.ILETI_TAHTA_KAPALI, "tahta_kapali", 429, bekleme_sn=ua.GECERSIZ_KAPALI_SN)
            return hata(ua.ILETI_GECERSIZ, "gecersiz", 403)
        ayrinti = ua.kimlik_bicimli(satir["kimlik"])
        if durum == "iptal":
            vt.kayit_dus(b, kim, "Reddedilen USB anahtar", f"{ayrinti} · iptal edilmiş", ip(istek))
            return hata(ua.ILETI_IPTAL, "iptal", 410)
        if durum == "kilitli":
            ogretmen_pin = satir["durum"] == "etkin"  # anahtar etkin ama öğretmenin PIN'i kilitli
            vt.kayit_dus(b, kim, "Reddedilen USB anahtar", f"{ayrinti} · {'öğretmen PIN’i kilitli' if ogretmen_pin else 'PIN kilitli'}",
                         ip(istek))  # fmt: skip
            return hata(ua.ILETI_OGRETMEN_PIN_KILITLI if ogretmen_pin else ua.ILETI_KILITLI, "kilitli", 423)
        # sahip_pasif: pasif öğretmen / kapalı kullanıcı — anahtar kendiliğinden geçersizdir (aynı ileti)
        vt.kayit_dus(b, kim, "Reddedilen USB anahtar", f"{ayrinti} · sahibi pasif", ip(istek))
        return hata(ua.ILETI_GECERSIZ, "gecersiz", 403)

    def pin_asamasi(b, istek: Request, tahta, govde, satir, sahip, an: int):
        """Ayara göre PIN gerekiyorsa doğrular; None (geçti) ya da hata yanıtı."""
        if not ua.pin_gerek(satir, ua.ayar_al(b)):
            return None
        pin = govde.get("pin")
        if not isinstance(pin, str) or not pin:
            return hata(ua.ILETI_PIN_GEREK, "pin_gerek", 403, pin_gerek=True)
        kapi = pin_kapisi()
        kim = f"tahta:{tahta['ad']}"
        durum, bekleme = ua.pin_dogrula(b, kapi, satir, sahip, pin, tahta["id"], an)
        ayrinti = ua.kimlik_bicimli(satir["kimlik"])
        if durum == "tamam":
            return None
        if durum == "bekle":
            cift = sahip["kod"] if satir["sahip_turu"] == "ogretmen" else "usb:" + satir["kimlik"]
            ileti = kapi.bekleme(tahta["id"], cift, an)[1] or yk.ILETI_BEKLE
            vt.kayit_dus(b, kim, "USB anahtar PIN girişi bekletildi", f"{ayrinti} · {bekleme} sn", ip(istek))
            return hata(ileti, "bekle", 429, bekleme_sn=bekleme)
        if durum == "kilitli":
            if satir["sahip_turu"] == "ogretmen":
                vt.kayit_dus(b, kim, "Hatalı USB anahtar PIN'i", f"{ayrinti} · öğretmen PIN'i kilitlendi", ip(istek))
                return hata(ua.ILETI_OGRETMEN_PIN_KILITLI, "kilitli", 423, bekleme_sn=0)
            vt.kayit_dus(b, kim, "USB anahtar kilitlendi", ayrinti, ip(istek))
            return hata(ua.ILETI_KILITLI, "kilitli", 423, bekleme_sn=0)
        vt.kayit_dus(b, kim, "Hatalı USB anahtar PIN'i", ayrinti, ip(istek))
        return hata(ua.ILETI_PIN_HATALI, "pin", 403, bekleme_sn=0)

    @uygulama.post("/ajan/usb/tani")
    async def ajan_tani(istek: Request):
        cozulen, yanit = await ajan_on(istek)
        if yanit:
            return yanit
        tahta, govde = cozulen
        an = vt.simdi()
        with vt.islem() as b:
            sonuc = tanima(b, istek, tahta, govde, an)
            if isinstance(sonuc, JSONResponse):
                return sonuc
            satir, sahip = sonuc
            ayar_ = ua.ayar_al(b)
            # Başarılı tanıma işlem kaydına YAZILMAZ: ajan belleği takılır takılmaz (dokunuş beklemeden) sorar,
            # yani bellek yalnız sunum için takıldığında da tanıma olur. Her tanımayı kayda yazmak, personelin
            # hangi gün hangi tahtada olduğunu süresiz biriktirirdi (§7 "yalnız son değer"). Son kullanım ve
            # tahtası usb_anahtar satırında tutulur; reddedilen denemeler ve kullanıcının işlemleri kayda düşer.
            ua.kullanildi(b, satir, tahta["id"], an)
            return {"anahtar": ua.gorunum(b, satir, sahip), "pin_gerek": ua.pin_gerek(satir, ayar_), "izinler": ua.izinler(b, ayar_),
                    "omur_sn": ua.TANI_OMRU_SN}  # fmt: skip

    @uygulama.post("/ajan/usb/yoklama")
    async def ajan_yoklama(istek: Request):
        cozulen, yanit = await ajan_on(istek)
        if yanit:
            return yanit
        tahta, govde = cozulen
        an = vt.simdi()
        with vt.islem() as b:
            if not yk.etkin(b):
                return hata(yk.ILETI_ETKIN_DEGIL, "yoklama_kapali", 409)
            sonuc = tanima(b, istek, tahta, govde, an)
            if isinstance(sonuc, JSONResponse):
                return sonuc
            satir, sahip = sonuc
            red = pin_asamasi(b, istek, tahta, govde, satir, sahip, an)
            if red:
                return red
            yoklama_ayari = yk.ayar_al(b)
            if satir["sahip_turu"] == "ogretmen":
                belirtec, bitis = yk.oturum_ac(b, ogretmen_id=satir["ogretmen_id"], tahta_id=tahta["id"], an=an,
                                               oturum_dk=yoklama_ayari["oturum_dk"], anahtar_id=satir["id"])  # fmt: skip
            else:
                belirtec, bitis = yk.oturum_ac(b, kullanici_id=satir["kullanici_id"], tahta_id=tahta["id"], an=an,
                                               oturum_dk=yoklama_ayari["oturum_dk"], anahtar_id=satir["id"])  # fmt: skip
            ua.kullanildi(b, satir, tahta["id"], an)
            gorunum = ua.gorunum(b, satir, sahip)
            vt.kayit_dus(b, f"tahta:{tahta['ad']}", "Yoklama oturumu açıldı (USB anahtar)", ua.kayit_ayrintisi(b, satir, sahip),
                         ip(istek))  # fmt: skip
            # 0.14.0: öğretmen anahtarında programdan ön seçim; idare anahtarında (ogretmen_id yok) ikisi de boş.
            program = yk.ogretmen_onerisi(b, satir["ogretmen_id"] if satir["sahip_turu"] == "ogretmen" else None, tahta, an,
                                          yk.GEC_YETENEGI in acil.yetenekler(tahta))  # fmt: skip
        # /ajan/yoklama/baslat ile AYNI biçim (+ "tur", 0.14.0: "oneri", "subeler_once"): sonraki uçlar değişmeden kullanılır.
        return {"belirtec": belirtec, "kalan_sn": bitis - an, "bosta_sn": yoklama_ayari["bosta_dk"] * 60,
                "ogretmen": {"kod": gorunum["kod"], "etiket": gorunum["etiket"]}, "tur": gorunum["tur"],
                "oneri": program["oneri"], "subeler_once": program["subeler_once"]}  # fmt: skip

    @uygulama.post("/ajan/usb/kilit_ac")
    async def ajan_kilit_ac(istek: Request):
        cozulen, yanit = await ajan_on(istek)
        if yanit:
            return yanit
        tahta, govde = cozulen
        an = vt.simdi()
        with vt.islem() as b:
            if not ua.ayar_al(b)["kilit_acar"]:
                return hata(ua.ILETI_KILIT_KAPALI, "kilit_kapali", 409)
            sonuc = tanima(b, istek, tahta, govde, an)
            if isinstance(sonuc, JSONResponse):
                return sonuc
            satir, sahip = sonuc
            red = pin_asamasi(b, istek, tahta, govde, satir, sahip, an)
            if red:
                return red
            ua.kullanildi(b, satir, tahta["id"], an)
            # Sunucu kilit durumunu DEĞİŞTİRMEZ (kilit tahtadadır): onay verir, kayda yazar; kilidi servis açar.
            vt.kayit_dus(b, f"tahta:{tahta['ad']}", "Kilit USB anahtarla açıldı", ua.kayit_ayrintisi(b, satir, sahip), ip(istek))
        return {"tamam": True}


# =================================================================================================
# SÖZLEŞME — şablon bağlamları ve ajan protokolü (sonraki uygulayıcı için; ayrıntı raporda)
#
# usb_anahtarlar.html (GET /usb-anahtarlar; iki role açık):
#   usb_ayari{etkin,kilit_acar,pin_idare,pin_ogretmen}, ozellik_kapali (bool), kapali_iletisi, yonetici (bool),
#   kendi_anahtarlar[satir], kendi_dolu (bool: 2 etkin var, üret düğmesi devre dışı), anahtarlar[satir] (yönetici: hepsi;
#   idareci: yalnız kendininkiler), ogretmenler[{id,etiket}] (yalnız yönetici), secili_ogretmen_id (int|None; ?ogretmen_id=),
#   destek{onayli,destekleyen,eski}, yoklama_kapali, kisi_basi (2), etiket_en_uzun (30), dosya_adi.
#   satir = {id, kimlik "K7Q2-M9XA", sahip_turu kullanici|ogretmen, tur idare|ogretmen, sahip ("A. Yılmaz (112)" | görünen ad),
#            etiket, olusturma "gg.aa.yyyy SS:DD", olusturan, son_kullanim ("… · Tahta adı" | "Hiç kullanılmadı"),
#            durum etkin|kilitli|iptal, durum_adi, iptal (metin), kopya_uyarisi (bool), kullanici_id, ogretmen_id}.
#   Formlar: POST /usb-anahtarlar {eylem=uret, sahip=kendim, etiket} · {eylem=uret, sahip=ogretmen, ogretmen_id, etiket}
#            · {eylem=iptal, id} (<dialog> onayı).
# usb_anahtar_uretildi.html (POST yanıtı, no-store): kimlik, tur (idare|ogretmen), sahip_metni, etiket, indir_adresi,
#   pin ("482 913" | None; yalnız idare anahtarında), pin_sorulur (bool, şu anki ayara göre), omur_dk (5), dosya_adi,
#   ozellik_kapali. İndirme: GET {indir_adresi} → application/octet-stream, attachment; filename="tahta-kontrol.anahtar".
# ayarlar.html (bolum=usb_anahtar, web.py): usb_ayari, usb_destek{onayli,destekleyen,eski}, usb_yoklama_kapali.
#   Alanlar: ua_etkin, ua_kilit_acar, ua_pin_idare, ua_pin_ogretmen (=1). Yönlendirme /ayarlar?yer=usb_anahtar#ileti.
# ogretmenler.html: ek bağlam usb_sayilari {ogretmen_id: n} → "USB anahtar" sütunu; yönetici bağlantısı
#   /usb-anahtarlar?ogretmen_id=<id>#ogretmen.
#
# Ajan uçları (hepsi POST, X-Tahta-Id/X-Tahta-Anahtar, onaylı tahta, gövde ≤ 4096 bayt JSON; her gövdede kimlik, gizli):
#   Ortak hatalar (hepsi {"hata": ileti, "neden": kod, ["bekleme_sn"]}):
#     409 kapali · 429 cok_istek|tahta_kapali (+bekleme_sn) · 409 sinav · 403 gecersiz · 410 iptal · 423 kilitli.
#   /ajan/usb/tani → 200 {"anahtar": {"tur": "idare"|"ogretmen", "etiket": "A. Yılmaz"|"İdare · A. Demir", "kod": "112"|""},
#                         "pin_gerek": bool, "izinler": ["yoklama"?, "kilit_ac"?], "omur_sn": 600}
#   /ajan/usb/yoklama {+pin?} → 200 {"belirtec","kalan_sn","bosta_sn","ogretmen":{"kod","etiket"},"tur"}
#                         ek hatalar: 409 yoklama_kapali · 403 pin_gerek (+pin_gerek:true) · 403 pin · 429 bekle · 423 kilitli
#   /ajan/usb/kilit_ac {+pin?} → 200 {"tamam": true}; ek hatalar: 409 kilit_kapali · 403 pin_gerek · 403 pin · 429 bekle · 423
#   /ajan/bekle yanıtında ayar.usb_anahtar = {"etkin": bool} (durum tabanlı; alan yoksa = eski sunucu → izleme kapalı).
# =================================================================================================
