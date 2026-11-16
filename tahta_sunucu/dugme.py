"""Tahtadaki yüzer düğme (0.9.0, saha bulgusu G3).

Ekran yardımcısı tahtanın köşesinde küçük, sürüklenebilir bir düğme gösterir; dokununca küçük bir menü
açılır (Kilitle, Kapat, Yeniden başlat, Arıza bildir, Yoklama al). Sunucu yalnız hangi işlemlerin
görüneceğini belirler; işlemleri tahtadaki servis uygular ve olay olarak bildirir ("Tahta olayı").

- Ayar DURUM tabanlıdır: her `/ajan/bekle` yanıtında `ayar.dugme = {"acik": bool, "islemler": [...]}`.
  Alan hiç gelmezse (eski sunucu) ajan düğmeyi göstermez; eski ajan alanı yok sayar.
- `islemler` ETKİN listedir: kutusu işaretli olanlardan, sunucu tarafında kapalı özelliğe bağlı olan
  çıkarılır ("yoklama" yalnız ders yoklaması etkinse). Ajan ayrıca kendi koşullarına bakar
  (kilit kodu yoksa "Kilitle" soluk; arıza/yoklama yeteneği).
- Sıra sabittir (menüdeki sıra); bilinmeyen işlem adı ayara yazılmaz.
"""

from __future__ import annotations

from . import acil, vt
from . import yoklama as yoklama_mod

YETENEK = "dugme"
AYAR_ANAHTARI = "tahta_dugmesi"
# Menü sırası ve Ayarlar'daki etiketler. "kapat" ve "yeniden_baslat" tahtada 10 sn geri sayımlı onay ister.
ISLEMLER = {
    "kilitle": "Kilitle",
    "kapat": "Kapat",
    "yeniden_baslat": "Yeniden başlat",
    "ariza": "Arıza bildir",
    "yoklama": "Yoklama al",
}
VARSAYILAN = {
    "acik": True,
    "islemler": {"kilitle": True, "kapat": True, "yeniden_baslat": False, "ariza": True, "yoklama": True},
}

# Ajanın bildirdiği olay metinleri (sözleşme; işlem kaydında "Tahta olayı" ayrıntısı olarak görünür).
# Kullanıcı adı taşımaz; yalnız hesap sınıfı (etapadmin/ogretmen/ogrenci/kisisel) eklenebilir.
OLAY_KILITLENDI = "Tahtadan kilitlendi"
OLAY_KAPATILDI = "Tahtadan kapatıldı"
OLAY_YENIDEN_BASLATILDI = "Tahtadan yeniden başlatıldı"


def ayar_al(b) -> dict:
    """Kayıtlı ayar (eksik/bozuk alan varsayılandan). Dönüş: {"acik": bool, "islemler": {ad: bool}}."""
    deger = vt.ayar_al(b, AYAR_ANAHTARI)
    sonuc = {"acik": VARSAYILAN["acik"], "islemler": dict(VARSAYILAN["islemler"])}
    if isinstance(deger, dict):
        if isinstance(deger.get("acik"), bool):
            sonuc["acik"] = deger["acik"]
        islemler = deger.get("islemler")
        if isinstance(islemler, dict):
            for ad in ISLEMLER:
                if isinstance(islemler.get(ad), bool):
                    sonuc["islemler"][ad] = islemler[ad]
    return sonuc


def ayar_coz(form) -> dict:
    """Ayarlar › Tahtadaki yüzer düğme formu (bolum=dugme): dg_acik + dg_<islem> kutuları."""
    return {
        "acik": form.get("dg_acik") == "1",
        "islemler": {ad: form.get(f"dg_{ad}") == "1" for ad in ISLEMLER},
    }


def ajan_gorunumu(b) -> dict:
    """`ayar.dugme`: tahtaya inen etkin görünüm. Düğme kapalıysa ya da hiç işlem kalmadıysa acik=False."""
    a = ayar_al(b)
    yoklama_etkin = yoklama_mod.etkin(b)
    islemler = [
        ad for ad in ISLEMLER
        if a["islemler"][ad] and (ad != "yoklama" or yoklama_etkin)
    ]  # fmt: skip
    acik = bool(a["acik"] and islemler)
    return {"acik": acik, "islemler": islemler if acik else []}


def ozet(a: dict) -> str:
    """İşlem kaydı için kısa özet: "açık · Kilitle, Kapat" ya da "kapalı"."""
    if not a["acik"]:
        return "kapalı"
    secili = [ISLEMLER[ad] for ad in ISLEMLER if a["islemler"][ad]]
    return "açık · " + (", ".join(secili) if secili else "işlem seçilmedi")


def yetenekli(tahta) -> bool:
    return YETENEK in acil.yetenekler(tahta)
