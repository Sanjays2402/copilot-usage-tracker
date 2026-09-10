"""Console entry point for the bundled dashboard server (frozen desktop apps).

The tray app cannot start its Streamlit server with
``sys.executable -m streamlit`` when frozen: PyInstaller's bootloader does
not implement ``-m`` and would simply re-launch the tray app itself with
``-m`` in argv (an infinite self-spawn). The PyInstaller specs therefore
bundle this module as a separate ``dashboard-server`` executable placed next
to the tray binary, and ``TrayApp.start_server()`` execs it when frozen.

Not used in normal (unfrozen) runs: there the tray app shells out to
``sys.executable -m streamlit`` directly.
"""

from __future__ import annotations

import sys


def main() -> None:
    from streamlit.web import cli as stcli

    # streamlit's CLI reads sys.argv: ["dashboard-server", "run", <script>, ...]
    sys.argv[0] = "dashboard-server"
    stcli.main()


if __name__ == "__main__":
    main()
