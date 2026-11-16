# Saha denemesi kılavuzu (0.6.0)

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
| Program kilidi (0.4.0): zil saatleri elle, derslik ızgarası, zamanlayıcının verdiği süreli kilidin tahtaya inmesi; kilit ekranında "Bu saatte bu derslikte ders yok · Tahta 04:45'te açılır." (kodlu ve kodsuz); idare kilidinin program kilidini ezmesi; mevcut kilit, duyuru ve kapatma ekranlarının bozulmadığı | Debian 12 kabı + sanal ekran (1920×1080), gerçek paket | Çalıştı |
| Program sayfası sekmeleri, pano şeridi ve "Program kilidini durdur" menüsü, tahta ızgarası, uyarılar, zil silme onay penceresi, dar ekran | Chromium (geliştirme bilgisayarı) | Çalıştı |
| Program kilidinin süre dolunca sunucusuz açılması, kodla açma, yeniden başlatmada geri yüklenmemesi | Birim testleri (kapta süre beklenmedi) | Geçti |
| Sınav kipi (0.5.0): uydurma R5 çizelgesinin içe aktarılması ve derslik adından eşleşme; giriş ekranında 34 ve 64 kişilik maskeli liste (64'te ilk 60 + "ve 4 kişi daha"); yanlış ve doğru gözetmen kodu; sınav başlamadan "Yoklama al"ın pasif olması ve başlayınca açılması; koltuk ızgarasında işaretleme ve kaydetme ("Yoklama kaydedildi: 3 öğrenci gelmedi"); 60'tan kalabalık salonda "Bu salonun yoklaması panelden alınır"; süre uzatmanın birkaç saniyede sayaca yansıması; sınav ekranının üstünde duyuru; sunucu kapalıyken 90 sn sonra "Kilidi aç" düğmesi ve düğmeyle sınav ekranının kalkması, sunucu dönünce geri gelmesi; panelden kip kaldırma; kilit ve kapatma ekranlarının bozulmadığı | Debian 12 kabı + sanal ekran (1920×1080), gerçek paket; dokunma `xdotool` ile | Çalıştı |
| Sınavlar, sınav sayfası (canlı durum), salon yoklaması, gözetmen fişleri, icmal, onay pencereleri, panoda "Sınav sürüyor" rozeti ve sınavdaki tahtaya kilit açma ek onayı | Chromium (geliştirme bilgisayarı) | Çalıştı |
| Ders yoklaması (0.6.0): gerçek paketle kurulan tahtada "Yoklama Al" kısayolunun (`tahta-ajan yoklama`) PIN sayfasını açması; PIN sonrası şube ve ders saati seçimi (zil saati yokken 1–12); 24 kişilik listede işaretleme ("Burak K. / YOK", "Yok: 3 · Mevcut: 21/24"), onay ve "Kaydedildi: 3 öğrenci yok"; kaydın panel ızgarasında "3 yok" görünmesi; kilit ekranında "Yoklama al" düğmesi; kilitli tahtada hatalı PIN iletisi; yoklama açıkken gelen duyurunun yoklamanın altında beklemesi, yoklama kapanınca görünmesi; `durum.json`'da liste ve belirteç olmaması; mevcut kilit, duyuru ve kapatma ekranlarının bozulmadığı | Debian 12 kabı + sanal ekran (1920×1080), gerçek paket; dokunmalar yerel iletiyle benzetildi (kapta `xdotool` yok) | Çalıştı |
| Yoklama günlük görünüm (e-Okul kutusunun kendiliğinden kaydı), kayıt ayrıntısı ve silme onayı (gerekçesiz açılmaz), panelden yoklama, icmal ("Metni kopyala" pano izni yokken metni seçer), öğretmenler, öğrenci listesi, önizleme | Chromium (geliştirme bilgisayarı) | Çalıştı |
| Gerçek e-Okul OOG01001R020 `.XLS` dosyası | — | Denenmedi |
| İcmalin A4 kâğıda yazdırılması (şube başına sayfa) | — | Denenmedi |
| Gerçek Kelebek çizelgesi (okulun Kelebek sürümüyle indirilen R5) | — | Denenmedi |
| **Gerçek ETAP tahtası** | — | **Denenmedi** |
| Kurulum dosyasının başka bir bilgisayara kurulması | — | Denenmedi |
| Gerçek kapatma / yeniden başlatma / uzaktan açma | — | Denenmedi (kapta benzetim) |

## 1. Sunucuyu kurun

1. `dist\cikti\tahta-kontrol-0.5.0-windows-kurulum.exe` dosyasını sunucu olacak
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

### 3.2 Ders programı ve program kilidi (0.4.0)

Hazırlık: Program → Zil saatleri'nden Okul Zili dosyasını alın (ya da elle girin); denenecek
tahtanın sayfasındaki ızgarada o günün derslerini işaretleyin; Program → Kurallar'da program
kilidini açın. Önce öğretmenlere haber verin; boş ders uyarısını denemede açmayın ya da yalnız
deneme tahtası programlı olsun.

| # | Deneme | Beklenen | Sonuç |
|---|---|---|---|
| P1 | Okul Zili'nin gerçek `ayarlar.json`'u (ya da `.okulzili` yedeği) | Önizlemede okulun bütün günleri ve dersleri doğru; ikili eğitimde iki devre ayrı tablo; uyarılar anlaşılır | |
| P2 | Teneffüs başladıktan 2 dk sonra | Tahta kilitlenir; ekranda "Teneffüs · Tahta SS:DD'de açılır." | |
| P3 | Derse girilecek saatte | Tahta kendiliğinden açılır (panelden bir şey yapılmadan) | |
| P4 | Teneffüste sunucu programını kapatın | Ders saatinde tahta yine kendiliğinden açılır; 90 sn sonra "Kilidi aç" düğmesi de çıkar | |
| P5 | Teneffüs kilidini öğretmen kodla açar | O teneffüs boyunca yeniden kilitlenmez | |
| P6 | Teneffüste tahtayı yeniden başlatın | Açılınca kilitsiz kalır (bilinçli) | |
| P7 | Panelden "Kilitle" (idare kilidi), sonra teneffüs | Kilit idarenin kilidi olarak kalır; ders saatinde açılmaz | |
| P8 | Pano → "Program kilidini durdur → 1 saat" | Program kaynaklı kilitli tahtalar birkaç saniyede açılır; bir saat kilit gelmez | |
| P9 | Kütüphane tahtasını muaf yapın | Hiç program kilidi gelmez | |
| P10 | Derslik programı CSV'si (Türkçe Excel'de doldurulup kaydedilmiş) | Önizlemede derslikler eşleşir; "Eşleşmeyen derslikler" doğru | |
| P11 | Boş ders uyarısı açık; programlı tahta derste kapalı kalsın (eşik 10 dk) | Panoda "1 boş ders uyarısı", kartta "Boş ders: N. ders (kapalı)"; tahta açılınca "…'ta kullanılmaya başlandı" | |
| P12 | Kilit ekranı sınıfın arkasından | Neden ve açılış saati okunur; ekranda şube, ders, öğretmen yok | |
| P13 | Okul Zili'nde planlanmış sınav günü | Sınav penceresinde program kilidi gelmez | |
| P14 | Sunucu bilgisayarının saati (Ayarlar/Program şeridi) | Okul zili ile aynı dakikada | |

### 3.3 Sınav kipi ve sınav yoklaması (0.5.0)

Hazırlık: Kelebek Sınav'da bir oturumu (tercihen onaylanmış) seçip **Toplu Dağıtım Çizelgesi
(Excel)** dosyasını indirin. Denemeyi gerçek sınavda değil, öğrenci olmayan bir saatte yapın:
çizelgedeki gerçek adlar tahtaya maskeli de olsa çıkar. Denenecek tahtanın "Derslik" alanı
salon adıyla aynı (ör. salon "10/B Dersliği" → derslik "10/B") ya da sınav sayfasında elle seçili
olsun. Künyede saati 15–20 dk sonraya alın.

| # | Deneme | Beklenen | Sonuç |
|---|---|---|---|
| S1 | Çizelgeyi Sınavlar → Kelebek'ten içe aktar ile yükleyin | Sınav taslak açılır; ad, tarih, saat, salonlar, dersler doğru; derslik adı tutan salonlar eşleşmiş | |
| S2 | Künyede süreyi yazın, **Yayına al** | "Sınav yayına alındı"; eşli tahtada "Ajan güncellenmeli" yok | |
| S3 | Şube dersliği tahtasına **Şube duyurusunu gönder** (Tahta sayfasında "Şubeler" dolu) | Duyuruda "Ah*** Yı****  …47  →  10/B Dersliği, koltuk 2" satırları; öğretmen kapatabiliyor | |
| S4 | **Gözetmen kodlarını yazdır** (A4) | Sayfada 6 fiş, kesik çizgiler; tahtasız salonun fişinde "yoklamayı kâğıda alın" | |
| S5 | Başlangıçtan 10 dk önce | Salon tahtası kendiliğinden giriş ekranına geçer; liste sınıfın arka sırasından okunur | |
| S6 | Giriş ekranında ortak kilit kodunu girmeyi deneyin | Kod tuş takımı yok; ekran kalkmaz | |
| S7 | Başlangıç anında | Liste kalkar, büyük sayaç ve kurallar gelir | |
| S8 | **Gözetmen** → yanlış kod, sonra fişteki kod | "Kod geçersiz. N deneme hakkı kaldı."; doğru kodla menü; "Yoklama al" | |
| S9 | Koltuklara dokunup **Kaydet** | "Yoklama kaydedildi: n öğrenci gelmedi"; panel sınav sayfasında "Yoklama alındı (Tahta …)" | |
| S10 | Panelden **+10 dk** | Birkaç saniyede sayaç ve bitiş saati değişir | |
| S11 | Sınav sırasında sunucu programını kapatın | Sayaç sürer; 90 sn sonra "Kilidi aç" çıkar; basınca ekran kalkar; sunucu açılınca sınav ekranı geri gelir | |
| S12 | Sınav sırasında panelden bir tahtaya duyuru | Ek onay ister; duyuru sınav ekranının üstünde görünür, kapatılınca sınav ekranı döner | |
| S13 | **Sınav kipini kaldır** (bir salonda) | O tahta sınav ekranından çıkar; alttaki kilit durumu görünür | |
| S14 | Sınav bitişinde | Tahta kendiliğinden eski durumuna döner | |
| S15 | **Yoklama icmali** yazdırın | Salon özeti, gelmeyenler şube ve okul no sırasıyla, imza alanları; e-Okul'a işlemeye uygun | |
| S16 | Tahtada `/var/lib/tahta-kontrol/durum.json` ve servis günlüğü (`journalctl -u tahta-ajan`) | Ad, maske, okul no, gözetmen kodu ya da belirteç yok | |
| S17 | Kişisel veriyi şimdi sil | Sınav sayfasında yalnız sayılar kalır; icmalde "yalnız sayılar gösterilir" | |

### 3.4 Ders yoklaması (0.6.0)

Hazırlık: Ayarlar › Ders yoklaması etkin; Yoklama › Öğrenci listesi'ne e-Okul dosyası
(dosya `saha/` klasöründe kalır, depoya girmez); Öğretmenler ve PIN'de bir deneme öğretmeni
ve PIN pusulası; tahta sayfasında "Şube(ler)" alanı dolu.

| # | Deneme | Beklenen | Sonuç |
|---|---|---|---|
| Y1 | Okulun güncel `OOG01001R020.XLS` dosyasını yükle | Önizlemede şube ve öğrenci sayıları e-Okul dipnotlarıyla aynı; atlanan satır yok; T.C. sütunu varsa "okunmadı" uyarısı | |
| Y2 | e-Okul'da raporun yeri (Öğrenci İşlemleri › Raporlar › OOG01001R020) | Güncel e-Okul'da aynı yerde; Excel çıktısı `.XLS` | |
| Y3 | ETAP dokunmatik ekranda tuş takımı ve öğrenci düğmeleri | Tek dokunuşla doğru düğme; yanlış dokunma yok | |
| Y4 | 40 öğrencilik şubede liste | Kaydırmasız ya da rahat kaydırma; etiketler arka sıradan okunur | |
| Y5 | "Yoklama Al" kısayolu `ogretmen` hesabının menüsünde | Görünür ve açar; masaüstüne simge konabiliyor mu? | |
| Y6 | Kilitli tahtada "Yoklama al" | Klavye kilidi sürer; yoklama sonrası kilit geri gelir | |
| Y7 | Yoklama sırasında panelden duyuru | Yoklama üstte kalır; yoklama kapanınca duyuru kalan süresiyle görünür | |
| Y8 | Yoklama açıkken ağ kablosunu çek, Onayla | "Kaydedilemedi; yeniden deneyin."; kablo takılınca yeniden Onayla başarılı | |
| Y9 | Listede 3 dk dokunmadan bekle | Ekran sessizce kapanır, liste silinir | |
| Y10 | İcmal metnini kopyalayıp e-Okul girişinde kullan | Girişi hızlandırıyor mu; biçim yeterli mi | |
| Y11 | İcmali A4 yazdır | Şube başına bir sayfa; taşma yok; menü ve düğmeler basılmaz | |
| Y12 | Aynı ders saatinde iki öğretmen (bölünmüş ders) | İcmal birleşimi doğru; ızgarada "×2" | |
| Y13 | Aynı öğretmen kodu ile 10 hatalı PIN (farklı tahtalardan da) | Öğretmen kilitlenir ("PIN'iniz kilitlendi"); Öğretmenler sayfasında "PIN kilitli", Kilidi aç ile düzelir | |
| Y14 | Sunucu kapalıyken "Yoklama Al" | "Sunucuya ulaşılamıyor. Bu dersin yoklamasını e-Okul'a doğrudan girin." 5 sn sonra kapanır | |
| Y15 | Fiziksel klavyeden PIN | Rakamlar, Geri silme ve Enter tuş takımı gibi çalışır | |
| Y16 | Tahtada `durum.json` ve `journalctl -u tahta-ajan` | Öğrenci adı, PIN, belirteç yok | |

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
- Program kilidi (0.4.0): tahtanın monotonik saati teneffüs boyunca düzgün işler (uyku/askıya
  alma tahtada kapalı); kilit sürerken tahta uykuya geçerse açılış gecikebilir.
- Okul Zili'nin gerçek dosyalarındaki ders etiketleri ("3. ders", "2-3. ders bloğu",
  ikili eğitimde "Sabah · …") yalnız Okul Zili kodundan ve uydurma örnekten çıkarıldı;
  gerçek bir okulun dosyasıyla denenmedi.
- Okul Zili'nin "tören" kuralları ders saatini değiştirmez; değiştiren gün için okul
  "tarihe özel program" kullanıyor.
- Teneffüs kilidi dokunmatik hareketlerle aşılamaz (0.1.x deneme 5 ile aynı varsayım).
- 200 MB'a yakın `.okulzili` yedeğinin yüklenmesi sunucu bilgisayarında bellek/disk sorunu
  çıkarmaz (dosya geçici olarak tutulur, kalıcı yazılmaz).
- Sınav kipi (0.5.0):
  - Kelebek'in gerçek R5 çıktısı, okuyucunun beklediği yapıda (tek sayfa `Dagitim`, A1'de
    "TOPLU DAĞITIM ÇİZELGESİ", A2'de "ad · gg.aa.yyyy SS:DD · dönem", 4. satırda başlıklar).
    Yalnız Kelebek'in kodu okunarak ve onu taklit eden uydurma dosyayla denendi.
  - Kelebek salon adları ile tahta "derslik" adlarının otomatik eşleşme oranı.
  - 10 dakikalık giriş penceresinin teneffüsle çakışıp önceki dersi bölüp bölmediği.
  - Giriş ekranındaki listenin (her sütunda en çok 20 satır, yazı yaklaşık 23–28 px) sınıfın
    arka sırasından okunabilirliği; ETAP ekran boyu ve pikseli.
  - Koltuk ızgarasının dokunmatikte kullanılabilirliği (40 kişide 9 sütun, düğme yaklaşık 190×120 px);
    yanlış dokunma oranı.
  - Sınav sırasında tahta–sunucu ağının kesintisizliği (kural 3 düğmesinin sınavda görünme ihtimali).
  - Gözetmen fişinin zarf usulüyle dağıtımının idarenin sabah iş akışına uyumu.
  - Tahtanın monotonik saatinin sınav boyunca düzgün işlemesi (uyku/askıya alma kapalı).
  - Sınav ekranının ETAP'ın pencere yöneticisinde EBA içeriği ya da tam ekran videonun
    üstüne çıkması (Debian 12 + openbox'ta çıktı).
  - Dayanaklar: KVKK md. 12 ve sınav kurallarındaki "ilk ve son 10 dakika" kuralı
    doğrulanacaklar listesindedir (`docs/tasarim.md` §17); arayüzde atıf yoktur.
- Ders yoklaması (0.6.0):
  - e-Okul OOG01001R020 `.XLS` çıktısının blok yapısı ve başlık biçimi ("10. Sınıf / A Şubesi",
    "Öğrenci No", dipnotlar) yalnız komşu projenin kodundan ve uydurma matristen çıkarıldı;
    gerçek dosyayla ve `xlrd` ile denenmedi. Menü yolu da doğrulanmadı.
  - Windows kurucusunda `xlrd`'nin pakete girdiği (build.ps1 çalıştırılmadı).
  - Öğrenci düğmeleri (260×96 px, 26 px yazı, 1920 genişlikte 6 sütun) ve tuş takımı (150×96 px)
    ETAP dokunmatiğinde rahat; 40 kişide liste kaydırılır.
  - Fiziksel klavye olayları kilitsiz tahtada da tam ekran pencereye gider (ETAP pencere yöneticisi).
  - "Yoklama Al" kısayolu (`/usr/share/applications`) ETAP menüsünde Eğitim altında görünür;
    `update-desktop-database` yoksa menü bir sonraki oturumda yenilenir.
  - PIN'in sınıf önünde girilmesinin gözetlenme riski kabul edilebilir düzeydedir (kısa oturum ve
    deneme sınırı tek önlemdir).
  - Yerel soket (`127.0.0.1`) tahtadaki diğer yerel süreçlere açıktır; yoklama açıkken ekrandaki
    etiketleri okuyabilirler (belirteç ve PIN girmez).
  - Dayanaklar: yoklamaya ilişkin yönetmelik fıkrası, ders saatinden güne çevirme kuralı ve
    KVKK md. 12 doğrulanacaklar listesindedir (`docs/tasarim.md` §17); arayüzde atıf yoktur.

## 6. Sorun olursa

- Tahtada: `tahta-ajan durum`, `tahta-ajan tani`, `journalctl -u tahta-ajan -n 50`.
- Ajanı kaldırmak: `sudo apt remove tahta-ajan` (ya da `sudo dpkg -r tahta-ajan`).
- Kilit takılı kalırsa: sunucu programını kapatın; 90 sn sonra tahtada "Kilidi aç"
  düğmesi çıkar. Klavye bağlıysa Ctrl+Alt+F3 ile metin uçbirimine geçip
  `sudo systemctl stop tahta-ajan` da kilidi kaldırır.
- Sunucu kayıtları: `%LOCALAPPDATA%\TahtaKontrol\sunucu.log`.
