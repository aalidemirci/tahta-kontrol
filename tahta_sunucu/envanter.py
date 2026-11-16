"""Tahta envanteri (A6, sunucu yanı): ajanın gönderdiği donanım/yazılım özetini saklar ve gösterir.

Ajan envanteri `/ajan/bekle` gövdesinde (`envanter`) yalnız sunucu `envanter_iste` dediğinde
ya da `envanter` komutunun çıktısı olarak gönderir. Envanter CİHAZ verisidir (seri no, MAC,
model); kişi verisi (hesap adı, ev dizini, dosya adı) içermez. Sunucu yalnız aşağıdaki
anahtarları okur; bilinmeyen anahtarlar JSON'da durur, gösterilmez.
"""

from __future__ import annotations

import json
import re

from . import ariza, metin, vt

EN_BUYUK_BAYT = 64 * 1024
YETENEK = "envanter"
OZET_DESENI = re.compile(r"^[0-9a-f]{8,64}$")
YER_TUTUCULAR = {"to be filled by o.e.m.", "default string", "system serial number", "none", "0",
                 "not specified", "not applicable", "n/a", "unknown"}  # fmt: skip
CSV_SUTUNLARI = [
    "Tahta", "Derslik", "Demirbaş no", "Üretici", "Model", "Seri no", "Anakart seri no", "BIOS", "İşlemci",
    "Çekirdek", "Bellek (GB)", "Disk (GB)", "Disk türü", "Ekran", "Dokunmatik", "İşletim sistemi",
    "Çekirdek sürümü", "Ajan sürümü", "MAC", "IP", "Son görülme", "Envanter tarihi", "Açık arıza", "Not",
]  # fmt: skip
DEMIRBAS_EN_UZUN = 40
NOT_EN_UZUN = 300


class EnvanterHatasi(ValueError):
    pass


def seri_temizle(deger) -> str:
    """Yer tutucu seri numaralarını boş sayar (yalnız 0/boşluk/nokta içerenler dahil)."""
    s = " ".join(str(deger or "").split())[:80]
    if not s or s.lower() in YER_TUTUCULAR or not s.strip("0 .").strip():
        return ""
    return s


def donanim_kimligi(env: dict) -> str:
    return seri_temizle(env.get("urun_seri")) or seri_temizle(env.get("anakart_seri"))


def ozet_hesapla(env: dict) -> str:
    import hashlib

    return hashlib.sha256(json.dumps(env, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def kaydet(b, tahta, env, bildirilen_ozet: str = "", ip: str = "") -> bool:
    """Envanteri yazar; donanım kimliği dolu→farklı dolu değiştiyse işlem kaydı + uyarı listesi (True döner).

    Hata (sözlük değil, 64 KB'ı aşıyor): EnvanterHatasi. Ajanın bildirdiği özet geçerliyse o
    saklanır (ajan aynı özeti `durum.envanter_ozet` ile gönderir; karşılaştırma tutarlı kalsın).
    """
    if not isinstance(env, dict):
        raise EnvanterHatasi("Envanter biçimi geçersiz.")
    metni = json.dumps(env, ensure_ascii=False)
    if len(metni.encode("utf-8")) > EN_BUYUK_BAYT:
        raise EnvanterHatasi("Envanter çok büyük.")
    ozet = bildirilen_ozet if OZET_DESENI.match(str(bildirilen_ozet or "")) else ozet_hesapla(env)
    yeni_kimlik = donanim_kimligi(env)
    eski = b.execute("SELECT donanim_kimligi, ad FROM tahta WHERE id = ?", (tahta["id"],)).fetchone()
    eski_kimlik = eski["donanim_kimligi"] if eski else ""
    b.execute(
        "UPDATE tahta SET envanter_json = ?, envanter_ozet = ?, envanter_zamani = ?, donanim_kimligi = ? WHERE id = ?",
        (metni, ozet, vt.simdi(), yeni_kimlik, tahta["id"]),
    )
    if eski_kimlik and yeni_kimlik and eski_kimlik != yeni_kimlik:
        vt.kayit_dus(
            b, "sistem", "Tahtanın donanım kimliği değişti",
            f"{eski['ad']}: {eski_kimlik} → {yeni_kimlik}. Disk başka cihaza takılmış ya da tahta anahtarı kopyalanmış olabilir.",
            ip,
        )  # fmt: skip
        uyarilar = [int(t) for t in (vt.ayar_al(b, "donanim_uyarilari") or []) if str(t).isdigit()]
        if tahta["id"] not in uyarilar:
            vt.ayar_yaz(b, "donanim_uyarilari", (uyarilar + [tahta["id"]])[-200:])
        return True
    return False


def donanim_uyarilari(b) -> set[int]:
    return {int(t) for t in (vt.ayar_al(b, "donanim_uyarilari") or []) if str(t).isdigit()}


def donanim_uyarisi_kaldir(b, tahta_id: int) -> bool:
    uyarilar = [int(t) for t in (vt.ayar_al(b, "donanim_uyarilari") or []) if str(t).isdigit()]
    if tahta_id not in uyarilar:
        return False
    vt.ayar_yaz(b, "donanim_uyarilari", [t for t in uyarilar if t != tahta_id])
    return True


def envanter_iste(tahta, bildirilen_ozet) -> bool:
    """Sunucuda envanter yoksa ya da ajanın özeti sunucudakinden farklıysa True."""
    if not tahta["envanter_json"]:
        return True
    return str(bildirilen_ozet or "") != (tahta["envanter_ozet"] or "")


def _yazi(deger, uzunluk: int = 120) -> str:
    return " ".join(str(deger).split())[:uzunluk] if isinstance(deger, (str, int, float)) and not isinstance(deger, bool) else ""


def _sayi(deger) -> int | None:
    return int(deger) if isinstance(deger, (int, float)) and not isinstance(deger, bool) and deger >= 0 else None


def gorunum(env_json: str | None) -> dict | None:
    """Panel için düz alanlar (§6.3/§6.5). Envanter yoksa None."""
    if not env_json:
        return None
    try:
        env = json.loads(env_json)
    except ValueError:
        return None
    if not isinstance(env, dict):
        return None
    bellek_mb = _sayi(env.get("bellek_mb"))
    diskler = []
    for d in env.get("diskler") or []:
        if isinstance(d, dict):
            diskler.append({
                "ad": _yazi(d.get("ad"), 20), "model": _yazi(d.get("model"), 60), "boyut_gb": _sayi(d.get("boyut_gb")),
                "ssd": d.get("ssd") if isinstance(d.get("ssd"), bool) else None,
            })  # fmt: skip
    ag = [
        {"arayuz": _yazi(a.get("arayuz"), 20), "mac": _yazi(a.get("mac"), 17), "kablosuz": bool(a.get("kablosuz"))}
        for a in (env.get("ag") or [])
        if isinstance(a, dict)
    ]
    dokunmatik = [_yazi(x, 80) for x in (env.get("dokunmatik") or []) if _yazi(x, 80)]
    uretici, model = _yazi(env.get("uretici")), _yazi(env.get("model"))
    return {
        "uretici": uretici,
        "model": model,
        "model_surumu": _yazi(env.get("model_surumu"), 40),
        "uretici_model": " · ".join(p for p in (uretici, model) if p),
        "seri": seri_temizle(env.get("urun_seri")),
        "anakart": _yazi(env.get("anakart")),
        "anakart_seri": seri_temizle(env.get("anakart_seri")),
        "bios": _yazi(env.get("bios")),
        "islemci": _yazi(env.get("islemci")),
        "cekirdek_sayisi": _sayi(env.get("cekirdek_sayisi")),
        "bellek_mb": bellek_mb,
        "bellek_gb": f"{bellek_mb / 1024:.1f}".replace(".", ",") if bellek_mb else "",
        "diskler": diskler,
        "disk_metni": ", ".join(
            f"{d['boyut_gb']} GB{' SSD' if d['ssd'] else (' HDD' if d['ssd'] is False else '')}"
            for d in diskler if d["boyut_gb"] is not None
        ),  # fmt: skip
        "ekran": _yazi(env.get("ekran"), 20),
        "dokunmatik": dokunmatik,
        "ag": ag,
        "isletim_sistemi": _yazi(env.get("isletim_sistemi")),
        "cekirdek": _yazi(env.get("cekirdek"), 60),
        "etap_paketleri": [_yazi(x, 80) for x in (env.get("etap_paketleri") or [])[:30] if _yazi(x, 80)],
        "python": _yazi(env.get("python"), 20),
        "ajan_surumu": _yazi(env.get("ajan_surumu"), 20),
    }


def tablo(b) -> list[dict]:
    """Envanter sayfası satırları (kaldırılmış tahtalar hariç), derslik/ad sırasıyla."""
    from . import acil

    suren = ariza.suren_sayilari(b)
    satirlar = []
    for t in b.execute(
        "SELECT * FROM tahta WHERE durum != 'iptal' ORDER BY derslik COLLATE NOCASE, ad COLLATE NOCASE"
    ):
        g = gorunum(t["envanter_json"])
        yetenekli = YETENEK in acil.yetenekler(t)
        satirlar.append({
            "id": t["id"], "ad": t["ad"], "derslik": t["derslik"], "demirbas_no": t["demirbas_no"],
            "envanter_notu": t["envanter_notu"], "durum": t["durum"], "ip": t["ip"], "mac": t["mac"],
            "son_gorulme": t["son_gorulme"], "surum": t["surum"], "envanter_zamani": t["envanter_zamani"],
            "env": g, "acik_ariza": suren.get(t["id"], 0),
            # Envanter yoksa satır sonunda: ajan yeteneği bildirmiyorsa "Ajan güncellenmeli", bildiriyorsa "Bekleniyor".
            "eksik_neden": "" if g else ("Bekleniyor" if yetenekli else "Ajan güncellenmeli"),
            "seri_tekrar": False,
        })  # fmt: skip
    # K-E3: aynı seri numarası iki tahtada → kopyalanmış disk belirtisi.
    sayac: dict[str, int] = {}
    for s in satirlar:
        if s["env"] and s["env"]["seri"]:
            sayac[s["env"]["seri"]] = sayac.get(s["env"]["seri"], 0) + 1
    for s in satirlar:
        if s["env"] and s["env"]["seri"] and sayac[s["env"]["seri"]] > 1:
            s["seri_tekrar"] = True
    return satirlar


def csv_uret(b, tarih_yaz) -> bytes:
    """§7.2 sütunlarıyla CSV (metin.csv_yaz: UTF-8 BOM, `;`, CRLF, formül kaçışı)."""
    satirlar = []
    for s in tablo(b):
        g = s["env"] or {}
        diskler = g.get("diskler") or []
        satirlar.append([
            s["ad"], s["derslik"], s["demirbas_no"], g.get("uretici", ""), g.get("model", ""), g.get("seri", ""),
            g.get("anakart_seri", ""), g.get("bios", ""), g.get("islemci", ""),
            g.get("cekirdek_sayisi") if g.get("cekirdek_sayisi") is not None else "",
            g.get("bellek_gb", ""),
            " + ".join(str(d["boyut_gb"]) for d in diskler if d["boyut_gb"] is not None),
            " + ".join("SSD" if d["ssd"] else ("HDD" if d["ssd"] is False else "?") for d in diskler),
            g.get("ekran", ""), ", ".join(g.get("dokunmatik") or []), g.get("isletim_sistemi", ""),
            g.get("cekirdek", ""), g.get("ajan_surumu", "") or s["surum"],
            ", ".join(a["mac"] for a in (g.get("ag") or []) if a["mac"]) or s["mac"], s["ip"],
            tarih_yaz(s["son_gorulme"]) if s["son_gorulme"] else "",
            tarih_yaz(s["envanter_zamani"]) if s["envanter_zamani"] else "",
            s["acik_ariza"], s["envanter_notu"],
        ])  # fmt: skip
    return metin.csv_yaz(CSV_SUTUNLARI, satirlar)
