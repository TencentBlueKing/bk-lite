"""日志 LLM 查询 NATS handler 契约。"""

from types import SimpleNamespace

import pytest

from apps.log.nats import log as log_nats
from apps.log.utils.log_group import LogGroupQueryBuilder

pytestmark = pytest.mark.django_db


def test_list_log_groups_without_identity_returns_empty():
    result = log_nats.list_log_groups(user_info=None)
    assert result["result"] is True
    assert result["data"] == []


def test_log_search_structured_builds_contains_query(mocker):
    captured = {}

    def fake_execute(query, time_range, limit, user_info, log_group_ids=None):
        captured["query"] = query
        captured["time_range"] = time_range
        captured["limit"] = limit
        captured["log_group_ids"] = log_group_ids
        captured["user_info"] = user_info
        return {"result": True, "data": [], "message": ""}

    mocker.patch.object(log_nats, "_llm_execute_log_search", fake_execute)
    result = log_nats.log_search_structured(
        {"keyword": "timeout", "time_range": ["2026-09-11T00:00:00Z", "2026-09-11T01:00:00Z"], "limit": 5, "log_group_ids": ["g1"]},
        user_info={"user": "alice", "domain": "d.com", "team": 1, "include_children": False},
    )
    assert result["result"] is True
    assert "timeout" in captured["query"]
    assert captured["limit"] == 5
    assert captured["log_group_ids"] == ["g1"]


def test_log_search_structured_ors_keywords(mocker):
    captured = {}

    def fake_execute(query, time_range, limit, user_info, log_group_ids=None):
        captured["query"] = query
        return {"result": True, "data": [], "message": ""}

    mocker.patch.object(log_nats, "_llm_execute_log_search", fake_execute)
    log_nats.log_search_structured(
        {"keywords": ["商城", "connection refused"]},
        user_info={"user": "alice", "domain": "d.com", "team": 1, "include_children": False},
    )
    assert " OR " in captured["query"]
    assert "商城" in captured["query"]
    assert "connection" in captured["query"]
    assert "refused" in captured["query"]


def test_log_search_structured_defaults_time_range(mocker):
    captured = {}

    def fake_execute(query, time_range, limit, user_info, log_group_ids=None):
        captured["time_range"] = time_range
        return {"result": True, "data": [], "message": ""}

    mocker.patch.object(log_nats, "_llm_execute_log_search", fake_execute)
    log_nats.log_search_structured(
        {"keyword": "timeout"},
        user_info={"user": "alice", "domain": "d.com", "team": 1, "include_children": False},
    )
    assert captured["time_range"] in (None, [], "")


def test_llm_execute_log_search_defaults_missing_time_range(mocker):
    mocker.patch.object(log_nats, "_llm_accessible_log_groups", return_value=[SimpleNamespace(id="llm-e2e")])
    mocker.patch.object(log_nats.SearchService, "_build_storage_query", return_value=("*", []))
    captured = {}

    class FakeApi:
        def query(self, query, start_time, end_time, limit):
            captured["start"] = start_time
            captured["end"] = end_time
            return []

    mocker.patch.object(log_nats, "VictoriaMetricsAPI", FakeApi)
    result = log_nats._llm_execute_log_search("*", None, 5, {"user": "alice"}, ["llm-e2e"])
    assert result["result"] is True
    assert captured["start"]
    assert captured["end"] > captured["start"]


def test_log_search_structured_keeps_raw_query(mocker):
    captured = {}

    def fake_execute(query, time_range, limit, user_info, log_group_ids=None):
        captured["query"] = query
        return {"result": True, "data": [], "message": ""}

    mocker.patch.object(log_nats, "_llm_execute_log_search", fake_execute)
    log_nats.log_search_structured(
        {"query": 'host:"web-1"', "time_range": ["2026-09-11T00:00:00Z", "2026-09-11T01:00:00Z"]},
        user_info={"user": "alice", "domain": "d.com", "team": 1, "include_children": False},
    )
    assert captured["query"] == 'host:"web-1"'


def test_llm_accessible_log_groups_intersects_requested(mocker):
    groups = [SimpleNamespace(id="g1"), SimpleNamespace(id="g2")]
    mocker.patch.object(log_nats, "_resolve_log_group_scope", return_value=groups)
    narrowed = log_nats._llm_accessible_log_groups({"user": "alice"}, ["g2"])
    assert [group.id for group in narrowed] == ["g2"]


def test_apply_log_group_scope_without_user_denies():
    assert log_nats._apply_log_group_scope("*", None) == LogGroupQueryBuilder.DENY_ALL_QUERY
