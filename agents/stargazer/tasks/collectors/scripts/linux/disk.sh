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
df -PT -B1 -x tmpfs -x devtmpfs -x squashfs 2>/dev/null | tail -n +2 | while read fs fstype size used avail pct mount; do
  case "$fs:$mount" in
    overlay:*|*:/var/lib/docker/overlay2/*/merged|*:/data/lib/docker/overlay2/*/merged|*:/run/containerd/*)
      continue
      ;;
  esac
  if [ $_disk_first -eq 0 ]; then echo ','; fi; _disk_first=0
  used_pct=$(echo "$pct" | tr -d '%')
  size=$(disk_number_or_zero "$size")
  used=$(disk_number_or_zero "$used")
  avail=$(disk_number_or_zero "$avail")
  used_pct=$(disk_number_or_zero "$used_pct")
  mount_json=$(json_escape "$mount")
  inode_pct=$(df -Pi "$mount" 2>/dev/null | tail -n 1 | awk '{print $5}' | tr -d '%')
  inode_pct=$(disk_number_or_zero "$inode_pct")
  fstype_json=$(json_escape "$fstype")
  echo "{\"mount\":\"$mount_json\",\"path\":\"$mount_json\",\"fstype\":\"$fstype_json\",\"total_bytes\":$size,\"free_bytes\":$avail,\"used_bytes\":$used,\"used_percent\":$used_pct,\"inodes_used_percent\":${inode_pct:-0}}"
done
echo ']'
