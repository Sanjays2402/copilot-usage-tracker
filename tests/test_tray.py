"""Tests for the tray app's GUI-free helpers."""

import re
import socket

import pytest

from tray.icon import SIZE, make_icon
from tray.util import (
    dashboard_url,
    find_free_port,
    resource_path,
    wait_for_http_ok,
    wait_for_port,
    yesterday_str,
)


def test_make_icon():
    img = make_icon()
    assert img.size == (SIZE, SIZE)
    assert img.mode == "RGBA"
    # not fully transparent: the rounded square was drawn
    assert any(px[3] > 0 for px in img.getdata())


def test_find_free_port_bindable():
    port = find_free_port()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))  # proves the port was actually free
    finally:
        sock.close()


def test_dashboard_url():
    assert dashboard_url(8501) == "http://127.0.0.1:8501"


def test_yesterday_str():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", yesterday_str())


def test_resource_path_repo_layout(tmp_path, monkeypatch):
    monkeypatch.delattr("sys._MEIPASS", raising=False)
    p = resource_path("dashboard/app.py")
    assert p.endswith("dashboard/app.py")


def test_wait_for_port_timeout():
    # Port 1 is privileged; nothing should accept there.
    with pytest.raises(TimeoutError):
        wait_for_port(1, timeout=0.5)


def test_wait_for_port_success():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    try:
        wait_for_port(srv.getsockname()[1], timeout=5)
    finally:
        srv.close()


def test_server_command_unfrozen_uses_module_flag():
    import sys as _sys

    from tray.app import TrayApp

    cmd = TrayApp()._server_command()
    assert cmd[0] == _sys.executable
    assert cmd[1:3] == ["-m", "streamlit"]
    assert cmd[3] == "run"
    # Frozen or not, developmentMode must stay off: Streamlit enables it
    # whenever it isn't running from site-packages, and it rejects
    # --server.port in dev mode.
    assert "--global.developmentMode" in cmd
    assert cmd[cmd.index("--global.developmentMode") + 1] == "false"


def test_server_command_frozen_uses_bundled_binary(monkeypatch, tmp_path):
    """Frozen apps must NOT use `sys.executable -m streamlit`: PyInstaller's
    bootloader ignores `-m` and would re-launch the tray app itself."""
    import os as _os
    import sys as _sys

    from tray.app import TrayApp

    fake_exe = str(tmp_path / "copilot-usage-tray")
    monkeypatch.setattr(_sys, "frozen", True, raising=False)
    monkeypatch.setattr(_sys, "executable", fake_exe)
    cmd = TrayApp()._server_command()
    expected = "dashboard-server.exe" if _os.name == "nt" else "dashboard-server"
    assert cmd[0] == str(tmp_path / expected)
    assert cmd[1] == "run"
    assert "-m" not in cmd


def test_run_dashboard_entry_importable():
    from tray import run_dashboard

    assert callable(run_dashboard.main)


def test_ensure_streamlit_version_fallback(monkeypatch):
    """If package metadata is missing (frozen bundle without dist-info),
    run_dashboard injects streamlit.version instead of crashing."""
    import importlib.metadata as md
    import sys as _sys

    from tray import run_dashboard

    def _boom(name):
        raise md.PackageNotFoundError(name)

    monkeypatch.setattr(md, "version", _boom)
    monkeypatch.delitem(_sys.modules, "streamlit.version", raising=False)
    run_dashboard._ensure_streamlit_version()
    assert _sys.modules["streamlit.version"].STREAMLIT_VERSION_STRING == "0.0.0+frozen"


def test_init_webview_missing_falls_back(monkeypatch):
    """No webview installed -> _init_webview False, no exception."""
    import sys as _sys

    from tray.app import TrayApp

    monkeypatch.setitem(_sys.modules, "webview", None)  # import raises ImportError
    assert TrayApp()._init_webview() is False


def test_init_webview_ok(monkeypatch):
    import sys as _sys
    import types

    from tray.app import TrayApp

    fake = types.ModuleType("webview")
    fake.windows = []

    class FakeEvent:
        def __init__(self):
            self.handlers = []

        def __iadd__(self, handler):
            self.handlers.append(handler)
            return self

    class FakeWindow:
        def __init__(self):
            self.events = types.SimpleNamespace(closing=FakeEvent())

    def create_window(*_a, **_k):
        w = FakeWindow()
        fake.windows.append(w)
        return w

    fake.create_window = create_window
    monkeypatch.setitem(_sys.modules, "webview", fake)
    app = TrayApp()
    assert app._init_webview() is True
    assert app._webview_ok is True
    assert app.window is not None


def test_show_dashboard_browser_fallback(monkeypatch):
    import webbrowser

    from tray.app import TrayApp

    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))
    app = TrayApp()
    app._webview_ok = False
    app.show_dashboard()
    assert opened == [app.url]


def _serve_health(body: bytes, status: int = 200):
    """Run a one-shot HTTP server answering /_stcore/health; return its port."""
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def test_wait_for_http_ok_success():
    srv, port = _serve_health(b"ok")
    try:
        wait_for_http_ok(port, timeout=10)
    finally:
        srv.shutdown()


def test_wait_for_http_ok_wrong_body():
    srv, port = _serve_health(b"starting")
    try:
        with pytest.raises(TimeoutError):
            wait_for_http_ok(port, timeout=2)
    finally:
        srv.shutdown()


def test_wait_for_http_ok_nothing_listening():
    port = find_free_port()
    with pytest.raises(TimeoutError):
        wait_for_http_ok(port, timeout=2)
