# backend/app-mac-x86_64.spec
from PyInstaller.utils.hooks import collect_submodules
from pathlib import Path
import playwright

block_cipher = None

playwrightPackageDir = Path(playwright.__file__).resolve().parent
playwrightBrowsersDir = playwrightPackageDir / ".local-browsers"

playwrightDatas = []
if playwrightBrowsersDir.exists():
    # Bundle Chromium where Playwright expects it
    playwrightDatas.append((str(playwrightBrowsersDir), "playwright/.local-browsers"))
else:
    print("WARNING: Playwright .local-browsers not found. Did you run playwright install with PLAYWRIGHT_BROWSERS_PATH=0?")

a = Analysis(
    ['app.py'],
    pathex=['backend'],
    binaries=[],
    datas=playwrightDatas,
    hiddenimports=collect_submodules('flask') + collect_submodules('flask_cors') + collect_submodules('_internal') + ['pypresence'] + collect_submodules("playwright"),
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
    exclude_binaries=True,
    name='app_mac_bin_x86_64',
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
    name='app_mac_x86_64',
    distpath='dist/app_mac_x86_64'
)
