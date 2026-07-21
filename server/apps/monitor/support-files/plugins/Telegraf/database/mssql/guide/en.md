# MSSQL Monitoring Guide

## Prerequisites

- The target SQL Server instance is up and reachable; default port is `1433` (named instances may use a dynamic port).
- The collector node can reach SQL Server (security groups / firewalls opened for `1433` or the actual port).
- A monitoring account with `VIEW SERVER STATE` permission is ready, along with its password.
- Host field accepts either an IP or a hostname; port defaults to `1433` and may be adjusted per instance.

## Recommended Permissions

The monitoring account must have at least `VIEW SERVER STATE` to read `sys.dm_*` dynamic management views. An administrator can grant it on the target instance:

```sql
USE master;
GRANT VIEW SERVER STATE TO monitor;
```

- Prefer a dedicated read-only monitoring account instead of `sa` or other high-privilege admin accounts.
- If mixed-mode authentication is enabled, make sure SQL Server authentication is allowed and the login is enabled.
- The template uses `encrypt=disable` by default; no extra certificate is required.

## Setup Steps

1. Verify connectivity from the collector node to the target SQL Server (use the pre-check command below).
2. Fill in username, password, host, port, and interval (default `60s`) on the configure page.
3. Add rows in the monitored objects table for node, host, port, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

Validate connectivity and credentials from the collector node with `sqlcmd`:

```bash
sqlcmd -S <host>,<port> -U <user> -P '<password>' -Q "SELECT @@VERSION"
```

The endpoint is basically healthy when:

- The command returns no authentication error and outputs the `SELECT @@VERSION` result (containing the SQL Server version).
- For a named instance, connect using `-S <host>\<instance_name>`.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | Yes | SQL Server login, e.g. `monitor` |
| Password | Yes | Password for the login |
| Host | Yes | SQL Server address (IP or hostname) |
| Port | Yes | SQL Server port, default `1433` |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform; auto-derived as `host:port` by default |
| Group | No | Organization group for ownership / permission |

## Troubleshooting

### 1. No data after saving

- Re-run the `sqlcmd` check from the collector node to confirm host, port, and credentials work.
- Confirm port `1433` (or the actual port) is open in security groups / firewalls.
- Wait for at least one collection interval before checking.
- Check whether Telegraf / collection tasks are healthy on the node and whether the `sqlserver` input reports errors.

### 2. Authentication failures (Login failed)

- Confirm SQL Server is configured for SQL Server authentication (mixed mode).
- Check username / password for accidental spaces; quoting `-P '<password>'` avoids shell escaping issues.
- Confirm the account has `VIEW SERVER STATE`.
- Make sure the account is not locked or disabled and the password has not expired.

### 3. Partial missing metrics or insufficient permissions

- The Telegraf `sqlserver` input relies on `sys.dm_*` views; insufficient permissions can yield successful login but missing metrics.
- Some metrics (availability groups, replication states) require additional permissions or AlwaysOn to be enabled; grant `VIEW SERVER STATE` and relevant DMV rights as needed.
- If schemas or column names differ, verify the SQL Server version is compatible with the installed Telegraf `sqlserver` input plugin.

### 4. Named instances or dynamic ports

- Named SQL Server instances often use dynamic ports; fix the TCP port on the instance or rely on the SQL Server Browser (UDP `1434`).
- If the collector node cannot reach SQL Server Browser, explicitly specify the actual TCP port for the named instance.
- The connection string defaults to `encrypt=disable`; if the target enforces encryption, update the template accordingly.