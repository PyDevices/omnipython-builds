# Upstream's octal-PSRAM variant, with the audio graph's kernels in IRAM. This
# board's own settings are the sdkconfig beside this file, which build_mp.py
# appends last.
include(${MICROPY_BOARD_DIR}/mpconfigvariant_SPIRAM_OCT.cmake)

# The audio graph's per-block kernels in IRAM. The RGB panel's scanout keeps
# the flash and PSRAM bus busy, and kernels fetched from flash stall on it:
# rhythm909 at 48 kHz stereo rendered 179 blocks a second from flash and 232
# from IRAM, of the 375 it needs. They take 15.6 KB of internal RAM.
set(AUDIODSP_GRAPH_IRAM 1)
