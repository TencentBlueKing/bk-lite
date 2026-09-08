from apps.cmdb.nats import nats as N
from apps.core.exceptions.base_app_exception import BaseAppException

CENTER_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
NEIGHBOR_UUID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
USER_INFO = {"user": "alice", "domain": "domain.com", "team": 1, "include_children": False}

EMPTY_TREE = {
    "src_result": {
        "inst_uuid": CENTER_UUID,
        "inst_name": "core-host",
        "model_id": "host",
        "children": [],
    },
    "dst_result": {
        "inst_uuid": CENTER_UUID,
        "inst_name": "core-host",
        "model_id": "host",
        "children": [],
    },
}

NEIGHBOR_TREE = {
    "src_result": {
        "inst_uuid": CENTER_UUID,
        "inst_name": "core-host",
        "model_id": "host",
        "children": [
            {
                "inst_uuid": NEIGHBOR_UUID,
                "inst_name": "edge-switch",
                "model_id": "switch",
                "asst_id": "connect",
                "children": [],
            }
        ],
    },
    "dst_result": {
        "inst_uuid": CENTER_UUID,
        "inst_name": "core-host",
        "model_id": "host",
        "children": [],
    },
}


def _center_entity():
    return {"inst_uuid": CENTER_UUID, "model_id": "host", "_id": 11, "_creator": "alice"}


def test_topo_search_lite_rejects_invalid_uuid_without_querying(monkeypatch):
    queried = {"called": False}

    def fake_query(inst_uuid):
        queried["called"] = True
        return _center_entity()

    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuid", fake_query)

    result = N.topo_search_lite_by_uuid(inst_uuid="not-a-uuid", user_info=USER_INFO)

    assert queried["called"] is False
    assert result["result"] is False
    assert result["data"]["code"] == "invalid_inst_uuid"


def test_topo_search_lite_does_not_require_model_id(monkeypatch):
    captured = {}
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda user_info, model_id="": {1: {}})
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuid", lambda inst_uuid: _center_entity())
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        staticmethod(lambda instance, permission_map, user=None: True),
    )

    def fake_topo(inst_uuid, depth=3, permission_map=None, user=None, language=None):
        captured["kwargs"] = {
            "inst_uuid": inst_uuid,
            "depth": depth,
            "permission_map": permission_map,
            "user": user,
            "language": language,
        }
        return EMPTY_TREE

    monkeypatch.setattr(N.InstanceManage, "topo_search_lite_by_uuid", fake_topo)

    result = N.topo_search_lite_by_uuid(inst_uuid=CENTER_UUID, user_info=USER_INFO, model_id="should-be-ignored")

    assert result == {"result": True, "data": EMPTY_TREE, "message": ""}
    assert captured["kwargs"]["inst_uuid"] == CENTER_UUID
    assert captured["kwargs"]["depth"] == 3
    assert captured["kwargs"]["permission_map"] == {1: {}}
    assert captured["kwargs"]["language"] == "zh-Hans"


def test_topo_search_lite_not_found_is_failure_not_empty_graph(monkeypatch):
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda user_info, model_id="": {1: {}})
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuid", lambda inst_uuid: None)
    called = {"topo": False}

    def fake_topo(*args, **kwargs):
        called["topo"] = True
        return EMPTY_TREE

    monkeypatch.setattr(N.InstanceManage, "topo_search_lite_by_uuid", fake_topo)

    result = N.topo_search_lite_by_uuid(inst_uuid=CENTER_UUID, user_info=USER_INFO)

    assert called["topo"] is False
    assert result["result"] is False
    assert result["data"]["code"] == "not_found"
    assert "src_result" not in result["data"]


def test_topo_search_lite_permission_denied_is_failure_not_empty_graph(monkeypatch):
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda user_info, model_id="": {1: {}})
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuid", lambda inst_uuid: _center_entity())
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        staticmethod(lambda instance, permission_map, user=None: False),
    )
    called = {"topo": False}
    monkeypatch.setattr(
        N.InstanceManage,
        "topo_search_lite_by_uuid",
        lambda *args, **kwargs: called.__setitem__("topo", True) or EMPTY_TREE,
    )

    result = N.topo_search_lite_by_uuid(inst_uuid=CENTER_UUID, user_info=USER_INFO)

    assert called["topo"] is False
    assert result["result"] is False
    assert result["data"]["code"] == "permission_denied"
    assert "src_result" not in result["data"]


def test_topo_search_lite_missing_permission_map_is_permission_denied(monkeypatch):
    queried = {"called": False}

    def fake_query(inst_uuid):
        queried["called"] = True
        return _center_entity()

    monkeypatch.setattr(N, "_build_nats_permission_map", lambda user_info, model_id="": None)
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuid", fake_query)
    monkeypatch.setattr(
        N.InstanceManage,
        "topo_search_lite_by_uuid",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not search when permission map is missing")),
    )

    result = N.topo_search_lite_by_uuid(inst_uuid=CENTER_UUID, user_info=USER_INFO)

    assert queried["called"] is True
    assert result["result"] is False
    assert result["data"]["code"] == "permission_denied"


def test_topo_search_lite_empty_neighbors_is_success(monkeypatch):
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda user_info, model_id="": {1: {}})
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuid", lambda inst_uuid: _center_entity())
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        staticmethod(lambda instance, permission_map, user=None: True),
    )
    monkeypatch.setattr(N.InstanceManage, "topo_search_lite_by_uuid", lambda *args, **kwargs: EMPTY_TREE)

    result = N.topo_search_lite_by_uuid(inst_uuid=CENTER_UUID, user_info=USER_INFO)

    assert result["result"] is True
    assert result["data"]["src_result"]["children"] == []
    assert result["data"]["dst_result"]["children"] == []
    assert result["data"]["src_result"]["inst_uuid"] == CENTER_UUID


def test_topo_search_lite_returns_lite_tree_and_passes_permission_map(monkeypatch):
    captured = {}
    permission_map = {1: {"inst_names": []}}
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda user_info, model_id="": permission_map)
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuid", lambda inst_uuid: _center_entity())
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        staticmethod(lambda instance, permission_map, user=None: True),
    )

    def fake_topo(inst_uuid, depth=3, permission_map=None, user=None, language=None):
        captured["permission_map"] = permission_map
        captured["user"] = getattr(user, "username", user)
        captured["language"] = language
        return NEIGHBOR_TREE

    monkeypatch.setattr(N.InstanceManage, "topo_search_lite_by_uuid", fake_topo)

    result = N.topo_search_lite_by_uuid(inst_uuid=CENTER_UUID, user_info=USER_INFO)

    assert result == {"result": True, "data": NEIGHBOR_TREE, "message": ""}
    assert captured["permission_map"] is permission_map
    assert captured["user"] == "alice"
    assert captured["language"] == "zh-Hans"


def test_topo_search_lite_builds_permission_map_with_instance_model(monkeypatch):
    captured = {}

    def fake_build(user_info, model_id=""):
        captured["model_id"] = model_id
        return {1: {}}

    monkeypatch.setattr(N, "_build_nats_permission_map", fake_build)
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuid", lambda inst_uuid: _center_entity())
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        staticmethod(lambda instance, permission_map, user=None: True),
    )
    monkeypatch.setattr(N.InstanceManage, "topo_search_lite_by_uuid", lambda *args, **kwargs: EMPTY_TREE)

    N.topo_search_lite_by_uuid(inst_uuid=CENTER_UUID, user_info=USER_INFO)

    assert captured["model_id"] == "host"


def test_topo_search_lite_maps_service_missing_instance_to_not_found(monkeypatch):
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda user_info, model_id="": {1: {}})
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuid", lambda inst_uuid: _center_entity())
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        staticmethod(lambda instance, permission_map, user=None: True),
    )

    def fake_topo(*args, **kwargs):
        raise BaseAppException("实例不存在！")

    monkeypatch.setattr(N.InstanceManage, "topo_search_lite_by_uuid", fake_topo)

    result = N.topo_search_lite_by_uuid(inst_uuid=CENTER_UUID, user_info=USER_INFO)

    assert result["result"] is False
    assert result["data"]["code"] == "not_found"
