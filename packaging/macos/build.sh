#!/usr/bin/env bash
# Build the macOS app bundle and DMG for Copilot Usage Tracker.
# Usage: bash packaging/macos/build.sh
#
# Signing: set APPLE_CODESIGN_IDENTITY to a "Developer ID Application"
# identity for distribution. Without it, the app is ad-hoc signed
# (fine for local testing; Gatekeeper will block it for others until
# it is properly signed + notarized -- see notarize.sh).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PKG="$ROOT/packaging/macos"
cd "$ROOT"

VERSION="$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
echo "Building Copilot Usage Tracker $VERSION for macOS"

# 1. Isolated build venv
python3 -m venv .venv-pkg
.venv-pkg/bin/pip install -q --upgrade pip
.venv-pkg/bin/pip install -q -e ".[desktop,dashboard]" pyinstaller

# 2. .app bundle (menu-bar-only via LSUIElement, see app.spec)
.venv-pkg/bin/pyinstaller packaging/macos/app.spec \
    --distpath "$PKG/dist" --workpath "$PKG/build" --noconfirm

APP="$PKG/dist/Copilot Usage Tracker.app"
[ -d "$APP" ] || { echo "PyInstaller output missing: $APP" >&2; exit 1; }

# 3. Code sign ("-" = ad-hoc when no identity is configured)
IDENTITY="${APPLE_CODESIGN_IDENTITY:--}"
codesign --deep --force --options runtime --sign "$IDENTITY" "$APP"
codesign --verify --deep --strict "$APP" && echo "signature ok"

# 4. DMG with drag-to-Applications
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
DMG="$PKG/dist/CopilotUsageTracker-${VERSION}.dmg"
hdiutil create -volname "Copilot Usage Tracker" \
    -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null

echo ""
echo "DMG ready: $DMG"
