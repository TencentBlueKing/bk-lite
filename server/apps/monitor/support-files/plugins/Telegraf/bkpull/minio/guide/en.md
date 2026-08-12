# MinIO Multi-version Monitoring Guide

This capability uses Telegraf's Prometheus collector to scrape official MinIO Metrics v2/v3, covering cluster health, capacity, request traffic, and node resources.

## Version Selection

| MinIO release | Selection | Notes |
| --- | --- | --- |
| Before `RELEASE.2021-01-30` | Unsupported | Legacy Metrics v1 is out of scope. |
| `RELEASE.2021-01-30` through `RELEASE.2024-05-27` | v2 | Uses compatibility endpoints. |
| `RELEASE.2024-05-28` and later | v3 (recommended) | Uses the complete set of core Metrics v3 groups. |

Metrics v3 first appeared in `RELEASE.2024-03-15`, but the early interface was still evolving, so this integration uses `RELEASE.2024-05-28` as its complete-core baseline. Current MinIO source still registers both v2 and v3; there is no “supported only through 2024-07-15” upper limit.

Existing instances without the new fields continue as `v2 + HTTP + public` with the original cluster, bucket, and resource endpoints. New instances default to `v3 + HTTPS + Bearer Token`.

## Prerequisites

- Enter the MinIO **API port**, not the Console administration port. API and Console commonly use `9000` and `9001`, respectively, but your deployment is authoritative.
- Use HTTPS in production and make the server certificate chain trusted by the collector node. Skip-certificate-verification is only for temporary diagnosis.
- Bearer Token is the default authentication mode. Do not enter an Access Key, Secret Key, username/password, or the `Bearer ` prefix.
- Create a dedicated identity with only `admin:Prometheus`, then generate a token using the corresponding `mc` alias. Explicitly select v3; with current `mc`, omitting `--api-version` generates a v2 scrape configuration:

```bash
mc admin prometheus generate ALIAS --api-version v3
```

If `mc` does not recognize `--api-version`, update `mc` first. Older `mc admin prometheus generate ALIAS` still produces a Bearer token, but its generated scrape configuration targets v2; before using that token, validate the v3 endpoint selected on this page with the command below.

The token is injected through a collector environment variable and is not written into the Telegraf TOML body. Select Public only when the server explicitly sets `MINIO_PROMETHEUS_AUTH_TYPE=public`; never expose anonymous metrics directly to the public Internet.

## Core and Extension Metrics

- v2 core endpoints: `/minio/v2/metrics/cluster` and `/minio/v2/metrics/resource`.
- Earlier than `RELEASE.2023-10-07T15-07-38Z`, v2 does not yet expose `/minio/v2/metrics/resource`. Telegraf reports 404 for that URL while continuing to collect the metrics available from the cluster endpoint. If persistent 404 logs are unacceptable, upgrade MinIO before enabling this integration. BK-Lite does not remove endpoints or fall back at runtime.
- v3 core endpoints: `/api/requests`, `/cluster/health`, `/cluster/erasure-set`, `/cluster/usage/objects`, `/system/cpu`, `/system/memory`, `/system/drive`, `/system/process`, and `/system/network/internode`, all under `/minio/metrics/v3`.
- Bucket extension: the v2 bucket endpoint or v3 `/cluster/usage/buckets`. The first release does not page through every `/bucket/.../<bucket>` detail endpoint.
- Replication, lifecycle, audit/notification, and IAM/KMS are opt-in. KMS metrics come from the v2 cluster endpoint; the current official v3 groups expose IAM without a separate KMS endpoint.

The template uses `namepass` to write only selected core and extension families and excludes the TTFB histogram to control cardinality. Every series includes `minio_metrics_version=v2|v3`.

## Minimum Metric Versions

Each metric's Description field shows its full minimum MinIO release. The table below summarizes the registered metric families. On an older release, an endpoint may respond successfully while a particular metric is still absent. The recommended complete-core baseline remains `RELEASE.2024-05-28T17-19-04Z` for v3; selected extensions must also meet their later minimums below.

| API | Registered metrics | Minimum MinIO release |
| --- | --- | --- |
| v2 | Cluster capacity, online/offline drives and nodes, S3 traffic | `RELEASE.2021-01-30T00-20-58Z` |
| v2 | Waiting S3 requests | `RELEASE.2021-02-23T20-05-01Z` |
| v2 | Process uptime | `RELEASE.2021-03-26T00-00-41Z` |
| v2 | Rejected S3 authentication | `RELEASE.2021-04-18T19-26-29Z` |
| v2 | Process CPU and resident memory | `RELEASE.2021-05-11T23-27-41Z` |
| v2 | Scanner objects scanned | `RELEASE.2021-12-18T04-42-33Z` |
| v2 | Current incoming S3 requests | `RELEASE.2022-02-12T00-51-25Z` |
| v2 | S3 5xx errors | `RELEASE.2022-06-10T16-59-15Z` |
| v2 | KMS internal request failures | `RELEASE.2022-07-13T23-29-44Z` |
| v2 | Cluster health status | `RELEASE.2023-08-04T17-40-21Z` |
| v2 | Resource CPU and drive I/O/utilization | `RELEASE.2023-10-07T15-07-38Z` |
| v2 | Resource memory-used percentage | `RELEASE.2023-12-07T04-16-00Z` |
| v2 | Erasure-set online drives | `RELEASE.2023-12-23T07-19-11Z` |
| v2 | Erasure-set health status | `RELEASE.2024-01-28T22-35-53Z` |
| v3 | API requests, cluster health/capacity, erasure sets, object usage, internode network | `RELEASE.2024-03-15T01-07-19Z` |
| v3 | System memory and drives | `RELEASE.2024-04-18T19-09-19Z` |
| v3 | System CPU, process, and notification errors | `RELEASE.2024-04-28T17-53-50Z` |
| v3 | IAM synchronization failures | `RELEASE.2024-05-07T06-41-25Z` |
| v3 | Scanner and Audit | `RELEASE.2024-05-27T19-17-46Z` |
| v3 | ILM | `RELEASE.2024-06-06T09-36-42Z` |
| v3 | Bucket usage after the endpoint fix used by this integration | `RELEASE.2024-07-15T19-02-30Z` |
| v3 | Recent replication backlog | `RELEASE.2024-08-03T04-33-23Z` |

## Setup

1. Validate the selected version, scheme, and authentication mode from the actual collector node.
2. For a new instance, explicitly confirm the metrics API version, scheme, and authentication mode.
3. Enter the API host and port. Do not include a scheme, port, or path in Host.
4. Enable only required extensions, save, and wait at least one collection interval.

Bearer v3 example:

```bash
export MINIO_METRICS_TOKEN='Token from mc admin prometheus generate output'
curl --fail --silent --show-error \
  -H "Authorization: Bearer ${MINIO_METRICS_TOKEN}" \
  "https://minio.example.com:9000/minio/metrics/v3/cluster/health"
```

Public v2 example:

```bash
curl --fail --silent --show-error \
  "http://minio.example.com:9000/minio/v2/metrics/cluster"
```

Do not print real tokens in shell history, platform logs, or tickets. In production, do not use `curl -k` instead of installing the correct CA trust.

## Fields

| Field | Description |
| --- | --- |
| Metrics API Version | Defaults to v3 for new instances; select v2 for older releases. |
| Scheme | Defaults to HTTPS. HTTP is only for isolated trusted networks. |
| Authentication | Defaults to Bearer; Public must match an explicit server setting. |
| Bearer Token | Encrypted field shown only for Bearer and injected through the environment. |
| Metric Extensions | Multi-select and disabled by default; only selected groups are collected in addition to core metrics. |
| Skip Certificate Verification | Disabled by default and intended only for temporary diagnosis. |
| Host and Port | The MinIO API address, not the Console address. |

## Troubleshooting

- `401/403`: the token is missing, wrong, expired, or lacks `admin:Prometheus`; or Public does not match server configuration.
- `404`: the selected version path is wrong, or the Console port was entered. This integration does not perform runtime fallback.
- TLS failure: check the certificate chain, hostname, and the collector node's system CA; do not leave verification disabled.
- Partial metrics: verify that the corresponding extension is enabled and the MinIO feature has emitted data. MinIO omits metrics with no value.
