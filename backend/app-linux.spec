from pathlib import Path
import playwright

block_cipher = None

playwrightPackageDir = Path(playwright.__file__).resolve().parent
playwrightDriverPackageDir = playwrightPackageDir / "driver" / "package"

specDir = Path(SPECPATH)
bundledZip = specDir / "playwright-browsers.zip"

playwrightDatas = []

if playwrightDriverPackageDir.exists():
    playwrightDatas.append((str(playwrightDriverPackageDir), "playwright/driver/package"))
else:
    print(f"WARNING: Playwright driver package not found: {playwrightDriverPackageDir}")

# 2) Bundle zipped browsers (preferred)
if bundledZip.exists():
    # Copy the zip FILE into the root of the bundle (_MEIPASS)
    playwrightDatas.append((str(bundledZip), "."))
else:
    print(f"WARNING: playwright-browsers.zip not found at {bundledZip}. Did CI create it in backend/?")

a = Analysis(
    ["app.py"],
    pathex=["backend"],
    binaries=[],
    datas=playwrightDatas,
    hiddenimports=[
        "pypresence",
        "playwright.sync_api",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "playwright._impl.__pyinstaller",
    ],
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
    name="app_linux",
    distpath="dist/app_linux",
)
