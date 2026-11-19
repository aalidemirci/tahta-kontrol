"""Panel: tahta grupları ve tahta niteliklerinin CSV ile dışa/içe aktarılması.

CSV biçimi (dışa ve içe aynı; `;` ayraçlı, UTF-8 BOM'lu; içe aktarmada cp1254 ve `,` da olur):
    id;ad;derslik;bina;kat;duzeyler;devre;subeler;gruplar;cevrimici;ajan_surumu
Dosyada hiç olmayan sütuna dokunulmaz; sütun var ama hücre boşsa alan temizlenir
(ad ve derslik boşsa değişmez). Önizleme sunucuda durum tutmaz: çözülmüş metin gizli
`icerik` alanında forma geri konur, "Uygula"da yeniden ayrıştırılıp doğrulanır.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from starlette.datastructures import UploadFile

from . import ayar, guvenlik, hedef, metin, vt

CSV_EN_COK_BAYT = 2 * 1024 * 1024
CSV_EN_COK_SATIR = 2000
GRUP_AD_EN_UZUN = 40
GRUP_ACIKLAMA_EN_UZUN = 200
CSV_SUTUNLARI = ["id", "ad", "derslik", "bina", "kat", "duzeyler", "devre", "subeler", "gruplar", "cevrimici", "ajan_surumu"]
# Başlık eşleme: katla(başlık) → alan
_BASLIKLAR = {
    "id": "id", "kimlik": "id", "ad": "ad", "tahta": "ad", "tahta adi": "ad", "derslik": "derslik",
    "bina": "bina", "blok": "bina", "kat": "kat", "duzeyler": "duzeyler", "duzey": "duzeyler",
    "devre": "devre", "subeler": "subeler", "sube": "subeler", "gruplar": "gruplar", "grup": "gruplar",
}  # fmt: skip
ALAN_ADI = {
    "ad": "Ad", "derslik": "Derslik", "bina": "Bina", "kat": "Kat", "duzeyler": "Düzey", "devre": "Devre",
    "subeler": "Şube", "gruplar": "Gruplar",
}  # fmt: skip


def _duzey_yaz(kume: str) -> str:
    return "|".join(hedef.DUZEYLER[d] for d in hedef.kume(kume) if d in hedef.DUZEYLER)


def _gorunen(alan: str, deger) -> str:
    if alan == "kat":
        return hedef.kat_adi(deger) if deger is not None else ""
    if alan == "duzeyler":
        return ", ".join(hedef.DUZEYLER[d] for d in hedef.kume(deger) if d in hedef.DUZEYLER)
    if alan == "devre":
        return hedef.DEVRELER.get(deger, "")
    if alan == "subeler":
        return ", ".join(hedef.kume(deger))
    if alan == "gruplar":
        return ", ".join(deger)
    return str(deger or "")


def disa_aktar(b) -> bytes:
    gruplar: dict[int, list[str]] = {}
    for s in b.execute(
        "SELECT u.tahta_id, g.ad FROM tahta_grubu_uye u JOIN tahta_grubu g ON g.id = u.grup_id ORDER BY g.ad COLLATE NOCASE"
    ):
        gruplar.setdefault(s["tahta_id"], []).append(s["ad"])
    satirlar = []
    simdi = vt.simdi()
    for t in b.execute("SELECT * FROM tahta WHERE durum != 'iptal' ORDER BY id"):
        cevrimici = bool(t["son_gorulme"]) and simdi - t["son_gorulme"] < ayar.CEVRIMICI_ESIK_SN
        satirlar.append(
            [
                t["id"],
                t["ad"],
                t["derslik"],
                t["bina"],
                hedef.kat_csv(t["kat"]),
                _duzey_yaz(t["duzeyler"]),
                hedef.DEVRELER.get(t["devre"], ""),
                "|".join(hedef.kume(t["subeler"])),
                "|".join(gruplar.get(t["id"], [])),
                "evet" if cevrimici else "hayır",
                t["surum"],
            ]
        )
    # IP/MAC bilinçli olarak yazılmaz (okula özgü ağ bilgisi; gereksiz).
    return metin.csv_yaz(CSV_SUTUNLARI, satirlar)


def ice_aktar_coz(b, bayt: bytes) -> dict:
    """CSV'yi ayrıştırıp doğrular; veritabanına yazmaz. Önizleme ve uygulama aynı sonucu kullanır.

    Döndürür: {"sutunlar", "satirlar": [{"satir","tahta_id","tahta","degisiklikler","durum","neden","yeni"}],
    "yeni_gruplar", "sayilar": {"degisecek","degismiyor","hatali"}}. Dosya okunamazsa ValueError.
    """
    basliklar, satirlar = metin.csv_oku(bayt, CSV_EN_COK_BAYT, CSV_EN_COK_SATIR)
    konum: dict[str, int] = {}
    for sira, baslik in enumerate(basliklar):
        alan = _BASLIKLAR.get(metin.katla(baslik).replace("_", " "))
        if alan and alan not in konum:
            konum[alan] = sira
    if "id" not in konum:
        raise ValueError("Dosyada 'id' sütunu yok. Önce tahtaları dışa aktarın ve aynı dosyayı doldurun.")
    tahtalar = {t["id"]: t for t in b.execute("SELECT * FROM tahta WHERE durum != 'iptal'")}
    mevcut_gruplar = {metin.katla(g["ad"]): g for g in b.execute("SELECT * FROM tahta_grubu")}
    uyelik: dict[int, list[str]] = {}
    for s in b.execute(
        "SELECT u.tahta_id, g.ad FROM tahta_grubu_uye u JOIN tahta_grubu g ON g.id = u.grup_id ORDER BY g.ad COLLATE NOCASE"
    ):
        uyelik.setdefault(s["tahta_id"], []).append(s["ad"])
    yeni_gruplar: dict[str, str] = {}
    gorulen: set[int] = set()
    sonuc = []
    for sira, satir in enumerate(satirlar, start=2):
        kayit = {"satir": sira, "tahta_id": None, "tahta": "", "degisiklikler": [], "durum": "hatali", "neden": "", "yeni": {}}
        sonuc.append(kayit)
        ham_id = satir[konum["id"]].strip().lstrip("'")
        if not ham_id.isdigit() or int(ham_id) not in tahtalar:
            kayit["neden"] = "Bu kimlikte tahta yok ya da kaldırılmış."
            continue
        t = tahtalar[int(ham_id)]
        kayit.update(tahta_id=t["id"], tahta=t["ad"])
        if t["id"] in gorulen:
            kayit["neden"] = "Bu tahta dosyada birden çok kez geçiyor."
            continue
        gorulen.add(t["id"])

        def hucre(alan: str, satir=satir) -> str | None:
            # Dışa aktarmadaki formül kaçışı (') geri alınır; gidiş-dönüş değeri bozmaz.
            return metin.csv_hucre_coz(satir[konum[alan]].strip()).strip() if alan in konum else None

        yeni: dict = {}
        try:
            for alan in ("ad", "derslik"):
                deger = hucre(alan)
                if deger:
                    if len(deger) > 60:
                        raise ValueError(f"{ALAN_ADI[alan]} en çok 60 karakter olabilir.")
                    yeni[alan] = deger
            if (deger := hucre("bina")) is not None:
                deger = " ".join(deger.split())
                if len(deger) > hedef.BINA_EN_UZUN:
                    raise ValueError(f"Bina adı en çok {hedef.BINA_EN_UZUN} karakter olabilir.")
                yeni["bina"] = deger
            if (deger := hucre("kat")) is not None:
                yeni["kat"] = hedef.kat_coz(deger)
            if (deger := hucre("duzeyler")) is not None:
                yeni["duzeyler"] = ",".join(hedef.duzey_coz(deger))
            if (deger := hucre("devre")) is not None:
                yeni["devre"] = hedef.devre_coz(deger)
            if (deger := hucre("subeler")) is not None:
                yeni["subeler"] = ",".join(hedef.subeler_coz(deger))
            if (deger := hucre("gruplar")) is not None:
                adlar: list[str] = []
                for parca in deger.split("|"):
                    ad = " ".join(parca.split())
                    if not ad:
                        continue
                    if len(ad) > GRUP_AD_EN_UZUN:
                        raise ValueError(f"Grup adı en çok {GRUP_AD_EN_UZUN} karakter olabilir: {ad}")
                    var = mevcut_gruplar.get(metin.katla(ad))
                    ad = var["ad"] if var else yeni_gruplar.setdefault(metin.katla(ad), ad)
                    if metin.katla(ad) not in {metin.katla(a) for a in adlar}:
                        adlar.append(ad)
                yeni["gruplar"] = sorted(adlar, key=metin.tr_sirala_anahtari)
        except ValueError as hata:
            kayit["neden"] = str(hata)
            continue
        eski = dict(t) | {"gruplar": sorted(uyelik.get(t["id"], []), key=metin.tr_sirala_anahtari)}
        for alan, deger in yeni.items():
            eski_deger = eski[alan]
            if alan == "gruplar":
                esit = [metin.katla(a) for a in eski_deger] == [metin.katla(a) for a in deger]
            elif alan == "kat":
                esit = eski_deger == deger
            else:
                esit = (eski_deger or "") == (deger or "")
            if not esit:
                kayit["degisiklikler"].append(
                    {"alan": alan, "ad": ALAN_ADI[alan], "eski": _gorunen(alan, eski_deger), "yeni": _gorunen(alan, deger)}
                )
        kayit["yeni"] = yeni
        kayit["durum"] = "degisecek" if kayit["degisiklikler"] else "degismiyor"
    # Yalnız değişecek satırların istediği yeni gruplar oluşturulur.
    istenen = {
        metin.katla(a) for s in sonuc if s["durum"] == "degisecek" for a in s["yeni"].get("gruplar", [])
    }
    return {
        "sutunlar": sorted(konum),
        "satirlar": sonuc,
        "yeni_gruplar": [ad for anahtar, ad in yeni_gruplar.items() if anahtar in istenen],
        "sayilar": {d: sum(1 for s in sonuc if s["durum"] == d) for d in ("degisecek", "degismiyor", "hatali")},
    }


def ice_aktar_uygula(b, cozum: dict, kullanici_ad: str) -> int:
    """Önizlemesi yapılmış çözümü tek işlemde uygular; değişen tahta sayısını döndürür."""
    simdi = vt.simdi()
    for ad in cozum["yeni_gruplar"]:
        b.execute(
            "INSERT OR IGNORE INTO tahta_grubu (ad, aciklama, olusturan, olusturma) VALUES (?, '', ?, ?)",
            (ad, kullanici_ad, simdi),
        )
    gruplar = {metin.katla(g["ad"]): g["id"] for g in b.execute("SELECT id, ad FROM tahta_grubu")}
    sayi = 0
    for s in cozum["satirlar"]:
        if s["durum"] != "degisecek":
            continue
        sayi += 1
        yeni = s["yeni"]
        for alan in ("ad", "derslik", "bina", "kat", "duzeyler", "devre", "subeler"):
            if alan in yeni:
                b.execute(f"UPDATE tahta SET {alan} = ? WHERE id = ?", (yeni[alan], s["tahta_id"]))  # alan sabit listeden
        if "gruplar" in yeni:
            b.execute("DELETE FROM tahta_grubu_uye WHERE tahta_id = ?", (s["tahta_id"],))
            for ad in yeni["gruplar"]:
                if metin.katla(ad) in gruplar:
                    b.execute(
                        "INSERT OR IGNORE INTO tahta_grubu_uye (grup_id, tahta_id) VALUES (?, ?)",
                        (gruplar[metin.katla(ad)], s["tahta_id"]),
                    )
    return sayi


def kaydet(uygulama, y) -> None:
    def yonetici_degil(istek: Request, k, islem: str):
        if not k:
            return y.yonlendir("/giris")
        if k["rol"] != "yonetici":
            with vt.islem() as b:
                vt.kayit_dus(b, k["ad"], "Yetkisiz işlem reddedildi", islem, y.istemci_ip(istek))
            return y.yonlendir("/gruplar", "Bu işlem için yönetici yetkisi gerekir.", hata=True)
        return None

    # ---- gruplar -------------------------------------------------------------------------
    @uygulama.get("/gruplar", response_class=HTMLResponse)
    async def gruplar_sayfasi(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        with vt.islem() as b:
            kullanim = hedef.plan_gruplari(b)
            uyeler: dict[int, list[int]] = {}
            for s in b.execute(
                "SELECT u.grup_id, u.tahta_id FROM tahta_grubu_uye u JOIN tahta t ON t.id = u.tahta_id WHERE t.durum != 'iptal'"
            ):
                uyeler.setdefault(s["grup_id"], []).append(s["tahta_id"])
            gruplar = [
                {
                    "id": g["id"],
                    "ad": g["ad"],
                    "aciklama": g["aciklama"],
                    "uyeler": uyeler.get(g["id"], []),
                    "uye_sayisi": len(uyeler.get(g["id"], [])),
                    "planlar": kullanim.get(g["id"], []),
                    "olusturan": g["olusturan"],
                }
                for g in b.execute("SELECT * FROM tahta_grubu ORDER BY ad COLLATE NOCASE")
            ]
            tahtalar = [
                {
                    "id": t["id"],
                    "ad": t["ad"],
                    "derslik": t["derslik"],
                    "bina": t["bina"],
                    "kat": hedef.kat_adi(t["kat"]) if t["kat"] is not None else "",
                    "alanlar": hedef.alanlar_metni(t),
                }
                for t in sorted(
                    b.execute("SELECT * FROM tahta WHERE durum = 'onayli'").fetchall(),
                    key=lambda t: metin.tr_sirala_anahtari(t["ad"]),
                )
            ]
        return y.sayfa(
            istek,
            "gruplar.html",
            k,
            gruplar=gruplar,
            tahtalar=tahtalar,
            yonetici=k["rol"] == "yonetici",
            ad_en_uzun=GRUP_AD_EN_UZUN,
            aciklama_en_uzun=GRUP_ACIKLAMA_EN_UZUN,
        )

    @uygulama.post("/gruplar")
    async def grup_islem(istek: Request):
        k = y.kullanici(istek)
        engel = yonetici_degil(istek, k, "Gruplar")  # yetki form ayrıştırılmadan önce
        if engel:
            return engel
        form = await istek.form()
        eylem = str(form.get("eylem", ""))
        ip = y.istemci_ip(istek)
        ad = " ".join(str(form.get("ad", "")).split())
        aciklama = " ".join(str(form.get("aciklama", "")).split())
        if eylem in ("ekle", "ad"):
            if not ad or len(ad) > GRUP_AD_EN_UZUN:
                return y.yonlendir("/gruplar", f"Grup adı 1-{GRUP_AD_EN_UZUN} karakter olmalı.", hata=True)
            if len(aciklama) > GRUP_ACIKLAMA_EN_UZUN:
                return y.yonlendir("/gruplar", f"Açıklama en çok {GRUP_ACIKLAMA_EN_UZUN} karakter olabilir.", hata=True)
            if guvenlik.tc_kimlik_var(ad) or guvenlik.tc_kimlik_var(aciklama):
                return y.yonlendir("/gruplar", guvenlik.TC_KIMLIK_ILETISI, hata=True)
        with vt.islem() as b:
            ayni_ad = [
                g for g in b.execute("SELECT id, ad FROM tahta_grubu") if metin.katla(g["ad"]) == metin.katla(ad)
            ]
            if eylem == "ekle":
                if ayni_ad:
                    return y.yonlendir("/gruplar", "Bu adla bir grup zaten var.", hata=True)
                b.execute(
                    "INSERT INTO tahta_grubu (ad, aciklama, olusturan, olusturma) VALUES (?, ?, ?, ?)",
                    (ad, aciklama, k["ad"], vt.simdi()),
                )
                vt.kayit_dus(b, k["ad"], "Tahta grubu eklendi", ad, ip)
                return y.yonlendir("/gruplar", f"'{ad}' grubu eklendi.")
            grup = b.execute("SELECT * FROM tahta_grubu WHERE id = ?", (str(form.get("id", "")),)).fetchone()
            if not grup:
                return y.yonlendir("/gruplar", "Grup bulunamadı.", hata=True)
            if eylem == "ad":
                if any(g["id"] != grup["id"] for g in ayni_ad):
                    return y.yonlendir("/gruplar", "Bu adla bir grup zaten var.", hata=True)
                b.execute("UPDATE tahta_grubu SET ad = ?, aciklama = ? WHERE id = ?", (ad, aciklama, grup["id"]))
                vt.kayit_dus(b, k["ad"], "Tahta grubu düzenlendi", f"{grup['ad']} → {ad}", ip)
                return y.yonlendir("/gruplar", "Grup kaydedildi.")
            if eylem == "sil":
                planlar = hedef.plan_gruplari(b).get(grup["id"], [])
                if planlar:
                    adlar = ", ".join(f"'{p}'" for p in planlar[:3]) + (" …" if len(planlar) > 3 else "")
                    return y.yonlendir(
                        "/gruplar",
                        f"Bu grup {len(planlar)} duyuru planında kullanılıyor ({adlar}). Önce planları düzenleyin.",
                        hata=True,
                    )
                b.execute("DELETE FROM tahta_grubu WHERE id = ?", (grup["id"],))
                vt.kayit_dus(b, k["ad"], "Tahta grubu silindi", grup["ad"], ip)
                return y.yonlendir("/gruplar", f"'{grup['ad']}' grubu silindi.")
            if eylem == "uyeler":
                idler = sorted({int(t) for t in form.getlist("tahta") if str(t).isdigit() and hedef.kimlik_mi(t)})
                b.execute("DELETE FROM tahta_grubu_uye WHERE grup_id = ?", (grup["id"],))
                for tahta_id in idler:
                    b.execute(
                        "INSERT OR IGNORE INTO tahta_grubu_uye (grup_id, tahta_id) "
                        "SELECT ?, id FROM tahta WHERE id = ? AND durum != 'iptal'",
                        (grup["id"], tahta_id),
                    )
                sayi = b.execute("SELECT COUNT(*) FROM tahta_grubu_uye WHERE grup_id = ?", (grup["id"],)).fetchone()[0]
                vt.kayit_dus(b, k["ad"], "Tahta grubu üyeleri değişti", f"{grup['ad']}: {sayi} tahta", ip)
                return y.yonlendir("/gruplar", f"'{grup['ad']}' grubunda {sayi} tahta var.")
        return y.yonlendir("/gruplar", "Bilinmeyen işlem.", hata=True)

    # ---- CSV -----------------------------------------------------------------------------
    @uygulama.get("/tahtalar.csv")
    async def tahtalar_csv(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        with vt.islem() as b:
            icerik = disa_aktar(b)
            vt.kayit_dus(b, k["ad"], "Tahtalar dışa aktarıldı (CSV)", "", y.istemci_ip(istek))
        return Response(
            icerik,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="tahtalar.csv"'},
        )

    @uygulama.get("/tahtalar/ice-aktar", response_class=HTMLResponse)
    async def ice_aktar_formu(istek: Request):
        k = y.kullanici(istek)
        engel = yonetici_degil(istek, k, "Tahta içe aktarma sayfası")
        if engel:
            return engel
        return y.sayfa(istek, "tahta_ice_aktar.html", k, cozum=None, icerik="", hata="")

    @uygulama.post("/tahtalar/ice-aktar")
    async def ice_aktar(istek: Request):
        k = y.kullanici(istek)
        engel = yonetici_degil(istek, k, "Tahta içe aktarma")
        if engel:
            return engel
        try:
            if int(istek.headers.get("content-length") or 0) > 3 * CSV_EN_COK_BAYT:
                return y.yonlendir("/tahtalar/ice-aktar", "Dosya en çok 2 MB olabilir.", hata=True)
        except ValueError:
            return y.yonlendir("/tahtalar/ice-aktar", "Dosya okunamadı.", hata=True)
        try:
            form = await istek.form(max_files=1, max_fields=10, max_part_size=3 * CSV_EN_COK_BAYT)
        except Exception:  # bozuk ya da sınırı aşan çok parçalı istek
            return y.yonlendir("/tahtalar/ice-aktar", "Dosya okunamadı ya da 2 MB'tan büyük.", hata=True)
        try:
            eylem = str(form.get("eylem", "onizle"))
            if eylem == "uygula":
                bayt = str(form.get("icerik", "")).encode("utf-8")
            else:
                dosya = form.get("dosya")
                if not isinstance(dosya, UploadFile):
                    return y.yonlendir("/tahtalar/ice-aktar", "CSV dosyası seçilmedi.", hata=True)
                bayt = await dosya.read(CSV_EN_COK_BAYT + 1)
        finally:
            await form.close()
        if not bayt.strip():
            return y.yonlendir("/tahtalar/ice-aktar", "CSV dosyası boş.", hata=True)
        with vt.islem() as b:
            try:
                cozum = ice_aktar_coz(b, bayt)
            except ValueError as hata:
                return y.sayfa(istek, "tahta_ice_aktar.html", k, durum_kodu=400, cozum=None, icerik="", hata=str(hata))
            if eylem != "uygula":
                try:
                    icerik = bayt.decode("utf-8-sig")
                except UnicodeDecodeError:
                    icerik = bayt.decode("cp1254", errors="replace")
                return y.sayfa(istek, "tahta_ice_aktar.html", k, cozum=cozum, icerik=icerik, hata="")
            sayi = ice_aktar_uygula(b, cozum, k["ad"])
            ayrinti = f"{sayi} tahta, {cozum['sayilar']['hatali']} hatalı satır"
            if cozum["yeni_gruplar"]:
                ayrinti += "; yeni grup: " + ", ".join(cozum["yeni_gruplar"])
            vt.kayit_dus(b, k["ad"], "Tahta alanları içe aktarıldı", ayrinti, y.istemci_ip(istek))
        return y.yonlendir("/tahtalar", f"Tahta alanları içe aktarıldı: {ayrinti}.")
