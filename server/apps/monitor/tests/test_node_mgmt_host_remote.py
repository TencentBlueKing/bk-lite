import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import CollectConfig
from apps.monitor.models.monitor_object import MonitorInstance, MonitorInstanceOrganization, MonitorObject
from apps.monitor.services import node_mgmt as node_mgmt_service


def _build_host_remote_payload(host_object_id: int, instance_id: str) -> dict:
    return {
        "collect_type": "http",
        "collector": "Telegraf",
        "configs": [
            {
                "type": "host",
                "os_type": "linux",
                "port": "22",
                "interval": 60,
            }
        ],
        "instances": [
            {
                "instance_id": instance_id,
                "instance_name": "10.10.41.149",
                "group_ids": [1],
                "node_ids": ["node-a"],
            }
        ],
        "monitor_object_id": host_object_id,
        "monitor_plugin_id": 208,
    }


@pytest.mark.parametrize("incoming_instance_id", ["MTVmOTFiYTM5ODZk", "('MTVmOTFiYTM5ODZk',)"])
def test_host_remote_onboarding_reuses_existing_host_instance(db, monkeypatch, incoming_instance_id):
    host_object = MonitorObject.objects.create(name="Host", display_name="Host")
    existing = MonitorInstance.objects.create(
        id="('MTVmOTFiYTM5ODZk',)",
        name="10.10.41.149",
        monitor_object_id=host_object.id,
    )
    MonitorInstanceOrganization.objects.create(monitor_instance_id=existing.id, organization=1)
    CollectConfig.objects.create(
        id="cfg-old-host",
        monitor_instance_id=existing.id,
        collector="Telegraf",
        collect_type="host",
        config_type="host",
        file_type="toml",
        is_child=True,
    )

    controller_payloads = []
    monkeypatch.setattr(
        node_mgmt_service.Controller,
        "controller",
        lambda self: controller_payloads.append(self.data),
    )
    monkeypatch.setattr(
        node_mgmt_service.InstanceConfigService,
        "_validate_instances_with_plugin_selector",
        staticmethod(lambda instances, monitor_plugin_id, actor_context=None: None),
    )

    node_mgmt_service.InstanceConfigService.create_monitor_instance_by_node_mgmt(
        _build_host_remote_payload(host_object.id, incoming_instance_id)
    )

    assert MonitorInstance.objects.filter(monitor_object_id=host_object.id).count() == 1
    assert controller_payloads[0]["instances"][0]["instance_id"] == existing.id
    assert controller_payloads[0]["instances"][0]["logical_instance_value"] == "MTVmOTFiYTM5ODZk"


def test_host_remote_onboarding_rejects_duplicate_same_collect_type(db, monkeypatch):
    host_object = MonitorObject.objects.create(name="Host", display_name="Host")
    existing = MonitorInstance.objects.create(
        id="('MTVmOTFiYTM5ODZk',)",
        name="10.10.41.149",
        monitor_object_id=host_object.id,
    )
    CollectConfig.objects.create(
        id="cfg-existing-http-host",
        monitor_instance_id=existing.id,
        collector="Telegraf",
        collect_type="http",
        config_type="host",
        file_type="toml",
        is_child=True,
    )
    monkeypatch.setattr(node_mgmt_service.Controller, "controller", lambda self: None)
    monkeypatch.setattr(
        node_mgmt_service.InstanceConfigService,
        "_validate_instances_with_plugin_selector",
        staticmethod(lambda instances, monitor_plugin_id, actor_context=None: None),
    )

    with pytest.raises(BaseAppException, match="重复配置冲突|已存在采集配置"):
        node_mgmt_service.InstanceConfigService.create_monitor_instance_by_node_mgmt(
            _build_host_remote_payload(host_object.id, "MTVmOTFiYTM5ODZk")
        )
