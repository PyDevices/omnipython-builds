# The all-apps browser build: the omnipython variant's runtime (its JS hooks,
# Asyncify and growing memory) with every app frozen in. Only the manifest
# differs; scripts/build_wasm_allapps.py builds it.
include $(VARIANT_DIR)/../omnipython/mpconfigvariant.mk
# IndexedDB behind /data, so what apps save there (Weather's ZIP code, the
# settings) is still there at the next visit. index.html mounts it.
JSFLAGS += -lidbfs.js
