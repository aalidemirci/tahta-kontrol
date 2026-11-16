# Tahta Kontrol — tasarım

Sürüm 0.5.0 · 16.11.2026

## 1. Amaç ve kapsam

Okul idaresinin etkileşimli tahtaları tek panelden yönetmesi: durum izleme,
kilitleme, duyuru, kapatma; orta vadede kelebek sınav duyurusu, sınav yoklaması
ve ders yoklaması. Veri okulda kalır, internet gerekmez.

Benzer amaçlı bir kiosk tarayıcı denemesinden çıkan dersler tasarıma işlendi:
sunucudan tahtaya komut kanalı, işletim sistemi oturumunun üstünde duran kilit,
cihaz anahtarının yalnız özetinin saklanması ve internete muhtaç olmayan kurulum.

## 2. Bileşenler

| Bileşen | Nerede | Teknoloji |
|---|---|---|
| Sunucu | İdaredeki bir Windows bilgisayarı | Python 3.12, FastAPI, SQLite, Jinja2 |
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
  bilgisayarının güvenliğine eşittir. Çok okullu dağıtımdan önce paket imzası eklenmeli.

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
uyar; niteliği boş tahta o ölçüte hiçbir zaman uymaz. Hedef plan kaydında değil
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

Ayrı yetkiyle (`acil_yetki`, rolden bağımsız; ilk kurulumdaki ve göçteki yöneticiler
alır, yalnız yönetici verir, kimse kendi yetkisini kaldıramaz), parolanın yeniden
girilmesi ve türe göre değişen açık onayla başlatılır. Tür (gerçek acil durum /
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

Sunucu, ajan `.deb` paketini kendi içindeki ajan kaynağından üretir. Sunucu
güncellenince paket de yenilenir; panelde sürümü eski tahtalar "Güncelleme var"
diye görünür ve "Ajanı güncelle" komutuyla paketi sunucudan indirip kurar
(özet denetimiyle). Kurulum servisten bağımsız bir birimde koşar. Otomatik ve
kademeli yayma ile başarısız güncellemede geri dönüş henüz yoktur.

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

- **Zil saatleri.** Okul Zili'nin `ayarlar.json` dosyası ya da `.okulzili` yedeği
  yüklenir; Okul Zili sunucu bilgisayarında kuruluysa tek düğmeyle sabit yolundan salt
  okunur alınır. Yalnız ders saatleri ve takvim (öğretim dönemi, ara tatiller, resmî
  tatiller, tarih kuralları) alınır; ses, okul adı, cihaz alanları okunmaz. Önizlemeden
  sonra onaylanır. Okul Zili'si olmayan okul ders akışından (ilk ders, süre, teneffüs,
  öğle arası) tablo üretir ve tablodan düzeltir; takvimi olmayan okulda tatiller İstisna
  olarak girilir. Okul Zili'ne hiçbir şey yazılmaz.
- **Derslik programı.** Hangi tahtada hangi gün hangi ders saatinde ders **olduğu**;
  öğretmen ve ders adı alınmaz (KVKK: amaçla sınırlı veri — kilit ve uyarı için dersliğin
  dolu olup olmadığı yeter). CSV ile topluca (önizlemeli; eşleşmeyen derslikler ve hatalı
  satırlar listelenir, dosyada geçmeyen tahtaya dokunulmaz) ya da tahta sayfasındaki
  haftalık ızgarayla girilir. Şube isteğe bağlıdır, yalnız panelde görünür. Programı
  girilmemiş tahta yalnız teneffüste kilitlenir ve boş ders uyarısı üretmez.
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
- **Boş ders uyarısı** (varsayılan kapalı). Derslik programında dersi olan tahta, ders
  başladıktan sonra eşik süre (5–30 dk) boyunca kesintisiz kapalı, program kilidinde ya da
  oturumsuz kalırsa panelde uyarı çıkar; idarenin bilerek kilitlediği tahta uyarı vermez.
  Tahta sonra kullanılırsa uyarı silinmez, "10:14'te kullanılmaya başlandı" diye kapanır.
  Uyarı tahtanın kullanılıp kullanılmadığını gösterir, dersin işlenip işlenmediğini değil;
  öğretmen adı tutulmaz, işlem kaydına yazılmaz, dışa aktarılmaz, tahtada görünmez ve 30
  gün sonra silinir (silmede `secure_delete` ve WAL budama). Sunucu yeniden başlarsa o
  dersin uyarısı geç ya da hiç üretilmez (yanlış uyarı yerine eksik uyarı).
- **Sonraya bırakılanlar** (göç gerektirmez): ortak hesapta oturum temizliği (açık
  pencereleri kapatma, tarayıcı oturum verisini silme, indirilenleri karantinaya alma) ve
  boş ders uyarısında "tahtaya dokunulmamışsa da uyar" ölçütü. Pencere yöneticisi, tarayıcı
  profil yolları ve merkezi yönetimin tepkisi ETAP'ta doğrulanmadan güvenle yazılamaz;
  geri dönüşsüz veri kaybı riski taşır.

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
koltuk numaraları ve sayılar yazılır). Kişisel veri sınav tarihinden **30 gün** sonra
kendiliğinden silinir (`secure_delete` + WAL budama); salon başına "mevcut / gelmeyen" sayıları
kalır. İdare daha önce de silebilir (yalnız sınav bittikten sonra).

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
acil > kapatma uyarısı > gözetmen > duyuru > sınav > kilit. Liste ve gözetmen belirteci
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

**Şube duyurusu:** sınavdan önce şube dersliklerinde (tahta sayfasındaki "Şubeler" alanı)
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

## 14. Yol haritası

| Aşama | İçerik | Durum |
|---|---|---|
| 0–1 | Sunucu, ajan, kayıt, pano, kilit, duyuru, kapatma, tanılama, güncelleme, otomatik kapatma | 0.1.2 — ETAP'ta denenecek |
| 1.5 | Görünüm ve okul kimliği: okul logosu ve renkleri, yeni panel ve tahta ekranı tasarımı | 0.2.0 — ETAP'ta denenecek |
| 2 | Duyuru zamanlama ve hedef grupları (bina, kat, düzey, devre, gruplar, CSV), acil durum ve tatbikat yayını | 0.3.0 — Debian 12 kabında denendi; ETAP'ta denenecek |
| 3 | Ders programı ve zil saatleri (Okul Zili'nden ya da elle), derslik programı, programa bağlı otomatik kilit/açma, istisnalar, boş geçen ders uyarısı | 0.4.0 — Debian 12 kabında denendi; ETAP'ta denenecek. Oturum temizliği sonraya (§12) |
| 4 | Kelebek sınav duyurusu ve sınav kipi (Kelebek Sınav verisinden, maskeli liste), sınav yoklaması | 0.5.0 — Debian 12 kabında denendi; ETAP'ta ve gerçek Kelebek çizelgesiyle denenecek. Tablo gösterimi, tahtadan sınav ekranını kapatma ve sayfalı ızgara sonraya (§13) |
| 5 | Ders yoklaması (öğretmen PIN'i, e-Okul'a giriş için icmal) | — |

Ayrıca bekleyenler: sunucunun Windows hizmeti olarak çalışması (şimdi oturum
açılınca başlar), şifreli yedek, paket imzası, sunucu IP'si değişince ajanın
yeniden bulması, tahta envanteri ve arıza bildirimi.

Aşama 2'den sonraya bırakılanlar (göç gerektirmez): panoda "Hızlı seç" ve "Seçili
tahtalara alan ata", plan formunda "sonraki 3 gösterim" canlı önizlemesi, çakışan
plan uyarısı.

## 15. Açık sorular

Yanıt gelene kadar bu belgedeki karar geçerlidir.

1. **"Devre" ne demek?** İkili eğitimdeki sabah/öğle öğretimi olarak alındı; bina
   ayrıca "bina" alanıyla karşılanır. Okulda başka anlamda (ana bina/ek bina gibi)
   kullanılıyorsa alan adı ve değerleri değişir.
2. **Acil yayın onayı yeterli mi?** Karar: tek kişi + parola + açık onay kutusu. İki
   kişinin onayı gerçek acil durumda gecikme yaratır; istenirse eklenir.
3. **Acil yayın yalnız bütün okula mı?** Karar: evet. Yalnız bir binaya yayın
   gerekiyorsa bina seçimi eklenebilir.
4. **Varsayılan acil yetkisi:** mevcut ve ilk kurulumdaki yöneticilere verildi,
   idarecilere verilmedi. Uygun mu?
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
12. **Boş ders uyarısı** personel denetimi gibi algılanabilir. Açılmadan önce öğretmenler
    kurulunda ya da yazılı bilgilendirmeyle duyurulmalı mı, okulun aydınlatma metnine
    eklenmeli mi? 30 günlük saklama uygun mu? (Dayanak §16'da doğrulanacak.)
13. **Derslik programı kaynağı:** okulda ders programı hangi programla hazırlanıyor
    (e-Okul, bir ders dağıtım programı, Excel)? Dışa aktardığı dosyanın uydurma verili bir
    örneği paylaşılırsa ikinci bir içe aktarma biçimi eklenebilir; şimdilik yalnız kendi
    CSV biçimimiz var.
14. **Sınav pencereleri:** Okul Zili'nde planlanmış sınav sırasında program kilidi askıya
    alınıyor. Sınav sırasında tahtaların kilitli kalması mı istenir? (0.5.0'da Tahta Kontrol'ün
    kendi sınav kipi bu soruyu karşıladı: sınav penceresindeki tahta sınav ekranında kilitlidir.)
15. **Kurum içi karar:** teneffüste tahtaların kilitlenmesine ilişkin öğretmenler kurulu ya
    da okul yönetimi kararı var mı/gerekli mi? Varsa arayüzde ona atıf yapılabilir;
    yazılım hiçbir mevzuat maddesine dayanak olarak atıf yapmıyor.
16. **Oturum temizliği** (sonraya bırakıldı): `ogrenci` hesabı tahtada kullanılıyor mu;
    tarayıcı geçmişi ve kayıtlı parolalar da silinsin mi (Firefox'ta geçmiş yer imleriyle
    aynı dosyadadır)? ETAP'taki tarayıcılar ve profil yolları sahada görülmeden yazılmayacak.
17. **Program kilidi süresi tahtada en çok 8 saat** sayılır. Gün boyu dersi olmayan
    dersliklerde bu, tahtanın öğleden sonra kendiliğinden açılması demektir; uygun mu?

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
22. **Saklama süresi** 30 gün. Mazeret sınavı takvimi uzun sürüyorsa süre uzatılmalı mı?
23. **Tahtadan yoklama kâğıt yoklamanın yanında mı, yerine mi?** Karar: yanında; icmalde
    "salon evrakındaki imzalı yoklama esastır" notu var.
24. **Şube duyurusu** tahtada gösterilsin mi, yoksa kâğıt liste yeter mi? Gösterilecekse süre
    (varsayılan 10 dk) uygun mu?
25. **Kelebek'e dışa aktarım:** Kelebek'e "Tahta Kontrol için dışa aktarım" (süre, gözetmen,
    hazır maskeli liste) eklenirse R5'teki süre eksikliği ve açık adların taşınması ortadan
    kalkar; komşu projede değişiklik ister. İstenir mi?
26. **Gözetmen adı** fişte ve icmalde isteğe bağlı elle yazılıyor (Kelebek'in görevlendirme
    çıktısı içe aktarılmıyor). Yeterli mi?

## 16. Doğrulanacak dayanaklar

Arayüzde hiçbir mevzuat maddesine atıf yapılmaz. Belgeye dayanak olarak yazılmadan
önce metni yerelde doğrulanması gerekenler:

- KVKK md. 12 (veri güvenliği yükümlülüğü) — metin yerelde yok. Sınav listesinin saklama
  ve silme tedbirleri (§13) için de dayanak olarak yazılmadı.
- Sınav kurallarındaki "ilk ve son 10 dakika salondan çıkılmaz" kuralının dayanağı (soru 21);
  okul tercihi olarak yazıldı.
- Gözetmenin yoklama alma ve tutanak düzenleme görevine ilişkin hüküm; şimdilik yalnız
  Kelebek'in salon evrakı (R1) uygulamasına dayanıldı (soru 23).
- Yazılımın acil durum yayınının acil durum planında "uyarı sistemi" sayılıp
  sayılamayacağı (soru 9).
- Tatbikat verisinin MEBBİS İSG modülüne girilecek biçimi (soru 6).
- Boş ders uyarısı için aydınlatma gerekip gerekmediği (KVKK md. 10) ve 30 günlük
  saklamanın okulun kişisel veri saklama ve imha politikasıyla uyumu (soru 12).
- Etkileşimli tahtaların kullanımına ilişkin MEB/YEĞİTEK düzenlemesi (varsa). Teneffüs
  kilidi bir okul yönetimi tedbiridir; öğrencinin kendi bilişim aracıyla ilgili disiplin
  hükmü okulun tahtası için dayanak gösterilmez (soru 15).
