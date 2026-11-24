# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

# The Audio Kit's frozen content: the port's and the modules you named
# (modules/manifest.py), plus appkit and touchkit, which its apps import, from
# the applibs package with what those two need (deskkit and requests).
# Frozen, they run from flash and leave the kit's small filesystem for the
# app itself. Only this variant freezes them; other builds install them with
# mip.
#
# appkit draws with icons, so the build needs ttfio and icons named too. The
# icons font is frozen deflated here, 45 KB in place of 90, and inflated
# into PSRAM at import: the image doesn't fit the kit's 4 MB otherwise.
# appkit and touchkit are frozen at opt=3 like the library's other packages.
import os

_named = {n.strip() for n in os.environ.get("OMNIPYTHON_MODULES", "").split(",")}
_missing = [n for n in ("ttfio", "icons") if n not in _named and "all" not in _named]
if _missing:
    raise ValueError(
        "AUDIO_KIT freezes appkit, which draws with icons: add %s to --modules" % ",".join(_missing)
    )

include("../../../../modules/manifest.py", module_options={"icons": {"deflate": True}})
include("../../../../modules/library.py")

require("applibs", library="omnipython-lib", packages=("appkit", "touchkit"), opt=3)
