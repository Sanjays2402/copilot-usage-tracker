"""Sanity tests for the installer packaging."""

import os

from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PKG = os.path.join(ROOT, "packaging")


def _read(*parts):
    with open(os.path.join(*parts), encoding="utf-8", errors="replace") as f:
        return f.read()


def test_icons_exist_and_open():
    for name in ("icon.png", "icon.ico", "icon.icns"):
        path = os.path.join(PKG, "assets", name)
        assert os.path.exists(path), f"missing {name}; run python packaging/icon.py"
        with Image.open(path) as img:
            img.load()
            assert img.size[0] >= 16


def test_windows_installer_script():
    iss = _read(PKG, "windows", "installer.iss")
    assert '#define AppVersion' in iss
    assert 'PrivilegesRequired=lowest' in iss  # per-user, no admin needed
    assert 'CurrentVersion\\Run' in iss  # optional run-at-login
    assert 'copilot-usage-tray.exe' in iss
    assert 'LicenseFile=' in iss


def test_windows_build_script():
    ps1 = _read(PKG, "windows", "build.ps1")
    assert 'installer.iss' in ps1
    assert 'pyinstaller tray\\pyinstaller.spec' in ps1
    assert 'ISCC.exe' in ps1


def test_macos_app_spec():
    spec = _read(PKG, "macos", "app.spec")
    assert '"LSUIElement": True' in spec  # menu-bar-only, no Dock icon
    assert 'Copilot Usage Tracker.app' in spec
    assert 'icon.icns' in spec


def test_macos_build_scripts():
    build = _read(PKG, "macos", "build.sh")
    assert 'app.spec' in build
    assert 'codesign' in build
    assert 'hdiutil create' in build
    notarize = _read(PKG, "macos", "notarize.sh")
    assert 'notarytool submit' in notarize
    assert 'stapler staple' in notarize


def test_packaging_workflow():
    wf = _read(ROOT, ".github", "workflows", "packaging.yml")
    assert 'tags: ["v*"]' in wf
    assert 'windows-latest' in wf
    assert 'macos-latest' in wf
    assert 'action-gh-release' in wf
