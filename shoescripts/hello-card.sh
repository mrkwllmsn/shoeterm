#!/bin/sh
# Minimal vector-graphics demo: rounded rect + circle + text.
# Run inside the graphics-capable foot:  ./bld/debug/foot sh hello-card.sh
printf '\033P>g
size 40 6
bg #101028
pen #ff5050
rrectf 10 10 130 50 12
pen #50d0ff
circ 220 35 28
pen #ffffff
text 12 90 hello
\033\\'
