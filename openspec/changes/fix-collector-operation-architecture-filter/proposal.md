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
