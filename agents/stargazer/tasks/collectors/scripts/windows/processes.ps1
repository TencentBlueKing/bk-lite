$processes = Get-MetricData 'Win32_Process'
$result['processes'] = @{
    running = ($processes | Measure-Object).Count
}
