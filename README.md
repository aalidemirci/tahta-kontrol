# Tahta Kontrol

Okul ağında çalışan etkileşimli tahta kontrol ve duyuru sistemi. İnternet
gerektirmez; veri okulda kalır, dışarıya hiçbir şey gönderilmez.

> **Durum: 0.5.0, saha denemesi sürümü.** Debian 12 ve Pardus 25 masaüstünde denendi;
> gerçek bir Pardus ETAP tahtasında henüz denenmedi. Okul genelinde kullanmadan
> önce tek tahtada deneyin (`docs/saha-denemesi.md`).

## Ne yapar

- **Sunucu:** idaredeki bir Windows bilgisayarına kurulan masaüstü programı.
- **Panel:** idari bilgisayarlardan tarayıcıyla, kullanıcı adı ve parolayla açılır;
  başka bilgisayara kurulum gerekmez.
- **Ajan:** Pardus ETAP tahtalara kurulan küçük bir paket (`.deb`). Yalnız Python
  standart kitaplığını kullanır; tahtada internet ya da paket deposu gerekmez.

Bu sürümde: tahtaların durumunu izleme, kilitleme ve açma, tam ekran duyuru,
kapatma ve yeniden başlatma, saatli otomatik kapatma (enerji tasarrufu), saha tanılaması, ajanın
sunucudan güncellenmesi, kullanıcı yetkileri ve işlem kaydı. Panel ve tahta
ekranı okulun logosu ve renkleriyle biçimlendirilebilir; renkler hangi seçimde
olursa olsun okunur kalacak biçimde sunucuda hesaplanır.

0.3.0 ile:

- **Zamanlanmış duyuru:** hemen, ileri tarihte bir kez, günlük ya da haftalık;
  planlar duraklatılır, düzenlenir, çoğaltılır. Sunucu kapalıyken saati gelen
  gösterim süresi dolmadıysa kalan süreyle yayımlanır, dolduysa "kaçırıldı" diye
  bildirilir ve tek tıkla yeniden gönderilir.
- **Hedef grupları:** tahtalara bina, kat, düzey, devre ve şube bilgisi; elle
  seçilen gruplar; duyurunun kaç tahtaya ulaşacağı canlı önizlenir. Nitelikler
  CSV ile dışa ve içe aktarılır (Türkçe Excel uyumlu).
- **Acil durum ve tatbikat yayını:** ayrı yetkiyle, parola ve açık onayla
  başlatılır; bütün tahtalarda (kilitli olanlarda da) kırmızı ya da tatbikatta
  kehribar tam ekran görünür, tahtadan kapatılamaz (sunucuya ulaşılamıyorsa
  kapatılabilir). Panelin her sayfasında bant görünür; hangi tahtada ne zaman
  göründüğünü gösteren yazdırılabilir rapor üretilir. Bu yayın binanın yangın
  alarmı ya da anons sisteminin yerine geçmez.
- Duyuru ve acil metninde T.C. kimlik numarasına benzeyen sayı reddedilir
  (tahta herkese açık ekrandır).

0.4.0 ile:

- **Zil saatleri ve ders programı:** ders saatleri ve takvim Okul Zili'nin
  yapılandırmasından ya da yedeğinden alınır (Okul Zili'ne hiçbir şey yazılmaz);
  Okul Zili'si olmayan okul elle girer. Hangi derslikte hangi saatte ders olduğu CSV
  ile ya da tahta sayfasındaki haftalık tabloyla girilir; öğretmen ve ders adı
  alınmaz.
- **Programa bağlı kilit** (varsayılan kapalı): teneffüste ve dersliğin boş olduğu
  saatlerde tahta kilitlenir, derse girilecek saatte sunucu kapalı olsa bile
  kendiliğinden açılır; ekranda yalnız neden ve açılış saati yazar. Tahta bazında
  muafiyet, tarih aralıklı istisna ve "1 saat / bugün durdur" vardır.
- **Boş ders uyarısı** (varsayılan kapalı): programında ders olan tahta ders
  başladıktan sonra kapalı ya da kilitli kalırsa panelde uyarı; uyarılar dışa
  aktarılmaz ve 30 gün sonra silinir.

0.5.0 ile:

- **Sınav kipi:** Kelebek Sınav'ın Toplu Dağıtım Çizelgesi (Excel) yüklenir; salonlar
  tahtalarla eşleştirilir (önceki eşleşmeler ve derslik adları kendiliğinden önerilir).
  Salon tahtası başlangıçtan 10 dakika önce maskeli oturma listesini (ör. "Ah*** Yı**** …47"),
  başlangıçta büyük bir geri sayımı ve okulun sınav kurallarını gösterir; süre bitince
  kendiliğinden eski durumuna döner. Süre uzatma, erken bitirme ve salonda sınav kipini
  kaldırma panelden yapılır.
- **Sınav yoklaması:** gözetmen tahtada salon fişindeki 6 haneli kodu girip gelmeyen
  koltukları işaretler; idare aynı işi panelden yapabilir. Gözetmen kodu fişleri ve
  yazdırılabilir "Sınav Yoklama İcmali" panelden alınır.
- **Şube duyurusu:** sınavdan önce şube dersliklerinde "kim hangi salonda, hangi koltukta"
  listesi maskeli olarak gösterilir.
- Öğrencinin adı sunucuda saklanmaz (yalnız maske); tahtaya tam okul numarası gitmez;
  öğrenci listesi 30 gün sonra kendiliğinden silinir.

Planlananlar: ders yoklaması (`docs/tasarim.md`, yol haritası).

## Çalıştırma (geliştirme)

Python 3.12 ve [uv](https://docs.astral.sh/uv/) gerekir.

```
uv sync
uv run python -m tahta_sunucu
uv run pytest -q
```

Panel `http://127.0.0.1:8787` adresinde açılır. Windows kurulum dosyası
`packaging\windows\build.ps1` ile derlenir (PyInstaller ve Inno Setup 6).

## Güvenlik ve gizlilik

- Sunucu ile tahta arasındaki bağlantı şifrelidir; tahta, sunucuyu kurulumda
  kaydedilen sertifika parmak iziyle tanır.
- Tahta sunucuya kullanıcı adı göndermez; tanılama raporu kişisel hesap adı,
  dosya adı ya da ev dizini içermez.
- Sunucu arızası dersi engellemez: sunucuya ulaşılamazsa kilit (ve sınav ekranı) tahtadan
  açılabilir.
- Sınav listesinde ad soyad saklanmaz; tahtada yalnız maskeli ad, numaranın son iki hanesi,
  şube ve koltuk görünür. Liste tahtada diske yazılmaz ve 30 gün sonra sunucudan silinir.
- Panel dış kaynak (font, CDN, analitik) yüklemez; satır içi betik ve stil
  içermez, içerik güvenliği politikası (CSP) bunu zorlar. Logo yalnız PNG ya da
  JPEG olarak kabul edilir.
- Ajan paketi henüz imzalı değildir; sunucu bilgisayarını yetkisiz erişime karşı koruyun.
- Güvenlik açığı bildirimi için herkese açık kayıt açmak yerine depo sahibine
  GitHub üzerinden özel olarak ulaşın.

## Sorumluluk

Bu yazılım Millî Eğitim Bakanlığı, TÜBİTAK ya da Pardus projesiyle bağlantılı
değildir ve onlarca onaylanmamıştır. Tahtalara yönetici yetkili yazılım kurmadan
önce kurumunuzun bilgi işlem kurallarını gözetin. Yazılım olduğu gibi sunulur.

## Lisans

[PolyForm Noncommercial 1.0.0](LICENSE): ticari olmayan kullanım serbesttir.
