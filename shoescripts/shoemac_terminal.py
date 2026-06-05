# shoemac_terminal - the Snow Leopard "Terminal" app for the shoemac desktop.
#
# A (lovingly fake) Terminal.app: a translucent dark window over the brushed
# desktop, a live scrollback, and a small set of *real* commands run against the
# actual filesystem -- ls / pwd / cd / cat / date / whoami / uname / echo /
# clear / help.  It is the first shoemac app to capture the keyboard (like
# shoexp's Notepad): while it is the focused window every keystroke is routed to
# term_key(), so you can type a command and hit Return.
#
# Self-contained module: make_app() returns the spec dict the host's
# register_app() consumes.  Drawing goes only through Canvas (text via cv.text,
# geometry comma-joined); all UI text is plain ASCII so no glyph is ever missing.

import os
import time
import platform

from shoemac_ui import C, mix, lighten, darken, human, sanitize  # noqa: F401

# ----- terminal palette (local: a translucent dark scheme, not the Aqua C) --- #
TERM = {
    "bg":      "#1d1f21f0",   # window body: near-opaque charcoal (faint see-through)
    "bgbar":   "#33363b",     # a hint of inner top shading
    "ink":     "#d7dadd",     # default text
    "dim":     "#8a8f96",     # secondary text
    "user":    "#76d275",     # prompt user@host (green)
    "path":    "#5fa9f0",     # prompt cwd (blue)
    "dirink":  "#74b6ff",     # directory names in ls
    "execink": "#76d275",     # executable names in ls
    "linkink": "#c2a3ff",     # symlink names in ls
    "err":     "#ff6f60",     # error text
    "cursor":  "#d7dadd",     # block cursor
    "edge":    "#0c0d0e",
}

MAXLINES = 600          # scrollback cap


def make_app():
    return {
        "kind": "terminal",
        "title": "Terminal",
        "size": (588, 360),
        "init": term_init,
        "draw": draw_terminal,
        "key": term_key,
        "icon16": icon16,
        "icon48": icon48,
        "dock": True,
    }


# ----- state ---------------------------------------------------------------- #
def term_init(win):
    cwd = win.open_path or os.path.expanduser("~")
    try:
        cwd = os.path.abspath(cwd)
        if not os.path.isdir(cwd):
            cwd = os.path.expanduser("~")
    except OSError:
        cwd = os.path.expanduser("~")
    win.state = {
        "cwd": cwd,
        "lines": [("dim", "shoemac Terminal -- type 'help' for commands.")],
        "cur": "",            # the command being typed
        "hist": [],           # command history
        "hidx": 0,            # history cursor (== len(hist) means "new line")
    }
    win.title = "Terminal"


def _short(cwd):
    home = os.path.expanduser("~")
    if cwd == home:
        return "~"
    if cwd.startswith(home + os.sep):
        return "~" + cwd[len(home):]
    return cwd


def _prompt(win, d):
    # "user@host shortcwd $ " -- returned as plain text for echoing into output.
    base = os.path.basename(win.state["cwd"]) or "/"
    return "%s@%s %s $ " % (d.user, d.host.split(".")[0], base)


# ----- output helpers -------------------------------------------------------- #
def _push(win, color, text):
    for ln in text.split("\n"):
        win.state["lines"].append((color, ln))
    extra = len(win.state["lines"]) - MAXLINES
    if extra > 0:
        del win.state["lines"][:extra]


# ----- command execution ----------------------------------------------------- #
def _run(win, d, raw):
    cmd = raw.strip()
    # echo the prompt + the command, exactly as a real shell scrollback would.
    _push(win, "prompt", _prompt(win, d) + cmd)
    if not cmd:
        return
    parts = cmd.split()
    name, args = parts[0], parts[1:]
    fn = COMMANDS.get(name)
    if fn is None:
        _push(win, "err", "-shoemac: %s: command not found" % name)
        return
    try:
        fn(win, d, args)
    except Exception as e:                       # noqa: BLE001
        _push(win, "err", "%s: %s" % (name, e))


def _resolve(win, p):
    if not p:
        return win.state["cwd"]
    p = os.path.expanduser(p)
    if not os.path.isabs(p):
        p = os.path.join(win.state["cwd"], p)
    return os.path.normpath(p)


def cmd_help(win, d, args):
    _push(win, "ink", "commands: ls  pwd  cd  cat  echo  date  whoami  "
                      "uname  clear  help")


def cmd_pwd(win, d, args):
    _push(win, "ink", win.state["cwd"])


def cmd_whoami(win, d, args):
    _push(win, "ink", d.user)


def cmd_uname(win, d, args):
    if args and args[0] == "-a":
        _push(win, "ink", "Darwin %s 10.6.8 Darwin Kernel Version 10.6.8 "
                          "x86_64" % d.host)
    else:
        _push(win, "ink", "Darwin")


def cmd_date(win, d, args):
    _push(win, "ink", time.strftime("%a %d %b %Y %H:%M:%S"))


def cmd_echo(win, d, args):
    _push(win, "ink", " ".join(args))


def cmd_clear(win, d, args):
    win.state["lines"] = []


def cmd_cd(win, d, args):
    target = _resolve(win, args[0] if args else None)
    if not os.path.isdir(target):
        _push(win, "err", "cd: no such directory: " + (args[0] if args else ""))
        return
    win.state["cwd"] = target


def cmd_cat(win, d, args):
    if not args:
        _push(win, "err", "cat: missing file operand")
        return
    path = _resolve(win, args[0])
    if os.path.isdir(path):
        _push(win, "err", "cat: %s: Is a directory" % args[0])
        return
    try:
        with open(path, "r", errors="replace") as f:
            data = f.read(8192)
    except OSError as e:
        _push(win, "err", "cat: %s: %s" % (args[0], e.strerror or "error"))
        return
    shown = data.splitlines()[:80]
    for ln in shown:
        _push(win, "ink", ln[:400])
    if len(data) >= 8192:
        _push(win, "dim", "[truncated]")


def cmd_ls(win, d, args):
    show_all = False
    target = None
    for a in args:
        if a.startswith("-"):
            show_all = "a" in a
        else:
            target = a
    path = _resolve(win, target)
    try:
        names = os.listdir(path)
    except OSError as e:
        _push(win, "err", "ls: %s: %s" % (target or ".", e.strerror or "error"))
        return
    if not show_all:
        names = [n for n in names if not n.startswith(".")]
    names.sort(key=str.lower)
    if not names:
        return
    # classify so we can colour + suffix like a real `ls -F`
    rows = []
    cols_w = body_cols(win, d)
    items = []
    for n in names:
        full = os.path.join(path, n)
        try:
            is_link = os.path.islink(full)
            is_dir = os.path.isdir(full)
            is_exec = (not is_dir and os.access(full, os.X_OK))
        except OSError:
            is_link = is_dir = is_exec = False
        label = n + ("/" if is_dir else "*" if is_exec else "@" if is_link else "")
        color = ("dirink" if is_dir else "execink" if is_exec
                 else "linkink" if is_link else "ink")
        items.append((label, color))
    # lay out into as many fixed-width columns as fit the window width
    cw = max(len(lbl) for lbl, _ in items) + 2
    ncols = max(1, cols_w // cw)
    nrows = (len(items) + ncols - 1) // ncols
    for r in range(nrows):
        rows.append([items[r + c * nrows] for c in range(ncols)
                     if r + c * nrows < len(items)])
    # each output line carries mixed colours, so emit a "cells" tuple the
    # renderer understands (list of (text,color) padded to column width).
    for r in rows:
        cells = [(lbl.ljust(cw), color) for lbl, color in r]
        win.state["lines"].append(("cells", cells))
    extra = len(win.state["lines"]) - MAXLINES
    if extra > 0:
        del win.state["lines"][:extra]


COMMANDS = {
    "help": cmd_help, "pwd": cmd_pwd, "whoami": cmd_whoami, "uname": cmd_uname,
    "date": cmd_date, "echo": cmd_echo, "clear": cmd_clear, "cd": cmd_cd,
    "cat": cmd_cat, "ls": cmd_ls,
}


# ----- geometry -------------------------------------------------------------- #
def _lh(d):
    return max(12, d.ch)


def body_cols(win, d):
    bx, by, bw, bh = win.body_rect()
    return max(8, (bw - 16) // d.charw)


# ----- draw ------------------------------------------------------------------ #
def draw_terminal(cv, d, win):
    bx, by, bw, bh = win.body_rect()
    # translucent charcoal body (fills our own background, per the contract)
    cv.pen(TERM["bg"])
    cv.rectf(bx, by, bw, bh)
    cv.pen(TERM["bgbar"])
    cv.rectf(bx, by, bw, 1)
    cv.pen(TERM["edge"])
    cv.rect(bx, by, bw, bh)

    lh = _lh(d)
    pad = 8
    left = bx + pad
    avail = bh - 2 * pad
    rows = max(1, avail // lh)

    # build the rendered line list = scrollback + the live prompt/input line
    lines = list(win.state["lines"])
    prompt = _prompt(win, d)
    lines.append(("input", prompt + win.state["cur"]))

    # show the tail that fits
    visible = lines[-rows:]
    y = by + pad + lh - 4
    cur_col = body_cols(win, d)
    for color, payload in visible:
        if color == "cells":
            # multi-colour ls row: payload is a list of (text, colorkey)
            x = left
            for text, ck in payload:
                cv.pen(TERM.get(ck, TERM["ink"]))
                cv.text(x, y, text[:cur_col])
                x += len(text) * d.charw
            y += lh
            continue
        text = payload
        if color == "prompt" or color == "input":
            # colour the "user@host cwd $ " prefix, then plain command text
            plen = len(prompt)
            cv.pen(TERM["user"])
            cv.text(left, y, text[:plen][:cur_col])
            cv.pen(TERM["ink"])
            cv.text(left + plen * d.charw, y, text[plen:][:cur_col])
            if color == "input":
                # block cursor at the end of the typed command
                cx = left + (plen + len(win.state["cur"])) * d.charw
                cv.pen(TERM["cursor"])
                cv.rectf(cx + 1, y - lh + 6, d.charw - 1, lh - 4)
        else:
            cv.pen(TERM.get(color, TERM["ink"]))
            cv.text(left, y, text[:cur_col])
        y += lh


# ----- keyboard (focused window only) ---------------------------------------- #
def term_key(win, key, d):
    st = win.state
    if key == "enter":
        line = st["cur"]
        if line.strip():
            st["hist"].append(line)
        st["hidx"] = len(st["hist"])
        _run(win, d, line)
        st["cur"] = ""
        return True
    if key == "back":
        st["cur"] = st["cur"][:-1]
        return True
    if key == "del":
        st["cur"] = ""
        return True
    if key == "up":
        if st["hist"] and st["hidx"] > 0:
            st["hidx"] -= 1
            st["cur"] = st["hist"][st["hidx"]]
        return True
    if key == "down":
        if st["hidx"] < len(st["hist"]):
            st["hidx"] += 1
            st["cur"] = (st["hist"][st["hidx"]]
                         if st["hidx"] < len(st["hist"]) else "")
        return True
    if key == "tab":
        return True            # swallow (no completion in v1)
    if isinstance(key, str) and len(key) == 1 and key >= " ":
        st["cur"] += key
        return True
    return False


# ----- icons ----------------------------------------------------------------- #
def _term_tile(cv, x, y, s):
    # a dark rounded terminal: title strip on top, a ">_" prompt below.
    r = max(2, s // 7)
    cv.vgrad(x, y, s, s, "#41454b", "#222428", 8)
    cv.pen(TERM["edge"])
    cv.rrect(x, y, s, s, r)
    # title strip
    th = max(3, s // 5)
    cv.pen("#5a5f66")
    cv.rectf(x + 2, y + 2, s - 4, th)
    cv.pen(TERM["edge"])
    cv.line(x + 2, y + 2 + th, x + s - 2, y + 2 + th)
    # screen
    sx, sy = x + max(2, s // 8), y + th + max(2, s // 10)
    # prompt chevron ">"
    cw = max(2, s // 8)
    cv.thickness(max(1, s // 22))
    cv.pen(TERM["user"])
    cv.line(sx, sy, sx + cw, sy + cw)
    cv.line(sx + cw, sy + cw, sx, sy + 2 * cw)
    # underscore cursor
    cv.pen(TERM["ink"])
    cv.line(sx + cw + 3, sy + 2 * cw, sx + cw + 3 + cw, sy + 2 * cw)
    cv.thickness(1)


def icon16(cv, x, y):
    _term_tile(cv, x, y, 16)


def icon48(cv, cx, top):
    s = 40
    _term_tile(cv, cx - s // 2, top, s)
