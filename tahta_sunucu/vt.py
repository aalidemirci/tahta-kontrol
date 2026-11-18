"""SQLite veritabanı: şema, göçler ve küçük yardımcılar.

Zamanlar UTC saniye (epoch) olarak saklanır; ekranda Europe/Istanbul saatine çevrilir.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import ayar

# Her öğe bir şema sürümüdür; yeni sürüm listenin SONUNA eklenir, eskiler değişmez.
GOCLER = [
    """
    CREATE TABLE ayar (anahtar TEXT PRIMARY KEY, deger TEXT NOT NULL);
    CREATE TABLE kullanici (
        id INTEGER PRIMARY KEY, ad TEXT NOT NULL UNIQUE, gorunen_ad TEXT NOT NULL,
        parola_ozet TEXT NOT NULL, rol TEXT NOT NULL, aktif INTEGER NOT NULL DEFAULT 1,
        olusturma INTEGER NOT NULL);
    CREATE TABLE oturum (
        belirtec_ozet TEXT PRIMARY KEY, kullanici_id INTEGER NOT NULL REFERENCES kullanici(id),
        bitis INTEGER NOT NULL);
    CREATE TABLE tahta (
        id INTEGER PRIMARY KEY, ad TEXT NOT NULL, derslik TEXT NOT NULL DEFAULT '',
        anahtar_ozet TEXT NOT NULL, durum TEXT NOT NULL DEFAULT 'bekliyor',
        kayit_zamani INTEGER NOT NULL, son_gorulme INTEGER, ip TEXT NOT NULL DEFAULT '',
        mac TEXT NOT NULL DEFAULT '', makine_adi TEXT NOT NULL DEFAULT '',
        surum TEXT NOT NULL DEFAULT '', platform TEXT NOT NULL DEFAULT '',
        durum_json TEXT NOT NULL DEFAULT '{}', tani_json TEXT, tani_zamani INTEGER);
    CREATE TABLE komut (
        id INTEGER PRIMARY KEY, tahta_id INTEGER NOT NULL REFERENCES tahta(id),
        tur TEXT NOT NULL, veri_json TEXT NOT NULL DEFAULT '{}', olusturan TEXT NOT NULL,
        olusturma INTEGER NOT NULL, bitis INTEGER NOT NULL,
        durum TEXT NOT NULL DEFAULT 'bekliyor', sonuc TEXT NOT NULL DEFAULT '', tamamlanma INTEGER);
    CREATE INDEX komut_bekleyen ON komut (tahta_id, durum);
    CREATE TABLE duyuru (
        id INTEGER PRIMARY KEY, baslik TEXT NOT NULL, metin TEXT NOT NULL, sure_sn INTEGER NOT NULL,
        kapatilabilir INTEGER NOT NULL, hedef TEXT NOT NULL, olusturan TEXT NOT NULL,
        olusturma INTEGER NOT NULL);
    CREATE TABLE kayit (
        id INTEGER PRIMARY KEY, zaman INTEGER NOT NULL, kullanici TEXT NOT NULL,
        islem TEXT NOT NULL, ayrinti TEXT NOT NULL DEFAULT '', ip TEXT NOT NULL DEFAULT '');
    """,
    # 0.3.0 — duyuru zamanlama, hedef grupları, acil durum yayını
    """
    ALTER TABLE tahta ADD COLUMN bina TEXT NOT NULL DEFAULT '';
    ALTER TABLE tahta ADD COLUMN kat INTEGER;
    ALTER TABLE tahta ADD COLUMN duzeyler TEXT NOT NULL DEFAULT '';
    ALTER TABLE tahta ADD COLUMN devre TEXT NOT NULL DEFAULT '';
    ALTER TABLE tahta ADD COLUMN subeler TEXT NOT NULL DEFAULT '';

    CREATE TABLE tahta_grubu (
        id INTEGER PRIMARY KEY,
        ad TEXT NOT NULL UNIQUE COLLATE NOCASE,
        aciklama TEXT NOT NULL DEFAULT '',
        olusturan TEXT NOT NULL, olusturma INTEGER NOT NULL);
    CREATE TABLE tahta_grubu_uye (
        grup_id INTEGER NOT NULL REFERENCES tahta_grubu(id) ON DELETE CASCADE,
        tahta_id INTEGER NOT NULL REFERENCES tahta(id) ON DELETE CASCADE,
        PRIMARY KEY (grup_id, tahta_id));

    CREATE TABLE duyuru_plani (
        id INTEGER PRIMARY KEY,
        baslik TEXT NOT NULL, metin TEXT NOT NULL,
        sure_sn INTEGER NOT NULL, kapatilabilir INTEGER NOT NULL,
        hedef_json TEXT NOT NULL,
        tekrar TEXT NOT NULL,
        saat TEXT NOT NULL,
        baslangic TEXT NOT NULL, bitis TEXT NOT NULL,
        gunler TEXT NOT NULL,
        durum TEXT NOT NULL DEFAULT 'etkin',
        gecerlilik INTEGER NOT NULL,
        olusturan TEXT NOT NULL, olusturma INTEGER NOT NULL,
        guncelleyen TEXT NOT NULL DEFAULT '', guncelleme INTEGER);

    ALTER TABLE duyuru ADD COLUMN plan_id INTEGER REFERENCES duyuru_plani(id);
    ALTER TABLE duyuru ADD COLUMN an INTEGER;
    ALTER TABLE duyuru ADD COLUMN bitis INTEGER;
    ALTER TABLE duyuru ADD COLUMN durum TEXT NOT NULL DEFAULT 'gonderildi';
    ALTER TABLE duyuru ADD COLUMN hedef_json TEXT NOT NULL DEFAULT '{}';
    ALTER TABLE duyuru ADD COLUMN tahta_sayisi INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE duyuru ADD COLUMN durduran TEXT NOT NULL DEFAULT '';
    UPDATE duyuru SET an = olusturma, bitis = olusturma + sure_sn WHERE an IS NULL;
    CREATE UNIQUE INDEX duyuru_plan_an ON duyuru (plan_id, an) WHERE plan_id IS NOT NULL;

    ALTER TABLE komut ADD COLUMN duyuru_id INTEGER;
    CREATE INDEX komut_duyuru ON komut (duyuru_id);

    ALTER TABLE kullanici ADD COLUMN acil_yetki INTEGER NOT NULL DEFAULT 0;
    UPDATE kullanici SET acil_yetki = 1 WHERE rol = 'yonetici';

    CREATE TABLE acil_yayin (
        id INTEGER PRIMARY KEY,
        tur TEXT NOT NULL,
        sablon TEXT NOT NULL DEFAULT '',
        baslik TEXT NOT NULL, metin TEXT NOT NULL,
        baslangic INTEGER NOT NULL, bitis_plan INTEGER NOT NULL,
        bitis INTEGER,
        bitis_nedeni TEXT NOT NULL DEFAULT '',
        baslatan TEXT NOT NULL, bitiren TEXT NOT NULL DEFAULT '',
        ip TEXT NOT NULL DEFAULT '', hedef_sayisi INTEGER NOT NULL,
        -- başlangıç anındaki hedef tahtalar ve durumları {"<tahta_id>": ""|"cevrimdisi"|"ekran_yok"};
        -- rapordaki "neden" sütunu bugünkü değil yayın anındaki duruma dayanır
        hedef_durum_json TEXT NOT NULL DEFAULT '{}');
    CREATE TABLE acil_teslim (
        acil_id INTEGER NOT NULL REFERENCES acil_yayin(id),
        tahta_id INTEGER NOT NULL REFERENCES tahta(id),
        ilk_gorulme INTEGER NOT NULL,
        ekran_var INTEGER NOT NULL,
        yol TEXT NOT NULL,
        PRIMARY KEY (acil_id, tahta_id));
    """,
    # 0.4.0 — ders programı, zil saatleri, program kilidi, boş ders uyarısı
    """
    CREATE TABLE ders_saati (
        gun INTEGER NOT NULL CHECK (gun BETWEEN 0 AND 6),
        devre TEXT NOT NULL,
        devre_adi TEXT NOT NULL,
        ders_no INTEGER NOT NULL CHECK (ders_no BETWEEN 1 AND 20),
        baslangic TEXT NOT NULL,
        bitis TEXT NOT NULL,
        PRIMARY KEY (gun, devre, ders_no));
    -- Derslik programı: bu tahtada bu ders saatinde ders VAR (öğretmen ve ders adı tutulmaz).
    CREATE TABLE tahta_ders (
        tahta_id INTEGER NOT NULL REFERENCES tahta(id),
        gun INTEGER NOT NULL CHECK (gun BETWEEN 0 AND 6),
        devre TEXT NOT NULL,
        ders_no INTEGER NOT NULL,
        sube TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (tahta_id, gun, devre, ders_no));
    CREATE TABLE program_istisna (
        id INTEGER PRIMARY KEY,
        bas INTEGER NOT NULL,
        bit INTEGER NOT NULL,
        tahta_ids TEXT NOT NULL DEFAULT '',
        neden TEXT NOT NULL DEFAULT '',
        olusturan TEXT NOT NULL,
        olusturma INTEGER NOT NULL,
        iptal INTEGER);
    CREATE INDEX program_istisna_aralik ON program_istisna (bit);
    CREATE TABLE program_isaret (
        tahta_id INTEGER NOT NULL,
        anahtar TEXT NOT NULL,
        zaman INTEGER NOT NULL,
        PRIMARY KEY (tahta_id, anahtar));
    CREATE TABLE bos_ders_uyari (
        id INTEGER PRIMARY KEY,
        tahta_id INTEGER NOT NULL REFERENCES tahta(id),
        tarih TEXT NOT NULL,
        devre TEXT NOT NULL,
        ders_no INTEGER NOT NULL,
        ders_bas INTEGER NOT NULL,
        neden TEXT NOT NULL,
        olusturma INTEGER NOT NULL,
        cozulme INTEGER,
        goruldu_kullanici TEXT,
        goruldu_zaman INTEGER,
        UNIQUE (tahta_id, tarih, devre, ders_no));
    ALTER TABLE tahta ADD COLUMN program_muaf INTEGER NOT NULL DEFAULT 0;
    """,
    # 0.5.0 — Kelebek sınav duyurusu, sınav kipi, sınav yoklaması (ad soyad SAKLANMAZ; yalnız maske)
    """
    CREATE TABLE sinav (
        id INTEGER PRIMARY KEY,
        ad TEXT NOT NULL,
        baslangic INTEGER NOT NULL,             -- UTC epoch; 0 = künye eksik (R5 başlığı okunamadı)
        sure_dk INTEGER NOT NULL DEFAULT 40,
        durum TEXT NOT NULL DEFAULT 'taslak',   -- taslak | yayinda
        donem TEXT NOT NULL DEFAULT '',
        kaynak_ozet TEXT NOT NULL DEFAULT '',   -- yüklenen dosyanın SHA-256'sı (dosya saklanmaz)
        bitirme INTEGER,
        kisisel_silinme INTEGER,
        olusturan TEXT NOT NULL,
        olusturma INTEGER NOT NULL,
        guncelleme INTEGER NOT NULL);
    CREATE TABLE sinav_ders (
        id INTEGER PRIMARY KEY,
        sinav_id INTEGER NOT NULL REFERENCES sinav(id) ON DELETE CASCADE,
        ad TEXT NOT NULL,
        sure_dk INTEGER NOT NULL,
        UNIQUE (sinav_id, ad));
    CREATE TABLE sinav_salon (
        id INTEGER PRIMARY KEY,
        sinav_id INTEGER NOT NULL REFERENCES sinav(id) ON DELETE CASCADE,
        ad TEXT NOT NULL,
        tahta_id INTEGER REFERENCES tahta(id),
        gozetmen_kodu TEXT NOT NULL,
        gozetmen_adi TEXT NOT NULL DEFAULT '',
        uzatma_dk INTEGER NOT NULL DEFAULT 0,
        kip_kapanma INTEGER,
        kip_kapatan TEXT NOT NULL DEFAULT '',
        yoklama_zamani INTEGER,
        yoklama_kaynak TEXT NOT NULL DEFAULT '',
        ozet_mevcut INTEGER,
        ozet_gelmeyen INTEGER,
        UNIQUE (sinav_id, ad));
    CREATE INDEX sinav_salon_tahta ON sinav_salon (tahta_id);
    CREATE TABLE sinav_ogrenci (
        id INTEGER PRIMARY KEY,
        sinav_id INTEGER NOT NULL REFERENCES sinav(id) ON DELETE CASCADE,
        salon_id INTEGER NOT NULL REFERENCES sinav_salon(id) ON DELETE CASCADE,
        ders_id INTEGER NOT NULL REFERENCES sinav_ders(id) ON DELETE CASCADE,
        koltuk INTEGER NOT NULL,
        okul_no TEXT NOT NULL,
        sube TEXT NOT NULL,
        maske TEXT NOT NULL,
        gelmedi INTEGER NOT NULL DEFAULT 0,
        isaretleyen TEXT NOT NULL DEFAULT '',
        isaret_zamani INTEGER,
        UNIQUE (salon_id, koltuk),
        UNIQUE (sinav_id, okul_no));
    CREATE INDEX sinav_ogrenci_salon ON sinav_ogrenci (salon_id, koltuk);
    CREATE TABLE sinav_eslesme (
        tur TEXT NOT NULL,                      -- yalnız 'salon' (şube→tahta: tahta.subeler)
        ad TEXT NOT NULL,
        tahta_id INTEGER NOT NULL REFERENCES tahta(id),
        PRIMARY KEY (tur, ad));
    ALTER TABLE duyuru ADD COLUMN sinav_id INTEGER;
    CREATE INDEX duyuru_sinav ON duyuru (sinav_id);
    """,
    # 0.6.0 — ders yoklaması: öğretmen kodu + PIN, sınıf listesi, yoklama, icmal (öğrenci verisi saklama süreli)
    """
    CREATE TABLE ogretmen (
        id INTEGER PRIMARY KEY, ad TEXT NOT NULL, soyad TEXT NOT NULL DEFAULT '',
        aktif INTEGER NOT NULL DEFAULT 1);
    -- PIN verisi öğretmen tablosundan AYRI durur: öğretmen listesini okuyan sorgu özetleri taşımasın.
    CREATE TABLE ogretmen_pin (
        ogretmen_id INTEGER PRIMARY KEY REFERENCES ogretmen(id) ON DELETE CASCADE,
        kod TEXT NOT NULL UNIQUE,               -- '101'..'999'; gizli değildir
        pin_ozet TEXT,                          -- guvenlik.parola_ozetle; NULL = PIN verilmedi
        pin_zamani INTEGER,
        hatali_sayi INTEGER NOT NULL DEFAULT 0,
        hatali_ilk INTEGER,                     -- 24 saatlik sayaç penceresinin başı
        kilitli INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE ogrenci (
        id INTEGER PRIMARY KEY,
        sube TEXT NOT NULL,                     -- kanonik '10/A'
        okul_no TEXT NOT NULL,                  -- metin: baştaki sıfırlar korunur
        ad TEXT NOT NULL, soyad TEXT NOT NULL,
        aktif INTEGER NOT NULL DEFAULT 1,
        guncelleme INTEGER NOT NULL);
    CREATE UNIQUE INDEX ogrenci_okul_no ON ogrenci (okul_no);
    CREATE INDEX ogrenci_sube ON ogrenci (sube, aktif);
    CREATE TABLE yoklama (
        id INTEGER PRIMARY KEY,
        tarih TEXT NOT NULL,                    -- 'YYYY-MM-DD', Europe/Istanbul, SUNUCU saatiyle
        ders_no INTEGER NOT NULL,
        sube TEXT NOT NULL,
        ogretmen_id INTEGER REFERENCES ogretmen(id) ON DELETE SET NULL,
        ders_adi TEXT NOT NULL DEFAULT '',
        tahta_id INTEGER REFERENCES tahta(id) ON DELETE SET NULL,
        kaynak TEXT NOT NULL,                   -- 'tahta' | 'panel'
        kaydeden TEXT NOT NULL,                 -- 'ogretmen:112' ya da panel kullanıcı adı
        mevcut INTEGER NOT NULL,                -- kayıt anında şubedeki etkin öğrenci sayısı
        olusturma INTEGER NOT NULL, guncelleme INTEGER NOT NULL);
    -- Aynı öğretmen aynı ders saatine tek kayıt; farklı öğretmenler ve panel kaydı ayrı satırdır (icmal birleşimi alır).
    CREATE UNIQUE INDEX yoklama_tek ON yoklama (tarih, sube, ders_no, IFNULL(ogretmen_id, 0), kaynak);
    CREATE INDEX yoklama_tarih ON yoklama (tarih);
    CREATE TABLE yoklama_yok (
        yoklama_id INTEGER NOT NULL REFERENCES yoklama(id) ON DELETE CASCADE,
        ogrenci_id INTEGER NOT NULL REFERENCES ogrenci(id),
        PRIMARY KEY (yoklama_id, ogrenci_id));
    CREATE INDEX yoklama_yok_ogrenci ON yoklama_yok (ogrenci_id);
    -- Kim neyi değiştirdi. Öğrenci kimliği içerdiği için 'kayit'e değil buraya yazılır, yoklamayla imha edilir.
    CREATE TABLE yoklama_iz (
        id INTEGER PRIMARY KEY,
        yoklama_id INTEGER NOT NULL REFERENCES yoklama(id) ON DELETE CASCADE,
        zaman INTEGER NOT NULL, kim TEXT NOT NULL,
        islem TEXT NOT NULL,                    -- 'olustur' | 'guncelle' | 'duzelt'
        eklenen TEXT NOT NULL DEFAULT '[]',     -- ogrenci_id JSON listesi
        cikarilan TEXT NOT NULL DEFAULT '[]',
        aciklama TEXT NOT NULL DEFAULT '');
    CREATE TABLE yoklama_belirtec (
        belirtec_ozet TEXT PRIMARY KEY,         -- guvenlik.ozet(belirtec)
        ogretmen_id INTEGER NOT NULL REFERENCES ogretmen(id) ON DELETE CASCADE,
        tahta_id INTEGER NOT NULL REFERENCES tahta(id) ON DELETE CASCADE,
        bitis INTEGER NOT NULL, olusturma INTEGER NOT NULL);
    CREATE TABLE eokul_islendi (
        tarih TEXT NOT NULL, sube TEXT NOT NULL,
        kullanici TEXT NOT NULL, zaman INTEGER NOT NULL,
        PRIMARY KEY (tarih, sube));
    CREATE TABLE ogrenci_aktarim (
        id INTEGER PRIMARY KEY, zaman INTEGER NOT NULL, kullanici TEXT NOT NULL,
        bicim TEXT NOT NULL,                    -- 'eokul_xls' | 'xlsx' | 'csv'
        sube_sayisi INTEGER NOT NULL, eklenen INTEGER NOT NULL, guncellenen INTEGER NOT NULL,
        pasif INTEGER NOT NULL, atlanan INTEGER NOT NULL);
    """,
    # 0.7.0 — tahta envanteri ve arıza bildirimi (yedekler için tablo YOK: kaynak yedek klasörüdür)
    """
    ALTER TABLE tahta ADD COLUMN envanter_json TEXT;
    ALTER TABLE tahta ADD COLUMN envanter_ozet TEXT NOT NULL DEFAULT '';
    ALTER TABLE tahta ADD COLUMN envanter_zamani INTEGER;
    ALTER TABLE tahta ADD COLUMN donanim_kimligi TEXT NOT NULL DEFAULT '';
    ALTER TABLE tahta ADD COLUMN demirbas_no TEXT NOT NULL DEFAULT '';
    ALTER TABLE tahta ADD COLUMN envanter_notu TEXT NOT NULL DEFAULT '';
    CREATE TABLE ariza (
        id INTEGER PRIMARY KEY,
        tahta_id INTEGER NOT NULL REFERENCES tahta(id),
        kaynak TEXT NOT NULL,                   -- 'tahta' | 'panel'
        yerel_id TEXT,                          -- tahtadan gelende tekrar önleme; panelde NULL
        kategori TEXT NOT NULL,
        aciklama TEXT NOT NULL DEFAULT '',      -- en çok 300 karakter
        bildiren TEXT NOT NULL,                 -- panel: kullanıcı adı; tahta: 'tahta'
        oturum_sinifi TEXT NOT NULL DEFAULT '', -- tahtadan gelende hesap sınıfı (kişi kimliği değil)
        durum TEXT NOT NULL DEFAULT 'acik',     -- acik | inceleniyor | cozuldu | iptal
        olusturma INTEGER NOT NULL,
        guncelleme INTEGER NOT NULL,
        cozum_notu TEXT NOT NULL DEFAULT '',
        UNIQUE (tahta_id, yerel_id));
    CREATE INDEX ariza_durum ON ariza (durum, tahta_id);
    CREATE TABLE ariza_hareket (
        id INTEGER PRIMARY KEY,
        ariza_id INTEGER NOT NULL REFERENCES ariza(id),
        zaman INTEGER NOT NULL,
        kullanici TEXT NOT NULL,                -- panel kullanıcı adı ya da 'tahta'
        eski_durum TEXT NOT NULL DEFAULT '',
        yeni_durum TEXT NOT NULL,
        not_metni TEXT NOT NULL DEFAULT '');
    CREATE INDEX ariza_hareket_ariza ON ariza_hareket (ariza_id);
    """,
    # 0.8.0 — 16.11.2026 kararları. K4: acil yayını bütün yönetici ve idareciler başlatır (sütun yalnız eski
    # sürüme dönüş için durur, okunmaz). K3: yoklamanın gün sayılı saklama ayarı kalkar; öğrenci verisi
    # içeren kayıtlar öğretim yılı bitiş tarihine kadar durur (`ayar.ogretim_yili_bitis`, saklama.py).
    # K6: boş ders uyarısı raporu tarih aralığıyla sorgulanır; uyarı oluştuğu andaki şubeyi saklar (rapor yıl
    # boyunca tutulur, sonradan değişen program eski uyarıyı başka şubeye yazmasın; eski satırda NULL).
    """
    UPDATE kullanici SET acil_yetki = 1;
    UPDATE ayar SET deger = json_remove(deger, '$.saklama_gun')
        WHERE anahtar = 'yoklama' AND json_valid(deger) AND json_type(deger) = 'object';
    CREATE INDEX bos_ders_uyari_tarih ON bos_ders_uyari (tarih);
    ALTER TABLE bos_ders_uyari ADD COLUMN sube TEXT;
    """,
    # 0.10.0 — zil düzenleyici: adlandırılmış çizelgeler, haftalık düzen, tarihe özel çizelgeler.
    # ders_saati bundan sonra türetilmiş tablodur (cizelge.haftalik_yaz); elle yazılmaz. Mevcut ders_saati
    # verisi açılışta bir kez çizelgelere taşınır (cizelge.ilk_tasima; bayrak `zil_tasima_bekliyor`).
    """
    CREATE TABLE zil_cizelgesi (
        id INTEGER PRIMARY KEY,
        ad TEXT NOT NULL UNIQUE COLLATE NOCASE,          -- 1–40 karakter
        kaynak TEXT NOT NULL DEFAULT 'elle',             -- 'elle' | 'okulzili' | 'tasima'
        olusturan TEXT NOT NULL, olusturma INTEGER NOT NULL,
        guncelleyen TEXT NOT NULL DEFAULT '', guncelleme INTEGER);
    CREATE TABLE zil_cizelge_ders (
        cizelge_id INTEGER NOT NULL REFERENCES zil_cizelgesi(id) ON DELETE CASCADE,
        devre TEXT NOT NULL,
        devre_adi TEXT NOT NULL,
        ders_no INTEGER NOT NULL CHECK (ders_no BETWEEN 1 AND 20),
        baslangic TEXT NOT NULL,
        bitis TEXT NOT NULL,
        PRIMARY KEY (cizelge_id, devre, ders_no));
    CREATE TABLE zil_haftalik (
        gun INTEGER PRIMARY KEY CHECK (gun BETWEEN 0 AND 6),
        cizelge_id INTEGER REFERENCES zil_cizelgesi(id));   -- satır yok ya da NULL = ders yok
    CREATE TABLE zil_tarihli (
        id INTEGER PRIMARY KEY,
        ad TEXT NOT NULL,                                -- 1–60 karakter, T.C. denetimi
        bas TEXT NOT NULL, bit TEXT NOT NULL,            -- ISO tarih, bit >= bas, en çok 366 gün
        gunler TEXT NOT NULL,                            -- '0,1,2,3,4' (virgüllü, sıralı)
        cizelge_id INTEGER REFERENCES zil_cizelgesi(id), -- NULL = ders yok
        olusturan TEXT NOT NULL, olusturma INTEGER NOT NULL);
    CREATE INDEX zil_tarihli_bit ON zil_tarihli (bit);
    INSERT INTO ayar (anahtar, deger)
        SELECT 'zil_tasima_bekliyor', 'true' WHERE EXISTS (SELECT 1 FROM ders_saati);
    """,
    # 0.10.0 — ders programı içe aktarma: hatırlanan eşlemeler ve geri alma için önceki programlar
    # (öğretmen, ders adı ve kişi verisi YOK; yalnız tahta, gün, devre, ders no ve şube).
    """
    CREATE TABLE program_eslesme (
        kaynak TEXT NOT NULL,                   -- 'asc' | 'tablo' (CSV/XLSX/yapay zekâ ortak)
        tur TEXT NOT NULL,                      -- 'derslik' | 'sinif' | 'saat' | 'sube'
        anahtar TEXT NOT NULL,                  -- katlanmış ad ya da 'period|starttime'
        tahta_id INTEGER REFERENCES tahta(id) ON DELETE CASCADE,  -- derslik/sube: NULL = atla
        deger TEXT NOT NULL DEFAULT '',         -- sinif: kanonik şube ('' = şubesiz); saat: 'devre|ders_no' ya da 'yok'
        guncelleme INTEGER NOT NULL,
        PRIMARY KEY (kaynak, tur, anahtar));
    CREATE TABLE program_surum (
        id INTEGER PRIMARY KEY,
        zaman INTEGER NOT NULL,
        kullanici TEXT NOT NULL,
        neden TEXT NOT NULL,                    -- 'aktarim' | 'geri_yukleme'
        bicim TEXT NOT NULL DEFAULT '',         -- 'asc' | 'csv' | 'xlsx' | 'xls' | 'yz' | ''
        satir_sayisi INTEGER NOT NULL,
        tahta_sayisi INTEGER NOT NULL,
        veri_json TEXT NOT NULL);               -- [[tahta_id, gun, devre, ders_no, sube], ...]
    """,
    # 0.11.0 — USB anahtar: yalnız gizli değerin özeti; yoklama belirteci idare oturumunu da taşır.
    # Belirteç tablosu yeniden kurulur (ogretmen_id NOT NULL kalkar; satırlar ≤ 15 dk yaşar, göçte düşer).
    """
    CREATE TABLE usb_anahtar (
        id INTEGER PRIMARY KEY,
        kimlik TEXT NOT NULL UNIQUE,            -- 'K7Q2M9XA'; gizli değil
        gizli_ozet TEXT NOT NULL,               -- sha256(gizli) onaltılık
        sahip_turu TEXT NOT NULL,               -- 'kullanici' | 'ogretmen'
        kullanici_id INTEGER REFERENCES kullanici(id) ON DELETE CASCADE,
        ogretmen_id INTEGER REFERENCES ogretmen(id) ON DELETE CASCADE,
        etiket TEXT NOT NULL DEFAULT '',        -- "Mavi bellek" gibi; kişi adı yazılmaz
        pin_ozet TEXT,                          -- yalnız kullanıcı anahtarında (guvenlik.parola_ozetle)
        hatali_sayi INTEGER NOT NULL DEFAULT 0, -- yalnız kullanıcı anahtarının PIN'i
        hatali_ilk INTEGER,
        durum TEXT NOT NULL DEFAULT 'etkin',    -- 'etkin' | 'kilitli' | 'iptal'
        olusturan TEXT NOT NULL,                -- panel kullanıcı adı
        olusturma INTEGER NOT NULL,
        iptal_eden TEXT, iptal_zamani INTEGER,
        son_kullanim INTEGER,                   -- yalnız SON başarılı tanıma/işlem (geçmiş tutulmaz)
        son_tahta_id INTEGER REFERENCES tahta(id) ON DELETE SET NULL,
        kopya_uyarisi INTEGER,                  -- son "iki tahtada" uyarısının zamanı
        CHECK ((sahip_turu = 'kullanici' AND kullanici_id IS NOT NULL AND ogretmen_id IS NULL)
            OR (sahip_turu = 'ogretmen' AND ogretmen_id IS NOT NULL AND kullanici_id IS NULL)));
    CREATE INDEX usb_anahtar_kullanici ON usb_anahtar (kullanici_id, durum);
    CREATE INDEX usb_anahtar_ogretmen ON usb_anahtar (ogretmen_id, durum);
    DROP TABLE yoklama_belirtec;
    CREATE TABLE yoklama_belirtec (
        belirtec_ozet TEXT PRIMARY KEY,         -- guvenlik.ozet(belirtec)
        ogretmen_id INTEGER REFERENCES ogretmen(id) ON DELETE CASCADE,
        kullanici_id INTEGER REFERENCES kullanici(id) ON DELETE CASCADE,
        anahtar_id INTEGER REFERENCES usb_anahtar(id) ON DELETE CASCADE,   -- NULL: kod + PIN ile açıldı
        tahta_id INTEGER NOT NULL REFERENCES tahta(id) ON DELETE CASCADE,
        bitis INTEGER NOT NULL, olusturma INTEGER NOT NULL,
        CHECK ((ogretmen_id IS NULL) <> (kullanici_id IS NULL)));
    """,
    # 0.13.0 — öğretmen programı (yoklama yetkisi kısıtlamaz); ham rapor/öğretmen etiketi saklanmaz.
    """
    CREATE TABLE ogretmen_program (
        id INTEGER PRIMARY KEY,
        sube TEXT NOT NULL,
        gun INTEGER NOT NULL CHECK (gun BETWEEN 0 AND 6),
        ders_no INTEGER NOT NULL CHECK (ders_no BETWEEN 1 AND 20),
        baslangic TEXT NOT NULL,
        bitis TEXT NOT NULL,
        ders_adi TEXT NOT NULL,
        ogretmen_id INTEGER REFERENCES ogretmen(id) ON DELETE SET NULL,
        guncelleme INTEGER NOT NULL,
        UNIQUE (sube, gun, ders_no, baslangic, ders_adi, ogretmen_id));
    CREATE INDEX ogretmen_program_gun ON ogretmen_program(gun, sube, ders_no);
    """,
    # 0.13.1 — 0.13.0 çok gruplu seçmeli hücrede ikinci öğretmenin adını ders adına karıştırıyordu
    # ("DERS1 KİŞİ2 - DERS2"). Bozuk değer her zaman " - " taşır; metnin neresinin ad olduğu bilinemediği
    # için kırpılmaz, tümü genel başlığa iner (aynı satır zaten varsa bozuk olan silinir).
    """
    UPDATE OR IGNORE ogretmen_program SET ders_adi = 'Seçmeli ders' WHERE ders_adi LIKE '% - %';
    DELETE FROM ogretmen_program WHERE ders_adi LIKE '% - %';
    """,
]
GOC_ONCESI_KALAN = 3
# Göç (ve göç öncesi kopya), yedek alma ve geri yükleme aynı anda çalışmaz (A6 K-B2).
KILIT = threading.Lock()


def yol():
    return ayar.veri_dizini() / "tahta-kontrol.db"


def baglan() -> sqlite3.Connection:
    baglanti = sqlite3.connect(yol(), timeout=15)
    baglanti.row_factory = sqlite3.Row
    baglanti.execute("PRAGMA foreign_keys = ON")
    baglanti.execute("PRAGMA journal_mode = WAL")
    baglanti.execute("PRAGMA synchronous = FULL")
    # Silinen kişisel veri (sınav listesi, A5 yoklama) dosyada eski sayfalarda kalmasın.
    baglanti.execute("PRAGMA secure_delete = ON")
    return baglanti


def wal_buda() -> None:
    """Kişisel veri silen işten sonra WAL dosyasını budar (silinen satırın kopyası diskte kalmasın).

    İşlem kapandıktan sonra ayrı bağlantıyla çağrılır; başarısızlık çağıranı düşürmez.
    """
    try:
        baglanti = baglan()
        try:
            baglanti.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            baglanti.close()
    except sqlite3.Error:
        pass


@contextmanager
def islem():
    baglanti = baglan()
    try:
        yield baglanti
        baglanti.commit()
    except BaseException:
        baglanti.rollback()
        raise
    finally:
        baglanti.close()


def goc_oncesi_kopya(baglanti: sqlite3.Connection, eski: int) -> Path:
    """Göçten önce veritabanının tutarlı bir kopyasını alır (SQLite yedek API'si).

    `veri_dizini/goc-oncesi/tahta-kontrol-v{eski}-{gg.aa.yyyy-SSDDss}.db`; en yeni
    GOC_ONCESI_KALAN kopya kalır. Kopya alınamazsa göç yapılmaz (RuntimeError).
    """
    dizin = ayar.veri_dizini() / "goc-oncesi"
    an = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y-%H%M%S")
    hedef = dizin / f"tahta-kontrol-v{eski}-{an}.db"
    try:
        dizin.mkdir(parents=True, exist_ok=True)
        sira = 1
        while hedef.exists():
            sira += 1
            hedef = dizin / f"tahta-kontrol-v{eski}-{an}-{sira}.db"
        kopya = sqlite3.connect(hedef)
        try:
            baglanti.backup(kopya)
        finally:
            kopya.close()
    except (OSError, sqlite3.Error) as hata:
        raise RuntimeError(f"Göç öncesi veritabanı kopyası alınamadı ({hata}); göç yapılmadı.") from hata
    eskiler = sorted(dizin.glob("tahta-kontrol-v*.db"), key=lambda y: y.stat().st_mtime_ns, reverse=True)
    for fazla in eskiler[GOC_ONCESI_KALAN:]:
        try:
            fazla.unlink()
        except OSError:
            pass
    return hedef


def hazirla() -> None:
    with KILIT:
        _hazirla()


def _hazirla() -> None:
    baglanti = baglan()
    try:
        surum = baglanti.execute("PRAGMA user_version").fetchone()[0]
        if 0 < surum < len(GOCLER):
            goc_oncesi_kopya(baglanti, surum)
        for sira in range(surum, len(GOCLER)):
            # Her göç tek işlemdir: yarıda kalırsa sürüm numarası da eski kalır.
            baglanti.executescript(f"BEGIN;\n{GOCLER[sira]}\nPRAGMA user_version = {sira + 1};\nCOMMIT;")
        # 0.10.0: eski ders_saati verisi çizelgelere bir kez taşınır (yarıda kalırsa sonraki açılışta yeniden).
        if baglanti.execute("SELECT 1 FROM ayar WHERE anahtar = 'zil_tasima_bekliyor'").fetchone():
            from . import cizelge  # içe aktarma döngüsü olmasın diye burada

            try:
                baglanti.execute("BEGIN")
                cizelge.ilk_tasima(baglanti)
                baglanti.commit()
            except BaseException:
                baglanti.rollback()
                raise
    except BaseException:
        if baglanti.in_transaction:
            baglanti.rollback()
        raise
    finally:
        baglanti.close()


def simdi() -> int:
    return int(time.time())


def ayar_al(b: sqlite3.Connection, anahtar: str, varsayilan=None):
    satir = b.execute("SELECT deger FROM ayar WHERE anahtar = ?", (anahtar,)).fetchone()
    return json.loads(satir["deger"]) if satir else varsayilan


def ayar_yaz(b: sqlite3.Connection, anahtar: str, deger) -> None:
    b.execute(
        "INSERT INTO ayar (anahtar, deger) VALUES (?, ?) ON CONFLICT(anahtar) DO UPDATE SET deger = excluded.deger",
        (anahtar, json.dumps(deger, ensure_ascii=False)),
    )


def kayit_dus(b: sqlite3.Connection, kullanici: str, islem_adi: str, ayrinti: str = "", ip: str = "") -> None:
    b.execute(
        "INSERT INTO kayit (zaman, kullanici, islem, ayrinti, ip) VALUES (?, ?, ?, ?, ?)",
        (simdi(), kullanici, islem_adi, ayrinti[:1000], ip),
    )
