import pytest
from unittest.mock import patch, MagicMock
from apps.alerts.action.handlers.job import JobActionHandler
from apps.alerts.action.exceptions import ConfigError, TargetError


def _alert(team=None):
    a = MagicMock()
    a.alert_id = "A1"; a.labels = {"ip": "10.0.0.5", "service": "nginx"}
    a.enrichment = {}; a.title = "t"; a.level = "1"; a.status = "unassigned"
    a.resource_id = a.resource_name = a.resource_type = a.item = a.source_name = None
    a.content = "c"
    a.team = [1] if team is None else team
    return a


def _rule(team=[1]):
    r = MagicMock()
    r.team = team
    r.name = "重启nginx"
    r.action_config = {
        "script_id": 42,
        "target_binding": {"source": "node_mgmt", "match_by": "ip", "host_field": "labels.ip"},
        "param_bindings": [{"name": "service", "from": "field", "value": "labels.service"}],
    }
    return r


SCRIPT = {"id": 42, "name": "重启nginx", "script_type": "shell", "content": "echo {{service}}",
          "params": [{"name": "service", "default": ""}], "timeout": 300}


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_bare_host_field_resolved_under_labels(mock_target, mock_job):
    """目标主机字段写裸字段名(ip_addr) → 后端默认从 labels.ip_addr 取值。"""
    mock_target.return_value = {"node_id": "n1", "name": "h", "ip": "10.0.0.9",
                                "os": "linux", "cloud_region_id": 1}
    mock_job.return_value.get_script.return_value = SCRIPT
    mock_job.return_value.job_script_execute.return_value = {"result": True, "data": {"task_id": 1}}
    rule = _rule()
    rule.action_config["target_binding"]["host_field"] = "ip_addr"
    alert = _alert()
    alert.labels = {"ip_addr": "10.0.0.9"}

    JobActionHandler().execute(rule, alert, MagicMock())

    # resolve_node_target 第一个位置参 = 解析出的主机值
    assert mock_target.call_args[0][0] == "10.0.0.9"


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_execute_success_builds_node_mgmt_payload(mock_target, mock_job):
    mock_target.return_value = {"node_id": "n1", "name": "h", "ip": "10.0.0.5",
                                "os": "linux", "cloud_region_id": 1}
    mock_job.return_value.get_script.return_value = SCRIPT
    mock_job.return_value.job_script_execute.return_value = {"result": True, "data": {"task_id": 4821}}
    execution = MagicMock()

    JobActionHandler().execute(_rule(), _alert(), execution)

    payload = mock_job.return_value.job_script_execute.call_args[0][0]
    assert payload["target_source"] == "node_mgmt"
    assert payload["target_list"] == [{"node_id": "n1", "name": "h", "ip": "10.0.0.5",
                                       "os": "linux", "cloud_region_id": 1}]
    assert payload["script_content"] == "echo {{service}}"
    assert payload["params"] == [{"name": "service", "value": "nginx"}]
    assert payload["callback_url"] is not None
    assert execution.job_task_id == 4821
    assert execution.status == "running"
    execution.save.assert_called()


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_execute_uses_alert_rule_team_intersection_for_all_external_calls(mock_target, mock_job):
    mock_target.return_value = {
        "node_id": "n1", "name": "h", "ip": "10.0.0.5",
        "os": "linux", "cloud_region_id": 1,
    }
    mock_job.return_value.get_script.return_value = SCRIPT
    mock_job.return_value.job_script_execute.return_value = {
        "result": True, "data": {"task_id": 4821}
    }

    JobActionHandler().execute(_rule(team=[1, 2]), _alert(team=[1]), MagicMock())

    mock_job.return_value.get_script.assert_called_once_with(42, team=[1])
    mock_target.assert_called_once_with("10.0.0.5", [1])
    payload = mock_job.return_value.job_script_execute.call_args.args[0]
    assert payload["team"] == [1]


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target", side_effect=TargetError("主机未纳管"))
def test_target_error_sets_config_error_no_nats(mock_target, mock_job):
    mock_job.return_value.get_script.return_value = SCRIPT
    execution = MagicMock()
    JobActionHandler().execute(_rule(), _alert(), execution)
    assert execution.status == "config_error"
    mock_job.return_value.job_script_execute.assert_not_called()


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_script_not_found_config_error(mock_target, mock_job):
    mock_job.return_value.get_script.return_value = None
    execution = MagicMock()
    JobActionHandler().execute(_rule(), _alert(), execution)
    assert execution.status == "config_error"


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_nats_failure_sets_failed(mock_target, mock_job):
    mock_target.return_value = {"node_id": "n1", "name": "h", "ip": "10.0.0.5", "os": "linux", "cloud_region_id": 1}
    mock_job.return_value.get_script.return_value = SCRIPT
    mock_job.return_value.job_script_execute.return_value = {"result": False, "message": "boom"}
    execution = MagicMock()
    JobActionHandler().execute(_rule(), _alert(), execution)
    assert execution.status == "failed"
    assert "boom" in str(execution.result)


def test_registry_returns_job_handler():
    from apps.alerts.action.handlers.registry import get_handler
    from apps.alerts.action.handlers.job import JobActionHandler
    assert isinstance(get_handler("job"), JobActionHandler)


def test_registry_unknown_type_raises():
    from apps.alerts.action.handlers.registry import get_handler
    import pytest
    with pytest.raises(KeyError):
        get_handler("itsm")
