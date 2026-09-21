$os = Get-MetricData 'Win32_OperatingSystem'
$totalBytes = [int64]$os.TotalVisibleMemorySize * 1024
$availableBytes = 0
$perfMem = Get-MetricData 'Win32_PerfRawData_PerfOS_Memory' | Select-Object -First 1
if ($perfMem -and $null -ne $perfMem.AvailableBytes) {
    $availableBytes = [int64]$perfMem.AvailableBytes
}
if ($availableBytes -le 0) {
    $fmtMem = Get-MetricData 'Win32_PerfFormattedData_PerfOS_Memory' | Select-Object -First 1
    if ($fmtMem -and $null -ne $fmtMem.AvailableMBytes) {
        $availableBytes = [int64]$fmtMem.AvailableMBytes * 1024 * 1024
    }
}
if ($totalBytes -gt 0 -and $availableBytes -gt $totalBytes) {
    $availableBytes = $totalBytes
}
$usedBytes = $totalBytes - $availableBytes
if ($usedBytes -lt 0) { $usedBytes = 0 }

$swapTotal = [int64]0
$swapUsed = [int64]0
foreach ($pagefile in @(Get-MetricData 'Win32_PageFileUsage')) {
    if (-not $pagefile) { continue }
    $swapTotal += [int64]$pagefile.AllocatedBaseSize * 1024 * 1024
    $swapUsed += [int64]$pagefile.CurrentUsage * 1024 * 1024
}
$swapFree = $swapTotal - $swapUsed
if ($swapFree -lt 0) { $swapFree = 0 }

$result['mem'] = @{
    total_bytes = $totalBytes
    used_bytes = $usedBytes
    available_bytes = $availableBytes
    swap_total_bytes = $swapTotal
    swap_used_bytes = $swapUsed
    swap_free_bytes = $swapFree
}
