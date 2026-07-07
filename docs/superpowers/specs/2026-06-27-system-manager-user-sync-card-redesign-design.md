# System Manager User Sync Card Redesign

## Summary

Refactor the system manager user sync source list from the current generic `EntityList` card layout to a user-sync-specific card layout that matches the new visual structure. The new layout must surface source context and sync summary data directly on the card without changing backend APIs.

## Goals

- Replace the current generic user sync cards with the new card information hierarchy shown in the approved target design.
- Keep the page-level search box, action buttons, loading state, empty state, and grid layout behavior.
- Keep all existing user sync actions functional: edit basic config, edit access config, edit sync strategy, delete, open sync records, refresh, and trigger sync now.
- Reuse a copy of the existing list component structure inside `system-manager` instead of expanding the shared `web/src/components/entity-list` API for this page-only layout.

## Non-Goals

- No backend API changes.
- No changes to other pages currently using the shared `EntityList`.
- No redesign of the user sync records drawer or modal workflows.
- No provider text badge or provider abbreviation fallback; provider identity is shown with icon only.

## Current State

The page at `web/src/app/system-manager/(pages)/user/user-sync/page.tsx` renders user sync sources through the shared `web/src/components/entity-list/index.tsx`. That shared component is optimized for a simple title, description, tag row, and optional bottom-right action slot. It does not provide clean structure for:

- a metadata line below the title,
- a two-column metric section,
- a bottom status summary row,
- two persistent action buttons inside the card footer.

Continuing to extend the shared component for this page would add page-specific branching to a component used by unrelated modules.

## Design Decision

Create a system-manager-local list component for user sync cards by copying the shared list container behavior that this page still needs:

- top toolbar with search and external action area,
- loading state,
- empty state,
- responsive grid layout.

The card body becomes a user-sync-specific implementation owned by `system-manager`.

## Card Layout

Each card must render the following sections in order.

### Header

- Provider icon on the left.
- Source name as the card title.
- Metadata line under the title in this exact order:
  - integration system name: `integration_instance_name`
  - separator dot
  - `根组织：{root_group_name}`
- Three-dot action menu on the top right.

### Description

- Show `description` using the existing description area behavior.
- If the description is empty, display `--`.

### Metrics

Render two compact metric blocks in one row:

- Block 1:
  - value: latest synced user count
  - label: `同步用户`
- Block 2:
  - value: sync cycle summary
  - label: `同步周期`

### Footer

- Left side status summary:
  - prefix text: `最近同步：`
  - latest sync time
  - separator dot
  - latest run status text
- Right side actions:
  - secondary button: `同步策略`
  - primary button: `立即同步`

## Data Mapping

All required data already exists in current frontend models.

### Provider icon

- Continue using the current provider-key-based icon rendering path already used by the page.

### Title and metadata

- Title: `source.name`
- Integration system name: `source.integration_instance_name`
- Root organization name: `source.root_group_name`

### Description

- Source: `source.description`
- Empty fallback: `--`

### Synced user count

- Source: `source.latest_run?.synced_user_count`
- If there is no latest run, render `--`

This count is defined as the latest run result, not a cumulative total.

### Sync cycle

- Source: `source.schedule_config`
- If `schedule_config?.enabled` is true and `schedule_config.sync_time` exists, show `sync_time`
- Otherwise show `手动同步`

### Latest sync summary

- Time source: `source.latest_run?.started_at`
- Status source: `source.latest_run?.status`
- If there is no latest run, show `最近同步：-- · 暂无记录`

The current top status tag row must be removed. Status is shown only in the footer summary.

## Interaction Design

### Search and page actions

Keep current page-level behavior:

- search box,
- sync records button,
- add source button,
- refresh button.

### Card actions

Keep existing behavior and handlers:

- `同步策略` opens the strategy modal.
- `立即同步` triggers sync now.
- three-dot menu contains:
  - edit basic config,
  - access config,
  - delete.

`同步策略` must move out of the menu into the visible footer button area.

## Component Boundaries

### New system-manager-local list component

Create a local component under `web/src/app/system-manager/components/user/user-sync/` that owns:

- toolbar layout,
- grid layout,
- loading and empty states,
- user-sync card markup.

It may keep a similar top-level prop shape to the shared list component where useful, but it does not need to stay API-compatible with the shared `EntityList`.

### User sync page responsibilities

`page.tsx` continues to own:

- API calls,
- page state,
- modal state,
- action handlers,
- source-to-view-model mapping.

The page should pass already-shaped card data and action callbacks into the new local component.

## Styling Constraints

- Follow existing `system-manager` and repository styling patterns.
- Keep the responsive card grid behavior currently used by the page.
- Do not globally restyle the shared list component.
- Only touch styles required for the new card layout.

## Testing

Minimum verification for this change:

- `web/src/app/system-manager/(pages)/user/user-sync/page.tsx` builds and type-checks.
- The new local component renders:
  - metadata line under the title,
  - two metric blocks,
  - footer latest sync summary,
  - footer `同步策略` and `立即同步` buttons.
- Existing page actions still invoke their current handlers.
- Empty and loading states still render correctly.

## Risks

- Provider icons may need layout adjustments because the new header is denser than the old card.
- Raw time formatting from `started_at` may not visually match the target mockup. If current page utilities do not provide a suitable formatter, add a local formatter scoped to this page change.
- Copying too much of the shared `EntityList` would duplicate unused features such as filter support and add-card mode. The local component should copy only the structure this page still needs.
