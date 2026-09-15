"""Capture the real pywebview desktop window ("Copilot Usage") under Xvfb.

Usage: DISPLAY=:99 python capture_window.py <url> <out.png> [wait_secs]
"""
import os
import sys
import threading
import time

URL = sys.argv[1]
OUT = sys.argv[2]
WAIT = float(sys.argv[3]) if len(sys.argv) > 3 else 14.0

import webview  # noqa: E402


def _shoot_and_exit():
    time.sleep(WAIT)
    try:
        from mss import mss

        with mss() as sct:
            sct.shot(output=OUT)
        print(f"saved {OUT}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"screenshot failed: {exc!r}", flush=True)
    finally:
        os._exit(0)


window = webview.create_window("Copilot Usage", URL, width=1200, height=800)
window.events.loaded += lambda: threading.Thread(target=_shoot_and_exit, daemon=True).start()
webview.start(gui="qt")
