"""内置主机健康巡检脚本（Windows PowerShell / Linux bash+python）。

约束：
- 禁止出现 Conductor 表达式字面量 ``${...}``（发布时虽会转义，脚本源码仍保持干净便于契约测试）。
- 输出统一为 ``BK_LITE_RESULT=`` + JSON，字段含 ``host`` 画像与可打分 ``metrics``。
"""

from __future__ import annotations

# 注意：勿在脚本正文使用 `${var}`。Conductor 会把 `${...}` 解析成工作流引用。
WINDOWS_HEALTH_SCRIPT = r"""
$ErrorActionPreference = "SilentlyContinue"
$collectedAt = (Get-Date).ToUniversalTime().ToString("o")

function Get-HealthStatus([double]$value, [double]$warning, [double]$critical) {
  if ($value -ge $critical) { return "CRITICAL" }
  if ($value -ge $warning) { return "WARNING" }
  return "NORMAL"
}

function New-Metric {
  param(
    [string]$Category,
    [string]$ObjectType,
    [string]$ObjectName,
    [string]$Dimensions,
    [string]$MetricName,
    [string]$DisplayName,
    [double]$Value,
    [string]$Unit,
    [double]$WarningThreshold,
    [double]$CriticalThreshold,
    [string]$HealthStatus,
    [string]$Detail
  )
  return @{
    category = $Category
    object_type = $ObjectType
    object_name = $ObjectName
    dimensions = $Dimensions
    metric_name = $MetricName
    display_name = $DisplayName
    value = $Value
    unit = $Unit
    warning_threshold = $WarningThreshold
    critical_threshold = $CriticalThreshold
    health_status = $HealthStatus
    collected_at = $collectedAt
    detail = $Detail
  }
}

$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$cpuInfo = @(Get-CimInstance Win32_Processor)
$cpuCores = ($cpuInfo | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
if (-not $cpuCores) { $cpuCores = 1 }
$uptimeHours = [math]::Round(((Get-Date) - $os.LastBootUpTime).TotalHours, 2)
$memTotalGb = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
$hostProfile = @{
  hostname = $env:COMPUTERNAME
  os_version = ($os.Caption + " " + $os.Version).Trim()
  architecture = $cs.SystemType
  uptime_hours = $uptimeHours
  cpu_cores = [int]$cpuCores
  memory_total_gb = $memTotalGb
  top_cpu = ""
  top_memory = ""
}

$metrics = @()

# --- 计算 ---
$cpu = [math]::Round(($cpuInfo | Measure-Object -Property LoadPercentage -Average).Average, 2)
$metrics += New-Metric -Category "计算" -ObjectType "processor" -ObjectName "CPU Total" -Dimensions "core=all" `
  -MetricName "usage_percent" -DisplayName "CPU 使用率" -Value $cpu -Unit "%" `
  -WarningThreshold 80 -CriticalThreshold 90 -HealthStatus (Get-HealthStatus $cpu 80 90) -Detail "处理器平均负载百分比"

# --- 内存 ---
$memory = [math]::Round((1 - ($os.FreePhysicalMemory / $os.TotalVisibleMemorySize)) * 100, 2)
$availableMb = [math]::Round($os.FreePhysicalMemory / 1024, 2)
$metrics += New-Metric -Category "内存" -ObjectType "physical_memory" -ObjectName "Memory Total" -Dimensions "scope=system" `
  -MetricName "usage_percent" -DisplayName "物理内存使用率" -Value $memory -Unit "%" `
  -WarningThreshold 80 -CriticalThreshold 90 -HealthStatus (Get-HealthStatus $memory 80 90) `
  -Detail ("total_gb=" + $memTotalGb + ",available_mb=" + $availableMb)
$metrics += New-Metric -Category "内存" -ObjectType "physical_memory" -ObjectName "Memory Available" -Dimensions "scope=system" `
  -MetricName "available_mb" -DisplayName "可用物理内存" -Value $availableMb -Unit "MB" `
  -WarningThreshold 0 -CriticalThreshold 0 -HealthStatus "NORMAL" -Detail "可用物理内存（仅展示）"

$page = Get-CimInstance Win32_PageFileUsage | Select-Object -First 1
if ($page -and $page.AllocatedBaseSize -gt 0) {
  $pageUsage = [math]::Round(($page.CurrentUsage / $page.AllocatedBaseSize) * 100, 2)
  $metrics += New-Metric -Category "内存" -ObjectType "page_file" -ObjectName "PageFile" -Dimensions "scope=system" `
    -MetricName "usage_percent" -DisplayName "页面文件使用率" -Value $pageUsage -Unit "%" `
    -WarningThreshold 80 -CriticalThreshold 90 -HealthStatus (Get-HealthStatus $pageUsage 80 90) `
    -Detail ("allocated_mb=" + $page.AllocatedBaseSize + ",used_mb=" + $page.CurrentUsage)
} else {
  $metrics += New-Metric -Category "内存" -ObjectType "page_file" -ObjectName "PageFile" -Dimensions "scope=system" `
    -MetricName "usage_percent" -DisplayName "页面文件使用率" -Value 0 -Unit "%" `
    -WarningThreshold 80 -CriticalThreshold 90 -HealthStatus "NORMAL" -Detail "未配置页面文件"
}

# --- 磁盘 ---
Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | ForEach-Object {
  $usage = if ($_.Size -gt 0) { [math]::Round((($_.Size - $_.FreeSpace) / $_.Size) * 100, 2) } else { 0 }
  $totalGb = [math]::Round($_.Size / 1GB, 2)
  $usedGb = [math]::Round(($_.Size - $_.FreeSpace) / 1GB, 2)
  $metrics += New-Metric -Category "磁盘" -ObjectType "logical_disk" -ObjectName $_.DeviceID -Dimensions ("mount=" + $_.DeviceID) `
    -MetricName "usage_percent" -DisplayName "磁盘使用率" -Value $usage -Unit "%" `
    -WarningThreshold 80 -CriticalThreshold 90 -HealthStatus (Get-HealthStatus $usage 80 90) `
    -Detail ("total_gb=" + $totalGb + ",used_gb=" + $usedGb)
}

# --- 网络 ---
Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "IPEnabled=TRUE" | ForEach-Object {
  $name = if ($_.Description) { $_.Description } else { "nic-" + $_.Index }
  $ip = @($_.IPAddress | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' } | Select-Object -First 1)
  if (-not $ip) { $ip = "n/a" }
  $linkUp = 1
  $linkDetail = "ip=" + $ip + ",status=up"
  $adapter = Get-CimInstance Win32_NetworkAdapter -Filter ("Index=" + $_.Index) | Select-Object -First 1
  if ($adapter -and $adapter.NetEnabled -eq $false) {
    $linkUp = 0
    $linkDetail = "ip=" + $ip + ",status=down"
  }
  $statusLabel = if ($linkUp -eq 1) { "NORMAL" } else { "WARNING" }
  $metrics += New-Metric -Category "网络" -ObjectType "network_adapter" -ObjectName $name -Dimensions ("adapter=" + $name) `
    -MetricName "link_up" -DisplayName "网卡链路" -Value ([double]$linkUp) -Unit "bool" `
    -WarningThreshold 1 -CriticalThreshold 1 -HealthStatus $statusLabel -Detail $linkDetail
}
$perfNics = @(Get-CimInstance Win32_PerfFormattedData_Tcpip_NetworkInterface)
foreach ($nic in $perfNics) {
  if (-not $nic.Name -or $nic.Name -match "Loopback|isatap|Teredo") { continue }
  $mbps = [math]::Round(($nic.BytesTotalPersec * 8) / 1MB, 2)
  $metrics += New-Metric -Category "网络" -ObjectType "network_adapter" -ObjectName $nic.Name -Dimensions ("adapter=" + $nic.Name) `
    -MetricName "throughput_mbps" -DisplayName "网卡吞吐" -Value $mbps -Unit "Mbps" `
    -WarningThreshold 800 -CriticalThreshold 950 -HealthStatus (Get-HealthStatus $mbps 800 950) -Detail "瞬时总吞吐"
}

# --- 系统健康 ---
$writable = 0
try {
  $probe = Join-Path $env:TEMP ("bklite-health-" + [guid]::NewGuid().ToString("N") + ".tmp")
  Set-Content -Path $probe -Value "ok" -ErrorAction Stop
  Remove-Item -Path $probe -Force -ErrorAction SilentlyContinue
  $writable = 1
} catch {
  $writable = 0
}
$metrics += New-Metric -Category "系统健康" -ObjectType "filesystem" -ObjectName "TEMP" -Dimensions "path=%TEMP%" `
  -MetricName "writable" -DisplayName "临时目录可写" -Value ([double]$writable) -Unit "bool" `
  -WarningThreshold 1 -CriticalThreshold 1 -HealthStatus ($(if ($writable -eq 1) { "NORMAL" } else { "CRITICAL" })) `
  -Detail $(if ($writable -eq 1) { "临时目录可写" } else { "临时目录不可写" })

$w32time = Get-Service -Name W32Time -ErrorAction SilentlyContinue
$timeOk = if ($w32time -and $w32time.Status -eq "Running") { 1 } else { 0 }
$metrics += New-Metric -Category "系统健康" -ObjectType "service" -ObjectName "W32Time" -Dimensions "service=W32Time" `
  -MetricName "running" -DisplayName "Windows 时间服务" -Value ([double]$timeOk) -Unit "bool" `
  -WarningThreshold 1 -CriticalThreshold 1 -HealthStatus ($(if ($timeOk -eq 1) { "NORMAL" } else { "WARNING" })) `
  -Detail $(if ($timeOk -eq 1) { "时间服务运行中" } else { "时间服务未运行" })

# --- 进程热点（不打分）---
$cpuTop = @(Get-Process | Sort-Object -Property CPU -Descending | Select-Object -First 3)
$memTop = @(Get-Process | Sort-Object -Property WorkingSet64 -Descending | Select-Object -First 3)
$hostProfile.top_cpu = (($cpuTop | ForEach-Object { $_.ProcessName + "=" + [math]::Round($_.CPU, 1) + "s" }) -join "; ")
$hostProfile.top_memory = (($memTop | ForEach-Object { $_.ProcessName + "=" + [math]::Round($_.WorkingSet64 / 1MB, 1) + "MB" }) -join "; ")
$rank = 1
foreach ($proc in $cpuTop) {
  $metrics += New-Metric -Category "进程热点" -ObjectType "process" -ObjectName $proc.ProcessName -Dimensions ("rank=" + $rank) `
    -MetricName "cpu_time_seconds" -DisplayName ("CPU Top" + $rank) -Value ([math]::Round($proc.CPU, 2)) -Unit "s" `
    -WarningThreshold 0 -CriticalThreshold 0 -HealthStatus "NORMAL" -Detail ("pid=" + $proc.Id)
  $rank++
}
$rank = 1
foreach ($proc in $memTop) {
  $metrics += New-Metric -Category "进程热点" -ObjectType "process" -ObjectName $proc.ProcessName -Dimensions ("rank=" + $rank) `
    -MetricName "working_set_mb" -DisplayName ("内存 Top" + $rank) -Value ([math]::Round($proc.WorkingSet64 / 1MB, 2)) -Unit "MB" `
    -WarningThreshold 0 -CriticalThreshold 0 -HealthStatus "NORMAL" -Detail ("pid=" + $proc.Id)
  $rank++
}

# --- 基础服务 ---
$winrm = Get-Service -Name WinRM -ErrorAction SilentlyContinue
$winrmOk = if ($winrm -and $winrm.Status -eq "Running") { 1 } else { 0 }
$metrics += New-Metric -Category "基础服务" -ObjectType "service" -ObjectName "WinRM" -Dimensions "service=WinRM" `
  -MetricName "running" -DisplayName "WinRM 服务" -Value ([double]$winrmOk) -Unit "bool" `
  -WarningThreshold 1 -CriticalThreshold 1 -HealthStatus ($(if ($winrmOk -eq 1) { "NORMAL" } else { "WARNING" })) `
  -Detail $(if ($winrmOk -eq 1) { "WinRM 运行中" } else { "WinRM 未运行" })

# --- 安全浅检 ---
$fw = Get-Service -Name mpssvc -ErrorAction SilentlyContinue
$fwOk = if ($fw -and $fw.Status -eq "Running") { 1 } else { 0 }
$metrics += New-Metric -Category "安全浅检" -ObjectType "service" -ObjectName "Windows Firewall" -Dimensions "service=mpssvc" `
  -MetricName "running" -DisplayName "防火墙服务" -Value ([double]$fwOk) -Unit "bool" `
  -WarningThreshold 1 -CriticalThreshold 1 -HealthStatus ($(if ($fwOk -eq 1) { "NORMAL" } else { "WARNING" })) `
  -Detail $(if ($fwOk -eq 1) { "防火墙服务运行中" } else { "防火墙服务未运行" })

# --- 更新账龄 ---
$hotfixes = @(Get-HotFix | Sort-Object -Property InstalledOn -Descending)
$updateDays = -1
$updateDetail = "无法读取更新记录"
$updateStatus = "NORMAL"
if ($hotfixes.Count -gt 0 -and $hotfixes[0].InstalledOn) {
  $updateDays = [math]::Round(((Get-Date) - [datetime]$hotfixes[0].InstalledOn).TotalDays, 0)
  $updateDetail = "last_hotfix=" + $hotfixes[0].HotFixID + ",days=" + $updateDays
  $updateStatus = Get-HealthStatus $updateDays 90 180
}
$metrics += New-Metric -Category "更新账龄" -ObjectType "patch" -ObjectName "Windows Update" -Dimensions "scope=system" `
  -MetricName "days_since_update" -DisplayName "距上次补丁天数" -Value ([double]([math]::Max($updateDays, 0))) -Unit "days" `
  -WarningThreshold 90 -CriticalThreshold 180 -HealthStatus $updateStatus -Detail $updateDetail

$critical = @($metrics | Where-Object { $_.health_status -eq "CRITICAL" })
$warning = @($metrics | Where-Object { $_.health_status -eq "WARNING" })
$normal = @($metrics | Where-Object { $_.health_status -eq "NORMAL" })

$result = @{
  collected_at = $collectedAt
  host = $hostProfile
  metrics = $metrics
  metric_count = $metrics.Count
  critical = $critical
  warning = $warning
  normal = $normal
  critical_count = $critical.Count
  warning_count = $warning.Count
  normal_count = $normal.Count
  conclusion = $(if (($critical.Count + $warning.Count) -gt 0) { "需关注" } else { "健康" })
}
Write-Output ("BK_LITE_RESULT=" + ($result | ConvertTo-Json -Depth 8 -Compress))
""".strip()


LINUX_HEALTH_SCRIPT = r"""
#!/bin/bash
set -euo pipefail
# 采集逻辑集中在 python3，避免 bash 花括号变量写法触发 Conductor 表达式。
python3 - <<'PY'
import json
import os
import shutil
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def health(value, warning, critical):
    value = float(value)
    if value >= critical:
        return "CRITICAL"
    if value >= warning:
        return "WARNING"
    return "NORMAL"


def metric(
    category, object_type, object_name, dimensions, metric_name, display_name,
    value, unit, warning_threshold, critical_threshold, health_status, detail,
):
    return {
        "category": category,
        "object_type": object_type,
        "object_name": object_name,
        "dimensions": dimensions,
        "metric_name": metric_name,
        "display_name": display_name,
        "value": float(value),
        "unit": unit,
        "warning_threshold": warning_threshold,
        "critical_threshold": critical_threshold,
        "health_status": health_status,
        "collected_at": collected_at,
        "detail": detail,
    }


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def cpu_usage_percent(sample_seconds=1.0):
    def snapshot():
        for line in read_text("/proc/stat").splitlines():
            if line.startswith("cpu "):
                parts = [float(x) for x in line.split()[1:]]
                idle = parts[3] + (parts[4] if len(parts) > 4 else 0.0)
                total = sum(parts)
                return idle, total
        return 0.0, 1.0

    idle1, total1 = snapshot()
    time.sleep(sample_seconds)
    idle2, total2 = snapshot()
    didle = idle2 - idle1
    dtotal = total2 - total1
    if dtotal <= 0:
        return 0.0
    return round(max(0.0, min(100.0, (1.0 - didle / dtotal) * 100.0)), 2)


cores = os.cpu_count() or 1
load1 = load5 = load15 = 0.0
try:
    load1, load5, load15 = os.getloadavg()
except OSError:
    pass
load_ratio = round((load1 / cores) * 100.0, 2) if cores else 0.0

meminfo = {}
for line in read_text("/proc/meminfo").splitlines():
    parts = line.split()
    if len(parts) >= 2 and parts[0].endswith(":"):
        meminfo[parts[0][:-1]] = float(parts[1])
mem_total = meminfo.get("MemTotal", 0.0)
mem_avail = meminfo.get("MemAvailable", meminfo.get("MemFree", 0.0))
memory = round((1.0 - mem_avail / mem_total) * 100.0, 2) if mem_total else 0.0
mem_total_gb = round(mem_total / 1024.0 / 1024.0, 2)
available_mb = round(mem_avail / 1024.0, 2)
swap_total = meminfo.get("SwapTotal", 0.0)
swap_free = meminfo.get("SwapFree", 0.0)
swap_usage = round((1.0 - swap_free / swap_total) * 100.0, 2) if swap_total > 0 else 0.0

uptime_hours = 0.0
uptime_raw = read_text("/proc/uptime").split()
if uptime_raw:
    uptime_hours = round(float(uptime_raw[0]) / 3600.0, 2)

os_version = ""
for line in read_text("/etc/os-release").splitlines():
    if line.startswith("PRETTY_NAME="):
        os_version = line.split("=", 1)[1].strip().strip('"')
        break
if not os_version:
    os_version = read_text("/proc/version").split("\n")[0][:120]

arch = os.uname().machine if hasattr(os, "uname") else ""
hostname = socket.gethostname()

host = {
    "hostname": hostname,
    "os_version": os_version,
    "architecture": arch,
    "uptime_hours": uptime_hours,
    "cpu_cores": int(cores),
    "memory_total_gb": mem_total_gb,
    "top_cpu": "",
    "top_memory": "",
}

metrics = []
cpu = cpu_usage_percent()
metrics.append(metric(
    "计算", "processor", "CPU Total", "core=all", "usage_percent", "CPU 使用率",
    cpu, "%", 80, 90, health(cpu, 80, 90), "1 秒采样使用率",
))
metrics.append(metric(
    "计算", "processor", "Load Average", "window=1m", "load_ratio_percent", "1 分钟负载/核",
    load_ratio, "%", 80, 90, health(load_ratio, 80, 90), "load1=%.2f,cores=%s" % (load1, cores),
))
metrics.append(metric(
    "内存", "physical_memory", "Memory Total", "scope=system", "usage_percent", "物理内存使用率",
    memory, "%", 80, 90, health(memory, 80, 90),
    "total_gb=%.2f,available_mb=%.2f" % (mem_total_gb, available_mb),
))
metrics.append(metric(
    "内存", "physical_memory", "Memory Available", "scope=system", "available_mb", "可用物理内存",
    available_mb, "MB", 0, 0, "NORMAL", "可用物理内存（仅展示）",
))
if swap_total > 0:
    metrics.append(metric(
        "内存", "swap", "Swap", "scope=system", "usage_percent", "Swap 使用率",
        swap_usage, "%", 80, 90, health(swap_usage, 80, 90),
        "total_mb=%.0f" % (swap_total / 1024.0),
    ))
else:
    metrics.append(metric(
        "内存", "swap", "Swap", "scope=system", "usage_percent", "Swap 使用率",
        0, "%", 80, 90, "NORMAL", "未配置 Swap",
    ))

# 磁盘：本地块设备挂载（跳过临时伪文件系统）
skip_fs = {"tmpfs", "devtmpfs", "overlay", "squashfs", "proc", "sysfs", "cgroup", "cgroup2", "devpts", "securityfs", "pstore", "efivarfs", "bpf"}
seen_mounts = set()
for line in read_text("/proc/mounts").splitlines():
    parts = line.split()
    if len(parts) < 3:
        continue
    device, mount, fstype = parts[0], parts[1], parts[2]
    if fstype in skip_fs or not device.startswith("/"):
        continue
    if mount in seen_mounts:
        continue
    seen_mounts.add(mount)
    usage = shutil.disk_usage(mount)
    pct = round((usage.used / usage.total) * 100.0, 2) if usage.total else 0.0
    metrics.append(metric(
        "磁盘", "logical_disk", mount, "mount=%s" % mount, "usage_percent", "磁盘使用率",
        pct, "%", 80, 90, health(pct, 80, 90),
        "total_gb=%.2f,used_gb=%.2f" % (usage.total / 1e9, usage.used / 1e9),
    ))
    # inode
    try:
        st = os.statvfs(mount)
        inodes_total = st.f_files
        inodes_free = st.f_ffree
        if inodes_total > 0:
            inode_pct = round((1.0 - inodes_free / inodes_total) * 100.0, 2)
            metrics.append(metric(
                "磁盘", "logical_disk", mount, "mount=%s,metric=inode" % mount, "inode_usage_percent", "inode 使用率",
                inode_pct, "%", 80, 90, health(inode_pct, 80, 90),
                "inodes_total=%s" % inodes_total,
            ))
    except OSError:
        pass
if not any(item["category"] == "磁盘" for item in metrics):
    try:
        usage = shutil.disk_usage("/")
        pct = round((usage.used / usage.total) * 100.0, 2) if usage.total else 0.0
        metrics.append(metric(
            "磁盘", "logical_disk", "/", "mount=/", "usage_percent", "磁盘使用率",
            pct, "%", 80, 90, health(pct, 80, 90),
            "total_gb=%.2f,used_gb=%.2f" % (usage.total / 1e9, usage.used / 1e9),
        ))
    except OSError:
        pass

# 根只读
root_ro = 0
for line in read_text("/proc/mounts").splitlines():
    parts = line.split()
    if len(parts) >= 4 and parts[1] == "/":
        opts = parts[3].split(",")
        root_ro = 1 if "ro" in opts else 0
        break
metrics.append(metric(
    "系统健康", "filesystem", "/", "mount=/", "read_only", "根分区只读",
    float(root_ro), "bool", 1, 1, "WARNING" if root_ro else "NORMAL",
    "根分区为只读挂载" if root_ro else "根分区可写",
))

# 临时目录可写
writable = 0
try:
    probe = Path("/tmp") / ("bklite-health-%s.tmp" % os.getpid())
    probe.write_text("ok", encoding="utf-8")
    probe.unlink(missing_ok=True)
    writable = 1
except OSError:
    writable = 0
metrics.append(metric(
    "系统健康", "filesystem", "/tmp", "path=/tmp", "writable", "临时目录可写",
    float(writable), "bool", 1, 1, "NORMAL" if writable else "CRITICAL",
    "临时目录可写" if writable else "临时目录不可写",
))

# 时间同步
time_ok = 0
time_detail = "未检测到 chronyd/ntpd/systemd-timesyncd"
for unit in ("chronyd", "chrony", "ntpd", "systemd-timesyncd"):
    try:
        proc = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0 and proc.stdout.strip() == "active":
            time_ok = 1
            time_detail = "%s active" % unit
            break
    except (OSError, subprocess.SubprocessError):
        continue
metrics.append(metric(
    "系统健康", "service", "time_sync", "scope=system", "running", "时间同步服务",
    float(time_ok), "bool", 1, 1, "NORMAL" if time_ok else "WARNING", time_detail,
))

# 网络：非 lo 的 IPv4 地址
try:
    proc = subprocess.run(["ip", "-o", "-4", "addr", "show", "up"], capture_output=True, text=True, timeout=5)
    for line in proc.stdout.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        ifname = parts[1]
        if ifname == "lo":
            continue
        ip = parts[3].split("/")[0]
        metrics.append(metric(
            "网络", "network_adapter", ifname, "adapter=%s" % ifname, "link_up", "网卡链路",
            1.0, "bool", 1, 1, "NORMAL", "ip=%s,status=up" % ip,
        ))
except (OSError, subprocess.SubprocessError):
    pass

# 进程热点
top_cpu = []
top_mem = []
try:
    proc = subprocess.run(["ps", "-eo", "pid,comm,%cpu,%mem", "--sort=-%cpu"], capture_output=True, text=True, timeout=5)
    rows = [ln.split(None, 3) for ln in proc.stdout.splitlines()[1:4] if ln.strip()]
    for idx, row in enumerate(rows, start=1):
        if len(row) < 4:
            continue
        pid, comm, cpu_p, mem_p = row[0], row[1], float(row[2]), float(row[3])
        top_cpu.append("%s=%.1f%%" % (comm, cpu_p))
        metrics.append(metric("进程热点", "process", comm, "rank=%s" % idx, "cpu_percent", "CPU Top%s" % idx, cpu_p, "%", 0, 0, "NORMAL", "pid=%s" % pid))
    proc = subprocess.run(["ps", "-eo", "pid,comm,%cpu,%mem", "--sort=-%mem"], capture_output=True, text=True, timeout=5)
    rows = [ln.split(None, 3) for ln in proc.stdout.splitlines()[1:4] if ln.strip()]
    for idx, row in enumerate(rows, start=1):
        if len(row) < 4:
            continue
        pid, comm, cpu_p, mem_p = row[0], row[1], float(row[2]), float(row[3])
        top_mem.append("%s=%.1f%%" % (comm, mem_p))
        metrics.append(metric("进程热点", "process", comm, "rank=%s" % idx, "mem_percent", "内存 Top%s" % idx, mem_p, "%", 0, 0, "NORMAL", "pid=%s" % pid))
except (OSError, subprocess.SubprocessError, ValueError):
    pass
host["top_cpu"] = "; ".join(top_cpu)
host["top_memory"] = "; ".join(top_mem)

# sshd
sshd_ok = 0
sshd_detail = "sshd 未运行"
for unit in ("sshd", "ssh"):
    try:
        proc = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0 and proc.stdout.strip() == "active":
            sshd_ok = 1
            sshd_detail = "%s active" % unit
            break
    except (OSError, subprocess.SubprocessError):
        continue
metrics.append(metric(
    "基础服务", "service", "sshd", "service=sshd", "running", "SSH 服务",
    float(sshd_ok), "bool", 1, 1, "NORMAL" if sshd_ok else "WARNING", sshd_detail,
))

# 防火墙
fw_ok = 0
fw_detail = "未检测到活跃防火墙服务"
for unit in ("firewalld", "ufw", "nftables", "iptables"):
    try:
        proc = subprocess.run(["systemctl", "is-active", unit], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0 and proc.stdout.strip() == "active":
            fw_ok = 1
            fw_detail = "%s active" % unit
            break
    except (OSError, subprocess.SubprocessError):
        continue
metrics.append(metric(
    "安全浅检", "service", "firewall", "scope=system", "running", "防火墙服务",
    float(fw_ok), "bool", 1, 1, "NORMAL" if fw_ok else "WARNING", fw_detail,
))

# 更新账龄：尽量读 dpkg/yum 记录，失败则 NORMAL + 说明
update_days = 0.0
update_status = "NORMAL"
update_detail = "无法读取更新记录"
stamp_candidates = [
    "/var/log/dpkg.log",
    "/var/log/yum.log",
    "/var/log/dnf.log",
    "/var/lib/apt/periodic/update-success-stamp",
]
newest = None
for path in stamp_candidates:
    try:
        mtime = Path(path).stat().st_mtime
        if newest is None or mtime > newest:
            newest = mtime
    except OSError:
        continue
if newest is not None:
    update_days = round((time.time() - newest) / 86400.0, 0)
    update_status = health(update_days, 90, 180)
    update_detail = "days_since_package_log=%.0f" % update_days
metrics.append(metric(
    "更新账龄", "patch", "Package Updates", "scope=system", "days_since_update", "距上次更新天数",
    update_days, "days", 90, 180, update_status, update_detail,
))

critical = [m for m in metrics if m["health_status"] == "CRITICAL"]
warning = [m for m in metrics if m["health_status"] == "WARNING"]
normal = [m for m in metrics if m["health_status"] == "NORMAL"]
result = {
    "collected_at": collected_at,
    "host": host,
    "metrics": metrics,
    "metric_count": len(metrics),
    "critical": critical,
    "warning": warning,
    "normal": normal,
    "critical_count": len(critical),
    "warning_count": len(warning),
    "normal_count": len(normal),
    "conclusion": "需关注" if (critical or warning) else "健康",
}
print("BK_LITE_RESULT=" + json.dumps(result, ensure_ascii=False, separators=(",", ":")))
PY
""".strip()
