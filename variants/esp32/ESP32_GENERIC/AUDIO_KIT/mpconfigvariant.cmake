# Upstream's PSRAM variant, unchanged. This board's own settings are the
# sdkconfig beside this file, which build_mp.py appends last.
include(${MICROPY_BOARD_DIR}/mpconfigvariant_SPIRAM.cmake)

# A ROMFS partition for your own compiled packages: mounted at /rom, with
# /rom and /rom/lib on sys.path, and imported in place from flash.
list(APPEND MICROPY_DEF_BOARD MICROPY_VFS_ROM=1)

# LVGL without its 24, 32 and 40 px Montserrat fonts, 145 KB of flash: with
# Bluetooth Receiver's libraries frozen, the image doesn't fit the kit's 4 MB
# otherwise. Apps that ask for those sizes fall back to the next one built in.
list(APPEND MICROPY_DEF_BOARD
    LV_FONT_MONTSERRAT_24=0
    LV_FONT_MONTSERRAT_32=0
    LV_FONT_MONTSERRAT_40=0
)
