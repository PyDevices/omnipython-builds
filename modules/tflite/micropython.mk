# tflite for the webassembly port: esp-vision's py_tflite.cpp by way of
# src/tflite_streaming.cpp, as the esp32 builds compile it
# (micropython.cmake), on TensorFlow Lite Micro from the esp-tflite-micro
# release those builds use, with its portable kernels in place of esp-nn's.
# Every other make port skips it: on a board tflite is the esp32 port's.
TFLITE_WASM_PORT := $(findstring /ports/webassembly,$(abspath $(CURDIR)))

ifneq ($(TFLITE_WASM_PORT),)
TFLITE_DIR := $(USERMOD_DIR)
TFLITE_MODULES := $(realpath $(TFLITE_DIR)/..)
ESP_VISION_SRC := $(shell sh $(TFLITE_MODULES)/.esp-vision/fetch.sh)
TFLM := $(shell sh $(TFLITE_MODULES)/.esp-tflite-micro/fetch.sh)
ifeq ($(ESP_VISION_SRC),)
$(error tflite: fetching esp-vision failed (modules/.esp-vision/fetch.sh))
endif
ifeq ($(TFLM),)
$(error tflite: fetching esp-tflite-micro failed (modules/.esp-tflite-micro/fetch.sh))
endif
TFLITE_REVISION := $(shell git -C $(TFLITE_DIR) describe --always --dirty --abbrev=7 2>/dev/null || echo unknown)

# The C++ compiler; the port names only emcc.
CXX = em++

SRC_USERMOD_CXX += $(TFLITE_DIR)/src/tflite_streaming.cpp

# The sources esp-tflite-micro's CMakeLists.txt compiles, with micro_time.cc
# in place of its ESP timer one and the portable kernels in place of esp-nn's.
# Left out: the signal library's operators and the micro frontend, which
# py_tflite.cpp registers none of.
TFLM_LITE := $(TFLM)/tensorflow/lite
TFLM_MICRO := $(TFLM_LITE)/micro
TFLM_SRC := $(addprefix $(TFLM_MICRO)/,\
	debug_log.cc flatbuffer_utils.cc memory_helpers.cc micro_allocation_info.cc \
	micro_allocator.cc micro_context.cc micro_interpreter_context.cc \
	micro_interpreter_graph.cc micro_interpreter.cc micro_log.cc micro_op_resolver.cc \
	micro_profiler.cc micro_resource_variable.cc micro_time.cc micro_utils.cc \
	recording_micro_allocator.cc system_setup.cc \
	memory_planner/greedy_memory_planner.cc memory_planner/linear_memory_planner.cc \
	arena_allocator/non_persistent_arena_buffer_allocator.cc \
	arena_allocator/persistent_arena_buffer_allocator.cc \
	arena_allocator/recording_single_arena_buffer_allocator.cc \
	arena_allocator/single_arena_buffer_allocator.cc)
TFLM_SRC += $(wildcard $(TFLM_MICRO)/kernels/*.cc $(TFLM_MICRO)/tflite_bridge/*.cc)
TFLM_SRC += $(addprefix $(TFLM_LITE)/,\
	kernels/kernel_util.cc core/c/common.cc core/api/flatbuffer_conversions.cc \
	core/api/tensor_utils.cc kernels/internal/common.cc kernels/internal/quantization_util.cc \
	kernels/internal/portable_tensor_utils.cc kernels/internal/tensor_utils.cc \
	kernels/internal/tensor_ctypes.cc kernels/internal/reference/portable_tensor_utils.cc \
	kernels/internal/reference/comparisons.cc)
TFLM_SRC += $(addprefix $(TFLM)/tensorflow/compiler/mlir/lite/,\
	core/api/error_reporter.cc schema/schema_utils.cc)
# MicroPython's rules compile .cpp, and TensorFlow's files are .cc: these are
# compiled by the rule below, into build/tflm/, with the flags C++ gets.
TFLM_OBJ := $(patsubst $(TFLM)/%.cc,$(BUILD)/tflm/%.o,$(TFLM_SRC))
PY_O += $(TFLM_OBJ)
$(BUILD)/tflm/%.o: $(TFLM)/%.cc
	$(ECHO) "CXX $<"
	$(Q)$(CXX) $(CXXFLAGS) -c -MD -MF $(@:.o=.d) -o $@ $<
-include $(TFLM_OBJ:.o=.d)

# py_tflite.cpp includes "ulab/code/ndarray.h", so the folder holding ulab;
# esp_heap_caps.h comes from wasm/.
CXXFLAGS_USERMOD += -I$(TFLITE_DIR)/wasm -I$(ESP_VISION_SRC)/modules -I$(TFLITE_MODULES) \
	-I$(TFLM) -I$(TFLM)/third_party/gemmlowp -I$(TFLM)/third_party/flatbuffers/include \
	-I$(TFLM)/third_party/ruy -I$(TFLM)/third_party/kissfft \
	-DTF_LITE_STATIC_MEMORY -DTF_LITE_DISABLE_X86_NEON -DTFLITE_REVISION=\"$(TFLITE_REVISION)\"
# After the port's CFLAGS, which py/mkrules.mk copies into CXXFLAGS ahead of
# these: its -Werror and C warnings are for our C, not TensorFlow's C++, and
# emscripten's C++ already defines the _GNU_SOURCE mpconfigport.h defines.
CXXFLAGS_MOD += -std=gnu++17 -fno-rtti -fno-exceptions -fno-threadsafe-statics \
	-Wno-error -Wno-macro-redefined -Wno-double-promotion -Wno-float-conversion \
	-Wno-unused-parameter -Wno-sign-compare -Wno-missing-field-initializers
endif
