# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Compares ttfio's masks with FreeType's drawing of the same icons, on the PC.

    python check_ttfio_freetype.py DIR

DIR holds the .mask files test_ttfio.py wrote with --out. Each is set beside
FreeType's unhinted drawing at the same size. FreeType is the reference
because it is what desktop font stacks draw with; unhinted, because ttfio
does not hint (a hinted FreeType draws this font a pixel taller and about 8 %
bolder). Bars:

- ttfio's box is FreeType's, give or take a pixel on a side;
- the two hold the same ink, within 3 %;
- every pixel that differs by more than a tenth lies on an edge of
  FreeType's drawing (within a pixel of one that is neither empty nor full).

Needs numpy and freetype-py.
"""

import os
import sys

import freetype
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(HERE, "data", "icons20.ttf")
ICONS = {
    "wifi": 0xE63E,
    "bluetooth": 0xE1A7,
    "battery_full": 0xE1A5,
    "volume_up": 0xE050,
    "settings": 0xE8B8,
    "home": 0xE9B2,
    "close": 0xE5CD,
    "check": 0xE668,
    "search": 0xEF7A,
    "mic": 0xE31D,
}


def signed(b):
    return b - 256 if b > 127 else b


def canvas(px, w, h, x, y, pixels):
    """The drawing on a canvas twice the em, pen at (px/2, 1.5*px)."""
    c = np.zeros((px * 2, px * 2), np.float64)
    ox, oy = px // 2 + x, px * 3 // 2 + y
    c[oy:oy + h, ox:ox + w] = pixels
    return c


def main(out):
    face = freetype.Face(FONT)
    failures = 0
    for name, cp in sorted(ICONS.items()):
        for px in (20, 40):
            raw = open(os.path.join(out, "%s_%d.mask" % (name, px)), "rb").read()
            w, h, x, y = raw[0], raw[1], signed(raw[2]), signed(raw[3])
            a = canvas(px, w, h, x, y, np.frombuffer(raw[4:], np.uint8).reshape(h, w) / 255.0)
            face.set_pixel_sizes(px, px)
            face.load_char(chr(cp), freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
            g = face.glyph
            b = g.bitmap
            fw, fh, fx, fy = b.width, b.rows, g.bitmap_left, -g.bitmap_top
            ft = np.array(b.buffer, np.uint8).reshape(fh, b.pitch)[:, :fw]
            p = canvas(px, fw, fh, fx, fy, ft / 255.0)
            box = max(abs(x - fx), abs(y - fy), abs(x + w - fx - fw), abs(y + h - fy - fh))
            ink = abs(a.sum() - p.sum()) / p.sum()
            partial = (p > 0.02) & (p < 0.98)
            near = np.zeros_like(partial)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    near |= np.roll(np.roll(partial, dy, 0), dx, 1)
            stray = (np.abs(a - p) > 0.1) & ~near
            ok = box <= 1 and ink < 0.03 and not stray.any()
            failures += not ok
            print("%s  %-13s %2d px  box off %d  ink off %.1f %%  off-edge pixels %d" % ("ok  " if ok else "FAIL", name, px, box, ink * 100, stray.sum()))
    print("%d failed" % failures if failures else "all passed")
    return failures


if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1]) else 0)
