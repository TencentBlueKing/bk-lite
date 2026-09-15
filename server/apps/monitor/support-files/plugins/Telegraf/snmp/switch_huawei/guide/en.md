# Huawei Switch SNMP Guide

This plugin uses Telegraf `inputs.snmp` on the selected node to collect Huawei campus, chassis, and CloudEngine switch health. Collection stays on the existing Switch / Network Device path (`snmp_huawei`). Interface counters remain the current IF-MIB 64-bit HC pair; this template does not add further IF-MIB objects.

## Supported models

One plugin covers the following Huawei switch families. Standalone boxes, iStack, and CSS chassis all use this object; no extra monitor objects are required.

- Campus and aggregation S-series: S5700, S6700, S7700, S8700, S9300
- Chassis campus / CSS: S9700, S12700, S12700E, S16700
- CloudEngine CE series, including SKUs such as CE6881 and CE5881

A device that does not enable stack or CSS simply returns empty stack/CSS tables. Missing private tables do not block CPU, memory, fan, PSU, optical, or interface metrics.

## Prerequisites

- The selected node can reach the device SNMP port (default `161/UDP`).
- SNMPv2c or SNMPv3 is enabled with read-only access.
- SNMPv3 with auth and privacy is recommended. For v2c, enter the community only in the dedicated form field.
- The read-only view should authorize standard IF-MIB plus `1.3.6.1.4.1.2011.5.25.31` (entity health, PSU, optical DDM) and `1.3.6.1.4.1.2011.5.25.183` (stack/CSS).

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

`sysUpTime` (`1.3.6.1.2.1.1.3.0`) should return TimeTicks. `sysObjectID` (`1.3.6.1.2.1.1.2.0`) belongs to enterprise `2011` on Huawei switches.

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
- `device_psu_state` reports each power supply (`hwEntityPwrState`).
- Optical DDM shows `device_optical_rx_power` / `device_optical_tx_power` plus temperature, voltage, and bias when modules are present.
- When iStack or CE stacking is enabled, `device_stack_member_role`, `device_stack_port_state`, and `device_stack_link_state` are populated.
- When CSS is enabled (S12700/S9700-class), `device_css_member_role`, `device_css_port_state`, and `device_css_link_state` are populated.

## Troubleshooting

### Only uptime and interfaces, no CPU or memory

The SNMP view may not authorize entity-health objects. Confirm the read-only view includes `1.3.6.1.4.1.2011.5.25.31`.

### No PSU or optical DDM beyond Rx/Tx

Confirm the view includes `hwEntityPwrState` / `hwEntityPwrPresent` and `hwOpticalModuleInfoTable`. Empty slots and missing modules produce no series.

### No stack or CSS metrics

Stack/CSS is disabled, the device is standalone, or the view does not authorize `1.3.6.1.4.1.2011.5.25.183`. This does not mean whole-device collection failed.

### High-speed traffic is zero or wrong

Confirm collection uses the existing 64-bit `ifHCInOctets` / `ifHCOutOctets` pair. This template does not add further IF-MIB counters.
