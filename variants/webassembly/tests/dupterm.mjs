// os.dupterm on the browser runtime: what the REPL prints reaches a dupterm
// stream, and what the stream is given reaches the REPL, from a timer
// callback as the REPL app's own keyboard tick does.
//
//   node variants/webassembly/tests/dupterm.mjs builds/webassembly/omnipython
import path from "node:path";

const dir = path.resolve(process.argv[2]);
const { loadMicroPython } = await import(path.join(dir, "micropython.mjs"));
const page = [];
const mp = await loadMicroPython({ stdout: (l) => page.push(l), stderr: (l) => page.push(l) });
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// A stream as vtterm's Console is one: write() keeps what the REPL prints,
// push() queues typed bytes and calls os.dupterm_notify.
await mp.runPythonAsync(`
import io, os, micropython, _wasm_bridge

class Term(io.IOBase):
    def __init__(self):
        self.out = bytearray()
        self.rx = bytearray()
    def write(self, buf):
        self.out.extend(buf)
        return len(buf)
    def readinto(self, buf):
        n = min(len(self.rx), len(buf))
        if not n:
            return None
        buf[:n] = self.rx[:n]
        self.rx[:n] = b""
        return n
    def ioctl(self, op, arg):
        return 1 if op == 3 and (arg & 1) and self.rx else 0
    def push(self, data):
        self.rx.extend(data)
        if b"\\x03" in data:
            micropython.schedule(os.dupterm_notify, None)
        else:
            os.dupterm_notify(None)

term = Term()
os.dupterm(term)
print("mirrored")
assert b"mirrored" in term.out, term.out

def typed(data):
    # From a timer, as the REPL app's tick pushes keys.
    _wasm_bridge.timer_start(40, 1, False, lambda: term.push(data))

def seen():
    return bytes(term.out).decode()
`);

async function type(data, ms = 200) {
    await mp.runPythonAsync(`typed(${JSON.stringify(data)}.encode())`);
    await wait(ms);
}

function check(label, ok) {
    if (!ok) {
        const out = seen();
        console.error(`FAIL ${label}\n--- the stream saw:\n${out}\n--- the page saw:\n${page.join("\n")}`);
        process.exit(1);
    }
    console.log(`ok   ${label}`);
}

function seen() {
    mp.runPython("_seen = seen()");
    return mp.globals.get("_seen");
}
const out = seen;

check("print() output reaches the stream", out().includes("mirrored"));

await type("1+2\r");
check("a line typed into the stream runs at the REPL, and its result comes back", /1\+2\r?\n3\r?\n>>> $/.test(out()));

await type("_wasm_bridge.sleep_ms(50); print('slept')\r", 400);
check("a line that sleeps (an Asyncify call) runs to the end", /slept\r?\n>>> $/.test(out()));

await type("for i in range(3):\r");
await type("print(i * 11)\r");
// Backspace over the auto-indent, then Enter ends the block, as on a board.
await type("\b\b\b\b\r", 300);
check("a compound statement over three lines, with auto-indent", /\r?\n0\r?\n11\r?\n22\r?\n>>> $/.test(out()));

await type("while True: _wasm_bridge.sleep_ms(10)\r");
await type("\r", 300);
await type("\x03", 400);
check("Ctrl-C from a timer interrupts the loop the stream started", out().includes("KeyboardInterrupt"));

await type("4*5\r");
check("the REPL takes lines again after the interrupt", /4\*5\r?\n20\r?\n>>> $/.test(out()));

const paste = "x = [" + "7, ".repeat(300) + "]\r";
await type(paste, 600);
await type("len(x)\r");
check(`a ${paste.length}-byte line, longer than the 512-byte buffer, arrives whole`, /len\(x\)\r?\n300\r?\n>>> $/.test(out()));

await mp.runPythonAsync(`
os.dupterm(None)
before = len(term.out)
print("not mirrored")
assert len(term.out) == before
`);
check("os.dupterm(None) stops the copying", true);
console.log("dupterm: ok");
process.exit(0);
