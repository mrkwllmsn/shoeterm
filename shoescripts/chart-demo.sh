#!/bin/sh
# Demo of shoelace - dataset charting on foot's vector-graphics protocol.
# Run this INSIDE the freshly-built foot:  ./bld/debug/foot sh chart-demo.sh
#
# For every example it prints the input you pipe in and the exact command,
# then renders the chart - so you can see how it's used at a glance.
# Pick a fixed look with e.g. SHOELACE_THEME=2.

# Locate shoelace next to this script (fall back to PATH / cwd).
dir=$(dirname "$0")
SHOELACE="$dir/shoelace"
[ -x "$SHOELACE" ] || SHOELACE=shoelace

# Force graphics: we know we're inside foot here.
export SHOELACE_FORCE=1

# Colours (built with printf so they work inside sed too).
B=$(printf '\033[1m'); D=$(printf '\033[2m')
C=$(printf '\033[1;36m'); R=$(printf '\033[0m')

# demo <label> <data> <type> <title>
#   shows the piped-in data + the command, then runs it.
demo() {
    label=$1; data=$2; type=$3; title=$4

    echo $label | shoestring
    # the data sent to shoelace on stdin, boxed
    printf '%s\n' "$data" | sed "s/^/    ${D}│${R} /"
    # the command you'd type
    printf '    %s└─ piped into:%s %sshoelace %s "%s"%s\n\n' \
        "$D" "$R" "$B" "$type" "$title" "$R"
    # the rendered chart
    printf '%s\n' "$data" | "$SHOELACE" "$type" "$title"
    printf '\n'
}

printf '\n  %sshoelace — charts in your terminal%s\n' "$B" "$R"
printf '  %s(each example shows the input it is fed, then the chart)%s\n' "$D" "$R"

demo 'bar — from CSV' \
'Mon,12
Tue,19
Wed,7
Thu,23
Fri,16
Sat,9
Sun,14' \
    bar 'Weekly visits'

demo 'line — from JSON array of objects' \
'[{"x":"Jan","y":4},{"x":"Feb","y":9},{"x":"Mar","y":7},{"x":"Apr","y":15},{"x":"May","y":22},{"x":"Jun","y":18}]' \
    line 'Signups / month'

demo 'pie — from JSON object map' \
'{"Rent":1200,"Food":420,"Transit":180,"Fun":260,"Savings":340}' \
    pie 'Monthly budget'

demo 'bar — from JSON bare numbers (labels 1..N)' \
'[5,8,6,11,9,14,12,17]' \
    bar 'Quarterly throughput'
