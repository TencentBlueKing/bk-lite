$processes = Get-MetricData 'Win32_Process'
$result['processes'] = @{
    running = ($processes | Measure-Object).Count
    blocked = 0
    sleeping = 0
    zombies = 0
}
