# Windows System Info Collector
# PowerShell script for collecting Windows host information

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

# Hostname
$hostname = $env:COMPUTERNAME
if ([string]::IsNullOrWhiteSpace($hostname)) {
    $hostname = [System.Net.Dns]::GetHostName()
}

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

# Build JSON output
$json = @{
    hostname = Get-ValueOrUnknown $hostname
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
} | ConvertTo-Json -Compress

# Output JSON
Write-Output $json
