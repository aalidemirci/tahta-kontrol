# 0.16.0 — panel arayüzü 2. aşama: Ayarlar

19 Kasım 2026. Geliştirme kopyası; kurulu hizmet ve bağlı tahta değiştirilmedi, dağıtılmadı.
Denemeler uydurma veriyle ("Örnek Anadolu Lisesi") yapıldı; ekran görüntüsü ve gerçek veri depoya girmedi.
Tasarım ve aşama planı: `docs/tasarim.md` §11.1.

Kullanıcı 0.15.0'ı (yeni kabuk) gördü ve 19.11.2026'da "Ayarlar'a geç" diyerek altı aşamalı planın
**2. aşamasına** onay verdi. Bu sürüm yalnız o aşamadır: Ayarlar tek uzun sayfa olmaktan çıktı. Ayarların
kendisi (anahtarlar, anlamları, varsayılanları) değişmedi; yalnız **nerede durdukları ve nasıl kaydedildikleri**
değişti.

## Ne değişti

- **Ayarlar giriş sayfası** (`/ayarlar`). Dört başlık altında on bir bölüm kartı; her kartın yanında o
  bölümün **o anki değeri** yazar ("18:30", "Kod tanımlı · açılışta kilit açık", sarı "Tarih yok"). Değeri
  görmek için bölümü açmak gerekmez. Özetlerde kilit kodu, parola, PIN, kişi adı, ağ adresi ve klasör yolu
  görünmez.
- **Kurulum kontrol listesi.** Giriş sayfasının başındaki kutu eksik adımları gösterir (kilit kodu, öğretim
  yılı bitiş tarihi, yedek parolası gibi); tamamlananlar tek satırda adlarıyla durur. Zorunlu adımlar bitince
  kutu katlanır. Kutu koşullardan türetilir; "gizle" diye saklanan yeni bir ayar yoktur.
- **Ayarlar içi arama.** Sözcük başına arar, önce Türkçe harflerle, sonuç yoksa harf katlayarak ("yuzer" →
  Yüzer düğme). Eş anlamlıları bilir ("kayar buton", "kvkk", "şifre", "kapanma saati", "idareci ekle").
  Ayarlar'da **olmayan** işler "Ayarlar'da değil, şurada" kutusunda çıkar (program kilidi, boş ders uyarısı,
  zil saatleri → Program; acil şablonları → Acil durum; PIN → Kişiler ve anahtarlar; yedek alma → Yedekler).
  JavaScript kapalıyken de çalışır (`/ayarlar?ara=…`).
- **Bölüm sayfaları** (`/ayarlar/<bölüm>`). Solda bölüm menüsü (değerleriyle; dar ekranda açılır liste), sağda
  o bölümün kartları. **Her kartın kendi Kaydet düğmesi** vardır ve yalnız kendi ayarını yazar; kayıttan sonra
  aynı bölüme, o kartın başındaki iletiye dönülür.
- **Kaydet çubuğu.** Değişiklik yokken "Değişiklik yok." yazar. Bir alan değişince "Kaydedilmemiş değişiklik
  var" çıkar, çubuk ekranın altına yapışır, Vazgeç görünür ve sayfadan çıkarken tarayıcı uyarır. Bu yalnız
  kolaylıktır: JavaScript kapalıyken formlar düz biçimde kaydedilir. Hiçbir ayar dokunur dokunmaz kaydolmaz.
- **Uzun açıklamalar kısaldı ya da açılır satıra alındı** ("Ne zaman uygulanmaz?", "Neler silinir, neler
  silinmez?" gibi). Hiçbir bilgi ve uyarı çıkarılmadı; eski sayfadaki her cümlenin yeni yeri taslağın
  açıklama çizelgesine göre yerleştirildi.
- **Dikkat gerektiren iki iş onay ister:** "Kodu kaldır…" ve "Logoyu kaldır…" onay penceresi açar.
  **JavaScript kapalıyken bu iki düğme çalışmaz** (bilerek: yanlışlıkla gönderilmesin); sayfa bunu bir notla
  söyler.
- **Yoklama maskesi** açılır liste yerine üç örnekli seçenek kartıdır ("Tahtada: 123 Ayşe Y." gibi). Seçenekler
  ve anlamları aynıdır; ad ile numaranın ikisi birden açık olduğu bir seçenek yine yoktur.
- **Kilit kodu** alanında "Kodu göster" kutusu vardır (yalnız yazarken; kayıtlı kod hiçbir zaman sayfaya geri
  yazılmaz).
- **Panel kullanıcıları** Ayarlar'ın bir bölümü oldu; menüdeki ayrı "Kullanıcılar" öğesi kalktı (menü dokuz
  öğe). Eski `/kullanicilar` adresi yeni bölüme yönlenir.
- **Acil yayın şablonları** Acil durum sayfasında "Şablonlar" sekmesine taşındı (yalnız yöneticiye çizilir).
- **Yedek parolası, saklama günü ve ikinci kopya** Ayarlar › Veri saklama ve yedek'te de görünür. Formlar
  kendi eski uçlarına gider; Yedekler sayfasındaki formlar da çalışmaya devam eder.
- Başka sayfalardaki "Ayarlar" bağlantıları ilgili bölüme gider (ör. panodaki adres uyarısı → Sunucu ve ağ).

## Hangi ayar nereye gitti

| Eski tek sayfadaki bölüm | Yeni yeri | Adres |
|---|---|---|
| Okul adı | Okul kimliği › Okulun adı | `/ayarlar/okul` |
| Okul kimliği (renkler, önizleme, logo) | Okul kimliği › Renkler · Logo | `/ayarlar/okul` |
| Ortak kilit kodu, kodu kaldır | Kilit ve güvenlik › Ortak kilit kodu | `/ayarlar/kilit` |
| Açılışta kilit | Kilit ve güvenlik › Açılışta kilit | `/ayarlar/kilit` |
| Otomatik kapatma | Kapatma ve gün sonu › Otomatik kapatma | `/ayarlar/gunsonu` |
| Oturum temizliği | Kapatma ve gün sonu › Oturum temizliği | `/ayarlar/gunsonu` |
| Tahtadaki yüzer düğme | Yüzer düğme | `/ayarlar/yuzer` |
| Ders yoklaması | Ders yoklaması | `/ayarlar/yoklama` |
| USB anahtar | USB anahtar | `/ayarlar/usb` |
| Sınav ekranı kuralları | Sınav ekranı | `/ayarlar/sinav` |
| Kişisel veri saklama (öğretim yılı bitişi) | Veri saklama ve yedek › Öğrenci verisinin saklanması | `/ayarlar/veri` |
| Yedek parolası, saklama, ikinci kopya (Yedekler sayfası) | Veri saklama ve yedek (Yedekler'de de durur) | `/ayarlar/veri` |
| Sunucu adresleri | Sunucu ve ağ › Sunucu adresleri | `/ayarlar/sunucu` |
| Sunucu bilgisi (parmak izi, veri klasörü) | Sunucu ve ağ › Bu sunucu | `/ayarlar/sunucu` |
| Güncelleme denetimi, "Şimdi denetle" | Güncelleme denetimi | `/ayarlar/guncelleme` |
| Kullanıcılar (ayrı sayfa) | Panel kullanıcıları | `/ayarlar/kullanicilar` |
| Acil yayın şablonları | **Ayarlar'da değil:** Acil durum › Şablonlar | `/acil?sekme=sablonlar` |
| "Ayarları kaydet" (ad + kapatma + kilit kodu birlikte) | Kalktı; üçü ayrı kartta ayrı kaydedilir | — |

Ayarlar'da hiç olmayanlar yerinde kaldı: program kilidi kuralları ve boş ders uyarısı (Program › Kurallar),
zil saatleri (Program), yedek alma ve geri yükleme (Yedekler). Arama bunlara yönlendirir.

Eski adresler çalışır: `/ayarlar?yer=…` (yer imi, açık kalmış sekmenin dönüşü) ilgili bölüme yönlenir;
`/ayarlar#bölüm` biçimindeki eski bağlantıyı giriş sayfası JavaScript ile bölüme taşır (JavaScript kapalıysa
giriş sayfasında kalınır, bölüm bir tık ötededir).

## Kayıt güvenliği

Bu sürümün asıl riski buydu: bir bölüm kaydedilirken başka bir ayarın sessizce sıfırlanması.

- Eski sayfada okul adı, otomatik kapatma ve kilit kodu **tek formla** kaydediliyordu. Artık üç ayrı karttır
  ve üç yeni gönderim bölümü vardır: `bolum=okul`, `bolum=kapatma`, `bolum=kilit_kodu`. Her biri önce
  doğrular, sonra **yalnız kendi anahtarını** yazar. Okul adını kaydetmek otomatik kapatmayı ve kilit kodunu
  değiştirmez; tersleri de öyle.
- **Onay kutuları:** işaretsiz kutu tarayıcıdan hiç gönderilmez. Yeni üç bölüm bu yüzden formun gerçekten o
  form olduğunu gösteren bir alan ister; eksik gövdeyle gelen istekte hiçbir şey yazılmaz.
- **Kilit kodu:** boş bırakılan alan kodu silmez. Kod yalnız onaylı "Kodu kaldır…" ile silinir.
- `bolum=genel` (eski birleşik form) uyumluluk için eski davranışıyla durur: 0.15.0 sayfası açık kalmış bir
  sekme yine kaydedebilir. Tek sertleştirme: otomatik kapatma yalnız saat alanı formdayken yazılır ve bozuk
  saatte okul adı da yazılmaz (0.15.0 formu bu alanı her zaman gönderdiği için o formun davranışı aynıdır).
- Öğretim yılı bitiş tarihi geçmiş bir tarihe onaysız kaydedilmez; sayfa gönderilen tarihle yeniden çizilir,
  onay kutusu kendiliğinden işaretlenmez. Yedek parolası yine hesap parolası ister.

## Ne değişmedi

- Ayar anahtarları, varsayılanlar, veritabanı şeması ve göçler. Var olan gönderim uçları ve alan adları
  (`bolum=yoklama`, `temizlik`, `dugme`, `usb_anahtar`, `saklama`, `sinav`, `adresler`, `guncelleme`,
  `acilis_kilidi`, `acil_sablonlari`, `/ayarlar/gorunum`, `/ayarlar/logo`, `/yedekler/parola`,
  `/yedekler/ayar`, `/kullanicilar`). Yedek uçlarına yalnız dönüş adresini seçen isteğe bağlı bir alan eklendi.
- Yetki: Ayarlar ve bütün bölümleri yalnız yöneticiye açıktır; idareci panoya döndürülür.
- Güncelleme denetimi (yalnız haber verir, ayar kapalıyken hiç istek çıkmaz, sayfa çizimi ağa çıkmaz), oturum
  temizliği, USB anahtar, yoklama maskesi ve saklama/imha kuralları.
- **Ajan ve tahta ekranı.** Ajan kodu değişmedi. Sürüm yalnız statik dosya önbelleği için yükseldi
  (`stil.css?v=`, `panel.js?v=`); tahtalar 0.16.0 paketini yine de "güncelleme" olarak görür.
- CSP (satır içi stil ve betik yok), dış kaynak ve derleme adımının olmaması, renk motoru.
- Tahtalar listesi, "Bugün" masası, sekme düzenlemeleri ve genel arama: sonraki aşamalardır, bu sürümde yok.

## Bilinen geçici durumlar

- Bilinmeyen bir bölüm adresi (`/ayarlar/olmayan`) 404 vermez; "Bilinmeyen ayar bölümü" iletisiyle giriş
  sayfasına döner.
- USB anahtar kapalıyken alt seçenekler soluk görünmez; "Kapalıyken aşağıdaki seçenekler de uygulanmaz" notu
  vardır.
- Yoklama, yüzer düğme, USB gibi eski tek anahtarlı bölümler eksik gövdeli isteği reddetmez (0.15.0'daki
  gibi); etkisi yalnız kendi anahtarındadır.
- Tahta sayfasında 390 px'te durum rozetlerinin taşabildiği incelemede not edildi; 3. aşamanın işidir, bu
  sürümün ölçümünde görülmedi.
- 1. aşamadan kalanlar sürüyor: Kişiler sayfaları Yoklama sekme şeridini çizer; bazı metinlerde "pano" sözcüğü
  durur; envanter tablosu 1366 px'te kendi kutusunda yana kayar.

## Taslaktaki sorular

Soru 69 ("Panel kullanıcıları nerede dursun?") için taslağın önerisi uygulandı: Ayarlar içinde bir bölüm.
Soru 72'nin ilk yarısı da (arama önce yalnız Ayarlar içinde) bu sürümdedir. Öbür sorular (`docs/tasarim.md`
§17, 70–79) açık duruyor; önerilen seçenekler varsayılır.

## Nasıl denendi

- `uv run pytest -q`: 1331 geçti, 11 atlandı. `uv run ruff check .`: temiz. Yeni `tests/test_ayarlar.py`
  (73 test): yalnız okul adı gönderilince otomatik kapatmanın ve kilit kodunun değişmemesi (ve tersleri), eksik
  gövdede hiçbir şeyin yazılmaması, boş kilit kodunun kodu silmemesi, eski birleşik formun hâlâ çalışması, her
  formun yeni sayfadan kendi ucuna gitmesi, eski `?yer=` adreslerinin bölüme yönlenmesi, özetlerin değerle
  tutarlı olması ve sır taşımaması, kurulum listesi, arama (Türkçe harf, harf katlama, eş anlamlı, başka
  yerdeki işler), idarecinin hiçbir bölümü açamaması, hiçbir alan adının ve uyarı cümlesinin kaybolmaması, onaylı düğmelerin
  kendiliğinden gönderilmemesi.
- Deneme sunucusunda (ayrı veri klasörü, 8797/8798, uydurma veri) başsız Edge ile **gerçek tarayıcıda kayıt
  denemesi**, JavaScript açık ve kapalı: her formda kayıttan önce ve sonra ayar tablosu okundu; yalnız o formun
  anahtarı değişti. Vazgeç, sayfadan çıkış uyarısı, arama, eski `#bölüm` bağlantıları ve "Kodu kaldır"ın
  JavaScript kapalıyken gönderilmemesi de bu denemededir.
- Ölçüm (`scripts/panel_olcum.mjs`): Ayarlar girişi, 11 bölüm ve Acil › Şablonlar; 1366 px ve 390 px, açık ve
  koyu: yatay taşma 0, kontrast eşiği altı metin 0, küçük dokunma hedefi 0, sayfa betiği hatası 0. Bütün panel
  (50 sayfa × 4 birleşim) yeniden ölçüldü; 0.15.0'a göre yeni sorun yok.
- Görüntülere gözle bakıldı: 1366'da giriş, okul, kilit, yoklama, veri (parola hatası), kullanıcılar,
  güncelleme; 390'da giriş, okul, yoklama (koyu), sonuçsuz arama.

## Denenmeyenler ve bilinen sınırlar

- **Okulun gerçek bilgisayarlarında ve gerçek telefonda denenmedi;** kurulu hizmette denenmedi, kurucu ve
  `.deb` bu sürüm için üretilmedi. Yalnız Edge (Chromium) ile denendi. Ekran okuyucuyla denenmedi.
- "Kodu göster" kutusunun alanı düz metne çevirmesi tarayıcıda tıklanarak denenmedi (kutunun yalnız JavaScript
  varken göründüğü görüntüde doğrulandı).
- Öğretim yılı tarihi ve kullanıcı ekleme hatalarında sayfanın yeniden çizimi testle ve komut satırından
  doğrulandı; ekran görüntüsüyle bakılmadı.
- Okulun gerçek ayarlarıyla (dolu kilit kodu, gerçek adres listesi, gerçek logo) denenmedi; özetler ve kurulum
  listesi yalnız uydurma tohumla görüldü.
