#!/usr/bin/ksh
# BK-Lite AIX OS metrics collector.
# Original ksh for AIX 7.2/7.3. Calls only platform commands; skip if absent.
# Do not install Splunk TA or Telegraf on AIX.

set +e
export LC_ALL=C
export LANG=C
export PATH=/usr/bin:/usr/sbin:/bin:/sbin:${PATH}

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

_json_str() {
  printf '%s' "${1:-}" | awk '
    BEGIN { ORS="" }
    {
      gsub(/\\/, "\\\\")
      gsub(/"/, "\\\"")
      gsub(/\r/, "\\r")
      gsub(/\t/, "\\t")
      if (NR > 1) printf "\\n"
      printf "%s", $0
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

# AIX 7.2/7.3 default 4K pages.
PAGE_SIZE=4096

# --- uptime: load1/5/15 and seconds since boot ---
LOAD1=0
LOAD5=0
LOAD15=0
UPTIME_SEC=0
UPTIME_RAW=$(_run uptime)
if [ -n "${UPTIME_RAW}" ]; then
  set -- $(printf '%s\n' "${UPTIME_RAW}" | awk -F'load average:' '{
    if (NF < 2) next
    gsub(/,/, " ", $2)
    print $2
  }')
  [ -n "$1" ] && LOAD1=$1
  [ -n "$2" ] && LOAD5=$2
  [ -n "$3" ] && LOAD15=$3
  UPTIME_SEC=$(printf '%s\n' "${UPTIME_RAW}" | awk '
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

# --- CPU: mpstat ALL us/sy/wt/id (already percent). wait ≈ iowait. ---
CPU_USER=0
CPU_SYS=0
CPU_WAIT=0
CPU_IDLE=0
CPU_USAGE=0

MPSTAT_OUT=$(_run mpstat 1 1)
if [ -n "${MPSTAT_OUT}" ]; then
  set -- $(printf '%s\n' "${MPSTAT_OUT}" | awk '
    BEGIN { us_c=0; sy_c=0; wt_c=0; id_c=0 }
    {
      for (i=1; i<=NF; i++) {
        col=tolower($i)
        if (col=="us") us_c=i
        if (col=="sy") sy_c=i
        if (col=="wt" || col=="wa" || col=="wait") wt_c=i
        if (col=="id" || col=="idle") id_c=i
      }
    }
    $1=="ALL" && us_c>0 {
      last_us=$us_c+0
      last_sy=$sy_c+0
      last_wt=$wt_c+0
      last_id=$id_c+0
      found=1
    }
    END {
      if (found) printf "%.2f %.2f %.2f %.2f", last_us, last_sy, last_wt, last_id
    }
  ')
  if [ -n "$1" ]; then
    CPU_USER=$1
    CPU_SYS=$2
    CPU_WAIT=$3
    CPU_IDLE=$4
  fi
fi

if [ "${CPU_USER}" = "0" ] && [ "${CPU_SYS}" = "0" ] && [ "${CPU_IDLE}" = "0" ]; then
  LPAR_CPU=$(_run lparstat 1 1)
  if [ -n "${LPAR_CPU}" ]; then
    set -- $(printf '%s\n' "${LPAR_CPU}" | awk '
      /%user/ { next }
      $1 ~ /^[0-9]/ {
        printf "%.2f %.2f %.2f %.2f", $1+0, $2+0, $3+0, $4+0
        exit
      }
    ')
    if [ -n "$1" ]; then
      CPU_USER=$1
      CPU_SYS=$2
      CPU_WAIT=$3
      CPU_IDLE=$4
    fi
  fi
fi

CPU_USAGE=$(awk -v i="${CPU_IDLE}" 'BEGIN {
  v = 100 - (i + 0)
  if (v < 0) v = 0
  if (v > 100) v = 100
  printf "%.2f", v
}')

# --- lparstat entitled / vCPU ---
LPAR_ENT=0
LPAR_VCPU=0
LPAR_INFO=$(_run lparstat -i)
if [ -n "${LPAR_INFO}" ]; then
  LPAR_ENT=$(printf '%s\n' "${LPAR_INFO}" | awk -F':' '
    /Entitled Capacity/ && $0 !~ /Weight/ && $0 !~ /Delta/ {
      gsub(/^[ \t]+|[ \t]+$/, "", $2)
      print $2 + 0
      exit
    }
  ')
  LPAR_VCPU=$(printf '%s\n' "${LPAR_INFO}" | awk -F':' '
    /Online Virtual CPUs/ {
      gsub(/^[ \t]+|[ \t]+$/, "", $2)
      print $2 + 0
      exit
    }
  ')
fi
[ -z "${LPAR_ENT}" ] && LPAR_ENT=0
[ -z "${LPAR_VCPU}" ] && LPAR_VCPU=0

# --- memory: vmstat header mem= plus fre frames ---
MEM_TOTAL=0
MEM_FREE=0
MEM_USED=0
MEM_USED_PCT=0
VMSTAT_OUT=$(_run vmstat)
if [ -n "${VMSTAT_OUT}" ]; then
  MEM_TOTAL=$(printf '%s\n' "${VMSTAT_OUT}" | awk '
    /mem=/ {
      if (match($0, /mem=[0-9]+MB/)) {
        s = substr($0, RSTART, RLENGTH)
        gsub(/[^0-9]/, "", s)
        printf "%.0f", s * 1024 * 1024
        exit
      }
      if (match($0, /mem=[0-9]+GB/)) {
        s = substr($0, RSTART, RLENGTH)
        gsub(/[^0-9]/, "", s)
        printf "%.0f", s * 1024 * 1024 * 1024
        exit
      }
    }
  ')
  MEM_FREE=$(printf '%s\n' "${VMSTAT_OUT}" | awk -v pz="${PAGE_SIZE}" '
    BEGIN { seen_hdr=0 }
    /avm/ && /fre/ {
      for (i=1; i<=NF; i++) if ($i == "fre") fre_col=i
      seen_hdr=1
      next
    }
    seen_hdr && $1 ~ /^[0-9]/ {
      if (fre_col > 0) printf "%.0f", $(fre_col) * pz
      exit
    }
  ')
fi
[ -z "${MEM_TOTAL}" ] && MEM_TOTAL=0
[ -z "${MEM_FREE}" ] && MEM_FREE=0
MEM_USED=$(awk -v t="${MEM_TOTAL}" -v f="${MEM_FREE}" 'BEGIN {
  u = t - f
  if (u < 0) u = 0
  printf "%.0f", u
}')
MEM_USED_PCT=$(awk -v t="${MEM_TOTAL}" -v u="${MEM_USED}" 'BEGIN {
  if (t > 0) printf "%.2f", u * 100 / t
  else printf "0"
}')

# --- paging space from lsps ---
SWAP_TOTAL=0
SWAP_FREE=0
LSPS_OUT=$(_run lsps -s)
if [ -n "${LSPS_OUT}" ]; then
  set -- $(printf '%s\n' "${LSPS_OUT}" | awk '
    /MB/ {
      tot=$1
      gsub(/MB/, "", tot)
      pct=$NF
      gsub(/%/, "", pct)
      totb = tot * 1024 * 1024
      used = totb * (pct + 0) / 100
      free = totb - used
      if (free < 0) free = 0
      printf "%.0f %.0f", totb, free
      exit
    }
  ')
  [ -n "$1" ] && SWAP_TOTAL=$1
  [ -n "$2" ] && SWAP_FREE=$2
fi

# --- svmon work / pers / clnt / pin (pages -> bytes); skip if missing ---
SVMON_WORK=0
SVMON_PERS=0
SVMON_CLNT=0
SVMON_PIN=0
SVMON_OUT=$(_run svmon -G)
if [ -n "${SVMON_OUT}" ]; then
  set -- $(printf '%s\n' "${SVMON_OUT}" | awk -v pz="${PAGE_SIZE}" '
    BEGIN { work=0; pers=0; clnt=0; pin=0 }
    $1 == "in" && $2 == "use" {
      work = $3 + 0
      pers = $4 + 0
      clnt = $5 + 0
    }
    /^memory/ {
      if (NF >= 5) pin = $5 + 0
    }
    END {
      printf "%.0f %.0f %.0f %.0f", work*pz, pers*pz, clnt*pz, pin*pz
    }
  ')
  SVMON_WORK=$1
  SVMON_PERS=$2
  SVMON_CLNT=$3
  SVMON_PIN=$4
fi
[ -z "${SVMON_WORK}" ] && SVMON_WORK=0
[ -z "${SVMON_PERS}" ] && SVMON_PERS=0
[ -z "${SVMON_CLNT}" ] && SVMON_CLNT=0
[ -z "${SVMON_PIN}" ] && SVMON_PIN=0

# If vmstat did not yield total, use svmon memory size column.
if [ "${MEM_TOTAL}" = "0" ] && [ -n "${SVMON_OUT}" ]; then
  MEM_TOTAL=$(printf '%s\n' "${SVMON_OUT}" | awk -v pz="${PAGE_SIZE}" '
    $1 == "memory" { printf "%.0f", ($2 + 0) * pz; exit }
  ')
  [ -z "${MEM_TOTAL}" ] && MEM_TOTAL=0
  MEM_USED=$(awk -v t="${MEM_TOTAL}" -v f="${MEM_FREE}" 'BEGIN {
    u = t - f
    if (u < 0) u = 0
    printf "%.0f", u
  }')
  MEM_USED_PCT=$(awk -v t="${MEM_TOTAL}" -v u="${MEM_USED}" 'BEGIN {
    if (t > 0) printf "%.2f", u * 100 / t
    else printf "0"
  }')
fi

# --- df capacity + inodes ---
DISK_JSON=$(
  DF_K=$(_run df -k)
  DF_I=$(_run df -i)
  printf '%s\n' "${DF_K}" | awk -v dfi="${DF_I}" '
    BEGIN {
      first=1
      print "["
      n = split(dfi, lines, "\n")
      for (i = 1; i <= n; i++) {
        line = lines[i]
        nf = split(line, f)
        if (nf < 6) continue
        if (f[1] == "Filesystem" || f[nf] == "on") continue
        m = f[nf]
        inode_iused[m] = f[3] + 0
        inode_ifree[m] = f[4] + 0
        ip = f[5]
        gsub(/%/, "", ip)
        inode_ipct[m] = ip + 0
      }
    }
    NR == 1 { next }
    $1 ~ /^(procfs|proc|nfs|nfs3|nfs4|autofs|namefs|cdrom|iso9660|ahafs)$/ { next }
    $NF ~ /^\/proc/ { next }
    NF >= 7 {
      fs=$1
      total=$2 * 1024
      freeb=$3 * 1024
      usedpct=$4
      gsub(/%/, "", usedpct)
      iused=$5 + 0
      ipct=$6
      gsub(/%/, "", ipct)
      mount=$NF
      if (mount == "/proc" || mount == "/ahafs") next
      used = total - freeb
      if (used < 0) used = 0
      if (mount in inode_iused) {
        iused = inode_iused[mount]
        ifree = inode_ifree[mount]
        if (mount in inode_ipct) ipct = inode_ipct[mount]
      } else {
        if (ipct + 0 >= 100) ifree = 0
        else if (ipct + 0 <= 0) ifree = 0
        else ifree = int(iused * (100 - ipct) / ipct)
      }
      if (!first) printf ","
      first=0
      gsub(/\\/, "\\\\", fs)
      gsub(/"/, "\\\"", fs)
      gsub(/\\/, "\\\\", mount)
      gsub(/"/, "\\\"", mount)
      printf "{\"mount\":\"%s\",\"path\":\"%s\",\"fstype\":\"\",\"total_bytes\":%.0f,\"used_bytes\":%.0f,\"free_bytes\":%.0f,\"used_percent\":%.2f,\"inodes_used_percent\":%.2f,\"iused\":%.0f,\"ifree\":%.0f}", mount, mount, total, used, freeb, usedpct+0, ipct+0, iused+0, ifree+0
    }
    END { print "]" }
  '
)
[ -z "${DISK_JSON}" ] && DISK_JSON='[]'

# --- iostat: counters from first report, tm_act from last ---
DISKIO_JSON=$(
  IO_OUT=$(_run iostat -d 1 2)
  printf '%s\n' "${IO_OUT}" | awk '
    BEGIN { n=0; pass=0 }
    /^Disks:/ { pass++; next }
    pass>=1 && $1 !~ /^Disks:/ && NF>=6 && $1 !~ /^[0-9]/ && $1 != "tty:" && $1 != "cpu" {
      dev=$1
      if (dev == "Name") next
      tm=$2 + 0
      kbr=$5 + 0
      kbw=$6 + 0
      if (pass==1) {
        if (!(dev in seen1)) {
          seen1[dev]=1
          order[++n]=dev
        }
        read_b[dev]=kbr * 1024
        write_b[dev]=kbw * 1024
      } else {
        tm_act[dev]=tm
      }
    }
    END {
      printf "["
      for (i=1; i<=n; i++) {
        d=order[i]
        if (i>1) printf ","
        printf "{\"device\":\"%s\",\"read_bytes\":%.0f,\"write_bytes\":%.0f,\"tm_act\":%.2f}", d, read_b[d]+0, write_b[d]+0, tm_act[d]+0
      }
      printf "]"
    }
  '
)
[ -z "${DISKIO_JSON}" ] && DISKIO_JSON='[]'

# --- network: netstat -in errors; bytes from netstat -v then ifconfig ---
NET_JSON=$(
  NSIN=$(_run netstat -in)
  NSV=$(_run netstat -v)
  IFC=$(_run ifconfig -a)
  printf '%s\n' "${NSIN}" | awk -v nsv="${NSV}" -v ifc="${IFC}" '
    BEGIN {
      n=0
      # bytes from netstat -v adapter sections
      split(nsv, lines, "\n")
      iface=""
      for (i in lines) {
        line=lines[i]
        if (match(line, /\(([a-zA-Z0-9]+[0-9]*)\)/)) {
          iface=substr(line, RSTART+1, RLENGTH-2)
        }
        if (iface != "" && match(line, /Bytes received:[ \t]*[0-9]+/)) {
          s=substr(line, RSTART, RLENGTH)
          gsub(/[^0-9]/, "", s)
          rxb[iface]=s + 0
        }
        if (iface != "" && match(line, /Bytes transmitted:[ \t]*[0-9]+/)) {
          s=substr(line, RSTART, RLENGTH)
          gsub(/[^0-9]/, "", s)
          txb[iface]=s + 0
        }
      }
      # ifconfig fallback: "bytes: N" after an interface header
      split(ifc, flines, "\n")
      iface=""
      for (i in flines) {
        line=flines[i]
        if (match(line, /^[a-zA-Z][a-zA-Z0-9]*:/)) {
          iface=substr(line, 1, index(line, ":")-1)
        }
        if (iface != "" && match(line, /bytes:[ \t]*[0-9]+/)) {
          s=substr(line, RSTART, RLENGTH)
          gsub(/[^0-9]/, "", s)
          if (!(iface in rxb)) rxb[iface]=s + 0
        }
      }
    }
    NR==1 { next }
    $1 == "Name" { next }
    $1 ~ /^(lo0|lo)$/ { next }
    NF >= 8 {
      name=$1
      gsub(/\*$/, "", name)
      ipkts=$(NF-4)+0
      ierrs=$(NF-3)+0
      opkts=$(NF-2)+0
      oerrs=$(NF-1)+0
      if (name in seen) next
      seen[name]=1
      order[++n]=name
      rxerr[name]=ierrs
      txerr[name]=oerrs
    }
    END {
      printf "["
      for (i=1; i<=n; i++) {
        d=order[i]
        if (i>1) printf ","
        printf "{\"interface\":\"%s\",\"rx_bytes\":%.0f,\"tx_bytes\":%.0f,\"rx_errors\":%.0f,\"tx_errors\":%.0f}", d, rxb[d]+0, txb[d]+0, rxerr[d]+0, txerr[d]+0
      }
      printf "]"
    }
  '
)
[ -z "${NET_JSON}" ] && NET_JSON='[]'

# --- ps AIX state letters ---
PROC_JSON=$(
  PS_OUT=$(_run ps -A -o state=)
  if [ -z "${PS_OUT}" ]; then
    PS_OUT=$(_run ps -e -o s=)
  fi
  printf '%s\n' "${PS_OUT}" | awk '
    BEGIN { }
    {
      s=$1
      gsub(/[ \t]/, "", s)
      if (s == "") next
      c = substr(s, 1, 1)
      if (c ~ /[A-Za-z]/) cnt[c]++
    }
    END {
      printf "{"
      first=1
      for (k in cnt) {
        if (!first) printf ","
        first=0
        printf "\"%s\":%d", k, cnt[k]
      }
      printf "}"
    }
  '
)
[ -z "${PROC_JSON}" ] && PROC_JSON='{}'

# oslevel is informational; 7.x expected, missing tools already skipped
OSLEVEL=$(_run oslevel)
OSLEVEL=$(_json_str "${OSLEVEL}")

printf '{'
printf '"oslevel":"%s",' "${OSLEVEL}"
printf '"cpu":{"usage_percent":%s,"usage_user_percent":%s,"usage_system_percent":%s,"usage_iowait_percent":%s},' \
  "$(_num "${CPU_USAGE}")" "$(_num "${CPU_USER}")" "$(_num "${CPU_SYS}")" "$(_num "${CPU_WAIT}")"
printf '"mem":{"total_bytes":%s,"used_bytes":%s,"free_bytes":%s,"swap_total_bytes":%s,"swap_free_bytes":%s,"used_percent":%s},' \
  "$(_num "${MEM_TOTAL}")" "$(_num "${MEM_USED}")" "$(_num "${MEM_FREE}")" "$(_num "${SWAP_TOTAL}")" "$(_num "${SWAP_FREE}")" "$(_num "${MEM_USED_PCT}")"
printf '"svmon":{"work":%s,"pers":%s,"clnt":%s,"pin":%s},' \
  "$(_num "${SVMON_WORK}")" "$(_num "${SVMON_PERS}")" "$(_num "${SVMON_CLNT}")" "$(_num "${SVMON_PIN}")"
printf '"lpar":{"entitled_capacity":%s,"virtual_cpus":%s},' \
  "$(_num "${LPAR_ENT}")" "$(_num "${LPAR_VCPU}")"
printf '"disk":%s,' "${DISK_JSON}"
printf '"diskio":%s,' "${DISKIO_JSON}"
printf '"net":%s,' "${NET_JSON}"
printf '"processes":{"states":%s},' "${PROC_JSON}"
printf '"system":{"uptime_seconds":%s,"load1":%s,"load5":%s,"load15":%s}' \
  "$(_num "${UPTIME_SEC}")" "$(_num "${LOAD1}")" "$(_num "${LOAD5}")" "$(_num "${LOAD15}")"
printf '}\n'
