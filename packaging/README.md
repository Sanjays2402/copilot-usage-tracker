# Packaging

Proper installers for the desktop tray app:

| OS      | Artifact                                    | Built by                          |
|---------|---------------------------------------------|-----------------------------------|
| Windows | `CopilotUsageTracker-Setup-<ver>.exe`       | Inno Setup 6 (`build.ps1`)        |
| macOS   | `CopilotUsageTracker-<ver>.dmg`             | PyInstaller `.app` + `hdiutil`    |

The easiest route is automated: push a tag like `v0.2.0` and the
[Packaging workflow](../.github/workflows/packaging.yml) builds both on
GitHub-hosted runners and attaches them to the GitHub Release.

## Icons

`packaging/assets/` holds the app icon rendered from `tray/icon.py`:

```bash
python packaging/icon.py   # regenerates icon.png / icon.ico / icon.icns
```

## Windows (local build)

Requirements: Python 3.11+, Inno Setup 6
(`winget install --id JRSoftware.InnoSetup`).

```powershell
powershell -ExecutionPolicy Bypass -File packaging/windows/build.ps1
```

This creates an isolated venv, installs `.[desktop,dashboard]`, bundles with
PyInstaller (windowed, no console), and compiles
`packaging/windows/installer.iss` into
`packaging/windows/dist/CopilotUsageTracker-Setup-<ver>.exe`.

The installer is per-user (no admin rights needed), adds a Start Menu
shortcut, offers optional launch-at-startup and a desktop shortcut, and
ships a real uninstaller. Version comes from the `vX.Y.Z` tag, else from
`pyproject.toml`.

## macOS (local build)

Requirements: macOS, Python 3.11+, Xcode command line tools.

```bash
bash packaging/macos/build.sh
```

This builds `Copilot Usage Tracker.app` via `packaging/macos/app.spec`
(`LSUIElement` makes it menu-bar-only: no Dock icon), code-signs it, and
wraps it in a drag-to-Applications DMG at
`packaging/macos/dist/CopilotUsageTracker-<ver>.dmg`.

## Signing & notarization (for distribution)

Unsigned builds work for personal use but trigger OS warnings for others:

- **Windows SmartScreen** warns on unknown publishers. For a clean install,
  sign the Setup exe with a code-signing certificate (or Azure Trusted
  Signing) before distributing.
- **macOS Gatekeeper** blocks unsigned/notarized apps. For distribution:
  1. Get an Apple Developer ID Application certificate.
  2. `export APPLE_CODESIGN_IDENTITY="Developer ID Application: Your Name (TEAMID)"`
     then `bash packaging/macos/build.sh`.
  3. `bash packaging/macos/notarize.sh <dmg>` with `APPLE_ID`,
     `APPLE_TEAM_ID`, and an app-specific `APPLE_APP_PASSWORD`.

  The GitHub workflow does steps 2-3 automatically when the
  `APPLE_CODESIGN_IDENTITY`, `APPLE_ID`, `APPLE_TEAM_ID`, and
  `APPLE_APP_PASSWORD` repo secrets are set.

## Versioning

Both installers read the version from `pyproject.toml`, overridden by the
release tag (`v0.2.0` -> `0.2.0`). Bump the version in `pyproject.toml`,
tag, push.
