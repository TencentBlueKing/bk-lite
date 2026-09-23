$cpuTotal = Get-MetricData 'Win32_PerfFormattedData_PerfOS_Processor' | Where-Object { $_.Name -eq '_Total' } | Select-Object -First 1
$cpuData = Get-MetricData 'Win32_Processor'
$cpuCount = ($cpuData | Measure-Object -Property NumberOfLogicalProcessors -Sum).Sum
if (-not $cpuCount) { $cpuCount = ($cpuData | Measure-Object).Count }
$result['cpu'] = @{
    core_count = $cpuCount
}
if ($cpuTotal -and $null -ne $cpuTotal.PercentProcessorTime) {
    $usage = [math]::Round([double]$cpuTotal.PercentProcessorTime, 2)
    if ($usage -lt 0) { $usage = 0 }
    if ($usage -gt 100) { $usage = 100 }
    $result['cpu']['usage_percent'] = $usage
}
