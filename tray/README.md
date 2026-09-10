# Desktop tray app

`copilot-usage tray` (after `pip install -e ".[desktop]"`) puts the
tracker in the taskbar's hidden icons (Windows) or the menu bar (macOS).
Clicking the icon pops the dashboard up in a native window; closing the
window hides it again without quitting.

## How it works

- `tray/app.py` starts a local Streamlit server (the same
  `dashboard/app.py` as the web version) on a free localhost port, then
  shows a [pystray](https://github.com/moses-palmer/pystray) icon.
- Clicking the icon (or the default menu item) opens the dashboard URL in
  a [pywebview](https://pywebview.flowrl.com/) native window. Closing the
  window only hides it; the tray icon keeps running.
- Right-click menu: **Open dashboard**, **Collect latest data** (runs
  yesterday's `collect --with-teams` in the background with a tray
  notification), **Open in browser**, **Quit**.
- Data lives in `~/.copilot-usage-tracker/copilot_usage.db` unless
  `COPILOT_DB` is set. If pywebview fails on a platform, the app falls
  back to opening the dashboard in the default browser.
- `tray/icon.py` renders the tray glyph with Pillow at runtime -- no
  binary assets to ship. `tray/util.py` holds the GUI-free helpers
  (port picking, PyInstaller path resolution); those are unit-tested.

## Run at login

**Windows** -- press `Win+R`, type `shell:startup`, and drop in a shortcut
to `copilot-usage.exe tray` (or a `.bat` running `copilot-usage tray`).

**macOS** -- create `~/Library/LaunchAgents/com.copilot-usage-tracker.plist`
pointing at the `copilot-usage tray` binary, then
`launchctl load ~/Library/LaunchAgents/com.copilot-usage-tracker.plist`.

**Linux** -- drop a `.desktop` file in `~/.config/autostart/` with
`Exec=copilot-usage tray`.

## Packaging with PyInstaller

A starting-point spec is in `tray/pyinstaller.spec`:

```bash
pip install -e ".[desktop,dashboard]" pyinstaller
pyinstaller tray/pyinstaller.spec
```

Streamlit is notoriously heavy under PyInstaller (many hidden imports and
data files); expect to iterate on `hiddenimports`/`datas` for your
Streamlit version. Verify the bundled app on a clean machine before
distributing -- the supported fallback is always a plain
`pip install` plus a login item.
