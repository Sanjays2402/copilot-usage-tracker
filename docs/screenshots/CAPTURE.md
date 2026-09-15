# Capturing screenshots

`dashboard.png` and `users-drilldown.png` are generated from fictional demo
data (fake `demo-*` users, `seed_demo.py`) — never real usage. No
repository-local virtualenv: use the system Python (Streamlit, PySide6,
pymupdf, and mss are installed with `--break-system-packages`).

```bash
# 1. Seed the demo database (regenerates docs/screenshots/demo.db)
COPILOT_DB=docs/screenshots/demo.db python3 docs/screenshots/seed_demo.py

# 2. Launch the dashboard (is_configured() requires COPILOT_ORG or
#    COPILOT_ENTERPRISE; PYTHONPATH=src so the package imports)
cd ~/workspace/copilot-usage-tracker-build
PYTHONPATH=src \
COPILOT_DB=docs/screenshots/demo.db \
COPILOT_ORG=acme-corp \
COPILOT_AUDIT_FILE=/tmp/demo-audit.jsonl \
python3 -m streamlit run dashboard/app.py \
  --server.headless true --server.port 8501
```

3. Render with QtWebEngine under Xvfb and capture via `printToPdf`
   (the GPU compositor produces no pixels in this headless VM, so
   QWidget/mss screen grabs come out blank; `printToPdf` renders
   faithfully). Set **Granted seats = 25** in the sidebar so the cost /
   utilization KPIs are non-zero, wait for "Unusual activity", then print
   the Overview tab to `dashboard.png` (1440×900 @ 96 dpi). Switch to the
   Users tab, wait for "User drill-down", print, and composite the
   drill-down section with the daily-charts page into
   `users-drilldown.png` (1440×900).

   The last working capture script pattern lives in `/tmp` only while the
   VM lasts — re-derive from the notes above if screenshots need a
   refresh. `setup.png` must NOT be refreshed (CI-captured installer
   asset).

4. Verify before accepting: PNG is exactly 1440×900, file size is tens of
   KB (not a ~6 KB blank), and KPI values / charts are visibly rendered.

5. Delete `docs/screenshots/demo.db` afterwards — it is a capture
   artifact, not a repo asset.

## Windows installer screenshots (captured on a genuine Windows machine)

`setup.png`, `installer-license.png`, and `installer-progress.png` were
captured during CI (`windows-smoke` in
[.github/workflows/packaging.yml](.github/workflows/packaging.yml)) on a
genuine Windows machine. To re-capture by hand:

1. Build the installer: `powershell -ExecutionPolicy Bypass -File packaging/windows/build.ps1`
2. Run `packaging\windows\dist\CopilotUsageTracker-Setup-<ver>.exe` and capture:
   - `installer-license.png` — the license agreement page
   - `installer-progress.png` — the installing progress page
3. After install, launch from the Start Menu and capture `setup.png` —
   the first-run setup window.
4. Never capture the full desktop in a public screenshot (other windows
   can leak into frame).
