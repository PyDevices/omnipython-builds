# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT
"""Write the icons package with its font compressed, for a board short of flash.

Frozen as it comes, the icons font takes about 90 KB of flash and no RAM.
This writes a copy of the package whose ``_material.py`` holds the font, the
name table and the code table deflated, about 45 KB, and inflates them when
``icons`` is imported. The icons are the same, and so is the package's API.
The cost moves to RAM: the inflated tables, about 90 KB, stay on the heap
from the first import, so use it on a board with PSRAM.

The manifest beside this file uses it when it's included with
``deflate=True``, as the ESP32 Audio Kit's variant does.
"""

import os
import shutil
import zlib

# The tables a font module holds, as icons.add() documents them.
TABLES = ("FONT", "NAMES", "CODES")

# deflate's largest window, 32 KB: the smallest output. Inflating allocates
# the window for as long as it runs, from the heap.
WBITS = 15

MATERIAL = '''# SPDX-FileCopyrightText: Google LLC
#
# SPDX-License-Identifier: Apache-2.0
"""%(doc)s

Deflated to save flash: the tables are inflated into RAM when this module is
imported. Made by omnipython-builds' modules/icons/compress.py from the
package's own _material.py. Do not edit.
"""

import deflate
import io


def _inflate(data):
    return deflate.DeflateIO(io.BytesIO(data), deflate.RAW, %(wbits)d).read()


%(tables)s
del _inflate
'''


def deflated(data):
    """*data* as a raw deflate stream with a `WBITS` window."""
    z = zlib.compressobj(9, zlib.DEFLATED, -WBITS, 9)
    return z.compress(data) + z.flush()


def tables(source):
    """The doc string and the tables of the font module at *source*, a ``_material.py``.

    Raises:
        ValueError: The module is missing one of `TABLES`.
    """
    names = {}
    with open(source) as f:
        exec(compile(f.read(), source, "exec"), names)
    missing = [t for t in TABLES if not isinstance(names.get(t), bytes)]
    if missing:
        raise ValueError("%s has no %s: it isn't an icons font module" % (source, ", ".join(missing)))
    return (names.get("__doc__") or "Icons.").strip(), {t: names[t] for t in TABLES}


def write(package, out):
    """Copy the icons package at *package* to *out*, with ``_material.py`` deflated.

    Args:
        package (str): The package folder, the one holding ``__init__.py`` and ``_material.py``.
        out (str): Where to write it. It is emptied first.

    Returns:
        dict: Each table's size before and after, ``{"FONT": (82988, 40881), ...}``.
    """
    source = os.path.join(package, "_material.py")
    doc, found = tables(source)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    for name in sorted(os.listdir(package)):
        if name.endswith(".py") and name != "_material.py":
            shutil.copyfile(os.path.join(package, name), os.path.join(out, name))
    sizes = {}
    lines = []
    for t in TABLES:
        packed = deflated(found[t])
        sizes[t] = (len(found[t]), len(packed))
        lines.append("%s = _inflate(%r)" % (t, packed))
    text = MATERIAL % {"doc": doc.split("\n")[0], "wbits": WBITS, "tables": "\n".join(lines)}
    with open(os.path.join(out, "_material.py"), "w") as f:
        f.write(text)
    return sizes
