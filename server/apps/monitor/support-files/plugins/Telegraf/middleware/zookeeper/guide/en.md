# ZooKeeper Monitoring Guide

This plugin uses Telegraf `inputs.zookeeper` to periodically issue the `mntr` command against ZooKeeper's client port (default `2181`) and collect cluster node counts, average latency, connection counts, watch / znode counts, and other runtime metrics. If the target ZooKeeper has the Prometheus Metric Provider enabled (`metricsProvider.httpPort=7000`), prefer `inputs.prometheus` against `/metrics` instead.

## Prerequisites

- The target ZooKeeper is running; the default client port is `2181`.
- The collector node can reach the ZooKeeper host (security groups / firewalls opened).
- The `mntr` four-letter command is enabled on the server (the default; if `4lw.commands.whitelist` is set, make sure it includes `mntr`).
- The template supports multiple `servers` to scrape all followers / leaders in a cluster.

> Telegraf sends `mntr\n` over TCP to `2181` and parses each `zk_xxx value` line, producing a single `zookeeper` measurement tagged with `server`, `port`, `state`. Leader-only fields (`followers`, `synced_followers`, `pending_syncs`) are populated accordingly.

## Recommended Permissions

`mntr` requires no authentication; restrict at the network layer or via ACLs:

```properties
# conf/zoo.cfg
4lw.commands.whitelist=mntr,conf,envi,ruok,srvr,stat
# or only mntr
4lw.commands.whitelist=mntr

# bind to an internal interface only
clientPortAddress=10.0.0.5
clientPort=2181
```

If SASL / Digest auth is enabled, the monitor account needs `read` permission (ACL only — `mntr` does not require a session).

## Setup Steps

1. Verify `mntr` from the collector node:

   ```bash
   echo mntr | nc <host> 2181
   ```

   The response should contain 14–17 lines of `zk_xxx value`.

2. On the configure page, fill in the Server Address (`host:port`, e.g. `10.0.0.5:2181`), Timeout (default `10s`), and Interval (default `60s`).
3. Add rows in the monitored objects table for node, server address, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

`mntr` reachability:

```bash
echo mntr | nc <host> 2181
```

A healthy server returns 14–17 lines of `zk_xxx value` text.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Server Address | Yes | ZooKeeper client address in `host:port` form, e.g. `10.0.0.5:2181` |
| Timeout | Yes | Maximum wait in seconds for a single `mntr` call, default `10` |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform; defaults to the Server Address |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Confirm ZooKeeper is running and `nc <host> 2181` + `mntr` returns output.
- Confirm `4lw.commands.whitelist` includes `mntr`; ZK 3.5+ with a whitelist restricted to `stat` / `ruok` will refuse the call.
- Wait for at least one collection interval; confirm Telegraf / collection tasks are healthy on the node.

### 2. Connection timeouts

- Adjust the Timeout field (recommend `5s~30s`); too short can produce false negatives during busy periods.
- Verify the firewall / security group allows TCP `2181`.

### 3. Partial missing metrics

- `followers` / `synced_followers` / `pending_syncs` are populated only on the leader; follower nodes show 0 for these.
- `zk_ephemerals_count` is non-zero only when ephemeral znodes exist.
- The `version` field varies slightly across versions — that is normal.
- If the cluster has the Prometheus Metric Provider enabled, prefer `inputs.prometheus` against `http://<host>:7000/metrics` for richer metrics.