"""Paketlenmiş programın giriş noktası.

Bağımsız değişken verilmezse durum penceresi açılır (kısayolların yaptığı; sunucuyu
başlatmaz, Windows hizmetinin durumunu gösterir). "hizmet" ile Hizmet Denetim
Yöneticisi'nin başlattığı sunucu hizmeti olur (kurucunun kaydettiği komut); "sunucu"
ile penceresiz çalışır (derleme duman testi); "tasi" kurucunun veri taşımasıdır.
"pencere --gizli" pencere açmadan yalnız bildirim alanı simgesini getirir (kurucunun isteğe
bağlı "Tahta Kontrol durum simgesi" oturum açılışı kısayolu); o da sunucu açmaz.
"""

import os
import sys

if sys.stdout is None:  # pencereli derlemede uçbirim yoktur
    sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115

if sys.argv[1:2] == ["hizmet"]:
    os.environ["TAHTA_HIZMET"] = "1"  # ayar.HIZMET içe aktarımda okunur

from tahta_sunucu.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["pencere"]))
