if [ $_first_module -eq 0 ]; then echo ','; fi; _first_module=0
cpu_count=$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || grep -c ^processor /proc/cpuinfo 2>/dev/null || printf '0')
read _ cpu_user_1 cpu_nice_1 cpu_system_1 cpu_idle_1 cpu_iowait_1 cpu_irq_1 cpu_softirq_1 cpu_steal_1 _ < /proc/stat
sleep 1
read _ cpu_user_2 cpu_nice_2 cpu_system_2 cpu_idle_2 cpu_iowait_2 cpu_irq_2 cpu_softirq_2 cpu_steal_2 _ < /proc/stat

prev_idle=$((cpu_idle_1+cpu_iowait_1))
curr_idle=$((cpu_idle_2+cpu_iowait_2))
prev_non_idle=$((cpu_user_1+cpu_nice_1+cpu_system_1+cpu_irq_1+cpu_softirq_1+cpu_steal_1))
curr_non_idle=$((cpu_user_2+cpu_nice_2+cpu_system_2+cpu_irq_2+cpu_softirq_2+cpu_steal_2))
prev_total=$((prev_idle+prev_non_idle))
curr_total=$((curr_idle+curr_non_idle))

total_delta=$((curr_total-prev_total))
idle_delta=$((curr_idle-prev_idle))
used_delta=$((total_delta-idle_delta))
if [ $total_delta -gt 0 ]; then
  cpu_usage=$(awk "BEGIN{printf \"%.2f\", $used_delta/$total_delta*100}")
else
  cpu_usage="0.00"
fi
load_1="" ; load_5="" ; load_15=""
if [ -f /proc/loadavg ]; then
  read load_1 load_5 load_15 _ < /proc/loadavg
fi
echo "\"cpu\":{\"usage_percent\":$cpu_usage,\"core_count\":$cpu_count,\"load_1m\":${load_1:-0},\"load_5m\":${load_5:-0},\"load_15m\":${load_15:-0}}"
