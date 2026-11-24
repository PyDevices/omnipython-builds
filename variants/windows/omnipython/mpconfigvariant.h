// The OmniPython windows build: upstream's dev variant, included from the port
// tree, plus an 8 MB GC heap by default (upstream's is 2 MB on 64-bit);
// -X heapsize= still overrides it. Needs patch 0012.
#include "variants/dev/mpconfigvariant.h"
// The dev variant turns on sys.settrace, which allocates a frame and a code
// object (128 bytes) on the heap for every Python function call, traced or
// not. Unix leaves it off, and code that must not allocate in a loop (audio
// callbacks, MIDI input) relies on that.
#undef MICROPY_PY_SYS_SETTRACE
#define MICROPY_PY_SYS_SETTRACE (0)
#define MICROPY_UNIX_DEFAULT_HEAP_SIZE (8 * 1024 * 1024)
// Run a built-in module's __init__ on import, as unix does. The windows port
// sits at the core ROM level, where this is off, so `import jpegio` after
// lv.init() never registered jpegio's LVGL decoder (displayif#41, from when jpegio lived there).
#define MICROPY_MODULE_BUILTIN_INIT (1)
