# backend/app.spec
import sys
import os
import glob
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

pythonDlls = glob.glob(os.path.join(os.path.dirname(sys.executable), "python*.dll"))

a = Analysis(['app.py'],
             pathex=['backend'],
             binaries=[(dll, '.') for dll in pythonDlls],
             datas=[],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher,
             noarchive=False)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          [],
          exclude_binaries=False,
          name='app_mac_bin_arm64',
          debug=False,
          bootloader_ignore_signals=False,
          strip=False,
          upx=True,
          console=False)
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='app_mac_arm64',
               distpath='dist/app_mac_arm64',)
