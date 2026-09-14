#!/usr/bin/ksh
# BK-Lite HP-UX OS metrics collector.
# Collect via HP-UX system commands; skip a command if it is missing.

set +e
export LC_ALL=C
export LANG=C
export PATH=/usr/bin:/usr/sbin:/bin:/sbin:/opt/network/bin:${PATH}

if [ -x /usr/bin/nawk ]; then
  AWK=/usr/bin/nawk
elif [ -x /usr/xpg4/bin/awk ]; then
  AWK=/usr/xpg4/bin/awk
else
  AWK=awk
fi

_have() {
  whence "$1" >/dev/null 2>&1
}

_run() {
  typeset cmd
  cmd=$1
  shift
  if _have "${cmd}"; then
    "${cmd}" "$@" 2>/dev/null
    return $?
  fi
  return 127
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
  typeset v
  v=$1
  case "${v}" in
    ''|*[!0-9.+-]*) printf '0' ;;
    *) printf '%s' "${v}" ;;
  esac
}

OS_REL=$(_run uname -r)
OS_ARCH=$(_run uname -m)
OS_MACH=$(_run model)
[ -z "${OS_REL}" ] && OS_REL=""
[ -z "${OS_ARCH}" ] && OS_ARCH=""
[ -z "${OS_MACH}" ] && OS_MACH=$(_run uname -i)
[ -z "${OS_MACH}" ] && OS_MACH=""

# --- load + uptime ---
LOAD1=0
LOAD5=0
LOAD15=0
UPTIME_SEC=0
UPTIME_RAW=$(_run uptime)
if [ -n "${UPTIME_RAW}" ]; then
  set -- $(printf '%s\n' "${UPTIME_RAW}" | ${AWK} -F'load average:' '{
    if (NF < 2) next
    gsub(/,/, " ", $2)
    print $2
  }')
  [ -n "$1" ] && LOAD1=$1
  [ -n "$2" ] && LOAD5=$2
  [ -n "$3" ] && LOAD15=$3
  UPTIME_SEC=$(printf '%s\n' "${UPTIME_RAW}" | ${AWK} '
    {
      line = $0
      sec = 0
      if (match(line, /up[ ]+[0-9]+[ ]+day/)) {
        s = substr(line, RSTART, RLENGTH)
        gsub(/[^0-9]/, "", s)
        sec += s * 86400
      }
      if (match(line, /[0-9]+[ ]+hr/)) {
        s = substr(line, RSTART, RLENGTH)
        gsub(/[^0-9]/, "", s)
        sec += s * 3600
      }
      if (match(line, /[0-9]+[ ]+min/)) {
        s = substr(line, RSTART, RLENGTH)
        gsub(/[^0-9]/, "", s)
        sec += s * 60
      }
      if (match(line, /up[ ]+[0-9]+:[0-9]+/)) {
        s = substr(line, RSTART, RLENGTH)
        sub(/^up[ ]+/, "", s)
        split(s, hm, ":")
        sec += hm[1] * 3600 + hm[2] * 60
      }
      print sec + 0
    }
  ')
fi

# --- CPU: sar -u 1 1 (%usr %sys %wio %idle); vmstat 1 2 fallback ---
CPU_USER=0
CPU_SYS=0
CPU_WAIT=0
CPU_IDLE=0
CPU_USAGE=0

SAR_CPU=$(_run sar -u 1 1)
if [ -n "${SAR_CPU}" ]; then
  set -- $(printf '%s\n' "${SAR_CPU}" | ${AWK} '
    BEGIN { us_c=0; sy_c=0; wt_c=0; id_c=0 }
    {
      line = $0
      low = line
      for (i=1; i<=NF; i++) {
        col = tolower($i)
        gsub(/%/, "", col)
        if (col=="usr" || col=="user" || col=="us") us_c=i
        if (col=="sys" || col=="system" || col=="sy") sy_c=i
        if (col=="wio" || col=="wait" || col=="wt" || col=="wa") wt_c=i
        if (col=="idle" || col=="id") id_c=i
      }
      if (us_c==0) next
      if (tolower($1)=="average" || $1 ~ /[0-9]:[0-9]/) {
        last_us = $(us_c)+0
        last_sy = $(sy_c)+0
        last_wt = $(wt_c)+0
        last_id = $(id_c)+0
        found = 1
      }
    }
    END {
      if (found) printf "%.2f %.2f %.2f %.2f", last_us, last_sy, last_wt, last_id
    }
  ')
  [ -n "$1" ] && CPU_USER=$1
  [ -n "$2" ] && CPU_SYS=$2
  [ -n "$3" ] && CPU_WAIT=$3
  [ -n "$4" ] && CPU_IDLE=$4
fi

if [ "${CPU_USER}" = "0" ] && [ "${CPU_SYS}" = "0" ] && [ "${CPU_IDLE}" = "0" ]; then
  VM_OUT=$(_run vmstat 1 2)
  if [ -n "${VM_OUT}" ]; then
    set -- $(printf '%s\n' "${VM_OUT}" | ${AWK} '
      $NF ~ /^[0-9.]+$/ && $(NF-1) ~ /^[0-9.]+$/ && $(NF-2) ~ /^[0-9.]+$/ {
        us=$(NF-2)+0; sy=$(NF-1)+0; id=$NF+0
      }
      END {
        if (us+sy+id > 0) printf "%.2f %.2f 0.00 %.2f", us, sy, id
      }
    ')
    [ -n "$1" ] && CPU_USER=$1
    [ -n "$2" ] && CPU_SYS=$2
    [ -n "$3" ] && CPU_WAIT=$3
    [ -n "$4" ] && CPU_IDLE=$4
  fi
fi

CPU_USAGE=$(${AWK} -v u="${CPU_USER}" -v s="${CPU_SYS}" -v w="${CPU_WAIT}" 'BEGIN {
  t = u+s+w
  if (t < 0) t = 0
  if (t > 100) t = 100
  printf "%.2f", t
}')

# --- memory + swap: swapinfo -tam; machinfo fallback for RAM ---
MEM_TOTAL=0
MEM_USED=0
MEM_FREE=0
MEM_USED_PCT=0
SWAP_TOTAL=0
SWAP_FREE=0

SWAPINFO_OUT=$(_run swapinfo -tam)
if [ -z "${SWAPINFO_OUT}" ]; then
  SWAPINFO_OUT=$(_run swapinfo -tm)
fi
if [ -n "${SWAPINFO_OUT}" ]; then
  set -- $(printf '%s\n' "${SWAPINFO_OUT}" | ${AWK} '
    BEGIN { mem_tot=0; mem_used=0; mem_free=0; sw_tot=0; sw_free=0 }
    tolower($1)=="type" { next }
    $1 ~ /^Kb/ || $0 ~ /^[ \t]*Kb/ { next }
    {
      t = tolower($1)
      avail = $2; used = $3; free = $4
      if (avail == "-") avail = 0
      if (used == "-") used = 0
      if (free == "-") free = 0
      if (t=="memory") {
        mem_tot = avail+0
        mem_used = used+0
        mem_free = free+0
        next
      }
      if (t=="dev" || t=="fs") {
        sw_tot += avail+0
        sw_free += free+0
      }
    }
    END {
      printf "%.0f %.0f %.0f %.0f %.0f", mem_tot*1024, mem_used*1024, mem_free*1024, sw_tot*1024, sw_free*1024
    }
  ')
  [ -n "$1" ] && MEM_TOTAL=$1
  [ -n "$2" ] && MEM_USED=$2
  [ -n "$3" ] && MEM_FREE=$3
  [ -n "$4" ] && SWAP_TOTAL=$4
  [ -n "$5" ] && SWAP_FREE=$5
fi

if [ "${MEM_TOTAL}" = "0" ]; then
  MACHINFO_OUT=$(_run machinfo)
  if [ -n "${MACHINFO_OUT}" ]; then
    MEM_TOTAL=$(printf '%s\n' "${MACHINFO_OUT}" | ${AWK} '
      BEGIN { bytes=0 }
      {
        line = $0
        if (match(line, /[Mm]emory[ \t=:]+[0-9]+[ \t]*[Mm][Bb]/)) {
          s = substr(line, RSTART, RLENGTH)
          gsub(/[^0-9]/, "", s)
          bytes = s * 1024 * 1024
        }
      }
      END { printf "%.0f", bytes }
    ')
  fi
fi

if [ "${MEM_TOTAL}" != "0" ] && [ "${MEM_USED}" != "0" ]; then
  MEM_USED_PCT=$(${AWK} -v t="${MEM_TOTAL}" -v u="${MEM_USED}" 'BEGIN {
    if (t<=0) { print 0; exit }
    printf "%.2f", (u/t)*100
  }')
fi

# --- disk: bdf / bdf -i; wrapped device lines; json_esc for mount/path ---
_parse_bdf_json() {
  printf '%s\n' "${1:-}" | ${AWK} "${_JSON_ESC_AWK}"'
    function join_from(a, start, n,    i, out) {
      out = ""
      for (i = start; i <= n; i++) {
        if (i > start) out = out " "
        out = out a[i]
      }
      return out
    }
    function emit(fs, kbytes, used, avail, usedpct, iused, ifree, ipct, mount,    total, usedb, freeb) {
      if (kbytes+0 <= 0 && used+0 <= 0 && avail+0 <= 0) return
      if (mount == "") mount = "/"
      if (!(mount in seen)) {
        n++
        order[n] = mount
        seen[mount] = 1
      }
      total = kbytes * 1024
      usedb = used * 1024
      freeb = avail * 1024
      if (freeb <= 0 && total > usedb) freeb = total - usedb
      if (total <= 0) total = usedb + freeb
      mt[mount] = mount
      pth[mount] = mount
      tot[mount] = total
      usd[mount] = usedb
      fre[mount] = freeb
      pct[mount] = usedpct+0
      iu[mount] = iused+0
      ifr[mount] = ifree+0
      ip[mount] = ipct+0
    }
    BEGIN { pending = ""; n = 0 }
    /Filesystem/ && /Mounted/ { next }
    /^[ \t]*$/ { next }
    $0 !~ /%/ {
      pending = $0
      gsub(/^[ \t]+|[ \t]+$/, "", pending)
      next
    }
    {
      line = $0
      gsub(/^[ \t]+/, "", line)
      if (pending != "") {
        line = pending " " line
        pending = ""
      }
      nfields = split(line, a, /[ \t]+/)
      pcts = 0
      for (i = 1; i <= nfields; i++) {
        if (a[i] ~ /%$/) {
          pcts++
          pidx[pcts] = i
        }
      }
      if (pcts < 1 || nfields < 5) next
      p1 = pidx[1]
      if (p1 < 4) next
      kbytes = a[p1-3]
      used = a[p1-2]
      avail = a[p1-1]
      usedpct = a[p1]
      gsub(/%/, "", usedpct)
      iused = 0
      ifree = 0
      ipct = 0
      if (pcts >= 2) {
        p2 = pidx[2]
        iused = a[p1+1]
        ifree = a[p1+2]
        ipct = a[p2]
        gsub(/%/, "", ipct)
        mount = join_from(a, p2+1, nfields)
      } else {
        mount = join_from(a, p1+1, nfields)
      }
      emit(a[1], kbytes, used, avail, usedpct, iused, ifree, ipct, mount)
    }
    END {
      printf "["
      for (i = 1; i <= n; i++) {
        m = order[i]
        if (i > 1) printf ","
        printf "{\"mount\":\"%s\",\"path\":\"%s\",\"fstype\":\"\",\"total_bytes\":%.0f,\"used_bytes\":%.0f,\"free_bytes\":%.0f,\"used_percent\":%.2f,\"inodes_used_percent\":%.2f,\"iused\":%.0f,\"ifree\":%.0f}", json_esc(mt[m]), json_esc(pth[m]), tot[m], usd[m], fre[m], pct[m], ip[m], iu[m], ifr[m]
      }
      printf "]"
    }
  '
}

if [ -n "${HPUX_MONITOR_PARSE_BDF:-}" ]; then
  BDF_IN=$(cat)
  DISK_JSON=$(_parse_bdf_json "${BDF_IN}")
  [ -z "${DISK_JSON}" ] && DISK_JSON='[]'
  printf '%s\n' "${DISK_JSON}"
  exit 0
fi

BDF_OUT=$(_run bdf -i)
if [ -z "${BDF_OUT}" ]; then
  BDF_OUT=$(_run bdf)
fi
DISK_JSON=$(_parse_bdf_json "${BDF_OUT}")
[ -z "${DISK_JSON}" ] && DISK_JSON='[]'

# --- diskio: sar -d 1 1 (%busy + combined blks/s); iostat fallback ---
DISKIO_JSON='[]'
SAR_D=$(_run sar -d 1 1)
if [ -n "${SAR_D}" ]; then
  DISKIO_JSON=$(printf '%s\n' "${SAR_D}" | ${AWK} "${_JSON_ESC_AWK}"'
    BEGIN { n=0; in_avg=0; busy_c=0; blks_c=0; rd_c=0; wr_c=0; brd_c=0; bwr_c=0; dev_c=0 }
    {
      low = tolower($0)
      if (low ~ /device/ && (low ~ /%busy/ || low ~ /blks/ || low ~ /bps/)) {
        for (i=1; i<=NF; i++) {
          col = tolower($i)
          gsub(/%/, "", col)
          if (col=="device" || col=="dev") dev_c=i
          if (col=="busy") busy_c=i
          if (col=="blks/s" || col=="blks") blks_c=i
          if (col=="rd/s" || col=="r/s") rd_c=i
          if (col=="wr/s" || col=="w/s") wr_c=i
          if (col=="brd/s" || col=="bread/s") brd_c=i
          if (col=="bwr/s" || col=="bwrtn/s") bwr_c=i
        }
        if (dev_c==0) dev_c=1
        next
      }
      if (tolower($1)=="average") in_avg=1
      if (dev_c==0) next
      dev = $dev_c
      if (tolower(dev)=="average") {
        if (NF > dev_c) dev = $(dev_c+1)
        else next
      }
      if (dev=="" || dev ~ /^-/ || dev ~ /[0-9]:[0-9]/) next
      if (dev ~ /^(HP-UX|device|Average)$/) next
      busy = (busy_c>0 ? $busy_c : 0)+0
      rbytes = 0
      wbytes = 0
      if (brd_c>0 || bwr_c>0) {
        rbytes = (brd_c>0 ? $brd_c : 0)+0
        wbytes = (bwr_c>0 ? $bwr_c : 0)+0
        rbytes *= 512
        wbytes *= 512
      } else if (blks_c>0) {
        rbytes = ($blks_c+0) * 512
        wbytes = 0
      } else next
      if (!(dev in seen)) {
        n++
        order[n] = dev
        seen[dev] = 1
      }
      r[dev] = rbytes
      w[dev] = wbytes
      b[dev] = busy
    }
    END {
      printf "["
      for (i=1; i<=n; i++) {
        d = order[i]
        if (i>1) printf ","
        printf "{\"device\":\"%s\",\"read_bytes\":%.0f,\"write_bytes\":%.0f,\"tm_act\":%.2f}", json_esc(d), r[d], w[d], b[d]
      }
      printf "]"
    }
  ')
fi

if [ -z "${DISKIO_JSON}" ] || [ "${DISKIO_JSON}" = "[]" ]; then
  IOSTAT_OUT=$(_run iostat 1 2)
  if [ -n "${IOSTAT_OUT}" ]; then
    DISKIO_JSON=$(printf '%s\n' "${IOSTAT_OUT}" | ${AWK} "${_JSON_ESC_AWK}"'
      BEGIN { n=0; mode=0 }
      tolower($1)=="device" { mode=1; next }
      mode==1 && NF>=2 && $1 !~ /^(tty|cpu|tin)$/ {
        dev=$1
        if (dev ~ /^[0-9.]+$/) next
        bps=$2+0
        if (!(dev in seen)) {
          n++
          order[n]=dev
          seen[dev]=1
        }
        r[dev]=bps*1024
        w[dev]=0
        b[dev]=0
      }
      END {
        printf "["
        for (i=1; i<=n; i++) {
          d=order[i]
          if (i>1) printf ","
          printf "{\"device\":\"%s\",\"read_bytes\":%.0f,\"write_bytes\":%.0f,\"tm_act\":%.2f}", json_esc(d), r[d], w[d], b[d]
        }
        printf "]"
      }
    ')
  fi
fi
[ -z "${DISKIO_JSON}" ] && DISKIO_JSON='[]'

# --- net: nwmgr / lanadmin MIB octets; lanscan for names; netstat -in fallback ---
NET_JSON='[]'
IFACES=""
LANSCAN_OUT=$(_run lanscan)
if [ -n "${LANSCAN_OUT}" ]; then
  IFACES=$(printf '%s\n' "${LANSCAN_OUT}" | ${AWK} '
    {
      for (i=1; i<=NF; i++) {
        if ($i ~ /^lan[0-9]+$/) print $i
      }
    }
  ' | sort | uniq)
fi
if [ -z "${IFACES}" ]; then
  LANSCAN_I=$(_run lanscan -i)
  if [ -n "${LANSCAN_I}" ]; then
    IFACES=$(printf '%s\n' "${LANSCAN_I}" | ${AWK} '
      {
        for (i=1; i<=NF; i++) {
          if ($i ~ /^lan[0-9]+$/) print $i
        }
      }
    ' | sort | uniq)
  fi
fi

NET_BUF=""
if [ -n "${IFACES}" ]; then
  for IFACE in ${IFACES}; do
    RX=0
    TX=0
    RXE=0
    TXE=0
    GOT=0
    NWMGR_OUT=$(_run nwmgr -g -c "${IFACE}")
    if [ -n "${NWMGR_OUT}" ]; then
      set -- $(printf '%s\n' "${NWMGR_OUT}" | ${AWK} '
        BEGIN { rx=0; tx=0; rxe=0; txe=0; got=0 }
        {
          line=$0
          if (match(line, /(Inbound Octets|InOctets|In Octets|Octets In)[ \t=:]+[0-9]+/)) {
            s=substr(line, RSTART, RLENGTH); gsub(/[^0-9]/, "", s); rx=s+0; got=1
          }
          if (match(line, /(Outbound Octets|OutOctets|Out Octets|Octets Out)[ \t=:]+[0-9]+/)) {
            s=substr(line, RSTART, RLENGTH); gsub(/[^0-9]/, "", s); tx=s+0; got=1
          }
          if (match(line, /(Inbound Errors|InErrors|In Errors)[ \t=:]+[0-9]+/)) {
            s=substr(line, RSTART, RLENGTH); gsub(/[^0-9]/, "", s); rxe=s+0
          }
          if (match(line, /(Outbound Errors|OutErrors|Out Errors)[ \t=:]+[0-9]+/)) {
            s=substr(line, RSTART, RLENGTH); gsub(/[^0-9]/, "", s); txe=s+0
          }
        }
        END { if (got) printf "%.0f %.0f %.0f %.0f 1", rx, tx, rxe, txe }
      ')
      if [ -n "$5" ]; then
        RX=$1; TX=$2; RXE=$3; TXE=$4; GOT=1
      fi
    fi
    if [ "${GOT}" = "0" ]; then
      PPA=$(printf '%s' "${IFACE}" | ${AWK} 'match($0, /[0-9]+$/) { print substr($0, RSTART, RLENGTH) }')
      [ -z "${PPA}" ] && PPA=0
      LANADMIN_OUT=$(_run lanadmin -g mibstats "${PPA}")
      if [ -n "${LANADMIN_OUT}" ]; then
        set -- $(printf '%s\n' "${LANADMIN_OUT}" | ${AWK} '
          BEGIN { rx=0; tx=0; rxe=0; txe=0; got=0 }
          {
            line=$0
            low=tolower(line)
            if (match(low, /in[ \t]*octets[ \t=:]+[0-9]+/) || match(low, /[0-9]+[ \t]+octets in/)) {
              s=substr(line, RSTART, RLENGTH); gsub(/[^0-9]/, "", s); rx=s+0; got=1
            }
            if (match(low, /out[ \t]*octets[ \t=:]+[0-9]+/) || match(low, /[0-9]+[ \t]+octets out/)) {
              s=substr(line, RSTART, RLENGTH); gsub(/[^0-9]/, "", s); tx=s+0; got=1
            }
            if (match(low, /in[ \t]*errors[ \t=:]+[0-9]+/)) {
              s=substr(line, RSTART, RLENGTH); gsub(/[^0-9]/, "", s); rxe=s+0
            }
            if (match(low, /out[ \t]*errors[ \t=:]+[0-9]+/)) {
              s=substr(line, RSTART, RLENGTH); gsub(/[^0-9]/, "", s); txe=s+0
            }
          }
          END { if (got) printf "%.0f %.0f %.0f %.0f 1", rx, tx, rxe, txe }
        ')
        if [ -n "$5" ]; then
          RX=$1; TX=$2; RXE=$3; TXE=$4; GOT=1
        fi
      fi
    fi
    if [ "${GOT}" = "1" ]; then
      IFACE_ESC=$(_json_str "${IFACE}")
      if [ -n "${NET_BUF}" ]; then
        NET_BUF="${NET_BUF},"
      fi
      NET_BUF="${NET_BUF}{\"interface\":\"${IFACE_ESC}\",\"rx_bytes\":$(_num "${RX}"),\"tx_bytes\":$(_num "${TX}"),\"rx_errors\":$(_num "${RXE}"),\"tx_errors\":$(_num "${TXE}")}"
    fi
  done
fi

if [ -n "${NET_BUF}" ]; then
  NET_JSON="[${NET_BUF}]"
else
  NETSTAT_OUT=$(_run netstat -in)
  if [ -n "${NETSTAT_OUT}" ]; then
    NET_JSON=$(printf '%s\n' "${NETSTAT_OUT}" | ${AWK} "${_JSON_ESC_AWK}"'
      BEGIN { n=0 }
      tolower($1)=="name" { next }
      $1 ~ /^(lo|lo0|gif|stf)/ { next }
      NF>=6 && $1 ~ /^[A-Za-z]/ {
        iface=$1
        gsub(/:$/, "", iface)
        if (!(iface in seen)) {
          n++
          order[n]=iface
          seen[iface]=1
        }
        # netstat -in on HP-UX is packets, not bytes
        rxb[iface]=0
        txb[iface]=0
        if (NF>=6) {
          rxerr[iface]=$5+0
          txerr[iface]=$7+0
        }
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
    ')
  fi
fi
[ -z "${NET_JSON}" ] && NET_JSON='[]'

OS_VER_ESC=$(_json_str "${OS_REL}")
OS_ARCH_ESC=$(_json_str "${OS_ARCH}")
OS_MACH_ESC=$(_json_str "${OS_MACH}")

printf '{'
printf '"os":{"version":"%s","release":"%s","arch":"%s","machine":"%s"},' \
  "${OS_VER_ESC}" "${OS_VER_ESC}" "${OS_ARCH_ESC}" "${OS_MACH_ESC}"
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
