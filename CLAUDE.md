# CLAUDE.md — Tahta Kontrol

Yerel geliştirme 0.22.0 (kullanıcı isteği 27.11.2026, "0.22.0'ı yaz"): **açılışta otomatik giriş** (kural 39;
`otomatik_giris.py` iki tarafta; tasarım §5.2). Okulda bazı tahtalar "Ekran yardımcısı yok" görünüyordu: tahta
açık ama giriş ekranında bekliyor, oturum yok. Ayarlar › Kilit ve güvenlik › Otomatik giriş: dokunma (varsayılan,
alan gönderilmez) · öğretmen · kaldır. etapadmin parolası İSTENMEZ (ajan root). "Öğretmen" yalnız kilit kodu ve
açılışta kilit varken kaydedilir; sonradan bozulursa Bugün uyarır. Ajan DEĞİŞTİ (yetenek `otomatik_giris`;
güncelleme bu özellik için gerekli), göç YOK. Tasarım §5'in "otomatik giriş ayarlanmaz" kararı kullanıcı isteğiyle
değişti; ayrıntılar VARSAYILDI (§17 soru 136–145). `docs/surum-0.22.0.md`. Testlerle ve deneme sunucusunda başsız
tarayıcıyla (uydurma veri) denendi; dağıtılmadı, gerçek ETAP'ta ve gerçek LightDM'de denenmedi (saha denemesi
§4, O1–O9; önce tek tahtada).

Yerel geliştirme 0.21.0 (kullanıcı onayı 21.11.2026). Okulda 0.20.0 24 ETAP tahtasında sorunsuz çalıştı; kullanıcı
beş saha talebinin tek sürümde çıkmasını istedi:
(1) **Toplu öğretmen yükleme** (`ogretmen_aktar.py`; kural 38; soru 34 kapandı). Kaynaklar: aSc XML (yalnız ad ve
soyad), e-Okul OOK01001R1, şablon. Tamamı büyük ya da tamamı küçük ad baş harf biçimine çevrilir; soyad boşsa tam ad
bölünür. Dosyada olmayan öğretmene dokunulmaz; PIN var olan toplu düğmeyle üretilir.
(2) **Sınıf başkanı USB anahtarı (deneme)** (kural 37). Şubeye bağlıdır, ad tutulmaz; öğretmen önceliği geçerlidir.
Yalnız kendi şubesinde, o şubenin tahtasında ve şu anki derste çalışır. PIN ister, kilit açmaz. Ayrı ayarı vardır,
varsayılan kapalıdır. Kural 33'e istisnadır; kural 18 ve 29 genişledi.
(3) **Tahta numarası** (`tahta.id`, "No 7"). Yeni tahta "Tahta <no>" adıyla gelir; `kur.sh` "TAHTA NO" satırı
basar; aynı adlılar `POST /tahtalar/adlandir` ile toplu adlandırılır.
(4) **Bildirim alanı durum simgesi** (`tepsi.py`, `pencere --gizli`). Kurucuda işaretli görevle başlangıç kısayolu
kurulur; kısayol yalnız simgeyi getirir, sunucu AÇMAZ (kural 28 istisnası).
(5) **aSc** (kullanıcının bildirdiği sorunlar). Devre grupları (S/Ö öneki ya da saat kullanımı); 9/I ≠ 9/İ; zil
önerisi; tahtaların şube bilgisini güncelleme (geri alınabilir); hatırlanan eşleşmeleri unutma; "deneme"
etiketi kalktı.
Ajan DEĞİŞMEDİ. Sürüm yükseldi: tahtalar "güncelleme var" görür, ajan güncellemesi isteğe bağlıdır. Göç:
`GOCLER`'e iki öğe (aSc, başkan). Ayrıntıdaki kararlar VARSAYILDI, kullanıcı ayrıca yanıtlamadı (§17 soru 102–135,
açık; 134 karar bekliyor, 135 okulun aydınlatma metnidir). Belgeler: `docs/surum-0.21.0.md`, tasarım §4, §12.3, §14, §14.3, §15.6.
Testlerle denendi; ayrıca deneme sunucusunda başsız tarayıcıyla (uydurma veri; 1366 ve 390 px; toplu adlandırma,
öğretmen ve aSc yüklemesi, başkan zip ve pusulası HTTP ile uçtan uca) ve gerçek aSc ve e-Okul dosyalarıyla yerelde
denendi. Dağıtılmadı. Gerçek ETAP'ta, gerçek USB bellekle, okul bilgisayarında, kurulu hizmette ve kurulu Windows'ta
simge görünümüyle denenmedi.

Yerel geliştirme 0.20.0 (kullanıcı onayı 19.11.2026, "Aramaya geç"): panel arayüzünün yeniden düzeninde 6. ve SON
aşama, genel arama. Yan menüde Acil'in altında arama kutusu (yazarken öneri; `/` kısayolu), çekmece kipinde üst
çubukta büyüteç, JS'siz tam sayfa sonuç. Yeni adres yalnız iki: `GET /ara?q=` ve `GET /api/ara?q=` (oturum, `no-store`).
Dizinin TEK yeri `arama.py`'dir ve var olan tanımlardan TÜRER (MENU, `bolum_serit.SERITLER`, `tahta_liste.SUZGECLER`,
`ayar_bolumleri.BOLUMLER`/`BASKA_YERDE`; elle yazılan tek liste `arama.SIK_ISLER`); rol hedef sayfadan türer ve süzme
dizinin içindedir; devingen kısım onaylı tahta, etkin şube ve (yöneticide) grup adıdır. Dizine kişi adı, serbest
metin, ağ/cihaz bilgisi GİRMEZ; sorgu hiçbir yere yazılmaz (kural 36). Arama menü öğesi değildir: menü yine tam on
öğe. Şema, ajan, komut ömürleri, var olan adresler/uçlar/alan adları ve `/api/durum` aynı (sürüm statik dosya önbelleği
için yükseldi); Ayarlar içi arama (`/ayarlar?ara=`) değişmedi. On bir karar VARSAYILDI, kullanıcı ayrıca yanıtlamadı
(§17 soru 91–101, açık). Soru 75 ONAYLANMADI: dizine de ders başlığı/öğretmen bilgisi eklenmez. `docs/surum-0.20.0.md`
("neler aranır / neler bilerek aranmaz" çizelgeleri), tasarım §11.1 (ALTI AŞAMANIN HEPSİ UYGULANDI; planda başka aşama
yok). Testlerle ve deneme sunucusunda başsız Edge ile (uydurma veri, benzetilmiş ajanlar; klavye/öneri etkileşimi, iki
rolde sızıntı denemesi; 1366 ve 390 px) denendi; dağıtılmadı, okul bilgisayarında, gerçek telefonda, gerçek klavyeyle ve
ekran okuyucuyla denenmedi.

Yerel geliştirme 0.19.0 (kullanıcı onayı 19.11.2026, "Sekmelere geç"): panel arayüzünün yeniden düzeninde 5. aşama,
bölüm sekmeleri ve tek sayfalık duyuru formu. Sekme şeritlerinin TEK tanımı `bolum_serit.py`'dir (çizim
`_serit.html`): Yoklama (Günlük · Şube defteri · Mazeret ve izin · Panelden gir · Devamsızlık icmali | Yoklama
ayarları* ↗), Kişiler ve anahtarlar (Öğrenciler · Öğretmenler ve PIN · USB anahtarlar; kendi şeridi), Program (Günü
önizle · Zil saatleri · Derslik programları · Öğretmen programı* | Kurallar · İstisnalar · Uyarılar | İçe aktar* ·
Önceki programlar*), Duyurular (Duyurular ve planlar · Yeni duyuru), Acil durum (Yayın başlat · Geçmiş ve raporlar |
Şablonlar*), Tahtalar (aynı). Yeni duyuru formu tek sayfadır (1. Ne yazılsın? · 2. Kime? · 3. Ne zaman? + gönder
çubuğu). HİÇBİR adres değişmedi/kalkmadı/yönlenmiyor (tek ek: `/acil?sekme=gecmis`); şema, ajan, komut ömürleri,
gönderim uçları, alan adları ve doğrulama aynı (sunucuya yalnız görünüm bilgisi eklendi: `panel_duyuru.hata_yeri`;
sürüm statik dosya önbelleği için yükseldi). Menü yine tam on öğe. Dokuz karar VARSAYILDI, kullanıcı ayrıca
yanıtlamadı (§17 soru 82–90, açık). Soru 75 ONAYLANMADI: hiçbir sayfaya ders başlığı/öğretmen bilgisi eklenmez.
`docs/surum-0.19.0.md` ("hangi sayfa ve sekme nereye gitti" çizelgesi), tasarım §11.1 (6. aşama, genel arama,
0.20.0'da uygulandı). Testlerle ve deneme sunucusunda başsız Edge ile (uydurma veri, benzetilmiş ajanlar; JS açık/kapalı duyuru
gönderimi veritabanından doğrulanarak; 1366 ve 390 px) denendi; dağıtılmadı, okul bilgisayarında, gerçek telefonda ve
gerçek tahtalarla denenmedi.

Yerel geliştirme 0.18.0 (kullanıcı onayı 19.11.2026, "Bugün'e geç"): panel arayüzünün yeniden düzeninde 4. aşama,
Bugün. `/` artık Bugün sayfasıdır (şu an + "Program kilidini durdur", "Sizi bekleyenler", tahtaların durum sayıları
ve konum çipleri, onaylı "Hepsini kilitle…", bugünün yoklama özeti, duyurular); `/tahtalar` yalnız listedir ve
ayrı işleyicidir. Bekleyen işler TEK işlevden çıkar (`bugun.bekleyenler(b, kullanici)`; rol süzmesi içinde; menü
rozeti ve `/api/durum`'un yeni `bekleyen_is` alanı aynı listeden). İki karar VARSAYILDI, kullanıcı ayrıca
yanıtlamadı (§17 soru 80–81, açık): V1 "Güncelleme var" rozeti liste satırında çizilmez; V2 `kapsam=hepsi` sınav
penceresindeki tahtaları atlar. Şema, ajan, komut ömürleri, var olan uçların alan adları ve `/api/durum`'un var
olan anahtarları aynı (sürüm statik dosya önbelleği için yükseldi). Soru 75 ONAYLANMADI: Bugün'e de ders
başlığı/öğretmen bilgisi eklenmez. `docs/surum-0.18.0.md` ("hangi uyarı nereye gitti" çizelgesi), tasarım §11.1
(5–6. aşamalar AYRI onay ister). Testlerle ve deneme sunucusunda başsız Edge ile (uydurma veri, benzetilmiş
ajanlar; JS açık/kapalı komut denemesi) denendi; dağıtılmadı, okul bilgisayarında, gerçek telefonda ve gerçek
tahtalarla denenmedi.

Yerel geliştirme 0.17.0 (kullanıcı onayı 19.11.2026, "Önce Tahtalar'a geç"): panel arayüzünün yeniden düzeninde
3. aşama, Tahtalar. `/tahtalar` konuma göre gruplu tahta listesidir (satırda duruma göre TEK birincil düğme + "⋯"
menüsü, seçince görünen seçim çubuğu, JS'siz `?durum=` süzgeci); 0.17.0'da `/` aynı listeyi çiziyordu (0.18.0'da
Bugün oldu). `/islem`'e iki alan eklendi: `tek=<tür>:<kimlik>` (yalnız o tahta; işaretli liste okunmaz) ve
`kapsam=hepsi` (yalnız kilitle; onaylı + çevrimiçi; düğmesi 0.18.0'da Bugün'de). `GET /duyurular/yeni?tahta=…` ön seçimi; tahta
sayfası `?sekme=` genel · program · bakim · bilgiler; Tahtalar bölümünün sekme şeridi (yan menüde alt liste kalktı).
Şema, ajan, komut ömürleri, var olan uçların alan adları ve `/api/durum`'un var olan anahtarları aynı (tek ek:
`tahtalar[].liste`; sürüm statik dosya önbelleği için yükseldi). Soru 75 (panelde ders başlığı) ONAYLANMADI:
listeye ve tahta sayfasına ders başlığı/öğretmen bilgisi eklenmez. `docs/surum-0.17.0.md`, tasarım §11.1.
Testlerle ve deneme sunucusunda başsız Edge ile (uydurma veri, benzetilmiş ajanlar; JS
açık/kapalı komut denemesi) denendi; dağıtılmadı, okul bilgisayarında, gerçek telefonda ve gerçek tahtalarla
denenmedi.

Yerel geliştirme 0.16.0 (kullanıcı onayı 19.11.2026): panel arayüzünün yeniden düzeninde 2. aşama, Ayarlar.
`/ayarlar` giriş sayfasıdır (11 bölüm kartı ve o anki değer özetleri, kurulum kontrol listesi, Ayarlar içi arama;
`?ara=` JS'siz), `/ayarlar/{bölüm}` bölüm sayfalarıdır; her kart kendi Kaydet'iyle yalnız kendi anahtarını yazar.
Yeni gönderim bölümleri `bolum=okul`, `kapatma`, `kilit_kodu`; `bolum=genel` yalnız uyumluluk için durur.
Kullanıcılar Ayarlar'ın bölümü (menü 9 öğe; GET /kullanicilar → /ayarlar/kullanicilar), acil şablonları
`/acil?sekme=sablonlar`. Ayar anahtarları, öbür uçlar, şema ve ajan aynı (sürüm statik dosya önbelleği için
yükseldi). `docs/surum-0.16.0.md`, tasarım §11.1 (3–6. aşamalar AYRI onay ister). Testlerle ve deneme sunucusunda
başsız Edge ile (uydurma veri; JS açık/kapalı kayıt denemesi) denendi; dağıtılmadı, okul bilgisayarında ve kurulu
hizmette denenmedi.

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
- Durum: **0.22.0, yerel geliştirme; dağıtılmadı.** Okulda kurulu sürüm 0.20.0'dır (24 ETAP tahtası; kullanıcı
  bildirimi 21.11.2026); 0.21.0 GitHub'da yayımlandı. 0.22.0: açılışta otomatik giriş (kural 39, tasarım §5.2;
  ajan değişti, göç yok; gerçek ETAP'ta denenmedi). 0.21.0: sahadan beş talep — toplu öğretmen yükleme, sınıf başkanı USB anahtarı (kural 37),
  tahta numarası ve toplu adlandırma, bildirim alanı durum simgesi, aSc ikili eğitim/I-İ/zil önerisi/şube bilgisi.
  Yalnız sunucu değişti, ajan değişmedi. Testlerle, başsız tarayıcıyla ve gerçek dosyalarla yerelde denendi; gerçek
  ETAP'ta, gerçek USB'de ve kurulu hizmette denenmedi; tasarım §4, §12.3, §14, §14.3, §15.6. (0.20.0: panel
  arayüzü 6. ve son aşama — genel arama (`/ara`, `/api/ara`; dizin tek yerde `arama.py`, var olan tanımlardan türer,
  rolle süzülür, kişi adı ve serbest metin yok, sorgu hiçbir yere yazılmaz; kural 36); yalnız sunucu, ajan değişmedi;
  testlerle ve deneme sunucusunda başsız tarayıcıyla (klavye ve öneri etkileşimi, iki rolde sızıntı denemesi, 1366
  ve 390 px, uydurma veri) denendi, gerçek telefonda, gerçek klavyeyle ve ekran okuyucuyla denenmedi; tasarım §11.1;
  0.19.0: panel
  arayüzü 5. aşama — bölüm sekme şeritleri (tek tanım `bolum_serit.py`; Yoklama, Kişiler ve anahtarlar, Program,
  Duyurular, Acil durum) ve tek sayfalık duyuru formu; adresler, uçlar, alan adları ve doğrulama aynı; yalnız
  sunucu, ajan değişmedi; testlerle ve deneme sunucusunda başsız tarayıcıyla (JS açık/kapalı duyuru gönderimi, 1366
  ve 390 px, uydurma veri) denendi, gerçek tahtayla denenmedi; tasarım §11.1; 0.18.0: panel
  arayüzü 4. aşama — `/` Bugün sayfası (bekleyen işler tek listede, durum sayıları ve çipler, onaylı "Hepsini
  kilitle…", yoklama özeti yalnız sayı, duyurular), `/tahtalar` yalnız liste; V1 ve V2 varsayıldı (§17 soru
  80–81); yalnız sunucu, ajan değişmedi; testlerle ve deneme sunucusunda başsız tarayıcıyla (JS açık/kapalı
  komut denemesi, 1366 ve 390 px, açık/koyu, uydurma veri) denendi, gerçek tahtayla ve gerçek telefonda
  denenmedi; tasarım §11.1; 0.17.0: panel
  arayüzü 3. aşama — tahta listesi, `/islem`'e `tek` ve `kapsam=hepsi`, tahta sayfası sekmeleri; yalnız sunucu,
  ajan değişmedi; testlerle ve deneme sunucusunda başsız tarayıcıyla (JS açık/kapalı komut denemesi, 1366 ve
  390 px, uydurma veri) denendi, gerçek tahtayla denenmedi; tasarım §11.1; 0.16.0: panel
  arayüzü 2. aşama — Ayarlar giriş sayfası ve 11 bölüm; yalnız sunucu; yalnız deneme sunucusunda başsız
  tarayıcıyla denendi; 0.15.0: panel
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
- Ders programı ve program kilidi `docs/tasarim.md` §12 (öğretmen programı ve kilit ekranı gün programı §12.5); sınav kipi §13; ders yoklaması §14 (0.14.0 yeniden tasarımı §14.2; sınıf başkanı anahtarı §14.3); tahta numarası §4;
  altyapı (yedek, adres listesi, envanter, arıza) §15, Windows hizmeti §15.6; yol haritası §16; okul idaresinin kesin
  kararları (K1–K8, 16.11.2026) ve kullanıcıya sorulacaklar §17; doğrulanacak dayanaklar §18.
  Kararlar yeniden tartışılmaz; bir kararla çelişen öneri yapılmaz.

## Komutlar (PowerShell 5.1; `&&` yok)

```powershell
uv sync                                   # bağımlılıklar (.venv, Python 3.12)
uv run python -m tahta_sunucu             # sunucu: http://127.0.0.1:8787 · https://<ip>:8788
uv run python -m tahta_sunucu pencere     # durum penceresi (hizmet yoksa sunucuyu pencerede çalıştırır)
uv run python -m tahta_sunucu pencere --gizli   # yalnız durum simgesi; geliştirmede TAHTA_TEPSI_DENE=1 ister, sunucu AÇMAZ
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
`TAHTA_HTTP_PORT` (8787, yalnız 127.0.0.1), `TAHTA_HTTPS_PORT` (8788, okul ağı), `TAHTA_TEPSI_DENE=1` (0.21.0:
geliştirmede durum simgesini dener; sunucu açılmaz).
Ajan: `TAHTA_AJAN_DIZIN`, `TAHTA_AJAN_DURUM`, `TAHTA_AJAN_BENZETIM=1` (kapatma komutu uygulanmaz).

## Yerleşim

```
tahta_sunucu/   FastAPI + SQLite + Jinja2 (HTMX yok, az miktar düz JavaScript)
  web.py        uygulama_olustur: oturum, Bugün (`/`), tahta listesi ve sayfası, ayarlar, /marka/*, /ajan/* (uzun bekleme);
                0.20.0: `ARAMA = arama.kur(MENU, MENU_ACIL, _secili)` MENU'den hemen sonra, modül düzeyinde (sahipsiz
                arama hedefi içe aktarmada ValueError verir: program AÇILMAZ); `ara_sayfasi` (GET /ara) ve `api_ara`
                (GET /api/ara; < 2 karakterde veritabanına gitmez) ortak `arama_sonucu`'ndan; ikisi de kayıt/günlük
                ÇAĞIRMAZ; şablon evrenseli `ara_en_uzun` (= ayar_bolumleri.SORGU_EN_UZUN); `sayfa()` ve /api/durum'a
                arama için sorgu EKLENMEDİ
                MENU (0.15.0): üç küme (Her gün, Dönemlik, Yönetim), ≤ 10 üst öğe (0.18.0'da TAM 10: Bugün eklendi),
                öğede `rol`/`simge`/`esler`/`alt`/`alt_cubuk`/`sayi`; MENU_ACIL kümelerin dışında; menu_gorunumu →
                {kumeler, alt_cubuk} (rolle süzülür); alt çubuk Bugün · Tahtalar · Duyurular · Yoklama · Menü
                0.18.0: `bugun_sayfasi` (`/`; `?durum=`/`?s=` taşıyan eski adres /tahtalar'a 303), `tahtalar_sayfasi`
                (yalnız `/tahtalar`), ortak `tahta_baglami` (iki sayfa ve /api/durum aynı `tahta_gorunumu`);
                `sayfa()` menü rozetlerini `bugun.bekleyenler(…, yalniz_rozet=True)` → `rozet_sayilari`'ndan alır;
                /api/durum'a eklemeli `bekleyen_is {sayi, imza}`; `yerel_ipler` (60 sn) ve `kurulum_onbellegi`
                (30 sn) süreç içi bellek; `islem` kapsam dalında sınav süzmesi (V2); `altyapi_uyarilari` SİLİNDİ
                0.21.0: `/ajan/kaydol` adı `tahta_liste.varsayilan_ad`'dan verir (INSERT + aynı işlemde UPDATE; makine
                adı yalnız `makine_adi`'nda); `POST /tahtalar/adlandir` (yalnız yönetici, `eylem=adlandir`; liste
                sunucuda `adlandirilacaklar`'dan, sabit noktaya kadar; yalnız `ad` yazılır, kayda yalnız sayı);
                `/tahta/{id}/kaydet` aynı adı reddetmez, numaralarla uyarır; `tahtalar_sayfasi` → `ayni_ad_sayisi`
                (yalnız yönetici); `usb_anahtar_kaydet` başkan kapanınca başkan belirteçlerini siler
  panel_duyuru.py   duyuru/plan uçları, /api/hedef-onizleme   (web.py'den `kaydet(uygulama, y)` ile);
                    0.19.0: hata_yeri (icerik | kime | zaman — iletinin tek sayfalık formda çizileceği bölüm; YALNIZ
                    görünüm, doğrulama yolu değişmedi)
  arama.py          genel aramanın dizini, TEK yer (0.20.0, FastAPI'siz; web'i içe aktarmaz, `_secili` parametreyle gelir;
                    kural 36): SIK_ISLER (elle yazılan tek liste: var olan GET sayfasına kısa yol + eş anlamlılar; `one` =
                    sorgu boşken "Sık işler" sırası; açık `rol` yalnız daraltır), yer_coz(yol) → (kırıntı, rol) — rol
                    hedef sayfadan türer, sahipsiz yol ValueError; sabit_dizin (sayfa ← MENU+MENU_ACIL, sekme ← SERITLER
                    `dis` hariç, is ← BASKA_YERDE+SIK_ISLER, suzgec ← SUZGECLER, ayar ← BOLUMLER; kurulurken kendini
                    denetler), kur (süreç başında bir kez), devingen_dizin (onaylı tahta: ad/derslik/bina/kat/şubeler;
                    yoklama açıksa etkin şube → şube defteri; yöneticide grup adı → /gruplar#grup-<no>; ≤ 4 dar SELECT,
                    önbellek YOK), sorgu_duzelt, ara (önce rol, sonra eşleşme: kesin → katlı → ekli `_ekli_uyar`; kademe;
                    TUR_SIRASI; aynı yol bir kez; dönen sözlükte iç alan yok), gruplu (GRUP_SIRASI), sik_isler; sınırlar
                    ONERI_EN_COK 8, SAYFA_EN_COK 50, SOZCUK_EN_COK 6, ONERI_EN_KISA 2, EK_KOK_EN_KISA 4, SIK_EN_COK 8;
                    metin ilkelleri ayar_bolumleri'nden içe aktarılır (ikinci harf haritası yok)
  bolum_serit.py    bölüm sekme şeritlerinin TEK tanımı (0.19.0, FastAPI'siz, saf): SERITLER (yoklama, kisiler, program,
                    duyurular, acil, tahtalar; küme listeleri; sekmede `rol`/`sayi`/`dis`), gorunum(ad, rol, etkin,
                    sayilar) (rolle süzer, boş küme düşer, tam bir etkin sekme), sayfa_onekleri (menü `esler` testi);
                    şablon evrenseli `bolum_seridi`; çizim sablonlar/_serit.html::ciz
  panel_tahtalar.py gruplar, /tahtalar.csv ve CSV içe aktarma
  tahta_liste.py    tahta listesi (0.17.0, FastAPI'siz, saf): SUZGECLER, durum_ozeti (satırın durumu, rozetleri,
                    birincil düğmesi, menü pasiflikleri — durum kuralının TEK yeri), menu_ogeleri, gruplar (bina ·
                    kat), sayilar, suzgec_coz, tek_coz, islem_hedefi, TEK_TURLERI, KAPSAM_HEPSI_TURLERI,
                    guvenli_donus, liste_yolu_mu (0.18.0: yalnız `/tahtalar`), sekme_coz; rozet sözlüğünde eklemeli
                    `liste: False` (V1: düz "Güncelleme var" satırda çizilmez) ve `cip: False` (Bugün çipinin
                    okunur metnine girmez); 0.21.0: varsayilan_ad ("Tahta <id>"), ad_anahtari (= metin.katla),
                    ayni_adlilar, adlandirilabilir_mi (ad = makine adı ya da "Yeni tahta"), adlandirilacaklar — aynı ad
                    kuralının TEK yeri (kayıt uyarısı, bant, toplu adlandırma, Bugün çipinin `no`'su); gruplar içinde
                    doğal sıra (`metin.dogal_sirala_anahtari`)
                    web.py 0.17.0: `tahtalar_sayfasi` listeyi çizer (0.18.0'dan beri yalnız `/tahtalar`; `/` Bugün'dür);
                `tahta_gorunumu` her tahtaya `liste` ekler (şablon ve /api/durum aynı sözlük); POST /islem hedefi
                `tahta_liste.islem_hedefi`'nden (nöbetçi → tek → kapsam → liste; dallar arası düşme yok);
                /tahta/{id} `?sekme=` (`tahta_liste.sekme_coz`); MENU'de Tahtalar `/tahtalar`, `alt` listesi yok
  bugun.py          Bugün sayfası (0.18.0, FastAPI'siz): bekleyenler(b, kullanici, …) — bekleyen işlerin TEK listesi
                    (üretici başına bir koşul; rol süzmesi İÇİNDE; tehlike → uyarı → bilgi; üst sınır yok;
                    `yalniz_rozet` menü için), rozet_sayilari, satir_sayisi, imza (anahtar:sayı; metin taşımaz),
                    acik_satir_sayisi (uyarı katlanmaz), kurulum_satiri, guncel_olmayan_sayisi; akis (ders no +
                    başlangıç saati), tahta_ozeti (durum kutuları, konum çipleri, `kilit_hedefi`; > CIP_EN_COK=60
                    tahtada grup kipi), yoklama_ozeti (yalnız sayı + şube adı; `yoklama_defter.Veri`), duyuru_ozeti
                    (başlık, tahta sayısı, saat; metin SELECT edilmez). Ürettiği sözlüklerde kişi adı, okul no,
                    mazeret türü, ders başlığı, arıza açıklaması, duyuru metni, bekleyen tahtanın adı/adresi yok
  panel_acil.py     /acil: başlatma, bitirme, rapor; `?sekme=` '' (Yayın başlat) | gecmis (0.19.0) | sablonlar (yalnız
                    yönetici); hata çizimi her zaman "Yayın başlat"; süren yayın kutusu _acil_aktif.html (iki sekmede)
  panel_program.py  /program (sekmeler: zil, derslik, kurallar, istisnalar), /program/uyarilar, /tahta/{id}/program;
                    zil_baglami (zil sekmesinin çizelge kısmı), Okul Zili'nden al → cizelge.okulzili_yaz
  panel_cizelge.py  zil düzenleyici (0.10.0): /program/cizelge[/{id}[/hizli|kopyala|sil|csv]], /program/haftalik,
                    /program/tarihli[/{id}/sil], /program/gun (günü önizle); Etki: bugünkü plan değişirse açma
  panel_aktar.py    ders programı içe aktarma sihirbazı (0.10.0): /program/aktar[/asc|tablo|esle|onayla|sablon.csv|
                    mevcut.csv|istem.txt], /program/gecmis[/{id}/geri-yukle]; eski /program/derslik/yukle|onayla → 303;
                    0.12.0: /program/aktar/eokul (rapor yükleme), /program/aktar/eokul/zil (rapordan zil çizelgesi)
                    0.21.0: aSc zilsiz de yüklenir; /program/aktar/asc/zil (onaylı zil önerisi), /program/aktar/unut
                    (kaynağın hatırlananları, onaylı); eşleme formunda `g_<n>` (devre grubu; `devre_secimi` kalktı);
                    onayda `subeleri_guncelle=1` (yalnız aSc; program aynıyken de onaylanabilir)
  panel_sinav.py    /sinavlar, /sinav/{id} (künye, eşleştirme, durum, uzatma, kip kaldırma, kodlar, şube
                    duyurusu, salon yoklaması, icmal), /api/sinav/{id}, /ajan/sinav/{kod,yoklama}
  panel_yoklama.py  /yoklama (günlük ızgara, kayıt/düzeltme, panelden gir, icmal + .csv, e-Okul işareti),
                    /ogretmenler (PIN pusulası), /ogrenciler (önizle/aktar/temizle), /ajan/yoklama/*;
                    sonunda şablon bağlamlarının SÖZLEŞME bloğu; 0.21.0: /ogretmenler/onizle, /ogretmenler/aktar (yalnız
                    yönetici, yetki form okunmadan; önizleme ortak OnizlemeDeposu'nda {"tur": "ogretmen_aktar"}, tek
                    kullanımlık, Vazgeç siler), GET /ogretmenler/sablon.csv; `liste_denetimi` başkan oturumunda
                    `yoklama.baskan_denetle` (/liste ve /kaydet)
  panel_defter.py   şube defteri ve mazeret uçları (0.14.0; `kaydet` panel_yoklama.kaydet içinden çağrılır):
                    /yoklama/sube (beş gün / gün kipi), /yoklama/sube/hucre (fırça; JSON ya da 303),
                    /yoklama/sube/toplu (Alındı iki adım, Bütün gün yok, Temizle), /yoklama/son-gunler,
                    /yoklama/ogrenci/{id}, /yoklama/mazeret[/onizle|onayla|{id}/iptal]; hepsi no-store
  panel_usb.py      USB anahtar (0.11.0): /usb-anahtarlar (üret, iptal), /usb-anahtarlar/indir/{belirtec} (tek
                    seferlik, 5 dk), /ajan/usb/{tani,yoklama,kilit_ac}; sonunda SÖZLEŞME bloğu; 0.21.0: `sahip=baskan`
                    üretimi (yalnız yönetici; yanıt PIN pusulası, tek şubede dosya, çokta tek seferlik zip),
                    `sube_secenekleri`, `tanima` → `baskan_kapali` 409 (kayda düşmez), /ajan/usb/yoklama başkan dalı,
                    /ajan/usb/kilit_ac şube anahtarına PIN sormadan 403
  panel_ogretmen_program.py  öğretmen programı (0.13.0): /ogretmen-programi[/onizle|vazgec|uygula]; yalnız yönetici;
                    dosya ayrıştırma iş parçacığı havuzunda; önizleme OnizlemeDeposu'nda (15 dk, Vazgeç'te silinir)
  usb_anahtar.py    USB anahtar iş mantığı (FastAPI'siz): ayar, dosya biçimi/ayrıştırıcı (ajandakiyle aynı),
                    bekleyen indirmeler, tanıma, PIN (öğretmen PIN'i ya da anahtar PIN'i), kopya uyarısı, iptal, yıl sonu;
                    0.21.0: şube anahtarı (`sahip_turu='sube'`, `sube`), ayar `baskan`/`pin_baskan` + nöbetçi
                    `ua_baskan_formu` (`ayar_coz(form, onceki)`), `baskan_acik`, `izinler` (şubeye `kilit_ac` yok),
                    SUBE_BASI_EN_COK 2, TOPLU_EN_COK 80, BekleyenPaket, paket_zip (stdlib zipfile, ASCII OKUBENI.txt),
                    tani → `baskan_kapali`, yil_sonu şube anahtarlarını siler
  panel_altyapi.py  /yedekler (parola, ayar, al, indir, geri-yukle + onay/uygula), /envanter (+ .csv),
                    /tahta/{id}/envanter, /tahta/{id}/donanim-goruldu, /arizalar, /ariza/{id}, /yerel/durum
  ayar_bolumleri.py  Ayarlar'ın tek listesi (0.16.0, FastAPI'siz): BOLUMLER, BASKA_YERDE, ESKI_YER, ESKI_PARCA,
                ara (Türkçe küçültme + harf katlama; panel.js ile aynı harita), ozetler (sır taşımaz), kurulum, menu;
                0.20.0: `uyar` (eski `_uyar`), `kucult`, `katla`, `sozcukler`, `samanlik`, `SORGU_EN_UZUN` genel aramanın
                da TEK metin ilkelleridir (arama.py içe aktarır); BASKA_YERDE öğeleri genel dizine `is` olarak AYNEN
                girer — öğenin `yol`'u hedef sekmenin yoluyla birebir yazılır (ör. `/program?bolum=zil`), yoksa sonuçta
                aynı sayfa iki satır çıkar; `tahta_liste._grup_adi` → `grup_adi` (arama da kullanır)
                uçlar web.py'de: GET /ayarlar (giriş, `?ara=`), GET /ayarlar/{bölüm}, POST /ayarlar `bolum=…`;
                şablonlar ayarlar.html (giriş), ayar_bolum.html, _ayar.html (makrolar), _ayar_<bölüm>.html;
                /yedekler/parola ve /yedekler/ayar isteğe bağlı `donus=ayarlar` alır (yalnız dönüş adresi)
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
                0.20.0: yan menüde Acil'den sonra, gezinmeden önce `form.genel-ara` (düz GET /ara, `name="q"`,
                `data-genel-ara`, gönder düğmesi yok; combobox öznitelikleri ŞABLONDA YOK, panel.js ekler), üst çubukta
                kimlik ile Acil arasında `a.ust-ara` (/ara); ara.html (sonuç sayfası: `#ara-q` kutusu `data-ara-oneri`,
                gruplar Sayfalar ve işler · Ayarlar · Şubeler · Tahtalar · Gruplar, sabit sonuçsuz notu `#ara-bos`,
                sorgu boşken "Sık işler"; başlıkta sorgu yok); gruplar.html satırı `id="grup-<no>"`;
                0.18.0: bugun.html (Bugün; kancalar `data-alan`, `data-sayi`, çip `data-id`; `bugun-veri` JSON),
                _bugun.html (makrolar: is_satiri, cip, durum_kutulari); _pano_bantlar.html SİLİNDİ; tahtalar.html
                yalnız /tahtalar'ı çizer (kalan bantlar: onay bekleyen, kilit kodu yok, yenile; grup `id="grup-<no>"`);
                yeni simgeler `m-bugun`, `s-ariza`;
                0.19.0: _serit.html (bölüm sekme şeridinin TEK makrosu `ciz`; `href`'ten hemen sonra `aria-current`),
                _kisiler_bas.html (Öğrenciler, Öğretmenler ve PIN, USB anahtarlar; _yoklama_bas ile aynı bağlam),
                _acil_aktif.html (süren yayın kutusu), duyuru_form.html tek sayfa (Ne · Kime · Ne zaman, gönder çubuğu);
                program.html, uyarilar.html ve ortak başları _program_bas.html (durum şeridi + bölüm sekme şeridi; bolum =
                gun|zil|derslik|ogretmen_program|kurallar|istisnalar|uyarilar|aktar|gecmis; çizen HER sayfa `serit` verir:
                program_gun, program_aktar, program_gecmis, ogretmen_program dahil);
                cizelge.html, program_gun.html, _zaman_cizgisi.html (SVG + liste makrosu), program_aktar.html,
                program_gecmis.html (0.10.0);
                sinavlar.html, sinav.html, sinav_yoklama.html, sinav_kodlar.html, sinav_icmal.html, _sinav.html;
                yoklama*.html, ogretmenler.html, ogretmen_program.html (0.13.0), ogretmen_pusula.html, ogrenciler.html, ogrenci_onizleme.html
                ve ortak başları _yoklama_bas.html (Yoklama şeridi + KVKK notu; bolum = gunluk|sube|mazeret|gir|icmal;
                0.19.0: kişi sayfaları _kisiler_bas.html'i, ogretmen_program.html _program_bas.html'i çizer; son günler
                şeritte `sube` etkin çizilir); usb_anahtarlar.html, usb_anahtar_uretildi.html;
                0.14.0: yoklama_sube.html (şube defteri), yoklama_son_gunler.html, yoklama_mazeret.html,
                yoklama_mazeret_onizleme.html, yoklama_ogrenci.html, _yoklama_hucre.html (hücre makrosu + lejant);
                yedekler.html, yedek_onay.html, yedek_geri_yukle.html, envanter.html, arizalar.html,
                ariza.html, _ariza.html (durum rozeti + açma formu makroları), _tahta_altyapi.html;
                0.21.0: ogretmen_onizleme.html (toplu öğretmen önizlemesi), usb_baskan_pusula.html (başkan PIN pusulası);
                tahtalar.html `#ayni-ad` bandı + `#ayni-ad-formu` (`data-onay="adlandir"`, JS'siz gönderilmez);
                "ad · No <id>" tahta.html, _tahta_komut.html, _tahta_altyapi.html, arıza sayfaları, _bugun.html::cip;
                program_aktar.html devre grubu tablosu, aSc zil önerisi, "Hatırlanan eşleşmeler", şube kutusu
  yoklama.py    ders yoklaması iş mantığı (FastAPI'siz): ayar, A3 uyarlama işlevleri, öneri (0.14.0: ders_kurali —
                süren → 5 dk içinde başlayacak → son 15 dk'da biten; teneffüste ders_adaylari; pencere_devresi;
                ogretmen_onerisi dar SELECT), gec_secilebilir, PIN kapısı (3 katman), belirteç, yoklama_yaz (upsert +
                iz; yok + geç + devre), gecerli_durum, günlük görünüm, icmal/metin/CSV, aktarım, imha;
                0.21.0: `baskan_denetle` (başkanın dar yetkisinin TEK yeri), `oturum_coz` üçüncü dal (`tur='baskan'`),
                `oturum_kaydedeni` ('baskan:10/A'), `oturum_kaynagi`, KAYNAK_BASKAN, BASKAN_NOTU
  yoklama_defter.py  şube defteri, son günler, mazeret (0.14.0, FastAPI'siz): Veri (aralığı toplu yükler; sorgu
                sayısı öğrenci/şube sayısından bağımsız), TEK birleşim kuralı (gecerli_duzeltmeler, kumeler,
                hucre_durumu; kural 34), hucre_yaz (düzeltme katmanı), sutun_alindi, ogretim_gunleri, ardisik_yok,
                sube_defteri, sube_gunu, son_gunler, ogrenci_gorunumu, mazeret_coz/onizle/yaz/iptal, eokul_bayat;
                0.21.0: `Veri.baskan_kaydi` (bellekten; defterde `b` işareti)
  eokul.py      öğrenci listesi ayrıştırıcı: e-Okul OOG01001R020 .xls (xlrd), düz .xlsx/.csv; 0.21.0:
                `baslik_esle(matris, alan_bul, kullanilir_mi)` (parametresizken öğrenci davranışı), `matris_oku(veri,
                asiri_ileti)`, kod sayfasız BIFF5'te cp1254 yedeği
  ogretmen_aktar.py  toplu öğretmen yükleme (0.21.0, FastAPI'siz; kural 38): dosya_oku (içerikten: `<` → aSc
                `asc_ogretmenleri`, ayrı expat okuyucu, yalnız teacher@firstname|lastname, yarımsa `name`; değilse
                `eokul.matris_oku`), matris_coz (eş anlamlılar SÖZCÜK SINIRIYLA; `_eokul_raporu_mu`: ADI SOYADI +
                GÖREVİ + KADRO/BRANŞ ve Kod sütunu yok), ad_bicimle (tamamı büyük ya da küçükse `metin.tr_bas_buyuk`),
                plan (ekle | var | pasif | yinelenen; katlanmış tam ad; kod dosyadan, yoksa 101'den; yazmaz), uygula
                (planı işlem içinde yeniden hesaplar; pin_ozet NULL), sablon_csv
  sinav.py      sınav iş mantığı: R5 ayrıştırma, içe aktarma, eşleşme önerisi, süreler/evreler, ayar.sinav,
                gözetmen kapısı (bellekte), yoklama, şube duyurusu, icmal, saklama temizliği
  xlsx.py       yalnız standart kitaplıkla .xlsx okuyucu (zip/DOCTYPE sınırları; A5 de kullanır)
  guvenli_xml.py  DTD/varlık reddi (expat; defusedxml yok) ve windows-1254 → UTF-8 (xlsx.py ve aSc okuyucu)
  cizelge.py    zil çizelgeleri (0.10.0, saf + birkaç b yardımcısı): taslak ↔ form/veritabanı, dogrula, numarala,
                hizli_uret, araliklar, zaman_cizgisi (SVG ölçüleri + liste), gunlere_bol, haftalik_yaz (ders_saati
                TÜRETİLMİŞ tablodur, elle yazılmaz), tarihli_kural, numara_kaymasi, okulzili_yaz, ilk_tasima, CSV
  program_aktar.py  ders programı içe aktarma (0.10.0): asc_oku (izinli öznitelikler; öğretmen/ders adı okunmaz),
                tablo_oku (v2, v1 uyumlu), yz_metni_temizle, esle, fark, uygula, program_surum (10), geri_yukle;
                0.21.0: aSc şube anahtarı `sube_duzelt` (katla DEĞİL), `breaks` (yalnız saatler), asc_devre_gruplari
                (önek → kullanım bölmesi DEVRE_HAPSI_ORANI/DEVRE_KAPSAMA → tek grup; `saatsiz`), grup → zil devresi
                eşlemesi, ikinci derslik adayı `metin.rakam_anahtari` (durum "rakam", hatırlanmaz), tahta_etiketi
                ("No {id} · ad · derslik"), sube_guncellemesi + `program_surum.tahta_json` (geri yüklemede yalnız
                değişmemiş tahta), asc_zil_hazirla/asc_zil_yaz, hatirlananlari_unut; eslesmeleri_yaz otomatik saat/devre
                eşlemesini YAZMAZ
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
  otomatik_giris.py  açılışta otomatik giriş (0.22.0; kural 39): ayar `otomatik_giris` = dokunma | ogretmen | kapali;
                ajan_gorunumu (dokunmada None → alan GÖNDERİLMEZ; yoksa {"hesap": "ogretmen" | None}), engel (kod yok /
                açılışta kilit kapalı), HESAPLAR (ajanla aynı), tahta_durumu (ajanın bildirdiğini süzer; sınıf adı),
                sayilar (Ayarlar kartı); uç web.py `otomatik_giris_kaydet` (bolum=otomatik_giris, `og_kip`); kart
                _ayar_kilit.html `#giris`; tahta sayfası _tahta_altyapi.html "Otomatik giriş" satırı; Bugün
                `bugun._otomatik_giris` (yalnız yönetici, uyarı)
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
  metin.py      Türkçe metin, şube biçimi, CSV okuma/yazma (aşamalar arası ortak); 0.21.0: tamami_buyuk_mu,
                tr_bas_buyuk ("IŞIK" → "Işık", harf olmayan her karakterden sonra büyük; NFC), dogal_sirala_anahtari
                (sinav.sirala_anahtari ona devreder), rakam_anahtari ("DERSLİK-101" → "101")
  tema.py       okul renklerinden bütün panel ve tahta tonları (OKLCH, kontrast eşikleri)
  marka.py      okul logosu: PNG/JPEG denetimi, ölçü okuma, saklama (veri_dizini/marka/logo)
  vt.py         şema ve göçler (GOCLER listesi, PRAGMA user_version; göç öncesi kopya veri_dizini/goc-oncesi)
  guvenlik.py   parola (scrypt), sunucu sertifikası ve parmak izi, kilit kodu özeti, tc_kimlik_var
  wol.py        uzaktan açma (Wake-on-LAN) sihirli paketi; birkaç yayın adresine gönderir ("deneysel")
  paket.py      ajan .deb paketini ve kurulum betiğini dış araç olmadan üretir
  sunucu.py     iki dinleyici: yerel HTTP + ağ için HTTPS; zamanlayıcı (state.zamanlayicilar, 20 sn)
  pencere.py    durum penceresi (tkinter): /yerel/durum + `sc query` ile kip seçer; kurulu programda
                sunucu AÇMAZ (hizmetin durumunu gösterir, "Hizmeti başlat" UAC ister); geliştirmede eskisi gibi;
                0.21.0: `calistir(gizli)`, `DurumUygulamasi` (tek Tk kökü, içerik Frame'de yeniden çizilir; olaylar
                queue + after(200); X/"Gizle" → withdraw, ilk gizlemede balon; çıkış simge menüsünde), `pencere_kipi`
                (kip_sec'e HER ZAMAN paketli=True; sc ve /yerel/durum okunamazsa `okunamadi`), `bekleniyor_metni`,
                `_gelistirme_kipi_mi`; sunucu yalnız `_gelistirme_penceresi`'nde içe aktarılır
  tepsi.py      bildirim alanı durum simgesi (0.21.0; pywin32 yalnız işlev içinde): saf tepsi_durumu (ipucu ≤ 127,
                ağ adresi/okul adı yok), menu_ogeleri, kararli_tur + gecis_bildirimi, sonraki_bekleme, simge_adaylari;
                DurumIzleyici (15 sn; açılışta/başlattan sonra 20 sn boyunca 1 sn); Tepsi (kendi iş parçacığında
                görünmez ÜST DÜZEY pencere + PumpMessages; NIM_ADD/MODIFY/DELETE, TaskbarCreated, WM_CLOSE → "Çık";
                seçim queue'ya); tek_ornek_al (`Local\TahtaKontrolDurum`), var_olani_goster, uyari_kutusu
  hizmet.py     Windows hizmeti kabuğu: saf `govde()` + pywin32 sınıfı (yalnız hizmet çalışırken içe aktarılır),
                gunluk\sunucu.log (5 MB × 3), geri yüklemede 75 koduyla çıkış (`yeniden_baslat_planla`)
  tasima.py     0.8 öncesi veriyi (%LOCALAPPDATA%) %PROGRAMDATA%'ya KOPYALAR (kurucu çağırır; çıkış kodları
                0/10/11/20/21); belirsizlik/hatada TASIMA-BEKLIYOR.txt → hizmet açılmaz
  statik/       stil.css (tek dosya; katmanlar `sifirla, temel, bilesen, kabuk, yardimci`; ölçek belirteçleri
                `--yazi-*`, `--b1..7`, `--kose-*`, `--golge-*`, `--dokunma`; kabuk kipi `--kb-*`), panel.js (tek dosya,
                kütüphanesiz; `kabukKur` = çekmece; `bugunKur` = Bugün'ün canlı tazelemesi ve `ONAY.hepsini_kilitle`;
                0.20.0: `aramaKur` = `/` kısayolu + iki kutu için ortak `aramaOneriKur` (combobox/listbox, /api/ara,
                150 ms bekleme, AbortController, yalnız textContent; eşleştirme ve dizin JS'te YOK), `kabukCekmeceAc`
                (kısayolun çekmeceyi açması için kabukKur'un dışarı verdiği tek işlev); stil.css kabuk katmanında
                `.genel-ara`, `.ara-oneri`, `.ust-ara`, `--kb-kisayol`; yan menü ızgarası BEŞ satır),
                isaret.svg (ürün işareti; 19.11.2026 kararı: ad "Tahta Kontrol" kaldı, işaret "onaylı tahta";
                Windows simgesi packaging/windows/tahta-kontrol.ico aynı çizimden, elle üretilir)
  ajan_paket/   .deb'e giren dosyalar: control, postinst, prerm, servis, kur.sh, tahta-yoklama.desktop,
                tahta-ariza.desktop; 0.21.0: kur.sh (`paket.kurulum_betigi` üretir) kayıttan sonra ajan.json'dan
                `tahta_id` okuyup çerçeveli "TAHTA NO" satırı basar (ASCII; okunamazsa sessiz)
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
                adres/hesap/çıktı ortam değişkeniyle (PANEL_ADRES, PANEL_KULLANICI, PANEL_PAROLA, PANEL_CIKTI), çıktı depo DIŞINA;
                0.20.0: SAYFALAR'da `ara`, `ara-sube`, `ara-ayar`, `ara-sonucsuz`
scripts/durum_simgeleri.py  durum simgelerini üretir (0.21.0; saf Python ICO, Pillow yok, belirlenimci; 16/24/32 px
                BGRA): packaging/windows/durum-{calisiyor,bekleniyor,durdu}.ico; pakette tahta_sunucu/simgeler/
scripts/ekran_olcum.py  Docker/Xvfb'de her tahta sayfasının ekrana sığıp sığmadığını ölçer (uydurma veri); 0.14.0:
                yoklama senaryoları (yk-secim-*, yk-liste-*), kaydırmasızlık ve dokunma ölçüsü denetimi, `--yalniz`
  __main__.py   komut satırı; `tahta-ajan yoklama` ("Yoklama Al" kısayolu) servise yoklama_ac yollar;
                `tahta-ajan ariza` (pencere), `tahta-ajan sunucu ADRES` (parmak izi tutarsa yazar)
  ayar.py       yapılandırma, varsayılan tahta paleti, logonun servis tarafında saklanması, adres doğrulama/sırası
  baglanti.py   sunucu istemcisi (Istemci): HTTPS, sertifika zinciri yerine parmak izi denetimi (tutmazsa tek bayt gitmez)
  otomatik_giris.py  LightDM otomatik girişi (0.22.0; işletim sistemine dokunan ÜÇÜNCÜ dosya, hepsi `kok` alır):
                okunan_dosyalar (LightDM sırası: /usr/share → /etc/xdg → /etc conf.d → lightdm.conf), etkin_ayar (seat0;
                özel koltuk > [Seat:*]/[SeatDefaults]; boş değer kapatır), durum (sınıf, bizim, ezilmis; ad/yol yok),
                uygula (HESAPLAR, uid ≥ 1000, atomik O_EXCL|O_NOFOLLOW yazım, yalnız imzalı kendi dosyasını siler,
                lightdm YENİDEN BAŞLATILMAZ); servis.py `_otomatik_giris_isle` (istek değişince ya da 600 sn'de bir),
                `_otomatik_giris_durumu` (600 sn bellek); prerm remove/purge'de imzalı dosya silinir
  sistem.py     işletim sistemine dokunan HER ŞEY (yeni platform = bu dosya); ortak_oturum, temizlik
                sürecini oturum sahibinin kimliğiyle başlatma (tarayici_temizligi, pencereleri_kapat);
                USB (0.11.0): BaglamaIzleyici (mountinfo poll), cikarilabilir_baglamalar, anahtar_oku, udisks_calisiyor
  temizlik.py   oturum temizliğinin işletim sistemi işleri (ikinci dosya; ayrı süreçte çalışır,
                `python3 -m tahta_ajan.temizlik tarayici|pencereler`): beyaz liste, yol/bağ koruması,
                tarayıcı süreçleri, X11 _NET_CLOSE_WINDOW (ctypes libX11), ad içermeyen rapor
  tani.py       saha tanılaması (denetim listesi)
packaging/windows/   PyInstaller tanımı, Inno Setup betiği (hizmet kaydı, taşıma, icacls), build.ps1, giris.py;
                0.21.0: .spec datas'ta durum-*.ico + tahta-kontrol.ico, hiddenimports'ta tepsi/win32gui/win32con;
                .iss "durumsimgesi" görevi (işaretli) → `{commonstartup}\Tahta Kontrol durum simgesi` (`pencere --gizli`)
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
   kullanıcı kararı 18.11.2026). Bu istisna yalnız PIN ya da USB anahtarla (0.21.0'dan beri sınıf başkanı
   anahtarı dahil; kullanıcı kararı 21.11.2026, kural 37) açılan ders yoklaması listesi içindir; sınav ekranları ve kalabalık listeleri (kural 17, `maske.kalabalik` + `no_son`) için "ad ve
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
   belirlenmeden otomatik yedek alınmaz (Bugün › Sizi bekleyenler uyarır). Geri yükleme yalnız 127.0.0.1'den ve yöneticiyle
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
   Hizmet (SYSTEM'e çevrilmez). Kurulu pencere sunucu açmaz; SUNUCU açan başlangıç kısayolu geri getirilmez.
   İstisna (kullanıcı kararı 21.11.2026, 0.21.0; tasarım §15.6): kurucunun işaretli gelen "durumsimgesi" görevi
   `{commonstartup}\Tahta Kontrol durum simgesi.lnk` → `TahtaKontrol.exe pencere --gizli` kurar (seçilmezse
   `[InstallDelete]` siler). Bu kısayol YALNIZ bildirim alanı simgesini açar, sunucu AÇMAZ; eski `Tahta Kontrol.lnk`
   silinmeye devam eder; kurucu testi başlangıçta yalnız bu satıra izin verir. Durum uygulaması `kip_sec`'e her
   zaman `paketli=True` verir, sunucu yalnız `_gelistirme_penceresi`'nde içe aktarılır (`test_tepsi.py`). Eski
   veri yalnız KOPYALANIR (kaynak silinmez); hedefte veri varsa taşınmaz; seçim belirsizse ya da kopya
   bozuksa `TASIMA-BEKLIYOR.txt` yazılır ve hizmet açılmaz — bu korumayı "kolaylık" için kaldırma
   (yeni sertifika = bütün tahtalar kopar, kural 4). Taşıma kodları `.iss` ile `tasima.py`'de aynıdır
   (`test_kurucu_tasima_kodlari_python_ile_ayni`). `hizmet.py` ve `tepsi.py` modül düzeyinde pywin32 içe aktarmaz.

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
   0.21.0: üç anahtar türü vardır — idare (`kullanici`), öğretmen (`ogretmen`), şube (`sube`, sınıf başkanı; kural 37).
   Bu kuralın hepsi şube anahtarı için de geçerlidir; dosya biçimi ve ajan aynıdır (tür dosyada yoktur, ajan
   bilinmeyen türü öğretmen sayar). Şube anahtarının tahtadaki etiketi "Sınıf başkanı · <şube>"dir; panel etiketi
   tahtaya inmez. Başkan ayarı kapalıyken tanıma da işlem kaydına yazılmaz ve geçersiz sayacını tüketmez.

30. **e-Okul raporunda öğretmen adı hiçbir yere girmez** (0.12.0; `docs/tasarim.md` §12.4). Hücreden yalnız
   "dolu mu" alınır; eşleme ipucu yalnız iki satırlı hücrenin İLK satırıdır (ders adı), blok başına en çok 3,
   yalnız önizleme kaydında durur. Tek satırlı hücreden ipucu almayı "kolaylık" için açma. Raporda şube adı
   yoktur: şube eşlemesi zorunlu adımdır, aynı şube iki bloğa atanamaz. Gerçek rapor ve PDF'i depoya,
   teste, belgeye girmez; testler uydurma matrisle (`tests/test_eokul_program.py`) yazılır.
   Bu kural derslik aktarımı (`eokul_program.py`, `/program/aktar/eokul`) içindir ve DEĞİŞMEDİ. İstisna
   (17.11.2026 kararı, 0.13.0): ayrı `/ogretmen-programi` yolu aynı raporun öğretmen satırını okur; ham ad
   yalnız önizleme belleğinde durur, kalıcı kayda mevcut öğretmen kimliği yazılır (kural 31). Ad işlem
   kaydına, tahtaya, ajana girmez; öğretmen kaydı kendiliğinden oluşturulmaz. İkinci istisna (kullanıcı kararı
   21.11.2026, 0.21.0): toplu öğretmen yüklemesi aSc XML'den ve e-Okul OOK01001R1'den yalnız ad ve soyad okur
   (kural 38). Bu AYRI bir okuyucu ve ayrı sayfadır. Derslik sihirbazı (`program_aktar.ASC_ATLA`,
   `eokul_program.py`) öğretmen ve ders adını yine OKUMAZ.

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
   Bugün'de (`bugun.bekleyenler`, `yeni_surum` satırı) yalnız yöneticiye çıkar. Ayar (`guncelleme_denetimi`, varsayılan açık) kapalıyken HİÇ istek çıkmaz
   ("Şimdi denetle" dahil). Günde en çok bir kez; başarısız deneme de günlük hakkı tüketir; başarısızlık
   sessizdir (Bugün'de satır ve hata yok, yalnız Ayarlar'da "ulaşılamadı"). Ağ çağrısı olay döngüsünde, `vt.KILIT`
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
   ve saat yalnız ÖN SEÇİMDİR: hiçbir şube ya da ders düğmesi programa göre kapatılmaz. Tek istisna sınıf başkanı
   anahtarıdır (kullanıcı kararı 21.11.2026, 0.21.0; kural 37): onda şube, tahta ve ders saati kısıtları sunucuda
   uygulanır. Öğretmen, idare ve panel yolları değişmedi; istisnayı başka yola genişletme.
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

36. **Arama dizini kişi verisi taşımaz; aranan sözcük hiçbir yere yazılmaz** (0.20.0; `docs/tasarim.md` §11.1,
   `arama.py`). Dizine ve sonuçlara öğrenci adı/okul no, öğretmen adı/kodu, panel kullanıcı adı, USB anahtar etiketi,
   mazeret ve yoklama kaydı, duyuru başlığı/metni, acil şablonu, arıza açıklaması, sınav adı/listesi, ders başlığı ve
   öğretmen programı (soru 75), tahtanın ağ adresi, makine adı, demirbaş no, envanter notu, onay bekleyen tahta, grup
   açıklaması ve ayar DEĞERLERİ girmez; bu tablolara arama yolundan sorgu gitmez (öğrenci tablosundan yalnız
   `DISTINCT sube`). Girenler: sayfa/sekme/iş/süzgeç/ayar bölümü adları, onaylı tahtanın adı, dersliği, binası, katı,
   şubeleri, etkin şube adları, (yöneticiye) grup adı. Sorgu işlem kaydına, günlüğe, tabloya, çereze, tarayıcı
   deposuna, sayfa başlığına yazılmaz; "son aramalar" eklenmez; sunucunun erişim günlüğü (`access_log`) açılmaz.
   Sonuçsuz notu SABİTTİR: sorguya ya da kişi tablolarına bakılarak değişmez ("var ama gösterilmez" ipucu yok);
   yalnız role göre sayfa adı/adresi taşımayan bir satır eklenir. Rol süzmesi dizinin içindedir, eşleştirmeden ÖNCE
   yapılır ve girdinin rolü hedef sayfadan türer (`yer_coz`; elle "herkese açık" yazılmaz, sahipsiz hedef program
   açılışında patlar); idareci sonucunda yönetici sayfasının adı, adresi ve sayısı yoktur. Sonuç yalnız var olan bir
   GET sayfasına bağlantıdır: arama sonucundan komut, POST ya da indirme tetiklenmez. Sayfa, sekme ve ayar adları
   dizine elle yazılmaz (MENU, `bolum_serit.SERITLER`, `ayar_bolumleri`'nden türer). Testler uydurma kişi imleriyle
   (`tests/test_arama_sayfasi.py`) iki rolde tarar; yeni bir tablo ya da sütun dizine alınacaksa önce bu kural ve
   o test güncellenir, kullanıcıya sorulur.

37. **Sınıf başkanı anahtarı şubeye bağlıdır ve dar yetkidir** (0.21.0, kullanıcı kararı 21.11.2026;
   `docs/tasarim.md` §14.3).
   - **Kimlik:** anahtar `usb_anahtar.sahip_turu='sube'` + `sube` ile tanımlanır. Öğrenci kimliği ya da başkanın
     adı hiçbir tabloya yazılmaz; etiket alanında T.C. denetimi vardır. Yalnız yönetici üretir.
   - **Ayar:** `usb_anahtar.baskan` varsayılan KAPALIDIR. USB anahtar ve ders yoklaması kapalıyken başkan anahtarı
     çalışmaz. Ayar kapatılınca açık başkan oturumları anında düşer: belirteçler silinir ve `oturum_coz` ayarı da
     denetler.
   - **Kilit:** başkan anahtarı HİÇBİR ZAMAN kilit açmaz. `izinler` ona `kilit_ac` vermez; `/ajan/usb/kilit_ac`
     PIN sormadan 403 döner. PIN `pin_baskan` ile sorulur (varsayılan açık).
   - **Yazma koşulları** TEK yerdedir (`yoklama.baskan_denetle`) ve hem /liste hem /kaydet'te çalışır:
     - yalnız anahtarın şubesi (400);
     - yalnız o şubenin tahtası: `tahta.subeler` ya da derslik programında aynı ders saati (409);
     - yalnız `ders_kurali` penceresindeki ders; ders saati bulunamazsa 409, nedeni ayrı iletiyle (zil yok,
       bugün ders yok, devre belirsiz); pencere dışı 400;
     - **öğretmen önceliği:** o ders saatinde başka kaynaklı kayıt, şube defteri düzeltmesi ya da kayıt
       sayfasından düzeltme (`yoklama_iz.islem='duzelt'`) varsa yazamaz (409).
   - **Kural 33 istisnası:** bu, kural 33'ün bilinçli ve kullanıcı onaylı istisnasıdır. Öğretmen, idare ve panel
     yolları değişmez.
   - **Kayıt:** `kaynak='baskan'`, `kaydeden='baskan:<şube>'`. Birleşim kuralı (kural 34) değişmez; öğretmen
     sonra alırsa öğretmeninki geçerlidir. İşlem kaydına yalnız şube, ders saati, sayılar ve anahtar kimliği
     yazılır.
   - **Panel:** kayıt "sınıf başkanı" olarak ve sabit notla görünür ("deneme amaçlı yardımcı kayıttır;
     öğretmenin yoklamasının yerine geçmez"; K5).
   - **Yıl sonu:** bitiş tarihinden önce üretilmiş şube anahtarları silinir.
   - **Arama:** anahtar, etiket ve kimlik genel arama dizinine girmez (kural 36).
   - Yetkiyi genişletmek (kilit, başka şube, geçmiş ders, öğretmen kaydının üstüne yazma) kullanıcı kararıdır.

38. **Toplu öğretmen yüklemesi yalnız ad ve soyad okur; kimseyi pasifleştirmez, PIN üretmez** (0.21.0, kullanıcı
   kararı 21.11.2026; `ogretmen_aktar.py`, tasarım §14).
   - **aSc:** yalnız `teachers/teacher` öğesinin `firstname` ve `lastname` öznitelikleri okunur; biri boşsa
     `name` okunur. Kısa ad, cinsiyet, renk, e-posta, telefon ve ortak kimlik okunmaz.
   - **e-Okul OOK01001R1:** yalnız ADI SOYADI okunur. GÖREVİ yalnız önizlemede görünür ve saklanmaz. KADRO
     DURUMU ve BRANŞI okunmaz.
   - **T.C.:** T.C. sütunu hiçbir kaynakta okunmaz. Adında T.C. kimlik numarasına benzeyen değer bulunan satır
     atlanır.
   - **Dosya ve önizleme:** dosya diske yazılmaz. Önizleme bellekte 15 dk durur, tek kullanımlıktır, yalnız
     yöneticiye açıktır.
   - **Dokunulmayanlar:** dosyada olmayan öğretmene dokunulmaz. Pasif aynı ad yalnız satır başına açık onayla
     etkinleşir. Eklenen öğretmenin PIN'i yoktur (kural 19: PIN yalnız toplu PIN pusulasında).
   - **İz:** işlem kaydına yalnız sayılar yazılır.
   - **Kural 30:** bu yol kural 30'daki "öğretmen kaydı kendiliğinden oluşturulmaz" hükmünü değiştirmez. Satır
     başına onaylı önizlemeyle çalışır ve öğretmen programı aktarımından ayrıdır. Testler uydurma adla yazılır;
     gerçek personel listesi depoya girmez.

39. **Otomatik giriş durumdur; parola istemez; yalnız ortak öğretmen hesabıdır** (0.22.0, kullanıcı isteği
   27.11.2026; `docs/tasarim.md` §5.2).
   - **Parola:** etapadmin (ya da başka bir hesabın) parolası panele, sunucuya, ajana GİRMEZ; ayarı root ajan
     yazar. "Kolaylık" için parola alanı eklenmez (kural 5).
   - **Değerler:** `dokunma` (varsayılan; alan hiç gönderilmez, tahtadaki ayara dokunulmaz) · `ogretmen` · `kapali`
     (yalnız ilk satırı imzalı KENDİ dosyamız silinir). Alan yalnız `otomatik_giris` yeteneğini bildiren ajana gider.
   - **Hesap:** iki tarafta sabit liste `("ogretmen",)` (test eşler); etapadmin, root, uid < 1000 ve kişisel hesap
     hiçbir koşulda yazılmaz. Listeyi genişletmek kullanıcı kararıdır.
   - **Kilit koruması:** `ogretmen` yalnız kilit kodu tanımlı VE açılışta kilit açıkken kaydedilir
     (`otomatik_giris.engel`); sonradan bozulursa ayar kendiliğinden değişmez, Bugün yöneticiyi uyarır. Uyarı
     ayara DEĞİL `kilitsiz_risk`'e bakar: ayar "dokunma"ya alınsa da dosyası duran tahta (ajanın bildirdiği `bizim`
     + öğretmen) sayılır. Uyarıyı yeniden `ayar_al(b) == "ogretmen"` koşuluna indirgeme.
   - **Tahtada:** tek dosya `/etc/lightdm/lightdm.conf.d/50-tahta-otomatik-giris.conf` (elle deneme betiğiyle aynı ad
     ve içerik); atomik yazım, sembolik bağ ve düz olmayan dosya izlenmez; başka LightDM dosyasına dokunulmaz;
     lightdm yeniden başlatılmaz (ayar sonraki açılışta). Paket kaldırılınca imzalı dosya silinir.
   - **Rapor:** ajan durumunda yalnız hesap SINIFI (`etapadmin|ogretmen|ogrenci|kisisel`), `bizim`, `ezilmis`,
     `lightdm`, `hata`; hesap adı, dosya yolu ve içerik sunucuya gitmez.

## Bilinen tuzaklar

- **Otomatik giriş "dokunma"da alan GÖNDERİLMEZ (0.22.0):** ajan alanın yokluğunu "dokunma" sayar. `ajan_ayari`'na
  `"otomatik_giris": None` yazılırsa eski sözleşme bozulmaz ama ajan `None`'ı dict değil diye yok sayar; "kaldır"
  ise `{"hesap": None}`'dır. İkisini karıştırma: `None` gönderip "kaldırdım" sanma.
- **LightDM'in okuma sırası ve koltuk önceliği tek yerdedir (0.22.0):** `tahta_ajan/otomatik_giris.etkin_ayar`.
  Tanılama da (`tani._giris_ekrani`) bunu kullanır. `[Seat:seat0]` her zaman `[Seat:*]`'ın önüne geçer (dosya
  sırasından bağımsız); boş `autologin-user=` otomatik girişi kapatır. Yeni bir okuyucu yazma.
- **Otomatik giriş her `/ajan/bekle` yanıtında yeniden yazılmaz (0.22.0):** istek değişince ya da
  `OTOMATIK_GIRIS_YENILE_SN` (600) dolunca uygulanır; durum özeti de 600 sn bellektedir. Süreyi kısaltma: yanıt
  25 sn'de bir gelir ve her seferinde /etc'yi okumak/yazmak gereksizdir.

- **Deneme sunucusu bu bilgisayarda 8797/8798'de açılmayabilir (0.21.0):** Windows 8789–9188 kapı aralığını
  ayırmış. Bu yüzden 0.21.0 denemesi 18807'de yapıldı. Kapı "kullanımda" hatası verirse önce ayrılmış aralığa bak
  (`netsh int ipv4 show excludedportrange protocol=tcp`); başka süreç arama.
- **0.21.0'ın iki göçü ayrı öğedir ve sırası bağlayıcıdır:** önce aSc (`program_eslesme` aSc saat eşlemeleri
  silinir, `program_surum.tahta_json` eklenir), sonra başkan. Başkan göçünde de iç sıra bağlayıcıdır: foreign_keys
  açık olduğundan önce `usb_anahtar`'a başvuran `yoklama_belirtec` düşer, sonra `usb_anahtar` yeni CHECK ile
  yeniden kurulur, en son `yoklama_belirtec` yeniden kurulur; açık oturumlar `yb_eski` TEMP tablosuyla korunur
  (yükseltme anında tahtada süren yoklama kaybolmasın). İkisini tek öğede birleştirme, sırasını değiştirme.
- **Yıl sonu "Tümünü sil" başkan anahtarlarını da siler (0.21.0):** `yoklama.hepsini_sil` `sahip_turu='sube'`
  satırlarını aynı işlemde siler; şube anahtarının sahibi "şubede etkin öğrenci var mı" diye canlı hesaplandığı
  için silinmezse geçen yılın başkanı yeni yılın aynı adlı şubesinde çalışırdı. Öğretmen/idare anahtarı kalır.
- **aSc şube güncellemesi şubeyi eski tahtadan da kaldırır (0.21.0):** `program_aktar.sube_guncellemesi` önce
  şube → yeni ana tahta haritasını kurar; bu aktarımda eşlenen başka tahtanın eski şubelerinden yeni tahtası
  belli olanları çıkarır (aynı şube iki tahtada kalırsa başkanın oda kısıtı ve şube hedefli duyuru bozulur).
- **Göç testleri göçü içerikten bulur, sondan değil (0.21.0):** `"tahta_json" in g`, `"CREATE TABLE
  usb_anahtar_yeni"`, `"CREATE TABLE yoklama_gec"`. Yeni göç ekleyince `GOCLER[-1]`'in belli bir göç olduğunu
  varsayan test yazma. `test_yoklama_sozlesme` 0.14.0 göçünün yoklama tablolarına dokunan tek göç olduğunu
  denetler; başkan göçü `yoklama_belirtec`'e dokunur, `yoklama*` kayıt tablolarına dokunmaz.
- **aSc şube anahtarında `metin.katla` kullanma (0.21.0):** I ile İ'yi birleştirir; 9/İ satırlarına 9/I
  yazılıyordu. Anahtar `metin.sube_duzelt`'tir. Eski katlanmış hatırlanan anahtarlar ("9/i") eşleşmez ve yok
  sayılır.
- **aSc'de otomatik saat/devre eşlemesi hatırlanmaz, yalnız elle seçilen hatırlanır (0.21.0):** otomatik eşleme
  zil değişince bayat kalıyor ve devre grubu eşlemesini eziyordu. `eslesmeleri_yaz`'a otomatik `saat`/`devre`
  yazdırma. Hatırlanan saat değeri zilde karşılığı yoksa yok sayılır.
- **aSc devre bölmesinin eşikleri bilerek vardır (0.21.0):** az kartlı dosyada her sınıf tek saatte görünür ve
  "tek parçada" sayılır. Kapsama eşiği (`DEVRE_KAPSAMA`) bu yüzden vardır; düşürme. Başlangıç saati olmayan period
  `saatsiz`'a ayrılır. Erken `return` ile bütün dosyayı gruplamasız bırakma; öyle yapılınca zil önerisi de
  kalkıyordu.
- **Şube güncellemesi sürümle saklanır (0.21.0):** eski ve yeni değerler `program_surum.tahta_json`'dadır.
  Geri yükleme yalnız o onaydan beri değişmemiş tahtada geri yazar. Tahta tablosuna sürümsüz UPDATE yazan yeni
  bir onay adımı ekleme. Onaylanabilir olmak programın değişeceği anlamına gelmez: yalnız şube güncellemesi için
  de onay açılır; `program_degisir` yanlışsa ve kutu işaretsizse `aktar_onayla` reddeder.
- **Rakamla derslik eşleşmesi öneridir (0.21.0):** durumu "rakam"dır ve hatırlanmaz. Addan yalnız tamamı
  numara olan ad aday olur (`_RAKAMLI_AD`). "Tahta 12" adını aday sayma: varsayılan ad her tahtayı aday yapar.
- **Tahta numarası = `tahta.id` (0.21.0):** ayrı bir numara sütunu açılmaz; numara sıfırla doldurulmaz,
  yeniden sıralanmaz, kaldırılan tahtanın numarası yeniden kullanılmaz. Kurulum çıktısı ve panel aynı değeri
  yazar. Tahta adı gösteren yeni bir yer aynı adlıları ayırmak için " · No <id>" ekini kullanır. Canlı tazeleme
  (`panel.js`) adı yazmaz; numara taşıyan öğeye JS ile metin yazılırsa numara da yazılmalı.
- **Yeni kayıtta ad makine adından alınmaz (0.21.0):** ETAP'ta bütün tahtaların makine adı aynıdır ("etap").
  `ad = makine_adi` geri getirilmez. Aynı ad reddedilmez, yalnız uyarılır. Toplu adlandırma formu kimlik
  taşımaz; liste sunucuda yeniden hesaplanır ki bayat sayfa başka tahtayı adlandırmasın. Toplu adlandırma
  yalnız `adlandirilabilir_mi` olan, yani adını kurulumdan almış tahtaya dokunur; elle verilmiş "Tahta 12"
  ezilmez.
- **Başkan oturumunda öğretmen ve kullanıcı YOKTUR (0.21.0):** `yoklama_belirtec`te ikisi de boştur, yalnız
  `anahtar_id` doludur; `oturum["tur"]=='baskan'`. Oturum türüne göre dallanan yeni kod üç dalı da ele alır
  (`oturum_kaydedeni`, `oturum_kaynagi`). Kayıt `kaynak='baskan'` ile yazılır. 'tahta' yazılırsa idare USB
  kaydıyla aynı satıra düşer (UNIQUE `IFNULL(ogretmen_id,0), kaynak`).
- **`yoklama.kaynak` üç değerlidir (0.21.0):** `alan_etiketi`, `kayit_ayrintisi` ve şablonlardaki
  `kaynak_turu == 'tahta'` koşulları 'baskan'ı da ele almalı. "Panel değilse tahta" varsayımı yanlıştır.
- **Başkan kutuları USB anahtar formundadır ve nöbetçi ister (0.21.0):** `ua_baskan` ve `ua_pin_baskan` öbür
  dört kutuyla aynı formdadır (0.16.0 onay kutusu tuzağı). `ua_baskan_formu` yoksa (eski sekmeden gelen form)
  başkan kutuları önceki değerinde kalır. Forma kutu eklerken ya da çıkarırken nöbetçiyi ve
  `test_her_bolum_tek_formda`'yı da güncelle.
- **Başkan anahtarının yıl sonu silmesi `olusturma < sınır + 1 gün` koşuluna bağlıdır (0.21.0):** imha saatte bir
  çalışır ve bitiş tarihi güncellenene kadar aynı sınırı kullanır. Koşul kaldırılırsa yeni yılda üretilen
  anahtarlar her saat silinir.
- **Öğretmen başlık eşlemesi sözcük sınırıyla yapılır (0.21.0):** öğrenci eşlemesi alt dize arar. Öğretmende de
  alt dize aransaydı "ad" eş anlamlısı "KADRO DURUMU"nu ad sütunu sayardı. `eokul.baslik_esle` parametresizken
  öğrenci davranışıdır; varsayılanını değiştirme. e-Okul personel raporunda sütun yeri dosyadan dosyaya değişir;
  sütun yeri sabitlenmez, başlıktan bulunur. Altbilgi satırları görevi boş olduğu için atlanır.
- **Önizleme deposu üç türle ortaktır (0.21.0):** öğretmen kaydı `{"tur": "ogretmen_aktar", "ayristirma"}`
  taşır ve "satirlar" anahtarı TAŞIMAZ; öğrenci ucu `"satirlar" in` diye bakar. Anahtar adı değişirse öğretmen
  belirteci öğrenci aktarımına geçebilir (`test_yonetici_belirteci_baska_onizleme_turunde_gecmez`).
  Önizlemedeki kodlar "öngörülen"dir: uygulama planı işlem içinde yeniden hesaplar.
- **Simge penceresi `HWND_MESSAGE` olmaz (0.21.0):** ileti penceresi TaskbarCreated yayınını almaz; Explorer
  yeniden başlayınca simge geri gelmez. Görünmeyen üst düzey pencere kullanılır; `FindWindow` (ikinci açılış)
  da buna bağlıdır.
- **tkinter yalnız ana iş parçacığında çağrılır (0.21.0):** simge iş parçacığı ve izleyici yalnız `queue`'ya
  yazar. `messagebox`'ı simge iş parçacığından açma. Simgeye başka iş parçacığından yalnız `Tepsi.guncelle`,
  `balon` ve `kapat` (PostMessage) ile dokunulur.
- **Simge katmanında üç Win32 tuzağı (0.21.0):**
  - Aynı süreçte ikinci `Tepsi` sınıfı yeniden kaydeder. Kapanışta `UnregisterClass` gerekir; yoksa 1410 hatası
    çıkar ve ileti haritası eski nesneye bağlı kalır.
  - Simge penceresine gelen WM_CLOSE "Çık"tır. Kaldırılırsa DefWindowProc pencereyi yok eder; süreç görünmez
    kalıp tek örnek mutex'ini tutar ve masaüstü kısayolu bir daha pencere açamaz.
  - Tek bir `Shell_NotifyIcon` hatası simgenin yok olduğu anlamına gelmez (Explorer meşgulken zaman aşımı).
    `_ekle` ADD düşerse MODIFY dener. `_eklendi`'yi tek hatada kalıcı False yapma.
- **sc okunamadı ≠ hizmet kurulu değil (0.21.0):** `pencere_kipi` iki kaynak da okunamazsa `okunamadi` verir;
  "kurucuyu yeniden çalıştırın" yalnız sc 1060'ta denir. Zorla öldürülen (`taskkill /F`) sürecin simgesi fare
  üstüne gelene kadar kalır; bu beklenen davranıştır. Windows 11 yeni simgeyi taşma alanına koyar; program
  sabitlemeyi zorlamaz.
- **Arama girdisi eklemek = `arama.SIK_ISLER`'e bir öğe (0.20.0):** yalnız var olan bir GET sayfasına giden kısa yol
  ve eş anlamlıları. Sayfa, sekme, süzgeç ya da ayar adı `arama.py`'ye yazılmaz (tanımından türer; testi kaynakta düz
  metin arar). Rol yazılmaz, hedeften türer; açık `rol` yalnız daraltır. POST isteyen iş, indirme adresi, kişi/kurum
  adı, ağ adresi girmez. Eş anlamlı en az dört harfliyse ekli biçimleri de bulur; daha kısa kök ek almaz (aşağıda).
- **Menü öğesi ya da sekme silinir/taşınırsa program açılmayabilir (0.20.0):** dizin `web.py` içe aktarılırken kurulur
  ve hedefi hiçbir menü öğesine/şeride bağlanamayan `SIK_ISLER`/`BASKA_YERDE` girdisi `ValueError` verir (bilerek:
  sahipsiz girdi sessizce "herkese açık" olmasın). Sekme yolu değişince o yola giden kısa yolları da güncelle;
  `try/except` ile yutma, varsayılan rol verme.
- **Arama yolundan kişi tablosuna sorgu atılmaz; sonuçsuz notu sorguya göre değiştirilmez (0.20.0, kural 36):**
  "öğrenci bulundu ama gösterilemiyor" türü yardımsever not var/yok kâhinidir. Sonuçsuz sayfaya sonuç satırı (ör. sık
  işler listesi) de çizilmez; gizlilik testi sonuçsuz sayfada hiç satır olmamasına bağlıdır, not yalnız `/ara`'ya
  bağlantı verir.
- **Aranan sözcük hiçbir yere yazılmaz (0.20.0, kural 36):** `ara_sayfasi`/`api_ara`'ya `vt.kayit…` ya da `gunluk`
  çağrısı, `sunucu.py`'ye `access_log`, `ara.html` başlığına sorgu, `panel.js`'e `localStorage`/çerez eklenmez (testi
  hepsini arar). Sorgudan yazdırılamayan karakterler `sorgu_duzelt`'te atılır; sayfaya yankılanan yalnız odur.
- **Eşleştirme yalnız sunucudadır (0.20.0):** `aramaOneriKur` yalnız `/api/ara` yanıtını çizer; dizin, kural ya da
  harf haritası `panel.js`'e kopyalanmaz, tahta/şube adları sayfa HTML'ine gömülmez. (Ayarlar içi aramanın
  `ayarKatla`'sı 0.16.0'dan kalan AYRI ve değişmeyen koddur; genel arama onu kullanmaz.) Öneri metni `textContent`
  ile yazılır; `yol` "/" ile başlamıyorsa ya da ikinci karakteri "/" veya "\" ise bağlanmaz.
- **Ekli sözcük eşleşmesi en alt kademedir ve kök en az dört harftir (0.20.0):** `_ekli_uyar` "pusulası" → "pusula"yı
  bulur; eşiği (`EK_KOK_EN_KISA`) düşürmek "kod" → "kodu…" gürültüsü üretir, kademeyi yükseltmek doğru başlık
  eşleşmesinin önüne geçer. Artan kısım yalnız harf olmalıdır ("idareci1", "tahta-12" ek sayılmaz: kullanıcı adı
  ve numara kalıpları eşleşmesin).
- **Şube girdisinin samanlığı YALNIZ şube adıdır (0.20.0):** başlık "9/A şube defteri"dir ama `_girdi(…, yalniz=şube)`
  ile kurulur; başlıktan kurulursa "10/d" sorgusu "defteri" sözcüğü yüzünden bütün şubeleri getirir. Süzgeç girdisinde
  başlık öneki etiketten sayılır (`bas=`): ad "Tahtalar: Çevrimdışı" kalıbıdır, "cev" yine ilk sırada çıkar.
- **`/` kısayolu çekmece kipinde sayfadan AYIRMAZ (0.20.0):** ilk yazımda dar ekranda `location.assign("/ara")`
  yapıyordu; yarım doldurulmuş duyuru formu gidiyordu (inceleme bulgusu). Şimdi `kabukCekmeceAc` ile çekmeceyi açıp
  kutuya odaklar. Kısayol metin alanında, `select`'te, `contenteditable`'da, açık `dialog`'da ve değiştirici tuşla
  tetiklenmez; yeni bir sayfa kısayolu (ör. şube defteri fırçası) `/` kullanmaz.
- **Öneri listesi açıkken Esc yalnız listeyi kapatır (0.20.0):** `stopPropagation` olmazsa aynı tuş çekmeceyi de
  kapatır. Yazınca etkin seçenek sıfırlanır: Enter yalnız kutuda o an yazılı olanın önerisine gider (eski yanıtın
  seçeneğine değil); seçim yoksa form `/ara`'ya gider.
- **Combobox öznitelikleri şablona yazılmaz (0.20.0):** `role="combobox"`, `aria-expanded`, `aria-controls` JS'sizken
  olmayan bir listeyi duyurur; `aramaOneriKur` ekler. İki arama alanı (yan menü, `/ara` sayfası) ayrı erişilebilir ad
  ve ayrı liste kimliği taşır (`genel-oneri`, `sayfa-oneri`), kod TEKTİR.
- **Yan menü ızgarası beş satırdır; arama satırı sayılır (0.20.0):** `.yan-menu { grid-template-rows: auto auto auto
  minmax(0, 1fr) auto }`. Menüye yeni sabit satır eklenirse şablon satırı da eklenir, yoksa gezinme esnemez ve Çıkış
  ekran dışına düşer. Arama satırı gezinmenin dikey payını bitirdi: kısa pencerede (≤ 40rem, fare) menü satırı 2rem'e
  iner ki yöneticinin on öğesi 1366x625 ve 1280x585'te kaydırmasız kalsın; ölçmeden büyütme.
- **Öneri listesi menünün İÇİNDE mutlak konumludur ve yüksekliği sınırlıdır (0.20.0):** `.yan-menu` taşmayı kırpar;
  `max-block-size` kaldırılırsa liste alt kenarda kesilir. "Tüm sonuçlar" satırı kayan listede yapışkandır
  (dokunmatikte sekiz öneri + o satır sığmaz). Listeyi `body`'ye taşıyan açılır katman yazma (çekmece `inert`
  kapsamı ve odak tuzağı bozulur).
- **Üst çubukta yer kalmadı (0.20.0):** Menü · kimlik · Ara · Acil; ≤ 26rem'de okul adı görsel olarak gizlidir (logo
  ve erişilebilir ad durur). Üst çubuğa yeni düğme 390 px'te taşma demektir (alt çubuk da genişler, 0.15.0 tuzağı).
- **`/ara` sayfasında hiçbir menü öğesi etkin değildir (0.20.0):** arama menü öğesi değildir;
  `test_her_sayfada_tek_etkin_oge` bu yol için TAM 0 bekler. `/ara`'yı bir öğenin `esler`'ine ekleme, üst çubuk
  düğmesine `aria-current` verme.
- **Arama girdisinde dokunmatikte yazı 16 px'tir (0.20.0):** daha küçük yazılı girdiye odaklanınca telefon tarayıcısı
  sayfayı yakınlaştırır; `(pointer: coarse)` kuralını kaldırma.
- **Sunum/deneme görüntüsünde `/tahtalar` onay bekleyen bandı ağ adresi gösterir (0.20.0, deneme betikleri):** deneme
  sunucusunda bu 127.0.0.1'dir, yine de paylaşılacak görüntü için bandı olmayan bir sayfa seç.
- **Sekme eklemek/taşımak = `bolum_serit.SERITLER`'de bir satır (0.19.0):** şablona ya da `web.py`'ye ikinci sekme
  listesi yazılmaz; çizim tek makrodur (`_serit.html::ciz`). Makronun çıktı biçimi testlerle bağlıdır: `href`'ten
  HEMEN sonra `aria-current` gelir, araya öznitelik girmez. Şerit yalnız görünümdür; yetki uçtadır. Yeni adres
  açılmaz: sekme gerekiyorsa var olan sayfa `?sekme=` alır.
- **Etkin sekmeyi şablon verir, istek yolundan çıkarılmaz (0.19.0):** aynı şablon başka uçta yeniden çizilir
  (`POST /duyurular` 400, `POST /acil/baslat` 400, `POST /program/gecmis/{id}/geri-yukle` onay adımı); yoldan
  çıkarılsaydı hata çiziminde yanlış sekme (ya da hiçbiri) işaretlenirdi.
- **Program şeridini çizen HER sayfa `serit` (program_is.program_ozeti) bağlamını verir (0.19.0):**
  `_program_bas.html` durum şeridini ve Uyarılar rozetini ondan çizer; `serit` vermeyen sayfa 500 verir. POST'un
  yeniden çizimleri de (geri yükleme onayı, içe aktarma 422, öğretmen programı önizleme) verir.
- **Bölüm şeridi sarar; kaydırma kabı yapılmaz, yapıştırılmaz (0.19.0):** `.bolum-serit`'e `overflow-x` ya da
  `nowrap` verilirse telefonda gizli sekme fark edilmez; taşarsa sayfa 390 px'ten genişler ve alt çubuk da taşar
  (0.15.0 tuzağı). Ayraç kümenin (`.sekme-kume`) İLK çocuğudur: geniş ekranda satır başına düşen kümenin ayracı
  kırpılır, ≤ 640 px'te ayraç satır başıdır. Telefonda yöneticide Program 4, Yoklama 3 satırdır (bilinen sınır,
  soru 89); dokuzuncudan sonra sekme eklemeden önce 390 px'te ölç.
- **Duyuru formunda `zaman` radyolarından biri HER ZAMAN işaretli çizilir (0.19.0):** sunucu eksik `zaman`'ı "hemen"
  sayar; işaretsiz çizilen grup JS'siz gönderimde planlanmak istenen duyuruyu o an yayımlar. Şablondaki `zaman_`
  hesabı (yeni duyuruda `hemen`, plan sayfasında `bir_kez`) kaldırılmaz.
- **Duyurunun gönder düğmesi düz `submit`'tir; zaman alanlarına `required` verilmez (0.19.0):** `data-onay` ya da
  `type="button"` JS'siz gönderimi keser (0.16.0'daki onaylı düğme kalıbı burada YANLIŞTIR). JS'siz üç zaman bloğu
  da görünür: `bitis`'e `required` konursa "Hemen" gönderimi boş bitişe takılır. Seçili olmayan zamanın dolu alanları
  sunucuda yok sayılır (soru 83; `<noscript>` notu söyler). Forma `data-kirli-izle` konmaz.
- **Gönder çubuğunun özeti bayat kalamaz (0.19.0):** onay penceresinin yerine geçen tek önlemdir (soru 82). Özet
  `hidden` çizilir ve yalnız `panel.js` açar (JS'siz seçim değişince güncellenemezdi; düğme de JS'sizken yansızdır:
  "Yayımla ya da planı kaydet"). Hedef değişince sayı HEMEN "hesaplanıyor…" olur, ağ hatasında "alınamadı"; eski
  sayı ekranda bırakılmaz. Zaman kısmı seçilen tarih/saat/günleri yazar, eksik alanı açıkça söyler.
- **Duyuru formunun gün düğmeleri tarayıcı saatini kullanmaz (0.19.0):** "Bugün"/"Yarın" tarihi formun `data-bugun`
  özniteliğinden (sunucunun günü) hesaplanır; `new Date()` gece yarısına yakın ve saati yanlış bilgisayarda yanlış
  güne plan yazar.
- **Kapalı `<details>` içindeki işaretli kutu da gönderilir (0.19.0):** duyuru formunda bina/kat/düzey/devre ve
  "tek tek seç" açılırları, içinde seçim varsa (hata çizimi, kopya, plan, 0.17.0 ön seçimi) AÇIK çizilir; yoksa
  görünmeyen seçim hedefi sessizce daraltır ya da genişletir.
- **Uzun formda doğrulama iletisi ilgili bölümde de çizilir (0.19.0):** `panel_duyuru.hata_yeri` → `icerik | kime |
  zaman`; ikinci kopya `role="alert"` taşımaz (ekran okuyucu iki kez okumasın). Yeni doğrulama iletisi eklenirse
  `hata_yeri`'nin öneki/`yer` eşlemesi de güncellenir (eşleşmeyen ileti "zaman" bölümüne düşer).
- **Acil'in süren yayın kutusu iki sekmede AYNI kimliklerle çizilir (0.19.0):** `_acil_aktif.html` (`#acil-aktif`,
  `#acil-teslim`, `#acil-kalan`) `panel.js`'in canlı sayacına bağlıdır; "Geçmiş ve raporlar"da kutu çizilmezse süren
  yayın o sekmede görünmez kalır ve "Yayını bitir…" bulunamaz. Dönüş adresi sekmeyi taşır (`acil_donus`).
- **Bekleyen iş eklemek = `bugun.py`'de bir üretici + iki rol için test (0.18.0):** uyarıyı şablona ya da başka
  sayfaya bant olarak yazma; `bekleyenler` tek listedir ve menü rozeti, satır sayısı, `/api/durum.bekleyen_is`
  ondan çıkar. Rol süzmesi üreticinin İÇİNDEDİR: idareci satırının `yol`'u `/ayarlar…`, `/yedekler…`, `/ekle`,
  `?sekme=bilgiler` olamaz (şablonda rol koşulu yoktur; `test_bekleyenler_idarecide_yonetici_satiri_ve_adresi_yok`).
  Koşul var olan işlevden okunur (kopya koşul yazılmaz). Menüde rozet isteyen satır `rozet` taşır ve üreticisi
  `yalniz_rozet` dalına da eklenir (her sayfada çalışır: az sorgu). Kurulum listesinde kendi satırı olan madde
  `KURULUMDA_AYRI_SATIR`'a girer (çift sayım).
- **Bugün'e ham hata metni, ad ve yol yazılmaz (0.18.0):** yedek hatasının istisna metni sunucu klasörünü ve
  ikinci kopya yolunu taşır (inceleme bulgusu; 0.17.0 bandı basıyordu). Satır yalnız "alınamadı" der, ayrıntı
  /yedekler'dedir. Aynı kural her yeni satır için: arıza açıklaması/kategorisi, duyuru metni, bekleyen tahtanın
  adı/adresi, öğrenci/öğretmen adı, mazeret türü, ders başlığı Bugün'e ve `/api/durum.bekleyen_is`'e girmez;
  `imza` yalnız `anahtar:sayı`'dır. Yoklama kutusu yalnız sayıdır; "yoklama alınmadı" uyarısı ya da alınmayan
  ders listesi eklenmez (K5, kural 13, 24, 35).
- **"Hepsini kilitle…" formunda gönder düğmesi, metin alanı ve `tur` alanı yoktur (0.18.0):** `tur=kilitle`
  yalnız onay penceresinin "evet" düğmesiyle eklenir; biri eklenirse form JS'siz ya da Enter'la bütün okula
  kilit yollar. Formun sayıları (`data-hedef`, `data-sinavda`, `data-cevrimdisi`) yalnız onay metni içindir;
  sunucu hedefi kendi sayar. `KAPSAM_HEPSI_TURLERI` yalnız `kilitle` kalır ("hepsinin kilidini aç" yapılmadı).
  V2 yalnız `kapsam` dalındadır: `tek` ve işaretli liste sınavdaki tahtaya eskisi gibi gider. Acil sürerken düğme
  çizilmez ve `bugunKur` sayfa açıkken de kapatır; sunucu ucu acilde REDDETMEZ (ayrı karar, §17 soru 81).
- **Bugün'ün yükleme anındaki imzası ile ilk `/api/durum` yanıtı aynı olmalı (0.18.0):** farklıysa "Bekleyen
  işler değişti. Sayfayı yenile" bandı sayfa açılır açılmaz çıkar. Bu yüzden Bugün `kurulum` satırını her
  yüklemede taze hesaplar ve belleği yeniler (`kurulum_onbellegi(…, taze=…)`), güncel olmayan tahta sayısı da
  iki yoldan (`tahta_sayilari` ve tek COUNT) aynı çıkmalıdır (testi var). Bekleyen iş metni JS ile yazılmaz
  (metin sunucudadır); canlı tazeleme yalnız `data-alan`/`data-sayi`/çip kancalarına yazar ve kuralı yeniden
  hesaplamaz (0.17.0 tuzağının devamı).
- **Durum kutuları sayfada İKİ kez çizilir (0.18.0):** telefonda ilk ekranda kalsın diye "Şu an"ın altında
  (`#bugun-ozet-kisa`, yalnız ≤ 640 px görünür) ve karttaki (`#bugun-ozet`); ikisi aynı makrodur ve `bugunKur`
  ikisine de yazar. Kutuya öznitelik ya da kanca eklenince makro değişir, tek kopya değil; testte kutu sayarken
  ikisini hesaba kat.
- **`/api/durum` 4 sn'de bir, açık sekme başına çalışır; içine pahalı üretici koyma (0.18.0):** bu bilgisayarın
  adres listesi 60 sn, `kurulum` satırı 30 sn süreç belleğindedir. Adres belleği işlev kimliğine bağlıdır
  (testler `guvenlik.yerel_ipler`'i değiştirir; kimlik değişince bellek geçersizdir). Yoklama ve duyuru özeti
  `/api/durum`'a girmez (yalnız sayfa yüklenirken); Bugün'ün sorgu sayısı tahta ve öğrenci sayısından
  bağımsızdır (`test_bugun_sorgu_sayisi_tahta_ve_ogrenci_sayisindan_bagimsiz`): `yoklama.gunluk_gorunum`
  (şube başına sorgu) Bugün'den çağrılmaz.
- **Başsız Edge ekran görüntüsünden sonra sayfayı "gizli" bildirebilir (0.18.0, deneme betikleri):** canlı
  yoklama sekme gizliyken durur; tarayıcı denemesinde canlı tazeleme "çalışmıyor" görünür. CDP'de
  `Emulation.setFocusEmulationEnabled` açık tutulur.
- **Liste formunun ilk gönder düğmesi nöbetçidir; kaldırma, devre dışı yapma, önüne gönder düğmesi koyma
  (0.17.0):** seçim kutusu odaktayken Enter örtük gönderim yapar ve tarayıcı formun ağaç sırasındaki ilk ETKİN
  gönder düğmesini tıklar; nöbetçi olmasa bu ilk satırın `tek=` düğmesidir (seçilmemiş tahtaya komut). Devre dışı
  nöbetçi işe yaramaz: Chromium onu atlayıp sıradaki etkin düğmeyi tıklar (başsız Edge'de ölçüldü, JS kapalıyken
  ilk satıra `kilit_ac` gitti). `nobetci` alanını gören `/islem` hiçbir komut yazmaz (`tahta_liste.islem_hedefi`,
  ilk dal). `panel.js`'in Enter'ı yutması ikinci kattır, tek başına yetmez (JS'siz). Liste formuna metin alanı
  da eklenmez.
- **`/islem` dalları arasında düşme yoktur (0.17.0):** sıra nöbetçi → `tek` → `kapsam` → işaretli liste. `tek`
  bozuksa "bari işaretlilere gönder" diye listeye düşülmez; hiçbir komut gitmez. `tek` dalında formdaki `tur` ve
  `tahta` okunmaz. `tek` biçimi tam eşleşme ister (`fullmatch`; "kilitle:1\n", "kilitle:01", "kilitle:0" reddedilir).
  `kapsam=hepsi` yalnız `kilitle`'ye açıktır ve başka hedefle birlikte reddedilir; yıkıcı komuta açma.
- **`data-tek` taşıyan onay tetiği `tur` ile gönderilmez (0.17.0):** satır menüsündeki "Kapat…" yalnız kendi
  tahtasınındır; `onayKur` bu dalda seçili satırlara bakmaz ve onay düğmesi `name="tek"` olur. Tetikte `data-tek`
  varken herhangi bir hata yolunda `tur` + işaretli listeye dönmek, onaylanan tek tahta yerine seçili bütün
  tahtaları kapatır.
- **Durum kuralı yalnız `tahta_liste.durum_ozeti`'ndedir (0.17.0):** şablon ve `/api/durum` aynı `liste`
  sözlüğünü kullanır; `panel.js`'e rozet, düğme ya da pasiflik hesabı YAZILMAZ (0.16.0'daki `durumHesapla`
  silindi; kuralın iki kopyası yanlış düğme demektir, `?durum=` süzgeci de JS'siz çalışmak zorunda). Rozet
  metinleri testlerle ve `/api/durum` sözleşmesiyle bağlıdır.
- **Canlı tazeleme birincil düğmeyi yalnız düğmenin HÜCRESİ boştayken yazar (0.17.0):** koruma satırın
  bütününe yayılırsa seçim kutusundaki odak düğmeyi dondurur (satır bayat düğmeyle kalır); hiç olmazsa düğme
  parmağın altında "Kilitle"den "Kilidi aç"a döner. Değişen düğme 700 ms tıklama almaz; açık menü yeniden çizilmez.
- **Tahta listesinin kabı kaydırma kabı değildir (0.17.0):** `.tablo-kap` (`overflow`, `max-block-size`) listede
  kullanılmaz; satır menüsü kırpılır ve çift dikey kaydırma olur. Menünün yönü görüntü alanına göre seçilir (üst
  çubuk, telefonda alt çubuk ve seçim çubuğu düşülerek); sığmazsa sayfa kayar, o da olmazsa menü kendi içinde kayar.
- **Satır komutunun iletisi satırda da çizilir (0.17.0):** `tek` dalı liste adresine `s=<kimlik>` + `#t-<kimlik>`
  ile döner; ileti yalnız sayfa başında kalsaydı uzun listede ekran dışında kalırdı. `#t-…` çapası yalnız liste
  adresinde eklenir (`tahta_liste.liste_yolu_mu`); `yonlendir` iletiyi parçadan ÖNCE koyar.
- **Seçim çubuğu sarmaz ve taşmaz; telefonda alt çubuğun üstündedir (0.17.0):** çubuk sararsa ya da taşarsa
  sayfa 390 px'ten genişler ve alt çubuk da taşar (0.15.0 tuzağı). Dar ekranda "Duyuru gönder" "Diğer"in ilk
  öğesine iner. Çubuktaki GET düğmesi (`formaction="/duyurular/yeni"`) formun `donus` ve `secimden` alanlarını da
  sorguya koyar; `secimden=1` olmasa seçimsiz gönderim "Tüm tahtalar"lı forma düşerdi.
- **`/` Bugün'dür, liste yalnız `/tahtalar`'dadır; ikinci liste yazma (0.18.0):** iki sayfa ve `/api/durum`
  tahtaları aynı yardımcıdan yükler (`web.py::tahta_baglami` → `tahta_gorunumu`); Bugün'e tahta satırı, satır
  düğmesi ya da seçim eklenmez (çip tahta sayfasına, kutu `?durum=`'a gider). `/` iletisiz yönlendirme yapmaz:
  öbür bölümlerin "yetkiniz yok" dönüşleri (`yonlendir("/", …)`) Bugün'ün başında çizilir ve odaklanır; yalnız
  0.17.0'ın `/?durum=`/`/?s=` adresleri `/tahtalar`'a 303 olur. `tahta_liste.liste_yolu_mu` yalnız `/tahtalar`'ı
  tanır: `donus="/"` ile gelen `tek` komutu `s=`/`#t-` almaz. `/`'yi açan test liste mi, ileti mi, bant mı
  sınıyor — ona göre adres seçilir.
- **Tahta sayfasına form eklerken dönüş adresi sekmeyi taşır (0.17.0):** `donus=/tahta/{id}?sekme=<sekme>#<bölüm>`;
  sekmesiz dönüş Genel'e düşer ve ileti başka sekmede kalır. Bölüm kimlikleri (`#program`, `#temizlik`,
  `#envanter`, `#arizalar`, `#baglanti`) eski yer imleri için korunur; `panel.js::tahtaEskiParcaKur` onları sekmeye
  taşır. Yeni alan ya da uç eklenince `tests/test_tahta_sekmeleri.py`'deki alan listesi de güncellenir.
- **Bir bölümün şeridini çizen sayfa menüde o bölümün `esler`'indedir (0.17.0; 0.19.0'da bütün bölümler):** rolle
  gizlenen sekmenin sayfası da (idareci `/gruplar`'ı adresle açarsa) bölümünü etkin göstermelidir. Yönetici
  sekmeleri idareci HTML'inde çizilmez (CSS ile gizlenmez); `test_idareci_htmlinde_yonetici_ogesi_yok` ve
  `tests/test_bolum_serit.py` adları ve adresleri arar. `/ogretmen-programi` Program'ın `esler`'indedir (0.19.0'a
  kadar Kişiler'deydi); `bolum_serit.sayfa_onekleri` ile `MENU` testle eşlenir.
- **İşaretsiz onay kutusu gönderilmez; "formda yok" ile "kapalı" ayırt edilemez (0.16.0):** bir bölümün POST'u
  eksik gövdeyle gelirse kutular kapalı sayılıp ayar ezilir. Yeni bölümler (`okul`, `kapatma`, `kilit_kodu`) formun
  o form olduğunu gösteren nöbetçi alanı ister, yoksa hiçbir şey yazmaz; `bolum=genel` otomatik kapatmayı yalnız
  `ok_saatler` formdayken yazar. Yeni birleşik form yazma; bir form bir uca gider, yalnız kendi anahtarını yazar.
- **Boş kilit kodu kodu silmez (0.16.0):** silme yalnız açık `kilit_kodu_sil=1` ile. Kod, özeti ve uzunluğu
  sayfaya, özete, iletiye, kayda geri yazılmaz.
- **Ayar bölümü eklemek = `ayar_bolumleri.BOLUMLER`'e bir öğe + `_ayar_<anahtar>.html` (0.16.0):** menü, giriş
  kartı, özet, arama ve test listesi oradan türer; şablona ya da `web.py`'ye ikinci liste yazılmaz.
- **Onaylı düğme `type="button"` + `data-onay`'dır ve JS'siz gönderilmez (0.16.0, bilerek):** "Kodu kaldır…",
  "Logoyu kaldır…". `type="submit"` yapıp "JS'siz de çalışsın" diye düzeltme; `<noscript>` notu durur.
- **Kart çapası ile alan kimliği çakışmasın (0.16.0):** Veri bölümünde kart `#saklama`, yedek saklama girdisinin
  kimliği `yedek_saklama`'dır (`name` yine `saklama`). Yedek parolası formuna `data-kirli-izle` konmaz.
- **Git Bash'te `panel_olcum.mjs --yol=/ayarlar/...` yolu Windows yoluna çevrilir (0.16.0):** `MSYS_NO_PATHCONV=1`
  ile çalıştır. Başsız Edge'in `AssistantLoadState` hatası tarayıcının kendi betiğidir, panelin değil.
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
- **Panel menüsünde açılır grup yoktur (0.15.0'dan beri; eskiden JS'siz `<details>` idi).** Yan menüde alt
  liste de yoktur (0.17.0; bölüm içi gezinme sekme şeritleriyle). JS'siz açılır
  `<details>` "Program kilidini durdur"da (Program şeridi ve 0.18.0'dan beri Bugün › Şu an), Bugün'ün "Diğer N iş"
  katlamasında ve duyuru formunun "Kime" açılırlarında (0.19.0; bina/kat/düzey/devre, tek tek seç) vardır.
  `<form>` `<p>` içine konmaz (tarayıcı
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
