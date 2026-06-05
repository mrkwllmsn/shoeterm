# shoemac_about - the Snow Leopard "About This Mac" panel for the shoemac desktop.
#
# Self-contained app module: make_app() returns the spec dict the host consumes
# (it calls register_app(make_app()) in _load_apps).  This is the Aqua reskin of
# shoexp's built-in "My Computer": the real disk-usage bar (shutil.disk_usage +
# human()) and the drive-row idiom are ported over, but instead of a list of
# drives we present the single classic "About This Mac" card -- a faux Apple
# logo, the "Mac OS X" heading, a version line, a decorative "Software Update..."
# button, then Processor / Memory / Startup Disk info rows (the Startup Disk row
# keeps the real capacity bar from My Computer, pointed at "/").
#
# Processor / memory are read once at init from /proc (with graceful fallbacks);
# the disk bar is sampled every frame like My Computer so it stays live.  All
# labels are plain ASCII (a vector `text` halts at the first missing glyph) and
# the Apple mark is drawn from primitives.

import os
import shutil

from shoemac_ui import C, mix, lighten, darken, human  # noqa: F401

# Window is small and fixed -- the About card is a compact centred panel.
WIN_W, WIN_H = 340, 350

# Local greys for the panel surface and the brushed Apple mark.  The shared C
# palette is the window chrome theme; these are card-local accents.
ABOUT = {
    "panel0":  "#f7f7f7",   # card gradient, top (soft aqua white)
    "panel1":  "#e8e8e8",   # card gradient, bottom
    "rule":    "#cfcfcf",   # hairline rule
    "apple0":  "#9a9a9a",   # Apple mark, top
    "apple1":  "#6f6f6f",   # Apple mark, bottom
    "btn0":    "#fdfdfd",   # Software Update button, top gloss
    "btn1":    "#dcdcdc",   # button, bottom
    "btnbd":   "#a9a9a9",   # button outline
    "btnink":  "#2a2a2a",
}


def make_app():
    return {
        "kind": "about",
        "title": "About This Mac",
        "size": (WIN_W, WIN_H),
        "init": about_init,
        "draw": draw_about,
        "icon16": icon16,
        "icon48": icon48,
        "dock": True,
    }


# ----- state --------------------------------------------------------------- #
def about_init(win):
    # Processor / memory are effectively static, so read them once.  Disk usage
    # is sampled per-frame in draw() (cheap, and keeps the bar live).
    win.state = {"cpu": _cpu_name(), "mem": _mem_total()}
    win.title = "About This Mac"


def _cpu_name():
    # Linux: the first "model name" line of /proc/cpuinfo; else fall back to the
    # platform module so the row is never blank.
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    try:
        import platform
        return platform.processor() or platform.machine() or "Unknown"
    except Exception:                                  # noqa: BLE001
        return "Unknown"


def _mem_total():
    # Total physical RAM in bytes (MemTotal is in kB), 0 if unavailable.
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return 0


# ----- draw ----------------------------------------------------------------- #
def draw_about(cv, d, win):
    bx, by, bw, bh = win.body_rect()

    # card surface (fills our own background, as the contract requires)
    cv.vgrad(bx, by, bw, bh, ABOUT["panel0"], ABOUT["panel1"], 14)

    cxc = bx + bw // 2                       # horizontal centre of the panel

    def centre(y, s, color):
        cv.pen(color)
        cv.text(cxc - len(s) * d.charw // 2, y, s)

    # ----- Apple mark ------------------------------------------------------- #
    _apple(cv, cxc, by + 44, 22, ABOUT["panel0"])

    # ----- heading + version ----------------------------------------------- #
    centre(by + 92, "Mac OS X", C["ink"])
    centre(by + 112, "Version 10.6.8", C["dim"])

    # ----- "Software Update..." button (decorative) ------------------------- #
    label = "Software Update..."
    btn_w = max(150, len(label) * d.charw + 28)
    btn_h = 22
    btn_x = cxc - btn_w // 2
    btn_y = by + 126
    cv.vgrad(btn_x, btn_y, btn_w, btn_h, ABOUT["btn0"], ABOUT["btn1"], 6)
    cv.pen("#ffffffaa")                       # top sheen
    cv.line(btn_x + 6, btn_y + 1, btn_x + btn_w - 6, btn_y + 1)
    cv.pen(ABOUT["btnbd"])
    cv.rrect(btn_x, btn_y, btn_w, btn_h, 5)
    cv.pen(ABOUT["btnink"])
    cv.text(cxc - len(label) * d.charw // 2, btn_y + btn_h - 7, label)

    # ----- hairline rule ---------------------------------------------------- #
    rule_y = btn_y + btn_h + 14
    cv.pen(ABOUT["rule"])
    cv.rectf(bx + 24, rule_y, bw - 48, 1)

    # ----- info rows -------------------------------------------------------- #
    lab_x = bx + 28
    val_x = bx + 132
    val_max = (bx + bw - 12) - val_x         # px available for a value string
    ry = rule_y + 24

    def row(label, value):
        cv.pen(C["dim"])
        cv.text(lab_x, ry, label)
        cv.pen(C["ink"])
        cv.text(val_x, ry, _fit(value, val_max, d.charw))

    cpu = win.state.get("cpu") or "Unknown"
    row("Processor", cpu)

    ry += 26
    mem = win.state.get("mem") or 0
    row("Memory", human(mem) if mem else "Unknown")

    # Startup Disk: keep the real My Computer capacity bar, pointed at "/".
    ry += 26
    cv.pen(C["dim"])
    cv.text(lab_x, ry, "Startup Disk")
    try:
        du = shutil.disk_usage("/")
        frac = (du.used / du.total) if du.total else 0.0
        info = "%s free of %s" % (human(du.free), human(du.total))
    except OSError:
        frac = 0.0
        info = "unavailable"
    bar_x, bar_y = val_x, ry - 9
    bar_w = (bx + bw - 12) - bar_x
    cv.pen("#d7dde6")
    cv.rrectf(bar_x, bar_y, bar_w, 9, 3)
    fillw = max(2, int(bar_w * frac))
    col0, col1 = ("#3a93ff", "#1f6fe0")       # Aqua blue (My Computer's accent)
    if frac > 0.9:
        col0, col1 = ("#ff7a5f", "#e0492f")   # nearly full -> warn red
    cv.vgrad(bar_x, bar_y, fillw, 9, col0, col1, 4)
    cv.pen("#b7c0cd")
    cv.rrect(bar_x, bar_y, bar_w, 9, 3)
    cv.pen(C["dim"])
    cv.text(bar_x, ry + 16, info)


def _fit(s, max_px, charw):
    # Truncate a value string to the available pixel width (with an ellipsis).
    if charw <= 0:
        return s
    maxch = max(1, max_px // charw)
    if len(s) <= maxch:
        return s
    return s[:max(1, maxch - 3)] + "..."


# ----- Apple mark + icons --------------------------------------------------- #
def _apple(cv, cx, cy, r, bg):
    # A brushed-grey Apple silhouette built from primitives: a round body, a
    # stubby stem, a leaf, and the signature bite carved out of the right side
    # by overdrawing a circle in the background colour `bg`.
    body0, body1 = ABOUT["apple0"], ABOUT["apple1"]
    # stem (behind the body)
    cv.thickness(max(1, r // 9))
    cv.pen(darken(body1, 0.15))
    cv.line(cx, cy - r, cx + r // 4, cy - r - r // 2)
    cv.thickness(1)
    # body -- two stacked tones give it a touch of the glossy gradient look
    cv.pen(body0)
    cv.circf(cx, cy - r // 6, r)
    cv.pen(body1)
    cv.circf(cx, cy + r // 4, r - r // 8)
    # leaf (up and to the right of the stem)
    cv.pen(body0)
    cv.circf(cx + int(r * 0.42), cy - r - r // 6, max(2, int(r * 0.30)))
    # the bite: a bg-coloured circle on the right edge
    cv.pen(bg)
    cv.circf(cx + int(r * 0.98), cy - r // 8, max(2, int(r * 0.52)))


def _about_tile(cv, x, y, s):
    # An icon tile: a soft rounded silver plate with the grey Apple mark, so the
    # bite has a known background to carve against (Dock / desktop use).
    r = max(2, s // 6)
    plate = "#f2f2f2"
    cv.vgrad(x, y, s, s, "#fbfbfb", "#dadada", 6)
    cv.pen("#a9a9a9")
    cv.rrect(x, y, s, s, r)
    # centre the Apple mark within the plate
    cx = x + s // 2
    cy = y + s // 2 + max(1, s // 12)
    _apple(cv, cx, cy, max(3, int(s * 0.30)), plate)


def icon16(cv, x, y):
    _about_tile(cv, x, y, 16)


def icon48(cv, cx, top):
    s = 40
    _about_tile(cv, cx - s // 2, top, s)
