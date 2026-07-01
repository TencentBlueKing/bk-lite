## Why

The built-in sFlow monitor plugins currently treat `sflow_bytes` and `sflow_packets` as raw sampled values and multiply them by `effective_sampling_rate` in every traffic query. Production sFlow samples show that this assumption is wrong for the Telegraf sFlow input used by BK-Lite: `sflow_bytes` already contains the sampled frame length multiplied by the sampling rate. One user sample reports `sflow_frame_length=263`, `effective_sampling_rate=2048`, and `sflow_bytes=538624`, which exactly matches `263 * 2048`.

The current sFlow metrics also group by NetFlow-style labels such as `src`, `dst`, and `protocol`, while production sFlow data exposes labels such as `src_ip`, `dst_ip`, `header_protocol`, `ether_type`, `input_ifindex`, `output_ifindex`, and `sample_direction`. This mismatch can make protocol, endpoint, port, interface, and conversation charts empty or misleading.

This change normalizes the sFlow plugin metric contract around the labels and values observed in production and the Telegraf sFlow output model, while keeping the existing sFlow onboarding flow and monitor plugin experience.

## What Changes

- Update sFlow monitor plugin metric queries for switch, router, firewall, and load balancer objects to use `sflow_bytes` and `sflow_packets` directly.
- Stop multiplying sFlow traffic metrics by `effective_sampling_rate`.
- Keep `effective_sampling_rate`, `fallback_sampling_rate`, and `sflow_sampling_rate` as diagnostic sampling labels/metrics rather than traffic normalization operands.
- Align sFlow grouping dimensions with production labels:
  - `src_ip`, `dst_ip`
  - `src_port`, `dst_port`
  - `header_protocol`, with `ether_type` available for protocol-family views where appropriate
  - `input_ifindex`, `output_ifindex`, `sample_direction`
- Add or update tests so NetFlow continues to require sampling-rate normalization, while sFlow explicitly rejects second-pass sampling-rate multiplication.
- Add checks that built-in sFlow queries avoid unsupported NetFlow-style labels (`src`, `dst`, `protocol`) when production sFlow labels are required.
- Preserve existing Flow onboarding, asset binding, access guide, and collector listener contracts.

## Capabilities

### New Capabilities

- `sflow-production-metrics`: Defines the production-aligned sFlow metric contract, query behavior, dimensions, and validation rules.

### Modified Capabilities

- None.

## Impact

- **Monitor sFlow plugin templates**: `server/apps/monitor/support-files/plugins/Telegraf/sflow/*/metrics.json`.
- **Monitor plugin tests**: `server/apps/monitor/tests/test_flow_plugin_metrics.py` and any focused tests added for sFlow production query behavior.
- **Metric language/display text**: metric names/descriptions may need small wording changes so sampling-rate diagnostics are not described as traffic normalization inputs for sFlow.
- **No API/model break**: Flow assets, enabled protocols, instance IDs, access guide endpoints, and collector listener ports remain unchanged.
- **Operational rollout**: after deployment, built-in monitor plugin templates must be re-imported or refreshed through the existing plugin initialization flow used for built-in monitor template updates.
