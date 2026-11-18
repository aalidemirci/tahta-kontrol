# Saha denemesi kılavuzu (0.13.1)

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
| Altyapı (0.7.0): gerçek paketin kurulum betiğiyle kurulması (`ajan.json`'a adres listesi yazıldı); birincil adres ulaşılamazken 3 hatadan sonra listedeki adrese geçip onu kalıcı birincil yapması; sunucunun gönderdiği listenin `ajan.json`'a yazılması; `tahta-ajan sunucu` (ulaşılamayan adreste hiçbir şey yazmaması, ulaşılanda yazması); envanterin (ekran çözünürlüğü dahil) panele inmesi ve "Envanteri yenile" komutu; menüdeki "Arıza bildir" kısayolunun kurulması, arıza penceresinde tür seçimi, açıklama ve "Arıza kaydı iletildi."; kaydın panelde "Tahtadan" görünmesi; tanılamada "Sunucu adresleri" ve "Arıza bildirimi kısayolu" satırları; mevcut kilit, duyuru ve kapatma ekranlarının bozulmadığı | Debian 12 kabı + sanal ekran (1920×1080), gerçek paket; dokunma `xdotool` ile | Çalıştı |
| Ekran ölçeği (0.7.1): tahta ekranının bütün ölçülerinin (yazı, tuş takımı, düğmeler, boşluklar) monitör boyutuna orantılı olması; gerçek paketle kurulan üç tahtada (1280×800, 1366×768, 1920×1080) kilit, duyuru, kapatma geri sayımı, acil yayın, ders yoklaması PIN'i, şube/ders seçimi ve öğrenci listesi, sınav giriş ekranı ve gözetmen kodu sayfasında pencerenin ekrana eşit olması (`xwininfo`), kesik yazı ve taşma olmaması; `scripts/ekran_olcum.py` ile 17 senaryonun 1024×768, 1280×800, 1366×768, 1920×1080, 3840×2160 ve portre 1080×1920'de ölçülmesi (taşan yok; yalnız 32–40 kişilik yoklama listesi dikey kaydırılır) | Debian 12 kabı + sanal ekran, gerçek paket; PIN fiziksel klavyeyle (`xdotool`), Gözetmen düğmesi dokunmayla | Çalıştı |
| Yedekler (parola, elle yedek, indirme, yanlış/doğru parolayla geri yükleme denetimi, önizleme, vazgeç), Envanter (sıralama, CSV), Arızalar ve arıza ayrıntısı, tahta sayfasında envanter/arıza/bağlantı kartları, panoda "Arıza" ve "Donanım değişti" rozetleri, Ayarlar › Sunucu adresleri | Chromium (geliştirme bilgisayarı) | Çalıştı |
| Onaylanan geri yüklemenin program yeniden açılınca uygulanması | Geliştirme bilgisayarı (deneme veri klasörü) | Çalıştı |
| 16.11.2026 kararları (0.8.0): iki devreli uydurma okulda (sabah 07:30–12:20, öğle 13:00–17:50) program kilidi, devre geçişinde "Öğle arası", boş ders uyarısının doğru devreye bakması, yoklama önerisinin saate göre doğru şube ve dersi seçmesi, ızgara ve icmalde devre adı, duyuru devre süzgecinin programdan türetilmesi, sınav şube duyurusunun programdaki tahtaya gitmesi | Birim ve uçtan uca testler (`tests/test_ikili_egitim.py`) | Geçti |
| Ayarlar › Kişisel veri saklama (tarih yokken uyarı, geçmiş tarihte onay ve silinecek sayılar, Okul Zili önerisi), boş ders raporu (tarih aralığı, tahta ve ders saati süzgeci, yazdırma), kullanıcılar sayfasında acil yetkisi sütununun kalkması, idarecinin acil yayın formunu görmesi | Geliştirme bilgisayarında ayrı veri klasörüyle deneme sunucusu, tarayıcı | Çalıştı |
| Oturum temizliği (K7, 0.8.0): gerçek paketin kurulum betiğiyle kurulduğu kapta `ogretmen` hesabı, sahte Firefox ve Chromium profili, sahte tarayıcı süreçleri ve açık bir GTK penceresi; panelden "Şimdi temizle": 60 sn uyarı ve Vazgeç ekranı, pencerenin kibar kapanması, tarayıcı süreçlerinin sonlandırılması, yalnız çerez/oturum dosyalarının silinmesi (geçmiş, parola, form, yerel depolama, İndirilenler/Masaüstü/Belgeler kaldı; sembolik bağ ve hedefi kaldı), ad içermeyen sonucun komut geçmişine ve işlem kaydına düşmesi. İlk denemede zombi süreç "kapanmadı" sayıldı ve Firefox verisi atlandı; düzeltildi, ikinci denemede çalıştı | Debian 12 kabı + Xvfb + openbox, sahte `loginctl` | Çalıştı (Vazgeç ve benzetim testlerle) |
| Windows hizmeti (K8, 0.8.0): veri dizini kuralı, eski veriyi taşıma (WAL'daki son kayıt, sertifikanın bayt bayt aynı kalması, kaynağa dokunulmaması, birden çok eski klasörde seçim, belirsizlikte ve yarıda kalan kopyada hizmetin bekletilmesi), hizmet gövdesi (aç, durdur, çökme, açılmama), durum penceresi kipleri, kurucu betiğinin metin denetimi | Birim testleri (`tests/test_hizmet.py`) | Geçti |
| Hizmet kipinin uçbirimde çalışması (`hizmet --konsol`, ayrı veri klasörü, 8797/8798): `/yerel/durum` `hizmet: true`, `gunluk\sunucu.log`; `tasi` ile taşınan klasörde aynı parmak izi; `TASIMA-BEKLIYOR.txt` varken açılmaması; hizmet yöneticisi dışından `hizmet`in 2 koduyla çıkması | Geliştirme bilgisayarı (hizmet kurulmadan) | Çalıştı |
| **Gerçek Windows hizmeti** (kurucuyla kayıt, açılışta başlama, Yerel Hizmet hesabı, izinler, 0.7.x'ten yükseltme, kaldırma) | — | **Denenmedi** (§3.7) |
| Gerçek e-Okul OOG01001R020 `.XLS` dosyası | — | Denenmedi |
| İcmalin A4 kâğıda yazdırılması (şube başına sayfa) | — | Denenmedi |
| Gerçek Kelebek çizelgesi (okulun Kelebek sürümüyle indirilen R5) | — | Denenmedi |
| Yetki alma (0.9.0, G1): sudo yetkisiz `ogretmen` + `sudo` grubunda parolalı `etapadmin`. `ogretmen` uçbirimde `bash tahta-kur.sh KOD`: "`etapadmin` hesabının parolası istenecek (su)", `su --pty etapadmin` + sudo ile root; aynısı eski `su` (`--pty` yok) yolunda `sudo -S` ile; `etapadmin` uçbirimde sudo (kendi parolası); yanlış parolada "Bu işlemi etapadmin oturumunda yapın"; uçbirim yokken doğrudan bu ileti; kodsuz çağrıda parola sorulmadan kullanım iletisi. Gerçek paketin deneme sunucusundan (8798) `ogretmen` oturumunda kurulup kaydolması. `otomatik-giris.sh` için aynı yollarla `etkinlestir`/`kaldir`/`durum` | Debian 12 kabı, `expect` ile parola girişi | Çalıştı |
| pkexec yolu: `DISPLAY` varken pkexec'in denenmesi; polkit'in "Authenticating as: etapadmin" demesi; kimlik doğrulama kapta "No session for cookie" ile düştüğünde (logind oturumu yok) ve yanlış parolada `su`'ya geçilmesi | Aynı kap, dbus + polkitd elle | Mantık doğrulandı; **başarılı pkexec denenmedi** (gerçek masaüstü gerekir) |
| Ayarlar › Tahtadaki yüzer düğme, tahta sayfası notu, "Tahta ekle" yönergesi (0.9.0) | Deneme sunucusu (8797), tarayıcı | Çalıştı |
| Açılışta kilit (0.9.0, G2): sunucu açıkken oturum kapat/aç ve servis + oturumun birlikte yeniden başlatılması sonrası kilitlenme; kodla açılan tahtanın aynı oturumda 35 sn boyunca açık kalması; yalnız servis yeniden başlayınca yeniden kilitlenmemesi; `etapadmin` oturumunun kilitlenmemesi; sunucu kapalıyken açılan oturumun açık kalması ve sunucu 120 sn'den sonra dönünce de açık kalması; kilit kodu yokken uygulanmaması; panel kilidinin sunucusuz servis yeniden başlatmasında korunması | Debian 12 kabı (gerçek 0.9.0 paketi, Xvfb + openbox, 1366x768 ve 1920x1080), deneme sunucusu 8798 | Çalıştı (kapta "tahta yeniden başlatma" servis ile oturumun birlikte yeniden başlatılmasıdır; çekirdek ve `boot_id` değişmez) |
| Zil düzenleyici (0.10.0): 0.9.0 veritabanının yükseltmede çizelgelere taşınması; yeni çizelge (tek ve ikili), hızlı oluştur (kaydetmeden taslak; kaydedilmemiş satırlar da gider), "Araya ekle"/"Ders ekle", silme işareti, hatalı saatte 422 + alan iletisi, numara kaymasında "Anladım, kaydet", haftalık düzen, tarihe özel çizelge (Sürüyor rozeti), günü önizle, kullanılmayan çizelgeyi onaylı silme, idareci salt okunur görünüm, 375 px dar ekran (yatay kaydırma yok), koyu tema | Deneme sunucusu (8797, ayrı veri klasörü, uydurma veri), Chromium | Çalıştı |
| Ders programı içe aktarma (0.10.0): yapay zekâ çıktısı yapıştırma (açıklama ve kod bloğu atıldı), şube → tahta eşlemesi, önizleme (tahta başına +/−/~), onay, "Önceki programlar"; aSc XML ve geri yükleme yalnız testlerde (uydurma XML) | Deneme sunucusu (8797), Chromium; birim testleri | Çalıştı |
| **Gerçek aSc Timetables XML dosyası**, okulun gerçek zil saatleriyle taşıma | — | **Denenmedi** (§3.9) |
| e-Okul "Haftalık Ders Programları" raporu (0.12.0): kullanıcının verdiği gerçek .XLS (ikili eğitim) boş sistemde yüklendi; rapordan zil çizelgesi (Sabah 8 + Öğleden sonra 8 ders) onayla kuruldu; PDF başlık biçiminde yapıştırılan şube listesi blok sırasına oturdu; tahta yokken onay kapalı kaldı; uydurma tahtalar (bir kısmı sabahçı + öğlenci şube taşır) eklenince önizleme, onay, "Önceki programlar", ikinci yüklemede hatırlanan eşleme; sayfalarda, işlem kaydında ve veritabanında öğretmen adı yok | Geliştirme bilgisayarı, ayrı veri dizini, deneme sunucusu (8797), betikle (tarayıcı değil) | Çalıştı (deneme verisi silindi) |
| Öğretmen programı ve kilit ekranı gün programı (0.13.0–0.13.1): hücre çözümü, göç, önizleme belleği, `gun_programi` anahtarı | Birim testleri (uydurma veri); kullanıcının gerçek XLS + PDF'i yalnız yerel ayrıştırmayla (yalnız sayılar: 59 blok, ders başlıklarında ad ve " - " yok) | Geçti; deneme sunucusu ve tarayıcıyla denenmedi |
| Yüzer düğme (0.13.1): tıklama, menü, sürükleme, odaklı tam ekran üstünde görünme, ikinci çalışma alanı | Debian 12 kabı + Xvfb, `xdotool`; xfwm4, Mutter, Muffin, Openbox | xfwm4'te tamamı çalıştı; Mutter/Muffin'de "masaüstünü göster" düğmeyi gizledi; Openbox'ta odaklı tam ekranın üstüne çıkamadı. Gerçek dokunma olayı üretilemedi |
| Kilit ekranı gün programı (0.13.1): `scripts/ekran_olcum.py` üç yeni senaryo, 1024×768, 1366×768, 1920×1080, 3840×2160 | Debian 12 kabı + Xvfb (Openbox) | "TAŞTI" ve "OYNADI" yok (en dar pay 1366×768'de 767/768 px) |
| **Yüzer düğme, gün programı ve öğretmen programı gerçek ETAP tahtasında** | — | **Denenmedi** (§3.12) |
| **Gerçek ETAP tahtası** | — | İlk deneme 16.11.2026 (0.8.0): bulgular G1–G3, `docs/tasarim.md` §5.1 |
| Kurulum dosyasının başka bir bilgisayara kurulması | — | Denenmedi |
| Gerçek kapatma / yeniden başlatma / uzaktan açma | — | Denenmedi (kapta benzetim) |

## 1. Sunucuyu kurun

1. `dist\cikti\tahta-kontrol-0.8.0-windows-kurulum.exe` dosyasını sunucu olacak
   idari bilgisayara kurun (yönetici izni ister). Kurucu sunucuyu **Windows hizmeti** olarak
   kaydedip başlatır (bilgisayar açılınca, oturum açılmadan çalışır), güvenlik duvarında 8788
   kapısını açar. Bitiş sayfasındaki metni okuyun (eski verinin taşınıp taşınmadığı orada yazar).
2. Açılan durum penceresinde **Paneli aç** deyin; ilk kurulumda okul adını ve yönetici
   hesabını oluşturun. Pencereyi kapatmak sunucuyu durdurmaz.
3. **Ayarlar** sayfasında bu bilgisayarın adresine bakın. Tahtaların bu adrese
   ulaşabildiğini bir tahtanın tarayıcısından `https://ADRES:8788/saglik`
   açarak sınayın (sertifika uyarısı beklenir).
4. Ayarlar'da 4-8 haneli bir kilit kodu belirleyin.
5. Ayarlar > **Okul kimliği**: okulun rengini seçip **Renkleri kaydet**, logoyu
   (PNG ya da JPEG, en çok 256 KB) **Logoyu yükle** deyin. Kontrast raporuna bakın.

Not: 0.8.0'dan itibaren sunucu oturum kapalıyken de çalışır. Bilgisayar kapanır, uykuya ya
da hazırda beklemeye geçerse tahtalar çevrimdışı kalır (kilitleri 90 sn sonra tahtadan
açılabilir); güç ayarlarında uykuyu kapatın.

### 1.1 0.1.x–0.7.x'ten yükseltirken ne olur

Önceki sürümler sunucuyu oturum açan kullanıcının programı olarak çalıştırır, verisini
(veritabanı, **sunucu sertifikası**, yedekler) o kullanıcının `%LOCALAPPDATA%\TahtaKontrol`
klasöründe tutardı. Tahtalar bu sertifikanın parmak izine bağlıdır; sertifika değişirse bütün
tahtalara ajan yeniden kurulur. Kurucu bu yüzden şunu yapar:

1. Açık Tahta Kontrol pencerelerini (her oturumda) kapatır; varsa hizmeti durdurur.
2. Eski "Windows açılınca başlat" kısayolunu siler.
3. `C:\ProgramData\TahtaKontrol` klasörünü açar; yalnız SYSTEM, Yöneticiler ve hizmet hesabı
   (Yerel Hizmet) erişebilir.
4. Eski veriyi **kopyalar** (taşımaz): kurucuyu çalıştıran hesabın ve bilgisayardaki diğer
   hesapların `AppData\Local\TahtaKontrol` klasörlerine bakar. Birden çok varsa tahtaların en
   son bağlandığı klasörü seçer. Kopyaların özetini karşılaştırır, veritabanını denetler. Eski
   klasör silinmez; içine `TASINDI.txt` bırakılır.
5. Hizmeti kaydeder ve başlatır. Tahtalar aynı adres ve aynı sertifikayla bağlanmayı sürdürür.

Kurucuyu, **sunucuyu her gün kullanan hesapla oturum açıp** (yönetici parolası istenince
girerek) çalıştırmanız önerilir. Kurucu hangi klasörü seçeceğini anlayamazsa ya da kopyalama
başarısız olursa hizmeti **başlatmaz** (yeni sertifika üretip tahtaları koparmasın) ve bitişte
kırmızı uyarı verir. O durumda:

1. Not Defteri'ni yönetici olarak açıp `C:\ProgramData\TahtaKontrol\TASIMA-BEKLIYOR.txt`
   dosyasını okuyun: bulunan eski klasörler, tahta sayıları ve son bağlantı zamanları oradadır.
2. Yönetici komut isteminde doğru klasörü verin:
   `"C:\Program Files\Tahta Kontrol\TahtaKontrol.exe" tasi --hedef "C:\ProgramData\TahtaKontrol" --kaynak "C:\Users\<hesap>\AppData\Local\TahtaKontrol"`
   (sonuç `C:\ProgramData\TahtaKontrol\gunluk\tasima.log` dosyasına yazılır), sonra
   `net start TahtaKontrol`. Ya da doğru klasördeki dosyaları elle kopyalayıp
   `TASIMA-BEKLIYOR.txt`'yi silin ve hizmeti başlatın.
3. Eski veri gerçekten istenmiyorsa yalnız `TASIMA-BEKLIYOR.txt`'yi silip hizmeti başlatın
   (yeni sertifika üretilir; bütün tahtalara ajan yeniden kurulur).

Kurucu taşıma sırasında kesilirse (elektrik, Görev Yöneticisi) kurucuyu yeniden çalıştırın:
yarım kopya geçici klasörde kalır ya da `yarim-tasima-…` klasörüne kaldırılır (silinmez) ve
taşıma baştan yapılır; `TASIMA-SURUYOR.txt` durdukça hizmet açılmaz.

Geri dönmek gerekirse: programı kaldırın (ProgramData'daki veri silinmez), eski sürümü kurun;
eski sürüm eski klasördeki veriyle açılır (taşımadan sonraki değişiklikler orada yoktur).
Sonra yeniden 0.8'e geçerken kurucu, eski klasörün taşımadan sonra kullanıldığını görür ve
hizmeti **başlatmaz**: hangi verinin doğru olduğunu (eski klasör mü, ProgramData mı)
`TASIMA-BEKLIYOR.txt`'deki adımlarla siz seçersiniz. Geri dönüş döneminde eklenen tahtalar ve
alınan yoklamalar yalnız eski klasördedir.

## 2. Tahtaya ajanı kurun

1. Panelde **Tahta ekle → Tahta eklemeyi aç**. Ekrandaki kodu not edin.
2. Tahtada uçbirimi açıp sayfadaki iki komutu çalıştırın (`bash tahta-kur.sh KOD`; başına `sudo`
   yazmayın). En kolayı `etapadmin` oturumudur (betik `etapadmin` parolasını sorar). `ogretmen`
   oturumunda betik yönetici parolasını önce bir pencerede (pkexec), olmazsa uçbirimde `su` ile
   sorar; ekranda hangi hesabın parolasının istendiği yazar — öğretmen parolası işe yaramaz.
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
| Y14 | Sunucu kapalıyken "Yoklama Al" | "Sunucuya ulaşılamıyor. Bu dersin yoklamasını kâğıda alın." 5 sn sonra kapanır | |
| Y15 | Fiziksel klavyeden PIN | Rakamlar, Geri silme ve Enter tuş takımı gibi çalışır | |
| Y16 | Tahtada `durum.json` ve `journalctl -u tahta-ajan` | Öğrenci adı, PIN, belirteç yok | |

### 3.5 Altyapı: yedek, sunucu adresleri, envanter, arıza (0.7.0)

Hazırlık: Yedekler sayfasında yedek parolasını belirleyin (kâğıda yazın). Ayarlar › Sunucu
adresleri'ne sunucunun adresini (ve okul DNS'inde bir ad varsa onu) yazın.

| # | Deneme | Beklenen | Sonuç |
|---|---|---|---|
| A1 | Yedek parolası belirle; 5 dk bekle | Yedekler'de "Günlük" yedek; panodaki kırmızı şerit kalkar | |
| A2 | İkinci kopya klasörü olarak USB disk; sonra USB'yi çıkar | Takılıyken kopya yazılır; çıkarılınca ana yedek alınır, panoda "ikinci kopya yazılamadı" | |
| A3 | Ağ paylaşımı (`\\sunucu\pay`) ikinci kopya olarak | 0.8.0 hizmeti (Yerel Hizmet) ağ paylaşımına yazamaz: ayar kaydedilmez; yerel disk/USB çalışır | |
| A4 | Yedeği başka bir Windows bilgisayara kurulan programın ilk kurulum sayfasından geri yükle | Önizlemede okul adı, tahta sayısı; "sertifika farklı" uyarısı; "Geri yükle ve yeniden başlat" sonrası hizmet kendiliğinden yeniden başlar, yarım dakika sonra eski kullanıcılarla giriş | |
| A5 | A4'teki bilgisayara eski IP verildiğinde tahtalar | Yeniden kurulum olmadan bağlanır | |
| A6 | Adres listesine ikinci bir adres ekle; Ayarlar'da "n/n tahta güncel adres listesini aldı" | Bütün çevrimiçi tahtalar bir iki dakikada listeyi alır | |
| A7 | Sunucunun IP'sini değiştir (listede yeni adres önceden varken) | Tahtalar yaklaşık 1 dk içinde yeni adrese geçer; tahta sayfasında "Bağlandığı adres" yeni adres | |
| A8 | Tahtada `sudo tahta-ajan sunucu https://YANLIŞ:8788` | "Sunucuya ulaşılamadı; hiçbir şey değiştirilmedi"; `ajan.json` aynı | |
| A9 | Envanter sayfası | Üretici, model, seri no (ETAP'ta `product_serial` dolu mu?), işlemci, bellek, disk, ekran, dokunmatik aygıt adı doğru | |
| A10 | CSV indir, Excel'de aç | Türkçe karakterler doğru; sütunlar ayrık; seri no bilimsel gösterime dönmüyor | |
| A11 | Menüde "Arıza bildir": `ogretmen` ve `ogrenci` hesaplarında | Görünür ve açılır; ETAP ekran klavyesi açıklama alanında çıkar mı? | |
| A12 | Arıza bildir (sunucu açık) | "Arıza kaydı iletildi."; panelde Arızalar'da "Tahtadan · öğretmen hesabı"; panoda "Arıza" rozeti | |
| A13 | Ağ kablosu çıkarılmışken arıza bildir; kabloyu tak | "Kayıt tahtada bekletiliyor…"; kablo takılınca kayıt panelde görünür | |
| A14 | Bir saatte 4 arıza bildir | Dördüncüsü "son bir saatte çok bildirim" iletisiyle reddedilir | |
| A15 | Tahtada `durum.json` | `ariza_kuyrugu` iletilince boşalır; hesap adı yok | |

### 3.6 16.11.2026 kararları (0.8.0)

Hazırlık: okulun gerçek ikili eğitim zil çizelgesi Okul Zili'nden ya da elle iki devre olarak
(ör. "Sabah" ve "Öğleden sonra") girilir; bir dersliğe sabah ve öğle şubesi programlanır.

| # | Deneme | Beklenen | Sonuç |
|---|---|---|---|
| K1 | Program › Zil saatleri; pano şeridi sabah ve öğle dersinde | İki devre ayrı tablo; şerit "Sabah · 3. ders …", "Öğleden sonra · 2. ders …" | |
| K2 | Sabah ve öğle şubesi olan tahtada sabah teneffüsü, devre geçişi ve öğle teneffüsü | Kilit ekranında "Teneffüs · Tahta 08:20'de açılır.", geçişte "Öğle arası · … 13:00'te açılır." | |
| K3 | Okul Zili dosyasında ikili eğitim oturum adları | Devre adları doğru okunur (`session_id` ve oturum adı); ders numaraları devre başına 1'den başlar | |
| K4 | Öğle dersinde tahta kapalı | Boş ders uyarısı "Öğleden sonra · 1. ders · 11/C"; sabah programlı tahtada öğlede uyarı yok | |
| K5 | Tahtada "Yoklama Al" sabah dersinde, teneffüste (ders başlamadan 5 dk önce) ve öğle dersinde | Şube ve ders saati devreye göre önerilir; öğle şubesi seçilince öğle saatleri gelir | |
| K6 | Yoklama › Günlük görünüm ve icmal | Şubenin yanında devre adı; sabah ve öğle 3. dersleri ayrı | |
| K7 | Duyuru › Kime › Devre: Sabahçılar | "Devre" alanı boş tahtalarda programa göre seçilir; sabah ve öğle şubeli tahta ikisine de girer | |
| K8 | Ayarlar › Kişisel veri saklama: tarih boşken, gelecek tarih, geçmiş tarih | Boşken üstte uyarı; geçmiş tarih onay ister ve silinecek sayıları söyler | |
| K9 | Program › Uyarılar: bir aylık aralık, bir tahta, bir ders saati | Tarih sütunlu liste, tahta ve ders saatine göre sayılar; kişi adı yok; Yazdır A4'te okunur | |
| K10 | İdareci hesabıyla Acil durum sayfası | Yayın formu görünür; parola ve onay kutusu olmadan başlamaz | |

#### 3.6.1 Oturum temizliği (K7)

Hazırlık: **önce benzetimle** deneyin. Tahtada `etapadmin` ile
`sudo systemctl edit tahta-ajan` → `[Service]` altına `Environment=TAHTA_AJAN_BENZETIM=1`, sonra
`sudo systemctl restart tahta-ajan` (benzetim kapatma komutunu da uygulamaz; denemeden sonra satırı
silip yeniden başlatın). `ogretmen` hesabıyla oturum açın; tarayıcıda deneme amaçlı bir siteye giriş
yapın, birkaç sekme ve bir metin belgesi (kaydedilmemiş) açık bırakın. Denemeden önce ve sonra
`etapadmin` ile `sudo find /home/ogretmen/.mozilla /home/ogretmen/.config -maxdepth 4 | sort` çıktısını
saklayın (gerçek kullanıcı dosyası adlarını depoya koymayın; `saha/` gitignore'dadır).

| # | Deneme | Beklenen | Sonuç |
|---|---|---|---|
| T1 | Tahta sayfası › Oturum temizliği › Şimdi temizle… (benzetim) | Tahtada 60 sn sayaçlı "Açık pencereler kapatılacak" ve Vazgeç; süre sonunda hiçbir şey kapanmaz; sonuç "… kapatma istenecek … silinecek … BENZETİM" | |
| T2 | Aynı deneme, sayaç sırasında Vazgeç | Sonuç "Vazgeçildi …"; hiçbir şey kapanmaz | |
| T3 | Benzetim kapalı, Şimdi temizle | Pencerelere kapatma isteği; kaydedilmemiş belge "kaydedilsin mi?" sorar ve açık kalır; tarayıcı kapanır; yeniden açınca siteden çıkılmış, geçmiş ve yer imleri yerinde, kayıtlı parola duruyor; İndirilenler/Masaüstü aynı | |
| T4 | Kilitli tahtada Şimdi temizle | Uyarısız temizlik; kilit ekranı kalır | |
| T5 | `etapadmin` ve kişisel hesapla oturumda Şimdi temizle | Sonuç "Atlandı: oturum ortak hesap değil"; hiçbir şeye dokunulmaz | |
| T6 | Ayarlar › Oturum temizliği açık, "Otomatik kapatmadan 5 dakika önce" | Kapatma saatinden 5 dk önce uyarı, sonra temizlik; ardından otomatik kapatma uyarısı | |
| T7 | Ekran klavyesi, ETAP kenar çubuğu/paneli açıkken temizlik | Klavye ve panel kapanmaz (yalnız görev çubuğundaki pencereler) | |
| T8 | İşlem kaydı ve tahta sayfası | "Oturum temizliği sonucu" yalnız sayılar içerir (kullanıcı, dosya, profil adı yok) | |

### 3.8 Saha bulguları G1–G3 (0.9.0)

Hazırlık: sunucuyu 0.9.0'a yükseltin. Tahtalar ajanı kendiliğinden güncellemez: panoda tahtaları seçip
“Ajanı güncelle” deyin (tahta sayfasında “Güncelleme var” rozeti kalkmalı). Ayarlar › Tahtadaki yüzer
düğme açık (varsayılan), kilit kodu belirlenmiş olsun. Ajanın kapatma komutunu uygulamaması için ilk
denemelerde benzetimi açın (§3.6.1 hazırlığı).

| # | Deneme | Beklenen | Sonuç |
|---|---|---|---|
| Y1 | `ogretmen` oturumunda `bash tahta-kur.sh KOD` (yeni tahtada ya da yeniden kurulumda) | Pencere (polkit) `etapadmin` parolasını sorar; girilince kurulum sürer. Pencere çıkmazsa uçbirimde "'etapadmin' hesabının parolası istenecek (su)" ve ardından sudo | |
| Y2 | Y1'de pencereyi Vazgeç ile kapat | "Pencerede yetki alınamadı; uçbirimde denenecek" ve `su` yolu | |
| Y3 | `etapadmin` oturumunda aynı komut | "sudo şimdi SİZİN (etapadmin) parolanızı soracak" | |
| Y4 | `ogretmen` oturumunda `sh otomatik-giris.sh durum` (çift tıklamayla da) | Y1 gibi yönetici parolası; ayar gösterilir | |
| Y5 | Tahta **açıkken** `ogretmen` oturumunu kapatıp yeniden aç (Ayarlar › Açılışta kilit açık, kilit kodu var) | Oturum açıldıktan birkaç saniye sonra kilit ekranı; İşlem kaydında "sistem · Açılışta kilit"; kodla açılınca aynı oturumda yeniden kilitlenmez | |
| Y6 | Tahta açıkken yeniden başlat (benzetim kapalı; otomatik giriş açık ya da elle giriş) | Oturum gelince kilitli başlar. Giriş ekranında uzun beklense de oturum açılınca kilitlenir (yaş oturumun başından sayılır) | |
| Y6a | Sunucu bilgisayarını kapat (ya da ağ kablosunu çıkar), tahtada oturumu kapatıp aç; 3 dk sonra sunucuyu aç | Tahta açık başlar, sunucu dönünce de açık kalır (oturum 120 sn'den yaşlı) | |
| Y6b | `etapadmin` oturumu aç | Kilitlenmez (bakım) | |
| Y6c | Program kilidi etkinken ders saatinde (ör. 3. ders) oturumu kapatıp aç | Kilitlenmez (derste açık); teneffüste program kilidi kilitler | |
| Y6e | Program kilidi etkinken tahtayı **ilk dersten önce** aç (ör. 08:05, 1. ders 08:20) | Kilitli başlar, kilit ekranında açılış saati (08:20); 1. ders başında kodsuz kendiliğinden açılır. İşlem kaydında "Açılışta kilit … program kilidiyle kilitlendi (08:20'de açılır)" | |
| Y6f | Program kilidi etkinken tahtayı **teneffüste ya da öğle arasında** yeniden başlat | Oturum gelince kilitli başlar (program kilidi), ders başında kendiliğinden açılır; dersin başlamasına 3 dk'dan az kalmışsa kilitlenmez | |
| Y6d | Tahta kilitliyken (panelden) yeniden başlat | Oturum gelince kilit geri gelir; panelde "Kilitli" | |
| Y7 | Yüzer düğme: sağ alt köşede küçük ve soluk; dokununca belirginleşir; sürükle, kenara yapışsın | Menü düğmenin yanında ekrana sığar; dışına dokununca kapanır; düğme klavye odağını çalmaz (açık bir metin alanına yazarken dokun) | |
| Y8 | Menüden Kilitle | Hemen kilitlenir; İşlem kaydında "Tahta olayı · Tahtadan kilitlendi" (kullanıcı adı yok); panelde "Kilitli"; kodla ve panelden açılır | |
| Y9 | Sunucuyu kapat, menüden Kilitle | Kilitlenir; 90 sn sonra kodsuz açma düğmesi; sunucu açılınca olay kayda düşer | |
| Y10 | Kilit kodu kaldırılmışken menü | "Kilitle (kilit kodu belirlenmemiş)" soluk, dokununca kilitlemez | |
| Y11 | Menüden Kapat (benzetim), geri sayımda Vazgeç; sonra beklet | Vazgeç'te hiçbir şey olmaz; 10 sn sonunda "Tahtadan kapatıldı" olayı | |
| Y12 | Ayarlar'da Yeniden başlat kutusunu aç, tahtadan dene | Menüye birkaç saniyede gelir; 10 sn onaylı | |
| Y13 | Duyuru, acil yayın tatbikatı, kapatma uyarısı, sınav ekranı sırasında | Düğme gizli; sayfa kalkınca geri gelir | |
| Y14 | Tam ekran video ve sunum (LibreOffice Impress) sırasında | Düğme üstte ama küçük ve soluk; sunum klavyeyle ilerler | |
| Y15 | `etapadmin` ve kişisel hesap oturumunda | Aynı düğme ve işlemler | |
| Y16 | Ayarlar'da düğmeyi kapat | Birkaç saniyede tahtadan kalkar | |

### 3.9 Zil düzenleyici ve ders programı içe aktarma (0.10.0)

Hazırlık: sunucuyu 0.10.0'a yükseltmeden önce Yedekler'den şifreli yedek alın (göç öncesi kopya ayrıca
`goc-oncesi` klasörüne kendiliğinden alınır). Ajan değişmedi: panoda "Güncelleme var" görünür ama
güncellemek gerekmez, davranış aynıdır (güncelleme yalnız panodan “Ajanı güncelle” ile yapılır). Bu denemeler ders saatlerini **hemen** değiştirir: ilk denemeleri ders dışı saatte yapın.
Panelden ya da yazılımdan çıkan sayılar dışında gerçek veri, ekran görüntüsü depoya girmez (`saha/`).

| # | Deneme | Beklenen | Sonuç |
|---|---|---|---|
| Z1 | Yükseltmeden sonra Program › Zil saatleri | Mevcut saatler "Ders saatleri · Pzt–Per" gibi çizelgelere taşınmış; haftalık düzen eski günlerle aynı; Derslik programları ve tahta ızgarası değişmemiş; İşlem kaydında "Zil saatleri çizelgelere taşındı · N çizelge · M gün" | |
| Z2 | "Yeni çizelge" (Tek devre), Hızlı oluştur'da okulun saatleri, Kaydet; haftalık düzende bir güne ata | Bugünün ders akışı ve "Günü önizle" o günün yeni saatlerini gösterir; Okul Zili açık değilken de çalışır | |
| Z3 | İkili eğitim: "Yeni çizelge" (İkili), öğle devresinin ilk dersini boş bırakıp Hızlı oluştur | Öğle başlangıcı sabahın son dersinden 20 dk sonrası (5'e yuvarlanmış); gerçek okulda uygun mu? Çakışan saatlerde sarı uyarı, kayıt yine yapılır | |
| Z4 | Bir dersin saatini 1 dk kaydırıp ders içinde (program kilidi açık, bir tahta program kilidinde) kaydet | "Bugünkü ders saatleri değişti; program kilitli tahtalar açıldı…"; tahta birkaç saniyede açılır, sonraki teneffüste yeni saatle kilitlenir | |
| Z5 | Kullanılan çizelgeden bir ders sil (derslik programı yüklü) | Kayıt "Anladım, kaydet" onayı ister; onaylanınca "artık olmayan … ders saati var" bandı; Derslik programları sekmesinde yetim sayısı | |
| Z6 | Tarihe özel çizelge: sınav haftası (Kısa gün), tek günlük tatil ("Ders yok"), takvimdeki bir resmî tatili kapsayan uzun aralık | Günü önizle kaynağı "… (tarihe özel çizelge)"; resmî tatil yine "Tatil"; program kilidi o günlerde kısa günün saatleriyle çalışır | |
| Z7 | Okul Zili kullanılıyorsa: "Okul Zili'nden al", önizleme, onay | Okul Zili kaynaklı çizelgeler kurulur; elle çizelgeler kalır ama haftalık düzenden düşer; Okul Zili'nin tarih kuralları listede salt okunur | |
| Z8 | Okul bilgisayarlarındaki tarayıcıda saat alanları | 24 saat (SS:DD) görünür; AM/PM görünürse not edin | |
| Z9 | İdareci hesabıyla aynı sayfalar | Görür, değiştiremez ("Zil saatlerini yalnız yönetici değiştirir.") | |
| P1 | aSc'de programın bir **kopyasını** açıp öğretmenleri "Ö1, Ö2…" diye yeniden adlandırın; Dosya › Dışa Aktar › aSc TimeTables XML; sihirbaza yükleyin | Eşleme ekranında derslikler/sınıflar/ders saatleri; önizlemede şube ve ders sayıları asıl programla aynı; öğretmen ve ders adı hiçbir yerde (önizleme, işlem kaydı) görünmez. Türkçe menü adını, kodlamayı (UTF-8 mi?) ve günlerin Pazartesi'den başlayıp başlamadığını not edin | |
| P2 | Blok (2 saatlik) ders, bölünmüş grup, dersliksiz ders (beden eğitimi), laboratuvar içeren dosya | Blok ders iki ders saatine yazılır; dersliksiz dersler "hiçbir tahtaya yazılmadı" listesinde | |
| P3 | İkili eğitimde sabahçı ve öğlenci programı (tek dosya ya da iki dosya) | Saatlerden devre bulunur ya da "Bu dosya hangi devrenin programı?" sorulur; sabahçı programı öğlenci satırlarını silmez | |
| P4 | Mevcut programı indir → Excel'de bir şubeyi değiştir → şablon olarak geri yükle | Önizlemede yalnız o değişiklik (~); onay; "Önceki programlar"dan geri yükleme eski hâle döndürür | |
| P5 | Yapay zekâ ile dönüştür: istemi kopyala, okulun dağıttığı programla (kişi adları silinmiş) kurumun izin verdiği araçta çalıştır, çıktıyı yapıştır | Önizlemede şube başına ders sayıları asıl programla karşılaştırılır; hatalı satırlar listelenir | |

### 3.10 USB anahtar (0.11.0)

Hazırlık: sunucuyu 0.11.0'a (ya da sonrasına) yükseltin ve panoda denenecek tahtaları seçip **“Ajanı
güncelle”** deyin; tahta sayfasında "USB anahtar: ajan güncellenmeli" yazmamalı (tahtalar ajanı
kendiliğinden güncellemez). Ayarlar › USB anahtar'da "USB anahtar kullanılsın"ı açın. Yoklama › USB anahtarlar'dan kendinize
bir anahtar üretin (PIN'i not alın), bir öğretmene de anahtar üretin. İndirilen `tahta-kontrol.anahtar`
dosyasını adını değiştirmeden iki ayrı belleğin en üst klasörüne kopyalayın (bellekte başka dosyalar da
dursun; biçimlendirmeyin). Bilgisayardaki kopyayı silin.

- [ ] **Bellek takılınca ne oluyor?** Dosya yöneticisi penceresi kendiliğinden açılıyor mu? Açılıyorsa
      anahtar dosyası sınıfın önünde listelenir: fotoğraf çekmeden not edin; PIN varsayılanları gözden
      geçirilecek (tasarım §17 açık soru 63). `ogretmen`, `ogrenci`, `etapadmin` ve kişisel hesapta ayrı ayrı.
- [ ] Bellek otomatik bağlanıyor mu; bağlama `/media/<hesap>/<etiket>` mı, `/run/media/<hesap>/…` mı
      (`findmnt -l | grep media`; yolu buraya ya da depoya YAZMAYIN, yalnız "media / run-media" yazın).
- [ ] Takınca köşede "USB anahtar tanındı · …" bildirimi kaç saniyede çıkıyor (hedef ≤ 3 sn)? Tam ekran
      sunum (LibreOffice Impress, tarayıcı F11) açıkken bildirim üstte görünüyor mu?
- [ ] Bildirimdeki "Yoklama al" (öğretmen anahtarı, PIN kapalı): kod ve PIN sorulmadan şube/ders seçimi
      geliyor mu? Yoklamayı kaydedin; panelde öğretmenin adıyla görünüyor mu?
- [ ] İdare anahtarıyla (PIN açık): "Yoklama al" yalnız PIN istiyor mu; kayıt panelde "idare (kullanıcı adı)"
      diye görünüyor mu? Yanlış PIN'de "PIN hatalı." çıkıyor mu?
- [ ] Yoklama listesi açıkken belleği çıkarın: liste açık kalıyor ve kaydediliyor mu? PIN sorulan ekrandayken
      çıkarın: ekran "USB anahtar çıkarıldı." ile kapanıyor mu?
- [ ] Tahtayı panelden kilitleyin, belleği takın: kilit ekranında "USB anahtarla aç" çıkıyor mu, dokununca
      (gerekiyorsa PIN'den sonra) kilit açılıyor mu? İşlem kaydında "Kilit USB anahtarla açıldı" satırı.
- [ ] Belleği 10 dakikadan uzun takılı bırakın, sonra "Yoklama al": "çok uzun süredir takılı" iletisi ve
      normal kod + PIN ekranı geliyor mu? Çıkarıp takınca yeniden tanınıyor mu?
- [ ] Sunucuyu durdurun, belleği takın: "USB anahtar şu an kullanılamıyor: sunucuya ulaşılamıyor." çıkıyor mu;
      90 sn sonra kilit ekranındaki çevrimdışı düğmesi eskisi gibi çalışıyor mu?
- [ ] Panelden anahtarı iptal edin (yoklama ekranı açıkken): tahtadaki yoklama kaydedilemiyor ve bellek
      yeniden takılınca "iptal edilmiş" deniyor mu?
- [ ] exFAT ya da NTFS biçimli bir bellek de deneyin (bağlama `fuseblk`/`ntfs3`): kök servis dosyayı okuyabiliyor mu?
- [ ] Tahtanın kart okuyucusu ya da USB çoğaltıcısı üzerinden takılan bellek tanınıyor mu? Tanılamada
      "USB anahtar: elenen bağlama" satırında "çıkarılabilir değil" sayısı artıyorsa not edin.
- [ ] Merkezî yönetim (LiderAhenk) USB depolamayı kısıtlıyor mu? Kısıtlıysa özellik o tahtada çalışmaz.
- [ ] Aynı anahtarı iki derslikte 60 sn içinde kullanın: panelde "kopyalanmış olabilir" rozeti çıkıyor mu?
      Derslikler arası gerçek yürüme süresi 60 sn eşiğine uyuyor mu?
- [ ] Tanılama raporunda "USB anahtar: …" satırları: udisks2 "çalışıyor" mu; yol, etiket, ad görünmüyor mu?

### 3.11 e-Okul "Haftalık Ders Programları" raporu (0.12.0)

Hazırlık: sunucuyu 0.12.0'a yükseltmeden önce Yedekler'den şifreli yedek alın. Ajan değişmedi
(panoda "Güncelleme var" görünür, güncellemek gerekmez). Rapordan zil çizelgesi oluşturmak ders
saatlerini **hemen** değiştirir: ilk denemeyi ders dışı saatte yapın. Rapor dosyası, PDF'i ve ekran
görüntüsü depoya girmez (`saha/`); buraya yalnız sayılar yazılır.

| # | Deneme | Beklenen | Sonuç |
|---|---|---|---|
| E1 | e-Okul'da "Haftalık Ders Programları (OOK11002_R01)" raporunu bütün şubelerle Excel (.XLS) ve PDF olarak kaydedin; Program › Derslik programları › İçe aktar › e-Okul kartından .XLS'i yükleyin | Eşleme adımı; "Rapor" kutusunda blok sayısı PDF'in sayfa sayısına eşit; devreler (ikili eğitimde iki satır) doğru saatlerle | |
| E2 | Zil saatleri girilmiş okulda | Rapordaki saatler zil çizelgesine uyuyorsa "zil çizelgesi oluştur" önerisi ÇIKMAZ; uymuyorsa çıkar ve hangi devrenin uymadığı görünür | |
| E3 | (Deneme okulunda ya da zil yokken) "Bu rapordaki saatlerden zil çizelgesi oluştur" | Onay kutusu olmadan oluşmaz; oluşunca Zil saatleri'nde "e-Okul · Pzt–Cum" çizelgesi, haftalık düzende Pzt–Cum ona atanmış | |
| E4 | PDF'teki sayfa başlıklarını (“9. Sınıf / A Şubesi”) sırayla kopyalayıp "Şube sırası" alanına yapıştırın, "Listeyi uygula" | Her blokta şube; ipuçları (ilk dersler) PDF'le aynı; blok/şube sayısı tutmazsa kırmızı-sarı uyarı | |
| E5 | Bir bloğun şubesini silin (atla) ve iki bloğa aynı şubeyi yazın | Boş blok "Atlanacak"; aynı şube "İki blokta" ve onay kapalı | |
| E6 | Tahtası olmayan şube | "Tahtası belli olmayan şubeler"de tahta seçilir; ikili eğitimde aynı tahtaya sabahçı ve öğlenci şube seçilebilir | |
| E7 | Önizleme ve onay | Şube başına haftalık ders saati PDF'le aynı; boş hücreler (dersi olmayan saat) yazılmaz; sabahçı şube öğlenci satırlarını silmez | |
| E8 | Önizleme sayfası, işlem kaydı | Öğretmen adı hiçbir yerde yok; işlem kaydında yalnız biçim ve sayılar | |
| E9 | Aynı raporu yeniden yükleyin | Şubeler "Hatırlanan" rozetiyle gelir | |
| E10 | Hiç dersi olmayan bloklar (e-Okul'da programı girilmemiş şubeler) | "N blokta hiç ders yok" uyarısı; o şubelerin tahtasına bir şey yazılmaz | |

### 3.12 Yüzer düğme, gün programı ve öğretmen programı (0.13.x)

Hazırlık: sunucuyu yükseltmeden önce şifreli yedek alın. 0.13.0 ile öğretmen programı aktarıldıysa
0.13.1'de yeniden aktarın. Ajan değişti: tek tahtayı güncelleyin, yeni ekran yardımcısı için oturumu
yeniden açın. Rapor dosyası, PDF'i ve ekran görüntüsü depoya girmez (`saha/`); buraya yalnız sayılar ve
evet/hayır yazılır. Tahtanın pencere yöneticisinin adını not edin (`wmctrl -m`; kurulu değilse
`xprop -root _NET_SUPPORTING_WM_CHECK`).

| # | Deneme | Beklenen | Sonuç |
|---|---|---|---|
| Y1 | Kilitli olmayan tahtada yüzer düğmeye parmakla bir kez dokunun | Menü açılır ve AÇIK KALIR (açılıp hemen kapanmaz); ikinci dokunuş kapatır | |
| Y2 | Menü açıkken görev çubuğuna, başlat menüsüne ve bir pencereye dokunun | Hepsi tıklanır; görev çubuğu kilitlenmez (0.12.0 bulgusu yinelenmez) | |
| Y3 | Düğmeyi parmakla sürükleyip bırakın; sonra parmağı titreterek kısa dokunun | Sürükleyince en yakın kenara yapışır; titrek kısa dokunuş sürükleme sayılmaz, menü açılır | |
| Y4 | Tam ekran bir uygulama açın (tarayıcıda F11, sunum, video) | Düğme üstte görünür ve tıklanır; odak uygulamada kalır | |
| Y5 | "Masaüstünü göster" kısayolunu kullanın; varsa ikinci çalışma alanına geçin | Düğme görünür kalır (kapta xfwm4 dışında gizlendi; ETAP'taki sonucu yazın) | |
| Y6 | Menüden Kilitle, Yoklama al, Arıza bildir | Her biri bir kez çalışır (çift tetikleme yok) | |
| Y7 | Fareyle aynı adımlar (Y1–Y3) | Fare tıklaması ve sürüklemesi de çalışır | |
| P1 | Öğretmen programı aktarılmış, tahtaya şube atanmış; tahtayı kilitleyin | Tuş takımının altında bugünün şube/ders/saat listesi; şimdiki ya da sıradaki dersin sayfası açık | |
| P2 | Önceki/Sonraki ile sayfa değiştirin; 1024×768 ve 1366×768'de de bakın | Tuş takımı ve düğmeler yer değiştirmez; hiçbir şey taşmaz; 60 sn sonra şimdiki derse döner | |
| P3 | **Gözle denetim:** bütün sayfalarda ders başlıklarını okuyun (özellikle seçmeli dersler) | Hiçbir satırda öğretmen ya da öğrenci adı YOK; yalnız şube, ders, saat | |
| P4 | Şubesi atanmamış bir tahtayı ve öğretmen programı hiç aktarılmamış sunucuyu deneyin | Program kutusu hiç çıkmaz (ileti de yok) | |
| P5 | Tatil günü | Kutuda ders yerine sunucunun iletisi ("Bugün tatil; ders programı yok.") | |
| P6 | Sunucuyu durdurun, 90 sn bekleyin | "Kilidi aç" düğmesi yine çıkar (kural 3); program kutusu kilit açmayı engellemez | |
| P7 | Tahtanın tarihi yanlışsa (saat pili) | Program gizlenmez; başlıkta sunucunun tarihi yazar | |
| O1 | Yönetici: Program › Öğretmen programı; aynı raporun XLS + PDF'ini yükleyin | Blok sayısı PDF sayfa sayısına eşit; belirsiz hücre ve aynı ad çakışması uyarıları (varsa) yalnız sayı verir | |
| O2 | Önizlemede seçmeli derslerin ders başlıkları | Hiçbir ders başlığında kişi adı ya da " - " yok | |
| O3 | "Vazgeç"; sonra yeniden yükleyip 15 dk bekleyin | Vazgeç'te önizleme hemen silinir; 15 dk sonra onay kabul edilmez, dosya yeniden yüklenir | |
| O4 | Onaydan sonra işlem kaydı ve bir öğretmenin başka sınıfta yoklama alması | İşlem kaydında ad yok, yalnız sayılar; başka sınıf/ders yoklaması engellenmez | |

### 3.7 Windows hizmeti (K8, 0.8.0)

Hazırlık: bu denemeler yönetici yetkisi ister ve **önce deneme bilgisayarında** yapılmalıdır.
0.7.x kurulu bir bilgisayarda yükseltme denenecekse önce Yedekler'den şifreli bir yedek alın ve
`%LOCALAPPDATA%\TahtaKontrol` klasörünü başka bir yere kopyalayın.

| # | Deneme | Beklenen | Sonuç |
|---|---|---|---|
| H1 | Boş bilgisayara kurulum | Bitiş sayfası "Sunucu Windows hizmeti olarak çalışıyor"; `sc query TahtaKontrol` → RUNNING; `sc qc TahtaKontrol` → `SERVICE_START_NAME: NT AUTHORITY\LocalService`, `START_TYPE: AUTO_START` | |
| H2 | 0.7.x kurulu bilgisayarda (tahtalar bağlıyken) yükseltme | Bitişte "verisi ve sunucu sertifikası … kopyalandı"; tahtalar ajan yeniden kurulmadan bir iki dakikada çevrimiçi; eski kullanıcılarla giriş; eski klasörde `TASINDI.txt` | |
| H3 | H2'den sonra `shell:common startup` klasörü | "Tahta Kontrol" kısayolu yok | |
| H4 | Bilgisayarı yeniden başlat, **oturum açma**; bir tahtadan panel/kilit | Tahta çevrimiçi; panel başka bilgisayardan açılır | |
| H5 | Sıradan (yönetici olmayan) bir hesapla `C:\ProgramData\TahtaKontrol` aç | Erişim engellendi | |
| H6 | Görev Yöneticisi › Ayrıntılar'dan hizmetin `TahtaKontrol.exe` sürecini sonlandır | 5 sn sonra yeniden açılır; tahtalar kopmaz | |
| H7 | Durum penceresi: hizmet çalışırken / `net stop TahtaKontrol` sonrası / "Hizmeti başlat" | Bilgi ve adresler / "Sunucu hizmeti çalışmıyor" / UAC sorar, birkaç saniyede bilgiye döner | |
| H8 | Yedekler › geri yükle › "Geri yükle ve yeniden başlat" | Hizmet kendiliğinden yeniden başlar; yarım dakika sonra yedekteki kullanıcılarla giriş | |
| H9 | Aynı sürümü yeniden kur (onarım) ve bir sonraki sürüme yükselt | Bitişte "mevcut veriyle çalışıyor"; veri ve sertifika aynı | |
| H10 | Programı kaldır | Hizmet listede yok; güvenlik duvarı kuralı yok; `C:\ProgramData\TahtaKontrol` duruyor; kaldırıcı bunu söyler | |
| H11 | İki hesapta eski veri (ör. ikinci hesapla da program açılmış) varken yükseltme | Tahtaların en son bağlandığı klasör seçilir; diğerine dokunulmaz | |
| H12 | Okulun antivirüs yazılımı | Hizmeti ve 8788 kuralını engellemiyor | |

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
- ETAP masaüstünde bir polkit ajanı çalışır ve `pkexec` yönetici olarak `etapadmin`'i sorar
  (kapta polkit "Authenticating as: etapadmin" dedi; gerçek oturumda başarı denenmedi).
- ETAP'ta ekran yardımcısı her oturum açılışında yeniden başlar (XDG otomatik başlatma) ve oturum
  kapatılınca eski yardımcı sonlanır. Sonlanmazsa yeni oturum görülmez, açılışta kilit uygulanmaz
  (tanılamada "Kilit durumu kalıcılığı" satırı oturumun yaşını yazar).
- Ağ, oturum açıldıktan sonra 120 sn içinde gelir (geç gelirse açılışta kilit uygulanmaz).
- ETAP'taki `su` `--pty` seçeneğini tanır (util-linux 2.31+; yoksa betik `sudo -S`'e düşer).
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
  - Zil düzenleyici ve ders programı içe aktarma (0.10.0; yalnız testlerde ve deneme sunucusunda uydurma veriyle):
    - aSc XML: kart başına bir ders saati (blok derste kart sayısı), `days` maskesinin Pazartesi'den başlaması,
      `class@classroomids`'in sınıfın kendi dersliği olması, dosyanın UTF-8 ve `DOCTYPE`'sız olması, Türkçe
      menü adı ("Dosya › Dışa Aktar › aSc TimeTables XML") gerçek dosyayla doğrulanmadı; sihirbazda "Sınanıyor" notu durur.
    - e-Okul Haftalık Ders Dağıtım Modülü'nün dışa aktarma biçimi bilinmiyor; e-Okul kaynağı yoktur.
    - Gün ortasında saat değişikliğinden sonra program kilitli ETAP tahtasının hemen açılıp sonraki teneffüste
      yeni saatle kilitlenmesi yalnız testlerde (komut düzeyinde) doğrulandı.
    - Sabahçı/öğlenci devre geçişinde 20 dakikalık öneri ve çakışmanın yalnız uyarı olması okulun gerçek
      saatlerine uyar mı (`docs/tasarim.md` §17, soru 55).
    - `type=time` alanları okulun tarayıcısında 24 saat gösterir (Türkçe yerel ayarda beklenen).
    - Okulun gerçek 0.9.0 veritabanında taşımanın beklenen çizelgeleri ürettiği (yalnız sayılarla bakılacak).
    - Tarihe özel çizelge derslik programını kendi hafta gününden eşler: Cumartesi telafisinde Pazartesi'nin
      derslik programı uygulanmaz (tahtalar açık kalır). Telafi için Okul Zili telafi kuralı kullanılır.
    - Tarihe özel çizelgenin devreleri derslik programındakilerle hiç uyuşmuyorsa (ikili okulda "Tek devre"
      kısa gün) o gün derslik programı uygulanmaz; ekleme sırasında uyarı çıkar. Okulda gerçekten
      sabah/öğle ayrı kısa gün çizelgesi yapılıp yapılmadığı denenmeli (Z6).
  - Dayanaklar: KVKK md. 12 ve sınav kurallarındaki "ilk ve son 10 dakika" kuralı
    doğrulanacaklar listesindedir (`docs/tasarim.md` §18); arayüzde atıf yoktur.
- Ders yoklaması (0.6.0):
  - e-Okul OOG01001R020 `.XLS` çıktısının blok yapısı ve başlık biçimi ("10. Sınıf / A Şubesi",
    "Öğrenci No", dipnotlar) yalnız komşu projenin kodundan ve uydurma matristen çıkarıldı;
    gerçek dosyayla ve `xlrd` ile denenmedi. Menü yolu da doğrulanmadı.
  - Windows kurucusunda `xlrd`'nin pakete girdiği (build.ps1 çalıştırılmadı).
  - Öğrenci düğmeleri (1920×1080'de 260×96 px, 26 px yazı, 6 sütun) ve tuş takımı (150×96 px)
    ETAP dokunmatiğinde rahat; 40 kişide liste kaydırılır. 0.7.1'den beri ölçüler ekrana orantılıdır
    (1366×768'de öğrenci düğmesi yaklaşık 185×68, tuş 107×68 px); küçük ekranda dokunma alanının yeterliliği denenmedi.
  - Fiziksel klavye olayları kilitsiz tahtada da tam ekran pencereye gider (ETAP pencere yöneticisi).
  - "Yoklama Al" kısayolu (`/usr/share/applications`) ETAP menüsünde Eğitim altında görünür;
    `update-desktop-database` yoksa menü bir sonraki oturumda yenilenir.
  - PIN'in sınıf önünde girilmesinin gözetlenme riski kabul edilebilir düzeydedir (kısa oturum ve
    deneme sınırı tek önlemdir).
  - Yerel soket (`127.0.0.1`) tahtadaki diğer yerel süreçlere açıktır; yoklama açıkken ekrandaki
    etiketleri okuyabilirler (belirteç ve PIN girmez).
  - Dayanaklar: yoklamaya ilişkin yönetmelik fıkrası, ders saatinden güne çevirme kuralı ve
    KVKK md. 12 doğrulanacaklar listesindedir (`docs/tasarim.md` §18); arayüzde atıf yoktur.

- Ekran ölçeği (0.7.1):
  - ETAP 4K tahtada GDK ölçeği (HiDPI, `GDK_SCALE`) 1 ise ölçek 2, 2 ise 1 olur; ikisinde de yazı aynı
    fiziksel boyda çıkar. ETAP'ın hangisini kullandığı ve çok monitörlü (yansıtma/genişletme) kurulumda
    pencerenin birincil monitörde açıldığı gerçek tahtada denenmedi.

- 16.11.2026 kararları (0.8.0):
  - Okul Zili'nin ikili eğitim dosyasında oturum kimlikleri ve adları (`day_schedules[].sessions`)
    yalnız uydurma örnekle ve şartnameden bilinir; gerçek dosyada devre adları "sabah"/"öğle" diye
    tanınmazsa iki devreli okulda erken başlayan devre sabah sayılır (duyuru devre süzgeci için).
  - Okulda sabah ve öğle devrelerinin dersleri zamanda çakışmıyor (çakışırsa o aralıkta teneffüs
    kilidi verilmez) ve bir şubenin aynı gün iki devrede dersi yok (varsa yoklamada ders saati serbest
    seçilir).
  - Öğretim yılı bitiş tarihinin geçmesiyle silme: saatlik imha kapalı sunucuda çalışmaz; tarih
    geçtiğinde sunucu kapalıysa silme ilk açılışta yapılır.

- Altyapı (0.7.0):
  - ETAP'ta `/sys/class/dmi/id/product_serial` ve `board_serial` dolu (üretici seri no yazıyor);
    boşsa donanım kimliği değişimi uyarısı çalışmaz (yalnız dolu→farklı dolu uyarır).
  - Dokunmatik aygıt adı `/proc/bus/input/devices` içinde "touch" sözcüğünü taşır.
  - `tahta-ariza.desktop` ETAP menüsünde (Donatılar/Utility) her hesapta görünür; ETAP'ın ekran
    klavyesi GTK metin alanına odaklanınca açılır.
  - Arıza penceresi (1920×1080'de 1240×860, ekrana orantılı; normal pencere) ETAP'ın 4K ve 1080p ekranlarında okunur; düğmeler
    dokunmaya yeterince iri. Pencere okulun renklerini değil varsayılan tahta paletini kullanır.
  - `dpkg-query` ETAP'ta birkaç saniyede biter (envanter açılışta ve 6 saatte bir okunur).
  - Okul ağında DNS adı tanımlanabiliyor ve tahtalar onu çözüyor (açık soru 51).
  - Sunucu IP'si değişince tahtaların 3 hata + üstel bekleme sonrası yaklaşık 1 dk içinde geçmesi
    (kapta birincil adres "ağ ulaşılamıyor" ile hızlı düştü; gerçek ağda bağlantı zaman aşımı
    45 sn'ye kadar sürebilir, geçiş birkaç dakikayı bulabilir).
  - Scrypt (n=2^17) parola belirleme ve geri yüklemede sunucu bilgisayarında 1 sn civarı sürer;
    200 MB'a yakın yedek ve büyük veritabanı bellekte işlenebilir.
  - Windows'ta ikinci kopya klasörüne yazma izni: Yedekler sayfasındaki `icacls` komutu 6A'da programı
    çalıştıran hesaba (`ALAN\kullanıcı`) izin verir; okulun etki alanı/yerel hesap düzeninde denenmedi.
  - Oturum temizliği (K7, 0.8.0; yalnız Debian 12 kabında Xvfb + openbox, sahte profil ve sahte
    tarayıcı süreciyle denendi):
    - ETAP'taki tarayıcılar ve profil yolları: Firefox ESR `~/.mozilla/firefox/<profil>/`, Chromium
      `~/.config/chromium/Default`; ETAP'a özgü ya da yerli bir tarayıcı varsa adı ve profil yolu
      listede yoktur (`tahta_ajan/temizlik.py::TARAYICI_PROFILLERI`, `TARAYICI_SURECLERI`) ve eklenmelidir.
    - Süreç adları (`/proc/<pid>/status` Name: firefox-esr, chromium, chrome …) ETAP paketlerinde aynı.
    - ETAP'ın pencere yöneticisi `_NET_CLIENT_LIST`, `_NET_CLOSE_WINDOW` ve `_NET_WM_PID`'i destekliyor;
      ekran klavyesi ve kenar çubuğu NORMAL dışı tür ya da `SKIP_TASKBAR` taşıyor (taşımıyorsa kapanır).
    - Firefox'un "birden çok sekmeyi kapat?" sorusu kibar kapatmayı durdursa da SIGTERM'le kapanır
      (sekmeler oturum dosyası silindiği için geri gelmez).
    - Bilgisini yalnız yerel depolamada (Local Storage/IndexedDB) tutan okul sistemi ya da site
      temizlikten sonra oturumu açık tutabilir; bunlar bilerek silinmez.
    - Servisin `subprocess(user=…)` ile yetki düşürmesi ETAP'ın Python sürümünde (3.9+) çalışır.
  - Windows hizmeti (K8, 0.8.0; gerçek hizmet kurulmadı, §3.7):
    - PyInstaller paketinde pywin32'nin hizmet barındırması (`servicemanager`) Yerel Hizmet hesabıyla
      çalışır; derleme duman testi yalnız "hizmet yöneticisi dışından 2 koduyla çıkar"ı sınar.
    - `sc create … obj= "NT AUTHORITY\LocalService"` Türkçe Windows'ta kabul edilir (hesap adı
      yerelleştirilmiş görünse de hizmet yöneticisi bu yazımı tanır).
    - `icacls` SID'leriyle verilen izinler okulun etki alanı ilkeleriyle ezilmez; antivirüs hizmeti ya
      da 8788 kuralını engellemez.
    - Kurucunun `taskkill` ile başka oturumlardaki eski programı kapatabildiği ve kapanan programın
      son yazılarının `-wal` dosyasıyla taşındığı (birim testinde WAL'lı veritabanıyla denendi).
    - Kurucu hesabının `{localappdata}`'sı, yönetici parolasını başka hesap girdiğinde o hesabın
      klasörüdür; bu yüzden bütün profiller taranır (`ProfileList`).
  - USB anahtar (0.11.0; yalnız Debian 12 kabında loop bellekle denendi, §3.10):
    - Bellek takılınca ETAP'ın oturumdaki dosya yöneticisi (udisks2) belleği kendiliğinden bağlar ve bağlama
      `/media/<hesap>/<etiket>` ya da `/run/media/<hesap>/<etiket>` altındadır; otomatik bağlama kapalıysa
      ya da merkezî yönetim USB depolamayı kısıtlıyorsa özellik çalışmaz (servis bilerek bağlamaz).
    - **Dosya yöneticisi penceresi kendiliğinden açılıyorsa anahtar dosyası herkese görünür — okulda denetlenecek.**
    - Gerçek USB belleğin `/sys/dev/block/MAJ:MIN` yolunda `/usb` geçer ya da diskin `removable` değeri 1'dir
      (kart okuyucu ve USB çoğaltıcı dahil); Docker'da yalnız `TAHTA_AJAN_USB_BENZETIM=1` ile `loop` kabul edildi.
    - exFAT/NTFS bellek (`fuseblk`, `ntfs3`) kök servisçe okunabilir; fuseblk'te asıl aygıt mountinfo'nun
      kaynak alanındaki `/dev/sdX1`'den çözülür.
    - `/proc/self/mountinfo` üzerinde `poll` ETAP çekirdeğinde bağlama değişikliğini bildirir (yoksa 5 sn'lik
      yedek yoklama devreye girer; tanıma en geç ~5 sn gecikir).
    - Köşedeki bildirim (override-redirect pencere) tam ekran sunumun üstünde görünür; XFCE'de odak çalmaz.
    - `tahta-kontrol.anahtar` adı ETAP'ın kendi "USB ile giriş" düzeninin dosya adıyla çakışmaz (doğrulanamadı).
    - 60 sn'lik "iki tahtada kısa arayla" eşiği derslikler arası yürüme süresinden kısadır.
  - e-Okul "Haftalık Ders Programları" raporu (0.12.0; bir okulun gerçek raporuyla denendi, §3.11):
    - Başka okulların raporu da aynı yerleşimdedir (ilk satır gün başlıkları, art arda bloklar, ders no
      1'e dönünce yeni şube, ikinci sütunda saat aralığı); Cumartesi sütunu, hazırlık sınıfı ve tek devreli
      okul örneği görülmedi.
    - XLS'teki blok sırası PDF'in sayfa sırasıyla aynıdır (örnekte öyleydi); değilse yapıştırılan liste
      blokları yanlış şubeye atar — kullanıcı ipuçlarını PDF'le karşılaştırmalıdır.
    - İki satırlı hücrenin ilk satırı ders adıdır (örnekte bütün iki satırlı hücrelerde öyleydi); tek
      satırlı hücrelerin ne taşıdığı kesin olmadığından ipucu alınmaz.
    - Raporun "Excel olarak kaydet" çıktısı her sürümde eski ikili biçimdedir (.XLS, OLE2); .xlsx gelirse de okunur.
  - Yüzer düğme ve öğretmen programı (0.13.x; §3.12):
    - ETAP'ın pencere yöneticisi yönetilen, keep_above + stick UTILITY pencereyi tam ekran uygulamanın
      üstünde tutar (kapta xfwm4/Mutter/Muffin tuttu, Openbox tutmadı; ETAP'ınki bilinmiyor).
    - Dokunmatik panel, dokunuşun ardından öykünülmüş fare basışını 0,7 sn içinde üretir; parmak titremesi
      28 px'in (1920×1080) altında kalır.
    - Başka okulların raporunda da seçmeli gruplar aynı hücrede çift boşluk, virgül, noktalı virgül ya da
      sekmeyle ayrılır (tek örnekte çift boşluktu); tek boşlukla ayrılırsa hücre belirsiz sayılır ve
      ders genel başlıkla yazılır.
    - Rapordaki aynı ad tek kişidir (adaş iki öğretmen yalnız aynı saatte farklı derste görünürse uyarılır).
  - Dayanaklar: KVKK md. 12 ve "yeterli önlemler" kararı doğrulanacaklar listesindedir
    (`docs/tasarim.md` §18); arayüzde atıf yoktur.

## 6. Sorun olursa

- Tahtada: `tahta-ajan durum`, `tahta-ajan tani`, `journalctl -u tahta-ajan -n 50`.
- Ajanı kaldırmak: `sudo apt remove tahta-ajan` (ya da `sudo dpkg -r tahta-ajan`).
- Kilit takılı kalırsa: sunucu hizmetini durdurun (yönetici komut isteminde
  `net stop TahtaKontrol`); 90 sn sonra tahtada "Kilidi aç" düğmesi çıkar. Klavye bağlıysa Ctrl+Alt+F3 ile metin uçbirimine geçip
  `sudo systemctl stop tahta-ajan` da kilidi kaldırır.
- Sunucu kayıtları (0.8.0, hizmet; yönetici olarak açın): `C:\ProgramData\TahtaKontrol\gunluk\sunucu.log`,
  ayrıca Olay Görüntüleyicisi > Windows Günlükleri > Uygulama (kaynak: TahtaKontrol). Taşıma sonucu:
  `C:\ProgramData\TahtaKontrol\gunluk\tasima.log`. Durum penceresinin kaydı:
  `%LOCALAPPDATA%\TahtaKontrol\pencere.log`. 0.8 öncesi: `%LOCALAPPDATA%\TahtaKontrol\sunucu.log`.
- Hizmet: `sc query TahtaKontrol`, `net stop TahtaKontrol`, `net start TahtaKontrol` (yönetici).
