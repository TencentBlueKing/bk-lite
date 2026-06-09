$diskCounters = Get-MetricData 'Win32_PerfRawData_PerfDisk_PhysicalDisk' | Where-Object { $_.Name -and $_.Name -ne '_Total' }
$diskioArr = @()
foreach ($d in $diskCounters) {
    $diskioArr += @{
        device = $d.Name
        reads = [int64]$d.DiskReadsPersec
        writes = [int64]$d.DiskWritesPersec
        read_bytes = [int64]$d.DiskReadBytesPersec
        write_bytes = [int64]$d.DiskWriteBytesPersec
        io_time_ms = 0
        read_time_ms = 0
        write_time_ms = 0
    }
}
$result['diskio'] = $diskioArr
