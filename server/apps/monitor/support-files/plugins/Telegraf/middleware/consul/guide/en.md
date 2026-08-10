# Consul Monitoring Guide

This capability uses Telegraf `inputs.consul` to access the Consul HTTP API. Its current metric scope is health-check state.

## Prerequisites

- The collector node can reach the full Consul HTTP API base address.
- The target has registered the health checks that need to be observed.
- The current page and template have only URL and interval fields. They send no authentication credential and expose no other plugin options.
- The API must therefore allow the collector node to read health checks directly. A target that requires authentication cannot be integrated directly.

## Setup Steps

1. From the actual collector node, confirm that the Consul base address and health-check API can be read directly.
2. Enter the full URL and interval (default `60` seconds).
3. In the monitored objects table, select the node and enter the URL, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

```bash
curl --fail --silent --show-error "http://consul.example.com:8500/v1/agent/checks"
```

The request must return `200` and JSON; `--fail` preserves `4xx/5xx` failures. An empty object means that the current agent has no registered checks, not that the collector failed.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| URL | Yes | Full Consul HTTP API base address, such as `http://consul.example.com:8500`. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can access the API directly. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `consul_health_checks_passing`
- `consul_health_checks_critical`
- `consul_health_checks_warning`
- `consul_health_checks_status`

## Troubleshooting

### The API returns `403` or requires authentication

- The current page and template cannot configure or send authentication credentials.
- Do not embed sensitive credentials in the URL. An authenticated target requires an implemented security field before integration.

### No health-check data appears

- Confirm that the target agent has registered health checks and inspect the pre-check response.
- The current capability covers health-check state only; it does not promise Consul telemetry or runtime metrics.

### The URL is reachable but collection fails

- Enter the HTTP API base address, not a specific health-check path.
- Inspect the Telegraf log for the actual HTTP status and parsing error.
