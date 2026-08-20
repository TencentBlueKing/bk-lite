from unittest.mock import Mock

import pytest

from apps.monitor.models import CollectConfig, MonitorInstance, MonitorObject
from apps.monitor.models.plugin import MonitorPlugin
from apps.monitor.services.monitor_instance_removal import MonitorInstanceRemovalService
from apps.monitor.services.node_mgmt import InstanceConfigService


def _base_config(config_id):
    monitor_object = MonitorObject.objects.create(name=f"object-{config_id}", display_name="监控对象")
    instance = MonitorInstance.objects.create(
        id=f"instance-{config_id}",
        name="监控实例",
        monitor_object=monitor_object,
    )
    plugin = MonitorPlugin.objects.create(name=f"plugin-{config_id}")
    config = CollectConfig.objects.create(
        id=config_id,
        monitor_instance=instance,
        monitor_plugin=plugin,
        collector="Telegraf",
        collect_type="host",
        config_type="base",
        file_type="yaml",
        is_child=False,
    )
    return instance, config


@pytest.mark.django_db
def test_update_instance_config_uses_monitor_scoped_update(monkeypatch):
    instance, config = _base_config("monitor-update")
    child_config = CollectConfig.objects.create(
        id="monitor-child-update",
        monitor_instance=instance,
        monitor_plugin=config.monitor_plugin,
        collector="Telegraf",
        collect_type="host",
        config_type="child",
        file_type="toml",
        is_child=True,
    )
    node_mgmt = Mock()
    monkeypatch.setattr("apps.monitor.services.node_mgmt.NodeMgmt", lambda: node_mgmt)

    InstanceConfigService.update_instance_config(
        child_info={
            "id": child_config.id,
            "content": {"plugin": ["inputs", "cpu"], "config": {"child": "value"}},
        },
        base_info={"id": config.id, "content": {"key": "value"}},
    )

    node_mgmt.update_config_content.assert_called_once_with(
        config.id,
        "key: value\n",
        None,
        source_app="monitor",
    )
    assert node_mgmt.update_child_config_content.call_args.kwargs == {"source_app": "monitor"}


@pytest.mark.django_db
def test_remove_instance_uses_monitor_scoped_delete(monkeypatch):
    instance, config = _base_config("monitor-delete")
    child_config = CollectConfig.objects.create(
        id="monitor-child-delete-caller",
        monitor_instance=instance,
        monitor_plugin=config.monitor_plugin,
        collector="Telegraf",
        collect_type="host",
        config_type="child",
        file_type="toml",
        is_child=True,
    )
    node_mgmt = Mock()
    monkeypatch.setattr("apps.monitor.services.monitor_instance_removal.NodeMgmt", lambda: node_mgmt)

    MonitorInstanceRemovalService.remove([instance.id])

    node_mgmt.delete_configs.assert_called_once_with([config.id], source_app="monitor")
    node_mgmt.delete_child_configs.assert_called_once_with([child_config.id], source_app="monitor")
