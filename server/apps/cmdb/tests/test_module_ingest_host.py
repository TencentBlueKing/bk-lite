"""CMDB module ingest：host 的 ID 优先 upsert + 存量认领。"""

import json

import pytest

from apps.cmdb.services.module_ingest import (
    HOST_NODE_ID_ATTR,
    CmdbModuleIngestService,
    ensure_host_node_id_attr,
)
from apps.core.exceptions.base_app_exception import BaseAppException


def test_ensure_host_node_id_attr_creates_when_missing(mocker):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value={
            "_id": 1,
            "model_id": "host",
            "attrs": json.dumps([{"attr_id": "ip_addr", "attr_name": "内网IP"}]),
        },
    )
    create = mocker.patch(
        "apps.cmdb.services.model.ModelManage.create_model_attr",
        return_value=dict(HOST_NODE_ID_ATTR),
    )

    created = ensure_host_node_id_attr(username="tester")

    assert created is True
    create.assert_called_once()
    attr_info = create.call_args.args[1]
    assert attr_info["attr_id"] == "node_id"
    assert attr_info["editable"] is True
    assert attr_info["is_only"] is True
    assert attr_info["is_required"] is False


def test_ensure_host_node_id_attr_noop_when_present(mocker):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value={
            "_id": 1,
            "model_id": "host",
            "attrs": json.dumps(
                [{"attr_id": "node_id", "attr_name": "节点ID", "editable": True}]
            ),
        },
    )
    create = mocker.patch("apps.cmdb.services.model.ModelManage.create_model_attr")

    created = ensure_host_node_id_attr(username="tester")

    assert created is False
    create.assert_not_called()


def test_ensure_host_node_id_attr_treats_duplicate_as_noop(mocker):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value={"_id": 1, "model_id": "host", "attrs": "[]"},
    )
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.create_model_attr",
        side_effect=BaseAppException("model attr repetition"),
    )

    assert ensure_host_node_id_attr() is False


def test_ingest_calls_ensure_host_node_id_attr(mocker):
    ensure = mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_host_node_id_attr",
        return_value=False,
    )
    mocker.patch.object(CmdbModuleIngestService, "_find_by_node_id", return_value=None)
    mocker.patch.object(CmdbModuleIngestService, "_find_host_by_ip_cloud", return_value=None)
    mocker.patch.object(
        CmdbModuleIngestService,
        "_create_host",
        return_value={"_id": 30, "node_id": "n3"},
    )
    CmdbModuleIngestService.ingest(
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
    ensure.assert_called_once_with(username="tester")


def test_claim_host_passes_node_id_to_instance_update(mocker):
    update = mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.instance_update",
        return_value={"_id": 20, "node_id": "n2"},
    )
    existing = {"_id": 20, "ip_addr": "1.1.1.2", "cloud": 1}
    desired = {
        "inst_name": "h2",
        "ip_addr": "1.1.1.2",
        "organization": [1],
        "cloud": 1,
        "os_type": "1",
        "node_id": "n2",
    }

    CmdbModuleIngestService._claim_host(
        existing,
        desired,
        operator="tester",
        allowed_org_ids=[1],
    )

    assert update.call_args.kwargs["update_attr"]["node_id"] == "n2"


def test_update_host_passes_node_id_when_changed(mocker):
    update = mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.instance_update",
        return_value={"_id": 10, "node_id": "n1-new"},
    )
    existing = {"_id": 10, "node_id": "n1-old", "ip_addr": "1.1.1.1", "cloud": 1}
    desired = {
        "inst_name": "h1",
        "ip_addr": "1.1.1.1",
        "organization": [1],
        "cloud": 1,
        "os_type": "1",
        "node_id": "n1-new",
    }

    CmdbModuleIngestService._update_host(
        existing,
        desired,
        operator="tester",
        allowed_org_ids=[1],
    )

    assert update.call_args.kwargs["update_attr"]["node_id"] == "n1-new"


def test_ingest_host_upserts_by_node_id(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_host_node_id_attr",
        return_value=False,
    )
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
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_host_node_id_attr",
        return_value=False,
    )
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
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_host_node_id_attr",
        return_value=False,
    )
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
