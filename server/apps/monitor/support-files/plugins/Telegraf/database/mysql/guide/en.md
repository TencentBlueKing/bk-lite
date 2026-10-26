# MySQL Monitoring Guide

This capability connects directly to MySQL and collects connection, query, InnoDB, and replication statistics.

## Prerequisites

- The collector node can reach the target MySQL host and actual port.
- This integration does not use TLS. The page has no TLS, database-name, or custom-connection fields.

### Basic monitoring permissions

Basic monitoring is enough for the health overview and the routine performance charts (connections, queries, InnoDB, and replication).

- Use a dedicated monitoring account that can log in. Limit the host to the collector node.
- View processes (`PROCESS`): process list and some instance status.
- View replication (`REPLICATION CLIENT`): replication status and Binary Log.
- Also grant `SELECT ON performance_schema.*`: Performance Schema statistics, including table waits. This is also the prerequisite for advanced statement and wait collection.
- Do not grant `SELECT` on business schemas. If an individual InnoDB metric is denied because of `information_schema`, grant `SELECT` on that table only.

### Top SQL and waits (advanced)

After the basic permissions are in place, the Top SQL and Waits pages also need:

- Performance Schema enabled on the instance. Without it, statements and waits cannot be collected.
- `SELECT ON performance_schema.*` on the monitoring account. The same grant recommended for basic monitoring is enough.
- The matching switch turned on in the collection settings. Both are off by default: Top SQL Collection feeds the Top SQL page; Wait and Session Collection feeds the Waits page.
- These are separate from Table IO Waits and Table Lock Waits. Turning on table waits does not produce statement or wait data, and the reverse is also true.

## Setup Steps

1. Have the DBA create a dedicated account. Replace `<monitor_user>`, `<password>`, and `<collector_host>` with site values. Limit the host to the collector node; do not use `%`, and do not put the password in command history:

```sql
CREATE USER '<monitor_user>'@'<collector_host>' IDENTIFIED BY '<password>';
GRANT PROCESS, REPLICATION CLIENT ON *.* TO '<monitor_user>'@'<collector_host>';
GRANT SELECT ON performance_schema.* TO '<monitor_user>'@'<collector_host>';
```

- `PROCESS`: process list and some instance status.
- `REPLICATION CLIENT`: replication status and Binary Log.
- `SELECT ON performance_schema.*`: Performance Schema statistics, including table waits. This is also the prerequisite for advanced statement and wait collection.
- Do not grant `SELECT` on business schemas. If an individual InnoDB metric is denied because of `information_schema`, grant `SELECT` on that table only.

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

After saving and waiting for one interval, confirm that the platform can show basic metrics such as uptime, current connections, query rate, and the InnoDB buffer pool.

## Troubleshooting

### Login fails

- Confirm that the account is allowed to log in from the collector node's source address.
- Recheck through the interactive password prompt to avoid a false result caused by shell interpretation of special characters.

### Only some data is present

- Missing `PROCESS`: the process list and some instance status have no data.
- Missing `REPLICATION CLIENT`: replication status and Binary Log have no data.
- Missing `SELECT ON performance_schema.*`: Performance Schema statistics have no data, including table waits and advanced statement or wait data.
- Top SQL Collection or Wait and Session Collection is off: the matching page has no data. Both switches are off by default and need Performance Schema enabled on the instance.
- A non-replication instance has no replication data. That is expected.
- If the data still does not match, check the collection task failure reason or the collection logs.

### The target enforces TLS

- This integration does not use TLS, and the page has no certificate or TLS-mode fields. A TLS-only target cannot be integrated directly.
