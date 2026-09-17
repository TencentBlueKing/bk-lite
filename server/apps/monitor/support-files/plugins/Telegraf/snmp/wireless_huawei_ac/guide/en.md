# Huawei WLAN AC SNMP Access Guide

This plugin uses Telegraf `inputs.snmp` on a selected node to collect Huawei WLAN controller (AC) health, access-point, radio, and uplink interface metrics.

## Prerequisites

- The selected node can reach the target device SNMP port (default `161/UDP`).
- SNMPv2c or SNMPv3 is enabled with read-only access.
- SNMPv3 (auth and privacy) is preferred. For v2c, put the community string only in the dedicated form field.
- The device should expose IF-MIB, entity health objects, and the wireless-controller objects declared by this template. Missing tables on some models or views do not block the remaining metrics.

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

`sysUpTime` (`1.3.6.1.2.1.1.3.0`) should return TimeTicks. `sysObjectID` (`1.3.6.1.2.1.1.2.0`) on Huawei WLAN AC devices usually belongs to the `1.3.6.1.4.1.2011.2.240` family.

## Form fields

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| IP | yes | none | Device management address. Not editable after create. |
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
- `device_cpu_usage` and `device_memory_usage` have entity-dimension readings.
- Chassis power shows `device_power_used` / `device_power_total` in watts (`hwDevicePowerInfoUsedPower` / `hwDevicePowerInfoTotalPower`). Invalid samples (`-1` or empty) are dropped.
- Fan-equipped models show `device_fan_state` / `device_fan_speed_pct` (percent of full speed), indexed by fan slot and serial number. Fanless SKUs may return an empty fan table.
- `wlan_cur_joint_ap_num` and `wlan_cur_assoc_sta_num` roughly match the site.
- `interface_ifHCInOctets` / `interface_ifHCOutOctets` show rates on the uplink.
- Optical DDM series (`optical_temp_c`, `optical_voltage_mV`, `optical_bias_uA`, `optical_rx_dbm`, `optical_tx_dbm`) appear when transceivers are present.

## Troubleshooting

### Only uptime and interfaces, no CPU or memory

The SNMP view may not authorize entity health objects. Confirm the read-only view includes `1.3.6.1.4.1.2011.5.25.31`.

### No chassis used/total power metrics

Confirm the view includes `1.3.6.1.4.1.2011.5.25.31.3`. These scalars are watts (`device_power_used` / `device_power_total`). Missing chassis power does not mean entity CPU/memory or IF-MIB collection failed.

### No fan speed or fan state

An empty `hwFanStatusTable` is expected on fanless SKUs and is not a collection failure. On fan-equipped models, confirm the view includes `1.3.6.1.4.1.2011.5.25.31.1.1.10`. Fan speed is a percent of full speed (`device_fan_speed_pct`), not RPM. Invalid samples (`-1` or empty) are dropped.

### No AP, station, or radio data

Wireless objects are unauthorized, or the model does not expose those scalars or tables. Confirm the read-only view includes `1.3.6.1.4.1.2011.6.139`. This does not mean whole-device collection failed.

### High-speed traffic is zero or inaccurate

Confirm collection uses 64-bit `ifHCInOctets` / `ifHCOutOctets`. This template collects those counters through the shared IF-MIB table.

### Two STA count series disagree

`wlan_cur_assoc_sta_num` (`hwWlanCurAssocStaNum`) is the current associated session count. `wlan_sta_cur_num` (`hwWlanStaCurNum`) is the controller's current STA object count. They are different counters and may disagree across software versions or SNMP views. Compare associated count with the license `wlan_access_max_sta_number` for capacity; do not reuse one threshold on both series. Auth-success `wlan_cur_auth_success_sta_num` is a third series; a growing gap versus associated count usually means authentication failures.

### Global wireless speed unit

`wlan_global_up_speed` / `wlan_global_down_speed` (`hwWlanGlobalUpSpeed` / `hwWlanGlobalDownSpeed`) are collected in Kbps as defined by the MIB. The platform unit is `kbitps`; there is no conversion to bit/s.

### No optical DDM series

Empty `hwOpticalModuleInfoTable` is expected when the chassis has no optical modules. Invalid readings `2147483647` are dropped. Rx/Tx power is stored as dBm×100; the query divides by 100 to display dBm. Voltage is millivolts and the query divides by 1000 to display volts.
