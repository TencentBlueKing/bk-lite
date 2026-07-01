"""PostgreSQL @tool 工具集单元测试 (postgres/analysis|monitoring|optimization|query)。

mock 边界为各工具模块导入的 execute_readonly_query(util 层,内部封装 psycopg2 连接),
返回真实形态的 RealDictCursor 行(dict)。断言派生指标(命中率/回滚率/seq_scan 比例)、
阈值分级(critical/high/medium)、建议文案、空结果与异常包装。不连真实 PostgreSQL。
"""

import json
from unittest.mock import patch

import pydantic.root_model  # noqa
import pytest

from apps.opspilot.metis.llm.tools.postgres import analysis as ana
from apps.opspilot.metis.llm.tools.postgres import monitoring as mon
from apps.opspilot.metis.llm.tools.postgres import optimization as opt
from apps.opspilot.metis.llm.tools.postgres import query as qry

CONFIG = {"configurable": {"host": "127.0.0.1", "port": 5432, "user": "pg", "database": "appdb"}}


def patch_erq(module, side_effect=None, return_value=None):
    """patch 模块内的 execute_readonly_query。side_effect 可为按调用次序的列表。"""
    if side_effect is not None:
        return patch.object(module, "execute_readonly_query", side_effect=side_effect)
    return patch.object(module, "execute_readonly_query", return_value=return_value)


# ---------------- analysis.analyze_cache_hit_ratio ----------------
class TestCacheHitRatio:
    def test_excellent(self):
        rows = [
            {"database": "appdb", "blocks_hit": 9999, "blocks_read": 1, "total_blocks": 10000, "cache_hit_ratio": 99.99},
        ]
        with patch_erq(ana, return_value=rows):
            out = json.loads(ana.analyze_cache_hit_ratio.invoke({"config": CONFIG}))
        assert out["overall_cache_hit_ratio"] == 99.99
        assert out["performance"] == "excellent"
        assert out["by_database"] == rows

    def test_poor_recommendation(self):
        rows = [{"database": "appdb", "blocks_hit": 50, "blocks_read": 50, "total_blocks": 100, "cache_hit_ratio": 50.0}]
        with patch_erq(ana, return_value=rows):
            out = json.loads(ana.analyze_cache_hit_ratio.invoke({"config": CONFIG}))
        assert out["performance"] == "poor"
        assert "强烈建议" in out["recommendation"]

    def test_error_wrapped(self):
        with patch_erq(ana, side_effect=RuntimeError("conn fail")):
            out = json.loads(ana.analyze_cache_hit_ratio.invoke({"config": CONFIG}))
        assert out["error"] == "conn fail"


# ---------------- analysis.analyze_connection_pool_usage ----------------
class TestConnPoolUsage:
    def test_idle_heavy_recommends_shrink(self):
        by_state = [
            {"state": "idle", "connection_count": 60, "avg_duration_seconds": 100.0},
            {"state": "active", "connection_count": 40, "avg_duration_seconds": 1.0},
        ]
        by_app = [{"application_name": "web", "username": "pg", "connection_count": 50, "active_count": 20, "idle_count": 30}]
        long_idle = [{"pid": 1, "usename": "pg", "application_name": "web", "client_addr": "10.0.0.1",
                      "state": "idle", "idle_duration": "0:20:00", "query": "SELECT 1"}]
        with patch_erq(ana, side_effect=[by_state, by_app, long_idle]):
            out = json.loads(ana.analyze_connection_pool_usage.invoke({"config": CONFIG}))
        assert out["total_connections"] == 100
        assert out["idle_connections"] == 60
        assert out["idle_percent"] == 60.0
        assert "考虑减小连接池大小" in out["recommendations"]
        assert any("长时间空闲" in r for r in out["recommendations"] if r)

    def test_no_idle_no_shrink(self):
        by_state = [{"state": "active", "connection_count": 10, "avg_duration_seconds": 1.0}]
        with patch_erq(ana, side_effect=[by_state, [], []]):
            out = json.loads(ana.analyze_connection_pool_usage.invoke({"config": CONFIG}))
        assert out["idle_percent"] == 0.0
        assert None in out["recommendations"]  # 收缩建议为 None


# ---------------- analysis.analyze_table_statistics ----------------
class TestTableStatistics:
    def test_stale_detection(self):
        rows = [
            {"schemaname": "public", "table_name": "hot", "last_analyze": None, "last_autoanalyze": None,
             "last_analyze_any": None, "time_since_analyze": None,
             "modifications_since_analyze": 5000, "live_tuples": 1000, "modification_percent": 500.0},
            {"schemaname": "public", "table_name": "ok", "last_analyze": "2024-06-01", "last_autoanalyze": None,
             "last_analyze_any": "2024-06-01", "time_since_analyze": "1 day",
             "modifications_since_analyze": 5, "live_tuples": 1000, "modification_percent": 0.5},
        ]
        with patch_erq(ana, return_value=rows):
            out = json.loads(ana.analyze_table_statistics.invoke({"schema_name": "public", "config": CONFIG}))
        assert out["total_tables"] == 2
        assert out["stale_statistics_count"] == 1
        stale = [t for t in out["tables"] if t["is_stale"]]
        assert stale[0]["table_name"] == "hot"
        assert out["tables"][0]["last_analyze"] == "Never"


# ---------------- analysis.analyze_checkpoint_activity ----------------
class TestCheckpointActivity:
    def test_good_when_timed_dominant(self):
        row = {"checkpoints_timed": 95, "checkpoints_requested": 5, "checkpoint_write_time": 100,
               "checkpoint_sync_time": 10, "buffers_checkpoint": 1, "buffers_clean": 1,
               "buffers_backend": 1, "buffers_backend_fsync": 0, "buffers_alloc": 1}
        with patch_erq(ana, return_value=[row]):
            out = json.loads(ana.analyze_checkpoint_activity.invoke({"config": CONFIG}))
        assert out["total_checkpoints"] == 100
        assert out["timed_percent"] == 95.0
        assert out["status"] == "good"

    def test_poor_when_requested_dominant(self):
        row = {"checkpoints_timed": 30, "checkpoints_requested": 70, "checkpoint_write_time": 0,
               "checkpoint_sync_time": 0, "buffers_checkpoint": 0, "buffers_clean": 0,
               "buffers_backend": 0, "buffers_backend_fsync": 0, "buffers_alloc": 0}
        with patch_erq(ana, return_value=[row]):
            out = json.loads(ana.analyze_checkpoint_activity.invoke({"config": CONFIG}))
        assert out["status"] == "poor"
        assert "max_wal_size" in out["recommendation"]


# ---------------- analysis.analyze_transaction_patterns ----------------
class TestTransactionPatterns:
    def test_rollback_classification(self):
        rows = [
            {"database": "a", "commits": 80, "rollbacks": 20, "total_transactions": 100,
             "rollback_percent": 20.0, "conflicts": 0, "deadlocks": 0},  # high
            {"database": "b", "commits": 93, "rollbacks": 7, "total_transactions": 100,
             "rollback_percent": 7.0, "conflicts": 0, "deadlocks": 0},  # moderate
            {"database": "c", "commits": 99, "rollbacks": 1, "total_transactions": 100,
             "rollback_percent": 1.0, "conflicts": 0, "deadlocks": 0},  # normal
        ]
        with patch_erq(ana, return_value=rows):
            out = json.loads(ana.analyze_transaction_patterns.invoke({"config": CONFIG}))
        statuses = [d["status"] for d in out["databases"]]
        assert statuses == ["high_rollback", "moderate_rollback", "normal"]


# ---------------- monitoring.get_database_metrics ----------------
class TestPgDatabaseMetrics:
    def test_rollback_ratio_and_temp_size_formatting(self):
        rows = [{
            "database": "appdb", "transactions_committed": 80, "transactions_rolled_back": 20,
            "temporary_bytes": 2048, "stats_reset": None,
        }]
        with patch_erq(mon, return_value=rows):
            out = json.loads(mon.get_database_metrics.invoke({"config": CONFIG}))
        assert out["total_databases"] == 1
        db = out["databases"][0]
        assert db["rollback_ratio"] == 20.0  # 20/100
        assert db["temporary_size"] == "2.00 KB"
        assert db["stats_reset"] == "Never"

    def test_error_wrapped(self):
        with patch_erq(mon, side_effect=RuntimeError("db down")):
            out = json.loads(mon.get_database_metrics.invoke({"config": CONFIG}))
        assert out["error"] == "db down"


# ---------------- monitoring.get_replication_metrics ----------------
class TestReplicationMetrics:
    def test_no_standby(self):
        with patch_erq(mon, return_value=[]):
            out = json.loads(mon.get_replication_metrics.invoke({"config": CONFIG}))
        assert out["has_replication"] is False
        assert "未配置复制" in out["message"]

    def test_with_replicas_formats_lag(self):
        rows = [{
            "write_lag": None, "flush_lag": None, "replay_lag": None,
            "sent_lag_bytes": 1024, "write_lag_bytes": 0, "flush_lag_bytes": 0,
            "replay_lag_bytes": 0, "backend_start": "2024-01-01", "reply_time": None,
        }]
        with patch_erq(mon, return_value=rows):
            out = json.loads(mon.get_replication_metrics.invoke({"config": CONFIG}))
        assert out["has_replication"] is True
        assert out["replica_count"] == 1
        assert out["replicas"][0]["sent_lag_size"] == "1.00 KB"
        assert out["replicas"][0]["write_lag"] == "0"


# ---------------- optimization.recommend_vacuum_strategy ----------------
class TestVacuumStrategy:
    def _row(self, name, dead_percent, dead_tuples):
        return {
            "schemaname": "public", "table_name": name, "dead_tuples": dead_tuples,
            "live_tuples": 1000, "dead_tuple_percent": dead_percent,
            "last_vacuum": None, "last_autovacuum": None, "last_vacuum_any": None,
            "time_since_vacuum": None, "table_size": "10 MB",
        }

    def test_priority_levels(self):
        rows = [
            self._row("crit", 40.0, 0),     # >30 critical
            self._row("high", 25.0, 0),     # >20 high
            self._row("med", 15.0, 0),      # >10 medium
            self._row("low", 2.0, 0),       # low
        ]
        with patch_erq(opt, return_value=rows):
            out = json.loads(opt.recommend_vacuum_strategy.invoke({"schema_name": "public", "config": CONFIG}))
        assert out["total_tables"] == 4
        assert out["critical_priority"] == 1
        assert out["high_priority"] == 1
        # low 不进 recommendations
        recs = {r["table_name"]: r["priority"] for r in out["recommendations"]}
        assert recs == {"crit": "critical", "high": "high", "med": "medium"}
        assert any("立即执行VACUUM FULL" in a for a in out["general_advice"] if a)

    def test_dead_tuples_count_triggers_critical(self):
        rows = [self._row("big", 5.0, 2000000)]  # dead_tuples > 1M
        with patch_erq(opt, return_value=rows):
            out = json.loads(opt.recommend_vacuum_strategy.invoke({"config": CONFIG}))
        assert out["critical_priority"] == 1


# ---------------- optimization.recommend_index_optimization ----------------
class TestPgIndexOptimization:
    def test_high_seq_scan_recommends_index(self):
        rows = [{
            "schemaname": "public", "table_name": "t", "sequential_scans": 900,
            "sequential_tuples_read": 100000, "index_scans": 100, "index_tuples_fetched": 10,
            "live_tuples": 5000, "avg_tuples_per_seq_scan": 200.0,
        }]
        with patch_erq(opt, return_value=rows):
            out = json.loads(opt.recommend_index_optimization.invoke({"config": CONFIG}))
        assert out["needs_optimization"] == 1
        rec = out["tables"][0]
        assert rec["seq_scan_ratio"] == 90.0
        assert rec["priority"] == "high"
        assert "添加索引" in rec["recommendation"]

    def test_good_index_usage(self):
        rows = [{
            "schemaname": "public", "table_name": "t", "sequential_scans": 5,
            "sequential_tuples_read": 10, "index_scans": 1000, "index_tuples_fetched": 999,
            "live_tuples": 5000, "avg_tuples_per_seq_scan": 2.0,
        }]
        with patch_erq(opt, return_value=rows):
            out = json.loads(opt.recommend_index_optimization.invoke({"config": CONFIG}))
        assert out["needs_optimization"] == 0


# ---------------- optimization.check_unused_indexes ----------------
class TestPgUnusedIndexes:
    def test_wasted_space_aggregated(self):
        rows = [
            {"schemaname": "public", "table_name": "t", "index_name": "idx1", "index_size_bytes": 1024},
            {"schemaname": "public", "table_name": "t", "index_name": "idx2", "index_size_bytes": 1024},
        ]
        with patch_erq(opt, return_value=rows):
            out = json.loads(opt.check_unused_indexes.invoke({"config": CONFIG}))
        assert out["unused_index_count"] == 2
        assert out["total_wasted_bytes"] == 2048
        assert out["total_wasted_space"] == "2.00 KB"
        assert any("可节省" in r for r in out["recommendations"])

    def test_empty_no_waste(self):
        with patch_erq(opt, return_value=[]):
            out = json.loads(opt.check_unused_indexes.invoke({"config": CONFIG}))
        assert out["unused_index_count"] == 0
        assert "未发现大型未使用索引" in out["recommendations"]

    def test_error_wrapped(self):
        with patch_erq(opt, side_effect=ValueError("boom")):
            out = json.loads(opt.check_unused_indexes.invoke({"config": CONFIG}))
        assert out["error"] == "boom"


# ---------------- query.search_objects ----------------
class TestSearchObjects:
    def test_unsupported_object_type(self):
        out = json.loads(qry.search_objects.invoke({"object_type": "nonsense", "config": CONFIG}))
        assert "不支持的对象类型" in out["error"]

    def test_table_search(self):
        rows = [{"schema": "public", "name": "users", "type": "table"}, {"schema": "public", "name": "user_log", "type": "table"}]
        with patch_erq(qry, return_value=rows):
            out = json.loads(qry.search_objects.invoke({"object_type": "table", "pattern": "use", "config": CONFIG}))
        assert out["object_type"] == "table"
        assert out["pattern"] == "use"
        assert out["total_objects"] == 2
        assert out["objects"] == rows


# ---------------- query.query_table_stats ----------------
class TestQueryTableStats:
    def test_index_scan_ratio_and_hot_table(self):
        rows = [{
            "schemaname": "public", "table_name": "hot",
            "sequential_scans": 2000, "index_scans": 18000,
        }]
        with patch_erq(qry, return_value=rows):
            out = json.loads(qry.query_table_stats.invoke({"config": CONFIG}))
        assert out["total_tables"] == 1
        t = out["tables"][0]
        assert t["index_scan_ratio"] == 90.0  # 18000/20000
        assert t["is_hot_table"] is True  # total_scans > 10000

    def test_error_wrapped(self):
        with patch_erq(qry, side_effect=RuntimeError("x")):
            out = json.loads(qry.query_table_stats.invoke({"config": CONFIG}))
        assert out["error"] == "x"

    def test_error_wrapped(self):
        with patch_erq(qry, side_effect=RuntimeError("x")):
            out = json.loads(qry.query_table_stats.invoke({"config": CONFIG}))
        assert out["error"] == "x"
