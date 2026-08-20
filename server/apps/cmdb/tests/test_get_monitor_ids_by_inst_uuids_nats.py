from apps.cmdb.constants.constants import NETWORK_STATUS_TOPOLOGY_MAX_NODES
from apps.cmdb.nats import nats as N

USER_INFO = {"user": "alice", "domain": "domain.com", "team": 1, "include_children": False}


def test_get_monitor_ids_rejects_more_than_node_limit():
    result = N.get_monitor_ids_by_inst_uuids(
        inst_uuids=[f"00000000-0000-4000-8000-{i:012d}" for i in range(NETWORK_STATUS_TOPOLOGY_MAX_NODES + 1)],
        user_info=USER_INFO,
    )
    assert result["result"] is False
    assert result["data"] == {"items": []}


def test_get_monitor_ids_returns_empty_monitor_id_and_omits_missing(monkeypatch):
    visible = [
        {"inst_uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "model_id": "switch", "monitor_id": "mon-1"},
        {"inst_uuid": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "model_id": "router", "monitor_id": ""},
    ]
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: {1: {}})
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuids", lambda uuids: visible)
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        staticmethod(lambda instance, permission_map, user=None: True),
    )

    result = N.get_monitor_ids_by_inst_uuids(
        inst_uuids=[
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
        ],
        user_info=USER_INFO,
    )

    assert result == {
        "result": True,
        "message": "",
        "data": {
            "items": [
                {
                    "inst_uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    "model_id": "switch",
                    "monitor_id": "mon-1",
                },
                {
                    "inst_uuid": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                    "model_id": "router",
                    "monitor_id": "",
                },
            ]
        },
    }


def test_get_monitor_ids_omits_unauthorized_instances(monkeypatch):
    entities = [
        {"inst_uuid": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "model_id": "switch", "monitor_id": "mon-1"},
        {"inst_uuid": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "model_id": "host", "monitor_id": "mon-2"},
    ]
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: {1: {}})
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuids", lambda uuids: entities)
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        staticmethod(lambda instance, permission_map, user=None: instance["model_id"] == "switch"),
    )

    result = N.get_monitor_ids_by_inst_uuids(
        inst_uuids=[
            "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        ],
        user_info=USER_INFO,
    )

    assert [item["inst_uuid"] for item in result["data"]["items"]] == ["aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"]


def test_get_monitor_ids_dedupes_and_does_not_pass_duplicates_to_query(monkeypatch):
    seen = {}

    def fake_query(uuids):
        seen["uuids"] = list(uuids)
        return [
            {"inst_uuid": uuids[0], "model_id": "switch", "monitor_id": "mon-1"},
        ]

    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: {1: {}})
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuids", fake_query)
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        staticmethod(lambda instance, permission_map, user=None: True),
    )

    uuid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    result = N.get_monitor_ids_by_inst_uuids(inst_uuids=[uuid, uuid], user_info=USER_INFO)

    assert seen["uuids"] == [uuid]
    assert len(result["data"]["items"]) == 1


def test_get_monitor_ids_returns_empty_when_permission_map_is_none(monkeypatch):
    queried = {"called": False}

    def fake_query(uuids):
        queried["called"] = True
        return [
            {"inst_uuid": uuids[0], "model_id": "switch", "monitor_id": "mon-1"},
        ]

    monkeypatch.setattr(N, "_build_nats_permission_map", lambda _user_info: None)
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuids", fake_query)
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        staticmethod(lambda instance, permission_map, user=None: True),
    )

    result = N.get_monitor_ids_by_inst_uuids(
        inst_uuids=["aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"],
        user_info=USER_INFO,
    )

    assert queried["called"] is False
    assert result == {"result": True, "data": {"items": []}, "message": ""}
