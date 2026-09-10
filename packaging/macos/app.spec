# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the macOS .app bundle.

Produces dist/"Copilot Usage Tracker.app" as a menu-bar-only app
(LSUIElement: no Dock icon), then packaging/macos/build.sh wraps it
in a DMG.
"""

import os

ROOT = os.path.abspath(os.path.join(SPECPATH, "..", ".."))

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
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
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
