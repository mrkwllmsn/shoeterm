#!/bin/sh
# Install the locally-built foot (as `shoe`) plus the shoe tools to /usr/local/bin.
# Run from anywhere: sh shoescripts/install_local_shoe.sh
set -e
dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)   # this script's dir (shoescripts/)
root=$(CDPATH= cd -- "$dir/.." && pwd)             # repo root

cp "$root/bld/debug/foot" /usr/local/bin/shoe
for tool in shoelace shoestring shoetable shoebling shoom; do
  cp "$dir/$tool" "/usr/local/bin/$tool"
done
echo "Installed to /usr/local/bin/shoe"
