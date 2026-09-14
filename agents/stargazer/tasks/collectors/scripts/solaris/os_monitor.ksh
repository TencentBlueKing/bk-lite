#!/usr/bin/ksh
# BK-Lite Solaris OS metrics collector (x86 and SPARC).
# Collect via system commands; skip a command if it is missing.

set +e
export LC_ALL=C
export LANG=C
export PATH=/usr/bin:/usr/sbin:/bin:/sbin:/usr/xpg4/bin:${PATH}

if whence nawk >/dev/null 2>&1; then
  AWK=nawk
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

PAGE_SIZE=4096
PAGESIZE_OUT=$(_run pagesize)
if [ -n "${PAGESIZE_OUT}" ]; then
  case "${PAGESIZE_OUT}" in
    ''|*[!0-9]*) ;;
    *) PAGE_SIZE=${PAGESIZE_OUT} ;;
  esac
fi

OS_REL=$(_run uname -r)
OS_VER=$(_run uname -v)
OS_ARCH=$(_run uname -p)
OS_MACH=$(_run uname -m)
[ -z "${OS_REL}" ] && OS_REL=""
[ -z "${OS_VER}" ] && OS_VER=""
[ -z "${OS_ARCH}" ] && OS_ARCH=""
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

BOOT_TIME=""
KSTAT_BOOT=$(_run kstat -p unix:0:system_misc:boot_time)
if [ -n "${KSTAT_BOOT}" ]; then
  BOOT_TIME=$(printf '%s\n' "${KSTAT_BOOT}" | ${AWK} '{ print $NF+0; exit }')
fi
NOW=""
if _have perl; then
  NOW=$(perl -e 'print time' 2>/dev/null)
fi
if [ -z "${NOW}" ]; then
  NOW=$(printf '%(%s)T' now 2>/dev/null)
  case "${NOW}" in
    ''|*[!0-9]*) NOW="" ;;
  esac
fi
if [ -n "${NOW}" ] && [ -n "${BOOT_TIME}" ]; then
  UPTIME_KSTAT=$(${AWK} -v n="${NOW}" -v b="${BOOT_TIME}" 'BEGIN {
    v = n - b
    if (v < 0) v = 0
    printf "%.0f", v
  }')
  [ -n "${UPTIME_KSTAT}" ] && [ "${UPTIME_KSTAT}" != "0" ] && UPTIME_SEC=${UPTIME_KSTAT}
fi
[ -z "${UPTIME_SEC}" ] && UPTIME_SEC=0

# --- CPU: last mpstat report (usr/sys/wt/idl), else sar -u ---
CPU_USER=0
CPU_SYS=0
CPU_WAIT=0
CPU_IDLE=0
CPU_USAGE=0

MPSTAT_OUT=$(_run mpstat 1 2)
if [ -n "${MPSTAT_OUT}" ]; then
  set -- $(printf '%s\n' "${MPSTAT_OUT}" | ${AWK} '
    BEGIN { pass=0 }
    {
      line=$0
      low=tolower(line)
      if (low ~ /usr/ && (low ~ /sys/ || low ~ /system/) && (low ~ /idl/ || low ~ /idle/)) {
        pass++
        us_c=0; sy_c=0; wt_c=0; id_c=0
        for (i=1; i<=NF; i++) {
          col=tolower($i)
          gsub(/%/, "", col)
          if (col=="usr" || col=="user") us_c=i
          if (col=="sys" || col=="system") sy_c=i
          if (col=="wt" || col=="wio" || col=="wait") wt_c=i
          if (col=="idl" || col=="idle") id_c=i
        }
        n=0; sum_us=0; sum_sy=0; sum_wt=0; sum_id=0
        next
      }
      if (pass>0 && $1 ~ /^[0-9]+$/) {
        n++
        if (us_c>0) sum_us+=$us_c+0
        if (sy_c>0) sum_sy+=$sy_c+0
        if (wt_c>0) sum_wt+=$wt_c+0
        if (id_c>0) sum_id+=$id_c+0
      }
    }
    END {
      if (n>0) printf "%.2f %.2f %.2f %.2f", sum_us/n, sum_sy/n, sum_wt/n, sum_id/n
    }
  ')
  if [ -n "$1" ]; then
    CPU_USER=$1
    CPU_SYS=$2
    CPU_WAIT=$3
    CPU_IDLE=$4
  fi
fi

if [ "${CPU_USER}" = "0" ] && [ "${CPU_SYS}" = "0" ] && [ "${CPU_WAIT}" = "0" ]; then
  SAR_OUT=$(_run sar -u 1 1)
  if [ -n "${SAR_OUT}" ]; then
    set -- $(printf '%s\n' "${SAR_OUT}" | ${AWK} '
      BEGIN { us_c=0; sy_c=0; wt_c=0; id_c=0 }
      {
        low=tolower($0)
        if (low ~ /%usr/ || (low ~ /usr/ && low ~ /idle/)) {
          for (i=1; i<=NF; i++) {
            col=tolower($i)
            gsub(/%/, "", col)
            if (col=="usr" || col=="user") us_c=i
            if (col=="sys" || col=="system") sy_c=i
            if (col=="wio" || col=="wt" || col=="wait") wt_c=i
            if (col=="idle" || col=="idl") id_c=i
          }
          next
        }
        if (us_c>0 && $1 !~ /^[A-Za-z]/ && NF>=us_c) {
          last_us=$us_c+0
          last_sy=$sy_c+0
          last_wt=$wt_c+0
          last_id=$id_c+0
        }
      }
      END {
        if (us_c>0) printf "%.2f %.2f %.2f %.2f", last_us+0, last_sy+0, last_wt+0, last_id+0
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

CPU_USAGE=$(${AWK} -v u="${CPU_USER}" -v s="${CPU_SYS}" -v w="${CPU_WAIT}" 'BEGIN {
  v = (u + 0) + (s + 0) + (w + 0)
  if (v < 0) v = 0
  if (v > 100) v = 100
  printf "%.2f", v
}')

# --- memory: kstat pages, then prtconf / vmstat ---
MEM_TOTAL=0
MEM_FREE=0
MEM_USED=0
MEM_USED_PCT=0

KSTAT_PHYS=$(_run kstat -p unix:0:system_pages:physmem)
KSTAT_FREE=$(_run kstat -p unix:0:system_pages:freemem)
if [ -n "${KSTAT_PHYS}" ]; then
  PHYS_PAGES=$(printf '%s\n' "${KSTAT_PHYS}" | ${AWK} '{ print $NF+0; exit }')
  MEM_TOTAL=$(${AWK} -v p="${PHYS_PAGES}" -v z="${PAGE_SIZE}" 'BEGIN { printf "%.0f", p*z }')
fi
if [ -n "${KSTAT_FREE}" ]; then
  FREE_PAGES=$(printf '%s\n' "${KSTAT_FREE}" | ${AWK} '{ print $NF+0; exit }')
  MEM_FREE=$(${AWK} -v p="${FREE_PAGES}" -v z="${PAGE_SIZE}" 'BEGIN { printf "%.0f", p*z }')
fi

if [ "${MEM_TOTAL}" = "0" ]; then
  PRT_OUT=$(_run prtconf)
  if [ -n "${PRT_OUT}" ]; then
    MEM_TOTAL=$(printf '%s\n' "${PRT_OUT}" | ${AWK} '
      /[Mm]emory [Ss]ize:/ {
        for (i=1; i<=NF; i++) {
          if ($(i)+0>0 && $(i) !~ /:/) {
            n=$(i)+0
            unit=tolower($(i+1))
            if (unit ~ /^g/) printf "%.0f", n*1024*1024*1024
            else printf "%.0f", n*1024*1024
            exit
          }
        }
      }
    ')
    [ -z "${MEM_TOTAL}" ] && MEM_TOTAL=0
  fi
fi

if [ "${MEM_FREE}" = "0" ]; then
  VMSTAT_OUT=$(_run vmstat)
  if [ -n "${VMSTAT_OUT}" ]; then
    MEM_FREE=$(printf '%s\n' "${VMSTAT_OUT}" | ${AWK} -v pz="${PAGE_SIZE}" '
      BEGIN { fre_c=0 }
      /free/ && /r/ {
        for (i=1; i<=NF; i++) if ($i=="free") fre_c=i
        next
      }
      fre_c>0 && $1 ~ /^[0-9]/ {
        printf "%.0f", $(fre_c)*pz
      }
    ' | ${AWK} 'END { print $0+0 }')
    [ -z "${MEM_FREE}" ] && MEM_FREE=0
  fi
fi

if [ "${MEM_USED}" = "0" ] && [ "${MEM_TOTAL}" != "0" ]; then
  MEM_USED=$(${AWK} -v t="${MEM_TOTAL}" -v f="${MEM_FREE}" 'BEGIN {
    u = t - f
    if (u < 0) u = 0
    printf "%.0f", u
  }')
fi
[ -z "${MEM_TOTAL}" ] && MEM_TOTAL=0
[ -z "${MEM_USED}" ] && MEM_USED=0
[ -z "${MEM_FREE}" ] && MEM_FREE=0
MEM_USED_PCT=$(${AWK} -v t="${MEM_TOTAL}" -v u="${MEM_USED}" 'BEGIN {
  if (t > 0) printf "%.2f", u * 100 / t
  else printf "0"
}')

# --- swap -s ---
SWAP_TOTAL=0
SWAP_FREE=0
SWAP_OUT=$(_run swap -s)
if [ -n "${SWAP_OUT}" ]; then
  set -- $(printf '%s\n' "${SWAP_OUT}" | ${AWK} '
    {
      line=$0
      usedk=0; freek=0
      if (match(line, /[0-9]+k used/)) {
        s=substr(line, RSTART, RLENGTH)
        gsub(/[^0-9]/, "", s)
        usedk=s+0
      }
      if (match(line, /[0-9]+k available/)) {
        s=substr(line, RSTART, RLENGTH)
        gsub(/[^0-9]/, "", s)
        freek=s+0
      }
      if (usedk>0 || freek>0) {
        printf "%.0f %.0f", (usedk+freek)*1024, freek*1024
        exit
      }
    }
  ')
  [ -n "$1" ] && SWAP_TOTAL=$1
  [ -n "$2" ] && SWAP_FREE=$2
fi
[ -z "${SWAP_TOTAL}" ] && SWAP_TOTAL=0
[ -z "${SWAP_FREE}" ] && SWAP_FREE=0

# --- df -k capacity; df -n fstype; df -o i inodes when present ---
DF_K=""
DF_N=""
DF_I=""
if _have df; then
  DF_K=$(df -k 2>/dev/null)
  DF_N=$(df -n 2>/dev/null)
  DF_I=$(df -o i 2>/dev/null)
fi
DISK_JSON=$(
  {
    printf '%s\n' '---CAP---'
    printf '%s\n' "${DF_K}"
    printf '%s\n' '---TYPE---'
    printf '%s\n' "${DF_N}"
    printf '%s\n' '---INO---'
    printf '%s\n' "${DF_I}"
  } | ${AWK} "${_JSON_ESC_AWK}"'
    function skip_fs(m, fs) {
      if (m=="" || m=="on") return 1
      if (m=="/proc" || m=="/etc/mnttab" || m=="/devices" || m=="/dev/fd") return 1
      if (m ~ /^\/proc/ || m ~ /^\/system\// || m ~ /^\/devices/) return 1
      if (fs ~ /^(proc|procfs|mntfs|ctfs|objfs|sharefs|fd|autofs|hsfs|nfs|nfs3|nfs4|devfs|ficlone)$/) return 1
      return 0
    }
    function fields_from(start,    i, m) {
      if (NF < start) return $NF
      m = $start
      for (i = start + 1; i <= NF; i++) m = m " " $i
      return m
    }
    function is_cap_hdr(    i, t) {
      for (i=1; i<=NF; i++) {
        t=tolower($i)
        if (t=="filesystem" || t=="kbytes" || t=="capacity" || t=="mounted") return 1
      }
      return 0
    }
    function is_ino_hdr(    i, t) {
      for (i=1; i<=NF; i++) {
        t=tolower($i)
        if (t=="iused" || t=="%iused" || t=="ifree" || t=="inodes") return 1
      }
      return 0
    }
    BEGIN { mode=""; nm=0 }
    $0=="---CAP---" { mode="cap"; next }
    $0=="---TYPE---" { mode="typ"; next }
    $0=="---INO---" { mode="ino"; next }
    NF==0 { next }
    mode=="cap" {
      if (is_cap_hdr()) next
      mount=fields_from(6)
      fs=$1
      if (NF<5) next
      if (skip_fs(mount, fs)) next
      total=$2+0; used=$3+0; avail=$4+0
      pct=$5
      gsub(/%/, "", pct)
      pct+=0
      if (total<=0 && used+avail>0) total=used+avail
      if (total<=0 && used<=0 && avail<=0) next
      if (pct==0 && total>0) pct=used*100/total
      if (!(mount in seenm)) { seenm[mount]=1; order[++nm]=mount }
      tot[mount]=total*1024
      ukb[mount]=used*1024
      fkb[mount]=avail*1024
      pc[mount]=pct
      next
    }
    mode=="typ" {
      fs=""
      mount=""
      if (match($0, /^[^:]+/)) mount=substr($0, RSTART, RLENGTH)
      gsub(/[ \t]+$/, "", mount)
      if (match($0, /:[ \t]*[A-Za-z0-9_]+/)) {
        fs=substr($0, RSTART)
        sub(/^:[ \t]*/, "", fs)
      }
      if (mount!="" && fs!="") ftype[mount]=fs
      next
    }
    mode=="ino" {
      if (is_ino_hdr()) next
      mount=fields_from(5)
      if (mount=="" || mount=="on") next
      iu=0; ifr=0; ip=0
      if (NF>=4) {
        iu=$2+0
        ifr=$3+0
        ip=$4
        gsub(/%/, "", ip)
        ip+=0
      }
      if (ip==0 && (iu+ifr)>0) ip=iu*100/(iu+ifr)
      iu_m[mount]=iu
      ifr_m[mount]=ifr
      ip_m[mount]=ip
      next
    }
    END {
      printf "["
      for (i=1; i<=nm; i++) {
        m=order[i]
        if (i>1) printf ","
        printf "{\"mount\":\"%s\",\"path\":\"%s\",\"fstype\":\"%s\",\"total_bytes\":%.0f,\"used_bytes\":%.0f,\"free_bytes\":%.0f,\"used_percent\":%.2f,\"inodes_used_percent\":%.2f,\"iused\":%.0f,\"ifree\":%.0f}", json_esc(m), json_esc(m), json_esc(ftype[m]), tot[m]+0, ukb[m]+0, fkb[m]+0, pc[m]+0, ip_m[m]+0, iu_m[m]+0, ifr_m[m]+0
      }
      printf "]"
    }
  '
)
[ -z "${DISK_JSON}" ] && DISK_JSON='[]'

# --- iostat -x 1 2: last report is the interval sample; %b is busy ---
DISKIO_JSON=$(
  IO_OUT=$(_run iostat -x 1 2)
  printf '%s\n' "${IO_OUT}" | ${AWK} "${_JSON_ESC_AWK}"'
    function io_header(    i, col) {
      r_c=0; w_c=0; b_c=0
      for (i=1; i<=NF; i++) {
        col=tolower($i)
        gsub(/%/, "", col)
        if (col=="kr/s" || col=="krs") r_c=i
        else if (col=="kw/s" || col=="kws") w_c=i
        else if (col=="b") b_c=i
      }
    }
    function is_io_hdr() {
      low=tolower($0)
      if (low ~ /kr\/s/ && low ~ /kw\/s/) return 1
      if (low ~ /device/ && low ~ /%b/) return 1
      return 0
    }
    BEGIN { pass=0 }
    NF==0 { next }
    is_io_hdr() {
      pass++
      io_header()
      next
    }
    pass>0 && $1 ~ /^[A-Za-z][A-Za-z0-9._-]*$/ {
      dev=$1
      if (dev=="device" || dev=="extended" || dev=="tty" || dev=="cpu" || dev=="nfs") next
      if (r_c>0 && NF<r_c) next
      if (!(pass SUBSEP dev in seenp)) {
        seenp[pass SUBSEP dev]=1
        n[pass]++
        order[pass, n[pass]]=dev
      }
      if (r_c>0) rkb[pass, dev]=$(r_c)+0
      if (w_c>0) wkb[pass, dev]=$(w_c)+0
      if (b_c>0) tma[pass, dev]=$(b_c)+0
    }
    END {
      src=0
      for (p=1; p<=pass; p++) if (n[p]>0) src=p
      printf "["
      if (src>0) {
        for (i=1; i<=n[src]; i++) {
          d=order[src, i]
          if (i>1) printf ","
          printf "{\"device\":\"%s\",\"read_bytes\":%.0f,\"write_bytes\":%.0f,\"tm_act\":%.2f}", json_esc(d), rkb[src, d]*1024, wkb[src, d]*1024, tma[src, d]+0
        }
      }
      printf "]"
    }
  '
)
[ -z "${DISKIO_JSON}" ] && DISKIO_JSON='[]'

# --- network: kstat counters, then dlstat, then netstat -in ---
NET_JSON=$(
  {
    printf '%s\n' '---KSTAT---'
    _run kstat -p
    printf '%s\n' '---DLSTAT---'
    if _have dlstat; then
      dlstat show-link 2>/dev/null
    fi
    printf '%s\n' '---NETSTAT---'
    _run netstat -in
  } | ${AWK} "${_JSON_ESC_AWK}"'
    function note(ifn) {
      if (ifn=="" || ifn=="lo" || ifn=="lo0" || ifn ~ /^lo[0-9]/) return
      if (ifn=="mac" || ifn=="statistics" || ifn=="class") return
      if (!(ifn in seen)) { seen[ifn]=1; order[++n]=ifn }
    }
    function prefer(cur, neu) {
      if (neu=="") return cur
      if (cur=="" || (neu+0)>=0) return neu
      return cur
    }
    BEGIN { mode=""; n=0 }
    $0=="---KSTAT---" { mode="kstat"; next }
    $0=="---DLSTAT---" { mode="dlstat"; next }
    $0=="---NETSTAT---" { mode="netstat"; next }
    mode=="kstat" {
      key=$1
      val=$2+0
      nfields=split(key, a, ":")
      if (nfields<4) next
      module=a[1]; inst=a[2]; name=a[3]; stat=a[4]
      if (name ~ /^[A-Za-z][A-Za-z0-9_]*[0-9][0-9]*$/) iface=name
      else if (name=="mac" && module ~ /[0-9]$/) iface=module
      else if (name=="mac") iface=module inst
      else if (module=="link") iface=name
      else next
      if (stat=="rbytes64" || (stat=="rbytes" && !(iface in rxb64))) {
        if (stat=="rbytes64") { rxb64[iface]=val; rxb[iface]=val }
        else rxb[iface]=val
        note(iface)
      }
      if (stat=="obytes64" || (stat=="obytes" && !(iface in txb64))) {
        if (stat=="obytes64") { txb64[iface]=val; txb[iface]=val }
        else txb[iface]=val
        note(iface)
      }
      if (stat=="ierrors") { rxerr[iface]=val; note(iface) }
      if (stat=="oerrors") { txerr[iface]=val; note(iface) }
      next
    }
    mode=="dlstat" {
      low=tolower($1)
      if (low=="link" || low=="ifname") next
      if (NF<5) next
      iface=$1
      if (!(iface in rxb)) rxb[iface]=$3+0
      if (!(iface in txb)) txb[iface]=$5+0
      note(iface)
      next
    }
    mode=="netstat" {
      if ($1=="Name" || $1=="name") next
      iface=$1
      sub(/\*$/, "", iface)
      if (iface=="" || NF<8) next
      note(iface)
      if (!(iface in rxerr)) rxerr[iface]=$5+0
      if (!(iface in txerr)) txerr[iface]=$7+0
      next
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

OS_REL_J=$(_json_str "${OS_REL}")
OS_VER_J=$(_json_str "${OS_VER}")
OS_ARCH_J=$(_json_str "${OS_ARCH}")
OS_MACH_J=$(_json_str "${OS_MACH}")

printf '{'
printf '"os":{"version":"%s","release":"%s","arch":"%s","machine":"%s"},' \
  "${OS_REL_J}" "${OS_VER_J}" "${OS_ARCH_J}" "${OS_MACH_J}"
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
