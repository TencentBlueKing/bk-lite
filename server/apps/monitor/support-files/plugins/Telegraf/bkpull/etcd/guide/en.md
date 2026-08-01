# Etcd Monitoring Guide

This plugin uses Telegraf to pull the etcd Prometheus endpoint directly. The page expects one complete URL containing the scheme, host, port, and metrics path.

## Prerequisites

- etcd exposes a Prometheus endpoint, normally `/metrics`.
- The collector node can reach the complete URL; a host-and-port check alone is insufficient.
- For HTTPS, the CA, client certificate, and client key files are present on the collector node and readable by the collector process.
- Prefer a trusted CA. Enable **Skip Certificate Verification** only for temporary troubleshooting after accepting the certificate-spoofing risk.

## Setup Steps

1. Run the pre-check from the collector node and confirm that the complete metrics URL succeeds.
2. On the Etcd configuration page, enter the URL, optional TLS file paths, collection interval, and certificate-verification setting.
3. In the monitored-objects table, select a node and enter the same complete URL, an instance name, and an optional group.
4. Save the configuration and wait for at least one collection interval. The default interval is `60` seconds.

## Pre-checks

HTTP example:

```bash
ETCD_METRICS_URL=http://127.0.0.1:2379/metrics
curl --fail-with-body --silent --show-error "$ETCD_METRICS_URL" --output /tmp/etcd-metrics.txt
grep -E -m 4 '^(etcd_|process_)' /tmp/etcd-metrics.txt
```

HTTPS with mutual TLS:

```bash
ETCD_METRICS_URL=https://etcd-1.example.com:2379/metrics
curl --fail-with-body --silent --show-error \
  --cacert /etc/ssl/etcd/ca.pem \
  --cert /etc/ssl/etcd/client.pem \
  --key /etc/ssl/etcd/client-key.pem \
  "$ETCD_METRICS_URL" --output /tmp/etcd-metrics.txt
grep -E -m 4 '^(etcd_|process_)' /tmp/etcd-metrics.txt
```

`curl` must exit with status `0`, and the output must contain etcd Prometheus metrics. Do not substitute a TCP-only result for the complete URL check.

## Field Reference

| Field | Required | Default | Description |
| --- | --- | --- | --- |
| URL | Yes | None | Complete `http://` or `https://` metrics URL, for example `http://127.0.0.1:2379/metrics`. |
| CA Certificate Path | No | None | Path on the collector node to the CA file used to verify the HTTPS server. |
| Client Certificate Path | No | None | Path to the mTLS client certificate; use it together with the client key. |
| Client Key Path | No | None | Path to the mTLS client private key; restrict its file permissions. |
| Interval | Yes | `60` seconds | Telegraf pull interval; minimum `1` second. |
| Skip Certificate Verification | No | Off | Disables HTTPS server-certificate verification. Keep it off in production. |
| Node | Yes | None | Collector node that performs the pull. |
| URL (monitored object) | Yes | None | Complete metrics URL for this instance; it must be unique within the configuration. |
| Instance Name | Yes | None | Display name in the platform; it can be initialized from the URL and then adjusted. |
| Group | No | None | Optional instance group. |

The template fixes both request and response timeouts at `30` seconds. There are no separate scheme, host, port, or metrics-path fields.

## Post-setup Verification

1. Wait for at least one interval and confirm that the instance status updates in the platform.
2. On the metrics page, confirm data for the target instance from at least one of these registered metrics:
   - `etcd_server_has_leader_gauge`
   - `etcd_backend_allocated_usage_percent`
   - `etcd_server_proposals_pending_gauge`
   - `etcd_disk_wal_fsync_p99_seconds`
3. If the instance exists but metrics are missing, repeat the complete URL check and verify the TLS paths on the actual collector node.

## Troubleshooting

### The URL returns 404

The page does not append `/metrics`. Ensure the URL includes the path actually exposed by the target.

### TLS handshake or certificate verification fails

Check the CA chain, certificate validity, hostname, and mTLS certificate/key pair. Fix the certificate configuration instead of treating permanent verification bypass as a solution.

### The request times out

Test the complete URL from the configured collector node. The template timeout is fixed at `30` seconds; an open TCP port does not prove the HTTP metrics response works.

### Setup succeeds but no etcd metrics appear

Confirm that the downloaded body is Prometheus text containing `etcd_` metrics rather than a proxy login page or another service.
