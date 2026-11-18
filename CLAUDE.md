# CLAUDE.md — Tahta Kontrol

Yerel geliştirme 0.15.0 (kullanıcı onayı 18.11.2026): panel arayüzünün yeniden düzeninde 1. aşama, "kabuk".
Sol kenar menüsü (üç küme, en çok on öğe, role göre çizilir), dar ekranda çekmece + yapışkan üst çubuk,
telefonda alt çubuk, Acil durum en üstte, ölçek belirteçleri, şekilli rozet, 44 px dokunma hedefi. YALNIZ
çerçeve değişti: sayfa içerikleri, adresler, POST uçları, veritabanı ve ajan aynı (sürüm statik dosya
önbelleği için yükseldi). `docs/surum-0.15.0.md`, tasarım §11.1 (aşama planı; 2–6. aşamalar AYRI onay
ister, kendiliğinden başlanmaz; taslağın soruları §17 69–79, önerilenler varsayıldı). Arayüz taslağı
(`taslak/`) depo dışında tutulur. Testlerle ve deneme sunucusunda başsız Edge ölçümüyle (uydurma veri)
denendi; dağıtılmadı, okul bilgisayarında, gerçek telefonda ve ekran okuyucuyla denenmedi.

Yerel geliştirme 0.14.0 (kullanıcı isteği 18.11.2026): ders yoklaması yeniden tasarlandı. Tahtada
kaydırmasız şube/ders saati seçimi, okul no sırasıyla "123 Ayşe Y." listesi, devrenin ilk dersinde "geç",
saate göre ders ön seçimi; panelde şube defteri (son beş öğretim günü + gün kipinde düzeltme), mazeret/izin
girişi ve son günler listesi. `docs/surum-0.14.0.md`, tasarım §14.2; kural 18, 19, 24 güncellendi, 33–35
eklendi. Ajan değişti (yetenek `yoklama_gec`). Testlerle, Debian 12 kabında (Xvfb) ekran ölçümüyle ve
tarayıcıda uydurma veriyle denendi; dağıtılmadı, gerçek ETAP'ta ve gerçek sınıfta denenmedi.

Yerel geliştirme 0.13.1: 0.13.0'ın bağımsız incelemesinde doğrulanan bulguların düzeltmesi
(seçmeli hücrede öğretmen adının ders başlığına karışması, kilit ekranı gün programı, önizleme
belleği, yüzer düğme). `docs/surum-0.13.1.md`. Dağıtılmadı; gerçek ETAP'ta denenmedi; 0.13.0 ile
öğretmen programı aktarılmışsa yeniden aktarılır. Aynı sürümde tek yeni özellik: sunucu GitHub'dan yeni
sürüm denetimi yapar (yalnız haber verir, kapatılabilir; kural 32, `docs/tasarim.md` §9.1).

0.13.0 kullanıcı kararı (17.11.2026): öğretmen programı bilgilendirme için
ayrı `/ogretmen-programi` yolunda PDF/XLS'den eşlenir; eski dolu/boş okuyucu
değişmez. Ham adlar yalnız önizleme belleğinde, kalıcı bağlantı mevcut öğretmen
kimliğidir. **Program hiçbir öğretmenin başka sınıf/ders yoklamasını engellemez.**
Kilit ekranında bugünün şube/ders/saat bilgisi gösterilir; öğretmen ve öğrenci
adları bu yola girmez. Bu talimat eski "programda öğretmen ve ders adı yok"
kuralına yalnız yeni öğretmen programı tablosu ve ders başlıkları için istisnadır;
istisna kural 12 ve 30'un içinde yazılıdır, ayrıştırıcı ve önizleme kural 31'dedir.
Program ajan diskine yazılmaz, gece yarısında bellek görünümü kalkar.

Yerel geliştirme 0.12.2: ETAP yüzer düğme için yönetilen yardımcı pencereler,
seat grab kaldırılması ve doğrudan dokunma desteği. `docs/surum-0.12.2.md`.
Gerçek ETAP'ta henüz denenmedi; kurulu sunucu/istemci değiştirilmedi.

Yerel geliştirme: 0.12.1 — ajan yanıt boyutu sınırları ve kesik yanıt denetimi.
Otomatik yedek ayrı tek işte çalışır; ortak kilitler ve 16 sn kapanış bütçesi korunur.
Dağıtılmadı; kurulu sunucu/istemciye dokunulmadı. Plan: `docs/gelistirme-plani.md`.

Okul ağında çalışan etkileşimli tahta kontrol ve duyuru sistemi. Bir bilgisayarda
**sunucu** (Windows hizmeti + durum penceresi), her tahtada **ajan** (Pardus ETAP, `.deb`).
İdare, paneli tarayıcıdan kullanıcı adıyla açar; diğer bilgisayarlara kurulum yoktur.

- Tasarım ve gerekçeler: `docs/tasarim.md` — "neden böyle?" sorusunun cevabı orada.
- Saha denemesi adımları ve doğrulanmamış varsayımlar: `docs/saha-denemesi.md`.
- Durum: **0.15.0, yerel geliştirme; dağıtılmadı** — saha denemesindeki sürüm 0.12.0'dır (0.15.0: panel
  arayüzü 1. aşama — sol menü, çekmece, alt çubuk, ölçek belirteçleri; yalnız sunucu, ajan değişmedi;
  testlerle ve başsız tarayıcı ölçümüyle (1366 ve 390 px, açık/koyu, uydurma veri) denendi, okul
  bilgisayarında ve gerçek telefonda denenmedi; tasarım §11.1; 0.14.0: ders yoklaması
  yeniden tasarımı — tahtada kaydırmasız seçim ekranı, okul no sıralı liste, geç, panelde şube defteri, mazeret
  ve son beş gün; testlerle, Debian 12 kabında (Xvfb) ekran ölçümüyle ve tarayıcıda uydurma veriyle denendi,
  gerçek ETAP'ta ve gerçek sınıfta denenmedi; tasarım §14.2; 0.13.1: 0.13.0
  inceleme bulguları, yukarıda, ve GitHub'dan yeni sürüm denetimi — gerçek ağla yalnız geliştirme ortamında
  denendi, kurulu hizmette ve okul ağında denenmedi; 0.13.0: öğretmen programı aktarımı (`/ogretmen-programi`, XLS + PDF ya da
  şube listesi) ve kilit ekranında bugünün şube/ders/saat programı, tasarım §12.5; yüzer düğme ve kilit
  programı yalnız Debian 12 kabında (Xvfb) ölçüldü; 0.12.0: ders programı sihirbazına beşinci kaynak — e-Okul
  "Haftalık Ders Programları" raporu (OOK11002_R01, .XLS): şube blokları ayrıştırılır, zil çizelgesi yoksa ya
  da uymuyorsa rapordaki saatlerden oluşturulur, şube eşlemesi zorunlu adımdır (raporda şube adı yok), her
  şubenin dersi şubenin tahtasına yazılır; yalnız sunucu, ajan değişmedi; bir okulun gerçek raporuyla yerel
  uçtan uca denendi; tasarım §12.4; 0.11.0: USB anahtar — bellekteki küçük anahtar dosyasıyla
  idareciler her tahtada yoklama alır, isteyen öğretmenlere de anahtar üretilir, ayar açıksa anahtar kilidi
  açar; takılınca yalnız küçük bildirim, yoklama/kilit dokunuşla; varsayılan kapalı; yalnız Debian 12 kabında
  loop bellekle (USB benzetimi) denendi, gerçek USB bellek ve ETAP'ta denenmedi; tasarım §14.1;
  0.10.0: Okul Zili'ne bağlı olmayan zil düzenleyicisi —
  adlandırılmış çizelgeler, haftalık düzen, tarihe özel çizelge, günü önizle, CSV; ders programını içe
  aktarma sihirbazı — aSc XML "deneme", şablon CSV/XLSX, yapay zekâ istemi, önceki programlar; yalnız
  sunucu, ajan değişmedi; tasarım §12.2–12.3; 0.9.0: gerçek ETAP tahtasındaki ilk saha bulguları G1–G3 —
  kurulum ve otomatik giriş betikleri yönetici yetkisini kendileri alır (sudo → pkexec → su, öğretmen
  oturumunda etapadmin parolası sorulur), tahtada yüzer düğme (Kilitle/Kapat/Yeniden başlat/Arıza/
  Yoklama; Ayarlar › Tahtadaki yüzer düğme), açılışta kilit (oturum açılınca ya da tahta açılınca sunucuya
  ulaşılıyorsa kilitlenir, kararı sunucu verir; Ayarlar › Açılışta kilit); tasarım §5.1;
  0.8.0: 16.11.2026 kararları — ikili eğitim, öğretim yılı sonuna
  kadar saklama, acil yayını bütün idareciler başlatır, boş ders uyarısı varsayılan açık + rapor, gün sonu
  oturum temizliği (K7, varsayılan kapalı; yalnız Debian 12 kabında denendi), sunucu Windows
  hizmeti (K8; birim testleri ve uçbirimde hizmet kipi, gerçek hizmet kurulumu denenmedi); 0.7.1:
  tahta ekranı ekran boyutuna orantılı). Pardus 25 (XFCE) masaüstünde denendi
  (0.1.1: kurulum, kilit, duyuru, kapatma, güncelleme çalıştı); 0.2.0'ın okul kimliği,
  0.3.0'ın duyuru planları, hedef grupları ve acil durum/tatbikat yayını, 0.4.0'ın ders
  programı/program kilidi, 0.5.0'ın sınav kipi/sınav yoklaması, 0.6.0'ın ders yoklaması ve
  0.7.0'ın altyapı çekirdeği (şifreli yedek, sunucu adres listesi, envanter, arıza bildirimi)
  yalnız Debian 12 kabında ve tarayıcıda denendi; gerçek bir ETAP tahtasında, gerçek Kelebek
  çizelgesiyle ve gerçek e-Okul sınıf listesiyle henüz denenmedi. Ajan paketi imzası yapılmadı.
- Ders programı ve program kilidi `docs/tasarim.md` §12 (öğretmen programı ve kilit ekranı gün programı §12.5); sınav kipi §13; ders yoklaması §14 (0.14.0 yeniden tasarımı §14.2);
  altyapı (yedek, adres listesi, envanter, arıza) §15, Windows hizmeti §15.6; yol haritası §16; okul idaresinin kesin
  kararları (K1–K8, 16.11.2026) ve kullanıcıya sorulacaklar §17; doğrulanacak dayanaklar §18.
  Kararlar yeniden tartışılmaz; bir kararla çelişen öneri yapılmaz.

## Komutlar (PowerShell 5.1; `&&` yok)

```powershell
uv sync                                   # bağımlılıklar (.venv, Python 3.12)
uv run python -m tahta_sunucu             # sunucu: http://127.0.0.1:8787 · https://<ip>:8788
uv run python -m tahta_sunucu pencere     # durum penceresi (hizmet yoksa sunucuyu pencerede çalıştırır)
uv run python -m tahta_sunucu paket x.deb # ajan paketini dosyaya yaz
uv run python -m tahta_sunucu hizmet --konsol   # hizmet kipini uçbirimde dene (Ctrl+C); hizmet KURMAZ
uv run python -m tahta_sunucu tasi --hedef D --kaynak K   # eski veriyi kopyala (kurucunun yaptığı)
uv run pytest -q                          # testler
uv run ruff check .                       # biçim denetimi
powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1   # Windows kurucusu
```

Ortam değişkenleri: `TAHTA_VERI_DIZINI` (varsayılan: geliştirmede `%LOCALAPPDATA%\TahtaKontrol`,
kurulu programda/hizmette `%PROGRAMDATA%\TahtaKontrol`; `ayar.veri_dizini_sec`), `TAHTA_HIZMET=1`
(hizmet kipi; giriş noktası ayarlar),
`TAHTA_HTTP_PORT` (8787, yalnız 127.0.0.1), `TAHTA_HTTPS_PORT` (8788, okul ağı).
Ajan: `TAHTA_AJAN_DIZIN`, `TAHTA_AJAN_DURUM`, `TAHTA_AJAN_BENZETIM=1` (kapatma komutu uygulanmaz).

## Yerleşim

```
tahta_sunucu/   FastAPI + SQLite + Jinja2 (HTMX yok, az miktar düz JavaScript)
  web.py        uygulama_olustur: oturum, pano, tahta, ayarlar, /marka/*, /ajan/* (uzun bekleme);
                MENU (0.15.0): üç küme (Her gün, Dönemlik, Yönetim), ≤ 10 üst öğe, öğede `rol`/`simge`/`esler`/
                `alt`/`alt_cubuk`; MENU_ACIL kümelerin dışında; menu_gorunumu → {kumeler, alt_cubuk} (rolle süzülür)
  panel_duyuru.py   duyuru/plan uçları, /api/hedef-onizleme   (web.py'den `kaydet(uygulama, y)` ile)
  panel_tahtalar.py gruplar, /tahtalar.csv ve CSV içe aktarma
  panel_acil.py     /acil: başlatma, bitirme, rapor
  panel_program.py  /program (sekmeler: zil, derslik, kurallar, istisnalar), /program/uyarilar, /tahta/{id}/program;
                    zil_baglami (zil sekmesinin çizelge kısmı), Okul Zili'nden al → cizelge.okulzili_yaz
  panel_cizelge.py  zil düzenleyici (0.10.0): /program/cizelge[/{id}[/hizli|kopyala|sil|csv]], /program/haftalik,
                    /program/tarihli[/{id}/sil], /program/gun (günü önizle); Etki: bugünkü plan değişirse açma
  panel_aktar.py    ders programı içe aktarma sihirbazı (0.10.0): /program/aktar[/asc|tablo|esle|onayla|sablon.csv|
                    mevcut.csv|istem.txt], /program/gecmis[/{id}/geri-yukle]; eski /program/derslik/yukle|onayla → 303;
                    0.12.0: /program/aktar/eokul (rapor yükleme), /program/aktar/eokul/zil (rapordan zil çizelgesi)
  panel_sinav.py    /sinavlar, /sinav/{id} (künye, eşleştirme, durum, uzatma, kip kaldırma, kodlar, şube
                    duyurusu, salon yoklaması, icmal), /api/sinav/{id}, /ajan/sinav/{kod,yoklama}
  panel_yoklama.py  /yoklama (günlük ızgara, kayıt/düzeltme, panelden gir, icmal + .csv, e-Okul işareti),
                    /ogretmenler (PIN pusulası), /ogrenciler (önizle/aktar/temizle), /ajan/yoklama/*;
                    sonunda şablon bağlamlarının SÖZLEŞME bloğu
  panel_defter.py   şube defteri ve mazeret uçları (0.14.0; `kaydet` panel_yoklama.kaydet içinden çağrılır):
                    /yoklama/sube (beş gün / gün kipi), /yoklama/sube/hucre (fırça; JSON ya da 303),
                    /yoklama/sube/toplu (Alındı iki adım, Bütün gün yok, Temizle), /yoklama/son-gunler,
                    /yoklama/ogrenci/{id}, /yoklama/mazeret[/onizle|onayla|{id}/iptal]; hepsi no-store
  panel_usb.py      USB anahtar (0.11.0): /usb-anahtarlar (üret, iptal), /usb-anahtarlar/indir/{belirtec} (tek
                    seferlik, 5 dk), /ajan/usb/{tani,yoklama,kilit_ac}; sonunda SÖZLEŞME bloğu
  panel_ogretmen_program.py  öğretmen programı (0.13.0): /ogretmen-programi[/onizle|vazgec|uygula]; yalnız yönetici;
                    dosya ayrıştırma iş parçacığı havuzunda; önizleme OnizlemeDeposu'nda (15 dk, Vazgeç'te silinir)
  usb_anahtar.py    USB anahtar iş mantığı (FastAPI'siz): ayar, dosya biçimi/ayrıştırıcı (ajandakiyle aynı),
                    bekleyen indirmeler, tanıma, PIN (öğretmen PIN'i ya da anahtar PIN'i), kopya uyarısı, iptal, yıl sonu
  panel_altyapi.py  /yedekler (parola, ayar, al, indir, geri-yukle + onay/uygula), /envanter (+ .csv),
                    /tahta/{id}/envanter, /tahta/{id}/donanim-goruldu, /arizalar, /ariza/{id}, /yerel/durum
  guncelleme.py GitHub'dan yeni sürüm denetimi (0.13.1, FastAPI'siz; kural 32): surum_coz/yanit_coz (saf), github_getir
                (tek GET, urllib), denetle (toplam ≤ 5 sn, hata dışarı çıkmaz), durum_al/gorunum (saklanan durum
                yeniden doğrulanır), Denetleyici (zamanla: günde bir, daemon iş parçacığı; simdi_denetle; durdur
                beklemez); uçlar web.py'de: Ayarlar › Güncelleme denetimi, POST /ayarlar/guncelleme/denetle
  yedek_is.py   otomatik yedeği ana zamanlayıcıyı bekletmeden ayrı tek işte yürütür (0.12.1; YedekIsleyici)
  yedek.py      şifreli yedek .tkyedek (scrypt → X25519 → HKDF → AES-GCM), saklama, ikinci kopya, geri yükleme
                (denetle → onay → açılışta bekleyeni_uygula); yedek.KILIT = vt.KILIT (göç ve yedek aynı kilitte)
  adresler.py   sunucu adres listesi (en çok 5): doğrulama, özet (ajanla aynı), eski sunucu_adresi geçişi
  envanter.py   ajanın gönderdiği envanteri saklar/gösterir, donanım kimliği değişimi, CSV
  ariza.py      arıza kayıtları: kategoriler, durum geçişleri, hareketler, tahtadan alma (yerel_id tekrarsız)
  sablonlar/    taban.html (0.15.0 kabuk: üst çubuk, yan menü `#menu`, perde, `main#icerik`, alt çubuk; `m-*`
                simgeleri; kabuk yalnız oturumlu ve `giris-sayfasi` olmayan sayfada — gövde sınıfı `kabuklu`);
                program.html, uyarilar.html ve ortak başları _program_bas.html (şerit + sekmeler);
                cizelge.html, program_gun.html, _zaman_cizgisi.html (SVG + liste makrosu), program_aktar.html,
                program_gecmis.html (0.10.0);
                sinavlar.html, sinav.html, sinav_yoklama.html, sinav_kodlar.html, sinav_icmal.html, _sinav.html;
                yoklama*.html, ogretmenler.html, ogretmen_program.html (0.13.0), ogretmen_pusula.html, ogrenciler.html, ogrenci_onizleme.html
                ve ortak başları _yoklama_bas.html (sekmeler + KVKK notu); usb_anahtarlar.html, usb_anahtar_uretildi.html;
                0.14.0: yoklama_sube.html (şube defteri), yoklama_son_gunler.html, yoklama_mazeret.html,
                yoklama_mazeret_onizleme.html, yoklama_ogrenci.html, _yoklama_hucre.html (hücre makrosu + lejant);
                yedekler.html, yedek_onay.html, yedek_geri_yukle.html, envanter.html, arizalar.html,
                ariza.html, _ariza.html (durum rozeti + açma formu makroları), _tahta_altyapi.html
  yoklama.py    ders yoklaması iş mantığı (FastAPI'siz): ayar, A3 uyarlama işlevleri, öneri (0.14.0: ders_kurali —
                süren → 5 dk içinde başlayacak → son 15 dk'da biten; teneffüste ders_adaylari; pencere_devresi;
                ogretmen_onerisi dar SELECT), gec_secilebilir, PIN kapısı (3 katman), belirteç, yoklama_yaz (upsert +
                iz; yok + geç + devre), gecerli_durum, günlük görünüm, icmal/metin/CSV, aktarım, imha
  yoklama_defter.py  şube defteri, son günler, mazeret (0.14.0, FastAPI'siz): Veri (aralığı toplu yükler; sorgu
                sayısı öğrenci/şube sayısından bağımsız), TEK birleşim kuralı (gecerli_duzeltmeler, kumeler,
                hucre_durumu; kural 34), hucre_yaz (düzeltme katmanı), sutun_alindi, ogretim_gunleri, ardisik_yok,
                sube_defteri, sube_gunu, son_gunler, ogrenci_gorunumu, mazeret_coz/onizle/yaz/iptal, eokul_bayat
  eokul.py      öğrenci listesi ayrıştırıcı: e-Okul OOG01001R020 .xls (xlrd), düz .xlsx/.csv
  sinav.py      sınav iş mantığı: R5 ayrıştırma, içe aktarma, eşleşme önerisi, süreler/evreler, ayar.sinav,
                gözetmen kapısı (bellekte), yoklama, şube duyurusu, icmal, saklama temizliği
  xlsx.py       yalnız standart kitaplıkla .xlsx okuyucu (zip/DOCTYPE sınırları; A5 de kullanır)
  guvenli_xml.py  DTD/varlık reddi (expat; defusedxml yok) ve windows-1254 → UTF-8 (xlsx.py ve aSc okuyucu)
  cizelge.py    zil çizelgeleri (0.10.0, saf + birkaç b yardımcısı): taslak ↔ form/veritabanı, dogrula, numarala,
                hizli_uret, araliklar, zaman_cizgisi (SVG ölçüleri + liste), gunlere_bol, haftalik_yaz (ders_saati
                TÜRETİLMİŞ tablodur, elle yazılmaz), tarihli_kural, numara_kaymasi, okulzili_yaz, ilk_tasima, CSV
  program_aktar.py  ders programı içe aktarma (0.10.0): asc_oku (izinli öznitelikler; öğretmen/ders adı okunmaz),
                tablo_oku (v2, v1 uyumlu), yz_metni_temizle, esle, fark, uygula, program_surum (10), geri_yukle
  eokul_program.py  e-Okul "Haftalık Ders Programları" (0.12.0, saf): matris_oku, rapor_oku (bloklar; yalnız dolu/boş
                + blok başına ≤3 ders adı ipucu), devre_gruplari/devre_esle (±5 dk), zil_onerisi/zil_yaz,
                sube_listesi_coz, blok_subeleri (öneri sırası), hazirla (→ program_aktar.esle girdisi)
  ogretmen_program.py  öğretmen programı (0.13.0, FastAPI'siz): hucre_coz (kapalı hata, kural 31), pdf_oku (pypdf;
                yalnız şube başlığı ve sıra doğrulaması), matris_oku, onizle (ad eşleme önerisi, uyarılar yalnız
                sayı), uygula (sürüm sayacı; kalıcı tabloda öğretmen KİMLİĞİ, ham ad yok)
  kilit_program.py  kilit ekranı gün programı (0.13.0): ajan_gorunumu → ayar.gun_programi {tarih, dersler, ileti,
                gecerli_sn}; yalnız şube/ders/saat; tablo boşsa ya da tahtanın şubesi yoksa None (kutu çıkmaz)
  maske.py      tek maskeleme tanımı: kalabalik("Ah*** Yı****"), no_son("47"), sinif_etiketi (0.14.0 varsayılanı
                no_ad_soyadbas "123 Ayşe Y."; ad_kisalt sunucuda, eşik sütuna bağlı; yoklama_yerlesim ajanla aynı)
  program.py    zil saatleri, Okul Zili okuma, takvim (plan_hesapla yalnız burada; dışarıdan gun_plani(b, tarih), aralık için gun_planlari),
                kilit aralıkları (saf); derslik CSV okuması program_aktar.tablo_oku'ya devredilir;
                ikili eğitim: devre_turleri (sabah/öğle eşlemesi), tahta_devreleri (programdan devre)
  dugme.py      tahtadaki yüzer düğme (0.9.0): ayar.tahta_dugmesi → ajana ayar.dugme {acik, islemler}
  acilis_kilidi.py  açılışta kilit (0.9.0): yeni durum.oturum_no + oturum_yasi_sn ≤ 120 → bir kez "kilitle"
                (program kilidinin yönettiği tahtada ders dışı saatte süreli program kilidi, derste kilit yok)
  temizlik.py   oturum temizliği (K7): ayar.oturum_temizligi (varsayılan kapalı), gün sonu anları
                (kapatma öncesi / son devrenin sonu / saat), zamanlayıcı (okul geneli işaret program_isaret
                tahta 0), tahta sayfası özeti; elle uç web.py /tahta/{id}/temizlik
  saklama.py    öğretim yılı bitiş tarihi (ayar.ogretim_yili_bitis): imha_siniri, Ayarlar durumu, arayüz notu
  program_is.py program zamanlayıcısı (kilit, açma yedeği, boş ders uyarısı, bakım), istisnalar, özetler,
                bos_ders_raporu (Uyarılar sekmesi: tarih aralığı, tahta, ders saati; kişi adı yok)
  komut.py      KOMUT_OMRU, KOMUT_ADI, komut_ekle (duyuru komutu ömrü açıkça ister)
  duyuru.py     tek yayın yolu duyuru_yayimla, plan zamanlayıcısı, kaçırma kuralı, durdurma
  zamanlama.py  plan takvimi (saf işlevler; Europe/Istanbul)
  hedef.py      hedef şeması ve çözümü; tahta nitelikleri (bina, kat, düzey, devre, şube)
  acil.py       acil/tatbikat yayını (durum tabanlı), yedek yol, teslim kaydı
  metin.py      Türkçe metin, şube biçimi, CSV okuma/yazma (aşamalar arası ortak)
  tema.py       okul renklerinden bütün panel ve tahta tonları (OKLCH, kontrast eşikleri)
  marka.py      okul logosu: PNG/JPEG denetimi, ölçü okuma, saklama (veri_dizini/marka/logo)
  vt.py         şema ve göçler (GOCLER listesi, PRAGMA user_version; göç öncesi kopya veri_dizini/goc-oncesi)
  guvenlik.py   parola (scrypt), sunucu sertifikası ve parmak izi, kilit kodu özeti, tc_kimlik_var
  wol.py        uzaktan açma (Wake-on-LAN) sihirli paketi; birkaç yayın adresine gönderir ("deneysel")
  paket.py      ajan .deb paketini ve kurulum betiğini dış araç olmadan üretir
  sunucu.py     iki dinleyici: yerel HTTP + ağ için HTTPS; zamanlayıcı (state.zamanlayicilar, 20 sn)
  pencere.py    durum penceresi (tkinter): /yerel/durum + `sc query` ile kip seçer; kurulu programda
                sunucu AÇMAZ (hizmetin durumunu gösterir, "Hizmeti başlat" UAC ister); geliştirmede eskisi gibi
  hizmet.py     Windows hizmeti kabuğu: saf `govde()` + pywin32 sınıfı (yalnız hizmet çalışırken içe aktarılır),
                gunluk\sunucu.log (5 MB × 3), geri yüklemede 75 koduyla çıkış (`yeniden_baslat_planla`)
  tasima.py     0.8 öncesi veriyi (%LOCALAPPDATA%) %PROGRAMDATA%'ya KOPYALAR (kurucu çağırır; çıkış kodları
                0/10/11/20/21); belirsizlik/hatada TASIMA-BEKLIYOR.txt → hizmet açılmaz
  statik/       stil.css (tek dosya; katmanlar `sifirla, temel, bilesen, kabuk, yardimci`; ölçek belirteçleri
                `--yazi-*`, `--b1..7`, `--kose-*`, `--golge-*`, `--dokunma`; kabuk kipi `--kb-*`), panel.js (tek dosya,
                kütüphanesiz; `kabukKur` = çekmece), isaret.svg (nötr ürün işareti)
  ajan_paket/   .deb'e giren dosyalar: control, postinst, prerm, servis, kur.sh, tahta-yoklama.desktop,
                tahta-ariza.desktop
tahta_ajan/     YALNIZ standart kitaplık (ekran.py ayrıca PyGObject/GTK3)
  servis.py     yönetici yetkili sistem servisi: sunucu döngüsü, komutlar, acil durumu, süreli program kilidi,
                sınav durumu (ayar.sinav, monotonik sayaç) ve gözetmen oturumu (belirteç yalnız burada),
                ders yoklaması (ayar.yoklama_etkin, self.yoklama; belirteç yalnız _yoklama_belirtec'te), yerel soket
                (ilk satır `arayuz: komut` ise kısa ömürlü istemci: ona yayın yok, ekran sayılmaz);
                0.14.0 yoklama: yetenek yoklama_gec; şube seçiminde sunucunun ders önerisi uygulanır
                (_yoklama_ders_uygula); tahta/öğretmen önerisi çatışması _yoklama_oturum_acildi'de liste isteğinden
                ÖNCE çözülür; geç, sayfalama (yoklama_sayfa), yoklama_temizle; yeni alanlar diske yazılmaz;
                A6: adres listesi (_istemci_kur/_adres_hatasi/_adres_basarili), envanter (donanim_tazele,
                envanter_iste), arıza kuyruğu (ariza_bildir, durum.json `ariza_kuyrugu`); döngünün bir turu _tur();
                USB anahtar (0.11.0): izleme iş parçacığı (yalnız ayar açıkken), self.usb durum makinesi, gizli
                yalnız _usb_gizli'de; _usb_tara, _usb_tani_iste, _usb_kilit_*, _usb_yoklama_baslat
  yoklama.py    yoklamanın ortak saf kuralları (0.14.0; servis ve ekran aynı işlevi kullanır): sonraki_durum
                (var → yok → geç), yerlesim (≤ 42: 6×7, ≤ 48: 6×8, sonrası 7×8), sayfa_sayisi, sayfa_dilimi (56'lık)
  usb_anahtar.py  USB anahtar (0.11.0, saf): dosya_coz (sunucuyla aynı), mountinfo_coz, aday_nedeni, ekran metinleri
  envanter.py   envanteri §5.4 biçiminde kurar (seri yer tutucuları boşaltılır), özet
  ariza_penceresi.py  "Arıza bildir" penceresi (GTK3, ayrı süreç; kullanıcı yetkisiyle); gonder() servise
                `merhaba arayuz=komut` + `ariza` yollar, `ariza_sonuc` bekler
  ekran.py      oturumda çalışan kilit/duyuru/kapatma/acil penceresi (GTK3), üst bantta logo ve okul adı;
                program kilidinde "Teneffüs · Tahta 10:40'ta açılır." satırı (saat_eki sunucudakiyle aynı);
                sınav sayfaları: sinav-giris, sinav, gozetmen-kod, gozetmen-menu, gozetmen-yoklama;
                yoklama sayfaları: yoklama-pin (USB kipi: yalnız PIN), yoklama-liste, yoklama-onay, yoklama-ileti;
                0.14.0: yoklama-liste içinde kaydırmasız seçim görünümü (öneri + ★ satırı, düzey, şube ızgarası,
                ders saatleri) ve homojen Gtk.Grid öğrenci listesi (iki satırlı Gtk.Button: no + YOK/GEÇ, ad;
                56'dan çok öğrencide sayfalı; ScrolledWindow/FlowBox yok);
                kilitte "Yoklama al" ve "USB anahtarla aç"; usb-pin sayfası; UsbBildirimi (köşe, odak çalmaz);
                ölçüler 1920x1080 için yazılır, ekran_olcegi() ile pencerenin monitörüne orantılanır (0.7.1)
  yuzer.py      yüzer düğme ve menüsü (0.9.0; 0.12.2'den beri yönetilen UTILITY pencere, grab yok; 0.13.1: stick,
                dokunma gölgesi 0,7 sn, dokunmada sürükleme eşiği 28 px); üstteki işlevler saf, GTK sınıfı kur() içinde
  gun_programi.py  sunucudan gelen gün programının izinli alanları (0.13.0, saf): coz — en çok 24 ders, şube/ders
                adı/saat/ileti; başka alan ekrana geçmez; yalnız servis belleğinde, gecerli_sn dolunca kalkar
scripts/panel_olcum.mjs  panel sayfalarını başsız Edge/Chrome ile ölçer (0.15.0; Node 22+, bağımlılık yok): yatay
                taşma, kontrast, küçük yazı, dokunma hedefi, isteğe bağlı görüntü. YALNIZ deneme sunucusuna karşı;
                adres/hesap/çıktı ortam değişkeniyle (PANEL_ADRES, PANEL_KULLANICI, PANEL_PAROLA, PANEL_CIKTI), çıktı depo DIŞINA
scripts/ekran_olcum.py  Docker/Xvfb'de her tahta sayfasının ekrana sığıp sığmadığını ölçer (uydurma veri); 0.14.0:
                yoklama senaryoları (yk-secim-*, yk-liste-*), kaydırmasızlık ve dokunma ölçüsü denetimi, `--yalniz`
  __main__.py   komut satırı; `tahta-ajan yoklama` ("Yoklama Al" kısayolu) servise yoklama_ac yollar;
                `tahta-ajan ariza` (pencere), `tahta-ajan sunucu ADRES` (parmak izi tutarsa yazar)
  ayar.py       yapılandırma, varsayılan tahta paleti, logonun servis tarafında saklanması, adres doğrulama/sırası
  baglanti.py   sunucu istemcisi (Istemci): HTTPS, sertifika zinciri yerine parmak izi denetimi (tutmazsa tek bayt gitmez)
  sistem.py     işletim sistemine dokunan HER ŞEY (yeni platform = bu dosya); ortak_oturum, temizlik
                sürecini oturum sahibinin kimliğiyle başlatma (tarayici_temizligi, pencereleri_kapat);
                USB (0.11.0): BaglamaIzleyici (mountinfo poll), cikarilabilir_baglamalar, anahtar_oku, udisks_calisiyor
  temizlik.py   oturum temizliğinin işletim sistemi işleri (ikinci dosya; ayrı süreçte çalışır,
                `python3 -m tahta_ajan.temizlik tarayici|pencereler`): beyaz liste, yol/bağ koruması,
                tarayıcı süreçleri, X11 _NET_CLOSE_WINDOW (ctypes libX11), ad içermeyen rapor
  tani.py       saha tanılaması (denetim listesi)
packaging/windows/   PyInstaller tanımı, Inno Setup betiği (hizmet kaydı, taşıma, icacls), build.ps1, giris.py
```

## Bağlayıcı kurallar

1. **Ajan standart kitaplık dışına çıkmaz.** Tahtada internet ve paket deposu
   varsayılmaz; `.deb` kendi kendine yeter (`Depends: python3`).
2. **Bağlantıyı hep tahta açar.** Sunucudan tahtaya bağlantı açan kod yazılmaz;
   komut `/ajan/bekle` uzun beklemesiyle iner.
3. **Sunucu arızası dersi rehin almaz.** Sunucuya `CEVRIMDISI_SN` (90 sn)
   ulaşılamazsa kilit tahtadan kodsuz açılır; ekran yardımcısı servisi 10 sn
   göremezse penceresini kapatır. Acil yayın da aynı tek düğmeyle (`cevrimdisi_ac`) yalnız
   sunucuya ulaşılamıyorken tahtadan kapatılır ve tahtada en çok 2 saat kalır.
   Bu davranışı "güvenlik açığı" diye kaldırma.
4. **Sunucu sertifikası yenilenmez.** Tahtalar parmak izine bağlıdır; sertifika
   değişirse bütün tahtalara ajan yeniden kurulur.
5. **Sır ekran yardımcısına gitmez.** Tahta anahtarı ve kilit kodu özeti yalnız
   yönetici yetkili serviste durur (`/etc/tahta-kontrol/ajan.json`, 0600).
6. **KVKK.** Tahta herkese açık ekrandır. Ajan sunucuya kullanıcı adı göndermez
   (yalnız hesap sınıfı: etapadmin/ogretmen/ogrenci/kişisel). Tanılama raporu ev
   dizini, dosya adı, kişisel hesap adı içermez. Gerçek okul verisi, tanılama
   dökümü, ekran görüntüsü depoya girmez (`saha/` gitignore'dadır).
7. **Sürüm dört yerde birlikte değişir:** `VERSION`, `tahta_ajan/__init__.py`,
   `tahta_sunucu/__init__.py` (`test_surumler_tutarli`) ve `pyproject.toml` (+ `uv lock`). Tahtalar güncellemeyi
   sürüm numarasından anlar: ajan kodu değiştiyse sürüm yükseltilir.
8. **Komut ömürleri bilinçlidir** (`komut.py::KOMUT_OMRU`): "kapat" 2 dakikada
   düşer; sonradan açılan tahta eskimiş komutla kapanmaz.
9. **Dil.** Arayüz, yorum, test adı, commit mesajı Türkçe; tanımlayıcılar ASCII
   Türkçe. `postinst`, `prerm`, `kur.sh` iletileri bilerek ASCII'dir (dash/UTF-8).
   `build.ps1` ve `.iss` UTF-8 BOM ile durur (PowerShell 5.1 BOM'suz dosyayı ANSI okur).
10. **Acil yayın komut değil durumdur** (`ayar.acil`, her `/ajan/bekle` yanıtında yeniden
   hesaplanır; komut tablosuna taşınmaz). Yalnız `acil` yeteneğini bildirmeyen eski ajana
   yedek `duyuru` komutu gider. Acil sürerken otomatik kapatma komut vermez; ajan da uyarılı
   `kapat`ı `(True, "...; uygulanmadı.")` ile atlar. Ajan anahtar hiç yoksa (eski sunucu)
   acil durumuna dokunmaz, `null` gelirse temizler; yetenekleri `durum.yetenekler` ile bildirir.
11. **Her duyuru gösterimi `duyuru.duyuru_yayimla` ile çıkar** (pano, plan, yeniden gönder,
   sonraki aşamalar `uygulama.state.duyuru_yayimla`). Göç `GOCLER`'in sonuna tek öğe eklenir.
12. **Program kilidi süreli ve kaynaklıdır.** Ajanda `kilit_kaynak` = `idare` (panel, süresiz)
   ya da `program` (süre tahtanın monotonik saatiyle sayılır, en çok 8 saat; sunucu kapalı olsa
   da süre dolunca açılır). Program kilidi idare kilidine uygulanmaz, program açması idare
   kilidini açmaz (`(True, "...; uygulanmadı.")`); idare kilidi program kilidini ezer. Program
   kilidi yeniden başlatmada **geri yüklenmez**. Program kilidinin gerekçe satırında yalnız neden ve
   açılış saati yazar; şube, ders, öğretmen yazılmaz. Derslik programında öğretmen ve ders adı tutulmaz.
   İstisna (17.11.2026 kararı, 0.13.0; `docs/tasarim.md` §12.5): ayrı `ogretmen_program` tablosu ders
   başlığı ve öğretmen KİMLİĞİ tutar; kilit ekranındaki ayrı gün programı kutusu (`ayar.gun_programi`,
   `kilit_program.ajan_gorunumu`) bugünün şube/ders/saat bilgisini gösterir. Öğretmen ve öğrenci adı
   tahtaya gitmez; kutu ajanda yalnız bellektedir, gece yarısında kalkar; derslik programı değişmedi.
13. **Boş ders uyarısı personel verisi gibi korunur:** varsayılan açıktır ve geçmişiyle raporlanır
   (K6) ama işlem kaydına içeriği yazılmaz (yalnız `#id`; rapor görüntülemesi yalnız tarih aralığı ve
   süzgecin varlığıyla), dışa aktarılmaz (yalnız yazdırılır), raporda kişi adı yoktur, tahtada görünmez,
   öğretim yılı sonunda `secure_delete` + WAL budamayla silinir (kural 24). Panel metni "dersin
   işlenmediği anlamına gelmez" notunu taşır; arayüzde mevzuat atfı yoktur.
14. **Sınav kipi durumdur, komut değil** (`ayar.sinav`, her `/ajan/bekle` yanıtında
   `sinav.tahta_sinavi` ile yeniden hesaplanır; pencere dışında `null`). Ajan kalan süreleri
   monotonik saatle sayar; sunucuya ulaşılamasa da sınav ekranı süresinde kalkar ve 90 sn sonra
   `cevrimdisi_ac` onu da kapatır (kural 3; sunucu dönünce sınav sürüyorsa geri gelir).
15. **Sınav ekranında ortak kilit kodu kabul edilmez** ve uyarılı `kapat` uygulanmaz
   (`"Sınav sürüyor; otomatik kapatma uygulanmadı."`). Panelden kilit açma sınav ekranını
   kaldırmaz; kip yalnız panelden ("Sınav kipini kaldır", "Sınavı bitir") ya da süreyle kalkar.
16. **Sınav listesi ajanda diske yazılmaz:** liste, gözetmen belirteci ve kod `durum.json`'a,
   günlüğe, tanılama raporuna girmez; liste sınav başlayınca bellekten de silinir. Gözetmen
   belirteci ekran yardımcısına gitmez; gözetmen kodu yalnız sunucuda doğrulanır.
17. **Sınavda ad soyad saklanmaz** (yalnız `maske.kalabalik`); tahtaya tam okul no ve ders gitmez;
   işlem kaydına ad, maske, okul no yazılmaz. Kişisel veri öğretim yılı sonunda (kural 24)
   `secure_delete` + WAL budamayla silinir. Okul no yalnız panelde salon yoklaması ve icmal sayfalarındadır.
18. **Öğrenci listesi tahtada diske yazılmaz; yoklama belirteci ekran yardımcısına gitmez.**
   Liste, işaretler (yok, geç) ve belirteç yalnız servisin belleğindedir (`durum.json`, günlük, tanılama
   raporu yok); kaydedilince ya da süre dolunca bellekten de atılır. Sunucuya giden durumda yalnız
   `yoklama_acik` bayrağı olur. Tahtada öğrenci maskeli etiketle (`maske.sinif_etiketi`) görünür; ders
   yoklaması listesinin varsayılan biçimi okul numarası + ad + soyadın baş harfidir ("123 Ayşe Y.";
   kullanıcı kararı 18.11.2026). Bu istisna yalnız PIN ya da USB anahtarla açılan ders yoklaması listesi
   içindir; sınav ekranları ve kalabalık listeleri (kural 17, `maske.kalabalik` + `no_son`) için "ad ve
   numara birlikte açık olmaz" hükmü sürer. **Tam soyad ve T.C. kimlik numarası tahtaya hiçbir biçimde
   gitmez** (`tam` maskesi yoktur). Mazeret/izin bilgisi, geçmiş günlerin yoklaması ve öğretmenin programı
   (PIN/USB doğrulanmadan) ajan yanıtına girmez.
19. **PIN düz metni yalnız pusula yanıtında görünür** (POST, `no-store`, yönlendirme yok); sunucuda
   scrypt özeti, tahtaya ne PIN ne özeti gider. İşlem kaydına öğretmen için yalnız kod, öğrenci için
   yalnız sayı yazılır; düzeltme gerekçesi ve öğrenci kimlikli iz yalnız `yoklama_iz`, `yoklama_duzeltme` ve
   `yoklama_mazeret`'tedir (0.14.0) ve üçü de imhayla gider; mazeret türü ve tarih aralığı da işlem kaydına yazılmaz.
20. **Kısa ömürlü yerel istemci kendini tanıtır:** yerel sokete bağlanan komut istemcisi ilk satırda
   `{"tur":"merhaba","arayuz":"komut"}` yollar; servis ona durum yayını göndermez, `durum_ozeti`
   ekranlarına ve "ekran bağlı" sayımına katmaz. Ekran yardımcısı da bağlanır bağlanmaz `merhaba` yollar
   (servis ilk satırı 3 sn bekler; gelmezse eski davranışla ekran sayar).

21. **Yedek parolası sunucuda saklanmaz;** yalnız X25519 açık anahtarı (`ayar.yedek`) durur. Parola
   belirlenmeden otomatik yedek alınmaz (pano uyarır). Geri yükleme yalnız 127.0.0.1'den ve yöneticiyle
   (ilk kurulumda oturumsuz, yine yalnız yerelden); önce denetlenir, onaylanınca program yeniden
   açılırken uygulanır, eski dosyalar `geri-yukleme-oncesi/`'ne taşınır. KVKK: elle yedekler de saklama
   gününden eskiyince, onaysız bekleyen geri yükleme 24 saatte, geri yükleme öncesi kopya (yalnız en
   yenisi) saklama gününde silinir. `*.tkyedek` depoya girmez.
22. **Sunucu adres listesi durumdur** (`ayar.sunucu_adresleri`, boşsa hiç gönderilmez; ajan boş ya da
   eksik listeyle kendi listesini silmez). Adres root yetkili kur.sh'e yazıldığı için ana makine adı
   yalnız geçerli IP ya da `[a-z0-9.-]` DNS adı olabilir (sunucu `adresler.dogrula_tek`, ajan
   `ayar.adres_dogrula`; `paket.kurulum_betigi` ayrıca denetler). Ajan bir adrese art arda 3 BAĞLANTI hatasında (parmak izi
   dahil; HTTP 401/403/5xx değil) sıradakine geçer, ulaştığı adresi `ajan.json`'da birincil yapar.
   Parmak izi her adreste denetlendiği için yanlış adrese veri gitmez. Tarama/yayınla keşif yoktur.
23. **Envanter cihaz verisidir; arıza metni tahtada gösterilmez.** Envanter yalnız sunucu `envanter_iste`
   deyince (ya da `envanter` komutunda) gider; hesap adı, ev dizini, makine adı, açık kalma süresi girmez.
   Tahtadan arıza yalnız hesap SINIFIYLA gelir; açıklama 300 karakter, T.C. no içeriyorsa sunucu metni
   kaydetmez. Arıza kuyruğu tahtada en çok 10 öğe / 7 gün, saatte 3 bildirim. Arıza kaydı silinmez.
24. **Öğrenci verisi içeren kayıtlar öğretim yılı sonuna kadar saklanır** (K3; `saklama.py`). Ders
   yoklaması (0.14.0: geç işaretleri `yoklama_gec`, panel düzeltmeleri `yoklama_duzeltme` ve mazeret kayıtları
   `yoklama_mazeret` dahil; aralığı sınırı aşan mazeret de bütünüyle silinir), sınav listesi/yoklaması ve boş ders uyarısı, yöneticinin Ayarlar'da girdiği
   `ogretim_yili_bitis` geçince (ertesi gün) o tarihe kadar oluşanlarıyla kalıcı silinir; tarih boşsa
   hiçbir şey silinmez ve Ayarlar uyarır. Gün sayılı saklama sabiti ya da ayarı geri getirilmez; tarih
   kendiliğinden (Okul Zili'nden ya da göçle) yazılmaz, yalnız önerilir. Tahtadan alınan ders ve sınav
   yoklaması kâğıdın yanında yardımcı kayıttır (K5); arayüz resmî kayıt iddiasında bulunmaz. Yalnız geç,
   düzeltme ya da mazeret kaydı olan pasif öğrenci de imhaya kadar silinmez; `hepsini_sil` yeni tabloları
   açık DELETE ile boşaltır (CASCADE'e güvenilmez).
25. **İkili eğitim (K1):** ders saati, derslik programı, boş ders uyarısı ve yoklama önerisi devreyle
   (`ders_saati.devre`) anahtarlanır; ders numarası devre başınadır (sabahın 3. dersi ≠ öğlenin 3.
   dersi). Tek devreli okulda devre adı hiçbir yerde gösterilmez ve davranış değişmez.
26. **Acil yayını bütün yönetici ve idareciler başlatır** (K4; `acil.yetkili`, rolden). `kullanici.acil_yetki`
   okunmaz; yalnız eski sürüme dönüş için 1 yazılır. Parola ve onay kutusu kaldırılmaz.
27. **Oturum temizliği hafiftir ve yalnız ortak hesaptadır** (K7; `docs/tasarim.md` §12.1). Yalnız
   `ogretmen`/`ogrenci` (`temizlik.TEMIZLENEBILIR_HESAPLAR`; sunucu daraltır, genişletemez); `etapadmin`
   ve kişisel hesap ASLA. Silinen yalnız beyaz listedeki çerez ve oturum dosyalarıdır; geçmiş, yer
   imleri, kayıtlı parola, form verisi, Local Storage/IndexedDB ve ev dizinindeki dosyalar listeye
   EKLENMEZ. Tarayıcı adımı root'ta değil, oturum sahibinin kimliğiyle ayrı süreçte çalışır; yol her
   adımda `lstat` ile izlenir, sembolik bağ izlenmez. Rapor yalnız sayıdır (ad, yol, başlık yok).
   Kullanılan tahtada 60 sn uyarı + Vazgeç; komut ömrü 2 dk, kaçan temizlik sonradan yapılmaz.
   Ajan komutun sonucunu ertelenmiş verir (`komut_uygula` → None; sonuç `sonuclar`a sonra eklenir).

28. **Sunucu Windows hizmetidir; veri ProgramData'dadır** (K8; `docs/tasarim.md` §15.6). Hesap Yerel
   Hizmet (SYSTEM'e çevrilmez). Kurulu pencere sunucu açmaz; başlangıç kısayolu geri getirilmez. Eski
   veri yalnız KOPYALANIR (kaynak silinmez); hedefte veri varsa taşınmaz; seçim belirsizse ya da kopya
   bozuksa `TASIMA-BEKLIYOR.txt` yazılır ve hizmet açılmaz — bu korumayı "kolaylık" için kaldırma
   (yeni sertifika = bütün tahtalar kopar, kural 4). Taşıma kodları `.iss` ile `tasima.py`'de aynıdır
   (`test_kurucu_tasima_kodlari_python_ile_ayni`). `hizmet.py` modül düzeyinde pywin32 içe aktarmaz.

29. **USB anahtar dar yetkidir ve belleği işgal etmez** (0.11.0; `docs/tasarim.md` §14.1). Servis belleği
   biçimlendirmez, BAĞLAMAZ (bağlamayı oturumdaki udisks2 yapar), yazmaz; yalnız bağlamanın kök dizinindeki
   `tahta-kontrol.anahtar`'ı `O_NOFOLLOW`/`dir_fd` ile, ≤ 1 KB, ayrı iş parçacığında 3 sn zaman aşımıyla okur.
   Gizli değer yalnız servis belleğinde, tanındıktan sonra en çok 10 dk durur; ekran yardımcısına, `durum.json`'a,
   günlüğe, tanılamaya gitmez; bağlama yolu ve bellek etiketi de yazılmaz. Dosyadaki `sunucu` parmak izine
   uymazsa gizli hiç gönderilmez. Çevrimdışıyken USB anahtar çalışmaz (kural 3 değişmez). Takılınca tam ekran
   açılmaz; yoklama ve kilit açma dokunuşla başlar. Sınav ekranında, acil yayında hiçbir şey yapmaz. Sunucu
   yalnız gizlinin SHA-256 özetini saklar; gizli yalnız tek seferlik indirilen dosyada çıkar. Belleğin
   kendiliğinden tanınması işlem kaydına YAZILMAZ (konum geçmişi birikmesin; yalnız `son_kullanim`); kilit açma
   iletileri yalnız ekrandaki oturumun yardımcısından kabul edilir (`_etkin_oturumdan`). İdare anahtarının
   tahtadaki etiketi panel kullanıcı adını taşımaz (görünen ad tek kelimeyse ya da kullanıcı adıysa "İdare").

30. **e-Okul raporunda öğretmen adı hiçbir yere girmez** (0.12.0; `docs/tasarim.md` §12.4). Hücreden yalnız
   "dolu mu" alınır; eşleme ipucu yalnız iki satırlı hücrenin İLK satırıdır (ders adı), blok başına en çok 3,
   yalnız önizleme kaydında durur. Tek satırlı hücreden ipucu almayı "kolaylık" için açma. Raporda şube adı
   yoktur: şube eşlemesi zorunlu adımdır, aynı şube iki bloğa atanamaz. Gerçek rapor ve PDF'i depoya,
   teste, belgeye girmez; testler uydurma matrisle (`tests/test_eokul_program.py`) yazılır.
   Bu kural derslik aktarımı (`eokul_program.py`, `/program/aktar/eokul`) içindir ve DEĞİŞMEDİ. İstisna
   (17.11.2026 kararı, 0.13.0): ayrı `/ogretmen-programi` yolu aynı raporun öğretmen satırını okur; ham ad
   yalnız önizleme belleğinde durur, kalıcı kayda mevcut öğretmen kimliği yazılır (kural 31). Ad işlem
   kaydına, tahtaya, ajana girmez; öğretmen kaydı kendiliğinden oluşturulmaz.

31. **Öğretmen programı ayrıştırıcısı kapalı hata çalışır; önizleme kısa ömürlüdür** (0.13.1;
   `docs/tasarim.md` §12.5). Hücre `ogretmen_program.hucre_coz` ile çözülür: seçmeli gruplar `,` `;` sekme
   ve iki ya da daha çok boşlukla ayrılır, her parça ayrı "kişi - ders" girişidir. Ders başlığına kişi adı
   karışabilecek belirsiz parça (bölündükten sonra hâlâ birden çok " - ") genel başlığa iner, kişi
   eşlemeye alınmaz, önizleme yalnız sayıyla uyarır; başlık satırının kendisi "kişi - ders" kalıbındaysa
   başlık "Ders" olur. Bunu "daha çok satır okunsun" diye gevşetme: ders başlığı kilit ekranına gider.
   PDF'ten yalnız şube başlığı ve sıra doğrulaması okunur. Önizleme (ham adlar) yalnız bellektedir:
   15 dk sonra zamanlayıcıda, "Vazgeç"te ve onayda silinir; diske, işlem kaydına yazılmaz. Program
   hiçbir öğretmenin başka sınıf/ders yoklamasını engellemez. Testler uydurma adla yazılır.

32. **Yeni sürüm denetimi yalnız sunucudadır, hiçbir veri göndermez, yalnız haber verir** (0.13.1;
   `docs/tasarim.md` §9.1, `guncelleme.py`). Programın internete çıkan TEK işi budur; tahtalar ve tarayıcı
   internete çıkmaz (ajana, `panel.js`'e, CSP'ye GitHub adresi girmez). Tek bir GET (GitHub "son sürüm"
   kaydı); istekte yalnız genel `User-Agent: tahta-kontrol` ve `Accept` vardır: okul adı, tahta sayısı,
   kimlik, KURULU SÜRÜM, sorgu parametresi, telemetri eklenmez. Yanıt güvenilmez girdidir: TLS doğrulaması
   kapatılmaz, yönlendirme izlenmez, ≤ 256 KiB, toplam ≤ 5 sn; yalnız `tag_name`/`draft`/`prerelease` okunur,
   etiket yalnız `^v?\d+(\.\d+){1,3}$` ise kabul edilir. Bağlantı yanıttaki `html_url`'den değil, doğrulanmış
   sürümden SABİT kalıpla kurulur; sürüm notu sayfaya basılmaz. Kendiliğinden indirme/kurma eklenmez. Not
   panoda yalnız yöneticiye çıkar. Ayar (`guncelleme_denetimi`, varsayılan açık) kapalıyken HİÇ istek çıkmaz
   ("Şimdi denetle" dahil). Günde en çok bir kez; başarısız deneme de günlük hakkı tüketir; başarısızlık
   sessizdir (panoda hata yok, yalnız Ayarlar'da "ulaşılamadı"). Ağ çağrısı olay döngüsünde, `vt.KILIT`
   altında ya da veritabanı bağlantısı açıkken yapılmaz; kapanış onu beklemez. İşlem kaydına yalnız elle
   denetim ve ayar değişikliği yazılır. Yeni bağımlılık (requests, certifi…) eklenmez.

33. **"Geç" yalnız devrenin ilk dersinde işaretlenir** (0.14.0, kullanıcı kararı 18.11.2026; `docs/tasarim.md`
   §14.2). `yoklama.gec_secilebilir` = seçilen ders, şubenin devresinin o günkü planındaki en küçük ders
   numarasıdır (sabah ve öğle devresinin ilk dersi ayrı ayrı; devre bulunamazsa 1. ders). Sunucu tahtadan da
   panelden de ilk ders dışındaki geçi reddeder; bir öğrenci aynı kayıtta hem yok hem geç olamaz. Geç ayrı
   tablodadır (`yoklama_gec`), "yok" sayımına girmez, ayrı sayılır; yarım/tam güne çevrilmez (K2). Yetenek
   `yoklama_gec`: bildiren ajan `/ajan/yoklama/kaydet` gövdesinde `gec`'i her zaman yollar (boş liste dahil;
   yoksa 400), bildirmeyen eski ajanın kaydı var olan geçi silmez ve ona geç öğrenci " (geç)" ekli etiketle
   gider. Sunucu–ajan yoklama sözleşmesinin örnekleri `tests/yoklama_sozlesme.json`'dadır; iki tarafın testi
   bu dosyadan beslenir, alan eklenirse dosya, sunucu ve ajan çözücüsü birlikte değişir. Öğretmen programı
   ve saat yalnız ÖN SEÇİMDİR: hiçbir şube ya da ders düğmesi programa göre kapatılmaz.
34. **İdare düzeltmesi ayrı katmandır; ders saatinin geçerli durumu tek koddan çıkar** (0.14.0;
   `yoklama_defter.Veri.gecerli_duzeltmeler`/`kumeler`, `hucre_durumu`, `yoklama.gecerli_durum`). Şube
   defterindeki düzeltme öğretmenin/tahtanın kaydına DOKUNMAZ, `yoklama_duzeltme`'ye satır yazar (aynı
   kullanıcı aynı hücrede 60 sn içinde tek satır). Geçerli durum: o ders saatinin EN SON KAYDEDİLEN yoklama
   kaydı (kayıtlar birleştirilmez); üstüne, o kayıttan ESKİ OLMAYAN en yeni düzeltme. Yani "en son işlem
   geçerlidir": düzeltmeden sonra tahtadan yeniden kaydedilen yoklama düzeltmenin üstüne geçer (liste
   düzeltilmiş durumu gösterdiği ve kaydet tam durumu yazdığı için veri kaybolmaz). Günlük görünüm, icmal,
   metin, CSV, `/yoklama/gir` ön doldurması ve tahtanın `/liste` yanıtı bu koddan geçer; ikinci bir toplama
   yolu yazılmaz. Yoklaması alınmamış saatte hücre yazılmaz (409; yalnız yok/geç satırı tutulduğu için kayıt
   açmak sınıfın kalanını "var" saymaktır); kayıt panelden yalnız iki adımlı "Alındı" onayıyla açılır.
   Yok/geç → var düzeltmesinde not zorunludur. Düzenleme bugün ve son 7 gün içindir; eskisi salt okunur.
35. **Mazerette serbest metin yoktur; mazeret ve geçmiş tahtaya gitmez** (0.14.0; `docs/tasarim.md` §14.2).
   Mazeret sabit tür (izinli, raporlu, mazeretli, görevli) ve isteğe bağlı sabit dayanak seçimiyle girilir;
   açıklama alanı EKLENMEZ (sağlık verisi ve gerekçe metni birikmesin). Tür yalnız mazeret sayfasında ve
   öğrenci görünümünün mazeret bölümünde görünür; şube defterinde, icmalde, metinde, CSV'de, yazdırmada,
   erişilebilirlik metninde ve işlem kaydında tek "Ö" (özürlü) vardır. İşlem kaydına tür ve tarih aralığı da
   yazılmaz (yalnız öğrenci ve gün sayısı). Mazeret ayrı katmandır: öğretmen kaydını ve düzeltmeyi
   değiştirmez; kaldırılınca tür `iptal` yapılır, dayanak boşaltılır. Önizleme yalnız bellekte 10 dk durur.
   "N gündür derste görülmedi" türetilir; saklanmaz, dışa aktarılmaz, arayüz "devamsızlık günü" demez (K2,
   K5). Şube defteri, son günler, öğrenci görünümü ve mazeret listesi `no-store` döner, yönetici ve idareciye
   açıktır, dışa aktarılmaz (yalnız yazdırılır). Ajan yanıtlarına mazeret ve geçmiş gün girmez.

## Bilinen tuzaklar

- **Panel kabuğunun kipi CSS'tedir (0.15.0):** çekmece / sabit menü ayrımı `stil.css`'te `--kb-*` özellikleriyle
  durur (sabit: ≥ 64rem; şube defteri `genis-sayfa` için ≥ 100rem). `panel.js` kipi `--kb-kip`'ten okur; genişlik
  eşiğini JS'e ya da başka bir kurala kopyalama.
- **`body`, `html` ve `main`'e `overflow` ya da yükseklik verme (0.15.0):** yan menü `position: fixed`'tir, içerik
  `body` dolgusuyla kayar; belge kaydırması bozulursa içerikteki bütün yapışkan (`sticky`) şeritler kırılır.
- **İçerikteki yapışkan öğe `inset-block-start: var(--yapiskan-ust)` kullanır (0.15.0):** çekmece kipinin HER
  genişliğinde üst çubuk yapışkandır (şube defterinde 1600 px'e kadar); `0` yazılırsa araç çubuğu, fırça şeridi
  ya da tablo başlığı üst çubuğun altında kalır. Baskıda değer 0'dır.
- **Yeni CSS belirteci `-a`/`-k` ile bitmez, `t-` ile başlamaz (0.15.0):** o adlar `tema.py`'nin ham marka
  renkleridir; `test_stil_varsayilanlari_motorla_ayni` hepsini motorla karşılaştırır ve kırılır.
- **Kabukla çakışan bileşen kuralı `kabuk` katmanında ezilir (0.15.0):** `kabuk` `bilesen`'den sonra gelir; aynı
  şeyi bileşen bloğunda düzeltmeye çalışmak etkisizdir.
- **İçerik sabit menü kadar (15rem) dardır (0.15.0):** 1366 px'te içerik ≈ 1069 px. Görüntü alanına bağlı
  `@media` eşikleri içerik enini anlatmaz; sekme şeridi ve tablo kuralları eşiği buna göre taşır (sabit menülü
  sayfa 85rem, tam genişlikli şube defteri 70rem; testi var). Yeni geniş tablo ya da şerit ekleyince
  `scripts/panel_olcum.mjs` ile 1366 ve 390 px'te, açık ve koyu ölç.
- **Telefonda sabit konumlu alt çubuk sayfayla birlikte genişler (0.15.0):** tek bir taşan öğe (ör. sarmayan
  fırça şeridi) sayfayı 390 px'ten genişletince alt çubuk da taşar; taşmayı çubukta değil taşan öğede gider.
- **Çekmece açık sayfa geri tuşunda açık ve `inert` dönebilir (0.15.0):** geri/ileri önbelleği sayfayı olduğu
  gibi getirir; `kabukKur` `pagehide` ve `pageshow`'da kapatır. `#menu` parçasıyla gelinirse çekmece sınıfla
  yeniden açılır (`:target`'a bağlı kalan çekmeceyi Esc ve perde kapatamaz).
- **Menüye öğe eklenirse biri çıkar (0.15.0):** üç küme, en çok on üst öğe (`test_menu_uc_kume_ve_en_cok_on_oge`);
  yöneticiye özel öğe `rol` taşır. Menü yalnız görünümdür: yetki denetimi uçta kalır. Bir sayfa hangi sekme
  şeridini çiziyorsa menüde o bölümün `esler`'inde durur (yoksa vurgu başka bölüme zıplar).

- **Panonun genel `.ozet { display: flex }` kuralı tablo hücresini bozar (0.14.0):** şube defterinin özet
  hücreleri bu yüzden alt alta diziliyordu; `.defter .ozet { display: table-cell }` ayrıca verilir. Dar ekranda
  görünmez (ekran okuyucu) metinler de sayfayı yatay taşırıyordu; yeni tablo sayfasında 800 px'te taşmaya bak.
- **Şube defterinde iki dikey kaydırma olmasın (0.14.0):** sığan tabloda kap kaydırma kabı değildir
  (`.defter-kap.sigar`); sütun sınırı (beş gün ≤ 40, gün ≤ 12 ders sütunu) aşılınca ya da dar ekranda kendi
  kabında kayar. 8 ders × 5 gün 1366 px'e ancak 22 px hücre ve 10rem ad sütunuyla sığar; sütun genişletme.
- **Pango kısaltması soyad baş harfini yutar (0.14.0):** öğrenci adı tahtada kısaltılmaz; ad kısmını sunucu
  kısaltır (`maske.ad_kisalt`, eşik sütun sayısına bağlı). Sütun × satır tablosu iki yerdedir
  (`maske.yoklama_yerlesim` ve `tahta_ajan/yoklama.yerlesim`) ve testle eşlenir; biri değişirse öbürü de.
- **Düzeltme ile kayıt aynı saniyedeyse düzeltme kazanır** (`zaman >= guncelleme`, kural 34). `/yoklama/kayit/{id}`
  "Düzelt" ile eski bir kaydı düzeltmek o kaydı en yeni yapar: o ders saatindeki öbür kaydı ve panel
  düzeltmelerini örter (sayfada şube defterine yönlendiren not vardır).
- **Tahtanın `/liste` yanıtında `gec_secilebilir` false ise `gec` hep `[]` döner (0.14.0):** plan sonradan
  değişmiş günde ilk ders dışı geç tahtaya inerse ajan onu geri yollar ve 400 alırdı.

- **Testler gerçek ağa çıkmaz (0.13.1):** `tests/conftest.py::ag_kapali` (autouse) her testte
  `guncelleme.github_getir` ve `guncelleme._ac` adlarını sahtesiyle değiştirir. Denetimi sınayan test
  getiriciyi `uygulama_olustur(..., guncelleme_getirici=...)` ya da `guncelleme.Denetleyici(getirici)` ile
  verir; asıl `github_getir` yalnız sahte `ac` ile çağrılır. Bu fikstürü kaldırma ya da daraltma.
- **Soket zaman aşımı toplam süre değildir (0.13.1):** her soket okumasında yeniden başlar, ad çözümlemesine
  hiç uygulanmaz; yanıtı bayt bayt damlatan ağ aygıtı `urlopen(timeout=5)`'i dakikalarca tutar. Toplam süreyi
  `guncelleme._sinirli_getir` (kısa ömürlü daemon iş parçacığı + süre + kapanış olayı) sınırlar.
- **e-Okul hücresinde iki seçmeli grup çift boşlukla ayrılır (0.13.1):** "KİŞİ - DERS  KİŞİ - DERS" tek
  satırda gelir; boşluklar bölmeden ÖNCE sadeleştirilirse ikinci kişinin adı ders başlığına karışır
  (0.13.0 kusuru; kilit ekranına ad sızdırabilirdi). Önce böl, sonra sadeleştir (`hucre_coz`). Göç,
  " - " taşıyan eski ders başlığını "Seçmeli ders" yapar; kaybolan satırı getirmez, program yeniden aktarılır.
- **Yüzer düğmede girdi tutma (grab) ve POPUP kullanılmaz:** `Gdk.Seat.grab` ETAP'ta görev çubuğunu
  kilitledi, düğme tıklanamadı (0.12.0 saha bulgusu). Pencere yönetilen UTILITY + keep_above + stick'tir.
  Kap ölçümü (18.11.2026, Xvfb): xfwm4/Mutter/Muffin'de odaklı tam ekranın üstünde tıklanır, Openbox'ta
  çıkamaz; "masaüstünü göster" Mutter/Muffin/Openbox'ta düğmeyi gizler. ETAP'ın pencere yöneticisi bilinmiyor.
- **Dokunuş iki kez gelir:** aynı dokunuş touch olayı ve ardından öykünülmüş fare basışı olarak gelebilir;
  dokunuştan sonraki 0,7 sn içindeki fare basışı yok sayılır (`yuzer.fare_oykunmesi_mi`), yoksa menü açılıp kapanır.
- **Kilit ekranı gün programında tahtanın tarihine güvenilmez:** tarih sunucununkinden farklıysa program
  gizlenmez, başlık sunucunun tarihini taşır ve ilk sayfadan açılır; eskimiş programı servis `gecerli_sn` ile kaldırır.

- **JS'de `form.id` kullanma (0.11.0):** formda `name="id"` alanı varsa `form.id` o alanı döndürür; onay
  düğmesi forma bağlanmaz, iptal/silme hiç gitmez (0.3.0'dan beri grup silme de böyle bozuktu).
  `form.getAttribute("id")` kullanılır (`panel.js::formKimligi`; test `form.id` arar).
- **`ders_saati` türetilmiş tablodur (0.10.0):** haftalık düzen ve çizelgelerden `cizelge.haftalik_yaz`
  ile yeniden yazılır; ona doğrudan INSERT yazan kod (eski `/program/zil/elle`) taşımadan sonra silinir.
  Testlerde zil kurmak için `yardimci.zil_kur` / `zil_elle` kullanılır. Günün planı yalnız
  `program.gun_plani(b, tarih)` ile alınır (`plan_hesapla(` program.py dışında geçmez; test eder).
- **Çizelge formu yeniden çizilirken boş satırlar taslağa girmez** (`cizelge.taslak_formdan`) ve yeni
  boş satırların kimliği gönderilen en büyük kimlikten sonra başlar: JS aralıklı kimlik (r40) verir;
  sayıyla başlatılan kimlik var olan satırla çakışıp iki alanı aynı adla gönderiyordu (16.11.2026).
- **Bölüm içi ileti:** Zil sekmesinde `?yer=haftalik|cizelgeler|tarihli#ileti`; ileti o bölümde çizilir
  ve odaklanır (yalnız `#bolum` parçasıyla yönlenince sayfa başındaki ileti ekran dışında kalıyordu).

- **GtkButton.set_label etiketi yeniden kurar:** ortalama (`set_justify`) ve kısaltma kaybolur;
  yoklama düğmesinin metni değişince `ekran._ogrenci_etiketi` ile yeniden verilir (16.11.2026, Docker).
  0.14.0'dan beri öğrenci düğmesi iki ayrı etiket taşır ve `set_label` çağrılmaz; `_ogrenci_etiketi` yalnız
  durum yazısını (YOK/GEÇ) ve stil sınıfını günceller. Başka düğmede `set_label` kullanılırsa tuzak sürer.
- **Zombi süreç /proc'ta yaşar görünür:** `/proc/<pid>/status` hâlâ Name ve Uid verir; tarayıcı
  süreci sayılırken `State: Z` atlanmazsa kapanmış tarayıcı "kapanmadı" sayılır ve verisi temizlenmez
  (16.11.2026, Docker oturum temizliği denemesi).
- **Kapta `pkill -f "tahta-ajan ekran"`, aynı metni taşıyan `sh -c` komutunu da öldürür;**
  deneme betiklerini dosyaya yazıp `sh dosya` ile çalıştırın (16.11.2026).

- **Statik dosya adresleri sürüm taşır** (`/statik/stil.css?v=<sürüm>`, `panel.js?v=<sürüm>`)
  ve uzun önbellekle sunulur: `stil.css` ya da `panel.js` değişip sürüm yükseltilmezse
  tarayıcı eskisini tutmaya devam eder. Statik dosya değiştiyse sürüm yükseltilir (16.11.2026).
- **Panel menüsünde açılır grup yoktur (0.15.0'dan beri; eskiden JS'siz `<details>` idi).** Yan menünün alt
  listeleri HTML'de hep çizilir; sabit kipte yalnız etkin bölümünki, çekmecede hepsi görünür. JS'siz açılır
  `<details>` yalnız Program şeridindeki "Program kilidini durdur"da kaldı. `<form>` `<p>` içine konmaz (tarayıcı
  `<p>`yi kapatır, düğme satırı dağılır); düğme satırında `<div class="dugme-satiri">` kullanılır.
- **Acil sayfası da `yigin.show_all()`'dan önce eklenir** ve rengi pencereye eklenen stil
  sınıfından (`acil`/`tatbikat`) gelir; başka sayfaya geçince sınıf kaldırılır. Acil renkleri
  sabittir (`ekran.ACIL_RENKLERI`), okulun renginden türetilmez; yanıp sönme yoktur (16.11.2026).
- **Paket içi dosya zamanı içerikten türetilir** (`paket.py`): sabit zaman,
  güncellenen dosyanın eski `__pycache__` ile çalışmasına yol açtı (15.11.2026).
  `postinst` ayrıca önbelleği siler.
- **`Referrer-Policy: no-referrer` kullanma:** tarayıcı form gönderiminde
  `Origin: null` yollar, kaynak denetimi bütün POST'ları reddeder (15.11.2026).
- **GtkStack en büyük sayfasına göre boyutlanır; sabit piksel ölçü verme** (16.11.2026, 0.7.0 kusuru):
  gözetmen kodu/yoklama PIN'i sayfasındaki 640/720 px sütun ve 150 px tuşlar pencereyi 1427 px'e
  zorladı; 1280x800 ve 1366x768 ekranda kilit ve duyuru da sağa kaydı, tahta adı kesildi. Artık yığın
  homojen değildir ve bütün pikseller (CSS dahil) `ekran.py`'de `_olcu/_kutu/_izgara/_kenar/_ekle/_dugme`
  ile 1920x1080 değeriyle verilip `ekran_olcegi()` ile ölçeklenir (`test_ekran_kodunda_sabit_piksel_yok`).
  Ekran sayfası değişince dar ekranda dene: `scripts/ekran_olcum.py`'yi Xvfb'de 1024x768, 1366x768,
  1920x1080 ve 3840x2160'ta çalıştır; "TAŞTI" kalmamalı.
- **GtkStack görünür olmayan sayfaya geçmez:** sayfalar pencere açılmadan
  `yigin.show_all()` ile görünür kılınır, pencere `show()` ile açılır (`show_all()` değil;
  o, gizlenmiş tuş takımını ve düğmeleri geri açar). Yoksa açılıştan sonraki ilk duyuru
  ya da kapatma uyarısı yerine bozuk bir kilit sayfası çıkar (16.11.2026).
- **Klavye kilidi pencere ekrana yerleşince alınır:** ilk deneme XFCE'de "not-viewable"
  ile düşer; kilit sürdükçe her saniye yeniden denenir (15.11.2026, Pardus 25 denemesi).
- **Otomatik kapatma** (`web.py::zamanlayici`, 20 sn'de bir; acil sürerken atlanır): yalnız o an çevrimiçi
  tahtalara, uyarılı (`uyari_sn`) komut verir; aynı gün-saat için bir kez (`kapatma_isaretleri`).
  Ajan, kilitli ya da ekransız tahtada uyarı göstermeden kapatır. Uzaktan açma
  (Wake-on-LAN) denenen bilgisayarda çalışmadı; düğme yalnız tahta sayfasında "deneysel" durur.
- **Panelde satır içi betik ve stil yok:** CSP `script-src 'self'; style-src 'self'`.
  Şablona `<style>`, `style=`, `onclick=` ya da çalışan `<script>` yazılmaz (yalnız
  `type="application/json"` veri blokları); test bunu denetler. Renkler `/marka/tema.css`'ten
  gelir, `stil.css`'teki varsayılan ham değerler `tema.varsayilan()` çıktısıyla aynı olmalı.
- **GTK'da `label` renk kuralı düğmenin içindeki etiketi de boyar:** düğme yazı rengi
  `button label` ve `#ana-dugme label` ile ayrıca verilir (`ekran.renk_stili`). Renkler ayrı
  bir CSS sağlayıcısındadır ve tema değişince aynı sağlayıcıya yeniden yüklenir.
- **Ajanın varsayılan paleti sunucuyla aynıdır:** `tahta_ajan/ayar.VARSAYILAN_PALET` =
  `tema.varsayilan()["tahta"]`; tema formülü değişirse ikisi birlikte değişir (test eder).
- **Logo ekran yardımcısına soketle gider:** dosya root'a aittir (0600); yardımcı okuyamaz.
  Logo bozuk ya da inmemişse ekran logosuz çalışır; bunu "hata" diye düşürme.
- **Eski ajana program komutu verilmez:** program kaynaklı `kilitle`/`kilit_ac` yalnız
  `durum.yetenekler` içinde `program_kilidi` bildiren tahtaya gider. 0.3.x ajanı `kilitle`'nin
  verisini yok sayıp süresiz kilitler, sonraki `kilit_ac` idarenin kilidini de açardı (16.11.2026).
- **Program kilidinin süresi komut tahtaya inerken hesaplanır** (`web.py`, `bitis_sunucu` →
  `sure_sn`; 30 sn'den azsa komut `iptal`). Panelde açılış saati `son_gorulme + kilit_kalan`
  dakikaya yuvarlanarak gösterilir (ajan kalan süreyi aşağı yuvarlar; 09:10 yerine 09:09 çıkıyordu).
- **Saatten sonra gelen ek** (`'ta/'da/'te/'de`) saatin okunuşundan seçilir: `program.saat_eki`
  ve `ekran.saat_eki` aynı tablodur (test bütün saatleri karşılaştırır). "10:40'da" yanlıştır.
- **`<details>` içindeki form alanları:** yeni tarayıcılarda içerik `::details-content` sözde
  öğesindedir ve `box-sizing` zincirini koparır; `stil.css` sıfırlama katmanında ayrıca
  `::details-content { box-sizing: inherit }` vardır. Yoksa açılır formlardaki alanlar kutudan taşar.
- **Sınav ve gözetmen sayfaları da `yigin.show_all()`'dan önce eklenir;** sonradan içi doldurulan
  liste ve koltuk ızgarasında yalnız o kapsayıcının `show_all()`'ı çağrılır (pencereninki değil).
  Koltuk ızgarası gözetmen oturumu değişince (`oturum` numarası) yeniden kurulur; ara `durum`
  iletileri işaretleri silmesin diye her çizimde yeniden kurulmaz (16.11.2026).
- **Kip kaldırılan salonun tahtası çakışma sayılmaz** (`sinav.cakisan_sinav`); yoksa kipi kaldırılan
  tahta aynı saatteki başka sınava eşlenemezdi (16.11.2026).
- **Docker'da ekran yardımcısını yeniden başlatırken** eski süreç (`python3 -m tahta_ajan ekran`)
  ayrıca öldürülür; iki yardımcı üst üste pencere açar, tıklamalar eskisine gider (16.11.2026).
- **Sunucunun ajan paketi süreç başında bir kez üretilir:** ajan kodunu değiştirdikten sonra Docker
  denemesinde paketi yeniden indirmek için deneme sunucusu yeniden başlatılır.
- **Deneme sunucusunda giriş hız sınırı** (adres başına 5 dk'da 10): betik her adımda yeniden giriş
  yapmasın; oturum çerezini saklayıp yeniden kullansın.
- **Arıza penceresinin "iletildi" iletisi sunucunun `ariza_alindi` yanıtına bağlıdır** (servis en çok
  5 sn bekler); gelmezse "tahtada bekletiliyor" der ve kayıt kuyrukta kalır. Docker'da ilk bağlantı
  uzun bekleme (25 sn) sürdüğü için adres listesi ve onay ancak bir tur sonra iner (16.11.2026).
- **Ajan döngüsü `_tur()` olarak ayrıldı:** testler ağı sahte `Istemci` ile verip turları tek tek
  çalıştırır (`tests/test_ajan_altyapi.py`); `_dongu` yalnız bekleme ekler.
- **Şablon makro bağımsız değişkeninin adı `on…` ile başlamaz** (`onek=` gibi): CSP testi
  ` on[a-z]+=` desenini satır içi olay işleyicisi sayar (16.11.2026).
- **Bu geliştirme bilgisayarında hizmet KURULMAZ:** `hizmet --konsol` hizmet yöneticisi olmadan aynı
  gövdeyi çalıştırır (ayrı `TAHTA_VERI_DIZINI`, 8797/8798). `python -m tahta_sunucu hizmet` elle
  çalıştırılınca 2 koduyla çıkar (1063); bu beklenen davranıştır.
- **`pencere` geliştirmede 8787'de sunucu açar:** kurulu sunucu bu bilgisayarda çalışıyorsa önce
  ona bağlanır; denemede `TAHTA_HTTP_PORT`/`TAHTA_HTTPS_PORT`'u değiştirmeden çalıştırma.
- **`sudo` çağıran hesabın KENDİ parolasını sorar:** `ogretmen` sudo yetkili değildir; öğretmen
  oturumunda `sudo bash tahta-kur.sh` öğretmen parolasını sorup reddeder (G1, 16.11.2026, gerçek ETAP).
  `kur.sh` ve `araclar/otomatik-giris.sh` yetkiyi kendileri alır: root → sudo (yetkiliyse) → pkexec
  (grafik oturum; polkit etapadmin'i sorar) → `su etapadmin` + sudo → "etapadmin oturumunda yapın".
  Yönergeye `sudo` yazılmaz.
- **`su -c` komutu yeni oturumda (denetim uçbirimi olmadan) çalıştırır:** içindeki `sudo` parola
  soramaz ("a terminal is required"); `su --pty` kullanılır, `--pty` yoksa `sudo -S` (Docker'da
  doğrulandı, 16.11.2026). Kapta polkit kimlik doğrulaması "No session for cookie" ile düşer (logind
  oturumu yok); pkexec yolu yalnız gerçek masaüstünde sınanır.
- **Ölü uzun bekleme komut çalar:** ajan yeniden başlayınca eski bağlantının `/ajan/bekle`'si sunucuda
  25 sn'ye kadar açık kalır; süresi dolunca bekleyen komutu alıp ölü sokete yollardı (açılışta kilit
  Docker'da hiç inmedi, 16.11.2026). `bekleyenler`'de yerini yenisi alan bekleme komut almaz.
- **Açılışta kilidin oturum yaşı süreç başlangıcından gelir** (`/proc/self/stat`, `execv`'de korunur):
  güncellemede kendini yeniden başlatan yardımcı yeni oturum sayılmaz. Docker kapları çekirdeği
  paylaştığı için `boot_id` ve açılış sayacı kapta "yeniden başlatma" ile değişmez.
- **USB bildirimi numarayla tüketilir** (0.11.0): kilit ya da tam ekran sayfa açıkken gelen `bildirim_no`
  "gösterildi" sayılır; yoksa kilit USB anahtarla açılınca aynı bildirim köşede yeniden çıkıyordu (Docker).
- **Docker'da USB benzetimi:** `--privileged` kap, `mkfs.vfat` kalıp, `mount -o loop,uid=1000 … /media/ogretmen/BELLEK`,
  servis `TAHTA_AJAN_USB_BENZETIM=1` ile (yalnız "çıkarılabilir" ölçütü gevşer, `loop` kabul edilir). Kapta
  systemd yok: tanılamada udisks2 "bilinmiyor" çıkar. İzleme ilk `/ajan/bekle` yanıtından sonra başlar (≤ 25 sn).
  Xvfb'yi yeniden başlatırken `docker exec -d` kullanın (`bash -c '… &'` süreci exec bitince ölür).
- **Deneme betiklerinde saat:** Git Bash'te `TZ=Europe/Istanbul date` UTC verir; saati Python ile hesapla.
- **İlk kurulum yalnız 127.0.0.1'den yapılır;** ağdaki biri yönetici hesabını kapamasın.
- **Docker'da deneme:** `debian:12` + `python3-gi gir1.2-gtk-3.0 xvfb openbox imagemagick`;
  sunucuya `https://host.docker.internal:8788` ile ulaşılır; systemd yoktur, servis elle başlatılır.
  Git Bash'te `docker exec` için `MSYS_NO_PATHCONV=1` gerekir (curl için gerekmez, bozar).
