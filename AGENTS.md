# Tahta Kontrol geliştirme

Değişiklik yapmadan önce `CLAUDE.md` dosyasının tamamını ve ilgili
`docs/tasarim.md` bölümünü okuyun. Mevcut mimari kararları burada da geçerlidir.
Gerçek ortam doğrulamaları `docs/saha-denemesi.md` içindedir.

- Sunucu Python 3.12, FastAPI, SQLite; ajan Pardus ETAP ve yalnız standart kitaplık.
- Arayüz, yorum, test ve doküman dili Türkçe; tanımlayıcılar ASCII Türkçe.
- Deneme için `scripts/dev.ps1` kullanın: ayrı veri klasörü, 8797/8798 ve yalnız yerel erişim.
- Bu bilgisayara Windows hizmeti kurmayın; üretim verisi ve sertifikasına dokunmayın.
- Gerçek okul verisi, sırlar ve ekran görüntüleri Git'e eklenmez.
- Doğrulama: `scripts/dev.ps1 test` ve `scripts/dev.ps1 lint`.
- Ajan davranışı, gizlilik ve sürüm değişikliklerinde CLAUDE.md kurallarını izleyin.
