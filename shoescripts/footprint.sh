#!/bin/sh
# A footprint logo, drawn with foot's vector graphics protocol.
#
#   Try it:  ./bld/debug/foot sh newfootprint.sh
#
# Draws a black foot-sole silhouette (rounded heel-to-ball sole + five toes of
# decreasing size) on a transparent, fixed-pixel "card", so it looks the same
# regardless of your font/cell size. The sole is a smooth closed Catmull-Rom
# spline; the toes are tilted ellipses.
#
# Env: FOOT_COLOR (default #ff00ff; use #141414 for the inky original look).

FOOT_COLOR=${FOOT_COLOR:-'#ff99ff'}

# Card geometry (pixels) — bounding box of the whole mark.
ox=12; oy=12; CW=266; CH=562

# Ask foot for its real cell size (ESC[16t -> ESC[6;h;w t) so we reserve exactly
# enough rows/cols. Query the controlling terminal, fall back to ~8x16.
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
cols=$(( (ox + CW + cw_px - 1) / cw_px ))
rows=$(( (oy + CH + ch_px - 1) / ch_px ))

{
  printf '\033P>g\n'
  printf 'size %d %d\n' "$cols" "$rows"
  printf 'bg none\n'
  printf 'pen %s\n' "$FOOT_COLOR"

  awk -v ox="$ox" -v oy="$oy" '
    function emitpts(n,   i){            # print the px,py arrays as polyf args
      printf "polyf"
      for (i = 0; i < n; i++) printf " %d %d", int(px[i]+ox+0.5), int(py[i]+oy+0.5)
      printf "\n"
    }
    # Closed Catmull-Rom spline through ax[]/ay[] (n anchors) -> filled polygon.
    function spline(n,  i,j,k,t,o,p0,p1,p2,p3,steps){
      steps = 14; o = 0
      for (i = 0; i < n; i++) {
        for (j = 0; j < steps; j++) {
          t = j / steps
          # x
          p0=ax[(i-1+n)%n]; p1=ax[i]; p2=ax[(i+1)%n]; p3=ax[(i+2)%n]
          px[o] = 0.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t)
          # y
          p0=ay[(i-1+n)%n]; p1=ay[i]; p2=ay[(i+1)%n]; p3=ay[(i+2)%n]
          py[o] = 0.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t)
          o++
        }
      }
      emitpts(o)
    }
    # Tilted ellipse -> filled polygon. rot in degrees, cw from +x.
    function ellipse(cx,cy,rx,ry,rot,  k,N,th,c,s,cr,sr,ex,ey){
      N = 28; rot = rot*3.14159265/180; cr = cos(rot); sr = sin(rot)
      for (k = 0; k < N; k++) {
        th = 2*3.14159265*k/N; c = cos(th); s = sin(th)
        ex = rx*c; ey = ry*s
        px[k] = cx + ex*cr - ey*sr
        py[k] = cy + ex*sr + ey*cr
      }
      emitpts(N)
    }
    BEGIN {
      # --- sole: closed spline through these anchors (clockwise from ball) ---
      n = split("88 150  150 120  210 150  236 210  236 330  220 440  185 520  140 548  95 525  78 440  96 360  66 270  72 195", S, " ")
      m = 0
      for (i = 1; i <= n; i += 2) { ax[m] = S[i]; ay[m] = S[i+1]; m++ }
      spline(m)

      # --- five toes, big -> little, tilting as they wrap the ball ---
      ellipse(212,  78, 46, 54,  -8)
      ellipse(150,  80, 36, 42, -16)
      ellipse(102, 108, 31, 37, -24)
      ellipse( 66, 150, 27, 32, -30)
      ellipse( 44, 200, 23, 27, -36)
    }
  '

  printf '\033\\'
} 2>/dev/null

printf '\n'
