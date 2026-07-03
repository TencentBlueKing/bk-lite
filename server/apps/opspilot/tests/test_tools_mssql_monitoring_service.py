"""MSSQL 监控 @tool 工具集单元测试 (mssql/monitoring.py)。

mock 边界:
- monitoring 模块内 execute_readonly_query(真实 DB 边界, 内部走 pyodbc.connect),
  用按 SQL 关键字分派的 side_effect 返回真实形态 dict 行。

断言工具产出的结构化 JSON、派生指标(合并缓存映射/等待分类/高延迟识别/备份问题判定/
作业失败统计/增长趋势计算)、特性分支(无 backupset/无 agent/无 replication 早退)、
safe_json_dumps 单位富化、异常脱敏透出。不连真实 MSSQL。

pyodbc 在导入 mssql 子模块时被加载;缺 unixodbc 时整文件跳过(本机已装 unixodbc)。
"""

import json
from unittest.mock import patch

import pydantic.root_model  # noqa
import pytest

pytest.importorskip("pyodbc", reason="pyodbc/unixodbc 未安装,跳过 MSSQL 工具测试")

from apps.opspilot.metis.llm.tools.mssql import monitoring as mon  # noqa: E402

CONFIG = {"configurable": {"host": "127.0.0.1", "port": 1433, "user": "sa", "password": "p", "database": "appdb"}}


def _dispatch(matchers):
    """execute_readonly_query side_effect: 按 SQL 子串命中第一个匹配返回对应 rows。"""

    def _impl(query, params=None, config=None, database=None):
        for substr, rows in matchers:
            if substr in query:
                return rows
        return []

    return _impl


# ============================ get_database_metrics ============================
class TestDatabaseMetrics:
    def test_merges_cache_stats_and_formats_create_date(self):
        db_rows = [
            {"database_name": "appdb", "state": "ONLINE", "recovery_model": "FULL",
             "compatibility_level": 150, "create_date": "2024-01-01 10:00:00",
             "active_connections": 5, "data_size_mb": 100, "log_size_mb": 20},
            {"database_name": "other", "state": "ONLINE", "recovery_model": "SIMPLE",
             "compatibility_level": 150, "create_date": None,
             "active_connections": 0, "data_size_mb": 10, "log_size_mb": 2},
        ]
        cache_rows = [
            {"database_name": "appdb", "buffer_pool_reads": 999, "index_seeks": 800,
             "index_scans": 100, "index_lookups": 99, "index_updates": 50},
        ]
        matchers = [
            ("sys.dm_db_index_usage_stats", cache_rows),
            ("FROM sys.databases d", db_rows),
        ]
        with patch.object(mon, "execute_readonly_query", _dispatch(matchers)):
            out = json.loads(mon.get_database_metrics.invoke({"config": CONFIG}))

        assert out["total_databases"] == 2
        appdb = next(d for d in out["databases"] if d["database_name"] == "appdb")
        # create_date 被 str() 化
        assert appdb["create_date"] == "2024-01-01 10:00:00"
        # 缓存统计被合并进来
        assert appdb["buffer_pool_reads"] == 999
        assert appdb["index_seeks"] == 800
        assert appdb["index_scans"] == 100
        # 无缓存命中的库不应有 buffer_pool_reads 键
        other = next(d for d in out["databases"] if d["database_name"] == "other")
        assert "buffer_pool_reads" not in other
        # None create_date 归一为 None
        assert other["create_date"] is None

    def test_error_sanitized(self):
        with patch.object(mon, "execute_readonly_query", side_effect=RuntimeError("boom")):
            out = json.loads(mon.get_database_metrics.invoke({"config": CONFIG}))
        assert out["error"] == "boom"


# ============================ get_table_metrics ============================
class TestTableMetrics:
    def test_single_table_formats_size_and_times(self):
        rows = [{
            "schema_name": "dbo", "table_name": "orders", "row_count": 1000,
            "total_space_kb": 2048, "used_space_kb": 1024, "unused_space_kb": 1024,
            "user_seeks": 10, "user_scans": 2, "user_lookups": 1, "user_updates": 3,
            "last_user_seek": "2024-06-01 00:00:00", "last_user_scan": None,
            "last_user_update": "2024-06-02 00:00:00",
        }]
        # 单表查询走 WHERE s.name = ? AND t.name = ?
        with patch.object(mon, "execute_readonly_query", _dispatch([("AND t.name = ?", rows)])):
            out = json.loads(mon.get_table_metrics.invoke(
                {"schema_name": "dbo", "table": "orders", "config": CONFIG}))

        assert out["schema"] == "dbo"
        assert out["table"] == "orders"
        assert out["total_tables"] == 1
        t = out["tables"][0]
        # used_space_kb=1024 -> 1024*1024 bytes -> 1.00 MB
        assert t["used_space_formatted"] == "1.00 MB"
        # 非空时间字段被 str 化, None 保持
        assert t["last_user_seek"] == "2024-06-01 00:00:00"
        assert t["last_user_scan"] is None

    def test_all_tables_uses_top_query(self):
        rows = [{
            "schema_name": "dbo", "table_name": "t1", "row_count": 5,
            "total_space_kb": 16, "used_space_kb": None,
            "user_seeks": 0, "user_scans": 0, "user_lookups": 0, "user_updates": 0,
        }]
        # 全表查询走 TOP 50 分支(无 AND t.name)
        with patch.object(mon, "execute_readonly_query", _dispatch([("TOP 50", rows)])):
            out = json.loads(mon.get_table_metrics.invoke({"schema_name": "dbo", "config": CONFIG}))
        assert out["table"] is None
        # used_space_kb 为 None -> N/A
        assert out["tables"][0]["used_space_formatted"] == "N/A"

    def test_error_sanitized(self):
        with patch.object(mon, "execute_readonly_query", side_effect=ValueError("xx")):
            out = json.loads(mon.get_table_metrics.invoke({"config": CONFIG}))
        assert out["error"] == "xx"


# ============================ get_wait_stats ============================
class TestWaitStats:
    def test_categorizes_waits(self):
        rows = [
            {"wait_type": "PAGEIOLATCH_SH", "waiting_tasks_count": 10, "wait_time_s": 5,
             "max_wait_time_ms": 100, "signal_wait_time_s": 1, "signal_wait_percent": 20},
            {"wait_type": "LCK_M_X", "waiting_tasks_count": 3, "wait_time_s": 2,
             "max_wait_time_ms": 50, "signal_wait_time_s": 0, "signal_wait_percent": 0},
            {"wait_type": "RESOURCE_SEMAPHORE", "waiting_tasks_count": 1, "wait_time_s": 1,
             "max_wait_time_ms": 10, "signal_wait_time_s": 0, "signal_wait_percent": 0},
            {"wait_type": "CXPACKET", "waiting_tasks_count": 2, "wait_time_s": 1,
             "max_wait_time_ms": 5, "signal_wait_time_s": 0, "signal_wait_percent": 0},
        ]
        with patch.object(mon, "execute_readonly_query", _dispatch([("dm_os_wait_stats", rows)])):
            out = json.loads(mon.get_wait_stats.invoke({"config": CONFIG}))

        assert out["total_wait_types"] == 4
        s = out["summary"]
        # PAGEIOLATCH 命中 IO 分类
        assert s["io_related_waits"] == 1
        # LCK_M_X 命中 lock 分类
        assert s["lock_related_waits"] == 1
        # RESOURCE_SEMAPHORE 命中 memory/resource 分类
        assert s["memory_related_waits"] == 1

    def test_error_sanitized(self):
        with patch.object(mon, "execute_readonly_query", side_effect=RuntimeError("e")):
            out = json.loads(mon.get_wait_stats.invoke({"config": CONFIG}))
        assert out["error"] == "e"


# ============================ get_instance_metrics ============================
class TestInstanceMetrics:
    def _matchers(self, cpu_rows=None, cpu_error=False):
        perf = [
            {"object_name": "SQLServer:Buffer Manager ", "counter_name": "Page life expectancy ",
             "instance_name": "  ", "cntr_value": 3000, "cntr_type": 65792},
            {"object_name": "SQLServer:Buffer Manager ", "counter_name": "Buffer cache hit ratio ",
             "instance_name": None, "cntr_value": 95, "cntr_type": 537003264},
        ]
        memory = [{"memory_used_mb": 2048, "memory_utilization_percentage": 80}]
        server = [{"server_name": "SQL01", "product_version": "15.0.2000",
                   "edition": "Enterprise", "full_version": "Microsoft SQL Server 2019"}]

        def _impl(query, params=None, config=None, database=None):
            if "dm_os_performance_counters" in query:
                return perf
            if "dm_os_process_memory" in query:
                return memory
            if "SERVERPROPERTY" in query:
                return server
            if "RING_BUFFER_SCHEDULER_MONITOR" in query:
                if cpu_error:
                    raise RuntimeError("cpu unavailable")
                return cpu_rows if cpu_rows is not None else []
            return []

        return _impl

    def test_groups_perf_counters_and_strips_whitespace(self):
        cpu = [{"record_id": 1, "sql_cpu_percent": 30, "system_idle_percent": 60,
                "other_process_cpu_percent": 10}]
        with patch.object(mon, "execute_readonly_query", self._matchers(cpu_rows=cpu)):
            out = json.loads(mon.get_instance_metrics.invoke({"config": CONFIG}))

        assert out["server_info"]["server_name"] == "SQL01"
        assert out["memory"]["memory_used_mb"] == 2048
        assert out["cpu"]["sql_cpu_percent"] == 30
        # 按 object_name(去空格) 分组
        pc = out["performance_counters"]
        assert "SQLServer:Buffer Manager" in pc
        counters = pc["SQLServer:Buffer Manager"]
        assert len(counters) == 2
        # counter/instance 去空格; None instance -> ""
        assert counters[0]["counter"] == "Page life expectancy"
        assert counters[1]["instance"] == ""

    def test_cpu_query_failure_falls_back_to_none(self):
        with patch.object(mon, "execute_readonly_query", self._matchers(cpu_error=True)):
            out = json.loads(mon.get_instance_metrics.invoke({"config": CONFIG}))
        # CPU 不可用时回退默认占位
        assert out["cpu"]["sql_cpu_percent"] is None

    def test_error_sanitized(self):
        with patch.object(mon, "execute_readonly_query", side_effect=RuntimeError("boom")):
            out = json.loads(mon.get_instance_metrics.invoke({"config": CONFIG}))
        assert out["error"] == "boom"


# ============================ get_io_stats ============================
class TestIoStats:
    def test_identifies_high_latency_files(self):
        rows = [
            {"database_name": "appdb", "logical_name": "appdb_data", "file_type": "ROWS",
             "physical_name": "/d/appdb.mdf", "num_of_reads": 100, "mb_read": 500,
             "io_stall_read_ms": 5000, "avg_read_latency_ms": 50,
             "num_of_writes": 10, "mb_written": 50, "io_stall_write_ms": 100,
             "avg_write_latency_ms": 5, "total_io_stall_ms": 5100, "size_on_disk_mb": 1000},
            {"database_name": "appdb", "logical_name": "appdb_log", "file_type": "LOG",
             "physical_name": "/d/appdb.ldf", "num_of_reads": 1, "mb_read": 1,
             "io_stall_read_ms": 1, "avg_read_latency_ms": 1,
             "num_of_writes": 1, "mb_written": 1, "io_stall_write_ms": 1,
             "avg_write_latency_ms": 1, "total_io_stall_ms": 2, "size_on_disk_mb": 10},
        ]
        with patch.object(mon, "execute_readonly_query", _dispatch([("dm_io_virtual_file_stats", rows)])):
            out = json.loads(mon.get_io_stats.invoke({"config": CONFIG}))

        assert out["total_files"] == 2
        # 第一个文件读延迟 50 > 20 -> 高延迟
        assert out["high_latency_files"] == 1
        # 有高延迟时给出建议(非 None 项)
        recs = [r for r in out["recommendations"] if r]
        assert any("磁盘性能" in r for r in recs)

    def test_no_high_latency_no_recommendations(self):
        rows = [{
            "database_name": "appdb", "logical_name": "d", "file_type": "ROWS",
            "physical_name": "/d.mdf", "num_of_reads": 1, "mb_read": 1,
            "io_stall_read_ms": 1, "avg_read_latency_ms": 1,
            "num_of_writes": 1, "mb_written": 1, "io_stall_write_ms": 1,
            "avg_write_latency_ms": 1, "total_io_stall_ms": 2, "size_on_disk_mb": 1,
        }]
        with patch.object(mon, "execute_readonly_query", _dispatch([("dm_io_virtual_file_stats", rows)])):
            out = json.loads(mon.get_io_stats.invoke({"config": CONFIG}))
        assert out["high_latency_files"] == 0
        # 无高延迟 -> recommendations 全为 None
        assert all(r is None for r in out["recommendations"])

    def test_error_sanitized(self):
        with patch.object(mon, "execute_readonly_query", side_effect=RuntimeError("e")):
            out = json.loads(mon.get_io_stats.invoke({"config": CONFIG}))
        assert out["error"] == "e"


# ============================ check_backup_status ============================
class TestBackupStatus:
    def test_no_backupset_table_early_return(self):
        with patch.object(mon, "execute_readonly_query",
                          _dispatch([("has_backupset_table", [{"has_backupset_table": 0}])])):
            out = json.loads(mon.check_backup_status.invoke({"config": CONFIG}))
        assert out["has_backup"] is False
        assert "backupset" in out["message"]

    def test_backupset_check_exception(self):
        # 第一个查询(表检查)就抛异常
        def _impl(query, params=None, config=None, database=None):
            raise RuntimeError("perm denied")

        with patch.object(mon, "execute_readonly_query", _impl):
            out = json.loads(mon.check_backup_status.invoke({"config": CONFIG}))
        assert out["has_backup"] is False
        assert "perm denied" in out["message"]

    def test_detects_never_backed_up_and_stale_issues(self):
        history = [{
            "database_name": "appdb", "backup_start_date": "2024-06-01 00:00:00",
            "backup_finish_date": "2024-06-01 00:10:00", "duration_seconds": 600,
            "backup_type": "D", "backup_type_desc": "完整备份",
            "backup_size_mb": 100, "compressed_size_mb": 50,
            "backup_path": "/bk/appdb.bak", "recovery_model": "FULL",
        }]
        last = [
            # 从未完整备份 -> critical
            {"database_name": "neverdb", "recovery_model": "SIMPLE",
             "last_full_backup": None, "last_diff_backup": None, "last_log_backup": None,
             "hours_since_full_backup": None, "hours_since_log_backup": None},
            # 完整备份超 7 天(168h) -> warning
            {"database_name": "staledb", "recovery_model": "SIMPLE",
             "last_full_backup": "2024-01-01", "last_diff_backup": None, "last_log_backup": None,
             "hours_since_full_backup": 200, "hours_since_log_backup": None},
            # FULL 模式日志备份超 24h -> warning
            {"database_name": "logdb", "recovery_model": "FULL",
             "last_full_backup": "2024-06-01", "last_diff_backup": None, "last_log_backup": "2024-05-01",
             "hours_since_full_backup": 10, "hours_since_log_backup": 48},
            # 正常 -> ok
            {"database_name": "okdb", "recovery_model": "SIMPLE",
             "last_full_backup": "2024-06-20", "last_diff_backup": None, "last_log_backup": None,
             "hours_since_full_backup": 5, "hours_since_log_backup": None},
        ]
        matchers = [
            ("has_backupset_table", [{"has_backupset_table": 1}]),
            ("FROM msdb.dbo.backupset bs", history),
            ("MAX(CASE WHEN bs.type", last),
        ]
        with patch.object(mon, "execute_readonly_query", _dispatch(matchers)):
            out = json.loads(mon.check_backup_status.invoke({"days": 7, "config": CONFIG}))

        assert out["has_issues"] is True
        assert out["backup_history_count"] == 1
        # 备份历史日期/大小被格式化
        h = out["backup_history"][0]
        assert h["backup_start_date"] == "2024-06-01 00:00:00"
        assert h["backup_size_formatted"] == "100.00 MB"
        # 状态判定
        statuses = {r["database_name"]: r["status"] for r in out["last_backups_by_database"]}
        assert statuses["neverdb"] == "critical"
        assert statuses["staledb"] == "warning"
        assert statuses["logdb"] == "warning"
        assert statuses["okdb"] == "ok"
        # 从未备份的库 last_full_backup 文案
        never = next(r for r in out["last_backups_by_database"] if r["database_name"] == "neverdb")
        assert never["last_full_backup"] == "从未备份"
        assert len(out["issues"]) == 3

    def test_final_query_error_sanitized(self):
        def _impl(query, params=None, config=None, database=None):
            if "has_backupset_table" in query:
                return [{"has_backupset_table": 1}]
            raise RuntimeError("query failed")

        with patch.object(mon, "execute_readonly_query", _impl):
            out = json.loads(mon.check_backup_status.invoke({"config": CONFIG}))
        assert out["error"] == "query failed"


# ============================ check_agent_jobs ============================
class TestAgentJobs:
    def test_no_sysjobs_table_early_return(self):
        with patch.object(mon, "execute_readonly_query",
                          _dispatch([("has_sysjobs_table", [{"has_sysjobs_table": 0}])])):
            out = json.loads(mon.check_agent_jobs.invoke({"config": CONFIG}))
        assert out["has_agent"] is False
        assert "Agent" in out["message"]

    def test_jobs_with_failures_and_running(self):
        jobs = [
            {"job_id": b"\x01\x02", "job_name": "nightly", "description": "x", "enabled": 1,
             "enabled_desc": "已启用", "category_name": "Maint",
             "date_created": "2024-01-01", "date_modified": "2024-02-01",
             "last_run_requested": "2024-06-01", "last_start_time": "2024-06-01 01:00:00",
             "last_stop_time": None, "current_status": "运行中"},
            {"job_id": "guid-str", "job_name": "weekly", "description": None, "enabled": 0,
             "enabled_desc": "已禁用", "category_name": None,
             "date_created": None, "date_modified": None,
             "last_run_requested": None, "last_start_time": None,
             "last_stop_time": "2024-06-01 02:00:00", "current_status": "空闲"},
        ]
        failed = [{"job_name": "weekly", "failure_count": 3, "last_failure_time": "2024-06-01 02:00:00"}]
        history = [
            {"job_name": "weekly", "step_id": 0, "step_name": "(Job outcome)", "run_status": 0,
             "run_status_desc": "失败", "run_datetime": "2024-06-01 02:00:00",
             "run_duration": 100, "duration_seconds": 60, "message": "Error: " + "x" * 600},
            {"job_name": "nightly", "step_id": 0, "step_name": "(Job outcome)", "run_status": 1,
             "run_status_desc": "成功", "run_datetime": "2024-06-01 01:10:00",
             "run_duration": 100, "duration_seconds": 60, "message": "OK"},
        ]
        matchers = [
            ("has_sysjobs_table", [{"has_sysjobs_table": 1}]),
            ("h.run_status = 0", failed),       # failed_jobs_query 含此谓词
            ("FROM msdb.dbo.sysjobhistory h", history),
            ("FROM msdb.dbo.sysjobs j", jobs),  # jobs_query 兜底
        ]
        with patch.object(mon, "execute_readonly_query", _dispatch(matchers)):
            out = json.loads(mon.check_agent_jobs.invoke({"include_history": True, "config": CONFIG}))

        assert out["total_jobs"] == 2
        assert out["enabled_jobs"] == 1
        assert out["running_jobs"] == 1
        assert out["has_failures"] is True
        assert out["recent_failure_count"] == 1
        # bytes job_id -> hex
        nightly = next(j for j in out["jobs"] if j["job_name"] == "nightly")
        assert nightly["job_id"] == "0102"
        # 过长消息被截断 + 省略号
        failmsg = next(h for h in out["recent_history"] if h["job_name"] == "weekly")["message"]
        assert failmsg.endswith("...")
        assert len(failmsg) == 503

    def test_include_history_false_skips_history(self):
        jobs = [{"job_id": "g", "job_name": "j", "description": None, "enabled": 1,
                 "enabled_desc": "已启用", "category_name": None,
                 "date_created": None, "date_modified": None,
                 "last_run_requested": None, "last_start_time": None,
                 "last_stop_time": None, "current_status": "空闲"}]
        matchers = [
            ("has_sysjobs_table", [{"has_sysjobs_table": 1}]),
            ("h.run_status = 0", []),
            ("FROM msdb.dbo.sysjobs j", jobs),
        ]
        with patch.object(mon, "execute_readonly_query", _dispatch(matchers)):
            out = json.loads(mon.check_agent_jobs.invoke({"include_history": False, "config": CONFIG}))
        assert out["recent_history"] == []
        assert out["recent_failure_count"] == 0


# ============================ check_replication_status ============================
class TestReplicationStatus:
    def test_no_publications_table_early_return(self):
        with patch.object(mon, "execute_readonly_query",
                          _dispatch([("has_publications_table", [{"has_publications_table": 0}])])):
            out = json.loads(mon.check_replication_status.invoke({"config": CONFIG}))
        assert out["has_replication"] is False
        assert "sys.publications" in out["message"]

    def test_no_distributor_no_publications(self):
        matchers = [
            ("has_publications_table", [{"has_publications_table": 1}]),
            ("has_distributor", [{"has_distributor": 0}]),
            ("FROM sys.publications p", []),  # publications_query 返回空
        ]
        with patch.object(mon, "execute_readonly_query", _dispatch(matchers)):
            out = json.loads(mon.check_replication_status.invoke({"config": CONFIG}))
        assert out["has_replication"] is False

    def test_distributor_with_failed_agent_and_high_latency(self):
        publications = [{"publication_name": "pub1", "description": "d",
                         "publication_type_desc": "事务复制", "status": 1, "status_desc": "活动",
                         "immediate_sync": 1, "allow_pull": 1, "allow_push": 1, "database_name": "appdb"}]
        subscriptions = [{"publication_name": "pub1", "article_name": "a1", "subscriber_db": "sub",
                          "status": 2, "status_desc": "活动", "sync_type": 1, "sync_type_desc": "自动"}]
        agents = [{"agent_name": "agent_x", "publisher_db": "appdb", "publication": "pub1",
                   "subscriber_db": "sub", "status_desc": "失败", "start_time": "2024-06-01",
                   "time": "2024-06-01", "duration": 10, "last_message": "z" * 400}]
        pending = [{"agent_name": "agent_x", "publisher_db": "appdb", "publication": "pub1",
                    "subscriber_db": "sub", "pending_commands": 500,
                    "oldest_command_time": "2024-06-01", "max_latency_seconds": 600}]

        def _impl(query, params=None, config=None, database=None):
            if "has_publications_table" in query:
                return [{"has_publications_table": 1}]
            if "has_distributor" in query:
                return [{"has_distributor": 1}]
            if "FROM sys.publications p\n    INNER JOIN sys.articles" in query or "INNER JOIN sys.articles" in query:
                return subscriptions
            if "FROM sys.publications p" in query:
                return publications
            if "MSdistribution_agents da" in query and "MSrepl_commands" in query:
                return pending
            if "MSdistribution_agents" in query:
                return agents
            return []

        with patch.object(mon, "execute_readonly_query", _impl):
            out = json.loads(mon.check_replication_status.invoke({"config": CONFIG}))

        assert out["has_replication"] is True
        assert out["has_distributor"] is True
        assert out["publication_count"] == 1
        assert out["agent_count"] == 1
        # 失败代理 + 高延迟(>300s) 各产生一条 issue
        assert out["has_issues"] is True
        assert len(out["issues"]) == 2
        # 代理 last_message 过长被截断
        assert out["agents"][0]["last_message"].endswith("...")

    def test_error_sanitized(self):
        with patch.object(mon, "execute_readonly_query", side_effect=RuntimeError("boom")):
            out = json.loads(mon.check_replication_status.invoke({"config": CONFIG}))
        assert out["error"] == "boom"


# ============================ check_database_size_growth ============================
class TestDatabaseSizeGrowth:
    def test_no_backupset_early_return(self):
        with patch.object(mon, "execute_readonly_query",
                          _dispatch([("has_backupset_table", [{"has_backupset_table": 0}])])):
            out = json.loads(mon.check_database_size_growth.invoke({"config": CONFIG}))
        assert out["has_growth_data"] is False

    def test_computes_growth_trend_and_flags_fast_growing(self):
        # appdb: 两次完整备份, 从 100MB 增至 200MB (10 天) -> 100% 增长 -> fast growing
        history = [
            {"database_name": "appdb", "backup_date": "2024-06-01",
             "backup_size_mb": 100, "compressed_size_mb": 50, "backup_type": "D"},
            {"database_name": "appdb", "backup_date": "2024-06-11",
             "backup_size_mb": 200, "compressed_size_mb": 100, "backup_type": "D"},
            # single-record db
            {"database_name": "soledb", "backup_date": "2024-06-05",
             "backup_size_mb": 30, "compressed_size_mb": 15, "backup_type": "D"},
        ]
        current = [
            {"database_name": "appdb", "data_size_mb": 180, "log_size_mb": 20, "total_size_mb": 200},
            # nobackup 在当前库但无备份记录
            {"database_name": "nobackupdb", "data_size_mb": 5, "log_size_mb": 1, "total_size_mb": 6},
        ]
        files = [{"database_name": "appdb", "file_id": 1, "file_name": "appdb",
                  "file_type": "ROWS", "current_size_mb": 180, "max_size": -1,
                  "growth_setting": "64 MB", "is_percent_growth": 0, "growth": 8192}]
        matchers = [
            ("has_backupset_table", [{"has_backupset_table": 1}]),
            ("type = 'D'", history),                    # growth_query
            ("FROM sys.databases d\n    INNER JOIN sys.master_files mf", current),
            ("FROM sys.master_files\n    WHERE database_id > 4", files),
        ]
        with patch.object(mon, "execute_readonly_query", _dispatch(matchers)):
            out = json.loads(mon.check_database_size_growth.invoke({"days": 30, "config": CONFIG}))

        # appdb 增长趋势
        appdb = next(g for g in out["growth_trends"] if g["database_name"] == "appdb")
        assert appdb["growth_mb"] == 100
        assert appdb["growth_percent"] == 100.0
        assert appdb["days_analyzed"] == 10
        assert appdb["daily_growth_mb"] == 10.0
        assert appdb["backup_count"] == 2
        # 单条记录库带 note
        soledb = next(g for g in out["growth_trends"] if g["database_name"] == "soledb")
        assert soledb["backup_count"] == 1
        assert "无法计算增长趋势" in soledb["note"]
        # appdb (>10%) 被标记快速增长
        assert "appdb" in out["fast_growing_databases"]
        # nobackupdb 当前存在但无备份记录
        assert "nobackupdb" in out["databases_without_backup"]
        # 当前大小格式化
        cur_appdb = next(c for c in out["current_sizes"] if c["database_name"] == "appdb")
        assert cur_appdb["total_size_formatted"] == "200.00 MB"
        assert out["summary"]["fast_growing_count"] == 1

    def test_error_sanitized(self):
        def _impl(query, params=None, config=None, database=None):
            if "has_backupset_table" in query:
                return [{"has_backupset_table": 1}]
            raise RuntimeError("growth boom")

        with patch.object(mon, "execute_readonly_query", _impl):
            out = json.loads(mon.check_database_size_growth.invoke({"config": CONFIG}))
        assert out["error"] == "growth boom"
