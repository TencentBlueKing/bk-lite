# PostgreSQL Monitoring Guide

This capability uses Telegraf `inputs.postgresql` to connect to a specified PostgreSQL host, port, and database.

## Prerequisites

- The collector node can reach the target PostgreSQL host and actual port.
- Prepare an account that can log in to the configured database and read `pg_stat_database` and `pg_stat_bgwriter`. On PostgreSQL 10 and later, grant `pg_read_all_stats`. The same grant can also read current session waits.
- Top SQL Collection is off by default. Before turning it on, have the DBA run `CREATE EXTENSION IF NOT EXISTS pg_stat_statements` in the database named on the page (and include it in `shared_preload_libraries`). The monitoring account must be able to read that view.
- Wait Event Collection is off by default. When on, it samples sessions currently waiting. It is not cumulative wait time.
- Recovery state, the streaming-replica count, and the replication-slot count are collected with the basic connection. A standby, or a count above zero, labels the header as primary-standby. Not in recovery with both counts at zero labels it standalone. Without those readings the form chip stays hidden, and not-in-recovery alone is not labeled standalone. The same query also collects write, flush, and replay lag for connected replicas, and the WAL still retained by replication slots. Lag is 0 when no streaming replica is connected. Slot backlog is 0 when no slot is retaining WAL.
- The target `pg_hba.conf` allows this account to connect from the collector node.
- The page supports SSL modes `disable`, `prefer`, and `require`. Certificate paths are not supported; `verify-ca` and `verify-full` are unavailable in this template.
- The template always ignores `template0` and `template1`.

## Setup Steps

1. Have the DBA create a dedicated account. This collector is Telegraf `inputs.postgresql` and reads `pg_stat_database` and `pg_stat_bgwriter`. On PostgreSQL 10 and later, grant `pg_read_all_stats`. Replace `<monitor_user>`, `<password>`, and `<dbname>` with site values, and do not put the password in command history:

```sql
CREATE ROLE <monitor_user> WITH LOGIN PASSWORD '<password>';
GRANT CONNECT ON DATABASE <dbname> TO <monitor_user>;
GRANT pg_read_all_stats TO <monitor_user>;
```

`<dbname>` must match the page database name; `postgres` is the usual default. Do not grant superuser, and do not use the `postgres_exporter` `SECURITY DEFINER` wrapper views. This template does not query them. Source addresses are still controlled by `pg_hba.conf`.

2. From the actual collector node, validate the target address, account, database name, SSL mode, and statistics-view permissions.
3. Enter the username, password, host, actual port, database name, SSL mode, and interval (default `60` seconds).
4. In the monitored objects table, select the node and enter the host, port, instance name, and optional group.
5. Save the configuration and wait for at least one collection interval.

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
| Top SQL Collection | No | Advanced option, off by default. When on, the professional dashboard can show statement time, executions, and rows returned. |
| Wait Event Collection | No | Advanced option, off by default. When on, current waiting sessions can be shown. |
| Node | Yes | Collector node that can reach PostgreSQL. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `postgresql_numbackends`
- `postgresql_xact_commit_rate`
- `postgresql_deadlocks_rate`
- `postgresql_cache_hit_ratio`
- `postgresql_recovery_in_recovery` (`0` accepts writes, `1` is a standby)
- `postgresql_replication_streaming_replicas` (connected streaming replicas)
- `postgresql_replication_replication_slots` (replication slots)
- `postgresql_replication_write_lag_seconds` (write lag of connected replicas, seconds)
- `postgresql_replication_flush_lag_seconds` (flush lag of connected replicas, seconds)
- `postgresql_replication_replay_lag_seconds` (replay lag of connected replicas, seconds)
- `postgresql_replication_slot_restart_lag_bytes` (WAL still retained by replication slots, bytes)

After turning on Top SQL Collection and waiting one interval, `postgresql_statement_total_time_seconds` can also be confirmed. After turning on Wait Event Collection, `postgresql_wait_sessions` can be confirmed when a session is waiting.

## Troubleshooting

### Authentication or the source address is rejected

- Check whether `pg_hba.conf` allows the collector source address, account, and target database.
- Check that the server's password-authentication mode matches the account configuration.

### Login succeeds but data is incomplete

- Confirm that the account can read `pg_stat_database` and `pg_stat_bgwriter`. On PostgreSQL 10 and later, use `pg_read_all_stats`.
- `template0` and `template1` are explicitly ignored by the template and produce no data.

### The target enforces SSL

- Set SSL mode to `require` (or `prefer`). Certificate paths are not supported; targets that require `verify-ca` or `verify-full` cannot be integrated directly with this template.
