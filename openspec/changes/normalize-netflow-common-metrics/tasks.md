## 1. Test Coverage

- [x] 1.1 Add or update node management tests to assert the Telegraf NetFlow converter tags `in_snmp` and `out_snmp`.
- [x] 1.2 Add monitor plugin tests that scan built-in NetFlow metrics and fail if queries reference `netflow_out_bytes` or `netflow_out_packets`.
- [x] 1.3 Add monitor plugin tests that verify interface metrics group flow bytes and packets by `in_snmp` and `out_snmp`.
- [x] 1.4 Add monitor plugin tests that verify overview, protocol, port, endpoint, and conversation metrics use `netflow_in_bytes` or `netflow_in_packets`.

## 2. Collector Normalization

- [x] 2.1 Update the Linux Telegraf default collector `add_config` to convert `in_snmp` and `out_snmp` into tags.
- [x] 2.2 Update the Windows Telegraf default collector `add_config` to convert `in_snmp` and `out_snmp` into tags.
- [x] 2.3 Preserve existing NetFlow v5/v9 listener ports and `netflow_version` tags.
- [x] 2.4 Validate `server/apps/node_mgmt/support-files/collectors/Telegraf.json` remains valid JSON.

## 3. NetFlow Plugin Metrics

- [x] 3.1 Update switch NetFlow metrics to remove `netflow_out_bytes` and `netflow_out_packets` dependencies.
- [x] 3.2 Update router NetFlow metrics to remove `netflow_out_bytes` and `netflow_out_packets` dependencies.
- [x] 3.3 Update firewall NetFlow metrics to remove `netflow_out_bytes` and `netflow_out_packets` dependencies.
- [x] 3.4 Update load balancer NetFlow metrics to remove `netflow_out_bytes` and `netflow_out_packets` dependencies.
- [x] 3.5 Rewrite interface metrics so ingress groups by `in_snmp` and egress groups by `out_snmp` while both use `netflow_in_bytes` or `netflow_in_packets`.
- [x] 3.6 Review metric names and descriptions so they describe Flow bytes/packets and interface direction accurately.
- [x] 3.7 Validate all changed NetFlow `metrics.json` files remain valid JSON.

## 4. Verification and Rollout Notes

- [x] 4.1 Run the targeted node management and monitor plugin tests added for this change.
- [x] 4.2 Run existing Flow access guide and NetFlow listener tests to ensure the v5/v9 endpoint behavior remains intact.
- [x] 4.3 Document the required operational rollout order: `node_init` first, then `repair_node_config`.
- [x] 4.4 Confirm no Flow asset, monitor instance, or onboarding API schema changes are introduced.
