# H3C WLAN AC SNMP Access Guide

This plugin uses Telegraf `inputs.snmp` on a selected node to collect H3C wireless controller (AC) health, connected AP count, and associated station count.

## Prerequisites

- The selected node can reach the target device SNMP port (default `161/UDP`).
- SNMPv2c or SNMPv3 is enabled with read-only access.
- SNMPv3 (auth and privacy) is preferred. For v2c, put the community string only in the dedicated form field.
- The device should expose the controller objects declared by this template. Missing optional scalars on some models or views do not block the remaining metrics.

## Access steps

1. Confirm SNMP reachability from the node to the device IP (see Pre-access checks).
2. Choose the SNMP version. For v2c fill in the community; for v3 fill in security name, security level, auth/privacy protocols and passwords.
3. Adjust port, timeout, and interval as needed. Defaults are port `161`, timeout `10` seconds, interval `60` seconds.
4. In the instance table, select a node and fill in device IP, instance name, and group.
5. Save and wait for at least one collection interval.

## Pre-access checks

Replace `TARGET` with the device IP and use a read-only community (use a matching v3 probe in v3 environments):

```bash
TARGET=192.0.2.10
snmpget -v2c -c "$SNMP_COMMUNITY" "$TARGET" 1.3.6.1.2.1.1.3.0
snmpget -v2c -c "$SNMP_COMMUNITY" "$TARGET" 1.3.6.1.2.1.1.2.0
```

`sysUpTime` (`1.3.6.1.2.1.1.3.0`) should return TimeTicks. `sysObjectID` (`1.3.6.1.2.1.1.2.0`) on H3C Comware WLAN AC devices usually belongs to the `1.3.6.1.4.1.25506` family.

## Form fields

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| IP | yes | none | Device management address. |
| Port | yes | `161` | SNMP UDP port. |
| Version | yes | v2c | `v2c` or `v3`. |
| Community | v2c required | `public` | Read-only community. |
| Name / Level / Auth protocol / Auth password / Privacy protocol / Privacy password | v3 by level | as on the form | SNMPv3 only; passwords are injected via environment variables and are not stored in plaintext config. |
| Timeout | yes | `10` seconds | Per SNMP request timeout. |
| Interval | yes | `60` seconds | Collection period, minimum `1` second. |
| Node | yes | none | Node that runs collection. |
| Instance name | yes | none | Display name in the platform. |
| Group | yes | none | Instance group. |

## Post-access checks

Wait for at least one collection interval, then confirm the instance appears and:

- `snmp_uptime` keeps increasing.
- `device_cpu_usage` and `device_memory_usage` have entity-dimension readings. Most physical entities return `0`; the CPU/memory-bearing board carries the real value.
- `wlan_ap_connect_count` and `wlan_station_connect_count` roughly match the site.

## Troubleshooting

### Only uptime, no CPU or memory

The SNMP view may not authorize entity health objects. Confirm the read-only view includes `1.3.6.1.4.1.25506.2.6` (HH3C-ENTITY-EXT-MIB).

### No AP or station data

Wireless controller objects are unauthorized, or the model does not expose those scalars. Confirm the read-only view includes `1.3.6.1.4.1.25506.2.75` (HH3C-DOT11-ACMT-MIB). This does not mean whole-device collection failed.

### CPU or memory stays at 0 on most rows

`hh3cEntityExtCpuUsage` and `hh3cEntityExtMemUsage` are per physical entity. Most entities return `0` and only the board that actually hosts CPU or memory reports a non-zero value. Use the non-zero entity for thresholds; do not average every row.

### Max AP number is missing

`wlan_max_ap_num_permitted` (`hh3cDot11MaxAPNumPermitted`) is optional and may be absent on some software versions. Connected AP count still comes from `wlan_ap_connect_count`.

### AP count series disagree

`wlan_ap_connect_count` (`hh3cDot11APConnectCount`) is the current connected AP count. `wlan_master_ap_count` (`hh3cDot11MasterAPCount`) is the master-AP count. `wlan_total_ap_connected` (`hh3cDot11TotalAPconnected`) is a separate total. They are different counters and may disagree across software versions or SNMP views. Use connected count for live scale; do not reuse one threshold on all three series.
