# Alert Strategy NATS CRUD Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add secure NATS RPC CRUD methods for alert strategies.

**Architecture:** Keep REST and NATS strategy behavior aligned by reusing `AlarmStrategySerializer` for create and update. Add small NATS-specific helpers in `server/apps/alerts/nats/nats.py` for permission checks, team scoping, request-like serializer context, response formatting, and REST-equivalent side effects.

**Tech Stack:** Python 3.12, Django 4.2, Django REST Framework serializers, pytest.

---

## File Structure

- Modify `server/apps/alerts/nats/nats.py`: add helper functions and registered CRUD RPC methods.
- Modify `server/apps/alerts/test/test_nats_handlers.py`: add focused TDD tests for authorization, scope, create, update, and delete.

## Task 1: Authorization And Scoped Reads

**Files:**
- Modify: `server/apps/alerts/test/test_nats_handlers.py`
- Modify: `server/apps/alerts/nats/nats.py`

- [ ] **Step 1: Write failing tests for list/detail authorization and team scope**

Add these tests to `server/apps/alerts/test/test_nats_handlers.py`:

```python
@pytest.fixture
def strategy_user_info():
    return {
        "team": 1,
        "user": "alice",
        "domain": "domain.com",
        "is_superuser": False,
        "permission": {"alarm": ["correlation_rules-View"]},
    }


@pytest.mark.django_db
def test_list_alarm_strategies_requires_view_permission():
    result = N.list_alarm_strategies(user_info={"team": 1, "permission": {"alarm": []}})

    assert result["result"] is False
    assert "permission" in result["message"].lower()


@pytest.mark.django_db
def test_list_alarm_strategies_filters_to_authorized_team(strategy_user_info):
    AlarmStrategy.objects.create(name="team-one", strategy_type="smart_denoise", team=[1], dispatch_team=[1])
    AlarmStrategy.objects.create(name="team-two", strategy_type="smart_denoise", team=[2], dispatch_team=[2])

    result = N.list_alarm_strategies(user_info=strategy_user_info)

    assert result["result"] is True
    names = [item["name"] for item in result["data"]["items"]]
    assert names == ["team-one"]


@pytest.mark.django_db
def test_get_alarm_strategy_rejects_cross_team_access(strategy_user_info):
    strategy = AlarmStrategy.objects.create(name="team-two", strategy_type="smart_denoise", team=[2], dispatch_team=[2])

    result = N.get_alarm_strategy(strategy.id, user_info=strategy_user_info)

    assert result["result"] is False
    assert "not found" in result["message"].lower()
```

- [ ] **Step 2: Run tests to verify RED**

Run:

```bash
cd server && uv run pytest apps/alerts/test/test_nats_handlers.py::test_list_alarm_strategies_requires_view_permission apps/alerts/test/test_nats_handlers.py::test_list_alarm_strategies_filters_to_authorized_team apps/alerts/test/test_nats_handlers.py::test_get_alarm_strategy_rejects_cross_team_access -q
```

Expected: fail because `list_alarm_strategies` and `get_alarm_strategy` do not exist.

- [ ] **Step 3: Implement minimal authorization and read helpers**

Add to `server/apps/alerts/nats/nats.py`:

```python
from types import SimpleNamespace
from rest_framework import serializers

from apps.alerts.models.alert_operator import AlarmStrategy
from apps.alerts.serializers import AlarmStrategySerializer
from apps.alerts.utils.permission_scope import apply_team_scope_with_group_ids
```

Add helper functions:

```python
def _flatten_error_message(detail, field_name: str = "") -> list[str]:
    if isinstance(detail, dict):
        items = []
        for key, value in detail.items():
            next_field = f"{field_name}.{key}" if field_name else str(key)
            items.extend(_flatten_error_message(value, next_field))
        return items
    if isinstance(detail, list):
        items = []
        for value in detail:
            items.extend(_flatten_error_message(value, field_name))
        return items
    message = str(detail)
    return [f"{field_name}: {message}" if field_name else message]


def _build_validation_message(exc: Exception) -> str:
    detail = getattr(exc, "detail", exc)
    messages = _flatten_error_message(detail)
    return "; ".join(dict.fromkeys(messages)) if messages else str(exc)


def _nats_failure(message: str, data=None):
    return {"result": False, "data": [] if data is None else data, "message": message}


def _nats_success(data):
    return {"result": True, "data": data, "message": ""}


def _extract_alert_permissions(user_info: dict) -> set:
    permission_data = (user_info or {}).get("permission", {})
    if isinstance(permission_data, dict):
        app_permissions = permission_data.get("alarm", [])
    elif isinstance(permission_data, (set, list, tuple)):
        app_permissions = permission_data
    else:
        app_permissions = []
    return set(app_permissions)


def _has_alarm_strategy_permission(user_info: dict, permission_name: str) -> bool:
    if (user_info or {}).get("is_superuser"):
        return True
    return permission_name in _extract_alert_permissions(user_info)


def _get_nats_group_ids(user_info: dict):
    user_info = user_info or {}
    current_team = user_info.get("team")
    if not current_team:
        return [], _nats_failure("缺少组织信息")
    try:
        team_id = int(current_team)
    except (TypeError, ValueError):
        return [], _nats_failure("组织信息非法")

    group_ids = [team_id]
    if user_info.get("include_children"):
        child_group_ids = GenericViewSetFun.extract_child_group_ids(user_info.get("group_tree", []), team_id)
        if child_group_ids:
            group_ids = child_group_ids
    return group_ids, None


def _authorize_alarm_strategy(user_info: dict, permission_name: str):
    if not isinstance(user_info, dict):
        return _nats_failure("缺少用户信息")
    if not _has_alarm_strategy_permission(user_info, permission_name):
        return _nats_failure("Insufficient permissions")
    _, error = _get_nats_group_ids(user_info)
    return error


def _get_alarm_strategy_queryset(user_info: dict):
    error = _authorize_alarm_strategy(user_info, "correlation_rules-View")
    if error:
        return None, error

    queryset = AlarmStrategy.objects.all()
    if (user_info or {}).get("is_superuser"):
        return queryset, None

    group_ids, error = _get_nats_group_ids(user_info)
    if error:
        return None, error
    return apply_team_scope_with_group_ids(queryset, group_ids, field_name="team"), None


def _get_scoped_alarm_strategy(strategy_id, user_info: dict, permission_name: str):
    error = _authorize_alarm_strategy(user_info, permission_name)
    if error:
        return None, error

    queryset = AlarmStrategy.objects.all()
    if not (user_info or {}).get("is_superuser"):
        group_ids, error = _get_nats_group_ids(user_info)
        if error:
            return None, error
        queryset = apply_team_scope_with_group_ids(queryset, group_ids, field_name="team")

    try:
        return queryset.get(id=strategy_id), None
    except AlarmStrategy.DoesNotExist:
        return None, _nats_failure("Alarm strategy not found")
```

Add registered read methods:

```python
@nats_client.register
def list_alarm_strategies(query_data=None, *args, **kwargs):
    user_info = kwargs.get("user_info", {}) or {}
    queryset, error = _get_alarm_strategy_queryset(user_info)
    if error:
        return error

    query_data = query_data or {}
    if query_data.get("name"):
        queryset = queryset.filter(name__icontains=query_data["name"])
    if query_data.get("created_at_after"):
        queryset = queryset.filter(created_at__gte=query_data["created_at_after"])
    if query_data.get("created_at_before"):
        queryset = queryset.filter(created_at__lte=query_data["created_at_before"])

    page = int(query_data.get("page", 1) or 1)
    page_size = int(query_data.get("page_size", 20) or 20)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)
    total_count = queryset.count()
    start = (page - 1) * page_size
    items = AlarmStrategySerializer(queryset.order_by("-created_at")[start:start + page_size], many=True).data
    return _nats_success({"count": total_count, "page": page, "page_size": page_size, "items": items})


@nats_client.register
def get_alarm_strategy(strategy_id, *args, **kwargs):
    strategy, error = _get_scoped_alarm_strategy(strategy_id, kwargs.get("user_info", {}) or {}, "correlation_rules-View")
    if error:
        return error
    return _nats_success(AlarmStrategySerializer(strategy).data)
```

- [ ] **Step 4: Run tests to verify GREEN**

Run the command from Step 2. Expected: pass.

## Task 2: Create RPC

**Files:**
- Modify: `server/apps/alerts/test/test_nats_handlers.py`
- Modify: `server/apps/alerts/nats/nats.py`

- [ ] **Step 1: Write failing create tests**

Add:

```python
@pytest.fixture
def strategy_add_user_info(strategy_user_info):
    data = dict(strategy_user_info)
    data["permission"] = {"alarm": ["correlation_rules-Add", "correlation_rules-View"]}
    return data


def _smart_strategy_payload(name="created-by-nats", team=None, dispatch_team=None):
    team = [1] if team is None else team
    dispatch_team = [1] if dispatch_team is None else dispatch_team
    return {
        "name": name,
        "strategy_type": "smart_denoise",
        "team": team,
        "dispatch_team": dispatch_team,
        "match_rules": [[{"key": "service", "operator": "eq", "value": "api"}]],
        "params": {"group_by": ["service"], "window_size": 5, "time_out": False},
        "auto_close": False,
        "close_minutes": 120,
    }


@pytest.mark.django_db
def test_create_alarm_strategy_uses_serializer_and_actor(strategy_add_user_info):
    result = N.create_alarm_strategy(_smart_strategy_payload(), user_info=strategy_add_user_info)

    assert result["result"] is True
    strategy = AlarmStrategy.objects.get(name="created-by-nats")
    assert strategy.params["window_size"] == 5
    assert result["data"]["id"] == strategy.id


@pytest.mark.django_db
def test_create_alarm_strategy_rejects_unauthorized_target_team(strategy_add_user_info):
    result = N.create_alarm_strategy(_smart_strategy_payload(team=[2], dispatch_team=[2]), user_info=strategy_add_user_info)

    assert result["result"] is False
    assert "authorized" in result["message"].lower()
    assert not AlarmStrategy.objects.filter(name="created-by-nats").exists()
```

- [ ] **Step 2: Run create tests to verify RED**

Run:

```bash
cd server && uv run pytest apps/alerts/test/test_nats_handlers.py::test_create_alarm_strategy_uses_serializer_and_actor apps/alerts/test/test_nats_handlers.py::test_create_alarm_strategy_rejects_unauthorized_target_team -q
```

Expected: fail because `create_alarm_strategy` does not exist.

- [ ] **Step 3: Implement create support**

Add to `server/apps/alerts/nats/nats.py`:

```python
def _normalize_nats_user(user_info: dict):
    user_value = (user_info or {}).get("user")
    username = getattr(user_value, "username", None) or (user_value if isinstance(user_value, str) and user_value else "api")
    domain = (user_info or {}).get("domain") or getattr(user_value, "domain", None) or "domain.com"
    return SimpleNamespace(
        username=username,
        domain=domain,
        is_superuser=bool((user_info or {}).get("is_superuser")),
        group_list=[{"id": group_id} for group_id in (_get_nats_group_ids(user_info)[0] or [])],
        group_tree=(user_info or {}).get("group_tree", []),
    )


def _build_nats_serializer_context(user_info: dict):
    group_ids, _ = _get_nats_group_ids(user_info)
    request = SimpleNamespace(
        user=_normalize_nats_user(user_info),
        COOKIES={
            "current_team": str((user_info or {}).get("team") or ""),
            "include_children": "1" if (user_info or {}).get("include_children") else "0",
        },
    )
    if group_ids:
        request.user.group_list = [{"id": group_id} for group_id in group_ids]
    return {"request": request}


def _create_alarm_strategy_payload(data: dict, user_info: dict):
    if not isinstance(data, dict):
        raise ValueError("data 必须是字典")
    serializer = AlarmStrategySerializer(data=dict(data), context=_build_nats_serializer_context(user_info))
    serializer.is_valid(raise_exception=True)
    strategy = serializer.save()
    _create_alarm_strategy_operator_log("创建告警策略", strategy, user_info)
    return strategy, AlarmStrategySerializer(strategy).data


def _execute_alarm_strategy_write(write_func, data, user_info: dict):
    try:
        result = write_func(data, user_info)
        if isinstance(result, tuple):
            _, result_data = result
        else:
            result_data = result
        return _nats_success(result_data)
    except (serializers.ValidationError, ValueError) as exc:
        return _nats_failure(_build_validation_message(exc))
    except Exception as exc:
        logger.exception("alert strategy NATS write failed, error=%s", exc)
        return _nats_failure(str(exc))


@nats_client.register
def create_alarm_strategy(data: dict, *args, **kwargs):
    user_info = kwargs.get("user_info", {}) or {}
    error = _authorize_alarm_strategy(user_info, "correlation_rules-Add")
    if error:
        return error
    return _execute_alarm_strategy_write(_create_alarm_strategy_payload, data, user_info)
```

Also add `_create_alarm_strategy_operator_log`:

```python
def _resolve_alarm_strategy_operator(user_info: dict) -> str:
    user_value = (user_info or {}).get("user")
    return getattr(user_value, "username", None) or (user_value if isinstance(user_value, str) and user_value else "api")


def _create_alarm_strategy_operator_log(action_text: str, strategy: AlarmStrategy, user_info: dict):
    OperatorLog.objects.create(
        action=LogAction.ADD if action_text.startswith("创建") else LogAction.MODIFY,
        target_type=LogTargetType.SYSTEM,
        operator=_resolve_alarm_strategy_operator(user_info),
        operator_object=f"告警策略-{action_text}",
        target_id=strategy.id,
        overview=f"{action_text}: 策略名称:{strategy.name}",
    )
```

- [ ] **Step 4: Run create tests to verify GREEN**

Run the command from Step 2. Expected: pass.

## Task 3: Update And Delete RPC

**Files:**
- Modify: `server/apps/alerts/test/test_nats_handlers.py`
- Modify: `server/apps/alerts/nats/nats.py`

- [ ] **Step 1: Write failing update/delete tests**

Add:

```python
@pytest.fixture
def strategy_edit_delete_user_info(strategy_user_info):
    data = dict(strategy_user_info)
    data["permission"] = {"alarm": ["correlation_rules-View", "correlation_rules-Edit", "correlation_rules-Delete"]}
    return data


@pytest.mark.django_db
def test_update_alarm_strategy_updates_authorized_strategy(strategy_edit_delete_user_info):
    strategy = AlarmStrategy.objects.create(
        name="before",
        strategy_type="smart_denoise",
        team=[1],
        dispatch_team=[1],
        match_rules=[[{"key": "service", "operator": "eq", "value": "api"}]],
        params={"group_by": ["service"], "window_size": 5, "time_out": False},
    )

    result = N.update_alarm_strategy(strategy.id, {"name": "after"}, user_info=strategy_edit_delete_user_info)

    assert result["result"] is True
    strategy.refresh_from_db()
    assert strategy.name == "after"


@pytest.mark.django_db
def test_update_alarm_strategy_rejects_cross_team_access(strategy_edit_delete_user_info):
    strategy = AlarmStrategy.objects.create(name="team-two", strategy_type="smart_denoise", team=[2], dispatch_team=[2])

    result = N.update_alarm_strategy(strategy.id, {"name": "after"}, user_info=strategy_edit_delete_user_info)

    assert result["result"] is False
    strategy.refresh_from_db()
    assert strategy.name == "team-two"


@pytest.mark.django_db
def test_delete_alarm_strategy_removes_authorized_strategy(strategy_edit_delete_user_info):
    strategy = AlarmStrategy.objects.create(name="delete-me", strategy_type="smart_denoise", team=[1], dispatch_team=[1])

    result = N.delete_alarm_strategy(strategy.id, user_info=strategy_edit_delete_user_info)

    assert result["result"] is True
    assert result["data"]["deleted_id"] == strategy.id
    assert not AlarmStrategy.objects.filter(id=strategy.id).exists()


@pytest.mark.django_db
def test_delete_alarm_strategy_rejects_cross_team_access(strategy_edit_delete_user_info):
    strategy = AlarmStrategy.objects.create(name="keep-me", strategy_type="smart_denoise", team=[2], dispatch_team=[2])

    result = N.delete_alarm_strategy(strategy.id, user_info=strategy_edit_delete_user_info)

    assert result["result"] is False
    assert AlarmStrategy.objects.filter(id=strategy.id).exists()
```

- [ ] **Step 2: Run update/delete tests to verify RED**

Run:

```bash
cd server && uv run pytest apps/alerts/test/test_nats_handlers.py::test_update_alarm_strategy_updates_authorized_strategy apps/alerts/test/test_nats_handlers.py::test_update_alarm_strategy_rejects_cross_team_access apps/alerts/test/test_nats_handlers.py::test_delete_alarm_strategy_removes_authorized_strategy apps/alerts/test/test_nats_handlers.py::test_delete_alarm_strategy_rejects_cross_team_access -q
```

Expected: fail because update/delete RPC methods do not exist.

- [ ] **Step 3: Implement update and delete**

Add:

```python
def _is_session_strategy(strategy: AlarmStrategy) -> bool:
    params = strategy.params or {}
    return bool(params.get("time_out")) and int(params.get("time_minutes") or 0) > 0


def _update_alarm_strategy_payload(strategy: AlarmStrategy, data: dict, user_info: dict, partial=True):
    if not isinstance(data, dict):
        raise ValueError("data 必须是字典")
    old_is_session = _is_session_strategy(strategy)
    serializer = AlarmStrategySerializer(
        strategy,
        data=dict(data),
        partial=partial,
        context=_build_nats_serializer_context(user_info),
    )
    serializer.is_valid(raise_exception=True)
    updated = serializer.save()
    if old_is_session and not _is_session_strategy(updated):
        from apps.alerts.aggregation.recovery.timeout_checker import TimeoutChecker

        TimeoutChecker.confirm_observing_alerts_by_strategy(updated.id)
    _create_alarm_strategy_operator_log("修改告警策略", updated, user_info)
    return updated, AlarmStrategySerializer(updated).data


@nats_client.register
def update_alarm_strategy(strategy_id, data: dict, partial=True, *args, **kwargs):
    user_info = kwargs.get("user_info", {}) or {}
    strategy, error = _get_scoped_alarm_strategy(strategy_id, user_info, "correlation_rules-Edit")
    if error:
        return error
    return _execute_alarm_strategy_write(
        lambda payload, context_user_info: _update_alarm_strategy_payload(strategy, payload, context_user_info, partial=partial),
        data,
        user_info,
    )


@nats_client.register
def delete_alarm_strategy(strategy_id, *args, **kwargs):
    user_info = kwargs.get("user_info", {}) or {}
    strategy, error = _get_scoped_alarm_strategy(strategy_id, user_info, "correlation_rules-Delete")
    if error:
        return error
    deleted_id = strategy.id
    deleted_name = strategy.name
    try:
        if _is_session_strategy(strategy):
            from apps.alerts.aggregation.recovery.timeout_checker import TimeoutChecker

            TimeoutChecker.close_observing_session_alerts_by_strategy(strategy.id)
        strategy.delete()
        OperatorLog.objects.create(
            action=LogAction.DELETE,
            target_type=LogTargetType.SYSTEM,
            operator=_resolve_alarm_strategy_operator(user_info),
            operator_object="告警策略-删除告警策略",
            target_id=deleted_id,
            overview=f"删除告警策略: 策略名称:{deleted_name}",
        )
        return _nats_success({"deleted_id": deleted_id})
    except Exception as exc:
        logger.exception("alert strategy NATS delete failed, error=%s", exc)
        return _nats_failure(str(exc))
```

- [ ] **Step 4: Run update/delete tests to verify GREEN**

Run the command from Step 2. Expected: pass.

## Task 4: Focused Regression

**Files:**
- Modify: `server/apps/alerts/test/test_nats_handlers.py`
- Modify: `server/apps/alerts/nats/nats.py`

- [ ] **Step 1: Run the full alert NATS handler test file**

Run:

```bash
cd server && uv run pytest apps/alerts/test/test_nats_handlers.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Fix any focused failures with the smallest change**

If a failure appears, only adjust `server/apps/alerts/nats/nats.py` or the newly added tests. Do not change unrelated alert behavior.

- [ ] **Step 3: Run server module gate if feasible**

Run:

```bash
cd server && make test
```

Expected: test suite exits with code 0. If environment services are missing, record the exact failure in the final response.
