# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Draw an icon from a TrueType font and print it as text.

Opens a font file with ``ttfio.Font``, asks where one glyph lands at a
size, draws it as an 8-bit coverage mask and prints the mask with one
character per pixel, darker characters for more ink. Then it draws the
same icon into a buffer of your own, which allocates nothing. Success is
a settings gear you can recognise, drawn in dots and hashes.

Needs: a MicroPython firmware built with ttfio (``--modules ttfio`` or
``all``), or CPython with omnipython-desktop. The font is
``tests/data/icons20.ttf`` from this module, ten Material Symbols icons;
any TrueType font works if you change ``CHAR`` to one of its characters.

Run it:

    mpremote cp ../tests/data/icons20.ttf :
    mpremote run ttfio_simpletest.py

Tested on: the MicroPython unix port v1.30.0-preview.160 built with
``--modules ttfio,icons``, and CPython 3.12 on Linux with
omnipython-desktop's ttfio over freetype-py.
"""

import ttfio

# Change these to match your setup.
FONT = "icons20.ttf"
CHAR = 0xE8B8  # a character or a codepoint: here the "settings" icon
SIZE = 20  # the em size in pixels

# Open the font. Its bytes stay where they are; ttfio reads them in place.
with open(FONT, "rb") as f:
    font = ttfio.Font(f.read())
ascent, descent, line_gap = font.metrics(SIZE)
print("%d units per em; at %d px ascent %d, descent %d" % (font.units_per_em, SIZE, ascent, descent))

# Ask where the glyph lands: its box, the box's corner from the pen on
# the baseline, and how far the pen moves after it.
w, h, x, y, advance = font.glyph(CHAR, SIZE)
print("glyph 0x%X: %dx%d at (%d, %d), advance %d" % (CHAR, w, h, x, y, advance))

# Draw it as coverage, 0 to 255 for each pixel, and print it row by row.
mask = font.render(CHAR, SIZE)
for row in range(h):
    print("".join(" .:#"[v // 64] for v in mask[row * w : row * w + w]))

# Draw it again into a buffer you made, as a program redrawing every frame
# would. The ink should match the first drawing.
buf = bytearray(w * h)
font.render(CHAR, SIZE, buf)
print("Same drawing: %s; %d pixels of ink" % (buf == mask, sum(mask) // 255))
