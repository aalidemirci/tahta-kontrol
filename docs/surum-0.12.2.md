# 0.12.2 — ETAP yüzer düğme geliştirme düzeltmesi

Bulgu: evde Pardus XFCE'de çalışan yüzer düğme ETAP'ta silik görünüyor,
tıklanamıyor; kullanıcı görev çubuğunun da kilitlendiğini bildirdi.
Kesin ETAP sürümü ve gerçek cihazda olay kaydı henüz yok.

## Düzeltme

- Düğme ve menü, override-redirect POPUP yerine çerçevesiz, odak almayan,
  görev çubuğunda görünmeyen TOPLEVEL/UTILITY pencereler kullanır.
- Menü masaüstünün fare/dokunma girdisini `Gdk.Seat.grab` ile topluca almaz.
  Dışarı dokunmayı yakalamak yerine açık "Menüyü kapat" düğmesi ve zaman aşımı vardır.
- Dokunma dizileri doğrudan ele alınır: tek dokunuş, sürükleme, iptal ve ikinci
  parmak ayrılır. Fareyle tıklama da korunur.
- Menüye gelen alt GdkWindow olayı dışarı dokunma sanılıp menüyü basma anında
  kapatmaz; değişmeyen durum iletisi menü düğmelerini yeniden oluşturmaz.
- Soluk görünüm görsel davranıştır, düğme devre dışı bırakılmaz.

Bu riskler kaynakta doğrulandı; ETAP sorununun bütünüyle giderildiği gerçek
cihaz denemesi yapılmadan söylenemez. Kilit/acil tam ekranının giriş politikası
ve çevrimdışı açılma davranışı değiştirilmedi.

## Doğrulama ve çıktı

- Yüzer GTK olay taklidi, mevcut ajan düğme ve paket gizliliği: 43 başarılı test.
- İndirme, yedek işleyici, ekran ölçeği ve sürüm tutarlılığı: 80 başarılı test.
- Ruff ve `git diff --check` temiz. `uv lock --offline` güncellendi.
- Yeni ajan: `dist/tahta-ajan-0.12.2.deb` (115924 bayt).
  SHA-256: `dfa420352fde0dfc2e50741fd171ba34b1f7aa1e569ce5c28bdaa11231c57a84`.
- Bu sürümde tam test takımı veya gerçek GTK/ETAP ekranı çalıştırılmadı.
  Daha önceki 0.12.1 tam test sonucu bu sürümün tam doğrulaması değildir.
- Kurulu sunucu, bağlı istemci, yerel öğrenci verisi ve GitHub görünürlüğü değişmedi.
  Windows klasör paketi önceki 0.12.1 derlemesidir; 0.12.2 için yeniden üretilmedi.

## Tek tahtada kabul

Bakım zamanında ajan paketi yönetici hesabıyla güncellenmeli; çalışan ekran
yardımcısının da yeni kodu yüklemesi için oturum kapatılıp açılmalı. Bu işlem
tahtada yapılır, bu bilgisayardaki kaynak dosyasını değiştirmek tahtayı güncellemez.

1. Fare ve dokunmayla silik düğmeye basın; tek menü açılmalı.
2. Menü açıkken görev çubuğu ve başka uygulama tıklanabilmeli.
3. Menüden arıza/yoklama gibi kapatıcı olmayan bir işlem deneyin.
4. Düğmeyi sürükleyin; sürükleme yanlışlıkla menü açmamalı.
5. Menü kapatma ve dokunmadan 12 saniye bekleme denenmeli.
6. Kilitle/aç, duyuru ve tam ekran bittiğinde düğmenin geri gelmesini doğrulayın.

Veritabanı/sertifika silinmez veya yeniden eşleme yapılmaz. Başarısız denemede
eski ajan paketiyle geri dönülebilir. Kabul sonucu alınmadan toplu dağıtım yapılmaz.
