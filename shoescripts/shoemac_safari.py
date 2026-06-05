# shoemac_safari - a (lovingly fake) Safari 4 for the shoemac desktop.
#
# Self-contained app module: `make_app()` returns the spec dict shoemac uses to
# register an app (window draw/click + Dock/desktop icons).  There is no real
# networking -- the browser navigates between a handful of canned "pages" keyed
# by id, and clicking an underlined link pushes the current page onto the Back
# history and loads the target page.  (The page model + Back/Forward stacks are
# ported straight from the XP build's Internet Explorer; only the chrome is
# reskinned to the Snow Leopard Safari look.)
#
# All chrome is drawn from foot vector-graphics primitives via the shared
# Canvas.  Text is ASCII-only (a vector `text` truncates at the first glyph the
# font lacks), so the blue Safari compass is built from concentric circles and a
# two-triangle needle rather than any unicode mark.

from shoemac_ui import C, mix, lighten, darken  # noqa: F401


# --------------------------------------------------------------------------- #
#  palette (local to the Safari skin; the shared C palette is the Aqua window
#  theme, this adds the brushed-metal toolbar + compass colours)
# --------------------------------------------------------------------------- #
COMPASS_BLUE = "#2f6fd0"     # compass body
COMPASS_RING = "#1b4ea0"     # compass outer ring / edge
COMPASS_FACE = "#e8f2ff"     # compass dial face
COMPASS_RED = "#d6402f"      # needle, north half
COMPASS_WHITE = "#ffffff"    # needle, south half
METAL0 = "#fcfcfc"           # brushed-metal toolbar, top
METAL1 = "#c6c6c6"           # brushed-metal toolbar, bottom
METAL_EDGE = "#9a9a9a"       # toolbar hairline
LINK = "#1a4fbf"             # underlined-link blue
HOME_HDR0 = "#7fa8d8"        # start-page header gradient, top
HOME_HDR1 = "#3a6aa8"        # start-page header gradient, bottom


# --------------------------------------------------------------------------- #
#  the blue Safari compass, drawn from primitives
# --------------------------------------------------------------------------- #
def _draw_compass(cv, cx, cy, r):
    """Draw the Safari compass centred at (cx,cy) with radius ~r."""
    ri = max(4, int(r))
    # chrome bezel + blue body
    cv.pen(COMPASS_RING)
    cv.circf(cx, cy, ri)
    cv.pen(COMPASS_BLUE)
    cv.circf(cx, cy, max(1, ri - 1))
    # recessed dial face (light) with a thin blue rim left showing
    cv.pen(COMPASS_FACE)
    cv.circf(cx, cy, max(1, ri * 3 // 4))
    # four cardinal tick marks (drawn, not lettered -- glyphs would truncate)
    cv.pen(COMPASS_RING)
    t = max(1, ri // 6)
    cv.line(cx, cy - ri + 1, cx, cy - ri + 1 + t)            # N
    cv.line(cx, cy + ri - 1, cx, cy + ri - 1 - t)            # S
    cv.line(cx - ri + 1, cy, cx - ri + 1 + t, cy)            # W
    cv.line(cx + ri - 1, cy, cx + ri - 1 - t, cy)            # E
    # needle: an elongated diamond split along its short axis.  NE tip + SW tip
    # are the long points; NW/SE are the short side points.  Red = north half,
    # white = south half -- the classic compass needle.
    nl = max(2, ri * 3 // 4)
    s = max(1, ri // 3)
    ne = (cx + nl, cy - nl)
    sw = (cx - nl, cy + nl)
    nw = (cx - s, cy - s)
    se = (cx + s, cy + s)
    cv.pen(COMPASS_RED)
    cv.trif(ne[0], ne[1], nw[0], nw[1], se[0], se[1])
    cv.pen(COMPASS_WHITE)
    cv.trif(sw[0], sw[1], nw[0], nw[1], se[0], se[1])
    # hub
    cv.pen(COMPASS_RING)
    cv.circf(cx, cy, max(1, ri // 6))


def icon16(cv, x, y):
    _draw_compass(cv, x + 8, y + 8, 7)


def icon48(cv, cx, top):
    # ~40px Dock/desktop icon, centred on cx, top edge at y=top
    r = 18
    _draw_compass(cv, cx, top + r + 2, r)


# --------------------------------------------------------------------------- #
#  page registry
# --------------------------------------------------------------------------- #
# Each page is keyed by an id.  draw_page() renders it; page_links() yields the
# clickable-link geometry (shared by draw + click so hit-boxes mirror the text).
PAGES = {
    "start": {
        "url": "http://www.apple.com/",
        "title": "Apple",
        "kind": "home",
        "links": [
            ("Mac OS X Snow Leopard - learn more", "search"),
            ("Switch to a Mac in five easy steps", "search"),
            ("Download the latest Safari today", "search"),
            ("Find a Genius Bar near you", "search"),
        ],
    },
    "search": {
        "url": "http://www.google.com/search?q=mac",
        "title": "Search Results",
        "kind": "search",
        "links": [
            ("Apple - Start Page", "start"),
            ("Safari 4 - the worlds fastest browser", "about"),
            ("Aqua interface design, explained", "start"),
            ("Snow Leopard release notes", "search"),
            ("Dashboard widgets worth installing", "about"),
        ],
    },
    "about": {
        "url": "about:blank",
        "title": "Safari Cant Open the Page",
        "kind": "error",
        "links": [
            ("Go to the Apple start page", "start"),
        ],
    },
}
START_PAGE = "start"


# --------------------------------------------------------------------------- #
#  unified brushed-metal toolbar layout (geometry shared by draw + click)
# --------------------------------------------------------------------------- #
TOOL_H = 40      # single unified toolbar strip height (Safari has no second bar)


def _nav_buttons(bx, by):
    """Return [(key, cx, cy, r), ...] for the round back/forward buttons."""
    cy = by + TOOL_H // 2
    r = 11
    return [
        ("back", bx + 10 + r, cy, r),
        ("fwd", bx + 10 + r + (r * 2 + 4) + r, cy, r),
    ]


def _addr_field(bx, by, bw):
    """Return (fx, fy, fw, fh) for the rounded address field."""
    fh = 24
    fy = by + (TOOL_H - fh) // 2
    fx = bx + 10 + (11 * 2) + 4 + (11 * 2) + 12
    fw = (bx + bw - 12) - fx
    return fx, fy, fw, fh


# --------------------------------------------------------------------------- #
#  toolbar glyphs
# --------------------------------------------------------------------------- #
def _nav_circle(cv, key, cx, cy, r, enabled):
    """A round metal back/forward button with a chevron triangle."""
    cv.pen(METAL_EDGE)
    cv.circf(cx, cy, r)
    cv.pen(lighten(METAL0, 0.0) if enabled else lighten(C["win"], 0.2))
    cv.circf(cx, cy, max(1, r - 1))
    # top sheen
    cv.pen(C["white"])
    cv.arc(cx, cy, r - 2, 200, 340)
    # chevron
    g = C["ink"] if enabled else C["dim"]
    cv.pen(g)
    if key == "back":
        cv.trif(cx - 4, cy, cx + 3, cy - 5, cx + 3, cy + 5)
    else:
        cv.trif(cx + 4, cy, cx - 3, cy - 5, cx - 3, cy + 5)


def _reload_glyph(cv, cx, cy, enabled):
    """A small circular-arrow reload glyph (sits at the right of the field)."""
    g = C["dim"] if enabled else lighten(C["dim"], 0.3)
    cv.pen(g)
    cv.thickness(2)
    cv.arc(cx, cy, 6, 300, 200)
    cv.thickness(1)
    cv.trif(cx + 6, cy - 7, cx + 6, cy + 1, cx + 1, cy - 3)


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
    if kind == "home":
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

    if kind == "home":
        # blue header band with an Apple wordmark + a small compass mark
        cv.vgrad(bx, by, bw, 40, HOME_HDR0, HOME_HDR1, 8)
        cv.pen("#ffffff")
        cv.text(bx + 14, by + 27, "Apple")
        # small compass to the right of the wordmark
        _draw_compass(cv, bx + 14 + 5 * d.charw + 14, by + 20, 9)
        cv.pen("#dfeaf7")
        cv.text(bx + bw - 18 * d.charw, by + 27, "Store  Mac  iPod  Support")
        # search box (sunken)
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
                 lighten(HOME_HDR0, 0.2), HOME_HDR1, 4)
        cv.pen("#ffffff")
        cv.text(bx + 12 + sw + 10, sy + 14, "Go")
        # headline links
        for label, target, lx, ly, lw, lh in page_links(rect, page_id, d):
            _draw_link_row(cv, d, lx, ly + 12, label)
        # two colored content tiles along the bottom
        ty = by + bh - 60
        tw = (bw - 36) // 2
        cv.vgrad(bx + 12, ty, tw, 48, "#dff0ff", "#a8cdf0", 6)
        cv.pen(darken("#a8cdf0", 0.3))
        cv.rect(bx + 12, ty, tw, 48)
        cv.pen(C["ink"])
        cv.text(bx + 20, ty + 18, "Top Sites")
        cv.text(bx + 20, ty + 36, "Your favourites")
        cv.vgrad(bx + 24 + tw, ty, tw, 48, "#fbe7a0", "#f3c64a", 6)
        cv.pen(darken("#f3c64a", 0.3))
        cv.rect(bx + 24 + tw, ty, tw, 48)
        cv.pen(C["ink"])
        cv.text(bx + 32 + tw, ty + 18, "Bookmarks")
        cv.text(bx + 32 + tw, ty + 36, "Reading list")

    elif kind == "search":
        cv.vgrad(bx, by, bw, 30, "#eef4ff", "#dbe7fb", 6)
        cv.pen(COMPASS_BLUE)
        cv.text(bx + 12, by + 20, "Web Search")
        cv.pen(C["dim"])
        cv.text(bx + 12, by + 40, "Results 1-5 of about 1,000,000")
        for label, target, lx, ly, lw, lh in page_links(rect, page_id, d):
            _draw_link_row(cv, d, lx, ly + 12, label)
            cv.pen("#1a8a1a")
            url_label = PAGES.get(target, {}).get("url", "http://www.apple.com/")
            cv.text(lx, ly + 26, url_label)

    elif kind == "error":
        # Safari's "can't open the page" sheet
        cv.pen(C["ink"])
        cv.text(bx + 16, by + 30, "Safari can't open the page.")
        cv.pen(C["dim"])
        cv.text(bx + 16, by + 56,
                "Safari can't open the page because it could")
        cv.text(bx + 16, by + 72,
                "not connect to the server. You may need to")
        cv.text(bx + 16, by + 88,
                "check your network connection and try again.")
        # warning glyph (drawn triangle + bang, no unicode)
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
    win.title = page["title"]


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

    # --- unified brushed-metal toolbar -----------------------------------
    cv.vgrad(bx, by, bw, TOOL_H, METAL0, METAL1, 6)
    cv.pen(METAL_EDGE)
    cv.line(bx, by + TOOL_H - 1, bx + bw, by + TOOL_H - 1)

    # round back / forward buttons
    enabled = {"back": bool(win.state["back"]), "fwd": bool(win.state["fwd"])}
    for key, cx, cy, r in _nav_buttons(bx, by):
        _nav_circle(cv, key, cx, cy, r, enabled.get(key, True))

    # address field (rounded, with compass favicon + reload glyph)
    fx, fy, fw, fh = _addr_field(bx, by, bw)
    cv.pen(C["white"])
    cv.rrectf(fx, fy, fw, fh, fh // 2)
    cv.pen(C["sunkenbd"])
    cv.rrect(fx, fy, fw, fh, fh // 2)
    # compass favicon at the left of the field
    _draw_compass(cv, fx + 13, fy + fh // 2, 7)
    # the URL text, truncated to the field width
    url = win.state["url"]
    txt_x = fx + 26
    maxc = max(4, (fw - 26 - 20) // d.charw)
    shown = url if len(url) <= maxc else url[:maxc - 1] + "~"
    cv.pen(C["ink"])
    cv.text(txt_x, fy + fh - 8, shown)
    # reload glyph at the right of the field
    _reload_glyph(cv, fx + fw - 14, fy + fh // 2, True)

    # --- page area (sunken white) ----------------------------------------
    pax = bx + 2
    pay = by + TOOL_H + 2
    paw = bw - 4
    pah = bh - TOOL_H - 4
    if pah < 10:
        pah = 10
    cv.pen(C["sunkenbd"])
    cv.rect(pax - 1, pay - 1, paw + 2, pah + 2)
    draw_page(cv, d, (pax, pay, paw, pah), win.state["page"])


def click_fn(win, px, py, d, btn):
    if btn != 0:
        return False
    bx, by, bw, bh = win.body_rect()

    # round back / forward buttons (hit-test by distance from centre)
    for key, cx, cy, r in _nav_buttons(bx, by):
        if (px - cx) ** 2 + (py - cy) ** 2 <= r * r:
            if key == "back":
                _go_back(win)
            else:
                _go_fwd(win)
            return True

    # address field / reload are cosmetic; swallow clicks inside the toolbar
    fx, fy, fw, fh = _addr_field(bx, by, bw)
    if fx <= px < fx + fw and fy <= py < fy + fh:
        return True

    # page links
    pax = bx + 2
    pay = by + TOOL_H + 2
    paw = bw - 4
    pah = bh - TOOL_H - 4
    rect = (pax, pay, paw, pah)
    for label, target, lx, ly, lw, lh in page_links(rect, win.state["page"], d):
        if lx <= px < lx + lw and ly <= py < ly + lh:
            _navigate(win, target)
            return True

    return True


def make_app():
    return {
        "kind": "safari",
        "title": "Safari",
        "size": (560, 400),
        "init": init_fn,
        "draw": draw_fn,
        "click": click_fn,
        "icon16": icon16,
        "icon48": icon48,
        "dock": True,
    }


if __name__ == "__main__":
    from shoemac_ui import Canvas

    class _W:
        def __init__(s, kind, size):
            s.x, s.y = 40, 40
            s.w, s.h = size
            s.kind = kind
            s.title = ""
            s.id = 1
            s.state = {}
            s.open_path = None

        def body_rect(s):
            return (s.x + 3, s.y + 22, s.w - 6, s.h - 22 - 4)

    class _D:
        charw = 8
        W = 1280
        H = 768

    spec = make_app()
    w = _W(spec["kind"], spec["size"])
    spec["init"](w)
    d = _D()
    cv = Canvas()
    spec["draw"](cv, d, w)
    spec["icon16"](cv, 0, 0)
    spec["icon48"](cv, 60, 0)
    bx, by, bw, bh = w.body_rect()
    # click a page link, then go back
    spec["click"](w, bx + 40, by + TOOL_H + 100, d, 0)
    spec["click"](w, bx + 21, by + TOOL_H // 2, d, 0)
    spec["draw"](cv, d, w)
    print("safari smoke ok: lines=%d url=%s" % (len(cv.lines), w.state.get("url")))
