# PyInstaller tanımı: Tahta Kontrol sunucusu (Windows, klasör düzeni)
# Depo kökünden çalıştırılır: pyinstaller packaging/windows/tahta-kontrol.spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

KOK = Path(SPECPATH).resolve().parent.parent

datas = [
    (str(KOK / "tahta_sunucu" / "sablonlar"), "tahta_sunucu/sablonlar"),
    (str(KOK / "tahta_sunucu" / "statik"), "tahta_sunucu/statik"),
    (str(KOK / "tahta_sunucu" / "ajan_paket"), "tahta_sunucu/ajan_paket"),
]
# Ajanın kaynak dosyaları veri olarak da taşınır: sunucu .deb paketini bunlardan üretir.
datas += [(str(yol), "tahta_ajan") for yol in sorted((KOK / "tahta_ajan").glob("*.py"))]
datas += collect_data_files("tzdata")

a = Analysis(
    [str(KOK / "packaging" / "windows" / "giris.py")],
    pathex=[str(KOK)],
    datas=datas,
    hiddenimports=collect_submodules("uvicorn") + ["python_multipart", "tahta_sunucu.pencere"],
    excludes=["gi", "pytest", "httpx"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TahtaKontrol",
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, name="TahtaKontrol")
