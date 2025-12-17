"""PostgreSQL慢查询追踪和会话分析工具"""
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from apps.opspilot.metis.llm.tools.postgres.utils import (
    execute_readonly_query,
    safe_json_dumps,
    format_duration,
)


@tool()
def get_top_queries(order_by: str = "mean_time", limit: int = 20, config: RunnableConfig = None):
    """
    获取Top查询

    **何时使用此工具:**
    - 识别性能瓶颈查询
    - 优化高频查询
    - 分析查询资源消耗

    **工具能力:**
    - 按多种维度排序(平均时间/总时间/调用次数/I/O)
    - 显示查询统计信息
    - 识别资源密集型查询

    **前置要求:**
    - 需要安装pg_stat_statements扩展

    Args:
        order_by (str, optional): 排序字段(mean_time/total_time/calls/rows),默认mean_time
        limit (int, optional): 返回结果数量,默认20
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含Top查询列表
    """
    order_mapping = {
        "mean_time": "mean_exec_time",
        "total_time": "total_exec_time",
        "calls": "calls",
        "rows": "rows"
    }

    order_column = order_mapping.get(order_by, "mean_exec_time")

    query = f"""
    SELECT 
        queryid,
        substring(query, 1, 200) as query,
        calls,
        total_exec_time as total_time,
        mean_exec_time as mean_time,
        min_exec_time as min_time,
        max_exec_time as max_time,
        stddev_exec_time as stddev_time,
        rows as total_rows,
        ROUND(rows::numeric / NULLIF(calls, 0), 2) as rows_per_call,
        shared_blks_hit + shared_blks_read as total_blocks,
        ROUND(100.0 * shared_blks_hit / NULLIF(shared_blks_hit + shared_blks_read, 0), 2) as cache_hit_ratio
    FROM pg_stat_statements
    ORDER BY {order_column} DESC
    LIMIT %s;
    """

    try:
        results = execute_readonly_query(query, params=(limit,), config=config)

        # 格式化时间
        for row in results:
            row["total_time_formatted"] = format_duration(row["total_time"])
            row["mean_time_formatted"] = format_duration(row["mean_time"])
            row["min_time_formatted"] = format_duration(row["min_time"])
            row["max_time_formatted"] = format_duration(row["max_time"])

        return safe_json_dumps({
            "order_by": order_by,
            "total_queries": len(results),
            "queries": results
        })
    except Exception as e:
        error_msg = str(e)
        if "pg_stat_statements" in error_msg:
            return safe_json_dumps({
                "error": "pg_stat_statements扩展未安装或未启用",
                "suggestion": "请在postgresql.conf中添加 shared_preload_libraries = 'pg_stat_statements' 并重启数据库"
            })
        return safe_json_dumps({"error": error_msg})


@tool()
def trace_lock_chain(config: RunnableConfig = None):
    """
    追踪锁等待链

    **何时使用此工具:**
    - 排查复杂的锁等待问题
    - 识别锁等待链路
    - 找到锁的根源

    **工具能力:**
    - 构建锁等待依赖链
    - 显示每个进程的锁信息
    - 识别锁等待的根源进程

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含锁等待链信息
    """
    query = """
    WITH RECURSIVE lock_chain AS (
        -- 找出所有被阻塞的进程
        SELECT 
            blocked.pid AS blocked_pid,
            blocked.usename AS blocked_user,
            blocked.query AS blocked_query,
            blocking.pid AS blocking_pid,
            blocking.usename AS blocking_user,
            blocking.query AS blocking_query,
            1 AS level
        FROM pg_catalog.pg_locks blocked
        JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked.pid = blocked_activity.pid
        JOIN pg_catalog.pg_locks blocking 
            ON blocking.locktype = blocked.locktype
            AND blocking.database IS NOT DISTINCT FROM blocked.database
            AND blocking.relation IS NOT DISTINCT FROM blocked.relation
            AND blocking.page IS NOT DISTINCT FROM blocked.page
            AND blocking.tuple IS NOT DISTINCT FROM blocked.tuple
            AND blocking.virtualxid IS NOT DISTINCT FROM blocked.virtualxid
            AND blocking.transactionid IS NOT DISTINCT FROM blocked.transactionid
            AND blocking.classid IS NOT DISTINCT FROM blocked.classid
            AND blocking.objid IS NOT DISTINCT FROM blocked.objid
            AND blocking.objsubid IS NOT DISTINCT FROM blocked.objsubid
            AND blocking.pid != blocked.pid
        JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking.pid = blocking_activity.pid
        WHERE NOT blocked.granted
        
        UNION ALL
        
        -- 递归查找阻塞链
        SELECT 
            lc.blocked_pid,
            lc.blocked_user,
            lc.blocked_query,
            blocking.pid AS blocking_pid,
            blocking_activity.usename AS blocking_user,
            blocking_activity.query AS blocking_query,
            lc.level + 1
        FROM lock_chain lc
        JOIN pg_catalog.pg_locks blocked ON lc.blocking_pid = blocked.pid
        JOIN pg_catalog.pg_locks blocking 
            ON blocking.locktype = blocked.locktype
            AND blocking.pid != blocked.pid
        JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking.pid = blocking_activity.pid
        WHERE NOT blocked.granted AND lc.level < 10
    )
    SELECT DISTINCT * FROM lock_chain
    ORDER BY level, blocked_pid;
    """

    try:
        results = execute_readonly_query(query, config=config)

        if not results:
            return safe_json_dumps({
                "has_lock_chain": False,
                "message": "未检测到锁等待链"
            })

        # 分析锁链深度
        max_level = max(row["level"] for row in results)
        root_blockers = [row for row in results if row["level"] == 1]

        return safe_json_dumps({
            "has_lock_chain": True,
            "max_chain_depth": max_level,
            "total_blocked_processes": len(set(row["blocked_pid"] for row in results)),
            "root_blocking_processes": len(set(row["blocking_pid"] for row in root_blockers)),
            "lock_chain": results,
            "recommendations": [
                f"发现{max_level}级锁等待链,建议终止根源阻塞进程",
                "检查长事务和应用逻辑",
                "考虑设置lock_timeout参数"
            ]
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def get_active_sessions(min_duration_seconds: int = 0, config: RunnableConfig = None):
    """
    获取活跃会话信息

    **何时使用此工具:**
    - 监控当前活动
    - 识别长时间运行的查询
    - 分析会话状态

    **工具能力:**
    - 显示所有活跃会话
    - 按持续时间过滤
    - 显示会话详细信息(用户/数据库/查询/状态)

    Args:
        min_duration_seconds (int, optional): 最小持续时间(秒),默认0
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含活跃会话列表
    """
    query = """
    SELECT 
        pid,
        usename as username,
        datname as database,
        application_name,
        client_addr,
        client_port,
        backend_start,
        xact_start as transaction_start,
        query_start,
        state_change,
        state,
        wait_event_type,
        wait_event,
        query,
        EXTRACT(EPOCH FROM (NOW() - query_start))::integer as query_duration_seconds,
        EXTRACT(EPOCH FROM (NOW() - xact_start))::integer as transaction_duration_seconds,
        EXTRACT(EPOCH FROM (NOW() - backend_start))::integer as connection_age_seconds
    FROM pg_stat_activity
    WHERE pid <> pg_backend_pid()
        AND state != 'idle'
        AND EXTRACT(EPOCH FROM (NOW() - COALESCE(query_start, backend_start))) >= %s
    ORDER BY query_start NULLS LAST;
    """

    try:
        results = execute_readonly_query(
            query, params=(min_duration_seconds,), config=config)

        # 格式化时间并分类
        for row in results:
            row["backend_start"] = str(row["backend_start"])
            row["transaction_start"] = str(
                row["transaction_start"]) if row["transaction_start"] else None
            row["query_start"] = str(
                row["query_start"]) if row["query_start"] else None
            row["state_change"] = str(
                row["state_change"]) if row["state_change"] else None

            # 分类会话
            duration = row["query_duration_seconds"] or 0
            if duration > 3600:
                row["duration_category"] = "very_long"
            elif duration > 300:
                row["duration_category"] = "long"
            elif duration > 60:
                row["duration_category"] = "medium"
            else:
                row["duration_category"] = "short"

        long_sessions = sum(1 for row in results if row["duration_category"] in [
                            "long", "very_long"])

        return safe_json_dumps({
            "total_active_sessions": len(results),
            "long_running_sessions": long_sessions,
            "sessions": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def analyze_query_pattern(hours: int = 24, config: RunnableConfig = None):
    """
    分析查询模式

    **何时使用此工具:**
    - 了解查询类型分布
    - 识别主要操作类型
    - 优化查询策略

    **工具能力:**
    - 统计SELECT/INSERT/UPDATE/DELETE比例
    - 识别查询热点
    - 分析查询复杂度

    **前置要求:**
    - 需要安装pg_stat_statements扩展

    Args:
        hours (int, optional): 分析时间范围(小时),默认24小时
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含查询模式分析
    """
    query = """
    SELECT 
        CASE 
            WHEN query LIKE 'SELECT%' THEN 'SELECT'
            WHEN query LIKE 'INSERT%' THEN 'INSERT'
            WHEN query LIKE 'UPDATE%' THEN 'UPDATE'
            WHEN query LIKE 'DELETE%' THEN 'DELETE'
            ELSE 'OTHER'
        END as query_type,
        COUNT(*) as query_count,
        SUM(calls) as total_calls,
        SUM(total_exec_time) as total_time,
        AVG(mean_exec_time) as avg_mean_time,
        SUM(rows) as total_rows
    FROM pg_stat_statements
    GROUP BY query_type
    ORDER BY total_calls DESC;
    """

    try:
        results = execute_readonly_query(query, config=config)

        total_calls = sum(row["total_calls"] for row in results)

        # 计算百分比
        for row in results:
            row["call_percent"] = round(
                (row["total_calls"] / total_calls) * 100, 2) if total_calls > 0 else 0
            row["total_time_formatted"] = format_duration(row["total_time"])
            row["avg_mean_time_formatted"] = format_duration(
                row["avg_mean_time"])

        return safe_json_dumps({
            "analysis_period_hours": hours,
            "total_query_calls": total_calls,
            "query_patterns": results
        })
    except Exception as e:
        error_msg = str(e)
        if "pg_stat_statements" in error_msg:
            return safe_json_dumps({
                "error": "pg_stat_statements扩展未安装或未启用"
            })
        return safe_json_dumps({"error": error_msg})
