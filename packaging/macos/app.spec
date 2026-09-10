# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the macOS .app bundle.

Produces dist/"Copilot Usage Tracker.app" as a menu-bar-only app
(LSUIElement: no Dock icon), then packaging/macos/build.sh wraps it
in a DMG.
"""

import os

from PyInstaller.utils.hooks import copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

# streamlit.version calls importlib.metadata.version("streamlit") at import
# time; the frozen dashboard-server exe dies with PackageNotFoundError
# unless the dist-info is collected explicitly.
STREAMLIT_METADATA = copy_metadata("streamlit")

VERSION = "0.1.0"
try:
    import tomllib

    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
        VERSION = tomllib.load(f)["project"]["version"]
except Exception:
    pass

ICON = os.path.join(ROOT, "packaging", "assets", "icon.icns")

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
        "keyring",
        "yaml",
        "click",
        "requests",
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
    datas=STREAMLIT_METADATA,
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
    name="Copilot Usage Tracker",
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
    icon=ICON,
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
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
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
    b.binaries,
    b.zipfiles,
    b.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Copilot Usage Tracker",
)
app = BUNDLE(
    coll,
    name="Copilot Usage Tracker.app",
    icon=ICON,
    bundle_identifier="com.sanjays2402.copilot-usage-tracker",
    info_plist={
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        # Menu-bar-only agent: lives in the menu bar, no Dock icon.
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "NSRequiresAquaSystemAppearance": False,
    },
)
