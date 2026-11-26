# The all-apps browser build: the omnipython variant's runtime (its JS hooks,
# Asyncify and growing memory) with every app frozen in. Only the manifest
# differs; scripts/build_wasm_allapps.py builds it.
include $(VARIANT_DIR)/../omnipython/mpconfigvariant.mk
