import pytest

CALLER_IDENTITY = {
    "username": "alice",
    "domain": "tenant-a.com",
    "team_id": 12,
    "include_children": True,
}


def _runtime_config(identity=CALLER_IDENTITY, **legacy_configurable):
    configurable = dict(legacy_configurable)
    if identity is not None:
        configurable["caller_identity"] = identity
    return {"configurable": configurable}


def _monitor_tools():
    from apps.opspilot.metis.llm.tools.monitor import (
        monitor_list_active_alerts,
        monitor_list_instance_metrics,
        monitor_list_object_instances,
        monitor_list_object_metrics,
        monitor_list_objects,
        monitor_query_alert_segments,
        monitor_query_metric_data,
    )

    return [
        monitor_list_objects,
        monitor_list_object_instances,
        monitor_list_object_metrics,
        monitor_list_instance_metrics,
        monitor_query_metric_data,
        monitor_list_active_alerts,
        monitor_query_alert_segments,
    ]


def test_monitor_tool_descriptions_guide_host_metric_queries():
    """规划器只看短描述；前 120 字须能表达主机 CPU 场景与调用步骤。"""
    tools = {tool.name: tool for tool in _monitor_tools()}
    for name, tool in tools.items():
        text = " ".join((tool.description or "").split())
        head = text[:120]
        assert "主机" in head, name
        assert "CPU" in head or "告警" in head, name

    objects = tools["monitor_list_objects"].description
    assert "第1步" in objects
    assert "monitor_obj_id" in objects
    assert "SSH" in objects or "top" in objects or "htop" in objects

    query = tools["monitor_query_metric_data"].description
    assert "第4步" in query
    assert "CPU" in query
    assert "instance_ids" in query
    assert "top" in query or "htop" in query or "SSH" in query

    instances = tools["monitor_list_object_instances"].description
    assert "第2步" in instances
    assert "主机名" in instances or "名称" in instances or "boxxxxx" in instances


def test_monitor_constructor_has_no_identity_params():
    from apps.opspilot.metis.llm.tools.monitor import CONSTRUCTOR_PARAMS

    assert CONSTRUCTOR_PARAMS == []


@pytest.mark.parametrize("monitor_tool", _monitor_tools(), ids=lambda monitor_tool: monitor_tool.name)
def test_monitor_tool_schemas_hide_runtime_and_legacy_identity_fields(monitor_tool):
    hidden_fields = {"username", "password", "domain", "team_id", "caller_identity", "config"}

    assert hidden_fields.isdisjoint(monitor_tool.args)


def test_monitor_legacy_authentication_helpers_are_removed():
    from apps.opspilot.metis.llm.tools.monitor import utils

    assert not hasattr(utils, "authenticate_monitor_user")
    assert not hasattr(utils, "resolve_monitor_runtime_params")


def test_resolve_monitor_user_info_builds_rpc_identity_from_runtime_snapshot():
    from apps.opspilot.metis.llm.tools.monitor.utils import resolve_monitor_user_info

    assert resolve_monitor_user_info(_runtime_config()) == {
        "user": "alice",
        "domain": "tenant-a.com",
        "team": 12,
        "include_children": True,
    }


@pytest.mark.parametrize(
    "identity,error",
    [
        ([], "caller_identity must be a dictionary"),
        ({"username": "", "domain": "tenant-a.com", "team_id": 12, "include_children": False}, "username"),
        ({"username": "   ", "domain": "tenant-a.com", "team_id": 12, "include_children": False}, "username"),
        ({"username": True, "domain": "tenant-a.com", "team_id": 12, "include_children": False}, "username"),
        ({"username": "alice", "domain": "", "team_id": 12, "include_children": False}, "domain"),
        ({"username": "alice", "domain": "   ", "team_id": 12, "include_children": False}, "domain"),
        ({"username": "alice", "domain": False, "team_id": 12, "include_children": False}, "domain"),
    ],
)
def test_resolve_monitor_user_info_rejects_malformed_identity_fields(identity, error):
    from apps.opspilot.metis.llm.tools.monitor.utils import resolve_monitor_user_info

    with pytest.raises(ValueError, match=error):
        resolve_monitor_user_info(_runtime_config(identity))


@pytest.mark.parametrize("team_id", [True, "12", 0, -1, 1.5])
def test_resolve_monitor_user_info_requires_strict_positive_integer_team_id(team_id):
    from apps.opspilot.metis.llm.tools.monitor.utils import resolve_monitor_user_info

    identity = {**CALLER_IDENTITY, "team_id": team_id}

    with pytest.raises(ValueError, match="team_id must be a positive integer"):
        resolve_monitor_user_info(_runtime_config(identity))


@pytest.mark.parametrize("include_children", [None, 0, 1, "false", []])
def test_resolve_monitor_user_info_requires_boolean_include_children(include_children):
    from apps.opspilot.metis.llm.tools.monitor.utils import resolve_monitor_user_info

    identity = {**CALLER_IDENTITY, "include_children": include_children}

    with pytest.raises(ValueError, match="include_children must be a boolean"):
        resolve_monitor_user_info(_runtime_config(identity))


def test_monitor_without_snapshot_reports_unsupported_trigger_and_never_starts_rpc(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_objects

    rpc_cls = mocker.patch.object(utils, "MonitorOperationAnaRpc")

    result = monitor_list_objects.invoke(
        {},
        config=_runtime_config(
            None,
            username="legacy-user",
            password="legacy-password",
            domain="legacy.example",
            team_id=99,
        ),
    )

    assert result["success"] is False
    assert "监控工具仅支持已登录的交互式 HTTP 调用" in result["error"]
    assert "caller_identity" in result["error"]
    assert "无法使用监控工具" in result["error"]
    rpc_cls.assert_not_called()


@pytest.mark.parametrize(
    ("configurable", "expected_source"),
    [
        ({"entry_type": "celery", "trigger_type": "unattended"}, "Celery 定时任务"),
        ({"entry_type": "nats", "trigger_type": "third_party"}, "NATS 触发"),
        ({"entry_type": "dingtalk", "trigger_type": "third_party"}, "钉钉"),
        ({"entry_type": "enterprise_wechat_aibot", "trigger_type": "third_party"}, "企业微信智能机器人"),
        ({"trigger_type": "unattended"}, "定时任务/无人值守触发"),
        ({"trigger_type": "third_party"}, "第三方渠道触发"),
        ({}, "当前触发方式"),
    ],
)
def test_monitor_missing_identity_error_names_non_a_trigger_source(configurable, expected_source, mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_objects

    rpc_cls = mocker.patch.object(utils, "MonitorOperationAnaRpc")
    result = monitor_list_objects.invoke({}, config={"configurable": dict(configurable)})

    assert result["success"] is False
    assert expected_source in result["error"]
    assert "未提供调用方身份快照" in result["error"]
    rpc_cls.assert_not_called()


def test_legacy_configurable_and_model_fields_cannot_override_snapshot(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_objects

    rpc = mocker.Mock()
    rpc.monitor_objects.return_value = {"result": True, "data": [{"id": "host"}]}
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_list_objects.invoke(
        {
            "username": "model-user",
            "password": "model-password",
            "domain": "model.example",
            "team_id": 777,
            "caller_identity": {
                "username": "model-user",
                "domain": "model.example",
                "team_id": 777,
                "include_children": False,
            },
            "config": {
                "configurable": {
                    "caller_identity": {
                        "username": "model-user",
                        "domain": "model.example",
                        "team_id": 777,
                        "include_children": False,
                    }
                }
            },
        },
        config=_runtime_config(
            username="legacy-user",
            password="legacy-password",
            domain="legacy.example",
            team_id=99,
        ),
    )

    assert result == {"success": True, "data": [{"id": "host"}]}
    rpc.monitor_objects.assert_called_once_with(
        user_info={
            "user": "alice",
            "domain": "tenant-a.com",
            "team": 12,
            "include_children": True,
        }
    )


@pytest.mark.parametrize(
    "tool_index,tool_input,rpc_method,rpc_kwargs",
    [
        (0, {}, "monitor_objects", {}),
        (1, {"monitor_obj_id": "host"}, "monitor_object_instances", {"monitor_obj_id": "host"}),
        (2, {"monitor_obj_id": "host"}, "monitor_metrics", {"monitor_obj_id": "host"}),
        (
            3,
            {
                "monitor_obj_id": "host",
                "instance_id": "host-1",
                "only_with_data": True,
                "lookback": "6h",
                "page": 2,
                "page_size": 25,
            },
            "monitor_instance_metrics",
            {
                "query_data": {
                    "monitor_obj_id": "host",
                    "instance_id": "host-1",
                    "only_with_data": True,
                    "lookback": "6h",
                    "page": 2,
                    "page_size": 25,
                }
            },
        ),
        (
            4,
            {
                "monitor_obj_id": "host",
                "metric": "cpu_usage",
                "start": 100,
                "end": 200,
                "step": "1m",
                "instance_ids": ["host-1"],
                "dimensions": {"cpu": "0"},
            },
            "query_monitor_data_by_metric",
            {
                "query_data": {
                    "monitor_obj_id": "host",
                    "metric": "cpu_usage",
                    "start": 100,
                    "end": 200,
                    "step": "1m",
                    "instance_ids": ["host-1"],
                    "dimensions": {"cpu": "0"},
                }
            },
        ),
        (
            5,
            {
                "monitor_obj_id": "host",
                "limit": 20,
                "instance_ids": ["host-1"],
                "level": "critical",
                "alert_type": "threshold",
            },
            "query_latest_active_alerts",
            {
                "query_data": {
                    "monitor_obj_id": "host",
                    "limit": 20,
                    "instance_ids": ["host-1"],
                    "level": "critical",
                    "alert_type": "threshold",
                }
            },
        ),
        (
            6,
            {
                "monitor_obj_id": "host",
                "start": 100,
                "end": 200,
                "instance_ids": ["host-1"],
                "status": "closed",
                "level": "warning",
                "alert_type": "threshold",
                "page": 3,
                "page_size": 50,
            },
            "query_monitor_alert_segments",
            {
                "query_data": {
                    "monitor_obj_id": "host",
                    "start": 100,
                    "end": 200,
                    "instance_ids": ["host-1"],
                    "status": "closed",
                    "level": "warning",
                    "alert_type": "threshold",
                    "page": 3,
                    "page_size": 50,
                }
            },
        ),
    ],
    ids=[
        "list-objects",
        "list-object-instances",
        "list-object-metrics",
        "list-instance-metrics",
        "query-metric-data",
        "list-active-alerts",
        "query-alert-segments",
    ],
)
def test_monitor_tools_map_business_arguments_to_existing_rpc_methods(
    mocker,
    tool_index,
    tool_input,
    rpc_method,
    rpc_kwargs,
):
    from apps.opspilot.metis.llm.tools.monitor import utils

    rpc = mocker.Mock()
    getattr(rpc, rpc_method).return_value = {"result": True, "data": {"rpc_method": rpc_method}}
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = _monitor_tools()[tool_index].invoke(tool_input, config=_runtime_config())

    assert result == {"success": True, "data": {"rpc_method": rpc_method}}
    getattr(rpc, rpc_method).assert_called_once_with(
        user_info={
            "user": "alice",
            "domain": "tenant-a.com",
            "team": 12,
            "include_children": True,
        },
        **rpc_kwargs,
    )


def test_monitor_call_rpc_preserves_monitor_error_response(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils

    rpc = mocker.Mock()
    rpc.monitor_objects.return_value = {"result": False, "message": "monitor denied"}
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    assert utils.call_monitor_rpc("monitor_objects", _runtime_config()) == {
        "success": False,
        "error": "monitor denied",
    }


def test_monitor_call_rpc_wraps_rpc_exception(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils

    rpc = mocker.Mock()
    rpc.monitor_objects.side_effect = RuntimeError("rpc down")
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = utils.call_monitor_rpc("monitor_objects", _runtime_config())

    assert result["success"] is False
    assert "rpc down" in result["error"]


@pytest.mark.parametrize(
    "tool_index,tool_input,error",
    [
        (1, {"monitor_obj_id": ""}, "monitor_obj_id is required"),
        (2, {"monitor_obj_id": ""}, "monitor_obj_id is required"),
        (3, {"monitor_obj_id": "", "instance_id": "host-1"}, "monitor_obj_id is required"),
        (3, {"monitor_obj_id": "host", "instance_id": ""}, "instance_id is required"),
        (4, {"metric": "cpu", "start": 100, "end": 200}, "monitor_obj_id is required"),
        (4, {"monitor_obj_id": "host", "start": 100, "end": 200}, "metric is required"),
        (4, {"monitor_obj_id": "host", "metric": "cpu", "end": 200}, "start is required"),
        (4, {"monitor_obj_id": "host", "metric": "cpu", "start": 100}, "end is required"),
        (6, {"start": 100, "end": 200}, "monitor_obj_id is required"),
        (6, {"monitor_obj_id": "host", "end": 200}, "start is required"),
        (6, {"monitor_obj_id": "host", "start": 100}, "end is required"),
    ],
)
def test_monitor_tools_keep_existing_business_required_validation(mocker, tool_index, tool_input, error):
    tool = _monitor_tools()[tool_index]
    rpc_call = mocker.patch(f"{tool.func.__module__}.call_monitor_rpc")

    result = tool.invoke(tool_input, config=_runtime_config())

    assert result == {"success": False, "error": error}
    rpc_call.assert_not_called()


def test_builtin_monitor_tool_descriptor_shape():
    """The builtin descriptor keeps the langchain URL and seven sub-tools."""
    from apps.core.utils.loader import LanguageLoader
    from apps.opspilot.services import builtin_tools

    loader = LanguageLoader("opspilot")
    descriptor = builtin_tools.build_builtin_monitor_tool(loader)

    assert descriptor["id"] == builtin_tools.BUILTIN_MONITOR_TOOL_ID
    assert descriptor["name"] == "monitor"
    assert descriptor["is_build_in"] is True
    assert descriptor["params"]["url"] == "langchain:monitor"
    sub_names = {tool["name"] for tool in descriptor["tools"]}
    assert "CONSTRUCTOR_PARAMS" not in sub_names
    assert sub_names == {tool.name for tool in _monitor_tools()}
