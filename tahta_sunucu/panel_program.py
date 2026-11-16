"""Panel: Program sayfası (zil saatleri, derslik programları, kurallar, istisnalar), boş ders
uyarıları ve tahta sayfasındaki program ızgarası.

Yetki (ortak sözlük §3): zil saatleri, derslik programı ve kurallar yalnız yönetici; istisna
ekleme/iptal ve uyarıyı "görüldü" yapma iki role açık. Her yazma işlemi işlem kaydına düşer.
Yüklenen dosya diske kalıcı yazılmaz; önizleme `program_onizleme` ayarında 30 dk durur
(kişisel veri içermez) ve yalnız onu oluşturan kullanıcı onaylayabilir.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import platform
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from starlette.datastructures import UploadFile

from . import cizelge, guvenlik, hedef, metin, program, program_is, saklama, vt, zamanlama

gunluk = logging.getLogger("tahta-sunucu")
ISTANBUL = program.ISTANBUL
BOLUMLER = ("zil", "derslik", "kurallar", "istisnalar")


def okulzili_yerel_yolu() -> Path:
    """Okul Zili `paths.py::user_data_dir()` ile aynı sıra; yol kullanıcıdan alınmaz."""
    ozel = os.environ.get("OKUL_ZILI_DATA_DIR")
    if ozel:
        return Path(ozel).expanduser().resolve() / "ayarlar.json"
    if platform.system().lower() == "windows":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "OkulZili" / "ayarlar.json"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "okul-zili" / "ayarlar.json"


def simdi_dt() -> datetime:
    return datetime.fromtimestamp(vt.simdi(), ISTANBUL)


def ham_satirlar(saatler: list[tuple]) -> list[list]:
    return [list(s) for s in saatler]


def izgaralar(saatler: list[tuple], dersli: dict | None = None) -> list[dict]:
    """Devre başına haftalık tablo. Hücre: {"gun","saat","bas","bit","alan_bas","alan_bit"} ve
    `dersli` verilirse (tahta ızgarası) {"var","sube","alan","sube_alan"}; ders yoksa None.

    dersli: {(gun, devre, no): sube}. Alan adları: zil `s_{gun}_{devre}_{no}_bas|bit`,
    tahta `d_{gun}_{devre}_{no}` (değer 1) ve `sube_{gun}_{devre}_{no}`.
    """
    devreler: dict[str, dict] = {}
    for gun, devre, devre_adi, no, bas, bit in saatler:
        d = devreler.setdefault(devre, {"devre": devre, "devre_adi": devre_adi, "hucre": {}, "gunler": set(), "nolar": set()})
        d["hucre"][(gun, no)] = (bas, bit)
        d["gunler"].add(gun)
        d["nolar"].add(no)
    sonuc = []
    for devre, d in sorted(devreler.items(), key=lambda x: min(b for b, _ in x[1]["hucre"].values())):
        gunler = sorted(d["gunler"])
        satirlar = []
        for no in sorted(d["nolar"]):
            hucreler = []
            for gun in gunler:
                if (gun, no) not in d["hucre"]:
                    hucreler.append(None)
                    continue
                bas, bit = d["hucre"][(gun, no)]
                anahtar = f"{gun}_{devre}_{no}"
                hucre = {"gun": gun, "saat": f"{bas}–{bit}", "bas": bas, "bit": bit,
                         "alan_bas": f"s_{anahtar}_bas", "alan_bit": f"s_{anahtar}_bit"}  # fmt: skip
                if dersli is not None:
                    hucre.update(var=(gun, devre, no) in dersli, sube=dersli.get((gun, devre, no), ""),
                                 alan=f"d_{anahtar}", sube_alan=f"sube_{anahtar}")  # fmt: skip
                hucreler.append(hucre)
            satirlar.append({"no": no, "hucreler": hucreler})
        sonuc.append({"devre": devre, "devre_adi": d["devre_adi"], "gunler": gunler,
                      "gun_adlari": [program.GUN_ADLARI[g] for g in gunler], "satirlar": satirlar})  # fmt: skip
    return sonuc


def kaynak_gorunumu(kaynak: dict | None) -> dict | None:
    if not isinstance(kaynak, dict):
        return None
    zaman = datetime.fromtimestamp(int(kaynak.get("yukleme") or 0), ISTANBUL).strftime("%d.%m.%Y %H:%M")
    tur = "Okul Zili'nden alındı" if kaynak.get("tur") == "okulzili" else "Elle girildi"
    metin_ = f"{tur} · {zaman} · {kaynak.get('yukleyen', '')}"
    if kaynak.get("tur") == "okulzili" and kaynak.get("duzenlendi"):
        metin_ += " · elle düzenlendi"
    return {**kaynak, "metin": metin_}


def yerel_degismis(kaynak: dict | None) -> bool:
    """İçe aktarılan yerel Okul Zili dosyası sonradan değişti mi (zaman/özet karşılaştırması)."""
    if not isinstance(kaynak, dict) or not kaynak.get("dosya_yolu"):
        return False
    yol = okulzili_yerel_yolu()
    if str(yol) != kaynak.get("dosya_yolu"):
        return False
    try:
        if int(yol.stat().st_mtime) == int(kaynak.get("dosya_zamani") or 0):
            return False
        return hashlib.sha256(yol.read_bytes()).hexdigest() != kaynak.get("dosya_ozet")
    except OSError:
        return False


def istisna_gorunumu(b, satirlar, an: int) -> list[dict]:
    adlar = {t["id"]: t["ad"] for t in b.execute("SELECT id, ad FROM tahta")}
    sonuc = []
    for s in satirlar:
        kapsam = program_is.istisna_kapsami(s)
        durum = program_is.istisna_durumu(s, an)
        sonuc.append(
            {
                "id": s["id"],
                "aralik": f"{zamanlama.an_yaz(s['bas'])} – {zamanlama.an_yaz(s['bit'])}",
                "kapsam": "Tümü" if kapsam is None else ", ".join(adlar.get(i, f"#{i}") for i in kapsam) or "—",
                "neden": s["neden"],
                "olusturan": s["olusturan"],
                "durum": durum,
                "durum_adi": program_is.ISTISNA_DURUMU[durum],
                "iptal_edilebilir": durum in ("etkin", "ileride"),
            }
        )
    return sonuc


def govde_uzunlugu(istek: Request) -> int | None:
    """Yükleme gövdesinin bildirilen boyu; Content-Length yoksa, bozuksa ya da gövde parça parça
    (chunked) geliyorsa None. Tarayıcı form gönderimi her zaman Content-Length yollar; başlıksız
    gövde geçici dizine sınırsız yazılmasın diye reddedilir (şartname §4)."""
    if "chunked" in istek.headers.get("transfer-encoding", "").lower():
        return None
    try:
        uzunluk = int(istek.headers.get("content-length", ""))
    except ValueError:
        return None
    return uzunluk if uzunluk >= 0 else None


async def bellekte_form(istek: Request, sinir: int, *, max_files: int = 1, max_fields: int = 3):
    """Kişisel veri taşıyan yüklemeyi diske taşırmadan ayrıştırır.

    Starlette dosya parçasını 1 MB'tan sonra %TEMP% altında geçici dosyaya taşır (spool_max_size);
    öğrenci listesi orada iz bırakmasın diye sınır bu ayrıştırıcı için gövde sınırına çekilir.
    Çağıran gövde boyunu önce `govde_uzunlugu` ile `sinir`e karşı denetlemiş olmalıdır.
    Yalnız multipart/form-data kabul eder; başkası ValueError."""
    from starlette.formparsers import MultiPartParser

    if not istek.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        raise ValueError("Dosya okunamadı.")
    ayristirici = MultiPartParser(istek.headers, istek.stream(), max_files=max_files, max_fields=max_fields)
    ayristirici.spool_max_size = sinir + 1
    return await ayristirici.parse()


def zil_baglami(b, simdi: datetime, yonetici: bool) -> dict:
    """program.html zil bölümünün çizelge kısmı (0.10.0, zil düzenleyici §5.1); `zil` bağlamına eklenir.

    {"bugun": panel_cizelge.gun_baglami(bugün), "cizelgeler": [{"id","ad","devreler","saat_araligi","kullanim",
    "kaynak_metni","silinebilir"}] (ada göre), "secenekler": [(id, ad)], "haftalik": [{"gun","gun_adi","cizelge_id","ozet"}],
    "haftalik_uyarilari": [metin], "tarihliler": [{"id","ad","aralik","gunler","cizelge","durum","durum_adi"}],
    "okulzili_kurallari": [{"ad","tur","aralik"}], "varsayilan_gunler", "tarihli_ad_en_uzun", "ad_en_uzun", "yonetici"}.
    """
    from . import panel_cizelge

    bugun = simdi.date()
    cizelgeler = []
    satirlar = b.execute("SELECT * FROM zil_cizelgesi").fetchall()
    for s in sorted(satirlar, key=lambda s: metin.tr_sirala_anahtari(s["ad"])):
        dersler = cizelge.cizelge_dersleri(b, s["id"])
        bilgi = cizelge.kullanim_bilgisi(b, s["id"], bugun)
        kaynak = cizelge.KAYNAK_ADI.get(s["kaynak"], s["kaynak"])
        if s["kaynak"] == "okulzili" and s["guncelleme"]:
            kaynak += " · elle düzenlendi"
        cizelgeler.append({
            "id": s["id"], "ad": s["ad"], "devreler": cizelge.devre_ozeti(dersler) if dersler else "Ders yok",
            "saat_araligi": cizelge.saat_araligi(dersler), "kullanim": bilgi["metin"], "kaynak_metni": kaynak,
            "silinebilir": not bilgi["kullaniliyor"],
        })  # fmt: skip
    ozetler = {c["id"]: f"{c['devreler']} · {c['saat_araligi']}" for c in cizelgeler}
    haftalik = cizelge.haftalik_oku(b)
    adlar = {c["id"]: c["ad"] for c in cizelgeler}
    tarihliler = []
    for s in b.execute("SELECT * FROM zil_tarihli ORDER BY bas DESC, id DESC LIMIT 200"):
        durum = cizelge.tarihli_durumu(s, bugun)
        tarihliler.append({
            "id": s["id"], "ad": s["ad"], "aralik": cizelge.aralik_metni(s["bas"], s["bit"]),
            "gunler": cizelge.gun_araligi(cizelge.gunler_coz(s["gunler"])),
            "cizelge": adlar.get(s["cizelge_id"], "—") if s["cizelge_id"] else "Ders yok",
            "durum": durum, "durum_adi": cizelge.TARIHLI_DURUMU[durum],
        })  # fmt: skip
    takvim = vt.ayar_al(b, "zil_takvimi") or {}
    kurallar = [
        {"ad": k.get("ad", ""), "tur": program.KURAL_ADI.get(k.get("tur"), k.get("tur")),
         "aralik": cizelge.aralik_metni(k["bas"], k["bit"]) if k.get("bas") and k.get("bit") else ""}
        for k in (takvim.get("kurallar") or []) if isinstance(k, dict)
    ]  # fmt: skip
    return {
        "bugun": panel_cizelge.gun_baglami(b, bugun),
        "cizelgeler": cizelgeler,
        "secenekler": [(c["id"], c["ad"]) for c in cizelgeler],
        "haftalik": [{"gun": g, "gun_adi": program.GUN_ADLARI[g], "cizelge_id": haftalik.get(g),
                      "ozet": ozetler.get(haftalik.get(g), "Ders yok")} for g in range(7)],  # fmt: skip
        "haftalik_uyarilari": panel_cizelge.haftalik_uyarilari(b),
        "tarihliler": tarihliler,
        "okulzili_kurallari": kurallar,
        "varsayilan_gunler": [0, 1, 2, 3, 4],
        "tarihli_ad_en_uzun": cizelge.TARIHLI_AD_EN_UZUN,
        "ad_en_uzun": cizelge.AD_EN_UZUN,
        "yonetici": yonetici,
    }


def tahta_program_baglami(b, tahta) -> dict:
    """tahta.html'in `program` bağlamı (bkz. modül sonundaki sözleşme)."""
    saatler = program.ders_saatleri_oku(b)
    dersli = {
        (s["gun"], s["devre"], s["ders_no"]): s["sube"]
        for s in b.execute("SELECT * FROM tahta_ders WHERE tahta_id = ?", (tahta["id"],))
    }
    an = vt.simdi()
    istisnalar = [
        s
        for s in b.execute("SELECT * FROM program_istisna WHERE iptal IS NULL AND bit > ? ORDER BY bas", (an,))
        if program_is.istisna_kapsami(s) is None or tahta["id"] in (program_is.istisna_kapsami(s) or [])
    ]
    durum = program_is.durum_oku(tahta)
    if tahta["program_muaf"]:
        durum_metni = "Muaf"
    elif durum.get("kilitli") and durum.get("kilit_kaynak") == "program":
        bilgi = program_is.tahta_program(tahta)
        durum_metni = "Program kilidi" + (f" ({bilgi['neden']})" if bilgi["neden"] else "")
        durum_metni += f", {program.saat_eki(bilgi['acilis'])} açılır" if bilgi["acilis"] else ""
    else:
        simdi = simdi_dt()
        ders = program.simdiki_ders(b, tahta, simdi)
        if not ders:
            durum_metni = "Program kilidi yok"
        else:
            # Tahtanın gerçek durumu: çevrimdışıysa "kapalı" — Uyarılar sayfasıyla çelişmesin.
            if not program_is.cevrimici(tahta, an):
                gercek = "tahta kapalı"
            elif durum.get("kilitli"):
                gercek = "idare kilidinde"
            else:
                gercek = "açık"
            durum_metni = f"Ders saatinde ({ders['ders_no']}. ders), {gercek}"
    gecerli = {(s[0], s[1], s[3]) for s in saatler}
    return {
        "muaf": bool(tahta["program_muaf"]),
        "izgaralar": izgaralar(saatler, dersli),
        "dersli_sayisi": sum(1 for a in dersli if a in gecerli),
        "toplam_ders": len(saatler),
        "yetim_sayisi": sum(1 for a in dersli if a not in gecerli),
        "ders_saati_var": bool(saatler),
        "istisnalar": istisna_gorunumu(b, istisnalar, an),
        "durum_metni": durum_metni,
        "program_yetenegi": program_is.yetenekli(tahta),
    }


def yetki_reddi(y, istek: Request, k, islem: str, donus: str = "/program"):
    """Yönetici değilse kayda düşürüp reddeder (oturum yoksa girişe); yöneticiyse None.

    Zil saatleri, derslik programı, program kuralları ve ders programı içe aktarma yalnız yöneticinindir
    (ortak sözlük §3); idarecinin denemesi "Yetkisiz işlem reddedildi" olarak işlem kaydına düşer."""
    if not k:
        return y.yonlendir("/giris")
    if k["rol"] != "yonetici":
        with vt.islem() as b:
            vt.kayit_dus(b, k["ad"], "Yetkisiz işlem reddedildi", islem, y.istemci_ip(istek))
        return y.yonlendir(donus, "Bu işlem için yönetici yetkisi gerekir.", hata=True)
    return None


def onizleme_yaz(b, tur: str, veri: dict, k) -> str:
    """İçe aktarma önizlemesi (`ayar.program_onizleme`; kişisel veri içermez, 30 dk, kullanıcıya bağlı belirteç)."""
    kimlik = guvenlik.belirtec()
    vt.ayar_yaz(
        b,
        "program_onizleme",
        {"kimlik": kimlik, "tur": tur, "bitis": vt.simdi() + program.ONIZLEME_OMRU_SN, "kullanici": k["ad"], "veri": veri},
    )
    return kimlik


def onizleme_al(b, tur: str, kimlik: str, k) -> dict | None:
    kayit = vt.ayar_al(b, "program_onizleme")
    if not isinstance(kayit, dict) or kayit.get("tur") != tur or not kimlik:
        return None
    if not hmac.compare_digest(str(kayit.get("kimlik", "")), str(kimlik)) or kayit.get("kullanici") != k["ad"]:
        return None
    if int(kayit.get("bitis") or 0) <= vt.simdi():
        vt.ayar_yaz(b, "program_onizleme", None)
        return None
    return kayit


def kaydet(uygulama, y) -> None:
    def yetkisiz(istek: Request, k, islem: str, donus: str = "/program"):
        return yetki_reddi(y, istek, k, islem, donus)

    def uyandir_hepsi(idler) -> None:
        y.uyandir_hepsi(idler)

    # ---- sayfa -----------------------------------------------------------------------------
    @uygulama.get("/program", response_class=HTMLResponse)
    async def program_sayfasi(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        return program_ciz(istek, k)

    def program_ciz(istek: Request, k, durum_kodu: int = 200, **ek) -> HTMLResponse:
        """program.html'i çizer. Hatalı bir form yönlendirmeden yeniden çizilirken (422) `ek` ile ileti ve
        girilen değerler verilir (ör. tarihli_form); bölüm sorgudan, yoksa "zil"."""
        bolum = istek.query_params.get("bolum", "zil")
        bolum = bolum if bolum in BOLUMLER else "zil"
        simdi = simdi_dt()
        an = vt.simdi()
        yonetici = k["rol"] == "yonetici"
        with vt.islem() as b:
            saatler = program.ders_saatleri_oku(b)
            kaynak = vt.ayar_al(b, "zil_kaynagi")
            takvim = vt.ayar_al(b, "zil_takvimi")
            serit = program_is.program_ozeti(b, simdi)
            onizleme = None
            kayit = vt.ayar_al(b, "program_onizleme")
            if (
                istek.query_params.get("onizleme") == "1"
                and isinstance(kayit, dict)
                and kayit.get("kullanici") == k["ad"]
                and int(kayit.get("bitis") or 0) > an
            ):
                veri = kayit["veri"]
                onizleme = {"tur": kayit["tur"], "kimlik": kayit["kimlik"], **veri}
                if kayit["tur"] == "zil":
                    onizleme["izgaralar"] = izgaralar([tuple(d) for d in veri["dersler"]])
                    onizleme["onaylanabilir"] = not veri["hatalar"]
                else:
                    onizleme["onaylanabilir"] = bool(veri["tahtalar"])
                bolum = "zil" if kayit["tur"] == "zil" else "derslik"
            tahta_satirlari = b.execute(
                "SELECT * FROM tahta WHERE durum = 'onayli' ORDER BY derslik COLLATE NOCASE, ad COLLATE NOCASE"
            ).fetchall()
            gecerli = {(s[0], s[1], s[3]) for s in saatler}
            sayilar: dict[int, list[int]] = {}
            for s in b.execute("SELECT tahta_id, gun, devre, ders_no FROM tahta_ders"):
                sayi = sayilar.setdefault(s["tahta_id"], [0, 0])
                sayi[0 if (s["gun"], s["devre"], s["ders_no"]) in gecerli else 1] += 1
            kural = program.ayar_kilit(b)
            bos = program.ayar_bos_ders(b)
            istisnalar = istisna_gorunumu(
                b, b.execute("SELECT * FROM program_istisna ORDER BY bas DESC LIMIT 200").fetchall(), an
            )
            zil_ek = zil_baglami(b, simdi, yonetici) if bolum == "zil" else {}
            from . import program_aktar

            gecmis = program_aktar.surum_listesi(b) if bolum == "derslik" and yonetici else []
        derslik_tahtalari = [
            {"id": t["id"], "ad": t["ad"], "derslik": t["derslik"], "dersli": sayilar.get(t["id"], [0, 0])[0],
             "toplam": len(saatler), "muaf": bool(t["program_muaf"]), "programli": sayilar.get(t["id"], [0, 0])[0] > 0}  # fmt: skip
            for t in tahta_satirlari
        ]
        return y.sayfa(
            istek,
            "program.html",
            k,
            durum_kodu=durum_kodu,
            **ek,
            bolum=bolum,
            yonetici=yonetici,
            serit=serit,
            gun_adlari=program.GUN_ADLARI,
            zil={
                "kaynak": kaynak_gorunumu(kaynak),
                "degismis": yerel_degismis(kaynak),
                "yerel_var": yonetici and okulzili_yerel_yolu().is_file(),
                "izgaralar": izgaralar(saatler),
                "takvim_ozeti": program.takvim_ozeti(takvim) if takvim else "",
                "takvim_var": bool(takvim and takvim.get("ogretim")),
                "satir_sayisi": len(saatler),
                **zil_ek,
            },
            onizleme=onizleme,
            derslik={
                "tahtalar": derslik_tahtalari,
                "yetim_sayisi": sum(1 for v in sayilar.values() if v[1]),
                "gecmis": gecmis,
            },
            kurallar={
                "program_kilidi": kural,
                "bos_ders_uyarisi": bos,
                "yetersiz_tahtalar": [
                    {"id": t["id"], "ad": t["ad"], "surum": t["surum"]} for t in tahta_satirlari if not program_is.yetenekli(t)
                ],
            },
            istisnalar=istisnalar,
            tahtalar=[{"id": t["id"], "ad": t["ad"], "derslik": t["derslik"]} for t in tahta_satirlari],
            neden_en_uzun=program.ISTISNA_NEDEN_EN_UZUN,
            bugun=simdi.date().isoformat(),
        )

    uygulama.state.program_ciz = program_ciz

    # ---- zil saatleri ------------------------------------------------------------------------
    def zil_onizlemesi(b, k, cozum: dict, kaynak: dict) -> str:
        return onizleme_yaz(b, "zil", {**cozum, "kaynak": kaynak}, k)

    @uygulama.post("/program/zil/yukle")
    async def zil_yukle(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Zil saatleri yükleme")
        if engel:
            return engel
        donus = "/program?bolum=zil"
        uzunluk = govde_uzunlugu(istek)
        if uzunluk is None:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        if uzunluk > program.ZIP_EN_COK_BAYT + 1024 * 1024:
            return y.yonlendir(donus, "Dosya en çok 200 MB olabilir.", hata=True)
        try:
            form = await istek.form(max_files=1, max_fields=5)
        except Exception:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        try:
            dosya = form.get("dosya")
            if not isinstance(dosya, UploadFile) or not dosya.filename:
                return y.yonlendir(donus, "Dosya seçilmedi.", hata=True)
            ad = dosya.filename.lower()
            if ad.endswith(".json"):
                bayt = await dosya.read(program.JSON_EN_COK_BAYT + 1)
                if len(bayt) > program.JSON_EN_COK_BAYT:
                    return y.yonlendir(donus, "ayarlar.json en çok 2 MB olabilir.", hata=True)
                ozet = hashlib.sha256(bayt).hexdigest()
                kaynak_veri = bayt
            elif ad.endswith(".okulzili") or ad.endswith(".zip"):
                if (dosya.size or 0) > program.ZIP_EN_COK_BAYT:
                    return y.yonlendir(donus, "Dosya en çok 200 MB olabilir.", hata=True)
                ozetci = hashlib.sha256()
                await dosya.seek(0)
                while parca := await dosya.read(1024 * 1024):
                    ozetci.update(parca)
                ozet = ozetci.hexdigest()
                await dosya.seek(0)
                kaynak_veri = dosya.file
            else:
                return y.yonlendir(donus, "Okul Zili'nin ayarlar.json dosyasını ya da .okulzili yedeğini seçin.", hata=True)
            try:
                cozum = program.okulzili_oku(kaynak_veri, ad)
            except ValueError as hata:
                gunluk.info("Okul Zili dosyası reddedildi: %s", hata)
                return y.yonlendir(donus, str(hata), hata=True)
        finally:
            await form.close()
        with vt.islem() as b:
            kaynak = {"tur": "okulzili", "dosya_ozet": ozet, "dosya_yolu": "", "dosya_zamani": None,
                      "okulzili_surumu": cozum["okulzili_surumu"]}  # fmt: skip
            zil_onizlemesi(b, k, cozum, kaynak)
            vt.kayit_dus(b, k["ad"], "Zil saatleri önizlendi", f"Okul Zili dosyası · {len(cozum['dersler'])} ders saati", y.istemci_ip(istek))
        return y.yonlendir("/program?bolum=zil&onizleme=1")

    @uygulama.post("/program/zil/yerel")
    async def zil_yerel(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Zil saatleri yerel okuma")
        if engel:
            return engel
        donus = "/program?bolum=zil"
        yol = okulzili_yerel_yolu()
        try:
            if yol.stat().st_size > program.JSON_EN_COK_BAYT:
                return y.yonlendir(donus, "Okul Zili dosyası en çok 2 MB olabilir.", hata=True)
            with open(yol, "rb") as f:  # yalnız okuma
                bayt = f.read(program.JSON_EN_COK_BAYT + 1)
            zaman = int(yol.stat().st_mtime)
        except OSError:
            return y.yonlendir(donus, "Bu bilgisayarda Okul Zili yapılandırması bulunamadı.", hata=True)
        try:
            cozum = program.okulzili_oku(bayt, "ayarlar.json")
        except ValueError as hata:
            gunluk.info("Yerel Okul Zili dosyası reddedildi: %s", hata)
            return y.yonlendir(donus, str(hata), hata=True)
        with vt.islem() as b:
            kaynak = {"tur": "okulzili", "dosya_ozet": hashlib.sha256(bayt).hexdigest(), "dosya_yolu": str(yol),
                      "dosya_zamani": zaman, "okulzili_surumu": cozum["okulzili_surumu"]}  # fmt: skip
            zil_onizlemesi(b, k, cozum, kaynak)
            vt.kayit_dus(b, k["ad"], "Zil saatleri önizlendi", f"Bu bilgisayardaki Okul Zili · {len(cozum['dersler'])} ders saati", y.istemci_ip(istek))
        return y.yonlendir("/program?bolum=zil&onizleme=1")

    @uygulama.post("/program/zil/onayla")
    async def zil_onayla(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Zil saatleri onaylama")
        if engel:
            return engel
        form = await istek.form()
        donus = "/program?bolum=zil"
        with vt.islem() as b:
            kayit = onizleme_al(b, "zil", str(form.get("onizleme", "")), k)
            if form.get("eylem") == "vazgec":
                if kayit:
                    vt.ayar_yaz(b, "program_onizleme", None)
                return y.yonlendir(donus, "Önizleme kapatıldı; zil saatleri değişmedi.")
            if not kayit:
                return y.yonlendir(donus, "Önizlemenin süresi geçmiş ya da başka bir kullanıcıya ait. Dosyayı yeniden yükleyin.", hata=True)
            veri = kayit["veri"]
            if veri["hatalar"]:
                return y.yonlendir(donus + "&onizleme=1", "Önizlemedeki hatalar giderilmeden kaydedilemez.", hata=True)
            from .panel_cizelge import Etki

            etki = Etki(b)
            cizelge_sayisi = cizelge.okulzili_yaz(b, veri, k)
            vt.ayar_yaz(b, "zil_takvimi", veri["takvim"])
            vt.ayar_yaz(b, "zil_kaynagi", {**veri["kaynak"], "yukleme": vt.simdi(), "yukleyen": k["ad"], "duzenlendi": False})
            vt.ayar_yaz(b, "program_onizleme", None)
            vt.kayit_dus(
                b, k["ad"], "Zil saatleri kaydedildi",
                f"Okul Zili · {len(veri['dersler'])} ders saati · {len(veri['takvim'].get('kurallar') or [])} tarih kuralı"
                f" · {cizelge_sayisi} çizelge",
                y.istemci_ip(istek),
            )  # fmt: skip
            iletiler = etki.bitir(b, k)
        uygulama.state.zil_etki_sonrasi(etki)
        return y.yonlendir(donus, " ".join(["Zil saatleri kaydedildi.", *iletiler]))

    @uygulama.post("/program/zil/sil")
    async def zil_sil(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Zil saatleri silme")
        if engel:
            return engel
        with vt.islem() as b:
            # 0.10.0: bütün zil düzeni (çizelgeler, haftalık düzen, tarihe özel çizelgeler) ve takvim silinir;
            # derslik programları kalır (yetim olarak görünür).
            b.execute("DELETE FROM zil_tarihli")
            b.execute("DELETE FROM zil_haftalik")
            b.execute("DELETE FROM zil_cizelgesi")
            b.execute("DELETE FROM ders_saati")
            vt.ayar_yaz(b, "zil_takvimi", None)
            vt.ayar_yaz(b, "zil_kaynagi", None)
            kural = program.ayar_kilit(b)
            kural["etkin"] = False  # programsız kilit olmaz (K30)
            vt.ayar_yaz(b, "program_kilidi", kural)
            uyandir = program_is.askiya_alma_acmasi(b, None, k["ad"])
            vt.kayit_dus(b, k["ad"], "Zil düzeni silindi", "Program kilidi kapatıldı.", y.istemci_ip(istek))
        isleyici = getattr(uygulama.state, "program_isleyici", None)
        if isleyici is not None:
            isleyici.bugun_degisti()
        uyandir_hepsi(uyandir)
        return y.yonlendir("/program?bolum=zil", "Zil düzeni silindi; program kilidi kapatıldı.")

    # ---- derslik programları ----------------------------------------------------------------
    @uygulama.get("/program/derslik/ornek.csv")
    async def derslik_ornek(istek: Request):
        if not y.kullanici(istek):
            return y.yonlendir("/giris")
        with vt.islem() as b:
            icerik = program.ornek_csv(program.ders_saatleri_oku(b))
        return Response(
            icerik,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="derslik-programi-ornek.csv"'},
        )

    # 0.10.0: derslik programı CSV yüklemesi içe aktarma sihirbazına taşındı (`panel_aktar`). Eski uçlar yetki
    # denetiminden sonra sihirbaza yönlendirir; bir sürüm sonra silinir.
    @uygulama.post("/program/derslik/yukle")
    async def derslik_yukle(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Derslik programı yükleme")
        if engel:
            return engel
        return y.yonlendir("/program/aktar", "Derslik programı artık “Ders programını içe aktar” sihirbazıyla yüklenir.")

    @uygulama.post("/program/derslik/onayla")
    async def derslik_onayla(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Derslik programı onaylama")
        if engel:
            return engel
        return y.yonlendir("/program/aktar", "Derslik programı artık “Ders programını içe aktar” sihirbazıyla yüklenir.")

    @uygulama.post("/program/derslik/yetim-temizle")
    async def derslik_yetim(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Derslik programı yetim temizliği")
        if engel:
            return engel
        with vt.islem() as b:
            silinen = b.execute(
                "DELETE FROM tahta_ders WHERE NOT EXISTS (SELECT 1 FROM ders_saati s WHERE s.gun = tahta_ders.gun "
                "AND s.devre = tahta_ders.devre AND s.ders_no = tahta_ders.ders_no)"
            ).rowcount
            vt.kayit_dus(b, k["ad"], "Derslik programı yetim satırları silindi", f"{silinen} satır", y.istemci_ip(istek))
        return y.yonlendir("/program?bolum=derslik", f"Artık olmayan ders saatlerine ait {silinen} satır silindi.")

    @uygulama.post("/tahta/{tahta_id}/program")
    async def tahta_programi(istek: Request, tahta_id: int):
        k = y.kullanici(istek)
        donus = f"/tahta/{tahta_id}#program"
        engel = yetkisiz(istek, k, f"Tahta #{tahta_id} programı", donus)
        if engel:
            return engel
        form = await istek.form()
        with vt.islem() as b:
            tahta = b.execute("SELECT * FROM tahta WHERE id = ? AND durum != 'iptal'", (tahta_id,)).fetchone()
            if not tahta:
                return y.yonlendir("/", "Tahta bulunamadı.", hata=True)
            satirlar = []
            for gun, devre, _ad, no, _b, _s in program.ders_saatleri_oku(b):
                anahtar = f"{gun}_{devre}_{no}"
                if form.get(f"d_{anahtar}") != "1":
                    continue
                ham = str(form.get(f"sube_{anahtar}", "")).strip()
                sube = ""
                if ham:
                    sube = metin.sube_duzelt(ham) or ""
                    if not sube:
                        return y.yonlendir(donus, f"Şube '{ham[:20]}' anlaşılamadı (ör. 9/A).", hata=True)
                satirlar.append((tahta_id, gun, devre, no, sube))
            muaf = form.get("program_muaf") == "1"
            b.execute("DELETE FROM tahta_ders WHERE tahta_id = ?", (tahta_id,))
            b.executemany("INSERT INTO tahta_ders (tahta_id, gun, devre, ders_no, sube) VALUES (?, ?, ?, ?, ?)", satirlar)
            b.execute("UPDATE tahta SET program_muaf = ? WHERE id = ?", (int(muaf), tahta_id))
            uyandir = program_is.askiya_alma_acmasi(b, [tahta_id], k["ad"]) if muaf and not tahta["program_muaf"] else []
            vt.kayit_dus(
                b, k["ad"], "Tahta programı kaydedildi",
                f"{tahta['ad']} · {len(satirlar)} ders saati" + (" · programdan muaf" if muaf else ""), y.istemci_ip(istek),
            )  # fmt: skip
        uyandir_hepsi(uyandir)
        return y.yonlendir(donus, "Program kaydedildi.")

    # ---- kurallar ---------------------------------------------------------------------------
    @uygulama.post("/program/kurallar")
    async def kurallar(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Program kuralları")
        if engel:
            return engel
        form = await istek.form()
        donus = "/program?bolum=kurallar"

        def sayi(ad: str, varsayilan: int, alt: int, ust: int) -> int:
            try:
                return max(alt, min(ust, int(str(form.get(ad, varsayilan)).strip() or varsayilan)))
            except ValueError:
                return varsayilan

        kilit = {
            "etkin": form.get("pk_etkin") == "1",
            "gecikme_dk": sayi("pk_gecikme_dk", 2, 0, 10),
            "bos_saatte_kilitle": form.get("pk_bos_saatte") == "1",
        }
        bos = {"etkin": form.get("bd_etkin") == "1", "esik_dk": sayi("bd_esik_dk", 10, 5, 30), "dokunma_yoksa": False}
        uyandir: list[int] = []
        with vt.islem() as b:
            if kilit["etkin"] and not program.ders_saatleri_oku(b):
                return y.yonlendir(donus, "Program kilidi için önce zil saatlerini girin.", hata=True)
            eski = program.ayar_kilit(b)
            vt.ayar_yaz(b, "program_kilidi", kilit)
            vt.ayar_yaz(b, "bos_ders_uyarisi", bos)
            if eski.get("etkin") and not kilit["etkin"]:
                uyandir = program_is.askiya_alma_acmasi(b, None, k["ad"])
            ayrinti = (
                f"program kilidi {'açık' if kilit['etkin'] else 'kapalı'} ({kilit['gecikme_dk']} dk"
                f"{', boş saatte de' if kilit['bos_saatte_kilitle'] else ''}) · boş ders uyarısı "
                f"{'açık' if bos['etkin'] else 'kapalı'} ({bos['esik_dk']} dk)"
            )
            vt.kayit_dus(b, k["ad"], "Program kuralları kaydedildi", ayrinti, y.istemci_ip(istek))
        uyandir_hepsi(uyandir)
        return y.yonlendir(donus, "Kurallar kaydedildi.")

    # ---- istisnalar ---------------------------------------------------------------------------
    @uygulama.post("/program/istisna")
    async def istisna(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        donus = str(form.get("donus", "")) or "/program?bolum=istisnalar"
        if not donus.startswith("/") or donus.startswith("//"):
            donus = "/program?bolum=istisnalar"
        an = vt.simdi()
        simdi = datetime.fromtimestamp(an, ISTANBUL)
        idler = sorted({int(t) for t in form.getlist("tahta") if str(t).isdigit() and hedef.kimlik_mi(t)})
        neden = " ".join(str(form.get("neden", "")).split())
        sure = str(form.get("sure", ""))
        try:
            if sure in ("1sa", "bugun"):
                bas = an
                bit = an + 3600 if sure == "1sa" else int(datetime.combine(simdi.date(), datetime.max.time(), ISTANBUL).timestamp())
                neden = neden or ("1 saat durduruldu" if sure == "1sa" else "Bugün için durduruldu")
            elif sure:
                raise ValueError("Bilinmeyen süre.")
            else:
                bas = zamanlama.an_hesapla(
                    zamanlama.tarih_coz(form.get("bas_tarih"), "Başlangıç tarihini seçin."),
                    zamanlama.saat_coz(form.get("bas_saat") or "00:00"),
                )
                bit_saat = zamanlama.saat_coz(form.get("bit_saat") or "23:59")
                bit = zamanlama.an_hesapla(zamanlama.tarih_coz(form.get("bit_tarih"), "Bitiş tarihini seçin."), bit_saat)
                if bit_saat == "23:59":
                    bit += 59
            if bit <= bas:
                raise ValueError("Bitiş başlangıçtan sonra olmalı.")
            if bit - bas > program.ISTISNA_EN_UZUN_GUN * 86400:
                raise ValueError(f"İstisna en çok {program.ISTISNA_EN_UZUN_GUN} gün sürebilir.")
            if len(neden) > program.ISTISNA_NEDEN_EN_UZUN:
                raise ValueError(f"Neden en çok {program.ISTISNA_NEDEN_EN_UZUN} karakter olabilir.")
        except ValueError as hata:
            return y.yonlendir(donus, str(hata), hata=True)
        if guvenlik.tc_kimlik_var(neden):
            with vt.islem() as b:
                vt.kayit_dus(b, k["ad"], "Program istisnası reddedildi", "T.C. kimlik numarasına benzeyen sayı", y.istemci_ip(istek))
            return y.yonlendir(donus, guvenlik.TC_KIMLIK_ILETISI, hata=True)
        with vt.islem() as b:
            if idler:
                idler = [t["id"] for t in b.execute(
                    f"SELECT id FROM tahta WHERE durum != 'iptal' AND id IN ({','.join('?' * len(idler))})", idler
                )]  # fmt: skip
                if not idler:
                    return y.yonlendir(donus, "Seçilen tahtalar bulunamadı.", hata=True)
            kimlik = program_is.istisna_ekle(b, bas=bas, bit=bit, tahta_ids=idler or None, neden=neden, olusturan=k["ad"])
            uyandir = program_is.askiya_alma_acmasi(b, idler or None, k["ad"], an) if bas <= an < bit else []
            kapsam = f"{len(idler)} tahta" if idler else "tüm tahtalar"
            # Nedenin metni kayda yazılmaz (serbest metin ad içerebilir; kayıt silinmez, istisna
            # satırı ise saklama süresi sonunda nedeniyle birlikte silinir).
            vt.kayit_dus(
                b, k["ad"], "Program istisnası eklendi",
                f"#{kimlik} {zamanlama.an_yaz(bas)} – {zamanlama.an_yaz(bit)} · {kapsam}" + (" · neden var" if neden else ""),
                y.istemci_ip(istek),
            )  # fmt: skip
        uyandir_hepsi(uyandir)
        bitis_metni = datetime.fromtimestamp(bit, ISTANBUL).strftime("%d.%m.%Y %H:%M")
        if bas > an:
            bas_metni = datetime.fromtimestamp(bas, ISTANBUL).strftime("%d.%m.%Y %H:%M")
            return y.yonlendir(
                donus, f"İstisna eklendi ({kapsam}): {bas_metni} – {bitis_metni}; program kilidi bu aralıkta uygulanmaz."
            )
        return y.yonlendir(donus, f"Program kilidi durduruldu ({kapsam}); bitiş: {bitis_metni}.")

    @uygulama.post("/program/istisna/{istisna_id}/iptal")
    async def istisna_iptal(istek: Request, istisna_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        donus = str(form.get("donus", "")) or "/program?bolum=istisnalar"
        if not donus.startswith("/") or donus.startswith("//"):
            donus = "/program?bolum=istisnalar"
        with vt.islem() as b:
            satir = b.execute("SELECT * FROM program_istisna WHERE id = ?", (istisna_id,)).fetchone()
            if not satir or program_is.istisna_durumu(satir, vt.simdi()) not in ("etkin", "ileride"):
                return y.yonlendir(donus, "İstisna bulunamadı ya da zaten bitmiş.", hata=True)
            b.execute("UPDATE program_istisna SET iptal = ? WHERE id = ?", (vt.simdi(), istisna_id))
            vt.kayit_dus(b, k["ad"], "Program istisnası iptal edildi", f"#{istisna_id}", y.istemci_ip(istek))
        return y.yonlendir(donus, "İstisna iptal edildi.")

    # ---- boş ders uyarıları --------------------------------------------------------------------
    @uygulama.get("/program/uyarilar", response_class=HTMLResponse)
    async def uyarilar(istek: Request):
        """Boş ders uyarıları: tek gün (varsayılan bugün) ya da tarih aralığı raporu (K6).

        Sorgu: tarih (tek gün, eski bağlantılar) | bas & bit (aralık, en çok 400 gün), tahta (kimlik), ders (no).
        Kişi adı gösterilmez. Birden çok günlük ya da süzgeçli görüntüleme işlem kaydına düşer (yalnız tarih aralığı
        ve süzgecin varlığı; tahta, ders ve uyarı sayısı yazılmaz)."""
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        q = istek.query_params
        bugun = simdi_dt().date()

        def tarih_al(ad: str, varsayilan: date) -> date:
            try:
                return zamanlama.tarih_coz(q.get(ad) or varsayilan.isoformat())
            except ValueError:
                return varsayilan

        tek = tarih_al("tarih", bugun)
        bas = tarih_al("bas", tek)
        bit = tarih_al("bit", tek if not q.get("bas") else bugun)
        bit = min(bit, bugun)
        if bas > bit:
            bas, bit = bit, bas
        if (bit - bas).days >= program_is.RAPOR_EN_UZUN_GUN:
            bas = bit - timedelta(days=program_is.RAPOR_EN_UZUN_GUN - 1)
        tahta_id = int(q["tahta"]) if hedef.kimlik_mi(q.get("tahta", "")) else None
        # ders: "3" (bütün devrelerin 3. dersi) ya da "sabah-3" (ikili eğitimde yalnız o devrenin 3. dersi).
        ders_ham = str(q.get("ders", ""))
        devre_s, _, no_s = ders_ham.rpartition("-")
        ders_no = int(no_s) if no_s.isdigit() and 1 <= int(no_s) <= 20 else None
        devre_s = devre_s if ders_no and len(devre_s) <= 40 else ""
        with vt.islem() as b:
            devreler = {s["devre"]: s["devre_adi"]
                        for s in b.execute("SELECT devre, MIN(devre_adi) AS devre_adi, MIN(baslangic) AS ilk "
                                           "FROM ders_saati GROUP BY devre ORDER BY ilk")}  # fmt: skip
            if devre_s not in devreler:
                devre_s = ""
            rapor = program_is.bos_ders_raporu(b, bas, bit, tahta_id, ders_no, devre_s or None)
            serit = program_is.program_ozeti(b, simdi_dt())
            tahtalar = [{"id": t["id"], "ad": t["ad"], "derslik": t["derslik"]}
                        for t in b.execute("SELECT id, ad, derslik FROM tahta WHERE durum != 'iptal'")]  # fmt: skip
            if len(devreler) > 1:
                ilk = {d: i for i, d in enumerate(devreler)}
                nolar = [
                    {"deger": f"{s['devre']}-{s['ders_no']}", "ad": f"{devreler[s['devre']]} · {s['ders_no']}. ders"}
                    for s in sorted(b.execute("SELECT DISTINCT devre, ders_no FROM ders_saati").fetchall(),
                                    key=lambda s: (ilk.get(s["devre"], 99), s["ders_no"]))
                ]  # fmt: skip
            else:
                nolar = [{"deger": str(n), "ad": f"{n}. ders"}
                         for n in sorted({s["ders_no"] for s in b.execute("SELECT DISTINCT ders_no FROM ders_saati")})]  # fmt: skip
            secili_ders = f"{devre_s}-{ders_no}" if devre_s and ders_no else (str(ders_no) if ders_no else "")
            saklama_metni = saklama.silinme_metni(b)
            if bas != bit or tahta_id or ders_no:
                # Kayda uyarının içeriği (tahta, ders, sayı) yazılmaz: kayıt silinmez, uyarı yıl sonunda silinir.
                suzgec = [a for a, v in (("tahta süzgeci", tahta_id), ("ders saati süzgeci", ders_no)) if v]
                vt.kayit_dus(
                    b, k["ad"], "Boş ders raporu görüntülendi",
                    f"{zamanlama.tarih_yaz(bas)}–{zamanlama.tarih_yaz(bit)}" + (f" · {', '.join(suzgec)}" if suzgec else ""),
                    y.istemci_ip(istek),
                )  # fmt: skip
        tahtalar.sort(key=lambda t: metin.tr_sirala_anahtari(t["ad"]))
        return y.sayfa(
            istek,
            "uyarilar.html",
            k,
            rapor=rapor,
            uyarilar=rapor["satirlar"],
            serit=serit,
            bolum="uyarilar",
            tek_gun=bas == bit,
            bas=bas.isoformat(),
            bit=bit.isoformat(),
            tarih=bas.isoformat(),
            tarih_metni=zamanlama.tarih_yaz(bas) if bas == bit else f"{zamanlama.tarih_yaz(bas)} – {zamanlama.tarih_yaz(bit)}",
            bugun=bugun.isoformat(),
            tahtalar=tahtalar,
            tahta_id=tahta_id,
            ders_nolari=nolar,
            ders_no=ders_no,
            secili_ders=secili_ders,
            saklama_metni=saklama_metni,
        )

    @uygulama.post("/program/uyarilar/{uyari_id}/goruldu")
    async def uyari_goruldu(istek: Request, uyari_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        with vt.islem() as b:
            satir = b.execute("SELECT * FROM bos_ders_uyari WHERE id = ?", (uyari_id,)).fetchone()
            if not satir:
                return y.yonlendir("/program/uyarilar", "Uyarı bulunamadı.", hata=True)
            if satir["goruldu_zaman"] is None:
                b.execute(
                    "UPDATE bos_ders_uyari SET goruldu_kullanici = ?, goruldu_zaman = ? WHERE id = ?",
                    (k["ad"], vt.simdi(), uyari_id),
                )
                # Tahta ve ders bilgisi kayda yazılmaz (uyarılar öğretim yılı sonunda silinir; kayıt kalır).
                vt.kayit_dus(b, k["ad"], "Boş ders uyarısı görüldü", f"#{uyari_id}", y.istemci_ip(istek))
        tarih = date.fromisoformat(satir["tarih"]).strftime("%d.%m.%Y")
        return y.yonlendir(f"/program/uyarilar?tarih={tarih}", "Görüldü olarak işaretlendi.")
