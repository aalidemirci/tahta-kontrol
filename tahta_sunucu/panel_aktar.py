"""Panel: ders programını içe aktarma sihirbazı ve önceki programlar (0.10.0).

Yalnız yönetici (derslik programını yalnız yönetici değiştirir; idarecinin denemesi işlem kaydına düşer).
Yüklenen dosya diske yazılmaz (`bellekte_form`), saklanmaz; önizlemede yalnız SHA-256 özeti, ara biçim (sınıf,
derslik, gün, ders saati) ve eşleme seçimleri durur (`ayar.program_onizleme`, tur='aktar', 30 dk, kullanıcıya
bağlı belirteç). Öğretmen ve ders adı hiçbir aşamada okunmaz. İşlem kaydına yalnız biçim ve sayılar yazılır.

Şablon sözleşmesi: `aktar_baglami` belgesi (program_aktar.html) ve `gecmis` (program_gecmis.html).
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from starlette.datastructures import UploadFile

from . import program, program_aktar, program_is, vt
from .panel_program import bellekte_form, govde_uzunlugu, onizleme_al, onizleme_yaz, simdi_dt, yetki_reddi

KVKK_BANDI = (
    "Programı dış bir yapay zekâ hizmetine verirken öğretmen adlarını silin ya da kurumunuzun izin verdiği aracı "
    "kullanın. Öğrenci bilgisi içeren hiçbir dosyayı vermeyin. Tahta Kontrol bu işlem için internete bağlanmaz; "
    "yalnız sizin yapıştırdığınız sonucu okur."
)
YZ_ADIMLARI = [
    "İstemi kopyalayın.",
    "Yapay zekâ aracına istemi yapıştırın ve ders programınızı (Excel, PDF ya da fotoğraf) ekleyin.",
    "Çıkan CSV'yi aşağıya yapıştırın ya da .csv olarak kaydedip yükleyin.",
    "Önizlemeyi mutlaka kontrol edin; yapay zekâ hata yapabilir.",
]
YZ_ONIZLEME_BANDI = "Bu program bir yapay zekâ aracından geldi. Şube ve ders sayılarını asıl programla karşılaştırın."
ASC_METNI = (
    "aSc Timetables'ta programınızı açın. Dosya › Dışa Aktar › aSc TimeTables XML (sürümünüzde \"aSc Timetables 2012 "
    "XML\" diye görünebilir) ile bir .xml dosyası kaydedin ve buraya yükleyin. Dosyadaki öğretmen ve ders adları okunmaz "
    "ve saklanmaz; yalnız sınıf, derslik, gün ve ders saati alınır. aSc'nin kayıtsız (ücretsiz deneme) sürümü en çok 10 ders "
    "dışa aktarır; o durumda program eksik görünür."
)
ASC_DENEME_NOTU = "Bu yol henüz sınanıyor; ilk kullanımda önizlemeyi dikkatle kontrol edin."
TABLO_TARIFI = (
    "Yapıştırdığınız metinde kod bloğu işaretleri (```) ya da metnin başında/sonunda açıklama cümlesi varsa Tahta "
    "Kontrol onları atar; sube;gun;ders sütunlarını içeren ilk satır başlık sayılır."
)
ASC_GOVDE_PAYI = 256 * 1024


def kaydet(uygulama, y) -> None:
    def yetkisiz(istek: Request, k, islem: str, donus: str = "/program?bolum=derslik"):
        return yetki_reddi(y, istek, k, islem, donus)

    def onizleme_guncelle(b, kayit: dict, veri: dict) -> None:
        vt.ayar_yaz(b, "program_onizleme", {**kayit, "veri": veri})

    def aktar_baglami(b, k, adim: str) -> dict:
        """program_aktar.html bağlamı (`aktar`):

        {"adim": "kaynak"|"esleme"|"onizleme", "ders_saati_var", "istem", "sablon_basliklari", "kvkk_bandi",
        "yz_adimlari", "asc_metni", "asc_deneme_notu", "tablo_tarifi", "sinirlar": {asc_mb, tablo_mb, yz_kb},
        "onizleme": None | {"kimlik", "kaynak": "asc"|"tablo", "bicim", "bicim_adi", "ozet": {sha256, satir_sayisi,
        kart_sayisi}, "ozet_metni", "hatalar", "hata_sayisi", "uyarilar", "cok_hata", "onaylanabilir",
        "eslesme": {"derslik"|"sinif"|"saat"|"sube": [{"anahtar","ad","durum": hatirlanan|otomatik|secildi|eslesmedi,
        "deger", ("bas","bit" saat için)}]}, "donemler": [(konum, ad)], "secili_donem", "devre_sorusu",
        "devre_secenekleri": [(devre, ad)], "devre_secimi", "saat_secenekleri": [{"deger","ad"}],
        "tahta_secenekleri": [(id, ad)], "tahtalar": fark.tahtalar, "toplam": fark.toplam,
        "dokunulmayan_programli": [{"id","ad","derslik","devreler"}], "dersliksiz": [..], "dersliksiz_sayi",
        "sube_sayilari": [(şube, saat)], "yz_bandi", "esleme_gerekli"}}.
        Eşleme formu alan adları: d_<n> (derslik → tahta id | "" atla), s_<n> (sınıf → şube | "" şubesiz),
        p_<n> (aSc ders saati → "devre|no" | "yok"), t_<n> (şube → tahta id | ""), donem, devre_secimi;
        n = ilgili listedeki sıra (0'dan).
        """
        saatler = program.ders_saatleri_oku(b)
        baglam = {
            "adim": adim,
            "ders_saati_var": bool(saatler),
            "istem": program_aktar.istem_metni(saatler) if saatler else "",
            "sablon_basliklari": program_aktar.SABLON_BASLIK,
            "kvkk_bandi": KVKK_BANDI,
            "yz_adimlari": YZ_ADIMLARI,
            "asc_metni": ASC_METNI,
            "asc_deneme_notu": ASC_DENEME_NOTU,
            "tablo_tarifi": TABLO_TARIFI,
            "sinirlar": {"asc_mb": program_aktar.ASC_EN_COK_BAYT // (1024 * 1024),
                         "tablo_mb": program_aktar.TABLO_EN_COK_BAYT // (1024 * 1024),
                         "yz_kb": program_aktar.YZ_METIN_EN_COK // 1024},  # fmt: skip
            "onizleme": None,
        }
        kayit = vt.ayar_al(b, "program_onizleme")
        if (isinstance(kayit, dict) and kayit.get("tur") == "aktar" and kayit.get("kullanici") == k["ad"]
                and int(kayit.get("bitis") or 0) > vt.simdi() and saatler):  # fmt: skip
            veri = kayit["veri"]
            sonuc = program_aktar.coz(b, veri)
            baglam["onizleme"] = {
                "kimlik": kayit["kimlik"],
                "kaynak": veri["kaynak"],
                "bicim": veri["bicim"],
                "bicim_adi": program_aktar.BICIM_ADI.get(veri["bicim"], veri["bicim"]),
                "ozet": veri["ozet"],
                "ozet_metni": sonuc["ozet_metni"],
                "hatalar": sonuc["hatalar"],
                "hata_sayisi": sonuc["hata_sayisi"],
                "uyarilar": sonuc["uyarilar"],
                "cok_hata": sonuc["cok_hata"],
                "onaylanabilir": sonuc["onaylanabilir"],
                "eslesme": sonuc["cozum"]["eslesme"],
                "donemler": sonuc["donemler"],
                "secili_donem": sonuc["secili_donem"],
                "devre_sorusu": sonuc["devre_sorusu"],
                "devre_secenekleri": sonuc["devre_secenekleri"],
                "devre_secimi": (veri.get("secimler") or {}).get("devre_secimi", ""),
                "saat_secenekleri": sonuc["saat_secenekleri"],
                "tahta_secenekleri": sonuc["tahta_secenekleri"],
                "tahtalar": sonuc["fark"]["tahtalar"],
                "toplam": sonuc["fark"]["toplam"],
                "dokunulmayan_programli": sonuc["fark"]["dokunulmayan_programli"],
                "dersliksiz": sonuc["cozum"]["dersliksiz"],
                "dersliksiz_sayi": sonuc["cozum"]["dersliksiz_sayi"],
                "sube_sayilari": sonuc["sube_sayilari"],
                "yz_bandi": YZ_ONIZLEME_BANDI if veri["bicim"] in ("yz", "yz_dosya") else "",
                "esleme_gerekli": sonuc["esleme_gerekli"],
                "asc_deneme": veri["kaynak"] == "asc",
            }
            if adim == "kaynak":
                baglam["adim"] = "esleme" if sonuc["esleme_gerekli"] else "onizleme"
        elif adim != "kaynak":
            baglam["adim"] = "kaynak"
        return baglam

    def onizle_ve_yonlendir(istek, k, kaynak: str, bicim: str, bayt_ozeti: str, okunan: dict, asc=None):
        try:
            veri = program_aktar.onizleme_verisi(kaynak, bicim, bayt_ozeti, okunan, asc)
        except ValueError as hata:
            return y.yonlendir("/program/aktar", str(hata), hata=True)
        with vt.islem() as b:
            onizleme_yaz(b, "aktar", veri, k)
            sonuc = program_aktar.coz(b, veri)
            eslesme = sonuc["cozum"]["eslesme"]["derslik"]
            vt.kayit_dus(
                b, k["ad"], "Ders programı önizlendi",
                f"{program_aktar.BICIM_ADI.get(bicim, bicim)} · "
                + (f"{okunan.get('kart_sayisi')} kart" if kaynak == "asc" else f"{okunan.get('satir_sayisi')} satır")
                + f" · {sum(1 for e in eslesme if e['durum'] != 'eslesmedi')} derslik eşleşti, "
                f"{sum(1 for e in eslesme if e['durum'] == 'eslesmedi')} eşleşmedi · {sonuc['hata_sayisi']} hatalı satır",
                y.istemci_ip(istek),
            )  # fmt: skip
        return y.yonlendir("/program/aktar?adim=" + ("esleme" if sonuc["esleme_gerekli"] else "onizleme"))

    # ---- sihirbaz sayfası --------------------------------------------------------------------------------
    @uygulama.get("/program/aktar", response_class=HTMLResponse)
    async def aktar_sayfasi(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Ders programı içe aktarma sayfası")
        if engel:
            return engel
        adim = istek.query_params.get("adim", "kaynak")
        adim = adim if adim in ("kaynak", "esleme", "onizleme") else "kaynak"
        with vt.islem() as b:
            baglam = aktar_baglami(b, k, adim)
            if istek.query_params.get("yeni") == "1":  # "Başka bir dosya yükle": önizleme dursa da kaynak adımı
                baglam["adim"] = "kaynak"
            serit = program_is.program_ozeti(b, simdi_dt())
        return y.sayfa(istek, "program_aktar.html", k, aktar=baglam, serit=serit, bolum="derslik", yonetici=True)

    # ---- kaynak: aSc XML ------------------------------------------------------------------------------------
    @uygulama.post("/program/aktar/asc")
    async def aktar_asc(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Ders programı aSc yükleme")
        if engel:
            return engel
        donus = "/program/aktar"
        uzunluk = govde_uzunlugu(istek)
        if uzunluk is None:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        if uzunluk > program_aktar.ASC_EN_COK_BAYT + ASC_GOVDE_PAYI:
            return y.yonlendir(donus, f"Dosya en çok {program_aktar.ASC_EN_COK_BAYT // (1024 * 1024)} MB olabilir.", hata=True)
        try:
            form = await bellekte_form(istek, program_aktar.ASC_EN_COK_BAYT + ASC_GOVDE_PAYI)
        except Exception:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        try:
            dosya = form.get("dosya")
            if not isinstance(dosya, UploadFile) or not dosya.filename:
                return y.yonlendir(donus, "aSc XML dosyası seçilmedi.", hata=True)
            bayt = await dosya.read(program_aktar.ASC_EN_COK_BAYT + 1)
        finally:
            await form.close()
        with vt.islem() as b:
            if not program.ders_saatleri_oku(b):
                return y.yonlendir(donus, program_aktar.ZIL_YOK, hata=True)
        try:
            asc = program_aktar.asc_oku(bayt)
        except ValueError as hata:
            return y.yonlendir(donus, str(hata), hata=True)
        okunan = {"kart_sayisi": len(asc["cards"]), "satir_sayisi": None}
        return onizle_ve_yonlendir(istek, k, "asc", "asc", program_aktar.ozet(bayt), okunan, asc)

    # ---- kaynak: şablon (CSV/XLSX/XLS) ya da yapay zekâ çıktısı ----------------------------------------------
    @uygulama.post("/program/aktar/tablo")
    async def aktar_tablo(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Ders programı tablo yükleme")
        if engel:
            return engel
        donus = "/program/aktar"
        uzunluk = govde_uzunlugu(istek)
        if uzunluk is None:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        sinir = program_aktar.TABLO_EN_COK_BAYT + program_aktar.YZ_METIN_EN_COK + 64 * 1024
        if uzunluk > sinir:
            return y.yonlendir(donus, "Dosya en çok 1 MB, yapıştırılan metin en çok 512 KB olabilir.", hata=True)
        bayt = b""
        yapistirilan = ""
        try:
            if istek.headers.get("content-type", "").lower().startswith("multipart/form-data"):
                form = await bellekte_form(istek, sinir, max_fields=5)
            else:
                form = await istek.form(max_files=0, max_fields=5)
        except Exception:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        try:
            bicim_secimi = "yz" if form.get("bicim") == "yz" else "tablo"
            dosya = form.get("dosya")
            if isinstance(dosya, UploadFile) and dosya.filename:
                bayt = await dosya.read(program_aktar.TABLO_EN_COK_BAYT + 1)
            ham_metin = form.get("metin")
            if isinstance(ham_metin, str):
                yapistirilan = ham_metin
        finally:
            await form.close()
        uyarilar: list[str] = []
        try:
            if yapistirilan.strip():
                temiz, uyarilar = program_aktar.yz_metni_temizle(yapistirilan)
                kaynak_bayt = temiz.encode("utf-8")
                bicim, matris = program_aktar.tablo_matrisi(kaynak_bayt)
                bicim = "yz" if bicim_secimi == "yz" else "csv"
            elif bayt:
                kaynak_bayt = bayt
                bicim, matris = program_aktar.tablo_matrisi(bayt)
                if bicim_secimi == "yz":
                    bicim = "yz_dosya"
            else:
                return y.yonlendir(donus, "Dosya seçin ya da metni yapıştırın.", hata=True)
            with vt.islem() as b:
                okunan = program_aktar.tablo_oku(matris, program.ders_saatleri_oku(b))
        except ValueError as hata:
            if str(hata) == program_aktar.TC_RET:
                with vt.islem() as b:
                    vt.kayit_dus(b, k["ad"], "Ders programı reddedildi", "T.C. kimlik numarasına benzeyen değer",
                                 y.istemci_ip(istek))  # fmt: skip
            elif yapistirilan.strip():
                # Yapıştırılan metin kaybolmasın: yönlendirmeden yeniden çiz (422), hata yapay zekâ kartında.
                # (Kimlik numarasına benzeyen değer içeren metin geri yazılmaz; yukarıdaki dal.)
                with vt.islem() as b:
                    baglam = aktar_baglami(b, k, "kaynak")
                    baglam["adim"] = "kaynak"
                    baglam["yz_metin"] = yapistirilan
                    baglam["yz_hata"] = str(hata)
                    serit = program_is.program_ozeti(b, simdi_dt())
                return y.sayfa(istek, "program_aktar.html", k, durum_kodu=422, aktar=baglam, serit=serit,
                               bolum="derslik", yonetici=True)  # fmt: skip
            return y.yonlendir(donus, str(hata), hata=True)
        okunan["uyarilar"] = uyarilar + okunan["uyarilar"]
        return onizle_ve_yonlendir(istek, k, "tablo", bicim, program_aktar.ozet(kaynak_bayt), okunan)

    # ---- eşleme ------------------------------------------------------------------------------------------------
    @uygulama.post("/program/aktar/esle")
    async def aktar_esle(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Ders programı eşleme")
        if engel:
            return engel
        form = await istek.form(max_files=0, max_fields=4 * program_aktar.ESLEME_EN_COK + 10)
        with vt.islem() as b:
            kayit = onizleme_al(b, "aktar", str(form.get("onizleme", "")), k)
            if not kayit:
                return y.yonlendir("/program/aktar", "Önizlemenin süresi geçmiş ya da başka bir kullanıcıya ait. Dosyayı yeniden yükleyin.", hata=True)
            veri = kayit["veri"]
            sonuc = program_aktar.coz(b, veri)
            secimler = veri.setdefault("secimler", {})
            degisen = 0
            for onek, tur in (("d", "derslik"), ("s", "sinif"), ("p", "saat"), ("t", "sube")):
                for n, e in enumerate(sonuc["cozum"]["eslesme"][tur]):
                    gelen = form.get(f"{onek}_{n}")
                    if gelen is None:
                        continue
                    gelen = str(gelen).strip()[:40]
                    if gelen == str(e["deger"] or "") and e["durum"] != "secildi":
                        continue
                    secimler.setdefault(tur, {})[e["anahtar"]] = gelen
                    degisen += 1
            for alan in ("donem", "devre_secimi"):
                if form.get(alan) is not None and str(form.get(alan)) != str(secimler.get(alan, "")):
                    secimler[alan] = str(form.get(alan))[:40]
                    degisen += 1
            onizleme_guncelle(b, kayit, veri)
            if degisen:
                vt.kayit_dus(b, k["ad"], "Ders programı eşlemesi değişti", f"{degisen} eşleme", y.istemci_ip(istek))
        return y.yonlendir("/program/aktar?adim=onizleme")

    # ---- onay ----------------------------------------------------------------------------------------------------
    @uygulama.post("/program/aktar/onayla")
    async def aktar_onayla(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Ders programı onaylama")
        if engel:
            return engel
        form = await istek.form(max_files=0, max_fields=5000)
        with vt.islem() as b:
            kayit = onizleme_al(b, "aktar", str(form.get("onizleme", "")), k)
            if form.get("eylem") == "vazgec":
                if kayit:
                    vt.ayar_yaz(b, "program_onizleme", None)
                return y.yonlendir("/program?bolum=derslik", "Önizleme kapatıldı; derslik programları değişmedi.")
            if not kayit:
                return y.yonlendir("/program/aktar", "Önizlemenin süresi geçmiş ya da başka bir kullanıcıya ait. Dosyayı yeniden yükleyin.", hata=True)
            veri = kayit["veri"]
            sonuc = program_aktar.coz(b, veri)
            if not sonuc["onaylanabilir"]:
                return y.yonlendir("/program/aktar?adim=onizleme", "Değişecek tahta yok; eşlemeyi kontrol edin.", hata=True)
            if sonuc["cok_hata"] and form.get("onay_hatali") != "1":
                return y.yonlendir("/program/aktar?adim=onizleme",
                                   "Satırların çoğu okunamadı; dosyayı kontrol edin ya da onay kutusunu işaretleyin.", hata=True)  # fmt: skip
            izinli = {t["id"] for t in sonuc["fark"]["dokunulmayan_programli"]}
            temizle = [int(t) for t in form.getlist("temizle_tahta") if str(t).isdigit() and int(t) in izinli]
            kaynak = "asc" if veri["kaynak"] == "asc" else "tablo"
            sonuc_ = program_aktar.uygula(b, sonuc["cozum"], k["ad"], veri["bicim"], kaynak, temizle)
            vt.ayar_yaz(b, "program_onizleme", None)
            t = sonuc["fark"]["toplam"]
            vt.kayit_dus(
                b, k["ad"], "Ders programı içe aktarıldı",
                f"{program_aktar.BICIM_ADI.get(veri['bicim'], veri['bicim'])} · {t['tahta']} tahta · +{t['eklenen']} "
                f"−{t['silinen']} ~{t['degisen']} · {sonuc['hata_sayisi']} hatalı satır atlandı"
                + (f" · {len(temizle)} tahtanın devre programı temizlendi" if temizle else ""),
                y.istemci_ip(istek),
            )  # fmt: skip
        ileti = f"{sonuc_['tahta']} tahtanın programı güncellendi. Önceki program “Önceki programlar” listesinden geri yüklenebilir."
        return y.yonlendir("/program?bolum=derslik", ileti)

    # ---- indirmeler ------------------------------------------------------------------------------------------------
    @uygulama.get("/program/aktar/sablon.csv")
    async def aktar_sablon(istek: Request):
        if not y.kullanici(istek):
            return y.yonlendir("/giris")
        with vt.islem() as b:
            icerik = program_aktar.sablon_csv(program.ders_saatleri_oku(b))
        return Response(icerik, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="ders-programi-sablon.csv"'})  # fmt: skip

    @uygulama.get("/program/aktar/mevcut.csv")
    async def aktar_mevcut(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Mevcut ders programı indirme")
        if engel:
            return engel
        with vt.islem() as b:
            icerik = program_aktar.mevcut_csv(b)
            satir = b.execute("SELECT COUNT(*) FROM tahta_ders").fetchone()[0]
            vt.kayit_dus(b, k["ad"], "Mevcut ders programı indirildi", f"{satir} satır", y.istemci_ip(istek))
        return Response(icerik, media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="ders-programi-mevcut.csv"'})  # fmt: skip

    @uygulama.get("/program/aktar/istem.txt")
    async def aktar_istem(istek: Request):
        if not y.kullanici(istek):
            return y.yonlendir("/giris")
        with vt.islem() as b:
            saatler = program.ders_saatleri_oku(b)
        if not saatler:
            return y.yonlendir("/program/aktar", program_aktar.ZIL_YOK, hata=True)
        return Response(program_aktar.istem_metni(saatler).encode("utf-8"), media_type="text/plain; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="ders-programi-istem.txt"'})  # fmt: skip

    # ---- önceki programlar ------------------------------------------------------------------------------------------
    @uygulama.get("/program/gecmis", response_class=HTMLResponse)
    async def gecmis(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Önceki ders programları")
        if engel:
            return engel
        with vt.islem() as b:
            liste = program_aktar.surum_listesi(b)
        return y.sayfa(istek, "program_gecmis.html", k, gecmis=liste, onay_surumu=None, bolum="derslik")

    @uygulama.post("/program/gecmis/{surum_id}/geri-yukle")
    async def geri_yukle(istek: Request, surum_id: int):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, f"Ders programı geri yükleme #{surum_id}")
        if engel:
            return engel
        form = await istek.form(max_files=0, max_fields=5)
        with vt.islem() as b:
            liste = program_aktar.surum_listesi(b)
            surum = next((s for s in liste if s["id"] == surum_id), None)
            if not surum:
                return y.yonlendir("/program?bolum=derslik", "Sürüm bulunamadı.", hata=True)
            if form.get("onay") != "1":
                onay = {**surum, "metin": f"Bu işlem bütün derslik programını {surum['zaman_metni']} tarihli sürüme döndürür."}
                return y.sayfa(istek, "program_gecmis.html", k, gecmis=liste, onay_surumu=onay, bolum="derslik")
            sonuc = program_aktar.geri_yukle(b, surum_id, k["ad"])
            if sonuc is None:
                return y.yonlendir("/program?bolum=derslik", "Sürüm okunamadı.", hata=True)
            vt.kayit_dus(b, k["ad"], "Ders programı geri yüklendi", f"sürüm #{surum_id} · {sonuc['satir']} satır",
                         y.istemci_ip(istek))  # fmt: skip
        return y.yonlendir("/program?bolum=derslik",
                           f"Derslik programı {surum['zaman_metni']} tarihli sürüme döndürüldü ({sonuc['satir']} satır).")  # fmt: skip
