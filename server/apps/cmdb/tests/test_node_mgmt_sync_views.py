import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.models.node_mgmt_sync import NodeMgmtSyncConfig, NodeMgmtSyncRun
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.cmdb.views.node_mgmt_sync import NodeMgmtSyncViewSet

pytestmark = pytest.mark.django_db


def _user(*permissions, is_superuser=False):
    return SimpleNamespace(
        username="operator", is_superuser=is_superuser, is_authenticated=True, is_active=True,
        permission={"cmdb": set(permissions)}, locale="zh", group_list=[{"id": 7}],
    )


def _call(action, method, user, data=None):
    request = getattr(APIRequestFactory(), method.lower())(f"/api/v1/cmdb/api/node_mgmt_sync/{action}/", data=data or {}, format="json",)
    force_authenticate(request, user=user)
    return NodeMgmtSyncViewSet.as_view({method.lower(): action})(request)


@pytest.mark.parametrize("action", ["task", "config"])
def test_view_permission_can_read_but_cannot_update_both_config_urls(action):
    user = _user("auto_collection-View")
    with patch.object(NodeMgmtSyncService, "get_task_payload", return_value={"id": 1}) as get_payload:
        get_response = _call(action, "GET", user)
    with patch.object(NodeMgmtSyncService, "update_task") as update_task:
        put_response = _call(action, "PUT", user, {"auto_sync_enabled": False})

    assert get_response.status_code == 200
    assert put_response.status_code == 403
    get_payload.assert_called_once_with(reconcile=True)
    update_task.assert_not_called()


@pytest.mark.parametrize("action", ["task", "config"])
def test_execute_permission_can_update_both_config_urls(action):
    config = SimpleNamespace()
    with patch.object(NodeMgmtSyncService, "update_task", return_value=config) as update_task:
        with patch.object(
            NodeMgmtSyncService, "serialize_task", return_value={"auto_sync_enabled": False},
        ):
            response = _call(action, "PUT", _user("auto_collection-Execute"), {"auto_sync_enabled": False},)

    assert response.status_code == 200
    assert json.loads(response.content)["data"]["auto_sync_enabled"] is False
    update_task.assert_called_once_with({"auto_sync_enabled": False})


@pytest.mark.parametrize("action,service_method", [("run_sync", "trigger_sync"), ("run_collect", "trigger_collect")])
def test_non_superuser_with_execute_permission_cannot_start_global_run(action, service_method):
    with patch.object(NodeMgmtSyncService, service_method) as trigger:
        response = _call(action, "POST", _user("auto_collection-Execute"))

    assert response.status_code == 403
    assert json.loads(response.content)["message"] == "仅平台管理员可执行全局节点同步"
    trigger.assert_not_called()


@pytest.mark.parametrize("action,service_method", [("run_sync", "trigger_sync"), ("run_collect", "trigger_collect")])
def test_superuser_can_start_global_run(action, service_method):
    with patch.object(NodeMgmtSyncService, service_method, return_value={"status": "submitted"}) as trigger:
        response = _call(action, "POST", _user(is_superuser=True))

    assert response.status_code == 200
    trigger.assert_called_once_with()


@pytest.mark.parametrize("action", ["latest_run", "display", "detail_compat"])
def test_read_only_actions_require_view_permission(action):
    response = _call(action, "GET", _user("auto_collection-Execute"))

    assert response.status_code == 403


def test_config_response_exposes_stable_reconciliation_health_contract():
    config = NodeMgmtSyncConfig.objects.create(
        schedule_status="degraded",
        node_config_status="waiting_sync",
        reconcile_error_code="RECONCILE_FAILED",
        reconcile_error_message="RuntimeError: 节点管理同步对账失败",
    )

    payload = NodeMgmtSyncService.serialize_task(config)

    assert payload["health"] == {
        "schedule_status": "degraded",
        "node_config_status": "waiting_sync",
        "last_reconciled_at": None,
        "reason_code": "RECONCILE_FAILED",
        "message": "RuntimeError: 节点管理同步对账失败",
    }


def test_run_response_exposes_stable_reason_and_real_timestamps():
    config = NodeMgmtSyncConfig.objects.create()
    submitted_at = timezone.now()
    deadline_at = submitted_at + timedelta(minutes=10)
    run = NodeMgmtSyncRun.objects.create(
        task=config,
        run_type=NodeMgmtSyncRun.RUN_TYPE_COLLECT,
        status=NodeMgmtSyncRun.STATUS_BLOCKED,
        reason_code="NO_ACCESS_POINT",
        submitted_at=submitted_at,
        deadline_at=deadline_at,
    )

    payload = NodeMgmtSyncService.serialize_run(run)

    assert payload["reason_code"] == "NO_ACCESS_POINT"
    assert payload["submitted_at"] == NodeMgmtSyncService._serialize_dt(submitted_at)
    assert payload["deadline_at"] == NodeMgmtSyncService._serialize_dt(deadline_at)
    assert "next_retry_at" not in payload


@pytest.mark.parametrize(
    "field,value",
    [("sync_interval_minutes", 0), ("sync_interval_minutes", 1441), ("collect_interval_minutes", 0), ("collect_interval_minutes", 1441)],
)
def test_update_rejects_interval_outside_one_to_1440(field, value):
    with pytest.raises(ValueError, match="必须在 1 到 1440 分钟之间"):
        NodeMgmtSyncService.update_task({field: value})


def test_invalid_interval_returns_stable_bad_request_from_update_api():
    response = _call("task", "PUT", _user("auto_collection-Execute"), {"sync_interval_minutes": 0},)

    assert response.status_code == 400
    assert "必须在 1 到 1440 分钟之间" in json.loads(response.content)["message"]


@pytest.mark.parametrize("action", ["task", "config"])
@pytest.mark.parametrize("value", [1440.9, 5.0, True, False, "5.0", "five"])
def test_update_api_rejects_non_integer_interval_types(action, value):
    response = _call(action, "PUT", _user("auto_collection-Execute"), {"sync_interval_minutes": value},)

    body = json.loads(response.content)
    assert response.status_code == 400
    assert body == {
        "data": {},
        "result": False,
        "message": "sync_interval_minutes 必须在 1 到 1440 分钟之间",
    }


@pytest.mark.parametrize("action", ["task", "config"])
def test_update_api_keeps_accepting_decimal_integer_string(action):
    response = _call(action, "PUT", _user("auto_collection-Execute"), {"sync_interval_minutes": "5"},)

    assert response.status_code == 200
    assert json.loads(response.content)["data"]["sync_interval_minutes"] == 5


def test_auto_collect_with_sync_disabled_is_saved_as_waiting_sync():
    config = NodeMgmtSyncService.update_task({"auto_sync_enabled": False, "auto_collect_enabled": True})

    config.refresh_from_db()
    assert config.auto_sync_enabled is False
    assert config.auto_collect_enabled is True
    assert config.node_config_status == "waiting_sync"


def test_reenable_sync_reconciles_waiting_node_config(mocker):
    config = NodeMgmtSyncService.get_task()
    config.auto_sync_enabled = False
    config.auto_collect_enabled = True
    config.node_config_status = "waiting_sync"
    config.save(
        update_fields=[
            "auto_sync_enabled", "auto_collect_enabled", "node_config_status", "updated_at",
        ]
    )
    reconcile = mocker.patch(
        "apps.cmdb.services.node_mgmt_sync_reconciler.NodeMgmtSyncReconciler.reconcile",
    )

    NodeMgmtSyncService.update_task({"auto_sync_enabled": True})

    reconcile.assert_called_once()
    assert reconcile.call_args.kwargs["reconcile_node_configs"] is True


def _sensitive_run_payload():
    row = {
        "model_id": "host",
        "inst_name": "other-org-host",
        "ip_addr": "10.0.0.8",
        "organization": [8],
    }
    detail = {
        "add": {"data": [row], "count": 1, "metadata": "10.0.0.9"},
        "update": {"data": [], "count": 0},
        "delete": {"data": [], "count": 0},
        "relation": {"data": [], "count": 0},
        "raw_data": {"data": [row], "count": 1},
        "todo": [{"organization": [8], "ip_addr": "10.0.0.8"}],
    }
    return {
        "id": 1,
        "status": "success",
        "message": {"all": 1, "add": 1, "message": "10.0.0.9 同步失败"},
        "summary": {"all": 1, "add": 1, "message": "10.0.0.9 同步失败"},
        "detail": detail,
        "error_message": "organization=[8]",
    }


def test_non_superuser_latest_run_get_keeps_counts_but_hides_global_rows():
    payload = _sensitive_run_payload()
    with patch.object(NodeMgmtSyncService, "get_latest_run_payload", return_value=payload):
        response = _call("latest_run", "GET", _user("auto_collection-View"))

    assert response.status_code == 200
    data = json.loads(response.content)["data"]
    assert data["summary"]["all"] == 1
    assert data["summary"]["add"] == 1
    assert data["summary"]["message"] == ""
    assert data["detail"]["add"] == {"data": [], "count": 1}
    assert data["detail"]["raw_data"] == {"data": [], "count": 1}
    assert data["detail"]["todo"] == []
    assert "10.0.0.8" not in json.dumps(data)
    assert "10.0.0.9" not in json.dumps(data)
    assert "organization" not in json.dumps(data)


def test_forged_current_team_fails_closed_in_display_projection():
    run = _sensitive_run_payload()
    payload = {
        "display_source": "collect",
        "message": run["message"],
        "summary": run["summary"],
        "detail": run["detail"],
        "run": run,
    }
    request = APIRequestFactory().get(
        "/api/v1/cmdb/api/node_mgmt_sync/display/",
        HTTP_COOKIE="current_team=8; include_children=1",
    )
    force_authenticate(request, user=_user("auto_collection-View"))
    with patch.object(NodeMgmtSyncService, "get_display_payload", return_value=payload):
        response = NodeMgmtSyncViewSet.as_view({"get": "display"})(request)

    assert response.status_code == 200
    data = json.loads(response.content)["data"]
    assert data["detail"]["raw_data"] == {"data": [], "count": 1}
    assert data["run"]["detail"]["raw_data"] == {"data": [], "count": 1}
    assert "10.0.0.8" not in json.dumps(data)
    assert "organization" not in json.dumps(data)


@pytest.mark.parametrize("action", ["latest_run", "display"])
def test_superuser_read_keeps_complete_global_detail(action):
    run = _sensitive_run_payload()
    payload = run if action == "latest_run" else {"detail": run["detail"], "run": run}
    method = "get_latest_run_payload" if action == "latest_run" else "get_display_payload"
    with patch.object(NodeMgmtSyncService, method, return_value=payload):
        response = _call(action, "GET", _user("auto_collection-View", is_superuser=True))

    data = json.loads(response.content)["data"]
    assert "10.0.0.8" in json.dumps(data)
    assert "organization" in json.dumps(data)


@pytest.mark.parametrize("action", ["task", "config"])
@pytest.mark.parametrize("field", ["auto_sync_enabled", "auto_collect_enabled"])
@pytest.mark.parametrize("value", ["false", "0", None, 0, 1])
def test_update_api_only_accepts_json_boolean_for_switches(action, field, value):
    response = _call(action, "PUT", _user("auto_collection-Execute"), {field: value})

    assert response.status_code == 400
    assert json.loads(response.content)["message"] == f"{field} 必须是布尔值"


def test_non_superuser_display_is_rebuilt_from_fixed_schema_and_validates_scalars():
    valid_time = "2026-07-17 03:00:00+0800"
    malicious = {
        "display_source": "collect",
        "display_schema": "host_collect",
        "root_secret": "10.0.0.99",
        "message": {
            "all": 2,
            "add": True,
            "update": "3",
            "delete": -1,
            "association": 10_000_001,
            "message": "10.0.0.98",
            "last_time": "not-a-time 10.0.0.97",
            "unknown": "10.0.0.96",
        },
        "summary": {"all": 2},
        "detail": "not-a-dict 10.0.0.95",
        "run": {
            "id": 9,
            "task_id": 1,
            "run_type": "collect",
            "status": "success",
            "reason_code": "OK",
            "started_at": valid_time,
            "submitted_at": "yesterday 10.0.0.94",
            "finished_at": valid_time,
            "deadline_at": None,
            "message": {"all": 2, "message": "10.0.0.93"},
            "summary": {"all": 2, "message": "10.0.0.92"},
            "detail": {"raw_data": {"count": "2", "data": [{"ip": "10.0.0.91"}]}},
            "error_message": "10.0.0.90",
            "run_secret": {"organization": [8]},
        },
        "task": {
            "id": 1,
            "name": "10.0.0.89",
            "is_builtin": True,
            "auto_sync_enabled": True,
            "auto_collect_enabled": False,
            "sync_interval_minutes": 5,
            "collect_interval_minutes": 30,
            "version": 2,
            "schedule_status": "healthy",
            "node_config_status": "healthy",
            "last_reconciled_at": valid_time,
            "last_sync_at": "invalid 10.0.0.88",
            "last_collect_at": valid_time,
            "health": {
                "schedule_status": "healthy",
                "node_config_status": "healthy",
                "last_reconciled_at": valid_time,
                "reason_code": "",
                "message": "10.0.0.87",
                "health_secret": "10.0.0.86",
            },
            "task_secret": {"raw_data": [{"ip": "10.0.0.85"}]},
        },
    }
    with patch.object(NodeMgmtSyncService, "get_display_payload", return_value=malicious):
        response = _call("display", "GET", _user("auto_collection-View"))

    data = json.loads(response.content)["data"]
    assert set(data) == {
        "display_source", "display_schema", "message", "summary", "detail", "run", "task",
    }
    assert data["message"]["all"] == 2
    assert data["message"]["add"] == 0
    assert data["message"]["update"] == 0
    assert data["message"]["delete"] == 0
    assert data["message"]["association"] == 0
    assert data["message"]["last_time"] == ""
    assert data["detail"]["raw_data"] == {"data": [], "count": 0}
    assert data["run"]["started_at"] == valid_time
    assert data["run"]["submitted_at"] == ""
    assert data["run"]["detail"]["raw_data"] == {"data": [], "count": 0}
    assert data["run"]["error_message"] == ""
    assert data["task"]["name"] == "节点管理同步"
    assert data["task"]["last_sync_at"] == ""
    assert data["task"]["last_collect_at"] == valid_time
    assert data["task"]["health"]["message"] == ""
    serialized = json.dumps(data)
    assert "10.0.0." not in serialized
    assert "secret" not in serialized
    assert "organization" not in serialized


def test_non_superuser_latest_run_non_dict_payload_returns_fixed_empty_schema():
    with patch.object(NodeMgmtSyncService, "get_latest_run_payload", return_value="10.0.0.1"):
        response = _call("latest_run", "GET", _user("auto_collection-View"))

    data = json.loads(response.content)["data"]
    assert data["id"] is None
    assert data["status"] is None
    assert data["message"]["all"] == 0
    assert data["detail"]["raw_data"] == {"data": [], "count": 0}
    assert "10.0.0.1" not in json.dumps(data)


def _sensitive_task_payload():
    return {
        "id": 1,
        "name": "伪造任务 10.0.0.8",
        "is_builtin": True,
        "auto_sync_enabled": True,
        "auto_collect_enabled": False,
        "sync_interval_minutes": 5,
        "collect_interval_minutes": 30,
        "version": 2,
        "schedule_status": "degraded",
        "node_config_status": "healthy",
        "last_reconciled_at": "2026-07-17 03:00:00+0800",
        "last_sync_at": None,
        "last_collect_at": None,
        "reconcile_error_code": "IP_10_0_0_8",
        "reconcile_error_message": "organization=8 ip=10.0.0.8",
        "health": {
            "schedule_status": "degraded",
            "node_config_status": "healthy",
            "last_reconciled_at": "2026-07-17 03:00:00+0800",
            "reason_code": "ORGANIZATION_8",
            "message": "ip=10.0.0.8",
        },
        "unknown": {"raw_data": [{"ip": "10.0.0.8"}]},
    }


@pytest.mark.parametrize("action", ["task", "config"])
def test_non_superuser_task_get_uses_fixed_safe_task_projection(action):
    payload = _sensitive_task_payload()
    with patch.object(NodeMgmtSyncService, "get_task_payload", return_value=payload):
        response = _call(action, "GET", _user("auto_collection-View"))

    data = json.loads(response.content)["data"]
    assert set(data) == {
        "id", "name", "is_builtin", "auto_sync_enabled", "auto_collect_enabled",
        "sync_interval_minutes", "collect_interval_minutes", "version", "schedule_status",
        "node_config_status", "last_reconciled_at", "reconcile_error_code",
        "reconcile_error_message", "health", "last_sync_at", "last_collect_at",
    }
    assert data["name"] == "节点管理同步"
    assert data["reconcile_error_code"] == ""
    assert data["reconcile_error_message"] == ""
    assert data["health"]["reason_code"] == ""
    assert data["health"]["message"] == ""
    assert "10.0.0.8" not in json.dumps(data)
    assert "organization" not in json.dumps(data)


@pytest.mark.parametrize("action", ["task", "config"])
def test_non_superuser_put_success_uses_fixed_safe_task_projection(action):
    payload = _sensitive_task_payload()
    with patch.object(NodeMgmtSyncService, "update_task", return_value=SimpleNamespace()), patch.object(
        NodeMgmtSyncService, "serialize_task", return_value=payload,
    ):
        response = _call(action, "PUT", _user("auto_collection-Execute"), {"auto_sync_enabled": True})

    data = json.loads(response.content)["data"]
    assert data["name"] == "节点管理同步"
    assert data["reconcile_error_code"] == ""
    assert data["reconcile_error_message"] == ""
    assert data["health"]["message"] == ""
    assert "10.0.0.8" not in json.dumps(data)


@pytest.mark.parametrize("action,method", [("task", "get_task_payload"), ("config", "get_task_payload")])
def test_superuser_task_get_keeps_complete_payload(action, method):
    payload = _sensitive_task_payload()
    with patch.object(NodeMgmtSyncService, method, return_value=payload):
        response = _call(action, "GET", _user(is_superuser=True))

    assert json.loads(response.content)["data"] == payload


@pytest.mark.parametrize("action", ["task", "config"])
def test_superuser_task_put_keeps_complete_payload(action):
    payload = _sensitive_task_payload()
    with patch.object(NodeMgmtSyncService, "update_task", return_value=SimpleNamespace()), patch.object(
        NodeMgmtSyncService, "serialize_task", return_value=payload,
    ):
        response = _call(action, "PUT", _user(is_superuser=True), {"auto_sync_enabled": True})

    assert json.loads(response.content)["data"] == payload


@pytest.mark.parametrize("reason_code", ["IP_10_0_0_8", "ORGANIZATION_8"])
def test_non_superuser_run_rejects_format_valid_but_unapproved_reason_code(reason_code):
    payload = _sensitive_run_payload()
    payload["reason_code"] = reason_code
    with patch.object(NodeMgmtSyncService, "get_latest_run_payload", return_value=payload):
        response = _call("latest_run", "GET", _user("auto_collection-View"))

    assert json.loads(response.content)["data"]["reason_code"] == ""


def test_non_superuser_projection_keeps_explicitly_approved_reason_codes():
    run_payload = _sensitive_run_payload()
    run_payload["reason_code"] = "RUN_TIMEOUT"
    task_payload = _sensitive_task_payload()
    task_payload["reconcile_error_code"] = "RECONCILE_FAILED"
    task_payload["health"]["reason_code"] = "RECONCILE_FAILED"

    with patch.object(NodeMgmtSyncService, "get_latest_run_payload", return_value=run_payload):
        run_response = _call("latest_run", "GET", _user("auto_collection-View"))
    with patch.object(NodeMgmtSyncService, "get_task_payload", return_value=task_payload):
        task_response = _call("task", "GET", _user("auto_collection-View"))

    assert json.loads(run_response.content)["data"]["reason_code"] == "RUN_TIMEOUT"
    task_data = json.loads(task_response.content)["data"]
    assert task_data["reconcile_error_code"] == "RECONCILE_FAILED"
    assert task_data["health"]["reason_code"] == "RECONCILE_FAILED"


@pytest.mark.parametrize("reason_code", ["NODE_SOURCE_EMPTY", "NO_VALID_NODES"])
def test_non_superuser_projection_keeps_empty_node_source_reason_codes(reason_code):
    payload = _sensitive_run_payload()
    payload["reason_code"] = reason_code

    with patch.object(NodeMgmtSyncService, "get_latest_run_payload", return_value=payload):
        response = _call("latest_run", "GET", _user("auto_collection-View"))

    assert json.loads(response.content)["data"]["reason_code"] == reason_code


def test_safe_task_schedule_status_rejects_disabled_and_defaults_degraded():
    payload = _sensitive_task_payload()
    payload["schedule_status"] = "disabled"
    payload["health"]["schedule_status"] = "unknown"

    safe = NodeMgmtSyncViewSet._safe_task(payload)

    assert safe["schedule_status"] == "degraded"
    assert safe["health"]["schedule_status"] == "degraded"


def test_safe_task_node_config_status_keeps_real_disabled_and_defaults_unknown():
    payload = _sensitive_task_payload()
    payload["node_config_status"] = "disabled"
    payload["health"]["node_config_status"] = "invalid"

    safe = NodeMgmtSyncViewSet._safe_task(payload)

    assert safe["node_config_status"] == "disabled"
    assert safe["health"]["node_config_status"] == "unknown"
