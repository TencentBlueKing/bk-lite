# Apache Monitoring Guide

This capability uses Telegraf `inputs.apache` to scrape the machine-readable output of Apache HTTPD `mod_status`.

## Prerequisites

- The target Apache loads `mod_status` and exposes a status endpoint with `?auto`.
- The collector node can reach the full URL.
- The current page and template have no username or password fields, so the collector node must be allowed to read the endpoint without Basic Auth.
- Restrict access by collector-node IP on Apache. Whether `ExtendedStatus On` is enabled determines how many statistics are available.

## Setup Steps

1. From the actual collector node, validate the status URL including `?auto`.
2. Enter the full URL and interval (default `60` seconds).
3. In the monitored objects table, select the node and enter the URL, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

```bash
curl --fail --silent --show-error "http://apache.example.com/server-status?auto"
```

The response must be `Key: Value` text containing `Total Accesses`. `--fail` preserves `4xx/5xx` failures. An HTML response usually means that `?auto` is missing.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| URL | Yes | Full machine-readable `mod_status` URL including `?auto`. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can read the URL without authentication. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `apache_ServerUptimeSeconds`
- `apache_TotalAccesses`
- `apache_BusyWorkers`
- `apache_IdleWorkers`

## Troubleshooting

### The endpoint returns `401` or requires Basic Auth

- Basic Auth is not supported by the current page or template; there are no credential fields.
- Within a controlled network, allow anonymous reads from the collector node and restrict source IPs.

### The response is HTML or cannot be parsed

- Confirm that the URL contains `?auto` and that a reverse proxy preserves the query string.
- Reproduce from the actual collector node, not only on the Apache host.

### Only some data is present

- Check the actual `ExtendedStatus` setting and whether the corresponding fields exist in the `mod_status` response.
