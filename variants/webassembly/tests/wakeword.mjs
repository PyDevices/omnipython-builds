// The all-apps page runs Wake word's model: tflite imports, the page's
// /models folder holds "Hey Jarvis", and medialink's MicroWakeWord, on
// audiodsp's audiofeatures, stays quiet through silence and fires on a
// spoken "Hey Jarvis" (hey_jarvis.wav beside this file, 16 kHz mono 16-bit,
// made with Pico TTS: pico2wave -l en-US "Hey Jarvis.", padded with silence).
//
//   node variants/webassembly/tests/wakeword.mjs builds/webassembly/allapps
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const dir = path.resolve(process.argv[2]);
const here = path.dirname(fileURLToPath(import.meta.url));
const { loadMicroPython } = await import(path.join(dir, "micropython.mjs"));
const mp = await loadMicroPython({ stdout: (l) => console.log(l), stderr: (l) => console.error(l) });

// The clip's samples, after its 44-byte header, where the Python can read them.
const wav = fs.readFileSync(path.join(here, "hey_jarvis.wav"));
if (wav.toString("ascii", 0, 4) !== "RIFF" || wav.readUInt32LE(24) !== 16000 || wav.readUInt16LE(22) !== 1) {
  throw new Error("hey_jarvis.wav is not 16 kHz mono");
}
mp.FS.writeFile("/hey_jarvis.pcm", wav.subarray(44));

await mp.runPythonAsync(`
import os
import tflite
from medialink.wakeword import MicroWakeWord

print("tflite", tflite.__revision__)
print("/models:", sorted(os.listdir("/models")))
ww = MicroWakeWord("/models/hey_jarvis.json")
m = ww.model
print("model: %d bytes, %d bytes of arena, input %r %r, output %r" % (m.len, m.ram, m.input_shape, m.input_dtype, m.output_shape))
assert ww.name == "Hey Jarvis", ww.name

def run(pcm):
    fired, best = 0, 0.0
    for at in range(0, len(pcm), 320):  # 10 ms at a time, as the app reads
        if ww.feed(pcm[at:at + 320], 16000, 1):
            fired += 1
        best = max(best, ww.probability)
    return fired, best

quiet = run(bytes(16000 * 2 * 3))
print("3 s of silence: fired %d times, best score %.2f" % quiet)
assert quiet[0] == 0, "fired on silence"
assert quiet[1] < 0.2, "a high score on silence"

with open("/hey_jarvis.pcm", "rb") as f:
    clip = f.read()
said = run(clip)
print('"Hey Jarvis": fired %d times, best score %.2f' % said)
assert said[0] == 1, "fired %d times on one Hey Jarvis" % said[0]
print("wakeword: ok")
`);
