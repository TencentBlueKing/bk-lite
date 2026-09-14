# Huawei NetEngine Router SNMP Guide

This plugin uses Telegraf `inputs.snmp` on the selected node to collect Huawei NetEngine (NE) router health, interface traffic, BGP, and BFD metrics.

## Prerequisites

- The selected node can reach the device SNMP port (default `161/UDP`).
- SNMPv2c or SNMPv3 is enabled with read-only access.
- SNMPv3 with auth and privacy is recommended. For v2c, enter the community only in the dedicated form field.
- The device must expose standard IF-MIB plus the Huawei private objects declared by this template. Some models or restricted views omit individual tables; missing objects do not block the rest of the metrics.

## Setup steps

1. Confirm SNMP reachability from the node to the device IP (see Pre-access checks).
2. Choose the SNMP version. For v2c fill in the community. For v3 fill in the security name, level, auth/privacy protocols, and passwords.
3. Adjust port, timeout, and interval if needed. Defaults are port `161`, timeout `10` seconds, interval `60` seconds.
4. In the monitor-object table, choose the node and fill in the device IP, instance name, and group.
5. Save and wait for at least one collection interval.

## Pre-access checks

Replace `TARGET` with the device IP. Use a read-only community (or the matching v3 probe in a v3 environment):

```bash
TARGET=192.0.2.10
snmpget -v2c -c "$SNMP_COMMUNITY" "$TARGET" 1.3.6.1.2.1.1.3.0
snmpget -v2c -c "$SNMP_COMMUNITY" "$TARGET" 1.3.6.1.2.1.1.2.0
```

`sysUpTime` (`1.3.6.1.2.1.1.3.0`) should return TimeTicks. On NetEngine, `sysObjectID` (`1.3.6.1.2.1.1.2.0`) usually belongs to the `1.3.6.1.4.1.2011.2.62` or `1.3.6.1.4.1.2011.2.297` family.

## Form fields

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| IP | yes | none | Device management address. Locked on edit. |
| Port | yes | `161` | SNMP UDP port. |
| Version | yes | v2c | `v2c` or `v3`. |
| Community | required for v2c | `public` | Read-only community. |
| Name / Level / Auth protocol / Auth password / Privacy protocol / Privacy password | v3 by level | per form | SNMPv3 only. Passwords are injected via environment variables and are not stored as plaintext in the template. |
| Timeout | yes | `10` seconds | Per-request SNMP timeout. |
| Interval | yes | `60` seconds | Collection period, minimum `1` second. |
| Node | yes | none | Collector node. |
| Instance name | yes | none | Display name in the platform. |
| Group | yes | none | Instance group. |

## After access

Wait for at least one collection interval, then confirm the instance appears and check:

- `snmp_uptime` keeps increasing.
- `device_cpu_usage` and `device_memory_usage` have per-entity readings.
- `interface_ifHCInOctets` / `interface_ifHCOutOctets` show rates on in-service ports.
- When BGP is established, `device_bgp_peer_state` should be established.
- When BFD is enabled, `device_bfd_sess_state` should be up.

Identity tags `hwDeviceEsn` and `hwProductName` are reported with the SNMP measurement so you can confirm the chassis.

## Troubleshooting

### Only uptime and interfaces, no CPU or memory

The SNMP view may not authorize entity-health objects. Confirm the read-only view includes `1.3.6.1.4.1.2011.5.25.31` and `1.3.6.1.4.1.2011.6.3`.

### No BGP or BFD data

The feature is disabled, no sessions exist, or the view does not authorize `1.3.6.1.4.1.2011.5.25.177` / `1.3.6.1.4.1.2011.5.25.38`. This does not mean whole-device collection failed.

### High-speed traffic is zero or wrong

Confirm collection uses 64-bit `ifHCInOctets` / `ifHCOutOctets`. This template collects those counters through the shared IF-MIB table.
