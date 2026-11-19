import pytest

from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.models import ChildConfig, CloudRegion, Collector, CollectorConfiguration, Node, NodeOrganization
from apps.node_mgmt.nats.node import delete_owned_child_configs, move_child_configs_to_node

pytestmark = pytest.mark.django_db


def _node(region, node_id, organization):
    node = Node.objects.create(
        id=node_id,
        name=node_id,
        ip=f"10.3.0.{organization}",
        operating_system="linux",
        collector_configuration_directory="/etc/collector",
        cloud_region=region,
    )
    NodeOrganization.objects.create(node=node, organization=organization)
    return node


def _collector():
    return Collector.objects.create(
        id="exit-nats-telegraf",
        name="ExitNatsTelegraf",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin/telegraf",
        execute_parameters="-c",
    )


def test_delete_owned_child_configs_removes_parent_only_after_last_child():
    region = CloudRegion.objects.create(name="exit-nats-delete-region")
    collector = _collector()
    node = _node(region, "exit-nats-delete-node", 1)
    parent = CollectorConfiguration.objects.create(name="exit-nats-parent", collector=collector, cloud_region=region, is_pre=True)
    parent.nodes.add(node)
    first = ChildConfig.objects.create(
        id="exit-nats-child-1",
        collect_type="host",
        config_type="cpu",
        content="[[inputs.cpu]]",
        collector_config=parent,
    )
    second = ChildConfig.objects.create(
        id="exit-nats-child-2",
        collect_type="host",
        config_type="mem",
        content="[[inputs.mem]]",
        collector_config=parent,
    )

    delete_owned_child_configs([first.id])
    delete_owned_child_configs([parent.id])

    assert not ChildConfig.objects.filter(id=first.id).exists()
    assert ChildConfig.objects.filter(id=second.id, content="[[inputs.mem]]").exists()
    assert CollectorConfiguration.objects.filter(id=parent.id).exists()

    delete_owned_child_configs([second.id, parent.id])

    assert not ChildConfig.objects.filter(id=second.id).exists()
    assert not CollectorConfiguration.objects.filter(id=parent.id).exists()


def test_move_child_configs_to_node_rejects_target_outside_organization():
    region = CloudRegion.objects.create(name="exit-nats-reject-region")
    collector = _collector()
    source = _node(region, "exit-nats-reject-source", 1)
    target = _node(region, "exit-nats-reject-target", 2)
    parent = CollectorConfiguration.objects.create(name="exit-nats-reject-parent", collector=collector, cloud_region=region, is_pre=True)
    parent.nodes.add(source)
    child = ChildConfig.objects.create(
        id="exit-nats-reject-child",
        collect_type="host",
        config_type="cpu",
        content="[[inputs.cpu]]",
        collector_config=parent,
    )

    with pytest.raises(BaseAppException, match="采集节点不在组织范围内"):
        move_child_configs_to_node([child.id], target.id, [child.id], [1])
    with pytest.raises(BaseAppException):
        move_child_configs_to_node([child.id], target.id, [child.id], [])

    child.refresh_from_db()
    assert child.collector_config_id == parent.id
    assert child.content == "[[inputs.cpu]]"
    assert list(parent.nodes.values_list("id", flat=True)) == [source.id]


def test_move_child_configs_to_node_moves_child_inside_organization():
    region = CloudRegion.objects.create(name="exit-nats-move-region")
    collector = _collector()
    source = _node(region, "exit-nats-move-source", 1)
    target = _node(region, "exit-nats-move-target", 1)
    parent = CollectorConfiguration.objects.create(name="exit-nats-move-parent", collector=collector, cloud_region=region, is_pre=True)
    parent.nodes.add(source)
    child = ChildConfig.objects.create(
        id="exit-nats-move-child",
        collect_type="host",
        config_type="cpu",
        content="[[inputs.mysql]]",
        collector_config=parent,
    )

    move_child_configs_to_node([child.id], target.id, [child.id], [1])

    child.refresh_from_db()
    assert child.content == "[[inputs.mysql]]"
    assert child.collector_config_id != parent.id
    assert list(child.collector_config.nodes.values_list("id", flat=True)) == [target.id]
