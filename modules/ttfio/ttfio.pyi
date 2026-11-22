# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""TrueType glyphs, drawn from a font where it lies.

A `Font` reads the font's bytes in place: frozen into the firmware, they stay
in flash and only the scratch buffer is RAM. Each glyph is drawn as 8-bit
coverage, a mask you blend a colour through. Drawing into a buffer you pass
allocates nothing.

The same code runs on every MicroPython port. On CPython, the `ttfio` module
in the desktop package gives the same API over FreeType.
"""

from typing import Optional, Tuple, Union

__revision__: str
"""Which source this firmware was built from, from `git describe`: a release
tag, or the nearest one and the commit. "unknown" when the build had no git."""

_Char = Union[str, int]

class Font:
    """A TrueType font.

    Fonts are trusted data: a damaged or hostile font file can make the
    drawing code read outside it, so load only fonts you ship.
    """

    units_per_em: int
    """The font's design units to one em, from its head table."""

    scratch_peak: int
    """The most scratch any render has used so far, in bytes. MicroPython only:
    it is how you size ``scratch``."""

    def __init__(self, data: bytes, scratch: int = 8192) -> None:
        """Open a font.

        Args:
            data: The font file's bytes, or any buffer holding them. The font
                keeps a reference and reads it in place. A frozen ``bytes``
                stays in flash; a font read from a file sits in RAM.
            scratch: Bytes of working memory, allocated once, that every render
                draws in. 8192 draws a Material Symbols icon at up to 48 px;
                detailed glyphs at large sizes need more.

        Raises:
            ValueError: ``data`` is not a TrueType font, or ``scratch`` is under
                256.
        """

    def has(self, ch: _Char) -> bool:
        """Whether the font has a glyph for ``ch``, a character or a codepoint."""

    def metrics(self, px: float) -> Tuple[int, int, int]:
        """The font's ascent, descent (negative) and line gap at an em of ``px``
        pixels, rounded."""

    def glyph(self, ch: _Char, px: float) -> Optional[Tuple[int, int, int, int, int]]:
        """Where ``ch`` lands at an em of ``px`` pixels.

        Returns:
            ``(w, h, x, y, advance)``: the mask's size, its top-left corner
            measured from the pen on the baseline (``y`` is negative above the
            baseline), and how far the pen moves. None if the font has no
            glyph for ``ch``.
        """

    def render(self, ch: _Char, px: float, buf: Optional[bytearray] = None, *, stride: int = 0) -> bytearray:
        """Draw ``ch`` at an em of ``px`` pixels as 8-bit coverage, 0 to 255.

        Args:
            ch: A character or a codepoint.
            px: The em size in pixels.
            buf: Where to draw. None makes a new ``bytearray`` of ``w * h``
                bytes, the size `glyph` gives.
            stride: Bytes from one row of ``buf`` to the next, to draw into a
                wider mask. 0 means the glyph's width. Bytes outside the
                glyph's box are left alone.

        Returns:
            ``buf``, or the new bytearray.

        Raises:
            KeyError: The font has no glyph for ``ch``.
            ValueError: ``buf`` is too small, or ``stride`` is narrower than
                the glyph.
            MemoryError: The glyph needs more scratch than the font has. The
                font still works; make one with a larger ``scratch`` for this
                glyph.
        """
