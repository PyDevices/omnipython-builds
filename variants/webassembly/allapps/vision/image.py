# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""A browser page's ``image``: a picture over a buffer, for `espdl`.

On a board ``image`` is the vision module's image library. In the all-apps
page it is only what the page's `espdl` reads: an RGB565 or grayscale
picture over a buffer the program owns::

    img = image.Image(320, 240, image.RGB565, buffer=buf)

RGB565 is little-endian, as the page's camera writes it. Drawing, filters,
codecs and the rest of a board's ``image`` aren't here.
"""

GRAYSCALE = 2
RGB565 = 3

_BPP = {GRAYSCALE: 1, RGB565: 2}


class Image:
    """A *w* x *h* picture in *format*, over *buffer* or a new one.

    Args:
        w: the width in pixels.
        h: the height in pixels.
        format: `RGB565` or `GRAYSCALE`.
        buffer: the pixels, which the picture reads and doesn't copy; a new
            buffer when None.
        copy_to_fb: taken for a board's image, and ignored.

    Raises:
        ValueError: the format isn't RGB565 or GRAYSCALE, or the buffer is
            too small for the picture.
    """

    def __init__(self, w, h, format=RGB565, *, buffer=None, copy_to_fb=False):
        if format not in _BPP:
            raise ValueError("a page's image is RGB565 or GRAYSCALE")
        size = w * h * _BPP[format]
        if buffer is None:
            buffer = bytearray(size)
        elif len(buffer) < size:
            raise ValueError("the buffer holds %d bytes; a %d x %d picture needs %d" % (len(buffer), w, h, size))
        self._w, self._h, self._format = w, h, format
        self._buf = memoryview(buffer)[:size]

    def width(self):
        return self._w

    def height(self):
        return self._h

    def format(self):
        return self._format

    def size(self):
        """The picture's size in bytes."""
        return len(self._buf)

    def bytearray(self):
        """The picture's pixels: a view of its buffer, not a copy."""
        return self._buf
