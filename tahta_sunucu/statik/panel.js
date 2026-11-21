/* Tahta Kontrol paneli — kütüphane yok, derleme yok.
   Sayfa kancalarına göre bölümler: onay (tehlikeli işlem dialogu), tahtalar (0.17.0: tahta listesinin canlı durumu,
   seçim çubuğu, süzgeç hapları, duyurucu; durum kuralı SUNUCUDADIR, burada yalnız /api/durum'un `liste` alanı yazılır),
   bugun (0.18.0: Bugün sayfasının canlı sayıları, çipleri, program satırı; "Hepsini kilitle…" onayı; kural yine sunucuda),
   menu (açılır menülerin kapanışı ve yönü), sayac,
   duyuru formu (koşullu alanlar, hedef önizlemesi), acil (tür, şablon, teslim sayacı),
   yazdir, acil şablonları, ayarlar (renk önizlemesi, logo; 0.16.0: kaydedilmemiş değişiklik çubuğu, Ayarlar içi
   arama, eski parça adresleri), kopyala, dogrulama,
   program (program satırı Bugün'de; tahta ızgarasında "Tümünü işaretle"),
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
      baslik: function (n, ad) { return n === null ? (ad ? "“" + ad + "” tahtası" : "Bu tahta") + " kapatılsın mı?" : n + " tahta kapatılsın mı?"; }
    },
    yeniden_baslat: {
      ad: "tur", deger: "yeniden_baslat", evet: "Yeniden başlat",
      metin: "Açık çalışmalar kaybolabilir.",
      baslik: function (n, ad) { return n === null ? (ad ? "“" + ad + "” tahtası" : "Bu tahta") + " yeniden başlatılsın mı?" : n + " tahta yeniden başlatılsın mı?"; }
    },
    sil: {
      ad: "eylem", deger: "sil", evet: "Tahtayı kaldır",
      metin: "Ajanı sunucuya bağlanamaz; yeniden eklemek için kurulum gerekir.",
      baslik: function () { return "Bu tahta panelden kaldırılsın mı?"; }
    },
    /* 0.21.0: Tahtalar › aynı ad bandı. data-onay-ad sayıyı taşır; sunucu listeyi yeniden hesaplar. */
    adlandir: {
      ad: "eylem", deger: "adlandir", evet: "Yeniden adlandır",
      metin: "Adı başka bir tahtayla aynı olan her tahta “Tahta <no>” adını alır; no, kurulumun sonunda tahtanın ekranında çıkan numaradır. Derslik ve öbür bilgiler değişmez.",
      baslik: function (n, ad) { return (ad ? ad + " tahta" : "Aynı adlı tahtalar") + " yeniden adlandırılsın mı?"; }
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
      baslik: function (n, ad) { return (ad ? "“" + ad + "” tahtasında" : "Bu tahtada") + " oturum temizliği yapılsın mı?"; }
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
    },
    /* Ayarlar (0.16.0): dikkat gerektiren iki iş. JS yoksa düğmeler (type="button") hiçbir şey göndermez. */
    kilit_kodu_sil: {
      ad: "kilit_kodu_sil", deger: "1", evet: "Kodu kaldır",
      metin: "Kilitli tahtalar yalnız panelden açılır; öğretmenler tahtayı kendileri açamaz. Yeni kod belirleyince eski düzen döner.",
      baslik: function () { return "Kilit kodu kaldırılsın mı?"; }
    },
    logo_sil: {
      ad: "eylem", deger: "sil", evet: "Logoyu kaldır",
      metin: "Panelde okul adının baş harfleri, tahtada yalnız okul adı görünür.",
      baslik: function () { return "Okul logosu kaldırılsın mı?"; }
    },
    /* Bugün (0.18.0): formda `tur` alanı yoktur; `tur=kilitle` yalnız bu pencerenin "evet" düğmesiyle eklenir.
       Sayılar formun data-hedef / data-sinavda / data-cevrimdisi özniteliklerinden okunur (onayKur'da ayrı dal). */
    hepsini_kilitle: {
      ad: "tur", deger: "kilitle", evet: "Hepsini kilitle",
      metin: "Kilit kodu ya da panelden açılana kadar tahtalar kilitli kalır. Derste kullanılan tahtalar da kilitlenir.",
      baslik: function (n) { return "Çevrimiçi " + n + " tahta kilitlensin mi?"; }
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
  var pano = null; // tahtalar bölümü kurulunca doldurulur (form, seçili satırlar, sınav ve etki özetleri)
  // Tek tahtaya yıkıcı komutun etki cümleleri (liste satırı ve tahta sayfası aynı metni kullanır).
  var ETKI = {
    oturum: "Bu tahtada açık oturum var; derste kullanılıyor olabilir.",
    cevrimdisi: "Tahta çevrimdışı; 2 dakika içinde bağlanmazsa komut düşer."
  };

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

    // Formdaki seçili tahtalardan kaçı sınav penceresinde (liste: /api/durum t.sinav; tahta sayfası: data-sinavdaki).
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
        if (!gonderen || gonderen === evet) return;
        // Satır düğmesi ve satır menüsü `tek=<tur>:<id>` gönderir: yalnız o tahta sınavdaysa ek onay istenir.
        var tek = gonderen.name === "tek";
        if (!tek && gonderen.name !== "tur") return;
        var ek = SINAV_EK_ONAY[tek ? String(gonderen.value).split(":")[0] : gonderen.value];
        if (!ek) return;
        var n = tek ? (pano && pano.sinavdaMi(String(gonderen.value).split(":")[1]) ? 1 : 0) : sinavdaki(form);
        if (!n) return;
        olay.preventDefault();
        liste.textContent = "";
        liste.hidden = true;
        uyari.textContent = "";
        uyari.hidden = true;
        ac(form, sinavCumlesi(n, kimlik === "islem" && !tek) + " Devam edilsin mi?", ek.metin, gonderen.name, gonderen.value, ek.evet);
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
        // Açık komut menüsü dialogun arkasında açık kalmasın.
        var acikMenu = tetik.closest("details");
        if (acikMenu) acikMenu.open = false;
        // Bugün › "Hepsini kilitle…": ayrı dal. Tahta adı listelenmez; sayılar sunucunun forma yazdığı (canlı tazelenen)
        // özniteliklerdendir. Kilitlenecek tahta yoksa pencere açılmaz. Sunucu yine kendi sayar ve iletide söyler.
        if (tetik.getAttribute("data-onay") === "hepsini_kilitle") {
          var kilitHedef = parseInt(form.getAttribute("data-hedef") || "0", 10) || 0;
          var kilitSinav = parseInt(form.getAttribute("data-sinavda") || "0", 10) || 0;
          var kilitDisi = parseInt(form.getAttribute("data-cevrimdisi") || "0", 10) || 0;
          var kilitNotu = $("kilit-notu");
          if (kilitNotu) kilitNotu.textContent = "";
          if (!kilitHedef) {
            if (kilitNotu) {
              kilitNotu.textContent = kilitSinav
                ? "Çevrimiçi tahtaların hepsi sınav kipinde; kilitlenecek tahta yok." : "Kilitlenecek çevrimiçi tahta yok.";
            }
            return;
          }
          var kilitCumleleri = [];
          if (kilitSinav) kilitCumleleri.push(kilitSinav + " tahta sınav kipinde; atlanacak.");
          if (kilitDisi) kilitCumleleri.push(kilitDisi + " tahta çevrimdışı; onlara gönderilmez.");
          if (kilitCumleleri.length) {
            uyari.textContent = kilitCumleleri.join(" ");
            uyari.hidden = false;
          }
          ac(form, tanim.baslik(kilitHedef), tanim.metin, tanim.ad, tanim.deger, tanim.evet);
          return;
        }
        // data-tek (satır menüsü): işaretli başka tahtalar olsa da onay YALNIZ o tahta içindir ve yalnız `tek` gönderilir.
        // KAPALI HATA: data-tek taşıyan tetik hiçbir koşulda `tur` ile (işaretli bütün tahtalara) gönderilmez;
        // liste kurulamadıysa (pano yok) hiçbir şey yapılmaz.
        var tekDeger = tetik.getAttribute("data-tek") || "";
        if (tetik.hasAttribute("data-tek")) {
          if (!pano || form !== pano.form || !/^[a-z_]+:[1-9][0-9]*$/.test(tekDeger)) return;
          var tekKimlik = tekDeger.split(":")[1] || "";
          var tekAd = tetik.getAttribute("data-onay-ad") || "";
          if (!tekAd) { // ad başlıkta yazar; yoksa listede kimlik yerine satırın adı aranır
            var tekSatir = document.createElement("li");
            tekSatir.textContent = "Tahta #" + tekKimlik;
            liste.appendChild(tekSatir);
            liste.hidden = false;
          }
          var tekCumleler = pano.tekOzeti(tekKimlik);
          if (pano.sinavdaMi(tekKimlik)) tekCumleler.unshift(sinavCumlesi(1, false));
          if (tekCumleler.length) {
            uyari.textContent = tekCumleler.join(" ");
            uyari.hidden = false;
          }
          ac(form, tanim.baslik(null, tekAd), tanim.metin, "tek", tekDeger, tanim.evet);
          return;
        }
        var sinavUyarisi = tanim.ad === "tur" ? sinavCumlesi(sinavdaki(form), !!(pano && form === pano.form)) : "";
        if (sinavUyarisi) {
          uyari.textContent = sinavUyarisi;
          uyari.hidden = false;
        }
        if (pano && form === pano.form) {
          var secili = pano.seciliSatirlar();
          if (!secili.length) {
            pano.uyar("Önce en az bir tahta seçin.");
            return;
          }
          n = secili.length;
          secili.slice(0, 12).forEach(function (satir) {
            var li = document.createElement("li");
            li.textContent = pano.satirAdi(satir);
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
        } else if (tanim.ad === "tur") {
          // Tahta sayfası (kapat, yeniden başlat): listedeki uyarıların aynısı, sunucunun forma yazdığı durumdan.
          var sayfaCumleleri = sinavUyarisi ? [sinavUyarisi] : [];
          if (form.hasAttribute("data-oturum-acik")) sayfaCumleleri.push(ETKI.oturum);
          if (form.hasAttribute("data-cevrimdisi")) sayfaCumleleri.push(ETKI.cevrimdisi);
          if (sayfaCumleleri.length) {
            uyari.textContent = sayfaCumleleri.join(" ");
            uyari.hidden = false;
          }
        }
        ac(form, tanim.baslik(n, tetik.getAttribute("data-onay-ad") || ""), tanim.metin, tanim.ad, tanim.deger, tanim.evet);
      });
    });
  }

  /* ---- tahtalar: canlı durum, seçim, süzgeç, duyurucu -------------------------- */
  // Satırın durumu, rozetleri, birincil düğmesi ve menü pasiflikleri SUNUCUDA hesaplanır (tahta_liste.durum_ozeti);
  // /api/durum her tahtada şablondakiyle aynı `liste` sözlüğünü verir. Burada yalnız yazılır: kural JS'te yinelenmez.
  var DEGISIM = {
    acik: "açıldı", cevrimdisi: "çevrimdışı oldu", kilitli: "kilitlendi",
    duyuru: "duyuru gösteriyor", sorun: "ekran yardımcısını yitirdi"
  };
  var DUGME_KORUMA_MS = 700; // canlı tazelemede değişen birincil düğme bu süre tıklama almaz

  function siteIciYol(yol) {
    return typeof yol === "string" && yol.charAt(0) === "/" && yol.charAt(1) !== "/";
  }

  /* Canlı yoklama (Tahtalar ve Bugün ortak): /api/durum 4 sn'de bir; sekme gizliyken durur, 401'de girişe gider.
     geriCagri(v) hata fırlatırsa ya da istek düşerse hataCagri() çağrılır. */
  function durumYoklayici(geriCagri, hataCagri) {
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
        if (v) geriCagri(v);
      }).catch(function () {
        hataCagri();
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
    zamanlayici = setTimeout(yokla, 4000);
  }

  /* "Canlı · son güncelleme SS:DD:SS" / "Bağlantı kesildi · son veri N sn önce" göstergesi. */
  function canliGostergesi(canli) {
    var sonBasari = Date.now();
    function iki(n) { return (n < 10 ? "0" : "") + n; }
    return function (basarili) {
      if (basarili) sonBasari = Date.now();
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
    };
  }

  /* Program satırı (Bugün › Şu an): şu anki ders, sunucu saati, program kilidi rozeti, boş ders uyarısı sayısı,
     "Durdur" açılırı. /api/durum.program'ı `kap` içindeki data-alan kancalarına yazar; metinler sunucudakiyle aynıdır. */
  var KILIT_ROZETI = {
    acik: ["acik", "s-kilit", function () { return "Program kilidi etkin"; }],
    durduruldu: ["uyari", "s-onay", function (p) { return "Program kilidi durduruldu · bitiş " + (p.durduruldu_bitis || ""); }],
    kapali: ["bilgi", "s-kapali", function () { return "Program kilidi kapalı"; }]
  };
  function programYazici(kap) {
    var son = "";
    function alan(ad) { return kap.querySelector('[data-alan="' + ad + '"]'); }
    return function (p) {
      if (!kap || !p) return;
      var imza = JSON.stringify([p.simdi, p.sunucu_saat, p.kilit, p.durduruldu_bitis, p.uyari_sayisi]);
      if (imza === son) return;
      son = imza;
      var simdi = alan("simdi");
      if (simdi) simdi.textContent = p.simdi || "";
      var saat = alan("saat");
      if (saat) saat.textContent = p.sunucu_saat || "";
      var kilit = alan("kilit");
      var k = KILIT_ROZETI[p.kilit] || KILIT_ROZETI.kapali;
      if (kilit) {
        kilit.textContent = "";
        kilit.appendChild(rozet(k[0], k[2](p), k[1]));
      }
      var istisnalar = alan("istisnalar");
      if (istisnalar) istisnalar.hidden = p.kilit !== "durduruldu";
      var kurallar = alan("kurallar");
      if (kurallar) kurallar.hidden = p.kilit !== "kapali";
      var uyari = alan("uyari");
      if (uyari) {
        uyari.hidden = !p.uyari_sayisi;
        uyari.querySelector("span").textContent = p.uyari_sayisi + " boş ders uyarısı";
      }
      var uyariNotu = alan("uyari-notu");
      if (uyariNotu) uyariNotu.hidden = !p.uyari_sayisi;
      var durdur = alan("durdur");
      // Açık menü kullanıcı seçim yaparken kapanmasın: yalnız kapalıyken gizlenir.
      if (durdur && !durdur.open) durdur.hidden = p.kilit !== "acik";
    };
  }

  function tahtalarKur() {
    var form = $("islem");
    var ilk = $("ilk-veri");
    if (!form || !ilk) return;
    var panoVeri = {};
    try { panoVeri = JSON.parse(($("pano-veri") || {}).textContent || "{}"); } catch (e) { panoVeri = {}; }
    var satirlar = new Map();
    Array.prototype.forEach.call(form.querySelectorAll("tr.tahta-satir[data-id]"), function (tr) {
      satirlar.set(String(tr.getAttribute("data-id")), tr);
    });
    var kutular = Array.prototype.slice.call(form.querySelectorAll('input[name="tahta"]'));
    var grupKutulari = Array.prototype.slice.call(form.querySelectorAll("input[data-grup-sec]"));
    var imzalar = new Map();
    var dugmeImzalari = new Map();
    var menuImzalari = new Map();
    var birinciller = new Map();
    var sonVeri = new Map();
    var secimSayisi = $("secim-sayisi");
    var canliBolge = $("canli-bolge");
    var canli = $("canli");
    var haplar = $("haplar");
    var hepsiniSec = $("hepsini-sec");
    var secimTemizle = $("secim-temizle");
    var suzgecBos = $("suzgec-bos");
    var yenileBandi = $("yenile-bandi");
    var diyalog = $("onay-diyalog");
    var donusAlani = form.querySelector('input[name="donus"]');
    var listeYolu = form.getAttribute("data-liste-yolu") || "/tahtalar";
    var suzgecBaglantilari = Array.prototype.slice.call(document.querySelectorAll("a[data-suzgec]"));
    var etkinHap = haplar && haplar.querySelector('a[aria-current="true"]');
    var suzgec = etkinHap ? (etkinHap.getAttribute("data-suzgec") || "") : "";
    // Telefonda haplar tek satırda yatay kayar: etkin hap görünür alana getirilir (sayfa kaymaz).
    if (etkinHap && haplar.scrollWidth > haplar.clientWidth) haplar.scrollLeft = Math.max(0, etkinHap.offsetLeft - haplar.offsetLeft - 8);
    var canliYaz = canliGostergesi(canli);
    var fareVar = !!(window.matchMedia && window.matchMedia("(hover: hover)").matches);

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

    function alan(tr, ad) { return tr.querySelector('[data-alan="' + ad + '"]'); }

    function rozetleriYaz(tr, liste) {
      var kap = alan(tr, "rozetler");
      if (!kap) return;
      kap.textContent = "";
      (liste.rozetler || []).forEach(function (r) {
        if (r.liste === false) return; // sunucu "liste satırında çizilmez" dedi (düz güncelleme rozeti; hap sayısında kalır)
        var e = rozet(r.d, r.m, r.s);
        if (siteIciYol(r.yol)) { // arıza rozeti arıza listesine bağlanır
          var a = document.createElement("a");
          a.className = "rozet";
          a.setAttribute("data-durum", r.d);
          a.setAttribute("href", r.yol);
          while (e.firstChild) a.appendChild(e.firstChild);
          e = a;
        }
        kap.appendChild(e);
        kap.appendChild(document.createTextNode(" "));
      });
    }

    // Birincil düğme: imleç ya da odak DÜĞMENİN ÜSTÜNDEYKEN (satırın işlem hücresi) ya da onay penceresi açıkken
    // DEĞİŞTİRİLMEZ (parmağın altında "Kilitle"den "Kilidi aç"a dönmesin); değişen düğme DUGME_KORUMA_MS boyunca
    // tıklama almaz. Koruma satırın bütününe yayılmaz: seçim kutusunda ya da kapalı menü özetinde kalan odak
    // düğmeyi dondurur, rozetle ("Kilitli") düğme ("Kilitle") çelişirdi.
    function dugmeYaz(tr, t, ilkCizim) {
      var id = String(t.id);
      var d = t.liste.dugme || null;
      var imza = JSON.stringify(d);
      if (dugmeImzalari.get(id) === imza) return;
      if (ilkCizim) { dugmeImzalari.set(id, imza); return; } // ilk boyama sunucudandır
      var kap = alan(tr, "dugme");
      if (!kap) return;
      var hucre = kap.closest(".satir-eylem") || kap;
      if (dialogAcik() || kap.contains(document.activeElement) || (fareVar && hucre.matches(":hover"))) return;
      kap.textContent = "";
      if (d) {
        var e;
        if (d.yol) {
          if (!siteIciYol(d.yol)) return;
          e = document.createElement("a");
          e.className = "dugme";
          e.setAttribute("href", d.yol);
        } else {
          e = document.createElement("button");
          e.type = "submit";
          e.name = "tek";
          e.value = d.tur + ":" + id;
          if (d.tur === "kilitle") e.appendChild(simge("s-kilit"));
        }
        var yazi = document.createElement("span");
        yazi.textContent = d.ad;
        e.appendChild(yazi);
        var ek = document.createElement("span");
        ek.className = "gizli";
        ek.textContent = " (" + t.ad + ")";
        e.appendChild(ek);
        e.setAttribute("data-degisti", String(Date.now()));
        kap.appendChild(e);
      }
      dugmeImzalari.set(id, imza);
    }

    // Menü pasiflikleri: açık menü yeniden çizilmez (kullanıcı seçim yaparken öğe yer değiştirmesin).
    function menuYaz(tr, t, ilkCizim) {
      var id = String(t.id);
      var pasif = t.liste.pasif || {};
      var ipucu = t.liste.ipucu || {};
      var imza = JSON.stringify([pasif, ipucu]);
      if (menuImzalari.get(id) === imza) return;
      if (ilkCizim) { menuImzalari.set(id, imza); return; }
      var menu = tr.querySelector("details.satir-menu");
      if (!menu || menu.open) return;
      Array.prototype.forEach.call(menu.querySelectorAll("button[data-komut]"), function (b) {
        var komut = b.getAttribute("data-komut");
        var neden = Object.prototype.hasOwnProperty.call(pasif, komut) ? String(pasif[komut]) : "";
        b.disabled = !!neden;
        if (!b.hasAttribute("data-onay")) { // onay isteyen düğme hep type="button" kalır
          if (neden) {
            b.type = "button";
            b.removeAttribute("name");
            b.removeAttribute("value");
          } else {
            b.type = "submit";
            b.name = "tek";
            b.value = komut + ":" + id;
          }
        }
        var kucuk = b.querySelector("small");
        if (kucuk) {
          var alt = neden || (Object.prototype.hasOwnProperty.call(ipucu, komut) ? String(ipucu[komut]) : "");
          kucuk.textContent = alt;
          kucuk.hidden = !alt;
        }
      });
      menuImzalari.set(id, imza);
    }

    function satiriYaz(tr, t) {
      var l = t.liste;
      tr.setAttribute("data-birincil", l.birincil);
      tr.setAttribute("data-durumlar", (l.durumlar || []).join(" "));
      rozetleriYaz(tr, l);
      var o = alan(tr, "oturum");
      if (o) o.textContent = l.oturum || "—";
      var g = alan(tr, "gorulme");
      if (g) g.textContent = t.son_gorulme || "";
      var s = alan(tr, "surum");
      if (s) {
        // Güncel olmayan sürüm rozetle değil hücrede söylenir (ekran okuyucuya sözcükle); `guncel` sunucunun alanıdır.
        var eski = !!t.surum && !t.guncel;
        s.textContent = t.surum || "—";
        s.classList.toggle("eski", eski);
        if (eski) {
          var ek = document.createElement("span");
          ek.className = "gizli";
          ek.textContent = " · güncelleme var";
          s.appendChild(ek);
        }
      }
    }

    function ciz(liste, ilkCizim) {
      var bilinmeyen = false;
      liste.forEach(function (t) {
        var id = String(t.id);
        var tr = satirlar.get(id);
        sonVeri.set(id, t);
        if (!tr) { bilinmeyen = true; return; }
        if (!t.liste) return;
        var imza = JSON.stringify([t.liste.birincil, t.liste.durumlar, t.liste.rozetler, t.liste.oturum, t.son_gorulme, t.surum]);
        if (imzalar.get(id) !== imza) {
          if (!ilkCizim) satiriYaz(tr, t);
          imzalar.set(id, imza);
        }
        dugmeYaz(tr, t, ilkCizim);
        menuYaz(tr, t, ilkCizim);
        var onceki = birinciller.get(id);
        if (!ilkCizim && onceki && onceki !== t.liste.birincil && DEGISIM[t.liste.birincil]) {
          kuyruga(t.ad, DEGISIM[t.liste.birincil]);
        }
        birinciller.set(id, t.liste.birincil);
      });
      if (bilinmeyen) yenileGoster();
      if (!ilkCizim) {
        sayilariGuncelle();
        suzgecUygula();
      }
    }

    function durumlari(tr) { return (tr.getAttribute("data-durumlar") || "").split(" "); }

    // Hap sayıları süzgeçten bağımsızdır (bütün onaylı tahtalar); başlıktaki "çevrimiçi" sayısı da buradan.
    function sayilariGuncelle() {
      if (haplar) {
        Array.prototype.forEach.call(haplar.querySelectorAll("a[data-suzgec]"), function (a) {
          var anahtar = a.getAttribute("data-suzgec") || "";
          var sayi = 0;
          satirlar.forEach(function (tr) {
            if (!anahtar || durumlari(tr).indexOf(anahtar) >= 0) sayi++;
          });
          var b = a.querySelector("b");
          if (b) b.textContent = String(sayi);
          if (anahtar) a.classList.toggle("bos", sayi === 0);
        });
      }
      var cevrimici = document.querySelector('#tahta-ozet [data-alan="cevrimici"]');
      if (cevrimici) {
        var n = 0;
        satirlar.forEach(function (tr) { if (tr.getAttribute("data-birincil") !== "cevrimdisi") n++; });
        cevrimici.textContent = String(n);
      }
    }

    function gorunenKutular() {
      return kutular.filter(function (k) { return !k.disabled && !k.closest("tr").hidden; });
    }
    function seciliSatirlar() {
      return kutular.filter(function (k) { return k.checked && !k.disabled; }).map(function (k) { return k.closest("tr"); });
    }
    function ucDurum(kutu, liste) {
      var secili = liste.filter(function (k) { return k.checked; }).length;
      kutu.checked = liste.length > 0 && secili === liste.length;
      kutu.indeterminate = secili > 0 && secili < liste.length;
      kutu.disabled = liste.length === 0;
    }
    function grupKutulariOf(grupKutusu) {
      var govde = grupKutusu.closest("tbody");
      return gorunenKutular().filter(function (k) { return k.closest("tbody") === govde; });
    }
    function say() {
      var n = seciliSatirlar().length;
      form.classList.toggle("secili", n > 0);
      if (secimSayisi) {
        secimSayisi.textContent = "";
        if (n) {
          var sayi = document.createElement("b");
          sayi.textContent = String(n);
          var orta = document.createElement("span");
          orta.className = "yalniz-genis";
          orta.textContent = " tahta";
          secimSayisi.appendChild(sayi);
          secimSayisi.appendChild(orta);
          secimSayisi.appendChild(document.createTextNode(" seçili"));
        }
      }
      if (hepsiniSec) ucDurum(hepsiniSec, gorunenKutular());
      grupKutulari.forEach(function (g) { ucDurum(g, grupKutulariOf(g)); });
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
      var gorunen = 0;
      var dusen = 0;
      satirlar.forEach(function (tr) {
        var gizle = !!suzgec && durumlari(tr).indexOf(suzgec) < 0;
        tr.hidden = gizle;
        var k = tr.querySelector('input[name="tahta"]');
        if (k) { // gizli satır komut almasın: kutusu işaretsiz ve devre dışı (forma girmez)
          if (gizle && k.checked) dusen++;
          if (gizle) k.checked = false;
          k.disabled = gizle;
        }
        if (!gizle) gorunen++;
      });
      Array.prototype.forEach.call(form.querySelectorAll("tbody[data-grup]"), function (govde) {
        var baslik = govde.querySelector("tr.grup");
        if (!baslik) return;
        var gorunenSatir = govde.querySelectorAll("tr.tahta-satir:not([hidden])").length;
        baslik.hidden = !gorunenSatir;
        // Süzgeçliyken başlık "1 / 2 tahta" der: "grubu seç" yalnız görüneni seçer.
        var sayi = baslik.querySelector('[data-alan="grup-sayi"]');
        if (sayi) {
          var toplam = parseInt(sayi.getAttribute("data-toplam"), 10) || 0;
          sayi.textContent = "(" + (gorunenSatir !== toplam ? gorunenSatir + " / " : "") + toplam + " tahta)";
        }
      });
      if (suzgecBos) suzgecBos.hidden = !(suzgec && gorunen === 0);
      say();
      // Süzgeç dışında kalan satırın işareti sessizce düşmesin: seçim çubuğunda ve canlı bölgede söylenir.
      if (dusen) {
        var not = "Süzgeç dışında kalan " + dusen + " tahtanın seçimi kaldırıldı.";
        if (secimSayisi && seciliSatirlar().length) {
          var ek = document.createElement("span");
          ek.className = "not secim-notu";
          ek.textContent = " · " + dusen + " seçim süzgeç dışında kaldı";
          secimSayisi.appendChild(ek);
        }
        duyur(not);
      }
    }

    // Hap tıklaması sayfayı yenilemez: adres ve dönüş alanı güncellenir, satırlar gizlenir/gösterilir.
    function suzgecSec(deger) {
      suzgec = deger;
      if (haplar) {
        Array.prototype.forEach.call(haplar.querySelectorAll("a[data-suzgec]"), function (a) {
          if ((a.getAttribute("data-suzgec") || "") === suzgec) a.setAttribute("aria-current", "true");
          else a.removeAttribute("aria-current");
        });
      }
      var adres = listeYolu + (suzgec ? "?durum=" + encodeURIComponent(suzgec) : "");
      if (donusAlani) donusAlani.value = adres;
      var yenile = yenileBandi && yenileBandi.querySelector("a");
      if (yenile) yenile.setAttribute("href", adres);
      try { history.replaceState(null, "", adres); } catch (e) { /* adres değişmese de süzgeç çalışır */ }
      suzgecUygula();
    }
    suzgecBaglantilari.forEach(function (a) {
      a.addEventListener("click", function (olay) {
        if (olay.ctrlKey || olay.metaKey || olay.shiftKey || olay.altKey || olay.button) return;
        olay.preventDefault();
        suzgecSec(a.getAttribute("data-suzgec") || "");
      });
    });

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

    // Seçim yardımcıları yalnız JS'liyken görünür: yalnız görünen ve devre dışı olmayan kutuları etkiler.
    if (hepsiniSec) {
      var hepsiKap = $("hepsini-sec-kap");
      if (hepsiKap) hepsiKap.hidden = false;
      hepsiniSec.addEventListener("change", function () {
        var isaretle = hepsiniSec.checked;
        gorunenKutular().forEach(function (k) { k.checked = isaretle; });
        say();
      });
    }
    grupKutulari.forEach(function (g) {
      var etiket = g.closest("label");
      if (etiket) etiket.hidden = false;
      g.addEventListener("change", function () {
        var isaretle = g.checked;
        grupKutulariOf(g).forEach(function (k) { k.checked = isaretle; });
        say();
      });
    });
    if (secimTemizle) {
      secimTemizle.hidden = false;
      secimTemizle.addEventListener("click", function () {
        kutular.forEach(function (k) { k.checked = false; });
        say();
        duyur("Seçim temizlendi.");
        if (hepsiniSec) hepsiniSec.focus(); // çubuk gizlenince odak kaybolmasın
      });
    }
    form.classList.add("js-secim");

    // Enter (ikinci kat; asıl koruma formun başındaki devre dışı nöbetçi düğmedir): seçim kutusunda Enter formu
    // örtük gönderip ilk satırın düğmesini tıklamasın. Düğme, bağlantı ve menü özetinde Enter olağan çalışır.
    form.addEventListener("keydown", function (olay) {
      if (olay.key !== "Enter") return;
      var h = olay.target;
      if (h && h.tagName === "INPUT" && h.type === "checkbox") olay.preventDefault();
    });

    // Canlı tazelemede az önce değişen düğme tıklama almaz (yanlış komuta basılmasın).
    form.addEventListener("click", function (olay) {
      var d = olay.target.closest && olay.target.closest("[data-degisti]");
      if (!d) return;
      if (Date.now() - (parseInt(d.getAttribute("data-degisti"), 10) || 0) < DUGME_KORUMA_MS) {
        olay.preventDefault();
        olay.stopPropagation();
      }
    }, true);

    function veri(tr) { return sonVeri.get(String(tr.getAttribute("data-id"))); }
    pano = {
      form: form,
      seciliSatirlar: seciliSatirlar,
      satirAdi: function (tr) { return tr.getAttribute("data-ad") || ""; },
      uyar: duyur,
      sinavdakiSayisi: function () {
        return seciliSatirlar().filter(function (tr) { var t = veri(tr); return !!(t && t.sinav); }).length;
      },
      // Tek satır (satır düğmesi / satır menüsü): o tahta sınav penceresinde mi?
      sinavdaMi: function (id) { var t = sonVeri.get(String(id)); return !!(t && t.sinav); },
      etkiOzeti: function (secili) {
        var oturumlu = 0;
        var cevrimdisi = 0;
        secili.forEach(function (tr) {
          var t = veri(tr);
          if (!t) return;
          if (t.oturum_acik) oturumlu++;
          if (!t.cevrimici) cevrimdisi++;
        });
        var c = [];
        if (oturumlu) c.push(oturumlu + " tahtada açık oturum var; derste kullanılıyor olabilir.");
        if (cevrimdisi) c.push(cevrimdisi + " tahta çevrimdışı; 2 dakika içinde bağlanmazsa komut düşer.");
        return c;
      },
      tekOzeti: function (id) {
        var t = sonVeri.get(String(id));
        var c = [];
        if (!t) return c;
        if (t.oturum_acik) c.push(ETKI.oturum);
        if (!t.cevrimici) c.push(ETKI.cevrimdisi);
        return c;
      }
    };

    var ilkListe = [];
    try { ilkListe = JSON.parse(ilk.textContent || "[]"); } catch (e) { ilkListe = []; }
    ciz(ilkListe, true);
    // Sunucunun çizdiği süzgeç (hidden + disabled) geçerlidir; geri/ileri önbelleğinden dönen sayfada kutular
    // tarayıcının hatırladığı durumda olabilir, bu yüzden bir kez de burada uygulanır.
    suzgecUygula();
    durumYoklayici(function (v) {
      ciz(v.tahtalar || [], false);
      if (typeof v.bekleyen === "number" && v.bekleyen !== (panoVeri.bekleyen || 0)) yenileGoster();
      canliYaz(true);
    }, function () { canliYaz(false); });
  }

  /* ---- bugun: Bugün sayfasının canlı sayıları, çipleri ve program satırı (0.18.0) ------------------
     Kural hesaplanmaz: /api/durum'un tahta başına verdiği `liste` (birincil, durumlar, rozetler), `cevrimici` ve
     `sinav` alanları yazılır ve sayılır. Bekleyen işlerin METNİ sunucudadır: liste değişince (imza) satırlar yeniden
     yazılmaz, "Sayfayı yenile" bandı açılır. Yoklama ve duyuru kutuları canlı değildir. */
  var CIP_SIMGESI = { acik: "s-acik", kilitli: "s-kilit", duyuru: "s-duyuru", sorun: "s-sorun", cevrimdisi: "s-kapali" };
  var GRUP_OZETI = [["acik", "açık"], ["kilitli", "kilitli"], ["duyuru", "duyuruda"], ["sorun", "ekran sorunu"], ["cevrimdisi", "çevrimdışı"]];

  function bugunKur() {
    var kart = $("bugun-tahtalar");
    if (!kart) return;
    // 0.17.0'da "/" listeydi: /#t-3 biçimindeki eski dönüş adresi listedeki satıra gider (parça sunucuya ulaşmaz).
    var eskiParca = /^#t-([1-9][0-9]*)$/.exec(location.hash || "");
    if (eskiParca) { location.replace("/tahtalar#t-" + eskiParca[1]); return; }
    var veri = {};
    try { veri = JSON.parse(($("bugun-veri") || {}).textContent || "{}"); } catch (e) { veri = {}; }
    var bilinen = {};
    (veri.tahtalar || []).forEach(function (id) { bilinen[String(id)] = true; });
    var bilinenSayisi = (veri.tahtalar || []).length;
    var grupOf = veri.gruplar || {};
    var cipler = new Map();
    Array.prototype.forEach.call(kart.querySelectorAll("a.cip[data-id]"), function (a) {
      cipler.set(String(a.getAttribute("data-id")), a);
    });
    // Sayı kutuları iki yerde çizilir (kartta ve telefonda "Şu an"ın altında); ikisine de yazılır.
    var kutular = Array.prototype.slice.call(document.querySelectorAll("#bugun-ozet a[data-sayi], #bugun-ozet-kisa a[data-sayi]"));
    var form = $("hepsini-kilitle");
    var yenile = $("bugun-yenile");
    var canliBolge = $("canli-bolge");
    var ozet = $("tahta-ozet");
    var sinavNotu = kart.querySelector('[data-alan="sinavda"]');
    var canliEl = $("canli");
    if (canliEl) canliEl.hidden = false; // JS'siz sayfada "Canlı" yazmaz (sayılar tazelenmez)
    var canliYaz = canliGostergesi(canliEl);
    var programYaz = programYazici($("bugun-simdi"));
    var cipImzalari = new Map();

    var genelYenile = false; // bekleyen işler / tahta listesi değişti (acil dışı neden)
    var genelMetin = "";
    function yenileGoster(metin) {
      if (!yenile) return;
      var yazi = yenile.querySelector('[data-alan="yenile-metni"]');
      if (yazi && !genelMetin) genelMetin = yazi.textContent;
      if (!metin) {
        genelYenile = true;
        if (!yenile.hidden) return; // acil sözü yazılıysa o kalır; acil bitince genel söze dönülür (acilYaz)
        if (yazi) yazi.textContent = genelMetin;
      } else if (yazi && yazi.textContent !== metin) {
        yazi.textContent = metin; // acil başladı/bitti: genel "bekleyen işler değişti" sözünün yerine geçer
      } else if (!yenile.hidden) {
        return;
      }
      yenile.hidden = false;
      if (canliBolge) canliBolge.textContent = yenile.textContent.trim();
    }

    /* Sayfa açıkken acil yayın başlarsa "Hepsini kilitle…" hemen kapanır (yeniden yüklenen sayfa formu hiç çizmez).
       Kural değil, sunucunun `acil` bayrağıdır; yayın sayfa yenilenmeden biterse düğme geri açılır. */
    var acilGorulen = !!veri.acil;
    function acilYaz(suruyor) {
      if (suruyor === acilGorulen) return;
      acilGorulen = suruyor;
      var dugme = form && form.querySelector("button[data-onay]");
      var notu = $("kilit-notu");
      if (dugme) dugme.disabled = suruyor;
      if (notu) notu.textContent = suruyor ? "Acil yayın sürüyor; toplu kilit kapalı." : "";
      if (suruyor !== !!veri.acil) {
        yenileGoster(suruyor ? "Acil yayın başladı." : "Acil yayın bitti.");
      } else if (yenile && !yenile.hidden) {
        // Sayfa yüklendiği andaki duruma dönüldü: acil sözü kalkar; başka neden varsa genel söz, yoksa bant kapanır.
        var yazi = yenile.querySelector('[data-alan="yenile-metni"]');
        if (genelYenile && yazi) yazi.textContent = genelMetin; else yenile.hidden = true;
      }
    }

    function cipYaz(a, t) {
      var l = t.liste;
      var ekler = [];
      if ((l.durumlar || []).indexOf("ariza") >= 0) ekler.push("ariza");
      if (t.sinav) ekler.push("sinav");
      var okunur = (l.rozetler || []).filter(function (r) { return r.cip !== false; }).map(function (r) { return r.m; }).join(", ");
      var imza = l.birincil + "|" + ekler.join(",") + "|" + okunur;
      if (cipImzalari.get(a) === imza) return;
      var ilk = !cipImzalari.has(a);
      cipImzalari.set(a, imza);
      if (ilk && a.getAttribute("data-durum") === l.birincil && (a.querySelector('[data-alan="okunur"]') || {}).textContent === okunur) return;
      a.setAttribute("data-durum", l.birincil);
      var use = a.querySelector("svg.simge use");
      if (use && CIP_SIMGESI[l.birincil]) use.setAttribute("href", "#" + CIP_SIMGESI[l.birincil]);
      var ekKap = a.querySelector('[data-alan="ek"]');
      if (ekKap) {
        ekKap.textContent = "";
        ekler.forEach(function (e) {
          var sp = document.createElement("span");
          sp.className = "cip-ek";
          sp.setAttribute("data-durum", e === "ariza" ? "sorun" : "uyari");
          sp.appendChild(simge(e === "ariza" ? "s-ariza" : "m-sinav")); // durum simgelerinden ayrı şekiller (_bugun.html::cip)
          ekKap.appendChild(sp);
        });
      }
      var ok = a.querySelector('[data-alan="okunur"]');
      if (ok) ok.textContent = okunur;
    }

    function ciz(v) {
      var liste = v.tahtalar || [];
      var sayi = {};
      var grupSayisi = {};
      var cevrimici = 0;
      var hedef = 0;
      var sinavCevrimici = 0;
      var sinavToplam = 0;
      var bilinmeyen = liste.length !== bilinenSayisi;
      liste.forEach(function (t) {
        var id = String(t.id);
        if (!bilinen[id]) bilinmeyen = true;
        if (!t.liste) return;
        (t.liste.durumlar || []).forEach(function (d) { sayi[d] = (sayi[d] || 0) + 1; });
        if (t.sinav) sinavToplam++;
        if (t.cevrimici) {
          cevrimici++;
          if (t.sinav) sinavCevrimici++; else hedef++;
        }
        var a = cipler.get(id);
        if (a) cipYaz(a, t);
        var g = grupOf[id];
        if (g) {
          if (!grupSayisi[g]) grupSayisi[g] = {};
          grupSayisi[g][t.liste.birincil] = (grupSayisi[g][t.liste.birincil] || 0) + 1;
        }
      });
      kutular.forEach(function (a) {
        var n = sayi[a.getAttribute("data-sayi")] || 0;
        var b = a.querySelector("b");
        if (b) b.textContent = String(n);
        a.classList.toggle("bos", n === 0);
      });
      if (ozet) {
        var hepsi = ozet.querySelector('[data-alan="hepsi"]');
        if (hepsi) hepsi.textContent = String(liste.length);
        var c = ozet.querySelector('[data-alan="cevrimici"]');
        if (c) c.textContent = String(cevrimici);
      }
      if (sinavNotu) {
        sinavNotu.hidden = !sinavToplam;
        var ss = sinavNotu.querySelector('[data-alan="sinav-sayi"]');
        if (ss) ss.textContent = String(sinavToplam);
      }
      if (form) {
        form.setAttribute("data-hedef", String(hedef));
        form.setAttribute("data-sinavda", String(sinavCevrimici));
        form.setAttribute("data-cevrimdisi", String(liste.length - cevrimici));
      }
      Array.prototype.forEach.call(kart.querySelectorAll(".harita-kat[data-grup]"), function (kat) {
        var hucre = kat.querySelector('[data-alan="grup-ozet"]');
        if (!hucre) return;
        var gs = grupSayisi[kat.getAttribute("data-grup")] || {};
        hucre.textContent = GRUP_OZETI.filter(function (o) { return gs[o[0]]; }).map(function (o) { return gs[o[0]] + " " + o[1]; }).join(" · ");
      });
      if (bilinmeyen) yenileGoster();
    }

    durumYoklayici(function (v) {
      if (v.program) programYaz(v.program);
      ciz(v);
      if (typeof v.bekleyen === "number" && v.bekleyen !== (veri.bekleyen || 0)) yenileGoster();
      if (v.bekleyen_is && typeof v.bekleyen_is.imza === "string" && v.bekleyen_is.imza !== (veri.imza || "")) yenileGoster();
      acilYaz(!!v.acil); // acil başladı/bitti: toplu kilit kapanır/açılır, bant "Sayfayı yenile" der
      canliYaz(true);
    }, function () { canliYaz(false); });
  }

  // Tahta sayfasının eski parça adresleri (/tahta/3#program …) sunucuya gitmez: sekme yoksa ilgili sekmeye taşınır.
  var TAHTA_ESKI_PARCA = {
    program: "program", envanter: "bakim", arizalar: "bakim", temizlik: "bakim", baglanti: "bakim",
    "tani-baslik": "bakim", "komut-baslik": "bakim", "tahta-bilgi": "bilgiler"
  };
  function tahtaEskiParcaKur() {
    var parca = (location.hash || "").slice(1);
    if (!parca || !/^\/tahta\/\d+$/.test(location.pathname) || /[?&]sekme=/.test(location.search)) return;
    if (!Object.prototype.hasOwnProperty.call(TAHTA_ESKI_PARCA, parca)) return;
    var sorgu = location.search ? location.search + "&" : "?";
    location.replace(location.pathname + sorgu + "sekme=" + TAHTA_ESKI_PARCA[parca] + "#" + parca);
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

  /* ---- ayarlar (0.16.0): kaydedilmemiş değişiklik çubuğu, Ayarlar içi arama, eski parça adresleri ----------
     Hepsi ilerlemeli iyileştirmedir: JS yokken her form kendi Kaydet düğmesiyle gönderilir, arama GET ?ara= ile
     sunucuda süzülür, eski parça adresinde giriş sayfası açılır. */

  // Formun durumu: ad=değer çiftleri. Dosya ve gizli alan sayılmaz; parola alanının değeri SAKLANMAZ (yalnız "dolu mu").
  // varsayilan=true ise sunucunun çizdiği değerler okunur (tarayıcı geri dönüşte alanları eski yazılanla doldurabilir).
  function formDurumu(form, varsayilan) {
    var parcalar = [];
    Array.prototype.forEach.call(form.elements, function (e) {
      var tur = (e.type || "").toLowerCase();
      if (!e.name || tur === "file" || tur === "hidden" || tur === "submit" || tur === "button" || tur === "reset") return;
      var deger;
      if (tur === "checkbox" || tur === "radio") {
        deger = (varsayilan ? e.defaultChecked : e.checked) ? "1" : "";
        parcalar.push(e.name + ":" + e.value + "=" + deger);
        return;
      }
      if (tur === "select-one" || tur === "select-multiple") {
        deger = Array.prototype.filter.call(e.options, function (o) { return varsayilan ? o.defaultSelected : o.selected; })
          .map(function (o) { return o.value; }).join(",");
        if (varsayilan && !deger && tur === "select-one" && e.options.length) deger = e.options[0].value;
      } else {
        deger = varsayilan ? e.defaultValue : e.value;
      }
      if (tur === "password") deger = deger ? "dolu" : "";
      parcalar.push(e.name + "=" + deger);
    });
    return parcalar.join("\u0001");
  }

  function ayarKirliKur() {
    var formlar = document.querySelectorAll("form[data-kirli-izle]");
    if (!formlar.length) return;
    var gonderilen = null;
    Array.prototype.forEach.call(formlar, function (form) {
      var ilk = formDurumu(form, true);
      var yok = form.querySelector(".kc-yok");
      var degisti = form.querySelector(".kc-var");
      var vazgec = form.querySelector(".kc-vazgec");
      form.classList.add("izleniyor");
      function guncelle() {
        var kirli = formDurumu(form, false) !== ilk;
        form.classList.toggle("kirli", kirli);
        if (yok) yok.hidden = kirli;
        if (degisti) degisti.hidden = !kirli;
        if (vazgec) vazgec.hidden = !kirli;
      }
      form.addEventListener("input", guncelle);
      form.addEventListener("change", guncelle);
      form.addEventListener("reset", function () {
        // Alanlar reset olayından SONRA ilk değerine döner; renk çıktıları, önizleme ve sayaçlar "input" dinler.
        setTimeout(function () {
          Array.prototype.forEach.call(form.querySelectorAll('input[type="color"], textarea'), function (alan) {
            alan.dispatchEvent(new Event("input", { bubbles: true }));
          });
          guncelle();
        }, 0);
      });
      guncelle();
    });
    // Gönderilen formun kendisi uyarmaz (Kaydet, onay penceresi); sayfadaki BAŞKA bir formda değişiklik kaldıysa uyarır.
    document.addEventListener("submit", function (olay) {
      gonderilen = olay.target;
      setTimeout(function () { gonderilen = null; }, 2000); // kullanıcı sayfada kalmayı seçerse uyarı yeniden çalışsın
    });
    window.addEventListener("beforeunload", function (olay) {
      var kalan = Array.prototype.some.call(formlar, function (f) { return f !== gonderilen && f.classList.contains("kirli"); });
      if (!kalan) return;
      olay.preventDefault();
      olay.returnValue = "";
    });
  }

  // "Kodu göster" (Ayarlar › Kilit ve güvenlik): adsız onay kutusu, data-goster'deki parola alanını düz metne çevirir.
  // Kutu JS'siz gizlidir; "Vazgeç" (reset) kutuyu boşaltınca alan yeniden gizlenir.
  function kodGosterKur() {
    Array.prototype.forEach.call(document.querySelectorAll("input[data-goster]"), function (kutu) {
      var alan = document.getElementById(kutu.getAttribute("data-goster"));
      if (!alan) return;
      var etiket = kutu.closest("label");
      if (etiket) etiket.hidden = false;
      function uygula() { alan.type = kutu.checked ? "text" : "password"; }
      kutu.addEventListener("change", uygula);
      if (kutu.form) kutu.form.addEventListener("reset", function () { setTimeout(uygula, 0); });
      uygula();
    });
  }

  // Harf katlama: ayar_bolumleri.KATLA_KAYNAK / KATLA_HEDEF ile AYNI dizgiler (test karşılaştırır).
  var AYAR_KATLA_KAYNAK = "çğıöşüâîû";
  var AYAR_KATLA_HEDEF = "cgiosuaiu";
  function ayarKatla(metin) {
    return metin.replace(/[^\u0000-\u007f]/g, function (h) {
      var sira = AYAR_KATLA_KAYNAK.indexOf(h);
      return sira < 0 ? h : AYAR_KATLA_HEDEF.charAt(sira);
    });
  }
  function ayarSozcukleri(metin) {
    return metin.toLocaleLowerCase("tr").split(/[^0-9a-zçğıöşüâîû-]+/).filter(Boolean);
  }

  // Kural sunucudakiyle (ayar_bolumleri.ara) aynıdır: her sorgu sözcüğü samanlıktaki bir sözcüğün BAŞINDA geçmeli;
  // önce data-ara (Türkçe küçük harf), hiçbir satır eşleşmezse harf katlanarak data-ara-kat.
  function ayarAraKur() {
    var kutu = document.querySelector("input[data-ayar-ara]");
    var kapsam = $("ayar-kapsam");
    if (!kutu || !kapsam) return;
    var satirlar = Array.prototype.slice.call(kapsam.querySelectorAll("li[data-ara]"));
    var kartlar = Array.prototype.slice.call(kapsam.querySelectorAll(".ayar-kume, .baska-yerde"));
    var baska = $("baska-yerde");
    var sonuc = $("ayar-ara-sonuc");
    var bos = $("ayar-ara-bos");
    var kumeler = kapsam.querySelector(".ayar-kumeler");
    var kurulum = $("kurulum");
    function uyar(sorgu, saman) {
      var sozcukler = saman.split(" ");
      return sorgu.every(function (q) { return sozcukler.some(function (s) { return s.indexOf(q) === 0; }); });
    }
    function suz() {
      var sorgu = ayarSozcukleri(kutu.value);
      var etkin = sorgu.length > 0;
      var eslesen = [];
      if (etkin) {
        eslesen = satirlar.filter(function (s) { return uyar(sorgu, s.getAttribute("data-ara") || ""); });
        if (!eslesen.length) {
          var katli = sorgu.map(ayarKatla);
          eslesen = satirlar.filter(function (s) { return uyar(katli, s.getAttribute("data-ara-kat") || ""); });
        }
      }
      satirlar.forEach(function (s) {
        s.hidden = etkin ? eslesen.indexOf(s) < 0 : !!(baska && baska.contains(s));
      });
      kartlar.forEach(function (k) { k.hidden = !k.querySelector("li[data-ara]:not([hidden])"); });
      if (bos) bos.hidden = !etkin || eslesen.length > 0;
      if (sonuc) sonuc.textContent = etkin ? eslesen.length + " sonuç" : "";
      if (kumeler) kumeler.classList.toggle("suzulu", etkin);
      if (kurulum) kurulum.hidden = etkin;
    }
    kutu.addEventListener("input", suz);
    // Tek satır eşleşiyorsa Enter doğrudan oraya götürür; yoksa form (GET ?ara=) sunucuda süzer.
    kutu.form.addEventListener("submit", function (olay) {
      var gorunen = satirlar.filter(function (s) { return !s.hidden; });
      var baglanti = gorunen.length === 1 && ayarSozcukleri(kutu.value).length ? gorunen[0].querySelector("a") : null;
      if (!baglanti) return;
      olay.preventDefault();
      location.assign(baglanti.getAttribute("href"));
    });
    if (kutu.value) suz(); // geri dönüşte tarayıcının doldurduğu sorgu
  }

  // Eski tek sayfanın parça adresi (/ayarlar#saklama …) sunucuya gitmez: giriş sayfasındaki eşlemeyle yönlendirilir.
  function ayarEskiParcaKur() {
    var veri = $("ayar-eski-parca");
    var parca = (location.hash || "").slice(1);
    if (!veri || !parca) return;
    var harita;
    try { harita = JSON.parse(veri.textContent || "{}"); } catch (e) { return; }
    if (!Object.prototype.hasOwnProperty.call(harita, parca)) return;
    var hedef = harita[parca];
    if (typeof hedef === "string" && hedef.charAt(0) === "/" && hedef.charAt(1) !== "/") location.replace(hedef);
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
    // Tahta listesinde satır komutundan dönüş (#t-<id>): ileti o satırda da çizilir (.satir-ileti) ve o odaklanır;
    // sayfa zaten satıra kaydığı için odak sayfayı yeniden kaydırmaz.
    var bant = document.querySelector(".satir-ileti[data-odakla], .bant[data-odakla]");
    if (!bant) return;
    var kaydirma = location.hash === "#ileti" || bant.classList.contains("satir-ileti");
    var odakla = function () { setTimeout(function () { bant.focus({ preventScroll: kaydirma }); }, 0); };
    if (document.readyState === "complete") odakla();
    else window.addEventListener("load", odakla, { once: true });
  }

  /* ---- kabuk: dar ekranda yan menü çekmecesi (0.15.0) --------------------------------
     JS'siz de çalışır: <a href="#menu"> çekmeceyi :target ile açar, #icerik kapatır. Burada sınıfla açılır
     (adrese parça yazılmaz), arkadaki sayfa inert olur, Esc kapatır ve odak açan düğmeye döner.
     Kip (çekmece / sabit) yalnız stil.css'tedir: --kb-kip okunur, genişlik eşiği burada yinelenmez. */
  var kabukCekmeceAc = null; // kabukKur kurar: çekmece kipindeyse çekmeceyi açar (genel aramanın "/" kısayolu kullanır)
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
      var etkin = menu.querySelector('.yan-gezinme a[aria-current="page"]');
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
    kabukCekmeceAc = function (tetik) { ac(tetik); return acikMi(); };
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

  /* ---- menu: açılır menüler (<details>) — JS'siz de çalışır; burada kapanış ve açılış yönü --- */
  var MENU_SECICI = "details.durdur-menu, details.satir-menu";
  function menuKur() {
    // "Program kilidini durdur", satırın "⋯" menüsü ve "Diğer" menüleri: aynı anda tek menü açık kalır.
    var gruplar = Array.prototype.slice.call(document.querySelectorAll(MENU_SECICI));
    if (!gruplar.length) return;
    function kapat(haric) {
      gruplar.forEach(function (g) { if (g !== haric) g.open = false; });
    }
    gruplar.forEach(function (g) {
      var sabitYon = g.classList.contains("yukari"); // seçim çubuğunun menüsü hep yukarı açılır
      g.addEventListener("toggle", function () {
        if (!g.open) return;
        kapat(g);
        // Yön GÖRÜNTÜ ALANINA göre seçilir (belgenin sonuna göre değil): üstte yapışkan üst çubuk, altta telefonun
        // alt çubuğu ve seçim çubuğu düşülür. Hiçbir yöne sığmayan liste kendi içinde kayar (liste kabı kaydırma
        // kabı değildir; kayan yalnız listenin kendisidir): "Kapat…" ekran dışında ya da alt çubuğun arkasında kalmaz.
        var liste = g.querySelector(".menu-liste");
        if (!liste) return;
        liste.style.maxBlockSize = "";
        if (!sabitYon) g.classList.remove("yukari");
        var ozet = g.querySelector("summary").getBoundingClientRect();
        var ustSinir = 0;
        var altSinir = window.innerHeight;
        var ustCubuk = document.querySelector(".ust-cubuk");
        if (ustCubuk) {
          var uk = ustCubuk.getBoundingClientRect();
          if (uk.height && uk.top <= 0 && uk.bottom > 0) ustSinir = uk.bottom;
        }
        [document.querySelector(".alt-cubuk"), g.closest(".secim-cubugu") ? null : $("secim-cubugu")].forEach(function (o) {
          if (!o) return;
          var k = o.getBoundingClientRect();
          if (k.height && k.top > ozet.bottom && k.top < altSinir) altSinir = k.top;
        });
        var pay = 12;
        var asagi = altSinir - ozet.bottom - pay;
        var yukari = ozet.top - ustSinir - pay;
        var boy = liste.getBoundingClientRect().height;
        if (sabitYon) { // seçim çubuğu ekrana yapışıktır: sayfa kaydırmak yer açmaz
          if (boy > yukari) liste.style.maxBlockSize = Math.max(yukari, 132) + "px";
          return;
        }
        if (boy <= asagi) return;
        if (boy <= yukari) { g.classList.add("yukari"); return; }
        // İki yöne de sığmıyor: sayfa, liste bütünüyle görünecek kadar kaydırılır (özet görünür kalıyorsa);
        // o da olmuyorsa (kısa pencere, sayfanın başı/sonu) liste kendi içinde kayar.
        var kok = document.scrollingElement || document.documentElement;
        var eksik = boy - asagi;
        if (ozet.top - eksik >= ustSinir + pay && kok.scrollHeight - window.innerHeight - window.scrollY >= eksik) {
          window.scrollBy(0, eksik);
          return;
        }
        eksik = boy - yukari;
        if (ozet.bottom + eksik <= altSinir - pay && window.scrollY >= eksik) {
          g.classList.add("yukari");
          window.scrollBy(0, -eksik);
          return;
        }
        if (yukari > asagi) g.classList.add("yukari");
        liste.style.maxBlockSize = Math.max(Math.max(yukari, asagi), 132) + "px";
      });
    });
    document.addEventListener("click", function (olay) {
      var icinde = olay.target.closest && olay.target.closest(MENU_SECICI);
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

  /* ---- genel arama (0.20.0): yan menüdeki kutu ------------------------------------------------
     JS'siz de çalışır: form düz GET /ara'dır. Burada yazarken öneri (combobox + listbox) ve "/" kısayolu eklenir.
     Eşleştirme YALNIZ sunucudadır (/api/ara): dizin, kural ve harf haritası buraya kopyalanmaz. Sorgu tarayıcıda
     hiçbir yere yazılmaz (kalıcı depo, çerez yok). Bütün metin textContent ile basılır; hedef yalnız site içi yoldur.
     Kip (çekmece / sabit) burada yinelenmez: kutunun görünürlüğüne bakılır. Sonuç sayfasının kendi kutusu
     (data-ara-oneri) AYNI kodla öneri verir. Kısayol sayfadan AYIRMAZ: kutu görünmüyorsa çekmece açılır. */
  var ARAMA_BEKLEME_MS = 150;
  var ARAMA_EN_KISA = 2;
  // "/" bu tür girdilerde yazı değildir; öbür bütün girdilerde (metin, arama, sayı, tarih, parola…) kısayol çalışmaz.
  var ARAMA_YAZISIZ = ["checkbox", "radio", "button", "submit", "reset", "range", "file", "color"];
  function aramaKur() {
    var kutu = document.querySelector("input[data-genel-ara]");
    if (!kutu || !kutu.form) return; // kabuksuz sayfa (giriş, ilk kurulum)
    aramaOneriKur(kutu, "genel-oneri");
    var sayfaKutusu = document.querySelector("input[data-ara-oneri]"); // yalnız /ara sayfasında
    if (sayfaKutusu && sayfaKutusu.form) aramaOneriKur(sayfaKutusu, "sayfa-oneri");

    // Kısayol "/": yazı yazılan yerde, değiştirici tuşla ve onay diyaloğu açıkken TETİKLENMEZ.
    function gorunur(o) {
      return !!o && o.getClientRects().length > 0 && getComputedStyle(o).visibility !== "hidden";
    }
    document.addEventListener("keydown", function (olay) {
      if (olay.key !== "/" || olay.ctrlKey || olay.altKey || olay.metaKey || olay.defaultPrevented) return;
      if (document.querySelector("dialog[open]")) return;
      var h = olay.target;
      if (h && h.closest && (h.isContentEditable || h.closest("textarea, select, [contenteditable]"))) return;
      if (h && h.tagName === "INPUT" && ARAMA_YAZISIZ.indexOf((h.getAttribute("type") || "text").toLowerCase()) < 0) return;
      // Sıra: görünen yan menü kutusu → sonuç sayfasının kutusu → çekmece açılır. Sayfadan HİÇ ayrılmaz (yarım
      // kalmış form, fırçayla çalışılan şube defteri tek tuşla kaybolmasın); çekmece açılamıyorsa tuş olağan kalır.
      var hedef = gorunur(kutu) ? kutu : (gorunur(sayfaKutusu) ? sayfaKutusu : null);
      if (!hedef) {
        var tetik = document.activeElement && document.activeElement !== document.body ? document.activeElement : null;
        if (!kabukCekmeceAc || !kabukCekmeceAc(tetik) || !gorunur(kutu)) return;
        hedef = kutu;
      }
      olay.preventDefault();
      hedef.focus();
      hedef.select();
    });
  }
  function aramaOneriKur(kutu, listeKimligi) {
    var formu = kutu.form;
    var liste = document.createElement("div");
    liste.setAttribute("id", listeKimligi);
    liste.className = "ara-oneri";
    liste.setAttribute("role", "listbox");
    liste.setAttribute("aria-label", "Öneriler");
    liste.hidden = true;
    var durum = document.createElement("p");
    durum.className = "gizli";
    durum.setAttribute("role", "status");
    formu.appendChild(liste);
    formu.appendChild(durum);
    kutu.setAttribute("role", "combobox");
    kutu.setAttribute("aria-autocomplete", "list");
    kutu.setAttribute("aria-expanded", "false");
    kutu.setAttribute("aria-controls", listeKimligi);

    var secenekler = [];
    var etkin = -1;
    var sira = 0;
    var denetci = null;
    var zamanlayici = null;
    var cizilen = null; // listedeki önerilerin sorgusu (aynı sorguya odak dönünce yeniden istenmez)

    function sec(i) {
      etkin = i;
      secenekler.forEach(function (s, n) { s.setAttribute("aria-selected", n === i ? "true" : "false"); });
      if (i < 0) { kutu.removeAttribute("aria-activedescendant"); return; }
      kutu.setAttribute("aria-activedescendant", secenekler[i].getAttribute("id"));
      if (secenekler[i].scrollIntoView) secenekler[i].scrollIntoView({ block: "nearest" });
    }
    function kapat() {
      liste.hidden = true;
      kutu.setAttribute("aria-expanded", "false");
      sec(-1);
    }
    function ac() {
      if (!secenekler.length) return;
      liste.hidden = false;
      kutu.setAttribute("aria-expanded", "true");
    }
    function bosalt() {
      while (liste.firstChild) liste.removeChild(liste.firstChild);
      secenekler = [];
      cizilen = null;
      sec(-1);
    }
    function secenek(ad, yer, yol, sinif) {
      var a = document.createElement("a");
      a.setAttribute("role", "option");
      a.setAttribute("id", listeKimligi + "-" + secenekler.length);
      a.setAttribute("href", yol);
      a.setAttribute("tabindex", "-1");
      a.setAttribute("aria-selected", "false");
      if (sinif) a.className = sinif;
      var ust = document.createElement("span");
      ust.textContent = ad;
      a.appendChild(ust);
      if (yer) {
        var alt = document.createElement("span");
        alt.textContent = yer;
        a.appendChild(alt);
      }
      liste.appendChild(a);
      secenekler.push(a);
    }
    function sorguMetni() {
      return kutu.value.replace(/\s+/g, " ").trim();
    }
    function ciz(veri, sorgu) {
      var sonuclar = veri && Array.isArray(veri.sonuclar) ? veri.sonuclar : [];
      bosalt();
      sonuclar.forEach(function (s) {
        // Hedef yalnız site içi yol ("/" ile başlar; ikinci karakter "/" ya da "\" değil). Sunucu da garanti eder.
        if (!s || !siteIciYol(s.yol) || s.yol.charAt(1) === "\\") return;
        secenek(String(s.ad || ""), String(s.yer || ""), s.yol, "");
      });
      var toplam = parseInt(veri && veri.toplam, 10) || 0;
      var fazlasi = secenekler.length > 0 && toplam > secenekler.length;
      if (fazlasi) secenek("Tüm sonuçlar (" + toplam + ")", "", "/ara?q=" + encodeURIComponent(sorgu), "hepsi");
      cizilen = sorgu;
      // Duyurulan sayı ok tuşuyla gezilebilen önerilerin sayısıdır ("Tüm sonuçlar" satırı öneri sayılmaz).
      var oneri = fazlasi ? secenekler.length - 1 : secenekler.length;
      durum.textContent = !oneri ? "Öneri yok" : (fazlasi ? "İlk " + oneri + " öneri, toplam " + toplam + " sonuç" : oneri + " öneri");
      if (secenekler.length && document.activeElement === kutu) ac(); else kapat();
    }
    function iste() {
      var sorgu = sorguMetni();
      if (denetci) denetci.abort();
      denetci = null;
      var benim = ++sira; // geç gelen eski yanıt atılır
      if (sorgu.length < ARAMA_EN_KISA) { bosalt(); durum.textContent = ""; kapat(); return; }
      if (sorgu === cizilen) { ac(); return; }
      denetci = window.AbortController ? new AbortController() : null;
      fetch("/api/ara?q=" + encodeURIComponent(sorgu), {
        credentials: "same-origin", headers: { Accept: "application/json" }, signal: denetci ? denetci.signal : undefined
      }).then(function (yanit) {
        if (!yanit.ok) throw new Error("ara");
        return yanit.json();
      }).then(function (veri) {
        if (benim === sira) ciz(veri, sorgu);
      }).catch(function () {
        // 401 ya da ağ hatası: liste sessizce kapanır; Enter yine /ara'ya gider (oradan girişe yönlenir).
        if (benim === sira) { bosalt(); kapat(); }
      });
    }
    kutu.addEventListener("input", function () {
      sec(-1); // yazı değişti: eski sorgunun seçili önerisi Enter'la açılmasın
      clearTimeout(zamanlayici);
      zamanlayici = setTimeout(iste, ARAMA_BEKLEME_MS);
    });
    kutu.addEventListener("focus", function () {
      if (cizilen !== null && cizilen === sorguMetni()) ac();
    });
    kutu.addEventListener("keydown", function (olay) {
      var acik = !liste.hidden;
      if (olay.key === "ArrowDown" || olay.key === "ArrowUp") {
        if (!secenekler.length) return;
        olay.preventDefault();
        if (!acik) { ac(); sec(olay.key === "ArrowDown" ? 0 : secenekler.length - 1); return; }
        var n = secenekler.length;
        sec(olay.key === "ArrowDown" ? (etkin + 1) % n : (etkin <= 0 ? n - 1 : etkin - 1));
      } else if (olay.key === "Enter") {
        // Etkin seçenek varsa VE liste kutudaki yazının önerisiyse oraya; yoksa form gönderilir (GET /ara?q=…).
        if (acik && etkin >= 0 && cizilen === sorguMetni()) { olay.preventDefault(); location.assign(secenekler[etkin].getAttribute("href")); }
      } else if (olay.key === "Escape") {
        // Liste açıksa YALNIZ liste kapanır (çekmece ve açılır menüler kapanmasın; kutudaki yazı silinmesin).
        if (acik) { olay.preventDefault(); olay.stopPropagation(); kapat(); }
      } else if (olay.key === "Tab") {
        kapat();
      }
    });
    formu.addEventListener("focusout", function (olay) {
      if (!olay.relatedTarget || !formu.contains(olay.relatedTarget)) kapat();
    });
    // Seçeneğe basınca odak kutuda kalır: bağlantıya odak vermeyen tarayıcıda liste tıklamadan önce kapanmasın.
    liste.addEventListener("mousedown", function (olay) { olay.preventDefault(); });
    window.addEventListener("pagehide", kapat);
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
  /* 0.19.0 ekleri (görünüm; doğrulama sunucudadır): hızlı süre ve gün düğmeleri, tahta önizlemesi, gönder çubuğu
     özeti. "Bugün" sunucunun verdiği data-bugun'dan hesaplanır; tarayıcının saati KULLANILMAZ (yanlış saatli
     bilgisayarda plan yanlış güne düşerdi). Önizleme yalnız textContent ile yazılır. */
  function duyuruFormuKur() {
    var form = $("duyuru-formu");
    if (!form) return;
    form.classList.add("js-duyuru");
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

    // Gönder çubuğu özeti: sunucunun çizdiği metnin aynısı (hedef · zaman; süre · kapatılabilirlik).
    var ZAMAN_ADI = { hemen: "hemen", bir_kez: "bir kez", tekrarli: "tekrarlı" };
    function alanYaz(ad, metin) {
      var oge = form.querySelector('[data-alan="' + ad + '"]');
      if (oge) oge.textContent = metin;
    }
    function deger(ad) {
      var a = form.querySelector('input[name="' + ad + '"]');
      return a ? a.value : "";
    }
    function trTarih(iso) {
      var p = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
      return p ? p[3] + "." + p[2] + "." + p[1] : "";
    }
    // Zaman özeti: plan listesindeki "Zamanlama" sütunuyla (zamanlama.ozet) aynı biçim; eksik alan AÇIKÇA yazılır.
    // Yalnız gösterimdir: tarih/saat doğrulaması sunucudadır.
    function zamanMetni() {
      var z = secili(form, "zaman");
      if (z === "bir_kez") {
        var t = trTarih(deger("bir_tarih")), s = deger("bir_saat");
        if (t && s) return t + " " + s;
        return t ? t + " · saat seçilmedi" : (s ? "tarih seçilmedi · " + s : "tarih ve saat seçilmedi");
      }
      if (z === "tekrarli") {
        var tur;
        if (secili(form, "siklik") === "haftalik") {
          var gunler = Array.prototype.map.call(form.querySelectorAll('input[name="gun"]:checked'), function (g) {
            return (g.parentNode.textContent || "").trim();
          });
          tur = gunler.length ? "her hafta " + gunler.join(", ") : "her hafta · gün seçilmedi";
        } else {
          var sonu = form.querySelector('input[name="hafta_sonu"]');
          tur = sonu && sonu.checked ? "her gün" : "her gün (hafta içi)";
        }
        var saat = deger("tekrar_saat"), bas = trTarih(deger("baslangic")), bit = trTarih(deger("bitis"));
        return tur + " " + (saat || "· saat seçilmedi") + " · " + (bit ? (bas || "bugün") + "–" + bit : "bitiş seçilmedi");
      }
      return ZAMAN_ADI[z] || "zaman seçilmedi";
    }
    function ozetYaz() {
      alanYaz("ozet-zaman", zamanMetni());
      var sure = form.querySelector('input[name="sure_dk"]');
      var kapat = form.querySelector('input[name="kapatilabilir"]');
      if (sure) alanYaz("ozet-sure", sure.value || "—");
      if (kapat) alanYaz("ozet-kapat", kapat.checked ? "öğretmen kapatabilir" : "öğretmen kapatamaz");
    }

    // Tahta önizlemesi: başlık boşsa tahtadaki varsayılan başlık.
    function tahtaOnizle() {
      var baslik = form.querySelector('input[name="baslik"]');
      var metin = form.querySelector('textarea[name="metin"]');
      if (baslik) alanYaz("oniz-baslik", baslik.value.trim() || "DUYURU");
      if (metin) alanYaz("oniz-metin", metin.value);
    }

    // Hızlı süre düğmeleri (yalnız JS ile görünür).
    var sureAlani = form.querySelector('input[name="sure_dk"]');
    var hizliSure = form.querySelector("[data-hizli-sure]");
    if (hizliSure && sureAlani && !sureAlani.disabled) {
      hizliSure.hidden = false;
      hizliSure.addEventListener("click", function (olay) {
        var dugme = olay.target.closest ? olay.target.closest("[data-sure]") : null;
        if (!dugme) return;
        sureAlani.value = dugme.getAttribute("data-sure");
        ozetYaz();
      });
    }

    // Gün düğmeleri: sunucunun bugünü (form[data-bugun], YYYY-AA-GG) + n gün. Takvim hesabı UTC'de yapılır
    // (yaz saati kayması günü değiştirmesin); tarayıcının "şimdi"si okunmaz.
    var tarihAlani = form.querySelector('input[name="bir_tarih"]');
    var hizliGun = form.querySelector("[data-hizli-gun]");
    function gunTarihi(n) {
      var p = /^(\d{4})-(\d{2})-(\d{2})$/.exec(form.getAttribute("data-bugun") || "");
      if (!p) return "";
      var t = new Date(Date.UTC(parseInt(p[1], 10), parseInt(p[2], 10) - 1, parseInt(p[3], 10) + n));
      return t.toISOString().slice(0, 10);
    }
    function gunDugmeleri() {
      if (!hizliGun || !tarihAlani) return;
      Array.prototype.forEach.call(hizliGun.querySelectorAll("[data-gun]"), function (dugme) {
        var tarih = gunTarihi(parseInt(dugme.getAttribute("data-gun"), 10));
        dugme.setAttribute("aria-pressed", tarih && tarihAlani.value === tarih ? "true" : "false");
      });
    }
    if (hizliGun && tarihAlani && !tarihAlani.disabled && gunTarihi(0)) {
      hizliGun.hidden = false;
      hizliGun.addEventListener("click", function (olay) {
        var dugme = olay.target.closest ? olay.target.closest("[data-gun]") : null;
        if (!dugme) return;
        var tarih = gunTarihi(parseInt(dugme.getAttribute("data-gun"), 10));
        if (tarih) tarihAlani.value = tarih;
        gunDugmeleri();
        ozetYaz();
      });
      gunDugmeleri();
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
        sira++; // yoldaki eski yanıt artık yazılmaz
        alanYaz("ozet-hedef", "Tahta seçilmedi");
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
          if (!s.ok) { onizlemeYaz("s-sorun", "uyari", [s.v.hata || "Seçim okunamadı."]); alanYaz("ozet-hedef", "Seçim okunamadı"); return; }
          var v = s.v;
          alanYaz("ozet-hedef", v.sayi ? v.sayi + " tahtaya" : "Hiçbir tahtaya ulaşmıyor");
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
        .catch(function () {
          // Ağ hatasında özet ESKİ sayıda kalmaz (yanlış hedef güveni vermesin); sunucu doğrulaması aynıdır.
          if (benim === sira) alanYaz("ozet-hedef", "Tahta sayısı alınamadı");
        });
    }
    function gecikmeliOnizle() {
      clearTimeout(bekleme);
      sira++; // yoldaki eski yanıt artık yazılmaz
      alanYaz("ozet-hedef", "Tahta sayısı hesaplanıyor…"); // gecikme + istek süresince eski sayı görünmesin
      bekleme = setTimeout(onizle, 300);
    }

    form.addEventListener("change", function (olay) {
      kosullariUygula();
      ozetYaz();
      gunDugmeleri();
      var ad = olay.target && olay.target.name;
      if (["kime", "bina", "kat", "duzey", "devre", "grup", "hedef_tahta"].indexOf(ad) >= 0) gecikmeliOnizle();
    });
    form.addEventListener("input", function (olay) {
      var ad = olay.target && olay.target.name;
      if (ad === "baslik" || ad === "metin") tahtaOnizle();
      else ozetYaz(); // süre, tarih, saat: özet her tuşta güncel
      if (ad === "bir_tarih") gunDugmeleri();
    });
    kosullariUygula();
    ozetYaz();
    tahtaOnizle();
    // Özet yalnız JS ile görünür (JS'siz güncellenemeyeceği için sunucu `hidden` çizer).
    var ozetKutusu = form.querySelector('[data-alan="gonder-ozet"]');
    if (ozetKutusu) ozetKutusu.hidden = false;
    // Hata çizimi: ileti ilgili bölümde de durur; sayfa oraya kayar (sayfa başındaki ileti role="alert" ile okunur).
    var hataYeri = $("hata-yeri");
    if (hataYeri && hataYeri.scrollIntoView) hataYeri.scrollIntoView({ block: "center" });
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

  tahtalarKur();
  bugunKur();
  tahtaEskiParcaKur();
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
  aramaKur();
  menuKur();
  sayacKur();
  duyuruFormuKur();
  acilKur();
  yazdirKur();
  tekIndirmeKur();
  sablonKur();
  onayKur();
  ayarlarKur();
  ayarKirliKur();
  kodGosterKur();
  ayarAraKur();
  ayarEskiParcaKur();
  kopyalaKur();
  dogrulamaKur();
  iletiKur();
})();
