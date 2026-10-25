$ErrorActionPreference = "SilentlyContinue"
$WarningPreference = "SilentlyContinue"

function Get-CounterAverage {
    param([string]$Path)
    try {
        $samples = @(Get-Counter -Counter $Path -ErrorAction SilentlyContinue | Select-Object -ExpandProperty CounterSamples)
        if (-not $samples) { return $null }
        $values = @($samples | Where-Object { $_.CookedValue -ge 0 -and $_.CookedValue -lt 1e8 } | ForEach-Object { $_.CookedValue })
        if (-not $values) { return $null }
        return ($values | Measure-Object -Average).Average
    } catch {
        return $null
    }
}

function Get-NamedCounterMap {
    param([string]$Path)
    $map = @{}
    try {
        $samples = @(Get-Counter -Counter $Path -ErrorAction SilentlyContinue | Select-Object -ExpandProperty CounterSamples)
        foreach ($sample in $samples) {
            if ($null -eq $sample) { continue }
            $instance = $sample.InstanceName
            if (-not $instance -or $instance -eq "_total") { continue }
            $map[$instance] = $sample.CookedValue
        }
    } catch {}
    return $map
}

$virtualizationNs = "root\virtualization\v2"
try {
    $null = Get-CimInstance -Namespace $virtualizationNs -ClassName Msvm_ComputerSystem -ErrorAction SilentlyContinue
} catch {}

Import-Module Hyper-V -ErrorAction SilentlyContinue
$vmHost = Get-VMHost
$hostName = if ($vmHost) { $vmHost.ComputerName } else { $env:COMPUTERNAME }
$cpu = Get-CounterAverage "\Processor(_Total)\% Processor Time"
if ($null -eq $cpu) {
    $cpu = Get-CounterAverage "\Hyper-V Hypervisor Logical Processor(_Total)\% Total Run Time"
}
$mem = $null
if ($vmHost -and $vmHost.MemoryCapacity) {
    $available = 0
    if ($vmHost.PSObject.Properties.Name -contains "MemoryAvailable") {
        $available = [double]$vmHost.MemoryAvailable
    }
    $capacity = [double]$vmHost.MemoryCapacity
    if ($capacity -gt 0) {
        $mem = [math]::Round((($capacity - $available) / $capacity) * 100, 2)
    }
}
if ($null -eq $mem) {
    $mem = Get-CounterAverage "\Memory\% Committed Bytes In Use"
}

$storageRead = Get-NamedCounterMap "\Hyper-V Virtual Storage Device(*)\Read Latency"
$storageWrite = Get-NamedCounterMap "\Hyper-V Virtual Storage Device(*)\Write Latency"
$useSecondsFallback = ($storageRead.Count -eq 0 -and $storageWrite.Count -eq 0)
$hostDisks = @()
if ($useSecondsFallback) {
    $logicalRead = Get-NamedCounterMap "\LogicalDisk(*)\Avg. Disk sec/Read"
    $logicalWrite = Get-NamedCounterMap "\LogicalDisk(*)\Avg. Disk sec/Write"
    foreach ($name in ($logicalRead.Keys + $logicalWrite.Keys | Select-Object -Unique)) {
        if ($name -eq "_total") { continue }
        $hostDisks += @{
            name = $name
            read_latency_ms = if ($logicalRead.ContainsKey($name)) { [math]::Round($logicalRead[$name] * 1000, 3) } else { $null }
            write_latency_ms = if ($logicalWrite.ContainsKey($name)) { [math]::Round($logicalWrite[$name] * 1000, 3) } else { $null }
            unit = "ms"
        }
    }
} else {
    foreach ($name in ($storageRead.Keys + $storageWrite.Keys | Select-Object -Unique)) {
        $hostDisks += @{
            name = $name
            read_latency_ms = if ($storageRead.ContainsKey($name)) { [math]::Round($storageRead[$name], 3) } else { $null }
            write_latency_ms = if ($storageWrite.ContainsKey($name)) { [math]::Round($storageWrite[$name], 3) } else { $null }
            unit = "ms"
        }
    }
}

$vms = @()
foreach ($vm in @(Get-VM)) {
    $cpuUsage = $null
    $guest = Get-CounterAverage ("\Hyper-V Hypervisor Virtual Processor(" + $vm.Name + ":*)\% Guest Run Time")
    if ($null -eq $guest) {
        $cpuUsage = $vm.CPUUsage
    } else {
        $cpuUsage = [math]::Round($guest, 2)
    }
    $memUsage = $null
    $assigned = [double]$vm.MemoryAssigned
    $maximum = [double]$vm.MemoryMaximum
    if ($maximum -le 0) { $maximum = [double]$vm.MemoryStartup }
    if ($maximum -gt 0 -and $assigned -ge 0) {
        $memUsage = [math]::Round(($assigned / $maximum) * 100, 2)
    }
    $vmDisks = @()
    foreach ($drive in @(Get-VMHardDiskDrive -VM $vm -ErrorAction SilentlyContinue)) {
        $leaf = Split-Path -Leaf $drive.Path
        $key = $null
        foreach ($candidate in @($leaf, $drive.Path, [IO.Path]::GetFileNameWithoutExtension($leaf))) {
            if ($storageRead.ContainsKey($candidate) -or $storageWrite.ContainsKey($candidate)) {
                $key = $candidate
                break
            }
        }
        if (-not $key) {
            foreach ($name in $storageRead.Keys + $storageWrite.Keys) {
                if ($name -and $leaf -and $name.ToLower().Contains($leaf.ToLower())) {
                    $key = $name
                    break
                }
            }
        }
        if ($key) {
            $vmDisks += @{
                name = $leaf
                read_latency_ms = if ($storageRead.ContainsKey($key)) { [math]::Round($storageRead[$key], 3) } else { $null }
                write_latency_ms = if ($storageWrite.ContainsKey($key)) { [math]::Round($storageWrite[$key], 3) } else { $null }
                unit = "ms"
            }
        } elseif ($useSecondsFallback -and $hostDisks.Count -gt 0) {
            $vmDisks += $hostDisks[0]
            $vmDisks[-1] = @{
                name = $leaf
                read_latency_ms = $hostDisks[0].read_latency_ms
                write_latency_ms = $hostDisks[0].write_latency_ms
                unit = "ms"
            }
        }
    }
    $vms += @{
        name = $vm.Name
        inst_name = $vm.Name
        resource_id = [string]$vm.VMId
        vmid = [string]$vm.VMId
        power_state = [string]$vm.State
        cpu_usage = $cpuUsage
        mem_usage = $memUsage
        disks = $vmDisks
    }
}

$result = @{
    host = @{
        inst_name = $hostName
        resource_id = $hostName
        cpu_usage = $cpu
        mem_usage = $mem
        disks = $hostDisks
    }
    vms = $vms
}

$result | ConvertTo-Json -Compress -Depth 6
