#!/bin/bash
# System Info Collector - Final Safe Version

set -e

# -----------------------------
# 只允许最终 JSON 输出到 stdout
# -----------------------------
exec 3>&1
exec 1>/dev/null 2>&1

safe() {
    "$@" 2>/dev/null || true
}

value_or_unknown() {
    local v="$1"
    [ -n "$v" ] && printf '%s' "$v" || printf 'unknown'
}

# -----------------------------
# Hostname
# -----------------------------
hostname_val="$(safe hostname -f)"
[ -z "$hostname_val" ] && hostname_val="$(safe hostname)"

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
    i386|i686)     os_bits="32-bit" ;;
    *)             os_bits="unknown" ;;
esac

# -----------------------------
# CPU
# -----------------------------
cpu_model="$(
    safe lscpu | awk -F: '/Model name/{print $2;exit}' | xargs
)"

[ -z "$cpu_model" ] && cpu_model="$(
    awk -F: '/model name/{print $2;exit}' /proc/cpuinfo 2>/dev/null | xargs
)"

cpu_cores="$(
    safe lscpu | awk -F: '/^CPU\(s\)/{print $2;exit}' | xargs
)"

[ -z "$cpu_cores" ] && cpu_cores="$(
    awk '/^processor/{c++} END{print c+0}' /proc/cpuinfo 2>/dev/null
)"

# -----------------------------
# Memory (GB, no bc)
# -----------------------------
memory_gb="$(
    safe free -m | awk '/Mem:/{printf "%.1f", $2/1024}'
)"

[ -z "$memory_gb" ] && memory_gb="$(
    awk '/MemTotal/{printf "%.1f", $2/1024/1024}' /proc/meminfo 2>/dev/null
)"

[ -z "$memory_gb" ] && memory_gb="0.0"

# -----------------------------
# Disk (GB)
# -----------------------------
disk_gb="$(
    safe df -k --exclude-type=tmpfs --exclude-type=devtmpfs --exclude-type=overlay \
    | awk 'NR>1{sum+=$2} END{printf "%.1f", sum/1024/1024}'
)"

[ -z "$disk_gb" ] && disk_gb="0.0"

# -----------------------------
# MAC Address
# -----------------------------
mac_address="$(
    safe ip link show | awk '/ether/{print $2;exit}'
)"

[ -z "$mac_address" ] && mac_address="unknown"

# -----------------------------
# Final JSON (ONLY OUTPUT)
# -----------------------------
cat >&3 <<EOF
{
  "hostname": "$(value_or_unknown "$hostname_val")",
  "os_type": "$(value_or_unknown "$os_type")",
  "os_name": "$(value_or_unknown "$os_name")",
  "os_version": "$(value_or_unknown "$os_version")",
  "os_bits": "$os_bits",
  "cpu_architecture": "$(value_or_unknown "$cpu_arch")",
  "cpu_model": "$(value_or_unknown "$cpu_model")",
  "cpu_cores": "$(value_or_unknown "$cpu_cores")",
  "memory_gb": "$memory_gb",
  "disk_gb": "$disk_gb",
  "mac_address": "$mac_address"
}
EOF
