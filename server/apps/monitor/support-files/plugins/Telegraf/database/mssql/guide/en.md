# MSSQL Monitoring Guide

This capability uses Telegraf `inputs.sqlserver` to connect to a specified host and TCP port with a SQL Server account.

## Prerequisites

- The collector node can reach the actual SQL Server TCP host and port.
- Prepare an account that can log in to the `master` database and read the required dynamic management views; `VIEW SERVER STATE` is normally required.
- The current page accepts a host and TCP port only. For a named instance, determine and fix its actual TCP port instead of entering instance-name syntax.
- The connection always uses `encrypt=disable`; the page has no encryption or certificate fields.
- The template explicitly excludes `SQLServerAvailabilityReplicaStates` and `SQLServerDatabaseReplicaStates`, so the corresponding replica-state data is not collected.

## Setup Steps

1. From the actual collector node, validate the target TCP port and monitoring account.
2. Enter the username, password, host, actual TCP port, and interval (default `60` seconds).
3. In the monitored objects table, select the node and enter the host, port, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

Use a `tcp:` address and fixed port. With `-P` omitted, `sqlcmd` prompts for the password:

```bash
sqlcmd -S tcp:sql.example.com,1433 -U monitor -Q "SELECT @@VERSION"
```

The command must return the version. Enter the TCP host and actual port in their separate page fields.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | Yes | SQL Server login. |
| Password | Yes | Password for the login. |
| Host | Yes | SQL Server hostname or IP address, without an instance name. |
| Port | Yes | Actual TCP port. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can reach the target TCP port. |
| Instance Name | Yes | Display name in the platform; it can be derived from host and port. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `sqlserver_cpu_sqlserver_process_cpu_avg`
- `sqlserver_server_properties_uptime`
- `sqlserver_memory_total_server_memory_kb`
- `sqlserver_page_life_expectancy`

## Troubleshooting

### A named instance cannot be reached

- Determine the named instance's actual TCP port on SQL Server, then enter the host and port separately.
- The current connection does not use SQL Server Browser to resolve an instance name.

### Login succeeds but data is incomplete

- Check the account's `VIEW SERVER STATE` access to dynamic management views.
- The two replica-state queries are explicitly excluded by the template, so their absence is a current configuration boundary.

### The target requires encryption

- The template always disables encryption and the page has no certificate fields. A target that enforces encryption cannot be integrated directly.
