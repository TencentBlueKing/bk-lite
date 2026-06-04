if [ $_first_module -eq 0 ]; then echo ','; fi; _first_module=0
echo '"net":['
_net_first=1
cat /proc/net/dev | tail -n +3 | while read line; do
  iface=$(echo "$line" | awk -F: '{print $1}' | tr -d ' ')
  case "$iface" in
    lo|docker0|br-*|veth*|cni*|flannel*|cali*|tunl*|virbr*|vnet*)
      continue
      ;;
  esac
  stats=$(echo "$line" | awk -F: '{print $2}')
  rx_bytes=$(echo "$stats" | awk '{print $1}')
  rx_errors=$(echo "$stats" | awk '{print $3}')
  tx_bytes=$(echo "$stats" | awk '{print $9}')
  tx_errors=$(echo "$stats" | awk '{print $11}')
  if [ $_net_first -eq 0 ]; then echo ','; fi; _net_first=0
  iface_json=$(json_escape "$iface")
  echo "{\"interface\":\"$iface_json\",\"rx_bytes\":$rx_bytes,\"tx_bytes\":$tx_bytes,\"rx_errors\":$rx_errors,\"tx_errors\":$tx_errors}"
done
echo ']'
