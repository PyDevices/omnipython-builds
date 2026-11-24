# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Unit tests for modules/icons/compress.py: the icons package written with its
font deflated, and the tables it gives back when it's imported.

    PYTHONPATH=tests python3 -m unittest test_icons_compress -v
"""

import importlib.util
import os
import sys
import tempfile
import types
import unittest
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "modules" / "icons"))
import compress  # noqa: E402

# A font module shaped like the icons package's: a doc string and three tables.
MATERIAL = '''# SPDX-FileCopyrightText: Google LLC
#
# SPDX-License-Identifier: Apache-2.0
"""Test icons: 2 icons.

Made by tools/make_icons.py. Do not edit.
"""

FONT = %r
NAMES = b"home\\nwifi\\n"
CODES = b"\\x00\\xe8\\x8a\\x00\\xe6\\x3e"
'''

FONT = bytes(range(256)) * 40 + b"glyf" * 500


def deflate_shim():
    """MicroPython's deflate module, as much of it as the written module uses."""
    mod = types.ModuleType("deflate")
    mod.RAW = 1

    class DeflateIO:
        def __init__(self, stream, fmt, wbits):
            self.stream, self.wbits = stream, wbits

        def read(self):
            return zlib.decompress(self.stream.read(), -self.wbits)

    mod.DeflateIO = DeflateIO
    return mod


class CompressTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.package = os.path.join(self.tmp.name, "src", "icons")
        os.makedirs(self.package)
        for name in ("__init__.py", "gfx.py", "lvgl.py"):
            Path(self.package, name).write_text("# %s\n" % name)
        Path(self.package, "__init__.pyi").write_text("# stub\n")
        Path(self.package, "icons.txt").write_text("home\nwifi\n")
        Path(self.package, "_material.py").write_text(MATERIAL % FONT)
        self.out = os.path.join(self.tmp.name, "out", "icons")
        sys.modules["deflate"] = deflate_shim()

    def tearDown(self):
        sys.modules.pop("deflate", None)
        self.tmp.cleanup()

    def load(self):
        spec = importlib.util.spec_from_file_location("written_material", os.path.join(self.out, "_material.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_tables_inflate_to_the_originals(self):
        compress.write(self.package, self.out)
        mod = self.load()
        self.assertEqual(mod.FONT, FONT)
        self.assertEqual(mod.NAMES, b"home\nwifi\n")
        self.assertEqual(mod.CODES, b"\x00\xe8\x8a\x00\xe6\x3e")
        self.assertFalse(hasattr(mod, "_inflate"))

    def test_the_font_comes_out_smaller(self):
        sizes = compress.write(self.package, self.out)
        self.assertEqual(sizes["FONT"][0], len(FONT))
        self.assertLess(sizes["FONT"][1], sizes["FONT"][0])
        source = Path(self.out, "_material.py").read_text()
        self.assertIn("Test icons: 2 icons.", source)
        self.assertIn("Deflated to save flash", source)

    def test_the_rest_of_the_package_is_copied_python_only(self):
        compress.write(self.package, self.out)
        self.assertEqual(sorted(os.listdir(self.out)), ["__init__.py", "_material.py", "gfx.py", "lvgl.py"])
        self.assertEqual(Path(self.out, "gfx.py").read_text(), "# gfx.py\n")

    def test_a_second_write_starts_clean(self):
        os.makedirs(self.out)
        Path(self.out, "stale.py").write_text("")
        compress.write(self.package, self.out)
        self.assertNotIn("stale.py", os.listdir(self.out))

    def test_a_module_without_the_tables_is_refused(self):
        Path(self.package, "_material.py").write_text('FONT = b"x"\n')
        with self.assertRaises(ValueError) as cm:
            compress.write(self.package, self.out)
        self.assertIn("NAMES, CODES", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
