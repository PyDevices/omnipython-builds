# Build the all-apps browser page

The all-apps page runs Home and every app of the
[apps repository](https://github.com/PyDevices/apps) in a browser tab. Each app
is frozen into one WebAssembly runtime, with everything it imports, so the page
fetches nothing at run time and no package comes from the index. An app that
can't work in a browser is still in, and says what it lacks.

It's published at <https://apps.omnipython.org/>, where a browser can install
it as an app and open it offline.

## Build it

```bash
./scripts/build_wasm_allapps.py --apps-ref main --omnipython-ref main --out site
```

That's the whole build. Its three inputs:

- `--apps-ref`: a branch, tag or full commit of PyDevices/apps. Its `apps/`
  folder is frozen with its shared libraries in `lib/`.
- `--omnipython-ref`: a branch, tag or full commit of PyDevices/omnipython,
  which the library of Python-only packages (OmniPython itself, vtterm,
  castdisplay and the rest) is built from.
- `--out`: the folder the page is written to. It's emptied first.

`--apps PATH` and `--omnipython PATH` take local checkouts instead of refs,
to try a change before it's pushed. Everything else is pinned in
[`DEPENDENCIES.lock`](https://github.com/PyDevices/omnipython-builds/blob/main/DEPENDENCIES.lock)
as for every other build: MicroPython and the patch series, LVGL, the modules
and emsdk. The fetched checkouts go in `deps/allapps/`.

The first build fetches MicroPython, LVGL and the modules as any webassembly
build does, and emsdk if `deps/` has none (see
[Build for a board](build-for-a-board.md)). With emsdk already there, a first
build took about 4 minutes on 4 cores; a build from scratch after that took
2 minutes 25 seconds, and used under 400 MB of memory.

## What comes out

| File | What it is |
|---|---|
| `index.html` | The page. It boots into Home on an 800x480 screen. |
| `micropython.mjs`, `micropython.wasm` | The runtime, 0.3 MB and 12.3 MB (5.3 MB gzipped). |
| `micropython.wasm.provenance` | Its size, hash, patch series and the commit of every source. |
| `allapps.json` | The apps and omnipython commits it was built from, and the build's id. |
| `manifest.webmanifest`, `icon.svg`, `icon-maskable.svg` | What makes the page an installable web app: its name, icons and window. |
| `sw.js` | The service worker, which keeps the page and its runtime so it opens offline. The build writes its id into it. |

The page takes `?width=` and `?height=` to size the screen, and `?app=clock`
to start in an app, as a restart into one does.

## Home or Watch

One build boots either home screen. By default the page boots Home, the grid
of tabs. `?home=watch` boots Watch instead, the watch face with its wheel of
apps, as Home's `main.py` picks on a board with a round or small screen. Add
`?round=1` for a round screen, so Watch keeps its text inside the circle:

```text
http://localhost:8000/?home=watch&round=1&width=240&height=240
```

In a browser Watch leaves out the line under its face (the date, battery,
steps and network on a board): a page has none of the board's to show. It
needs no parameter, since Watch knows when it runs in a page.

`?home=` takes any installed app's name; one that isn't installed boots Home,
and the log says so. Another page that loads the runtime itself does the
same in its own boot code: set `board_config.display_drv.round = True` before
importing `display_driver` for a round screen, and set `launcher.home` after
`launcher.scan("apps")`.

## Serve it and look

Any static server works, as long as it serves `.wasm` as
`application/wasm` (Python's does):

```bash
python3 -m http.server -d site 8000
```

Then open http://localhost:8000/. Home should show its tabs within a few
seconds. Typing works once the canvas has focus: click it first.

## What goes in

The build is the webassembly port's `allapps` variant
([`variants/webassembly/allapps`](https://github.com/PyDevices/omnipython-builds/tree/main/variants/webassembly/allapps)).
Its manifest starts from the omnipython variant's content, every module
(`--modules all,pdwidgets`), then reads each app's `package.json`, as `omip`
would, and freezes what those list:

- a module of this repository is already in, through `all`;
- a package of the omnipython library is required from it, at the
  `--omnipython-ref` you named;
- an `upstream` package comes from micropython-lib, except `requests`: the
  variant's own Fetch-backed `requests` stands in for it.

`tflite` goes in as well, which `all` leaves out, so Wake word runs its model
in the page. The model files the apps look for in a `models` folder are in
the page's `/models`: Wake word's "Hey Jarvis" (`hey_jarvis.json` and
`hey_jarvis.tflite`, 52 KB), fetched at the commit `DEPENDENCIES.lock` pins
for `micro-wake-word-models`. The page asks for the microphone at the first
click or key press after an app opens it.

Then the apps repository's own `apps/manifest.py` freezes every app as the
package `frozen_apps`, which Home lists, and its `lib/` folders under their
own names. Upstream's `uasyncio` shim goes in too, as it does on boards, for
app code that imports asyncio by its old name. A package file with viper or
inline assembler can't be compiled
for this port, so it's left out, and the build says which: castdisplay goes
in without `castfast.py`, which it only imports where it's there.

## How it differs from the shared browser build

The shared build (the omnipython variant) is what the website, the docs'
live examples and workbench load: a runtime with the OmniPython stack, into
which each page writes its own program. It's rebuilt from the pins whenever
they change, by the WebAssembly runtime workflow.

The all-apps build is that runtime plus every app and app library, tflite
and the wake word model, 2 MB more, and a page that starts Home. It's built from the apps and omnipython
refs you choose, not from the pins, and only when someone asks for it.

## Use it from another site

Another page can load the published runtime instead of keeping a copy:

```js
const { loadMicroPython } = await import("https://apps.omnipython.org/micropython.mjs");
```

The runtime finds `micropython.wasm` beside itself. GitHub Pages serves both
with `Access-Control-Allow-Origin: *`, and the wasm as `application/wasm`, so
any origin may load them. Your page then boots the launcher itself, as
[Home or Watch](#home-or-watch) says. It always gets the newest published
build.

## Offline and updates

The page registers `sw.js`, which stores the page, the runtime and the icons
the first time it runs. After that it opens with no network, at any of its
addresses (`?home=watch`, `?app=clock`).

Each build has its own id, a hash of the runtime and the page files, which
`allapps.json` records and `sw.js` carries. When a new build is published,
the browser notices the changed `sw.js` the next time the page opens and
fetches the new build beside the old one. The page shows "A new version is
ready" with a Reload button; the new build takes over when you press it, or
when every window of the page has closed. The old copy is deleted then.

## What the page keeps

What apps save under `/data` stays between visits, as it does on a board:
the ZIP code Weather was given, the settings, the apps you've hidden. The
page keeps that folder in the browser's IndexedDB, for its own address, and
writes changes back every two seconds and when the page is hidden. Clearing
the site's data in the browser forgets it. Where IndexedDB is refused, as in
some private windows, `/data` lasts until the page closes and the log says
so.

Weather opens on the forecast for where the visitor is: it looks the place up
from the visitor's public IP address, as a board does when it joins a
network. Hold the screen for the ZIP pad to choose another place, which is
then kept.

## In CI

The [All-apps browser page](https://github.com/PyDevices/omnipython-builds/actions/workflows/wasm-allapps.yml)
workflow builds the page, checks that the runtime starts and imports Home,
runs Wake word's model on a spoken "Hey Jarvis"
(`variants/webassembly/tests/wakeword.mjs`), and uploads it as the `allapps-page` artifact. On `main` it then asks the
[apps.omnipython.org](https://github.com/PyDevices/apps.omnipython.org)
repository to publish that artifact: its workflow downloads the page from
this run and deploys it to its GitHub Pages site. No build output is
committed anywhere. The workflow runs:

- when the apps repository publishes a release, which sends an
  `apps-release` event naming its tag; that tag and omnipython's `main` are
  built;
- on a pull request that changes the page's build, its variant or tflite,
  with apps and omnipython `main`; it never publishes;
- by hand: open the workflow, choose **Run workflow**, and give the two refs.
  Untick **publish** to build without publishing; a run from any branch but
  `main` never publishes.

To put an earlier build back, run apps.omnipython.org's publish workflow by
hand with the run id of the build you want: it deploys that run's artifact
again, for as long as GitHub keeps it (90 days). For an older build, run this
workflow by hand with the commits it was made from; every build's
`allapps.json` names them, and <https://apps.omnipython.org/allapps.json>
names the ones live now.

A job of your own needs the
same: a checkout of this repository, emsdk (the dev container's `install.sh`
packages, or any machine with git, Python 3 and a C toolchain, since the
build fetches emsdk at its pin), and room for the build tree. Caching `deps/`
saves fetching emsdk and the library's sources again.
