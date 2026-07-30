# ZooKeeper Monitoring Guide

This capability uses Telegraf `inputs.zookeeper` to send the `mntr` four-letter command to one ZooKeeper client address.

## Prerequisites

- The collector node can reach one target ZooKeeper `host:port`.
- The server explicitly allows `mntr`. If `4lw.commands.whitelist` is configured, it must include `mntr`.
- The current page accepts one server address, and the template creates one `servers` entry from that value.
- The current page and template have no authentication fields. A target that requires an authenticated session cannot be integrated directly.

## Setup Steps

1. From the actual collector node, confirm that the target address accepts `mntr`.
2. Enter one Server Address, the timeout (default `10` seconds), and the interval (default `60` seconds).
3. In the monitored objects table, select the node and enter the same Server Address, instance name, and optional group.
4. Save the configuration and wait for at least one collection interval.

## Pre-checks

```bash
printf 'mntr\n' | nc -w 10 zk.example.com 2181
```

The response must contain multiple key/value lines beginning with `zk_`. If the response says the four-letter command is not in the whitelist, enable `mntr` on ZooKeeper according to the environment's security policy.

## Field Reference

| Field | Required | Description |
| --- | --- | --- |
| Server Address | Yes | One ZooKeeper client address in `host:port` form. |
| Timeout | Yes | Per-request timeout in seconds; default `10`. |
| Interval | Yes | Collection interval in seconds; default `60`. |
| Node | Yes | Collector node that can reach the client address. |
| Instance Name | Yes | Display name in the platform. |
| Group | No | Optional instance group. |

## Post-setup Verification

After saving and waiting for one interval, confirm that these metrics are queryable in the platform:

- `zookeeper_num_alive_connections`
- `zookeeper_outstanding_requests`
- `zookeeper_avg_latency`
- `zookeeper_znode_count`

## Troubleshooting

### `mntr` returns nothing or is rejected

- Confirm that `4lw.commands.whitelist` explicitly includes `mntr`.
- Validate both the network and the command from the actual collector node; a listening port alone is not sufficient.

### Only one cluster member has data

- The current UI configures one server address and cannot enter multiple servers in one instance.
- To observe multiple members, create separate monitored objects within the current product model.

### The target requires an authenticated session

- The current template has no authentication fields. A target that requires an authenticated session is outside the current capability.
