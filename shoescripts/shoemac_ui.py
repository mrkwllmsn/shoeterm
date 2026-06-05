# shoemac_ui - shared drawing primitives for shoemac and its app modules.
#
# This is the Snow Leopard (Mac OS X 10.6 / Aqua) counterpart to shoexp_ui.
# It holds the bits every shoemac app needs: the Aqua colour palette, the
# colour-mixing helpers, the human-readable size formatter, the `Canvas`
# drawing-command buffer that emits one comma-delimited foot vector-graphics
# program per frame, and the filesystem scan model (Entry/Pane) that the Finder
# app walks the real disk with.
#
# The math/format helpers and the Canvas come straight from shoexp_ui (no point
# duplicating them); only the palette and the Pane model are local, because the
# chrome is reskinned and Finder is a module here (in shoexp the explorer was
# built into the main script, so Entry/Pane lived there).
#
# shoemac imports these, and so does each separate app file
# (shoemac_finder.py, shoemac_calc.py, ...), which keeps the apps out of the
# main script without a circular import.

import os
import stat

# Re-use the proven primitives from the XP build.  ESC + Canvas + the colour
# math are theme-neutral, so we import rather than copy them.
from shoexp_ui import ESC, mix, lighten, darken, human, sanitize, Canvas  # noqa: F401

# --------------------------------------------------------------------------- #
#  palette (Aqua / Snow Leopard)
# --------------------------------------------------------------------------- #
C = {
    # ----- Aurora wallpaper ------------------------------------------------ #
    "wp0":      "#0b1026",   # sky, top (deep indigo)
    "wp1":      "#2a1b4a",   # sky, mid (violet)
    "wp2":      "#112233",   # sky, near bottom (a cold hint)
    "aur0":     "#4fe0d0aa",  # aurora ribbon, cyan (translucent)
    "aur1":     "#c060ffaa",  # aurora ribbon, magenta (translucent)
    "aur2":     "#7fffd4aa",  # aurora ribbon, mint (translucent)
    "star":     "#ffffffcc",

    # ----- window chrome (brushed aluminium) ------------------------------- #
    "win":      "#ececec",   # window body grey
    "winframe": "#9a9a9a",   # window frame line
    "winframei": "#bdbdbd",  # inactive frame line
    "ttl0":     "#f5f5f5",   # active title gradient, top (light)
    "ttl1":     "#d6d6d6",   # active title gradient, bottom (darker)
    "ttl0i":    "#f3f3f3",   # inactive title gradient, top
    "ttl1i":    "#e2e2e2",   # inactive title gradient, bottom
    "ttltxt":   "#3a3a3a",   # active title text
    "ttltxti":  "#9a9a9a",   # inactive title text
    "ttlsep":   "#bcbcbc",   # hairline under the title bar

    # ----- traffic lights -------------------------------------------------- #
    "tlclose":  "#ff5f57",
    "tlmin":    "#febc2e",
    "tlzoom":   "#28c840",
    "tlcloser": "#e0443e",   # darker rings
    "tlminr":   "#dd9d1f",
    "tlzoomr":  "#1aaa2f",
    "tlgloss":  "#ffffffaa",  # specular highlight
    "tloff":    "#cfcfcf",   # desaturated (window not focused)
    "tloffr":   "#b3b3b3",
    "tlglyph":  "#5a3a00",   # the x / - / + ink (dark, drawn on the light)

    # ----- menu bar -------------------------------------------------------- #
    "menubg":   "#f6f6f6e6",  # translucent light bar
    "menuline": "#0000001f",  # faint bottom hairline
    "menuink":  "#1a1a1a",
    "menuhi":   "#1f6fe5",    # highlighted-menu blue
    "menuhitxt": "#ffffff",

    # ----- Aqua selection -------------------------------------------------- #
    "sel0":     "#3a93ff",   # selection gradient, top
    "sel1":     "#1f6fe0",   # selection gradient, bottom
    "seltxt":   "#ffffff",

    # ----- dock ------------------------------------------------------------ #
    "dock":     "#20242caa",  # translucent dark glass shelf
    "dockline": "#ffffff33",  # top hairline / sheen
    "dockdot":  "#ffffffcc",  # "running" indicator dot
    "docksep":  "#ffffff33",  # separator line

    # ----- Finder / files -------------------------------------------------- #
    "sidebar":  "#dde4ec",   # Finder source-list background
    "dir":      "#6fa8e0",   # folder blue
    "diredge":  "#4f86bf",   # folder tab/edge
    "file":     "#dfe3ea",   # plain file
    "fileink":  "#2a3a52",   # list-row ink
    "exec":     "#7ed957",   # executable accent
    "link":     "#b69bff",   # symlink accent

    # ----- common ink / surfaces ------------------------------------------- #
    "ink":      "#1d1d1f",
    "dim":      "#6e6e73",
    "white":    "#ffffff",
    "sunken":   "#ffffff",
    "sunkenbd": "#b7b7b7",
    "iconlbl":  "#ffffff",
    "iconsel":  "#ffffff44",
    "shadow":   "#00000055",
}


# --------------------------------------------------------------------------- #
#  filesystem model (ported from shoexp/slippers so Finder can import it)
# --------------------------------------------------------------------------- #
class Entry:
    __slots__ = ("name", "path", "is_dir", "is_link", "is_exec", "size")

    def __init__(self, name, path, st, is_link):
        self.name = name
        self.path = path
        self.is_link = is_link
        self.is_dir = stat.S_ISDIR(st.st_mode) if st else False
        self.is_exec = bool(st and (st.st_mode & 0o111) and not self.is_dir)
        self.size = st.st_size if st else 0


class Pane:
    def __init__(self, path):
        self.cwd = os.path.abspath(path)
        self.sel = 0
        self.top = 0
        self.entries = []
        self.scan()

    def scan(self, keep=None):
        items = []
        parent = os.path.dirname(self.cwd)
        if parent != self.cwd:
            try:
                items.append(Entry("..", parent, os.stat(parent), False))
            except OSError:
                items.append(Entry("..", parent, None, False))
        try:
            with os.scandir(self.cwd) as it:
                for de in it:
                    try:
                        st = de.stat(follow_symlinks=True)
                    except OSError:
                        st = None
                    items.append(Entry(de.name, de.path, st, de.is_symlink()))
        except OSError:
            pass
        rest = [e for e in items if e.name != ".."]
        rest.sort(key=lambda e: (not e.is_dir, e.name.lower()))
        self.entries = ([items[0]] if items and items[0].name == ".." else []) + rest
        self.sel = 0
        self.top = 0
        if keep:
            for i, e in enumerate(self.entries):
                if e.name == keep:
                    self.sel = i
                    break

    def cur(self):
        return self.entries[self.sel] if self.entries else None

    def clamp(self, visible):
        if self.sel < 0:
            self.sel = 0
        if self.sel >= len(self.entries):
            self.sel = max(0, len(self.entries) - 1)
        if visible > 0:
            if self.sel < self.top:
                self.top = self.sel
            elif self.sel >= self.top + visible:
                self.top = self.sel - visible + 1
            maxtop = max(0, len(self.entries) - visible)
            self.top = max(0, min(self.top, maxtop))

    def enter(self):
        e = self.cur()
        if e and e.is_dir:
            try:
                os.listdir(e.path)
            except OSError:
                return
            self.cwd = os.path.abspath(e.path)
            self.scan()

    def up(self):
        parent = os.path.dirname(self.cwd)
        if parent != self.cwd:
            leaving = os.path.basename(self.cwd)
            self.cwd = parent
            self.scan(keep=leaving)
