"""Panel (A6 çekirdeği): şifreli yedekler, geri yükleme, tahta envanteri, arıza kayıtları, yerel durum.

Yetki (ortak sözlük §3): yedek, demirbaş no, donanım uyarısını kapatma yalnız yönetici; envanteri
görme ve arıza açma/izleme iki role açık. Geri yükleme yalnız 127.0.0.1'den ve yöneticiyle; ilk
kurulum gerekiyorsa (kullanıcı yok) yalnız 127.0.0.1'den, oturumsuz. Her değiştirici işlem
`kayit`'a düşer; parola hiçbir iletiye ve kayda girmez.
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime

from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from . import __version__, ariza, ayar, envanter, guvenlik, vt, yedek

ISTANBUL = yedek.ISTANBUL
GERI_YUKLEME_HATA_SINIRI = (5, 600)  # K-B5: 5 başarısız deneme / 10 dk (IP başına)
YEDEK_PAROLA_SINIRI = (5, 600)
KVKK_YEDEK_NOTU = (
    "Şifreli yedekler; öğretim yılı sonunda silinen ders yoklaması, sınav listesi ve boş ders uyarısı gibi "
    "kişisel verinin kopyasını, silindikten sonra da yedek saklama süresi kadar (günlük yedek sayısı kadar gün) "
    "taşır. Elle alınan "
    "yedekler de bu süreden eskiyince silinir. Geri yüklemede bir önceki veritabanı en çok bu süre kadar "
    "saklanır; onaylanmamış geri yükleme dosyaları bir gün sonra silinir. Bilgisayarınıza indirdiğiniz "
    "yedekleri siz silmelisiniz."
)


def yedek_ayar_baglami(b) -> dict:
    """Yedek parolası ve saklama formlarının bağlamı: Yedekler sayfası ve Ayarlar › Veri saklama ve yedek (0.16.0)
    aynı işlevi kullanır. Parola hiçbir alana geri yazılmaz; yalnız "var mı" ve belirlenme zamanı."""
    ayar_ = yedek.ayarlar(b)
    return {
        "yedek_ayari": {
            "parola_var": ayar_["parola_var"],
            "parola_zamani": ayar_.get("parola_zamani"),
            "saklama": int(ayar_.get("saklama") or yedek.SAKLAMA_VARSAYILAN),
            "kopya_dizini": ayar_.get("kopya_dizini") or "",
        },
        "saklama_aralik": yedek.SAKLAMA_ARALIK,
        "parola_en_kisa": yedek.PAROLA_EN_KISA,
    }


def donus_adresi(form, yer: str) -> str:
    """Yedek formlarının dönüş adresi. Ayarlar'daki form gizli `donus=ayarlar` yollar; başka her değer yok
    sayılır (beyaz liste: açık yönlendirme yok)."""
    if form.get("donus") == "ayarlar":
        return f"/ayarlar/veri?yer={yer}#ileti"
    return f"/yedekler?yer={yer}#ileti"


def kaydet(uygulama, y) -> None:
    geri_yukleme_hatalari: dict[str, list[float]] = defaultdict(list)
    parola_denemeleri: dict[str, list[float]] = defaultdict(list)

    def yonetici_mi(k) -> bool:
        return bool(k) and k["rol"] == "yonetici"

    def ip(istek: Request) -> str:
        return y.istemci_ip(istek)

    # ---- yerel durum (durum penceresi; 6B'de hizmet kipini seçer) ----------------------
    @uygulama.get("/yerel/durum")
    async def yerel_durum(istek: Request):
        if not y.yerel_mi(istek):
            return JSONResponse({"hata": "Bulunamadı."}, status_code=404)
        with vt.islem() as b:
            ayar_ = yedek.ayarlar(b)
            son = yedek.son_yedek(b)
        return {
            "surum": __version__,
            "ag_adresleri": [f"https://{a}:{ayar.HTTPS_PORT}" for a in guvenlik.yerel_ipler()],
            "parmak_izi_kisa": (y.parmak_izi or "")[:16],
            "yedek_parolasi_var": ayar_["parola_var"],
            "son_yedek": {"zaman": son.get("zaman"), "basarili": son.get("basarili")} if son else {"zaman": None, "basarili": None},
            "paket_imzali": False,  # 6B (paket imzası) gelene kadar
            "hizmet": ayar.HIZMET,
        }

    # ---- yedekler -------------------------------------------------------------------
    def yedekler_baglami(b) -> dict:
        ayar_ = yedek.ayarlar(b)
        son = yedek.son_yedek(b)
        simdi = vt.simdi()
        bugun = yedek.bugunun_gunlugu_var(simdi)
        if not ayar_["parola_var"]:
            sonraki = "Parola belirlenmeden otomatik yedek alınmaz."
        elif bugun:
            sonraki = "Bugünün yedeği alındı; sonraki yarın."
        else:
            sonraki = "Program açıldıktan 5 dakika sonra (bugün)."
        return {
            **yedek_ayar_baglami(b),
            "son_yedek": son,
            "bugun_alindi": bugun,
            "sonraki_otomatik": sonraki,
            "klasor": str(yedek.dizin()),
            "yedekler": yedek.listele(),
            "izin_komutu": yedek.izin_komutu(ayar_.get("kopya_dizini") or "D:\\TahtaYedek"),
            "kvkk_notu": KVKK_YEDEK_NOTU,
            "bekleyen": yedek.bekleyen_oku(),
        }

    @uygulama.get("/yedekler", response_class=HTMLResponse)
    async def yedekler_sayfasi(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        if not yonetici_mi(k):
            return y.yonlendir("/", "Bu sayfa için yönetici yetkisi gerekir.", hata=True)
        with vt.islem() as b:
            baglam = yedekler_baglami(b)
        return y.sayfa(istek, "yedekler.html", k, yerel=y.yerel_mi(istek), **baglam)

    @uygulama.post("/yedekler/parola")
    async def yedek_parolasi(istek: Request):
        k = y.kullanici(istek)
        if not yonetici_mi(k):
            return y.yetkisiz_reddet(istek, k, "Yedek parolası")
        form = await istek.form()
        adres = donus_adresi(form, "parola")
        hesap = str(form.get("hesap_parolasi", ""))
        parola, parola2 = str(form.get("parola", "")), str(form.get("parola2", ""))
        if not y.hiz_siniri(parola_denemeleri, ip(istek), *YEDEK_PAROLA_SINIRI):
            return y.yonlendir(adres, "Çok fazla deneme yapıldı. Birkaç dakika sonra yeniden deneyin.", hata=True)
        if not guvenlik.parola_dogrula(hesap, k["parola_ozet"]):
            with vt.islem() as b:
                vt.kayit_dus(b, k["ad"], "Yedek parolası belirlenemedi", "Hesap parolası doğrulanamadı.", ip(istek))
            return y.yonlendir(adres, "Hesap parolanız doğrulanamadı.", hata=True)
        try:
            yedek.parola_dogrula(parola, parola2)
        except yedek.YedekHatasi as hata:
            return y.yonlendir(adres, str(hata), hata=True)

        def belirle() -> bool:
            with vt.islem() as b:
                degisti = yedek.parola_belirle(b, parola)
                vt.kayit_dus(b, k["ad"], "Yedek parolası değiştirildi" if degisti else "Yedek parolası belirlendi", "", ip(istek))
            return degisti

        degisti = await run_in_threadpool(belirle)
        mesaj = "Yedek parolası değiştirildi." if degisti else "Yedek parolası belirlendi. Bugünün yedeği 5 dakika içinde alınır."
        if yedek.bugunun_gunlugu_var():
            # K-B4: yeni parolayla açılabilen bir yedek hemen olsun.
            try:
                await run_in_threadpool(lambda: yedek.yedek_al("elle", kullanici=k["ad"], ip=ip(istek)))
                mesaj += " Yeni parolayla bir yedek hemen alındı."
            except yedek.YedekHatasi as hata:
                mesaj += f" Yeni parolayla yedek alınamadı: {hata}"
        return y.yonlendir(adres, mesaj)

    @uygulama.post("/yedekler/ayar")
    async def yedek_ayari(istek: Request):
        k = y.kullanici(istek)
        if not yonetici_mi(k):
            return y.yetkisiz_reddet(istek, k, "Yedek ayarları")
        form = await istek.form()
        adres = donus_adresi(form, "ayar")
        try:
            saklama = int(str(form.get("saklama", "")).strip())
        except ValueError:
            saklama = 0
        alt, ust = yedek.SAKLAMA_ARALIK
        if not alt <= saklama <= ust:
            return y.yonlendir(adres, f"Saklama sayısı {alt}–{ust} arasında olmalı.", hata=True)
        try:
            kopya = await run_in_threadpool(yedek.kopya_dizini_dogrula, str(form.get("kopya_dizini", "")))
        except yedek.YedekHatasi as hata:
            return y.yonlendir(adres, str(hata), hata=True)
        with vt.islem() as b:
            ayar_ = yedek.ayarlar(b)
            ayar_.update(saklama=saklama, kopya_dizini=kopya)
            yedek._ayar_yaz(b, ayar_)
            vt.kayit_dus(b, k["ad"], "Yedek ayarları kaydedildi",
                         f"saklama {saklama} · ikinci kopya {kopya or 'yok'}", ip(istek))  # fmt: skip
        return y.yonlendir(adres, "Yedek ayarları kaydedildi.")

    @uygulama.post("/yedekler/al")
    async def yedek_al(istek: Request):
        k = y.kullanici(istek)
        if not yonetici_mi(k):
            return y.yetkisiz_reddet(istek, k, "Elle yedek")
        adres = "/yedekler?yer=durum#ileti"
        try:
            sonuc = await run_in_threadpool(lambda: yedek.yedek_al("elle", kullanici=k["ad"], ip=ip(istek)))
        except yedek.YedekHatasi as hata:
            return y.yonlendir(adres, str(hata), hata=True)
        mesaj = f"Yedek alındı: {sonuc['dosya']} ({yedek.boyut_metni(sonuc['boyut'])})."
        if not sonuc["yeni"]:
            mesaj = f"Bu saniyede alınmış yedek zaten var: {sonuc['dosya']}."
        if sonuc["kopya_hata"]:
            mesaj += f" İkinci kopya yazılamadı: {sonuc['kopya_hata']}"
        return y.yonlendir(adres, mesaj, hata=bool(sonuc["kopya_hata"]))

    @uygulama.get("/yedekler/indir/{ad}")
    async def yedek_indir(istek: Request, ad: str):
        k = y.kullanici(istek)
        if not yonetici_mi(k):
            return y.yetkisiz_reddet(istek, k, "Yedek indirme")
        yol = yedek.indirilecek_yol(ad)
        if not yol:
            return Response("Yedek bulunamadı.", status_code=404, media_type="text/plain; charset=utf-8")
        with vt.islem() as b:
            vt.kayit_dus(b, k["ad"], "Yedek indirildi", yol.name, ip(istek))
        return FileResponse(yol, media_type="application/octet-stream", filename=yol.name,
                            headers={"Cache-Control": "no-store"})  # fmt: skip

    # ---- geri yükleme ---------------------------------------------------------------
    def geri_yukleme_izni(istek: Request):
        """(None, k, kurulum) izinliyse; değilse (yanıt, k, kurulum)."""
        kurulum = y.kurulum_gerekli()
        k = None if kurulum else y.kullanici(istek)
        if not y.yerel_mi(istek):
            if k:
                with vt.islem() as b:
                    vt.kayit_dus(b, k["ad"], "Geri yükleme reddedildi", "Ağdan istek (yalnız yerel)", ip(istek))
            hedef = "/yedekler?yer=geri#ileti" if yonetici_mi(k) else ("/kurulum" if kurulum else "/")
            return y.yonlendir(hedef, "Geri yükleme yalnız sunucunun kurulu olduğu bilgisayardan yapılır.", hata=True), k, kurulum
        if kurulum:
            return None, None, True
        if not k:
            return y.yonlendir("/giris"), None, False
        if not yonetici_mi(k):
            return y.yetkisiz_reddet(istek, k, "Yedekten geri yükleme"), k, False
        return None, k, False

    def geri_adresi(kurulum: bool) -> str:
        return "/yedekler/geri-yukle" if kurulum else "/yedekler?yer=geri#ileti"

    @uygulama.get("/yedekler/geri-yukle", response_class=HTMLResponse)
    async def geri_yukle_formu(istek: Request):
        red, k, kurulum = geri_yukleme_izni(istek)
        if red:
            return red
        if not kurulum:
            return y.yonlendir("/yedekler#geri-yukleme")
        return y.sayfa(istek, "yedek_geri_yukle.html", None, kurulum=True, bekleyen=yedek.bekleyen_oku())

    @uygulama.post("/yedekler/geri-yukle")
    async def geri_yukle(istek: Request):
        red, k, kurulum = geri_yukleme_izni(istek)
        if red:
            return red
        kim = k["ad"] if k else "?"
        adres = geri_adresi(kurulum)
        anahtar = ip(istek)
        simdi = time.time()
        pencere = GERI_YUKLEME_HATA_SINIRI[1]
        geri_yukleme_hatalari[anahtar] = [z for z in geri_yukleme_hatalari[anahtar] if simdi - z < pencere]
        if len(geri_yukleme_hatalari[anahtar]) >= GERI_YUKLEME_HATA_SINIRI[0]:
            return y.yonlendir(adres, "Çok fazla başarısız deneme yapıldı. On dakika sonra yeniden deneyin.", hata=True)
        try:
            if int(istek.headers.get("content-length") or 0) > yedek.DOSYA_EN_BUYUK + 1024 * 1024:
                return y.yonlendir(adres, "Yedek dosyası en çok 200 MB olabilir.", hata=True)
        except ValueError:
            return y.yonlendir(adres, "Yedek dosyası okunamadı.", hata=True)
        try:
            form = await istek.form(max_files=1, max_fields=3)
        except Exception:
            return y.yonlendir(adres, "Yedek dosyası okunamadı.", hata=True)
        try:
            dosya = form.get("dosya")
            parola = str(form.get("parola", ""))
            veri = await dosya.read(yedek.DOSYA_EN_BUYUK + 1) if isinstance(dosya, UploadFile) else b""
        finally:
            await form.close()
        if not veri:
            return y.yonlendir(adres, "Yedek dosyası seçilmedi.", hata=True)
        if not parola:
            return y.yonlendir(adres, "Yedek parolasını yazın.", hata=True)
        try:
            onizleme = await run_in_threadpool(yedek.bekleyeni_hazirla, veri, parola, y.parmak_izi)
        except yedek.YedekHatasi as hata:
            if not isinstance(hata, yedek.YedekMesgul):
                geri_yukleme_hatalari[anahtar].append(time.time())
            with vt.islem() as b:
                vt.kayit_dus(b, kim, "Başarısız geri yükleme denemesi", str(hata), anahtar)
            return y.yonlendir(adres, str(hata), hata=True)
        with vt.islem() as b:
            vt.kayit_dus(
                b, kim, "Geri yükleme için yedek denetlendi",
                f"yedek tarihi {datetime.fromtimestamp(onizleme['yedek_olusturma'], ISTANBUL):%d.%m.%Y %H:%M} · "
                f"{onizleme['tahta_sayisi']} tahta", anahtar,
            )  # fmt: skip
        return y.yonlendir("/yedekler/geri-yukle/onay")

    @uygulama.get("/yedekler/geri-yukle/onay", response_class=HTMLResponse)
    async def geri_yukle_onay(istek: Request):
        red, k, kurulum = geri_yukleme_izni(istek)
        if red:
            return red
        bekleyen = yedek.bekleyen_oku()
        if not bekleyen:
            return y.yonlendir(geri_adresi(kurulum), "Bekleyen geri yükleme yok.")
        return y.sayfa(
            istek,
            "yedek_onay.html",
            k,
            kurulum=kurulum,
            onizleme=bekleyen,
            simdiki_parmak_izi=y.parmak_izi,
            sertifika_farkli=bool(y.parmak_izi) and bekleyen.get("parmak_izi") != y.parmak_izi,
            hizmet=ayar.HIZMET,
        )

    @uygulama.post("/yedekler/geri-yukle/uygula")
    async def geri_yukle_uygula(istek: Request):
        red, k, kurulum = geri_yukleme_izni(istek)
        if red:
            return red
        kim = k["ad"] if k else "?"
        form = await istek.form()
        eylem = str(form.get("eylem", ""))
        if eylem == "vazgec":
            yedek.bekleyeni_sil()
            with vt.islem() as b:
                vt.kayit_dus(b, kim, "Geri yükleme vazgeçildi", "", ip(istek))
            return y.yonlendir(geri_adresi(kurulum), "Geri yüklemeden vazgeçildi; bekleyen dosyalar silindi.")
        if eylem != "uygula":
            return y.yonlendir("/yedekler/geri-yukle/onay", "Bilinmeyen işlem.", hata=True)
        bekleyen = yedek.bekleyeni_onayla()
        if not bekleyen:
            return y.yonlendir(geri_adresi(kurulum), "Bekleyen geri yükleme yok.", hata=True)
        with vt.islem() as b:
            vt.kayit_dus(
                b, kim, "Geri yükleme onaylandı",
                f"yedek tarihi {datetime.fromtimestamp(int(bekleyen['yedek_olusturma']), ISTANBUL):%d.%m.%Y %H:%M}; "
                "program yeniden açılınca uygulanır", ip(istek),
            )  # fmt: skip
        if ayar.HIZMET:
            # Hizmet kipi: süreç 2 sn sonra 75 koduyla çıkar, hizmet yöneticisi yeniden başlatır.
            from . import hizmet

            hizmet.yeniden_baslat_planla()
            return y.yonlendir(
                "/yedekler/geri-yukle/onay",
                "Geri yükleme onaylandı. Sunucu hizmeti birkaç saniye içinde yeniden başlıyor; "
                "yedek açılışta yerleştirilir. Yarım dakika sonra sayfayı yenileyip yeniden giriş yapın.",
            )
        # Oturum programı (geliştirme) kendini yeniden başlatmaz.
        return y.yonlendir(
            "/yedekler/geri-yukle/onay",
            "Geri yükleme onaylandı. Tahta Kontrol programını kapatıp yeniden açın; yedek açılışta yerleştirilir.",
        )

    # ---- envanter -------------------------------------------------------------------
    @uygulama.get("/envanter", response_class=HTMLResponse)
    async def envanter_sayfasi(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        with vt.islem() as b:
            satirlar = envanter.tablo(b)
        return y.sayfa(
            istek, "envanter.html", k, satirlar=satirlar,
            eksik_sayisi=sum(1 for s in satirlar if not s["env"]),
            guncellenmeli_sayisi=sum(1 for s in satirlar if s["eksik_neden"] == "Ajan güncellenmeli"),
        )  # fmt: skip

    @uygulama.get("/envanter.csv")
    async def envanter_csv(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        with vt.islem() as b:
            veri = envanter.csv_uret(b, y.tarih_yaz)
            vt.kayit_dus(b, k["ad"], "Envanter dışa aktarıldı", "", ip(istek))
        ad = f"tahta-envanteri-{datetime.fromtimestamp(vt.simdi(), ISTANBUL):%Y-%m-%d}.csv"
        return Response(veri, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="{ad}"'})  # fmt: skip

    @uygulama.post("/tahta/{tahta_id}/envanter")
    async def envanter_bilgisi(istek: Request, tahta_id: int):
        k = y.kullanici(istek)
        if not yonetici_mi(k):
            return y.yetkisiz_reddet(istek, k, f"Tahta #{tahta_id} demirbaş bilgisi")
        adres = f"/tahta/{tahta_id}#envanter"
        form = await istek.form()
        demirbas = ariza.temizle(form.get("demirbas_no", ""))
        notu = ariza.temizle(form.get("envanter_notu", ""))
        if len(str(form.get("demirbas_no", "")).strip()) > envanter.DEMIRBAS_EN_UZUN:
            return y.yonlendir(adres, f"Demirbaş numarası en çok {envanter.DEMIRBAS_EN_UZUN} karakter olabilir.", hata=True)
        if len(str(form.get("envanter_notu", "")).strip()) > envanter.NOT_EN_UZUN:
            return y.yonlendir(adres, f"Not en çok {envanter.NOT_EN_UZUN} karakter olabilir.", hata=True)
        with vt.islem() as b:
            if guvenlik.tc_kimlik_var(notu) or guvenlik.tc_kimlik_var(demirbas):
                vt.kayit_dus(b, k["ad"], "Envanter notu reddedildi", "T.C. kimlik numarasına benzeyen sayı", ip(istek))
                return y.yonlendir(adres, guvenlik.TC_KIMLIK_ILETISI, hata=True)
            satir = b.execute("SELECT ad FROM tahta WHERE id = ? AND durum != 'iptal'", (tahta_id,)).fetchone()
            if not satir:
                return y.yonlendir("/", "Tahta bulunamadı.", hata=True)
            b.execute("UPDATE tahta SET demirbas_no = ?, envanter_notu = ? WHERE id = ?",
                      (demirbas[: envanter.DEMIRBAS_EN_UZUN], notu, tahta_id))  # fmt: skip
            vt.kayit_dus(b, k["ad"], "Tahta demirbaş bilgisi kaydedildi", f"{satir['ad']} · {demirbas or 'demirbaş no yok'}", ip(istek))
        return y.yonlendir(adres, "Demirbaş bilgisi kaydedildi.")

    @uygulama.post("/tahta/{tahta_id}/donanim-goruldu")
    async def donanim_goruldu(istek: Request, tahta_id: int):
        k = y.kullanici(istek)
        if not yonetici_mi(k):
            return y.yetkisiz_reddet(istek, k, f"Tahta #{tahta_id} donanım uyarısı")
        with vt.islem() as b:
            satir = b.execute("SELECT ad FROM tahta WHERE id = ?", (tahta_id,)).fetchone()
            if satir and envanter.donanim_uyarisi_kaldir(b, tahta_id):
                vt.kayit_dus(b, k["ad"], "Donanım değişikliği görüldü", satir["ad"], ip(istek))
        return y.yonlendir(f"/tahta/{tahta_id}#envanter", "Donanım uyarısı kapatıldı.")

    # ---- arızalar -------------------------------------------------------------------
    def tahta_secenekleri(b) -> list[dict]:
        return [
            {"id": t["id"], "ad": t["ad"], "derslik": t["derslik"]}
            for t in b.execute("SELECT id, ad, derslik FROM tahta WHERE durum = 'onayli' ORDER BY derslik COLLATE NOCASE, ad COLLATE NOCASE")
        ]

    @uygulama.get("/arizalar", response_class=HTMLResponse)
    async def arizalar_sayfasi(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        durum = istek.query_params.get("durum", "")
        durum = durum if durum in (*ariza.ARIZA_DURUM, "hepsi") else ""
        tahta_q = istek.query_params.get("tahta", "")
        tahta_id = int(tahta_q) if tahta_q.isdigit() and len(tahta_q) < 10 else None
        with vt.islem() as b:
            liste = ariza.listele(b, durum, tahta_id)
            sayilar = ariza.durum_sayilari(b)
            tahtalar = tahta_secenekleri(b)
            suzulen = b.execute("SELECT id, ad FROM tahta WHERE id = ?", (tahta_id,)).fetchone() if tahta_id else None
        return y.sayfa(
            istek, "arizalar.html", k, arizalar=liste, durum_sayilari=sayilar,
            suren_sayisi=sayilar["acik"] + sayilar["inceleniyor"], secili_durum=durum,
            tahta_suzgeci=dict(suzulen) if suzulen else None, tahtalar=tahtalar,
            kategoriler=ariza.ARIZA_KATEGORI, durumlar=ariza.ARIZA_DURUM,
        )  # fmt: skip

    @uygulama.post("/arizalar")
    async def ariza_ac(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        donus = str(form.get("donus", "/arizalar"))
        donus = donus if donus.startswith("/") and not donus.startswith("//") else "/arizalar"
        tahta_q = str(form.get("tahta_id", ""))
        if not (tahta_q.isdigit() and len(tahta_q) < 10):
            return y.yonlendir(donus, "Tahtayı seçin.", hata=True)
        if len(str(form.get("aciklama", "")).strip()) > ariza.METIN_EN_UZUN:
            return y.yonlendir(donus, f"Açıklama en çok {ariza.METIN_EN_UZUN} karakter olabilir.", hata=True)
        try:
            with vt.islem() as b:
                yeni = ariza.panelden_ac(b, int(tahta_q), str(form.get("kategori", "")), str(form.get("aciklama", "")),
                                         k["ad"], ip(istek))  # fmt: skip
        except ValueError as hata:
            if str(hata) == guvenlik.TC_KIMLIK_ILETISI:  # numaranın kendisi kayda yazılmaz
                with vt.islem() as b:
                    vt.kayit_dus(b, k["ad"], "Arıza kaydı reddedildi", "T.C. kimlik numarasına benzeyen sayı", ip(istek))
            return y.yonlendir(donus, str(hata), hata=True)
        return y.yonlendir(f"/ariza/{yeni}", f"Arıza kaydı açıldı (#{yeni}).")

    def ariza_ciz(istek: Request, k, ariza_id: int, hata: str = "", durum_kodu: int = 200, form=None):
        """Ayrıntı sayfası. `form` (reddedilen gönderim) verilirse yazılan not, çözüm notu ve seçilen
        durum geri basılır; kullanıcı yazdığını kaybetmez (veritabanına yazılmamıştır)."""
        with vt.islem() as b:
            sonuc = ariza.ayrinti(b, ariza_id)
        if not sonuc:
            return y.yonlendir("/arizalar", "Arıza kaydı bulunamadı.", hata=True)
        kayit_, hareketler = sonuc
        ek = {"mesaj": hata, "mesaj_hata": True} if hata else {}
        girilen = None
        if form is not None:
            cozum = form.get("cozum_notu")
            girilen = {
                "durum": str(form.get("durum", "")),
                "not_metni": str(form.get("not_metni", ""))[:1000],
                "cozum_notu": str(cozum)[:1000] if cozum is not None else None,
            }
        return y.sayfa(istek, "ariza.html", k, durum_kodu=durum_kodu, ariza=kayit_, hareketler=hareketler,
                       durumlar=ariza.ARIZA_DURUM, girilen=girilen, **ek)  # fmt: skip

    @uygulama.get("/ariza/{ariza_id}", response_class=HTMLResponse)
    async def ariza_sayfasi(istek: Request, ariza_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        return ariza_ciz(istek, k, ariza_id)

    @uygulama.post("/ariza/{ariza_id}")
    async def ariza_guncelle(istek: Request, ariza_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        for alan in ("not_metni", "cozum_notu"):
            if len(str(form.get(alan, "")).strip()) > ariza.METIN_EN_UZUN:
                return ariza_ciz(istek, k, ariza_id, f"Not en çok {ariza.METIN_EN_UZUN} karakter olabilir.", 400, form)
        cozum = form.get("cozum_notu")
        try:
            with vt.islem() as b:
                mesaj = ariza.guncelle(
                    b, ariza_id, k["ad"], str(form.get("durum", "")), str(form.get("not_metni", "")),
                    str(cozum) if cozum is not None else None, ip(istek),
                )  # fmt: skip
        except LookupError as hata:
            return y.yonlendir("/arizalar", str(hata), hata=True)
        except ValueError as hata:
            if str(hata) == guvenlik.TC_KIMLIK_ILETISI:
                with vt.islem() as b:
                    vt.kayit_dus(b, k["ad"], "Arıza notu reddedildi", f"#{ariza_id} · T.C. kimlik numarasına benzeyen sayı", ip(istek))
            return ariza_ciz(istek, k, ariza_id, str(hata), 400, form)
        return y.yonlendir(f"/ariza/{ariza_id}", mesaj)
