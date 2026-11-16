# Saha denemesi kılavuzu (0.3.0)

Amaç: yazılımı tek bir tahtada deneyip Pardus ETAP hakkındaki varsayımları
ölçmek. Tek tahta yeter; sorunsuzsa ikinci ve üçüncü tahta eklenir.

## Şimdiye kadar ne denendi

| Denenen | Nerede | Sonuç |
|---|---|---|
| Sunucu testleri (10 test) | Geliştirme bilgisayarı | Geçti |
| Kurulum betiği, paket kurulumu, kayıt, onay | Debian 12 kabı (Docker) | Çalıştı |
| Kilit ekranı, kodla açma, duyuru, tanılama | Debian 12 + sanal ekran | Çalıştı |
| Sunucu kapalıyken kilidin tahtadan açılması | Aynı | Çalıştı |
| Ajanın sunucudan güncellenmesi | Aynı | Çalıştı |
| Windows kurulum dosyasının derlenmesi, paketli programın açılması | Geliştirme bilgisayarı | Çalıştı |
| Kurulum, kilit, duyuru, kapatma, güncelleme, klavye kilidi | Pardus 25 (XFCE) masaüstü | Çalıştı |
| Uzaktan açma (Wake-on-LAN) | Aynı | Çalışmadı |
| Otomatik kapatma: geri sayım, Vazgeç, süre sonunda kapatma | Debian 12 kabı | Çalıştı |
| Okul kimliği (0.2.0): logo ve renklerin tahtaya inmesi; kilit, duyuru, kapatma ekranı; canlı renk ve logo değişimi, logonun kaldırılması | Debian 12 kabı + sanal ekran (1920×1080) | Çalıştı |
| Panelin yeni tasarımı: açık/koyu görünüm, dar ekran, onay penceresi, logo yükleme | Chromium (geliştirme bilgisayarı) | Çalıştı |
| Acil yayın ve tatbikat (0.3.0): kilitliyken üstte görünme, bitince kilidin dönmesi, acil bitince kalan süreli duyurunun dönmesi, acil sürerken uyarılı kapatmanın atlanması, sunucu kapalıyken 90 sn sonra "yayını kapat" düğmesi; düğmenin gönderdiği yerel iletiyle acilin ve kilidin kalkması (dokunma benzetilmedi) | Debian 12 kabı + sanal ekran (1920×1080), gerçek paket | Çalıştı |
| Duyuru planları, hedef önizlemesi, gruplar, CSV önizleme, acil sayfası ve rapor, açılır menü | Chromium (geliştirme bilgisayarı), açık/koyu, dar ekran | Çalıştı |
| **Gerçek ETAP tahtası** | — | **Denenmedi** |
| Kurulum dosyasının başka bir bilgisayara kurulması | — | Denenmedi |
| Gerçek kapatma / yeniden başlatma / uzaktan açma | — | Denenmedi (kapta benzetim) |

## 1. Sunucuyu kurun

1. `dist\cikti\tahta-kontrol-0.3.0-windows-kurulum.exe` dosyasını sunucu olacak
   idari bilgisayara kurun (yönetici izni ister; güvenlik duvarında 8788 kapısını açar).
2. Açılan pencerede **Paneli aç** deyin; ilk kurulumda okul adını ve yönetici
   hesabını oluşturun.
3. **Ayarlar** sayfasında bu bilgisayarın adresine bakın. Tahtaların bu adrese
   ulaşabildiğini bir tahtanın tarayıcısından `https://ADRES:8788/saglik`
   açarak sınayın (sertifika uyarısı beklenir).
4. Ayarlar'da 4-8 haneli bir kilit kodu belirleyin.
5. Ayarlar > **Okul kimliği**: okulun rengini seçip **Renkleri kaydet**, logoyu
   (PNG ya da JPEG, en çok 256 KB) **Logoyu yükle** deyin. Kontrast raporuna bakın.

Not: sunucu şimdilik oturum açıkken çalışır; bilgisayar kapanır ya da oturum
kapanırsa tahtalar çevrimdışı kalır (kilitleri tahtadan açılabilir).

## 2. Tahtaya ajanı kurun

1. Panelde **Tahta ekle → Tahta eklemeyi aç**. Ekrandaki kodu not edin.
2. Tahtada `etapadmin` ile oturum açıp uçbirimde sayfadaki iki komutu çalıştırın.
3. Betiğin yazdığı parmak izinin başı paneldekiyle aynı mı, bakın.
4. Panoda "Onay bekleyen tahtalar" altında tahtayı açın, ad ve derslik verip onaylayın.
5. Tahtada oturumu kapatıp açın (ekran yardımcısı oturum açılışında başlar).

## 3. Ölçülecekler

Önce panelde tahtanın sayfasından **Tanılama çalıştır** deyin ve raporu saklayın
(depoya koymayın). Sonra sırayla deneyin:

| # | Deneme | Beklenen | Sonuç |
|---|---|---|---|
| 1 | Tanılama: "Kilit ekranı kitaplığı (GTK3)" | Tamam | |
| 2 | Tanılama: "Etkin oturum" türü | x11 (wayland ise kilit zayıf kalır) | |
| 3 | Tanılama: "Ekran yardımcısı" | Bağlı, klavye kilidi "alındı" | |
| 4 | Kilitle | Tam ekran kilit, 1-2 sn içinde | |
| 5 | Kilitliyken Alt+Tab, Süper tuşu, dokunma hareketleri | Kilit aşılamamalı | |
| 6 | Tahtadan kodla açma | Açılır; panelde "Açık" görünür | |
| 7 | 5 kez yanlış kod | 60 sn bekleme | |
| 8 | Duyuru (2 dk, kapatılabilir) | Tam ekran; süre dolunca kalkar | |
| 9 | Kilitliyken sunucu programını kapatın, 90 sn bekleyin | "Kilidi aç" düğmesi çıkar | |
| 10 | Kapat | Tahta kapanır; panelde çevrimdışı | |
| 11 | Uzaktan aç | Tahta açılır mı? (BIOS'a bağlı; açılmaması olağan) | |
| 12 | Yeniden başlat | Açılınca ajan kendiliğinden bağlanır | |
| 13 | `ogretmen` ve `ogrenci` hesaplarıyla oturum | Ekran yardımcısı ikisinde de başlar mı | |
| 14 | Karekod/USB ile kişisel hesaba giriş | Kilit orada da çalışır mı | |
| 15 | Tahta kilitliyken oturum kapatılırsa | Giriş ekranında kilit YOKTUR (bilinen sınır) | |
| 16 | ETAP güncellemesinden sonra | Ajan hâlâ çalışıyor mu | |
| 17 | Ayarlar'da kapatma saatini birkaç dakika sonrasına verin; tahta açık ve kilitsiz | 60 sn geri sayım; Vazgeç tahtayı açık bırakır | |
| 18 | Aynısı, tahta kilitliyken | Uyarısız kapanır | |
| 19 | Logo yüklüyken kilitle | Üst bantta beyaz kutu içinde logo, okul adı, sağda tahta adı · derslik | |
| 20 | JPEG logo yükleyin | Tahtada görünür (ETAP'ta JPEG yükleyicisi var mı) | |
| 21 | Kilit ekranı açıkken panelde rengi değiştirin | Birkaç saniye içinde tahtanın renkleri değişir, pencere kapanıp açılmaz | |
| 22 | Logoyu kaldırın | Tahtada logo kutusu kaybolur; okul adı kalır | |
| 23 | En büyük logo (yaklaşık 250 KB) | Tahtada görünür (yerel sokette büyük satır) | |
| 24 | Projeksiyonda / gün ışığında kilit ve duyuru ekranı | Okul adı, saat, bilgi yazısı ve duyuru başlığı sınıfın arkasından okunur | |
| 25 | Üst bandın zemin rengi | Bant okul renginin koyu tonunda çizilir (çizilmiyorsa not alın) | |

### 3.1 Acil yayın ve zamanlanmış duyuru (0.3.0)

Acil denemesinden önce okulda herkese haber verin; ilk denemelerde **Tatbikat** türünü
kullanın. Ekran görüntüleri depoya konmaz.

| # | Deneme | Beklenen | Sonuç |
|---|---|---|---|
| A1 | Tahta açık ve kilitsizken acil yayın | En çok 5 sn içinde kırmızı tam ekran | |
| A2 | Aynısı tahta kilitliyken | Acil kilidin üstünde; Alt+Tab ile aşılamaz; "Yayını bitir" sonrası kilit ekranı döner | |
| A3 | Tahtada tam ekran başka uygulama (video, EBA içeriği) açıkken | Acil penceresi üstte mi? | |
| A4 | Oturum açık değilken (giriş ekranı) | Görünmez — bilinen sınır; raporda "Ekran yardımcısı yok" | |
| A5 | 20+ tahtaya aynı anda acil | Hepsinde en çok 10 sn; sunucu yükü | |
| A6 | Acil sürerken sunucu programı kapatılır | Yayın kalır; 90 sn sonra "Sunucuya ulaşılamıyor — yayını kapat" düğmesi | |
| A7 | Tatbikat bandı sınıfın arkasından okunabiliyor mu | Yazı boyu ve kehribar zemin yeterli | |
| A8 | Eski sürüm (0.2.0) ajanlı tahta | Yedek duyuru kilit üstünde, kapatılamaz; bitince kalkar; panoda "Eski ajan" | |
| A9 | Acil sürerken otomatik kapatma saati gelir | Tahta kapanmaz; işlem kaydında "atlandı" | |
| A10 | Rapor sayfasını yazdırın | Menü ve düğmeler çıkmaz; tablo tek sayfada okunur | |
| D1 | Günlük plan; sunucu bilgisayarı gece kapalı, sabah açılıyor | İlk gösterim saatinde doğru; kaçırılan yok | |
| D2 | Sunucu bilgisayarı planlı saatte uykuda | Uyanınca süre içindeyse kalan süreyle; değilse "Kaçırıldı" ve panoda not | |
| D3 | Okulun bütün tahtalarına bina/kat/düzey/devre doldurma (CSV ile) | Yönetici için kabul edilebilir süre; Türkçe Excel'de dosya bozulmadan açılıp kaydediliyor mu | |

## 4. Otomatik giriş denemesi (elle)

Yazılım otomatik girişi ayarlamaz. Tanılama raporundaki "Giriş ekranı ve
otomatik giriş" satırı hangi giriş yöneticisinin kullanıldığını gösterir.
LightDM ise `etapadmin` ile `/etc/lightdm/lightdm.conf` içinde
`[Seat:*]` altına `autologin-user=ogretmen` eklenerek denenir. Denemeden önce
dosyanın yedeğini alın. Bakılacaklar: tahta `ogretmen` hesabına kendiliğinden
açılıyor mu, karekod simgesi hâlâ kullanılabiliyor mu, ayar yeniden başlatmadan
ve güncellemeden sonra duruyor mu.

## 5. Doğrulanmamış varsayımlar

- ETAP'ta PyGObject/GTK3 kurulu ve oturum X11.
- `/etc/xdg/autostart` altındaki yardımcı her hesapta (sınırlı erişimli `ogrenci` dâhil) başlar.
- `etapadmin` `sudo` kullanabilir ve `dpkg -i` engellenmemiştir.
- Merkezî yönetim (LiderAhenk) üçüncü taraf servisi kaldırmaz; bu konuda İlçe MEM
  bilgi işlem birimine danışılması önerilir.
- Tahtalar ile sunucu bilgisayarı arasındaki ağ erişimi (yönlendirme) açık.
- ETAP'taki GTK 3.24 sürümü `Gtk.Box` zeminini CSS'ten çizer (Debian 12'de çiziyor;
  çizmezse üst bant `Gtk.EventBox` içine alınmalı).
- GdkPixbuf'un PNG ve JPEG yükleyicileri ETAP'ta kurulu.
- Acil penceresi (`keep_above` + `present` + tam ekran) ETAP'ın pencere yöneticisinde
  tam ekran video ya da EBA içeriğinin üstüne çıkar (Debian 12 + openbox'ta çıktı).
- Pencereye eklenen stil sınıfı (`window.acil`) ETAP'taki GTK 3.24 temasında zemini boyar.
- Türkçe Excel CSV'yi `;` ile ve ANSI (cp1254) ya da UTF-8 olarak kaydeder; ikisi de okunur.
- Sunucu bilgisayarının saati doğru ve Europe/Istanbul; planlar bu saatle işler.

## 6. Sorun olursa

- Tahtada: `tahta-ajan durum`, `tahta-ajan tani`, `journalctl -u tahta-ajan -n 50`.
- Ajanı kaldırmak: `sudo apt remove tahta-ajan` (ya da `sudo dpkg -r tahta-ajan`).
- Kilit takılı kalırsa: sunucu programını kapatın; 90 sn sonra tahtada "Kilidi aç"
  düğmesi çıkar. Klavye bağlıysa Ctrl+Alt+F3 ile metin uçbirimine geçip
  `sudo systemctl stop tahta-ajan` da kilidi kaldırır.
- Sunucu kayıtları: `%LOCALAPPDATA%\TahtaKontrol\sunucu.log`.
