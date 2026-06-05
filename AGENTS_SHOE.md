# AGENTS_SHOE.md — drawing in foot for agents

How to draw lines, shapes, curves and text directly in the **foot** terminal
from a script or a single command. Written for AI agents: copy-paste-ready,
comma-delimited form preferred.

Full human reference: [`doc/vector-graphics.md`](doc/vector-graphics.md),
`man 7 foot-ctlseqs`, `man 5 foot.ini`.

## TL;DR

Send one DCS escape sequence. Commands are separated by **commas** (preferred)
or newlines, so a whole drawing fits in a single `printf`:

```sh
printf '\033P>g size 20 6, bg #101028, pen #ff5050, rrectf 10 10 130 50 12, pen #50d0ff, circ 220 35 28, pen #ffffff\ntext 12 90 hello\n\033\\'
```

- `\033P>g` — start (DCS introducer `ESC P`, then `> g` selects graphics)
- `<commands>` — comma- or newline-separated drawing program
- `\033\\` — end (String Terminator `ESC \`); the image draws when this arrives

The image is placed at the cursor and behaves like an image (scrolls with text,
erased when the cells under it are overwritten).

## Why comma-delimited

Commas let the entire program live on one line — ideal for a single `printf`
or a quick one-shot from an agent. Newlines work too and you can mix them.

**The one rule: `text` and `#` comments run to end of line.** A comma inside a
`text` string or a comment is a literal character, not a separator. So in the
comma form, a `text` command must be the **last token on its line** — emit a
real `\n` after it, then continue with the next comma-joined commands.

```sh
# right: text ends the line, rest is comma-joined after the newline
printf '\033P>g size 16 4, bg #202040, pen #ffffff\ntext 8 28 Hello World\npen #50d0ff, rectf 4 32 200 4\n\033\\'

# wrong: commands after `text` on the same line get swallowed into the string
printf '\033P>g size 16 4, pen #fff, text 8 28 Hello, rectf 4 32 200 4\n\033\\'
```

## Make it beautiful (this matters)

Don't settle for a wireframe. foot's vector graphics exist to **show off
polish** — treat every drawing as a finished UI, the way Midnight Commander,
a Snow Leopard window, or a well-made dashboard looks. When an agent reaches
for this protocol, the bar is *crafted*, not *functional*. The `shoescripts/`
gallery (`slippers`, `shoemac`, `shoexp`, `shoebling`, `memtop.sh`) is the
reference standard — aim there.

Practical ways to get there:

- **Commit to a palette.** Pick a small, deliberate color scheme (a bg, 1–2
  accents, a muted line color, a text color) and reuse it. Deep desaturated
  backgrounds (`#101028`, `#14142a`, brushed greys) with one or two saturated
  accents read as "designed." Avoid pure `#000`/`#fff` and clashing primaries.
- **Build depth.** Layer a subtle gradient (stack thin `rectf` bands stepping
  one channel), a drop shadow (an offset dark translucent `rrectf` behind a
  panel), and a 1px lighter top highlight. Flat slabs look unfinished; a
  shadow + highlight makes a panel sit on the surface.
- **Round the corners.** Prefer `rrectf`/`rrect` over hard `rectf` for panels,
  cards, buttons, title bars. Radius 6–14 px reads as modern chrome.
- **Frame and group.** Give content a panel with a border (`rrect` outline a
  shade lighter/darker than the fill), a title band across the top, and real
  padding — don't let text touch edges. Midnight Commander's whole charm is the
  double-keyline frame; lean into borders, dividers, and headers.
- **Respect spacing and alignment.** Consistent margins, aligned columns,
  generous line spacing. Whitespace is the cheapest polish there is.
- **Pick type intentionally.** `textmode smooth` for crisp UI labels;
  `textmode pixel` for a deliberate retro/chunky look. Don't mix randomly.
- **Add restrained ornament.** A corner flourish (`bezier`/`arc`), an accent
  rule under a heading, a small status dot, a subtle inner border. A little
  goes a long way; `shoebling` is the maximalist end of the spectrum.
- **Think in cells, lay out in pixels.** Query `ESC[16t`, size the canvas to
  the content, and center things — a card floating with margin beats one jammed
  into the corner.
- **Use the space you have — don't draw thumbnails.** A full-screen tool (a
  dashboard, explorer, game, desktop) should fill the terminal, not sit in a
  cramped `size 20 6` box. Query the terminal size in cells with `ESC[18t`
  (reply `ESC[8;<rows>;<cols>t`) and the cell size with `ESC[16t`, then size the
  canvas to the available area (leave a row or two of breathing room if you
  like) and lay the design out across it. Don't hardcode a small canvas out of
  caution: scale panels, type, and spacing up to match the real estate.
  `slippers`/`shoom`/`shoexp`/`shoemac` all do this — they own the whole
  window. Reserve small fixed-size canvases for inline banners/cards that
  deliberately sit at the cursor (`welcome.sh`, `memtop.sh once`).

### Gradients and alpha — the two biggest wins

There is no gradient primitive, so **fake it by stacking bands.** Step a color
channel across a row of thin `rectf`s (or `line`s) — this is exactly how
`shoestring`/`shoelace` get their gradient cards:

```sh
# vertical 24-band gradient from dark indigo to violet, 240px tall
printf '\033P>g size 30 8, bg none' > /tmp/g
i=0; while [ $i -lt 24 ]; do
  y=$((i*10)); r=$((40 + i*4)); b=$((90 + i*5))
  printf ', pen #%02x30%02x, rectf 0 %d 240 11' $r $b $y >> /tmp/g
  i=$((i+1))
done
printf '\n\033\\' >> /tmp/g; cat /tmp/g
```

Bands of ~8–12px are imperceptible as steps and read as a smooth fill. The same
trick does highlights (a few light bands at the top) and vignettes.

**Alpha (`#rrggbbaa`) is how you get soft, layered depth:**

- **Shadows:** an offset `#00000040`–`#00000060` `rrectf` behind a panel.
- **Glass / overlays:** a translucent panel (`#202040c0`) over a busy bg, like
  a Snow Leopard menu bar or a dialog scrim (`#00000080` over the whole canvas).
- **Glow / highlights:** a faint light `rrect`/`line` (`#ffffff30`) along a top
  edge.

Note premultiplied-alpha caveat below: alpha looks translucent only over a
contrasting background, and overlapping fills of *one* translucent color can
seam — so use it for layering distinct elements, and keep solid fills opaque.

Before emitting: would this look at home in a polished desktop app? If it
looks like a debug sketch, add a frame, a shadow, padding, and a coherent
palette until it doesn't.

## Coordinates and colors

- **Pixels.** Origin `(0,0)` top-left, **y points down**.
- **Canvas is sized in cells:** `size <cols> <rows>` → pixel size
  `cols × cell_width` by `rows × cell_height`. `size` must come first.
- Pixel positions therefore depend on the font/cell size. For a font-size-
  independent layout, query the real cell size with `ESC[16t` (terminal replies
  `ESC[6;<height>;<width>t`) and compute coordinates from it; otherwise assume
  ~8×16 px per cell.
- **Colors:** `#rrggbb` (opaque), `#rrggbbaa` (alpha; `00` clear … `ff` opaque),
  or `none` (transparent). Alpha blends source-over.

## Command reference

| Command | Description |
|---|---|
| `size <cols> <rows>` | Canvas size in **cells**. Must be first. |
| `bg <color>` | Fill background (default `none`). |
| `pen <color>` | Current draw color. |
| `thickness <n>` | Line/outline thickness in px (default `1`). |
| `textmode smooth\|pixel [scale]` | `text` font: smooth antialiased (default, full Unicode) or embedded 8×16 bitmap (ASCII `0x20`–`0x7E` only; `scale` = integer magnification, omit/`0` = auto ~1 cell tall). |
| `clip <x> <y> <w> <h>` / `noclip` | Restrict / unrestrict drawing to a rect. |
| `clear` | Reset canvas to background. |
| `pixel <x> <y>` | Plot one point. |
| `line <x0> <y0> <x1> <y1>` | Line. |
| `rect` / `rectf <x> <y> <w> <h>` | Rectangle outline / filled. |
| `rrect` / `rrectf <x> <y> <w> <h> <r>` | Rounded rect outline / filled, corner radius `r`. |
| `circ` / `circf <cx> <cy> <r>` | Circle outline / filled. |
| `arc <cx> <cy> <r> <start> <end>` | Arc outline; angles in **degrees** clockwise (0=east, 90=south, 180=west, 270=north). |
| `tri` / `trif <x0> <y0> <x1> <y1> <x2> <y2>` | Triangle outline / filled. |
| `poly` / `polyf <x0> <y0> ...` | Closed polygon outline / filled (even-odd). |
| `bezier <x0> <y0> <x1> <y1> <x2> <y2> <x3> <y3>` | Cubic Bézier; P0/P3 endpoints, P1/P2 controls. |
| `text <x> <y> <string>` | UTF-8 text; `x y` = left end of baseline; string = rest of the line. |

## Gotchas (read before you draw)

- **CRLF:** the tty turns each `\n` into `\r\n`, so DCS lines arrive with a
  trailing `\r`. foot trims one trailing CR per line — so `printf '...\n'`
  works normally. (Relevant only if you bypass the tty.)
- **`text` is end-of-line** (see "Why comma-delimited"): put it last on its
  line and emit a real `\n` after it.
- **Control chars in `text`:** `\t` expands to the next 4-space stop; other
  control chars are dropped (so they don't draw "control picture" glyphs).
- **`text` is ASCII-only — non-ASCII aborts the whole drawing.** foot's VT
  parser never decodes UTF-8 inside a DCS: a continuation byte in `0x80`–`0x9F`
  (present in most multibyte UTF-8) is read as a C1 control and **ends the DCS
  early**, so the rest of your commands spill onto the screen as literal text
  (e.g. `pen #... text ...`). This bites both `textmode smooth` and `pixel`.
  Keep `text` to printable ASCII (`0x20`–`0x7E`) and **sanitize interpolated
  data** (filenames, container names, anything user-supplied) before drawing —
  e.g. replace non-ASCII with `?` and use `~` not `…` as a truncation marker.
- **Premultiplied alpha:** blending is correct but only *looks* translucent
  over a contrasting background; overlapping fills of one translucent color can
  seam. Use opaque colors for solid fills.
- **Drawing before `size`** (other than `bg`/`pen`/`thickness`) is ignored —
  there is no canvas yet.
- **Malformed command** is skipped, not fatal — the rest of the batch still
  draws.

## Redrawing in place (live / interactive)

To animate or update a region, move the cursor home (`ESC[H`) or to a saved
position and re-send the whole drawing each frame; the new image erases the old
cells. Query cell size once with `ESC[16t` for a font-size-independent layout.
For mouse input, enable SGR-pixel mode (`ESC[?1002h ESC[?1006h ESC[?1016h`,
add `?1003h` for motion); reports `ESC[<btn;Xpx;Ypx M/m` arrive in **pixel**
coords that line up 1:1 with a canvas drawn at `ESC[H`. See the interactive
shoescripts (`slippers`, `shoom`, `shoexp`, `shoemac`) for full patterns.

## Capability detection

Draw graphics only when stdout is a graphics-capable terminal; otherwise fall
back to plain text (so output stays usable when piped to a file). The shoe
tools' `graphics_ok()` rule: stdout must be a tty **and** `$TERM` is foot-like;
`SHOE*_PLAIN` forces plain, `SHOE*_FORCE` forces graphics (PLAIN beats FORCE).

## Worked examples

Card with rounded rect, circle, label:

```sh
printf '\033P>g size 20 6, bg #101028, pen #ff5050, rrectf 10 10 130 50 12, pen #50d0ff, circ 220 35 28, pen #ffffff\ntext 12 90 hello\n\033\\'
```

Translucent overlap (RGB-ish Venn over a dark bg):

```sh
printf '\033P>g size 16 6, bg #202040, pen #ff000080, rectf 10 10 120 60, pen #00ff0080, rectf 60 20 120 60\n\033\\'
```

Chunky retro bitmap text:

```sh
printf '\033P>g size 24 4, bg #101028, pen #50ff90, textmode pixel 2\ntext 8 30 PIXEL TEXT\n\033\\'
```

Quarter arc (east → south) plus a triangle:

```sh
printf '\033P>g size 16 6, bg #14142a, pen #ffd060, thickness 3, arc 100 60 40 0 90, pen #60ffd0, trif 130 20 200 20 165 80\n\033\\'
```

## See also

- [`doc/vector-graphics.md`](doc/vector-graphics.md) — full protocol + the
  `shoescripts/` gallery (`draw-demo.sh`, `welcome.sh`, `shoestring`,
  `shoebling`, `shoelace`, `shoetree`, `memtop.sh`, `shoestat`, `slippers`,
  `shoom`, `shoexp`, `shoemac`).
- `shoescripts/draw-demo.sh` — runnable guided tour of every primitive.
