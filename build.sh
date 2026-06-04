#!/bin/sh
# Build foot (debug). Run: ./build.sh
set -e

meson setup bld/debug
ninja -C bld/debug

echo "Done. Run: ./bld/debug/foot"
