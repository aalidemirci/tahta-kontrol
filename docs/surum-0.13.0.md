# 0.13.0 — öğretmen programı ve kilit ekranı

17 Kasım 2026. Geliştirme kopyası; kurulu hizmet ve bağlı tahta değiştirilmedi.
Gerçek raporlar depoya/pakete eklenmedi, testler yapay verilerle yazıldı.

## Çalışan özellikler

- Yönetici için **Program → Öğretmen programı** ve Yoklama sekmelerinden
  erişilen yeni aktarım ekranı. Aynı e-Okul programının XLS ve PDF dosyaları
  birlikte yüklenir; alternatif olarak XLS yanında sıralı şube listesi girilir.
- PDF sayfa/şube adedi ve Excel blok sırası öğretmen satırlarıyla karşılaştırılır.
  Boş bloklar da önizlemede görünür. Mevcut öğrenci listesinin tekrar yüklenmesi gerekmez.
- Kaynak öğretmen adları mevcut öğretmen kimlikleriyle eşlenir. Tek ve tam ad
  eşleşmesi önerilir; belirsiz veya eksik eşlemede açık seçim gerekir.
  Öğretmeni bulunamayan dersleri eşlemesiz kaydetmek ayrıca onay ister.
- Kalıcı programda şube, gün, ders no/saat, ders başlığı ve öğretmen kimliği var;
  ham PDF/XLS ve kaynak öğretmen adları diske yazılmaz. Önizleme kullanıcıya
  bağlı, süreli ve tek kullanımlıdır. Eşzamanlı program değişikliği onayı reddeder.
- USB anahtarı zaten öğretmen kimliğine bağlı olduğundan program eşlemesi aynı
  kişiyle ilişkilendirilir. Yoklama ayrıntısında USB kimlikleri, alan öğretmen
  ve güncel haftalık programdaki öğretmen birlikte görülebilir.
- **Başka öğretmen/sınıf/ders yoklaması engellenmez.** Nöbet ve boş ders
  gözetimi yolu açıktır. Mevcut kimlik doğrulama, geçerli ders saati ve gelecek
  ders denetimleri korunur; öğretmen programı yeni yetki sınırı oluşturmaz.
- Kayıt ayrıntısındaki karşılaştırma o an yüklü programadır; geçmişteki programın
  değişmediğini kanıtlamaz. Başka öğretmen kaydı ihlal diye etiketlenmez.

## Kilit ekranı

Tahtaya atanmış şubelerin bugünkü dersleri gönderilir: **şube, ders başlığı ve
saat**. Öğretmen/öğrenci adı, USB kimliği ve yoklama kayıtları bu içerikte yoktur.
Tatil, telafi günü ve mevcut zil saatleri gözetilir; ikili eğitim devresi
eşleşmiyorsa eski rapor saatini sessizce göstermek yerine açıklama verilir.

Program sağ sütunda tuş takımının altında yer alır. En çok 24 ders, dört satırlık
sayfalarla gösterilir; büyük saat ve kilit açıklaması sol sütunda kalır.
Uzun adlar metin olarak kısaltılır, markup çalıştırılmaz. Kod/USB açma yolu
olmasa da program görünür. Eski sunucu veya başka günün verisi paneli gizler.
Ajan yalnız bellekte tutar; sunucunun gece yarısına kadar verdiği monotonik
süre dolunca program kalkar. Kilit/çevrimdışı açma kuralları değişmez.

## Saha öncesi doğrulama

Yeni aktarım/parçalama, onay, USB bilgisi, esnek yoklama, saat/devre ve ekran
mantığı test edildi. Tam koşu: **925 geçti, 12 atlandı** (571,83 saniye).
Tek uyarı FastAPI/Starlette test istemcisinin httpx kullanımdan kaldırma uyarısıdır.
Ruff ve Git fark denetimi geçti. PyInstaller Windows klasör paketi ve Inno
kurucusu üretildi; paketlenmiş sunucunun sağlık/ilk kurulum yanıtları ve
temiz kapanışı ayrı deneme verisiyle doğrulandı. Ajan .deb paketi yeniden
üretildi; yeni program modülü içeride, liste/veritabanı dosyası yok.
Kurucu çalıştırılmadan arşiv olarak okunabildi. SHA-256 değerleri
dist/SHA256SUMS-0.13.0.txt dosyasındadır.

Gerçek GTK/ETAP görsel ölçümü bu Windows ortamında yapılamadı; kaynak yerleşimi
ve ölçek sözleşmesi testleri, gerçek tahtada 1024×768 / 1366×768 denemesinin
yerini tutmaz. Tek tahtada kurulum, kilitle/açma, program sayfalama ve yüzer
düğme denemesi yapılmadan okul geneline dağıtılmamalıdır.

## Kullanım

Yeni sunucu kurulduktan sonra yönetici oturumuyla Öğretmen programı ekranından
aynı raporun PDF ve XLS dosyalarını seçin, önizlemeyi ve öğretmen eşlemelerini
kontrol edip onaylayın. Bu yol zil saatlerini veya mevcut derslik programı
kilitlerini değiştirmez. Gerekiyorsa önce mevcut Zil/Derslik programı aktarımını
tamamlayın; şubeleri ilgili tahtalara atayın. Sonra tek tahtanın ajanını
güncelleyin. Tahtada yeni ekran yardımcısının yüklenmesi için oturumu yeniden açın.

Bu sürüm yoklama yönetimi taslağındaki yeni idari durumlar, toplu faaliyet,
Geç ve ders arası yokluk uyarılarını içermez; onlar `yoklama-yonetimi-tasarimi.md`
içinde uygulanmamış taslak olarak durur (kararlar `tasarim.md` §17'dedir). Bir bölümü
[0.14.0](surum-0.14.0.md)'da uygulandı.

Düzeltmeler: [0.13.1](surum-0.13.1.md) — seçmeli hücrede öğretmen adının ders başlığına
karışması dahil. 0.13.0 ile aktarım yapıldıysa 0.13.1'de program yeniden aktarılır.
