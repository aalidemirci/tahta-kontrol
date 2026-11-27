# 0.22.0 — açılışta otomatik giriş

27 Kasım 2026. Geliştirme kopyası; okuldaki kurulu sunucu ve tahtalar değiştirilmedi, dağıtılmadı. Denemeler
uydurma veriyle ve geçici klasörde yapıldı; gerçek bir ETAP tahtasında denenmedi.

## Neden

Okulda 0.20.0 kurulu 24 tahtada bazı tahtalar panelde "Ekran yardımcısı yok" görünüyordu. Tahta açık ve sunucuya
bağlıydı, ama giriş ekranında bekliyordu. Oturum açılmadığı için tahtadaki ekran yardımcısı başlamamış; kilit,
duyuru ve acil yayın ekrana gelemiyordu.

Kullanıcı, uzaktan açılan tahtanın kendiliğinden öğretmen hesabıyla açılmasının sunucudan ayarlanmasını istedi.
Bunun için etapadmin parolasının panele girilmesini önerdi. Fizibilite incelemesinden sonra 27.11.2026'da
"0.22.0'ı yaz" dedi.

## Ne değişti

### Ayarlar › Kilit ve güvenlik › Otomatik giriş

Yeni bir kart; üç seçenek:

- **Tahtalardaki ayara dokunma** (varsayılan). 0.21.0 ile aynı davranış: tahtaya hiçbir şey gitmez, elle
  yapılmış ayar olduğu gibi kalır.
- **Öğretmen hesabıyla otomatik gir.** Tahta açılınca giriş ekranında beklemeden `ogretmen` oturumuna girer.
  Ekran yardımcısı başlar, açılışta kilit tahtayı kilitler.
- **Otomatik girişi kaldır.** Tahta Kontrol'ün yazdığı ayar silinir; tahta yine giriş ekranında bekler.

Önemli noktalar:

- **etapadmin parolası istenmez.** Tahtadaki Tahta Kontrol servisi zaten yönetici yetkisiyle çalışır ve ayarı
  kendisi yazar. Parola panele, sunucuya ya da tahtaya gitmez.
- **Kilitsiz açılmasın diye** "Öğretmen" yalnız kilit kodu tanımlıyken ve açılışta kilit açıkken kaydedilir.
  Bu koşullardan biri sonradan kalkarsa ayar değişmez. Bunun yerine Bugün › Sizi bekleyenler'de yöneticiye
  uyarı çıkar ve Ayarlar kartında bant görünür. Uyarı, ayar "Dokunma"ya alınmış olsa da Tahta Kontrol ayarını
  hâlâ taşıyan tahtaları sayar: "Dokunma" tahtadaki ayarı silmez, silmek için "Otomatik girişi kaldır" seçilir.
  Sunucuya ulaşılamıyorsa tahta yine kilitsiz açılır (kural 3).
- **Yalnız öğretmen hesabı.** etapadmin ve kişisel hesaplar hiçbir koşulda seçilemez. Tahta da kendi listesiyle
  ayrıca denetler.
- **Bir sonraki açılışta geçerli olur.** Giriş ekranı yeniden başlatılmaz; açık tahtanın dersi bölünmez.
- **Kart sayıları.** Kart, kaç tahtada uygulandığını, kaçının beklediğini ve kaç tahtada ajanın güncellenmesi
  gerektiğini gösterir.

### Tahta sayfası

Bakım › Bağlantı ve ajan'da yeni bir **Otomatik giriş** satırı var. Tahtanın bildirdiği etkin hesabı gösterir:
öğretmen, öğrenci, etapadmin ya da "kişisel hesap"; kişisel hesabın adı gösterilmez. Satır ayrıca şunları söyler:

- ayar Tahta Kontrol'ün mü, elle mi yapılmış;
- başka bir ayar Tahta Kontrol ayarını eziyor mu;
- ayar uygulanamadıysa nedeni.

### Tahtadaki program (ajan) değişti

- Tahta, LightDM'in ayar dosyalarını LightDM'in okuduğu sırayla okur ve etkin otomatik giriş hesabını bulur.
- Tek bir dosya yazar: `/etc/lightdm/lightdm.conf.d/50-tahta-otomatik-giris.conf`. Elle deneme betiği
  `otomatik-giris.sh` de aynı dosyayı yazar.
- "Kaldır" yalnız bu dosyayı siler, o da yalnız Tahta Kontrol imzası taşıyorsa. Başka dosyalara dokunulmaz.
- Ayar en geç 10 dakikada bir yeniden uygulanır; elle silinen dosya geri gelir.
- Değişiklik işlem kaydına "Tahta olayı" olarak düşer.
- Paket kaldırılırsa dosya da silinir: ajan kalkınca açılışta kilit de kalkar.
- Tanılamanın "Giriş ekranı" satırı etkin hesabı da yazar; artık `/etc/xdg/lightdm` dizinini de okur.

**Ajan güncellemesi bu özellik için gereklidir.** Güncellemek yine isteğe bağlıdır; güncellenmeyen tahta bu
ayarı uygulamaz, öbür her şey eskisi gibi çalışır. Veritabanına göç eklenmedi.

## Bilinen sınırlar

Gerçek ETAP'ta denenmedi; denenecekler `docs/saha-denemesi.md` §4'te (O1–O9):

- **EBA ve USB girişi.** Giriş ekranı atlandığı için EBA karekodu ve USB ile giriş ilk açılışta görünmez.
  Kişisel hesabıyla girecek öğretmen önce "Çık" der; giriş ekranı gelir ve tahta yeniden kendiliğinden girmez.
- **Kablosuz ağ.** Tahta kablosuz ağla bağlanıyorsa ağ giriş ekranında açılıyor olabilir.
- **ETAP'ın USB yardımcısı.** USB ile kilitleme ve öğrenciye geçiş etkilenebilir (çıkarım).
- **LiderAhenk.** Merkezî yönetim oturumu sonlandırabilir.

**Öneri:** ayarı bütün okulda açmadan önce bir tahtada deneyin. Yeni ajanı yalnız o tahtaya kurun; öbür tahtalar
güncellenmedikçe ayarı uygulamaz.

## Varsayılan kararlar

Kullanıcı ayrıca yanıtlamadı; `docs/tasarim.md` §17 soru 136–145:

- yalnız `ogretmen` hesabı;
- varsayılan "dokunma";
- kilit kodu ya da açılışta kilit yokken kaydetme reddi, sonradan bozulursa yalnız uyarı;
- tahta başına istisna yok;
- elle yapılmış ayara dokunulmaz;
- paket kaldırılınca dosya silinir.

Tasarım §5'teki "otomatik giriş bu yazılımca ayarlanmaz" kararı kullanıcı isteğiyle değişti (§5.2).

## Denendi

- Birim testleri: sunucu, ajan, okuma sırası, sembolik bağ, imzasız dosya, servis akışı. Bütün test takımı
  geçti.
- Bağımsız çok ajanlı inceleme (dört boyut, her bulgu ayrıca doğrulandı). Doğrulanan tek bulgu düzeltildi:
  "Dokunma"ya alınınca tahtada kalan ayar için kilit uyarısı çıkmıyordu.
- Deneme sunucusunda başsız tarayıcıyla Ayarlar kartı ve tahta sayfası (uydurma veri).

Yayımdan sonra (27.11.2026) kullanıcı özelliği okulda bir ETAP tahtasında denedi ve çalıştığını bildirdi.
Çok tahtayla kullanım ve `docs/saha-denemesi.md` §4'teki O4–O9 henüz denenmedi.
