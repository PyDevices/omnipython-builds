# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Makes data/icons20.ttf, the font ttfio's tests draw, from Material Symbols.

    python make_font.py MaterialSymbolsOutlined[FILL,GRAD,opsz,wght].ttf MaterialSymbolsOutlined[FILL,GRAD,opsz,wght].codepoints

Both files are in https://github.com/google/material-design-icons, under
variablefont/. The result is the filled, weight 400 instance at the 20 px
optical size, cut down to the icons in NAMES, with no hinting and no ligature
tables: each icon is reached by its codepoint. Needs fontTools.
"""

import io
import os
import sys

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

NAMES = ["wifi", "bluetooth", "battery_full", "volume_up", "settings", "home", "close", "check", "search", "mic"]


def main(src, codepoints):
    table = dict(line.split() for line in open(codepoints) if line.strip())
    font = instancer.instantiateVariableFont(TTFont(src), {"FILL": 1, "wght": 400, "GRAD": 0, "opsz": 20})
    opts = subset.Options()
    opts.layout_features = []
    opts.notdef_outline = False
    opts.name_IDs = [0, 1, 2]
    opts.hinting = False
    opts.drop_tables += ["GSUB", "GPOS", "DSIG"]
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=[int(table[n], 16) for n in NAMES])
    sub.subset(font)
    buf = io.BytesIO()
    font.save(buf)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "icons20.ttf")
    with open(out, "wb") as f:
        f.write(buf.getvalue())
    for n in NAMES:
        print("%s = 0x%s" % (n, table[n]))
    print("%s: %d bytes" % (out, len(buf.getvalue())))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
