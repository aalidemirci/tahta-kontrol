# Tahta Kontrol — tasarım

Sürüm 0.2.0 · 16.11.2026

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

Seçili tahtalarda tam ekran başlık + metin; süre dolunca kalkar; istenirse
öğretmen tahtadan kapatabilir. Kalan süre sunucuda hesaplanır (tahta saatine
güvenilmez). Tahta duyuru süresi içinde çevrimiçi olmazsa duyuru düşer.

## 7. Otomatik kapatma

Enerji tasarrufu için sunucu, ayarlanan saatlerde (hafta içi) o an açık olan
tahtalara kapatma komutu verir; hafta sonunda belirlenen süreden uzun açık kalan
tahtaya da aynı komut gider. Kullanılan tahtada 60 saniyelik geri sayım ve
"Vazgeç" düğmesi çıkar; kilitli ya da oturumsuz tahta uyarısız kapanır. Saatinden
sonra açılan tahtaya dokunulmaz. Resmî tatil takvimi yoktur. Uzaktan açma
(Wake-on-LAN) güvenilir olmadığı için akışın parçası değildir; tahta gerektiğinde
cihazdan açılır.

## 8. Güncelleme

Sunucu, ajan `.deb` paketini kendi içindeki ajan kaynağından üretir. Sunucu
güncellenince paket de yenilenir; panelde sürümü eski tahtalar "Güncelleme var"
diye görünür ve "Ajanı güncelle" komutuyla paketi sunucudan indirip kurar
(özet denetimiyle). Kurulum servisten bağımsız bir birimde koşar. Otomatik ve
kademeli yayma ile başarısız güncellemede geri dönüş henüz yoktur.

## 9. Platforma taşınabilirlik

- Sunucu saf Python'dır; Windows'a özgü tek parça paketleme ve denetim
  penceresidir. Pardus sürümü için `.deb` + systemd birimi yazmak yeter.
- Ajanın işletim sistemine dokunan bütün işlevleri `tahta_ajan/sistem.py`
  içindedir. Windows'lu tahta desteği bu dosyanın ve bir ekran arka ucunun
  (ör. tkinter) yazılmasıdır.

## 10. Görünüm ve okul kimliği

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
  çevrimdışı gri, sorun kırmızı. Okulun rengi bunlara karışmaz; her durum
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

## 11. Yol haritası

| Aşama | İçerik | Durum |
|---|---|---|
| 0–1 | Sunucu, ajan, kayıt, pano, kilit, duyuru, kapatma, tanılama, güncelleme, otomatik kapatma | 0.1.2 — ETAP'ta denenecek |
| 1.5 | Görünüm ve okul kimliği: okul logosu ve renkleri, yeni panel ve tahta ekranı tasarımı | 0.2.0 — ETAP'ta denenecek |
| 2 | Duyuru zamanlama ve hedef grupları (kat, düzey, devre), acil durum yayını | — |
| 3 | Ders programı ve zil saatleri (Okul Zili'nden), programa bağlı otomatik kilit/açma, boş geçen ders uyarısı, oturum temizliği | — |
| 4 | Kelebek sınav duyurusu ve sınav kipi (Kelebek Sınav verisinden, maskeli liste), sınav yoklaması | — |
| 5 | Ders yoklaması (öğretmen PIN'i, e-Okul'a giriş için icmal) | — |

Ayrıca bekleyenler: sunucunun Windows hizmeti olarak çalışması (şimdi oturum
açılınca başlar), şifreli yedek, paket imzası, sunucu IP'si değişince ajanın
yeniden bulması, tahta envanteri ve arıza bildirimi.
