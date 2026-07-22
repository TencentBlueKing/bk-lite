# Normalize Netflow Common Metrics

Status: done

## Migration Context

- Legacy source: `openspec/changes/normalize-netflow-common-metrics/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

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

## Implementation Decisions

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

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-06-22
```

## Capability Deltas

### netflow-common-metrics

## ADDED Requirements

### Requirement: NetFlow v5 and v9 share one monitor plugin
The system SHALL keep NetFlow v5 and NetFlow v9 as one user-facing NetFlow monitor plugin while collecting them through version-specific Telegraf listeners.

#### Scenario: NetFlow listeners are version-specific
- **WHEN** the built-in Telegraf collector definition is initialized
- **THEN** it contains one NetFlow v5 listener on UDP 2055 and one NetFlow v9 listener on UDP 2056
- **AND** both listeners tag records with `collect_type=netflow`
- **AND** each listener tags records with the corresponding `netflow_version`

#### Scenario: Monitor plugin remains protocol-level
- **WHEN** a user opens or configures a NetFlow Flow analysis plugin
- **THEN** the system presents one NetFlow plugin rather than separate v5 and v9 plugins
- **AND** the access guide explains which listener endpoint to use for each export version

### Requirement: Collector preprocessing exposes common NetFlow dimensions
The system SHALL convert common NetFlow flow-record dimensions into queryable tags before metrics are sent to storage.

#### Scenario: Endpoint and protocol dimensions are tags
- **WHEN** Telegraf processes a NetFlow record
- **THEN** `protocol`, `src`, `src_port`, `dst`, and `dst_port` are available as tags for grouping and filtering

#### Scenario: Interface dimensions are tags
- **WHEN** Telegraf processes a NetFlow record that contains interface index fields
- **THEN** `in_snmp` and `out_snmp` are available as tags for grouping and filtering

### Requirement: NetFlow metrics use portable bytes and packets fields
The system SHALL base NetFlow byte and packet metrics on fields that are portable across NetFlow v5 and v9.

#### Scenario: NetFlow plugin does not depend on out bytes fields
- **WHEN** built-in NetFlow monitor plugin metrics are imported or tested
- **THEN** NetFlow metric queries do not reference `netflow_out_bytes`
- **AND** NetFlow metric queries do not reference `netflow_out_packets`

#### Scenario: Overview metrics use flow record counters
- **WHEN** the system queries NetFlow overview traffic metrics
- **THEN** byte metrics aggregate `netflow_in_bytes`
- **AND** packet metrics aggregate `netflow_in_packets`
- **AND** the queries apply the asset's effective sampling rate

#### Scenario: Protocol, port, endpoint, and conversation metrics use common dimensions
- **WHEN** the system queries NetFlow protocol, port, endpoint, or conversation metrics
- **THEN** the queries aggregate `netflow_in_bytes` or `netflow_in_packets`
- **AND** the queries group only by common NetFlow dimensions such as `protocol`, `src`, `dst`, `src_port`, and `dst_port`

### Requirement: Interface direction is derived from interface dimensions
The system SHALL represent NetFlow interface direction by grouping the same flow-record bytes and packets by input and output interface labels.

#### Scenario: Ingress interface metrics use in_snmp
- **WHEN** the system queries ingress interface traffic for NetFlow
- **THEN** the query groups `netflow_in_bytes` or `netflow_in_packets` by `in_snmp`
- **AND** the resulting series identifies the direction as ingress

#### Scenario: Egress interface metrics use out_snmp
- **WHEN** the system queries egress interface traffic for NetFlow
- **THEN** the query groups `netflow_in_bytes` or `netflow_in_packets` by `out_snmp`
- **AND** the resulting series identifies the direction as egress

### Requirement: Existing Flow assets remain compatible
The system SHALL preserve existing Flow asset and monitor instance contracts while changing the NetFlow metric query contract.

#### Scenario: Existing NetFlow assets continue to match incoming records
- **WHEN** an existing Flow asset has `netflow` enabled
- **THEN** incoming NetFlow v5 and v9 records that match the asset source IP continue to receive `instance_id`, `instance_type`, `collect_type`, and `effective_sampling_rate`

#### Scenario: Operational refresh updates persisted collector configs
- **WHEN** the optimized collector definition is deployed to an environment with existing nodes
- **THEN** running `node_init` followed by `repair_node_config` updates persisted collector defaults and repairs existing node configurations

## Work Checklist

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
