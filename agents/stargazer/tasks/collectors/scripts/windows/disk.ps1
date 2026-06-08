$disks = Get-MetricData 'Win32_LogicalDisk' | Where-Object { $_.DriveType -eq 3 }
$diskArr = @()
foreach ($d in $disks) {
    $total = [int64]$d.Size
    $free = [int64]$d.FreeSpace
    $used = $total - $free
    $pct = if ($total -gt 0) { [math]::Round($used / $total * 100, 2) } else { 0 }
    $diskArr += @{
        mount = $d.DeviceID
        total_bytes = $total
        free_bytes = $free
        used_bytes = $used
        used_percent = $pct
        inodes_used_percent = 0
    }
}
$result['disk'] = $diskArr
