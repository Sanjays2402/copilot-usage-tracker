# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the copilot-usage-tracker tray app.

Starting point only: Streamlit pulls in a large dependency graph, so
expect to extend hiddenimports/datas for your exact Streamlit version
and to test the bundle on a clean machine before distributing.
"""

block_cipher = None

a = Analysis(
    ["tray/app.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("dashboard", "dashboard"),
        ("src/copilot_usage_tracker", "copilot_usage_tracker"),
        ("tray", "tray"),
    ],
    hiddenimports=[
        "streamlit",
        "pandas",
        "pystray",
        "webview",
        "PIL",
        "copilot_usage_tracker",
        "tray.app",
        "tray.icon",
        "tray.util",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="copilot-usage-tray",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # windowed: no console window on Windows
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="copilot-usage-tray",
)
