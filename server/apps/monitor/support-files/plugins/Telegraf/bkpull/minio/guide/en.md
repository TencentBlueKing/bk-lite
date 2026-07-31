# MinIO Monitoring Guide

This capability uses Telegraf `inputs.prometheus` to access three fixed MinIO Prometheus v2 endpoints: cluster, bucket, and resource.

## Prerequisites

- The collector node can reach the MinIO API host and port over HTTP.
- All three fixed endpoints allow anonymous reads: `/minio/v2/metrics/cluster`, `/minio/v2/metrics/bucket`, and `/minio/v2/metrics/resource`.
- The current page has only host, port, and interval fields. The template sends no username, password, or Bearer Token and does not generate HTTPS URLs.
- If the MinIO endpoints require authentication or force HTTPS, the current configuration cannot integrate them directly. Restrict anonymous metrics access at the network boundary.

## Setup Steps

1. From the actual collector node, validate all three fixed metrics endpoints.
2. Set the interval (default `60` seconds).
3. In the monitored objects table, select the node and enter only the MinIO API host and port, without a scheme or path.
4. Enter the instance name and optional group, save, and wait for at least one collection interval.

## Pre-checks

The commands below use an example address. `--fail` preserves `4xx/5xx` failures:

```bash
curl --fail --silent --show-error --output /dev/null "http://minio.example.com:9000/minio/v2/metrics/cluster"
curl --fail --silent --show-error --output /dev/null "http://minio.example.com:9000/minio/v2/metrics/bucket"
curl --fail --silent --show-error --output /dev/null "http://minio.example.com:9000/minio/v2/metrics/resource"
```

All three commands must succeed, and they must be run from the actual collector node's network.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Host | Yes | MinIO API IP address or hostname, without `http://`, a port, or a path. |
| Port | Yes | Actual MinIO API port. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can reach all three fixed endpoints. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `minio_cluster_health_status_gauge`
- `minio_cluster_capacity_usable_free_bytes_gauge`
- `minio_cluster_drive_online_total_gauge`
- `minio_node_cpu_avg_idle_gauge`

## Troubleshooting

### The endpoint returns `401` or `403`

- The current template has no authentication fields. Allow anonymous reads from the collector node.
- Do not embed credentials or a token in the Host field.

### The endpoint returns `404`

- Confirm that the configured port is the MinIO API port, not the Console port.
- The paths are fixed to the three Prometheus v2 endpoints; the legacy path is not supported.

### HTTP or TLS fails

- The current template generates HTTP URLs only. An HTTPS-only target cannot be integrated directly.
- Check routing, firewalls, and security groups between the collector node and the MinIO API port.

### Only some data is present

- Validate the cluster, bucket, and resource endpoints separately. A failure on any endpoint removes its corresponding data.
- Some series may be absent when there are no buckets or related activity.
