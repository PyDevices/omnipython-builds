# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

# OmniPython's own Python, from omnipython-lib: what lib/ holds, which is
# `omnipython` and `bledev` as the library splits them (`omnipython` carries
# hmilink, medialink, mp4mux and usb_hid; usb_hid runs over the usb-device-hid
# that modules/micropython-lib freezes), plus the host-only
# parts of audiodev, bledev, displaydev and multimer that mip ships in
# `omnipython-desktop` and that lib/ has always carried, so a build's frozen
# files are the ones it had when this module froze lib/ itself.
#
# Frozen at opt=3, as before. A frozen OmniPython comes before /lib on
# sys.path, so it shadows a copy installed with mip.
import os

include("../library.py")

# A board with very little flash can leave some of the omnipython package's
# members out, as the Audio Kit's variant does:
#   include(".../modules/manifest.py", module_options={"omnipython": {"leave_out": ("hmilink",)}})
# Each name is a package or module at the top of omnipython. The rest is
# frozen with the files the package's own manifest names.
options.defaults(leave_out=())
if options.leave_out:
    _tree = os.environ["OMNIPYTHON_LIBRARY"]
    _gone = set(options.leave_out)
    _known = {n.split(".")[0] for n in os.listdir(os.path.join(_tree, "omnipython"))}
    if not _gone <= _known:
        raise ValueError("omnipython has no member %s" % ", ".join(sorted(_gone - _known)))

    class _Options:
        opt = 3

        def defaults(self, **kwargs):
            pass

    def _freeze(name, gone=()):
        # Runs the library package's own manifest, skipping the members in
        # gone. Its require("omnipython") is skipped too: the package is
        # frozen here already, without those members, and requiring it would
        # freeze all of it a second time.
        base = os.path.join(_tree, name)

        def _package(member, files=None, opt=None):
            if member not in gone:
                package(member, files=files, base_path=base, opt=3)

        def _module(member, opt=None):
            if member.split(".")[0] not in gone:
                module(member, base_path=base, opt=3)

        def _require(member, **kwargs):
            if member != "omnipython":
                require(member, **kwargs)

        with open(os.path.join(base, "manifest.py")) as f:
            exec(
                f.read(),
                {
                    "package": _package,
                    "module": _module,
                    "require": _require,
                    "metadata": lambda **kwargs: None,
                    "options": _Options(),
                },
            )

    _freeze("omnipython", _gone)
    _freeze("bledev")
else:
    require("omnipython", library="omnipython-lib", opt=3)
    require("bledev", library="omnipython-lib", opt=3)
# endpointkit, which audiodev's Bluetooth and USB providers and displaydev's
# endpoints import: without it a board that doesn't build usbhost (whose
# packages bring it) can't list a Bluetooth speaker under audio out.
require("endpointkit", library="omnipython-lib", opt=3)
# MIDI ports for a program or app: UART, USB device and host, Bluetooth LE.
# Frozen where the image has room for them, a flash of 8 MB or more as
# --flash gives it; a smaller board installs midiports with omip.
_flash = os.environ.get("OMNIPYTHON_FLASH", "")
if _flash.endswith("MB") and int(_flash[:-2]) >= 8:
    require("midiports", library="omnipython-lib", opt=3)

# omnipython-desktop also holds mip.py, micropython.py, pngio.py and mdns.py,
# which would stand in front of the firmware's own mip and of the C modules
# of the same names, and the three desktop helpers (usdl2, uwin32,
# frame_recorder) that only the desktop board config freezes. So only its
# packages' files are taken, from the library tree.
#
# A board's build leaves them out (build_mp.py sets OMNIPYTHON_PLATFORM to
# "board" for every port but unix, windows and webassembly, and the same for
# CircuitPython, whose only desktop port is unix): they are 26 files of desktop-only code, and on a
# CircuitPython board their names are more than a frozen-string pool of 64 KB
# can spare. With it unset, as when freeze_list.py lists a desktop manifest,
# they are frozen.
if os.environ.get("OMNIPYTHON_PLATFORM") != "board":
    _host = os.path.join(os.environ["OMNIPYTHON_LIBRARY"], "omnipython-desktop")
    for _pkg in sorted(os.listdir(_host)):
        if os.path.isdir(os.path.join(_host, _pkg)):
            _files = sorted(f for f in os.listdir(os.path.join(_host, _pkg)) if f.endswith(".py"))
            package(_pkg, files=_files, base_path=_host, opt=3)
