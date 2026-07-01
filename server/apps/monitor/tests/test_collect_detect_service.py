import pytest

from apps.monitor.models import CollectDetectTask, MonitorObject, MonitorPlugin, MonitorPluginConfigTemplate
from apps.monitor.serializers.plugin import MonitorPluginSerializer
from apps.monitor.services.collect_detect import CollectDetectService
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

    assert "telegraf --once --config /tmp/bklite-detect.toml" in command
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
