// ttfio's engine: stb_truetype on one fixed scratch buffer.
//
// stb asks for memory several times a glyph (the outline, the flattened
// points, the edges, the active-edge chunks) and frees it all by the end. Here
// every request is a bump in the font's scratch buffer, reset at the start of
// each render, so a render allocates nothing from the heap. If the buffer runs
// out, the allocator jumps back to ttfio_core_render, which reports it; stb
// never sees a NULL.
//
// SPDX-License-Identifier: MIT

#include <setjmp.h>
#include <string.h>

#include "ttfio_core.h"

static void *ttfio_arena_alloc(size_t n, void *userdata);

#define STBTT_malloc(x, u) ttfio_arena_alloc((x), (u))
#define STBTT_free(x, u) ((void)(x), (void)(u))
#define STBTT_assert(x) ((void)0)
#define STBTT_STATIC
#define STB_TRUETYPE_IMPLEMENTATION

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#pragma GCC diagnostic ignored "-Wdouble-promotion"
#pragma GCC diagnostic ignored "-Wfloat-conversion"
// CircuitPython's espressif port builds with -Werror=float-equal.
#pragma GCC diagnostic ignored "-Wfloat-equal"
#pragma GCC diagnostic ignored "-Wsign-compare"
#pragma GCC diagnostic ignored "-Wunused-parameter"
#pragma GCC diagnostic ignored "-Wimplicit-fallthrough"
#include "stb_truetype.h"
#pragma GCC diagnostic pop

_Static_assert(sizeof(stbtt_fontinfo) <= sizeof(((ttfio_font_t *)0)->info), "TTFIO_INFO_WORDS too small");

#define INFO(f) ((stbtt_fontinfo *)(f)->info)

// How far a flattened curve may stray from the true one, in pixels. stb's own
// 0.35 px trims the inside of small arcs, up to 4 % of a 20 px icon's ink;
// 0.1 px keeps every icon within 2 % of FreeType's unhinted drawing, for about
// 1 KB more scratch at 48 px.
#ifndef TTFIO_FLATNESS
#define TTFIO_FLATNESS 0.1f
#endif

static void *ttfio_arena_alloc(size_t n, void *userdata) {
    ttfio_arena_t *a = userdata;
    size_t at = (a->used + 7) & ~(size_t)7;
    if (at > a->size || n > a->size - at) {
        longjmp(*(jmp_buf *)a->jump, 1);
    }
    a->used = at + n;
    if (a->used > a->peak) {
        a->peak = a->used;
    }
    return a->buf + at;
}

int ttfio_core_open(ttfio_font_t *f, const uint8_t *data, size_t len, uint8_t *scratch, size_t scratch_size) {
    memset(f, 0, sizeof(*f));
    f->data = data;
    f->len = len;
    f->arena.buf = scratch;
    f->arena.size = scratch_size;
    if (len < 12) {
        return -1;
    }
    int at = stbtt_GetFontOffsetForIndex(data, 0);
    if (at < 0 || (size_t)at >= len) {
        return -1;
    }
    stbtt_fontinfo *info = INFO(f);
    if (!stbtt_InitFont(info, data, at) || !info->head) {
        return -1;
    }
    info->userdata = &f->arena;
    f->units_per_em = ttUSHORT((stbtt_uint8 *)data + info->head + 18);
    return f->units_per_em ? 0 : -1;
}

static float ttfio_scale(ttfio_font_t *f, float px) {
    return px / (float)f->units_per_em;
}

static int ttfio_round(float v) {
    return v < 0 ? -(int)(0.5f - v) : (int)(v + 0.5f);
}

void ttfio_core_metrics(ttfio_font_t *f, float px, int *ascent, int *descent, int *line_gap) {
    int a, d, g;
    stbtt_GetFontVMetrics(INFO(f), &a, &d, &g);
    float s = ttfio_scale(f, px);
    *ascent = ttfio_round(a * s);
    *descent = ttfio_round(d * s);
    *line_gap = ttfio_round(g * s);
}

int ttfio_core_find(ttfio_font_t *f, uint32_t cp) {
    return stbtt_FindGlyphIndex(INFO(f), (int)cp);
}

void ttfio_core_glyph(ttfio_font_t *f, int glyph, float px, ttfio_glyph_t *g) {
    float s = ttfio_scale(f, px);
    int x0, y0, x1, y1, adv, lsb;
    stbtt_GetGlyphBitmapBox(INFO(f), glyph, s, s, &x0, &y0, &x1, &y1);
    stbtt_GetGlyphHMetrics(INFO(f), glyph, &adv, &lsb);
    g->w = x1 - x0;
    g->h = y1 - y0;
    g->x = x0;
    g->y = y0;
    g->advance = ttfio_round(adv * s);
}

int ttfio_core_render(ttfio_font_t *f, int glyph, float px, uint8_t *out, int w, int h, int stride) {
    jmp_buf jump;
    f->arena.used = 0;
    f->arena.jump = &jump;
    if (setjmp(jump)) {
        f->arena.jump = NULL;
        return -1;
    }
    // stbtt_MakeGlyphBitmap, with TTFIO_FLATNESS for its fixed 0.35 px.
    float s = ttfio_scale(f, px);
    stbtt_vertex *v;
    int n = stbtt_GetGlyphShape(INFO(f), glyph, &v);
    int x0, y0;
    stbtt_GetGlyphBitmapBox(INFO(f), glyph, s, s, &x0, &y0, NULL, NULL);
    stbtt__bitmap bm = { w, h, stride, out };
    stbtt_Rasterize(&bm, TTFIO_FLATNESS, v, n, s, s, 0, 0, x0, y0, 1, &f->arena);
    f->arena.jump = NULL;
    return 0;
}
