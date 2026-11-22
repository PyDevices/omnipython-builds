# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Draw a row of icons from a TrueType font on the display.

Draws every icon in ``icons20.ttf`` at one size, side by side on a
baseline, the way a line of text is set: each glyph's mask is placed from
the pen by its offset, blended in a colour into a pygraphics framebuffer
with ``blit_alpha``, and the pen moves on by the glyph's advance. The
strip then goes onto the display in one copy. Success is ten icons
(Wi-Fi, Bluetooth, battery, volume, settings, home, close, check, search
and a microphone) in a band across the screen, softly edged.

Needs: a board_config with a display_drv, which an OmniPython board
package or omnipython-desktop provides, pygraphics with
``FrameBuffer.blit_alpha``, and ttfio (built into the firmware with
``--modules ttfio`` or ``all``, or omnipython-desktop's on CPython). Copy
``tests/data/icons20.ttf`` from this module next to the example.

Run it:

    mpremote cp ../tests/data/icons20.ttf :
    mpremote run ttfio_display.py

Tested on: the MicroPython unix port v1.30.0-preview.160 built with
``--modules ttfio,icons``, and CPython 3.12 on Linux with pygraphics 0.2, each
through the desktop board_config in an SDL window.
"""

import time

import ttfio
from board_config import display_drv
from pygraphics import RGB565, FrameBuffer

# Change these to match your setup.
FONT = "icons20.ttf"
CODES = (0xE63E, 0xE1A7, 0xE1A5, 0xE050, 0xE8B8, 0xE9B2, 0xE5CD, 0xE668, 0xEF7A, 0xE31D)
COLORS = (0x07FF, 0xFFE0, 0x07E0, 0xF81F)  # RGB565, used in turn
BACKGROUND = 0x0010  # dark blue
SECONDS = 10

with open(FONT, "rb") as f:
    font = ttfio.Font(f.read())

# Pick the largest size at which the whole row fits across the display,
# and make a strip one line high to draw it in.
width = display_drv.width
size = width * 20 // (20 * len(CODES) + 8)
ascent, descent, line_gap = font.metrics(size)
strip_height = ascent - descent
pixels = bytearray(width * strip_height * 2)
strip = FrameBuffer(pixels, width, strip_height, RGB565)
strip.fill(BACKGROUND)

# Set the icons on the baseline like text. Each mask's corner is measured
# from the pen, so the pen walks along the baseline by each advance.
pen = (width - sum(font.glyph(code, size)[4] for code in CODES)) // 2
for i, code in enumerate(CODES):
    w, h, x, y, advance = font.glyph(code, size)
    mask = font.render(code, size)
    strip.blit_alpha(mask, pen + x, ascent + y, w, h, COLORS[i % len(COLORS)])
    pen += advance

# Clear the screen and copy the strip into its middle.
display_drv.fill(BACKGROUND)
top = (display_drv.height - strip_height) // 2
display_drv.blit_rect(pixels, 0, top, width, strip_height)
display_drv.show()
print("Drew %d icons at %d px on the %dx%d display" % (len(CODES), size, width, display_drv.height))
time.sleep(SECONDS)
