"""Bugün sayfası (0.18.0, panel arayüzü 4. aşama): bekleyen işler, şu an akışı, tahta özeti, yoklama ve duyuru
kutuları. FastAPI'siz.

`bekleyenler` TEK işlevdir: 0.17.0'da tahta listesinin üstündeki bantlara dağılmış her koşul burada bir satırdır.
Role göre süzme işlevin İÇİNDEDİR (şablonda rol koşulu yazılmaz); menü rozeti, Bugün'deki satır ve /api/durum'un
`bekleyen_is` alanı aynı listeden çıkar. Koşullar var olan işlevlerden okunur (kopya koşul yoktur).

Gizlilik: Bugün omuz üstünden görülebilen bir ekrandır. Bu modülün ürettiği hiçbir sözlükte öğrenci ya da öğretmen
adı, okul numarası, mazeret türü, ders başlığı, arıza açıklaması, duyuru metni ve onay bekleyen tahtanın adı/adresi
yoktur; yoklama kutusu yalnız sayı verir (K5, kural 13, 24, 35). İşlem kaydına hiçbir şey yazılmaz.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import (
    __version__,
    adresler,
    ariza,
    ayar_bolumleri,
    guncelleme,
    guvenlik,
    paket,
    program,
    saklama,
    tahta_liste,
    vt,
    yedek,
    yoklama,
    yoklama_defter,
    zamanlama,
)

ISTANBUL = ZoneInfo("Europe/Istanbul")
ONEM_SIRASI = {"tehlike": 0, "uyari": 1, "bilgi": 2}
ACIK_SATIR = 6  # en az bu kadar satır açık çizilir; kalan BİLGİ satırları "Diğer N iş" içindedir (acik_satir_sayisi)
CIP_EN_COK = 60  # bundan çok onaylı tahtada tahta başına çip yerine grup başına tek satır
SUBE_HAPI_EN_COK = 40
OLAY_EN_COK = 3
PLAN_EN_COK = 200
YEDEK_ESKI_SN = 2 * 86400
# Kurulum listesinde olup bekleyenlerde KENDİ satırı bulunan maddeler: `kurulum` satırı bunları saymaz (çift sayım olmasın).
KURULUMDA_AYRI_SATIR = frozenset({"yedek_parolasi", "ogretim_yili", "sunucu_adresi", "kilit_kodu"})
YOKLAMA_NOTU = (
    "Tahtadan alınan yoklama kâğıdın yanında yardımcı kayıttır. "
    "Burada görünmemesi dersin işlenmediği anlamına gelmez."
)


def _tarih(epoch) -> str:
    return datetime.fromtimestamp(int(epoch), ISTANBUL).strftime("%d.%m.%Y %H:%M") if epoch else "—"


def _satir(anahtar: str, onem: str, baslik: str, *, alt: str = "", yol: str = "", eylem: str = "", sayi: int = 1,
           rozet: str | None = None, simge: str = "s-bilgi", dis: bool = False) -> dict:  # fmt: skip
    return {
        "anahtar": anahtar, "onem": onem, "baslik": baslik, "alt": alt, "yol": yol, "eylem": eylem if yol else "",
        "dis": dis, "sayi": max(1, int(sayi)), "rozet": rozet, "simge": simge,
    }  # fmt: skip


# ---- bekleyenler: üreticiler (çizelge sırası = eşit önemde liste sırası) --------------------------------
def _yedek_satirlari(b, yonetici: bool, an: int) -> list[dict]:
    """B1–B4: 0.17.0 `web.altyapi_uyarilari`'nın yedek dalı.

    Ham hata metni (`son["hata"]`, `son["kopya_hata"]`) Bugün'e YAZILMAZ: istisna metni sunucu yolunu ve ikinci kopya
    klasörünü taşır; bu sayfa omuz üstünden görülür ve idareciye de açıktır. Ayrıntı yalnız /yedekler'dedir (yönetici)."""
    ayrinti = "Ayrıntı Yedekler sayfasında." if yonetici else "Yöneticiye bildirin."
    yedek_ayari = yedek.ayarlar(b)
    if not yedek_ayari["parola_var"]:
        if yonetici:
            return [_satir("yedek_parola", "tehlike", "Yedek parolası belirlenmedi; otomatik yedek alınmıyor.",
                           yol="/yedekler", eylem="Yedekler", rozet="yedekler", simge="m-yedek")]  # fmt: skip
        return [_satir("yedek_parola_i", "tehlike", "Yedek alınmıyor; yöneticiye bildirin.", simge="m-yedek")]
    yol, rozet = ("/yedekler", "yedekler") if yonetici else ("", None)
    son = yedek.son_yedek(b)
    son_basarili = int(son.get("son_basarili") or 0)
    eski = (son_basarili and an - son_basarili > YEDEK_ESKI_SN) or (
        not son_basarili and an - int(yedek_ayari.get("parola_zamani") or an) > YEDEK_ESKI_SN
    )
    satirlar = []
    if son and not son.get("basarili", True):
        bas = f"son başarılı: {_tarih(son_basarili)}" if son_basarili else "henüz başarılı yedek yok"
        satirlar.append(_satir("yedek_basarisiz", "uyari", f"Son yedek alınamadı ({bas}).", alt=ayrinti,
                               yol=yol, eylem="Yedekler", rozet=rozet, simge="m-yedek"))  # fmt: skip
    elif eski:
        bas = f"Son yedek: {_tarih(son_basarili)}." if son_basarili else "Henüz yedek alınmadı."
        satirlar.append(_satir("yedek_eski", "uyari", bas + " Yedek 2 günden eski.", alt="" if yonetici else ayrinti,
                               yol=yol, eylem="Yedekler", rozet=rozet, simge="m-yedek"))  # fmt: skip
    if son.get("basarili") and son.get("kopya_hata"):
        satirlar.append(_satir("yedek_kopya", "uyari", "Yedeğin ikinci kopyası yazılamadı.", alt=ayrinti,
                               yol=yol, eylem="Yedekler", rozet=rozet, simge="m-yedek"))  # fmt: skip
    return satirlar


def _geri_yukleme(yonetici: bool) -> list[dict]:
    if not yonetici:
        return []
    bekleyen = yedek.bekleyen_oku()
    if not bekleyen:
        return []
    baslik = (
        "Geri yükleme onaylandı; program yeniden açılınca uygulanacak."
        if bekleyen.get("onaylandi")
        else "Denetlenmiş bir yedek geri yükleme onayı bekliyor."
    )
    return [_satir("geri_yukleme", "uyari", baslik, yol="/yedekler?yer=geri", eylem="Yedekler", simge="m-yedek")]


def _adres(b, yonetici: bool, ipler: list[str]) -> list[dict]:
    if not ipler or adresler.bu_bilgisayar_listede_mi(adresler.al(b), ipler):
        return []
    return [_satir(
        "adres", "uyari",
        f"Bu bilgisayarın adresi ({ipler[0]}) tahtalara bildirilen listede yok. Tahtalar eski adresi kullanıyor olabilir.",
        yol="/ayarlar/sunucu#adresler" if yonetici else "", eylem="Ayarlar", simge="a-sunucu",
    )]  # fmt: skip


def _ogretim_yili(b, yonetici: bool, an: int) -> list[dict]:
    if not yonetici:
        return []
    d = saklama.durum(b, datetime.fromtimestamp(an, ISTANBUL).date())
    if not d["uyari"]:
        return []
    # Koşul `saklama.durum`'dandır; uzun açıklaması Ayarlar › Veri'de okunur, burada kısa hâli durur.
    if d["gecti"]:
        baslik, alt = f"Öğretim yılı bitiş tarihi ({d['bitis_metni']}) geçti.", "Yeni öğretim yılının bitiş tarihini girin."
    else:
        baslik, alt = "Öğretim yılı bitiş tarihi girilmedi; öğrenci kayıtları kendiliğinden silinmiyor.", ""
    return [_satir("ogretim_yili", "uyari", baslik, alt=alt, yol="/ayarlar/veri#saklama", eylem="Tarihi gir", simge="s-takvim")]


def _onay(b, yonetici: bool) -> list[dict]:
    n = b.execute("SELECT COUNT(*) FROM tahta WHERE durum = 'bekliyor'").fetchone()[0]
    if not n:
        return []
    if yonetici:
        return [_satir("onay", "uyari", f"{n} yeni tahta onay bekliyor.", alt="Ad ve derslik verilip onaylanınca komut alır.",
                       yol="/tahtalar#onay-bekleyen", eylem="Adlandır ve onayla", sayi=n, rozet="tahtalar", simge="m-tahta")]  # fmt: skip
    return [_satir("onay_i", "bilgi", f"{n} yeni tahta yöneticinin onayını bekliyor.",
                   alt="Onaylanınca komut alır; sizin yapacağınız bir şey yok.", sayi=n, simge="m-tahta")]  # fmt: skip


def _ariza(b) -> list[dict]:
    n = ariza.suren_toplam(b)
    if not n:
        return []
    # Kategori, açıklama ve tahta adı yazılmaz (kural 23).
    return [_satir("ariza", "uyari", f"{n} arıza kaydı açık.", yol="/arizalar", eylem="Arızaları aç", sayi=n,
                   rozet="tahtalar", simge="s-sorun")]  # fmt: skip


def _kacirilan(b, an: int) -> list[dict]:
    n = b.execute("SELECT COUNT(*) FROM duyuru WHERE durum = 'kacirildi' AND olusturma > ?", (an - 86400,)).fetchone()[0]
    if not n:
        return []
    return [_satir("kacirilan", "uyari", f"Sunucu kapalıyken {n} zamanlanmış duyuru kaçırıldı.",
                   alt="Duyurular sayfasından yeniden gönderebilirsiniz.", yol="/duyurular#gecmis-baslik", eylem="Duyurular",
                   sayi=n, simge="s-duyuru")]  # fmt: skip


def _kilit_kodu(b, yonetici: bool) -> list[dict]:
    if vt.ayar_al(b, "kilit_kodu"):
        return []
    return [_satir("kilit_kodu", "bilgi", "Kilit kodu tanımlı değil: kilitlenen tahta yalnız panelden açılır.",
                   yol="/ayarlar/kilit" if yonetici else "", eylem="Kod belirle", simge="s-kilit")]  # fmt: skip


def guncel_olmayan_sayisi(b) -> int:
    """Ajanı güncel olmayan onaylı tahta sayısı; `tahta_liste.sayilar(...)["guncelleme"]` ile aynı kural, tek COUNT."""
    return b.execute(
        "SELECT COUNT(*) FROM tahta WHERE durum = 'onayli' AND surum IS NOT NULL AND surum != '' AND surum != ?",
        (paket.ajan_paketi().surum,),
    ).fetchone()[0]


def _guncelleme_tahta(b, tahta_sayilari: dict | None) -> list[dict]:
    n = int(tahta_sayilari["guncelleme"]) if tahta_sayilari is not None else guncel_olmayan_sayisi(b)
    if not n:
        return []
    return [_satir("guncelleme_tahta", "bilgi", f"{n} tahtada ajan güncellenebilir.", yol="/tahtalar?durum=guncelleme",
                   eylem="Tahtaları göster", sayi=n, simge="s-guncel")]  # fmt: skip


def _yeni_surum(b, yonetici: bool) -> list[dict]:
    """B6, kural 32: yalnız yönetici; bağlantı SABİT kalıptan (`guncelleme.gorunum` → `surum_adresi`); sürüm notu
    basılmaz; ulaşılamadı / denetlenmedi / ayar kapalı → satır yok."""
    if not yonetici:
        return []
    yeni = guncelleme.gorunum(b)["yeni"]
    if not yeni:
        return []
    return [_satir("yeni_surum", "bilgi", f"Tahta Kontrol {yeni['surum']} yayımlandı (kurulu sürüm {__version__}).",
                   alt="Kendiliğinden indirilmez.", yol=yeni["adres"], eylem="Sürüm sayfası", dis=True, simge="s-guncel")
            | {"surum": yeni["surum"], "ek_yol": "/ayarlar/guncelleme", "ek_eylem": "Ayarlar"}]  # fmt: skip


def _kurulum(b, yonetici: bool, an: int, ipler: list[str]) -> list[dict]:
    if not yonetici:
        return []
    k = ayar_bolumleri.kurulum(b, datetime.fromtimestamp(an, ISTANBUL).date(), ipler)
    eksik = [m for m in k["zorunlu_eksik"] + k["oneri_eksik"] if m["anahtar"] not in KURULUMDA_AYRI_SATIR]
    if not eksik:
        return []
    return [_satir("kurulum", "bilgi", f"Kurulumda {len(eksik)} adım eksik.", alt=", ".join(m["ad"] for m in eksik),
                   yol="/ayarlar#kurulum", eylem="Tamamla", sayi=len(eksik), simge="m-ayar")]  # fmt: skip


def kurulum_satiri(b, kullanici, *, an: int | None = None, ipler: list[str] | None = None) -> list[dict]:
    """`kurulum` satırı tek başına ([] ya da tek öğe). /api/durum bu satırı kısa süre bellekte tutar: kurulum eksikleri
    saniyeler içinde değişmez, üreticisi ise dokuz ayar okur (4 sn'de bir, açık sekme başına)."""
    an = vt.simdi() if an is None else an
    return _kurulum(b, kullanici["rol"] == "yonetici", an, guvenlik.yerel_ipler() if ipler is None else ipler)


def acik_satir_sayisi(satirlar: list[dict]) -> int:
    """Açık çizilecek satır sayısı: tehlike ve uyarı satırları HEP açıktır; "Diğer N iş" yalnız bilgi satırı katlar."""
    return max(ACIK_SATIR, sum(1 for s in satirlar if s["onem"] != "bilgi"))


def bekleyenler(b, kullanici, *, an: int | None = None, ipler: list[str] | None = None, yalniz_rozet: bool = False,
                tahta_sayilari: dict | None = None, kurulum: list[dict] | None = None) -> list[dict]:  # fmt: skip
    """Kullanıcının rolüne göre süzülmüş bekleyen işler; önem (tehlike → uyarı → bilgi), sonra çizelge sırası.

    Satır: {"anahtar", "onem", "baslik", "alt", "yol" ("" = bağlantısız), "eylem", "dis", "sayi", "rozet", "simge"}.
    `yol` yalnız o rolün açabildiği adrestir. Üst sınır yoktur (uyarı kesilerek kaybolmasın).
    yalniz_rozet: yalnız menü rozeti taşıyabilen üreticiler çalışır (her sayfada; az sorgu) ve yalnız rozetli satırlar döner.
    tahta_sayilari: çağıran `tahta_liste.sayilar` çıktısını zaten hesapladıysa (Bugün sayfası) sayım yinelenmez.
    kurulum: çağıran `kurulum_satiri` çıktısını bellekte tutuyorsa (/api/durum) üretici yeniden çalışmaz.
    """
    an = vt.simdi() if an is None else an
    yonetici = kullanici["rol"] == "yonetici"
    if yalniz_rozet:
        satirlar = (_yedek_satirlari(b, True, an) if yonetici else []) + _onay(b, yonetici) + _ariza(b)
        return [s for s in satirlar if s["rozet"]]
    if ipler is None:
        ipler = guvenlik.yerel_ipler()
    satirlar = (
        _yedek_satirlari(b, yonetici, an)
        + _geri_yukleme(yonetici)
        + _adres(b, yonetici, ipler)
        + _ogretim_yili(b, yonetici, an)
        + _onay(b, yonetici)
        + _ariza(b)
        + _kacirilan(b, an)
        + _kilit_kodu(b, yonetici)
        + _guncelleme_tahta(b, tahta_sayilari)
        + _yeni_surum(b, yonetici)
        + (_kurulum(b, yonetici, an, ipler) if kurulum is None else list(kurulum))
    )
    return sorted(satirlar, key=lambda s: ONEM_SIRASI[s["onem"]])  # kararlı: eşit önemde çizelge sırası korunur


def rozet_sayilari(satirlar: list[dict]) -> dict[str, int]:
    """Menü rozetleri: {"tahtalar": n, "yedekler": n} (`rozet` anahtarına göre `sayi` toplamı)."""
    sonuc = {"tahtalar": 0, "yedekler": 0}
    for s in satirlar:
        if s.get("rozet"):
            sonuc[s["rozet"]] = sonuc.get(s["rozet"], 0) + int(s["sayi"])
    return sonuc


def satir_sayisi(satirlar: list[dict], anahtar: str) -> int:
    return next((int(s["sayi"]) for s in satirlar if s["anahtar"] == anahtar), 0)


def imza(satirlar: list[dict]) -> str:
    """Canlı tazeleme: liste değişti mi (anahtar ve sayı); metin taşımaz."""
    return ",".join(f"{s['anahtar']}:{s['sayi']}" for s in satirlar)


# ---- şu an: akış şeridi -----------------------------------------------------------------------------
def akis(b, simdi: datetime, plan: dict | None = None) -> list[dict]:
    """Günün ders akışı: [{"devre": ad ("" = tek devre), "dersler": [{"no", "bas": "08:30", "durum"}]}].

    durum: "gecti" | "simdi" | "gelecek". Yalnız ders numarası ve başlangıç saati; ders adı, şube, öğretmen yok.
    Plan boşsa ya da tatilse []. İkili eğitimde (kural 25) devre başına bir sıra; tek devrede devre adı boştur.
    """
    plan = program.gun_plani(b, simdi.date()) if plan is None else plan
    if plan.get("tatil") or not plan.get("dersler"):
        return []
    siralar: dict[str, dict] = {}
    for devre, devre_adi, no, bas, bit in plan["dersler"]:
        sira = siralar.setdefault(devre, {"devre": devre_adi or program.devre_adi_varsayilan(devre), "dersler": []})
        durum = "gecti" if bit <= simdi else "simdi" if bas <= simdi else "gelecek"
        sira["dersler"].append({"no": no, "bas": f"{bas:%H:%M}", "durum": durum})
    sonuc = list(siralar.values())
    if len(sonuc) == 1:
        sonuc[0]["devre"] = ""
    return sonuc


# ---- tahtalar şu an ---------------------------------------------------------------------------------
_OZET_SIRASI = (("acik", "açık"), ("kilitli", "kilitli"), ("duyuru", "duyuruda"), ("sorun", "ekran sorunu"),
                ("cevrimdisi", "çevrimdışı"))  # fmt: skip
KUTULAR = ("acik", "kilitli", "duyuru", "sorun", "cevrimdisi", "guncelleme")  # sayı kutularının sırası
DURUM_SIMGESI = {"acik": "s-acik", "kilitli": "s-kilit", "duyuru": "s-duyuru", "sorun": "s-sorun", "cevrimdisi": "s-kapali",
                 "guncelleme": "s-guncel"}  # fmt: skip


def cip_okunur(liste: dict) -> str:
    """Çipin ekran okuyucu metni: satır rozetlerinin sözcükleri (boş ders ve program muafiyeti hariç; `cip: False`)."""
    return ", ".join(r["m"] for r in liste["rozetler"] if r.get("cip") is not False)


def grup_ozeti(tahtalar: list[dict]) -> str:
    """ "5 açık · 2 kilitli · 1 çevrimdışı" (birincil duruma göre; yalnız sıfır olmayanlar)."""
    parcalar = []
    for anahtar, ad in _OZET_SIRASI:
        n = sum(1 for t in tahtalar if t["liste"]["birincil"] == anahtar)
        if n:
            parcalar.append(f"{n} {ad}")
    return " · ".join(parcalar)


def tahta_ozeti(onayli: list[dict]) -> dict:
    """Onaylı tahta görünümlerinden (`web.tahta_gorunumu`, `liste` dolu) Bugün'ün tahta kartı.

    Durum kuralı yeniden yazılmaz: sayılar `tahta_liste.sayilar`, gruplar `tahta_liste.gruplar` (liste ile aynı sıra
    ve aynı grup numarası). Çipte ders, oturum sınıfı, boş ders ve güncelleme simgesi yoktur.
    kilit_hedefi: "Hepsini kilitle"nin gideceği tahtalar (çevrimiçi ve sınav penceresinde olmayan).
    """
    gruplar = []
    for no, g in enumerate(tahta_liste.gruplar(onayli), start=1):
        cipler = []
        for t in g["tahtalar"]:
            ek = []
            if "ariza" in t["liste"]["durumlar"]:
                ek.append("ariza")
            if t.get("sinav"):
                ek.append("sinav")
            cipler.append({
                "id": t["id"], "ad": t["ad"], "birincil": t["liste"]["birincil"],
                "simge": DURUM_SIMGESI[t["liste"]["birincil"]], "okunur": cip_okunur(t["liste"]), "ek": ek,
            })  # fmt: skip
        gruplar.append({"no": no, "ad": g["ad"], "baslik": g["baslik"], "tahtalar": cipler, "sayi": len(cipler),
                        "ozet": grup_ozeti(g["tahtalar"])})  # fmt: skip
    cevrimici = [t for t in onayli if t.get("cevrimici")]
    sayilar = tahta_liste.sayilar(onayli)
    return {
        "kutular": [{"anahtar": a, "ad": tahta_liste.SUZGECLER[a], "simge": DURUM_SIMGESI[a], "sayi": sayilar[a]} for a in KUTULAR],
        "grup_haritasi": {str(t["id"]): g["no"] for g in gruplar for t in g["tahtalar"]},
        "hepsi": len(onayli),
        "cevrimici": len(cevrimici),
        "sayilar": sayilar,
        "sinavda": sum(1 for t in onayli if t.get("sinav")),
        "kilit_hedefi": sum(1 for t in cevrimici if not t.get("sinav")),
        "kilit_sinavda": sum(1 for t in cevrimici if t.get("sinav")),
        "kilit_cevrimdisi": len(onayli) - len(cevrimici),
        "kip": "grup" if len(onayli) > CIP_EN_COK else "cip",
        "gruplar": gruplar,
    }


# ---- yoklama · bugün --------------------------------------------------------------------------------
def yoklama_ozeti(b, an: int) -> dict:
    """Bugünün yoklama özeti; YALNIZ sayı ve şube adı (kişi verisi, mazeret türü, kayıt saati yok).

    Veri `yoklama_defter.Veri` ile toplu yüklenir (sorgu sayısı şube/öğrenci sayısından bağımsız); sayılar tek
    birleşim kuralından (`Veri.kumeler`, kural 34). `beklenen`: bitişinden 15 dk geçmiş planlı şube-ders;
    plan dışı kayıt paya ve paydaya birlikte eklenir. `yok`/`gec`: ayrı öğrenci sayısı (mazeretli dahil).
    """
    if not yoklama.ayar_al(b)["etkin"]:
        return {"etkin": False}
    gun = datetime.fromtimestamp(an, ISTANBUL).date()
    tarih = gun.isoformat()
    veri = yoklama_defter.Veri(b, gun, gun)
    aktif = yoklama.aktif_subeler(b)
    subeler = sorted(set(aktif) | {y["sube"] for y in veri.yoklamalar}, key=yoklama.sube_anahtari)
    plan = veri.plan(gun)
    beklenen = alinan = kayit = 0
    yok: set[int] = set()
    gec: set[int] = set()
    satirlar = []
    for sube in subeler:
        s_beklenen = s_alinan = 0
        for d in veri.dersler(gun, sube):
            alindi = veri.alindi(tarih, sube, d["ders_no"])
            if alindi:
                kayit += 1
                y, g = veri.kumeler(tarih, sube, d["ders_no"])
                yok |= y
                gec |= g
            if d["plan"]:
                if d["bit"] is not None and d["bit"] + yoklama.ALINMADI_PAYI_SN <= an:
                    s_beklenen += 1
                    s_alinan += 1 if alindi else 0
            elif alindi:
                s_beklenen += 1
                s_alinan += 1
        beklenen += s_beklenen
        alinan += s_alinan
        satirlar.append({"ad": sube, "alinan": s_alinan, "beklenen": s_beklenen})
    return {
        "etkin": True,
        "tatil": plan.get("tatil"),
        "program_var": bool(plan.get("dersler")),
        "liste_var": bool(aktif),
        "beklenen": beklenen,
        "alinan": alinan,
        "kayit": kayit,
        "yok": len(yok),
        "gec": len(gec),
        "subeler": satirlar[:SUBE_HAPI_EN_COK],
        "sube_fazla": max(0, len(satirlar) - SUBE_HAPI_EN_COK),
        "nota": YOKLAMA_NOTU,
    }


# ---- duyurular --------------------------------------------------------------------------------------
def duyuru_ozeti(b, an: int) -> dict:
    """Ekrandaki ve bugün planlı duyurular: {"ekranda": [...], "planli": [...], "ekranda_fazla", "planli_fazla"}.

    Duyuru METNİ, oluşturan ve hedef adları SELECT edilmez (yalnız başlık, tahta sayısı, saat). İki sorgu.
    `tahta_sayisi` gönderim hedefidir (çevrimdışı tahtalar dahil), o an gösteren tahta sayısı değildir; şablon
    "N tahtaya gönderildi" der. `bitis`: "13:56'da" (program.saat_eki).
    """
    yayinda = b.execute(
        "SELECT id, baslik, bitis, tahta_sayisi FROM duyuru WHERE durum = 'gonderildi' AND bitis > ? ORDER BY an DESC, id DESC",
        (an,),
    ).fetchall()
    ekranda = [
        {"baslik": d["baslik"] or "Başlıksız duyuru", "tahta_sayisi": d["tahta_sayisi"],
         "bitis": program.saat_eki(datetime.fromtimestamp(d["bitis"], ISTANBUL).strftime("%H:%M"))}
        for d in yayinda[:OLAY_EN_COK]
    ]  # fmt: skip
    simdi = datetime.fromtimestamp(an, ISTANBUL)
    gun_sonu = int((simdi.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp())
    bugunku = []
    for p in b.execute(
        "SELECT id, baslik, tekrar, saat, baslangic, bitis, gunler, gecerlilik FROM duyuru_plani WHERE durum = 'etkin' "
        "ORDER BY id LIMIT ?",
        (PLAN_EN_COK,),
    ):
        try:
            anlar = zamanlama.sonraki(p, an, 1)
        except (ValueError, TypeError):  # bozuk plan satırı özeti durdurmasın
            continue
        if anlar and anlar[0] < gun_sonu:
            bugunku.append((anlar[0], p["id"], p["baslik"] or "Başlıksız duyuru"))
    bugunku.sort()
    planli = [{"saat": datetime.fromtimestamp(z, ISTANBUL).strftime("%H:%M"), "baslik": ad} for z, _, ad in bugunku[:OLAY_EN_COK]]
    return {
        "ekranda": ekranda,
        "planli": planli,
        "ekranda_fazla": max(0, len(yayinda) - OLAY_EN_COK),
        "planli_fazla": max(0, len(bugunku) - OLAY_EN_COK),
    }
