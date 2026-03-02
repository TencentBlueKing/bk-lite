"""MSSQL故障诊断工具"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.mssql.utils import execute_readonly_query, format_duration, format_size, safe_json_dumps


@tool()
def diagnose_slow_queries(threshold_ms: int = 1000, limit: int = 20, config: RunnableConfig = None):
    """
    诊断慢查询

    **何时使用此工具:**
    - 用户反馈"系统慢"、"查询慢"
    - 性能分析和优化
    - 定期巡检慢查询

    **工具能力:**
    - 基于sys.dm_exec_query_stats识别慢查询
    - 显示查询的平均/最大执行时间
    - 显示调用次数、总耗时
    - 提供查询文本和统计信息

    Args:
        threshold_ms (int, optional): 慢查询阈值(毫秒),默认1000ms
        limit (int, optional): 返回结果数量,默认20
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含慢查询列表,每个查询包含:
        - query: 查询文本
        - execution_count: 调用次数
        - total_time_ms: 总耗时(ms)
        - avg_time_ms: 平均耗时(ms)
        - max_time_ms: 最大耗时(ms)
    """
    query = f"""
    SELECT TOP {int(limit)}
        SUBSTRING(st.text, (qs.statement_start_offset/2)+1,
            ((CASE qs.statement_end_offset
                WHEN -1 THEN DATALENGTH(st.text)
                ELSE qs.statement_end_offset
            END - qs.statement_start_offset)/2)+1) as query,
        qs.execution_count,
        qs.total_elapsed_time / 1000 as total_time_ms,
        qs.total_elapsed_time / qs.execution_count / 1000 as avg_time_ms,
        qs.max_elapsed_time / 1000 as max_time_ms,
        qs.total_worker_time / 1000 as total_cpu_time_ms,
        qs.total_logical_reads as total_reads,
        qs.total_logical_writes as total_writes,
        qs.creation_time,
        qs.last_execution_time
    FROM sys.dm_exec_query_stats qs
    CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
    WHERE qs.total_elapsed_time / qs.execution_count > ?
    ORDER BY avg_time_ms DESC;
    """

    try:
        # threshold_ms需要转换为微秒(MSSQL使用微秒)
        threshold_us = threshold_ms * 1000
        results = execute_readonly_query(query, params=(threshold_us,), config=config)

        # 格式化时间
        for row in results:
            row["total_time_formatted"] = format_duration(row["total_time_ms"])
            row["avg_time_formatted"] = format_duration(row["avg_time_ms"])
            row["max_time_formatted"] = format_duration(row["max_time_ms"])
            row["creation_time"] = str(row["creation_time"]) if row["creation_time"] else None
            row["last_execution_time"] = str(row["last_execution_time"]) if row["last_execution_time"] else None

        return safe_json_dumps({"threshold_ms": threshold_ms, "total_slow_queries": len(results), "slow_queries": results})
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def diagnose_lock_conflicts(config: RunnableConfig = None):
    """
    检测锁冲突和阻塞

    **何时使用此工具:**
    - 用户反馈"查询卡住"、"事务阻塞"
    - 排查死锁问题
    - 分析锁等待情况

    **工具能力:**
    - 检测当前锁等待情况
    - 显示阻塞关系(哪个进程阻塞了哪个进程)
    - 提供被阻塞查询和阻塞查询的信息
    - 显示等待时长

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含锁冲突列表
    """
    query = """
    SELECT
        r.session_id as blocked_session_id,
        r.blocking_session_id,
        r.wait_type,
        r.wait_time / 1000 as wait_time_ms,
        r.wait_resource,
        r.status as blocked_status,
        blocked_sql.text as blocked_query,
        blocking_sql.text as blocking_query,
        s1.login_name as blocked_login,
        s2.login_name as blocking_login,
        s1.host_name as blocked_host,
        s2.host_name as blocking_host,
        DB_NAME(r.database_id) as database_name
    FROM sys.dm_exec_requests r
    INNER JOIN sys.dm_exec_sessions s1 ON r.session_id = s1.session_id
    LEFT JOIN sys.dm_exec_sessions s2 ON r.blocking_session_id = s2.session_id
    CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) blocked_sql
    OUTER APPLY (
        SELECT text FROM sys.dm_exec_sql_text(
            (SELECT TOP 1 sql_handle FROM sys.dm_exec_requests WHERE session_id = r.blocking_session_id)
        )
    ) blocking_sql
    WHERE r.blocking_session_id > 0;
    """

    try:
        results = execute_readonly_query(query, config=config)

        # 格式化等待时间
        for row in results:
            row["wait_time_formatted"] = format_duration(row["wait_time_ms"])

        return safe_json_dumps({"total_blocked_queries": len(results), "lock_conflicts": results, "has_conflicts": len(results) > 0})
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def diagnose_connection_issues(config: RunnableConfig = None):
    """
    诊断连接池问题

    **何时使用此工具:**
    - 用户反馈"无法连接数据库"
    - 检查连接数是否达到上限
    - 分析连接使用情况

    **工具能力:**
    - 显示当前连接数和最大连接数
    - 按数据库、用户、状态分组统计连接
    - 识别空闲连接和长时间运行的连接
    - 计算连接池使用率

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含连接统计信息
    """
    # 获取最大连接数
    max_conn_query = """
    SELECT CAST(value_in_use AS INT) as max_connections
    FROM sys.configurations
    WHERE name = 'user connections';
    """

    # 当前连接统计
    connections_query = """
    SELECT
        DB_NAME(database_id) as database_name,
        login_name,
        status,
        COUNT(*) as connection_count,
        SUM(CASE WHEN status = 'sleeping' THEN 1 ELSE 0 END) as idle_count,
        SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) as active_count,
        SUM(CASE WHEN status = 'suspended' THEN 1 ELSE 0 END) as suspended_count
    FROM sys.dm_exec_sessions
    WHERE is_user_process = 1
    GROUP BY database_id, login_name, status
    ORDER BY connection_count DESC;
    """

    # 长时间运行的查询
    long_running_query = """
    SELECT TOP 10
        r.session_id,
        s.login_name,
        DB_NAME(r.database_id) as database_name,
        r.status,
        st.text as query,
        r.total_elapsed_time / 1000 as duration_ms,
        r.start_time
    FROM sys.dm_exec_requests r
    INNER JOIN sys.dm_exec_sessions s ON r.session_id = s.session_id
    CROSS APPLY sys.dm_exec_sql_text(r.sql_handle) st
    WHERE r.total_elapsed_time > 300000000  -- 5分钟以上(微秒)
    ORDER BY r.total_elapsed_time DESC;
    """  # noqa

    try:
        max_conn = execute_readonly_query(max_conn_query, config=config)
        connections = execute_readonly_query(connections_query, config=config)
        long_running = execute_readonly_query(long_running_query, config=config)

        # 计算总连接数
        total_connections = sum(row["connection_count"] for row in connections)
        max_connections = max_conn[0]["max_connections"] if max_conn[0]["max_connections"] > 0 else 32767
        usage_percent = round((total_connections / max_connections) * 100, 2)

        # 格式化长时间运行的查询
        for row in long_running:
            row["duration_formatted"] = format_duration(row["duration_ms"])
            row["start_time"] = str(row["start_time"]) if row["start_time"] else None

        return safe_json_dumps(
            {
                "max_connections": max_connections,
                "current_connections": total_connections,
                "usage_percent": usage_percent,
                "is_near_limit": usage_percent > 80,
                "connections_by_state": connections,
                "long_running_queries": long_running,
            }
        )
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def check_database_health(config: RunnableConfig = None):
    """
    整体数据库健康检查

    **何时使用此工具:**
    - 定期健康巡检
    - 快速了解数据库状态
    - 发现潜在问题

    **工具能力:**
    - 检查连接数、锁等待、长事务
    - 检查数据库状态和可用性
    - 检查磁盘使用情况
    - 提供健康状态评分

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含健康检查结果
    """
    # 基础统计
    stats_query = """
    SELECT
        (SELECT CAST(value_in_use AS INT) FROM sys.configurations WHERE name = 'user connections') as max_connections,
        (SELECT COUNT(*) FROM sys.dm_exec_sessions WHERE is_user_process = 1) as current_connections,
        (SELECT COUNT(*) FROM sys.dm_exec_requests WHERE status = 'running') as active_queries,
        (SELECT COUNT(*) FROM sys.dm_exec_requests WHERE status = 'suspended') as suspended_queries,
        (SELECT COUNT(*) FROM sys.dm_exec_requests WHERE blocking_session_id > 0) as blocked_queries,
        (SELECT COUNT(*) FROM sys.dm_exec_requests WHERE total_elapsed_time > 3600000000) as long_running_queries;
    """

    # 数据库状态检查
    db_status_query = """
    SELECT
        name as database_name,
        state_desc as state,
        user_access_desc as user_access,
        recovery_model_desc as recovery_model
    FROM sys.databases
    WHERE database_id > 4  -- 排除系统数据库
    ORDER BY name;
    """

    # 磁盘空间检查
    disk_space_query = """
    SELECT
        DB_NAME(database_id) as database_name,
        type_desc as file_type,
        name as logical_name,
        physical_name,
        size * 8 / 1024 as size_mb,
        CAST(FILEPROPERTY(name, 'SpaceUsed') AS BIGINT) * 8 / 1024 as used_mb,
        (size * 8 / 1024) - (CAST(FILEPROPERTY(name, 'SpaceUsed') AS BIGINT) * 8 / 1024) as free_mb
    FROM sys.master_files
    WHERE database_id = DB_ID();
    """

    try:
        stats = execute_readonly_query(stats_query, config=config)[0]
        db_statuses = execute_readonly_query(db_status_query, config=config)
        disk_space = execute_readonly_query(disk_space_query, config=config)

        # 计算健康评分
        issues = []
        health_score = 100

        # 连接数检查
        max_conn = stats["max_connections"] if stats["max_connections"] > 0 else 32767
        conn_usage = (stats["current_connections"] / max_conn) * 100
        if conn_usage > 90:
            issues.append("连接数超过90%")
            health_score -= 20
        elif conn_usage > 80:
            issues.append("连接数超过80%")
            health_score -= 10

        # 阻塞检查
        if stats["blocked_queries"] > 0:
            issues.append(f"存在{stats['blocked_queries']}个被阻塞的查询")
            health_score -= 15

        # 长时间运行查询检查
        if stats["long_running_queries"] > 0:
            issues.append(f"存在{stats['long_running_queries']}个长时间运行的查询(>1小时)")
            health_score -= 15

        # 数据库状态检查
        offline_dbs = [db for db in db_statuses if db["state"] != "ONLINE"]
        if offline_dbs:
            issues.append(f"存在{len(offline_dbs)}个非ONLINE状态的数据库")
            health_score -= 20

        # 确定健康状态
        if health_score >= 90:
            health_status = "healthy"
        elif health_score >= 70:
            health_status = "warning"
        else:
            health_status = "critical"

        # 格式化磁盘空间
        for row in disk_space:
            row["size_formatted"] = format_size(row["size_mb"] * 1024 * 1024)
            row["used_formatted"] = format_size(row["used_mb"] * 1024 * 1024) if row["used_mb"] else "N/A"
            row["free_formatted"] = format_size(row["free_mb"] * 1024 * 1024) if row["free_mb"] else "N/A"

        return safe_json_dumps(
            {
                "health_status": health_status,
                "health_score": health_score,
                "statistics": stats,
                "issues": issues,
                "database_statuses": db_statuses,
                "disk_space": disk_space,
                "recommendations": [
                    item
                    for item in [
                        "定期监控连接数使用情况" if conn_usage > 70 else None,
                        "排查并解决阻塞问题" if stats["blocked_queries"] > 0 else None,
                        "分析长时间运行的查询" if stats["long_running_queries"] > 0 else None,
                        "检查非ONLINE数据库的状态" if offline_dbs else None,
                    ]
                    if item
                ],
            }
        )
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def check_replication_lag(config: RunnableConfig = None):
    """
    检查数据库镜像/AlwaysOn复制延迟

    **何时使用此工具:**
    - 监控复制延迟
    - 排查数据不一致问题
    - 检查从库健康状态

    **工具能力:**
    - 检测AlwaysOn可用性组状态
    - 显示同步状态和延迟
    - 识别复制问题

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含复制状态信息
    """
    # AlwaysOn可用性组状态
    ag_query = """
    SELECT
        ag.name as availability_group,
        ars.role_desc as role,
        ar.replica_server_name,
        ars.synchronization_health_desc as sync_health,
        ars.operational_state_desc as operational_state,
        ars.connected_state_desc as connected_state,
        drs.synchronization_state_desc as sync_state,
        drs.database_state_desc as database_state,
        DB_NAME(drs.database_id) as database_name,
        drs.log_send_queue_size as log_send_queue_kb,
        drs.redo_queue_size as redo_queue_kb,
        drs.last_commit_time
    FROM sys.availability_groups ag
    INNER JOIN sys.availability_replicas ar ON ag.group_id = ar.group_id
    INNER JOIN sys.dm_hadr_availability_replica_states ars ON ar.replica_id = ars.replica_id
    LEFT JOIN sys.dm_hadr_database_replica_states drs ON ar.replica_id = drs.replica_id
    ORDER BY ag.name, ar.replica_server_name;
    """

    try:
        results = execute_readonly_query(ag_query, config=config)

        if not results:
            return safe_json_dumps({"has_replication": False, "message": "未检测到AlwaysOn可用性组配置"})

        # 格式化数据
        for row in results:
            row["log_send_queue_formatted"] = format_size(row["log_send_queue_kb"] * 1024) if row["log_send_queue_kb"] else "0 B"
            row["redo_queue_formatted"] = format_size(row["redo_queue_kb"] * 1024) if row["redo_queue_kb"] else "0 B"
            row["last_commit_time"] = str(row["last_commit_time"]) if row["last_commit_time"] else None

        return safe_json_dumps({"has_replication": True, "replica_count": len(results), "replicas": results})
    except Exception as e:
        # 可能是没有启用AlwaysOn功能
        error_msg = str(e)
        if "Invalid object name" in error_msg or "does not exist" in error_msg:
            return safe_json_dumps({"has_replication": False, "message": "当前实例未启用AlwaysOn可用性组功能"})
        return safe_json_dumps({"error": error_msg})


@tool()
def diagnose_deadlocks(limit: int = 10, config: RunnableConfig = None):
    """
    诊断死锁问题

    **何时使用此工具:**
    - 应用报告死锁错误
    - 排查事务冲突
    - 分析死锁历史

    **工具能力:**
    - 从系统健康扩展事件中提取死锁信息
    - 显示死锁涉及的资源和进程
    - 帮助识别死锁模式

    Args:
        limit (int, optional): 返回结果数量,默认10
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含死锁诊断信息
    """
    query = f"""
    SELECT TOP {int(limit)}
        xdr.value('@timestamp', 'datetime') as deadlock_time,
        xdr.query('.') as deadlock_graph
    FROM (
        SELECT CAST(target_data AS XML) as target_data
        FROM sys.dm_xe_session_targets st
        INNER JOIN sys.dm_xe_sessions s ON s.address = st.event_session_address
        WHERE s.name = 'system_health'
        AND st.target_name = 'ring_buffer'
    ) AS data
    CROSS APPLY target_data.nodes('RingBufferTarget/event[@name="xml_deadlock_report"]') AS xed(xdr)
    ORDER BY deadlock_time DESC;
    """

    try:
        results = execute_readonly_query(query, config=config)

        if not results:
            return safe_json_dumps({"deadlock_count": 0, "message": "未发现最近的死锁记录"})

        # 格式化时间
        for row in results:
            row["deadlock_time"] = str(row["deadlock_time"]) if row["deadlock_time"] else None
            row["deadlock_graph"] = str(row["deadlock_graph"])[:2000] if row["deadlock_graph"] else None

        return safe_json_dumps(
            {
                "deadlock_count": len(results),
                "deadlocks": results,
                "recommendations": ["分析死锁图确定冲突的资源", "考虑调整事务隔离级别", "优化访问顺序以避免循环等待"],
            }
        )
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def get_failed_queries(limit: int = 20, config: RunnableConfig = None):
    """
    获取失败和错误的查询信息

    **何时使用此工具:**
    - 排查应用错误
    - 分析查询失败原因
    - 监控数据库错误率

    Args:
        limit (int, optional): 返回结果数量,默认20
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含失败查询统计
    """
    # 检查错误日志(最近的错误)
    error_query = f"""
    SELECT TOP {int(limit)}
        LogDate as error_time,
        ProcessInfo as process_info,
        Text as error_message
    FROM sys.fn_readerrorlog(0, 1, N'Error', NULL)
    ORDER BY LogDate DESC;
    """

    # 数据库级别统计
    db_stats_query = """
    SELECT
        DB_NAME(database_id) as database_name,
        SUM(user_seeks + user_scans + user_lookups) as total_reads,
        SUM(user_updates) as total_writes
    FROM sys.dm_db_index_usage_stats
    WHERE database_id > 4
    GROUP BY database_id
    ORDER BY total_reads DESC;
    """

    try:
        errors = execute_readonly_query(error_query, config=config)
        db_stats = execute_readonly_query(db_stats_query, config=config)

        # 格式化时间
        for row in errors:
            row["error_time"] = str(row["error_time"]) if row["error_time"] else None

        return safe_json_dumps({"recent_errors": errors, "error_count": len(errors), "database_stats": db_stats})
    except Exception as e:
        return safe_json_dumps({"error": str(e)})
