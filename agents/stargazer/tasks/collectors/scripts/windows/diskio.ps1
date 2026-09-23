$diskCounters = Get-MetricData 'Win32_PerfRawData_PerfDisk_PhysicalDisk' | Where-Object { $_.Name -and $_.Name -ne '_Total' }
$utilByName = @{}
Get-MetricData 'Win32_PerfFormattedData_PerfDisk_PhysicalDisk' | ForEach-Object {
    if ($_.Name -and $_.Name -ne '_Total' -and $null -ne $_.PercentDiskTime) {
        $utilByName[$_.Name] = [double]$_.PercentDiskTime
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
    if ($utilByName.ContainsKey($d.Name)) {
        $util = $utilByName[$d.Name]
        if ($util -lt 0) { $util = 0 }
        if ($util -gt 100) { $util = 100 }
        $item['io_util_percent'] = [math]::Round($util, 2)
    }
    $diskioArr += $item
}
$result['diskio'] = $diskioArr
