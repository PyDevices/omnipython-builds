# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

# The all-apps browser build: the omnipython variant's content, then every
# app of an apps checkout and everything the apps install with, so the page
# boots into Home and never fetches a package. scripts/build_wasm_allapps.py
# builds it; docs/guides/wasm-all-apps.md says how.
#
# $OMNIPYTHON_APPS is the apps checkout. What the apps need comes from their
# own package.json files, as omip reads them: each "deps" entry is a module
# of this repository (it must be among --modules, and "all" holds every one)
# or a package of omnipython-lib, and each "upstream" entry is a
# micropython-lib package. The apps and their shared libraries (lib/) are
# frozen by the apps repository's own apps/manifest.py, as the package
# frozen_apps that Home lists. An app that can't work in a browser is still
# in, and says what it lacks when it starts.
import json
import os
import sys

_apps = os.environ.get("OMNIPYTHON_APPS")
if not _apps or not os.path.isdir(os.path.join(_apps, "apps")):
    raise ValueError(
        "allapps: OMNIPYTHON_APPS must name a checkout of the apps repository "
        "(scripts/build_wasm_allapps.py sets it), not %r" % (_apps,)
    )

include("../omnipython/manifest.py")
# Boards freeze upstream's uasyncio shim beside asyncio, and app code written
# for them (midiEngine's umidiparser) imports it; the webassembly port doesn't.
module("uasyncio.py", base_path="$(MPY_DIR)/extmod/asyncio", opt=3)
include("../../../modules/library.py")

_modules = os.path.abspath("../../../modules")
_named = {n.strip().rstrip("/").rsplit("/", 1)[-1] for n in os.environ.get("OMNIPYTHON_MODULES", "").split(",")}
# Frozen with the apps, or by the variant itself: the apps' shared libraries
# (applibs is apps/lib), another app, and the Fetch-backed requests the
# omnipython variant freezes in place of micropython-lib's.
_with_apps = ("applibs", "github:PyDevices/apps/")
_own = ("requests",)
_library = set()
_upstream = set()
_folder = os.path.join(_apps, "apps")
for _app in sorted(os.listdir(_folder)):
    _pkg = os.path.join(_folder, _app, "package.json")
    if not os.path.isfile(_pkg):
        continue
    with open(_pkg) as _f:
        _body = json.load(_f)
    for _dep in _body.get("deps", ()):
        _name = _dep[0]
        if _name.startswith(_with_apps):
            continue
        if _name.startswith("github:PyDevices/omnipython/packages/"):
            _name = _name.rsplit("/", 1)[-1]
        elif ":" in _name or "/" in _name:
            raise ValueError("allapps: %s needs %r, which isn't a package this build can freeze" % (_pkg, _name))
        if os.path.isdir(os.path.join(_modules, _name)):
            if _name not in _named and "all" not in _named:
                raise ValueError("allapps: the app %s needs the module %s: add it to --modules" % (_app, _name))
            continue
        _library.add(_name)
    for _dep in _body.get("upstream", ()):
        if _dep[0] not in _own:
            _upstream.add(_dep[0])



def _emitter_only(path):
    """True when *path* has viper or inline assembler, which a port with no
    native emitter can't compile."""
    with open(path) as f:
        text = f.read()
    return "@micropython.viper" in text or "@micropython.asm_" in text


# A package with such a file goes in without it: castdisplay's castfast is
# viper for a board's audio feed, and castdisplay imports it only if it's
# there. Such a package must require nothing, or its needs would be lost.
_tree = os.environ["OMNIPYTHON_LIBRARY"]
for _name in sorted(_library):
    _root = os.path.join(_tree, _name)
    _files, _left = [], []
    for _path, _dirs, _names in os.walk(os.path.join(_root, _name)):
        _dirs.sort()
        for _f in sorted(_names):
            if _f.endswith(".py"):
                _full = os.path.join(_path, _f)
                (_left if _emitter_only(_full) else _files).append(os.path.relpath(_full, os.path.join(_root, _name)))
    if not _left:
        require(_name, library="omnipython-lib", opt=3)
        continue
    with open(os.path.join(_root, "manifest.py")) as _f:
        if "require(" in _f.read():
            raise ValueError("allapps: %s has %s, which this port can't compile, and requires other packages" % (_name, ", ".join(_left)))
    # stderr: make reads the C module list from this manifest's stdout.
    sys.stderr.write("allapps: %s goes in without %s (viper or assembler)\n" % (_name, ", ".join(_left)))
    package(_name, files=_files, base_path=_root, opt=3)
# A page needs files a board's firmware leaves out: midiports freezes only
# its board transports, and a browser reads MIDI through Web MIDI, other
# tabs and Web Bluetooth, and finds it in Connections through endpoints.
# bledev's Web Bluetooth backend is a host's, so a board leaves it out too.
_for_pages = {
    "midiports": ("webmidi.py", "endpoints.py", "tabs.py", "webble.py"),
    "bledev": ("webble.py",),
}
for _name in sorted(_for_pages):
    if _name not in _library:
        continue
    _have = [f for f in _for_pages[_name] if os.path.isfile(os.path.join(_tree, _name, _name, f))]
    package(_name, files=_have, base_path=os.path.join(_tree, _name), opt=3)
for _name in sorted(_upstream):
    require(_name, opt=3)

include(os.path.join(_apps, "apps"))
