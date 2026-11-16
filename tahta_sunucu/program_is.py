"""Ders programının veritabanına dokunan işleri: zamanlayıcı, istisnalar, askıya alma açması,
pano/`/api/durum` özetleri.

Zamanlayıcı (`ProgramZamanlayici.calistir`) sözlük §2.3 listesinde 4. iştir (20 sn'de bir).
Komut yazan işlevler uyandırma yapmaz; uyandırılacak tahta kimliklerini döndürür.

Program kilidi yalnız `durum.yetenekler` içinde `program_kilidi` bildiren tahtaya verilir:
eski ajan `kilitle`'nin verisini yok sayıp süresiz kilitler ve sonraki `kilit_ac` idarenin
kilidini de açar. Komut ömrü 120 sn'dir (geç açılan tahta eskimiş kilitle karşılaşmasın);
kilidin süresi (`sure_sn`) komut tahtaya inerken sunucu saatiyle hesaplanır.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

from . import acil, ayar, program, saklama, vt
from .komut import komut_ekle

gunluk = logging.getLogger("tahta-sunucu")
ISTANBUL = program.ISTANBUL
# Ajanın kendi süresiyle açmasının sunucuya yansıması için tanınan pay (uzun bekleme turu 25 sn).
ACMA_YEDEGI_PAYI_SN = 30


def durum_oku(tahta) -> dict:
    try:
        durum = json.loads(tahta["durum_json"] or "{}")
    except (ValueError, TypeError):
        return {}
    return durum if isinstance(durum, dict) else {}


def cevrimici(tahta, an: int) -> bool:
    return bool(tahta["son_gorulme"]) and an - tahta["son_gorulme"] < ayar.CEVRIMICI_ESIK_SN


def yetenekli(tahta) -> bool:
    return program.PROGRAM_YETENEGI in acil.yetenekler(tahta)


def program_kilitli(tahta) -> bool:
    durum = durum_oku(tahta)
    return bool(durum.get("kilitli")) and durum.get("kilit_kaynak") == "program"


# ---- istisnalar ---------------------------------------------------------------------------
def istisna_kapsami(satir) -> list[int] | None:
    """None = bütün tahtalar; yoksa tahta kimlikleri."""
    if not satir["tahta_ids"]:
        return None
    try:
        return [int(i) for i in json.loads(satir["tahta_ids"]) if isinstance(i, int)]
    except (ValueError, TypeError):
        return []


def etkin_istisnalar(b, an: int) -> list:
    return b.execute(
        "SELECT * FROM program_istisna WHERE iptal IS NULL AND bas <= ? AND bit > ? ORDER BY bit", (an, an)
    ).fetchall()


def istisnada(istisnalar, tahta_id: int) -> bool:
    for s in istisnalar:
        kapsam = istisna_kapsami(s)
        if kapsam is None or tahta_id in kapsam:
            return True
    return False


def istisna_durumu(satir, an: int) -> str:
    if satir["iptal"] is not None:
        return "iptal"
    if satir["bit"] <= an:
        return "bitti"
    if satir["bas"] > an:
        return "ileride"
    return "etkin"


ISTISNA_DURUMU = {"etkin": "Etkin", "ileride": "İleride", "bitti": "Bitti", "iptal": "İptal edildi"}


def istisna_ekle(b, *, bas: int, bit: int, tahta_ids: list[int] | None, neden: str, olusturan: str) -> int:
    return b.execute(
        "INSERT INTO program_istisna (bas, bit, tahta_ids, neden, olusturan, olusturma) VALUES (?, ?, ?, ?, ?, ?)",
        (bas, bit, json.dumps(sorted(set(tahta_ids))) if tahta_ids else "", neden, olusturan, vt.simdi()),
    ).lastrowid


def onizleme_temizle(b, an: int) -> bool:
    """Süresi geçmiş içe aktarma önizlemesini (`program_onizleme`, 30 dk ömürlü) siler.

    Önizleme CSV'den alınmış ham hücreler içerebilir; ömür sınırı yalnız ekranda değil,
    veritabanında da uygulanır. Silindiyse True."""
    kayit = vt.ayar_al(b, "program_onizleme")
    if kayit is None:
        return False
    if isinstance(kayit, dict) and int(kayit.get("bitis") or 0) > an:
        return False
    vt.ayar_yaz(b, "program_onizleme", None)
    return True


# ---- askıya alma açması (§5.6) ----------------------------------------------------------------
def askiya_alma_acmasi(b, idler=None, olusturan: str = "sistem", an: int | None = None) -> list[int]:
    """Etkilenen tahtalarda bekleyen program kilidi komutlarını iptal eder; program kaynaklı kilitli
    (ve yetenekli) olanlara `kilit_ac {"kaynak":"program"}` verir. Uyandırılacak kimlikleri döndürür.

    idler None ise bütün onaylı tahtalar.
    """
    an = vt.simdi() if an is None else an
    tahtalar = b.execute("SELECT * FROM tahta WHERE durum = 'onayli'").fetchall()
    if idler is not None:
        kume = {int(i) for i in idler}
        tahtalar = [t for t in tahtalar if t["id"] in kume]
    uyandir = []
    for t in tahtalar:
        iptal = b.execute(
            "UPDATE komut SET durum = 'iptal', tamamlanma = ?, sonuc = 'Program kilidi askıya alındı.' "
            "WHERE tahta_id = ? AND tur = 'kilitle' AND durum = 'bekliyor' AND json_extract(veri_json, '$.kaynak') = 'program'",
            (an, t["id"]),
        ).rowcount
        if program_kilitli(t) and yetenekli(t):
            komut_ekle(b, t["id"], "kilit_ac", {"kaynak": "program"}, olusturan, program.KILIT_KOMUT_OMRU_SN, simdi=an)
            uyandir.append(t["id"])
        elif iptal:
            uyandir.append(t["id"])
    return uyandir


# ---- tahta bazında hesaplar ----------------------------------------------------------------------
def tahta_dersleri(b, program_gunu: int) -> tuple[dict[int, dict[tuple[str, int], str]], set[int]]:
    """(o günün dersli saatleri: tahta → {(devre, no): şube}, programı olan tahtalar)."""
    gunluk_: dict[int, dict[tuple[str, int], str]] = {}
    for s in b.execute("SELECT tahta_id, devre, ders_no, sube FROM tahta_ders WHERE gun = ?", (program_gunu,)):
        gunluk_.setdefault(s["tahta_id"], {})[(s["devre"], s["ders_no"])] = s["sube"]
    programli = programli_tahtalar(b)
    return gunluk_, programli


def programli_tahtalar(b) -> set[int]:
    """Geçerli bir ders saatine karşılık gelen en az bir satırı olan tahtalar (K6: yetim satırlar
    yok sayılır; yalnız yetim satırı kalan tahta programsızdır, bütün gün kilitlenmez)."""
    return {
        s["tahta_id"]
        for s in b.execute(
            "SELECT DISTINCT d.tahta_id FROM tahta_ders d JOIN ders_saati s "
            "ON s.gun = d.gun AND s.devre = d.devre AND s.ders_no = d.ders_no"
        )
    }


def dersli_dersler(plan: dict, tahta_id: int, gunluk_: dict, programli: set[int], bos_saatte_kilitle: bool) -> list:
    """Tahtanın derste sayıldığı dersler: programı varsa onunkiler, yoksa günün bütün dersleri."""
    if tahta_id not in programli or not bos_saatte_kilitle:
        return list(plan["dersler"])
    satirlar = gunluk_.get(tahta_id, {})
    # Günün çizelgesi derslik programıyla aynı devreleri kullanmıyorsa (ör. ikili düzende "Tek devre" ile
    # yapılmış tarihe özel çizelge) program o güne uygulanamaz: tahta programsız sayılır, açık kalır
    # (ders sürerken bütün gün kilitlenmesin; kural 3'ün ruhu).
    plan_devreler = {d[0] for d in plan["dersler"]}
    gun_devreler = {devre for satir in gunluk_.values() for devre, _no in satir}
    if plan_devreler and gun_devreler and not (plan_devreler & gun_devreler):
        return list(plan["dersler"])
    if satirlar and not (plan_devreler & {devre for devre, _no in satirlar}):
        return list(plan["dersler"])
    return [d for d in plan["dersler"] if (d[0], d[2]) in satirlar]


def devre_uyusmazligi(b, cizelge_devreleri: dict[str, str], gunler) -> str | None:
    """Tarihe özel çizelgenin devreleri, seçilen günlerdeki derslik programının devreleriyle hiç kesişmiyorsa
    uyarı metni; kesişiyorsa ya da biri boşsa None. (O gün `dersli_dersler` programı uygulamaz.)"""
    gunler = list(gunler)
    if not cizelge_devreleri or not gunler:
        return None
    soru = ",".join("?" * len(gunler))
    prog = {s["devre"] for s in b.execute(f"SELECT DISTINCT devre FROM tahta_ders WHERE gun IN ({soru})", gunler)}
    if not prog or set(cizelge_devreleri) & prog:
        return None
    c_adlar = ", ".join(sorted(cizelge_devreleri.values()))
    p_adlar = ", ".join(sorted(program.devre_adi_varsayilan(d) for d in prog))
    return (
        f"Uyarı: bu çizelgede {c_adlar} devresi var; derslik programları {p_adlar} devresinde. "
        "Bu günlerde derslik programı uygulanmaz: tahtalar boş saatte kilitlenmez, yalnız teneffüslerde kilitlenir."
    )


def _ts(an: datetime) -> int:
    return int(an.timestamp())


def sinav_penceresinde(plan: dict, an_dt: datetime) -> bool:
    return bool(plan["tum_gun_sinav"]) or any(b_ <= an_dt <= s_ for b_, s_ in plan["sinav"])


def bos_nedeni(tahta, durum: dict, cevrimici_: bool) -> str | None:
    """Boş ders ölçütü (çekirdek: kapali, kilitli, oturumsuz). Dolu ise None.

    "kilitli" yalnız program kaynaklı kilittir: idarenin bilerek kilitlediği (ya da kaynağını
    bildirmeyen eski ajandaki) kilit öğretmene yazılmaz.
    """
    if not cevrimici_:
        return "kapali"
    if durum.get("kilitli") and durum.get("kilit_kaynak") == "program":
        return "kilitli"
    oturum = (durum.get("oturum") or {}).get("sinif", "yok") if isinstance(durum.get("oturum"), dict) else "yok"
    if oturum == "yok" or not acil.ekran_var(durum):
        return "oturumsuz"
    return None


# ---- zamanlayıcı -------------------------------------------------------------------------------
class ProgramZamanlayici:
    """§5.5: program kilidi, açma yedeği, boş ders uyarısı ve günlük bakım.

    `bos_baslangic` bellekte durur: sunucu yeniden başlarsa o ders için uyarı geç ya da hiç
    üretilmez (yanlış uyarı yerine eksik uyarı). `askida_kancalari`: sonraki aşamaların
    (A4 sınav penceresi) eklediği `kanca(b, tahta_id, an_epoch) -> bool` işlevleri; True dönen
    tahtaya program kilidi verilmez ve boş ders uyarısı üretilmez.
    """

    def __init__(self):
        self.bos_baslangic: dict[int, int] = {}
        self.askida_kancalari: list = []
        # A4: True dönen tahtaya YENİ program kilidi verilmez (sınav penceresinden önceki 10 dk);
        # açma yedeği ve boş ders uyarısı bundan etkilenmez.
        self.kilit_engel_kancalari: list = []
        self.wal_budanacak = False

    def bugun_degisti(self) -> None:
        """Bugünün ders saatleri değişti (zil düzenleyici §6.3): eski saate göre başlamış boş ders süreleri
        yeni derse sayılmasın."""
        self.bos_baslangic.clear()

    def calistir(self, b, simdi: datetime) -> list[int]:
        an = _ts(simdi)
        # Uyarı silindiyse çağıran, işlem bittikten sonra WAL'ı budar (bos_ders_imha_sonrasi).
        self.wal_budanacak = self.bakim(b, simdi)
        onizleme_temizle(b, an)
        saatler = program.ders_saatleri_oku(b)
        # Haftalık düzen boş olsa da tarihe özel çizelge o günün planını verebilir (tek giriş noktası gun_plani).
        plan = program.gun_plani(b, simdi.date(), saatler)
        if not saatler and not plan["dersler"]:
            self.bos_baslangic.clear()
            return []
        tarih = simdi.date().isoformat()
        kural = program.ayar_kilit(b)
        bos = program.ayar_bos_ders(b)
        gecikme = max(0, min(10, int(kural.get("gecikme_dk", 2)))) * 60
        esik = max(5, min(30, int(bos.get("esik_dk", 10)))) * 60
        acil_suruyor = acil.aktif(b, an) is not None
        istisnalar = etkin_istisnalar(b, an)
        sinavda = sinav_penceresinde(plan, simdi)
        gunluk_, programli = tahta_dersleri(b, plan["program_gunu"])
        kilitlenen: dict[str, list[int]] = {}
        acilan: list[int] = []
        uyandir: list[int] = []
        tahtalar = b.execute("SELECT * FROM tahta WHERE durum = 'onayli'").fetchall()
        for t in tahtalar:
            durum = durum_oku(t)
            acik = cevrimici(t, an)
            askida = istisnada(istisnalar, t["id"]) or sinavda or any(k(b, t["id"], an) for k in self.askida_kancalari)
            # 3–4: program kilidi
            dersli = dersli_dersler(plan, t["id"], gunluk_, programli, bool(kural.get("bos_saatte_kilitle", True)))
            araliklar = program.kilit_araliklari(plan, [(_ts(d[3]), _ts(d[4])) for d in dersli]) if plan["dersler"] else []
            simdiki = next((a for a in araliklar if a["bas"] <= an < a["bit"]), None)
            uygun = bool(kural.get("etkin")) and yetenekli(t) and not askida and not t["program_muaf"]
            kilit_engeli = uygun and any(k(b, t["id"], an) for k in self.kilit_engel_kancalari)
            if uygun and acik and not acil_suruyor and not kilit_engeli and simdiki and an >= simdiki["bas"] + gecikme \
                    and simdiki["bit"] - an >= program.EN_KISA_KILIT_SN:  # fmt: skip
                bas_s = datetime.fromtimestamp(simdiki["bas"], ISTANBUL).strftime("%H:%M")
                bit_s = datetime.fromtimestamp(simdiki["bit"], ISTANBUL).strftime("%H:%M")
                if self._isaret_yaz(b, t["id"], f"{tarih}|kilit|{bas_s}", an):
                    idare_kilidi = bool(durum.get("kilitli")) and durum.get("kilit_kaynak") != "program"
                    if not idare_kilidi:
                        veri = {"kaynak": "program", "bitis_sunucu": simdiki["bit"], "neden": simdiki["neden"], "acilis": bit_s}
                        komut_ekle(b, t["id"], "kilitle", veri, "sistem", program.KILIT_KOMUT_OMRU_SN, simdi=an)
                        kilitlenen.setdefault(f"{simdiki['neden']} {bas_s}–{bit_s}", []).append(t["id"])
                        uyandir.append(t["id"])
            # 5: açma yedeği (asıl açma ajandaki süredir; bu, saat kayması ve istisna içindir)
            if acik and program_kilitli(t) and yetenekli(t) and (not uygun or simdiki is None) \
                    and (not uygun or not self._ajan_kendisi_acacak(t, durum, an)):  # fmt: skip
                kova = simdi.replace(minute=simdi.minute - simdi.minute % 5).strftime("%H:%M")
                if self._isaret_yaz(b, t["id"], f"{tarih}|ac|{kova}", an):
                    komut_ekle(b, t["id"], "kilit_ac", {"kaynak": "program"}, "sistem", program.KILIT_KOMUT_OMRU_SN, simdi=an)
                    acilan.append(t["id"])
                    uyandir.append(t["id"])
            # 7: boş ders uyarısı (yalnız programı olan tahtada; programsızda yanlış alarm yağar)
            if t["id"] not in programli:
                self.bos_baslangic.pop(t["id"], None)
                continue
            neden = bos_nedeni(t, durum, acik)
            if neden:
                self.bos_baslangic.setdefault(t["id"], an)
            else:
                self.bos_baslangic.pop(t["id"], None)
            satirlar = gunluk_.get(t["id"], {})
            ders = next((d for d in plan["dersler"] if d[3] <= simdi < d[4] and (d[0], d[2]) in satirlar), None)
            if not ders:
                continue
            if not neden:
                b.execute(
                    "UPDATE bos_ders_uyari SET cozulme = ? WHERE tahta_id = ? AND tarih = ? AND devre = ? AND ders_no = ? "
                    "AND cozulme IS NULL",
                    (an, t["id"], tarih, ders[0], ders[2]),
                )
                continue
            ders_bas = _ts(ders[3])
            if bos.get("etkin") and not askida and an - ders_bas >= esik \
                    and self.bos_baslangic[t["id"]] <= ders_bas + program.BOS_DERS_SUREKLILIK_SN:  # fmt: skip
                b.execute(
                    "INSERT OR IGNORE INTO bos_ders_uyari (tahta_id, tarih, devre, ders_no, ders_bas, neden, olusturma, sube) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (t["id"], tarih, ders[0], ders[2], ders_bas, neden, an, satirlar.get((ders[0], ders[2])) or ""),
                )
        # 9: işlem kaydı — tek tur, tek satır
        parcalar = [f"{len(idler)} tahta · {ad}" for ad, idler in sorted(kilitlenen.items())]
        if acilan:
            parcalar.append(f"açma: {len(acilan)} tahta")
        if parcalar:
            vt.kayit_dus(b, "sistem", "Program kilidi", "; ".join(parcalar))
        return sorted(set(uyandir))

    @staticmethod
    def _ajan_kendisi_acacak(tahta, durum: dict, an: int) -> bool:
        """Aralık doğal olarak bittiğinde: ajanın kendi süresiyle açacağı an (son görülme + kalan)
        henüz geçmediyse ya da üzerinden `ACMA_YEDEGI_PAYI_SN` geçmediyse True. Bayat durum yüzünden
        gereksiz `kilit_ac` ve işlem kaydı gürültüsü olmasın; yedek yalnız ajan gecikirse devreye girer.
        İstisna, kural kapanması ve muafiyet açması bu denetime takılmaz (çağıran `uygun` ile ayırır)."""
        kalan = durum.get("kilit_kalan")
        if not isinstance(kalan, (int, float)) or not tahta["son_gorulme"]:
            return False
        return an < int(tahta["son_gorulme"] + kalan) + ACMA_YEDEGI_PAYI_SN

    @staticmethod
    def _isaret_yaz(b, tahta_id: int, anahtar: str, an: int) -> bool:
        """İşaret yoksa yazar ve True döner ("her aralıkta bir kez")."""
        return (
            b.execute(
                "INSERT OR IGNORE INTO program_isaret (tahta_id, anahtar, zaman) VALUES (?, ?, ?)", (tahta_id, anahtar, an)
            ).rowcount
            == 1
        )

    @staticmethod
    def bakim(b, simdi: datetime) -> bool:
        """Boş ders uyarılarını öğretim yılı bitiş tarihi geçince (o tarihe kadar oluşanları) siler (K3,
        `saklama.py`; her tur, yalnız silinecek varsa yazar); günde bir kez (03:00 sonrası ilk tur) eski
        işaret ve istisnaları siler. Uyarı silindiyse True (çağıran WAL'ı budar)."""
        silinen = 0
        sinir = saklama.imha_siniri(b, simdi.date())
        if sinir and b.execute("SELECT 1 FROM bos_ders_uyari WHERE tarih <= ? LIMIT 1", (sinir.isoformat(),)).fetchone():
            b.execute("PRAGMA secure_delete = ON")  # uyarılar personel verisi gibi korunur (§8.1)
            silinen = b.execute("DELETE FROM bos_ders_uyari WHERE tarih <= ?", (sinir.isoformat(),)).rowcount
            vt.kayit_dus(b, "sistem", "Boş ders uyarısı imhası",
                         f"{silinen} uyarı (öğretim yılı bitişi {saklama.tarih_metni(sinir)})")  # fmt: skip
        if simdi.hour < 3:
            return bool(silinen)
        son = vt.ayar_al(b, "program_bakim_son_tur")
        if isinstance(son, (int, float)) and datetime.fromtimestamp(son, ISTANBUL).date() >= simdi.date():
            return bool(silinen)
        an = _ts(simdi)
        vt.ayar_yaz(b, "program_bakim_son_tur", an)
        b.execute("DELETE FROM program_isaret WHERE zaman < ?", (an - program.ISARET_SAKLAMA_GUN * 86400,))
        b.execute(
            "DELETE FROM program_istisna WHERE COALESCE(iptal, bit) < ?", (an - program.ISTISNA_SAKLAMA_GUN * 86400,)
        )
        # 0.10.0: geçmişte biten tarihe özel çizelgeler istisnayla aynı süre sonra silinir.
        b.execute(
            "DELETE FROM zil_tarihli WHERE bit < ?",
            ((simdi.date() - timedelta(days=program.ISTISNA_SAKLAMA_GUN)).isoformat(),),
        )
        return bool(silinen)


def bos_ders_imha_sonrasi() -> None:
    """Uyarı silindikten sonra WAL dosyası budanır (silinen satır kopyası diskte kalmasın)."""
    try:
        baglanti = vt.baglan()
        try:
            baglanti.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            baglanti.close()
    except Exception:  # bakım başarısızlığı zamanlayıcıyı düşürmez
        gunluk.exception("WAL budanamadı")


# ---- özetler (pano şeridi, /api/durum, program sayfası) -----------------------------------------
def tarih_metni(gun: date) -> str:
    return f"{program.GUN_ADLARI[gun.weekday()]}, {gun:%d.%m.%Y}"


def program_ozeti(b, simdi: datetime) -> dict:
    """/api/durum üst düzey `program` alanı ve Program sayfası şeridi.

    {"bugun", "simdi", "simdi_tur", "ders_saati_var", "kilit": "acik"|"kapali"|"durduruldu",
     "askida": bool, "durduruldu_bitis": "11:45"|"17.11.2026 23:59"|None, "uyari_sayisi": n,
     "bos_ders_etkin": bool, "sunucu_saat": "SS:DD", "kaynak": metin}
    """
    an = _ts(simdi)
    saatler = program.ders_saatleri_oku(b)
    kural = program.ayar_kilit(b)
    bos = program.ayar_bos_ders(b)
    genel = [s for s in etkin_istisnalar(b, an) if istisna_kapsami(s) is None]
    durduruldu_bitis = None
    if genel:
        son = datetime.fromtimestamp(max(s["bit"] for s in genel), ISTANBUL)
        durduruldu_bitis = son.strftime("%H:%M") if son.date() == simdi.date() else son.strftime("%d.%m.%Y %H:%M")
    plan = program.gun_plani(b, simdi.date(), saatler)
    if saatler or plan["dersler"]:
        durum = program.simdiki_durum(plan, simdi)
        simdi_metni, simdi_tur, kaynak = durum["metin"], durum["tur"], plan["kaynak"]
    else:
        simdi_metni, simdi_tur, kaynak = "Ders saatleri tanımlı değil", "yok", ""
    uyari = b.execute(
        "SELECT COUNT(*) FROM bos_ders_uyari WHERE tarih = ? AND goruldu_zaman IS NULL", (simdi.date().isoformat(),)
    ).fetchone()[0]
    return {
        "bugun": tarih_metni(simdi.date()),
        "simdi": simdi_metni,
        "simdi_tur": simdi_tur,
        "ders_saati_var": bool(saatler or plan["dersler"]),
        "kilit": ("durduruldu" if genel else "acik") if kural.get("etkin") else "kapali",
        "askida": bool(genel),
        "durduruldu_bitis": durduruldu_bitis,
        "uyari_sayisi": uyari,
        "bos_ders_etkin": bool(bos.get("etkin")),
        "sunucu_saat": simdi.strftime("%H:%M"),
        "kaynak": kaynak,
    }


def bos_ders_metinleri(b, simdi: datetime) -> dict[int, str]:
    """Şu anki dersinde çözülmemiş boş ders uyarısı olan tahtalar: {tahta_id: "3. ders (kapalı)"}."""
    plan = program.gun_plani(b, simdi.date())
    simdiki = {(d[0], d[2]) for d in plan["dersler"] if d[3] <= simdi < d[4]}
    sonuc = {}
    for s in b.execute(
        "SELECT * FROM bos_ders_uyari WHERE tarih = ? AND cozulme IS NULL", (simdi.date().isoformat(),)
    ):
        if (s["devre"], s["ders_no"]) in simdiki:
            sonuc[s["tahta_id"]] = f"{s['ders_no']}. ders ({program.BOS_NEDENLERI.get(s['neden'], s['neden']).lower()})"
    return sonuc


RAPOR_EN_UZUN_GUN = 400


def bos_ders_raporu(
    b, bas: date, bit: date, tahta_id: int | None = None, ders_no: int | None = None, devre: str | None = None
) -> dict:
    """Boş ders uyarısı geçmişi ve raporu (K6). KİŞİ ADI İÇERMEZ: öğretmen tutulmaz; "görüldü" yalnız saattir.

    Döndürür: {"satirlar": [{id, tarih, tarih_metni, saat, tahta_id, tahta, derslik, ders, ders_no, durum, neden,
    sonuc, goruldu, goruldu_metni}], "toplam", "nedenler": [(ad, sayı)], "tahtalar": [{tahta_id, tahta, derslik, sayi,
    kapali, kilitli, oturumsuz, cozulen}], "dersler": [(ders metni, sayı)], "gun_sayisi"}.
    Satırlar tarih ve saat sırasıyla; ikili eğitimde ders numarası devre adıyla yazılır ("Sabah · 3. ders").
    `devre` verilirse ders süzgeci yalnız o devrenin dersidir (ikili eğitimde sabah ve öğlenin 3. dersi karışmaz).
    Şube, uyarının oluştuğu anda saklanan değerdir; 0.8.0 öncesi satırda (NULL) o günün programından bulunur ve
    "(güncel programa göre)" notu düşülür.
    """
    kosul, arg = ["u.tarih BETWEEN ? AND ?"], [bas.isoformat(), bit.isoformat()]
    if tahta_id:
        kosul.append("u.tahta_id = ?")
        arg.append(tahta_id)
    if ders_no:
        kosul.append("u.ders_no = ?")
        arg.append(ders_no)
    if devre:
        kosul.append("u.devre = ?")
        arg.append(devre)
    satirlar = b.execute(
        "SELECT u.*, t.ad AS tahta_ad, t.derslik AS derslik, "
        "(SELECT devre_adi FROM ders_saati s WHERE s.devre = u.devre LIMIT 1) AS devre_adi "
        f"FROM bos_ders_uyari u JOIN tahta t ON t.id = u.tahta_id WHERE {' AND '.join(kosul)} "
        "ORDER BY u.tarih, u.ders_bas, t.ad",
        arg,
    ).fetchall()
    cok_devre = b.execute("SELECT COUNT(DISTINCT devre) FROM ders_saati").fetchone()[0] > 1
    subeler: dict[tuple, str] | None = None
    program_gunleri: dict[str, int] = {}
    liste, nedenler, tahtalar, dersler = [], {}, {}, {}
    for s in satirlar:
        gun = date.fromisoformat(s["tarih"])
        ders_adi = f"{s['ders_no']}. ders"
        if cok_devre and s["devre_adi"]:
            ders_adi = f"{s['devre_adi']} · {ders_adi}"
        sube = s["sube"] or ""
        if s["sube"] is None:  # 0.8.0 öncesi uyarı: şube saklanmamış, bugünkü programdan bulunur
            if subeler is None:
                subeler = {
                    (r["tahta_id"], r["gun"], r["devre"], r["ders_no"]): r["sube"]
                    for r in b.execute("SELECT tahta_id, gun, devre, ders_no, sube FROM tahta_ders WHERE sube != ''")
                }
            if s["tarih"] not in program_gunleri:
                program_gunleri[s["tarih"]] = program.gun_plani(b, gun)["program_gunu"]
            sube = subeler.get((s["tahta_id"], program_gunleri[s["tarih"]], s["devre"], s["ders_no"]), "")
            if sube:
                sube = f"{sube} (güncel programa göre)"
        durum_ = program.BOS_NEDENLERI.get(s["neden"], s["neden"])
        liste.append({
            "id": s["id"],
            "tarih": s["tarih"],
            "tarih_metni": f"{gun:%d.%m.%Y}",
            "saat": datetime.fromtimestamp(s["ders_bas"], ISTANBUL).strftime("%H:%M"),
            "tahta_id": s["tahta_id"],
            "tahta": s["tahta_ad"],
            "derslik": s["derslik"],
            "ders": f"{ders_adi} · {sube}" if sube else ders_adi,
            "ders_no": s["ders_no"],
            "durum": durum_,
            "neden": s["neden"],
            "sonuc": (
                f"{program.saat_eki(datetime.fromtimestamp(s['cozulme'], ISTANBUL).strftime('%H:%M'))} kullanılmaya başlandı"
                if s["cozulme"] else "Ders boyunca boş"
            ),
            "goruldu": s["goruldu_zaman"] is not None,
            "goruldu_metni": (
                datetime.fromtimestamp(s["goruldu_zaman"], ISTANBUL).strftime("%d.%m.%Y %H:%M") if s["goruldu_zaman"] else ""
            ),
        })  # fmt: skip
        nedenler[durum_] = nedenler.get(durum_, 0) + 1
        dersler[ders_adi] = dersler.get(ders_adi, 0) + 1
        t = tahtalar.setdefault(s["tahta_id"], {"tahta_id": s["tahta_id"], "tahta": s["tahta_ad"], "derslik": s["derslik"],
                                                "sayi": 0, "kapali": 0, "kilitli": 0, "oturumsuz": 0, "cozulen": 0})  # fmt: skip
        t["sayi"] += 1
        if s["neden"] in ("kapali", "kilitli", "oturumsuz"):
            t[s["neden"]] += 1
        if s["cozulme"]:
            t["cozulen"] += 1
    return {
        "satirlar": liste,
        "toplam": len(liste),
        "nedenler": sorted(nedenler.items(), key=lambda x: -x[1]),
        "tahtalar": sorted(tahtalar.values(), key=lambda x: (-x["sayi"], x["tahta"])),
        "dersler": sorted(dersler.items(), key=lambda x: -x[1]),
        "gun_sayisi": (bit - bas).days + 1,
    }


def tahta_program(tahta, bos_ders: str | None = None) -> dict:
    """Pano kartı / /api/durum için tahta başına `program` alanı.

    {"kilit_kaynak": "program"|"idare"|None, "acilis": "10:40"|None, "neden": "Teneffüs"|""|None,
     "muaf": bool, "bos_ders": "3. ders (kapalı)"|None, "program_yetenegi": bool}

    `neden` ajanın bildirdiği program kilidi nedenidir; yalnız bilinen üç metinden biri geçer.
    """
    durum = durum_oku(tahta)
    kaynak = None
    if durum.get("kilitli"):
        kaynak = "program" if durum.get("kilit_kaynak") == "program" else "idare"
    neden = None
    if kaynak == "program":
        neden = durum.get("kilit_neden")
        neden = neden if neden in (program.NEDEN_TENEFFUS, program.NEDEN_OGLE, program.NEDEN_DERS_YOK) else ""
    acilis = None
    kalan = durum.get("kilit_kalan")
    if kaynak == "program" and isinstance(kalan, (int, float)) and tahta["son_gorulme"]:
        # Ajan kalan süreyi aşağı yuvarlar (459 sn); açılış en yakın dakikaya yuvarlanır (09:10, 09:09 değil).
        acilis = datetime.fromtimestamp(int(tahta["son_gorulme"] + kalan + 30), ISTANBUL).strftime("%H:%M")
    return {
        "kilit_kaynak": kaynak,
        "acilis": acilis,
        "neden": neden,
        "muaf": bool(tahta["program_muaf"]),
        "bos_ders": bos_ders,
        "program_yetenegi": yetenekli(tahta),
    }
