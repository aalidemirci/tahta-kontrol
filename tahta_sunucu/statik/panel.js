/* Tahta Kontrol paneli 0.2.0 — kütüphane yok, derleme yok.
   Sayfa kancalarına göre bölümler: onay (tehlikeli işlem dialogu), pano (canlı durum,
   seçim, süzgeç, duyurucu), ayarlar (renk önizlemesi, logo), kopyala, dogrulama.
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
    e.appendChild(simge(simgeAdi));
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
    }
  };
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
          if (cumleler.length) {
            uyari.textContent = cumleler.join(" ");
            uyari.hidden = false;
          }
        }
        $("onay-baslik").textContent = tanim.baslik(n);
        $("onay-metin").textContent = tanim.metin;
        evet.setAttribute("form", form.id);
        evet.name = tanim.ad;
        evet.value = tanim.deger;
        evet.textContent = tanim.evet;
        diyalog.showModal();
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
    duyuru: "Duyuru ekranda", sorun: "Ekran yardımcısı yok", guncelleme: "Güncelleme var"
  };
  var DEGISIM = {
    acik: "açıldı", cevrimdisi: "çevrimdışı oldu", kilitli: "kilitlendi",
    duyuru: "duyuru gösteriyor", sorun: "ekran yardımcısını yitirdi"
  };

  function durumHesapla(t) {
    var birincil;
    if (!t.cevrimici) birincil = "cevrimdisi";
    else if (!t.ekran_bagli) birincil = "sorun";
    else if (t.duyuru_var) birincil = "duyuru";
    else if (t.kilitli) birincil = "kilitli";
    else birincil = "acik";
    var rozetler = [birincil];
    if ((birincil === "duyuru" || birincil === "sorun") && t.kilitli) rozetler.push("kilitli");
    if (t.surum && !t.guncel) rozetler.push("guncelleme");
    rozetler = rozetler.slice(0, 3);
    return {
      birincil: birincil,
      rozetler: rozetler,
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
      h.rozetler.forEach(function (d) { alan.appendChild(rozet(d, METIN[d], SIMGE[d])); });
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
        var h = durumHesapla(t);
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

  panoKur();
  onayKur();
  ayarlarKur();
  kopyalaKur();
  dogrulamaKur();
  iletiKur();
})();
