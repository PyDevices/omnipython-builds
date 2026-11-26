# The all-apps browser build: the omnipython variant's runtime (its JS hooks,
# Asyncify and growing memory) with every app frozen in. Only the manifest
# differs, and the page's /models folder, where the apps look for their model
# files: Object detection's there is a note of where its model is fetched
# from. scripts/build_wasm_allapps.py builds it, and names that folder in
# $OMNIPYTHON_MODELS.
include $(VARIANT_DIR)/../omnipython/mpconfigvariant.mk
# IndexedDB behind /data, so what apps save there (Weather's ZIP code, the
# settings) is still there at the next visit. index.html mounts it.
JSFLAGS += -lidbfs.js

ifeq ($(wildcard $(OMNIPYTHON_MODELS)/.),)
$(error allapps: OMNIPYTHON_MODELS must name the folder of model files for the page's /models (scripts/build_wasm_allapps.py sets it), not '$(OMNIPYTHON_MODELS)')
endif
LDFLAGS += --embed-file $(OMNIPYTHON_MODELS)@/models
