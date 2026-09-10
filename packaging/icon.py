"""Render installer icons (.ico / .icns / .png) from the tray glyph.

Run:  python packaging/icon.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from tray.icon import make_icon


def main() -> None:
    assets = os.path.join(os.path.dirname(__file__), "assets")
    os.makedirs(assets, exist_ok=True)
    img = make_icon(1024)
    img.save(os.path.join(assets, "icon.png"))
    img.save(
        os.path.join(assets, "icon.ico"),
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    img.save(os.path.join(assets, "icon.icns"))
    print(f"wrote icons to {assets}")


if __name__ == "__main__":
    main()
