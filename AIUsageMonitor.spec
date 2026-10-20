# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

datas = []
binaries = []
hiddenimports = []


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Qt uses Windows' unversioned ICU ABI. The host Python runtime also supplies
# an unrelated ICU 78 DLL on PATH; bundling it causes a QtCore import failure.
# This application targets Windows 11 and uses the ICU shipped with Windows.
a.binaries = [item for item in a.binaries if Path(item[0]).name.lower() not in {'icuuc.dll', 'icuin.dll', 'icudt78.dll'}]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AIUsageMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AIUsageMonitor',
)
