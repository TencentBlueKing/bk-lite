import pytest
from django.test import RequestFactory

from apps.monitor.models import CollectDetectTask, MonitorObject, MonitorPlugin, MonitorPluginConfigTemplate
from apps.monitor.serializers.plugin import MonitorPluginSerializer
from apps.monitor.services.collect_detect import CollectDetectService
from apps.monitor.services.plugin import MonitorPluginService
from apps.monitor.services.collect_detect_runtime import (
    build_telegraf_once_command,
    render_preflight_telegraf_config,
    sanitize_execution_result,
)


@pytest.mark.django_db
def test_monitor_plugin_defaults_collect_detect_disabled():
    monitor_object = MonitorObject.objects.create(name="Host")
    plugin = MonitorPlugin.objects.create(
        name="Host(Telegraf)",
        collector="Telegraf",
        collect_type="host",
    )
    plugin.monitor_object.add(monitor_object)

    assert plugin.support_collect_detect is False


def test_monitor_tasks_package_registers_collect_detect_task():
    from apps.monitor import tasks

    assert tasks.run_collect_detect_task.name == "apps.monitor.tasks.collect_detect.run_collect_detect_task"


@pytest.mark.django_db
def test_monitor_plugin_serializer_exposes_collect_detect_capability():
    plugin = MonitorPlugin.objects.create(
        name="Ping(Telegraf)",
        collector="Telegraf",
        collect_type="ping",
        support_collect_detect=True,
    )

    data = MonitorPluginSerializer(plugin).data

    assert data["support_collect_detect"] is True


@pytest.mark.django_db
def test_ui_template_by_params_exposes_collect_detect_capability():
    monitor_object = MonitorObject.objects.create(name="MySQL")
    plugin = MonitorPlugin.objects.create(
        name="MySQL",
        collector="Telegraf",
        collect_type="mysql",
        template_type="builtin",
        support_collect_detect=True,
    )
    plugin.monitor_object.add(monitor_object)
    MonitorPluginConfigTemplate.objects.create(
        plugin=plugin,
        type="mysql",
        config_type="mysql",
        file_type="toml",
        content="[[inputs.mysql]]\n",
    )
    from apps.monitor.models import MonitorPluginUITemplate

    MonitorPluginUITemplate.objects.create(
        plugin=plugin,
        content={"collector": "Telegraf", "collect_type": "mysql"},
    )

    data = MonitorPluginService.get_ui_template_by_params(
        "Telegraf",
        "mysql",
        monitor_object.id,
    )

    assert data["support_collect_detect"] is True


@pytest.mark.django_db
def test_plugin_import_persists_collect_detect_capability():
    MonitorPluginService.import_monitor_plugin(
        {
            "plugin": "HTTP",
            "plugin_desc": "HTTP check",
            "collector": "Telegraf",
            "collect_type": "http",
            "support_collect_detect": True,
            "name": "Website",
            "description": "Website",
            "metrics": [],
        }
    )

    plugin = MonitorPlugin.objects.get(name="HTTP")

    assert plugin.support_collect_detect is True


@pytest.mark.django_db
def test_collect_detect_task_stores_sanitized_execution_message():
    task = CollectDetectTask.objects.create(
        status="failed",
        phase="execute_once",
        monitor_plugin_id=1,
        monitor_object_id=2,
        collector="Telegraf",
        collect_type="snmp",
        node_id="node-1",
        instance_key="row-1",
        request_fingerprint="fp-1",
        created_by="admin",
        organization=3,
        result={
            "summary": "SNMP authentication failed",
            "stdout": "",
            "stderr": "authentication failed",
            "exit_code": 1,
            "duration_ms": 352,
        },
    )

    task.refresh_from_db()

    assert task.status == "failed"
    assert task.phase == "execute_once"
    assert task.result["stderr"] == "authentication failed"


def test_render_preflight_telegraf_config_replaces_real_outputs():
    template = """
[[inputs.mysql]]
  servers = ["{{ username }}:${PASSWORD__{{ config_id }}}@tcp({{ host }}:{{ port }})/"]

[[outputs.http]]
  url = "https://example.com/write"
"""

    rendered = render_preflight_telegraf_config(
        template,
        {
            "config_id": "detect-1",
            "username": "root",
            "host": "127.0.0.1",
            "port": 3306,
        },
    )

    assert "[[inputs.mysql]]" in rendered
    assert "[[outputs.http]]" not in rendered
    assert "[[outputs.file]]" in rendered
    assert 'files = ["stdout"]' in rendered


def test_build_telegraf_once_command_uses_temp_config_and_cleanup():
    command = build_telegraf_once_command("/tmp/bklite-detect.toml")

    assert "/opt/fusion-collectors/bin/telegraf --once --config /tmp/bklite-detect.toml" in command
    assert "rm -f /tmp/bklite-detect.toml" in command


def test_sanitize_execution_result_redacts_and_truncates_output():
    result = sanitize_execution_result(
        {
            "success": False,
            "result": "password=top-secret\n" + ("x" * 9000),
            "error": "token=abc123",
            "code": "execution_failure",
        },
        sensitive_values=["top-secret", "abc123"],
        output_limit=120,
    )

    assert result["success"] is False
    assert result["exit_code"] == 1
    assert "top-secret" not in result["stdout"]
    assert "abc123" not in result["stderr"]
    assert result["stdout_truncated"] is True


def test_sanitize_execution_result_accepts_string_stdout():
    result = sanitize_execution_result("cpu,host=node usage_idle=99")

    assert result["success"] is True
    assert result["stdout"] == "cpu,host=node usage_idle=99"
    assert result["stderr"] == ""
    assert result["exit_code"] == 0


@pytest.mark.django_db
def test_create_collect_detect_task_requires_supported_plugin():
    plugin = MonitorPlugin.objects.create(
        name="JMX",
        collector="JMX",
        collect_type="jmx",
        support_collect_detect=False,
    )

    with pytest.raises(ValueError, match="不支持采集检测"):
        CollectDetectService.create_task(
            {
                "monitor_plugin_id": plugin.id,
                "monitor_object_id": 1,
                "node_id": "node-1",
                "instance": {"host": "127.0.0.1"},
                "env": {},
            },
            user=type("User", (), {"username": "admin"})(),
            organization=3,
        )


@pytest.mark.django_db
def test_create_collect_detect_task_stores_sanitized_snapshot_and_dispatches(monkeypatch):
    plugin = MonitorPlugin.objects.create(
        name="MySQL",
        collector="Telegraf",
        collect_type="mysql",
        support_collect_detect=True,
    )
    dispatched = {}
    monkeypatch.setattr(
        "apps.monitor.tasks.collect_detect.run_collect_detect_task.delay",
        lambda task_id, runtime_payload: dispatched.update(task_id=task_id, runtime_payload=runtime_payload),
    )

    task = CollectDetectService.create_task(
        {
            "monitor_plugin_id": plugin.id,
            "monitor_object_id": 1,
            "node_id": "node-1",
            "instance_key": "mysql-1",
            "instance": {"host": "127.0.0.1", "password": "top-secret"},
            "env": {"PASSWORD__detect": "top-secret"},
        },
        user=type("User", (), {"username": "admin"})(),
        organization=3,
    )

    assert task.status == "pending"
    assert task.request_snapshot["instance"]["password"] == "***"
    assert dispatched["task_id"] == task.id
    assert dispatched["runtime_payload"]["instance"]["password"] == "top-secret"
    assert "top-secret" not in str(task.request_snapshot)


@pytest.mark.django_db
def test_run_collect_detect_task_executes_telegraf_once(monkeypatch):
    plugin = MonitorPlugin.objects.create(
        name="MySQL",
        collector="Telegraf",
        collect_type="mysql",
        support_collect_detect=True,
    )
    MonitorPluginConfigTemplate.objects.create(
        plugin=plugin,
        type="mysql",
        config_type="mysql",
        file_type="toml",
        content='[[inputs.mysql]]\n  servers = ["{{ username }}:${PASSWORD__{{ config_id }}}@tcp({{ host }}:{{ port }})/"]\n',
    )
    task = CollectDetectTask.objects.create(
        status="pending",
        phase="validate",
        monitor_plugin_id=plugin.id,
        monitor_object_id=1,
        collector="Telegraf",
        collect_type="mysql",
        node_id="node-1",
        request_fingerprint="fp-1",
        created_by="admin",
        organization=3,
    )
    executed = {}

    class FakeExecutor:
        def __init__(self, node_id):
            executed["node_id"] = node_id

        def execute_local(self, command, timeout=60, shell=None, env=None):
            executed.update(command=command, timeout=timeout, shell=shell, env=env)
            return {"success": True, "result": "mysql_up value=1", "error": ""}

    monkeypatch.setattr("apps.monitor.services.collect_detect.Executor", FakeExecutor)

    result = CollectDetectService.run_task(
        task.id,
        {
            "instance": {
                "config_id": "detect",
                "username": "root",
                "host": "127.0.0.1",
                "port": 3306,
            },
            "env": {"PASSWORD__detect": "top-secret"},
            "timeout": 30,
        },
    )

    task.refresh_from_db()
    assert result["success"] is True
    assert task.status == "success"
    assert "telegraf --once --config" in executed["command"]
    assert "[[outputs.file]]" in executed["command"]
    assert executed["env"] == {"PASSWORD__detect": "top-secret"}
    assert "top-secret" not in str(task.result)


@pytest.mark.django_db
def test_run_collect_detect_task_derives_sensitive_instance_env(monkeypatch):
    plugin = MonitorPlugin.objects.create(
        name="MySQL",
        collector="Telegraf",
        collect_type="mysql",
        support_collect_detect=True,
    )
    MonitorPluginConfigTemplate.objects.create(
        plugin=plugin,
        type="mysql",
        config_type="mysql",
        file_type="toml",
        content='[[inputs.mysql]]\n  servers = ["root:${PASSWORD__{{ config_id }}}@tcp({{ host }}:3306)/"]\n',
    )
    task = CollectDetectTask.objects.create(
        status="pending",
        phase="validate",
        monitor_plugin_id=plugin.id,
        monitor_object_id=1,
        collector="Telegraf",
        collect_type="mysql",
        node_id="node-1",
        request_fingerprint="fp-1",
        created_by="admin",
        organization=3,
    )
    executed = {}

    class FakeExecutor:
        def __init__(self, node_id):
            executed["node_id"] = node_id

        def execute_local(self, command, timeout=60, shell=None, env=None):
            executed.update(command=command, env=env)
            return {"success": True, "result": "mysql_up value=1", "error": ""}

    monkeypatch.setattr("apps.monitor.services.collect_detect.Executor", FakeExecutor)

    CollectDetectService.run_task(
        task.id,
        {
            "instance": {
                "config_id": "detect",
                "host": "127.0.0.1",
                "password": "top-secret",
            },
            "env": {},
        },
    )

    assert executed["env"] == {"PASSWORD__detect": "top-secret"}
    assert "top-secret" not in executed["command"]


@pytest.mark.django_db
def test_run_collect_detect_task_renders_selected_config_templates(monkeypatch):
    plugin = MonitorPlugin.objects.create(
        name="Host",
        collector="Telegraf",
        collect_type="host",
        support_collect_detect=True,
    )
    MonitorPluginConfigTemplate.objects.create(
        plugin=plugin,
        type="cpu",
        config_type="cpu",
        file_type="toml",
        content="[[inputs.cpu]]\n  percpu = true\n",
    )
    MonitorPluginConfigTemplate.objects.create(
        plugin=plugin,
        type="mem",
        config_type="mem",
        file_type="toml",
        content="[[inputs.mem]]\n",
    )
    task = CollectDetectTask.objects.create(
        status="pending",
        phase="validate",
        monitor_plugin_id=plugin.id,
        monitor_object_id=1,
        collector="Telegraf",
        collect_type="host",
        node_id="node-1",
        request_fingerprint="fp-1",
        created_by="admin",
        organization=3,
    )
    executed = {}

    class FakeExecutor:
        def __init__(self, node_id):
            executed["node_id"] = node_id

        def execute_local(self, command, timeout=60, shell=None, env=None):
            executed.update(command=command)
            return {"success": True, "result": "cpu value=1\nmem value=1", "error": ""}

    monkeypatch.setattr("apps.monitor.services.collect_detect.Executor", FakeExecutor)

    CollectDetectService.run_task(
        task.id,
        {
            "instance": {
                "config_id": "detect",
                "metric_type": ["cpu", "mem"],
            },
            "env": {},
        },
    )

    assert "[[inputs.cpu]]" in executed["command"]
    assert "[[inputs.mem]]" in executed["command"]
    assert executed["command"].count("[[outputs.file]]") == 1


@pytest.mark.django_db
def test_collect_detect_viewset_create_returns_task(monkeypatch):
    from apps.monitor.views.collect_detect import CollectDetectViewSet

    created = type("Task", (), {"id": 9, "status": "pending"})()
    calls = []

    def ensure_access(request, payload):
        calls.append(("access", payload["node_id"]))
        return {"current_team": 3}

    def create_task(payload, user, organization):
        calls.append(("create", payload["node_id"]))
        return created

    monkeypatch.setattr(
        "apps.monitor.views.collect_detect._ensure_collect_detect_access",
        ensure_access,
        raising=False,
    )
    monkeypatch.setattr(
        "apps.monitor.views.collect_detect.CollectDetectService.create_task",
        create_task,
    )
    request = RequestFactory().post(
        "/monitor/api/collect_detect/",
        data={"monitor_plugin_id": 1, "monitor_object_id": 2, "node_id": "node-1"},
        content_type="application/json",
    )
    request.user = type("User", (), {"username": "admin", "domain": "default", "is_superuser": True, "group_list": []})()
    request.COOKIES["current_team"] = "3"
    monkeypatch.setattr("apps.monitor.views.collect_detect.WebUtils.response_success", staticmethod(lambda data=None: data))

    response = CollectDetectViewSet().create(request)

    assert response == {"task_id": 9, "status": "pending"}
    assert calls == [("access", "node-1"), ("create", "node-1")]


@pytest.mark.django_db
def test_create_collect_detect_task_caps_timeout(monkeypatch):
    plugin = MonitorPlugin.objects.create(
        name="MySQL",
        collector="Telegraf",
        collect_type="mysql",
        support_collect_detect=True,
    )
    dispatched = {}
    monkeypatch.setattr(
        "apps.monitor.tasks.collect_detect.run_collect_detect_task.delay",
        lambda task_id, runtime_payload: dispatched.update(task_id=task_id, runtime_payload=runtime_payload),
    )

    CollectDetectService.create_task(
        {
            "monitor_plugin_id": plugin.id,
            "monitor_object_id": 1,
            "node_id": "node-1",
            "timeout": 9999,
            "instance": {"host": "127.0.0.1"},
        },
        user=type("User", (), {"username": "admin"})(),
        organization=3,
    )

    assert dispatched["runtime_payload"]["timeout"] == 600


@pytest.mark.django_db
def test_collect_detect_viewset_retrieve_returns_task_result(monkeypatch):
    from apps.monitor.views.collect_detect import CollectDetectViewSet

    task = CollectDetectTask.objects.create(
        status="failed",
        phase="execute_once",
        monitor_plugin_id=1,
        monitor_object_id=2,
        collector="Telegraf",
        collect_type="mysql",
        node_id="node-1",
        request_fingerprint="fp-1",
        created_by="admin",
        organization=3,
        result={"success": False, "stdout": "", "stderr": "authentication failed", "exit_code": 1},
    )
    request = RequestFactory().get(f"/monitor/api/collect_detect/{task.id}/")
    request.user = type("User", (), {"username": "admin", "domain": "default", "is_superuser": True, "group_list": []})()
    request.COOKIES["current_team"] = "3"
    monkeypatch.setattr(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        lambda *args, **kwargs: {"result": True, "data": [3]},
    )
    monkeypatch.setattr("apps.monitor.views.collect_detect.WebUtils.response_success", staticmethod(lambda data=None: data))

    response = CollectDetectViewSet().retrieve(request, pk=task.id)

    assert response["id"] == task.id
    assert response["status"] == "failed"
    assert response["result"]["stderr"] == "authentication failed"


@pytest.mark.django_db
def test_collect_detect_viewset_retrieve_hides_other_user_task(monkeypatch):
    from apps.monitor.views.collect_detect import CollectDetectViewSet

    task = CollectDetectTask.objects.create(
        status="failed",
        phase="execute_once",
        monitor_plugin_id=1,
        monitor_object_id=2,
        collector="Telegraf",
        collect_type="mysql",
        node_id="node-1",
        request_fingerprint="fp-1",
        created_by="other",
        organization=3,
        result={"success": False, "stdout": "", "stderr": "authentication failed", "exit_code": 1},
    )
    request = RequestFactory().get(f"/monitor/api/collect_detect/{task.id}/")
    request.user = type("User", (), {"username": "admin", "domain": "default", "is_superuser": False, "group_list": []})()
    request.COOKIES["current_team"] = "3"
    monkeypatch.setattr(
        "apps.core.utils.current_team_scope.SystemMgmt.get_authorized_groups_scoped",
        lambda *args, **kwargs: {"result": True, "data": [3]},
    )
    monkeypatch.setattr(
        "apps.monitor.views.collect_detect.WebUtils.response_error",
        staticmethod(lambda message, status_code=400: {"message": message, "status_code": status_code}),
    )

    response = CollectDetectViewSet().retrieve(request, pk=task.id)

    assert response == {"message": "任务不存在或无权访问", "status_code": 404}
