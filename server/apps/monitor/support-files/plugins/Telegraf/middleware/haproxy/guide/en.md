# HAProxy Monitoring Guide

This plugin uses Telegraf `inputs.haproxy` to periodically scrape the HAProxy stats endpoint — either an HTTP stats page or a unix socket — and collect `proxy`, `sv`, status-code, connection, byte, and rate metrics. The default UI uses HTTP form (`http://<host>:<port>/<path>;csv`). From Telegraf v1.21, `username` and `password` are independent fields so special characters in credentials do not break `net/url.Parse`; keep them separate from the URL.

## Prerequisites

- The target HAProxy is running and exposes a stats endpoint (e.g. `stats enable` or `stats uri /haproxy?stats`, commonly `http://<ip>:1024/haproxy?stats` or `:1936`).
- The collector node can reach the stats port (security groups / firewalls opened).
- If the stats page is behind Basic Auth, prepare a read-only account.
- The current template sets `keep_field_names = true`, preserving the original HAProxy field names (`pxname`, `svname`, etc. are not renamed to `proxy`, `sv`).

> `inputs.haproxy` accepts http(s), tcp, and unix-socket endpoints. If credentials contain special characters, fill the dedicated username / password fields — do not embed them in the URL userinfo, otherwise 401 errors may occur.

## Recommended Permissions

The HAProxy stats page is gated by `stats auth <user>:<pass>` or a `userlist`. Use a read-only account:

```haproxy
userlist monitor-users
    user monitor-user insecure-password "monitor-pwd"

frontend stats
    bind *:8404
    stats enable
    stats uri /haproxy?stats
    stats auth monitor-user:monitor-pwd
    stats refresh 10s
    acl auth_ok http_auth(monitor-users)
    http-request auth unless auth_ok
```

The monitor account only needs GET on the stats page; no traffic-scheduling rights.

## Setup Steps

1. Verify the stats endpoint is reachable:

   ```bash
   curl -u monitor-user:monitor-pwd "http://<host>:8404/haproxy?stats;csv"
   ```

2. On the configure page, fill in the Stats Address (`http://<host>:<port>/<path>`, no userinfo), the optional username / password, and the interval (default `60s`).
3. Add rows in the monitored objects table for node, stats address, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

Stats reachability (use `-u` if auth is enabled):

```bash
curl -u <user>:<pwd> "http://<host>:8404/haproxy?stats;csv"
```

Multiple CSV lines starting with `pxname,svname,...` indicate the endpoint is healthy.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Stats Address | Yes | HAProxy stats endpoint URL, e.g. `http://10.0.0.5:8404/haproxy?stats`, no userinfo |
| Username | No | Basic Auth username for the stats page; leave blank if auth is disabled |
| Password | No | Basic Auth password for the stats page; leave blank if auth is disabled |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform; defaults to the Stats Address |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Confirm the Stats Address is correct and `;csv` returns content via `curl` from the collector node.
- If Basic Auth is disabled, do not fill the username / password fields.
- Wait for at least one collection interval.

### 2. Authentication failures / 401

- When the password contains special characters (`@` `/` `:` `#`), keep them out of the URL. From Telegraf v1.21, the `Authorization` header is sent from the dedicated username / password fields.
- Verify `stats auth` matches the `userlist` / `user` entry.

### 3. Unfamiliar field names

- The template sets `keep_field_names = true`, so original HAProxy field names like `pxname`, `svname`, and `hrsp_2xx` are preserved. To get the normalized names (`proxy`, `sv`, `http_response.2xx`, etc.), flip the flag to `false`.