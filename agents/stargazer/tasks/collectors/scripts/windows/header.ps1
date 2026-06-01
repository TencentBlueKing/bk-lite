$ErrorActionPreference = 'SilentlyContinue'
function Get-MetricData {
    param([string]$Class)
    try { Get-WmiObject -Class $Class -ErrorAction Stop }
    catch { Get-CimInstance -ClassName $Class }
}
$result = @{}
