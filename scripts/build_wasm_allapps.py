#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Build the all-apps browser page: Home and every app, frozen into one runtime.

    python3 scripts/build_wasm_allapps.py --apps-ref main --omnipython-ref main --out site/

It fetches the apps repository and the omnipython repository at the refs you
name (a branch, a tag or a full commit), builds the webassembly port's
``allapps`` variant from them with ``build_mp.py``, and writes a folder you
can serve as it is: ``index.html``, ``micropython.mjs``, ``micropython.wasm``,
``micropython.wasm.provenance`` and ``allapps.json``, which records the
commits that went in. ``--apps`` and ``--omnipython`` take local checkouts
instead of refs, to try a change before it's pushed.

Serve the folder with any static server, for instance
``python3 -m http.server -d site 8000``, and open http://localhost:8000/.
docs/guides/build-the-all-apps-page.md has the rest.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ORG = "https://github.com/PyDevices/"
VARIANT = "allapps"
PAGE = REPO / "variants" / "webassembly" / VARIANT / "index.html"
BUILD = REPO / "builds" / "webassembly" / VARIANT
# Every module of this repository ("all"), and pdwidgets, which "all" leaves
# out, as the shared browser build has.
MODULES = "all,pdwidgets"
RUNTIME = ("micropython.mjs", "micropython.wasm")


def say(text):
    print("build_wasm_allapps:", text, flush=True)


def die(text):
    sys.exit("build_wasm_allapps: " + text)


def git(*args, cwd=None):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        die("git %s failed:\n%s%s" % (" ".join(args), r.stdout, r.stderr))
    return r.stdout.strip()


def fetch(repo, ref, dest):
    """A shallow checkout of *repo* at *ref* in *dest*, made again each time."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    git("init", "-q", cwd=dest)
    git("fetch", "-q", "--depth", "1", ORG + repo + ".git", ref, cwd=dest)
    git("checkout", "-q", "FETCH_HEAD", cwd=dest)
    return dest


def describe(checkout, ref):
    head = git("rev-parse", "HEAD", cwd=checkout)
    dirty = bool(git("status", "--porcelain", cwd=checkout))
    return {"ref": ref, "commit": head, "dirty": dirty}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    apps = ap.add_mutually_exclusive_group(required=True)
    apps.add_argument("--apps-ref", help="the PyDevices/apps branch, tag or commit to freeze")
    apps.add_argument("--apps", type=Path, help="a local apps checkout to freeze, as it is")
    omni = ap.add_mutually_exclusive_group(required=True)
    omni.add_argument("--omnipython-ref", help="the PyDevices/omnipython branch, tag or commit to build the library from")
    omni.add_argument("--omnipython", type=Path, help="a local omnipython checkout, as it is")
    ap.add_argument("--out", type=Path, required=True, help="the folder to write the page into (emptied first)")
    ap.add_argument("--work", type=Path, default=REPO / "deps" / "allapps",
                    help="where fetched checkouts go (default: deps/allapps)")
    ap.add_argument("--clean", action="store_true", help="build from scratch, not on the last build's objects")
    args = ap.parse_args()

    work = args.work.resolve()
    if args.apps:
        apps_dir = args.apps.expanduser().resolve()
        apps_rec = describe(apps_dir, None)
    else:
        say("fetching apps at %s" % args.apps_ref)
        apps_dir = fetch("apps", args.apps_ref, work / "apps")
        apps_rec = describe(apps_dir, args.apps_ref)
    if not (apps_dir / "apps" / "manifest.py").is_file():
        die("%s is not an apps checkout: it has no apps/manifest.py" % apps_dir)
    if args.omnipython:
        omni_dir = args.omnipython.expanduser().resolve()
        omni_rec = describe(omni_dir, None)
    else:
        say("fetching omnipython at %s" % args.omnipython_ref)
        omni_dir = fetch("omnipython", args.omnipython_ref, work / "omnipython")
        omni_rec = describe(omni_dir, args.omnipython_ref)

    cmd = [sys.executable, str(REPO / "build_mp.py"), "--port", "webassembly", "--variant", VARIANT,
           "--modules", MODULES, "--library-checkout", str(omni_dir),
           "--library-source", "applibs=%s" % apps_dir]
    if args.clean:
        cmd.append("--clean")
    env = dict(os.environ, OMNIPYTHON_APPS=str(apps_dir))
    say("building: " + " ".join(cmd))
    if subprocess.run(cmd, cwd=REPO, env=env).returncode != 0:
        die("build_mp.py failed")
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "wasm_provenance.py"), str(BUILD)])
    if r.returncode != 0:
        die("wasm_provenance.py failed")

    out = args.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in RUNTIME + ("micropython.wasm.provenance",):
        shutil.copyfile(BUILD / name, out / name)
    shutil.copyfile(PAGE, out / "index.html")
    # In a container the checkout may belong to another user, and git won't
    # read it; CI says its commit in GITHUB_SHA.
    r = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True)
    builds = {"commit": r.stdout.strip() if r.returncode == 0 else os.environ.get("GITHUB_SHA")}
    record = {"apps": apps_rec, "omnipython": omni_rec, "omnipython-builds": builds,
              "variant": VARIANT, "modules": MODULES,
              "bytes": {name: (out / name).stat().st_size for name in RUNTIME}}
    (out / "allapps.json").write_text(json.dumps(record, indent=1) + "\n")
    wasm_mb = record["bytes"]["micropython.wasm"] / 1e6
    say("wrote %s (micropython.wasm %.1f MB)" % (out, wasm_mb))
    say("serve it with: python3 -m http.server -d %s 8000" % out)


if __name__ == "__main__":
    main()
