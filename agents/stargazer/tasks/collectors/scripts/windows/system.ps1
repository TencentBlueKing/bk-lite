$os = Get-MetricData 'Win32_OperatingSystem'
$uptime = 0
try {
    $lastBoot = [Management.ManagementDateTimeConverter]::ToDateTime($os.LastBootUpTime)
    $uptime = [int64]((Get-Date) - $lastBoot).TotalSeconds
} catch {}
$result['system'] = @{
    uptime_seconds = $uptime
    load1 = 0
    load5 = 0
    load15 = 0
}
