# Historical Superpowers change: 2026-07-01-system-manager-user-sync-schedule-cutover

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-07-01-system-manager-user-sync-schedule-cutover.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut the system-manager user-sync strategy over to the new mode-based schedule model so the backend and frontend support `disabled` / `daily` / `weekly` / `interval_hours`, with `interval_hours` aligned to `00:00`, no legacy schedule payload compatibility, and no data backfill.

**Architecture:** Keep `UserSyncSource.enabled` as the source-level runtime switch and move auto-sync onto a new mode-based `schedule_config` contract. `UserSyncSource` remains responsible for translating business `schedule_config` into a neutral `schedule_spec`, while a new static helper on `PeriodicTaskUtils` writes `django_celery_beat` objects from that spec without changing the old daily-only helper used by other modules. The frontend strategy modal, payload builders, and list summary switch to the new contract in one clean cutover.

**Tech Stack:** Next.js App Router, React 19, TypeScript, Ant Design, Django 4.2, django-celery-beat, pytest

## Execution Constraints

- The primary objective is to complete all task goals in this plan end-to-end.
- Perform the full verification and review after all planned tasks are completed; do not stop for a separate full review after each individual task.
- Prefer lightweight, directly relevant validation and review first; avoid spending disproportionate effort on heavyweight verification unless risk or uncertainty justifies it.
- Do not force through ambiguous issues. If schedule semantics, weekday encoding, interval alignment, or helper boundaries become unclear, stop and align with the user before continuing.
- Follow existing repository code style and implementation patterns.
- Keep changes tightly scoped to this user-sync schedule cutover; avoid unrelated refactors, opportunistic cleanup, or broad restructuring.
- Treat task completion as behaviorally meeting the planned end-state, not merely landing partial code or passing isolated interim tests.
- Prefer no temporary compatibility layer unless explicitly required.
- User sync schedule cutover is a clean switch: no old payload mapping, no read compatibility, no backfill command.
- `interval_hours` is constrained to `1 / 2 / 3 / 4 / 6 / 8 / 12` and is always aligned to `00:00`.
- `PeriodicTaskUtils.create_periodic_task(sync_time, ...)` must remain available for old daily-only callers; new user-sync schedule behavior must use a new static helper.
- Any git commit must be explicitly approved by the user first; do not commit during execution unless the user asks.
- Execute this plan in `executing-plans` style: follow the documented task order in a single mainline flow, avoid large parallel workstreams, and use only lightweight interim validation until final verification.

---

## File Structure

### Existing files to modify

- `server/apps/core/mixinx.py`
  Keep the old daily-only `create_periodic_task(sync_time, ...)` unchanged and add a new static helper that creates periodic tasks from an explicit `schedule_spec`.
- `server/apps/system_mgmt/models/user_sync_source.py`
  Replace the daily-only `schedule_config.sync_time` assumption with mode-based schedule-spec generation for user sync.
- `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`
  Replace old schedule validation with mode-based validation and make periodic-task sync depend only on the new schedule contract.
- `server/apps/system_mgmt/services/capability_contract_service.py`
  Keep shared legacy schedule validation stable for old callers and add a user-sync-specific validator path for the new contract.
- `server/apps/system_mgmt/tests/test_user_sync_service.py`
  Add/replace backend tests for schedule-spec generation, interval alignment, old-payload rejection, and user-sync-specific validator behavior.
- `server/apps/system_mgmt/tests/test_user_sync_source_viewset.py`
  Add/replace API contract tests for accepting only the new schedule payload shape.
- `web/src/app/system-manager/types/user-sync.ts`
  Replace the old `schedule_enabled + sync_time` strategy form contract with the new `schedule_mode` model.
- `web/src/app/system-manager/utils/userSyncUtils.ts`
  Replace daily-only schedule builders/parsers with new payload builders for `disabled` / `daily` / `weekly` / `interval_hours`.
- `web/src/app/system-manager/components/user/user-sync/UserSyncStrategyModal.tsx`
  Rebuild the modal fields around source status plus mode-based auto-sync controls.
- `web/src/app/system-manager/(pages)/user/user-sync/page.tsx`
  Update strategy submission, card summary text, and any disabled-state handling to the new contract.
- `web/src/app/system-manager/utils/userSyncPageUtils.ts`
  Move or rewrite schedule summary generation so the list shows meaningful new-mode summaries.
- `web/src/app/system-manager/locales/zh.json`
  Add/update copy for the new strategy form and schedule summaries.
- `web/src/app/system-manager/locales/en.json`
  Same as above for English.
- `web/src/stories/system-manager-user-sync-source-list.stories.tsx`
  Update story data to match the new schedule summary format.

### Reference files to read during implementation

- `docs/superpowers/specs/2026-07-01-system-manager-user-sync-schedule-strategy-design.md`
- `web/src/app/system-manager/components/channel/im-notification/IMNotificationConfigModal.tsx`
- `server/apps/core/mixinx.py`
- `server/apps/system_mgmt/models/user_sync_source.py`
- `server/apps/system_mgmt/services/capability_contract_service.py`

---

### Task 1: Add backend schedule-spec support without changing the old helper

**Files:**
- Modify: `server/apps/core/mixinx.py`
- Modify: `server/apps/system_mgmt/models/user_sync_source.py`
- Test: `server/apps/system_mgmt/tests/test_user_sync_service.py`

**Interfaces:**
- Consumes: existing `PeriodicTaskUtils.delete_periodic_task(task_name)` and `UserSyncSource.periodic_task_name()`
- Produces:
  - `PeriodicTaskUtils.create_periodic_task_from_spec(schedule_spec: dict, task_name: str, task_args: str, task_path: str) -> None`
  - `UserSyncSource.build_schedule_spec() -> dict | None`
  - `UserSyncSource.create_sync_periodic_task() -> None` using `build_schedule_spec()`

- [ ] **Step 1: Write failing backend tests for schedule-spec generation**

Add tests covering:

```python
@pytest.mark.django_db
def test_user_sync_source_builds_daily_schedule_spec(ready_integration_instance):
    source = UserSyncSource.objects.create(
        name="daily-source",
        integration_instance=ready_integration_instance,
        root_group_name="Daily Root",
        field_mapping={},
        business_config={"root_department_id": "dept-root"},
        schedule_config={"mode": "daily", "time": "02:15", "timezone": "Asia/Shanghai"},
    )

    assert source.build_schedule_spec() == {
        "kind": "crontab",
        "minute": "15",
        "hour": "2",
        "day_of_week": "*",
        "day_of_month": "*",
        "month_of_year": "*",
    }


@pytest.mark.django_db
def test_user_sync_source_builds_weekly_schedule_spec(ready_integration_instance):
    source = UserSyncSource.objects.create(
        name="weekly-source",
        integration_instance=ready_integration_instance,
        root_group_name="Weekly Root",
        field_mapping={},
        business_config={"root_department_id": "dept-root"},
        schedule_config={"mode": "weekly", "time": "03:20", "weekdays": [1, 3, 5], "timezone": "Asia/Shanghai"},
    )

    assert source.build_schedule_spec() == {
        "kind": "crontab",
        "minute": "20",
        "hour": "3",
        "day_of_week": "1,3,5",
        "day_of_month": "*",
        "month_of_year": "*",
    }


@pytest.mark.django_db
def test_user_sync_source_builds_interval_hours_schedule_spec_from_midnight_alignment(ready_integration_instance):
    source = UserSyncSource.objects.create(
        name="interval-source",
        integration_instance=ready_integration_instance,
        root_group_name="Interval Root",
        field_mapping={},
        business_config={"root_department_id": "dept-root"},
        schedule_config={"mode": "interval_hours", "interval_hours": 6, "timezone": "Asia/Shanghai"},
    )

    assert source.build_schedule_spec() == {
        "kind": "crontab",
        "minute": "0",
        "hour": "*/6",
        "day_of_week": "*",
        "day_of_month": "*",
        "month_of_year": "*",
    }
```

- [ ] **Step 2: Run the targeted backend tests to confirm failure**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_service.py -k "builds_daily_schedule_spec or builds_weekly_schedule_spec or builds_interval_hours_schedule_spec" -v
```

Expected:
- FAIL because `build_schedule_spec` and/or the new helper behavior does not exist yet.

- [ ] **Step 3: Implement the new static helper and user-sync schedule-spec builder**

Implement along these lines:

```python
class PeriodicTaskUtils:
    @staticmethod
    def create_periodic_task_from_spec(schedule_spec, task_name, task_args, task_path):
        from django.utils import timezone
        from django_celery_beat.models import CrontabSchedule, PeriodicTask

        if schedule_spec.get("kind") != "crontab":
            raise ValueError(f"Unsupported schedule kind: {schedule_spec.get('kind')}")

        schedule, _ = CrontabSchedule.objects.get_or_create(
            minute=str(schedule_spec["minute"]),
            hour=str(schedule_spec["hour"]),
            day_of_week=str(schedule_spec.get("day_of_week", "*")),
            day_of_month=str(schedule_spec.get("day_of_month", "*")),
            month_of_year=str(schedule_spec.get("month_of_year", "*")),
            timezone=schedule_spec.get("timezone") or timezone.get_current_timezone(),
        )

        PeriodicTask.objects.update_or_create(
            name=task_name,
            defaults={
                "crontab": schedule,
                "task": task_path,
                "args": task_args,
                "enabled": True,
            },
        )
```

```python
class UserSyncSource(...):
    def build_schedule_spec(self):
        schedule_config = self.schedule_config or {}
        mode = schedule_config.get("mode")

        if mode == "disabled":
            return None
        if mode == "daily":
            hour, minute = map(int, schedule_config["time"].split(":"))
            return {
                "kind": "crontab",
                "minute": str(minute),
                "hour": str(hour),
                "day_of_week": "*",
                "day_of_month": "*",
                "month_of_year": "*",
                "timezone": schedule_config.get("timezone") or timezone.get_current_timezone(),
            }
        if mode == "weekly":
            hour, minute = map(int, schedule_config["time"].split(":"))
            weekdays = ",".join(str(day) for day in schedule_config["weekdays"])
            return {
                "kind": "crontab",
                "minute": str(minute),
                "hour": str(hour),
                "day_of_week": weekdays,
                "day_of_month": "*",
                "month_of_year": "*",
                "timezone": schedule_config.get("timezone") or timezone.get_current_timezone(),
            }
        if mode == "interval_hours":
            return {
                "kind": "crontab",
                "minute": "0",
                "hour": f"*/{schedule_config['interval_hours']}",
                "day_of_week": "*",
                "day_of_month": "*",
                "month_of_year": "*",
                "timezone": schedule_config.get("timezone") or timezone.get_current_timezone(),
            }
        raise ValueError(f"Unsupported user sync schedule mode: {mode}")
```

- [ ] **Step 4: Re-run the targeted backend tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_service.py -k "builds_daily_schedule_spec or builds_weekly_schedule_spec or builds_interval_hours_schedule_spec" -v
```

Expected:
- PASS

- [ ] **Step 5: Do not commit; record that commit requires user approval**

Record in implementation notes:
- code for Task 1 is complete
- no git commit performed because user approval is required before any commit

### Task 2: Cut backend validation and API contract over to the new schedule payload

**Files:**
- Modify: `server/apps/system_mgmt/services/capability_contract_service.py`
- Modify: `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`
- Modify: `server/apps/system_mgmt/tests/test_user_sync_service.py`
- Modify: `server/apps/system_mgmt/tests/test_user_sync_source_viewset.py`

**Interfaces:**
- Consumes: `UserSyncSource.build_schedule_spec()` and `PeriodicTaskUtils.create_periodic_task_from_spec(...)`
- Produces:
  - `validate_user_sync_schedule_config(schedule_config, *, field: str) -> None`
  - `UserSyncSourceSerializer._validate_schedule_config(schedule_config) -> None`
  - API contract that accepts only the new `schedule_config`

- [ ] **Step 1: Write failing tests for the new schedule payload and old-payload rejection**

Add tests like:

```python
@pytest.mark.django_db
def test_serializer_accepts_weekly_schedule_config(ready_integration_instance):
    serializer = UserSyncSourceSerializer(data={
        "name": "weekly-source",
        "integration_instance": ready_integration_instance.id,
        "description": "",
        "root_group_name": "Weekly Root",
        "business_config": {"root_department_id": "dept-root"},
        "field_mapping": {},
        "schedule_config": {
            "mode": "weekly",
            "time": "02:00",
            "weekdays": [1, 3, 5],
            "timezone": "Asia/Shanghai",
        },
    })

    assert serializer.is_valid(), serializer.errors


@pytest.mark.django_db
def test_serializer_rejects_legacy_schedule_payload(ready_integration_instance):
    serializer = UserSyncSourceSerializer(data={
        "name": "legacy-source",
        "integration_instance": ready_integration_instance.id,
        "description": "",
        "root_group_name": "Legacy Root",
        "business_config": {"root_department_id": "dept-root"},
        "field_mapping": {},
        "schedule_config": {"enabled": True, "sync_time": "02:00"},
    })

    assert serializer.is_valid() is False
    assert "schedule_config" in serializer.errors
```

- [ ] **Step 2: Run the targeted serializer and API tests to confirm failure**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_service.py -k "schedule" -v
uv run pytest apps/system_mgmt/tests/test_user_sync_source_viewset.py -k "schedule or update_source" -v
```

Expected:
- FAIL on old validator assumptions and/or old payload acceptance.

- [ ] **Step 3: Implement user-sync-specific validation and cut over the serializer**

Implementation target:

```python
def validate_user_sync_schedule_config(schedule_config, *, field: str):
    if not isinstance(schedule_config, dict):
        raise CapabilityContractError(field, "Schedule config must be an object")

    mode = schedule_config.get("mode")
    allowed_modes = {"disabled", "daily", "weekly", "interval_hours"}
    if mode not in allowed_modes:
        raise CapabilityContractError(field, "Schedule mode is invalid")

    if mode == "daily":
        _validate_hhmm(schedule_config.get("time"), field)
    elif mode == "weekly":
        _validate_hhmm(schedule_config.get("time"), field)
        weekdays = schedule_config.get("weekdays")
        if not isinstance(weekdays, list) or not weekdays:
            raise CapabilityContractError(field, "Schedule weekdays must be a non-empty list")
    elif mode == "interval_hours":
        interval = schedule_config.get("interval_hours")
        if interval not in {1, 2, 3, 4, 6, 8, 12}:
            raise CapabilityContractError(field, "Schedule interval_hours must be one of 1,2,3,4,6,8,12")
```

Then wire `validate_user_sync_contract()` to call the new user-sync validator instead of the shared legacy one.

- [ ] **Step 4: Re-run the targeted serializer and API tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_service.py -k "schedule" -v
uv run pytest apps/system_mgmt/tests/test_user_sync_source_viewset.py -k "schedule or update_source" -v
```

Expected:
- PASS
- any old-payload path in user-sync tests must now assert rejection, not compatibility.

- [ ] **Step 5: Do not commit; record that commit requires user approval**

Record in implementation notes:
- Task 2 complete
- no git commit performed

### Task 3: Cut the frontend strategy modal, payload builders, and summary text over to the new contract

**Files:**
- Modify: `web/src/app/system-manager/types/user-sync.ts`
- Modify: `web/src/app/system-manager/utils/userSyncUtils.ts`
- Modify: `web/src/app/system-manager/components/user/user-sync/UserSyncStrategyModal.tsx`
- Modify: `web/src/app/system-manager/(pages)/user/user-sync/page.tsx`
- Modify: `web/src/app/system-manager/utils/userSyncPageUtils.ts`
- Modify: `web/src/app/system-manager/locales/zh.json`
- Modify: `web/src/app/system-manager/locales/en.json`
- Modify: `web/src/stories/system-manager-user-sync-source-list.stories.tsx`

**Interfaces:**
- Consumes: new backend `schedule_config` contract from Task 2
- Produces:
  - `UserSyncSourceStrategyFormValues` with `schedule_mode`, `time`, `weekdays`, `interval_hours`
  - `buildSchedulePayload(values)` returning the new backend payload
  - `getScheduleSummary(scheduleConfig, enabled, t)` for card rendering

- [ ] **Step 1: Write a failing TypeScript-level contract sketch in the touched files**

Target types:

```ts
export type UserSyncScheduleMode = 'disabled' | 'daily' | 'weekly' | 'interval_hours';

export interface ScheduleConfig {
  mode: UserSyncScheduleMode;
  time?: string;
  weekdays?: number[];
  interval_hours?: 1 | 2 | 3 | 4 | 6 | 8 | 12;
  timezone?: string;
}

export interface UserSyncSourceStrategyFormValues {
  enabled: boolean;
  schedule_mode: UserSyncScheduleMode;
  time?: string;
  weekdays?: number[];
  interval_hours?: 1 | 2 | 3 | 4 | 6 | 8 | 12;
}
```

- [ ] **Step 2: Run a focused frontend sanity check to surface breakage**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/components/user/user-sync/UserSyncStrategyModal.tsx src/app/system-manager/utils/userSyncUtils.ts src/app/system-manager/(pages)/user/user-sync/page.tsx src/app/system-manager/utils/userSyncPageUtils.ts src/app/system-manager/types/user-sync.ts
pnpm exec tsc -p tsconfig.lint.json --noEmit
```

Expected:
- FAIL due to old `schedule_enabled` / `sync_time` assumptions.

- [ ] **Step 3: Implement the new frontend contract and modal behavior**

Implementation target:

```ts
export function buildSchedulePayload(values: UserSyncSourceStrategyFormValues): ScheduleConfig {
  switch (values.schedule_mode) {
    case 'disabled':
      return { mode: 'disabled', timezone: 'Asia/Shanghai' };
    case 'daily':
      return { mode: 'daily', time: values.time!, timezone: 'Asia/Shanghai' };
    case 'weekly':
      return {
        mode: 'weekly',
        time: values.time!,
        weekdays: values.weekdays!,
        timezone: 'Asia/Shanghai',
      };
    case 'interval_hours':
      return {
        mode: 'interval_hours',
        interval_hours: values.interval_hours!,
        timezone: 'Asia/Shanghai',
      };
  }
}
```

```tsx
<Form.Item name="schedule_mode" label={t('system.user.userSyncPage.autoSync')}>
  <Select
    options={[
      { value: 'disabled', label: t('system.user.userSyncPage.scheduleModeDisabled') },
      { value: 'daily', label: t('system.user.userSyncPage.scheduleModeDaily') },
      { value: 'weekly', label: t('system.user.userSyncPage.scheduleModeWeekly') },
      { value: 'interval_hours', label: t('system.user.userSyncPage.scheduleModeIntervalHours') },
    ]}
  />
</Form.Item>
```

```ts
export function getScheduleSummary(scheduleConfig: UserSyncSource['schedule_config'], enabled: boolean): string {
  if (!enabled) return '已停用';
  if (!scheduleConfig || scheduleConfig.mode === 'disabled') return '手动';
  if (scheduleConfig.mode === 'daily') return `每天 ${scheduleConfig.time}`;
  if (scheduleConfig.mode === 'weekly') return `每周${(scheduleConfig.weekdays || []).join('、')} ${scheduleConfig.time}`;
  return `每 ${scheduleConfig.interval_hours} 小时（00:00 对齐）`;
}
```

- [ ] **Step 4: Re-run the focused frontend sanity check**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/components/user/user-sync/UserSyncStrategyModal.tsx src/app/system-manager/utils/userSyncUtils.ts src/app/system-manager/(pages)/user/user-sync/page.tsx src/app/system-manager/utils/userSyncPageUtils.ts src/app/system-manager/types/user-sync.ts src/stories/system-manager-user-sync-source-list.stories.tsx
pnpm exec tsc -p tsconfig.lint.json --noEmit
```

Expected:
- touched frontend files pass lint
- type-check is clean for touched paths, or any unrelated baseline issue is recorded explicitly.

- [ ] **Step 5: Do not commit; record that commit requires user approval**

Record in implementation notes:
- Task 3 complete
- no git commit performed

### Task 4: Final verification and review

**Files:**
- Review: `docs/superpowers/specs/2026-07-01-system-manager-user-sync-schedule-strategy-design.md`
- Test: touched frontend user-sync files
- Test: `server/apps/system_mgmt/tests/test_user_sync_service.py`
- Test: `server/apps/system_mgmt/tests/test_user_sync_source_viewset.py`

**Interfaces:**
- Consumes: all outputs from Tasks 1-3
- Produces: verified end-state implementation matching the approved design

- [ ] **Step 1: Run the focused backend verification suite**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_service.py -k "schedule or periodic_task" -v
uv run pytest apps/system_mgmt/tests/test_user_sync_source_viewset.py -k "schedule or update_source or preview_rejects_invalid_payload" -v
```

Expected:
- PASS
- old legacy schedule payloads are rejected for user-sync endpoints and serializer tests

- [ ] **Step 2: Run the focused frontend verification suite**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/components/user/user-sync/UserSyncStrategyModal.tsx src/app/system-manager/utils/userSyncUtils.ts src/app/system-manager/(pages)/user/user-sync/page.tsx src/app/system-manager/utils/userSyncPageUtils.ts src/app/system-manager/types/user-sync.ts src/stories/system-manager-user-sync-source-list.stories.tsx
pnpm exec tsc -p tsconfig.lint.json --noEmit
```

Expected:
- touched frontend files remain clean
- any unrelated baseline issue is recorded explicitly instead of being misattributed

- [ ] **Step 3: Manually verify the user-sync end-state behaviors**

Checklist:
- strategy modal clearly separates `同步源状态` and `自动同步`
- `daily` shows only execution time
- `weekly` shows weekdays plus execution time
- `interval_hours` shows only interval selector and states `00:00` alignment
- card summary shows `已停用` / `手动` / `每天 HH:mm` / `每周...` / `每 N 小时（00:00 对齐）`
- disabled sources cannot trigger `立即同步`
- enabled sources with `mode=disabled` still allow manual sync and do not create a periodic task

- [ ] **Step 4: Review implementation against the spec before handoff**

Checklist:
- no legacy `{ enabled, sync_time }` compatibility path remains inside user-sync
- old daily-only helper remains intact for non-user-sync callers
- new helper is a static method on `PeriodicTaskUtils`
- `schedule_config -> schedule_spec` stays in user-sync business code, not inside the generic helper
- `interval_hours` is aligned to `00:00` and does not accept arbitrary values
- no git commit was performed without explicit user approval

## Self-Review

- Spec coverage: backend schedule helper, user-sync validator split, frontend modal/payload/summary cutover, and final verification are all covered by Tasks 1-4.
- Placeholder scan: no `TODO` / `TBD` placeholders were intentionally left in the plan; each task has explicit commands and expected outcomes.
- Type consistency: the plan consistently uses `schedule_mode`, `time`, `weekdays`, `interval_hours`, `build_schedule_spec()`, and `create_periodic_task_from_spec(...)`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-01-system-manager-user-sync-schedule-cutover.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
