#!/bin/sh
# Docker 配置采集脚本（POSIX sh 版本）
# 输出每行一个 JSON，交由 SSHPlugin 聚合

TRUE_STR=true
FALSE_STR=false

escape_json() {
  printf '%s' "$1" | awk '
    BEGIN { ORS="" }
    {
      if (NR > 1) {
        printf "\\n"
      }
      len = length($0)
      for (i = 1; i <= len; i++) {
        c = substr($0, i, 1)
        if (c == "\\") {
          printf "\\\\"
        } else if (c == "\"") {
          printf "\\\""
        } else if (c == "\b") {
          printf "\\b"
        } else if (c == "\f") {
          printf "\\f"
        } else if (c == "\r") {
          printf "\\r"
        } else if (c == "\t") {
          printf "\\t"
        } else {
          printf "%s", c
        }
      }
    }
  '
}

get_host_ip() {
  ip=""

  if command -v ip >/dev/null 2>&1; then
    ip=$(ip route get 1 2>/dev/null | awk '/src/ {for (i = 1; i <= NF; i++) { if ($i == "src") { print $(i+1); exit } }}') || ip=""
  fi

  if [ -z "$ip" ] && command -v hostname >/dev/null 2>&1; then
    ip=$(hostname -I 2>/dev/null | awk 'NF { print $1; exit }') || ip=""
    if [ -z "$ip" ]; then
      ip=$(hostname -i 2>/dev/null | awk 'NF { print $1; exit }') || ip=""
    fi
  fi

  if [ -z "$ip" ] && command -v ifconfig >/dev/null 2>&1; then
    ip=$(ifconfig 2>/dev/null | awk '/inet / && $2 != "127.0.0.1" { print $2; exit }') || ip=""
  fi

  if [ -z "$ip" ]; then
    ip="127.0.0.1"
  fi

  printf '%s\n' "$ip"
}

build_ports_json() {
  cid="$1"
  host_ip="$2"
  ports_output=$("$DOCKER_BIN" port "$cid" 2>/dev/null || true)

  PORTS_JSON="["
  PORTS_DISPLAY=""
  PORT_PRIMARY=""
  first=1

  if [ -n "$ports_output" ]; then
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      spec=${line%% *}
      rest=${line#*-> }
      if [ "$rest" = "$line" ]; then
        host_ip_map=""
        host_port_map=""
      else
        host_ip_map=${rest%:*}
        host_port_map=${rest##*:}
      fi
      protocol=${spec##*/}
      container_port=${spec%/*}
      if [ "$container_port" = "$spec" ]; then
        container_port=""
      fi
      host_ip_final="$host_ip"
      if [ -n "$host_ip_map" ]; then
        host_ip_final="$host_ip_map"
      fi
      host_port_final="$host_port_map"

      if [ "$first" -eq 1 ]; then
        first=0
      else
        PORTS_JSON=${PORTS_JSON},
      fi

      port_entry=$(printf '{"host_ip":"%s","host_port":"%s","container_port":"%s","protocol":"%s"}' \
        "$(escape_json "$host_ip_final")" \
        "$(escape_json "$host_port_final")" \
        "$(escape_json "$container_port")" \
        "$(escape_json "$protocol")")

  PORTS_JSON=${PORTS_JSON}$port_entry

      # 构造 docker ps 风格的字符串
      display_part=""
      if [ -n "$host_port_final" ]; then
        if [ -n "$host_ip_final" ]; then
          display_part="$host_ip_final:$host_port_final"
        else
          display_part="$host_port_final"
        fi
        if [ -n "$container_port" ]; then
          display_part="$display_part->$container_port/$protocol"
        fi
      else
        if [ -n "$container_port" ]; then
          display_part="$container_port/$protocol"
        fi
      fi

      if [ -n "$display_part" ]; then
        if [ -z "$PORTS_DISPLAY" ]; then
          PORTS_DISPLAY="$display_part"
        else
          PORTS_DISPLAY="$PORTS_DISPLAY, $display_part"
        fi
      fi

      if [ -z "$PORT_PRIMARY" ] && [ -n "$host_port_final" ]; then
        PORT_PRIMARY="$host_port_final"
      fi
    done <<PORTS_BLOCK
$ports_output
PORTS_BLOCK
  fi

  PORTS_JSON=${PORTS_JSON}]
}

build_mounts_json() {
  cid="$1"
  mounts_data=$("$DOCKER_BIN" inspect --format '{{range .Mounts}}{{printf "%s|%s|%s|%s|%t\n" .Type .Source .Destination .Mode .RW}}{{end}}' "$cid" 2>/dev/null || true)

  MOUNTS_JSON="["
  first=1

  if [ -n "$mounts_data" ]; then
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      old_ifs=$IFS
      IFS='|'
      set -- $line
      IFS=$old_ifs
      type=${1:-}
      source=${2:-}
      dest=${3:-}
      mode=${4:-}
      rw_flag=${5:-}
      bool_value=$FALSE_STR
      if [ "$rw_flag" = "true" ] || [ "$rw_flag" = "True" ]; then
        bool_value=$TRUE_STR
      fi

      if [ "$first" -eq 1 ]; then
        first=0
      else
        MOUNTS_JSON=${MOUNTS_JSON},
      fi

      mount_entry=$(printf '{"type":"%s","source":"%s","destination":"%s","mode":"%s","rw":%s}' \
        "$(escape_json "$type")" \
        "$(escape_json "$source")" \
        "$(escape_json "$dest")" \
        "$(escape_json "$mode")" \
        "$bool_value")

  MOUNTS_JSON=${MOUNTS_JSON}$mount_entry
    done <<MOUNTS_BLOCK
$mounts_data
MOUNTS_BLOCK
  fi

  MOUNTS_JSON=${MOUNTS_JSON}]
}

build_networks_json() {
  cid="$1"
  networks_data=$("$DOCKER_BIN" inspect --format '{{range $name, $conf := .NetworkSettings.Networks}}{{printf "%s|%s|%s|%s\n" $name $conf.Driver $conf.IPAddress $conf.MacAddress}}{{end}}' "$cid" 2>/dev/null || true)

  NETWORKS_JSON="["
  NETWORKS_DISPLAY=""
  first=1

  if [ -n "$networks_data" ]; then
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      old_ifs=$IFS
      IFS='|'
      set -- $line
      IFS=$old_ifs
      name=${1:-}
      driver=${2:-}
      ip_addr=${3:-}
      mac_addr=${4:-}

      if [ "$first" -eq 1 ]; then
        first=0
      else
        NETWORKS_JSON=${NETWORKS_JSON},
      fi

      network_entry=$(printf '{"name":"%s","driver":"%s","ip_address":"%s","mac_address":"%s"}' \
        "$(escape_json "$name")" \
        "$(escape_json "$driver")" \
        "$(escape_json "$ip_addr")" \
        "$(escape_json "$mac_addr")")

  NETWORKS_JSON=${NETWORKS_JSON}$network_entry

      if [ -z "$NETWORKS_DISPLAY" ]; then
        NETWORKS_DISPLAY="$name"
      else
        NETWORKS_DISPLAY="$NETWORKS_DISPLAY,$name"
      fi
    done <<NETWORKS_BLOCK
$networks_data
NETWORKS_BLOCK
  fi

  NETWORKS_JSON=${NETWORKS_JSON}]
}

DOCKER_BIN=$(command -v docker || true)
if [ -z "$DOCKER_BIN" ]; then
  printf '{"cmdb_collect_error":"docker command not found"}\n'
  exit 0
fi

if ! "$DOCKER_BIN" ps >/dev/null 2>&1; then
  printf '{"cmdb_collect_error":"docker command cannot run (permission denied?)"}\n'
  exit 0
fi

CONTAINER_IDS=$("$DOCKER_BIN" ps -q 2>/dev/null || true)
if [ -z "$CONTAINER_IDS" ]; then
  exit 0
fi

HOST_IP=${DOCKER_COLLECT_HOST_IP:-$(get_host_ip)}

for cid in $CONTAINER_IDS; do
  CONTAINER_ID=$cid
  local_suffix=$(printf '%s' "$CONTAINER_ID" | cut -c1-12)
  INST_NAME="${HOST_IP}_${local_suffix}"

  CREATED=$("$DOCKER_BIN" inspect --format '{{.Created}}' "$cid" 2>/dev/null || true)
  IMAGE_TAG_FULL=$("$DOCKER_BIN" inspect --format '{{if .RepoTags}}{{index .RepoTags 0}}{{else}}{{.Config.Image}}{{end}}' "$cid" 2>/dev/null || true)
  IMAGE_DIGEST=$("$DOCKER_BIN" inspect --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{end}}' "$cid" 2>/dev/null || true)
  CONFIG_IMAGE=$("$DOCKER_BIN" inspect --format '{{.Config.Image}}' "$cid" 2>/dev/null || true)

  # 回退逻辑：若 RepoTags 为空，尝试使用 Config.Image，再尝试使用镜像 ID
  if [ -z "$IMAGE_TAG_FULL" ] && [ -n "$CONFIG_IMAGE" ]; then
    IMAGE_TAG_FULL="$CONFIG_IMAGE"
  fi
  if [ -z "$IMAGE_TAG_FULL" ]; then
    IMAGE_TAG_FULL=$("$DOCKER_BIN" inspect --format '{{.Image}}' "$cid" 2>/dev/null || true)
  fi
  COMMAND_RAW=$("$DOCKER_BIN" inspect --format '{{range .Config.Entrypoint}}{{printf "%s " .}}{{end}}{{range .Config.Cmd}}{{printf "%s " .}}{{end}}' "$cid" 2>/dev/null || true)
  COMMAND_RAW=$(printf '%s\n' "$COMMAND_RAW" | sed 's/[[:space:]]*$//')

  IMAGE_NAME=$IMAGE_TAG_FULL
  IMAGE_TAG=""
  case $IMAGE_TAG_FULL in
    *:*)
      IMAGE_NAME=${IMAGE_TAG_FULL%:*}
      IMAGE_TAG=${IMAGE_TAG_FULL##*:}
      ;;
  esac

  # 若解析后仍为空，使用 Config.Image 或镜像 ID 兜底
  if [ -z "$IMAGE_NAME" ] && [ -n "$CONFIG_IMAGE" ]; then
    IMAGE_NAME="$CONFIG_IMAGE"
  fi
  if [ -z "$IMAGE_NAME" ] && [ -n "$IMAGE_DIGEST" ]; then
    IMAGE_NAME="$IMAGE_DIGEST"
  fi
  if [ -z "$IMAGE_NAME" ]; then
    IMAGE_NAME="unknown"
  fi

  if [ -z "$IMAGE_DIGEST" ]; then
    IMAGE_DIGEST=$("$DOCKER_BIN" inspect --format '{{.Image}}' "$cid" 2>/dev/null || true)
  fi

  build_ports_json "$cid" "$HOST_IP"
  build_mounts_json "$cid"
  build_networks_json "$cid"

  INST_NAME_ESC=$(escape_json "$INST_NAME")
  CONTAINER_ID_ESC=$(escape_json "$CONTAINER_ID")
  HOST_IP_ESC=$(escape_json "$HOST_IP")
  COMMAND_ESC=$(escape_json "$COMMAND_RAW")
  CREATED_ESC=$(escape_json "$CREATED")
  TOP_PORT_ESC=$(escape_json "$PORT_PRIMARY")

  # image 输出改为类似 docker ps 的字符串：name[:tag]，若缺失则用 digest，再无则 unknown
  IMAGE_DISPLAY="$IMAGE_NAME"
  if [ -n "$IMAGE_TAG" ]; then
    IMAGE_DISPLAY="$IMAGE_NAME:$IMAGE_TAG"
  fi
  if [ -z "$IMAGE_DISPLAY" ] && [ -n "$IMAGE_DIGEST" ]; then
    IMAGE_DISPLAY="$IMAGE_DIGEST"
  fi
  if [ -z "$IMAGE_DISPLAY" ]; then
    IMAGE_DISPLAY="unknown"
  fi
  IMAGE_DISPLAY_ESC=$(escape_json "$IMAGE_DISPLAY")

  # 其他字段：ports/mounts 为转义后的 JSON 字符串；networks 为名称逗号串；ports_display 为 docker ps 风格串
  PORTS_DISPLAY_ESC=$(escape_json "$PORTS_DISPLAY")
  PORTS_JSON_ESC=$(escape_json "$PORTS_JSON")
  MOUNTS_JSON_ESC=$(escape_json "$MOUNTS_JSON")
  NETWORKS_DISPLAY_ESC=$(escape_json "$NETWORKS_DISPLAY")

  printf '{"inst_name":"%s","container_id":"%s","ip_addr":"%s","port":"%s","image":"%s","created":"%s","command":"%s","ports":"%s","mounts":"%s","networks":"%s"}\n' \
    "$INST_NAME_ESC" \
    "$CONTAINER_ID_ESC" \
    "$HOST_IP_ESC" \
    "$TOP_PORT_ESC" \
    "$IMAGE_DISPLAY_ESC" \
    "$CREATED_ESC" \
    "$COMMAND_ESC" \
    "$PORTS_DISPLAY_ESC" \
    "$MOUNTS_JSON_ESC" \
    "$NETWORKS_DISPLAY_ESC"
done
