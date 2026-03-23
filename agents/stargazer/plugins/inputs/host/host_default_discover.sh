#!/bin/sh
# System Info Collector - POSIX sh Safe Version

set -e

# 保留原始 stdout，最终 JSON 统一写回
exec 3>&1

safe() {
    "$@" 2>/dev/null || true
}

value_or_unknown() {
    v="$1"
    [ -n "$v" ] && printf '%s' "$v" || printf 'unknown'
}

json_escape() {
    printf '%s' "${1:-}" | awk '
        BEGIN { ORS="" }
        {
            gsub(/\\/, "\\\\")
            gsub(/"/, "\\\"")
            gsub(/\r/, "\\r")
            gsub(/\t/, "\\t")
            if (NR > 1) {
                printf "\\n"
            }
            printf "%s", $0
        }
    '
}

make_temp_file() {
    prefix="$1"
    tmp_file="$(mktemp 2>/dev/null || true)"
    if [ -n "$tmp_file" ]; then
        printf '%s' "$tmp_file"
        return 0
    fi

    tmp_file="/tmp/${prefix}.$$"
    : > "$tmp_file"
    printf '%s' "$tmp_file"
}

# -----------------------------
# 进程排除指纹（name + arg）
# -----------------------------
PROC_EXCLUDE_FINGERPRINTS=$(cat <<'EOF'
systemd
dhclient
deferwq
sshd
crond
rsyslogd
auditd
polkitd
dockerd
containerd
tuned
iscsid
rpcbind
chronyd
agetty
kthreadd
kworker/
ksoftirqd/
migration/
rcu_
watchdog/
dbus-daemon
systemd-udevd
systemd-journald
systemd-logind
cpuhp/
idle_inject/
kaluad
kpsmoused
kdevtmpfs
khungtaskd
kswapd
ksmd
khugepaged
kcompactd
kintegrityd
kblockd
kauditd
kmpath
kcryptd
kstrp
kthrotld
ipv6_addrconf
ata_sff
bioset
md
rpciod
xprtiod
edac-poller
devfreq_wq
netns
oom_reaper
writeback
scsi_eh_
scsi_tmf_
irq/
napi/
xfs-
NetworkManager
udisksd
wpa_supplicant
accounts-daemon
host_default_discover.sh
EOF
)

collect_proc_ports() {
    ss_output="$(safe ss -lntpH)"
    [ -n "$ss_output" ] || ss_output="$(safe ss -lntp)"
    [ -n "$ss_output" ] || return 0

    printf '%s\n' "$ss_output" | awk '
        /^(Netid|State)/ { next }
        {
            local_addr = $4
            proc_info = $NF
            if (local_addr == "" || proc_info == "") {
                next
            }

            port = local_addr
            sub(/^.*:/, "", port)
            if (port == "" || port == "*") {
                next
            }

            while (match(proc_info, /pid=[0-9]+/)) {
                pid = substr(proc_info, RSTART + 4, RLENGTH - 4)
                if (pid != "") {
                    key = pid SUBSEP port
                    if (!(key in seen)) {
                        seen[key] = 1
                        if (ports[pid] != "") {
                            ports[pid] = ports[pid] "," port
                        } else {
                            ports[pid] = port
                        }
                    }
                }
                proc_info = substr(proc_info, RSTART + RLENGTH)
            }
        }
        END {
            for (pid in ports) {
                printf "%s\t%s\n", pid, ports[pid]
            }
        }
    '
}

collect_proc_list() {
    ports_file="$(make_temp_file host_proc_ports)"
    ps_file="$(make_temp_file host_proc_ps)"

    collect_proc_ports > "$ports_file"
    safe ps -e -o pid= -o comm= -o args= > "$ps_file"

    proc_json="$(awk -v excludes="$PROC_EXCLUDE_FINGERPRINTS" -v ports_file="$ports_file" '
        function esc(s) {
            gsub(/\\/, "\\\\", s)
            gsub(/"/, "\\\"", s)
            gsub(/\r/, "\\r", s)
            gsub(/\n/, "\\n", s)
            gsub(/\t/, "\\t", s)
            return s
        }
        BEGIN {
            pattern_count = split(excludes, patterns, /\n/)
            while ((getline line < ports_file) > 0) {
                split(line, port_kv, /\t/)
                if (port_kv[1] != "") {
                    ports[port_kv[1]] = port_kv[2]
                }
            }
            close(ports_file)
            first = 1
            printf "["
        }
        {
            pid = $1
            name = $2
            $1 = ""
            $2 = ""
            sub(/^[[:space:]]+/, "", $0)
            arg = $0

            if (pid == "" || arg == "") {
                next
            }

            fingerprint = name " " arg
            for (i = 1; i <= pattern_count; i++) {
                if (patterns[i] != "" && index(fingerprint, patterns[i]) > 0) {
                    next
                }
            }

            cmd = "readlink -f /proc/" pid "/exe 2>/dev/null"
            exe = ""
            cmd | getline exe
            close(cmd)

            cmd = "readlink -f /proc/" pid "/cwd 2>/dev/null"
            cwd = ""
            cmd | getline cwd
            close(cmd)

            if (!first) {
                printf ","
            }
            first = 0

            printf "{\"pid\":\"%s\",\"name\":\"%s\",\"arg\":\"%s\",\"exe\":\"%s\",\"cwd\":\"%s\",\"ports\":\"%s\"}", \
                esc(pid), esc(name), esc(arg), esc(exe), esc(cwd), esc(ports[pid])
        }
        END {
            printf "]"
        }
    ' "$ps_file")"

    rm -f "$ports_file" "$ps_file"
    printf '%s' "$proc_json"
}

# -----------------------------
# Hostname
# -----------------------------
hostname_val="$(safe hostname -f)"
[ -n "$hostname_val" ] || hostname_val="$(safe hostname)"

# -----------------------------
# OS
# -----------------------------
os_type="$(safe uname -s)"

os_name="$(
    awk -F= '/^NAME=/{gsub(/"/,"",$2);print $2;exit}' /etc/os-release 2>/dev/null
)"

os_version="$(
    awk -F= '/^VERSION_ID=/{gsub(/"/,"",$2);print $2;exit}' /etc/os-release 2>/dev/null
)"

# -----------------------------
# Arch / Bits
# -----------------------------
cpu_arch="$(safe uname -m)"

case "$cpu_arch" in
    x86_64|aarch64) os_bits="64-bit" ;;
    i386|i686) os_bits="32-bit" ;;
    *) os_bits="unknown" ;;
esac

# -----------------------------
# CPU
# -----------------------------
cpu_model="$(
    safe lscpu | awk -F: '/Model name/{print $2;exit}' | xargs
)"

[ -n "$cpu_model" ] || cpu_model="$(
    awk -F: '/model name/{print $2;exit}' /proc/cpuinfo 2>/dev/null | xargs
)"

cpu_cores="$(
    safe lscpu | awk -F: '/^CPU\(s\)/{print $2;exit}' | xargs
)"

[ -n "$cpu_cores" ] || cpu_cores="$(
    awk '/^processor/{c++} END{print c+0}' /proc/cpuinfo 2>/dev/null
)"

# -----------------------------
# Memory (GB, no bc)
# -----------------------------
memory_gb="$(
    safe free -m | awk '/Mem:/{printf "%.1f", $2/1024}'
)"

[ -n "$memory_gb" ] || memory_gb="$(
    awk '/MemTotal/{printf "%.1f", $2/1024/1024}' /proc/meminfo 2>/dev/null
)"

[ -n "$memory_gb" ] || memory_gb="0.0"

# -----------------------------
# Disk (GB)
# -----------------------------
disk_gb="$(
    safe df -k --exclude-type=tmpfs --exclude-type=devtmpfs --exclude-type=overlay | \
    awk 'NR>1{sum+=$2} END{printf "%.1f", sum/1024/1024}'
)"

[ -n "$disk_gb" ] || disk_gb="0.0"

# -----------------------------
# MAC Address
# -----------------------------
mac_address="$(
    safe ip link show | awk '/ether/{print $2;exit}'
)"

[ -n "$mac_address" ] || mac_address="unknown"

# -----------------------------
# Process
# -----------------------------
proc_json="$(collect_proc_list)"

# -----------------------------
# Final JSON (ONLY OUTPUT)
# -----------------------------
cat >&3 <<EOF
{
  "hostname": "$(json_escape "$(value_or_unknown "$hostname_val")")",
  "os_type": "$(json_escape "$(value_or_unknown "$os_type")")",
  "os_name": "$(json_escape "$(value_or_unknown "$os_name")")",
  "os_version": "$(json_escape "$(value_or_unknown "$os_version")")",
  "os_bits": "$(json_escape "$os_bits")",
  "cpu_architecture": "$(json_escape "$(value_or_unknown "$cpu_arch")")",
  "cpu_model": "$(json_escape "$(value_or_unknown "$cpu_model")")",
  "cpu_cores": "$(json_escape "$(value_or_unknown "$cpu_cores")")",
  "memory_gb": "$memory_gb",
  "disk_gb": "$disk_gb",
  "mac_address": "$(json_escape "$mac_address")",
  "proc": $proc_json
}
EOF
