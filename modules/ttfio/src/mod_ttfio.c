// ttfio for MicroPython: TrueType glyphs drawn straight from a font in flash.
//
//   font = ttfio.Font(data)              # data: bytes, frozen or not
//   w, h, x, y, advance = font.glyph("A", 20)
//   mask = font.render("A", 20)          # w*h bytes of coverage, 0..255
//
// The engine is ttfio_core.c over stb_truetype. The font is read where it is,
// never copied, and each render works inside the Font's own scratch buffer,
// so drawing a glyph allocates nothing beyond the mask (and nothing at all
// when you pass a buffer to draw into). On CPython, omnipython-desktop's
// ttfio.py gives the same API over Pillow.
//
// SPDX-License-Identifier: MIT

#include <string.h>

#include "py/obj.h"
#include "py/objstr.h"
#include "py/runtime.h"

#include "ttfio_core.h"

typedef struct {
    mp_obj_base_t base;
    mp_obj_t data;      // keeps the font's bytes alive
    uint8_t *scratch;
    ttfio_font_t font;
} ttfio_font_obj_t;

static mp_obj_t ttfio_font_make_new(const mp_obj_type_t *type, size_t n_args, size_t n_kw, const mp_obj_t *all_args) {
    enum { ARG_data, ARG_scratch };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_data, MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_scratch, MP_ARG_INT, { .u_int = 8192 } },
    };
    mp_arg_val_t a[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all_kw_array(n_args, n_kw, all_args, MP_ARRAY_SIZE(allowed), allowed, a);
    mp_buffer_info_t bi;
    mp_get_buffer_raise(a[ARG_data].u_obj, &bi, MP_BUFFER_READ);
    mp_int_t size = a[ARG_scratch].u_int;
    if (size < 256) {
        mp_raise_ValueError(MP_ERROR_TEXT("scratch must be at least 256 bytes"));
    }
    ttfio_font_obj_t *self = mp_obj_malloc(ttfio_font_obj_t, type);
    self->data = a[ARG_data].u_obj;
    self->scratch = m_new(uint8_t, size);
    if (ttfio_core_open(&self->font, bi.buf, bi.len, self->scratch, (size_t)size) != 0) {
        mp_raise_ValueError(MP_ERROR_TEXT("not a TrueType font"));
    }
    return MP_OBJ_FROM_PTR(self);
}

// A one-character str, or an int codepoint.
static uint32_t ttfio_codepoint(mp_obj_t ch) {
    if (mp_obj_is_int(ch)) {
        mp_int_t cp = mp_obj_get_int(ch);
        if (cp < 0 || cp > 0x10FFFF) {
            mp_raise_ValueError(MP_ERROR_TEXT("codepoint out of range"));
        }
        return (uint32_t)cp;
    }
    if (mp_obj_is_str(ch)) {
        size_t len;
        const char *s = mp_obj_str_get_data(ch, &len);
        if (len > 0) {
            const byte *p = (const byte *)s;
            unichar c = utf8_get_char(p);
            if (utf8_next_char(p) == p + len) {
                return (uint32_t)c;
            }
        }
    }
    mp_raise_TypeError(MP_ERROR_TEXT("expected one character or a codepoint"));
}

static float ttfio_px(mp_obj_t px) {
    mp_float_t v = mp_obj_get_float(px);
    if (!(v > 0 && v <= 1024)) {
        mp_raise_ValueError(MP_ERROR_TEXT("px must be above 0 and at most 1024"));
    }
    return (float)v;
}

// The glyph for ch, or 0 if the font has none.
static int ttfio_find(ttfio_font_obj_t *self, mp_obj_t ch) {
    return ttfio_core_find(&self->font, ttfio_codepoint(ch));
}

static mp_obj_t ttfio_font_has(mp_obj_t self_in, mp_obj_t ch) {
    return mp_obj_new_bool(ttfio_find(MP_OBJ_TO_PTR(self_in), ch) != 0);
}
static MP_DEFINE_CONST_FUN_OBJ_2(ttfio_font_has_obj, ttfio_font_has);

static mp_obj_t ttfio_font_metrics(mp_obj_t self_in, mp_obj_t px) {
    ttfio_font_obj_t *self = MP_OBJ_TO_PTR(self_in);
    int a, d, g;
    ttfio_core_metrics(&self->font, ttfio_px(px), &a, &d, &g);
    mp_obj_t t[3] = { MP_OBJ_NEW_SMALL_INT(a), MP_OBJ_NEW_SMALL_INT(d), MP_OBJ_NEW_SMALL_INT(g) };
    return mp_obj_new_tuple(3, t);
}
static MP_DEFINE_CONST_FUN_OBJ_2(ttfio_font_metrics_obj, ttfio_font_metrics);

static mp_obj_t ttfio_font_glyph(mp_obj_t self_in, mp_obj_t ch, mp_obj_t px) {
    ttfio_font_obj_t *self = MP_OBJ_TO_PTR(self_in);
    int glyph = ttfio_find(self, ch);
    if (!glyph) {
        return mp_const_none;
    }
    ttfio_glyph_t g;
    ttfio_core_glyph(&self->font, glyph, ttfio_px(px), &g);
    mp_obj_t t[5] = {
        MP_OBJ_NEW_SMALL_INT(g.w), MP_OBJ_NEW_SMALL_INT(g.h),
        MP_OBJ_NEW_SMALL_INT(g.x), MP_OBJ_NEW_SMALL_INT(g.y),
        MP_OBJ_NEW_SMALL_INT(g.advance),
    };
    return mp_obj_new_tuple(5, t);
}
static MP_DEFINE_CONST_FUN_OBJ_3(ttfio_font_glyph_obj, ttfio_font_glyph);

static mp_obj_t ttfio_font_render(size_t n_args, const mp_obj_t *pos_args, mp_map_t *kw_args) {
    enum { ARG_self, ARG_ch, ARG_px, ARG_buf, ARG_stride };
    static const mp_arg_t allowed[] = {
        { MP_QSTR_, MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_ch, MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_px, MP_ARG_REQUIRED | MP_ARG_OBJ, { .u_obj = MP_OBJ_NULL } },
        { MP_QSTR_buf, MP_ARG_OBJ, { .u_obj = mp_const_none } },
        { MP_QSTR_stride, MP_ARG_INT, { .u_int = 0 } },
    };
    mp_arg_val_t a[MP_ARRAY_SIZE(allowed)];
    mp_arg_parse_all(n_args, pos_args, kw_args, MP_ARRAY_SIZE(allowed), allowed, a);
    ttfio_font_obj_t *self = MP_OBJ_TO_PTR(a[ARG_self].u_obj);
    int glyph = ttfio_find(self, a[ARG_ch].u_obj);
    if (!glyph) {
        mp_raise_msg(&mp_type_KeyError, MP_ERROR_TEXT("the font has no glyph for that character"));
    }
    float px = ttfio_px(a[ARG_px].u_obj);
    ttfio_glyph_t g;
    ttfio_core_glyph(&self->font, glyph, px, &g);
    mp_int_t stride = a[ARG_stride].u_int ? a[ARG_stride].u_int : g.w;
    if (stride < g.w) {
        mp_raise_ValueError(MP_ERROR_TEXT("stride is narrower than the glyph"));
    }
    size_t need = g.h ? (size_t)stride * (size_t)(g.h - 1) + (size_t)g.w : 0;
    mp_obj_t out = a[ARG_buf].u_obj;
    mp_buffer_info_t bi;
    if (out == mp_const_none) {
        // Zeroed, so a stride wider than the glyph leaves blank margins.
        out = mp_obj_new_bytearray_by_ref(need, m_new0(uint8_t, need));
        mp_get_buffer_raise(out, &bi, MP_BUFFER_WRITE);
    } else {
        mp_get_buffer_raise(out, &bi, MP_BUFFER_WRITE);
        if (bi.len < need) {
            mp_raise_ValueError(MP_ERROR_TEXT("buf is too small for the glyph"));
        }
    }
    if (g.w && g.h && ttfio_core_render(&self->font, glyph, px, bi.buf, g.w, g.h, (int)stride) != 0) {
        mp_raise_msg(&mp_type_MemoryError, MP_ERROR_TEXT("glyph needs more scratch than the Font has; make it with a larger scratch="));
    }
    return out;
}
static MP_DEFINE_CONST_FUN_OBJ_KW(ttfio_font_render_obj, 3, ttfio_font_render);

static void ttfio_font_attr(mp_obj_t self_in, qstr attr, mp_obj_t *dest) {
    ttfio_font_obj_t *self = MP_OBJ_TO_PTR(self_in);
    if (dest[0] != MP_OBJ_NULL) {
        dest[1] = MP_OBJ_SENTINEL;  // continue lookup in locals_dict
        return;
    }
    if (attr == MP_QSTR_units_per_em) {
        dest[0] = MP_OBJ_NEW_SMALL_INT(self->font.units_per_em);
    } else if (attr == MP_QSTR_scratch_peak) {
        dest[0] = mp_obj_new_int_from_uint(self->font.arena.peak);
    } else {
        dest[1] = MP_OBJ_SENTINEL;
    }
}

static const mp_rom_map_elem_t ttfio_font_locals_table[] = {
    { MP_ROM_QSTR(MP_QSTR_has), MP_ROM_PTR(&ttfio_font_has_obj) },
    { MP_ROM_QSTR(MP_QSTR_metrics), MP_ROM_PTR(&ttfio_font_metrics_obj) },
    { MP_ROM_QSTR(MP_QSTR_glyph), MP_ROM_PTR(&ttfio_font_glyph_obj) },
    { MP_ROM_QSTR(MP_QSTR_render), MP_ROM_PTR(&ttfio_font_render_obj) },
};
static MP_DEFINE_CONST_DICT(ttfio_font_locals, ttfio_font_locals_table);

MP_DEFINE_CONST_OBJ_TYPE(
    ttfio_font_type,
    MP_QSTR_Font,
    MP_TYPE_FLAG_NONE,
    make_new, ttfio_font_make_new,
    attr, ttfio_font_attr,
    locals_dict, &ttfio_font_locals
    );

// ttfio.__revision__: which ttfio this firmware was built from. The build
// passes TTFIO_REVISION (git describe) as a compile definition; a build with no
// git says "unknown" rather than guessing.
#ifndef TTFIO_REVISION
#define TTFIO_REVISION "unknown"
#endif
static const MP_DEFINE_STR_OBJ(ttfio_revision_obj, TTFIO_REVISION);

static const mp_rom_map_elem_t ttfio_module_globals_table[] = {
    { MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_ttfio) },
    { MP_ROM_QSTR(MP_QSTR___revision__), MP_ROM_PTR(&ttfio_revision_obj) },
    { MP_ROM_QSTR(MP_QSTR_Font), MP_ROM_PTR(&ttfio_font_type) },
};
static MP_DEFINE_CONST_DICT(ttfio_module_globals, ttfio_module_globals_table);

const mp_obj_module_t ttfio_user_cmodule = {
    .base = { &mp_type_module },
    .globals = (mp_obj_dict_t *)&ttfio_module_globals,
};

MP_REGISTER_MODULE(MP_QSTR_ttfio, ttfio_user_cmodule);
