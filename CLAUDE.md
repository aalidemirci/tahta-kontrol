# CLAUDE.md — Tahta Kontrol

Okul ağında çalışan etkileşimli tahta kontrol ve duyuru sistemi. Bir bilgisayarda
**sunucu** (Windows masaüstü programı), her tahtada **ajan** (Pardus ETAP, `.deb`).
İdare, paneli tarayıcıdan kullanıcı adıyla açar; diğer bilgisayarlara kurulum yoktur.

- Tasarım ve gerekçeler: `docs/tasarim.md` — "neden böyle?" sorusunun cevabı orada.
- Saha denemesi adımları ve doğrulanmamış varsayımlar: `docs/saha-denemesi.md`.
- Durum: **0.4.0, saha denemesi sürümü.** Pardus 25 (XFCE) masaüstünde denendi
  (0.1.1: kurulum, kilit, duyuru, kapatma, güncelleme çalıştı); 0.2.0'ın okul kimliği,
  0.3.0'ın duyuru planları, hedef grupları ve acil durum/tatbikat yayını ve 0.4.0'ın ders
  programı/program kilidi yalnız Debian 12 kabında ve tarayıcıda denendi; gerçek bir ETAP
  tahtasında henüz denenmedi.
- Ders programı ve program kilidi `docs/tasarim.md` §12; yol haritası §13; kullanıcıya
  sorulacaklar §14 "Açık sorular"; doğrulanacak dayanaklar §15.

## Komutlar (PowerShell 5.1; `&&` yok)

```powershell
uv sync                                   # bağımlılıklar (.venv, Python 3.12)
uv run python -m tahta_sunucu             # sunucu: http://127.0.0.1:8787 · https://<ip>:8788
uv run python -m tahta_sunucu pencere     # denetim penceresiyle (kurulu programın yaptığı)
uv run python -m tahta_sunucu paket x.deb # ajan paketini dosyaya yaz
uv run pytest -q                          # testler
uv run ruff check .                       # biçim denetimi
powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1   # Windows kurucusu
```

Ortam değişkenleri: `TAHTA_VERI_DIZINI` (varsayılan `%LOCALAPPDATA%\TahtaKontrol`),
`TAHTA_HTTP_PORT` (8787, yalnız 127.0.0.1), `TAHTA_HTTPS_PORT` (8788, okul ağı).
Ajan: `TAHTA_AJAN_DIZIN`, `TAHTA_AJAN_DURUM`, `TAHTA_AJAN_BENZETIM=1` (kapatma komutu uygulanmaz).

## Yerleşim

```
tahta_sunucu/   FastAPI + SQLite + Jinja2 (HTMX yok, az miktar düz JavaScript)
  web.py        uygulama_olustur: oturum, pano, tahta, ayarlar, /marka/*, /ajan/* (uzun bekleme), MENU
  panel_duyuru.py   duyuru/plan uçları, /api/hedef-onizleme   (web.py'den `kaydet(uygulama, y)` ile)
  panel_tahtalar.py gruplar, /tahtalar.csv ve CSV içe aktarma
  panel_acil.py     /acil: başlatma, bitirme, rapor
  panel_program.py  /program (sekmeler: zil, derslik, kurallar, istisnalar), /program/uyarilar, /tahta/{id}/program
  sablonlar/    program.html, uyarilar.html ve ortak başları _program_bas.html (şerit + sekmeler)
  program.py    zil saatleri, Okul Zili okuma, takvim (plan_hesapla/gun_plani), derslik CSV, kilit aralıkları (saf)
  program_is.py program zamanlayıcısı (kilit, açma yedeği, boş ders uyarısı, bakım), istisnalar, özetler
  komut.py      KOMUT_OMRU, KOMUT_ADI, komut_ekle (duyuru komutu ömrü açıkça ister)
  duyuru.py     tek yayın yolu duyuru_yayimla, plan zamanlayıcısı, kaçırma kuralı, durdurma
  zamanlama.py  plan takvimi (saf işlevler; Europe/Istanbul)
  hedef.py      hedef şeması ve çözümü; tahta nitelikleri (bina, kat, düzey, devre, şube)
  acil.py       acil/tatbikat yayını (durum tabanlı), yedek yol, teslim kaydı
  metin.py      Türkçe metin, şube biçimi, CSV okuma/yazma (aşamalar arası ortak)
  tema.py       okul renklerinden bütün panel ve tahta tonları (OKLCH, kontrast eşikleri)
  marka.py      okul logosu: PNG/JPEG denetimi, ölçü okuma, saklama (veri_dizini/marka/logo)
  vt.py         şema ve göçler (GOCLER listesi, PRAGMA user_version; göç öncesi kopya veri_dizini/goc-oncesi)
  guvenlik.py   parola (scrypt), sunucu sertifikası ve parmak izi, kilit kodu özeti, tc_kimlik_var
  paket.py      ajan .deb paketini ve kurulum betiğini dış araç olmadan üretir
  sunucu.py     iki dinleyici: yerel HTTP + ağ için HTTPS; zamanlayıcı (state.zamanlayicilar, 20 sn)
  pencere.py    masaüstü denetim penceresi (tkinter)
  statik/       stil.css (tek dosya, katmanlı), panel.js (tek dosya, kütüphanesiz), isaret.svg (nötr ürün işareti)
  ajan_paket/   .deb'e giren dosyalar: control, postinst, prerm, servis, kur.sh
tahta_ajan/     YALNIZ standart kitaplık (ekran.py ayrıca PyGObject/GTK3)
  servis.py     yönetici yetkili sistem servisi: sunucu döngüsü, komutlar, acil durumu, süreli program kilidi, yerel soket
  ekran.py      oturumda çalışan kilit/duyuru/kapatma/acil penceresi (GTK3), üst bantta logo ve okul adı;
                program kilidinde "Teneffüs · Tahta 10:40'ta açılır." satırı (saat_eki sunucudakiyle aynı)
  ayar.py       yapılandırma, varsayılan tahta paleti, logonun servis tarafında saklanması
  sistem.py     işletim sistemine dokunan HER ŞEY (yeni platform = bu dosya)
  tani.py       saha tanılaması (denetim listesi)
packaging/windows/   PyInstaller tanımı, Inno Setup betiği, build.ps1
```

## Bağlayıcı kurallar

1. **Ajan standart kitaplık dışına çıkmaz.** Tahtada internet ve paket deposu
   varsayılmaz; `.deb` kendi kendine yeter (`Depends: python3`).
2. **Bağlantıyı hep tahta açar.** Sunucudan tahtaya bağlantı açan kod yazılmaz;
   komut `/ajan/bekle` uzun beklemesiyle iner.
3. **Sunucu arızası dersi rehin almaz.** Sunucuya `CEVRIMDISI_SN` (90 sn)
   ulaşılamazsa kilit tahtadan kodsuz açılır; ekran yardımcısı servisi 10 sn
   göremezse penceresini kapatır. Acil yayın da aynı tek düğmeyle (`cevrimdisi_ac`) yalnız
   sunucuya ulaşılamıyorken tahtadan kapatılır ve tahtada en çok 2 saat kalır.
   Bu davranışı "güvenlik açığı" diye kaldırma.
4. **Sunucu sertifikası yenilenmez.** Tahtalar parmak izine bağlıdır; sertifika
   değişirse bütün tahtalara ajan yeniden kurulur.
5. **Sır ekran yardımcısına gitmez.** Tahta anahtarı ve kilit kodu özeti yalnız
   yönetici yetkili serviste durur (`/etc/tahta-kontrol/ajan.json`, 0600).
6. **KVKK.** Tahta herkese açık ekrandır. Ajan sunucuya kullanıcı adı göndermez
   (yalnız hesap sınıfı: etapadmin/ogretmen/ogrenci/kişisel). Tanılama raporu ev
   dizini, dosya adı, kişisel hesap adı içermez. Gerçek okul verisi, tanılama
   dökümü, ekran görüntüsü depoya girmez (`saha/` gitignore'dadır).
7. **Sürüm dört yerde birlikte değişir:** `VERSION`, `tahta_ajan/__init__.py`,
   `tahta_sunucu/__init__.py` (`test_surumler_tutarli`) ve `pyproject.toml` (+ `uv lock`). Tahtalar güncellemeyi
   sürüm numarasından anlar: ajan kodu değiştiyse sürüm yükseltilir.
8. **Komut ömürleri bilinçlidir** (`komut.py::KOMUT_OMRU`): "kapat" 2 dakikada
   düşer; sonradan açılan tahta eskimiş komutla kapanmaz.
9. **Dil.** Arayüz, yorum, test adı, commit mesajı Türkçe; tanımlayıcılar ASCII
   Türkçe. `postinst`, `prerm`, `kur.sh` iletileri bilerek ASCII'dir (dash/UTF-8).
   `build.ps1` ve `.iss` UTF-8 BOM ile durur (PowerShell 5.1 BOM'suz dosyayı ANSI okur).
10. **Acil yayın komut değil durumdur** (`ayar.acil`, her `/ajan/bekle` yanıtında yeniden
   hesaplanır; komut tablosuna taşınmaz). Yalnız `acil` yeteneğini bildirmeyen eski ajana
   yedek `duyuru` komutu gider. Acil sürerken otomatik kapatma komut vermez; ajan da uyarılı
   `kapat`ı `(True, "...; uygulanmadı.")` ile atlar. Ajan anahtar hiç yoksa (eski sunucu)
   acil durumuna dokunmaz, `null` gelirse temizler; yetenekleri `durum.yetenekler` ile bildirir.
11. **Her duyuru gösterimi `duyuru.duyuru_yayimla` ile çıkar** (pano, plan, yeniden gönder,
   sonraki aşamalar `uygulama.state.duyuru_yayimla`). Göç `GOCLER`'in sonuna tek öğe eklenir.
12. **Program kilidi süreli ve kaynaklıdır.** Ajanda `kilit_kaynak` = `idare` (panel, süresiz)
   ya da `program` (süre tahtanın monotonik saatiyle sayılır, en çok 8 saat; sunucu kapalı olsa
   da süre dolunca açılır). Program kilidi idare kilidine uygulanmaz, program açması idare
   kilidini açmaz (`(True, "...; uygulanmadı.")`); idare kilidi program kilidini ezer. Program
   kilidi yeniden başlatmada **geri yüklenmez**. Tahta ekranında yalnız neden ve açılış saati
   yazar; şube, ders, öğretmen yazılmaz. Derslik programında öğretmen ve ders adı tutulmaz.
13. **Boş ders uyarısı personel verisi gibi korunur:** işlem kaydına yazılmaz (yalnız `#id`),
   dışa aktarılmaz, tahtada görünmez, 30 gün sonra `secure_delete` + WAL budamayla silinir.
   Panel metni "dersin işlenmediği anlamına gelmez" notunu taşır; arayüzde mevzuat atfı yoktur.

## Bilinen tuzaklar

- **Statik dosya adresleri sürüm taşır** (`/statik/stil.css?v=<sürüm>`, `panel.js?v=<sürüm>`)
  ve uzun önbellekle sunulur: `stil.css` ya da `panel.js` değişip sürüm yükseltilmezse
  tarayıcı eskisini tutmaya devam eder. Statik dosya değiştiyse sürüm yükseltilir (16.11.2026).
- **Panel menüsünün açılır grupları JS'siz `<details>`dır.** Dar ekranda menü yatay kayan
  kutudur ve mutlak konumlu açılır kutuyu kırpar; bu yüzden grup dar ekranda satır içi, geniş
  ekranda şeridin altına açılır (`stil.css`, `48rem`). `<form>` `<p>` içine konmaz (tarayıcı
  `<p>`yi kapatır, düğme satırı dağılır); düğme satırında `<div class="dugme-satiri">` kullanılır.
- **Acil sayfası da `yigin.show_all()`'dan önce eklenir** ve rengi pencereye eklenen stil
  sınıfından (`acil`/`tatbikat`) gelir; başka sayfaya geçince sınıf kaldırılır. Acil renkleri
  sabittir (`ekran.ACIL_RENKLERI`), okulun renginden türetilmez; yanıp sönme yoktur (16.11.2026).
- **Paket içi dosya zamanı içerikten türetilir** (`paket.py`): sabit zaman,
  güncellenen dosyanın eski `__pycache__` ile çalışmasına yol açtı (15.11.2026).
  `postinst` ayrıca önbelleği siler.
- **`Referrer-Policy: no-referrer` kullanma:** tarayıcı form gönderiminde
  `Origin: null` yollar, kaynak denetimi bütün POST'ları reddeder (15.11.2026).
- **GtkStack görünür olmayan sayfaya geçmez:** sayfalar pencere açılmadan
  `yigin.show_all()` ile görünür kılınır, pencere `show()` ile açılır (`show_all()` değil;
  o, gizlenmiş tuş takımını ve düğmeleri geri açar). Yoksa açılıştan sonraki ilk duyuru
  ya da kapatma uyarısı yerine bozuk bir kilit sayfası çıkar (16.11.2026).
- **Klavye kilidi pencere ekrana yerleşince alınır:** ilk deneme XFCE'de "not-viewable"
  ile düşer; kilit sürdükçe her saniye yeniden denenir (15.11.2026, Pardus 25 denemesi).
- **Otomatik kapatma** (`web.py::zamanlayici`, 20 sn'de bir; acil sürerken atlanır): yalnız o an çevrimiçi
  tahtalara, uyarılı (`uyari_sn`) komut verir; aynı gün-saat için bir kez (`kapatma_isaretleri`).
  Ajan, kilitli ya da ekransız tahtada uyarı göstermeden kapatır. Uzaktan açma
  (Wake-on-LAN) denenen bilgisayarda çalışmadı; düğme yalnız tahta sayfasında "deneysel" durur.
- **Panelde satır içi betik ve stil yok:** CSP `script-src 'self'; style-src 'self'`.
  Şablona `<style>`, `style=`, `onclick=` ya da çalışan `<script>` yazılmaz (yalnız
  `type="application/json"` veri blokları); test bunu denetler. Renkler `/marka/tema.css`'ten
  gelir, `stil.css`'teki varsayılan ham değerler `tema.varsayilan()` çıktısıyla aynı olmalı.
- **GTK'da `label` renk kuralı düğmenin içindeki etiketi de boyar:** düğme yazı rengi
  `button label` ve `#ana-dugme label` ile ayrıca verilir (`ekran.renk_stili`). Renkler ayrı
  bir CSS sağlayıcısındadır ve tema değişince aynı sağlayıcıya yeniden yüklenir.
- **Ajanın varsayılan paleti sunucuyla aynıdır:** `tahta_ajan/ayar.VARSAYILAN_PALET` =
  `tema.varsayilan()["tahta"]`; tema formülü değişirse ikisi birlikte değişir (test eder).
- **Logo ekran yardımcısına soketle gider:** dosya root'a aittir (0600); yardımcı okuyamaz.
  Logo bozuk ya da inmemişse ekran logosuz çalışır; bunu "hata" diye düşürme.
- **Eski ajana program komutu verilmez:** program kaynaklı `kilitle`/`kilit_ac` yalnız
  `durum.yetenekler` içinde `program_kilidi` bildiren tahtaya gider. 0.3.x ajanı `kilitle`'nin
  verisini yok sayıp süresiz kilitler, sonraki `kilit_ac` idarenin kilidini de açardı (16.11.2026).
- **Program kilidinin süresi komut tahtaya inerken hesaplanır** (`web.py`, `bitis_sunucu` →
  `sure_sn`; 30 sn'den azsa komut `iptal`). Panelde açılış saati `son_gorulme + kilit_kalan`
  dakikaya yuvarlanarak gösterilir (ajan kalan süreyi aşağı yuvarlar; 09:10 yerine 09:09 çıkıyordu).
- **Saatten sonra gelen ek** (`'ta/'da/'te/'de`) saatin okunuşundan seçilir: `program.saat_eki`
  ve `ekran.saat_eki` aynı tablodur (test bütün saatleri karşılaştırır). "10:40'da" yanlıştır.
- **`<details>` içindeki form alanları:** yeni tarayıcılarda içerik `::details-content` sözde
  öğesindedir ve `box-sizing` zincirini koparır; `stil.css` sıfırlama katmanında ayrıca
  `::details-content { box-sizing: inherit }` vardır. Yoksa açılır formlardaki alanlar kutudan taşar.
- **Sunucunun ajan paketi süreç başında bir kez üretilir:** ajan kodunu değiştirdikten sonra Docker
  denemesinde paketi yeniden indirmek için deneme sunucusu yeniden başlatılır.
- **Deneme sunucusunda giriş hız sınırı** (adres başına 5 dk'da 10): betik her adımda yeniden giriş
  yapmasın; oturum çerezini saklayıp yeniden kullansın.
- **Deneme betiklerinde saat:** Git Bash'te `TZ=Europe/Istanbul date` UTC verir; saati Python ile hesapla.
- **İlk kurulum yalnız 127.0.0.1'den yapılır;** ağdaki biri yönetici hesabını kapamasın.
- **Docker'da deneme:** `debian:12` + `python3-gi gir1.2-gtk-3.0 xvfb openbox imagemagick`;
  sunucuya `https://host.docker.internal:8788` ile ulaşılır; systemd yoktur, servis elle başlatılır.
  Git Bash'te `docker exec` için `MSYS_NO_PATHCONV=1` gerekir (curl için gerekmez, bozar).
