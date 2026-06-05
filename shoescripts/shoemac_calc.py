# shoemac_calc - the Snow Leopard "Calculator" app for the shoemac desktop.
#
# Self-contained app module: make_app() returns the spec dict the host consumes
# (it calls register_app(make_app()) in _load_apps).  The arithmetic state
# machine is ported verbatim from shoexp's built-in calculator -- a state dict
# {cur, acc, op, fresh} mutated by calc_press / _calc / _fmt -- so behaviour is
# identical; only the chrome is reskinned to the graphite Snow Leopard look:
# a dark rounded body, a recessed right-aligned display, round-ish buttons with
# the operator column (+ - * / =) in a graphite/orange accent and the digit
# keys a lighter graphite.
#
# Geometry is shared between draw and click through calc_grid / calc_btn_rect,
# so the hit-tests mirror the drawn rects exactly (the shoexp/shoemac idiom).

from shoemac_ui import C, mix, lighten, darken  # noqa: F401

# ----- graphite palette (local to the calculator skin) --------------------- #
# The shared C palette is the light Aqua window theme; the Snow Leopard
# Calculator is a dark graphite slab, so its colours live here rather than in C.
CALC = {
    "body0":   "#3a3d42",   # body gradient, top
    "body1":   "#202327",   # body gradient, bottom
    "bodyedge": "#15171a",   # body outline
    "disp0":   "#10130f",   # display recess, top (dark olive-charcoal)
    "disp1":   "#1c211a",   # display recess, bottom
    "dispbd":  "#000000",   # display bevel line
    "dispink": "#e9f3e6",   # display digits (faint phosphor green-white)
    "num0":    "#6c7076",   # number key, top
    "num1":    "#4a4e54",   # number key, bottom
    "numink":  "#ffffff",
    "op0":     "#54585f",   # operator key, top (graphite)
    "op1":     "#34373c",   # operator key, bottom
    "opink":   "#ffffff",
    "acc0":    "#ffb13d",   # equals / accent key, top (orange)
    "acc1":    "#f08a17",   # equals / accent key, bottom
    "accink":  "#ffffff",
    "keyedge": "#1a1c1f",   # key outline
    "keyhi":   "#ffffff33",  # key top sheen
}

# label, key, col, row, colspan  (identical layout to shoexp's CALC_KEYS)
CALC_KEYS = [
    ("C", "C", 0, 0, 1), ("+-", "neg", 1, 0, 1), ("%", "%", 2, 0, 1), ("/", "/", 3, 0, 1),
    ("7", "7", 0, 1, 1), ("8", "8", 1, 1, 1), ("9", "9", 2, 1, 1), ("*", "*", 3, 1, 1),
    ("4", "4", 0, 2, 1), ("5", "5", 1, 2, 1), ("6", "6", 2, 2, 1), ("-", "-", 3, 2, 1),
    ("1", "1", 0, 3, 1), ("2", "2", 1, 3, 1), ("3", "3", 2, 3, 1), ("+", "+", 3, 3, 1),
    ("0", "0", 0, 4, 2), (".", ".", 2, 4, 1), ("=", "=", 3, 4, 1),
]

OPS = ("/", "*", "-", "+", "=")


def make_app():
    return {
        "kind": "calc",
        "title": "Calculator",
        "size": (208, 296),
        "init": calc_init,
        "draw": draw_calc,
        "click": calc_click,
        "key": calc_key,
        "icon16": icon16,
        "icon48": icon48,
        "dock": True,
    }


# ----- state --------------------------------------------------------------- #
def calc_init(win):
    # state machine seed -- identical shape to shoexp's inline calc init.
    win.state = {"cur": "0", "acc": None, "op": None, "fresh": True}
    win.title = "Calculator"


# ----- geometry (shared by draw + click) ----------------------------------- #
def calc_grid(win):
    bx, by, bw, bh = win.body_rect()
    pad = 8
    disp_h = 40
    gx = bx + pad
    gy = by + pad + disp_h + 8
    gw = bw - 2 * pad
    gh = bh - pad - (gy - by)
    cols, rows = 4, 5
    cellw = gw // cols
    cellh = gh // rows
    return bx, by, bw, bh, pad, disp_h, gx, gy, cellw, cellh


def calc_btn_rect(win, col, row, span):
    _, _, _, _, _, _, gx, gy, cellw, cellh = calc_grid(win)
    x = gx + col * cellw + 2
    y = gy + row * cellh + 2
    w = cellw * span - 4
    h = cellh - 4
    return (x, y, w, h)


# ----- draw ----------------------------------------------------------------- #
def draw_calc(cv, d, win):
    bx, by, bw, bh, pad, disp_h, gx, gy, cellw, cellh = calc_grid(win)

    # graphite body slab (fills our own background, as the contract requires)
    cv.vgrad(bx, by, bw, bh, CALC["body0"], CALC["body1"], 18)
    cv.pen(CALC["bodyedge"])
    cv.rect(bx, by, bw, bh)

    # recessed display: a dark olive-charcoal well with a black bevel,
    # right-aligned phosphor digits (the classic calculator readout).
    dx, dy, dw = bx + pad, by + pad, bw - 2 * pad
    cv.pen(CALC["dispbd"])
    cv.rrect(dx - 1, dy - 1, dw + 2, disp_h + 2, 5)
    cv.vgrad(dx, dy, dw, disp_h, CALC["disp0"], CALC["disp1"], 8)
    cv.pen(CALC["dispbd"])
    cv.rrect(dx, dy, dw, disp_h, 5)
    s = win.state["cur"]
    txt = s if len(s) <= 12 else s[:12]
    cv.pen(CALC["dispink"])
    cv.text(dx + dw - len(txt) * d.charw - 10, dy + disp_h - 13, txt)

    # buttons: digits lighter graphite, operator column graphite, equals orange.
    for label, key, col, row, span in CALC_KEYS:
        x, y, w, h = calc_btn_rect(win, col, row, span)
        if key == "=":
            top, bot, ink = CALC["acc0"], CALC["acc1"], CALC["accink"]
        elif key in OPS:
            top, bot, ink = CALC["op0"], CALC["op1"], CALC["opink"]
        else:
            top, bot, ink = CALC["num0"], CALC["num1"], CALC["numink"]
        r = min(8, h // 2)
        cv.vgrad(x, y, w, h, top, bot, 6)
        # a thin top sheen line for the glassy Aqua-ish key
        cv.pen(CALC["keyhi"])
        cv.line(x + r, y + 1, x + w - r, y + 1)
        cv.pen(CALC["keyedge"])
        cv.rrect(x, y, w, h, r)
        cv.pen(ink)
        cv.text(x + w // 2 - len(label) * d.charw // 2, y + h // 2 + 6, label)


# ----- input ---------------------------------------------------------------- #
def calc_click(win, px, py, d, btn):
    # left-click only; mirror the drawn key rects exactly.
    if btn != 0:
        return False
    for label, key, col, row, span in CALC_KEYS:
        x, y, w, h = calc_btn_rect(win, col, row, span)
        if x <= px < x + w and y <= py < y + h:
            calc_press(win, key)
            return True
    return False


def calc_key(win, key, d):
    # let the keyboard drive the calculator too (focused window only).
    m = {"enter": "=", "back": "C", "del": "C"}
    if key in m:
        calc_press(win, m[key])
        return True
    if key in "0123456789.+-*/%":
        calc_press(win, key)
        return True
    if key in ("c", "C"):
        # don't steal the desktop's quit key; only treat lowercase 'c' / 'C'
        # as clear here would clash with quit ('q'), so map explicit 'c'.
        calc_press(win, "C")
        return True
    if key == "=":
        calc_press(win, "=")
        return True
    return False


# ----- arithmetic state machine (verbatim port from shoexp) ----------------- #
def calc_press(win, key):
    st = win.state
    cur = st["cur"]
    if cur == "Error" and key != "C":
        return
    if key in "0123456789":
        if st["fresh"]:
            cur = key
            st["fresh"] = False
        else:
            cur = key if cur == "0" else cur + key
    elif key == ".":
        if st["fresh"]:
            cur = "0."
            st["fresh"] = False
        elif "." not in cur:
            cur += "."
    elif key == "neg":
        if cur != "0":
            cur = cur[1:] if cur.startswith("-") else "-" + cur
    elif key == "%":
        try:
            cur = _fmt(float(cur) / 100.0)
        except ValueError:
            cur = "Error"
    elif key in "+-*/":
        if st["op"] and not st["fresh"]:
            st["acc"] = _calc(st["acc"], st["op"], float(cur))
            cur = _fmt(st["acc"])
        else:
            st["acc"] = float(cur)
        st["op"] = key
        st["fresh"] = True
    elif key == "=":
        if st["op"] is not None:
            st["acc"] = _calc(st["acc"], st["op"], float(cur))
            cur = _fmt(st["acc"])
            st["op"] = None
            st["fresh"] = True
    elif key == "C":
        cur = "0"
        st["acc"] = None
        st["op"] = None
        st["fresh"] = True
    st["cur"] = cur


def _calc(a, op, b):
    try:
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            return a / b
    except ZeroDivisionError:
        return None
    return b


def _fmt(v):
    if v is None:
        return "Error"
    if v == int(v) and abs(v) < 1e15:
        return str(int(v))
    return ("%.10g" % v)


# ----- icons ---------------------------------------------------------------- #
def _calc_tile(cv, x, y, s):
    # a graphite calculator: rounded body, green display strip, 3x4 key grid.
    r = max(2, s // 7)
    cv.vgrad(x, y, s, s, CALC["body0"], CALC["body1"], 8)
    cv.pen(CALC["bodyedge"])
    cv.rrect(x, y, s, s, r)
    pad = max(2, s // 9)
    # display
    dh = max(3, s // 5)
    cv.pen(CALC["disp1"])
    cv.rectf(x + pad, y + pad, s - 2 * pad, dh)
    cv.pen(CALC["dispbd"])
    cv.rect(x + pad, y + pad, s - 2 * pad, dh)
    # key grid (3 cols x 4 rows), bottom-right key orange
    gy = y + pad + dh + max(1, s // 16)
    gw = s - 2 * pad
    gh = (y + s - pad) - gy
    cols, rows = 3, 4
    cw = gw / cols
    chh = gh / rows
    for rr in range(rows):
        for cc in range(cols):
            kx = x + pad + cc * cw
            ky = gy + rr * chh
            accent = (rr == rows - 1 and cc == cols - 1)
            cv.pen(CALC["acc0"] if accent else CALC["num0"])
            cv.rectf(int(kx) + 1, int(ky) + 1, int(cw) - 2, int(chh) - 2)


def icon16(cv, x, y):
    _calc_tile(cv, x, y, 16)


def icon48(cv, cx, top):
    s = 40
    _calc_tile(cv, cx - s // 2, top, s)
