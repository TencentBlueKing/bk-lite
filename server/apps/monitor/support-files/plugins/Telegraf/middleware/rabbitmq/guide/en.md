# RabbitMQ Monitoring Guide

This capability uses Telegraf `inputs.rabbitmq` to access the RabbitMQ Management Plugin HTTP API. The management port is separate from the AMQP port.

## Prerequisites

- The target RabbitMQ enables the Management Plugin and exposes an HTTP(S) management address reachable from the collector node.
- Prepare an account that can read the Management API. Do not use the default localhost-only `guest` account for remote collection.
- Username and password are both required on the current page.
- The current page and template have no queue include/exclude filters and do not manage the Management Plugin lifecycle.
- Use actual Management API reachability as the readiness signal.

## Setup Steps

1. From the actual collector node, validate the Management API address and monitoring account.
2. Enter the URL, username, password, and interval (default `60` seconds).
3. In the monitored objects table, select the node and enter the URL, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

This command prompts for the password and preserves HTTP failures:

```bash
curl --fail --silent --show-error --user monitor "http://rabbitmq.example.com:15672/api/overview"
```

The request must return `200` and JSON. Validate the same full base address that will be entered on the page; do not use the AMQP port.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| URL | Yes | RabbitMQ Management HTTP(S) API base address. |
| Username | Yes | Account that can read the Management API. |
| Password | Yes | Password for the account. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can reach the Management API. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `rabbitmq_node_running`
- `rabbitmq_overview_connections`
- `rabbitmq_overview_messages`
- `rabbitmq_node_mem_used`

## Troubleshooting

### The API returns `401` or `403`

- Confirm that the account has monitoring read access to the Management API.
- The `guest` account cannot log in remotely by default; use a dedicated collection account.

### The port is reachable but no data appears

- Confirm that the URL targets the Management HTTP(S) API, not the AMQP service port.
- Inspect the Telegraf log for the exact API, HTTP status, and response-parsing error.

### Queue filtering is required

- The current UI and template have no queue-filter fields. This guide does not promise or ask users to configure that capability.
