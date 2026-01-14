# backend/app.spec
import sys
import os
import glob
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules
import playwright

block_cipher = None

# Where PyInstaller is running this spec from
specDir = Path(SPECPATH)

# Playwright python package locations
playwrightPackageDir = Path(playwright.__file__).resolve().parent
playwrightDriverPackageDir = playwrightPackageDir / "driver" / "package"

# This zip is created by your workflow step inside backend/
bundledZip = specDir / "playwright-browsers.zip"

playwrightDatas = []

# 1) Bundle Playwright driver package (node driver + cli that Playwright uses)
if playwrightDriverPackageDir.exists():
    playwrightDatas.append((str(playwrightDriverPackageDir), "playwright/driver/package"))
else:
    print(f"WARNING: Playwright driver package dir not found: {playwrightDriverPackageDir}")

# 2) Bundle zipped browsers (preferred)
if bundledZip.exists():
    # Copy the zip FILE into the root of the bundle (_MEIPASS)
    playwrightDatas.append((str(bundledZip), "."))
else:
    print(f"WARNING: playwright-browsers.zip not found at {bundledZip}. Did CI create it in backend/?")

# Windows needs python*.dll sometimes depending on how Python is installed on runner
pythonDlls = glob.glob(os.path.join(os.path.dirname(sys.executable), "python*.dll"))

a = Analysis(
    ["app.py"],
    pathex=["backend"],
    binaries=[(dll, ".") for dll in pythonDlls],
    datas=playwrightDatas,
    hiddenimports=collect_submodules("playwright") + ["pypresence"],
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
    name="app",
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
    distpath="resources/app/build",
    workpath="backend/build",
    name="app",
)
