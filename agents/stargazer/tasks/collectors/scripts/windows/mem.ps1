$os = Get-MetricData 'Win32_OperatingSystem'
$totalBytes = [int64]$os.TotalVisibleMemorySize * 1024
$freeBytes = [int64]$os.FreePhysicalMemory * 1024
$usedBytes = $totalBytes - $freeBytes
$swapTotal = [int64]$os.TotalVirtualMemorySize * 1024
$swapFree = [int64]$os.FreeVirtualMemory * 1024
$swapUsed = $swapTotal - $swapFree
$result['mem'] = @{
    total_bytes = $totalBytes
    used_bytes = $usedBytes
    available_bytes = $freeBytes
    swap_total_bytes = $swapTotal
    swap_used_bytes = $swapUsed
}
