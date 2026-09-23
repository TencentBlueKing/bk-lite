$diskCounters = Get-MetricData 'Win32_PerfRawData_PerfDisk_PhysicalDisk' | Where-Object { $_.Name -and $_.Name -ne '_Total' }
$formattedByName = @{}
Get-MetricData 'Win32_PerfFormattedData_PerfDisk_PhysicalDisk' | ForEach-Object {
    if ($_.Name -and $_.Name -ne '_Total') {
        $formattedByName[$_.Name] = $_
    }
}
$diskioArr = @()
foreach ($d in $diskCounters) {
    $item = @{
        device = $d.Name
        reads = [int64]$d.DiskReadsPersec
        writes = [int64]$d.DiskWritesPersec
        read_bytes = [int64]$d.DiskReadBytesPersec
        write_bytes = [int64]$d.DiskWriteBytesPersec
    }
    if ($formattedByName.ContainsKey($d.Name)) {
        $formatted = $formattedByName[$d.Name]
        if ($null -ne $formatted.PercentDiskTime) {
            $util = [double]$formatted.PercentDiskTime
            if ($util -lt 0) { $util = 0 }
            if ($util -gt 100) { $util = 100 }
            $item['io_util_percent'] = [math]::Round($util, 2)
        }
        if ($null -ne $formatted.AvgDiskSecPerRead) {
            $item['read_latency_ms'] = [math]::Round([math]::Max([double]$formatted.AvgDiskSecPerRead, 0) * 1000, 4)
        }
        if ($null -ne $formatted.AvgDiskSecPerWrite) {
            $item['write_latency_ms'] = [math]::Round([math]::Max([double]$formatted.AvgDiskSecPerWrite, 0) * 1000, 4)
        }
    }
    $diskioArr += $item
}
$result['diskio'] = $diskioArr
