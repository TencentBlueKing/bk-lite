# ElasticSearch Monitoring Guide

## Prerequisites

- Elasticsearch HTTP service is up (default port `9200`).
- The collector node can reach the Elasticsearch endpoint (security groups / firewalls opened).
- A username and password with permission to query cluster health and node stats are ready.
- The Server Address field must be a full URL starting with `http://` or `https://`, for example `http://10.0.0.10:9200`.

## Recommended Permissions

The account should at least access:

- `GET /_cluster/health`
- `GET /_nodes/stats`

Prefer a dedicated read-only monitoring account instead of a high-privilege admin account.

## Setup Steps

1. Verify connectivity from the collector node to Elasticsearch.
2. Fill in username, password, and interval (default `60s`) on the configure page.
3. Add rows in the monitored objects table for node, server address, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

Without authentication (only if allowed):

```bash
curl -sS "http://<host>:9200/_cluster/health?pretty"
```

With Basic Auth:

```bash
curl -sS -u "<username>:<password>" "http://<host>:9200/_cluster/health?pretty"
```

Node stats:

```bash
curl -sS -u "<username>:<password>" "http://<host>:9200/_nodes/stats?pretty"
```

The endpoint is basically healthy when:

- HTTP status is `200`
- `_cluster/health` returns fields such as `status` and `number_of_nodes`

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Username | Yes | Account for Elasticsearch HTTP APIs |
| Password | Yes | Password for that account |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Server Address | Yes | Full URL such as `http://localhost:9200` |
| Instance Name | Yes | Display name in the platform |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Verify protocol and port in the server address.
- Re-run the `curl` checks from the collector node, not only from your laptop.
- Wait for at least one collection interval.
- Confirm Telegraf / collection tasks are healthy on the node.

### 2. Authentication failures (401 / 403)

- Check username/password for accidental spaces.
- Confirm the account can read `_cluster/health` and `_nodes/stats`.
- If extra security plugins are enabled, allow the collector node IP.

### 3. HTTPS / certificate issues

- The template sets `insecure_skip_verify = true` by default.
- If it still fails, confirm the URL scheme and whether a custom CA is required.

### 4. Partial missing metrics

- Cluster health metrics require `cluster_health = true`.
- Node, breaker, HTTP, and thread-pool metrics depend on `node_stats`.
- Permission gaps can make health succeed while node stats fail; validate both APIs separately.
