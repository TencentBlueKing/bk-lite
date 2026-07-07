# Monitor Policy Condition Permission Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收口监控策略和监控条件的对象级权限，确保跨组织裸 ID 读写删和组织混入写入都被服务端拦截。

**Architecture:** 在 `MonitorPolicyViewSet` 与 `MonitorConditionViewSet` 内采用“统一 queryset + 写入围栏”。读操作使用 View 范围，写操作使用 Operate 范围；创建和组织关联更新前校验目标组织；策略批量模板创建前校验资产授权并保持事务全有或全无。

**Tech Stack:** Python 3.12, Django 4.2, Django REST Framework, pytest, BK-Lite monitor permission helpers.

---

## File Structure

- Modify: `server/apps/monitor/views/monitor_policy.py`
  - 增加 actor context / 授权组织 / 可读可写 queryset / 组织校验 helper。
  - 让 `get_queryset()` 成为策略对象级权限统一入口。
  - 在 create/update/partial_update/bulk_create_from_templates/get_bulk_policy_assets 进入写入前增加围栏。
- Modify: `server/apps/monitor/views/monitor_condition.py`
  - 增加同类 helper。
  - 让 `get_queryset()` 成为条件对象级权限统一入口。
  - 在 create/update/partial_update/destroy 进入写入前增加围栏。
- Create: `server/apps/monitor/tests/test_monitor_permission_guards.py`
  - 集中覆盖策略与条件的对象级权限、组织混入、批量资产越权、副作用不发生。
- Keep unchanged:
  - `server/apps/monitor/serializers/monitor_policy.py`
  - `server/apps/monitor/serializers/monitor_condition.py`
  - 告警扫描任务、节点管理和 NATS 代码。

## Task 1: Add Failing Policy Permission Guard Tests

**Files:**
- Create: `server/apps/monitor/tests/test_monitor_permission_guards.py`
- Read: `server/apps/monitor/views/monitor_policy.py`
- Read: `server/apps/monitor/tests/test_monitor_policy_view_helpers.py`

- [ ] **Step 1: Create policy permission test file**

Create `server/apps/monitor/tests/test_monitor_permission_guards.py` with the following content:

```python
from types import SimpleNamespace

import pytest
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from apps.monitor.models import MonitorAlert
from apps.monitor.models.monitor_object import (
    MonitorInstance,
    MonitorInstanceOrganization,
    MonitorObject,
)
from apps.monitor.models.monitor_policy import MonitorPolicy, PolicyOrganization
from apps.monitor.views.monitor_policy import MonitorPolicyViewSet

pytestmark = pytest.mark.django_db


def _user(username="alice", *, is_superuser=False, groups=None):
    return SimpleNamespace(
        username=username,
        domain="domain.com",
        is_superuser=is_superuser,
        locale="zh-Hans",
        group_list=groups or [{"id": 1, "name": "Team 1"}],
        is_authenticated=True,
    )


def _request(user=None, *, current_team=1, include_children="0"):
    req = SimpleNamespace(
        user=user or _user(),
        COOKIES={"current_team": str(current_team), "include_children": include_children},
        query_params={},
        GET={},
        data={},
    )
    return req


def _monitor_object(name="PermissionGuardObj"):
    return MonitorObject.objects.create(name=name, level="base")


def _policy(obj, *, name="policy", org=1):
    policy = MonitorPolicy.objects.create(
        monitor_object=obj,
        name=name,
        algorithm="max",
        query_condition={"type": "pmq", "query": "up"},
        source={},
        group_by=[],
        schedule={"type": "min", "value": 5},
    )
    PolicyOrganization.objects.create(policy=policy, organization=org)
    return policy


def _patch_policy_permission(mocker, *, teams=None, instances=None):
    mocker.patch(
        "apps.monitor.views.monitor_policy.get_permission_rules",
        return_value={"team": teams or [], "instance": instances or []},
    )


class TestMonitorPolicyObjectPermission:
    def test_read_queryset_returns_only_authorized_team_policies(self, mocker):
        obj = _monitor_object("PolicyReadObj")
        allowed = _policy(obj, name="allowed", org=1)
        _policy(obj, name="blocked", org=2)
        _patch_policy_permission(mocker, teams=[1])

        view = MonitorPolicyViewSet()
        view.request = _request(current_team=1)
        view.action = "retrieve"

        ids = set(view.get_queryset().values_list("id", flat=True))
        assert allowed.id in ids
        assert MonitorPolicy.objects.get(name="blocked").id not in ids

    def test_write_queryset_requires_operate_instance_permission(self, mocker):
        obj = _monitor_object("PolicyOperateObj")
        allowed = _policy(obj, name="allowed-operate", org=9)
        blocked = _policy(obj, name="blocked-view", org=9)
        _patch_policy_permission(
            mocker,
            teams=[],
            instances=[
                {"id": allowed.id, "permission": ["View", "Operate"]},
                {"id": blocked.id, "permission": ["View"]},
            ],
        )

        view = MonitorPolicyViewSet()
        view.request = _request(current_team=1)
        view.action = "update"

        ids = set(view.get_queryset().values_list("id", flat=True))
        assert allowed.id in ids
        assert blocked.id not in ids

    def test_rejects_unauthorized_organizations_before_sync(self, mocker):
        _patch_policy_permission(mocker, teams=[1])
        view = MonitorPolicyViewSet()
        view.request = _request(current_team=1)

        with pytest.raises(Exception):
            view._ensure_target_organizations([1, 2])

    def test_destroy_queryset_blocks_side_effect_targets(self, mocker):
        obj = _monitor_object("PolicyDestroyObj")
        blocked = _policy(obj, name="blocked-destroy", org=2)
        schedule = CrontabSchedule.objects.create(minute="*/5", hour="*", day_of_week="*", day_of_month="*", month_of_year="*")
        PeriodicTask.objects.create(
            name=f"scan_policy_task_{blocked.id}",
            task="apps.monitor.tasks.monitor_policy.scan_policy_task",
            args=f"[{blocked.id}]",
            crontab=schedule,
        )
        MonitorAlert.objects.create(policy_id=blocked.id, monitor_instance_id="h1", status="new")
        _patch_policy_permission(mocker, teams=[1])

        view = MonitorPolicyViewSet()
        view.request = _request(current_team=1)
        view.action = "destroy"

        assert not view.get_queryset().filter(id=blocked.id).exists()
        assert PeriodicTask.objects.filter(name=f"scan_policy_task_{blocked.id}").exists()
        assert PolicyOrganization.objects.filter(policy_id=blocked.id, organization=2).exists()


class TestMonitorPolicyBulkAssetPermission:
    def test_get_bulk_policy_assets_rejects_cross_team_asset(self, mocker):
        obj = _monitor_object("PolicyBulkObj")
        inst = MonitorInstance.objects.create(id="('h1',)", name="h1", monitor_object=obj)
        MonitorInstanceOrganization.objects.create(monitor_instance=inst, organization=2)
        _patch_policy_permission(mocker, teams=[1])

        view = MonitorPolicyViewSet()
        view.request = _request(current_team=1)
        view.action = "bulk_create_from_templates"

        with pytest.raises(Exception):
            view.get_bulk_policy_assets(obj.id, [inst.id])
```

- [ ] **Step 2: Run the policy permission tests and verify they fail**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_monitor_permission_guards.py -q
```

Expected: FAIL because `MonitorPolicyViewSet.get_queryset()` does not scope by action yet, and helper methods such as `_ensure_target_organizations()` do not exist.

- [ ] **Step 3: Commit the failing tests**

```bash
git add server/apps/monitor/tests/test_monitor_permission_guards.py
git commit -m "test(monitor): 覆盖策略对象级权限围栏"
```

## Task 2: Implement MonitorPolicyViewSet Permission Guards

**Files:**
- Modify: `server/apps/monitor/views/monitor_policy.py`
- Test: `server/apps/monitor/tests/test_monitor_permission_guards.py`
- Test: `server/apps/monitor/tests/test_monitor_policy_view_helpers.py`

- [ ] **Step 1: Add local permission helpers to monitor_policy.py**

Modify imports near the top:

```python
from apps.core.exceptions.base_app_exception import BaseAppException, UnauthorizedException
from apps.core.utils.user_group import normalize_user_group_ids
from apps.monitor.services.node_mgmt import InstanceConfigService
```

Add these helpers above `class MonitorPolicyViewSet`:

```python
def _build_actor_context(request):
    current_team = get_current_team(request)
    if current_team in (None, ""):
        raise BaseAppException("缺少 current_team 参数")
    try:
        current_team = int(current_team)
    except (TypeError, ValueError):
        raise BaseAppException("current_team 参数非法")
    return {
        "username": request.user.username,
        "domain": request.user.domain,
        "current_team": current_team,
        "include_children": request.COOKIES.get("include_children", "0") == "1",
        "is_superuser": request.user.is_superuser,
        "group_list": normalize_user_group_ids(getattr(request.user, "group_list", [])),
    }


def _normalize_orgs(organizations):
    try:
        return {int(org) for org in (organizations or []) if org not in (None, "")}
    except (TypeError, ValueError):
        raise BaseAppException("组织参数非法")


def _operate_only_permission(permission):
    return {
        **permission,
        "team": permission.get("team", []),
        "instance": [
            item
            for item in permission.get("instance", [])
            if isinstance(item, dict) and "Operate" in item.get("permission", [])
        ],
    }
```

- [ ] **Step 2: Add ViewSet methods for policy queryset and org guard**

Inside `MonitorPolicyViewSet`, add these methods before `list()`:

```python
    def _get_permission(self, monitor_object_id=None):
        include_children = self.request.COOKIES.get("include_children", "0") == "1"
        module = PermissionConstants.POLICY_MODULE
        if monitor_object_id not in (None, ""):
            module = f"{PermissionConstants.POLICY_MODULE}.{monitor_object_id}"
        return get_permission_rules(
            self.request.user,
            get_current_team(self.request),
            "monitor",
            module,
            include_children=include_children,
        )

    def _scope_queryset(self, queryset, permission):
        return permission_filter(
            queryset.model,
            permission,
            team_key="policyorganization__organization__in",
            id_key="id__in",
        ).distinct()

    def get_queryset(self):
        queryset = MonitorPolicy.objects.all()
        request = getattr(self, "request", None)
        if request is None:
            return queryset
        if getattr(request.user, "is_superuser", False):
            return queryset
        monitor_object_id = request.query_params.get("monitor_object_id") if hasattr(request, "query_params") else None
        if monitor_object_id in (None, "") and hasattr(request, "data"):
            monitor_object_id = request.data.get("monitor_object")
        permission = self._get_permission(monitor_object_id)
        if getattr(self, "action", "") in {"update", "partial_update", "destroy"}:
            permission = _operate_only_permission(permission)
        return self._scope_queryset(queryset, permission)

    def _get_authorized_scope_groups(self):
        actor_context = _build_actor_context(self.request)
        if actor_context["is_superuser"]:
            return None
        groups = set(InstanceConfigService._get_actor_scope_groups(actor_context) or [])
        if not groups:
            raise UnauthorizedException("当前组织无可用权限范围")
        return groups

    def _ensure_target_organizations(self, organizations):
        target_orgs = _normalize_orgs(organizations)
        if not target_orgs or getattr(self.request.user, "is_superuser", False):
            return sorted(target_orgs)
        allowed_groups = self._get_authorized_scope_groups()
        unauthorized_orgs = target_orgs - allowed_groups
        if unauthorized_orgs:
            raise UnauthorizedException("无权限关联指定组织")
        return sorted(target_orgs)
```

- [ ] **Step 3: Update list() to use get_queryset()**

Replace the permission/queryset setup in `list()` with:

```python
        permission = self._get_permission(monitor_object_id)
        queryset = self.filter_queryset(self.get_queryset()).distinct()
```

Keep the existing pagination, serialization, and permission display logic unchanged.

- [ ] **Step 4: Guard create/update/partial_update/destroy and bulk assets**

In `create()`, normalize organizations before save:

```python
        request.data["created_by"] = request.user.username
        organizations = self._ensure_target_organizations(request.data.get("organizations", []))
        response = super().create(request, *args, **kwargs)
        policy_id = response.data["id"]
        policy = MonitorPolicy.objects.filter(id=policy_id).first()
        schedule = request.data.get("schedule")
        self.update_or_create_task(policy_id, schedule)
        self.update_policy_organizations(policy_id, organizations)
```

In `update()` and `partial_update()`, call `self.get_object()` before reading old state, and normalize organizations only when present:

```python
        existing_policy = self.get_object()
        policy_id = existing_policy.id
        organizations = None
        if "organizations" in request.data:
            organizations = self._ensure_target_organizations(request.data.get("organizations", []))
```

Use `policy_id = existing_policy.id` instead of `kwargs["pk"]`. Replace `if organizations:` with:

```python
            if organizations is not None:
                self.update_policy_organizations(policy_id, organizations)
```

In `destroy()`, call `policy = self.get_object()` before side effects and use `policy.id`.

In `get_bulk_policy_assets()`, require `self.request` and filter instances through monitor instance authorization:

```python
        actor_context = _build_actor_context(self.request)
        authorized_qs = InstanceConfigService._get_authorized_monitor_instances(
            actor_context,
            monitor_object_id,
            require_operate=False,
        )
        instances = list(
            authorized_qs.filter(
                id__in=normalized_ids,
                monitor_object_id=monitor_object_id,
                is_deleted=False,
            ).values("id")
        )
```

- [ ] **Step 5: Run policy tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_monitor_permission_guards.py apps/monitor/tests/test_monitor_policy_view_helpers.py -q
```

Expected: PASS for the policy tests. If an unrelated assertion in `test_monitor_policy_view_helpers.py` needs `view.request`, update only that test helper to provide `_request(current_team=1)` before invoking guarded methods.

- [ ] **Step 6: Commit policy guard implementation**

```bash
git add server/apps/monitor/views/monitor_policy.py server/apps/monitor/tests/test_monitor_permission_guards.py server/apps/monitor/tests/test_monitor_policy_view_helpers.py
git commit -m "fix(monitor): 收口策略对象级权限"
```

## Task 3: Add Failing MonitorCondition Permission Guard Tests

**Files:**
- Modify: `server/apps/monitor/tests/test_monitor_permission_guards.py`
- Read: `server/apps/monitor/views/monitor_condition.py`
- Read: `server/apps/monitor/tests/test_monitor_views_extra.py`

- [ ] **Step 1: Append condition permission tests**

Append this content to `server/apps/monitor/tests/test_monitor_permission_guards.py`:

```python
from apps.monitor.models.monitor_condition import MonitorCondition, MonitorConditionOrganization
from apps.monitor.views.monitor_condition import MonitorConditionViewSet


def _condition(*, name="condition", org=1):
    condition = MonitorCondition.objects.create(name=name, condition={"field": "value"})
    MonitorConditionOrganization.objects.create(monitor_condition=condition, organization=org)
    return condition


def _patch_condition_permission(mocker, *, teams=None, instances=None):
    mocker.patch(
        "apps.monitor.views.monitor_condition.get_permission_rules",
        return_value={"team": teams or [], "instance": instances or []},
    )


class TestMonitorConditionObjectPermission:
    def test_read_queryset_returns_only_authorized_team_conditions(self, mocker):
        allowed = _condition(name="allowed-condition", org=1)
        blocked = _condition(name="blocked-condition", org=2)
        _patch_condition_permission(mocker, teams=[1])

        view = MonitorConditionViewSet()
        view.request = _request(current_team=1)
        view.action = "retrieve"

        ids = set(view.get_queryset().values_list("id", flat=True))
        assert allowed.id in ids
        assert blocked.id not in ids

    def test_write_queryset_requires_operate_instance_permission(self, mocker):
        allowed = _condition(name="allowed-condition-operate", org=9)
        blocked = _condition(name="blocked-condition-view", org=9)
        _patch_condition_permission(
            mocker,
            teams=[],
            instances=[
                {"id": allowed.id, "permission": ["View", "Operate"]},
                {"id": blocked.id, "permission": ["View"]},
            ],
        )

        view = MonitorConditionViewSet()
        view.request = _request(current_team=1)
        view.action = "update"

        ids = set(view.get_queryset().values_list("id", flat=True))
        assert allowed.id in ids
        assert blocked.id not in ids

    def test_rejects_unauthorized_condition_organizations(self, mocker):
        _patch_condition_permission(mocker, teams=[1])
        view = MonitorConditionViewSet()
        view.request = _request(current_team=1)

        with pytest.raises(Exception):
            view._ensure_target_organizations([1, 2])

    def test_destroy_queryset_blocks_organization_cleanup_target(self, mocker):
        blocked = _condition(name="blocked-condition-destroy", org=2)
        _patch_condition_permission(mocker, teams=[1])

        view = MonitorConditionViewSet()
        view.request = _request(current_team=1)
        view.action = "destroy"

        assert not view.get_queryset().filter(id=blocked.id).exists()
        assert MonitorConditionOrganization.objects.filter(monitor_condition_id=blocked.id, organization=2).exists()
```

- [ ] **Step 2: Run condition tests and verify they fail**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_monitor_permission_guards.py -q
```

Expected: FAIL because `MonitorConditionViewSet.get_queryset()` and `_ensure_target_organizations()` are not implemented yet.

- [ ] **Step 3: Commit failing condition tests**

```bash
git add server/apps/monitor/tests/test_monitor_permission_guards.py
git commit -m "test(monitor): 覆盖条件对象级权限围栏"
```

## Task 4: Implement MonitorConditionViewSet Permission Guards

**Files:**
- Modify: `server/apps/monitor/views/monitor_condition.py`
- Test: `server/apps/monitor/tests/test_monitor_permission_guards.py`
- Test: `server/apps/monitor/tests/test_monitor_views_extra.py`

- [ ] **Step 1: Add local helpers to monitor_condition.py**

Modify imports:

```python
from apps.core.exceptions.base_app_exception import BaseAppException, UnauthorizedException
from apps.core.utils.user_group import normalize_user_group_ids
from apps.monitor.services.node_mgmt import InstanceConfigService
```

Add helpers above `class MonitorConditionViewSet`:

```python
def _build_actor_context(request):
    current_team = get_current_team(request)
    if current_team in (None, ""):
        raise BaseAppException("缺少 current_team 参数")
    try:
        current_team = int(current_team)
    except (TypeError, ValueError):
        raise BaseAppException("current_team 参数非法")
    return {
        "username": request.user.username,
        "domain": request.user.domain,
        "current_team": current_team,
        "include_children": request.COOKIES.get("include_children", "0") == "1",
        "is_superuser": request.user.is_superuser,
        "group_list": normalize_user_group_ids(getattr(request.user, "group_list", [])),
    }


def _normalize_orgs(organizations):
    try:
        return {int(org) for org in (organizations or []) if org not in (None, "")}
    except (TypeError, ValueError):
        raise BaseAppException("组织参数非法")


def _operate_only_permission(permission):
    return {
        **permission,
        "team": permission.get("team", []),
        "instance": [
            item
            for item in permission.get("instance", [])
            if isinstance(item, dict) and "Operate" in item.get("permission", [])
        ],
    }
```

- [ ] **Step 2: Add ViewSet methods for condition queryset and org guard**

Inside `MonitorConditionViewSet`, add before `list()`:

```python
    def _get_permission(self):
        include_children = self.request.COOKIES.get("include_children", "0") == "1"
        return get_permission_rules(
            self.request.user,
            get_current_team(self.request),
            "monitor",
            PermissionConstants.CONDITION_MODULE,
            include_children=include_children,
        )

    def get_queryset(self):
        queryset = MonitorCondition.objects.all()
        request = getattr(self, "request", None)
        if request is None:
            return queryset
        if getattr(request.user, "is_superuser", False):
            return queryset
        permission = self._get_permission()
        if getattr(self, "action", "") in {"update", "partial_update", "destroy"}:
            permission = _operate_only_permission(permission)
        return permission_filter(
            MonitorCondition,
            permission,
            team_key="organizations__organization__in",
            id_key="id__in",
        ).distinct()

    def _get_authorized_scope_groups(self):
        actor_context = _build_actor_context(self.request)
        if actor_context["is_superuser"]:
            return None
        groups = set(InstanceConfigService._get_actor_scope_groups(actor_context) or [])
        if not groups:
            raise UnauthorizedException("当前组织无可用权限范围")
        return groups

    def _ensure_target_organizations(self, organizations):
        target_orgs = _normalize_orgs(organizations)
        if not target_orgs or getattr(self.request.user, "is_superuser", False):
            return sorted(target_orgs)
        allowed_groups = self._get_authorized_scope_groups()
        unauthorized_orgs = target_orgs - allowed_groups
        if unauthorized_orgs:
            raise UnauthorizedException("无权限关联指定组织")
        return sorted(target_orgs)
```

- [ ] **Step 3: Update list/create/update/partial_update/destroy**

In `list()`, replace the direct permission setup with:

```python
        permission = self._get_permission()
        queryset = self.filter_queryset(self.get_queryset()).distinct()
```

In `create()`:

```python
        request.data["created_by"] = request.user.username
        organizations = self._ensure_target_organizations(request.data.get("organizations", []))
        response = super().create(request, *args, **kwargs)
        condition_id = response.data["id"]
        self.update_condition_organizations(condition_id, organizations)
        return response
```

In `update()` and `partial_update()`, call `self.get_object()` first and only sync organizations when the request includes the field:

```python
        condition = self.get_object()
        condition_id = condition.id
        response = super().update(request, *args, **kwargs)
        if "organizations" in request.data:
            organizations = self._ensure_target_organizations(request.data.get("organizations", []))
            self.update_condition_organizations(condition_id, organizations)
        return response
```

For `partial_update()`, use `super().partial_update(...)` with the same guard.

In `destroy()`:

```python
        condition = self.get_object()
        condition_id = condition.id
        MonitorConditionOrganization.objects.filter(monitor_condition_id=condition_id).delete()
        return super().destroy(request, *args, **kwargs)
```

- [ ] **Step 4: Run condition tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_monitor_permission_guards.py apps/monitor/tests/test_monitor_views_extra.py -q
```

Expected: PASS. If the old `TestMonitorConditionView` tests call create/destroy without `current_team`, update those tests to set `api_client.cookies["current_team"] = "1"` and mock authorized groups or use a superuser-style authenticated user fixture already present in the test suite.

- [ ] **Step 5: Commit condition guard implementation**

```bash
git add server/apps/monitor/views/monitor_condition.py server/apps/monitor/tests/test_monitor_permission_guards.py server/apps/monitor/tests/test_monitor_views_extra.py
git commit -m "fix(monitor): 收口条件对象级权限"
```

## Task 5: Regression Verification and Cleanup

**Files:**
- Read: `docs/superpowers/specs/2026-07-07-monitor-policy-condition-permission-guard-design.md`
- Read: `server/apps/monitor/views/monitor_policy.py`
- Read: `server/apps/monitor/views/monitor_condition.py`
- Read: `server/apps/monitor/tests/test_monitor_permission_guards.py`

- [ ] **Step 1: Run focused monitor permission tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_monitor_permission_guards.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run related existing monitor tests**

Run:

```bash
cd server && uv run pytest apps/monitor/tests/test_monitor_policy_view_helpers.py apps/monitor/tests/test_monitor_views_extra.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Run broad monitor policy/condition selection**

Run:

```bash
cd server && uv run pytest apps/monitor/tests -k "policy or condition" -q
```

Expected: all selected tests pass. If unrelated plugin tests are selected and fail due environment fixtures, capture the failing test names and rerun only the relevant ViewSet/helper files from Steps 1 and 2.

- [ ] **Step 4: Inspect diff for scope creep**

Run:

```bash
git diff --stat HEAD
git diff -- server/apps/monitor/views/monitor_policy.py server/apps/monitor/views/monitor_condition.py server/apps/monitor/tests/test_monitor_permission_guards.py
```

Expected: only the two ViewSet files and permission guard tests contain implementation changes. No serializer, frontend, NATS, node management, or migration files are changed.

- [ ] **Step 5: Final commit if Step 4 reveals only test adjustments**

If Step 4 shows only small test adjustments not committed earlier:

```bash
git add server/apps/monitor/tests/test_monitor_permission_guards.py server/apps/monitor/tests/test_monitor_policy_view_helpers.py server/apps/monitor/tests/test_monitor_views_extra.py
git commit -m "test(monitor): 补齐权限围栏回归验证"
```

If there are no uncommitted changes, skip this commit.

## Self-Review Checklist

- Spec coverage:
  - Policy object-level read/write/delete guard is covered by Tasks 1 and 2.
  - Condition object-level read/write/delete guard is covered by Tasks 3 and 4.
  - Organization authorization guard is covered by Tasks 1 through 4.
  - Bulk policy asset authorization is covered by Tasks 1 and 2.
  - Regression and no-scope-creep verification is covered by Task 5.
- No placeholders: every task has concrete files, code snippets, commands, and expected outcomes.
- Type consistency:
  - Helper names `_build_actor_context`, `_normalize_orgs`, `_operate_only_permission`, `_ensure_target_organizations` are consistent across tasks.
  - Model and relation names match current code: `PolicyOrganization`, `MonitorConditionOrganization`, `policyorganization__organization__in`, `organizations__organization__in`.
  - Permission constants match current code: `PermissionConstants.POLICY_MODULE` and `PermissionConstants.CONDITION_MODULE`.
