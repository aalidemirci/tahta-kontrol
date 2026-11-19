"""Genel aramanın dizini (0.20.0, FastAPI'siz): TEK yer.

Dizin var olan tek tanımlardan TÜRETİLİR; burada sayfa, sekme, ayar ya da süzgeç adı yazılmaz:
  sayfa   web.MENU + web.MENU_ACIL              sekme   bolum_serit.SERITLER (dış bağlantı olmayanlar)
  suzgec  tahta_liste.SUZGECLER                 ayar    ayar_bolumleri.BOLUMLER
  is      ayar_bolumleri.BASKA_YERDE + SIK_ISLER (aşağıda; yalnız var olan GET sayfasına giden kısa yol)
  tahta   onaylı tahtalar (ad, derslik, bina, kat, şubeler)      sube   etkin öğrencisi olan şubeler
  grup    tahta grupları (yalnız yönetici isteğinde sorgulanır; açıklama okunmaz)

Rol süzmesi dizinin İÇİNDEDİR ve girdinin rolü hedef adresinden türer (`yer_coz`): hedef sayfa menüde ya da sekme
şeridinde yöneticiye özelse girdi de öyledir. Süzme eşleştirmeden ÖNCE yapılır; sayılar da süzülmüş kümedendir.

GİZLİLİK (bağlayıcı): dizine öğrenci adı/okul no, öğretmen adı/kodu, panel kullanıcı adı, USB anahtar etiketi,
mazeret, yoklama kaydı, duyuru başlığı/metni, arıza açıklaması, sınav adı, ders başlığı, tahtanın ağ adresi,
makine adı, demirbaş no, envanter notu, onay bekleyen tahta, grup açıklaması ve ayar DEĞERLERİ girmez. Bu
tablolara arama yolundan sorgu gitmez; "sonuç yok" notu sabittir. Sorgu hiçbir yere yazılmaz (kayıt, günlük, tablo).

Eşleştirme yalnız buradadır (panel.js'e kural, dizin ya da harf haritası kopyalanmaz). Metin ilkel işlevleri
`ayar_bolumleri`'ndekilerdir: Ayarlar içi aramayla aynı küçültme, aynı harf katlama, aynı "sözcük başı" kuralı.
Tek ek, en alt kademedeki "ekli sözcük" eşleşmesidir (`_ekli_uyar`): "pusulası" → "pusula", "tahtaları" → "tahta".
"""

from __future__ import annotations

from urllib.parse import quote

from . import bolum_serit, hedef, metin, tahta_liste, yoklama
from .ayar_bolumleri import (
    BASKA_YERDE,
    BOLUMLER,
    SORGU_EN_UZUN,
    katla,
    kucult,
    samanlik,
    sozcukler,
    uyar,
)

YONETICI = bolum_serit.YONETICI
TUR_SIRASI = ("sayfa", "sekme", "is", "suzgec", "ayar", "sube", "tahta", "grup")
# Sonuç sayfasındaki gruplar (başlıkları şablondadır): tür → grup anahtarı.
TUR_GRUBU = {"sayfa": "sayfa", "sekme": "sayfa", "is": "sayfa", "suzgec": "sayfa", "ayar": "ayar", "sube": "sube",
             "tahta": "tahta", "grup": "grup"}  # fmt: skip
GRUP_SIRASI = ("sayfa", "ayar", "sube", "tahta", "grup")
ONERI_EN_COK = 8
SAYFA_EN_COK = 50
SOZCUK_EN_COK = 6
ONERI_EN_KISA = 2  # /api/ara bundan kısa sorguda veritabanına gitmez
EK_KOK_EN_KISA = 4  # ekli sözcük eşleşmesinde dizindeki kökün en kısa boyu ("kod" → "kodu" gürültüsü olmasın)
SIK_EN_COK = 8  # sorgu boşken gösterilen kısa yol sayısı
AYRAC = " › "

# Sık işler: var olan GET sayfalarına giden kısa yollar (test eder). `yer` ve rol hedeften türer (yer_coz); açık
# `rol` yalnız DARALTIR (hedef herkese açık ama iş yöneticinin). POST gerektiren iş, indirme adresi, kişi adı,
# kurum adı, ağ adresi buraya yazılmaz. Arama girdisi eklemek = buraya bir öğe. `one` (1…): sorgu boşken gösterilen
# "Sık işler"deki sırası (en çok SIK_EN_COK tane; günlük iş sırası); `one` taşımayan iş yalnız aranınca çıkar.
SIK_ISLER: list[dict] = [
    {"ad": "Duyuru yap", "yol": "/duyurular/yeni", "one": 1,
     "sozcukler": "yeni duyuru mesaj anons ilan gönder yayımla yaz planla zamanla yarın tekrarlı"},
    {"ad": "Kapat, kilitle, yeniden başlat (tahtalar)", "yol": "/tahtalar", "one": 2,
     "sozcukler": "tahtaları kapatma kilit kilidi aç uzaktan komut seç"},
    {"ad": "Planlı duyurular", "yol": "/duyurular",
     "sozcukler": "plan zamanlanmış tekrarlı duraklat durdur kaçırılan"},
    {"ad": "Bütün tahtaları kilitle", "yol": "/#bugun-tahtalar", "one": 3,
     "sozcukler": "hepsini kilitle toplu kilit tüm tahtalar"},
    {"ad": "Acil durum ya da tatbikat yayını başlat", "yol": "/acil",
     "sozcukler": "acil yangın deprem tahliye tatbikat alarm siren"},
    {"ad": "Acil yayın raporları", "yol": "/acil?sekme=gecmis",
     "sozcukler": "acil geçmiş rapor teslim tatbikat"},
    {"ad": "Tahta ekle, ajan paketini indir", "yol": "/ekle",
     "sozcukler": "yeni tahta kur kurulum ajan paket deb usb indir etap pardus"},
    {"ad": "Onay bekleyen tahtalar", "yol": "/tahtalar#onay-bekleyen", "rol": YONETICI,
     "sozcukler": "onay onayla bekleyen yeni tahta"},
    {"ad": "Arıza kayıtları", "yol": "/arizalar", "one": 8,
     "sozcukler": "arıza bozuk tamir bakım servis sorun bildir"},
    {"ad": "Demirbaş ve donanım listesi", "yol": "/envanter",
     "sozcukler": "envanter demirbaş donanım seri cihaz"},
    {"ad": "Tahtaları CSV ile aktar", "yol": "/tahtalar/ice-aktar",
     "sozcukler": "csv excel toplu içe dışa aktar liste"},
    {"ad": "Tahta grubu oluştur", "yol": "/gruplar",
     "sozcukler": "grup hedef küme blok laboratuvar"},
    {"ad": "Mazeret ya da izin gir", "yol": "/yoklama/mazeret", "one": 6,
     "sozcukler": "mazeret izin izinli rapor raporlu görevli özür"},
    {"ad": "Yoklamayı panelden gir", "yol": "/yoklama/gir", "one": 5,
     "sozcukler": "elle yoklama kâğıt gir düzelt"},
    {"ad": "Devamsızlık icmali", "yol": "/yoklama/icmal", "one": 7,
     "sozcukler": "devamsızlık icmal özet e-okul eokul rapor yazdır"},
    {"ad": "Şube defteri (son beş gün)", "yol": "/yoklama/sube", "one": 4,
     "sozcukler": "şube sınıf defteri son beş gün geçmiş yoklama düzelt"},
    {"ad": "Okul geneli son günler", "yol": "/yoklama/son-gunler",
     "sozcukler": "son günler art arda derste görülmeyen okul geneli"},
    {"ad": "Ders programını gör", "yol": "/program?bolum=derslik",
     "sozcukler": "ders programı haftalık program sınıf hangi ders dolu boş"},
    {"ad": "Ders programını içe aktar", "yol": "/program/aktar",
     "sozcukler": "asc e-okul eokul xlsx csv şablon haftalık ders programı yükle"},
    {"ad": "Tören ya da etkinlik günü (program istisnası)", "yol": "/program?bolum=istisnalar",
     "sozcukler": "tören etkinlik tatil bayram gezi istisna kilit durdur"},
    {"ad": "Bir günün zil planını önizle", "yol": "/program/gun",
     "sozcukler": "yarın bugün önizle plan çizelge"},
    {"ad": "Sınav oluştur, salon listesi yükle", "yol": "/sinavlar",
     "sozcukler": "sınav kelebek salon gözetmen ortak sınav"},
    {"ad": "Kim ne yaptı (işlem kaydı)", "yol": "/kayit",
     "sozcukler": "kayıt günlük geçmiş denetim log"},
]  # fmt: skip
# SIK_ISLER sonu


# ---- metin ---------------------------------------------------------------------------------------------------
def _saman(*parcalar: str) -> str:
    """`ayar_bolumleri.samanlik` + bölü/tire açılımı: "9/A" ve "9-A" → 9-a, 9, a, 9a.

    Sözcük ayırıcısı "/"ı böler ama "-"yi bölmez; "9/a", "9-a" ve "9a" sorgularının üçü de hem "9-A" adlı tahtayı
    hem "9/A" şubesini bulsun diye dizin tarafı genişletilir. Sorgu tarafı değişmez (`sozcukler`).
    """
    genis: list[str] = []
    for parca in parcalar:
        parca = str(parca or "")
        genis.append(parca)
        if "/" in parca:
            genis.append(parca.replace("/", "-"))
    taban = samanlik(*genis).split()
    gorulen: dict[str, None] = dict.fromkeys(taban)
    for s in taban:
        if "-" in s:
            alt = [p for p in s.split("-") if p]
            for p in alt:
                gorulen.setdefault(p, None)
            if len(alt) > 1:
                gorulen.setdefault("".join(alt), None)
    return " ".join(gorulen)


def _girdi(tur: str, ad: str, yer: str, yol: str, rol: str, *anahtar: str, alt: str = "", sira=0, yalniz: str = "", bas: str = "") -> dict:
    """`yalniz` verilirse samanlık YALNIZ ondan kurulur (şube: "10/d" sorgusu "defteri" yüzünden bütün şubeleri bulmasın).
    `bas` verilirse başlık öneki kademesi ondan sayılır (süzgeç: ad "<liste>: <etiket>", önek etiketten)."""
    saman = _saman(yalniz) if yalniz else _saman(ad, yer, *anahtar)
    return {
        "tur": tur,
        "ad": ad,
        "yer": yer,
        "yol": yol,
        "rol": rol or "",
        "alt": alt,
        "saman": saman,
        "saman_kat": katla(saman),
        "ad_sozcuk": sozcukler(bas or ad),
        "ad_saman": _saman(ad),
        "sira": sira,
    }


# ---- yer ve rol: hedef adresten türer --------------------------------------------------------------------------
def _sorgusuz(yol: str) -> str:
    return yol.split("#", 1)[0].split("?", 1)[0]


def _menu_ogeleri(menu: list[dict], menu_acil: dict) -> list[dict]:
    return [oge for kume in menu for oge in kume["ogeler"]] + [menu_acil]


def _menu_ogesi(yol: str, menu, menu_acil, secili) -> dict | None:
    for oge in _menu_ogeleri(menu, menu_acil):
        if secili(oge, yol):
            return oge
    return None


def _serit_sekmeleri(ad: str) -> list[dict]:
    return [s for kume in bolum_serit.SERITLER[ad]["kumeler"] for s in kume if not s.get("dis")]


def serit_ust_ogesi(ad: str, menu, menu_acil, secili) -> dict:
    """Şeridin menüdeki üst öğesi: ilk (dış olmayan) sekmenin sorgusuz yolunu seçili sayan öğe."""
    sekmeler = _serit_sekmeleri(ad)
    oge = _menu_ogesi(_sorgusuz(sekmeler[0]["yol"]), menu, menu_acil, secili) if sekmeler else None
    if oge is None:
        raise ValueError(f"Şeridin menüde üst öğesi yok: {ad}")
    return oge


def yer_coz(yol: str, menu: list[dict], menu_acil: dict, secili) -> tuple[str, str]:
    """(kırıntı, rol): bir hedef adresin hangi bölümde olduğu ve kime açık olduğu.

    Sıra: tam eşleşen sekme → aynı sorgusuz yoldaki sekmenin şeridi → Ayarlar bölümü → menü öğesi. Hiçbiri
    tutmazsa ValueError: sahipsiz girdi sessizce "herkese açık" olmaz (dizin kurulurken patlar).
    """
    yol = str(yol).split("#", 1)[0]
    if not yol.startswith("/") or yol.startswith("//"):
        raise ValueError(f"Arama hedefi site içi yol değil: {yol!r}")
    duz = _sorgusuz(yol)
    for serit in bolum_serit.SERITLER:
        sekmeler = _serit_sekmeleri(serit)
        tam = next((s for s in sekmeler if s["yol"] == yol), None)
        ayni = [s for s in sekmeler if _sorgusuz(s["yol"]) == duz]
        if not tam and not ayni:
            continue
        ust = serit_ust_ogesi(serit, menu, menu_acil, secili)
        if tam:
            yer = ust["ad"] if tam["ad"] == ust["ad"] else ust["ad"] + AYRAC + tam["ad"]  # "Tahtalar › Tahtalar" olmasın
            return yer, tam.get("rol") or ust.get("rol") or ""
        # Sorgusu bilinmeyen adres: o yoldaki sekmelerin HEPSİ yöneticiye özelse girdi de öyledir.
        ortak = YONETICI if all(s.get("rol") == YONETICI for s in ayni) else ""
        return ust["ad"], ortak or ust.get("rol") or ""
    oge = _menu_ogesi(duz, menu, menu_acil, secili)
    if oge is None:
        raise ValueError(f"Arama hedefinin menüde yeri yok: {yol!r}")
    for b in BOLUMLER:
        if duz == f"{oge['yol']}/{b['anahtar']}":
            return oge["ad"] + AYRAC + b["baslik"], oge.get("rol") or ""
    return oge["ad"], oge.get("rol") or ""


# ---- sabit dizin -----------------------------------------------------------------------------------------------
def sabit_dizin(menu: list[dict], menu_acil: dict, secili) -> list[dict]:
    """sayfa + sekme + is + suzgec + ayar; süreç başında bir kez kurulur (web.py). Kurulurken kendini denetler."""
    girdiler: list[dict] = []

    def coz(yol: str) -> tuple[str, str]:
        return yer_coz(yol, menu, menu_acil, secili)

    for oge in _menu_ogeleri(menu, menu_acil):
        girdiler.append(_girdi("sayfa", oge["ad"], "", oge["yol"], oge.get("rol") or ""))
    for serit in bolum_serit.SERITLER:
        ust = serit_ust_ogesi(serit, menu, menu_acil, secili)
        for sekme in _serit_sekmeleri(serit):
            girdiler.append(_girdi("sekme", sekme["ad"], ust["ad"], sekme["yol"], sekme.get("rol") or ust.get("rol") or ""))
    for o in BASKA_YERDE:
        girdiler.append(_girdi("is", o["ad"], o["yer"], o["yol"], coz(o["yol"])[1], o["sozcukler"]))
    for o in SIK_ISLER:
        yer, rol = coz(o["yol"])
        acik = o.get("rol", "")
        if acik not in ("", YONETICI):
            raise ValueError(f"Sık işte bilinmeyen rol: {o['ad']}")
        girdiler.append(_girdi("is", o["ad"], yer, o["yol"], rol or acik, o["sozcukler"]))
    liste_yolu = _serit_sekmeleri("tahtalar")[0]["yol"]
    liste_adi = _serit_sekmeleri("tahtalar")[0]["ad"]
    for anahtar, etiket in tahta_liste.SUZGECLER.items():
        yol = f"{liste_yolu}?durum={anahtar}"
        # Ad "<liste>: <etiket>" kalıbıdır: etiket ne olursa olsun düzgün okunur (etikete çoğul eki yapıştırılmaz).
        girdiler.append(_girdi("suzgec", f"{liste_adi}: {etiket}", "", yol, coz(yol)[1], anahtar, bas=etiket))
    for b in BOLUMLER:
        yol = f"/ayarlar/{b['anahtar']}"
        yer, rol = coz(yol)
        ust = yer.split(AYRAC, 1)[0]
        girdiler.append(_girdi("ayar", b["baslik"], ust + AYRAC + b["kume"], yol, rol, b["aciklama"], b["sozcukler"], alt=b["aciklama"]))  # fmt: skip

    gorulen: set[tuple[str, str]] = set()
    for sira, g in enumerate(girdiler):
        g["sira"] = sira
        if not g["yol"].startswith("/") or g["yol"].startswith("//") or "\\" in g["yol"]:
            raise ValueError(f"Arama hedefi site içi yol değil: {g['yol']!r}")
        if g["rol"] not in ("", YONETICI):
            raise ValueError(f"Bilinmeyen rol: {g['ad']}")
        if (g["tur"], g["yol"]) in gorulen:
            raise ValueError(f"Aynı tür ve yol iki kez: {g['tur']} {g['yol']}")
        gorulen.add((g["tur"], g["yol"]))
    return girdiler


def kur(menu: list[dict], menu_acil: dict, secili) -> dict:
    """Sürecin arama tanımı: {"sabit": [...], "sube": {...}, "grup": {...}} (devingen girdilerin türeyen yer ve rolü)."""
    sube_sekmesi = next(s for s in _serit_sekmeleri("yoklama") if s["anahtar"] == "sube")
    grup_sekmesi = next(s for s in _serit_sekmeleri("tahtalar") if s["anahtar"] == "gruplar")
    sube_yer, sube_rol = yer_coz(sube_sekmesi["yol"], menu, menu_acil, secili)
    grup_yer, grup_rol = yer_coz(grup_sekmesi["yol"], menu, menu_acil, secili)
    return {
        "sabit": sabit_dizin(menu, menu_acil, secili),
        "sube": {"yol": sube_sekmesi["yol"], "yer": sube_yer, "rol": sube_rol, "ek": kucult(sube_sekmesi["ad"])},
        "grup": {"yol": grup_sekmesi["yol"], "yer": grup_yer, "rol": grup_rol},
    }  # fmt: skip


# ---- devingen dizin ------------------------------------------------------------------------------------------
def _gorur(girdi_rolu: str, rol: str | None) -> bool:
    return not girdi_rolu or girdi_rolu == rol


def devingen_dizin(b, rol: str | None, kurulu: dict) -> list[dict]:
    """tahta + şube (+ yöneticide grup). Önbellek yok; istek başına en çok 4 dar SELECT, sayısı tahta, öğrenci ve
    grup sayısından bağımsız. Yalnız ONAYLI tahta; ağ adresi, makine adı, sürüm, demirbaş, not OKUNMAZ."""
    girdiler: list[dict] = []
    tahtalar = b.execute("SELECT id, ad, derslik, bina, kat, subeler FROM tahta WHERE durum = 'onayli'").fetchall()
    for t in sorted(tahtalar, key=lambda t: (metin.tr_sirala_anahtari(t["ad"] or ""), t["id"])):
        bina = " ".join(str(t["bina"] or "").split())
        kat = t["kat"]
        konum = tahta_liste.grup_adi(bina, kat) if (bina or kat is not None) else ""
        derslik = str(t["derslik"] or "").strip()
        yer = " · ".join(p for p in ("Tahta", derslik, konum) if p)
        kat_metni = hedef.kat_adi(kat) if kat is not None else ""
        subeler = str(t["subeler"] or "").replace("|", " ")  # "9/A|10/B"; çözücü çağrılmaz (bozuk değer patlatmasın)
        girdiler.append(_girdi("tahta", t["ad"], yer, f"/tahta/{t['id']}", "", derslik, bina, kat_metni, subeler, sira=len(girdiler)))
    sube = kurulu["sube"]
    if _gorur(sube["rol"], rol) and yoklama.ayar_al(b)["etkin"]:
        for s in yoklama.aktif_subeler(b):
            yol = f"{sube['yol']}?sube={quote(s, safe='')}"
            girdiler.append(_girdi("sube", f"{s} {sube['ek']}", sube["yer"], yol, sube["rol"], sira=len(girdiler), yalniz=s))
    grup = kurulu["grup"]
    if _gorur(grup["rol"], rol):  # rolün göremeyeceği girdi için sorgu da atılmaz
        gruplar = b.execute("SELECT id, ad FROM tahta_grubu").fetchall()
        for g in sorted(gruplar, key=lambda g: (metin.tr_sirala_anahtari(g["ad"] or ""), g["id"])):
            girdiler.append(_girdi("grup", g["ad"], grup["yer"], grup["yol"] + f"#grup-{g['id']}", grup["rol"], sira=len(girdiler)))
    return girdiler


# ---- eşleştirme ----------------------------------------------------------------------------------------------
def sorgu_duzelt(q) -> str:
    """Kesilmiş, boşlukları sadeleşmiş sorgu (uzun sorgu reddedilmez, kesilir; Ayarlar aramasıyla aynı sınır).
    Yazdırılamayan karakterler (NUL, denetim, yön değiştirici, sıfır genişlikli) atılır: sayfaya yankılanmasın."""
    ham = str(q or "")[: SORGU_EN_UZUN * 4]
    temiz = "".join(c for c in ham if c.isprintable() or c.isspace())
    return " ".join(" ".join(temiz.split())[:SORGU_EN_UZUN].split())


def _kademe(q: list[str], ad_sozcuk: list[str], ad_saman: str) -> int:
    """0: sorgu başlığın İLK sözcüklerine sırayla önek; 1: bütün sorgu başlık sözcüklerinde; 2: anahtar sözcükten."""
    if len(q) <= len(ad_sozcuk) and all(a.startswith(s) for s, a in zip(q, ad_sozcuk, strict=False)):
        return 0
    return 1 if uyar(q, ad_saman) else 2


def _ekli_uyar(q: list[str], saman: str) -> bool:
    """Ekli sözcük: sorgu sözcüğü samanlıktaki bir sözcüğün başı DEĞİLSE, samanlıktaki (en az EK_KOK_EN_KISA harfli)
    bir sözcük sorgu sözcüğünün başı olabilir ("pusulası" → "pusula", "ayarları" → "ayarlar"). Kökten artan kısım
    yalnız harf olmalıdır (ek): "idareci1", "tahta-12" ek sayılmaz. İlkel yine `uyar`."""
    kokler = [s for s in saman.split() if len(s) >= EK_KOK_EN_KISA]
    return all(uyar([x], saman) or any(uyar([k], x) and x[len(k) :].isalpha() for k in kokler) for x in q)


def _dis(g: dict) -> dict:
    return {"tur": g["tur"], "ad": g["ad"], "yer": g["yer"], "yol": g["yol"], "alt": g["alt"]}


def ara(sorgu, sabit: list[dict], devingen: list[dict], rol: str | None, en_cok: int = SAYFA_EN_COK) -> dict:
    """{"sorgu", "etkin", "sonuclar": [{"tur","ad","yer","yol","alt"}], "toplam", "fazla"}.

    Önce ROL süzülür, sonra eşleştirilir: her sorgu sözcüğü samanlıktaki bir sözcüğün BAŞINDA geçmelidir. Türkçe
    küçük harfle eşleşenler (kesin) üstte, yalnız harf katlanınca eşleşenler altta; en altta yalnız ekli sözcükle
    eşleşenler (`_ekli_uyar`). Aynı hedef bir kez listelenir.
    """
    sorgu = sorgu_duzelt(sorgu)
    q = sozcukler(sorgu)[:SOZCUK_EN_COK]
    if not q:
        return {"sorgu": sorgu, "etkin": False, "sonuclar": [], "toplam": 0, "fazla": False}
    qk = [katla(s) for s in q]
    puanli: list[tuple[tuple, dict]] = []
    for g in list(sabit) + list(devingen):
        if not _gorur(g["rol"], rol):
            continue
        if uyar(q, g["saman"]):
            ekli, katli, kademe = 0, 0, _kademe(q, g["ad_sozcuk"], g["ad_saman"])
        elif uyar(qk, g["saman_kat"]):
            ekli, katli, kademe = 0, 1, _kademe(qk, [katla(s) for s in g["ad_sozcuk"]], katla(g["ad_saman"]))
        elif _ekli_uyar(q, g["saman"]):
            ekli, katli, kademe = 1, 0, 2
        elif _ekli_uyar(qk, g["saman_kat"]):
            ekli, katli, kademe = 1, 1, 2
        else:
            continue
        puanli.append(((ekli, katli, kademe, TUR_SIRASI.index(g["tur"]), g["sira"]), g))
    puanli.sort(key=lambda p: p[0])
    gorulen: set[str] = set()
    sonuclar = []
    for _, g in puanli:
        if g["yol"] in gorulen:
            continue
        gorulen.add(g["yol"])
        sonuclar.append(_dis(g))
    return {"sorgu": sorgu, "etkin": True, "sonuclar": sonuclar[:en_cok], "toplam": len(sonuclar), "fazla": len(sonuclar) > en_cok}


def gruplu(sonuclar: list[dict]) -> list[dict]:
    """Sonuç sayfası için sabit sıralı gruplar: [{"anahtar", "sonuclar"}]; boş grup dönmez, grup içi sıra korunur."""
    kovalar: dict[str, list[dict]] = {a: [] for a in GRUP_SIRASI}
    for s in sonuclar:
        kovalar[TUR_GRUBU[s["tur"]]].append(s)
    return [{"anahtar": a, "sonuclar": kovalar[a]} for a in GRUP_SIRASI if kovalar[a]]


def sik_isler(sabit: list[dict], rol: str | None) -> list[dict]:
    """Sorgu boşken gösterilen kısa yollar: SIK_ISLER'de `one` taşıyan, role göre süzülmüş `is` girdileri; günlük iş
    sırasıyla, en çok SIK_EN_COK tane. Bütün kısa yolların dökümü değildir (kalanı aranınca çıkar). Devingen girdi yok."""
    one = {(o["ad"], o["yol"]): o["one"] for o in SIK_ISLER if o.get("one")}
    secilen = [g for g in sabit if g["tur"] == "is" and (g["ad"], g["yol"]) in one and _gorur(g["rol"], rol)]
    secilen.sort(key=lambda g: one[(g["ad"], g["yol"])])
    return [_dis(g) for g in secilen[:SIK_EN_COK]]
