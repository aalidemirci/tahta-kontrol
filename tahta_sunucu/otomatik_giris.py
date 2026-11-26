"""Tahtanın açılışta ortak hesaba kendiliğinden girmesi (0.22.0, kullanıcı isteği 27.11.2026; kural 39).

ETAP'ta tahta uzaktan ya da düğmeyle açılınca giriş ekranında bekler; oturum açılmadığı için ekran yardımcısı
başlamaz, kilit ve duyuru ekrana gelmez ("Ekran yardımcısı yok"). Bu ayar tahtaya "açılışta `ogretmen`
hesabına gir" der; LightDM yapılandırmasını tahtadaki ajan (root) kendisi yazar.

- etapadmin parolası GEREKMEZ ve hiçbir yerde istenmez/saklanmaz: ajan zaten yönetici yetkisiyle çalışır.
- Ayar DURUMDUR, üç değerlidir:
  * `dokunma` (varsayılan): alan tahtaya HİÇ gönderilmez; tahtadaki ayara (elle yapılmış olsa da) dokunulmaz.
  * `ogretmen`: ajan `/etc/lightdm/lightdm.conf.d/50-tahta-otomatik-giris.conf` dosyasını yazar.
  * `kapali`: ajan YALNIZ kendi dosyasını siler (başka dosyadaki ayara dokunmaz, yalnız bildirir).
- Hesap listesi SABİTTİR ve dardır: yalnız `ogretmen`. etapadmin, root ve kişisel hesap hiçbir koşulda
  seçilemez; ajan da kendi listesiyle ayrıca denetler (sunucu daraltır, genişletemez).
- Kilitsiz açılmasın diye `ogretmen` yalnız açılışta kilit AÇIK ve kilit kodu TANIMLI iken kaydedilir;
  sonradan biri kapanırsa Bugün yöneticiyi uyarır (ayar kendiliğinden değişmez).
- Ayar bir sonraki açılışta geçerli olur: ajan giriş ekranını (lightdm) yeniden başlatmaz, açık dersi bozmaz.
- Ajan durumunda `otomatik_giris` alanı bildirir (`tahta_durumu`): yalnız hesap SINIFI (standart ad ya da
  "kisisel"), kendi dosyası var mı, başka bir dosya onu eziyor mu. Hesap adı, dosya yolu, içerik gelmez.
"""

from __future__ import annotations

import json

from . import acil, acilis_kilidi, vt

YETENEK = "otomatik_giris"
AYAR_ANAHTARI = "otomatik_giris"
VARSAYILAN = "dokunma"
SECENEKLER = {
    "dokunma": "Tahtalardaki ayara dokunma",
    "ogretmen": "Öğretmen hesabıyla otomatik gir",
    "kapali": "Otomatik girişi kaldır",
}
HESAPLAR = ("ogretmen",)  # ajandaki OTOMATIK_GIRIS_HESAPLARI ile aynı (test karşılaştırır)
ISLEM_ADI = "Otomatik giriş ayarı kaydedildi"
# Ajanın bildirdiği etkin hesap sınıfının paneldeki adı.
SINIF_ADI = {
    "ogretmen": "öğretmen",
    "ogrenci": "öğrenci",
    "etapadmin": "etapadmin",
    "kisisel": "kişisel hesap",
}


def ayar_al(b) -> str:
    deger = vt.ayar_al(b, AYAR_ANAHTARI)
    return deger if deger in SECENEKLER else VARSAYILAN


def ayar_coz(form) -> str | None:
    """Ayarlar › Otomatik giriş formu (bolum=otomatik_giris): tek radyo `og_kip`; bilinmeyen değer None."""
    deger = str(form.get("og_kip") or "")
    return deger if deger in SECENEKLER else None


def engel(b) -> str | None:
    """`ogretmen` neden kaydedilemez / neden tehlikelidir; sorun yoksa None."""
    if not vt.ayar_al(b, "kilit_kodu"):
        return "kilit kodu belirlenmedi"
    if not acilis_kilidi.ayar_al(b):
        return "açılışta kilit kapalı"
    return None


def ajan_gorunumu(b) -> dict | None:
    """`ayar.otomatik_giris`: `dokunma`da None (alan GÖNDERİLMEZ), yoksa {"hesap": "ogretmen" | None}."""
    kip = ayar_al(b)
    if kip == "dokunma":
        return None
    return {"hesap": "ogretmen" if kip == "ogretmen" else None}


def ozet(kip: str) -> str:
    return {"dokunma": "dokunma", "ogretmen": "öğretmen hesabı", "kapali": "kaldır"}.get(kip, kip)


def yetenekli(tahta) -> bool:
    return YETENEK in acil.yetenekler(tahta)


def tahta_durumu(durum: dict) -> dict | None:
    """Ajanın bildirdiği `otomatik_giris` alanını panel için süzer; alan yoksa (eski ajan) None.

    Dönüş: {"lightdm": bool, "etkin": "" | sınıf adı, "bizim": bool, "ezilmis": bool, "hata": str}.
    Bilinmeyen değerler atılır; hesap adı yalnız standart sınıf ya da "kişisel hesap" olarak görünür.
    """
    ham = durum.get("otomatik_giris") if isinstance(durum, dict) else None
    if not isinstance(ham, dict):
        return None
    etkin = ham.get("etkin")
    hata = ham.get("hata")
    return {
        "lightdm": ham.get("lightdm") is True,
        "etkin": SINIF_ADI.get(etkin, "") if isinstance(etkin, str) else "",
        "bizim": ham.get("bizim") is True,
        "ezilmis": ham.get("ezilmis") is True,
        "hata": hata[:200] if isinstance(hata, str) else "",
    }


def _durumlar(b, yalniz_bizim: bool = False):
    """Onaylı tahtaların (yetenekler, süzülmüş otomatik giriş durumu) çiftleri.

    yalniz_bizim: yalnız durumunda `"bizim": true` geçen satırlar okunur (ön süzgeç; asıl karar JSON'dan)."""
    sql = "SELECT durum_json FROM tahta WHERE durum = 'onayli'"
    if yalniz_bizim:
        sql += " AND durum_json LIKE '%\"bizim\": true%'"
    for t in b.execute(sql):
        try:
            durum = json.loads(t["durum_json"] or "{}")
        except ValueError:
            durum = {}
        if not isinstance(durum, dict):
            durum = {}
        yetenekler = durum.get("yetenekler") if isinstance(durum.get("yetenekler"), list) else []
        yield yetenekler, tahta_durumu(durum)


def ogretmenle_acilan_sayisi(b) -> int:
    """Tahta Kontrol dosyasıyla öğretmen hesabına giren tahta sayısı (ajanın bildirdiğine göre).

    Ayar "dokunma"ya alınınca dosya tahtada KALIR; kilit koruması ayara değil buna da bakar (kural 39)."""
    return sum(1 for _, d in _durumlar(b, True) if d and d["bizim"] and d["etkin"] == SINIF_ADI["ogretmen"])


def kilitsiz_risk(b) -> dict | None:
    """Tahtalar öğretmen oturumunda kilitsiz açılabilir mi? {"neden", "kip", "sayi"} ya da None.

    Ayar "ogretmen" ise ya da ayar başka olsa da tahtalarda bizim dosyamız duruyorsa (ve `engel` varsa) risk vardır.
    Bugün bunu /api/durum'da 4 sn'de bir çağırır: olağan yol (ayar "ogretmen" değil, aday tahta yok) TEK sorgudur
    (`test_bugun_sorgu_sayisi_tahta_ve_ogrenci_sayisindan_bagimsiz`)."""
    satir = b.execute(
        "SELECT (SELECT deger FROM ayar WHERE anahtar = ?) AS kip, "
        "(SELECT COUNT(*) FROM tahta WHERE durum = 'onayli' AND durum_json LIKE ?) AS aday",
        (AYAR_ANAHTARI, '%"bizim": true%'),
    ).fetchone()
    try:
        kip = json.loads(satir["kip"]) if satir["kip"] else VARSAYILAN
    except ValueError:
        kip = VARSAYILAN
    kip = kip if kip in SECENEKLER else VARSAYILAN
    if kip != "ogretmen" and not satir["aday"]:
        return None
    neden = engel(b)
    if not neden:
        return None
    sayi = ogretmenle_acilan_sayisi(b) if satir["aday"] else 0
    if kip != "ogretmen" and not sayi:
        return None
    return {"neden": neden, "kip": kip, "sayi": sayi}


def sayilar(b) -> dict:
    """Onaylı tahtalarda: {"yeteneksiz", "uygulandi", "bekliyor"} — Ayarlar kartının sayıları.

    `uygulandi`: ajan bildirdiği etkin hesap ayarla uyumlu (ogretmen'de öğretmen, kapali'da bizim dosya yok).
    """
    kip = ayar_al(b)
    sonuc = {"yeteneksiz": 0, "uygulandi": 0, "bekliyor": 0}
    for yetenekler, d in _durumlar(b):
        if YETENEK not in yetenekler:
            sonuc["yeteneksiz"] += 1
            continue
        if d is None or kip == "dokunma":
            continue
        tamam = (d["bizim"] and not d["ezilmis"]) if kip == "ogretmen" else not d["bizim"]
        sonuc["uygulandi" if tamam else "bekliyor"] += 1
    return sonuc
