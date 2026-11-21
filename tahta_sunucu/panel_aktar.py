"""Panel: ders programını içe aktarma sihirbazı ve önceki programlar (0.10.0; 0.12.0: e-Okul raporu kaynağı).

Yalnız yönetici (derslik programını yalnız yönetici değiştirir; idarecinin denemesi işlem kaydına düşer).
Yüklenen dosya diske yazılmaz (`bellekte_form`), saklanmaz; önizlemede yalnız SHA-256 özeti, ara biçim (sınıf,
derslik, gün, ders saati) ve eşleme seçimleri durur (`ayar.program_onizleme`, tur='aktar', 30 dk, kullanıcıya
bağlı belirteç). Öğretmen ve ders adı hiçbir aşamada okunmaz; tek istisna e-Okul raporunda eşleme ipucu olarak
blok başına en çok üç ders adıdır (öğretmen adı asla; önizlemeyle birlikte silinir). İşlem kaydına yalnız biçim ve
sayılar yazılır.

Şablon sözleşmesi: `aktar_baglami` belgesi (program_aktar.html) ve `gecmis` (program_gecmis.html).
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from starlette.datastructures import UploadFile

from . import eokul_program, metin, program, program_aktar, program_is, vt
from .panel_cizelge import Etki, devre_sayilari
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
ASC_DENEME_NOTU = ("Bir okulun aSc Timetables 2012 dosyasıyla denendi. İkili eğitimde sabah ve öğle ders saatleri ayrı "
                   "devrelere yazılır; ilk kullanımda önizlemeyi kontrol edin.")  # fmt: skip
TABLO_TARIFI = (
    "Yapıştırdığınız metinde kod bloğu işaretleri (```) ya da metnin başında/sonunda açıklama cümlesi varsa Tahta "
    "Kontrol onları atar; sube;gun;ders sütunlarını içeren ilk satır başlık sayılır."
)
ASC_GOVDE_PAYI = 256 * 1024
EOKUL_ADIMLARI = [
    f"e-Okul'da rapor listesinden “{eokul_program.RAPOR_ADI}” raporunu açın; bütün şubeleri seçin.",
    "Raporu Excel olarak kaydedin (.XLS). Dosyayı açıp değiştirmeniz gerekmez.",
    "Aynı raporu PDF olarak da açın: şube adı yalnız PDF'te, her sayfanın başında (“9. Sınıf / A Şubesi”) yazar. "
    "Şube sırasını eşleme adımında oradan doğrulayacaksınız.",
    ".XLS dosyasını aşağıdan yükleyin.",
]
EOKUL_NOTU = (
    "Tahta Kontrol e-Okul'a bağlanmaz; yalnız yüklediğiniz dosyayı okur. Raporda şube adı ve derslik olmadığı için "
    "eşleme adımında her bloğun şubesini siz onaylarsınız; her şubenin dersi şubenin kendi tahtasına yazılır. "
    "Öğretmen adları okunmaz ve saklanmaz; eşleme ekranında blokları tanımanız için yalnız birkaç ders adı geçici "
    "olarak gösterilir."
)
EOKUL_GOVDE_PAYI = 64 * 1024


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
        "deger", ("bas","bit" saat için)}], "devre": [{"anahtar","ad","bas","bit","sayi","durum","deger",("tek")}]},
        "donemler": [(konum, ad)], "secili_donem", "devre_secenekleri": [(devre, ad)], "saat_secenekleri": [{"deger","ad"}],
        "tahta_secenekleri": [(id, "No <id> · ad · derslik")], "ayni_adli_tahta", "tahtalar": fark.tahtalar,
        "toplam": fark.toplam, "dokunulmayan_programli": [{"id","ad","derslik","devreler"}], "dersliksiz": [..],
        "dersliksiz_sayi", "sube_sayilari": [(şube, saat)], "yz_bandi", "esleme_gerekli", "asc_zil": None | {zil_onerisi,
        zil_gerekli, zil_onerilemez, zil_yalniz_fark}, "zil_etkisi", "sube_guncellemesi": [{"id","ad","eski_subeler",
        "subeler","eski_derslik","derslik"}], "hatirlanan_sayisi"}}.
        Eşleme formu alan adları: d_<n> (derslik → tahta id | "" atla), s_<n> (sınıf → şube | "" şubesiz),
        p_<n> (aSc ders saati → "devre|no" | "yok"), t_<n> (şube → tahta id | ""), g_<n> (aSc devre grubu → devre | "yok"
        | ""; 0.21.0, eski tek `devre_secimi`'nin yerine), donem; n = ilgili listedeki sıra (0'dan).
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
        baglam["eokul_adimlari"] = EOKUL_ADIMLARI
        baglam["eokul_notu"] = EOKUL_NOTU
        baglam["sinirlar"]["eokul_mb"] = eokul_program.EN_COK_BAYT // (1024 * 1024)
        if (isinstance(kayit, dict) and kayit.get("tur") == "aktar" and kayit.get("kullanici") == k["ad"]
                and int(kayit.get("bitis") or 0) > vt.simdi()
                and (saatler or (kayit.get("veri") or {}).get("kaynak") in ("eokul", "asc"))):  # fmt: skip
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
                "devre_secenekleri": sonuc["devre_secenekleri"],
                "saat_secenekleri": sonuc["saat_secenekleri"],
                "tahta_secenekleri": sonuc["tahta_secenekleri"],
                "ayni_adli_tahta": sonuc["ayni_adli_tahta"],
                "asc_zil": sonuc["asc_zil"],
                "sube_guncellemesi": sonuc["sube_guncellemesi"],
                "hatirlanan_sayisi": program_aktar.hatirlanan_sayisi(b, program_aktar.hatirlanan_kaynagi(veri)),
                "tahtalar": sonuc["fark"]["tahtalar"],
                "toplam": sonuc["fark"]["toplam"],
                "dokunulmayan_programli": sonuc["fark"]["dokunulmayan_programli"],
                "dersliksiz": sonuc["cozum"]["dersliksiz"],
                "dersliksiz_sayi": sonuc["cozum"]["dersliksiz_sayi"],
                "sube_sayilari": sonuc["sube_sayilari"],
                "yz_bandi": YZ_ONIZLEME_BANDI if veri["bicim"] in ("yz", "yz_dosya") else "",
                "esleme_gerekli": sonuc["esleme_gerekli"],
                "asc_deneme": veri["kaynak"] == "asc",
                "eokul": sonuc["eokul"],
                "sube_secenekleri": eokul_program.sistem_subeleri(b) if veri["kaynak"] == "eokul" else [],
                "sube_listesi": ", ".join((veri.get("secimler") or {}).get("sube_listesi") or []),
                "zil_etkisi": (eokul_program.zil_etkisi(b, sonuc["eokul"]["zil_onerisi"])
                               if sonuc["eokul"] and sonuc["eokul"]["zil_onerisi"] else
                               eokul_program.zil_etkisi(b, sonuc["asc_zil"]["zil_onerisi"])
                               if sonuc["asc_zil"] and sonuc["asc_zil"]["zil_onerisi"] else None),  # fmt: skip
            }
            if adim == "kaynak":
                baglam["adim"] = "esleme" if sonuc["esleme_gerekli"] else "onizleme"
        elif adim != "kaynak":
            baglam["adim"] = "kaynak"
        return baglam

    def onizle_ve_yonlendir(istek, k, kaynak: str, bicim: str, bayt_ozeti: str, okunan: dict, asc=None, veri=None):
        try:
            veri = veri or program_aktar.onizleme_verisi(kaynak, bicim, bayt_ozeti, okunan, asc)
        except ValueError as hata:
            return y.yonlendir("/program/aktar", str(hata), hata=True)
        with vt.islem() as b:
            onizleme_yaz(b, "aktar", veri, k)
            sonuc = program_aktar.coz(b, veri)
            eslesme = sonuc["cozum"]["eslesme"]["derslik"]
            if kaynak == "eokul":
                e = sonuc["eokul"]
                ayrinti = (f"{program_aktar.BICIM_ADI['eokul']} · {e['sayilar']['blok']} blok ("
                           + ", ".join(f"{ad} {n}" for ad, n in e["devre_dagilimi"])
                           + f") · {veri['eokul']['dolu_sayisi']} dolu, {veri['eokul']['bos_sayisi']} boş ders saati · "
                           f"{sonuc['hata_sayisi']} hatalı satır")  # fmt: skip
            else:
                ayrinti = (f"{program_aktar.BICIM_ADI.get(bicim, bicim)} · "
                           + (f"{okunan.get('kart_sayisi')} kart" if kaynak == "asc" else f"{okunan.get('satir_sayisi')} satır")
                           + f" · {sum(1 for e in eslesme if e['durum'] != 'eslesmedi')} derslik eşleşti, "
                           f"{sum(1 for e in eslesme if e['durum'] == 'eslesmedi')} eşleşmedi · {sonuc['hata_sayisi']} hatalı satır")  # fmt: skip
            vt.kayit_dus(b, k["ad"], "Ders programı önizlendi", ayrinti, y.istemci_ip(istek))
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
        return y.sayfa(istek, "program_aktar.html", k, aktar=baglam, serit=serit, bolum="aktar", yonetici=True)

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
        # 0.21.0: zil yoksa da okunur; eşleme adımında dosyadaki saatlerden zil çizelgesi önerilir (onaylı).
        try:
            asc = program_aktar.asc_oku(bayt)
        except ValueError as hata:
            return y.yonlendir(donus, str(hata), hata=True)
        if not program_aktar.asc_devre_gruplari(asc)["gruplar"]:
            with vt.islem() as b:
                zil_var = bool(program.ders_saatleri_oku(b))
            if not zil_var:  # dosyada saat yok, zil yok: eşleme adımında ilerlenemez (zil önerisi de çıkamaz)
                return y.yonlendir(donus, program_aktar.ASC_SAATSIZ, hata=True)
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
                               bolum="aktar", yonetici=True)  # fmt: skip
            return y.yonlendir(donus, str(hata), hata=True)
        okunan["uyarilar"] = uyarilar + okunan["uyarilar"]
        return onizle_ve_yonlendir(istek, k, "tablo", bicim, program_aktar.ozet(kaynak_bayt), okunan)

    # ---- kaynak: e-Okul "Haftalık Ders Programları" raporu (0.12.0) -----------------------------------------
    @uygulama.post("/program/aktar/eokul")
    async def aktar_eokul(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Ders programı e-Okul raporu yükleme")
        if engel:
            return engel
        donus = "/program/aktar"
        sinir = eokul_program.EN_COK_BAYT + EOKUL_GOVDE_PAYI
        uzunluk = govde_uzunlugu(istek)
        if uzunluk is None:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        if uzunluk > sinir:
            return y.yonlendir(donus, f"Dosya en çok {eokul_program.EN_COK_BAYT // (1024 * 1024)} MB olabilir.", hata=True)
        try:
            form = await bellekte_form(istek, sinir)  # dosya diske yazılmaz
        except Exception:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        try:
            dosya = form.get("dosya")
            if not isinstance(dosya, UploadFile) or not dosya.filename:
                return y.yonlendir(donus, "e-Okul raporu (.XLS) seçilmedi.", hata=True)
            bayt = await dosya.read(eokul_program.EN_COK_BAYT + 1)
        finally:
            await form.close()
        try:
            rapor = eokul_program.rapor_oku(eokul_program.matris_oku(bayt))
        except ValueError as hata:
            if str(hata) == eokul_program.TC_RET:
                with vt.islem() as b:
                    vt.kayit_dus(b, k["ad"], "Ders programı reddedildi", "e-Okul raporu · T.C. kimlik numarasına benzeyen değer",
                                 y.istemci_ip(istek))  # fmt: skip
            return y.yonlendir(donus, str(hata), hata=True)
        veri = eokul_program.onizleme_verisi(program_aktar.ozet(bayt), rapor)
        return onizle_ve_yonlendir(istek, k, "eokul", "eokul", veri["ozet"]["sha256"], {}, veri=veri)

    @uygulama.post("/program/aktar/eokul/zil")
    async def aktar_eokul_zil(istek: Request):
        """Rapordaki saatlerden zil çizelgesi oluşturur (yeni çizelge + haftalık düzende rapordaki günler)."""
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Zil çizelgesini e-Okul raporundan oluşturma")
        if engel:
            return engel
        form = await istek.form(max_files=0, max_fields=5)
        donus = "/program/aktar?adim=esleme"
        with vt.islem() as b:
            kayit = onizleme_al(b, "aktar", str(form.get("onizleme", "")), k)
            if not kayit or kayit["veri"].get("kaynak") != "eokul":
                return y.yonlendir("/program/aktar", "Önizlemenin süresi geçmiş ya da başka bir kullanıcıya ait. Dosyayı yeniden yükleyin.", hata=True)
            oneri = program_aktar.coz(b, kayit["veri"])["eokul"]["zil_onerisi"]
            if not oneri or oneri["hatalar"]:
                return y.yonlendir(donus, "Bu rapordan zil çizelgesi oluşturulamıyor; zil saatlerini elle girin.", hata=True)
            if form.get("onay") != "1":
                return y.yonlendir(donus, "Zil çizelgesi oluşturmak için onay kutusunu işaretleyin.", hata=True)
            etki = Etki(b)
            _kimlik, ad = eokul_program.zil_yaz(b, oneri, k["ad"])
            iletiler = etki.bitir(b, k)
            vt.kayit_dus(b, k["ad"], "Zil çizelgesi oluşturuldu",
                         f"{ad} · {devre_sayilari(oneri['dersler'])} · e-Okul raporundan · {oneri['gun_metni']}",
                         y.istemci_ip(istek))  # fmt: skip
        if etki.bugun_degisti:
            isleyici = getattr(uygulama.state, "program_isleyici", None)
            if isleyici is not None:
                isleyici.bugun_degisti()
        y.uyandir_hepsi(etki.uyandir)
        return y.yonlendir(donus, " ".join([f"“{ad}” zil çizelgesi oluşturuldu ve {oneri['gun_metni']} günlerine atandı.",
                                            *iletiler]))  # fmt: skip

    @uygulama.post("/program/aktar/asc/zil")
    async def aktar_asc_zil(istek: Request):
        """0.21.0: aSc dosyasındaki ders saatlerinden zil çizelgesi oluşturur (yeni çizelge + haftalık düzende dosyadaki
        günler); onay kutusu zorunludur."""
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Zil çizelgesini aSc dosyasından oluşturma")
        if engel:
            return engel
        form = await istek.form(max_files=0, max_fields=5)
        donus = "/program/aktar?adim=esleme"
        with vt.islem() as b:
            kayit = onizleme_al(b, "aktar", str(form.get("onizleme", "")), k)
            if not kayit or kayit["veri"].get("kaynak") != "asc":
                return y.yonlendir("/program/aktar", "Önizlemenin süresi geçmiş ya da başka bir kullanıcıya ait. Dosyayı yeniden yükleyin.", hata=True)
            asc_zil = program_aktar.coz(b, kayit["veri"])["asc_zil"] or {}
            oneri = asc_zil.get("zil_onerisi")
            if not oneri or oneri["hatalar"]:
                return y.yonlendir(donus, "Bu dosyadan zil çizelgesi oluşturulamıyor; zil saatlerini elle girin.", hata=True)
            if form.get("onay") != "1":
                return y.yonlendir(donus, "Zil çizelgesi oluşturmak için onay kutusunu işaretleyin.", hata=True)
            etki = Etki(b)
            _kimlik, ad = program_aktar.asc_zil_yaz(b, oneri, k["ad"])
            iletiler = etki.bitir(b, k)
            vt.kayit_dus(b, k["ad"], "Zil çizelgesi oluşturuldu",
                         f"{ad} · {devre_sayilari(oneri['dersler'])} · aSc dosyasından · {oneri['gun_metni']}",
                         y.istemci_ip(istek))  # fmt: skip
        if etki.bugun_degisti:
            isleyici = getattr(uygulama.state, "program_isleyici", None)
            if isleyici is not None:
                isleyici.bugun_degisti()
        y.uyandir_hepsi(etki.uyandir)
        return y.yonlendir(donus, " ".join([f"“{ad}” zil çizelgesi oluşturuldu ve {oneri['gun_metni']} günlerine atandı.",
                                            *iletiler]))  # fmt: skip

    @uygulama.post("/program/aktar/unut")
    async def aktar_unut(istek: Request):
        """0.21.0: önizlemedeki kaynağın (aSc, e-Okul ya da tablo) hatırlanan bütün eşleşmelerini siler; onay kutusu
        zorunludur. Bu oturumda eşleme ekranında yapılan seçimler durur. İşlem kaydına yalnız kaynak ve sayı."""
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Hatırlanan ders programı eşleşmelerini silme")
        if engel:
            return engel
        form = await istek.form(max_files=0, max_fields=5)
        donus = "/program/aktar?adim=esleme"
        with vt.islem() as b:
            kayit = onizleme_al(b, "aktar", str(form.get("onizleme", "")), k)
            if not kayit:
                return y.yonlendir("/program/aktar", "Önizlemenin süresi geçmiş ya da başka bir kullanıcıya ait. Dosyayı yeniden yükleyin.", hata=True)
            if form.get("onay") != "1":
                return y.yonlendir(donus, "Hatırlanan eşleşmeleri silmek için onay kutusunu işaretleyin.", hata=True)
            kaynak = program_aktar.hatirlanan_kaynagi(kayit["veri"])
            silinen = program_aktar.hatirlananlari_unut(b, kaynak)
            ad = {"asc": "aSc", "eokul": "e-Okul"}.get(kaynak, "CSV, Excel ve yapay zekâ")
            vt.kayit_dus(b, k["ad"], "Hatırlanan ders programı eşleşmeleri silindi", f"{ad} · {silinen} eşleşme",
                         y.istemci_ip(istek))  # fmt: skip
        return y.yonlendir(donus, f"Hatırlanan {silinen} eşleşme silindi; eşleme dosyadan ve tahta bilgilerinden yeniden önerildi.")

    # ---- eşleme ------------------------------------------------------------------------------------------------
    def eokul_esle(istek, k, b, kayit: dict, veri: dict, sonuc: dict, form):
        """e-Okul: yapıştırılan şube listesi (değiştiyse uygulanır, blok seçimleri sıfırlanır, eşlemeye dönülür) ve
        b_<blok no> alanları (şube; boş = atla). Yönlendirme gerekiyorsa yanıt, yoksa None (genel eşleme sürer)."""
        secimler = veri["secimler"]
        ham_liste = form.get("sube_listesi")
        if isinstance(ham_liste, str):
            try:
                liste, uyarilar = eokul_program.sube_listesi_coz(ham_liste)
            except ValueError as hata:
                return y.yonlendir("/program/aktar?adim=esleme", str(hata), hata=True)
            if liste != (secimler.get("sube_listesi") or []):
                secimler["sube_listesi"] = liste
                secimler["blok"] = {}
                onizleme_guncelle(b, kayit, veri)
                vt.kayit_dus(b, k["ad"], "Ders programı eşlemesi değişti", f"e-Okul şube listesi: {len(liste)} şube",
                             y.istemci_ip(istek))  # fmt: skip
                bloklar = len(veri["eokul"]["bloklar"])
                ileti = (f"Şube listesi uygulandı ({len(liste)} şube, {bloklar} blok). Blokları PDF'teki sırayla karşılaştırın."
                         if liste else "Şube listesi temizlendi.")  # fmt: skip
                return y.yonlendir("/program/aktar?adim=esleme", " ".join([ileti, *uyarilar]))
        anlasilmayan = []
        degisen = 0
        for satir in sonuc["eokul"]["bloklar"]:
            gelen = form.get(f"b_{satir['no']}")
            if gelen is None:
                continue
            gelen = str(gelen).strip()[:30]
            kanonik = metin.sube_duzelt(gelen) if gelen else ""
            if kanonik is None:
                anlasilmayan.append(str(satir["no"]))
                continue
            if kanonik == satir["deger"] and satir["durum"] != "secildi":
                continue
            secimler.setdefault("blok", {})[str(satir["no"])] = kanonik
            degisen += 1
        if degisen:
            onizleme_guncelle(b, kayit, veri)
            vt.kayit_dus(b, k["ad"], "Ders programı eşlemesi değişti", f"{degisen} blok şubesi", y.istemci_ip(istek))
        if anlasilmayan:
            return y.yonlendir("/program/aktar?adim=esleme",
                               f"Şube anlaşılamadı ({', '.join(anlasilmayan[:10])}. blok); 9/A biçiminde yazın ya da boş bırakın.",
                               hata=True)  # fmt: skip
        return None

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
            if veri["kaynak"] == "eokul":
                yanit = eokul_esle(istek, k, b, kayit, veri, sonuc, form)
                if yanit is not None:
                    return yanit
            for onek, tur in (("d", "derslik"), ("s", "sinif"), ("p", "saat"), ("t", "sube"), ("g", "devre")):
                for n, e in enumerate(sonuc["cozum"]["eslesme"][tur]):
                    gelen = form.get(f"{onek}_{n}")
                    if gelen is None:
                        continue
                    gelen = str(gelen).strip()[:40]
                    if gelen == str(e["deger"] or "") and e["durum"] != "secildi":
                        continue
                    secimler.setdefault(tur, {})[e["anahtar"]] = gelen
                    degisen += 1
            for alan in ("donem",):
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
            kaynak = program_aktar.hatirlanan_kaynagi(veri)
            # 0.21.0: isteğe bağlı şube bilgisi (yalnız aSc; kutu işaretsiz gelir)
            subeler = sonuc["sube_guncellemesi"] if veri["kaynak"] == "asc" and form.get("subeleri_guncelle") == "1" else None
            if not sonuc["program_degisir"] and not subeler:
                return y.yonlendir("/program/aktar?adim=onizleme", "Değişecek tahta yok; eşlemeyi kontrol edin.", hata=True)
            sonuc_ = program_aktar.uygula(b, sonuc["cozum"], k["ad"], veri["bicim"], kaynak, temizle, subeler)
            vt.ayar_yaz(b, "program_onizleme", None)
            t = sonuc["fark"]["toplam"]
            vt.kayit_dus(
                b, k["ad"], "Ders programı içe aktarıldı",
                f"{program_aktar.BICIM_ADI.get(veri['bicim'], veri['bicim'])} · {t['tahta']} tahta · +{t['eklenen']} "
                f"−{t['silinen']} ~{t['degisen']} · {sonuc['hata_sayisi']} hatalı satır atlandı"
                + (f" · {len(temizle)} tahtanın devre programı temizlendi" if temizle else "")
                + (f" · {sonuc_['sube_tahta']} tahtanın şube bilgisi güncellendi" if sonuc_["sube_tahta"] else ""),
                y.istemci_ip(istek),
            )  # fmt: skip
        ileti = f"{sonuc_['tahta']} tahtanın programı güncellendi. Önceki program “Önceki programlar” listesinden geri yüklenebilir."
        if not sonuc["program_degisir"]:
            ileti = "Derslik programları değişmedi."
        if sonuc_["sube_tahta"]:
            ileti += f" {sonuc_['sube_tahta']} tahtanın şube bilgisi programdan güncellendi."
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
            serit = program_is.program_ozeti(b, simdi_dt())
        return y.sayfa(istek, "program_gecmis.html", k, gecmis=liste, onay_surumu=None, serit=serit, bolum="gecmis")

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
                serit = program_is.program_ozeti(b, simdi_dt())
                return y.sayfa(istek, "program_gecmis.html", k, gecmis=liste, onay_surumu=onay, serit=serit, bolum="gecmis")
            sonuc = program_aktar.geri_yukle(b, surum_id, k["ad"])
            if sonuc is None:
                return y.yonlendir("/program?bolum=derslik", "Sürüm okunamadı.", hata=True)
            ek = (f" · {sonuc['tahta_bilgisi']} tahtanın şube bilgisi geri döndü" if sonuc["tahta_bilgisi"] else "") + (
                f" · {sonuc['tahta_bilgisi_atlanan']} tahtanın şube bilgisi sonradan değiştiği için korundu"
                if sonuc["tahta_bilgisi_atlanan"] else "")  # fmt: skip
            vt.kayit_dus(b, k["ad"], "Ders programı geri yüklendi", f"sürüm #{surum_id} · {sonuc['satir']} satır" + ek,
                         y.istemci_ip(istek))  # fmt: skip
        ileti = f"Derslik programı {surum['zaman_metni']} tarihli sürüme döndürüldü ({sonuc['satir']} satır)."
        if sonuc["tahta_bilgisi"]:
            ileti += f" {sonuc['tahta_bilgisi']} tahtanın şube bilgisi de eski hâline döndü."
        if sonuc["tahta_bilgisi_atlanan"]:
            ileti += (f" {sonuc['tahta_bilgisi_atlanan']} tahtanın şube bilgisi o zamandan beri değiştirildiği için "
                      "olduğu gibi bırakıldı.")  # fmt: skip
        return y.yonlendir("/program?bolum=derslik", ileti)
