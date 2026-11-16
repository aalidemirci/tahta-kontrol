"""Tahtaya giden komutlar: adlar, ömürler ve kuyruğa yazma.

Komutlar `komut` tablosunda bekler; tahta `/ajan/bekle` ile gelip alır (bağlantıyı hep
tahta açar). Komut yazan işlev uyandırma yapmaz: çağıran, veritabanı işlemi bittikten
sonra ilgili tahtaları uyandırır.
"""

from __future__ import annotations

import json

from . import vt

# Komutun geçerlilik süresi (sn). Kapatma komutu kısa ömürlüdür: bir saat sonra
# açılan tahta, eskimiş bir "kapat" komutuyla kapanmamalıdır. "duyuru" burada YOKTUR:
# ömrü duyurunun bitişinden hesaplanıp açıkça verilir.
KOMUT_OMRU = {
    "kilitle": 600,
    "kilit_ac": 600,
    "duyuru_kaldir": 600,
    "kapat": 120,
    "yeniden_baslat": 120,
    "tani": 86400,
    "guncelle": 86400,
    "envanter": 86400,
    # K7: gün sonu temizliği kısa ömürlüdür; sonradan açılan tahta eski temizlik komutunu almaz.
    "temizlik": 120,
}
KOMUT_ADI = {
    "kilitle": "Kilitle",
    "kilit_ac": "Kilidi aç",
    "duyuru": "Duyuru",
    "duyuru_kaldir": "Duyuruyu kaldır",
    "kapat": "Kapat",
    "yeniden_baslat": "Yeniden başlat",
    "tani": "Tanılama",
    "guncelle": "Ajanı güncelle",
    "envanter": "Envanteri yenile",
    "uyandir": "Uzaktan aç",
    "temizlik": "Oturum temizliği",
}
KOMUT_DURUMU = {
    "bekliyor": "Tahta bekleniyor",
    "gonderildi": "Tahtaya iletildi",
    "tamam": "Uygulandı",
    "hata": "Başarısız",
    "zaman_asimi": "Süresi doldu",
    "iptal": "İptal edildi",
}


def komut_ekle(
    b,
    tahta_id: int,
    tur: str,
    veri: dict,
    olusturan: str,
    omur: int | None = None,
    *,
    duyuru_id: int | None = None,
    simdi: int | None = None,
) -> int:
    """Komutu kuyruğa yazar, kimliğini döndürür.

    `omur` verilmezse KOMUT_OMRU'ndan alınır; "duyuru" için açıkça verilmesi zorunludur.
    `simdi` (epoch) zamanlayıcının hesapladığı ana göre bitişi sabitler.
    """
    if omur is None:
        if tur not in KOMUT_OMRU:
            raise ValueError(f"'{tur}' komutu için ömür (omur) açıkça verilmeli.")
        omur = KOMUT_OMRU[tur]
    an = vt.simdi() if simdi is None else int(simdi)
    imlec = b.execute(
        "INSERT INTO komut (tahta_id, tur, veri_json, olusturan, olusturma, bitis, duyuru_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (tahta_id, tur, json.dumps(veri, ensure_ascii=False), olusturan, vt.simdi(), an + int(omur), duyuru_id),
    )
    return imlec.lastrowid
