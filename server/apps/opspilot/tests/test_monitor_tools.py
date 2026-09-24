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
        monitor_get_host_resource_snapshot,
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
        monitor_get_host_resource_snapshot,
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
    assert "空矩阵" in query or "无时序" in query
    assert "禁止" in query and ("重试" in query or "换" in query)
    assert "instance_id" in query
    assert "禁止用" in query or "不要用" in query

    instances = tools["monitor_list_object_instances"].description
    assert "第2步" in instances
    assert "主机名" in instances or "名称" in instances or "boxxxxx" in instances
    assert "IP" in instances
    assert "只调一次" in instances
    assert "禁止猜测" in instances or "递增" in instances
    assert "request_user_choice" in instances
    assert "instance_id" in instances
    assert "禁止用 name" in instances or "禁止用实例名" in instances

    objects = tools["monitor_list_objects"].description
    assert "request_user_choice" in objects
    assert "猜" in objects
    assert "已声明" in objects

    metrics = tools["monitor_list_object_metrics"].description
    assert "第3步" in metrics
    assert "keyword" in metrics
    assert "猜测" in metrics or "cpu.util" in metrics


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

    assert result["success"] is True
    assert result["data"] == [{"id": "host"}]
    assert "request_user_choice" in result["_next_step_hint"]
    rpc.monitor_objects.assert_called_once_with(
        user_info={
            "user": "alice",
            "domain": "tenant-a.com",
            "team": 12,
            "include_children": True,
        }
    )


def test_monitor_list_objects_keeps_identity_fields_and_drops_plugin_blobs(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_objects

    rpc = mocker.Mock()
    rpc.monitor_objects.return_value = {
        "result": True,
        "data": [
            {
                "id": "host",
                "name": "Host",
                "type": 1,
                "plugin_config": {"huge": "x" * 50},
                "default_metric": {"promql": "up"},
            }
        ],
    }
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_list_objects.invoke({}, config=_runtime_config())

    assert result["success"] is True
    assert result["data"] == [{"id": "host", "name": "Host", "type": 1}]
    assert "plugin_config" not in result["data"][0]
    assert "request_user_choice" in result["_next_step_hint"]
    assert "Host" in result["_next_step_hint"]


def test_monitor_list_objects_choice_hint_uses_real_type_names(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_objects

    rpc = mocker.Mock()
    rpc.monitor_objects.return_value = {
        "result": True,
        "data": [
            {"id": "12", "name": "Host"},
            {"id": "8", "name": "K8S Pod"},
            {"id": "9", "name": "Redis"},
        ],
    }
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_list_objects.invoke({}, config=_runtime_config())

    hint = result["_next_step_hint"]
    assert "禁止根据名称形态猜测" in hint
    assert "K8s Pod" in hint or "K8S Pod" in hint
    assert "Host" in hint
    assert "Redis" in hint
    assert "single_select" in hint
    assert "text" in hint.lower() or "不要用 text" in hint
    assert "已明确" in hint or "已声明" in hint
    assert "不要 request_user_choice" in hint
    assert result["data"][0]["id"] == "12"


def test_monitor_list_objects_choice_hint_keeps_single_select_for_many_types(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_objects

    rpc = mocker.Mock()
    rpc.monitor_objects.return_value = {
        "result": True,
        "data": [{"id": str(i), "name": f"Type-{i}"} for i in range(10)],
    }
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_list_objects.invoke({}, config=_runtime_config())

    hint = result["_next_step_hint"]
    assert "共 10 类" in hint
    assert "single_select" in hint
    assert "不要用 text" in hint
    assert "Type-0" not in hint


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
                "monitor_obj_id": "12",
                "limit": 20,
                "instance_ids": ["host-1"],
                "level": "critical",
                "alert_type": "threshold",
            },
            "query_latest_active_alerts",
            {
                "query_data": {
                    "monitor_obj_id": "12",
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
        (
            7,
            {"instance_ids": ["host-1", "host-2"]},
            "get_host_resource_snapshot",
            {"instance_ids": ["host-1", "host-2"]},
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
        "host-resource-snapshot",
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
    if rpc_method == "monitor_object_instances":
        rpc_data = [{"id": "h1", "name": "web-01", "instance_id": "h1"}]
    elif rpc_method == "monitor_metrics":
        rpc_data = [{"name": "cpu_usage_total", "display_name": "CPU使用率", "query": "huge"}]
    else:
        rpc_data = {"rpc_method": rpc_method}
    getattr(rpc, rpc_method).return_value = {"result": True, "data": rpc_data}
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = _monitor_tools()[tool_index].invoke(tool_input, config=_runtime_config())

    if rpc_method == "monitor_object_instances":
        assert result["success"] is True
        assert result["data"] == [{"id": "h1", "name": "web-01", "ip": None, "instance_id": "h1"}]
        assert "h1" in result["_next_step_hint"]
        assert "instance_id" in result["_next_step_hint"]
        assert "禁止用 name" in result["_next_step_hint"] or "禁止用实例名" in result["_next_step_hint"]
    elif rpc_method == "monitor_metrics":
        assert result["success"] is True
        assert result["data"] == [{"name": "cpu_usage_total", "display_name": "CPU使用率"}]
        assert "cpu.util" in result["_next_step_hint"]
    else:
        assert result["success"] is True
        assert result["data"] == {"rpc_method": rpc_method}
        if rpc_method == "monitor_objects":
            assert "request_user_choice" in result["_next_step_hint"]
        else:
            assert "_next_step_hint" not in result
    getattr(rpc, rpc_method).assert_called_once_with(
        user_info={
            "user": "alice",
            "domain": "tenant-a.com",
            "team": 12,
            "include_children": True,
        },
        **rpc_kwargs,
    )


def _instance_rpc_rows():
    return [
        {"id": "h1", "name": "web-01", "ip": "10.0.0.1", "instance_id": "h1", "interval": 60},
        {
            "id": "('MTVmOTFiYTM5ODZk',)",
            "name": "local",
            "ip": "10.10.41.149",
            "instance_id": "MTVmOTFiYTM5ODZk",
            "permission": ["View"],
        },
        {"id": "h3", "name": "db-01", "ip": "10.0.0.2"},
    ]


def test_monitor_list_object_instances_filters_keyword_locally(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_object_instances

    rpc = mocker.Mock()
    rpc.monitor_object_instances.return_value = {"result": True, "data": _instance_rpc_rows()}
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_list_object_instances.invoke(
        {"monitor_obj_id": "host", "keyword": "web"},
        config=_runtime_config(),
    )

    assert result["success"] is True
    assert result["data"] == [{"id": "h1", "name": "web-01", "ip": "10.0.0.1", "instance_id": "h1"}]
    assert result["_next_step_hint"].count("h1") >= 1
    assert "instance_id" in result["_next_step_hint"]
    assert "web-01" not in result["_next_step_hint"]
    rpc.monitor_object_instances.assert_called_once_with(
        user_info={
            "user": "alice",
            "domain": "tenant-a.com",
            "team": 12,
            "include_children": True,
        },
        monitor_obj_id="host",
    )


def test_monitor_list_object_instances_matches_ip_keyword(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_object_instances

    rpc = mocker.Mock()
    rpc.monitor_object_instances.return_value = {"result": True, "data": _instance_rpc_rows()}
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_list_object_instances.invoke(
        {"monitor_obj_id": "host", "keyword": "10.10.41.149"},
        config=_runtime_config(),
    )

    assert result["success"] is True
    assert result["data"] == [
        {
            "id": "MTVmOTFiYTM5ODZk",
            "name": "local",
            "ip": "10.10.41.149",
            "instance_id": "MTVmOTFiYTM5ODZk",
        }
    ]
    assert "MTVmOTFiYTM5ODZk" in result["_next_step_hint"]
    assert "local" not in result["_next_step_hint"]


def test_monitor_list_object_instances_matches_asset_ip_fact(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_object_instances

    rpc = mocker.Mock()
    rpc.monitor_object_instances.return_value = {
        "result": True,
        "data": [
            {"id": "h2", "name": "local", "ip": None, "summary_facts": {"asset.ip": "10.10.41.149"}},
            {"id": "h3", "name": "db-01", "ip": "10.0.0.2"},
        ],
    }
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_list_object_instances.invoke(
        {"monitor_obj_id": "host", "keyword": "10.10.41.149"},
        config=_runtime_config(),
    )

    assert result["success"] is True
    assert result["data"] == [{"id": "h2", "name": "local", "ip": None}]
    assert "h2" in result["_next_step_hint"]


def test_monitor_list_object_instances_keeps_ip_without_keyword(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_object_instances

    rpc = mocker.Mock()
    rpc.monitor_object_instances.return_value = {"result": True, "data": _instance_rpc_rows()}
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_list_object_instances.invoke(
        {"monitor_obj_id": "host"},
        config=_runtime_config(),
    )

    assert result["success"] is True
    assert result["data"] == [
        {"id": "h1", "name": "web-01", "ip": "10.0.0.1", "instance_id": "h1"},
        {
            "id": "MTVmOTFiYTM5ODZk",
            "name": "local",
            "ip": "10.10.41.149",
            "instance_id": "MTVmOTFiYTM5ODZk",
        },
        {"id": "h3", "name": "db-01", "ip": "10.0.0.2"},
    ]
    assert "MTVmOTFiYTM5ODZk" in result["_next_step_hint"]
    assert "web-01" not in result["_next_step_hint"]


def test_monitor_list_object_instances_unmatched_keyword_is_terminal(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_object_instances

    rpc = mocker.Mock()
    rpc.monitor_object_instances.return_value = {
        "result": True,
        "data": [
            {"id": "h1", "name": "id-mismatch-sz-app-01", "ip": "10.88.1.11", "instance_id": "h1"},
            {"id": "h2", "name": "id-mismatch-other-01", "ip": "10.88.9.91", "instance_id": "h2"},
        ],
    }
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_list_object_instances.invoke(
        {"monitor_obj_id": "12", "keyword": "not-a-host"},
        config=_runtime_config(),
    )

    assert result["success"] is True
    assert result["data"] == []
    assert result["keyword"] == "not-a-host"
    assert "不要把空列表当成最终结论" in result["message"]
    assert "request_user_choice" in result["message"]
    assert "已声明" in result["message"]
    assert "request_user_choice" in result["_next_step_hint"]
    assert "已声明" in result["_next_step_hint"] or "不要再问" in result["_next_step_hint"]
    assert "必须立即" not in result["_next_step_hint"]
    assert "id-mismatch-sz-app-01" in result["available_names"]
    rpc.monitor_object_instances.assert_called_once()


def test_monitor_list_object_instances_hint_requires_listed_instance_id(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_object_instances

    rpc = mocker.Mock()
    rpc.monitor_object_instances.return_value = {
        "result": True,
        "data": [
            {
                "id": "MDw4DkyHjgDTc1",
                "name": "fusion-collector-default",
                "ip": "172.18.0.20",
                "instance_id": "MDw4DkyHjgDTc1",
            }
        ],
    }
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_list_object_instances.invoke(
        {"monitor_obj_id": "12", "keyword": "fusion-collector-default"},
        config=_runtime_config(),
    )

    assert result["data"][0]["instance_id"] == "MDw4DkyHjgDTc1"
    hint = result["_next_step_hint"]
    assert "MDw4DkyHjgDTc1" in hint
    assert "fusion-collector-default" not in hint
    assert "172.18.0.20" not in hint
    assert "instance_id" in hint
    assert "monitor_query_metric_data" in hint
    assert "禁止用 name" in hint or "禁止用实例名" in hint


def test_monitor_list_object_instances_coerces_non_list_payload(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_object_instances

    rpc = mocker.Mock()
    rpc.monitor_object_instances.return_value = {"result": True, "data": {}}
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_list_object_instances.invoke(
        {"monitor_obj_id": "14", "keyword": "sz-app-01"},
        config=_runtime_config(),
    )

    assert result["success"] is True
    assert result["data"] == []
    assert "没有实例" in result["message"]
    assert "request_user_choice" in result["message"]
    assert "已声明" in result["message"]
    assert "request_user_choice" in result["_next_step_hint"]
    assert "已声明" in result["_next_step_hint"] or "不要再问" in result["_next_step_hint"]
    assert "必须立即" not in result["_next_step_hint"]
    assert "禁止猜测" in result["message"] or "猜测其他 ID" in result["message"]


def test_monitor_list_object_instances_reads_nested_items(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.objects import monitor_list_object_instances

    rpc = mocker.Mock()
    rpc.monitor_object_instances.return_value = {
        "result": True,
        "data": {"items": [{"id": "h1", "name": "id-mismatch-sz-app-01", "ip": "10.88.1.11", "instance_id": "h1"}]},
    }
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_list_object_instances.invoke(
        {"monitor_obj_id": "12", "keyword": "sz-app-01"},
        config=_runtime_config(),
    )

    assert result["success"] is True
    assert result["data"] == [
        {
            "id": "h1",
            "name": "id-mismatch-sz-app-01",
            "ip": "10.88.1.11",
            "instance_id": "h1",
        }
    ]
    assert "h1" in result["_next_step_hint"]
    assert "id-mismatch-sz-app-01" not in result["_next_step_hint"]


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
        (6, {"start": 100, "end": 200}, "monitor_obj_id is required"),
        (6, {"monitor_obj_id": "host", "end": 200}, "start is required"),
        (6, {"monitor_obj_id": "host", "start": 100}, "end is required"),
        (7, {}, "instance_ids is required"),
    ],
)
def test_monitor_tools_keep_existing_business_required_validation(mocker, tool_index, tool_input, error):
    tool = _monitor_tools()[tool_index]
    rpc_call = mocker.patch(f"{tool.func.__module__}.call_monitor_rpc")

    result = tool.invoke(tool_input, config=_runtime_config())

    assert result["success"] is False
    assert result["error"] == error
    assert "request_user_choice" in result["_next_step_hint"]
    assert "禁止编造 uvx" in result["_next_step_hint"]
    rpc_call.assert_not_called()


def test_monitor_list_object_metrics_filters_cpu_and_forbids_guessing(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.metrics import monitor_list_object_metrics

    rpc = mocker.Mock()
    rpc.monitor_metrics.return_value = {
        "result": True,
        "data": [
            {"name": "cpu_usage_total", "display_name": "CPU使用率", "unit": "percent", "query": "huge"},
            {"name": "mem_used", "display_name": "内存使用量", "unit": "bytes", "description": "RSS"},
            {"name": "cpu_usage_iowait_total", "display_name": "CPU等待IO占比", "unit": "percent"},
        ],
    }
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_list_object_metrics.invoke(
        {"monitor_obj_id": "12", "keyword": "CPU"},
        config=_runtime_config(),
    )

    assert result["success"] is True
    names = [item["name"] for item in result["data"]]
    assert names == ["cpu_usage_total", "cpu_usage_iowait_total"]
    assert "query" not in result["data"][0]
    hint = result["_next_step_hint"]
    assert "cpu_usage_total" in hint
    assert "cpu.util" in hint
    assert "不要 request_user_choice" in hint
    assert "手填" in hint or "猜测" in hint


def test_monitor_list_object_metrics_empty_keyword_keeps_catalog_hint(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.metrics import monitor_list_object_metrics

    rpc = mocker.Mock()
    rpc.monitor_metrics.return_value = {
        "result": True,
        "data": [{"name": "mem_used", "display_name": "内存使用量", "unit": "bytes"}],
    }
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_list_object_metrics.invoke({"monitor_obj_id": "12"}, config=_runtime_config())

    assert [item["name"] for item in result["data"]] == ["mem_used"]
    assert "keyword" in result["_next_step_hint"]
    assert "cpu.util" in result["_next_step_hint"]


def test_monitor_query_metric_data_empty_matrix_is_terminal(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.metrics import monitor_query_metric_data

    rpc = mocker.Mock()
    rpc.query_monitor_data_by_metric.return_value = {
        "result": True,
        "data": {
            "status": "success",
            "data": {"resultType": "matrix", "result": []},
            "stats": {"seriesMatched": "0", "executionTimeMs": 0},
        },
    }
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_query_metric_data.invoke(
        {"monitor_obj_id": "12", "metric": "cpu_usage_total", "instance_ids": ["fusion-collector-default"]},
        config=_runtime_config(),
    )

    assert result["success"] is True
    hint = result["_next_step_hint"]
    assert "有效结论" in hint
    assert "禁止" in hint
    assert "instance_ids" in hint
    assert "dimensions" in hint
    assert "重试" in hint
    assert "request_user_choice" not in hint


def test_monitor_query_metric_data_with_series_does_not_stop_as_empty(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.metrics import monitor_query_metric_data

    rpc = mocker.Mock()
    rpc.query_monitor_data_by_metric.return_value = {
        "result": True,
        "data": {
            "status": "success",
            "data": {"resultType": "matrix", "result": [{"metric": {"instance": "web-1"}, "values": [[1, "1"]]}]},
            "stats": {"seriesMatched": "1"},
        },
    }
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_query_metric_data.invoke(
        {"monitor_obj_id": "12", "metric": "cpu_usage_total", "instance_ids": ["web-1"]},
        config=_runtime_config(),
    )

    assert result["success"] is True
    assert "_next_step_hint" not in result


def test_monitor_query_metric_data_unknown_metric_lists_catalog_not_user(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.metrics import monitor_query_metric_data

    rpc = mocker.Mock()
    rpc.query_monitor_data_by_metric.return_value = {"result": False, "data": [], "message": "监控对象或指标不存在"}
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_query_metric_data.invoke(
        {"monitor_obj_id": "12", "metric": "cpu.util", "instance_ids": ["web-1"]},
        config=_runtime_config(),
    )

    assert result["success"] is False
    assert result["error"] == "监控对象或指标不存在"
    hint = result["_next_step_hint"]
    assert "monitor_list_object_metrics" in hint
    assert "cpu.util" in hint
    assert "不要 request_user_choice" in hint


def test_monitor_query_metric_data_defaults_last_hour_window(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.metrics import monitor_query_metric_data

    mocker.patch.object(utils.time, "time", return_value=1_789_200_000.0)
    rpc = mocker.Mock()
    rpc.query_monitor_data_by_metric.return_value = {"result": True, "data": {"series": []}}
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_query_metric_data.invoke(
        {"monitor_obj_id": "12", "metric": "cpu_usage_user_total", "instance_ids": ["web-1"]},
        config=_runtime_config(),
    )

    assert result["success"] is True
    assert "有效结论" in result["_next_step_hint"]
    query_data = rpc.query_monitor_data_by_metric.call_args.kwargs["query_data"]
    assert query_data["start"] == 1_789_200_000_000 - 3_600_000
    assert query_data["end"] == 1_789_200_000_000
    assert query_data["instance_ids"] == ["web-1"]


def test_monitor_query_metric_data_converts_unix_seconds_to_ms(mocker):
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.metrics import monitor_query_metric_data

    rpc = mocker.Mock()
    rpc.query_monitor_data_by_metric.return_value = {"result": True, "data": {"series": []}}
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    result = monitor_query_metric_data.invoke(
        {
            "monitor_obj_id": "12",
            "metric": "cpu_usage_user_total",
            "start": 1_789_200_000,
            "end": 1_789_203_600,
            "instance_ids": ["web-1"],
        },
        config=_runtime_config(),
    )

    assert result["success"] is True
    query_data = rpc.query_monitor_data_by_metric.call_args.kwargs["query_data"]
    assert query_data["start"] == 1_789_200_000_000
    assert query_data["end"] == 1_789_203_600_000


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


def test_monitor_list_active_alerts_rejects_non_digit_monitor_obj_id(mocker):
    """CMDB monitor_id / 实例标识不得塞进 monitor_obj_id，避免 Field 'id' expected a number。"""
    from apps.opspilot.metis.llm.tools.monitor import utils
    from apps.opspilot.metis.llm.tools.monitor.alerts import monitor_list_active_alerts

    rpc = mocker.Mock()
    mocker.patch.object(utils, "MonitorOperationAnaRpc", return_value=rpc)

    for bad in ("MTVmOTFiYTM5ODZk", "1_10.10.41.149_80", "host", "nginx"):
        out = monitor_list_active_alerts.invoke(
            {"monitor_obj_id": bad, "instance_ids": ["1_10.10.41.149_80"]},
            config=_runtime_config(),
        )
        assert out["success"] is False, bad
        assert "必须是监控对象类型的数字 id" in out["error"], bad
        assert "instance_ids" in out["error"], bad

    rpc.query_latest_active_alerts.assert_not_called()

    rpc.query_latest_active_alerts.return_value = {"result": True, "data": []}
    ok = monitor_list_active_alerts.invoke(
        {"monitor_obj_id": "12", "instance_ids": ["1_10.10.41.149_80"]},
        config=_runtime_config(),
    )
    assert ok["success"] is True
    rpc.query_latest_active_alerts.assert_called_once()
