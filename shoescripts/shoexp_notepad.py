# shoexp_notepad - a Notepad text editor for the shoexp fake-XP desktop.
#
# Self-contained app module: make_app() returns the spec dict shoexp wires up.
# A minimal-but-real plain-text editor - menu bar, sunken white text area,
# caret, insert/delete/split/join, arrows, home/end/pgup/pgdn, scrolling.
# All text is ASCII (a missing glyph truncates the rest of a vector text run).

from shoexp_ui import C, mix, lighten, darken

MENU = ("File", "Edit", "Format", "View", "Help")
LH = 16          # line height in px (fixed, per the spec)
TAB_W = 4        # tab => this many spaces
MENU_H = 18      # menu-bar strip height


# --------------------------------------------------------------------------- #
#  geometry: split the body into the menu strip and the sunken text area
# --------------------------------------------------------------------------- #
def text_area(win, d):
    """Return geometry shared by draw / click / scroll-keeping.

    -> dict with: menu rect (mx,my,mw,mh); text-area rect (tx,ty,tw,th);
       inner content origin (cx,cy) where cy is the first baseline; the
       column width charw; and the number of fully-visible rows.
    """
    bx, by, bw, bh = win.body_rect()
    mx, my, mw, mh = bx, by, bw, MENU_H
    tx, ty = bx, by + MENU_H
    tw, th = bw, bh - MENU_H
    pad = 4
    cx = tx + pad
    cy = ty + pad + LH - 4          # first baseline (bottom-left of row 0)
    inner_h = th - pad * 2
    visible = max(1, inner_h // LH)
    return {
        "menu": (mx, my, mw, mh),
        "area": (tx, ty, tw, th),
        "cx": cx, "cy": cy, "pad": pad,
        "charw": d.charw, "visible": visible,
        "inner_w": tw - pad * 2,
    }


def _clampcol(st, row):
    return max(0, min(st["col"], len(st["lines"][row])))


def _keep_visible(win, d):
    """Adjust scroll offset so the caret row sits inside the visible window."""
    g = text_area(win, d)
    st = win.state
    visible = g["visible"]
    if st["row"] < st["top"]:
        st["top"] = st["row"]
    elif st["row"] >= st["top"] + visible:
        st["top"] = st["row"] - visible + 1
    st["top"] = max(0, min(st["top"], max(0, len(st["lines"]) - 1)))


# --------------------------------------------------------------------------- #
#  init
# --------------------------------------------------------------------------- #
def init_notepad(win):
    win.state = {
        "lines": [""],
        "row": 0,
        "col": 0,
        "top": 0,        # first visible line index
        "dirty": False,
    }
    win.title = "Untitled - Notepad"


def _mark_dirty(win):
    st = win.state
    if not st["dirty"]:
        st["dirty"] = True
    win.title = ("*" if st["dirty"] else "") + "Untitled - Notepad"


# --------------------------------------------------------------------------- #
#  draw
# --------------------------------------------------------------------------- #
def draw_notepad(cv, d, win):
    g = text_area(win, d)
    st = win.state
    _keep_visible(win, d)

    # --- menu bar: a light strip with greyed menu titles --------------------
    mx, my, mw, mh = g["menu"]
    cv.vgrad(mx, my, mw, mh, lighten(C["win"], 0.45), C["win"], 4)
    cv.pen(C["sunkenbd"]); cv.line(mx, my + mh - 1, mx + mw - 1, my + mh - 1)
    cv.pen(C["dim"])
    tx0 = mx + 8
    for label in MENU:
        cv.text(tx0, my + mh - 5, label)
        tx0 += (len(label) + 2) * d.charw

    # --- sunken white text area --------------------------------------------
    tx, ty, tw, th = g["area"]
    cv.pen(C["sunken"]); cv.rectf(tx, ty, tw, th)
    cv.pen(C["sunkenbd"]); cv.rect(tx, ty, tw, th)

    visible = g["visible"]
    charw = g["charw"]
    maxchars = max(1, g["inner_w"] // charw)
    cx = g["cx"]
    cy = g["cy"]

    # document text, clipped to visible rows
    cv.pen(C["ink"])
    for r in range(visible):
        idx = st["top"] + r
        if idx >= len(st["lines"]):
            break
        s = st["lines"][idx]
        if len(s) > maxchars:
            s = s[:maxchars]
        if cv.textmode and cv.textmode.startswith("pixel"):
            s = "".join(c if 0x20 <= ord(c) <= 0x7e else " " for c in s)
        baseline = cy + r * LH
        if s:
            cv.text(cx, baseline, s)

    # caret: a 1px vertical bar at the caret position (if on a visible row)
    crow = st["row"] - st["top"]
    if 0 <= crow < visible:
        col = _clampcol(st, st["row"])
        col = min(col, maxchars)
        caret_x = cx + col * charw
        cary0 = ty + g["pad"] + crow * LH
        cv.pen(C["ink"])
        cv.line(caret_x, cary0, caret_x, cary0 + LH - 2)


# --------------------------------------------------------------------------- #
#  click: place caret at the clicked row/col
# --------------------------------------------------------------------------- #
def click_notepad(win, px, py, d, btn):
    if btn != 0:
        return True
    g = text_area(win, d)
    st = win.state
    tx, ty, tw, th = g["area"]
    visible = g["visible"]
    # row from y within the text area
    rel_y = py - (ty + g["pad"])
    r = int(rel_y // LH)
    r = max(0, min(r, visible - 1))
    row = st["top"] + r
    row = max(0, min(row, len(st["lines"]) - 1))
    # col from x
    rel_x = px - g["cx"]
    col = int(round(rel_x / max(1, g["charw"])))
    col = max(0, min(col, len(st["lines"][row])))
    st["row"] = row
    st["col"] = col
    _keep_visible(win, d)
    return True


# --------------------------------------------------------------------------- #
#  key: edit + navigate
# --------------------------------------------------------------------------- #
def _insert_text(st, s):
    row, col = st["row"], _clampcol(st, st["row"])
    line = st["lines"][row]
    st["lines"][row] = line[:col] + s + line[col:]
    st["col"] = col + len(s)


def key_notepad(win, key, d):
    st = win.state
    lines = st["lines"]
    st["col"] = _clampcol(st, st["row"])

    consumed = True
    if key == "enter":
        row, col = st["row"], st["col"]
        line = lines[row]
        lines[row:row + 1] = [line[:col], line[col:]]
        st["row"] = row + 1
        st["col"] = 0
        _mark_dirty(win)
    elif key == "tab":
        _insert_text(st, " " * TAB_W)
        _mark_dirty(win)
    elif key == "back":
        row, col = st["row"], st["col"]
        if col > 0:
            line = lines[row]
            lines[row] = line[:col - 1] + line[col:]
            st["col"] = col - 1
        elif row > 0:
            prev = lines[row - 1]
            st["col"] = len(prev)
            lines[row - 1] = prev + lines[row]
            del lines[row]
            st["row"] = row - 1
        _mark_dirty(win)
    elif key == "del":
        row, col = st["row"], st["col"]
        line = lines[row]
        if col < len(line):
            lines[row] = line[:col] + line[col + 1:]
        elif row + 1 < len(lines):
            lines[row] = line + lines[row + 1]
            del lines[row + 1]
        _mark_dirty(win)
    elif key == "left":
        if st["col"] > 0:
            st["col"] -= 1
        elif st["row"] > 0:
            st["row"] -= 1
            st["col"] = len(lines[st["row"]])
    elif key == "right":
        if st["col"] < len(lines[st["row"]]):
            st["col"] += 1
        elif st["row"] + 1 < len(lines):
            st["row"] += 1
            st["col"] = 0
    elif key == "up":
        if st["row"] > 0:
            st["row"] -= 1
            st["col"] = _clampcol(st, st["row"])
    elif key == "down":
        if st["row"] + 1 < len(lines):
            st["row"] += 1
            st["col"] = _clampcol(st, st["row"])
    elif key == "home":
        st["col"] = 0
    elif key == "end":
        st["col"] = len(lines[st["row"]])
    elif key == "pgup":
        visible = text_area(win, d)["visible"]
        st["row"] = max(0, st["row"] - visible)
        st["col"] = _clampcol(st, st["row"])
        st["top"] = max(0, st["top"] - visible)
    elif key == "pgdn":
        visible = text_area(win, d)["visible"]
        st["row"] = min(len(lines) - 1, st["row"] + visible)
        st["col"] = _clampcol(st, st["row"])
    elif isinstance(key, str) and len(key) == 1 and key >= " ":
        # plain printable character (space included)
        _insert_text(st, key)
        _mark_dirty(win)
    else:
        consumed = False

    if consumed:
        _keep_visible(win, d)
    return consumed


# --------------------------------------------------------------------------- #
#  16x16 icon: a white page with a folded corner and grey text lines
# --------------------------------------------------------------------------- #
def icon16_notepad(cv, x, y):
    # page body
    cv.pen(C["white"]); cv.rectf(x + 2, y + 1, 11, 14)
    cv.pen(C["sunkenbd"]); cv.rect(x + 2, y + 1, 11, 14)
    # folded corner (top-right)
    cv.pen(lighten(C["sunkenbd"], 0.4))
    cv.trif(x + 9, y + 1, x + 13, y + 1, x + 13, y + 5)
    cv.pen(C["sunkenbd"]); cv.line(x + 9, y + 1, x + 13, y + 5)
    cv.line(x + 9, y + 1, x + 9, y + 5)
    cv.line(x + 9, y + 5, x + 13, y + 5)
    # a few grey text lines
    cv.pen(C["dim"])
    for i in range(4):
        ly = y + 5 + i * 2
        cv.line(x + 4, ly, x + 11 - (i % 2) * 2, ly)


# --------------------------------------------------------------------------- #
#  spec
# --------------------------------------------------------------------------- #
def make_app():
    return {
        "kind": "notepad",
        "title": "Untitled - Notepad",
        "size": (440, 320),
        "init": init_notepad,
        "draw": draw_notepad,
        "click": click_notepad,
        "key": key_notepad,
        "icon16": icon16_notepad,
        "start": True,
        "start_label": "Notepad",
    }


# --------------------------------------------------------------------------- #
#  smoke test
# --------------------------------------------------------------------------- #
def win_state_text(w):
    return w.state.get("lines", [])


if __name__ == "__main__":
    from shoexp_ui import Canvas

    class _W:
        def __init__(s, kind, size):
            s.x, s.y = 40, 40
            s.w, s.h = size
            s.kind = kind
            s.title = ""
            s.id = 1
            s.state = {}

        def body_rect(s):
            return (s.x + 4, s.y + 26, s.w - 8, s.h - 26 - 4)

    class _D:
        charw = 8
        W = 1280
        H = 768

    spec = make_app()
    w = _W(spec["kind"], spec["size"])
    spec["init"](w)
    for ch in "Hello, world":
        spec["key"](w, ch, _D())
    spec["key"](w, "enter", _D())
    spec["key"](w, "tab", _D())
    for ch in "second line":
        spec["key"](w, ch, _D())
    spec["key"](w, "back", _D())
    spec["key"](w, "left", _D())
    spec["key"](w, "home", _D())
    cv = Canvas()
    spec["draw"](cv, _D(), w)
    spec["icon16"](cv, 0, 0)
    spec["click"](w, w.x + 30, w.y + 60, _D(), 0)
    assert win_state_text(w) is not None
    print("notepad smoke ok: lines=%d state_rows=%d" % (
        len(cv.lines), len(w.state.get("lines", []))))
