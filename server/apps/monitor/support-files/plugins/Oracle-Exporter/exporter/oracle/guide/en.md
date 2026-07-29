# Oracle Monitoring Guide

This capability runs Oracle-Exporter on the selected node, and Telegraf scrapes its local `/metrics` endpoint.

## Prerequisites

- The collector node can reach the Oracle database host and actual listener port.
- Prepare a dedicated monitoring account that can log in to the specified `service_name` and read the dynamic performance views queried by the exporter, such as `v$session`, `v$sysstat`, and `v$database`.
- The page requires an Oracle `service_name`, not a SID.
- Reserve an unused exporter listen port on the collector node. It is separate from the Oracle database port.
- The current page has no fields for a SID, TCPS, Wallet, or a custom connection string.

## Setup Steps

1. From the actual collector node, validate the database host, port, `service_name`, and monitoring account.
2. Enter the username, password, service name, database host, and database port.
3. Enter an unused exporter listen port and the interval (default `60` seconds).
4. In the monitored objects table, select the node and enter the listen port, host, port, instance name, and optional group.
5. Save the configuration and wait for at least one collection interval.

## Pre-checks

Use `sqlplus` to connect to the service. The command prompts for the password, so no password is placed on the command line:

```bash
sqlplus monitor@//db.example.com:1521/ORCLPDB1
```

After login, confirm that the account can query the required dynamic performance views. You can also check the TCP port first:

```bash
nc -vz db.example.com 1521
```

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | Yes | Oracle monitoring account. |
| Password | Yes | Password for the account. |
| Service Name | Yes | Oracle `service_name`, not a SID. |
| Listen Port | Yes | Local port where Oracle-Exporter exposes `/metrics`. |
| Host | Yes | Oracle database host. |
| Port | Yes | Actual Oracle database listener port. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that runs Oracle-Exporter. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, check the local endpoint with the configured listen port, for example:

```bash
curl --fail --silent --show-error "http://127.0.0.1:9161/metrics"
```

Then confirm that these metrics are queryable in the platform:

- `oracledb_up_gauge`
- `oracledb_uptime_seconds_gauge`
- `oracledb_sessions_value_gauge`
- `oracledb_tablespace_used_percent_gauge`

## Troubleshooting

### Login fails

- Distinguish `service_name` from SID, and check the host, database port, and account state.
- Validate through the interactive password prompt to avoid a false result caused by shell escaping.

### The exporter's local endpoint is unavailable

- Do not enter the database port in the Listen Port field.
- Check for a local port conflict and inspect the Oracle-Exporter process arguments and logs.

### Only some metrics are present

- A successful login does not prove access to every dynamic performance view. Use the actual query error in the exporter log to grant the minimum required read access.
- Tablespace, session, and resource metrics depend on different views; verify both privileges and whether the target instance provides the data.
