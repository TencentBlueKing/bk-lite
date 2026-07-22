# Normalize Sflow Production Metrics

Status: done

## Migration Context

- Legacy source: `openspec/changes/normalize-sflow-production-metrics/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

## Context

BK-Lite now has parallel NetFlow and sFlow monitor plugins for network device Flow analysis. The recent `normalize-netflow-common-metrics` change correctly handled NetFlow v5/v9 by treating `netflow_in_bytes` and `netflow_in_packets` as portable flow-record counters and applying `effective_sampling_rate` in plugin queries.

sFlow needs a different contract. Production sFlow data collected from a user environment shows that Telegraf emits fields and labels like:

- Measurements: `sflow_bytes`, `sflow_drops`, `sflow_frame_length`, `sflow_header_length`, `sflow_sampling_rate`, `sflow_tcp_header_length`, `sflow_udp_length`, `sflow_ip_ttl`, `sflow_ip_flags`, `sflow_ip_ecn`, `sflow_ip_fragment_offset`
- Labels: `src_ip`, `dst_ip`, `src_port`, `dst_port`, `src_mac`, `dst_mac`, `input_ifindex`, `output_ifindex`, `sample_direction`, `header_protocol`, `ether_type`, `effective_sampling_rate`, `fallback_sampling_rate`

The decisive sample is:

```text
sflow_frame_length = 263
effective_sampling_rate = 2048
sflow_bytes = 538624
```

Because `263 * 2048 = 538624`, the plugin must treat `sflow_bytes` as already sampling-rate adjusted. Multiplying it again inflates traffic by the sampling rate. The same principle applies to `sflow_packets`, which should be consumed as the Telegraf sFlow packet estimate rather than a raw packet sample requiring a second multiplier.

## Goals / Non-Goals

**Goals:**

- Align sFlow metrics with production sFlow labels and Telegraf sFlow semantics.
- Remove second-pass sampling-rate multiplication from sFlow bytes and packets queries.
- Keep NetFlow sampling-rate normalization unchanged.
- Preserve one sFlow plugin per supported network object type: switch, router, firewall, and load balancer.
- Keep sFlow onboarding, asset matching, collector listener, and access guide behavior compatible.
- Add tests that prevent future sFlow queries from drifting back to NetFlow-style field names or double sampling-rate multiplication.

**Non-Goals:**

- Do not redesign Flow onboarding or asset mapping.
- Do not add a new storage backend or custom NTA pipeline.
- Do not split sFlow by vendor or device model.
- Do not remove `effective_sampling_rate`; keep it for diagnostics and source-of-truth visibility.
- Do not change NetFlow metrics as part of this change, except shared tests may need to distinguish protocol-specific rules.

## Decisions

### 1. Use `sflow_bytes` and `sflow_packets` directly for sFlow traffic

sFlow traffic metrics SHALL aggregate `sflow_bytes` and `sflow_packets` directly. Queries SHALL NOT multiply these measurements by `label_value(..., "effective_sampling_rate")`.

Rationale: production samples show `sflow_bytes` is already equal to `sflow_frame_length * effective_sampling_rate`. A second multiplication produces traffic values that are off by the sampling rate.

Alternative considered: keep multiplying by `effective_sampling_rate` for consistency with NetFlow. Rejected because sFlow and NetFlow Telegraf outputs have different semantics.

### 2. Keep sampling rate as diagnostics, not a traffic operand

The sFlow plugin SHALL keep sampling-rate visibility through metrics or labels such as `device_flow_effective_sampling_rate`, `sflow_sampling_rate`, and `fallback_sampling_rate`, but these values SHALL NOT be used to normalize `sflow_bytes` or `sflow_packets`.

Rationale: users still need to confirm whether device-reported sampling is present and whether fallback sampling was used. That does not mean the value belongs in the traffic formula.

### 3. Align dimensions to production sFlow labels

sFlow protocol, endpoint, port, and conversation metrics SHALL use production labels:

- Source endpoint: `src_ip`
- Destination endpoint: `dst_ip`
- Transport ports: `src_port`, `dst_port`
- Protocol grouping: `header_protocol`; `ether_type` may be exposed as a separate protocol-family dimension where useful
- Interface indexes: `input_ifindex`, `output_ifindex`
- Direction: `sample_direction` when grouping by the reported direction

Rationale: existing queries use `src`, `dst`, and `protocol`, which are NetFlow-style dimensions and do not match observed sFlow production labels.

### 4. Preserve interface direction while avoiding double-counting confusion

Interface metrics SHALL group the same sFlow traffic value by interface direction:

- Ingress interface metrics group by `input_ifindex` and identify direction as ingress.
- Egress interface metrics group by `output_ifindex` and identify direction as egress.
- Queries may use `sample_direction` as a filter or display dimension when it is present, but they must still tolerate records that include interface indexes.

Rationale: production samples contain both `input_ifindex`, `output_ifindex`, and `sample_direction=ingress`. Interface views should remain stable even if some exporters primarily report ingress samples.

### 5. Keep the common Flow metric names unless semantics require a new metric

The plugin SHOULD keep existing unified metric names such as `device_flow_bytes_rate`, `device_flow_protocol_bytes_rate`, and `device_flow_top_conversation_bytes_rate` so dashboards and policies do not need broad schema changes. New sFlow-only diagnostic metrics, such as drop rate from `sflow_drops`, MAY be added if they are useful and low risk.

Rationale: the issue is query semantics and dimensions, not the user-facing Flow plugin shape.

## Proposed sFlow Metric Contract

| Area | Metric behavior |
| --- | --- |
| Device traffic | `sum(sflow_bytes) by (instance_id)` |
| Device packets | `sum(sflow_packets) by (instance_id)` |
| Average frame size | Prefer `avg(sflow_frame_length)` or `sum(sflow_bytes) / sum(sflow_packets)` only if packet semantics are confirmed equivalent |
| Sampling diagnostics | `avg(sflow_sampling_rate)` and/or `avg(label_value(..., "effective_sampling_rate"))` |
| Drops | `sum(sflow_drops) by (instance_id)` if exposed as a stable measurement |
| Interface traffic | group `sflow_bytes` by `input_ifindex` and `output_ifindex` with direction labels |
| Protocol | group by `header_protocol`; optionally expose `ether_type` separately |
| Endpoint | group by `src_ip` and `dst_ip` |
| Conversation | group by `src_ip`, `dst_ip`, `header_protocol`, and `dst_port` |

## Risks / Trade-offs

- [Historical value shift] -> sFlow traffic values will drop by roughly the sampling-rate factor compared with the current double-normalized values. This is expected and correct.
- [Different exporter richness] -> some sFlow exporters may omit ports or output interface indexes. Overview metrics should remain useful; high-cardinality drilldowns may be sparse.
- [Metric name compatibility] -> preserving existing metric names means descriptions must be updated carefully so they no longer imply sFlow traffic is normalized in query formulas.
- [Average packet/frame semantics] -> `sflow_frame_length` is a direct sampled-frame value; `sum(bytes)/sum(packets)` may be valid only if `sflow_packets` carries the same sampling estimate. Prefer explicit tests and wording.

## Migration Plan

1. Add failing tests that encode the sFlow production contract:
   - sFlow byte/packet queries do not multiply by `effective_sampling_rate`.
   - sFlow endpoint/protocol/conversation queries use `src_ip`, `dst_ip`, and `header_protocol`.
   - NetFlow queries continue to apply `effective_sampling_rate`.
2. Update sFlow metrics for switch, router, firewall, and load balancer.
3. Update metric descriptions and translations where they mention normalization in a way that conflicts with sFlow.
4. Validate all changed JSON/YAML files.
5. Run the targeted monitor plugin tests.
6. Re-import or refresh built-in monitor plugin templates through the existing operational path.

Rollback: revert the metric template and test changes, then refresh built-in monitor plugin templates back to the previous version. No database rollback is expected.

## Open Questions

- Should `sflow_drops` become a default supplementary indicator, or remain an advanced diagnostic metric?
- Should protocol charts use only `header_protocol`, or should they expose a separate `ether_type` chart for L2/L3 protocol family analysis?
- Should average size be named "Average Frame Length" for sFlow to avoid conflating sampled frame length with IP packet size?

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-06-24
```

## Capability Deltas

### sflow-production-metrics

## ADDED Requirements

### Requirement: sFlow traffic metrics use Telegraf-adjusted values directly
The system SHALL treat Telegraf sFlow traffic measurements as already sampling-rate adjusted and SHALL NOT apply a second sampling-rate multiplier in sFlow monitor plugin traffic queries.

#### Scenario: Device sFlow byte rate does not multiply sampling rate
- **WHEN** built-in sFlow monitor plugin metrics are imported or tested
- **THEN** sFlow byte-rate queries aggregate `sflow_bytes`
- **AND** those queries do not multiply `sflow_bytes` by `effective_sampling_rate`
- **AND** those queries do not multiply `sflow_bytes` by `sflow_sampling_rate`

#### Scenario: Device sFlow packet rate does not multiply sampling rate
- **WHEN** built-in sFlow monitor plugin metrics are imported or tested
- **THEN** sFlow packet-rate queries aggregate `sflow_packets`
- **AND** those queries do not multiply `sflow_packets` by `effective_sampling_rate`
- **AND** those queries do not multiply `sflow_packets` by `sflow_sampling_rate`

#### Scenario: NetFlow normalization remains separate
- **WHEN** built-in NetFlow monitor plugin metrics are imported or tested
- **THEN** NetFlow byte and packet queries continue to apply the asset's effective sampling rate according to the NetFlow metric contract

### Requirement: sFlow sampling rate is diagnostic metadata
The system SHALL expose sFlow sampling-rate information for diagnostics without using it as a second-pass traffic normalization operand.

#### Scenario: Sampling diagnostics remain visible
- **WHEN** sFlow records include `sflow_sampling_rate`, `effective_sampling_rate`, or `fallback_sampling_rate`
- **THEN** the sFlow plugin can expose sampling-rate metrics or labels for troubleshooting
- **AND** traffic, packet, interface, protocol, endpoint, port, and conversation queries do not use those values as multipliers

### Requirement: sFlow metrics use production sFlow dimensions
The system SHALL group sFlow metrics by labels observed in production sFlow records instead of NetFlow-style labels that are not part of the sFlow production contract.

#### Scenario: Endpoint metrics use sFlow IP labels
- **WHEN** the system queries sFlow endpoint metrics
- **THEN** source endpoint metrics group by `src_ip`
- **AND** destination endpoint metrics group by `dst_ip`
- **AND** endpoint queries do not group by `src` or `dst`

#### Scenario: Protocol metrics use sFlow protocol labels
- **WHEN** the system queries sFlow protocol metrics
- **THEN** protocol metrics group by `header_protocol`
- **AND** protocol queries do not group by `protocol`

#### Scenario: Port metrics use sFlow port labels
- **WHEN** the system queries sFlow port metrics
- **THEN** source port metrics group by `src_port`
- **AND** destination port metrics group by `dst_port`

#### Scenario: Conversation metrics use sFlow conversation labels
- **WHEN** the system queries top sFlow conversations
- **THEN** conversation metrics group by `src_ip`, `dst_ip`, `header_protocol`, and `dst_port`
- **AND** conversation metrics do not group by `src`, `dst`, or `protocol`

### Requirement: sFlow interface direction uses interface indexes and direction labels
The system SHALL represent sFlow interface traffic direction through production sFlow interface labels.

#### Scenario: Ingress interface metrics use input interface index
- **WHEN** the system queries ingress interface traffic for sFlow
- **THEN** the query groups `sflow_bytes` or `sflow_packets` by `input_ifindex`
- **AND** the resulting series identifies the direction as ingress

#### Scenario: Egress interface metrics use output interface index
- **WHEN** the system queries egress interface traffic for sFlow
- **THEN** the query groups `sflow_bytes` or `sflow_packets` by `output_ifindex`
- **AND** the resulting series identifies the direction as egress

#### Scenario: Reported sample direction remains available
- **WHEN** sFlow records include `sample_direction`
- **THEN** queries or rendered dimensions may expose `sample_direction` as diagnostic context
- **AND** the interface query contract still works from `input_ifindex` and `output_ifindex`

### Requirement: Existing sFlow onboarding contracts remain compatible
The system SHALL preserve existing Flow asset and monitor instance contracts while changing sFlow metric query behavior.

#### Scenario: Existing sFlow assets continue to match incoming records
- **WHEN** an existing Flow asset has `sflow` enabled
- **THEN** incoming sFlow records that match the asset source IP continue to receive `instance_id`, `instance_type`, `collect_type`, `effective_sampling_rate`, and `fallback_sampling_rate`

#### Scenario: sFlow listener and access guide stay stable
- **WHEN** a user opens the sFlow access guide
- **THEN** the system continues to present the existing sFlow listener endpoint and UDP port
- **AND** no user-facing split by vendor or sFlow variant is introduced

## Work Checklist

## 1. Test Coverage

- [x] 1.1 Add monitor plugin tests that assert sFlow bytes/packets queries do not multiply by `effective_sampling_rate` or `sflow_sampling_rate`.
- [x] 1.2 Update shared Flow metric tests so NetFlow still requires sampling-rate normalization while sFlow explicitly forbids second-pass normalization.
- [x] 1.3 Add monitor plugin tests that assert sFlow endpoint metrics group by `src_ip` and `dst_ip`, not `src` and `dst`.
- [x] 1.4 Add monitor plugin tests that assert sFlow protocol and conversation metrics use `header_protocol`, not `protocol`.
- [x] 1.5 Add monitor plugin tests that assert sFlow interface metrics use `input_ifindex` and `output_ifindex`.

## 2. sFlow Plugin Metrics

- [x] 2.1 Update switch sFlow metrics to use `sflow_bytes` and `sflow_packets` directly.
- [x] 2.2 Update router sFlow metrics to use `sflow_bytes` and `sflow_packets` directly.
- [x] 2.3 Update firewall sFlow metrics to use `sflow_bytes` and `sflow_packets` directly.
- [x] 2.4 Update load balancer sFlow metrics to use `sflow_bytes` and `sflow_packets` directly.
- [x] 2.5 Rewrite sFlow endpoint metrics to group by `src_ip` and `dst_ip`.
- [x] 2.6 Rewrite sFlow protocol metrics to group by `header_protocol`.
- [x] 2.7 Rewrite sFlow conversation metrics to group by `src_ip`, `dst_ip`, `header_protocol`, and `dst_port`.
- [x] 2.8 Review sFlow interface metrics so ingress uses `input_ifindex` and egress uses `output_ifindex`.
- [x] 2.9 Decide whether to add `sflow_drops` and/or `sflow_frame_length` as sFlow diagnostic metrics.

## 3. Descriptions and Translations

- [x] 3.1 Update sFlow metric descriptions so they no longer imply query-time sampling-rate normalization.
- [x] 3.2 Update bilingual metric translations for any renamed or newly added sFlow diagnostic metrics.
- [x] 3.3 Keep existing user-facing Flow plugin names and low-cardinality default indicators unless a metric is intentionally added or removed.

## 4. Validation and Rollout Notes

- [x] 4.1 Validate all changed sFlow `metrics.json` files remain valid JSON.
- [x] 4.2 Run targeted monitor plugin metric tests.
- [x] 4.3 Confirm Flow onboarding, access guide, and asset-mapping tests still pass without schema changes.
- [x] 4.4 Document the operational refresh path for built-in monitor plugin templates after deployment.
- [x] 4.5 Add and run a local sFlow production contract script that checks the screenshot sample math, production labels, and no second-pass sampling normalization.
