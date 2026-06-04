#!/usr/bin/env bash
# ============================================================================
# Frogger for foot — keyboard-driven, rendered with foot's vector-graphics DCS
# protocol, one canvas per tick. Pure bash (needs fractional `read -t`).
#
#   ./bld/debug/foot bash frogger.sh
#
# Controls: WASD or arrow keys to hop, q to quit. Cross the road and the river,
# fill all 5 home pads to clear the level. See frogger-plan.md for the design.
# ============================================================================

set -u

# --- constants ---------------------------------------------------------------
COLS=13; ROWS=14; TILE=40
CW=$((COLS * TILE))          # canvas width  in px (520)
CH=$((ROWS * TILE))          # canvas height in px (560)
FRAMETIME=0.02               # tick / input-poll interval (≈20 fps)

# --- shared game state (owned here, read/written by the modules) -------------
declare -a L_TYPE L_DIR L_SPEED L_EW L_ENTS PAD_FILLED
CELL_W=8; CELL_H=16          # overwritten by query_cell_size
SIZE_COLS=0; SIZE_ROWS=0     # canvas size in cells (set after probe)
FROG_PX=0; FROG_PY=0; START_PX=0; START_PY=0; MAX_ROW=13
LIVES=3; SCORE=0; LEVEL=1; FRAME=0
STATE=play                   # play | win | over | quit
CMDS=""; key=""; SAVED_STTY=""
BOARD_BG=""                  # static scenery, built once (see build_board_bg)

# ============================================================================
# TERMINAL setup / teardown / input
# cleanup is wired to a trap (trap cleanup EXIT INT TERM); it must be trap-safe.
# ============================================================================

# Query foot for the cell pixel size. Sends CSI 16 t; foot replies
# CSI 6 ; <height> ; <width> t (both in pixels). Sets globals CELL_W / CELL_H.
# Falls back to 8x16 on no reply / parse failure. Assumes the tty is already
# in raw/-echo mode (setup_term has run).
query_cell_size() {
	local reply c cw ch
	CELL_W=8; CELL_H=16                      # defaults / fallback
	printf '\033[16t'                        # request cell size
	reply=''
	while IFS= read -rsn1 -t 0.2 c; do
		reply+=$c
		[[ $c == t ]] && break
	done
	if [[ $reply =~ 6\;([0-9]+)\;([0-9]+)t ]]; then
		ch=${BASH_REMATCH[1]}                # height (pixels)
		cw=${BASH_REMATCH[2]}                # width  (pixels)
		if [[ $cw -gt 0 && $ch -gt 0 ]]; then
			CELL_W=$cw; CELL_H=$ch
		fi
	fi
}

# Save tty state, switch to non-canonical no-echo input, hide cursor, clear.
setup_term() {
	SAVED_STTY=$(stty -g)
	stty -echo -icanon min 0 time 0
	printf '\033[?25l\033[2J\033[H'
}

# Restore the terminal. Safe from a trap and to call more than once.
cleanup() {
	[[ -n $SAVED_STTY ]] && stty "$SAVED_STTY" 2>/dev/null
	printf '\033[?25h\033[2J\033[H'
}

# Per-frame input poll + tick timer in one call. $1 = frame time (seconds).
# Sets global `key` (empty on timeout). Arrow keys (ESC [ A/B/C/D) are drained
# and translated to the WASD equivalent: A=up=w B=down=s C=right=d D=left=a.
poll_key() {
	key=''
	read -rsn1 -t "$1" key
	if [[ $key == $'\033' ]]; then
		local b1 b2
		read -rsn1 -t 0.001 b1
		read -rsn1 -t 0.001 b2
		if [[ $b1 == '[' ]]; then
			case $b2 in
				A) key=w ;;
				B) key=s ;;
				C) key=d ;;
				D) key=a ;;
				*) key='' ;;
			esac
		fi
	fi
}

# ============================================================================
# GAME LOGIC — pure state, no drawing / no terminal I/O.
# ============================================================================

# init_world — build a fresh game: populate every lane, reset counters, spawn.
init_world() {
	local r x ew gap
	for ((r = 0; r < ROWS; r++)); do
		L_ENTS[r]=""
		case $r in
			0)  L_TYPE[r]=home;  L_DIR[r]=0; L_SPEED[r]=0; L_EW[r]=0 ;;
			1|2|3|4|5)
				L_TYPE[r]=water
				if ((r % 2 == 0)); then L_DIR[r]=1; else L_DIR[r]=-1; fi
				L_SPEED[r]=$(( 2 + (r % 3) ))            # 2..4 px/tick
				L_EW[r]=$(( TILE * (2 + r % 2) ))        # logs ~2-3 tiles
				;;
			6)  L_TYPE[r]=safe;  L_DIR[r]=0; L_SPEED[r]=0; L_EW[r]=0 ;;
			7|8|9|10|11)
				L_TYPE[r]=road
				if ((r % 2 == 0)); then L_DIR[r]=1; else L_DIR[r]=-1; fi
				L_SPEED[r]=$(( 3 + (r % 4) ))            # 3..6 px/tick
				L_EW[r]=$(( TILE + TILE / 2 * (r % 2) )) # cars 1-1.5 tiles
				;;
			12) L_TYPE[r]=safe;  L_DIR[r]=0; L_SPEED[r]=0; L_EW[r]=0 ;;
			13) L_TYPE[r]=start; L_DIR[r]=0; L_SPEED[r]=0; L_EW[r]=0 ;;
		esac
		if [[ ${L_TYPE[r]} == water || ${L_TYPE[r]} == road ]]; then
			ew=${L_EW[r]}
			# clear gap between entities: roads keep a wide hole so a 1-tile
			# frog can thread traffic; the river packs logs closer so there's
			# always a reachable next log to hop onto.
			if [[ ${L_TYPE[r]} == water ]]; then
				gap=$(( ew + TILE * 3 ))
			else
				gap=$(( ew + TILE * 14 ))
			fi
			local ents=""
			for ((x = 0; x < CW; x += gap)); do ents+="$x "; done
			L_ENTS[r]="${ents% }"
		fi
	done
	LIVES=3; SCORE=0; LEVEL=1
	for ((r = 0; r < 5; r++)); do PAD_FILLED[r]=0; done
	respawn_frog
}

# respawn_frog — place frog at the start tile (center column, row 13).
respawn_frog() {
	START_PX=$(( (COLS / 2) * TILE ))
	START_PY=$(( 13 * TILE ))
	FROG_PX=$START_PX; FROG_PY=$START_PY
	MAX_ROW=13
}

# move_frog $1=dx (tiles) $2=dy (tiles) — move, clamp, score new highest row.
move_frog() {
	local dx=$1 dy=$2
	local nx=$(( FROG_PX + dx * TILE ))
	local ny=$(( FROG_PY + dy * TILE ))
	(( nx < 0 )) && nx=0
	(( nx > (COLS - 1) * TILE )) && nx=$(( (COLS - 1) * TILE ))
	(( ny < 0 )) && ny=0
	(( ny > 13 * TILE )) && ny=$(( 13 * TILE ))
	FROG_PX=$(( (nx / TILE) * TILE ))
	FROG_PY=$ny
	local nrow=$(( FROG_PY / TILE ))
	if (( nrow < MAX_ROW )); then
		SCORE=$(( SCORE + 10 )); MAX_ROW=$nrow
	fi
}

# update_world $1=FRAME — advance lanes, then resolve the frog's current row.
update_world() {
	local r x nx ew dir sp ents span
	local frow=$(( FROG_PY / TILE ))
	local fcx=$(( FROG_PX + TILE / 2 ))

	# 1) advance every moving lane; wrap into [-ew, CW).
	for ((r = 0; r < ROWS; r++)); do
		[[ ${L_TYPE[r]} == water || ${L_TYPE[r]} == road ]] || continue
		dir=${L_DIR[r]}; sp=${L_SPEED[r]}; ew=${L_EW[r]}
		span=$(( CW + ew ))
		ents=""
		for x in ${L_ENTS[r]}; do
			nx=$(( x + dir * sp ))
			nx=$(( (nx + ew) % span ))
			(( nx < 0 )) && nx=$(( nx + span ))
			nx=$(( nx - ew ))
			ents+="$nx "
		done
		L_ENTS[r]="${ents% }"
	done

	# 2) resolve the frog's row.
	case ${L_TYPE[frow]} in
		water)
			dir=${L_DIR[frow]}; sp=${L_SPEED[frow]}; ew=${L_EW[frow]}
			local on=0
			for x in ${L_ENTS[frow]}; do
				if (( fcx >= x && fcx < x + ew )); then on=1; break; fi
			done
			if (( ! on )); then lose_life; return; fi
			FROG_PX=$(( FROG_PX + dir * sp ))
			local cx=$(( FROG_PX + TILE / 2 ))
			if (( cx < 0 || cx >= CW )); then lose_life; return; fi
			;;
		road)
			ew=${L_EW[frow]}
			for x in ${L_ENTS[frow]}; do
				if (( FROG_PX < x + ew && FROG_PX + TILE > x )); then
					lose_life; return
				fi
			done
			;;
	esac

	# 3) home row: map frog column to a pad index; fill or die.
	if (( frow == 0 )); then
		local col=$(( FROG_PX / TILE ))
		local pad=$(( col * 5 / COLS ))
		(( pad < 0 )) && pad=0
		(( pad > 4 )) && pad=4
		if (( PAD_FILLED[pad] == 0 )); then
			PAD_FILLED[pad]=1; SCORE=$(( SCORE + 50 )); respawn_frog
		else
			lose_life
		fi
	fi
}

# lose_life — drop a life and respawn (game-over check lives in check_win_lose).
lose_life() {
	LIVES=$(( LIVES - 1 )); respawn_frog
}

# check_win_lose — set STATE to play | win | over.
check_win_lose() {
	if (( LIVES <= 0 )); then STATE="over"; return; fi
	local r all=1
	for ((r = 0; r < 5; r++)); do
		(( PAD_FILLED[r] == 1 )) || { all=0; break; }
	done
	if (( all )); then
		LEVEL=$(( LEVEL + 1 ))
		SCORE=$(( SCORE + 100 * LEVEL ))
		for ((r = 0; r < ROWS; r++)); do
			[[ ${L_TYPE[r]} == water || ${L_TYPE[r]} == road ]] && \
				L_SPEED[r]=$(( L_SPEED[r] + 1 ))
		done
		for ((r = 0; r < 5; r++)); do PAD_FILLED[r]=0; done
		respawn_frog
		if (( LEVEL > 5 )); then STATE="win"; else STATE="play"; fi
		return
	fi
	STATE="play"
}

# ============================================================================
# RENDER — build the per-frame DCS command string in CMDS, emit one canvas.
# Convention: every helper appends newline-separated commands to CMDS; always
# `pen <color>` before drawing a new colour. All coords are integer px.
# ============================================================================

# draw_frame: orchestrator. Canvas size is ALWAYS the same SIZE_COLS/SIZE_ROWS
# so foot's overwrite rectangle matches frame to frame (flicker-free replace).
draw_frame() {
	CMDS=$'size '"$SIZE_COLS"' '"$SIZE_ROWS"$'\nbg #001018\nclear\n'"$BOARD_BG"
	draw_pads
	draw_entities
	draw_frog
	draw_hud
	# \033[H re-anchors the canvas top-left every frame; %s so game data is
	# never re-interpreted as printf escapes.
	printf '\033[H\033P>g\n%s\033\\' "$CMDS"
}

# build_board_bg: RICH static scenery into the global BOARD_BG. Called ONCE after
# L_TYPE[] / sizes are known; per-frame draw_frame just prepends BOARD_BG, so the
# textured water/road/grass/home art costs nothing to redraw. Goal pads that fill
# in are the only dynamic part of the board — see draw_pads.
build_board_bg() {
    local TILE=40 CW=520 ROWS=14
    local r y type

    # find first/last road row so we can place curbs correctly
    local first_road=-1 last_road=-1
    for ((r=0; r<ROWS; r++)); do
        if [[ "${L_TYPE[r]}" == "road" ]]; then
            (( first_road < 0 )) && first_road=$r
            last_road=$r
        fi
    done

    for ((r=0; r<ROWS; r++)); do
        y=$(( r * TILE ))
        type="${L_TYPE[r]}"

        case "$type" in
        # ---------------------------------------------------------------
        water)
            # vertical gradient: deep #0e2a5e -> brighter #2f6ad0 over 8 bands
            local b bands=8 bh fr R G B by
            bh=$(( TILE / bands ))
            (( bh < 1 )) && bh=1
            for ((b=0; b<bands; b++)); do
                fr=$(( b * 255 / (bands - 1) ))
                R=$(( 14  + (47  - 14)  * fr / 255 ))
                G=$(( 42  + (106 - 42)  * fr / 255 ))
                B=$(( 94  + (208 - 94)  * fr / 255 ))
                by=$(( y + b * bh ))
                local hh=$bh
                (( b == bands - 1 )) && hh=$(( TILE - b * bh ))
                printf -v R2 '%02x' "$R"; printf -v G2 '%02x' "$G"; printf -v B2 '%02x' "$B"
                BOARD_BG+=$'pen #'"$R2$G2$B2"$'\nrectf 0 '"$by"' '"$CW"' '"$hh"$'\n'
            done
            # gentle ripple lines (translucent light blue arcs/segments)
            BOARD_BG+=$'pen #9fc6ff40\nthickness 1\n'
            local rx ry rr seed
            seed=$(( (r * 131) % 360 ))
            for ((rx=20; rx<CW; rx+=110)); do
                ry=$(( y + 12 + ((rx + seed) % 16) ))
                rr=$(( 9 + ((rx / 30) % 6) ))
                BOARD_BG+=$'arc '"$(( rx + (seed % 25) ))"' '"$ry"' '"$rr"$' 200 340\n'
                BOARD_BG+=$'arc '"$(( rx + 55 + (seed % 18) ))"' '"$(( ry + 8 ))"' '"$(( rr - 2 ))"$' 200 340\n'
            done
            # a few sparkle pixels (bright)
            BOARD_BG+=$'pen #d7e9ff\n'
            local sx
            for ((sx=35; sx<CW; sx+=140)); do
                BOARD_BG+=$'pixel '"$(( sx + (seed % 30) ))"' '"$(( y + 6 + (seed % 22) ))"$'\n'
                BOARD_BG+=$'pixel '"$(( sx + 60 + (seed % 20) ))"' '"$(( y + 26 - (seed % 14) ))"$'\n'
            done
            ;;

        # ---------------------------------------------------------------
        road)
            # asphalt gradient: dark grey #1a1a1e -> #2c2c30, 6 bands
            local b bands=6 bh fr R G B by hh R2 G2 B2
            bh=$(( TILE / bands ))
            (( bh < 1 )) && bh=1
            for ((b=0; b<bands; b++)); do
                fr=$(( b * 255 / (bands - 1) ))
                R=$(( 26 + (44 - 26) * fr / 255 ))
                G=$(( 26 + (44 - 26) * fr / 255 ))
                B=$(( 30 + (48 - 30) * fr / 255 ))
                by=$(( y + b * bh ))
                hh=$bh
                (( b == bands - 1 )) && hh=$(( TILE - b * bh ))
                printf -v R2 '%02x' "$R"; printf -v G2 '%02x' "$G"; printf -v B2 '%02x' "$B"
                BOARD_BG+=$'pen #'"$R2$G2$B2"$'\nrectf 0 '"$by"' '"$CW"' '"$hh"$'\n'
            done
            # faint tire-wear streaks (slightly darker translucent horizontal lines)
            BOARD_BG+=$'pen #00000033\nthickness 3\n'
            BOARD_BG+=$'line 0 '"$(( y + 12 ))"' '"$CW"' '"$(( y + 12 ))"$'\n'
            BOARD_BG+=$'line 0 '"$(( y + 27 ))"' '"$CW"' '"$(( y + 27 ))"$'\n'
            BOARD_BG+=$'thickness 1\n'

            # curb edge: lighter line at top of first road row, bottom of last
            if (( r == first_road )); then
                BOARD_BG+=$'pen #6a6a72\nthickness 2\nline 0 '"$(( y + 1 ))"' '"$CW"' '"$(( y + 1 ))"$'\nthickness 1\n'
            fi
            if (( r == last_road )); then
                BOARD_BG+=$'pen #6a6a72\nthickness 2\nline 0 '"$(( y + TILE - 1 ))"' '"$CW"' '"$(( y + TILE - 1 ))"$'\nthickness 1\n'
            fi

            # dashed yellow center line only BETWEEN two adjacent road rows
            if [[ "${L_TYPE[r+1]}" == "road" ]]; then
                BOARD_BG+=$'pen #d8c84a\nthickness 2\n'
                local dx dlen=24 dgap=18 dy
                dy=$(( y + TILE ))   # boundary between this row and the next
                for ((dx=8; dx<CW; dx+=dlen+dgap)); do
                    BOARD_BG+=$'line '"$dx"' '"$dy"' '"$(( dx + dlen ))"' '"$dy"$'\n'
                done
                BOARD_BG+=$'thickness 1\n'
            fi
            ;;

        # ---------------------------------------------------------------
        safe|start)
            # green gradient #1f5e30 -> #2c7a3f, 6 bands
            local b bands=6 bh fr R G B by hh R2 G2 B2
            bh=$(( TILE / bands ))
            (( bh < 1 )) && bh=1
            for ((b=0; b<bands; b++)); do
                fr=$(( b * 255 / (bands - 1) ))
                R=$(( 31 + (44  - 31) * fr / 255 ))
                G=$(( 94 + (122 - 94) * fr / 255 ))
                B=$(( 48 + (63  - 48) * fr / 255 ))
                by=$(( y + b * bh ))
                hh=$bh
                (( b == bands - 1 )) && hh=$(( TILE - b * bh ))
                printf -v R2 '%02x' "$R"; printf -v G2 '%02x' "$G"; printf -v B2 '%02x' "$B"
                BOARD_BG+=$'pen #'"$R2$G2$B2"$'\nrectf 0 '"$by"' '"$CW"' '"$hh"$'\n'
            done
            # subtle top highlight line
            BOARD_BG+=$'pen #4a9a5aff\nthickness 1\nline 0 '"$y"' '"$CW"' '"$y"$'\n'
            # darker grass tufts (tiny trif/line)
            BOARD_BG+=$'pen #1c4a28\n'
            local gx gseed
            gseed=$(( (r * 73) % 40 ))
            for ((gx=14; gx<CW; gx+=46)); do
                local tx=$(( gx + (gseed % 18) ))
                local ty=$(( y + TILE - 4 ))
                BOARD_BG+=$'trif '"$tx"' '"$ty"' '"$(( tx + 3 ))"' '"$(( ty - 10 ))"' '"$(( tx + 6 ))"' '"$ty"$'\n'
                BOARD_BG+=$'line '"$(( tx + 8 ))"' '"$ty"' '"$(( tx + 9 ))"' '"$(( ty - 7 ))"$'\n'
            done
            # 2-3 little flowers (circf petal + colored center)
            local fcol; local fx
            local fi=0
            for ((fx=70; fx<CW; fx+=170)); do
                case $(( (fx + gseed) % 3 )) in
                    0) fcol="#e8e8ee";;
                    1) fcol="#f2c84a";;
                    *) fcol="#e87ab0";;
                esac
                local fy=$(( y + 16 + (gseed % 8) ))
                BOARD_BG+=$'pen '"$fcol"$'\ncircf '"$fx"' '"$fy"$' 3\n'
                BOARD_BG+=$'pen #f2c84a\ncircf '"$fx"' '"$fy"$' 1\n'
                ((fi++))
                (( fi >= 3 )) && break
            done
            ;;

        # ---------------------------------------------------------------
        home)
            # dark water/hedge bank gradient #10331c -> #143a20, 4 bands
            local b bands=4 bh fr R G B by hh R2 G2 B2
            bh=$(( TILE / bands ))
            (( bh < 1 )) && bh=1
            for ((b=0; b<bands; b++)); do
                fr=$(( b * 255 / (bands - 1) ))
                R=$(( 16 + (20 - 16) * fr / 255 ))
                G=$(( 51 + (58 - 51) * fr / 255 ))
                B=$(( 28 + (32 - 28) * fr / 255 ))
                by=$(( y + b * bh ))
                hh=$bh
                (( b == bands - 1 )) && hh=$(( TILE - b * bh ))
                printf -v R2 '%02x' "$R"; printf -v G2 '%02x' "$G"; printf -v B2 '%02x' "$B"
                BOARD_BG+=$'pen #'"$R2$G2$B2"$'\nrectf 0 '"$by"' '"$CW"' '"$hh"$'\n'
            done
            # hedge top highlight
            BOARD_BG+=$'pen #1e5c30ff\nthickness 1\nline 0 '"$(( y + TILE - 1 ))"' '"$CW"' '"$(( y + TILE - 1 ))"$'\n'

            # FIVE empty goal-pad recesses — geometry MUST match draw_pads
            local gap=$(( CW / 5 )) pad_m=4 pw px sh i
            pw=$(( gap - 2 * pad_m - 8 ))
            sh=$(( TILE - 2 * pad_m ))
            for ((i=0; i<5; i++)); do
                px=$(( i * gap + (gap - pw) / 2 ))
                # recessed dark slot
                BOARD_BG+=$'pen #0c2614\nrrectf '"$px"' '"$pad_m"' '"$pw"' '"$sh"$' 9\n'
                # subtle rim (darker outline + faint top-inner highlight)
                BOARD_BG+=$'pen #06160bff\nthickness 1\nrrect '"$px"' '"$pad_m"' '"$pw"' '"$sh"$' 9\n'
                BOARD_BG+=$'pen #1a4a2820\nrrect '"$(( px + 2 ))"' '"$(( pad_m + 2 ))"' '"$(( pw - 4 ))"' '"$(( sh - 4 ))"$' 7\n'
            done
            ;;
        esac
    done
    # reset thickness so nothing downstream inherits it
    BOARD_BG+=$'thickness 1\n'
}

# draw_pads — per-frame, cheap. For each filled goal pad draw a bright lily pad +
# a seated frog token, using the SAME slot geometry as build_board_bg's recesses.
draw_pads() {
    local TILE=40 CW=520
    local gap=$(( CW / 5 )) pad_m=4 pw px sh i
    pw=$(( gap - 2 * pad_m - 8 ))
    sh=$(( TILE - 2 * pad_m ))

    for ((i=0; i<5; i++)); do
        [[ "${PAD_FILLED[i]}" == "1" ]] || continue
        px=$(( i * gap + (gap - pw) / 2 ))
        local cx=$(( px + pw / 2 ))
        local cy=$(( pad_m + sh / 2 ))

        # bright lily pad + highlight notch
        CMDS+=$'pen #1f5a30\nrrectf '"$px"' '"$pad_m"' '"$pw"' '"$sh"$' 9\n'
        CMDS+=$'pen #2c7a3f\nrrectf '"$(( px + 3 ))"' '"$(( pad_m + 3 ))"' '"$(( pw - 6 ))"' '"$(( sh / 2 ))"$' 6\n'

        # seated frog token: body + two tiny eyes
        CMDS+=$'pen #36b24a\ncircf '"$cx"' '"$(( cy + 2 ))"$' 9\n'
        CMDS+=$'pen #ffffff\ncircf '"$(( cx - 4 ))"' '"$(( cy - 4 ))"$' 3\ncircf '"$(( cx + 4 ))"' '"$(( cy - 4 ))"$' 3\n'
        CMDS+=$'pen #000000\ncircf '"$(( cx - 4 ))"' '"$(( cy - 4 ))"$' 1\ncircf '"$(( cx + 4 ))"' '"$(( cy - 4 ))"$' 1\n'
    done
}

# draw_entities: every entity in each water/road row plus wrap-around ghosts.
draw_entities() {
	local r y type ew h m
	m=5
	for ((r = 0; r < ROWS; r++)); do
		type=${L_TYPE[r]}
		[[ $type == water || $type == road ]] || continue
		y=$((r * TILE + m))
		h=$((TILE - 2 * m))
		ew=${L_EW[r]}
		# ghost copies use the SAME period as the wrap in update_world
		# (span = CW + ew). Using CW here put the entering-edge ghost ew px
		# off from where the entity actually wraps to → the per-lap jerk.
		local span=$(( CW + ew ))
		local idx=0 base copy x
		for base in ${L_ENTS[r]}; do
			for copy in $((base - span)) "$base" $((base + span)); do
				x=$copy
				(( x + ew < 0 || x > CW )) && continue
				if [[ $type == water ]]; then
					_draw_log "$x" "$y" "$ew" "$h"
				else
					# seed the style with the row so different lanes show
					# different vehicle types (else every lane is red/green).
					_draw_car "$x" "$y" "$ew" "$h" "$((idx + r))" "${L_DIR[r]}"
				fi
			done
			idx=$((idx + 1))
		done
	done
}

# Log: barky wooden body with a top-lit gradient, grain streaks, knots and
# concentric end-grain tree rings at both caps.
_draw_log() {
    local x=$1 y=$2 w=$3 h=$4
    # base barky body
    CMDS+=$'pen #7a4a1f\nrrectf '"$x"' '"$y"' '"$w"' '"$h"$' 7\n'
    # faked vertical light gradient: lighter bands toward the top
    local b1=$((y + 2)) b2=$((y + 6)) b3=$((y + 10))
    CMDS+=$'pen #8a5a2b\nrrectf '"$x"' '"$b1"' '"$w"' '"$((h - 4))"$' 7\n'
    CMDS+=$'pen #9a6a36\nrrectf '"$x"' '"$y"' '"$w"$' 7 6\n'
    CMDS+=$'pen #a87842\nrrectf '"$((x + 3))"' '"$y"' '"$((w - 6))"$' 4 4\n'
    # darker waterline shadow at the bottom
    CMDS+=$'pen #5a3417\nrrectf '"$x"' '"$((y + h - 5))"' '"$w"$' 5 3\n'
    # long horizontal wood-grain streaks (varied browns, thickness 1)
    CMDS+=$'thickness 1\n'
    local g1=$((y + 9)) g2=$((y + 15)) g3=$((y + 21))
    CMDS+=$'pen #6e451f\nline '"$((x + 12))"' '"$g1"' '"$((x + w - 12))"' '"$g1"$'\n'
    CMDS+=$'pen #5e3a1a\nline '"$((x + 14))"' '"$g2"' '"$((x + w - 10))"' '"$g2"$'\n'
    CMDS+=$'pen #7d5226\nline '"$((x + 10))"' '"$g3"' '"$((x + w - 14))"' '"$g3"$'\n'
    # a couple of small knots: dark center + lighter ring
    local k1x=$((x + w / 3)) k2x=$((x + 2 * w / 3)) ky=$((y + h / 2))
    CMDS+=$'pen #8a5a2b\ncirc '"$k1x"' '"$ky"$' 4\n'
    CMDS+=$'pen #3f2710\ncircf '"$k1x"' '"$ky"$' 2\n'
    CMDS+=$'pen #3f2710\ncircf '"$k2x"' '"$((ky + 3))"$' 2\n'
    # END-GRAIN tree-rings at both caps
    local lcx=$((x + 6)) rcx=$((x + w - 6)) ecy=$((y + h / 2))
    CMDS+=$'pen #a8824e\ncirc '"$lcx"' '"$ecy"$' 9\n'
    CMDS+=$'pen #7a4a1f\ncirc '"$lcx"' '"$ecy"$' 6\n'
    CMDS+=$'pen #c7a36a\ncirc '"$lcx"' '"$ecy"$' 3\n'
    CMDS+=$'pen #a8824e\ncirc '"$rcx"' '"$ecy"$' 9\n'
    CMDS+=$'pen #7a4a1f\ncirc '"$rcx"' '"$ecy"$' 6\n'
    CMDS+=$'pen #c7a36a\ncirc '"$rcx"' '"$ecy"$' 3\n'
    # faint translucent white sheen along the top
    CMDS+=$'pen #ffffff44\nline '"$((x + 14))"' '"$((y + 3))"' '"$((x + w - 14))"' '"$((y + 3))"$'\n'
}

# Car: a glossy little vehicle. idx selects a style/colour (sedan, sports,
# pickup, taxi, van); dir (+1 right / -1 left) drives head/taillight placement.
_draw_car() {
  local x=$1 y=$2 w=$3 h=$4 idx=$5 dir=$6
  # ---- per-style palette: body / lighter top band / darkest bottom band ----
  # styles: 0 sedan, 1 sports, 2 pickup, 3 taxi/cab, 4 van
  local style=$(( idx % 5 ))
  local body light dark
  case $style in
    0) body="#d23c3c" light="#ef7a6e" dark="#8e2424" ;;  # red sedan
    1) body="#1e9e6a" light="#5fd6a2" dark="#136844" ;;  # green sports
    2) body="#3c6cc0" light="#7fa3e0" dark="#244a86" ;;  # blue pickup
    3) body="#f0b400" light="#ffe06a" dark="#a87c00" ;;  # yellow taxi
    4) body="#9c6cd2" light="#c6a0ec" dark="#6a4490" ;;  # purple van
  esac

  # leading edge x (where the vehicle is heading): right side if dir>0 else left
  local lead trail
  if (( dir >= 0 )); then lead=$(( x + w )); trail=$x
  else                    lead=$x;          trail=$(( x + w )); fi

  # ---- soft translucent shadow under chassis ----
  CMDS+=$'pen #00000038\nrrectf '"$((x + 3))"' '"$((y + h - 3))"' '"$((w - 6))"$' 7 4\n'

  # ---- body with faked top-light gradient (3 stacked rrectf bands) ----
  local b3=$(( h / 3 ))
  CMDS+=$'pen '"$dark"$'\nrrectf '"$x"' '"$y"' '"$w"' '"$h"$' 6\n'
  CMDS+=$'pen '"$body"$'\nrrectf '"$x"' '"$y"' '"$w"' '"$((h - b3))"$' 6\n'
  CMDS+=$'pen '"$light"$'\nrrectf '"$((x + 2))"' '"$((y + 1))"' '"$((w - 4))"' '"$b3"$' 5\n'

  # ---- cabin / roof + tinted window + reflection streak ----
  local rx ry rw rh
  if (( style == 2 )); then
    # pickup: short cabin on TRAILING side + open cargo bed on leading side
    rw=$(( w / 2 - 2 ))
    if (( dir >= 0 )); then rx=$(( x + 3 )); else rx=$(( x + w - rw - 3 )); fi
    ry=$(( y - 7 )); rh=11
    CMDS+=$'pen '"$dark"$'\nrrectf '"$rx"' '"$ry"' '"$rw"' '"$rh"$' 4\n'
    CMDS+=$'pen #2a3b4dcc\nrrectf '"$((rx + 2))"' '"$((ry + 2))"' '"$((rw - 4))"$' 6 3\n'
    # cargo bed lip on leading side
    local bx
    if (( dir >= 0 )); then bx=$(( x + rw + 4 )); else bx=$x; fi
    CMDS+=$'pen '"$dark"$'\nrrectf '"$bx"' '"$((y + 2))"' '"$((w / 2 - 4))"' '"$((h / 2))"$' 3\n'
  elif (( style == 4 )); then
    # van: tall full-length roof box + long window
    ry=$(( y - 9 )); rh=12
    CMDS+=$'pen '"$body"$'\nrrectf '"$((x + 2))"' '"$ry"' '"$((w - 4))"' '"$rh"$' 5\n'
    CMDS+=$'pen '"$light"$'\nrrectf '"$((x + 3))"' '"$ry"' '"$((w - 6))"$' 4 4\n'
    CMDS+=$'pen #2a3b4dcc\nrrectf '"$((x + 5))"' '"$((ry + 3))"' '"$((w - 12))"$' 6 3\n'
    CMDS+=$'pen #ffffff66\nrectf '"$((x + 7))"' '"$((ry + 4))"$' 8 3\n'
  else
    # sedan / sports / taxi: centered cabin with tinted glass + reflection
    rw=$(( w / 2 + 4 )); rx=$(( x + (w - rw) / 2 ))
    if (( style == 1 )); then ry=$(( y - 4 )); rh=9; else ry=$(( y - 7 )); rh=11; fi
    CMDS+=$'pen '"$dark"$'\nrrectf '"$rx"' '"$ry"' '"$rw"' '"$rh"$' 5\n'
    CMDS+=$'pen #243446e0\nrrectf '"$((rx + 2))"' '"$((ry + 2))"' '"$((rw - 4))"' '"$((rh - 3))"$' 3\n'
    CMDS+=$'pen #ffffff70\nbezier '"$((rx + 3))"' '"$((ry + rh - 2))"' '"$((rx + 6))"' '"$((ry + 2))"' '"$((rx + 9))"' '"$((ry + 2))"' '"$((rx + 12))"' '"$((ry + rh - 2))"$'\n'
    if (( style == 3 )); then
      # taxi: little roof sign
      CMDS+=$'pen #f8f4d8\nrrectf '"$((rx + rw / 2 - 6))"' '"$((ry - 5))"$' 12 5 2\n'
    fi
  fi

  # ---- headlights (warm) on LEADING edge, taillights (red) on TRAILING ----
  local lcx tcx ly=$(( y + h / 2 ))
  if (( dir >= 0 )); then lcx=$(( lead - 4 )); tcx=$(( trail + 4 ))
  else                    lcx=$(( lead + 4 )); tcx=$(( trail - 4 )); fi
  CMDS+=$'pen #ffe9a0\ncircf '"$lcx"' '"$ly"$' 3\n'
  CMDS+=$'pen #ff3020\ncircf '"$tcx"' '"$ly"$' 3\n'

  # ---- two wheels with lighter hubcap dot ----
  local wy=$(( y + h ))
  local w1=$(( x + 10 )) w2=$(( x + w - 10 ))
  CMDS+=$'pen #141414\ncircf '"$w1"' '"$wy"$' 5\ncircf '"$w2"' '"$wy"$' 5\n'
  CMDS+=$'pen #9aa0a6\ncircf '"$w1"' '"$wy"$' 2\ncircf '"$w2"' '"$wy"$' 2\n'
}

# draw_frog: a cute cartoon frog — drop shadow, splayed webbed legs, top-lit
# gradient body, lighter belly, domed eyes with catch-lights, nostrils, smile.
draw_frog() {
  local cx cy m
  m=5
  cx=$((FROG_PX + TILE / 2)); cy=$((FROG_PY + TILE / 2))

  # --- soft drop shadow (flattened: a wide short rrectf under the body) ---
  CMDS+=$'pen #00000030\nrrectf '"$((FROG_PX + 7))"' '"$((FROG_PY + TILE - 7))"' '"$((TILE - 14))"' 6'$' 3\n'

  # --- four splayed webbed legs poking out the corners (drawn under body) ---
  CMDS+=$'pen #1f6b2e\n'
  # back legs (lower corners, fat webbed feet)
  CMDS+=$'circf '"$((FROG_PX + m + 2))"' '"$((FROG_PY + TILE - m - 3))"$'  6\n'
  CMDS+=$'circf '"$((FROG_PX + TILE - m - 2))"' '"$((FROG_PY + TILE - m - 3))"$'  6\n'
  # front legs (upper corners, smaller)
  CMDS+=$'circf '"$((FROG_PX + m + 1))"' '"$((FROG_PY + m + 5))"$'  5\n'
  CMDS+=$'circf '"$((FROG_PX + TILE - m - 1))"' '"$((FROG_PY + m + 5))"$'  5\n'

  # --- darker green rim/shading behind body ---
  CMDS+=$'pen #2a8c3a\nrrectf '"$((FROG_PX + m - 1))"' '"$((FROG_PY + m))"' '"$((TILE - 2 * (m - 1)))"' '"$((TILE - 2 * m))"$' 10\n'

  # --- top-lit gradient body: stacked rrectf bands light->base (5 bands) ---
  CMDS+=$'pen #5fdd5f\nrrectf '"$((FROG_PX + m))"' '"$((FROG_PY + m))"' '"$((TILE - 2 * m))"' 24'$' 10\n'
  CMDS+=$'pen #54d152\nrrectf '"$((FROG_PX + m))"' '"$((FROG_PY + m + 5))"' '"$((TILE - 2 * m))"' 20'$' 9\n'
  CMDS+=$'pen #49c548\nrrectf '"$((FROG_PX + m))"' '"$((FROG_PY + m + 10))"' '"$((TILE - 2 * m))"' 15'$' 9\n'
  CMDS+=$'pen #3fbf4f\nrrectf '"$((FROG_PX + m))"' '"$((FROG_PY + m + 15))"' '"$((TILE - 2 * m))"' '"$((TILE - 2 * m - 15))"$' 9\n'

  # --- lighter belly/highlight patch (lower-center) ---
  CMDS+=$'pen #9fe07a\nrrectf '"$((cx - 6))"' '"$((cy + 4))"' 12 8'$' 5\n'

  # --- two big domed eyes on top: green dome, white sclera, dark pupil, catch-light ---
  # green eye domes
  CMDS+=$'pen #54d152\n'
  CMDS+=$'circf '"$((cx - 8))"' '"$((FROG_PY + m + 4))"$'  6\n'
  CMDS+=$'circf '"$((cx + 8))"' '"$((FROG_PY + m + 4))"$'  6\n'
  # white sclera
  CMDS+=$'pen #ffffff\n'
  CMDS+=$'circf '"$((cx - 8))"' '"$((FROG_PY + m + 3))"$'  4\n'
  CMDS+=$'circf '"$((cx + 8))"' '"$((FROG_PY + m + 3))"$'  4\n'
  # dark pupils
  CMDS+=$'pen #16261a\n'
  CMDS+=$'circf '"$((cx - 8))"' '"$((FROG_PY + m + 4))"$'  2\n'
  CMDS+=$'circf '"$((cx + 8))"' '"$((FROG_PY + m + 4))"$'  2\n'
  # catch-light dots
  CMDS+=$'pen #ffffff\n'
  CMDS+=$'pixel '"$((cx - 9))"' '"$((FROG_PY + m + 2))"$'\n'
  CMDS+=$'pixel '"$((cx + 7))"' '"$((FROG_PY + m + 2))"$'\n'

  # --- two nostrils ---
  CMDS+=$'pen #2a8c3a\n'
  CMDS+=$'pixel '"$((cx - 2))"' '"$((cy - 2))"$'\n'
  CMDS+=$'pixel '"$((cx + 2))"' '"$((cy - 2))"$'\n'

  # --- friendly curved smile (arc bowing downward) ---
  CMDS+=$'pen #16261a\nthickness 2\narc '"$cx"' '"$((cy + 2))"$' 6 20 160\nthickness 1\n'
}

# draw_hud: a tidy arcade status bar along the top edge — frog-head LIVES icons,
# centred SCORE and right-aligned LEVEL, each on a slim translucent pill so the
# goal pads behind row 0 stay visible.
draw_hud() {
  # --- LEFT: LIVES label + frog-head icons ---
  # pill sized to "LIVES" (~5 glyphs) + the life icons
  local lx=4
  local lpw=$(( 44 + LIVES * 16 + 8 ))
  CMDS+=$'pen #00000055\nrrectf '"$lx"' 2 '"$lpw"$' 22 9\n'
  CMDS+=$'pen #ffcf6b\ntext '"$((lx + 6))"$' 16 LIVES\n'
  # frog-head icons: green head + two eye dots
  local fx=$(( lx + 50 ))
  CMDS+=$'pen #4ad06a\n'
  local i
  for ((i = 0; i < LIVES; i++)); do
    local cx=$(( fx + i * 16 + 5 ))
    CMDS+=$'circf '"$cx"$' 11 5\n'
  done
  CMDS+=$'pen #ffffff\n'
  for ((i = 0; i < LIVES; i++)); do
    local cx=$(( fx + i * 16 + 5 ))
    CMDS+=$'circf '"$((cx - 2))"$' 9 1\ncircf '"$((cx + 2))"$' 9 1\n'
  done

  # --- CENTER: SCORE <n> ---
  local stxt="SCORE $SCORE"
  local sw=$(( ${#stxt} * 8 + 12 ))
  local sx=$(( CW / 2 - sw / 2 ))
  CMDS+=$'pen #00000055\nrrectf '"$sx"' 2 '"$sw"$' 22 9\n'
  CMDS+=$'pen #ffffff\ntext '"$((sx + 6))"$' 16 SCORE '"$SCORE"$'\n'

  # --- RIGHT: LEVEL <n> ---
  local ltxt="LEVEL $LEVEL"
  local lw=$(( ${#ltxt} * 8 + 12 ))
  local rx=$(( CW - lw - 4 ))
  CMDS+=$'pen #00000055\nrrectf '"$rx"' 2 '"$lw"$' 22 9\n'
  CMDS+=$'pen #ffcf6b\ntext '"$((rx + 6))"$' 16 LEVEL '"$LEVEL"$'\n'
}

# draw_end: overlay a centred "card" banner for the win / game-over screen.
draw_end() {
  local title=$1 sub=$2
  CMDS=$'size '"$SIZE_COLS"' '"$SIZE_ROWS"$'\nbg #001018\nclear\n'"$BOARD_BG"
  draw_pads; draw_entities; draw_frog; draw_hud

  # --- centered rounded card ---
  local cardw=360 cardh=120
  local cx=$(( CW / 2 - cardw / 2 ))
  local cy=$(( CH / 2 - cardh / 2 ))
  # soft drop shadow
  CMDS+=$'pen #00000066\nrrectf '"$((cx + 6))"' '"$((cy + 8))"' '"$cardw"' '"$cardh"$' 16\n'
  # card body (translucent dark)
  CMDS+=$'pen #11161fdd\nrrectf '"$cx"' '"$cy"' '"$cardw"' '"$cardh"$' 16\n'
  # bright rounded border
  CMDS+=$'pen #ffcf6b\nrrect '"$cx"' '"$cy"' '"$cardw"' '"$cardh"$' 16\n'
  # thin top sheen line
  CMDS+=$'pen #ffffff55\nline '"$((cx + 18))"' '"$((cy + 8))"' '"$((cx + cardw - 18))"' '"$((cy + 8))"$'\n'

  # --- title (large, centered, bright) ---
  local tx=$(( CW / 2 - ${#title} * 5 ))
  local ty=$(( cy + 52 ))
  CMDS+=$'pen #ffffff\ntext '"$tx"' '"$ty"' '"$title"$'\n'

  # --- decorative diamond accents flanking title ---
  local dy=$(( ty - 5 ))
  local dl=$(( tx - 18 )) dr=$(( CW / 2 + ${#title} * 5 + 10 ))
  CMDS+=$'pen #ffcf6b\npolyf '"$dl"' '"$((dy - 6))"' '"$((dl + 6))"' '"$dy"' '"$dl"' '"$((dy + 6))"' '"$((dl - 6))"' '"$dy"$'\n'
  CMDS+=$'polyf '"$dr"' '"$((dy - 6))"' '"$((dr + 6))"' '"$dy"' '"$dr"' '"$((dy + 6))"' '"$((dr - 6))"' '"$dy"$'\n'

  # --- bezier swoosh under title ---
  CMDS+=$'pen #ffcf6b88\nbezier '"$((cx + 40))"' '"$((ty + 16))"' '"$((CW / 2 - 30))"' '"$((ty + 26))"' '"$((CW / 2 + 30))"' '"$((ty + 6))"' '"$((cx + cardw - 40))"' '"$((ty + 16))"$'\n'

  # --- subtitle (muted grey, centered) ---
  local sx=$(( CW / 2 - ${#sub} * 4 ))
  CMDS+=$'pen #b0b0b0\ntext '"$sx"' '"$((ty + 40))"' '"$sub"$'\n'

  printf '\033[H\033P>g\n%s\033\\' "$CMDS"
}

# ============================================================================
# MAIN
# ============================================================================

main() {
	# --dump: render one frame to stdout (no terminal probe) for offline checks.
	if [[ ${1:-} == --dump ]]; then
		SIZE_COLS=$(( (CW + CELL_W - 1) / CELL_W ))
		SIZE_ROWS=$(( (CH + CELL_H - 1) / CELL_H ))
		init_world
		build_board_bg
		draw_frame
		echo
		return
	fi
	trap cleanup EXIT INT TERM
	setup_term
	query_cell_size
	# canvas size in cells = ceil(canvas_px / cell_px); constant for all frames.
	SIZE_COLS=$(( (CW + CELL_W - 1) / CELL_W ))
	SIZE_ROWS=$(( (CH + CELL_H - 1) / CELL_H ))

	# Static scenery (water/road/grass texture, empty goal pads) is built once —
	# lane types never change across games/levels, so the per-frame redraw just
	# prepends BOARD_BG.
	init_world
	build_board_bg

	while true; do
		init_world
		STATE=play; FRAME=0
		draw_frame
		while [[ $STATE == play ]]; do
			poll_key "$FRAMETIME"
			case $key in
				w) move_frog 0 -1 ;;
				s) move_frog 0 1 ;;
				a) move_frog -1 0 ;;
				d) move_frog 1 0 ;;
				q|Q) STATE=quit ;;
			esac
			[[ $STATE == quit ]] && break
			update_world "$FRAME"
			check_win_lose
			draw_frame
			FRAME=$((FRAME + 1))
		done

		[[ $STATE == quit ]] && break
		if [[ $STATE == win ]]; then
			draw_end "YOU WIN!" "score $SCORE  -  r: play again   q: quit"
		else
			draw_end "GAME OVER" "score $SCORE  -  r: play again   q: quit"
		fi
		# wait for restart / quit
		while true; do
			poll_key 0.2
			case $key in
				r|R) break ;;
				q|Q) STATE=quit; break ;;
			esac
		done
		[[ $STATE == quit ]] && break
	done
}

main "$@"
