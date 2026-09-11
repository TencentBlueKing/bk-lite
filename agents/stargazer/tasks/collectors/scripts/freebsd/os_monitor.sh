#!/bin/sh
# BK-Lite FreeBSD OS metrics collector.
# Collect via system commands; skip a command if it is missing.

set +e
export LC_ALL=C
export LANG=C
export PATH=/bin:/usr/bin:/sbin:/usr/sbin:/usr/local/bin:${PATH}

AWK=awk

_have() {
  command -v "$1" >/dev/null 2>&1
}

_run() {
  cmd=$1
  shift
  if _have "${cmd}"; then
    "${cmd}" "$@" 2>/dev/null
    return $?
  fi
  return 127
}

_sysctl_n() {
  sysctl -n "$1" 2>/dev/null
}

# Shared awk JSON string escape: quotes, backslash, and C0 controls.
# Used by _json_str and by disk/diskio/net array builders.
_JSON_ESC_AWK='
function json_esc_init(    i, c, hex) {
  if (_JSON_ESC_READY) return
  _JSON_ESC_READY = 1
  hex = "0123456789abcdef"
  _JSON_CTRL[sprintf("%c", 8)] = "\\b"
  _JSON_CTRL[sprintf("%c", 9)] = "\\t"
  _JSON_CTRL[sprintf("%c", 10)] = "\\n"
  _JSON_CTRL[sprintf("%c", 12)] = "\\f"
  _JSON_CTRL[sprintf("%c", 13)] = "\\r"
  for (i = 0; i < 32; i++) {
    c = sprintf("%c", i)
    if (!(c in _JSON_CTRL)) {
      _JSON_CTRL[c] = "\\u00" substr(hex, int(i / 16) + 1, 1) substr(hex, (i % 16) + 1, 1)
    }
  }
  _JSON_CTRL[sprintf("%c", 127)] = "\\u007f"
}
function json_esc(s,    i, c, n, out) {
  json_esc_init()
  out = ""
  n = length(s)
  for (i = 1; i <= n; i++) {
    c = substr(s, i, 1)
    if (c == "\\") { out = out "\\\\"; continue }
    if (c == "\"") { out = out "\\\""; continue }
    if (c in _JSON_CTRL) { out = out _JSON_CTRL[c]; continue }
    out = out c
  }
  return out
}
'

_json_str() {
  printf '%s' "${1:-}" | ${AWK} "${_JSON_ESC_AWK}"'
    BEGIN { ORS="" }
    {
      if (NR > 1) printf "\\n"
      printf "%s", json_esc($0)
    }
  '
}

_num() {
  v=$1
  case "${v}" in
    ''|*[!0-9.+-]*) printf '0' ;;
    *) printf '%s' "${v}" ;;
  esac
}

_is_int() {
  case "$1" in
    ''|*[!0-9]*) return 1 ;;
    *) return 0 ;;
  esac
}

# --- os.version ---
OS_REL=$(_run uname -r)
OS_ARCH=$(_run uname -p)
OS_MACH=$(_run uname -m)
OS_VER=$(_run freebsd-version)
[ -z "${OS_VER}" ] && OS_VER=${OS_REL}
[ -z "${OS_REL}" ] && OS_REL=""
[ -z "${OS_ARCH}" ] && OS_ARCH=""
[ -z "${OS_MACH}" ] && OS_MACH=""

# --- load + uptime ---
LOAD1=0
LOAD5=0
LOAD15=0
UPTIME_SEC=0

LOADAVG_RAW=$(_sysctl_n vm.loadavg)
if [ -n "${LOADAVG_RAW}" ]; then
  set -- $(printf '%s\n' "${LOADAVG_RAW}" | ${AWK} '{
    gsub(/[{}]/, " ")
    for (i = 1; i <= NF; i++) {
      if ($i ~ /^[0-9]/) printf "%s ", $i
    }
  }')
  [ -n "$1" ] && LOAD1=$1
  [ -n "$2" ] && LOAD5=$2
  [ -n "$3" ] && LOAD15=$3
else
  UPTIME_RAW=$(_run uptime)
  if [ -n "${UPTIME_RAW}" ]; then
    set -- $(printf '%s\n' "${UPTIME_RAW}" | ${AWK} -F'load average[s]*:' '{
      if (NF < 2) next
      gsub(/,/, " ", $2)
      print $2
    }')
    [ -n "$1" ] && LOAD1=$1
    [ -n "$2" ] && LOAD5=$2
    [ -n "$3" ] && LOAD15=$3
  fi
fi

BOOT_SEC=$(printf '%s\n' "$(_sysctl_n kern.boottime)" | ${AWK} '{
  if (match($0, /sec[ \t]*=[ \t]*[0-9]+/)) {
    s = substr($0, RSTART, RLENGTH)
    sub(/.*[^0-9]/, "", s)
    print s + 0
  }
}')
NOW_SEC=$(date +%s 2>/dev/null)
if _is_int "${BOOT_SEC}" && _is_int "${NOW_SEC}"; then
  UPTIME_SEC=$((NOW_SEC - BOOT_SEC))
  [ "${UPTIME_SEC}" -lt 0 ] && UPTIME_SEC=0
fi
if [ "${UPTIME_SEC}" = "0" ] || [ -z "${UPTIME_SEC}" ]; then
  UPTIME_SEC=$(_sysctl_n kern.boottime.sec)
  if _is_int "${UPTIME_SEC}" && _is_int "${NOW_SEC}"; then
    UPTIME_SEC=$((NOW_SEC - UPTIME_SEC))
    [ "${UPTIME_SEC}" -lt 0 ] && UPTIME_SEC=0
  else
    UPTIME_SEC=0
  fi
fi

# --- CPU: kern.cp_time two snapshots; vmstat 1 2 fallback ---
# kern.cp_time: user nice sys interrupt idle. FreeBSD has no Linux-style iowait.
CPU_USER=0
CPU_SYS=0
CPU_WAIT=0
CPU_USAGE=0

_cp_delta() {
  printf '%s\n%s\n' "$1" "$2" | ${AWK} '
    NR==1 { for (i=1; i<=NF; i++) a[i]=$i+0; n=NF; next }
    NR==2 {
      du=$1-a[1]; dn=$2-a[2]; ds=$3-a[3]; di=$4-a[4]; dd=$5-a[5]
      tot=du+dn+ds+di+dd
      if (tot <= 0) { print "0 0 0 0"; exit }
      user=(du+dn)*100/tot
      sys=(ds+di)*100/tot
      idle=dd*100/tot
      usage=user+sys
      if (usage < 0) usage=0
      if (usage > 100) usage=100
      printf "%.2f %.2f %.2f %.2f\n", user, sys, usage, idle
    }
  '
}

CP1=$(_sysctl_n kern.cp_time)
if [ -n "${CP1}" ]; then
  sleep 1
  CP2=$(_sysctl_n kern.cp_time)
  if [ -n "${CP2}" ]; then
    set -- $(_cp_delta "${CP1}" "${CP2}")
    [ -n "$1" ] && CPU_USER=$1
    [ -n "$2" ] && CPU_SYS=$2
    [ -n "$3" ] && CPU_USAGE=$3
  fi
fi

if [ "${CPU_USAGE}" = "0" ] && [ "${CPU_USER}" = "0" ]; then
  VM_OUT=$(_run vmstat 1 2)
  if [ -n "${VM_OUT}" ]; then
    set -- $(printf '%s\n' "${VM_OUT}" | ${AWK} '
      BEGIN { last="" }
      $0 ~ /us[ \t]+sy[ \t]+id/ { hdr=1; next }
      NF >= 3 { last=$0 }
      END {
        if (last == "") exit
        n=split(last, f, /[ \t]+/)
        us=f[n-2]+0; sy=f[n-1]+0; id=f[n]+0
        usage=us+sy
        if (usage < 0) usage=0
        if (usage > 100) usage=100
        printf "%.2f %.2f %.2f\n", us, sy, usage
      }
    ')
    [ -n "$1" ] && CPU_USER=$1
    [ -n "$2" ] && CPU_SYS=$2
    [ -n "$3" ] && CPU_USAGE=$3
  fi
fi
CPU_WAIT=0

# --- mem: hw.physmem + vm.stats.vm page counters; swapinfo -k ---
PAGE_SIZE=$(_sysctl_n hw.pagesize)
[ -z "${PAGE_SIZE}" ] && PAGE_SIZE=4096
case "${PAGE_SIZE}" in
  ''|*[!0-9]*) PAGE_SIZE=4096 ;;
esac

MEM_TOTAL=$(_sysctl_n hw.physmem)
[ -z "${MEM_TOTAL}" ] && MEM_TOTAL=0
ACTIVE=$(_sysctl_n vm.stats.vm.v_active_count)
WIRE=$(_sysctl_n vm.stats.vm.v_wire_count)
LAUNDRY=$(_sysctl_n vm.stats.vm.v_laundry_count)
FREE_PG=$(_sysctl_n vm.stats.vm.v_free_count)
[ -z "${ACTIVE}" ] && ACTIVE=0
[ -z "${WIRE}" ] && WIRE=0
[ -z "${LAUNDRY}" ] && LAUNDRY=0
[ -z "${FREE_PG}" ] && FREE_PG=0

MEM_USED=$(${AWK} -v a="${ACTIVE}" -v w="${WIRE}" -v l="${LAUNDRY}" -v p="${PAGE_SIZE}" 'BEGIN {
  printf "%.0f", (a+0+w+0+l+0)*p
}')
MEM_FREE=$(${AWK} -v f="${FREE_PG}" -v p="${PAGE_SIZE}" 'BEGIN { printf "%.0f", (f+0)*p }')
if [ "${MEM_TOTAL}" = "0" ] || [ -z "${MEM_TOTAL}" ]; then
  PAGE_COUNT=$(_sysctl_n vm.stats.vm.v_page_count)
  MEM_TOTAL=$(${AWK} -v c="${PAGE_COUNT}" -v p="${PAGE_SIZE}" 'BEGIN { printf "%.0f", (c+0)*p }')
fi
MEM_USED_PCT=$(${AWK} -v u="${MEM_USED}" -v t="${MEM_TOTAL}" 'BEGIN {
  if (t+0 <= 0) { print 0; exit }
  printf "%.2f", u*100/t
}')

SWAP_TOTAL=0
SWAP_FREE=0
SWAP_OUT=$(_run swapinfo -k)
if [ -n "${SWAP_OUT}" ]; then
  set -- $(printf '%s\n' "${SWAP_OUT}" | ${AWK} '
    BEGIN { tot=0; used=0; avail=0; saw=0 }
    NR==1 { next }
    tolower($1)=="total" {
      tot=$2+0; used=$3+0; avail=$4+0; saw=1
      next
    }
    $1 ~ /^\// || $1 ~ /^[A-Za-z]/ {
      tot+=$2+0; used+=$3+0; avail+=$4+0; saw=1
    }
    END {
      if (!saw) { print "0 0"; exit }
      if (avail <= 0 && tot >= used) avail=tot-used
      printf "%.0f %.0f\n", tot*1024, avail*1024
    }
  ')
  [ -n "$1" ] && SWAP_TOTAL=$1
  [ -n "$2" ] && SWAP_FREE=$2
fi

# --- disk: df -kT (or df -kP) + df -i; skip pseudo filesystems ---
DF_K=$(_run df -kT)
[ -z "${DF_K}" ] && DF_K=$(_run df -kP)
DF_I=$(_run df -iT)
[ -z "${DF_I}" ] && DF_I=$(_run df -i)

DISK_JSON=$(
  printf '%s\n' "${DF_K}" | ${AWK} -v inode_src="${DF_I}" "${_JSON_ESC_AWK}"'
    function skip_fs(t) {
      t=tolower(t)
      return (t=="devfs" || t=="procfs" || t=="fdescfs" || t=="linprocfs" || t=="linsysfs" || t=="fd" || t=="ptsfs" || t=="none" || t=="autofs")
    }
    function take_mount(line, cap_idx,    i, m) {
      m=""
      for (i=cap_idx+1; i<=NF; i++) {
        if (m != "") m=m " "
        m=m $i
      }
      return m
    }
    function parse_cap_row(line, has_type,    cap_i, i) {
      for (i=1; i<=NF; i++) {
        if ($i ~ /%$/) { cap_i=i; break }
      }
      if (!cap_i) return 0
      mount=take_mount(line, cap_i)
      if (mount == "") return 0
      if (has_type) {
        ftype=$2
        tot=$3+0; ukb=$4+0; fkb=$5+0; pc=$cap_i+0
      } else {
        ftype=""
        tot=$2+0; ukb=$3+0; fkb=$4+0; pc=$cap_i+0
      }
      return 1
    }
    BEGIN {
      n=0
      n_inode=split(inode_src, ilines, "\n")
      for (li=1; li<=n_inode; li++) {
        line=ilines[li]
        if (line ~ /^Filesystem/) continue
        if (line == "") continue
        nfi=split(line, f, /[ \t]+/)
        cap_i=0
        iused_i=0
        for (i=1; i<=nfi; i++) {
          if (f[i] ~ /%$/) {
            if (!cap_i) cap_i=i
            else { iused_i=i; break }
          }
        }
        if (!cap_i || !iused_i) continue
        m=""
        for (i=iused_i+1; i<=nfi; i++) {
          if (m != "") m=m " "
          m=m f[i]
        }
        if (m == "") continue
        # df -i: ... Capacity iused ifree %iused Mounted on
        if (iused_i >= 2) {
          iu[m]=f[iused_i-2]+0
          ifr[m]=f[iused_i-1]+0
        }
        ipct[m]=f[iused_i]+0
      }
    }
    NR==1 {
      has_type=($0 ~ /Type/)
      next
    }
    {
      if ($0 ~ /%/) {
        if (pending_dev != "") {
          $0 = pending_dev " " $0
          pending_dev=""
        }
      } else {
        pending_dev=$0
        next
      }
      if (!parse_cap_row($0, has_type)) next
      if (skip_fs(ftype)) next
      if (mount == "") next
      if (!(mount in seen)) {
        n++
        order[n]=mount
        seen[mount]=1
      }
      totb[mount]=tot*1024
      usedb[mount]=ukb*1024
      freeb[mount]=fkb*1024
      pct[mount]=pc
      if (ftype != "") fst[mount]=ftype
    }
    END {
      printf "["
      for (i=1; i<=n; i++) {
        m=order[i]
        if (i>1) printf ","
        ip = (m in ipct) ? ipct[m] : 0
        iuv = (m in iu) ? iu[m] : 0
        ifv = (m in ifr) ? ifr[m] : 0
        printf "{\"mount\":\"%s\",\"path\":\"%s\",\"fstype\":\"%s\",\"total_bytes\":%.0f,\"used_bytes\":%.0f,\"free_bytes\":%.0f,\"used_percent\":%.2f,\"inodes_used_percent\":%.2f,\"iused\":%.0f,\"ifree\":%.0f}", json_esc(m), json_esc(m), json_esc(fst[m]), totb[m]+0, usedb[m]+0, freeb[m]+0, pct[m]+0, ip+0, iuv, ifv
      }
      printf "]"
    }
  '
)
[ -z "${DISK_JSON}" ] && DISK_JSON='[]'

# --- diskio: iostat -x 1 2 interval; iostat -Ix totals when present ---
DISKIO_JSON='[]'
IO_X=$(_run iostat -x -w 1 -c 2)
IO_I=$(_run iostat -Ix -c 1)
DISKIO_JSON=$(
  printf '%s\n' "${IO_X}" | ${AWK} -v totals_src="${IO_I}" "${_JSON_ESC_AWK}"'
    function skip_dev(d) {
      return (d=="device" || d=="extended" || d=="cpu" || d=="tty" || d ~ /^pass[0-9]/ || d ~ /^cd[0-9]/)
    }
    function parse_x_line() {
      if (NF < 5) return
      d=$1
      if (skip_dev(d)) return
      # FreeBSD iostat -x: device r/s w/s kr/s kw/s ... %b
      rkb=$4+0
      wkb=$5+0
      tma=$NF+0
      if (!(d in seen)) {
        n++
        order[n]=d
        seen[d]=1
      }
      r_int[d]=rkb*1024
      w_int[d]=wkb*1024
      tm[d]=tma
    }
    BEGIN {
      n=0
      n_tot=split(totals_src, tlines, "\n")
      for (li=1; li<=n_tot; li++) {
        line=tlines[li]
        ntf=split(line, f, /[ \t]+/)
        if (ntf < 5) continue
        d=f[1]
        if (skip_dev(d)) continue
        if (f[1] == "device") continue
        rtot[d]=f[4]*1024
        wtot[d]=f[5]*1024
      }
    }
    $1=="device" { in_tbl=1; next }
    in_tbl && NF>=5 { parse_x_line() }
    END {
      printf "["
      for (i=1; i<=n; i++) {
        d=order[i]
        if (i>1) printf ","
        if (d in rtot) {
          printf "{\"device\":\"%s\",\"read_bytes\":%.0f,\"write_bytes\":%.0f,\"read_bytes_total\":%.0f,\"write_bytes_total\":%.0f,\"tm_act\":%.2f}", json_esc(d), r_int[d]+0, w_int[d]+0, rtot[d]+0, wtot[d]+0, tm[d]+0
        } else {
          printf "{\"device\":\"%s\",\"read_bytes\":%.0f,\"write_bytes\":%.0f,\"tm_act\":%.2f}", json_esc(d), r_int[d]+0, w_int[d]+0, tm[d]+0
        }
      }
      printf "]"
    }
  '
)
[ -z "${DISKIO_JSON}" ] && DISKIO_JSON='[]'

# --- net: netstat -ibn Link rows ---
NET_JSON='[]'
NET_OUT=$(_run netstat -ibn)
if [ -z "${NET_OUT}" ]; then
  NET_OUT=$(_run netstat -ib)
fi
NET_JSON=$(
  printf '%s\n' "${NET_OUT}" | ${AWK} "${_JSON_ESC_AWK}"'
    $0 ~ /^Name/ { next }
    $3 !~ /<Link/ { next }
    {
      iface=$1
      if (iface == "") next
      if ($4 ~ /^[0-9]+$/) {
        ierrs=$5+0; ibytes=$7+0; oerrs=$9+0; obytes=$10+0
      } else {
        ierrs=$6+0; ibytes=$8+0; oerrs=$10+0; obytes=$11+0
      }
      if (!(iface in seen)) {
        n++
        order[n]=iface
        seen[iface]=1
      }
      rxb[iface]=ibytes
      txb[iface]=obytes
      rxerr[iface]=ierrs
      txerr[iface]=oerrs
    }
    END {
      printf "["
      for (i=1; i<=n; i++) {
        d=order[i]
        if (i>1) printf ","
        printf "{\"interface\":\"%s\",\"rx_bytes\":%.0f,\"tx_bytes\":%.0f,\"rx_errors\":%.0f,\"tx_errors\":%.0f}", json_esc(d), rxb[d]+0, txb[d]+0, rxerr[d]+0, txerr[d]+0
      }
      printf "]"
    }
  '
)
[ -z "${NET_JSON}" ] && NET_JSON='[]'

OS_VER_J=$(_json_str "${OS_VER}")
OS_ARCH_J=$(_json_str "${OS_ARCH}")
OS_MACH_J=$(_json_str "${OS_MACH}")

printf '{'
printf '"os":{"version":"%s","arch":"%s","machine":"%s"},' "${OS_VER_J}" "${OS_ARCH_J}" "${OS_MACH_J}"
printf '"cpu":{"usage_percent":%s,"usage_user_percent":%s,"usage_system_percent":%s,"usage_iowait_percent":%s},' \
  "$(_num "${CPU_USAGE}")" "$(_num "${CPU_USER}")" "$(_num "${CPU_SYS}")" "$(_num "${CPU_WAIT}")"
printf '"mem":{"total_bytes":%s,"used_bytes":%s,"free_bytes":%s,"swap_total_bytes":%s,"swap_free_bytes":%s,"used_percent":%s},' \
  "$(_num "${MEM_TOTAL}")" "$(_num "${MEM_USED}")" "$(_num "${MEM_FREE}")" "$(_num "${SWAP_TOTAL}")" "$(_num "${SWAP_FREE}")" "$(_num "${MEM_USED_PCT}")"
printf '"disk":%s,' "${DISK_JSON}"
printf '"diskio":%s,' "${DISKIO_JSON}"
printf '"net":%s,' "${NET_JSON}"
printf '"system":{"uptime_seconds":%s,"load1":%s,"load5":%s,"load15":%s}' \
  "$(_num "${UPTIME_SEC}")" "$(_num "${LOAD1}")" "$(_num "${LOAD5}")" "$(_num "${LOAD15}")"
printf '}\n'
