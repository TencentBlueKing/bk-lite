"""NodeAssociationService：主机资产 → 节点只建关联。"""

import pytest

from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import Node
from apps.node_mgmt.services.module_link import NodeAssociationService


@pytest.fixture
def region(db):
    return CloudRegion.objects.create(name="link-region")


@pytest.fixture
def node(db, region):
    return Node.objects.create(
        id="node-link-1",
        name="node-link-1",
        ip="10.0.0.50",
        operating_system="linux",
        collector_configuration_directory="/tmp",
        cloud_region=region,
    )


@pytest.mark.django_db
def test_associate_cmdb_host_links_unique_node(node, region):
    linked = NodeAssociationService.best_effort_associate_cmdb_host(
        cmdb_id=1704,
        ip="10.0.0.50",
        cloud=region.id,
    )
    assert linked == node.id
    node.refresh_from_db()
    assert node.cmdb_id == "1704"


@pytest.mark.django_db
def test_associate_monitor_host_links_unique_node(node, region):
    linked = NodeAssociationService.best_effort_associate_monitor_host(
        monitor_id="('mon-1',)",
        ip="10.0.0.50",
        cloud=region.id,
    )
    assert linked == node.id
    node.refresh_from_db()
    assert node.monitor_id == "('mon-1',)"


@pytest.mark.django_db
def test_associate_skips_when_no_match(region):
    linked = NodeAssociationService.best_effort_associate_cmdb_host(
        cmdb_id=1,
        ip="10.0.0.99",
        cloud=region.id,
    )
    assert linked is None


@pytest.mark.django_db
def test_associate_skips_when_non_unique(node, region):
    Node.objects.create(
        id="node-link-2",
        name="node-link-2",
        ip="10.0.0.50",
        operating_system="linux",
        collector_configuration_directory="/tmp",
        cloud_region=region,
    )
    linked = NodeAssociationService.best_effort_associate_cmdb_host(
        cmdb_id=1,
        ip="10.0.0.50",
        cloud=region.id,
    )
    assert linked is None
    node.refresh_from_db()
    assert node.cmdb_id == ""


@pytest.mark.django_db
def test_associate_skips_conflict_on_existing_peer_id(node, region):
    node.cmdb_id = "999"
    node.save(update_fields=["cmdb_id"])
    linked = NodeAssociationService.best_effort_associate_cmdb_host(
        cmdb_id=1704,
        ip="10.0.0.50",
        cloud=region.id,
    )
    assert linked is None
    node.refresh_from_db()
    assert node.cmdb_id == "999"


@pytest.mark.django_db
def test_associate_with_existing_node_id_backfills_peer(node):
    linked = NodeAssociationService.best_effort_associate_monitor_host(
        monitor_id="mon-x",
        ip="ignored",
        cloud=None,
        existing_node_id=node.id,
    )
    assert linked == node.id
    node.refresh_from_db()
    assert node.monitor_id == "mon-x"
