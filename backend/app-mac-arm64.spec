from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path
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

a = Analysis(
    ["app.py"],
    pathex=["backend"],
    binaries=[],
    datas = [
      (str(playwrightDriverPackageDir), "playwright/driver/package"),
      ("playwright-browsers.zip", "playwright-browsers.zip"),
    ]
    hiddenimports=collect_submodules("flask") + collect_submodules("flask_cors") + ["pypresence"] + collect_submodules("playwright"),
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
    exclude_binaries=True,
    name="app_mac_bin_arm64",
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
    name="app_mac_arm64",
    distpath="dist/app_mac_arm64",
)
