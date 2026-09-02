"""PostgreSQL 诊断：慢查询缺扩展、锁冲突、连接池使用率。"""
import json
from unittest.mock import patch

import pytest

from apps.opspilot.metis.llm.tools.postgres import diagnostics as diag

pytestmark = pytest.mark.unit
CONFIG = {"configurable": {"host": "127.0.0.1"}}


def test_diagnose_slow_queries_and_missing_extension():
    rows = [{"query": "SELECT 1", "calls": 10, "total_time": 5000, "mean_time": 500, "max_time": 800}]
    with patch.object(diag, "execute_readonly_query", return_value=rows):
        out = json.loads(diag.diagnose_slow_queries.invoke({"threshold_ms": 100, "config": CONFIG}))
    assert out["total_slow_queries"] == 1
    assert out["threshold_ms"] == 100
    with patch.object(diag, "execute_readonly_query", side_effect=RuntimeError("pg_stat_statements missing")):
        err = json.loads(diag.diagnose_slow_queries.invoke({"config": CONFIG}))
    assert "pg_stat_statements" in err["error"]
    assert "suggestion" in err


def test_diagnose_lock_conflicts_flags_blocked():
    rows = [{"blocked_pid": 11, "blocking_pid": 22, "blocked_duration": "00:00:05"}]
    with patch.object(diag, "execute_readonly_query", return_value=rows):
        out = json.loads(diag.diagnose_lock_conflicts.invoke({"config": CONFIG}))
    assert out["has_conflicts"] is True
    assert out["total_blocked_queries"] == 1
    assert out["lock_conflicts"][0]["blocked_pid"] == 11
    with patch.object(diag, "execute_readonly_query", return_value=[]):
        empty = json.loads(diag.diagnose_lock_conflicts.invoke({"config": CONFIG}))
    assert empty["has_conflicts"] is False


def test_diagnose_connection_issues_near_limit():
    def fake_query(sql, params=None, config=None, database=None):
        if "max_connections" in sql:
            return [{"max_connections": 10}]
        if "pg_stat_activity" in sql and "query_start" in sql:
            return [{"duration": "00:06:00", "query": "SELECT pg_sleep(400)"}]
        return [{"state": "active", "connection_count": 9}]

    with patch.object(diag, "execute_readonly_query", side_effect=fake_query):
        out = json.loads(diag.diagnose_connection_issues.invoke({"config": CONFIG}))
    assert out["current_connections"] == 9
    assert out["usage_percent"] == 90.0
    assert out["is_near_limit"] is True
    assert out["long_running_queries"][0]["query"]
