#!/bin/sh
# Build foot natively on a Raspberry Pi (Pi OS / Debian, aarch64, Wayland).
# Run on the Pi from the repo root: ./build-pi.sh
#
# Uses a separate build dir (bld/release) so it never touches bld/debug.
# fcft (>=3.3.1) and wayland-protocols (>=1.41) are newer than some Pi OS
# releases ship; if the system packages are too old meson falls back to the
# git subprojects in subprojects/*.wrap (needs network on the first build).
# Set SKIP_APT=1 to skip the package install step.
set -e

if [ -z "$SKIP_APT" ]; then
  sudo apt-get update
  sudo apt-get install -y \
    build-essential meson ninja-build pkg-config git cmake scdoc ncurses-bin \
    libwayland-dev wayland-protocols libxkbcommon-dev libpixman-1-dev \
    libfontconfig-dev libfreetype-dev libharfbuzz-dev libutf8proc-dev \
    libfcft-dev python3 fonts-dejavu-core
fi

meson setup bld/release --buildtype=release \
  || meson setup --reconfigure bld/release --buildtype=release
ninja -C bld/release

echo "Done. Run: ./bld/release/foot"
echo "Install:  sudo SHOE_BUILD=bld/release sh shoescripts/install_local_shoe.sh"
