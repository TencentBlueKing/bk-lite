"""CMDB module ingest：host 的 ID 优先 upsert + 存量认领。"""

import pytest

from apps.cmdb.services.module_ingest import CmdbModuleIngestService


def test_ingest_host_upserts_by_node_id(mocker):
    mocker.patch.object(
        CmdbModuleIngestService,
        "_find_by_node_id",
        return_value={"_id": 10, "node_id": "n1", "ip_addr": "1.1.1.1", "cloud": 1},
    )
    update = mocker.patch.object(
        CmdbModuleIngestService,
        "_update_host",
        return_value={"_id": 10, "node_id": "n1"},
    )
    result = CmdbModuleIngestService.ingest(
        {
            "source_module": "node_mgmt",
            "source_id": "n1",
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {
                "ip": "1.1.1.1",
                "cloud_region_id": 1,
                "organization_ids": [1],
                "name": "h1",
            },
            "link_ids": {"node_id": "n1"},
            "allowed_org_ids": [1],
            "operator": "tester",
        }
    )
    assert result["id"] == 10
    assert result["updated"] is True
    update.assert_called_once()


def test_ingest_host_claims_existing_by_ip_cloud(mocker):
    mocker.patch.object(CmdbModuleIngestService, "_find_by_node_id", return_value=None)
    mocker.patch.object(
        CmdbModuleIngestService,
        "_find_host_by_ip_cloud",
        return_value={"_id": 20, "ip_addr": "1.1.1.2", "cloud": 1},
    )
    claim = mocker.patch.object(
        CmdbModuleIngestService,
        "_claim_host",
        return_value={"_id": 20, "node_id": "n2"},
    )
    result = CmdbModuleIngestService.ingest(
        {
            "source_module": "node_mgmt",
            "source_id": "n2",
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {"ip": "1.1.1.2", "cloud_region_id": 1, "organization_ids": [1]},
            "link_ids": {"node_id": "n2"},
            "allowed_org_ids": [1],
            "operator": "tester",
        }
    )
    assert result["id"] == 20
    assert result["claimed"] is True
    claim.assert_called_once()


def test_ingest_host_creates_when_no_match(mocker):
    mocker.patch.object(CmdbModuleIngestService, "_find_by_node_id", return_value=None)
    mocker.patch.object(CmdbModuleIngestService, "_find_host_by_ip_cloud", return_value=None)
    create = mocker.patch.object(
        CmdbModuleIngestService,
        "_create_host",
        return_value={"_id": 30, "node_id": "n3"},
    )
    result = CmdbModuleIngestService.ingest(
        {
            "source_module": "node_mgmt",
            "source_id": "n3",
            "event_type": "upsert",
            "occurred_at": "2026-08-05T00:00:00Z",
            "raw": {"ip": "1.1.1.3", "cloud_region_id": 1, "organization_ids": [1]},
            "link_ids": {"node_id": "n3"},
            "allowed_org_ids": [1],
            "operator": "tester",
        }
    )
    assert result["id"] == 30
    assert result["created"] is True
    create.assert_called_once()


def test_ingest_requires_auth_scope():
    with pytest.raises(ValueError, match="authorization"):
        CmdbModuleIngestService.ingest(
            {
                "source_module": "node_mgmt",
                "source_id": "n3",
                "event_type": "upsert",
                "occurred_at": "2026-08-05T00:00:00Z",
                "raw": {"ip": "1.1.1.3", "cloud_region_id": 1},
                "link_ids": {"node_id": "n3"},
            }
        )
