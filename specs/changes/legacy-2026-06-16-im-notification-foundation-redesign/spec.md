# Historical Superpowers change: 2026-06-16-im-notification-foundation-redesign

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-16-im-notification-foundation-redesign.md

> **For agentic workers:** REQUIRED EXECUTION STYLE: Use `superpowers:executing-plans` to implement this plan in a single mainline sequence. Follow the task order in this document, use lightweight validation between tasks, and perform full verification/review only after all planned tasks are complete. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the IM notification foundation so sync is external-user-driven, mappings only store formal matched relations, sync runs execute asynchronously, and provider manifest metadata can support future IM providers.

**Architecture:** The implementation keeps channel strategy, formal mapping relations, and sync execution records as separate concerns. Backend changes stay inside `server/apps/system_mgmt`, with provider manifest/schema updates defining capability semantics, Celery tasks executing sync runs, and serializers/viewsets exposing both formal state and computed display state.

**Tech Stack:** Django 4.2, Celery, DRF, Pydantic provider manifests, pytest

## Execution Constraints

- The primary objective is to complete all task goals in this plan end-to-end.
- Perform the full verification and review after all planned tasks are completed; do not stop for a separate full review after each individual task.
- Prefer lightweight, directly relevant validation and review first; avoid spending disproportionate effort on heavyweight verification unless risk or uncertainty justifies it.
- Do not force through ambiguous issues. If design intent, migration behavior, compatibility scope, or implementation direction becomes unclear, stop and align with the user before continuing.
- Follow existing repository code style and implementation patterns.
- Keep changes tightly scoped to this redesign; avoid unrelated refactors, opportunistic cleanup, or broad restructuring.
- Treat task completion as behaviorally meeting the planned end-state, not merely landing partial code or passing isolated interim tests.
- This plan focuses on the backend foundation first, but the current implementation already includes the aligned frontend page adaptation.
- Prefer no temporary compatibility layer unless explicitly required.
- If migration strategy, destructive change scope, or data handling expectations become unclear, stop and align with the user before continuing.
- Execute this plan in `executing-plans` style: follow the documented task order in a single mainline flow, avoid large parallel workstreams, and use only lightweight interim validation until final verification.

**Delivery scope note:** This plan focuses on backend foundation changes first. In the current code state, the IM notification page has already been adapted to the redesigned backend contract, including formal mappings, per-channel sync records, display status presentation, and test-send flow.

---

## File Structure

### Existing files to modify

- `server/apps/system_mgmt/models/im_notification_channel.py`
  Redefine `IMNotificationChannel`, redesign `IMNotificationUserMapping`, add `IMNotificationSyncRun`.
- `server/apps/system_mgmt/models/__init__.py`
  Export updated IM notification models.
- `server/apps/system_mgmt/migrations/`
  Add migration(s) for the model redesign.
- `server/apps/system_mgmt/providers/schemas.py`
  Extend provider business template metadata for IM notification field semantics.
- `server/apps/system_mgmt/providers/manifests/feishu.py`
  Populate IM notification field semantics and defaults for Feishu.
- `server/apps/system_mgmt/providers/adapters/base.py`
  Clarify IM adapter contract for sync and send operations if needed.
- `server/apps/system_mgmt/providers/adapters/feishu.py`
  Normalize IM user payload shape and adapt send path to `external_receive_key + external_snapshot`.
- `server/apps/system_mgmt/services/im_notification_service.py`
  Replace synchronous platform-user-driven sync logic with external-user-driven run execution logic.
- `server/apps/system_mgmt/tasks.py`
  Add Celery task entrypoint for IM notification sync runs.
- `server/apps/system_mgmt/serializers/im_notification_channel_serializer.py`
  Update serializers for new channel/mapping/run fields and computed display state.
- `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`
  Change sync endpoint to enqueue Celery runs, expose per-channel run records, and keep mappings formal-only.
- `server/apps/system_mgmt/tests/test_im_notification_service.py`
  Replace old sync assumptions with new mapping/run/task behavior tests.
- `server/apps/system_mgmt/tests/`
  Add focused tests for serializer/viewset/task behavior where needed.
- `web/src/app/system-manager/(pages)/channel/im-notification/page.tsx`
  Current code state already includes the aligned frontend page adaptation for formal mappings, records, display state, and test-send flow.

### Potential new files

- `server/apps/system_mgmt/tests/test_im_notification_viewset.py`
  Endpoint behavior tests for async sync, per-channel records, and display fields.
- `server/apps/system_mgmt/tests/test_im_notification_manifest.py`
  Manifest/schema tests for IM notification capability metadata.

### Reference files to read during implementation

- `docs/superpowers/specs/2026-06-16-im-notification-foundation-redesign-design.md`
- `server/apps/system_mgmt/models/user_sync_source.py`
- `server/apps/system_mgmt/services/user_sync_service.py`
- `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`

---

### Task 1: Redesign Provider Manifest Contract

**Files:**
- Modify: `server/apps/system_mgmt/providers/schemas.py`
- Modify: `server/apps/system_mgmt/providers/manifests/feishu.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_manifest.py`

- [ ] **Step 1: Write the failing manifest test**

```python
def test_feishu_im_notification_manifest_declares_field_semantics():
    manifest = PROVIDER_MANIFEST
    template = manifest.business_templates["im_notification_form"]

    assert template.available_external_fields == ["user_id", "open_id", "name", "email", "mobile"]
    assert template.matchable_fields == ["email", "mobile", "user_id", "open_id"]
    assert template.receivable_fields == ["user_id", "open_id"]
    assert template.identity_fields == ["user_id", "open_id"]
    assert template.default_external_match_field == "email"
    assert template.default_external_receive_field == "user_id"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest apps/system_mgmt/tests/test_im_notification_manifest.py -v`
Expected: FAIL because IM notification manifest metadata is missing.

- [ ] **Step 3: Add minimal schema support and Feishu manifest data**

```python
class BusinessTemplateManifest(BaseModel):
    ...
    matchable_fields: list[str] = Field(default_factory=list)
    receivable_fields: list[str] = Field(default_factory=list)
    identity_fields: list[str] = Field(default_factory=list)
    default_external_match_field: str = Field(default="")
    default_external_receive_field: str = Field(default="")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && pytest apps/system_mgmt/tests/test_im_notification_manifest.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/apps/system_mgmt/providers/schemas.py server/apps/system_mgmt/providers/manifests/feishu.py server/apps/system_mgmt/tests/test_im_notification_manifest.py
git commit -m "feat: add im notification manifest semantics"
```

### Task 2: Redesign IM Notification Models

**Files:**
- Modify: `server/apps/system_mgmt/models/im_notification_channel.py`
- Modify: `server/apps/system_mgmt/models/__init__.py`
- Create: `server/apps/system_mgmt/migrations/<new_migration>.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_service.py`

- [ ] **Step 1: Write the failing model test**

```python
def test_im_notification_mapping_stores_identity_and_snapshot_only(db):
    mapping = IMNotificationUserMapping.objects.create(
        channel=channel,
        user=user,
        external_identity_key="user_id",
        external_identity_value="ou_123",
        external_receive_key="user_id",
        external_display_name="Tester",
        match_context={"platform_field": "email", "external_field": "email"},
        external_snapshot={"user_id": "ou_123", "email": "tester@example.com"},
    )

    assert mapping.external_identity_value == "ou_123"
    assert mapping.external_receive_key == "user_id"
    assert "user_id" in mapping.external_snapshot
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest apps/system_mgmt/tests/test_im_notification_service.py -k mapping_stores_identity -v`
Expected: FAIL because the current model shape does not match the redesigned fields.

- [ ] **Step 3: Implement the model redesign**

```python
class IMNotificationChannel(...):
    status = models.CharField(max_length=32, default="pending_sync")
    platform_match_field = models.CharField(max_length=32)
    external_match_field = models.CharField(max_length=64)
    external_receive_field = models.CharField(max_length=64)

class IMNotificationUserMapping(...):
    user = models.ForeignKey(...)
    external_identity_key = models.CharField(max_length=64)
    external_identity_value = models.CharField(max_length=255)
    external_receive_key = models.CharField(max_length=64)
    external_display_name = models.CharField(max_length=150, blank=True, default="")
    match_context = models.JSONField(default=dict, blank=True)
    external_snapshot = models.JSONField(default=dict, blank=True)

class IMNotificationSyncRun(...):
    channel = models.ForeignKey(...)
    status = models.CharField(max_length=32, default="running", db_index=True)
    summary = models.CharField(max_length=255, blank=True, default="")
    total_external_user_count = models.PositiveIntegerField(default=0)
```

Remove `mapping_strategy`, `external_field`, and `message_type` from the channel's core model semantics.

- [ ] **Step 4: Create migration and run the targeted test**

Run: `cd server && pytest apps/system_mgmt/tests/test_im_notification_service.py -k mapping_stores_identity -v`
Expected: PASS

- [ ] **Step 5: Evaluate migration risk and continue unless blocked**

Report in the final implementation summary:
- the exact model changes made
- the generated migration file name
- whether the migration is additive, destructive, or mixed
- any data backfill or compatibility questions

Only stop and align with the user at this stage if migration scope, destructive impact, or data handling expectations are unclear.

### Task 3: Rebuild Sync Service Around Formal Runs

**Files:**
- Modify: `server/apps/system_mgmt/services/im_notification_service.py`
- Modify: `server/apps/system_mgmt/providers/adapters/base.py`
- Modify: `server/apps/system_mgmt/providers/adapters/feishu.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_service.py`

- [ ] **Step 1: Write the failing sync-run tests**

```python
def test_execute_im_notification_sync_run_marks_partial_when_some_external_users_unmatched():
    result = execute_im_notification_sync_run(run.id)
    run.refresh_from_db()

    assert result["result"] is True
    assert run.status == "partial"
    assert IMNotificationUserMapping.objects.filter(channel=channel).count() == 1
    assert run.unmatched_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest apps/system_mgmt/tests/test_im_notification_service.py -k sync_run_marks_partial -v`
Expected: FAIL because async run execution and formal mapping replacement do not exist yet.

- [ ] **Step 3: Implement minimal sync-run execution**

```python
def execute_im_notification_sync_run(run_id: int):
    run = IMNotificationSyncRun.objects.select_related("channel").get(id=run_id)
    config = run.locked_config_snapshot
    external_users = _fetch_external_users(config)
    matched_relations, unmatched_issues, conflict_issues = _match_external_users(...)
    _replace_formal_mappings(...)
    _finalize_run(...)
```

`execute_im_notification_sync_run(run_id)` must treat the run as an immutable execution envelope. All critical matching and sending config must be read from `run.locked_config_snapshot`, not from mutable live channel fields, except where a final channel status update is explicitly required.
`locked_config_snapshot` must at minimum persist `integration_instance_id`, `provider_key`, `platform_match_field`, `external_match_field`, and `external_receive_field`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest apps/system_mgmt/tests/test_im_notification_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/apps/system_mgmt/services/im_notification_service.py server/apps/system_mgmt/providers/adapters/base.py server/apps/system_mgmt/providers/adapters/feishu.py server/apps/system_mgmt/tests/test_im_notification_service.py
git commit -m "feat: redesign im notification sync service"
```

### Task 4: Enforce Channel Validation and Status Transitions

**Files:**
- Modify: `server/apps/system_mgmt/serializers/im_notification_channel_serializer.py`
- Modify: `server/apps/system_mgmt/services/im_notification_service.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_service.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_viewset.py`

- [ ] **Step 1: Write failing validation and status-transition tests**

```python
def test_channel_update_marks_needs_resync_when_critical_config_changes():
    ...

def test_channel_rejects_external_match_field_not_declared_by_manifest():
    ...

def test_send_im_notification_is_blocked_when_channel_needs_resync():
    ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && pytest apps/system_mgmt/tests/test_im_notification_service.py apps/system_mgmt/tests/test_im_notification_viewset.py -k "needs_resync or external_match_field or blocked_when_channel" -v`
Expected: FAIL because field validation and status transitions are not implemented yet.

- [ ] **Step 3: Implement validation and status transitions**

Requirements:
- validate `external_match_field` against manifest `matchable_fields`
- validate `external_receive_field` against manifest `receivable_fields`
- mark `channel.status = "needs_resync"` when critical config changes:
  `integration_instance`, `platform_match_field`, `external_match_field`, `external_receive_field`
- block send unless `channel.status == "ready"`
- keep this behavior explicit even if stale mappings still exist

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest apps/system_mgmt/tests/test_im_notification_service.py apps/system_mgmt/tests/test_im_notification_viewset.py -k "needs_resync or external_match_field or blocked_when_channel" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/apps/system_mgmt/serializers/im_notification_channel_serializer.py server/apps/system_mgmt/services/im_notification_service.py server/apps/system_mgmt/tests/test_im_notification_service.py server/apps/system_mgmt/tests/test_im_notification_viewset.py
git commit -m "feat: enforce im notification channel validation and status transitions"
```

### Task 5: Add Celery Task Entry and Async Endpoint Flow

**Files:**
- Modify: `server/apps/system_mgmt/tasks.py`
- Modify: `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`
- Modify: `server/apps/system_mgmt/serializers/im_notification_channel_serializer.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_viewset.py`

- [ ] **Step 1: Write the failing async endpoint test**

```python
def test_sync_mappings_enqueues_run_and_returns_run_id(api_client, channel):
    response = api_client.post(f"/system_mgmt/im_notification_channel/{channel.id}/sync_mappings/")

    assert response.status_code == 200
    assert response.json()["result"] is True
    assert "run_id" in response.json()["data"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest apps/system_mgmt/tests/test_im_notification_viewset.py -k enqueues_run_and_returns_run_id -v`
Expected: FAIL because the endpoint still runs sync inline.

- [ ] **Step 3: Implement async run creation and task dispatch**

```python
@shared_task
def execute_im_notification_sync_run_task(run_id: int):
    return im_notification_service.execute_im_notification_sync_run(run_id)

def sync_mappings(...):
    run = create_sync_run(channel)
    execute_im_notification_sync_run_task.delay(run.id)
    return JsonResponse({"result": True, "data": {"run_id": run.id}})
```

The request handler must create `IMNotificationSyncRun` and persist `locked_config_snapshot` before Celery dispatch. The Celery task only executes an already-created run.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest apps/system_mgmt/tests/test_im_notification_viewset.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/apps/system_mgmt/tasks.py server/apps/system_mgmt/viewset/im_notification_channel_viewset.py server/apps/system_mgmt/serializers/im_notification_channel_serializer.py server/apps/system_mgmt/tests/test_im_notification_viewset.py
git commit -m "feat: enqueue im notification sync runs"
```

### Task 6: Expose Records and Computed Display State

**Files:**
- Modify: `server/apps/system_mgmt/serializers/im_notification_channel_serializer.py`
- Modify: `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_viewset.py`

- [ ] **Step 1: Write the failing display-state test**

```python
def test_channel_serializer_returns_display_status_from_channel_and_latest_run(channel):
    data = IMNotificationChannelSerializer(channel).data

    assert data["display_status"]
    assert data["latest_sync_status"] == "running"
    assert data["status"] == "pending_sync"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && pytest apps/system_mgmt/tests/test_im_notification_viewset.py -k display_status -v`
Expected: FAIL because the serializer does not yet expose computed display fields.

- [ ] **Step 3: Implement minimal computed read-only fields**

```python
class IMNotificationChannelSerializer(...):
    display_status = serializers.SerializerMethodField()
    latest_sync_status = serializers.SerializerMethodField()
    latest_sync_started_at = serializers.SerializerMethodField()
    latest_sync_finished_at = serializers.SerializerMethodField()
    latest_sync_summary = serializers.SerializerMethodField()
```

Also expose per-channel sync records only:
- `GET /system_mgmt/im_notification_channel/{id}/records/`
- do not add a global cross-channel records endpoint in this phase
- order records by `-started_at, -id`
- use normal pagination only; do not add extra aggregation or a fixed-length latest-N shortcut in this phase

`GET mappings` must return formal matched relations only. Unmatched, conflict, and error diagnostics must remain in `IMNotificationSyncRun.payload`, not in the mappings response.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && pytest apps/system_mgmt/tests/test_im_notification_viewset.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/apps/system_mgmt/serializers/im_notification_channel_serializer.py server/apps/system_mgmt/viewset/im_notification_channel_viewset.py server/apps/system_mgmt/tests/test_im_notification_viewset.py
git commit -m "feat: expose im notification sync display state"
```

### Task 7: Final Verification and Documentation Sync

**Files:**
- Modify: `docs/superpowers/specs/2026-06-16-im-notification-foundation-redesign-design.md` (only if implementation required clarifying note)
- Test: `server/apps/system_mgmt/tests/test_im_notification_service.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_viewset.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_manifest.py`

- [ ] **Step 1: Run focused backend test suite**

Run:

```bash
cd server
pytest apps/system_mgmt/tests/test_im_notification_manifest.py apps/system_mgmt/tests/test_im_notification_service.py apps/system_mgmt/tests/test_im_notification_viewset.py -v
```

Expected: PASS

- [ ] **Step 2: Run any serializer/task regression tests that changed behavior**

Run:

```bash
cd server
pytest apps/system_mgmt/tests/test_user_sync_service.py -k "run or preview" -v
```

Expected: PASS or no regressions in overlapping async/sync patterns

- [ ] **Step 3: Review implementation against the spec**

Checklist:
- formal mapping table stores only matched relations
- channel state excludes running
- run state owns running/success/partial/failed
- sync is Celery-backed
- sync runs are created at request entry before Celery dispatch
- critical config is read from `locked_config_snapshot`
- adapter send path no longer depends on `channel.message_type`
- send flow reads `external_receive_key` and resolves value from `external_snapshot`

- [ ] **Step 4: Commit any final doc or test adjustments**

```bash
git add server/apps/system_mgmt docs/superpowers/specs/2026-06-16-im-notification-foundation-redesign-design.md
git commit -m "test: finalize im notification foundation redesign"
```

## specs: 2026-06-16-im-notification-foundation-redesign-design.md

> 说明：本文档保留设计阶段的过程记录。当前仓库实现已经在此基础上继续演进，凡与现状不一致之处，以当前代码实现为准。

## 背景

当前 IM 应用通知能力已经具备基础的实例绑定、用户拉取、映射同步和测试发送闭环，但底座仍存在几个明显问题：

- 同步逻辑以平台用户全集为起点，把平台内用户逐个与外部 IM 用户比对，导致大量未匹配平台用户写入映射表。
- `IMNotificationUserMapping` 同时承担正式映射关系、同步诊断结果和平台用户匹配快照三类职责，语义混杂。
- `im_notification` provider manifest 仅暴露基础表单字段，没有明确声明外部字段的匹配、发送和身份语义。
- 模型中直接铺设 `external_user_id/open_id/email/mobile/name` 等字段，当前能支撑飞书一期实现，但不利于后续接入更多 IM 应用。

本次设计只覆盖 IM 应用通知底座重构，不覆盖页面/交互语义调整。

## 目标

- 将 IM 应用通知同步改为以外部用户目录为起点。
- 将正式映射关系与同步运行结果拆分为不同模型。
- 将 provider 能力声明补足到可支撑多 IM 应用接入的程度。
- 保持发送链路只依赖正式映射关系，不依赖临时匹配或外部目录再次查询。

## 非目标

- 不在本次设计中调整 IM 应用通知页面的信息架构与视觉交互。
- 不在本次设计中引入消息卡片、富文本等高级消息类型支持。
- 不在本次设计中抽象消息卡片、富文本及其他 provider-specific 消息类型；本轮仅覆盖纯文本消息发送闭环。
- 不在本次设计中覆盖非 IM 通知能力的 manifest 通用重构。

## 现状问题

### 1. 同步语义与业务期望不一致

当前实现会遍历平台用户全集，按 `mapping_strategy` 取平台字段，再去外部用户集合中找匹配项。匹配成功与否都会落到 `IMNotificationUserMapping`。这会产生两个问题：

- 映射表中存在大量未匹配平台用户记录，噪声极高。
- “用户映射”页面展示的更像平台用户匹配审计结果，而不是正式可用的 IM 用户映射关系。

### 2. 正式关系与同步诊断混在一张表里

当前 `IMNotificationUserMapping` 包含：

- 平台用户引用
- 外部用户字段快照
- `status`
- `summary`
- `payload`

这意味着它既表示“正式映射关系”，又表示“同步时未匹配/错误结果”，导致：

- 表语义不稳定
- 查询正式关系不直接
- 发送链路容易误用失败记录

### 3. IM provider contract 不完整

现有 manifest 仅通过 `available_external_fields` 表达“有哪些外部字段”，无法表达：

- 哪些字段允许用于匹配
- 哪些字段允许用于发送
- 哪些字段适合作为外部稳定身份
- 默认建议使用哪个匹配字段、哪个发送字段

这会把字段语义判断推回业务代码，降低底座稳定性。

## 设计原则

### 1. 正式关系与运行结果分离

正式映射关系只表达当前可用的用户映射；同步过程中的未匹配、冲突、异常等都属于运行结果，不进入正式映射表。

### 2. Provider contract 先行

不同 IM 应用的字段差异由 provider manifest 显式声明，业务层不依赖硬编码猜测外部字段语义。

### 3. 适度泛化

底座支持不同 IM provider 的字段差异，但不走“所有语义都动态 JSON 化”的极端路线。核心字段保持结构化，provider 差异通过 manifest 和快照承载。

### 4. 发送链路稳定优先

发送时只读取正式映射关系，不重新做用户匹配，不再次查询外部目录。

## Manifest 设计

在现有 `ProviderManifest -> business_templates/capabilities` 框架上，增强 `im_notification` capability 的字段语义声明。

### 新增的 IM 字段语义元数据

- `available_external_fields`
  外部目录中可返回、可展示、可存入快照的字段全集。
- `matchable_fields`
  允许用于和平台用户做身份匹配的外部字段集合。
- `receivable_fields`
  允许作为消息接收标识传给发送 API 的外部字段集合。
- `identity_fields`
  可作为外部用户稳定身份的字段集合。
- `default_external_match_field`
  默认外部匹配字段。
- `default_external_receive_field`
  默认外部发送字段。

### Manifest 责任边界

- Manifest 负责声明 provider 支持哪些字段和字段语义。
- Adapter 负责把 provider 原始数据转换成 manifest 能解释的外部用户数据结构。
- 业务层负责按照 channel 上保存的匹配/发送策略做正式匹配和发送。

## 模型设计

### `IMNotificationChannel`

`IMNotificationChannel` 只承载通道策略，不承载外部用户数据结构。

建议保留和新增的核心字段：

- `name`
- `integration_instance`
- `enabled`
- `description`
- `status`
- `platform_match_field`
- `external_match_field`
- `external_receive_field`
- `team`

字段语义：

- `platform_match_field`
  平台侧用哪个逻辑字段参与匹配，当前业务层先约定为稳定的小集合，例如 `username/email/phone`。
- `status`
  通道当前运行状态。模型层使用普通字符串字段，不写死 `choices`，由业务层维护状态约定。
- `external_match_field`
  外部目录里用于匹配的平台对应字段，候选值来自 manifest 的 `matchable_fields`。
- `external_receive_field`
  发送消息时作为 receive id 的外部字段，候选值来自 manifest 的 `receivable_fields`。

当前 `mapping_strategy` 应被拆分为 `platform_match_field + external_match_field`。
`message_type` 不再作为 `IMNotificationChannel` 的核心配置字段保留。本轮底座仅保证文本消息发送闭环，发送适配器按 provider 当前最小可用能力默认发送文本消息。

当前业务层约定的最小状态集合：

- `pending_sync`
  配置已完成，但从未执行过同步。
- `ready`
  已有当前策略下的有效正式映射，可发送。
- `needs_resync`
  历史上同步过，但关键配置已变更，旧映射失效，必须重同步。
- `disabled`
  显式停用，不可发送。

展示约定：

- `channel.status` 用于业务状态建模，不直接作为最终用户展示状态。
- 用户展示状态由后端基于 `channel.status + latest IMNotificationSyncRun` 组合计算后输出。
- 后端应额外提供只读展示信息，例如：
  - `display_status`
  - `latest_sync_status`
  - `latest_sync_started_at`
  - `latest_sync_finished_at`
  - `latest_sync_summary`
- 前端优先展示上述组合状态与最近一次同步结果，用于表达“是否已开始同步、最近一次同步时间、最近一次同步结果”。

### `IMNotificationUserMapping`

`IMNotificationUserMapping` 只承载正式已匹配关系。

建议字段：

- `channel`
- `user`
- `external_identity_key`
- `external_identity_value`
- `external_receive_key`
- `external_display_name`
- `match_context`
- `external_snapshot`
- `synced_at`

字段语义：

- `user`
  对应的平台用户，必须存在。
- `external_identity_key`
  用于稳定标识该外部用户的主身份字段名，实际值从 `external_snapshot` 中读取。
- `external_identity_value`
  用于稳定标识该外部用户的主身份字段值，作为正式关系的外部唯一身份，并用于数据库唯一约束。
- `external_receive_key`
  发送消息时采用的外部字段名，实际值运行时从 `external_snapshot` 中读取。
- `external_display_name`
  页面展示使用的外部名称。
- `match_context`
  本次匹配过程的上下文信息，例如平台匹配字段、平台匹配值、外部匹配字段、外部匹配值等。
- `external_snapshot`
  外部用户原始快照，承载 provider 差异字段。

设计约束：

- `external_snapshot` 中必须存在 `external_identity_key` 指向的字段和值，并与 `external_identity_value` 一致。
- `external_snapshot` 中必须存在 `external_receive_key` 指向的字段和值。
- `external_identity_key` 和 `external_receive_key` 允许相同，也允许不同。
- 匹配过程中的 value 不再作为独立模型硬字段重复存储，避免与 `external_snapshot` 双写。
- `external_receive_value` 不作为模型硬字段单独存储。

明确删除或不再保留以下职责：

- `status`
- `summary`
- 未匹配记录
- 错误记录
- 平台用户全量扫描结果

建议唯一约束：

- `(channel, user)` 唯一
- `(channel, external_identity_key, external_identity_value)` 唯一

### `IMNotificationSyncRun`

新增 `IMNotificationSyncRun` 记录一次同步运行结果。

建议字段：

- `channel`
- `status`
- `summary`
- `total_external_user_count`
- `matched_count`
- `unmatched_count`
- `conflict_count`
- `locked_config_snapshot`
- `payload`
- `started_at`
- `finished_at`

说明：

- `status` 使用普通字符串字段，不在模型层写死 `choices`。
- 业务层当前约定三态：
  - `success`
  - `partial`
  - `failed`
- 任务执行中使用 `running` 作为 `IMNotificationSyncRun` 的运行态，由业务层约定，不写死在模型 `choices` 中。
- `locked_config_snapshot` 用于记录任务发起时的 channel 关键配置快照，避免异步执行时读取到后续被修改的配置。
- `payload` 保存未匹配用户列表、冲突明细以及 provider 返回的附加诊断信息（例如 request id、错误明细等）。

`locked_config_snapshot` 至少应包含：
- `integration_instance_id`
- `provider_key`
- `platform_match_field`
- `external_match_field`
- `external_receive_field`

`locked_config_snapshot` 的职责不只是异步读取保护，还包括：
- 为一次同步请求提供稳定可追踪的 `run_id`
- 支撑请求入口对同 channel 并发运行的控制
- 固化本次同步运行的配置语义，避免任务排队期间 channel 配置变化导致结果不可解释
- 为后续排查和审计保留“本次同步实际按什么配置执行”的证据

## 流程设计

### 同步流程

同步必须以外部用户目录为起点，不允许回退到平台用户全集扫描。

#### 异步执行模式

IM 应用通知同步复用用户同步的分层思路与运行记录建模方式，但调度方式采用“请求入口创建 run 并锁定配置快照，Worker 异步执行”的模式，通过 Celery 后台执行。
这样可以在请求返回时立即获得稳定的 `run_id`，便于前端轮询、日志关联和故障排查；同时保证一次同步运行始终基于发起时的配置快照执行，不受后续 channel 配置变更影响。

建议链路：

1. 用户点击“同步映射”
2. 接口先检查当前 channel 是否已有 `running` 的同步任务
3. 若无运行中任务，则创建 `IMNotificationSyncRun(status=running)`
4. 在 run 上保存 `locked_config_snapshot`
5. 接口投递 Celery 任务并立即返回 `run_id`
6. Worker 在后台基于该快照执行同步
7. Worker 更新 `IMNotificationSyncRun` 为 `success / partial / failed`
8. 前端通过 run 记录或 channel 展示态查询最新同步结果

说明：

- `channel.status` 不进入 `running`
- `running` 只属于 `IMNotificationSyncRun`
- 新建策略首次发起同步时，`channel.status` 仍然保持 `pending_sync`
- 前端看到的“同步中”由后端根据 `channel.status + latest run.status` 组合计算

#### 接口语义

- `POST sync_mappings`
  - 创建一条 `IMNotificationSyncRun`
  - 保存 `locked_config_snapshot`
  - 投递 Celery 任务
  - 返回 `run_id`
- `GET records`
  - 查询指定 channel 的同步运行记录
- `GET mappings`
  - 仅查询正式映射关系

#### 并发控制

同一个 `channel` 同一时刻只允许一个 `running` 的同步任务。

规则：

- 如果已有 `running` 的 `IMNotificationSyncRun`
- 再次触发同步请求时，默认直接拒绝并返回“已有同步进行中”
- 不允许同一 channel 的多个同步任务并行执行

本次设计不支持：

- 同一 channel 并行同步
- 自动抢占式覆盖
- 在已有 `running` 任务时再次排队多个同步任务

如果后续需要支持强制重跑，应单独设计“取消当前任务并重试”的控制语义。

流程如下：

1. 读取 `IMNotificationChannel`
2. 读取 `IMNotificationSyncRun.locked_config_snapshot`
3. 根据快照中的 `integration_instance` 获取 provider manifest 和 adapter
4. 调用 adapter 拉取外部用户列表
5. adapter 返回标准化外部用户集合
6. 服务层从 `locked_config_snapshot` 读取：
   - `platform_match_field`
   - `external_match_field`
   - `external_receive_field`
7. 遍历外部用户并执行平台匹配
8. 在内存中得到：
   - `matched_relations`
   - `unmatched_issues`
   - `conflict_issues`
9. 在事务内提交结果：
   - 根据规则更新 `IMNotificationUserMapping`
   - 更新 `IMNotificationSyncRun`
   - 必要时更新 `channel.status`
10. 根据结果写入运行状态：
   - 全部匹配成功：`success`
   - 存在正式映射更新且同时存在未匹配或冲突：`partial`
   - provider 调用失败或执行流程失败：`failed`

#### 事务性提交约束

Worker 不得边拉取边写正式映射表，不得边匹配边逐条提交正式结果。

建议做法：

1. 完整拉取并完成整轮匹配计算
2. 形成本次可信的匹配结果集合
3. 在一个事务内替换正式映射并更新 run 结果

这样可以避免异步任务中途失败时把正式映射表写成半成品状态。

#### 配置变更后的行为

以下字段视为会改变映射语义的关键配置：

- `integration_instance`
- `platform_match_field`
- `external_match_field`
- `external_receive_field`

当上述字段发生变更时：

1. 保存新配置
2. `channel.status` 更新为 `needs_resync`
3. 发送链路被硬阻断
4. 旧正式映射关系保留在 `IMNotificationUserMapping` 中，但不再视为当前策略下可用映射
5. 用户执行新一轮同步

重新同步后的处理规则：

- `success`
  - 使用新结果整体替换旧映射
  - `channel.status` 变为 `ready`
- `partial`
  - 使用新结果中已匹配成功的关系整体替换旧映射
  - `channel.status` 变为 `ready`
  - 未匹配/冲突问题记录在 `IMNotificationSyncRun`
- `failed`
  - 保留旧映射不变
  - `channel.status` 继续保持 `needs_resync`
  - 发送继续硬阻断

说明：

- “旧映射/过期映射”语义当前只挂在 `channel` 层，不下沉到 `IMNotificationUserMapping`。
- 正式映射表在任意时刻只代表一套策略下的一致结果，不允许旧策略结果与新策略结果混用。
- `channel.status` 不承载 `running` 一类运行态；运行态只由 `IMNotificationSyncRun` 表达。

#### 匹配规则

服务层不依赖 provider 固定字段名，而是通过 channel 配置和 manifest 语义做字段读取：

- 读取外部用户的 `external_match_field`
- 用该值去平台用户的 `platform_match_field` 中做精确匹配

匹配结果分类：

- 外部匹配值为空：`missing_external_match_value`
- 平台无对应用户：`platform_user_not_found`
- 平台命中多个用户：`multiple_platform_users`
- 唯一命中：建立正式映射关系

### 发送流程

发送链路只依赖正式映射关系，不重新匹配，不查询外部目录。

流程如下：

1. 业务传入 `channel_id + 平台用户列表`
2. 查询 `IMNotificationUserMapping`
3. 对每条正式关系读取 `external_receive_key`
4. 从 `external_snapshot` 中解析对应的发送值
5. 调用 adapter 执行发送

发送链路不读取 `IMNotificationSyncRun`，也不重新使用平台字段推导外部身份。
未匹配、冲突、错误等运行期诊断信息只保留在 `IMNotificationSyncRun.payload` 中，不混入 `GET mappings` 返回结果。

## Adapter 责任边界

Adapter 只做 provider 协议相关工作：

- 拉取外部用户目录
- 把原始用户数据转换为底座能消费的外部用户结构
- 按给定 receive field 和 receive values 调 provider 发送消息

Adapter 不承担：

- 平台用户匹配
- 正式映射关系落库
- 同步结果状态判定

这些职责统一留在系统管理服务层。

## 兼容与迁移

由于当前功能尚未上线，本次设计允许直接调整现有模型语义，而不以历史兼容为优先目标。

本次变更以服务端底座重构为主，优先完成模型、服务、任务与接口语义调整。前端页面适配可在后续阶段单独完成，不影响本次底座设计结论。

迁移方向：

- `IMNotificationChannel`
  - 用 `platform_match_field/external_match_field/external_receive_field` 替代现有 `mapping_strategy` 核心语义
- `IMNotificationUserMapping`
  - 从“平台匹配结果表”迁移为“正式关系表”
- 新增 `IMNotificationSyncRun`
- Manifest 中为 `im_notification` 增加字段语义声明

## 风险与约束

### 1. Provider contract 不完整会直接影响底座稳定性

如果 provider 未明确声明可匹配字段、可发送字段和身份字段，业务层不应允许其进入可用状态。

### 2. 正式映射表不得承载失败语义

`IMNotificationUserMapping` 中不得再写入未匹配、冲突或错误记录，否则会再次混淆正式关系与运行诊断。

### 3. 不允许回退到平台全量扫描

这是本次底座重构的硬约束，后续实现和维护均需遵守。

### 4. 发送链路必须只依赖正式映射关系

否则同步和发送会重新耦合，降低链路稳定性。

## 测试与验证方向

本次设计完成后，后续实现至少应覆盖以下验证：

- manifest 对 IM capability 字段语义的声明校验
- `IMNotificationChannel` 对匹配/发送字段的合法性校验
- 同步流程在以下场景的结果：
  - 全量匹配成功
  - 部分匹配成功
  - provider 调用失败
  - 外部匹配字段缺失
  - 平台用户冲突
- 正式映射表的 upsert 和陈旧关系清理
- 发送链路只读取正式映射关系，不触发重新匹配

## 决策结论

本次 IM 应用通知底座重构采用以下决策：

- 同步结果采用业务层三态 `success / partial / failed`
- 正式映射表只保存成功关系
- 同步运行结果独立建模
- provider manifest 补足字段语义声明
- 通道策略显式区分平台匹配字段、外部匹配字段和外部发送字段
- 同步链路以外部用户目录为起点
- 发送链路只依赖正式映射关系
