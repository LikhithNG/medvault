#!/usr/bin/env python3
"""Draw the home-screen icons from the same geometry the inline mark uses.

Run from the project root:  python3 tools/make_icons.py

There is no SVG rasteriser in this project's dependencies and adding one for four files
would be silly, so this samples medvault/logo.py's own curves and fills them with Pillow,
which is already a dependency. The point of reading logo.py rather than keeping a second
copy of the shape is that the icon on a phone's home screen and the mark in the app bar
stay the same drawing when either one changes.
"""
import pathlib
import sys

from PIL import Image, ImageChops, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "medvault"))
import logo  # noqa: E402

SS = 4                      # supersample, then LANCZOS down: no jagged shield edge
OUT = ROOT / "static"
TILE_RADIUS = 0.2237        # the proportion iOS and Android both round a tile by


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def gradient(size, top_left, bottom_right):
    """A diagonal wash. Drawn per-pixel-row-and-column rather than with a library so the
    512px icon and the 180px one are the same gradient, not two different approximations."""
    a, b = _hex(top_left), _hex(bottom_right)
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return img


def _place(size, frac):
    """Where the 48-unit box sits inside an icon of this size, at this fraction of it."""
    k = size * frac / logo.BOX
    off = (size - logo.BOX * k) / 2
    return k, off


def shield_mask(size, frac):
    """White shield with the cross punched out of it."""
    k, off = _place(size, frac)
    shield = Image.new("L", (size, size), 0)
    ImageDraw.Draw(shield).polygon(
        [(x * k + off, y * k + off) for x, y in logo.shield_points(steps=64)], fill=255)

    cross = Image.new("L", (size, size), 0)
    pen = ImageDraw.Draw(cross)
    for x, y, w, h, r in (logo.CROSS_V, logo.CROSS_H):
        pen.rounded_rectangle(
            [x * k + off, y * k + off, (x + w) * k + off, (y + h) * k + off],
            radius=r * k, fill=255)
    return ImageChops.subtract(shield, cross)


def rounded_mask(size, radius):
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def icon(size, frac=0.68, rounded=True):
    """Gradient tile, white shield, and the cross showing the gradient through the hole."""
    big = size * SS
    img = gradient(big, logo.ACCENT_BRIGHT, logo.ACCENT_DEEP).convert("RGBA")
    img.paste(Image.new("RGBA", (big, big), (255, 255, 255, 255)),
              (0, 0), shield_mask(big, frac))
    if rounded:
        img.putalpha(rounded_mask(big, round(big * TILE_RADIUS)))
    return img.resize((size, size), Image.LANCZOS)


def main():
    OUT.mkdir(exist_ok=True)
    made = [
        ("icon-192.png", icon(192)),
        ("icon-512.png", icon(512)),
        # Apple rounds the touch icon itself, and a transparent corner under that rounding
        # shows as black, so this one is square and opaque.
        ("icon-180.png", icon(180, rounded=False).convert("RGB")),
        # A maskable icon can be cropped to a circle by the launcher, so the shield sits
        # inside the 80% safe zone and the gradient runs to all four edges.
        ("icon-maskable-512.png", icon(512, frac=0.50, rounded=False)),
    ]
    for name, img in made:
        img.save(OUT / name)
        print(f"{name:26} {img.size[0]}x{img.size[1]}  {(OUT / name).stat().st_size:>7,} bytes")


if __name__ == "__main__":
    main()
