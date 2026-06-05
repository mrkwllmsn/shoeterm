# shoexp_ui - shared drawing primitives for shoexp and its app modules.
#
# This holds the bits every shoexp app needs: the Luna colour palette, the
# colour-mixing helpers, the human-readable size formatter and the `Canvas`
# drawing-command buffer that emits one comma-delimited foot vector-graphics
# program per frame.  shoexp.py imports these, and so does each separate app
# file (shoexp_minesweeper.py, shoexp_notepad.py, ...), which keeps the apps
# out of the main script without a circular import.

ESC = "\033"

# --------------------------------------------------------------------------- #
#  palette (Luna blue, give or take)
# --------------------------------------------------------------------------- #
C = {
    "sky0":     "#1f6fe5",   # wallpaper sky, top
    "sky1":     "#3f8ff0",   # wallpaper sky, mid
    "sky2":     "#a9d6ff",   # wallpaper sky, near horizon
    "hill0":    "#9ccb50",   # hill crest highlight
    "hill1":    "#6ba83a",   # hill body
    "hill2":    "#3f7d27",   # hill shadow, bottom
    "cloud":    "#ffffffcc",

    "tb0":      "#3f8df4",   # taskbar gradient, top
    "tb1":      "#1c50c9",   # taskbar gradient, bottom
    "tbhi":     "#7fb6ff",   # taskbar top highlight line
    "tray0":    "#1b53c9",   # tray well, top
    "tray1":    "#1142a8",   # tray well, bottom

    "start0":   "#5bbf3a",   # start button, top
    "start1":   "#2f7d28",   # start button, bottom
    "starttxt": "#ffffff",

    "win":      "#ece9d8",   # XP window beige
    "winframe": "#0831d9",   # active window frame blue
    "winframei": "#9bb4d6",  # inactive frame
    "ttl0":     "#3b8bf0",   # active title bar, top
    "ttl1":     "#1c50c9",   # active title bar, bottom
    "ttl0i":    "#9cb6df",   # inactive title bar, top
    "ttl1i":    "#7f9cc8",   # inactive title bar, bottom
    "ttltxt":   "#ffffff",
    "closebtn": "#e0492f",
    "closehi":  "#ff7a5f",
    "ctrlbtn":  "#4f93f2",
    "ctrlhi":   "#8fbcfb",

    "ink":      "#10243f",
    "dim":      "#5a6b86",
    "white":    "#ffffff",
    "sunken":   "#ffffff",
    "sunkenbd": "#7f9db9",
    "selrow0":  "#3a93ff",
    "selrow1":  "#1f6fe0",

    "dir":      "#f6c344",   # folder yellow
    "diredge":  "#caa01f",
    "file":     "#dfe3ea",
    "fileink":  "#2a3a52",
    "exec":     "#7ed957",
    "link":     "#b69bff",

    "iconlbl":  "#ffffff",
    "iconsel":  "#3a6ea5aa",
    "shadow":   "#00000040",
}


def _rgb(c):
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mix(a, b, t):
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return "#%02x%02x%02x" % (int(ra + (rb - ra) * t),
                              int(ga + (gb - ga) * t),
                              int(ba + (bb - ba) * t))


def lighten(c, t):
    return mix(c, "#ffffff", t)


def darken(c, t):
    return mix(c, "#000000", t)


def human(n):
    n = float(n)
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024 or unit == "T":
            if unit == "B":
                return "%d B" % int(n)
            return "%.1f %s" % (n, unit)
        n /= 1024.0


def sanitize(s):
    return "".join(ch for ch in s if ch >= " " and ch != "," and ch != "\x7f")


# --------------------------------------------------------------------------- #
#  drawing-command buffer  (same discipline as slippers: comma-join geometry,
#  flush before every text because `text` runs to end of line)
# --------------------------------------------------------------------------- #
class Canvas:
    def __init__(self, textmode=None):
        self.lines = []
        self.geo = []
        # Optional "pixel" / "pixel <scale>" to render `text` with the embedded
        # 8x16 bitmap font instead of the default antialiased fcft font. None
        # keeps the default smooth font (so existing callers are unaffected).
        self.textmode = textmode

    def _flush(self):
        if self.geo:
            self.lines.append(",".join(self.geo))
            self.geo = []

    def cmd(self, s):
        self.geo.append(s)

    def pen(self, color):
        self.geo.append("pen " + color)

    def thickness(self, n):
        self.geo.append("thickness %d" % n)

    def clip(self, x, y, w, h):
        self.geo.append("clip %d %d %d %d" % (x, y, w, h))

    def noclip(self):
        self.geo.append("noclip")

    def rectf(self, x, y, w, h):
        self.geo.append("rectf %d %d %d %d" % (x, y, w, h))

    def rect(self, x, y, w, h):
        self.geo.append("rect %d %d %d %d" % (x, y, w, h))

    def rrectf(self, x, y, w, h, r):
        self.geo.append("rrectf %d %d %d %d %d" % (x, y, w, h, r))

    def rrect(self, x, y, w, h, r):
        self.geo.append("rrect %d %d %d %d %d" % (x, y, w, h, r))

    def line(self, x0, y0, x1, y1):
        self.geo.append("line %d %d %d %d" % (x0, y0, x1, y1))

    def trif(self, x0, y0, x1, y1, x2, y2):
        self.geo.append("trif %d %d %d %d %d %d" % (x0, y0, x1, y1, x2, y2))

    def circf(self, cx, cy, r):
        self.geo.append("circf %d %d %d" % (cx, cy, r))

    def circ(self, cx, cy, r):
        self.geo.append("circ %d %d %d" % (cx, cy, r))

    def arc(self, cx, cy, r, a0, a1):
        self.geo.append("arc %d %d %d %d %d" % (cx, cy, r, a0, a1))

    def polyf(self, pts):
        self.geo.append("polyf " + " ".join("%d" % v for v in pts))

    def bezier(self, x0, y0, x1, y1, x2, y2, x3, y3):
        self.geo.append("bezier %d %d %d %d %d %d %d %d" %
                        (x0, y0, x1, y1, x2, y2, x3, y3))

    def vgrad(self, x, y, w, h, c0, c1, steps=18):
        if w <= 0 or h <= 0:
            return
        steps = max(1, min(steps, h))
        for i in range(steps):
            y0 = y + h * i // steps
            y1 = y + h * (i + 1) // steps
            if y1 <= y0:
                continue
            self.pen(mix(c0, c1, i / max(1, steps - 1)))
            self.rectf(x, y0, w, y1 - y0)

    def text(self, x, y, s):
        self._flush()
        self.lines.append("text %d %d %s" % (x, y, sanitize(s)))

    def dcs(self, cols, rows, bg):
        self._flush()
        body = "\n".join(self.lines)
        tm = ("textmode %s\n" % self.textmode) if self.textmode else ""
        return "%s[H%sP>g\nsize %d %d\nbg %s\n%s%s\n%s\\" % (
            ESC, ESC, cols, rows, bg, tm, body, ESC)
