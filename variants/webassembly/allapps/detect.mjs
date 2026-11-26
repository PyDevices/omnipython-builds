// Object detection for the all-apps page: YOLOX-nano through ONNX Runtime
// Web, behind the page's `espdl.YOLO11` (vision/espdl.py), so the Detect app
// runs as it does on a board.
//
// ONNX Runtime Web ships with the page, in ./ort/, at the version
// DEPENDENCIES.lock pins, and loads the first time a detector opens. The
// model, Megvii's YOLOX-nano (Apache-2.0), ships with the page too, in
// ./models/, but it is fetched only the first time it's used, from the
// address the page's /models/yolo11n_coco.espdl names, with a note on screen
// while it downloads. The browser keeps a copy (the Cache API), so it
// downloads once.
//
// Python polls: open() and run() return at once, and the handle's `state`,
// `busy`, `result` and `error` say where they are. That lets the runtime
// sleep through _wasm_bridge.sleep_ms while ONNX Runtime works.

const ORT_DIR = new URL("./ort/", import.meta.url).href;
const CACHE = "omnipython-models";
// Execution providers, best first. WebGPU where the browser has it, then
// WebGL, then plain WebAssembly on the CPU, which every browser runs.
export const PROVIDERS = ["webgpu", "webgl", "wasm"];

let runtime = null;

/** Use *ort* as ONNX Runtime instead of the page's own copy (for tests). */
export function useRuntime(ort) {
  runtime = Promise.resolve(ort);
}

function loadRuntime() {
  if (!runtime) {
    runtime = import(ORT_DIR + "ort.all.min.mjs").then((ort) => {
      ort.env.wasm.wasmPaths = ORT_DIR;
      // Threads need a cross-origin isolated page, which this one isn't.
      ort.env.wasm.numThreads = globalThis.crossOriginIsolated ? Math.min(4, navigator.hardwareConcurrency || 1) : 1;
      return ort;
    });
    runtime.catch(() => { runtime = null; });
  }
  return runtime;
}

// The note on screen while the model downloads: a bar along the top of the
// page, over the canvas, gone once the model is in.
function note(text) {
  const doc = globalThis.document;
  if (!doc || !doc.body) return;
  let el = doc.getElementById("model-note");
  if (!el) {
    el = doc.createElement("div");
    el.id = "model-note";
    el.setAttribute("role", "status");
    el.style.cssText = "position:fixed;left:0;right:0;top:0;padding:8px 16px;background:#1d3557;color:#fff;" +
      "font:14px system-ui,sans-serif;z-index:10;text-align:center";
    doc.body.appendChild(el);
  }
  if (text) {
    el.textContent = text;
    el.hidden = false;
  } else {
    el.hidden = true;
  }
}

const mb = (n) => (n / 1e6).toFixed(1);

async function sha256(bytes) {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

async function openCache() {
  try {
    return globalThis.caches ? await caches.open(CACHE) : null;
  } catch {
    return null; // a private window may refuse storage
  }
}

/** The model's bytes: from the browser's cache, or downloaded with the note up. */
export async function fetchModel(spec, say = note) {
  // The page's note names the model relative to the page.
  const base = globalThis.document?.baseURI || globalThis.location?.href;
  if (base) spec = { ...spec, url: new URL(spec.url, base).href };
  const cache = await openCache();
  if (cache) {
    const hit = await cache.match(spec.url);
    if (hit) {
      const bytes = new Uint8Array(await hit.arrayBuffer());
      if (!spec.sha256 || (await sha256(bytes)) === spec.sha256) return { bytes, from: "cache" };
      await cache.delete(spec.url);
    }
  }
  const host = base ? new URL(spec.url).host : spec.url;
  const total = spec.bytes || 0;
  const about = [spec.license, total ? mb(total) + " MB" : ""].filter(Boolean).join(", ");
  const what = `Object detection is downloading its model, ${spec.model || "a detector"}` +
    `${about ? " (" + about + ")" : ""}, from ${host}. It's kept for next time.`;
  say(what);
  try {
    const response = await fetch(spec.url, { mode: "cors" });
    if (!response.ok) throw new Error(`the model's download failed: ${response.status} from ${spec.url}`);
    const length = total || Number(response.headers.get("content-length")) || 0;
    let bytes;
    if (response.body && response.body.getReader) {
      const reader = response.body.getReader();
      const parts = [];
      let got = 0;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        parts.push(value);
        got += value.length;
        say(what + (length ? ` ${Math.min(100, Math.round((got * 100) / length))}%` : ` ${mb(got)} MB`));
      }
      bytes = new Uint8Array(got);
      let at = 0;
      for (const p of parts) { bytes.set(p, at); at += p.length; }
    } else {
      bytes = new Uint8Array(await response.arrayBuffer());
    }
    if (spec.sha256) {
      const got = await sha256(bytes);
      if (got !== spec.sha256) throw new Error(`the model downloaded from ${spec.url} isn't the one this page expects (SHA-256 ${got})`);
    }
    if (cache) {
      try {
        await cache.put(spec.url, new Response(bytes, { headers: { "content-type": "application/octet-stream" } }));
      } catch { /* full or refused: it downloads again next time */ }
    }
    return { bytes, from: "network" };
  } finally {
    say("");
  }
}

/**
 * YOLOX's input from an RGB565 (little-endian, as the page's camera writes
 * it) or grayscale picture, as YOLOX's own demo makes it: scaled to fit
 * size x size, keeping its shape, in the top left corner, the rest grey
 * (114), as BGR planes of 0..255 with no normalisation. Returns the tensor
 * data and the scale, to map boxes back.
 */
export function preprocess(pixels, w, h, gray, size) {
  const scale = Math.min(size / w, size / h);
  const nw = Math.max(1, Math.floor(w * scale));
  const nh = Math.max(1, Math.floor(h * scale));
  const plane = size * size;
  const data = new Float32Array(3 * plane).fill(114);
  for (let y = 0; y < nh; y++) {
    const sy = Math.min(h - 1, Math.floor((y + 0.5) / scale));
    const row = y * size;
    for (let x = 0; x < nw; x++) {
      const sx = Math.min(w - 1, Math.floor((x + 0.5) / scale));
      let r, g, b;
      if (gray) {
        r = g = b = pixels[sy * w + sx];
      } else {
        const i = (sy * w + sx) * 2;
        const p = pixels[i] | (pixels[i + 1] << 8);
        r = (((p >> 11) & 31) * 255 + 15) / 31 | 0;
        g = (((p >> 5) & 63) * 255 + 31) / 63 | 0;
        b = ((p & 31) * 255 + 15) / 31 | 0;
      }
      const o = row + x;
      data[o] = b;
      data[plane + o] = g;
      data[2 * plane + o] = r;
    }
  }
  return { data, scale };
}

// YOLOX looks at three grids, one cell each 8, 16 and 32 pixels.
const STRIDES = [8, 16, 32];

function iou(a, b) {
  const x0 = Math.max(a[0], b[0]), y0 = Math.max(a[1], b[1]);
  const x1 = Math.min(a[0] + a[2], b[0] + b[2]), y1 = Math.min(a[1] + a[3], b[1] + b[3]);
  const inter = Math.max(0, x1 - x0) * Math.max(0, y1 - y0);
  const union = a[2] * a[3] + b[2] * b[3] - inter;
  return union > 0 ? inter / union : 0;
}

/**
 * Boxes from YOLOX's output, [1, anchors, 5 + classes]: for each cell of
 * the 8, 16 and 32 pixel grids, its box as offsets from the cell (centre)
 * and log sizes, then how likely it holds an object, then each class's
 * score. A box scores its object score times its best class's. Keeps those
 * scoring at least *score*, suppresses overlaps of one class above *nms*,
 * best *topk* first, as espdl's YOLO11 returns them: [x, y, w, h, score,
 * class] in the picture's pixels.
 */
export function boxes(out, dims, fit, w, h, score, nms, topk, size) {
  const n = dims[1], row = dims[2], classes = row - 5;
  const grids = STRIDES.map((s) => Math.floor(size / s));
  if (grids.reduce((t, g) => t + g * g, 0) !== n) {
    throw new Error(`the model's output has ${n} boxes, not YOLOX's for a ${size} x ${size} input`);
  }
  const found = [];
  let i = 0;
  STRIDES.forEach((stride, k) => {
    const g = grids[k];
    for (let gy = 0; gy < g; gy++) {
      for (let gx = 0; gx < g; gx++, i++) {
        const o = i * row;
        const obj = out[o + 4];
        if (obj < score) continue;
        let best = 0, cls = -1;
        for (let c = 0; c < classes; c++) {
          const s = out[o + 5 + c];
          if (s > best) { best = s; cls = c; }
        }
        best *= obj;
        if (best < score) continue;
        const cx = (out[o] + gx) * stride, cy = (out[o + 1] + gy) * stride;
        const bw = Math.exp(out[o + 2]) * stride, bh = Math.exp(out[o + 3]) * stride;
        let x0 = (cx - bw / 2) / fit.scale, y0 = (cy - bh / 2) / fit.scale;
        let x1 = (cx + bw / 2) / fit.scale, y1 = (cy + bh / 2) / fit.scale;
        x0 = Math.max(0, Math.min(w, x0)); x1 = Math.max(0, Math.min(w, x1));
        y0 = Math.max(0, Math.min(h, y0)); y1 = Math.max(0, Math.min(h, y1));
        if (x1 - x0 < 1 || y1 - y0 < 1) continue;
        found.push([x0, y0, x1 - x0, y1 - y0, best, cls]);
      }
    }
  });
  found.sort((a, b) => b[4] - a[4]);
  const kept = [];
  for (const f of found) {
    if (kept.length >= topk) break;
    if (kept.some((k) => k[5] === f[5] && iou(k, f) > nms)) continue;
    kept.push(f);
  }
  return kept.map(([x, y, bw, bh, s, c]) => [Math.round(x), Math.round(y), Math.round(bw), Math.round(bh), s, c]);
}

async function session(ort, bytes, size, said) {
  const errors = [];
  const zeros = new ort.Tensor("float32", new Float32Array(3 * size * size), [1, 3, size, size]);
  for (const ep of PROVIDERS) {
    if (ep === "webgpu" && !globalThis.navigator?.gpu) { errors.push("webgpu: this browser has none"); continue; }
    try {
      const s = await ort.InferenceSession.create(bytes, { executionProviders: [ep], graphOptimizationLevel: "all" });
      // A provider may take the model and still fail on its first run.
      await s.run({ [s.inputNames[0]]: zeros });
      return { session: s, provider: ep };
    } catch (e) {
      errors.push(`${ep}: ${e && e.message ? e.message : e}`);
      console.warn(`Object detection: ${ep} didn't run the model, so the next way:`, e && e.message ? e.message : e);
    }
  }
  throw new Error("no way to run the model here: " + errors.join("; "));
}

/**
 * Open a detector on the model *spec* names ({url, bytes, sha256, input,
 * model, license}).
 * Returns a handle at once: its `state` is "loading", then "ready" or
 * "failed" (with `error`).
 */
export function open(spec, score = 0.25, nms = 0.45, topk = 10) {
  if (typeof spec === "string") spec = JSON.parse(spec);
  const size = spec.input || 416;
  const handle = {
    state: "loading", error: "", provider: "", from: "", busy: false, result: "[]", ms: 0,
    score, nms, topk, session: null,
    run(pixels, w, h, gray) {
      if (handle.state !== "ready") throw new Error("the detector isn't open");
      handle.busy = true;
      handle.error = "";
      const t0 = performance.now();
      const fit = preprocess(pixels, w, h, !!gray, size);
      const s = handle.session;
      const input = new handle.ort.Tensor("float32", fit.data, [1, 3, size, size]);
      s.run({ [s.inputNames[0]]: input }).then((outs) => {
        const out = outs[s.outputNames[0]];
        handle.result = JSON.stringify(boxes(out.data, out.dims, fit, w, h, handle.score, handle.nms, handle.topk, size));
        handle.ms = Math.round(performance.now() - t0);
      }, (e) => {
        handle.error = String(e && e.message ? e.message : e);
        handle.result = "[]";
      }).finally(() => { handle.busy = false; });
    },
    close() {
      const s = handle.session;
      handle.session = null;
      handle.state = "closed";
      if (s && s.release) s.release().catch(() => {});
    },
  };
  (async () => {
    const ort = await loadRuntime();
    const { bytes, from } = await fetchModel(spec);
    handle.from = from;
    const { session: s, provider } = await session(ort, bytes, size);
    if (handle.state === "closed") { s.release && s.release(); return; }
    handle.ort = ort;
    handle.session = s;
    handle.provider = provider;
    handle.state = "ready";
    console.log(`Object detection: ${spec.model || "the model"} on ${provider}, model from ${from === "cache" ? "this browser's cache" : spec.url}`);
  })().catch((e) => {
    handle.error = String(e && e.message ? e.message : e);
    handle.state = "failed";
    console.error("Object detection:", e);
  });
  return handle;
}

globalThis.omnipythonDetect = { open, fetchModel, preprocess, boxes, useRuntime, PROVIDERS };
