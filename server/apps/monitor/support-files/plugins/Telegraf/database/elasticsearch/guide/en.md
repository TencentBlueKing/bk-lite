# Elasticsearch Monitoring Guide

This capability uses Telegraf `inputs.elasticsearch` to access the Elasticsearch HTTP API and collect cluster health plus selected node statistics.

## Prerequisites

- The collector node can reach the full Elasticsearch HTTP(S) address.
- Prepare a username and password that can read cluster health and node statistics. Both fields are required on the current page.
- Authenticated endpoints should use HTTPS and a server certificate whose chain is trusted by the collector node.
- If the target supports only HTTP, use it only over an isolated, trusted path. Basic Auth credentials are merely reversibly encoded and cross the network without transport encryption.
- The account can access at least `/_cluster/health` and `/_nodes/stats`.
- The current template always enables cluster health and collects JVM, filesystem, process, breaker, HTTP, and thread-pool node statistics.
- The current template always skips server-certificate verification for HTTPS, and the page has no CA or verification switch. Do not treat this as a routine reason to deploy an untrusted certificate.

## Setup Steps

1. From the actual collector node, validate the full server address, credentials, and API permissions.
2. Enter the server address, username, password, and interval (default `60` seconds).
3. In the monitored objects table, select the node and enter the server address, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

These HTTPS commands prompt for the password instead of placing it in command arguments and shell history. Prompting does not protect network transport; security still depends on TLS, and the certificate chain must be trusted by the collector node. Do not use `-k` or `--insecure` as a routine workaround:

```bash
curl --fail --silent --show-error --user monitor "https://es.example.com:9200/_cluster/health"
curl --fail --silent --show-error --user monitor "https://es.example.com:9200/_nodes/stats"
```

Both requests must return `200`; `--fail` preserves `4xx/5xx` failures.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Server Address | Yes | Full HTTP(S) URL; prefer `https://es.example.com:9200` when authentication is used. |
| Username | Yes | Account that can read cluster health and node statistics. |
| Password | Yes | Password for the account. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can reach Elasticsearch. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `elasticsearch_cluster_health_status_code`
- `elasticsearch_cluster_health_active_primary_shards`
- `elasticsearch_jvm_mem_heap_used_percent`
- `elasticsearch_thread_pool_search_queue`

## Troubleshooting

### The API returns `401` or `403`

- Check the username, password, and read permissions for both APIs.
- Validate cluster health and node statistics separately; success on one does not prove permission for the other.

### HTTPS fails

- Check the URL scheme and port.
- The template skips server-certificate verification but has no client-certificate or custom-CA fields. A target that requires mutual TLS cannot be integrated directly.

### Only some data is present

- Node statistics are limited to the six categories listed in the template; unconfigured categories are not collected.
- Use the Telegraf log to determine whether cluster health or a specific node-statistics request failed.
