# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\arim_rde_tool.py'],
    pathex=[],
    binaries=[],
    datas=[('src/image', 'image'), ('src/js_templates', 'js_templates'), ('THIRD_PARTY_NOTICES', 'THIRD_PARTY_NOTICES'), ('LICENSE', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ARIM-RDE-Tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['src\\image\\icon\\icon1.ico'],
)
