"""Small pure helpers for the tray app (kept GUI-free so they're testable)."""

from __future__ import annotations

import os
import socket
import sys
import time
from datetime import date, timedelta

DEFAULT_PORT = 8501


def resource_path(relative: str) -> str:
    """Resolve a repo-relative path, PyInstaller-bundle aware."""
    base = getattr(sys, "_MEIPASS", None)
    if base is None:
        base = os.path.join(os.path.dirname(__file__), "..")
    return os.path.join(base, relative)


def find_free_port(preferred: int = DEFAULT_PORT) -> int:
    """Return `preferred` if free, else an OS-assigned ephemeral port."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", preferred))
        return preferred
    except OSError:
        sock.close()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        return port
    finally:
        try:
            sock.close()
        except OSError:
            pass


def wait_for_port(port: int, timeout: float = 60.0) -> None:
    """Block until something accepts TCP on 127.0.0.1:port."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.25)
    raise TimeoutError(f"nothing listening on 127.0.0.1:{port} after {timeout}s")


def dashboard_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def yesterday_str() -> str:
    # Local calendar day: "latest data" means yesterday where the user sits.
    return (date.today() - timedelta(days=1)).isoformat()  # noqa: DTZ011
