"""Tahtada görünen öğrenci bilgisinin TEK maskeleme tanımı (ortak sözlük §6 M1).

Maske yalnız sunucuda üretilir. Kalabalık listesi (A4 salon giriş ekranı, şube sınav
duyurusu, gözetmen yoklama ızgarası): `kalabalik(ad_soyad)` + `no_son(okul_no)`.
Ders yoklaması listesi dışında bir öğrencinin adı ve numarası tahtada hiçbir zaman ikisi
birden açık görünmez (M2). Ders yoklaması listesi (A5, yalnız PIN ya da USB anahtar sonrası):
`sinif_etiketi` / `sinif_etiketleri`; 0.14.0'dan beri varsayılan biçim okul no + ad + soyadın
baş harfidir ("123 Ayşe Y."; kullanıcı kararı 18.11.2026). Tam soyad ve T.C. kimlik numarası
hiçbir biçimde tahtaya gitmez (`tam` biçimi yoktur).
"""

from __future__ import annotations

KALABALIK_EN_UZUN = 60


def kalabalik(ad_soyad: str) -> str:
    """"Ahmet Yılmaz" → "Ah*** Yı****"; ≤ 2 harfli sözcük → ilk harf + "*". Büyük/küçük harf korunur."""
    parcalar = str(ad_soyad or "").split()
    return " ".join(p[0] + "*" if len(p) <= 2 else p[:2] + "*" * (len(p) - 2) for p in parcalar)[:KALABALIK_EN_UZUN]


def no_son(okul_no: str) -> str:
    """Okul numarasının son 2 rakamı ("1047" → "47"); rakam yoksa metnin son 2 karakteri."""
    metin = str(okul_no or "")
    rakam = "".join(c for c in metin if c.isdigit()) or metin
    return rakam[-2:]


# ---- Aşama 5: sınıf listesi (ders yoklaması; yalnız PIN/USB sonrası) --------------------------
SINIF_BICIMLERI = {
    "no_ad_soyadbas": "Okul no, ad ve soyadın baş harfi (123 Ayşe Y.)",
    "ad_soyadbas": "Ad ve soyadın baş harfi (Ayşe Y.)",
    "no_basharf": "Okul no ve baş harfler (1047 A. Y.)",
}
VARSAYILAN_SINIF_BICIMI = "no_ad_soyadbas"
ETIKET_EN_UZUN = 40  # ajan etiketi 40 karakterde keser (servis._yoklama_listesi_coz)
OKUL_NO_EN_UZUN = 12  # etiketteki numara; boşluksuz tek belirteçtir
GEC_EKI = " (geç)"  # `yoklama_gec` yeteneği olmayan ajana geç öğrencinin etiketi bu ekle gider
KESME_ISARETI = "…"

# Tahtadaki öğrenci ızgarası (tests/yoklama_sozlesme.json "yerlesim"; ajandaki tabloyla testle eşlenir).
YOKLAMA_SAYFA_BOYU = 56
AD_ESIGI = {6: 16, 7: 13}  # sütun sayısı → etiketin ad kısmının ("Ayşe Nur Y.") en çok karakteri


def yoklama_yerlesim(n: int) -> tuple[int, int]:
    """Bir sayfadaki öğrenci ızgarası (sütun, satır): ≤ 42 → 6×7, 43–48 → 6×8, daha çoğu 7×8
    (56'dan çok öğrenci 56'lık sayfalara bölünür; sayfa sayısı `yoklama_sayfa_sayisi`)."""
    if n <= 42:
        return 6, 7
    if n <= 48:
        return 6, 8
    return 7, 8


def yoklama_sayfa_sayisi(n: int) -> int:
    return max(1, -(-int(n) // YOKLAMA_SAYFA_BOYU))


def ad_esigi(sutun: int) -> int:
    return AD_ESIGI[6] if sutun <= 6 else AD_ESIGI[7]


def _bas_harf(sozcuk: str) -> str:
    from .metin import tr_buyuk

    return tr_buyuk(sozcuk[:1]) + "." if sozcuk else ""


def ad_kisalt(ad: str, soyad: str, esik: int = AD_ESIGI[6]) -> str:
    """Etiketin ad kısmı: "Ayşe Nur Y."; `esik`ten uzunsa ikinci ve sonraki adlar baş harfe iner
    ("Muhammed E. Y."), hâlâ uzunsa ilk ad "…" ile kesilir ("Abdurr… E. Y."). Soyadın baş harfi HER
    ZAMAN kalır (Pango kısaltması sondan keser, soyad harfini yutardı; bu yüzden sunucuda yapılır).
    """
    adlar = str(ad or "").split()
    soyad_harfi = " ".join(_bas_harf(s) for s in str(soyad or "").split())

    def birlestir(*parcalar: str) -> str:
        return " ".join(p for p in (*parcalar, soyad_harfi) if p)

    if not adlar:
        return soyad_harfi or "?"
    tam = birlestir(*adlar)
    if len(tam) <= esik:
        return tam
    ortalar = [_bas_harf(a) for a in adlar[1:]]
    kisa = birlestir(adlar[0], *ortalar)
    if len(kisa) <= esik:
        return kisa
    # İlk ad kesilir; ona 3 karakter (2 harf + …) bile kalmıyorsa aradaki baş harfler de atılır.
    for orta in [ortalar, []] if ortalar else [[]]:
        kuyruk = birlestir(*orta)
        pay = esik - len(kuyruk) - (1 if kuyruk else 0)
        if pay >= 3 or not orta:
            ilk = adlar[0] if len(adlar[0]) <= pay else adlar[0][: max(1, pay - 1)] + KESME_ISARETI
            return " ".join(p for p in (ilk, kuyruk) if p)
    return kisa  # ulaşılmaz


def etiket_no(okul_no: str) -> str:
    """Etiketin numara kısmı: boşluksuz tek belirteç, en çok 12 karakter ("" = numarasız)."""
    return "".join(str(okul_no or "").split())[:OKUL_NO_EN_UZUN]


def sinif_etiketi(ad: str, soyad: str, okul_no: str, bicim: str = VARSAYILAN_SINIF_BICIMI, esik: int = AD_ESIGI[6]) -> str:
    """Sınıf listesi etiketi (çakışma çözülmeden): "123 Ayşe Y.", "Ayşe Y." ya da "1047 A. Y.".

    `no_ad_soyadbas`: okul no + ad(lar) + soyadın baş harfi; ad kısmı `esik`e göre kısalır
    (`ad_kisalt`), okul no boşsa yalnız ad kısmı. `ad_soyadbas`: ad(lar) açık, soyadın yalnız baş
    harfi. `no_basharf`: okul no ve her adın ve soyadın baş harfi. Bilinmeyen biçim (elle yazılmış
    "tam" dahil) en dar açık biçime, `ad_soyadbas`a düşer (tam soyad tahtaya hiç gitmez, M1).
    """
    adlar = str(ad or "").split()
    soyadlar = str(soyad or "").split()
    if bicim == "no_ad_soyadbas":
        return " ".join(p for p in (etiket_no(okul_no), ad_kisalt(ad, soyad, esik)) if p)[:ETIKET_EN_UZUN]
    if bicim == "no_basharf":
        harfler = " ".join(_bas_harf(s) for s in adlar + soyadlar)
        return f"{str(okul_no or '').strip()} {harfler}".strip()
    soyad_harfi = " ".join(_bas_harf(s) for s in soyadlar)
    return " ".join(p for p in (" ".join(adlar), soyad_harfi) if p) or "?"


def gec_ekli(etiket: str) -> str:
    """`yoklama_gec` yeteneği olmayan ajana giden geç öğrenci etiketi: sonuna " (geç)", 40 karakter içinde."""
    return str(etiket)[: ETIKET_EN_UZUN - len(GEC_EKI)].rstrip() + GEC_EKI


def sinif_etiketleri(ogrenciler, bicim: str = VARSAYILAN_SINIF_BICIMI, sutun: int | None = None) -> dict[int, str]:
    """{id: etiket}. `no_ad_soyadbas` biçiminde çakışma çözümü ÇALIŞMAZ (numara ayırır); ad kısmının
    eşiği sütun sayısından gelir (`sutun` verilmezse mevcuttan: `yoklama_yerlesim(len(ogrenciler))`).
    Öbür biçimlerde aynı etiketi alanlar `Ayşe Y. (47)` olur. Yine çakışanlar `no_basharf`
    biçimine geçer (`1047 A. Y.`): sözlük M1 "yine çakışırsa tam no" der, ama açık ad ile tam
    numara yan yana M2'ye aykırı olurdu ("Ayşe Y. (1047)"); tam numara yalnız baş harflerle durur.

    ogrenciler: `id`, `ad`, `soyad`, `okul_no` anahtarlı satırlar.
    """
    ogrenciler = list(ogrenciler)
    if bicim == "no_ad_soyadbas":
        esik = ad_esigi(sutun or yoklama_yerlesim(len(ogrenciler))[0])
        return {o["id"]: sinif_etiketi(o["ad"], o["soyad"], o["okul_no"], bicim, esik) for o in ogrenciler}
    ilk = {o["id"]: sinif_etiketi(o["ad"], o["soyad"], o["okul_no"], bicim) for o in ogrenciler}
    no = {o["id"]: str(o["okul_no"] or "").strip() for o in ogrenciler}

    def cakisanlar(etiketler: dict[int, str]) -> set[int]:
        sayac: dict[str, int] = {}
        for e in etiketler.values():
            sayac[e] = sayac.get(e, 0) + 1
        return {i for i, e in etiketler.items() if sayac[e] > 1}

    sonuc = dict(ilk)
    cift = cakisanlar(sonuc)
    for i in cift:
        sonuc[i] = f"{ilk[i]} ({no_son(no[i])})"
    if bicim != "no_basharf":
        sahip = {o["id"]: o for o in ogrenciler}
        for i in cakisanlar(sonuc) & cift:
            o = sahip[i]
            sonuc[i] = sinif_etiketi(o["ad"], o["soyad"], o["okul_no"], "no_basharf")
    return sonuc
