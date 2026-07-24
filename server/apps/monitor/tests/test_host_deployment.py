import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.monitor.models import CollectConfig, MonitorInstance, MonitorObject
from apps.monitor.services.host_deployment import HostDeploymentStatus
from apps.monitor.services.node_mgmt import InstanceConfigService
from apps.node_mgmt.models import (
    ChildConfig,
    CloudRegion,
    Collector,
    CollectorConfiguration,
    Node,
)
from apps.rpc.node_mgmt import NodeMgmt


class FakeNodeMgmt:
    def __init__(self, configured_node_ids):
        self.configured_node_ids = configured_node_ids
        self.calls = []

    def get_nodes_with_child_config(self, node_ids, collector, collect_type):
        self.calls.append((node_ids, collector, collect_type))
        return self.configured_node_ids


@pytest.mark.unit
def test_registry_returns_configured_host_monitoring_nodes():
    node_mgmt = FakeNodeMgmt(["node-2", "node-2"])
    deployment_status = HostDeploymentStatus(node_mgmt=node_mgmt)

    configured_node_ids = deployment_status.get_configured_node_ids(
        ["node-2", "node-1", "node-1", ""]
    )

    assert configured_node_ids == {"node-2"}
    assert node_mgmt.calls == [(["node-2", "node-1"], "Telegraf", "host")]


@pytest.mark.django_db
def test_registry_uses_node_mgmt_assignment_as_deployment_fact():
    region = CloudRegion.objects.create(name="host-deployment-region")
    collector = Collector.objects.create(
        id="host-deployment-telegraf",
        name="Telegraf",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin/telegraf",
        execute_parameters="-c",
    )
    node = Node.objects.create(
        id="host-deployment-node",
        name="host-deployment-node",
        ip="10.0.0.1",
        operating_system="linux",
        collector_configuration_directory="/etc/telegraf",
        cloud_region=region,
    )
    config = CollectorConfiguration.objects.create(
        name="host-deployment-config",
        collector=collector,
        cloud_region=region,
    )
    config.nodes.add(node)
    ChildConfig.objects.create(
        id="host-deployment-child",
        collect_type="host",
        config_type="cpu",
        content="[[inputs.cpu]]",
        collector_config=config,
    )

    configured_node_ids = HostDeploymentStatus(
        node_mgmt=NodeMgmt(is_local_client=True)
    ).get_configured_node_ids([node.id])

    assert configured_node_ids == {node.id}


@pytest.mark.django_db
def test_host_onboarding_rejects_node_with_deployed_monitoring(mocker):
    host = MonitorObject.objects.create(name="Host", level="base")
    mocker.patch(
        "apps.monitor.services.node_mgmt.HostDeploymentStatus.get_configured_node_ids",
        return_value={"node-1"},
    )

    with pytest.raises(BaseAppException, match="已接入主机监控"):
        InstanceConfigService.create_monitor_instance_by_node_mgmt(
            {
                "monitor_object_id": host.id,
                "collector": "Telegraf",
                "collect_type": "host",
                "configs": [],
                "instances": [
                    {
                        "instance_id": "host-1",
                        "instance_name": "host-1",
                        "node_ids": ["node-1"],
                        "group_ids": [1],
                    }
                ],
            }
        )


@pytest.mark.django_db
def test_host_onboarding_rejects_existing_instance_with_different_metric_type(mocker):
    host = MonitorObject.objects.create(name="Host", level="base")
    instance = MonitorInstance.objects.create(
        id="('host-1',)", name="host-1", monitor_object=host
    )
    CollectConfig.objects.create(
        id="host-cpu-config",
        monitor_instance=instance,
        collector="Telegraf",
        collect_type="host",
        config_type="cpu",
        file_type="toml",
        is_child=True,
    )
    mocker.patch(
        "apps.monitor.services.node_mgmt.HostDeploymentStatus.get_configured_node_ids",
        return_value=set(),
    )

    with pytest.raises(BaseAppException, match="已存在主机监控配置"):
        InstanceConfigService.create_monitor_instance_by_node_mgmt(
            {
                "monitor_object_id": host.id,
                "collector": "Telegraf",
                "collect_type": "host",
                "configs": [{"type": "gpu"}],
                "instances": [
                    {
                        "instance_id": "host-1",
                        "instance_name": "host-1",
                        "node_ids": ["node-1"],
                        "group_ids": [1],
                    }
                ],
            }
        )
