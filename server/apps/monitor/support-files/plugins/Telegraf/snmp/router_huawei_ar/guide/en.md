# Huawei AR Router SNMP Guide

This plugin uses Telegraf `inputs.snmp` on the selected node to collect Huawei AR-series router health and interface traffic.

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

`sysUpTime` (`1.3.6.1.2.1.1.3.0`) should return TimeTicks. On AR routers, `sysObjectID` (`1.3.6.1.2.1.1.2.0`) belongs to `1.3.6.1.4.1.2011.2.224` (hwAR).

## sysObjectID model dictionary

Root `1.3.6.1.4.1.2011.2.224`. Leaf numbers below are the product identity used by this plugin.

| Leaf | Display name |
| --- | --- |
| 340 | AR8140-12G10XG |
| 341 | AR8140-T-12G10XG |
| 349 | AR720 |
| 350 | AR730 |
| 363 | AR6710-L50T2X4 |
| 364 | AR6710-L50T2X4-T |
| 365 | AR6710-L26T2X4 |
| 366 | AR6710-L26T2X4-T |
| 368 | AR5710-H8T2TS1 |
| 369 | AR5710-H8T2TS1-T |
| 370 | AR6710-L8T3TS1X2 |
| 371 | AR6710-L8T3TS1X2-T |
| 378 | AR8700-8 |
| 379 | AR6510-L11T1X2 |
| 380 | AR6510-L5T4S4 |
| 381 | AR5510-H8P2TW1 |
| 382 | AR5510-H10T1 |
| 383 | AR5510-L5T-LTE4EA |
| 384 | AR5510-L5T |
| 385 | AR6500-10 |

Other leaves under the same root remain AR-series devices. This pass does not add private metrics or a new AR monitor object.

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
- `device_cpu_usage` and `device_memory_usage` have readings.
- `interface_ifHCInOctets` / `interface_ifHCOutOctets` show rates on in-service ports.

Interface traffic uses the built-in IF-MIB table (`ifTable` / `ifXTable`). This template does not expand IF objects such as extra `ifHC*` or `ifOperStatus` leaves.

## Troubleshooting

### Only uptime and interfaces, no CPU or memory

The SNMP view may not authorize entity-health objects. Confirm the read-only view includes `1.3.6.1.4.1.2011.5.25.31`.

### High-speed traffic is zero or wrong

Confirm collection uses 64-bit `ifHCInOctets` / `ifHCOutOctets` from the built-in IF-MIB table.

### sysObjectID is not in the table above

The device is still an AR-series router if the OID is under `1.3.6.1.4.1.2011.2.224`. Collection does not depend on a listed leaf; the dictionary is for model recognition only.
