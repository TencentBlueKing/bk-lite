# InfluxDB Monitoring Guide

This capability uses Telegraf `inputs.influxdb` to read runtime statistics from the InfluxDB v1 `/debug/vars` endpoint.

## Prerequisites

- The target is an InfluxDB v1 instance that exposes `/debug/vars`, and the collector node can reach its full HTTP(S) URL.
- The server address includes the scheme, port, and `/debug/vars` path.
- If Basic Auth is enabled, prepare a username and password; otherwise leave both fields empty.
- HTTPS can use CA, client-certificate, and client-key paths. These files must exist on the actual collector node.

## Setup Steps

1. From the actual collector node, validate the `/debug/vars` URL and optional authentication.
2. Enter the server address, optional username/password, interval (default `60` seconds), and timeout (default `30` seconds).
3. For HTTPS, enter the CA, client certificate, client key, and verification switch as required.
4. In the monitored objects table, select the node and enter the server address, instance name, and optional group.
5. Save the configuration and wait for at least one collection interval.

## Pre-checks

For an endpoint without authentication:

```bash
curl --fail --silent --show-error "http://influxdb.example.com:8086/debug/vars"
```

For Basic Auth, the following command prompts for the password:

```bash
curl --fail --silent --show-error --user monitor "http://influxdb.example.com:8086/debug/vars"
```

The request must return `200` and JSON; `--fail` preserves `4xx/5xx` failures.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Server Address | Yes | Full URL, normally ending in `/debug/vars`. |
| Username, Password | No | Enter both when Basic Auth is enabled; otherwise leave both empty. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Timeout | Yes | Per-request timeout in seconds; default `30`. |
| CA Certificate Path | No | Path to a CA file on the collector node. |
| Client Certificate Path | No | Client certificate path for mutual TLS. |
| Client Key Path | No | Key path paired with the client certificate. |
| Skip Certificate Verification | No | Whether to skip server-certificate verification; disabled by default. |
| Node | Yes | Collector node that can reach the URL and contains the configured certificate files. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `influxdb_database_numSeries`
- `influxdb_httpd_writeReq_rate`
- `influxdb_httpd_pointsWrittenFail_rate`
- `influxdb_runtime_HeapAlloc`

## Troubleshooting

### The endpoint returns `401`, `403`, or `404`

- Check whether authentication is enabled and whether username and password are entered together.
- Confirm that the URL targets InfluxDB v1 `/debug/vars`, not the root path or a v2 API.

### HTTPS fails

- Certificate paths are read on the collector node; do not enter paths that exist only on another host.
- Enable Skip Certificate Verification only when the risk is explicitly accepted.

### Only some data is present

- All data comes from the `/debug/vars` body. Confirm that the target version actually returns the relevant statistics.
- A timeout fails the whole request; adjust the page timeout based on observed endpoint latency.
