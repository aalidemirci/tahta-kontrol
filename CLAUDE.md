# CLAUDE.md — Tahta Kontrol

Okul ağında çalışan etkileşimli tahta kontrol ve duyuru sistemi. Bir bilgisayarda
**sunucu** (Windows hizmeti + durum penceresi), her tahtada **ajan** (Pardus ETAP, `.deb`).
İdare, paneli tarayıcıdan kullanıcı adıyla açar; diğer bilgisayarlara kurulum yoktur.

- Tasarım ve gerekçeler: `docs/tasarim.md` — "neden böyle?" sorusunun cevabı orada.
- Saha denemesi adımları ve doğrulanmamış varsayımlar: `docs/saha-denemesi.md`.
- Durum: **0.9.0, saha denemesi sürümü** (0.9.0: gerçek ETAP tahtasındaki ilk saha bulguları G1–G3 —
  kurulum ve otomatik giriş betikleri yönetici yetkisini kendileri alır (sudo → pkexec → su, öğretmen
  oturumunda etapadmin parolası sorulur), tahtada yüzer düğme (Kilitle/Kapat/Yeniden başlat/Arıza/
  Yoklama; Ayarlar › Tahtadaki yüzer düğme), açılışta kilit (oturum açılınca ya da tahta açılınca sunucuya
  ulaşılıyorsa kilitlenir, kararı sunucu verir; Ayarlar › Açılışta kilit); tasarım §5.1;
  0.8.0: 16.11.2026 kararları — ikili eğitim, öğretim yılı sonuna
  kadar saklama, acil yayını bütün idareciler başlatır, boş ders uyarısı varsayılan açık + rapor, gün sonu
  oturum temizliği (K7, varsayılan kapalı; yalnız Debian 12 kabında denendi), sunucu Windows
  hizmeti (K8; birim testleri ve uçbirimde hizmet kipi, gerçek hizmet kurulumu denenmedi); 0.7.1:
  tahta ekranı ekran boyutuna orantılı). Pardus 25 (XFCE) masaüstünde denendi
  (0.1.1: kurulum, kilit, duyuru, kapatma, güncelleme çalıştı); 0.2.0'ın okul kimliği,
  0.3.0'ın duyuru planları, hedef grupları ve acil durum/tatbikat yayını, 0.4.0'ın ders
  programı/program kilidi, 0.5.0'ın sınav kipi/sınav yoklaması, 0.6.0'ın ders yoklaması ve
  0.7.0'ın altyapı çekirdeği (şifreli yedek, sunucu adres listesi, envanter, arıza bildirimi)
  yalnız Debian 12 kabında ve tarayıcıda denendi; gerçek bir ETAP tahtasında, gerçek Kelebek
  çizelgesiyle ve gerçek e-Okul sınıf listesiyle henüz denenmedi. Ajan paketi imzası yapılmadı.
- Ders programı ve program kilidi `docs/tasarim.md` §12; sınav kipi §13; ders yoklaması §14;
  altyapı (yedek, adres listesi, envanter, arıza) §15, Windows hizmeti §15.6; yol haritası §16; okul idaresinin kesin
  kararları (K1–K8, 16.11.2026) ve kullanıcıya sorulacaklar §17; doğrulanacak dayanaklar §18.
  Kararlar yeniden tartışılmaz; bir kararla çelişen öneri yapılmaz.

## Komutlar (PowerShell 5.1; `&&` yok)

```powershell
uv sync                                   # bağımlılıklar (.venv, Python 3.12)
uv run python -m tahta_sunucu             # sunucu: http://127.0.0.1:8787 · https://<ip>:8788
uv run python -m tahta_sunucu pencere     # durum penceresi (hizmet yoksa sunucuyu pencerede çalıştırır)
uv run python -m tahta_sunucu paket x.deb # ajan paketini dosyaya yaz
uv run python -m tahta_sunucu hizmet --konsol   # hizmet kipini uçbirimde dene (Ctrl+C); hizmet KURMAZ
uv run python -m tahta_sunucu tasi --hedef D --kaynak K   # eski veriyi kopyala (kurucunun yaptığı)
uv run pytest -q                          # testler
uv run ruff check .                       # biçim denetimi
powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1   # Windows kurucusu
```

Ortam değişkenleri: `TAHTA_VERI_DIZINI` (varsayılan: geliştirmede `%LOCALAPPDATA%\TahtaKontrol`,
kurulu programda/hizmette `%PROGRAMDATA%\TahtaKontrol`; `ayar.veri_dizini_sec`), `TAHTA_HIZMET=1`
(hizmet kipi; giriş noktası ayarlar),
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
  program.py    zil saatleri, Okul Zili okuma, takvim (plan_hesapla/gun_plani), derslik CSV, kilit aralıkları (saf);
                ikili eğitim: devre_turleri (sabah/öğle eşlemesi), tahta_devreleri (programdan devre)
  dugme.py      tahtadaki yüzer düğme (0.9.0): ayar.tahta_dugmesi → ajana ayar.dugme {acik, islemler}
  acilis_kilidi.py  açılışta kilit (0.9.0): yeni durum.oturum_no + oturum_yasi_sn ≤ 120 → bir kez "kilitle"
                (program kilidinin yönettiği tahtada ders dışı saatte süreli program kilidi, derste kilit yok)
  temizlik.py   oturum temizliği (K7): ayar.oturum_temizligi (varsayılan kapalı), gün sonu anları
                (kapatma öncesi / son devrenin sonu / saat), zamanlayıcı (okul geneli işaret program_isaret
                tahta 0), tahta sayfası özeti; elle uç web.py /tahta/{id}/temizlik
  saklama.py    öğretim yılı bitiş tarihi (ayar.ogretim_yili_bitis): imha_siniri, Ayarlar durumu, arayüz notu
  program_is.py program zamanlayıcısı (kilit, açma yedeği, boş ders uyarısı, bakım), istisnalar, özetler,
                bos_ders_raporu (Uyarılar sekmesi: tarih aralığı, tahta, ders saati; kişi adı yok)
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
  wol.py        uzaktan açma (Wake-on-LAN) sihirli paketi; birkaç yayın adresine gönderir ("deneysel")
  paket.py      ajan .deb paketini ve kurulum betiğini dış araç olmadan üretir
  sunucu.py     iki dinleyici: yerel HTTP + ağ için HTTPS; zamanlayıcı (state.zamanlayicilar, 20 sn)
  pencere.py    durum penceresi (tkinter): /yerel/durum + `sc query` ile kip seçer; kurulu programda
                sunucu AÇMAZ (hizmetin durumunu gösterir, "Hizmeti başlat" UAC ister); geliştirmede eskisi gibi
  hizmet.py     Windows hizmeti kabuğu: saf `govde()` + pywin32 sınıfı (yalnız hizmet çalışırken içe aktarılır),
                gunluk\sunucu.log (5 MB × 3), geri yüklemede 75 koduyla çıkış (`yeniden_baslat_planla`)
  tasima.py     0.8 öncesi veriyi (%LOCALAPPDATA%) %PROGRAMDATA%'ya KOPYALAR (kurucu çağırır; çıkış kodları
                0/10/11/20/21); belirsizlik/hatada TASIMA-BEKLIYOR.txt → hizmet açılmaz
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
                yoklama sayfaları: yoklama-pin, yoklama-liste, yoklama-onay, yoklama-ileti; kilitte "Yoklama al";
                ölçüler 1920x1080 için yazılır, ekran_olcegi() ile pencerenin monitörüne orantılanır (0.7.1)
scripts/ekran_olcum.py  Docker/Xvfb'de her tahta sayfasının ekrana sığıp sığmadığını ölçer (uydurma veri)
  __main__.py   komut satırı; `tahta-ajan yoklama` ("Yoklama Al" kısayolu) servise yoklama_ac yollar;
                `tahta-ajan ariza` (pencere), `tahta-ajan sunucu ADRES` (parmak izi tutarsa yazar)
  ayar.py       yapılandırma, varsayılan tahta paleti, logonun servis tarafında saklanması, adres doğrulama/sırası
  baglanti.py   sunucu istemcisi (Istemci): HTTPS, sertifika zinciri yerine parmak izi denetimi (tutmazsa tek bayt gitmez)
  sistem.py     işletim sistemine dokunan HER ŞEY (yeni platform = bu dosya); ortak_oturum, temizlik
                sürecini oturum sahibinin kimliğiyle başlatma (tarayici_temizligi, pencereleri_kapat)
  temizlik.py   oturum temizliğinin işletim sistemi işleri (ikinci dosya; ayrı süreçte çalışır,
                `python3 -m tahta_ajan.temizlik tarayici|pencereler`): beyaz liste, yol/bağ koruması,
                tarayıcı süreçleri, X11 _NET_CLOSE_WINDOW (ctypes libX11), ad içermeyen rapor
  tani.py       saha tanılaması (denetim listesi)
packaging/windows/   PyInstaller tanımı, Inno Setup betiği (hizmet kaydı, taşıma, icacls), build.ps1, giris.py
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
13. **Boş ders uyarısı personel verisi gibi korunur:** varsayılan açıktır ve geçmişiyle raporlanır
   (K6) ama işlem kaydına içeriği yazılmaz (yalnız `#id`; rapor görüntülemesi yalnız tarih aralığı ve
   süzgecin varlığıyla), dışa aktarılmaz (yalnız yazdırılır), raporda kişi adı yoktur, tahtada görünmez,
   öğretim yılı sonunda `secure_delete` + WAL budamayla silinir (kural 24). Panel metni "dersin
   işlenmediği anlamına gelmez" notunu taşır; arayüzde mevzuat atfı yoktur.
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
   işlem kaydına ad, maske, okul no yazılmaz. Kişisel veri öğretim yılı sonunda (kural 24)
   `secure_delete` + WAL budamayla silinir. Okul no yalnız panelde salon yoklaması ve icmal sayfalarındadır.
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
24. **Öğrenci verisi içeren kayıtlar öğretim yılı sonuna kadar saklanır** (K3; `saklama.py`). Ders
   yoklaması, sınav listesi/yoklaması ve boş ders uyarısı, yöneticinin Ayarlar'da girdiği
   `ogretim_yili_bitis` geçince (ertesi gün) o tarihe kadar oluşanlarıyla kalıcı silinir; tarih boşsa
   hiçbir şey silinmez ve Ayarlar uyarır. Gün sayılı saklama sabiti ya da ayarı geri getirilmez; tarih
   kendiliğinden (Okul Zili'nden ya da göçle) yazılmaz, yalnız önerilir. Tahtadan alınan ders ve sınav
   yoklaması kâğıdın yanında yardımcı kayıttır (K5); arayüz resmî kayıt iddiasında bulunmaz.
25. **İkili eğitim (K1):** ders saati, derslik programı, boş ders uyarısı ve yoklama önerisi devreyle
   (`ders_saati.devre`) anahtarlanır; ders numarası devre başınadır (sabahın 3. dersi ≠ öğlenin 3.
   dersi). Tek devreli okulda devre adı hiçbir yerde gösterilmez ve davranış değişmez.
26. **Acil yayını bütün yönetici ve idareciler başlatır** (K4; `acil.yetkili`, rolden). `kullanici.acil_yetki`
   okunmaz; yalnız eski sürüme dönüş için 1 yazılır. Parola ve onay kutusu kaldırılmaz.
27. **Oturum temizliği hafiftir ve yalnız ortak hesaptadır** (K7; `docs/tasarim.md` §12.1). Yalnız
   `ogretmen`/`ogrenci` (`temizlik.TEMIZLENEBILIR_HESAPLAR`; sunucu daraltır, genişletemez); `etapadmin`
   ve kişisel hesap ASLA. Silinen yalnız beyaz listedeki çerez ve oturum dosyalarıdır; geçmiş, yer
   imleri, kayıtlı parola, form verisi, Local Storage/IndexedDB ve ev dizinindeki dosyalar listeye
   EKLENMEZ. Tarayıcı adımı root'ta değil, oturum sahibinin kimliğiyle ayrı süreçte çalışır; yol her
   adımda `lstat` ile izlenir, sembolik bağ izlenmez. Rapor yalnız sayıdır (ad, yol, başlık yok).
   Kullanılan tahtada 60 sn uyarı + Vazgeç; komut ömrü 2 dk, kaçan temizlik sonradan yapılmaz.
   Ajan komutun sonucunu ertelenmiş verir (`komut_uygula` → None; sonuç `sonuclar`a sonra eklenir).

28. **Sunucu Windows hizmetidir; veri ProgramData'dadır** (K8; `docs/tasarim.md` §15.6). Hesap Yerel
   Hizmet (SYSTEM'e çevrilmez). Kurulu pencere sunucu açmaz; başlangıç kısayolu geri getirilmez. Eski
   veri yalnız KOPYALANIR (kaynak silinmez); hedefte veri varsa taşınmaz; seçim belirsizse ya da kopya
   bozuksa `TASIMA-BEKLIYOR.txt` yazılır ve hizmet açılmaz — bu korumayı "kolaylık" için kaldırma
   (yeni sertifika = bütün tahtalar kopar, kural 4). Taşıma kodları `.iss` ile `tasima.py`'de aynıdır
   (`test_kurucu_tasima_kodlari_python_ile_ayni`). `hizmet.py` modül düzeyinde pywin32 içe aktarmaz.

## Bilinen tuzaklar

- **GtkButton.set_label etiketi yeniden kurar:** ortalama (`set_justify`) ve kısaltma kaybolur;
  yoklama düğmesinin metni değişince `ekran._ogrenci_etiketi` ile yeniden verilir (16.11.2026, Docker).
- **Zombi süreç /proc'ta yaşar görünür:** `/proc/<pid>/status` hâlâ Name ve Uid verir; tarayıcı
  süreci sayılırken `State: Z` atlanmazsa kapanmış tarayıcı "kapanmadı" sayılır ve verisi temizlenmez
  (16.11.2026, Docker oturum temizliği denemesi).
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
- **GtkStack en büyük sayfasına göre boyutlanır; sabit piksel ölçü verme** (16.11.2026, 0.7.0 kusuru):
  gözetmen kodu/yoklama PIN'i sayfasındaki 640/720 px sütun ve 150 px tuşlar pencereyi 1427 px'e
  zorladı; 1280x800 ve 1366x768 ekranda kilit ve duyuru da sağa kaydı, tahta adı kesildi. Artık yığın
  homojen değildir ve bütün pikseller (CSS dahil) `ekran.py`'de `_olcu/_kutu/_izgara/_kenar/_ekle/_dugme`
  ile 1920x1080 değeriyle verilip `ekran_olcegi()` ile ölçeklenir (`test_ekran_kodunda_sabit_piksel_yok`).
  Ekran sayfası değişince dar ekranda dene: `scripts/ekran_olcum.py`'yi Xvfb'de 1024x768, 1366x768,
  1920x1080 ve 3840x2160'ta çalıştır; "TAŞTI" kalmamalı.
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
- **Bu geliştirme bilgisayarında hizmet KURULMAZ:** `hizmet --konsol` hizmet yöneticisi olmadan aynı
  gövdeyi çalıştırır (ayrı `TAHTA_VERI_DIZINI`, 8797/8798). `python -m tahta_sunucu hizmet` elle
  çalıştırılınca 2 koduyla çıkar (1063); bu beklenen davranıştır.
- **`pencere` geliştirmede 8787'de sunucu açar:** kurulu sunucu bu bilgisayarda çalışıyorsa önce
  ona bağlanır; denemede `TAHTA_HTTP_PORT`/`TAHTA_HTTPS_PORT`'u değiştirmeden çalıştırma.
- **`sudo` çağıran hesabın KENDİ parolasını sorar:** `ogretmen` sudo yetkili değildir; öğretmen
  oturumunda `sudo bash tahta-kur.sh` öğretmen parolasını sorup reddeder (G1, 16.11.2026, gerçek ETAP).
  `kur.sh` ve `araclar/otomatik-giris.sh` yetkiyi kendileri alır: root → sudo (yetkiliyse) → pkexec
  (grafik oturum; polkit etapadmin'i sorar) → `su etapadmin` + sudo → "etapadmin oturumunda yapın".
  Yönergeye `sudo` yazılmaz.
- **`su -c` komutu yeni oturumda (denetim uçbirimi olmadan) çalıştırır:** içindeki `sudo` parola
  soramaz ("a terminal is required"); `su --pty` kullanılır, `--pty` yoksa `sudo -S` (Docker'da
  doğrulandı, 16.11.2026). Kapta polkit kimlik doğrulaması "No session for cookie" ile düşer (logind
  oturumu yok); pkexec yolu yalnız gerçek masaüstünde sınanır.
- **Ölü uzun bekleme komut çalar:** ajan yeniden başlayınca eski bağlantının `/ajan/bekle`'si sunucuda
  25 sn'ye kadar açık kalır; süresi dolunca bekleyen komutu alıp ölü sokete yollardı (açılışta kilit
  Docker'da hiç inmedi, 16.11.2026). `bekleyenler`'de yerini yenisi alan bekleme komut almaz.
- **Açılışta kilidin oturum yaşı süreç başlangıcından gelir** (`/proc/self/stat`, `execv`'de korunur):
  güncellemede kendini yeniden başlatan yardımcı yeni oturum sayılmaz. Docker kapları çekirdeği
  paylaştığı için `boot_id` ve açılış sayacı kapta "yeniden başlatma" ile değişmez.
- **Deneme betiklerinde saat:** Git Bash'te `TZ=Europe/Istanbul date` UTC verir; saati Python ile hesapla.
- **İlk kurulum yalnız 127.0.0.1'den yapılır;** ağdaki biri yönetici hesabını kapamasın.
- **Docker'da deneme:** `debian:12` + `python3-gi gir1.2-gtk-3.0 xvfb openbox imagemagick`;
  sunucuya `https://host.docker.internal:8788` ile ulaşılır; systemd yoktur, servis elle başlatılır.
  Git Bash'te `docker exec` için `MSYS_NO_PATHCONV=1` gerekir (curl için gerekmez, bozar).
