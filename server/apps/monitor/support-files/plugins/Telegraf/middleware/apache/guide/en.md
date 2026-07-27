# Apache Monitoring Guide

This plugin uses Telegraf `inputs.apache` to periodically scrape the Apache HTTPD `mod_status` machine-readable page (default `/server-status?auto`) and collect worker counts, request rate, byte counters, and connection status. Apache must have `mod_status` enabled and `ExtendedStatus On` to expose the full set of fields.

## Prerequisites

- The target Apache HTTPD service is running with `mod_status` loaded.
- `ExtendedStatus On` is enabled and `/server-status` is exposed, e.g.:

  ```apache
  <Location "/server-status">
      SetHandler server-status
      Require local
      Require ip 10.0.0.0/24   # for remote access
  </Location>
  ExtendedStatus On
  ```

- The collector node can reach the Apache host (security groups / firewalls opened).
- The URL must point at the machine-readable page, i.e. include `?auto`, otherwise the HTML page cannot be parsed.

> Telegraf's default URL is `http://localhost/server-status?auto`, which yields `apache_*` metrics such as `BusyWorkers`, `ReqPerSec`, `BytesPerSec`, and `TotalAccesses`.

## Recommended Permissions

If `/server-status` does not need Basic Auth (best to bind to `127.0.0.1` or the LAN), no account is required. If it must be exposed publicly, restrict by IP and add Basic Auth:

```apache
<Location "/server-status">
    SetHandler server-status
    AuthType Basic
    AuthName "Apache Status"
    AuthUserFile "/etc/httpd/conf/.htpasswd"
    Require valid-user
</Location>
```

Grant the monitoring account only enough privilege to read `/server-status`; do not give it site-management rights.

## Setup Steps

1. Verify `mod_status` is reachable:

   ```bash
   curl http://<host>/server-status?auto
   ```

   Multiple `Key: Value` lines indicate the endpoint is healthy.

2. On the configure page, fill in the URL (must include `?auto`, e.g. `http://10.0.0.5/server-status?auto`) and interval (default `60s`).
3. Add rows in the monitored objects table for node, URL, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

`mod_status` reachability — the response should include `Total Accesses`:

```bash
curl http://<host>/server-status?auto
```

If HTML is returned the `?auto` parameter is missing; fix the Apache route or the URL.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| URL | Yes | Apache mod_status machine-readable URL, must include `?auto`, e.g. `http://10.0.0.5/server-status?auto` |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform; defaults to the URL |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Confirm the URL ends with `?auto`; otherwise Telegraf fails to parse the HTML.
- Confirm `ExtendedStatus On` is enabled — without it `BusyWorkers` and similar fields collapse to 0.
- Run `curl` from the collector node to verify `/server-status?auto` returns 200 plus machine-readable text.
- Wait for at least one collection interval.

### 2. Authentication failures

- If Apache requires Basic Auth, add the username / password to UI.json (the current template omits them; add `username` / `password` to `inputs.apache` when needed).
- Check that the `AuthUserFile` path exists and is readable.

### 3. Partial missing metrics

- Without `ExtendedStatus On`, fields such as `BytesPerReq`, `ReqPerSec`, and the `Scoreboard` block are dropped.
- If a reverse proxy (e.g. Nginx) strips `?auto`, the URL degrades to HTML; let the proxy pass the query string through.