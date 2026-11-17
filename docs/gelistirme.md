# Bu bilgisayarda geliştirme

17 Kasım 2026 tarihinde `aalidemirci/tahta-kontrol` deposunun `main` dalı,
`58ab6191d82e40c3da1f36c4b6b37466b828ecd3` commit'i indirildi. Sürüm: 0.12.0.
Mevcut `pyproject.toml` ve `uv.lock` korundu; Python 3.12.16 ile `.venv`
oluşturulup kilitli bağımlılıklar kuruldu. GitHub'a değişiklik gönderilmedi.

Kullanıcı bilgisi: bu bilgisayarda kurulu bir sunucu ve ona bağlı bir istemci
zaten var. Bu çalışma kaynak kodu ve ayrı geliştirme ortamı içindir; kurulu
hizmet, üretim verisi, sertifika ve bağlı istemci üzerinde işlem yapılmadı.
Yeni geliştirmeleri mevcut istemciye uygulamak ayrı bir dağıtım adımıdır.

## Komutlar

Depo kökünde PowerShell ile:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 sunucu
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 test
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 lint
powershell -ExecutionPolicy Bypass -File scripts\dev.ps1 paket
```

Panel: http://127.0.0.1:8797 — ilk açılışta deneme yönetici hesabı oluşturulur.
Sunucu Ctrl+C ile durdurulur. Veri ve deneme sertifikası `work/dev-veri/` altında
kalır. HTTP ve HTTPS yalnız bu bilgisayarı dinler. Okuldaki tahtaları bağlamak
için bu yerel geliştirme ayarları uygun değildir.

`paket` yalnız `dist/tahta-ajan.deb` üretir; ajanı kurmaz. Windows kurucusu için
mevcut `packaging/windows/build.ps1` ve ayrıca Inno Setup 6 gerekir. Kurucu bu
hazırlık sırasında üretilmedi ve Windows hizmeti kurulmadı.

## Editör

VS Code'da bu klasörü açın; önerilen Python, Debugger ve Ruff eklentilerini
kurun. F5 yapılandırması aynı yerel adresleri ve deneme veri klasörünü kullanır.
Test keşfi `.venv` yorumlayıcısıyla `tests/` altında yapılır.

## Ortamı yeniden kurma

Python 3.12 ve uv ile `scripts/dev.ps1 kur` veya `uv sync --locked` kullanın.
`.python-version` gerekli Python ailesini seçer. Bu bilgisayar için taşınabilir
uv çalışma alanının `../../work/tools/uv/uv.exe` konumuna indirildi; Python
`../../work/python/` altındadır. `.venv` taşınabilir değildir: klasörü başka
bilgisayara taşırsanız uv ile yeniden oluşturun.

İlk kurulumda indirmeler için Windows güven deposu gerekti. Aynı ağda gerekirse
`$env:UV_SYSTEM_CERTS = 'true'` kullanın; sertifika doğrulamasını kapatmayın.
Yeni Python indirmelerinin de çalışma alanında tutulması istenirse kurulumdan
önce `UV_PYTHON_INSTALL_DIR` ve `UV_CACHE_DIR` değişkenlerini çalışma alanındaki
uygun klasörlere ayarlayın. Betik `.env` dosyası okumaz; ortam değişkenlerini
PowerShell'de verin.

## Çalışma kuralları

Önce `CLAUDE.md`, ilgili `docs/tasarim.md` bölümü ve `AGENTS.md` okunur.
Gerçek okul verisi yerine yapay örnekler kullanılır. Pardus GTK, USB, oturum
temizliği ve Windows hizmet izinleri Windows birim testleriyle tam doğrulanmaz;
`docs/saha-denemesi.md` adımları ayrı deneme ortamında uygulanır.
