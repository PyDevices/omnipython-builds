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
``micropython.wasm.provenance``, ``allapps.json``, which records the commits
that went in, the web app's manifest, icons and service worker, and
``detect.mjs`` with ONNX Runtime Web in ``ort/`` and YOLOX-nano in ``models/``,
which run Object detection.
``--apps`` and ``--omnipython`` take local checkouts
instead of refs, to try a change before it's pushed.

Serve the folder with any static server, for instance
``python3 -m http.server -d site 8000``, and open http://localhost:8000/.
docs/guides/build-the-all-apps-page.md has the rest.
"""

import argparse
import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ORG = "https://github.com/PyDevices/"
VARIANT = "allapps"
PAGE = REPO / "variants" / "webassembly" / VARIANT
# The page and what makes it an installable web app: its manifest, icons and
# service worker, which keeps the page and its runtime for offline use.
# detect.mjs is Object detection's page side (below).
PAGE_FILES = ("index.html", "manifest.webmanifest", "icon.svg", "icon-maskable.svg", "sw.js", "detect.mjs")
BUILD = REPO / "builds" / "webassembly" / VARIANT
# Every module of this repository ("all"), and pdwidgets, which "all" leaves
# out, as the shared browser build has.
MODULES = "all,pdwidgets"
RUNTIME = ("micropython.mjs", "micropython.wasm")
# Object detection: the page's espdl runs YOLOX-nano with ONNX Runtime Web, which
# ships in the page's ort/ folder at the version DEPENDENCIES.lock pins; these
# are the files of its npm package that run it on WebGPU, WebGL and the CPU.
# The npm registry's SHA-512 of that package, checked before anything is used.
ORT = "onnxruntime-web"
ORT_SHA512 = "5GeH+bWQ+HxM10z7erGlsWqryrwMbSvm/1tkIsKTT48g0fI19VXVVC435t4t7VsPdSQeS7NmuZPXrQ73k82URw=="
ORT_FILES = ("ort.all.min.mjs", "ort-wasm-simd-threaded.jsep.mjs", "ort-wasm-simd-threaded.jsep.wasm")
# The model is Megvii's YOLOX-nano (Apache-2.0), the ONNX file of the YOLOX
# release DEPENDENCIES.lock pins, with its SHA-256 here. It ships in the
# page's models/ folder with YOLOX's licence beside it, and is fetched from
# there only when Object detection first opens. /models/yolo11n_coco.espdl,
# where the Detect app looks for its model, is a note of where that is.
DETECT = "yolox-nano"
DETECT_MODEL = "yolo11n_coco.espdl"
DETECT_FILE = "models/yolox_nano.onnx"
DETECT_SHA256 = "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d"
DETECT_INPUT = 416
# YOLOX's licence at the commit of the pinned release's tag.
DETECT_LICENSE = "models/LICENSE-yolox.txt"
DETECT_LICENSE_URL = ("https://raw.githubusercontent.com/Megvii-BaseDetection/YOLOX/"
                      "e1052df71842031413f6030723c3607b839c80ce/LICENSE")
DETECT_LICENSE_SHA256 = "577c03d505ec80f667ebf96ebd0cc4f6825c817ca1088ee348c48aaabd51bd92"


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


def fetch_ort(dest, work):
    """ONNX Runtime Web's page files, from its pinned npm package (kept in
    *work*), in *dest*/ort. Returns its version."""
    sys.path.insert(0, str(REPO / "scripts"))
    import pins

    pin = pins.get(ORT, REPO)
    cache = work / ("%s-%s.tgz" % (ORT, pin.ref))
    if not cache.is_file():
        say("fetching %s" % pin.url)
        cache.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(pin.url, timeout=120) as r:
            cache.write_bytes(r.read())
    data = cache.read_bytes()
    got = base64.b64encode(hashlib.sha512(data).digest()).decode()
    if got != ORT_SHA512:
        cache.unlink()
        die("%s is not the %s %s the npm registry published (sha512 %s)" % (pin.url, ORT, pin.ref, got))
    ort = dest / "ort"
    ort.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        version = json.load(t.extractfile("package/package.json"))["version"]
        if version != pin.ref:
            die("%s says it is %s %s, not %s" % (pin.url, ORT, version, pin.ref))
        for name in ORT_FILES:
            # Each carries its MIT licence notice in its first lines.
            (ort / name).write_bytes(t.extractfile("package/dist/" + name).read())
    return version


def fetch_checked(url, sha256, cache):
    """*url*'s bytes, kept in *cache*, if their SHA-256 is *sha256*."""
    if not cache.is_file():
        say("fetching %s" % url)
        cache.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(url, timeout=120) as r:
            cache.write_bytes(r.read())
    data = cache.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != sha256:
        cache.unlink()
        die("%s is not the file this build expects (sha256 %s, not %s)" % (url, got, sha256))
    return data


def fetch_model(work):
    """YOLOX-nano's ONNX file and YOLOX's licence, from the pinned release,
    checked. Returns (model bytes, licence bytes, the pin)."""
    sys.path.insert(0, str(REPO / "scripts"))
    import pins

    pin = pins.get(DETECT, REPO)
    model = fetch_checked(pin.url, DETECT_SHA256, work / ("%s-%s.onnx" % (DETECT, pin.ref)))
    licence = fetch_checked(DETECT_LICENSE_URL, DETECT_LICENSE_SHA256, work / "LICENSE-yolox.txt")
    return model, licence, pin


def detect_note(size):
    """The page's /models/yolo11n_coco.espdl: where Object detection finds its model."""
    return json.dumps({"url": DETECT_FILE, "bytes": size, "sha256": DETECT_SHA256, "input": DETECT_INPUT,
                       "model": "YOLOX-nano", "license": "Apache-2.0"}, indent=1) + "\n"


def page_models(dest, size):
    """The folder the page carries as /models, in *dest*, made again each time."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    (dest / DETECT_MODEL).write_text(detect_note(size))
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
    model, licence, model_pin = fetch_model(work)
    models = page_models(work / "models" / "page", len(model))
    env = dict(os.environ, OMNIPYTHON_APPS=str(apps_dir), OMNIPYTHON_MODELS=str(models))
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
    for name in PAGE_FILES:
        shutil.copyfile(PAGE / name, out / name)
    # A new runtime is a new service worker, so a browser that has the page
    # installed picks the new build up.
    build_id = hashlib.sha256((out / "micropython.wasm").read_bytes()
                              + (out / "micropython.mjs").read_bytes()
                              + b"".join((PAGE / name).read_bytes() for name in PAGE_FILES)).hexdigest()[:16]
    sw = out / "sw.js"
    sw.write_text(sw.read_text().replace("__BUILD__", build_id))
    ort_version = fetch_ort(out, work)
    (out / DETECT_FILE).parent.mkdir()
    (out / DETECT_FILE).write_bytes(model)
    (out / DETECT_LICENSE).write_bytes(licence)
    # In a container the checkout may belong to another user, and git won't
    # read it; CI says its commit in GITHUB_SHA.
    r = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, text=True)
    builds = {"commit": r.stdout.strip() if r.returncode == 0 else os.environ.get("GITHUB_SHA")}
    record = {"apps": apps_rec, "omnipython": omni_rec, "omnipython-builds": builds,
              "variant": VARIANT, "modules": MODULES, "build": build_id,
              "onnxruntime-web": ort_version,
              "detect_model": {"url": model_pin.url, "release": model_pin.ref, "sha256": DETECT_SHA256},
              "bytes": {name: (out / name).stat().st_size for name in RUNTIME}}
    (out / "allapps.json").write_text(json.dumps(record, indent=1) + "\n")
    wasm_mb = record["bytes"]["micropython.wasm"] / 1e6
    say("wrote %s (micropython.wasm %.1f MB)" % (out, wasm_mb))
    say("serve it with: python3 -m http.server -d %s 8000" % out)


if __name__ == "__main__":
    main()
