// The page's sound goes to the speaker and comes from the microphone chosen
// through Module.omnipythonBridge.route, before audio is on and while it runs,
// and a speaker the browser refuses is reported once by routeError.
//
//   node variants/webassembly/tests/audio_route.mjs builds/webassembly/omnipython
import path from "node:path";

const dir = path.resolve(process.argv[2]);
const sinks = [];
const opened = [];
class FakeContext {
  constructor() { this.state = "suspended"; this.sinkId = ""; this.destination = {}; }
  async resume() { this.state = "running"; }
  async setSinkId(id) {
    if (id === "gone") throw new Error("NotFoundError");
    sinks.push(id); this.sinkId = id;
  }
  createMediaStreamSource(stream) { return { stream, connect() {}, disconnect() {} }; }
  createScriptProcessor() { return { connect() {}, disconnect() {} }; }
}
globalThis.AudioContext = FakeContext;
Object.defineProperty(globalThis, "navigator", {
  configurable: true,
  value: { mediaDevices: { getUserMedia: async (c) => { opened.push(JSON.stringify(c.audio)); return { getTracks: () => [{ stop() {} }] }; } } },
});

const { loadMicroPython } = await import(path.join(dir, "micropython.mjs"));
const mp = await loadMicroPython({ stdout: (l) => console.log(l), stderr: (l) => console.error(l) });
// Asking whether audio is on exports the host's controls, as a page's first
// output does.
mp.runPython("import _wasm_bridge\n_wasm_bridge.audio_state(False)");
const bridge = globalThis.Module.omnipythonBridge;
const fail = (what) => { console.error("FAIL", what); process.exitCode = 1; };

// A program that opens the microphone before the page has it is given it at
// the next gesture: until then the microphone is on its way, and reads nothing.
mp.runPython(`
assert _wasm_bridge.audio_state(True) == 1, "the microphone wasn't asked for"
assert _wasm_bridge.audio_readinto(bytearray(64), 16000, 1, 16, True, False) == 0, "an early read wasn't empty"
`);
if (opened.length) fail("the microphone opened before a gesture: " + opened.join(" "));

if (!bridge || !bridge.route) fail("the bridge has no route()");
else {
  await bridge.route("out", "hp");            // chosen before audio is on
  await bridge.enableAudio(false);
  if (sinks.join() !== "hp") fail("audio started on " + sinks.join());
  await bridge.route("out", "");              // back to the default while playing
  if (sinks.join() !== "hp,") fail("the default came back as " + sinks.join());
  await bridge.route("out", "gone");
  const error = bridge.routeError("out");
  if (!error || !error.includes("speaker")) fail("a refused speaker said " + error);
  if (bridge.routeError("out") !== null) fail("the error came back twice");
  await bridge.route("in", "mic");            // before the microphone is on: kept
  await bridge.enableAudio(true);
  await bridge.route("in", "");               // while recording: a new stream
  if (opened.join(" ") !== '{"deviceId":{"exact":"mic"}} true') fail("microphones opened " + opened.join(" "));
}
console.log(process.exitCode ? "audio_route: failed" : "audio_route: ok");
