#!/bin/bash
# Tahta Kontrol ajani kurulum betigi (surum @SURUM@)
# Kullanim:  sudo bash tahta-kur.sh ESLESTIRME_KODU
# Iletiler bilerek ASCII tutulur.
set -euo pipefail

SUNUCU="@SUNUCU@"
# Sunucu adres listesi (bosluklu; bos olabilir). Ajan birincil adrese ulasamazsa siradakini dener.
SUNUCULAR="@SUNUCULAR@"
PARMAK_IZI="@PARMAK_IZI@"
PAKET_SHA256="@PAKET_SHA256@"
KOD="${1:-}"

if [ "$(id -u)" != "0" ]; then
    echo "Bu betik yonetici yetkisi ister:  sudo bash $0 ESLESTIRME_KODU"
    exit 1
fi
if [ -z "$KOD" ]; then
    echo "Eslestirme kodu verilmedi.  Kullanim:  sudo bash $0 ESLESTIRME_KODU"
    exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 bulunamadi; ajan kurulamaz."
    exit 3
fi

echo "Sunucu      : $SUNUCU"
echo "Parmak izi  : ${PARMAK_IZI:0:16}...  (paneldeki 'Tahta ekle' sayfasiyla ayni olmali)"

BURASI="$(cd "$(dirname "$0")" && pwd)"
GECICI="$(mktemp -d)"
trap 'rm -rf "$GECICI"' EXIT
PAKET="$GECICI/tahta-ajan.deb"

if [ -f "$BURASI/tahta-ajan.deb" ]; then
    echo "Paket betigin yanindan aliniyor."
    cp "$BURASI/tahta-ajan.deb" "$PAKET"
else
    echo "Paket sunucudan indiriliyor."
    python3 - "$SUNUCU" "$PARMAK_IZI" "$PAKET" <<'PY'
import hashlib, http.client, ssl, sys
from urllib.parse import urlsplit
sunucu, parmak_izi, hedef = sys.argv[1:4]
parca = urlsplit(sunucu)
if parca.scheme == "https":
    baglam = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    baglam.check_hostname = False
    baglam.verify_mode = ssl.CERT_NONE
    baglanti = http.client.HTTPSConnection(parca.hostname, parca.port or 443, timeout=30, context=baglam)
    baglanti.connect()
    if hashlib.sha256(baglanti.sock.getpeercert(binary_form=True)).hexdigest() != parmak_izi:
        sys.exit("Sunucu sertifikasi beklenen parmak iziyle uyusmuyor; kurulum durduruldu.")
else:
    baglanti = http.client.HTTPConnection(parca.hostname, parca.port or 80, timeout=30)
baglanti.request("GET", "/kur/paket")
yanit = baglanti.getresponse()
if yanit.status != 200:
    sys.exit("Paket indirilemedi: HTTP %s" % yanit.status)
open(hedef, "wb").write(yanit.read())
PY
fi

if ! echo "$PAKET_SHA256  $PAKET" | sha256sum -c - >/dev/null 2>&1; then
    echo "Paket ozeti tutmuyor; kurulum durduruldu."
    exit 4
fi

mkdir -p /etc/tahta-kontrol
python3 - "$SUNUCU" "$PARMAK_IZI" "$SUNUCULAR" <<'PY'
import json, os, sys
yol = "/etc/tahta-kontrol/ajan.json"
try:
    eski = json.load(open(yol, encoding="utf-8"))
except Exception:
    eski = {}
yeni = {"sunucu": sys.argv[1], "parmak_izi": sys.argv[2]}
sunucular = [a for a in sys.argv[3].split() if a.startswith("https://")][:5]
if sunucular:
    yeni["sunucular"] = sunucular
# Ayni sunucuya yeniden kurulumda tahtanin kaydi korunur.
if eski.get("parmak_izi") == yeni["parmak_izi"] and eski.get("tahta_id"):
    yeni["tahta_id"] = eski["tahta_id"]
    yeni["anahtar"] = eski.get("anahtar", "")
with open(yol + ".yeni", "w", encoding="utf-8") as dosya:
    json.dump(yeni, dosya)
os.chmod(yol + ".yeni", 0o600)
os.replace(yol + ".yeni", yol)
PY

echo "Paket kuruluyor."
dpkg -i "$PAKET"

echo "Tahta sunucuya kaydediliyor."
if ! /usr/bin/tahta-ajan kaydol "$KOD"; then
    echo "Kayit yapilamadi. Kodu ve sunucu erisimini denetleyip betigi yeniden calistirin."
    exit 5
fi

if [ -d /run/systemd/system ]; then
    systemctl restart tahta-ajan.service || true
fi

echo
echo "Kurulum tamamlandi. Okul idaresi panelden bu tahtayi onaylayinca kullanima girer."
echo "Kilit ve duyuru ekrani bir sonraki oturum acilisinda kendiliginden baslar;"
echo "hemen baslatmak icin oturumu kapatip acin."
