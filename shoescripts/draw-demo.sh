#!/bin/sh
# Demo of foot's vector graphics protocol.
# Run this INSIDE the freshly-built foot:  ./bld/debug/foot sh draw-demo.sh
#
# For each primitive it prints the exact commands it sends, then draws them -
# so you can see how the protocol is used. The whole batch is wrapped in:
#
#     ESC P > g  <commands>  ESC \
#
# Coordinates are pixels; the canvas size is given in terminal cells.

B=$(printf '\033[1m'); D=$(printf '\033[2m')
C=$(printf '\033[1;36m'); R=$(printf '\033[0m')

# demo <label> <commands>
#   prints the commands (boxed), then sends them as one graphics sequence.
demo() {
    label=$1; cmds=$2
    echo "$label" | shoestring
    printf '%s\n' "$cmds" | sed "s/^/    ${D}│${R} /"
    { printf '\033P>g\n'; printf '%s\n' "$cmds"; printf '\033\\'; }
    printf '\n'
}

echo 'foot vector graphics — primitives' "$B" "$R" | shoestring
printf '  %s(each block below is sent verbatim between ESC P > g ... ESC backslash)%s\n' "$D" "$R"

demo 'lines + thickness' \
'size 30 5
bg #15162b
pen #ffd000
line 12 18 224 18
thickness 4
pen #50d0ff
line 12 42 224 42
thickness 9
pen #ff80c0
line 12 70 224 70'

demo 'rect (outline) + rectf (filled)' \
'size 30 6
bg #15162b
thickness 2
pen #ff5050
rect 14 14 96 72
pen #50d0ff
rectf 134 14 96 72'

demo 'rrect / rrectf (rounded, corner radius)' \
'size 30 6
bg #15162b
thickness 3
pen #ffd000
rrect 14 14 96 72 16
pen #80ff80
rrectf 134 14 96 72 16'

demo 'circ / circf' \
'size 30 6
bg #15162b
thickness 3
pen #ff80ff
circ 72 50 34
pen #66f0d0
circf 184 50 34'

demo 'arc (angles in degrees, 0=east 90=south)' \
'size 30 6
bg #15162b
thickness 4
pen #ffd166
arc 120 78 54 180 360
pen #ff5d8f
arc 120 78 34 180 360'

demo 'tri / trif' \
'size 30 6
bg #15162b
thickness 3
pen #ffd000
tri 64 14 104 84 24 84
pen #4ecdc4
trif 206 14 246 84 166 84'

demo 'poly / polyf (any number of points)' \
'size 30 6
bg #15162b
pen #a78bfa
polyf 72 14 104 42 90 84 54 84 40 42
thickness 3
pen #ffd000
poly 206 14 240 50 206 86 172 50'

demo 'bezier (cubic curve)' \
'size 30 5
bg #15162b
thickness 3
pen #38e0ff
bezier 12 64 92 8 156 84 232 24'

demo 'text (uses your font, full UTF-8)' \
'size 34 4
bg #15162b
pen #ffffff
text 12 30 Vector text — sharp & UTF-8 ✓
pen #ffd166
text 12 56 colour set with: pen #ffd166'

demo 'textmode pixel — embedded 8x16 bitmap font (chunky, scalable)' \
'size 40 6
bg #15162b
pen #cfe8ff
text 12 26 smooth (default): fcft antialiased
textmode pixel
pen #7fe0ff
text 12 58 pixel: ASCII 0123 ?&@ at 1x
textmode pixel 2
pen #ffd166
text 12 104 PIXEL 2x  g j p q y'

demo 'alpha blending (#rrggbbaa) — translucent circles over white' \
'size 30 9
bg #ffffff
pen #ff0000a0
circf 95 60 44
pen #00ff00a0
circf 145 60 44
pen #0000ffa0
circf 120 102 44'

demo 'clip — confine drawing to a rectangle' \
'size 30 6
bg #15162b
pen #2a2c52
rectf 64 14 132 72
clip 64 14 132 72
pen #ffd000
circf 96 50 52
pen #ff5d8f
circf 168 50 52'

demo 'everything together' \
'size 26 12
bg #101028
pen #ff5050
rrectf 12 12 150 60 10
pen #50d0ff
circf 240 45 30
pen #ffd000
thickness 3
line 0 0 360 130
pen #80ff80
trif 60 90 150 150 30 150
pen #ff80ff
rrect 180 95 150 60 18
pen #ffa0d0
bezier 12 165 110 120 240 210 348 165
pen #ffffff
text 14 188 hello, foot graphics!'

