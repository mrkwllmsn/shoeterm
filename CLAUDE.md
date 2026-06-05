# CLAUDE.md

Guidance for working in this repo (foot terminal emulator) — plus the vector
graphics feature added on top of upstream.

## Project

**foot** is a fast, lightweight Wayland terminal emulator (C, Meson build).
Rendering is CPU-side via **pixman**, fonts via **fcft**, output to Wayland
**shm** buffers. It's a Wayland-native client (no X).

### Build & test

```sh
./build.sh                       # = meson setup bld/debug && ninja -C bld/debug
ninja -C bld/debug               # incremental build
ninja -C bld/debug test          # run the test suite (tllist, config, graphics)
./bld/debug/foot                 # run the freshly built binary
```

Source files are registered in the top-level `meson.build`. The VT/escape-
sequence code is a static lib `vtlib` (`vt.c`, `csi.c`, `dcs.c`, `osc.c`,
`sixel.c`, `graphics.c`, …); the app links `render.c`, `terminal.c`, etc.

### Key architecture (the parts that matter for graphics)

- **Escape-sequence dispatch:** `vt.c` drives the state machine; CSI in `csi.c`,
  OSC in `osc.c`, **DCS** in `dcs.c` (`dcs_hook`/`dcs_put`/`dcs_unhook`).
  `term->vt.private` holds the DCS private/intermediate byte(s);
  `term->vt.dcs.data`/`.idx`/`.size` accumulate the payload.
- **Sixel / images:** `sixel.c` decodes sixels into a premultiplied ARGB buffer
  staged in `term->sixel.image`, then places it on the grid as a `struct sixel`
  in `term->grid->sixel_images`. `render.c:render_sixel_images()` composites
  that list each frame; scrolling, scaling on font-size change, damage tracking,
  and erase-on-overwrite all operate on the list.
- **Text/glyphs:** `fcft_rasterize_char_utf32(font, cp, subpixel)` returns a
  `struct fcft_glyph` with `->pix` (pixman image), bearings `->x/->y`,
  `->advance.x`, `->is_color_glyph`. Color text = composite a solid-color image
  masked by the glyph (`PIXMAN_OP_OVER, clr, glyph->pix, …`). `term->fonts[0]`
  is the regular font. See `render.c` ~line 1059 for the canonical pattern.

## Vector graphics feature (added here)

Lets a program draw lines/shapes/curves/text in the terminal.
Full reference: **`doc/vector-graphics.md`**, plus
`man 7 foot-ctlseqs` (Vector graphics section) and `man 5 foot.ini` (the
`graphics` tweak).

### Protocol

```
ESC P > g  <commands>  ESC \
```

Commands separated by newlines **or commas** (one command each; the comma lets
a whole drawing fit on one line, e.g. a single `printf`). `#` line comments and
`text` strings ignore commas (they run to end of line). Coordinates are
**pixels** (origin top-left, y down); the **canvas is sized in cells**
(`size <cols> <rows>` → pixel size `cols*cell_width × rows*cell_height`).
Colors are `#rrggbb`, `#rrggbbaa`, or `none`. Commands: `size, bg, pen,
thickness, textmode, clip/noclip, clear, pixel, line, rect/rectf, rrect/rrectf,
circ/circf, arc, tri/trif, poly/polyf, bezier, text`. (`textmode smooth|pixel
[scale]` switches `text` between the fcft font and an embedded 8×16 bitmap font.)

### Design (the important bit)

The feature **reuses the sixel pipeline** rather than adding a new renderer:
the emission tail of `sixel_unhook()` was extracted into
**`sixel_emit_image(term)`** (`sixel.c`). Both sixel and graphics stage a
premultiplied ARGB buffer into `term->sixel.image` (+ `pos`, `transparent_bg`,
`pixman_fmt`) and call it — so a drawn canvas inherits placement, scrolling,
scaling, damage, and erase for free. **No changes to `render.c`.**

### Files

- **`graphics.c`** — `graphics_put` accumulates the DCS body (like
  `xtgettcap_put`); `graphics_unhook` parses + rasterizes + emits in one pass.
  All drawing state (canvas, pen, clip, thickness) is local to `graphics_unhook`.
- **`graphics_draw.h`** — dependency-free software rasterizers (premultiplied
  ARGB, source-over blend, Bresenham line, midpoint circle, barycentric
  triangle, scanline polygon, arc, rounded rect, cubic Bézier). Pure header so
  it can be unit-tested standalone.
- **`dcs.c`** — dispatch `case '>': case 'g':` → `graphics_put`/`graphics_unhook`,
  gated on `term->conf->tweak.graphics`.
- **`config.c` / `config.h`** — `tweak.graphics` (default `yes`).
- **`tests/test-graphics.c`** — pixel-level unit tests of the rasterizers
  (registered in `tests/meson.build`, needs the `math` dep).
- **`doc/vector-graphics.md`**, `doc/foot-ctlseqs.7.scd`, `doc/foot.ini.5.scd`.

### Gotchas (learned the hard way)

- **CRLF:** the tty line discipline turns each `\n` a client prints into
  `\r\n`, so DCS lines arrive with a trailing `\r`. `graphics_unhook` trims one
  trailing CR per line — clients can `printf '...\n'` normally.
- **Control chars in text:** `text` expands `\t` to the next 4-space stop and
  drops other control chars (otherwise fcft draws their "control picture"
  glyph, e.g. the `CR`/`HT` boxes).
- **Non-ASCII in `text` aborts the DCS** (`vt.c` `state_dcs_passthrough_switch`):
  UTF-8 is only decoded from `STATE_GROUND`, never inside a DCS, so a
  continuation byte in `0x80`–`0x9F` is read as a C1 control → `action_unhook`
  ends the sequence and the remaining commands spill onto the screen as literal
  text. Affects both text modes. **Sanitize every interpolated string to
  printable ASCII before drawing** (filenames, container names, `…`→`~`); this
  is why `shoestat`'s `Canvas.text` filters to `0x20`–`0x7E`.
- **Alpha is premultiplied** internally; blending is correct but only *looks*
  obviously translucent over a light/contrasting background (the demo uses an
  RGB Venn over white). Overlapping *fills* of one translucent color can seam.
- **Pixel coords depend on font size:** a script using absolute pixels assumes a
  cell size; the userland scripts assume ~8×16 px and estimate text width with a
  `charw` constant (tune it if text overflows).
- **Comma vs `text`:** commands split on commas *or* newlines, but `text` runs
  to end of **line** (commas in it are literal). So in the one-line/comma form a
  `text` must be the last token on its line — emit a real `\n` after every
  `text` and comma-join the rest (see `slippers`'s `Canvas`).
- **Interactive: mouse is SGR-pixel.** Enable `ESC[?1002h ESC[?1006h ESC[?1016h`;
  reports arrive as `ESC[<btn;Xpx;Ypx M/m` in **pixel** coords that line up 1:1
  with a canvas drawn at `ESC[H`, so clicks map straight onto drawn rectangles
  (no cell math). Wheel = btn 64/65; modifiers add +4/+8/+16, motion +32.

## Userland scripts (`shoescripts/`)

All live in `shoescripts/` and are runnable inside the built foot; the `*-demo`
ones print the commands / input they send so usage is self-documenting.
(`install_local_shoe.sh` installs the build + the shoe tools to
`/usr/local/bin`.)

- **`draw-demo.sh`** — guided tour of every primitive (shows each command block
  then draws it). `./bld/debug/foot sh shoescripts/draw-demo.sh`
- **`welcome.sh`** — a polished gradient header banner (good shell-startup
  banner). Fixed-size card on a transparent canvas (font-size independent).
- **`shoestring`** — `echo "text" | shoestring` → randomly-themed gradient
  banner. First stdin line = title, rest = subtitle.
- **`shoebling`** — `echo "text" | shoebling` → ornate **vintage frame** around
  the text (corner scrollwork, double keyline, filigree dividers). 1–3 stdin
  lines = title / kicker / footer. `SHOEBLING_INVERT=1` for a dark panel; all
  drawing is bezier/arc/poly scrollwork built in awk (no gradient).
- **`shoelace`** — `… | shoelace bar|line|pie "Title"` → chart from CSV or JSON
  (object map / array-of-objects / `[label,value]` pairs / bare numbers; the
  JSON parser is pure awk). `TH` is the title-band height (kept large so the
  title clears the top axis label).
- **`chart-demo.sh`** — shoelace demo: shows the input + command for each chart.
- **`shoetree`** — `… | shoetree "Title"` → a themed table drawn at the cursor
  from whitespace/CSV/TSV/JSON (Python, stdlib only; the richer successor to the
  shell/awk `shoetable`). Header-driven whitespace split keeps the last column's
  spaces (`ps aux`'s `COMMAND`), numeric columns right-align. **Tree mode** (auto;
  `SHOETREE_TREE=0|1`) nests rows into a forest from `PID`+`PPID` columns *or*
  from `ps axf`-style indentation, drawing connector elbows/guides. Cell size via
  `ESC[16t` over **`/dev/tty`** (stdin is the data pipe). Plain unicode-box
  fallback (ASCII `|--`/`` `-- `` tree connectors). `SHOETREE_THEME=0..8`,
  `SHOETREE_PLAIN`/`_FORCE`; `SHOETREE_SELFTEST=1` renders one headless frame.
- **`memtop.sh`** — live memory dashboard (half-ring `% used` gauge, stacked
  RAM/swap bars, history area graph) redrawn in place from `/proc/meminfo`.
  `memtop.sh [interval]` for live mode, `memtop.sh once` for a single frame at
  the cursor (banner-friendly). Queries cell size via `ESC[16t` so the card is
  font-size independent.
- **`shoestat`** — a full-window **system-status dashboard** (Python, stdlib
  only): a header band (host/OS/clock/uptime), a CPU-load **half-ring gauge**
  (`arc`, colored green/amber/red by load÷cores) with 1m/5m/15m mini-bars,
  RAM/swap/disk **progress bars**, and a **Docker** panel (two-column container
  list with status dots, muted `image:tag`, right-aligned uptime — from `docker
  info`/`docker ps`, omitted when docker is absent). `shoestat` for one frame at
  the cursor, `shoestat live [N]` to redraw in place. Sizes the canvas to the
  window via `TIOCGWINSZ` (`os.get_terminal_size`, more reliable here than
  `ESC[18t`) + cell size via `ESC[16t`. `graphics_ok()` fallback to a plain
  ASCII table; `SHOESTAT_PLAIN`/`_FORCE`. **All `text` is ASCII-sanitized** in
  `Canvas.text` (truncation marker `~`) — see the non-ASCII DCS-abort gotcha.
- **`slippers`** — dual-pane Midnight-Commander-style file explorer. The
  first **interactive** shoescript and the first in **Python** (stdlib only):
  redraws a full-screen frame in place, keyboard + **mouse** (SGR-pixel) nav,
  clickable F-key bar, alt-screen with clean teardown. v1 is navigate + view
  (copy/move/mkdir/delete are confirm-only stubs). `slippers [start-dir]`;
  `SLIPPERS_FORCE`/`_PLAIN` like the others.
- **`shoom`** — a DOOM-style first-person shooter and the first **real-time
  game** shoescript (Python, stdlib only). A software **raycaster**: each screen
  column casts one ray into a grid map and draws one distance-shaded vertical
  `rectf`, so the 3D view is a row of filled rects redrawn over itself each
  frame (z-buffer in a list; imps are billboard sprites depth-tested against
  it). WASD + mouse-look (`ESC[?1003h` motion reporting), space/click to shoot;
  minimap + status bar; health/ammo pickups. `SHOOM_FORCE`/`_PLAIN`;
  `SHOOM_SELFTEST=1` renders one frame headless (no GUI) for a smoke check. v1
  is one hand-built level + contact-damage imps + one weapon (no enemy
  projectiles / doors / texture-mapped walls yet).
- **`shoexp`** — a (lovingly fake) **Windows XP desktop**, mouse-driven. The
  "Bliss" wallpaper (sky gradient + bezier/polyf hill + cloud blobs), a
  Luna-blue taskbar with a green Start button + live tray clock, a Start menu,
  desktop icons, and a tiny **window manager**: draggable windows with XP title
  bars (`_`/`X` controls), click-to-focus z-order, taskbar buttons. Apps:
  a working **Calculator** (clickable grid + arithmetic state machine), **My
  Computer** (drive rows with *real* `shutil.disk_usage` bars; double-click C:
  opens the explorer), a **File Explorer** that browses the **real filesystem**
  (ports slippers' `Entry`/`Pane` scan model, rooted at `$HOME`), and an empty
  **Recycle Bin**. Four more apps live in their own modules and register through
  a tiny app registry (`make_app()` → spec dict; see below): **Minesweeper**
  (real 9×9/10-mine game, left-reveal/right-flag/flood-fill, smiley reset),
  **Notepad** (a plain-text editor that captures the keyboard — the first app to
  take key focus), **Paint** (drag-to-draw pencil/line/rect/ellipse/eraser +
  palette, via a drag-aware `mouse` press/drag/release handler), and a fake
  **Internet Explorer** (IE6 chrome + canned clickable pages, blue "e" drawn
  from primitives). Same interactive scaffolding as slippers (Canvas DCS buffer,
  raw-mode `Term`, SGR-pixel mouse, alt-screen teardown). `SHOEXP_FORCE`/
  `_PLAIN`; `SHOEXP_SELFTEST=1` renders one headless frame for a smoke check.
  v1: windows aren't resizable/maximizable and the Recycle Bin is decorative.
  - **Structure:** shared drawing primitives (`Canvas`, the `C` palette,
    `mix/lighten/darken`, `human`) live in **`shoexp_ui.py`**, imported by both
    `shoexp` and each app module. Built-in apps (calc/mycomputer/explorer/
    recycle) are still dispatched inline; the extra apps live in
    **`shoexp_<name>.py`** and register via `register_app(make_app())` in
    `_load_apps()`. A spec dict supplies `kind/title/size/draw/icon16` plus
    optional `init/click/mouse/key/wheel/icon48/desktop/start`; the registry
    (`APP_DRAW`, `APP_CLICK`, `APP_MOUSE`, `APP_KEY`, …) routes draw, clicks
    (left **and** right via `btn`), drag (`mouse` press/drag/release), keys and
    wheel. `install_local_shoe.sh` copies the modules next to `shoexp` on PATH.

- **`shoemac`** — a (lovingly fake) **Mac OS X Snow Leopard (10.6 / Aqua)
  desktop**, the cousin of `shoexp`. An **Aurora** wallpaper (indigo→violet
  gradient + faint stars + soft translucent aurora ribbons), a translucent
  **global menu bar** across the top (Apple logo drawn from primitives + app
  menus + live clock + a Spotlight magnifier), and a glossy **Dock** pinned to
  the bottom with proper **magnification** on hover (`?1003h` motion tracking).
  The window manager draws brushed-aluminium windows with **traffic-light**
  controls (close/minimise/zoom) and click-to-focus z-order. Apps:
  **Finder** (ports slippers'/shoexp's `Entry`/`Pane` real-filesystem browser
  with a FAVORITES sidebar + brushed-metal toolbar; double-click to enter,
  in-place nav), a working **Calculator** (graphite reskin of shoexp's calc),
  **About This Mac** (real CPU/RAM via /proc + `shutil.disk_usage` Startup Disk
  bar), a fake **Safari** (canned clickable pages, compass logo from
  primitives), and a **Terminal** (the first key-capturing shoemac app, like
  shoexp's Notepad): a translucent charcoal Terminal.app that runs a small set of
  *real* commands against the live filesystem — `ls`/`pwd`/`cd`/`cat`/`echo`/
  `date`/`whoami`/`uname`/`clear`/`help` — with a coloured prompt, `ls -F`-style
  colour-coded columns, and up/down command history. Reuses shoexp's interactive
  scaffolding (Canvas DCS buffer,
  raw-mode `Term`, SGR-pixel mouse, alt-screen teardown). `SHOEMAC_FORCE`/
  `_PLAIN`; `SHOEMAC_SELFTEST=1` renders one headless frame for a smoke check.
  - **Structure:** shared primitives (`Canvas`, the `C` Aqua palette,
    `mix/lighten/darken`, `human`, and `Entry`/`Pane` for Finder) live in
    **`shoemac_ui.py`**, imported by both `shoemac` and each app module. Every
    app lives in its own **`shoemac_<name>.py`** and registers via
    `register_app(make_app())` in `_load_apps()`; the only built-in window is
    the decorative Trash. A spec dict supplies `kind/title/size/draw` plus
    optional `init/click/mouse/key/wheel/icon16/icon48/dock/desktop`; the
    registry routes draw, clicks (left **and** right via `btn`), drag, keys and
    wheel — same contract as shoexp. `install_local_shoe.sh` copies the modules
    next to `shoemac` on PATH. v1: windows aren't resizable/maximizable, zoom
    light + Trash are decorative, Safari's pages are canned, and the Terminal's
    command set is the fixed list above (no pipes/globs/external programs).

### Graphics-or-plain detection (shoestring / shoelace / shoebling / slippers)

All emit graphics only to a graphics-capable terminal, else fall back to plain
text (so they're safe when piped to a file or run elsewhere). `graphics_ok()`:
`SHOE*_PLAIN` → plain; `SHOE*_FORCE` → graphics; else stdout must be a tty
**and** `$TERM` foot-like. PLAIN beats FORCE. Theme override:
`SHOESTRING_THEME`/`SHOELACE_THEME=0..6` (0 Aurora .. 6 Slate),
`SHOEBLING_THEME=0..5` (0 Sepia .. 5 Slate; `SHOEBLING_INVERT=1` flips to dark).

## This environment

- Compositor is **mutter** (GNOME). `grim` fails (no `wlr-screencopy`); use
  **`gnome-screenshot -f out.png`** to capture (D-Bus screenshot API is
  access-denied). The desktop may have a live session — avoid stealing focus.
- The user's `~/.config/foot` includes the `srcery` theme with old `[colors]`
  sections → a flood of harmless `deprecated` warnings on startup. `--config`
  / `XDG_CONFIG_HOME` did not reliably suppress them here.
- A foot launched in the background dies with SIGHUP if you `pkill`/churn other
  processes across tool calls — launch once and don't kill it mid-verify.
- Deterministic visual checks without the GUI: compile a tiny C harness that
  `#include`s `graphics_draw.h`, render to a PPM, `convert` to PNG, and view.
  (This is how the rasterizers and layouts were verified.)

## IMPORTANT NOTE
do not cd into directories when you don't need to. don't do this:
    cd /tmp; convert shoemac_shot.png -crop 1700x1150+150+430 +repage shoemac_crop.png && identify shoemac_crop.png

use paths and do it something like this instead
    convert /tmp/shoemac_shot.png -crop 1700x1150+150+430 +repage /tmp/shoemac_crop.png && identify /tmp/shoemac_crop.png
This is important because it imeans you don't get stuck at prompting me for permission so much

