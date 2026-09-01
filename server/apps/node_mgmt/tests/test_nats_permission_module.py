"""节点 NATS 权限模块：按云区域/组织分页节点，以及模块列表。"""
import pytest

from apps.node_mgmt.models import CloudRegion, Node, NodeOrganization
from apps.node_mgmt.nats import permission as nats_perm

pytestmark = pytest.mark.django_db


def test_get_node_module_data_filters_by_org_and_rejects_unknown():
    region = CloudRegion.objects.create(name="nats-perm-region")
    node = Node.objects.create(
        id="nats-node-1",
        name="nn1",
        ip="10.9.9.1",
        operating_system="linux",
        collector_configuration_directory="/etc/sidecar",
        cloud_region=region,
    )
    NodeOrganization.objects.create(node=node, organization=4)
    other = Node.objects.create(
        id="nats-node-2",
        name="nn2",
        ip="10.9.9.2",
        operating_system="linux",
        collector_configuration_directory="/etc/sidecar",
        cloud_region=region,
    )
    NodeOrganization.objects.create(node=other, organization=9)

    out = nats_perm.get_node_module_data("instance", region.id, 1, 10, 4)
    assert out["count"] == 1
    assert out["items"] == [{"id": "nats-node-1", "name": "nn1"}]

    with pytest.raises(ValueError, match="Invalid module type"):
        nats_perm.get_node_module_data("policy", region.id, 1, 10, 4)


def test_get_node_module_list_includes_cloud_regions():
    region = CloudRegion.objects.create(name="nats-list-region")
    out = nats_perm.get_node_module_list()
    assert out[0]["name"] == "instance"
    assert out[0]["display_name"] == "Instance"
    assert {"name": region.id, "display_name": "nats-list-region", "children": []} in out[0]["children"]
