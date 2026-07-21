# RabbitMQ Monitoring Guide

This plugin uses Telegraf `inputs.rabbitmq` to periodically call the RabbitMQ Management Plugin HTTP API and collect overview, node, queue, exchange, and federation metrics. The default Management port is `15672` — distinct from the AMQP port (`5672`).

## Prerequisites

- The target RabbitMQ is running with the Management Plugin enabled:

  ```bash
  rabbitmq-plugins enable rabbitmq_management
  ```

- The default Management port is `15672`. The default account is `guest / guest`, restricted to local logins.
- The collector node can reach the RabbitMQ host (security groups / firewalls opened).
- If LDAP or internal accounts are used, prepare a read-only account.

> Telegraf emits five main measurements — `rabbitmq_overview`, `rabbitmq_node`, `rabbitmq_queue`, `rabbitmq_exchange`, `rabbitmq_federation` — tagged with `url`, `node`, `queue`, `vhost`, etc.

## Recommended Permissions

Management users are controlled by built-in tags (`administrator`, `monitoring`, `management`, `policymaker`). Grant the monitor account the `monitoring` tag — read-only on the Management API:

```bash
rabbitmqctl add_user monitor monitor-pwd
rabbitmqctl set_user_tags monitor monitoring
rabbitmqctl set_permissions -p / monitor "^$" "^$" "^$"   # monitoring only needs HTTP API read
```

The `monitoring` tag already provides Management HTTP API read access; no AMQP permissions are required.

## Setup Steps

1. Verify the Management API is reachable:

   ```bash
   curl -u monitor:monitor-pwd http://<host>:15672/api/overview
   ```

2. On the configure page, fill in the URL (default `http://<host>:15672`), username, password, and interval (default `60s`).
3. Add rows in the monitored objects table for node, URL, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

Management API reachability:

```bash
curl -u <user>:<pwd> http://<host>:15672/api/nodes
```

HTTP 200 with a JSON array indicates the endpoint is healthy.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| URL | Yes | RabbitMQ Management API address, e.g. `http://10.0.0.5:15672` |
| Username | Yes | Management login account; prefer a `monitoring`-tagged read-only account |
| Password | Yes | Password for that account |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform; defaults to the URL |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Confirm the Management Plugin is enabled and RabbitMQ has been restarted (or wait for the next node start).
- Confirm port `15672` is reachable — different from AMQP `5672`.
- Run `curl /api/overview` directly from the collector node.

### 2. Authentication failures

- The `guest` account only allows localhost logins; create a new account for remote collection.
- Check that `set_user_tags` includes `monitoring` or `management`; `set_permissions` alone is not enough.
- Special characters in the password do not need escaping — Telegraf sends the credentials via the `Authorization` header.

### 3. Partial missing metrics

- `rabbitmq_node` reports only the currently reachable nodes; if a cluster node is down, wait for it to recover or inspect the cluster status.
- Some fields (`gc_num`, `io_read_bytes`, etc.) require RabbitMQ 3.6+ statistics; older versions may miss them.
- `queue_name_include` / `queue_name_exclude` accept globs; an empty list means "all" (the default).