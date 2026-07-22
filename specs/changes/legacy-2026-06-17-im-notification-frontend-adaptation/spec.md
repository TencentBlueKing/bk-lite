# Historical Superpowers change: 2026-06-17-im-notification-frontend-adaptation

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-17-im-notification-frontend-adaptation.md

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

## specs: 2026-06-17-im-notification-frontend-adaptation-design.md

> 说明：本文档保留设计阶段的过程记录。当前仓库实现已经在此基础上继续演进，凡与现状不一致之处，以当前代码实现为准。

## 背景

IM 应用通知后端底座已经完成重构，前端当前页面仍基于旧语义实现，存在以下错位：

- 页面表单仍使用 `mapping_strategy`、`external_field`、`message_type`
- 列表和抽屉仍把“映射关系”和“同步诊断结果”混合展示
- `sync_mappings` 仍被前端当作同步立即完成动作处理
- 页面没有接入新的 run 状态、展示状态和 provider manifest 字段语义

本次设计仅覆盖前端适配，目标是在不改变当前 IM 应用通知页面整体布局的前提下，对齐新的后端接口和业务语义。

## 目标

- 保持当前 `/system-manager/channel/im-notification` 页面的整体布局与主交互结构
- 将页面字段、列表列和抽屉内容切换到新的后端模型语义
- 将“正式映射关系”和“同步运行记录”拆开展示
- 将“同步映射”改为异步任务启动语义
- 接入 provider manifest 的匹配字段、发送字段和默认值语义

## 非目标

- 不改为 `user_sync` 的卡片式页面
- 不新增独立路由或全局记录页
- 不引入自动轮询或复杂的运行态订阅
- 不扩展文本消息之外的消息类型
- 首版不强制实现同步记录 `payload` 详情展开

## 现状

当前前端入口集中在：

- `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`
- `web/src/app/system-manager/types/im-notification.ts`
- `web/src/app/system-manager/api/im-notification/index.ts`
- `web/src/app/system-manager/utils/imNotificationUtils.ts`

当前页面布局为：

- 顶部说明区
- 搜索与新增操作区
- 渠道列表表格
- 新增/编辑弹层
- 查看映射抽屉
- 测试发送弹层

本次适配保持这套布局不变，只调整语义与字段。

## 设计原则

### 1. 布局保持稳定，语义对齐后端

用户已有页面使用心智不变，不在本轮改变主布局、主路由、动作位置和弹层组织方式。

### 2. 映射关系与运行记录明确拆分

正式映射只展示可用关系；未匹配、冲突、失败等诊断信息只属于同步运行记录，不再混入“查看映射”。

### 3. 状态展示以后端聚合字段为准

前端不自行推导 channel 运行状态，只使用后端返回的：

- `display_status`
- `latest_sync_status`
- `latest_sync_started_at`
- `latest_sync_finished_at`
- `latest_sync_summary`

### 4. 保持现有字段映射视觉表达

编辑弹层中“平台字段 = 外部字段”的表达保留，用于表示匹配字段等价关系；发送字段作为独立配置单独展示。

## 页面信息架构

页面整体结构保持不变：

1. 顶部说明区
2. 搜索框与新增按钮
3. 渠道列表表格
4. 新增/编辑弹层
5. 正式映射抽屉
6. 同步记录抽屉
7. 测试发送弹层

不新增新的主区域，不拆分新页面。

## 列表设计

列表继续使用当前表格结构，但列语义调整如下：

- `名称`
- `集成实例`
- `匹配关系`
- `发送字段`
- `状态`
- `最近同步`
- `启用`
- `操作`

### 列字段说明

#### 匹配关系

由 `platform_match_field = external_match_field` 组成，用于直接表达同步映射时的字段等价关系。

示例：

- `用户名 = user_id`
- `邮箱 = email`
- `手机号 = mobile`

#### 发送字段

展示 `external_receive_field`，用于表达发送消息时使用哪个外部字段作为接收标识。

#### 状态

使用 `display_status` 做主状态展示，前端只负责文案和颜色映射，不负责业务推导。

建议文案：

- `pending_sync` -> `待同步`
- `syncing` -> `同步中`
- `ready` -> `可用`
- `needs_resync` -> `需重新同步`
- `disabled` -> `已停用`

#### 最近同步

优先展示 `latest_sync_status`，并辅以最近开始时间或摘要。

建议文案：

- `running` -> `运行中`
- `success` -> `成功`
- `partial` -> `部分成功`
- `failed` -> `失败`

若没有运行记录，则显示空态文案。

## 操作设计

列表操作区保留当前密度与顺序风格，调整为：

- `编辑`
- `同步映射`
- `查看映射`
- `查看记录`
- `测试发送`
- `删除`

### 同步映射

- 点击后调用 `POST sync_mappings`
- 前端将其视为“启动同步任务”，而不是“同步立即完成”
- 成功后提示“同步已启动”
- 如果返回 `run_id`，首版只做轻量刷新，不做自动轮询
- 如果后端返回“已有同步进行中”，前端直接展示后端错误提示

### 查看映射

- 调用 `GET mappings`
- 只展示正式映射关系
- 不再展示 `matched/unmatched/error`

### 查看记录

- 新增动作
- 调用 `GET records`
- 展示当前 channel 的同步运行记录

### 测试发送

- 继续保留当前弹层
- 输入的“接收人”语义明确为平台用户名列表
- 渠道未进入可发送状态时禁止发起

## 新增/编辑弹层设计

继续保留当前弹层的两段结构：

- 基础信息
- 字段映射

不引入步骤条，不拆成多个弹层。

### 基础信息区

保留字段：

- `name`
- `integration_instance`
- `description`

### 字段映射区

字段映射区保留现有“字段等价关系”表达：

- 左侧：`platform_match_field`
- 中间：`=`
- 右侧：`external_match_field`

在此基础上，新增独立的发送字段配置：

- `external_receive_field`

语义约束：

- `platform_match_field` 表示平台侧用于匹配的字段
- `external_match_field` 表示外部目录中参与匹配的字段
- `external_receive_field` 表示消息发送时使用的外部接收字段

### 字段来源

#### platform_match_field

前端使用固定平台字段集合：

- `username`
- `email`
- `phone`

#### external_match_field

来自 provider manifest 的：

- `matchable_fields`

#### external_receive_field

来自 provider manifest 的：

- `receivable_fields`

### 默认值行为

新建渠道时，若所选实例对应 manifest 提供默认值，则自动填充：

- `default_external_match_field`
- `default_external_receive_field`

当 `integration_instance` 切换时：

- 更新外部匹配字段选项
- 更新发送字段选项
- 必要时重新应用默认值

## 查看映射抽屉设计

“查看映射”抽屉继续保留，但内容改为正式映射表。

建议列：

- 平台用户名
- 外部显示名 `external_display_name`
- 外部身份 `external_identity_key / external_identity_value`
- 发送字段 `external_receive_key`
- 同步时间 `synced_at`

说明：

- 不再展示状态列
- 不再展示失败摘要
- 不再展示未匹配/冲突信息

空态文案建议为：

- `暂无正式映射`

## 查看记录抽屉设计

新增“查看记录”抽屉，展示同步运行记录。

建议列：

- 开始时间
- 结束时间
- 状态
- 外部用户总数
- 匹配数
- 未匹配数
- 冲突数
- 摘要

首版仅展示列表，不强制提供 `payload` 详情展开。

如后续需要补充，可在不改主布局的前提下加二级详情视图或记录详情弹层。

## 测试发送设计

继续保留当前测试发送弹层，字段保持：

- 标题
- 内容
- 接收人

但“接收人”字段提示语调整为平台用户名语义，例如：

- 输入平台用户名，使用逗号或换行分隔

原因：

- 后端会先解析平台用户，再查正式映射发送
- 前端不应再暗示这里输入外部 receive id

## 状态与禁用规则

### 同步映射

在以下情况下禁用：

- 当前 channel 最近一条 run 为 `running`

### 测试发送

在以下状态下禁用：

- `pending_sync`
- `syncing`
- `needs_resync`
- `disabled`

仅当渠道处于可发送态时允许执行。

### 查看映射

- 始终可点
- 无数据时展示空态

### 查看记录

- 始终可点
- 无记录时展示空态

## API 与类型调整

前端需要对齐新的接口返回结构和字段模型。

### 渠道模型

`IMNotificationChannel` 需要切换到以下核心字段：

- `status`
- `platform_match_field`
- `external_match_field`
- `external_receive_field`
- `display_status`
- `latest_sync_status`
- `latest_sync_started_at`
- `latest_sync_finished_at`
- `latest_sync_summary`

删除旧前端依赖：

- `mapping_strategy`
- `external_field`
- `message_type`

### 映射模型

`IMNotificationUserMapping` 需要切换到正式关系字段：

- `user`
- `username`
- `external_identity_key`
- `external_identity_value`
- `external_receive_key`
- `external_display_name`
- `match_context`
- `external_snapshot`
- `synced_at`

### 记录模型

新增 `IMNotificationSyncRun` 前端类型，至少包括：

- `id`
- `channel`
- `status`
- `summary`
- `total_external_user_count`
- `matched_count`
- `unmatched_count`
- `conflict_count`
- `payload`
- `started_at`
- `finished_at`

### 接口调整

- `sync_mappings`：返回 `run_id`
- `mappings`：只返回正式映射
- `records`：新增 per-channel 记录接口
- `test_send`：保留现有入口，调整前端文案和可用状态控制

## 首版范围边界

本轮前端适配严格限制在以下范围：

- 保持当前 IM 应用通知页面整体布局不变
- 只做后端新语义适配
- 只支持文本消息测试发送
- 不做自动轮询
- 不做记录详情展开的强制实现
- 不引入新的页面结构和路由

## 风险与注意事项

### 1. Manifest 语义缺失会直接影响表单联动

如果 provider 未返回 `matchable_fields`、`receivable_fields` 或默认字段，前端需要有空态/降级处理，避免直接渲染错误选项。

### 2. 状态文案必须统一走后端展示语义

若前端继续自行用 `status + latest_sync_status` 拼状态，容易再次偏离后端规则。

### 3. 映射与记录不能重新混用

“查看映射”必须保持正式关系视角；同步失败、未匹配、冲突等问题只能留在“查看记录”。

## 决策结论

本次前端适配采用以下结论：

- 保持当前 IM 应用通知页面布局不变
- 列表仍为表格，不切换到卡片式
- 编辑弹层继续使用“平台字段 = 外部字段”的映射表达
- 发送字段单独配置
- 正式映射与同步记录拆成两个独立入口
- 同步映射改为异步任务启动语义
- 前端状态展示以后端聚合字段为准
