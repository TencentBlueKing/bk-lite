# Postgres Monitoring Guide

## Prerequisites

- The PostgreSQL service is up on the target instance (default port `5432`).
- The collector node can reach the PostgreSQL endpoint (security groups / firewalls opened for port `5432`).
- A username and password with permission to log in and query stat views are ready.
- The monitoring account should be granted the `pg_monitor` role to read `pg_stat_*` views.

## Recommended Permissions

Per the upstream `inputs.postgresql` README, use a dedicated read-only monitoring account and grant the `pg_read_all_stats` predefined role (PostgreSQL 10+, which grants read access to all `pg_stat_*` / `pg_stat_database` views):

```sql
CREATE USER monitor WITH PASSWORD '<your_password>';
GRANT pg_read_all_stats TO monitor;
```

> On older versions grant `pg_monitor` (the predecessor role, PostgreSQL 10-15) and optionally `GRANT SELECT ON ALL TABLES IN SCHEMA pg_catalog TO monitor;`. Never grant SUPERUSER.

The template already ignores `template0` and `template1` by default.

## Setup Steps

1. Verify the connection from the collector node using `psql`.
2. Fill in username, password, host, port (default `5432`), and interval (default `60s`) on the configure page.
3. Add rows in the monitored objects table for node, host, port, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

Run from the collector node using the monitoring account to verify connectivity and basic query privileges:

```bash
psql "host=<host> port=<port> user=<user> dbname=postgres" -c "SELECT version();"
```

The endpoint is basically healthy when:

- The command returns the PostgreSQL version without `FATAL: could not connect`.
- The monitoring account can run `SELECT * FROM pg_stat_database;` and similar `pg_stat_*` queries.

Optional connectivity probe:

```bash
nc -vz <host> 5432
```

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | Yes | Account for PostgreSQL; recommended to grant `pg_monitor` |
| Password | Yes | Password for that account |
| Host | Yes | PostgreSQL host, e.g. `10.0.0.10` |
| Port | Yes | PostgreSQL port, default `5432` |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform (default `host:port`) |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Re-run the `psql` check from the collector node, not only from your laptop.
- Confirm `pg_hba.conf` allows connections from the collector IP (`host all all <collector_ip>/32 md5`).
- Wait for at least one collection interval (default 60s).
- Confirm Telegraf / collection tasks are healthy on the node.

### 2. Authentication failures

- Check username/password for accidental spaces.
- Confirm the account has been granted `pg_monitor` via `GRANT pg_monitor TO <user>;`.
- Verify `pg_hba.conf` uses `md5` or `scram-sha-256` as expected.

### 3. Partial missing metrics / insufficient privileges

- Missing `pg_stat_*` metrics usually indicate insufficient privileges; grant `pg_monitor` and retry.
- Connection count, lock waits, and replication lag depend on the corresponding stat views.
- The template ignores `template0` and `template1`; other databases may be silently skipped without privileges.

### 4. SSL / connection issues

- The template sets `sslmode=disable` by default; if the target enforces SSL, use a compatible connection string and update `pg_hba.conf` accordingly.
- `FATAL: no pg_hba.conf entry` typically means `pg_hba.conf` does not allow the collector IP.
