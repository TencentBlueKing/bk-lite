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
