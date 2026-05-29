if [ $_first_module -eq 0 ]; then echo ','; fi; _first_module=0
echo '"disk":['
_disk_first=1
df -P -B1 -x tmpfs -x devtmpfs -x squashfs 2>/dev/null | tail -n +2 | while read fs size used avail pct mount; do
  if [ $_disk_first -eq 0 ]; then echo ','; fi; _disk_first=0
  used_pct=$(echo "$pct" | tr -d '%')
  echo "{\"mount\":\"$mount\",\"total_bytes\":$size,\"used_bytes\":$used,\"used_percent\":$used_pct}"
done
echo ']'
