# 0.13.1 — 0.13.0 inceleme bulgularının düzeltmesi

18 Kasım 2026. Geliştirme kopyası; kurulu hizmet ve bağlı tahta değiştirilmedi, dağıtılmadı.
Gerçek raporlar depoya/pakete eklenmedi, testler uydurma verilerle yazıldı. Tek yeni özellik sunucudaki yeni sürüm denetimidir.

**0.13.0 ile öğretmen programı aktarıldıysa 0.13.1'e geçtikten sonra program yeniden aktarılır**
(gerekçe aşağıda, "Öğretmen adı sızıntısı").

## Sunucu

- **Öğretmen adı sızıntısı (kritik).** e-Okul raporunda bir hücredeki birden çok seçmeli grup tek satırda,
  çift boşlukla ayrılmış "KİŞİ - DERS" parçaları olarak gelir. 0.13.0 boşlukları bölmeden önce
  sadeleştirdiği için ikinci kişinin adı ders başlığına karışıyor, ders başlığı da kilit ekranına
  gidiyordu. Hücre artık `ogretmen_program.hucre_coz` ile önce bölünür (`,` `;` sekme, iki ve daha çok
  boşluk). Bölündükten sonra hâlâ belirsiz kalan parça genel başlıkla yazılır, kişi eşlemeye alınmaz ve
  önizleme bunu yalnız sayıyla bildirir (kapalı hata). Bütün rapor okunduktan sonra ders adları rapordaki
  kişi adlarıyla da karşılaştırılır: ders adı, raporda kişi olarak görülen (en az iki sözcüklü) bir adı
  içeriyorsa genel başlığa iner ve o satır eşlemeye alınmaz. Önizleme artık aktarılacak FARKLI ders
  adlarının tamamını listeler (kilit ekranına gidecek metin onaydan önce görülür). Sınır: raporda hiçbir
  yerde kişi olarak geçmeyen bir ad ders konumunda yazılmışsa kod bunu ayırt edemez; bu listeyi insan okur.
- **Göç:** ders başlığında " - " geçen eski satırlar "Seçmeli ders" yapılır. Kaybolan ikinci grubun ders
  satırı göçle geri gelmez; bu yüzden yeniden aktarım gerekir. **Göç yalnız canlı veritabanını düzeltir:**
  veri dizinindeki `goc-oncesi` klasöründe duran 0.13.0 kopyası (`tahta-kontrol-v11-*.db`) ve 0.13.0 ile
  alınmış `.tkyedek` yedekleri eski ders başlığını (ikinci öğretmenin adıyla) taşımaya devam eder; program
  bunlara dokunmaz. 0.13.0 ile aktarım yapılmış kurulumda yeniden aktarımdan sonra bu kopya ve o yedekler
  elle silinir (karar ve işlem idarenindir).
- **Aynı adlı iki kaynak öğretmen:** aynı ad aynı gün ve saatte farklı derslerde görünüyorsa önizleme
  uyarır. Hiç çakışmayan iki adaş yine tek kişide birleşir (rapor ayırt etmiyor).
- **Kilit ekranı kutusu:** öğretmen programı hiç aktarılmamışsa ya da tahtanın şubesi yoksa kutu
  gönderilmez; "Bu tahtaya şube atanmamış." iletisi kalktı.
- **Önizleme belleği:** süresi dolan (15 dk) önizleme zamanlayıcıda silinir; "Vazgeç" belleği hemen
  boşaltır. Dosya ayrıştırma olay döngüsünü bekletmez.

- **Yeni sürüm denetimi (yeni).** Sunucu günde en çok bir kez GitHub'daki son sürüm kaydına bakar; yeni
  sürüm varsa panoda yalnız yöneticiye not ve sürüm sayfası bağlantısı çıkar. Kendiliğinden indirme/kurma
  yoktur. İstekle hiçbir bilgi (okul adı, tahta sayısı, kurulu sürüm) gönderilmez; tahtalar internete
  çıkmaz. Ayarlar › Güncelleme denetimi'nden kapatılır (kapalıyken hiç istek çıkmaz), "Şimdi denetle" ile
  elle çalıştırılır. İnternet yoksa sessizdir: panoda hata çıkmaz, yalnız Ayarlar'da "GitHub'a ulaşılamadı"
  yazar, sonraki deneme ertesi gündür. Bir denetim toplam en çok 5 sn sürer, kapanışı ve paneli bekletmez;
  yanıttaki bağlantı ve sürüm notu kullanılmaz (bağlantı sabit kalıptan kurulur). Yeni bağımlılık ve şema
  değişikliği yok. Ayrıntı: `docs/tasarim.md` §9.1 ve §15.7; `CLAUDE.md` kural 32.

## Tahta (ajan)

- **Yüzer düğme:** bütün çalışma alanlarında görünür (`stick`). Dokunuşun ardından gelen öykünülmüş fare
  basışı menüyü geri kapatmaz. Dokunmada sürükleme eşiği büyütüldü; iptal edilen sürüklemede düğme
  kenara yapışır. Girdi tutma (grab) ve POPUP pencere yine yoktur.
- **Kilit ekranında gün programı:** tahtanın tarihi sunucununkinden farklıysa program kaybolmaz, başlık
  sunucunun tarihini taşır. Sunucuya ulaşılamazken programın ömrü (gece yarısı) dolarsa servis bunu
  ekrana bir kez yayınlar; dünün programı kilit ekranında kalmaz. Program şimdiki ya da sıradaki dersin sayfasından açılır. Sunucunun iletisi
  dersler varken de görünür. Sayfa değişince tuş takımı ve düğmeler yer değiştirmez.

## Diğer

- CI iş akışındaki bozuk kodlanmış Türkçe adım adları düzeltildi; `scripts/dev.ps1` bilgisayara özgü yola
  bakmaz (uv PATH'te varsayılır).
- Belgeler: `CLAUDE.md` kural 12 ve 30'a 0.13.0 kararının istisnası yazıldı, kural 31 eklendi;
  `docs/tasarim.md` §12.5; `docs/saha-denemesi.md` §3.12.

## Doğrulama

- `uv run pytest -q`: 1039 geçti, 11 atlandı (Windows'ta PyGObject olmadığı için gerçek GTK testleri
  atlananlar arasında). `uv run ruff check .`: temiz.
- Debian 12 kabı (Xvfb, gerçek GTK): yüzer düğme ve kilit programı testleri geçti; `scripts/ekran_olcum.py`
  1024×768, 1366×768, 1920×1080 ve 3840×2160'ta "TAŞTI" ve "OYNADI" vermedi.
- Kapta dört pencere yöneticisiyle fare tıklaması ve sürüklemesi: xfwm4'te tamamı çalıştı; Mutter ve
  Muffin'de "masaüstünü göster" kipi düğmeyi gizledi; Openbox'ta düğme odaklı tam ekran uygulamanın üstüne
  çıkamadı (tablo: `docs/tasarim.md` §12.5).
- Kullanıcının gerçek XLS + PDF'i yalnız yerelde ayrıştırıldı (dosyalar depo dışında; yalnız sayılar):
  59 blok; çok gruplu 6 hücrenin 6'sı doğru bölündü; ders başlıklarının hiçbirinde ad ya da " - " yok.

## Denenmeyenler ve bilinen sınırlar

- **Gerçek ETAP tahtasında denenmedi.** ETAP'ın pencere yöneticisi bilinmiyor; gerçek dokunma olayı kapta
  üretilemedi, dokunma yolu yalnız taklit testlerle sınandı. Adımlar: `docs/saha-denemesi.md` §3.12.
- Deneme sunucusu yalnız yeni sürüm denetimi için (ayrı veri dizini, 8797/8798) çalıştırıldı; panel
  tarayıcıda açılmadı; kurucu ve `.deb` bu sürüm için üretilmedi.
- Yeni sürüm denetimi gerçek ağla yalnız geliştirme ortamında denendi. Kurulu programda (PyInstaller,
  Yerel Hizmet hesabı) ve vekil gerektiren ya da GitHub'ı engelleyen okul ağında denenmedi; orada beklenen
  sonuç Ayarlar'da "GitHub'a ulaşılamadı"dır (`docs/saha-denemesi.md` §3.13).
- "Masaüstünü göster" kipinde düğmenin gizlenmesine (xfwm4 dışında) önlem eklenmedi.
- Kilit ekranında uzun ileti iki satırda kesilir.
- Öğrenci listesi önizlemesi aynı depo sınıfını kullanır; zamanlayıcı temizliği ve "Vazgeç" ucu yalnız
  öğretmen programı önizlemesine eklendi.
