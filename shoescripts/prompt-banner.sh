#!/bin/sh
# prompt-banner.sh — a vector-graphics prompt banner for shoeterm/foot.
#
# Draws a small card *above* your shell prompt each time the prompt is shown:
# user@host, the current git branch (if any), and the time. PS1 itself stays a
# plain string, so line editing / history are never disturbed — the banner is
# emitted from PROMPT_COMMAND and the cursor scrolls to a clean line beneath it.
#
#   Try it:   ./bld/debug/foot sh -c '. ./prompt-banner.sh; exec bash'
#   Use it:   add to ~/.bashrc:   . /path/to/prompt-banner.sh
#
# Honours the same env switches as the other userland scripts:
#   PROMPT_BANNER_FORCE=1   always draw graphics (even when $TERM isn't foot)
#   PROMPT_BANNER_PLAIN=1   never draw graphics (disable the banner)
#
# Why a graphic above the prompt and not inline: a drawn canvas reuses the
# sixel pipeline, which advances the cursor to *below* the image (CLAUDE.md /
# sixel.c:sixel_emit_image). So a banner stacks above the prompt nicely, but a
# glyph you could type next to on the same line isn't possible with this model.

# ---- capability gate (PLAIN beats FORCE, like shoestring/shoelace) ----------
__pb_graphics_ok() {
    [ -n "$PROMPT_BANNER_PLAIN" ] && return 1
    [ -n "$PROMPT_BANNER_FORCE" ] && return 0
    [ -t 1 ] || return 1                 # not a tty (redirected) -> no banner
    case "$TERM" in
        foot | foot-* | *-foot | *foot*) return 0 ;;
    esac
    return 1
}

# ---- one-time cell-size probe (pixels per cell) -----------------------------
# Absolute pixel coords assume a cell size; ask foot for its real one via
# ESC[16t -> ESC[6;h;w t. Query /dev/tty so it works with redirected stdin.
# Fall back to ~8x16. Done once at source time, not per prompt.
__PB_CW=8; __PB_CH=16
__pb_probe_cells() {
    old=`stty -g </dev/tty 2>/dev/null` || return
    stty raw -echo min 0 time 2 </dev/tty 2>/dev/null
    printf '\033[16t' >/dev/tty
    resp=`dd bs=1 count=20 </dev/tty 2>/dev/null`
    stty "$old" </dev/tty 2>/dev/null
    h=`printf '%s' "$resp" | sed -n 's/.*\[6;\([0-9]*\);\([0-9]*\)t.*/\1/p'`
    w=`printf '%s' "$resp" | sed -n 's/.*\[6;\([0-9]*\);\([0-9]*\)t.*/\2/p'`
    [ -n "$h" ] && __PB_CH=$h
    [ -n "$w" ] && __PB_CW=$w
}

# ---- the banner ------------------------------------------------------------
# Kept deliberately cheap (no awk gradient loops) because it runs every prompt.
# Card is a fixed pixel size on a transparent canvas, sized snugly in cells.
__pb_draw() {
    status=$?                            # preserve $? for the rest of PROMPT_COMMAND

    # dynamic bits
    branch=`git symbolic-ref --quiet --short HEAD 2>/dev/null \
        || git rev-parse --short HEAD 2>/dev/null`
    clock=`date +%H:%M`
    who="$USER@${HOSTNAME%%.*}"
    [ "$status" = 0 ] && dot='#38e0ff' || dot='#ff5277'   # ok=cyan, error=red

    # card geometry (pixels)
    ox=4; oy=2; CW=420; CH=40
    cols=$(( (ox + CW + __PB_CW - 1) / __PB_CW ))
    rows=$(( (oy + CH + __PB_CH - 1) / __PB_CH ))

    {
        printf '\033P>g\n'
        printf 'size %d %d\n' "$cols" "$rows"
        printf 'bg none\n'

        # rounded panel + left accent bar
        printf 'pen #1b1230d8\n';  printf 'rrectf %d %d %d %d 8\n' "$ox" "$oy" "$CW" "$CH"
        printf 'pen %s\n' "$dot";  printf 'rrectf %d %d 6 %d 3\n'  $((ox+8)) $((oy+8)) $((CH-16))

        # status dot
        printf 'pen %s\n' "$dot";  printf 'circf %d %d 4\n' $((ox+26)) $((oy+CH/2))

        # user@host (bright) and a soft flourish under it
        printf 'pen #ffffff\n';    printf 'text %d %d %s\n' $((ox+40)) $((oy+13)) "$who"
        printf 'pen #dc82f0aa\n'
        printf 'bezier %d %d %d %d %d %d %d %d\n' \
            $((ox+40)) $((oy+24)) $((ox+130)) $((oy+20)) \
            $((ox+220)) $((oy+28)) $((ox+CW-90)) $((oy+24))

        # branch (if any) + clock, right-aligned-ish using the char-width estimate
        [ -n "$branch" ] && {
            printf 'pen #8be9fd\n'; printf 'text %d %d %s\n' $((ox+40)) $((oy+34)) "git:$branch"
        }
        clk_x=$(( ox + CW - ${#clock} * __PB_CW - 12 ))
        printf 'pen #b8a8e8\n';     printf 'text %d %d %s\n' "$clk_x" $((oy+13)) "$clock"

        printf '\033\\'
    } 2>/dev/null

    # The sixel pipeline leaves the cursor on the image's *last* row
    # (sixel.c:sixel_emit_image), so drop one line to keep the prompt clear
    # of the card's bottom edge.
    printf '\n'

    return $status
}

# ---- wire-up ---------------------------------------------------------------
if __pb_graphics_ok; then
    __pb_probe_cells
    # Prepend to any existing PROMPT_COMMAND rather than clobbering it.
    case ";$PROMPT_COMMAND;" in
        *";__pb_draw;"*) : ;;                       # already installed
        *) PROMPT_COMMAND="__pb_draw${PROMPT_COMMAND:+;$PROMPT_COMMAND}" ;;
    esac
fi
