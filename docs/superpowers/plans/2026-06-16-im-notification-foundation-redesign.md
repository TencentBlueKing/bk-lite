# IM Notification Foundation Redesign Implementation Plan

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
