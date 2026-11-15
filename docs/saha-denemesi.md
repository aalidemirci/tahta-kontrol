# Saha denemesi kılavuzu (0.1.0)

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
| **Gerçek ETAP tahtası** | — | **Denenmedi** |
| Kurulum dosyasının başka bir bilgisayara kurulması | — | Denenmedi |
| Gerçek kapatma / yeniden başlatma / uzaktan açma | — | Denenmedi (kapta benzetim) |

## 1. Sunucuyu kurun

1. `dist\cikti\tahta-kontrol-0.1.0-windows-kurulum.exe` dosyasını sunucu olacak
   idari bilgisayara kurun (yönetici izni ister; güvenlik duvarında 8788 kapısını açar).
2. Açılan pencerede **Paneli aç** deyin; ilk kurulumda okul adını ve yönetici
   hesabını oluşturun.
3. **Ayarlar** sayfasında bu bilgisayarın adresine bakın. Tahtaların bu adrese
   ulaşabildiğini bir tahtanın tarayıcısından `https://ADRES:8788/saglik`
   açarak sınayın (sertifika uyarısı beklenir).
4. Ayarlar'da 4-8 haneli bir kilit kodu belirleyin.

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

## 6. Sorun olursa

- Tahtada: `tahta-ajan durum`, `tahta-ajan tani`, `journalctl -u tahta-ajan -n 50`.
- Ajanı kaldırmak: `sudo apt remove tahta-ajan` (ya da `sudo dpkg -r tahta-ajan`).
- Kilit takılı kalırsa: sunucu programını kapatın; 90 sn sonra tahtada "Kilidi aç"
  düğmesi çıkar. Klavye bağlıysa Ctrl+Alt+F3 ile metin uçbirimine geçip
  `sudo systemctl stop tahta-ajan` da kilidi kaldırır.
- Sunucu kayıtları: `%LOCALAPPDATA%\TahtaKontrol\sunucu.log`.
