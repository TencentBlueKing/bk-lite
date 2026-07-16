import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.models.node_mgmt_sync import NodeMgmtSyncConfig
from apps.cmdb.services.node_mgmt_sync_service import NodeMgmtSyncService
from apps.cmdb.views.node_mgmt_sync import NodeMgmtSyncViewSet

pytestmark = pytest.mark.django_db


def _user(*permissions, is_superuser=False):
    return SimpleNamespace(
        username="operator", is_superuser=is_superuser, is_authenticated=True, is_active=True, permission={"cmdb": set(permissions)}, locale="zh",
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


def test_auto_collect_with_sync_disabled_is_saved_as_waiting_sync():
    config = NodeMgmtSyncService.update_task({"auto_sync_enabled": False, "auto_collect_enabled": True})

    config.refresh_from_db()
    assert config.auto_sync_enabled is False
    assert config.auto_collect_enabled is True
    assert config.node_config_status == "waiting_sync"
