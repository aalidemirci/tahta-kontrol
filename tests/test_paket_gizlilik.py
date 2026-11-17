"""Temiz kurulum öğrenci oluşturmaz; ajan paketi uygulama verisini taşımaz."""

from __future__ import annotations

import io
import tarfile

from tahta_sunucu import paket, vt


def test_temiz_kurulumda_ogrenci_listesi_yok(tmp_path, monkeypatch):
    monkeypatch.setenv("TAHTA_VERI_DIZINI", str(tmp_path))
    vt.hazirla()
    with vt.islem() as b:
        for tablo in ("ogrenci", "ogrenci_aktarim", "sinav_ogrenci"):
            assert b.execute(f'SELECT COUNT(*) FROM "{tablo}"').fetchone()[0] == 0


def test_ajan_paketi_veritabani_ve_ogrenci_dosyasi_tasimaz():
    ham = paket.ajan_paketi().icerik
    konum = 8
    while konum < len(ham):
        baslik = ham[konum:konum + 60]
        boyut = int(baslik[48:58])
        ad = baslik[:16].decode().strip().rstrip("/")
        veri = ham[konum + 60:konum + 60 + boyut]
        konum += 60 + boyut + boyut % 2
        if ad != "data.tar.gz":
            continue
        with tarfile.open(fileobj=io.BytesIO(veri), mode="r:gz") as arsiv:
            dosyalar = [u.name for u in arsiv.getmembers() if u.isfile()]
        assert dosyalar
        assert all(not ad.endswith((".db", ".sqlite", ".csv", ".xls", ".xlsx", ".tkyedek", ".pem")) for ad in dosyalar)
        assert not any("/tests/" in ad or "/veri/" in ad for ad in dosyalar)
        break
    else:
        raise AssertionError("Ajan paketinin veri arşivi bulunamadı")
