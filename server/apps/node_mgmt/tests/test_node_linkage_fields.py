import pytest

from apps.node_mgmt.models import Node
from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.serializers.node import NodeSerializer


@pytest.mark.django_db
def test_node_stores_linkage_fields():
    region = CloudRegion.objects.create(name="default")
    node = Node.objects.create(
        id="n-link-1",
        name="n1",
        ip="10.0.0.9",
        operating_system="linux",
        collector_configuration_directory="/tmp",
        cloud_region=region,
        cmdb_id="123",
        monitor_id="m-1",
        push_status={"cmdb": {"state": "ok"}, "monitor": {"state": "skipped"}},
    )
    node.refresh_from_db()
    assert node.cmdb_id == "123"
    assert node.monitor_id == "m-1"
    assert node.push_status["monitor"]["state"] == "skipped"


@pytest.mark.django_db
def test_node_serializer_exposes_linkage_fields():
    region = CloudRegion.objects.create(name="default-ser")
    node = Node.objects.create(
        id="n-link-ser-1",
        name="n-ser",
        ip="10.0.0.10",
        operating_system="linux",
        collector_configuration_directory="/tmp",
        cloud_region=region,
        cmdb_id="456",
        monitor_id="m-2",
        push_status={"cmdb": {"state": "ok"}},
    )
    data = NodeSerializer(node).data
    assert data["cmdb_id"] == "456"
    assert data["monitor_id"] == "m-2"
    assert data["push_status"]["cmdb"]["state"] == "ok"
