# 0.15.0 — panel arayüzü 1. aşama: yeni kabuk

18 Kasım 2026. Geliştirme kopyası; kurulu hizmet ve bağlı tahta değiştirilmedi, dağıtılmadı.
Denemeler uydurma veriyle ("Örnek Anadolu Lisesi") yapıldı; ekran görüntüsü ve gerçek veri depoya girmedi.
Tasarım ve aşama planı: `docs/tasarim.md` §11.1.

Kullanıcı isteği (18.11.2026): yönetim paneli "ilkel ve karışık" bulundu. Bütün panel için bir arayüz taslağı
hazırlandı (tıklanabilir prototip; depo dışında tutulur), kullanıcı taslağı gördü ve altı aşamalı planın
**1. aşamasına** onay verdi. Bu sürüm yalnız o aşamadır: sayfaların **çerçevesi** (kabuk) değişti, sayfaların
içi değişmedi.

## Ne değişti

- **Sol kenar menüsü.** Üstteki yatay şerit ve açılır gruplar kalktı. Menü üç kümedir ve en çok on öğedir:
  - *Her gün:* Tahtalar (altında Arızalar, Envanter, Gruplar, Tahta ekle), Duyurular, Yoklama
  - *Dönemlik:* Program, Sınavlar, Kişiler ve anahtarlar (öğrenciler, öğretmenler ve PIN, USB anahtarlar,
    öğretmen programı)
  - *Yönetim:* Yedekler, İşlem kaydı, Kullanıcılar, Ayarlar
- **Acil durum** kümelerin dışında, menünün en üstünde durur (renk + simge + sözcük); dar ekranda üst çubukta
  da her zaman görünür.
- **Menü role göre çizilir.** İdareciye yönetici öğeleri (Gruplar, Tahta ekle, Yedekler, Kullanıcılar, Ayarlar)
  hiç çizilmez. Uçların kendi yetki denetimi değişmedi; bu yalnız menünün görünümüdür.
- **Dar ekran.** 1024 px altında menü çekmecedir: üstte yapışkan bir çubuk (Menü, okul adı, Acil) durur, menü
  soldan açılır, arkadaki sayfa dokunulmaz olur, Esc ve dışarı tıklama kapatır. Telefonda (640 px altı)
  ayrıca alt çubuk vardır: Tahtalar, Duyurular, Yoklama, Menü. JavaScript kapalıyken de çekmece açılır
  ve kapanır.
- **Şube defteri** (beş günlük geniş tablo) 1600 px altında çekmece kipinde açılır; tablo menüye yer
  bırakmak için daralmaz.
- **Ölçek belirteçleri.** Yazı boyu, boşluk, köşe, gölge ve dokunma ölçüleri tek yerde tanımlandı
  (`stil.css`); gövde yazısı 15 px'ten 16 px'e çıktı (şube defteri 15 px'te kaldı).
- **Erişilebilirlik.** Dokunulan yerde (dar ekran, dokunmatik) düğme ve bağlantılar en az 44 px; klavye
  odağı her yerde görünür; simgesi olmayan durum rozetine şekil eklendi (durum yalnız renkle anlatılmaz);
  etkin menü öğesi renk + kalın yazı + çizgiyle belli olur; menüdeki arıza sayısı ekran okuyucuya "açık
  arıza" diye okunur.
- Küçük metin düzeltmeleri: ana sayfanın sekme başlığı ve tahta sayfasındaki geri bağlantısı "Tahtalar";
  Ayarlar'daki renk açıklaması "üst şerit" yerine "panelin menüsü" der.
- Yaygınlaşan yan etkiler giderildi: 1366 px'te daralan içerikte tablolar (hücre dolgusu, tek satır düğme
  sırası, yana kayan tabloda kenar gölgesi), sekme şeritlerinin sarması, telefonda fırça şeridinin sayfayı
  genişletmesi (0.14.0'da da vardı).
- Geliştirme aracı: `scripts/panel_olcum.mjs` — deneme sunucusuna karşı başsız tarayıcıyla her sayfada yatay
  taşma, kontrast, küçük yazı ve dokunma hedefi ölçer. Adres, hesap ve çıktı klasörü ortam değişkeniyle
  verilir; çıktı depo dışına yazılır.

## Ne değişmedi

- Sayfaların içeriği, adresler (URL), form gönderim uçları, veritabanı şeması ve göçler.
- **Ajan ve tahta ekranı.** Ajan kodu değişmedi. Sürüm yalnız statik dosya önbelleği için yükseldi
  (`stil.css?v=`, `panel.js?v=`); tahtalar 0.15.0 paketini yine de "güncelleme" olarak görür.
- Renk motoru (`tema.py`), okul renkleri, CSP (satır içi stil ve betik yok), dış kaynak ve derleme adımının
  olmaması, giriş ve ilk kurulum sayfaları (kabuksuz).
- Koyu görünümde menü zemini ve birincil düğme tonu `tema.py` çıktısıdır; dokunulmadı.

## Sonraki aşamalar (bu sürümde YOK)

Her biri ayrı sürüm ve ayrı onaydır; ayrıntı `docs/tasarim.md` §11.1.

| Aşama | Ne gelir |
|---|---|
| 2 | Ayarlar'ın bölümlere ayrılması (bugün tek uzun sayfa) |
| 3 | Ayrı Tahtalar listesi, satır düğmeleri, tahta sayfasında sekmeler |
| 4 | "Bugün" masası (şu an, bekleyen işler) |
| 5 | Yoklama / Program / Kişiler sekmelerinin ayrışması, tek sayfalık duyuru formu |
| 6 | Genel arama |

Bu yüzden bilinen geçici durumlar:

- Öğrenciler, Öğretmenler ve PIN, USB anahtarlar ve Öğretmen programı sayfaları hâlâ Yoklama sekme şeridini
  çizer; menüde ise "Kişiler ve anahtarlar" seçili görünür.
- Ayarlar tek uzun sayfadır; içindeki renk önizleme maketi hâlâ üst şeritli eski düzeni çizer.
- Kullanıcılar menüde ayrı öğedir (taslakta Ayarlar'ın bir bölümü).
- İdarecinin gördüğü sayfaların içinde yöneticiye ait birkaç bağlantı durur (tıklanınca uç reddeder); yalnız
  menü süzüldü.
- Envanter tablosu 1366 px'te kendi kutusunda yana kayar (0.14.0'da da kayıyordu).
- Bazı metinlerde "pano" sözcüğü kaldı.

## Taslaktaki sorular

Taslağın sorduğu on bir soruya ayrıca cevap verilmedi; **taslağın önerdiği seçenekler varsayıldı**
(ör. menü okulun şerit renginde, açık/koyu görünüm işletim sistemini izler, menü adı "Kişiler ve
anahtarlar"). Sorular `docs/tasarim.md` §17'de 69–79 numarayla açık duruyor; çoğu sonraki aşamaları
ilgilendirir.

## Nasıl denendi

- `uv run pytest -q`: 1173 geçti, 11 atlandı. `uv run ruff check .`: temiz. Yeni `tests/test_kabuk.py`: üç küme ve en çok on
  öğe, menü adreslerinin var olması, her sayfada tek etkin öğe, idareciye yönetici öğesinin çizilmemesi,
  giriş ve kurulumun kabuksuz kalması, menü ve durum yazısı kontrastı (dört palet), baskıda kabuğun
  gizlenmesi, `stil.css` varsayılanlarının `tema.varsayilan()` ile aynı kalması.
- Deneme sunucusunda (ayrı veri klasörü, 8797/8798, uydurma veri) başsız Edge ile 39 sayfa (38 sayfa + şube
  defterinin gün görünümü), 1366 px ve 390 px, açık ve koyu: yatay taşma 0, kontrast eşiği altı metin 0,
  kabukta küçük yazı 0, 390 px'te küçük dokunma hedefi 0.
- Ek genişlikler: 1024, 1093×500 (Windows %125 ölçeği benzetimi), 1280, 1600; idareci hesabıyla ayrıca.
- Çekmece senaryosu 390 ve 800 px'te: aç, arkadaki sayfanın dokunulmazlığı, Esc, odağın açan düğmeye
  dönmesi, pencere büyüyünce kapanma.
- Baskı: beş baskı sayfasının sayfa sayıları 0.14.0 ile aynı.
- Görüntülerin 1366 açık ve 390 açık olanlarının hepsine, koyuların bir bölümüne gözle bakıldı; kalan
  koyu görüntüler yalnız ölçümle denetlendi.

## Denenmeyenler ve bilinen sınırlar

- **Okulun gerçek bilgisayarlarında ve gerçek telefonda denenmedi.** Telefon ve dokunma, başsız tarayıcıda
  pencere genişliğiyle benzetildi. Yalnız Edge (Chromium) ile denendi; Firefox ve Safari'de bakılmadı.
- Ekran okuyucuyla denenmedi. JavaScript kapalı çekmece yalnız testte ve biçim kurallarıyla doğrulandı.
- Geri tuşuyla dönüşte çekmecenin kapalı gelmesi yapay olayla denendi; tarayıcının gerçek geri/ileri
  önbelleğiyle denenmedi.
- Kurucu ve `.deb` bu sürüm için üretilmedi; kurulu hizmette denenmedi.
- Taslaktaki `<progress>` bileşeni bu sürümde yok (kullanan sayfa yok); ölçek belirteçlerinin bir bölümü
  henüz kullanılmıyor, bileşenler yeniden çizildikçe taşınacak.
