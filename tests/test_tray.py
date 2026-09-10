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
