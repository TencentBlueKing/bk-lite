# IM Notification Frontend Adaptation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adapt the existing IM notification frontend page to the redesigned backend contract while preserving the current page layout and interaction structure.

**Architecture:** The implementation keeps the current `im-notification` page shell, modals, and drawers, and only rewires data contracts, status presentation, and action semantics to the new backend model. The frontend continues to use the current page entry, but splits formal mappings from sync run records, consumes provider manifest field semantics, and treats sync as an async run-start action rather than an inline completion flow.

> **Status:** Implemented in the current code state.
>
> **Implementation notes:**
> - The page keeps the existing route entry and shell structure.
> - Formal mappings and sync records are split into separate drawers.
> - Sync is handled as an async run-start action.
> - Provider manifest field semantics are used for external match and receive field selection.

**Tech Stack:** Next.js App Router, React 19, TypeScript, Ant Design

## Execution Constraints

- The primary objective is to complete all task goals in this plan end-to-end.
- Perform the full verification and review after all planned tasks are completed; do not stop for a separate full review after each individual task.
- Prefer lightweight, directly relevant validation and review first; avoid spending disproportionate effort on heavyweight verification unless risk or uncertainty justifies it.
- Do not force through ambiguous issues. If design intent, migration behavior, compatibility scope, or implementation direction becomes unclear, stop and align with the user before continuing.
- Follow existing repository code style and implementation patterns.
- Keep changes tightly scoped to this frontend adaptation; avoid unrelated refactors, opportunistic cleanup, or broad restructuring.
- Treat task completion as behaviorally meeting the planned end-state, not merely landing partial code or passing isolated interim tests.
- This phase focuses on frontend adaptation for the existing IM notification page and does not include backend semantic changes.
- Prefer no temporary compatibility layer unless explicitly required.
- If API contract, field semantics, or rollout behavior become unclear, stop and align with the user before continuing.
- Execute this plan in `executing-plans` style: follow the documented task order in a single mainline flow, avoid large parallel workstreams, and use only lightweight interim validation until final verification.

---

## File Structure

### Existing files to modify

- `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`
  The current page entry. Update table columns, action semantics, modal fields, records drawer, disabled rules, and state handling while preserving the current layout.
- `web/src/app/system-manager/types/im-notification.ts`
  Replace old IM notification channel/mapping types with the redesigned channel, formal mapping, and sync run frontend models.
- `web/src/app/system-manager/api/im-notification/index.ts`
  Update request/response typings and add the per-channel records API.
- `web/src/app/system-manager/utils/imNotificationUtils.ts`
  Replace old mapping-status helpers with display-status, run-status, and receiver-input helpers aligned to the new frontend semantics.
- `web/src/app/system-manager/types/integration-center.ts`
  Extend IM business template typing so the page can consume `matchable_fields`, `receivable_fields`, and default external field semantics.
- `web/src/app/system-manager/locales/zh.json`
  Update IM notification copy for the new table columns, records drawer, state labels, and receiver semantics.
- `web/src/app/system-manager/locales/en.json`
  Keep English locale in sync with the new IM notification frontend contract.

### Potential new files

- None required if the current page continues to own its modals and drawers inline.

### Reference files to read during implementation

- `docs/superpowers/specs/2026-06-17-im-notification-frontend-adaptation-design.md`
- `docs/superpowers/specs/2026-06-16-im-notification-foundation-redesign-design.md`
- `docs/superpowers/plans/2026-06-16-im-notification-foundation-redesign.md`
- `web/src/app/system-manager/(pages)/user/user-sync/page.tsx`
- `web/src/app/system-manager/components/user/user-sync/UserSyncRecordsDrawer.tsx`
- `server/apps/system_mgmt/serializers/im_notification_channel_serializer.py`
- `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`

---

### Task 1: Redesign Frontend Types and API Contract

**Files:**
- Modify: `web/src/app/system-manager/types/im-notification.ts`
- Modify: `web/src/app/system-manager/api/im-notification/index.ts`
- Modify: `web/src/app/system-manager/types/integration-center.ts`
- Test: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`

- [ ] **Step 1: Write the failing type usage in the page**

Update the page to reference the new fields before changing the types:

```ts
channel.platform_match_field
channel.external_match_field
channel.external_receive_field
channel.display_status
channel.latest_sync_status
```

Expected immediate failure: TypeScript reports that these fields do not exist on `IMNotificationChannel`.

- [ ] **Step 2: Run a lightweight old-contract scan**

Run: `cd web && rg -n "mapping_strategy|external_field|message_type|platform_identifier|external_user_id|external_open_id" src/app/system-manager`
Expected: IM notification page/types/API still show old frontend contract references that must be removed in the following steps.

- [x] **Step 3: Replace the frontend IM types with the redesigned contract**

Update `types/im-notification.ts` to model:

```ts
export type PlatformMatchField = 'username' | 'email' | 'phone';
export type ChannelStatus = 'pending_sync' | 'ready' | 'needs_resync' | 'disabled';
export type DisplayStatus = ChannelStatus | 'syncing';
export type SyncRunStatus = 'running' | 'success' | 'failed' | 'partial';

export interface IMNotificationChannel {
  id: number;
  name: string;
  integration_instance: number;
  integration_instance_name: string;
  enabled: boolean;
  description: string;
  status: ChannelStatus;
  platform_match_field: PlatformMatchField;
  external_match_field: string;
  external_receive_field: string;
  display_status: DisplayStatus;
  latest_sync_status: SyncRunStatus | '';
  latest_sync_started_at: string | null;
  latest_sync_finished_at: string | null;
  latest_sync_summary: string;
}

export interface IMNotificationUserMapping {
  id: number;
  channel: number;
  user: number;
  username: string;
  external_identity_key: string;
  external_identity_value: string;
  external_receive_key: string;
  external_display_name: string;
  match_context: Record<string, unknown>;
  external_snapshot: Record<string, unknown>;
  synced_at: string | null;
}

export interface IMNotificationSyncRun {
  id: number;
  channel: number;
  status: SyncRunStatus;
  summary: string;
  total_external_user_count: number;
  matched_count: number;
  unmatched_count: number;
  conflict_count: number;
  payload: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
}
```

Also extend the integration-center business template type to include:

```ts
matchable_fields: string[];
receivable_fields: string[];
default_external_match_field: string;
default_external_receive_field: string;
```

- [x] **Step 4: Update the IM API wrapper to the new endpoints and typed responses**

Add or adjust:

```ts
async function syncMappings(id: number): Promise<ActionResult & { data?: { run_id?: number } }>
async function getRecords(id: number, params: any)
```

Keep `mappings` typed as formal mappings only.

- [ ] **Step 5: Run a lightweight contract scan**

Run: `cd web && rg -n "mapping_strategy|external_field|message_type|platform_identifier|external_user_id|external_open_id" src/app/system-manager/types/im-notification.ts src/app/system-manager/api/im-notification/index.ts`
Expected: no remaining old IM type/API contract references in the touched files.

### Task 2: Replace Old IM Utility Semantics

**Files:**
- Modify: `web/src/app/system-manager/utils/imNotificationUtils.ts`
- Modify: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`
- Test: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`

- [ ] **Step 1: Remove one old mapping-status dependency from the page**

Replace a current usage such as:

```ts
getMappingStatusColor(status)
```

with a new helper call placeholder for display status or run status:

```ts
getDisplayStatusColor(record.display_status)
```

Expected immediate failure: helper does not exist yet.

- [ ] **Step 2: Run a lightweight helper-surface check**

Run: `cd web && rg -n "getMappingStatusColor|MappingStatus" src/app/system-manager/utils/imNotificationUtils.ts src/app/system-manager/(pages)/channel/im-notification/page.tsx`
Expected: old mapping-status helper usage is still present before the utility rewrite.

- [x] **Step 3: Rewrite the IM notification utility helpers**

Keep `parseReceiversInput`, then replace the old status helper set with:

```ts
export function getDisplayStatusColor(status: string): string {
  const map: Record<string, string> = {
    pending_sync: 'default',
    syncing: 'processing',
    ready: 'success',
    needs_resync: 'warning',
    disabled: 'default',
  };
  return map[status] ?? 'default';
}

export function getSyncRunStatusColor(status: string): string {
  const map: Record<string, string> = {
    running: 'processing',
    success: 'success',
    partial: 'warning',
    failed: 'error',
  };
  return map[status] ?? 'default';
}

export function isChannelSendReady(displayStatus: string): boolean {
  return displayStatus === 'ready';
}

export function isChannelSyncRunning(latestSyncStatus: string): boolean {
  return latestSyncStatus === 'running';
}

export function getDisplayStatusText(
  status: string,
  t: (key: string, fallback?: string) => string,
): string {
  return t(`system.channel.imNotificationPage.displayStatus.${status}`, status);
}

export function getSyncRunStatusText(
  status: string,
  t: (key: string, fallback?: string) => string,
): string {
  return t(`system.channel.imNotificationPage.syncRunStatus.${status}`, status);
}
```

- [x] **Step 4: Wire the new helpers into the page**

Replace old mapping-status rendering and local inline checks with the new helpers so the page reads state semantics from the redesigned contract, including both:

- display-status text rendering from `display_status`
- latest-run status text rendering from `latest_sync_status`

- [ ] **Step 5: Run a lightweight helper scan**

Run: `cd web && rg -n "getMappingStatusColor|MappingStatus" src/app/system-manager/utils/imNotificationUtils.ts src/app/system-manager/(pages)/channel/im-notification/page.tsx`
Expected: no remaining old mapping-status helper usage in the touched files.

### Task 3: Rebuild the Table and Action Semantics in the Existing Layout

**Files:**
- Modify: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`
- Modify: `web/src/app/system-manager/locales/zh.json`
- Modify: `web/src/app/system-manager/locales/en.json`
- Test: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`

- [ ] **Step 1: Change the table columns to the new field names before implementing all renderers**

Add placeholder column references:

```ts
dataIndex: 'display_status'
dataIndex: 'external_receive_field'
render: (_, record) => `${record.platform_match_field} = ${record.external_match_field}`
```

Expected immediate failure: page still depends on removed fields such as `mapping_strategy` and old copy keys.

- [ ] **Step 2: Run a lightweight table-contract scan**

Run: `cd web && rg -n "mapping_strategy|external_field|message_type|syncMappingsSuccess" src/app/system-manager/(pages)/channel/im-notification/page.tsx src/app/system-manager/locales/zh.json src/app/system-manager/locales/en.json`
Expected: old table/action contract references are still present before the table rewrite.

- [x] **Step 3: Implement the redesigned table columns and action semantics**

Update the page so the table shows:

- `name`
- `integration_instance_name`
- `platform_match_field = external_match_field`
- `external_receive_field`
- `display_status`
- latest sync information from `latest_sync_status`, `latest_sync_started_at`, `latest_sync_summary`
- `enabled`

Update actions:

- `sync_mappings` shows “sync started” semantics and accepts `run_id`
- `view_mappings` remains formal-mapping only
- add `view_records`
- `test_send` follows send-ready gating

Also update `handleSyncMappings`:

```ts
const result = await syncMappings(record.id);
if (result.result) {
  message.success(t('system.channel.imNotificationPage.syncMappingsStarted'));
  await fetchChannels();
}
```

Keep `查看映射` and `查看记录` always clickable in the action area. Empty data must be handled inside the opened drawer rather than by disabling the entry action.

- [x] **Step 4: Add locale keys for the new table and action labels**

Add or update copy such as:

- `matchRelation`
- `receiveField`
- `displayStatus`
- `latestSync`
- `latestSyncEmpty`
- `viewRecords`
- `syncMappingsStarted`
- `noFormalMappings`
- `noSyncRecords`

- [ ] **Step 5: Run a lightweight table/action scan**

Run: `cd web && rg -n "mapping_strategy|external_field|message_type|syncMappingsSuccess" src/app/system-manager/(pages)/channel/im-notification/page.tsx`
Expected: no remaining old list/action field references in the touched page sections.

### Task 4: Adapt the Edit Modal to New Match and Receive Field Semantics

**Files:**
- Modify: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`
- Modify: `web/src/app/system-manager/locales/zh.json`
- Modify: `web/src/app/system-manager/locales/en.json`
- Test: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`

- [ ] **Step 1: Replace old form field names in the modal**

Change modal bindings from:

```ts
name="mapping_strategy"
name="external_field"
```

to:

```ts
name="platform_match_field"
name="external_match_field"
name="external_receive_field"
```

Also remove the obsolete `message_type` flow from the modal state, form bindings, submitted payload construction, and any create/edit defaults.

Expected immediate gap: the form still hardcodes old option lists and has no manifest-driven source for the new external fields.

- [ ] **Step 2: Run a lightweight modal-contract scan**

Run: `cd web && rg -n "mapping_strategy|external_field|message_type" src/app/system-manager/(pages)/channel/im-notification/page.tsx`
Expected: old modal field references are still present before the modal rewrite completes.

- [x] **Step 3: Implement manifest-driven external field options while preserving the current layout**

Inside the existing modal:

- keep the match row rendered as `platform_match_field = external_match_field`
- add a separate `external_receive_field` form item below the existing mapping row
- derive external field options from the selected instance’s provider manifest
- use manifest defaults on create:

```ts
default_external_match_field
default_external_receive_field
```

- keep platform field options as a fixed small set:

```ts
[
  { value: 'username', label: ... },
  { value: 'email', label: ... },
  { value: 'phone', label: ... },
]
```

- [x] **Step 4: Apply instance-change behavior and editing defaults**

When `integration_instance` changes:

- refresh the resolved manifest template
- refresh `external_match_field` options
- refresh `external_receive_field` options
- fill defaults on add mode
- preserve current values on edit mode unless they become invalid

Also add degraded handling for missing or incomplete manifest semantics:

- if `matchable_fields` is empty, render an empty option set and keep the match field selector visibly unavailable
- if `receivable_fields` is empty, render an empty option set and keep the receive field selector visibly unavailable
- if manifest defaults are absent, do not synthesize frontend defaults
- surface a lightweight inline hint rather than inventing fallback field semantics in the page

- [ ] **Step 5: Run type-check to verify the modal is aligned**
- [ ] **Step 5: Run a lightweight modal scan**

Run: `cd web && rg -n "mapping_strategy|external_field|message_type" src/app/system-manager/(pages)/channel/im-notification/page.tsx`
Expected: no remaining old modal field references in the page.

### Task 5: Split Formal Mappings and Sync Records into Separate Drawers

**Files:**
- Modify: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`
- Modify: `web/src/app/system-manager/locales/zh.json`
- Modify: `web/src/app/system-manager/locales/en.json`
- Test: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`

- [ ] **Step 1: Add the new records state usage before implementing the drawer**

Introduce placeholder state and API usage:

```ts
const [recordsOpen, setRecordsOpen] = useState(false);
const [records, setRecords] = useState<IMNotificationSyncRun[]>([]);
const { getRecords } = useImNotificationApi();
```

Expected immediate failure: records types, handlers, and drawer rendering are incomplete.

- [ ] **Step 2: Run type-check to verify it fails**
- [ ] **Step 2: Run a lightweight drawer wiring check**

Run: `cd web && rg -n "viewMappings|viewRecords|recordsOpen|noFormalMappings|noSyncRecords" src/app/system-manager/(pages)/channel/im-notification/page.tsx src/app/system-manager/locales/zh.json src/app/system-manager/locales/en.json`
Expected: records drawer wiring and empty-state copy are only partially present before drawer implementation completes.

- [x] **Step 3: Rewrite the mappings drawer to formal mappings only**

Replace old mapping columns such as `status`, `summary`, `external_name` with:

- `username`
- `external_display_name`
- identity pair
- `external_receive_key`
- `synced_at`

Do not display unmatched or error rows.

- [x] **Step 4: Add the per-channel records drawer**

Add:

- `handleViewRecords`
- records pagination state
- records columns for:
  - `started_at`
  - `finished_at`
  - `status`
  - `total_external_user_count`
  - `matched_count`
  - `unmatched_count`
  - `conflict_count`
  - `summary`

Do not add payload detail expansion in this first pass.

Make both entry actions explicit:

- `查看映射` is always enabled and opens even when there are zero mappings
- `查看记录` is always enabled and opens even when there are zero records

Render empty states inside the drawers using dedicated copy rather than disabling the actions.

- [ ] **Step 5: Run a lightweight drawer scan**

Run: `cd web && rg -n "noFormalMappings|noSyncRecords|recordsOpen|mappingsOpen" src/app/system-manager/(pages)/channel/im-notification/page.tsx`
Expected: drawer empty states and entry-action wiring are explicitly present in the page.

### Task 6: Finalize Test Send Semantics and Disabled Rules

**Files:**
- Modify: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`
- Modify: `web/src/app/system-manager/locales/zh.json`
- Modify: `web/src/app/system-manager/locales/en.json`
- Test: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`

- [ ] **Step 1: Add one strict disabled check before updating copy**

For example, gate the action button with:

```ts
disabled={!isChannelSendReady(record.display_status)}
```

Expected immediate failure or incomplete UX: related message keys and placeholders still describe old receiver semantics.

- [ ] **Step 2: Run a lightweight action-state scan**

Run: `cd web && rg -n "display_status|latest_sync_status|testSendReceiversPlaceholder|testSend" src/app/system-manager/(pages)/channel/im-notification/page.tsx src/app/system-manager/locales/zh.json src/app/system-manager/locales/en.json`
Expected: send gating and receiver copy still need final alignment before the last page pass.

- [x] **Step 3: Finalize the send modal and action disabled rules**

Implement:

- `test_send` disabled unless the channel is send-ready
- `sync_mappings` disabled when `latest_sync_status === 'running'`
- receiver placeholder explicitly describes platform usernames
- success/failure copy remains aligned to the new backend semantics

Use helpers rather than ad hoc inline condition chains.

- [x] **Step 4: Refresh the page flow after async actions**

After:

- create
- update
- sync start
- test send success

ensure the page state is minimally refreshed or closed consistently without adding polling or extra background logic.

- [ ] **Step 5: Run type-check to verify the IM page is fully aligned**

Run: `cd web && pnpm type-check`
Expected: PASS

### Task 7: Final Verification and Review

**Files:**
- Test: `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`
- Test: `web/src/app/system-manager/types/im-notification.ts`
- Test: `web/src/app/system-manager/api/im-notification/index.ts`

- [ ] **Step 1: Run focused frontend type validation**

Run:

```bash
cd web
pnpm type-check
```

Expected: PASS

- [ ] **Step 2: Run lightweight frontend lint validation**

Run:

```bash
cd web
pnpm lint
```

Expected: PASS or only unrelated pre-existing issues outside the touched IM notification scope.

- [x] **Step 3: Review the implementation against the frontend spec**

Checklist:

- current IM page layout is preserved
- list uses `platform_match_field = external_match_field`
- send field is displayed separately
- status display reads `display_status`
- sync action is treated as async start, not inline completion
- mappings drawer shows formal mappings only
- records drawer shows per-channel sync runs
- test-send receiver semantics are platform usernames
- no auto-polling or extra route was introduced

- [ ] **Step 4: Commit any final doc or copy adjustments**

```bash
git add web/src/app/system-manager
git commit -m "feat: adapt im notification frontend to redesigned backend"
```
