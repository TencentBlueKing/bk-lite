export const WINDOWS_HOST_SCRIPT = `# Windows 主机采集示例。stdout 只能是这一个 JSON 数组。
# os_type：Windows=2。cpu_arch：x64 / arm64 / x86。
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Get-Gb([long]$bytes) {
    if ($bytes -le 0) { return "0" }
    return [string]([int][math]::Round($bytes / 1GB))
}

$cs = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
$cpu = @(Get-CimInstance Win32_Processor)
$diskBytes = @(Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" |
    Measure-Object -Property Size -Sum).Sum
$nic = Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "IPEnabled=TRUE" |
    Where-Object { $_.MACAddress -and $_.IPAddress } |
    Select-Object -First 1

$arch = "x64"
switch -Regex ([string]$env:PROCESSOR_ARCHITECTURE) {
    "ARM64" { $arch = "arm64"; break }
    "86" { $arch = "x86"; break }
}

$model = [string]$cs.Model
$machineType = "physical_server"
if ($cs.HypervisorPresent -or $model -match "Virtual|VMware|KVM|Hyper-V|Xen|QEMU") {
    $machineType = "virtual"
}

$bits = "64"
if ([string]$os.OSArchitecture -match "32") { $bits = "32" }

$ip = "{{bk_host_innerip}}"
if (-not $ip -or $ip -like "*bk_host_innerip*") {
    $picked = @($nic.IPAddress | Where-Object { $_ -match '^\\d+\\.\\d+\\.\\d+\\.\\d+$' } | Select-Object -First 1)
    $ip = if ($picked) { [string]$picked[0] } else { "" }
}

$cpuCores = ($cpu | Measure-Object NumberOfLogicalProcessors -Sum).Sum
if (-not $cpuCores) { $cpuCores = 0 }

$row = [ordered]@{
    inst_name    = [string]$cs.Name
    ip_addr      = [string]$ip
    hostname     = [string]$cs.Name
    os_type      = "2"
    os_name      = ([string]$os.Caption).Trim()
    os_version   = [string]$os.Version
    os_bit       = $bits
    cpu_model    = [string]($cpu | Select-Object -First 1).Name
    cpu_core     = [string]$cpuCores
    cpu_arch     = $arch
    memory       = Get-Gb ([int64]$cs.TotalPhysicalMemory)
    disk         = Get-Gb ([int64]$diskBytes)
    inner_mac    = ([string]$nic.MACAddress).Replace("-", ":").ToUpper()
    machine_type = $machineType
}

Write-Output ("[" + ($row | ConvertTo-Json -Compress) + "]")
`;

export const LINUX_HOST_SCRIPT = `#!/bin/bash
# Linux 主机采集示例。stdout 只能是这一个 JSON 数组。
# os_type：Linux=1。cpu_arch：x64 / arm64 / x86。
set -euo pipefail

ip="{{bk_host_innerip}}"
name="$(hostname -s 2>/dev/null || hostname)"
. /etc/os-release 2>/dev/null || true
os_name="\${PRETTY_NAME:-}"
os_version="\${VERSION_ID:-}"

case "$(uname -m)" in
  aarch64|arm64) cpu_arch="arm64" ;;
  i386|i686) cpu_arch="x86" ;;
  *) cpu_arch="x64" ;;
esac

bits="$(getconf LONG_BIT 2>/dev/null || echo 64)"
cpu_model="$(awk -F: '/model name/{gsub(/^ /, "", $2); print $2; exit}' /proc/cpuinfo)"
cpu_core="$(nproc 2>/dev/null || echo 0)"
memory="$(awk '/MemTotal/{printf "%d", ($2 + 1048575) / 1048576}' /proc/meminfo)"
disk_bytes="$(df -B1 --output=size / 2>/dev/null | awk 'NR==2{print $1}')"
disk="0"
if [ -n "\${disk_bytes:-}" ]; then
  disk="$(( (disk_bytes + 1073741823) / 1073741824 ))"
fi
mac="$(ip -o link show 2>/dev/null | awk '!/LOOPBACK/ && /ether/{print toupper($17); exit}' | tr '-' ':')"
machine_type="physical_server"
if grep -Eqi 'hypervisor|vmware|kvm|qemu|xen' /proc/cpuinfo /sys/class/dmi/id/product_name 2>/dev/null; then
  machine_type="virtual"
fi

python3 - "$name" "$ip" "$os_name" "$os_version" "$bits" "$cpu_model" "$cpu_core" "$cpu_arch" "$memory" "$disk" "$mac" "$machine_type" <<'PY'
import json, sys
name, ip, os_name, os_version, bits, cpu_model, cpu_core, cpu_arch, memory, disk, mac, machine_type = sys.argv[1:]
print(json.dumps([{
    "inst_name": name,
    "ip_addr": ip,
    "hostname": name,
    "os_type": "1",
    "os_name": os_name,
    "os_version": os_version,
    "os_bit": bits,
    "cpu_model": cpu_model,
    "cpu_core": cpu_core,
    "cpu_arch": cpu_arch,
    "memory": memory,
    "disk": disk,
    "inner_mac": mac,
    "machine_type": machine_type,
}], ensure_ascii=False, separators=(",", ":")))
PY
`;
