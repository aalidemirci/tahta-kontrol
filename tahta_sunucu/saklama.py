"""Öğrenci verisi içeren kayıtların saklama sınırı: öğretim yılı bitiş tarihi (16.11.2026 kararı K3).

Ders yoklaması, sınav yoklaması (sınavın öğrenci listesi) ve boş ders uyarısı, Ayarlar'da
yöneticinin girdiği **öğretim yılı bitiş tarihine** kadar saklanır. Tarih geçince (ertesi gün)
o tarihte ve öncesinde oluşmuş kayıtlar kalıcı silinir (`secure_delete` + WAL budama; silmeyi
her iş kendi zamanlayıcısında yapar). Tarihten SONRA oluşan kayıtlar (yaz dönemi, yeni yılın ilk
günleri) bir sonraki tarihe kadar kalır.

Tarih girilmemişse hiçbir şey silinmez ve Ayarlar'da uyarı görünür. Tarih geçtikten sonra
yönetici yeni öğretim yılının bitiş tarihini girer (o zamana kadar Ayarlar uyarı gösterir).

Bu modül veritabanına yalnız `ayar` tablosu üzerinden dokunur; silme sorgularını çağıran yazar.
"""

from __future__ import annotations

from datetime import date, timedelta

from . import vt

AYAR_ANAHTARI = "ogretim_yili_bitis"
# Yanlış yazılmış yılı (2207) yakalamak için: bugünden en çok bu kadar gün sonrası girilebilir.
EN_UZAK_GUN = 550


def bitis_al(b) -> date | None:
    deger = vt.ayar_al(b, AYAR_ANAHTARI)
    try:
        return date.fromisoformat(str(deger)) if deger else None
    except ValueError:
        return None


def imha_siniri(b, bugun: date) -> date | None:
    """Bitiş tarihi geçtiyse (bugün > bitiş) o tarih: bu tarihte ve öncesinde oluşan kayıtlar silinir."""
    bitis = bitis_al(b)
    return bitis if bitis and bugun > bitis else None


def tarih_metni(gun: date | None) -> str:
    return f"{gun:%d.%m.%Y}" if gun else ""


def silinme_metni(b, kayit_tarihi: date | None = None) -> str:
    """Arayüz notu: bu (ya da bugünkü) kayıt ne zaman silinir? Örn. "öğretim yılı sonunda (26.06.2027'den sonra)"."""
    bitis = bitis_al(b)
    if not bitis:
        return "öğretim yılı bitiş tarihi girilmediği için kendiliğinden silinmez (Ayarlar › Kişisel veri saklama)"
    if kayit_tarihi and kayit_tarihi > bitis:
        return "bir sonraki öğretim yılının bitiş tarihi geçince silinir"
    return f"öğretim yılı bitiş tarihi ({tarih_metni(bitis)}) geçince kendiliğinden silinir"


def durum(b, bugun: date) -> dict:
    """Ayarlar ve uyarı şeridi için: {"bitis", "bitis_metni", "girildi", "gecti", "uyari", "oneri", "oneri_metni"}.

    `oneri`: Okul Zili takviminde öğretimin bitişi (varsa ve bugünden sonraysa) — tek tıkla doldurmak için.
    """
    bitis = bitis_al(b)
    gecti = bool(bitis and bugun > bitis)
    uyari = None
    if not bitis:
        uyari = ("Öğretim yılı bitiş tarihi girilmedi: ders yoklaması, sınav listeleri ve boş ders uyarıları "
                 "kendiliğinden silinmiyor.")  # fmt: skip
    elif gecti:
        uyari = (f"Öğretim yılı bitiş tarihi ({tarih_metni(bitis)}) geçti; o tarihe kadarki kayıtlar silindi ya da "
                 "bir saat içinde silinecek. Yeni öğretim yılının bitiş tarihini girin.")  # fmt: skip
    oneri = None
    takvim = vt.ayar_al(b, "zil_takvimi")
    ham = ((takvim or {}).get("ogretim") or {}).get("bit") if isinstance(takvim, dict) else None
    try:
        aday = date.fromisoformat(str(ham)[:10]) if ham else None
    except ValueError:
        aday = None
    if aday and aday >= bugun and aday != bitis:
        oneri = aday
    return {
        "bitis": bitis.isoformat() if bitis else "",
        "bitis_metni": tarih_metni(bitis),
        "girildi": bool(bitis),
        "gecti": gecti,
        "uyari": uyari,
        "oneri": oneri.isoformat() if oneri else "",
        "oneri_metni": tarih_metni(oneri),
        "en_gec": (bugun + timedelta(days=EN_UZAK_GUN)).isoformat(),
    }


def bitis_coz(ham, bugun: date) -> date | None:
    """Formdan gelen tarih; boş = None (silme yapılmaz). Geçersizde iletili ValueError."""
    s = str(ham or "").strip()
    if not s:
        return None
    try:
        gun = date.fromisoformat(s)
    except ValueError:
        raise ValueError("Öğretim yılı bitiş tarihi geçerli bir tarih olmalı.") from None
    if gun > bugun + timedelta(days=EN_UZAK_GUN):
        raise ValueError("Öğretim yılı bitiş tarihi en çok 18 ay sonrası olabilir; yılı denetleyin.")
    return gun
