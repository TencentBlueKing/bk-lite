# Nginx Monitoring Guide

This capability uses Telegraf `inputs.nginx` to scrape Nginx `stub_status` text.

## Prerequisites

- The target Nginx enables `ngx_http_stub_status_module` and exposes a status endpoint.
- The collector node can reach the full configured URL.
- The current page and template have no username or password fields, so the collector node must be allowed to read the endpoint without Basic Auth.
- Restrict the status endpoint to collector-node IPs on Nginx.

## Setup Steps

1. From the actual collector node, validate the `stub_status` URL.
2. Enter the full URL and interval (default `60` seconds).
3. In the monitored objects table, select the node and enter the URL, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

```bash
curl --fail --silent --show-error "http://nginx.example.com/stub_status"
```

The response must include `Active connections`, `Reading`, `Writing`, and `Waiting`; `--fail` preserves `4xx/5xx` failures.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| URL | Yes | Full Nginx `stub_status` endpoint URL. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Virtual Host Traffic | No | Off by default. `inputs.nginx_vts` is collected only after it is turned on. |
| VTS URL | Required when on | JSON status page of nginx-module-vts. |
| Node | Yes | Collector node that can read the URL without authentication. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Virtual Host Traffic (optional)

This switch is off by default. While it is off, collection uses only the Status URL above. The existing stub_status address and charts stay as they are.

Before turning it on, the target host must already:

- Have `nginx-module-vts` installed, with `vhost_traffic_status_display` enabled.
- Expose a JSON status page. The usual URL is `http://<host>/vts_status/format/json`, and the response Content-Type is `application/json`.
- Allow the collector node to read that URL without Basic Auth.

Tengine does not support `nginx-module-vts`. Do not enable this switch for Tengine.

Enter a VTS URL for each instance. The Status URL remains the original `stub_status` address; the two URLs do not replace each other.

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `nginx_active`
- `nginx_reading`
- `nginx_writing`
- `nginx_requests_rate`
- `nginx_http_requests_total`
- `nginx_connections_accepted`
- `nginx_connections_handled`
- `nginx_up`

## Troubleshooting

### The endpoint returns `401` or requires Basic Auth

- Basic Auth is not supported by the current page or template; there are no credential fields.
- Within a controlled network, allow anonymous reads from the collector node and restrict source IPs.

### The endpoint returns `403`

- Check whether Nginx `allow`/`deny` rules include the actual collector source IP.
- Reproduce from the actual collector node, not only on the Nginx host.

### Only basic connection data is present

- With Virtual Host Traffic off, collection is `stub_status` only.
- Status-code, upstream, and cache metrics require `nginx-module-vts` on the target and this switch turned on. Tengine is not supported.
