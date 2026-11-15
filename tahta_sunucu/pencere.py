"""Masaüstü denetim penceresi: sunucuyu başlatır, adresleri gösterir, paneli açar.

Kurulu program bu pencereyle çalışır. Pencere kapatılınca sunucu durur; bu
yüzden kapatma onay ister ve pencere simge durumuna küçültülerek açık tutulur.
"""

from __future__ import annotations

import logging
import tkinter as tk
import webbrowser
from tkinter import messagebox

from . import __version__, ayar
from .sunucu import Sunucu


def calistir() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        filename=str(ayar.veri_dizini() / "sunucu.log"),
        encoding="utf-8",
    )
    kok = tk.Tk()
    kok.title("Tahta Kontrol")
    kok.resizable(False, False)
    try:
        sunucu = Sunucu()
        sunucu.baslat()
    except Exception as hata:  # pencere açılamadan önce kullanıcıya gösterilir
        logging.exception("Sunucu başlatılamadı")
        kok.withdraw()
        messagebox.showerror("Tahta Kontrol", f"Sunucu başlatılamadı:\n\n{hata}")
        return 1

    cerceve = tk.Frame(kok, padx=22, pady=18)
    cerceve.pack()
    tk.Label(cerceve, text="Tahta Kontrol sunucusu çalışıyor", font=("Segoe UI", 14, "bold")).pack(anchor="w")
    tk.Label(cerceve, text=f"Sürüm {__version__}", fg="#555").pack(anchor="w", pady=(0, 12))

    tk.Label(cerceve, text="Bu bilgisayardan panel adresi:", font=("Segoe UI", 9, "bold")).pack(anchor="w")
    tk.Label(cerceve, text=sunucu.yerel_adres, fg="#1d4ed8").pack(anchor="w", pady=(0, 8))

    tk.Label(
        cerceve, text="Diğer idari bilgisayarlardan panel adresi:", font=("Segoe UI", 9, "bold")
    ).pack(anchor="w")
    adresler = sunucu.ag_adresleri() or ["(ağ bağlantısı bulunamadı)"]
    for adres in adresler:
        kutu = tk.Entry(cerceve, width=42, relief="flat", fg="#1d4ed8")
        kutu.insert(0, adres)
        kutu.configure(state="readonly")
        kutu.pack(anchor="w")
    tk.Label(
        cerceve,
        text=(
            "Diğer bilgisayarlarda tarayıcı ilk açılışta sertifika uyarısı gösterir;\n"
            "\"Gelişmiş\" → \"siteye ilerle\" ile devam edilir."
        ),
        fg="#555",
        justify="left",
    ).pack(anchor="w", pady=(4, 14))

    dugmeler = tk.Frame(cerceve)
    dugmeler.pack(anchor="w")
    tk.Button(
        dugmeler, text="Paneli aç", width=16, command=lambda: webbrowser.open(sunucu.yerel_adres)
    ).pack(side="left")
    tk.Button(dugmeler, text="Simge durumuna küçült", width=22, command=kok.iconify).pack(side="left", padx=8)

    def kapat():
        if messagebox.askyesno(
            "Tahta Kontrol",
            "Sunucu durdurulursa tahtalar çevrimdışı kalır ve panel açılmaz.\n\nSunucu durdurulsun mu?",
        ):
            sunucu.durdur()
            kok.destroy()

    tk.Button(dugmeler, text="Sunucuyu durdur", width=16, command=kapat).pack(side="left")
    kok.protocol("WM_DELETE_WINDOW", kapat)
    kok.mainloop()
    return 0
