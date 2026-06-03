if [ $_first_module -eq 0 ]; then echo ','; fi; _first_module=0
cpu_count=$(nproc 2>/dev/null || grep -c ^processor /proc/cpuinfo)
read cpu_user cpu_nice cpu_system cpu_idle cpu_iowait cpu_irq cpu_softirq _ < <(head -1 /proc/stat | awk '{print $2,$3,$4,$5,$6,$7,$8}')
cpu_total=$((cpu_user+cpu_nice+cpu_system+cpu_idle+cpu_iowait+cpu_irq+cpu_softirq))
cpu_used=$((cpu_total-cpu_idle))
if [ $cpu_total -gt 0 ]; then
  cpu_usage=$(awk "BEGIN{printf \"%.2f\", $cpu_used/$cpu_total*100}")
else
  cpu_usage="0.00"
fi
load_1="" ; load_5="" ; load_15=""
if [ -f /proc/loadavg ]; then
  read load_1 load_5 load_15 _ < /proc/loadavg
fi
echo "\"cpu\":{\"usage_percent\":$cpu_usage,\"core_count\":$cpu_count,\"load_1m\":${load_1:-0},\"load_5m\":${load_5:-0},\"load_15m\":${load_15:-0}}"
