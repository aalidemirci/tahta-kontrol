"""Panel: duyurular, duyuru planları ve hedef önizlemesi.

Uçlar `web.uygulama_olustur` içinde `kaydet(uygulama, y)` ile eklenir; `y` ortak
yardımcıları taşır (kullanici, sayfa, yonlendir, uyandir_hepsi, istemci_ip …).
İş mantığı `duyuru.py`, `zamanlama.py`, `hedef.py`'dedir.
"""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse

from . import duyuru, guvenlik, hedef, metin, program, sinav, vt, zamanlama
from .zamanlama import ISTANBUL

GECMIS_EN_COK = 100
YETKI_ILETISI = "Bu {tur} {sahip} kullanıcısına ait; yalnız oluşturan ya da yönetici değiştirebilir."


ON_SECIM_EN_COK = 500  # /duyurular/yeni?tahta=… ön seçiminde okunan en çok değer


def yetkili_mi(k, sahip: str) -> bool:
    return k["rol"] == "yonetici" or k["ad"] == sahip


def _bugun() -> str:
    return datetime.now(ISTANBUL).date().isoformat()


def bos_form() -> dict:
    """Yeni duyuru formunun varsayılan değerleri (şablon `form` bağlamı)."""
    return {
        "baslik": "",
        "metin": "",
        "sure_dk": 5,
        "kapatilabilir": True,
        "zaman": "hemen",
        "bir_tarih": "",
        "bir_saat": "",
        "siklik": "gunluk",
        "hafta_sonu": False,
        "gunler": [0, 1, 2, 3, 4],
        "tekrar_saat": "",
        "baslangic": _bugun(),
        "bitis": "",
        "kime": "tumu",
        "hedef": {},
    }


def _hedef_formu(ham: dict) -> dict:
    """Hedef sözlüğünü formun "Kime" alanlarına çevirir (işaretli kutular için)."""
    if ham.get("tumu"):
        return {"kime": "tumu", "hedef": {}}
    return {"kime": "secim", "hedef": {a: list(d) for a, d in ham.items() if isinstance(d, list)}}


def plandan_form(plan) -> dict:
    form = bos_form()
    form.update(
        baslik=plan["baslik"],
        metin=plan["metin"],
        sure_dk=plan["sure_sn"] // 60,
        kapatilabilir=bool(plan["kapatilabilir"]),
    )
    if plan["tekrar"] == "tek":
        form.update(zaman="bir_kez", bir_tarih=plan["baslangic"], bir_saat=plan["saat"])
    else:
        form.update(
            zaman="tekrarli",
            siklik=plan["tekrar"],
            hafta_sonu=plan["gunler"] == zamanlama.HER_GUN,
            gunler=sorted(zamanlama.gunler_kumesi(plan)),
            tekrar_saat=plan["saat"],
            baslangic=plan["baslangic"],
            bitis=plan["bitis"],
        )
    try:
        form.update(_hedef_formu(hedef.dogrula(plan["hedef_json"])))
    except ValueError:
        form.update(kime="secim", hedef={})
    return form


def yayindan_form(yayin) -> dict:
    form = bos_form()
    form.update(
        baslik=yayin["baslik"],
        metin=yayin["metin"],
        sure_dk=max(1, yayin["sure_sn"] // 60),
        kapatilabilir=bool(yayin["kapatilabilir"]),
    )
    try:
        form.update(_hedef_formu(hedef.dogrula(yayin["hedef_json"])))
    except ValueError:
        pass
    return form


def gonderilen_form(form) -> dict:
    """Hatalı gönderimde formu kullanıcının yazdıklarıyla yeniden doldurmak için."""
    sonuc = bos_form()
    for ad in ("baslik", "metin", "zaman", "bir_tarih", "bir_saat", "siklik", "tekrar_saat", "baslangic", "bitis"):
        if form.get(ad) is not None:
            sonuc[ad] = str(form.get(ad))
    try:
        sonuc["sure_dk"] = int(str(form.get("sure_dk", "5")))
    except ValueError:
        sonuc["sure_dk"] = str(form.get("sure_dk", ""))
    sonuc["kapatilabilir"] = form.get("kapatilabilir") == "1"
    sonuc["hafta_sonu"] = form.get("hafta_sonu") == "1"
    sonuc["gunler"] = sorted({int(g) for g in form.getlist("gun") if str(g) in ("0", "1", "2", "3", "4", "5", "6")})
    sonuc["kime"] = "tumu" if form.get("kime") == "tumu" else "secim"
    sonuc["hedef"] = hedef.formdan(form) if sonuc["kime"] == "secim" else {}
    return sonuc


def secenekler(b) -> dict:
    """"Kime" bölümünün seçenekleri: yalnız kayıtlı (onaylı) tahtalarda geçen değerler."""
    tahtalar = b.execute("SELECT * FROM tahta WHERE durum = 'onayli'").fetchall()
    binalar: dict[str, str] = {}
    katlar, duzeyler, devreler = set(), set(), set()
    turetilen = program.tahta_devreleri(b)  # ikili eğitimde "devre" alanı boş tahtalar için
    for t in tahtalar:
        if t["bina"]:
            binalar.setdefault(hedef.bina_anahtari(t["bina"]), t["bina"].strip())
        if t["kat"] is not None:
            katlar.add(t["kat"])
        duzeyler.update(hedef.kume(t["duzeyler"]))
        if t["devre"] or turetilen.get(t["id"]):
            devreler.add(t["devre"] or turetilen[t["id"]])
    if "her_ikisi" in devreler:
        devreler.update(("sabah", "ogle"))
    gruplar = b.execute(
        "SELECT g.id, g.ad, g.aciklama, COUNT(u.tahta_id) AS uye_sayisi FROM tahta_grubu g "
        "LEFT JOIN tahta_grubu_uye u ON u.grup_id = g.id LEFT JOIN tahta t ON t.id = u.tahta_id AND t.durum = 'onayli' "
        "GROUP BY g.id ORDER BY g.ad COLLATE NOCASE"
    ).fetchall()
    return {
        "binalar": sorted(binalar.values(), key=metin.tr_sirala_anahtari),
        "katlar": [(k, hedef.kat_adi(k)) for k in sorted(katlar)],
        "duzeyler": [(d, hedef.DUZEYLER[d]) for d in hedef.DUZEYLER if d in duzeyler],
        "devreler": [(d, hedef.DEVRELER[d]) for d in ("sabah", "ogle") if d in devreler],
        "gruplar": [{"id": g["id"], "ad": g["ad"], "aciklama": g["aciklama"], "uye_sayisi": g["uye_sayisi"]} for g in gruplar],
        "tahtalar": [
            {"id": t["id"], "ad": t["ad"], "derslik": t["derslik"], "alanlar": hedef.alanlar_metni(t)}
            for t in sorted(tahtalar, key=lambda t: metin.tr_sirala_anahtari(t["ad"]))
        ],
    }


def kaydet(uygulama, y) -> None:  # noqa: C901 (uç tanımları)
    def form_sayfasi(istek: Request, k, form: dict, *, plan=None, hata: str = "", durum_kodu: int = 200, on_secim=None):
        with vt.islem() as b:
            sec = secenekler(b)
            onizleme = None
            if form.get("kime") == "tumu" or form.get("hedef"):
                try:
                    temiz = hedef.dogrula({"tumu": True} if form.get("kime") == "tumu" else form["hedef"])
                    onizleme = {"sayi": len(hedef.coz(b, temiz)), "ozet": hedef.ozet(b, temiz)}
                except ValueError:
                    onizleme = None
        return y.sayfa(
            istek,
            "duyuru_form.html",
            k,
            durum_kodu=durum_kodu,
            form=form,
            plan=plan,
            duzenlenebilir=plan is None or yetkili_mi(k, plan["olusturan"]),
            hata=hata,
            secenekler=sec,
            onizleme=onizleme,
            on_secim=on_secim,
            bugun=_bugun(),
            sure_siniri=zamanlama.DUYURU_SURE_DK,
        )

    # ---- liste -------------------------------------------------------------------------
    @uygulama.get("/duyurular", response_class=HTMLResponse)
    async def duyurular(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        simdi = vt.simdi()
        with vt.islem() as b:
            yayindaki = b.execute(
                "SELECT * FROM duyuru WHERE durum = 'gonderildi' AND bitis > ? ORDER BY an DESC", (simdi,)
            ).fetchall()
            planlar = b.execute(
                "SELECT * FROM duyuru_plani WHERE durum != 'silindi' "
                "ORDER BY CASE durum WHEN 'etkin' THEN 0 WHEN 'duraklatildi' THEN 1 ELSE 2 END, id DESC"
            ).fetchall()
            gecmis = b.execute(f"SELECT * FROM duyuru ORDER BY an DESC, id DESC LIMIT {GECMIS_EN_COK}").fetchall()
            teslim = duyuru.teslimler(b, [d["id"] for d in [*yayindaki, *gecmis]])
            sahipler = {d["id"]: duyuru.sahip(b, d) for d in [*yayindaki, *gecmis]}
            plan_satirlari = []
            for p in planlar:
                try:
                    hedef_ozet = hedef.ozet(b, hedef.dogrula(p["hedef_json"]))
                except ValueError:
                    hedef_ozet = "—"
                sonraki = zamanlama.sonraki(p, simdi, 1) if p["durum"] == "etkin" else []
                plan_satirlari.append(
                    {
                        "id": p["id"],
                        "baslik": p["baslik"],
                        "metin": p["metin"][:120],
                        "zamanlama": zamanlama.ozet(p),
                        "hedef": hedef_ozet,
                        "sonraki": sonraki[0] if sonraki else None,
                        "durum": p["durum"],
                        "olusturan": p["olusturan"],
                        "yetkili": yetkili_mi(k, p["olusturan"]),
                    }
                )

        def yayin_satiri(d) -> dict:
            ulasan, toplam = teslim.get(d["id"], (0, 0))
            return {
                "id": d["id"],
                "an": d["an"],
                "bitis": d["bitis"],
                "baslik": d["baslik"],
                "metin": d["metin"][:120],
                "sure_dk": d["sure_sn"] // 60,
                "kapatilabilir": bool(d["kapatilabilir"]),
                "hedef": d["hedef"],
                "teslim": {"ulasan": ulasan, "toplam": toplam},
                "durum": d["durum"],
                "gonderen": f"sistem (plan #{d['plan_id']})" if d["plan_id"] else d["olusturan"],
                "plan_id": d["plan_id"],
                "durdurabilir": d["durum"] == "gonderildi" and (d["bitis"] or 0) > simdi and yetkili_mi(k, sahipler[d["id"]]),
                "yeniden": d["durum"] in ("kacirildi", "durduruldu"),
            }

        return y.sayfa(
            istek,
            "duyurular.html",
            k,
            yayinda=[yayin_satiri(d) for d in yayindaki],
            planlar=plan_satirlari,
            gecmis=[yayin_satiri(d) for d in gecmis],
        )

    # ---- form ---------------------------------------------------------------------------
    @uygulama.get("/duyurular/yeni", response_class=HTMLResponse)
    async def yeni_duyuru(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = bos_form()
        on_secim = None
        kopya, yayin_id = istek.query_params.get("kopya", ""), istek.query_params.get("yayin", "")
        with vt.islem() as b:
            kaynak = None  # kopyalanan plan ya da yayın; bulunamazsa ön seçime (?tahta=) bakılır
            if kopya.isdigit() and hedef.kimlik_mi(kopya):
                kaynak = b.execute("SELECT * FROM duyuru_plani WHERE id = ? AND durum != 'silindi'", (int(kopya),)).fetchone()
                if kaynak:
                    form = plandan_form(kaynak)
            elif yayin_id.isdigit() and hedef.kimlik_mi(yayin_id):
                kaynak = b.execute("SELECT * FROM duyuru WHERE id = ?", (int(yayin_id),)).fetchone()
                if kaynak:
                    form = yayindan_form(kaynak)
            if not kaynak:
                on_secim = _on_secim(b, istek.query_params)
                if on_secim is not None:
                    form.update(_hedef_formu({"tahtalar": on_secim["idler"]}))
        return form_sayfasi(istek, k, form, on_secim=on_secim)

    def _on_secim(b, sorgu) -> dict | None:
        """Tahtalar sayfasından gelen ön seçim (0.17.0): `?tahta=1&tahta=2` ya da `secimden=1`.

        Yalnız onaylı tahtalar kalır; geçerli tahta kalmasa da `kime` "secim" olur (boş hedef): form "Tüm tahtalar"a
        DÜŞMEZ, gönderilirse var olan doğrulama boş hedefi reddeder. Sorguda yalnız tahta kimliği vardır.
        {"idler": [...], "istenen": n, "atlanan": n, "sinavda": n} ya da ön seçim yoksa None. `sinavda`: seçilenlerden
        sınav penceresinde olanların sayısı (form bandında uyarı; satır içi duyuru formunun eski ek onayının yerine).
        """
        hamlar = sorgu.getlist("tahta")[:ON_SECIM_EN_COK]
        if not hamlar and "secimden" not in sorgu:
            return None
        adaylar = list(dict.fromkeys(int(d) for d in hamlar if str(d).isdigit() and hedef.kimlik_mi(d)))
        idler: list[int] = []
        if adaylar:
            isaret = ",".join("?" * len(adaylar))
            gecerli = {
                s["id"] for s in b.execute(f"SELECT id FROM tahta WHERE durum = 'onayli' AND id IN ({isaret})", adaylar)
            }
            idler = [d for d in adaylar if d in gecerli]
        sinavda = len(set(idler) & set(sinav.pencere_haritasi(b, vt.simdi()))) if idler else 0
        return {"idler": idler, "istenen": len(hamlar), "atlanan": len(set(hamlar)) - len(idler), "sinavda": sinavda}

    @uygulama.get("/duyurular/plan/{plan_id}", response_class=HTMLResponse)
    async def plan_sayfasi(istek: Request, plan_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        with vt.islem() as b:
            plan = b.execute("SELECT * FROM duyuru_plani WHERE id = ? AND durum != 'silindi'", (plan_id,)).fetchone()
        if not plan:
            return y.yonlendir("/duyurular", "Plan bulunamadı.", hata=True)
        return form_sayfasi(istek, k, plandan_form(plan), plan=plan)

    def formu_coz(form, simdi: int) -> tuple[dict, dict]:
        """(zamanlama sözlüğü, temiz hedef); hatada ValueError."""
        bilgi = zamanlama.form_coz(form, simdi)
        return bilgi, hedef.dogrula(hedef.formdan(form))

    @uygulama.post("/duyurular")
    async def duyuru_kaydet(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        simdi = vt.simdi()
        ip = y.istemci_ip(istek)
        try:
            bilgi, temiz = formu_coz(form, simdi)
        except ValueError as hata:
            if str(hata) == guvenlik.TC_KIMLIK_ILETISI:
                with vt.islem() as b:
                    vt.kayit_dus(b, k["ad"], "Duyuru reddedildi", "T.C. kimlik numarasına benzeyen sayı", ip)
            return form_sayfasi(istek, k, gonderilen_form(form), hata=str(hata), durum_kodu=400)
        if bilgi["zaman"] == "hemen":
            with vt.islem() as b:
                if not hedef.coz(b, temiz):
                    hata = "Bu seçim şu an hiçbir tahtaya ulaşmıyor; duyuru gönderilmedi."
                    sonuc = None
                else:
                    hata = ""
                    sonuc = duyuru.duyuru_yayimla(
                        b,
                        baslik=bilgi["baslik"],
                        metin=bilgi["metin"],
                        sure_sn=bilgi["sure_sn"],
                        kapatilabilir=bool(bilgi["kapatilabilir"]),
                        hedef=temiz,
                        olusturan=k["ad"],
                        an=simdi,
                        simdi=simdi,
                        ip=ip,
                    )
            if not sonuc:
                return form_sayfasi(istek, k, gonderilen_form(form), hata=hata, durum_kodu=400)
            y.uyandir_hepsi(sonuc[1])
            return y.yonlendir("/duyurular", f"Duyuru {len(sonuc[1])} tahtaya gönderildi.")
        with vt.islem() as b:
            plan_id = b.execute(
                "INSERT INTO duyuru_plani (baslik, metin, sure_sn, kapatilabilir, hedef_json, tekrar, saat, baslangic, "
                "bitis, gunler, durum, gecerlilik, olusturan, olusturma) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'etkin', ?, ?, ?)",
                (
                    bilgi["baslik"],
                    bilgi["metin"],
                    bilgi["sure_sn"],
                    bilgi["kapatilabilir"],
                    json.dumps(temiz, ensure_ascii=False),
                    bilgi["tekrar"],
                    bilgi["saat"],
                    bilgi["baslangic"],
                    bilgi["bitis"],
                    bilgi["gunler"],
                    simdi,
                    k["ad"],
                    simdi,
                ),
            ).lastrowid
            plan = b.execute("SELECT * FROM duyuru_plani WHERE id = ?", (plan_id,)).fetchone()
            sayi = len(hedef.coz(b, temiz))
            ozet = hedef.ozet(b, temiz)
            vt.kayit_dus(b, k["ad"], "Duyuru planı oluşturuldu", f"#{plan_id} {zamanlama.ozet(plan)} · {ozet}", ip)
        return y.yonlendir("/duyurular", plan_iletisi(plan, simdi, sayi))

    def plan_iletisi(plan, simdi: int, sayi: int) -> str:
        sonraki = zamanlama.sonraki(plan, simdi, 1)
        ileti = "Plan kaydedildi."
        ileti += f" Sonraki gösterim: {zamanlama.an_yaz(sonraki[0])}." if sonraki else " Planın ileride gösterimi yok."
        if not sayi:
            ileti += " Bu seçim şu an hiçbir tahtaya ulaşmıyor."
        return ileti

    @uygulama.post("/duyurular/plan/{plan_id}")
    async def plan_islem(istek: Request, plan_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        eylem = str(form.get("eylem", ""))
        simdi = vt.simdi()
        ip = y.istemci_ip(istek)
        with vt.islem() as b:
            plan = b.execute("SELECT * FROM duyuru_plani WHERE id = ? AND durum != 'silindi'", (plan_id,)).fetchone()
            if not plan:
                return y.yonlendir("/duyurular", "Plan bulunamadı.", hata=True)
            if not yetkili_mi(k, plan["olusturan"]):
                vt.kayit_dus(b, k["ad"], "Yetkisiz işlem reddedildi", f"Duyuru planı #{plan_id}: {eylem}", ip)
                return y.yonlendir(
                    "/duyurular", YETKI_ILETISI.format(tur="plan", sahip=plan["olusturan"]), hata=True
                )
            if eylem == "duraklat":
                if plan["durum"] != "etkin":
                    return y.yonlendir("/duyurular", "Yalnız etkin plan duraklatılabilir.", hata=True)
                b.execute(
                    "UPDATE duyuru_plani SET durum = 'duraklatildi', guncelleyen = ?, guncelleme = ? WHERE id = ?",
                    (k["ad"], simdi, plan_id),
                )
                vt.kayit_dus(b, k["ad"], "Duyuru planı duraklatıldı", f"#{plan_id} {zamanlama.ozet(plan)}", ip)
                return y.yonlendir("/duyurular", "Plan duraklatıldı. Yayındaki gösterim varsa ayrıca durdurun.")
            if eylem == "surdur":
                if plan["durum"] != "duraklatildi":
                    return y.yonlendir("/duyurular", "Yalnız duraklatılmış plan sürdürülebilir.", hata=True)
                # Duraklatma süresince geçen anlar ne yayımlanır ne kaçırıldı sayılır.
                b.execute(
                    "UPDATE duyuru_plani SET durum = 'etkin', gecerlilik = ?, guncelleyen = ?, guncelleme = ? WHERE id = ?",
                    (simdi, k["ad"], simdi, plan_id),
                )
                vt.kayit_dus(b, k["ad"], "Duyuru planı sürdürüldü", f"#{plan_id} {zamanlama.ozet(plan)}", ip)
                return y.yonlendir("/duyurular", "Plan sürdürüldü.")
            if eylem == "sil":
                b.execute(
                    "UPDATE duyuru_plani SET durum = 'silindi', guncelleyen = ?, guncelleme = ? WHERE id = ?",
                    (k["ad"], simdi, plan_id),
                )
                vt.kayit_dus(b, k["ad"], "Duyuru planı silindi", f"#{plan_id} {zamanlama.ozet(plan)}", ip)
                return y.yonlendir("/duyurular", "Plan silindi. Yayındaki gösterim varsa ayrıca durdurun.")
            if eylem != "kaydet":
                return y.yonlendir("/duyurular", "Bilinmeyen işlem.", hata=True)
        try:
            bilgi, temiz = formu_coz(form, simdi)
            if bilgi["zaman"] == "hemen":
                raise ValueError("Kayıtlı plan 'Hemen' olarak değiştirilemez; yeni duyuru oluşturun.")
        except ValueError as hata:
            if str(hata) == guvenlik.TC_KIMLIK_ILETISI:  # POST /duyurular ile aynı iz (numara yazılmaz)
                with vt.islem() as b:
                    vt.kayit_dus(b, k["ad"], "Duyuru reddedildi", f"Plan #{plan_id}: T.C. kimlik numarasına benzeyen sayı", ip)
            return form_sayfasi(istek, k, gonderilen_form(form), plan=plan, hata=str(hata), durum_kodu=400)
        with vt.islem() as b:
            b.execute(
                "UPDATE duyuru_plani SET baslik = ?, metin = ?, sure_sn = ?, kapatilabilir = ?, hedef_json = ?, tekrar = ?, "
                "saat = ?, baslangic = ?, bitis = ?, gunler = ?, gecerlilik = ?, guncelleyen = ?, guncelleme = ?, "
                "durum = CASE durum WHEN 'bitti' THEN 'etkin' ELSE durum END WHERE id = ?",
                (
                    bilgi["baslik"],
                    bilgi["metin"],
                    bilgi["sure_sn"],
                    bilgi["kapatilabilir"],
                    json.dumps(temiz, ensure_ascii=False),
                    bilgi["tekrar"],
                    bilgi["saat"],
                    bilgi["baslangic"],
                    bilgi["bitis"],
                    bilgi["gunler"],
                    simdi,
                    k["ad"],
                    simdi,
                    plan_id,
                ),
            )
            guncel = b.execute("SELECT * FROM duyuru_plani WHERE id = ?", (plan_id,)).fetchone()
            sayi = len(hedef.coz(b, temiz))
            vt.kayit_dus(
                b, k["ad"], "Duyuru planı düzenlendi", f"#{plan_id} {zamanlama.ozet(guncel)} · {hedef.ozet(b, temiz)}", ip
            )
        return y.yonlendir("/duyurular", plan_iletisi(guncel, simdi, sayi))

    # ---- yayınlar ------------------------------------------------------------------------
    @uygulama.post("/duyurular/yayin/{duyuru_id}/durdur")
    async def yayin_durdur(istek: Request, duyuru_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        ip = y.istemci_ip(istek)
        with vt.islem() as b:
            yayin = b.execute("SELECT * FROM duyuru WHERE id = ?", (duyuru_id,)).fetchone()
            if not yayin:
                return y.yonlendir("/duyurular", "Duyuru bulunamadı.", hata=True)
            sahip = duyuru.sahip(b, yayin)
            if not yetkili_mi(k, sahip):
                vt.kayit_dus(b, k["ad"], "Yetkisiz işlem reddedildi", f"Duyuru #{duyuru_id} durdurma", ip)
                return y.yonlendir("/duyurular", YETKI_ILETISI.format(tur="duyuru", sahip=sahip), hata=True)
            try:
                idler = duyuru.yayin_durdur(b, duyuru_id, k["ad"])
            except ValueError as hata:
                return y.yonlendir("/duyurular", str(hata), hata=True)
        y.uyandir_hepsi(idler)
        return y.yonlendir("/duyurular", "Duyuru durduruldu.")

    @uygulama.post("/duyurular/yayin/{duyuru_id}/yeniden")
    async def yayin_yeniden(istek: Request, duyuru_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        simdi = vt.simdi()
        with vt.islem() as b:
            yayin = b.execute("SELECT * FROM duyuru WHERE id = ?", (duyuru_id,)).fetchone()
            if not yayin or yayin["durum"] not in ("kacirildi", "durduruldu"):
                return y.yonlendir("/duyurular", "Yalnız kaçırılan ya da durdurulan duyuru yeniden gönderilir.", hata=True)
            try:
                temiz = hedef.dogrula(yayin["hedef_json"])
            except ValueError:
                return y.yonlendir("/duyurular", "Bu duyurunun hedefi okunamadı; yeni duyuru oluşturun.", hata=True)
            if not hedef.coz(b, temiz):
                return y.yonlendir("/duyurular", "Bu seçim şu an hiçbir tahtaya ulaşmıyor; duyuru gönderilmedi.", hata=True)
            _, idler = duyuru.duyuru_yayimla(
                b,
                baslik=yayin["baslik"],
                metin=yayin["metin"],
                sure_sn=yayin["sure_sn"],
                kapatilabilir=bool(yayin["kapatilabilir"]),
                hedef=temiz,
                olusturan=k["ad"],
                an=simdi,
                simdi=simdi,
                ip=y.istemci_ip(istek),
                kayit_ayrintisi=f"#{duyuru_id} yeniden gönderildi",
            )
        y.uyandir_hepsi(idler)
        return y.yonlendir("/duyurular", f"Duyuru yeniden gönderildi: {len(idler)} tahta.")

    # ---- hedef önizlemesi ---------------------------------------------------------------
    @uygulama.get("/api/hedef-onizleme")
    async def hedef_onizleme(istek: Request):
        if not y.kullanici(istek):
            return JSONResponse({"hata": "Oturum gerekli."}, status_code=401)
        ham = istek.query_params.get("hedef", "")
        if len(ham) > 20000:
            return JSONResponse({"hata": "Hedef çok uzun."}, status_code=400)
        try:
            temiz = hedef.dogrula(ham)
        except ValueError as hata:
            return JSONResponse({"hata": str(hata)}, status_code=400)
        with vt.islem() as b:
            tahtalar = hedef.coz(b, temiz)
            ozet = hedef.ozet(b, temiz)
            gorunum = [y.tahta_gorunumu(t) for t in tahtalar]
        return {
            "sayi": len(tahtalar),
            "ozet": ozet,
            "tahtalar": [{"id": t["id"], "ad": t["ad"], "derslik": t["derslik"], "cevrimici": t["cevrimici"]} for t in gorunum],
        }
