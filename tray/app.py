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
import webbrowser
from pathlib import Path

from .icon import make_icon
from .util import dashboard_url, find_free_port, resource_path, wait_for_port, yesterday_str

APP_NAME = "Copilot Usage"


def _log(message: str) -> None:
    """Best-effort stderr logging for the tray process (no log infra here)."""
    with contextlib.suppress(Exception):  # logging must never crash the tray
        print(f"[{APP_NAME}] {message}", file=sys.stderr, flush=True)


def _default_db() -> str:
    data_dir = Path.home() / ".copilot-usage-tracker"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "copilot_usage.db")


class TrayApp:
    def __init__(self) -> None:
        os.environ.setdefault("COPILOT_DB", _default_db())
        self.port = find_free_port()
        self.url = dashboard_url(self.port)
        self.server: subprocess.Popen | None = None
        self.window = None
        self._icon = None

    # -- local dashboard server ----------------------------------------
    def start_server(self) -> None:
        cmd = [
            sys.executable, "-m", "streamlit", "run",
            resource_path("dashboard/app.py"),
            "--server.port", str(self.port),
            "--server.headless", "true",
            "--browser.gatherUsageStats", "false",
        ]
        self.server = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        wait_for_port(self.port, timeout=90)

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
            try:
                window.restore()
            except Exception as exc:  # noqa: BLE001 - not all backends support restore
                _log(f"window restore failed: {exc}")
        except Exception:  # noqa: BLE001 - webview broken/missing: use browser
            webbrowser.open(self.url)

    # -- tray actions ----------------------------------------------------
    def collect_latest(self, *_) -> None:
        def _run() -> None:
            day = yesterday_str()
            try:
                subprocess.run(
                    [sys.executable, "-m", "copilot_usage_tracker.cli",
                     "collect", "--day", day, "--with-teams"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=900, check=False,
                )
                self._notify(f"Collection for {day} finished.")
            except Exception as exc:  # noqa: BLE001 - surface to the user
                self._notify(f"Collection failed: {exc}")

        threading.Thread(target=_run, daemon=True, name="collect").start()
        self._notify("Collecting latest usage data…")

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

        import webview

        self._ensure_window()
        webview.start()
        # webview.start() returns after the window is destroyed (Quit)
        self.stop_server()


def main() -> None:
    TrayApp().run()


if __name__ == "__main__":
    main()
