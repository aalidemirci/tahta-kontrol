# CLAUDE.md — Tahta Kontrol

Okul ağında çalışan etkileşimli tahta kontrol ve duyuru sistemi. Bir bilgisayarda
**sunucu** (Windows masaüstü programı), her tahtada **ajan** (Pardus ETAP, `.deb`).
İdare, paneli tarayıcıdan kullanıcı adıyla açar; diğer bilgisayarlara kurulum yoktur.

- Tasarım ve gerekçeler: `docs/tasarim.md` — "neden böyle?" sorusunun cevabı orada.
- Saha denemesi adımları ve doğrulanmamış varsayımlar: `docs/saha-denemesi.md`.
- Durum: **0.7.0, saha denemesi sürümü.** Pardus 25 (XFCE) masaüstünde denendi
  (0.1.1: kurulum, kilit, duyuru, kapatma, güncelleme çalıştı); 0.2.0'ın okul kimliği,
  0.3.0'ın duyuru planları, hedef grupları ve acil durum/tatbikat yayını, 0.4.0'ın ders
  programı/program kilidi, 0.5.0'ın sınav kipi/sınav yoklaması, 0.6.0'ın ders yoklaması ve
  0.7.0'ın altyapı çekirdeği (şifreli yedek, sunucu adres listesi, envanter, arıza bildirimi)
  yalnız Debian 12 kabında ve tarayıcıda denendi; gerçek bir ETAP tahtasında, gerçek Kelebek
  çizelgesiyle ve gerçek e-Okul sınıf listesiyle henüz denenmedi. Windows hizmeti ve ajan paketi
  imzası (Aşama 6B) yapılmadı.
- Ders programı ve program kilidi `docs/tasarim.md` §12; sınav kipi §13; ders yoklaması §14;
  altyapı (yedek, adres listesi, envanter, arıza) §15; yol haritası §16; kullanıcıya sorulacaklar
  §17 "Açık sorular"; doğrulanacak dayanaklar §18.

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
  panel_sinav.py    /sinavlar, /sinav/{id} (künye, eşleştirme, durum, uzatma, kip kaldırma, kodlar, şube
                    duyurusu, salon yoklaması, icmal), /api/sinav/{id}, /ajan/sinav/{kod,yoklama}
  panel_yoklama.py  /yoklama (günlük ızgara, kayıt/düzeltme, panelden gir, icmal + .csv, e-Okul işareti),
                    /ogretmenler (PIN pusulası), /ogrenciler (önizle/aktar/temizle), /ajan/yoklama/*;
                    sonunda şablon bağlamlarının SÖZLEŞME bloğu
  panel_altyapi.py  /yedekler (parola, ayar, al, indir, geri-yukle + onay/uygula), /envanter (+ .csv),
                    /tahta/{id}/envanter, /tahta/{id}/donanim-goruldu, /arizalar, /ariza/{id}, /yerel/durum
  yedek.py      şifreli yedek .tkyedek (scrypt → X25519 → HKDF → AES-GCM), saklama, ikinci kopya, geri yükleme
                (denetle → onay → açılışta bekleyeni_uygula); yedek.KILIT = vt.KILIT (göç ve yedek aynı kilitte)
  adresler.py   sunucu adres listesi (en çok 5): doğrulama, özet (ajanla aynı), eski sunucu_adresi geçişi
  envanter.py   ajanın gönderdiği envanteri saklar/gösterir, donanım kimliği değişimi, CSV
  ariza.py      arıza kayıtları: kategoriler, durum geçişleri, hareketler, tahtadan alma (yerel_id tekrarsız)
  sablonlar/    program.html, uyarilar.html ve ortak başları _program_bas.html (şerit + sekmeler);
                sinavlar.html, sinav.html, sinav_yoklama.html, sinav_kodlar.html, sinav_icmal.html, _sinav.html;
                yoklama*.html, ogretmenler.html, ogretmen_pusula.html, ogrenciler.html, ogrenci_onizleme.html
                ve ortak başları _yoklama_bas.html (sekmeler + KVKK notu);
                yedekler.html, yedek_onay.html, yedek_geri_yukle.html, envanter.html, arizalar.html,
                ariza.html, _ariza.html (durum rozeti + açma formu makroları), _tahta_altyapi.html
  yoklama.py    ders yoklaması iş mantığı (FastAPI'siz): ayar, A3 uyarlama işlevleri, öneri, PIN kapısı
                (3 katman), belirteç, yoklama_yaz (upsert + iz), günlük görünüm, icmal/metin/CSV, aktarım, imha
  eokul.py      öğrenci listesi ayrıştırıcı: e-Okul OOG01001R020 .xls (xlrd), düz .xlsx/.csv
  sinav.py      sınav iş mantığı: R5 ayrıştırma, içe aktarma, eşleşme önerisi, süreler/evreler, ayar.sinav,
                gözetmen kapısı (bellekte), yoklama, şube duyurusu, icmal, saklama temizliği
  xlsx.py       yalnız standart kitaplıkla .xlsx okuyucu (zip/DOCTYPE sınırları; A5 de kullanır)
  maske.py      tek maskeleme tanımı: kalabalik("Ah*** Yı****"), no_son("47"), sinif_etiketi("Ayşe Y.")
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
  ajan_paket/   .deb'e giren dosyalar: control, postinst, prerm, servis, kur.sh, tahta-yoklama.desktop,
                tahta-ariza.desktop
tahta_ajan/     YALNIZ standart kitaplık (ekran.py ayrıca PyGObject/GTK3)
  servis.py     yönetici yetkili sistem servisi: sunucu döngüsü, komutlar, acil durumu, süreli program kilidi,
                sınav durumu (ayar.sinav, monotonik sayaç) ve gözetmen oturumu (belirteç yalnız burada),
                ders yoklaması (ayar.yoklama_etkin, self.yoklama; belirteç yalnız _yoklama_belirtec'te), yerel soket
                (ilk satır `arayuz: komut` ise kısa ömürlü istemci: ona yayın yok, ekran sayılmaz);
                A6: adres listesi (_istemci_kur/_adres_hatasi/_adres_basarili), envanter (donanim_tazele,
                envanter_iste), arıza kuyruğu (ariza_bildir, durum.json `ariza_kuyrugu`); döngünün bir turu _tur()
  envanter.py   envanteri §5.4 biçiminde kurar (seri yer tutucuları boşaltılır), özet
  ariza_penceresi.py  "Arıza bildir" penceresi (GTK3, ayrı süreç; kullanıcı yetkisiyle); gonder() servise
                `merhaba arayuz=komut` + `ariza` yollar, `ariza_sonuc` bekler
  ekran.py      oturumda çalışan kilit/duyuru/kapatma/acil penceresi (GTK3), üst bantta logo ve okul adı;
                program kilidinde "Teneffüs · Tahta 10:40'ta açılır." satırı (saat_eki sunucudakiyle aynı);
                sınav sayfaları: sinav-giris, sinav, gozetmen-kod, gozetmen-menu, gozetmen-yoklama;
                yoklama sayfaları: yoklama-pin, yoklama-liste, yoklama-onay, yoklama-ileti; kilitte "Yoklama al"
  __main__.py   komut satırı; `tahta-ajan yoklama` ("Yoklama Al" kısayolu) servise yoklama_ac yollar;
                `tahta-ajan ariza` (pencere), `tahta-ajan sunucu ADRES` (parmak izi tutarsa yazar)
  ayar.py       yapılandırma, varsayılan tahta paleti, logonun servis tarafında saklanması, adres doğrulama/sırası
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
14. **Sınav kipi durumdur, komut değil** (`ayar.sinav`, her `/ajan/bekle` yanıtında
   `sinav.tahta_sinavi` ile yeniden hesaplanır; pencere dışında `null`). Ajan kalan süreleri
   monotonik saatle sayar; sunucuya ulaşılamasa da sınav ekranı süresinde kalkar ve 90 sn sonra
   `cevrimdisi_ac` onu da kapatır (kural 3; sunucu dönünce sınav sürüyorsa geri gelir).
15. **Sınav ekranında ortak kilit kodu kabul edilmez** ve uyarılı `kapat` uygulanmaz
   (`"Sınav sürüyor; otomatik kapatma uygulanmadı."`). Panelden kilit açma sınav ekranını
   kaldırmaz; kip yalnız panelden ("Sınav kipini kaldır", "Sınavı bitir") ya da süreyle kalkar.
16. **Sınav listesi ajanda diske yazılmaz:** liste, gözetmen belirteci ve kod `durum.json`'a,
   günlüğe, tanılama raporuna girmez; liste sınav başlayınca bellekten de silinir. Gözetmen
   belirteci ekran yardımcısına gitmez; gözetmen kodu yalnız sunucuda doğrulanır.
17. **Sınavda ad soyad saklanmaz** (yalnız `maske.kalabalik`); tahtaya tam okul no ve ders gitmez;
   işlem kaydına ad, maske, okul no yazılmaz. Kişisel veri 30 gün sonra `secure_delete` + WAL
   budamayla silinir. Okul no yalnız panelde salon yoklaması ve icmal sayfalarındadır.
18. **Öğrenci listesi tahtada diske yazılmaz; yoklama belirteci ekran yardımcısına gitmez.**
   Liste, işaretler ve belirteç yalnız servisin belleğindedir (`durum.json`, günlük, tanılama
   raporu yok); kaydedilince ya da süre dolunca bellekten de atılır. Sunucuya giden durumda yalnız
   `yoklama_acik` bayrağı olur. Tahtada öğrenci ancak maskeli etiketle (`maske.sinif_etiketi`)
   görünür; ad ve okul no hiçbir zaman ikisi birden açık değildir (`tam` maskesi yoktur).
19. **PIN düz metni yalnız pusula yanıtında görünür** (POST, `no-store`, yönlendirme yok); sunucuda
   scrypt özeti, tahtaya ne PIN ne özeti gider. İşlem kaydına öğretmen için yalnız kod, öğrenci için
   yalnız sayı yazılır; düzeltme gerekçesi ve öğrenci kimlikli iz `yoklama_iz`'dedir ve imhayla gider.
20. **Kısa ömürlü yerel istemci kendini tanıtır:** yerel sokete bağlanan komut istemcisi ilk satırda
   `{"tur":"merhaba","arayuz":"komut"}` yollar; servis ona durum yayını göndermez, `durum_ozeti`
   ekranlarına ve "ekran bağlı" sayımına katmaz. Ekran yardımcısı da bağlanır bağlanmaz `merhaba` yollar
   (servis ilk satırı 3 sn bekler; gelmezse eski davranışla ekran sayar).

21. **Yedek parolası sunucuda saklanmaz;** yalnız X25519 açık anahtarı (`ayar.yedek`) durur. Parola
   belirlenmeden otomatik yedek alınmaz (pano uyarır). Geri yükleme yalnız 127.0.0.1'den ve yöneticiyle
   (ilk kurulumda oturumsuz, yine yalnız yerelden); önce denetlenir, onaylanınca program yeniden
   açılırken uygulanır, eski dosyalar `geri-yukleme-oncesi/`'ne taşınır. KVKK: elle yedekler de saklama
   gününden eskiyince, onaysız bekleyen geri yükleme 24 saatte, geri yükleme öncesi kopya (yalnız en
   yenisi) saklama gününde silinir. `*.tkyedek` depoya girmez.
22. **Sunucu adres listesi durumdur** (`ayar.sunucu_adresleri`, boşsa hiç gönderilmez; ajan boş ya da
   eksik listeyle kendi listesini silmez). Adres root yetkili kur.sh'e yazıldığı için ana makine adı
   yalnız geçerli IP ya da `[a-z0-9.-]` DNS adı olabilir (sunucu `adresler.dogrula_tek`, ajan
   `ayar.adres_dogrula`; `paket.kurulum_betigi` ayrıca denetler). Ajan bir adrese art arda 3 BAĞLANTI hatasında (parmak izi
   dahil; HTTP 401/403/5xx değil) sıradakine geçer, ulaştığı adresi `ajan.json`'da birincil yapar.
   Parmak izi her adreste denetlendiği için yanlış adrese veri gitmez. Tarama/yayınla keşif yoktur.
23. **Envanter cihaz verisidir; arıza metni tahtada gösterilmez.** Envanter yalnız sunucu `envanter_iste`
   deyince (ya da `envanter` komutunda) gider; hesap adı, ev dizini, makine adı, açık kalma süresi girmez.
   Tahtadan arıza yalnız hesap SINIFIYLA gelir; açıklama 300 karakter, T.C. no içeriyorsa sunucu metni
   kaydetmez. Arıza kuyruğu tahtada en çok 10 öğe / 7 gün, saatte 3 bildirim. Arıza kaydı silinmez.

## Bilinen tuzaklar

- **GtkButton.set_label etiketi yeniden kurar:** ortalama (`set_justify`) ve kısaltma kaybolur;
  yoklama düğmesinin metni değişince `ekran._ogrenci_etiketi` ile yeniden verilir (16.11.2026, Docker).
- **Kapta `pkill -f "tahta-ajan ekran"`, aynı metni taşıyan `sh -c` komutunu da öldürür;**
  deneme betiklerini dosyaya yazıp `sh dosya` ile çalıştırın (16.11.2026).

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
- **Sınav ve gözetmen sayfaları da `yigin.show_all()`'dan önce eklenir;** sonradan içi doldurulan
  liste ve koltuk ızgarasında yalnız o kapsayıcının `show_all()`'ı çağrılır (pencereninki değil).
  Koltuk ızgarası gözetmen oturumu değişince (`oturum` numarası) yeniden kurulur; ara `durum`
  iletileri işaretleri silmesin diye her çizimde yeniden kurulmaz (16.11.2026).
- **Kip kaldırılan salonun tahtası çakışma sayılmaz** (`sinav.cakisan_sinav`); yoksa kipi kaldırılan
  tahta aynı saatteki başka sınava eşlenemezdi (16.11.2026).
- **Docker'da ekran yardımcısını yeniden başlatırken** eski süreç (`python3 -m tahta_ajan ekran`)
  ayrıca öldürülür; iki yardımcı üst üste pencere açar, tıklamalar eskisine gider (16.11.2026).
- **Sunucunun ajan paketi süreç başında bir kez üretilir:** ajan kodunu değiştirdikten sonra Docker
  denemesinde paketi yeniden indirmek için deneme sunucusu yeniden başlatılır.
- **Deneme sunucusunda giriş hız sınırı** (adres başına 5 dk'da 10): betik her adımda yeniden giriş
  yapmasın; oturum çerezini saklayıp yeniden kullansın.
- **Arıza penceresinin "iletildi" iletisi sunucunun `ariza_alindi` yanıtına bağlıdır** (servis en çok
  5 sn bekler); gelmezse "tahtada bekletiliyor" der ve kayıt kuyrukta kalır. Docker'da ilk bağlantı
  uzun bekleme (25 sn) sürdüğü için adres listesi ve onay ancak bir tur sonra iner (16.11.2026).
- **Ajan döngüsü `_tur()` olarak ayrıldı:** testler ağı sahte `Istemci` ile verip turları tek tek
  çalıştırır (`tests/test_ajan_altyapi.py`); `_dongu` yalnız bekleme ekler.
- **Şablon makro bağımsız değişkeninin adı `on…` ile başlamaz** (`onek=` gibi): CSP testi
  ` on[a-z]+=` desenini satır içi olay işleyicisi sayar (16.11.2026).
- **Deneme betiklerinde saat:** Git Bash'te `TZ=Europe/Istanbul date` UTC verir; saati Python ile hesapla.
- **İlk kurulum yalnız 127.0.0.1'den yapılır;** ağdaki biri yönetici hesabını kapamasın.
- **Docker'da deneme:** `debian:12` + `python3-gi gir1.2-gtk-3.0 xvfb openbox imagemagick`;
  sunucuya `https://host.docker.internal:8788` ile ulaşılır; systemd yoktur, servis elle başlatılır.
  Git Bash'te `docker exec` için `MSYS_NO_PATHCONV=1` gerekir (curl için gerekmez, bozar).
