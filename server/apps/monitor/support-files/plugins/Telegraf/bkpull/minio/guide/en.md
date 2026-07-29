# MinIO Monitoring Guide

## Prerequisites

- The target MinIO service exposes Prometheus v2 metrics endpoints.
- The collector node can reach the MinIO API host and port over HTTP. The default port is commonly `9000`.
- The following three endpoints allow anonymous access from the collector node:
  - `/minio/v2/metrics/cluster`
  - `/minio/v2/metrics/bucket`
  - `/minio/v2/metrics/resource`
- If the MinIO metrics endpoints require authentication by default, configure the Prometheus authentication type as `public` on the MinIO side and restrict access to the port within a controlled network.

The current plugin always sends anonymous HTTP requests. It does not send a username, password, or Bearer Token, and it cannot be configured for HTTPS. An environment that permits only HTTPS or authenticated access cannot be integrated directly with the current configuration.

## Setup Steps

1. From the actual collector node, open each of the three MinIO metrics endpoints and confirm that it returns Prometheus text metrics.
2. Select the `MinIO` plugin on the monitoring integration page.
3. Set the collection interval. The default is `60` seconds.
4. In the monitored objects table, select the collector node and enter the MinIO host and API port.
5. Set the instance name and optional group, and then save the configuration.
6. Wait for at least one collection interval before checking the instance or metrics page.

## Pre-checks

Run the following commands from the actual collector node:

```bash
curl -fsS http://<minio-host>:<port>/minio/v2/metrics/cluster | grep '^minio_'
curl -fsS http://<minio-host>:<port>/minio/v2/metrics/bucket | grep '^minio_'
curl -fsS http://<minio-host>:<port>/minio/v2/metrics/resource | grep '^minio_'
```

All three commands should succeed and print Prometheus metrics beginning with `minio_`. Run these checks from the collector node's network. Success from an administrator workstation alone does not prove that the collection path is reachable.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Host | Yes | IP address or hostname of the MinIO API. Do not include `http://`, a port, or a path. |
| Port | Yes | MinIO API port, commonly `9000`. |
| Interval | Yes | Collection interval in seconds. The default is `60`. |
| Node | Yes | Collector node that runs Telegraf. It must be able to reach all three metrics endpoints. |
| Instance Name | Yes | Display name of the instance in the platform. It can be generated from `host:port` by default. |
| Group | No | Optional group for the instance. |

The plugin builds the following fixed URLs from the host and port. No metrics path is entered on the page:

```text
http://<host>:<port>/minio/v2/metrics/cluster
http://<host>:<port>/minio/v2/metrics/bucket
http://<host>:<port>/minio/v2/metrics/resource
```

## Post-setup Verification

After saving the configuration and waiting for at least one collection interval:

1. Confirm that the Telegraf collection task is running normally on the selected node.
2. Confirm that none of the three metrics endpoints returns a connection error, `401`, `403`, or `404`.
3. Confirm that at least the following metrics are queryable in the platform:
   - `minio_cluster_health_status_gauge`
   - `minio_cluster_capacity_usable_free_bytes_gauge`
   - `minio_cluster_drive_online_total_gauge`
4. To verify resource and S3 service data, also check:
   - `minio_node_cpu_avg_idle_gauge`
   - `minio_s3_traffic_received_bytes_counter_rate`

## Troubleshooting

### 1. The endpoint returns `401 Unauthorized` or `403 Forbidden`

- The current plugin does not support a username, password, or Bearer Token.
- Allow the collector node to read the Prometheus metrics endpoints anonymously on the MinIO side, for example by setting the Prometheus authentication type to `public`.
- After making the endpoints public, restrict their source network with a firewall, security group, or another controlled network boundary.

### 2. The endpoint returns `404 Not Found`

- Confirm that the target MinIO version provides the `/minio/v2/metrics/cluster`, `bucket`, and `resource` endpoints.
- Confirm that the configured port is the MinIO API port, not the Console administration port.
- The current plugin cannot change the metrics paths and is not compatible with the legacy `/minio/prometheus/metrics` path.

### 3. HTTP access fails or a TLS error occurs

- The current template generates only `http://` URLs and does not support `https://`.
- Check routing, firewalls, and security groups between the collector node and the MinIO API port.
- If the target forces an HTTPS redirect, the current plugin cannot collect it directly because the protocol does not match.

### 4. Only some MinIO metrics are available

- Check the cluster, bucket, and resource endpoints separately. A failure on any endpoint removes the corresponding group of metrics.
- When there are no buckets or related activities, some Bucket or S3 metric series may be absent.
- Inspect the Telegraf logs for the exact failing URL and HTTP status code.
