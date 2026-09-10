# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the copilot-usage-tracker tray app.

Starting point only: Streamlit pulls in a large dependency graph, so
expect to extend hiddenimports/datas for your exact Streamlit version
and to test the bundle on a clean machine before distributing.
"""

import os

# Anchor every path on the spec file's directory: PyInstaller resolves
# bare relative paths in a spec against the CWD, which differs between
# local builds and CI.
HERE = os.path.abspath(SPECPATH)
ROOT = os.path.abspath(os.path.join(HERE, ".."))

block_cipher = None

a = Analysis(
    [os.path.join(ROOT, "tray", "app.py")],
    pathex=[],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "dashboard"), "dashboard"),
        (os.path.join(ROOT, "src", "copilot_usage_tracker"), "copilot_usage_tracker"),
        (os.path.join(ROOT, "tray"), "tray"),
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

# --- dashboard server -------------------------------------------------------
# The tray app cannot use `sys.executable -m streamlit` when frozen
# (PyInstaller's bootloader ignores `-m` and would re-launch the tray app
# itself). So the Streamlit CLI gets its own console executable, placed
# next to the tray binary; TrayApp.start_server() execs it when frozen.
b = Analysis(
    [os.path.join(ROOT, "tray", "run_dashboard.py")],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=["streamlit"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_server = PYZ(b.pure, b.zipped_data, cipher=block_cipher)

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

exe_server = EXE(
    pyz_server,
    b.scripts,
    [],
    exclude_binaries=True,
    name="dashboard-server",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # console: real CLI semantics for the Streamlit server
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    exe_server,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="copilot-usage-tray",
)
