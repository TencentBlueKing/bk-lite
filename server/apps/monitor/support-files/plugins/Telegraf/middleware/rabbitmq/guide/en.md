# RabbitMQ Monitoring Guide

This capability uses Telegraf `inputs.rabbitmq` to access the RabbitMQ Management Plugin HTTP API. The management port is separate from the AMQP port.

## Prerequisites

- The target RabbitMQ enables the Management Plugin and exposes an HTTP(S) management address reachable from the collector node.
- Prepare an account that can read the Management API. Do not use the default localhost-only `guest` account for remote collection.
- Username and password are both required on the current page.
- An authenticated Management API should use HTTPS and a server certificate whose chain is trusted by the collector node.
- If the target supports only HTTP, use it only over an isolated, trusted path. Basic Auth credentials are merely reversibly encoded and cross the network without transport encryption.
- Use actual Management API reachability as the readiness signal.

## Setup Steps

1. From the actual collector node, validate the Management API address and monitoring account.
2. Enter the URL, username, password, and interval (default `60` seconds; do not go below `30`). Fill the Management root, for example `http://127.0.0.1:15672`, and do not include `/api/queues`.
3. Leave Collect Queues off to collect overview and node only, without calling `/api/queues`.
4. To collect queue metrics, turn Collect Queues on and fill the required queue-include rules (empty include cannot be saved, to avoid fetching all of `/api/queues`). Keep the timeout at the default `20` seconds.
5. In the monitored objects table, select the node and enter the URL, instance name, and optional group.
6. Save the configuration and wait for at least one collection interval.

## Pre-checks

This HTTPS command prompts for the password and preserves HTTP failures. Prompting only keeps the password out of command arguments and shell history; it does not protect network transport. The certificate chain must be trusted by the collector node. Do not use `-k` or `--insecure` as a routine workaround:

```bash
curl --fail --silent --show-error --user monitor "https://rabbitmq.example.com:15671/api/overview"
```

The request must return `200` and JSON. Validate the same full base address that will be entered on the page; do not use the AMQP port.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| URL | Yes | RabbitMQ Management HTTP(S) root, for example `http://127.0.0.1:15672`. Do not include `/api/queues` or another path. On save, trailing slashes are stripped and duplicate slashes are collapsed. |
| Username | Yes | Account that can read the Management API. |
| Password | Yes | Password for the account. |
| Interval | Yes | Collection interval in seconds; default `60`, not below `30`. |
| Collect Queues | No | Off by default. Only then does collection call `/api/queues`. Turning this off is the only way to stop the full Management table fetch. |
| Queue Include | Required when Collect Queues is on | When Collect Queues is on, include rules are required. Empty values cannot be saved, to avoid fetching all of `/api/queues`. Name filters still fetch the full table and only reduce stored series. |
| Queue Exclude | No | Optional Telegraf `queue_name_exclude` glob. |
| Timeout | Recommended when Collect Queues is on | Telegraf `client_timeout`; default `20` seconds, range `15–30`. |
| Node | Yes | Collector node that can reach the Management API. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

Name filters still fetch the full `/api/queues` table first and only reduce stored series. Tightening the include glob does not reduce Management fetch pressure. Turn Collect Queues off to stop that pressure. Telegraf 1.29 has no vhost include/exclude; queue series already carry `queue` and `vhost` labels for dashboard filtering.

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `rabbitmq_node_running`
- `rabbitmq_overview_connections`
- `rabbitmq_overview_messages`
- `rabbitmq_node_mem_used`

After enabling Collect Queues, also confirm `rabbitmq_queue_messages`.

## Troubleshooting

### The API returns `401` or `403`

- Confirm that the account has monitoring read access to the Management API.
- The `guest` account cannot log in remotely by default; use a dedicated collection account.

### The port is reachable but no data appears

- Confirm that the URL targets the Management HTTP(S) API, not the AMQP service port.
- Inspect the Telegraf log for the exact API, HTTP status, and response-parsing error.

### Queue collection times out or slows the node

- Name filters still fetch the full `/api/queues` table. The include glob only reduces stored series and does not reduce Management fetch pressure. The only way to stop that pressure is to turn Collect Queues off. If the request is slow, raise the timeout to `15–30` seconds; that does not avoid the full-table fetch.
