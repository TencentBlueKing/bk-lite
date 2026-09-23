# MySQL Monitoring Guide

This capability uses Telegraf `inputs.mysql` to connect directly to one MySQL host and port and collect connection, query, InnoDB, replication, and cache statistics configured by the current template.

## Prerequisites

- The collector node can reach the target MySQL host and actual port.
- Prepare a dedicated monitoring account that can log in and read global status, global variables, and the statistics required by the template.
- Process-list statistics normally require `PROCESS`; replication statistics normally require `REPLICATION CLIENT`. Grant only the permissions required by the data in use.
- The current template always uses `tls=false`. The page has no TLS, database-name, or custom-connection fields.
- The template gathers process list, InnoDB, legacy replication status, binary logs, global variables, and table-wait statistics. It does not gather user statistics or the newer replica-status query.

## Setup Steps

1. Have the DBA create a dedicated account. Replace `<monitor_user>`, `<password>`, and `<collector_host>` with site values. Limit the host to the collector node; do not use `%`, and do not put the password in command history:

```sql
CREATE USER '<monitor_user>'@'<collector_host>' IDENTIFIED BY '<password>';
GRANT PROCESS, REPLICATION CLIENT ON *.* TO '<monitor_user>'@'<collector_host>';
GRANT SELECT ON performance_schema.* TO '<monitor_user>'@'<collector_host>';
```

`PROCESS` covers the process list and InnoDB status. `REPLICATION CLIENT` covers replication status and binary logs. `SELECT` on `performance_schema` covers table-wait statistics. Do not grant `SELECT` on business schemas. If an InnoDB metric is denied on `information_schema.innodb_metrics`, grant `SELECT` on that table only.

2. From the actual collector node, validate the target address, account, and basic status-query permission.
3. Enter the username, password, host, actual port, and interval (default `60` seconds).
4. In the monitored objects table, select the node and enter the host, port, instance name, and optional group.
5. Save the configuration and wait for at least one collection interval.

## Pre-checks

`--password` prompts for the password:

```bash
mysql --host db.example.com --port 3306 --user monitor --password --execute "SHOW GLOBAL STATUS LIKE 'Uptime';"
```

The command must return `Uptime`. If replication data is required, use the same account to confirm that the target version supports the relevant replication-status query and that the account can execute it.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | Yes | MySQL monitoring account. |
| Password | Yes | Password for the account. |
| Host | Yes | MySQL hostname or IP address without a scheme. |
| Port | Yes | Actual MySQL listener port. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can reach MySQL. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `mysql_uptime`
- `mysql_threads_connected`
- `mysql_queries_rate`
- `mysql_innodb_buffer_pool_pages_total`

## Troubleshooting

### Login fails

- Confirm that the account is allowed to log in from the collector node's source address.
- Recheck through the interactive password prompt to avoid a false result caused by shell interpretation of special characters.

### Only some data is present

- Use the actual Telegraf log to distinguish missing `PROCESS`, replication, or `performance_schema` access.
- Missing replication-status data is normal on a non-replica.
- The current template uses the legacy replication-status gatherer and does not switch automatically to the newer replica-status query.

### The target enforces TLS

- The current template disables TLS and the page has no certificate or TLS-mode fields. A TLS-only target cannot be integrated directly.
