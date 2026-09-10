# Capturing screenshots

`dashboard.png` is generated from fictional demo data:

```bash
python3 -m venv .venv-shot
.venv-shot/bin/pip install -e ".[dashboard]"
COPILOT_DB=docs/screenshots/demo.db python3 docs/screenshots/seed_demo.py
COPILOT_DB=docs/screenshots/demo.db \
  .venv-shot/bin/streamlit run dashboard/app.py --server.headless true
# then screenshot http://localhost:8501 (e.g. headless Chromium)
```

## Windows installer screenshots (capture on a Windows machine)

The installer can only be built and run on Windows, so these shots have to
be taken there. Two minutes with the Snipping Tool (`Win+Shift+S`):

1. Build the installer: `powershell -ExecutionPolicy Bypass -File packaging/windows/build.ps1`
2. Run `packaging\windows\dist\CopilotUsageTracker-Setup-<ver>.exe` and capture:
   - `installer-welcome.png` — the welcome page
   - `installer-options.png` — the "select additional tasks" page (startup / desktop icon)
   - `installer-progress.png` — the installing progress page
3. After install, launch from the Start Menu and capture:
   - `tray-icon.png` — the tray icon in the hidden-icons overflow popup
   - `tray-menu.png` — the right-click tray menu
   - `dashboard-popup.png` — the dashboard popup window
4. Save all files in this directory (`docs/screenshots/`) with exactly
   these names, then uncomment the installer block in the README's
   Screenshots section.
