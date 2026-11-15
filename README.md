# Tahta Kontrol

Okul ağında çalışan etkileşimli tahta kontrol ve duyuru sistemi. İnternet
gerektirmez; veri okulda kalır, dışarıya hiçbir şey gönderilmez.

> **Durum: 0.1.2, saha denemesi sürümü.** Debian 12 ve Pardus 25 masaüstünde denendi;
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
sunucudan güncellenmesi, kullanıcı yetkileri ve işlem kaydı.

Planlananlar: duyuru zamanlama, ders programına bağlı otomatik kilit, sınav
duyurusu ve sınav yoklaması, ders yoklaması (`docs/tasarim.md`, yol haritası).

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
- Ajan paketi henüz imzalı değildir; sunucu bilgisayarını yetkisiz erişime karşı koruyun.
- Güvenlik açığı bildirimi için herkese açık kayıt açmak yerine depo sahibine
  GitHub üzerinden özel olarak ulaşın.

## Sorumluluk

Bu yazılım Millî Eğitim Bakanlığı, TÜBİTAK ya da Pardus projesiyle bağlantılı
değildir ve onlarca onaylanmamıştır. Tahtalara yönetici yetkili yazılım kurmadan
önce kurumunuzun bilgi işlem kurallarını gözetin. Yazılım olduğu gibi sunulur.

## Lisans

[PolyForm Noncommercial 1.0.0](LICENSE): ticari olmayan kullanım serbesttir.
