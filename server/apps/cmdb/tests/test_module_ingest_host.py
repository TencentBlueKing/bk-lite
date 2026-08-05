"""CMDB module ingest：host 的 ID 优先 upsert + 存量认领。"""

import json

import pytest

from apps.cmdb.services.module_ingest import (
    HOST_NODE_ID_ATTR,
    CmdbModuleIngestService,
    ensure_host_node_id_attr,
)
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.services.module_push_contract import LINK_CONFLICT


def _ingest_params(*, node_id: str = "n2", ip: str = "1.1.1.2", **overrides):
    base = {
        "source_module": "node_mgmt",
        "source_id": node_id,
        "event_type": "upsert",
        "occurred_at": "2026-08-05T00:00:00Z",
        "raw": {"ip": ip, "cloud_region_id": 1, "organization_ids": [1]},
        "link_ids": {"node_id": node_id},
        "allowed_org_ids": [1],
        "operator": "tester",
    }
    base.update(overrides)
    return base


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

    ready = ensure_host_node_id_attr(username="tester")

    assert ready is True
    create.assert_called_once()
    attr_info = create.call_args.args[1]
    assert attr_info["attr_id"] == "node_id"
    assert attr_info["editable"] is True
    assert attr_info["is_only"] is True
    assert attr_info["is_required"] is False


def test_ensure_host_node_id_attr_ready_when_present(mocker):
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

    ready = ensure_host_node_id_attr(username="tester")

    assert ready is True
    create.assert_not_called()


def test_ensure_host_node_id_attr_treats_duplicate_as_ready(mocker):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value={"_id": 1, "model_id": "host", "attrs": "[]"},
    )
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.create_model_attr",
        side_effect=BaseAppException("model attr repetition"),
    )

    assert ensure_host_node_id_attr() is True


def test_ensure_host_node_id_attr_false_when_model_missing(mocker):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value=None,
    )
    create = mocker.patch("apps.cmdb.services.model.ModelManage.create_model_attr")

    assert ensure_host_node_id_attr() is False
    create.assert_not_called()


def test_ingest_calls_ensure_model_node_id_attr(mocker):
    ensure = mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    mocker.patch.object(CmdbModuleIngestService, "_find_by_node_id", return_value=None)
    mocker.patch.object(CmdbModuleIngestService, "_find_host_by_ip_cloud", return_value=None)
    mocker.patch.object(
        CmdbModuleIngestService,
        "_create_instance",
        return_value={"_id": 30, "node_id": "n3"},
    )
    CmdbModuleIngestService.ingest(_ingest_params(node_id="n3", ip="1.1.1.3"))
    ensure.assert_called_once_with("host", username="tester")


def test_ingest_raises_when_ensure_model_node_id_attr_fails(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=False,
    )
    find_node = mocker.patch.object(CmdbModuleIngestService, "_find_by_node_id")

    with pytest.raises(ValueError, match="node_id"):
        CmdbModuleIngestService.ingest(_ingest_params())

    find_node.assert_not_called()


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
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    mocker.patch.object(
        CmdbModuleIngestService,
        "_find_by_node_id",
        return_value={"_id": 10, "node_id": "n1", "ip_addr": "1.1.1.1", "cloud": 1},
    )
    update = mocker.patch.object(
        CmdbModuleIngestService,
        "_update_instance",
        return_value={"_id": 10, "node_id": "n1"},
    )
    result = CmdbModuleIngestService.ingest(
        _ingest_params(
            node_id="n1",
            ip="1.1.1.1",
            raw={
                "ip": "1.1.1.1",
                "cloud_region_id": 1,
                "organization_ids": [1],
                "name": "h1",
            },
        )
    )
    assert result["id"] == 10
    assert result["updated"] is True
    update.assert_called_once()


def test_ingest_host_claims_existing_by_ip_cloud(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    mocker.patch.object(CmdbModuleIngestService, "_find_by_node_id", return_value=None)
    mocker.patch.object(
        CmdbModuleIngestService,
        "_find_host_by_ip_cloud",
        return_value={"_id": 20, "ip_addr": "1.1.1.2", "cloud": 1},
    )
    claim = mocker.patch.object(
        CmdbModuleIngestService,
        "_claim_instance",
        return_value={"_id": 20, "node_id": "n2"},
    )
    result = CmdbModuleIngestService.ingest(_ingest_params())
    assert result["id"] == 20
    assert result["claimed"] is True
    claim.assert_called_once()


def test_ingest_claim_conflicts_when_existing_has_different_node_id(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    mocker.patch.object(CmdbModuleIngestService, "_find_by_node_id", return_value=None)
    mocker.patch.object(
        CmdbModuleIngestService,
        "_find_host_by_ip_cloud",
        return_value={
            "_id": 20,
            "ip_addr": "1.1.1.2",
            "cloud": 1,
            "node_id": "other-node",
        },
    )
    claim = mocker.patch.object(CmdbModuleIngestService, "_claim_instance")

    result = CmdbModuleIngestService.ingest(_ingest_params(node_id="n2"))

    assert result["id"] == 20
    assert result["conflict"] == LINK_CONFLICT
    assert result["claimed"] is False
    assert result["updated"] is False
    assert result["created"] is False
    claim.assert_not_called()


def test_ingest_claim_when_existing_node_id_empty(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    mocker.patch.object(CmdbModuleIngestService, "_find_by_node_id", return_value=None)
    mocker.patch.object(
        CmdbModuleIngestService,
        "_find_host_by_ip_cloud",
        return_value={"_id": 20, "ip_addr": "1.1.1.2", "cloud": 1, "node_id": ""},
    )
    claim = mocker.patch.object(
        CmdbModuleIngestService,
        "_claim_instance",
        return_value={"_id": 20, "node_id": "n2"},
    )

    result = CmdbModuleIngestService.ingest(_ingest_params(node_id="n2"))

    assert result["id"] == 20
    assert result["claimed"] is True
    assert result.get("conflict") in (None, "")
    claim.assert_called_once()


def test_ingest_claim_when_existing_same_node_id(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    # node_id 查找未命中（查询异常/时序），但 ip+cloud 命中同 node_id 行 → 认领幂等成功
    mocker.patch.object(CmdbModuleIngestService, "_find_by_node_id", return_value=None)
    mocker.patch.object(
        CmdbModuleIngestService,
        "_find_host_by_ip_cloud",
        return_value={
            "_id": 20,
            "ip_addr": "1.1.1.2",
            "cloud": 1,
            "node_id": "n2",
        },
    )
    claim = mocker.patch.object(
        CmdbModuleIngestService,
        "_claim_instance",
        return_value={"_id": 20, "node_id": "n2"},
    )

    result = CmdbModuleIngestService.ingest(_ingest_params(node_id="n2"))

    assert result["id"] == 20
    assert result["claimed"] is True or result["updated"] is True
    assert result.get("conflict") in (None, "")
    claim.assert_called_once()


def test_ingest_host_creates_when_no_match(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    mocker.patch.object(CmdbModuleIngestService, "_find_by_node_id", return_value=None)
    mocker.patch.object(CmdbModuleIngestService, "_find_host_by_ip_cloud", return_value=None)
    create = mocker.patch.object(
        CmdbModuleIngestService,
        "_create_instance",
        return_value={"_id": 30, "node_id": "n3"},
    )
    result = CmdbModuleIngestService.ingest(_ingest_params(node_id="n3", ip="1.1.1.3"))
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
