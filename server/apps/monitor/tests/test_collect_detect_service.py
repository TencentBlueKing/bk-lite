import pytest

from apps.monitor.models import CollectDetectTask, MonitorObject, MonitorPlugin
from apps.monitor.serializers.plugin import MonitorPluginSerializer
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
