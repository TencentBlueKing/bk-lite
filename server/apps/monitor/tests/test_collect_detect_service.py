import pytest

from apps.monitor.models import CollectDetectTask, MonitorObject, MonitorPlugin
from apps.monitor.serializers.plugin import MonitorPluginSerializer


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
