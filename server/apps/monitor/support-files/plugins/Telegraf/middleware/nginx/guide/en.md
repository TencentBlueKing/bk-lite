# Nginx Monitoring Guide

This plugin uses Telegraf `inputs.nginx` to periodically scrape the Nginx `ngx_http_stub_status_module` output (commonly `/stub_status` or `/server_status`) and collect connection / request / read-write state metrics. The module works with open-source Nginx only; Nginx Plus requires `inputs.nginx_plus` or `inputs.nginx_upstream_check` instead.

## Prerequisites

- The target Nginx is running and was compiled with `ngx_http_stub_status_module` (verify with `nginx -V 2>&1 | grep -o stub_status`).
- A stub_status endpoint is exposed, for example:

  ```nginx
  server {
      listen 127.0.0.1:80;
      location = /stub_status {
          stub_status;
          access_log off;
          allow 127.0.0.1;
          deny all;
      }
  }
  ```

- The collector node can reach the Nginx stub_status port (security groups / firewalls opened).

> `inputs.nginx` only collects seven core fields: `accepts`, `active`, `handled`, `requests`, `reading`, `waiting`, `writing`. Tags are `port` and `server`.

## Recommended Permissions

The stub_status endpoint requires no account. If it must be exposed to a wider network, bind it to an internal IP and add an IP allow-list:

```nginx
location = /stub_status {
    stub_status;
    access_log off;
    allow 10.0.0.0/24;
    deny all;
}
```

## Setup Steps

1. Verify the stub_status endpoint is reachable:

   ```bash
   curl http://<host>/stub_status
   ```

   The response should include lines such as `Active connections:`, `accepts handled requests`, `Reading`, `Writing`, `Waiting`.

2. On the configure page, fill in the URL (default `http://<host>/stub_status`) and interval (default `60s`).
3. Add rows in the monitored objects table for node, URL, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

stub_status reachability:

```bash
curl http://<host>/stub_status
```

HTTP 200 with 4–5 lines of text indicates the endpoint is healthy.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| URL | Yes | Nginx stub_status endpoint URL, e.g. `http://10.0.0.5/stub_status` |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform; defaults to the URL |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Confirm Nginx was built with `stub_status` (`nginx -V 2>&1 | grep stub_status`).
- Run `curl` directly from the collector node against `/stub_status` to confirm `Active connections:` text is returned.
- Wait for at least one collection interval.

### 2. 403 / Forbidden

- `stub_status` defaults to `127.0.0.1`. For remote collection, change the listen address to `0.0.0.0` or a NIC IP and add an `allow` rule.
- If Nginx is configured with `auth_basic`, fill in `username` / `password` for `inputs.nginx` (the current template omits them).

### 3. Only seven fields are collected

- That is the design of stub_status. For finer metrics such as `connections_accepted` / `connections_active`, switch to Nginx Plus with `inputs.nginx_plus`.
- If stub_status is missing from your Nginx build (some distributions strip it), recompile with `--with-http_stub_status_module`.