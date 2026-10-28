import json

import pytest
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.cmdb.constants.constants import PERMISSION_TASK, CollectDriverTypes, CollectPluginTypes, CollectRunStatusType
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


ORG1_SNMP_COMMUNITY = "org1-snmp-community-x7k"
TASK_ACCESS_DENIED = "抱歉！您没有访问该采集任务的权限"
CREDENTIAL_RESTORE_DENIED = "无法恢复原始凭据，请确认原任务可访问，或手动重新输入凭据"


@pytest.fixture
def org_scoped_user(authenticated_user):
    authenticated_user.is_superuser = False
    authenticated_user.domain = "domain.com"
    authenticated_user.permission = {"cmdb": {"collection_tool-View", "collection_tool-Execute"}}
    authenticated_user.rules = {}
    return authenticated_user


@pytest.fixture
def org1_snmp_task():
    return CollectModels.objects.create(
        name="组织1 SNMP采集",
        task_type=CollectPluginTypes.SNMP,
        model_id="network",
        driver_type=CollectDriverTypes.PROTOCOL,
        cycle_value_type="cycle",
        team=[1],
        is_system=False,
        ip_range="10.1.0.8",
        access_point=[{"id": "node-1"}],
        credential={"version": "v2c", "community": ORG1_SNMP_COMMUNITY},
    )


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


def _rendered_text(response):
    if hasattr(response, "render") and not getattr(response, "is_rendered", False):
        response.render()
    return response.content.decode()


def _team_request(method, path, team_id, data=None):
    factory = APIRequestFactory()
    if method == "get":
        request = factory.get(path, data or {})
    else:
        request = factory.post(path, data or {}, format="json")
    request.COOKIES["current_team"] = str(team_id)
    return request


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
def test_collect_tool_empty_rules_cannot_cross_team_to_restore_snmp_credential(org_scoped_user, org1_snmp_task, monkeypatch, mocker):
    monkeypatch.setattr("apps.cmdb.views.collect.get_permission_rules", lambda *args, **kwargs: {})
    mocker.patch(
        "apps.cmdb.views.collect_tool.CollectToolService.resolve_access_point",
        return_value="default_stargazer",
    )
    enqueue = mocker.patch("apps.cmdb.views.collect_tool.CollectToolService.enqueue_debug_task")

    prefill_request = _team_request(
        "get",
        "/collect_tool/prefill/",
        2,
        {"task_id": org1_snmp_task.id, "protocol": "snmp"},
    )
    force_authenticate(prefill_request, user=org_scoped_user)
    prefill_response = CollectToolViewSet.as_view({"get": "prefill"})(prefill_request)
    prefill_body = _body(prefill_response)

    assert prefill_response.status_code == 403
    assert prefill_body["message"] == TASK_ACCESS_DENIED
    assert ORG1_SNMP_COMMUNITY not in _rendered_text(prefill_response)

    execute_request = _team_request(
        "post",
        "/collect_tool/execute/",
        2,
        {
            "protocol": "snmp",
            "action": "test_connection",
            "access_point_id": "node-1",
            "target": "10.1.0.8",
            "port": 161,
            "credential": {"version": "v2c", "community": MASKED_PASSWORD},
            "task_id": org1_snmp_task.id,
        },
    )
    force_authenticate(execute_request, user=org_scoped_user)
    execute_response = CollectToolViewSet.as_view({"post": "execute"})(execute_request)
    execute_data = _body(execute_response)["data"]

    assert execute_response.status_code == 200
    assert execute_data["result"]["summary"] == CREDENTIAL_RESTORE_DENIED
    assert ORG1_SNMP_COMMUNITY not in _rendered_text(execute_response)
    enqueue.assert_not_called()

    same_team_prefill = _team_request(
        "get",
        "/collect_tool/prefill/",
        1,
        {"task_id": org1_snmp_task.id, "protocol": "snmp"},
    )
    force_authenticate(same_team_prefill, user=org_scoped_user)
    same_team_prefill_response = CollectToolViewSet.as_view({"get": "prefill"})(same_team_prefill)
    same_team_prefill_body = _body(same_team_prefill_response)

    assert same_team_prefill_body.get("message") != TASK_ACCESS_DENIED

    same_team_execute = _team_request(
        "post",
        "/collect_tool/execute/",
        1,
        {
            "protocol": "snmp",
            "action": "test_connection",
            "access_point_id": "node-1",
            "target": "10.1.0.8",
            "port": 161,
            "credential": {"version": "v2c", "community": MASKED_PASSWORD},
            "task_id": org1_snmp_task.id,
        },
    )
    force_authenticate(same_team_execute, user=org_scoped_user)
    same_team_execute_response = CollectToolViewSet.as_view({"post": "execute"})(same_team_execute)

    assert same_team_execute_response.status_code == 200
    enqueue.assert_called_once()


@pytest.mark.django_db
def test_collect_tool_vault_execute_queues_reference_without_page_secrets(superuser, monkeypatch, mocker):
    monkeypatch.setattr("apps.cmdb.views.collect_tool.get_current_team_from_request", lambda request: 1)
    mocker.patch("apps.cmdb.views.collect_tool.CollectToolService.resolve_access_point", return_value="default_stargazer")
    enqueue = mocker.patch("apps.cmdb.views.collect_tool.CollectToolService.enqueue_debug_task")
    request = APIRequestFactory().post(
        "/collect_tool/execute/",
        {
            "protocol": "snmp",
            "action": "test_connection",
            "access_point_id": "node-1",
            "target": "10.0.0.1",
            "port": 161,
            "credential": {
                "credential_source": "vault",
                "vault_credential_id": "crd-1",
                "community": "page-secret",
                "authkey": "page-secret",
                "vault_actor_context": {"username": "forged"},
            },
        },
        format="json",
    )
    force_authenticate(request, user=superuser)
    response = CollectToolViewSet.as_view({"post": "execute"})(request)
    assert response.status_code == 200
    assert _body(response)["data"]["status"] == "pending"
    queued = enqueue.call_args.args[1]
    assert queued["credential"] == {"credential_source": "vault", "vault_credential_id": "crd-1"}
    assert queued["vault_actor_context"] == {"username": superuser.username, "domain": superuser.domain, "current_team": 1}
    assert "page-secret" not in str(queued)


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
