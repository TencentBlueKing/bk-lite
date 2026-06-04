# Ops Analysis Event Table Widget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current log-specific message widget path with a generic expandable event table that reuses existing table configuration and handles plain-list and paginated responses.

**Architecture:** Keep the current `message` chart type entry point for now, but route it to a new generic event-table implementation. Reuse `tableConfig.columns`, `useTableConfig`, `TableSettingsSection`, and `CustomTable`, while extracting common table-like data parsing utilities so `comTable` and the new event widget share the same response-shape logic.

**Tech Stack:** Next.js 16, React 19, TypeScript, Ant Design, CustomTable

---

### Task 1: Extract shared table-like data utilities

**Files:**

- Create: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/shared/tableLikeData.ts`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/comTable.tsx`
- Test: `web/scripts/ops-analysis-event-table-validation.ts`

- [ ] Add a failing validation script that asserts plain-list and paginated data are parsed consistently.
- [ ] Run `pnpm exec tsx scripts/ops-analysis-event-table-validation.ts` and confirm it fails because the shared utility does not exist yet.
- [ ] Implement shared parsing helpers for records, pagination metadata, and fallback column config generation.
- [ ] Switch `comTable` to use the shared utility without behavior regression.
- [ ] Re-run `pnpm exec tsx scripts/ops-analysis-event-table-validation.ts` and confirm it passes.

### Task 2: Implement generic expandable event table widget

**Files:**

- Create: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/eventTable/eventTable.tsx`
- Create: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/eventTable/eventTableDetail.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/comMessage.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/widgetWrapper.tsx`

- [ ] Add a failing validation case for expandable event-table data handling to `scripts/ops-analysis-event-table-validation.ts`.
- [ ] Run the validation script and confirm the new case fails.
- [ ] Implement the generic event-table widget with `CustomTable`, single-row expand, full-record detail rendering, and interface-driven pagination.
- [ ] Replace log-specific normalization in `comMessage` with the new generic widget path.
- [ ] Relax widget data validation for `message` chart type to accept any list or `{ items }` paginated shape.
- [ ] Re-run `pnpm exec tsx scripts/ops-analysis-event-table-validation.ts` and confirm all cases pass.

### Task 3: Reuse table config UI for message/event widget

**Files:**

- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig.tsx`
- Modify: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig/hooks/useTableConfig.ts`
- Modify: `web/src/app/ops-analysis/constants/common.ts`
- Modify: `web/src/app/ops-analysis/locales/zh.json`
- Modify: `web/src/app/ops-analysis/locales/en.json`

- [ ] Extend table-like config handling so the current `message` chart type reuses `useTableConfig` probing and `TableSettingsSection`.
- [ ] Ensure initialization, re-probe, and save logic all treat `message` like `table` for `tableConfig.columns` and optional filter fields.
- [ ] Rename the chart type label from message-oriented wording to event-table wording in locales if needed.
- [ ] Run targeted ESLint on modified files and confirm no new errors.

### Task 4: Verify end-to-end behavior

**Files:**

- Test: `web/scripts/ops-analysis-event-table-validation.ts`
- Test: `web/src/app/ops-analysis/(pages)/view/dashBoard/widgets/comMessage.tsx`
- Test: `web/src/app/ops-analysis/(pages)/view/dashBoard/components/viewConfig.tsx`

- [ ] Run `pnpm exec tsx scripts/ops-analysis-event-table-validation.ts`.
- [ ] Run targeted ESLint for event-table and view-config files.
- [ ] Run `get_errors` on touched files to confirm no editor diagnostics remain.
- [ ] Manually verify the widget supports list data, paginated data, configured columns, and expanded full-record display.
