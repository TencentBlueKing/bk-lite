# Huawei Switch SNMP Guide

This plugin monitors Huawei campus, chassis, and CloudEngine switch health: per-entity CPU, memory, temperature, and voltage (millivolts converted to volts); fans (state, presence, and speed as a percent of full speed); chassis used/total power and per-entity board power in watts; chassis and board energy in milliwatts; power-supply presence, operating state, current in milliamperes, voltage in millivolts, and module rated power in watts; optical-module DDM; stack/CSS; and, when enabled, M-LAG member heartbeat and member-port state. Access stays on the existing Switch object; S12700H and S16700 do not need a new monitor object.

## Supported models

One plugin covers the following Huawei switch families. Standalone boxes, iStack, CSS chassis, and M-LAG dual-active pairs all use this object; no extra monitor objects are required.

- Campus and aggregation S-series: S5700, S6700, S7700, S8700 (S8704/S8706/S8710), S9300
- Chassis campus / CSS: S9700, S12700, S12700E, S12700H, S16700 (S16704/S16708)
- CloudEngine CE series, including CE16800-X4/X8/X16, CE16804/CE16808/CE16816, and SKUs such as CE6881 and CE5881

S12700H and S16700 are V600-generation chassis and still use this plugin and Switch object. A device that does not enable stack, CSS, or M-LAG simply returns empty tables. Missing private tables do not block CPU, memory, fan, PSU, or optical metrics. Stack/CSS link-up/down objects and M-LAG consistency checks are traps, not pollable tables; use stack/CSS/M-LAG port status and member heartbeat for link health.

## Prerequisites

- The selected node can reach the device SNMP port (default `161/UDP`).
- SNMPv2c or SNMPv3 is enabled with read-only access.
- SNMPv3 with auth and privacy is recommended. For v2c, enter the community only in the dedicated form field.
- The read-only view should authorize standard IF-MIB plus `1.3.6.1.4.1.2011.5.25.31` (entity health including voltage and board power, fan speed/presence, chassis power, PSU presence/state/electrical, optical DDM), `1.3.6.1.4.1.2011.6.157` (chassis and board energy in milliwatts), `1.3.6.1.4.1.2011.5.25.183` (stack object `183.1` and CSS object `183.3`), and `1.3.6.1.4.1.2011.5.25.178.8` (M-LAG member ports and heartbeat).

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

## sysObjectID model dictionary

Chassis identity only. No new Switch object. No extra private metrics.

| sysObjectID | Display name |
| --- | --- |
| `1.3.6.1.4.1.2011.2.239` | CloudEngine CE / dcswitch family |
| `1.3.6.1.4.1.2011.2.239.58` | CE16804 |
| `1.3.6.1.4.1.2011.2.239.59` | CE16808 |
| `1.3.6.1.4.1.2011.2.239.60` | CE16816 |
| `1.3.6.1.4.1.2011.2.239.120` | CE16800-X4 |
| `1.3.6.1.4.1.2011.2.239.121` | CE16800-X8 |
| `1.3.6.1.4.1.2011.2.239.122` | CE16800-X16 |
| `1.3.6.1.4.1.2011.2.383` | S8700 |
| `1.3.6.1.4.1.2011.2.383.3` | S8704 |
| `1.3.6.1.4.1.2011.2.383.1` | S8706 |
| `1.3.6.1.4.1.2011.2.383.2` | S8710 |
| `1.3.6.1.4.1.2011.2.409` | S16700 |
| `1.3.6.1.4.1.2011.2.409.1` | S16704 |
| `1.3.6.1.4.1.2011.2.409.2` | S16708 |

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
- `device_voltage_volts` reports per-entity input voltage (`hwEntityVoltage`, millivolts converted to volts; dimension `descr` is `entPhysicalName`). Distinct from optical-module `device_optical_voltage` (`hwEntityOpticalVoltage`).
- `device_fan_state` reports each cooling fan (`hwEntityFanState`: normal/abnormal). `device_fan_speed` is a percent of full speed on present fans; empty slots show on `device_fan_present`.
- `device_power_used` / `device_power_total` report chassis used and total power in watts (`hwDevicePowerInfoUsedPower` / `hwDevicePowerInfoTotalPower`).
- `device_entity_board_power` reports per-entity board power in watts (`hwEntityBoardPower`; dimension `descr` is `entPhysicalName`). Distinct from ENERGYMNGT milliwatt series `device_board_current_power_mw` / `device_board_rated_power_mw`.
- `device_energy_current_power_mw` / `device_energy_average_power_mw` / `device_energy_rated_power_mw` report chassis energy in milliwatts (`hwCurrentPower` / `hwAveragePower` / `hwRatedPower`; divide by 1000 for watts). Board series use `device_board_current_power_mw` / `device_board_rated_power_mw` with dimension `hwBoardName`.
- `device_psu_state` reports each installed power supply (`hwEntityPwrState`: supply/notSupply/sleep/unknown). Empty slots show on `device_psu_present`. Present modules also report `device_psu_current_mA` (milliamperes), `device_psu_voltage_mV` (millivolts), and `device_psu_rated_power_watts` (module rated watts, not chassis used power).
- Optical DDM shows `device_optical_rx_power` / `device_optical_tx_power` (µW converted to dBm) plus temperature (°C), voltage (mV→V), and bias (µA) when modules are present. Invalid sentinel `2147483647` is dropped.
- When iStack or CE stacking is enabled, `device_stack_member_role` (`hwMemberStackRole`) and `device_stack_port_state` (`hwStackPortStatus` up=1/down=2) are populated.
- When CSS is enabled (S12700/S12700H/S9700-class), `device_css_member_role` (`hwCssMemberRole`) and `device_css_port_state` (`hwCssPortOperStatus` down=0/up=1) are populated.
- When M-LAG is enabled, `device_mlag_port_state` (`hwPortState` down=0/up=1) and `device_mlag_member_heartbeat` (`hwLocalHeartBeatState` ok=1/lost=2) are populated.

## Troubleshooting

### Only uptime and interfaces, no CPU or memory

The SNMP view may not authorize entity-health objects. Confirm the read-only view includes `1.3.6.1.4.1.2011.5.25.31`.

### No PSU or optical DDM beyond Rx/Tx

Confirm the view includes `hwEntityPwrState` / `hwEntityPwrPresent` / `hwEntityPwrCurrent` / `hwEntityPwrVoltage` / `hwEntityPwrPower` and `hwOpticalModuleInfoTable`. Empty slots and missing modules produce no series. PSU current is milliamperes and voltage is millivolts.

### No stack, CSS, or M-LAG metrics

Stack/CSS/M-LAG is disabled, the device is standalone, or the view does not authorize the matching objects. iStack/CE uses `183.1.20` / `183.1.21`; CSS uses `183.3.2` / `183.3.4`; M-LAG uses `178.8.1.4` / `178.8.1.5`. Objects under `183.1.4`/`183.1.5`/`183.1.6`/`183.1.22` and M-LAG consistency checks are scalars or traps, not member/port/link tables. This does not mean whole-device collection failed.

### No milliwatt energy metrics

Confirm the view includes `1.3.6.1.4.1.2011.6.157`. These series are milliwatts and coexist with `device_power_used` / `device_power_total` (watts). Missing energy tables do not mean watts chassis power failed.

### High-speed traffic is zero or wrong

Confirm collection uses the existing 64-bit `ifHCInOctets` / `ifHCOutOctets` pair. This template does not add further IF-MIB counters.
