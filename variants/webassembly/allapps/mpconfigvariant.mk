# The all-apps browser build: the omnipython variant's runtime (its JS hooks,
# Asyncify and growing memory) with every app frozen in. Only the manifest
# differs, and the page's /models folder, which carries the model files the
# apps load (the wake word's), so the page fetches nothing for them, and
# Object detection's note of where the page keeps its model.
# scripts/build_wasm_allapps.py builds it, and names that folder in
# $OMNIPYTHON_MODELS.
include $(VARIANT_DIR)/../omnipython/mpconfigvariant.mk

ifeq ($(wildcard $(OMNIPYTHON_MODELS)/.),)
$(error allapps: OMNIPYTHON_MODELS must name the folder of model files for the page's /models (scripts/build_wasm_allapps.py sets it), not '$(OMNIPYTHON_MODELS)')
endif
LDFLAGS += --embed-file $(OMNIPYTHON_MODELS)@/models
# IndexedDB behind /data, so what apps save there (Weather's ZIP code, the
# settings) is still there at the next visit. index.html mounts it.
JSFLAGS += -lidbfs.js
