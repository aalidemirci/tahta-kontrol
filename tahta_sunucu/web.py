"""Web uygulaması: idare paneli ve tahta ajanlarının konuştuğu arayüz.

Panel uçları oturum çerezi ister; /ajan/* uçları tahtanın kimliği ve anahtarıyla
çalışır. Sunucudan tahtaya bağlantı açılmaz: ajan "uzun bekleme" isteği atar,
komut gelince istek hemen yanıtlanır.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.datastructures import UploadFile

from . import __version__, ayar, guvenlik, marka, paket, tema, vt, wol

ISTANBUL = ZoneInfo("Europe/Istanbul")
CEREZ = "tk_oturum"
ROLLER = {"yonetici": "Yönetici", "idareci": "İdareci"}

# Komutun geçerlilik süresi (sn). Kapatma komutu kısa ömürlüdür: bir saat sonra
# açılan tahta, eskimiş bir "kapat" komutuyla kapanmamalıdır.
KOMUT_OMRU = {
    "kilitle": 600,
    "kilit_ac": 600,
    "duyuru_kaldir": 600,
    "kapat": 120,
    "yeniden_baslat": 120,
    "tani": 86400,
    "guncelle": 86400,
}
KOMUT_ADI = {
    "kilitle": "Kilitle",
    "kilit_ac": "Kilidi aç",
    "duyuru": "Duyuru",
    "duyuru_kaldir": "Duyuruyu kaldır",
    "kapat": "Kapat",
    "yeniden_baslat": "Yeniden başlat",
    "tani": "Tanılama",
    "guncelle": "Ajanı güncelle",
    "uyandir": "Uzaktan aç",
}
KOMUT_DURUMU = {
    "bekliyor": "Tahta bekleniyor",
    "gonderildi": "Tahtaya iletildi",
    "tamam": "Uygulandı",
    "hata": "Başarısız",
    "zaman_asimi": "Süresi doldu",
}
OTURUM_SINIFI = {
    "etapadmin": "Yönetici hesabı (etapadmin)",
    "ogretmen": "Öğretmen hesabı (ortak)",
    "ogrenci": "Öğrenci hesabı (sınırlı)",
    "kisisel": "Kişisel hesap",
    "yok": "Oturum açık değil",
    "windows": "Windows oturumu",
}

# İçerik güvenlik politikası: satır içi betik/stil yok, dış kaynak yok.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; "
    "font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)
UZUN_ONBELLEK = "public, max-age=31536000, immutable"


def zaman_yaz(epoch) -> str:
    if not epoch:
        return "—"
    return datetime.fromtimestamp(int(epoch), ISTANBUL).strftime("%d.%m.%Y %H:%M:%S")


def gecen_sure(epoch) -> str:
    if not epoch:
        return "hiç bağlanmadı"
    fark = max(0, int(time.time()) - int(epoch))
    if fark < 90:
        return "şimdi"
    if fark < 3600:
        return f"{fark // 60} dk önce"
    if fark < 86400:
        return f"{fark // 3600} sa önce"
    return f"{fark // 86400} gün önce"


def uygulama_olustur(parmak_izi: str = "") -> FastAPI:
    vt.hazirla()
    uygulama = FastAPI(title="Tahta Kontrol", docs_url=None, redoc_url=None, openapi_url=None)
    uygulama.mount("/statik", StaticFiles(directory=ayar.SUNUCU_DIZINI / "statik"), name="statik")
    sablonlar = Jinja2Templates(directory=ayar.SUNUCU_DIZINI / "sablonlar")
    sablonlar.env.filters["zaman"] = zaman_yaz
    sablonlar.env.filters["gecen"] = gecen_sure
    sablonlar.env.globals.update(
        surum=__version__, komut_adi=KOMUT_ADI, komut_durumu=KOMUT_DURUMU, roller=ROLLER, oturum_sinifi=OTURUM_SINIFI
    )

    bekleyenler: dict[int, tuple[asyncio.AbstractEventLoop, asyncio.Event]] = {}
    kayit_denemeleri: dict[str, list[float]] = defaultdict(list)
    giris_denemeleri: dict[str, list[float]] = defaultdict(list)

    # ---- yardımcılar ---------------------------------------------------------
    def istemci_ip(istek: Request) -> str:
        return istek.client.host if istek.client else ""

    def yerel_mi(istek: Request) -> bool:
        return istemci_ip(istek) in ("127.0.0.1", "::1")

    def kullanici(istek: Request):
        belirtec = istek.cookies.get(CEREZ)
        if not belirtec:
            return None
        with vt.islem() as b:
            return b.execute(
                "SELECT k.* FROM oturum o JOIN kullanici k ON k.id = o.kullanici_id "
                "WHERE o.belirtec_ozet = ? AND o.bitis > ? AND k.aktif = 1",
                (guvenlik.ozet(belirtec), vt.simdi()),
            ).fetchone()

    def yonlendir(adres: str, mesaj: str = "", hata: bool = False) -> RedirectResponse:
        """İleti ?m= ile taşınır; hata=True ise bant hata görünümünde ve role="alert" ile çizilir."""
        if mesaj:
            from urllib.parse import quote

            adres, isaret, parca = adres.partition("#")  # ileti parçadan (#…) önce gelmeli
            tur = "&t=hata" if hata else ""
            adres += ("&" if "?" in adres else "?") + "m=" + quote(mesaj) + tur + isaret + parca
        return RedirectResponse(adres, status_code=303)

    def sayfa(istek: Request, ad: str, k, **baglam) -> HTMLResponse:
        with vt.islem() as b:
            okul_adi = vt.ayar_al(b, "okul_adi", "")
            ana, vurgu = tema.tema_al(b)
            logo_v = marka.logo_surumu(b)
        baglam.update(
            kullanici=k,
            okul_adi=okul_adi,
            mesaj=istek.query_params.get("m", ""),
            mesaj_hata=istek.query_params.get("t") == "hata",
            ileti_yeri=istek.query_params.get("yer", ""),
            tema_v=tema.surum(ana, vurgu),
            tema_serit=tema.uret(ana, vurgu)["acik"]["serit"],
            logo_v=logo_v,
            monogram=tema.bas_harfler(okul_adi),
        )
        return sablonlar.TemplateResponse(istek, ad, baglam)

    def onayli_tahtalari_uyandir() -> None:
        with vt.islem() as b:
            idler = [s["id"] for s in b.execute("SELECT id FROM tahta WHERE durum = 'onayli'").fetchall()]
        for tahta_id in idler:
            uyandir(tahta_id)

    def hiz_siniri(kayit: dict[str, list[float]], anahtar: str, adet: int, pencere: int) -> bool:
        simdi = time.time()
        kayit[anahtar] = [z for z in kayit[anahtar] if simdi - z < pencere]
        if len(kayit[anahtar]) >= adet:
            return False
        kayit[anahtar].append(simdi)
        return True

    def sunucu_adresi(istek: Request) -> str:
        if istek.url.scheme == "https" and istek.headers.get("host"):
            return f"https://{istek.headers['host']}"
        with vt.islem() as b:
            kayitli = vt.ayar_al(b, "sunucu_adresi", "")
        if kayitli:
            return kayitli
        ipler = guvenlik.yerel_ipler()
        return f"https://{ipler[0] if ipler else '127.0.0.1'}:{ayar.HTTPS_PORT}"

    def uyandir(tahta_id: int) -> None:
        kayit = bekleyenler.get(tahta_id)
        if kayit:
            dongu, olay = kayit
            dongu.call_soon_threadsafe(olay.set)

    def komut_ekle(b, tahta_id: int, tur: str, veri: dict, olusturan: str, omur: int | None = None) -> None:
        simdi = vt.simdi()
        b.execute(
            "INSERT INTO komut (tahta_id, tur, veri_json, olusturan, olusturma, bitis) VALUES (?, ?, ?, ?, ?, ?)",
            (tahta_id, tur, json.dumps(veri, ensure_ascii=False), olusturan, simdi, simdi + (omur or KOMUT_OMRU[tur])),
        )

    def tahta_gorunumu(satir) -> dict:
        durum = json.loads(satir["durum_json"] or "{}")
        cevrimici = bool(satir["son_gorulme"]) and (vt.simdi() - satir["son_gorulme"]) < ayar.CEVRIMICI_ESIK_SN
        ekranlar = durum.get("ekranlar") or []
        oturum = (durum.get("oturum") or {}).get("sinif", "yok")
        return {
            "id": satir["id"],
            "ad": satir["ad"],
            "derslik": satir["derslik"],
            "durum": satir["durum"],
            "cevrimici": cevrimici,
            "kilitli": bool(durum.get("kilitli")) if cevrimici else None,
            "duyuru_var": bool(durum.get("duyuru_var")) if cevrimici else False,
            "ekran_bagli": any(e.get("arayuz") not in (None, "yok") for e in ekranlar),
            "oturum": OTURUM_SINIFI.get(oturum, oturum),
            "oturum_acik": cevrimici and oturum != "yok",
            "son_gorulme": gecen_sure(satir["son_gorulme"]),
            "surum": satir["surum"],
            "guncel": satir["surum"] == paket.ajan_paketi().surum,
            "ip": satir["ip"],
        }

    # ---- güvenlik katmanı ----------------------------------------------------
    @uygulama.middleware("http")
    async def kapilar(istek: Request, sonraki):
        yol = istek.url.path
        if istek.method == "POST" and not yol.startswith("/ajan/"):
            # Çerezle çalışan uçlara başka siteden istek attırılmasın.
            kaynak = istek.headers.get("origin")
            if kaynak and kaynak.split("://", 1)[-1] != istek.headers.get("host", ""):
                return JSONResponse({"hata": "Geçersiz istek kaynağı."}, status_code=403)
        yanit = await sonraki(istek)
        basliklar = yanit.headers
        basliklar["X-Content-Type-Options"] = "nosniff"
        basliklar["X-Frame-Options"] = "DENY"
        # no-referrer KULLANMA: tarayıcı form gönderiminde "Origin: null" yollar, kaynak denetimi reddeder.
        basliklar["Referrer-Policy"] = "same-origin"
        basliklar.setdefault("Content-Security-Policy", CSP)
        basliklar.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), usb=()")
        basliklar.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if not yol.startswith("/statik"):
            basliklar.setdefault("Cache-Control", "no-store")
        return yanit

    def kapatma_ozeti(kural: dict) -> str:
        parcalar = []
        if kural.get("etkin") and kural.get("saatler"):
            parcalar.append("hafta içi " + ", ".join(kural["saatler"]))
        if kural.get("hafta_sonu"):
            parcalar.append(f"hafta sonu {kural.get('hafta_sonu_dk', 60)} dakika açık kalınca")
        return " · ".join(parcalar)

    def kurulum_gerekli() -> bool:
        with vt.islem() as b:
            return b.execute("SELECT COUNT(*) FROM kullanici").fetchone()[0] == 0

    # ---- oturum --------------------------------------------------------------
    @uygulama.get("/saglik")
    async def saglik():
        return {"durum": "calisiyor", "surum": __version__}

    @uygulama.get("/kurulum", response_class=HTMLResponse)
    async def kurulum_formu(istek: Request):
        if not kurulum_gerekli():
            return yonlendir("/giris")
        return sayfa(istek, "kurulum.html", None, yerel=yerel_mi(istek))

    @uygulama.post("/kurulum")
    async def kurulum_kaydet(istek: Request):
        if not kurulum_gerekli():
            return yonlendir("/giris")
        if not yerel_mi(istek):
            return yonlendir("/kurulum", "İlk kurulum yalnız sunucunun kurulu olduğu bilgisayardan yapılabilir.", hata=True)
        form = await istek.form()
        ad = str(form.get("ad", "")).strip().lower()
        parola = str(form.get("parola", ""))
        if len(ad) < 3 or len(parola) < 8 or parola != str(form.get("parola2", "")):
            return yonlendir("/kurulum", "Kullanıcı adı en az 3, parola en az 8 karakter olmalı ve iki parola aynı girilmeli.", hata=True)
        with vt.islem() as b:
            b.execute(
                "INSERT INTO kullanici (ad, gorunen_ad, parola_ozet, rol, olusturma) VALUES (?, ?, ?, 'yonetici', ?)",
                (ad, str(form.get("gorunen_ad", "")).strip() or ad, guvenlik.parola_ozetle(parola), vt.simdi()),
            )
            vt.ayar_yaz(b, "okul_adi", str(form.get("okul_adi", "")).strip())
            vt.kayit_dus(b, ad, "İlk kurulum", "Yönetici hesabı oluşturuldu.", istemci_ip(istek))
        return yonlendir("/giris", "Kurulum tamamlandı. Giriş yapabilirsiniz.")

    @uygulama.get("/giris", response_class=HTMLResponse)
    async def giris_formu(istek: Request):
        if kurulum_gerekli():
            return yonlendir("/kurulum")
        return sayfa(istek, "giris.html", None)

    @uygulama.post("/giris")
    async def giris(istek: Request):
        form = await istek.form()
        ad = str(form.get("ad", "")).strip().lower()
        if not hiz_siniri(giris_denemeleri, istemci_ip(istek), 10, 300):
            return yonlendir("/giris", "Çok fazla deneme yapıldı. Birkaç dakika sonra yeniden deneyin.", hata=True)
        with vt.islem() as b:
            satir = b.execute("SELECT * FROM kullanici WHERE ad = ? AND aktif = 1", (ad,)).fetchone()
            if not satir or not guvenlik.parola_dogrula(str(form.get("parola", "")), satir["parola_ozet"]):
                vt.kayit_dus(b, ad or "?", "Başarısız giriş", "", istemci_ip(istek))
                basarili = False
            else:
                belirtec = guvenlik.belirtec()
                b.execute("DELETE FROM oturum WHERE bitis < ?", (vt.simdi(),))
                b.execute(
                    "INSERT INTO oturum (belirtec_ozet, kullanici_id, bitis) VALUES (?, ?, ?)",
                    (guvenlik.ozet(belirtec), satir["id"], vt.simdi() + ayar.OTURUM_SAAT * 3600),
                )
                vt.kayit_dus(b, ad, "Giriş", "", istemci_ip(istek))
                basarili = True
        if not basarili:
            return yonlendir("/giris", "Kullanıcı adı ya da parola hatalı.", hata=True)
        yanit = yonlendir("/")
        yanit.set_cookie(
            CEREZ,
            belirtec,
            max_age=ayar.OTURUM_SAAT * 3600,
            httponly=True,
            samesite="strict",
            secure=istek.url.scheme == "https",
        )
        return yanit

    @uygulama.post("/cikis")
    async def cikis(istek: Request):
        belirtec = istek.cookies.get(CEREZ)
        if belirtec:
            with vt.islem() as b:
                b.execute("DELETE FROM oturum WHERE belirtec_ozet = ?", (guvenlik.ozet(belirtec),))
        yanit = yonlendir("/giris")
        yanit.delete_cookie(CEREZ)
        return yanit

    # ---- pano ----------------------------------------------------------------
    @uygulama.get("/", response_class=HTMLResponse)
    async def pano(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/kurulum" if kurulum_gerekli() else "/giris")
        with vt.islem() as b:
            satirlar = b.execute(
                "SELECT * FROM tahta WHERE durum != 'iptal' ORDER BY derslik COLLATE NOCASE, ad COLLATE NOCASE"
            ).fetchall()
            kilit_kodu_var = bool(vt.ayar_al(b, "kilit_kodu"))
            kapatma = kapatma_ozeti(vt.ayar_al(b, "otomatik_kapatma") or {})
        tahtalar = [tahta_gorunumu(s) for s in satirlar]
        return sayfa(
            istek,
            "pano.html",
            k,
            onayli=[t for t in tahtalar if t["durum"] == "onayli"],
            bekleyen=[t for t in tahtalar if t["durum"] == "bekliyor"],
            kilit_kodu_var=kilit_kodu_var,
            kapatma=kapatma,
        )

    @uygulama.get("/api/durum")
    async def api_durum(istek: Request):
        if not kullanici(istek):
            return JSONResponse({"hata": "Oturum gerekli."}, status_code=401)
        with vt.islem() as b:
            satirlar = b.execute("SELECT * FROM tahta WHERE durum = 'onayli'").fetchall()
            bekleyen = b.execute("SELECT COUNT(*) FROM tahta WHERE durum = 'bekliyor'").fetchone()[0]
        return {"tahtalar": [tahta_gorunumu(s) for s in satirlar], "bekleyen": bekleyen}

    @uygulama.post("/islem")
    async def islem(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        form = await istek.form()
        tur = str(form.get("tur", ""))
        idler = [int(d) for d in form.getlist("tahta") if str(d).isdigit()]
        if not idler:
            return yonlendir("/", "Önce en az bir tahta seçin.", hata=True)
        if tur not in KOMUT_ADI:
            return yonlendir("/", "Bilinmeyen işlem.", hata=True)
        veri: dict = {}
        omur = None
        if tur == "duyuru":
            metin = str(form.get("metin", "")).strip()
            if not metin:
                return yonlendir("/", "Duyuru metni boş olamaz.", hata=True)
            try:
                sure_dk = max(1, min(240, int(str(form.get("sure_dk", "5")))))
            except ValueError:
                sure_dk = 5
            veri = {
                "baslik": str(form.get("baslik", "")).strip()[:200],
                "metin": metin[:4000],
                "sure_sn": sure_dk * 60,
                "kapatilabilir": form.get("kapatilabilir") == "1",
                "bitis_sunucu": vt.simdi() + sure_dk * 60,
            }
            omur = sure_dk * 60
        if tur == "guncelle":
            veri = {"sha256": paket.ajan_paketi().sha256, "surum": paket.ajan_paketi().surum}
        notlar = []
        with vt.islem() as b:
            isaret = ",".join("?" * len(idler))
            tahtalar = b.execute(
                f"SELECT * FROM tahta WHERE durum = 'onayli' AND id IN ({isaret})", idler
            ).fetchall()
            if not tahtalar:
                return yonlendir("/", "Seçilen tahtalar bulunamadı.", hata=True)
            adlar = ", ".join(t["ad"] for t in tahtalar)
            if tur == "uyandir":
                for t in tahtalar:
                    if not t["mac"]:
                        notlar.append(f"{t['ad']}: MAC adresi bilinmiyor")
                        continue
                    try:
                        wol.gonder(t["mac"], t["ip"])
                    except (ValueError, OSError) as hata:
                        notlar.append(f"{t['ad']}: {hata}")
            else:
                for t in tahtalar:
                    komut_ekle(b, t["id"], tur, veri, k["ad"], omur)
                if tur == "duyuru":
                    b.execute(
                        "INSERT INTO duyuru (baslik, metin, sure_sn, kapatilabilir, hedef, olusturan, olusturma) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (veri["baslik"], veri["metin"], veri["sure_sn"], int(veri["kapatilabilir"]), adlar, k["ad"], vt.simdi()),
                    )
            vt.kayit_dus(b, k["ad"], KOMUT_ADI[tur], f"{len(tahtalar)} tahta: {adlar}", istemci_ip(istek))
        for t in tahtalar:
            uyandir(t["id"])
        mesaj = f"{KOMUT_ADI[tur]}: {len(tahtalar)} tahtaya gönderildi."
        if tur == "uyandir":
            mesaj = f"Uzaktan açma paketi {len(tahtalar) - len(notlar)} tahtaya gönderildi. Tahtanın açılıp açılmadığını panodan izleyin."
        if notlar:
            mesaj += " " + "; ".join(notlar)
        return yonlendir(str(form.get("donus", "/")) if str(form.get("donus", "/")).startswith("/") else "/", mesaj)

    # ---- tahta ayrıntısı -----------------------------------------------------
    @uygulama.get("/tahta/{tahta_id}", response_class=HTMLResponse)
    async def tahta_sayfasi(istek: Request, tahta_id: int):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        with vt.islem() as b:
            satir = b.execute("SELECT * FROM tahta WHERE id = ? AND durum != 'iptal'", (tahta_id,)).fetchone()
            if not satir:
                return yonlendir("/", "Tahta bulunamadı.", hata=True)
            komutlar = b.execute(
                "SELECT * FROM komut WHERE tahta_id = ? ORDER BY id DESC LIMIT 30", (tahta_id,)
            ).fetchall()
        tani = json.loads(satir["tani_json"]) if satir["tani_json"] else None
        durum = json.loads(satir["durum_json"] or "{}")
        return sayfa(
            istek, "tahta.html", k, t=tahta_gorunumu(satir), ham=satir, komutlar=komutlar, tani=tani, durum=durum
        )

    @uygulama.post("/tahta/{tahta_id}/kaydet")
    async def tahta_kaydet(istek: Request, tahta_id: int):
        k = kullanici(istek)
        if not k or k["rol"] != "yonetici":
            return yonlendir(f"/tahta/{tahta_id}", "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        form = await istek.form()
        ad = str(form.get("ad", "")).strip()[:60]
        eylem = str(form.get("eylem", "kaydet"))
        with vt.islem() as b:
            satir = b.execute("SELECT * FROM tahta WHERE id = ?", (tahta_id,)).fetchone()
            if not satir:
                return yonlendir("/", "Tahta bulunamadı.", hata=True)
            if eylem == "sil":
                b.execute("UPDATE tahta SET durum = 'iptal', anahtar_ozet = '' WHERE id = ?", (tahta_id,))
                vt.kayit_dus(b, k["ad"], "Tahta kaldırıldı", satir["ad"], istemci_ip(istek))
                return yonlendir("/", f"{satir['ad']} kaldırıldı. Tahtadaki ajan artık sunucuya bağlanamaz.")
            if not ad:
                return yonlendir(f"/tahta/{tahta_id}", "Tahta adı boş olamaz.", hata=True)
            yeni_durum = "onayli" if eylem == "onayla" else satir["durum"]
            b.execute(
                "UPDATE tahta SET ad = ?, derslik = ?, durum = ? WHERE id = ?",
                (ad, str(form.get("derslik", "")).strip()[:60], yeni_durum, tahta_id),
            )
            vt.kayit_dus(
                b, k["ad"], "Tahta onaylandı" if eylem == "onayla" else "Tahta düzenlendi", ad, istemci_ip(istek)
            )
        uyandir(tahta_id)
        return yonlendir(f"/tahta/{tahta_id}", "Kaydedildi.")

    # ---- tahta ekleme --------------------------------------------------------
    @uygulama.get("/ekle", response_class=HTMLResponse)
    async def ekle(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        with vt.islem() as b:
            pencere = vt.ayar_al(b, "kayit_penceresi") or {}
        acik = bool(pencere) and pencere.get("bitis", 0) > vt.simdi()
        return sayfa(
            istek,
            "ekle.html",
            k,
            acik=acik,
            kod=pencere.get("kod") if acik else "",
            bitis=pencere.get("bitis") if acik else None,
            adres=sunucu_adresi(istek),
            parmak_izi=parmak_izi,
            paket=paket.ajan_paketi(),
        )

    @uygulama.post("/ekle")
    async def ekle_ayarla(istek: Request):
        k = kullanici(istek)
        if not k or k["rol"] != "yonetici":
            return yonlendir("/ekle", "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        form = await istek.form()
        with vt.islem() as b:
            if form.get("eylem") == "kapat":
                vt.ayar_yaz(b, "kayit_penceresi", {})
                vt.kayit_dus(b, k["ad"], "Tahta ekleme kapatıldı", "", istemci_ip(istek))
                return yonlendir("/ekle", "Tahta ekleme kapatıldı.")
            vt.ayar_yaz(
                b,
                "kayit_penceresi",
                {"kod": guvenlik.kayit_kodu(), "bitis": vt.simdi() + ayar.KAYIT_PENCERESI_DK * 60},
            )
            vt.kayit_dus(b, k["ad"], "Tahta ekleme açıldı", f"{ayar.KAYIT_PENCERESI_DK} dakika", istemci_ip(istek))
        return yonlendir("/ekle", "Tahta ekleme açıldı; yeni eşleştirme kodu üretildi.")

    @uygulama.get("/kur")
    async def kur_betigi(istek: Request):
        icerik = paket.kurulum_betigi(sunucu_adresi(istek), parmak_izi)
        return Response(
            icerik,
            media_type="application/x-sh",
            headers={"Content-Disposition": 'attachment; filename="tahta-kur.sh"'},
        )

    @uygulama.get("/kur/paket")
    async def kur_paketi():
        p = paket.ajan_paketi()
        return Response(
            p.icerik,
            media_type="application/vnd.debian.binary-package",
            headers={"Content-Disposition": f'attachment; filename="{p.dosya_adi}"', "X-Sha256": p.sha256},
        )

    @uygulama.get("/kur/usb.zip")
    async def kur_usb(istek: Request):
        if not kullanici(istek):
            return yonlendir("/giris")
        return Response(
            paket.usb_paketi(sunucu_adresi(istek), parmak_izi),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="tahta-kurulum.zip"'},
        )

    # ---- duyurular, kayıt, kullanıcılar, ayarlar -----------------------------
    @uygulama.get("/duyurular", response_class=HTMLResponse)
    async def duyurular(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        with vt.islem() as b:
            satirlar = b.execute("SELECT * FROM duyuru ORDER BY id DESC LIMIT 100").fetchall()
        return sayfa(istek, "duyurular.html", k, duyurular=satirlar)

    @uygulama.get("/kayit", response_class=HTMLResponse)
    async def kayit(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        with vt.islem() as b:
            satirlar = b.execute("SELECT * FROM kayit ORDER BY id DESC LIMIT 300").fetchall()
        return sayfa(istek, "kayit.html", k, kayitlar=satirlar)

    @uygulama.get("/kullanicilar", response_class=HTMLResponse)
    async def kullanicilar(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        if k["rol"] != "yonetici":
            return yonlendir("/", "Bu sayfa için yönetici yetkisi gerekir.", hata=True)
        with vt.islem() as b:
            satirlar = b.execute("SELECT * FROM kullanici ORDER BY ad").fetchall()
        return sayfa(istek, "kullanicilar.html", k, kullanicilar=satirlar)

    @uygulama.post("/kullanicilar")
    async def kullanici_islem(istek: Request):
        k = kullanici(istek)
        if not k or k["rol"] != "yonetici":
            return yonlendir("/", "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        form = await istek.form()
        eylem = str(form.get("eylem", ""))
        with vt.islem() as b:
            if eylem == "ekle":
                ad = str(form.get("ad", "")).strip().lower()
                parola = str(form.get("parola", ""))
                rol = str(form.get("rol", "idareci"))
                if len(ad) < 3 or len(parola) < 8 or rol not in ROLLER:
                    return yonlendir("/kullanicilar", "Kullanıcı adı en az 3, parola en az 8 karakter olmalı.", hata=True)
                if b.execute("SELECT 1 FROM kullanici WHERE ad = ?", (ad,)).fetchone():
                    return yonlendir("/kullanicilar", "Bu kullanıcı adı zaten var.", hata=True)
                b.execute(
                    "INSERT INTO kullanici (ad, gorunen_ad, parola_ozet, rol, olusturma) VALUES (?, ?, ?, ?, ?)",
                    (ad, str(form.get("gorunen_ad", "")).strip() or ad, guvenlik.parola_ozetle(parola), rol, vt.simdi()),
                )
                vt.kayit_dus(b, k["ad"], "Kullanıcı eklendi", f"{ad} ({ROLLER[rol]})", istemci_ip(istek))
                return yonlendir("/kullanicilar", "Kullanıcı eklendi.")
            hedef = b.execute("SELECT * FROM kullanici WHERE id = ?", (str(form.get("id", "")),)).fetchone()
            if not hedef:
                return yonlendir("/kullanicilar", "Kullanıcı bulunamadı.", hata=True)
            if eylem == "durum":
                if hedef["id"] == k["id"]:
                    return yonlendir("/kullanicilar", "Kendi hesabınızı kapatamazsınız.", hata=True)
                b.execute("UPDATE kullanici SET aktif = ? WHERE id = ?", (0 if hedef["aktif"] else 1, hedef["id"]))
                b.execute("DELETE FROM oturum WHERE kullanici_id = ?", (hedef["id"],))
                vt.kayit_dus(
                    b, k["ad"], "Kullanıcı kapatıldı" if hedef["aktif"] else "Kullanıcı açıldı", hedef["ad"], istemci_ip(istek)
                )
            elif eylem == "parola":
                parola = str(form.get("parola", ""))
                if len(parola) < 8:
                    return yonlendir("/kullanicilar", "Parola en az 8 karakter olmalı.", hata=True)
                b.execute(
                    "UPDATE kullanici SET parola_ozet = ? WHERE id = ?", (guvenlik.parola_ozetle(parola), hedef["id"])
                )
                if hedef["id"] != k["id"]:
                    b.execute("DELETE FROM oturum WHERE kullanici_id = ?", (hedef["id"],))
                vt.kayit_dus(b, k["ad"], "Parola değiştirildi", hedef["ad"], istemci_ip(istek))
        return yonlendir("/kullanicilar", "Kaydedildi.")

    @uygulama.get("/ayarlar", response_class=HTMLResponse)
    async def ayarlar(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        if k["rol"] != "yonetici":
            return yonlendir("/", "Bu sayfa için yönetici yetkisi gerekir.", hata=True)
        with vt.islem() as b:
            kilit_kodu_var = bool(vt.ayar_al(b, "kilit_kodu"))
            kayitli_adres = vt.ayar_al(b, "sunucu_adresi", "")
            kapatma = vt.ayar_al(b, "otomatik_kapatma") or {}
            ana, vurgu = tema.tema_al(b)
            logo = marka.logo_oku(b)
        uretilen = tema.uret(ana, vurgu)
        logo_bilgi = None
        if logo:
            bilgi = logo[1]
            logo_bilgi = {
                "tur": "PNG" if bilgi.get("tur") == "png" else "JPEG",
                "en": bilgi.get("en"),
                "boy": bilgi.get("boy"),
                "kb": max(1, round(int(bilgi.get("boyut") or 0) / 1024)),
                "zaman": datetime.fromtimestamp(int(bilgi.get("zaman") or 0), ISTANBUL).strftime("%d.%m.%Y %H:%M"),
            }
        return sayfa(
            istek,
            "ayarlar.html",
            k,
            tema_ana=ana,
            tema_vurgu=vurgu,
            varsayilan_vurgu=tema.VARSAYILAN_VURGU,
            tema_notlar=uretilen["notlar"],
            tema_rapor=uretilen["rapor"],
            logo=logo_bilgi,
            kilit_kodu_var=kilit_kodu_var,
            kayitli_adres=kayitli_adres,
            kapatma=kapatma,
            ipler=guvenlik.yerel_ipler(),
            https_port=ayar.HTTPS_PORT,
            parmak_izi=parmak_izi,
            veri_dizini=str(ayar.veri_dizini()),
        )

    @uygulama.post("/ayarlar")
    async def ayarlar_kaydet(istek: Request):
        k = kullanici(istek)
        if not k or k["rol"] != "yonetici":
            return yonlendir("/", "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        form = await istek.form()
        with vt.islem() as b:
            vt.ayar_yaz(b, "okul_adi", str(form.get("okul_adi", "")).strip()[:120])
            adres = str(form.get("sunucu_adresi", "")).strip().rstrip("/")
            if adres and not adres.startswith("https://"):
                return yonlendir("/ayarlar", "Sunucu adresi https:// ile başlamalı.", hata=True)
            vt.ayar_yaz(b, "sunucu_adresi", adres)
            saatler = [s.strip().replace(".", ":") for s in str(form.get("ok_saatler", "")).split(",") if s.strip()]
            if any(not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", s) for s in saatler):
                return yonlendir("/ayarlar", "Kapatma saatleri SS:DD biçiminde, virgülle ayrılarak yazılmalı (ör. 19:15).", hata=True)
            try:
                hafta_sonu_dk = max(10, min(600, int(str(form.get("ok_hafta_sonu_dk", "60")) or "60")))
            except ValueError:
                hafta_sonu_dk = 60
            vt.ayar_yaz(
                b,
                "otomatik_kapatma",
                {
                    "etkin": form.get("ok_etkin") == "1" and bool(saatler),
                    "saatler": sorted(set(saatler)),
                    "hafta_sonu": form.get("ok_hafta_sonu") == "1",
                    "hafta_sonu_dk": hafta_sonu_dk,
                },
            )
            kod = str(form.get("kilit_kodu", "")).strip()
            if form.get("kilit_kodu_sil") == "1":
                vt.ayar_yaz(b, "kilit_kodu", None)
                vt.kayit_dus(b, k["ad"], "Kilit kodu kaldırıldı", "", istemci_ip(istek))
            elif kod:
                if not (kod.isdigit() and 4 <= len(kod) <= 8):
                    return yonlendir("/ayarlar", "Kilit kodu 4-8 haneli rakamlardan oluşmalı.", hata=True)
                vt.ayar_yaz(b, "kilit_kodu", guvenlik.kilit_kodu_ozetle(kod))
                vt.kayit_dus(b, k["ad"], "Kilit kodu değiştirildi", "", istemci_ip(istek))
            vt.kayit_dus(b, k["ad"], "Ayarlar kaydedildi", "", istemci_ip(istek))
            idler = [s["id"] for s in b.execute("SELECT id FROM tahta WHERE durum = 'onayli'").fetchall()]
        for tahta_id in idler:  # yeni ayar tahtalara hemen insin
            uyandir(tahta_id)
        return yonlendir("/ayarlar", "Ayarlar kaydedildi.")

    # ---- okul kimliği: renkler ve logo ----------------------------------------
    @uygulama.post("/ayarlar/gorunum")
    async def gorunum_kaydet(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        if k["rol"] != "yonetici":
            return yonlendir("/", "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        form = await istek.form()
        if form.get("eylem") == "varsayilan":
            with vt.islem() as b:
                vt.ayar_yaz(b, "tema", None)
                vt.kayit_dus(b, k["ad"], "Görünüm varsayılana döndürüldü", "", istemci_ip(istek))
            onayli_tahtalari_uyandir()
            return yonlendir("/ayarlar?yer=kimlik#ileti", "Renkler varsayılana döndürüldü.")
        ana = tema.renk_dogrula(form.get("ana_renk"))
        vurgu = None
        if form.get("vurgu_kullan") == "1":
            vurgu = tema.renk_dogrula(form.get("vurgu_renk"))
            if not vurgu:
                ana = None
        if not ana:
            return yonlendir("/ayarlar?yer=kimlik#ileti", "Renk #rrggbb biçiminde olmalı.", hata=True)
        with vt.islem() as b:
            vt.ayar_yaz(b, "tema", {"ana": ana, "vurgu": vurgu})
            vt.kayit_dus(b, k["ad"], "Görünüm değiştirildi", f"{ana} {vurgu or '-'}", istemci_ip(istek))
        onayli_tahtalari_uyandir()
        return yonlendir("/ayarlar?yer=kimlik#ileti", "Renkler kaydedildi.")

    @uygulama.post("/ayarlar/logo")
    async def logo_yukle(istek: Request):
        # Yetki, form ayrıştırılmadan önce denetlenir.
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        if k["rol"] != "yonetici":
            return yonlendir("/", "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        boyut_iletisi = "Logo dosyası en çok 256 KB olabilir."
        try:
            if int(istek.headers.get("content-length") or 0) > 600_000:
                return yonlendir("/ayarlar?yer=kimlik#ileti", boyut_iletisi, hata=True)
        except ValueError:
            return yonlendir("/ayarlar?yer=kimlik#ileti", "Logo dosyası okunamadı.", hata=True)
        try:
            form = await istek.form(max_files=1, max_fields=2)
        except Exception:
            return yonlendir("/ayarlar?yer=kimlik#ileti", "Logo dosyası okunamadı.", hata=True)
        dosya = form.get("logo")
        if not isinstance(dosya, UploadFile):
            return yonlendir("/ayarlar?yer=kimlik#ileti", "Logo dosyası seçilmedi.", hata=True)
        veri = await dosya.read(marka.LOGO_SINIRI + 1)
        await form.close()
        if not veri:
            return yonlendir("/ayarlar?yer=kimlik#ileti", "Logo dosyası seçilmedi.", hata=True)
        if len(veri) > marka.LOGO_SINIRI:
            return yonlendir("/ayarlar?yer=kimlik#ileti", boyut_iletisi, hata=True)
        try:
            tur, en, boy = marka.logo_dogrula(veri)
        except ValueError as hata:
            return yonlendir("/ayarlar?yer=kimlik#ileti", str(hata), hata=True)
        marka.logo_yaz(veri)
        with vt.islem() as b:
            vt.ayar_yaz(
                b,
                "logo",
                {
                    "sha256": hashlib.sha256(veri).hexdigest(),
                    "tur": tur,
                    "en": en,
                    "boy": boy,
                    "boyut": len(veri),
                    "zaman": vt.simdi(),
                },
            )
            vt.kayit_dus(b, k["ad"], "Okul logosu yüklendi", f"{tur} {en}x{boy} {len(veri)} bayt", istemci_ip(istek))
        onayli_tahtalari_uyandir()
        return yonlendir("/ayarlar?yer=kimlik#ileti", "Logo yüklendi.")

    @uygulama.post("/ayarlar/logo/sil")
    async def logo_kaldir(istek: Request):
        k = kullanici(istek)
        if not k:
            return yonlendir("/giris")
        if k["rol"] != "yonetici":
            return yonlendir("/", "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        marka.logo_sil()
        with vt.islem() as b:
            vt.ayar_yaz(b, "logo", None)
            vt.kayit_dus(b, k["ad"], "Okul logosu kaldırıldı", "", istemci_ip(istek))
        onayli_tahtalari_uyandir()
        return yonlendir("/ayarlar?yer=kimlik#ileti", "Logo kaldırıldı.")

    @uygulama.get("/marka/tema.css")
    async def tema_css(istek: Request):
        with vt.islem() as b:
            ana, vurgu = tema.tema_al(b)
        onbellek = UZUN_ONBELLEK if istek.query_params.get("v") == tema.surum(ana, vurgu) else "no-cache"
        return Response(
            tema.css_metni(ana, vurgu),
            media_type="text/css; charset=utf-8",
            headers={"Cache-Control": onbellek},
        )

    @uygulama.get("/marka/logo")
    async def logo_sun(istek: Request):
        # Oturum istemez: logo giriş sayfasında ve tahtada zaten herkese görünür.
        with vt.islem() as b:
            logo = marka.logo_oku(b)
        if not logo:
            return Response("Logo yok.", status_code=404, media_type="text/plain; charset=utf-8")
        veri, bilgi = logo
        onbellek = UZUN_ONBELLEK if istek.query_params.get("v") == bilgi["sha256"][:12] else "no-cache"
        return Response(
            veri,
            media_type=marka.TURLER[bilgi["tur"]],
            headers={
                "Cache-Control": onbellek,
                "ETag": f'"{bilgi["sha256"]}"',
                "Content-Security-Policy": "default-src 'none'; sandbox",
            },
        )

    # ---- ajan arayüzü --------------------------------------------------------
    def tahta_dogrula(istek: Request):
        kimlik = istek.headers.get("x-tahta-id", "")
        anahtar = istek.headers.get("x-tahta-anahtar", "")
        if not (kimlik.isdigit() and anahtar):
            return None
        with vt.islem() as b:
            return b.execute(
                "SELECT * FROM tahta WHERE id = ? AND anahtar_ozet = ? AND durum != 'iptal'",
                (int(kimlik), guvenlik.ozet(anahtar)),
            ).fetchone()

    def ajan_ayari(b, tahta) -> dict:
        """Onaylı tahtaya her yanıtta inen ayarlar. Logo baytları buraya girmez (yalnız özeti)."""
        ana, vurgu = tema.tema_al(b)
        logo = marka.logo_oku(b)
        # Ad ve derslik uzun bekleme sırasında değişmiş olabilir: güncel satırdan okunur.
        guncel = b.execute("SELECT ad, derslik FROM tahta WHERE id = ?", (tahta["id"],)).fetchone() or tahta
        return {
            "okul_adi": vt.ayar_al(b, "okul_adi", ""),
            "kilit_kodu": vt.ayar_al(b, "kilit_kodu"),
            "sunucu_saat": time.time(),
            "ajan_surumu": paket.ajan_paketi().surum,
            "tema": dict(tema.uret(ana, vurgu)["tahta"]),
            "logo_sha256": logo[1]["sha256"] if logo else None,
            "tahta": {"ad": guncel["ad"], "derslik": guncel["derslik"]},
        }

    @uygulama.post("/ajan/kaydol")
    async def ajan_kaydol(istek: Request):
        if not hiz_siniri(kayit_denemeleri, istemci_ip(istek), 10, 600):
            return JSONResponse({"hata": "Çok fazla deneme; on dakika sonra yeniden deneyin."}, status_code=429)
        try:
            govde = await istek.json()
        except ValueError:
            return JSONResponse({"hata": "Geçersiz istek."}, status_code=400)
        with vt.islem() as b:
            pencere = vt.ayar_al(b, "kayit_penceresi") or {}
            import hmac

            gecerli = (
                pencere.get("bitis", 0) > vt.simdi()
                and pencere.get("kod")
                and hmac.compare_digest(str(govde.get("kod", "")), str(pencere["kod"]))
            )
            if not gecerli:
                vt.kayit_dus(b, "tahta:?", "Reddedilen tahta kaydı", "Kod geçersiz ya da tahta ekleme kapalı.", istemci_ip(istek))
                return JSONResponse(
                    {"hata": "Eşleştirme kodu geçersiz ya da panelde tahta ekleme açık değil."}, status_code=403
                )
            anahtar = guvenlik.belirtec()
            ad = str(govde.get("makine_adi", "")).strip()[:60] or "Yeni tahta"
            imlec = b.execute(
                "INSERT INTO tahta (ad, anahtar_ozet, kayit_zamani, ip, mac, makine_adi, surum, platform) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ad,
                    guvenlik.ozet(anahtar),
                    vt.simdi(),
                    istemci_ip(istek),
                    str(govde.get("mac", ""))[:17],
                    ad,
                    str(govde.get("surum", ""))[:20],
                    str(govde.get("platform", ""))[:120],
                ),
            )
            vt.kayit_dus(b, f"tahta:{ad}", "Tahta kaydoldu", "Onay bekliyor.", istemci_ip(istek))
            return {"tahta_id": imlec.lastrowid, "anahtar": anahtar}

    @uygulama.post("/ajan/bekle")
    async def ajan_bekle(istek: Request):
        tahta = tahta_dogrula(istek)
        if not tahta:
            return JSONResponse({"hata": "Tahta tanınmıyor."}, status_code=401)
        try:
            govde = await istek.json()
        except ValueError:
            return JSONResponse({"hata": "Geçersiz istek."}, status_code=400)
        durum = govde.get("durum") if isinstance(govde.get("durum"), dict) else None
        with vt.islem() as b:
            if durum is not None:
                olaylar = durum.pop("olaylar", []) or []
                b.execute(
                    "UPDATE tahta SET son_gorulme = ?, ip = ?, surum = ?, durum_json = ?, mac = ?, makine_adi = ?, platform = ? "
                    "WHERE id = ?",
                    (
                        vt.simdi(),
                        istemci_ip(istek),
                        str(govde.get("surum", ""))[:20],
                        json.dumps(durum, ensure_ascii=False)[:20000],
                        str(durum.get("mac") or tahta["mac"])[:17],
                        str(durum.get("makine_adi") or tahta["makine_adi"])[:60],
                        str(durum.get("platform") or tahta["platform"])[:120],
                        tahta["id"],
                    ),
                )
                for olay in olaylar[:20]:
                    vt.kayit_dus(b, f"tahta:{tahta['ad']}", "Tahta olayı", str(olay), istemci_ip(istek))
            else:
                b.execute("UPDATE tahta SET son_gorulme = ?, ip = ? WHERE id = ?", (vt.simdi(), istemci_ip(istek), tahta["id"]))
            for sonuc in (govde.get("sonuclar") or [])[:50]:
                komut = b.execute(
                    "SELECT * FROM komut WHERE id = ? AND tahta_id = ?", (sonuc.get("komut_id"), tahta["id"])
                ).fetchone()
                if not komut or komut["durum"] in ("tamam", "hata"):
                    continue
                cikti = str(sonuc.get("cikti", ""))
                basarili = bool(sonuc.get("basarili"))
                if komut["tur"] == "tani" and basarili:
                    b.execute(
                        "UPDATE tahta SET tani_json = ?, tani_zamani = ? WHERE id = ?",
                        (cikti[:200000], vt.simdi(), tahta["id"]),
                    )
                    cikti = "Tanılama raporu alındı."
                b.execute(
                    "UPDATE komut SET durum = ?, sonuc = ?, tamamlanma = ? WHERE id = ?",
                    ("tamam" if basarili else "hata", cikti[:4000], vt.simdi(), komut["id"]),
                )
            ayarlar_ = ajan_ayari(b, tahta)
        if tahta["durum"] != "onayli":
            return {"durum": "bekliyor", "ayar": {"sunucu_saat": time.time()}}
        if govde.get("komut_al", True) is False:
            return {"durum": "onayli", "komutlar": [], "ayar": ayarlar_}

        def bekleyen_komutlar() -> list[dict]:
            with vt.islem() as b:
                b.execute(
                    "UPDATE komut SET durum = 'zaman_asimi' WHERE tahta_id = ? AND durum = 'bekliyor' AND bitis < ?",
                    (tahta["id"], vt.simdi()),
                )
                satirlar = b.execute(
                    "SELECT * FROM komut WHERE tahta_id = ? AND durum = 'bekliyor' ORDER BY id", (tahta["id"],)
                ).fetchall()
                cikti = []
                for s in satirlar:
                    veri = json.loads(s["veri_json"] or "{}")
                    if s["tur"] == "duyuru":  # tahtanın saatine güvenilmez; kalan süre burada hesaplanır
                        veri["sure_sn"] = max(5, int(veri.pop("bitis_sunucu", vt.simdi() + 60)) - vt.simdi())
                    cikti.append({"id": s["id"], "tur": s["tur"], "veri": veri})
                    b.execute("UPDATE komut SET durum = 'gonderildi' WHERE id = ?", (s["id"],))
                return cikti

        komutlar = bekleyen_komutlar()
        bekle = max(0, min(25, int(govde.get("bekle", 0) or 0)))
        if not komutlar and bekle:
            olay = asyncio.Event()
            bekleyenler[tahta["id"]] = (asyncio.get_running_loop(), olay)
            try:
                await asyncio.wait_for(olay.wait(), timeout=bekle)
            except TimeoutError:
                pass
            finally:
                if bekleyenler.get(tahta["id"], (None, None))[1] is olay:
                    bekleyenler.pop(tahta["id"], None)
            komutlar = bekleyen_komutlar()
            with vt.islem() as b:
                ayarlar_ = ajan_ayari(b, tahta)
        return {"durum": "onayli", "komutlar": komutlar, "ayar": ayarlar_}

    @uygulama.get("/ajan/paket")
    async def ajan_paketi(istek: Request):
        if not tahta_dogrula(istek):
            return JSONResponse({"hata": "Tahta tanınmıyor."}, status_code=401)
        p = paket.ajan_paketi()
        return Response(p.icerik, media_type="application/vnd.debian.binary-package", headers={"X-Sha256": p.sha256})

    @uygulama.get("/ajan/logo")
    async def ajan_logo(istek: Request):
        if not tahta_dogrula(istek):
            return JSONResponse({"hata": "Tahta tanınmıyor."}, status_code=401)
        with vt.islem() as b:
            logo = marka.logo_oku(b)
        if not logo:
            return JSONResponse({"hata": "Logo yok."}, status_code=404)
        veri, bilgi = logo
        return Response(
            veri,
            media_type=marka.TURLER[bilgi["tur"]],
            headers={"X-Sha256": bilgi["sha256"], "Cache-Control": "no-store"},
        )

    # ---- otomatik kapatma ----------------------------------------------------
    hafta_sonu_son: dict[int, float] = {}

    def zamanlayici(simdi: datetime | None = None) -> int:
        """Otomatik kapatma kurallarını uygular; komut verilen tahta sayısını döndürür.

        Sunucu bunu 20 saniyede bir çağırır. Yalnız o anda çevrimiçi olan tahtalara
        komut verilir; saatinden sonra açılan tahta kapatılmaz. Komut uyarılıdır:
        kullanılan tahtada geri sayım çıkar ve kullanan kişi vazgeçebilir.
        """
        simdi = simdi or datetime.now(ISTANBUL)
        hedefler, neden = [], ""
        with vt.islem() as b:
            kural = vt.ayar_al(b, "otomatik_kapatma") or {}
            if not (kural.get("etkin") or kural.get("hafta_sonu")):
                return 0
            acik = [
                t
                for t in b.execute("SELECT * FROM tahta WHERE durum = 'onayli'").fetchall()
                if t["son_gorulme"] and vt.simdi() - t["son_gorulme"] < ayar.CEVRIMICI_ESIK_SN
            ]
            if simdi.weekday() < 5:
                isaretler = vt.ayar_al(b, "kapatma_isaretleri") or []
                for saat in kural.get("saatler", []) if kural.get("etkin") else []:
                    an = simdi.replace(hour=int(saat[:2]), minute=int(saat[3:]), second=0, microsecond=0)
                    isaret = f"{simdi:%Y-%m-%d} {saat}"
                    if 0 <= (simdi - an).total_seconds() < 600 and isaret not in isaretler:
                        vt.ayar_yaz(b, "kapatma_isaretleri", (isaretler + [isaret])[-20:])
                        hedefler, neden = acik, f"Otomatik kapatma (saat {saat})"
                        break
            elif kural.get("hafta_sonu"):
                sinir = int(kural.get("hafta_sonu_dk", 60)) * 60
                for t in acik:
                    acik_sure = json.loads(t["durum_json"] or "{}").get("acik_sure", 0)
                    if acik_sure > sinir and time.time() - hafta_sonu_son.get(t["id"], 0) > sinir:
                        hafta_sonu_son[t["id"]] = time.time()
                        hedefler.append(t)
                neden = "Hafta sonu otomatik kapatma"
            for t in hedefler:
                komut_ekle(b, t["id"], "kapat", {"uyari_sn": 60, "neden": neden}, "sistem")
            if hedefler:
                vt.kayit_dus(b, "sistem", neden, f"{len(hedefler)} tahta: " + ", ".join(t["ad"] for t in hedefler))
        for t in hedefler:
            uyandir(t["id"])
        return len(hedefler)

    uygulama.state.zamanlayici = zamanlayici
    return uygulama
