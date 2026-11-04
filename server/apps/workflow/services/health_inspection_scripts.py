"""内置主机健康巡检脚本（Windows PowerShell / Linux Shell）。

约束：
- 禁止出现 Conductor 表达式字面量 ``${...}``（发布时虽会转义，脚本源码仍保持干净便于契约测试）。
- 输出统一为行首 ``result=`` + JSON，字段含 ``host`` 画像与可打分 ``metrics``。
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
Write-Output ("result=" + ($result | ConvertTo-Json -Depth 8 -Compress))
""".strip()


LINUX_HEALTH_SCRIPT = r"""
#!/usr/bin/env bash
# Linux 主机巡检（Excel）内置脚本：输出 result=JSON；禁止 Conductor 表达式字面量。
set -eu

collected_at="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)"

json_escape() {
  # shellcheck disable=SC2001
  printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e 's/	/\\t/g' \
    | awk 'BEGIN{ORS=""} {gsub(/\r/,""); printf "%s", $0} END{}' \
    | tr '\n' ' ' | sed 's/[[:space:]]*$//'
}

health_of() {
  # args: value warning critical
  awk -v v="$1" -v w="$2" -v c="$3" 'BEGIN{
    if (v+0 >= c+0) { print "CRITICAL"; exit }
    if (v+0 >= w+0) { print "WARNING"; exit }
    print "NORMAL"
  }'
}

round2() {
  awk -v v="$1" 'BEGIN{ printf "%.2f", v+0 }'
}

METRICS_FILE="$(mktemp)"
trap 'rm -f "$METRICS_FILE"' EXIT

append_metric() {
  # category object_type object_name dimensions metric_name display_name value unit warn crit status detail
  # 不用两位位置参数编号；也不写 Conductor 表达式字面量。
  local category="$1" object_type="$2" object_name="$3" dimensions="$4"
  local metric_name="$5" display_name="$6" value="$7" unit="$8" warn="$9"
  shift 9
  local crit="$1" status="$2" detail="$3"
  local sep=""
  if [ -s "$METRICS_FILE" ]; then
    sep=","
  fi
  printf '%s{"category":"%s","object_type":"%s","object_name":"%s","dimensions":"%s",'\
'"metric_name":"%s","display_name":"%s","value":%s,"unit":"%s",'\
'"warning_threshold":%s,"critical_threshold":%s,"health_status":"%s",'\
'"collected_at":"%s","detail":"%s"}' \
    "$sep" \
    "$(json_escape "$category")" \
    "$(json_escape "$object_type")" \
    "$(json_escape "$object_name")" \
    "$(json_escape "$dimensions")" \
    "$(json_escape "$metric_name")" \
    "$(json_escape "$display_name")" \
    "$(round2 "$value")" \
    "$(json_escape "$unit")" \
    "$warn" \
    "$crit" \
    "$(json_escape "$status")" \
    "$(json_escape "$collected_at")" \
    "$(json_escape "$detail")" \
    >>"$METRICS_FILE"
}

read_text() {
  if [ -r "$1" ]; then
    cat "$1" 2>/dev/null || true
  fi
}

# --- host basics ---
cores="$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 1)"
[ -n "$cores" ] || cores=1
load1=0; load5=0; load15=0
if [ -r /proc/loadavg ]; then
  # shellcheck disable=SC2034
  read -r load1 load5 load15 _ </proc/loadavg || true
fi
load_ratio="$(awk -v l="$load1" -v c="$cores" 'BEGIN{ if (c+0<=0){print "0.00"; exit} printf "%.2f", (l/c)*100 }')"

mem_total=0; mem_avail=0; swap_total=0; swap_free=0
while IFS= read -r line; do
  case "$line" in
    MemTotal:*) mem_total=$(echo "$line" | awk '{print $2}') ;;
    MemAvailable:*) mem_avail=$(echo "$line" | awk '{print $2}') ;;
    MemFree:*)
      if [ -z "$mem_avail" ] || [ "$mem_avail" = "0" ]; then
        mem_avail=$(echo "$line" | awk '{print $2}')
      fi
      ;;
    SwapTotal:*) swap_total=$(echo "$line" | awk '{print $2}') ;;
    SwapFree:*) swap_free=$(echo "$line" | awk '{print $2}') ;;
  esac
done <<EOF
$(read_text /proc/meminfo)
EOF

memory="$(awk -v a="$mem_avail" -v t="$mem_total" 'BEGIN{ if (t+0<=0){print "0.00"; exit} printf "%.2f", (1-a/t)*100 }')"
mem_total_gb="$(awk -v t="$mem_total" 'BEGIN{ printf "%.2f", t/1024/1024 }')"
available_mb="$(awk -v a="$mem_avail" 'BEGIN{ printf "%.2f", a/1024 }')"
if awk -v t="$swap_total" 'BEGIN{ exit !(t+0>0) }'; then
  swap_usage="$(awk -v f="$swap_free" -v t="$swap_total" 'BEGIN{ printf "%.2f", (1-f/t)*100 }')"
else
  swap_usage="0.00"
fi

uptime_hours="0.00"
if [ -r /proc/uptime ]; then
  uptime_hours="$(awk '{ printf "%.2f", $1/3600 }' /proc/uptime)"
fi

os_version=""
while IFS= read -r line; do
  case "$line" in
    PRETTY_NAME=*)
      os_version="$(printf '%s\n' "$line" | sed -e 's/^PRETTY_NAME=//' -e 's/^\"//' -e 's/\"$//')"
      ;;
  esac
done <<EOF
$(read_text /etc/os-release)
EOF
if [ -z "$os_version" ]; then
  os_version="$(read_text /proc/version | head -n1 | cut -c1-120)"
fi

arch="$(uname -m 2>/dev/null || true)"
hostname="$(hostname 2>/dev/null || uname -n 2>/dev/null || echo unknown)"

# CPU sample ~1s from /proc/stat
cpu_snapshot() {
  awk '/^cpu /{
    idle=$5+($6+0); total=0;
    for(i=2;i<=NF;i++) total+=$i;
    print idle, total; exit
  }' /proc/stat 2>/dev/null || echo "0 1"
}
read -r idle1 total1 <<EOF
$(cpu_snapshot)
EOF
sleep 1
read -r idle2 total2 <<EOF
$(cpu_snapshot)
EOF
cpu="$(awk -v i1="$idle1" -v t1="$total1" -v i2="$idle2" -v t2="$total2" 'BEGIN{
  di=i2-i1; dt=t2-t1;
  if (dt<=0){ print "0.00"; exit }
  u=(1-di/dt)*100; if(u<0)u=0; if(u>100)u=100;
  printf "%.2f", u
}')"

append_metric "计算" "processor" "CPU Total" "core=all" "usage_percent" "CPU 使用率" \
  "$cpu" "%" 80 90 "$(health_of "$cpu" 80 90)" "1 秒采样使用率"
append_metric "计算" "processor" "Load Average" "window=1m" "load_ratio_percent" "1 分钟负载/核" \
  "$load_ratio" "%" 80 90 "$(health_of "$load_ratio" 80 90)" "load1=$(round2 "$load1"),cores=$cores"
append_metric "内存" "physical_memory" "Memory Total" "scope=system" "usage_percent" "物理内存使用率" \
  "$memory" "%" 80 90 "$(health_of "$memory" 80 90)" "total_gb=$mem_total_gb,available_mb=$available_mb"
append_metric "内存" "physical_memory" "Memory Available" "scope=system" "available_mb" "可用物理内存" \
  "$available_mb" "MB" 0 0 "NORMAL" "可用物理内存（仅展示）"
if awk -v t="$swap_total" 'BEGIN{ exit !(t+0>0) }'; then
  swap_total_mb="$(awk -v t="$swap_total" 'BEGIN{ printf "%.0f", t/1024 }')"
  append_metric "内存" "swap" "Swap" "scope=system" "usage_percent" "Swap 使用率" \
    "$swap_usage" "%" 80 90 "$(health_of "$swap_usage" 80 90)" "total_mb=$swap_total_mb"
else
  append_metric "内存" "swap" "Swap" "scope=system" "usage_percent" "Swap 使用率" \
    0 "%" 80 90 "NORMAL" "未配置 Swap"
fi

# disks from /proc/mounts + df
has_disk=0
skip_fs='tmpfs|devtmpfs|overlay|squashfs|proc|sysfs|cgroup|cgroup2|devpts|securityfs|pstore|efivarfs|bpf'
seen_mounts=""
while IFS= read -r line; do
  # device mount fstype
  device=$(echo "$line" | awk '{print $1}')
  mount=$(echo "$line" | awk '{print $2}')
  fstype=$(echo "$line" | awk '{print $3}')
  case "$fstype" in
    tmpfs|devtmpfs|overlay|squashfs|proc|sysfs|cgroup|cgroup2|devpts|securityfs|pstore|efivarfs|bpf) continue ;;
  esac
  case "$device" in
    /*) ;;
    *) continue ;;
  esac
  case " $seen_mounts " in
    *" $mount "*) continue ;;
  esac
  seen_mounts="$seen_mounts $mount"
  # df -P for portable numbers
  df_line="$(df -P "$mount" 2>/dev/null | awk 'NR==2{print}')"
  [ -n "$df_line" ] || continue
  total_kb=$(echo "$df_line" | awk '{print $2}')
  used_kb=$(echo "$df_line" | awk '{print $3}')
  pct="$(awk -v u="$used_kb" -v t="$total_kb" 'BEGIN{ if(t+0<=0){print "0.00"; exit} printf "%.2f", (u/t)*100 }')"
  total_gb="$(awk -v t="$total_kb" 'BEGIN{ printf "%.2f", t*1024/1e9 }')"
  used_gb="$(awk -v u="$used_kb" 'BEGIN{ printf "%.2f", u*1024/1e9 }')"
  append_metric "磁盘" "logical_disk" "$mount" "mount=$mount" "usage_percent" "磁盘使用率" \
    "$pct" "%" 80 90 "$(health_of "$pct" 80 90)" "total_gb=$total_gb,used_gb=$used_gb"
  has_disk=1
  # inode via df -i if available
  if df_i_line="$(df -iP "$mount" 2>/dev/null | awk 'NR==2{print}')"; then
    inodes_total=$(echo "$df_i_line" | awk '{print $2}')
    inodes_used=$(echo "$df_i_line" | awk '{print $3}')
    if awk -v t="$inodes_total" 'BEGIN{ exit !(t+0>0) }'; then
      inode_pct="$(awk -v u="$inodes_used" -v t="$inodes_total" 'BEGIN{ printf "%.2f", (u/t)*100 }')"
      append_metric "磁盘" "logical_disk" "$mount" "mount=$mount,metric=inode" "inode_usage_percent" "inode 使用率" \
        "$inode_pct" "%" 80 90 "$(health_of "$inode_pct" 80 90)" "inodes_total=$inodes_total"
    fi
  fi
done <<EOF
$(read_text /proc/mounts)
EOF

if [ "$has_disk" -eq 0 ]; then
  df_line="$(df -P / 2>/dev/null | awk 'NR==2{print}')"
  if [ -n "$df_line" ]; then
    total_kb=$(echo "$df_line" | awk '{print $2}')
    used_kb=$(echo "$df_line" | awk '{print $3}')
    pct="$(awk -v u="$used_kb" -v t="$total_kb" 'BEGIN{ if(t+0<=0){print "0.00"; exit} printf "%.2f", (u/t)*100 }')"
    total_gb="$(awk -v t="$total_kb" 'BEGIN{ printf "%.2f", t*1024/1e9 }')"
    used_gb="$(awk -v u="$used_kb" 'BEGIN{ printf "%.2f", u*1024/1e9 }')"
    append_metric "磁盘" "logical_disk" "/" "mount=/" "usage_percent" "磁盘使用率" \
      "$pct" "%" 80 90 "$(health_of "$pct" 80 90)" "total_gb=$total_gb,used_gb=$used_gb"
  fi
fi

# root read-only
root_ro=0
while IFS= read -r line; do
  mount=$(echo "$line" | awk '{print $2}')
  opts=$(echo "$line" | awk '{print $4}')
  if [ "$mount" = "/" ]; then
    case ",$opts," in
      *,ro,*) root_ro=1 ;;
    esac
    break
  fi
done <<EOF
$(read_text /proc/mounts)
EOF
if [ "$root_ro" -eq 1 ]; then
  append_metric "系统健康" "filesystem" "/" "mount=/" "read_only" "根分区只读" \
    1 "bool" 1 1 "WARNING" "根分区为只读挂载"
else
  append_metric "系统健康" "filesystem" "/" "mount=/" "read_only" "根分区只读" \
    0 "bool" 1 1 "NORMAL" "根分区可写"
fi

# /tmp writable
writable=0
probe="/tmp/bklite-health-$$.tmp"
if printf 'ok' >"$probe" 2>/dev/null; then
  rm -f "$probe" || true
  writable=1
fi
if [ "$writable" -eq 1 ]; then
  append_metric "系统健康" "filesystem" "/tmp" "path=/tmp" "writable" "临时目录可写" \
    1 "bool" 1 1 "NORMAL" "临时目录可写"
else
  append_metric "系统健康" "filesystem" "/tmp" "path=/tmp" "writable" "临时目录可写" \
    0 "bool" 1 1 "CRITICAL" "临时目录不可写"
fi

# time sync
time_ok=0
time_detail="未检测到 chronyd/ntpd/systemd-timesyncd"
for unit in chronyd chrony ntpd systemd-timesyncd; do
  if command -v systemctl >/dev/null 2>&1; then
    state="$(systemctl is-active "$unit" 2>/dev/null || true)"
    if [ "$state" = "active" ]; then
      time_ok=1
      time_detail="$unit active"
      break
    fi
  fi
done
if [ "$time_ok" -eq 1 ]; then
  append_metric "系统健康" "service" "time_sync" "scope=system" "running" "时间同步服务" \
    1 "bool" 1 1 "NORMAL" "$time_detail"
else
  append_metric "系统健康" "service" "time_sync" "scope=system" "running" "时间同步服务" \
    0 "bool" 1 1 "WARNING" "$time_detail"
fi

# network ipv4 up (non-lo)
if command -v ip >/dev/null 2>&1; then
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    ifname=$(echo "$line" | awk '{print $2}')
    [ "$ifname" = "lo" ] && continue
    ipaddr=$(echo "$line" | awk '{print $4}' | cut -d/ -f1)
    [ -n "$ipaddr" ] || continue
    append_metric "网络" "network_adapter" "$ifname" "adapter=$ifname" "link_up" "网卡链路" \
      1 "bool" 1 1 "NORMAL" "ip=$ipaddr,status=up"
  done <<EOF
$(ip -o -4 addr show up 2>/dev/null || true)
EOF
fi

# process hotspots
top_cpu=""
top_mem=""
if command -v ps >/dev/null 2>&1; then
  idx=0
  while IFS= read -r line; do
    idx=$((idx + 1))
    [ "$idx" -le 3 ] || break
    pid=$(echo "$line" | awk '{print $1}')
    comm=$(echo "$line" | awk '{print $2}')
    cpu_p=$(echo "$line" | awk '{print $3}')
    [ -n "$comm" ] || continue
    piece="$comm=$(round2 "$cpu_p")%"
    if [ -z "$top_cpu" ]; then top_cpu="$piece"; else top_cpu="$top_cpu; $piece"; fi
    append_metric "进程热点" "process" "$comm" "rank=$idx" "cpu_percent" "CPU Top$idx" \
      "$(round2 "$cpu_p")" "%" 0 0 "NORMAL" "pid=$pid"
  done <<EOF
$(ps -eo pid,comm,%cpu,%mem --sort=-%cpu 2>/dev/null | awk 'NR>1 && NR<=4{print}')
EOF
  idx=0
  while IFS= read -r line; do
    idx=$((idx + 1))
    [ "$idx" -le 3 ] || break
    pid=$(echo "$line" | awk '{print $1}')
    comm=$(echo "$line" | awk '{print $2}')
    mem_p=$(echo "$line" | awk '{print $4}')
    [ -n "$comm" ] || continue
    piece="$comm=$(round2 "$mem_p")%"
    if [ -z "$top_mem" ]; then top_mem="$piece"; else top_mem="$top_mem; $piece"; fi
    append_metric "进程热点" "process" "$comm" "rank=$idx" "mem_percent" "内存 Top$idx" \
      "$(round2 "$mem_p")" "%" 0 0 "NORMAL" "pid=$pid"
  done <<EOF
$(ps -eo pid,comm,%cpu,%mem --sort=-%mem 2>/dev/null | awk 'NR>1 && NR<=4{print}')
EOF
fi

# sshd
sshd_ok=0
sshd_detail="sshd 未运行"
for unit in sshd ssh; do
  if command -v systemctl >/dev/null 2>&1; then
    state="$(systemctl is-active "$unit" 2>/dev/null || true)"
    if [ "$state" = "active" ]; then
      sshd_ok=1
      sshd_detail="$unit active"
      break
    fi
  fi
done
if [ "$sshd_ok" -eq 1 ]; then
  append_metric "基础服务" "service" "sshd" "service=sshd" "running" "SSH 服务" \
    1 "bool" 1 1 "NORMAL" "$sshd_detail"
else
  append_metric "基础服务" "service" "sshd" "service=sshd" "running" "SSH 服务" \
    0 "bool" 1 1 "WARNING" "$sshd_detail"
fi

# firewall
fw_ok=0
fw_detail="未检测到活跃防火墙服务"
for unit in firewalld ufw nftables iptables; do
  if command -v systemctl >/dev/null 2>&1; then
    state="$(systemctl is-active "$unit" 2>/dev/null || true)"
    if [ "$state" = "active" ]; then
      fw_ok=1
      fw_detail="$unit active"
      break
    fi
  fi
done
if [ "$fw_ok" -eq 1 ]; then
  append_metric "安全浅检" "service" "firewall" "scope=system" "running" "防火墙服务" \
    1 "bool" 1 1 "NORMAL" "$fw_detail"
else
  append_metric "安全浅检" "service" "firewall" "scope=system" "running" "防火墙服务" \
    0 "bool" 1 1 "WARNING" "$fw_detail"
fi

# update age
update_days="0.00"
update_status="NORMAL"
update_detail="无法读取更新记录"
newest=""
for path in /var/log/dpkg.log /var/log/yum.log /var/log/dnf.log /var/lib/apt/periodic/update-success-stamp; do
  if [ -e "$path" ]; then
    mtime="$(stat -c %Y "$path" 2>/dev/null || stat -f %m "$path" 2>/dev/null || true)"
    if [ -n "$mtime" ]; then
      if [ -z "$newest" ] || [ "$mtime" -gt "$newest" ]; then
        newest="$mtime"
      fi
    fi
  fi
done
if [ -n "$newest" ]; then
  now="$(date +%s)"
  update_days="$(awk -v n="$now" -v m="$newest" 'BEGIN{ printf "%.0f", (n-m)/86400 }')"
  update_status="$(health_of "$update_days" 90 180)"
  update_detail="days_since_package_log=$update_days"
fi
append_metric "更新账龄" "patch" "Package Updates" "scope=system" "days_since_update" "距上次更新天数" \
  "$update_days" "days" 90 180 "$update_status" "$update_detail"

# 去掉可能混入的换行，保证整段 result= 是单行合法 JSON（下游按整段 json.loads）
metrics_json="$(tr -d '\n\r' <"$METRICS_FILE")"

critical_count="$(printf '%s' "$metrics_json" | grep -o '"health_status":"CRITICAL"' | wc -l | tr -d ' ')"
warning_count="$(printf '%s' "$metrics_json" | grep -o '"health_status":"WARNING"' | wc -l | tr -d ' ')"
normal_count="$(printf '%s' "$metrics_json" | grep -o '"health_status":"NORMAL"' | wc -l | tr -d ' ')"
metric_count="$(awk -v s="$metrics_json" 'BEGIN{ n=gsub(/"metric_name"/,"&",s); print n+0 }')"

# 报告汇总 SQL 主要吃 result.metrics；分类数组用空数组，避免纯 shell 二次拼装弄坏 JSON。
critical_json="[]"
warning_json="[]"
normal_json="[]"

if [ "$critical_count" -gt 0 ] || [ "$warning_count" -gt 0 ]; then
  conclusion="需关注"
else
  conclusion="健康"
fi

host_json="$(printf '{"hostname":"%s","os_version":"%s","architecture":"%s",'\
'"uptime_hours":%s,"cpu_cores":%s,"memory_total_gb":%s,"top_cpu":"%s","top_memory":"%s"}' \
  "$(json_escape "$hostname")" \
  "$(json_escape "$os_version")" \
  "$(json_escape "$arch")" \
  "$uptime_hours" \
  "$cores" \
  "$mem_total_gb" \
  "$(json_escape "$top_cpu")" \
  "$(json_escape "$top_mem")"
)"

printf 'result={"collected_at":"%s","host":%s,"metrics":[%s],"metric_count":%s,'\
'"critical":%s,"warning":%s,"normal":%s,"critical_count":%s,'\
'"warning_count":%s,"normal_count":%s,"conclusion":"%s"}\n' \
  "$(json_escape "$collected_at")" \
  "$host_json" \
  "$metrics_json" \
  "$metric_count" \
  "$critical_json" \
  "$warning_json" \
  "$normal_json" \
  "$critical_count" \
  "$warning_count" \
  "$normal_count" \
  "$(json_escape "$conclusion")"
""".strip()
