# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""The unix port's REPL survives a dupterm stream that takes itself off.

A desktop app that mirrors the REPL through os.dupterm() and detaches it when
it closes can do that from inside the stream's read(), or from a timer that
runs there. The REPL must then go back to reading stdin, not read the empty
slot (patches/micropython/0088). And a read() that has nothing yet must leave
the interpreter's exception handlers as it found them.

The tests run a unix build with os.dupterm, the omnipython variant:
builds/unix/omnipython/micropython, or the interpreter $MICROPYTHON_BIN names.
They skip without one, unless OMNIPYTHON_REQUIRE_MICROPYTHON is set, as CI does.

    PYTHONPATH=tests python3 -m unittest test_unix_dupterm -v
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
BINARY = Path(os.environ.get("MICROPYTHON_BIN", HERE / "builds" / "unix" / "omnipython" / "micropython"))

STREAM = """
import io
import os

DETACH = object()


class Term(io.IOBase):
    def __init__(self, reads):
        self.reads = list(reads)

    def read(self, n):
        r = self.reads.pop(0) if self.reads else None
        if r is DETACH:
            os.dupterm(None, 0)
            r = None
        return r

    def readinto(self, buf):
        return None

    def write(self, buf):
        return len(buf)

    def ioctl(self, op, arg):
        return 0

"""


class DetachingStream(unittest.TestCase):
    def setUp(self):
        if not BINARY.is_file():
            why = "needs a unix build with os.dupterm at %s or $MICROPYTHON_BIN" % BINARY
            if os.environ.get("OMNIPYTHON_REQUIRE_MICROPYTHON"):
                self.fail(why)
            self.skipTest(why)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)

    def run_script(self, body, stdin, *flags):
        script = self.tmp / "script.py"
        script.write_text(STREAM + body)
        return subprocess.run([str(BINARY), *flags, str(script)], input=stdin, capture_output=True,
                              timeout=30)

    def test_repl_reads_stdin_once_the_stream_detaches(self):
        # The REPL prompt reads the stream, which has nothing twice and then
        # detaches itself. The REPL then runs the line waiting on stdin.
        result = self.run_script('os.dupterm(Term([None, None, DETACH]), 0)\n', b"print('from stdin')\n",
                                 "-i")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"from stdin", result.stdout)

    def test_a_read_with_nothing_leaves_the_exception_handlers_alone(self):
        # input() reads through the REPL's stdin path. The stream's first read
        # has nothing; then an exception is raised and caught, and the script
        # ends. A handler left behind by that read sent the interpreter into a
        # frame that had returned, and it crashed on the way out.
        body = (
            'os.dupterm(Term([None, b"a", b"\\n"]), 0)\n'
            "line = input()\n"
            "os.dupterm(None, 0)\n"
            'print("read", repr(line))\n'
            "try:\n"
            '    raise ValueError("caught")\n'
            "except ValueError as e:\n"
            "    print(e)\n"
            'print("done")\n'
        )
        result = self.run_script(body, b"")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b"read 'a'\ncaught\ndone\n", result.stdout)


if __name__ == "__main__":
    unittest.main()
