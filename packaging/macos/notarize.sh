#!/usr/bin/env bash
# Notarize a DMG with Apple so Gatekeeper accepts it on other Macs.
# Usage: bash packaging/macos/notarize.sh <path-to-dmg>
#
# Requires:
#   - the DMG built from an app signed with a "Developer ID Application"
#     certificate (APPLE_CODESIGN_IDENTITY during build.sh)
#   - env: APPLE_ID (Apple ID email), APPLE_TEAM_ID, APPLE_APP_PASSWORD
#     (an app-specific password from appleid.apple.com)
set -euo pipefail

DMG="${1:?usage: notarize.sh <path-to-dmg>}"
: "${APPLE_ID:?set APPLE_ID}"; : "${APPLE_TEAM_ID:?set APPLE_TEAM_ID}"
: "${APPLE_APP_PASSWORD:?set APPLE_APP_PASSWORD (app-specific password)}"

xcrun notarytool submit "$DMG" \
    --apple-id "$APPLE_ID" \
    --team-id "$APPLE_TEAM_ID" \
    --password "$APPLE_APP_PASSWORD" \
    --wait
xcrun stapler staple "$DMG"
xcrun stapler validate "$DMG" && echo "notarized + stapled: $DMG"
