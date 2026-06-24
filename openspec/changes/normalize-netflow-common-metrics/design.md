## Context

BK-Lite currently models network device Flow analysis as user-facing NetFlow and sFlow monitor plugins. NetFlow v5 and v9 now use separate Telegraf UDP listeners, but the user-facing plugin remains a single NetFlow template. That is the right product shape: switch operators usually think "NetFlow" first, then choose the export version supported by the device.

The fragile part is the metric contract. The current NetFlow plugin queries frequently combine `netflow_in_bytes` with `netflow_out_bytes`, and `netflow_in_packets` with `netflow_out_packets`. NetFlow v5 and v9 exporters consistently provide flow-record bytes/packets, endpoints, ports, protocol, and input/output interface indexes, but they do not provide a portable pair of independent `out_bytes` and `out_packets` fields across all devices and versions.

Current node management Telegraf base config also converts only `protocol`, `src`, `src_port`, `dst`, and `dst_port` into tags. The monitor plugin queries use `in_snmp` and `out_snmp` as dimensions, so those interface fields must also become tags before VictoriaMetrics can reliably group by them.

## Goals / Non-Goals

**Goals:**

- Preserve one user-facing NetFlow plugin for both v5 and v9.
- Keep separate collector listeners for v5 and v9 because Telegraf protocol decoding is configured per listener.
- Normalize NetFlow metrics around v5/v9 common flow fields.
- Make interface-level queries stable by exposing `in_snmp` and `out_snmp` as tags.
- Remove query dependency on `netflow_out_bytes` and `netflow_out_packets`.
- Keep existing Flow asset onboarding, protocol selection, detection, and instance schemas compatible.

**Non-Goals:**

- Do not split NetFlow v5 and v9 into separate monitor plugins.
- Do not introduce new database models or migrations.
- Do not change sFlow metric semantics in this change, except where shared tests need to distinguish NetFlow behavior.
- Do not add IPFIX support beyond preserving Telegraf's future extension path.
- Do not require users to recreate existing Flow assets.

## Decisions

### 1. Keep one NetFlow plugin, split only the collector listeners

NetFlow v5 and v9 SHALL remain represented by one monitor plugin. Node management Telegraf base config SHALL keep independent listeners:

```toml
[[inputs.netflow]]
    protocol = "netflow v5"
    service_address = "udp://:2055"

[[inputs.netflow]]
    protocol = "netflow v9"
    service_address = "udp://:2056"
```

Rationale: listener separation is a collector decoding concern; plugin separation would duplicate templates, policies, dashboards, and user workflows without solving the common-field issue.

Alternative considered: create `NetFlow v5` and `NetFlow v9` plugins. Rejected because it pushes protocol implementation detail into the user workflow and doubles maintenance for the same logical analysis model.

### 2. Treat `netflow_in_bytes` and `netflow_in_packets` as flow record counters, not device ingress direction

The NetFlow plugin SHALL use `netflow_in_bytes` and `netflow_in_packets` as the canonical bytes/packets fields for total, protocol, port, endpoint, and conversation metrics.

Rationale: in Telegraf NetFlow output these names map to flow-record byte and packet counters. The `in_` prefix is inherited from the NetFlow field naming, not a reliable instruction to render only ingress traffic.

Alternative considered: keep adding `netflow_out_bytes` when present. Rejected because missing `out_*` fields produce inconsistent totals and make v5/v9 behavior depend on exporter-specific templates.

### 3. Model interface direction through `in_snmp` and `out_snmp`

Interface views SHALL derive direction from interface index fields:

- Ingress interface metrics group `netflow_in_bytes` / `netflow_in_packets` by `in_snmp`.
- Egress interface metrics group the same bytes/packets by `out_snmp`.
- Each produced series SHALL tag a synthetic direction label (`in` or `out`) for display.

Rationale: a flow record can be attributed to both its input and output interface. Direction belongs to the grouping dimension, not to separate byte fields.

Alternative considered: keep `netflow_out_bytes` for egress interface charts. Rejected because it conflates interface direction with non-portable field availability.

### 4. Extend collector preprocessing, not every plugin query, for interface labels

Node management Telegraf base config SHALL convert `in_snmp` and `out_snmp` into tags alongside existing endpoint and protocol dimensions.

Rationale: this keeps the common NetFlow label contract close to the collector preprocessing layer and prevents every monitor query from depending on field-to-label behavior that may not exist.

### 5. Keep `netflow_version` as diagnostic metadata

The v5/v9 listeners SHALL continue tagging `netflow_version` as `v5` or `v9`. Monitor plugin queries SHALL NOT require this label for normal dashboards and policies, but it can be used for troubleshooting and future version-specific drill-down.

## Risks / Trade-offs

- [Metric value interpretation changes] → Update metric descriptions to describe "Flow bytes/packets" rather than "in + out bytes" where needed.
- [Historical dashboard comparison shifts] → Existing historical data with `out_*` fields may not line up exactly with the new common-field totals. This is acceptable because the new contract favors portable correctness.
- [Exporter omits `out_snmp`] → Egress interface charts may be sparse for devices that do not export output interface indexes. Ingress charts and non-interface dimensions continue to work.
- [Tag cardinality] → Promoting `in_snmp` and `out_snmp` adds bounded interface-index labels, comparable to existing endpoint and port labels. This is acceptable for Flow analysis.
- [Built-in collector definitions already persisted] → Operators must run `node_init` before `repair_node_config` so existing nodes receive the new converter tags.

## Migration Plan

1. Update node management Telegraf default collector config to tag `in_snmp` and `out_snmp`.
2. Update NetFlow plugin metrics under each supported network object type to remove `netflow_out_bytes` and `netflow_out_packets`.
3. Update metric descriptions where direction semantics change.
4. Add tests for collector converter tags and NetFlow metric query field usage.
5. Deploy code.
6. Run:

```bash
cd server
uv run python manage.py node_init
uv run python manage.py repair_node_config
```

Rollback: revert the code changes and rerun the same two commands so persisted collector defaults and node configs return to the previous state.

## Open Questions

- Should the UI expose `netflow_version` as an optional filter in future dashboards? This change keeps the tag available but does not add version filtering.
- Should IPFIX later join this same plugin once a stable common-field mapping is confirmed? This change intentionally leaves IPFIX out of scope.
