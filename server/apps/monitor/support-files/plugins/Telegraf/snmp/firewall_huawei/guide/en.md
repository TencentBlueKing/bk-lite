# Huawei USG Firewall SNMP Guide

This plugin monitors Huawei USG firewall health and session/throughput: per-entity CPU, memory, temperature, and voltage; current sessions, new sessions, session-create rate, half-open sessions, TCP/UDP/ICMP session counts; and device forwarding throughput. USG9500 also reports per-SPU CPU usage when those boards are present. Access stays on the existing Firewall object; USG6000E, USG9500, and HiSecEngine USG do not need a new monitor object. Interface metrics use the platform built-in IF-MIB; this plugin does not extend ifTable / ifXTable.

## Supported models

One plugin covers the following Huawei firewall families. Box, chassis, and HiSecEngine appliances all use this object; no extra monitor objects are required.

- USG6000 series
- USG6000E series
- USG9500 (chassis; SPU CPU usage is present only when SPU boards are installed)
- HiSecEngine USG

A box without SPU boards simply returns an empty SPU table. Missing private objects on a given software version do not block the rest of the template.

## Prerequisites

- The selected node can reach the device SNMP port (default `161/UDP`).
- SNMPv2c or SNMPv3 is enabled with read-only access.
- SNMPv3 with auth and privacy is recommended. For v2c, enter the community only in the dedicated form field.
- The read-only view should authorize standard IF-MIB plus `1.3.6.1.4.1.2011.5.25.31` (entity health), `1.3.6.1.4.1.2011.6.122.69` (current/new sessions), and `1.3.6.1.4.1.2011.6.122.15` (session statistics, device throughput, and SPU usage).

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
snmpget -v2c -c "$SNMP_COMMUNITY" "$TARGET" 1.3.6.1.4.1.2011.6.122.69.1.1.2.0
snmpget -v2c -c "$SNMP_COMMUNITY" "$TARGET" 1.3.6.1.4.1.2011.6.122.15.6.5.0
```

`sysUpTime` (`1.3.6.1.2.1.1.3.0`) should return TimeTicks. `sysObjectID` (`1.3.6.1.2.1.1.2.0`) belongs to enterprise `2011` on Huawei USG. Current concurrent sessions (`…122.69.1.1.2`) or 64-bit throughput (`…122.15.6.5.0`) may be absent on some releases; probe `…122.15.1.2.1.4.0` (total sessions) or `…122.15.6.2.0` (device sessions) next.

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
- `firewall_active_sessions` or `firewall_device_sessions` / `firewall_total_sessions` reports session count.
- `firewall_session_rate` or `firewall_device_session_rate` reports session-create rate.
- `firewall_throughput` (64-bit) reports device forwarding throughput; use `firewall_throughput32` when only the 32-bit object exists.
- On USG9500 with SPU boards, `firewall_spu_usage` has per-slot and per-CPU readings. An empty SPU table on a box without those boards does not mean whole-device collection failed.

## Troubleshooting

### Only uptime and interfaces, no CPU or memory

The SNMP view may not authorize entity-health objects. Confirm the read-only view includes `1.3.6.1.4.1.2011.5.25.31`.

### CPU is present, but no sessions or throughput

Confirm the read-only view includes `1.3.6.1.4.1.2011.6.122.69` and `1.3.6.1.4.1.2011.6.122.15`. Different series may implement only one of these trees. Empty objects do not block the rest of the template.

### No SPU CPU usage

Box USG6000 / USG6000E / HiSecEngine devices usually have no SPU table. Only chassis such as USG9500 return `hwSecStatUsage` when SPU boards are installed. Indexing uses the performance-table slot and CPU columns; do not join them to ENTITY names.

### High-speed traffic is zero or wrong

Interface traffic uses the platform built-in IF-MIB 64-bit `ifHCInOctets` / `ifHCOutOctets` pair. This plugin does not add further ifXTable counters. Device forwarding throughput is `firewall_throughput`, not interface octets.
