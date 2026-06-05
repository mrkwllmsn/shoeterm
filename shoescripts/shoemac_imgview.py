# shoemac_imgview - a Preview-style photo viewer for the shoemac fake-Aqua desktop.
#
# This is the first shoemac app to put a *real* photo on screen.  The desktop is
# one full-screen vector-graphics DCS image re-emitted at ESC[H each frame, and
# the vector protocol has no "blit an image" command -- only primitives.  So the
# photo is shown as a genuine **sixel** image overlaid on top of the vector
# frame: img2sixel decodes the file once (scaled to fit the window's "photo
# well"), and the host's render loop re-blits the cached sixel bytes after the
# vector frame, positioned at the well.  Because both are grid images, the vector
# frame draws first and the sixel composites over it; the next frame's
# full-screen vector image at ESC[H overwrites those cells and erases the old
# photo (the same erase-on-overwrite every sixel relies on), then we re-place it.
#
# Two consequences worth knowing (v1):
#   * Sixel placement is cell-granular (~cw x ch px), so the photo snaps to the
#     cell grid; we draw a dark matte "well" generously and centre the photo in
#     it so the snap slop hides inside the matte.
#   * A sixel always composites above the vector image regardless of window
#     z-order, so the host only blits the photo when this window is topmost
#     (d.top_win()); occluded, the well shows empty rather than bleeding the
#     photo over whatever is on top.  See _overlay_blit() / the host render loop.
#
# All cv.text() is plain ASCII (a vector `text` aborts the DCS at the first
# non-ASCII byte); filenames are sanitised before drawing.

import os
import re
import subprocess

from shoemac_ui import C, mix, lighten, darken, human, sanitize  # noqa: F401

# Default window size -- a comfortable Preview-ish frame; the well fills it.
WIN_W, WIN_H = 560, 460

# Margins inside the window body, in px.
MATTE = 12           # gap between the body edge and the photo well
INFO_H = 26          # bottom strip for the filename + dimensions

# Extensions img2sixel / the foot sixel decoder handle here.  Used by Finder to
# decide whether a double-clicked file opens in the viewer.
IMAGE_EXTS = (
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ppm", ".pgm", ".pnm",
    ".tga", ".webp", ".tiff", ".tif",
)


def is_image(path):
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


def make_app():
    return {
        "kind":   "imgview",
        "title":  "Preview",
        "size":   (WIN_W, WIN_H),
        "init":   iv_init,
        "draw":   iv_draw,
        "overlay": iv_overlay,
        "icon16": icon16,
        "icon48": icon48,
        # Not on the Dock by default -- it is launched from Finder by opening an
        # image.  (Set "dock": True here if you want a permanent tile.)
    }


# --------------------------------------------------------------------------- #
#  state / decode
# --------------------------------------------------------------------------- #
def iv_init(win):
    # init() does not receive the desktop, so we don't yet know the real cell
    # size -- decoding is deferred to the first draw() (which has `d`).  Here we
    # just record the path and set the title to the basename.
    path = win.open_path
    win.state = {
        "path":   path,
        "sixel":  None,     # cached sixel bytes once decoded
        "imgw":   0,        # produced photo size in px (parsed from the sixel)
        "imgh":   0,
        "err":    None,     # human-readable error if decode failed / no file
        "tried":  False,    # decode attempted (so we don't retry a failure)
    }
    if path:
        win.title = os.path.basename(path) or "Preview"
    else:
        win.title = "Preview"
        win.state["err"] = "No image"


def _well_rect(win):
    # The dark matte well the photo sits in, in canvas px (above the info strip).
    bx, by, bw, bh = win.body_rect()
    wx = bx + MATTE
    wy = by + MATTE
    ww = max(8, bw - 2 * MATTE)
    wh = max(8, bh - 2 * MATTE - INFO_H)
    return wx, wy, ww, wh


def _decode(win, d):
    # Run img2sixel once, scaled to fit the well, and cache the bytes + the
    # produced pixel size (parsed from the sixel raster-attributes header
    # `ESC P q " a ; b ; W ; H`).  Failures are recorded, not retried.
    win.state["tried"] = True
    path = win.state["path"]
    if not path:
        win.state["err"] = "No image"
        return
    if not os.path.isfile(path):
        win.state["err"] = "File not found"
        return
    _wx, _wy, ww, wh = _well_rect(win)
    try:
        out = subprocess.run(
            ["img2sixel", "-w", str(int(ww)), "-h", str(int(wh)), path],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=15,
        )
    except FileNotFoundError:
        win.state["err"] = "img2sixel not installed"
        return
    except subprocess.SubprocessError:
        win.state["err"] = "Could not decode image"
        return
    data = out.stdout
    if out.returncode != 0 or not data:
        win.state["err"] = "Could not decode image"
        return
    m = re.search(rb'"\d+;\d+;(\d+);(\d+)', data)
    if m:
        win.state["imgw"] = int(m.group(1))
        win.state["imgh"] = int(m.group(2))
    else:
        # No raster attributes -> assume it filled the well.
        win.state["imgw"], win.state["imgh"] = int(ww), int(wh)
    win.state["sixel"] = data
    win.state["err"] = None


# --------------------------------------------------------------------------- #
#  placement: where the cached photo lands, in canvas px and in cells
# --------------------------------------------------------------------------- #
def photo_geom(win, d):
    """Return (px, py, iw, ih, col, row) for the decoded photo: px/py are the
    cell-snapped top-left in canvas pixels, iw/ih its size, col/row the 1-based
    cell coordinates to position the cursor for the sixel blit.  Returns None if
    there is nothing to show."""
    if not win.state.get("sixel"):
        return None
    wx, wy, ww, wh = _well_rect(win)
    iw = win.state["imgw"] or ww
    ih = win.state["imgh"] or wh
    # centre within the well, then snap the origin to the cell grid so the sixel
    # (which lands at a cell boundary) matches the px rect we draw the frame at.
    cw = max(1, d.charw)
    ch = max(1, getattr(d, "ch", 16))
    cx = wx + (ww - iw) // 2
    cy = wy + (wh - ih) // 2
    col = max(0, int(round(cx / cw)))
    row = max(0, int(round(cy / ch)))
    px = col * cw
    py = row * ch
    return px, py, iw, ih, col + 1, row + 1


# --------------------------------------------------------------------------- #
#  draw (vector layer) -- chrome, matte well, info strip; the photo is the
#  sixel overlaid by the host afterwards (see _overlay_blit in the main script).
# --------------------------------------------------------------------------- #
def iv_draw(cv, d, win):
    bx, by, bw, bh = win.body_rect()
    # neutral light body so any letterboxing around the well reads as chrome
    cv.pen("#e9e9ec"); cv.rectf(bx, by, bw, bh)

    # decode lazily on first draw (we now know the real cell size via d)
    if not win.state["tried"]:
        _decode(win, d)

    wx, wy, ww, wh = _well_rect(win)
    # the photo well: a recessed dark matte with a soft inner edge
    cv.pen("#1b1b1f"); cv.rrectf(wx, wy, ww, wh, 6)
    cv.pen("#000000"); cv.rrect(wx, wy, ww, wh, 6)

    geom = photo_geom(win, d)
    if geom is not None:
        px, py, iw, ih, _col, _row = geom
        # a 1px frame exactly around where the sixel will land, so even before
        # the overlay paints (or when occluded) the photo's footprint reads.
        cv.pen("#3a3a40")
        cv.rect(px - 1, py - 1, iw + 2, ih + 2)
    elif win.state.get("err"):
        # centred error message in the well
        msg = sanitize(win.state["err"])
        cv.pen("#c8c8cc")
        cv.text(wx + ww // 2 - len(msg) * d.charw // 2,
                wy + wh // 2 + 5, msg)

    # ----- info strip -------------------------------------------------------- #
    iy = by + bh - INFO_H
    cv.vgrad(bx, iy, bw, INFO_H, "#f4f4f6", "#e2e2e6", 6)
    cv.pen(C["ttlsep"]); cv.rectf(bx, iy, bw, 1)
    name = sanitize(os.path.basename(win.state["path"] or "")) or "(no file)"
    cv.pen(C["ink"]); cv.text(bx + 12, iy + INFO_H - 8, name)
    # right-aligned dimensions + file size
    dims = ""
    if win.state["imgw"] and win.state["imgh"]:
        dims = "%d x %d" % (win.state["imgw"], win.state["imgh"])
    sz = ""
    try:
        if win.state["path"] and os.path.isfile(win.state["path"]):
            sz = human(os.path.getsize(win.state["path"]))
    except OSError:
        sz = ""
    meta = "   ".join(s for s in (dims, sz) if s)
    if meta:
        cv.pen(C["dim"])
        cv.text(bx + bw - 12 - len(meta) * d.charw, iy + INFO_H - 8, meta)


# --------------------------------------------------------------------------- #
#  overlay -- what the host blits on top of the vector frame (a real sixel).
#  The host calls this only for the topmost window (sixels ignore z-order), and
#  re-blits every frame; we return the cached bytes + cell position, or None.
# --------------------------------------------------------------------------- #
def iv_overlay(win, d):
    geom = photo_geom(win, d)
    if geom is None:
        return None
    _px, _py, _iw, _ih, col, row = geom
    return (col, row, win.state["sixel"])


# --------------------------------------------------------------------------- #
#  icons -- a tiny framed "photo": sky + hill + sun, like a Preview thumbnail
# --------------------------------------------------------------------------- #
def _photo_tile(cv, x, y, s):
    r = max(2, s // 8)
    # white mat + frame
    cv.vgrad(x, y, s, s, "#fdfdfd", "#e6e6e6", 5)
    cv.pen("#9a9a9a"); cv.rrect(x, y, s, s, r)
    # inset picture
    m = max(1, s // 8)
    ix, iy, iw, ih = x + m, y + m, s - 2 * m, s - 2 * m
    cv.pen("#2f6fb0"); cv.rectf(ix, iy, iw, ih)               # sky
    cv.pen("#bfe0f5"); cv.rectf(ix, iy, iw, max(1, ih // 2))  # lighter upper sky
    cv.pen("#ffd34d")                                         # sun
    cv.circf(ix + iw - max(2, iw // 4), iy + max(2, ih // 4), max(1, s // 10))
    cv.pen("#2f7d3a")                                         # hill
    cv.trif(ix, iy + ih, ix + iw // 2, iy + ih // 2, ix + iw, iy + ih)


def icon16(cv, x, y):
    _photo_tile(cv, x, y, 16)


def icon48(cv, cx, top):
    s = 40
    _photo_tile(cv, cx - s // 2, top, s)
