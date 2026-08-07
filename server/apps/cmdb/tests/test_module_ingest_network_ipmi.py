"""CMDB module ingest：网络设备 + physcial_server IPMI 认领。"""

import json

import pytest

from apps.cmdb.services.module_ingest import (
    HOST_NODE_ID_ATTR,
    CmdbModuleIngestService,
    ensure_model_node_id_attr,
)
from apps.core.exceptions.base_app_exception import BaseAppException
from apps.node_mgmt.services.module_push_contract import LINK_CONFLICT


def _ingest_params(
    *,
    node_id: str = "sw-n1",
    ip: str = "10.0.0.1",
    model_id: str = "switch",
    **overrides,
):
    raw = {
        "model_id": model_id,
        "ip": ip,
        "organization_ids": [1],
        "name": f"{model_id}-1",
    }
    base = {
        "source_module": "node_mgmt",
        "source_id": node_id,
        "event_type": "upsert",
        "occurred_at": "2026-08-05T00:00:00Z",
        "raw": raw,
        "link_ids": {"node_id": node_id},
        "allowed_org_ids": [1],
        "operator": "tester",
    }
    base.update(overrides)
    if "raw" in overrides and isinstance(overrides["raw"], dict):
        # 允许完全覆盖 raw；否则合并 model_id 默认值
        pass
    return base


# ----- ensure_model_node_id_attr -----


def test_ensure_model_node_id_attr_creates_for_switch(mocker):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value={
            "_id": 2,
            "model_id": "switch",
            "attrs": json.dumps([{"attr_id": "ip_addr", "attr_name": "管理IP"}]),
        },
    )
    create = mocker.patch(
        "apps.cmdb.services.model.ModelManage.create_model_attr",
        return_value=dict(HOST_NODE_ID_ATTR),
    )

    assert ensure_model_node_id_attr("switch", username="tester") is True
    create.assert_called_once()
    assert create.call_args.args[0] == "switch"
    assert create.call_args.args[1]["attr_id"] == "node_id"


def test_ensure_model_node_id_attr_ready_when_present(mocker):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value={
            "_id": 2,
            "model_id": "switch",
            "attrs": json.dumps(
                [{"attr_id": "node_id", "attr_name": "节点ID", "editable": True}]
            ),
        },
    )
    create = mocker.patch("apps.cmdb.services.model.ModelManage.create_model_attr")

    assert ensure_model_node_id_attr("switch") is True
    create.assert_not_called()


def test_ensure_model_node_id_attr_treats_duplicate_as_ready(mocker):
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.search_model_info",
        return_value={"_id": 2, "model_id": "switch", "attrs": "[]"},
    )
    mocker.patch(
        "apps.cmdb.services.model.ModelManage.create_model_attr",
        side_effect=BaseAppException("model attr repetition"),
    )

    assert ensure_model_node_id_attr("switch") is True


# ----- routing -----


def test_ingest_routes_raw_model_id_switch_to_switch_queries(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    query = mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.query_entity_by_identity",
        return_value={},
    )
    create = mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.instance_create",
        return_value={"_id": 100, "node_id": "sw-n1", "model_id": "switch"},
    )

    result = CmdbModuleIngestService.ingest(_ingest_params(model_id="switch"))

    assert result["created"] is True
    assert result["id"] == 100
    # 至少一次按 switch + node_id 查询；创建 model_id=switch
    model_ids_queried = {c.args[0] for c in query.call_args_list}
    assert "switch" in model_ids_queried
    assert "host" not in model_ids_queried
    assert create.call_args.kwargs["model_id"] == "switch"


def test_ingest_routes_object_type_fallback(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    query = mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.query_entity_by_identity",
        return_value={},
    )
    mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.instance_create",
        return_value={"_id": 101},
    )

    CmdbModuleIngestService.ingest(
        _ingest_params(
            raw={
                "object_type": "firewall",
                "ip": "10.0.0.2",
                "organization_ids": [1],
            }
        )
    )

    assert {c.args[0] for c in query.call_args_list} == {"firewall"}


def test_ingest_defaults_to_host_when_model_missing(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    query = mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.query_entity_by_identity",
        return_value={},
    )
    mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.instance_create",
        return_value={"_id": 102},
    )

    CmdbModuleIngestService.ingest(
        _ingest_params(
            node_id="n-host",
            raw={"ip": "1.1.1.1", "cloud_region_id": 1, "organization_ids": [1]},
        )
    )

    assert "host" in {c.args[0] for c in query.call_args_list}


def test_ingest_rejects_unsupported_model():
    with pytest.raises(ValueError, match="unsupported"):
        CmdbModuleIngestService.ingest(
            _ingest_params(raw={"model_id": "mysql", "ip": "1.1.1.1", "organization_ids": [1]})
        )


# ----- switch: upsert / claim / conflict / create -----


def test_ingest_switch_upserts_by_node_id(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.query_entity_by_identity",
        return_value={"_id": 10, "node_id": "sw-n1", "ip_addr": "10.0.0.1", "model_id": "switch"},
    )
    update = mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.instance_update",
        return_value={"_id": 10, "node_id": "sw-n1"},
    )

    result = CmdbModuleIngestService.ingest(
        _ingest_params(
            node_id="sw-n1",
            raw={
                "model_id": "switch",
                "ip": "10.0.0.1",
                "organization_ids": [1],
                "name": "sw-core",
            },
        )
    )

    assert result["id"] == 10
    assert result["updated"] is True
    update.assert_called_once()


def test_ingest_switch_claims_by_ip_addr(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )

    def _query(model_id, identity):
        assert model_id == "switch"
        if "node_id" in identity:
            return {}
        if identity.get("ip_addr") == "10.0.0.1":
            return {"_id": 20, "ip_addr": "10.0.0.1", "model_id": "switch"}
        return {}

    mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.query_entity_by_identity",
        side_effect=_query,
    )
    update = mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.instance_update",
        return_value={"_id": 20, "node_id": "sw-n2"},
    )

    result = CmdbModuleIngestService.ingest(
        _ingest_params(node_id="sw-n2", ip="10.0.0.1", model_id="switch")
    )

    assert result["id"] == 20
    assert result["claimed"] is True
    assert update.call_args.kwargs["update_attr"]["node_id"] == "sw-n2"
    # 认领白名单不含 cloud
    assert "cloud" not in update.call_args.kwargs["update_attr"]


def test_ingest_switch_conflict_when_existing_different_node_id(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )

    def _query(model_id, identity):
        assert model_id == "switch"
        if "node_id" in identity:
            return {}
        return {
            "_id": 20,
            "ip_addr": "10.0.0.1",
            "node_id": "other-node",
            "model_id": "switch",
        }

    mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.query_entity_by_identity",
        side_effect=_query,
    )
    update = mocker.patch("apps.cmdb.services.module_ingest.InstanceManage.instance_update")

    result = CmdbModuleIngestService.ingest(
        _ingest_params(node_id="sw-n2", ip="10.0.0.1", model_id="switch")
    )

    assert result["id"] == 20
    assert result["conflict"] == LINK_CONFLICT
    assert result["claimed"] is False
    update.assert_not_called()


def test_ingest_switch_creates_when_miss(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.query_entity_by_identity",
        return_value={},
    )
    create = mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.instance_create",
        return_value={"_id": 30, "node_id": "sw-n3"},
    )

    result = CmdbModuleIngestService.ingest(
        _ingest_params(node_id="sw-n3", ip="10.0.0.3", model_id="switch")
    )

    assert result["id"] == 30
    assert result["created"] is True
    assert create.call_args.kwargs["model_id"] == "switch"
    payload = create.call_args.kwargs["instance_info"]
    assert payload["node_id"] == "sw-n3"
    assert payload["ip_addr"] == "10.0.0.3"
    assert "cloud" not in payload
    assert "os_type" not in payload


# ----- physcial_server (typo preserved) -----


def test_ingest_physcial_server_upserts_by_node_id(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    query = mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.query_entity_by_identity",
        return_value={
            "_id": 40,
            "node_id": "ps-n1",
            "ip_addr": "192.168.1.10",
            "model_id": "physcial_server",
        },
    )
    update = mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.instance_update",
        return_value={"_id": 40, "node_id": "ps-n1"},
    )

    result = CmdbModuleIngestService.ingest(
        _ingest_params(
            node_id="ps-n1",
            raw={
                "model_id": "physcial_server",
                "ip_addr": "192.168.1.10",
                "organization_ids": [1],
                "name": "ps-bmc-1",
            },
        )
    )

    assert result["id"] == 40
    assert result["updated"] is True
    assert query.call_args.args[0] == "physcial_server"
    update.assert_called_once()


def test_ingest_physcial_server_claims_by_ip_addr(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )

    def _query(model_id, identity):
        assert model_id == "physcial_server"
        if "node_id" in identity:
            return {}
        if identity.get("ip_addr") == "192.168.1.10":
            return {"_id": 41, "ip_addr": "192.168.1.10", "model_id": "physcial_server"}
        return {}

    mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.query_entity_by_identity",
        side_effect=_query,
    )
    update = mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.instance_update",
        return_value={"_id": 41, "node_id": "ps-n2"},
    )

    result = CmdbModuleIngestService.ingest(
        _ingest_params(
            node_id="ps-n2",
            raw={
                "model_id": "physcial_server",
                "bmc_ip": "192.168.1.10",
                "organization_ids": [1],
            },
        )
    )

    assert result["id"] == 41
    assert result["claimed"] is True
    assert update.call_args.kwargs["update_attr"]["node_id"] == "ps-n2"
    assert "cloud" not in update.call_args.kwargs["update_attr"]


def test_ingest_physcial_server_conflict_when_existing_different_node_id(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )

    def _query(model_id, identity):
        assert model_id == "physcial_server"
        if "node_id" in identity:
            return {}
        return {
            "_id": 42,
            "ip_addr": "192.168.1.10",
            "node_id": "other-ps",
            "model_id": "physcial_server",
        }

    mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.query_entity_by_identity",
        side_effect=_query,
    )
    update = mocker.patch("apps.cmdb.services.module_ingest.InstanceManage.instance_update")

    result = CmdbModuleIngestService.ingest(
        _ingest_params(
            node_id="ps-n2",
            raw={
                "model_id": "physcial_server",
                "ip": "192.168.1.10",
                "organization_ids": [1],
            },
        )
    )

    assert result["id"] == 42
    assert result["conflict"] == LINK_CONFLICT
    assert result["claimed"] is False
    update.assert_not_called()


def test_ingest_physcial_server_creates_when_miss(mocker):
    mocker.patch(
        "apps.cmdb.services.module_ingest.ensure_model_node_id_attr",
        return_value=True,
    )
    mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.query_entity_by_identity",
        return_value={},
    )
    create = mocker.patch(
        "apps.cmdb.services.module_ingest.InstanceManage.instance_create",
        return_value={"_id": 43, "node_id": "ps-n3"},
    )

    result = CmdbModuleIngestService.ingest(
        _ingest_params(
            node_id="ps-n3",
            raw={
                "model_id": "physcial_server",
                "ip_addr": "192.168.1.11",
                "organization_ids": [1],
                "name": "ps-new",
            },
        )
    )

    assert result["id"] == 43
    assert result["created"] is True
    assert create.call_args.kwargs["model_id"] == "physcial_server"
    payload = create.call_args.kwargs["instance_info"]
    assert payload["ip_addr"] == "192.168.1.11"
    assert "cloud" not in payload
