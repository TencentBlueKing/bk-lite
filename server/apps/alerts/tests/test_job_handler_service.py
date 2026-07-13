import pytest
from unittest.mock import patch, MagicMock
from apps.alerts.action.handlers.job import JobActionHandler
from apps.alerts.action.exceptions import ConfigError, TargetError


def _alert():
    a = MagicMock()
    a.alert_id = "A1"; a.labels = {"ip": "10.0.0.5", "service": "nginx"}
    a.enrichment = {}; a.title = "t"; a.level = "1"; a.status = "unassigned"
    a.resource_id = a.resource_name = a.resource_type = a.item = a.source_name = None
    a.content = "c"
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
    # 测试环境未设 SELF_BASE_URL → callback_url 字段为 None；行为见 test_callback_url_uses_self_base_url_when_set。
    assert payload["callback_url"] is None
    assert execution.job_task_id == 4821
    assert execution.status == "running"
    execution.save.assert_called()


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


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_nats_failure_preserves_target_ip(mock_target, mock_job):
    """NATS 失败时不应丢失 target_ip——前端要能看到"试图往这个 IP 发，却失败"。"""
    mock_target.return_value = {"node_id": "n1", "name": "h", "ip": "10.0.0.5",
                                "os": "linux", "cloud_region_id": 1}
    mock_job.return_value.get_script.return_value = SCRIPT
    mock_job.return_value.job_script_execute.return_value = {"result": False, "message": "Invalid callback_url"}
    execution = MagicMock()
    JobActionHandler().execute(_rule(), _alert(), execution)
    assert execution.status == "failed"
    assert execution.result.get("target_ip") == "10.0.0.5"
    assert execution.result.get("message") == "Invalid callback_url"


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_mode_fixed_uses_rule_ip_not_alert_payload(mock_target, mock_job):
    """mode='fixed' + ip='10.0.0.7'：resolve_node_target 应被规则 IP 调用，而不是 alert.labels.ip。"""
    mock_target.return_value = {"node_id": "n1", "name": "fix", "ip": "10.0.0.7",
                                "os": "linux", "cloud_region_id": 1}
    mock_job.return_value.get_script.return_value = SCRIPT
    mock_job.return_value.job_script_execute.return_value = {"result": True, "data": {"task_id": 7}}
    rule = _rule()
    rule.action_config["target_binding"] = {
        "source": "node_mgmt",
        "mode": "fixed",
        "ip": "10.0.0.7",
    }
    alert = _alert()
    alert.labels = {"ip": "10.0.0.5", "ip_addr": "10.0.0.5"}    # 期望被忽略

    JobActionHandler().execute(rule, alert, MagicMock())

    assert mock_target.call_args[0][0] == "10.0.0.7"


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_mode_fixed_missing_ip_raises_config_error(mock_target, mock_job):
    """mode='fixed' 但 ip 缺失：应当走 ConfigError/execution.status=config_error，且不调用 job_script_execute。"""
    mock_job.return_value.get_script.return_value = SCRIPT
    rule = _rule()
    rule.action_config["target_binding"] = {
        "source": "node_mgmt",
        "mode": "fixed",
        # 故意不写 ip
    }
    execution = MagicMock()
    JobActionHandler().execute(rule, _alert(), execution)
    assert execution.status == "config_error"
    mock_target.assert_not_called()
    mock_job.return_value.job_script_execute.assert_not_called()


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_mode_default_is_from_alert_for_backward_compat(mock_target, mock_job):
    """缺省 mode / 显式 from_alert：仍然按 alert payload 取 host_field。"""
    mock_target.return_value = {"node_id": "n1", "name": "h", "ip": "10.0.0.5",
                                "os": "linux", "cloud_region_id": 1}
    mock_job.return_value.get_script.return_value = SCRIPT
    mock_job.return_value.job_script_execute.return_value = {"result": True, "data": {"task_id": 1}}

    # 缺省 mode：rule 用 fixtures 默认 host_field="labels.ip"，alert 用 _alert() 默认 labels（含 "ip"）。
    rule_default = _rule()
    rule_default.action_config["target_binding"].pop("mode", None)
    alert = _alert()    # labels={"ip": "10.0.0.5", ...}
    JobActionHandler().execute(rule_default, alert, MagicMock())
    assert mock_target.call_args[0][0] == "10.0.0.5"

    # 显式 from_alert：同样预期从 alert payload 取值
    mock_target.reset_mock()
    rule_explicit = _rule()
    rule_explicit.action_config["target_binding"]["mode"] = "from_alert"
    JobActionHandler().execute(rule_explicit, alert, MagicMock())
    assert mock_target.call_args[0][0] == "10.0.0.5"


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_execution_result_records_target_ip_from_alert(mock_target, mock_job):
    """from_alert 模式：execution.result.target_ip 应当被记录为本次解析到的主机 IP。"""
    mock_target.return_value = {"node_id": "n1", "name": "h", "ip": "10.0.0.5",
                                "os": "linux", "cloud_region_id": 1}
    mock_job.return_value.get_script.return_value = SCRIPT
    mock_job.return_value.job_script_execute.return_value = {"result": True, "data": {"task_id": 9}}
    execution = MagicMock()
    JobActionHandler().execute(_rule(), _alert(), execution)

    assert execution.result.get("target_ip") == "10.0.0.5"
    assert execution.status == "running"


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_execution_result_records_target_ip_when_mode_fixed(mock_target, mock_job):
    """mode=fixed 模式：execution.result.target_ip 同样需要记录（用户手动指定 IP）。"""
    mock_target.return_value = {"node_id": "n1", "name": "fix", "ip": "10.0.0.7",
                                "os": "linux", "cloud_region_id": 1}
    mock_job.return_value.get_script.return_value = SCRIPT
    mock_job.return_value.job_script_execute.return_value = {"result": True, "data": {"task_id": 10}}
    rule = _rule()
    rule.action_config["target_binding"] = {"source": "node_mgmt", "mode": "fixed", "ip": "10.0.0.7"}
    execution = MagicMock()
    JobActionHandler().execute(rule, _alert(), execution)

    assert execution.result.get("target_ip") == "10.0.0.7"
    assert execution.status == "running"


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_callback_url_returns_none_when_self_base_url_unset(mock_target, mock_job, settings):
    """SELF_BASE_URL 未设置时 _callback_url 必须返回 None（不再默认到 localhost，
    否则会被 job_mgmt SSRFValidator 的"禁止 localhost"拦截）。
    返回 None 等价于不传 callback，作业可执行但不回调，ActionExecution.status 停在 running。"""
    mock_target.return_value = {"node_id": "n1", "name": "h", "ip": "10.0.0.5",
                                "os": "linux", "cloud_region_id": 1}
    mock_job.return_value.get_script.return_value = SCRIPT
    mock_job.return_value.job_script_execute.return_value = {"result": True, "data": {"task_id": 1}}

    handler = JobActionHandler()
    if hasattr(settings, "SELF_BASE_URL"):
        delattr(settings, "SELF_BASE_URL")
    assert handler._callback_url() is None


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_callback_url_uses_self_base_url_when_set(mock_target, mock_job, settings):
    """SELF_BASE_URL 已设时，_callback_url 应正确拼接完整 URL。"""
    mock_target.return_value = {"node_id": "n1", "name": "h", "ip": "10.0.0.5",
                                "os": "linux", "cloud_region_id": 1}
    mock_job.return_value.get_script.return_value = SCRIPT
    mock_job.return_value.job_script_execute.return_value = {"result": True, "data": {"task_id": 1}}

    settings.SELF_BASE_URL = "http://10.0.0.1:8011"
    handler = JobActionHandler()
    assert handler._callback_url() == "http://10.0.0.1:8011/api/v1/alerts/api/action_callback/"


@patch("apps.alerts.action.handlers.job.JobMgmt")
@patch("apps.alerts.action.handlers.job.resolve_node_target")
def test_job_url_returns_relative_when_web_base_url_unset(mock_target, mock_job, settings):
    """WEB_BASE_URL 未设时 _job_url 退到相对路径（前端跳转用）。"""
    mock_target.return_value = {"node_id": "n1", "name": "h", "ip": "10.0.0.5",
                                "os": "linux", "cloud_region_id": 1}
    mock_job.return_value.get_script.return_value = SCRIPT
    mock_job.return_value.job_script_execute.return_value = {"result": True, "data": {"task_id": 1}}

    handler = JobActionHandler()
    if hasattr(settings, "WEB_BASE_URL"):
        delattr(settings, "WEB_BASE_URL")
    assert handler._job_url(123) == "/job/execution/job-record?id=123"


def test_registry_returns_job_handler():
    from apps.alerts.action.handlers.registry import get_handler
    from apps.alerts.action.handlers.job import JobActionHandler
    assert isinstance(get_handler("job"), JobActionHandler)


def test_registry_unknown_type_raises():
    from apps.alerts.action.handlers.registry import get_handler
    import pytest
    with pytest.raises(KeyError):
        get_handler("itsm")
