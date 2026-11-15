"""SQLite veritabanı: şema, göçler ve küçük yardımcılar.

Zamanlar UTC saniye (epoch) olarak saklanır; ekranda Europe/Istanbul saatine çevrilir.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager

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
]


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


def hazirla() -> None:
    baglanti = baglan()
    try:
        surum = baglanti.execute("PRAGMA user_version").fetchone()[0]
        for sira in range(surum, len(GOCLER)):
            baglanti.executescript(GOCLER[sira])
            baglanti.execute(f"PRAGMA user_version = {sira + 1}")
        baglanti.commit()
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
