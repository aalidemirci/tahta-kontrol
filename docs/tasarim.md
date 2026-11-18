# Tahta Kontrol — tasarım

Sürüm 0.5.0 · 16.11.2026

## 1. Amaç ve kapsam

Okul idaresinin etkileşimli tahtaları tek panelden yönetmesi: durum izleme,
kilitleme, duyuru, kapatma; orta vadede kelebek sınav duyurusu, sınav yoklaması
ve ders yoklaması. Veri okulda kalır, internet gerekmez
(internete çıkan tek iş, kapatılabilen yeni sürüm denetimidir: §9.1).

Benzer amaçlı bir kiosk tarayıcı denemesinden çıkan dersler tasarıma işlendi:
sunucudan tahtaya komut kanalı, işletim sistemi oturumunun üstünde duran kilit,
cihaz anahtarının yalnız özetinin saklanması ve internete muhtaç olmayan kurulum.

## 2. Bileşenler

| Bileşen | Nerede | Teknoloji |
|---|---|---|
| Sunucu | İdaredeki bir Windows bilgisayarı; Windows hizmeti (0.8.0, §15.6) | Python 3.12, FastAPI, SQLite, Jinja2, pywin32 (yalnız hizmet kabuğu) |
| Panel | Herhangi bir idari bilgisayarın tarayıcısı | Sunucunun sunduğu web sayfaları |
| Ajan servisi | Her tahta, yönetici yetkisiyle | Python standart kitaplığı, systemd |
| Ekran yardımcısı | Her tahta, oturumdaki kullanıcıyla | PyGObject / GTK3 |

Sunucu iki kapı açar: `127.0.0.1:8787` (şifresiz, yalnız sunucu bilgisayarı) ve
`0.0.0.0:8788` (HTTPS, okul ağı ve tahtalar).

## 3. Sunucu–tahta iletişimi

- Bağlantıyı her zaman tahta açar. Ajan `/ajan/bekle` isteğini atar; sunucu
  komut gelene kadar en çok 25 saniye bekletir, komut gelince hemen yanıtlar.
  Böylece komutlar anında iner ve tahtada açık kapı gerekmez.
- Ajan her istekte durumunu (kilitli mi, duyuru var mı, oturum sınıfı, ekran
  yardımcısı bağlı mı) ve bekleyen komut sonuçlarını gönderir.
- Tahtadaki değişiklik (kodla kilit açma gibi) beklemeden ayrı bir istekle bildirilir.
- Tahtalar ve idari bilgisayarlar çoğu okulda farklı alt ağlardadır; otomatik
  keşif (mDNS/yayın) alt ağlar arasında çalışmaz. Bu yüzden sunucu adresi
  kurulum betiğine gömülür; iki ağ arasında yönlendirmenin açık olması yeterlidir.

## 4. Güven modeli

- **Sunucunun kimliği:** sunucu ilk açılışta 20 yıllık bir sertifika üretir.
  Kurulum betiği sertifikanın SHA-256 parmak izini taşır; ajan zincire değil bu
  parmak izine güvenir. Parmak izi tutmayan sunucuya veri gönderilmez.
- **Tahtanın kimliği:** kayıt sırasında üretilen rastgele anahtar. Sunucuda yalnız
  özeti saklanır. Tahta panelden kaldırılınca anahtar geçersizleşir.
- **Kayıt:** panelde "tahta ekleme" 60 dakikalığına açılır ve 8 haneli kod üretilir.
  Kodla kaydolan tahta **onay bekler**; yönetici ad ve derslik verip onaylamadan
  komut almaz. Adres başına 10 dakikada 10 kayıt denemesi sınırı vardır.
- **Panel:** oturum çerezi (HttpOnly, SameSite=Strict), parolalar scrypt ile,
  POST isteklerinde kaynak denetimi, adres başına giriş denemesi sınırı. İki yetki:
  yönetici ve idareci. Her işlem silinemeyen işlem kaydına düşer.
- **İlk kurulum** yalnız sunucu bilgisayarından (127.0.0.1) yapılabilir.
- **Bilinen sınır:** ajan paketi imzalı değildir; güncellemenin güvenliği sunucu
  bilgisayarının güvenliğine eşittir. Paket imzası (sürüm anahtarı sunucuda değil, derleyenin
  bilgisayarında; tahtada saf Python Ed25519 doğrulaması) sonraya bırakıldı; 0.8.0'da yoktur (K8, §15).
- **Sunucu adres listesi** (§15.2) bu modeli değiştirmez: tahta listedeki her adreste aynı
  parmak izini arar; parmak izi tutmayan adrese tek bayt veri gitmez.

## 5. Kilit

- Kilit, oturumun üstünde duran tam ekran bir penceredir; X11'de klavye ve fare
  pencereye bağlanır. İşletim sisteminin giriş ekranı değildir ve ETAP'ın EBA
  karekod/USB girişine dokunmaz.
- Öngörülen kullanım: tahta `ogretmen` ortak hesabına otomatik açılır, kontrolü
  bu katman sağlar. Otomatik giriş bu yazılımca **ayarlanmaz**; saha denemesinde
  elle kurulup sınanacak.
- Açma yolları: panelden; tahtada okul genelinde ortak kilit koduyla (özeti
  tahtada durur, sunucu kapalıyken de çalışır; 5 hatalı denemede 60 sn bekleme);
  sunucuya ulaşılamıyorsa kodsuz düğmeyle.
- Ortak kod sınıfın önünde girilir ve görülebilir; 0.4.0'dan beri teneffüs kilidi
  derse girilecek saatte kendiliğinden açılır (§12), böylece kod daha az girilir.
  Yoklama anında öğretmen PIN'i sonraki aşamadır.
- **Kilidin kaynağı:** panelden verilen kilit "idare" kilididir ve süresizdir; ders
  programından gelen kilit "program" kilididir ve süresi tahtada sayılır (§12).
  İdare kilidi program kilidini ezer; program kilidi ve program açması idare kilidine
  dokunmaz.

### 5.1 Tahtadaki yüzer düğme ve tahtadan kilitleme (0.9.0)

İlk gerçek ETAP denemesinin (16.11.2026) üç bulgusu:

| # | Bulgu | Karar |
|---|---|---|
| G1 | Kurulum ve otomatik giriş betikleri `sudo` ile yönetici parolası istiyor; `ogretmen` oturumunda uçbirim **öğretmen** parolasını soruyor (`sudo` çağıran hesabın parolasını sorar; `ogretmen` sudo yetkili değildir). | Betikler yetkiyi kendileri alır (aşağıda). Yönergede `sudo` yazılmaz. |
| G2 | "Tahta açıkken oturumu kapatıp açınca da yeniden başlatınca da otomatik kilitlenmiyor." Kusur değil, istenen yeni davranış: sunucuya ulaşılabiliyorsa açılışta kilitlensin, ulaşılamıyorsa açık kalsın. | **Açılışta kilit** (aşağıda). Kilitli tahtanın kilidi zaten kalıcıdır: servis yeniden başlasa ya da tahta yeniden açılsa da idare kilidi korunur (`durum.json`), yardımcı bağlanır bağlanmaz kilit ekranı gelir (Docker'da doğrulandı). Giriş ekranında kilit olmaması bilinen sınırdır (kilit oturumun üstündedir, §5). |
| G3 | Tahtadan kilitlemenin yolu yok; "ekranda bir yüzer düğme olsa: kilitlemek, bilgisayarı kapatmak vb." | Yüzer düğme (aşağıda). |

**Açılışta kilit (G2)** — tahta açılınca ya da tahtada oturum açılınca, sunucuya ulaşılabiliyorsa
tahta kendiliğinden kilitlenir; öğretmen kilit koduyla açar. Kararı **sunucu** verir; böylece "sunucuya
ulaşılamıyorsa açık kalır" (kural 3) ayrıca kodlanmaz:

- Ekran yardımcısı `merhaba` iletisinde kendi sürecinin başlangıcını bildirir (`oturum_baslangic`:
  açılıştan saniye, `/proc/self/stat`). Servis, bilinen oturumdan daha geç başlamış bir yardımcı
  görünce yeni bir **rastgele** oturum kimliği üretir (kullanıcı adı değil) ve durumda `oturum_no` ile
  `oturum_yasi_sn`'yi (açılış sayacıyla; tahta saatine dayanmaz) bildirir. Aynı yardımcının yeniden
  bağlanması ya da güncellemede `execv` ile kendini yeniden başlatması aynı başlangıcı bildirir:
  oturum değişmez (güncelleme ders ortasında kilitlemez). Oturum `durum.json`'da açılış kimliğiyle
  (`boot_id`) saklanır: aynı açılışta servis yeniden başlasa da aynı oturum sürer.
- Sunucu (`tahta_sunucu/acilis_kilidi.py`) bir tahtada önceki durumdakinden farklı `oturum_no` görünce
  **bir kez** değerlendirir (eşzamanlı iki istekte de bir kez: `program_isaret` tablosuna `oturum|<no>`
  işareti tek yazılır); uygunsa `kilitle {}` komutu verir (ömür 120 sn) ve işlem kaydına kullanıcı
  "sistem", "Açılışta kilit" düşer. Aynı oturum yeniden kilitlenmez (kodla ya da panelden açılan tahta
  açık kalır).
- Uygulanmaz: Ayarlar › **Açılışta kilit** kapalı (varsayılan açık); kilit kodu belirlenmemiş (kodsuz
  kilit tahtayı panelden açılana kadar rehin alırdı; Ayarlar'da uyarı çıkar); oturum 120 sn'den
  yaşlı (ağ geç geldi, ders başlamış olabilir); oturum sınıfı `etapadmin` (bakım) ya da oturum yok;
  tahta zaten kilitli; acil yayın sürüyor; tahta sınav penceresinde (ya da program kilidi uygulanırken
  pencereye 10 dk'dan az var); program kilidi bu tahtayı yönetiyor ve tahta şu an derste ya da dersi
  3 dk içinde başlıyor (derste açık kararı program kilidinindir).
- **Program kilidiyle birlikte:** program kilidi bu tahtayı yönetiyorsa (kural etkin, tahta yetenekli ve
  muaf değil, istisna yok, ders günü, son dersin bitişinden önce) ve tahta derste değilse (ilk dersten
  önce, teneffüs, öğle arası, dersi olmayan saat) açılışta kilit **süreli program kilidi** olarak verilir:
  tahtanın bir sonraki dersinin başında kendiliğinden açılır (kayıtta "…'de açılır"). Süresiz idare kilidi
  verilmez: program açması idare kilidine dokunmadığı için sabah açılan tahta 1. derste kilitli kalırdı;
  ajan yeniden açılınca program kilidini bilerek geri yüklemediği için de teneffüste yeniden başlayan tahta
  aralık sonuna dek açık kalırdı (0.9.0 incelemesi). Program turu aynı aralık için ikinci kez kilit vermez
  (aralık işareti yazılır). Son dersten sonra, hafta sonu ve tatilde program yönetmez: idare kilidi.
- Eski ajan alanları göndermez: davranış yok (Ayarlar'da güncellenmesi gereken tahta sayısı yazar).
  Yetenek: `acilis_kilidi`.
- Docker denemesinde bulunan ve düzeltilen yarış: ajan yeniden başlayınca eski (ölü) bağlantının uzun
  beklemesi sunucuda 25 sn'ye kadar açık kalır ve süresi dolunca bekleyen komutu "gönderildi" diye
  alıp kaybediyordu. Yerini daha yeni bir uzun bekleme alan bağlantı artık komut almaz; açılış
  komutu verilince tahtanın güncel uzun beklemesi uyandırılır.

**Yetki alma sırası (G1)** — `tahta_sunucu/ajan_paket/kur.sh` ve `araclar/otomatik-giris.sh` (depoda
izlenmeyen yardımcı betik) aynı sırayı izler: (a) zaten root ise devam; (b) çağıran hesap sudo yetkiliyse
(`sudo -n true` ya da `sudo`/`admin`/`wheel` grubu) `sudo` — o hesabın kendi parolası; (c) değilse ve
grafik oturum + `pkexec` varsa `pkexec` — polkit yönetici hesabını (`etapadmin`) seçtirip onun parolasını
pencerede sorar; pencere kapatılır ya da doğrulama olmazsa (126/127) (d)'ye geçer; (d) `su` ile yönetici
hesabı (`etapadmin` varsa o, yoksa `root`) ve ekrana **hangi hesabın** parolasının istendiği yazılır;
`su etapadmin` içinden `sudo` aynı parolayı bir kez daha sorabilir. `su -c` komutu denetim uçbirimi
olmadan çalıştırdığı için `su --pty` kullanılır (eski `su`'da `sudo -S`). (e) Hiçbiri olmazsa "Bu
işlemi etapadmin oturumunda yapın". Parolayı `sudo`/`pkexec`/`su` sorar; betik görmez, saklamaz.
Eşleştirme kodu denetimi yetkiden önce yapılır (kodsuz çağrıda parola sorulmaz).

**Yüzer düğme (G3)** — ekran yardımcısında (GTK3) küçük, yuvarlak, yarı saydam, hep üstte, görev
çubuğunda görünmeyen ve odak çalmayan (klavye girişini kesmez) bir düğme; parmakla sürüklenir, kenara
yapışır, konumu oturum boyunca hatırlanır; varsayılan sağ alt köşe. Ölçüleri ekran ölçeğinden türetilir
(sabit piksel yok). Tam ekran video/sunumda rahatsız etmemesi için küçük ve soluktur, dokununca belirginleşir.
Dokununca yanında ekrana sığan yönde küçük bir menü açılır. 0.12.2 geliştirmesinde
ETAP girdisi için POPUP yerine çerçevesiz, odak almayan TOPLEVEL/UTILITY pencereler
kullanılır; yüzer düğme ve menü seat grab yapmaz. Menü düğmeye yeniden dokunarak,
"Menüyü kapat" ile veya 12 saniyelik zaman aşımıyla kapanır; masaüstünün dış
dokunuşlarını yakalamaz. Dokunma dizisi doğrudan işlenir; fare öykünmesi şart değildir.
Bu değişiklik GTK taklidiyle doğrulandı, gerçek ETAP kabul denemesi bekliyor:

| İşlem | Davranış |
|---|---|
| Kilitle | Hemen kilitler; **yerelde** çalışır (sunucu kapalıyken de). Bu kilit idare kilidiyle aynıdır (ayrı tür değil): panelde "Kilitli", açma yolları aynı (panel, kilit kodu, sunucuya 90 sn ulaşılamazsa kodsuz). Kilit kodu belirlenmemişse tahtadan kilitlenen tahta yalnız panelden açılabileceği için menüde soluk "Kilitle (kilit kodu belirlenmemiş)" görünür ve kilitlemez. |
| Kapat, Yeniden başlat | 10 sn geri sayımlı, Vazgeç düğmeli onay (yanlış dokunuşa karşı); servis mevcut kapatma yolunu uygular (benzetim kipine saygı). |
| Arıza bildir, Yoklama al | Özellik açıksa; mevcut arıza penceresi ve yoklama akışı. |

Kilit, duyuru, acil, sınav, gözetmen, yoklama ve kapatma uyarısı gibi tam ekran sayfalar varken
düğme gizlenir. `etapadmin` ve kişisel hesap oturumlarında da aynı işlemlerle görünür. Program
kilidi, sınav kipi ve acil yayının önceliği değişmez (yerel kilit program kilidini ezer, tıpkı
panelden verilen idare kilidi gibi).

Sunucu tarafı: Ayarlar › **Tahtadaki yüzer düğme** (`bolum=dugme`, anahtar `tahta_dugmesi`): düğme
açık/kapalı (varsayılan açık) ve işlem kutuları — Kilitle (açık), Kapat (açık), Yeniden başlat
(**kapalı**), Arıza bildir (açık), Yoklama al (açık). Ayar her `/ajan/bekle` yanıtında durum tabanlı
iner: `ayar.dugme = {"acik": bool, "islemler": [...]}` — `islemler` menü sırasıyla **etkin** listedir
(ders yoklaması kapalıysa `yoklama` çıkarılır; hiçbir işlem kalmazsa `acik: false`). Alan hiç yoksa
(eski sunucu) ajan düğmeyi göstermez; eski ajan alanı yok sayar. Yetenek: `durum.yetenekler` içinde
`dugme`; tahta sayfasında "Yüzer düğme için ajan güncellenmeli" notu buradan çıkar.

Tahtadan yapılan işlemler sunucuya mevcut olay yoluyla (`durum.olaylar`, düz metin) bildirilir ve
işlem kaydına "Tahta olayı" olarak düşer: "Tahtadan kilitlendi.", "Tahtadan kapatıldı.", "Tahtadan
yeniden başlatıldı." (ardına yalnız hesap sınıfı eklenebilir: "(oturum: ogretmen)"); kullanıcı adı
gönderilmez. Sunucu olay başına en çok 300 karakter, istek başına en çok 20 olay yazar. Kilit durumu
ayrıca bir alan gerektirmez: ajanın bildirdiği `durum.kilitli`/`kilit_kaynak: "idare"` panele yansır.

## 6. Duyuru

Tahtada tam ekran başlık + metin; süre dolunca kalkar; istenirse öğretmen
tahtadan kapatabilir. Kalan süre sunucuda hesaplanır (tahta saatine güvenilmez).

- **Tek yayın yolu.** Panodan hemen gönderilen, plandan doğan ve "yeniden
  gönder"ilen her gösterim `duyuru.duyuru_yayimla` ile çıkar: bir `duyuru` satırı
  (yayın) yazılır, hedef o anda çözülür, her tahtaya ömrü yayının bitişine eşit bir
  `duyuru` komutu eklenir. Komut çevrimdışı tahtaya da yazılır: süre içinde açılan
  tahta kalan süreyle alır, süre geçerse komut düşer. Ajan tek duyuru tutar; sonra
  gelen öncekinin yerine geçer (yığın tutulmaz).
- **Planlar.** Bir kez (tarih + saat), günlük (isteğe bağlı hafta sonu) ya da haftalık
  (seçili günler); başlangıç ve bitiş tarihi, en çok bir yıl. Plan tarihleri ve saati
  yerel saattir (Europe/Istanbul); her gösterim anı epoch'a o an çevrilir. Planlar
  duraklatılır, sürdürülür, düzenlenir, çoğaltılır, silinir (silinen plan kayıtta kalır,
  listelenmez). Başkasının planını yalnız yönetici değiştirir.
- **Zamanlayıcı** 20 saniyede bir ve sunucu açılırken çalışır; en çok 7 gün geriye
  bakar. Gösterim en çok ~20 sn geç başlar.
- **Kaçırma kuralı = duyurunun kendi süresi.** Sunucu kapalıyken (ya da uykudayken)
  saati gelen gösterim, süresi dolmadıysa kalan süreyle yayımlanır; dolduysa
  yayımlanmaz, "Kaçırıldı — sunucu kapalıydı" diye kaydedilir, panoda 24 saat not
  görünür ve tek tıkla yeniden gönderilir. Gerekçe: süresi geçmiş duyurunun geç
  gösterilmesi yanlış bilgi verir ("teneffüste toplanınız" öğleden sonra çıkmamalı).
  7 günden uzun kesintide tek "uzun kesinti" kaydı düşer.
- **`gecerlilik`:** plan oluşturulunca, düzenlenince ve sürdürülünce o an yazılır;
  daha önceki anlar ne yayımlanır ne kaçırıldı sayılır (10:05'te kurulan "her gün
  10:00" planı bugün yarım gösterim yapmaz; duraklatma süresi kaçırma sayılmaz).
  Aynı plan-an çifti benzersizdir: sunucu saati geri alınsa da iki kez yayımlanmaz.
- **Durdurma:** yayındaki gösterim panelden durdurulur; bekleyen komutlar iptal edilir,
  gösteren tahtalara kimlikli `duyuru_kaldir` gider. Ajan yalnız ekrandaki duyuru o
  kimlikteyse kaldırır (yerine başka duyuru geçtiyse dokunmaz). Plan duraklatma ya da
  silme o an yayındaki gösterimi durdurmaz.

### 6.1 Hedef

Tahtaya dört yapısal nitelik verilir — **bina** (serbest metin), **kat** (2. bodrum …
20. kat), **düzey** (hazırlık, 9–12; birden çok), **devre** (sabah, öğle, sabah ve
öğle) — ve dersliğin şube(ler)i (sonraki aşamalar için). Ayrıca adlandırılmış,
üyeleri elle seçilen **gruplar** vardır ("Fen laboratuvarları"). Ayrı bir etiket
kavramı yoktur: iki benzer kavram kullanıcıyı şaşırtır.

Hedef "tüm onaylı tahtalar" ya da şu birleşimdir: **tek tek seçilen tahtalar ∪
grup üyeleri ∪ süzgeç**. Süzgeçte dolu satırların hepsi sağlanmalı (VE), bir satırın
değerlerinden biri yeter (VEYA); "sabah ve öğle" devreli tahta sabaha da öğleye de
uyar; niteliği boş tahta o ölçüte hiçbir zaman uymaz — bir istisnayla (0.8.0): ikili eğitimde
"devre" alanı boş tahtanın devresi derslik programından türetilir (`program.tahta_devreleri`:
sabah ve öğle devresinde dersi olan tahta ikisine de uyar; ders saati devreleri adlarından,
adlar söylemiyorsa erken başlayan sabah sayılarak eşlenir). Elle girilen alan programdan önce
gelir; tek devreli okulda türetme yapılmaz. Hedef plan kaydında değil
**gösterim anında** çözülür: gruba sonradan eklenen tahta sonraki gösterimi alır.
Formda kaç tahtaya ulaşılacağı canlı önizlenir; hemen gönderimde 0 tahta reddedilir,
planda kaydedilir ve uyarılır.

Nitelikler tahta sayfasından tek tek ya da CSV ile toplu doldurulur. Dışa aktarma
UTF-8 BOM'lu, `;` ayraçlı (Türkçe Excel); içe aktarma önce `utf-8-sig`, olmazsa
`cp1254` dener, önce önizler, "Uygula"da yeniden ayrıştırır ve tek işlemde uygular.
Dosyada olmayan sütuna dokunulmaz, boş hücre alanı temizler. CSV'ye IP/MAC yazılmaz;
formül gibi başlayan hücreler kaçışlanır.

**Kişisel veri:** duyuru metnine yazılımca ayırt edilebilen tek kişisel veri olan T.C.
kimlik numarası (denetim haneleri tutan 11 hane) reddedilir; formda kalıcı "öğrenci adı,
numarası ya da kişisel bilgi yazmayın" notu vardır.

## 7. Acil durum ve tatbikat yayını

Bütün yönetici ve idareciler (16.11.2026 kararı; 0.8.0'a kadar ayrı `acil_yetki` vardı,
göçle herkese verildi ve sütun artık okunmaz, yalnız eski sürüme dönüşte aynı davranış sürsün
diye yazılır) parolanın yeniden girilmesi ve türe göre değişen açık onayla başlatır. Tür (gerçek acil durum /
tatbikat) varsayılansızdır. Yayın bütün onaylı tahtalara gider, en çok 120 dakika
sürer, panelden bitirilir (parola istenmez: bitirmek güvenli yöndür) ya da süresi
dolunca kendiliğinden kalkar. Yeni yayın, süren yayını bitirir. Kayıtlar silinmez.

- **Komut değil durum.** Süren yayın her `/ajan/bekle` yanıtında `ayar.acil` olarak
  yeniden hesaplanır (`null` ya da `{id, tur, baslik, metin, kalan_sn}`). Gerekçe:
  çevrimdışıyken kaçıran, ajanı yeniden başlayan ya da bitişi duymayan tahta bir sonraki
  turda kendiliğinden doğru duruma gelir; komut tablosu şişmez; bitiş bütün tahtalarda
  tek turda etkili olur. Ajan anahtarı hiç görmezse (eski sunucu) dokunmaz.
- **Teslim kaydı.** Ajan ekrana aldığı yayının kimliğini `durum.acil_id` ile bildirir;
  sunucu ilk görülme anını ve o an ekran yardımcısı bağlı mıydı bilgisini yazar.
  Rapor sayfası tahta tahta görüntülenmeyi, gecikmeyi ve görüntülenmediyse nedenini
  ("Çevrimdışıydı", "Ekran yardımcısı yok", "Görüntülendiği kaydedilmedi") verir;
  yazdırılabilir. Hedef tahtalar ve her birinin o anki durumu yayın başlarken
  dondurulur (`acil_yayin.hedef_durum_json`): sonradan açılan ya da eklenen tahta eski
  raporu değiştirmez. Rapor tahta ekranlarında görüntülenmeyi gösterir, tahliyenin
  kendisini değil.
- **Tahta ekranı yerleşimi.** Acil sayfası üç kattır: bant, kaydırılabilir başlık + metin,
  altta okul · saat ve "yayını kapat" düğmesi. 1000 karakterlik metin ve 120 karakterlik
  başlıkta da düğme ekranda kalır (kural 3); uzun metinde yazı küçülür, başlık en çok iki
  satırdır. Bant sözcüğünü ("ACİL DURUM", "TATBİKAT") tekrarlayan başlık gösterilmez.
- **Yetenekler.** Ajan `durum.yetenekler` (`acil`, `duyuru_id`) bildirir; sunucu sürüm
  karşılaştırmaz. `acil` bildirmeyen eski ajana yedek yol olarak kapatılamaz bir
  `duyuru` komutu ("ACİL DURUM — …" / "TATBİKAT — …") gider; eski ekran yardımcısı
  duyuruyu kilidin üstünde gösterir. Panel o tahtayı "Eski ajan (yedek duyuru)" diye
  işaretler; ajan güncellenince bekleyen yedek komut iptal edilir.
- **Tahta ekranı.** Öncelik: acil > kapatma > duyuru > kilit. Acil kırmızı, tatbikat
  kehribar zeminde, okulun renginden bağımsız sabit renklerle, tam ekran; yanıp sönme ve
  animasyon yoktur (ışığa duyarlılık; yüzlerce kişinin baktığı ekran). Kilitli tahtada
  acil görünür ve klavye kilidi sürer (acil ekranı kilidi atlatma yolu olmasın); bitince
  önceki hâl (kilit ya da kalan süreli duyuru) döner. Acil gelince süren kapatma geri
  sayımı iptal edilir; acil sürerken otomatik kapatma ne sunucuda komut üretir ne
  ajanda uygulanır. Panelden verilen uyarısız "Kapat" idarenin açık kararıdır, uygulanır.
- **Kural 3 uyarlaması.** Sunucu sürdükçe yayın tahtadan kapatılamaz. Sunucuya 90 sn
  ulaşılamazsa ekranda "Sunucuya ulaşılamıyor — yayını kapat" düğmesi çıkar; bu, kilit
  ekranındaki ile aynı tek çevrimdışı iletisidir (`cevrimdisi_ac`) ve kilidi de açar.
  Sunucu dönünce yayın sürüyorsa tahta yeniden alır. Tahta yayını en çok 2 saat tutar;
  servis 10 sn görülmezse ekran yardımcısı kapanır.
- **Panel.** Acil sürerken her sayfada kırmızı (tatbikatta kehribar) bant ve yetkiliye
  "Yayını bitir"; menünün en sağında herkese görünen "Acil durum" bağlantısı. Pano
  kartında "Acil yayın ekranda" rozeti.
- **Bilinen sınırlar.** Sunucu bilgisayarı kapalıyken acil yayın yapılamaz. Yayın yalnız
  ekran yardımcısının çalıştığı (oturumu açık) tahtada görünür; giriş ekranındaki tahtada
  görünmez. Tahta ekranı sessizdir; sesli uyarı binanın alarm sisteminin işidir. Yazılım
  bir "uyarı sistemi" olduğunu iddia etmez; şablon metinler örnektir, mevzuat metni değildir.

## 8. Otomatik kapatma

Enerji tasarrufu için sunucu, ayarlanan saatlerde (hafta içi) o an açık olan
tahtalara kapatma komutu verir; hafta sonunda belirlenen süreden uzun açık kalan
tahtaya da aynı komut gider. Acil yayın sürerken hiç komut verilmez (§7). Kullanılan tahtada 60 saniyelik geri sayım ve
"Vazgeç" düğmesi çıkar; kilitli ya da oturumsuz tahta uyarısız kapanır. Saatinden
sonra açılan tahtaya dokunulmaz. Resmî tatil takvimi yoktur. Uzaktan açma
(Wake-on-LAN) güvenilir olmadığı için akışın parçası değildir; tahta gerektiğinde
cihazdan açılır.

## 9. Güncelleme

0.12.1 geliştirmesinde ajan indirmeleri sınırlıdır: JSON yanıtı 4 MiB,
`.deb` paketi 16 MiB, logo 256 KiB. Başlıkta boyut bulunmasa veya yanıt chunked
olsa da sınır uygulanır. Boyutu aşan ve Content-Length'e göre kesik kalan yanıt
bağlantı hatası sayılır; paket kurulmaz. Sertifika ve özet denetimi değişmez.

Sunucu, ajan `.deb` paketini kendi içindeki ajan kaynağından üretir. Sunucu
güncellenince paket de yenilenir; panelde sürümü eski tahtalar "Güncelleme var"
diye görünür ve "Ajanı güncelle" komutuyla paketi sunucudan indirip kurar
(özet denetimiyle). Kurulum servisten bağımsız bir birimde koşar. Otomatik ve
kademeli yayma ile başarısız güncellemede geri dönüş henüz yoktur.

### 9.1 Yeni sürüm denetimi (sunucu, GitHub)

Sunucu, yeni bir Tahta Kontrol sürümü yayımlanıp yayımlanmadığını öğrenmek için günde en çok bir kez
GitHub'daki deponun "son sürüm" kaydına bakar (`tahta_sunucu/guncelleme.py`). Programın internete çıkan
tek işi budur; ayar (`guncelleme_denetimi`, varsayılan açık) Ayarlar › Güncelleme denetimi'nden kapatılır
ve kapalıyken hiç istek çıkmaz ("Şimdi denetle" de çalışmaz, düğmesi çizilmez).

- **Yalnız sunucu sorar.** Tahtalar internete çıkmaz, ajan değişmedi; tarayıcı da dış kaynağa istek atmaz
  (CSP aynı kalır). İnternet yoksa program hiçbir şekilde etkilenmez.
- **Giden veri yok.** Tek bir GET (`https://api.github.com/repos/aalidemirci/tahta-kontrol/releases/latest`);
  istekte yalnız genel `User-Agent: tahta-kontrol` ve `Accept` başlığı vardır. Okul adı, tahta sayısı,
  kimlik, kurulu sürüm numarası gönderilmez; sorgu parametresi, çerez, telemetri yoktur. Karşılaştırma
  sunucuda yapılır. GitHub, her internet isteğinde olduğu gibi, isteğin geldiği internet adresini görür.
- **Gelen veri güvenilmez girdidir.** TLS doğrulaması açıktır (Windows'ta sistem sertifika deposu), yanıt
  en çok 256 KiB, yönlendirme izlenmez. Bir denetimin TOPLAM süresi 5 sn ile sınırlıdır (ad çözümlemesi,
  bağlantı, başlıklar ve gövde birlikte): soket zaman aşımı her okumada yeniden başladığı için yanıtı bayt
  bayt damlatan bir ağ aygıtı tek başına onunla durdurulamaz; ağ çağrısı kısa ömürlü bir iş parçacığında
  yürür ve süre dolunca bırakılır. Yanıttan yalnız `tag_name`, `draft`, `prerelease`
  okunur; etiket yalnız `^v?\d+(\.\d+){1,3}$` ise kabul edilir, taslak ve ön sürüm yok sayılır. Sürüm
  sayfası bağlantısı yanıttaki `html_url`'den değil, doğrulanmış sürümden sabit kalıpla kurulur; sürüm
  notu metni hiçbir yere basılmaz. Saklanan durum (sürüm ve denetim zamanı) okunurken de yeniden doğrulanır;
  bozuk ya da başka yerden geri yüklenmiş kayıt panoyu ve Ayarlar'ı düşüremez.
- **Yalnız haber verir.** Yeni sürüm varsa (sayısal karşılaştırma: 0.13.10 > 0.13.9) panoda yalnız
  yöneticiye kısa not ve sürüm sayfası bağlantısı çıkar. Kendiliğinden indirme ya da kurma yoktur.
- **Zamanlama.** İş zamanlayıcı listesindedir ama ağ çağrısını kendi (daemon) iş parçacığında yapar: olay
  döngüsünü, 20 sn'lik zamanlayıcıyı ve `vt.KILIT`'i tutmaz; ağ çağrısı sırasında veritabanı bağlantısı
  açık değildir; kapanış onu beklemez (16 sn bütçesi değişmez; süren "Şimdi denetle" de kapanışta hemen
  bırakılır ve kapanıştan sonra ağ çağrısına başlanmaz). "Denetlensin mi" kararı ile işin başlatılması
  tek kilit bloğundadır; istek kilidi alındıktan sonra karar yeniden verilir, bu yüzden süren bir denetim
  varken basılan "Şimdi denetle" ikinci isteği çıkarmaz, onun sonucunu gösterir. Son denemenin zamanı ve sonucu
  `ayar.guncelleme_durumu`'ndadır (şema değişmedi); başarısız deneme de günlük hakkı tüketir, sonraki
  deneme ertesi gündür. Başarısızlık panoda görünmez, yalnız Ayarlar'da "GitHub'a ulaşılamadı" yazar;
  bilinen son sürüm korunur.
- **İşlem kaydı.** Yalnız elle "Şimdi denetle" ve ayar değişikliği yazılır; kendiliğinden denetim yazılmaz.
  "Şimdi denetle" 60 sn içinde yeniden basılırsa yeni istek çıkmaz.
- **Testler ağa çıkmaz.** `tests/conftest.py::ag_kapali` her testte ağ kapısını sahtesiyle değiştirir;
  getirici `uygulama_olustur(..., guncelleme_getirici=...)` ile verilir.

## 10. Platforma taşınabilirlik

- Sunucu saf Python'dır; Windows'a özgü tek parça paketleme ve denetim
  penceresidir. Pardus sürümü için `.deb` + systemd birimi yazmak yeter.
- Ajanın işletim sistemine dokunan bütün işlevleri `tahta_ajan/sistem.py`
  içindedir. Windows'lu tahta desteği bu dosyanın ve bir ekran arka ucunun
  (ör. tkinter) yazılmasıdır.

## 11. Görünüm ve okul kimliği

Panel ve tahta ekranı okulun logosu ve renkleriyle biçimlendirilir (Ayarlar >
Okul kimliği). Amaç kimliktir, süs değil: renk anlam taşımaz, okunurluk her
seçimde korunur.

- **İki renk girdisi:** ana renk ve isteğe bağlı vurgu (ikinci okul rengi). Bütün
  tonlar sunucuda (`tahta_sunucu/tema.py`, yalnız standart kitaplık) OKLCH
  uzayında üretilir ve sRGB'ye sığdırılır; her metin/zemin çifti için kontrast
  eşiği orada tutturulur (metin 4.5:1, tahtada uzaktan okuma 7:1, kenar ve simge
  3:1). Kullanıcının seçimi reddedilmez; gerekirse ton açılır/koyulaştırılır ve
  Ayarlar bunu söyler (kontrast raporu). Türetilmiş tonlar saklanmaz.
- **Durum renkleri sabittir:** açık yeşil, kilitli çivit, duyuru kehribar,
  çevrimdışı gri, sorun kırmızı, güncelleme var camgöbeği. Okulun rengi bunlara karışmaz; her durum
  renk + simge + metinle verilir. Çevrimdışı alarm sayılmaz (akşam olağandır).
- **Panel:** açık/koyu görünüm işletim sisteminin tercihine uyar. Renkler
  `/marka/tema.css` ile gelir; satır içi betik ve stil yoktur (CSP
  `style-src 'self'; script-src 'self'`). Tarayıcının yeni renk özellikleri
  (`light-dark()`, göreli renk, `contrast-color()`) yalnız aşamalı iyileştirme
  ve kayıt öncesi önizlemedir; doğruluk onlara bağlı değildir. Dış font, CDN ve
  derleme adımı yoktur.
- **Logo:** yalnız PNG ya da JPEG (sihirli baytlarla denetlenir; SVG ve WebP
  reddedilir), en çok 256 KB, kenarlar 64–2048 px, en-boy oranı 1:4–4:1. Kullanıcı
  dosya adı hiçbir yerde kullanılmaz. Logo yokken panelde okul adının baş
  harfleri, o da yoksa nötr ürün işareti görünür.
- **Tahta ekranı her zaman koyudur** (projeksiyon parlamasında okunur). Her
  sayfanın (kilit, duyuru, kapatma) üstünde bant durur: logo, okul adı, sağda
  tahta adı · derslik; altında vurgu çizgisi. Duyuru başlığı vurgu renginde,
  "Aç" tuşu ana renktedir; kapatma uyarısı markadan bağımsız sabit renktir.
- **Tahtaya iniş:** onaylı tahtaya her `/ajan/bekle` yanıtında sunucunun
  hesapladığı 11 tonluk tahta paleti, logonun SHA-256 özeti ve tahtanın adı/
  dersliği iner; logo baytları ayrı uçtan (`/ajan/logo`, tahta kimliğiyle)
  yalnız özet değişince indirilir, özeti ve türü denetlenir, servis dizininde
  (root, 0600) saklanır. Ekran yardımcısı root dosyalarını okuyamaz; logo ona
  yerel soketle ("marka" satırı, base64) gider. Tahta ton hesaplamaz; palet
  doğrulanır, geçersiz değer varsayılanla değişir. Logo inmezse ya da bozuksa
  ekran logosuz çalışır; eski sunucuya bağlı tahta varsayılan temayla çizilir.
- **GTK'da iki stil sağlayıcısı:** ölçüler bir kez yüklenir, renkler tema
  değişince aynı sağlayıcıya yeniden yüklenir (pencere yeniden açılmaz).

## 12. Ders programı ve program kilidi

Panelde **Program** sayfası (menüde Duyurular'dan sonra) sekmelidir: Zil saatleri ·
Derslik programları · Kurallar · İstisnalar · Uyarılar. Üstte bugünün şeridi (bugün,
şu anki ders ya da teneffüs, sunucu saati, program kilidinin durumu, boş ders uyarısı
sayısı) durur; aynı şerit pano başında da görünür. Program sunucu saatine
(Europe/Istanbul) göre işler; tahta saatine güvenilmez.

- **Zil saatleri.** 0.10.0'dan beri Tahta Kontrol'ün kendi zil düzenleyicisi vardır (§12.2):
  adlandırılmış çizelgeler, haftalık düzen ve tarihe özel çizelgeler; Okul Zili gerekmez. Okul
  Zili kullanan okul `ayarlar.json` dosyasını ya da `.okulzili` yedeğini yükler (Okul Zili sunucu
  bilgisayarında kuruluysa tek düğmeyle sabit yolundan salt okunur alınır); yalnız ders saatleri ve
  takvim (öğretim dönemi, ara tatiller, resmî tatiller, tarih kuralları) alınır, ses, okul adı,
  cihaz alanları okunmaz; önizlemeden sonra onaylanınca Okul Zili kaynaklı çizelgeler ve haftalık
  düzen kurulur, elle oluşturulan çizelgeler kalır. Okul Zili'ne hiçbir şey yazılmaz.
- **Derslik programı.** Hangi tahtada hangi gün hangi ders saatinde ders **olduğu**;
  öğretmen ve ders adı alınmaz (KVKK: amaçla sınırlı veri — kilit ve uyarı için dersliğin
  dolu olup olmadığı yeter). 0.10.0'dan beri içe aktarma sihirbazıyla (§12.3: aSc XML, şablon
  CSV/XLSX, yapay zekâ çıktısı; önizlemeli, eşlemeli, geri alınabilir) ya da tahta sayfasındaki
  haftalık ızgarayla girilir. Şube isteğe bağlıdır, yalnız panelde görünür. Programı
  girilmemiş tahta yalnız teneffüste kilitlenir ve boş ders uyarısı üretmez.
- **İkili eğitim** (16.11.2026 kararı). Sabahçı ve öğlenci devre ayrı zil çizelgesidir
  (Okul Zili'nin oturumu ya da elle üretimde ayrı devre adı); aynı tahtada sabah bir şube, öğle
  başka şube ders görebilir. Derslik programı ve boş ders uyarısı (gün, devre, ders no) anahtarıyla
  tutulur; program kilidi her tahtanın kendi derslerinden aralık hesaplar (devre geçişindeki boşluk
  20 dakikayı aşıyorsa "Öğle arası", aşmıyorsa "Teneffüs"). "Dersi olmayan saatte de kilitle"
  kapalıyken bütün devrelerin dersleri dolu sayılır (yalnız teneffüs kilitlenir). Bilinen sınır:
  iki devrenin dersleri zamanda çakışırsa çakışan aralıkta teneffüs kilidi verilmez (açık kalmak
  yeğlenir); bir şubenin aynı gün iki devrede dersi varsa yoklamada ders saati serbest seçilir.
- **Program kilidi** (varsayılan kapalı). Teneffüste, öğle arasında ve (istenirse)
  dersliğin boş olduğu ders saatlerinde ders bitiminden `gecikme` dakika sonra tahtaya
  bir kez kilit gider; aralığın bitimine 3 dakikadan az kaldıysa gitmez. Kilit **süreli**
  verilir: süre sunucuda, komut tahtaya inerken hesaplanır; tahta kendi monotonik
  saatiyle sayar ve derse girilecek saatte **sunucu kapalı olsa da** kendiliğinden açılır
  (kural 3; ayrıca 90 sn sonra kodsuz açma düğmesi aynen sürer). Kilit ekranında yalnız
  neden ve açılış saati yazar ("Teneffüs · Tahta 10:40'ta açılır."); şube, ders,
  öğretmen yazılmaz. Öğretmen ortak kodla açarsa o aralıkta yeniden kilitlenmez.
  Yeniden başlatılan tahtada program kilidi geri yüklenmez (süresi bilinmez; açık
  kalmak döngüsel kilit/açmadan iyidir). Komut ömrü 120 sn'dir.
- **Yetenek.** Program kilidi yalnız `durum.yetenekler` içinde `program_kilidi` bildiren
  tahtaya verilir. Eski ajan `kilitle`'nin verisini bilmez, süresiz kilitler ve sonraki
  açma idarenin kilidini de açardı. Panelde böyle tahtalar "Ajan güncellenmeli" diye
  görünür.
- **Askı.** Program kilidi şu durumlarda verilmez ve program kaynaklı kilitli tahtaya hemen
  açma gider: tahta muafsa (kütüphane, öğretmenler odası), istisna aralığındaysa, Okul
  Zili'nde planlanmış sınav penceresindeyse, gün tatilse, acil yayın sürüyorsa, kural
  kapatılınca ya da zil saatleri silinince. İstisna tarih-saat aralıklıdır (bütün ya da
  seçili tahtalar, en çok 400 gün); pano ve Program şeridinde "1 saat / bugün durdur"
  kısayolu vardır. İstisnayı idareci de ekleyip iptal edebilir; kuralları, zil saatlerini
  ve derslik programını yalnız yönetici değiştirir.
- **Açma yedeği.** Asıl açma tahtadaki süredir; sunucu, aralığı bittiği hâlde program
  kaynaklı kilitli görünen tahtaya en çok 5 dakikada bir açma komutu verir (saat kayması
  ve istisna için).
- **Boş ders uyarısı** (0.8.0'dan beri varsayılan açık; yöneticinin önceden kaydettiği ayar göçle
  değişmez). Derslik programında dersi olan tahta, ders
  başladıktan sonra eşik süre (5–30 dk) boyunca kesintisiz kapalı, program kilidinde ya da
  oturumsuz kalırsa panelde uyarı çıkar; idarenin bilerek kilitlediği tahta uyarı vermez.
  Tahta sonra kullanılırsa uyarı silinmez, "10:14'te kullanılmaya başlandı" diye kapanır.
  Uyarı tahtanın kullanılıp kullanılmadığını gösterir, dersin işlenip işlenmediğini değil;
  öğretmen adı tutulmaz, işlem kaydına yazılmaz, dışa aktarılmaz (yazdırılabilir), tahtada
  görünmez ve **geçmişiyle** öğretim yılı bitiş tarihine kadar saklanır (§14 "Saklama ve imha";
  silmede `secure_delete` ve WAL budama). Uyarılar sekmesi rapordur: tarih aralığı (en çok 400
  gün), tahta/derslik ve ders saati süzgeci, tahtaya ve ders saatine göre sayılar; kişi adı yoktur
  ("görüldü" yalnız saattir, işaretleyen yalnız işlem kaydındadır). Birden çok günlük ya da süzgeçli
  görüntüleme işlem kaydına yalnız tarih aralığı ve süzgecin varlığıyla düşer. Öğretmenlerin önceden
  bilgilendirilmesi okul idaresinin sorumluluğundadır. Sunucu yeniden başlarsa o
  dersin uyarısı geç ya da hiç üretilmez (yanlış uyarı yerine eksik uyarı).
- **Sonraya bırakılanlar** (göç gerektirmez): boş ders uyarısında "tahtaya dokunulmamışsa da
  uyar" ölçütü. Ortak hesapta oturum temizliği §12.1'dedir (K7, 0.8.0).

### 12.1 Oturum temizliği (K7, 0.8.0)

Ortak hesapla açılan tahtada bir öğretmenin tarayıcıda açık bıraktığı e-posta ya da okul sistemi
oturumu, sonraki kullanıcıya açık kalmasın diye gün sonunda **hafif** bir temizlik yapılır.
Silme değil, oturum kapatmadır: amaç sonraki kullanıcının önceki oturuma girememesidir.

- **Ayar** (Ayarlar › Oturum temizliği, `ayar.oturum_temizligi`, yalnız yönetici): varsayılan
  **kapalı**. Zaman: otomatik kapatma saatlerinin her birinden 5 dk önce (otomatik kapatma kapalıysa
  temizlik yapılmaz ve Ayarlar uyarır), günün son dersi bittikten 10 dk sonra (ikili eğitimde son
  devrenin sonu; tatil ve dersiz günde yok) ya da belirli bir saat. Yalnız hafta içi.
- **Zamanlayıcı** (`temizlik.zamanlayici`, 20 sn'lik turda `oturum_temizligi`): zamanı gelen an için
  okul genelinde bir kez (`program_isaret`, tahta 0), yalnız o an çevrimiçi ve `temizlik` yeteneği
  bildiren tahtalara `temizlik` komutu verir. Acil yayın sürerken hiçbirine, sınav penceresindeki
  tahtaya verilmez. **Kaçan iş sonradan çalışmaz:** zamanından sonraki 4 dk içinde sunucu
  çalışmıyorsa o günün temizliği yapılmaz; komut ömrü 2 dk'dır (`KOMUT_OMRU["temizlik"]`), sonradan
  açılan tahta eski temizliği almaz. Her tur işlem kaydına tek satır düşer (tahta sayısı, eski ajan
  ve sınavdaki tahta sayısı).
- **Elle:** tahta sayfasındaki "Şimdi temizle…" (onay dialoglu; yönetici ve idareci; ayar kapalı olsa
  da). Panodaki toplu işlem ucu bu komutu kabul etmez (yetenek denetimi yalnız tahta ucunda).
  Tahta sayfası son sonucu (komut geçmişinden) ve süren temizliği gösterir.
- **Ajan:** yalnız **ortak hesap** sınıflarında (`ogretmen`, `ogrenci`; sabit
  `temizlik.TEMIZLENEBILIR_HESAPLAR`; sunucunun listesi bunu daraltır, genişletemez). `etapadmin`,
  kişisel hesap ve root **hiçbir koşulda** temizlenmez. Acil yayın, sınav ekranı ya da açık ders
  yoklaması varsa atlanır. Kullanılan tahtada (ekran var, kilitli değil) önce kapatma uyarısı
  sayfasının diliyle 60 sn geri sayımlı uyarı ve "Vazgeç" çıkar; kilitli ya da ekransız tahtada
  uyarısızdır. Geri sayımda acil yayın gelirse temizlik iptal edilir. Kapatma uyarısı ekrandayken
  (öncelik kapatma > temizlik) temizlik geri sayımı durur ve kapatma kalkınca 60 sn baştan gösterilir;
  kapatma uyarısındaki "Vazgeç" bekleyen temizliği de iptal eder (temizlik görülmeden çalışmaz). Adımlar:
  1. **Pencereler:** oturumdaki ekran yardımcısı ayrı bir süreçte (`python3 -m tahta_ajan.temizlik
     pencereler`) görev çubuğunda görünen NORMAL/DIALOG pencerelere EWMH `_NET_CLOSE_WINDOW` gönderir
     (libX11, ctypes; wmctrl/xdotool varsayılmaz). Kibar kapatmadır: kaydedilmemiş belgesi olan
     uygulama soru sorar ve açık kalır. Masaüstü, panel, ekran klavyesi gibi görev çubuğu dışı
     pencereler, pid'i bilinmeyen pencere ve ekran yardımcısının kendisi atlanır. Wayland'de yapılmaz.
     Ekran yardımcısı her oturumda (etapadmin ve kişisel hesaplar dahil) başladığı için istek yalnız
     **temizlenen oturumun kullanıcı kimliğine** ait yardımcıya gider: servis bağlantının sahibini
     çekirdekten (`/proc/net/tcp`, uid sütunu) okur, yardımcının beyanına güvenmez; yardımcı da
     kimlik kendisininkiyle eşleşmezse hiçbir pencereye dokunmaz. Eşleşen yardımcı yoksa adım atlanır.
  2. **Tarayıcı süreçleri:** yalnız o hesabın ve yalnız tarayıcı adlı süreçler (`TARAYICI_SURECLERI`):
     önce 5 sn kendiliğinden kapanması beklenir, sonra SIGTERM, 10 sn sonra SIGKILL. Kapanmayan
     tarayıcının verisine dokunulmaz. Tarayıcı dışında hiçbir süreç sonlandırılmaz.
  3. **Tarayıcı verisi:** Firefox, Chromium, Chrome, Yandex, Opera, Brave, Vivaldi, Edge profillerinde
     (Flatpak yolları dahil) YALNIZ çerez ve oturum dosyaları: Firefox `cookies.sqlite*`,
     `sessionstore.jsonlz4`, `sessionstore.js`, `sessionstore.bak`, `sessionstore-backups/` içindeki
     dosyalar; Chromium ailesi (`Default`, `Profile N`) `Cookies`, `Cookies-journal`,
     `Network/Cookies*`, `Current Session`, `Current Tabs`, `Last Session`, `Last Tabs`, `Sessions/` ve
     `Session Storage/` içindeki dosyalar.
- **Dokunulmayanlar:** geçmiş ve yer imleri (`places.sqlite`, `History`, `Bookmarks`), kayıtlı
  parolalar (`logins.json`, `key4.db`, `Login Data`), form ve otomatik doldurma (`formhistory.sqlite`,
  `Web Data`), site depolaması (`webappsstore.sqlite`, `storage/`, `Local Storage/`, `IndexedDB/`;
  web tabanlı çizim uygulamaları çalışmayı burada tutabilir), uzantılar, ayarlar ve ev dizinindeki
  bütün dosyalar (İndirilenler, Masaüstü, Belgeler). Bunun bedeli: bilgisini yerel depolamada tutan
  bir site oturumu açık kalabilir (saha belgesinde doğrulanacak).
- **Korumalar:** tarayıcı adımı servisin içinde değil, oturum sahibinin kimliğiyle (root yetkisi
  düşürülerek, `subprocess` `user=`) kök dizinde başlatılan ayrı süreçte çalışır; bu süreç root
  olarak çalıştırılırsa reddeder. Ev dizini mutlak, sembolik bağ içermeyen gerçek dizin olmalıdır;
  her dizin `O_NOFOLLOW | O_DIRECTORY` ile dosya tanıtıcısı olarak açılır ve listeleme, denetim ve
  silme o tanıtıcıya göre (`dir_fd`) yapılır: denetimden sonra bir dizini sembolik bağla değiştirmek
  silmeyi başka yere (ör. Belgeler) yöneltemez; sembolik bağ dizin sayılmaz ve izlenmez; beyaz listedeki ad
  sembolik bağsa silinmez (bağın kendisi de); dizinlerde alt dizine inilmez, dizinin kendisi kalır.
  Her adımın hatası sessizce atlanır ve rapora sayı olarak girer.
- **Rapor** (komutun sonucu, işlem kaydı "Oturum temizliği sonucu"): yalnız sayılar ve adım
  sonuçları, ör. "Tamamlandı · Pencereler: 2 pencereye kapatma istendi · Tarayıcı: 1 tarayıcı süreci
  kapatıldı, Firefox 1 profil, 5 çerez/oturum dosyası silindi". Kullanıcı adı, ev dizini, profil
  adı, dosya adı ve pencere başlığı gönderilmez (kural 6). Sonuç komut "iletildi" durumundayken
  temizlik bitince ertelenmiş olarak gider; tahta temizlik sırasında yeniden başlarsa komut
  "Tahtaya iletildi"de kalır.
- **Benzetim:** `TAHTA_AJAN_BENZETIM=1` iken hiçbir pencereye istek gitmez, süreç sonlandırılmaz,
  dosya silinmez; rapor ne yapılacağını "kapatılacak/silinecek" diye sayar ve "BENZETİM" der.
- **Geriye uyum:** eski ajan `temizlik` yeteneği bildirmediği için komut almaz (panelde "ajan
  güncellenmeli"); eski sunucu yeni ajana bu komutu hiç vermez. Eski ekran yardımcısı uyarıyı
  göstermez ama servis sürüm farkında yardımcıyı yeniden başlatır; pencere yanıtı 15 sn içinde
  gelmezse o adım "atlandı" olur.

### 12.2 Zil düzenleyici (0.10.0)

Okul Zili'nin "gün programı + oturum + tarih kuralı" üçlüsü Tahta Kontrol'de **çizelge + devre +
haftalık düzen + tarihe özel çizelge** olarak tutulur (GOCLER 8. öğe, `user_version` 8: `zil_cizelgesi`, `zil_cizelge_ders`,
`zil_haftalik`, `zil_tarihli`). Zil sesi, öğrenci zili, blok düzeni, tören ve anons alınmaz: Tahta
Kontrol zil çalmaz, yalnız ders aralığını bilmesi gerekir.

- **Çizelge** adlandırılmış bir günün ders akışıdır ("Normal gün", "Cuma", "Kısa gün"); bir ya da iki
  devre (`normal`, ya da `sabah` + `ogle`; taşınan özel kimlikler korunur). Ders numarası elle
  girilmez, devre içinde başlangıç saatine göre kendiliğinden verilir. Teneffüs ve öğle arası satır
  değildir, iki dersin arasındaki boşluktur (≤ 20 dk teneffüs). Gerekçe: "Pzt–Per aynı, Cuma farklı"
  en sık durumdur; tek çizelgeyi düzeltmek atandığı bütün günleri düzeltir.
- **`ders_saati` türetilmiş tablodur:** haftalık düzen ya da bir çizelge her değiştiğinde atanan
  çizelgelerden yeniden yazılır. Böylece derslik programı, tahta ızgarası, kilit, yoklama ve boş ders
  uyarısı değişmeden çalışır. Mevcut zil saatleri yükseltmede bir kez çizelgelere taşınır (aynı
  imzalı günler tek çizelge, "Ders saatleri · Pzt–Per"); taşıma sonrası `ders_saati` birebir aynıdır.
- **Düzenleme:** "Hızlı oluştur" (ilk ders, ders sayısı, süre, teneffüs, uzun ara) satırları üretir
  ama kaydetmez; öğle devresinin ilk dersi boşsa sabahın son dersinden 20 dk sonrası (5'e yuvarlanır)
  önerilir. Tablo satır satır düzeltilir; JS'siz de çalışır (her devre sonunda 3 boş satır, sıralama
  sunucuda), JS varken "Ders ekle"/"Araya ekle" ve canlı numara/ara hesabı vardır. Hata ya da taslak
  yönlendirmeyle kaybolmaz: sayfa girilen değerlerle yeniden çizilir. Devreler arası saat çakışması
  **uyarıdır**, kaydı engellemez (aynı devre içindeki çakışma hatadır).
- **Günün planı (öncelik):** takvim tatili (Okul Zili `tatil` kuralı, dönem dışı, ara/resmî tatil) >
  **tarihe özel çizelge** > Okul Zili'nin diğer tarih kuralları > haftalık düzen. Tatil hiçbir zaman
  yerel kayıtla ezilmez (uzun "şu tarihten itibaren" aralığı resmî tatili derse çevirmesin). Tek giriş
  noktası `program.gun_plani(b, tarih)`. Tarihe özel çizelgeyi yalnız yönetici ekler; aynı günlere
  düşen iki yerel kayıt olmaz. Takvimi olmayan okul tatilleri "Ders yok" tarihe özel çizelge olarak girer.
- **Yürürlük hemen:** kayıt işlemi bitince `ders_saati` yeniden yazılır, zamanlayıcı en geç 20 sn içinde
  yeni planla çalışır. Bugünün planı değiştiyse ve okul saatindeysek program kaynaklı kilitli tahtalar
  hemen açılır, sonraki aralıktan itibaren yeni saatlerle kilitlenir. İleri tarihli değişiklik için
  tarihe özel çizelge vardır (bekleyen sürüm tutulmaz).
- **Numara kayması:** kullanılan bir çizelgede bir devrenin ders sayısı değişiyor ve o devrede derslik
  programı varsa kayıt ayrıca onay ister ("Anladım, kaydet"); artık olmayan ders saatine bağlı derslik
  programı satırları bugünkü yetim mekanizmasıyla görünür. Yoklama kayıtları değiştirilmez.
- **Önizleme:** günün zaman çizgisi sunucuda çizilen satır içi SVG'dir (konumlar öznitelikle, CSP'ye
  uygun); asıl erişilebilir biçim yanındaki metin listesidir. "Günü önizle" herhangi bir tarihin
  planını ve kaynağını gösterir. Çizelgeler CSV olarak dışa/içe aktarılır (içe aktarım taslaktır).
- **Ajan değişmez:** tahta yalnız süreli `kilitle`/`kilit_ac` alır; komut biçimi ve yetenekler aynıdır.
- **Devre uyuşmazlığı (0.10.0 düzeltmesi):** günün çizelgesindeki devreler derslik programındaki devrelerle
  hiç kesişmiyorsa (ör. ikili okulda "Tek devre" ile yapılmış kısa gün) derslik programı o güne uygulanamaz;
  tahta programsız sayılır (yalnız teneffüs kilidi, boş saat kilidi ve boş ders uyarısı yok). Eskiden tahta
  ders sürerken bütün gün "ders yok" diye kilitleniyordu. Tarihe özel çizelge eklenirken uyarı çıkar.
- **Haftalık düzen boşken** tarihe özel çizelge yine o günün planını verir; kilit, açılışta kilit ve
  temizlik de `gun_plani`'yi okur (eskiden `ders_saati` boşsa erken dönülüyordu).
- **Telafi (bilinen sınır):** tarihe özel çizelge derslik programını **kendi hafta gününden** eşler
  (`program_gunu` = takvim günü). Cumartesi'ye "Pazartesi telafisi" girilirse zil saatleri gelir ama
  Pazartesi'nin derslik programı uygulanmaz (tahtalar programsız sayılır, açık kalır). Telafi için Okul
  Zili'nin telafi kuralı ya da program istisnası kullanılır; `zil_tarihli`'ye isteğe bağlı "hangi günün
  derslik programı" sütunu sonraki sürüme bırakıldı.

### 12.3 Ders programını içe aktarma (0.10.0)

Program › Derslik programları › "Ders programını içe aktar" sihirbazı (yalnız yönetici; önce zil
saatleri tanımlı olmalı). Adımlar: kaynak → eşleme → önizleme ve onay. GOCLER 9. öğe (`user_version` 9): `program_eslesme`
(hatırlanan eşlemeler), `program_surum` (geri alma).

- **Kaynaklar:** aSc Timetables XML ("deneme": gerçek bir dosyayla doğrulanmadı; yalnız sınıf, derslik,
  gün, ders saati öznitelikleri okunur, öğretmen ve ders adı bölümleri hiç okunmaz; DTD/varlık reddi,
  boyut/derinlik sınırları, `guvenli_xml.py`), Tahta Kontrol şablonu (CSV/XLSX/XLS, sürüm 2: derslik
  boşsa şubenin tahtası), **yapay zekâ ile dönüştür** (hazır istem + KVKK uyarısı; kullanıcı kendi
  aracında çalıştırır, Tahta Kontrol hiçbir yapay zekâ hizmetine bağlanmaz; çıktı güvenilmeyen girdi sayılır)
  ve elle giriş (tahta sayfası). 0.12.0'dan beri beşinci kaynak **e-Okul "Haftalık Ders Programları"
  raporu** (OOK11002_R01, .XLS; §12.4).
- **Eşleme:** derslik → tahta, sınıf → şube, aSc ders saati → (devre, ders no), şube → tahta; onayda
  hatırlanır. İkili eğitimde dosyanın devresi saatlerden ya da soruyla belirlenir.
- **Kapsam:** onayda yalnız içe aktarımda geçen (tahta, devre) çiftlerinin satırları değişir; sabahçı
  programı yüklemek öğlenci satırlarını silmez. Dosyada geçmeyen tahtalar ancak işaretlenirse temizlenir.
  Hatalı satırlar atlanır; satırların çoğu okunamadıysa ek onay istenir.
- **Geri alma:** her onaydan ve geri yüklemeden önce bütün derslik programı saklanır (en yeni 10 sürüm,
  yalnız tahta·gün·devre·ders·şube); "Önceki programlar"dan geri yüklenir. İşlem kaydına yalnız biçim
  ve sayılar yazılır. Eski `/program/derslik/yukle` ve `/onayla` uçları sihirbaza yönlendirir; bir
  sürüm sonra silinir.

### 12.4 e-Okul "Haftalık Ders Programları" raporu (0.12.0)

Kullanıcının verdiği gerçek bir örnekten (ikili eğitimli bir lise; dosya depoda YOKTUR, testler uydurma
matrisle çalışır) gözlenen yerleşim: tek sayfa; ilk satırda gün başlıkları (Pazartesi–Cuma, "ÇARSAMBA"
gibi Ş'siz yazım olabilir; Türkçe katlamayla eşlenir); sonra şube blokları art arda — blok başlığı yok,
**şube adı raporda hiç yok**. Satır = ders saati: 1. sütun ders no, 2. sütun "13:30-14:05", gün
sütunlarında hücre ("DERS ADI\nÖĞRETMEN", seçmelide "SEÇMELİ DERS\nÖĞRETMEN - DERS"; boş = ders yok).
Ders no 1'e (ya da öncekine eşit/küçüğe) dönünce yeni blok; ders no'suz satırlar (altbilgi) atlanır.
Derslik yoktur. Şube adı ve sırası yalnız raporun PDF'indedir ("9. Sınıf / A Şubesi"; düzey artan, harf
Türk abecesiyle … H, I, İ, J …); bu derslik aktarımında PDF ayrıştırılmaz, kullanıcı gözle doğrular.
(0.13.0'dan beri ayrı öğretmen programı yolunda PDF `pypdf` ile okunur; yalnız şube başlığı ve sıra
doğrulaması için, §12.5. Derslik aktarımı PDF'i yine reddeder.)

- **Okuma** (`eokul_program.py`, saf): ilk baytlardan OLE2 → `eokul.xls_oku` (xlrd; her hata Türkçe
  iletiye döner), ZIP → `xlsx.oku`, PDF ve diğerleri Türkçe ret. 2 MB, 5000 satır, 300 blok sınırı; T.C.
  kimlik numarasına benzeyen hücre varsa dosya reddedilir (işlem kaydına yalnız "reddedildi"). Dosya diske
  yazılmaz (`bellekte_form`), saklanmaz; yalnız SHA-256 özeti.
- **KVKK:** hücreden yalnız "dolu mu" alınır. Öğretmen adı (hücrenin ikinci ve sonraki satırları) hiç
  saklanmaz, gösterilmez. Ders adı programa girmez; tek istisna eşleme ekranında blokları tanımaya yardım
  eden blok başına en çok 3 ipucu ("Pzt 1: MATEMATİK", iki satırlı hücrenin İLK satırı; tek satırlı
  hücreden ipucu alınmaz). İpucu yalnız önizleme kaydında durur ve önizlemeyle (30 dk, onay, vazgeç) silinir.
- **Devre:** bloklar ilk dersin başlangıcına göre (±5 dk) gruplanır; grup, zil çizelgesindeki devreye
  ilk dersin başlangıcı ±5 dk tutan ve en çok dersi tutan devre olarak eşlenir. Zil çizelgesi yoksa ya da
  bir grup hiçbir devreye uymuyorsa (ya da bazı dersleri 5 dk'dan çok farklıysa) eşleme adımında **"Bu
  rapordaki saatlerden zil çizelgesi oluştur"** önerilir: tek grup → Normal, iki grup → Sabah + Öğleden
  sonra (zil çizelgesinde aynı sayıda devre varsa onların kimlik ve adları korunur; yoksa mevcut derslik
  programı yetim kalabilir). Onay kutusunun üstünde kuru çalıştırmayla etkisi gösterilir
  (`eokul_program.zil_etkisi`): o günlerin şu anki çizelgeleri (yeni çizelge yerlerini alır) ve karşılığı
  kalmayacak derslik programı satırı sayısı. Zil uyuyor da yalnız bazı ders saatleri ±5 dk'dan çok farklıysa
  bloklar yine yazılır; farklı dersler uyarıda listelenir, öneri ikincil kalır. İkiden çok başlangıç grubu
  varsa öneri yapılmaz, nedeni yazılır ve zil düzenleyicisine yönlendirilir. Ayrı onay kutusuyla `zil_cizelgesi` (kaynak `eokul`, ad "e-Okul · Pzt–Cum") yazılır ve haftalık
  düzende rapordaki günlere atanır; başka günler ve mevcut çizelgeler değişmez; zil yazımının bütün
  etkileri (`panel_cizelge.Etki`: bugünün planı değiştiyse program kilitleri açılır, yetim uyarısı) geçerlidir.
  Raporda her gün aynı saat yazar; farklı saatli gün (ör. Cuma) sonra zil düzenleyicisinde ayarlanır.
  Hiçbir devreye uymayan grubun blokları yazılmaz (uyarı). Rapor zil çizelgesi yokken de yüklenebilir
  (diğer kaynaklar zil ister).
- **Şube eşlemesi zorunlu adımdır:** bloklar sırayla listelenir (blok no, devre ve saat, dolu ders sayısı,
  ipucu); her blok için şube yazılır/seçilir (boş = atla). Öneri sırası: bu oturumda seçilen > yapıştırılan
  sıralı şube listesi ("9/A, 9/B…", satır satır ya da PDF başlıkları "AL - 9. Sınıf / A Şubesi";
  `metin.sube_duzelt`) > önceki onayda hatırlanan (`program_eslesme` `tur='blok'`, yalnız blok sayısı aynıysa)
  > sistemde kayıtlı şubeler (tahtaların şubeleri + öğrenci listesi) düzey ve **Türk abecesi** sırasıyla
  (`eokul_program.sube_sira_anahtari`, kod noktası sırası değil) > boş. Blok sayısı ile şube sayısı tutmazsa
  belirgin uyarı; aynı şube iki bloğa atanırsa iki blok da yazılmaz ve onay kapalıdır. Hiç dolu hücresi
  olmayan blok (e-Okul'da programı girilmemiş şube) uyarıyla gösterilir, tahtaya bir şey yazılmaz.
- **Tahta:** derslik olmadığından her şubenin dersi `tahta.subeler`'inde o şube geçen tek tahtaya yazılır;
  yoksa ya da birden çoksa "Tahtası belli olmayan şubeler" tablosunda tahta seçilir (hatırlanır, `tur='sube'`)
  ya da atlanır. Öncelik: bu oturumda seçilen > `tahta.subeler`'de tek tahta > hatırlanan seçim; yani
  `tahta.subeler`'den bulunan eşleme hatırlanmaz ve hatırlanan seçim güncel `tahta.subeler`'in önüne geçmez
  (şube başka dersliğe taşınınca eski tahtaya yazılmasın; bu kural tablo kaynağı için de geçerlidir).
  Tahtası bulunan şubeler eşleme ekranında kapalı bir bölümde durur. İkili eğitimde aynı tahtaya sabahçı bir şube ve öğlenci bir şube düşer; kapsam (tahta,
  devre) olduğundan biri ötekini silmez.
- Sonrası ortak yol: önizleme (tahta başına +/−/~, şube başına haftalık ders saati, dolu/boş ders saati
  sayısı), onay, önceki sürümün saklanması, işlem kaydı (yalnız biçim ve sayılar). Yalnız yönetici.
  Tahta Kontrol e-Okul'a bağlanmaz.

### 12.5 Öğretmen programı ve kilit ekranında gün programı (0.13.0, 0.13.1)

Kullanıcının 17.11.2026 talimatıyla, öğretmen programı ayrı bir içe aktarma
yolunda (`ogretmen_program.py`, `/ogretmen-programi`) mevcut öğretmen kimliklerine
bağlanır. PDF şube başlıklarını, XLS gün/saat/ders ve kaynak öğretmen satırlarını
sağlar. Ham dosyalar ve kaynak adlar yalnız süreli önizleme belleğindedir;
kalıcı tabloda öğretmen kimliği vardır. Öğretmen adı otomatik oluşturulmaz.
Eski e-Okul dolu/boş program okuyucusu ve kişi verisi tutmayan derslik programı
aynen korunur. Program eşlemesi **yoklama yetkisini kısıtlamaz**; nöbet veya boş
ders gözetimi için başka sınıfın geçerli dersine yoklama alınabilir.

Yeni `ogretmen_program` tablosu yıl sonu saklama sınırında temizlenir; yalnız
bu tablonun silinmesi de WAL budamasını tetikler. Program sürüm sayacı,
bekleyen önizlemelerin eski veri üzerine sessizce yazmasını önler.

Kilit ekranına yalnız ilgili şubelerin bugünkü şube/ders/saat listesi gönderilir.
Öğretmen ve öğrenci kimliği/ismi gönderilmez. Ajan bellek görünümü sunucunun
gece yarısı süresiyle sona erer, disk/tanılamaya yazılmaz. Bu görünüm eski
program kilidi gerekçesi satırından ayrıdır. Dört satırlık sayfalama tuş
takımının altında kalır; gerçek ETAP ekran ölçümü saha aşamasıdır.

**0.13.1 düzeltmeleri** (0.13.0'ın bağımsız incelemesi; `docs/surum-0.13.1.md`):

- **Hücre çözümü kapalı hata** (`ogretmen_program.hucre_coz`). Seçmeli hücrede birden çok grup tek satırda
  "KİŞİ - DERS" parçaları olarak gelir ve parçalar `,` `;` sekme ya da iki ve daha çok boşlukla ayrılır.
  0.13.0 boşlukları bölmeden önce sadeleştirdiği için ikinci kişinin adı ders başlığına karışıyordu; ders
  başlığı kilit ekranına gittiğinden bu bir ad sızıntısıydı. Artık önce bölünür; bölündükten sonra hâlâ
  birden çok " - " taşıyan parça belirsiz sayılır: ders başlığı hücrenin ilk satırındaki genel başlığa
  iner, kişi eşlemeye alınmaz, önizleme yalnız sayıyla uyarır. İlk satırın kendisi "kişi - ders"
  kalıbındaysa başlık "Ders" olur. PDF'ten ders adı hiç çıkarılmaz.
- **Göç:** `ders_adi` içinde " - " geçen eski satırlar "Seçmeli ders" yapılır (metnin neresinin ad olduğu
  bilinemediği için kırpılmaz), çakışan bozuk satır silinir. 0.13.0'da kaybolan ikinci grubun satırı geri
  gelmez; 0.13.0 ile aktarım yapılmışsa program yeniden aktarılır. Göç öncesi kopya (`goc-oncesi`) eski
  değeri saklama düzeni içinde taşımaya devam eder.
- **Aynı adlı iki kaynak öğretmen:** rapor iki kişiyi ayırt etmez. Aynı ad aynı gün ve saatte farklı
  derslerde görünüyorsa önizleme sayıyla uyarır ve satırı işaretler (şubeleri birleştirilen aynı ders
  sayılmaz). Hiç çakışmayan iki adaş yine tek kişide birleşir; bu bilinen sınırdır.
- **Önizleme belleği:** 15 dk (`yoklama.ONIZLEME_OMRU_SN`); süresi dolan kayıt zamanlayıcıda (20 sn) silinir,
  "Vazgeç" (`POST /ogretmen-programi/vazgec`, JS'siz `formaction`) hemen siler, onay tek kullanımlıktır.
  Dosya ayrıştırma iş parçacığı havuzunda çalışır (olay döngüsü beklemez).
- **Kilit ekranı kutusu:** öğretmen programı hiç aktarılmamışsa ya da tahtanın şubesi yoksa
  `ajan_gorunumu` `None` döner; anahtar yetenekli ajana yine gider (değeri null), ajan elindeki programı
  kaldırır ve kutu çıkmaz. Tahtanın tarihi sunucununkinden farklıysa program gizlenmez; başlık
  "Bugünün ders programı" yerine sunucunun tarihini taşır ve ilk sayfadan açılır (tahtanın saatine
  güvenilmez). Tarih tutuyorsa program şimdiki ya da sıradaki dersin sayfasından açılır; elle seçilen
  sayfa 60 sn kalır. Sunucunun iletisi dersler varken de gösterilir (160 karakter, ekranda en çok iki
  satır). Sayfa değişince tuş takımı ve düğmeler yer değiştirmez (`scripts/ekran_olcum.py` "OYNADI").
- **Yüzer düğme** (§5.1): pencere yapışkandır (`stick`), ipucu UTILITY kalır; grab ve POPUP yoktur.
  Dokunuşun ardından gelen öykünülmüş fare basışı 0,7 sn yok sayılır; dokunmada sürükleme eşiği 28 px.

Yalnız Debian 12 kabında (Xvfb) ölçülen pencere davranışı (18.11.2026); ETAP'ın pencere yöneticisi
bilinmediği için saha denemesinin yerini tutmaz:

| Pencere yöneticisi | Odaklı tam ekranın üstünde tıklanır | 2. çalışma alanında | "Masaüstünü göster" kipinde |
|---|---|---|---|
| xfwm4 | evet | evet | evet |
| Mutter | evet | evet | hayır (gizlenir) |
| Muffin | evet | evet | hayır (gizlenir) |
| Openbox | hayır | evet | hayır (gizlenir) |

Gerçek dokunma olayı kapta üretilemedi; dokunma yolu yalnız taklit testlerle sınandı.

## 13. Sınav kipi ve sınav yoklaması

Kaynak, Kelebek Sınav'ın **Toplu Dağıtım Çizelgesi** (R5, `.xlsx`) dosyasıdır; bir dosya bir
sınav oturumudur. Sunucu dosyayı standart kitaplıkla okur (`xlsx.py`: zip üye sayısı ve açılmış
boyut sınırı, `<!DOCTYPE` reddi; yeni bağımlılık yok), dosyayı diske yazmaz. Başlık satırı (A2)
künyeyi verir; süre çizelgede olmadığı için idareci yazar (varsayılan 40 dk, ders başına
değiştirilebilir). Aynı sınavın (ad + başlangıç) yeni dosyası, giriş penceresinden önce
yüklenirse öğrenci listesini yeniler; süreler, eşleşmeler ve gözetmen kodları korunur.

**Veri en aza:** ad soyad sunucuda **saklanmaz**; içe aktarma anında maske hesaplanır
(`maske.kalabalik`: "Ah*** Yı****") ve ad bellekte atılır. Sunucuda okul no, şube, salon,
koltuk, ders ve maske durur. Tahtaya yalnız maske, okul numarasının son iki hanesi, şube ve
koltuk gider; tam okul no ve ders gitmez. İşlem kaydına ad, maske, okul no yazılmaz (salon adı,
koltuk numaraları ve sayılar yazılır). Kişisel veri **öğretim yılı bitiş tarihi** geçince (o
tarihte ve öncesinde yapılan sınavlarınki; §14 "Saklama ve imha") kendiliğinden silinir
(`secure_delete` + WAL budama); salon başına "mevcut / gelmeyen" sayıları kalır. Tahtadan alınan
sınav yoklaması salon evrakındaki imzalı yoklamanın yanında yardımcı kayıttır. İdare daha önce de silebilir (yalnız sınav bittikten sonra).

**Bildirimsel `ayar.sinav`:** sınav kipi komut olarak bir kez inmez; her `/ajan/bekle`
yanıtında sunucu, tahtanın o an sınav penceresinde olup olmadığını yeniden hesaplar
(`sinav.tahta_sinavi`). Pencere [başlangıç − 10 dk, salon bitişi) aralığıdır; sınav yayında,
salonda kip kaldırılmamış ve kişisel veri silinmemiş olmalıdır. Kalan süreler saniye olarak
gelir ve ajan bunları kendi monotonik saatine çapalar: tahtanın saati yanlış olsa da sayaç
doğrudur; ajan ya da tahta yeniden başlarsa, süre uzatılırsa durum kendiliğinden düzelir.
Pencere dışında değer `null`'dur. Eski ajan anahtarı yok sayar; panel o tahtada "Ajan
güncellenmeli" der (yetenek `sinav`). Eski sunucu anahtarı hiç göndermez; yeni ajan sınav
durumuna dokunmaz.

**Tahta ekranı:** başlangıçtan 10 dk önce **giriş ekranı** (sınav adı, salon, başlangıç saati,
maskeli oturma listesi; ≤ 20 kişi tek, ≤ 40 iki, ≤ 60 üç sütun, fazlası "ve N kişi daha");
başlangıçta **sınav ekranı** (büyük geri sayım, bitiş saati ya da karma salonda ders başına
bitiş, okulun sınav kuralları; son 5 dakikada sayaç kehribar). Liste sınav başlayınca ekrandan
**ve servisin belleğinden** silinir. İki ekranda da klavye ve fare pencereye bağlıdır ve ortak
kilit kodu kabul edilmez (kod sınıfın önünde girildiği için öğrencilerce bilinebilir). Panelden
"Kilidi aç" sınav ekranını kaldırmaz; sınav ekranı süre bitince, "Sınavı bitir" ya da salonda
"Sınav kipini kaldır" ile kalkar ve alttaki kilit durumu görünür. Ekran önceliği:
acil > kapatma uyarısı > gözetmen > (0.6.0: ders yoklaması) > duyuru > sınav > kilit. Liste ve gözetmen belirteci
`durum.json`'a, günlüğe ve tanılama raporuna yazılmaz.

**Kural 3 sınavda da geçerlidir:** sunucuya 90 sn ulaşılamazsa sınav ekranında "Kilidi aç"
düğmesi çıkar; basılınca kilit açılır ve sınav ekranı o çevrimdışılık süresince kapanır. Sunucu
dönünce sınav hâlâ sürüyorsa ekran geri gelir. Sunucuya hiç ulaşılamasa da sınav ekranı
süresinde (en çok 8 saat) kalkar.

**Gözetmen kodu modeli ("salon fişine sahip gözetmen"):** her salona 6 haneli rastgele kod
üretilir ve panelden fiş olarak yazdırılır (sayfaya 6 fiş). Kod yalnız o salonun eşli tahtasında
ve yalnız sınav penceresinde geçerlidir; **sunucuda doğrulanır** (tahtada özet tutulmaz, servis
kodu saklamaz). Tahta başına 10 dakikada 5 hatalı deneme 5 dakika bekletir ve her deneme işlem
kaydına düşer. Doğru kod 15 dakikalık, tahtaya ve salona bağlı bir belirteç verir; belirteç
yalnız tahtadaki yönetici yetkili serviste ve sunucuda (özetiyle, bellekte) durur, ekran
yardımcısına gitmez. Gözetmen menüsünden "Yoklama al" sınav başlayınca açılır; koltuk
düğmelerine dokunup gelmeyenleri işaretler, kaydeder. Kayıt salonun yoklamasını bütünüyle
yazar; işaretler kaydedilince ekrandan ve bellekten silinir. 60'tan kalabalık salonun yoklaması
panelden alınır. Bilinen sınır: kod kişiye değil fişe bağlıdır; kişiye bağlı kimlik Aşama 5'in
öğretmen PIN'idir. Panel yoklaması kullanıcı adıyla kaydedilir ve tahta yoklamasının üzerine
yazabilir (idare son sözü söyler).

**Zamanlayıcıyla ilişki:** sınav penceresindeki eşli tahtaya otomatik kapatma, program kilidi
ve boş ders uyarısı verilmez; pencereden önceki 10 dakikada yeni program kilidi de verilmez
(süreli kilit pencereye taşmasın). Ajan da sınav ekranı açıkken uyarılı kapatmayı
"Sınav sürüyor; otomatik kapatma uygulanmadı." diye atlar. Panoda sınavdaki tahtaya duyuru,
kilit açma, kapatma ya da yeniden başlatma ek onay ister.

**Şube duyurusu:** sınavdan önce şube dersliklerinde (tahta sayfasındaki "Şubeler" alanı; şube
hiçbir tahtanın alanında yoksa derslik programında o şubenin en çok dersinin olduğu tahta)
"kim hangi salonda, hangi koltukta" listesi maskeli olarak, süreli ve öğretmence kapatılabilir
bir duyuru olarak gösterilir. Duyuru kaydına liste değil özet yazılır; liste yalnız komut
verisindedir ve saklama süresi dolunca o da boşaltılır. Duyurunun süresi sınav başlangıcına
kırpılır (liste sınav sürerken görünmez); başlangıca bir dakikadan az kala gönderilemez.
Tahtada 12 satırdan uzun duyuru 1–3 sütuna bölünür, yazı boyu satır sayısına göre küçülür;
Kapat düğmesi her uzunlukta ekranda kalır.

**Sınav kuralları metni** en çok 1500 karakter ve 8 satırdır; tahta da en çok 8 satır
(satır başına en çok 2 sarılmış satır) gösterir. Ekranın alt satırı (saat, "Gözetmen",
çevrimdışıyken "Kilidi aç") her metin uzunluğunda ekranda kalır.

**İcmal:** "Sınav Yoklama İcmali" yazdırılabilir sayfadır (salon özeti, şube ve okul no
sırasıyla gelmeyenler, imza alanları). Liste CSV/Excel olarak dışa verilmez. İcmal ve panel
yoklama sayfası okul no içerir; görüntülenmeleri işlem kaydına düşer. Salon evrakındaki imzalı
yoklama esastır; icmal bunu kolaylaştırır, yerine geçmez.

Sonraya bırakılanlar (göç gerektirmez): şube duyurusunun tahtada tablo olarak gösterimi,
gözetmen menüsünde "Sınav ekranını bu tahtada kapat" (açık soru 20; kip kaldırma panelden
yapılır), 60'tan kalabalık salonda tahtada sayfalı yoklama ızgarası, Aşama 5'ten sonra gözetmen
ekranında öğretmen PIN'i.

## 14. Ders yoklaması

Öğretmen derste tahtadan, ders saati bazında **yalnız gelmeyenleri** işaretler; idare gün sonu
icmalini e-Okul'a **elle** işler (devamsızlık e-Okul'a ders saati bazında işlenir; icmal şube ve
ders saati bazındadır). Tahtadan alınan yoklama sınıftaki **kâğıt yoklamanın yanında yardımcı
kayıttır**, onun yerine geçmez; arayüz ve icmal bunu yazar. İkili eğitimde ders numarası şubenin
kendi devresinindir (sabahçının 3. dersi ile öğlencinin 3. dersi ayrıdır); ızgara ve icmal şubenin
yanında devre adını gösterir. Tahta Kontrol e-Okul'a bağlanmaz, veri göndermez, ondan veri
çekmez; resmî devamsızlık kaydı e-Okul'dadır. Yarım gün/tam gün hesabı yapılmaz. 0.6.0–0.13.1'de özür,
rapor, izin nedeni tutulmuyor, "geç geldi" ayrı işaret sayılmıyordu; kullanıcının 18.11.2026 isteğiyle
0.14.0'da ikisi de sınırlı biçimde eklendi (§14.2): geç yalnız devrenin ilk dersinde; mazeret yalnız
panelde, sabit türle ve serbest metinsiz (sağlık verisi birikmesin). Aşağıdaki tahta akışı ve panel
anlatımının 0.14.0'da değişen yerleri de §14.2'dedir.

**Sınıf listesi:** e-Okul'un "OOG01001R020 — Sınıf/Şube Öğrenci Listesi" Excel çıktısı (`.XLS`,
blok düzenli; şube yalnız blok başlığında) olduğu gibi yüklenir; elle hazırlanmış düz tablo
(`.xlsx`, `.csv`) da kabul edilir (`eokul.py`; `.xls` için `xlrd`, `.xlsx` için A4'ün
`xlsx.py`'si). Yalnız şube, okul no, ad, soyad okunur; T.C. kimlik no, cinsiyet, pansiyon ve
bilinmeyen sütunlar okunmaz (T.C. sütunu görülürse önizlemede "okunmadı" denir). Dosya diske
yazılmaz; önizleme yalnız bellekte 15 dakika ve yalnız yükleyen kullanıcı için durur, "Aktar"
tek kullanımlıktır. Dosyadaki her şube **tam liste** sayılır: o şubede dosyada olmayan öğrenci
listeden çıkar (pasif), dosyada geçmeyen şubelere dokunulmaz.

**Öğretmen kimliği:** öğretmen panel kullanıcısı değildir. Her öğretmene 3 haneli **öğretmen
kodu** (gizli değil) ve 6 haneli **PIN** verilir. PIN sunucuda yalnız scrypt özeti olarak durur;
düz PIN yalnız üretildiği POST yanıtındaki **pusulada** bir kez görünür (`no-store`, yönlendirme
yok). Tahtaya ne PIN ne özeti gider; doğrulama her seferinde sunucudadır. Deneme sınırları üç
katmanlıdır: tahta başına 10 dakikada 10 hata → o tahtada 10 dakika kapalı; öğretmen kodu +
tahta çifti art arda 3 hata → 120 sn bekleme; öğretmen başına 24 saatte 10 hata → PIN
**kilitlenir**, yalnız panelden açılır. Bilinmeyen kod, pasif öğretmen ve yanlış PIN aynı yanıtı
alır ve aynı süreyi harcar. Bir öğrencinin bilerek hatalı girip öğretmeni kilitlemesi mümkündür;
bunun bedeli idarenin tek tıkla kilidi açmasıdır, kaba kuvvet ise imkânsız kalır. Doğru PIN
**kilidi açmaz**; kilitli tahtada yoklama sürerken klavye kilidi sürer, yoklama bitince kilit
ekranı geri gelir.

**Tahtada akış:** "Yoklama Al" kısayolu (`/usr/share/applications/tahta-yoklama.desktop` →
`tahta-ajan yoklama`) ya da kilit ekranındaki **Yoklama al** düğmesi (yoklama etkin, tahta
çevrimiçi ve kayıtlıyken). Kısayol servise yerel soketle "yoklama aç" der ve kapanır; bu kısa
ömürlü istemci kendini `arayuz: komut` diye tanıtır, servis ona hiçbir durum yayını göndermez ve
onu ekran yardımcısı saymaz. Servis sunucudan **öneri** alır (bugünün tarihi, şubenin ders
saatleri ve hangilerinin başladığı, programdaki şu anki ders ya da tahtanın tek şubesi; öğrenci
verisi yok). Şu an ders yoksa tahtada 5 dakika içinde başlayacak, o da yoksa 15 dakika içinde
bitmiş ders önerilir; tahtanın "Şubeler" alanında birden çok şube varsa (ikili eğitim) devresi şu
an süren tek şube önerilir. Öğretmen kodunu ve PIN'ini tuş takımıyla girer (fiziksel klavyeden de olur);
sunucu 3–15 dakikalık (varsayılan 8) bir **belirteç** verir. Belirteç yalnız yönetici yetkili
serviste ve sunucuda (özetiyle) durur, ekran yardımcısına gitmez (kural 5). Şube ve ders saati
biliniyorsa liste hemen gelir; değilse öğretmen şubeyi ve başlamış bir ders saatini seçer (zil
saati yoksa 1–12). Liste düğmeleri maskeli etiket taşır ("Ayşe Y.", çakışmada "Ayşe Y. (47)", yine çakışırsa
yalnız o öğrenciler için "1047 A. Y."; ayarla hep "1047 A. Y."); tahtada ad ve okul numarası
hiçbir zaman ikisi birden açık görünmez. Çakışma eki düğmede ikinci satırdadır: uzun ad üç
noktayla kısalsa da ek kesilmez. **0.14.0:** varsayılan biçim okul no + ad + soyadın baş harfidir
("123 Ayşe Y."; kullanıcı kararı 18.11.2026) ve liste okul no sırasındadır; "ad ve numara birlikte açık
görünmez" hükmü yalnız ders yoklaması listesi için kalktı, sınav ekranlarında sürer; tam soyad ve T.C.
kimlik no tahtaya hiçbir biçimde gitmez (§14.2).
Öğretmen gelmeyenlere dokunur (kırmızı zemin + "YOK" yazısı), **Kaydet** → onay sayfası
("2 öğrenci yok yazılacak: …") → **Onayla**. Kayıt tek seferliktir: belirteç silinir, liste
ve işaretler ekrandan ve servisin belleğinden atılır; "Kaydedildi" iletisi 3 sn görünür. Aynı
öğretmen aynı ders saatine yeniden PIN girerse önceki işaretleri hazır gelir ve kayıt güncellenir.
Dokunulmazsa (varsayılan 3 dk) ya da süre dolunca ekran sessizce kapanır; bitime 1 dk kala
"Süre dolmak üzere; kaydedin." yazar. Ağ kaydet anında koparsa işaretler kalır ve yeniden
denenebilir; ikinci denemede oturum bulunamazsa "Yoklama kaydedilmiş olabilir; panelde kontrol
edilir." denir (kayıt upsert olduğu için çift kayıt oluşmaz).

**Bildirimsel `ayar.yoklama_etkin`:** her `/ajan/bekle` yanıtında yalnız açık/kapalı bayrağı
gider; maske ve süreler sunucuda uygulanır. Ajan `durum.yetenekler`'e `yoklama` ve
`durum.yoklama_acik` (yalnız bayrak) ekler; şube, öğretmen, öğrenci sunucuya giden duruma
girmez. Eski ajan anahtarı yok sayar, panel tahta sayfasında "Yoklama: ajan güncellenmeli"
der. Eski sunucu anahtarı göndermez; yeni ajan kilit ekranında düğmeyi göstermez, kısayolla
açılan yoklama sunucunun 404'ünde "Sunucu ders yoklamasını desteklemiyor" der.

**Ekran önceliği:** acil > kapatma uyarısı > gözetmen > **yoklama** > duyuru > sınav > kilit.
Yoklama öğretmenin başlattığı kısa etkileşimdir; dokunurken ekran değişirse yanlış işaret olur.
Gelen duyuru serviste bekler, yoklama kapanınca kalan süresiyle görünür. Sınav penceresinde
yoklama açılmaz (sunucu da reddeder); acil sürerken açılmaz. Yoklama açıkken tahta kilitli olsa
da "kullanılıyor" sayılır: uyarılı otomatik kapatma önce geri sayım gösterir.

**Kural 3:** sunucuya ulaşılamıyorsa yoklama açılmaz ("Sunucuya ulaşılamıyor. Bu dersin
yoklamasını kâğıda alın."; K5: asıl dayanak kâğıt yoklamadır); PIN tahtada doğrulanamaz, liste tahtaya kalıcı
yazılmaz. Kilit davranışı değişmez.

**Panel:** üst menüde **Yoklama**; sayfa içi sekmeler Günlük görünüm · Panelden gir ·
Öğretmenler ve PIN · Öğrenci listesi. Günlük görünüm şube × ders saati ızgarasıdır: "0"
(alındı, yok yok), "3 yok", "alınmadı" (programda ders var, bitişinden 15 dk geçti; program
yoksa hiç üretilmez), "·". Aynı saatin birden çok kaydı (bölünmüş ders, panel kaydı) 0.13.1'e kadar
**birleşim** olarak gösterilirdi; 0.14.0'dan beri en son kaydedilen geçerlidir (§14.2 birleşim kuralı). Satır sonunda "e-Okul'a işlendi" kutusu (değişince kendiliğinden kaydedilir;
JS'siz "Kaydet" düğmesi). Kayıt ayrıntısında düzeltme ve silme **gerekçe** ister (T.C. kimlik
no reddedilir); gerekçe ve öğrenci kimlikli değişiklik izi yalnız `yoklama_iz`'de durur, işlem
kaydına yalnız sayılar ve öğretmen kodu yazılır. Panelden yoklama bugün ve son 7 gün içindir.
İcmal yazdırılabilir (A4, şube başına sayfa, okul adı yazdırılmaz; "e-Okul girişine yardımcı
çalışma belgesi"), sekmeyle ayrılmış metin olarak kopyalanabilir ve CSV (UTF-8 BOM, `;`)
indirilebilir; görüntüleme ve indirme işlem kaydına düşer. Öğrenci adı içeren her sayfanın
başında "Bu sayfa öğrenci adları içerir" notu vardır. Öğrenci listesi dışa verilmez.

**Yetki:** görme, düzeltme, panelden yoklama, icmal, yeni PIN, PIN kilidini açma iki role açık;
öğretmen ekleme/düzenleme/pasifleştirme, toplu PIN, öğrenci aktarma, yıl sonu silme ve ayarlar
yalnız yöneticinin.

**Saklama ve imha (16.11.2026 kararı):** öğrenci verisi içeren kayıtlar — ders yoklaması (iz ve
e-Okul işaretiyle), sınavın öğrenci listesi ve yoklaması, boş ders uyarısı — **öğretim yılı
sonuna kadar** saklanır. Bitiş tarihini yönetici Ayarlar › Kişisel veri saklama'dan girer
(`ayar.ogretim_yili_bitis`, `saklama.py`; Okul Zili takvimi varsa öğretimin bitişi tek tıkla
önerilir, kendiliğinden yazılmaz). Tarih geçince (ertesi gün) o tarihte ve öncesinde oluşan
kayıtlar kalıcı silinir (yoklama saatte bir, sınav ve uyarı 20 sn'lik turda; `secure_delete` +
WAL budama, işlem kaydına yalnız sayılar); tarihten sonra oluşanlar bir sonraki yılın bitişine
kadar kalır. Tarih boşsa hiçbir şey silinmez ve Ayarlar uyarır; tarih geçtikten sonra da yeni
yılın tarihi girilene kadar uyarır. Geçmiş bir tarih girmek onay kutusu ister ve silinecek kayıt
sayılarını gösterir. Gün sayılı saklama ayarı (0.6–0.7: 30 gün, 7–365) göçle kalktı. Hiçbir
kaydın göstermediği pasif öğrenciler saatlik imhada silinir; sınıf listesinin kendisi yıl sonu
silmesine girmez: "Tüm öğrenci ve yoklama verisini sil" (`SİL` onayı) ya da yeni yılın listesi.
**Şifreli yedekler** bu veriyi silindikten sonra da yedek saklama süresi kadar (günlük yedek sayısı
kadar gün, varsayılan 14) daha taşır; Ayarlar ve Yedekler sayfası bunu yazar.

**Bilinen sınırlar:** sunucu kapalıyken yoklama alınamaz; yerel soket `127.0.0.1` TCP'dir ve o
tahtadaki herhangi bir yerel süreç yoklama açıkken ekrandaki etiketleri alabilir (belirteç ve
PIN yayına girmez; Unix soketine taşıma ayrı iş); PIN sınıf önünde girilir, gözetlenmeye karşı
önlem kısa oturum ve deneme sınırıdır.

Sonraya bırakılanlar (göç gerektirmez): e-Okul personel listesi (OOK01001R1) aktarımı
(öğretmenler elle eklenir); günlük ızgarada "programdaki öğretmenden farklı" işareti (Aşama 3
öğretmen tutmaz).

### 14.1 USB anahtar (0.11.0)

İstek: idareciler her sınıfta USB bellekle yoklama alabilsin; isteyen öğretmenler için de seçenek olsun;
bellek "yalnız anahtar olarak işgal edilmesin". Özellik Ayarlar › USB anahtar'da **varsayılan kapalıdır**;
kapalıyken tahtalar takılan belleklere hiç bakmaz.

| Konu | Karar | Gerekçe |
|---|---|---|
| Bellek | Biçimlendirilmez, bölünmez, yazılmaz. Anahtar kök dizindeki tek küçük metin dosyasıdır: `tahta-kontrol.anahtar` (ASCII, ≤ 1 KB) | Bellek ders sunumu için de kullanılır |
| Dosya | Başlık + `surum=1` + `kimlik` (8 karakter, gizli değil) + `sunucu` (sertifika parmak izinin ilk 16 hanesi) + `gizli` (32 rastgele bayt, base32). Ad, kod, kullanıcı adı, okul adı YOK | Bulan kişi kime ait olduğunu öğrenemez |
| Sunucu | Yalnız gizlinin SHA-256 özeti saklanır; gizli yalnız bir kez, tek seferlik indirilen dosyada çıkar (5 dk, yalnız üreten oturum) | Veritabanı ya da yedek sızarsa anahtar üretilemez |
| Okuyan | Yalnız kök yetkili servis (`sistem.anahtar_oku`): kök dizinde `O_NOFOLLOW`/`dir_fd`, düz dosya, aynı aygıt, ≤ 1 KB, ayrı iş parçacığında 3 sn zaman aşımı; dizin listelenmez | Güvenilmeyen bellekte sembolik bağ, FIFO, dev dosya, yarış |
| Bağlama | Servis BAĞLAMAZ; oturumdaki dosya yöneticisi (udisks2) bağlar. `/proc/self/mountinfo` poll ile izlenir (5 sn yedek). Aday: `/media` ya da `/run/media`, kök `/`, vfat/exfat/ntfs/fuseblk/ext4, çıkarılabilir aygıt (`/usb` yolu ya da `removable=1`), etkin oturumun hesabı | Kök yetkiyle bağlama çekirdek sürücüsünü saldırıya açar, kurumun USB politikasını deler |
| Tetikleme | Takılınca tam ekran açılmaz; köşede 10 sn'lik bildirim ("USB anahtar tanındı · A. Yılmaz (kod 112)" [Yoklama al] [Kapat]). Kilitliyse kilit ekranında aynı satır + "USB anahtarla aç" | Yanlışlıkla yoklama/kilit ekranı açılmasın |
| Yoklama | Her "Yoklama al" yolu (yüzer düğme, kilit ekranı, kısayol, bildirim) tanınan anahtarla kod + PIN adımını atlar; PIN gerekiyorsa yalnız 6 haneli PIN sorulur; "Başka öğretmen (kod ve PIN)" anahtarı o yoklamada yok sayar | Tek dokunuş; bellek takılıyken başkası da yoklama alabilsin |
| Kimin adına | Öğretmen anahtarı: kod + PIN ile alınanla aynı satır. İdare anahtarı: öğretmensiz, `kaydeden='kullanici:<ad>'` (panelde "idare (ad)"); her şube seçilebilir | Kullanıcının yanıtlamadığı soruda şartname varsayımı (açık soru 61) |
| Kilit | Ayar açıksa (varsayılan açık) idare ve öğretmen anahtarları kilidi açar; sınav ekranında ve acil yayında hayır. Sunucu onay verir, kilidi servis açar | Ortak kilit kodundan zayıf değil; kişiye bağlı, iptal edilebilir, iz bırakır |
| PIN | İdare anahtarında varsayılan açık (anahtarın kendi PIN'i, üretimde bir kez gösterilir); öğretmen anahtarında varsayılan kapalı (açılırsa öğretmenin yoklama PIN'i, aynı sayaçlar) | Kopyalanan idare dosyası tek başına işe yaramasın |
| Ömür | Tanınan anahtar tahtada 10 dk geçerli; sonra "çıkarıp yeniden takın". Bellek çıkarılınca gizli silinir, açık yoklama listesi KALIR, PIN bekleyen ekran kapanır | Unutulan bellek kalıcı yetki bırakmasın; öğretmen listeyi bitirebilsin |
| Çevrimdışı | Çalışmaz ("sunucuya ulaşılamıyor"); bağlantı gelince bir kez yeniden dener. Kural 3 (90 sn sonra kodsuz açma) değişmez | İptal edilen anahtar tahtada geçerli kalmasın |
| Kapsam | Yalnız ders yoklaması ve kilit açma; panel oturumu, ayar, komut, duyuru, sınav/gözetmen yok | Dar yetki = küçük zarar |
| Kişi başına | En çok 2 iptal edilmemiş anahtar; yenileme yok (iptal + yeni üretim) | Tek yol, tek kural |

**Dürüst sınır.** Anahtar bir dosyadır ve kopyalanabilir: bellek tahtaya takılınca udisks onu oturumdaki
kullanıcının izinleriyle bağlar; tahtayı kullanan herkes (öğrenci dahil) dosya yöneticisinden dosyayı
birkaç saniyede kopyalayabilir. Bunu belleği "işgal etmeden" engellemenin yolu yoktur (dosyayı gizlemek
koruma değildir). Karşı önlemler katmanlıdır: PIN, dar yetki, anlık iptal (o anahtarla açılmış yoklama
oturumları da düşer), her işlemin (yoklama, kilit açma, reddedilen deneme) anahtar kimliği + sahip
koduyla işlem kaydına düşmesi, 60 sn içinde iki
farklı tahtada kullanılan anahtar için "kopyalanmış olabilir" uyarısı (engellemez), 10 dk tanıma ömrü,
geçersiz anahtar ve PIN için hız sınırları, dosyadaki sunucu parmak izi (başka sunucuya gizli gitmez).
**Bellek takılınca dosya yöneticisi penceresi kendiliğinden açılıyorsa anahtar dosyası sınıfın önünde
listelenir — okulda denetlenecek** (`docs/saha-denemesi.md` §3.10).

**Tahtada iz yok.** Gizli değer yalnız servis belleğinde durur (Python belleği sıfırlamayı garanti etmez;
referans bırakılır — bilinen sınır). Gizli, anahtar kimliği, bağlama yolu (`/media/<hesap>/…`) ve bellek
etiketi `durum.json`'a, günlüğe, tanılamaya, ekran yardımcısına, sunucuya giden duruma yazılmaz; sunucuya
yalnız `usb_izleme` (`kapali` | `izleniyor` | `desteklenmiyor`) gider. Tanılama yalnız sayı ve evet/hayır verir.

**Sunucuda saklama.** `usb_anahtar` satırı yalnız SON kullanım zamanını ve tahtasını tutar (geçmiş tablo
yok; panelde yalnız yöneticiye ve sahibine görünür). Belleğin kendiliğinden tanınması işlem kaydına
yazılmaz (açık soru 64); kayda yalnız yoklama, kilit açma ve reddedilen denemeler düşer. Öğretim yılı bitişinde (kural 24) iptal edilmiş
anahtarlar silinir, etkinlerin son kullanım bilgisi boşaltılır; etkin anahtar yeni yıla geçer.

**Kaybolan bellek.** Sahibi idareye bildirir → anahtar Yoklama › USB anahtarlar'dan iptal edilir (idareci
kendi anahtarını, yönetici herhangi birini) → yeni anahtar üretilir. Dosyada kişi verisi olmadığından kayıp
yalnız yetki kaybıdır; iptal onu kapatır. PIN'i kilitlenen idare anahtarının kilidi açılmaz: iptal + yeni.

**Geriye uyum.** Yeni sunucu + eski ajan: `ayar.usb_anahtar` yok sayılır, anahtar o tahtada çalışmaz; panel
"N tahtada ajan güncellenmeli" der (yetenek `usb_anahtar`). Eski sunucu + yeni ajan: alan gelmez, izleme
kapalı kalır. Yeni servis + eski ekran yardımcısı: "merhaba" sürüm farkıyla yardımcı yeniden başlar.

Yerleşim: sunucu `usb_anahtar.py` (iş mantığı), `panel_usb.py` (panel ve `/ajan/usb/{tani,yoklama,kilit_ac}`
uçları, SÖZLEŞME bloğu); ajan `usb_anahtar.py` (saf: ayrıştırıcı, mountinfo, metinler), `sistem.py`
(izleme, okuma), `servis.py` (durum makinesi), `ekran.py` (usb-pin sayfası, yoklama PIN'inin USB kipi,
kilit ekranı düğmesi, `UsbBildirimi`), `tani.py` (USB satırları).

### 14.2 Yoklama yeniden tasarımı (0.14.0)

Kullanıcının 18.11.2026 isteği: tahtadaki yoklama ekranı kullanışsızdı (şube seçilince ders saati için
kaydırmak gerekiyordu); öğrenciler numara sırasıyla "numara + ad + soyadın baş harfi" görünsün; birinci
derste "geç" işaretlenebilsin; saate göre o anın dersi seçili gelsin; panelde yoklama kolay görülsün,
mazeret/izin girilebilsin, son beş gün görülsün. Bu bölüm §14'ün üç hükmünü değiştirir: "geç ayrı işaret
değildir", "özür/rapor/izin tutulmaz" ve "tahtada ad ile numara birlikte açık görünmez" (yalnız ders
yoklaması listesi için). Değişmeyenler: yoklama kâğıdın yanında yardımcı kayıttır (K5), yarım/tam gün
hesabı yapılmaz (K2), e-Okul'a bağlanılmaz, liste tahtada diske yazılmaz, saklama öğretim yılı sonuna
kadardır (K3), ikili eğitimde ders numarası devre başınadır (K1).

**Kararlar (18.11.2026; varsayım olarak kullanıcıya bildirildi, itiraz gelmedi):** tahtada okul no + ad +
soyadın baş harfi gösterilir, tam soyad ve T.C. kimlik no tahtaya gitmez; mazerette serbest açıklama yoktur,
seçenekler sabittir; defterde mazeretli yokluk tek "Ö" ile görünür; idare düzeltmesi öğretmen kaydını
silmez (ayrı katman); yok → var düzeltmesinde kısa not zorunludur; geç yalnız her devrenin ilk dersindedir;
teneffüste hangi dersin kastedildiği belirsizse "biten / başlayacak" sorulur.

**Tahta — seçim görünümü (kaydırmasız).** `yoklama-liste` sayfasının içindeki görünümdür; kaydırma alanı
yoktur. Üst satırda öneri düğmesi ("10/A · 3. ders 09:50–10:30 → Listeyi aç") ve öne alınan şubeler (★,
en çok 6; açıklama yazısı yok); solda düzey sütunu (yalnız şube sayısı 15'i geçince; düzey, şube adının
"/" öncesidir); ortada 5 sütunlu (bir düzeyde 20'den çok şube varsa 6) homojen şube ızgarası; sağda iki
sütunlu ders saatleri. Şimdiki ders "● 3. ders · şimdi" diye yazıyla da işaretlidir (renk tek başına
anlam taşımaz); biten ders "bitti" yazar; başlamamış ders soluk ve dokunulamazdır. Çok devreli okulda
başlıkta devre adı durur; devre bilinmiyorsa sütun "Önce şubeyi seçin" der; devresi hiç bulunamayan şubede
saatsiz 1–12 düğmesi çıkar. Ölçüler sabit değildir: ızgaralar kalan alanı paylaşır, yalnız sütun × satır
sayısı saf işlevle seçilir. Şubeye dokununca servis sunucudan o şubenin ders saatlerini ve ders önerisini
alır; ders tekse liste hemen açılır (tek dokunuş). 0.13.1'de ajan şube elle seçilince ders önerisini
atıyordu; ikinci dokunuş ve kaydırma bu yüzden gerekiyordu. Öğretmen ders saatine şubeden ÖNCE dokunduysa
seçim "elle" sayılır ve şube değişince yalnız yeni şubede aynı numara VE aynı başlangıç saati varsa
korunur (sabahın 3. dersi öğlenin 3. dersine dönüşmez); saatsiz görünümden hiç korunmaz. Üst satırda uzun
düzey adı yalnız gösterimde kısalır ("Hazırlık/G" → "Hz/G"); ızgara düğmeleri tam adı taşır.

**Ders ön seçimi (sunucu, tek saf kural `yoklama.ders_kurali`).** Şubenin devresinin o günkü ders saatleri
üzerinde, sunucu saatiyle: (1) süren ders; (2) yoksa 5 dakika içinde başlayacak ders; (3) yoksa son 15
dakikada bitmiş ders; (4) yoksa ön seçim yok. Teneffüste hem biten hem başlayacak ders tutuyorsa ve kimlik
(öğretmen programı) hangisinin kastedildiğini göstermiyorsa ders seçilmez: yanıt iki aday taşır
(`ders_adaylari`), liste doğrudan açılmaz, seçim görünümü iki dersi "biten 2. ders" / "başlayacak 3. ders"
diye vurgular ve tek dokunuşla seçilir. Tahtanın derslik programı o şubeye yalnız birinde ders gösteriyorsa
aday teke iner. Kimlik biliniyorsa (PIN ya da öğretmen USB anahtarı sonrası) öğretmenin programında biten
derste satırı olup başlayacakta olmayana biten, tersine başlayacak ders seçilir. Listenin üst satırında
ders numarası ve saat aralığı en büyük yazıyla durur: yanlış ön seçimin savunması budur.

Devre: şube verilmişse önce derslik programından, bulunamazsa öğretmen programındaki o şube-gün
satırlarının saatlerinden bulunur (sorgu yalnız şube, gün, ders no ve saatleri seçer; ders adı ve
öğretmen adı sorguya girmez); yoksa saatsiz 1–12. Şubesiz istekte devre, penceresi (ilk ders − 5 dk … son
ders + 15 dk) şu anı kapsayan TEK devredir; iki devre birden kapsıyorsa (devir saati) ya da hiçbiri
kapsamıyorsa ders saatleri boş döner ve ön seçim yapılmaz.

Şube önerisi: PIN'siz `/ajan/yoklama/oneri` yalnız tahtanın derslik programını ve şubelerini kullanır;
yanıtı hiçbir öğretmene bağlı değildir. PIN/USB doğrulandıktan sonra `/baslat` ve `/ajan/usb/yoklama`
öğretmenin bugünkü programından öneri ve en çok dört şube ekler (idare anahtarında yok). İkisi aynıysa
ya da yalnız biri varsa ve ders tekse liste doğrudan açılır. İkisi farklıysa liste AÇILMAZ: seçim görünümü
tahtanın şubesi seçili, öğretmeninki ★ satırında açılır (vekâlet ve ders değişimi olağandır). Bu karar
serviste liste isteğinden önce verilir (kod + PIN, USB + PIN ve PIN'siz USB aynı yerden geçer). Hiçbir
durumda şube ya da ders düğmesi programa göre kapatılmaz (0.13.0 kararı: program yalnız ön seçimdir).

**Tahta — öğrenci listesi.** Sıra okul numarasıdır (sunucu sıralar, ajan sırayı korur; numarasız öğrenci
sonda). Etiketin yeni varsayılan biçimi `no_ad_soyadbas`: "123 Ayşe Y."; bu biçimde çakışma çözümü
çalışmaz (numara ayırır). Pango kısaltması soyadın baş harfini yuttuğu için ad kısmını sunucu kısaltır:
eşikten uzunsa ikinci ve sonraki adlar baş harfe iner ("Muhammed E. Y."), hâlâ uzunsa ilk ad kesilir;
soyadın baş harfi her zaman kalır. Eşik sütun sayısına bağlıdır (6 sütun: 16, 7 sütun: 13 karakter).
Göç, kayıtlı `ad_soyadbas` ayarını `no_ad_soyadbas` yapar; "Ayşe Y." ve "1047 A. Y." biçimleri Ayarlar'da
seçilebilir kalır. Etiket sunucuda kurulduğu için güncellenmemiş (eski ajanlı) tahtalarda da numara görünür.

Liste kaydırmasızdır: homojen ızgara, mevcut ≤ 42 ise 6×7, 43–48 ise 6×8, 49–56 ise 7×8; 56'dan çok
öğrenci 56'lık sayfalara bölünür. Sayfalı listede ana düğme bütün sayfalar en az bir kez gösterilene kadar
"Sonraki sayfa ›" olarak çalışır, sonra KAYDET olur (görülmeyen sayfadaki öğrenciler sessizce "var"
sayılmasın); işaretler sayfa değişince korunur. Öğrenci düğmesi iki satırdır: üstte okul no ve durum
yazısı (YOK / GEÇ), altta ad. YOK koyu kırmızı, GEÇ koyu kehribar zemin ve kalın kenardır; yanıp sönme
yoktur. Dokunuş ekranda hemen çizilir (servisin yanıtı beklenmez), servis aynı saf işlevle
(`tahta_ajan/yoklama.sonraki_durum`) eşitler. Alt çubuk "Yok: n · Geç: m · Derste: k/toplam" yazar;
"Temizle" KAYDET ve Vazgeç'ten uzakta, en soldadır ve iki dokunuş ister. Sonuç iletisi "Kaydedildi: n yok,
m geç."dir. Listeden seçim görünümüne dönüp aynı şube ve derse gelince işaretler korunur.

**Geç.** Yalnız şubenin devresinin o günkü planındaki en küçük numaralı derste seçilebilir (sabah ve öğle
devresinin ilk dersi ayrı ayrı; devre bulunamazsa 1. ders). O derste dokunuş döngüsü var → yok → geç →
var, diğer derslerde var ↔ yok'tur. Yeniden açılan listede var olan durum görünür: yok kayıtlı öğrenci tek
dokunuşla geç, geç kayıtlı öğrenci tek dokunuşla var olur. Sunucu ilk ders dışındaki geçi ve aynı
öğrencinin hem yok hem geç gönderilmesini 400 ile reddeder. Geç ayrı tablodadır (`yoklama_gec`), "yok"
sayımına girmez, ayrı sayılır; panelde de aynı sınır geçerlidir.

**Sunucu–ajan uyumu.** Ajan `durum.yetenekler`'e `yoklama_gec` ekler. Sözleşmenin örnek istek ve yanıtları
`tests/yoklama_sozlesme.json`'dadır; iki tarafın testleri bu dosyadan beslenir. Karar tahtanın yeteneğine
göredir: yetenekli ajan `/kaydet` gövdesinde `gec`'i her zaman yollar (boş liste dahil; yoksa 400);
yeteneksiz ajanın kaydı var olan geçi silmez, ona geç öğrenci " (geç)" ekli etiketle gider, teneffüste
biten ders ve iki aday önerilmez. Yeni ajan eski sunucuda geç sunmaz ve `gec` göndermez. `/liste`'deki
`yok` ve `gec` o ders saatinin geçerli durumudur (aşağıdaki birleşim kuralı); kimin kaydı olduğu yanıtta
yoktur. `/kaydet` gövdesi öğretmenin gördüğü tam durumdur ve kaydedenin kendi kaydına yazılır; başka
öğretmenin kaydına dokunulmaz. Yeni alanların hiçbiri (`gec`, `subeler_once`, öneri, adaylar) tahtada
`durum.json`'a, günlüğe, tanılamaya yazılmaz; öğretmene bağlı olanlar ekran yardımcısına yalnız belirteç
varken gider; yoklama kapanınca bellekten atılır. Mazeret, geçmiş gün, tam soyad ve ders adı ajan
yanıtlarına girmez; gelecek ya da bugünkü mazeret `/liste`'yi değiştirmez.

**Panel — şube defteri** (`/yoklama/sube`; Yoklama sekmelerinde "Şube defteri", günlük görünümde şube adı
buraya bağlanır). Varsayılan kip **son beş öğretim günüdür**: satırlar öğrenciler (okul no sırası, No + ad
soyad), sütun grupları bitiş tarihinden geriye beş öğretim günü. Öğretim günü, şubenin devresine o gün
ders veren ya da o şubenin yoklama kaydı bulunan gündür; hafta sonu, tatil ve "ders yok" günleri (kayıt
yoksa) atlanır, en çok 30 takvim günü geriye bakılır. Plan dışı bir derse yazılmış kayıt başlığında `*`
ile görünür. Sol yapışkan blok No · Ad · "N gündür" rozeti · beş işaretlik gün şerididir (gün başına tek
işaret: alınan bütün derslerde yok, kısmen yok, tam, alınmadı; mazeretli gün ayrı işaret); sağda yapışkan
yok/geç sayıları. Hücre simgeleri harf + renk + desendir: `·` var, `Y` yok, `G` geç, `Ö` yok ve geçerli
mazeret, `V` idarenin "var" yaptığı hücre, `–` yoklama alınmadı, boş hücre o saatte ders yok (bugünün
başlamamış dersi "henüz başlamadı"). 8 ders × 5 gün 1366 px'te yatay kaydırmasız sığar; sığan tabloda iç
kaydırma yoktur (tek sayfa kaydırması, başlık satırı yapışkan), daha çok sütunda ve dar ekranda tablo kendi
kabında kayar. "Yalnız yokluğu olanlar" süzgeci ve beşer günlük gezgin vardır. Yazdırma A4 yataydır.

"N gündür derste görülmedi" rozeti türetilir, saklanmaz, dışa aktarılmaz, icmale girmez: bitişten geriye,
yoklaması alınmış en az bir dersi olan ve alınan BÜTÜN derslerinde yok olduğu art arda gün sayısıdır.
Yoklama alınmamış gün zinciri ne kırar ne sayılır; sayım beş günle sınırlı değildir (en çok 30 öğretim
günü). Vurgu yalnız zincirde mazeretsiz en az bir gün varsa yapılır (N ≥ 2 düz, N ≥ 3 vurgulu); zincirin
tamamı mazeret kapsamındaysa vurgusuz "N gündür yok (özürlü)" yazar, tür yazılmaz. Sayfa "e-Okul
devamsızlık günü değildir" notunu taşır (K2, K5). Okul geneli kısa liste `/yoklama/son-gunler`'dedir
(N ≥ 2; varsayılan olarak yalnız mazeretsiz günü olanlar). `/yoklama/ogrenci/{id}` bir öğrencinin son 20
öğretim gününü ve mazeret kayıtlarını gösterir; salt okunurdur.

**Gün kipi ve düzeltme katmanı.** Gün başlığından ya da hücreden o günün gün kipine geçilir. Düzenleme tek
"fırça" modelidir ve JS'li ile JS'siz aynı çalışır: üstte yapışkan şeritte Yok / Geç / Var seçilir, hücreye
tıklanınca o durum uygulanır, aynı durumdaki hücreye yeniden tıklamak düzeltmeyi kaldırır (alttaki kayıt
geri görünür). JS yalnız yerinde güncelleme, ok tuşlarıyla gezinme ve `aria-live` iletisi ekler. Düzeltme
öğretmenin/tahtanın kaydına DOKUNMAZ; `yoklama_duzeltme` tablosuna satır ekler (tablo kendi izidir: kim,
ne zaman, hangi durum, not). Aynı kullanıcı aynı hücreyi 60 sn içinde yeniden değiştirirse yeni satır
açılmaz. Yok/geç'i "var"a çeviren düzeltmede not zorunludur (en az 5 karakter, T.C. kimlik no reddedilir,
"ad yazmayın" uyarısı); yok/geç eklemede isteğe bağlıdır. Not JS'siz gönderimler arasında adrese yazılmaz,
sunucu belleğinde 30 dk tutulur. Geç yalnız devrenin ilk dersinde; gelecek ders reddedilir; bugün ve son 7
gün düzenlenir, eskisi salt okunurdur.

Yoklaması alınmamış (`–`) hücre tıklanamaz (409, satır oluşmaz): yalnız yok/geç satırı tutulduğu için kayıt
açmak sınıfın geri kalanını "var" saymak olur. Kayıt panelden yalnız sütun başlığındaki "Alındı" düğmesiyle
ve iki adımda açılır: düğme onay sorusunu tablonun üstünde açar ("işaretlenmeyen herkes derste sayılacak");
o gün alınan bütün derslerde yok olan öğrenciler varsa, varsayılan işaretli seçenekle bu derste de yok
yazılır. Satır işlemleri: "Bütün gün yok" (yalnız kaydı bulunan ders saatlerine; kaç dersin atlandığı
iletide yazar), "Temizle" (satırın düzeltmelerini kaldırır), "Mazeret gir".

**Birleşim kuralı (tek kod: `yoklama_defter.Veri.gecerli_duzeltmeler`/`kumeler`, `hucre_durumu`).** Bir
ders saatinin geçerli durumu: o saatin EN SON KAYDEDİLEN yoklama kaydı; üstüne, o kayıttan eski olmayan en
yeni panel düzeltmesi. Aynı ders saatinin iki kaydı artık birleştirilmez (0.6.0–0.13.1'de birleşimdi):
tahta listeyi geçerli durumla açtığı ve kaydet tam durumu yazdığı için en son kayıt eksiksizdir. Örnek: A
öğrenciyi yok kaydetti, sonra B geç kaydetti → hücre G; A'nın kaydı olduğu gibi durur. Günlük görünüm,
icmal, metin, CSV, panelden giriş formu ve tahtanın `/liste` yanıtı aynı koddan geçer.

Şartname panel düzeltmesinin her kaydı ezmesini öngörüyordu; uygulamada **"en son işlem geçerlidir"**
seçildi: düzeltmeden SONRA tahtadan yeniden kaydedilen yoklama düzeltmenin üstüne geçer. Gerekçe: aksi
halde öğretmene "Kaydedildi" denip kaydı gösterilmiyor, silinen bir kaydın düzeltmesi de sonradan alınan
yeni yoklamayı eziyordu. Düzeltme ve iz satırları silinmez (kayıt silinip o ders saatinin başka kaydı
kalmadıysa düzeltmeleri de silinir). Yan etkiler: kayıt ayrıntısındaki "Düzelt" eski bir kaydı düzeltince o
kayıt en yeni olur ve öbür kaydı da panel düzeltmelerini de örter; aynı saniyedeki düzeltme ve kayıtta
düzeltme kazanır; üstüne kayıt gelen (bayat) düzeltme hücrede görünmez, izi yalnız tablodadır. Bu seçimi
kullanıcı 18.11.2026'da onayladı (§17 soru 65, kapandı).

**Mazeret/izin** (`/yoklama/mazeret`). Form: okul no(ları) (en çok 50), tarih aralığı, tam gün ya da ders
aralığı, tür, isteğe bağlı dayanak. Türler: izinli, raporlu, mazeretli, görevli (nöbet, yarışma, gezi, okul
görevi). **Serbest açıklama alanı yoktur** (sağlık verisi ve gerekçe metni birikmesin; belge e-Okul'da ve
dosyasında durur); yerine sabit dayanak seçimi vardır: veli dilekçesi, kurum yazısı, belge sunuldu, idare
izni. Tür saklanır ama mazeret sayfası ve öğrenci görünümünün mazeret bölümü dışında tek "özürlü" (`Ö`)
olarak görünür: hücrede, icmalde, metinde, CSV'de, yazdırmada, erişilebilirlik metninde ve işlem kaydında
tür yoktur. Tarih: bitiş başlangıçtan önce olamaz, en çok 31 gün; bitiş öğretim yılı bitişini (boşsa bugün +
31 günü) geçemez; başlangıç en çok 7 gün geriye gider. Ders aralıklı mazerette bütün öğrenciler aynı
devreden olmalıdır; kayıt giriş anındaki devreyi yazar. İki adımdır: önizleme (bulunan ve bulunamayan
numaralar, kapsanan gün ve ders saati, kaçının yok kayıtlı olduğu) yalnız bellekte 10 dk durur, onay atomik
yazar. Kaldırınca tür `iptal` yapılır, dayanak boşaltılır; kayıt listede tür göstermeden "kaldırıldı" diye
30 gün görünür. Mazeret AYRI KATMANDIR: öğretmenin kaydını ve panel düzeltmesini değiştirmez; gösterimde
yok + geçerli mazeret `Ö` olur, kaldırılınca asıl durum geri görünür. Tahtada mazeret hiç görünmez.

**İcmal, e-Okul işareti, işlem kaydı, saklama.** İcmal hücrelerine `G` ve `Ö` eklendi; CSV'nin SONUNA
"Geç Sayısı" ve "Özürlü Yok Sayısı" sütunları geldi (var olan sütunların sırası değişmedi; yok toplamı
özürlü yokları içerir). "e-Okul'a işlendi" işareti, işaretten sonra o gün-şubede kayıt, düzeltme ya da
mazeret değişirse "İşlendikten sonra değişti" olur. İşlem kaydına ad, numara, maske, mazeret türü ve tarih
aralığı yazılmaz ("Şube defteri düzeltmesi: 16.11.2026 10/A, 3 hücre"; "Mazeret girildi: 2 öğrenci, 3
gün"); öğrenci kimlikli iz yalnız `yoklama_iz`, `yoklama_duzeltme` ve `yoklama_mazeret`'tedir. Üçü de,
`yoklama_gec` ile birlikte, öğretim yılı sonu imhasına ve "tümünü sil"e girer (aralığı sınırı aşan mazeret
bütünüyle silinir); yalnız geç, düzeltme ya da mazeret kaydı olan pasif öğrenci imhaya kadar silinmez;
şifreli yedek yeni tabloları taşır. Yeni sayfalar ve hücre yanıtı `no-store` döner, yönetici ve idareciye
açıktır; beş günlük görünüm, son günler listesi, öğrenci görünümü ve mazeret listesi dışa aktarılmaz
(yalnız yazdırılır). Şube defteri ve son günler aralığı toplu yükler: sorgu sayısı öğrenci ve şube
sayısından bağımsızdır (uydurma 1200 öğrencide son günler listesi yaklaşık 65 ms).

**Veri modeli (tek göç).** `yoklama.devre` (kayıt anındaki devre; eski satırda boş = türetilir),
`yoklama_gec` (yoklama, öğrenci), `yoklama_iz`'e geç eklenen/çıkarılan sütunları, `yoklama_duzeltme` (tarih,
şube, ders, öğrenci, durum var/yok/geç/kaldır, not, giren, zaman), `yoklama_mazeret` (öğrenci, tarih
aralığı, ders aralığı ya da tam gün, devre, tür, dayanak, giren, oluşturma, iptal zamanı ve eden) ve maske
ayarının çevrilmesi.

**Dosyalar:** sunucu `yoklama.py`, `yoklama_defter.py` (yeni; defter, son günler, mazeret, birleşim),
`panel_yoklama.py`, `panel_defter.py` (yeni uçlar), `maske.py`, `program.py` (`gun_planlari`), `vt.py`;
ajan `servis.py`, `ekran.py`, `yoklama.py` (yeni; ortak saf kurallar); `scripts/ekran_olcum.py`.

**Bilinen sınırlar ve denenmeyenler:** gerçek ETAP'ta dokunma ve gerçek sınıf listesiyle denenmedi; portre
ekran yerleşimi yalnız ölçümle görüldü. Beş gün kipinde ad sütunu dardır (uzun soyad üç noktayla kesilir, tam
ad ipucundadır); plan dışı dersle 40 sütunu aşan şubede tablo kendi kabında kayar. Hücre gezinmesi ok
tuşlarıyladır; sekme sırası kısaltılmadı. Taslaktaki rehberlik/idari görüşme, nöbetçi ve faaliyet
kategorileri, hücre aralığı seçimi ve ders arası yokluk uyarısı uygulanmadı
(`docs/yoklama-yonetimi-tasarimi.md`). Saha adımları: `docs/saha-denemesi.md` §3.14.

## 15. Altyapı: şifreli yedek, sunucu adresleri, envanter, arıza (0.7.0)

Aşama 6'nın çekirdeği (6A). Windows hizmeti 0.8.0'da geldi (K8, §15.6); ajan paketi imzası
(sürüm anahtarını kim tutacak kararı gerekir) hâlâ sonraya bırakılmıştır. Göç: `tahta`'ya
`envanter_json, envanter_ozet, envanter_zamani, donanim_kimligi, demirbas_no, envanter_notu`;
yeni `ariza`, `ariza_hareket` tabloları (`user_version` 6).

### 15.1 Şifreli yedek

- **Biçim:** tek dosya `.tkyedek` = başlık (JSON: KDF değiştirgeleri, alıcı açık anahtarı, geçici
  açık anahtar, nonce) + AES-256-GCM ile şifreli ZIP (`tahta-kontrol.db` SQLite yedek API'siyle
  tutarlı görüntü, sunucu sertifikası ve anahtarı, `bilgi.json`). Başlık şifrelemenin ek verisidir;
  değiştirilirse çözme düşer. Okul adı yalnız şifreli içerikte durur.
- **Anahtar:** yedek parolası (en az 12 karakter) scrypt (n=2^17, r=8, p=1) ile X25519 özel anahtara
  çevrilir; sunucuda **yalnız açık anahtar** saklanır. Bu yüzden sunucu parolayı bilmeden her gün
  yedek alabilir ama yedeği açamaz; sunucu diski çalınsa da eski yedekler açılmaz. Parola
  belirlenirken hesap parolası yeniden istenir. Parola unutulursa yedekler açılamaz.
- **Zamanlama:** 0.12.1 geliştirmesinde otomatik yedek ve geri yükleme kalıntılarının temizliği
  tek bir arka plan işinde yürür; yavaş ikinci disk diğer zamanlayıcı işlerini bekletmez.
  Önceki iş bitmediyse yeni tur yedek başlatmaz. İş hataları günlüğe yazılır; sonraki tur
  yeniden denenebilir. Parola varsa, program en az 5 dk açıksa ve bugünün
  (Europe/Istanbul) günlük yedeği yoksa alınır; başarısızsa 30 dk sonra yeniden denenir. Aynı gün
  ikinci günlük yedek üretilmez. Saklama: günlük yedeklerden en yeni N (3–90, varsayılan 14), elle
  alınanlardan en yeni 10; elle alınanlar ayrıca N günden eskiyince silinir (KVKK: seyrek alınan elle
  yedek süreli silinen veriyi süresiz taşımasın). Aynı kurallar ikinci kopya klasörüne de uygulanır.
  İsteğe bağlı ikinci kopya klasörü (başka disk/sürücü); klasöre yazılamazsa ayar kaydedilmez. İzin
  komutu (`yedek.izin_komutu`) 6A'da programı çalıştıran Windows hesabına, hizmet kipinde (6B)
  LocalService'e (`*S-1-5-19`) yazma izni verir. Yedek, göç ve geri yükleme aynı kilitte (`vt.KILIT`) çalışır.
  Kapanış önce yeni yedek kabulünü kapatır ve zamanlayıcıyı uyandırır; HTTP, zamanlayıcı ve
  süren yedek toplam en çok 16 saniye beklenir (Windows hizmeti ipucu 20 saniye).
  İşletim sisteminde takılmış disk I/O'su Python iş parçacığından zorla iptal edilemez;
  süre dolarsa uyarı yazılır ve daemon işi süreç kapanırken sonlanır. Dosyanın atomik
  değiştirilmesi mevcut tamamlanmış yedeği korur; yarıda kalan `.yeni` dosyası yedek sayılmaz.
- **Parolasız yedek yoktur:** parola belirlenene kadar panoda kırmızı şerit durur.
- **Geri yükleme** yalnız sunucu bilgisayarından (127.0.0.1) ve yöneticiyle; ilk kurulumda
  (kullanıcı yokken) oturumsuz ama yine yalnız yerelden ("Yedekten geri yükle" bağlantısı). Akış:
  dosya + parola → denetim (sihirli bayt, başlık, KDF sınırları, parola, GCM, ZIP içinde tam dört
  dosya ve boyut sınırı, `integrity_check`, şema sürümü, sertifika/anahtar eşleşmesi) → önizleme
  (yedek tarihi, okul adı, tahta ve kullanıcı sayısı, parmak izleri; sertifika farklıysa kırmızı
  uyarı) → onay → **program kapatılıp açılınca** uygulanır: bugünkü dosyalar
  `geri-yukleme-oncesi/<zaman>/` klasörüne taşınır, yedektekiler yerleşir, oturumlar silinir. Hata
  olursa taşınanlar geri konur. Onaydan sonra da yeniden açılıştan önce vazgeçilebilir. Başarısız
  denemeye 10 dakikada 5 sınırı vardır.
- **Sapma (şartnameden):** onaylanan yedek açılışta parolasız uygulanabilsin diye denetlenmiş içerik
  çözülmüş olarak `geri-yukleme/bekleyen/` altında (canlı veritabanıyla aynı klasör izinlerinde)
  bekler; vazgeçilince ya da uygulanınca silinir, onaylanmadan 24 saat bekleyen kendiliğinden silinir.
  Parola ya da özel anahtar diske hiç yazılmaz. `geri-yukleme-oncesi/` altında yalnız en yeni klasör
  kalır, o da N günden eskiyince silinir (zamanlayıcının yedek işi budar; işlem kaydına düşer).
- **KVKK:** şifreli yedekler, öğretim yılı sonunda silinen kişisel verinin (sınav, yoklama, boş
  ders uyarısı) kopyasını yedek saklama süresi kadar daha taşır; Yedekler ve Ayarlar sayfası bunu yazar. Arayüzde mevzuat
  atfı yoktur (KVKK md. 12 §18'de doğrulanacak).

### 15.2 Sunucu adres listesi

- Ayarlar › Sunucu adresleri: en çok 5 adres (IP ya da DNS adı, `https://`, yol yok, yerel adres
  değil). İlk satır birincildir (kurulum betiği bunu kullanır; `kur.sh` listeyi de `ajan.json`'a
  `sunucular` olarak yazar). Eski tek adres ayarı (`sunucu_adresi`) okunur ve ilk kayıtta taşınır.
- Liste **durum tabanlıdır**: her `/ajan/bekle` yanıtında `ayar.sunucu_adresleri` (boşsa hiç
  gönderilmez). Ajan listeyi aynı kurallarla süzer, farklıysa `ajan.json`'a yazar; boş ya da hiç
  gelmeyen listede kendi listesine dokunmaz.
- Ajan bir adrese art arda **3 bağlantı hatasında** (parmak izi hatası dahil; HTTP 401/403/5xx
  dahil değil, çünkü sunucuya ulaşılmıştır) sıradaki adrese geçer; birincil olmayan bir adreste ilk
  başarılı yanıtta onu kalıcı birincil yapar ve olay kaydı düşer. Üstel bekleme (2→30 sn) ve
  `CEVRIMDISI_SN` (kural 3) değişmez.
- Panel: "n/m tahta güncel adres listesini aldı" (ajanın bildirdiği liste özeti sunucununkiyle
  karşılaştırılır), tahta sayfasında bağlandığı adres ve "listede yok" uyarısı, panoda "bu
  bilgisayarın adresi listede yok" şeridi (listede DNS adı varsa uyarılmaz).
- Adres habersiz değişirse tahtalar listeyi alamaz; çözüm: eski IP'yi geri vermek, listeye
  önceden DNS adı koymak ya da tahtada `sudo tahta-ajan sunucu https://YENİ:8788` (parmak izi
  tutmazsa ya da ulaşılamazsa hiçbir şey yazmaz). Ağ taraması ve yayınla keşif bilerek yoktur
  (kurum ağında saldırı sayılabilir; alt ağlar ayrı olduğundan yayın zaten ulaşmaz).

### 15.3 Envanter

- Ajan donanım okumalarını (`sistem.donanim_bilgisi`: DMI üretici/model/seri, anakart, BIOS,
  işlemci, bellek, diskler — takılı USB bellek hariç, dokunmatik aygıt adları, fiziksel ağ
  arayüzleri ve MAC, işletim sistemi, çekirdek, ETAP paketleri, Python) açılışta ve 6 saatte bir
  yeniler; ekran çözünürlüğü bağlı ekran yardımcısından gelir. Yer tutucu seri numaraları ("To be
  filled by O.E.M." vb.) boş sayılır.
- Envanter yalnız sunucu `envanter_iste` deyince (sunucuda yoksa ya da özet farklıysa) ya da
  "Envanteri yenile" (`envanter` komutu) ile gider; aynı özet ikinci kez gönderilmez.
- **Girmez:** hesap/kullanıcı adları, ev dizinleri, dosya adları, makine adı, açık kalma süresi
  (kural 6). Seri no, MAC, model **cihaz** verisidir.
- Panel: Envanter sayfası (sıralanabilir tablo; CSV: UTF-8 BOM, `;`, formül kaçışı, MAC ve IP
  dahil), tahta sayfasında envanter kartı ve yöneticinin girdiği demirbaş no/not. Seri no iki
  tahtada aynıysa "başka tahtada da var" rozeti (kopyalanmış disk belirtisi). Donanım kimliği
  (ürün seri no, yoksa anakart seri no) dolu→farklı dolu değişirse işlem kaydı ve panoda "Donanım
  değişti" rozeti; yönetici "Gördüm" diyene kadar durur. Bağlantı kesilmez (yanlış alarm dersi
  rehin almasın); karar yöneticinindir.

### 15.4 Arıza bildirimi

- **Tahtadan:** menüde "Arıza bildir" (`tahta-ariza.desktop` → `tahta-ajan ariza`). Kullanıcı
  yetkisiyle açılan ayrı bir GTK3 penceresidir (ekran yardımcısının sayfalarına dokunmaz): sekiz iri
  tür düğmesi ("Açılmıyor" yalnız panelden), isteğe bağlı 300 karakterlik açıklama, sabit "Kişi adı
  yazmayın" notu. Pencere servise yerel soketle `merhaba arayuz=komut` + `ariza` yollar; tahtanın
  adı, eski kayıtlar ve hiçbir arıza metni tahtada gösterilmez. Pencere varsayılan tahta paletiyle
  çizilir (okulun renkleri yalnız servisten ekran yardımcısına gider).
- **Servis:** kategori ve açıklamayı denetler, saatte 3 bildirim ve en çok 10 bekleyen kayıt sınırı
  koyar, kaydı `durum.json`'daki kuyruğa yazar (yalnız hesap SINIFIYLA) ve hemen iletmeyi dener.
  Sunucu 5 sn içinde `ariza_alindi` derse pencere "Arıza kaydı iletildi.", demezse "Kayıt tahtada
  bekletiliyor; sunucuya ulaşınca iletilecek." der. Kuyruk sonraki her bağlantıda gönderilir;
  7 günde iletilemeyen kayıt atılır. Aynı kayıt iki kez gelse de (`yerel_id`) tek kayıt olur.
  Onaylanmamış ya da kayıtsız tahta bildiremez.
- **Panelden:** Arızalar sayfası ve tahta sayfası; iki rol de açar ve izler. Durumlar: Açık →
  İnceleniyor / Çözüldü / İptal; İnceleniyor → Açık / Çözüldü / İptal; Çözüldü → Açık; İptal
  sondur. Her değişiklik hareket geçmişine ve işlem kaydına düşer; kayıt silinmez. Süren arıza
  sayısı menüde ve pano kartında rozetle görünür.
- **KVKK:** açıklama serbest metindir; her giriş yerinde "Kişi adı yazmayın" notu, 300 karakter;
  T.C. kimlik numarasına benzeyen sayı panelde reddedilir, tahtadan gelende metin kaydedilmez
  (kayıt alınır ki kuyruk tıkanmasın).

### 15.5 Geriye uyum

- Eski ajan (0.6 ve öncesi) + yeni sunucu: yeni yanıt alanlarını yok sayar; panel "Envanter ve
  arıza bildirimi için ajanı güncelleyin" der, "Envanteri yenile" o tahtayı atlar.
- Yeni ajan + eski sunucu: liste, `envanter_iste`, `ariza_alindi` gelmez; liste değişmez, envanter
  gönderilmez, arıza kuyrukta 7 gün bekler.
- Windows hizmeti (§15.6) tahta arayüzünü değiştirmez: aynı kapı, aynı sertifika (taşınır), aynı uçlar.
  Ajanın yeniden kurulması gerekmez.

### 15.6 Windows hizmeti (K8, 0.8.0)

Sunucu bilgisayar açılınca, kimse oturum açmadan başlar. 0.8 öncesinde sunucu, oturum açan
kullanıcının denetim penceresiydi ve `{commonstartup}` kısayoluyla **her oturum açan kullanıcıda**
kendi verisiyle açılabiliyordu.

**Seçim: pywin32 ile gerçek Windows hizmeti** (`pywin32>=308`, yalnız Windows; PSF lisansı).
- Derleme anında PyPI'den gelen bir Python kitaplığıdır; kuruluma ayrı ikili araç (NSSM, WinSW)
  girmez, kurulumda internet gerekmez. PyInstaller'la hizmet barındırma (`servicemanager`) olgun,
  yaygın bir yoldur.
- Reddedilen: **Görev Zamanlayıcı "sistem açılışında"** — düzgün durdurma (`net stop`), durum
  sorgusu ve çökmede yeniden başlatma vermez; kurucunun görev kaydı yetki hatalarına açıktır.
  **ctypes ile elle hizmet protokolü** — ek bağımlılık yok ama sahada hiç denenmemiş kendi
  kodumuz olurdu. **NSSM/WinSW** — üçüncü taraf ikili.
- `tahta_sunucu/hizmet.py` içe aktarılırken pywin32 istemez (Linux ve testler); pywin32 yalnız
  `TahtaKontrol.exe hizmet` çalışırken yüklenir. Hizmetin işi saf Python `govde()`'dedir.

**Hesap: Yerel Hizmet (`NT AUTHORITY\LocalService`)**, en az yetki. 8787 ve 8788 ayrıcalıksız
kapılardır; sunucunun sistem ayarı değiştirmesi gerekmez. SYSTEM seçilmedi: panelde ya da bir
kitaplıkta açık bulunursa bütün bilgisayar ele geçmesin. Bedeli: yedeğin ikinci kopyası ağ
paylaşımına yazılamaz (Yerel Hizmet ağda anonim görünür); yerel disk/USB çalışır (açık soru 42).

**Kayıt** (kurucu, `sc.exe`): `TahtaKontrol`, "Tahta Kontrol Sunucusu", `start= auto`,
`binPath= "…\TahtaKontrol.exe" hizmet`; çökmede 5 sn, 5 sn, 30 sn sonra yeniden başlatma
(`sc failure … reset= 86400`, `failureflag 1`). Hizmet zaten varsa `sc config` ile güncellenir.
Hizmet yöneticisi dışından `TahtaKontrol.exe hizmet` çalıştırılırsa (1063) sessizce 2 koduyla çıkar.

**Veri dizini** (`ayar.veri_dizini_sec`):
1. `TAHTA_VERI_DIZINI` her şeyi ezer (deneme, derleme duman testi).
2. Paketli Windows programı → `%PROGRAMDATA%\TahtaKontrol` (hizmet ve kurucu).
3. Windows'ta geliştirme (`uv run`) → `%LOCALAPPDATA%\TahtaKontrol` (eskisi gibi).
4. Diğer → XDG yolu.

Hizmet günlüğü `gunluk\sunucu.log` (5 MB × 3); başlama/durma ve açılmama nedenleri ayrıca Olay
Görüntüleyicisi > Windows Günlükleri > Uygulama'ya yazılır.

**İzinler** (kurucu, SID'lerle; Türkçe Windows'ta grup adları yerelleştiği için ad kullanılmaz):
`icacls "%ProgramData%\TahtaKontrol" /inheritance:r /grant:r *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F *S-1-5-19:(OI)(CI)M`.
Yalnız SYSTEM, Administrators ve Yerel Hizmet erişir; sıradan kullanıcılar veritabanını, sertifika
anahtarını ve yedekleri okuyamaz (ProgramData'nın varsayılanı Users'a okuma verir; devralma bu
yüzden kesilir). Taşınan dosyalar `icacls … /reset /T` ile klasörün izinlerini devralır.

**Eski veriyi taşıma** (`tahta_sunucu/tasima.py`). Kurucu yönetici yetkisiyle
`TahtaKontrol.exe tasi --hedef "%ProgramData%\TahtaKontrol" --tercih "<kurucuyu çalıştıranın %LOCALAPPDATA%>\TahtaKontrol"`
çağırır; hizmet hesabı kullanıcı profillerini okuyamadığı için taşıma hizmette değil kurucudadır.
Sertifika değişirse bütün tahtalar koptuğu (kural 4) için kurallar sıkıdır:
- **Hedefte veri varsa** (veritabanı ya da sertifika) hiçbir şey taşınmaz; hedef kazanır (kod 11).
  0.8.0'dan sonraki her yükseltme bu yoldan geçer.
- **Adaylar:** kurucuyu çalıştıran hesabın klasörü ve bilgisayardaki bütün profillerin
  (`ProfileList` + Users klasörü; yalnız okunur) `AppData\Local\TahtaKontrol` klasörleri; içinde
  veritabanı ya da sertifika olan ve `TASINDI.txt` taşımayanlar. Hiç yoksa ilk kurulum (kod 10).
- **Seçim:** tek aday → o. Birden çoksa (başlangıç kısayolu her oturumda programı açtığı için
  mümkündür) tahtaların **en son bağlandığı** (onaylı tahtaların en yeni `son_gorulme`'si)
  veritabanı; hiçbirinde tahta yoksa kurucuyu çalıştıran hesabınki; o da yoksa **seçim yapılmaz**
  (kod 20). Adayların veritabanı geçici bir kopyada okunur; kaynağa yazılmaz.
- **Kopyalama:** bütün dosyalar (veritabanı ve `-wal` dosyası, sertifika ve anahtar, `yedekler\`,
  `goc-oncesi\`, `marka\`, bekleyen geri yükleme…) kopyalanır; günlükler ve `-shm` kopyalanmaz,
  sembolik bağ izlenmez. Her dosyanın SHA-256'sı karşılaştırılır, veritabanı `integrity_check`'ten
  geçer, sertifikayla anahtar birlikte olmalıdır. Hata → bu taşımanın oluşturduğu dosyalar silinir
  (kod 21). Başarı → kaynağa yalnız `TASINDI.txt` yazılır; **eski klasör silinmez** (geri dönüş:
  eski sürüm yeniden kurulursa eski veri yerindedir; ama o günden sonraki değişiklikleri taşımaz).
- **Belirsizlik ya da hata** → hedefe `TASIMA-BEKLIYOR.txt` (adaylar, tahta sayıları, son temas,
  çözüm adımları) yazılır; hizmet bu dosya durdukça **açılmaz** (yeni sertifika üretmesin), kurucu
  hizmeti başlatmaz ve bitişte kırmızı uyarı gösterir. Çözüm: doğru klasörü
  `TahtaKontrol.exe tasi --hedef … --kaynak …` ile vermek ya da dosyaları elle kopyalayıp işareti
  silmek; eski veri gerçekten istenmiyorsa yalnız işareti silmek. Taşıma programı hiç
  çalışamadıysa kurucu işareti kendisi yazar.
- **Kesinti** (süreç öldürülür, elektrik gider; istisna yolu çalışmaz): kopyalama ve doğrulama
  hedefteki `.tasima-gecici` dizininde yapılır; hedef ancak her şey doğrulanınca dolar. Yerleştirme
  `TASIMA-SURUYOR.txt` işaretiyle yapılır (önce sertifika çifti ve diğer dosyalar, en son
  veritabanı; aynı birimde yeniden adlandırma). Sonraki çalıştırma geçiciyi siler; işaret kalmışsa
  hedefteki yarım dosyaları `yarim-tasima-<zaman>` klasörüne **kaldırır** (silmez) ve baştan taşır.
  İşaret durdukça hizmet açılmaz (yarım kopyayla boş veritabanı açılıp tahtalar reddedilmesin).
- **Geri dönüşten sonra yeniden yükseltme:** hedef dolu olsa da, `TASINDI.txt` taşıyan bir eski
  klasördeki veritabanı (ya da `-wal`) `TASINDI.txt`'den 2 dakikadan fazla sonra değişmişse eski
  sürüm o klasörde kullanılmış demektir: kod 20, `TASIMA-BEKLIYOR.txt` iki kopyayı tahta sayısı ve
  son temasla yazar; hizmet başlatılmaz. Seçenekler: (A) eski klasör doğruysa hedefteki veri
  dosyaları kenara alınır, eski klasördeki `TASINDI.txt` silinir, `tasi --kaynak`; (B) hedef
  doğruysa eski klasörün adı değiştirilir ya da silinir.
- **Kurucu yükseltmede** hizmeti durdurmadan önce `start= demand` ve boş `sc failure` eylemleri
  yazar: çökme döngüsündeki hizmeti hizmet yöneticisi dosya kopyalanırken yeniden açmasın; ikisi
  de kayıt adımında geri yazılır.

**Kurulum ve yükseltme akışı** (`tahta-kontrol.iss`):
1. Hazırlık: hizmet varsa `net stop` (durana kadar bekler); sonra `taskkill /F /T /IM TahtaKontrol.exe`
   — 0.8 öncesi oturum programı (her oturumda) ve durum pencereleri kapanır. SQLite işlenmiş
   kayıtları diske yazmıştır; son yazılar `-wal`'daysa o da taşınır.
2. Dosyalar; eski `{commonstartup}\Tahta Kontrol.lnk` silinir (hizmetle ikinci sunucu açmasın).
3. Veri klasörü, izinler, taşıma, izinlerin devralınması, hizmet kaydı, güvenlik duvarı (8788,
   eskisiyle aynı kural adı), taşıma güvenle bittiyse `net start`.
4. Bitiş sayfası taşımanın sonucunu ve uyku notunu yazar; taşınamadıysa ayrıca kırmızı ileti.

**Kaldırma:** `net stop`, açık pencereler kapatılır, `sc delete`, güvenlik duvarı kuralı silinir.
`%ProgramData%\TahtaKontrol` **silinmez** (veritabanı, sertifika, yedekler); kaldırıcı bunu söyler.

**Durum penceresi** (`pencere.py`; kısayollar açar, kullanıcı oturumunda çalışır, hizmetin
verisine dokunmaz, günlüğü `%LOCALAPPDATA%\TahtaKontrol\pencere.log`). Açılışta
`http://127.0.0.1:8787/yerel/durum` (2 sn) ve `sc query TahtaKontrol` ile kip seçer; hizmet
yeni başlıyorsa 20 sn yanıt bekler:
- **Çalışıyor:** sürüm, yerel ve ağ adresleri, uyarılar (yedek parolası yok, son yedek eski ya da
  başarısız, uyku), "Paneli aç", "Kapat". Pencereyi kapatmak sunucuyu durdurmaz.
- **Hizmet kurulu ama yanıt yok:** "Sunucu hizmeti çalışmıyor; kilitler 90 saniye sonra tahtadan
  açılabilir", günlük yerleri, `TASIMA-BEKLIYOR.txt` olasılığı, "Hizmeti başlat" (UAC sorar),
  "Yeniden dene".
- **Paketli program ama hizmet yok:** "Kurucuyu yeniden çalıştırın". Pencere sunucu **açmaz**
  (hizmetle çift çalışma olmasın).
- **Geliştirme** (`uv run … pencere`, hizmet yok ve yanıt yok): eskisi gibi sunucuyu pencerede
  çalıştırır. Yanıt veren bir sunucu varsa ikincisini açmaz.

**Geri yükleme** (§15.1): hizmet kipinde onaydan 2 sn sonra süreç 75 koduyla çıkar; hizmet
yöneticisi 5 sn sonra yeniden başlatır, yedek açılışta yerleştirilir. `/yerel/durum`'un `hizmet`
alanı hizmet kipinde `true` döner.

**Çift çalışmayı önleme:** başlangıç kısayolu silinir; paketli pencere sunucu açmaz; iki sunucu
aynı kapıyı tutamaz (ikincisi "kullanımda" ile açılmaz).

**Bilinen sınırlar:** bilgisayar uyku/hazırda beklemeye geçerse hizmet durmuş sayılır (pencere ve
kurucu uyarır, güç ayarı değiştirilmez). Gerçek hizmet kurulumu ve PyInstaller paketinde pywin32'nin
hizmet olarak çalışması henüz yönetici yetkili bir denemede doğrulanmadı (saha-denemesi.md §3.7).

### 15.7 Yeni sürüm denetimi (0.13.1)

Sunucu günde en çok bir kez GitHub'daki "son sürüm" kaydına bakar ve yeni sürüm varsa panoda yalnız
yöneticiye haber verir; indirme ve kurma yapmaz. İstekle hiçbir bilgi gitmez, tahtalar internete çıkmaz,
ayar kapatılabilir, internet yoksa program etkilenmez (yalnız Ayarlar'da "GitHub'a ulaşılamadı" yazar).
Şema değişmedi: `ayar.guncelleme_denetimi` ve `ayar.guncelleme_durumu`. Ayrıntı ve gerekçeler §9.1'dedir.

Bilinen sınırlar: hizmet Yerel Hizmet hesabıyla çalıştığı için kullanıcıya özgü vekil (proxy) ayarını
görmez; vekil zorunlu ya da GitHub'ı engelleyen ağda sonuç hep "ulaşılamadı" olur ve yeni sürüm elle
izlenir. Kurulu (PyInstaller) programda sistem sertifika deposunun bulunduğu henüz denenmedi
(saha-denemesi.md §3.13).

## 16. Yol haritası

| Aşama | İçerik | Durum |
|---|---|---|
| 0–1 | Sunucu, ajan, kayıt, pano, kilit, duyuru, kapatma, tanılama, güncelleme, otomatik kapatma | 0.1.2 — ETAP'ta denenecek |
| 1.5 | Görünüm ve okul kimliği: okul logosu ve renkleri, yeni panel ve tahta ekranı tasarımı | 0.2.0 — ETAP'ta denenecek |
| 2 | Duyuru zamanlama ve hedef grupları (bina, kat, düzey, devre, gruplar, CSV), acil durum ve tatbikat yayını | 0.3.0 — Debian 12 kabında denendi; ETAP'ta denenecek |
| 3 | Ders programı ve zil saatleri (Okul Zili'nden ya da elle), derslik programı, programa bağlı otomatik kilit/açma, istisnalar, boş geçen ders uyarısı | 0.4.0 — Debian 12 kabında denendi; ETAP'ta denenecek. Oturum temizliği sonraya (§12) |
| 4 | Kelebek sınav duyurusu ve sınav kipi (Kelebek Sınav verisinden, maskeli liste), sınav yoklaması | 0.5.0 — Debian 12 kabında denendi; ETAP'ta ve gerçek Kelebek çizelgesiyle denenecek. Tablo gösterimi, tahtadan sınav ekranını kapatma ve sayfalı ızgara sonraya (§13) |
| 5 | Ders yoklaması (öğretmen kodu + PIN, e-Okul sınıf listesi, tahtadan ve panelden yoklama, icmal, imha) | 0.6.0 — Debian 12 kabında denendi; ETAP'ta ve gerçek e-Okul dosyasıyla denenecek. e-Okul personel listesi aktarımı sonraya (§14) |
| 6A | Altyapı çekirdeği: şifreli yedek ve geri yükleme, sunucu adres listesi (`tahta-ajan sunucu`), tahta envanteri, arıza bildirimi (panel + tahtadaki "Arıza bildir" penceresi) | 0.7.0 — Debian 12 kabında ve tarayıcıda denendi; ETAP'ta denenecek (§15) |
| 6B | Sunucunun Windows hizmeti olarak çalışması (oturum açılmadan başlar, Yerel Hizmet hesabı, veri ProgramData'ya kurucuda kopyalanır, durum penceresi) | 0.8.0 (K8, §15.6) — birim testleriyle ve hizmet kipi uçbirimde denendi; gerçek hizmet kurulumu yönetici yetkili denemede doğrulanacak. Ajan paketi imzası sonraya |
| K | 16.11.2026 kararları (§17): ikili eğitim denetimi ve düzeltmeleri (yoklama önerisi, devre süzgeci, sınav şube duyurusu, ızgara/icmalde devre adı), öğretim yılı sonuna kadar saklama, acil yayını bütün idarecilere açma, yardımcı kayıt metinleri, boş ders uyarısı varsayılan açık + rapor; gün sonu oturum temizliği (K7, §12.1) | 0.8.0 — testlerle ve tarayıcıda denendi; oturum temizliği Debian 12 kabında (Xvfb + openbox, sahte profil) denendi; ETAP'ta denenecek |
| 5B | USB anahtar: bellekteki anahtar dosyasıyla idare ve isteyen öğretmen için yoklama, ayarla kilit açma; tek seferlik indirme, iptal, kopya uyarısı (§14.1) | 0.11.0 — testlerle, tarayıcıda ve Debian 12 kabında loop bellekle (USB benzetimi) denendi; gerçek USB bellek, udisks ve ETAP'ta denenecek |
| 3B | Zil düzenleyici (çizelgeler, haftalık düzen, tarihe özel çizelge, günü önizle, CSV; Okul Zili'nden alma aynı yapıya yazar) ve ders programını içe aktarma sihirbazı (aSc XML deneme, şablon CSV/XLSX, yapay zekâ istemi, önceki programlar) | 0.10.0 (§12.2–12.3) — testlerle ve tarayıcıda uydurma veriyle denendi; gerçek aSc dosyası ve okulun gerçek zil saatleriyle denenecek |
| 5C | Yoklama yeniden tasarımı: tahtada kaydırmasız şube/ders seçimi, okul no sıralı liste, devrenin ilk dersinde geç, saate göre ders ön seçimi; panelde şube defteri (son beş öğretim günü, düzeltme katmanı), mazeret/izin, son günler listesi (§14.2) | 0.14.0 — testlerle, Debian 12 kabında (Xvfb) ekran ölçümüyle ve tarayıcıda uydurma veriyle denendi; ETAP'ta ve gerçek sınıfta denenecek |
| 3C | Sihirbaza e-Okul "Haftalık Ders Programları" raporu (OOK11002_R01, .XLS): blok ayrıştırma, rapordan zil çizelgesi, zorunlu şube eşlemesi, şubenin tahtasına yazma (§12.4) | 0.12.0 — testlerle (uydurma matris) ve geliştirme bilgisayarında gerçek bir raporla (ayrı veri dizini, uydurma tahtalar) uçtan uca denendi; okulda denenecek |

Aşama 2'den sonraya bırakılanlar (göç gerektirmez): panoda "Hızlı seç" ve "Seçili
tahtalara alan ata", plan formunda "sonraki 3 gösterim" canlı önizlemesi, çakışan
plan uyarısı.

## 17. Kararlar (16.11.2026) ve açık sorular

### Kararlar (16.11.2026)

Okul idaresinin (bir ortaöğretim kurumunun idarecisi) yanıtları; kesindir. Uygulandıkları yer
parantezdedir. Bu kararlarla yanıtlanan açık sorular (1, 4, 12, 16, 22, 23, 27, 32, 41) aşağıdaki
listeden çıkarıldı; kalan soruların numaraları değişmedi.

- **K1. İkili eğitim.** Okulda sabahçı ve öğlenci devre vardır; zil çizelgeleri ayrıdır; aynı
  derslikte/tahtada iki ayrı şube ders görebilir. "Devre" alanı bu anlamdadır (bina ayrı alandır).
  (§6.1 devre süzgecinin programdan türetilmesi, §12 ikili eğitim, §14 öneri; 0.8.0)
- **K2. Devamsızlık e-Okul'a ders saati bazında işlenir;** icmal şube ve ders saati bazında kalır,
  yarım gün/tam gün hesabı yapılmaz. (§14)
- **K3. Öğrenci verisi içeren kayıtlar** (ders yoklaması, sınav yoklaması ve listesi, boş ders
  uyarısı) **öğretim yılı sonuna kadar** saklanır. Bitiş tarihini yönetici Ayarlar'da girer; boşsa
  silme yapılmaz ve Ayarlar uyarır; tarih geçince kayıtlar kalıcı silinir, sonra yönetici yeni
  yılın tarihini girer. Şifreli yedekler bu veriyi yedek saklama süresi kadar daha taşır.
  (§13, §14 "Saklama ve imha", §15.1; 0.8.0 göçü gün sayılı ayarı kaldırır)
- **K4. Acil durum yayınını bütün idareciler ve yöneticiler başlatabilir;** parola ve onay kutusu
  yine istenir; ayrı acil yetkisi yoktur (göçle herkese verildi, sütun okunmaz). (§7)
- **K5. Tahtadan alınan ders ve sınav yoklaması kâğıdın yanında yardımcı kayıttır;** arayüz ve
  belge resmî kayıt iddiasında bulunmaz. (§13, §14)
- **K6. Boş ders uyarısı açık ve geçmişiyle:** varsayılan açıktır; uyarılar K3 süresince saklanır
  ve tarih aralığı, tahta/derslik ve ders saatine göre raporlanır (kişi adı yok; ikili eğitimde ders
  süzgeci devreyle birlikte seçilir, ör. "Sabah · 3. ders"). Uyarı oluştuğu andaki şubeyi saklar
  (sonradan değişen program eski uyarıyı başka şubeye yazmasın); 0.8.0 öncesi uyarıda şube güncel
  programdan bulunur ve "(güncel programa göre)" diye işaretlenir. Öğretmenlerin
  önceden bilgilendirilmesi okul idaresinin sorumluluğundadır. (§12)
- **K7. Oturum temizliği: gün sonu, hafif.** Gün sonunda (otomatik kapatmadan önce ya da ayarlanan
  saatte) ortak hesap oturumunda açık pencereler kapanır, tarayıcı oturumları ve çerezleri silinir;
  dosyalara (İndirilenler, Masaüstü, belgeler), tarayıcı geçmişine ve kayıtlı parolalara
  dokunulmaz. (§12.1; 0.8.0. Varsayılan kapalı.)
- **K8. Sunucu Windows hizmeti olarak çalışır** (bilgisayar açılınca, oturum açılmadan başlar).
  Ajan paketi imzası bu sürümde yoktur. (§15.6; 0.8.0. Yerel Hizmet hesabı, veri
  `%ProgramData%\TahtaKontrol`, eski veri kurucuda kopyalanır.)

### Açık sorular

Yanıt gelene kadar bu belgedeki karar geçerlidir.

2. **Acil yayın onayı yeterli mi?** Karar: tek kişi + parola + açık onay kutusu. İki
   kişinin onayı gerçek acil durumda gecikme yaratır; istenirse eklenir.
3. **Acil yayın yalnız bütün okula mı?** Karar: evet. Yalnız bir binaya yayın
   gerekiyorsa bina seçimi eklenebilir.
5. **Acil şablon metinleri** okulun acil durum planındaki ifadelerle değiştirilmeli mi?
   Örnek metinler mevzuattan alınmadı; iş güvenliği/sivil savunma sorumlusunun
   görüşü önerilir.
6. **Tatbikat raporu:** rapordaki alanlar okulun tatbikat formu ve MEBBİS'e girilen
   bilgiler için yeterli mi? (İlgili modülün alan listesi bilinmiyor.)
7. **Kaçırma kuralı:** süresi dolmuş zamanlanmış duyuru hiç gösterilmez, yalnız
   bildirilir. "Gün içinde geç de olsa göster" istenirse kural değişir.
8. **Resmî tatil:** Aşama 3'e (Okul Zili takvimi) kadar tatil günlerinde tekrarlı
   planlar elle duraklatılacak. Kabul edilebilir mi?
9. Acil yayının okulun acil durum planında bir "uyarı aracı" olarak yazılıp
   yazılamayacağı iş güvenliği uzmanı ve sivil savunma sorumlusunun kararıdır;
   yazılım bu iddiada bulunmaz.

Ders programı ve program kilidi (0.4.0):

10. **Teneffüs kilidi gecikmesi** 2 dakika seçildi. Öğretmen dersi uzatırsa kodla açar;
    2 dakika uygun mu?
11. **Dersi olmayan saatte kilit** varsayılan açık. Boş saatte tahtanın öğretmence bireysel
    çalışma için kullanılması okulda olağan mı? Olağansa varsayılan kapatılır.
13. **Derslik programı kaynağı:** (0.10.0'da aSc XML, şablon CSV/XLSX ve yapay zekâ yolu, §12.3;
    0.12.0'da e-Okul "Haftalık Ders Programları" raporu, §12.4.) Kalan: aSc XML'in (öğretmenleri "Ö1,
    Ö2…" diye adlandırılmış kopyadan) bir örneği gelirse aSc okuyucusunun "deneme" etiketi kalkar. e-Okul
    raporunda bir okulun örneği görüldü; başka okulun raporunda (tek devre, hazırlık sınıfı, Cumartesi,
    farklı ders sayısı) yerleşim aynı mı, okulda denenecek.
14. **Sınav pencereleri:** Okul Zili'nde planlanmış sınav sırasında program kilidi askıya
    alınıyor. Sınav sırasında tahtaların kilitli kalması mı istenir? (0.5.0'da Tahta Kontrol'ün
    kendi sınav kipi bu soruyu karşıladı: sınav penceresindeki tahta sınav ekranında kilitlidir.)
15. **Kurum içi karar:** teneffüste tahtaların kilitlenmesine ilişkin öğretmenler kurulu ya
    da okul yönetimi kararı var mı/gerekli mi? Varsa arayüzde ona atıf yapılabilir;
    yazılım hiçbir mevzuat maddesine dayanak olarak atıf yapmıyor.
17. **Program kilidi süresi tahtada en çok 8 saat** sayılır. Gün boyu dersi olmayan
    dersliklerde bu, tahtanın öğleden sonra kendiliğinden açılması demektir; uygun mu?

Zil düzenleyici ve ders programı içe aktarma (0.10.0; yanıt gelene kadar karar geçerli):

54. **Tarihe özel çizelgeyi idareci de ekleyebilsin mi?** Karar: yalnız yönetici; idareci İstisna ile
    program kilidini durdurabilir.
55. **Sabahçı ve öğlenci devrenin dersleri zamanda çakışıyor mu?** Karar: çakışma uyarıdır, kaydı
    engellemez; çakışan aralıkta teneffüs kilidi verilmez.
56. **Yarıyıl ortasında saat değişikliği** için "şu tarihten itibaren" tarihe özel çizelge yeterli mi,
    yoksa haftalık düzenin ileri bir tarihte kendiliğinden değişmesi mi isteniyor? Karar: tarihe özel çizelge.
57. **Tahta Kontrol'de girilen tarihe özel çizelge Okul Zili'nin tarih kurallarından önce gelsin mi?**
    Karar: evet (tatiller hariç; tatil her zaman üstte).
58. **Birleşik derste** (iki şube tek derslikte) tahtaya hangi şube yazılsın? Karar: düzey sırasındaki
    ilk şube + uyarı. **İki haftada bir** yapılan dersler her hafta dolu sayılır; yeterli mi?
59. **Yapay zekâ aracı:** kurumun izin verdiği bir araç var mı? Panelde araç adı geçmez, yalnız genel
    KVKK uyarısı durur.

Sınav kipi ve sınav yoklaması (0.5.0):

18. **Maske biçimi:** "Ah*** Yı****" (harf sayısı kadar yıldız) uygulandı. Sabit uzunluk
    ("Ah* Yı*") daha az bilgi verir ama aynı baş harfli öğrencileri ayırmak zorlaşır. Hangisi?
19. **Giriş penceresi** 10 dakika. Okulun teneffüs süresine göre uygun mu (önceki dersi
    bölüyor mu)?
20. **Gözetmen kodu tahtayı açabilsin mi?** Şimdilik gözetmen kodu yalnız yoklama açar; sınav
    ekranını tahtada kapatma ("Sınav ekranını bu tahtada kapat") uygulanmadı, salonda sınav
    kipi panelden kaldırılır. Gözetmenin tahtadan kapatabilmesi istenir mi?
21. **Sınav kuralları** varsayılan metni okulun uygulamasına uyuyor mu? Özellikle "ilk ve son
    10 dakika salondan çıkılmaz" maddesi okul tercihi olarak yazıldı; dayanak gösterilmedi.
24. **Şube duyurusu** tahtada gösterilsin mi, yoksa kâğıt liste yeter mi? Gösterilecekse süre
    (varsayılan 10 dk) uygun mu?
25. **Kelebek'e dışa aktarım:** Kelebek'e "Tahta Kontrol için dışa aktarım" (süre, gözetmen,
    hazır maskeli liste) eklenirse R5'teki süre eksikliği ve açık adların taşınması ortadan
    kalkar; komşu projede değişiklik ister. İstenir mi?
26. **Gözetmen adı** fişte ve icmalde isteğe bağlı elle yazılıyor (Kelebek'in görevlendirme
    çıktısı içe aktarılmıyor). Yeterli mi?

Ders yoklaması (0.6.0):

28. **"Geç geldi"** ayrı işaret olarak gerekli mi? (Karar, 18.11.2026, 0.14.0: evet; yalnız her devrenin
    ilk dersinde, "yok" sayımına girmeden ayrı sayılır; §14.2.)
29. **Kilitli tahtada doğru PIN kilidi de açsın mı?** Karar: açmaz; yoklama bitince kilit geri gelir.
30. **PIN'i öğretmen kendisi değiştirebilsin mi?** Karar: hayır; idare yeni PIN üretir (sınıf
    önünde iki kez PIN yazdırmak gözetlenme riskini artırır).
31. **Tahtadaki ad görünümü:** varsayılan "Ayşe Y." uygun mu? Seçenek: "1047 A. Y.". Ad soyadın
    açık gösterimi bilerek kaldırıldı. (Karar, 18.11.2026, 0.14.0: varsayılan "123 Ayşe Y.", okul no
    sırasıyla; eski iki biçim seçilebilir; tam soyad yine gösterilmez; §14.2.)
33. **Aydınlatma:** okulun öğrenci/veli aydınlatma metni "ders yoklamasının etkileşimli tahtadan
    alınıp okul sunucusunda tutulmasını" kapsıyor mu?
34. **Öğretmen listesi kaynağı:** öğretmenler elle ekleniyor; e-Okul personel listesi (OOK01001R1)
    aktarımı istenir mi?
35. **İcmal üstbilgisi:** yazdırılan icmalde okul adı istenir mi? (Şimdi yok; "Düzenleyen/İmza"
    satırı var.)
36. **Kimler icmal görür:** bütün idareci hesapları mı, yalnız devamsızlıktan sorumlu müdür
    yardımcısı mı? (Şimdi bütün idareciler.)
37. **Yoklaması alınmayan derse tahtada hatırlatma** (ders ortasında küçük uyarı) istenir mi?
    (Kapsam dışı bırakıldı.)
38. **"Yoklama Al" kısayolu** ETAP'ta öğretmen hesabının menüsünde görünüyor; masaüstüne de
    konulsun mu? (Sahada denenecek.)
39. **İkinci çakışma:** ortak sözlük M1 "yine çakışırsa tam no" diyor, M2 ise "ad ve numara
    tahtada hiçbir zaman ikisi birden açık görünmez". "Ayşe Y. (1047)" M2'ye aykırı olacağından
    ikinci çakışmada o öğrenciler "1047 A. Y." biçimine geçer. Uygun mu?
40. **Program yokken icmal:** ders programı yüklenmemişse icmal, günlük ızgara gibi 8 ders
    saati varsayar ("ders programı yüklü değil, 8 saat varsayıldı"). Okulun günlük ders sayısı
    farklıysa programın yüklenmesi gerekir.
65. ~~**Düzeltmeden sonra tahtadan yeniden alınan yoklama** idarenin şube defterindeki düzeltmesinin üstüne
    geçsin mi?~~ **Kapandı (kullanıcı kararı, 18.11.2026):** evet, "en son işlem geçerlidir"; gerekçe ve yan
    etkiler §14.2. Yeniden tartışılmaz.
66. **Mazeret türleri** (izinli, raporlu, mazeretli, görevli) ve dayanak seçenekleri okulun uygulamasına
    uyuyor mu? Defterde tür harfi görmek istenir mi? (Şimdi tek "Ö".)
67. **Teneffüste ön seçim:** program hangi dersin kastedildiğini göstermiyorsa "biten / başlayacak"
    sorulur. Her zaman başlayacak ders mi seçilsin?
68. **Aydınlatma:** okulun aydınlatma metni tahtada okul numarası ile adın birlikte görünmesini ve mazeret
    türünün (raporlu dahil) okul sunucusunda tutulmasını kapsıyor mu? (Soru 33'ün devamı.)

Altyapı (0.7.0 ve 6B):

42. **Hizmet hesabı Yerel Hizmet (LocalService) olsun mu?** (Karar, 0.8.0: evet, en az yetki; §15.6.)
    Sonucu: yedeğin ikinci kopyası ağ paylaşımına yazılamaz, yalnız yerel disk/USB. Ağ paylaşımı
    gerekiyorsa daha geniş yetkili hesap gerekir.
43. **Parola belirlenmeden yedek almamak** kabul mü? (Karar: hiç almamak + panoda sürekli kırmızı şerit.)
44. **Saklama:** varsayılan 14 günlük yedek yeterli mi? Okulun imha politikası daha kısa süre
    istiyorsa ayardan 3 güne kadar indirilebilir.
45. **Arıza kategorileri** okulun ihtiyacına uyuyor mu; eklenecek/çıkarılacak var mı?
46. **Öğrenci hesabından arıza bildirimi** açık kalsın mı? (Karar: açık; saatte 3 sınırı ve kayıtta
    hesap sınıfı görünür.)
47. **Arıza açıklamasındaki kişi adı:** yönetici açıklamayı sonradan düzeltebilsin mi (düzeltme hareket
    geçmişine "açıklama düzeltildi" diye düşer, eski metin saklanmaz)? Şimdilik düzeltme yok.
48. **Demirbaş numarası biçimi:** taşınır kayıt sistemindeki sicil biçimi mi, serbest metin mi?
    (Şimdi serbest metin, en çok 40 karakter; dayanak §18'de doğrulanacak.)
49. **Kapalı arızalar** ne kadar saklansın? (Karar: süresiz; cihaz bakım geçmişi.)
50. **Sunucu bilgisayarının güç ayarı** (uyku kapalı) kim tarafından yapılacak? Yazılım yalnız uyarır.
51. **Okul DNS'inde sunucu için ad tanımlanabiliyor mu?** Tanımlanabiliyorsa adres listesine eklenmesi
    önerilir; IP habersiz değişince tahtalar ada geçer.
52. **Envanter CSV'sinde MAC ve IP** bulunuyor (şartname böyle istiyor; eski tahta CSV'si bu iki alanı
    dışarıda bırakıyordu). Cihaz verisidir ama ağ yönetimi bilgisidir; CSV'den çıkarılsın mı?
53. **Arıza penceresi okulun renklerini kullansın mı?** Şimdi varsayılan tahta paletiyle çiziliyor
    (pencere servisten durum yayını almaz). İstenirse servis pencereye yalnız paleti verebilir.
USB anahtar (0.11.0; yanıt gelene kadar karar geçerli):

60. **Öğretmen anahtarında PIN sorulsun mu?** (Karar, 0.11.0: varsayılan sorulmaz; Ayarlar'dan açılır.
   Bedeli: bellek tahtada takılıyken bir öğrenci dosyayı kopyalarsa o öğretmen adına yoklama yazıp kilidi
   açabilir; her kayıt anahtar kimliğiyle iz bırakır ve yoklama düzeltilebilir.)
61. **İdare anahtarıyla alınan yoklama kimin adına?** (Karar, 0.11.0: "idare (kullanıcı adı)" adına,
   öğretmen seçilmez. İstenirse tahtada dersin öğretmenini seçme adımı eklenir.)
62. **Kilidi hangi anahtar açsın?** (Karar, 0.11.0: ayar açıkken idare ve öğretmen anahtarlarının ikisi
   de; ayar kapatılınca hiçbiri. Yalnız idare anahtarı seçeneği istenirse ayar genişletilir.)
63. **Tahtada bellek takınca dosya yöneticisi kendiliğinden açılıyor mu?** Açılıyorsa anahtar dosyası
   ekranda herkese görünür; PIN varsayılanları buna göre gözden geçirilir. Okulda denetlenecek.
64. **Belleğin her tanınması işlem kaydına yazılsın mı?** (Karar, 0.11.0: yazılmaz. Tahta belleği takılır
   takılmaz, dokunuş beklemeden tanır; bellek yalnız sunum için takıldığında da. Her tanımayı kayda yazmak,
   işlem kaydını gören her panel kullanıcısına personelin gün gün hangi tahtada olduğunu süresiz gösterirdi;
   bu, "yalnız son kullanım" kararıyla çelişir. Kayda yalnız yoklama, kilit açma ve reddedilen denemeler
   düşer — bugünkü kod + PIN yoklamasının kaydıyla aynı düzey. İşlem kaydı sayfası idareciye de açıktır;
   USB satırları yalnız yöneticiye gösterilsin mi?)

## 18. Doğrulanacak dayanaklar

Arayüzde hiçbir mevzuat maddesine atıf yapılmaz. Belgeye dayanak olarak yazılmadan
önce metni yerelde doğrulanması gerekenler:

- KVKK md. 12 (veri güvenliği yükümlülüğü) — metin yerelde yok. Sınav listesinin saklama
  ve silme tedbirleri (§13) için de dayanak olarak yazılmadı.
- Sınav kurallarındaki "ilk ve son 10 dakika salondan çıkılmaz" kuralının dayanağı (soru 21);
  okul tercihi olarak yazıldı.
- Gözetmenin yoklama alma ve tutanak düzenleme görevine ilişkin hüküm; şimdilik yalnız
  Kelebek'in salon evrakı (R1) uygulamasına dayanıldı (K5: tahtadan yoklama kâğıdın yanında yardımcı kayıttır).
- Yazılımın acil durum yayınının acil durum planında "uyarı sistemi" sayılıp
  sayılamayacağı (soru 9).
- Tatbikat verisinin MEBBİS İSG modülüne girilecek biçimi (soru 6).
- Boş ders uyarısı için aydınlatma gerekip gerekmediği (KVKK md. 10) ve öğretim yılı sonuna kadar
  saklamanın okulun kişisel veri saklama ve imha politikasıyla uyumu (K3, K6; öğretmenlerin
  bilgilendirilmesi okul idaresinin sorumluluğundadır, belge mevzuat atfı yapmaz).
- Etkileşimli tahtaların kullanımına ilişkin MEB/YEĞİTEK düzenlemesi (varsa). Teneffüs
  kilidi bir okul yönetimi tedbiridir; öğrencinin kendi bilişim aracıyla ilgili disiplin
  hükmü okulun tahtası için dayanak gösterilmez (soru 15).
- Ders yoklaması: okulun devam takibi yükümlülüğüne ilişkin Ortaöğretim Kurumları
  Yönetmeliği md. 36'nın yoklamaya ilişkin fıkrası — depoda yalnız md. 36/7 (özür belgesi) metni
  var; fıkra numarası yazılmadı (e-Okul'a ders saati bazında işlendiği K2 ile bilindi; yarım/tam güne
  çevirme yapılmaz). KVKK md. 12 (veri güvenliği) yoklama için de doğrulanacak. Aydınlatma metninin
  kapsamı (KVKK md. 10, soru 33) ve öğretim yılı sonuna kadar saklamanın imha politikasıyla uyumu (K3).
- Mazeret kaydı (0.14.0): "raporlu" türünün özel nitelikli kişisel veri sayılıp sayılmayacağı (KVKK md. 6) ve
  aydınlatma metninin kapsamı (md. 10; soru 68) — metinler yerelde doğrulanmadı; tedbir olarak serbest metin
  alınmadı ve tür mazeret sayfası dışında gösterilmedi. Arayüz atıf yapmaz.
- Şifreli yedek: KVKK md. 12 ve Kurul'un "yeterli önlemler" kararındaki kriptografik yöntem ve
  anahtarların ayrı tutulması önlemleri; metinleri yerelde usulünce yok, arayüz bunlara atıf yapmaz.
- Demirbaş numarası biçimi için taşınır mal mevzuatındaki sicil/kod hükmü (soru 48).
- Arıza açıklamasında kişi adının düzeltilmesi/silinmesi talebi (KVKK md. 7 ve 11 açısından; soru 47).
