"""Tests for the tray app's GUI-free helpers."""

import re
import socket

import pytest

from tray.icon import SIZE, make_icon
from tray.util import (
    dashboard_url,
    find_free_port,
    resource_path,
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
