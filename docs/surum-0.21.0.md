# 0.21.0 — sahadan beş talep

21 Kasım 2026. Geliştirme kopyası; okuldaki kurulu sunucu ve tahtalar değiştirilmedi, dağıtılmadı.
Denemeler uydurma veriyle yapıldı; gerçek dosyalarla yapılan yerel denemelerde çıktıya yalnız sayı yazıldı,
dosyalar, ekran görüntüleri ve gerçek veri depoya girmedi.

Kullanıcı 0.20.0'ı okulda 24 ETAP tahtasına kurdu; sistem sorunsuz çalıştı. Kullanıcı kullanım sırasında
beş talep iletti ve 21.11.2026'da bu beş talebin **tek sürümde (0.21.0)** çıkmasına karar verdi:

1. Öğretmen listesi dosyadan toplu yüklenebilsin.
2. Ders yoklaması sınıf başkanlarıyla denenebilsin (sınıf başkanı USB anahtarı).
3. Tahtalar panelde birbirinden ayırt edilebilsin: 24 tahtanın hepsi aynı adla ("etap") gelmişti.
4. Sunucu penceresi kapatılınca da bildirim alanında bir simge kalsın.
5. aSc'den aktarılan ders programındaki sorunlar giderilsin: ikili eğitimde sabah ve öğle dersleri
   karışıyordu, "9/I" ile "9/İ" birleşiyordu, tahtalar ayırt edilemediği için eşleme körlemesine yapılmıştı.

Talep 3 ve 5 kullanıcının bildirdiği sorunların çözümüdür. Talep 1, 2 ve 4'ün ana çizgileri kullanıcı
kararıdır (aşağıda "kullanıcı kararı" diye geçer). Ayrıntıda ayrıca sorulmayan kararlarda önerilen seçenek
**varsayıldı**. Hepsi "Varsayılan kararlar" bölümünde listelidir ve `docs/tasarim.md` §17'de açık soru olarak
durur (soru 102–135).

**Yalnız sunucu değişti; ajan (tahtadaki program) değişmedi.** Veritabanına iki göç eklendi (aşağıda).

## Ne değişti

### 1. Öğretmenleri toplu yükleme

Yer: Kişiler ve anahtarlar › Öğretmenler ve PIN › **Toplu yükle**. Yalnız yönetici kullanır. Henüz öğretmen
yoksa kutu açık gelir.

- **Üç kaynak (kullanıcı kararı):**
  - aSc'nin "aSc Timetables 2012 XML" dışa aktarımı: yalnız öğretmenin adı ve soyadı okunur;
  - e-Okul personel listesi **OOK01001R1** (.XLS): "Adı Soyadı" ve "Görevi" sütunları okunur;
  - "Adı; Soyadı; Kod" şablonu (.xlsx, .xls ya da .csv). Şablon sayfadan indirilir.
  Kaynak dosyanın içeriğinden tanınır; dosya diske yazılmaz.
- **Önizleme:** satırlar dört durumdan birini alır: eklenecek, zaten var, pasif olarak var, dosyada
  yinelenen. Atlanan satırlar ayrıca listelenir; atlama nedeni yazılır, ad yazılmaz. Eklenecekler satır satır
  seçilir. e-Okul'da görevi öğretmen ya da müdür olmayanlar (memur, hizmetli…) ve şablonun örnek satırı
  işaretsiz gelir. Görev yalnız önizlemede görünür, saklanmaz. Önizleme 15 dakika bellekte durur ve bir kez
  kullanılır; "Vazgeç" onu siler.
- **Ad biçimi (kullanıcı kararı):** tamamı büyük harfli ad Türkçe kurala göre baş harfi büyük yazılır
  ("ŞULE İPEK" → "Şule İpek", "IŞIK" → "Işık"). Aynı çeviri tamamı küçük harfli adlara da uygulanır. Karışık
  yazılmış ad olduğu gibi kalır.
- **Ad bölme (kullanıcı kararı):** "Soyadı" sütunu boşsa ve "Adı" sütununda birden çok sözcük varsa son sözcük
  soyad sayılır. e-Okul'un tek "Adı Soyadı" sütununda da kural aynıdır. Üç ya da daha çok sözcüklü adlar
  önizlemede "bölmesini denetleyin" diye işaretlenir; bunlar yüklemeden sonra "Düzenle" ile düzeltilir.
- **Dokunulmayanlar (kullanıcı kararı):** dosyada olmayan öğretmenin kaydı değişmez; yükleme kimseyi
  pasifleştirmez. Pasif bir öğretmenle aynı adı taşıyan satır, yalnız o satırdaki "Etkinleştir" kutusu
  işaretlenirse etkinleşir.
- **Kod:** dosyada geçerli ve boşta bir kod varsa o kullanılır. Yoksa 101'den başlayarak ilk boş kod verilir.
  Var olan öğretmenin kodu değişmez.
- **PIN (kullanıcı kararı):** yükleme PIN üretmez. Yüklemeden sonra sayfanın başındaki "PIN'i olmayanların
  hepsine PIN üret" düğmesi pusulaları verir; düğme eskiden de vardı.
- **Okunmayanlar:** T.C. kimlik no, kadro, branş, aSc kısa adı, e-posta, telefon. Adında T.C. kimlik
  numarasına benzeyen değer bulunan satır atlanır. İşlem kaydına yalnız sayılar yazılır.

Derslik programı sihirbazı aSc dosyasından öğretmen okumamaya devam eder. Öğretmen listesi için aynı aSc
dosyası bu ayrı sayfaya ayrıca yüklenir.

### 2. Sınıf başkanı USB anahtarı (deneme)

Okul, ders yoklamasını öğretmenlere yaygınlaştırmadan önce sınıf başkanlarıyla denemek istedi.
Kullanıcının kararları:

- **Anahtar şubeye bağlıdır, kişiye bağlı değildir.** Sistemde kimin başkan olduğu tutulmaz; anahtarı kimin
  taşıdığını idare kendisi bilir. Bellek el değiştirdiğinde yeni anahtar üretmek gerekmez.
- **Öğretmen önceliği:** o ders saatinin yoklaması öğretmence (ya da idarece, panelden) alınmışsa başkan
  yazamaz. Öğretmen yoklamayı başkandan sonra alırsa öğretmeninki geçerli olur.
- **Dar yetki:** anahtar yalnız kendi şubesi için, yalnız o şubenin dersliğindeki tahtada ve yalnız o anki
  ders için çalışır. "O anki ders" şunlardan biridir: süren ders, 5 dakika içinde başlayacak ders ya da son
  15 dakikada biten ders. Anahtar PIN ister ve **kilit açmaz**.
- **Ayrı ayar, varsayılan kapalı:** Ayarlar › USB anahtar › "Sınıf başkanı anahtarları (deneme)". Bu ayar
  çalışmak için USB anahtar ayarının ve ders yoklamasının da açık olmasını gerektirir. Kapatılınca o an açık
  olan başkan yoklama ekranları da kapanır.

Üretim yalnız yöneticinindir: Kişiler ve anahtarlar › USB anahtarlar › **Sınıf başkanı anahtarları**. Bir
ya da birçok şube seçilir. Yanıt, her şubenin PIN'ini yazan bir pusuladır; PIN yalnız bu sayfada bir kez
görünür. Tek şube seçildiyse düz bir anahtar dosyası iner. Birden çok şubede tek seferlik bir zip iner: her
şube için bir klasör ve bir OKUBENI.txt; bağlantı 5 dakika geçerlidir ve bir kez kullanılır. Bir şubenin
en çok iki etkin anahtarı olabilir (başkan ve yardımcısı); indirilmeyi bekleyen anahtar da bu sayıya girer.

Tahtada anahtar "Sınıf başkanı · 10/A" diye görünür. Başkanın açtığı liste de öğretmeninki gibi
"123 Ayşe Y." biçimindedir. Başkan kaydı panelde "sınıf başkanı" diye gösterilir ve şu sabit notu taşır:
"deneme amaçlı yardımcı kayıttır; öğretmenin yoklamasının yerine geçmez". Şube defterinde bu kaydın ders
saati başlığı "b" ile işaretlenir. Öğretim yılı bitince o yıl üretilen şube anahtarları silinir.

Bu özellik iki kuralı bilerek esnetir; ikisi de kullanıcı onaylıdır:

- "Öğretmen programı ve saat yalnız ön seçimdir" kuralı (CLAUDE.md kural 33) başkan anahtarında geçerli
  değildir. Başkan anahtarında şube, tahta ve saat kısıtlarının hepsi uygulanır. Öğretmen, idare ve panel
  yolları değişmedi.
- "123 Ayşe Y." liste istisnası (kural 18) başkan anahtarıyla açılan listeye de uygulanır.

### 3. Tahta numarası

- Her tahtanın panelde görünen bir **numarası** vardır: "No 7". Numara, veritabanındaki tahta kimliğidir;
  yeni bir sütun açılmadı, var olan 24 tahta da numarasını hemen gösterir. Numara şu yerlerde görünür: onay
  bekleyen bandı, tahta listesinin satırları, tahta sayfasının başlığı, Bakım › Bağlantı ve ajan, arıza
  sayfaları, ders programı eşleme listesi ("No 7 · ad · derslik") ve onay pencereleri. Bugün sayfasındaki
  çiplerde numara yalnız adı başka bir tahtayla aynı olan tahtada yazar.
- **Yeni kurulan tahta "Tahta <no>" adıyla gelir.** ETAP'ta bütün tahtaların bilgisayar adı aynı
  olduğundan bilgisayar adı artık tahtanın adı olarak kullanılmaz; yalnız Bakım sekmesinde görünür.
- **Kurulum betiği** kayıt başarılı olunca tahtanın ekranına çerçeveli bir satır basar:
  "TAHTA NO: 7 -> Bu numarayi sinifin adiyla birlikte not edin." Tahta ekleme sayfası da numaranın not
  edilmesini ister.
- **Aynı adı taşıyan tahtalar:** yönetici Tahtalar sayfasında "Aynı adı taşıyan N tahta var." bandını görür.
  Banttaki düğme onay istedikten sonra adını kurulumdan almış (bilgisayar adı ya da "Yeni tahta") her tahtaya
  "Tahta <no>" adını verir. Elle verilmiş adlar, derslikler ve öbür bilgiler değişmez. İşlem kaydına yalnız
  sayı yazılır. Bilgiler sekmesinde aynı ad kaydedilebilir, ama kayıttan sonra hangi numaralarla çakıştığı
  uyarı olarak yazılır.
- Tahta listesi grup içinde doğal sırayla dizilir ("Tahta 2" "Tahta 10"dan önce gelir). Onay bekleyenler
  kurulum (numara) sırasıyla listelenir.

### 4. Bildirim alanında durum simgesi

- Kurulu programda durum penceresi kapatılınca (X ya da "Gizle") program kapanmaz, bildirim alanında simge
  olarak kalır. İlk gizlemede bir kez bilgi balonu çıkar.
- Simgenin rengi sunucunun durumunu gösterir: yeşil çalışıyor, gri başlatılıyor ya da yanıt yok, kırmızı
  durdu ya da kurulu değil. Durum 15 saniyede bir okunur. Simgenin ipucu ve balonları ağ adresi, okul adı ya
  da kişi verisi taşımaz.
- Sağ tık menüsü: Paneli aç · Durumu göster · Hizmeti başlat (yalnız hizmet durmuşken görünür, Windows yönetici
  onayı ister) · Çık. Çift tıklayınca pencere açılır. Sunucu çalışırken durursa bir kez "Sunucu durdu"
  balonu çıkar.
- **Kurucuda yeni görev (kullanıcı kararı):** "Oturum açılınca durum simgesini göster" görevi işaretli
  gelir. Bu görev başlangıç klasörüne "Tahta Kontrol durum simgesi" kısayolunu koyar; kısayol
  `TahtaKontrol.exe pencere --gizli` komutunu çalıştırır. Bu kısayol **yalnız simgeyi getirir, sunucu
  açmaz.** 0.8 öncesinin sunucu açan "Tahta Kontrol" başlangıç kısayolu yine silinir. Görev işaretsiz
  bırakılırsa önceki kurulumdan kalan simge kısayolu da silinir.
- Durum penceresi `sc query` okunamadığında artık "kurulu değil" demez, "Sunucunun durumu okunamadı" der.
  "Hizmet yeni başladı" yazısı yalnız hizmet gerçekten başlarken görünür.
- Durum simgesi her oturumda tektir. Masaüstü kısayoluna ikinci kez tıklanınca yeni simge açılmaz; var olan
  pencere öne gelir.

### 5. aSc ders programı aktarımı

- **İkili eğitim:** aSc'de ders saatleri "S1…S8" ve "Ö1…Ö8" gibi adlandırılmışsa önek devreyi, sayı da devre
  içindeki ders numarasını verir. Önek yoksa devre, sınıfların yalnız sabah ya da yalnız öğle saatlerini
  kullanmasından çıkarılır. Her saat grubu zil çizelgesinin bir devresine eşlenir. Devre sayıları aynıysa
  eşleme başlangıç sırasıyla yapılır ve soru sorulmaz (tablo açılır kutuda durur, değiştirilebilir). Sayılar
  farklıysa eşleme ekranında her grup için devre sorulur. Böylece öğlenin 1. dersi artık sabahın 9. dersine
  yazılmaz.
- **Şube anahtarı:** "9/I" ile "9/İ" artık ayrı şubelerdir.
- **Zil önerisi:** zil saatleri tanımlı değilse ya da dosyanın saatleri zile uymuyorsa dosyadaki saatlerden
  bir zil çizelgesi önerilir. Öneri onay kutusuyla oluşturulur; dosyada teneffüs saatleri yanlış olabileceği
  için oluşturmadan önce okulun gerçek zil saatleriyle karşılaştırılmalıdır. aSc dosyası artık zil saatleri
  tanımlanmadan da yüklenebilir.
- **Tahta eşleme:** seçeneklerde tahta "No 7 · ad · derslik" diye yazılır. Aynı adı taşıyan tahta varsa
  uyarı çıkar. Derslik alanı eşleşmezse rakamlar karşılaştırılır ("DERSLİK-101" ↔ "101"); rakamla bulunan
  eşleşme "Numarasından öneri" diye gösterilir ve hatırlanmaz.
- **Hatırlanan eşleşmeleri unutma:** eşleme ekranındaki "Hatırlanan eşleşmeler" kutusu, o kaynak için
  hatırlanan bütün eşleşmeleri onayla siler. Derslik programları bundan etkilenmez. Otomatik bulunan ders
  saati ve devre eşleşmeleri artık hatırlanmaz; yalnız elle seçilenler hatırlanır.
- **Tahtaların şube bilgisi:** onay ekranındaki isteğe bağlı (işaretsiz gelen) kutu, her tahtanın şube
  bilgisini o tahtanın dersliğine yerleşen sınıflardan yazar. Derslik alanı yalnız boşsa doldurulur. Bu adım
  program aynı kalsa da tek başına yapılabilir. "Önceki programlar"dan geri yükleme bu değişikliği de geri
  alır; ama yalnız o günden beri elle değiştirilmemiş tahtalarda.
- aSc kartındaki "Sınanıyor" etiketi kalktı. Yol, bir okulun gerçek "aSc Timetables 2012 XML" dosyasıyla
  denendi.

## Saha bilgisi (0.20.0 kurulu okulda yükseltme)

- **Yalnız sunucu değişti, ajan kodu değişmedi.** Sürüm numarası yükseldiği için Tahtalar'da 24 tahtanın
  hepsi "güncelleme var" görünür. "Ajanı güncelle" isteğe bağlıdır; güncellenmeyen tahta eskisi gibi çalışır.
  Sürüm, panelin stil ve betik dosyaları tarayıcı önbelleğinde yenilensin diye de yükseltildi.
- **Tahtalara yeniden kurulum gerekmez.** Kurulum betiğindeki "TAHTA NO" satırı yalnız bundan sonraki
  kurulumlarda çıkar. Kurulu tahtaların numarası panelde hemen görünür.
- **Göç** (`vt.GOCLER`'e iki öğe; yükseltmede sırayla bir kez çalışır, öncesinde her zamanki göç öncesi kopya
  alınır):
  1. **aSc:** 0.20.0'ın hatırladığı aSc ders saati eşlemeleri silinir; derslik, sınıf ve şube eşlemeleri
     kalır. Eskiden otomatik bulunan eşleme de hatırlanıyordu ve yeni devre eşlemesini bozuyordu. Eski
     kayıtlarda hangi eşlemenin elle seçildiği bilinemediği için hepsi bir kez silinir. Program sürümlerine
     şube güncellemesini geri alabilmek için bir sütun eklenir.
  2. **Sınıf başkanı:** USB anahtar tablosu şube anahtarını da alacak biçimde yeniden kurulur. Var olan idare
     ve öğretmen anahtarları korunur. Açık yoklama oturumları tablosu yeniden kurulur: yükseltme anında
     tahtada açık duran bir yoklama ekranı kapanır, yoklama yeniden açılır.

## Kurulumdan sonra yapılacaklar

1. **Tahtaları adlandırın.** Tahtalar sayfasındaki "Aynı adı taşıyan N tahta var" bandından tahtalara
   "Tahta <no>" adını verin. Sonra hangi numaranın hangi sınıfta olduğunu bulun:
   - Bakım › Bağlantı ve ajan sekmesi numarayı gösterir.
   - Kilit ekranının üst bandında tahtanın adı yazar.
   - Panelden tek bir tahtayı kilitleyip hangi sınıfta kilitlendiğine bakabilirsiniz.
   Ardından her tahtanın Bilgiler sekmesine derslik adını (istenirse yeni adını) girin. Bu sırada kilit
   ekranında yeni adın görünmesi beklenir; bu, gerçek tahtada denenmedi.
2. **Ders programını aSc'den yeniden aktarın** (0.20.0'da tahtalar ayırt edilemeden eşlendiyse). Program ›
   İçe aktar › aSc'ye gidin ve dosyayı yükleyin. Eşleme ekranındaki "Hatırlanan eşleşmeler" kutusundan eski
   eşleşmeleri unutun. Derslikleri "No · ad · derslik" seçeneklerinden yeniden eşleyin, devre tablosunu
   denetleyin. Onayda "Tahtaların şube bilgisini programdan güncelle" kutusunu işaretleyin. Zil önerisi
   çıkarsa okulun gerçek zil saatleriyle karşılaştırmadan oluşturmayın.
3. **Öğretmenleri yükleyin:** Kişiler ve anahtarlar › Öğretmenler ve PIN › Toplu yükle (e-Okul OOK01001R1,
   aSc XML ya da şablon). Önizlemede üç ya da daha çok sözcüklü adların bölünüşünü denetleyin. Sonra
   "PIN'i olmayanların hepsine PIN üret" düğmesiyle pusulaları alın ve yazdırın.
4. **Sınıf başkanı pilotu** için önce şunlar doğru olmalı:
   - tahtaların şube bilgisi (2. adım ya da Bilgiler sekmesi): yanlışsa başkan kendi sınıfında "Bu tahta
     … şubesinin dersliği değil" uyarısını alır;
   - zil saatleri: zil yoksa başkan hiç yoklama alamaz;
   - ikili eğitimde derslik programı: şubenin devresi programdan bulunur.
   Sonra Ayarlar'da ders yoklamasını, USB anahtarı ve "Sınıf başkanı anahtarları (deneme)" ayarını açın.
   Pilot şubelerin anahtarlarını üretin, pusulayı başkana verin. Okulun aydınlatma metnini denetleyin (§17
   soru 135, §18).
5. **Durum simgesi:** Windows 11 yeni simgeyi önce görev çubuğunun taşma alanına ("^") koyar. Sürekli
   görünsün isterseniz Ayarlar › Kişiselleştirme › Görev çubuğu › Diğer sistem tepsisi simgeleri'nden
   açın.

## Varsayılan kararlar (geri alınabilir)

Önceki soruların önerileri geçerliliğini koruyor (soru 69–101). Bu sürümde **soru 34 kapandı**
(öğretmen listesi kaynağı; kullanıcı kararı, yukarıda). Aşağıdaki kararlar ayrıca sorulmadı; önerilen
seçenek varsayıldı ve `docs/tasarim.md` §17'de açık soru olarak duruyor:

| No | Konu | Varsayılan |
|---|---|---|
| 102 | Numara biçimi ve varsayılan ad | "No 7", sıfırla doldurma yok; yeni tahtanın adı "Tahta 7". Okulun elle verdiği bir "Tahta N" adıyla çakışabilir; çakışma onayda uyarılır |
| 103 | Numaranın görünmesi | Her yerde "ad · No 7" yazar (ad "Tahta 7" olsa da). Bugün çipinde yalnız aynı adlıda yazar. Duyuru, gruplar, program ve sınav seçim listelerinde ve genel aramada yer almaz |
| 104 | Aynı ad | Reddedilmez, uyarılır. Karşılaştırmada büyük/küçük harf, Türkçe harf ve boşluk farkı yok sayılır. Onaylı ve onay bekleyen tahtalar sayılır |
| 105 | Toplu adlandırma | Yalnız adını kurulumdan almış tahtalar değişir (onay bekleyenler dahil). Elle verilmiş aynı adlar için bant çıkmaz. Düğme onay penceresiyle çalışır, JavaScript kapalıyken çalışmaz |
| 106 | aSc devre ayrımı | Önek yoksa sınıfların saat kullanımından ayrılır (%90 tek parçada, %60 kapsama). Teneffüs bilgisi yalnız eşitliği bozar. Sınıflar iki önekin saatlerini birden kullanıyorsa önek yalnız etiket sayılır |
| 107 | Devre grubu ↔ zil devresi | Sayılar eşitse başlangıç sırası, soru sorulmaz. Değilse ilk dersin saati ±5 dk, o da tutmazsa soru |
| 108 | Hatırlanan aSc eşlemeleri | Otomatik saat ve devre eşlemeleri hatırlanmaz. 0.20.0'ın hatırladığı aSc saat eşlemeleri göçte silinir (elle seçilenler de) |
| 109 | aSc zil önerisi | Fark uyarısı yalnız ikili eğitimli dosyada çıkar. Zil hiç yoksa tek devreli dosyada da öneri çıkar ("Normal"). Bütün günlere aynı saatler atanır. Öneri onay kutusuyla oluşturulur |
| 110 | Şube güncellemesi | Tahtanın şubeleri tamamen değişir. Sınıfı düşmeyen tahtanın şubeleri silinmez. Derslik alanı yalnız boşsa yazılır. Kutu işaretsiz gelir. Tahtalar uyandırılmaz. Geri yüklemede yalnız sonradan elle değiştirilmemiş tahtalar döner |
| 111 | Unut | O kaynağın bütün hatırlanan eşleşmelerini siler; tek tek silme yok |
| 112 | Rakamla derslik eşlemesi | Öneri olarak gösterilir, hatırlanmaz. Tahtanın adı yalnız baştan sona numaraysa ("101") aday olur; iki tahta aynı rakamı taşırsa eşlenmez |
| 113 | Öğretmen satır seçimi | Eklenecekler satır satır seçilir. Müdür ve müdür yardımcıları işaretli gelir; öğretmen ya da müdür olmayan görevler ve şablon örneği işaretsiz gelir |
| 114 | "Zaten var" ölçütü | Ad ve soyad birlikte karşılaştırılır; büyük/küçük harf ve Türkçe harf farkı yok sayılır. Benzer ad yeni kayıt olur. Dosyada aynı ad iki kez geçerse ilki alınır |
| 115 | Pasif aynı ad | Satırdaki "Etkinleştir" kutusu işaretsiz gelir; işaretlenmezse yeni kayıt da açılmaz |
| 116 | Öğretmen kodu | Dosyadaki geçerli ve boşta kod kullanılır, yoksa 101'den ilk boş kod verilir. Var olan öğretmenin kodu değişmez |
| 117 | Ad düzeltme | Önizlemede satır içi düzeltme yok; üç ve daha çok sözcüklü ad işaretlenir, sonra "Düzenle" ile düzeltilir. Karışık harfli ad olduğu gibi kalır |
| 118 | Aktarım geçmişi | Ayrı tablo ve "geri al" yok; iz yalnız işlem kaydında, sayı olarak durur. Yanlış yükleme pasifleştirmeyle geri alınır |
| 119 | aSc öğretmen adı | Ad ya da soyad boşsa aSc'deki tam ad (`name`) bölünür. aSc kısa adı kod olarak kullanılmaz |
| 120 | Simge okuma aralığı | 15 sn; açılışta ve "Hizmeti başlat"tan sonra 20 sn boyunca 1 sn |
| 121 | Simge renkleri | Hizmet çalışıyor ama sunucu yanıt vermiyorsa simge gri olur. Durdu, kurulu değil ve duraklatıldı kırmızıdır. Yedek uyarısı için ayrı (sarı) simge yok |
| 122 | Balon | Yalnız "çalışıyor → durdu" geçişinde bir kez çıkar. Hizmet yeniden çalışınca balon çıkmaz |
| 123 | Menü ve ikinci açılış | Sunucu yanıt vermezken "Paneli aç" gri kalır. Gizli açılış ikinci örnekse sessizce çıkar; elle ikinci açılış var olan pencereyi öne getirir |
| 124 | Geliştirme ve kurucu | Geliştirmede `pencere --gizli` 2 koduyla çıkar. Kurucuya "programı kapatın" uyarısı (AppMutex) eklenmedi |
| 125 | Başkan: ders saati bilinmiyorsa | Zil yoksa, bugün ders yoksa ya da şubenin devresi belirsizse başkan yazamaz; her durum ayrı iletiyle söylenir |
| 126 | Başkan: idare düzeltmesi | O ders saatinde şube defteri düzeltmesi ya da kayıt sayfasından düzeltme varsa başkan yazamaz. Kayıt sayfasından düzeltilen başkan kaydı "sınıf başkanı" kaynaklı kalır |
| 127 | Başkan: tahta ve saat | Tahta, şube bilgisinden ya da derslik programında aynı ders saatinden kabul edilir. Teneffüste hem biten hem başlayacak ders yazılabilir |
| 128 | Başkan: yıl sonu | Şube anahtarları iptal edilmez, silinir (yalnız bitiş tarihinden önce üretilenler). Öğrenciler sayfasındaki yıl sonu "Tümünü sil" de bütün başkan anahtarlarını siler (bütünleşik inceleme bulgusu) |
| 129 | Başkan: üretim | Tek etiket bütün seçilen şubelere yazılır. Şube başına en çok 2 anahtar (bekleyen dahil). Bir şube sınıra takılırsa hiçbiri üretilmez. Bir seferde en çok 80 şube. Tek şubede düz dosya, birden çoğunda zip |
| 130 | Başkan: öğrencisiz şube | Şubede etkin öğrenci kalmazsa anahtar geçersiz sayılır |
| 131 | Başkan: tahtadaki etiket | "Sınıf başkanı · 10/A"; paneldeki etiket tahtaya inmez |
| 132 | Başkan kaydının yeri | e-Okul işaretine, icmale, şube defterine ve Bugün özetine normal kayıt gibi girer; ayırt edici olan "sınıf başkanı" etiketi, sabit not ve defterdeki "b" işaretidir |
| 133 | Başkan ayarı | USB anahtar ayarı kapatılınca başkan anahtarı da çalışmaz. Başkan PIN'i varsayılan açıktır ve Ayarlar'dan kapatılabilir. Eski sekmeden gelen ayar formu başkan kutularını değiştirmez |
| 134 | İptal edilmiş başkan anahtarı | Takılınca, öğretmen anahtarında olduğu gibi işlem kaydına "iptal edilmiş/geçersiz" satırı yazılır. Öğrencinin belleği her gün takılırsa konum izi birikebilir. **Değiştirilmedi; ayrıca soruluyor** |
| 135 | Başkan: aydınlatma | Öğrencinin arkadaşlarının devam verisini okul adına işlemesi okulun aydınlatma metninde yer almalıdır; okul denetler (soru 33 ve 68'in devamı) |

Her sorunun gerekçesi ve kararın kodda nasıl değiştirileceği §17'dedir.

## Gizlilik ve yetki

- **Öğretmen yükleme:** yalnız ad ve soyad okunur ve kaydedilir; görev yalnız önizlemede görünür. T.C. kimlik
  no hiçbir kaynakta okunmaz. Dosya diske yazılmaz. İşlem kaydına yalnız sayılar düşer.
- **Başkan anahtarı:**
  - Başkanın adı ya da öğrenci kimliği hiçbir tabloya yazılmaz. Anahtar etiketinde T.C. no denetimi vardır.
  - İşlem kaydına yalnız şube, ders saati, sayılar ve anahtar kimliği yazılır.
  - Anahtar, etiket ve kimlik genel arama dizinine girmez (kural 36).
  - Ayar kapalıyken bellek takılırsa işlem kaydına bir şey yazılmaz.
- **Tahta numarası ve toplu adlandırma:** yalnız yönetici adlandırır. Adlandırılacak tahtaların listesi
  sunucuda hesaplanır; formdan tahta kimliği okunmaz. Numara genel aramaya girmez.
- **Durum simgesi:** yalnız sunucu bilgisayarının kendi adresine (127.0.0.1) ve `sc query`'ye bakar. Simge
  her Windows oturumunda o kullanıcının sürecidir. Sunucu açmaz; hizmetin verisine dokunmaz.
- **aSc:** derslik sihirbazı öğretmen ve ders adı okumamaya devam eder. Teneffüs bölümünden yalnız saatler
  okunur.

## Ne değişmedi

- Ajan ve tahta ekranı; komutlar, komut ömürleri ve adları; `/api/durum` sözleşmesi.
- Var olan adresler ve alan adları. Yeni uçlar şunlardır: `POST /tahtalar/adlandir`,
  `POST /ogretmenler/onizle`, `POST /ogretmenler/aktar`, `GET /ogretmenler/sablon.csv`,
  `POST /program/aktar/asc/zil`, `POST /program/aktar/unut`. Başkan anahtarı var olan `/usb-anahtarlar` ve
  `/ajan/usb/*` uçlarından geçer.
- Menü (on öğe) ve sekme şeritleri. Genel aramaya yeni bir girdi türü eklenmedi. Tek fark: Ayarlar'daki
  USB anahtar bölümü artık "sınıf başkanı" sözcüğüyle de bulunur.
- Kural 34 (geçerli durumun tek koddan çıkması) ve öğretmen, idare, panel yoklama yolları.
- Hizmet hesabı, veri klasörü, taşıma kuralları. Kurulu pencere yine sunucu açmaz.

## Bilinen sınırlar

- Başkan anahtarı, tahtanın şube bilgisi ya da derslik programı doğru olmadan çalışmaz. Zil saatleri
  tanımlı değilse de hiç çalışmaz.
- Başkan anahtarı da bir dosyadır ve kopyalanabilir (§14.1'deki sınır). Önlemler PIN, dar yetki, öğretmen
  önceliği ve iptaldir.
- Ajan değişmediği için tahta, anahtar türünü öğretmen anahtarı olarak bilir. Ekranda etiket "Sınıf
  başkanı · 10/A" diye görünür, kod boş kalır. Sunucu kilit izni vermediği için kilit ekranında "USB
  anahtarla aç" düğmesi çıkmaz; bu ajan testinde görüldü, gerçek tahtada denenmedi.
- aSc zil önerisi dosyadaki saatleri olduğu gibi alır; dosyada teneffüs olmayabilir.
- Toplu adlandırma, bir tahtaya elle "Tahta 7" adı verilmiş durumu çözmez. Bu çakışma iletide numarasıyla
  söylenir.
- Durum simgesinde yedek uyarısı yoktur; uyarılar durum penceresinde ve Bugün'dedir.
- Zorla kapatılan (`taskkill /F`) sürecin simgesi, fare üstüne gelene kadar bildirim alanında kalır. Bu
  Windows'un davranışıdır.

## Nasıl denendi

- `uv run pytest -q`: 1848 geçti, 11 atlandı. `uv run ruff check .`: temiz.
- Yeni testler:
  - `tests/test_ogretmen_aktar.py`: üç kaynak, ad biçimi ve bölme, kod, durumlar, T.C. reddi, yetki, önizleme
    türlerinin karışmaması;
  - `tests/test_usb_baskan.py`: göç eski şemadan veriyle; dar yetkinin her kolu; öğretmen önceliği ve yarış;
    zip ve pusula; işlem kaydında ad ve okul no bulunmaması; arama dizini; yıl sonu;
  - `tests/test_tahta_no.py`: varsayılan ad, aynı ad kuralı, toplu adlandırma ve sabit nokta, doğal sıra,
    numaranın göründüğü yerler;
  - `tests/test_tepsi.py`: sahte Win32 çağrılarıyla simge, menü, geçiş balonu, tek örnek, WM_CLOSE;
  - `tests/test_program_aktar.py` eklemeleri: uydurma ikili eğitim XML'i, göç, şube güncellemesi ve geri alma.
- Kurucu testi (`tests/test_hizmet.py`) başlangıç klasöründe yalnız `pencere --gizli` taşıyan simge
  kısayoluna izin verir. Eski "Tahta Kontrol" kısayol adı yasak kalır.
- Deneme sunucusunda (ayrı veri klasörü, uydurma veri) başsız tarayıcıyla:
  - yeni ve değişen yedi sayfa (Tahtalar, Öğretmenler ve PIN, USB anahtarlar, Ayarlar › USB anahtar,
    Program › İçe aktar, tahta sayfası Bilgiler sekmesi, Arızalar) 1366 ve 390 px'te yatay taşmasız, kontrast ve
    dokunma hedefi sorunu yok (`scripts/panel_olcum.mjs`);
  - toplu adlandırma, öğretmen CSV ve aSc yüklemesi, başkan zip'i ve pusulası HTTP ile uçtan uca.
  Bu denemede iki kusur görüldü ve düzeltildi: tamamı küçük harfli ad düzeltilmiyordu; "Soyadı" boşken
  "Adı"ndaki tam ad bölünmüyordu.
- Gerçek dosyalarla yerel deneme (ayrı veri, uydurma tahtalar, çıktıda yalnız sayı):
  - **aSc XML:** 1820 satır (sabah 894, öğle 926); 9/I ve 9/İ ayrı. Zil yokken iki devreli öneri,
    onaydan sonra yine 1820 satır.
  - **Öğretmen listesi:** iki e-Okul OOK01001R1 dosyası ve bir aSc XML'i. Bütün adlar baş harf biçimine
    çevrildi. Aynı dosya ikinci kez yüklenince hepsi "zaten var" çıktı.
- Durum simgesi bu geliştirme bilgisayarında kısa bir Win32 denemesinde çalıştırıldı; hizmet kurulmadı,
  sunucu açılmadı. Denenenler: simge ekleme, güncelleme ve silme; tek örnek; WM_CLOSE ile düzgün çıkış.

## Denenmeyenler

- **Gerçek ETAP tahtasında:**
  - kurulum betiğinin "TAHTA NO" satırı;
  - adlandırmadan sonra kilit ekranındaki yeni ad;
  - 0.20.0 ajanıyla başkan anahtarının bildirimi, PIN sayfası ve ret iletileri.
- **Gerçek USB bellekle:** başkan zip'inin Windows Gezgini'nde açılması (Türkçe harfli klasör adı) ve
  dosyanın belleğe kopyalanması.
- **Okul bilgisayarında ve kurulu hizmette:**
  - kurucu (bu sürüm için derlenmedi);
  - PyInstaller paketine simge dosyalarının ve `win32gui`'nin girmesi;
  - kurulu Windows'ta bildirim alanı simgesinin görünümü: oturum açılınca gelmesi, Explorer yeniden
    başlayınca geri gelmesi, yönetici olmayan kullanıcıda `sc query`, yüksek DPI, açık ve koyu görev çubuğu;
  - göçün okulun gerçek 0.20.0 veritabanında çalışması.
- Gerçek telefonda ve ekran okuyucuyla denenmedi. Öğretmen önizlemesi yaklaşık 100 satırla telefonda
  kullanılmadı.
- Okulun gerçek zil saatleriyle aSc zil önerisinin karşılaştırılması.
