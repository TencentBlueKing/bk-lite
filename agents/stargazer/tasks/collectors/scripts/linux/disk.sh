if [ $_first_module -eq 0 ]; then echo ','; fi; _first_module=0
echo '"disk":['
_disk_first=1
df -P -B1 -x tmpfs -x devtmpfs -x squashfs 2>/dev/null | tail -n +2 | while read fs size used avail pct mount; do
  case "$fs:$mount" in
    overlay:*|*:/var/lib/docker/overlay2/*/merged|*:/data/lib/docker/overlay2/*/merged|*:/run/containerd/*)
      continue
      ;;
  esac
  if [ $_disk_first -eq 0 ]; then echo ','; fi; _disk_first=0
  used_pct=$(echo "$pct" | tr -d '%')
  mount_json=$(json_escape "$mount")
  inode_pct=$(df -Pi "$mount" 2>/dev/null | tail -n 1 | awk '{print $5}' | tr -d '%')
  echo "{\"mount\":\"$mount_json\",\"total_bytes\":$size,\"free_bytes\":$avail,\"used_bytes\":$used,\"used_percent\":$used_pct,\"inodes_used_percent\":${inode_pct:-0}}"
done
echo ']'
