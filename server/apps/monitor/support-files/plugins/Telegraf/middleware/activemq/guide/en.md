# ActiveMQ Monitoring Guide

This capability uses Telegraf `inputs.activemq` with the URL, username, and password provided on the page to access an ActiveMQ HTTP management endpoint.

## Prerequisites

- The target ActiveMQ exposes an HTTP management endpoint compatible with Telegraf `inputs.activemq`.
- The collector node can reach the full configured URL.
- Prepare an account accepted by that HTTP endpoint and allowed to read monitoring data. The actual role name and permissions depend on the target ActiveMQ security configuration.
- The current page has only URL, username, password, and interval fields. It has no management-path, queue-filter, or other plugin options.

## Setup Steps

1. From the actual collector node, validate the full URL and monitoring account.
2. Enter the URL, username, password, and interval (default `60` seconds).
3. In the monitored objects table, select the node and enter the URL, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

This command prompts for the password and preserves HTTP failures:

```bash
curl --fail --silent --show-error --location --user monitor "http://activemq.example.com:8161"
```

The request must complete without an authentication or access-denied response. Final compatibility with the collection API is confirmed by the Telegraf log and metrics after saving.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| URL | Yes | Full base address of the ActiveMQ HTTP management endpoint. |
| Username | Yes | Login accepted by the target endpoint. |
| Password | Yes | Password for the account. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can reach the URL. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `activemq_topics_consumer_count`
- `activemq_topics_dequeue_count`
- `activemq_topics_enqueue_count`
- `activemq_topics_size`

## Troubleshooting

### Authentication or access is denied

- Check the URL, account, and the target ActiveMQ's actual permission configuration.
- Recheck through the interactive password prompt; do not put the password on the command line.

### A custom management path or filter is required

- The current page and template have no management-path or queue-filter fields, so these cannot be configured through the page.
- A target outside the current field contract needs an implemented capability first; the guide cannot add parameters that the page does not expose.

### No data appears after saving

- Inspect the Telegraf log for the actual HTTP status, response-parsing, or authentication error.
- Successful browser login to a management page does not prove that its response is compatible with the `inputs.activemq` collection API.
