# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Tests for scripts/stage_firmware_page.py.

    PYTHONPATH=tests python3 -m unittest test_stage_firmware_page -v
"""
import json
import html
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import release_firmware as rf
import stage_firmware_page as sp
from test_release_firmware import fake_set

URL = "https://github.com/PyDevices/omnipython-builds/releases/download/staged-20261020/"
INTERP = {"tag": "v0.5.5", "files": {"micropython": {"sha256": "0" * 64, "size": 1, "platform": "linux-x86_64",
                                                     "version": "x"}}}
INTERP_REL = {"tag_name": "v0.5.5", "html_url": "https://github.com/PyDevices/omnipython/releases/tag/v0.5.5",
              "assets": [{"name": "micropython", "size": 1,
                          "browser_download_url": "https://example.invalid/v0.5.5/micropython"}]}


class Stage(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root)
        indir = self.root / "in"
        indir.mkdir()
        fake_set(indir)
        self.fw = self.root / "fw"
        self.doc = rf.assemble(indir, self.fw, False, "staged-20261020", "https://run")
        self.page = self.root / "page"
        names = {f["name"]: f["size"] for b in self.doc["builds"] for f in b["files"]}
        self.release = {"tag_name": "staged-20261020", "name": "OmniPython firmware test", "draft": False,
                        "html_url": "https://github.com/PyDevices/omnipython-builds/releases/tag/staged-20261020",
                        "assets": [{"name": n, "size": sz, "browser_download_url": URL + n}
                                   for n, sz in names.items()]}

    def test_the_page_links_every_image_on_the_release(self):
        page = sp.stage(self.doc, self.release, self.page)
        self.assertEqual((self.page / "index.html").read_text(), page)
        self.assertEqual(json.loads((self.page / "firmware.json").read_text()), self.doc)
        self.assertEqual(sorted(p.name for p in self.page.iterdir()), ["firmware.json", "index.html"])
        text = html.unescape(page)
        for b in self.doc["builds"]:
            self.assertIn(b["label"], text)
            for f in b["files"]:
                self.assertIn(URL + f["name"], text)
        self.assertIn("esptool --chip esp32p4 write-flash 0x2000 ", text)
        self.assertIn("--preview", text)
        self.assertIn("gh attestation verify", text)

    def test_the_giga_lists_its_three_images_in_order(self):
        text = html.unescape(sp.stage(self.doc, self.release, self.page))
        giga = next(b for b in self.doc["builds"] if b["id"] == "mp-giga-shield")
        order = [next(f["name"] for f in giga["files"] if f["role"] == r) for r in ("wifi", "romfs", "flash")]
        at = [text.index("-D " + n) for n in order]
        self.assertEqual(at, sorted(at))

    def test_a_draft_is_refused(self):
        self.release["draft"] = True
        with self.assertRaisesRegex(sp.Failed, "draft"):
            sp.stage(self.doc, self.release, self.page)
        self.assertFalse(self.page.exists())

    def test_a_file_missing_from_the_release_is_refused(self):
        self.release["assets"].pop()
        with self.assertRaisesRegex(sp.Failed, "is not on release"):
            sp.stage(self.doc, self.release, self.page)

    def test_a_file_of_another_size_is_refused(self):
        self.release["assets"][0]["size"] += 1
        with self.assertRaisesRegex(sp.Failed, "bytes on the release"):
            sp.stage(self.doc, self.release, self.page)

    def test_another_release_is_refused(self):
        self.release["tag_name"] = "staged-other"
        with self.assertRaisesRegex(sp.Failed, "firmware.json names"):
            sp.stage(self.doc, self.release, self.page)

    def test_the_interpreters_are_linked_or_said_to_come_later(self):
        text = sp.stage(self.doc, self.release, self.page, INTERP, INTERP_REL)
        self.assertIn("https://example.invalid/v0.5.5/micropython", text)
        self.assertIn("Linux x86-64", text)
        text = sp.stage(self.doc, self.release, self.page)
        self.assertIn("arrive with the next OmniPython release", text)

    def test_newest_final_with_interpreters(self):
        asset = [{"name": "interpreters.json"}]
        rel = [{"tag_name": "v0.7.7.dev1", "prerelease": True, "assets": asset},
               {"tag_name": "v0.7.6", "assets": [{"name": "x.whl"}]},
               {"tag_name": "v0.7.5", "draft": True, "assets": asset},
               {"tag_name": "v0.5.5", "assets": asset},
               {"tag_name": "v0.5.4", "assets": asset}]
        self.assertEqual(sp.newest_final_with_interpreters(rel)["tag_name"], "v0.5.5")
        self.assertIsNone(sp.newest_final_with_interpreters(rel[:3]))


if __name__ == "__main__":
    unittest.main()
