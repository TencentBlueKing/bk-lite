if [ $_first_module -eq 0 ]; then echo ','; fi; _first_module=0
uptime_seconds=$(awk '{printf "%.0f", $1}' /proc/uptime 2>/dev/null || printf '0')
load_1=0 ; load_5=0 ; load_15=0
if [ -f /proc/loadavg ]; then
  read load_1 load_5 load_15 _ < /proc/loadavg
fi
echo "\"system\":{\"uptime_seconds\":$uptime_seconds,\"load1\":$load_1,\"load5\":$load_5,\"load15\":$load_15}"
