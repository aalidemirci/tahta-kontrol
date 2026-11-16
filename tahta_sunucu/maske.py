"""Tahtada görünen öğrenci bilgisinin TEK maskeleme tanımı (ortak sözlük §6 M1).

Maske yalnız sunucuda üretilir. Kalabalık listesi (A4 salon giriş ekranı, şube sınav
duyurusu, gözetmen yoklama ızgarası): `kalabalik(ad_soyad)` + `no_son(okul_no)`.
Bir öğrencinin adı ve numarası tahtada hiçbir zaman ikisi birden açık görünmez (M2).
Sınıf listesi (A5, yalnız PIN sonrası): `sinif_etiketi` / `sinif_etiketleri`.
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


# ---- Aşama 5: sınıf listesi (ders yoklaması; yalnız PIN sonrası) ------------------------------
SINIF_BICIMLERI = {
    "ad_soyadbas": "Ad ve soyadın baş harfi (Ayşe Y.)",
    "no_basharf": "Okul no ve baş harfler (1047 A. Y.)",
}
VARSAYILAN_SINIF_BICIMI = "ad_soyadbas"


def _bas_harf(sozcuk: str) -> str:
    from .metin import tr_buyuk

    return tr_buyuk(sozcuk[:1]) + "." if sozcuk else ""


def sinif_etiketi(ad: str, soyad: str, okul_no: str, bicim: str = VARSAYILAN_SINIF_BICIMI) -> str:
    """Sınıf listesi etiketi (çakışma çözülmeden): "Ayşe Y." ya da "1047 A. Y.".

    `ad_soyadbas`: ad(lar) açık, soyadın yalnız baş harfi. `no_basharf`: okul no ve her adın
    ve soyadın baş harfi. Bilinmeyen biçim varsayılana düşer (tam ad tahtaya hiç gitmez, M1).
    """
    adlar = str(ad or "").split()
    soyadlar = str(soyad or "").split()
    if bicim == "no_basharf":
        harfler = " ".join(_bas_harf(s) for s in adlar + soyadlar)
        return f"{str(okul_no or '').strip()} {harfler}".strip()
    soyad_harfi = " ".join(_bas_harf(s) for s in soyadlar)
    return " ".join(p for p in (" ".join(adlar), soyad_harfi) if p) or "?"


def sinif_etiketleri(ogrenciler, bicim: str = VARSAYILAN_SINIF_BICIMI) -> dict[int, str]:
    """{id: etiket}; aynı etiketi alanlar `Ayşe Y. (47)` olur. Yine çakışanlar `no_basharf`
    biçimine geçer (`1047 A. Y.`): sözlük M1 "yine çakışırsa tam no" der, ama açık ad ile tam
    numara yan yana M2'ye aykırı olurdu ("Ayşe Y. (1047)"); tam numara yalnız baş harflerle durur.

    ogrenciler: `id`, `ad`, `soyad`, `okul_no` anahtarlı satırlar.
    """
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
