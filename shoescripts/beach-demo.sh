#!/bin/sh
# Full-terminal beach sunset, drawn with foot's vector graphics protocol.
# Run inside the freshly-built foot:
#
#     ./bld/debug/foot sh beach-demo.sh
#
# The canvas is sized in *cells* but everything is laid out as fractions of the
# pixel canvas, so it fills the whole window at any size / font. We ask the
# terminal for its grid (rows x cols) and its cell pixel size (ESC[16t) and
# build a canvas exactly that big.
#
# Scene, back to front: a graded dusk sky, soft clouds, a low sun with glow,
# the sea with a shimmering sun-reflection, a little sailboat on the horizon,
# a foamy shoreline onto graded sand, and a palm-tree silhouette in front.

# --- terminal grid (cells) -------------------------------------------------
cols=$(tput cols 2>/dev/null); rows=$(tput lines 2>/dev/null)
[ -n "$cols" ] || cols=80
[ -n "$rows" ] || rows=24

# --- cell pixel size (fall back to ~8x16) ----------------------------------
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

W=$(( cols * cw_px ))
H=$(( rows * ch_px ))

# --- draw ------------------------------------------------------------------
printf '\033[2J\033[H'              # clear screen, cursor home

{
printf '\033P>g\n'
printf 'size %d %d\n' "$cols" "$rows"
printf 'bg none\n'

awk -v W="$W" -v H="$H" '
function ci(a,b,t){ return int(a + (b-a)*t) }

# Vertical gradient: stacked filled rects from y0..y1, colour r0g0b0 -> r1g1b1.
function band(y0,y1, r0,g0,b0, r1,g1,b1,   n,i,t,yy,hh,r,g,b){
  n=48
  for(i=0;i<n;i++){
    t=(n>1)?i/(n-1):0
    r=ci(r0,r1,t); g=ci(g0,g1,t); b=ci(b0,b1,t)
    yy=y0+(y1-y0)*i/n
    hh=int((y1-y0)/n)+2
    printf "pen #%02x%02x%02x\nrectf %d %d %d %d\n", r,g,b, 0,int(yy),W,hh
  }
}

# A fluffy cloud = a few overlapping circles on a flat base.
function cloud(cx,cy,s,al){
  printf "pen #ffffff%s\n", al
  printf "rectf %d %d %d %d\n", cx-int(s*0.4), cy, int(s*3.0), int(s*0.7)
  printf "circf %d %d %d\n", cx,            cy,            int(s*0.62)
  printf "circf %d %d %d\n", cx+s,          cy+int(s*0.10),int(s*0.78)
  printf "circf %d %d %d\n", cx+2*s,        cy,            int(s*0.55)
  printf "circf %d %d %d\n", cx+int(s*0.6), cy-int(s*0.35),int(s*0.50)
}

function bird(x,y,s){
  printf "thickness 2\npen #34464d\n"
  printf "line %d %d %d %d\n", x-s, y, x, y-int(s*0.55)
  printf "line %d %d %d %d\n", x, y-int(s*0.55), x+s, y
}

# A palm frond: arch up from the crown then droop to (ex,ey).
function frond(x0,y0,ex,ey,th,   c1x,c1y,c2x,c2y,span){
  span = ey - y0
  c1x = x0 + int(0.40*(ex-x0)); c1y = y0 - int(0.55*ay)
  c2x = ex - int(0.10*(ex-x0)); c2y = ey - int(0.25*ay)
  printf "thickness %d\npen #133024\n", th
  printf "bezier %d %d %d %d %d %d %d %d\n", x0,y0, c1x,c1y, c2x,c2y, ex,ey
}

BEGIN{
  hor = int(H*0.55)         # horizon (sky / sea split)
  sea = int(H*0.72)         # waterline (sea / sand split)

  # --- sky (two-stop dusk gradient) ---
  band(0,            int(hor*0.5), 40,54,112,   124,152,206)
  band(int(hor*0.5), hor,          124,152,206, 255,202,150)

  # --- sea ---
  band(hor, sea, 122,160,180, 16,52,86)

  # --- sand ---
  band(sea, H, 208,182,130, 242,220,168)

  # --- clouds (upper sky, away from the sun) ---
  cloud(int(W*0.12), int(H*0.13), int(W*0.028)+6, "b4")
  cloud(int(W*0.70), int(H*0.09), int(W*0.022)+5, "a0")
  cloud(int(W*0.45), int(H*0.20), int(W*0.018)+4, "84")

  # --- distant birds ---
  bs=int(H*0.018)+4
  bird(int(W*0.30), int(H*0.20), bs)
  bird(int(W*0.36), int(H*0.17), int(bs*0.8))
  bird(int(W*0.33), int(H*0.24), int(bs*0.7))

  # --- sun + glow (sits on the horizon) ---
  sx=int(W*0.52); r=int(H*0.11); sy=hor-int(r*0.18)
  printf "pen #ff985422\ncircf %d %d %d\n", sx,sy,int(r*2.7)
  printf "pen #ffac6432\ncircf %d %d %d\n", sx,sy,int(r*2.0)
  printf "pen #ffc67e48\ncircf %d %d %d\n", sx,sy,int(r*1.5)
  printf "pen #ffe6ab\ncircf %d %d %d\n",   sx,sy,r
  printf "pen #fff4cf\ncircf %d %d %d\n",   sx,sy,int(r*0.80)

  # --- sun reflection shimmer on the water ---
  nb=16
  for(i=0;i<nb;i++){
    yy = hor + (sea-hor)*i/nb
    ww = int(r*0.5 + (r*1.9)*i/nb)
    hh = int((sea-hor)/nb*0.55)+1
    if(i%2==0) a="ffe9aa72"; else a="ffd98a4a"
    printf "pen #%s\nrrectf %d %d %d %d 3\n", a, sx-int(ww/2), int(yy), ww, hh
  }

  # --- sailboat on the horizon (left of the sun) ---
  bx=int(W*0.30); by=hor+int((sea-hor)*0.16); bz=int(H*0.045)
  printf "pen #f4ead0\ntrif %d %d %d %d %d %d\n", bx,by-int(bz*1.9), bx,by, bx+int(bz*0.95),by
  printf "pen #e6d9bc\ntrif %d %d %d %d %d %d\n", bx,by-int(bz*1.7), bx,by, bx-int(bz*0.7),by
  printf "pen #2c2c34\npolyf %d %d %d %d %d %d %d %d\n", \
    bx-bz,by, bx+bz,by, bx+int(bz*0.55),by+int(bz*0.45), bx-int(bz*0.55),by+int(bz*0.45)

  # --- foamy shoreline (wavy translucent white along the waterline) ---
  printf "thickness 5\npen #ffffffcc\n"
  printf "bezier %d %d %d %d %d %d %d %d\n", 0,sea, int(W*0.30),sea-9, int(W*0.55),sea+9, int(W*0.78),sea-5
  printf "bezier %d %d %d %d %d %d %d %d\n", int(W*0.78),sea-5, int(W*0.88),sea-12, int(W*0.95),sea+8, W,sea
  printf "thickness 2\npen #ffffff80\n"
  printf "bezier %d %d %d %d %d %d %d %d\n", 0,sea+int(H*0.02), int(W*0.35),sea+int(H*0.015), int(W*0.65),sea+int(H*0.03), W,sea+int(H*0.018)

  # --- palm-tree silhouette (foreground, right) ---
  bx2=int(W*0.84); tx=int(W*0.74); ty=int(H*0.21)
  tn=int(W*0.016)+4
  printf "pen #173024\nthickness %d\n", tn
  printf "bezier %d %d %d %d %d %d %d %d\n", bx2,H, bx2-int(W*0.015),int(H*0.62), tx+int(W*0.03),int(H*0.36), tx,ty
  printf "thickness %d\n", int(tn*0.55)
  printf "bezier %d %d %d %d %d %d %d %d\n", bx2,H, bx2-int(W*0.015),int(H*0.62), tx+int(W*0.03),int(H*0.36), tx,ty

  # crown of fronds
  ax=int(W*0.17); ay=int(H*0.17); fth=int(W*0.006)+3
  frond(tx,ty, tx-ax,            ty+int(ay*0.55), fth)   # far left, drooping
  frond(tx,ty, tx-int(ax*0.8),   ty-int(ay*0.45), fth)   # upper left
  frond(tx,ty, tx-int(ax*0.3),   ty-ay,           fth)   # up
  frond(tx,ty, tx+int(ax*0.3),   ty-ay,           fth)   # up right
  frond(tx,ty, tx+int(ax*0.8),   ty-int(ay*0.40), fth)   # upper right
  frond(tx,ty, tx+ax,            ty+int(ay*0.55), fth)   # far right, drooping
  frond(tx,ty, tx-int(ax*0.6),   ty+int(ay*0.95), fth)   # low left
  frond(tx,ty, tx+int(ax*0.6),   ty+int(ay*0.95), fth)   # low right

  # coconuts
  cr=int(H*0.012)+2
  printf "pen #0f2018\ncircf %d %d %d\n", tx+5, ty+7,  cr
  printf "circf %d %d %d\n",              tx-6, ty+11, cr
  printf "circf %d %d %d\n",              tx+1, ty+14, cr
}
'

printf '\033\\'
}

