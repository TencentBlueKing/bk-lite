# PostgreSQL Monitoring Guide

This capability uses Telegraf `inputs.postgresql` to connect to a specified PostgreSQL host, port, and database.

## Prerequisites

- The collector node can reach the target PostgreSQL host and actual port.
- Prepare an account that can log in to the configured database and read the required statistics views. On PostgreSQL 10 and later, `pg_monitor` can be granted according to least privilege.
- The target `pg_hba.conf` allows this account to connect from the collector node.
- The page supports SSL modes `disable`, `prefer`, and `require`. Certificate paths are not supported; `verify-ca` and `verify-full` are unavailable in this template.
- The template always ignores `template0` and `template1`.

## Setup Steps

1. From the actual collector node, validate the target address, account, database name, SSL mode, and statistics-view permissions.
2. Enter the username, password, host, actual port, database name, SSL mode, and interval (default `60` seconds).
3. In the monitored objects table, select the node and enter the host, port, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

`--password` prompts for the password:

```bash
psql --host db.example.com --port 5432 --username monitor --dbname postgres --password --command "SELECT count(*) FROM pg_stat_database;"
```

The command must return a result without authentication, network, or statistics-view permission errors. If the target requires SSL, add the corresponding SSL parameters to the validation command.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | Yes | PostgreSQL monitoring account. |
| Password | Yes | Password for the account. |
| Host | Yes | PostgreSQL hostname or IP address without a scheme. |
| Port | Yes | Actual PostgreSQL listener port. |
| Database Name | Yes | Database used to establish the monitoring connection; default `postgres`. |
| SSL Mode | Yes | `disable` / `prefer` / `require`; default `disable`. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can reach PostgreSQL. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `postgresql_numbackends`
- `postgresql_xact_commit_rate`
- `postgresql_deadlocks_rate`
- `postgresql_cache_hit_ratio`

## Troubleshooting

### Authentication or the source address is rejected

- Check whether `pg_hba.conf` allows the collector source address, account, and target database.
- Check that the server's password-authentication mode matches the account configuration.

### Login succeeds but data is incomplete

- Confirm that the account can read the required `pg_stat_*` views. Use `pg_monitor` or equivalent least-privilege grants for the target version.
- `template0` and `template1` are explicitly ignored by the template and produce no data.

### The target enforces SSL

- Set SSL mode to `require` (or `prefer`). Certificate paths are not supported; targets that require `verify-ca` or `verify-full` cannot be integrated directly with this template.
