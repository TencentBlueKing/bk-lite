# Aruba AOS Wireless Controller SNMP Access Guide

This plugin uses Telegraf `inputs.snmp` on a selected node to collect Aruba AOS wireless controller health, access-point count, and associated station count.

## Prerequisites

- The selected node can reach the target device SNMP port (default `161/UDP`).
- SNMPv2c or SNMPv3 is enabled with read-only access.
- SNMPv3 (auth and privacy) is preferred. For v2c, put the community string only in the dedicated form field.
- This template is for Aruba AOS wireless controllers (enterprise `1.3.6.1.4.1.14823`). Do not use it for ArubaOS-CX switches (enterprise `1.3.6.1.4.1.47196`; use Switch Aruba SNMP) or Instant/IAP.
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

`sysUpTime` (`1.3.6.1.2.1.1.3.0`) should return TimeTicks. `sysObjectID` (`1.3.6.1.2.1.1.2.0`) on Aruba AOS wireless controllers usually belongs to the `1.3.6.1.4.1.14823` family, not the CX `1.3.6.1.4.1.47196` family.

Optionally confirm the controller CPU scalar:

```bash
snmpget -v2c -c "$SNMP_COMMUNITY" "$TARGET" 1.3.6.1.4.1.14823.2.2.1.2.1.30.0
```

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
- `device_cpu_usage` and `device_memory_usage` have readings (0-100 percent).
- `device_temperature_celsius` reports internal temperature.
- `wireless_ap_count` and `wireless_station_count` roughly match the site.

## Troubleshooting

### Only uptime, no CPU, memory, or temperature

The SNMP view may not authorize system-extension objects. Confirm the read-only view includes `1.3.6.1.4.1.14823.2.2.1.2` (WLSX-SYSTEMEXT). This does not mean whole-device collection failed.

### No AP or station data

Controller switch objects are unauthorized, or the target is not an AOS controller. Confirm the read-only view includes `1.3.6.1.4.1.14823.2.2.1.1.3` (WLSX-SWITCH count scalars). Instant/IAP and ArubaOS-CX switches are out of scope. This does not mean whole-device collection failed.

### The device is identified as an Aruba switch

ArubaOS-CX switches use enterprise `1.3.6.1.4.1.47196` and should use Switch Aruba SNMP (`snmp_aruba`). This plugin uses collect_type `snmp_aruba_wireless` for AOS controllers only and does not share CX discovery rules.
