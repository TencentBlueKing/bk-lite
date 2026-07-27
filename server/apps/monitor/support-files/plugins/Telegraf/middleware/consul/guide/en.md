# Consul Monitoring Guide

This plugin uses Telegraf `inputs.consul` to call the HashiCorp Consul HTTP API and collect only health-check states — Consul telemetry itself is not included. If you need telemetry, expose it via the StatsD protocol on your own. The default Consul HTTP API port is `8500`.

## Prerequisites

- The target Consul cluster is up; the default HTTP API port is `8500`.
- The collector node can reach the Consul host (security groups / firewalls opened).
- Health checks and services are registered with Consul (the `consul_health_checks` measurement originates from `/v1/health/service/:name` and `/v1/health/state/:state`).
- If ACLs are enabled, prepare a token for the monitoring account.

> Telegraf outputs a single measurement `consul_health_checks`, tagged with `node`, `service_name`, `check_id`, `check_name`, `service_id`, `status`. The fields are integer counters `passing`, `critical`, `warning`.

## Recommended Permissions

By default, Consul health-check endpoints are publicly readable and require no ACL. If ACLs are enabled, a read-only policy is enough:

```hcl
# monitor token: health-related read only
acl = "write"
```

```bash
# recommended: explicit read-only policy
consul acl policy create -name monitor-read -rules - <<EOF
service ".*" {
  policy = "read"
}
operator = "read"
EOF

consul acl token create -description "monitor" -policy-name monitor-read
```

## Setup Steps

1. Verify the Consul API is reachable from the collector node:

   ```bash
   curl http://<host>:8500/v1/status/leader
   ```

2. On the configure page, fill in the URL (default `http://<host>:8500`) and interval (default `60s`).
3. Add rows in the monitored objects table for node, URL, instance name, and group.
4. Click Confirm and wait for at least one collection interval.
5. Check the asset or metrics page to confirm data is reporting.

## Pre-check Commands

Consul API reachability:

```bash
curl http://<host>:8500/v1/health/service/consul
```

HTTP 200 with a JSON array indicates the endpoint is healthy.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| URL | Yes | Consul HTTP API address, e.g. `http://10.0.0.5:8500` |
| Interval | Yes | Collection interval in seconds, default `60` |
| Node | Yes | Collector node used for this instance |
| Instance Name | Yes | Display name in the platform; defaults to the URL |
| Group | No | Organization group for ownership/permission |

## Troubleshooting

### 1. No data after saving

- Confirm Consul is running and port `8500` is reachable.
- Run `curl /v1/status/leader` from the collector node.
- Wait for at least one collection interval; confirm Telegraf / collection tasks are healthy on the node.

### 2. Authentication failures

- After enabling Consul ACLs, add `token = "<token>"` to `inputs.consul`. The current Telegraf template omits this; if you enable ACLs, also adjust the template and inject the token via env_config.
- Check `acl.tokens.default` and `acl.enabled` are consistent in the Consul server config.

### 3. Partial missing metrics

- `consul_health_checks` reports health-check state only — runtime / telemetry metrics are not included. Use `inputs.prometheus` against `/v1/agent/metrics` if you enabled it.
- Field naming differs across Consul versions. `metric_version = 2` (the default from Consul v1.16) moves string fields to tags; upgrade to at least v1.16 if possible.
- When no services are registered, only node-level checks such as `serfHealth` will appear — that is normal.