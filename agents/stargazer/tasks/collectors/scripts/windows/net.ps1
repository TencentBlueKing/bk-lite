$netAdapters = Get-MetricData 'Win32_PerfRawData_Tcpip_NetworkInterface'
$netArr = @()
foreach ($n in $netAdapters) {
    if (-not $n.Name) { continue }
    $netArr += @{
        interface = $n.Name
        rx_bytes = [int64]$n.BytesReceivedPersec
        tx_bytes = [int64]$n.BytesSentPersec
        rx_errors = [int64]$n.PacketsReceivedErrors
        tx_errors = [int64]$n.PacketsOutboundErrors
    }
}
$result['net'] = $netArr
