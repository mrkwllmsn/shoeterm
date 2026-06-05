# shoexp_music - a Windows-Media-Player-ish sound player for the fake-XP desktop.
#
# The shoexp cousin of shoemac's Music app, and the first shoexp app to drive a
# *real* background process: it plays actual audio files through an external CLI
# player (default `mpg321`, overridable with $SHOEXP_PLAYER).  Two control
# strategies, picked automatically -- the "hybrid" design borrowed wholesale
# from shoemac_music:
#
#   * REMOTE mode -- used when the player command is the bare `mpg321`/`mpg123`
#     binary.  We run it as `mpg321 -R -` (the generic remote-control protocol):
#     LOAD/PAUSE/STOP/JUMP/QUIT go in on stdin, and `@F frames secs ...` / `@P n`
#     status lines come back (on stderr, merged into stdout), giving real
#     elapsed time, true pause, a seekable progress bar, and end-of-track
#     detection.  One persistent process is reused across tracks.
#   * GENERIC mode -- any other command (e.g. `ffplay -nodisp -autoexit` or
#     `cvlc --play-and-exit {}`).  We spawn `<cmd> <file>` as a plain child in
#     its own session; pause/resume is OS-level SIGSTOP/SIGCONT, stop/next is
#     SIGTERM, elapsed time is a wall clock, end-of-track is the child exiting.
#     No seek; duration unknown.
#
# Source of music: double-click an audio file in the Explorer (it routes here,
# like images route to the picture viewer), and/or browse the filesystem in the
# window's own list and double-click a track.  Auto-advance walks the audio
# files of the current folder in order.
#
# The host gives us two registry hooks this app relies on: `tick(win, d)` (polled
# ~1/s off the main loop's select timeout -> animate the progress bar +
# auto-advance) and `close(win)` (teardown -> kill/quit the child).  All
# cv.text() is plain ASCII (a vector `text` aborts the DCS at the first
# non-ASCII byte); names go through sanitize() and transport glyphs are drawn
# shapes, never Unicode.

import os
import shlex
import signal
import stat
import subprocess
import time

from shoexp_ui import C, mix, lighten, darken, human, sanitize  # noqa: F401

WIN_W, WIN_H = 600, 430

# Extensions we treat as playable.  Kept in sync with shoexp's AUDIO_EXTS so the
# Explorer's double-click routing and this list agree on what "is audio".
AUDIO_EXTS = (
    ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".oga", ".opus", ".wav",
    ".wma", ".mpc", ".ape", ".aiff", ".aif",
)

# Player commands we know how to remote-control via the `-R -` protocol.  Any
# other command (or any command with extra args / a {} placeholder) falls back
# to the generic SIGSTOP/SIGCONT strategy.
REMOTE_BINS = ("mpg321", "mpg123")


def is_audio(path):
    return os.path.splitext(path)[1].lower() in AUDIO_EXTS


def make_app():
    return {
        "kind":    "music",
        "title":   "Windows Media Player",
        "size":    (WIN_W, WIN_H),
        "init":    mus_init,
        "draw":    mus_draw,
        "click":   mus_click,
        "key":     mus_key,
        "wheel":   mus_wheel,
        "tick":    mus_tick,
        "close":   mus_close,
        "icon16":  icon16,
        "icon48":  icon48,
        "desktop": True,
        "start":   True,
        "desktop_label": "Media Player",
        "start_label":   "Windows Media Player",
    }


# --------------------------------------------------------------------------- #
#  filesystem model (a compact Entry/Pane, mirroring shoexp's own -- kept local
#  so this module needn't import the shoexp main script)
# --------------------------------------------------------------------------- #
class Entry:
    __slots__ = ("name", "path", "is_dir", "size")

    def __init__(self, name, path, st):
        self.name = name
        self.path = path
        self.is_dir = stat.S_ISDIR(st.st_mode) if st else False
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
                items.append(Entry("..", parent, os.stat(parent)))
            except OSError:
                items.append(Entry("..", parent, None))
        try:
            with os.scandir(self.cwd) as it:
                for de in it:
                    if de.name.startswith("."):
                        continue
                    try:
                        st = de.stat(follow_symlinks=True)
                    except OSError:
                        st = None
                    items.append(Entry(de.name, de.path, st))
        except OSError:
            pass
        rest = [e for e in items if e.name != ".."]
        rest.sort(key=lambda e: (not e.is_dir, e.name.lower()))
        head = [items[0]] if items and items[0].name == ".." else []
        self.entries = head + rest
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


# --------------------------------------------------------------------------- #
#  local palette (WMP-blue accents over the shared Luna C palette)
# --------------------------------------------------------------------------- #
M = {
    "tb0":     "#dfeaf8",   # transport bar gradient, top
    "tb1":     "#9fbbe0",   # transport bar gradient, bottom
    "tbsep":   "#5a78a0",   # hairline under the transport bar
    "lcd0":    "#0b2b4a",   # the time/title "LCD" display, top (deep WMP blue)
    "lcd1":    "#06192e",   # display, bottom
    "lcdbd":   "#3a5f88",   # display bezel
    "lcdink":  "#9fe6ff",   # display text (cyan glow)
    "btn0":    "#fdfdfd",   # transport button gloss, top
    "btn1":    "#bcd0ee",   # button, bottom
    "btnbd":   "#6f8fbb",   # button outline
    "glyph":   "#1c3a63",   # transport glyph ink
    "glyphhi": "#1f7ae0",   # play glyph when playing
    "track0":  "#c4d2e6",   # progress trough, top
    "track1":  "#aabbd6",   # trough, bottom
    "fill0":   "#7fc0ff",   # progress fill, top
    "fill1":   "#1f7ae0",   # fill, bottom
    "knob":    "#ffffff",
    "knobbd":  "#1f6fe0",
    "rowalt":  "#f2f6fc",   # zebra row tint
    "rowsep":  "#e1e7f0",
    "noteink": "#1f4f9e",   # audio-row note glyph
    "pop0":    "#ffffef",   # gear popover, top
    "pop1":    "#eef0dd",   # popover, bottom
    "popbd":   "#b9b39a",
}

DBL_MS = 0.42             # double-click window (seconds)


# --------------------------------------------------------------------------- #
#  background player (hybrid remote / generic)  -- identical engine to shoemac
# --------------------------------------------------------------------------- #
def _player_cmd():
    return (os.environ.get("SHOEXP_PLAYER")
            or os.environ.get("SHOEMAC_PLAYER")
            or "mpg321").strip() or "mpg321"


class Player:
    """Owns at most one child process.  state is one of stopped/playing/paused.
    `ended` latches True when a track finishes on its own (consumed by the app to
    auto-advance); explicit stop()/play() never set it."""

    def __init__(self):
        cmd = _player_cmd()
        try:
            self.tokens = shlex.split(cmd) or ["mpg321"]
        except ValueError:
            self.tokens = ["mpg321"]
        base = os.path.basename(self.tokens[0])
        self.remote = (len(self.tokens) == 1 and base in REMOTE_BINS)
        self.cmd = cmd
        self.proc = None
        self.state = "stopped"
        self.ended = False
        self.err = None
        # remote status (seconds / frames)
        self.pos = 0.0
        self.dur = 0.0
        self._ftot = 0
        self._rbuf = b""
        self._user_stop = False     # guard so an explicit STOP's @P 0 != "ended"
        # generic timing (seconds)
        self._t0 = 0.0
        self._acc = 0.0

    # ---- spawning --------------------------------------------------------- #
    def _ensure_remote(self):
        if self.proc and self.proc.poll() is None:
            return True
        try:
            self.proc = subprocess.Popen(
                self.tokens + ["-R", "-"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, start_new_session=True)
        except OSError:
            self.err = "player not found: " + self.tokens[0]
            self.proc = None
            return False
        try:
            os.set_blocking(self.proc.stdout.fileno(), False)
        except (OSError, ValueError):
            pass
        self.err = None
        return True

    def _send(self, line):
        if not (self.proc and self.proc.stdin):
            return
        try:
            self.proc.stdin.write((line + "\n").encode())
            self.proc.stdin.flush()
        except (OSError, ValueError):
            pass

    def _generic_argv(self, path):
        if any(t == "{}" for t in self.tokens):
            return [path if t == "{}" else t for t in self.tokens]
        return self.tokens + [path]

    # ---- transport -------------------------------------------------------- #
    def play(self, path):
        self.ended = False
        self.err = None
        if self.remote:
            if not self._ensure_remote():
                return
            self._user_stop = False
            self._send("LOAD " + path)
            self.state = "playing"
            self.pos = 0.0
            self.dur = 0.0
            self._ftot = 0
        else:
            self._kill()            # stop whatever was playing
            try:
                self.proc = subprocess.Popen(
                    self._generic_argv(path),
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True)
            except OSError:
                self.err = "player not found: " + self.tokens[0]
                self.proc = None
                self.state = "stopped"
                return
            self.state = "playing"
            self._acc = 0.0
            self._t0 = time.monotonic()

    def toggle_pause(self):
        if self.state == "stopped":
            return
        if self.remote:
            self._send("PAUSE")
            self.state = "paused" if self.state == "playing" else "playing"
            return
        if not (self.proc and self.proc.poll() is None):
            return
        try:
            if self.state == "playing":
                os.killpg(self.proc.pid, signal.SIGSTOP)
                self._acc += time.monotonic() - self._t0
                self.state = "paused"
            else:
                os.killpg(self.proc.pid, signal.SIGCONT)
                self._t0 = time.monotonic()
                self.state = "playing"
        except OSError:
            pass

    def stop(self):
        if self.remote and self.proc and self.proc.poll() is None:
            self._user_stop = True
            self._send("STOP")
        else:
            self._kill()
        self.state = "stopped"
        self.pos = 0.0
        self._acc = 0.0

    def seek(self, frac):
        # absolute seek, remote mode only (we know the total frame count).
        if not self.remote or self._ftot <= 0:
            return
        frac = max(0.0, min(1.0, frac))
        self._send("JUMP %d" % int(frac * self._ftot))

    # ---- per-frame poll (called from the app's tick) ---------------------- #
    def poll(self):
        changed = False
        if self.remote:
            if self.proc is None:
                return False
            if self.proc.poll() is not None:        # remote process died
                self.proc = None
                self.state = "stopped"
                return True
            try:
                data = self.proc.stdout.read(8192)
            except (BlockingIOError, OSError):
                data = None
            if data:
                self._rbuf += data
                while b"\n" in self._rbuf:
                    line, self._rbuf = self._rbuf.split(b"\n", 1)
                    changed |= self._parse(line.decode("ascii", "replace"))
        else:
            if self.proc is not None and self.proc.poll() is not None:
                self.proc = None
                if self.state != "stopped":         # finished on its own
                    self.ended = True
                self.state = "stopped"
                changed = True
        return changed

    def _parse(self, line):
        line = line.strip()
        if line.startswith("@F "):
            p = line.split()
            try:
                f0, f1 = int(p[1]), int(p[2])
                self.pos = float(p[3])
                self.dur = self.pos + float(p[4])
                self._ftot = f0 + f1
            except (ValueError, IndexError):
                pass
            return True
        if line.startswith("@P "):
            n = line[3:].strip()
            if n in ("0", "3"):
                was_user = self._user_stop
                self._user_stop = False
                if self.state != "stopped" and (n == "3" or not was_user):
                    self.ended = True
                self.state = "stopped"
                return True
            if n == "1":
                self.state = "paused"
                return True
            if n == "2":
                self.state = "playing"
                return True
        return False

    # ---- timing readouts -------------------------------------------------- #
    def elapsed(self):
        if self.remote:
            return self.pos
        if self.state == "playing":
            return self._acc + (time.monotonic() - self._t0)
        return self._acc

    def duration(self):
        return self.dur if self.remote else 0.0

    # ---- teardown --------------------------------------------------------- #
    def _kill(self):
        if not (self.proc and self.proc.poll() is None):
            self.proc = None
            return
        try:
            os.killpg(self.proc.pid, signal.SIGCONT)   # wake if paused, so it dies
        except OSError:
            pass
        try:
            os.killpg(self.proc.pid, signal.SIGTERM)
        except OSError:
            pass
        try:
            self.proc.wait(timeout=0.5)
        except Exception:                               # noqa: BLE001
            pass
        self.proc = None

    def shutdown(self):
        if self.proc and self.proc.poll() is None:
            if self.remote:
                self._send("QUIT")
                try:
                    self.proc.wait(timeout=0.3)
                except Exception:                       # noqa: BLE001
                    pass
            self._kill()
        self.proc = None
        self.state = "stopped"


# --------------------------------------------------------------------------- #
#  state
# --------------------------------------------------------------------------- #
def _default_dir():
    music = os.path.expanduser("~/Music")
    return music if os.path.isdir(music) else os.path.expanduser("~")


def mus_init(win):
    start = getattr(win, "open_path", None)
    if start and os.path.isfile(start):
        base = os.path.dirname(start)
    elif start and os.path.isdir(start):
        base = start
    else:
        base = _default_dir()
    try:
        win.pane = Pane(base)
    except OSError:
        win.pane = Pane(os.path.expanduser("~"))
    win.state = {
        "player":  Player(),
        "nowpath": None,        # path of the track currently loaded
        "dblk":    (None, 0.0),  # (row index, monotonic) for double-click
        "showcmd": False,        # gear popover visible?
    }
    win.title = "Windows Media Player"
    if start and os.path.isfile(start) and is_audio(start):
        for i, e in enumerate(win.pane.entries):
            if e.path == os.path.abspath(start):
                win.pane.sel = i
                break
        _play_path(win, os.path.abspath(start))


# --------------------------------------------------------------------------- #
#  helpers
# --------------------------------------------------------------------------- #
def _audio_entries(win):
    return [e for e in win.pane.entries if not e.is_dir and is_audio(e.path)]


def _play_path(win, path):
    win.state["player"].play(path)
    win.state["nowpath"] = path
    win.title = "WMP - " + (sanitize(os.path.basename(path)) or "")


def _toggle(win):
    pl = win.state["player"]
    if pl.state == "stopped":
        cur = win.state.get("nowpath")
        if cur is None:
            al = _audio_entries(win)
            cur = al[0].path if al else None
        if cur:
            _play_path(win, cur)
    else:
        pl.toggle_pause()


def _advance(win, delta):
    al = _audio_entries(win)
    if not al:
        win.state["player"].stop()
        win.state["nowpath"] = None
        win.title = "Windows Media Player"
        return
    cur = win.state.get("nowpath")
    idx = next((i for i, e in enumerate(al) if e.path == cur), None)
    if idx is None:
        idx = 0 if delta >= 0 else len(al) - 1
    else:
        idx += delta
    if idx < 0 or idx >= len(al):                 # ran off either end -> stop
        win.state["player"].stop()
        win.state["nowpath"] = None
        win.title = "Windows Media Player"
        return
    _play_path(win, al[idx].path)


def _double(win, idx):
    last, t = win.state.get("dblk", (None, 0.0))
    now = time.monotonic()
    win.state["dblk"] = (idx, now)
    return last == idx and (now - t) < DBL_MS


def _mmss(secs):
    secs = int(max(0, secs))
    return "%d:%02d" % (secs // 60, secs % 60)


def _inrect(r, px, py):
    x, y, w, h = r
    return x <= px < x + w and y <= py < y + h


def _incirc(c, px, py):
    cx, cy, r = c
    return (px - cx) ** 2 + (py - cy) ** 2 <= (r + 2) ** 2


# --------------------------------------------------------------------------- #
#  layout (shared by draw + click so hit-tests can't drift from the painting)
# --------------------------------------------------------------------------- #
def _layout(win, d):
    bx, by, bw, bh = win.body_rect()
    tb = 100
    pad = 16
    bar = (bx + pad, by + 46, bw - 2 * pad, 8)
    cx = bx + bw // 2
    btny = by + 78
    prev = (cx - 56, btny, 13)
    play = (cx, btny, 17)
    nxt = (cx + 56, btny, 13)
    gear = (bx + bw - 26, by + 8, 18, 18)
    listr = (bx, by + tb, bw, bh - tb)
    rowh = max(20, d.ch + 6)
    return {"bx": bx, "by": by, "bw": bw, "bh": bh, "tb": tb, "cx": cx,
            "bar": bar, "prev": prev, "play": play, "next": nxt,
            "gear": gear, "list": listr, "rowh": rowh, "pad": pad}


# --------------------------------------------------------------------------- #
#  draw
# --------------------------------------------------------------------------- #
def mus_draw(cv, d, win):
    L = _layout(win, d)
    bx, by, bw, bh = L["bx"], L["by"], L["bw"], L["bh"]
    pl = win.state["player"]

    # body background (list area)
    cv.pen("#ffffff")
    cv.rectf(bx, by, bw, bh)

    # ----- transport bar ---------------------------------------------------- #
    tb = L["tb"]
    cv.vgrad(bx, by, bw, tb, M["tb0"], M["tb1"], 14)
    cv.pen(M["tbsep"])
    cv.rectf(bx, by + tb - 1, bw, 1)

    # title / status "LCD" display centred at the top
    disp_w = min(bw - 120, 360)
    disp_h = 26
    dx = L["cx"] - disp_w // 2
    dy = by + 8
    cv.vgrad(dx, dy, disp_w, disp_h, M["lcd0"], M["lcd1"], 6)
    cv.pen(M["lcdbd"])
    cv.rrect(dx, dy, disp_w, disp_h, 5)
    if pl.err:
        title = sanitize(pl.err)
    elif win.state["nowpath"]:
        title = sanitize(os.path.basename(win.state["nowpath"]))
        if pl.state == "paused":
            title = "|| " + title
    else:
        title = "Not Playing"
    maxc = max(3, (disp_w - 12) // d.charw)
    if len(title) > maxc:
        title = title[:maxc - 1] + "~"
    cv.pen(M["lcdink"])
    cv.text(L["cx"] - len(title) * d.charw // 2, dy + disp_h - 9, title)

    # ----- progress / seek bar --------------------------------------------- #
    sx, sy, sw, sh = L["bar"]
    el = pl.elapsed()
    dur = pl.duration()
    frac = (el / dur) if dur > 0 else 0.0
    frac = max(0.0, min(1.0, frac))
    cv.vgrad(sx, sy, sw, sh, M["track0"], M["track1"], 4)
    if frac > 0:
        cv.vgrad(sx, sy, max(2, int(sw * frac)), sh, M["fill0"], M["fill1"], 4)
    cv.pen("#7f97bb")
    cv.rrect(sx, sy, sw, sh, 3)
    if pl.state != "stopped" and (dur > 0 or not pl.remote):
        kx = sx + int(sw * frac)
        cv.pen(M["knob"])
        cv.circf(kx, sy + sh // 2, 6)
        cv.pen(M["knobbd"])
        cv.circ(kx, sy + sh // 2, 6)
    # time readouts: elapsed left, duration (or --:--) right
    cv.pen(C["dim"])
    cv.text(sx, sy + 20, _mmss(el))
    rt = _mmss(dur) if dur > 0 else "--:--"
    cv.text(sx + sw - len(rt) * d.charw, sy + 20, rt)

    # ----- transport buttons ----------------------------------------------- #
    _draw_btn(cv, L["prev"], "prev", M["glyph"])
    playing = (pl.state == "playing")
    _draw_btn(cv, L["play"], "pause" if playing else "play",
              M["glyphhi"] if playing else M["glyph"])
    _draw_btn(cv, L["next"], "next", M["glyph"])

    # ----- gear (player-command info toggle) -------------------------------- #
    _draw_gear(cv, L["gear"])

    # ----- file / playlist list -------------------------------------------- #
    lx, ly, lw, lh = L["list"]
    rowh = L["rowh"]
    visible = max(1, lh // rowh)
    pane = win.pane
    pane.clamp(visible)
    nowp = win.state["nowpath"]
    y = ly
    for i in range(pane.top, min(len(pane.entries), pane.top + visible)):
        e = pane.entries[i]
        is_now = (not e.is_dir and e.path == nowp)
        if is_now:
            cv.vgrad(lx, y, lw, rowh, C["selrow0"], C["selrow1"], 4)
            ink = C["white"]
        else:
            if (i - pane.top) % 2:
                cv.pen(M["rowalt"])
                cv.rectf(lx, y, lw, rowh)
            ink = (C["dir"] if e.is_dir else
                   M["noteink"] if is_audio(e.path) else C["dim"])
        if i == pane.sel and not is_now:
            cv.pen("#3a93ff")
            cv.rect(lx + 1, y, lw - 2, rowh)
        gy = y + rowh // 2
        gx = lx + 16
        if e.is_dir:
            _folder_glyph(cv, gx, gy, "#fff4d6" if is_now else C["dir"])
        elif is_audio(e.path):
            _note_glyph(cv, gx, gy, "#ffffff" if is_now else M["noteink"])
        else:
            cv.pen(ink)
            cv.circ(gx, gy, 3)
        name = sanitize(e.name) + ("/" if e.is_dir else "")
        maxc = max(3, (lw - 40) // d.charw)
        if len(name) > maxc:
            name = name[:maxc - 1] + "~"
        cv.pen(ink)
        cv.text(lx + 30, gy + 5, name)
        if is_now and playing:
            cv.text(lx + lw - 16, gy + 5, ">")
        y += rowh
        cv.pen(M["rowsep"])
        cv.rectf(lx, y - 1, lw, 1)

    # ----- gear popover (drawn last so it floats over the bar) -------------- #
    if win.state.get("showcmd"):
        _draw_popover(cv, d, win, L)


def _draw_btn(cv, c, glyph, ink):
    cx, cy, r = c
    cv.vgrad(cx - r, cy - r, 2 * r, 2 * r, M["btn0"], M["btn1"], 6)
    cv.pen(M["btnbd"])
    cv.circ(cx, cy, r)
    cv.pen("#ffffffcc")
    cv.arc(cx, cy, r - 2, 200, 340)          # top sheen
    cv.pen(ink)
    s = r // 2 + 1
    if glyph == "play":
        cv.trif(cx - s + 2, cy - s, cx - s + 2, cy + s, cx + s + 1, cy)
    elif glyph == "pause":
        w = max(2, s // 2)
        cv.rectf(cx - s + 1, cy - s, w, 2 * s)
        cv.rectf(cx + s - w - 1, cy - s, w, 2 * s)
    elif glyph == "prev":
        cv.trif(cx + s - 1, cy - s, cx + s - 1, cy + s, cx - 2, cy)
        cv.rectf(cx - s - 1, cy - s, 2, 2 * s)
    elif glyph == "next":
        cv.trif(cx - s + 1, cy - s, cx - s + 1, cy + s, cx + 2, cy)
        cv.rectf(cx + s - 1, cy - s, 2, 2 * s)


def _draw_gear(cv, r):
    x, y, w, h = r
    cx, cy = x + w // 2, y + h // 2
    cv.pen("#5a78a0")
    cv.circf(cx, cy, w // 2)
    cv.pen(M["tb0"])
    cv.circf(cx, cy, w // 4)
    cv.pen("#5a78a0")
    for a in range(0, 360, 45):                # little teeth as short spokes
        cv.arc(cx, cy, w // 2 + 1, a, a + 18)


def _folder_glyph(cv, cx, cy, col):
    cv.pen(col)
    cv.rrectf(cx - 7, cy - 4, 14, 9, 2)
    cv.rectf(cx - 7, cy - 6, 6, 3)


def _note_glyph(cv, cx, cy, col):
    cv.pen(col)
    cv.circf(cx - 3, cy + 4, 3)               # note head
    cv.rectf(cx, cy - 6, 2, 9)                # stem
    cv.rectf(cx, cy - 6, 5, 2)               # flag


def _draw_popover(cv, d, win, L):
    pl = win.state["player"]
    bx, by, bw = L["bx"], L["by"], L["bw"]
    pw = min(bw - 24, 380)
    ph = 58
    px = bx + bw - pw - 8
    py = by + 28
    cv.vgrad(px, py, pw, ph, M["pop0"], M["pop1"], 8)
    cv.pen(M["popbd"])
    cv.rrect(px, py, pw, ph, 5)
    cv.pen(C["ink"])
    mode = "remote control" if pl.remote else "SIGSTOP/CONT"
    cv.text(px + 10, py + 16, "Player: " + sanitize(pl.cmd))
    cv.pen(C["dim"])
    cv.text(px + 10, py + 32, "Mode: " + mode)
    cv.text(px + 10, py + 48, "Set $SHOEXP_PLAYER to change")


# --------------------------------------------------------------------------- #
#  input
# --------------------------------------------------------------------------- #
def mus_click(win, px, py, d, btn):
    L = _layout(win, d)
    if _inrect(L["gear"], px, py):
        win.state["showcmd"] = not win.state.get("showcmd")
        return True
    if win.state.get("showcmd"):
        win.state["showcmd"] = False         # any other click dismisses popover
    if _incirc(L["prev"], px, py):
        _advance(win, -1)
        return True
    if _incirc(L["play"], px, py):
        _toggle(win)
        return True
    if _incirc(L["next"], px, py):
        _advance(win, +1)
        return True
    sx, sy, sw, sh = L["bar"]
    if sx <= px <= sx + sw and sy - 8 <= py <= sy + sh + 8:
        win.state["player"].seek((px - sx) / max(1, sw))
        return True
    lx, ly, lw, lh = L["list"]
    rowh = L["rowh"]
    if lx <= px < lx + lw and ly <= py < ly + lh:
        idx = win.pane.top + (py - ly) // rowh
        if 0 <= idx < len(win.pane.entries):
            win.pane.sel = idx
            if _double(win, idx):
                e = win.pane.entries[idx]
                if e.is_dir:
                    win.pane.enter()
                elif is_audio(e.path):
                    _play_path(win, e.path)
        return True
    return True


def mus_key(win, key, d):
    L = _layout(win, d)
    visible = max(1, L["list"][3] // L["rowh"])
    p = win.pane
    if key == " ":
        _toggle(win)
        return True
    if key == "up":
        p.sel -= 1
        p.clamp(visible)
        return True
    if key == "down":
        p.sel += 1
        p.clamp(visible)
        return True
    if key == "pgup":
        p.sel -= visible
        p.clamp(visible)
        return True
    if key == "pgdn":
        p.sel += visible
        p.clamp(visible)
        return True
    if key == "left":
        _advance(win, -1)
        return True
    if key == "right":
        _advance(win, +1)
        return True
    if key == "enter":
        e = p.cur()
        if e and e.is_dir:
            p.enter()
        elif e and is_audio(e.path):
            _play_path(win, e.path)
        return True
    return False


def mus_wheel(win, px, py, up, d):
    L = _layout(win, d)
    visible = max(1, L["list"][3] // L["rowh"])
    win.pane.top += -3 if up else 3
    maxtop = max(0, len(win.pane.entries) - visible)
    win.pane.top = max(0, min(win.pane.top, maxtop))
    return True


def mus_tick(win, d):
    pl = win.state["player"]
    changed = pl.poll()
    if pl.ended:
        pl.ended = False
        _advance(win, +1)                    # auto-advance to the next track
        changed = True
    # keep redrawing ~1/s while a track plays so the progress bar animates
    return changed or pl.state == "playing"


def mus_close(win):
    st = getattr(win, "state", None)
    if st and st.get("player"):
        st["player"].shutdown()


# --------------------------------------------------------------------------- #
#  icons -- a glossy rounded tile with an eighth-note
# --------------------------------------------------------------------------- #
def _music_tile(cv, x, y, s):
    r = max(2, s // 6)
    cv.vgrad(x, y, s, s, "#7db2ff", "#2f6fe0", 8)
    cv.pen("#ffffff66")
    cv.rrect(x + 1, y + 1, s - 2, s // 2, r)     # top gloss
    cv.pen("#1f5bbf")
    cv.rrect(x, y, s, s, r)
    # eighth note in white
    cv.pen("#ffffff")
    hx = x + int(s * 0.36)
    hy = y + int(s * 0.66)
    cv.circf(hx, hy, max(2, s // 9))             # note head
    stemw = max(1, s // 16)
    cv.rectf(hx + max(2, s // 9) - stemw, y + int(s * 0.28), stemw,
             int(s * 0.40))                      # stem
    cv.polyf([hx + max(2, s // 9) - stemw, y + int(s * 0.28),
              x + int(s * 0.66), y + int(s * 0.34),
              x + int(s * 0.66), y + int(s * 0.46),
              hx + max(2, s // 9) - stemw, y + int(s * 0.40)])  # flag


def icon16(cv, x, y):
    _music_tile(cv, x, y, 16)


def icon48(cv, cx, top):
    s = 40
    _music_tile(cv, cx - s // 2, top, s)


# --------------------------------------------------------------------------- #
#  standalone smoke test
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import sys
    spec = make_app()
    print("shoexp_music make_app ok:", spec["kind"], spec["title"], spec["size"])
    print("audio?", is_audio("/x/y.mp3"), is_audio("/x/y.txt"))
    sys.exit(0)