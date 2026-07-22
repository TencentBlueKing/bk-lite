# Historical Superpowers change: 2026-06-27-system-manager-user-sync-card-redesign

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-27-system-manager-user-sync-card-redesign.md

> **For agentic workers:** REQUIRED EXECUTION STYLE: Use `superpowers:executing-plans` to implement this plan in a single mainline sequence. Follow the task order in this document, use lightweight validation between tasks, and perform full verification/review only after all planned tasks are complete. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current system manager user sync source cards with the approved richer card layout while preserving all existing page behaviors and using a system-manager-local list component instead of extending the shared `EntityList`.

**Architecture:** `user-sync/page.tsx` remains the page state and action owner, but it stops rendering the shared `EntityList` directly. A new local list component under `system-manager/components/user/user-sync/` owns the toolbar shell, responsive grid, loading/empty states, and the new card markup with metadata, metrics, footer status summary, and visible `同步策略` / `立即同步` actions.

**Tech Stack:** Next.js App Router, React 19, TypeScript, Ant Design, Tailwind utility classes, existing `useLocalizedTime` hook

## Execution Constraints

- The primary objective is to complete all task goals in this plan end-to-end.
- Perform the full verification and review after all planned tasks are completed; do not stop for a separate full review after each individual task.
- Prefer lightweight, directly relevant validation and review first; avoid spending disproportionate effort on heavyweight verification unless risk or uncertainty justifies it.
- Do not force through ambiguous issues. If design intent, card information hierarchy, action placement, or user sync data semantics become unclear, stop and align with the user before continuing.
- Follow existing repository code style and implementation patterns.
- Keep changes tightly scoped to this user sync card redesign; avoid unrelated refactors, opportunistic cleanup, or broad restructuring.
- Treat task completion as behaviorally meeting the planned end-state, not merely landing partial code or passing isolated interim tests.
- The approved design already fixes the key UI decisions: provider identity is icon-only, synced user count comes from the latest run, top status tags are removed, and `同步策略` is a visible footer action rather than a menu item.
- Prefer no compatibility branch inside the shared `web/src/components/entity-list`; this redesign is intentionally page-local.
- If time formatting, provider icon rendering, or empty-state semantics become unclear during implementation, stop and align with the user before continuing.
- Execute this plan in `executing-plans` style: follow the documented task order in a single mainline flow, avoid large parallel workstreams, and use only lightweight interim validation until final verification.
- Do not add `git commit` or `git add` steps in this plan; deliver the implementation and verification only.

**Delivery scope note:** This plan covers only the system manager user sync card list UI and its immediate page wiring. It does not include backend API changes, unrelated shared component refactors, or modal/records drawer redesign.

---

## File Structure

### Existing files to modify

- `web/src/app/system-manager/(pages)/user/user-sync/page.tsx`
  Replace direct usage of the shared `EntityList`, shape source data for the new card component, wire the new footer actions, and keep page-level state/API ownership unchanged.
- `web/src/app/system-manager/locales/zh.json`
  Add any new user sync card copy keys only if the new local component should avoid hard-coded Chinese strings.

### New files to create

- `web/src/app/system-manager/components/user/user-sync/UserSyncSourceList.tsx`
  System-manager-local list shell and card renderer for user sync sources.
- `web/src/app/system-manager/components/user/user-sync/UserSyncSourceList.module.scss`
  Scoped card layout styles if utility classes alone are insufficient for the denser card structure.

### Reference files to read during implementation

- `docs/superpowers/specs/2026-06-27-system-manager-user-sync-card-redesign-design.md`
- `web/src/components/entity-list/index.tsx`
- `web/src/app/system-manager/components/user/user-sync/UserSyncRecordsDrawer.tsx`
- `web/src/app/system-manager/utils/userSyncPageUtils.ts`
- `web/src/hooks/useLocalizedTime.ts`

---

### Task 1: Introduce a system-manager-local user sync source list component

**Files:**
- Create: `web/src/app/system-manager/components/user/user-sync/UserSyncSourceList.tsx`
- Create: `web/src/app/system-manager/components/user/user-sync/UserSyncSourceList.module.scss`
- Reference: `web/src/components/entity-list/index.tsx`
- Reference: `docs/superpowers/specs/2026-06-27-system-manager-user-sync-card-redesign-design.md`

**Interfaces:**
- Consumes:
  - `UserSyncSourceCardItem` view model from `user-sync/page.tsx`
  - toolbar props: `loading`, `searchTerm`-driven callback, `operateSection`
  - action callbacks: `onEdit`, `onConfig`, `onStrategy`, `onDelete`, `onSyncNow`
- Produces:
  - `UserSyncSourceList` React component with props:
    - `data: UserSyncSourceCardItem[]`
    - `loading: boolean`
    - `operateSection?: React.ReactNode`
    - `onSearch?: (value: string) => void`
    - `onEdit: (item: UserSyncSourceCardItem) => void`
    - `onConfig: (item: UserSyncSourceCardItem) => void`
    - `onStrategy: (item: UserSyncSourceCardItem) => void`
    - `onDelete: (item: UserSyncSourceCardItem) => void`
    - `onSyncNow: (item: UserSyncSourceCardItem) => void`

- [ ] **Step 1: Define the local list component prop contract around user-sync-specific card data**

Requirements:
- do not preserve full API compatibility with the shared `EntityList`
- keep only the features this page still needs: search box, external operate section, loading state, empty state, responsive grid, action menu, footer buttons
- define a card item type that already contains display-ready fields for:
  - `id`
  - `name`
  - `description`
  - `providerIcon`
  - `integrationSystemName`
  - `rootGroupName`
  - `syncedUsersText`
  - `syncCycleText`
  - `latestSyncTimeText`
  - `latestStatusText`
  - `latestStatusTone`
  - raw source reference for callbacks if still needed

- [ ] **Step 2: Implement the toolbar, loading state, empty state, and responsive grid shell**

Requirements:
- keep the search box on the top right using the same general interaction pattern as the current page
- render `operateSection` alongside the search box
- keep a spinner-centered loading state
- keep an empty state when filtered results are empty and there is no add-card mode
- preserve responsive card grid behavior suitable for desktop widths shown in the approved design

- [ ] **Step 3: Implement the new card header and description structure**

Requirements:
- provider identity is icon-only
- render source title prominently
- render metadata line under the title as:
  - integration system name
  - separator dot
  - `根组织：{rootGroupName}`
- keep the top-right three-dot menu
- show description with `--` fallback when empty

- [ ] **Step 4: Implement the metric blocks and footer action area**

Requirements:
- render two metric blocks labeled `同步用户` and `同步周期`
- metric values come from already-shaped string props and must support `--`
- remove the old top status tag row entirely
- footer left side renders `最近同步：{latestSyncTimeText} · {latestStatusText}`
- footer right side renders visible `同步策略` and `立即同步` buttons
- `立即同步` disabled state must remain controllable from the shaped card item or callback context if the source is disabled

- [ ] **Step 5: Add only scoped styles needed for the denser card layout**

Requirements:
- prefer existing utility classes first
- use module styles only for card-specific spacing, borders, line clamping, or metric block presentation that is awkward with utility classes alone
- do not restyle unrelated system-manager pages

- [ ] **Step 6: Run a focused lint sanity check on the new list component**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/components/user/user-sync/UserSyncSourceList.tsx
```

Expected:
- no new lint errors in the new local component file

### Task 2: Re-shape user sync page data and replace the shared list integration

**Files:**
- Modify: `web/src/app/system-manager/(pages)/user/user-sync/page.tsx`
- Reference: `web/src/app/system-manager/types/user-sync.ts`
- Reference: `web/src/app/system-manager/utils/userSyncPageUtils.ts`
- Reference: `web/src/hooks/useLocalizedTime.ts`

**Interfaces:**
- Consumes:
  - `UserSyncSourceList` from Task 1
  - current page handlers: `openBasic`, `openConfig`, `openStrategy`, `handleDelete`, `handleSyncNow`, `openRecords`, `openAdd`, `handleRefresh`
- Produces:
  - `UserSyncSourceCardItem[]` view models passed to `UserSyncSourceList`
  - page-level callbacks wired to the new visible footer actions and menu actions

- [ ] **Step 1: Replace the shared `EntityList` import and wire the page to the new local list component**

Requirements:
- remove direct dependency on `@/components/entity-list` from this page
- keep `PageLayout`, `TopSection`, page actions, and modal wiring unchanged where possible
- preserve the current page-level search/records/add/refresh affordances

- [ ] **Step 2: Introduce a page-local `UserSyncSourceCardItem` mapping that matches the new component contract**

Requirements:
- compute integration system display text from `integration_instance_name`
- compute root organization display text from `root_group_name`
- compute description fallback as `--`
- compute synced user count from `latest_run?.synced_user_count`, fallback `--`
- compute sync cycle text from `schedule_config`, fallback `手动同步`
- compute latest sync summary from `latest_run`
- compute provider icon identity from the current provider-key-based lookup path already used by the page

- [ ] **Step 3: Use the existing localized time hook for latest sync time formatting**

Requirements:
- prefer `useLocalizedTime` over introducing a page-local date formatter if it satisfies the target card layout
- if there is no latest run, latest time text must be `--`
- status text must remain mapped through existing user sync status locale keys

- [ ] **Step 4: Move `同步策略` out of the menu and into a visible footer button callback**

Requirements:
- footer button must call the existing `openStrategy` behavior
- three-dot menu must retain:
  - edit basic config
  - access config
  - delete
- do not leave a duplicate `同步策略` menu item behind

- [ ] **Step 5: Preserve `立即同步` behavior in the new footer button**

Requirements:
- button must call the existing sync-now flow
- disabled behavior should remain aligned with current source enabled state
- success/failure messaging remains owned by the existing page handler

- [ ] **Step 6: Run a targeted lint sanity check on the rewired page**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/\(pages\)/user/user-sync/page.tsx
```

Expected:
- no new lint errors in the rewired page file

### Task 3: Reconcile copy usage and final card semantics

**Files:**
- Modify: `web/src/app/system-manager/locales/zh.json`
- Modify if needed: `web/src/app/system-manager/components/user/user-sync/UserSyncSourceList.tsx`
- Reference: `docs/superpowers/specs/2026-06-27-system-manager-user-sync-card-redesign-design.md`

**Interfaces:**
- Consumes:
  - current `userSyncPage` locale namespace
  - new card copy needs surfaced during Tasks 1-2
- Produces:
  - final visible strings for card labels and fallbacks without hard-coded drift from the approved design

- [ ] **Step 1: Decide whether the new card labels can reuse existing locale keys or need new ones**

Requirements:
- prefer reusing existing `userSyncPage` keys such as `syncNow`, `syncStrategy`, `noRun`, and `runStatus.*`
- add new locale keys only for card-specific labels not already present, such as:
  - `根组织`
  - `同步用户`
  - `同步周期`
  - `最近同步`
- avoid broad locale cleanup outside this page

- [ ] **Step 2: Align empty-state and no-run text with the approved design semantics**

Requirements:
- latest sync summary with no run must read as `最近同步：-- · 暂无记录`
- synced user count with no run must show `--`
- description fallback remains `--`
- sync cycle fallback remains `手动同步`

- [ ] **Step 3: Run a targeted TypeScript sanity check for the touched page and local component**

Run:

```bash
cd web
pnpm type-check
```

Expected:
- type-check passes without introducing new errors from the user sync page or its new local component

### Task 4: Perform final verification against the approved design and current behavior

**Files:**
- Reference: `docs/superpowers/specs/2026-06-27-system-manager-user-sync-card-redesign-design.md`
- Reference: `web/src/app/system-manager/(pages)/user/user-sync/page.tsx`
- Reference: `web/src/app/system-manager/components/user/user-sync/UserSyncSourceList.tsx`

**Interfaces:**
- Consumes:
  - final user sync page implementation from Tasks 1-3
- Produces:
  - verified implementation that matches both design intent and current action behavior

- [ ] **Step 1: Run the required local web verification commands**

Run:

```bash
cd web
pnpm lint
pnpm type-check
```

Expected:
- lint passes
- type-check passes

- [ ] **Step 2: Manually verify the card structure against the approved target**

Check in the browser:
- each card shows provider icon, title, metadata line, description, two metric blocks, latest sync summary, and footer buttons
- top status tag is gone
- `同步策略` and `立即同步` are visible on the card footer
- the three-dot menu still exposes edit, access config, and delete

- [ ] **Step 3: Manually verify current page behaviors were preserved**

Check in the browser:
- search still filters the card list
- sync records button still opens records drawer
- add source button still opens creation flow
- refresh still reloads source data
- `同步策略` still opens the strategy modal
- `立即同步` still triggers sync and uses the existing page-level messaging flow

- [ ] **Step 4: Perform plan-vs-spec self-review before closing the work**

Checklist:
- confirm the plan delivered the system-manager-local list approach rather than shared `EntityList` branching
- confirm no backend API change was introduced
- confirm provider identity remains icon-only
- confirm synced user count uses latest-run semantics, not cumulative semantics
- confirm latest sync status appears only in the footer summary
- confirm no unrelated system-manager pages were modified

## specs: 2026-06-27-system-manager-user-sync-card-redesign-design.md

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
