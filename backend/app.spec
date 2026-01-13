# backend/app.spec
import sys
import os
import glob
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules
import playwright

block_cipher = None

playwrightPackageDir = Path(playwright.__file__).resolve().parent
playwrightDriverPackageDir = playwrightPackageDir / "driver" / "package"
playwrightBrowsersDir = playwrightDriverPackageDir / ".local-browsers"

playwrightDatas = []

# Bundle Playwright's driver package (contains node/cli drivers)
if playwrightDriverPackageDir.exists():
    playwrightDatas.append((str(playwrightDriverPackageDir), "playwright/driver/package"))
else:
    print(f"WARNING: Playwright driver package dir not found: {playwrightDriverPackageDir}")

# Bundle the installed browsers (from PLAYWRIGHT_BROWSERS_PATH=0 install)
if playwrightBrowsersDir.exists():
    playwrightDatas.append((str(playwrightBrowsersDir), "playwright/driver/package/.local-browsers"))
else:
    print("WARNING: Playwright .local-browsers not found. Did you run playwright install with PLAYWRIGHT_BROWSERS_PATH=0?")

pythonDlls = glob.glob(os.path.join(os.path.dirname(sys.executable), "python*.dll"))

a = Analysis(
    ['app.py'],
    pathex=['backend'],
    binaries=[(dll, '.') for dll in pythonDlls],
    datas=playwrightDatas,
    hiddenimports=collect_submodules("playwright") + ['pypresence'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=False,
    name='app',
    debug=False,
    bootloader_ignore_signals=False,
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
    distpath='resources/app/build',
    workpath='backend/build',
    name='app'
)
