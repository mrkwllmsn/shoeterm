#!/bin/sh
# memtop.sh - a live memory-usage dashboard drawn with foot's vector graphics
# protocol. Re-renders a fixed-size "card" in place every interval, so it looks
# the same regardless of your font/cell size.
#
#   Run it:   ./bld/debug/foot sh memtop.sh
#   Interval: ./bld/debug/foot sh memtop.sh 2      # seconds (default 1)
#   Oneshot:  ./bld/debug/foot sh memtop.sh once   # draw a single frame & exit
#
# Reads /proc/meminfo. A half-ring "speedometer" shows % RAM in use, stacked
# bars break RAM (used / cache / free) and swap down, and an area graph tracks
# the usage history. Press q or Ctrl-C to quit (live mode).
#
# Oneshot mode draws one frame at the cursor and returns (no clear, no cursor
# hijack) so it can be dropped into welcome.sh / a shell startup banner.

ONESHOT=""
case "${1:-}" in
  once|oneshot|--once|-1) ONESHOT=1; INTERVAL=1 ;;
  *)                      INTERVAL=${1:-1} ;;
esac

# --- card geometry (pixels) -------------------------------------------------
ox=8; oy=8; CW=760; CH=300

# Ask foot for its real cell size (ESC[16t -> ESC[6;h;w t) so we reserve just
# enough rows/cols. Query /dev/tty so it works with redirected stdin. Fall back
# to ~8x16.
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

# --- terminal setup / cleanup (live mode only) ------------------------------
if [ -z "$ONESHOT" ]; then
  tty_old=`stty -g </dev/tty 2>/dev/null`
  cleanup() {
    stty "$tty_old" </dev/tty 2>/dev/null
    printf '\033[?25h\033[%d;1H\n' $((rows+1)) >/dev/tty # show cursor, drop below card
  }
  trap 'cleanup; exit 0' INT TERM
  trap 'cleanup' EXIT
  stty -echo -icanon min 0 time 0 </dev/tty 2>/dev/null  # raw-ish: read keys nonblocking
  printf '\033[2J\033[?25l' >/dev/tty                    # clear once, hide cursor
fi

HIST=""          # space-separated history of % used
MAXPTS=120

draw() {
  # Read memory (kB) from /proc/meminfo.
  set -- `awk '
    /^MemTotal:/      {tot=$2}
    /^MemFree:/       {free=$2}
    /^MemAvailable:/  {avail=$2}
    /^Buffers:/       {buf=$2}
    /^Cached:/        {cache=$2}
    /^SReclaimable:/  {sr=$2}
    /^SwapTotal:/     {st=$2}
    /^SwapFree:/      {sf=$2}
    END{
      cac = buf + cache + sr
      used = tot - free - cac              # app-used (excludes reclaimable cache)
      uavail = tot - avail                 # what the % gauge tracks
      printf "%d %d %d %d %d %d", tot, used, cac, uavail, st, st-sf
    }' /proc/meminfo`
  MTOTAL=$1; MUSED=$2; MCACHE=$3; MUAVAIL=$4; STOTAL=$5; SUSED=$6

  PCT=$(( MTOTAL > 0 ? MUAVAIL * 100 / MTOTAL : 0 ))

  # update history
  HIST="$HIST $PCT"
  set -- $HIST
  while [ $# -gt $MAXPTS ]; do shift; done
  HIST="$*"

  TS=`date '+%H:%M:%S'`

  {
    printf '\033P>g\n'
    printf 'size %d %d\n' "$cols" "$rows"
    printf 'bg none\n'

    awk -v ox="$ox" -v oy="$oy" -v W="$CW" -v H="$CH" \
        -v tot="$MTOTAL" -v used="$MUSED" -v cac="$MCACHE" \
        -v uavail="$MUAVAIL" -v pct="$PCT" \
        -v stot="$STOTAL" -v sused="$SUSED" \
        -v ts="$TS" -v hist="$HIST" 'BEGIN{
      # palette
      bg="#11141c"; panel="#1b2030"; ink="#e8ecf5"; dim="#8893ad"
      red="#ff5470"; amber="#ffb454"; green="#3ddc97"; blue="#4aa8ff"
      # usage-tier color
      tier = (pct<60)? green : (pct<85)? amber : red

      # ---- card background ----
      printf "pen %s\nrrectf %d %d %d %d 16\n", bg, ox, oy, W, H
      printf "pen %s\nrrect %d %d %d %d 16\n", "#2a3145", ox, oy, W, H

      # ---- header ----
      printf "pen %s\ntext %d %d MEMORY  USAGE\n", ink, ox+24, oy+34
      printf "pen %s\ntext %d %d %s\n", dim, ox+W-96, oy+34, ts
      printf "pen %s\nrectf %d %d %d 2\n", "#2a3145", ox+24, oy+48, W-48

      # ===================== speedometer (left) =====================
      gx = ox+150; gy = oy+190; gr = 92
      # half-ring gauge built from overlapping filled circles (the arc command
      # renders partial sweeps inconsistently; circf segments are reliable).
      # 180..360 sweeps bottom-left, up over the top, to the right.
      ring(gx, gy, gr, 180, 360, panel, 9)
      end = 180 + 180*pct/100.0
      if (pct > 0) ring(gx, gy, gr, 180, end, tier, 9)
      # ticks
      printf "thickness 1\npen %s\n", dim
      for (a=180; a<=360; a+=22.5) {
        rad=a*3.14159265/180.0
        x1=gx+(gr+12)*cos(rad); y1=gy+(gr+12)*sin(rad)
        x2=gx+(gr+18)*cos(rad); y2=gy+(gr+18)*sin(rad)
        printf "line %.0f %.0f %.0f %.0f\n", x1,y1,x2,y2
      }
      # big % readout
      printf "pen %s\nthickness 1\n", tier
      printf "text %d %d %d%%\n", gx-22, gy-8, pct
      printf "pen %s\ntext %d %d in use\n", dim, gx-22, gy+14
      printf "pen %s\ntext %d %d %s\n", dim, gx-78, gy+44, gb(tot) " GB total"

      # ===================== right column =====================
      rx = ox+310; rw = W-310-32

      # ---- RAM stacked bar ----
      by = oy+78; bh = 30
      printf "pen %s\ntext %d %d RAM\n", ink, rx, by-8
      printf "pen %s\ntext %d %d %s / %s GB\n", dim, rx+rw-150, by-8, gb(uavail), gb(tot)
      stack(rx, by, rw, bh, tot, used, cac, red, amber, panel)

      # legend
      ly = by+bh+18
      legend(rx,        ly, red,   "used "  gb(used) "G")
      legend(rx+rw*0.34,ly, amber, "cache " gb(cac) "G")
      legend(rx+rw*0.70,ly, panel, "free "  gb(tot-used-cac) "G")

      # ---- swap bar ----
      sy = ly+34; sbh=22
      printf "pen %s\ntext %d %d SWAP\n", ink, rx, sy-8
      if (stot>0)
        printf "pen %s\ntext %d %d %s / %s GB\n", dim, rx+rw-150, sy-8, gb(sused), gb(stot)
      else
        printf "pen %s\ntext %d %d none\n", dim, rx+rw-60, sy-8
      printf "pen %s\nrrectf %d %d %d %d 6\n", panel, rx, sy, rw, sbh
      if (stot>0) {
        sw = rw*sused/stot; if (sw<2 && sused>0) sw=2
        printf "pen %s\nrrectf %d %d %.0f %d 6\n", blue, rx, sy, sw, sbh
      }

      # ===================== history area graph (bottom) =====================
      gx0 = ox+24; gy0 = oy+H-24; gw = W-48; ght = 70
      gtop = gy0-ght
      printf "pen %s\nrrectf %d %d %d %d 8\n", "#141824", gx0, gtop, gw, ght
      # gridlines at 25/50/75%
      printf "thickness 1\npen %s\n", "#222a3c"
      for (i=1;i<=3;i++){ yy=gtop+ght*i/4.0; printf "line %d %.0f %d %.0f\n", gx0, yy, gx0+gw, yy }
      printf "pen %s\ntext %d %d history\n", dim, gx0+6, gtop+14

      n = split(hist, hv, " ")
      if (n>=1) {
        # filled area as 1px-ish vertical strips, plus a top stroke line
        prevx=-1; prevy=-1
        for (i=1;i<=n;i++){
          x = gx0 + (n==1? gw : gw*(i-1)/(n-1))
          v = hv[i]+0; if(v<0)v=0; if(v>100)v=100
          y = gy0 - ght*v/100.0
          # area strip
          printf "pen %s\nrectf %.0f %.0f 2 %.0f\n", "#3ddc9733", x, y, gy0-y
          if (prevx>=0) {
            printf "pen %s\nthickness 2\nline %.0f %.0f %.0f %.0f\n", green, prevx, prevy, x, y
          }
          prevx=x; prevy=y
        }
        # leading dot
        printf "pen %s\ncircf %.0f %.0f 3\n", green, prevx, prevy
      }

      printf "\n"
    }
    function gb(kb){ return sprintf("%.1f", kb/1048576.0) }
    function ring(cx,cy,r,a0,a1,col,t,   a,rad){
      printf "pen %s\n", col
      for (a=a0; a<=a1; a+=2){
        rad = a*3.14159265/180.0
        printf "circf %.0f %.0f %d\n", cx+r*cos(rad), cy+r*sin(rad), t
      }
    }
    function stack(x,y,w,h,t,u,c,cu,cc,cf){
      printf "pen %s\nrrectf %d %d %d %d 6\n", cf, x, y, w, h
      uw = w*u/t; cw2 = w*c/t
      if (uw>0){ printf "pen %s\nrrectf %d %d %.0f %d 6\n", cu, x, y, uw, h }
      if (cw2>0){ printf "pen %s\nrectf %.0f %d %.0f %d\n", cc, x+uw, y, cw2, h }
    }
    function legend(x,y,col,label){
      printf "pen %s\nrrectf %.0f %d 12 12 3\n", col, x, y-10
      printf "pen %s\ntext %.0f %d %s\n", "#b9c2d8", x+18, y, label
    }'
    printf '\033\\'
  }
}

# --- oneshot: one frame at the cursor, then return --------------------------
if [ -n "$ONESHOT" ]; then
  draw 2>/dev/null
  printf '\n'        # advance past the card so the prompt/banner continues below
  exit 0
fi

# --- live loop: redraw the card in place ------------------------------------
while :; do
  printf '\033[H' >/dev/tty           # home; redraw over itself (overwrite erases old)
  draw >/dev/tty 2>/dev/null
  # wait INTERVAL seconds (>=1) but stay responsive to 'q'
  i=0
  while [ "$i" -lt "$INTERVAL" ]; do
    key=`dd bs=1 count=1 </dev/tty 2>/dev/null`
    case "$key" in q|Q) exit 0 ;; esac
    sleep 1
    i=$((i+1))
  done
done
