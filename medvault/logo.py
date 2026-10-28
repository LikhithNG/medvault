#!/usr/bin/env python3
"""The mark.

One shape, used at five sizes: 19px in a navigation rail, 30px in an app bar, 44px on a
landing page, 180px on a phone's home screen, 512px in an install prompt. It is a shield
with the cross cut *out* of it rather than drawn on top, which is the only version that
survives being twenty pixels wide — a cross drawn in a second colour turns to mush at that
size, a hole does not.

The geometry lives here as numbers rather than in an .svg file so that the inline SVG, the
CSS mask and the PNG home-screen icons are the same shape by construction rather than by
somebody remembering to re-export. tools/make_icons.py reads these same constants.
"""
from urllib.parse import quote

ACCENT = "#0F6FDE"
ACCENT_BRIGHT = "#3B8CFF"
ACCENT_DEEP = "#0A4E9E"
INK = "#0B1220"

BOX = 48.0  # everything below is in a 48x48 box

# The shield, as the segments it is actually made of. Flat top with two softened corners,
# straight shoulders, and a single curve down each side into a point — a vault door rather
# than a heraldic crest. This list is the source of truth: the SVG path string below is
# generated from it, and tools/make_icons.py samples the same curves to draw the PNGs, so
# the inline mark and the home-screen icon cannot drift apart.
SHIELD_SEGMENTS = (
    ("M", (24.0, 3.4)),
    ("L", (39.1, 9.1)),
    ("Q", (40.4, 9.6), (40.4, 11.0)),
    ("L", (40.4, 24.3)),
    ("C", (40.4, 33.4), (33.6, 41.0), (24.0, 44.6)),
    ("C", (14.4, 41.0), (7.6, 33.4), (7.6, 24.3)),
    ("L", (7.6, 11.0)),
    ("Q", (7.6, 9.6), (8.9, 9.1)),
    ("Z",),
)


def _d(segments):
    out = []
    for seg in segments:
        cmd, pts = seg[0], seg[1:]
        out.append(cmd + " ".join(f"{x:g} {y:g}" for x, y in pts))
    return " ".join(out)


def _bezier(points, steps):
    """de Casteljau, so a quadratic and a cubic go through the same code path."""
    for i in range(1, steps + 1):
        t = i / steps
        cur = list(points)
        while len(cur) > 1:
            cur = [(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
                   for a, b in zip(cur, cur[1:])]
        yield cur[0]


def shield_points(steps=26):
    """The shield outline as a polygon, for a rasteriser that has no path support."""
    pts, here = [], (0.0, 0.0)
    for seg in SHIELD_SEGMENTS:
        cmd, args = seg[0], seg[1:]
        if cmd == "M":
            here = args[0]
            pts.append(here)
        elif cmd == "L":
            here = args[0]
            pts.append(here)
        elif cmd in ("Q", "C"):
            pts.extend(_bezier((here,) + args, steps))
            here = args[-1]
        elif cmd == "Z":
            break
    return pts


SHIELD = _d(SHIELD_SEGMENTS)

# The cross, as two rounded bars crossing at (24, 23) — a shade above the middle of the
# box, because the shield's point drags its visual centre downwards.
CROSS_V = (21.0, 14.0, 6.0, 18.0, 3.0)   # x, y, w, h, radius
CROSS_H = (15.0, 20.0, 18.0, 6.0, 3.0)

_CROSS_RECTS = (
    '<rect x="{0}" y="{1}" width="{2}" height="{3}" rx="{4}" fill="black"/>'.format(*CROSS_V)
    + '<rect x="{0}" y="{1}" width="{2}" height="{3}" rx="{4}" fill="black"/>'.format(*CROSS_H)
)


def _mask(uid):
    """White shield, black cross: the cross becomes a hole in whatever the mask is over."""
    return (f'<mask id="mvm{uid}" maskUnits="userSpaceOnUse" x="0" y="0" '
            f'width="48" height="48">'
            f'<rect width="48" height="48" fill="black"/>'
            f'<path d="{SHIELD}" fill="white"/>{_CROSS_RECTS}</mask>')


def _gradient(uid, a=ACCENT_BRIGHT, b=ACCENT_DEEP):
    return (f'<linearGradient id="mvg{uid}" x1="0" y1="0" x2="1" y2="1">'
            f'<stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/>'
            f'</linearGradient>')


def mark(size=30, uid="a", fill="gradient"):
    """The shield on its own, transparent behind it.

    fill="gradient" for a light background, "white" for a dark one, "mono" to take the
    colour of the surrounding text (used in the footer, where the mark should recede).
    """
    paint = {"gradient": f"url(#mvg{uid})", "white": "#FFFFFF",
             "mono": "currentColor"}.get(fill, f"url(#mvg{uid})")
    defs = _mask(uid) + (_gradient(uid) if fill == "gradient" else "")
    return (f'<svg class="mvmark" width="{size}" height="{size}" viewBox="0 0 48 48" '
            f'fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
            f'<defs>{defs}</defs>'
            f'<rect width="48" height="48" fill="{paint}" mask="url(#mvm{uid})"/></svg>')


def tile(size=48, uid="t", radius=11.0):
    """The app-icon lockup: a filled tile with the shield in white and the cross cut
    through it, so the tile's own gradient shows through the hole."""
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 48 48" '
            f'xmlns="http://www.w3.org/2000/svg" aria-hidden="true">'
            f'<defs>{_gradient(uid)}{_mask(uid)}</defs>'
            f'<rect width="48" height="48" rx="{radius}" fill="url(#mvg{uid})"/>'
            f'<rect width="48" height="48" fill="#FFFFFF" mask="url(#mvm{uid})"/></svg>')


def data_uri(svg):
    """For CSS. Percent-encoded rather than base64 so the shape stays readable in the
    stylesheet and a wrong character shows up as a wrong character."""
    return "data:image/svg+xml," + quote(svg, safe="")


def css_url(svg):
    return f'url("{data_uri(svg)}")'


def wordmark(size=19, uid="w", ink=INK, accent=ACCENT):
    """Mark plus name. The name is live text, not an outline: it picks up Inter from the
    page, stays selectable, and is read aloud by a screen reader."""
    # The size goes on the name itself. It was a custom property on the wrapper, which
    # Streamlit's markdown renderer drops from inline styles, so every lockup was 19px.
    return (f'<span class="mvlockup">'
            f'{mark(size=round(size * 1.75), uid=uid)}'
            f'<span class="mvname" style="color:{ink};font-size:{size}px">Med'
            f'<span style="color:{accent}">Vault</span></span></span>')
