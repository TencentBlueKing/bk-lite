"""MSSQL监控指标采集工具"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.mssql.utils import execute_readonly_query, format_duration, format_size, safe_json_dumps


@tool()
def get_database_metrics(config: RunnableConfig = None):
    """
    获取数据库级别监控指标

    **何时使用此工具:**
    - 收集数据库性能指标
    - 监控数据库健康状态
    - 生成监控报告

    **工具能力:**
    - 采集数据库大小、连接数等核心指标
    - 显示各数据库的资源使用情况
    - 提供趋势分析数据

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含数据库指标
    """
    query = """
    SELECT
        d.name as database_name,
        d.state_desc as state,
        d.recovery_model_desc as recovery_model,
        d.compatibility_level,
        d.create_date,
        (SELECT COUNT(*) FROM sys.dm_exec_sessions WHERE database_id = d.database_id AND is_user_process = 1) as active_connections,
        (SELECT SUM(size) * 8 / 1024 FROM sys.master_files WHERE database_id = d.database_id AND type = 0) as data_size_mb,
        (SELECT SUM(size) * 8 / 1024 FROM sys.master_files WHERE database_id = d.database_id AND type = 1) as log_size_mb
    FROM sys.databases d
    WHERE d.database_id > 4  -- 排除系统数据库
    ORDER BY d.name;
    """

    # 缓存命中率查询
    cache_query = """
    SELECT
        DB_NAME(database_id) as database_name,
        SUM(user_seeks + user_scans + user_lookups) as buffer_pool_reads,
        SUM(user_seeks) as index_seeks,
        SUM(user_scans) as index_scans,
        SUM(user_lookups) as index_lookups,
        SUM(user_updates) as index_updates
    FROM sys.dm_db_index_usage_stats
    WHERE database_id > 4
    GROUP BY database_id
    ORDER BY buffer_pool_reads DESC;
    """

    try:
        results = execute_readonly_query(query, config=config)
        cache_stats = execute_readonly_query(cache_query, config=config)

        # 创建缓存统计映射
        cache_map = {row["database_name"]: row for row in cache_stats}

        # 格式化和增强数据
        for row in results:
            row["data_size_formatted"] = format_size(row["data_size_mb"] * 1024 * 1024) if row["data_size_mb"] else "0 B"
            row["log_size_formatted"] = format_size(row["log_size_mb"] * 1024 * 1024) if row["log_size_mb"] else "0 B"
            row["create_date"] = str(row["create_date"]) if row["create_date"] else None

            # 合并缓存统计
            db_name = row["database_name"]
            if db_name in cache_map:
                row["buffer_pool_reads"] = cache_map[db_name]["buffer_pool_reads"]
                row["index_seeks"] = cache_map[db_name]["index_seeks"]
                row["index_scans"] = cache_map[db_name]["index_scans"]

        return safe_json_dumps({"total_databases": len(results), "databases": results})
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def get_table_metrics(schema_name: str = "dbo", table: str = None, config: RunnableConfig = None):
    """
    获取表级别监控指标

    **何时使用此工具:**
    - 监控表的访问模式
    - 分析表性能
    - 识别热表

    **工具能力:**
    - 采集表的读写统计
    - 显示索引使用情况
    - 监控表大小和行数

    Args:
        schema_name (str, optional): Schema名,默认dbo
        table (str, optional): 表名,不填则返回所有表
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含表指标
    """
    if table:
        query = """
        SELECT
            s.name as schema_name,
            t.name as table_name,
            p.rows as row_count,
            SUM(a.total_pages) * 8 as total_space_kb,
            SUM(a.used_pages) * 8 as used_space_kb,
            (SUM(a.total_pages) - SUM(a.used_pages)) * 8 as unused_space_kb,
            i.user_seeks,
            i.user_scans,
            i.user_lookups,
            i.user_updates,
            i.last_user_seek,
            i.last_user_scan,
            i.last_user_update
        FROM sys.tables t
        INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
        INNER JOIN sys.indexes idx ON t.object_id = idx.object_id AND idx.index_id <= 1
        INNER JOIN sys.partitions p ON idx.object_id = p.object_id AND idx.index_id = p.index_id
        INNER JOIN sys.allocation_units a ON p.partition_id = a.container_id
        LEFT JOIN sys.dm_db_index_usage_stats i ON t.object_id = i.object_id AND idx.index_id = i.index_id AND i.database_id = DB_ID()
        WHERE s.name = ? AND t.name = ?
        GROUP BY s.name, t.name, p.rows, i.user_seeks, i.user_scans, i.user_lookups, i.user_updates,
                 i.last_user_seek, i.last_user_scan, i.last_user_update;
        """
        params = (schema_name, table)
    else:
        query = """
        SELECT TOP 50
            s.name as schema_name,
            t.name as table_name,
            p.rows as row_count,
            SUM(a.total_pages) * 8 as total_space_kb,
            SUM(a.used_pages) * 8 as used_space_kb,
            i.user_seeks,
            i.user_scans,
            i.user_lookups,
            i.user_updates
        FROM sys.tables t
        INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
        INNER JOIN sys.indexes idx ON t.object_id = idx.object_id AND idx.index_id <= 1
        INNER JOIN sys.partitions p ON idx.object_id = p.object_id AND idx.index_id = p.index_id
        INNER JOIN sys.allocation_units a ON p.partition_id = a.container_id
        LEFT JOIN sys.dm_db_index_usage_stats i ON t.object_id = i.object_id AND idx.index_id = i.index_id AND i.database_id = DB_ID()
        WHERE s.name = ?
        GROUP BY s.name, t.name, p.rows, i.user_seeks, i.user_scans, i.user_lookups, i.user_updates
        ORDER BY (COALESCE(i.user_seeks, 0) + COALESCE(i.user_scans, 0)) DESC;
        """
        params = (schema_name,)

    try:
        results = execute_readonly_query(query, params=params, config=config)

        # 格式化数据
        for row in results:
            row["total_space_formatted"] = format_size(row["total_space_kb"] * 1024)
            row["used_space_formatted"] = format_size(row["used_space_kb"] * 1024) if row.get("used_space_kb") else "N/A"

            # 格式化时间字段
            for time_field in ["last_user_seek", "last_user_scan", "last_user_update"]:
                if time_field in row and row[time_field]:
                    row[time_field] = str(row[time_field])

        return safe_json_dumps({"schema": schema_name, "table": table, "total_tables": len(results), "tables": results})
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def get_wait_stats(config: RunnableConfig = None):
    """
    获取等待统计信息

    **何时使用此工具:**
    - 分析系统性能瓶颈
    - 识别等待类型
    - 优化数据库性能

    **工具能力:**
    - 显示各种等待类型的统计
    - 帮助识别IO、CPU、锁等瓶颈
    - 提供等待时间分析

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含等待统计
    """
    query = """
    SELECT TOP 20
        wait_type,
        waiting_tasks_count,
        wait_time_ms / 1000.0 as wait_time_s,
        max_wait_time_ms,
        signal_wait_time_ms / 1000.0 as signal_wait_time_s,
        CASE
            WHEN wait_time_ms > 0
            THEN CAST(100.0 * signal_wait_time_ms / wait_time_ms AS DECIMAL(5,2))
            ELSE 0
        END as signal_wait_percent
    FROM sys.dm_os_wait_stats
    WHERE wait_type NOT IN (
        'CLR_SEMAPHORE', 'LAZYWRITER_SLEEP', 'RESOURCE_QUEUE', 'SLEEP_TASK',
        'SLEEP_SYSTEMTASK', 'SQLTRACE_BUFFER_FLUSH', 'WAITFOR', 'LOGMGR_QUEUE',
        'CHECKPOINT_QUEUE', 'REQUEST_FOR_DEADLOCK_SEARCH', 'XE_TIMER_EVENT',
        'BROKER_TO_FLUSH', 'BROKER_TASK_STOP', 'CLR_MANUAL_EVENT', 'CLR_AUTO_EVENT',
        'DISPATCHER_QUEUE_SEMAPHORE', 'FT_IFTS_SCHEDULER_IDLE_WAIT', 'XE_DISPATCHER_WAIT',
        'XE_DISPATCHER_JOIN', 'SQLTRACE_INCREMENTAL_FLUSH_SLEEP', 'ONDEMAND_TASK_QUEUE',
        'BROKER_EVENTHANDLER', 'SLEEP_BPOOL_FLUSH', 'DIRTY_PAGE_POLL', 'HADR_FILESTREAM_IOMGR_IOCOMPLETION'
    )
    AND waiting_tasks_count > 0
    ORDER BY wait_time_ms DESC;
    """

    try:
        results = execute_readonly_query(query, config=config)

        # 格式化数据
        for row in results:
            row["wait_time_formatted"] = format_duration(row["wait_time_s"] * 1000)
            row["max_wait_time_formatted"] = format_duration(row["max_wait_time_ms"])

        # 分类等待类型
        io_waits = [r for r in results if "PAGEIO" in r["wait_type"] or "IO" in r["wait_type"]]
        lock_waits = [r for r in results if "LCK" in r["wait_type"]]
        memory_waits = [r for r in results if "MEMORY" in r["wait_type"] or "RESOURCE" in r["wait_type"]]

        return safe_json_dumps(
            {
                "total_wait_types": len(results),
                "all_waits": results,
                "summary": {"io_related_waits": len(io_waits), "lock_related_waits": len(lock_waits), "memory_related_waits": len(memory_waits)},
            }
        )
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def get_instance_metrics(config: RunnableConfig = None):
    """
    获取实例级别监控指标

    **何时使用此工具:**
    - 监控SQL Server实例整体状态
    - 收集性能计数器
    - 评估实例资源使用

    **工具能力:**
    - 显示CPU、内存使用情况
    - 监控缓冲池和连接数
    - 提供性能计数器数据

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含实例指标
    """
    # 性能计数器
    perf_query = """
    SELECT
        object_name,
        counter_name,
        instance_name,
        cntr_value,
        cntr_type
    FROM sys.dm_os_performance_counters
    WHERE object_name LIKE '%Buffer Manager%'
        OR object_name LIKE '%Memory Manager%'
        OR object_name LIKE '%General Statistics%'
        OR object_name LIKE '%SQL Statistics%'
    ORDER BY object_name, counter_name;
    """

    # 内存使用
    memory_query = """
    SELECT
        physical_memory_in_use_kb / 1024 as memory_used_mb,
        locked_page_allocations_kb / 1024 as locked_pages_mb,
        total_virtual_address_space_kb / 1024 as virtual_memory_mb,
        virtual_address_space_committed_kb / 1024 as committed_memory_mb,
        memory_utilization_percentage,
        process_physical_memory_low,
        process_virtual_memory_low
    FROM sys.dm_os_process_memory;
    """

    # CPU使用
    cpu_query = """
    SELECT TOP 1
        record_id,
        SQLProcessUtilization as sql_cpu_percent,
        SystemIdle as system_idle_percent,
        100 - SystemIdle - SQLProcessUtilization as other_process_cpu_percent
    FROM (
        SELECT
            record.value('(./Record/@id)[1]', 'int') AS record_id,
            record.value('(./Record/SchedulerMonitorEvent/SystemHealth/SystemIdle)[1]', 'int') AS SystemIdle,
            record.value('(./Record/SchedulerMonitorEvent/SystemHealth/ProcessUtilization)[1]', 'int') AS SQLProcessUtilization
        FROM (
            SELECT TOP 1 CONVERT(XML, record) AS record
            FROM sys.dm_os_ring_buffers
            WHERE ring_buffer_type = N'RING_BUFFER_SCHEDULER_MONITOR'
            AND record LIKE '%<SystemHealth>%'
            ORDER BY timestamp DESC
        ) AS x
    ) AS y;
    """

    # 服务器属性
    server_query = """
    SELECT
        SERVERPROPERTY('ServerName') as server_name,
        SERVERPROPERTY('ProductVersion') as product_version,
        SERVERPROPERTY('ProductLevel') as product_level,
        SERVERPROPERTY('Edition') as edition,
        SERVERPROPERTY('EngineEdition') as engine_edition,
        @@VERSION as full_version;
    """

    try:
        perf_counters = execute_readonly_query(perf_query, config=config)
        memory_info = execute_readonly_query(memory_query, config=config)
        server_info = execute_readonly_query(server_query, config=config)

        # CPU信息可能不总是可用
        try:
            cpu_info = execute_readonly_query(cpu_query, config=config)
        except Exception:
            cpu_info = [{"sql_cpu_percent": None, "system_idle_percent": None}]

        # 组织性能计数器
        perf_by_category = {}
        for row in perf_counters:
            category = row["object_name"].strip()
            if category not in perf_by_category:
                perf_by_category[category] = []
            perf_by_category[category].append(
                {
                    "counter": row["counter_name"].strip(),
                    "instance": row["instance_name"].strip() if row["instance_name"] else "",
                    "value": row["cntr_value"],
                }
            )

        # 格式化内存信息
        if memory_info:
            mem = memory_info[0]
            mem["memory_used_formatted"] = format_size(mem["memory_used_mb"] * 1024 * 1024)
            mem["virtual_memory_formatted"] = format_size(mem["virtual_memory_mb"] * 1024 * 1024)

        return safe_json_dumps(
            {
                "server_info": server_info[0] if server_info else {},
                "memory": memory_info[0] if memory_info else {},
                "cpu": cpu_info[0] if cpu_info else {},
                "performance_counters": perf_by_category,
            }
        )
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def get_io_stats(config: RunnableConfig = None):
    """
    获取I/O统计信息

    **何时使用此工具:**
    - 分析磁盘I/O性能
    - 识别I/O瓶颈
    - 监控文件读写

    **工具能力:**
    - 显示各数据库文件的I/O统计
    - 监控读写延迟
    - 识别热点文件

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含I/O统计
    """
    query = """
    SELECT
        DB_NAME(vfs.database_id) as database_name,
        mf.name as logical_name,
        mf.type_desc as file_type,
        mf.physical_name,
        vfs.num_of_reads,
        vfs.num_of_bytes_read / 1024 / 1024 as mb_read,
        vfs.io_stall_read_ms,
        CASE WHEN vfs.num_of_reads > 0
            THEN vfs.io_stall_read_ms / vfs.num_of_reads
            ELSE 0
        END as avg_read_latency_ms,
        vfs.num_of_writes,
        vfs.num_of_bytes_written / 1024 / 1024 as mb_written,
        vfs.io_stall_write_ms,
        CASE WHEN vfs.num_of_writes > 0
            THEN vfs.io_stall_write_ms / vfs.num_of_writes
            ELSE 0
        END as avg_write_latency_ms,
        vfs.io_stall as total_io_stall_ms,
        vfs.size_on_disk_bytes / 1024 / 1024 as size_on_disk_mb
    FROM sys.dm_io_virtual_file_stats(NULL, NULL) vfs
    INNER JOIN sys.master_files mf ON vfs.database_id = mf.database_id AND vfs.file_id = mf.file_id
    WHERE vfs.database_id > 4
    ORDER BY vfs.io_stall DESC;
    """

    try:
        results = execute_readonly_query(query, config=config)

        # 格式化数据
        for row in results:
            row["mb_read_formatted"] = format_size(row["mb_read"] * 1024 * 1024)
            row["mb_written_formatted"] = format_size(row["mb_written"] * 1024 * 1024)
            row["size_on_disk_formatted"] = format_size(row["size_on_disk_mb"] * 1024 * 1024)
            row["avg_read_latency_formatted"] = format_duration(row["avg_read_latency_ms"])
            row["avg_write_latency_formatted"] = format_duration(row["avg_write_latency_ms"])

        # 识别高延迟文件(>20ms平均延迟)
        high_latency_files = [r for r in results if r["avg_read_latency_ms"] > 20 or r["avg_write_latency_ms"] > 20]

        return safe_json_dumps(
            {
                "total_files": len(results),
                "files": results,
                "high_latency_files": len(high_latency_files),
                "recommendations": [
                    "检查高延迟文件的磁盘性能" if high_latency_files else None,
                    "考虑将高I/O文件移动到更快的存储" if high_latency_files else None,
                ],
            }
        )
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def check_backup_status(database_name: str = None, days: int = 7, config: RunnableConfig = None):
    """
    检查数据库备份状态

    **何时使用此工具:**
    - 监控备份是否成功执行
    - 检查备份历史记录
    - 确保数据安全和恢复能力

    **工具能力:**
    - 显示最近的备份记录
    - 检查各数据库的备份状态(完整/差异/日志)
    - 识别长时间未备份的数据库
    - 提供备份大小和时长统计

    Args:
        database_name (str, optional): 数据库名,不填则检查所有数据库
        days (int, optional): 检查最近几天的备份,默认7天
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含备份状态和历史
    """
    # 最近备份记录查询
    if database_name:
        backup_history_query = f"""
        SELECT TOP 50
            bs.database_name,
            bs.backup_start_date,
            bs.backup_finish_date,
            DATEDIFF(SECOND, bs.backup_start_date, bs.backup_finish_date) as duration_seconds,
            bs.type as backup_type,
            CASE bs.type
                WHEN 'D' THEN '完整备份'
                WHEN 'I' THEN '差异备份'
                WHEN 'L' THEN '日志备份'
                WHEN 'F' THEN '文件/文件组备份'
                ELSE bs.type
            END as backup_type_desc,
            bs.backup_size / 1024 / 1024 as backup_size_mb,
            bs.compressed_backup_size / 1024 / 1024 as compressed_size_mb,
            bmf.physical_device_name as backup_path,
            bs.recovery_model,
            bs.server_name,
            bs.user_name as backup_user
        FROM msdb.dbo.backupset bs
        INNER JOIN msdb.dbo.backupmediafamily bmf ON bs.media_set_id = bmf.media_set_id
        WHERE bs.database_name = ?
        AND bs.backup_start_date >= DATEADD(DAY, -{int(days)}, GETDATE())
        ORDER BY bs.backup_start_date DESC;
        """
        params = (database_name,)
    else:
        backup_history_query = f"""
        SELECT TOP 100
            bs.database_name,
            bs.backup_start_date,
            bs.backup_finish_date,
            DATEDIFF(SECOND, bs.backup_start_date, bs.backup_finish_date) as duration_seconds,
            bs.type as backup_type,
            CASE bs.type
                WHEN 'D' THEN '完整备份'
                WHEN 'I' THEN '差异备份'
                WHEN 'L' THEN '日志备份'
                WHEN 'F' THEN '文件/文件组备份'
                ELSE bs.type
            END as backup_type_desc,
            bs.backup_size / 1024 / 1024 as backup_size_mb,
            bs.compressed_backup_size / 1024 / 1024 as compressed_size_mb,
            bmf.physical_device_name as backup_path,
            bs.recovery_model
        FROM msdb.dbo.backupset bs
        INNER JOIN msdb.dbo.backupmediafamily bmf ON bs.media_set_id = bmf.media_set_id
        WHERE bs.backup_start_date >= DATEADD(DAY, -{int(days)}, GETDATE())
        ORDER BY bs.backup_start_date DESC;
        """
        params = None

    # 各数据库最后备份时间
    last_backup_query = """
    SELECT
        d.name as database_name,
        d.recovery_model_desc as recovery_model,
        MAX(CASE WHEN bs.type = 'D' THEN bs.backup_finish_date END) as last_full_backup,
        MAX(CASE WHEN bs.type = 'I' THEN bs.backup_finish_date END) as last_diff_backup,
        MAX(CASE WHEN bs.type = 'L' THEN bs.backup_finish_date END) as last_log_backup,
        DATEDIFF(HOUR, MAX(CASE WHEN bs.type = 'D' THEN bs.backup_finish_date END), GETDATE()) as hours_since_full_backup,
        DATEDIFF(HOUR, MAX(CASE WHEN bs.type = 'L' THEN bs.backup_finish_date END), GETDATE()) as hours_since_log_backup
    FROM sys.databases d
    LEFT JOIN msdb.dbo.backupset bs ON d.name = bs.database_name
    WHERE d.database_id > 4  -- 排除系统数据库
    AND d.state = 0  -- 只检查ONLINE数据库
    GROUP BY d.name, d.recovery_model_desc
    ORDER BY hours_since_full_backup DESC;
    """

    try:
        backup_history = execute_readonly_query(backup_history_query, params=params, config=config)
        last_backups = execute_readonly_query(last_backup_query, config=config)

        # 格式化备份历史
        for row in backup_history:
            row["backup_start_date"] = str(row["backup_start_date"]) if row["backup_start_date"] else None
            row["backup_finish_date"] = str(row["backup_finish_date"]) if row["backup_finish_date"] else None
            row["duration_formatted"] = format_duration(row["duration_seconds"] * 1000) if row["duration_seconds"] else "N/A"
            row["backup_size_formatted"] = format_size(row["backup_size_mb"] * 1024 * 1024) if row["backup_size_mb"] else "N/A"
            row["compressed_size_formatted"] = format_size(row["compressed_size_mb"] * 1024 * 1024) if row["compressed_size_mb"] else "N/A"

        # 格式化最后备份时间并识别问题
        issues = []
        for row in last_backups:
            row["last_full_backup"] = str(row["last_full_backup"]) if row["last_full_backup"] else "从未备份"
            row["last_diff_backup"] = str(row["last_diff_backup"]) if row["last_diff_backup"] else "无"
            row["last_log_backup"] = str(row["last_log_backup"]) if row["last_log_backup"] else "无"

            # 检查问题
            if row["hours_since_full_backup"] is None:
                issues.append(f"{row['database_name']}: 从未进行完整备份")
                row["status"] = "critical"
            elif row["hours_since_full_backup"] > 168:  # 7天
                issues.append(f"{row['database_name']}: 完整备份超过7天 ({row['hours_since_full_backup']}小时)")
                row["status"] = "warning"
            elif row["recovery_model"] == "FULL" and row["hours_since_log_backup"] and row["hours_since_log_backup"] > 24:
                issues.append(f"{row['database_name']}: FULL恢复模式但日志备份超过24小时")
                row["status"] = "warning"
            else:
                row["status"] = "ok"

        return safe_json_dumps(
            {
                "check_days": days,
                "database_filter": database_name,
                "backup_history": backup_history,
                "backup_history_count": len(backup_history),
                "last_backups_by_database": last_backups,
                "issues": issues,
                "has_issues": len(issues) > 0,
                "recommendations": [
                    "确保所有生产数据库有定期完整备份计划",
                    "FULL恢复模式的数据库应有日志备份计划",
                    "定期验证备份文件的可恢复性",
                ]
                if issues
                else [],
            }
        )
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def check_agent_jobs(job_name: str = None, include_history: bool = True, config: RunnableConfig = None):
    """
    检查SQL Server代理作业状态

    **何时使用此工具:**
    - 监控定时作业是否正常执行
    - 检查作业历史和失败记录
    - 确保自动化任务按计划运行

    **工具能力:**
    - 列出所有代理作业及其状态
    - 显示最近执行历史和结果
    - 识别失败的作业
    - 提供下次运行时间

    Args:
        job_name (str, optional): 作业名,不填则检查所有作业
        include_history (bool, optional): 是否包含执行历史,默认True
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含作业状态和历史
    """
    # 作业列表查询
    if job_name:
        jobs_query = """
        SELECT
            j.job_id,
            j.name as job_name,
            j.description,
            j.enabled,
            CASE j.enabled WHEN 1 THEN '已启用' ELSE '已禁用' END as enabled_desc,
            c.name as category_name,
            j.date_created,
            j.date_modified,
            ja.run_requested_date as last_run_requested,
            ja.start_execution_date as last_start_time,
            ja.stop_execution_date as last_stop_time,
            CASE ja.run_requested_source
                WHEN 1 THEN '计划触发'
                WHEN 2 THEN '警报触发'
                WHEN 3 THEN '启动触发'
                WHEN 4 THEN '用户执行'
                ELSE '未知'
            END as last_run_source,
            CASE
                WHEN ja.start_execution_date IS NOT NULL AND ja.stop_execution_date IS NULL THEN '运行中'
                ELSE '空闲'
            END as current_status
        FROM msdb.dbo.sysjobs j
        LEFT JOIN msdb.dbo.syscategories c ON j.category_id = c.category_id
        LEFT JOIN msdb.dbo.sysjobactivity ja ON j.job_id = ja.job_id
            AND ja.session_id = (SELECT MAX(session_id) FROM msdb.dbo.sysjobactivity)
        WHERE j.name = ?
        ORDER BY j.name;
        """
        job_params = (job_name,)
    else:
        jobs_query = """
        SELECT
            j.job_id,
            j.name as job_name,
            j.description,
            j.enabled,
            CASE j.enabled WHEN 1 THEN '已启用' ELSE '已禁用' END as enabled_desc,
            c.name as category_name,
            j.date_created,
            j.date_modified,
            ja.run_requested_date as last_run_requested,
            ja.start_execution_date as last_start_time,
            ja.stop_execution_date as last_stop_time,
            CASE
                WHEN ja.start_execution_date IS NOT NULL AND ja.stop_execution_date IS NULL THEN '运行中'
                ELSE '空闲'
            END as current_status
        FROM msdb.dbo.sysjobs j
        LEFT JOIN msdb.dbo.syscategories c ON j.category_id = c.category_id
        LEFT JOIN msdb.dbo.sysjobactivity ja ON j.job_id = ja.job_id
            AND ja.session_id = (SELECT MAX(session_id) FROM msdb.dbo.sysjobactivity)
        ORDER BY j.name;
        """
        job_params = None

    # 最近执行历史(所有作业)
    history_query = """
    SELECT TOP 100
        j.name as job_name,
        h.step_id,
        h.step_name,
        h.run_status,
        CASE h.run_status
            WHEN 0 THEN '失败'
            WHEN 1 THEN '成功'
            WHEN 2 THEN '重试'
            WHEN 3 THEN '已取消'
            WHEN 4 THEN '进行中'
            ELSE '未知'
        END as run_status_desc,
        msdb.dbo.agent_datetime(h.run_date, h.run_time) as run_datetime,
        h.run_duration,
        ((h.run_duration / 10000) * 3600 + ((h.run_duration % 10000) / 100) * 60 + (h.run_duration % 100)) as duration_seconds,
        h.message
    FROM msdb.dbo.sysjobhistory h
    INNER JOIN msdb.dbo.sysjobs j ON h.job_id = j.job_id
    WHERE h.step_id = 0  -- 只看作业级别的历史，不看步骤
    ORDER BY h.instance_id DESC;
    """

    # 失败作业统计
    failed_jobs_query = """
    SELECT
        j.name as job_name,
        COUNT(*) as failure_count,
        MAX(msdb.dbo.agent_datetime(h.run_date, h.run_time)) as last_failure_time
    FROM msdb.dbo.sysjobhistory h
    INNER JOIN msdb.dbo.sysjobs j ON h.job_id = j.job_id
    WHERE h.step_id = 0
    AND h.run_status = 0  -- 失败
    AND h.run_date >= CONVERT(INT, CONVERT(VARCHAR(8), DATEADD(DAY, -7, GETDATE()), 112))
    GROUP BY j.name
    ORDER BY failure_count DESC;
    """

    try:
        jobs = execute_readonly_query(jobs_query, params=job_params, config=config)
        failed_jobs = execute_readonly_query(failed_jobs_query, config=config)

        history = []
        if include_history:
            history = execute_readonly_query(history_query, config=config)

        # 格式化作业信息
        for row in jobs:
            row["date_created"] = str(row["date_created"]) if row["date_created"] else None
            row["date_modified"] = str(row["date_modified"]) if row["date_modified"] else None
            row["last_run_requested"] = str(row["last_run_requested"]) if row.get("last_run_requested") else None
            row["last_start_time"] = str(row["last_start_time"]) if row.get("last_start_time") else None
            row["last_stop_time"] = str(row["last_stop_time"]) if row.get("last_stop_time") else None
            # job_id是bytes类型，转换为字符串
            row["job_id"] = row["job_id"].hex() if isinstance(row["job_id"], bytes) else str(row["job_id"])

        # 格式化历史
        for row in history:
            row["run_datetime"] = str(row["run_datetime"]) if row["run_datetime"] else None
            row["duration_formatted"] = format_duration(row["duration_seconds"] * 1000) if row["duration_seconds"] else "N/A"
            # 截断过长的消息
            if row.get("message") and len(row["message"]) > 500:
                row["message"] = row["message"][:500] + "..."

        # 格式化失败作业
        for row in failed_jobs:
            row["last_failure_time"] = str(row["last_failure_time"]) if row["last_failure_time"] else None

        # 统计
        enabled_jobs = len([j for j in jobs if j["enabled"] == 1])
        running_jobs = len([j for j in jobs if j["current_status"] == "运行中"])
        recent_failures = len([h for h in history if h["run_status"] == 0])

        return safe_json_dumps(
            {
                "job_filter": job_name,
                "total_jobs": len(jobs),
                "enabled_jobs": enabled_jobs,
                "running_jobs": running_jobs,
                "jobs": jobs,
                "recent_history": history if include_history else [],
                "failed_jobs_last_7_days": failed_jobs,
                "recent_failure_count": recent_failures,
                "has_failures": len(failed_jobs) > 0,
                "recommendations": [
                    "检查失败作业的错误消息",
                    "确保作业有适当的重试机制",
                    "考虑为关键作业设置告警",
                ]
                if failed_jobs
                else [],
            }
        )
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def check_replication_status(config: RunnableConfig = None):
    """
    检查数据库复制(发布/订阅)状态

    **何时使用此工具:**
    - 监控发布/订阅复制是否正常
    - 检查复制延迟和延时
    - 确保数据同步正常

    **工具能力:**
    - 显示所有发布和订阅
    - 监控复制代理状态
    - 检查复制延迟和待处理命令
    - 识别复制错误

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含复制状态信息
    """
    # 检查是否配置了复制
    distributor_check = """
    SELECT
        CASE WHEN EXISTS (SELECT 1 FROM sys.databases WHERE name = 'distribution' AND state = 0)
        THEN 1 ELSE 0 END as has_distributor;
    """

    # 发布信息
    publications_query = """
    SELECT
        p.name as publication_name,
        p.description,
        CASE p.publication_type
            WHEN 0 THEN '事务复制'
            WHEN 1 THEN '快照复制'
            WHEN 2 THEN '合并复制'
            ELSE '未知'
        END as publication_type_desc,
        p.status,
        CASE p.status
            WHEN 0 THEN '非活动'
            WHEN 1 THEN '活动'
            ELSE '未知'
        END as status_desc,
        p.immediate_sync,
        p.allow_pull,
        p.allow_push,
        DB_NAME() as database_name
    FROM sys.publications p;
    """

    # 订阅信息
    subscriptions_query = """
    SELECT
        p.name as publication_name,
        a.name as article_name,
        s.dest_db as subscriber_db,
        s.status,
        CASE s.status
            WHEN 0 THEN '非活动'
            WHEN 1 THEN '已订阅'
            WHEN 2 THEN '活动'
            ELSE '未知'
        END as status_desc,
        s.sync_type,
        CASE s.sync_type
            WHEN 1 THEN '自动'
            WHEN 2 THEN '无同步'
            ELSE '未知'
        END as sync_type_desc
    FROM sys.publications p
    INNER JOIN sys.articles a ON p.publication_id = a.publication_id
    LEFT JOIN sys.subscriptions s ON a.article_id = s.article_id;
    """

    # 复制代理状态(分发库)
    agents_query = """
    SELECT
        name as agent_name,
        publisher_db,
        publication,
        subscriber_db,
        CASE status
            WHEN 1 THEN '已启动'
            WHEN 2 THEN '成功'
            WHEN 3 THEN '进行中'
            WHEN 4 THEN '空闲'
            WHEN 5 THEN '重试中'
            WHEN 6 THEN '失败'
            ELSE '未知'
        END as status_desc,
        start_time,
        time as last_activity_time,
        duration,
        comments as last_message
    FROM distribution.dbo.MSdistribution_agents
    WHERE subscriber_db IS NOT NULL;
    """

    # 复制延迟(待处理命令)
    pending_commands_query = """
    SELECT
        da.name as agent_name,
        da.publisher_db,
        da.publication,
        da.subscriber_db,
        COUNT(*) as pending_commands,
        MIN(c.entry_time) as oldest_command_time,
        DATEDIFF(SECOND, MIN(c.entry_time), GETDATE()) as max_latency_seconds
    FROM distribution.dbo.MSdistribution_agents da
    INNER JOIN distribution.dbo.MSrepl_commands c ON da.id = c.publisher_database_id
    GROUP BY da.name, da.publisher_db, da.publication, da.subscriber_db
    HAVING COUNT(*) > 0;
    """

    try:
        # 首先检查是否有分发数据库
        dist_check = execute_readonly_query(distributor_check, config=config)
        has_distributor = dist_check[0]["has_distributor"] == 1 if dist_check else False

        if not has_distributor:
            # 没有分发数据库，检查是否有发布
            try:
                publications = execute_readonly_query(publications_query, config=config)
                if not publications:
                    return safe_json_dumps({"has_replication": False, "message": "当前数据库未配置复制功能"})
            except Exception:
                return safe_json_dumps({"has_replication": False, "message": "当前数据库未配置复制功能或无权限查看"})

        # 获取发布信息
        publications = []
        try:
            publications = execute_readonly_query(publications_query, config=config)
        except Exception:
            pass

        # 获取订阅信息
        subscriptions = []
        try:
            subscriptions = execute_readonly_query(subscriptions_query, config=config)
        except Exception:
            pass

        # 获取代理状态
        agents = []
        if has_distributor:
            try:
                agents = execute_readonly_query(agents_query, config=config)
                for row in agents:
                    row["start_time"] = str(row["start_time"]) if row.get("start_time") else None
                    row["last_activity_time"] = str(row["last_activity_time"]) if row.get("last_activity_time") else None
                    if row.get("last_message") and len(row["last_message"]) > 300:
                        row["last_message"] = row["last_message"][:300] + "..."
            except Exception:
                pass

        # 获取待处理命令
        pending = []
        if has_distributor:
            try:
                pending = execute_readonly_query(pending_commands_query, config=config)
                for row in pending:
                    row["oldest_command_time"] = str(row["oldest_command_time"]) if row.get("oldest_command_time") else None
                    row["max_latency_formatted"] = format_duration(row["max_latency_seconds"] * 1000) if row.get("max_latency_seconds") else "N/A"
            except Exception:
                pass

        # 识别问题
        issues = []
        failed_agents = [a for a in agents if a.get("status_desc") == "失败"]
        high_latency = [p for p in pending if p.get("max_latency_seconds", 0) > 300]  # 5分钟以上

        for agent in failed_agents:
            issues.append(f"复制代理失败: {agent['agent_name']}")
        for item in high_latency:
            issues.append(f"复制延迟超过5分钟: {item['agent_name']} ({item['pending_commands']}条待处理)")

        return safe_json_dumps(
            {
                "has_replication": True,
                "has_distributor": has_distributor,
                "publications": publications,
                "publication_count": len(publications),
                "subscriptions": subscriptions,
                "subscription_count": len(subscriptions),
                "agents": agents,
                "agent_count": len(agents),
                "pending_commands": pending,
                "issues": issues,
                "has_issues": len(issues) > 0,
                "recommendations": [
                    "检查失败的复制代理并查看错误日志" if failed_agents else None,
                    "排查高延迟的复制链路" if high_latency else None,
                    "确保网络连接稳定" if issues else None,
                ],
            }
        )
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def check_database_size_growth(database_name: str = None, days: int = 30, config: RunnableConfig = None):
    """
    检查数据库大小增长趋势

    **何时使用此工具:**
    - 分析数据库大小的历史变化
    - 预测存储需求和容量规划
    - 检测异常的数据增长

    **工具能力:**
    - 显示数据库大小的历史变化（基于备份记录）
    - 计算增长率和增长量
    - 提供趋势分析和预测
    - 识别快速增长的数据库

    Args:
        database_name (str, optional): 数据库名,不填则检查所有数据库
        days (int, optional): 分析最近几天的数据,默认30天
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含数据库大小增长趋势
    """
    # 基于备份历史的大小变化
    if database_name:
        growth_query = f"""
        SELECT
            database_name,
            CAST(backup_start_date AS DATE) as backup_date,
            backup_size / 1024 / 1024 as backup_size_mb,
            compressed_backup_size / 1024 / 1024 as compressed_size_mb,
            type as backup_type,
            CASE type
                WHEN 'D' THEN '完整备份'
                WHEN 'I' THEN '差异备份'
                WHEN 'L' THEN '日志备份'
                ELSE type
            END as backup_type_desc
        FROM msdb.dbo.backupset
        WHERE database_name = ?
        AND type = 'D'  -- 只看完整备份,更能反映真实大小
        AND backup_start_date >= DATEADD(DAY, -{int(days)}, GETDATE())
        ORDER BY backup_start_date ASC;
        """
        params = (database_name,)
    else:
        growth_query = f"""
        SELECT
            database_name,
            CAST(backup_start_date AS DATE) as backup_date,
            backup_size / 1024 / 1024 as backup_size_mb,
            compressed_backup_size / 1024 / 1024 as compressed_size_mb,
            type as backup_type
        FROM msdb.dbo.backupset
        WHERE type = 'D'  -- 只看完整备份
        AND backup_start_date >= DATEADD(DAY, -{int(days)}, GETDATE())
        ORDER BY database_name, backup_start_date ASC;
        """
        params = None

    # 当前大小查询
    current_size_query = """
    SELECT
        d.name as database_name,
        SUM(CASE WHEN mf.type = 0 THEN mf.size END) * 8 / 1024 as data_size_mb,
        SUM(CASE WHEN mf.type = 1 THEN mf.size END) * 8 / 1024 as log_size_mb,
        SUM(mf.size) * 8 / 1024 as total_size_mb
    FROM sys.databases d
    INNER JOIN sys.master_files mf ON d.database_id = mf.database_id
    WHERE d.database_id > 4
    GROUP BY d.name
    ORDER BY total_size_mb DESC;
    """

    # 文件增长事件（如果有扩展事件）
    file_growth_query = """
    SELECT TOP 50
        DB_NAME(database_id) as database_name,
        file_id,
        name as file_name,
        type_desc as file_type,
        size * 8 / 1024 as current_size_mb,
        max_size,
        CASE
            WHEN growth = 0 THEN '不自动增长'
            WHEN is_percent_growth = 1 THEN CAST(growth AS VARCHAR) + '%'
            ELSE CAST(growth * 8 / 1024 AS VARCHAR) + ' MB'
        END as growth_setting,
        is_percent_growth,
        growth
    FROM sys.master_files
    WHERE database_id > 4
    ORDER BY database_id, file_id;
    """

    try:
        backup_history = execute_readonly_query(growth_query, params=params, config=config)
        current_sizes = execute_readonly_query(current_size_query, config=config)
        file_settings = execute_readonly_query(file_growth_query, config=config)

        # 按数据库分组分析增长趋势
        growth_by_db = {}
        for row in backup_history:
            db = row["database_name"]
            if db not in growth_by_db:
                growth_by_db[db] = []
            growth_by_db[db].append({"date": str(row["backup_date"]), "size_mb": row["backup_size_mb"], "compressed_mb": row["compressed_size_mb"]})

        # 计算增长统计
        growth_analysis = []
        for db, records in growth_by_db.items():
            if len(records) >= 2:
                first_size = records[0]["size_mb"] or 0
                last_size = records[-1]["size_mb"] or 0
                first_date = records[0]["date"]
                last_date = records[-1]["date"]

                growth_mb = last_size - first_size
                growth_percent = ((last_size - first_size) / first_size * 100) if first_size > 0 else 0

                # 计算日均增长
                from datetime import datetime

                try:
                    d1 = datetime.strptime(first_date, "%Y-%m-%d")
                    d2 = datetime.strptime(last_date, "%Y-%m-%d")
                    days_diff = (d2 - d1).days or 1
                    daily_growth_mb = growth_mb / days_diff
                except Exception:
                    days_diff = 1
                    daily_growth_mb = 0

                growth_analysis.append(
                    {
                        "database_name": db,
                        "first_backup_date": first_date,
                        "first_size_mb": round(first_size, 2),
                        "last_backup_date": last_date,
                        "last_size_mb": round(last_size, 2),
                        "growth_mb": round(growth_mb, 2),
                        "growth_percent": round(growth_percent, 2),
                        "days_analyzed": days_diff,
                        "daily_growth_mb": round(daily_growth_mb, 2),
                        "backup_count": len(records),
                        "size_formatted": format_size(last_size * 1024 * 1024),
                        "growth_formatted": format_size(abs(growth_mb) * 1024 * 1024),
                    }
                )
            elif len(records) == 1:
                growth_analysis.append(
                    {
                        "database_name": db,
                        "first_backup_date": records[0]["date"],
                        "first_size_mb": round(records[0]["size_mb"] or 0, 2),
                        "last_backup_date": records[0]["date"],
                        "last_size_mb": round(records[0]["size_mb"] or 0, 2),
                        "growth_mb": 0,
                        "growth_percent": 0,
                        "daily_growth_mb": 0,
                        "backup_count": 1,
                        "note": "只有一次备份记录,无法计算增长趋势",
                    }
                )

        # 排序：按增长百分比降序
        growth_analysis.sort(key=lambda x: x.get("growth_percent", 0), reverse=True)

        # 格式化当前大小
        for row in current_sizes:
            row["data_size_formatted"] = format_size(row["data_size_mb"] * 1024 * 1024) if row["data_size_mb"] else "N/A"
            row["log_size_formatted"] = format_size(row["log_size_mb"] * 1024 * 1024) if row["log_size_mb"] else "N/A"
            row["total_size_formatted"] = format_size(row["total_size_mb"] * 1024 * 1024) if row["total_size_mb"] else "N/A"

        # 识别快速增长的数据库（>10%增长）
        fast_growing = [g for g in growth_analysis if g.get("growth_percent", 0) > 10]

        # 识别无备份记录的数据库
        current_db_names = {r["database_name"] for r in current_sizes}
        backed_up_db_names = set(growth_by_db.keys())
        no_backup_dbs = current_db_names - backed_up_db_names

        return safe_json_dumps(
            {
                "analysis_period_days": days,
                "database_filter": database_name,
                "growth_trends": growth_analysis,
                "current_sizes": current_sizes,
                "file_growth_settings": file_settings,
                "fast_growing_databases": [g["database_name"] for g in fast_growing],
                "databases_without_backup": list(no_backup_dbs),
                "summary": {
                    "total_databases_analyzed": len(growth_analysis),
                    "databases_with_growth": len([g for g in growth_analysis if g.get("growth_mb", 0) > 0]),
                    "databases_with_shrink": len([g for g in growth_analysis if g.get("growth_mb", 0) < 0]),
                    "fast_growing_count": len(fast_growing),
                },
                "recommendations": [
                    "定期清理不需要的数据和日志" if fast_growing else None,
                    "检查快速增长数据库的业务原因" if fast_growing else None,
                    "确保所有数据库都有备份计划" if no_backup_dbs else None,
                    "考虑为大型数据库启用数据压缩" if any(g.get("last_size_mb", 0) > 10240 for g in growth_analysis) else None,
                ],
                "note": "增长趋势基于完整备份记录分析,如无备份记录则无法分析",
            }
        )
    except Exception as e:
        return safe_json_dumps({"error": str(e)})
