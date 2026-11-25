# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

# The Audio Kit's frozen content: the port's and the modules you named
# (modules/manifest.py), plus the app libraries Bluetooth Receiver imports:
# appkit, touchkit, controlkit, deskkit and spectrum, with what they need.
#
# This is the one board that freezes app libraries. Everywhere else they
# install with omip, so they update without new firmware. On the kit's 4 MB
# they take about half the room frozen that they do as files, and as files
# Bluetooth Receiver and its libraries don't fit beside the firmware. The app
# itself still installs with omip (`app-btreceiver`), and so does the board
# config.
#
# appkit draws with icons, so the build needs ttfio and icons named too. The
# icons font is frozen deflated here, 45 KB in place of 90, and inflated
# into PSRAM at import. The libraries are frozen at opt=3 like the library's
# other packages.
#
# To make room, the omnipython package goes in without hmilink, medialink,
# mp4mux and usb_hid, which Bluetooth Receiver doesn't use, and
# mpconfigvariant.cmake leaves LVGL's largest fonts out.
import os

_named = {n.strip() for n in os.environ.get("OMNIPYTHON_MODULES", "").split(",")}
_missing = [n for n in ("ttfio", "icons") if n not in _named and "all" not in _named]
if _missing:
    raise ValueError(
        "AUDIO_KIT freezes appkit, which draws with icons: add %s to --modules" % ",".join(_missing)
    )

include(
    "../../../../modules/manifest.py",
    module_options={
        "icons": {"deflate": True},
        "omnipython": {"leave_out": ("hmilink", "medialink", "mp4mux", "usb_hid")},
    },
)
include("../../../../modules/library.py")

require(
    "applibs",
    library="omnipython-lib",
    packages=("appkit", "touchkit", "controlkit", "deskkit", "spectrum"),
    opt=3,
)
