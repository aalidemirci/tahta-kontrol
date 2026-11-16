"""SQLite veritabanı: şema, göçler ve küçük yardımcılar.

Zamanlar UTC saniye (epoch) olarak saklanır; ekranda Europe/Istanbul saatine çevrilir.
"""

from __future__ import annotations

import json
import sqlite3
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
]
GOC_ONCESI_KALAN = 3


def yol():
    return ayar.veri_dizini() / "tahta-kontrol.db"


def baglan() -> sqlite3.Connection:
    baglanti = sqlite3.connect(yol(), timeout=15)
    baglanti.row_factory = sqlite3.Row
    baglanti.execute("PRAGMA foreign_keys = ON")
    baglanti.execute("PRAGMA journal_mode = WAL")
    baglanti.execute("PRAGMA synchronous = FULL")
    return baglanti


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
    baglanti = baglan()
    try:
        surum = baglanti.execute("PRAGMA user_version").fetchone()[0]
        if 0 < surum < len(GOCLER):
            goc_oncesi_kopya(baglanti, surum)
        for sira in range(surum, len(GOCLER)):
            # Her göç tek işlemdir: yarıda kalırsa sürüm numarası da eski kalır.
            baglanti.executescript(f"BEGIN;\n{GOCLER[sira]}\nPRAGMA user_version = {sira + 1};\nCOMMIT;")
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
