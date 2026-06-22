$netAdapters = Get-MetricData 'Win32_PerfRawData_Tcpip_NetworkInterface'
$netArr = @()
foreach ($n in $netAdapters) {
    if (-not $n.Name) { continue }
    $netArr += @{
        interface = $n.Name
        rx_bytes = [int64]$n.BytesReceivedPersec
        tx_bytes = [int64]$n.BytesSentPersec
        rx_packets = [int64]$n.PacketsReceivedPersec
        tx_packets = [int64]$n.PacketsSentPersec
        rx_errors = [int64]$n.PacketsReceivedErrors
        tx_errors = [int64]$n.PacketsOutboundErrors
        rx_drops = [int64]$n.PacketsReceivedDiscarded
        tx_drops = [int64]$n.PacketsOutboundDiscarded
    }
}
$result['net'] = $netArr
