import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.node_mgmt.models import ChildConfig, CloudRegion, Collector, CollectorConfiguration, Node, NodeOrganization
from apps.node_mgmt.nats.node import NatsService

pytestmark = pytest.mark.django_db


def _create_node(region, node_id, name, organization):
    node = Node.objects.create(
        id=node_id,
        name=name,
        ip=f"10.0.0.{node_id[-1]}",
        operating_system="linux",
        collector_configuration_directory="/etc",
        cloud_region=region,
    )
    NodeOrganization.objects.create(node=node, organization=organization)
    return node


def test_get_child_config_nodes_by_ids_batches_filters_and_orders(db):
    region = CloudRegion.objects.create(name="batch-config-node-region")
    collector = Collector.objects.create(
        id="batch-config-node-collector",
        name="BatchConfigNodeCollector",
        service_type="svc",
        node_operating_system="linux",
        executable_path="/bin/collector",
        execute_parameters="",
    )
    first_node = _create_node(region, "node-2", "Beta", 7)
    second_node = _create_node(region, "node-1", "Alpha", 7)
    denied_node = _create_node(region, "node-3", "Denied", 8)
    parent = CollectorConfiguration.objects.create(
        id="parent-config",
        name="parent-config",
        collector=collector,
        cloud_region=region,
    )
    parent.nodes.add(first_node, second_node, denied_node)
    ChildConfig.objects.create(
        id="child-b",
        collect_type="host",
        config_type="mem",
        content="[[inputs.mem]]",
        collector_config=parent,
    )
    ChildConfig.objects.create(
        id="child-a",
        collect_type="host",
        config_type="cpu",
        content="[[inputs.cpu]]",
        collector_config=parent,
    )

    with CaptureQueriesContext(connection) as queries:
        result = NatsService().get_child_config_nodes_by_ids(
            ["child-b", "child-a", "child-a"],
            [7],
        )

    assert len(queries) == 1
    assert result == [
        {
            "id": "child-a",
            "nodes": [
                {"id": "node-1", "name": "Alpha"},
                {"id": "node-2", "name": "Beta"},
            ],
        },
        {
            "id": "child-b",
            "nodes": [
                {"id": "node-1", "name": "Alpha"},
                {"id": "node-2", "name": "Beta"},
            ],
        },
    ]


def test_get_child_config_nodes_by_ids_fails_closed_without_organization_scope(db):
    assert NatsService().get_child_config_nodes_by_ids(["child-a"], []) == []
    assert NatsService().get_child_config_nodes_by_ids(None, [7]) == []
    assert NatsService().get_child_config_nodes_by_ids(["child-a"], "7") == []
