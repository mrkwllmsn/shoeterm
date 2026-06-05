#!/bin/sh
# Install the locally-built foot (as `shoe`) plus the shoe tools to /usr/local/bin.
# Run from anywhere: sh shoescripts/install_local_shoe.sh
set -e
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)   # this script's dir (shoescripts/)
root=$(CDPATH= cd -- "$dir/.." && pwd)             # repo root

cp "$root/bld/debug/foot" /usr/local/bin/shoe
for tool in shoelace shoestring shoetable shoetree shoebling shoom shuggy shoexp shoemac shoeshine shoestat; do
  cp "$dir/$tool" "/usr/local/bin/$tool"
done
# shoexp imports these helper modules; they must sit next to it on PATH.
for mod in shoexp_ui shoexp_minesweeper shoexp_notepad shoexp_paint shoexp_ie; do
  cp "$dir/$mod.py" "/usr/local/bin/$mod.py"
done
# shoemac imports these helper modules; they must sit next to it on PATH.
for mod in shoemac_ui shoemac_finder shoemac_calc shoemac_about shoemac_safari shoemac_terminal shoemac_imgview; do
  cp "$dir/$mod.py" "/usr/local/bin/$mod.py"
done
echo "Installed to /usr/local/bin/shoe"
