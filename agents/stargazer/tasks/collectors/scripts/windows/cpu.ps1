$cpuData = Get-MetricData 'Win32_Processor'
$cpuLoad = ($cpuData | Measure-Object -Property LoadPercentage -Average).Average
$cpuCount = ($cpuData | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
if (-not $cpuCount) { $cpuCount = ($cpuData | Measure-Object).Count }
$result['cpu'] = @{
    usage_percent = [math]::Round($cpuLoad, 2)
    usage_user_percent = 0
    usage_system_percent = 0
    usage_iowait_percent = 0
    usage_irq_percent = 0
    usage_steal_percent = 0
    core_count = $cpuCount
    load_1m = 0
    load_5m = 0
    load_15m = 0
}
