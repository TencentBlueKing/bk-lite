if [ $_first_module -eq 0 ]; then echo ','; fi; _first_module=0
running=0
blocked=0
sleeping=0
zombies=0
for stat in /proc/[0-9]*/stat; do
  [ -r "$stat" ] || continue
  state=$(awk '{print $3}' "$stat" 2>/dev/null)
  case "$state" in
    R) running=$((running+1)) ;;
    D) blocked=$((blocked+1)) ;;
    S|I) sleeping=$((sleeping+1)) ;;
    Z) zombies=$((zombies+1)) ;;
  esac
done
echo "\"processes\":{\"running\":$running,\"blocked\":$blocked,\"sleeping\":$sleeping,\"zombies\":$zombies}"
