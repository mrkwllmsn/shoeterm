#!/bin/sh
# Comma-only one-liner printf examples from the docs/index.html JSON-LD FAQ.
# Run inside the built foot to verify each renders. Each draws at the cursor.

# Card
printf '\033P>g size 40 6, bg #101028, pen #ff5050, rrectf 10 10 130 50 12, pen #50d0ff, circ 220 35 28, pen #ffffff, text 12 90 hello\033\\'
echo

# Simple shapes
printf '\033P>g size 10 4, pen #50d0ff, thickness 3, line 10 10 180 60, circ 120 30 20, rectf 200 10 60 40\033\\'
echo

# Filled triangle
printf '\033P>g size 8 4, pen #4fd99a, trif 10 70 70 10 130 70\033\\'
echo
