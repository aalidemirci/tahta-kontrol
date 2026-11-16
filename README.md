# Tahta Kontrol

Okul ağında çalışan etkileşimli tahta kontrol ve duyuru sistemi. İnternet
gerektirmez; veri okulda kalır, dışarıya hiçbir şey gönderilmez.

> **Durum: 0.3.0, saha denemesi sürümü.** Debian 12 ve Pardus 25 masaüstünde denendi;
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

Planlananlar: ders programına bağlı otomatik kilit, sınav duyurusu ve sınav
yoklaması, ders yoklaması (`docs/tasarim.md`, yol haritası).

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
- Sunucu arızası dersi engellemez: sunucuya ulaşılamazsa kilit tahtadan açılabilir.
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
