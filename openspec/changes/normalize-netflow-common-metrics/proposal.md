## Why

NetFlow v5 and v9 are received by separate Telegraf listeners, but the monitor plugin currently treats all NetFlow data as if `out_bytes` and `out_packets` are stable fields. That assumption is fragile across v5/v9 exporters and can leave overview, interface, protocol, port, endpoint, and conversation metrics empty or inconsistent for some switches.

This change normalizes the NetFlow metric contract around fields that are common to v5/v9 flow records, while preserving the single NetFlow plugin experience for users.

## What Changes

- Keep one NetFlow monitor plugin for v5 and v9 instead of splitting user-facing plugins.
- Keep the collector-side listeners separated:
  - NetFlow v5 listens on UDP 2055.
  - NetFlow v9 listens on UDP 2056.
- Extend the Telegraf base converter so NetFlow interface fields used by metrics, especially `in_snmp` and `out_snmp`, become queryable tags.
- Update NetFlow plugin metric queries to use common fields:
  - `netflow_in_bytes`
  - `netflow_in_packets`
  - `src`, `dst`, `src_port`, `dst_port`, `protocol`
  - `in_snmp`, `out_snmp`
- Remove NetFlow plugin query dependency on `netflow_out_bytes` and `netflow_out_packets`.
- Define interface direction by aggregating the same flow bytes/packets by `in_snmp` for ingress and `out_snmp` for egress.
- Preserve `netflow_version` as a diagnostic tag, not as a plugin split.
- Keep existing Flow onboarding, asset binding, and detection APIs compatible.

## Capabilities

### New Capabilities

- `netflow-common-metrics`: Defines the normalized NetFlow v5/v9 metric contract, collector preprocessing requirements, and monitor plugin query behavior.

### Modified Capabilities

- None.

## Impact

- **Node management collector definition**: `server/apps/node_mgmt/support-files/collectors/Telegraf.json` and tests under `server/apps/node_mgmt/tests/`.
- **Monitor NetFlow plugin templates**: `server/apps/monitor/support-files/plugins/Telegraf/netflow/*/metrics.json`.
- **Monitor plugin tests**: targeted tests validating NetFlow metrics avoid non-common `out_*` fields and use interface tags consistently.
- **Operational rollout**: after deployment, built-in collector definitions must be synced with `node_init`, then existing node configs repaired with `repair_node_config`.
- **No API/model break**: Flow assets, protocol selection, plugin IDs, and monitor instance schemas remain unchanged.
