# Mysql Monitoring Guide

## Prerequisites

- The target MySQL instance is running and listening on port `3306` (default).
- The collector node can reach MySQL (security groups / firewalls opened for `3306`).
- A MySQL account with the required monitoring privileges is ready, along with its password.
- A Telegraf collector node is available and registered in the platform.

## Recommended Permissions

The monitoring account needs at least the following privileges to cover `SHOW GLOBAL STATUS`, `SHOW GLOBAL VARIABLES`, `SHOW SLAVE STATUS`, and reads against `performance_schema` / `information_schema`:

- `PROCESS`
- `REPLICATION CLIENT`
- `SELECT` on `performance_schema` and `information_schema`
- Optional: `SUPER` or `BACKUP_ADMIN` (for `SHOW SLAVE STATUS` compatibility on MySQL 8.0; grant by least-privilege principle)

Example (minimal grants):

```sql
CREATE USER 'monitor'@'%' IDENTIFIED BY '<password>';
GRANT PROCESS, REPLICATION CLIENT ON *.* TO 'monitor'@'%';
GRANT SELECT ON performance_schema.* TO 'monitor'@'%';
GRANT SELECT ON information_schema.* TO 'monitor'@'%';
FLUSH PRIVILEGES;
```

Prefer a dedicated read-only monitoring account instead of a high-privilege business account.

## Setup Steps

1. From the collector node, confirm connectivity with `mysql -h <host> -P 3306 -u <username> -p`.
2. Fill in username, password, host, port, and interval (default `60s`) on the configure page.
3. Add rows in the monitored objects table for node, host, port, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting (e.g. `mysql_uptime`, `mysql_threads_connected`).

## Pre-check Commands

Use the MySQL client to log in and run:

```bash
mysql -h <host> -P 3306 -u <username> -p -e "SHOW GLOBAL STATUS LIKE 'Uptime';"
```

A non-zero `Uptime` value confirms `SHOW GLOBAL STATUS` works.

For replication (when `gather_slave_status` is enabled):

```bash
mysql -h <host> -P 3306 -u <username> -p -e "SHOW SLAVE STATUS\\G"
```

The collection path is basically healthy when:

- The command exits successfully without prompting for extra input.
- `Uptime` returns a non-zero value.
- There is no `ERROR 1045 (28000)` or `ERROR 1130` for auth/network denial.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | Yes | Account used to connect to MySQL |
| Password | Yes | Password for that account |
| Host | Yes | MySQL instance address (IP or domain) |
| Port | Yes | MySQL listening port, default `3306` |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform |
| Group | No | Organization group for ownership / permission |

## Troubleshooting

### 1. No data after saving

- Confirm the collector node can reach MySQL TCP `3306`.
- Confirm Telegraf / collection tasks are healthy on the node.
- Wait for at least one collection interval (default 60s) before checking again.
- Re-run the `mysql` client checks above from the collector node, not only from your laptop.

### 2. Authentication failures (`ERROR 1045` / `Access denied`)

- Check the username / password for accidental spaces or stray newlines.
- Confirm the account is allowed to log in from the collector IP (`user@'%'` or `user@'<collector_ip>'`).
- Confirm the account has at least `PROCESS` and `REPLICATION CLIENT` privileges, otherwise collection fails immediately.
- On MySQL 8.0 the default plugin is `caching_sha2_password`; make sure the collector driver is compatible.

### 3. Partial missing metrics or permission gaps

- InnoDB metrics depend on `performance_schema` or `SHOW ENGINE INNODB STATUS`; missing `PROCESS` causes this group to be empty.
- Replication metrics depend on `REPLICATION CLIENT`; an empty `SHOW SLAVE STATUS` indicates a missing grant.
- It is normal for `slave_*` fields to be empty when `gather_slave_status = true` but the instance is not a replica.
- Temporary table, buffer pool, and similar metrics depend on `SHOW GLOBAL STATUS`; verify the grants if they are missing.

### 4. Replication lag anomalies

- The default template sets `gather_slave_status = true` and `gather_replica_status = false`. For MySQL 8.0.22+, switch to `gather_replica_status` if you use `SHOW REPLICA STATUS`.
- For a standalone (non-replication) instance, empty `slave_*` fields are expected.

> Note: this plugin uses Telegraf's native `inputs.mysql`; no additional exporter is required. To extend metrics, adjust `fieldinclude` and the `gather_*` flags directly in the template.