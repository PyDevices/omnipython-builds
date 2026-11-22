# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""ttfio: the API, its errors, and drawing without allocating.

    micropython test_ttfio.py [--out DIR]

It runs unchanged on CPython against omnipython-desktop's ttfio.py, which
skips the checks of the scratch buffer.

Bars fixed before the first run:

- every icon in data/icons20.ttf is found by its codepoint and by its
  character, and a character the font lacks is None from glyph(), False from
  has() and KeyError from render();
- a Material Symbols icon at 20 px is a 20 px advance with its box inside the
  20 px em, and at 40 px every figure doubles, give or take a pixel;
- render() draws the same pixels twice running, and into a wider buffer it
  writes the glyph's box and nothing else;
- with a buffer given, render() allocates nothing at all;
- a glyph too big for the scratch buffer raises MemoryError, the same Font
  draws correctly afterwards, and a larger scratch draws it;
- bad arguments raise, naming the problem.

With --out, each icon's mask at 20 and 40 px is written there for
check_ttfio_freetype.py, which compares it with FreeType's on the PC.
"""

import sys

import ttfio

# The scratch buffer and the heap lock are MicroPython's; on CPython this runs
# against omnipython-desktop's ttfio.py and skips those checks.
ON_MICROPYTHON = sys.implementation.name == "micropython"
if ON_MICROPYTHON:
    import micropython

_FILE = __file__.replace("\\", "/")  # Windows paths too
HERE = _FILE.rsplit("/", 1)[0] if "/" in _FILE else "."
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

OUT = None
_argv = getattr(sys, "argv", [])
if "--out" in _argv:
    OUT = _argv[_argv.index("--out") + 1]

failures = []


def check(ok, what):
    print("%s  %s" % ("ok  " if ok else "FAIL", what))
    if not ok:
        failures.append(what)


def raises(exc, fn, *args, **kw):
    try:
        fn(*args, **kw)
    except exc as e:
        return str(e)
    return None


with open(HERE + "/data/icons20.ttf", "rb") as f:
    DATA = f.read()
font = ttfio.Font(DATA)

check(font.units_per_em == 960, "units_per_em is 960 (got %r)" % (font.units_per_em,))
m = font.metrics(20)
check(len(m) == 3 and m[0] > 0 and m[1] <= 0, "metrics(20) is ascent, descent, gap: %r" % (m,))

for name, cp in sorted(ICONS.items()):
    ch = chr(cp)
    g = font.glyph(cp, 20)
    check(font.has(cp) and font.has(ch) and g == font.glyph(ch, 20), "%s found by codepoint and by character" % name)
    w, h, x, y, adv = g
    check(adv == 20 and 0 < w <= 20 and 0 < h <= 20 and x >= 0 and x + w <= 20 and -20 <= y and y + h <= 0,
          "%s at 20 px: %r inside the em" % (name, g))
    g2 = font.glyph(cp, 40)
    check(all(abs(b - 2 * a) <= 2 for a, b in zip(g, g2)), "%s at 40 px doubles: %r" % (name, g2))
    mask = font.render(cp, 20)
    check(len(mask) == w * h and max(mask) >= 224 and mask == font.render(cp, 20),
          "%s renders %d bytes, solid inside, same twice" % (name, len(mask)))
    if OUT:
        for px in (20, 40):
            gw, gh, gx, gy, _ = font.glyph(cp, px)
            with open("%s/%s_%d.mask" % (OUT, name, px), "wb") as f:
                f.write(bytes((gw, gh, gx & 0xFF, gy & 0xFF)))
                f.write(font.render(cp, px))

check(font.glyph("A", 20) is None and not font.has("A"), "a character the font lacks: glyph() None, has() False")
check(raises(KeyError, font.render, "A", 20) is not None, "render() of a missing character raises KeyError")

# Into a wider buffer: the glyph's box changes, nothing else does.
cp = ICONS["settings"]
w, h, x, y, adv = font.glyph(cp, 20)
alone = font.render(cp, 20)
stride = 32
buf = bytearray(b"\x07" * (stride * 24))
font.render(cp, 20, buf, stride=stride)
inside = bytearray()
outside_ok = True
for row in range(24):
    for col in range(stride):
        v = buf[row * stride + col]
        if row < h and col < w:
            inside.append(v)
        elif v != 7:
            outside_ok = False
check(inside == alone and outside_ok, "render(buf, stride=32) writes the box and nothing else")

# A frozen font is a bytes object in flash; a memoryview of it is read in place too.
check(ttfio.Font(memoryview(DATA)).render(cp, 20) == alone, "a memoryview of the font draws the same")

if ON_MICROPYTHON:
    out = bytearray(64 * 64)
    # Every name the locked loop sets exists first: a new global grows the
    # module's dict, which would allocate.
    px = 0
    locked = "render() raised MemoryError"
    micropython.heap_lock()
    try:
        for px in (16, 20, 24, 48):
            font.render(cp, px, out)
        locked = None
    except MemoryError:
        pass
    micropython.heap_unlock()
    check(locked is None, "render() into a buffer allocates nothing (heap locked)")
    check(0 < font.scratch_peak <= 8192, "scratch_peak after a 48 px icon: %d bytes" % font.scratch_peak)

if ON_MICROPYTHON:
    # The settings icon needs about 6.5 KB at 20 px and 21 KB at 1000 px.
    err = raises(MemoryError, font.render, cp, 1000)
    check(err is not None and "scratch" in err, "too little scratch raises MemoryError: %r" % (err,))
    check(font.render(cp, 20) == alone, "the same Font draws correctly after the error")
    check(len(ttfio.Font(DATA, scratch=32768).render(cp, 1000)) > 0, "Font(scratch=32768) draws it at 1000 px")

check(raises(ValueError, ttfio.Font, b"not a font at all") is not None, "Font(junk) raises ValueError")
check(raises(ValueError, ttfio.Font, DATA, scratch=16) is not None, "Font(scratch=16) raises ValueError")
check(raises(TypeError, font.glyph, "ab", 20) is not None, "glyph('ab') raises TypeError")
check(raises(ValueError, font.glyph, cp, 0) is not None, "glyph(px=0) raises ValueError")
check(raises(ValueError, font.render, cp, 20, bytearray(4)) is not None, "render() into too small a buffer raises ValueError")
check(raises(ValueError, font.render, cp, 20, bytearray(400), stride=2) is not None, "a stride narrower than the glyph raises ValueError")

print("%d failed" % len(failures) if failures else "all passed")
if failures:
    sys.exit(1)
