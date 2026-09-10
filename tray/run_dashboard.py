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


def _ensure_streamlit_version() -> None:
    """Let `import streamlit` succeed without installed package metadata.

    `streamlit.version` calls `importlib.metadata.version("streamlit")` at
    import time. The specs collect the dist-info explicitly (see
    `copy_metadata("streamlit")`), but if it is ever missing from a frozen
    bundle, inject the version module directly so the dashboard still
    starts instead of dying with PackageNotFoundError.
    """
    try:
        import importlib.metadata as _md

        _md.version("streamlit")
    except Exception:  # noqa: BLE001 - any metadata failure -> fallback below
        import types

        version_mod = types.ModuleType("streamlit.version")
        version_mod.STREAMLIT_VERSION_STRING = "0.0.0+frozen"
        sys.modules["streamlit.version"] = version_mod


def main() -> None:
    _ensure_streamlit_version()
    from streamlit.web import cli as stcli

    # streamlit's CLI reads sys.argv: ["dashboard-server", "run", <script>, ...]
    sys.argv[0] = "dashboard-server"
    stcli.main()


if __name__ == "__main__":
    main()
