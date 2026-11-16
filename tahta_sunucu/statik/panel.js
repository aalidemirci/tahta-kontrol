/* Tahta Kontrol paneli — kütüphane yok, derleme yok.
   Sayfa kancalarına göre bölümler: onay (tehlikeli işlem dialogu), pano (canlı durum,
   seçim, süzgeç, duyurucu, acil rozetleri), menu (açılır grupların kapanışı), sayac,
   duyuru formu (koşullu alanlar, hedef önizlemesi), acil (tür, şablon, teslim sayacı),
   yazdir, acil şablonları, ayarlar (renk önizlemesi, logo), kopyala, dogrulama,
   program (pano şeridi ve kart rozetleri pano bölümünde; tahta ızgarasında "Tümünü işaretle"),
   sinav (sınav sayfasının canlı salon durumu, sınavdaki tahtaya duyuru/kilit açma ek onayı,
   salon yoklamasında gelmeyen sayısı).
   Her bölüm JS kapalıyken de çalışan sayfayı yalnız iyileştirir.
   Metin her zaman textContent ile yazılır; innerHTML kullanılmaz. */
(function () {
  "use strict";

  var SVG = "http://www.w3.org/2000/svg";
  var $ = function (id) { return document.getElementById(id); };

  function simge(ad) {
    var svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("class", "simge");
    svg.setAttribute("aria-hidden", "true");
    var use = document.createElementNS(SVG, "use");
    use.setAttribute("href", "#" + ad);
    svg.appendChild(use);
    return svg;
  }

  function rozet(durum, metin, simgeAdi) {
    var e = document.createElement("span");
    e.className = "rozet";
    e.setAttribute("data-durum", durum);
    if (simgeAdi) e.appendChild(simge(simgeAdi));
    e.appendChild(document.createTextNode(metin));
    return e;
  }

  // Pano bölümü dialog açılınca duyuruları bekletmek için bu kancayı kullanır.
  var dialogKapaninca = [];

  /* ---- onay: tehlikeli işlem dialogu ------------------------------------------ */
  var ONAY = {
    kapat: {
      ad: "tur", deger: "kapat", evet: "Kapat",
      metin: "Açık çalışmalar kaybolabilir. Tahtayı kullanan kişi uyarılmaz.",
      baslik: function (n) { return n === null ? "Bu tahta kapatılsın mı?" : n + " tahta kapatılsın mı?"; }
    },
    yeniden_baslat: {
      ad: "tur", deger: "yeniden_baslat", evet: "Yeniden başlat",
      metin: "Açık çalışmalar kaybolabilir.",
      baslik: function (n) { return n === null ? "Bu tahta yeniden başlatılsın mı?" : n + " tahta yeniden başlatılsın mı?"; }
    },
    sil: {
      ad: "eylem", deger: "sil", evet: "Tahtayı kaldır",
      metin: "Ajanı sunucuya bağlanamaz; yeniden eklemek için kurulum gerekir.",
      baslik: function () { return "Bu tahta panelden kaldırılsın mı?"; }
    },
    acil_bitir: {
      ad: "eylem", deger: "bitir", evet: "Yayını bitir",
      metin: "Acil yayın bütün tahtalarda kaldırılacak.",
      baslik: function () { return "Acil yayın bitirilsin mi?"; }
    },
    plan_sil: {
      ad: "eylem", deger: "sil", evet: "Planı sil",
      metin: "Plan bir daha gösterilmez; yayındaki gösterim varsa ayrıca durdurun.",
      baslik: function () { return "Bu duyuru planı silinsin mi?"; }
    },
    grup_sil: {
      ad: "eylem", deger: "sil", evet: "Grubu sil",
      metin: "Grup silinir; tahtalar kalır.",
      baslik: function () { return "Bu grup silinsin mi?"; }
    },
    sablon_varsayilan: {
      ad: "eylem", deger: "varsayilan", evet: "Örneklere dön",
      metin: "Düzenlediğiniz bütün acil şablonu metinleri silinir.",
      baslik: function () { return "Şablonlar örneklere döndürülsün mü?"; }
    },
    zil_sil: {
      ad: "eylem", deger: "sil", evet: "Zil saatlerini sil",
      metin: "Ders saatleri ve takvim silinir; program kilidi kapatılır ve program kaynaklı kilitli tahtalar açılır. Derslik programları kalır.",
      baslik: function () { return "Zil saatleri silinsin mi?"; }
    },
    /* Sınav (Aşama 4) */
    sinav_bitir: {
      ad: "eylem", deger: "bitir", evet: "Sınavı bitir",
      metin: "Bütün salon tahtaları sınav kipinden hemen çıkar ve sayaç durur. Geri alınamaz.",
      baslik: function () { return "Sınav şimdi bitirilsin mi?"; }
    },
    kip_kaldir: {
      ad: "eylem", deger: "kaldir", evet: "Sınav kipini kaldır",
      metin: "Bu salonun tahtası sınav ekranından hemen çıkar ve bu sınavda geri gelmez. Salonun yoklaması panelden alınır.",
      baslik: function (n, ad) { return (ad ? ad + ": s" : "S") + "ınav kipi kaldırılsın mı?"; }
    },
    kodlar_yenile: {
      ad: "eylem", deger: "yenile", evet: "Kodları yenile",
      metin: "Bütün salonlara yeni gözetmen kodu üretilir; yazdırılmış eski fişler geçersiz olur.",
      baslik: function () { return "Gözetmen kodları yenilensin mi?"; }
    },
    kisisel_sil: {
      ad: "eylem", deger: "kisisel_sil", evet: "Kişisel veriyi sil",
      metin: "Öğrenci listesi, okul numaraları, yoklama işaretleri, gözetmen kodları ve adları silinir; salon başına sayılar kalır. İcmali yazdırdıysanız devam edin. Geri alınamaz.",
      baslik: function () { return "Kişisel veri şimdi silinsin mi?"; }
    },
    sinav_sil: {
      ad: "eylem", deger: "sil", evet: "Sınavı sil",
      metin: "Sınav, salonları ve öğrenci listesi tamamen silinir; icmal de üretilemez. Geri alınamaz.",
      baslik: function () { return "Sınav silinsin mi?"; }
    }
  };
  // Sınavdaki tahtaya duyuru / kilit açma: düz gönderim düğmeleridir; sınav sürüyorsa araya ek onay girer.
  var SINAV_EK_ONAY = {
    duyuru: {
      evet: "Duyuruyu gönder",
      metin: "Duyuru sınav ekranının üstünde görünür; süre dolunca ya da kapatılınca sınav ekranı geri gelir."
    },
    kilit_ac: {
      evet: "Kilidi aç",
      metin: "Kilidi açmak sınav ekranını kaldırmaz; sınav bitince tahta açık kalır. Sınav ekranını kaldırmak için sınav sayfasında “Sınav kipini kaldır” deyin."
    }
  };
  function sinavCumlesi(n, panoFormu) {
    if (!n) return "";
    return panoFormu ? "Seçili tahtalardan " + n + " tanesinde sınav sürüyor." : "Bu tahtada sınav sürüyor.";
  }
  var pano = null; // pano bölümü kurulunca doldurulur

  function onayKur() {
    var diyalog = $("onay-diyalog");
    var tetikler = document.querySelectorAll("button[data-onay]");
    if (!diyalog || !tetikler.length) return;
    // showModal yoksa tetikler hiçbir şey göndermez (type="button"): güvenli başarısızlık.
    if (typeof diyalog.showModal !== "function") return;
    var evet = $("onay-evet");
    var liste = $("onay-liste");
    var uyari = $("onay-uyari");

    diyalog.addEventListener("close", function () {
      diyalog.returnValue = "";
      var bekleyen = dialogKapaninca.slice();
      dialogKapaninca.length = 0;
      bekleyen.forEach(function (f) { f(); });
    });

    // Formdaki seçili tahtalardan kaçı sınav penceresinde (pano: /api/durum t.sinav; tahta sayfası: data-sinavdaki).
    function sinavdaki(form) {
      if (pano && form === pano.form) return pano.sinavdakiSayisi();
      return parseInt(form.getAttribute("data-sinavdaki") || "0", 10) || 0;
    }

    function ac(form, baslik, metin, ad, deger, evetMetni) {
      $("onay-baslik").textContent = baslik;
      $("onay-metin").textContent = metin;
      evet.setAttribute("form", form.id);
      evet.name = ad;
      evet.value = deger;
      evet.textContent = evetMetni;
      diyalog.showModal();
    }

    ["islem", "tahta-islem"].forEach(function (kimlik) {
      var form = $(kimlik);
      if (!form) return;
      form.addEventListener("submit", function (olay) {
        var gonderen = olay.submitter;
        if (!gonderen || gonderen === evet || gonderen.name !== "tur") return;
        var ek = SINAV_EK_ONAY[gonderen.value];
        if (!ek) return;
        var n = sinavdaki(form);
        if (!n) return;
        olay.preventDefault();
        liste.textContent = "";
        liste.hidden = true;
        uyari.textContent = "";
        uyari.hidden = true;
        ac(form, sinavCumlesi(n, kimlik === "islem") + " Devam edilsin mi?", ek.metin, "tur", gonderen.value, ek.evet);
      });
    });

    Array.prototype.forEach.call(tetikler, function (tetik) {
      tetik.addEventListener("click", function () {
        var tanim = ONAY[tetik.getAttribute("data-onay")];
        var form = tetik.form || tetik.closest("form");
        if (!tanim || !form || !form.id) return;
        var n = null;
        liste.textContent = "";
        liste.hidden = true;
        uyari.textContent = "";
        uyari.hidden = true;
        var sinavUyarisi = tanim.ad === "tur" ? sinavCumlesi(sinavdaki(form), !!(pano && form === pano.form)) : "";
        if (sinavUyarisi) {
          uyari.textContent = sinavUyarisi;
          uyari.hidden = false;
        }
        if (pano && form === pano.form) {
          var secili = pano.seciliKartlar();
          if (!secili.length) {
            pano.uyar("Önce en az bir tahta seçin.");
            return;
          }
          n = secili.length;
          secili.slice(0, 12).forEach(function (kart) {
            var li = document.createElement("li");
            li.textContent = kart.querySelector(".ad a").textContent;
            liste.appendChild(li);
          });
          if (secili.length > 12) {
            var fazla = document.createElement("li");
            fazla.textContent = "+" + (secili.length - 12) + " tahta daha";
            liste.appendChild(fazla);
          }
          liste.hidden = false;
          var cumleler = pano.etkiOzeti(secili);
          if (sinavUyarisi) cumleler.unshift(sinavUyarisi);
          if (cumleler.length) {
            uyari.textContent = cumleler.join(" ");
            uyari.hidden = false;
          }
        }
        ac(form, tanim.baslik(n, tetik.getAttribute("data-onay-ad") || ""), tanim.metin, tanim.ad, tanim.deger, tanim.evet);
      });
    });
  }

  /* ---- pano: canlı durum, seçim, süzgeç, duyurucu ----------------------------- */
  var SIMGE = {
    acik: "s-acik", cevrimdisi: "s-kapali", kilitli: "s-kilit",
    duyuru: "s-duyuru", sorun: "s-sorun", guncelleme: "s-guncel"
  };
  var METIN = {
    acik: "Açık", cevrimdisi: "Çevrimdışı", kilitli: "Kilitli",
    duyuru: "Duyuru ekranda", sorun: "Ekran yardımcısı yok", guncelleme: "Güncelleme var",
    acil_ekranda: "Acil yayın ekranda", eski_ajan: "Eski ajan (yedek duyuru)"
  };
  // Rozet anahtarı → renk (data-durum). Belirtilmeyen anahtarın rengi kendi adıdır.
  var RENK = { acil_ekranda: "sorun", eski_ajan: "uyari" };
  SIMGE.acil_ekranda = "s-sorun";
  SIMGE.eski_ajan = "s-guncel";
  var DEGISIM = {
    acik: "açıldı", cevrimdisi: "çevrimdışı oldu", kilitli: "kilitlendi",
    duyuru: "duyuru gösteriyor", sorun: "ekran yardımcısını yitirdi"
  };

  // Program kilidi rozeti: "Teneffüs kilidi · 10:40" (neden ve açılış /api/durum'daki tahta.program'dan).
  var PROGRAM_KILIT_ADI = { "Teneffüs": "Teneffüs kilidi", "Öğle arası": "Öğle arası kilidi" };
  // Sınav penceresindeki tahta (sunucunun hesabı, /api/durum t.sinav): "Sınav: giriş" / "Sınav sürüyor".
  function sinavRozeti(t) {
    if (!t.sinav) return null;
    var m = t.sinav.evre === "giris" ? "Sınav: giriş" : "Sınav sürüyor";
    if (t.surum && t.sinav_yetenegi === false) m += " · ajan güncellenmeli";
    return { d: "uyari", m: m, s: "s-onay" };
  }
  function programRozetleri(t, programKilidiAcik) {
    var p = t.program || {};
    var ek = [];
    var sr = sinavRozeti(t);
    if (sr) ek.push(sr);
    // Kapalı (çevrimdışı) tahta boş dersin en sık nedenidir; rozet o durumda da çizilir.
    if (p.bos_ders) ek.push({ d: "sorun", m: "Boş ders: " + p.bos_ders, s: "s-sorun" });
    if (p.muaf) ek.push({ d: "bilgi", m: "Programdan muaf", s: "s-bilgi" });
    // Sürümü eski ajanda "Güncelleme var" rozeti bu metne döner (guncelMetni); ayrı rozet yalnız o yoksa.
    if (programAjaniEski(t, programKilidiAcik) && t.guncel) {
      ek.push({ d: "bilgi", m: "Ajan güncellenmeli", s: "s-guncel" });
    }
    return ek;
  }
  function programAjaniEski(t, programKilidiAcik) {
    return !!(programKilidiAcik && t.cevrimici && t.surum && t.program && t.program.program_yetenegi === false);
  }
  function kilitMetni(t) {
    var p = t.program || {};
    if (p.kilit_kaynak !== "program") return METIN.kilitli;
    var ad = PROGRAM_KILIT_ADI[p.neden] || "Program kilidi";
    return p.acilis ? ad + " · " + p.acilis : ad;
  }

  function durumHesapla(t, acilSuruyor, programKilidiAcik) {
    var birincil;
    if (!t.cevrimici) birincil = "cevrimdisi";
    else if (!t.ekran_bagli) birincil = "sorun";
    else if (t.duyuru_var) birincil = "duyuru";
    else if (t.kilitli) birincil = "kilitli";
    else birincil = "acik";
    var rozetler = [birincil];
    // Acil yayın sürerken: ekrana aldıysa kırmızı rozet; ajan acil yeteneği bildirmiyorsa
    // yayını yedek duyuru olarak alır (kapatılamaz) ve güncellenmelidir.
    // acil_gorundu "bir kez ekrana aldı" demektir; çevrimdışı tahtada "şu an ekranda" denmez.
    if (acilSuruyor && t.acil_gorundu && t.cevrimici) rozetler.unshift("acil_ekranda");
    else if (acilSuruyor && t.cevrimici && !t.acil_yetenegi) rozetler.push("eski_ajan");
    if ((birincil === "duyuru" || birincil === "sorun") && t.kilitli) rozetler.push("kilitli");
    if (t.surum && !t.guncel) rozetler.push("guncelleme");
    rozetler = rozetler.slice(0, 4);
    return {
      birincil: birincil,
      rozetler: rozetler,
      kilitMetni: kilitMetni(t),
      guncelMetni: programAjaniEski(t, programKilidiAcik) ? "Ajan güncellenmeli" : METIN.guncelleme,
      ek: programRozetleri(t, programKilidiAcik).slice(0, 2),
      oturum: t.cevrimici ? (t.oturum || "") : "",
      alt: "Son görülme: " + t.son_gorulme + (t.surum ? " · ajan " + t.surum : "")
    };
  }

  function panoKur() {
    var form = $("islem");
    var ilk = $("ilk-veri");
    if (!form || !ilk) return;
    var panoVeri = {};
    try { panoVeri = JSON.parse(($("pano-veri") || {}).textContent || "{}"); } catch (e) { panoVeri = {}; }
    var kartlar = new Map();
    Array.prototype.forEach.call(form.querySelectorAll("article.tahta[data-id]"), function (k) {
      kartlar.set(String(k.getAttribute("data-id")), k);
    });
    var kutular = Array.prototype.slice.call(form.querySelectorAll('input[name="tahta"]'));
    var imzalar = new Map();
    var birinciller = new Map();
    var sonVeri = new Map();
    var secimSayisi = $("secim-sayisi");
    var canliBolge = $("canli-bolge");
    var canli = $("canli");
    var ozet = $("ozet");
    var hepsiniSec = $("hepsini-sec");
    var yenileBandi = $("yenile-bandi");
    var diyalog = $("onay-diyalog");
    var suzgec = "hepsi";
    var sonBasari = Date.now();
    var acilSuruyor = !!panoVeri.acil;
    var programKilidiAcik = !!panoVeri.program_kilidi;
    var programSeridi = $("pano-program");

    /* Duyurucu: yalnız değişimi, en çok 5 sn'de bir, birikenleri tek cümlede söyler. */
    var kuyruk = [];
    var sonDuyuru = 0;
    var duyuruZamani = null;
    function dialogAcik() { return !!(diyalog && diyalog.open); }
    function duyur(metin) {
      if (canliBolge) canliBolge.textContent = metin;
    }
    function kuyruguBosalt() {
      duyuruZamani = null;
      if (!kuyruk.length) return;
      if (dialogAcik()) { dialogKapaninca.push(kuyruguBosalt); return; }
      var gecen = Date.now() - sonDuyuru;
      if (gecen < 5000) { duyuruZamani = setTimeout(kuyruguBosalt, 5000 - gecen); return; }
      var gruplar = new Map();
      kuyruk.forEach(function (o) {
        if (!gruplar.has(o.olay)) gruplar.set(o.olay, []);
        var adlar = gruplar.get(o.olay);
        if (adlar.indexOf(o.ad) < 0) adlar.push(o.ad);
      });
      kuyruk = [];
      var cumleler = [];
      gruplar.forEach(function (adlar, olay) {
        var bas = adlar.slice(0, 3).join(", ");
        if (adlar.length > 3) bas += " ve " + (adlar.length - 3) + " tahta daha";
        cumleler.push(bas + " " + olay + ".");
      });
      duyur(cumleler.join(" "));
      sonDuyuru = Date.now();
    }
    // Gizliyken açılan bölge ekran okuyucuya güvenilir duyurulmaz; tek canlı bölge üzerinden bir kez söylenir.
    function yenileGoster() {
      if (!yenileBandi || !yenileBandi.hidden) return;
      yenileBandi.hidden = false;
      if (dialogAcik()) dialogKapaninca.push(function () { duyur(yenileBandi.textContent.trim()); });
      else duyur(yenileBandi.textContent.trim());
    }
    function kuyruga(ad, olay) {
      kuyruk.push({ ad: ad, olay: olay });
      if (!duyuruZamani) duyuruZamani = setTimeout(kuyruguBosalt, 0);
    }

    function kartiYaz(kart, h) {
      kart.setAttribute("data-durum", h.birincil);
      kart.setAttribute("data-durumlar", h.rozetler.join(" "));
      kart.classList.toggle("cevrimdisi", h.birincil === "cevrimdisi");
      var alan = kart.querySelector('[data-alan="rozetler"]');
      alan.textContent = "";
      h.rozetler.forEach(function (d) {
        var m = d === "kilitli" ? h.kilitMetni : d === "guncelleme" ? h.guncelMetni : METIN[d];
        alan.appendChild(rozet(RENK[d] || d, m, SIMGE[d]));
      });
      h.ek.forEach(function (r) { alan.appendChild(rozet(r.d, r.m, r.s)); });
      kart.querySelector('[data-alan="oturum"]').textContent = h.oturum;
      kart.querySelector('[data-alan="alt"]').textContent = h.alt;
    }

    function ciz(liste, ilkCizim) {
      var bilinmeyen = false;
      liste.forEach(function (t) {
        var id = String(t.id);
        var kart = kartlar.get(id);
        sonVeri.set(id, t);
        if (!kart) { bilinmeyen = true; return; }
        var h = durumHesapla(t, acilSuruyor, programKilidiAcik);
        var imza = JSON.stringify(h);
        if (imzalar.get(id) !== imza) {
          kartiYaz(kart, h);
          imzalar.set(id, imza);
        }
        var onceki = birinciller.get(id);
        if (!ilkCizim && onceki && onceki !== h.birincil && DEGISIM[h.birincil]) {
          kuyruga(t.ad, DEGISIM[h.birincil]);
        }
        birinciller.set(id, h.birincil);
      });
      if (bilinmeyen) yenileGoster();
      ozetGuncelle();
      suzgecUygula();
    }

    /* Program şeridi: şu anki ders, program kilidi rozeti, boş ders uyarısı sayısı. */
    var KILIT_ROZETI = {
      acik: ["acik", "s-kilit", function () { return "Program kilidi açık"; }],
      durduruldu: ["uyari", "s-onay", function (p) { return "Program kilidi durduruldu · bitiş " + (p.durduruldu_bitis || ""); }],
      kapali: ["bilgi", "s-kapali", function () { return "Program kilidi kapalı"; }]
    };
    var sonSerit = "";
    function seritYaz(p) {
      if (!programSeridi || !p) return;
      var imza = JSON.stringify([p.simdi, p.kilit, p.durduruldu_bitis, p.uyari_sayisi]);
      if (imza === sonSerit) return;
      sonSerit = imza;
      var simdi = programSeridi.querySelector('[data-alan="simdi"]');
      if (simdi) simdi.textContent = p.simdi || "";
      var kilit = programSeridi.querySelector('[data-alan="kilit"]');
      var k = KILIT_ROZETI[p.kilit] || KILIT_ROZETI.kapali;
      if (kilit) {
        kilit.textContent = "";
        kilit.appendChild(rozet(k[0], k[2](p), k[1]));
      }
      var uyari = programSeridi.querySelector('[data-alan="uyari"]');
      if (uyari) {
        uyari.hidden = !p.uyari_sayisi;
        uyari.querySelector("span").textContent = p.uyari_sayisi + " boş ders uyarısı";
      }
      var durdur = programSeridi.querySelector('[data-alan="durdur"]');
      // Açık menü kullanıcı seçim yaparken kapanmasın: yalnız kapalıyken gizlenir.
      if (durdur && !durdur.open) durdur.hidden = p.kilit !== "acik";
    }

    function ozetGuncelle() {
      if (!ozet) return;
      Array.prototype.forEach.call(ozet.querySelectorAll("button[data-suzgec]"), function (d) {
        var anahtar = d.getAttribute("data-suzgec");
        var sayi = 0;
        kartlar.forEach(function (kart) {
          var durumlar = (kart.getAttribute("data-durumlar") || "").split(" ");
          if (anahtar === "hepsi" || durumlar.indexOf(anahtar) >= 0) sayi++;
        });
        d.querySelector(".sayi").textContent = String(sayi);
      });
    }

    function gorunenKutular() {
      return kutular.filter(function (k) { return !k.closest("article.tahta").hidden; });
    }
    function seciliKartlar() {
      return kutular.filter(function (k) { return k.checked; }).map(function (k) { return k.closest("article.tahta"); });
    }
    function say() {
      var n = kutular.filter(function (k) { return k.checked; }).length;
      secimSayisi.textContent = n ? n + " tahta seçili" : "";
    }

    var suzgecBekliyor = false;
    function suzgecUygula() {
      // Onay dialogu açıkken seçim değişmez: dialogda sayılan ve listelenen tahtalar gönderilenle aynı kalır.
      // Süzgeç dialog kapanınca uygulanır (Vazgeç); onaylanırsa form zaten gönderilmiştir.
      if (dialogAcik()) {
        if (!suzgecBekliyor) {
          suzgecBekliyor = true;
          dialogKapaninca.push(function () { suzgecBekliyor = false; suzgecUygula(); });
        }
        return;
      }
      kartlar.forEach(function (kart) {
        var durumlar = (kart.getAttribute("data-durumlar") || "").split(" ");
        var gizle = suzgec !== "hepsi" && durumlar.indexOf(suzgec) < 0;
        kart.hidden = gizle;
        if (gizle) { // gizli kart komut almasın
          var k = kart.querySelector('input[name="tahta"]');
          if (k) k.checked = false;
        }
      });
      if (hepsiniSec) hepsiniSec.textContent = suzgec === "hepsi" ? "Tümünü seç" : "Görünenleri seç";
      say();
    }

    if (ozet) {
      ozet.hidden = false;
      ozet.addEventListener("click", function (olay) {
        var d = olay.target.closest("button[data-suzgec]");
        if (!d) return;
        suzgec = d.getAttribute("data-suzgec");
        Array.prototype.forEach.call(ozet.querySelectorAll("button[data-suzgec]"), function (b) {
          b.setAttribute("aria-pressed", b === d ? "true" : "false");
        });
        suzgecUygula();
      });
    }

    var sonTiklanan = null;
    kutular.forEach(function (k) {
      k.addEventListener("click", function (olay) {
        if (olay.shiftKey && sonTiklanan && sonTiklanan !== k) {
          var gorunen = gorunenKutular();
          var a = gorunen.indexOf(sonTiklanan);
          var b = gorunen.indexOf(k);
          if (a >= 0 && b >= 0) {
            gorunen.slice(Math.min(a, b), Math.max(a, b) + 1).forEach(function (x) { x.checked = k.checked; });
          }
        }
        sonTiklanan = k;
        say();
      });
      k.addEventListener("change", say);
    });

    if (hepsiniSec) {
      hepsiniSec.addEventListener("click", function () {
        var gorunen = gorunenKutular();
        var hepsi = gorunen.length > 0 && gorunen.every(function (k) { return k.checked; });
        gorunen.forEach(function (k) { k.checked = !hepsi; });
        say();
      });
    }

    /* Canlı gösterge ve yoklama */
    function iki(n) { return (n < 10 ? "0" : "") + n; }
    function canliYaz(basarili) {
      if (!canli) return;
      canli.textContent = "";
      if (basarili) {
        var s = new Date();
        canli.setAttribute("data-durum", "cevrimici");
        canli.appendChild(simge("s-acik"));
        canli.appendChild(document.createTextNode(
          "Canlı · son güncelleme " + iki(s.getHours()) + ":" + iki(s.getMinutes()) + ":" + iki(s.getSeconds())));
      } else {
        canli.setAttribute("data-durum", "sorun");
        canli.appendChild(simge("s-sorun"));
        canli.appendChild(document.createTextNode(
          "Bağlantı kesildi · son veri " + Math.round((Date.now() - sonBasari) / 1000) + " sn önce"));
      }
    }

    var zamanlayici = null;
    var yoklaniyor = false;
    function yokla() {
      clearTimeout(zamanlayici);
      zamanlayici = null;
      if (document.visibilityState === "hidden" || yoklaniyor) return;
      yoklaniyor = true;
      fetch("/api/durum", { credentials: "same-origin", cache: "no-store" }).then(function (y) {
        if (y.status === 401) { location.href = "/giris"; return null; }
        if (!y.ok) throw new Error(String(y.status));
        return y.json();
      }).then(function (v) {
        if (!v) return;
        sonBasari = Date.now();
        acilSuruyor = !!v.acil;
        if (v.program) {
          programKilidiAcik = v.program.kilit !== "kapali";
          seritYaz(v.program);
        }
        ciz(v.tahtalar || [], false);
        if (typeof v.bekleyen === "number" && v.bekleyen !== (panoVeri.bekleyen || 0)) yenileGoster();
        canliYaz(true);
      }).catch(function () {
        canliYaz(false);
      }).then(function () {
        yoklaniyor = false;
        if (document.visibilityState !== "hidden") zamanlayici = setTimeout(yokla, 4000);
      });
    }
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") {
        clearTimeout(zamanlayici);
        zamanlayici = null;
      } else {
        yokla();
      }
    });

    pano = {
      form: form,
      seciliKartlar: seciliKartlar,
      uyar: function (metin) {
        secimSayisi.textContent = metin;
        duyur(metin);
      },
      sinavdakiSayisi: function () {
        return seciliKartlar().filter(function (kart) {
          var t = sonVeri.get(String(kart.getAttribute("data-id")));
          return !!(t && t.sinav);
        }).length;
      },
      etkiOzeti: function (secili) {
        var oturumlu = 0;
        var cevrimdisi = 0;
        secili.forEach(function (kart) {
          var t = sonVeri.get(String(kart.getAttribute("data-id")));
          if (!t) return;
          if (t.oturum_acik) oturumlu++;
          if (!t.cevrimici) cevrimdisi++;
        });
        var c = [];
        if (oturumlu) c.push(oturumlu + " tahtada açık oturum var; derste kullanılıyor olabilir.");
        if (cevrimdisi) c.push(cevrimdisi + " tahta çevrimdışı; 2 dakika içinde bağlanmazsa komut düşer.");
        return c;
      }
    };

    var ilkListe = [];
    try { ilkListe = JSON.parse(ilk.textContent || "[]"); } catch (e) { ilkListe = []; }
    ciz(ilkListe, true);
    zamanlayici = setTimeout(yokla, 4000);
  }

  /* ---- ayarlar: renk önizlemesi ve logo ---------------------------------------- */
  function ayarlarKur() {
    var gorunum = $("gorunum-formu");
    var onizleme = $("onizleme");
    if (gorunum && onizleme) {
      var ana = $("ana_renk");
      var vurgu = $("vurgu_renk");
      var kullan = gorunum.querySelector('input[name="vurgu_kullan"]');
      var guncelle = function () {
        Array.prototype.forEach.call(gorunum.querySelectorAll("output[for]"), function (o) {
          var girdi = $(o.getAttribute("for"));
          if (girdi) o.textContent = girdi.value;
        });
        onizleme.style.setProperty("--o-ana", ana.value);
        onizleme.style.setProperty("--o-vurgu", kullan && kullan.checked ? vurgu.value : ana.value);
        onizleme.setAttribute("data-canli", "");
      };
      [ana, vurgu].forEach(function (g) { if (g) g.addEventListener("input", guncelle); });
      if (kullan) kullan.addEventListener("change", guncelle);
    }

    var dosya = document.querySelector('input[type="file"][name="logo"]');
    if (dosya) {
      var hata = $("logo-hata");
      var resim = $("logo-secilen");
      var cerceve = $("logo-secilen-cerceve");
      var adres = null;
      dosya.addEventListener("change", function () {
        if (adres) { URL.revokeObjectURL(adres); adres = null; }
        if (cerceve) cerceve.hidden = true;
        if (hata) { hata.hidden = true; hata.textContent = ""; hata.classList.remove("goster"); }
        dosya.setCustomValidity("");
        var f = dosya.files && dosya.files[0];
        if (!f) return;
        if (f.size > 256 * 1024) {
          var ileti = "Hata: Dosya 256 KB'tan büyük.";
          dosya.setCustomValidity(ileti);
          if (hata) { hata.textContent = ileti; hata.hidden = false; hata.classList.add("goster"); }
          return;
        }
        adres = URL.createObjectURL(f);
        if (resim) resim.src = adres;
        if (cerceve) cerceve.hidden = false;
      });
    }
  }

  /* ---- kopyala ------------------------------------------------------------------ */
  function kopyalaKur() {
    if (!navigator.clipboard || !window.isSecureContext) return;
    Array.prototype.forEach.call(document.querySelectorAll("button[data-kopyala]"), function (d) {
      var hedef = $(d.getAttribute("data-kopyala"));
      if (!hedef) return;
      d.hidden = false;
      var asil = d.textContent;
      var zaman = null;
      d.addEventListener("click", function () {
        navigator.clipboard.writeText(hedef.textContent).then(function () {
          d.textContent = "Kopyalandı";
          clearTimeout(zaman);
          zaman = setTimeout(function () { d.textContent = asil; }, 2000);
        }).catch(function () {});
      });
    });
  }

  /* ---- dogrulama: aria-invalid ve hata iletisi ---------------------------------- */
  function hataIletisi(alan) {
    var e = alan.nextElementSibling;
    while (e) {
      if (e.classList && e.classList.contains("hata-ileti")) return e;
      e = e.nextElementSibling;
    }
    return null;
  }
  function tanimlilar(alan) {
    return (alan.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean);
  }
  function dogrulamaKur() {
    document.addEventListener("invalid", function (olay) {
      var alan = olay.target;
      if (!alan || !alan.setAttribute) return;
      alan.setAttribute("aria-invalid", "true");
      var ileti = hataIletisi(alan);
      if (ileti && ileti.id) {
        var ler = tanimlilar(alan);
        if (ler.indexOf(ileti.id) < 0) { ler.push(ileti.id); alan.setAttribute("aria-describedby", ler.join(" ")); }
      }
    }, true);
    // Dosya alanında özel geçerlilik "change" dinleyicisinde temizlenir; "input" ondan önce gelir. İkisi de dinlenir.
    function temizle(olay) {
      var alan = olay.target;
      if (!alan || !alan.validity || alan.getAttribute("aria-invalid") !== "true" || !alan.validity.valid) return;
      alan.removeAttribute("aria-invalid");
      var ileti = hataIletisi(alan);
      if (ileti && ileti.id) {
        var ler = tanimlilar(alan).filter(function (x) { return x !== ileti.id; });
        if (ler.length) alan.setAttribute("aria-describedby", ler.join(" "));
        else alan.removeAttribute("aria-describedby");
      }
    }
    document.addEventListener("input", temizle);
    document.addEventListener("change", temizle);
  }

  /* ---- ileti: yönlendirme sonrası bölüm içinde çizilen iletiyi odakla ---------- */
  // Sayfa yüklenirken var olan role="status"/"alert" okunmaz; odaklanan bant okunur. Bağlantı parçası
  // (#ileti) zaten bandı gösterir; tarayıcı parçaya kaydırırken odağı sıfırlayabildiği için odak
  // yükleme bittikten sonra verilir.
  function iletiKur() {
    var bant = document.querySelector(".bant[data-odakla]");
    if (!bant) return;
    var odakla = function () { setTimeout(function () { bant.focus({ preventScroll: location.hash === "#ileti" }); }, 0); };
    if (document.readyState === "complete") odakla();
    else window.addEventListener("load", odakla, { once: true });
  }

  /* ---- menu: açılır gruplar (<details>) — JS'siz de çalışır; burada yalnız kapanış --- */
  function menuKur() {
    // Program şeridindeki "Program kilidini durdur" açılır menüsü de aynı biçimde kapanır.
    var gruplar = Array.prototype.slice.call(document.querySelectorAll("details.menu-grup, details.durdur-menu"));
    if (!gruplar.length) return;
    function kapat(haric) {
      gruplar.forEach(function (g) { if (g !== haric) g.open = false; });
    }
    gruplar.forEach(function (g) {
      g.addEventListener("toggle", function () { if (g.open) kapat(g); });
    });
    document.addEventListener("click", function (olay) {
      var icinde = olay.target.closest && olay.target.closest("details.menu-grup, details.durdur-menu");
      kapat(icinde || null);
    });
    document.addEventListener("keydown", function (olay) {
      if (olay.key !== "Escape") return;
      var acik = gruplar.filter(function (g) { return g.open; })[0];
      if (!acik) return;
      acik.open = false;
      acik.querySelector("summary").focus();
    });
  }

  /* ---- sayac: metin alanının altında "123/4000" ---------------------------------- */
  function sayacKur() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-sayac]"), function (s) {
      var alan = $(s.getAttribute("data-sayac"));
      if (!alan) return;
      var enCok = parseInt(alan.getAttribute("maxlength") || "0", 10);
      var asil = s.textContent;
      var yaz = function () {
        var n = alan.value.length;
        s.textContent = enCok ? n + "/" + enCok : String(n);
        if (!n) s.textContent = asil;
      };
      alan.addEventListener("input", yaz);
      yaz();
    });
  }

  /* Bir radyo grubunun seçili değeri ("" = seçili yok). */
  function secili(form, ad) {
    var r = form.querySelector('input[name="' + ad + '"]:checked');
    return r ? r.value : "";
  }

  /* ---- duyuru formu: koşullu alanlar, gönder metni, hedef önizlemesi -------------- */
  function duyuruFormuKur() {
    var form = $("duyuru-formu");
    if (!form) return;
    var kosullular = Array.prototype.slice.call(form.querySelectorAll(".kosullu[data-kosul]"));
    var gonder = $("duyuru-gonder");
    var onizleme = $("hedef-onizleme");
    var plan = !!form.querySelector('input[name="eylem"][value="kaydet"]');

    function kosullariUygula() {
      kosullular.forEach(function (k) {
        // İç içe koşul (Tekrarlı › Günlük/Haftalık): üstteki gizliyse içteki zaten görünmez.
        // Gizli alanlar yine gönderilir; sunucu yalnız seçili zamanlamanın alanlarını okur.
        k.hidden = secili(form, k.getAttribute("data-kosul")) !== k.getAttribute("data-deger");
      });
      if (gonder) {
        var hemen = secili(form, "zaman") === "hemen" && !plan;
        gonder.textContent = gonder.getAttribute(hemen ? "data-hemen" : "data-plan");
      }
    }

    // Formdan hedef sözlüğü: sunucudaki hedef.formdan ile aynı kural.
    function hedefTopla() {
      if (secili(form, "kime") === "tumu") return { tumu: true };
      var h = {};
      function sayilar(ad) {
        return Array.prototype.map.call(form.querySelectorAll('input[name="' + ad + '"]:checked'), function (x) { return parseInt(x.value, 10); });
      }
      function metinler(ad) {
        return Array.prototype.map.call(form.querySelectorAll('input[name="' + ad + '"]:checked'), function (x) { return x.value; });
      }
      [["hedef_tahta", "tahtalar"], ["grup", "gruplar"], ["kat", "kat"]].forEach(function (c) {
        var d = sayilar(c[0]);
        if (d.length) h[c[1]] = d;
      });
      ["bina", "duzey", "devre"].forEach(function (a) {
        var d = metinler(a);
        if (d.length) h[a] = d;
      });
      return h;
    }

    var ozet = onizleme && onizleme.querySelector('[data-alan="ozet"]');
    var liste = onizleme && onizleme.querySelector(".onizleme-liste");
    var sira = 0;
    var bekleme = null;
    function onizlemeYaz(simgeAdi, durum, parcalar) {
      var p = onizleme.querySelector("p");
      var eski = p.querySelector("svg");
      if (eski) p.replaceChild(simge(simgeAdi), eski);
      if (durum) onizleme.setAttribute("data-durum", durum); else onizleme.removeAttribute("data-durum");
      ozet.textContent = "";
      parcalar.forEach(function (x) {
        if (x && x.kalin) { var b = document.createElement("strong"); b.textContent = x.kalin; ozet.appendChild(b); }
        else ozet.appendChild(document.createTextNode(x));
      });
    }
    function onizle() {
      bekleme = null;
      if (!onizleme) return;
      var h = hedefTopla();
      if (!h.tumu && !Object.keys(h).length) {
        onizlemeYaz("s-bilgi", "uyari", ["Duyurunun hangi tahtalara gideceğini seçin."]);
        if (liste) liste.hidden = true;
        return;
      }
      var benim = ++sira;
      fetch("/api/hedef-onizleme?hedef=" + encodeURIComponent(JSON.stringify(h)), { credentials: "same-origin", cache: "no-store" })
        .then(function (y) {
          if (y.status === 401) { location.href = "/giris"; return null; }
          return y.json().then(function (v) { return { ok: y.ok, v: v }; });
        })
        .then(function (s) {
          if (!s || benim !== sira) return; // yalnız son isteğin yanıtı yazılır
          if (!s.ok) { onizlemeYaz("s-sorun", "uyari", [s.v.hata || "Seçim okunamadı."]); return; }
          var v = s.v;
          if (!v.sayi) onizlemeYaz("s-sorun", "uyari", ["Bu seçim şu an ", { kalin: "hiçbir tahtaya" }, " ulaşmıyor · " + v.ozet]);
          else onizlemeYaz("s-acik", "", ["Şu an ", { kalin: v.sayi + " tahtaya" }, " ulaşır · " + v.ozet]);
          if (liste) {
            var ul = liste.querySelector("ul");
            ul.textContent = "";
            (v.tahtalar || []).forEach(function (t) {
              var li = document.createElement("li");
              li.textContent = t.ad + (t.derslik ? " · " + t.derslik : "") + (t.cevrimici ? "" : " (çevrimdışı)");
              ul.appendChild(li);
            });
            liste.querySelector("summary").textContent = "Tahtalar (" + v.sayi + ")";
            liste.hidden = !v.sayi;
          }
        })
        .catch(function () {});
    }
    function gecikmeliOnizle() {
      clearTimeout(bekleme);
      bekleme = setTimeout(onizle, 300);
    }

    form.addEventListener("change", function (olay) {
      kosullariUygula();
      var ad = olay.target && olay.target.name;
      if (["kime", "bina", "kat", "duzey", "devre", "grup", "hedef_tahta"].indexOf(ad) >= 0) gecikmeliOnizle();
    });
    kosullariUygula();
    if (onizleme && !form.querySelector("fieldset[disabled]")) onizle();
  }

  /* ---- acil: tür kartı, şablon, onay metni, süren yayının sayacı ------------------ */
  function acilKur() {
    var form = $("acil-formu");
    if (form) {
      var onayMetni = $("acil-onay-metin");
      var gonder = $("acil-gonder");
      var baslik = $("acil-baslik");
      var metin = $("acil-metin");
      var turUygula = function () {
        var tur = secili(form, "tur");
        form.setAttribute("data-tur", tur);
        if (tur && onayMetni) onayMetni.textContent = onayMetni.getAttribute("data-" + tur);
        if (gonder) {
          gonder.textContent = tur ? gonder.getAttribute("data-" + tur) : "Yayını başlat";
          gonder.classList.toggle("uyari-dolu", tur === "tatbikat");
          gonder.classList.toggle("tehlike-dolu", tur !== "tatbikat");
        }
      };
      form.addEventListener("change", function (olay) {
        var t = olay.target;
        if (t.name === "tur") {
          turUygula();
          // Tür değişince eski onay geçersizdir: kişi yeni metni okuyup yeniden işaretler.
          var onay = form.querySelector('input[name="onay"]');
          if (onay) onay.checked = false;
        }
        if (t.name === "sablon" && t.checked && t.value) {
          baslik.value = t.getAttribute("data-baslik") || "";
          metin.value = t.getAttribute("data-metin") || "";
          metin.dispatchEvent(new Event("input"));
        }
      });
      turUygula();
    }

    var kutu = $("acil-aktif");
    if (!kutu) return;
    var kimlik = parseInt(kutu.getAttribute("data-acil-id"), 10);
    var teslim = $("acil-teslim");
    var kalan = $("acil-kalan");
    var bitti = $("acil-bitti");
    var zaman = null;
    function yokla() {
      zaman = null;
      if (document.visibilityState === "hidden") return;
      fetch("/api/durum", { credentials: "same-origin", cache: "no-store" }).then(function (y) {
        if (y.status === 401) { location.href = "/giris"; return null; }
        return y.ok ? y.json() : null;
      }).then(function (v) {
        if (!v) return;
        if (!v.acil || v.acil.id !== kimlik) {
          if (bitti) bitti.hidden = false;
          var dugme = kutu.querySelector("[data-onay]");
          if (dugme) dugme.hidden = true;
          return; // yayın bitti: yoklama durur
        }
        teslim.textContent = v.acil.teslim + "/" + v.acil.hedef;
        kalan.textContent = String(Math.ceil(v.acil.kalan_sn / 60));
        zaman = setTimeout(yokla, 4000);
      }).catch(function () { zaman = setTimeout(yokla, 4000); });
    }
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState !== "hidden" && !zaman && bitti && bitti.hidden) yokla();
    });
    zaman = setTimeout(yokla, 4000);
  }

  /* ---- rapor: Yazdır düğmesi (JS yoksa tarayıcının yazdırması kullanılır) --------- */
  function yazdirKur() {
    Array.prototype.forEach.call(document.querySelectorAll("button[data-yazdir]"), function (d) {
      d.hidden = false;
      d.addEventListener("click", function () { window.print(); });
    });
  }

  /* ---- ayarlar: acil şablonu satırını sil (adı boşaltır; kaydedince silinir) ------ */
  function sablonKur() {
    Array.prototype.forEach.call(document.querySelectorAll("button[data-sablon-sil]"), function (d) {
      d.hidden = false;
      d.addEventListener("click", function () {
        var satir = d.closest(".sablon-satiri");
        Array.prototype.forEach.call(satir.querySelectorAll("input, textarea"), function (g) { g.value = ""; });
        satir.hidden = true;
        var ileti = $("acil-sablon-bilgi");
        if (ileti) ileti.hidden = false;
      });
    });
  }

  /* ---- program ızgarası: "Tümünü işaretle" / "Temizle" (tahta sayfası) ----------- */
  function izgaraKur() {
    var form = $("tahta-program");
    if (!form) return;
    var araclar = form.querySelector(".izgara-araclari");
    if (!araclar) return;
    araclar.hidden = false;
    araclar.addEventListener("click", function (olay) {
      var d = olay.target.closest("button[data-izgara]");
      if (!d) return;
      var isaretle = d.getAttribute("data-izgara") === "hepsi";
      Array.prototype.forEach.call(form.querySelectorAll('table.secimli input[type="checkbox"]'), function (k) {
        k.checked = isaretle;
      });
    });
  }

  /* ---- sınav: canlı salon durumu, salon yoklamasında gelmeyen sayısı ---------------- */
  var EKRAN_ROZET = { giris: ["uyari", "s-onay"], suruyor: ["kilitli", "s-kilit"], yoklama: ["duyuru", "s-onay"] };
  // sinav.html'deki salon_durumu makrosuyla AYNI kural.
  function salonRozetleri(sl) {
    var r = [];
    if (sl.tahta_id) r.push(rozet(sl.cevrimici ? "acik" : "cevrimdisi", sl.cevrimici ? "Çevrimiçi" : "Çevrimdışı", sl.cevrimici ? "s-acik" : "s-kapali"));
    else r.push(rozet("bilgi", "Tahta yok", "s-bilgi"));
    if (sl.evre === "kaldirildi") r.push(rozet("uyari", "Sınav kipi kaldırıldı", "s-kapali"));
    else if (sl.tahta_id && (sl.evre === "giris" || sl.evre === "suruyor")) {
      var e = EKRAN_ROZET[sl.ekran] || ["sorun", "s-sorun"];
      r.push(rozet(e[0], sl.ekran_metni || "", e[1]));
    }
    if (sl.yoklama_alindi) {
      r.push(rozet("tamam", "Yoklama alındı (" + sl.yoklama_metni + ")", "s-tamam"));
      r.push(rozet(sl.gelmeyen ? "sorun" : "tamam", "Gelmeyen: " + sl.gelmeyen, ""));
    } else if (sl.evre === "suruyor" || sl.evre === "bitti") {
      r.push(rozet("bilgi", "Yoklama yok", "s-bilgi"));
    }
    if (sl.bitis_saat) {
      var b = document.createElement("span");
      b.className = "bitis";
      b.textContent = "Bitiş " + sl.bitis_saat + (sl.uzatma_dk ? " (+" + sl.uzatma_dk + " dk)" : "");
      r.push(b);
    }
    return r;
  }

  function sinavKur() {
    var gosterge = $("sinav-canli");
    if (!gosterge) return;
    var api = gosterge.getAttribute("data-api");
    var ilkEvre = gosterge.getAttribute("data-evre");
    var yenile = $("sinav-yenile");
    var zaman = null;
    var yoklaniyor = false;
    var sonBasari = Date.now();
    function iki(n) { return (n < 10 ? "0" : "") + n; }
    function gostergeYaz(basarili) {
      gosterge.textContent = "";
      var span = document.createElement("span");
      if (basarili) {
        var s = new Date();
        gosterge.setAttribute("data-durum", "cevrimici");
        gosterge.appendChild(simge("s-acik"));
        span.textContent = "Canlı · son güncelleme " + iki(s.getHours()) + ":" + iki(s.getMinutes()) + ":" + iki(s.getSeconds());
      } else {
        gosterge.setAttribute("data-durum", "sorun");
        gosterge.appendChild(simge("s-sorun"));
        span.textContent = "Bağlantı kesildi · son veri " + Math.round((Date.now() - sonBasari) / 1000) + " sn önce";
      }
      gosterge.appendChild(span);
    }
    function yaz(v) {
      (v.salonlar || []).forEach(function (sl) {
        var hucre = document.querySelector('tr[data-salon="' + sl.id + '"] [data-alan="durum"]');
        if (!hucre) return;
        var imza = JSON.stringify(sl);
        if (hucre.getAttribute("data-imza") === imza) return;
        hucre.setAttribute("data-imza", imza);
        hucre.textContent = "";
        salonRozetleri(sl).forEach(function (e) {
          hucre.appendChild(e);
          hucre.appendChild(document.createTextNode(" "));
        });
      });
      // Evre değişince işlem düğmeleri eskir: kendiliğinden yenileme yok (yazılan form kaybolmasın), bant çıkar.
      if (yenile && v.evre !== ilkEvre) {
        // Önce görünür, sonra metin: role="status" bölgesindeki değişiklik ekran okuyucuya duyurulsun.
        var alan = yenile.querySelector('[data-alan="evre"]');
        var acildi = yenile.hidden;
        yenile.hidden = false;
        if (alan) {
          if (acildi) alan.textContent = "";
          setTimeout(function () { alan.textContent = v.evre_adi || v.evre; }, acildi ? 50 : 0);
        }
      }
    }
    function yokla() {
      clearTimeout(zaman);
      zaman = null;
      if (document.visibilityState === "hidden" || yoklaniyor) return;
      yoklaniyor = true;
      var dur = false;
      fetch(api, { credentials: "same-origin", cache: "no-store" }).then(function (y) {
        if (y.status === 401) { location.href = "/giris"; dur = true; return null; }
        if (y.status === 404) { dur = true; return null; }
        if (!y.ok) throw new Error(String(y.status));
        return y.json();
      }).then(function (v) {
        if (!v) return;
        sonBasari = Date.now();
        yaz(v);
        gostergeYaz(true);
      }).catch(function () {
        gostergeYaz(false);
      }).then(function () {
        yoklaniyor = false;
        if (!dur && document.visibilityState !== "hidden") zaman = setTimeout(yokla, 4000);
      });
    }
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "hidden") { clearTimeout(zaman); zaman = null; } else yokla();
    });
    zaman = setTimeout(yokla, 4000);
  }

  function yoklamaSayaciKur() {
    var sayac = document.querySelector("[data-sayac-gelmedi]");
    var form = $("yoklama-formu");
    if (!sayac || !form) return;
    function say() {
      var n = form.querySelectorAll('input[name="gelmedi"]:checked').length;
      sayac.textContent = "Gelmeyen: " + n;
    }
    form.addEventListener("change", say);
    say();
  }

  panoKur();
  sinavKur();
  yoklamaSayaciKur();
  izgaraKur();
  menuKur();
  sayacKur();
  duyuruFormuKur();
  acilKur();
  yazdirKur();
  sablonKur();
  onayKur();
  ayarlarKur();
  kopyalaKur();
  dogrulamaKur();
  iletiKur();
})();
