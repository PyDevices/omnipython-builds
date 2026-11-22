# ttfio: TrueType glyphs from a font in flash (stb_truetype). Platform-neutral
# C on every port.
TTFIO_DIR := $(USERMOD_DIR)/src

CFLAGS_USERMOD += -I$(TTFIO_DIR) -I$(USERMOD_DIR)/third_party/stb_truetype

# Which ttfio this firmware was built from: ttfio.__revision__.
TTFIO_REVISION := $(shell git -C $(USERMOD_DIR) describe --always --dirty --abbrev=7 2>/dev/null || echo unknown)
CFLAGS_USERMOD += -DTTFIO_REVISION='"$(TTFIO_REVISION)"'

SRC_USERMOD_C += $(TTFIO_DIR)/mod_ttfio.c

# The engine has no qstrs, so it stays out of the QSTR scan.
SRC_USERMOD_LIB_C += $(TTFIO_DIR)/ttfio_core.c
