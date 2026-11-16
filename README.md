# Tahta Kontrol

Okul ağında çalışan etkileşimli tahta kontrol ve duyuru sistemi. İnternet
gerektirmez; veri okulda kalır, dışarıya hiçbir şey gönderilmez.

> **Durum: 0.8.0, saha denemesi sürümü.** Debian 12 ve Pardus 25 masaüstünde denendi;
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
- **Boş ders uyarısı** (0.8.0'dan beri varsayılan açık): programında ders olan tahta ders
  başladıktan sonra kapalı ya da kilitli kalırsa panelde uyarı; uyarılar dışa
  aktarılmaz, öğretim yılı sonunda silinir.

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
  öğrenci listesi öğretim yılı sonunda kendiliğinden silinir.

0.6.0 ile:

- **Ders yoklaması:** öğretmen tahtada "Yoklama Al" kısayoluna ya da kilit ekranındaki
  "Yoklama al" düğmesine dokunur, 3 haneli öğretmen kodunu ve 6 haneli PIN'ini girer; şube ve
  ders saati programdan önerilir. Liste maskeli adlarla ("Ayşe Y.") gelir; öğretmen yalnız
  gelmeyenlere dokunur, onaylayıp kaydeder. Liste tahtaya yazılmaz, birkaç dakika dokunulmazsa
  kapanır.
- **Öğrenci listesi:** e-Okul'un sınıf listesi Excel çıktısı (ya da düz tablo) önizlenip
  aktarılır; yalnız şube, okul no, ad ve soyad saklanır.
- **Panel:** günün şube × ders saati ızgarası ("alınmadı" uyarısı programdan), kayıt düzeltme
  (gerekçeyle), tahta bozukken panelden yoklama, öğretmen kodları ve yazdırılabilir PIN pusulası,
  e-Okul girişine yardımcı icmal (yazdırma, kopyalanabilir metin, CSV) ve "e-Okul'a işlendi"
  işareti. e-Okul'a giriş idarece elle yapılır; Tahta Kontrol e-Okul'a bağlanmaz.
- Tahtadan alınan yoklama kâğıt yoklamanın yanında yardımcı kayıttır. Yoklama kayıtları öğretim
  yılı sonunda kendiliğinden silinir; bütün öğrenci ve yoklama verisi tek işlemle de silinebilir.

0.7.0 ile:

- **Şifreli yedek:** veritabanı ve sunucu sertifikası her gün bir kez, yedek parolasıyla
  şifrelenmiş tek dosya (`.tkyedek`) olarak yedeklenir; parola sunucuda saklanmaz (sunucu yalnız
  şifreleyebilir, açamaz). Saklama sayısı, ikinci kopya klasörü (başka disk ya da USB), elle yedek
  ve indirme vardır. Geri yükleme yalnız sunucu bilgisayarından, önizleme ve onayla yapılır; yeni
  bir bilgisayarda ilk kurulum sayfasından da başlatılabilir.
- **Sunucu adres listesi:** tahtalara en çok 5 adres (IP ya da okul DNS'indeki ad) bildirilir;
  tahta birincil adrese ulaşamazsa sıradakini dener ve ulaştığını kalıcı yapar. Sunucunun adresi
  değişecekse yeni adres önceden eklenir. Tahtada elle düzeltme: `sudo tahta-ajan sunucu ADRES`.
- **Tahta envanteri:** üretici, model, seri no, işlemci, bellek, disk, ekran, dokunmatik aygıt,
  işletim sistemi ve ajan sürümü tahtadan kendiliğinden gelir; demirbaş numarası panelden girilir;
  sıralanabilir tablo ve CSV. Seri numarası değişen ya da iki tahtada aynı görünen cihaz işaretlenir.
- **Arıza bildirimi:** öğretmen tahtanın menüsündeki "Arıza bildir" penceresinden türü seçip kısa
  açıklama yazar; sunucuya ulaşılamıyorsa kayıt tahtada bekler. İdare kaydı panelden de açar,
  "İnceleniyor / Çözüldü" diye izler; her değişiklik geçmişe düşer, kayıt silinmez.

0.8.0 ile:

- **İkili eğitim:** sabahçı ve öğlenci devrenin ayrı zil çizelgeleri; aynı tahtada sabah bir şube,
  öğle başka şube. Program kilidi, boş ders uyarısı, yoklama önerisi ve icmal devreyi gözetir
  (sabahın 3. dersi ile öğlenin 3. dersi karışmaz); duyuruda "Sabahçılar/Öğlenciler" süzgeci
  derslik programından da çalışır.
- **Öğretim yılı sonuna kadar saklama:** ders yoklaması, sınav listesi ve boş ders uyarıları,
  Ayarlar'da girilen öğretim yılı bitiş tarihi geçince silinir; tarih girilmemişse silinmez ve
  Ayarlar uyarır. Şifreli yedekler bu veriyi yedek saklama süresi kadar daha taşır.
- **Acil durum yayını** bütün idare kullanıcılarınca başlatılabilir (parola ve açık onayla).
- **Boş ders raporu:** tarih aralığı, tahta/derslik ve ders saatine göre; kişi adı içermez.
- **Gün sonu oturum temizliği** (varsayılan kapalı): ortak öğretmen/öğrenci hesabında açık
  pencerelere kapatma isteği gider, tarayıcılar kapatılır, yalnız çerez ve oturum dosyaları
  silinir; dosyalara, geçmişe ve kayıtlı parolalara dokunulmaz. Kullanılan tahtada 60 saniyelik
  uyarı ve "Vazgeç" çıkar. Yalnız Debian 12 kabında denendi.
- **Sunucu Windows hizmeti olarak çalışır:** bilgisayar açılınca, kimse oturum açmadan başlar;
  çökerse kendiliğinden yeniden başlar. Hizmet en az yetkili Yerel Hizmet hesabıyla çalışır;
  veri `C:\ProgramData\TahtaKontrol` klasöründedir ve sıradan kullanıcılar okuyamaz. Masaüstü
  kısayolu yalnız durum penceresini açar. Önceki sürümden yükseltirken veri ve sunucu
  sertifikası kurulumda kopyalanır; tahtalara ajan yeniden kurulmaz (`docs/saha-denemesi.md`
  §1.1). Gerçek hizmet kurulumu henüz yönetici yetkili bir denemede doğrulanmadı.

0.9.0 ile (ilk gerçek tahta denemesinin bulguları):

- **Tahtadaki yüzer düğme:** köşede küçük, soluk, parmakla taşınabilen bir düğme; dokununca
  Kilitle, Kapat, Yeniden başlat, Arıza bildir ve Yoklama al. Kapatma ve yeniden başlatma
  10 saniyelik onay ister; tahtadan kilitleme sunucu kapalıyken de çalışır. Hangi işlemlerin
  görüneceği Ayarlar'dan seçilir; her işlem işlem kaydına düşer (kullanıcı adı gönderilmez).
- **Kurulum öğretmen oturumunda da yapılabilir:** kurulum betiği yönetici yetkisini kendisi
  alır ve yönetici hesabının parolasını sorar (başına `sudo` yazılmaz).
- **Açılışta kilit:** tahta açılınca ya da oturum açılınca, sunucuya ulaşabiliyorsa tahta
  kendiliğinden kilitlenir ve öğretmen kilit koduyla açar; sunucuya ulaşılamıyorsa açık başlar
  (ders bölünmez). Yönetici (etapadmin) oturumu ve program kilidinin yönettiği ders saatleri
  hariçtir; program kilidi açıksa ders dışında (ilk dersten önce, teneffüste) verilen kilit bir
  sonraki dersin başında kendiliğinden açılır. Kilit kodu belirlenmemişse uygulanmaz. Ayarlar'dan
  kapatılabilir.
- Kilitli tahtanın kilidi yeniden başlatmada ve oturum değişince korunur.

## Çalıştırma (geliştirme)

Python 3.12 ve [uv](https://docs.astral.sh/uv/) gerekir.

```
uv sync
uv run python -m tahta_sunucu
uv run pytest -q
```

Panel `http://127.0.0.1:8787` adresinde açılır. Windows kurulum dosyası
`packaging\windows\build.ps1` ile derlenir (PyInstaller ve Inno Setup 6). Kurucu sunucuyu
Windows hizmeti olarak kaydeder (pywin32; ayrı bir hizmet aracı kullanılmaz).

## Güvenlik ve gizlilik

- Sunucu ile tahta arasındaki bağlantı şifrelidir; tahta, sunucuyu kurulumda
  kaydedilen sertifika parmak iziyle tanır.
- Tahta sunucuya kullanıcı adı göndermez; tanılama raporu kişisel hesap adı,
  dosya adı ya da ev dizini içermez.
- Sunucu arızası dersi engellemez: sunucuya ulaşılamazsa kilit (ve sınav ekranı) tahtadan
  açılabilir.
- Sınav listesinde ad soyad saklanmaz; tahtada yalnız maskeli ad, numaranın son iki hanesi,
  şube ve koltuk görünür. Liste tahtada diske yazılmaz ve öğretim yılı sonunda sunucudan silinir.
- Ders yoklamasında tahtada öğrenci yalnız maskeli adla görünür; liste tahtada diske yazılmaz.
  Öğretmen PIN'i sunucuda yalnız geri çevrilemez özet olarak durur ve tahtaya gitmez. Yoklama
  kayıtları öğretim yılı sonunda silinir; öğrenci listesi dışa verilmez.
- Panel dış kaynak (font, CDN, analitik) yüklemez; satır içi betik ve stil
  içermez, içerik güvenliği politikası (CSP) bunu zorlar. Logo yalnız PNG ya da
  JPEG olarak kabul edilir.
- Yedekler şifrelidir ve parola sunucuda durmaz; parola unutulursa yedek açılamaz. Yedekler,
  süresi dolunca silinen kişisel verinin kopyasını yedek saklama süresi kadar daha taşır.
- Envanter yalnız cihaz bilgisidir (hesap adı, dosya adı, makine adı girmez). Tahtadan gelen arıza
  kaydında kişi kimliği yoktur, yalnız hesap türü (öğretmen/öğrenci); tahtada hiçbir arıza metni
  gösterilmez.
- Sunucu hizmeti en az yetkili hesapla (Yerel Hizmet) çalışır; veritabanı, sertifika anahtarı ve
  yedekler yalnız yöneticilerin ve hizmetin erişebildiği klasördedir. Program kaldırılınca bu
  klasör silinmez.
- Ajan paketi henüz imzalı değildir; sunucu bilgisayarını yetkisiz erişime karşı koruyun.
- Güvenlik açığı bildirimi için herkese açık kayıt açmak yerine depo sahibine
  GitHub üzerinden özel olarak ulaşın.

## Sorumluluk

Bu yazılım Millî Eğitim Bakanlığı, TÜBİTAK ya da Pardus projesiyle bağlantılı
değildir ve onlarca onaylanmamıştır. Tahtalara yönetici yetkili yazılım kurmadan
önce kurumunuzun bilgi işlem kurallarını gözetin. Yazılım olduğu gibi sunulur.

## Lisans

[PolyForm Noncommercial 1.0.0](LICENSE): ticari olmayan kullanım serbesttir.
