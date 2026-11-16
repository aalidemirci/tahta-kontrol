"""Açılışta kilit (0.9.0, saha bulgusu G2).

Tahta açıldığında ya da tahtada oturum açıldığında, SUNUCUYA ULAŞILABİLİYORSA tahta kendiliğinden kilitlenir;
ulaşılamıyorsa açık kalır (kural 3: sunucu arızası dersi rehin almaz). Kararı sunucu verir: ajan durumunda
oturumun rastgele kimliğini (`oturum_no`) ve yaşını (`oturum_yasi_sn`, tahtanın açılış sayacıyla) bildirir.
Sunucu bir tahtada YENİ `oturum_no` görünce bir kez değerlendirir; aynı oturum ikinci kez kilitlenmez (kodla
ya da panelden açıldıktan sonra yeniden kilitlemez). Eski ajan alanı göndermez: davranış yok.

Uygulanmayan durumlar (`neden` döner, komut verilmez):
- Ayar kapalı ("Tahta açılınca kilitli başlasın", varsayılan açık).
- Kilit kodu belirlenmemiş: kodsuz kilit tahtayı panelden açılana kadar rehin alırdı.
- Oturum 120 sn'den yaşlı: ağ geç geldi, ders başlamış olabilir.
- Oturum sınıfı "etapadmin" (bakım) ya da oturum yok.
- Tahta zaten kilitli; acil yayın sürüyor; tahta sınav penceresinde.
- Program kilidi bu tahtayı yönetiyor (ders günü, son dersin bitişine kadar) ve tahta şu an derste ya da
  ders başlamak üzere: derste açık kararı program kilidinindir.

Program kilidinin yönettiği tahtada ders dışı saatte (ilk dersten önce, teneffüs, öğle arası) açılışta kilit
SÜRELİ PROGRAM KİLİDİ olarak verilir; tahtanın bir sonraki dersinin başında kendiliğinden açılır.
"""

from __future__ import annotations

from datetime import datetime

from . import acil, program, program_is, sinav, vt
from .komut import komut_ekle

YETENEK = "acilis_kilidi"
AYAR_ANAHTARI = "acilis_kilidi"
VARSAYILAN = True
EN_YASLI_OTURUM_SN = 120
KOMUT_OMRU_SN = 120
MUAF_SINIFLAR = ("etapadmin",)
ISTANBUL = program.ISTANBUL
ISLEM_ADI = "Açılışta kilit"


def ayar_al(b) -> bool:
    deger = vt.ayar_al(b, AYAR_ANAHTARI)
    return deger if isinstance(deger, bool) else VARSAYILAN


def yetenekli(tahta) -> bool:
    return YETENEK in acil.yetenekler(tahta)


def yeni_oturum(onceki: dict, durum: dict) -> str | None:
    """Durumda daha önce görülmemiş bir oturum kimliği varsa onu döndürür."""
    no = durum.get("oturum_no")
    if not isinstance(no, str) or not no or len(no) > 32:
        return None
    return None if no == (onceki or {}).get("oturum_no") else no


def neden_uygulanmaz(durum: dict, *, ayar_acik: bool, kod_var: bool) -> str | None:
    """Veritabanı gerektirmeyen denetimler; uygulanacaksa None."""
    if not ayar_acik:
        return "ayar kapalı"
    if not kod_var:
        return "kilit kodu belirlenmemiş"
    yas = durum.get("oturum_yasi_sn")
    if isinstance(yas, bool) or not isinstance(yas, (int, float)) or yas > EN_YASLI_OTURUM_SN:
        return "oturum yaşlı"
    oturum = durum.get("oturum") if isinstance(durum.get("oturum"), dict) else {}
    sinif = oturum.get("sinif") or "yok"
    if sinif in MUAF_SINIFLAR:
        return "yönetici oturumu"
    if sinif == "yok":
        return "oturum yok"
    if durum.get("kilitli"):
        return "zaten kilitli"
    return None


def program_karari(b, tahta, simdi: datetime) -> dict | None:
    """Program kilidi bu tahtayı şu an yönetiyor mu (program_is.calistir ile aynı uygunluk ölçütü)?

    None: yönetmiyor (kural kapalı, tahta muaf/istisnada/yeteneksiz, bugün ders yok, sınav günü ya da son
    dersin bitişinden sonra); açılışta kilit idare kilidi olarak uygulanır. Yönetiyorsa:
    - tahta şu an dersteyse ya da dersin başlamasına `EN_KISA_KILIT_SN`'den az kaldıysa {"neden": ...}
      (derste açık; kilit verilmez),
    - değilse (ilk dersten önce, teneffüs, öğle arası, dersi olmayan saat) {"veri": ...}: açılışta kilit
      PROGRAM KİLİDİ olarak verilir ve tahtanın bir sonraki dersinin başında kendiliğinden açılır. Süresiz
      idare kilidi verilmez: program açması onu açmaz, öğretmen kodu bilmiyorsa ders bölünürdü (0.9.0 incelemesi).
    """
    kural = program.ayar_kilit(b)
    if not kural.get("etkin") or not program_is.yetenekli(tahta) or tahta["program_muaf"]:
        return None
    an = int(simdi.timestamp())
    if program_is.istisnada(program_is.etkin_istisnalar(b, an), tahta["id"]):
        return None
    plan = program.gun_plani(b, simdi.date())  # haftalık düzen boşken tarihe özel çizelge de plan verir
    if not plan["dersler"] or program_is.sinav_penceresinde(plan, simdi):
        return None
    gun_bit = max(int(d[4].timestamp()) for d in plan["dersler"])
    if an >= gun_bit:
        return None
    gunluk_, programli = program_is.tahta_dersleri(b, plan["program_gunu"])
    dersli = [(int(d[3].timestamp()), int(d[4].timestamp()))
              for d in program_is.dersli_dersler(plan, tahta["id"], gunluk_, programli,
                                                 bool(kural.get("bos_saatte_kilitle", True)))]  # fmt: skip
    if any(bas <= an < bit for bas, bit in dersli):
        return {"neden": "program kilidi yönetiyor (derste açık)"}
    acilis = min((bas for bas, _ in dersli if bas > an), default=gun_bit)
    if acilis - an < program.EN_KISA_KILIT_SN:
        return {"neden": "program kilidi yönetiyor (ders başlamak üzere)"}
    if sinav.tahta_sinav_penceresinde(b, tahta["id"], an, sinav.PROGRAM_ONCESI_SN):
        return {"neden": "sınav penceresi yaklaşıyor"}
    araliklar = program.kilit_araliklari(plan, dersli)
    simdiki = next((a for a in araliklar if a["bas"] <= an < a["bit"]), None)
    neden = simdiki["neden"] if simdiki and simdiki["bit"] == acilis else program.NEDEN_DERS_YOK
    return {
        "veri": {"kaynak": "program", "bitis_sunucu": acilis, "neden": neden,
                 "acilis": datetime.fromtimestamp(acilis, ISTANBUL).strftime("%H:%M")},  # fmt: skip
        "isaret": (f"{simdi.date().isoformat()}|kilit|{datetime.fromtimestamp(simdiki['bas'], ISTANBUL):%H:%M}"
                   if simdiki else None),  # fmt: skip
    }


def degerlendir(b, tahta, onceki: dict, durum: dict, simdi: datetime) -> str | None:
    """Yeni oturumda bir kez çağrılır (ajan_bekle). Kilitlediyse komutu ve kaydı yazar ve "kilitlendi",
    uygulamadıysa nedenini, oturum yeni değilse (ya da eşzamanlı başka bir istek aynı oturumu zaten
    değerlendirdiyse) None döndürür."""
    no = yeni_oturum(onceki, durum)
    if no is None:
        return None
    an = int(simdi.timestamp())
    # "Bir kez" sözleşmesi eşzamanlı isteklerde de tutsun: oturum işareti tek yazılır (birincil anahtar).
    if b.execute(
        "INSERT OR IGNORE INTO program_isaret (tahta_id, anahtar, zaman) VALUES (?, ?, ?)",
        (tahta["id"], f"oturum|{no}", an),
    ).rowcount != 1:
        return None
    neden = neden_uygulanmaz(durum, ayar_acik=ayar_al(b), kod_var=bool(vt.ayar_al(b, "kilit_kodu")))
    if neden is None and acil.aktif(b, an) is not None:
        neden = "acil yayın sürüyor"
    if neden is None and sinav.tahta_sinav_penceresinde(b, tahta["id"], an):
        neden = "sınav penceresi"
    karar = program_karari(b, tahta, simdi) if neden is None else None
    if karar and "neden" in karar:
        neden = karar["neden"]
    if neden is not None:
        return neden
    if karar:
        komut_ekle(b, tahta["id"], "kilitle", karar["veri"], "sistem", KOMUT_OMRU_SN, simdi=an)
        if karar["isaret"]:  # program turu aynı aralık için ikinci kez kilit vermesin
            b.execute("INSERT OR IGNORE INTO program_isaret (tahta_id, anahtar, zaman) VALUES (?, ?, ?)",
                      (tahta["id"], karar["isaret"], an))  # fmt: skip
        ayrinti = f"{tahta['ad']}: oturum açıldı, program kilidiyle kilitlendi ({karar['veri']['acilis']}'de açılır)."
    else:
        komut_ekle(b, tahta["id"], "kilitle", {}, "sistem", KOMUT_OMRU_SN, simdi=an)
        ayrinti = f"{tahta['ad']}: oturum açıldı, tahta kilitlendi."
    vt.kayit_dus(b, "sistem", ISLEM_ADI, ayrinti)
    return "kilitlendi"
