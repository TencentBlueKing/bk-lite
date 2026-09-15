from apps.cmdb.constants.constants import NETWORK_STATUS_TOPOLOGY_MAX_NODES
from apps.cmdb.nats import nats as N
from apps.core.exceptions.base_app_exception import BaseAppException

USER_INFO = {"user": "alice", "domain": "domain.com", "team": 1, "include_children": False}
SWITCH_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PEER_UUID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _allow_permission_map(*_args, **_kwargs):
    return {1: {}}


def test_network_topology_by_uuid_rejects_invalid_uuid():
    result = N.network_topology_by_uuid(inst_uuid="not-a-uuid", user_info=USER_INFO)

    assert result["result"] is False
    assert result["data"]["code"] == "invalid_inst_uuid"


def test_network_topology_by_uuid_rejects_depth_other_than_one(monkeypatch):
    queried = {"called": False}

    def fake_query(_uuid):
        queried["called"] = True
        return {"inst_uuid": SWITCH_UUID, "model_id": "switch"}

    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuid", fake_query)

    result = N.network_topology_by_uuid(inst_uuid=SWITCH_UUID, depth=2, user_info=USER_INFO)

    assert queried["called"] is False
    assert result["result"] is False
    assert result["message"] == "depth 仅支持 1"


def test_network_topology_by_uuid_rejects_missing_instance(monkeypatch):
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuid", lambda _uuid: None)

    result = N.network_topology_by_uuid(inst_uuid=SWITCH_UUID, depth=1, user_info=USER_INFO)

    assert result["result"] is False
    assert result["data"]["code"] == "not_found"


def test_network_topology_by_uuid_rejects_non_network_device(monkeypatch):
    monkeypatch.setattr(
        N.InstanceManage,
        "query_entity_by_uuid",
        lambda _uuid: {"inst_uuid": SWITCH_UUID, "model_id": "host"},
    )
    monkeypatch.setattr(
        "apps.cmdb.services.topology_theme.is_network_device_model",
        lambda _model_id: False,
    )

    result = N.network_topology_by_uuid(inst_uuid=SWITCH_UUID, depth=1, user_info=USER_INFO)

    assert result["result"] is False
    assert result["message"] == "仅网络设备支持一跳拓扑"


def test_network_topology_by_uuid_fails_closed_when_permission_map_is_none(monkeypatch):
    monkeypatch.setattr(
        N.InstanceManage,
        "query_entity_by_uuid",
        lambda _uuid: {"inst_uuid": SWITCH_UUID, "model_id": "switch"},
    )
    monkeypatch.setattr("apps.cmdb.services.topology_theme.is_network_device_model", lambda _model_id: True)
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda *args, **kwargs: None)

    called = {"by_uuid": False}

    def reject(*_args, **_kwargs):
        called["by_uuid"] = True
        return {}

    monkeypatch.setattr(N.InstanceManage, "network_topology_by_uuid", reject)

    result = N.network_topology_by_uuid(inst_uuid=SWITCH_UUID, depth=1, user_info=USER_INFO)

    assert called["by_uuid"] is False
    assert result["result"] is False
    assert result["data"]["code"] == "permission_denied"


def test_network_topology_by_uuid_expands_one_hop(monkeypatch):
    captured = {}
    topology = {
        "center": {"id": SWITCH_UUID, "hop": 0},
        "nodes": [
            {"id": SWITCH_UUID, "model_id": "switch", "name": "core", "hop": 0},
            {"id": PEER_UUID, "model_id": "switch", "name": "peer", "hop": 1},
        ],
        "links": [{"relationship_id": "rel-1", "source_device": SWITCH_UUID, "target_device": PEER_UUID}],
        "truncated": False,
    }

    def fake_by_uuid(inst_uuid, model_id, depth=1, permission_map=None, user=None, node_limit=None):
        captured["args"] = {
            "inst_uuid": inst_uuid,
            "model_id": model_id,
            "depth": depth,
            "node_limit": node_limit,
        }
        return topology

    monkeypatch.setattr(N, "_build_nats_permission_map", _allow_permission_map)
    monkeypatch.setattr(
        N.InstanceManage,
        "query_entity_by_uuid",
        lambda _uuid: {"inst_uuid": SWITCH_UUID, "model_id": "switch"},
    )
    monkeypatch.setattr("apps.cmdb.services.topology_theme.is_network_device_model", lambda _model_id: True)
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(N.InstanceManage, "network_topology_by_uuid", fake_by_uuid)

    result = N.network_topology_by_uuid(
        inst_uuid=SWITCH_UUID,
        depth=1,
        node_limit=80,
        user_info=USER_INFO,
    )

    assert captured["args"]["inst_uuid"] == SWITCH_UUID
    assert captured["args"]["model_id"] == "switch"
    assert captured["args"]["depth"] == 1
    assert captured["args"]["node_limit"] == 80
    assert result == {
        "result": True,
        "message": "",
        "data": {
            "center": topology["center"],
            "nodes": topology["nodes"],
            "links": topology["links"],
            "truncated": False,
        },
    }


def test_network_topology_by_uuid_rejects_over_limit_node_limit():
    result = N.network_topology_by_uuid(
        inst_uuid=SWITCH_UUID,
        depth=1,
        node_limit=NETWORK_STATUS_TOPOLOGY_MAX_NODES + 1,
        user_info=USER_INFO,
    )

    assert result["result"] is False
    assert "node_limit" in result["message"]


def test_network_topology_by_uuid_maps_business_rejection(monkeypatch):
    monkeypatch.setattr(N, "_build_nats_permission_map", _allow_permission_map)
    monkeypatch.setattr(
        N.InstanceManage,
        "query_entity_by_uuid",
        lambda _uuid: {"inst_uuid": SWITCH_UUID, "model_id": "switch"},
    )
    monkeypatch.setattr("apps.cmdb.services.topology_theme.is_network_device_model", lambda _model_id: True)
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        lambda *_args, **_kwargs: True,
    )

    def reject(*_args, **_kwargs):
        raise BaseAppException("实例不存在！")

    monkeypatch.setattr(N.InstanceManage, "network_topology_by_uuid", reject)

    result = N.network_topology_by_uuid(inst_uuid=SWITCH_UUID, depth=1, user_info=USER_INFO)

    assert result["result"] is False
    assert result["data"]["code"] == "not_found"
