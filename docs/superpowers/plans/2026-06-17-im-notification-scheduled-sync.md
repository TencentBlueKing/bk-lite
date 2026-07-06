# IM Notification Scheduled Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-channel scheduled sync support to IM notification by reusing the existing async run execution chain and periodic-task infrastructure.

**Architecture:** The implementation extends `IMNotificationChannel` with `schedule_config`, adds `trigger_mode` to `IMNotificationSyncRun`, and uses `PeriodicTaskUtils + django_celery_beat` to manage one periodic task per IM channel. Scheduled execution remains a thin trigger path that creates a run with `trigger_mode="schedule"` and then dispatches the existing async run executor.

**Tech Stack:** Django 4.2, Celery, django-celery-beat, DRF, pytest

## Execution Constraints

- The primary objective is to complete all task goals in this plan end-to-end.
- Perform the full verification and review after all planned tasks are completed; do not stop for a separate full review after each individual task.
- Prefer lightweight, directly relevant validation and review first; avoid spending disproportionate effort on heavyweight verification unless risk or uncertainty justifies it.
- Do not force through ambiguous issues. If design intent, migration behavior, compatibility scope, or implementation direction becomes unclear, stop and align with the user before continuing.
- Follow existing repository code style and implementation patterns.
- Keep changes tightly scoped to this redesign; avoid unrelated refactors, opportunistic cleanup, or broad restructuring.
- Treat task completion as behaviorally meeting the planned end-state, not merely landing partial code or passing isolated interim tests.
- This plan focuses on backend completion first. The current code state already exposes scheduled-sync related behavior through the aligned IM notification page without introducing a separate frontend-only follow-up plan.
- Prefer no temporary compatibility layer unless explicitly required.
- If migration strategy, destructive change scope, or data handling expectations become unclear, stop and align with the user before continuing.
- Execute this plan in `executing-plans` style: follow the documented task order in a single mainline flow, avoid large parallel workstreams, and use only lightweight interim validation until final verification.

## Migration Constraint

- IM scheduled-sync model changes must **not** land as a new migration patch file.
- Use the established IM migration strategy:
  - roll back to `0035`
  - regenerate and adjust `0036`
- Merge the scheduled-sync schema changes directly into:
  - `server/apps/system_mgmt/migrations/0036_imnotificationchannel_imnotificationusermapping.py`

---

## File Structure

### Existing files to modify

- `server/apps/system_mgmt/models/im_notification_channel.py`
  Add `schedule_config` to the channel and add `trigger_mode` to sync runs; reuse `PeriodicTaskUtils` for per-channel periodic task management.
- `server/apps/system_mgmt/models/__init__.py`
  Export the updated IM notification models if required.
- `server/apps/system_mgmt/migrations/0036_imnotificationchannel_imnotificationusermapping.py`
  Regenerate the existing IM migration to include scheduled-sync schema changes instead of creating a new migration.
- `server/apps/system_mgmt/services/im_notification_service.py`
  Extend run creation to accept `trigger_mode`, keep concurrency semantics, and define scheduled-trigger skip behavior.
- `server/apps/system_mgmt/tasks.py`
  Add the thin scheduled-trigger task that creates runs and dispatches the existing async executor.
- `server/apps/system_mgmt/serializers/im_notification_channel_serializer.py`
  Validate and persist `schedule_config`, and synchronize periodic tasks after create/update.
- `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`
  Delete the channel’s periodic task on destroy.
- `server/apps/system_mgmt/tests/test_im_notification_service.py`
  Add scheduled-run creation, skip, and trigger-mode coverage.
- `server/apps/system_mgmt/tests/test_im_notification_viewset.py`
  Add serializer/viewset coverage for schedule config and destroy cleanup.

### Potential new files

- None required if scheduled-sync behavior stays inside the current IM service/task/test layout.

### Reference files to read during implementation

- `docs/superpowers/specs/2026-06-17-im-notification-scheduled-sync-design.md`
- `docs/superpowers/specs/2026-06-16-im-notification-foundation-redesign-design.md`
- `docs/superpowers/plans/2026-06-16-im-notification-foundation-redesign.md`
- `server/apps/system_mgmt/models/user_sync_source.py`
- `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`
- `server/apps/system_mgmt/tasks.py`

---

### Task 1: Extend IM Models for Scheduling

**Files:**
- Modify: `server/apps/system_mgmt/models/im_notification_channel.py`
- Modify: `server/apps/system_mgmt/models/__init__.py`
- Modify: `server/apps/system_mgmt/migrations/0036_imnotificationchannel_imnotificationusermapping.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_service.py`

- [ ] **Step 1: Write the failing model test**

```python
def test_im_notification_channel_stores_schedule_config_and_run_trigger_mode(channel):
    channel.schedule_config = {"enabled": True, "sync_time": "02:00"}
    channel.save(update_fields=["schedule_config"])

    run = IMNotificationSyncRun.objects.create(
        channel=channel,
        trigger_mode="schedule",
        status="running",
    )

    channel.refresh_from_db()
    assert channel.schedule_config["enabled"] is True
    assert channel.schedule_config["sync_time"] == "02:00"
    assert run.trigger_mode == "schedule"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_im_notification_service.py -k "schedule_config_and_run_trigger_mode" -v --create-db`
Expected: FAIL because the current IM models do not expose the scheduled-sync fields.

- [x] **Step 3: Implement the model changes and regenerate `0036`**

Update the models so that:

```python
class IMNotificationChannel(..., PeriodicTaskUtils):
    ...
    schedule_config = models.JSONField(default=dict, blank=True)

class IMNotificationSyncRun(...):
    ...
    trigger_mode = models.CharField(max_length=16, default="manual")
```

Also add:

```python
def periodic_task_name(self):
    return f"im_notification_channel_{self.id}"

def create_sync_periodic_task(self):
    ...

def delete_sync_periodic_task(self):
    ...
```

Migration handling for this task must follow the required strategy:

- roll back to `0035`
- regenerate and edit `0036`
- do not create `0037+`

- [ ] **Step 4: Run the targeted test to verify it passes**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_im_notification_service.py -k "schedule_config_and_run_trigger_mode" -v --create-db`
Expected: PASS

- [ ] **Step 5: Record migration outcome and continue**

The final implementation summary must explicitly report:

- the exact fields added to `IMNotificationChannel`
- the exact fields added to `IMNotificationSyncRun`
- that `0036` was regenerated/edited instead of creating a new migration file
- whether the migration remains destructive or mixed

Only stop here if the `0035 -> 0036` migration strategy becomes unclear in practice.

### Task 2: Add Scheduled Trigger Semantics to the IM Service

**Files:**
- Modify: `server/apps/system_mgmt/services/im_notification_service.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_service.py`

- [ ] **Step 1: Write the failing scheduled-run tests**

```python
def test_create_im_notification_sync_run_accepts_trigger_mode(channel):
    result = create_im_notification_sync_run(channel.id, trigger_mode="schedule")
    run = IMNotificationSyncRun.objects.get(id=result["data"]["run_id"])
    assert run.trigger_mode == "schedule"

def test_schedule_trigger_skips_when_run_is_already_running(channel):
    IMNotificationSyncRun.objects.create(channel=channel, trigger_mode="manual", status="running")
    result = create_im_notification_sync_run(channel.id, trigger_mode="schedule")
    assert result["result"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_im_notification_service.py -k "trigger_mode or already_running" -v --create-db`
Expected: FAIL because run creation does not yet distinguish trigger source.

- [x] **Step 3: Extend the service with trigger-mode support**

Update:

```python
def create_im_notification_sync_run(channel_id: int, trigger_mode: str = "manual"):
    ...
    run = IMNotificationSyncRun.objects.create(
        channel=channel,
        trigger_mode=trigger_mode,
        ...
    )
```

Keep the current concurrency rule:

- one `running` run per channel

And keep the semantics clear:

- `trigger_mode` only records the source of run creation
- it must not alter run status semantics

- [ ] **Step 4: Define the scheduled-skip behavior explicitly**

The service path used by scheduled triggers must treat these as normal non-run cases:

- an existing `running` run
- a disabled channel
- a non-ready integration instance

These must not create a `failed` run.

- [ ] **Step 5: Run the targeted tests to verify they pass**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_im_notification_service.py -k "trigger_mode or already_running" -v --create-db`
Expected: PASS

### Task 3: Add the Thin Scheduled Trigger Task

**Files:**
- Modify: `server/apps/system_mgmt/tasks.py`
- Modify: `server/apps/system_mgmt/services/im_notification_service.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_service.py`

- [ ] **Step 1: Write the failing scheduled-task test**

```python
def test_schedule_im_notification_sync_enqueues_existing_run_executor(channel):
    with patch("apps.system_mgmt.tasks.execute_im_notification_sync_run_task.delay") as mock_delay:
        result = schedule_im_notification_sync(channel.id)
    assert result["result"] is True
    mock_delay.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_im_notification_service.py -k "schedule_im_notification_sync_enqueues" -v --create-db`
Expected: FAIL because the scheduled trigger task does not exist yet.

- [x] **Step 3: Implement the thin scheduling task**

Add a task such as:

```python
@shared_task
def schedule_im_notification_sync(channel_id):
    result = im_notification_service.create_im_notification_sync_run(
        int(channel_id),
        trigger_mode="schedule",
    )
    if not result.get("result"):
        return result
    run_id = result["data"]["run_id"]
    execute_im_notification_sync_run_task.delay(run_id)
    return result
```

This task must:

- create a scheduled run when allowed
- dispatch the existing async run executor
- return `result=False` with a readable message when no run is created

The scheduled-trigger return contract must be kept explicit:

- `result=True`: a run was created and dispatched
- `result=False`: no run was created for this schedule tick
- `result=False` in this path must not create a `failed` run

- [ ] **Step 4: Run the targeted test to verify it passes**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_im_notification_service.py -k "schedule_im_notification_sync_enqueues" -v --create-db`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/apps/system_mgmt/tasks.py server/apps/system_mgmt/services/im_notification_service.py server/apps/system_mgmt/tests/test_im_notification_service.py
git commit -m "feat: add im notification scheduled trigger task"
```

### Task 4: Synchronize Periodic Tasks from the Channel Serializer Lifecycle

**Files:**
- Modify: `server/apps/system_mgmt/serializers/im_notification_channel_serializer.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_viewset.py`

- [ ] **Step 1: Write the failing serializer lifecycle test**

```python
def test_channel_create_syncs_periodic_task_when_schedule_enabled(ready_im_instance):
    serializer = IMNotificationChannelSerializer(
        data={
            "name": "scheduled-channel",
            "integration_instance": ready_im_instance.id,
            "enabled": True,
            "description": "",
            "platform_match_field": "email",
            "external_match_field": "email",
            "external_receive_field": "user_id",
            "schedule_config": {"enabled": True, "sync_time": "02:00"},
        },
    )
    assert serializer.is_valid(), serializer.errors

def test_channel_update_syncs_periodic_task_when_schedule_enabled(channel, ready_im_instance):
    serializer = IMNotificationChannelSerializer(
        instance=channel,
        data={
            "name": channel.name,
            "integration_instance": ready_im_instance.id,
            "enabled": True,
            "description": channel.description,
            "platform_match_field": "email",
            "external_match_field": "email",
            "external_receive_field": "user_id",
            "schedule_config": {"enabled": True, "sync_time": "02:00"},
        },
    )
    assert serializer.is_valid(), serializer.errors
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_im_notification_viewset.py -k "periodic_task_when_schedule_enabled" -v --create-db`
Expected: FAIL because IM serializer lifecycle does not yet manage periodic tasks.

- [x] **Step 3: Implement serializer support for `schedule_config` and task sync**

Update the serializer so it:

- accepts `schedule_config` as an object
- persists it during create/update
- calls a private `_sync_periodic_task(instance)` helper after save

The helper should mirror `user_sync` semantics:

- if `instance.enabled and schedule_config.enabled and sync_time`: create/update periodic task
- else: delete periodic task

- [ ] **Step 4: Make the lifecycle tests verify save-time behavior explicitly**

Each lifecycle test must:

- call `serializer.save()`
- assert `schedule_config` was persisted
- assert the periodic-task sync method was invoked on the saved instance

This task must explicitly cover both:

- create path
- update path

- [ ] **Step 5: Run the targeted test to verify it passes**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_im_notification_viewset.py -k "periodic_task_when_schedule_enabled" -v --create-db`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add server/apps/system_mgmt/serializers/im_notification_channel_serializer.py server/apps/system_mgmt/tests/test_im_notification_viewset.py
git commit -m "feat: sync im notification periodic tasks from serializer lifecycle"
```

### Task 5: Clean Up Periodic Tasks on Channel Deletion

**Files:**
- Modify: `server/apps/system_mgmt/viewset/im_notification_channel_viewset.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_viewset.py`

- [ ] **Step 1: Write the failing destroy cleanup test**

```python
def test_destroy_channel_deletes_periodic_task(api_client, channel):
    with patch(
        "apps.system_mgmt.viewset.im_notification_channel_viewset.IMNotificationChannel.delete_sync_periodic_task"
    ) as mock_delete_periodic_task:
        response = api_client.delete(f"/api/v1/system_mgmt/im_notification_channel/{channel.id}/")
    assert response.status_code == 204
    mock_delete_periodic_task.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_im_notification_viewset.py -k "destroy_channel_deletes_periodic_task" -v --create-db`
Expected: FAIL because IM channel deletion does not yet clean scheduled tasks explicitly.

- [x] **Step 3: Add periodic-task cleanup on destroy**

Before or during delete handling, call:

```python
obj.delete_sync_periodic_task()
```

Keep the existing operation-log behavior intact.

- [ ] **Step 4: Run the targeted test to verify it passes**

Run: `cd server && uv run pytest apps/system_mgmt/tests/test_im_notification_viewset.py -k "destroy_channel_deletes_periodic_task" -v --create-db`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/apps/system_mgmt/viewset/im_notification_channel_viewset.py server/apps/system_mgmt/tests/test_im_notification_viewset.py
git commit -m "feat: cleanup im notification periodic task on delete"
```

### Task 6: Final Verification and Review

**Files:**
- Test: `server/apps/system_mgmt/tests/test_im_notification_service.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_viewset.py`
- Test: `server/apps/system_mgmt/tests/test_im_notification_manifest.py`

- [x] **Step 1: Run focused IM backend tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_im_notification_manifest.py apps/system_mgmt/tests/test_im_notification_service.py apps/system_mgmt/tests/test_im_notification_viewset.py -v --create-db
```

Expected: PASS

- [ ] **Step 2: Run overlapping async regression coverage**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_service.py -k "run or preview" -v --create-db
```

Expected: PASS

- [ ] **Step 3: Run explicit scheduled-first-sync coverage**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_im_notification_service.py -k "pending_sync and schedule" -v --create-db
```

Expected: PASS, proving a `pending_sync` channel can complete its first sync through the scheduled path.

- [ ] **Step 4: Review implementation against the scheduled-sync spec**

Checklist:

- `schedule_config` exists on `IMNotificationChannel`
- `trigger_mode` exists on `IMNotificationSyncRun`
- `trigger_mode` only records run creation source
- periodic task lifecycle is synchronized on create/update/delete
- scheduled execution creates runs with `trigger_mode="schedule"`
- scheduled execution dispatches the existing async run executor
- scheduled non-run cases do not create `failed` runs
- a `pending_sync` channel can complete its first sync through the scheduled path
- no new migration file was added; changes were merged into regenerated `0036`

- [ ] **Step 5: Commit any final adjustments**

```bash
git add server/apps/system_mgmt
git commit -m "feat: add im notification scheduled sync"
```
