# Historical Superpowers change: 2026-06-24-system-manager-user-auth-governance-phase1

Status: cancelled

## Migration Context

该文档保留旧 Superpowers 规格/计划的完整内容，仅用于历史追溯，不代表当前工作流。

## plans: 2026-06-24-system-manager-user-auth-governance-phase1.md

﻿# System Manager User/Auth Governance Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the phase-1 governance fixes for system-manager login auth and user sync so builtin login objects are treated as read-only display mappings with create-only initialization, disabled sync sources cannot execute, user-sync conflicts become partial runs, root-group names are reserved safely, and delete semantics directly remove the root subtree and users with explicit frontend confirmation.

**Architecture:** Keep the existing `IntegrationInstance -> LoginAuthBinding / UserSyncSource` model split, reclassify builtin login objects as read-only display mappings, and prefer enforcing lifecycle rules through existing serializers, services, payloads, and viewsets rather than new models or schema changes. Preserve current signin/runtime contracts where possible, and treat phase 1 as backend-first delivery with only the minimal frontend changes required for hidden builtin instances, read-only builtin login-auth rows, and non-lying user-sync states.

**Tech Stack:** Django 4.2 ORM and management commands, Celery task execution, pytest, Next.js 16 + React 19 + TypeScript system-manager pages

## Execution Constraints

- The primary objective is to complete all phase-1 governance goals end-to-end; do not silently defer high-risk lifecycle semantics to “a later follow-up.”
- Perform full verification and code review after all planned tasks are complete; use only lightweight, directly relevant validation between tasks unless risk justifies more.
- Do not force through ambiguous semantics. If reservation handling or worker audit behavior becomes unclear against real repo data, stop and align with the user.
- Create and use a fresh git worktree before implementation. Do not implement directly in the current workspace.
- Follow existing repository code style and patterns; keep changes tightly scoped to system-manager login auth and user sync governance.
- Avoid unrelated refactors, UI redesign, builtin-login extra hints, or speculative phase-2 tooling beyond the minimum governance exit required by the spec.
- Treat task completion as behaviorally meeting the planned end-state, not merely landing partial code or passing isolated tests.
- Preserve current integration-center `available_instances` semantics; this plan must not re-open team-filtering or builtin-provider visibility design.
- Execute in a mostly mainline sequence because the tasks share model and lifecycle semantics; avoid parallel implementation that would create overlapping writes in `system_mgmt`.
- After implementation and verification are complete, do not stage or commit. Stop and notify the user first, summarize the worktree path, changed files, and validation results, and wait for approval before any `git add` / `git commit`.

**Delivery scope note:** This plan intentionally implements only spec phase 1 from [2026-06-24-system-manager-user-auth-governance-design.md](D:/Work/bk-lite/bk-lite/docs/superpowers/specs/2026-06-24-system-manager-user-auth-governance-design.md). Phase 1 explicitly includes the minimum builtin-login UI handling: hide the builtin integration instance and render the builtin login-auth row as read-only enabled. Broader phase 2 UX/polish/tooling remains out of scope except for the minimum admin-facing governance path required to avoid trapping dirty data.

---

## Workspace Setup

- Before Task 1, create a new git worktree for this plan and perform all edits, tests, and review inside that worktree.
- Keep the current workspace untouched except for the already-written spec/plan documents.
- Use the worktree path consistently for all commands in this plan.

Suggested command pattern:

```bash
git worktree add ..\\bk-lite-user-auth-governance-phase1 <branch-or-new-branch>
cd ..\\bk-lite-user-auth-governance-phase1
```

If the current branch state or repository layout makes a fresh worktree unsafe, stop and align with the user before proceeding.

---

## File Structure

### Existing files to modify

- `server/apps/system_mgmt/management/commands/init_login_settings.py`
  Keep builtin initialization create-only; do not add drift self-heal behavior.
- `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`
  Enforce reservation-aware create/update validation and keep root-group mutability rules explicit.
- `server/apps/system_mgmt/services/user_sync_service.py`
  Centralize sync execution semantics: partial conflict handling, disable/delete race handling, direct delete behavior, reservation maintenance, and re-enable behavior.
- `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`
  Reject invalid `sync_now` and execute the direct delete behavior for phase 1.
- `server/apps/system_mgmt/tests/test_builtin_platform_login_auth.py`
  Cover builtin create-only initialization semantics.
- `server/apps/system_mgmt/tests/test_user_sync_service.py`
  Replace current “fail whole sync” assertions with partial semantics and add reservation/delete/race tests.
- `server/apps/system_mgmt/tests/`
  Add viewset-focused tests if existing files become too overloaded.
- `web/src/app/system-manager/(pages)/user/user-sync/page.tsx`
  Disable lying “Sync Now” behavior and use the direct-delete confirmation flow.
- `web/src/app/system-manager/(pages)/user/login-auth/page.tsx`
  Render builtin login-auth row as read-only enabled and keep its action controls non-interactive.
- `web/src/app/system-manager/api/user-sync/index.ts`
  Keep only the delete API used by the direct-delete confirmation flow.
- `web/src/app/system-manager/components/user/user-sync/UserSyncRecordsDrawer.tsx`
  Render new summary/count fields only if backend payload changes require basic visibility to avoid opaque partial runs.
- `web/src/app/system-manager/types/user-sync.ts`
  Extend run/source typing if backend fields change.
- `web/src/app/system-manager/locales/zh.json`
  Minimal strings for disabled-sync rejection / direct-delete confirmation / partial summary.
- `web/src/app/system-manager/locales/en.json`
  Minimal strings for the same cases.

### New files likely to create

- `server/apps/system_mgmt/tests/test_user_sync_source_viewset.py`
  Focused API tests for `sync_now` and direct delete behavior if existing service tests become too indirect.

### Reference files to read during implementation

- `docs/superpowers/specs/2026-06-24-system-manager-user-auth-governance-design.md`
- `docs/superpowers/specs/2026-06-23-integration-center-design.md`
- `docs/superpowers/plans/2026-06-18-signin-validation-cutover.md`
- `server/apps/system_mgmt/viewset/integration_instance_viewset.py`
- `server/apps/system_mgmt/serializers/login_auth_binding_serializer.py`

---

### Task 1: Keep builtin login initialization create-only and lock down display semantics

**Files:**
- Modify: `server/apps/system_mgmt/management/commands/init_login_settings.py`
- Modify: `web/src/app/system-manager/(pages)/user/login-auth/page.tsx`
- Test: `server/apps/system_mgmt/tests/test_builtin_platform_login_auth.py`

- [ ] **Step 1: Write tests for builtin create-only initialization and read-only display semantics**

Add tests covering:

```python
def test_init_login_settings_creates_builtin_objects_when_missing():
    IntegrationInstance.objects.filter(instance_id="bk_lite_builtin").delete()
    LoginAuthBinding.objects.filter(instance__instance_id="bk_lite_builtin").delete()

    call_command("init_login_settings")

    assert IntegrationInstance.objects.filter(instance_id="bk_lite_builtin").exists()
    assert LoginAuthBinding.objects.filter(instance__instance_id="bk_lite_builtin").exists()
```

```python
def test_init_login_settings_does_not_self_heal_drifted_builtin_fields():
    instance, binding = create_builtin_platform_login_auth()
    instance.enabled = False
    instance.save(update_fields=["enabled"])
    binding.enabled = False
    binding.save(update_fields=["enabled"])

    call_command("init_login_settings")

    instance.refresh_from_db()
    binding.refresh_from_db()
    assert instance.enabled is False
    assert binding.enabled is False
```

- [ ] **Step 2: Run the targeted builtin login test file and verify the intended contract**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_builtin_platform_login_auth.py -k "builtin" -v
```

Expected:
- PASS for create-only behavior if already implemented
- otherwise FAIL only where missing-create semantics are incomplete

- [ ] **Step 3: Adjust `init_login_settings.py` only if needed to preserve create-only semantics**

Implementation requirements:
- keep `get_or_create` for missing builtin objects
- do not add drift normalization or field backfill for existing builtin instance/binding rows
- keep signin/runtime contracts unchanged

- [ ] **Step 4: Implement builtin display semantics in system-manager frontend**

Implementation requirements:
- hide the builtin integration instance in the integration instance list
- keep the builtin login-auth record visible in the login-auth list when it exists
- render that row as read-only: edit/delete/enable-disable controls all non-interactive
- show the builtin row as enabled by default without extra explanatory tooltip or message
- if builtin initialization resources are absent, do not add frontend fallback rendering

- [ ] **Step 5: Re-run focused builtin login backend/frontend validation**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_builtin_platform_login_auth.py -v
cd ..\web
pnpm exec eslint src/app/system-manager/\(pages\)/user/login-auth/page.tsx
```

Expected:
- PASS

- [ ] **Step 6: Commit**

```bash
Do not commit yet. After task-local validation, record touched files and continue to the next task.
```
### Task 2: Enforce root-group reservation semantics on existing models

**Files:**
- Modify: `server/apps/system_mgmt/serializers/user_sync_source_serializer.py`
- Modify: `server/apps/system_mgmt/services/user_sync_service.py`
- Test: `server/apps/system_mgmt/tests/test_user_sync_service.py`

- [ ] **Step 1: Write failing tests for create-time root-group validation and historical conflict compatibility**

Add tests covering:

```python
def test_create_source_rejects_existing_root_group_name_in_active_source():
    UserSyncSource.objects.create(..., root_group_name="Root A")

    serializer = UserSyncSourceSerializer(data={... "root_group_name": "Root A"})
    assert serializer.is_valid() is False
    assert "root_group_name" in serializer.errors
```

```python
def test_historical_duplicate_root_group_sources_are_reported_but_not_auto_repaired():
    UserSyncSource.objects.create(..., root_group_name="Dup Root")
    UserSyncSource.objects.create(..., root_group_name="Dup Root")

    conflicts = detect_root_group_name_conflicts()
    assert "Dup Root" in conflicts
```

- [ ] **Step 2: Run only the new root-group validation tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_service.py -k "root_group_name or historical_duplicate" -v
```

Expected:
- FAIL because create-time root-group validation and historical-conflict detection are incomplete

- [ ] **Step 3: Implement create-time root-group validation on existing models**

Implementation requirements:
- use existing `UserSyncSource.root_group_name` as the source of truth
- reject reuse of the same root-group name by another active source at create time
- keep `root_group_name` immutable after creation
- add a small helper to detect historical duplicate declarations without rewriting existing rows
- do not add a new reservation model or migration unless implementation proves existing models cannot safely express the rule

- [ ] **Step 4: Re-run root-group validation tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_service.py -k "root_group_name or historical_duplicate" -v
```

Expected:
- PASS

- [ ] **Step 5: Commit**

```bash
Do not commit yet. After task-local validation, record touched files and continue to the next task.
```

### Task 3: Convert user-sync conflict handling from full failure to partial runs

**Files:**
- Modify: `server/apps/system_mgmt/services/user_sync_service.py`
- Test: `server/apps/system_mgmt/tests/test_user_sync_service.py`

- [ ] **Step 1: Write failing tests for partial conflict behavior and auto re-enable**

Add tests covering:

```python
def test_execute_user_sync_marks_partial_when_one_user_conflicts_but_others_sync():
    # source_a owns shared_user; source_b sync payload contains shared_user + new_user
    result = execute_user_sync(source_b.id)
    assert result["result"] is True
    run = UserSyncRun.objects.get(source=source_b)
    assert run.status == UserSyncRunStatusChoices.PARTIAL
    assert run.synced_user_count == 1
    assert run.payload["conflict_usernames"] == ["shared_user"]
```

```python
def test_execute_user_sync_marks_partial_when_user_groups_point_to_another_source():
    source_a = UserSyncSource.objects.create(...)
    source_b = UserSyncSource.objects.create(...)
    foreign_root = Group.objects.create(name="Root A", parent_id=0, sync_source=source_a, external_id="user-sync:a:0")
    foreign_dept = Group.objects.create(name="Dept A", parent_id=foreign_root.id, sync_source=source_a, external_id="user-sync:a:dept-a")
    User.objects.create(username="shared_user", domain="domain.com", sync_source=None, group_list=[foreign_dept.id], disabled=False)

    result = execute_user_sync(source_b.id)
    assert result["result"] is True
    run = UserSyncRun.objects.get(source=source_b)
    assert run.status == UserSyncRunStatusChoices.PARTIAL
    assert run.payload["conflict_usernames"] == ["shared_user"]
```

```python
def test_reappearing_disabled_user_is_reenabled():
    user = User.objects.create(username="alice", disabled=True, group_list=[], sync_source=source)
    result = execute_user_sync(source.id)
    user.refresh_from_db()
    assert user.disabled is False
```

- [ ] **Step 2: Run the targeted conflict tests and verify they fail under current full-failure behavior**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_service.py -k "partial or reenabled" -v
```

Expected:
- FAIL because conflicts currently abort the whole sync

- [ ] **Step 3: Implement partial conflict collection in `user_sync_service.py`**

Implementation requirements:
- do not raise immediately on per-user ownership conflict
- collect conflict usernames and continue
- treat direct `user.sync_source` conflicts and indirect “user currently belongs to groups owned by another source” conflicts as the same partial-conflict class
- only fail the whole run for non-recoverable provider/runtime/data errors
- keep transaction boundaries coherent so successful rows persist
- extend run payload/summary to expose conflict counts and names

Suggested control flow:

```python
conflicts = []
for item in normalized_users:
    try:
        _ensure_user_sync_source_match(...)
    except ValueError:
        conflicts.append(item["username"])
        continue
    ...

run_status = UserSyncRunStatusChoices.PARTIAL if conflicts else UserSyncRunStatusChoices.SUCCESS
```

- [ ] **Step 4: Extend run payload/count fields only if the existing payload is insufficient**

Requirements:
- prefer storing conflict counts and usernames inside `payload`
- use existing run `payload` / `summary` first; do not add model fields unless existing structures prove insufficient

- [ ] **Step 5: Re-run the focused user-sync service tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_service.py -k "partial or reenabled or conflicting_user" -v
```

Expected:
- PASS

- [ ] **Step 6: Commit**

```bash
Do not commit yet. After task-local validation, record touched files and continue to the next task.
```

### Task 4: Enforce non-executable disabled sources

**Files:**
- Modify: `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`
- Modify: `server/apps/system_mgmt/services/user_sync_service.py`
- Test: `server/apps/system_mgmt/tests/test_user_sync_source_viewset.py`
- Test: `server/apps/system_mgmt/tests/test_user_sync_service.py`

- [ ] **Step 1: Add failing API and worker-race tests**

Add tests covering:

```python
def test_sync_now_rejects_disabled_source(api_client, source):
    source.enabled = False
    source.save(update_fields=["enabled"])
    response = api_client.post(f"/api/v1/system_mgmt/user_sync_source/{source.id}/sync_now/")
    assert response.status_code == 400
```

```python
def test_scheduled_execution_for_disabled_source_creates_failed_run():
    source.enabled = False
    source.save(update_fields=["enabled"])
    result = execute_user_sync(source.id, trigger_mode=UserSyncTriggerModeChoices.SCHEDULE)
    run = UserSyncRun.objects.get(source=source)
    assert run.trigger_mode == UserSyncTriggerModeChoices.SCHEDULE
    assert run.status == UserSyncRunStatusChoices.FAILED
```

```python
def test_queued_sync_for_disabled_source_creates_failed_run():
    source.enabled = False
    source.save(update_fields=["enabled"])
    result = execute_user_sync(source.id)
    run = UserSyncRun.objects.get(source=source)
    assert run.status == UserSyncRunStatusChoices.FAILED
    assert "disabled" in run.summary.lower()
```

```python
```

- [ ] **Step 2: Run the targeted disable/race tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_source_viewset.py -k "sync_now_rejects_disabled" -v
uv run pytest apps/system_mgmt/tests/test_user_sync_service.py -k "disabled_source or scheduled_execution" -v
```

Expected:
- FAIL because `sync_now` currently enqueues disabled sources and worker failure semantics are underspecified

- [ ] **Step 3: Reject disabled sources at the API edge**

Implementation requirements:
- in `sync_now`, check `source.enabled`
- return a stable 400 response with a user-facing message
- do not enqueue Celery work for disabled sources

- [ ] **Step 4: Make worker-side disable/delete races auditable**

Implementation requirements:
- if `execute_user_sync` sees a disabled source after a task was already triggered, do not silently drop the work
- create a failed run when source identity is still recoverable
- do not expand phase 1 into extra deleted-source audit handling or `tasks.py` changes
- keep behavior deterministic and testable

- [ ] **Step 5: Re-run the disable/race tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_source_viewset.py -v
uv run pytest apps/system_mgmt/tests/test_user_sync_service.py -k "disabled_source or sync_now or scheduled_execution" -v
```

Expected:
- PASS

- [ ] **Step 6: Commit**

```bash
Do not commit yet. After task-local validation, record touched files and continue to the next task.
```

### Task 5: Converge destructive delete into direct subtree deletion with explicit confirmation

**Files:**
- Modify: `server/apps/system_mgmt/viewset/user_sync_source_viewset.py`
- Modify: `server/apps/system_mgmt/services/user_sync_service.py`
- Test: `server/apps/system_mgmt/tests/test_user_sync_source_viewset.py`
- Modify: `web/src/app/system-manager/api/user-sync/index.ts`
- Modify: `web/src/app/system-manager/(pages)/user/user-sync/page.tsx`
- Modify: `web/src/app/system-manager/locales/zh.json`
- Modify: `web/src/app/system-manager/locales/en.json`

- [ ] **Step 1: Write failing delete tests**

Add backend tests covering direct delete behavior for:

- deleting the root subtree and affected users when the source has landed data
- deleting the source even when no root group exists

- [ ] **Step 2: Run only the new delete tests**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_source_viewset.py -k "destroy_deletes" -v
```

- [ ] **Step 3: Implement direct delete in backend**

Implementation requirements:
- remove cleanup action and cleanup gating
- destroy should delete the root organization, all descendant organizations, and users under that tree
- source-linked users should also be deleted
- keep delete behavior deterministic and scoped to the current source

- [ ] **Step 4: Wire the minimum frontend confirmation flow**

Implementation requirements:
- keep the existing delete entry
- use a danger confirm modal
- clearly state that deleting the source also deletes the root organization, all child organizations, and users under it
- do not add extra explanatory semantics

- [ ] **Step 5: Re-run backend delete tests plus lightweight frontend lint checks**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_user_sync_source_viewset.py -v
cd ..\web
pnpm exec eslint src/app/system-manager/\(pages\)/user/user-sync/page.tsx src/app/system-manager/api/user-sync/index.ts
```

Expected:
- backend delete tests PASS
- touched frontend files have no new lint errors

- [ ] **Step 6: Commit**

```bash
Do not commit yet. After task-local validation, record touched files and continue to final verification.
```

### Task 6: Final verification and review

**Files:**
- Review: `docs/superpowers/specs/2026-06-24-system-manager-user-auth-governance-design.md`
- Test: touched `system_mgmt` backend files
- Test: touched system-manager frontend files

- [ ] **Step 1: Run the focused backend governance suite**

Run:

```bash
cd server
uv run pytest apps/system_mgmt/tests/test_builtin_platform_login_auth.py apps/system_mgmt/tests/test_user_sync_service.py apps/system_mgmt/tests/test_user_sync_source_viewset.py -v
```

Expected:
- PASS
- if unrelated baseline failures exist, record them explicitly and distinguish them from introduced regressions

- [ ] **Step 2: Run the focused frontend validation for touched system-manager files**

Run:

```bash
cd web
pnpm exec eslint src/app/system-manager/\(pages\)/user/user-sync/page.tsx src/app/system-manager/api/user-sync/index.ts src/app/system-manager/components/user/user-sync/UserSyncRecordsDrawer.tsx src/app/system-manager/types/user-sync.ts
pnpm exec tsc -p tsconfig.lint.json --noEmit
```

Expected:
- touched frontend files remain clean
- any unrelated baseline type issue is called out clearly instead of being treated as introduced by this plan

- [ ] **Step 3: Manually verify the end-state governance behaviors**

Checklist:
- builtin login objects are created when missing but are not silently self-healed when drifted
- builtin login remains excluded from login-auth available instances
- builtin login is hidden in the integration instance list
- builtin login-auth row is read-only and visually enabled without interactive controls
- disabled sync source cannot be manually synced
- queued disabled/deleted sync tasks do not disappear silently
- scheduled sync for a disabled source is blocked with the same non-executable semantics
- conflicting users produce `partial` runs while non-conflicting users still sync
- users whose current groups belong to another source also produce `partial` runs instead of aborting the whole job
- users removed from source results become disabled rather than deleted
- duplicate root-group names are blocked for new sources
- historical duplicate root-group sources are surfaced as conflicted rather than auto-mutated
- delete directly removes the root subtree and affected users
- frontend confirmation accurately describes the deletion impact

- [ ] **Step 4: Review implementation against the spec before handoff**

Checklist:
- no strong-binding login refactor was introduced
- builtin login objects remained display mappings rather than self-healing governance objects
- integration-center `available_instances` semantics stayed intact
- user-sync phase 1 delivers direct delete semantics with explicit confirmation
- delete semantics are explicit in code and tests
- partial sync behavior is visible in run payload/summary
- no phase-2 UI redesign crept into phase-1 delivery

- [ ] **Step 5: Notify the user before any commit**

Checklist:
- summarize the worktree path used for implementation
- list modified files
- summarize pytest / lint / type-check results
- explicitly state that no commit has been created
- wait for user approval before any staging or commit action
