// Object detection in the all-apps page: the page's espdl.YOLO11 and image,
// called as the Detect app calls them, over detect.mjs with a stand-in for
// ONNX Runtime. It checks the model is fetched from the address the note in
// /models names, with the note on screen and its SHA-256 checked; that the
// picture reaches the model letterboxed; that providers fall back in order;
// and that boxes come back in the picture's pixels, thresholded and with
// overlaps suppressed.
//
//   node variants/webassembly/tests/detect.mjs builds/allapps-page
import { createHash } from "node:crypto";
import path from "node:path";

const dir = path.resolve(process.argv[2]);
let failures = 0;
const check = (ok, what) => {
  console.log((ok ? "ok   " : "FAIL ") + what);
  if (!ok) failures++;
};

// The page around the runtime: a body the note goes in, and every text it showed.
const notes = [];
const note = { hidden: true, set textContent(t) { notes.push(t); }, setAttribute() {}, style: {} };
globalThis.document = {
  baseURI: "file://" + dir + "/",
  body: { appendChild() {} },
  getElementById: (id) => (id === "model-note" && note.attached ? note : null),
  createElement: () => { note.attached = true; return note; },
};

// The model, as the network serves it.
const MODEL = new TextEncoder().encode("a stand-in for YOLO11n");
const MODEL_SHA = createHash("sha256").update(MODEL).digest("hex");
const fetched = [];
globalThis.fetch = async (url, opts) => {
  fetched.push([String(url), opts && opts.mode]);
  const body = new ReadableStream({ start(c) { c.enqueue(MODEL.slice(0, 10)); c.enqueue(MODEL.slice(10)); c.close(); } });
  return { ok: true, status: 200, headers: new Map([["content-length", String(MODEL.length)]]), body };
};

// ONNX Runtime: WebGL refuses the model, the CPU takes it. Its output is
// YOLO11's [1, 84, anchors] with three anchors: a person, the same person
// again a little weaker (suppressed), and a cup under the score.
const SIZE = 320;
const tried = [];
const inputs = [];
class Tensor {
  constructor(type, data, dims) { this.type = type; this.data = data; this.dims = dims; }
}
function output() {
  const n = 3, out = new Float32Array(84 * n);
  const put = (i, cx, cy, w, h, cls, s) => {
    out[i] = cx; out[n + i] = cy; out[2 * n + i] = w; out[3 * n + i] = h; out[(4 + cls) * n + i] = s;
  };
  put(0, 160, 160, 160, 80, 0, 0.9);
  put(1, 162, 160, 160, 80, 0, 0.8);
  put(2, 40, 120, 20, 20, 41, 0.1);
  return new Tensor("float32", out, [1, 84, n]);
}
const ort = {
  Tensor,
  InferenceSession: {
    async create(bytes, opts) {
      const ep = opts.executionProviders[0];
      tried.push(ep);
      if (Buffer.compare(Buffer.from(bytes), Buffer.from(MODEL)) !== 0) throw new Error("not the downloaded model");
      if (ep === "webgl") throw new Error("WebGL can't run this model");
      return {
        inputNames: ["images"], outputNames: ["output0"],
        async run(feeds) {
          inputs.push(feeds.images);
          await new Promise((r) => setTimeout(r, 30)); // a model takes a while
          return { output0: output() };
        },
        async release() {},
      };
    },
  },
};

const detect = await import(path.join(dir, "detect.mjs"));
detect.useRuntime(ort);
check(globalThis.omnipythonDetect && globalThis.omnipythonDetect.open === detect.open, "detect.mjs registers itself for the page's espdl");

const { loadMicroPython } = await import(path.join(dir, "micropython.mjs"));
const mp = await loadMicroPython({ stdout: (l) => console.log(l), stderr: (l) => console.error(l) });
const py = async (code) => { await mp.runPythonAsync(code); };

// The page's own note says where the real model is.
await py(`
with open("/models/yolo11n_coco.espdl") as f:
    page_note = f.read()
`);
const { url, sha256: sha, bytes, input } = JSON.parse(mp.globals.get("page_note"));
check(/^https?:\/\//.test(url) && /^[0-9a-f]{64}$/.test(sha) && bytes > 1e6 && input > 0,
  `the page's /models/yolo11n_coco.espdl names the model: ${url}, ${bytes} bytes, input ${input}`);

// A note for the stand-in, and a 200 x 100 picture, all red, as the camera
// writes it (RGB565, little-endian).
await py(`
import json
with open("/models/test_note.espdl", "w") as f:
    json.dump({"url": "https://models.example/yolo11n.onnx", "bytes": ${MODEL.length}, "sha256": "${MODEL_SHA}", "input": ${SIZE}}, f)

import espdl
import image

buf = bytearray(200 * 100 * 2)
for i in range(0, len(buf), 2):
    buf[i] = 0x00
    buf[i + 1] = 0xF8
det = espdl.YOLO11("/models/test_note.espdl", score=0.15)
img = image.Image(200, 100, image.RGB565, buffer=buf)

# A timer due while the model looks waits until detect returns, as on a
# board, where nothing runs inside it.
import _wasm_bridge
fired = []
_wasm_bridge.timer_start(77, 0, False, lambda: fired.append(1))
found = json.dumps(det.detect(img))
fired_inside = len(fired)
_wasm_bridge.sleep_ms(0)
fired_after = len(fired)
provider = det.provider
det.deinit()
`);
check(fetched.length === 1 && fetched[0][0] === "https://models.example/yolo11n.onnx" && fetched[0][1] === "cors",
  "the model is fetched once, with CORS, from the note's address: " + JSON.stringify(fetched));
check(notes.some((t) => /downloading its model/.test(t) && /models\.example/.test(t) && /100%/.test(t)),
  "the page says on screen that it is downloading the model, and from where");
check(note.hidden === true, "the note goes once the model is in");
check(JSON.stringify(tried) === JSON.stringify(["webgl", "wasm"]), "with no WebGPU, WebGL then the CPU are tried: " + JSON.stringify(tried));
check(mp.globals.get("provider") === "wasm", "the detector says where it runs: " + mp.globals.get("provider"));

check(mp.globals.get("fired_inside") === 0 && mp.globals.get("fired_after") === 1,
  "no timer runs inside detect(); it runs at the next sleep: " + mp.globals.get("fired_inside") + ", " + mp.globals.get("fired_after"));

const fed = inputs[inputs.length - 1];
const plane = SIZE * SIZE;
const at = (c, x, y) => fed.data[c * plane + y * SIZE + x];
check(JSON.stringify(fed.dims) === JSON.stringify([1, 3, SIZE, SIZE]), "the model gets a 1 x 3 x 320 x 320 picture");
check(at(0, 160, 160) === 1 && at(1, 160, 160) === 0 && at(2, 160, 160) === 0, "red RGB565 reaches it as red, 0 to 1");
check(Math.abs(at(0, 160, 10) - 114 / 255) < 1e-6 && Math.abs(at(0, 160, 310) - 114 / 255) < 1e-6,
  "the picture is letterboxed: grey above and below a wide one");

const got = JSON.parse(mp.globals.get("found"));
check(got.length === 1, "one box: the overlap suppressed, the weak cup dropped: " + JSON.stringify(got));
if (got.length) {
  const [x, y, w, h, score, cls] = got[0];
  check(x === 50 && y === 25 && w === 100 && h === 50, `the box is in the picture's pixels: ${x}, ${y}, ${w} x ${h}`);
  check(Math.abs(score - 0.9) < 1e-6 && cls === 0, "with its score and class: a person, 0.9");
}

// A board's real .espdl in a page says what's wrong instead of failing oddly.
await py(`
with open("/models/board.espdl", "wb") as f:
    f.write(b"EDL2\\x00\\x01\\xff")
try:
    espdl.YOLO11("/models/board.espdl")
    board_error = ""
except OSError as e:
    board_error = str(e)
`);
check(/board's model/.test(mp.globals.get("board_error")), "a board's model file is refused with a reason: " + mp.globals.get("board_error"));

// A download that isn't the model the note names fails the open.
await py(`
with open("/models/bad_note.espdl", "w") as f:
    json.dump({"url": "https://models.example/other.onnx", "sha256": "0" * 64, "input": ${SIZE}}, f)
try:
    espdl.YOLO11("/models/bad_note.espdl")
    bad_error = ""
except OSError as e:
    bad_error = str(e)
`);
check(/isn't the one this page expects/.test(mp.globals.get("bad_error")), "a model with the wrong SHA-256 is refused: " + mp.globals.get("bad_error"));

if (failures) {
  console.log(failures + " failed");
  process.exit(1);
}
console.log("all passed");
