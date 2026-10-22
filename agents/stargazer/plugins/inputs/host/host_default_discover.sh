#!/bin/sh
# System Info Collector - POSIX sh, CentOS/RHEL 6+ compatible
# Rollback: host_default_discover.sh.bak
#
# EL6 兼容：
# - /etc/os-release 可能不存在，回退 /etc/centos-release|/etc/redhat-release|/etc/system-release
# - ss 无 -H，-p 输出是 users:(("name",pid,fd))；再回退 netstat
# - ip 可能缺失，回退 ifconfig
# - df --exclude-type 失败时回退 df -kP
# - 过滤内核线程（arg 形如 [kthreadd]）

classify_host_machine_type() {
    virt_type=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')
    vendor=$(printf '%s' "$2" | tr '[:upper:]' '[:lower:]')
    product=$(printf '%s' "$3" | tr '[:upper:]' '[:lower:]')
    cpuinfo=$(printf '%s' "$4" | tr '[:upper:]' '[:lower:]')
    identity="$vendor $product"

    case "$virt_type" in
        ""|none|unknown) ;;
        *)
            printf 'virtual'
            return 0
            ;;
    esac

    case " $cpuinfo " in
        *" hypervisor "*)
            printf 'virtual'
            return 0
            ;;
    esac

    if printf '%s' "$identity" | grep -qE 'vmware|virtualbox|qemu|kvm|xen|parallels|bochs|bhyve|hyper-v|virtual machine|openstack|amazon ec2|google compute engine|alibaba cloud|tencent cloud|huawei cloud|nutanix|ahv|innotek|ovirt'; then
        printf 'virtual'
        return 0
    fi

    if [ "$virt_type" = "none" ]; then
        printf 'physical_server'
        return 0
    fi

    trimmed=$(printf '%s' "$identity" | tr -d '[:space:]')
    if [ -n "$trimmed" ]; then
        printf 'physical_server'
        return 0
    fi

    printf 'unknown'
}

json_from_df() {
    awk '
        function esc(s) {
            gsub(/\\/, "\\\\", s)
            gsub(/"/, "\\\"", s)
            return s
        }
        function skip_fs(device, fstype, mount) {
            if (device == "tmpfs" || device == "devtmpfs" || device == "overlay" || device == "squashfs") return 1
            if (fstype == "tmpfs" || fstype == "devtmpfs" || fstype == "overlay" || fstype == "squashfs") return 1
            if (fstype == "proc" || fstype == "sysfs" || fstype == "devpts" || fstype == "cgroup" || fstype == "cgroup2") return 1
            if (mount == "" || mount ~ /^\/(proc|sys|dev|run)(\/|$)/) return 1
            return 0
        }
        NR == 1 { next }
        $0 !~ /%/ { pending = pending $0; next }
        {
            if (pending != "") {
                $0 = pending " " $0
                pending = ""
            }
            if ($2 ~ /^[0-9]+$/) {
                device = $1
                fstype = ""
                blocks = $2
                mount = $NF
            } else {
                device = $1
                fstype = $2
                blocks = $3
                mount = $NF
            }
            if (skip_fs(device, fstype, mount)) next
            if ((blocks + 0) <= 0) next
            size = sprintf("%.1f", (blocks + 0) / 1024 / 1024)
            if (!first) printf ","
            first = 0
            printf "{\"device\":\"%s\",\"mount\":\"%s\",\"fstype\":\"%s\",\"size_gb\":\"%s\"}", esc(device), esc(mount), esc(fstype), size
        }
        BEGIN { first = 1; printf "[" }
        END { printf "]" }
    '
}

json_from_nic_rows() {
    awk '
        function esc(s) {
            gsub(/\\/, "\\\\", s)
            gsub(/"/, "\\\"", s)
            return s
        }
        function skip_iface(iface,    name) {
            name = iface
            sub(/@.*$/, "", name)
            if (name == "" || name == "lo") return 1
            if (name ~ /^(veth|docker|br-|virbr|cali|flannel|cni|dummy|ifb|kube-|nodelocaldns|vnet|qbr|qvb|qvo|fwbr|fwln|fwpr|cilium|lxc)/) return 1
            return 0
        }
        $1 == "LINK" {
            iface = $2
            mac = $3
            if (skip_iface(iface)) next
            macs[iface] = mac
            if (!(iface in seen)) {
                seen[iface] = 1
                order[++count] = iface
            }
        }
        $1 == "ADDR" {
            iface = $2
            ip = $3
            sub(/\/.*/, "", ip)
            if (skip_iface(iface) || ip == "") next
            if (ips[iface] == "") ips[iface] = ip
            else ips[iface] = ips[iface] "," ip
            if (!(iface in seen)) {
                seen[iface] = 1
                order[++count] = iface
            }
        }
        END {
            printf "["
            for (i = 1; i <= count; i++) {
                iface = order[i]
                if (i > 1) printf ","
                printf "{\"name\":\"%s\",\"mac\":\"%s\",\"ip\":\"%s\"}", esc(iface), esc(macs[iface]), esc(ips[iface])
            }
            printf "]"
        }
    '
}

# 三次 ps 快照，块之间用单独一行 --- 分隔。出现不少于 2 次的 pid 视为稳定进程。
stable_pids() {
    awk '
        $0 == "---" {
            sample++
            next
        }
        {
            pid = $1
            if (pid == "" || pid + 0 != pid) {
                next
            }
            key = sample SUBSEP pid
            if (!(key in seen)) {
                seen[key] = 1
                count[pid]++
            }
        }
        END {
            for (pid in count) {
                if (count[pid] >= 2) {
                    print pid
                }
            }
        }
    '
}

# 完整域名优先，否则短主机名。两条都取不到时留空，主机名称不是必填。
collected_hostname() {
    name="$(hostname -f 2>/dev/null || true)"
    [ -n "$name" ] || name="$(hostname 2>/dev/null || true)"
    printf '%s' "$name"
}

if [ "${HOST_DISCOVER_SOURCE_ONLY:-}" = "1" ]; then
    return 0 2>/dev/null || exit 0
fi

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

parse_legacy_release() {
    what="$1"
    file="$2"
    [ -r "$file" ] || return 0
    awk -v what="$what" '
        {
            for (i = 1; i <= NF; i++) {
                if ($i == "release") {
                    name = $1
                    for (j = 2; j < i; j++) {
                        name = name " " $j
                    }
                    ver = $(i + 1)
                    gsub(/[^0-9.].*/, "", ver)
                    if (what == "name") {
                        print name
                    } else {
                        print ver
                    }
                    exit
                }
            }
        }
    ' "$file"
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
mingetty
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
release workque
host_default_discover.sh
host_default_discover_el6.sh
EOF
)

collect_proc_ports() {
    ss_output="$(safe ss -lntpH)"
    [ -n "$ss_output" ] || ss_output="$(safe ss -lntp)"
    [ -n "$ss_output" ] || ss_output="$(safe ss -lnt -p)"
    [ -n "$ss_output" ] || ss_output="$(safe netstat -lntp)"
    [ -n "$ss_output" ] || ss_output="$(safe netstat -tlnp)"
    [ -n "$ss_output" ] || return 0

    printf '%s\n' "$ss_output" | awk '
        function add_pid_port(pid, port,    key) {
            if (pid == "" || port == "" || port == "*") {
                return
            }
            key = pid SUBSEP port
            if (key in seen) {
                return
            }
            seen[key] = 1
            if (ports[pid] != "") {
                ports[pid] = ports[pid] "," port
            } else {
                ports[pid] = port
            }
        }
        /^(Netid|State|Recv-Q|Proto|Active)/ { next }
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

            rest = proc_info
            found = 0
            while (match(rest, /pid=[0-9]+/)) {
                add_pid_port(substr(rest, RSTART + 4, RLENGTH - 4), port)
                found = 1
                rest = substr(rest, RSTART + RLENGTH)
            }

            if (!found) {
                rest = proc_info
                while (match(rest, /users:\(\("[^"]+",[0-9]+/)) {
                    m = substr(rest, RSTART, RLENGTH)
                    sub(/.*,/, "", m)
                    add_pid_port(m, port)
                    found = 1
                    rest = substr(rest, RSTART + RLENGTH)
                }
            }

            if (!found && match(proc_info, /^[0-9]+\//)) {
                add_pid_port(substr(proc_info, 1, RLENGTH - 1), port)
            }
        }
        END {
            for (pid in ports) {
                printf "%s\t%s\n", pid, ports[pid]
            }
        }
    '
}

collect_ps_snapshot() {
    dest="$1"
    safe ps -e -o pid= -o comm= -o args= > "$dest"
    if [ ! -s "$dest" ]; then
        safe ps -eo pid,comm,args > "$dest"
    fi
}

collect_proc_list() {
    ports_file="$(make_temp_file host_proc_ports)"
    ps_file="$(make_temp_file host_proc_ps)"
    snap1="$(make_temp_file host_proc_snap1)"
    snap2="$(make_temp_file host_proc_snap2)"
    snap3="$(make_temp_file host_proc_snap3)"
    stable_file="$(make_temp_file host_proc_stable)"

    collect_proc_ports > "$ports_file"
    collect_ps_snapshot "$snap1"
    sleep 3
    collect_ps_snapshot "$snap2"
    sleep 3
    collect_ps_snapshot "$snap3"

    nonempty=0
    [ -s "$snap1" ] && nonempty=$((nonempty + 1))
    [ -s "$snap2" ] && nonempty=$((nonempty + 1))
    [ -s "$snap3" ] && nonempty=$((nonempty + 1))
    if [ "$nonempty" -ge 2 ]; then
        {
            cat "$snap1"
            echo "---"
            cat "$snap2"
            echo "---"
            cat "$snap3"
        } | stable_pids > "$stable_file"
        cp "$snap3" "$ps_file"
        [ -s "$ps_file" ] || cp "$snap2" "$ps_file"
        [ -s "$ps_file" ] || cp "$snap1" "$ps_file"
    else
        cp "$snap1" "$ps_file"
        [ -s "$ps_file" ] || cp "$snap2" "$ps_file"
        [ -s "$ps_file" ] || cp "$snap3" "$ps_file"
        awk '{ if ($1+0 == $1) print $1 }' "$ps_file" > "$stable_file"
    fi

    proc_json="$(awk -v excludes="$PROC_EXCLUDE_FINGERPRINTS" -v ports_file="$ports_file" -v stable_file="$stable_file" '
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
            while ((getline line < stable_file) > 0) {
                if (line != "") {
                    stable[line] = 1
                }
            }
            close(stable_file)
            first = 1
            printf "["
        }
        {
            pid = $1
            name = $2
            $1 = ""
            $2 = ""
            sub(/^[ \t]+/, "", $0)
            arg = $0

            if (pid == "" || arg == "") {
                next
            }
            if (pid + 0 != pid) {
                next
            }
            if (!(pid in stable)) {
                next
            }
            # Linux 内核线程：ps 显示为 [kthreadd]
            if (arg ~ /^\[[^\]]+\]$/) {
                next
            }
            if (name == "ps" && index(arg, "pid=") > 0) {
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

    rm -f "$ports_file" "$ps_file" "$snap1" "$snap2" "$snap3" "$stable_file"
    printf '%s' "${proc_json:-[]}"
}

# -----------------------------
# Hostname
# -----------------------------
hostname_val="$(collected_hostname)"

# -----------------------------
# OS
# -----------------------------
os_type="$(safe uname -s)"
os_name=""
os_version=""

if [ -r /etc/os-release ]; then
    os_name="$(awk -F= '/^NAME=/{gsub(/"/,"",$2);print $2;exit}' /etc/os-release)"
    os_version="$(awk -F= '/^VERSION_ID=/{gsub(/"/,"",$2);print $2;exit}' /etc/os-release)"
fi

if [ -z "$os_name" ] || [ -z "$os_version" ]; then
    for release_file in /etc/centos-release /etc/redhat-release /etc/system-release; do
        if [ -r "$release_file" ]; then
            [ -n "$os_name" ] || os_name="$(parse_legacy_release name "$release_file")"
            [ -n "$os_version" ] || os_version="$(parse_legacy_release version "$release_file")"
            break
        fi
    done
fi

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
    safe lscpu | awk -F: '/Model name/{gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2; exit}'
)"

if [ -z "$cpu_model" ] && [ -r /proc/cpuinfo ]; then
    cpu_model="$(awk -F: '/model name/{gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2; exit}' /proc/cpuinfo)"
fi

cpu_cores="$(
    safe lscpu | awk -F: '/^CPU\(s\)/{gsub(/^[ \t]+|[ \t]+$/, "", $2); print $2; exit}'
)"

if [ -z "$cpu_cores" ] && [ -r /proc/cpuinfo ]; then
    cpu_cores="$(awk '/^processor/{c++} END{print c+0}' /proc/cpuinfo)"
fi

# -----------------------------
# Memory (GB, no bc)
# -----------------------------
memory_gb="$(
    safe free -m | awk '/Mem:/{printf "%.1f", $2/1024}'
)"

if [ -z "$memory_gb" ] && [ -r /proc/meminfo ]; then
    memory_gb="$(awk '/MemTotal/{printf "%.1f", $2/1024/1024}' /proc/meminfo)"
fi

[ -n "$memory_gb" ] || memory_gb="0.0"

# -----------------------------
# Disk (GB)
# -----------------------------
df_out="$(safe df -k --exclude-type=tmpfs --exclude-type=devtmpfs --exclude-type=overlay)"
[ -n "$df_out" ] || df_out="$(safe df -k -x tmpfs -x devtmpfs)"
[ -n "$df_out" ] || df_out="$(safe df -kP)"

disk_gb="$(
    printf '%s\n' "$df_out" | awk '
        NR==1 { next }
        $1 == "tmpfs" || $1 == "devtmpfs" { next }
        { sum += $2 }
        END { printf "%.1f", sum/1024/1024 }
    '
)"

[ -n "$disk_gb" ] || disk_gb="0.0"

# -----------------------------
# MAC Address
# -----------------------------
mac_address="$(
    safe ip link show | awk '/ether/{print $2;exit}'
)"

[ -n "$mac_address" ] || mac_address="$(
    safe ifconfig -a | awk '/HWaddr/{print $NF; exit}'
)"

[ -n "$mac_address" ] || mac_address="unknown"

# -----------------------------
# Machine type: virtual / physical_server / unknown
# -----------------------------
virt_type=""
if command -v systemd-detect-virt >/dev/null 2>&1; then
    virt_type="$(systemd-detect-virt 2>/dev/null || true)"
fi

sys_vendor=""
product_name=""
if [ -r /sys/class/dmi/id/sys_vendor ]; then
    sys_vendor="$(cat /sys/class/dmi/id/sys_vendor 2>/dev/null || true)"
fi
if [ -r /sys/class/dmi/id/product_name ]; then
    product_name="$(cat /sys/class/dmi/id/product_name 2>/dev/null || true)"
fi

cpu_flags=""
if [ -r /proc/cpuinfo ]; then
    cpu_flags="$(awk -F: '/^flags/{gsub(/^[ \t]+/, "", $2); print $2; exit}' /proc/cpuinfo 2>/dev/null || true)"
fi

machine_type="$(classify_host_machine_type "$virt_type" "$sys_vendor" "$product_name" "$cpu_flags")"
[ -n "$machine_type" ] || machine_type="unknown"

# -----------------------------
# Mounts and NICs
# -----------------------------
df_out="$(safe df -kP -T)"
[ -n "$df_out" ] || df_out="$(safe df -kP)"
mount_json="$(printf '%s\n' "$df_out" | json_from_df)"
[ -n "$mount_json" ] || mount_json="[]"

nic_rows=""
if command -v ip >/dev/null 2>&1; then
    nic_rows="$(
        safe ip -o link show | awk '
            {
                iface = $2
                gsub(/:$/, "", iface)
                mac = ""
                for (i = 1; i <= NF; i++) if ($i == "link/ether") mac = $(i + 1)
                if (iface != "") printf "LINK %s %s\n", iface, mac
            }
        '
        safe ip -o addr show | awk '
            $3 == "inet" {
                iface = $2
                gsub(/:$/, "", iface)
                printf "ADDR %s %s\n", iface, $4
            }
        '
    )"
else
    nic_rows="$(
        safe ifconfig -a | awk '
            /^[A-Za-z0-9]/ {
                iface = $1
                gsub(/:$/, "", iface)
            }
            /HWaddr/ { printf "LINK %s %s\n", iface, $NF }
            /ether/ { printf "LINK %s %s\n", iface, $2 }
            /inet addr:/ {
                split($2, parts, ":")
                printf "ADDR %s %s\n", iface, parts[2]
            }
            $1 == "inet" && $2 ~ /^[0-9]/ { printf "ADDR %s %s\n", iface, $2 }
        '
    )"
fi
nic_json="$(printf '%s\n' "$nic_rows" | json_from_nic_rows)"
[ -n "$nic_json" ] || nic_json="[]"

# -----------------------------
# Process
# -----------------------------
proc_json="$(collect_proc_list)"
[ -n "$proc_json" ] || proc_json="[]"

# -----------------------------
# Final JSON (ONLY OUTPUT)
# -----------------------------
cat >&3 <<EOF
{
  "hostname": "$(json_escape "$hostname_val")",
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
  "machine_type": "$(json_escape "$machine_type")",
  "mounts": $mount_json,
  "nics": $nic_json,
  "proc": $proc_json
}
EOF
