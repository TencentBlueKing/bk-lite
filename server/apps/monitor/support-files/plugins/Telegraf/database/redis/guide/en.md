# Redis Monitoring Guide

This capability uses Telegraf `inputs.redis` to connect to a specified Redis host and port over TCP and read `INFO` statistics.

## Prerequisites

- The collector node can reach the target Redis host and actual port.
- Leave username and password empty when authentication is disabled. For `requirepass`, only the password may be entered. For Redis 6+ ACL, enter both username and password.
- The monitoring account can execute `INFO`.
- The current template always builds a `tcp://` address. The page has no TLS, Unix-socket, database-number, or Sentinel fields.

## Setup Steps

1. From the actual collector node, validate the target address and `INFO` permission.
2. Enter the optional username and password according to the target authentication mode, then enter the host, port, and interval (default `60` seconds).
3. In the monitored objects table, select the node and enter the host, port, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

For an instance without authentication:

```bash
redis-cli -h redis.example.com -p 6379 INFO server
```

When authentication is required, use an interactive password prompt:

```bash
redis-cli -h redis.example.com -p 6379 --user monitor --askpass INFO server
```

The response must include `redis_version` and `uptime_in_seconds` without `NOAUTH` or `WRONGPASS`.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | No | Redis 6+ ACL username; leave empty when ACL is not used. |
| Password | No | `requirepass` or ACL password; leave empty when authentication is disabled. |
| Host | Yes | Redis hostname or IP address without a scheme. |
| Port | Yes | Actual Redis listener port. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can reach Redis. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `redis_uptime`
- `redis_used_memory`
- `redis_instantaneous_ops_per_sec`
- `redis_clients`

## Troubleshooting

### Redis returns `NOAUTH` or `WRONGPASS`

- Determine whether the target uses password-only authentication or Redis 6+ ACL, then fill the matching fields.
- Recheck with an interactive password prompt; do not put the password on the command line.

### Only some data is present

- Confirm that the account can execute the complete `INFO` command, not only one restricted subsection.
- Some fields depend on the Redis version and whether a feature is active.

### TLS or a Sentinel address cannot be integrated

- The current page and template support one TCP host and port only; they have no TLS or Sentinel parameters.
