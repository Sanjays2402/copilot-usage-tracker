"""Capture a specific dashboard tab in the real pywebview desktop window.

Usage: DISPLAY=:99 python capture_tab.py <url> <tab_name> <out.png>
"""
import os
import sys
import threading
import time

URL = sys.argv[1]
TAB = sys.argv[2]
OUT = sys.argv[3]

import webview  # noqa: E402

CLICK_JS = """
(() => {
  const tabs = [...document.querySelectorAll('div[data-testid="stTab"]')];
  const t = tabs.find(b => (b.innerText || '').trim() === %r);
  if (t) { t.click(); return 'clicked ' + %r; }
  return 'tab not found; saw: ' + tabs.map(b => (b.innerText || '').trim()).join('|');
})()
""" % (TAB, TAB)


def _flow(window):
    time.sleep(10)  # let Streamlit boot
    try:
        result = window.evaluate_js(CLICK_JS)
        print(f"js: {result}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"js failed: {exc!r}", flush=True)
    time.sleep(10)  # let charts render
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
window.events.loaded += lambda: threading.Thread(target=_flow, args=(window,), daemon=True).start()
webview.start(gui="qt")
