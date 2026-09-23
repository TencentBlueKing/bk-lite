"""CMDB LLM tools: NATS RPC wrappers with caller_identity."""

from unittest.mock import patch

import pytest

from apps.opspilot.metis.llm.tools import cmdb as cmdb_tools
from apps.opspilot.metis.llm.tools.cmdb import instances as inst
from apps.opspilot.metis.llm.tools.cmdb import models as mdl
from apps.opspilot.metis.llm.tools.cmdb.utils import call_cmdb_params

_CMDB_TOOL_CASES = [
    ("cmdb_list_models", {}, "search_models_for_llm", False, {}),
    ("cmdb_get_model_info", {"model_id": "host"}, "get_model_info", False, {"model_id": "host"}),
    ("cmdb_list_model_attrs", {"model_id": "host"}, "search_model_attrs_for_llm", False, {"model_id": "host"}),
    ("cmdb_get_instance", {"inst_uuid": "u1"}, "get_instance_by_uuid", False, {"inst_uuid": "u1"}),
    (
        "cmdb_get_monitor_ids",
        {"inst_uuids": ["u1"]},
        "get_monitor_ids_by_inst_uuids",
        True,
        {"inst_uuids": ["u1"]},
    ),
    (
        "cmdb_create_instance",
        {"model_id": "host", "instance_info": {"inst_name": "box1"}},
        "create_instance_for_llm",
        False,
        {"model_id": "host", "instance_info": {"inst_name": "box1"}},
    ),
    (
        "cmdb_update_instance",
        {"inst_uuid": "u1", "update_data": {"inst_name": "n2"}},
        "update_instance_for_llm",
        False,
        {"inst_uuid": "u1", "update_attr": {"inst_name": "n2"}},
    ),
    (
        "cmdb_batch_update_instances",
        {"inst_uuids": ["u1"], "update_data": {"k": "v"}},
        "batch_update_instances",
        False,
        {"inst_uuids": ["u1"], "update_attr": {"k": "v"}},
    ),
    ("cmdb_delete_instance", {"inst_uuid": "u1"}, "delete_instance_for_llm", False, {"inst_uuid": "u1"}),
    ("cmdb_batch_delete_instances", {"inst_uuids": ["u1"]}, "delete_instance_for_llm", False, {"inst_uuids": ["u1"]}),
    ("cmdb_topo_search", {"inst_uuid": "u1", "depth": 2}, "topo_search_lite_by_uuid", True, {"inst_uuid": "u1", "depth": 2}),
    (
        "cmdb_topo_expand",
        {"inst_uuid": "u1", "parent_uuids": ["p1"], "depth": 1},
        "topo_search_expand_by_uuid",
        True,
        {"inst_uuid": "u1", "parent_uuids": ["p1"], "depth": 1},
    ),
    ("cmdb_list_model_associations", {"model_id": "host"}, "search_model_associations", False, {"model_id": "host"}),
    (
        "cmdb_list_instance_associations",
        {"model_id": "host", "inst_uuid": "u1"},
        "search_instance_associations_for_llm",
        False,
        {"model_id": "host", "inst_uuid": "u1"},
    ),
    (
        "cmdb_list_associated_instances",
        {"model_id": "host", "inst_uuid": "u1"},
        "search_instance_associations_for_llm",
        False,
        {"model_id": "host", "inst_uuid": "u1"},
    ),
    (
        "cmdb_create_instance_association",
        {"data": {"src_inst_uuid": "s1", "dst_inst_uuid": "d1", "model_asst_id": "host_run_app"}},
        "create_instance_association_for_llm",
        False,
        {"src_inst_uuid": "s1", "dst_inst_uuid": "d1", "model_asst_id": "host_run_app"},
    ),
    (
        "cmdb_delete_instance_association",
        {"src_inst_uuid": "s1", "dst_inst_uuid": "d1", "model_asst_id": "host_run_app"},
        "delete_instance_association_for_llm",
        False,
        {"src_inst_uuid": "s1", "dst_inst_uuid": "d1", "model_asst_id": "host_run_app"},
    ),
    ("cmdb_fulltext_search", {"search": "web"}, "fulltext_search", False, {"search": "web", "case_sensitive": False}),
    ("cmdb_fulltext_search_stats", {"search": "web"}, "fulltext_search_stats", False, {"search": "web", "case_sensitive": False}),
    (
        "cmdb_fulltext_search_by_model",
        {"search": "web", "model_id": "host"},
        "fulltext_search_by_model",
        False,
        {"search": "web", "model_id": "host", "page": 1, "page_size": 10, "case_sensitive": False},
    ),
]


@pytest.fixture(autouse=True)
def _skip_db_cleanup_on_tool_invoke(mocker):
    mocker.patch("apps.opspilot.utils.db_cleanup.close_old_connections")


CALLER_IDENTITY = {
    "username": "alice",
    "domain": "tenant-a.com",
    "team_id": 12,
    "include_children": True,
}


def cfg(identity=CALLER_IDENTITY):
    return {"configurable": {"caller_identity": identity}}


def test_cmdb_constructor_has_no_identity_params():
    from apps.opspilot.metis.llm.tools.cmdb import CONSTRUCTOR_PARAMS

    assert CONSTRUCTOR_PARAMS == []


def test_cmdb_search_instances_maps_to_list_instances():
    with patch("apps.opspilot.metis.llm.tools.cmdb.utils.CMDB") as rpc_cls:
        rpc_cls.return_value.list_instances_for_llm.return_value = {"count": 1, "items": [{"inst_uuid": "u1"}]}
        out = inst.cmdb_search_instances.invoke(
            {"model_id": "host", "query_list": [{"field": "ip_addr", "type": "str=", "value": "1.1.1.1"}]},
            config=cfg(),
        )
    assert out["success"] is True
    assert out["data"] == {"count": 1, "items": [{"inst_uuid": "u1"}]}
    assert "monitor_id" in out["_next_step_hint"]
    assert "instance_ids" in out["_next_step_hint"]
    params = rpc_cls.return_value.list_instances_for_llm.call_args.kwargs["params"]
    assert params["protocol_version"] == "2"
    assert params["model_id"] == "host"
    assert params["operator"] == "alice"
    assert params["organization_ids"] == [12]
    assert params["user_info"] == {"user": "alice", "domain": "tenant-a.com", "team": 12, "include_children": True}


def test_cmdb_search_instances_requires_model_id():
    out = inst.cmdb_search_instances.invoke({"model_id": ""}, config=cfg())
    assert out["success"] is False
    assert "model_id is required" in out["error"]


def test_cmdb_search_instances_rejects_host_when_declared_model():
    """用户点名中间件时，runtime 已注入 declared_cmdb_model，禁止再默认 host。"""
    with patch("apps.opspilot.metis.llm.tools.cmdb.utils.CMDB") as rpc_cls:
        out = inst.cmdb_search_instances.invoke(
            {"model_id": "host", "query_list": [{"field": "ip_addr", "type": "str=", "value": "10.10.41.149"}]},
            config={"configurable": {**cfg()["configurable"], "declared_cmdb_model": "nginx"}},
        )
    assert out["success"] is False
    assert "nginx" in out["error"]
    assert "禁止默认 host" in out["error"]
    rpc_cls.return_value.list_instances_for_llm.assert_not_called()


def test_cmdb_search_instances_adds_next_step_hint_with_declared_model():
    with patch("apps.opspilot.metis.llm.tools.cmdb.utils.CMDB") as rpc_cls:
        rpc_cls.return_value.list_instances_for_llm.return_value = {
            "count": 1,
            "items": [{"inst_uuid": "u1", "monitor_id": "1_10.10.41.149_80"}],
        }
        out = inst.cmdb_search_instances.invoke(
            {"model_id": "nginx"},
            config={"configurable": {**cfg()["configurable"], "declared_cmdb_model": "nginx"}},
        )
    assert out["success"] is True
    hint = out["_next_step_hint"]
    assert "nginx" in hint
    assert "monitor_id" in hint
    assert "instance_ids" in hint


def test_cmdb_get_monitor_ids_requires_inst_uuids():
    out = inst.cmdb_get_monitor_ids.invoke({"inst_uuids": []}, config=cfg())
    assert out["success"] is False
    assert "inst_uuids is required" in out["error"]


def test_cmdb_tools_require_caller_identity():
    out = inst.cmdb_get_instance.invoke({"inst_uuid": "u1"}, config={"configurable": {}})
    assert out["success"] is False
    assert "caller_identity" in out["error"]


def test_cmdb_create_instance_passes_user_info():
    with patch("apps.opspilot.metis.llm.tools.cmdb.utils.CMDB") as rpc_cls:
        rpc_cls.return_value.create_instance_for_llm.return_value = {"inst_uuid": "u1"}
        out = inst.cmdb_create_instance.invoke(
            {"model_id": "host", "instance_info": {"inst_name": "box1"}},
            config=cfg(),
        )
    assert out["success"] is True
    params = rpc_cls.return_value.create_instance_for_llm.call_args.kwargs["params"]
    assert params["instance_info"] == {"inst_name": "box1"}
    assert params["user_info"]["user"] == "alice"
    assert params["operator"] == "alice"


def test_cmdb_list_models_uses_search_models():
    with patch("apps.opspilot.metis.llm.tools.cmdb.utils.CMDB") as rpc_cls:
        rpc_cls.return_value.search_models_for_llm.return_value = [{"model_id": "host"}]
        out = mdl.cmdb_list_models.invoke({}, config=cfg())
    assert out["data"] == [{"model_id": "host"}]


def test_call_cmdb_params_unwraps_result_false():
    with patch("apps.opspilot.metis.llm.tools.cmdb.utils.CMDB") as rpc_cls:
        rpc_cls.return_value.get_instance_by_uuid.return_value = {"result": False, "message": "denied"}
        out = call_cmdb_params("get_instance_by_uuid", cfg(), inst_uuid="u1")
    assert out == {"success": False, "error": "denied"}


@pytest.mark.parametrize("tool_name,payload,method,kwargs_mode,extra", _CMDB_TOOL_CASES)
def test_cmdb_tools_map_to_rpc(tool_name, payload, method, kwargs_mode, extra):
    tool = getattr(cmdb_tools, tool_name)
    with patch("apps.opspilot.metis.llm.tools.cmdb.utils.CMDB") as rpc_cls:
        getattr(rpc_cls.return_value, method).return_value = {"ok": True}
        out = tool.invoke(payload, config=cfg())
    assert out == {"success": True, "data": {"ok": True}}
    call = getattr(rpc_cls.return_value, method)
    call.assert_called_once()
    kwargs = call.call_args.kwargs
    if kwargs_mode:
        assert kwargs["user_info"] == {"user": "alice", "domain": "tenant-a.com", "team": 12, "include_children": True}
        for key, value in extra.items():
            assert kwargs[key] == value
        return
    params = kwargs["params"]
    assert params["protocol_version"] == "2"
    assert params["operator"] == "alice"
    assert params["organization_ids"] == [12]
    assert params["user_info"]["user"] == "alice"
    for key, value in extra.items():
        assert params[key] == value


@pytest.mark.parametrize(
    "tool_name,payload",
    [(name, payload) for name, payload, *_rest in _CMDB_TOOL_CASES]
    + [
        ("cmdb_search_instances", {"model_id": "host"}),
        ("cmdb_create_instance", {"model_id": "host", "instance_info": {"inst_name": "box1"}}),
    ],
)
def test_every_cmdb_tool_requires_caller_identity(tool_name, payload):
    tool = getattr(cmdb_tools, tool_name)
    out = tool.invoke(payload, config={"configurable": {}})
    assert out["success"] is False
    assert "caller_identity" in out["error"]
