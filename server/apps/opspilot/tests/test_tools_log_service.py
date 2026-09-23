"""Log LLM tools: NATS RPC wrappers with caller_identity."""

from unittest.mock import patch

import pytest

from apps.opspilot.metis.llm.tools.log import log_list_groups, log_search_raw, log_search_structured


@pytest.fixture(autouse=True)
def _skip_db_cleanup_on_tool_invoke(mocker):
    mocker.patch("apps.opspilot.utils.db_cleanup.close_old_connections")


CALLER_IDENTITY = {
    "username": "alice",
    "domain": "tenant-a.com",
    "team_id": 12,
    "include_children": True,
}


def cfg():
    return {"configurable": {"caller_identity": CALLER_IDENTITY}}


def test_log_constructor_has_no_identity_params():
    from apps.opspilot.metis.llm.tools.log import CONSTRUCTOR_PARAMS

    assert CONSTRUCTOR_PARAMS == []


def test_log_list_groups_maps_to_rpc():
    with patch("apps.opspilot.metis.llm.tools.log.utils.LogOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.list_log_groups.return_value = {"result": True, "data": [{"id": "default", "name": "默认"}]}
        out = log_list_groups.invoke({}, config=cfg())
    assert out["data"][0]["id"] == "default"
    kwargs = rpc_cls.return_value.list_log_groups.call_args.kwargs
    assert kwargs["user_info"]["team"] == 12


def test_log_search_structured_defaults_time_when_omitted():
    with patch("apps.opspilot.metis.llm.tools.log.utils.LogOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.search_structured.return_value = {"result": True, "data": []}
        out = log_search_structured.invoke({"keyword": "timeout"}, config=cfg())
    assert out["success"] is True
    query_data = rpc_cls.return_value.search_structured.call_args.kwargs["query_data"]
    assert query_data["keywords"] == ["timeout"]
    assert len(query_data["time_range"]) == 2


def test_log_search_structured_requires_paired_time():
    out = log_search_structured.invoke({"start": "2026-09-11T00:00:00Z"}, config=cfg())
    assert "start and end must be provided together" in out["error"]


def test_log_search_structured_maps_to_rpc():
    with patch("apps.opspilot.metis.llm.tools.log.utils.LogOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.search_structured.return_value = {"result": True, "data": []}
        out = log_search_structured.invoke(
            {"start": "2026-09-11T00:00:00Z", "end": "2026-09-11T01:00:00Z", "keyword": "error"},
            config=cfg(),
        )
    assert out["success"] is True
    query_data = rpc_cls.return_value.search_structured.call_args.kwargs["query_data"]
    assert query_data["keywords"] == ["error"]
    assert query_data["time_range"][0].startswith("2026-09-11")


def test_log_search_raw_requires_query():
    out = log_search_raw.invoke({"query": ""}, config=cfg())
    assert out["error"] == "query is required"


def test_log_search_raw_maps_to_structured_rpc():
    with patch("apps.opspilot.metis.llm.tools.log.utils.LogOperationAnaRpc") as rpc_cls:
        rpc_cls.return_value.search_structured.return_value = {"result": True, "data": []}
        out = log_search_raw.invoke(
            {
                "query": 'host:"web-1"',
                "start": "2026-09-11T00:00:00Z",
                "end": "2026-09-11T01:00:00Z",
                "log_group_ids": ["g1"],
            },
            config=cfg(),
        )
    assert out["success"] is True
    query_data = rpc_cls.return_value.search_structured.call_args.kwargs["query_data"]
    assert query_data["query"] == 'host:"web-1"'
    assert query_data["log_group_ids"] == ["g1"]


def test_log_tools_require_caller_identity():
    out = log_list_groups.invoke({}, config={"configurable": {}})
    assert "caller_identity" in out["error"]
