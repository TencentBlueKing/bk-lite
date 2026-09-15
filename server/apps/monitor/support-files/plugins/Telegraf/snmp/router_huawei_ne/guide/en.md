# Huawei NetEngine Router SNMP Guide

This plugin uses Telegraf `inputs.snmp` on the selected node to collect Huawei NetEngine (NE) router health, interface traffic, BGP, and BFD metrics.

## Prerequisites

- The selected node can reach the device SNMP port (default `161/UDP`).
- SNMPv2c or SNMPv3 is enabled with read-only access.
- SNMPv3 with auth and privacy is recommended. For v2c, enter the community only in the dedicated form field.
- The device must expose standard IF-MIB plus the Huawei private objects declared by this template. Interface counters use the built-in IF-MIB table; this plugin does not expand IF-MIB. Some models or restricted views omit individual tables; missing objects do not block the rest of the metrics.

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

`sysUpTime` (`1.3.6.1.2.1.1.3.0`) should return TimeTicks. `sysObjectID` (`1.3.6.1.2.1.1.2.0`) identifies the chassis with this dictionary. Interface counters use the built-in IF-MIB table; this plugin does not expand IF-MIB.

| sysObjectID | Display name |
| --- | --- |
| `1.3.6.1.4.1.2011.2.62`, `1.3.6.1.4.1.2011.2.297` | NetEngine NE40E family |
| `1.3.6.1.4.1.2011.2.315` | NetEngine 9000 family |
| `1.3.6.1.4.1.2011.2.315.2` | `ne9000SysOid` |
| `1.3.6.1.4.1.2011.2.315.2.1` | NetEngine 9000-20 |
| `1.3.6.1.4.1.2011.2.315.2.2` | NetEngine 9000-8 |
| `1.3.6.1.4.1.2011.2.315.2.3` | NetEngine 9000-8 Admin |
| `1.3.6.1.4.1.2011.2.315.2.4` | NetEngine 9000-8 LS |
| `1.3.6.1.4.1.2011.2.315.2.5` | NetEngine 9000-20 Admin |
| `1.3.6.1.4.1.2011.2.315.2.6` | NetEngine 9000-20 LS |
| `1.3.6.1.4.1.2011.2.360` | NetEngine 8000 family |
| `1.3.6.1.4.1.2011.2.360.1` | `NetEngine8000SysOid` |
| `1.3.6.1.4.1.2011.2.360.1.1` | NetEngine 8000 X4 |
| `1.3.6.1.4.1.2011.2.360.1.3` | NetEngine 8000 X8 |
| `1.3.6.1.4.1.2011.2.360.1.27` | NetEngine 8000 X16 |
| `1.3.6.1.4.1.2011.2.360.1.5` | NetEngine 8000 F1A |
| `1.3.6.1.4.1.2011.2.360.1.39` | NetEngine 8000 F2A-8K36H |
| `1.3.6.1.4.1.2011.2.360.1.23` | NetEngine 8000 F8 |
| `1.3.6.1.4.1.2011.2.360.1.7` | NetEngine 8000 M14 |
| `1.3.6.1.4.1.2011.2.360.1.9` | NetEngine 8000 M8 |
| `1.3.6.1.4.1.2011.2.360.1.13` | NetEngine 8000 M6 |
| `1.3.6.1.4.1.2011.2.360.1.55` | NetEngine 8000 M4 |
| `1.3.6.1.4.1.2011.2.360.1.11` | NetEngine 8000 M1A |
| `1.3.6.1.4.1.2011.2.360.1.25` | NetEngine 8000 M1B |
| `1.3.6.1.4.1.2011.2.360.1.29` | NetEngine 8000 M1C |
| `1.3.6.1.4.1.2011.2.360.1.21` | NetEngine 8000 M1D |
| `1.3.6.1.4.1.2011.2.360.1.35` | NetEngine 8000E X4 |
| `1.3.6.1.4.1.2011.2.360.1.31` | NetEngine 8000E X8 |
| `1.3.6.1.4.1.2011.2.360.1.43` | NetEngine 8000E X16 |
| `1.3.6.1.4.1.2011.2.360.1.49` | NetEngine 8000E F8 |
| `1.3.6.1.4.1.2011.2.360.1.47` | NetEngine 8000E M14 |
| `1.3.6.1.4.1.2011.2.360.1.45` | NetEngine 8000E M8 |
| `1.3.6.1.4.1.2011.2.360.1.57` | NetEngine 8000E M4 |

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
- When BFD is enabled, `device_bfd_sess_state` should be up(3) (HUAWEI-BFD-MIB: adminDown(0)/down(1)/init(2)/up(3)).

Identity tags `hwDeviceEsn` and `hwProductName` are reported with the SNMP measurement so you can confirm the chassis.

## Troubleshooting

### Only uptime and interfaces, no CPU or memory

The SNMP view may not authorize entity-health objects. Confirm the read-only view includes `1.3.6.1.4.1.2011.5.25.31` and `1.3.6.1.4.1.2011.6.3`.

### No BGP or BFD data

The feature is disabled, no sessions exist, or the view does not authorize `1.3.6.1.4.1.2011.5.25.177` / `1.3.6.1.4.1.2011.5.25.38`. This does not mean whole-device collection failed.

### High-speed traffic is zero or wrong

Confirm collection uses 64-bit `ifHCInOctets` / `ifHCOutOctets`. This template collects those counters through the built-in IF-MIB table and does not expand IF-MIB.
