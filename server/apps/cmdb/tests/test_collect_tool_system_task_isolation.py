import json

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.constants.constants import PERMISSION_TASK, CollectPluginTypes, CollectRunStatusType
from apps.cmdb.models.collect_model import CollectModels
from apps.cmdb.nats.nats import _get_collect_task_queryset, get_cmdb_collect_statistics, get_cmdb_module_data
from apps.cmdb.services.collect_tool_service import MASKED_PASSWORD
from apps.cmdb.views.collect_tool import CollectToolViewSet
from apps.cmdb.views.config_file import ConfigFileVersionViewSet
from apps.core.exceptions.base_app_exception import BaseAppException


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
        instances=[{"_id": "host-1", "ip_addr": "10.0.0.1", "model_id": "host"}],
        credential={"version": "v2c", "community": "secret"},
        exec_status=CollectRunStatusType.RUNNING,
        task_id="exec-system-1",
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
def test_collect_tool_masked_execute_cannot_restore_node_mgmt_system_task_credentials(superuser, system_task, monkeypatch, mocker):
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


@pytest.mark.django_db
def test_config_file_receive_result_cannot_mutate_node_mgmt_system_task(superuser, system_task):
    request = APIRequestFactory().post(
        "/config-file/receive_result/",
        {
            "collect_task_id": system_task.id,
            "execution_id": "exec-system-1",
            "instance_id": "host-1",
            "version": "1700000000000",
            "status": "error",
            "error": "callback rejected",
        },
        format="json",
    )
    force_authenticate(request, user=superuser)

    with pytest.raises(BaseAppException, match="配置文件采集任务不存在"):
        ConfigFileVersionViewSet.as_view({"post": "receive_result"})(request)

    system_task.refresh_from_db()
    assert system_task.exec_status == CollectRunStatusType.RUNNING
    assert system_task.collect_data == {}


@pytest.mark.django_db
def test_permission_task_enum_excludes_node_mgmt_system_tasks(system_task):
    visible = CollectModels.objects.create(
        name="普通采集",
        task_type=CollectPluginTypes.HOST,
        model_id="host",
        driver_type="ordinary",
        cycle_value_type="cycle",
        team=[1],
    )

    result = get_cmdb_module_data(PERMISSION_TASK, CollectPluginTypes.HOST, 1, 100, 1)

    assert result == {
        "count": 1,
        "items": [{"id": str(visible.id), "name": "host_普通采集"}],
    }


@pytest.mark.django_db
def test_collect_statistics_queryset_excludes_node_mgmt_system_tasks(system_task):
    queryset = _get_collect_task_queryset({"team": 1})

    assert "is_system" in str(queryset.query.where)


@pytest.mark.django_db
def test_collect_statistics_counts_each_team_exactly():
    team_a = 881001
    team_b = 881002
    CollectModels.objects.create(
        name="team-a-success",
        task_type=CollectPluginTypes.HOST,
        model_id="host-a-success",
        cycle_value_type="cycle",
        team=[team_a],
        is_interval=True,
        exec_status=CollectRunStatusType.SUCCESS,
    )
    CollectModels.objects.create(
        name="team-a-error",
        task_type=CollectPluginTypes.HOST,
        model_id="host-a-error",
        cycle_value_type="cycle",
        team=[team_a],
        exec_status=CollectRunStatusType.ERROR,
    )
    CollectModels.objects.create(
        name="team-b-success",
        task_type=CollectPluginTypes.HOST,
        model_id="host-b-success",
        cycle_value_type="cycle",
        team=[team_b],
        exec_status=CollectRunStatusType.SUCCESS,
    )

    team_a_data = get_cmdb_collect_statistics(user_info={"team": team_a})["data"]
    team_b_data = get_cmdb_collect_statistics(user_info={"team": team_b})["data"]

    assert team_a_data == {
        "task_count": 2,
        "interval_task_count": 1,
        "success_count": 1,
        "error_count": 1,
        "running_count": 0,
        "timeout_count": 0,
        "never_run_count": 0,
        "partial_success_count": 0,
    }
    assert team_b_data == {
        "task_count": 1,
        "interval_task_count": 0,
        "success_count": 1,
        "error_count": 0,
        "running_count": 0,
        "timeout_count": 0,
        "never_run_count": 0,
        "partial_success_count": 0,
    }
