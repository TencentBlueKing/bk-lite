if [ $_first_module -eq 0 ]; then echo ','; fi; _first_module=0
echo '"diskio":['
_diskio_first=1
while read major minor device reads reads_merged sectors_read read_ms writes writes_merged sectors_written write_ms io_in_progress io_ms weighted_io_ms rest; do
  case "$device" in
    loop*|ram*|sr*|dm-*)
      continue
      ;;
  esac
  if [ $_diskio_first -eq 0 ]; then echo ','; fi; _diskio_first=0
  device_json=$(json_escape "$device")
  read_bytes=$((sectors_read*512))
  write_bytes=$((sectors_written*512))
  echo "{\"device\":\"$device_json\",\"reads\":$reads,\"writes\":$writes,\"read_bytes\":$read_bytes,\"write_bytes\":$write_bytes,\"io_time_ms\":$io_ms,\"read_time_ms\":$read_ms,\"write_time_ms\":$write_ms}"
done < /proc/diskstats
echo ']'
