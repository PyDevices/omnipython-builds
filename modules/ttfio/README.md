# ttfio — TrueType glyphs from flash

`import ttfio` draws a font's glyphs as 8-bit coverage masks, straight from
the font's bytes. Freeze a font into the firmware and it stays in flash: the
RAM it costs is one scratch buffer, 8 KB by default, and drawing into a buffer
you pass allocates nothing.

```python
import ttfio

with open("icons.ttf", "rb") as f:
    font = ttfio.Font(f.read())

w, h, x, y, advance = font.glyph(0xE8B8, 20)   # the "settings" icon at 20 px
mask = font.render(0xE8B8, 20)                 # w*h bytes, 0..255
for row in range(h):
    print("".join(" .:#"[v // 64] for v in mask[row * w:row * w + w]))
```

It is built for icon fonts such as Material Symbols, where one 20 KB font
holds every icon at every size, and works for any TrueType font. The same code
runs on every MicroPython port (`--modules all` has it). On CPython, `ttfio.py`
in omnipython-desktop gives the same API over FreeType.

## API

### `ttfio.Font(data, scratch=8192)`

`data` is the font file's bytes, or any buffer holding them. The font keeps a
reference and reads it in place, so a frozen `bytes` never leaves flash; a
font read from a file sits in RAM. `scratch` is the working memory every
render draws in, allocated once. 8192 bytes draws a Material Symbols icon at
up to 48 px; a detailed glyph at a large size needs more, and `scratch_peak`
says how much the renders so far have used.

Fonts are trusted data. A damaged or hostile font can make the drawing code
read outside it, so load only fonts you ship.

### `glyph(ch, px) -> (w, h, x, y, advance)` or `None`

`ch` is a character or a codepoint and `px` is the em size in pixels. `(x, y)`
is the mask's top-left corner from the pen on the baseline, with `y` negative
above it. `None` means the font has no glyph for `ch`; `has(ch)` asks the same
question.

### `render(ch, px, buf=None, *, stride=0) -> bytearray`

Draws the glyph as coverage, 0 to 255, into `buf` (rows `stride` bytes apart,
default the glyph's width) or into a new `bytearray`. Bytes outside the
glyph's box are left alone, so you can draw several glyphs into one mask.
A glyph that needs more scratch than the font has raises `MemoryError`, and
the font keeps working.

### `metrics(px) -> (ascent, descent, line_gap)`

The font's line metrics at `px`, rounded; descent is negative.

## How

The engine is Sean Barrett's
[stb_truetype](https://github.com/nothings/stb), with its memory requests
served from the font's scratch buffer: each render starts the buffer empty and
takes what it needs from it in order. Curves are flattened to a tenth of a
pixel, so an icon at 20 px holds the same ink as FreeType's unhinted drawing,
within 2 %. ttfio does not hint, so text at small sizes is softer than a
hinted desktop renderer draws it.

[`tests/test_ttfio.py`](tests/test_ttfio.py) checks the API on any port, and
[`tests/check_ttfio_freetype.py`](tests/check_ttfio_freetype.py) compares its
drawings with FreeType's on a PC.
