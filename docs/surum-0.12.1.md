# 0.12.1 geliştirme sürümü

17 Kasım 2026. Yerel geliştirme kopyası; kurulu sunucu ve bağlı istemciye
dağıtılmadı, üretim verisi veya sertifikası kullanılmadı.

## Değişen davranış

- Ajan JSON yanıtlarını 4 MiB, güncelleme paketini 16 MiB, logoyu 256 KiB ile
  sınırlar. Content-Length olmasa ve veri chunked gelse de okuma sınırlıdır.
  Kesik yanıt reddedilir; bağlantı kapanır. Sertifika ve SHA-256 kontrolü sürer.
- Otomatik yedek ve geri yükleme kalıntılarının temizliği tek arka plan işinde
  yürür. Yavaş ikinci disk ana zamanlayıcıyı bekletmez, iki otomatik iş çakışmaz.
- Kapanışta yeni yedek kabulü kapanır, bekleyen zamanlayıcı uyandırılır;
  HTTP/zamanlayıcı/yedek için toplam bekleme 16 saniyedir. Takılmış disk I/O'su
  zorla iptal edilemez; süre aşımı uyarısı yazılır ve süreç kapanırken iş sonlanır.
- Windows ve Ubuntu için kilitli bağımlılık, Ruff ve pytest GitHub Actions
  tanımı eklendi. Henüz GitHub'a gönderilmedi, bulut koşusu yapılmadı.

## Doğrulama

- Yeni indirme testleri: 14 başarılı.
- Yeni arka plan işleyici testleri: 5 başarılı; ayrıca yavaş ikinci disk
  entegrasyonu ve mevcut acil zamanlayıcı testi başarılı.
- Ruff, kilit dosyası ve `git diff --check` temiz.
- Kaynak sunucu 8897/8898 yerel portları ve ayrı veriyle açılıp temiz kapandı.
- PyInstaller 6.11.1 ile Windows klasör paketi üretildi:
  `dist/TahtaKontrol/`. Paketin sağlık ve ilk kurulum sayfaları geçici veriyle
  HTTP 200 verdi; deneme süreci kapatıldı. Yeni yedek modülü pakete dahil.
- Tam test koşusu: **868 başarılı, 12 atlanan, 0 başarısız** (516,08 saniye).
  Koşu başladıktan sonra eklenen başlatma hatası testi ayrıca arka plan dosyasının
  5/5 başarılı koşusunda doğrulandı. Bir mevcut Starlette/httpx kullanımdan
  kaldırma uyarısı var; bağımlılıklar bu değişiklikte yükseltilmedi.

## Dağıtım öncesi kalanlar

- Inno Setup 6 derleyicisi bilinen konumlarda bulunamadı; Windows kurucu
  `.exe` dosyası üretilmedi. Klasör paketi kurucu yerine dağıtılmamalı.
- Kurulu sunucunun şifreli yedeği, geri dönüş kurucusu ve bakım zamanı
  hazırlanmalı; mevcut sertifika korunmalı.
- Gerçek Pardus/USB/Windows hizmet yükseltmesi ve Ubuntu CI çalışması bu
  bilgisayardaki kaynak testleriyle doğrulanmış sayılmaz.

Geliştirme için `scripts/dev.ps1 sunucu` kullanılır. Paketin exe dosyasını
varsayılan ayarlarla çift tıklamak yerine ayrı veri/port ayarlarıyla test edin.
