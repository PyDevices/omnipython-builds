# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

# icons, from omnipython-lib: Material Symbols as a font that stays in flash,
# drawn at any size by the ttfio module, which a build names beside it
# (--modules ttfio,icons; "all" has both). Frozen at opt=3.
#
# Included with deflate=True (a variant passes it through modules/manifest.py's
# module_options), the font and its tables are frozen deflated instead, about
# 45 KB in place of 90 KB, and inflated into RAM when icons is imported
# (compress.py, beside this file). For a board with PSRAM and little flash.
import os
import sys

options.defaults(deflate=False)
include("../library.py")
if not options.deflate:
    require("icons", library="omnipython-lib", opt=3)
else:
    # Loaded by path under its own name, as audioeffects loads selection.py.
    import importlib.util

    _spec = importlib.util.spec_from_file_location("icons_compress", os.path.join(os.getcwd(), "compress.py"))
    compress = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(compress)

    _library = os.environ["OMNIPYTHON_LIBRARY"]
    _out = os.path.join(os.path.dirname(_library), "icons-deflated", "icons")
    _sizes = compress.write(os.path.join(_library, "icons", "icons"), _out)
    _before = sum(s[0] for s in _sizes.values())
    _after = sum(s[1] for s in _sizes.values())
    # On stderr: the build reads stdout for C module paths.
    print("icons: freezing the font deflated, %d bytes for %d" % (_after, _before), file=sys.stderr)
    package("icons", base_path=os.path.dirname(_out), opt=3)
