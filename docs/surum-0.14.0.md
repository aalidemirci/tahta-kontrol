# 0.14.0 — yoklama yeniden tasarımı

18 Kasım 2026. Geliştirme kopyası; kurulu hizmet ve bağlı tahta değiştirilmedi, dağıtılmadı.
Gerçek sınıf listesi, rapor ve ekran görüntüsü depoya/pakete eklenmedi; testler ve denemeler uydurma
verilerle yapıldı. Tasarım ve gerekçeler: `docs/tasarim.md` §14.2.

Kullanıcı isteği (18.11.2026): tahtadaki yoklama ekranı kullanışsızdı (şube seçilince ders saati için
kaydırmak gerekiyordu); öğrenciler numara sırasıyla "numara + ad + soyadın baş harfi" görünsün; şube ve ders
saati seçimi kolay olsun; birinci derste "geç" seçeneği olsun; saate göre o anın dersi seçili gelsin; panelde
yoklama kolay görülsün, mazeret/izin girilebilsin, son beş gün görülsün.

## Tahta (ajan)

- **Tek ekranlık seçim, kaydırma yok.** Üstte öneri ("10/A · 3. ders 09:50–10:30 → Listeyi aç") ve öne
  alınan şubeler (★), ortada şube ızgarası (şube çoksa solda düzey sütunu), sağda ders saatleri. Şimdiki
  ders "● 3. ders · şimdi" diye işaretli ve seçili gelir; şubeye tek dokunuşla liste açılır. 0.13.1'de şube
  elle seçilince ders önerisi atılıyor, ders saati için aşağı kaydırıp ikinci kez dokunmak gerekiyordu.
- **Saate göre ders ön seçimi:** süren ders; yoksa 5 dakika içinde başlayacak; yoksa son 15 dakikada biten
  ders. Teneffüste hangisinin kastedildiği belli değilse liste kendiliğinden açılmaz, "biten 2. ders" /
  "başlayacak 3. ders" tek dokunuşla sorulur. PIN ya da öğretmen USB anahtarından sonra öğretmenin
  programı da ön seçime katılır; tahtanın şubesiyle çelişirse ikisi de tek dokunuşluk seçenek olarak
  sunulur. Program hiçbir şube ya da dersi kapatmaz.
- **Numara sırasıyla liste:** öğrenciler okul no sırasıyla ve "123 Ayşe Y." biçiminde, kaydırmasız
  ızgarada (42'ye kadar 6×7, 48'e kadar 6×8, 56'ya kadar 7×8). 56'dan kalabalık şube sayfalanır; bütün
  sayfalar görülmeden KAYDET çıkmaz. Düğme iki satırdır (üstte numara ve YOK/GEÇ, altta ad); uzun adlarda
  ikinci ad baş harfe iner, soyadın baş harfi kesilmez.
- **Geç:** her devrenin ilk dersinde dokunuş döngüsü var → YOK → GEÇ → var'dır (diğer derslerde var ↔
  YOK). Alt çubuk "Yok · Geç · Derste" sayılarını gösterir. Yeniden açılan listede kayıtlı yok ve geç
  işaretli gelir.
- "Temizle" en solda durur ve iki dokunuş ister. Listeden seçim ekranına dönüp aynı şube ve derse
  gelince işaretler korunur.
- Öğrenci listesi, geç işaretleri, şube önerileri ve belirteç yine yalnız servis belleğindedir; diske,
  günlüğe, tanılamaya yazılmaz. Mazeret, geçmiş günler ve tam soyad tahtaya gönderilmez.

## Panel

- **Şube defteri** (Yoklama › Şube defteri): öğrenci × ders tablosu. Varsayılan görünüm **son beş öğretim
  günüdür** (hafta sonu ve tatil atlanır); her satırda yok/geç sayıları, beş günlük şerit ve alınan
  yoklamalara göre "N gündür derste görülmedi" rozeti. Okul genelinde iki ve daha çok gündür görülmeyenler
  ayrı listede (Günlük görünümden bağlantı). Bu sayılar e-Okul devamsızlık günü değildir.
- **Gün görünümünde düzeltme:** üstte Yok / Geç / Var seçilir, hücreye tıklanır; aynı hücreye yeniden
  tıklamak düzeltmeyi kaldırır. Düzeltme öğretmenin kaydını silmez, ayrı katmanda kim/ne zaman bilgisiyle
  durur. Öğretmenin "yok" ya da "geç"ini "var" yapmak kısa not ister. Yoklaması alınmamış saat hücreden
  doldurulamaz; "Alındı" düğmesi onay sorarak kaydı açar. Bugün ve son 7 gün düzenlenir.
- **Mazeret/izin** (Yoklama › Mazeret/izin): okul numaralarıyla, tarih ya da ders aralığı için izinli,
  raporlu, mazeretli, görevli kaydı; önizleme ve onay iki adımdır. Serbest açıklama alanı yoktur; isteğe
  bağlı "dayanak" sabit seçeneklerdendir. Mazeretli yokluk defterde, icmalde ve CSV'de tek "Ö" (özürlü)
  olarak görünür; tür yalnız mazeret sayfasında ve öğrenci görünümünde yazar. Mazeret öğretmenin kaydını
  değiştirmez; kaldırılınca asıl durum geri görünür.
- İcmal ve CSV'de G (geç) ve Ö (özürlü yok) hücreleri; CSV'nin sonuna "Geç Sayısı" ve "Özürlü Yok Sayısı"
  sütunları eklendi (var olan sütunların sırası değişmedi). "e-Okul'a işlendi" işareti, sonradan kayıt,
  düzeltme ya da mazeret değişirse "İşlendikten sonra değişti" olur.
- Şube defteri A4 yatay yazdırılır. Beş günlük görünüm, son günler listesi, öğrenci görünümü ve mazeret
  listesi dışa aktarılmaz.

## Davranış değişiklikleri (bilmeniz gerekenler)

- **Tahtada numara ve ad birlikte görünür.** Yeni varsayılan "123 Ayşe Y."dir ve kayıtlı "Ayşe Y." ayarı
  yükseltmede buna çevrilir. Etiketi sunucu kurduğu için **güncellenmemiş (eski ajanlı) tahtalar dahil
  bütün tahtalarda numara görünür.** Eski biçimler Ayarlar › Ders yoklaması'ndan tek seçimle geri gelir.
  Tam soyad ve T.C. kimlik no tahtaya hiçbir biçimde gitmez; sınav ekranlarının maskesi değişmedi.
- **Aynı ders saatinin iki kaydı artık birleştirilmez; en son kaydedilen geçerlidir.** Tahta listeyi o
  ders saatinin geçerli durumuyla açtığı için sonraki kayıt öncekinin işaretlerini taşır. Günlük
  görünümdeki "×2 birleştirildi" yazısı "2 kayıt; en son kaydedilen geçerli" oldu.
- **İdare düzeltmesi ile öğretmen kaydı arasında "en son işlem geçerlidir".** Şube defterinde düzeltme
  yapıldıktan sonra öğretmen aynı ders saatini tahtadan yeniden kaydederse öğretmenin son kaydı geçerli
  olur (liste düzeltilmiş durumla açıldığı için düzeltme kaybolmaz, öğretmen onu bilerek değiştirebilir).
  Şartnamede idare düzeltmesinin her zaman üstte kalması yazılıydı; öğretmene "Kaydedildi" denip kaydının
  gösterilmemesi sorununu önlemek için bu yol seçildi. Karar kullanıcıya sorulacak (`docs/tasarim.md` §17
  soru 65).
- Kayıt ayrıntısındaki "Düzelt" ile eski bir kayıt düzeltilince o kayıt en yeni olur ve o ders saatindeki
  öbür kaydın ve panel düzeltmelerinin üstüne geçer; hücre düzeltmesi için şube defteri kullanılır.
- Bir kayıt silinip o ders saatinin başka kaydı kalmazsa o saatin panel düzeltmeleri de silinir.
- Teneffüste, öğle arasında biten ders eski ajanlı tahtaya artık önerilmez (yeni ajanda iki aday sorulur).
- Geç yalnız devrenin ilk dersinde işaretlenir; sunucu başka derste geçi reddeder.

## 0.13.x'ten yükseltirken

1. Önce şifreli yedek alın. Veritabanı şeması değişir (yeni tablolar: geç, panel düzeltmesi, mazeret);
   göç öncesi kopya her zamanki gibi veri klasöründe `goc-oncesi` altında kalır.
2. Sunucu yükseldikten sonra tahtalar açıldıkça ajan güncellemesini kendiliğinden alır; **yeni yoklama
   ekranı ajan güncellenince gelir.** Yeni ekran yardımcısı için tahtada oturum yeniden açılır.
3. Güncellenmemiş tahtada eski ekran çalışmaya devam eder: numara yine görünür, "geç" sunulmaz; başka
   tahtadan geç yazılmış öğrenci "(geç)" ekiyle görünür ve eski tahtadan kaydedilince geçi silinmez.
4. Yeni tahta ajanı eski sunucuyla da çalışır (geç sunmaz, eski öneri davranışı).
5. Ayarlar › Kişisel veri saklama'da öğretim yılı bitiş tarihi girili değilse girin: geç, düzeltme ve
   mazeret kayıtları da yıl sonu silmesine bağlıdır.
6. Önce tek tahtada deneyin: `docs/saha-denemesi.md` §3.14.

## Doğrulama

- `uv run pytest -q`: 1143 geçti, 11 atlandı (Windows'ta PyGObject olmadığı için gerçek GTK testleri
  atlananlar arasında). `uv run ruff check .`: temiz.
- Tahta: Debian 12 kabında (Xvfb + Openbox, gerçek GTK) `scripts/ekran_olcum.py` 19 yoklama senaryosu —
  40 ve 60 şube, 12 ders saati, teneffüs (iki aday), ikili eğitim, saatsiz, 30/42/48/56/70 öğrenci, 4 haneli
  numara + uzun adlar, ilk ders (geç), eski sunucu biçimi — 1024×768, 1366×768, 1920×1080 ve 3840×2160'ta:
  hepsi sığdı, kaydırma alanı ve kesik etiket yok. En küçük öğrenci düğmesi 1920×1080'de yaklaşık 250×74,
  1366×768'de 177×52 pikseldir (56 kişi).
- Panel: deneme sunucusunda (ayrı veri klasörü, 8797/8798; uydurma 2 şube × 35 öğrenci × 6 gün) tarayıcıda
  şube defteri (beş gün ve gün kipi), fırçayla düzeltme (yok yaz, kaldır, notsuz ve notlu var), "Alındı",
  mazeret önizle → kaydet, son günler ve öğrenci görünümü denendi. 8 ders × 5 gün 1366×768'de yatay
  kaydırmasız; 800 px genişlikte taşma yok. Şube defterinin yazdırma çıktısı başsız tarayıcıyla PDF'e
  alınıp bakıldı (A4 yatay, beş gün ve sayılar sayfada).
- Eski ajan uyumu: 0.13.1 ajanının yanıt çözücülerinin sabitlenmiş kopyası testte 0.14.0 yanıtlarını okur.

## Denenmeyenler ve bilinen sınırlar

- **Gerçek ETAP tahtasında ve gerçek sınıfta denenmedi:** parmakla dokunma, arka sıradan okunurluk,
  yoklamanın gerçekte ne kadar sürdüğü ölçülmedi. Gerçek e-Okul sınıf listesiyle denenmedi. Portre ekran
  yerleşimi yalnız ölçümle görüldü. Kurucu ve `.deb` bu sürüm için üretilmedi.
- Tahtada "Temizle"nin iki dokunuşu ve "bitti" yazısı gerçek dokunuşla uçtan uca denenmedi (saf işlevleri
  testte, yerleşimi ölçümde).
- Panel açık temada, telefon genişliğinde (390 px), JS kapalı tarayıcıda ve ekran okuyucuyla denenmedi
  (JS'siz yol testlerle ve form gönderimiyle doğrulandı); gerçek yazıcı önizlemesi açılmadı.
- Beş gün görünümünde ad sütunu dardır: uzun soyad üç noktayla kesilir, tam ad ipucundadır. Plan dışı bir
  dersle 40 sütunu aşan şubede tablo 1366 px'te kendi kabında yatay kayar.
- Hücreler arasında ok tuşlarıyla gezilir; sekme (Tab) sırası kısaltılmadı.
- Üstüne tahtadan yeni kayıt gelen düzeltme hücrede işaretlenmez; izi yalnız veritabanındaki düzeltme
  tablosundadır.
- Uygulanmayanlar: rehberlik/idari görüşme, nöbetçi ve faaliyet kategorileri, ders arası yokluk uyarısı,
  tahtada idari etiket (`docs/yoklama-yonetimi-tasarimi.md` başındaki not).
- Geliştirici yönergesi (`CLAUDE.md`) bu sürümde değiştirilmedi: tahtada ad ile numaranın birlikte
  görünmesine ilişkin kural 18 metninin güncellenmesi depo sahibinin onayını bekliyor.
