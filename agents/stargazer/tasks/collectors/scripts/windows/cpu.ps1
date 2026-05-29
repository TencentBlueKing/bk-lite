$cpuData = Get-MetricData 'Win32_Processor'
$cpuLoad = ($cpuData | Measure-Object -Property LoadPercentage -Average).Average
$cpuCount = ($cpuData | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
if (-not $cpuCount) { $cpuCount = ($cpuData | Measure-Object).Count }
$result['cpu'] = @{
    usage_percent = [math]::Round($cpuLoad, 2)
    core_count = $cpuCount
    load_1m = 0
    load_5m = 0
    load_15m = 0
}
