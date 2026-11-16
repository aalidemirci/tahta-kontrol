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

from . import guvenlik, hedef, metin, program, program_is, vt, zamanlama

gunluk = logging.getLogger("tahta-sunucu")
ISTANBUL = program.ISTANBUL
BOLUMLER = ("zil", "derslik", "kurallar", "istisnalar")
ELLE_VARSAYILAN = {"devre_adi": "Normal", "ilk_ders": "08:20", "ders_sayisi": 8, "ders_dk": 40, "teneffus_dk": 10,
                   "ogle_sonra": 4, "ogle_dk": 45, "gunler": [0, 1, 2, 3, 4]}  # fmt: skip


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
        ders = program.simdiki_ders(b, tahta, simdi) if saatler else None
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


def kaydet(uygulama, y) -> None:
    def yetkisiz(istek: Request, k, islem: str, donus: str = "/program"):
        """Yönetici değilse kayda düşürüp reddeder; yöneticiyse None."""
        if not k:
            return y.yonlendir("/giris")
        if k["rol"] != "yonetici":
            with vt.islem() as b:
                vt.kayit_dus(b, k["ad"], "Yetkisiz işlem reddedildi", islem, y.istemci_ip(istek))
            return y.yonlendir(donus, "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        return None

    def onizleme_yaz(b, tur: str, veri: dict, k) -> str:
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

    def uyandir_hepsi(idler) -> None:
        y.uyandir_hepsi(idler)

    # ---- sayfa -----------------------------------------------------------------------------
    @uygulama.get("/program", response_class=HTMLResponse)
    async def program_sayfasi(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
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
        derslik_tahtalari = [
            {"id": t["id"], "ad": t["ad"], "derslik": t["derslik"], "dersli": sayilar.get(t["id"], [0, 0])[0],
             "toplam": len(saatler), "muaf": bool(t["program_muaf"]), "programli": sayilar.get(t["id"], [0, 0])[0] > 0}  # fmt: skip
            for t in tahta_satirlari
        ]
        return y.sayfa(
            istek,
            "program.html",
            k,
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
            },
            elle=ELLE_VARSAYILAN,
            onizleme=onizleme,
            derslik={
                "tahtalar": derslik_tahtalari,
                "yetim_sayisi": sum(1 for v in sayilar.values() if v[1]),
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
            b.execute("DELETE FROM ders_saati")
            for gun, devre, devre_adi, no, bas, bit in veri["dersler"]:
                b.execute(
                    "INSERT INTO ders_saati (gun, devre, devre_adi, ders_no, baslangic, bitis) VALUES (?, ?, ?, ?, ?, ?)",
                    (gun, devre, devre_adi, no, bas, bit),
                )
            vt.ayar_yaz(b, "zil_takvimi", veri["takvim"])
            vt.ayar_yaz(b, "zil_kaynagi", {**veri["kaynak"], "yukleme": vt.simdi(), "yukleyen": k["ad"], "duzenlendi": False})
            vt.ayar_yaz(b, "program_onizleme", None)
            vt.kayit_dus(
                b, k["ad"], "Zil saatleri kaydedildi",
                f"Okul Zili · {len(veri['dersler'])} ders saati · {len(veri['takvim'].get('kurallar') or [])} tarih kuralı",
                y.istemci_ip(istek),
            )  # fmt: skip
        return y.yonlendir(donus, "Zil saatleri kaydedildi.")

    @uygulama.post("/program/zil/elle")
    async def zil_elle(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Zil saatleri elle giriş")
        if engel:
            return engel
        form = await istek.form()
        donus = "/program?bolum=zil"
        eylem = str(form.get("eylem", ""))
        with vt.islem() as b:
            saatler = program.ders_saatleri_oku(b)
            if eylem == "uret":
                try:
                    yeni = program.elle_uret({**{a: form.get(a) for a in ELLE_VARSAYILAN if a != "gunler"},
                                              "gunler": form.getlist("gunler")})  # fmt: skip
                except ValueError as hata:
                    return y.yonlendir(donus, str(hata), hata=True)
                devre = yeni[0][1]
                gunler = sorted({s[0] for s in yeni})
                kalan = [s for s in saatler if not (s[1] == devre and s[0] in gunler)]
                ayrinti = f"{yeni[0][2]} · {len({s[3] for s in yeni})} ders · {', '.join(zamanlama.GUN_KISA[g] for g in gunler)}"
                islem_adi = "Zil saatleri elle üretildi"
            elif eylem == "kaydet":
                kalan, yeni = [], []
                for gun, devre, devre_adi, no, bas, bit in saatler:
                    anahtar = f"s_{gun}_{devre}_{no}"
                    yb = program.saat_dogrula(form.get(f"{anahtar}_bas", bas))
                    ys = program.saat_dogrula(form.get(f"{anahtar}_bit", bit))
                    if not yb or not ys:
                        return y.yonlendir(donus, f"{program.GUN_ADLARI[gun]} {no}. ders: saat SS:DD biçiminde olmalı.", hata=True)
                    if program.dk(ys) <= program.dk(yb):
                        return y.yonlendir(donus, f"{program.GUN_ADLARI[gun]} {no}. ders: bitiş başlangıçtan sonra olmalı.", hata=True)
                    yeni.append((gun, devre, devre_adi, no, yb, ys))
                gunler = []
                ayrinti = f"{len(yeni)} ders saati"
                islem_adi = "Zil saatleri elle düzenlendi"
            else:
                return y.yonlendir(donus, "Bilinmeyen işlem.", hata=True)
            hatalar: list[str] = []
            program.dogrula(kalan + yeni, hatalar, [])
            if hatalar:
                return y.yonlendir(donus, hatalar[0], hata=True)
            if eylem == "uret":
                for gun in gunler:
                    b.execute("DELETE FROM ders_saati WHERE gun = ? AND devre = ?", (gun, devre))
            else:
                b.execute("DELETE FROM ders_saati")
            for s in yeni:
                b.execute(
                    "INSERT INTO ders_saati (gun, devre, devre_adi, ders_no, baslangic, bitis) VALUES (?, ?, ?, ?, ?, ?)", s
                )
            kaynak = vt.ayar_al(b, "zil_kaynagi")
            if isinstance(kaynak, dict) and kaynak.get("tur") == "okulzili":
                kaynak["duzenlendi"] = True
            else:
                kaynak = {"tur": "elle", "dosya_ozet": "", "dosya_yolu": "", "dosya_zamani": None,
                          "yukleme": vt.simdi(), "yukleyen": k["ad"], "duzenlendi": False}  # fmt: skip
            vt.ayar_yaz(b, "zil_kaynagi", kaynak)
            vt.kayit_dus(b, k["ad"], islem_adi, ayrinti, y.istemci_ip(istek))
        return y.yonlendir(donus, "Zil saatleri kaydedildi.")

    @uygulama.post("/program/zil/sil")
    async def zil_sil(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Zil saatleri silme")
        if engel:
            return engel
        with vt.islem() as b:
            b.execute("DELETE FROM ders_saati")
            vt.ayar_yaz(b, "zil_takvimi", None)
            vt.ayar_yaz(b, "zil_kaynagi", None)
            kural = program.ayar_kilit(b)
            kural["etkin"] = False  # programsız kilit olmaz (K30)
            vt.ayar_yaz(b, "program_kilidi", kural)
            uyandir = program_is.askiya_alma_acmasi(b, None, k["ad"])
            vt.kayit_dus(b, k["ad"], "Zil saatleri silindi", "Program kilidi kapatıldı.", y.istemci_ip(istek))
        uyandir_hepsi(uyandir)
        return y.yonlendir("/program?bolum=zil", "Zil saatleri silindi; program kilidi kapatıldı.")

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

    @uygulama.post("/program/derslik/yukle")
    async def derslik_yukle(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Derslik programı yükleme")
        if engel:
            return engel
        donus = "/program?bolum=derslik"
        uzunluk = govde_uzunlugu(istek)
        if uzunluk is None:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        if uzunluk > program.CSV_EN_COK_BAYT + 64 * 1024:
            return y.yonlendir(donus, "Dosya en çok 1 MB olabilir.", hata=True)
        try:
            form = await istek.form(max_files=1, max_fields=5)
        except Exception:
            return y.yonlendir(donus, "Dosya okunamadı ya da 1 MB'tan büyük.", hata=True)
        try:
            dosya = form.get("dosya")
            if not isinstance(dosya, UploadFile) or not dosya.filename:
                return y.yonlendir(donus, "CSV dosyası seçilmedi.", hata=True)
            bayt = await dosya.read(program.CSV_EN_COK_BAYT + 1)
        finally:
            await form.close()
        if not bayt.strip():
            return y.yonlendir(donus, "CSV dosyası boş.", hata=True)
        with vt.islem() as b:
            tahtalar = [dict(t) for t in b.execute("SELECT id, ad, derslik FROM tahta WHERE durum != 'iptal'")]
            try:
                cozum = program.derslik_csv_oku(bayt, program.ders_saatleri_oku(b), tahtalar)
            except ValueError as hata:
                return y.yonlendir(donus, str(hata), hata=True)
            onizleme_yaz(b, "derslik", {**cozum, "tahtalar": {str(a): v for a, v in cozum["tahtalar"].items()}}, k)
            vt.kayit_dus(
                b, k["ad"], "Derslik programı önizlendi",
                f"{len(cozum['eslesen'])} tahta eşleşti, {len(cozum['eslesmeyen'])} derslik eşleşmedi, {cozum['hata_sayisi']} hatalı satır",
                y.istemci_ip(istek),
            )  # fmt: skip
        return y.yonlendir("/program?bolum=derslik&onizleme=1")

    @uygulama.post("/program/derslik/onayla")
    async def derslik_onayla(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Derslik programı onaylama")
        if engel:
            return engel
        form = await istek.form()
        donus = "/program?bolum=derslik"
        with vt.islem() as b:
            kayit = onizleme_al(b, "derslik", str(form.get("onizleme", "")), k)
            if form.get("eylem") == "vazgec":
                if kayit:
                    vt.ayar_yaz(b, "program_onizleme", None)
                return y.yonlendir(donus, "Önizleme kapatıldı; derslik programları değişmedi.")
            if not kayit:
                return y.yonlendir(donus, "Önizlemenin süresi geçmiş ya da başka bir kullanıcıya ait. Dosyayı yeniden yükleyin.", hata=True)
            gecerli = {t["id"] for t in b.execute("SELECT id FROM tahta WHERE durum != 'iptal'")}
            sayi = 0
            for tahta_id, satirlar in kayit["veri"]["tahtalar"].items():
                tahta_id = int(tahta_id)
                if tahta_id not in gecerli:
                    continue
                sayi += 1
                b.execute("DELETE FROM tahta_ders WHERE tahta_id = ?", (tahta_id,))
                for gun, devre, no, sube in satirlar:
                    b.execute(
                        "INSERT OR REPLACE INTO tahta_ders (tahta_id, gun, devre, ders_no, sube) VALUES (?, ?, ?, ?, ?)",
                        (tahta_id, gun, devre, no, sube),
                    )
            vt.ayar_yaz(b, "program_onizleme", None)
            vt.kayit_dus(b, k["ad"], "Derslik programı içe aktarıldı", f"{sayi} tahta", y.istemci_ip(istek))
        return y.yonlendir(donus, f"Derslik programı {sayi} tahtaya uygulandı.")

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
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        bugun = simdi_dt().date()
        try:
            gun = zamanlama.tarih_coz(istek.query_params.get("tarih") or bugun.isoformat())
        except ValueError:
            gun = bugun
        if not bugun - timedelta(days=program.UYARI_SAKLAMA_GUN) <= gun <= bugun:
            gun = bugun
        with vt.islem() as b:
            satirlar = b.execute(
                "SELECT u.*, t.ad AS tahta_ad, t.derslik AS derslik, "
                "(SELECT sube FROM tahta_ders d WHERE d.tahta_id = u.tahta_id AND d.devre = u.devre AND d.ders_no = u.ders_no "
                " AND d.gun = ?) AS sube, "
                "(SELECT devre_adi FROM ders_saati s WHERE s.devre = u.devre LIMIT 1) AS devre_adi "
                "FROM bos_ders_uyari u JOIN tahta t ON t.id = u.tahta_id WHERE u.tarih = ? ORDER BY u.ders_bas, t.ad",
                (gun.weekday(), gun.isoformat()),
            ).fetchall()
            cok_devre = b.execute("SELECT COUNT(DISTINCT devre) FROM ders_saati").fetchone()[0] > 1
            serit = program_is.program_ozeti(b, simdi_dt())
        liste = []
        for s in satirlar:
            ders = f"{s['ders_no']}. ders"
            if cok_devre and s["devre_adi"]:
                ders = f"{s['devre_adi']} · {ders}"
            if s["sube"]:
                ders += f" · {s['sube']}"
            liste.append(
                {
                    "id": s["id"],
                    "saat": datetime.fromtimestamp(s["ders_bas"], ISTANBUL).strftime("%H:%M"),
                    "tahta_id": s["tahta_id"],
                    "tahta": s["tahta_ad"],
                    "derslik": s["derslik"],
                    "ders": ders,
                    "durum": program.BOS_NEDENLERI.get(s["neden"], s["neden"]),
                    "neden": s["neden"],
                    "sonuc": (
                        f"{program.saat_eki(datetime.fromtimestamp(s['cozulme'], ISTANBUL).strftime('%H:%M'))}"
                        " kullanılmaya başlandı"
                        if s["cozulme"] else "Ders boyunca boş"
                    ),
                    "goruldu": (
                        f"{s['goruldu_kullanici']} · {datetime.fromtimestamp(s['goruldu_zaman'], ISTANBUL):%H:%M}"
                        if s["goruldu_zaman"] else None
                    ),
                }
            )  # fmt: skip
        return y.sayfa(
            istek,
            "uyarilar.html",
            k,
            uyarilar=liste,
            serit=serit,
            bolum="uyarilar",
            tarih=gun.isoformat(),
            tarih_metni=zamanlama.tarih_yaz(gun),
            en_eski=(bugun - timedelta(days=program.UYARI_SAKLAMA_GUN)).isoformat(),
            bugun=bugun.isoformat(),
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
                # Tahta ve ders bilgisi kayda yazılmaz (uyarılar 30 gün sonra silinir; kayıt kalır).
                vt.kayit_dus(b, k["ad"], "Boş ders uyarısı görüldü", f"#{uyari_id}", y.istemci_ip(istek))
        tarih = date.fromisoformat(satir["tarih"]).strftime("%d.%m.%Y")
        return y.yonlendir(f"/program/uyarilar?tarih={tarih}", "Görüldü olarak işaretlendi.")
