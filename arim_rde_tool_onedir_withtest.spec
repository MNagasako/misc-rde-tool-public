# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['src\\arim_rde_tool.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src/image', 'image'),
        ('src/resources', 'resources'),
        ('config', 'config'),
        ('src/js_templates', 'js_templates'),
        # tests配下を完全に含める（診断機能に必要）
        ('tests', 'tests'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # テスト関連
        'pytest',  '_pytest', 'nose', 'doctest',
        # 未使用の科学計算・データ処理（大容量）
        'matplotlib', 'IPython', 'scipy', 'numexpr', 'numba',
        'traitlets', 'jupyter', 'notebook',
        # 未使用のExcel/DB関連（削減効果大）
        'xlrd','pyxlsb', 'odf', 'python_calamine',
        # 未使用のデータフォーマット（削減効果大）
        'lxml', 'html5lib', 'defusedxml',
        'pyarrow', 'fastparquet', 'fsspec',
        # 未使用のネットワーク/暗号化（削減効果大）
        'OpenSSL', 'cryptography', 'h2', 'socks', 'brotli', 'brotlicffi',
        'zstandard', 'compression',
        # 未使用のPIL/画像処理
        'PIL.Jpeg2KImagePlugin', 'PIL.SpiderImagePlugin', 'olefile',
        # その他未使用
        'curses', 'readline', 'pdb', 'pydoc',
        'setuptools', 'distutils', 'pkg_resources', 'wheel',
        'secretstorage', 'gi', 'dbus',
        # PySide6未使用モジュール（削減効果中）
        'PySide6.QtPositioning', 'PySide6.QtQuick', 'PySide6.QtQml',
        'PySide6.QtOpenGL', 'PySide6.QtQuickWidgets',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],          # ★ ここを空にする
    [],          # ★ データも渡さない
    exclude_binaries=True,   # ★ onedir の肝
    name='arim_rde_tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
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

coll = COLLECT(
    exe,
    a.binaries,   # ★ こっちでまとめる
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='arim_rde_tool',
)
