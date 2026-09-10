"""Programmatic tray icon (no binary assets to ship)."""

from __future__ import annotations

from PIL import Image, ImageDraw

SIZE = 64


def make_icon(size: int = SIZE) -> Image.Image:
    """Render a small bar-chart glyph on a dark rounded square."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = size // 8
    d.rounded_rectangle(
        [pad // 2, pad // 2, size - pad // 2, size - pad // 2],
        radius=size // 6,
        fill=(17, 24, 39, 255),
    )
    bar_w = size // 10
    for x_frac, top_frac in ((0.28, 0.58), (0.44, 0.42), (0.60, 0.26)):
        x = int(size * x_frac)
        d.rectangle(
            [x, int(size * top_frac), x + bar_w, size - pad],
            fill=(45, 212, 191, 255),
        )
    return img
