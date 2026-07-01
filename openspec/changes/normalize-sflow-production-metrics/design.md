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
