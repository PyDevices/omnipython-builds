#!/bin/sh
# Put esp-tflite-micro at its DEPENDENCIES.lock commit in
# modules/.esp-tflite-micro/src, once, and print that directory.
#
# This is TensorFlow Lite Micro as Espressif packages it, the version the
# esp32 builds get from the component registry. Those builds never run this:
# the component manager fetches it for them. The webassembly port's make
# build has no component manager, so modules/tflite/micropython.mk runs this
# script and compiles the same sources, with the portable kernels in place of
# esp-nn's. ESP_TFLITE_MICRO_DIR names a clone at the pinned commit to link
# instead. The directory starts with a dot, so build_mp.py never offers it as
# a module and "all" never includes it.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
src="$here/src"
pins="$here/../../scripts/pins.py"
url=$(python3 "$pins" esp-tflite-micro url)
pin=$(python3 "$pins" esp-tflite-micro commit)
at_pin() { [ "$(git -C "$1" rev-parse HEAD 2>/dev/null)" = "$pin" ]; }

if [ -e "$src" ] || [ -L "$src" ]; then
    at_pin "$src" || { echo "esp-tflite-micro: $src is not at $pin; delete it to refetch" >&2; exit 1; }
    echo "$src"; exit 0
fi
cand="${ESP_TFLITE_MICRO_DIR:-}"
if [ -n "$cand" ] && [ -d "$cand" ] && at_pin "$cand"; then
    ln -s "$(cd "$cand" && pwd)" "$src"
    echo "$src"; exit 0
fi
git init -q "$src"
git -C "$src" remote add origin "$url"
git -C "$src" fetch -q --depth 1 origin "$pin"
git -C "$src" checkout -q FETCH_HEAD
echo "$src"
