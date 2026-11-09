# Windows host facts for CMDB custom collect plugin custom_win_host.
# stdout: one JSON array. Field names are host model attr ids.
# Enum values are option ids: os_type Windows=2, cpu_arch x64/arm64/x86.
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Get-Gb([long]$bytes) {
    if ($bytes -le 0) { return 0 }
    return [int][math]::Round($bytes / 1GB)
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
    $ip = @($nic.IPAddress | Where-Object { $_ -match "^\d+\.\d+\.\d+\.\d+$" } | Select-Object -First 1)
    if (-not $ip) { $ip = "" }
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
    memory       = [string](Get-Gb ([int64]$cs.TotalPhysicalMemory))
    disk         = [string](Get-Gb ([int64]$diskBytes))
    inner_mac    = ([string]$nic.MACAddress).Replace("-", ":").ToUpper()
    machine_type = $machineType
}

Write-Output ("[" + ($row | ConvertTo-Json -Compress) + "]")
