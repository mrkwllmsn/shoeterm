# shoexp_paint - a simplified MS Paint app for the shoexp fake-XP desktop.
#
# Self-contained module: exposes make_app() returning the shoexp app spec.
# Uses the drag-aware "mouse" hook (press/drag/release) so left-dragging in the
# body draws freehand strokes; the title bar still drags the window.
#
# Layout inside the body (all geometry lives in paint_geom(), shared by draw and
# mouse so hit-tests mirror the drawn rects):
#   - a left tool box column  (Pencil/Brush, Line, Rect, Ellipse, Eraser)
#   - a bottom colour palette  (16 swatches, current colour shown)
#   - the main sunken white drawing canvas filling the rest

from shoexp_ui import C, mix, lighten, darken

# --------------------------------------------------------------------------- #
#  tools + palette
# --------------------------------------------------------------------------- #
TOOLS = [
    # (key, label)  -- label is a tiny ASCII glyph drawn in the button
    ("pencil",  "Pn"),
    ("brush",   "Br"),
    ("line",    "Ln"),
    ("rect",    "Rc"),
    ("ellipse", "El"),
    ("eraser",  "Er"),
]

PALETTE = [
    "#000000", "#7f7f7f", "#7f0000", "#7f7f00",
    "#007f00", "#007f7f", "#00007f", "#7f007f",
    "#ffffff", "#c0c0c0", "#ff0000", "#ffff00",
    "#00ff00", "#00ffff", "#0000ff", "#ff00ff",
]

# geometry constants
TBW = 40          # tool box column width
TBTN = 30         # tool button height
PALH = 22         # palette strip height (single row of swatches)
SW = 16           # swatch size
PAD = 6


# --------------------------------------------------------------------------- #
#  geometry  (shared by draw_fn and mouse_fn)
# --------------------------------------------------------------------------- #
def paint_geom(win):
    """Return a dict of all clickable/drawable rects for the given window."""
    bx, by, bw, bh = win.body_rect()
    # tool box column on the left
    tools = []
    tx = bx + PAD
    ty = by + PAD
    btn_w = TBW - 2
    for i, (key, label) in enumerate(TOOLS):
        ry = ty + i * (TBTN + 2)
        tools.append((key, label, tx, ry, btn_w, TBTN))

    # canvas: right of the tool box, above the palette
    cx = bx + PAD + TBW + PAD
    cy = by + PAD
    cw = bx + bw - PAD - cx
    ch = by + bh - PAD - PALH - PAD - cy
    if cw < 1:
        cw = 1
    if ch < 1:
        ch = 1
    canvas = (cx, cy, cw, ch)

    # palette: row(s) of swatches along the bottom, full width under the canvas
    px0 = bx + PAD + TBW + PAD
    py0 = by + bh - PAD - PALH
    swatches = []
    per_row = max(1, (bx + bw - PAD - px0 + 2) // (SW + 2))
    for i, col in enumerate(PALETTE):
        r = i // per_row
        c = i % per_row
        sx = px0 + c * (SW + 2)
        sy = py0 + r * (SW + 2)
        swatches.append((col, sx, sy, SW, SW))
    # current-colour preview swatch sits to the left of the palette block
    cur_prev = (bx + PAD, py0, TBW - 2, SW)

    return {
        "body": (bx, by, bw, bh),
        "tools": tools,
        "canvas": canvas,
        "swatches": swatches,
        "cur_prev": cur_prev,
    }


def _clamp_to_canvas(g, x, y):
    cx, cy, cw, ch = g["canvas"]
    if x < cx:
        x = cx
    elif x > cx + cw - 1:
        x = cx + cw - 1
    if y < cy:
        y = cy
    elif y > cy + ch - 1:
        y = cy + ch - 1
    return x, y


def _in_rect(px, py, r):
    x, y, w, h = r
    return x <= px < x + w and y <= py < y + h


# --------------------------------------------------------------------------- #
#  lifecycle
# --------------------------------------------------------------------------- #
def init_fn(win):
    win.state = {
        "shapes": [],      # committed shapes
        "tool": "pencil",
        "color": "#000000",
        "size": 2,
        "cur": None,       # in-progress shape
    }


# --------------------------------------------------------------------------- #
#  mouse  (press / drag / release)
# --------------------------------------------------------------------------- #
def mouse_fn(win, phase, px, py, d, btn):
    st = win.state
    g = paint_geom(win)

    if phase == "press":
        # tool buttons?
        for key, label, x, y, w, h in g["tools"]:
            if _in_rect(px, py, (x, y, w, h)):
                st["tool"] = key
                st["cur"] = None
                return
        # palette swatches?
        for col, x, y, w, h in g["swatches"]:
            if _in_rect(px, py, (x, y, w, h)):
                st["color"] = col
                st["cur"] = None
                return
        # canvas? begin a shape
        if _in_rect(px, py, g["canvas"]):
            x, y = _clamp_to_canvas(g, px, py)
            tool = st["tool"]
            if tool in ("pencil", "brush", "eraser"):
                color = C["white"] if tool == "eraser" else st["color"]
                size = st["size"] + (3 if tool == "brush" else 0) \
                    + (4 if tool == "eraser" else 0)
                st["cur"] = {"t": "free", "color": color, "size": size,
                             "pts": [(x, y)]}
            else:
                st["cur"] = {"t": tool, "color": st["color"], "size": st["size"],
                             "x0": x, "y0": y, "x1": x, "y1": y}
        else:
            st["cur"] = None
        return

    if phase == "drag":
        cur = st.get("cur")
        if not cur:
            return
        x, y = _clamp_to_canvas(g, px, py)
        if cur["t"] == "free":
            cur["pts"].append((x, y))
        else:
            cur["x1"] = x
            cur["y1"] = y
        return

    if phase == "release":
        cur = st.get("cur")
        if cur:
            if cur["t"] == "free":
                if len(cur["pts"]) == 1:
                    # a single click: duplicate so it renders as a dot
                    cur["pts"].append(cur["pts"][0])
                st["shapes"].append(cur)
            else:
                st["shapes"].append(cur)
        st["cur"] = None
        return


# --------------------------------------------------------------------------- #
#  shape rendering
# --------------------------------------------------------------------------- #
def _draw_shape(cv, sh):
    color = sh["color"]
    size = max(1, sh.get("size", 1))
    cv.pen(color)
    t = sh["t"]
    if t == "free":
        pts = sh["pts"]
        cv.thickness(size)
        for i in range(1, len(pts)):
            x0, y0 = pts[i - 1]
            x1, y1 = pts[i]
            cv.line(x0, y0, x1, y1)
        if len(pts) == 1:
            x0, y0 = pts[0]
            cv.line(x0, y0, x0, y0)
        cv.thickness(1)
    elif t == "line":
        cv.thickness(size)
        cv.line(sh["x0"], sh["y0"], sh["x1"], sh["y1"])
        cv.thickness(1)
    elif t == "rect":
        x = min(sh["x0"], sh["x1"])
        y = min(sh["y0"], sh["y1"])
        w = abs(sh["x1"] - sh["x0"])
        h = abs(sh["y1"] - sh["y0"])
        cv.thickness(size)
        cv.rect(x, y, w, h)
        cv.thickness(1)
    elif t == "ellipse":
        # approximate as a circle from the bounding-box centre
        cxp = (sh["x0"] + sh["x1"]) // 2
        cyp = (sh["y0"] + sh["y1"]) // 2
        r = max(abs(sh["x1"] - sh["x0"]), abs(sh["y1"] - sh["y0"])) // 2
        if r < 1:
            r = 1
        cv.thickness(size)
        cv.circ(cxp, cyp, r)
        cv.thickness(1)


# --------------------------------------------------------------------------- #
#  draw
# --------------------------------------------------------------------------- #
def draw_fn(cv, d, win):
    st = win.state
    g = paint_geom(win)
    bx, by, bw, bh = g["body"]

    # tool box
    for key, label, x, y, w, h in g["tools"]:
        sel = (key == st["tool"])
        top = lighten(C["win"], 0.55) if not sel else "#cfe0f4"
        bot = darken(C["win"], 0.06) if not sel else "#9fc1ec"
        cv.vgrad(x, y, w, h, top, bot, 5)
        cv.pen("#9aa6b4" if not sel else C["winframe"])
        cv.rect(x, y, w, h)
        cv.pen(C["ink"])
        cv.text(x + w // 2 - len(label) * d.charw // 2, y + h // 2 + 5, label)

    # canvas background (sunken white)
    cx, cy, cw, ch = g["canvas"]
    cv.pen(C["sunkenbd"]); cv.rectf(cx - 1, cy - 1, cw + 2, ch + 2)
    cv.pen(C["sunken"]); cv.rectf(cx, cy, cw, ch)

    # committed shapes
    for sh in st["shapes"]:
        _draw_shape(cv, sh)
    # in-progress preview
    if st.get("cur"):
        _draw_shape(cv, st["cur"])

    # current-colour preview block
    px, py, pw, ph = g["cur_prev"]
    cv.pen(C["sunkenbd"]); cv.rect(px - 1, py - 1, pw + 2, ph + 2)
    cv.pen(st["color"]); cv.rectf(px, py, pw, ph)

    # palette swatches
    for col, x, y, w, h in g["swatches"]:
        cv.pen(col); cv.rectf(x, y, w, h)
        if col == st["color"]:
            cv.pen(C["winframe"]); cv.rect(x - 1, y - 1, w + 1, h + 1)
            cv.pen(C["white"]); cv.rect(x, y, w - 1, h - 1)
        else:
            cv.pen("#808080"); cv.rect(x, y, w, h)


# --------------------------------------------------------------------------- #
#  icon
# --------------------------------------------------------------------------- #
def icon16_fn(cv, x, y):
    # a little artist's palette blob with three colour dots + a brush
    cv.pen("#d8b27a")
    cv.polyf([x + 2, y + 9, x + 4, y + 4, x + 9, y + 2,
              x + 13, y + 5, x + 12, y + 11, x + 7, y + 13])
    cv.pen("#a87f4a"); cv.circ(x + 11, y + 10, 1)   # thumb hole
    cv.pen("#ffffff"); cv.circf(x + 11, y + 10, 1)
    cv.pen("#e04030"); cv.circf(x + 5, y + 6, 1)
    cv.pen("#3060d0"); cv.circf(x + 8, y + 5, 1)
    cv.pen("#30b040"); cv.circf(x + 6, y + 9, 1)
    # brush handle across the corner
    cv.pen("#8a5a30"); cv.thickness(2)
    cv.line(x + 9, y + 13, x + 14, y + 8)
    cv.thickness(1)
    cv.pen("#c0c0c0"); cv.line(x + 13, y + 9, x + 15, y + 7)


# --------------------------------------------------------------------------- #
#  spec
# --------------------------------------------------------------------------- #
def make_app():
    return {
        "kind": "paint",
        "title": "untitled - Paint",
        "size": (480, 360),
        "init": init_fn,
        "draw": draw_fn,
        "mouse": mouse_fn,
        "icon16": icon16_fn,
        "start": True,
    }


# --------------------------------------------------------------------------- #
#  smoke test
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    from shoexp_ui import Canvas
    class _W:
        def __init__(s, kind, size):
            s.x, s.y = 40, 40; s.w, s.h = size; s.kind = kind
            s.title = ""; s.id = 1; s.state = {}
        def body_rect(s):
            return (s.x + 4, s.y + 26, s.w - 8, s.h - 26 - 4)
    class _D: charw = 8; W = 1280; H = 768
    spec = make_app(); w = _W(spec["kind"], spec["size"]); spec["init"](w)
    d = _D()
    bx, by, bw, bh = w.body_rect()
    # draw a freehand stroke somewhere in the lower-right (likely canvas area)
    spec["mouse"](w, "press", bx + bw - 60, by + bh - 40, d, 0)
    spec["mouse"](w, "drag",  bx + bw - 50, by + bh - 30, d, 0)
    spec["mouse"](w, "drag",  bx + bw - 40, by + bh - 20, d, 0)
    spec["mouse"](w, "release", bx + bw - 40, by + bh - 20, d, 0)
    cv = Canvas(); spec["draw"](cv, d, w); spec["icon16"](cv, 0, 0)
    print("paint smoke ok: lines=%d shapes=%d" % (len(cv.lines), len(w.state.get("shapes", []))))
