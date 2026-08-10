# HAProxy Monitoring Guide

This capability uses Telegraf `inputs.haproxy` to access the HAProxy HTTP(S) stats address entered on the page.

## Prerequisites

- HAProxy exposes an HTTP or HTTPS stats page, and the collector node can reach its full address.
- The current page accepts HTTP(S) stats URLs only.
- Leave username and password empty when the stats page has no authentication; enter both when Basic Auth is enabled.
- The current template preserves the original HAProxy field names.

## Setup Steps

1. From the actual collector node, validate the HTTP(S) stats address and optional Basic Auth.
2. Enter the Stats Address, optional username/password, and interval (default `60` seconds).
3. In the monitored objects table, select the node and enter the Stats Address, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

For a CSV stats endpoint without authentication:

```bash
curl --fail --silent --show-error "http://haproxy.example.com:8404/haproxy?stats;csv"
```

With Basic Auth, `curl` prompts for the password:

```bash
curl --fail --silent --show-error --user monitor "https://haproxy.example.com:8404/haproxy?stats;csv"
```

The response must be HAProxy stats CSV; `--fail` preserves `4xx/5xx` failures.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Stats Address | Yes | Full HAProxy HTTP(S) stats URL. |
| Username | No | Basic Auth username; leave empty when authentication is disabled. |
| Password | No | Enter together with the username; leave empty when authentication is disabled. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can reach the stats URL. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `haproxy_scur`
- `haproxy_rate`
- `haproxy_hrsp_5xx`
- `haproxy_chkfail`

## Troubleshooting

### The endpoint returns `401`

- Confirm that username and password are entered together, and keep credentials out of the URL.
- Reproduce through the interactive password prompt to avoid plaintext credentials and shell-escaping issues.

### The Stats Address format is invalid

- Enter a full HTTP(S) URL containing the scheme, host, port, and stats path.

### Field names differ from expectations

- The current template always preserves the original HAProxy field names.
