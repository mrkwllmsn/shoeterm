# shoexp_minesweeper - classic Beginner Minesweeper for the shoexp desktop.
#
# Self-contained app module: make_app() returns the spec dict shoexp consumes.
# 9x9 grid, 10 mines.  Geometry is shared between draw and click via cell_rect /
# face_rect so hit-tests mirror the drawn rects (the shoexp idiom).

import random

from shoexp_ui import C, mix, lighten, darken, human  # noqa: F401

GRID = 9          # cells per side
MINES = 10        # bombs
CELL = 22         # px per cell
HDR = 38          # header band height (counter + smiley)
PAD = 8           # body padding around the playfield

# classic number colours, index 1..8
NUMCOL = {
    1: "#0000ff", 2: "#008000", 3: "#ff0000", 4: "#000080",
    5: "#800000", 6: "#008080", 7: "#000000", 8: "#808080",
}


def _board_px():
    return GRID * CELL


def make_app():
    w = _board_px() + 2 * PAD + 8           # body width + window chrome
    h = HDR + _board_px() + 3 * PAD + 26 + 8  # header + grid + title bar
    return {
        "kind": "mines",
        "title": "Minesweeper",
        "size": (w, h),
        "init": mines_init,
        "draw": draw_mines,
        "click": mines_click,
        "icon16": icon16,
        "start": True,
    }


# ----- state --------------------------------------------------------------- #
def mines_init(win):
    win.state = _new_game()
    win.title = "Minesweeper"


def _new_game():
    return {
        "mine": [[False] * GRID for _ in range(GRID)],
        "adj": [[0] * GRID for _ in range(GRID)],
        "shown": [[False] * GRID for _ in range(GRID)],
        "flag": [[False] * GRID for _ in range(GRID)],
        "placed": False,     # defer mine placement until first reveal
        "over": False,       # game finished
        "won": False,
        "moves": 0,
    }


def _place_mines(st, safe_r, safe_c):
    # avoid the first-clicked cell so the opening move never loses
    cells = [(r, c) for r in range(GRID) for c in range(GRID)
             if not (r == safe_r and c == safe_c)]
    for r, c in random.sample(cells, MINES):
        st["mine"][r][c] = True
    for r in range(GRID):
        for c in range(GRID):
            st["adj"][r][c] = sum(
                st["mine"][r + dr][c + dc]
                for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                if 0 <= r + dr < GRID and 0 <= c + dc < GRID
                and not (dr == 0 and dc == 0))
    st["placed"] = True


# ----- geometry (shared by draw + click) ----------------------------------- #
def grid_origin(win):
    bx, by, bw, bh = win.body_rect()
    gx = bx + (bw - _board_px()) // 2
    gy = by + HDR + PAD
    return gx, gy


def cell_rect(win, col, row):
    gx, gy = grid_origin(win)
    return (gx + col * CELL, gy + row * CELL, CELL, CELL)


def cell_at(win, px, py):
    gx, gy = grid_origin(win)
    if px < gx or py < gy:
        return None
    col = (px - gx) // CELL
    row = (py - gy) // CELL
    if 0 <= col < GRID and 0 <= row < GRID:
        return (int(col), int(row))
    return None


def face_rect(win):
    bx, by, bw, bh = win.body_rect()
    fs = 26
    return (bx + bw // 2 - fs // 2, by + PAD + (HDR - 2 * PAD - fs) // 2 + 4, fs, fs)


# ----- drawing ------------------------------------------------------------- #
def _bevel(cv, x, y, w, h, raised):
    # 2px bevel: light on top/left, dark on bottom/right (or reversed)
    hi = "#ffffff" if raised else "#808080"
    lo = "#808080" if raised else "#ffffff"
    cv.pen(hi)
    cv.rectf(x, y, w, 2)
    cv.rectf(x, y, 2, h)
    cv.pen(lo)
    cv.rectf(x, y + h - 2, w, 2)
    cv.rectf(x + w - 2, y, 2, h)


def _draw_face(cv, win, d):
    fx, fy, fw, fh = face_rect(win)
    cv.pen("#c0c0c0")
    cv.rectf(fx, fy, fw, fh)
    _bevel(cv, fx, fy, fw, fh, True)
    st = win.state
    cx, cy, r = fx + fw // 2, fy + fh // 2, fw // 2 - 5
    cv.pen("#ffd72e")
    cv.circf(cx, cy, r)
    cv.pen("#000000")
    cv.circ(cx, cy, r)
    ex = r // 2
    if st["over"] and not st["won"]:
        # dead face: X eyes + frown
        for s in (-1, 1):
            cv.line(cx + s * ex - 2, cy - 3, cx + s * ex + 2, cy + 1)
            cv.line(cx + s * ex + 2, cy - 3, cx + s * ex - 2, cy + 1)
        cv.arc(cx, cy + r // 2 + 2, r // 2, 200, 340)
    else:
        # eyes
        cv.circf(cx - ex, cy - 2, 1)
        cv.circf(cx + ex, cy - 2, 1)
        if st["won"]:
            # cool shades + smile
            cv.rectf(cx - ex - 3, cy - 4, ex * 2 + 6, 4)
            cv.arc(cx, cy + 1, r // 2, 20, 160)
        else:
            cv.arc(cx, cy + 1, r // 2, 20, 160)


def _seven_seg(cv, x, y, w, h, txt):
    # sunken red-on-black LED-ish counter
    cv.pen("#000000")
    cv.rectf(x, y, w, h)
    cv.pen("#ff2020")
    cv.text(x + 4, y + h // 2 + 5, txt)


def draw_mines(cv, d, win):
    st = win.state
    bx, by, bw, bh = win.body_rect()

    # header band (sunken panel)
    hx, hy, hw, hh = bx + PAD, by + PAD, bw - 2 * PAD, HDR - 2 * PAD
    cv.pen("#c0c0c0")
    cv.rectf(hx, hy, hw, hh)
    _bevel(cv, hx, hy, hw, hh, False)

    # mine counter (left): mines minus flags
    flags = sum(st["flag"][r][c] for r in range(GRID) for c in range(GRID))
    left = MINES - flags
    _seven_seg(cv, hx + 6, hy + 4, 42, hh - 8, "%03d" % max(-99, min(999, left)))

    # move counter (right)
    _seven_seg(cv, hx + hw - 48, hy + 4, 42, hh - 8, "%03d" % min(999, st["moves"]))

    # smiley reset
    _draw_face(cv, win, d)

    # playfield frame (sunken)
    bd = _board_px()
    gx, gy = grid_origin(win)
    _bevel(cv, gx - 2, gy - 2, bd + 4, bd + 4, False)

    for row in range(GRID):
        for col in range(GRID):
            x, y, w, h = cell_rect(win, col, row)
            if st["shown"][row][col]:
                cv.pen("#bdbdbd")
                cv.rectf(x, y, w, h)
                cv.pen("#909090")
                cv.rect(x, y, w, h)
                if st["mine"][row][col]:
                    _draw_mine(cv, x, y, w, h,
                               hit=(st["over"] and not st["won"]))
                else:
                    n = st["adj"][row][col]
                    if n:
                        cv.pen(NUMCOL[n])
                        cv.text(x + w // 2 - d.charw // 2, y + h // 2 + 6, str(n))
            else:
                cv.pen("#c0c0c0")
                cv.rectf(x, y, w, h)
                _bevel(cv, x, y, w, h, True)
                if st["flag"][row][col]:
                    _draw_flag(cv, x, y, w, h)


def _draw_mine(cv, x, y, w, h, hit=False):
    cx, cy = x + w // 2, y + h // 2
    r = w // 4
    if hit:
        cv.pen("#ff0000")
        cv.rectf(x + 1, y + 1, w - 2, h - 2)
    cv.pen("#000000")
    cv.circf(cx, cy, r)
    cv.line(cx - r - 2, cy, cx + r + 2, cy)
    cv.line(cx, cy - r - 2, cx, cy + r + 2)
    cv.line(cx - r, cy - r, cx + r, cy + r)
    cv.line(cx - r, cy + r, cx + r, cy - r)
    cv.pen("#ffffff")
    cv.circf(cx - r // 3, cy - r // 3, 1)


def _draw_flag(cv, x, y, w, h):
    px = x + w // 2 - 1
    cv.pen("#000000")
    cv.rectf(px, y + 5, 2, h - 10)
    cv.rectf(x + 5, y + h - 6, w - 10, 2)
    cv.pen("#ff0000")
    cv.trif(px, y + 4, px, y + 11, x + 5, y + 7)


# ----- gameplay ------------------------------------------------------------ #
def _reveal(st, r, c):
    # flood-fill open from (r,c)
    stack = [(r, c)]
    while stack:
        cr, cc = stack.pop()
        if st["shown"][cr][cc] or st["flag"][cr][cc]:
            continue
        st["shown"][cr][cc] = True
        if st["adj"][cr][cc] == 0 and not st["mine"][cr][cc]:
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    nr, nc = cr + dr, cc + dc
                    if 0 <= nr < GRID and 0 <= nc < GRID:
                        if not st["shown"][nr][nc] and not st["flag"][nr][nc]:
                            stack.append((nr, nc))


def _check_win(st):
    for r in range(GRID):
        for c in range(GRID):
            if not st["mine"][r][c] and not st["shown"][r][c]:
                return False
    return True


def mines_click(win, px, py, d, btn):
    st = win.state

    # smiley always resets, even mid-game / after over
    fx, fy, fw, fh = face_rect(win)
    if fx <= px < fx + fw and fy <= py < fy + fh:
        win.state = _new_game()
        win.title = "Minesweeper"
        return True

    if st["over"]:
        return True  # consume clicks but ignore until reset

    cell = cell_at(win, px, py)
    if cell is None:
        return False
    col, row = cell

    if btn == 2:  # right-click: toggle flag
        if not st["shown"][row][col]:
            st["flag"][row][col] = not st["flag"][row][col]
        return True

    if btn != 0:  # only left-click reveals
        return True

    if st["flag"][row][col] or st["shown"][row][col]:
        return True

    if not st["placed"]:
        _place_mines(st, row, col)

    st["moves"] += 1

    if st["mine"][row][col]:
        # boom: reveal every mine, sad face
        for r in range(GRID):
            for c in range(GRID):
                if st["mine"][r][c]:
                    st["shown"][r][c] = True
        st["shown"][row][col] = True
        st["over"] = True
        st["won"] = False
        win.title = "Minesweeper - Game Over"
        return True

    _reveal(st, row, col)

    if _check_win(st):
        st["over"] = True
        st["won"] = True
        # flag remaining mines for the victory look
        for r in range(GRID):
            for c in range(GRID):
                if st["mine"][r][c]:
                    st["flag"][r][c] = True
        win.title = "Minesweeper - You Win!"
    return True


# ----- icon ---------------------------------------------------------------- #
def icon16(cv, x, y):
    # grey tile with a small black mine + spokes
    cv.pen("#c0c0c0")
    cv.rectf(x + 1, y + 1, 14, 14)
    cv.pen("#ffffff")
    cv.line(x + 1, y + 1, x + 14, y + 1)
    cv.line(x + 1, y + 1, x + 1, y + 14)
    cv.pen("#808080")
    cv.line(x + 1, y + 14, x + 14, y + 14)
    cv.line(x + 14, y + 1, x + 14, y + 14)
    cx, cy, r = x + 8, y + 8, 3
    cv.pen("#000000")
    cv.line(cx - r - 1, cy, cx + r + 1, cy)
    cv.line(cx, cy - r - 1, cx, cy + r + 1)
    cv.line(cx - r, cy - r, cx + r, cy + r)
    cv.line(cx - r, cy + r, cx + r, cy - r)
    cv.circf(cx, cy, r)
    cv.pen("#ffffff")
    cv.circf(cx - 1, cy - 1, 1)


if __name__ == "__main__":
    from shoexp_ui import Canvas
    class _W:
        def __init__(s, kind, size):
            s.x, s.y = 40, 40; s.w, s.h = size; s.kind = kind
            s.title = ""; s.id = 1; s.state = {}
        def body_rect(s):
            return (s.x + 4, s.y + 26, s.w - 8, s.h - 26 - 4)
    class _D: charw = 8; W = 1280; H = 768
    spec = make_app()
    w = _W(spec["kind"], spec["size"]); spec["init"](w)
    cv = Canvas(); spec["draw"](cv, _D(), w)
    spec["icon16"](cv, 0, 0)
    spec["click"](w, w.x + 20, w.y + 60, _D(), 0)   # left
    spec["click"](w, w.x + 40, w.y + 60, _D(), 2)   # right (flag)
    spec["draw"](cv, _D(), w)
    print("mines smoke ok: lines=%d" % len(cv.lines))
