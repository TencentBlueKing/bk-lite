$services = Get-MetricData 'Win32_Service'
$serviceArr = @()
foreach ($svc in @($services)) {
    if (-not $svc -or -not $svc.Name) { continue }
    $stateValue = 0
    if ([string]$svc.State -eq 'Running') { $stateValue = 1 }
    $serviceArr += @{
        name = [string]$svc.Name
        state = $stateValue
    }
}
$result['service'] = $serviceArr
