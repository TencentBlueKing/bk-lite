# Redis Monitoring Guide

## Prerequisites

- Redis service is up on the target instance (default port `6379`).
- The collector node can reach the Redis endpoint (security groups / firewalls opened).
- An account with permission to run `INFO` is ready (a username is only required when ACL is enabled on Redis 6+).
- If `requirepass` is set on Redis, prepare the matching password; leave it empty when no authentication is configured.
- The collector uses Telegraf `inputs.redis`, addresses look like `tcp://<host>:<port>`, and metrics come from the `INFO` command.

## Recommended Permissions

The account should at least run:

- `INFO` (default sub-commands include `INFO server`, `INFO clients`, `INFO memory`, etc.)

If ACL / `requirepass` is not enabled, you can connect with empty username and password. In production, prefer a dedicated read-only monitoring account instead of root or any account that has high-risk commands such as `CONFIG` or `SHUTDOWN`.

## Setup Steps

1. Verify connectivity from the collector node to Redis (see pre-check commands below).
2. Fill in host, port, optional username, optional password, and interval (default `60s`) on the configure page.
3. Add rows in the monitored objects table for node, host, port, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

Without authentication (only if allowed):

```bash
redis-cli -h <host> -p <port> INFO server
```

With password:

```bash
redis-cli -h <host> -p <port> -a <password> INFO server
```

With ACL username (Redis 6+):

```bash
redis-cli -h <host> -p <port> --user <username> -a <password> INFO server
```

The endpoint is basically healthy when:

- The command succeeds and returns fields such as `redis_version` and `uptime_in_seconds`.
- The port is reachable and authentication (if enabled) succeeds.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | No | Required only when ACL is enabled on Redis 6+; leave empty otherwise |
| Password | No | Required when Redis sets `requirepass`; leave empty when no auth is configured |
| Host | Yes | Redis server host (collection target) |
| Port | Yes | Redis service port, default `6379` |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Verify host and port, the default scheme is `tcp://`.
- Re-run the `redis-cli` checks from the collector node, not only from your laptop.
- Wait for at least one collection interval.
- Confirm Telegraf / collection tasks are healthy on the node.

### 2. Authentication failures (NOAUTH / WRONGPASS)

- Check the password for accidental spaces.
- When ACL is enabled on Redis 6+, confirm the username and password pair are correct and the account has at least the `INFO` permission.
- When authentication is not enabled, confirm the password field is empty and Redis does not have `requirepass` set.

### 3. Partial missing metrics

- `inputs.redis` relies on `INFO` by default; custom metrics depend on Redis version.
- Permission gaps can make basic metrics succeed while sub-commands fail; validate `INFO server`, `INFO clients`, `INFO memory` separately.
- Under ACL, accounts only see fields matching their granted permissions.
