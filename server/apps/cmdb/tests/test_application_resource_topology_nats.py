from apps.cmdb.nats import nats as N

CENTER_UUID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
USER_INFO = {"user": "alice", "domain": "domain.com", "team": 1, "include_children": False}


def _system():
    return {"inst_uuid": CENTER_UUID, "model_id": "system", "_id": 11, "_creator": "alice"}


def _allow(monkeypatch, entity):
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda user_info, model_id="": {1: {}})
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuid", lambda inst_uuid: entity)
    monkeypatch.setattr(
        N.InstanceManage,
        "_has_topology_view_permission",
        staticmethod(lambda instance, permission_map, user=None: True),
    )


def test_application_topology_nats_rejects_invalid_uuid(monkeypatch):
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuid", lambda inst_uuid: _system())
    result = N.application_resource_topology_by_uuid(inst_uuid="not-a-uuid", user_info=USER_INFO)
    assert result["result"] is False
    assert result["data"]["code"] == "invalid_inst_uuid"


def test_application_topology_nats_rejects_non_system_model(monkeypatch):
    _allow(monkeypatch, {**_system(), "model_id": "host"})
    host = N.application_resource_topology_by_uuid(inst_uuid=CENTER_UUID, user_info=USER_INFO)
    assert host["result"] is False
    assert host["data"]["code"] == "unsupported_model"

    _allow(monkeypatch, {**_system(), "model_id": "application"})
    application = N.application_resource_topology_by_uuid(inst_uuid=CENTER_UUID, user_info=USER_INFO)
    assert application["result"] is False
    assert application["data"]["code"] == "unsupported_model"
    assert application["message"] == "应用拓扑仅支持应用系统"


def test_application_topology_nats_uses_instance_model_and_depth(monkeypatch):
    captured = {}
    _allow(monkeypatch, _system())

    def fake_build(inst_id, model_id, depth=1, permission_map=None, user=None):
        captured["args"] = {"inst_id": inst_id, "model_id": model_id, "depth": depth}
        return {"center": {"id": CENTER_UUID}, "nodes": [], "links": [], "truncated": False}

    monkeypatch.setattr(
        "apps.cmdb.services.application_resource_overview.ApplicationResourceOverviewService.build_application_topology",
        staticmethod(fake_build),
    )
    result = N.application_resource_topology_by_uuid(inst_uuid=CENTER_UUID, depth=4, user_info=USER_INFO, model_id="host")
    assert result["result"] is True
    assert captured["args"]["model_id"] == "system"
    assert captured["args"]["depth"] == 4
    assert captured["args"]["inst_id"] == 11


def test_application_topology_nats_defaults_depth_and_denies_without_permission(monkeypatch):
    monkeypatch.setattr(N, "_build_nats_permission_map", lambda user_info, model_id="": None)
    monkeypatch.setattr(N.InstanceManage, "query_entity_by_uuid", lambda inst_uuid: _system())
    result = N.application_resource_topology_by_uuid(inst_uuid=CENTER_UUID, user_info=USER_INFO)
    assert result["result"] is False
    assert result["data"]["code"] == "permission_denied"
