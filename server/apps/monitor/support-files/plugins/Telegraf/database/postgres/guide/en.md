# PostgreSQL Monitoring Guide

This capability uses Telegraf `inputs.postgresql` to connect to a specified PostgreSQL host and port. The database is fixed to `postgres`.

## Prerequisites

- The collector node can reach the target PostgreSQL host and actual port.
- Prepare an account that can log in to the `postgres` database and read the required statistics views. On PostgreSQL 10 and later, `pg_monitor` can be granted according to least privilege.
- The target `pg_hba.conf` allows this account to connect from the collector node.
- The current template always uses `sslmode=disable`. The page has no database-name, SSL, or certificate fields.
- The template always ignores `template0` and `template1`.

## Setup Steps

1. From the actual collector node, validate the target address, account, `postgres` database, and statistics-view permissions.
2. Enter the username, password, host, actual port, and interval (default `60` seconds).
3. In the monitored objects table, select the node and enter the host, port, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

`--password` prompts for the password:

```bash
psql --host db.example.com --port 5432 --username monitor --dbname postgres --password --command "SELECT count(*) FROM pg_stat_database;"
```

The command must return a result without authentication, network, or statistics-view permission errors.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | Yes | PostgreSQL monitoring account. |
| Password | Yes | Password for the account. |
| Host | Yes | PostgreSQL hostname or IP address without a scheme. |
| Port | Yes | Actual PostgreSQL listener port. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can reach PostgreSQL. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `postgresql_numbackends`
- `postgresql_xact_commit_rate`
- `postgresql_deadlocks_rate`
- `postgresql_blks_hit_rate`

## Troubleshooting

### Authentication or the source address is rejected

- Check whether `pg_hba.conf` allows the collector source address, account, and `postgres` database.
- Check that the server's password-authentication mode matches the account configuration.

### Login succeeds but data is incomplete

- Confirm that the account can read the required `pg_stat_*` views. Use `pg_monitor` or equivalent least-privilege grants for the target version.
- `template0` and `template1` are explicitly ignored by the template and produce no data.

### The target enforces SSL

- The template always uses `sslmode=disable` and the page has no SSL fields. An SSL-only target cannot be integrated directly.
