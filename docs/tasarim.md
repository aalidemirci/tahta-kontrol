# Tahta Kontrol — tasarım

Sürüm 0.3.0 · 16.11.2026

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
- Ortak kod sınıfın önünde girilir ve görülebilir; kalıcı çözüm ders programına
  bağlı otomatik açma ve yalnız yoklama anında öğretmen PIN'idir (sonraki aşama).

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

## 12. Yol haritası

| Aşama | İçerik | Durum |
|---|---|---|
| 0–1 | Sunucu, ajan, kayıt, pano, kilit, duyuru, kapatma, tanılama, güncelleme, otomatik kapatma | 0.1.2 — ETAP'ta denenecek |
| 1.5 | Görünüm ve okul kimliği: okul logosu ve renkleri, yeni panel ve tahta ekranı tasarımı | 0.2.0 — ETAP'ta denenecek |
| 2 | Duyuru zamanlama ve hedef grupları (bina, kat, düzey, devre, gruplar, CSV), acil durum ve tatbikat yayını | 0.3.0 — Debian 12 kabında denendi; ETAP'ta denenecek |
| 3 | Ders programı ve zil saatleri (Okul Zili'nden), programa bağlı otomatik kilit/açma, boş geçen ders uyarısı, oturum temizliği | — |
| 4 | Kelebek sınav duyurusu ve sınav kipi (Kelebek Sınav verisinden, maskeli liste), sınav yoklaması | — |
| 5 | Ders yoklaması (öğretmen PIN'i, e-Okul'a giriş için icmal) | — |

Ayrıca bekleyenler: sunucunun Windows hizmeti olarak çalışması (şimdi oturum
açılınca başlar), şifreli yedek, paket imzası, sunucu IP'si değişince ajanın
yeniden bulması, tahta envanteri ve arıza bildirimi.

Aşama 2'den sonraya bırakılanlar (göç gerektirmez): panoda "Hızlı seç" ve "Seçili
tahtalara alan ata", plan formunda "sonraki 3 gösterim" canlı önizlemesi, çakışan
plan uyarısı.

## 13. Açık sorular

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

## 14. Doğrulanacak dayanaklar

Arayüzde hiçbir mevzuat maddesine atıf yapılmaz. Belgeye dayanak olarak yazılmadan
önce metni yerelde doğrulanması gerekenler:

- KVKK md. 12 (veri güvenliği yükümlülüğü) — metin yerelde yok.
- Yazılımın acil durum yayınının acil durum planında "uyarı sistemi" sayılıp
  sayılamayacağı (soru 9).
- Tatbikat verisinin MEBBİS İSG modülüne girilecek biçimi (soru 6).
