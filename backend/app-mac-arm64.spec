from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path
import playwright

block_cipher = None

playwrightPackageDir = Path(playwright.__file__).resolve().parent
playwrightDriverPackageDir = playwrightPackageDir / "driver" / "package"
specDir = Path(__file__).resolve().parent
bundledZip = specDir / "playwright-browsers.zip"

playwrightDatas = []

if playwrightDriverPackageDir.exists():
    playwrightDatas.append((str(playwrightDriverPackageDir), "playwright/driver/package"))
else:
    print(f"WARNING: Playwright driver package not found: {playwrightDriverPackageDir}")

if bundledZip.exists():
    playwrightDatas.append((str(bundledZip), "playwright-browsers.zip"))
else:
    print("WARNING: backend/playwright-browsers.zip not found. CI must create it before PyInstaller.")

a = Analysis(
    ['app.py'],
    pathex=['backend'],
    binaries=[],
    datas=playwrightDatas,
    hiddenimports=collect_submodules("playwright") + collect_submodules("flask") + collect_submodules("flask_cors") + ['pypresence'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='app_mac_bin_arm64',
    debug=False,
    strip=False,
    upx=True,
    console=False
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name='app_mac_arm64',
    distpath='dist/app_mac_arm64'
)
