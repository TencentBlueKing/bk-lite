from apps.cmdb.constants.constants import NETWORK_STATUS_TOPOLOGY_MAX_NODES
from apps.cmdb.nats import nats as N
from apps.core.exceptions.base_app_exception import BaseAppException

USER_INFO = {"user": "alice", "domain": "domain.com", "team": 1, "include_children": False}
SWITCH_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ROUTER_UUID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
CLOSED_SET_ERROR = "设备列表包含无效或不允许的网络设备，请重新配置"


def _allow_permission_map(*_args, **_kwargs):
    return {1: {}}


def _mark_called(flag):
    def _inner(*_args, **_kwargs):
        flag["among"] = True
        return {}

    return _inner


def test_network_topology_among_uuids_rejects_non_list():
    result = N.network_topology_among_uuids(inst_uuids="not-a-list", user_info=USER_INFO)

    assert result["result"] is False
    assert result["data"] == {"nodes": [], "links": []}
    assert result["message"] == "inst_uuids 必须是列表"


def test_network_topology_among_uuids_rejects_empty(monkeypatch):
    queried = {"called": False}

    def fake_query(uuids):
        queried["called"] = True
        return []

    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuids", fake_query)

    result = N.network_topology_among_uuids(inst_uuids=[], user_info=USER_INFO)

    assert queried["called"] is False
    assert result == {
        "result": False,
        "data": {"nodes": [], "links": []},
        "message": CLOSED_SET_ERROR,
    }


def test_network_topology_among_uuids_rejects_more_than_node_limit(monkeypatch):
    queried = {"called": False}

    def fake_query(uuids):
        queried["called"] = True
        return []

    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuids", fake_query)

    result = N.network_topology_among_uuids(
        inst_uuids=[f"00000000-0000-4000-8000-{i:012d}" for i in range(NETWORK_STATUS_TOPOLOGY_MAX_NODES + 1)],
        user_info=USER_INFO,
    )

    assert queried["called"] is False
    assert result["result"] is False
    assert result["data"] == {"nodes": [], "links": []}
    assert result["message"] == f"inst_uuids 不能超过 {NETWORK_STATUS_TOPOLOGY_MAX_NODES}"


def test_network_topology_among_uuids_rejects_duplicates_and_invalid_uuid(monkeypatch):
    queried = {"called": False}

    def fake_query(uuids):
        queried["called"] = True
        return []

    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuids", fake_query)

    duplicated = N.network_topology_among_uuids(inst_uuids=[SWITCH_UUID, SWITCH_UUID], user_info=USER_INFO)
    invalid = N.network_topology_among_uuids(inst_uuids=["not-a-uuid"], user_info=USER_INFO)

    assert queried["called"] is False
    assert duplicated["result"] is False
    assert duplicated["message"] == CLOSED_SET_ERROR
    assert invalid["result"] is False
    assert invalid["message"] == CLOSED_SET_ERROR


def test_network_topology_among_uuids_rejects_null_and_blank_slots(monkeypatch):
    queried = {"called": False}

    def fake_query(uuids):
        queried["called"] = True
        return []

    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuids", fake_query)

    with_none = N.network_topology_among_uuids(inst_uuids=[SWITCH_UUID, None], user_info=USER_INFO)
    with_blank = N.network_topology_among_uuids(inst_uuids=[SWITCH_UUID, ""], user_info=USER_INFO)

    assert queried["called"] is False
    assert with_none == {
        "result": False,
        "data": {"nodes": [], "links": []},
        "message": CLOSED_SET_ERROR,
    }
    assert with_blank == {
        "result": False,
        "data": {"nodes": [], "links": []},
        "message": CLOSED_SET_ERROR,
    }


def test_network_topology_among_uuids_fails_closed_when_entity_missing(monkeypatch):
    called = {"among": False}
    monkeypatch.setattr(
        N.InstanceManage,
        "query_entity_by_uuids",
        lambda uuids: [{"inst_uuid": SWITCH_UUID, "model_id": "switch"}],
    )
    monkeypatch.setattr(
        N.InstanceManage,
        "network_topology_among_uuids",
        _mark_called(called),
    )

    result = N.network_topology_among_uuids(
        inst_uuids=[SWITCH_UUID, ROUTER_UUID],
        user_info=USER_INFO,
    )

    assert called["among"] is False
    assert result == {
        "result": False,
        "data": {"nodes": [], "links": []},
        "message": CLOSED_SET_ERROR,
    }


def test_network_topology_among_uuids_fails_closed_when_permission_map_is_none(monkeypatch):
    called = {"among": False}
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        N.InstanceManage,
        "query_entity_by_uuids",
        lambda uuids: [{"inst_uuid": SWITCH_UUID, "model_id": "switch"}],
    )
    monkeypatch.setattr(
        N.InstanceManage,
        "network_topology_among_uuids",
        _mark_called(called),
    )

    result = N.network_topology_among_uuids(inst_uuids=[SWITCH_UUID], user_info=USER_INFO)

    assert called["among"] is False
    assert result == {
        "result": False,
        "data": {"nodes": [], "links": []},
        "message": CLOSED_SET_ERROR,
    }


def test_network_topology_among_uuids_maps_business_rejection_to_closed_set(monkeypatch):
    monkeypatch.setattr(N, "_build_nats_permission_map", _allow_permission_map)
    monkeypatch.setattr(
        N.InstanceManage,
        "query_entity_by_uuids",
        lambda uuids: [{"inst_uuid": SWITCH_UUID, "model_id": "host"}],
    )

    def reject(*_args, **_kwargs):
        raise BaseAppException(CLOSED_SET_ERROR)

    monkeypatch.setattr(N.InstanceManage, "network_topology_among_uuids", reject)

    result = N.network_topology_among_uuids(inst_uuids=[SWITCH_UUID], user_info=USER_INFO)

    assert result == {
        "result": False,
        "data": {"nodes": [], "links": []},
        "message": CLOSED_SET_ERROR,
    }


def test_network_topology_among_uuids_returns_nodes_and_links(monkeypatch):
    captured = {}
    topology = {
        "nodes": [{"id": SWITCH_UUID, "model_id": "switch", "name": "core", "hop": 0}],
        "links": [{"relationship_id": "rel-1", "source_device": SWITCH_UUID, "target_device": ROUTER_UUID}],
        "truncated": False,
    }

    def fake_among(uuids, permission_maps=None, user=None):
        captured["uuids"] = list(uuids)
        captured["permission_maps"] = permission_maps
        captured["user"] = user
        return topology

    monkeypatch.setattr(N, "_build_nats_permission_map", _allow_permission_map)
    monkeypatch.setattr(
        N.InstanceManage,
        "query_entity_by_uuids",
        lambda uuids: [
            {"inst_uuid": SWITCH_UUID, "model_id": "switch"},
            {"inst_uuid": ROUTER_UUID, "model_id": "router"},
        ],
    )
    monkeypatch.setattr(N.InstanceManage, "network_topology_among_uuids", fake_among)

    result = N.network_topology_among_uuids(
        inst_uuids=[SWITCH_UUID, ROUTER_UUID],
        user_info=USER_INFO,
    )

    assert captured["uuids"] == [SWITCH_UUID, ROUTER_UUID]
    assert set(captured["permission_maps"]) == {"switch", "router"}
    assert getattr(captured["user"], "username", None) == "alice"
    assert result == {
        "result": True,
        "message": "",
        "data": {
            "nodes": topology["nodes"],
            "links": topology["links"],
            "truncated": False,
        },
    }
