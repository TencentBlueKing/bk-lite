#!/bin/sh
set -u

# Pure shell Redis discovery (POSIX): standalone/sentinel/cluster + topo_mode, cluster_uuid, slaves, master.
# Env: REDIS_TARGET_HOST, REDIS_TARGET_PORTS, REDIS_DISCOVER_FROM_PROCESS, BK_HOST_INNERIP, REDIS_CLI_BIN
# Auth (injected by runner): REDISCLI_AUTH, REDIS_USER (ACL)
# Storage: in-memory only (no temp files). _ASSOC = name<TAB>key<TAB>value per line; list vars = newline-separated.

REDIS_CLI="${REDIS_CLI_BIN:-redis-cli}"
REDIS_TARGET_HOST="${REDIS_TARGET_HOST:-127.0.0.1}"
REDIS_TARGET_PORTS="${REDIS_TARGET_PORTS:-6379,6389,26379,26380,26381,7000-7005}"
REDIS_DISCOVER_FROM_PROCESS="${REDIS_DISCOVER_FROM_PROCESS:-yes}"
BK_HOST_INNERIP="${BK_HOST_INNERIP:-}"

# Input validation: allow only safe chars to reduce injection risk (type/format only; no shell execution from vars).
_safe_host() { echo "$1" | tr -d '\r\n' | sed -n 's/^[0-9a-zA-Z._:-]*$/\0/p'; }
_safe_port() { echo "$1" | tr -d '\r\n' | sed -n 's/^[0-9]*$/\0/p' | awk -v max=65535 '$1>=1 && $1<=max {print $1}'; }
_safe_redis_user() { echo "$1" | tr -d '\r\n' | sed -n 's/^[0-9a-zA-Z_]*$/\0/p'; }
_safe_cli_path() { echo "$1" | tr -d '\r\n' | sed -n 's/^[0-9a-zA-Z./_-]*$/\0/p'; }
_safe_path() {
  p=$(printf '%s' "$1" | tr -d '\r\n'); [ -z "$p" ] && return 0
  case "$p" in *..*) return 0;; esac
  echo "$p" | sed -n 's/^[0-9a-zA-Z./_[[:space:]]-]*$/\0/p'
}
_safe_sentinel_name() { echo "$1" | tr -d '\r\n' | sed -n 's/^[0-9a-zA-Z_-]*$/\0/p'; }

# Whitelist: only these Redis commands (auth via REDISCLI_AUTH env only, never -a on cmdline).
_redis_cmd_ok() {
  [ $# -ge 1 ] || return 1
  case "$1" in
    PING) [ $# -eq 1 ] && return 0 ;;
    INFO) [ $# -eq 2 ] && case "$2" in replication|sentinel|server) return 0 ;; esac ;;
    CONFIG) [ $# -eq 3 ] && [ "$2" = "GET" ] && case "$3" in maxclients|maxmemory|config_file) return 0 ;; esac ;;
    CLUSTER) [ $# -eq 2 ] && case "$2" in INFO|NODES) return 0 ;; esac ;;
    SENTINEL)
      [ $# -eq 2 ] && [ "$2" = "MASTERS" ] && return 0
      [ $# -eq 3 ] && case "$2" in REPLICAS|SENTINELS)
        _sn=$(_safe_sentinel_name "$3"); [ -n "$_sn" ] && return 0
      ;; esac ;;
  esac
  return 1
}

_tab=$(printf '\t')
_ASSOC=""

# Return field n (1-based) of line with delimiter d
field() { echo "$1" | cut -d"$2" -f"$3"; }

# Associative array helpers (in-memory): name key [value]. Format per line: name\tkey\tvalue.
assoc_init() { :; }
assoc_set() {
  _an="$1"; _k=$(printf '%s' "$2" | tr -d '=\n\r\t'); _v=$(printf '%s' "$3" | tr -d '\n\r\t')
  _ASSOC=$(echo "$_ASSOC" | while IFS= read -r _line; do
    [ -z "$_line" ] && continue
    _n="${_line%%$_tab*}"; _r="${_line#*$_tab}"; _k2="${_r%%$_tab*}"; [ "$_n" = "$_an" ] && [ "$_k2" = "$_k" ] && continue; echo "$_line"
  done)
  _ASSOC="${_ASSOC}${_ASSOC:+
}${_an}${_tab}${_k}${_tab}${_v}"
}
assoc_get() {
  _an="$1"; _k=$(printf '%s' "$2" | tr -d '=\n\r\t')
  echo "$_ASSOC" | while IFS= read -r _line; do
    [ -z "$_line" ] && continue
    _n="${_line%%$_tab*}"; _r="${_line#*$_tab}"; _k2="${_r%%$_tab*}"; _v="${_r#*$_tab}"
    [ "$_n" = "$_an" ] && [ "$_k2" = "$_k" ] && echo "$_v" && break
  done
}
assoc_keys() {
  _an="$1"
  echo "$_ASSOC" | while IFS= read -r _line; do
    [ -z "$_line" ] && continue
    _n="${_line%%$_tab*}"; _r="${_line#*$_tab}"; _k2="${_r%%$_tab*}"; [ "$_n" = "$_an" ] && echo "$_k2"
  done
}

run_redis() {
  host="$1" port="$2"; shift 2
  host=$(_safe_host "$host"); port=$(_safe_port "$port")
  [ -z "$host" ] || [ -z "$port" ] && return 0
  _redis_cmd_ok "$@" || return 0
  _cli=$(_safe_cli_path "$REDIS_CLI"); [ -z "$_cli" ] && return 0
  if [ -n "${REDIS_USER:-}" ]; then
    _user=$(_safe_redis_user "$REDIS_USER"); [ -z "$_user" ] && return 0
    "$_cli" -h "$host" -p "$port" --user "$_user" "$@" 2>/dev/null
  else
    "$_cli" -h "$host" -p "$port" "$@" 2>/dev/null
  fi
}

parse_info() {
  while IFS= read -r line; do
    line=$(printf '%s' "$line" | tr -d '\r')
    case "$line" in *:*) echo "$line"; ;; esac
  done
}

config_get_value() { sed -n '2p' 2>/dev/null | tr -d '\r'; }

parse_ports() {
  spec="${1:-}"; _out=""
  printf '%s' "$spec" | tr ',' '\n' | tr -d '\r' | while read -r part; do
    part=$(echo "$part" | tr -d ' ')
    [ -z "$part" ] && continue
    case "$part" in
      *-*) start=${part%-*}; end=${part#*-}
        [ "$start" -gt "$end" ] 2>/dev/null && { _t=$start; start=$end; end=$_t; }
        p=$start
        while [ $p -le $end ]; do
          [ $p -ge 1 ] && [ $p -le 65535 ] 2>/dev/null && echo $p
          p=$((p+1))
        done ;;
      *) [ "$part" -ge 1 ] 2>/dev/null && [ "$part" -le 65535 ] 2>/dev/null && echo "$part"; ;;
    esac
  done | sort -nu 2>/dev/null
}

# Output "port|install_path" per line (path = first word of redis-server command)
discover_ports_from_process() {
  if command -v ps >/dev/null 2>&1; then
    ps -e -o args= 2>/dev/null | while IFS= read -r line; do
      case "$line" in *redis-server*)
        port=$(echo "$line" | sed -n 's/.*:\([0-9]\{1,5\}\).*/\1/p')
        path=$(echo "$line" | awk '{print $1}')
        [ -n "$port" ] && [ -n "$path" ] && echo "${port}|${path}"
      ;; esac
    done
  fi
}

# Detect OS: Linux, Darwin (macOS), Windows (MINGW/MSYS/CYGWIN)
_redis_disc_os=""
_redis_disc_os_done=""
detect_os() {
  [ -n "$_redis_disc_os_done" ] && return 0
  _u=$(uname -s 2>/dev/null) || _u=""
  case "$_u" in
    Linux*) _redis_disc_os="linux"; ;;
    Darwin*) _redis_disc_os="macos"; ;;
    MINGW*|MSYS*|CYGWIN*|*_NT-*) _redis_disc_os="windows"; ;;
    *) _redis_disc_os=""; ;;
  esac
  _redis_disc_os_done=1
}

# Get install_path for port: from port_path file, or resolve by OS (Linux/macOS/Windows)
get_install_path_for_port() {
  port="$1"
  [ -n "$port" ] || return 0
  if [ -n "$_port_path" ]; then
    _p=$(echo "$_port_path" | grep -F "^${port}|" 2>/dev/null | head -1 | cut -d'|' -f2)
    [ -n "$_p" ] && printf '%s\n' "$_p" && return 0
  fi
  detect_os
  pid=""
  case "$_redis_disc_os" in
    linux)
      if command -v lsof >/dev/null 2>&1; then
        pid=$(lsof -i :"$port" -t 2>/dev/null | head -1)
      elif [ -d /proc ] && command -v ss >/dev/null 2>&1; then
        pid=$(ss -tlnp 2>/dev/null | awk -v p=":$port" '$4 ~ p { gsub(/.*pid=/,""); gsub(/,.*/,""); print; exit }')
      fi
      [ -n "$pid" ] && [ -r "/proc/$pid/exe" ] && readlink "/proc/$pid/exe" 2>/dev/null
      ;;
    macos)
      if command -v lsof >/dev/null 2>&1; then
        pid=$(lsof -i :"$port" -t 2>/dev/null | head -1)
        if [ -n "$pid" ]; then
          lsof -p "$pid" 2>/dev/null | awk '/ txt / {print $NF; exit}'
        fi
      fi
      ;;
    windows)
      pid=$(netstat -ano 2>/dev/null | grep ":$port" | grep -i LISTENING | awk '{print $NF}' | head -1)
      if [ -n "$pid" ]; then
        _exe=$(wmic process where "processid=$pid" get executablepath 2>/dev/null | sed -n '2p' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//' | tr -d '\r')
        [ -n "$_exe" ] && printf '%s\n' "$_exe"
      fi
      ;;
    *) ;;
  esac
}

# Parse redis version from redis-server --version output (stdin or first arg)
parse_redis_version() { sed -n 's/.*v=\([0-9][0-9.]*\).*/\1/p' | head -1; }

# Get version string from redis-server binary (--version or -v); path must pass _safe_path (no .., safe chars).
get_version_from_path() {
  path=$(_safe_path "$1"); [ -z "$path" ] && return 0
  out=""
  detect_os
  case "$_redis_disc_os" in
    windows)
      out=$(cmd //c "\"$path\" --version" 2>/dev/null) || out=$(cmd //c "\"$path\" -v" 2>/dev/null)
      ;;
    *)
      out=$("$path" --version 2>/dev/null) || out=$("$path" -v 2>/dev/null)
      ;;
  esac
  echo "$out" | parse_redis_version
}

# When target is local and Docker is available: find container publishing port, get Redis version via docker exec
get_version_via_docker() {
  port="$1"
  [ -z "$port" ] && return 0
  command -v docker >/dev/null 2>&1 || return 0
  cid=$(docker ps -q 2>/dev/null | while read -r id; do
    docker port "$id" 2>/dev/null | grep -qE ":$port$|/$port/" && echo "$id" && break
  done)
  [ -z "$cid" ] && return 0
  out=$(docker exec "$cid" redis-server --version 2>/dev/null) || out=$(docker exec "$cid" redis-server -v 2>/dev/null)
  echo "$out" | parse_redis_version
}

probe_port() { command -v nc >/dev/null 2>&1 && nc -z "$1" "$2" 2>/dev/null || true; }

detect_mode() {
  info_sentinel="$1" cluster_state="$2" role="$3"
  sentinel_masters=$(echo "$info_sentinel" | parse_info | grep -E '^sentinel_masters:' | cut -d: -f2 | tr -d '\r')
  [ -n "$sentinel_masters" ] && [ "$sentinel_masters" -gt 0 ] 2>/dev/null && { echo "sentinel"; return; }
  [ -n "$cluster_state" ] && { echo "cluster"; return; }
  case "$role" in master|slave) echo "replication"; return; ;; esac
  echo "standalone"
}

parse_cluster_nodes() {
  while IFS= read -r line; do
    line=$(echo "$line" | tr -d '\r'); [ -z "$line" ] && continue
    set -- $line
    node_id="$1" addr="${2%%@*}" flags="$3" master_id="$4"
    case "$addr" in
      *:*) host=${addr%:*}; port=${addr##*:}; ;;
      *) host="$addr"; port=""; ;;
    esac
    echo "${node_id}|${host}|${port}|${flags}|${master_id}"
  done
}

sha1_hex() {
  s="$1"
  if command -v openssl >/dev/null 2>&1; then
    printf '%s' "$s" | openssl dgst -sha1 -binary 2>/dev/null | xxd -p -c 256 2>/dev/null | tr -d '\n'
  elif command -v sha1sum >/dev/null 2>&1; then
    printf '%s' "$s" | sha1sum | cut -d' ' -f1
  else
    echo ""
  fi
}

resp_bulk_strings() {
  raw="$1" expect_bulk=0
  printf '%s\n' "$raw" | while IFS= read -r line; do
    line=$(echo "$line" | tr -d '\r')
    if [ "$expect_bulk" -eq 1 ]; then echo "$line"; expect_bulk=0; continue; fi
    [ -z "$line" ] && continue
    case "$line" in \$*) expect_bulk=1; continue; ;; esac
    case "$line" in :*) echo "${line#:}"; continue; ;; esac
    case "$line" in \**) continue; ;; esac
    echo "$line"
  done
}

# key-val pairs (alternating lines) -> one line per map: name=X ip=Y port=Z runid=W
resp_maps_from_pairs() {
  awk 'NR%2==1 { key=$0 } NR%2==0 {
    val=$0; if(key=="name" && cur!="") { print cur; cur="" }; if(cur!="") cur=cur" "; cur=cur key"="val
  } END { if(cur!="") print cur }'
}

parse_resp_maps() {
  raw="$1"
  first=$(echo "$raw" | head -1 | tr -d '\r')
  if [ -n "$first" ] && [ "${first#\*}" = "$first" ] && [ "${first#\$}" = "$first" ]; then
    echo "$raw" | tr -d '\r' | resp_maps_from_pairs
  else
    resp_bulk_strings "$raw" | tr -d '\r' | resp_maps_from_pairs
  fi
}

collect_instance() {
  host="$1" port="$2" local_ip="$3"
  probe_port "$host" "$port" || return 1
  ping=$(run_redis "$host" "$port" PING 2>/dev/null)
  install_path=$(get_install_path_for_port "$port")
  case "$ping" in PONG|pong) ;; *)
    version=$(get_version_from_path "$install_path")
    [ -z "$version" ] && case "$host" in 127.0.0.1|localhost) version=$(get_version_via_docker "$port"); ;; esac
    emit_partial_instance "$local_ip" "$port" "$version" "$install_path"
    return 1
  ;; esac
  out_info_repl=$(run_redis "$host" "$port" INFO replication 2>/dev/null)
  out_info_sentinel=$(run_redis "$host" "$port" INFO sentinel 2>/dev/null)
  out_cluster=$(run_redis "$host" "$port" CLUSTER INFO 2>/dev/null)
  out_config_mc=$(run_redis "$host" "$port" CONFIG GET maxclients 2>/dev/null)
  out_config_mm=$(run_redis "$host" "$port" CONFIG GET maxmemory 2>/dev/null)
  out_info_server=$(run_redis "$host" "$port" INFO server 2>/dev/null)
  role=$(echo "$out_info_repl" | parse_info | grep -E '^role:' | cut -d: -f2 | tr -d '\r')
  version=$(echo "$out_info_server" | parse_info | grep -E '^redis_version:' | cut -d: -f2 | tr -d '\r')
  max_conn=$(echo "$out_config_mc" | config_get_value)
  max_mem=$(echo "$out_config_mm" | config_get_value)
  run_id=$(echo "$out_info_server" | parse_info | grep -E '^run_id:' | cut -d: -f2 | tr -d '\r')
  # install_path: 7.2+ INFO executable -> 6.0+ CONFIG GET config_file -> else process resolution (Linux/macOS/Windows)
  install_path=$(echo "$out_info_server" | parse_info | grep -E '^executable:' | sed 's/^executable:[[:space:]]*//' | tr -d '\r')
  if [ -z "$install_path" ]; then
    install_path=$(run_redis "$host" "$port" CONFIG GET config_file 2>/dev/null | config_get_value | sed 's/^[[:space:]]*"//;s/"[[:space:]]*$//')
  fi
  [ -z "$install_path" ] && install_path=$(get_install_path_for_port "$port")
  cluster_state=$(echo "$out_cluster" | parse_info | grep -E '^cluster_state:' | cut -d: -f2 | tr -d '\r')
  mode=$(detect_mode "$out_info_sentinel" "$cluster_state" "$role")
  echo "${port}|${mode}|${role}|${version}|${install_path}|${max_conn}|${max_mem}|${run_id}|${local_ip}"
}

cluster_uuid_from_nodes() {
  nodes="$1"
  uid_src=$(echo "$nodes" | cut -d'|' -f1 | sort -u | tr '\n' '|' | sed 's/|$//')
  [ -n "$uid_src" ] && sha1_hex "$uid_src" || echo ""
}

sentinel_uuid_from_masters() {
  masters_text="$1"
  uid_src=$(echo "$masters_text" | tr ' ' '\n' | grep -E '^name=' | cut -d= -f2- | sort -u | tr '\n' '|' | sed 's/|$//')
  [ -n "$uid_src" ] && sha1_hex "$uid_src" || echo ""
}

# Use sed to avoid awk -v corrupting backslashes (e.g. Windows paths)
json_esc() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\r//g'
}

emit_instance() {
  local_ip="$1" port="$2" mode="$3" role="$4" version="$5" install_path="$6" max_conn="$7" max_mem="$8" cluster_uuid="$9" slaves_json="${10}" master_json="${11}"
  inst_name="${local_ip}-redis-${port}"
  printf '{"inst_name":"%s","bk_obj_id":"redis","ip_addr":"%s","port":"%s","version":"%s","install_path":"%s","max_conn":"%s","max_mem":"%s","database_role":"%s","topo_mode":"%s","cluster_uuid":"%s","slaves":%s,"master":%s}\n' \
    "$(json_esc "$inst_name")" "$(json_esc "$local_ip")" "$port" "$(json_esc "$version")" "" \
    "$(json_esc "$max_conn")" "$(json_esc "$max_mem")" "$(json_esc "$role")" "$(json_esc "$mode")" "$(json_esc "$cluster_uuid")" \
    "$slaves_json" "$master_json"
}

emit_partial_instance() {
  local_ip="$1" port="$2" version="${3:-}" install_path="${4:-}"
  inst_name="${local_ip}-redis-${port}"
  printf '{"inst_name":"%s","bk_obj_id":"redis","ip_addr":"%s","port":"%s","version":"%s","install_path":"%s","max_conn":"","max_mem":"","database_role":"","topo_mode":"","cluster_uuid":"","slaves":[],"master":{}}\n' \
    "$(json_esc "$inst_name")" "$(json_esc "$local_ip")" "$port" "$(json_esc "$version")" ""
}

main() {
  REDIS_TARGET_HOST=$(_safe_host "$REDIS_TARGET_HOST"); [ -z "$REDIS_TARGET_HOST" ] && REDIS_TARGET_HOST="127.0.0.1"
  REDIS_CLI=$(_safe_cli_path "$REDIS_CLI"); [ -z "$REDIS_CLI" ] && REDIS_CLI="redis-cli"
  [ -n "${REDIS_USER:-}" ] && REDIS_USER=$(_safe_redis_user "$REDIS_USER")
  [ -z "$BK_HOST_INNERIP" ] && BK_HOST_INNERIP=$(hostname -I 2>/dev/null | awk '{print $1}')
  [ -z "$BK_HOST_INNERIP" ] && BK_HOST_INNERIP=$( ( ifconfig 2>/dev/null || ip addr 2>/dev/null ) | grep -oE 'inet ([0-9.]+)' | head -1 | awk '{print $2}')
  BK_HOST_INNERIP="${BK_HOST_INNERIP:-127.0.0.1}"
  BK_HOST_INNERIP=$(_safe_host "$BK_HOST_INNERIP"); [ -z "$BK_HOST_INNERIP" ] && BK_HOST_INNERIP="127.0.0.1"

  _port_path=""; _ports_list=""; _instances=""
  rdp=$(echo "${REDIS_DISCOVER_FROM_PROCESS}" | tr '[:upper:]' '[:lower:]')
  case "$rdp" in yes|1|true)
    _port_path=$(discover_ports_from_process 2>/dev/null)
    _ports_list=$(echo "$_port_path" | cut -d'|' -f1 2>/dev/null | sort -nu)
  ;; esac
  [ -z "$_ports_list" ] && _ports_list=$(parse_ports "$REDIS_TARGET_PORTS")
  if [ -z "$_ports_list" ]; then
    spec="$REDIS_TARGET_PORTS"
    while [ -n "$spec" ]; do
      part="${spec%%,*}"
      part=$(echo "$part" | tr -d ' \r')
      [ "$part" = "$spec" ] && spec="" || spec="${spec#*,}"
      [ -z "$part" ] && continue
      case "$part" in
        *-*) start=${part%-*}; end=${part#*-}
          [ "$start" -gt "$end" ] 2>/dev/null && { _t=$start; start=$end; end=$_t; }
          p=$start
          while [ $p -le $end ] 2>/dev/null; do
            [ $p -ge 1 ] && [ $p -le 65535 ] 2>/dev/null && _ports_list="${_ports_list}${_ports_list:+
}$p"
            p=$((p+1))
          done ;;
        *) [ "$part" -ge 1 ] 2>/dev/null && [ "$part" -le 65535 ] 2>/dev/null && _ports_list="${_ports_list}${_ports_list:+
}$part"; ;;
      esac
    done
    _ports_list=$(echo "$_ports_list" | sort -nu 2>/dev/null)
  fi

  while IFS= read -r port; do
    port=$(printf '%s' "$port" | tr -d '\r')
    [ -z "$port" ] && continue
    line=$(collect_instance "$REDIS_TARGET_HOST" "$port" "$BK_HOST_INNERIP") || { [ -n "$line" ] && echo "$line"; continue; }
    [ -z "$line" ] && continue
    _instances="${_instances}${_instances:+
}${line}"
  done <<EOF
$_ports_list
EOF

  [ -z "$_instances" ] && exit 0

  cluster_uuid_global="" sentinel_uuid_global="" cluster_nodes_out="" first_cluster_port="" first_sentinel_port=""
  _lines="$_instances"
  while IFS= read -r line; do
    line=$(printf '%s' "$line" | tr -d '\r')
    [ -z "$line" ] && continue
    mode=$(field "$line" "|" 2)
    case "$mode" in
      cluster) [ -z "$first_cluster_port" ] && first_cluster_port=$(field "$line" "|" 1); ;;
      sentinel) [ -z "$first_sentinel_port" ] && first_sentinel_port=$(field "$line" "|" 1); ;;
    esac
  done <<EOF
$_lines
EOF

  if [ -n "$first_cluster_port" ]; then
    cluster_nodes_out=$(run_redis "$REDIS_TARGET_HOST" "$first_cluster_port" CLUSTER NODES 2>/dev/null)
    cluster_uuid_global=$(cluster_uuid_from_nodes "$(echo "$cluster_nodes_out" | parse_cluster_nodes)")
  fi

  sentinel_masters_parsed=""; _replica_entries=""; _sentinel_runids=""
  if [ -n "$first_sentinel_port" ]; then
    assoc_init masters_by_group; assoc_init slave_set_by_group; assoc_init replica_runid_to_group
    sentinel_masters_raw=$(run_redis "$REDIS_TARGET_HOST" "$first_sentinel_port" SENTINEL MASTERS 2>/dev/null)
    sentinel_masters_parsed=$(parse_resp_maps "$sentinel_masters_raw")
    sentinel_uuid_global=$(sentinel_uuid_from_masters "$sentinel_masters_parsed")
    _sm="$sentinel_masters_parsed"
    while IFS= read -r mline; do
      mline=$(printf '%s' "$mline" | tr -d '\r')
      [ -z "$mline" ] && continue
      name="" ip="" port="" runid=""
      for pair in $mline; do
        case "$pair" in name=*) name="${pair#name=}"; ;; ip=*) ip="${pair#ip=}"; ;; port=*) port="${pair#port=}"; ;; runid=*) runid="${pair#runid=}"; ;; esac
      done
      name=$(printf '%s' "$name" | tr -d '\r ')
      [ -z "$name" ] && continue
      assoc_set masters_by_group "$name" "${ip}|${port}|${runid}"
      repl_raw=$(run_redis "$REDIS_TARGET_HOST" "$first_sentinel_port" SENTINEL REPLICAS "$name" 2>/dev/null)
      repl_pairs=$(parse_resp_maps "$repl_raw")
      assoc_set slave_set_by_group "$name" "[]"
      _repl_lines="$repl_pairs"
      while IFS= read -r rline; do
        [ -z "$rline" ] && continue
        rip="" rport="" rrunid=""
        for pair in $rline; do
          case "$pair" in ip=*) rip="${pair#ip=}"; ;; port=*) rport="${pair#port=}"; ;; runid=*) rrunid="${pair#runid=}"; ;; esac
        done
        item="{\"ip\":\"$rip\",\"port\":\"$rport\"}"
        arr=$(assoc_get slave_set_by_group "$name")
        arr="${arr%]}"; [ "$arr" != "[" ] && arr="${arr},"
        assoc_set slave_set_by_group "$name" "${arr}${item}]"
        [ -n "$rrunid" ] && assoc_set replica_runid_to_group "$rrunid" "$name"
        _replica_entries="${_replica_entries}${_replica_entries:+
}${rip}|${rport}|${rrunid}|${name}"
      done <<EOF
$_repl_lines
EOF
      sent_raw=$(run_redis "$REDIS_TARGET_HOST" "$first_sentinel_port" SENTINEL SENTINELS "$name" 2>/dev/null)
      sent_pairs=$(parse_resp_maps "$sent_raw")
      _sent_pairs_lines="$sent_pairs"
      while IFS= read -r sline; do
        [ -z "$sline" ] && continue
        for pair in $sline; do
          case "$pair" in runid=*) rrid="${pair#runid=}"; [ -n "$rrid" ] && _sentinel_runids="${_sentinel_runids}${_sentinel_runids:+
}$rrid"; ;; esac
        done
      done <<EOF
$_sent_pairs_lines
EOF
    done <<EOF
$_sm
EOF
    names_uid=$(echo "$sentinel_masters_parsed" | tr ' ' '\n' | grep -E '^name=' | cut -d= -f2- | sort -u | tr '\n' '|' | sed 's/|$//')
    runids_uid=$(echo "$_sentinel_runids" | sort -u 2>/dev/null | tr '\n' '|' | sed 's/|$//')
    [ -n "$names_uid" ] || [ -n "$runids_uid" ] && sentinel_uuid_global=$(sha1_hex "${names_uid}#${runids_uid}")
  fi

  if [ -n "$cluster_nodes_out" ]; then
    assoc_init by_port; assoc_init slave_set_by_master; assoc_init node_by_id
    _cluster_nodes=$(echo "$cluster_nodes_out" | parse_cluster_nodes)
    while IFS= read -r line; do
      [ -z "$line" ] && continue
      node_id=$(field "$line" "|" 1); addr_host=$(field "$line" "|" 2); addr_port=$(field "$line" "|" 3)
      flags=$(field "$line" "|" 4); master_id=$(field "$line" "|" 5)
      [ -n "$addr_port" ] && assoc_set by_port "$addr_port" "$node_id|$addr_host|$addr_port|$flags|$master_id"
      [ "$master_id" != "-" ] && [ -n "$master_id" ] && {
        item="{\"ip\":\"$addr_host\",\"port\":\"$addr_port\",\"node_id\":\"$node_id\"}"
        old=$(assoc_get slave_set_by_master "$master_id")
        if [ -z "$old" ]; then assoc_set slave_set_by_master "$master_id" "[$item]"
        else arr="${old%]}"; [ "$arr" != "[" ] && arr="${arr},"; assoc_set slave_set_by_master "$master_id" "${arr}${item}]"; fi
      }
      assoc_set node_by_id "$node_id" "$addr_host|$addr_port"
    done <<EOF
$_cluster_nodes
EOF
  fi

  assoc_init emitted
  _lines="$_instances"
  while IFS= read -r line; do
    line=$(printf '%s' "$line" | tr -d '\r')
    [ -z "$line" ] && continue
    port=$(field "$line" "|" 1); port=$(printf '%s' "$port" | tr -d '\r ')
    mode=$(field "$line" "|" 2); role=$(field "$line" "|" 3)
    version=$(field "$line" "|" 4); install_path=$(field "$line" "|" 5); max_conn=$(field "$line" "|" 6)
    max_mem=$(field "$line" "|" 7); run_id=$(field "$line" "|" 8); local_ip=$(field "$line" "|" 9)
    cluster_uuid="" slaves_json="[]" master_json="{}"
    case "$mode" in
      sentinel) cluster_uuid="$sentinel_uuid_global"; ;;
      cluster) cluster_uuid="$cluster_uuid_global"
        node_line=$(assoc_get by_port "$port")
        if [ -n "$node_line" ]; then
          node_id=$(field "$node_line" "|" 1); addr_host=$(field "$node_line" "|" 2); addr_port=$(field "$node_line" "|" 3)
          flags=$(field "$node_line" "|" 4); master_id=$(field "$node_line" "|" 5)
          case "$flags" in *master*) slaves_json=$(assoc_get slave_set_by_master "$node_id"); [ -z "$slaves_json" ] && slaves_json="[]"; ;;
            *slave*) [ -n "$master_id" ] && { m_addr=$(assoc_get node_by_id "$master_id"); [ -n "$m_addr" ] && { m_host=$(field "$m_addr" "|" 1); m_port=$(field "$m_addr" "|" 2); master_json="\"$(json_esc "$m_host:$m_port")\""; }; }; ;;
          esac
        fi ;;
      *) [ -n "$sentinel_uuid_global" ] && cluster_uuid="$sentinel_uuid_global"
        group_name=""
        if [ -n "$sentinel_uuid_global" ]; then
          if [ "$role" = "master" ]; then
            _runid=$(printf '%s' "$run_id" | tr -d '\r ')
            for g in $(assoc_keys masters_by_group 2>/dev/null); do
              mval=$(assoc_get masters_by_group "$g")
              mport=$(echo "$mval" | cut -d'|' -f2 | tr -d '\r ')
              mrunid=$(echo "$mval" | cut -d'|' -f3 | tr -d '\r ')
              [ "$mport" = "$port" ] && { group_name="$g"; break; }
              [ -n "$_runid" ] && [ "$mrunid" = "$_runid" ] && { group_name="$g"; break; }
              _mp="${REDIS_MASTER_PORT_MAPPED:-6389}"
              [ "$mport" = "6379" ] && [ "$port" = "$_mp" ] && { group_name="$g"; break; }
            done
            [ -z "$group_name" ] && _one=$(assoc_keys masters_by_group 2>/dev/null | head -1) && _two=$(assoc_keys masters_by_group 2>/dev/null | sed -n '2p') && [ -n "$_one" ] && [ -z "$_two" ] && group_name="$_one"
            if [ -n "$group_name" ]; then
              slaves_json=$(assoc_get slave_set_by_group "$group_name")
              if [ -z "$slaves_json" ] || [ "$slaves_json" = "[]" ]; then
                _sl=""
                while IFS= read -r _re; do [ -z "$_re" ] && continue
                  _rn=$(echo "$_re" | cut -d'|' -f4); [ "$_rn" != "$group_name" ] && continue
                  _ri=$(echo "$_re" | cut -d'|' -f1); _rp=$(echo "$_re" | cut -d'|' -f2); _rr=$(echo "$_re" | cut -d'|' -f3)
                  [ -n "$_sl" ] && _sl="$_sl,"; _sl="$_sl{\"ip\":\"$_ri\",\"port\":\"$_rp\"}"
                done <<REPL
$_replica_entries
REPL
                [ -n "$_sl" ] && slaves_json="[$_sl]"
              fi
              [ -z "$slaves_json" ] && slaves_json="[]"
            fi
          elif [ "$role" = "slave" ] && [ -n "$run_id" ]; then
            group_name=$(assoc_get replica_runid_to_group "$run_id")
            if [ -n "$group_name" ]; then
              mval=$(assoc_get masters_by_group "$group_name")
              mhost=$(field "$mval" "|" 1 | tr -d '\r '); mport=$(field "$mval" "|" 2 | tr -d '\r ')
              _mh="$mhost"; _mp="$mport"
              [ "$mport" = "6379" ] && [ -n "${REDIS_MASTER_PORT_MAPPED:-}" ] && _mh="${REDIS_TARGET_HOST:-$mhost}" && _mp="${REDIS_MASTER_PORT_MAPPED}"
              master_json="\"$(json_esc "$_mh:$_mp")\""
            fi
          fi
        fi ;;
    esac
    emit_instance "$local_ip" "$port" "$mode" "$role" "$version" "$install_path" "$max_conn" "$max_mem" "$cluster_uuid" "$slaves_json" "$master_json"
    assoc_set emitted "$local_ip:$port" "1"
  done <<EOF
$_lines
EOF

  if [ -n "$sentinel_uuid_global" ] && [ -n "$_replica_entries" ]; then
    while IFS= read -r entry; do
      entry=$(printf '%s' "$entry" | tr -d '\r')
      [ -z "$entry" ] && continue
      rip=$(field "$entry" "|" 1 | tr -d '\r '); rport=$(field "$entry" "|" 2 | tr -d '\r '); rrunid=$(field "$entry" "|" 3 | tr -d '\r '); name=$(field "$entry" "|" 4 | tr -d '\r ')
      [ -n "$(assoc_get emitted "$rip:$rport")" ] && continue
      master_json="{}"
      if [ -n "$name" ]; then
        mval=$(assoc_get masters_by_group "$name")
        if [ -n "$mval" ]; then
          mhost=$(field "$mval" "|" 1 | tr -d '\r '); mport=$(field "$mval" "|" 2 | tr -d '\r ')
          _mh="$mhost"; _mp="$mport"
          [ "$mport" = "6379" ] && [ -n "${REDIS_MASTER_PORT_MAPPED:-}" ] && _mh="${REDIS_TARGET_HOST:-$mhost}" && _mp="${REDIS_MASTER_PORT_MAPPED}"
          master_json="\"$(json_esc "$_mh:$_mp")\""
        else
          _mph="${REDIS_TARGET_HOST:-127.0.0.1}"
          _mpp="${REDIS_MASTER_PORT_MAPPED:-6389}"
          master_json="\"$(json_esc "$_mph:$_mpp")\""
        fi
      fi
      rver="" rpath="" rmc="" rmm=""
      _si=$(run_redis "$rip" "$rport" INFO server 2>/dev/null)
      [ -n "$_si" ] && rver=$(echo "$_si" | parse_info | grep -E '^redis_version:' | cut -d: -f2 | tr -d '\r')
      [ -n "$_si" ] && rpath=$(echo "$_si" | parse_info | grep -E '^executable:' | sed 's/^executable:[[:space:]]*//' | tr -d '\r')
      _mc=$(run_redis "$rip" "$rport" CONFIG GET maxclients 2>/dev/null); rmc=$(echo "$_mc" | config_get_value)
      _mm=$(run_redis "$rip" "$rport" CONFIG GET maxmemory 2>/dev/null); rmm=$(echo "$_mm" | config_get_value)
      [ -z "$rpath" ] && rpath=$(run_redis "$rip" "$rport" CONFIG GET config_file 2>/dev/null | config_get_value | sed 's/^[[:space:]]*"//;s/"[[:space:]]*$//')
      emit_instance "$rip" "$rport" "replication" "slave" "$rver" "$rpath" "$rmc" "$rmm" "$sentinel_uuid_global" "[]" "$master_json"
      assoc_set emitted "$rip:$rport" "1"
    done <<EOF
$_replica_entries
EOF
  fi
  exit 0
}

main "$@"
