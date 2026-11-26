#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Brad Barnett
#
# SPDX-License-Identifier: MIT

"""Write the firmware download page for a published firmware release.

    stage_firmware_page.py <tag> <page-dir> [--repo OWNER/REPO]
                           [--interpreters-from-release OWNER/REPO]

<tag> names a published release of this repository. A draft is refused: no one
else can download its files. <page-dir> is the `firmware/` folder of the site.
This writes two files there, replacing what the last set left:

    index.html      the page: every board's image as a link to the release,
                    the command that writes it, and how to flash with mcuctl
    firmware.json   the set's description, as the release carries it

The images stay on the release, and the page links each one there. Every file
firmware.json names must be an asset of the release with the size it lists, or
nothing is written.

--interpreters-from-release asks GitHub for the newest final release of that
repository that carries an `interpreters.json` asset, and the page links the
desktop interpreters it lists.
"""
import argparse
import html
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from release_firmware import REPO_SLUG, fs_text, kind_of, write_command  # noqa: E402

MB = 1024 * 1024
PLATFORMS = {"linux-x86_64": "Linux x86-64", "windows-amd64": "Windows x64", "wasm": "WebAssembly"}
# Pins in firmware.json that are OmniPython releases, in the order the page names them.
OMNIPYTHON_PINS = (("omnipython-lib", "OmniPython"), ("audiodsp", "audiodsp"), ("pygraphics", "pygraphics"),
                   ("omnipython-lvgl", "omnipython-lvgl"))


class Failed(Exception):
    pass


def gh_json(path):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if out.returncode:
        raise Failed(f"gh api {path}: {out.stderr.strip()}")
    return json.loads(out.stdout)


def download_json(url):
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def newest_final_with_interpreters(releases):
    """The newest published, non-pre-release release carrying interpreters.json (GitHub lists newest first)."""
    for r in releases:
        if r.get("draft") or r.get("prerelease"):
            continue
        if any(a["name"] == "interpreters.json" for a in r.get("assets", [])):
            return r
    return None


def fetch_interpreters(repo):
    rel = newest_final_with_interpreters(gh_json(f"repos/{repo}/releases?per_page=100"))
    if rel is None:
        return None, None
    asset = next(a for a in rel["assets"] if a["name"] == "interpreters.json")
    return download_json(asset["browser_download_url"]), rel


def check(doc, release):
    """Every file firmware.json names is on the published release with its size: {name: asset}."""
    if release.get("draft"):
        raise Failed(f"{release['tag_name']} is a draft; publish it first, so its files can be downloaded")
    if doc.get("tag") != release["tag_name"]:
        raise Failed(f"firmware.json names {doc.get('tag')}, but the release is {release['tag_name']}")
    assets = {a["name"]: a for a in release.get("assets", [])}
    for b in doc["builds"]:
        for f in b["files"]:
            a = assets.get(f["name"])
            if a is None:
                raise Failed(f"{f['name']} ({b['id']}) is not on release {release['tag_name']}")
            if a["size"] != f["size"]:
                raise Failed(f"{f['name']} is {a['size']} bytes on the release, but firmware.json says {f['size']}")
    return assets


def e(text):
    return html.escape(str(text), quote=True)


def link(asset, text=None):
    return f'<a href="{e(asset["browser_download_url"])}">{e(text or asset["name"])}</a>'


def size(n):
    return f"{n / MB:.1f} MB" if n >= MB else f"{n // 1024:,} KB"


def flash_files(b):
    """The files a person writes to this board, in the order they write them (the GIGA's Wi-Fi image first)."""
    main = next(f for f in b["files"] if f["role"] in ("flash", "uf2"))
    return [f for role in ("wifi", "romfs") for f in b["files"] if f["role"] == role] + [main]


def how(b):
    if any(f["role"] == "uf2" for f in b["files"]):
        return "Hold BOOTSEL while you plug the board in, then copy the .uf2 onto the drive that appears."
    return "\n".join(write_command(b, f) for f in flash_files(b))


ROLE_TEXT = {"wifi": "Wi-Fi image", "romfs": "ROMFS image"}


def download_text(f, several):
    ext = f["name"].rsplit(".", 1)[-1]
    if several:
        return f"{ROLE_TEXT.get(f['role'], 'Firmware')} (.{ext})"
    return f"Download .{ext}"


def board_row(b, assets):
    files = flash_files(b)
    downloads = "<br>".join(
        f"<a href=\"{e(assets[f['name']]['browser_download_url'])}\" title=\"{e(f['name'])}\">"
        f"{e(download_text(f, len(files) > 1))}</a> <span class=\"fw-size\">{size(f['size'])}</span>"
        for f in files)
    return (f"<tr id=\"{e(b['id'])}\"><td>{e(b['label'])}</td>"
            f"<td>{e(kind_of(b))} {e(b['interpreter_version'])}</td>"
            f"<td>{downloads}</td><td><code>{e(b['id'])}</code></td><td>{e(fs_text(b))}</td></tr>")


def board_steps(b, assets):
    shown = {f["name"] for f in flash_files(b)}
    others = [f for f in b["files"] if f["name"] not in shown]
    extra = ", ".join(link(assets[f["name"]]) for f in others)
    return (f"<details class=\"fw-board\"><summary>{e(b['label'])}, {e(kind_of(b))}</summary>"
            f"<pre><code>{e(how(b))}</code></pre>"
            + (f"<p class=\"fw-muted\">Also on the release: {extra}.</p>" if extra else "")
            + "</details>")


def interpreters_block(interp, rel):
    if not interp:
        return "<p class=\"prose\">The desktop interpreters arrive with the next OmniPython release.</p>"
    assets = {a["name"]: a for a in rel.get("assets", [])}
    rows = []
    for name, f in interp["files"].items():
        a = assets.get(name)
        if a is None:
            raise Failed(f"interpreters.json lists {name}, but {rel['tag_name']} has no such file")
        rows.append(f"<tr><td>{link(a)}</td><td>{e(PLATFORMS.get(f.get('platform'), f.get('platform', '')))}</td>"
                    f"<td>{e(f.get('version', ''))}</td><td>{size(f['size'])}</td></tr>")
    return (f"<p class=\"prose\">The same OmniPython on a desktop, from <a href=\"{e(rel['html_url'])}\">OmniPython "
            f"{e(interp['tag'].lstrip('v'))}</a>. On Linux, <code>chmod +x</code> the file and run it.</p>"
            "<div class=\"fw-scroll\"><table class=\"fw-table\"><thead><tr><th>File</th><th>Platform</th>"
            "<th>Version</th><th>Size</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>")


STYLE = """
.fw h2 { margin: 0 0 12px; }
.fw-set, .fw-warn { margin: 20px 0; padding: 14px 18px; border-radius: var(--radius-sm); color: var(--ink); }
.fw-set { border: 1px solid var(--border); border-left: 3px solid var(--accent); background: var(--panel); }
.fw-warn { border: 1px solid rgb(var(--warn-rgb) / 0.5); border-left: 4px solid var(--warn);
  background: rgb(var(--warn-rgb) / 0.09); }
.fw-set p, .fw-warn p { margin: 0 0 6px; }
.fw-set p:last-child, .fw-warn p:last-child { margin-bottom: 0; }
.fw-muted, .fw-size { color: var(--muted); font-size: 0.9rem; }
.fw pre { margin: 8px 0; padding: 12px 14px; overflow-x: auto; border: 1px solid var(--border-soft);
  border-radius: var(--radius-sm); background: var(--bg-soft); }
.fw pre code { font-family: var(--mono); font-size: 0.86rem; white-space: pre; }
.fw-scroll { overflow-x: auto; }
.fw-table { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
.fw-table th, .fw-table td { text-align: left; padding: 8px 10px; border-bottom: 1px solid var(--border-soft);
  vertical-align: top; }
.fw-table td a { word-break: break-all; }
.fw-table td code { white-space: nowrap; }
.fw-table th { color: var(--muted); font-weight: 600; white-space: nowrap; }
.fw-board { margin: 0 0 8px; }
.fw-board summary { cursor: pointer; font-weight: 600; }
"""


def render(doc, release, assets, interp=None, interp_rel=None):
    tag = doc["tag"]
    finals = [f"{label} {doc['pins'][k]['tag'].lstrip('v')}" for k, label in OMNIPYTHON_PINS
              if doc["pins"].get(k, {}).get("tag")]
    preview = ""
    if doc.get("preview"):
        preview = ("<p>The interpreters underneath are previews (" + e("; ".join(doc["preview_reasons"])) + "), "
                   "so the release is marked as a pre-release, and mcuctl takes it with <code>--preview</code>.</p>")
    rows = "\n".join(board_row(b, assets) for b in doc["builds"])
    steps = "\n".join(board_steps(b, assets) for b in doc["builds"])
    notes = []
    if any(b["chip"] == "stm32h747" for b in doc["builds"]):
        notes.append("The Arduino GIGA's images are written in its bootloader (<code>machine.bootloader()</code> at "
                     "the REPL, or double-tap RESET), the Wi-Fi firmware first. The Wi-Fi image only changes when "
                     "its driver does, so after the first time you can leave it out. Write the ROMFS image with "
                     "every update: it holds the firmware's own Python modules. "
                     f"<a href=\"https://github.com/{REPO_SLUG}/blob/main/docs/guides/flash-a-board.md"
                     "#stm32-arduino-giga-r1-wifi\">The flash guide</a> has the steps.")
    if any(b["id"] == "mp-s3-8mb" for b in doc["builds"]):
        notes.append("Some QT Py ESP32-S3 boards have no PSRAM and need the no-PSRAM image. Run "
                     "<code>esptool chip-id</code>: a board with PSRAM has an <code>Embedded PSRAM</code> entry on "
                     "its Features line.")
    notes_html = "\n".join(f"      <p class=\"prose\">{n}</p>" for n in notes)
    example = next((b for b in doc["builds"] if b["id"] == "mp-s3-octal"), doc["builds"][0])
    pre = " --preview" if doc.get("preview") else ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Firmware downloads — OmniPython</title>
  <meta name="description" content="OmniPython firmware for the boards it runs on, MicroPython-compatible and CircuitPython-compatible: a download link for each board's image, and how to flash it.">
  <link rel="icon" href="/assets/img/favicon.svg" type="image/svg+xml">
  <link rel="alternate icon" href="/assets/img/favicon.ico" sizes="16x16 32x32 48x48">
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Nunito:wght@600;700;800&display=swap">
  <link rel="stylesheet" href="/assets/chrome/site.css">
  <style>{STYLE}</style>
</head>
<body>
  <!-- Written by omnipython-builds' scripts/stage_firmware_page.py from release {e(tag)}. Edit that script, not this file. -->
  <div id="pydevices-site-header"></div>

  <main class="wrap fw" style="padding-bottom: 60px;">
    <div class="section-head" style="margin-top: 36px;">
      <h1 style="margin: 0;">Firmware downloads</h1>
      <span class="hint">OmniPython for your board</span>
    </div>
    <p class="prose">Find your board below, download its image and flash it with mcuctl or esptool. The firmware is
      MicroPython-compatible or CircuitPython-compatible, with the OmniPython libraries built in. Every file is on
      <a href="{e(release['html_url'])}">the GitHub release</a>, built there by public CI and attested.</p>

    <div class="fw-set">
      <p><strong>{e(release.get('name') or tag)}</strong> carries {e(', '.join(finals))}. Built {e(doc['built'][:10])}
        by <a href="{e(doc['run'])}">this run</a>.</p>
      {preview}
    </div>

    <div class="fw-warn" role="note">
      <p><strong>Copy your files off the board first, <code>secrets.py</code> above all.</strong>
        A board whose filesystem sits somewhere else in this build starts with an empty one. Compare the Filesystem
        column with yours, and when you come from another firmware (MicroPython to CircuitPython, or back), erase the
        flash first.</p>
    </div>

    <div class="spec-block">
      <h2>Flash with mcuctl</h2>
      <p class="prose"><a href="https://pypi.org/project/mcuctl/">mcuctl</a> fetches a board's image from the release,
        checks its sha256 and writes it to an ESP32 over serial. The build id is the board's id in the table.</p>
      <pre><code>pip install mcuctl
mcuctl firmware download --source omnipython --board {e(example['id'])}{pre}
mcuctl firmware flash --port esp32 --artifact &lt;the file it printed&gt; --device &lt;serial port&gt;</code></pre>
    </div>

    <div class="spec-block">
      <h2>Boards</h2>
      <div class="fw-scroll"><table class="fw-table">
        <thead><tr><th>Board</th><th>Interpreter</th><th>Download</th><th>Build id</th><th>Filesystem</th></tr></thead>
        <tbody>
{rows}
        </tbody>
      </table></div>
    </div>

    <div class="spec-block">
      <h2>Flash by hand</h2>
      <p class="prose">With <a href="https://pypi.org/project/esptool/">esptool</a> for an ESP32, dfu-util for the
        GIGA, or the BOOTSEL drive for an RP2040 or RP2350. Run the command in the folder you downloaded to.</p>
{steps}
{notes_html}
      <p class="prose">Check a download came from our CI:</p>
      <pre><code>gh attestation verify &lt;file&gt; --repo {REPO_SLUG}</code></pre>
      <p class="fw-muted">Each file's sha256, size and offset, and the pins the set was built from, are in
        <a href="firmware.json">firmware.json</a>.</p>
    </div>

    <div class="spec-block">
      <h2>Desktop interpreters</h2>
      {interpreters_block(interp, interp_rel)}
    </div>
  </main>

  <div id="pydevices-site-footer"></div>
  <script src="/assets/chrome/site-chrome.js"></script>
</body>
</html>
"""


def stage(doc, release, page_dir, interp=None, interp_rel=None):
    assets = check(doc, release)
    page = render(doc, release, assets, interp, interp_rel)
    dst = Path(page_dir)
    dst.mkdir(parents=True, exist_ok=True)
    (dst / "index.html").write_text(page)
    (dst / "firmware.json").write_text(json.dumps(doc, indent=1) + "\n")
    return page


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("tag")
    ap.add_argument("page_dir")
    ap.add_argument("--repo", default=REPO_SLUG)
    ap.add_argument("--interpreters-from-release", metavar="OWNER/REPO")
    args = ap.parse_args(argv)
    try:
        release = gh_json(f"repos/{args.repo}/releases/tags/{args.tag}")
        manifest = next((a for a in release.get("assets", []) if a["name"] == "firmware.json"), None)
        if manifest is None:
            raise Failed(f"{args.tag} has no firmware.json")
        doc = download_json(manifest["browser_download_url"])
        interp = interp_rel = None
        if args.interpreters_from_release:
            interp, interp_rel = fetch_interpreters(args.interpreters_from_release)
            if interp is None:
                print(f"note: no final release of {args.interpreters_from_release} carries interpreters.json")
        stage(doc, release, args.page_dir, interp, interp_rel)
    except (Failed, OSError, ValueError, KeyError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    print(f"wrote {args.page_dir}/index.html for {doc['tag']}: {len(doc['builds'])} builds"
          + (f", interpreters from {interp['tag']}" if interp else ", no interpreters"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
