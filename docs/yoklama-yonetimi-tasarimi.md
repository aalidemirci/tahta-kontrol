# Yoklama yönetimi — taslak (uygulanmadı)

> **Taslak, uygulanmadı.** Bağlayıcı kararlar `docs/tasarim.md` §17'dedir; ders yoklamasının
> yürürlükteki tasarımı §14'tür ("yalnız yok" işareti, kategori tutulmaz). Bu belge onları
> değiştirmez; aşağıdakiler ancak §14 ve §17 açıkça güncellenirse uygulanır.

17 Kasım 2026. Canlı uygulamanın veritabanı, ajanı ve icmal hesaplaması bu özellikler için
değiştirilmedi.

## Taslaktaki kurallar

| Bilgi | İdare paneli | Tahtadaki yoklama ekranı | Devamsızlık toplamı |
|---|---|---|---|
| Var | Görünür | O ders için seçilebilir | Dahil değil |
| Yok | Görünür | O ders için seçilebilir | Dahil |
| Geç | Ayrı işaret ve sayaç | O ders için seçilebilir | Ayrı geç sayacı; kendiliğinden yok veya yarım gün yapılmaz |
| İzinli | Görünür | Gönderilmez | Dahil |
| Rehberlik Görüşmesi | Görünür | Gönderilmez | Ayrı tutulur |
| İdari Görüşme | Görünür | Gönderilmez | Ayrı tutulur |
| Nöbetçi | Görünür | Yalnız ilgili derste etiket | Ayrı tutulur |
| Faaliyet | Görünür | Yalnız ilgili derste etiket | Ayrı tutulur |

Geç sayacının resmi kayda nasıl işleneceği için mevzuat yorumu veya otomatik
gün dönüşümü yapılmaz. e-Okul'a giriş yine idarece elle yapılır; yardımcı kayıt
niteliği korunur. Sağlık bilgisi, görüşme içeriği veya izin gerekçesi alınmaz.
Görüşme kategorileri yalnız idare panelinde korunur.

## Ekran ve iş akışı

- İdarede tarih/şube/devre seçilir; satırlarda öğrenciler, sütunlarda dersler.
  Öğretmenin orijinal kaydı ile idarenin eklediği durum ayrı tutulur.
- Tek veya çok sayıda ders hücresi seçilip beş idari durumdan biri uygulanır.
  İlk hücre ve Shift+tıklanan son hücre arasındaki dikdörtgen alan seçilir;
  Shift boyunca başlangıç noktası sabit kalır. Öğrenci adı satırı, ders başlığı
  sütunu seçer; Shift ile aradaki tüm satır/sütunlar seçilir. "Seçimi kaldır"
  başlangıç noktasını da sıfırlar. Seçim kendi başına kayıt değiştirmez.
  Orijinal var/yok/geç kaydı üzerine yazılmaz. Kategoriyi kaldırmak orijinal
  kaydı tekrar görünür yapar. Aynı hücrede yalnız bir etkin idari kategori olur.
- Numarayla toplu giriş okul numarasıyla tüm okulda eşleşir; şube/devre seçimi
  yanlış öğrenciyi dışarıda bırakmaz. Önizlemede şube ve etkilenecek dersler
  gösterilir. Aynı öğrenci bir kez işlenir; bulunamayan/geçersiz numaralar açıkça
  gösterilir. Kullanıcı eşleşen öğrencileri onaylamadan kayıt yazılmaz.
- Başlangıç/son ders seçilir; okul numaraları satır, virgül, boşluk veya noktalı
  virgülle yapıştırılabilir. Önizleme sonrası girdiler değişirse onay geçersizleşir.
- Çakışan eski idari işaretler önizlemede görünür; açık onay olmadan sessizce
  ezilmez. İşlem atomik olmalı; beklenmeyen hatada kısmi toplu kayıt olmamalı.
- Geçmiş kayıtta düzeltme, kişi ve zamanla izlenir; işlem günlüğüne öğrenci
  adı/numarası veya rehberlik türü dökülmez, yalnız işlem ve sayılar yazılır.
- Yoklama alınmayan dersin üzerinde idari plan olması öğrenciyi otomatik
  "Var" yapmaz. Eksik yoklama görünümü ve uyarısı korunur.

## Tahtada gizlilik

Öğretmen güncel dersin maskeli listesini görür; Var / Yok / Geç işaretler.
Yalnız o ders için etkin Nöbetçi/Faaliyet etiketi eklenir; bu etiketler otomatik
Var seçimi yapmaz. Geçmiş yoklama, izinli, rehberlik/idari görüşme bilgisi
sunucunun ajan yanıtına **hiç dahil edilmez**; yalnız arayüzde gizlemek yeterli değildir.
Liste ve seçimler tahtada diske/günlüğe yazılmaz. Belirteçler servis belleğinde kalır.

## Ders arası yokluk uyarıları

Yalnız idare rollerinin görebileceği ayrı bir ekran: tarih, şube/devre, öğrenci,
son Var/Geç görüldüğü ders, ilk açıklanmayan Yok dersi ve kayıt inceleme bağlantısı.
Gün içinde daha önce hiç Var/Geç kaydı olmayan öğrenci bu özel uyarıya girmez.
Sonraki dersin yoklaması alınmadan uyarı çıkarılmaz. Arada birden fazla ders
varsa son bilinen Var/Geç ve ilk açıklanmayan Yok saati açıkça belirtilir.
Öğrencinin izni/görevi bittiği halde sonraki derste Yok kaydı sürüyorsa yeniden
inceleme gerekir; önceki saatin izni tüm güne yayılmaz.

İzinli, Rehberlik Görüşmesi, İdari Görüşme, Nöbetçi veya Faaliyet kaydı ilgili
dersteki uyarıyı engeller. İzinli devamsızlık toplamına dahil olsa da açıklanmış
yokluktur; bu özel uyarıda sayılmaz. Öğrenci yeniden Var/Geç işaretlendiğinde
etkin uyarı kapanır. Düzeltmeler ve idari kategori değişiklikleri uyarıyı yeniden
hesaplatır. İdare incelemesi sebebiyle kapatılan kayıtta yeniden Yok girişi olursa
yeni uyarı önceki incelemeyle sessizce kapatılmaz.

Uyarı okuldan izinsiz ayrılma veya disiplin ihlali kanıtı olarak sunulmaz;
yoklama hatası ve gecikmiş izin olasılığı için yalnız inceleme çağrısıdır.
Tahtaya, öğretmen ekranına veya genel olay günlüğüne öğrenci kimliğiyle
gönderilmez. Yıl sonu/tüm veri imhası uyarı ve inceleme kayıtlarını da kapsar.
Kalıcı inceleme geçmişi uygulama aşamasının işidir.

## Uygulama sırası

1. Ön koşul: `docs/tasarim.md` §14'teki "yalnız yok" ve kategori tutmama kararları yürürlüktedir.
   Bu taslak ancak o kararlar açıkça değiştirilip §14 ve §17'ye işlendikten sonra uygulanır;
   eski veri dönüştürülmeden korunur.
2. Yeni göç: orijinal kayda bağlı geç işaretleri ve ayrı idari durum/iz tabloları.
   Tarih, öğrenci, ders, şube/devre geçmişi ve değişiklik sürümü saklanacak.
   Aynı öğrencinin sabah/öğle dersleri karışmayacak.
3. Yetkili panel uçları, önizleme belirteci, atomik toplu uygulama ve eşzamanlı
   düzenleme denetimi. Sonradan değişen kayıtta kullanıcıya çakışma gösterilecek.
4. Günlük tablo, seçili hücre düzenleyicisi ve numara yapıştırma ekranı.
5. Ajan/sunucu uyumu: eski ajan yalnız var/yok gönderir; boş geç alanı uyumlu
   okunur. Yeni ajan Geç alanını açıkça gönderir, eski sunucu desteği denetlenir.
6. İcmal/metin/CSV aynı sayım politikasını kullanır. İzinli devamsızlığa dahil,
   diğer dört idari durum ve Geç ayrı sütun/sayaçlarda; tam/yarım gün hesabı yok.
   Değişiklik sonrası eski "e-Okul'a işlendi" işareti geçerli sayılmayacak;
   yeniden inceleme gerektiği açıkça gösterilecek.
7. Yıl sonu imhası, tüm öğrenci verisini silme ve yedek/geri yükleme testleri
   yeni tabloları kapsayacak; özel veriler genel işlem kaydında bırakılmayacak.

## Kabul testleri

- Var/Yok/Geç aynı öğrencide aynı kayıt için çakışmaz; eski kayıtlar değişmez.
- İzinli + orijinal yok tek kez sayılır; diğer kategoriler ayrı sayılır.
- Numara önizlemesi tekrarları, eşleşmeyenleri ve ders aralığı hatasını gösterir.
- Etkin kategori çakışması ve eşzamanlı değişiklik sessizce üzerine yazılmaz.
- Yeni kategori tahtanın JSON yanıtında yalnız Nöbetçi/Faaliyet izin listesiyle çıkar.
- Öğrenci şube değiştirince eski günün şube/devre eşleşmesi bozulmaz.
- Günlük ekran, yazdırma, metin ve CSV aynı sonuçları verir.
- İşlendi işareti değişen icmalden sonra yeniden onay gerektirir.
- Yıl sonu ve elle silme, idari durum/iz/Geç verisini de kaldırır.

Çakışma yönetimi, yetkilendirme ve kalıcı kayıt uygulama aşamasının işidir.
