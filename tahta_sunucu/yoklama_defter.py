"""Şube defteri, son günler, mazeret/izin ve panel düzeltme katmanı (0.14.0; FastAPI'siz, testle sınanır).

Üç katman vardır ve hiçbiri ötekini DEĞİŞTİRMEZ:
  1. yoklama kaydı (`yoklama` + `yoklama_yok` + `yoklama_gec`): öğretmenin/tahtanın ya da panelin aldığı yoklama;
  2. panel düzeltmesi (`yoklama_duzeltme`): idarenin hücre düzeltmesi; kendi izidir, kayda dokunmaz;
  3. mazeret/izin (`yoklama_mazeret`): yokluğu "özürlü" gösterir; var/yok/geç durumunu değiştirmez.

Tek birleşim kuralı (`Veri.kumeler`, `hucre_durumu`): hücrede en yeni düzeltme `kaldir` değilse VE o ders saatinin
en son kaydından ESKİ değilse (`zaman >= guncelleme`) o geçerlidir; yoksa o ders saatinin EN SON KAYDEDİLEN yoklama
kaydı. Yani "en son işlem geçerlidir": tahta `/liste` geçerli durumu (düzeltme dahil) gösterip `/kaydet` tam durumu
yazdığı için düzeltmeden SONRA kaydedilen yoklama düzeltmeyi zaten içerir; öğretmenin bilinçli değişikliği sessizce
ezilmez. Silinip yeniden alınan ders saatinde eski (yetim) düzeltme de bu yüzden geri uygulanmaz. Günlük görünüm,
icmal, CSV, tahtanın `/liste` yanıtı ve buradaki bütün görünümler bu kuraldan geçer.

Yoklama kâğıdın yanında yardımcı kayıttır (K5): "N gündür derste görülmedi" alınan yoklamalardan türetilir,
saklanmaz, dışa aktarılmaz; e-Okul devamsızlık günü değildir (K2). Mazeret TÜRÜ yalnız mazeret sayfasında ve
öğrenci görünümünün mazeret bölümünde görünür; hücrede, icmalde, CSV'de, işlem kaydında yoktur.
Üç tablo da öğrenci kimliği taşır: yıl sonu imhasına girer (kural 24), işlem kaydına yazılmaz.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from . import guvenlik, metin, saklama
from . import program as program_mod
from . import yoklama as yk

DUZELTME_BIRLESTIRME_SN = 60  # aynı kullanıcı aynı hücreyi bu sürede yeniden değiştirirse yeni iz satırı açılmaz
DEFTER_GUN = 5  # varsayılan kip: son beş öğretim günü
DEFTER_GERI_TAKVIM = 30  # beş öğretim günü için en çok bu kadar takvim günü geriye bakılır
ARDISIK_GERI_TAKVIM = 45  # "N gündür" zinciri için yüklenen takvim aralığı
ARDISIK_EN_COK = 30  # zincirde sayılan en çok öğretim günü
OGRENCI_GUN = 20  # öğrenci görünümü: son 20 öğretim günü
OGRENCI_GERI_TAKVIM = 60
SON_GUNLER_ESIK = 2  # okul geneli listeye giren en küçük N
ROZET_VURGU_ESIK = 3
MAZERET_NO_EN_COK = 50
MAZERET_GUN_EN_COK = 31
MAZERET_LISTE_GUN = 30  # biten ve kaldırılan kayıtlar listede bu kadar gün görünür
MAZERET_ONIZLEME_OMRU_SN = 10 * 60
OKUL_NO_EN_UZUN = 20
GUN_KISA = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"]

SIMGE = {"var": "·", "yok": "Y", "gec": "G", "ozurlu": "Ö", "alinmadi": "–", "bos": ""}
DURUM_ADI = {"var": "derste", "yok": "yok", "gec": "geç", "alinmadi": "yoklama alınmadı", "bos": "ders yok"}
FIRCA_DURUMLARI = ("yok", "gec", "var")
SIMGE_DUZELTME_VAR = "V"  # idare düzeltmesiyle "var": "·" + alt çizgi "–" (alınmadı) ile karışıyordu
SERIT = {"hep": ("■", "alınan bütün derslerde yok"), "ozurlu": ("□", "alınan bütün derslerde yok (özürlü)"),
         "kismen": ("◧", "bazı derslerde yok"), "tam": ("·", "yokluk yok"), "alinmadi": ("–", "yoklama alınmadı")}  # fmt: skip

ILETI_ALINMADI = "Bu ders saatinin yoklaması alınmamış. Önce sütun başlığından \"Alındı (herkes var)\" deyin."
ILETI_SALT_OKUNUR = f"Şube defteri yalnız bugün ve son {yk.PANEL_GERI_GUN} gün için düzeltilebilir; daha eski günler salt okunurdur."
ILETI_NOT_GEREK = ("Yok ya da geç yazılmış öğrenciyi \"var\" yapmak için düzeltme notu yazın "
                   f"(en az {yk.ACIKLAMA_EN_KISA} karakter). Öğrenci ya da kişi adı yazmayın.")  # fmt: skip
ILETI_K5 = "Bu kayıt e-Okul girişine yardımcı nottur; e-Okul'un yerini tutmaz."
ILETI_N_GUN = "\"N gündür derste görülmedi\" alınan yoklamalara göre hesaplanır; e-Okul devamsızlık günü değildir."
ILETI_KARISIK_DEVRE = "Ders aralığı için sabah ve öğle şubelerini ayrı girin."


class Alinmadi(ValueError):
    """Yoklaması alınmamış ders saatine hücre yazılamaz (409): yalnız yok/geç satırı tutulduğu için kayıt açmak
    sınıfın geri kalanını "var" saymak olurdu."""


# ---- toplu yükleme ve birleşim -----------------------------------------------------------------
class Veri:
    """Bir tarih aralığının yoklama, düzeltme ve mazeret verisi; sabit sayıda sorguyla yüklenir.

    Sorgular: yoklama, yoklama_yok, yoklama_gec, yoklama_duzeltme, yoklama_mazeret (kurucuda, beşi de birer kez);
    günlerin planı (`program.gun_planlari`), derslik programındaki devreler ve gerekirse öğretmen programı
    saatleri ilk gerektiğinde bir kez. Sorgu sayısı öğrenci ve şube sayısından bağımsızdır.
    """

    def __init__(self, b, bas: date, bit: date, sube: str | None = None):
        self.b, self.bas, self.bit, self.sube = b, bas, bit, sube
        aralik = [bas.isoformat(), bit.isoformat()]
        kosul, arg = (" AND y.sube = ?", [sube]) if sube else ("", [])
        self.yoklamalar = b.execute(
            "SELECT y.id, y.tarih, y.sube, y.ders_no, y.devre, y.kaynak, y.ogretmen_id, y.kaydeden, y.guncelleme, y.mevcut "
            f"FROM yoklama y WHERE y.tarih BETWEEN ? AND ?{kosul} ORDER BY y.id",
            aralik + arg,
        ).fetchall()
        self.kayitlar: dict[tuple[str, str, int], list] = {}
        self.son: dict[tuple[str, str, int], object] = {}
        self._gun_kaydi: dict[tuple[str, str], list] = {}
        for y in self.yoklamalar:
            anahtar = (y["tarih"], y["sube"], y["ders_no"])
            self.kayitlar.setdefault(anahtar, []).append(y)
            onceki = self.son.get(anahtar)
            if onceki is None or (y["guncelleme"], y["id"]) > (onceki["guncelleme"], onceki["id"]):
                self.son[anahtar] = y
            self._gun_kaydi.setdefault((y["tarih"], y["sube"]), []).append(y)
        self._yok = self._isaretler("yoklama_yok", aralik, kosul, arg)
        self._gec = self._isaretler("yoklama_gec", aralik, kosul, arg)
        d_kosul = " AND sube = ?" if sube else ""
        self.duz: dict[tuple[str, str, int], dict[int, object]] = {}
        self.duz_zaman: dict[tuple[str, str], int] = {}
        for d in b.execute(f"SELECT * FROM yoklama_duzeltme WHERE tarih BETWEEN ? AND ?{d_kosul} ORDER BY zaman, id", aralik + arg):
            self.duz.setdefault((d["tarih"], d["sube"], d["ders_no"]), {})[d["ogrenci_id"]] = d  # en yenisi kalır
            gun_anahtari = (d["tarih"], d["sube"])
            self.duz_zaman[gun_anahtari] = max(self.duz_zaman.get(gun_anahtari, 0), d["zaman"])
        self.mazeret_tum: dict[int, list] = {}  # iptal edilenler dahil (e-Okul işaretinin bayatlaması için)
        self.mazeretler: dict[int, list] = {}  # yalnız geçerli olanlar
        for m in b.execute(
            "SELECT * FROM yoklama_mazeret WHERE bas_tarih <= ? AND bit_tarih >= ? ORDER BY olusturma, id", (aralik[1], aralik[0])
        ):
            self.mazeret_tum.setdefault(m["ogrenci_id"], []).append(m)
            if m["tur"] != yk.MAZERET_IPTAL:
                self.mazeretler.setdefault(m["ogrenci_id"], []).append(m)
        self._planlar: dict[date, dict] | None = None
        self._derslik: dict[tuple[int, str], set[str]] | None = None
        self._program: dict[tuple[str, int], list] | None = None
        self._devre: dict[tuple[date, str], str | None] = {}
        self._dersler: dict[tuple[date, str], list[dict]] = {}
        self._kume: dict[tuple[str, str, int], tuple[frozenset, frozenset]] = {}

    def _isaretler(self, tablo: str, aralik: list, kosul: str, arg: list) -> dict[int, set[int]]:
        sonuc: dict[int, set[int]] = {}
        for s in self.b.execute(
            f"SELECT i.yoklama_id, i.ogrenci_id FROM {tablo} i JOIN yoklama y ON y.id = i.yoklama_id "
            f"WHERE y.tarih BETWEEN ? AND ?{kosul}",
            aralik + arg,
        ):
            sonuc.setdefault(s["yoklama_id"], set()).add(s["ogrenci_id"])
        return sonuc

    # ---- plan ve devre ----
    def plan(self, gun: date) -> dict:
        if self._planlar is None:
            gunler = [self.bas + timedelta(days=i) for i in range((self.bit - self.bas).days + 1)]
            try:
                self._planlar = program_mod.gun_planlari(self.b, gunler)
            except Exception:  # bozuk zil takvimi görünümü durdurmasın; plansız gün kayıtlarından çizilir
                self._planlar = {}
        if gun not in self._planlar:
            self._planlar[gun] = {"tatil": None, "dersler": [], "program_gunu": gun.weekday()}
        return self._planlar[gun]

    def _derslik_devreleri(self, program_gunu: int, sube: str) -> set[str]:
        if self._derslik is None:
            self._derslik = {}
            for s in self.b.execute("SELECT DISTINCT gun, sube, devre FROM tahta_ders WHERE sube != ''"):
                ad = metin.sube_duzelt(s["sube"]) or s["sube"]
                self._derslik.setdefault((s["gun"], ad), set()).add(s["devre"])
        return self._derslik.get((program_gunu, sube), set())

    def _program_satirlari(self, program_gunu: int, sube: str) -> list:
        if self._program is None:
            self._program = {}
            # Yalnız şube, gün, ders no ve başlangıç saati: ders adı ve öğretmen sorguya girmez.
            for s in self.b.execute("SELECT DISTINCT sube, gun, ders_no, baslangic FROM ogretmen_program"):
                self._program.setdefault((s["sube"], s["gun"]), []).append((s["ders_no"], s["baslangic"]))
        return self._program.get((sube, program_gunu), [])

    def devre(self, gun: date, sube: str) -> str | None:
        """Şubenin o günkü devresi: o günün kaydında yazılıysa o (program sonradan değişse de sütunlar kaymaz);
        yoksa bugünkü türetme (`yoklama.devre_sec`)."""
        anahtar = (gun, sube)
        if anahtar not in self._devre:
            yazili = [y for y in self._gun_kaydi.get((gun.isoformat(), sube), []) if y["devre"]]
            if yazili:
                self._devre[anahtar] = max(yazili, key=lambda y: (y["guncelleme"], y["id"]))["devre"]
            else:
                plan = self.plan(gun)
                self._devre[anahtar] = yk.devre_sec(
                    plan, self._derslik_devreleri(plan["program_gunu"], sube),
                    lambda: self._program_satirlari(plan["program_gunu"], sube),
                )  # fmt: skip
        return self._devre[anahtar]

    def dersler(self, gun: date, sube: str) -> list[dict]:
        """O gün şubenin sütunları: devresinin planlı dersleri ∪ kaydı bulunan ders numaraları (plan dışı: plan=False).
        Boş liste = öğretim günü değil (hafta sonu, tatil, istisna; kayıt da yok)."""
        anahtar = (gun, sube)
        if anahtar not in self._dersler:
            devre = self.devre(gun, sube)
            sonuc = {s["ders_no"]: {**s, "plan": True} for s in (yk.devre_saatleri(self.plan(gun), devre) if devre else [])}
            for y in self._gun_kaydi.get((gun.isoformat(), sube), []):
                sonuc.setdefault(y["ders_no"], {"ders_no": y["ders_no"], "baslangic": "", "bitis": "", "bas": None, "bit": None,
                                                "plan": False})  # fmt: skip
            self._dersler[anahtar] = [sonuc[n] for n in sorted(sonuc)]
        return self._dersler[anahtar]

    def alinan_dersler(self, gun: date, sube: str) -> list[int]:
        return sorted({y["ders_no"] for y in self._gun_kaydi.get((gun.isoformat(), sube), [])})

    def gec_dersi(self, gun: date, sube: str) -> int:
        """ "Geç" işaretlenebilen ders: devrenin o günkü ilk planlı dersi; plan bilinmiyorsa 1."""
        planli = [d["ders_no"] for d in self.dersler(gun, sube) if d["plan"]]
        return min(planli) if planli else 1

    # ---- birleşim ----
    def alindi(self, tarih: str, sube: str, ders_no: int) -> bool:
        return (tarih, sube, ders_no) in self.son

    def gecerli_duzeltmeler(self, tarih: str, sube: str, ders_no: int) -> dict[int, object]:
        """Ders saatinin GEÇERLİ düzeltmeleri {öğrenci: satır}: kaldırılmamış ve en son kayıttan eski olmayanlar.
        Kayıttan eski düzeltme bayattır (kayıt, düzeltmeyi gören tam durumdur); kayıt yoksa hiçbiri geçerli değildir."""
        son = self.son.get((tarih, sube, ders_no))
        if son is None:
            return {}
        return {oid: d for oid, d in self.duz.get((tarih, sube, ders_no), {}).items()
                if d["durum"] != "kaldir" and d["zaman"] >= son["guncelleme"]}  # fmt: skip

    def kumeler(self, tarih: str, sube: str, ders_no: int) -> tuple[frozenset, frozenset]:
        """Ders saatinin geçerli (yok, geç) kümeleri. Kayıt yoksa ikisi de boş (düzeltme saati "alınmış" yapmaz)."""
        anahtar = (tarih, sube, ders_no)
        if anahtar not in self._kume:
            son = self.son.get(anahtar)
            if son is None:
                self._kume[anahtar] = (frozenset(), frozenset())
            else:
                yok, gec = set(self._yok.get(son["id"], ())), set(self._gec.get(son["id"], ()))
                for oid, d in self.gecerli_duzeltmeler(tarih, sube, ders_no).items():
                    yok.discard(oid)
                    gec.discard(oid)
                    if d["durum"] == "yok":
                        yok.add(oid)
                    elif d["durum"] == "gec":
                        gec.add(oid)
                self._kume[anahtar] = (frozenset(yok), frozenset(gec))
        return self._kume[anahtar]

    def kayit_durumu(self, tarih: str, sube: str, ders_no: int, ogrenci_id: int) -> str:
        """Düzeltme katmanı yokmuş gibi: en son kaydedilen kayıttaki durum (var | yok | gec | alinmadi)."""
        son = self.son.get((tarih, sube, ders_no))
        if son is None:
            return "alinmadi"
        if ogrenci_id in self._yok.get(son["id"], ()):
            return "yok"
        return "gec" if ogrenci_id in self._gec.get(son["id"], ()) else "var"

    def duzeltme(self, tarih: str, sube: str, ders_no: int, ogrenci_id: int):
        """Hücrenin geçerli (kaldırılmamış, kayıttan eski olmayan) düzeltme satırı ya da None."""
        return self.gecerli_duzeltmeler(tarih, sube, ders_no).get(ogrenci_id)

    def durum(self, tarih: str, sube: str, ders_no: int, ogrenci_id: int) -> str:
        if not self.alindi(tarih, sube, ders_no):
            return "alinmadi"
        yok, gec = self.kumeler(tarih, sube, ders_no)
        return "yok" if ogrenci_id in yok else "gec" if ogrenci_id in gec else "var"

    def mazeret_kapsar(self, ogrenci_id: int, tarih: str, ders_no: int, devre: str | None) -> bool:
        return any(mazeret_kapsar(m, tarih, ders_no, devre) for m in self.mazeretler.get(ogrenci_id, ()))

    def hucre(self, gun: date, sube: str, ders_no: int, ogrenci_id: int) -> dict:
        """{"durum", "ozurlu" (yok + geçerli mazeret), "kapsam" (saat mazeret kapsamında), "duzeltme" (bool)}."""
        tarih = gun.isoformat()
        durum = self.durum(tarih, sube, ders_no, ogrenci_id)
        kapsam = self.mazeret_kapsar(ogrenci_id, tarih, ders_no, self.devre(gun, sube)) if ogrenci_id in self.mazeretler else False
        return {"durum": durum, "ozurlu": durum == "yok" and kapsam, "kapsam": kapsam,
                "duzeltme": self.duzeltme(tarih, sube, ders_no, ogrenci_id) is not None}  # fmt: skip


def mazeret_kapsar(m, tarih: str, ders_no: int, devre: str | None = None) -> bool:
    """Geçerli mazeret bu gün ve ders saatini kapsıyor mu? Ders aralığı yalnız AYNI devrenin ders numaralarına
    uygulanır (kural 25); iki taraftan biri devresizse numara yeter. İptal edilmiş kayıt hiçbir şeyi kapsamaz."""
    if m["tur"] == yk.MAZERET_IPTAL or not m["bas_tarih"] <= tarih <= m["bit_tarih"]:
        return False
    if m["ders_bas"] is None:
        return True
    if m["devre"] and devre and m["devre"] != devre:
        return False
    return m["ders_bas"] <= ders_no <= m["ders_bit"]


def hucre_durumu(b, tarih: str, sube: str, ders_no: int, ogrenci_id: int) -> dict:
    """Tek hücrenin geçerli durumu (birleşim kuralının tek işlevi; toplu görünümler `Veri` ile aynı kodu kullanır)."""
    gun = yk.tarih_coz(tarih)
    if not gun:
        return {"durum": "alinmadi", "ozurlu": False, "kapsam": False, "duzeltme": False}
    return Veri(b, gun, gun, sube).hucre(gun, sube, ders_no, ogrenci_id)


def simge(hucre: dict) -> str:
    if hucre.get("ozurlu"):
        return SIMGE["ozurlu"]
    if hucre["durum"] == "var" and hucre.get("duzeltme"):
        return SIMGE_DUZELTME_VAR
    return SIMGE[hucre["durum"]]


def durum_metni(hucre: dict) -> str:
    """Erişilebilirlik metni: "yok, özürlü" · "derste" · "yoklama alınmadı, özür kapsamında" (tür YOK)."""
    ad = DURUM_ADI[hucre["durum"]]
    if hucre.get("ozurlu"):
        ad += ", özürlü"
    elif hucre.get("kapsam") and hucre["durum"] in ("var", "alinmadi"):
        ad += ", özür kapsamında"
    if hucre.get("duzeltme"):
        ad += ", idare düzeltmesi"
    return ad


# ---- öğrenciler ve günler ------------------------------------------------------------------------
def _sube_ogrencileri(b, veri: Veri, sube: str) -> list:
    """Şubenin etkin öğrencileri + bu aralıkta bu şubede işareti/düzeltmesi bulunan (pasifleşmiş, şubesi değişmiş)
    öğrenciler; okul no sırasıyla. Tek sorgu."""
    ek: set[int] = set()
    for (_tarih, s, _no), son in veri.son.items():
        if s == sube:
            ek |= veri._yok.get(son["id"], set()) | veri._gec.get(son["id"], set())
    for tarih, s, no in veri.duz:
        if s == sube:
            ek |= set(veri.gecerli_duzeltmeler(tarih, s, no))
    idler = sorted(ek)
    satirlar = b.execute(
        f"SELECT * FROM ogrenci WHERE (sube = ? AND aktif = 1){' OR id IN (' + ','.join('?' * len(idler)) + ')' if idler else ''}",
        [sube, *idler],
    ).fetchall()
    return yk.ogrenci_sirala(satirlar)


def ogretim_gunleri(veri: Veri, sube: str, bitis: date, en_cok: int, geri_takvim: int) -> list[date]:
    """`bitis`ten geriye öğretim günleri (yeniden eskiye). Öğretim günü = şubenin devresi için planda ders var YA DA
    o gün o şubenin yoklama kaydı var; hafta sonu, tatil ve istisna günleri (kayıt yoksa) atlanır."""
    sonuc = []
    for i in range(geri_takvim + 1):
        gun = bitis - timedelta(days=i)
        if gun < veri.bas:
            break
        if veri.dersler(gun, sube):
            sonuc.append(gun)
            if len(sonuc) >= en_cok:
                break
    return sonuc


def gun_ozeti(veri: Veri, gun: date, sube: str, ogrenci_id: int) -> str:
    """Gün şeridi durumu: hep (alınan bütün derslerde yok) | kismen | tam | alinmadi."""
    alinan = veri.alinan_dersler(gun, sube)
    if not alinan:
        return "alinmadi"
    tarih = gun.isoformat()
    yok = sum(1 for n in alinan if ogrenci_id in veri.kumeler(tarih, sube, n)[0])
    return "hep" if yok == len(alinan) else "kismen" if yok else "tam"


def ardisik_yok(veri: Veri, sube: str, ogrenci_id: int, gunler: list[date]) -> tuple[int, bool]:
    """(N, mazeretsiz gün var mı): yeniden eskiye `gunler` üzerinde, yoklaması alınmış en az bir dersi olan ve
    alınan BÜTÜN derslerinde yok olduğu art arda gün sayısı. Hiç yoklama alınmamış gün zinciri ne kırar ne sayılır.
    Türetilmiş değerdir: saklanmaz, dışa aktarılmaz; e-Okul devamsızlık günü değildir (K2/K5)."""
    n, mazeretsiz = 0, False
    for gun in gunler[:ARDISIK_EN_COK]:
        alinan = veri.alinan_dersler(gun, sube)
        if not alinan:
            continue
        tarih = gun.isoformat()
        if not all(ogrenci_id in veri.kumeler(tarih, sube, no)[0] for no in alinan):
            break
        n += 1
        devre = veri.devre(gun, sube)
        if not all(veri.mazeret_kapsar(ogrenci_id, tarih, no, devre) for no in alinan):
            mazeretsiz = True
    return n, mazeretsiz


def rozet(n: int, mazeretsiz: bool) -> dict | None:
    """N ≥ 2 rozeti: {"tur": vurgulu|duz|ozurlu, "kisa", "uzun", "metin"}; N < 2 → None. Mazeret türü yazılmaz.
    `kisa` beş gün kipindeki dar sütun içindir ("3 gündür", "3 gün (Ö)"); `metin` ipucu ve ekran okuyucu metnidir."""
    if n < SON_GUNLER_ESIK:
        return None
    if not mazeretsiz:
        return {"tur": "ozurlu", "kisa": f"{n} gün (Ö)", "uzun": f"{n} gündür yok (özürlü)",
                "metin": f"alınan yoklamalara göre {n} gündür yok (özürlü)"}  # fmt: skip
    return {"tur": "vurgulu" if n >= ROZET_VURGU_ESIK else "duz", "kisa": f"{n} gündür", "uzun": f"{n} gündür derste görülmedi",
            "metin": f"alınan yoklamalara göre {n} gündür derste görülmedi"}  # fmt: skip


def _serit_durumu(veri: Veri, gun: date, sube: str, ogrenci_id: int) -> str:
    """Gün şeridi durumu: `gun_ozeti` + "ozurlu" (alınan bütün derslerde yok ve hepsi mazeret kapsamında; tür yok)."""
    d = gun_ozeti(veri, gun, sube, ogrenci_id)
    if d == "hep" and ogrenci_id in veri.mazeretler:
        tarih, devre = gun.isoformat(), veri.devre(gun, sube)
        if all(veri.mazeret_kapsar(ogrenci_id, tarih, no, devre) for no in veri.alinan_dersler(gun, sube)):
            return "ozurlu"
    return d


def _serit(veri: Veri, sube: str, ogrenci_id: int, gunler: list[date]) -> list[dict]:
    return [{"simge": SERIT[d][0], "durum": d, "metin": f"{gun:%d.%m} {GUN_KISA[gun.weekday()]}: {SERIT[d][1]}"}
            for gun in gunler for d in [_serit_durumu(veri, gun, sube, ogrenci_id)]]  # fmt: skip


def _hucre_gorunumu(veri: Veri, gun: date, sube: str, ders_no: int, o, gun_metni: str, gelecek: bool = False) -> dict:
    """`gelecek`: bugünün henüz başlamamış dersi; "yoklama alınmadı" (–) yerine boş ve "henüz başlamadı" görünür."""
    h = veri.hucre(gun, sube, ders_no, o["id"])
    gelecek = gelecek and h["durum"] == "alinmadi"
    metin_ = "henüz başlamadı" if gelecek else durum_metni(h)
    return {**h, "ders_no": ders_no, "gelecek": gelecek, "simge": "" if gelecek else simge(h),
            "etiket": f"{yk.ad_soyad(o)}, {gun_metni} {ders_no}. ders: {metin_}"}  # fmt: skip


def sonraki_bitis(b, sube: str, bitis: date, bugun: date, gun_sayisi: int = DEFTER_GUN) -> date:
    """Beş gün gezgininin "sonraki" bitişi: `bitis`ten ileriye `gun_sayisi` öğretim günü (bugünle sınırlı); böylece
    "önceki" ile simetriktir (aynı gün iki pencerede yinelenmez, gün atlanmaz)."""
    son = min(bugun, bitis + timedelta(days=DEFTER_GERI_TAKVIM))
    if son <= bitis:
        return bugun
    veri = Veri(b, bitis + timedelta(days=1), son, sube)
    n, gun = 0, bitis
    while gun < son:
        gun += timedelta(days=1)
        if veri.dersler(gun, sube):
            n += 1
            if n >= gun_sayisi:
                return gun
    return bugun


# ---- şube defteri: beş gün kipi ---------------------------------------------------------------------
def sube_defteri(b, sube: str, bitis: date, an: int, gun_sayisi: int = DEFTER_GUN, yalniz_yok: bool = False) -> dict:
    """Son `gun_sayisi` öğretim günü: öğrenci × (gün × ders saati) ızgarası, gün şeridi, "N gündür" rozeti."""
    bugun = yk.bugun(an)
    bitis = min(bitis, bugun)
    veri = Veri(b, bitis - timedelta(days=ARDISIK_GERI_TAKVIM), bitis, sube)
    ogrenciler = _sube_ogrencileri(b, veri, sube)
    zincir = ogretim_gunleri(veri, sube, bitis, ARDISIK_EN_COK, ARDISIK_GERI_TAKVIM)
    gunler = sorted(g for g in zincir[:gun_sayisi] if g >= bitis - timedelta(days=DEFTER_GERI_TAKVIM))
    gun_basliklari = []
    for gun in gunler:
        gun_basliklari.append({
            "tarih": gun.isoformat(), "kisa": f"{GUN_KISA[gun.weekday()]} {gun:%d.%m}", "yazi": yk.tarih_yazi(gun),
            "bugun": gun == bugun,
            "dersler": [{"ders_no": d["ders_no"], "plan": d["plan"], "gelecek": _gelecek(d, gun, an)} for d in veri.dersler(gun, sube)],
        })  # fmt: skip
    satirlar = []
    for o in ogrenciler:
        bu_subede = bool(o["aktif"]) and o["sube"] == sube
        n, mazeretsiz = ardisik_yok(veri, sube, o["id"], zincir) if bu_subede else (0, False)
        yok = gec = 0
        gun_hucreleri = []
        for gun, baslik in zip(gunler, gun_basliklari, strict=True):
            hucreler = [_hucre_gorunumu(veri, gun, sube, d["ders_no"], o, f"{gun:%d.%m} {yk.GUN_ADLARI[gun.weekday()]}", d["gelecek"])
                        for d in baslik["dersler"]]  # fmt: skip
            yok += sum(1 for h in hucreler if h["durum"] == "yok")
            gec += sum(1 for h in hucreler if h["durum"] == "gec")
            gun_hucreleri.append(hucreler)
        if yalniz_yok and not yok:
            continue
        satirlar.append({
            "id": o["id"], "okul_no": o["okul_no"], "ad_soyad": yk.ad_soyad(o), "pasif": not bu_subede, "n": n,
            "rozet": rozet(n, mazeretsiz), "serit": _serit(veri, sube, o["id"], gunler), "gunler": gun_hucreleri,
            "yok": yok, "gec": gec,
        })  # fmt: skip
    onceki = (gunler[0] - timedelta(days=1)) if gunler else bitis - timedelta(days=7)
    sonraki = sonraki_bitis(b, sube, bitis, bugun, gun_sayisi) if bitis < bugun else bugun
    return {
        "sube": sube, "bitis": bitis.isoformat(), "bitis_yazi": yk.tarih_yazi(bitis), "gun_sayisi": gun_sayisi,
        "gunler": gun_basliklari, "satirlar": satirlar, "ogrenci_sayisi": len(ogrenciler), "yalniz_yok": yalniz_yok,
        "onceki": onceki.isoformat(), "sonraki": sonraki.isoformat() if bitis < bugun else "", "bugun": bitis == bugun,
        "ders_sayisi": sum(len(g["dersler"]) for g in gun_basliklari),
        "plan_disi_var": any(not d["plan"] for g in gun_basliklari for d in g["dersler"]),
        "devre_adi": yk.sube_devre_adi(b, veri.plan(bitis), sube),
    }  # fmt: skip


# ---- şube defteri: gün kipi -------------------------------------------------------------------------
def duzenlenebilir(gun: date, an: int) -> bool:
    bugun = yk.bugun(an)
    return bugun - timedelta(days=yk.PANEL_GERI_GUN) <= gun <= bugun


def _gelecek(ders: dict, gun: date, an: int) -> bool:
    return gun == yk.bugun(an) and ders["bas"] is not None and ders["bas"] > an + yk.GELECEK_PAYI_SN


def sube_gunu(b, sube: str, gun: date, an: int) -> dict:
    """Bir günün öğrenci × ders saati ızgarası (düzenlenebilir görünüm)."""
    veri = Veri(b, gun, gun, sube)
    tarih = gun.isoformat()
    ogrenciler = _sube_ogrencileri(b, veri, sube)
    dersler = veri.dersler(gun, sube)
    acik = duzenlenebilir(gun, an)
    gec_dersi = veri.gec_dersi(gun, sube)
    gun_metni = f"{gun:%d.%m} {yk.GUN_ADLARI[gun.weekday()]}"
    sutunlar = []
    for d in dersler:
        no = d["ders_no"]
        yok, gec = veri.kumeler(tarih, sube, no)
        alindi = veri.alindi(tarih, sube, no)
        gelecek = _gelecek(d, gun, an)
        sutunlar.append({
            "ders_no": no, "aralik": f"{d['baslangic']}–{d['bitis']}" if d["baslangic"] else "", "plan": d["plan"], "alindi": alindi,
            "gelecek": gelecek, "gec": no == gec_dersi, "yok_sayisi": len(yok), "gec_sayisi": len(gec),
            "alinabilir": acik and not alindi and not gelecek,
        })  # fmt: skip
    satirlar = []
    for o in ogrenciler:
        hucreler = []
        for s in sutunlar:
            h = _hucre_gorunumu(veri, gun, sube, s["ders_no"], o, gun_metni, s["gelecek"])
            h["tiklanir"] = acik and s["alindi"]
            hucreler.append(h)
        satirlar.append({
            "id": o["id"], "okul_no": o["okul_no"], "ad_soyad": yk.ad_soyad(o), "pasif": not (o["aktif"] and o["sube"] == sube),
            "hucreler": hucreler, "yok": sum(1 for h in hucreler if h["durum"] == "yok"),
            "gec": sum(1 for h in hucreler if h["durum"] == "gec"), "duzeltme_var": any(h["duzeltme"] for h in hucreler),
        })  # fmt: skip
    islenen = b.execute("SELECT * FROM eokul_islendi WHERE tarih = ? AND sube = ?", (tarih, sube)).fetchone()
    bugun = yk.bugun(an)
    return {
        "sube": sube, "tarih": tarih, "tarih_yazi": yk.tarih_yazi(gun), "bugun": gun == bugun,
        "onceki": (gun - timedelta(days=1)).isoformat(), "sonraki": (gun + timedelta(days=1)).isoformat() if gun < bugun else "",
        "duzenlenebilir": acik, "sutunlar": sutunlar, "satirlar": satirlar, "tatil": veri.plan(gun).get("tatil"),
        "gec_var": any(s["gec"] and s["alindi"] for s in sutunlar), "alinan": sum(1 for s in sutunlar if s["alindi"]),
        "plan_disi_var": any(not s["plan"] for s in sutunlar), "devre_adi": yk.sube_devre_adi(b, veri.plan(gun), sube),
        "alinabilir_var": any(s["alinabilir"] for s in sutunlar),
        "gun_boyu_yok": len(gun_boyu_yoklar(veri, gun, sube, ogrenciler)),
        "islendi": bool(islenen), "bayat": bool(islenen) and sube in eokul_bayat(b, veri, tarih, {sube: islenen}),
        "islendi_metni": f"{islenen['kullanici']}, {yk.an_yazi(islenen['zaman'])}" if islenen else "",
    }  # fmt: skip


def hucre_ozetleri(b, sube: str, gun: date, ogrenci_id: int, ders_no: int) -> dict:
    """Bir hücre değişince yerinde güncellenecek sayılar (ad ve numara İÇERMEZ): satır ve sütun özeti."""
    veri = Veri(b, gun, gun, sube)
    tarih = gun.isoformat()
    h = veri.hucre(gun, sube, ders_no, ogrenci_id)
    satir = [veri.durum(tarih, sube, d["ders_no"], ogrenci_id) for d in veri.dersler(gun, sube)]
    yok, gec = veri.kumeler(tarih, sube, ders_no)
    satir_duzeltme = any(ogrenci_id in veri.gecerli_duzeltmeler(tarih, sube, d["ders_no"]) for d in veri.dersler(gun, sube))
    return {"durum": h["durum"], "ozurlu": h["ozurlu"], "kapsam": h["kapsam"], "duzeltme": h["duzeltme"], "simge": simge(h),
            "durum_metni": durum_metni(h), "satir_ozeti": {"yok": satir.count("yok"), "gec": satir.count("gec")},
            "sutun_ozeti": {"yok": len(yok), "gec": len(gec)}, "satir_duzeltme": satir_duzeltme}  # fmt: skip


# ---- düzeltme katmanı --------------------------------------------------------------------------------
def not_coz(aciklama) -> str:
    """Düzeltme notu (isteğe bağlı): kırpılır; T.C. kimlik numarası içeriyorsa reddedilir."""
    aciklama = " ".join(str(aciklama or "").split())[: yk.ACIKLAMA_EN_UZUN]
    if aciklama and guvenlik.tc_kimlik_var(aciklama):
        raise ValueError(guvenlik.TC_KIMLIK_ILETISI)
    return aciklama


def hucre_yaz(b, *, gun: date, sube: str, ders_no: int, ogrenci_id: int, durum: str, giren: str, an: int,
              aciklama: str = "", veri: Veri | None = None) -> bool:  # fmt: skip
    """Şube defteri hücresine düzeltme yazar; öğretmen/tahta kaydına DOKUNMAZ. Döndürür: bir şey değişti mi.

    "Fırça" modeli: istenen durum hücrenin geçerli düzeltmesiyle ya da (düzeltme yokken) kayıttaki durumla aynıysa
    düzeltme kaldırılır / hiçbir şey yazılmaz (alttaki kayıt görünür); değilse o durum yazılır. Aynı kullanıcı aynı
    hücreyi 60 sn içinde yeniden değiştirirse yeni satır açılmaz, son satırı güncellenir. Kayıttaki yok/geç'i
    "var"a çeviren düzeltmede not zorunludur. Geç yalnız devrenin ilk dersinde. Yoklaması alınmamış saatte
    `Alinmadi` (409); düzenleme penceresi dışında ve gelecek derste ValueError.
    """
    if durum not in FIRCA_DURUMLARI:
        raise ValueError("Durum geçersiz.")
    if not duzenlenebilir(gun, an):
        raise ValueError(ILETI_SALT_OKUNUR)
    tarih = gun.isoformat()
    veri = veri or Veri(b, gun, gun, sube)
    ders = next((d for d in veri.dersler(gun, sube) if d["ders_no"] == ders_no), None)
    if ders is not None and _gelecek(ders, gun, an):
        raise ValueError(yk.ILETI_GELECEK)
    if not veri.alindi(tarih, sube, ders_no):
        raise Alinmadi(ILETI_ALINMADI)
    o = b.execute("SELECT id, sube, aktif FROM ogrenci WHERE id = ?", (ogrenci_id,)).fetchone()
    kayit = veri.kayit_durumu(tarih, sube, ders_no, ogrenci_id)
    eski = veri.duzeltme(tarih, sube, ders_no, ogrenci_id)
    if not o or not ((o["aktif"] and o["sube"] == sube) or kayit != "var" or eski is not None):
        raise ValueError(yk.ILETI_LISTE_DEGISTI)
    if durum == "gec" and ders_no != veri.gec_dersi(gun, sube):
        raise ValueError(yk.ILETI_GEC_ILK_DERS)
    if eski is not None and (eski["durum"] == durum or durum == kayit):
        yeni = "kaldir"
    elif eski is None and durum == kayit:
        return False
    else:
        yeni = durum
    aciklama = not_coz(aciklama)
    if yeni == "var" and kayit in ("yok", "gec") and len(aciklama) < yk.ACIKLAMA_EN_KISA:
        raise ValueError(ILETI_NOT_GEREK)
    son = b.execute(
        "SELECT id, giren, zaman FROM yoklama_duzeltme WHERE sube = ? AND tarih = ? AND ders_no = ? AND ogrenci_id = ? "
        "ORDER BY zaman DESC, id DESC LIMIT 1",
        (sube, tarih, ders_no, ogrenci_id),
    ).fetchone()
    if son and son["giren"] == giren and 0 <= an - son["zaman"] < DUZELTME_BIRLESTIRME_SN:
        b.execute("UPDATE yoklama_duzeltme SET durum = ?, aciklama = ?, zaman = ? WHERE id = ?", (yeni, aciklama, an, son["id"]))
    else:
        b.execute(
            "INSERT INTO yoklama_duzeltme (tarih, sube, ders_no, ogrenci_id, durum, aciklama, giren, zaman) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (tarih, sube, ders_no, ogrenci_id, yeni, aciklama, giren, an),
        )
    return True


def satir_butun_gun_yok(b, *, gun: date, sube: str, ogrenci_id: int, giren: str, an: int, aciklama: str = "") -> tuple[int, int]:
    """ "Bütün gün yok": YALNIZ yoklaması alınmış ders saatlerine uygulanır. (yazılan, atlanan ders saati) döner."""
    veri = Veri(b, gun, gun, sube)
    tarih = gun.isoformat()
    yazilan = atlanan = 0
    for d in veri.dersler(gun, sube):
        if not veri.alindi(tarih, sube, d["ders_no"]):
            atlanan += 0 if _gelecek(d, gun, an) else 1
            continue
        if veri.durum(tarih, sube, d["ders_no"], ogrenci_id) == "yok":
            continue
        yazilan += int(hucre_yaz(b, gun=gun, sube=sube, ders_no=d["ders_no"], ogrenci_id=ogrenci_id, durum="yok", giren=giren,
                                 an=an, aciklama=aciklama, veri=veri))  # fmt: skip
    return yazilan, atlanan


def satir_temizle(b, *, gun: date, sube: str, ogrenci_id: int, giren: str, an: int) -> int:
    """Öğrencinin o günkü düzeltmelerini kaldırır (kayıtlar geri görünür). Kaldırılan hücre sayısı."""
    if not duzenlenebilir(gun, an):
        raise ValueError(ILETI_SALT_OKUNUR)
    veri = Veri(b, gun, gun, sube)
    tarih = gun.isoformat()
    n = 0
    for t, s, no in list(veri.duz):
        if t == tarih and s == sube and ogrenci_id in veri.gecerli_duzeltmeler(t, s, no):
            b.execute(
                "INSERT INTO yoklama_duzeltme (tarih, sube, ders_no, ogrenci_id, durum, aciklama, giren, zaman) "
                "VALUES (?, ?, ?, ?, 'kaldir', '', ?, ?)",
                (tarih, sube, no, ogrenci_id, giren, an),
            )
            n += 1
    return n


def gun_boyu_yoklar(veri: Veri, gun: date, sube: str, ogrenciler=None) -> list[int]:
    """O gün yoklaması alınmış (en az bir) ders saatinin HEPSİNDE yok olan etkin öğrencilerin kimlikleri.
    "Alındı (herkes var)" bu öğrencileri sessizce "derste" saymasın diye kullanılır."""
    alinan = veri.alinan_dersler(gun, sube)
    if not alinan:
        return []
    tarih = gun.isoformat()
    hep_yok = frozenset.intersection(*(veri.kumeler(tarih, sube, no)[0] for no in alinan))
    if not hep_yok:
        return []
    if ogrenciler is None:
        ogrenciler = veri.b.execute("SELECT id, sube, aktif FROM ogrenci WHERE sube = ? AND aktif = 1", (sube,)).fetchall()
    return sorted(o["id"] for o in ogrenciler if o["aktif"] and o["sube"] == sube and o["id"] in hep_yok)


def sutun_alindi(b, *, gun: date, sube: str, ders_no: int, giren: str, an: int, gun_boyu_yok: bool = False) -> int:
    """ "Alındı (herkes var)": yoklaması alınmamış ders saatine panel kaynaklı kayıt açar. Çağıran, "işaretlenmeyen
    herkes derste sayılacak" onayını almış olmalıdır. `gun_boyu_yok`: o gün alınan diğer bütün derslerde yok yazılmış
    öğrenciler bu derste de yok yazılır (yoksa "N gündür" zinciri sessizce kırılırdı). Yok yazılan sayısı döner."""
    if not duzenlenebilir(gun, an):
        raise ValueError(ILETI_SALT_OKUNUR)
    veri = Veri(b, gun, gun, sube)
    tarih = gun.isoformat()
    if veri.alindi(tarih, sube, ders_no):
        raise ValueError("Bu ders saatinin yoklaması zaten alınmış.")
    ders = next((d for d in veri.dersler(gun, sube) if d["ders_no"] == ders_no), None)
    if ders is None:
        raise ValueError("Bu şubenin o günkü ders saatlerinde bu ders yok.")
    if _gelecek(ders, gun, an):
        raise ValueError(yk.ILETI_GELECEK)
    if not b.execute("SELECT 1 FROM ogrenci WHERE sube = ? AND aktif = 1 LIMIT 1", (sube,)).fetchone():
        raise ValueError(yk.ILETI_LISTE_YOK)
    yoklar = gun_boyu_yoklar(veri, gun, sube) if gun_boyu_yok else []
    yk.yoklama_yaz(b, tarih=tarih, sube=sube, ders_no=ders_no, ogretmen_id=None, kaynak="panel", kaydeden=giren, tahta_id=None,
                   yok=yoklar, gec=[], kim=giren, an=an)  # fmt: skip
    return len(yoklar)


# ---- e-Okul işaretinin bayatlaması ---------------------------------------------------------------------
def eokul_bayat(b, veri: Veri, tarih: str, islenen: dict) -> set[str]:
    """ "İşlendi" işaretinden SONRA değişen şubeler: yoklama kaydı, panel düzeltmesi ya da o günü kapsayan mazeret
    (giriş/kaldırma) işaretten yeniyse. `islenen`: {şube: eokul_islendi satırı}. Şema değişmez (hepsi epoch)."""
    if not islenen:
        return set()
    son: dict[str, int] = {}
    for y in veri.yoklamalar:
        if y["tarih"] == tarih:
            son[y["sube"]] = max(son.get(y["sube"], 0), y["guncelleme"])
    for (t, sube), zaman in veri.duz_zaman.items():
        if t == tarih:
            son[sube] = max(son.get(sube, 0), zaman)
    ilgili = {oid: [m for m in ms if m["bas_tarih"] <= tarih <= m["bit_tarih"]] for oid, ms in veri.mazeret_tum.items()}
    ilgili = {oid: ms for oid, ms in ilgili.items() if ms}
    if ilgili:
        idler = sorted(ilgili)
        for o in b.execute(f"SELECT id, sube FROM ogrenci WHERE id IN ({','.join('?' * len(idler))})", idler):
            for m in ilgili[o["id"]]:
                son[o["sube"]] = max(son.get(o["sube"], 0), m["olusturma"], m["iptal_zamani"] or 0)
    return {sube for sube, satir in islenen.items() if son.get(sube, 0) > satir["zaman"]}


# ---- okul geneli "son günler" ve öğrenci görünümü ------------------------------------------------------
def son_gunler(b, an: int, ozurluler: bool = False) -> dict:
    """Okul geneli kısa liste: "N gündür derste görülmedi" N ≥ 2 olan öğrenciler, N'ye göre azalan.
    Varsayılan olarak yalnız zincirinde mazeretsiz günü olanlar; `ozurluler` ile hepsi. Yalnız yazdırılır."""
    bugun = yk.bugun(an)
    veri = Veri(b, bugun - timedelta(days=ARDISIK_GERI_TAKVIM), bugun)
    subeler: dict[str, list] = {}
    for o in b.execute("SELECT * FROM ogrenci WHERE aktif = 1"):
        subeler.setdefault(o["sube"], []).append(o)
    satirlar = []
    ozurlu_gizlenen = 0
    for sube, ogrenciler in subeler.items():
        zincir = ogretim_gunleri(veri, sube, bugun, ARDISIK_EN_COK, ARDISIK_GERI_TAKVIM)
        son_bes = sorted(zincir[:DEFTER_GUN])
        for o in ogrenciler:
            n, mazeretsiz = ardisik_yok(veri, sube, o["id"], zincir)
            if n < SON_GUNLER_ESIK:
                continue
            if not mazeretsiz and not ozurluler:
                ozurlu_gizlenen += 1
                continue
            satirlar.append({"id": o["id"], "sube": sube, "okul_no": o["okul_no"], "ad_soyad": yk.ad_soyad(o), "n": n,
                             "rozet": rozet(n, mazeretsiz), "serit": _serit(veri, sube, o["id"], son_bes)})  # fmt: skip
    satirlar.sort(key=lambda r: (-r["n"], yk.sube_anahtari(r["sube"]), yk.no_anahtari(r["okul_no"])))
    return {"satirlar": satirlar, "ozurluler": ozurluler, "ozurlu_gizlenen": ozurlu_gizlenen, "tarih_yazi": yk.tarih_yazi(bugun),
            "bugun": bugun.isoformat()}  # fmt: skip


def ogrenci_gorunumu(b, ogrenci_id: int, an: int) -> dict | None:
    """Öğrencinin şubesindeki son 20 öğretim günü (satır = gün, sütun = ders saati) ve mazeret kayıtları.
    Mazeret türü yalnız burada ve mazeret sayfasında görünür. Salt okunur."""
    o = b.execute("SELECT * FROM ogrenci WHERE id = ?", (ogrenci_id,)).fetchone()
    if not o:
        return None
    bugun = yk.bugun(an)
    sube = o["sube"]
    veri = Veri(b, bugun - timedelta(days=OGRENCI_GERI_TAKVIM), bugun, sube)
    gunler = ogretim_gunleri(veri, sube, bugun, OGRENCI_GUN, OGRENCI_GERI_TAKVIM)
    sutunlar = sorted({d["ders_no"] for g in gunler for d in veri.dersler(g, sube)})
    satirlar = []
    for gun in gunler:
        var_olan = {d["ders_no"] for d in veri.dersler(gun, sube)}
        gun_metni = f"{gun:%d.%m} {yk.GUN_ADLARI[gun.weekday()]}"
        hucreler = [(_hucre_gorunumu(veri, gun, sube, n, o, gun_metni) if n in var_olan else
                     {"durum": "bos", "ders_no": n, "simge": "", "etiket": "", "ozurlu": False, "kapsam": False, "duzeltme": False})
                    for n in sutunlar]  # fmt: skip
        satirlar.append({"tarih": gun.isoformat(), "yazi": yk.tarih_yazi(gun), "hucreler": hucreler,
                         "yok": sum(1 for h in hucreler if h["durum"] == "yok"), "gec": sum(1 for h in hucreler if h["durum"] == "gec")})  # fmt: skip
    zincir = ogretim_gunleri(veri, sube, bugun, ARDISIK_EN_COK, ARDISIK_GERI_TAKVIM)
    n, mazeretsiz = ardisik_yok(veri, sube, ogrenci_id, zincir) if o["aktif"] else (0, False)
    mazeretler = [_mazeret_satiri(m, bugun) for m in b.execute(
        "SELECT m.*, o.okul_no, o.ad, o.soyad, o.sube FROM yoklama_mazeret m JOIN ogrenci o ON o.id = m.ogrenci_id "
        "WHERE m.ogrenci_id = ? ORDER BY m.bas_tarih DESC, m.id DESC", (ogrenci_id,))]  # fmt: skip
    return {"id": o["id"], "okul_no": o["okul_no"], "ad_soyad": yk.ad_soyad(o), "sube": sube, "pasif": not o["aktif"],
            "sutunlar": sutunlar, "satirlar": satirlar, "rozet": rozet(n, mazeretsiz), "mazeretler": mazeretler,
            "yok": sum(s["yok"] for s in satirlar), "gec": sum(s["gec"] for s in satirlar)}  # fmt: skip


# ---- mazeret/izin ----------------------------------------------------------------------------------------
_NO_AYIRICI = re.compile(r"[\s,;]+")


def mazeret_ust_siniri(b, bugun: date) -> date:
    """Mazeretin bitebileceği en geç gün: öğretim yılı bitişi girilmişse o, değilse bugün + 31 gün."""
    return saklama.bitis_al(b) or bugun + timedelta(days=MAZERET_GUN_EN_COK)


def mazeret_coz(b, form, an: int) -> dict:
    """Mazeret formu → girdi sözlüğü; geçersizde kullanıcıya gösterilecek iletiyle ValueError.
    Alanlar: nolar, bas, bit, kapsam (tam|ders), ders_bas, ders_bit, tur, dayanak. Serbest metin alanı YOKTUR."""
    bugun = yk.bugun(an)
    nolar = list(dict.fromkeys(n for n in _NO_AYIRICI.split(str(form.get("nolar", "")).strip()) if n))
    if not nolar:
        raise ValueError("En az bir okul numarası yazın.")
    if len(nolar) > MAZERET_NO_EN_COK:
        raise ValueError(f"Bir seferde en çok {MAZERET_NO_EN_COK} okul numarası girilebilir.")
    if any(len(n) > OKUL_NO_EN_UZUN for n in nolar):
        raise ValueError("Okul numarası çok uzun.")
    if any(guvenlik.tc_kimlik_var(n) for n in nolar):
        raise ValueError(guvenlik.TC_KIMLIK_ILETISI)
    bas, bit = yk.tarih_coz(form.get("bas")), yk.tarih_coz(form.get("bit") or form.get("bas"))
    if not bas or not bit:
        raise ValueError("Başlangıç ve bitiş tarihini seçin.")
    if bit < bas:
        raise ValueError("Bitiş tarihi başlangıçtan önce olamaz.")
    if (bit - bas).days + 1 > MAZERET_GUN_EN_COK:
        raise ValueError(f"Bir mazeret kaydı en çok {MAZERET_GUN_EN_COK} gün olabilir.")
    if bas < bugun - timedelta(days=yk.PANEL_GERI_GUN):
        raise ValueError(f"Başlangıç tarihi en çok {yk.PANEL_GERI_GUN} gün geriye gidebilir.")
    ust = mazeret_ust_siniri(b, bugun)
    if bit > ust:
        raise ValueError(f"Bitiş tarihi en geç {saklama.tarih_metni(ust)} olabilir.")
    ders_bas = ders_bit = None
    if str(form.get("kapsam", "tam")) == "ders":
        try:
            ders_bas, ders_bit = int(str(form.get("ders_bas", "")).strip()), int(str(form.get("ders_bit", "")).strip())
        except ValueError:
            raise ValueError("Ders aralığı için ilk ve son ders numarasını yazın.") from None
        if not 1 <= ders_bas <= ders_bit <= 20:
            raise ValueError("Ders aralığı 1–20 arasında ve ilk ders sondan büyük olmamalı.")
    tur = str(form.get("tur", ""))
    if tur not in yk.MAZERET_TURLERI:
        raise ValueError("Mazeret türünü seçin.")
    dayanak = str(form.get("dayanak", ""))
    if dayanak not in yk.MAZERET_DAYANAKLARI:
        raise ValueError("Dayanak seçimi geçersiz.")
    return {"nolar": nolar, "bas": bas.isoformat(), "bit": bit.isoformat(), "ders_bas": ders_bas, "ders_bit": ders_bit,
            "tur": tur, "dayanak": dayanak}  # fmt: skip


def aralik_metni(bas: str, bit: str) -> str:
    b1, b2 = yk.tarih_coz(bas), yk.tarih_coz(bit)
    if not b1 or not b2:
        return f"{bas}–{bit}"
    return yk.tarih_kisa(b1) if b1 == b2 else f"{yk.tarih_kisa(b1)}–{yk.tarih_kisa(b2)}"


def kapsam_metni(ders_bas, ders_bit) -> str:
    if ders_bas is None:
        return "Tam gün"
    return f"{ders_bas}. ders" if ders_bas == ders_bit else f"{ders_bas}–{ders_bit}. ders"


def mazeret_onizle(b, girdi: dict, an: int) -> dict:
    """Önizleme (hiçbir şey yazmaz): bulunan/bulunamayan numaralar, kapsanan öğretim günü ve ders saati sayısı,
    kapsamdaki hücrelerden kaçının "yok" kayıtlı olduğu. Ders aralıklı girişte bütün öğrenciler aynı devreden
    olmalıdır (kural 25); değilse ValueError. Dönen sözlük `mazeret_yaz`a verilir."""
    nolar = girdi["nolar"]
    bulunan = yk.ogrenci_sirala(b.execute(
        f"SELECT * FROM ogrenci WHERE aktif = 1 AND okul_no IN ({','.join('?' * len(nolar))})", nolar).fetchall())  # fmt: skip
    var_olan = {o["okul_no"] for o in bulunan}
    bulunamayan = [n for n in nolar if n not in var_olan]
    if not bulunan:
        raise ValueError("Girilen numaralarla eşleşen etkin öğrenci yok.")
    bas, bit = date.fromisoformat(girdi["bas"]), date.fromisoformat(girdi["bit"])
    veri = Veri(b, bas, bit)
    gunler = [bas + timedelta(days=i) for i in range((bit - bas).days + 1)]
    subeler = sorted({o["sube"] for o in bulunan}, key=yk.sube_anahtari)
    devre = ""
    if girdi["ders_bas"] is not None:
        devreler = {veri.devre(g, s) for s in subeler for g in gunler if veri.plan(g).get("dersler")} - {None}
        if len(devreler) > 1:
            raise ValueError(ILETI_KARISIK_DEVRE)
        devre = next(iter(devreler), "")
    sahte = {"tur": girdi["tur"], "bas_tarih": girdi["bas"], "bit_tarih": girdi["bit"], "ders_bas": girdi["ders_bas"],
             "ders_bit": girdi["ders_bit"], "devre": devre}  # fmt: skip
    kapsanan_gun: set[date] = set()
    ders_saati = yok_kayitli = 0
    for o in bulunan:
        for g in gunler:
            tarih = g.isoformat()
            sube_devresi = veri.devre(g, o["sube"])
            for d in veri.dersler(g, o["sube"]):
                if not mazeret_kapsar(sahte, tarih, d["ders_no"], sube_devresi):
                    continue
                kapsanan_gun.add(g)
                ders_saati += 1
                yok_kayitli += int(veri.durum(tarih, o["sube"], d["ders_no"], o["id"]) == "yok")
    cok_devre = any(len({d[0] for d in veri.plan(g).get("dersler") or []}) > 1 for g in gunler)
    return {
        "girdi": {**girdi, "devre": devre},
        "ogrenci_idleri": [o["id"] for o in bulunan],
        "ogrenciler": [{"id": o["id"], "okul_no": o["okul_no"], "ad_soyad": yk.ad_soyad(o), "sube": o["sube"]} for o in bulunan],
        "bulunamayan": bulunamayan, "gun_sayisi": len(kapsanan_gun), "takvim_gunu": len(gunler), "ders_saati_sayisi": ders_saati,
        "yok_kayitli": yok_kayitli, "aralik": aralik_metni(girdi["bas"], girdi["bit"]),
        "kapsam": kapsam_metni(girdi["ders_bas"], girdi["ders_bit"]), "tur_adi": yk.MAZERET_TURLERI[girdi["tur"]],
        "dayanak_adi": yk.MAZERET_DAYANAKLARI[girdi["dayanak"]],
        "devre_adi": next((d[1] for g in gunler for d in veri.plan(g).get("dersler") or [] if d[0] == devre), "") if cok_devre else "",
    }  # fmt: skip


def mazeret_yaz(b, onizleme: dict, giren: str, an: int) -> int:
    """Önizlemesi onaylanan mazereti yazar (çağıran tek işlem içinde). Öğrenci başına bir satır; sayı döner.
    Yoklama kaydına ve panel düzeltmesine DOKUNMAZ."""
    g = onizleme["girdi"]
    idler = onizleme["ogrenci_idleri"]
    gecerli = {s["id"] for s in b.execute(
        f"SELECT id FROM ogrenci WHERE aktif = 1 AND id IN ({','.join('?' * len(idler))})", idler)}  # fmt: skip
    if gecerli != set(idler):
        raise ValueError("Öğrenci listesi değişti; mazereti yeniden girin.")
    b.executemany(
        "INSERT INTO yoklama_mazeret (ogrenci_id, bas_tarih, bit_tarih, ders_bas, ders_bit, devre, tur, dayanak, giren, olusturma) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(i, g["bas"], g["bit"], g["ders_bas"], g["ders_bit"], g["devre"] if g["ders_bas"] is not None else "", g["tur"],
          g["dayanak"], giren, an) for i in idler],  # fmt: skip
    )
    return len(idler)


def mazeret_iptal(b, mazeret_id: int, kim: str, an: int) -> bool:
    """Mazereti kaldırır: tür 'iptal' olur, dayanak boşalır; iz için yalnız giren/oluşturma/iptal eden/iptal zamanı
    kalır. Satır silinmez (kalıcı silme yalnız yıl sonu imhası ve "tümünü sil" ile)."""
    return bool(b.execute(
        "UPDATE yoklama_mazeret SET tur = 'iptal', dayanak = '', iptal_zamani = ?, iptal_eden = ? WHERE id = ? AND tur != 'iptal'",
        (an, kim, mazeret_id),
    ).rowcount)  # fmt: skip


def _mazeret_satiri(m, bugun: date) -> dict:
    iptal = m["tur"] == yk.MAZERET_IPTAL
    return {
        "id": m["id"], "ogrenci_id": m["ogrenci_id"], "okul_no": m["okul_no"], "ad_soyad": yk.ad_soyad(m), "sube": m["sube"],
        "aralik": aralik_metni(m["bas_tarih"], m["bit_tarih"]), "kapsam": kapsam_metni(m["ders_bas"], m["ders_bit"]),
        "iptal": iptal, "tur_adi": "" if iptal else yk.MAZERET_TURLERI.get(m["tur"], m["tur"]),
        "dayanak_adi": "" if iptal or not m["dayanak"] else yk.MAZERET_DAYANAKLARI.get(m["dayanak"], ""),
        "giren": m["giren"], "zaman": yk.an_yazi(m["olusturma"]),
        "iptal_metni": f"{m['iptal_eden']}, {yk.an_yazi(m['iptal_zamani'])}" if iptal else "",
        "durum": "kaldirildi" if iptal else "bitti" if m["bit_tarih"] < bugun.isoformat() else
                 "ileride" if m["bas_tarih"] > bugun.isoformat() else "gecerli",
    }  # fmt: skip


def mazeret_listesi(b, an: int) -> list[dict]:
    """Geçerli ve ilerideki kayıtlar + son 30 günde biten ya da kaldırılanlar (kaldırılan kayıt tür göstermez)."""
    bugun = yk.bugun(an)
    esik = (bugun - timedelta(days=MAZERET_LISTE_GUN)).isoformat()
    esik_an = an - MAZERET_LISTE_GUN * 86400
    satirlar = b.execute(
        "SELECT m.*, o.okul_no, o.ad, o.soyad, o.sube FROM yoklama_mazeret m JOIN ogrenci o ON o.id = m.ogrenci_id "
        "WHERE (m.tur != 'iptal' AND m.bit_tarih >= ?) OR (m.tur = 'iptal' AND m.iptal_zamani >= ?) "
        "ORDER BY m.tur = 'iptal', m.bas_tarih DESC, m.id DESC",
        (esik, esik_an),
    ).fetchall()
    return [_mazeret_satiri(m, bugun) for m in satirlar]
