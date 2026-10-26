$ErrorActionPreference = "SilentlyContinue"
$WarningPreference = "SilentlyContinue"

$virtualizationNs = "root\virtualization\v2"
try {
    $null = Get-CimInstance -Namespace $virtualizationNs -ClassName Msvm_ComputerSystem -ErrorAction SilentlyContinue
} catch {}

Import-Module Hyper-V -ErrorAction SilentlyContinue
$vmHost = Get-VMHost
$hostName = if ($vmHost) { $vmHost.ComputerName } else { $env:COMPUTERNAME }
$ipAddr = "{{bk_host_innerip}}"
$cpuCores = if ($vmHost) { [int]$vmHost.LogicalProcessorCount } else { 0 }
$memoryMb = 0
if ($vmHost -and $vmHost.MemoryCapacity) {
    $memoryMb = [int]([double]$vmHost.MemoryCapacity / 1MB)
}
$version = ""
try {
    $version = (Get-ItemProperty -Path "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Virtualization" -ErrorAction SilentlyContinue).Version
} catch {}
if (-not $version -and $vmHost) {
    $version = [string]$vmHost.HyperVVersion
}

$vms = @()
foreach ($vm in @(Get-VM)) {
    $guestIp = ""
    try {
        $addresses = @($vm | Get-VMNetworkAdapter | ForEach-Object { $_.IPAddresses } | Where-Object { $_ })
        $guestIp = ($addresses | Where-Object { $_ -notmatch ":" } | Select-Object -First 1)
        if (-not $guestIp -and $addresses.Count -gt 0) {
            $guestIp = $addresses[0]
        }
    } catch {}
    $vms += @{
        inst_name = $vm.Name
        resource_id = [string]$vm.VMId
        power_state = [string]$vm.State
        vcpus = [int]$vm.ProcessorCount
        memory = [int]([double]$vm.MemoryStartup / 1MB)
        ip_addr = if ($guestIp) { [string]$guestIp } else { "" }
        self_host = $hostName
    }
}

@{
    host = @{
        inst_name = $hostName
        resource_id = $hostName
        ip_addr = $ipAddr
        cpu_cores = $cpuCores
        memory = $memoryMb
        hyperv_version = [string]$version
    }
    vms = $vms
} | ConvertTo-Json -Compress -Depth 6
