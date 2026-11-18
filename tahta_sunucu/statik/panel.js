/* Tahta Kontrol paneli — kütüphane yok, derleme yok.
   Sayfa kancalarına göre bölümler: onay (tehlikeli işlem dialogu), pano (canlı durum,
   seçim, süzgeç, duyurucu, acil rozetleri), menu (açılır grupların kapanışı), sayac,
   duyuru formu (koşullu alanlar, hedef önizlemesi), acil (tür, şablon, teslim sayacı),
   yazdir, acil şablonları, ayarlar (renk önizlemesi, logo), kopyala, dogrulama,
   program (pano şeridi ve kart rozetleri pano bölümünde; tahta ızgarasında "Tümünü işaretle"),
   sinav (sınav sayfasının canlı salon durumu, sınavdaki tahtaya duyuru/kilit açma ek onayı,
   salon yoklamasında gelmeyen sayısı), yoklama (Aşama 5: "e-Okul'a işlendi" kutusunun kendiliğinden
   gönderimi, yok sayacı, icmal metnini kopyalama ve yazdırma, yoklama silme onayı, panoda "Yoklama alınıyor"),
   altyapı (Aşama 6: panoda "Arıza" ve "Donanım değişti" rozetleri; th[data-sirala] tablolarında sütun sıralama).
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
      ad: "eylem", deger: "sil", evet: "Zil düzenini sil",
      metin: "Bütün çizelgeler, haftalık düzen, tarihe özel çizelgeler ve takvim silinir; program kilidi kapatılır ve program kaynaklı kilitli tahtalar açılır. Derslik programları kalır.",
      baslik: function () { return "Bütün zil düzeni silinsin mi?"; }
    },
    /* Zil düzenleyici (0.10.0): yalnız kullanılmayan çizelgede görünür */
    cizelge_sil: {
      ad: "eylem", deger: "sil", evet: "Çizelgeyi sil",
      metin: "Çizelge ve satırları silinir. Hiçbir günde kullanılmadığı için ders saatleri değişmez.",
      baslik: function (n, ad) { return (ad ? "“" + ad + "” çizelgesi" : "Bu çizelge") + " silinsin mi?"; }
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
    /* Ders yoklaması (Aşama 5). dogrula: form önce tarayıcıda doğrulanır (gerekçe zorunlu). */
    yoklama_sil: {
      ad: "eylem", deger: "sil", evet: "Yoklamayı sil", dogrula: true,
      metin: "Bu ders saatinin yoklaması, işaretleri ve değişiklik geçmişi silinir. Geri alınamaz.",
      baslik: function () { return "Bu yoklama silinsin mi?"; }
    },
    /* Oturum temizliği (K7) */
    temizlik: {
      ad: "eylem", deger: "temizle", evet: "Temizle",
      metin: "Tahta kullanılıyorsa 60 saniyelik uyarı çıkar ve kullanan kişi vazgeçebilir. Açık pencereler kapanır, tarayıcı oturumları ve çerezler silinir; dosyalara, geçmişe ve kayıtlı parolalara dokunulmaz.",
      baslik: function () { return "Bu tahtada oturum temizliği yapılsın mı?"; }
    },
    /* USB anahtar (0.11.0): anlık ve geri alınmaz */
    usb_iptal: {
      ad: "eylem", deger: "iptal", evet: "Anahtarı iptal et",
      metin: "Bu anahtar hemen geçersiz olur ve geri alınamaz. Bu anahtarla açılmış yoklama ekranları da kapanır.",
      baslik: function (n, ad) { return (ad ? ad + " a" : "A") + "nahtarı iptal edilsin mi?"; }
    },
    /* Mazeret/izin (0.14.0): kayıt silinmez; tür ve dayanak boşaltılır, yoklamadaki asıl durum geri görünür */
    mazeret_kaldir: {
      ad: "eylem", deger: "iptal", evet: "Mazereti kaldır",
      metin: "Kayıt kaldırılır; yoklamada yok yazılan saatler yeniden mazeretsiz görünür. Öğretmenin yoklama kaydı değişmez.",
      baslik: function (n, ad) { return (ad ? ad + ": bu" : "Bu") + " mazeret/izin kaydı kaldırılsın mı?"; }
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

    function formKimligi(form) {
      return form.getAttribute("id") || "";
    }

    function ac(form, baslik, metin, ad, deger, evetMetni) {
      $("onay-baslik").textContent = baslik;
      $("onay-metin").textContent = metin;
      // Formun "id" özelliği kullanılmaz: formda name="id" alanı varsa özellik o alanı döndürür (adlandırılmış öğe gölgelemesi).
      evet.setAttribute("form", formKimligi(form));
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
        if (!tanim || !form || !formKimligi(form)) return;
        // Onay düğmesi formnovalidate'tir; zorunlu alanı olan işlemde form önce burada doğrulanır.
        if (tanim.dogrula && form.reportValidity && !form.reportValidity()) return;
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
    // Ders yoklaması (A5): ajanın bildirdiği bayrak; şube, öğretmen, öğrenci bilgisi gelmez.
    if (t.cevrimici && t.yoklama_acik) ek.push({ d: "duyuru", m: "Yoklama alınıyor", s: "s-onay" });
    // Kapalı (çevrimdışı) tahta boş dersin en sık nedenidir; rozet o durumda da çizilir.
    if (p.bos_ders) ek.push({ d: "sorun", m: "Boş ders: " + p.bos_ders, s: "s-sorun" });
    if (p.muaf) ek.push({ d: "bilgi", m: "Programdan muaf", s: "s-bilgi" });
    // Sürümü eski ajanda "Güncelleme var" rozeti bu metne döner (guncelMetni); ayrı rozet yalnız o yoksa.
    if (programAjaniEski(t, programKilidiAcik) && t.guncel) {
      ek.push({ d: "bilgi", m: "Ajan güncellenmeli", s: "s-guncel" });
    }
    return ek;
  }
  // A6: süren (açık + inceleniyor) arıza sayısı ve donanım kimliği değişimi; sunucunun /api/durum alanlarından.
  function altyapiRozetleri(t) {
    var ek = [];
    if (t.ariza_sayisi > 0) ek.push({ d: "sorun", m: t.ariza_sayisi > 1 ? t.ariza_sayisi + " arıza" : "Arıza", s: "s-sorun" });
    if (t.donanim_degisti) ek.push({ d: "uyari", m: "Donanım değişti", s: "s-sorun" });
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
      ek: altyapiRozetleri(t).concat(programRozetleri(t, programKilidiAcik)).slice(0, 3),
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
  // data-kopyala-yedek: pano erişimi yoksa ya da reddedilirse metin seçili hâle getirilir ve
  // "Ctrl+C ile kopyalayın" denir (yoklama icmali). Yedeksiz düğme pano yoksa gizli kalır (eski davranış).
  function metniSec(hedef) {
    var kutu = hedef.closest("details");
    if (kutu) kutu.open = true;
    hedef.focus();
    if (typeof hedef.select === "function") { hedef.select(); return; } // textarea (aktarma istemi)
    var secim = window.getSelection();
    var aralik = document.createRange();
    aralik.selectNodeContents(hedef);
    secim.removeAllRanges();
    secim.addRange(aralik);
  }
  function kopyalaKur() {
    var pano = !!(navigator.clipboard && window.isSecureContext);
    Array.prototype.forEach.call(document.querySelectorAll("button[data-kopyala]"), function (d) {
      var hedef = $(d.getAttribute("data-kopyala"));
      var yedek = d.hasAttribute("data-kopyala-yedek");
      if (!hedef || (!pano && !yedek)) return;
      d.hidden = false;
      var asil = d.textContent;
      var ileti = $("kopyala-ileti");
      var zaman = null;
      function bildir(metin) {
        if (!ileti) return;
        ileti.textContent = metin;
        ileti.hidden = !metin;
      }
      function elle() {
        metniSec(hedef);
        bildir("Metin seçildi: Ctrl+C ile kopyalayın.");
      }
      d.addEventListener("click", function () {
        if (!pano) { elle(); return; }
        navigator.clipboard.writeText(typeof hedef.value === "string" ? hedef.value : hedef.textContent).then(function () {
          d.textContent = "Kopyalandı";
          bildir("");
          clearTimeout(zaman);
          zaman = setTimeout(function () { d.textContent = asil; }, 2000);
        }).catch(function () { if (yedek) elle(); });
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

  /* ---- kabuk: dar ekranda yan menü çekmecesi (0.15.0) --------------------------------
     JS'siz de çalışır: <a href="#menu"> çekmeceyi :target ile açar, #icerik kapatır. Burada sınıfla açılır
     (adrese parça yazılmaz), arkadaki sayfa inert olur, Esc kapatır ve odak açan düğmeye döner.
     Kip (çekmece / sabit) yalnız stil.css'tedir: --kb-kip okunur, genişlik eşiği burada yinelenmez. */
  function kabukKur() {
    var menu = $("menu");
    if (!menu || !menu.classList.contains("yan-menu")) return; // kabuksuz sayfa (giriş, ilk kurulum)
    // Çekmece açıkken arkada kalanlar (inert): Tab çekmecenin dışına çıkmaz. Onay diyaloğu body'nin çocuğudur, kapsam dışı.
    var arka = Array.prototype.slice.call(document.querySelectorAll("main#icerik, .ust-cubuk, .alt-cubuk, a.atla"));
    var acanlar = Array.prototype.slice.call(document.querySelectorAll("a.menu-ac"));
    var kapatan = menu.querySelector(".yan-kapat");
    var perde = document.querySelector(".perde");
    var sonTetik = null;
    function cekmeceMi() {
      return getComputedStyle(document.body).getPropertyValue("--kb-kip").trim() !== "sabit";
    }
    function acikMi() { return menu.classList.contains("acik"); }
    function isaretle(acik) {
      arka.forEach(function (o) { o.inert = acik; });
      acanlar.forEach(function (a) { a.setAttribute("aria-expanded", acik ? "true" : "false"); });
    }
    // Liste sığmayıp kayıyorsa (kısa pencere, telefon çekmecesi) etkin öğe görünür alana gelir; sayfa kaymaz
    // (yan menü sabit konumludur, en yakın kaydırma kutusu listenin kendisidir).
    function etkiniGoster() {
      var etkin = menu.querySelector('.yan-gezinme a[aria-current="page"]') || menu.querySelector(".yan-gezinme li[data-icinde] > a");
      if (etkin && etkin.scrollIntoView) etkin.scrollIntoView({ block: "nearest" });
    }
    function ac(tetik) {
      if (!cekmeceMi() || acikMi()) return;
      menu.classList.add("acik");
      isaretle(true);
      sonTetik = tetik;
      (kapatan || menu).focus();
      etkiniGoster();
    }
    function kapat(odakGeri) {
      if (!acikMi()) return;
      menu.classList.remove("acik");
      isaretle(false);
      if (!odakGeri) return;
      var hedef = sonTetik && sonTetik.getClientRects().length ? sonTetik : $("icerik");
      if (hedef) hedef.focus();
    }
    acanlar.forEach(function (a) {
      a.setAttribute("role", "button");
      a.setAttribute("aria-expanded", "false");
      a.addEventListener("click", function (olay) { olay.preventDefault(); ac(a); });
      a.addEventListener("keydown", function (olay) { // role="button": Boşluk da açar
        if (olay.key === " " || olay.key === "Spacebar") { olay.preventDefault(); ac(a); }
      });
    });
    [kapatan, perde].forEach(function (o) {
      if (o) o.addEventListener("click", function (olay) {
        if (!acikMi()) return; // JS'siz açılmış (:target) çekmecede bağlantı kendi işini görür
        olay.preventDefault();
        kapat(true);
      });
    });
    document.addEventListener("keydown", function (olay) {
      if (olay.key === "Escape" && acikMi()) kapat(true); // onay diyaloğu açıkken tarayıcı Esc'yi diyaloğa verir
    });
    window.addEventListener("resize", function () { if (!cekmeceMi()) kapat(false); });
    // Çekmeceden bir sayfaya gidilip Geri'ye basılınca sayfa geri/ileri önbelleğinden çekmece açık ve içerik
    // inert olarak dönmesin: ayrılırken (ve önbellekten dönerken) çekmece kapatılır.
    window.addEventListener("pagehide", function () { kapat(false); });
    window.addEventListener("pageshow", function (olay) { if (olay.persisted) kapat(false); });
    etkiniGoster();
    // #menu parçasıyla gelinirse (JS'siz açılmış adres yenilendi, adres elle yazıldı) çekmece sınıfla açılır;
    // :target'a bağlı kalırsa Esc ve perde onu kapatamaz.
    function parcadanAc() {
      if (location.hash !== "#menu") return;
      location.replace("#icerik"); // :target menüden alınır (replaceState tek başına :target'ı değiştirmez)
      history.replaceState(null, "", location.pathname + location.search);
      ac(null);
    }
    window.addEventListener("hashchange", parcadanAc);
    parcadanAc();
  }

  /* ---- menu: açılır gruplar (<details>) — JS'siz de çalışır; burada yalnız kapanış --- */
  function menuKur() {
    // Program şeridindeki "Program kilidini durdur" açılır menüsü de aynı biçimde kapanır.
    var gruplar = Array.prototype.slice.call(document.querySelectorAll("details.durdur-menu"));
    if (!gruplar.length) return;
    function kapat(haric) {
      gruplar.forEach(function (g) { if (g !== haric) g.open = false; });
    }
    gruplar.forEach(function (g) {
      g.addEventListener("toggle", function () { if (g.open) kapat(g); });
    });
    document.addEventListener("click", function (olay) {
      var icinde = olay.target.closest && olay.target.closest("details.durdur-menu");
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

  /* ---- USB anahtar: indirme bağlantısı tek kullanımlıktır (0.11.0) ----------------
     İlk tıklamadan sonra bağlantı devre dışı kalır: ikinci tıklama sayfadan ayrılıp bir kez
     gösterilen PIN'i kaybettirmesin. JS yoksa bağlantı düz çalışır; sunucu ikinci isteği iletiyle
     panele yönlendirir. */
  function tekIndirmeKur() {
    Array.prototype.forEach.call(document.querySelectorAll("a[data-tek-indirme]"), function (a) {
      a.addEventListener("click", function () {
        setTimeout(function () {
          a.removeAttribute("href");
          a.setAttribute("aria-disabled", "true");
          var not = $(a.getAttribute("data-tek-indirme"));
          if (not) not.hidden = false;
        }, 0);
      });
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

  /* ---- ders yoklaması (A5): "e-Okul'a işlendi" kutusu kendiliğinden gönderilir; yok sayacı --- */
  function otomatikGonderKur() {
    Array.prototype.forEach.call(document.querySelectorAll("input[data-otomatik-gonder]"), function (k) {
      var form = k.form;
      if (!form) return;
      // JS varsa yedek "Kaydet" düğmesi gizlenir; kutu değişince form gönderilir.
      Array.prototype.forEach.call(form.querySelectorAll("[data-js-gizle]"), function (d) { d.hidden = true; });
      k.addEventListener("change", function () {
        if (form.requestSubmit) form.requestSubmit(); else form.submit();
      });
    });
  }
  // Panelden yoklama: üstteki seçim (ders saati, öğretmen…) "Listeyi getir" denmeden değişirse kayıt
  // formu eski değerleri gönderirdi; Kaydet kapatılır ve uyarı gösterilir.
  function secimDegisimiKur() {
    Array.prototype.forEach.call(document.querySelectorAll("form[data-secim-formu]"), function (secim) {
      var kayit = document.getElementById(secim.getAttribute("data-secim-formu"));
      if (!kayit) return;
      var ilk = new URLSearchParams(new FormData(secim)).toString();
      secim.addEventListener("change", function () {
        var degisti = new URLSearchParams(new FormData(secim)).toString() !== ilk;
        Array.prototype.forEach.call(kayit.querySelectorAll("button.ana"), function (d) {
          if (degisti) { if (!d.disabled) { d.disabled = true; d.setAttribute("data-secim-kapatti", ""); } }
          else if (d.hasAttribute("data-secim-kapatti")) { d.disabled = false; d.removeAttribute("data-secim-kapatti"); }
        });
        var uyari = kayit.querySelector("[data-secim-uyari]");
        if (uyari) uyari.hidden = !degisti;
      });
    });
  }
  function yokSayaciKur() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-sayac-yok]"), function (sayac) {
      var form = sayac.closest("form");
      if (!form) return;
      var toplam = form.querySelectorAll('input[name="yok"]').length;
      function say() {
        var n = form.querySelectorAll('input[name="yok"]:checked').length;
        sayac.textContent = "Yok: " + n + " · Derste: " + (toplam - n) + "/" + toplam;
      }
      form.addEventListener("change", say);
      say();
    });
  }

  /* ---- sıralama (A6 envanter): th[data-sirala] başlığı düğmeye döner, aria-sort ile duyurulur ----------
     data-sirala="sayi" sütunlarında hücrenin data-deger'i sayı olarak, ötekilerde metin Türkçe
     harf sırasıyla karşılaştırılır. Boş ("—") hücreler her iki yönde de sonda kalır. */
  function siralamaKur() {
    var basliklar = document.querySelectorAll("table th[data-sirala]");
    if (!basliklar.length) return;
    var harf = typeof Intl !== "undefined" ? new Intl.Collator("tr", { numeric: true, sensitivity: "base" }) : null;
    Array.prototype.forEach.call(basliklar, function (th) {
      var tablo = th.closest("table");
      var govde = tablo && tablo.tBodies[0];
      if (!govde) return;
      var dugme = document.createElement("button");
      dugme.type = "button";
      dugme.className = "sirala";
      while (th.firstChild) dugme.appendChild(th.firstChild);
      var ok = simge("s-asagi");
      ok.setAttribute("class", "simge sirala-ok");
      dugme.appendChild(ok);
      th.appendChild(dugme);
      dugme.addEventListener("click", function () {
        var sutun = Array.prototype.indexOf.call(th.parentNode.children, th);
        var artan = th.getAttribute("aria-sort") !== "ascending";
        Array.prototype.forEach.call(tablo.querySelectorAll("th[aria-sort]"), function (x) { x.removeAttribute("aria-sort"); });
        th.setAttribute("aria-sort", artan ? "ascending" : "descending");
        var sayi = th.getAttribute("data-sirala") === "sayi";
        function deger(tr) {
          var h = tr.cells[sutun];
          if (!h) return "";
          var d = h.getAttribute("data-deger");
          var v = d !== null ? d : h.textContent.trim();
          return v === "—" ? "" : v;
        }
        var satirlar = Array.prototype.slice.call(govde.rows);
        satirlar.sort(function (a, b) {
          var x = deger(a), y = deger(b);
          if (!sayi && (x === "" || y === "")) return x === y ? 0 : (x === "" ? 1 : -1);
          var f = sayi ? (parseFloat(x) || 0) - (parseFloat(y) || 0)
            : (harf ? harf.compare(x, y) : (x < y ? -1 : x > y ? 1 : 0));
          return artan ? f : -f;
        });
        satirlar.forEach(function (tr) { govde.appendChild(tr); });
      });
    });
  }

  /* ---- cizelge (0.10.0 zil düzenleyici): form#cizelge-formu ---------------------------------------
     JS'siz sayfa tam işlevlidir (boş satırlar, sıralama ve numaralama sunucuda). Burada: boş satırlar gizlenir,
     "Ders ekle" ve "Araya ekle" <template id="cizelge-satir">'dan satır çoğaltır, numara ve "Sonraki ara" yazdıkça
     yeniden hesaplanır (sunucuyla aynı ≤ 20 dk teneffüs eşiği), "Sil" işaretli satır .silinecek olur. Hızlı oluştur
     gönderilirken düzenleme tablosundaki kaydedilmemiş satırlar da gider (sunucu o taslağı temel alır). */
  var TENEFFUS_ESIGI_DK = 20;
  function dakika(s) {
    var m = /^(\d{1,2}):(\d{2})/.exec(s || "");
    if (!m) return null;
    var h = parseInt(m[1], 10), d = parseInt(m[2], 10);
    return h < 24 && d < 60 ? h * 60 + d : null;
  }
  function saatYaz(dk) {
    if (dk === null || dk < 0 || dk >= 24 * 60) return "";
    var h = Math.floor(dk / 60), d = dk % 60;
    return (h < 10 ? "0" : "") + h + ":" + (d < 10 ? "0" : "") + d;
  }
  function araMetni(dk) {
    if (dk === null) return "—";
    if (dk <= 0) return "Ara yok";
    return (dk <= TENEFFUS_ESIGI_DK ? "Teneffüs " : "Öğle arası ") + dk + " dk";
  }
  function cizelgeKur() {
    var form = $("cizelge-formu");
    var sablon = $("cizelge-satir");
    if (!form || !sablon || !("content" in sablon)) return;
    var duyuru = $("cizelge-duyuru");
    form.classList.add("js-cizelge");
    var sira = 0;
    Array.prototype.forEach.call(form.querySelectorAll('input[name="satir"]'), function (g) {
      var n = parseInt((g.value || "").replace(/^r/, ""), 10);
      if (!isNaN(n) && n >= sira) sira = n + 1;
    });

    function duyur(metin) {
      if (!duyuru) return;
      duyuru.textContent = "";
      setTimeout(function () { duyuru.textContent = metin; }, 50);
    }
    function satirBilgisi(tr) {
      var bas = tr.querySelector('input[type="time"][name$="_bas"]');
      var bit = tr.querySelector('input[type="time"][name$="_bit"]');
      var sil = tr.querySelector('input[type="checkbox"][name$="_sil"]');
      return { tr: tr, bas: bas, bit: bit, b: dakika(bas && bas.value), s: dakika(bit && bit.value), silinecek: !!(sil && sil.checked) };
    }
    function gecerliler(kap) {
      return Array.prototype.map.call(kap.querySelectorAll("tbody tr"), satirBilgisi).filter(function (x) {
        return !x.silinecek && x.b !== null && x.s !== null && x.s > x.b;
      }).sort(function (a, b) { return a.b - b.b; });
    }
    function yenile(kap) {
      var adi = kap.getAttribute("data-devre-adi") || "";
      var liste = gecerliler(kap);
      var numara = new Map();
      liste.forEach(function (x, i) { numara.set(x.tr, i); });
      Array.prototype.forEach.call(kap.querySelectorAll("tbody tr"), function (tr) {
        var x = satirBilgisi(tr);
        var i = numara.has(tr) ? numara.get(tr) : -1;
        var noYeri = tr.querySelector("[data-no]");
        var ara = tr.querySelector("td.ara");
        var etiket = adi + " " + (i >= 0 ? (i + 1) + ". ders" : "yeni ders");
        if (noYeri) noYeri.textContent = i >= 0 ? (i + 1) + ". ders" : (x.silinecek ? "Silinecek" : "Yeni");
        if (x.bas) x.bas.setAttribute("aria-label", etiket + " başlangıç");
        if (x.bit) x.bit.setAttribute("aria-label", etiket + " bitiş");
        var sil = tr.querySelector('input[type="checkbox"][name$="_sil"]');
        if (sil) sil.setAttribute("aria-label", adi + " " + (i >= 0 ? (i + 1) + ". dersi" : "bu satırı") + " sil");
        var araya = tr.querySelector("button[data-araya]");
        if (araya) araya.setAttribute("aria-label", adi + " " + (i >= 0 ? (i + 1) + ". dersten" : "bu satırdan") + " sonra araya ekle");
        tr.classList.toggle("silinecek", x.silinecek);
        if (ara) {
          var dk = i >= 0 && i + 1 < liste.length ? liste[i + 1].b - x.s : null;
          ara.textContent = i >= 0 ? araMetni(dk) : "";
          if (dk !== null && dk > TENEFFUS_ESIGI_DK) ara.setAttribute("data-tur", "ogle");
          else ara.removeAttribute("data-tur");
        }
      });
      var baslik = kap.querySelector("caption");
      if (baslik) baslik.textContent = adi + " · " + liste.length + " ders";
    }
    function arayaDugmesi(tr) {
      var td = document.createElement("td");
      td.className = "araya-hucre";
      var d = document.createElement("button");
      d.type = "button";
      d.className = "araya";
      d.setAttribute("data-araya", "");
      d.textContent = "Araya ekle";
      td.appendChild(d);
      tr.appendChild(td);
    }
    function yeniSatir(kap, sonra, bas, bit) {
      var devre = kap.getAttribute("data-devre");
      var tr = sablon.content.firstElementChild.cloneNode(true);
      var r = "r" + (sira++);
      tr.querySelector('input[name="satir"]').value = r;
      var dv = tr.querySelector('[data-alan="devre"]');
      dv.name = r + "_devre";
      dv.value = devre;
      ["bas", "bit", "sil"].forEach(function (a) {
        var g = tr.querySelector('[data-alan="' + a + '"]');
        g.name = r + "_" + a;
        if (a !== "sil") g.id = r + "_" + a;
      });
      tr.querySelector('[data-alan="bas"]').value = bas || "";
      tr.querySelector('[data-alan="bit"]').value = bit || "";
      arayaDugmesi(tr);
      var govde = kap.querySelector("tbody");
      if (sonra && sonra.nextSibling) govde.insertBefore(tr, sonra.nextSibling);
      else if (sonra) govde.appendChild(tr);
      else {
        var bos = govde.querySelector("tr[data-bos]");
        govde.insertBefore(tr, bos);
      }
      yenile(kap);
      var ilk = tr.querySelector('input[type="time"]');
      if (ilk) ilk.focus();
      duyur((kap.getAttribute("data-devre-adi") || "") + ": yeni ders satırı eklendi.");
    }
    function dersEkle(kap) {
      var liste = gecerliler(kap);
      var bas = null, sure = 40, ara = 10;
      if (liste.length) {
        var son = liste[liste.length - 1];
        sure = son.s - son.b;
        if (liste.length > 1) {
          var onceki = liste[liste.length - 2];
          var g = son.b - onceki.s;
          if (g >= 0 && g <= TENEFFUS_ESIGI_DK) ara = g;
        }
        bas = son.s + ara;
      } else if (kap.getAttribute("data-devre") === "ogle") {
        var sabah = form.querySelector('.devre-tablosu[data-devre="sabah"]');
        var sl = sabah ? gecerliler(sabah) : [];
        if (sl.length) bas = Math.ceil((sl[sl.length - 1].s + 20) / 5) * 5;
      }
      var b = bas === null ? "" : saatYaz(bas);
      yeniSatir(kap, null, b, b ? saatYaz(bas + sure) : "");
    }
    function arayaEkle(kap, tr) {
      var x = satirBilgisi(tr);
      var liste = gecerliler(kap);
      var i = liste.map(function (y) { return y.tr; }).indexOf(tr);
      var sonraki = i >= 0 && i + 1 < liste.length ? liste[i + 1] : null;
      var bas = x.s, bit = sonraki ? sonraki.b : null;
      if (bas === null || bit === null || bit <= bas) { bas = null; bit = null; }
      yeniSatir(kap, tr, saatYaz(bas), saatYaz(bit));
    }

    Array.prototype.forEach.call(form.querySelectorAll(".devre-tablosu"), function (kap) {
      var bas = kap.querySelector("thead tr");
      if (bas) {
        var th = document.createElement("th");
        th.scope = "col";
        var g = document.createElement("span");
        g.className = "gizli";
        g.textContent = "Araya ekle";
        th.appendChild(g);
        bas.appendChild(th);
      }
      Array.prototype.forEach.call(kap.querySelectorAll("tbody tr"), function (tr) {
        if (tr.hasAttribute("data-bos")) { tr.appendChild(document.createElement("td")); return; }
        arayaDugmesi(tr);
      });
      var dugmeler = kap.querySelector(".devre-dugmeleri");
      if (dugmeler) dugmeler.hidden = false;
      kap.addEventListener("click", function (olay) {
        var d = olay.target.closest("button");
        if (!d || !kap.contains(d)) return;
        if (d.hasAttribute("data-ders-ekle")) dersEkle(kap);
        else if (d.hasAttribute("data-araya")) arayaEkle(kap, d.closest("tr"));
      });
      kap.addEventListener("input", function () { yenile(kap); });
      kap.addEventListener("change", function () { yenile(kap); });
      yenile(kap);
    });

    // Hızlı oluştur: kaydedilmemiş düzenleme tablosu da gönderilsin (sunucu "satir" alanı varsa formu temel alır).
    var hizli = $("hizli-formu");
    if (hizli) {
      hizli.addEventListener("submit", function () {
        Array.prototype.forEach.call(hizli.querySelectorAll("input[data-kopya]"), function (g) { g.remove(); });
        new FormData(form).forEach(function (deger, ad) {
          if (ad === "eylem" || ad === "onay_numara" || typeof deger !== "string") return;
          var g = document.createElement("input");
          g.type = "hidden";
          g.name = ad;
          g.value = deger;
          g.setAttribute("data-kopya", "");
          hizli.appendChild(g);
        });
      });
    }
  }

  /* ---- Şube defteri (0.14.0): fırça ile hücre düzeltme -----------------------------
     Form JS'siz de aynı sonucu verir (hücre = gönder düğmesi, 303 ile aynı sayfa). Burada yalnız
     fetch + yerinde güncelleme + aria-live iletisi eklenir; hata olursa hücre geri alınır.
     Toplu işlemler ("Bütün gün yok", "Temizle", "Alındı") ve "Notu kaydet" düz gönderilir. */
  var DEFTER_SIMGE = { yok: "Y", gec: "G", "var": "·" };
  function defterKur() {
    var form = document.querySelector("form[data-defter]");
    if (!form || typeof window.fetch !== "function" || typeof window.URLSearchParams !== "function") return;
    var ileti = $("defter-ileti");
    function bildir(metin, hata) {
      if (!ileti) return;
      if (hata) ileti.setAttribute("data-hata", ""); else ileti.removeAttribute("data-hata");
      ileti.textContent = metin;
    }
    function ciz(td, dugme, durum, simge, ozurlu, kapsam, duz) {
      td.setAttribute("data-d", durum);
      if (ozurlu) td.setAttribute("data-ozurlu", ""); else td.removeAttribute("data-ozurlu");
      if (kapsam && durum === "var") td.setAttribute("data-kapsam", ""); else td.removeAttribute("data-kapsam");
      if (duz) td.setAttribute("data-duz", ""); else td.removeAttribute("data-duz");
      dugme.textContent = simge;
    }
    // Ok tuşlarıyla hücreden hücreye (Tab sırası değişmez; tıklanamayan hücreler atlanır).
    var OK_YONU = { ArrowLeft: [0, -1], ArrowRight: [0, 1], ArrowUp: [-1, 0], ArrowDown: [1, 0] };
    form.addEventListener("keydown", function (olay) {
      var yon = OK_YONU[olay.key];
      var hedef = olay.target;
      if (!yon || !hedef || hedef.name !== "hucre" || olay.altKey || olay.ctrlKey || olay.metaKey) return;
      var hucre = hedef.closest("td");
      var satir = hucre.parentNode;
      var sira = Array.prototype.indexOf.call(satir.children, hucre);
      var bulunan = null;
      for (var adim = 0; adim < 80 && !bulunan; adim++) {
        if (yon[0]) {
          satir = yon[0] > 0 ? satir.nextElementSibling : satir.previousElementSibling;
          hucre = satir ? satir.children[sira] : null;
        } else {
          hucre = yon[1] > 0 ? hucre.nextElementSibling : hucre.previousElementSibling;
        }
        if (!hucre) return;
        bulunan = hucre.querySelector('button[name="hucre"]');
      }
      if (bulunan) { olay.preventDefault(); bulunan.focus(); }
    });
    form.addEventListener("submit", function (olay) {
      var dugme = olay.submitter;
      if (!dugme || dugme.name !== "hucre") return;
      olay.preventDefault();
      var td = dugme.closest("td");
      var tr = dugme.closest("tr");
      var govde = new URLSearchParams(new FormData(form));
      govde.set("hucre", dugme.value);
      var firca = govde.get("durum") || "yok";
      var onceki = {
        durum: td.getAttribute("data-d"), simge: dugme.textContent, ozurlu: td.hasAttribute("data-ozurlu"),
        kapsam: td.hasAttribute("data-kapsam"), duz: td.hasAttribute("data-duz")
      };
      // Dokunuş hemen çizilir; yanıt gelince sunucunun dediğiyle eşitlenir (aynı duruma dokunmak düzeltmeyi kaldırır).
      ciz(td, dugme, firca, DEFTER_SIMGE[firca] || onceki.simge, false, false, true);
      td.setAttribute("aria-busy", "true");
      fetch(form.getAttribute("action"), {
        method: "POST", body: govde, credentials: "same-origin", headers: { Accept: "application/json" }
      }).then(function (yanit) {
        return yanit.json().then(function (veri) { return { tamam: yanit.ok, veri: veri }; });
      }).then(function (sonuc) {
        if (!sonuc.tamam) {
          var hata = new Error(sonuc.veri && sonuc.veri.hata ? sonuc.veri.hata : "Kaydedilemedi.");
          hata.notGerek = !!(sonuc.veri && sonuc.veri.not_gerek);
          throw hata;
        }
        var v = sonuc.veri;
        ciz(td, dugme, v.durum, v.simge, v.ozurlu, v.kapsam, v.duzeltme);
        var etiket = dugme.getAttribute("aria-label") || "";
        dugme.setAttribute("aria-label", etiket.replace(/: [^:]*$/, ": " + v.durum_metni));
        var satir = tr && tr.querySelector("[data-satir-ozet]");
        if (satir) satir.textContent = v.satir_ozeti.yok + " / " + v.satir_ozeti.gec;
        var sutun = form.querySelector('[data-sutun-ozet="' + dugme.value.split(":")[1] + '"]');
        if (sutun) sutun.textContent = v.sutun_ozeti.yok + " / " + v.sutun_ozeti.gec;
        // Satırın "Temizle" düğmesi satırda düzeltme kaldıkça görünür (yanlış dokunuş sayfa yenilemeden geri alınır).
        var temizle = tr && tr.querySelector("[data-temizle]");
        if (temizle) temizle.hidden = !v.satir_duzeltme;
        bildir(v.ileti || "", false);
      }).catch(function (hata) {
        ciz(td, dugme, onceki.durum, onceki.simge, onceki.ozurlu, onceki.kapsam, onceki.duz);
        bildir(hata && hata.message ? hata.message : "Kaydedilemedi; bağlantıyı denetleyin.", true);
        var notAlani = hata && hata.notGerek ? $("df-not") : null;
        if (notAlani) notAlani.focus(); // not zorunlu: alan yapışkan şeritte, odak oraya gider
      }).then(function () {
        td.removeAttribute("aria-busy");
      });
    });
  }

  panoKur();
  defterKur();
  cizelgeKur();
  siralamaKur();
  sinavKur();
  yoklamaSayaciKur();
  otomatikGonderKur();
  secimDegisimiKur();
  yokSayaciKur();
  izgaraKur();
  kabukKur();
  menuKur();
  sayacKur();
  duyuruFormuKur();
  acilKur();
  yazdirKur();
  tekIndirmeKur();
  sablonKur();
  onayKur();
  ayarlarKur();
  kopyalaKur();
  dogrulamaKur();
  iletiKur();
})();
