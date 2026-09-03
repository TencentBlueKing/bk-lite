#!/usr/bin/ksh
# BK-Lite AIX OS metrics collector.
# Collect via AIX system commands; skip a command if it is missing.
# OS level from oslevel -r (for example 7100-00).

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

# Default 4K pages; prefer the host pagesize command when present.
PAGE_SIZE=4096
PAGESIZE_OUT=$(_run pagesize)
if [ -n "${PAGESIZE_OUT}" ]; then
  case "${PAGESIZE_OUT}" in
    ''|*[!0-9]*) ;;
    *) PAGE_SIZE=${PAGESIZE_OUT} ;;
  esac
fi

# oslevel -r prefix (7100/7200/7300) selects parse branches. Not a form field.
# 7.1 field evidence used oslevel -s 7100-00-10-1334; -r empty still reads -s.
OSLEVEL_RAW=$(_run oslevel -r)
[ -z "${OSLEVEL_RAW}" ] && OSLEVEL_RAW=$(_run oslevel -s)
AIX_REL=$(printf '%s\n' "${OSLEVEL_RAW}" | awk '{ print substr($1, 1, 4)+0 }')
[ -z "${AIX_REL}" ] && AIX_REL=0

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

# --- CPU: mpstat -a (ALL row, else average per-cpu). Total = user + sys + iowait. ---
CPU_USER=0
CPU_SYS=0
CPU_WAIT=0
CPU_IDLE=0
CPU_USAGE=0

MPSTAT_OUT=$(_run mpstat -a)
if [ -n "${MPSTAT_OUT}" ]; then
  set -- $(printf '%s\n' "${MPSTAT_OUT}" | awk '
    BEGIN { us_c=0; sy_c=0; wt_c=0; id_c=0; n=0 }
    tolower($1)=="cpu" {
      for (i=1; i<=NF; i++) {
        col=tolower($i)
        if (col=="us" || col=="user") us_c=i
        if (col=="sy" || col=="sys" || col=="system") sy_c=i
        if (col=="wt" || col=="wa" || col=="wait") wt_c=i
        if (col=="id" || col=="idle") id_c=i
      }
      next
    }
    us_c>0 && $1=="ALL" {
      last_us=$us_c+0
      last_sy=$sy_c+0
      last_wt=$wt_c+0
      last_id=$id_c+0
      found_all=1
    }
    us_c>0 && $1 ~ /^[0-9]+$/ {
      n++
      sum_us+=$us_c+0
      sum_sy+=$sy_c+0
      sum_wt+=$wt_c+0
      sum_id+=$id_c+0
    }
    END {
      if (found_all) printf "%.2f %.2f %.2f %.2f", last_us, last_sy, last_wt, last_id
      else if (n>0) printf "%.2f %.2f %.2f %.2f", sum_us/n, sum_sy/n, sum_wt/n, sum_id/n
    }
  ')
  if [ -n "$1" ]; then
    CPU_USER=$1
    CPU_SYS=$2
    CPU_WAIT=$3
    CPU_IDLE=$4
    CPU_USAGE=$(awk -v u="${CPU_USER}" -v s="${CPU_SYS}" -v w="${CPU_WAIT}" 'BEGIN {
      v = (u + 0) + (s + 0) + (w + 0)
      if (v < 0) v = 0
      if (v > 100) v = 100
      printf "%.2f", v
    }')
  fi
fi

# --- lparstat -i: Entitled Capacity, Online Virtual CPUs ---
LPAR_ENT=0
LPAR_VCPU=0
LPAR_INFO=$(_run lparstat -i)
if [ -n "${LPAR_INFO}" ]; then
  LPAR_ENT=$(printf '%s\n' "${LPAR_INFO}" | awk -F':' '
    {
      label=$1
      gsub(/^[ \t]+|[ \t]+$/, "", label)
      if (label == "Entitled Capacity") {
        gsub(/^[ \t]+|[ \t]+$/, "", $2)
        print $2 + 0
        exit
      }
    }
  ')
  LPAR_VCPU=$(printf '%s\n' "${LPAR_INFO}" | awk -F':' '
    {
      label=$1
      gsub(/^[ \t]+|[ \t]+$/, "", label)
      if (label == "Online Virtual CPUs") {
        gsub(/^[ \t]+|[ \t]+$/, "", $2)
        print $2 + 0
        exit
      }
    }
  ')
fi
[ -z "${LPAR_ENT}" ] && LPAR_ENT=0
[ -z "${LPAR_VCPU}" ] && LPAR_VCPU=0

# --- svmon: call svmon, then svmon -G if the memory row is missing ---
# Pin is memory-row pin column only. The pin-breakdown row must not overwrite it.
MEM_TOTAL=0
MEM_FREE=0
MEM_USED=0
MEM_USED_PCT=0
SVMON_WORK=0
SVMON_PERS=0
SVMON_CLNT=0
SVMON_PIN=0
SVMON_OUT=$(_run svmon)
_svmon_has_memory=$(printf '%s\n' "${SVMON_OUT}" | awk '/^memory/ { print 1; exit }')
if [ -z "${_svmon_has_memory}" ]; then
  SVMON_G=$(_run svmon -G)
  [ -n "${SVMON_G}" ] && SVMON_OUT=${SVMON_G}
fi
if [ -n "${SVMON_OUT}" ]; then
  set -- $(printf '%s\n' "${SVMON_OUT}" | awk -v pz="${PAGE_SIZE}" '
    BEGIN { work=0; pers=0; clnt=0; pin=0; msize=0; minuse=0; mfree=0 }
    $1 == "in" && $2 == "use" {
      work = $3 + 0
      pers = $4 + 0
      clnt = $5 + 0
    }
    /^memory/ {
      if (NF >= 5) {
        msize = $2 + 0
        minuse = $3 + 0
        mfree = $4 + 0
        pin = $5 + 0
      }
    }
    END {
      printf "%.0f %.0f %.0f %.0f %.0f %.0f %.0f", work*pz, pers*pz, clnt*pz, pin*pz, msize*pz, minuse*pz, mfree*pz
    }
  ')
  SVMON_WORK=$1
  SVMON_PERS=$2
  SVMON_CLNT=$3
  SVMON_PIN=$4
  [ -n "$5" ] && MEM_TOTAL=$5
  [ -n "$6" ] && MEM_USED=$6
  [ -n "$7" ] && MEM_FREE=$7
fi
[ -z "${SVMON_WORK}" ] && SVMON_WORK=0
[ -z "${SVMON_PERS}" ] && SVMON_PERS=0
[ -z "${SVMON_CLNT}" ] && SVMON_CLNT=0
[ -z "${SVMON_PIN}" ] && SVMON_PIN=0
[ -z "${MEM_TOTAL}" ] && MEM_TOTAL=0
[ -z "${MEM_USED}" ] && MEM_USED=0
[ -z "${MEM_FREE}" ] && MEM_FREE=0

# --- vmstat 1 1: fallback total/free when svmon did not yield memory ---
VMSTAT_OUT=$(_run vmstat 1 1)
if [ -n "${VMSTAT_OUT}" ]; then
  if [ "${MEM_TOTAL}" = "0" ]; then
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
    [ -z "${MEM_TOTAL}" ] && MEM_TOTAL=0
  fi
  if [ "${MEM_FREE}" = "0" ]; then
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
    [ -z "${MEM_FREE}" ] && MEM_FREE=0
  fi
  if [ "${MEM_USED}" = "0" ] && [ "${MEM_TOTAL}" != "0" ]; then
    MEM_USED=$(awk -v t="${MEM_TOTAL}" -v f="${MEM_FREE}" 'BEGIN {
      u = t - f
      if (u < 0) u = 0
      printf "%.0f", u
    }')
  fi
fi

MEM_USED_PCT=$(awk -v t="${MEM_TOTAL}" -v u="${MEM_USED}" 'BEGIN {
  if (t > 0) printf "%.2f", u * 100 / t
  else printf "0"
}')

# --- paging space from lsps -s ---
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

# --- df: IBM -F header parse on all levels. Never treat %used as bytes.
# 7100 only: if -F yields no mounts, df -kP capacity + df -i inodes. ---
DF_OUT=""
if _have df; then
  DF_OUT=$(df -kP -F '%u %f %z %l %n %p %m' 2>/dev/null)
fi
DISK_JSON=$(
  printf '%s\n' "${DF_OUT}" | awk '
    function reset_cols() {
      used_c=0; free_c=0; pct_c=0; iused_c=0; ifree_c=0; ipct_c=0; alloc_c=0
    }
    function is_header(    i, t) {
      for (i=1; i<=NF; i++) {
        t=tolower($i)
        if (t=="filesystem" || t=="allocated" || t=="1024-blocks" || t=="512-blocks" || t=="%used" || t=="iused" || t=="%iused" || t=="ifree" || t=="mounted" || t=="capacity") return 1
      }
      return 0
    }
    function map_header(    i, t) {
      reset_cols()
      for (i=1; i<=NF; i++) {
        t=tolower($i)
        if (t=="1024-blocks" || t=="512-blocks" || t=="allocated") alloc_c=i
        else if (t=="%used" || t=="capacity" || t=="use%") pct_c=i
        else if (t=="%iused") ipct_c=i
        else if (t=="used") used_c=i
        else if (t=="free" || t=="available") free_c=i
        else if (t=="iused") iused_c=i
        else if (t=="ifree") ifree_c=i
      }
    }
    function num_at(c,    s) {
      if (c<1 || c>NF) return 0
      s=$c
      gsub(/%/, "", s)
      return s+0
    }
    function skip_fs(m, fs) {
      if (m=="on" || m=="/proc" || m=="/ahafs" || m ~ /^\/proc/ || m ~ /^\/ahafs/) return 1
      if (fs ~ /^(procfs|proc|nfs|nfs3|nfs4|autofs|namefs|cdrom|iso9660|ahafs)$/) return 1
      if (fs=="/proc" || fs=="/ahafs") return 1
      return 0
    }
    BEGIN { first=1; have_hdr=0; print "[" }
    NF==0 { next }
    is_header() { map_header(); have_hdr=1; next }
    $NF=="on" { next }
    {
      mount=$NF
      fs=$1
      if (skip_fs(mount, fs)) next
      usedkb=0; freekb=0; allockb=0; iused=0; ifree=0; pct=0; ipct=0
      mapped=0
      if (have_hdr && used_c>0 && free_c>0) {
        usedkb=num_at(used_c)
        freekb=num_at(free_c)
        if (pct_c>0) pct=num_at(pct_c)
        if (iused_c>0) iused=num_at(iused_c)
        if (ifree_c>0) ifree=num_at(ifree_c)
        if (ipct_c>0) ipct=num_at(ipct_c)
        if (alloc_c>0) allockb=num_at(alloc_c)
        mapped=1
      }
      if (!mapped && $1 ~ /^[0-9]/ && NF>=7) {
        usedkb=$1+0; freekb=$2+0; pct=$3; iused=$4+0; ifree=$5+0; ipct=$6
        gsub(/%/, "", pct); gsub(/%/, "", ipct); pct+=0; ipct+=0
        mapped=1
      }
      if (!mapped && NF>=9) {
        allockb=$2+0; usedkb=$3+0; freekb=$4+0; pct=$5; iused=$6+0; ifree=$7+0; ipct=$8
        gsub(/%/, "", pct); gsub(/%/, "", ipct); pct+=0; ipct+=0
        mapped=1
      }
      if (!mapped && NF==8 && $1 !~ /^[0-9]/) {
        usedkb=$2+0; freekb=$3+0; pct=$4; iused=$5+0; ifree=$6+0; ipct=$7
        gsub(/%/, "", pct); gsub(/%/, "", ipct); pct+=0; ipct+=0
        mapped=1
      }
      if (!mapped) next
      if (allockb<=0) allockb=usedkb+freekb
      if (ipct==0 && (iused+ifree)>0) ipct=iused*100/(iused+ifree)
      if (!first) printf ","
      first=0
      gsub(/\\/, "\\\\", mount)
      gsub(/"/, "\\\"", mount)
      printf "{\"mount\":\"%s\",\"path\":\"%s\",\"fstype\":\"\",\"total_bytes\":%.0f,\"used_bytes\":%.0f,\"free_bytes\":%.0f,\"used_percent\":%.2f,\"inodes_used_percent\":%.2f,\"iused\":%.0f,\"ifree\":%.0f}", mount, mount, allockb*1024, usedkb*1024, freekb*1024, pct+0, ipct+0, iused+0, ifree+0
    }
    END { print "]" }
  '
)
_DF_HAS_MOUNT=$(printf '%s' "${DISK_JSON}" | awk 'index($0, "\"mount\"") { print 1; exit }')
if [ "${AIX_REL}" = "7100" ] && [ "${_DF_HAS_MOUNT}" != "1" ]; then
  DF_KP=""
  DF_I=""
  if _have df; then
    DF_KP=$(df -kP 2>/dev/null)
    DF_I=$(df -i 2>/dev/null)
  fi
  DISK_JSON=$(
    {
      printf '%s\n' '---KP---'
      printf '%s\n' "${DF_KP}"
      printf '%s\n' '---IN---'
      printf '%s\n' "${DF_I}"
    } | awk '
      function reset_cols() {
        used_c=0; free_c=0; pct_c=0; iused_c=0; ifree_c=0; ipct_c=0; alloc_c=0
      }
      function is_header(    i, t) {
        for (i=1; i<=NF; i++) {
          t=tolower($i)
          if (t=="filesystem" || t=="allocated" || t=="1024-blocks" || t=="512-blocks" || t=="%used" || t=="iused" || t=="%iused" || t=="ifree" || t=="mounted" || t=="capacity" || t=="available" || t=="inodes") return 1
        }
        return 0
      }
      function map_header(    i, t) {
        reset_cols()
        for (i=1; i<=NF; i++) {
          t=tolower($i)
          if (t=="1024-blocks" || t=="512-blocks" || t=="allocated") alloc_c=i
          else if (t=="%used" || t=="capacity" || t=="use%") pct_c=i
          else if (t=="%iused") ipct_c=i
          else if (t=="used") used_c=i
          else if (t=="free" || t=="available") free_c=i
          else if (t=="iused") iused_c=i
          else if (t=="ifree") ifree_c=i
        }
      }
      function num_at(c,    s) {
        if (c<1 || c>NF) return 0
        s=$c
        gsub(/%/, "", s)
        return s+0
      }
      function skip_fs(m, fs) {
        if (m=="on" || m=="/proc" || m=="/ahafs" || m ~ /^\/proc/ || m ~ /^\/ahafs/) return 1
        if (fs ~ /^(procfs|proc|autofs|namefs|cdrom|iso9660|ahafs)$/) return 1
        if (fs=="/proc" || fs=="/ahafs") return 1
        return 0
      }
      BEGIN { mode=""; nm=0 }
      $0=="---KP---" { mode="kp"; reset_cols(); next }
      $0=="---IN---" { mode="in"; reset_cols(); next }
      NF==0 { next }
      is_header() { map_header(); next }
      $NF=="on" { next }
      mode=="kp" {
        mount=$NF
        fs=$1
        if (skip_fs(mount, fs)) next
        usedkb=num_at(used_c)
        freekb=num_at(free_c)
        allockb=num_at(alloc_c)
        pct=num_at(pct_c)
        if (used_c==0 && free_c==0 && alloc_c==0 && NF>=6 && $2+0>0) {
          allockb=$2+0
          usedkb=$3+0
          freekb=$4+0
          pct=$5
          gsub(/%/, "", pct)
          pct+=0
        }
        if (usedkb<=0 && allockb>0) usedkb=allockb-freekb
        if (usedkb<0) usedkb=0
        if (allockb<=0) allockb=usedkb+freekb
        if (allockb<=0 && usedkb<=0 && freekb<=0) next
        if (pct==0 && allockb>0) pct=usedkb*100/allockb
        if (!(mount in seenm)) { seenm[mount]=1; order[++nm]=mount }
        ukb[mount]=usedkb
        fkb[mount]=freekb
        akb[mount]=allockb
        pc[mount]=pct
        next
      }
      mode=="in" {
        mount=$NF
        fs=$1
        if (skip_fs(mount, fs)) next
        iu=num_at(iused_c)
        ifr=num_at(ifree_c)
        ip=num_at(ipct_c)
        if (ifr==0 && ip>0 && ip<100 && iu>0) ifr=int(iu*(100-ip)/ip+0.5)
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
          mm=m
          gsub(/\\/, "\\\\", mm)
          gsub(/"/, "\\\"", mm)
          printf "{\"mount\":\"%s\",\"path\":\"%s\",\"fstype\":\"\",\"total_bytes\":%.0f,\"used_bytes\":%.0f,\"free_bytes\":%.0f,\"used_percent\":%.2f,\"inodes_used_percent\":%.2f,\"iused\":%.0f,\"ifree\":%.0f}", mm, mm, akb[m]*1024, ukb[m]*1024, fkb[m]*1024, pc[m]+0, ip_m[m]+0, iu_m[m]+0, ifr_m[m]+0
        }
        printf "]"
      }
    '
  )
fi
[ -z "${DISK_JSON}" ] && DISK_JSON='[]'

# --- iostat: header names. Interval sample by default.
# 7100 only: if that sample is all zeros, JSON keeps the earlier report's
# tm_act and KB (same shape as 7.1 field v2). Interval KB goes in *_interval
# for rate series only. ---
DISKIO_JSON=$(
  IO_OUT=$(_run iostat -d 1 2)
  printf '%s\n' "${IO_OUT}" | awk -v aixrel="${AIX_REL}" '
    function io_header(    i, tok, nxt, low, col) {
      tm_c=0; read_c=0; write_c=0
      col=0
      i=1
      while (i<=NF) {
        tok=$i
        low=tolower(tok)
        if (tok=="%" && i<NF) {
          nxt=tolower($(i+1))
          if (nxt=="tm_act" || nxt=="tmact") {
            tok="%tm_act"
            low="tm_act"
            i++
          }
        }
        col++
        gsub(/:/, "", low)
        gsub(/%/, "", low)
        if (low=="tm_act" || low=="tmact") tm_c=col
        else if (low=="kb_read" || low=="kbread" || low=="bread") read_c=col
        else if (low=="kb_wrtn" || low=="kbwrtn" || low=="bwrtn" || low=="kb_write" || low=="kbwrite") write_c=col
        i++
      }
    }
    function is_io_hdr() {
      if ($0 ~ /^[ \t]*Disks:/) return 1
      if ($0 ~ /tm_act/ && $0 ~ /Kb_read|kb_read|bread|Kb_wrtn|kb_wrtn/) return 1
      return 0
    }
    function report_idle(p,    i, d) {
      if (n[p]<1) return 1
      for (i=1; i<=n[p]; i++) {
        d=order[p, i]
        if ((tma[p, d]+0)!=0) return 0
        if ((rkb[p, d]+0)!=0) return 0
        if ((wkb[p, d]+0)!=0) return 0
      }
      return 1
    }
    BEGIN { pass=0 }
    NF==0 { next }
    is_io_hdr() {
      if ($0 ~ /^[ \t]*Disks:/ || pass==0) pass++
      io_header()
      next
    }
    pass>0 && $1 ~ /^[A-Za-z][A-Za-z0-9_]*$/ {
      dev=$1
      if (dev=="Name" || dev=="tty:" || dev=="cpu" || dev=="avg-cpu:" || dev=="System" || dev=="History" || dev=="Tin") next
      if (dev ~ /^(Disks|Kbps|tps)$/) next
      need=tm_c
      if (read_c>need) need=read_c
      if (write_c>need) need=write_c
      if (need>0 && NF<need) next
      key=pass SUBSEP dev
      if (!(key in seenp)) {
        seenp[key]=1
        n[pass]++
        order[pass, n[pass]]=dev
      }
      if (tm_c>0) tma[pass, dev]=$(tm_c)+0
      if (read_c>0) rkb[pass, dev]=$(read_c)+0
      if (write_c>0) wkb[pass, dev]=$(write_c)+0
    }
    END {
      ival=0
      for (p=1; p<=pass; p++) if (n[p]>0) ival=p
      use_tm=ival
      cum=0
      if (aixrel==7100 && ival>0 && report_idle(ival)) {
        for (p=ival-1; p>=1; p--) {
          if (n[p]>0 && !report_idle(p)) { use_tm=p; cum=1; break }
        }
      }
      printf "["
      src=ival
      if (cum && use_tm>0) src=use_tm
      if (src>0) {
        for (i=1; i<=n[src]; i++) {
          d=order[src, i]
          if (i>1) printf ","
          tm=tma[use_tm, d]+0
          if (cum) {
            printf "{\"device\":\"%s\",\"read_bytes\":%.0f,\"write_bytes\":%.0f,\"tm_act\":%.2f,\"read_bytes_interval\":%.0f,\"write_bytes_interval\":%.0f}", d, rkb[use_tm, d]*1024, wkb[use_tm, d]*1024, tm, rkb[ival, d]*1024, wkb[ival, d]*1024
          } else {
            printf "{\"device\":\"%s\",\"read_bytes\":%.0f,\"write_bytes\":%.0f,\"tm_act\":%.2f}", d, rkb[ival, d]*1024, wkb[ival, d]*1024, tm
          }
        }
      }
      printf "]"
    }
  '
)
[ -z "${DISKIO_JSON}" ] && DISKIO_JSON='[]'

# --- network: netstat -v + ifconfig -a via stdin segments; never awk -v the blob ---
NET_JSON=$(
  {
    printf '%s\n' '---NSV---'
    _run netstat -v
    printf '%s\n' '---IFC---'
    _run ifconfig -a
  } | awk '
    function note(ifn) {
      if (ifn=="" || ifn=="lo" || ifn=="lo0") return
      if (!(ifn in seen)) { seen[ifn]=1; order[++n]=ifn }
    }
    function take_num(re,    s) {
      if (!match($0, re)) return 0
      s=substr($0, RSTART, RLENGTH)
      gsub(/[^0-9]/, "", s)
      return s+0
    }
    BEGIN { mode=""; iface=""; n=0 }
    $0=="---NSV---" { mode="nsv"; iface=""; next }
    $0=="---IFC---" { mode="ifc"; iface=""; next }
    mode=="nsv" {
      if (tolower($0) ~ /statistics/ && match($0, /\(([A-Za-z]+[0-9]+)\)/)) {
        iface=substr($0, RSTART+1, RLENGTH-2)
        note(iface)
        next
      }
      if (iface=="") next
      if (match($0, /Bytes received:[ \t]*[0-9]+/)) {
        rxb[iface]=take_num("Bytes received:[ \t]*[0-9]+")
        note(iface)
      }
      if (match($0, /Bytes transmitted:[ \t]*[0-9]+/)) {
        txb[iface]=take_num("Bytes transmitted:[ \t]*[0-9]+")
        note(iface)
      }
      if (match($0, /Receive Errors:[ \t]*[0-9]+/)) {
        rxerr[iface]=take_num("Receive Errors:[ \t]*[0-9]+")
        note(iface)
      }
      if (match($0, /Transmit Errors:[ \t]*[0-9]+/)) {
        txerr[iface]=take_num("Transmit Errors:[ \t]*[0-9]+")
        note(iface)
      }
      if ($1=="Bytes:" && NF>=4) {
        txb[iface]=$2+0
        if ($3=="Bytes:") rxb[iface]=$4+0
        else if ($3 ~ /^[0-9]/) rxb[iface]=$3+0
        note(iface)
      }
      next
    }
    mode=="ifc" {
      if (match($0, /^[A-Za-z][A-Za-z0-9]*:/)) {
        iface=substr($0, 1, index($0, ":")-1)
        note(iface)
        next
      }
      if (iface!="" && match($0, /bytes:[ \t]*[0-9]+/) && !(iface in rxb)) {
        rxb[iface]=take_num("bytes:[ \t]*[0-9]+")
        note(iface)
      }
      next
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

# --- process states: /usr/sysv/bin/ps column s only; skip if missing ---
PROC_JSON='{}'
if [ -x /usr/sysv/bin/ps ]; then
  PS_OUT=$(/usr/sysv/bin/ps -e -o s= 2>/dev/null)
  if [ -n "${PS_OUT}" ]; then
    PROC_JSON=$(
      printf '%s\n' "${PS_OUT}" | awk '
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
  fi
fi

OSLEVEL=$(_json_str "${OSLEVEL_RAW}")

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
