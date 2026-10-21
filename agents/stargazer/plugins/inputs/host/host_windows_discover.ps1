# Windows System Info Collector
# PowerShell script for collecting Windows host information

function Get-HostMachineType {
    param(
        $HypervisorPresent,
        [string]$Manufacturer = "",
        [string]$Model = ""
    )
    $blob = "$Manufacturer $Model"
    if ($blob -match 'VMware|VirtualBox|KVM|QEMU|Xen|Virtual Machine|Hyper-V|Bochs|Parallels|AHV|Nutanix|Amazon EC2|Alibaba Cloud|OpenStack|BHYVE|oVirt') {
        return "virtual"
    }
    $hasIdentity = -not [string]::IsNullOrWhiteSpace($Manufacturer) -or -not [string]::IsNullOrWhiteSpace($Model)
    if ($HypervisorPresent -eq $true) {
        return "virtual"
    }
    if ($hasIdentity) {
        return "physical_server"
    }
    return "unknown"
}

function Get-CollectedHostName {
    param(
        [AllowEmptyString()]
        [string]$ComputerName = $env:COMPUTERNAME,
        [AllowEmptyString()]
        [string]$DnsHostName
    )
    if (-not [string]::IsNullOrWhiteSpace($ComputerName)) {
        return $ComputerName.Trim()
    }
    if ($PSBoundParameters.ContainsKey("DnsHostName")) {
        $resolved = $DnsHostName
    } else {
        try {
            $resolved = [System.Net.Dns]::GetHostName()
        } catch {
            $resolved = ""
        }
    }
    if ([string]::IsNullOrWhiteSpace($resolved)) {
        return ""
    }
    return $resolved.Trim()
}

if ($env:HOST_DISCOVER_SOURCE_ONLY -eq '1') {
    return
}

# Error handling
$ErrorActionPreference = "SilentlyContinue"

# Helper function to get value or return "unknown"
function Get-ValueOrUnknown {
    param($Value)
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return "unknown"
    }
    return $Value.ToString().Trim()
}

# Hostname：计算机名优先，否则 DNS 主机名。都没有时留空。
$hostname = Get-CollectedHostName

# OS Information
$os = Get-WmiObject -Class Win32_OperatingSystem
$os_type = "Windows"
$os_name = if ($os) { $os.Caption } else { "unknown" }
$os_version = if ($os) { $os.Version } else { "unknown" }

# Architecture / Bits
$cs = Get-WmiObject -Class Win32_ComputerSystem
$cpu_arch = if ($cs) { $cs.SystemType } else { $env:PROCESSOR_ARCHITECTURE }
$os_bits = if ($cpu_arch -match "64") { "64-bit" } else { "32-bit" }

# CPU Information
$cpu = Get-WmiObject -Class Win32_Processor | Select-Object -First 1
$cpu_model = if ($cpu) { $cpu.Name } else { "unknown" }
$cpu_cores = if ($cpu) { $cpu.NumberOfLogicalProcessors } else { $env:NUMBER_OF_PROCESSORS }
if ([string]::IsNullOrWhiteSpace($cpu_cores)) {
    $cpu_cores = "unknown"
}

# Memory (GB)
$memory_bytes = if ($cs) { $cs.TotalPhysicalMemory } else { 0 }
$memory_gb = if ($memory_bytes -gt 0) { 
    [math]::Round($memory_bytes / 1GB, 1) 
} else { 
    0.0 
}

# Disk (GB) - Sum all physical drives
$disk_gb = 0.0
$drives = Get-WmiObject -Class Win32_LogicalDisk -Filter "DriveType=3"
if ($drives) {
    foreach ($drive in $drives) {
        if ($drive.Size) {
            $disk_gb += [math]::Round($drive.Size / 1GB, 1)
        }
    }
}

# MAC Address - Get first active network adapter
$mac_address = "unknown"
$adapters = Get-WmiObject -Class Win32_NetworkAdapterConfiguration -Filter "IPEnabled=True"
if ($adapters) {
    $firstAdapter = $adapters | Select-Object -First 1
    if ($firstAdapter.MACAddress) {
        $mac_address = $firstAdapter.MACAddress
    }
}

$mountRows = @()
if ($drives) {
    foreach ($drive in @($drives)) {
        if (-not $drive.DeviceID) { continue }
        $sizeText = "0.0"
        if ($drive.Size) {
            $sizeText = [math]::Round($drive.Size / 1GB, 1).ToString()
        }
        $mountRows += @{
            device = $drive.DeviceID
            mount = $drive.DeviceID
            fstype = $(if ($drive.FileSystem) { $drive.FileSystem } else { "" })
            size_gb = $sizeText
        }
    }
}

$nicRows = @()
$adapterConfigs = Get-WmiObject -Class Win32_NetworkAdapterConfiguration
$adapters = Get-WmiObject -Class Win32_NetworkAdapter
if ($adapters) {
    foreach ($adapter in @($adapters)) {
        if (-not $adapter.NetConnectionID -or -not $adapter.MACAddress) { continue }
        $ipText = ""
        if ($adapterConfigs) {
            $config = @($adapterConfigs | Where-Object { $_.Index -eq $adapter.Index } | Select-Object -First 1)
            if ($config -and $config.IPAddress) {
                $ipText = (@($config.IPAddress) | Where-Object { $_ -match '^\d+\.' }) -join ","
            }
        }
        $nicRows += @{
            name = $adapter.NetConnectionID
            mac = $adapter.MACAddress
            ip = $ipText
        }
    }
}

$hypervisorPresent = $null
if ($cs -and ($cs.PSObject.Properties.Name -contains "HypervisorPresent")) {
    $hypervisorPresent = $cs.HypervisorPresent
}
$machineType = Get-HostMachineType `
    -HypervisorPresent $hypervisorPresent `
    -Manufacturer $(if ($cs) { $cs.Manufacturer } else { "" }) `
    -Model $(if ($cs) { $cs.Model } else { "" })

# Build JSON output
$json = @{
    hostname = $hostname
    os_type = Get-ValueOrUnknown $os_type
    os_name = Get-ValueOrUnknown $os_name
    os_version = Get-ValueOrUnknown $os_version
    os_bits = Get-ValueOrUnknown $os_bits
    cpu_architecture = Get-ValueOrUnknown $cpu_arch
    cpu_model = Get-ValueOrUnknown $cpu_model
    cpu_cores = Get-ValueOrUnknown $cpu_cores
    memory_gb = $memory_gb
    disk_gb = [math]::Round($disk_gb, 1)
    mac_address = Get-ValueOrUnknown $mac_address
    machine_type = $machineType
    mounts = @($mountRows)
    nics = @($nicRows)
} | ConvertTo-Json -Compress -Depth 4

# Output JSON
Write-Output $json
