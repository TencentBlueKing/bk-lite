# Fix Collector Operation Architecture Filter

Status: done

## Migration Context

- Legacy source: `openspec/changes/fix-collector-operation-architecture-filter/`
- Legacy state: `active`
- 内容按原始 artifact 合并，未把 delta 自动写回长期 capability。

## Problem and Proposal

## Why

Node collector operations can query collectors with only `node_operating_system` and `tags`. In multi-architecture Linux deployments this can return same-name collectors for different CPU architectures, making actions such as restarting Telegraf ambiguous.

## What Changes

- Require node collector operation selection to use the selected nodes' structured `cpu_architecture` when loading collector options.
- Prevent collector operations from opening when the selected node architecture is unknown, instead of silently falling back to a broad collector query.
- Keep tag filtering only as an optional application-category filter; it MUST NOT be relied on to disambiguate CPU architecture.

## Capabilities

### New Capabilities
- `node-collector-operation-selection`: Collector operation option loading and validation for selected nodes.

### Modified Capabilities
- None.

## Impact

- Affected frontend: `web/src/app/node-manager/(pages)/cloudregion/node/page.tsx`
- Affected frontend: `web/src/app/node-manager/(pages)/cloudregion/node/collectorOperation/collectorModal.tsx`
- Verification: targeted frontend tests plus existing lint/type-check where feasible.

## Implementation Decisions

## Context

The collector API already supports `cpu_architecture` through `CollectorFilter`, and the collector operation modal already passes `cpu_architecture` when it receives a non-empty `selectedArchitecture`. The observed request omits that parameter:

```text
/node_mgmt/api/collector?node_operating_system=linux&tags=monitor
```

That omission allows same-name x86_64 and ARM64 collectors to appear together. The frontend also currently treats an empty selected node architecture as a valid value and simply omits `cpu_architecture` from the request.

## Goals / Non-Goals

**Goals:**
- Collector operation option queries include the selected nodes' normalized CPU architecture.
- Users cannot start collector operations for nodes whose CPU architecture is unknown.
- Tag filtering remains a category convenience only, not the source of architecture correctness.

**Non-Goals:**
- Do not change collector management page filtering.
- Do not change backend collector filtering semantics.
- Do not backfill historical node architectures in this change.

## Decisions

1. Validate selected node architecture before opening the collector operation modal.
   - Rationale: the parent page already knows the selected nodes and already requires one OS and one architecture. Blocking before the modal avoids a broad query and gives the user immediate feedback.
   - Alternative considered: let the modal open and show an empty collector list. This hides the real cause and still requires the modal to handle an invalid input state.

2. Keep passing `cpu_architecture` as a structured query parameter.
   - Rationale: `Collector.cpu_architecture` is a first-class model field and the backend filter already normalizes aliases.
   - Alternative considered: add architecture tags to `tags`. Tags are not reliable enough for correctness and can conflict with app-category filtering.

3. Keep `tags` as an app-category filter for the existing radio UI.
   - Rationale: removing it would broaden category results and change the modal's workflow more than needed for this bug.
   - Correctness comes from `node_operating_system + cpu_architecture`; `tags` only narrows visible categories.

## Risks / Trade-offs

- Nodes with empty `cpu_architecture` will be blocked from collector operations until their architecture is reported or backfilled. This is safer than offering ambiguous same-name collectors.
- If backend data contains collectors with missing `cpu_architecture`, x86_64 nodes will no longer see those legacy collector rows in the operation modal. Current collector definitions use explicit `x86_64`/`arm64`, so this is acceptable for operation selection.

## Legacy Metadata

```yaml
schema: spec-driven
created: 2026-06-11
```

## Capability Deltas

### node-collector-operation-selection

## ADDED Requirements

### Requirement: Collector operation queries are architecture-scoped
When loading collector options for selected nodes, the system SHALL include the selected nodes' CPU architecture as the structured `cpu_architecture` query parameter.

#### Scenario: Selected ARM64 Linux node opens restart collector modal
- **WHEN** a user selects an ARM64 Linux node and opens a collector operation modal
- **THEN** the collector list request includes `node_operating_system=linux` and `cpu_architecture=arm64`

#### Scenario: Collector category is selected
- **WHEN** a collector application category is selected in the modal
- **THEN** the category MAY be sent as `tags`, but architecture correctness MUST still come from `cpu_architecture`

### Requirement: Unknown node architecture blocks collector operations
The system SHALL NOT open collector operation selection when the selected nodes have no known CPU architecture.

#### Scenario: Selected node has unknown architecture
- **WHEN** a user selects a node whose `cpu_architecture` is empty and chooses a collector operation
- **THEN** the system shows an error and does not request the collector list

## Work Checklist

## 1. Tests

- [x] 1.1 Add a frontend regression test proving collector operation queries include `cpu_architecture`.
- [x] 1.2 Add a frontend regression test proving unknown architecture blocks collector operation modal opening.

## 2. Implementation

- [x] 2.1 Update the node page collector operation handler to validate selected node architecture before opening the modal.
- [x] 2.2 Ensure collector option loading continues to pass `cpu_architecture` and treats `tags` only as a category filter.

## 3. Verification

- [x] 3.1 Run the targeted frontend test.
- [x] 3.2 Run the relevant web lint/type-check command if dependency state allows it.
