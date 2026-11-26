WASMBRIDGE_PORT := $(findstring /ports/webassembly,$(abspath $(CURDIR)))

ifneq ($(WASMBRIDGE_PORT),)
ifneq ($(filter omnipython allapps,$(VARIANT)),)
SRC_USERMOD_C += $(USERMOD_DIR)/mod_wasm_bridge.c
LDFLAGS_USERMOD += --js-library $(USERMOD_DIR)/library_wasm_bridge.js
endif
endif
