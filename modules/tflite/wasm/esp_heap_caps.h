// SPDX-FileCopyrightText: 2026 Brad Barnett
//
// SPDX-License-Identifier: MIT

// What py_tflite.cpp asks of ESP-IDF's esp_heap_caps.h, for the webassembly
// port: its buffers come from the C heap, which grows as it needs to. A
// browser has no PSRAM, so both capabilities are the one heap.
//
// The largest free block is what py_tflite.cpp sizes its throw-away probe
// arena by, which it then caps at 16 MB; with a heap that grows, the block it
// may have is that cap. The probe is freed before the real, exactly sized
// arena is made.
#ifndef TFLITE_WASM_ESP_HEAP_CAPS_H
#define TFLITE_WASM_ESP_HEAP_CAPS_H

#include <stddef.h>
#include <stdlib.h>

#define MALLOC_CAP_8BIT (1 << 2)
#define MALLOC_CAP_SPIRAM (1 << 10)
#define MALLOC_CAP_DEFAULT (1 << 12)

static inline void *heap_caps_aligned_alloc(size_t alignment, size_t size, unsigned int caps) {
    (void)caps;
    void *p = NULL;
    return posix_memalign(&p, alignment < sizeof(void *) ? sizeof(void *) : alignment, size) == 0 ? p : NULL;
}

static inline void heap_caps_free(void *p) {
    free(p);
}

static inline size_t heap_caps_get_largest_free_block(unsigned int caps) {
    (void)caps;
    return 16 * 1024 * 1024 + 4096;
}

#endif
