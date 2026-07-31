# MongoDB Monitoring Guide

This capability uses Telegraf `inputs.mongodb` to connect directly to one MongoDB `host:port`. The connection string always uses `connect=direct`.

## Prerequisites

- The collector node can reach the target MongoDB host and port.
- Leave both username and password empty when authentication is disabled; enter both when it is enabled.
- The monitoring account can read the data required by `serverStatus`; use a dedicated least-privilege account.
- The current template connects directly to one address and has no fields for a replica-set name, multiple servers, TLS, authentication database, or custom connection parameters.

## Setup Steps

1. From the actual collector node, validate the target address and optional authentication account.
2. Enter the optional username/password, host, port, and interval (default `60` seconds).
3. In the monitored objects table, select the node and enter the host, port, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

For an instance without authentication:

```bash
mongosh "mongodb://db.example.com:27017/?connect=direct" --eval "db.serverStatus().ok"
```

When authentication is enabled, use an interactive password prompt:

```bash
mongosh "mongodb://db.example.com:27017/?connect=direct" --username monitor --authenticationDatabase admin --password
```

After login, run `db.serverStatus().ok`; it must return `1`. If the target uses a non-default authentication database, it cannot be selected on the current page.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | No | Enter when authentication is enabled; otherwise leave empty. |
| Password | No | Enter together with the username; otherwise leave empty. |
| Host | Yes | MongoDB host without a scheme or connection parameters. |
| Port | Yes | Actual MongoDB listener port. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can reach MongoDB. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `mongodb_uptime_ns`
- `mongodb_connections_current`
- `mongodb_active_reads`
- `mongodb_wtcache_current_bytes`

## Troubleshooting

### Authentication fails

- Confirm that username and password are entered together, and check the account's actual authentication database.
- The page cannot set `authSource` or x.509/TLS parameters. A target that requires those parameters cannot be integrated directly.

### A replica-set address does not work

- The template always uses `connect=direct` and one host/port; the page does not configure replica-set discovery.
- Select a specific MongoDB member directly reachable from the collector node.

### Only some data is present

- A successful login does not prove permission for `serverStatus`. Use the actual command error in the Telegraf log.
- Some statistics depend on the MongoDB version and storage engine.
