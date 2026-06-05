# shoexp_ie - a (lovingly fake) Internet Explorer 6 for the shoexp desktop.
#
# Self-contained app module: `make_app()` returns the spec dict shoexp uses to
# register an app (window draw/click + desktop & start-menu icons).  There is no
# real networking -- the browser navigates between a handful of canned "pages"
# keyed by URL, and clicking an underlined link pushes the current page onto the
# Back history and loads the target page.
#
# All chrome is drawn from foot vector-graphics primitives via the shared
# Canvas.  Text is ASCII-only (a missing glyph truncates the rest of the
# string), so the classic blue "e" logo is built from arcs/ellipses + a yellow
# ring rather than a unicode character.

from shoexp_ui import C, mix, lighten, darken


# --------------------------------------------------------------------------- #
#  palette
# --------------------------------------------------------------------------- #
IE_BLUE = "#1b66c9"      # the "e" body
IE_BLUE_HI = "#5aa0ee"
IE_YELLOW = "#f4c12a"    # the orbit ring
LINK = "#1a3fa0"         # classic underlined-link blue
LINK_VIS = "#7a2aa0"
MSN_HDR0 = "#2f74d8"
MSN_HDR1 = "#1b4ea0"


# --------------------------------------------------------------------------- #
#  the blue "e" logo, drawn from shapes
# --------------------------------------------------------------------------- #
def _draw_e(cv, cx, cy, r):
    """Draw the IE 'e' centred at (cx,cy) with radius ~r, from primitives."""
    ri = int(r)
    # yellow orbit ring (tilted ellipse approximated with two arcs)
    cv.pen(IE_YELLOW)
    cv.thickness(max(2, ri // 4))
    cv.arc(cx, cy, ri + max(2, ri // 3), 200, 340)
    cv.arc(cx, cy, ri + max(2, ri // 3), 20, 160)
    cv.thickness(1)
    # blue disc with a lighter top for a glossy look
    cv.pen(IE_BLUE)
    cv.circf(cx, cy, ri)
    cv.pen(IE_BLUE_HI)
    cv.arc(cx, cy, ri - 1, 200, 340)
    # carve the white "e": a white ring with a wedge cut on the right plus the
    # white horizontal bar.  Built from a white circle + blue inner disc.
    cv.pen("#ffffff")
    cv.circf(cx, cy, max(2, ri * 3 // 5))
    cv.pen(IE_BLUE)
    cv.circf(cx, cy, max(1, ri * 2 // 5))
    # white cross-bar of the e
    bar_h = max(2, ri // 3)
    cv.pen("#ffffff")
    cv.rectf(cx - ri * 3 // 5, cy - bar_h // 2, ri * 6 // 5, bar_h)
    # open the mouth on the lower-right with a blue wedge
    cv.pen(IE_BLUE)
    cv.trif(cx, cy, cx + ri, cy + bar_h, cx + ri, cy + ri)


def icon16(cv, x, y):
    _draw_e(cv, x + 8, y + 8, 6)


def icon48(cv, cx, top):
    # ~40px desktop icon, centred on cx, top edge at y=top
    r = 16
    _draw_e(cv, cx, top + r + 4, r)


# --------------------------------------------------------------------------- #
#  page registry
# --------------------------------------------------------------------------- #
# Each page is keyed by an id.  draw_page() renders it; page_links() yields the
# clickable-link geometry (shared by draw + click so hit-boxes mirror the text).
PAGES = {
    "msn": {
        "url": "http://www.msn.com/",
        "title": "MSN.com",
        "kind": "msn",
        "links": [
            ("Top stories from around the web", "search"),
            ("Markets rally as chips lead gains", "search"),
            ("Ten tips for a faster XP machine", "search"),
            ("Weather: sunny, 72F all weekend", "search"),
        ],
    },
    "search": {
        "url": "http://search.msn.com/results.aspx?q=xp",
        "title": "Search Results",
        "kind": "search",
        "links": [
            ("Windows XP - Home Page", "msn"),
            ("Internet Explorer 6 downloads", "about"),
            ("The Bliss wallpaper, explained", "msn"),
            ("Solitaire strategy guide", "search"),
            ("Dial-up vs broadband in 2003", "about"),
        ],
    },
    "about": {
        "url": "about:blank",
        "title": "The page cannot be displayed",
        "kind": "error",
        "links": [
            ("Try MSN.com instead", "msn"),
        ],
    },
}
START_PAGE = "msn"


# --------------------------------------------------------------------------- #
#  toolbar / address-bar layout (geometry shared by draw + click)
# --------------------------------------------------------------------------- #
TOOL_H = 30      # toolbar strip height
ADDR_H = 24      # address-bar strip height


def _toolbar_buttons(bx, by, d):
    """Return [(key, x, y, w, h, label), ...] for the toolbar buttons."""
    out = []
    x = bx + 6
    y = by + 4
    h = TOOL_H - 8
    for key in ("back", "fwd", "stop", "refresh", "home"):
        w = 26
        out.append((key, x, y, w, h))
        x += w + 3
    return out


def _addr_field(bx, by, bw, d):
    """Return (label_x, field_x, field_y, field_w, field_h, go_x, go_w)."""
    ay = by + TOOL_H + 3
    fh = ADDR_H - 6
    lbl_x = bx + 8
    fx = lbl_x + 8 * d.charw
    go_w = 4 * d.charw
    go_x = bx + bw - go_w - 6
    fw = go_x - fx - 6
    return lbl_x, fx, ay, fw, fh, go_x, go_w


# --------------------------------------------------------------------------- #
#  toolbar button glyphs
# --------------------------------------------------------------------------- #
def _bevel(cv, x, y, w, h, enabled=True):
    top = C["white"] if enabled else lighten(C["win"], 0.4)
    face = lighten(C["win"], 0.3) if enabled else C["win"]
    cv.pen(face)
    cv.rectf(x, y, w, h)
    cv.pen(top)
    cv.line(x, y, x + w - 1, y)
    cv.line(x, y, x, y + h - 1)
    cv.pen(C["sunkenbd"])
    cv.line(x, y + h - 1, x + w - 1, y + h - 1)
    cv.line(x + w - 1, y, x + w - 1, y + h - 1)


def _btn_glyph(cv, key, x, y, w, h, enabled):
    cx = x + w // 2
    cy = y + h // 2
    g = C["ink"] if enabled else C["dim"]
    if key == "back":
        cv.pen(g if enabled else C["dim"])
        cv.trif(cx - 4, cy, cx + 3, cy - 5, cx + 3, cy + 5)
    elif key == "fwd":
        cv.pen(g if enabled else C["dim"])
        cv.trif(cx + 4, cy, cx - 3, cy - 5, cx - 3, cy + 5)
    elif key == "stop":
        cv.pen("#d83a2a")
        cv.circf(cx, cy, 6)
        cv.pen("#ffffff")
        cv.thickness(2)
        cv.line(cx - 3, cy - 3, cx + 3, cy + 3)
        cv.line(cx - 3, cy + 3, cx + 3, cy - 3)
        cv.thickness(1)
    elif key == "refresh":
        cv.pen("#2f8f3a")
        cv.thickness(2)
        cv.arc(cx, cy, 6, 300, 210)
        cv.thickness(1)
        cv.pen("#2f8f3a")
        cv.trif(cx + 6, cy - 7, cx + 6, cy + 1, cx + 1, cy - 3)
    elif key == "home":
        cv.pen("#8a5a2a")
        cv.rectf(cx - 5, cy - 1, 10, 6)
        cv.pen("#c0392b")
        cv.trif(cx - 6, cy - 1, cx + 6, cy - 1, cx, cy - 7)
        cv.pen("#ffd27f")
        cv.rectf(cx - 1, cy + 1, 3, 4)


# --------------------------------------------------------------------------- #
#  page rendering
# --------------------------------------------------------------------------- #
def page_links(rect, page_id, d):
    """Yield (label, target_id, lx, ly, lw, lh) for each clickable link, using
    the same coordinates the draw routine uses so hit-boxes mirror the text."""
    bx, by, bw, bh = rect
    page = PAGES.get(page_id)
    if not page:
        return []
    out = []
    kind = page["kind"]
    if kind == "msn":
        # links start under the header band + search box
        ly = by + 96
        for label, target in page["links"]:
            lw = len(label) * d.charw
            out.append((label, target, bx + 16, ly - 12, lw, 16))
            ly += 22
    elif kind == "search":
        ly = by + 56
        for label, target in page["links"]:
            lw = len(label) * d.charw
            out.append((label, target, bx + 16, ly - 12, lw, 16))
            ly += 34
    elif kind == "error":
        ly = by + bh - 40
        for label, target in page["links"]:
            lw = len(label) * d.charw
            out.append((label, target, bx + 16, ly - 12, lw, 16))
            ly += 22
    return out


def _draw_link_row(cv, d, x, baseline, label):
    cv.pen(LINK)
    cv.text(x, baseline, label)
    cv.pen(LINK)
    cv.line(x, baseline + 2, x + len(label) * d.charw, baseline + 2)


def draw_page(cv, d, rect, page_id):
    bx, by, bw, bh = rect
    page = PAGES.get(page_id, PAGES[START_PAGE])
    kind = page["kind"]
    # white page canvas
    cv.pen(C["white"])
    cv.rectf(bx, by, bw, bh)

    if kind == "msn":
        # blue header band with MSN wordmark
        cv.vgrad(bx, by, bw, 40, MSN_HDR0, MSN_HDR1, 8)
        cv.pen("#ffffff")
        cv.text(bx + 14, by + 27, "MSN")
        # little butterfly mark to the right of MSN
        mfx = bx + 14 + 3 * d.charw + 10
        cv.pen("#7ec8ff")
        cv.trif(mfx, by + 14, mfx + 9, by + 9, mfx + 6, by + 22)
        cv.pen("#3a8de0")
        cv.trif(mfx + 9, by + 14, mfx, by + 9, mfx + 3, by + 22)
        cv.pen("#cfe7ff")
        cv.text(bx + bw - 16 * d.charw, by + 27, "Hotmail  Messenger")
        # search box
        sy = by + 50
        sw = bw - 24 - 5 * d.charw
        cv.pen(C["sunken"])
        cv.rectf(bx + 12, sy, sw, 20)
        cv.pen(C["sunkenbd"])
        cv.rect(bx + 12, sy, sw, 20)
        cv.pen(C["dim"])
        cv.text(bx + 18, sy + 14, "Search the web")
        # Go button
        cv.vgrad(bx + 12 + sw + 4, sy, 5 * d.charw - 8, 20,
                 lighten(MSN_HDR0, 0.2), MSN_HDR1, 4)
        cv.pen("#ffffff")
        cv.text(bx + 12 + sw + 10, sy + 14, "Go")
        # headline links
        for label, target, lx, ly, lw, lh in page_links(rect, page_id, d):
            _draw_link_row(cv, d, lx, ly + 12, label)
        # two colored content tiles along the bottom
        ty = by + bh - 60
        tw = (bw - 36) // 2
        cv.vgrad(bx + 12, ty, tw, 48, "#fbe7a0", "#f3c64a", 6)
        cv.pen(darken("#f3c64a", 0.3))
        cv.rect(bx + 12, ty, tw, 48)
        cv.pen(C["ink"])
        cv.text(bx + 20, ty + 18, "Today on MSN")
        cv.text(bx + 20, ty + 36, "Shopping deals")
        cv.vgrad(bx + 24 + tw, ty, tw, 48, "#bfe0ff", "#6fb0f0", 6)
        cv.pen(darken("#6fb0f0", 0.3))
        cv.rect(bx + 24 + tw, ty, tw, 48)
        cv.pen(C["ink"])
        cv.text(bx + 32 + tw, ty + 18, "Weather")
        cv.text(bx + 32 + tw, ty + 36, "72F  Sunny")

    elif kind == "search":
        cv.vgrad(bx, by, bw, 30, "#eef4ff", "#dbe7fb", 6)
        cv.pen(IE_BLUE)
        cv.text(bx + 12, by + 20, "MSN Search")
        cv.pen(C["dim"])
        cv.text(bx + 12, by + 40, "Results 1-5 of about 1,000,000")
        for label, target, lx, ly, lw, lh in page_links(rect, page_id, d):
            _draw_link_row(cv, d, lx, ly + 12, label)
            cv.pen("#1a8a1a")
            url_label = PAGES.get(target, {}).get("url", "http://www.msn.com/")
            cv.text(lx, ly + 26, url_label)

    elif kind == "error":
        # classic "page cannot be displayed"
        cv.pen(C["ink"])
        cv.text(bx + 16, by + 30, "The page cannot be displayed")
        cv.pen(C["dim"])
        cv.text(bx + 16, by + 56,
                "The page you are looking for is currently")
        cv.text(bx + 16, by + 72,
                "unavailable. The Web site might be")
        cv.text(bx + 16, by + 88,
                "experiencing technical difficulties.")
        # warning glyph
        cv.pen("#f4c12a")
        cv.trif(bx + bw - 60, by + 30, bx + bw - 80, by + 64,
                bx + bw - 40, by + 64)
        cv.pen(C["ink"])
        cv.text(bx + bw - 62, by + 60, "!")
        for label, target, lx, ly, lw, lh in page_links(rect, page_id, d):
            _draw_link_row(cv, d, lx, ly + 12, label)


# --------------------------------------------------------------------------- #
#  spec callbacks
# --------------------------------------------------------------------------- #
def _set_page(win, page_id):
    page = PAGES.get(page_id, PAGES[START_PAGE])
    win.state["page"] = page_id
    win.state["url"] = page["url"]
    win.title = page["title"] + " - Internet Explorer"


def init_fn(win):
    win.state = {"page": START_PAGE, "url": PAGES[START_PAGE]["url"],
                 "back": [], "fwd": []}
    _set_page(win, START_PAGE)


def _navigate(win, target):
    cur = win.state["page"]
    if target == cur:
        return
    win.state["back"].append(cur)
    win.state["fwd"] = []
    _set_page(win, target)


def _go_back(win):
    if win.state["back"]:
        cur = win.state["page"]
        prev = win.state["back"].pop()
        win.state["fwd"].append(cur)
        _set_page(win, prev)


def _go_fwd(win):
    if win.state["fwd"]:
        cur = win.state["page"]
        nxt = win.state["fwd"].pop()
        win.state["back"].append(cur)
        _set_page(win, nxt)


def draw_fn(cv, d, win):
    bx, by, bw, bh = win.body_rect()

    # --- toolbar strip ---
    cv.vgrad(bx, by, bw, TOOL_H, lighten(C["win"], 0.35), C["win"], 4)
    enabled = {
        "back": bool(win.state["back"]),
        "fwd": bool(win.state["fwd"]),
        "stop": True, "refresh": True, "home": True,
    }
    for key, x, y, w, h in _toolbar_buttons(bx, by, d):
        _bevel(cv, x, y, w, h, enabled.get(key, True))
        _btn_glyph(cv, key, x, y, w, h, enabled.get(key, True))
    # the blue "e" logo at top-right of the toolbar
    _draw_e(cv, bx + bw - 18, by + TOOL_H // 2, 9)

    # --- address bar strip ---
    cv.vgrad(bx, by + TOOL_H, bw, ADDR_H, "#f3f4f8", "#dfe3ea", 4)
    lbl_x, fx, fy, fw, fh, go_x, go_w = _addr_field(bx, by, bw, d)
    cv.pen(C["dim"])
    cv.text(lbl_x, fy + fh - 5, "Address")
    cv.pen(C["sunken"])
    cv.rectf(fx, fy, fw, fh)
    cv.pen(C["sunkenbd"])
    cv.rect(fx, fy, fw, fh)
    # little "e" favicon in the field
    _draw_e(cv, fx + 8, fy + fh // 2, 5)
    url = win.state["url"]
    maxc = max(4, (fw - 22) // d.charw)
    shown = url if len(url) <= maxc else url[:maxc - 1] + "~"
    cv.pen(C["ink"])
    cv.text(fx + 18, fy + fh - 5, shown)
    # Go button
    _bevel(cv, go_x, fy, go_w, fh, True)
    cv.pen("#2f8f3a")
    cv.trif(go_x + 6, fy + 4, go_x + 6, fy + fh - 4, go_x + 13, fy + fh // 2)
    cv.pen(C["ink"])
    cv.text(go_x + 16, fy + fh - 5, "Go")

    # --- page area (sunken white) ---
    pax = bx + 4
    pay = by + TOOL_H + ADDR_H + 4
    paw = bw - 8
    pah = bh - (TOOL_H + ADDR_H + 4) - 4
    if pah < 10:
        pah = 10
    cv.pen(C["sunkenbd"])
    cv.rect(pax - 1, pay - 1, paw + 2, pah + 2)
    draw_page(cv, d, (pax, pay, paw, pah), win.state["page"])


def click_fn(win, px, py, d, btn):
    if btn != 0:
        return False
    bx, by, bw, bh = win.body_rect()

    # toolbar buttons
    for key, x, y, w, h in _toolbar_buttons(bx, by, d):
        if x <= px < x + w and y <= py < y + h:
            if key == "back":
                _go_back(win)
            elif key == "fwd":
                _go_fwd(win)
            elif key == "home":
                _navigate(win, START_PAGE)
            # stop / refresh are cosmetic
            return True

    # Go button (cosmetic re-load of current page)
    lbl_x, fx, fy, fw, fh, go_x, go_w = _addr_field(bx, by, bw, d)
    if go_x <= px < go_x + go_w and fy <= py < fy + fh:
        return True

    # page links
    pax = bx + 4
    pay = by + TOOL_H + ADDR_H + 4
    paw = bw - 8
    pah = bh - (TOOL_H + ADDR_H + 4) - 4
    rect = (pax, pay, paw, pah)
    for label, target, lx, ly, lw, lh in page_links(rect, win.state["page"], d):
        if lx <= px < lx + lw and ly <= py < ly + lh:
            _navigate(win, target)
            return True

    return True


def make_app():
    return {
        "kind": "ie",
        "title": "Internet Explorer",
        "size": (560, 400),
        "init": init_fn,
        "draw": draw_fn,
        "click": click_fn,
        "icon16": icon16,
        "icon48": icon48,
        "desktop": True,
        "start": True,
    }


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
    cv = Canvas(); spec["draw"](cv, d, w)
    spec["icon16"](cv, 0, 0); spec["icon48"](cv, 60, 0)
    bx, by, bw, bh = w.body_rect()
    # click somewhere in the page area to try to follow a link
    spec["click"](w, bx + 40, by + 120, d, 0)
    spec["draw"](cv, d, w)
    print("ie smoke ok: lines=%d url=%s" % (len(cv.lines), w.state.get("url")))
