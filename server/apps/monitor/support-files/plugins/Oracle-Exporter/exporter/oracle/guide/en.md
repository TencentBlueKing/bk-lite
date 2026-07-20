# Oracle Monitoring Guide

## Prerequisites

- The target Oracle database is running and reachable; the default listener port is `1521`.
- The collector node can reach the Oracle database (security groups / firewalls opened).
- A username and password with the required SELECT privileges on Oracle dynamic performance views are ready.
- This plugin collects metrics through a locally running Oracle-Exporter (Prometheus exporter); Telegraf's `inputs.prometheus` then scrapes `http://127.0.0.1:<listen_port>/metrics`. Make sure Oracle-Exporter is deployed or can be started on the collector node.

## Recommended Permissions

The monitoring account should at least have `SELECT` privileges on these dynamic performance views:

- `v$session`
- `v$sysstat`
- `v$database`

Grant the corresponding privileges in Oracle, for example:

```sql
GRANT SELECT ANY DICTIONARY TO <monitor_user>;
```

Or grant precisely (more secure):

```sql
GRANT SELECT ON v_$session TO <monitor_user>;
GRANT SELECT ON v_$sysstat TO <monitor_user>;
GRANT SELECT ON v_$database TO <monitor_user>;
```

Prefer a dedicated read-only monitoring account instead of `SYS` or `SYSTEM`.

## Setup Steps

1. Verify connectivity from the collector node to the Oracle database using `sqlplus`.
2. Verify that Oracle-Exporter is running and exposes metrics at `http://127.0.0.1:<listen_port>/metrics`.
3. Fill in username, password, service name, listen port, host, port, and interval (default `60s`) on the configure page.
4. Add rows in the monitored objects table for node, listen port, host, port, instance name, and group.
5. Click Confirm and wait for at least one collection interval.
6. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

Verify Oracle connectivity from the collector node:

```bash
sqlplus <user>/<pass>@//<host>:<port>/<service_name>
```

Verify the Oracle-Exporter is listening locally and exposing `/metrics` (this is the exporter's local port, NOT the Oracle port):

```bash
curl -sS "http://127.0.0.1:<listen_port>/metrics" | head
```

The integration is basically healthy when:

- `sqlplus` can log in to the target Oracle instance
- `curl http://127.0.0.1:<listen_port>/metrics` returns `200` and contains `oracle_*` metric lines

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | Yes | Oracle monitoring account |
| Password | Yes | Password for that account |
| Service Name | Yes | Oracle `service_name`; must match the running service |
| Listen Port | Yes | Local port on which Oracle-Exporter exposes `/metrics` (NOT the Oracle port) |
| Host | Yes | Oracle database host address |
| Port | Yes | Oracle database listener port, default `1521` |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Re-run `sqlplus` and `curl http://127.0.0.1:<listen_port>/metrics` from the collector node to confirm both the database and the exporter are reachable.
- Check whether the Oracle-Exporter process is running (`ps`, `docker ps`, or `systemctl status`).
- Wait for at least one collection interval (default 60 seconds).
- Confirm Telegraf / Oracle-Exporter collection tasks are healthy on the node.

### 2. Authentication failures (ORA-01017 / ORA-28000)

- Check username, password, and service name for accidental spaces; Oracle usernames are usually upper-cased automatically.
- Make sure the account is not locked (`ALTER USER <user> ACCOUNT UNLOCK;`) and the password has not expired.
- Confirm the account has `SELECT` privileges on `v$session`, `v$sysstat`, `v$database`, and the other required views.

### 3. Exporter not listening / port conflict

- In this plugin, "Listen Port" is the local port on which Oracle-Exporter exposes `/metrics` on the collector node, distinct from "Port" (the Oracle database itself, default `1521`). Do not confuse them.
- Run `curl -v http://127.0.0.1:<listen_port>/metrics` on the collector node; it should return `200` and contain `oracle_*` metric lines.
- If the port is already in use, change the Oracle-Exporter listen port and update "Listen Port" in this plugin configuration accordingly.
- Inspect Oracle-Exporter logs to identify startup failures (for example, an incorrect connection string or insufficient account privileges).

### 4. Partial missing metrics or insufficient privileges

- Metrics depend on `v$session`, `v$sysstat`, `v$database`, and other dynamic performance views; missing privileges may cause only some metrics to be empty.
- Use `GRANT SELECT ANY DICTIONARY` first to confirm whether the issue is permission-related, then narrow the grants as needed.
- If only `tablespace`-related metrics are missing, confirm the account has access to query the relevant tablespaces.
