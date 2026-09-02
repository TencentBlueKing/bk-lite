"""PostgreSQL 查询/追踪/监控剩余路径：膨胀分级、I/O 热点、锁链、WAL、会话时长。"""
import json
from unittest.mock import patch

import pytest

from apps.opspilot.metis.llm.tools.postgres import monitoring as mon
from apps.opspilot.metis.llm.tools.postgres import query as query_mod
from apps.opspilot.metis.llm.tools.postgres import tracing as tracing_mod

pytestmark = pytest.mark.unit
CONFIG = {"configurable": {"host": "127.0.0.1", "port": 5432, "database": "app", "user": "u", "password": "p"}}


def _patch(module, rows):
    return patch.object(module, "execute_readonly_query", return_value=rows)


def test_query_bloat_classifies_critical_and_never_vacuum():
    rows = [
        {"dead_tuple_percent": 25, "last_vacuum": None, "last_autovacuum": None, "table_name": "events"},
        {"dead_tuple_percent": 12, "last_vacuum": "2026-01-01", "last_autovacuum": None, "table_name": "hosts"},
        {"dead_tuple_percent": 3, "last_vacuum": None, "last_autovacuum": "2026-02-01", "table_name": "ok"},
    ]
    with _patch(query_mod, rows):
        out = json.loads(query_mod.query_bloat_analysis.invoke({"schema_name": "public", "config": CONFIG}))
    levels = {row["table_name"]: row["bloat_level"] for row in out["tables"]}
    assert levels["events"] == "critical"
    assert levels["hosts"] == "warning"
    assert levels["ok"] == "normal"
    assert out["critical_bloat_count"] == 1
    assert out["tables"][0]["last_vacuum"] == "Never"
    with patch.object(query_mod, "execute_readonly_query", side_effect=RuntimeError("denied")):
        err = json.loads(query_mod.query_bloat_analysis.invoke({"config": CONFIG}))
    assert "denied" in err["error"]


def test_query_table_io_stats_marks_hot_and_low_cache():
    rows = [
        {
            "heap_blocks_read": 120000,
            "index_blocks_read": 1,
            "cache_hit_ratio": 80,
            "table_name": "hot",
        },
        {
            "heap_blocks_read": 10,
            "index_blocks_read": 1,
            "cache_hit_ratio": 99,
            "table_name": "cold",
        },
    ]
    with _patch(query_mod, rows):
        out = json.loads(query_mod.query_table_io_stats.invoke({"limit": 20, "config": CONFIG}))
    by_name = {row["table_name"]: row for row in out["tables"]}
    assert by_name["hot"]["is_io_intensive"] is True
    assert by_name["hot"]["has_low_cache_hit"] is True
    assert by_name["cold"]["is_io_intensive"] is False
    assert by_name["cold"]["has_low_cache_hit"] is False


def test_search_objects_view_pattern_and_error():
    with _patch(query_mod, [{"object_name": "v_hosts", "object_type": "view"}]):
        out = json.loads(query_mod.search_objects.invoke({"object_type": "view", "pattern": "v_%", "config": CONFIG}))
    assert out["total_objects"] == 1
    assert out["objects"][0]["object_name"] == "v_hosts"
    with _patch(query_mod, [{"object_name": "all_views"}]):
        all_views = json.loads(query_mod.search_objects.invoke({"object_type": "view", "config": CONFIG}))
    assert all_views["total_objects"] == 1
    with patch.object(query_mod, "execute_readonly_query", side_effect=RuntimeError("timeout")):
        err = json.loads(query_mod.search_objects.invoke({"object_type": "table", "config": CONFIG}))
    assert "timeout" in err["error"]


def test_trace_lock_chain_empty_and_depth():
    with _patch(tracing_mod, []):
        empty = json.loads(tracing_mod.trace_lock_chain.invoke({"config": CONFIG}))
    assert empty["has_lock_chain"] is False
    rows = [
        {"level": 1, "blocked_pid": 11, "blocking_pid": 10},
        {"level": 2, "blocked_pid": 12, "blocking_pid": 11},
    ]
    with _patch(tracing_mod, rows):
        out = json.loads(tracing_mod.trace_lock_chain.invoke({"config": CONFIG}))
    assert out["has_lock_chain"] is True
    assert out["max_chain_depth"] == 2
    assert out["total_blocked_processes"] == 2
    assert out["root_blocking_processes"] == 1
    with patch.object(tracing_mod, "execute_readonly_query", side_effect=RuntimeError("lock denied")):
        err = json.loads(tracing_mod.trace_lock_chain.invoke({"config": CONFIG}))
    assert "lock denied" in err["error"]


def test_active_sessions_duration_categories():
    rows = [
        {
            "backend_start": "t0",
            "transaction_start": None,
            "query_start": "t1",
            "state_change": None,
            "query_duration_seconds": 4000,
            "pid": 1,
        },
        {
            "backend_start": "t0",
            "transaction_start": "tx",
            "query_start": None,
            "state_change": "sc",
            "query_duration_seconds": 120,
            "pid": 2,
        },
        {
            "backend_start": "t0",
            "transaction_start": None,
            "query_start": "t1",
            "state_change": None,
            "query_duration_seconds": 10,
            "pid": 3,
        },
    ]
    with _patch(tracing_mod, rows):
        out = json.loads(tracing_mod.get_active_sessions.invoke({"min_duration_seconds": 0, "config": CONFIG}))
    cats = {row["pid"]: row["duration_category"] for row in out["sessions"]}
    assert cats[1] == "very_long"
    assert cats[2] == "medium"
    assert cats[3] == "short"
    assert out["long_running_sessions"] == 1
    assert out["sessions"][0]["transaction_start"] is None


def test_analyze_query_pattern_percent_and_missing_extension():
    rows = [
        {"query_type": "SELECT", "total_calls": 80, "total_time": 1000, "avg_mean_time": 10},
        {"query_type": "INSERT", "total_calls": 20, "total_time": 200, "avg_mean_time": 5},
    ]
    with _patch(tracing_mod, rows):
        out = json.loads(tracing_mod.analyze_query_pattern.invoke({"hours": 12, "config": CONFIG}))
    assert out["total_query_calls"] == 100
    assert out["analysis_period_hours"] == 12
    percents = {row["query_type"]: row["call_percent"] for row in out["query_patterns"]}
    assert percents["SELECT"] == 80.0
    assert percents["INSERT"] == 20.0
    with patch.object(tracing_mod, "execute_readonly_query", side_effect=RuntimeError("pg_stat_statements missing")):
        err = json.loads(tracing_mod.analyze_query_pattern.invoke({"config": CONFIG}))
    assert "pg_stat_statements" in err["error"]


def test_table_metrics_dead_ratio_and_never():
    rows = [
        {
            "live_tuples": 80,
            "dead_tuples": 20,
            "last_vacuum": None,
            "last_autovacuum": None,
            "last_analyze": None,
            "last_autoanalyze": None,
            "table_name": "hosts",
        }
    ]
    with _patch(mon, rows):
        out = json.loads(mon.get_table_metrics.invoke({"table": "hosts", "config": CONFIG}))
    assert out["total_tables"] == 1
    assert out["tables"][0]["dead_tuple_ratio"] == 20.0
    assert out["tables"][0]["last_vacuum"] == "Never"
    with _patch(mon, []):
        all_tables = json.loads(mon.get_table_metrics.invoke({"config": CONFIG}))
    assert all_tables["table"] is None


def test_check_configuration_tuning_attaches_advice():
    from apps.opspilot.metis.llm.tools.postgres import optimization as opt

    rows = [
        {"name": "shared_buffers", "setting": "128MB"},
        {"name": "work_mem", "setting": "4MB"},
        {"name": "unknown_param", "setting": "1"},
    ]
    with patch.object(opt, "execute_readonly_query", return_value=rows):
        out = json.loads(opt.check_configuration_tuning.invoke({"config": CONFIG}))
    assert out["total_parameters"] == 3
    advised = {row["name"]: row.get("advice") for row in out["parameters"]}
    assert "25%" in advised["shared_buffers"]
    assert advised["unknown_param"] is None
    with patch.object(opt, "execute_readonly_query", side_effect=RuntimeError("settings denied")):
        err = json.loads(opt.check_configuration_tuning.invoke({"config": CONFIG}))
    assert "settings denied" in err["error"]

    bg = {
        "checkpoints_timed": 9,
        "checkpoints_req": 1,
        "buffers_checkpoint": 50,
        "buffers_clean": 30,
        "buffers_backend": 20,
        "stats_reset": None,
    }
    with _patch(mon, [bg]):
        out = json.loads(mon.get_bgwriter_stats.invoke({"config": CONFIG}))
    assert out["total_checkpoints"] == 10
    assert out["timed_checkpoint_ratio"] == 90.0
    assert out["checkpoint_buffer_ratio"] == 50.0
    assert out["stats_reset"] == "Never"

    wal_info = {"current_wal_lsn": "0/1", "wal_level": "replica"}
    wal_stats = {"wal_bytes": 2048, "stats_reset": None}

    def fake_query(sql, params=None, config=None, database=None):
        if "pg_stat_wal" in sql:
            return [wal_stats]
        return [wal_info]

    with patch.object(mon, "execute_readonly_query", side_effect=fake_query):
        wal = json.loads(mon.get_wal_metrics.invoke({"config": CONFIG}))
    assert wal["wal_info"]["wal_level"] == "replica"
    assert wal["wal_stats"]["wal_size"]

    def missing_stat(sql, params=None, config=None, database=None):
        if "pg_stat_wal" in sql:
            raise RuntimeError("relation pg_stat_wal does not exist")
        return [wal_info]

    with patch.object(mon, "execute_readonly_query", side_effect=missing_stat):
        fallback = json.loads(mon.get_wal_metrics.invoke({"config": CONFIG}))
    assert "PostgreSQL 14" in fallback["wal_stats"]["note"]
