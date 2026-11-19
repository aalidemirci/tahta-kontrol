# 0.19.0 — panel arayüzü 5. aşama: bölüm sekmeleri ve tek sayfalık duyuru formu

19 Kasım 2026. Geliştirme kopyası; kurulu hizmet ve bağlı tahta değiştirilmedi, dağıtılmadı.
Denemeler uydurma veriyle ("Örnek Anadolu Lisesi") yapıldı; ekran görüntüsü ve gerçek veri depoya girmedi.
Tasarım ve aşama planı: `docs/tasarim.md` §11.1.

Kullanıcı 0.18.0'ı (Bugün) gördü ve 19.11.2026'da "Sekmelere geç" diyerek altı aşamalı planın
**5. aşamasına** onay verdi. Bu sürüm yalnız o aşamadır: Yoklama, Program, Duyurular ve Acil durum
bölümlerinin sayfa içi sekme şeritleri yeniden düzenlendi, kişi sayfaları kendi şeridini aldı ve yeni duyuru
formu tek sayfada üç adıma (Ne yazılsın · Kime · Ne zaman) dizildi.

**Hiçbir adres değişmedi, hiçbir adres kalkmadı, hiçbiri yönlenmiyor.** Eski yer imleri aynı sayfayı yeni
şeritle açar. Sayfaların içeriği (tablolar, formlar, notlar) yerinde durur; değişen yalnız sayfa başındaki
şerit ve aşağıdaki çizelgede yazan birkaç taşımadır.

Taslağın açık sorularında ve bu aşamada doğan yeni sorularda **önerilen seçenek varsayıldı**; hepsi aşağıda
"Varsayılan kararlar" başlığında, nasıl geri alınacağıyla birlikte yazılıdır.

## Ne değişti

- **Yoklama şeridi sadeleşti:** Günlük · Şube defteri · Mazeret ve izin · Panelden gir · Devamsızlık icmali
  ve (yalnız yöneticiye) "Yoklama ayarları ↗". Kişilerle ilgili üç sayfa ve öğretmen programı bu şeritten
  çıktı (aşağıda).
- **"Kişiler ve anahtarlar" kendi şeridini aldı:** Öğrenciler · Öğretmenler ve PIN · USB anahtarlar. Menüdeki
  öğe aynıdır (menü yine tam on öğe); bu üç sayfa artık Yoklama şeridini değil kendi şeridini çizer.
- **Program şeridi üç kümeye ayrıldı:** Günü önizle · Zil saatleri · Derslik programları · Öğretmen
  programı* | Kurallar · İstisnalar · Uyarılar | İçe aktar* · Önceki programlar*. Yıldızlılar yalnız
  yöneticiye çizilir. Günlük iş solda, kurulum işleri çizgiyle ayrılmış sağdadır; idarecide son küme hiç
  olmadığı için onun çizgisi de çizilmez.
- **Duyurular şeridi:** Duyurular ve planlar · Yeni duyuru.
- **Yeni duyuru tek sayfalık form:** "1. Ne yazılsın?", "2. Kime?", "3. Ne zaman?" alt alta; geniş ekranda
  yanda "Tahtada böyle görünür" önizlemesi; ekranın altında, ne gönderileceğini özetleyen gönder çubuğu
  ("4 tahtaya · 20.11.2026 10:00 · 5 dk ekranda · öğretmen kapatabilir"). Ayrıntısı aşağıda.
- **Acil durum şeridi:** Yayın başlat · Geçmiş ve raporlar | Şablonlar*. Geçmiş tablosu başlatma formunun
  altından kendi sekmesine (`/acil?sekme=gecmis`) indi. Şerit artık idareciye de çizilir (iki sekme).
- **Tahtalar şeridi** aynı görünür; yalnız çizimi öbür şeritlerle ortak kalıba alındı.
- **Şeritler dar ekranda sarar** (yana kaydırmaz, sayfayı genişletmez); kümeler arasındaki çizgi telefonda
  satır başına döner. Her sayfada içinde bulunulan sekme işaretlidir (ekran okuyucuya da bildirilir).

## Hangi sayfa ve sekme nereye gitti

| Eskiden (0.18.0) | Şimdi | Kim görür |
|---|---|---|
| Yoklama › Günlük görünüm | Yoklama › Günlük | ikisi |
| Yoklama › Şube defteri | aynı | ikisi |
| Yoklama › Mazeret/izin | Yoklama › Mazeret ve izin | ikisi |
| Yoklama › Panelden gir | aynı | ikisi |
| Günlük'ün araç çubuğundaki "İcmal" düğmesi | yerinde durur; ayrıca Yoklama › Devamsızlık icmali sekmesi | ikisi |
| Günlük'ün araç çubuğundaki "Son günler" | yerinde durur; sayfa artık Şube defteri'nin altındadır (şeritte Şube defteri işaretli, geri bağlantısı "← Şube defteri") | ikisi |
| Şube defteri › "Okul geneli son günler" | yerinde durur | ikisi |
| Yoklama › Öğretmenler ve PIN | Kişiler ve anahtarlar › Öğretmenler ve PIN | ikisi |
| Yoklama › Öğrenci listesi | Kişiler ve anahtarlar › Öğrenciler | ikisi |
| Yoklama › USB anahtarlar | Kişiler ve anahtarlar › USB anahtarlar | ikisi |
| Yoklama › Öğretmen programı | Program › Öğretmen programı (yalnız orada) | yönetici |
| (yoktu) | Yoklama › Yoklama ayarları ↗ (Ayarlar › Yoklama'ya götürür) | yönetici |
| Program › Zil saatleri, Derslik programları, Kurallar, İstisnalar, Uyarılar | aynı adlarla | ikisi |
| Zil saatleri'ndeki "Başka bir günü önizle" | yerinde durur; ayrıca Program › Günü önizle sekmesi | ikisi |
| Derslik programları'ndaki "Ders programını içe aktar" düğmesi | yerinde durur; ayrıca Program › İçe aktar sekmesi | yönetici |
| Derslik programları'nın altındaki "Önceki programlar" kutusu | Program › Önceki programlar sekmesi (liste ve "Geri yükle" yalnız orada) | yönetici |
| Duyurular › "Yeni duyuru" düğmesi | yerinde durur; ayrıca Duyurular › Yeni duyuru sekmesi | ikisi |
| Acil › başlatma formu | Acil › Yayın başlat (aynı) | ikisi |
| Acil › sayfanın altındaki Geçmiş tablosu | Acil › Geçmiş ve raporlar | ikisi |
| Acil › Şablonlar | aynı | yönetici |
| Süren yayın kutusu ("Yayını bitir…", "Rapor") | Yayın başlat **ve** Geçmiş ve raporlar sekmelerinde | ikisi |

Notlar da yerinde: kişi sayfalarındaki KVKK bandı, yoklama sayfalarındaki "yardımcı kayıt" notu, boş ders
uyarısındaki "dersin işlenmediği anlamına gelmez" notu, duyuru formundaki "Tahta bütün sınıfa açık
ekrandır…" uyarısı ve JavaScript kapalıyken çıkan notlar.

## Duyuru formu: ne değişti, ne değişmedi

Duyuruda en pahalı hata yanlış tahtaya ya da yanlış zamanda yayındır. Bu yüzden **sunucu tarafı aynen
bırakıldı;** değişen yalnız sayfanın dizilişidir.

Değişmeyenler:

- Form tek formdur ve aynı adrese gider (`POST /duyurular`; plan düzenlemede `POST /duyurular/plan/<no>`).
- Alan adları aynıdır: `baslik`, `metin`, `sure_dk`, `kapatilabilir`, `kime`, `bina`, `kat`, `duzey`, `devre`,
  `grup`, `hedef_tahta`, `zaman` (`hemen` / `bir_kez` / `tekrarli`), `bir_tarih`, `bir_saat`, `siklik`,
  `hafta_sonu`, `gun`, `tekrar_saat`, `baslangic`, `bitis`.
- Doğrulama, iletiler ve varsayılanlar aynıdır: süre 5 dakika, "Öğretmen tahtadan kapatabilsin" işaretli,
  "Tüm tahtalar" seçili, zaman "Hemen". T.C. kimlik numarasına benzeyen sayı yine reddedilir.
- "Hemen" seçiliyken plan alanları, plan seçiliyken öbür zamanın alanları dikkate alınmaz (eskisi gibi).
- JavaScript kapalıyken form eksiksiz çalışır: bütün bölümler ve üç zaman bloğu görünür, düğme
  "Yayımla ya da planı kaydet" yazar ve altında hangi seçimin geçerli olduğunu anlatan not çıkar.
- "Kaç tahtaya ulaşır" önizlemesi ve Tahtalar sayfasından seçimle gelme (0.17.0) çalışır; seçim boş
  gelirse form yine "Tüm tahtalar"a düşmez.
- KVKK uyarısı ve "Öğretmen tahtadan kapatabilsin" kutusu formdadır.

Değişenler (yalnız görünüm):

- Sıra artık Ne · Kime · Ne zaman'dır (eskiden İçerik ve Ne zaman yan yana, Kime altta idi).
- "Kime"de Gruplar öne alındı; bina, kat, düzey ve devre tek bir açılır başlığın altında toplandı (seçim
  varsa açık gelir; kapalıyken de içindeki işaretler gönderilir).
- Süre için "5 dk · 15 dk · 40 dk", tek seferlik plan için "Bugün · Yarın" hızlı düğmeleri (yalnız
  JavaScript açıkken; tarih sunucunun bugününden hesaplanır, tarayıcının saatinden değil).
- **Gönder çubuğu** ekranın altında durur (telefonda alt çubuğun üstünde) ve göndermeden önce kaç tahtaya,
  ne zaman, kaç dakika gideceğini yazar. Hedef değişince sayı önce "Tahta sayısı hesaplanıyor…" olur; ağ
  hatasında "Tahta sayısı alınamadı" yazar, eski sayı ekranda kalmaz. Eksik alan açıkça söylenir ("bitiş
  seçilmedi", "tarih ve saat seçilmedi"). Düğme "Hemen"de "Şimdi yayımla", planda "Planı kaydet" yazar.
- Tekrarlı planda bitiş alanının etiketi "Bitiş (zorunlu)" oldu (kural aynı; yalnız etiket açık söylüyor).
- Doğrulama iletisi sayfa başına ek olarak ilgili bölümün (Ne · Kime · Ne zaman) içinde de çizilir;
  JavaScript varsa sayfa oraya kayar, yoksa sayfa başındaki bağlantı götürür.

## Varsayılan kararlar (geri alınabilir)

Taslağın daha önce sorulmuş sorularında önerilen seçenekler sürüyor: Yoklama'ya tıklayınca Günlük açılır
(soru 74), menüdeki ad "Kişiler ve anahtarlar"dır (soru 77; taslakta "Okul verisi" de geçiyordu), genel arama
son aşamadadır (soru 72). **Soru 75 onaylanmadı:** hiçbir sayfaya ders başlığı ya da öğretmen bilgisi
eklenmedi.

Bu aşamada doğan ve ayrıca sorulmayan kararlar; hepsinde önerilen seçenek **varsayıldı** ve `docs/tasarim.md`
§17'de açık soru olarak durur (soru 82–90):

| No | Varsayılan | Geri almak / değiştirmek |
|---|---|---|
| 82 | "Tüm tahtalar + hemen" için ek onay penceresi yok; önlem gönder çubuğundaki özettir | Onay istenirse sunucuda iki adımlı onay gerekir (JavaScript'siz gönderim bozulmasın diye); ayrı iş |
| 83 | "Hemen" seçiliyken dolu plan alanları (ve tersi) reddedilmez, yok sayılır | Reddetmek sunucu doğrulamasını değiştirir; ayrı karar |
| 84 | "Son günler" ayrı sekme değil; Şube defteri'nin altında, iki girişle | `bolum_serit.py`'de Yoklama şeridine bir satır + şablonda `bolum` |
| 85 | Menüde Program'a tıklayınca Zil saatleri açılır (eskisi gibi) | `web.py::MENU`'de Program öğesinin `yol`'u `/program/gun` yapılır |
| 86 | Derslik'teki "Önceki programlar" kutusu kalktı; yalnız sekmede | Kutu `program.html`'e geri konur (liste `program_aktar.surum_listesi`) |
| 87 | Acil şeridi idareciye de çizilir (iki sekme) | Geçmiş ayrı sekmede olduğu için gerekli; geri almak geçmişi de geri taşımaktır |
| 88 | Sekme adları taslaktaki gibi ("Günlük", "Mazeret ve izin", "Öğrenciler") | Adlar yalnız `bolum_serit.py`'dedir |
| 89 | Dar ekranda şerit sarar (yana kaymaz), sayfaya yapışmaz | `stil.css` "0.19.0" bloğu; yana kaydırma sayfa genişliği tuzağına dikkat ister |
| 90 | İcmal sekmesi her açılışta işlem kaydına bir satır düşer (eski davranış; sekme olduğu için daha sık açılabilir) | Kayıt istenmiyorsa `panel_yoklama.py`'deki icmal görüntüleme kaydı kaldırılır; ayrı karar |

## Gizlilik ve yetki

- **Şerit yalnız görünümdür.** Her sayfanın yetki denetimi eskisi gibi kendi ucundadır; idareci yönetici
  sayfasının adresini elle yazarsa yine reddedilir.
- **Yöneticiye özel sekmeler idarecinin sayfasında hiç yoktur** (gizlenmiş değil, çizilmemiş): Yoklama
  ayarları, Öğretmen programı, İçe aktar, Önceki programlar, Acil şablonları, Gruplar, CSV, Ajan paketi.
- Taşınan sayfaların gizlilik davranışı aynıdır: şube defteri, son günler, mazeret ve öğrenci görünümü
  önbelleğe alınmaz; PIN yalnız pusula yanıtında görünür; USB anahtar dosyası tek seferlik iner; mazerette
  serbest metin yoktur; öğretmen programı önizlemesi yalnız bellekte ve kısa ömürlüdür.
- Acil yayını başlatmak yine parola ve onay kutusu ister; bütün yönetici ve idareciler başlatabilir.
- Ders başlığı ve öğretmen bilgisi hiçbir sayfaya eklenmedi (soru 75).
- Mevzuat atfı yoktur.

## Ne değişmedi

- Veritabanı şeması ve göçler; ajan ve tahta ekranı; komutlar, ömürleri ve adları.
- Bütün adresler; var olan gönderim uçları, alan adları ve doğrulamaları. Sunucuya eklenen tek şey görünüm
  bilgisidir: duyuru doğrulama iletisinin hangi bölümde çizileceği ve Acil sayfasında `?sekme=gecmis`.
- Öğretmen programı sayfasının yetkisiz dönüşü artık Program'a gider (eskiden Yoklama'ya); uç ve yetki aynı.
- Menü: üç küme, tam on öğe; telefon alt çubuğu Bugün · Tahtalar · Duyurular · Yoklama · Menü.
- Sayfa içerikleri: yoklama, program, kişi ve duyuru listesi sayfaları yeniden tasarlanmadı.
- CSP (satır içi stil ve betik yok), dış kaynak ve derleme adımının olmaması, renk motoru.
- Ajan kodu değişmedi; sürüm statik dosya önbelleği için yükseldi (tahtalar 0.19.0 paketini yine de
  "güncelleme" olarak görür).
- Genel arama (6. aşama) bu sürümde yok; ayrı onay ister.

## Bilinen sınırlar

- **Telefonda şeritler birkaç satır tutar:** 390 px'te yöneticide Program 4, Yoklama 3, Kişiler 2, Acil 2
  satır; idarecide Program 2, Yoklama 2. Yana kaydırma bilerek yapılmadı (gizli kalan sekme fark edilmez,
  taşan şerit sayfayı ve alt çubuğu genişletir). Kısaltmak isterseniz sekme adları ya da sayısı değişmeli.
- **"Günü önizle" iki yerde:** hem kendi sekmesi hem Zil saatleri'ndeki küçük form. Biri kaldırılabilir;
  karar bekliyor.
- "Bir kez"te tarih ve saat kendiliğinden dolmaz (kullanıcı seçmeden değer yazılmasın diye); "Bugün" ve
  "Yarın" düğmeleri yalnız tarihi doldurur.
- Telefonda gönder çubuğunda "Vazgeç" düğmesi JavaScript açıkken gizlidir (yer açmak için); aynı adres
  şeritteki "Duyurular ve planlar"dır.
- Bazı sayfa başlıkları ve bağlantı metinleri eski adlarıyla kaldı ("Öğrenci listesi", "Panelden yoklama",
  Bugün'deki ve şube defterindeki "Günlük görünüm" bağlantısı).
- Önceki programı geri yükledikten sonra sayfa Derslik programları'na döner (0.18.0'daki gibi).
- Plan düzenleme adresine elle `zaman=hemen` gönderilirse hata çiziminde "Bir kez" işaretli gelir (0.18.0'daki
  gibi; plan sayfasında "Hemen" seçeneği yoktur).
- Aynı duyuru iki kez gönderilirse (çift tıklama) iki yayın oluşur; bu sürümden önce de böyleydi.
- Bu aşamada dokunulmayan küçük dokunma hedefleri ve kapalı açılır başlıkların açma işareti duruyor.

## Nasıl denendi

- `uv run pytest -q`: 1583 geçti, 11 atlandı (0.18.0: 1533 geçti). `uv run ruff check .`: temiz. Yeni testler:
  `tests/test_bolum_serit.py` (şeridin tek tanımı ve rol süzmesi; 28 adreste doğru sekmenin ve doğru menü
  öğesinin işaretli olması; idareci sayfasında yönetici sekmesinin adının ve adresinin bulunmaması; şerit
  çizen her sayfanın menüde doğru bölümde olması; dönüş adresleri; uyarı rozeti; önbelleğe alınmayan
  sayfalar; dar ekran kuralları), `tests/test_duyuru_formu.py` (bölüm sırası; alan adlarının eksiksizliği;
  varsayılanlar; her zaman kipi için sayfanın çizdiği alanlarla uçtan uca gönderim — hemen, bir kez, günlük,
  haftalık; öbür zamanın dolu alanlarının yok sayılması; işaretsiz kutular; seçimden ön doldurma; hata
  çiziminde değerlerin korunması ve iletinin doğru bölümde çıkması; plan sayfası) ve `tests/test_acil.py`'ye
  üç sekme testi. Eski testlerden şeridin yerini ya da "Önceki programlar" kutusunu arayanlar, gerçekte neyi
  sınıyorlarsa ona göre uyarlandı; test silinmedi.
- Deneme sunucusunda (ayrı veri klasörü, 8797/8798, uydurma veri, benzetilmiş ajanlar) başsız Edge ile
  **gerçek tarayıcıda** duyuru gönderildi ve sonuç veritabanından okundu; yalnız beklenen hedef ve plan oluştu:
  - JavaScript açık: hemen + bir kat → o kattaki 4 tahta; bir kez (yarın 10:00) + grup → tek plan; günlük
    08:20 + tüm tahtalar → hafta içi planı; haftalık Pzt ve Per 13:00 + iki tahta → gün ve tahta listesi
    doğru. Bitişsiz tekrarlı plan ve boş seçim reddedildi, ileti ilgili bölümde göründü, kayıt oluşmadı.
  - JavaScript kapalı: hemen + bir düzey → 2 tahta; bir kez + bir bina (tekrarlı alanları dolu bırakılarak) →
    yalnız tek seferlik plan; günlük + hafta sonu + grup (bir kez alanları dolu bırakılarak) → yalnız günlük
    plan; hemen + tüm tahtalar, kapatılamaz (bir tahta kutusu işaretli unutulmuşken) → 12 tahta, kapatılamaz;
    tarihsiz bir kez → reddedildi, ileti "3. Ne zaman?" içinde.
- Ölçüm (başsız Edge; 29 adres, yönetici ve idareci, 1366 px ve 390 px, açık ve koyu): yatay taşma yok, alt
  çubuk taşması yok, içerikte kontrast eşiği altı metin yok. Şeritler 1366 px'te tek satır; 390 px'te sekme
  yüksekliği 44 px. Duyuru formunda 1366x768'de gönder düğmesi kaydırmadan görünür; 390 px'te gönder çubuğu
  alt çubuğun üstünde durur.
- Görüntülere gözle bakıldı: Yoklama günlük, Kişiler ve anahtarlar, Program (yönetici ve idareci), yeni
  duyuru formu, Acil — 1366 px; Yoklama ve duyuru formu — 390 px.

## Denenmeyenler

- **Okulun gerçek bilgisayarlarında, gerçek telefonda ve gerçek tahtalarla denenmedi;** kurulu hizmette
  denenmedi, kurucu ve `.deb` bu sürüm için üretilmedi. Duyuruların tahtaya inişi yalnız testlerle ve
  benzetilmiş ajanlarla görüldü.
- Yalnız Edge (Chromium) ile denendi; Firefox ve Safari'de denenmedi (tarih ve saat alanları tarayıcıya göre
  farklı görünür).
- Gerçek parmakla dokunma ve ekran okuyucu denenmedi.
- Okulun gerçek tahta, grup ve bina sayısıyla denenmedi; "Kime" bölümünün çok gruplu, çok tahtalı okuldaki
  boyu yalnız uydurma tohumla (on iki tahta) görüldü.
- Planlı duyurunun saati gelince yayımlanması bu sürümde yeniden beklenerek denenmedi (zamanlayıcı
  değişmedi; var olan testleri geçiyor).
- Acil yayın gerçek tahtalarda başlatılmadı; sekmeler yalnız testle ve deneme sunucusunda görüldü.
