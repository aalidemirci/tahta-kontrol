# 0.20.0 — panel arayüzü 6. aşama: genel arama

19 Kasım 2026. Geliştirme kopyası; kurulu hizmet ve bağlı tahta değiştirilmedi, dağıtılmadı.
Denemeler uydurma veriyle ("Örnek Anadolu Lisesi") yapıldı; ekran görüntüsü ve gerçek veri depoya girmedi.
Tasarım ve aşama planı: `docs/tasarim.md` §11.1.

Kullanıcı 0.19.0'ı (sekmeler) gördü ve 19.11.2026'da "Aramaya geç" diyerek altı aşamalı planın **6. ve son
aşamasına** onay verdi. Bu sürüm yalnız o aşamadır: panelin her sayfasında duran bir arama kutusu ve bir sonuç
sayfası. Bununla taslaktaki altı aşamanın hepsi yerelde uygulanmış oldu.

**Var olan hiçbir adres değişmedi.** Yeni adres yalnız iki tanedir: `/ara` (sonuç sayfası) ve `/api/ara`
(kutunun yazarken gösterdiği öneriler). Veritabanı, tahtalar (ajan), komutlar ve öbür sayfalar aynıdır.

Taslağın açık sorularında ve bu aşamada doğan yeni sorularda **önerilen seçenek varsayıldı**; hepsi aşağıda
"Varsayılan kararlar" başlığında, nasıl geri alınacağıyla birlikte yazılıdır.

## Ne değişti

- **Yan menüde arama kutusu:** "Acil durum" düğmesinin hemen altında, menünün üstünde. Yer tutucusu "Tahta,
  şube, sayfa ara". Menü öğesi değildir: menü yine üç küme ve tam on öğedir.
- **Yazarken öneri:** iki harften sonra kutunun altında en çok sekiz öneri açılır; daha çok sonuç varsa en altta
  "Tüm sonuçlar (N)" satırı durur. Ok tuşlarıyla gezilir, Enter seçilen sayfayı açar.
- **Sonuç sayfası (`/ara`):** sonuçlar sabit sırayla gruplanır — Sayfalar ve işler · Ayarlar · Şubeler ·
  Tahtalar · Gruplar. Her satır tek bir sayfaya götüren bağlantıdır. JavaScript kapalıyken de çalışır (kutuya
  yazıp Enter).
- **Sorgu boşken "Sık işler":** en çok sekiz kısa yol, günlük iş sırasıyla (Duyuru yap · Kapat, kilitle,
  yeniden başlat · Bütün tahtaları kilitle · Şube defteri · Yoklamayı panelden gir · Mazeret ya da izin gir ·
  Devamsızlık icmali · Arıza kayıtları).
- **Telefonda ve dar ekranda:** üst çubukta, Acil'in solunda büyüteç düğmesi; arama sayfasını açar ve kutu
  kendiliğinden odaklanır. Sayfadaki kutu da yazarken öneri verir. Aynı kutu çekmece menüsünün içinde de vardır.
  Alt çubuk değişmedi (Bugün · Tahtalar · Duyurular · Yoklama · Menü).
- **Yer açmak için iki küçük görünüm değişikliği:** çok dar ekranda (yaklaşık 416 px ve altı) üst çubukta okul
  adı yazılmaz, yalnız logo rozeti durur (ad ekran okuyucuya yine okunur); kısa pencerede (yaklaşık 640 px
  yükseklik ve altı, fareyle) yan menü satırları biraz alçalır, böylece yöneticinin on öğesi kaydırmadan sığar.

## Neler aranır

| Ne | Örnek | Nereye götürür |
|---|---|---|
| Sayfalar ve sekmeler | "yoklama", "zil", "mazeret", "arıza" | o sayfa ya da sekme |
| Sık işler (kısa yollar) | "duyuru yap", "pin pusulası", "yedek", "tören", "kapat", "ders programı" | işin yapıldığı sayfa |
| Tahta listesi süzgeçleri | "çevrimdışı", "güncelleme", "kilitli" | Tahtalar, o süzgeçle |
| Ayar bölümleri (yalnız yönetici) | "kvkk", "yüzer", "kilit kodu" | Ayarlar'ın o bölümü |
| Şubeler (yoklama açıksa) | "9/a", "9-a", "9a" | o şubenin şube defteri |
| Tahtalar | adı, dersliği, binası, katı, şubesi | o tahtanın sayfası |
| Tahta grupları (yalnız yönetici) | grubun adı | Tahtalar › Gruplar |

Nasıl eşleşir:

- **Sözcüğün başı yeter:** "duy" Duyurular'ı, "yed" Yedekler'i bulur. Sözcüğün ortası aranmaz ("urular"
  bulmaz).
- **Türkçe harf yazmasanız da olur:** "cevrimdisi", "ogretmen pin", "yuzer" bulur; Türkçe harfle yazılmış
  eşleşme üstte sıralanır.
- **Ek almış sözcük de bulur:** "pusulası", "tahtaları kapat", "yoklama ayarları".
- Birden çok sözcük yazarsanız hepsi geçmelidir. En çok 60 karakter ve altı sözcük dikkate alınır.
- Yazım hatası düzeltilmez ("yoklma" bulmaz).

Arama sonucu yalnız **bir sayfayı açar**. Sonuca tıklamak hiçbir tahtaya komut göndermez, hiçbir şeyi
kaydetmez, hiçbir dosya indirmez: "Bütün tahtaları kilitle" sonucu Bugün sayfasındaki onaylı düğmenin yanına,
"Kapat, kilitle, yeniden başlat" Tahtalar listesine götürür; işi orada siz yaparsınız.

## Neler BİLEREK aranmaz ve neden

| Aranmayan | Neden |
|---|---|
| Öğrenci adı, okul numarası | Panel yeni bir "kişi arama" aracına dönüşmesin; öğrenci verisi yalnız kendi sayfalarında (şube defteri, öğrenci listesi) görünür |
| Öğretmen adı ve kodu, panel kullanıcı adları | Aynı gerekçe; PIN ve hesap bilgisi kendi sayfasında kalır |
| Mazeret ve yoklama kayıtları | Mazeret türü ve devamsızlık bilgisi kendi sayfaları dışına çıkmaz |
| Duyuru başlığı ve metni, acil şablonları | Serbest metindir, içinde kişi adı olabilir |
| Arıza açıklamaları | Serbest metindir |
| Sınav adları, salon ve öğrenci listeleri | Sınav verisi yalnız sınav sayfalarındadır |
| Ders başlıkları, öğretmen programı | Soru 75 onaylanmadı: panelde ders başlığı ve öğretmen bilgisi gösterilmez |
| USB anahtar etiketleri | Anahtarın kimde olduğunu söyler |
| Tahtanın ağ adresi, makine adı, demirbaş numarası, envanter notu | Ağ ve cihaz bilgisi; not serbest metindir |
| Onay bekleyen tahtalar | Henüz adlandırılmamıştır; adları yalnız Tahtalar'daki bantta ve yalnız yöneticiye görünür |
| Ayarların değerleri, grup açıklamaları | Aranan şey ayarın yeri, değeri değil |

Bunun sonuçları:

- **Kişi adı yazarsanız sonuç çıkmaz.** Çıkan not her sorguda aynıdır; o adda biri olup olmadığını belli etmez.
  Not yol gösterir: yazımı denetleyin ya da sözcüğün başını yazın; bir öğrencinin yoklaması için Yoklama › Şube
  defteri'nden şubesini açın.
- **Aradığınız şey hiçbir yere yazılmaz:** işlem kaydına, günlük dosyasına, veritabanına girmez; "son
  aramalar" listesi yoktur (tarayıcıda da saklanmaz). Tek istisna tarayıcının kendi geçmişidir: sonuç
  sayfasının adresi (`/ara?q=…`) yazdığınız sözcüğü taşır ve tarayıcı geçmişinde kalır. Sayfa başlığına sorgu
  bilerek yazılmadı ("Arama · Tahta Kontrol"). Ortak bilgisayarda bunu aklınızda tutun.
- **Sonuçlar role göre süzülür.** İdareci, yalnız yöneticinin açabildiği sayfaları (Ayarlar, Yedekler, Gruplar,
  Ajan kurulum paketi, CSV aktarma, öğretmen programı, program içe aktarma, acil şablonları) sonuçlarda
  görmez: adı da adresi de sayıya da girmez. İdarecinin sonuçsuz notunda bir satır bunu genel olarak söyler
  ("Yalnız yöneticinin açabildiği sayfalar sonuçlarda görünmez"); hangi sayfa olduğunu söylemez.
- **Tahta adına kişi adı yazdıysanız** (ör. bir öğretmenin adıyla anılan derslik) o ad aramada da çıkar; tahta
  adı zaten iki role de Tahtalar listesinde açıktır, arama yeni bir şey göstermez.

## Klavye

- **`/` tuşu** arama kutusuna götürür. Bir metin alanında yazarken (duyuru metni, şube defterindeki not, herhangi
  bir form alanı) tetiklenmez: `/` karakteri yazdığınız yere yazılır. Dar ekranda `/` çekmece menüsünü açıp
  kutuya odaklar; arama sayfasındayken sayfadaki kutuya odaklar.
- **Ok tuşları** öneriler arasında gezer, **Enter** seçili öneriyi açar. Öneri seçmeden Enter bütün sonuçların
  sayfasını açar.
- **Esc** önce öneri listesini kapatır; çekmece açıksa ikinci Esc çekmeceyi kapatır.
- Türkçe Q klavyede `/` Shift+7'dir; kısayolu kullanmak zorunda değilsiniz, kutu tıklanarak da kullanılır.

## Ayarlar içi aramayla ilişkisi

Ayarlar giriş sayfasındaki arama (0.16.0, `/ayarlar?ara=`) olduğu gibi duruyor: kartları yerinde süzer ve
ayarların o anki değer özetlerini gösterir; yalnız yöneticiye açıktır. Genel arama ayar bölümlerini aynı
listeden ve aynı harf kurallarıyla bulur, ama değer göstermez; yalnız bölüme götürür. İki ayrı ayar listesi
yoktur.

## Varsayılan kararlar (geri alınabilir)

Önceki soruların önerileri sürüyor (soru 69–90). Soru 72 ("genel arama ne zaman?") bu sürümle kapandı.
**Soru 75 onaylanmadı:** hiçbir sayfaya, arama dizinine de, ders başlığı ya da öğretmen bilgisi eklenmedi.

Bu aşamada doğan ve ayrıca sorulmayan kararlar; hepsinde önerilen seçenek **varsayıldı** ve `docs/tasarim.md`
§17'de açık soru olarak durur (soru 91–101):

| No | Varsayılan | Geri almak / değiştirmek |
|---|---|---|
| 91 | Kısayol yalnız `/`; Ctrl+K yok (tarayıcının kendi kısayoluyla çakışır) | `panel.js::aramaKur`'daki tuş koşuluna ikinci tuş eklenir |
| 92 | Şube aranınca şube defteri açılır ve şube, aynı adlı tahtadan önce sıralanır | Sıra `arama.TUR_SIRASI` ve `GRUP_SIRASI`'ndadır |
| 93 | Grup sonucu yalnız yöneticiye çıkar ve Gruplar sayfasına götürür | İdareciye de çıkması için "bu gruba duyuru" ön seçimi (yeni bir GET parametresi) gerekir; ayrı iş |
| 94 | Onay bekleyen tahtanın adı yöneticinin aramasında da çıkmaz | `arama.devingen_dizin`'deki `durum = 'onayli'` koşulu; gizlilik kuralına dokunur, ayrı karar |
| 95 | Demirbaş numarasıyla tahta aranmaz | Aynı sorguya sütun eklemek; ayrı karar |
| 96 | Telefonda büyüteç düğmesi arama sayfasına gider; yerinde açılan kutu yok | Açılır katman kabuk işidir (odak, çekmece, alt çubuk); ayrı iş |
| 97 | Öneri seçmeden Enter ilk öneriye değil, bütün sonuçların sayfasına gider | `panel.js::aramaOneriKur`'da Enter dalı |
| 98 | Ayarlar içi arama ayrı kalır; ikisi aynı tanımlardan beslenir | Birleştirmek Ayarlar sayfasındaki değer özetlerini kaybettirir |
| 99 | Sonuçsuz notunun metni (yukarıda) | Metin yalnız `ara.html`'dedir; sorguya göre değişen not YAZILMAZ |
| 100 | Sorgu boşken sekiz "sık iş" ve sırası | `arama.SIK_ISLER`'deki `one` sayıları |
| 101 | Ek almış sözcük eşleşir ("pusulası"); yazım hatası düzeltilmez ("yoklma") | Ek kuralı `arama._ekli_uyar`; yazım toleransı yeni iş ve gürültü riski |

Aramaya yeni bir kısa yol eklemek ya da bir işin eş anlamlılarını değiştirmek tek yerde yapılır:
`tahta_sunucu/arama.py` içindeki `SIK_ISLER` listesi. Sayfa, sekme ve ayar adları oraya yazılmaz; menüden,
sekme şeritlerinden ve ayar bölümlerinden kendiliğinden türer (bir sekmenin adı değişirse arama da değişir).

## Gizlilik ve yetki

- **Arama yalnız görünümdür.** Her sayfanın yetki denetimi eskisi gibi kendi ucundadır; idareci yönetici
  sayfasının adresini elle yazarsa yine reddedilir.
- Bir sonucun kime görüneceği elle yazılmaz: hedef sayfa menüde ya da sekme şeridinde yöneticiye özelse sonuç
  da öyledir. Hiçbir bölüme bağlanamayan hedef program açılırken hata verir (sessizce "herkese açık" olmaz).
- Rol süzmesi eşleştirmeden önce yapılır; "N sonuç" sayısı ve "Tüm sonuçlar (N)" süzülmüş sayıdır.
- Arama sırasında öğrenci, öğretmen, kullanıcı, USB anahtar, yoklama, mazeret, duyuru, arıza, sınav ve öğretmen
  programı tablolarına sorgu gitmez (öğrenci tablosundan yalnız şube adları okunur). Okunan sorgu sayısı tahta
  ve öğrenci sayısından bağımsızdır (en çok dört).
- İki uç da oturum ister ve önbelleğe alınmaz (`no-store`). Sorgu sayfaya kaçışlı basılır; öneri listesi metni
  düz metin olarak yazar. Satır içi betik ve stil yoktur (CSP değişmedi); dış kaynak yoktur.
- Mevzuat atfı yoktur.

## Ne değişmedi

- Veritabanı şeması ve göçler; ajan ve tahta ekranı; komutlar, ömürleri ve adları.
- Var olan bütün adresler, gönderim uçları, alan adları ve doğrulamaları; `/api/durum`'un anahtarları (aramanın
  o yola hiçbir yükü yoktur).
- Menü: üç küme, tam on öğe; telefon alt çubuğu beş düğme.
- Ayarlar içi arama (`/ayarlar?ara=`).
- Sayfa içerikleri. İki küçük dokunuş: Gruplar tablosunda her satır bir çapa aldı (arama sonucu doğru satıra
  insin diye); Ayarlar aramasındaki "Boş ders uyarısı" ve "Zil saatleri" kısa yollarının kırıntısı ve adresi
  hedef sekmeyle aynı yazıldı (açılan sayfa aynıdır).
- CSP, dış kaynak ve derleme adımının olmaması, renk motoru (yeni renk belirteci eklenmedi).
- Ajan kodu değişmedi; sürüm statik dosya önbelleği için yükseldi (tahtalar 0.20.0 paketini yine de
  "güncelleme" olarak görür).

## Bilinen sınırlar

- **Yazım hatası toleransı yok;** sözcük ortası aranmaz. Not bunu söyler.
- **Tarayıcı geçmişi** sonuç sayfasının adresini (aranan sözcükle) tutar; öneri listesinden gidilen sayfalarda
  sözcük adrese girmez.
- **"Onay bekleyen tahtalar" sonucu** (yalnız yönetici) Tahtalar sayfasındaki banda götürür; bekleyen tahta
  yokken bant da yoktur, sayfa başı açılır.
- **Aranmayan işler:** "çıkış", "tahta sil", "nöbet" gibi sözcükler sonuç vermez (çıkış bir gönderimdir, sayfa
  değildir; silme tahtanın kendi sayfasındadır).
- **Kısa sözcüklerde gürültü:** sözcük başı kuralı yüzünden "ip" USB anahtarlar'ı ("iptal"), "A Blok" ya da
  "10 b" gibi sorgular ilgisiz birkaç satırı da getirebilir; aranan tahta ilk sıradadır.
- **Tahtalar ada göre sıralanır** (Tahtalar listesindeki konum sırasıyla değil).
- Sonuç sayfası en çok 50 sonuç gösterir; aşılırsa "bir sözcük daha yazın" notu çıkar. Öneri en çok sekizdir.
- Yan menüdeki yer tutucu iki rolde aynıdır ve "ayar" demez (yönetici ayarları da arayabilir; sonuç
  sayfasındaki açıklama söyler).
- Arama sayfasındayken üst çubuktaki büyüteç "bu sayfadasınız" diye işaretlenmez.
- Telefonda, arama sayfasında öneri listesi açıkken altındaki "Sık işler" başlığını örter.
- Çok dar ekranda okul adı üst çubukta görünmez (yukarıda); logosu olmayan okulda baş harf rozeti kalır.
- Kısa pencerede yan menü satırları 32 px'e iner (yalnız fareyle; dokunmatikte 44 px kalır).

## Nasıl denendi

- `uv run pytest -q`: 1694 geçti, 11 atlandı (0.19.0: 1583 geçti). `uv run ruff check .`: temiz. Yeni testler:
  `tests/test_arama.py` (dizinin menü, sekme şeritleri, ayar bölümleri ve süzgeçlerle birebir eşlenmesi; kaynak
  dosyada elle yazılmış sayfa adı bulunmaması; her hedefin var olan bir GET sayfası olması; rolün hedef sayfadan
  türemesi; idareci dizininde yönetici girdisinin bulunmaması; eşleme ve sıralama kuralları; örnek görevlerin
  ilk üç sonuçta çıkması) ve `tests/test_arama_sayfasi.py` (oturum, `no-store`; **uydurma öğrenci, öğretmen,
  kullanıcı, USB etiketi, duyuru, arıza, sınav, ders başlığı, mazeret, grup açıklaması, ağ adresi, makine adı,
  demirbaş ve bekleyen tahta tohumlanıp hiçbir sorguda iki rolde de çıkmadığının** denetimi; idareci
  sonucunda yönetici başlığı ve adresinin bulunmaması; aramanın işlem kaydına, veritabanına ve günlüğe
  yazmaması; kişi tablolarına sorgu gitmemesi; sorgu sayısının tahta ve öğrenci sayısından bağımsızlığı; HTML
  kaçışı; uzun sorgu; kabuktaki formun her sayfada düz GET olması; betikte `innerHTML` ve tarayıcı deposu
  bulunmaması; kısayolun metin alanında tetiklenmemesi; yer tutucu kontrastı; Ayarlar içi aramanın
  değişmemesi). Var olan "idareci sayfasında yönetici öğesi yok" testlerine arama adresleri eklendi; test
  silinmedi, gevşetilmedi.
- Deneme sunucusunda (ayrı veri klasörü, 8797/8798, uydurma veri, benzetilmiş ajanlar) başsız Edge ile:
  - 1366 px: `/` kutuyu odaklar; yazınca öneri açılır, ok ve Enter doğru sayfayı açar; yazmaya devam edince
    seçim sıfırlanır; Esc listeyi kapatır.
  - Duyuru formunda (800 px) ve şube defterinde (1366 px) metin alanında `/` yazınca karakter alana yazılır,
    sayfa değişmez.
  - 390 px: üst çubuk ve alt çubuk taşmaz; büyüteç arama sayfasını açar; sayfadaki kutu öneri verir, "Tüm
    sonuçlar" satırı görünür; çekmecedeki kutu öneri verir; Esc önce listeyi, sonra çekmeceyi kapatır.
  - İki rolde `/ara` boş, dolu ve sonuçsuz; uydurma kişi adı ve okul numarası sıfır sonuç; idarecinin ham
    yanıtında yönetici adresi yok.
  - Kısa pencere (1366x625, 1280x585, 1024x600): yöneticinin on menü öğesi kaydırmadan görünür.
- Ölçüm (`scripts/panel_olcum.mjs`; bütün sayfalar, yönetici ve idareci, 1366 ve 390 px, açık ve koyu): yatay
  taşma yok, kontrast eşiği altı metin yok; küçük dokunma hedefi yalnız önceki sürümlerden bilinen kalemlerde
  (yeni kalem yok).
- Görüntülere gözle bakıldı (uydurma veri): öneri listesi açık, sonuç sayfası yönetici ve idareci, sonuçsuz
  durum, sık işler — 1366 px; üst çubuk, sayfa kutusunda öneri ve sonuç — 390 px.

## Denenmeyenler

- **Okulun gerçek bilgisayarlarında, gerçek telefonda ve gerçek tahtalarla denenmedi;** kurulu hizmette
  denenmedi, kurucu ve `.deb` bu sürüm için üretilmedi.
- Yalnız Edge (Chromium) ile denendi; Firefox ve Safari'de denenmedi.
- Gerçek parmakla dokunma, telefon klavyesi (klavye açılınca öneri listesinin kalan yere sığması) ve ekran
  okuyucu denenmedi; öneri listesinin erişilebilirlik öznitelikleri yalnız kaynak ve tarayıcı denetimiyle
  görüldü.
- Gerçek Türkçe Q klavyede `/` (Shift+7) elle denenmedi; tuş benzetimiyle denendi.
- Okulun gerçek tahta, şube ve grup sayısıyla denenmedi; uydurma tohum on dört tahta ve altmış öğrencidir
  (sorgu sayısının büyüklükten bağımsızlığı testle, 60 tahta ve 400 öğrenciyle görüldü).
- Gerçek kullanıcıların hangi sözcükleri yazacağı bilinmiyor; eş anlamlı listesi tahmindir ve kullanımda
  görülen eksiklerle (`arama.SIK_ISLER`) genişletilmelidir.

## Ürün işareti ve tanım satırı (19.11.2026, kullanıcı kararı)

Ad "Tahta Kontrol" olarak kaldı. Ürün işareti yenilendi (`tahta_sunucu/statik/isaret.svg`: beyaz tahta, onay imi,
altında vurgu çubuğu); eski işaret 16 pikselde dağılıyordu. İşaret yalnız okul logosu yüklenmemişken görünür
(giriş sayfası, menü başlığı, tarayıcı sekmesi). Giriş ve ilk kurulum sayfalarındaki tanım satırı "kilit, duyuru,
yoklama, sınav: okulun tahtaları tek panelde" oldu. Windows kurucusu ve program dosyası aynı işareti simge olarak
taşır (`packaging/windows/tahta-kontrol.ico`). Tahtadaki ekranlar ve teknik adlar (klasör, paket, hizmet) değişmedi.
Simge gerçek Windows görev çubuğunda ve başlat menüsünde denenmedi.
