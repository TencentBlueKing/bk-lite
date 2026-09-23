# Cisco Wireless Controller SNMP Setup Guide

This plugin uses Telegraf `inputs.snmp` to collect CPU, memory, and connected access-point count from Cisco AireOS WLC and Catalyst 9800 wireless LAN controllers.

## Prerequisites

- The selected node can reach the target device SNMP port (default `161/UDP`).
- SNMPv2c or SNMPv3 is enabled with read-only access.
- SNMPv3 (auth+priv) is recommended. For v2c, enter the community only in the dedicated form field.
- AireOS WLC uses Airespace controller scalars. Catalyst 9800 falls back to CISCO-PROCESS tables when those scalars are absent. Do not use this instance for Cisco devices in a switch or router role.
- The target must expose the controller objects declared by this template. Missing objects on some models or views do not block the remaining metrics.

## Setup steps

1. Confirm SNMP reachability from the node to the device IP (see “Pre-check”).
2. Choose the SNMP version. For v2c fill in the community; for v3 fill in security name, level, auth/priv protocols and passwords.
3. Adjust port, timeout, and interval as needed. Defaults are port `161`, timeout `10` seconds, interval `60` seconds.
4. In the monitor object table, choose a node and fill in device IP, instance name, and group.
5. Save and wait for at least one collection interval.

## Pre-check

Replace `TARGET` with the device IP and use a read-only community (use the matching v3 probe in v3 environments):

```bash
TARGET=192.0.2.10
snmpget -v2c -c "$SNMP_COMMUNITY" "$TARGET" 1.3.6.1.2.1.1.3.0
snmpget -v2c -c "$SNMP_COMMUNITY" "$TARGET" 1.3.6.1.2.1.1.2.0
```

`sysUpTime` (`1.3.6.1.2.1.1.3.0`) should return TimeTicks. `sysObjectID` (`1.3.6.1.2.1.1.2.0`) on Cisco wireless controllers usually belongs to the `1.3.6.1.4.1.9` or `1.3.6.1.4.1.14179` family.

On AireOS, also probe the controller CPU scalar `1.3.6.1.4.1.14179.1.1.5.1.0`. On Catalyst 9800, probe `1.3.6.1.4.1.9.9.109.1.1.1.1.8` (table column; do not append `.0`).

## Form fields

| Field | Required | Default | Description |
| --- | --- | --- | --- |
| IP | yes | none | Device management address. |
| Port | yes | `161` | SNMP UDP port. |
| Version | yes | v2c | `v2c` or `v3`. |
| Community | required for v2c | `public` | Read-only community. |
