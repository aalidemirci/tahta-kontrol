# 0.18.0 — panel arayüzü 4. aşama: Bugün

19 Kasım 2026. Geliştirme kopyası; kurulu hizmet ve bağlı tahta değiştirilmedi, dağıtılmadı.
Denemeler uydurma veriyle ("Örnek Anadolu Lisesi") yapıldı; ekran görüntüsü ve gerçek veri depoya girmedi.
Tasarım ve aşama planı: `docs/tasarim.md` §11.1.

Kullanıcı 0.17.0'ı (Tahtalar) gördü ve 19.11.2026'da "Bugün'e geç" diyerek altı aşamalı planın
**4. aşamasına** onay verdi. Bu sürüm yalnız o aşamadır: paneli açınca gelen sayfa artık tahta listesi değil,
**"Bugün"** sayfasıdır. Tahta listesi `/tahtalar` adresinde, olduğu gibi durur.

0.17.0'ın sonunda iki karar sorulmuştu; ayrıca yanıt gelmediği için ikisinde de **önerilen seçenek
varsayıldı**. İkisi de tek yerden geri alınır; ayrıntısı aşağıda "Varsayılan iki karar" başlığında.

## Ne değişti

- **Açılış sayfası "Bugün"** (`/`). Yukarıdan aşağıya beş bölüm:
  - **Şu an:** ders mi, teneffüs mü, ders dışı mı (bugünkü program şeridindeki metin), sunucu saati, günün
    ders akışı (yalnız ders numarası ve başlangıç saati), program kilidinin durumu ve **"Program kilidini
    durdur"** (1 saat / gün sonuna kadar). Durdurulmuşsa yanında "Geri al (İstisnalar)" bağlantısı çıkar.
  - **Sizi bekleyenler:** eskiden tahta listesinin üstünde ayrı ayrı bantlarda duran uyarıların hepsi tek
    listede, önem sırasıyla (önce kırmızı, sonra sarı, sonra bilgi). Her satır ne olduğunu ve nereye
    gidileceğini söyler. Tehlike ve uyarı satırları hiç gizlenmez; yalnız bilgi satırları çoksa "Diğer N iş"
    altında toplanır. Hiçbir şey yoksa "Bekleyen iş yok." yazar.
  - **Tahtalar şu an:** altı durum kutusu (Açık · Kilitli · Duyuruda · Ekran sorunu · Çevrimdışı ·
    Güncelleme) ve konuma göre (bina · kat) dizilmiş küçük tahta çipleri. Kutuya basınca liste o duruma
    süzülmüş açılır; çipe basınca o tahtanın sayfası, kat adına basınca listede o grup açılır. Çipteki ek
    işaretler (açık arıza kaydı, sınav kipi) altındaki lejantta açıklanır. 60'tan çok tahtası olan okulda
    çip yerine kat başına tek özet satırı çizilir. Tam liste yalnız Tahtalar'dadır.
  - **Yoklama · bugün:** yalnız sayılar — bugün biten derslerin kaçında yoklama alındığı (her şubenin her
    dersi ayrı sayılır), kaç öğrencinin en az bir derste yok, kaçının geç olduğu ve şube defterine götüren
    şube düğmeleri ("9/A 2/4").
  - **Duyurular:** şu an ekrandaki ve bugün için planlı duyurular (yalnız başlık, kaç tahtaya gönderildiği,
    saat) ve "Duyuru gönder".
- **"Hepsini kilitle…"** Tahtalar kutusunun altındadır. Önce onay penceresi açılır ve kaç tahtanın
  kilitleneceğini söyler ("Çevrimiçi 9 tahta kilitlensin mi? 1 tahta sınav kipinde; atlanacak. 2 tahta
  çevrimdışı; onlara gönderilmez."). Yönetici ve idareci kullanabilir.
- **Menü.** İlk öğe "Bugün", ikincisi "Tahtalar". Telefondaki alt çubuk: Bugün · Tahtalar · Duyurular ·
  Yoklama · Menü. Menüdeki "Tahtalar" rozeti açık arıza sayısını (yöneticide ayrıca onay bekleyen tahta
  sayısını), "Yedekler" rozeti yedek uyarısını gösterir; bu sayılar Bugün'deki satırlarla aynı yerden
  hesaplanır, birbirini tutmaması mümkün değildir.
- **Tahtalar sayfası sadeleşti.** Program şeridi ile yedek, adres, yeni sürüm ve kaçırılan duyuru bantları
  listenin üstünden kalktı (Bugün'e taşındı); liste telefonda daha yukarıdan başlar. Listede kalanlar aşağıdaki
  çizelgededir.
- **Sayfa kendini tazeler.** Şu an satırı, program kilidi, durum kutuları ve çipler dört saniyede bir
  yenilenir. Bekleyen işler değişirse sayfa metni kendiliğinden değiştirmez; "Bekleyen işler değişti. Sayfayı
  yenile" der. Yoklama ve duyuru kutuları sayfa açılırken hesaplanır (yenileyince güncellenir).

## Hangi uyarı nereye gitti

Eskiden (0.17.0) tahta listesinin üstünde duranlar:

| Eskiden listenin üstünde | Şimdi | Kim görür |
|---|---|---|
| Program şeridi: "Şu an: 4. ders · …" | Bugün › Şu an | ikisi |
| Program kilidi rozeti (etkin / durduruldu / kapalı) | Bugün › Şu an | ikisi |
| "N boş ders uyarısı" rozeti | Bugün › Şu an (yanında "Dersin işlenmediği anlamına gelmez.") | ikisi |
| "Program kilidini durdur" (1 saat / bugün) | Bugün › Şu an; Program sayfasında da durur | ikisi |
| "Yedek parolası belirlenmedi; otomatik yedek alınmıyor." | Sizi bekleyenler (kırmızı) → Yedekler | yönetici |
| "Yedek alınmıyor; yöneticiye bildirin." | Sizi bekleyenler (kırmızı), bağlantısız | idareci |
| Son yedek denemesi başarısız | Sizi bekleyenler: "Son yedek alınamadı (son başarılı: …)." | ikisi (bağlantı yalnız yöneticide) |
| Yedek 2 günden eski / henüz yedek alınmadı | Sizi bekleyenler | ikisi (bağlantı yalnız yöneticide) |
| Yedeğin ikinci kopyası yazılamadı | Sizi bekleyenler: "Yedeğin ikinci kopyası yazılamadı." | ikisi (bağlantı yalnız yöneticide) |
| Bu bilgisayarın adresi tahtalara bildirilen listede yok | Sizi bekleyenler → Ayarlar › Sunucu | ikisi (bağlantı yalnız yöneticide) |
| "Tahta Kontrol X yayımlandı (kurulu sürüm Y)." | Sizi bekleyenler → Sürüm sayfası · Ayarlar | yalnız yönetici |
| "Sunucu kapalıyken N zamanlanmış duyuru kaçırıldı." | Sizi bekleyenler → Duyurular | ikisi |
| "Kilit kodu tanımlı değil…" | Sizi bekleyenler **ve** Tahtalar listesinin üstünde (kısa bant) | ikisi (bağlantı yalnız yöneticide) |
| "N yeni tahta onay bekliyor." + tahtaların listesi | Sizi bekleyenler'de yalnız sayı → Tahtalar'daki bant (adlar yalnız orada) | yönetici |
| "N yeni tahta yöneticinin onayını bekliyor." | Sizi bekleyenler (bilgi, bağlantısız); Tahtalar'da da durur | idareci |
| Menüdeki arıza sayısı rozeti | Aynı yerde; ayrıca Sizi bekleyenler: "N arıza kaydı açık." → Arızalar | ikisi |
| "otomatik kapatma: …" özeti ve "Ayarla" | Tahtalar sayfasının başında kaldı | ikisi (bağlantı yalnız yöneticide) |
| "Yeni tahta onaylandı… Sayfayı yenile" bandı | Tahtalar'da kaldı; Bugün'ün kendi "Sayfayı yenile" bandı var | ikisi |
| Acil yayın bandı | Her sayfada, olduğu gibi | ikisi |

Eskiden panoda hiç görünmeyen, Bugün'e **yeni eklenen** satırlar:

| Koşul | Satır | Kim görür |
|---|---|---|
| Öğretim yılı bitiş tarihi girilmedi ya da geçti | "Öğretim yılı bitiş tarihi girilmedi; öğrenci kayıtları kendiliğinden silinmiyor." → Tarihi gir | yönetici |
| Denetlenmiş ya da onaylanmış bir geri yükleme bekliyor | "…geri yükleme onayı bekliyor." / "…program yeniden açılınca uygulanacak." → Yedekler | yönetici |
| Ajanı güncel olmayan tahtalar | "N tahtada ajan güncellenebilir." → süzülmüş liste | ikisi |
| Kurulum listesinde eksik adım (okul adı, zil, derslik, öğrenci listesi, ikinci yönetici) | "Kurulumda N adım eksik." → Ayarlar | yönetici |

Değişen iki şey bilerek yapıldı:

- **Yedek hatasının ayrıntısı Bugün'de yazmaz.** Eskiden bant, hatanın ham metnini basıyordu; bu metin sunucu
  klasörünün yolunu taşıyabilir ve Bugün herkesin görebileceği bir ekrandır. Satır yalnız "alınamadı" der;
  ayrıntı Yedekler sayfasındadır (yönetici). İdareci "Yöneticiye bildirin." notunu görür.
- **"En çok üç bant" sınırı kalktı.** Eskiden üçten fazla altyapı uyarısı varsa fazlası çizilmiyordu; artık
  hiçbir uyarı kesilmez.

Taşıma bekliyor (`TASIMA-BEKLIYOR.txt`) durumunda hizmet hiç açılmadığı için panel de açılmaz; bunun Bugün'de
satırı yoktur, durum penceresi söyler (değişmedi).

## Varsayılan iki karar (geri alınabilir)

Bu iki soru 0.17.0'ın sonunda soruldu; "Bugün'e geç" yanıtı bunları ayrıca kararlaştırmadı. Önerilen
seçenekler **varsayıldı**; ikisi de `docs/tasarim.md` §17'de açık soru olarak durur (soru 80 ve 81).

- **V1 — "Güncelleme var" rozeti tahta listesinin satırlarında çizilmez.** Çok tahtada her satırda yinelenen
  rozet kalabalık ediyordu. Bilgi kaybolmadı: listenin üstündeki "Güncelleme N" süzgecinde, satırın Sürüm
  sütununda (işaretli), tahta sayfasında, Bugün'ün "Güncelleme" kutusunda ve "N tahtada ajan güncellenebilir."
  satırında durur. Program ajanı eski olduğu için program kilidi çalışmayan tahtadaki "Ajan güncellenmeli"
  rozeti satırda **kalır**.
  *Geri almak:* `tahta_sunucu/tahta_liste.py::durum_ozeti` içindeki `rozet["liste"] = False` satırı kaldırılır.
  Başka hiçbir yer değişmez (şablon ve betik yalnız bu alana bakar; `/api/durum` iki durumda da aynıdır).
- **V2 — "Hepsini kilitle" sınav kipindeki tahtaları atlar** ve iletide kaç tahtanın atlandığını söyler
  ("Kilitle: 9 tahtaya gönderildi. 1 tahta sınav kipinde olduğu için atlandı."). Çevrimiçi tahtaların hepsi
  sınavdaysa hiçbir komut gitmez. Sınavdaki tahta satırından ya da işaretlenerek eskisi gibi kilitlenebilir;
  V2 yalnız "hepsi" yolundadır.
  *Geri almak:* `tahta_sunucu/web.py::islem` içinde "V2" yorumlu sınav süzmesi kaldırılır; onay penceresindeki
  "atlanacak" cümlesi ve `bugun.tahta_ozeti`'ndeki `kilit_hedefi` sayımı buna göre düzeltilir.

## Gizlilik

Bugün, odaya giren herkesin omuz üstünden görebileceği bir ekrandır; buna göre yazıldı.

- **Yoklama kutusunda yalnız sayı vardır.** Öğrenci adı, okul numarası, öğretmen adı ya da kodu, kayıt saati,
  mazeret türü yoktur; "devamsızlık" sözü geçmez; "yoklama alınmadı" diye bir uyarı ya da alınmayan derslerin
  listesi yoktur; yalnız bugün gösterilir. Kutu her durumda şu notu taşır: "Tahtadan alınan yoklama kâğıdın
  yanında yardımcı kayıttır. Burada görünmemesi dersin işlenmediği anlamına gelmez."
- **Boş ders uyarısı** yalnız sayıyla ve "Dersin işlenmediği anlamına gelmez." notuyla görünür; tahta, ders
  ve neden Bugün'de yazmaz, bekleyen işler listesine girmez.
- **Duyurunun metni, kimin gönderdiği ve hedef adları** Bugün'de yazmaz (yalnız başlık, tahta sayısı, saat).
- **Arızanın** kategorisi, açıklaması ve hangi tahtada olduğu yazmaz (yalnız sayı).
- **Onay bekleyen tahtanın** adı ve ağ adresi Bugün'de yazmaz (yalnız sayı; adlar Tahtalar'daki bantta ve
  yalnız yöneticiye).
- **İdarecinin sayfasında yöneticiye özel hiçbir satır ve adres yoktur** (Ayarlar, Yedekler, onaylama,
  yeni sürüm). Süzme sunucuda, listeyi üreten tek işlevin içindedir; sayfada gizlenmiş bir şey yoktur.
- **Ders başlığı ve öğretmen bilgisi eklenmedi** (taslağın 75. sorusu onaylanmadı).
- **Yeni sürüm satırı** yalnız yöneticiye çıkar; bağlantı sabit kalıptan kurulur, sürüm notu basılmaz;
  GitHub'a ulaşılamadıysa ya da denetim kapalıysa satır hiç yoktur. Sayfa çizilirken ağ çağrısı yapılmaz.
- Bugün'ün açılması işlem kaydına yazılmaz. Tek ağ bilgisi, 0.17.0'da da aynı metinle duran adres uyarısıdır
  (bu bilgisayarın adresi).
- Mevzuat atfı yoktur.

## Komut güvenliği

- **"Hepsini kilitle…" JavaScript kapalıyken ve Enter'la gönderilmez.** Formda gönder düğmesi, metin alanı ve
  komut türü yoktur; komut türü yalnız onay penceresindeki "Hepsini kilitle" düğmesiyle eklenir. JavaScript
  kapalıysa sayfa bunu bir notla söyler. Vazgeç ve Esc hiçbir şey göndermez.
- Yalnız **onaylı ve o an çevrimiçi** tahtalara gider; sınavdakiler atlanır (V2). Kilitlenecek tahta yoksa
  pencere açılmaz. Bu yolla yalnız kilitleme verilir; kapatma, yeniden başlatma ya da kilit açma verilemez.
- **Acil yayın sürerken düğme çizilmez;** sayfa açıkken acil başlarsa düğme hemen kapanır. (Sunucu ucu acilde
  isteği ayrıca reddetmez; bu 0.17.0'daki davranıştır ve ayrı bir karardır.)
- **"Program kilidini durdur"** eskiden olduğu gibidir: onay sormaz, JavaScript'siz çalışır, iki role açıktır,
  Program › İstisnalar'dan geri alınır.
- 0.17.0'ın kuralları yerindedir: satır düğmesi yalnız kendi tahtasına gider (`tek`), listede Enter komut
  vermez (nöbetçi düğme), kapatma ve yeniden başlatma her zaman onay ister.

## Ne değişmedi

- Veritabanı şeması ve göçler; ajan ve tahta ekranı; komutlar, ömürleri ve adları; var olan gönderim uçları ve
  alan adları. `/islem`'in `kapsam=hepsi` dalına yalnız sınav süzmesi eklendi (V2).
- `/api/durum`: var olan bütün alanlar aynı. Eklenenler: `bekleyen_is` (`sayi`, `imza`; isteği yapanın rolüyle)
  ve rozet sözlüklerinde isteğe bağlı `liste` / `cip` alanları.
- `/tahtalar` adresi, süzgeçler, seçim çubuğu, satır menüsü, tahta sayfasının sekmeleri.
- Eski adresler: `/?durum=kilitli` gibi 0.17.0 yer imleri listeye yönlenir. Başka bölümlerin "bu sayfa için
  yönetici yetkisi gerekir" dönüşleri yine `/`'ye gelir ve ileti Bugün'ün başında görünür.
- Yetki: yönetici/idareci ayrımı aynı; menü ve Bugün yalnız görünümdür, denetim uçlardadır.
- Menüde üç küme ve en çok on öğe kuralı (şimdi tam on öğe: bundan sonra bir öğe eklenirse biri çıkar).
- CSP (satır içi stil ve betik yok), dış kaynak ve derleme adımının olmaması, renk motoru.
- Ajan kodu değişmedi; sürüm statik dosya önbelleği için yükseldi (tahtalar 0.18.0 paketini yine de
  "güncelleme" olarak görür).
- Yoklama / Program / duyuru formu sekmeleri (5. aşama) ve genel arama (6. aşama) bu sürümde yok; ayrı onay
  ister.

## Bilinen sınırlar

- **Sunucu, acil yayın sürerken `kapsam=hepsi` isteğini reddetmez;** yalnız düğme çizilmez. Elle kurulmuş bir
  istek acilde de kilit komutu yazar (tahta acil ekranını yine gösterir). Karar bekliyor (§17, soru 81).
- Toplu kilidin iletisi "Kilitle: 9 tahtaya gönderildi." biçimindedir (bütün komutların 0.17.0'daki ortak
  biçimi); değiştirilmedi.
- Yoklama ve duyuru kutuları canlı değildir; sayfa yenilenince güncellenir.
- Tahtalar sayfasında telefonda sekme şeridi üç satır tutar ve onay bandı uzundur (0.17.0 bileşenleri;
  dokunulmadı).
- İdareci için menüdeki "Bugün" öğesi rozet taşımaz; bekleyen iş sayısı sayfadaki başlıkta yazar.
- Bu aşamada dokunulmayan sayfalarda ölçümün işaretlediği küçük dokunma hedefleri duruyor (zil çizelgesi 8,
  envanter tablosu 13, mazeret 2, şube defteri gün kipi 1).

## Nasıl denendi

- `uv run pytest -q`: 1533 geçti, 11 atlandı (0.17.0: 1446 geçti). `uv run ruff check .`: temiz. Yeni testler: `tests/test_bugun.py` (bekleyen
  işlerin her koşulu ayrı ayrı ve iki rol için; yedek hatasının ham metninin yazılmaması; yeni sürüm satırının
  yalnız yöneticide, sabit bağlantıyla ve ulaşılamayınca hiç çıkmaması; sıra; üçten çok uyarının kesilmemesi;
  menü rozetinin aynı listeden gelmesi; işlem kaydına yazılmaması; tahta özeti sayılarının listeyle aynı
  olması; yoklama özeti sayıları, düzeltme katmanı, mazeret türünün görünmemesi; duyuru özeti; sorgu sayısının
  tahta ve öğrenci sayısından bağımsızlığı) ve `tests/test_bugun_sayfasi.py` (bölümler ve sıra; ileti;
  idareci sayfasında yönetici adresi olmaması; onay bekleyen tahtanın adının hiç yazılmaması; her satırın
  bağlantısının var olan bir sayfa olması; ders başlığı ve öğretmen olmaması; yoklama kutusunda kişi adı
  olmaması ve notun bulunması; duyuru metninin olmaması; "Hepsini kilitle…"nin gönder düğmesi olmaması, türsüz
  isteğin reddi, acilde ve tahta yokken çizilmemesi; V2'nin üç durumu ve yalnız "hepsi" yolunda olması; V1;
  Tahtalar'da taşınan bantların bulunmaması; eski süzgeç adresinin yönlenmesi; `/api/durum` eklemesi).
  `/`'yi açan eski testler, gerçekte neyi sınıyorlarsa ona göre Tahtalar'a ya da Bugün'e uyarlandı; test
  silinmedi.
- Deneme sunucusunda (ayrı veri klasörü, 8797/8798, uydurma veri, benzetilmiş ajanlar) başsız Edge ile
  **gerçek tarayıcıda**, JavaScript açık ve kapalı; komut tablosu okunarak: "Hepsini kilitle…" onayı →
  komut yalnız çevrimiçi ve sınavda olmayan 9 tahtaya gitti, sınavdaki tahtaya gitmedi; Vazgeç, Esc ve Enter
  komut vermedi; JavaScript kapalıyken hiçbir şey gitmedi. "Durdur › 1 saat" JavaScript'li ve JavaScript'siz
  çalıştı. İdarecinin yetkisiz sayfa denemeleri Bugün'de iletiyle açıldı. Sayfa açıkken acil başlatılınca
  toplu kilit kapandı. Bekleyen iş satırlarının her bağlantısı açıldı.
- Gizlilik taraması: iki rolde Bugün'ün gövdesinde ve `/api/durum` yanıtında, tohumdaki 52 uydurma ad, metin
  ve yol parçasından hiçbiri bulunmadı; yoklama kutusunda dört haneli sayı (okul numarası) yok.
- Ölçüm (`scripts/panel_olcum.mjs`): Bugün ve Tahtalar, 1366 px ve 390 px, açık ve koyu: yatay taşma yok,
  kontrast eşiği altı metin 0, küçük dokunma hedefi 0, küçük yazı yok.
- Görüntülere gözle bakıldı: Bugün yönetici (1366 açık ve koyu, 390), Bugün idareci, bekleyen iş yokken boş
  durum, "Hepsini kilitle…" onay penceresi, Tahtalar'ın yeni hâli (1366 ve 390).

## Denenmeyenler

- **Okulun gerçek bilgisayarlarında, gerçek telefonda ve gerçek tahtalarla denenmedi;** kurulu hizmette
  denenmedi, kurucu ve `.deb` bu sürüm için üretilmedi. Toplu kilidin tahtalara inişi yalnız testlerle ve
  benzetilmiş ajanlarla görüldü.
- Yalnız Edge (Chromium) ile denendi; Firefox ve Safari'de denenmedi.
- Gerçek parmakla dokunma ve ekran okuyucu denenmedi.
- Okulun gerçek tahta sayısıyla, gerçek konum bilgileriyle ve gerçek bir günün yoklama kayıtlarıyla
  denenmedi; çipler yalnız uydurma tohumla (on iki onaylı tahta) ve 60'tan çok tahtalı grup görünümü yalnız
  testle görüldü.
- İkili eğitimde (iki devre) akış şeridi yalnız testle sınandı; tarayıcıda görülmedi.
- Sayfanın gün boyu açık kalması (saatlerce canlı tazeleme, gece yarısında gün değişimi) denenmedi.
