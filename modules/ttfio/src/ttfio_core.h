// ttfio's engine: stb_truetype on one fixed scratch buffer.
//
// SPDX-License-Identifier: MIT

#ifndef TTFIO_CORE_H
#define TTFIO_CORE_H

#include <stddef.h>
#include <stdint.h>

// Big enough to hold an stbtt_fontinfo on any port (it is about 160 bytes on a
// 64-bit host); ttfio_core.c checks this at compile time.
#define TTFIO_INFO_WORDS 48

typedef struct {
    uint8_t *buf;
    size_t size;
    size_t used;
    size_t peak;
} ttfio_arena_t;

typedef struct {
    uint64_t info[TTFIO_INFO_WORDS / 2];
    ttfio_arena_t arena;
    const uint8_t *data;
    size_t len;
    int units_per_em;
} ttfio_font_t;

typedef struct {
    int w, h;       // bitmap size in pixels
    int x, y;       // its top-left, from the pen on the baseline (y < 0 is up)
    int advance;    // pen advance, in pixels, rounded
} ttfio_glyph_t;

// 0 if data holds a TrueType font, else -1. scratch is the buffer every render
// works in; the font keeps pointers to both, so they must outlive it.
int ttfio_core_open(ttfio_font_t *f, const uint8_t *data, size_t len, uint8_t *scratch, size_t scratch_size);

// Ascent, descent (negative) and line gap at an em of px pixels, rounded.
void ttfio_core_metrics(ttfio_font_t *f, float px, int *ascent, int *descent, int *line_gap);

// The font's glyph for codepoint cp, or 0 if it has none.
int ttfio_core_find(ttfio_font_t *f, uint32_t cp);

// Where glyph (from ttfio_core_find) lands at an em of px pixels.
void ttfio_core_glyph(ttfio_font_t *f, int glyph, float px, ttfio_glyph_t *g);

// Draws glyph as 8-bit coverage into out, w by h as ttfio_core_glyph gave,
// rows stride bytes apart. 0 on success, -1 if the scratch buffer ran out (out
// is then partly drawn).
int ttfio_core_render(ttfio_font_t *f, int glyph, float px, uint8_t *out, int w, int h, int stride);

#endif
