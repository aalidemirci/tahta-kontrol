# Geliştirme planı — 17 Kasım 2026

Amaç: çalışan okul sistemine dağıtım yapmadan güvenilirliği artırmak.
Bu bilgisayarda kurulu sunucu ve bir bağlı istemci vardır. Geliştirme ayrı
kaynak kopyasında yapılır; üretim verisi ve sertifikası kullanılmaz.

## 1. Ajan indirmelerini sınırlandırma — uygulandı ve yerelde doğrulandı

- JSON 4 MiB, ajan paketi 16 MiB, logo 256 KiB üst sınırı.
- Başlıksız ve chunked yanıtlarda da gerçek okunan veri sınırlanır.
- Kesik Content-Length yanıtı hata sayılır; bağlantı kapatılır.
- Mevcut sertifika parmak izi, SHA-256, çevrimdışı açma ve hata yolları korunur.
- Kabul: sınırda/üstünde yanıtlar, kesik gövde ve chunked veri testleri;
  mevcut ajan regresyon testleri, lint ve paket üretimi.
- Ajan değiştiği için geliştirme sürümü 0.12.1; kurulu sürüm değiştirilmez.

Sonuç: ajan iletişim/altyapı, acil, program, sınav, USB, yoklama ve sunucu
akışlarını kapsayan seçili regresyonda 157 test başarılı, 8 Linux testi atlandı.
Sonradan eklenen normal yanıt testleriyle yeni indirme test dosyası toplam
14/14 başarılı. Ruff ve `git diff --check` temiz, `uv lock --check --offline`
başarılı. `uv lock` bağımlılık sürümlerini korudu, proje sürümünü 0.12.1 ve
kilit biçimi revizyonunu 5 yaptı. Ajan paketi üretildi, kurulmadı.

Sonraki yedekleme değişikliğiyle birlikte tam test takımı çalıştırıldı:
868 başarılı / 12 atlanan / 0 başarısız (516,08 saniye).
Koşu başladıktan sonra eklenen iş parçacığı başlatma hatası testi de arka plan
dosyasının 5/5 başarılı hedefli koşusunda doğrulandı. Mevcut Starlette test
istemcisi uyarısı sürüyor.

## 2. Sürekli doğrulama — dosyası hazır, GitHub koşusu bekliyor

- GitHub Actions'ta Windows ve Ubuntu, Python 3.12.
- Kilitli bağımlılık kurulumu, Ruff ve pytest.
- Dosya: `.github/workflows/dogrulama.yml`; eylemler commit SHA'larına,
  uv 0.13.8 sürümüne sabitlendi. Salt okunur depo izni kullanır.
- Kabul: dosyanın yerel incelemesi; GitHub'a gönderildikten sonra her iki
  platformun gerçek koşu sonuçları. Yerel Windows sonucu Linux doğrulaması sayılmaz.

## 3. Yedekleme ve zamanlayıcı — uygulandı ve doğrulandı

- Önce veritabanı kilidi, elle/otomatik yedek çakışması ve kapanış incelenir.
- Otomatik yedek için aynı anda yalnız bir arka plan işi; hata günlüğü ve
  kontrollü kapanış tasarlanır. Ortak veritabanı kilitleri gelişigüzel kaldırılmaz.
- Kabul: yavaş ikinci diskte program/acil denetimi sürer, iki yedek üst üste
  başlamaz; hata sonrası tekrar denenebilir ve mevcut yedek/geri yükleme testleri geçer.

`yedek_is.py::YedekIsleyici` eklendi; yalnız otomatik yedek arka planda yürür.
Senkron yedek fonksiyonu ve `vt.KILIT` korundu. Hata sonrası tekrar deneme,
başlatma hatası, tek iş sınırı, kapanış ve zamanlayıcının sürmesi test edildi.
İkinci disk yazımı bekletilen gerçek şifreli yedekte normal SQLite işlemi
tamamlandı; eşzamanlı yedek reddedildi ve biten kopyalar aynı çıktı.
Kapanış toplam 16 saniyeyle sınırlı; takılmış I/O zorla kesilmez, süre aşımı
günlüğe yazılır. 8897/8898 yerel portlarında gerçek geliştirme sunucusu
sağlık 200 verdi ve HTTP/zamanlayıcı/arka plan işi temiz kapandı.

## 4. Kontrollü sürüm denemesi — dağıtım öncesi

- Tam test takımı, Windows kurucu üretimi ve geçici veriyle duman testi.
- Mevcut sunucu sürümü ve geri dönüş kurucusu kaydedilir; panelden şifreli yedek
  alınır ve geri yükleme önizlemesi ayrı deneme verisinde doğrulanır.
- Uygun bakım zamanında tek istemcide bağlantı, kilit/açma, duyuru ve güncelleme
  denenir; ardından program ve USB senaryoları saha listesine göre kontrol edilir.
- Kurulu sisteme dağıtım bu geliştirme adımının kapsamı değildir.

Windows kurucu önkoşulu kontrol edildi: bilinen üç kurulum konumunda Inno
Setup 6 derleyicisi bulunamadı. Bu adımda kurucu üretilmedi veya sistem aracı
kurulmadı. Kaynak doğrulaması ve yerel duman testi tamamlanabilir; Windows
kurucu üretimi ve gerçek Pardus testi dağıtım öncesi hâlâ gereklidir.

Tam koşu tamamlandı: 868 başarılı, 12 platform/bağ desteği nedeniyle atlanan,
0 başarısız test. PyInstaller 6.11.1 ile `dist/TahtaKontrol/` klasör paketi
üretildi; paketlenmiş sunucunun sağlık ve ilk kurulum sayfaları geçici veri ve
8897/8898 yerel portlarıyla HTTP 200 verdi. Deneme süreci kapatıldı. Kurucu
üretimi ve gerçek sistemde yükseltme bu sonuçtan ayrı doğrulamalardır.

## Daha sonra

Büyük modülleri bölme, kimliksiz içe aktarma örnekleri, tanılama özeti ve paket
imzası ayrı işlerdir. Önce bu küçük değişikliklerin saha sonuçları alınır.
