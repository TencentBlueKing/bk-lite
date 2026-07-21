# InfluxDB Monitoring Guide

## Prerequisites

- The target InfluxDB v1 service is up (default port `8086`).
- The InfluxDB v1 `/debug/vars` endpoint is exposed (Telegraf `inputs.influxdb` collects runtime metrics from it).
- The collector node can reach the InfluxDB endpoint (security groups / firewalls opened).
- If the endpoint has Basic Auth enabled, have the username and password ready; otherwise leave them empty.
- The Server Address field must be a full URL starting with `http://` or `https://` and ending with `/debug/vars`, for example `http://10.0.0.10:8086/debug/vars`.

## Recommended Permissions

- InfluxDB v1 `/debug/vars` is a read-only runtime statistics endpoint and does not touch database data.
- If the instance has no Basic Auth, no account is required for collection.
- If Basic Auth is enabled, any read-only account that can pass authentication to `/debug/vars` is enough; avoid a high-privilege admin account.

## Setup Steps

1. Verify from the collector node that the target InfluxDB `/debug/vars` endpoint is reachable.
2. On the configure page fill in the server address, username/password (if auth is enabled), interval (default `60s`), and timeout (default `30s`); for HTTPS, fill in certificate paths or enable Skip Certificate Verification as needed.
3. Add rows in the monitored objects table for node, server address, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

Without authentication (only if allowed):

```bash
curl -sS "http://<host>:8086/debug/vars"
```

With Basic Auth:

```bash
curl -sS -u "<username>:<password>" "http://<host>:8086/debug/vars"
```

The endpoint is basically healthy when:

- HTTP status is `200`
- The body is JSON containing runtime stats fields such as `memstats` and `cmdline`

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Server Address | Yes | Full URL ending with `/debug/vars`, e.g. `http://localhost:8086/debug/vars` |
| Username | No | Fill in when the endpoint has Basic Auth enabled, otherwise leave empty |
| Password | No | Matches the username, required when Basic Auth is enabled |
| Interval | Yes | Collection interval in seconds, default `60` |
| Timeout | Yes | Timeout for a single `/debug/vars` request in seconds, default `30` |
| CA Certificate Path | No | CA certificate path for HTTPS |
| Client Certificate Path | No | Client certificate path for HTTPS mutual auth |
| Client Key Path | No | Client key path for HTTPS mutual auth |
| Skip Certificate Verification | No | Whether to skip server certificate verification for HTTPS |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Verify the protocol and port in the server address, and that it ends with `/debug/vars`.
- Re-run the `curl` checks from the collector node, not only from your laptop.
- Confirm the InfluxDB v1 `/debug/vars` endpoint is exposed (some versions or configs may disable it).
- Wait for at least one collection interval, and confirm Telegraf / collection tasks are healthy on the node.

### 2. Authentication failures (401 / 403)

- Confirm whether Basic Auth is actually enabled: supplying credentials when it is not may itself cause errors.
- Check the username/password for accidental leading/trailing spaces or unescaped special characters.
- Confirm the account can pass authentication to `/debug/vars`.

### 3. Partial missing metrics or insufficient permissions

- All InfluxDB runtime metrics come from the `/debug/vars` body; missing metrics usually mean an incomplete response or version differences.
- Use `curl` to inspect the `/debug/vars` body directly and confirm the target fields exist.
- For HTTPS, if the response is abnormal, verify the certificate paths, or temporarily enable Skip Certificate Verification in a test environment to isolate the issue.
