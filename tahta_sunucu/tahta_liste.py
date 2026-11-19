"""Tahtalar listesi (0.17.0, panel arayüzü 3. aşama): satırın durumu, rozetleri, birincil düğmesi, menü
pasiflikleri, konuma göre gruplama, `?durum=` süzgeci ve `/islem`'in hedef seçimi. FastAPI'siz, saf.

Durum kuralı TEK yerdedir: şablon (`tahtalar.html`) ve `/api/durum` aynı `liste` sözlüğünü kullanır;
`panel.js` kuralı yeniden hesaplamaz (0.16.0'daki `durumHesapla`'nın Python karşılığı).

Komut güvenliği: `islem_hedefi` dalları sıralıdır ve bir dal başarısız olunca başka dala DÜŞÜLMEZ
(`tek` bozuksa işaretli listeye geçilmez; hiçbir komut gitmez).
"""

from __future__ import annotations

import re

from . import hedef, metin
from .komut import KOMUT_ADI, KOMUT_OMRU

# ?durum= değerleri (sıra hapların sırasıdır) → etiket
SUZGECLER = {
    "acik": "Açık",
    "kilitli": "Kilitli",
    "duyuru": "Duyuruda",
    "sorun": "Ekran sorunu",
    "cevrimdisi": "Çevrimdışı",
    "guncelleme": "Güncelleme",
    "ariza": "Arıza bildirilen",
}
SEKMELER = ("genel", "program", "bakim", "bilgiler")

# `tek=<tur>:<id>` ile verilebilen komutlar. Duyuru kendi formundan, temizlik tahta sayfasındaki onaylı uçtan gider.
TEK_TURLERI = frozenset(KOMUT_ADI) - {"duyuru", "temizlik"}
# `kapsam=hepsi` yalnız kilitlemeye açıktır (TASLAK Karar 10); yıkıcı komut bütün tahtalara birden verilemez.
KAPSAM_HEPSI_TURLERI = frozenset({"kilitle"})
NOBETCI_ILETISI = "Komut gönderilmedi: Enter tuşu komut vermez; bir komut düğmesine basın."
_TEK = re.compile(r"([a-z_]{1,20}):([1-9][0-9]{0,9})")  # tek_coz fullmatch ile dener (sondaki satır sonu da reddedilir)

_SIMGE = {
    "acik": "s-acik", "cevrimdisi": "s-kapali", "kilitli": "s-kilit", "duyuru": "s-duyuru", "sorun": "s-sorun",
    "guncelleme": "s-guncel", "acil_ekranda": "s-sorun", "eski_ajan": "s-guncel",
}  # fmt: skip
_METIN = {
    "acik": "Açık", "cevrimdisi": "Çevrimdışı", "kilitli": "Kilitli", "duyuru": "Duyuru ekranda",
    "sorun": "Ekran yardımcısı yok", "guncelleme": "Güncelleme var",
    "acil_ekranda": "Acil yayın ekranda", "eski_ajan": "Eski ajan (yedek duyuru)",
}  # fmt: skip
_RENK = {"acil_ekranda": "sorun", "eski_ajan": "uyari"}  # belirtilmeyenin rengi kendi adıdır
_PROGRAM_KILIT_ADI = {"Teneffüs": "Teneffüs kilidi", "Öğle arası": "Öğle arası kilidi"}
_BIRINCIL_DUGME = {
    "sorun": ("tani", "Tanıla"),
    "duyuru": ("duyuru_kaldir", "Duyuruyu kaldır"),
    "kilitli": ("kilit_ac", "Kilidi aç"),
    "acik": ("kilitle", "Kilitle"),
}
EN_COK_DURUM_ROZETI = 4
EN_COK_EK_ROZET = 3


def _program_ajani_eski(t: dict, program_kilidi_acik: bool) -> bool:
    program = t.get("program") or {}
    return bool(program_kilidi_acik and t.get("cevrimici") and t.get("surum") and program.get("program_yetenegi") is False)


def _kilit_metni(t: dict) -> str:
    program = t.get("program") or {}
    if program.get("kilit_kaynak") != "program":
        return _METIN["kilitli"]
    ad = _PROGRAM_KILIT_ADI.get(program.get("neden"), "Program kilidi")
    return f"{ad} · {program['acilis']}" if program.get("acilis") else ad


def _ek_rozetler(t: dict, program_kilidi_acik: bool) -> list[dict]:
    """Altyapı (arıza, donanım) ve program/sınav/yoklama rozetleri; sırası 0.16.0 panosundakiyle aynıdır.
    `"cip": False` (0.18.0, eklemeli): rozet Bugün'deki tahta çipinin okunur metnine girmez (boş ders, programdan muaf)."""
    ek: list[dict] = []
    ariza = int(t.get("ariza_sayisi") or 0)
    if ariza > 0:
        ek.append({
            "d": "sorun", "m": f"{ariza} arıza" if ariza > 1 else "Arıza", "s": "s-sorun",
            "yol": f"/arizalar?durum=hepsi&tahta={t['id']}",
        })  # fmt: skip
    if t.get("donanim_degisti"):
        ek.append({"d": "uyari", "m": "Donanım değişti", "s": "s-sorun"})
    sinav = t.get("sinav")
    if sinav:
        m = "Sınav: giriş" if sinav.get("evre") == "giris" else "Sınav sürüyor"
        if t.get("surum") and t.get("sinav_yetenegi") is False:
            m += " · ajan güncellenmeli"
        ek.append({"d": "uyari", "m": m, "s": "s-onay"})
    if t.get("cevrimici") and t.get("yoklama_acik"):
        ek.append({"d": "duyuru", "m": "Yoklama alınıyor", "s": "s-onay"})
    program = t.get("program") or {}
    if program.get("bos_ders"):  # kapalı tahta boş dersin en sık nedenidir; çevrimdışında da çizilir
        ek.append({"d": "sorun", "m": f"Boş ders: {program['bos_ders']}", "s": "s-sorun", "cip": False})
    if program.get("muaf"):
        ek.append({"d": "bilgi", "m": "Programdan muaf", "s": "s-bilgi", "cip": False})
    if _program_ajani_eski(t, program_kilidi_acik) and t.get("guncel"):
        ek.append({"d": "bilgi", "m": "Ajan güncellenmeli", "s": "s-guncel"})
    return ek


UYANDIR_IPUCU = "çoğu cihazda çalışmaz"  # tahtanın donanımına ve BIOS ayarına bağlıdır


def _omur_metni(tur: str) -> str:
    """Çevrimdışı tahtaya verilen komutun akıbeti, komut ömründen (kural 8): kısa ömürlü düşer, uzun ömürlü bekler."""
    omur = KOMUT_OMRU[tur]
    return "bağlanınca çalışır" if omur >= 3600 else f"{omur // 60} dk bağlanmazsa düşer"


def _ipuclari(cevrimici: bool) -> dict[str, str]:
    """Etkin menü öğesinin alt yazısı. Çevrimdışı tahtada her etkin komut, bağlanmazsa ne olacağını söyler."""
    if cevrimici:
        return {}
    ipucu = {tur: _omur_metni(tur) for tur in ("kilitle", "kilit_ac", "duyuru_kaldir", "tani", "guncelle")}
    ipucu["uyandir"] = UYANDIR_IPUCU
    return ipucu


def durum_ozeti(t: dict, acil_suruyor: bool = False, program_kilidi_acik: bool = False) -> dict:
    """Tahta görünümünden (`web.tahta_gorunumu`) satırın `liste` sözlüğü.

    {"birincil", "durumlar" (süzgeç anahtarları, kesilmemiş), "rozetler" [{"d","m","s"[,"yol"]}],
     "dugme" {"tur","ad"} | {"yol","ad"} | None, "pasif" {tur: gerekçe}, "ipucu" {tur: alt yazı}, "oturum"}
    """
    cevrimici = bool(t.get("cevrimici"))
    if not cevrimici:
        birincil = "cevrimdisi"
    elif not t.get("ekran_bagli"):
        birincil = "sorun"
    elif t.get("duyuru_var"):
        birincil = "duyuru"
    elif t.get("kilitli"):
        birincil = "kilitli"
    else:
        birincil = "acik"

    anahtarlar = [birincil]
    # acil_gorundu "bir kez ekrana aldı" demektir; çevrimdışı tahtada "şu an ekranda" denmez.
    if acil_suruyor and t.get("acil_gorundu") and cevrimici:
        anahtarlar.insert(0, "acil_ekranda")
    elif acil_suruyor and cevrimici and not t.get("acil_yetenegi"):
        anahtarlar.append("eski_ajan")
    if birincil in ("duyuru", "sorun") and t.get("kilitli"):
        anahtarlar.append("kilitli")
    if t.get("surum") and not t.get("guncel"):
        anahtarlar.append("guncelleme")

    guncel_metni = "Ajan güncellenmeli" if _program_ajani_eski(t, program_kilidi_acik) else _METIN["guncelleme"]
    rozetler = []
    for a in anahtarlar[:EN_COK_DURUM_ROZETI]:
        m = _kilit_metni(t) if a == "kilitli" else guncel_metni if a == "guncelleme" else _METIN[a]
        rozet = {"d": _RENK.get(a, a), "m": m, "s": _SIMGE[a]}
        if a == "guncelleme" and m == _METIN["guncelleme"]:
            # V1 (0.18.0, varsayıldı; geri almak için bu alanı kaldırmak yeter): düz "Güncelleme var" rozeti tahta
            # LİSTESİNİN satırında çizilmez (hap sayısında, tahta sayfasında ve Bugün'de kalır). Alan eklemelidir:
            # `durumlar`, süzgeç ve /api/durum rozet listesi değişmez. "Ajan güncellenmeli" metni satırda kalır.
            rozet["liste"] = False
        rozetler.append(rozet)
    rozetler += _ek_rozetler(t, program_kilidi_acik)[:EN_COK_EK_ROZET]

    durumlar = [a for a in anahtarlar if a in SUZGECLER]
    if int(t.get("ariza_sayisi") or 0) > 0:
        durumlar.append("ariza")

    # Birincil düğme (ilk uyan): acil → yok; sınav → bağlantı; çevrimdışı → yok; sonra duruma göre tek komut.
    # Hiçbir durumda yıkıcı komut (kapat, yeniden başlat, temizlik) olmaz.
    dugme = None
    sinav = t.get("sinav")
    if acil_suruyor:
        dugme = None
    elif sinav:
        dugme = {"yol": f"/sinav/{sinav['sinav_id']}", "ad": "Sınavı aç"}
    elif birincil in _BIRINCIL_DUGME:
        tur, ad = _BIRINCIL_DUGME[birincil]
        dugme = {"tur": tur, "ad": ad}

    # Menü pasifliği yalnız KESİN etkisiz komutta; seçim çubuğunda hiçbir komut pasifleşmez.
    pasif: dict[str, str] = {}
    if cevrimici and not t.get("kilitli"):
        pasif["kilit_ac"] = "kilitli değil"
    if cevrimici and not t.get("duyuru_var"):
        pasif["duyuru_kaldir"] = "ekranda duyuru yok"
    if t.get("surum") and t.get("guncel"):
        pasif["guncelle"] = f"güncel ({t['surum']})"
    if cevrimici:
        pasif["uyandir"] = "tahta açık"
    else:
        pasif["kapat"] = "çevrimdışı"
        pasif["yeniden_baslat"] = "çevrimdışı"

    return {
        "birincil": birincil,
        "durumlar": durumlar,
        "rozetler": rozetler,
        "dugme": dugme,
        "pasif": pasif,
        "ipucu": _ipuclari(cevrimici),
        "oturum": (t.get("oturum") or "") if cevrimici else "",
    }


# Satır menüsü ve tahta sayfasının "Diğer" menüsü: sıra sözleşmedir (şartname §1.6).
#   bicim: "komut" (gönderir), "onay" (type="button" + data-onay; JS yoksa çalışmaz), "baglanti", "ayrac"
_MENU = (
    ("baglanti", "duyuru", "Duyuru gönder", None),
    ("komut", "kilitle", "Kilitle", None),
    ("komut", "kilit_ac", "Kilidi aç", None),
    ("komut", "duyuru_kaldir", "Duyuruyu kaldır", None),
    ("komut", "tani", "Tanılama çalıştır", None),
    ("komut", "guncelle", "Ajanı güncelle", None),
    ("komut", "uyandir", "Uzaktan aç (deneysel)", None),
    ("baglanti", "ayrinti", "Ayrıntı", None),
    ("baglanti", "bilgiler", "Bilgiler ve düzenle", "yonetici"),
    ("ayrac", "", "", None),
    ("onay", "kapat", "Kapat…", None),
    ("onay", "yeniden_baslat", "Yeniden başlat…", None),
)


def menu_ogeleri(t: dict, rol: str | None) -> list[dict]:
    """Satırın "⋯" menüsü: [{"bicim", "tur", "ad", "yol", "pasif" (gerekçe ya da ""), "alt" (alt yazı)}].

    Rolüne çizilmeyen öğe listeye hiç girmez (CSS ile gizlenmez). Pasif öğe komut değeri taşımaz.
    """
    pasif = (t.get("liste") or {}).get("pasif") or {}
    ipucu = (t.get("liste") or {}).get("ipucu") or {}
    ogeler = []
    for bicim, tur, ad, gereken_rol in _MENU:
        if gereken_rol and gereken_rol != rol:
            continue
        oge = {"bicim": bicim, "tur": tur, "ad": ad, "yol": "", "pasif": "", "alt": ""}
        if bicim == "baglanti":
            oge["yol"] = {
                "duyuru": f"/duyurular/yeni?tahta={t['id']}",
                "ayrinti": f"/tahta/{t['id']}",
                "bilgiler": f"/tahta/{t['id']}?sekme=bilgiler",
            }[tur]
        elif bicim in ("komut", "onay"):
            oge["pasif"] = pasif.get(tur, "")
            oge["alt"] = ipucu.get(tur, "")
        ogeler.append(oge)
    return ogeler


def _grup_adi(bina: str, kat) -> str:
    if bina and kat is not None:
        return f"{bina} · {hedef.kat_adi(kat)}"
    if bina:
        return bina
    if kat is not None:
        return hedef.kat_adi(kat)
    return "Konumu belirtilmemiş"


def gruplar(tahtalar: list[dict]) -> list[dict]:
    """Onaylı tahtaları konuma göre gruplar: [{"ad", "baslik" (çizilsin mi), "tahtalar"}].

    Grup sırası: bina (Türk abecesi; binasızlar sonda), sonra kat (belirtilmemiş sonda). Grup içi: derslik, ad.
    Tek grup varsa ve o da "Konumu belirtilmemiş" ise başlık çizilmez (düz liste).
    Her tahtaya `alt_satir` yazılır: derslik + nitelikler; bina ve kat grup başlığında yazdığı için yinelenmez.
    """
    kovalar: dict[tuple, dict] = {}
    for t in tahtalar:
        bina = " ".join(str(t.get("bina") or "").split())
        kat = t.get("kat")
        anahtar = (hedef.bina_anahtari(bina), kat)
        kova = kovalar.setdefault(anahtar, {"bina": bina, "kat": kat, "tahtalar": []})
        kova["tahtalar"].append(t)

    def sira(kova: dict) -> tuple:
        return (
            not kova["bina"],
            metin.tr_sirala_anahtari(kova["bina"]),
            kova["kat"] is None,
            kova["kat"] if kova["kat"] is not None else 0,
        )

    sonuc = []
    for kova in sorted(kovalar.values(), key=sira):
        kova["tahtalar"].sort(key=lambda t: (metin.tr_sirala_anahtari(t.get("derslik") or ""), metin.tr_sirala_anahtari(t.get("ad") or "")))
        sonuc.append({"ad": _grup_adi(kova["bina"], kova["kat"]), "baslik": True, "tahtalar": kova["tahtalar"]})
    if len(sonuc) == 1 and sonuc[0]["ad"] == "Konumu belirtilmemiş":
        sonuc[0]["baslik"] = False
    for grup in sonuc:
        for t in grup["tahtalar"]:
            nitelik = hedef.alanlar_metni({"bina": "", "kat": None, "duzeyler": ",".join(t.get("duzeyler") or []), "devre": t.get("devre")})
            t["alt_satir"] = " · ".join(p for p in (t.get("derslik") or "Derslik atanmadı", nitelik) if p)
    return sonuc


def sayilar(tahtalar: list[dict]) -> dict:
    """Hap sayıları (süzgeçten bağımsız, bütün onaylı tahtalar): {"hepsi", "cevrimici", <süzgeç anahtarı>…}."""
    sonuc = {"hepsi": len(tahtalar), "cevrimici": sum(1 for t in tahtalar if t.get("cevrimici"))}
    for anahtar in SUZGECLER:
        sonuc[anahtar] = sum(1 for t in tahtalar if anahtar in t["liste"]["durumlar"])
    return sonuc


def suzgec_coz(deger) -> str:
    """Doğrulanmış `?durum=`; bilinmeyen değer "" (Hepsi) olur ve HTML'e yazılmaz."""
    deger = str(deger or "")
    return deger if deger in SUZGECLER else ""


def tek_coz(deger) -> tuple[str, int] | None:
    """`"<tur>:<id>"` → (tur, id); biçim tutmazsa None. Türün ve kimliğin geçerliliğini `islem_hedefi` denetler."""
    es = _TEK.fullmatch(deger) if isinstance(deger, str) else None
    return (es.group(1), int(es.group(2))) if es else None


def islem_hedefi(form) -> dict:
    """`/islem` formundan hedef dalı. İlk uyan dal geçerlidir; hatada başka dala düşülmez.

    {"dal": "tek", "tur", "id"} | {"dal": "kapsam", "tur"} | {"dal": "liste", "tur", "idler"} | {"hata": ileti}
    Sıra: nöbetçi (her zaman hata) → tek → kapsam → liste.
    `tek` dalında formdaki `tur` ve `tahta` değerleri okunmaz. Veritabanı denetimi (onaylı mı, çevrimiçi mi)
    çağıranındır.
    """
    # Nöbetçi (tahtalar.html): seçim kutusunda Enter'ın örtük gönderimi formun ilk gönder düğmesini tıklar. O düğme
    # `nobetci` taşır; bu alan geldiyse başka hangi alan gelirse gelsin HİÇBİR komut verilmez.
    if form.getlist("nobetci"):
        return {"hata": NOBETCI_ILETISI}
    tekler = form.getlist("tek")
    kapsamlar = form.getlist("kapsam")
    if tekler:
        if len(tekler) > 1 or kapsamlar:
            return {"hata": "Geçersiz istek."}
        cozulen = tek_coz(tekler[0])
        if not cozulen:
            return {"hata": "Bilinmeyen işlem."}
        tur, kimlik = cozulen
        if tur == "temizlik":
            return {"hata": "Oturum temizliği tahta sayfasından başlatılır."}
        if tur not in TEK_TURLERI:
            return {"hata": "Bilinmeyen işlem."}
        if not hedef.kimlik_mi(kimlik) or kimlik < 1:
            return {"hata": "Tahta bulunamadı."}
        return {"dal": "tek", "tur": tur, "id": kimlik}
    if kapsamlar:
        if len(kapsamlar) > 1 or str(kapsamlar[0]) != "hepsi":
            return {"hata": "Geçersiz istek."}
        if form.getlist("tahta"):  # geniş hedef sessizce seçilmez
            return {"hata": "Geçersiz istek."}
        tur = str(form.get("tur", ""))
        if tur not in KAPSAM_HEPSI_TURLERI:
            return {"hata": "Bu işlem bütün tahtalara birden verilemez."}
        return {"dal": "kapsam", "tur": tur}
    tur = str(form.get("tur", ""))
    idler = [int(d) for d in form.getlist("tahta") if str(d).isdigit() and hedef.kimlik_mi(d)]
    if not idler:
        return {"hata": "Önce en az bir tahta seçin."}
    if tur not in KOMUT_ADI:
        return {"hata": "Bilinmeyen işlem."}
    return {"dal": "liste", "tur": tur, "idler": idler}


def guvenli_donus(deger, varsayilan: str = "/tahtalar") -> str:
    """Yalnız bu sitenin içindeki yol: "/" ile başlar, "//" ile başlamaz, ters eğik çizgi ve denetim karakteri
    içermez, en çok 200 karakter. Değilse `varsayilan`."""
    if not isinstance(deger, str) or not deger.startswith("/") or deger.startswith("//") or len(deger) > 200:
        return varsayilan
    if "\\" in deger or any(ord(h) < 32 or ord(h) == 127 for h in deger):
        return varsayilan
    return deger


def liste_yolu_mu(donus: str) -> bool:
    """Dönüş adresi tahta listesi mi (satır çapası `#t-<id>` yalnız orada anlamlıdır). 0.18.0: "/" Bugün'dür."""
    return donus.partition("#")[0].partition("?")[0] == "/tahtalar"


def sekme_coz(deger, rol: str | None, durum: str, yer: str = "") -> str:
    """Tahta sayfasının etkin sekmesi; yönlendirme yapılmaz, bilinmeyen değer Genel'e iner.

    Bekleyen tahtada yönetici doğrudan Bilgiler'i (onay formu) görür; idareciye Bilgiler, bekleyen tahtada
    Program çizilmez. `yer=temizlik` eski dönüş adresidir: sekme yoksa Bakım açılır.
    """
    deger = str(deger or "")
    yonetici = rol == "yonetici"
    if deger not in SEKMELER:
        if yer == "temizlik":
            return "bakim"
        return "bilgiler" if durum == "bekliyor" and yonetici else "genel"
    if deger == "bilgiler" and not yonetici:
        return "genel"
    if deger == "program" and durum != "onayli":
        return "genel"
    return deger
