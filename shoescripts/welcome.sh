#!/bin/sh
# A beautiful welcome header for foot, drawn with the vector graphics protocol.
#
#   Try it:   ./bld/debug/foot sh welcome.sh
#   Use it:   add to ~/.bashrc / ~/.zshrc:   sh /path/to/welcome.sh
#
# It draws a fixed-size gradient "card" on a transparent canvas, so it looks
# the same regardless of your font/cell size. Edit TITLE / SUBTITLE below.

TITLE='WELCOME  TO  SHOETERM'
SUBTITLE=`date`

# Card geometry (pixels)
ox=8; oy=8; CW=560; CH=104

# Canvas is sized in *cells*, but the card is a fixed pixel size. Ask foot for
# its actual cell size (ESC[16t -> ESC[6;h;w t) so we reserve exactly enough
# rows/cols and leave no padding under the banner. Query the controlling
# terminal (/dev/tty) not stdin, so it works even with redirected input.
# Fall back to ~8x16 cells.
cw_px=8; ch_px=16
old=`stty -g </dev/tty 2>/dev/null` && {
  stty raw -echo min 0 time 2 </dev/tty 2>/dev/null
  printf '\033[16t' >/dev/tty
  resp=`dd bs=1 count=20 </dev/tty 2>/dev/null`
  stty "$old" </dev/tty 2>/dev/null
  h=`printf '%s' "$resp" | sed -n 's/.*\[6;\([0-9]*\);\([0-9]*\)t.*/\1/p'`
  w=`printf '%s' "$resp" | sed -n 's/.*\[6;\([0-9]*\);\([0-9]*\)t.*/\2/p'`
  [ -n "$h" ] && ch_px=$h
  [ -n "$w" ] && cw_px=$w
}
cols=$(( (ox + CW + cw_px - 1) / cw_px ))   # ceil((ox+CW)/cell_w)
rows=$(( (oy + CH + ch_px - 1) / ch_px ))   # ceil((oy+CH)/cell_h)

{
  printf '\033P>g\n'
  printf 'size %d %d\n' "$cols" "$rows"  # canvas (cells) - snug around the card
  printf 'bg none\n'          # transparent around the card

  # --- gradient fill (2px vertical strips) ---
  awk -v ox="$ox" -v oy="$oy" -v cw="$CW" -v ch="$CH" 'BEGIN{
    split("0 0.42 0.74 1.0", st, " ")
    split("22 9 54  64 18 104  132 36 150  206 46 130", col, " ")
    for (x = 0; x < cw; x += 2) {
      t = x / cw
      for (i = 0; i < 3; i++) {
        a = st[i+1]; b = st[i+2]
        if (t <= b) {
          u = (t - a) / (b - a)
          r  = int(col[i*3+1] + u*(col[(i+1)*3+1] - col[i*3+1]))
          g  = int(col[i*3+2] + u*(col[(i+1)*3+2] - col[i*3+2]))
          bl = int(col[i*3+3] + u*(col[(i+1)*3+3] - col[i*3+3]))
          printf "pen #%02x%02x%02x\nrectf %d %d 2 %d\n", r, g, bl, ox+x, oy, ch
          break
        }
      }
    }
  }'

  # --- top sheen + bright edge ---
  printf 'pen #ffffff12\n';  printf 'rectf %d %d %d 24\n' "$ox" "$oy" "$CW"
  printf 'pen #ffffffa0\n';  printf 'rectf %d %d %d 2\n'  "$ox" "$oy" "$CW"

  # --- "sunrise" motif, top-right ---
  printf 'thickness 2\n'
  printf 'pen #ffd6ffbe\n'; printf 'arc %d %d 14 95 210\n' $((ox+CW-48)) $((oy+30))
  printf 'pen #ffd6ffa4\n'; printf 'arc %d %d 25 95 210\n' $((ox+CW-48)) $((oy+30))
  printf 'pen #ffd6ff88\n'; printf 'arc %d %d 36 95 210\n' $((ox+CW-48)) $((oy+30))
  printf 'pen #ffd6ff6c\n'; printf 'arc %d %d 47 95 210\n' $((ox+CW-48)) $((oy+30))
  printf 'pen #ffd6ff50\n'; printf 'arc %d %d 58 95 210\n' $((ox+CW-48)) $((oy+30))
  printf 'pen #ffffff\n';   printf 'circf %d %d 4\n'       $((ox+CW-48)) $((oy+30))

  # --- left accent bar ---
  printf 'pen #38e0ff\n'
  printf 'rrectf %d %d 7 %d 3\n' $((ox+22)) $((oy+22)) $((CH-44))

  # --- flourish under the title ---
  printf 'pen #dc82f0\n'
  printf 'bezier %d %d %d %d %d %d %d %d\n' \
    $((ox+44)) $((oy+58)) $((ox+150)) $((oy+50)) \
    $((ox+260)) $((oy+66)) $((ox+360)) $((oy+54))

  # --- bullet diamond before the subtitle ---
  printf 'pen #ff38e0\n'
  printf 'polyf %d %d %d %d %d %d %d %d\n' \
    $((ox+44)) $((oy+77)) $((ox+49)) $((oy+82)) \
    $((ox+44)) $((oy+87)) $((ox+39)) $((oy+82))

  # --- title + subtitle text (uses your font) ---
  printf 'pen #ffffff\n'; printf 'text %d %d %s\n' $((ox+44)) $((oy+46)) "$TITLE"
  printf 'pen #d8c8ff\n'; printf 'text %d %d %s\n' $((ox+58)) $((oy+88)) "$SUBTITLE"

  printf '\033\\'
} 2>/dev/null

printf '\n'

