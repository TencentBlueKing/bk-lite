from unittest.mock import MagicMock, patch

from apps.alerts.action.handlers.job import JobActionHandler
from apps.alerts.action.resolver import resolve_params

OLD_BINDING = [{"name": "mode", "from": "const", "value": "old-value"}]


def test_empty_script_params_do_not_restore_old_bindings():
    assert resolve_params({}, OLD_BINDING, []) == []


def test_missing_script_params_still_fall_back_to_bindings():
    assert resolve_params({}, OLD_BINDING, None) == [{"name": "mode", "value": "old-value"}]


def test_nonempty_script_params_follow_script_order():
    bindings = [
        {"name": "later", "from": "const", "value": "b"},
        {"name": "mode", "from": "const", "value": "kept"},
    ]
    script_params = [
        {"name": "mode", "default": "unused"},
        {"name": "later", "default": "x"},
    ]
    assert resolve_params({}, bindings, script_params) == [
        {"name": "mode", "value": "kept"},
        {"name": "later", "value": "b"},
    ]


def _alert():
    alert = MagicMock()
    alert.alert_id = "A1"
    alert.labels = {"ip": "10.0.0.5"}
    alert.enrichment = {}
    alert.title = "t"
    alert.level = "1"
    alert.status = "unassigned"
    alert.resource_id = alert.resource_name = alert.resource_type = None
    alert.item = alert.source_name = None
    alert.content = "c"
    alert.team = [1]
    alert.events = None
    return alert


def _rule():
    rule = MagicMock()
    rule.team = [1]
    rule.name = "清空参数"
    rule.action_config = {
        "script_id": 42,
        "target_binding": {"source": "node_mgmt", "match_by": "ip", "host_field": "labels.ip"},
        "param_bindings": [{"name": "mode", "from": "const", "value": "old-value"}],
    }
    return rule


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_job_handler_sends_empty_params_when_script_params_are_empty(mock_target, mock_job):
    mock_target.return_value = {
        "node_id": "n1",
        "name": "h",
        "ip": "10.0.0.5",
        "os": "linux",
        "cloud_region_id": 1,
    }
    mock_job.return_value.get_script.return_value = {
        "id": 42,
        "name": "清空参数",
        "script_type": "shell",
        "content": "echo",
        "params": [],
        "timeout": 300,
    }
    mock_job.return_value.job_script_execute.return_value = {"result": True, "data": {"task_id": 1}}
    execution = MagicMock()
    execution.trigger_event = "created"
    execution.result = {}

    JobActionHandler().execute(_rule(), _alert(), execution)

    payload = mock_job.return_value.job_script_execute.call_args[0][0]
    assert payload["params"] == []
    assert execution.result["params"] == []
