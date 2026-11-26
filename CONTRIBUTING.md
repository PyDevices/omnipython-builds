# Contributing to omnipython-builds

This repository holds our patches to one pinned MicroPython release, our
variants, the C modules that live only here, and the command that builds it all.
A documentation fix, a provenance update, or a narrowly scoped variant or module
fix is a good first contribution.

## Where things are

| Path | What's there |
|---|---|
| [`build.py`](build.py) | The build command. For now it runs [`build_mp.py`](build_mp.py), where the code is. |
| [`DEPENDENCIES.lock`](DEPENDENCIES.lock) | Everything a build fetches when it's missing, one pin per line: the MicroPython commit the patches apply to, the modules, omnipython-lvgl, esp-vision and the toolchains. [`scripts/pins.py`](scripts/pins.py) reads it for every script and workflow. |
| [`modules/`](modules) | The module manifest, `all/`, `tflite/` and `vision/` (esp-vision's), the modules linked or cloned, and the C modules that live only here: `audioif`, `cameraif`, `castif`, `displayif`, `h264enc`, `jpegio`, `mdns`, `offheap`, `pngio`, `ppa`, `svgio`, `tsmux`, `ttfio`, `usbhost`. Each has its own README and tests. |
| `modules/.omnipython-lvgl` | LVGL, its bindings and its ports, which `--modules lvgl` compiles: the sibling checkout, linked, or its `DEPENDENCIES.lock` commit, fetched. |
| [`patches/`](patches) | The patch series and `apply_patches.py`. |
| [`variants/`](variants), [`boards/`](boards) | Our variants and CircuitPython boards. |
| [`scripts/`](scripts) | `pins.py`, `exercise_build.sh`, `release_firmware.py`, `stage_firmware_page.py`, `serve_workbench.sh`, `freeze_list.py`, `update_provenance.py`, `ci_scope.py`, `wasm_provenance.py`. |
| [`tests/`](tests) | The unit tests for `build_mp.py` and `build.py`, the scripts, the provenance record and `lib-overrides`. |
| [`.devcontainer/`](.devcontainer) | One dev container per port. |
| [`docs/`](docs) | The documentation site. |

The reference pages in [the docs](docs/index.md)
describe what each of these does.

## Rules

- Upstream is pinned. Moving the `micropython` line of `DEPENDENCIES.lock` re-validates every patch.
- Never hand-edit a patched tree. Change the patch and prepare again.
- Patches are justified in their headers.
- The build code (`build_mp.py`, run through `build.py`) names no version and no setting. Pins move in `DEPENDENCIES.lock`, and
  esp32 settings live in sdkconfig fragments it finds by convention.
- Publishing binaries is a separate decision from this source repository.

## Run the tests

The build code's unit tests decide things before any build, such as when a build
directory has to be wiped. They need no toolchain:

```bash
PYTHONPATH=tests python3 -m unittest test_build_mp test_freeze_list -v
PYTHONPATH=tests python3 -m unittest test_provenance -v
PYTHONPATH=tests python3 -m unittest test_release_firmware test_stage_firmware_page test_ci_scope -v
PYTHONPATH=tests python3 -m unittest test_lib_overrides -v
```

Each module has its own workflow under [`.github/workflows/`](.github/workflows), named for it.

## Change a patch

Check a patch change with `patches/apply_patches.py --check` before you commit
it. After changing a patch or moving the MicroPython pin, rewrite the record, because CI
fails on a stale file:

```bash
python3 scripts/update_provenance.py
```

## Exercise a build from a bare clone

[`scripts/exercise_build.sh`](scripts/exercise_build.sh) builds every desktop port and two esp32 boards from
a bare clone, checks the failure paths, and writes a report of what should match
on any machine. It needs no board. For a report on builds you already have, name
their folders:

```bash
scripts/exercise_build.sh --report builds/rp2/RPI_PICO2/default ...
```

## The website's WebAssembly runtime

PyDevices.github.io and workbench serve the webassembly port's `omnipython`
variant, built with every module and `pdwidgets`, which `all` leaves out because it is
opt-in and the browser would otherwise have to fetch its many files one by one. When a push to main changes what goes into it
(`DEPENDENCIES.lock`, the patch series, `modules/`, the webassembly
variant), the **WebAssembly runtime** workflow
([`wasm-runtime.yml`](.github/workflows/wasm-runtime.yml)) rebuilds it from the
pins, checks it starts under node and imports what it freezes, stamps
`micropython.wasm.provenance` with
[`scripts/wasm_provenance.py`](scripts/wasm_provenance.py), and opens a pull
request on each site. A newer one closes the older. Run it by hand from
Actions > WebAssembly runtime > Run workflow.

## Firmware sets

A firmware set is every board's flashable file, built from one commit of this
repository by the **Release firmware** workflow
([`release-firmware.yml`](.github/workflows/release-firmware.yml); the cells are
in [`scripts/release_firmware.py`](scripts/release_firmware.py), and
`release_firmware.py cells` lists them). Each cell is one `build.py` call; the
`assemble` job checks every file (checksums, the ESP image magic, the app image
inside the flash image, UF2 blocks, the vector table of a GIGA's main image and the modules in its ROMFS image) and writes `firmware.json`, which records
every file's sha256 and size, the flash offset, and the pins the set was built
from.

### Each board keeps its filesystem

Every MicroPython rp2 cell, and the esp32 cells that say so, names the
filesystem its boards keep from one release to the next (`fs`), and builds with
`--keep-fs` at that size. The other esp32 cells either let `build_mp.py` grow the
app slot to fit (`autosize`), so their filesystem can move, or keep the partition
table of their board variant (`board_table`, `--no-autosize`). An
image that outgrows the flash left beside it fails its build, which says what
size would fit, instead of shipping a set that leaves an updated board with an
empty filesystem. `assemble` checks each filesystem is where its cell says and
records it in `firmware.json`.

When an image no longer fits, build fewer modules into it, or change the cell's
`fs` on purpose. That moves the filesystem on that board, and the draft's notes
say so: they compare the set with the newest published one and name each board
whose filesystem moved.

### Build a set

Actions > Release firmware > Run workflow. A pull request that touches the
recipe, and a run every Monday, build the same cells and keep the files as a run
artifact for 14 days. They publish nothing.

### Put a set on a draft Release

Tick **draft_release** and give a **tag**. After `assemble`, the `draft` job
attests every file (`gh attestation verify <file> --repo
PyDevices/omnipython-builds`) and creates a *draft* GitHub Release holding
the flash images, the `.elf` and `.map` of each build, and `firmware.json`. A
draft is seen only by people who can push to the repository, and GitHub makes no
tag until someone publishes it.

The tag is `v<MicroPython version>-<YYYYMMDD>`. A set built from a preview
MicroPython or CircuitPython only takes a tag that starts with `staged-`, is
created as a pre-release, and its notes open by saying the interpreters are
previews.

### Publish a set

Open the draft on the Releases page, give it a title that names the OmniPython
version it carries, and press Publish. That makes the tag. A preview set stays
a pre-release, so it is never marked Latest, and `mcuctl firmware download
--source omnipython` takes it with `--preview`. Read the notes once before you publish:
they are the release's description from then on.

### The download page

[`scripts/stage_firmware_page.py`](scripts/stage_firmware_page.py) writes the
site's `firmware/` page for a published set: each board's image as a link to
the release, the command that writes it, and the desktop interpreters of the
newest omnipython final. The images stay on the release. It refuses a draft, and
a set whose release is missing a file or has one of another size.

```bash
python3 scripts/stage_firmware_page.py <tag> <site checkout>/firmware \
    --interpreters-from-release PyDevices/omnipython
```

## Build the docs

```bash
python3 -m venv .venv-docs
.venv-docs/bin/pip install -r docs/requirements.txt
.venv-docs/bin/sphinx-build -W --keep-going -b html docs _site
```
