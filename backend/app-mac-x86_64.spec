import sys, os, glob
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules
import playwright

block_cipher = None

playwrightPackageDir = Path(playwright.__file__).resolve().parent
playwrightDriverPackageDir = playwrightPackageDir / "driver" / "package"

specDir = Path(SPECPATH)
bundledZip = specDir / "playwright-browsers.zip"

playwrightDatas = [
    (str(playwrightDriverPackageDir), "playwright/driver/package"),
]

if bundledZip.exists():
    playwrightDatas.append((str(bundledZip), "playwright-browsers.zip"))
else:
    print(f"WARNING: playwright-browsers.zip not found at {bundledZip}")

pythonDlls = glob.glob(os.path.join(os.path.dirname(sys.executable), "python*.dll"))

a = Analysis(
    ["app.py"],
    pathex=["backend"],
    binaries=[(dll, ".") for dll in pythonDlls],
    datas = [(str(playwrightDriverPackageDir), "playwright/driver/package"), ("playwright-browsers.zip", "playwright-browsers.zip"),],
    hiddenimports=["pypresence"] + collect_submodules("playwright"),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=False,
    name="app_linux_bin",
    debug=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="app-linux",
    distpath="dist/app-linux",
)
