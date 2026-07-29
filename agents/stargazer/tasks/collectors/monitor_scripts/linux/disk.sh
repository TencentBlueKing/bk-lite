# Host Remote 监控专属磁盘采集：保留文件系统类型，供监控白黑名单过滤。
if [ $_first_module -eq 0 ]; then echo ','; fi; _first_module=0
echo '"disk":['
_disk_first=1
disk_number_or_zero() {
  case "$1" in
    ''|*[!0-9]*)
      echo 0
      ;;
    *)
      echo "$1"
      ;;
  esac
}
df -PT -B1 2>/dev/null | tail -n +2 | while read fs fstype size used avail pct mount; do
  if [ $_disk_first -eq 0 ]; then echo ','; fi; _disk_first=0
  used_pct=$(echo "$pct" | tr -d '%')
  size=$(disk_number_or_zero "$size")
  used=$(disk_number_or_zero "$used")
  avail=$(disk_number_or_zero "$avail")
  used_pct=$(disk_number_or_zero "$used_pct")
  mount_json=$(json_escape "$mount")
  fstype_json=$(json_escape "$fstype")
  inode_pct=$(df -Pi "$mount" 2>/dev/null | tail -n 1 | awk '{print $5}' | tr -d '%')
  inode_pct=$(disk_number_or_zero "$inode_pct")
  echo "{\"mount\":\"$mount_json\",\"path\":\"$mount_json\",\"fstype\":\"$fstype_json\",\"total_bytes\":$size,\"free_bytes\":$avail,\"used_bytes\":$used,\"used_percent\":$used_pct,\"inodes_used_percent\":${inode_pct:-0}}"
done
echo ']'
