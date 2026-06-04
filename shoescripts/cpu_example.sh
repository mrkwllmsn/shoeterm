ps -eo %cpu,comm --no-headers | awk '{cpu[$2]+=$1} END {for (cmd in cpu) print cmd "," cpu[cmd]}' | sort -t, -k2,2nr | head -6 | shoelace pie "System CPU Usage"
ps -eo %cpu,comm --no-headers | awk '{cpu[$2]+=$1} END {for (cmd in cpu) print cmd "," cpu[cmd]}' | sort -t, -k2,2nr | head -6 | shoetable "System CPU Usage"

ps -eo %mem,comm --sort=-%mem --no-headers \
| head -6 \
| awk '{print $2 "," $1}' \
| shoelace pie "System Memory Usage"

ps -eo %mem,comm --sort=-%mem --no-headers \
| head -6 \
| awk '{print $2 "," $1}' \
| shoetable "System Memory Usage"

 ps -ef | head -11 | shoetable "Processes"
