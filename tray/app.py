"""Desktop system-tray application for copilot-usage-tracker.

Lives in the taskbar's hidden icons (Windows) or the menu bar (macOS);
clicking the icon pops the dashboard up in a native window. A local
Streamlit server feeds the window, so the dashboard code is shared
verbatim with the web version.

Run:  copilot-usage tray
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import threading
import traceback
import webbrowser
from datetime import datetime, timezone

if __package__ in (None, ""):
    # Frozen entry point (PyInstaller runs this file as top-level module
    # "app", so relative imports fail with "no known parent package").
    # Make the bundled `tray` package importable and use absolute imports.
    import os as _os
    import sys as _sys

    _here = _os.path.dirname(_os.path.abspath(__file__))
    for _candidate in (
        _here,  # source checkout: <root>/tray/app.py -> <root>
        _os.path.dirname(_here),  # frozen: <_MEIPASS>/tray/app.py -> <_MEIPASS>
    ):
        if _os.path.isdir(_os.path.join(_candidate, "tray")) and _candidate not in _sys.path:
            _sys.path.insert(0, _candidate)
    del _os, _sys, _here, _candidate

from tray.icon import make_icon
from tray.util import (
    dashboard_url,
    find_free_port,
    resource_path,
    wait_for_port,
    yesterday_str,
)

APP_NAME = "Copilot Usage"


def _log(message: str) -> None:
    """Best-effort stderr logging for the tray process (no log infra here)."""
    with contextlib.suppress(Exception):  # logging must never crash the tray
        print(f"[{APP_NAME}] {message}", file=sys.stderr, flush=True)


def _log_file_path() -> str | None:
    """Where the tray app writes its startup log (for support & smoke tests)."""
    try:
        from copilot_usage_tracker import appconfig

        return os.path.join(appconfig.data_dir(), "tray.log")
    except Exception:  # noqa: BLE001 - logging must never crash the tray
        return None


def _flog(message: str) -> None:
    """Append a timestamped milestone to the tray log file (best effort)."""
    path = _log_file_path()
    if path is None:
        return
    with contextlib.suppress(Exception):
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{ts} {message}\n")


def _configured() -> bool:
    try:
        from copilot_usage_tracker import appconfig

        return appconfig.is_configured()
    except Exception:  # noqa: BLE001 - fail open: dashboard shows setup anyway
        return False


class TrayApp:
    def __init__(self) -> None:
        self.port = find_free_port()
        self.url = dashboard_url(self.port)
        self.server: subprocess.Popen | None = None
        self.window = None
        self._icon = None

    # -- local dashboard server ----------------------------------------
    def _server_command(self) -> list[str]:
        script = resource_path(os.path.join("dashboard", "app.py"))
        args = [
            "run",
            script,
            # Streamlit thinks any install outside site-packages is a dev
            # checkout and enables developmentMode (which rejects
            # --server.port). A frozen bundle is never a checkout.
            "--global.developmentMode",
            "false",
            "--server.port",
            str(self.port),
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ]
        if getattr(sys, "frozen", False):
            # Frozen: PyInstaller's bootloader does not implement `-m`, so
            # `sys.executable -m streamlit` would re-launch this tray app
            # itself. The specs bundle a dedicated `dashboard-server`
            # executable next to the tray binary -- exec that instead.
            exe_dir = os.path.dirname(sys.executable)
            name = "dashboard-server.exe" if os.name == "nt" else "dashboard-server"
            return [os.path.join(exe_dir, name), *args]
        return [sys.executable, "-m", "streamlit", *args]

    def start_server(self) -> None:
        env = dict(os.environ)
        # Defense in depth: no Streamlit telemetry, even if flags change.
        env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
        cmd = self._server_command()
        _flog(f"starting dashboard server: {os.path.basename(cmd[0])} (port {self.port})")
        # Keep the server's output in a file (not DEVNULL): if the dashboard
        # ever fails to come up, this is what support -- and the smoke test
        # -- reads to find out why.
        server_log = os.path.join(os.path.dirname(_log_file_path() or "."), "dashboard-server.log")
        _flog(f"dashboard server output -> {server_log}")
        with open(server_log, "a", encoding="utf-8") as log_fh:
            self.server = subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT, env=env)
        # Popen dup'ed the handle for the child; closing ours is safe.
        wait_for_port(self.port, timeout=150)
        _flog(f"dashboard server up on 127.0.0.1:{self.port}")

    def stop_server(self) -> None:
        if self.server is not None and self.server.poll() is None:
            self.server.terminate()

    # -- popup window ---------------------------------------------------
    def _ensure_window(self):
        import webview

        if self.window is None or self.window not in webview.windows:
            self.window = webview.create_window(
                APP_NAME, self.url, width=1120, height=780, hidden=True
            )
            # Hide instead of closing so the tray icon stays alive.
            # Returning False from a `closing` handler cancels the close.
            self.window.events.closing += self._on_closing
        return self.window

    def _on_closing(self):
        try:
            self.window.hide()
        except Exception as exc:  # noqa: BLE001 - best effort; recreate on next open
            _log(f"hide on close failed: {exc}")
        return False

    def show_dashboard(self, *_) -> None:
        try:
            window = self._ensure_window()
            window.show()
            _flog("dashboard window shown")
            try:
                window.restore()
            except Exception as exc:  # noqa: BLE001 - not all backends support restore
                _log(f"window restore failed: {exc}")
        except Exception:  # noqa: BLE001 - webview broken/missing: use browser
            _flog("webview unavailable, opening dashboard in browser")
            webbrowser.open(self.url)

    # -- tray actions ----------------------------------------------------
    def collect_latest(self, *_) -> None:
        def _run() -> None:
            try:
                from copilot_usage_tracker import appconfig
                from copilot_usage_tracker.sync import run_collection, summary_line

                cfg = appconfig.load_app_config()
                summary = run_collection(yesterday_str(), with_teams=cfg.with_teams)
                self._notify(summary_line(summary))
            except Exception as exc:  # noqa: BLE001 - surface to the user
                self._notify(f"Collection failed: {exc}")

        threading.Thread(target=_run, daemon=True, name="collect").start()
        self._notify("Collecting latest usage data…")

    def _auto_collect_loop(self) -> None:
        """Background collection on the GUI-configured interval.

        Keeps the dashboard fresh without clicks: every
        ``auto_collect_hours`` the tray app pulls yesterday's reports.
        ``0`` (or unconfigured scope) disables the loop. Failures notify
        once per cycle and never kill the thread.
        """
        import time

        from copilot_usage_tracker import appconfig
        from copilot_usage_tracker.sync import run_collection, summary_line

        while True:
            try:
                cfg = appconfig.load_app_config()
                hours = float(cfg.auto_collect_hours or 0)
            except Exception as exc:  # noqa: BLE001 - config unreadable
                _log(f"auto-collect config unreadable: {exc}")
                hours = 0
            if hours <= 0 or not appconfig.is_configured(cfg):
                _log("auto-collect idle (disabled or not configured)")
                time.sleep(3600)
                continue
            _log(f"auto-collect sleeping {hours}h")
            time.sleep(hours * 3600)
            try:
                cfg = appconfig.load_app_config()
                summary = run_collection(yesterday_str(), with_teams=cfg.with_teams)
                self._notify("Auto-collect: " + summary_line(summary))
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                _log(f"auto-collect failed: {exc}")

    def _notify(self, message: str) -> None:
        try:
            if self._icon is not None:
                self._icon.notify(message, APP_NAME)
        except Exception as exc:  # noqa: BLE001 - notifications are best effort
            _log(f"notification failed: {exc}")

    def quit_app(self, *_) -> None:
        try:
            if self._icon is not None:
                self._icon.stop()
        finally:
            try:
                if self.window is not None:
                    self.window.destroy()
            except Exception as exc:  # noqa: BLE001 - shutting down anyway
                _log(f"window destroy failed: {exc}")

    # -- main loop --------------------------------------------------------
    def run(self) -> None:
        import pystray

        self.start_server()
        menu = pystray.Menu(
            pystray.MenuItem("Open dashboard", self.show_dashboard, default=True),
            pystray.MenuItem("Collect latest data", self.collect_latest),
            pystray.MenuItem("Open in browser", lambda *_: webbrowser.open(self.url)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.quit_app),
        )
        self._icon = pystray.Icon(APP_NAME, make_icon(), APP_NAME, menu)
        threading.Thread(target=self._icon.run, daemon=True, name="tray-icon").start()
        threading.Thread(target=self._auto_collect_loop, daemon=True, name="auto-collect").start()

        import webview

        self._ensure_window()
        if not _configured():
            # First run: pop the setup page so the user never needs a terminal.
            self.show_dashboard()
        webview.start()
        # webview.start() returns after the window is destroyed (Quit)
        self.stop_server()


def main() -> None:
    _flog("tray starting")
    try:
        TrayApp().run()
    except BaseException:
        _flog("fatal:\n" + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
