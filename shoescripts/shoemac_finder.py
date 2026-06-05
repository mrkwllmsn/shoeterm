# shoemac_finder - the "Finder" app module for the shoemac fake-Aqua desktop.
#
# This is the Snow Leopard reskin of shoexp's built-in File Explorer.  It walks
# the *real* filesystem (rooted at $HOME) using the Entry/Pane scan model that
# now lives in shoemac_ui, and dresses it up in Finder chrome: a brushed-metal
# toolbar with back/forward chevrons + the current path, a left source list
# ("FAVORITES" with Desktop / Documents / Downloads / Home), and a white list
# view with a header row and the Aqua-blue selection gradient on the active row.
#
# The module exposes a single make_app() that returns the spec dict the host
# registers (see the SHOEMAC APP CONTRACT in the shoemac main script).  All the
# state (the Pane, the double-click clock) lives on the Win object the host
# hands us; nothing is imported from the main script, so there is no circular
# import.
#
# Everything drawn through cv.text() is plain ASCII: a vector `text` halts at
# the first glyph the font lacks, so labels stay 7-bit and all icons/glyphs are
# built from primitives.

import os
import time

from shoemac_ui import (C, lighten, darken, human, sanitize,  # noqa: F401
                        Entry, Pane)


# --------------------------------------------------------------------------- #
#  favourites (left source list)
# --------------------------------------------------------------------------- #
def _favorites():
    # A few static FAVORITES rows.  They point at the usual $HOME subdirs; a
    # row whose folder doesn't exist falls back to $HOME when clicked (see
    # _go), so the list is always safe.
    home = os.path.expanduser("~")
    return [
        ("Desktop",   os.path.join(home, "Desktop")),
        ("Documents", os.path.join(home, "Documents")),
        ("Downloads", os.path.join(home, "Downloads")),
        ("Home",      home),
    ]


# --------------------------------------------------------------------------- #
#  geometry  (everything the draw + the handlers agree on)
# --------------------------------------------------------------------------- #
def finder_geom(win, d):
    bx, by, bw, bh = win.body_rect()
    tb_h = 30          # brushed-metal toolbar strip
    side_w = 132       # FAVORITES source list
    hdr_h = 18         # "Name / Size" column header
    row_h = 20
    list_x = bx + side_w
    area_y = by + tb_h          # top of sidebar + list area
    area_h = bh - tb_h
    list_w = bw - side_w
    rows_y = area_y + hdr_h     # first file row
    rows_h = area_h - hdr_h
    visible = max(1, rows_h // row_h)
    return (bx, by, bw, bh, tb_h, side_w, hdr_h, row_h,
            list_x, area_y, area_h, list_w, rows_y, rows_h, visible)


def _back_rect(win, d):
    # back chevron button in the toolbar (forward sits just to its right)
    bx, by = win.body_rect()[0], win.body_rect()[1]
    return (bx + 8, by + 6, 22, 18)


def _fwd_rect(win, d):
    x, y, w, h = _back_rect(win, d)
    return (x + w + 4, y, w, h)


def _fav_rects(win, d):
    # hit boxes for the FAVORITES rows, laid out down the sidebar
    g = finder_geom(win, d)
    bx, side_w, area_y = g[0], g[5], g[9]
    y0 = area_y + 24            # below the "FAVORITES" header
    out = []
    for i, (name, path) in enumerate(_favorites()):
        out.append((bx + 6, y0 + i * 22, side_w - 12, 20, name, path))
    return out


# --------------------------------------------------------------------------- #
#  navigation helpers
# --------------------------------------------------------------------------- #
def _go(win, path):
    # navigate the pane to an absolute path in place (used by FAVORITES);
    # falls back to $HOME if the target isn't a readable directory.
    if not os.path.isdir(path):
        path = os.path.expanduser("~")
    win.pane.cwd = os.path.abspath(path)
    win.pane.scan()


def _double(win, idx):
    # self-contained double-click clock (the host doesn't pass one to apps):
    # a second click on the same row within 0.42s counts as a double-click.
    st = win.state
    now = time.monotonic()
    hit = (now - st.get("lct", 0.0) < 0.42 and st.get("lidx") == idx)
    st["lct"] = 0.0 if hit else now
    st["lidx"] = None if hit else idx
    return hit


# --------------------------------------------------------------------------- #
#  little icons (all primitives, ASCII-free)
# --------------------------------------------------------------------------- #
def draw_file_icon(cv, x, cy, e):
    # one ~15px file/folder badge centred vertically on cy (ported from
    # shoexp's draw_file_icon, recoloured against the Aqua palette).
    if e.is_dir:
        cv.pen(C["diredge"]); cv.polyf([x, cy - 5, x + 6, cy - 5,
                                        x + 8, cy - 7, x, cy - 7])
        cv.pen(C["dir"]); cv.rrectf(x, cy - 6, 15, 11, 2)
        cv.pen(lighten(C["dir"], 0.3)); cv.rectf(x + 1, cy - 4, 13, 2)
    elif e.is_exec:
        cv.pen(darken(C["exec"], 0.3)); cv.rrectf(x, cy - 6, 14, 12, 2)
        cv.pen(C["exec"]); cv.trif(x + 4, cy - 3, x + 4, cy + 3, x + 10, cy)
    elif e.is_link:
        cv.pen("#cfd6df"); cv.rrectf(x + 1, cy - 6, 12, 12, 2)
        cv.pen(C["link"]); cv.line(x + 4, cy + 2, x + 10, cy - 3)
    else:
        cv.pen("#cfd6df"); cv.rrectf(x + 1, cy - 6, 12, 12, 2)
        cv.pen(C["white"]); cv.polyf([x + 9, cy - 6, x + 13, cy - 6,
                                      x + 13, cy - 2])
        cv.pen("#9fb0c4")
        for ly in (cy - 2, cy + 1):
            cv.line(x + 3, ly, x + 10, ly)


def _fav_glyph(cv, x, cy, name):
    # tiny sidebar glyph: a house for Home, otherwise a small blue folder.
    if name == "Home":
        cv.pen("#7f8c9c")
        cv.trif(x, cy - 1, x + 6, cy - 6, x + 12, cy - 1)   # roof
        cv.rectf(x + 2, cy - 1, 8, 6)                       # walls
        cv.pen(C["white"]); cv.rectf(x + 5, cy + 1, 2, 4)   # door
    else:
        cv.pen(C["diredge"]); cv.polyf([x, cy - 4, x + 5, cy - 4,
                                        x + 7, cy - 6, x, cy - 6])
        cv.pen(C["dir"]); cv.rrectf(x, cy - 5, 12, 9, 2)


def _chevron(cv, cx, cy, left, col):
    # a < or > arrow drawn with two strokes
    cv.pen(col); cv.thickness(2)
    if left:
        cv.line(cx + 2, cy - 4, cx - 3, cy)
        cv.line(cx - 3, cy, cx + 2, cy + 4)
    else:
        cv.line(cx - 2, cy - 4, cx + 3, cy)
        cv.line(cx + 3, cy, cx - 2, cy + 4)
    cv.thickness(1)


def _finder_face(cv, cx, cy, r):
    # the classic two-tone Finder "face": a square, split light/blue down the
    # middle, with two eyes and a smile.  Drawn within +-r of (cx, cy).
    cv.pen("#2b6fd6"); cv.rrectf(cx - r, cy - r, 2 * r, 2 * r, max(2, r // 3))
    cv.pen("#dbe9ff"); cv.rectf(cx - r + 1, cy - r + 1, r - 1, 2 * r - 2)  # left light half
    # eyes (one on each half)
    cv.pen("#1d3a6b"); cv.circf(cx - r // 2, cy - r // 3, max(1, r // 6))
    cv.pen("#cfe1ff"); cv.circf(cx + r // 2, cy - r // 3, max(1, r // 6))
    # smile across the chin
    cv.pen("#1d3a6b"); cv.thickness(max(1, r // 8))
    cv.arc(cx, cy - r // 4, r * 2 // 3, 20, 160)
    cv.thickness(1)


def icon16(cv, x, y):
    # small Finder face for chrome that wants a 16px tile (x,y top-left)
    _finder_face(cv, x + 8, y + 8, 7)


def icon48(cv, cx, top):
    # ~40px Dock / desktop tile: a glossy blue square with the Finder face
    cv.pen(C["shadow"]); cv.rrectf(cx - 18, top + 4, 38, 38, 8)
    cv.vgrad(cx - 20, top, 40, 40, "#5aa0ff", "#1f5fd0", 10)
    cv.pen("#16498f"); cv.rrect(cx - 20, top, 40, 40, 9)
    cv.pen("#ffffff44"); cv.rrectf(cx - 17, top + 3, 34, 14, 6)  # top sheen
    _finder_face(cv, cx, top + 20, 13)


# --------------------------------------------------------------------------- #
#  lifecycle
# --------------------------------------------------------------------------- #
def fin_init(win):
    # build the browse pane from the launch path (or $HOME) and seed the
    # double-click clock.
    win.pane = Pane(win.open_path or os.path.expanduser("~"))
    win.state.setdefault("lct", 0.0)
    win.state.setdefault("lidx", None)


# --------------------------------------------------------------------------- #
#  draw
# --------------------------------------------------------------------------- #
def fin_draw(cv, d, win):
    g = finder_geom(win, d)
    (bx, by, bw, bh, tb_h, side_w, hdr_h, row_h,
     list_x, area_y, area_h, list_w, rows_y, rows_h, visible) = g
    pane = win.pane
    pane.clamp(visible)
    cw = d.charw
    # track the window title to the current folder
    win.title = os.path.basename(pane.cwd) or "/"

    # ----- body background ------------------------------------------------- #
    cv.pen(C["win"]); cv.rectf(bx, by, bw, bh)

    # ----- toolbar strip --------------------------------------------------- #
    cv.vgrad(bx, by, bw, tb_h, lighten(C["ttl0"], 0.02), C["ttl1"], 6)
    cv.pen(C["ttlsep"]); cv.rectf(bx, by + tb_h - 1, bw, 1)
    # back / forward chevrons in a shared rounded well
    bxr = _back_rect(win, d)
    fxr = _fwd_rect(win, d)
    can_back = os.path.dirname(pane.cwd) != pane.cwd
    cv.pen("#ffffffaa"); cv.rrectf(bxr[0] - 2, bxr[1], bxr[2] * 2 + 8, bxr[3], 8)
    cv.pen(C["sunkenbd"]); cv.rrect(bxr[0] - 2, bxr[1], bxr[2] * 2 + 8, bxr[3], 8)
    _chevron(cv, bxr[0] + bxr[2] // 2, bxr[1] + bxr[3] // 2, True,
             C["ink"] if can_back else "#bcbcbc")
    _chevron(cv, fxr[0] + fxr[2] // 2, fxr[1] + fxr[3] // 2, False, "#bcbcbc")
    # current path, in a sunken pill to the right of the chevrons
    px0 = fxr[0] + fxr[2] + 10
    pw = bx + bw - px0 - 10
    cv.pen(C["sunken"]); cv.rrectf(px0, by + 6, pw, 18, 5)
    cv.pen(C["sunkenbd"]); cv.rrect(px0, by + 6, pw, 18, 5)
    path = pane.cwd
    maxc = max(4, (pw - 10) // cw)
    if len(path) > maxc:
        path = "..." + path[-(maxc - 3):]
    cv.pen(C["ink"]); cv.text(px0 + 6, by + 19, path)

    # ----- sidebar (FAVORITES source list) --------------------------------- #
    cv.pen(C["sidebar"]); cv.rectf(bx, area_y, side_w, area_h)
    cv.pen(C["winframe"]); cv.rectf(bx + side_w - 1, area_y, 1, area_h)
    cv.pen(C["dim"]); cv.text(bx + 12, area_y + 16, "FAVORITES")
    for (x, y, w, h, name, fpath) in _fav_rects(win, d):
        here = os.path.abspath(fpath) == pane.cwd
        if here:
            cv.vgrad(x, y, w, h, C["sel0"], C["sel1"], 4)
            tcol = C["seltxt"]
        else:
            tcol = C["fileink"]
        _fav_glyph(cv, x + 6, y + h // 2, name)
        cv.pen(tcol); cv.text(x + 24, y + h - 6, name)

    # ----- list view ------------------------------------------------------- #
    size_w = 9 * cw
    # column header
    cv.vgrad(list_x, area_y, list_w, hdr_h, "#f7f9fc", "#e6eaf0", 4)
    cv.pen(C["ttlsep"]); cv.rectf(list_x, area_y + hdr_h - 1, list_w, 1)
    cv.pen(C["dim"]); cv.text(list_x + 28, area_y + 13, "Name")
    cv.text(list_x + list_w - size_w - 10, area_y + 13, "Size")
    # rows (white sheet with subtle Finder zebra striping)
    cv.pen(C["white"]); cv.rectf(list_x, rows_y, list_w, rows_h)
    name_x = list_x + 28
    name_max = max(2, (list_w - 28 - 12 - size_w) // cw)
    for r in range(visible):
        idx = pane.top + r
        if idx >= len(pane.entries):
            break
        e = pane.entries[idx]
        ry = rows_y + r * row_h
        if idx == pane.sel:
            cv.vgrad(list_x, ry, list_w, row_h, C["sel0"], C["sel1"], 4)
            tcol = C["seltxt"]; tagcol = C["seltxt"]
        else:
            if r % 2:
                cv.pen("#f4f7fb"); cv.rectf(list_x, ry, list_w, row_h)
            tcol = C["fileink"]; tagcol = C["dim"]
        draw_file_icon(cv, list_x + 8, ry + row_h // 2, e)
        nm = e.name + ("/" if e.is_dir and e.name != ".." else "")
        if len(nm) > name_max:
            nm = nm[:name_max - 1] + "~"
        cv.pen(tcol); cv.text(name_x, ry + row_h - 6, nm)
        # Finder shows "--" in the size column for folders / parent
        tag = "--" if e.is_dir else human(e.size)
        cv.pen(tagcol)
        cv.text(list_x + list_w - len(tag) * cw - 10, ry + row_h - 6, tag)
    # scrollbar
    n = len(pane.entries)
    if n > visible:
        thumb = max(12, rows_h * visible // n)
        tpos = rows_y + (rows_h - thumb) * pane.top // max(1, n - visible)
        cv.pen("#dfe3ea"); cv.rectf(list_x + list_w - 8, rows_y, 8, rows_h)
        cv.pen("#9fb0c4"); cv.rrectf(list_x + list_w - 7, tpos, 6, thumb, 3)


# --------------------------------------------------------------------------- #
#  input handlers
# --------------------------------------------------------------------------- #
def _in(px, py, r):
    x, y, w, h = r
    return x <= px < x + w and y <= py < y + h


def fin_click(win, px, py, d, btn):
    g = finder_geom(win, d)
    (bx, by, bw, bh, tb_h, side_w, hdr_h, row_h,
     list_x, area_y, area_h, list_w, rows_y, rows_h, visible) = g
    pane = win.pane
    # toolbar: back chevron goes up a level (forward is decorative)
    if _in(px, py, _back_rect(win, d)):
        pane.up()
        return True
    if _in(px, py, _fwd_rect(win, d)):
        return True
    # sidebar FAVORITES: jump there in place
    for (x, y, w, h, name, fpath) in _fav_rects(win, d):
        if _in(px, py, (x, y, w, h)):
            _go(win, fpath)
            return True
    # list rows: single click selects, double-click opens
    if (list_x <= px < list_x + list_w and
            rows_y <= py < rows_y + visible * row_h):
        r = (py - rows_y) // row_h
        idx = pane.top + r
        if idx < len(pane.entries):
            pane.sel = idx
            e = pane.entries[idx]
            if _double(win, idx):
                if e.is_dir:
                    if e.name == "..":
                        pane.up()
                    else:
                        pane.enter()
                else:
                    _open_file(e, d)
    return True


def _open_file(e, d):
    # Double-clicking a file: open images in the Preview viewer, ignore the rest
    # (v1 has no other file-type handlers).  is_image() lives in the viewer
    # module so the extension list stays in one place.
    try:
        from shoemac_imgview import is_image
    except ImportError:
        return
    if is_image(e.path):
        d.open_app("imgview", e.path)


def fin_key(win, key, d):
    pane = win.pane
    visible = finder_geom(win, d)[-1]
    if key == "up":
        pane.sel -= 1; pane.clamp(visible); return True
    if key == "down":
        pane.sel += 1; pane.clamp(visible); return True
    if key == "pgup":
        pane.sel -= visible; pane.clamp(visible); return True
    if key == "pgdn":
        pane.sel += visible; pane.clamp(visible); return True
    if key == "home":
        pane.sel = 0; pane.clamp(visible); return True
    if key == "end":
        pane.sel = len(pane.entries) - 1; pane.clamp(visible); return True
    if key == "enter":
        e = pane.cur()
        if e and e.is_dir:
            if e.name == "..":
                pane.up()
            else:
                pane.enter()
        elif e:
            _open_file(e, d)
        return True
    if key in ("back", "left"):
        pane.up(); return True
    if key == "right":
        e = pane.cur()
        if e and e.is_dir and e.name != "..":
            pane.enter()
        return True
    return False


def fin_wheel(win, px, py, up, d):
    pane = win.pane
    visible = finder_geom(win, d)[-1]
    pane.top += -3 if up else 3
    maxtop = max(0, len(pane.entries) - visible)
    pane.top = max(0, min(pane.top, maxtop))
    return True


# --------------------------------------------------------------------------- #
#  registration
# --------------------------------------------------------------------------- #
def make_app():
    return {
        "kind":   "finder",
        "title":  "Finder",
        "size":   (600, 400),
        "init":   fin_init,
        "draw":   fin_draw,
        "click":  fin_click,
        "key":    fin_key,
        "wheel":  fin_wheel,
        "icon16": icon16,
        "icon48": icon48,
        # Finder is on the Dock automatically (DOCK_ITEMS seeds with it); the
        # flag is harmless/idempotent and documents intent.
        "dock":   True,
    }
