"""NodeModuleIngestService：只关联，不创建节点。"""

import pytest

from apps.node_mgmt.models.cloud_region import CloudRegion
from apps.node_mgmt.models.sidecar import Node
from apps.node_mgmt.services.module_ingest import NodeModuleIngestService


@pytest.fixture
def region(db):
    return CloudRegion.objects.create(name="node-ingest-region")


@pytest.fixture
def node(region):
    return Node.objects.create(
        id="node-ingest-1",
        name="n1",
        ip="10.9.9.1",
        operating_system="linux",
        collector_configuration_directory="/etc/telegraf",
        cloud_region=region,
    )


@pytest.mark.django_db
def test_cmdb_source_links_unique_node(node, region):
    result = NodeModuleIngestService.ingest(
        {
            "source_module": "cmdb",
            "source_id": "501",
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {"ip": "10.9.9.1", "cloud_region_id": region.id},
            "link_ids": {"cmdb_id": "501"},
        }
    )
    assert result["updated"] is True
    assert result["id"] == node.id
    node.refresh_from_db()
    assert node.cmdb_id == "501"


@pytest.mark.django_db
def test_monitor_source_links_unique_node(node, region):
    result = NodeModuleIngestService.ingest(
        {
            "source_module": "monitor",
            "source_id": "('m1',)",
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {"ip": "10.9.9.1", "cloud": region.id},
            "link_ids": {"monitor_id": "('m1',)"},
        }
    )
    assert result["updated"] is True
    assert result["id"] == node.id
    node.refresh_from_db()
    assert node.monitor_id == "('m1',)"


@pytest.mark.django_db
def test_no_match_ignored(region):
    result = NodeModuleIngestService.ingest(
        {
            "source_module": "cmdb",
            "source_id": "502",
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {"ip": "10.9.9.99", "cloud_region_id": region.id},
            "link_ids": {"cmdb_id": "502"},
        }
    )
    assert result["ignored"] is True
    assert result["id"] is None


@pytest.mark.django_db
def test_echo_from_node_mgmt_ignored(node):
    result = NodeModuleIngestService.ingest(
        {
            "source_module": "node_mgmt",
            "source_id": node.id,
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {"ip": node.ip},
            "link_ids": {"node_id": node.id, "cmdb_id": "9"},
        }
    )
    assert result["ignored"] is True


@pytest.mark.django_db
def test_lifecycle_from_cmdb_clears_cmdb_id_only(node):
    node.cmdb_id = "501"
    node.monitor_id = "m-keep"
    node.save(update_fields=["cmdb_id", "monitor_id", "updated_at"])

    result = NodeModuleIngestService.ingest(
        {
            "source_module": "cmdb",
            "source_id": "501",
            "event_type": "lifecycle",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {"action": "unlink"},
            "link_ids": {"cmdb_id": "501", "node_id": node.id},
        }
    )
    assert result["updated"] is True
    node.refresh_from_db()
    assert node.cmdb_id in (None, "")
    assert node.monitor_id == "m-keep"
    assert Node.objects.filter(id=node.id).exists()
