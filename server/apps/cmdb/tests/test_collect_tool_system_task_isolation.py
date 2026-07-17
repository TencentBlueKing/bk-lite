import json

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.constants.constants import CollectPluginTypes
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.services.collect_tool_service import MASKED_PASSWORD
from apps.cmdb.views.collect_tool import CollectToolViewSet


@pytest.fixture
def superuser(authenticated_user):
    authenticated_user.is_superuser = True
    authenticated_user.domain = "domain.com"
    return authenticated_user


@pytest.fixture
def system_task():
    return CollectModels.objects.create(
        name="节点管理系统采集",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        driver_type="snmp",
        cycle_value_type="cycle",
        team=[1],
        is_system=True,
        is_visible=False,
        system_code="node_mgmt_region_1",
        ip_range="10.0.0.1",
        access_point=[{"id": "node-1"}],
        credential={"version": "v2c", "community": "secret"},
    )


def _body(response):
    if hasattr(response, "render"):
        response.render()
        return json.loads(response.rendered_content)
    return json.loads(response.content)


@pytest.mark.django_db
def test_collect_tool_prefill_rejects_node_mgmt_system_task(superuser, system_task, monkeypatch):
    monkeypatch.setattr(
        "apps.cmdb.permissions.inst_task_permission.InstanceTaskPermission.has_object_permission",
        lambda *args, **kwargs: True,
    )
    request = APIRequestFactory().get(
        "/collect_tool/prefill/",
        {"task_id": system_task.id, "protocol": "snmp"},
    )
    force_authenticate(request, user=superuser)

    response = CollectToolViewSet.as_view({"get": "prefill"})(request)

    assert response.status_code == 403
    assert _body(response)["result"] is False


@pytest.mark.django_db
def test_collect_tool_masked_execute_cannot_restore_node_mgmt_system_task_credentials(
    superuser, system_task, monkeypatch, mocker
):
    monkeypatch.setattr(
        "apps.cmdb.permissions.inst_task_permission.InstanceTaskPermission.has_object_permission",
        lambda *args, **kwargs: True,
    )
    mocker.patch(
        "apps.cmdb.views.collect_tool.CollectToolService.resolve_access_point",
        return_value="default_stargazer",
    )
    enqueue = mocker.patch("apps.cmdb.views.collect_tool.CollectToolService.enqueue_debug_task")
    request = APIRequestFactory().post(
        "/collect_tool/execute/",
        {
            "protocol": "snmp",
            "action": "test_connection",
            "access_point_id": "node-1",
            "target": "10.0.0.1",
            "port": 161,
            "credential": {"version": "v2c", "community": MASKED_PASSWORD},
            "task_id": system_task.id,
        },
        format="json",
    )
    force_authenticate(request, user=superuser)

    response = CollectToolViewSet.as_view({"post": "execute"})(request)
    data = _body(response)["data"]

    assert response.status_code == 200
    assert data["status"] == "error"
    assert data["result"]["stage"] == "param"
    enqueue.assert_not_called()
