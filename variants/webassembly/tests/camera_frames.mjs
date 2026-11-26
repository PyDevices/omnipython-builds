// The page's camera through _wasm_bridge: it opens once the browser answers,
// scales its frames into a block of an RGB565 picture, hands out a JPEG, says
// when the browser refused, and moves to the camera chosen through
// Module.omnipythonBridge.route while it's open.
//
//   node variants/webassembly/tests/camera_frames.mjs builds/webassembly/omnipython
import path from "node:path";

const dir = path.resolve(process.argv[2]);
const opened = [];
let refuse = null;
let time = 0;

// A browser with a 4 x 2 camera whose every frame is red, and canvases that
// keep what's drawn on them only as far as this test needs.
class FakeVideo {
  constructor() { this.videoWidth = 0; this.videoHeight = 0; this.readyState = 0; }
  set srcObject(stream) { this.stream = stream; if (stream) { this.videoWidth = 4; this.videoHeight = 2; this.readyState = 4; } }
  get srcObject() { return this.stream; }
  get currentTime() { return time; }
  addEventListener(type, fn) { if (type === "loadedmetadata") fn(); }
  async play() {}
  pause() {}
}
class FakeCanvas {
  constructor() { this.width = 0; this.height = 0; this.turns = []; }
  getContext() {
    const canvas = this;
    return {
      setTransform(a, b, c, d) { if (a !== 1 || d !== 1) canvas.turns.push([a, d]); },
      drawImage() {},
      getImageData(x, y, w, h) {
        const data = new Uint8ClampedArray(w * h * 4);
        for (let i = 0; i < data.length; i += 4) { data[i] = 255; data[i + 3] = 255; }
        return { data };
      },
    };
  }
  toDataURL(type, quality) { return "data:" + type + ";base64," + Buffer.from("JPEG" + this.width + "x" + this.height + "@" + quality).toString("base64"); }
}
const canvases = [];
globalThis.document = {
  createElement: (tag) => {
    if (tag === "video") return new FakeVideo();
    const canvas = new FakeCanvas(); canvases.push(canvas); return canvas;
  },
};
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  value: { mediaDevices: { getUserMedia: async (c) => {
    if (refuse) { const error = new Error("refused"); error.name = refuse; throw error; }
    opened.push(JSON.stringify(c.video));
    return { getTracks: () => [{ stop() {} }] };
  } } },
});

const { loadMicroPython } = await import(path.join(dir, "micropython.mjs"));
const mp = await loadMicroPython({ stdout: (l) => console.log(l), stderr: (l) => console.error(l) });
// One line is an expression, and its value comes back; more are run.
const py = (code) => {
  if (code.includes("\n")) return mp.runPython(code);
  mp.runPython("_r = " + code);
  return mp.globals.get("_r");
};
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));
const fail = (what) => { console.error("FAIL", what); process.exitCode = 1; };

py("import _wasm_bridge as b\nb.camera_open()");
await settle();
if (py("b.camera_state()") !== 1) fail("the camera didn't open: " + py("b.camera_state()"));
if (py("str(b.camera_size())") !== "(4, 2)") fail("size " + py("str(b.camera_size())"));
if (opened.join() !== "true") fail("opened " + opened.join());

// A 2 x 2 block at (1, 1) of a 4 x 3 picture: red there, nothing elsewhere.
time = 1;
py("pic = bytearray(4 * 3 * 2)\nwrote = b.camera_readinto(pic, 4, 3, 1, 1, 2, 2, 2)");
if (py("wrote") !== 1) fail("no frame written");
if (py("bytes(pic[10:14]).hex()") !== "00f800f8") fail("the block holds " + py("bytes(pic[10:14]).hex()"));
if (py("bytes(pic[0:10]) == bytes(10) and bytes(pic[14:18]) == bytes(4)") !== true) fail("wrote outside the block: " + py("bytes(pic).hex()"));
if (!canvases.some((c) => c.turns.some(([a, d]) => a === -1 && d === 1))) fail("the mirror wasn't drawn");
if (py("b.camera_readinto(pic, 4, 3, 0, 0, 4, 3, 0)") !== 0) fail("the same frame twice");
time = 2;
py("b.camera_readinto(pic, 4, 3, 0, 0, 1, 1, 4)");
if (py("bytes(pic[0:2]).hex()") !== "f800") fail("swap gave " + py("bytes(pic[0:2]).hex()"));
if (py("b.camera_jpeg(85, 0)") === null || !py("b.camera_jpeg(85, 0).decode()").startsWith("JPEG4x2@0.85")) fail("jpeg " + py("b.camera_jpeg(85, 0)"));
try { py("b.camera_readinto(pic, 4, 3, 3, 0, 2, 1, 0)"); fail("a block outside the picture was taken"); } catch (_) { /* ValueError */ }

// Choosing another camera while this one is open moves it there.
await globalThis.Module.omnipythonBridge.route("camera", "usb");
if (opened.join(" ") !== 'true {"deviceId":{"exact":"usb"}}') fail("chose and opened " + opened.join(" "));
py("b.camera_close()");
if (py("b.camera_state()") >= 0) fail("still open after close");

refuse = "NotAllowedError";
py("b.camera_open()");
await settle();
if (py("b.camera_state()") !== -1) fail("a refusal reads " + py("b.camera_state()"));
refuse = "NotFoundError";
py("b.camera_open()");
await settle();
if (py("b.camera_state()") !== -2) fail("no camera reads " + py("b.camera_state()"));
py("b.camera_close()");

console.log(process.exitCode ? "camera_frames: failed" : "camera_frames: ok");
