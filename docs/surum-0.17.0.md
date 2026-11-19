# 0.17.0 — panel arayüzü 3. aşama: Tahtalar

19 Kasım 2026. Geliştirme kopyası; kurulu hizmet ve bağlı tahta değiştirilmedi, dağıtılmadı.
Denemeler uydurma veriyle ("Örnek Anadolu Lisesi") yapıldı; ekran görüntüsü ve gerçek veri depoya girmedi.
Tasarım ve aşama planı: `docs/tasarim.md` §11.1.

Kullanıcı 0.16.0'ı (Ayarlar) gördü ve 19.11.2026'da "Önce Tahtalar'a geç" diyerek altı aşamalı planın
**3. aşamasına** onay verdi. Bu sürüm yalnız o aşamadır: tahta kartlarından oluşan pano, konuma göre gruplu
bir **tahta listesine**; tek uzun tahta sayfası **dört sekmeye** dönüştü. Komutların kendisi (ne yaptıkları,
ne kadar bekledikleri, kime gittikleri) değişmedi; yalnız **nereden verildikleri** değişti.

## Ne değişti

- **Tahtalar listesi** (`/tahtalar`). Her tahta bir satırdır: ad ve derslik, durum rozetleri, oturum, son
  görülme, ajan sürümü. Satırlar konuma göre (bina · kat) gruplanır; konumu girilmemiş tahtalar "Konumu
  belirtilmemiş" grubunda durur. Dar ekranda satır karta döner; yana kaydırma yoktur.
- **Satırda tek düğme.** Her satırda, tahtanın o anki durumuna göre **en olası tek işlem** durur: açık
  tahtada "Kilitle", kilitli tahtada "Kilidi aç", duyuru gösteren tahtada "Duyuruyu kaldır", ekran
  yardımcısı bağlı olmayan tahtada "Tanıla", sınavdaki tahtada "Sınavı aç" (sınav sayfasına bağlantı).
  Çevrimdışı tahtada ve acil yayın sürerken satır düğmesi yoktur. Bu düğme hiçbir durumda kapatma ya da
  yeniden başlatma olmaz.
- **"⋯" menüsü.** Satırın öbür bütün işlemleri buradadır: Duyuru gönder, Kilitle, Kilidi aç, Duyuruyu
  kaldır, Tanılama çalıştır, Ajanı güncelle, Uzaktan aç (deneysel), Ayrıntı, (yöneticiye) Bilgiler ve
  düzenle, Kapat…, Yeniden başlat…. Kesin etkisiz olan işlem soluk durur ve nedenini yazar ("kilitli
  değil", "ekranda duyuru yok", "güncel", "çevrimdışı"). Çevrimdışı tahtada etkin kalan her işlem akıbetini
  söyler ("10 dk bağlanmazsa düşer", "bağlanınca çalışır").
- **Seçim çubuğu.** Bir ya da birkaç tahta işaretlenince ekranın altında bir çubuk belirir: "3 tahta
  seçili" · Kilitle · Kilidi aç · Duyuru gönder · Diğer (Duyuruyu kaldır, Tanılama çalıştır, Ajanı güncelle,
  Kapat…, Yeniden başlat…) · Seçimi temizle. Tablo başlığındaki kutu görünen bütün tahtaları, grup
  başlığındaki kutu o grubu seçer; Shift ile aralık seçilir. Telefonda çubuk alt menünün üstünde durur.
- **Duruma göre süzgeç.** Listenin üstündeki haplar (Hepsi · Açık · Kilitli · Duyuruda · Ekran sorunu ·
  Çevrimdışı · Güncelleme · Arıza bildirilen) sayılarıyla birlikte durur. Adres `/tahtalar?durum=kilitli`
  biçimindedir ve JavaScript kapalıyken de çalışır. Süzgeç dışında kalan tahta seçilemez ve komut almaz.
- **Duyuru göndermek tek formdan.** Panodaki satır içi küçük duyuru kutusu kalktı. Seçim çubuğundaki ya da
  satır menüsündeki "Duyuru gönder" asıl duyuru formunu açar; seçtiğiniz tahtalar formda **işaretli gelir**
  ("Tüm tahtalar" işaretli gelmez). Seçilenlerden biri sınavdaysa form bunu söyler.
- **Onay bekleyen tahtalar** listenin üstünde ayrı bir bantta durur ve yalnız yöneticiye bağlantı olarak
  çıkar ("adlandır ve onayla"). İdareci yalnız "N yeni tahta yöneticinin onayını bekliyor" cümlesini görür.
  Onay bekleyen tahta listede satır olmaz, seçilemez, komut almaz (eskiden de komut almıyordu).
- **Tahta sayfası dört sekme** (`/tahta/<no>?sekme=…`): **Genel** (durum, bugünkü program satırı, süren
  arızalar, son üç komut) · **Program** (haftalık ızgara, muaf, istisnalar, program kilidini durdurma) ·
  **Bakım** (oturum temizliği, envanter ve demirbaş, arızalar, bağlantı ve ajan, saha tanılaması, son
  komutlar) · **Bilgiler ve düzenle** (yalnız yöneticiye: ad, derslik, konum, şubeler, grup, onay, kaldırma).
  Sayfa başı her sekmede aynıdır: tahtanın adı ve durumu, duruma göre tek düğme, "Duyuru gönder" ve
  "Diğer" menüsü (bütün komutlar + "Oturumu şimdi temizle…").
- **Tahtalar bölümünün sekme şeridi.** Tahtalar · Arızalar · Envanter; yöneticiye ayrıca Gruplar · CSV ile
  içe/dışa aktar · Ajan kurulum paketi. Yan menüde Tahtalar'ın altındaki liste kalktı; arıza sayısı rozeti
  menüdeki "Tahtalar" öğesindedir. "Tahta ekle" düğmesi sayfa başında, yalnız yöneticiye çizilir.
- **Onay penceresi tahtanın adını başlığında taşır** (tek tahtada adı, toplu işlemde sayıyı ve listeyi); tahtada açık oturum varsa ya da
  tahta çevrimdışıysa bunu da yazar.
- Satırdan verilen komutun iletisi ("Kilitle: … tahtasına gönderildi.") sayfa başına ek olarak **o satırda**
  da görünür; sayfa o satırda kalır.

## Hangi işlem nereye gitti

Liste (eski pano):

| Eskiden (pano) | Şimdi | Not |
|---|---|---|
| Tahta kartları | Tahtalar listesinin satırları (konuma göre gruplu) | adres `/tahtalar`; `/` de aynı listeyi çizer |
| Araç çubuğu: Kilitle, Kilidi aç | Satırdaki düğme · satırın "⋯" menüsü · seçim çubuğu | |
| Araç çubuğu: Duyuruyu kaldır, Tanılama, Ajanı güncelle | Satırın "⋯" menüsü · seçim çubuğu › Diğer | duyuru gösteren satırda "Duyuruyu kaldır" tek düğmedir |
| Araç çubuğu: Kapat…, Yeniden başlat… | Satırın "⋯" menüsü · seçim çubuğu › Diğer | onay penceresi ister |
| Araç çubuğu: satır içi "Duyuru gönder" kutusu | "Duyuru gönder" → duyuru formu (tahtalar işaretli gelir) | kutu kalktı |
| "Tümünü seç / Görünenleri seç" | Tablo başlığındaki kutu; grup başlığındaki "grubu seç" | |
| Durum süzgeci (yalnız JavaScript ile) | Haplar; `?durum=` adresiyle, JavaScript'siz de | |
| "Yeni tahtalar onay bekliyor" kutusu | Listenin üstündeki bant (bağlantılar yalnız yöneticiye) | |
| Program şeridi, "Program kilidini durdur", yedek/adres/güncelleme uyarıları | Aynı yerde: listenin üstünde | 4. aşamada "Bugün"e taşınacak |
| Yan menü › Tahtalar › Arızalar, Envanter, Gruplar, Tahta ekle | Tahtalar bölümünün sekme şeridi; "Tahta ekle" sayfa başında | |
| Gruplar sayfasındaki "Tahtaları dışa aktar (CSV)" | Şeritte "CSV ile içe/dışa aktar" | |

Tahta sayfası:

| Eskiden (tek sayfa) | Şimdi | Adres |
|---|---|---|
| Komut çubuğu (8 komut) | Sayfa başı: duruma göre tek düğme + "Diğer" menüsü | her sekmede |
| Tahta bilgileri formu, onaylama, "Tahtayı kaldır…" (yönetici) | Bilgiler ve düzenle | `?sekme=bilgiler` |
| Tahta bilgileri (idarecinin salt okunur gördüğü) | Sayfa başındaki alt satır | her sekmede |
| Durum: son görülme, oturum, ekran yardımcısı, ajan sürümü, sınav, yoklama | Genel › Durum | `/tahta/<no>` |
| Durum: kayıt zamanı, IP · MAC, makine adı, işletim sistemi | Bakım › Bağlantı ve ajan | `?sekme=bakim#baglanti` |
| Yüzer düğme / yoklama / USB anahtar yetenek satırları | Bakım › Bu tahtada neler çalışır? | `?sekme=bakim` |
| Program ızgarası, muaf, istisnalar, "1 saat / bugün durdur" | Program (durdurma, program kilidi açıksa sayfa başında da) | `?sekme=program` |
| Oturum temizliği, "Şimdi temizle…" | Bakım › Oturum temizliği (+ "Diğer" menüsü) | `?sekme=bakim#temizlik` |
| Envanter, "Envanteri yenile", donanım değişti bandı, demirbaş bilgisi | Bakım › Envanter ve demirbaş | `?sekme=bakim#envanter` |
| Arızalar, "Arıza kaydı aç" | Bakım › Arızalar (Genel'de süren arızaların kısa listesi) | `?sekme=bakim#arizalar` |
| Sunucu bağlantısı, saha tanılaması | Bakım | `?sekme=bakim` |
| Son komutlar | Bakım › Son komutlar (Genel'de son üçü) | `?sekme=bakim` |

Her form kayıttan sonra **kendi sekmesine** döner. Onay bekleyen tahtayı yönetici açınca doğrudan Bilgiler
sekmesi (onay formu) gelir. Eski yer imleri çalışır: `/tahta/<no>#program`, `#envanter`, `#arizalar` gibi
adresleri sayfa ilgili sekmeye taşır (JavaScript kapalıysa Genel açılır, sekme bir tık ötededir).

## Komut güvenliği

Bu sürümün asıl riski buydu: komutun yanlış tahtaya ya da istenenden çok tahtaya gitmesi.

- **Satır düğmesi yalnız kendi tahtasına gider.** Satırdaki düğme ve satır menüsü `/islem`'e yeni `tek`
  alanını yollar (`tek=kilitle:5`). Bu alan gelince sunucu **yalnız o tahtayı** işler; o sırada başka tahtalar
  işaretli olsa da onlara komut gitmez, formdaki öbür alanlar okunmaz.
- **Bozuk istek hiçbir yere gitmez.** `tek` alanı bozuksa, iki kez gelmişse, bilinmeyen bir komut
  taşıyorsa ya da tahta onaylı değilse hiçbir komut yazılmaz; sunucu "işaretli tahtalara" düşmez.
- **Kapatma ve yeniden başlatma her zaman onay ister.** Bu düğmeler onay penceresini açar; pencere
  tahtanın adını (toplu işlemde tahtaların listesini) gösterir. **JavaScript kapalıyken bu düğmeler
  çalışmaz** (bilerek: onaysız kapatma olmasın); liste bunu bir notla söyler. Aynısı tahta sayfasındaki
  "Oturumu şimdi temizle…" ve "Tahtayı kaldır…" için de geçerlidir.
- **Enter tuşu komut vermez.** Bir seçim kutusu odaktayken Enter'a basmak, tarayıcıda formun ilk gönder
  düğmesini tetikler; önlem alınmasa bu, listenin ilk satırının düğmesi olurdu (seçilmemiş tahtaya komut).
  Formun ilk gönder düğmesi bu yüzden görünmez ve zararsız bir "nöbetçi"dir; sunucu onu görünce hiçbir komut
  yazmaz ve "Enter tuşu komut vermez; bir komut düğmesine basın." der. JavaScript açıkken sayfa hiç
  gönderilmez.
- **Düğme parmağın altında değişmez.** Liste dört saniyede bir kendiliğinden tazelenir. İmleç ya da odak
  düğmenin üstündeyken düğme değişmez; yeni değişmiş düğme kısa bir süre (0,7 sn) tıklama almaz.
- **Süzgeç dışındaki tahta komut almaz.** Süzgeçle gizlenen satırın kutusu devre dışıdır; önceden
  işaretlenmişse seçimden düşer ve seçim çubuğu bunu söyler.
- **"Hepsini kilitle" için sunucu hazır, düğmesi yok.** `/islem` yeni `kapsam=hepsi` alanını kabul eder:
  yalnız **Kilitle** ile, yalnız **onaylı ve o an çevrimiçi** tahtalara gider; kapatma, yeniden başlatma ve
  öbür komutlar bu yolla verilemez, başka bir hedefle birlikte gelirse reddedilir. Bu sürümde arayüzde bunu
  gönderen bir düğme yoktur; düğme 4. aşamada "Bugün" ekranına gelecek.
- **Dönüş adresi yalnız bu sitenin içidir** (`//başka-site` biçimi artık reddedilir).

Değişmeyenler: komut ömürleri (kapat 2 dakikada düşer), acil yayın ve sınav sürerken tahtanın uyguladığı
kurallar, program kaynaklı kilidin yalnız bunu bilen ajana gitmesi, her duyurunun tek yayın yolundan
çıkması, yönetici ve idarecinin verebildiği komutlar. İşaretli tahtalara toplu komut eskisi gibi çalışır
(çevrimdışı tahtaya verilen komut ömrü boyunca bekler).

## Ne değişmedi

- Veritabanı şeması ve göçler; komutlar, ömürleri ve adları; var olan gönderim uçları ve alan adları
  (`/islem`: `tur`, `tahta`, `donus`; `/tahta/<no>/kaydet`, `/program`, `/temizlik`, `/envanter`,
  `/donanim-goruldu`; `/program/istisna`; `/arizalar`). `/islem`'e yalnız `tek` ve `kapsam` eklendi.
- `/api/durum`: var olan bütün alanlar aynı; her tahtaya yalnız ek bir `liste` alanı geldi (satırın durumu,
  rozetleri ve düğmesi artık sunucuda tek kuralla hesaplanır, tarayıcıda yeniden hesaplanmaz).
- Yetki: yönetici/idareci ayrımı aynı. İdarecinin sayfasında yöneticiye özel hiçbir öğe çizilmez (Tahta
  ekle, Bilgiler ve düzenle, Gruplar, CSV, Ajan paketi; onay bekleyen tahtanın adı ve ağ adresi).
- Ana sayfa adresi `/` çalışmaya devam eder ve aynı listeyi çizer (iki ayrı liste yoktur). 4. aşamada `/`
  "Bugün" ekranı olacak, `/tahtalar` yerinde kalacak.
- **Ajan ve tahta ekranı.** Ajan kodu değişmedi. Sürüm yalnız statik dosya önbelleği için yükseldi
  (`stil.css?v=`, `panel.js?v=`); tahtalar 0.17.0 paketini yine de "güncelleme" olarak görür.
- **Ders başlığı ve öğretmen bilgisi eklenmedi** (taslağın 75. sorusu onaylanmadı): listede ve tahta
  sayfasında yalnız bugün de görünen program durumu satırı vardır.
- CSP (satır içi stil ve betik yok), dış kaynak ve derleme adımının olmaması, renk motoru.
- "Bugün" ekranı, "Hepsini kilitle…" düğmesi, Yoklama/Program/duyuru formu sekmeleri, tahta adına göre
  arama ve genel arama: sonraki aşamalardır, bu sürümde yok.

## Bilinen sınırlar ve geçici durumlar

- **Sınavdaki tahtaya JavaScript kapalıyken "Kilidi aç"** ek onay sormadan gider (ek onay JavaScript
  ister). Satırın tek düğmesi sınavda bağlantı olduğu için bu yalnız "⋯" menüsünden olur; tahta zaten sınav
  ekranını panelden kilit açmayla kaldırmaz (kural 15). Sunucu davranışı 0.16.0 ile aynıdır.
- **`kapsam=hepsi` sınavdaki tahtaları da kilitler** (sunucu `/islem`'de sınav ayrımı yapmaz; bugün de
  yapmıyor). Düğmesi 4. aşamada eklenirken bu karar kullanıcıya sorulacak.
- "Güncelleme var" rozeti güncel olmayan her satırda yinelenir; çok tahtada kalabalık görünür. Görünüm
  kararı gerektirdiği için dokunulmadı.
- Çevrimdışı satırda tek düğmenin yeri boş kalır (rozet "Çevrimdışı" der); yapışkan tablo başlığı kayarken
  grup başlığını yarım kesebilir.
- Telefonda ilk tahta satırına ulaşmak için hâlâ uzun kaydırmak gerekir (sayfa başı, sekme şeridi, uyarı
  bantları, haplar): haplar tek satıra indi ve sayısı sıfır olanlar telefonda çizilmiyor, ama bantlar
  4. aşamada "Bugün"e taşınana kadar listenin üstünde duruyor.
- Çok kısa pencerede (ör. 600 px yükseklik) uzun bir satır menüsü kendi içinde kayar; "Yeniden başlat…"
  erişilebilir kalır.
- JavaScript kapalıyken süzgeç değiştirmek sayfayı yeniler; işaretli seçim kaybolur.
- `/` ve `/tahtalar` bu sürümde eşdeğerdir; menü, kırıntı ve tahta işlerinin dönüşleri `/tahtalar`'ı
  kullanır, öbür bölümlerin "yetkiniz yok" dönüşleri hâlâ `/`'ye gelir.
- Bu aşamada dokunulmayan sayfalarda ölçümün işaretlediği küçük dokunma hedefleri duruyor (zil çizelgesi,
  mazeret, şube defteri gün kipi, envanter tablosu; envanter tablosu 1366 px'te kendi kutusunda yana kayar).

## Taslaktaki sorular

Soru 78 ("Hepsini kilitle kime gitsin?") için taslağın önerisi sunucuda uygulandı: çevrimiçi ve onaylı
bütün tahtalar. Soru 70 ("Ana sayfanın adı"): menüdeki "Tahtalar" artık `/tahtalar`'a gider; `/` 4. aşamaya
kadar aynı listeyi çizer. Soru 75 (panelde ders başlıkları) **onaylanmadı ve uygulanmadı.** Öbür sorular
(`docs/tasarim.md` §17, 70–79) açık duruyor; önerilen seçenekler varsayılır.

## Nasıl denendi

- `uv run pytest -q`: 1446 geçti, 11 atlandı. `uv run ruff check .`: temiz. Yeni testler: `tests/test_tahta_liste.py`
  (durum → düğme çizelgesi, menü pasiflikleri, gruplama, süzgeç, `tek` ve dönüş adresi çözümü),
  `tests/test_tahtalar_sayfasi.py` (komut güvenliği: `tek` ile işaretli liste birlikte gelince yalnız tek;
  bozuk, çift, bilinmeyen `tek`; onaysız tahta; `kapsam=hepsi`'nin çevrimdışı ve onaysızı atlaması, yalnız
  kilitlemeye açık olması; nöbetçi; komut ömürleri; onay isteyen hiçbir düğmenin kendiliğinden gönderilmemesi;
  idareci sayfasında yönetici öğesi olmaması; panodaki her komutun yeni listede bulunması; `/api/durum`
  sözleşmesi) ve `tests/test_tahta_sekmeleri.py` (eski tahta sayfasındaki her alan ve ucun dört sekmenin
  birleşiminde durması, her gönderimin doğru sekmeye dönmesi, ders başlığı ve öğretmen bilgisinin
  bulunmaması, sekme şeridi).
- Deneme sunucusunda (ayrı veri klasörü, 8797/8798, uydurma veri, benzetilmiş ajanlar) başsız Edge ile
  **gerçek tarayıcıda komut denemesi**, JavaScript açık ve kapalı; her adımda komut tablosu okundu (54
  denetimin 54'ü geçti): iki tahta işaretliyken başka satırın düğmesi → yalnız o satır; satırdan "Kapat…"
  onayı → yalnız o tahta, Esc → hiçbir komut; toplu "Kapat" → yalnız seçililer; süzgeçliyken toplu komut →
  yalnız görünen seçililer; JavaScript'siz "Kapat…" hiçbir şey göndermedi; seçim kutusunda Enter (tek kutu,
  iki kutu, grup kutusu, hepsini seç) → hiçbir komut; `kapsam=hepsi` → yalnız çevrimiçi onaylı tahtalar.
- Ölçüm (`scripts/panel_olcum.mjs`): 56 sayfa, 1366 px ve 390 px, açık ve koyu: yatay taşma 0, kontrast
  eşiği altı metin 0, sayfa betiği hatası 0. Tahtalar bölümünün bütün sayfalarında (liste, süzgeçli liste,
  tahta sayfasının dört sekmesi, onay bekleyen tahta, ekle, içe aktar, duyuru ön seçimi) küçük dokunma
  hedefi 0. Satır menüsü 1366x768 ve 390x844'te on iki satırın hepsinde (seçimli ve seçimsiz) kesilmeden
  açıldı.
- Görüntülere gözle bakıldı: liste 1366 ve 390 (açık, koyu), seçim çubuğu, satır menüsü (çevrimdışı satır
  dahil), süzgeç + seçim, satır iletisi, onay penceresi, tahta sayfasının sekmeleri.

## Denenmeyenler

- **Okulun gerçek bilgisayarlarında, gerçek telefonda ve gerçek tahtalarla denenmedi;** kurulu hizmette
  denenmedi, kurucu ve `.deb` bu sürüm için üretilmedi. Komutların tahtaya inişi yalnız testlerle ve
  benzetilmiş ajanlarla görüldü.
- Yalnız Edge (Chromium) ile denendi. "Enter komut vermez" önlemi tarayıcının Enter davranışına bağlıdır;
  Firefox ve Safari'de ayrıca denenmedi (sunucudaki nöbetçi denetimi tarayıcıdan bağımsızdır).
- Gerçek parmakla dokunma (satır menüsü, seçim çubuğu, telefonda kart düzeni) ve ekran okuyucu denenmedi.
- Okulun gerçek tahta sayısıyla ve gerçek konum bilgileriyle (bina, kat) denenmedi; gruplama yalnız uydurma
  tohumla (on iki onaylı tahta, yedi konum grubu, iki onay bekleyen) görüldü.
- Acil yayın sürerken ve sınav sırasında listenin davranışı ağırlıkla testlerle sınandı.
