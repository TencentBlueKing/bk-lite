# Ruckus ZoneDirector SNMP Access Guide

This plugin uses Telegraf `inputs.snmp` on a selected node to collect Ruckus ZoneDirector wireless controller health, access-point counts, client-station count, and licensed AP count.

## Prerequisites

- The selected node can reach the target device SNMP port (default `161/UDP`).
- SNMPv2c or SNMPv3 is enabled with read-only access.
- SNMPv3 (auth and privacy) is preferred. For v2c, put the community string only in the dedicated form field.
- This template is for ZoneDirector. SmartZone/SCG and Unleashed use different OID trees and must not share this instance.
- The device should expose the controller objects declared by this template. Missing scalars on some models or views do not block the remaining metrics.

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

`sysUpTime` (`1.3.6.1.2.1.1.3.0`) should return TimeTicks. `sysObjectID` (`1.3.6.1.2.1.1.2.0`) on Ruckus ZoneDirector devices usually belongs to the `1.3.6.1.4.1.25053` family.

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
- `wireless_ap_count` and `wireless_client_count` roughly match the site.
- `wireless_licensed_ap_count` can be compared against the license ceiling.

## Troubleshooting

### Only uptime, no CPU or memory

The SNMP view may not authorize system or ZoneDirector health objects. Confirm the read-only view includes `1.3.6.1.4.1.25053.1.1.11` (RUCKUS-SYSTEM) or `1.3.6.1.4.1.25053.1.2.1` (ZoneDirector). Both trees map to the same CPU/memory metrics; missing one tree does not mean whole-device collection failed.

### No AP or client data

ZoneDirector objects are unauthorized, or the target is not a ZoneDirector. Confirm the read-only view includes `1.3.6.1.4.1.25053.1.2.1`. SmartZone/SCG and Unleashed are out of scope for this template; create a separate instance for those products. This does not mean whole-device collection failed.

### Associated, registered, and licensed AP counts disagree

`wireless_ap_count` (`ruckusZDSystemNumAP`) is the current associated AP count. `wireless_registered_ap_count` (`ruckusZDSystemNumRegisteredAP`) is the registered AP count. `wireless_licensed_ap_count` (`ruckusZDSystemLicensedAPs`) is the licensed AP count. They are different counters and may disagree across software versions or SNMP views. Use associated count for live scale and licensed count for capacity; do not reuse one threshold on all three series.
