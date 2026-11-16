"""Panel: zil düzenleyici uçları (0.10.0) — çizelgeler, haftalık düzen, tarihe özel çizelgeler, günü önizle.

Yetki: okuma iki role açık; her yazma yalnız yönetici (`panel_program.yetki_reddi`, ortak sözlük §3).
Her yazma tek `vt.islem()` içindedir ve sonunda `cizelge.haftalik_yaz` ile `ders_saati` yeniden yazılır;
bugünün planı değiştiyse program kaynaklı kilitli tahtalar açılır (şartname §6.3). Kaydetme, hızlı oluşturma,
CSV'den doldurma ve devre ekleme hata/taslakta yönlendirmez: çizelge sayfası taslakla yeniden çizilir
(hata varsa 422). İşlem kaydına çizelge ve tarihe özel kayıt adı, gün ve sayılar yazılır; kişi bilgisi yazılmaz.

Şablon sözleşmesi için `cizelge_baglami`, `gun_baglami` ve `panel_program.zil_baglami` belgelerine bakın.
"""

from __future__ import annotations

from datetime import date, datetime

from fastapi import Request
from fastapi.responses import HTMLResponse, Response
from starlette.datastructures import UploadFile

from . import cizelge, program, program_is, vt, zamanlama
from .panel_program import bellekte_form, govde_uzunlugu, yetki_reddi

ISTANBUL = program.ISTANBUL
TASLAK_BANDI = "Taslak — henüz kaydedilmedi."
HIZLI_BANDI = "Satırlar üretildi; gözden geçirip Kaydet'e basın. Kaydetmezseniz değişiklik olmaz."
CSV_BANDI = "Satırlar CSV'den dolduruldu; gözden geçirip Kaydet'e basın. Kaydetmezseniz değişiklik olmaz."
YENI_BANDI = "Varsayılan saatlerle oluşturuldu; düzenleyip kaydedin. Haftalık düzende bir güne atanana kadar kullanılmaz."
BUGUN_DEGISTI = (
    "Bugünkü ders saatleri değişti; program kilitli tahtalar açıldı, sonraki aralıktan itibaren yeni saatlerle kilitlenir."
)


def simdi_dt() -> datetime:
    return datetime.fromtimestamp(vt.simdi(), ISTANBUL)


# ---- etkiler (şartname §6) ---------------------------------------------------------------------------
def plan_imzasi(b, gun: date) -> tuple:
    plan = program.gun_plani(b, gun)
    return plan["tatil"], tuple((d[0], d[2], d[3], d[4]) for d in plan["dersler"])


class Etki:
    """Bir zil yazmasının öncesini tutar; `bitir` sonrasını karşılaştırıp etkileri uygular.

    Kullanım (aynı işlem içinde): e = Etki(b); …yazma…; cizelge.haftalik_yaz(b); iletiler = e.bitir(b, k).
    Uyandırma işlem dışından yapılır (`e.uyandir`), `e.bugun_degisti` ise zamanlayıcı belleği sıfırlanır.
    """

    def __init__(self, b):
        self.simdi = simdi_dt()
        self.once = plan_imzasi(b, self.simdi.date())
        self.yetim_once = cizelge.yetim_sayilari(b)
        self.uyandir: list[int] = []
        self.bugun_degisti = False

    def bitir(self, b, k) -> list[str]:
        iletiler: list[str] = []
        sonra = plan_imzasi(b, self.simdi.date())
        if sonra != self.once:
            dersler = [*self.once[1], *sonra[1]]
            if dersler:
                bas = min(d[2] for d in dersler)
                bit = max(d[3] for d in dersler)
                if bas <= self.simdi < bit:
                    self.uyandir = program_is.askiya_alma_acmasi(b, None, k["ad"])
                    self.bugun_degisti = True
                    iletiler.append(BUGUN_DEGISTI)
        yetim = cizelge.yetim_sayilari(b)
        if yetim[1] and yetim != self.yetim_once:
            iletiler.append(
                f"{yetim[0]} tahtanın derslik programında artık olmayan {yetim[1]} ders saati var; "
                "Derslik programları sekmesinden temizleyebilirsiniz."
            )
        return iletiler


def haftalik_ozeti(b) -> str:
    """İşlem kaydı için: "Pzt–Per: Normal gün · Cum: Cuma · Cmt, Paz: ders yok"."""
    adlar = {s["id"]: s["ad"] for s in b.execute("SELECT id, ad FROM zil_cizelgesi")}
    haftalik = cizelge.haftalik_oku(b)
    gruplar: dict[str, list[int]] = {}
    for gun in range(7):
        cid = haftalik.get(gun)
        gruplar.setdefault(adlar.get(cid, "ders yok") if cid else "ders yok", []).append(gun)
    return " · ".join(f"{cizelge.gun_araligi(g)}: {ad}" for ad, g in sorted(gruplar.items(), key=lambda x: x[1][0]))


def haftalik_uyarilari(b) -> list[str]:
    """Haftalık düzen uyarıları (şartname §5.4)."""
    satirlar = b.execute("SELECT gun, devre FROM ders_saati GROUP BY gun, devre").fetchall()
    if not cizelge.haftalik_oku(b) or not any(v for v in cizelge.haftalik_oku(b).values()):
        return ["Hiçbir güne çizelge atanmadı; program kilidi ve boş ders uyarısı çalışmaz."]
    gunler: dict[int, set[str]] = {}
    for s in satirlar:
        gunler.setdefault(s["gun"], set()).add(s["devre"])
    tekli = any("normal" in d and not d & {"sabah", "ogle"} for d in gunler.values())
    ikili = any(d & {"sabah", "ogle"} for d in gunler.values())
    if tekli and ikili:
        return ["Bazı günler tek devre, bazı günler ikili; derslik programı ızgarasında iki ayrı tablo görünür."]
    return []


def devre_sayilari(dersler) -> str:
    """İşlem kaydı için: "Sabah 6, Öğleden sonra 6"."""
    sayilar: dict[str, list] = {}
    for d in dersler:
        k = sayilar.setdefault(d[0], [d[1], 0, d[3]])
        k[1] += 1
        k[2] = min(k[2], d[3])
    return ", ".join(f"{k[0]} {k[1]}" for k in sorted(sayilar.values(), key=lambda k: k[2])) or "ders yok"


# ---- çizelge sayfası bağlamı ------------------------------------------------------------------------------
def cizelge_baglami(b, satir, taslak: dict, *, yonetici: bool, taslak_mi: bool = False, hatalar=None, uyarilar=None,
                    bant: str = "", hizli_p=None, hizli_acik: bool = False, numara=None, onay_numara: bool = False) -> dict:  # fmt: skip
    """cizelge.html bağlamı.

    {"cizelge": {"id","ad","kaynak","kaynak_metni","kullanim"}, "form_ad", "devreler": [{"devre","devre_adi","ders_sayisi",
    "satirlar": [{"r","bas","bit","sil","bos","no","sonraki_ara","hata_bas","hata_bit"}]}], "eksik_devreler": [(kimlik, ad)],
    "taslak_mi", "taslak_bandi", "bant", "hatalar": [{"metin","alan"}], "uyarilar", "hizli": [devre başına alanlar],
    "hizli_acik", "numara_onayi": {"metin"}|None, "onay_numara", "zaman_cizgisi", "yonetici", "csv_adresi"}.
    Satırlar devre içinde girildikleri sırada gelir; JS'siz kullanım için her devre sonunda 3 boş satır (`bos`).
    """
    hatalar = hatalar or []
    alan_hatasi = {h["alan"]: h["metin"] for h in hatalar if h.get("alan")}
    devreler = []
    numaralar = cizelge.numarala(taslak)
    for d in taslak["devreler"]:
        gecerli = cizelge._gecerli_satirlar(d)
        no_haritasi = {r: i for i, (_b, _s, r) in enumerate(gecerli, start=1)}
        ara_haritasi = {}
        for i, (_b, bit, r) in enumerate(gecerli):
            ara_haritasi[r] = program.dk(gecerli[i + 1][0]) - program.dk(bit) if i + 1 < len(gecerli) else None
        satirlar = []
        for s in d["satirlar"]:
            satirlar.append({**s, "bos": bool(s.get("bos")), "no": no_haritasi.get(s["r"]),
                             "sonraki_ara": cizelge.ara_metni(ara_haritasi.get(s["r"])) if s["r"] in no_haritasi else "",
                             "hata_bas": alan_hatasi.get(f"{s['r']}_bas"), "hata_bit": alan_hatasi.get(f"{s['r']}_bit")})  # fmt: skip
        devreler.append({"devre": d["devre"], "devre_adi": d["devre_adi"], "ders_sayisi": len(gecerli), "satirlar": satirlar})
    if yonetici:
        # Yeni boş satırların kimliği gönderilen kimliklerle çakışmasın (JS r25 gibi aralıklı kimlik verebilir).
        sira = 1 + max((int(s["r"][1:]) for d in devreler for s in d["satirlar"] if s["r"][1:].isdigit()), default=-1)
        for d in devreler:
            for _ in range(cizelge.BOS_SATIR):
                d["satirlar"].append({"r": f"r{sira}", "bas": "", "bit": "", "sil": False, "bos": True, "no": None,
                                      "sonraki_ara": "", "hata_bas": None, "hata_bit": None})  # fmt: skip
                sira += 1
    mevcut = {d["devre"] for d in taslak["devreler"]}
    kaynak = satir["kaynak"]
    kaynak_metni = cizelge.KAYNAK_ADI.get(kaynak, kaynak)
    if kaynak == "okulzili" and satir["guncelleme"]:
        kaynak_metni += " · elle düzenlendi"
    numara_onayi = None
    if numara:
        numara_onayi = {"metin": numara}
    return {
        "cizelge": {"id": satir["id"], "ad": satir["ad"], "kaynak": kaynak, "kaynak_metni": kaynak_metni,
                    "kullanim": cizelge.kullanim(b, satir["id"])},  # fmt: skip
        "form_ad": taslak["ad"],
        "devreler": devreler,
        "eksik_devreler": [(d, a) for d, a in cizelge.DEVRELER.items() if d not in mevcut],
        "taslak_mi": taslak_mi,
        "taslak_bandi": TASLAK_BANDI if taslak_mi else "",
        "bant": bant,
        "hatalar": hatalar,
        "uyarilar": uyarilar or [],
        "hizli": cizelge.hizli_degerleri(taslak, hizli_p),
        "hizli_acik": hizli_acik,
        "numara_onayi": numara_onayi,
        "onay_numara": onay_numara,
        "zaman_cizgisi": cizelge.zaman_cizgisi_derslerden(numaralar),
        "yonetici": yonetici,
        "csv_adresi": f"/program/cizelge/{satir['id']}/csv",
        "satir_ici_sayi": cizelge.BOS_SATIR,
    }


def gun_baglami(b, gun: date) -> dict:
    """program_gun.html bağlamı: {"tarih" (ISO), "tarih_metni" ("Pazartesi, 16.11.2026"), "kaynak", "tatil",
    "zaman_cizgisi", "sinavlar": ["10:00–11:20"], "tum_gun_sinav", "ders_var"}."""
    plan = program.gun_plani(b, gun)
    return {
        "tarih": gun.isoformat(),
        "tarih_metni": program_is.tarih_metni(gun),
        "kaynak": plan["kaynak"] if (plan["dersler"] or plan["tatil"] or "tarihe özel" in plan["kaynak"]) else "Ders yok",
        "tatil": plan["tatil"],
        "zaman_cizgisi": cizelge.zaman_cizgisi_plandan(plan),
        "sinavlar": [f"{a:%H:%M}–{s:%H:%M}" for a, s in plan["sinav"]],
        "tum_gun_sinav": plan["tum_gun_sinav"],
        "ders_var": bool(plan["dersler"]),
    }


HIZLI_ALAN_IPUCLARI = (
    ("uzun aranın yeri", "us"), ("uzun ara (dk)", "ud"), ("ders sayısı", "sayi"), ("ders süresi", "sure"),
    ("teneffüs", "ten"), ("ilk ders", "ilk"), ("gece yarısını", "ilk"),
)  # fmt: skip


def hizli_alani(taslak: dict, hata: str) -> str | None:
    """Hızlı oluştur hatasının alan kimliği (h-<devre>-<ek>); bulunamazsa None."""
    for d in taslak["devreler"]:
        if hata.startswith(f"{d['devre_adi']}:") or (d["devre"] == "ogle" and hata.startswith("Öğleden sonra devresinin")):
            kucuk = hata.lower()
            for ipucu, ek in HIZLI_ALAN_IPUCLARI:
                if ipucu in kucuk:
                    return f"h-{d['devre']}-{ek}"
            return f"h-{d['devre']}-ilk"
    return None


def numara_iletisi(b, kayma, cizelge_id: int, eski, yeni) -> str:
    parcalar = []
    for adi, e, y_, t in kayma:
        parcalar.append(
            f"{adi}: ders sayısı {e} → {y_}. Derslik programları ve yoklama ders numarasına bağlıdır; araya eklenen ya da "
            f"silinen ders sonraki derslerin numarasını kaydırır ({t} tahta etkilenir)."
        )
    metin_ = " ".join(parcalar) + " Derslik programlarını gözden geçireceğinizi onaylayıp yeniden kaydedin."
    bugun = simdi_dt().date()
    kural = cizelge.tarihli_kural(b, bugun)
    bugunku = (kural or {}).get("cizelge_id") if kural else cizelge.haftalik_oku(b).get(bugun.weekday())
    if bugunku == cizelge_id:
        y_sayi = b.execute("SELECT COUNT(*) FROM yoklama WHERE tarih = ?", (bugun.isoformat(),)).fetchone()[0]
        if y_sayi:
            metin_ += f" Bugün alınmış {y_sayi} yoklama eski numarasıyla kalır."
    return metin_


def kaydet(uygulama, y) -> None:
    def yetkisiz(istek: Request, k, islem: str, donus: str = "/program?bolum=zil"):
        return yetki_reddi(y, istek, k, islem, donus)

    def sonrasi(etki: Etki | None) -> None:
        """İşlemden sonra: uyandırma ve zamanlayıcı belleği."""
        if not etki:
            return
        if etki.bugun_degisti:
            isleyici = getattr(uygulama.state, "program_isleyici", None)
            if isleyici is not None:
                isleyici.bugun_degisti()
        y.uyandir_hepsi(etki.uyandir)

    def cizelge_satiri(b, cizelge_id: int):
        return b.execute("SELECT * FROM zil_cizelgesi WHERE id = ?", (cizelge_id,)).fetchone()

    def diger_adlar(b, cizelge_id: int | None) -> list[str]:
        return [s["ad"] for s in b.execute("SELECT id, ad FROM zil_cizelgesi") if s["id"] != cizelge_id]

    def devre_adlari(b, cizelge_id: int) -> dict[str, str]:
        return {d[0]: d[1] for d in cizelge.cizelge_dersleri(b, cizelge_id)}

    def ciz(istek, k, baglam: dict, durum_kodu: int = 200, **ek):
        ek.setdefault("hizli_hatali", set())
        return y.sayfa(istek, "cizelge.html", k, durum_kodu=durum_kodu, bolum="zil", **baglam, **ek)

    # ---- günü önizle ---------------------------------------------------------------------------------
    @uygulama.get("/program/gun", response_class=HTMLResponse)
    async def gun_onizle(istek: Request):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        try:
            gun = zamanlama.tarih_coz(istek.query_params.get("tarih") or "")
        except ValueError:
            gun = simdi_dt().date()
        with vt.islem() as b:
            baglam = gun_baglami(b, gun)
            serit = program_is.program_ozeti(b, simdi_dt())
        return y.sayfa(istek, "program_gun.html", k, gun=baglam, serit=serit, bolum="zil", yonetici=k["rol"] == "yonetici")

    # ---- yeni çizelge ---------------------------------------------------------------------------------
    @uygulama.post("/program/cizelge")
    async def cizelge_yeni(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Zil çizelgesi oluşturma")
        if engel:
            return engel
        form = await istek.form()
        ad = cizelge.ad_temizle(form.get("ad"))
        duzen = "ikili" if form.get("duzen") == "ikili" else "tek"
        with vt.islem() as b:
            hatalar, _ = cizelge.dogrula({"ad": ad, "devreler": []}, ad, diger_adlar(b, None))
            hatalar = [h for h in hatalar if h.get("alan") == "cizelge-ad"]
            if hatalar:
                return y.yonlendir("/program?bolum=zil&yer=cizelgeler#ileti", hatalar[0]["metin"], hata=True)
            dersler = cizelge.numarala(cizelge.varsayilan_taslak(ad, duzen))
            kimlik = cizelge.cizelge_ekle(b, ad, dersler, "elle", k["ad"])
            vt.kayit_dus(b, k["ad"], "Zil çizelgesi oluşturuldu", f"{ad} · {devre_sayilari(dersler)}", y.istemci_ip(istek))
        return y.yonlendir(f"/program/cizelge/{kimlik}?yeni=1", YENI_BANDI)

    # ---- çizelge sayfası ------------------------------------------------------------------------------
    @uygulama.get("/program/cizelge/{cizelge_id}", response_class=HTMLResponse)
    async def cizelge_sayfasi(istek: Request, cizelge_id: int):
        k = y.kullanici(istek)
        if not k:
            return y.yonlendir("/giris")
        with vt.islem() as b:
            satir = cizelge_satiri(b, cizelge_id)
            if not satir:
                return y.yonlendir("/program?bolum=zil", "Çizelge bulunamadı.", hata=True)
            taslak = cizelge.taslak_dbden(b, cizelge_id)
            baglam = cizelge_baglami(b, satir, taslak, yonetici=k["rol"] == "yonetici",
                                     hizli_acik=istek.query_params.get("yeni") == "1")  # fmt: skip
        return ciz(istek, k, baglam)

    @uygulama.post("/program/cizelge/{cizelge_id}")
    async def cizelge_kaydet(istek: Request, cizelge_id: int):
        k = y.kullanici(istek)
        donus = f"/program/cizelge/{cizelge_id}"
        engel = yetkisiz(istek, k, f"Zil çizelgesi #{cizelge_id} kaydetme", donus)
        if engel:
            return engel
        form = await istek.form()
        eylem = str(form.get("eylem", "kaydet"))
        etki = None
        with vt.islem() as b:
            satir = cizelge_satiri(b, cizelge_id)
            if not satir:
                return y.yonlendir("/program?bolum=zil", "Çizelge bulunamadı.", hata=True)
            taslak = cizelge.taslak_formdan(form, devre_adlari(b, cizelge_id))
            if eylem == "devre_ekle":
                devre = str(form.get("yeni_devre", ""))
                if devre in cizelge.DEVRELER and devre not in {d["devre"] for d in taslak["devreler"]}:
                    taslak["devreler"].append({"devre": devre, "devre_adi": cizelge.DEVRELER[devre], "satirlar": []})
                cizelge.kimlikleri_yenile(taslak)
                return ciz(istek, k, cizelge_baglami(b, satir, taslak, yonetici=True, taslak_mi=True))
            if eylem != "kaydet":
                return y.yonlendir(donus, "Bilinmeyen işlem.", hata=True)
            hatalar, uyarilar = cizelge.dogrula(taslak, taslak["ad"], diger_adlar(b, cizelge_id))
            if hatalar:
                return ciz(istek, k, cizelge_baglami(b, satir, taslak, yonetici=True, taslak_mi=True, hatalar=hatalar,
                                                     uyarilar=uyarilar), 422)  # fmt: skip
            eski = cizelge.cizelge_dersleri(b, cizelge_id)
            yeni = cizelge.numarala(taslak)
            kayma = cizelge.numara_kaymasi(b, cizelge_id, eski, yeni)
            onay = form.get("onay_numara") == "1"
            if kayma and not onay:
                metin_ = numara_iletisi(b, kayma, cizelge_id, eski, yeni)
                return ciz(istek, k, cizelge_baglami(b, satir, taslak, yonetici=True, taslak_mi=True, uyarilar=uyarilar,
                                                     numara=metin_), 422)  # fmt: skip
            etki = Etki(b)
            b.execute(
                "UPDATE zil_cizelgesi SET ad = ?, guncelleyen = ?, guncelleme = ? WHERE id = ?",
                (taslak["ad"], k["ad"], vt.simdi(), cizelge_id),
            )
            cizelge.dersler_yaz(b, cizelge_id, yeni)
            cizelge.haftalik_yaz(b)
            kaynak = vt.ayar_al(b, "zil_kaynagi")
            if satir["kaynak"] == "okulzili" and isinstance(kaynak, dict) and kaynak.get("tur") == "okulzili":
                vt.ayar_yaz(b, "zil_kaynagi", {**kaynak, "duzenlendi": True})
            elif not isinstance(kaynak, dict):
                vt.ayar_yaz(b, "zil_kaynagi", {"tur": "elle", "dosya_ozet": "", "dosya_yolu": "", "dosya_zamani": None,
                                               "yukleme": vt.simdi(), "yukleyen": k["ad"], "duzenlendi": False})  # fmt: skip
            iletiler = etki.bitir(b, k)
            kullanim = cizelge.kullanim(b, cizelge_id)
            ayrinti = f"{taslak['ad']} · {devre_sayilari(yeni)} · kullanımda: {kullanim}"
            if kayma:
                ayrinti += " · numara kayması onaylandı"
            vt.kayit_dus(b, k["ad"], "Zil çizelgesi kaydedildi", ayrinti, y.istemci_ip(istek))
        sonrasi(etki)
        return y.yonlendir(donus, " ".join(["Çizelge kaydedildi.", *uyarilar, *iletiler]))

    @uygulama.post("/program/cizelge/{cizelge_id}/hizli")
    async def cizelge_hizli(istek: Request, cizelge_id: int):
        k = y.kullanici(istek)
        donus = f"/program/cizelge/{cizelge_id}"
        engel = yetkisiz(istek, k, f"Zil çizelgesi #{cizelge_id} hızlı oluştur", donus)
        if engel:
            return engel
        form = await istek.form()
        with vt.islem() as b:
            satir = cizelge_satiri(b, cizelge_id)
            if not satir:
                return y.yonlendir("/program?bolum=zil", "Çizelge bulunamadı.", hata=True)
            # Form düzenleme tablosunu da taşıyorsa o taslak, yoksa kayıtlı çizelge temel alınır.
            taslak = cizelge.taslak_formdan(form, devre_adlari(b, cizelge_id)) if form.getlist("satir") or form.getlist("devre") \
                else cizelge.taslak_dbden(b, cizelge_id)  # fmt: skip
            if not taslak["ad"]:
                taslak["ad"] = satir["ad"]
            # JS yokken tablo bu forma gelmez: "Devre ekle" ile eklenip kaydedilmemiş devre kayıtlı taslakta yoktur.
            # Formda üretilmesi istenen her bilinen devre taslağa (boş) eklenir ki sessizce düşmesin.
            mevcut = {d["devre"] for d in taslak["devreler"]}
            for devre, adi in cizelge.DEVRELER.items():
                if devre not in mevcut and str(form.get(f"{devre}_uret", "")) == "1":
                    taslak["devreler"].append({"devre": devre, "devre_adi": adi, "satirlar": []})
            yeni, hatalar = cizelge.hizli_uret(form, taslak)
            if hatalar:
                yapili = [{"metin": h, "alan": hizli_alani(taslak, h)} for h in hatalar]
                return ciz(istek, k, cizelge_baglami(b, satir, taslak, yonetici=True, taslak_mi=True, hatalar=yapili,
                                                     hizli_p=form, hizli_acik=True), 422,
                           hatalar_basligi="Satırlar üretilemedi; şunları düzeltin:",
                           hizli_hatali={h["alan"] for h in yapili if h["alan"]})  # fmt: skip
            _, uyarilar = cizelge.dogrula(yeni)
            return ciz(istek, k, cizelge_baglami(b, satir, yeni, yonetici=True, taslak_mi=True, uyarilar=uyarilar,
                                                 bant=HIZLI_BANDI, hizli_p=form, hizli_acik=True))  # fmt: skip

    @uygulama.post("/program/cizelge/{cizelge_id}/kopyala")
    async def cizelge_kopyala(istek: Request, cizelge_id: int):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, f"Zil çizelgesi #{cizelge_id} kopyalama")
        if engel:
            return engel
        with vt.islem() as b:
            satir = cizelge_satiri(b, cizelge_id)
            if not satir:
                return y.yonlendir("/program?bolum=zil", "Çizelge bulunamadı.", hata=True)
            ad = cizelge.benzersiz_ad(b, satir["ad"][: cizelge.AD_EN_UZUN - 8].rstrip() + " (kopya)")
            kimlik = cizelge.cizelge_ekle(b, ad, cizelge.cizelge_dersleri(b, cizelge_id), "elle", k["ad"])
            vt.kayit_dus(b, k["ad"], "Zil çizelgesi kopyalandı", f"{satir['ad']} → {ad}", y.istemci_ip(istek))
        return y.yonlendir(f"/program/cizelge/{kimlik}", f"'{ad}' oluşturuldu; düzenleyip kaydedin.")

    @uygulama.post("/program/cizelge/{cizelge_id}/sil")
    async def cizelge_sil(istek: Request, cizelge_id: int):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, f"Zil çizelgesi #{cizelge_id} silme")
        if engel:
            return engel
        with vt.islem() as b:
            satir = cizelge_satiri(b, cizelge_id)
            if not satir:
                return y.yonlendir("/program?bolum=zil", "Çizelge bulunamadı.", hata=True)
            bilgi = cizelge.kullanim_bilgisi(b, cizelge_id)
            if bilgi["kullaniliyor"]:
                return y.yonlendir(
                    "/program?bolum=zil&yer=cizelgeler#ileti",
                    f"Bu çizelge kullanılıyor: {bilgi['metin']}. Önce haftalık düzenden ve tarihe özel çizelgelerden kaldırın.",
                    hata=True,
                )
            b.execute("DELETE FROM zil_cizelgesi WHERE id = ?", (cizelge_id,))
            vt.kayit_dus(b, k["ad"], "Zil çizelgesi silindi", satir["ad"], y.istemci_ip(istek))
        return y.yonlendir("/program?bolum=zil&yer=cizelgeler#ileti", f"'{satir['ad']}' silindi.")

    # ---- CSV ------------------------------------------------------------------------------------------
    @uygulama.get("/program/cizelge/{cizelge_id}/csv")
    async def cizelge_csv(istek: Request, cizelge_id: int):
        if not y.kullanici(istek):
            return y.yonlendir("/giris")
        with vt.islem() as b:
            satir = cizelge_satiri(b, cizelge_id)
            if not satir:
                return y.yonlendir("/program?bolum=zil", "Çizelge bulunamadı.", hata=True)
            icerik = cizelge.csv_yaz(cizelge.cizelge_dersleri(b, cizelge_id))
        return Response(
            icerik,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="cizelge-{cizelge.ascii_ad(satir["ad"])}.csv"'},
        )

    @uygulama.post("/program/cizelge/{cizelge_id}/csv")
    async def cizelge_csv_yukle(istek: Request, cizelge_id: int):
        k = y.kullanici(istek)
        donus = f"/program/cizelge/{cizelge_id}"
        engel = yetkisiz(istek, k, f"Zil çizelgesi #{cizelge_id} CSV", donus)
        if engel:
            return engel
        uzunluk = govde_uzunlugu(istek)
        if uzunluk is None:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        if uzunluk > cizelge.CSV_EN_COK_BAYT + 16 * 1024:
            return y.yonlendir(donus, "Dosya en çok 64 KB olabilir.", hata=True)
        try:
            form = await bellekte_form(istek, cizelge.CSV_EN_COK_BAYT + 16 * 1024)
        except Exception:
            return y.yonlendir(donus, "Dosya okunamadı.", hata=True)
        try:
            dosya = form.get("dosya")
            if not isinstance(dosya, UploadFile) or not dosya.filename:
                return y.yonlendir(donus, "CSV dosyası seçilmedi.", hata=True)
            bayt = await dosya.read(cizelge.CSV_EN_COK_BAYT + 1)
        finally:
            await form.close()
        with vt.islem() as b:
            satir = cizelge_satiri(b, cizelge_id)
            if not satir:
                return y.yonlendir("/program?bolum=zil", "Çizelge bulunamadı.", hata=True)
            adlar = {d[0]: d[1] for d in cizelge.cizelge_dersleri(b, cizelge_id)}
            try:
                devreler, satir_hatalari = cizelge.csv_oku(bayt, adlar)
            except ValueError as hata:
                return y.yonlendir(donus, str(hata), hata=True)
            taslak = cizelge.kimlikleri_yenile({"ad": satir["ad"], "devreler": devreler})
            hatalar = [{"metin": h, "alan": None} for h in satir_hatalari]
            _, uyarilar = cizelge.dogrula(taslak)
            return ciz(istek, k, cizelge_baglami(b, satir, taslak, yonetici=True, taslak_mi=True, hatalar=hatalar,
                                                 uyarilar=uyarilar, bant=CSV_BANDI), 422 if hatalar else 200)  # fmt: skip

    # ---- haftalık düzen ----------------------------------------------------------------------------------
    @uygulama.post("/program/haftalik")
    async def haftalik_kaydet(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Haftalık zil düzeni")
        if engel:
            return engel
        form = await istek.form()
        donus = "/program?bolum=zil&yer=haftalik#ileti"
        with vt.islem() as b:
            gecerli = {s["id"] for s in b.execute("SELECT id FROM zil_cizelgesi")}
            atama: dict[int, int] = {}
            for gun in range(7):
                ham = str(form.get(f"gun_{gun}", "")).strip()
                if not ham:
                    continue
                if not ham.isdigit() or int(ham) not in gecerli:
                    return y.yonlendir(donus, f"{program.GUN_ADLARI[gun]}: çizelge bulunamadı.", hata=True)
                atama[gun] = int(ham)
            etki = Etki(b)
            b.execute("DELETE FROM zil_haftalik")
            b.executemany("INSERT INTO zil_haftalik (gun, cizelge_id) VALUES (?, ?)", sorted(atama.items()))
            cizelge.haftalik_yaz(b)
            iletiler = etki.bitir(b, k)
            uyarilar = haftalik_uyarilari(b)
            vt.kayit_dus(b, k["ad"], "Haftalık zil düzeni kaydedildi", haftalik_ozeti(b), y.istemci_ip(istek))
        sonrasi(etki)
        return y.yonlendir(donus, " ".join(["Haftalık düzen kaydedildi.", *uyarilar, *iletiler]))

    # ---- tarihe özel çizelgeler ----------------------------------------------------------------------------
    @uygulama.post("/program/tarihli")
    async def tarihli_ekle(istek: Request):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, "Tarihe özel çizelge ekleme")
        if engel:
            return engel
        form = await istek.form()
        donus = "/program?bolum=zil&yer=tarihli#ileti"
        ham_cizelge = str(form.get("cizelge", "")).strip()
        with vt.islem() as b:
            degerler, hatalar = cizelge.tarihli_dogrula(
                b, form.get("ad"), form.get("bas"), form.get("bit"), form.getlist("gunler"), simdi_dt().date()
            )
            cizelge_id = None
            cizelge_adi = "Ders yok"
            if ham_cizelge:
                satir = cizelge_satiri(b, int(ham_cizelge)) if ham_cizelge.isdigit() else None
                if not satir:
                    hatalar.append("Çizelge bulunamadı.")
                else:
                    cizelge_id, cizelge_adi = satir["id"], satir["ad"]
            tc_var = any(h == cizelge.TC_ILETISI for h in hatalar)
            if hatalar and tc_var:
                vt.kayit_dus(b, k["ad"], "Tarihe özel çizelge reddedildi", "T.C. kimlik numarasına benzeyen sayı",
                             y.istemci_ip(istek))  # fmt: skip
            if not hatalar:
                etki = Etki(b)
                b.execute(
                    "INSERT INTO zil_tarihli (ad, bas, bit, gunler, cizelge_id, olusturan, olusturma) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (degerler["ad"], degerler["bas"], degerler["bit"], ",".join(map(str, degerler["gunler"])), cizelge_id,
                     k["ad"], vt.simdi()),
                )  # fmt: skip
                iletiler = etki.bitir(b, k)
                if cizelge_id is not None:
                    uyari = program_is.devre_uyusmazligi(b, devre_adlari(b, cizelge_id), degerler["gunler"])
                    if uyari:
                        iletiler.append(uyari)
                aralik = cizelge.aralik_metni(degerler["bas"], degerler["bit"])
                vt.kayit_dus(
                    b, k["ad"], "Tarihe özel çizelge eklendi",
                    f"{degerler['ad']} · {aralik} · {cizelge.gun_araligi(degerler['gunler'])} · {cizelge_adi}",
                    y.istemci_ip(istek),
                )  # fmt: skip
        if hatalar:
            # Yönlendirmeden yeniden çiz (422): girilen değerler kaybolmasın. Kimlik numarasına benzeyen ad geri yazılmaz.
            tarihli_form = {
                "ad": "" if tc_var else str(form.get("ad") or "")[: cizelge.TARIHLI_AD_EN_UZUN],
                "bas": str(form.get("bas") or "")[:10],
                "bit": str(form.get("bit") or "")[:10],
                "gunler": [int(g) for g in form.getlist("gunler") if str(g).isdigit() and int(g) < 7],
                "cizelge": ham_cizelge[:12],
                "hata_tarih": any("tarih" in h.lower() or "aralık" in h.lower() for h in hatalar),
            }
            return uygulama.state.program_ciz(istek, k, 422, mesaj=" ".join(hatalar), mesaj_hata=True,
                                              ileti_yeri="tarihli", tarihli_form=tarihli_form)  # fmt: skip
        sonrasi(etki)
        return y.yonlendir(donus, " ".join([f"'{degerler['ad']}' eklendi ({aralik}).", *iletiler]))

    @uygulama.post("/program/tarihli/{tarihli_id}/sil")
    async def tarihli_sil(istek: Request, tarihli_id: int):
        k = y.kullanici(istek)
        engel = yetkisiz(istek, k, f"Tarihe özel çizelge #{tarihli_id} silme")
        if engel:
            return engel
        donus = "/program?bolum=zil&yer=tarihli#ileti"
        with vt.islem() as b:
            satir = b.execute("SELECT * FROM zil_tarihli WHERE id = ?", (tarihli_id,)).fetchone()
            if not satir:
                return y.yonlendir(donus, "Tarihe özel çizelge bulunamadı.", hata=True)
            etki = Etki(b)
            b.execute("DELETE FROM zil_tarihli WHERE id = ?", (tarihli_id,))
            iletiler = etki.bitir(b, k)
            aralik = cizelge.aralik_metni(satir["bas"], satir["bit"])
            vt.kayit_dus(b, k["ad"], "Tarihe özel çizelge silindi", f"{satir['ad']} · {aralik}", y.istemci_ip(istek))
        sonrasi(etki)
        return y.yonlendir(donus, " ".join([f"'{satir['ad']}' silindi.", *iletiler]))

    uygulama.state.zil_etki_sonrasi = sonrasi
