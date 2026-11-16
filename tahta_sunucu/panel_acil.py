"""Panel: acil durum ve tatbikat yayını (başlatma, bitirme, rapor).

Başlatma sırası kesindir: yetki → hız sınırı → parola → tür ve onay → metin → yayın.
Bitirmek parola istemez (güvenli yön). Kayıtlar silinmez; silme ucu yoktur.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import HTMLResponse

from . import acil, ayar, guvenlik, vt

GECMIS_EN_COK = 50
ONAY_METNI = {
    "acil": "Bu bir tatbikat DEĞİLDİR; gerçek acil durum yayını başlatıyorum.",
    "tatbikat": "Bu bir tatbikattır; tahtalarda 'TATBİKAT' olarak görünecek.",
}


def _sure_dk(baslangic: int, bitis: int | None) -> int:
    return max(0, round(((bitis or vt.simdi()) - baslangic) / 60))


def kaydet(uygulama, y) -> None:
    @uygulama.get("/acil", response_class=HTMLResponse)
    async def acil_sayfasi(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        return ciz(istek, k)

    def ciz(istek: Request, k, girilen: dict | None = None, hata: str = "") -> HTMLResponse:
        """Acil sayfası. Başlatma reddedilince (hata) sayfa aynı yanıtta 400 ile yeniden çizilir:
        tür, şablon, başlık, metin ve süre korunur; parola ve onay boş gelir."""
        ek: dict = {"mesaj": hata, "mesaj_hata": True} if hata else {}
        simdi = vt.simdi()
        with vt.islem() as b:
            yayin = acil.aktif(b, simdi)
            tahtalar = b.execute("SELECT * FROM tahta WHERE durum = 'onayli'").fetchall()
            eski_ajan = sum(1 for t in tahtalar if acil.ACIL_YETENEK not in acil.yetenekler(t))
            gecmis = b.execute(f"SELECT * FROM acil_yayin ORDER BY id DESC LIMIT {GECMIS_EN_COK}").fetchall()
            teslim = acil.teslim_sayilari(b, [g["id"] for g in gecmis])
            sablonlar = acil.sablonlar(b)
        aktif = None
        if yayin:
            aktif = {
                "id": yayin["id"],
                "tur": yayin["tur"],
                "baslik": yayin["baslik"],
                "metin": yayin["metin"],
                "baslatan": yayin["baslatan"],
                "baslangic": yayin["baslangic"],
                "bitis_plan": yayin["bitis_plan"],
                "kalan_sn": max(0, yayin["bitis_plan"] - simdi),
                "teslim": teslim.get(yayin["id"], 0),
                "hedef": yayin["hedef_sayisi"],
            }
        return y.sayfa(
            istek,
            "acil.html",
            k,
            durum_kodu=400 if hata else 200,
            girilen=girilen or {},
            **ek,
            aktif=aktif,
            yetkili=bool(k["acil_yetki"]),
            sablonlar=sablonlar,
            onay_metni=ONAY_METNI,
            varsayilan_sure=acil.ACIL_VARSAYILAN_DK,
            sure_siniri=acil.ACIL_SURE_DK,
            baslik_en_uzun=acil.BASLIK_EN_UZUN,
            metin_en_uzun=acil.METIN_EN_UZUN,
            hedef_sayisi=len(tahtalar),
            eski_ajan_sayisi=eski_ajan,
            gecmis=[
                {
                    "id": g["id"],
                    "tur": g["tur"],
                    "baslik": g["baslik"],
                    "baslangic": g["baslangic"],
                    "bitis": g["bitis"],
                    "sure_dk": _sure_dk(g["baslangic"], g["bitis"]),
                    "teslim": teslim.get(g["id"], 0),
                    "hedef": g["hedef_sayisi"],
                    "baslatan": g["baslatan"],
                    "bitiren": g["bitiren"],
                    "bitis_nedeni": g["bitis_nedeni"],
                    "suruyor": g["bitis"] is None and yayin is not None and yayin["id"] == g["id"],
                }
                for g in gecmis
            ],
        )

    @uygulama.post("/acil/baslat")
    async def acil_baslat(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        ip = y.istemci_ip(istek)
        form = await istek.form()
        # Hata olursa form bu değerlerle yeniden çizilir (parola ve onay hiç geri konmaz).
        girilen = {
            "tur": str(form.get("tur", "")),
            "sablon": str(form.get("sablon", "")),
            "baslik": str(form.get("baslik", ""))[: acil.BASLIK_EN_UZUN],
            "metin": str(form.get("metin", ""))[: acil.METIN_EN_UZUN],
            "sure_dk": str(form.get("sure_dk", ""))[:4],
        }

        def reddet(ileti: str, kayit: str = "") -> object:
            with vt.islem() as b:
                vt.kayit_dus(b, k["ad"], "Acil yayın reddedildi", kayit or ileti, ip)
            return ciz(istek, k, girilen, ileti)

        if not k["acil_yetki"]:
            return reddet("Acil yayın yetkiniz yok; yöneticiden isteyin.", "Acil yetkisi yok")
        if not y.hiz_siniri(y.giris_denemeleri, ip, 10, 300):
            return reddet("Çok fazla deneme yapıldı. Birkaç dakika sonra yeniden deneyin.", "Hız sınırı")
        with vt.islem() as b:
            satir = b.execute("SELECT parola_ozet FROM kullanici WHERE id = ?", (k["id"],)).fetchone()
        if not satir or not guvenlik.parola_dogrula(str(form.get("parola", "")), satir["parola_ozet"]):
            with vt.islem() as b:
                vt.kayit_dus(b, k["ad"], "Acil yayın: parola hatalı", "", ip)
            return ciz(istek, k, girilen, "Parola hatalı; yayın başlatılmadı.")
        tur = str(form.get("tur", ""))
        if tur not in acil.TURLER:
            return reddet("Yayın türünü seçin: gerçek acil durum ya da tatbikat.", "Tür seçilmedi")
        if form.get("onay") != "1":
            return reddet("Onay kutusunu işaretleyin.", "Onay verilmedi")
        baslik = " ".join(str(form.get("baslik", "")).split())[: acil.BASLIK_EN_UZUN]
        metin = str(form.get("metin", "")).strip()
        if not metin:
            return reddet("Yayın metni boş olamaz.")
        if len(metin) > acil.METIN_EN_UZUN:
            return reddet(f"Yayın metni en çok {acil.METIN_EN_UZUN} karakter olabilir.")
        try:
            sure_dk = int(str(form.get("sure_dk", acil.ACIL_VARSAYILAN_DK)) or acil.ACIL_VARSAYILAN_DK)
        except ValueError:
            sure_dk = 0
        if not acil.ACIL_SURE_DK[0] <= sure_dk <= acil.ACIL_SURE_DK[1]:
            return reddet(f"Süre {acil.ACIL_SURE_DK[0]}-{acil.ACIL_SURE_DK[1]} dakika olmalı.")
        if guvenlik.tc_kimlik_var(metin) or guvenlik.tc_kimlik_var(baslik):
            return reddet(guvenlik.TC_KIMLIK_ILETISI, "T.C. kimlik numarasına benzeyen sayı")
        with vt.islem() as b:
            kodlar = {s["kod"] for s in acil.sablonlar(b)}
            sablon = str(form.get("sablon", ""))
            acil_id, idler = acil.baslat(
                b,
                tur=tur,
                sablon=sablon if sablon in kodlar else "",
                # Boş başlık panel ve kayıt için varsayılanla dolar; tahta ekranı bant sözcüğüyle
                # aynı başlığı ikinci kez yazmaz (ekran.py).
                baslik=baslik or ("TATBİKAT" if tur == "tatbikat" else "ACİL DURUM"),
                metin=metin,
                sure_sn=sure_dk * 60,
                baslatan=k["ad"],
                ip=ip,
            )
        y.uyandir_hepsi(idler)
        return y.yonlendir(f"/acil/{acil_id}", "Yayın başlatıldı. Tahtalar birkaç saniye içinde gösterir.")

    @uygulama.post("/acil/{acil_id}/bitir")
    async def acil_bitir(istek: Request, acil_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        form = await istek.form()
        donus = str(form.get("donus", ""))
        donus = donus if donus.startswith("/") and not donus.startswith("//") else f"/acil/{acil_id}"
        ip = y.istemci_ip(istek)
        with vt.islem() as b:
            if not k["acil_yetki"]:
                vt.kayit_dus(b, k["ad"], "Acil yayın reddedildi", f"#{acil_id} bitirme: acil yetkisi yok", ip)
                return y.yonlendir(donus, "Acil yayın yetkiniz yok; yöneticiden isteyin.", hata=True)
            yayin = acil.aktif(b)
            if not yayin or yayin["id"] != acil_id:
                return y.yonlendir(donus, "Bu yayın zaten bitmiş.", hata=True)
            idler = acil.bitir(b, acil_id, bitiren=k["ad"], neden="panel", ip=ip)
            hepsi = [t["id"] for t in b.execute("SELECT id FROM tahta WHERE durum = 'onayli'")]
        y.uyandir_hepsi([*idler, *hepsi])
        return y.yonlendir(donus, "Yayın bitirildi; tahtalar önceki hâllerine döner.")

    @uygulama.get("/acil/{acil_id}", response_class=HTMLResponse)
    async def acil_rapor(istek: Request, acil_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        with vt.islem() as b:
            acil.aktif(b)  # süresi dolduysa kaydı kapansın
            yayin = b.execute("SELECT * FROM acil_yayin WHERE id = ?", (acil_id,)).fetchone()
            if not yayin:
                return y.yonlendir("/acil", "Yayın bulunamadı.", hata=True)
            satirlar = acil.rapor_satirlari(b, yayin, ayar.CEVRIMICI_ESIK_SN)
        teslim = [s for s in satirlar if s["ilk_gorulme"]]
        return y.sayfa(
            istek,
            "acil_rapor.html",
            k,
            yayin={
                **dict(yayin),
                "tur_adi": acil.TURLER.get(yayin["tur"], yayin["tur"]),
                "bitis_nedeni_adi": acil.BITIS_NEDENI.get(yayin["bitis_nedeni"], "—"),
                "sure_dk": _sure_dk(yayin["baslangic"], yayin["bitis"]),
                "suruyor": yayin["bitis"] is None,
            },
            satirlar=satirlar,
            sayilar={
                "hedef": yayin["hedef_sayisi"],
                "teslim": len(teslim),
                "acil_yol": sum(1 for s in teslim if s["yol"] == "Acil"),
                "yedek_yol": sum(1 for s in teslim if s["yol"] == "Yedek duyuru"),
            },
            yetkili=bool(k["acil_yetki"]),
        )
