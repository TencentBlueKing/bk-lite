"""PostgreSQL故障诊断工具"""
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from apps.opspilot.metis.llm.tools.postgres.utils import (
    execute_readonly_query,
    safe_json_dumps,
    format_duration,
)


@tool()
def diagnose_slow_queries(threshold_ms: int = 1000, limit: int = 20, config: RunnableConfig = None):
    """
    诊断慢查询

    **何时使用此工具:**
    - 用户反馈"系统慢"、"查询慢"
    - 性能分析和优化
    - 定期巡检慢查询

    **工具能力:**
    - 基于pg_stat_statements识别慢查询
    - 显示查询的平均/最大执行时间
    - 显示调用次数、总耗时
    - 提供查询文本和统计信息

    **前置要求:**
    - 需要安装pg_stat_statements扩展

    Args:
        threshold_ms (int, optional): 慢查询阈值(毫秒),默认1000ms
        limit (int, optional): 返回结果数量,默认20
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含慢查询列表,每个查询包含:
        - query: 查询文本
        - calls: 调用次数
        - total_time: 总耗时(ms)
        - mean_time: 平均耗时(ms)
        - max_time: 最大耗时(ms)
        - rows: 平均返回行数
    """
    query = """
    SELECT 
        substring(query, 1, 200) as query,
        calls,
        total_exec_time as total_time,
        mean_exec_time as mean_time,
        max_exec_time as max_time,
        stddev_exec_time as stddev_time,
        rows as total_rows,
        ROUND(rows::numeric / calls, 2) as rows_per_call
    FROM pg_stat_statements
    WHERE mean_exec_time > %s
    ORDER BY mean_exec_time DESC
    LIMIT %s;
    """

    try:
        results = execute_readonly_query(
            query, params=(threshold_ms, limit), config=config)

        # 格式化时间
        for row in results:
            row["total_time_formatted"] = format_duration(row["total_time"])
            row["mean_time_formatted"] = format_duration(row["mean_time"])
            row["max_time_formatted"] = format_duration(row["max_time"])

        return safe_json_dumps({
            "threshold_ms": threshold_ms,
            "total_slow_queries": len(results),
            "slow_queries": results
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
        blocked_locks.pid AS blocked_pid,
        blocked_activity.usename AS blocked_user,
        blocking_locks.pid AS blocking_pid,
        blocking_activity.usename AS blocking_user,
        blocked_activity.query AS blocked_query,
        blocking_activity.query AS blocking_query,
        blocked_activity.state AS blocked_state,
        blocking_activity.state AS blocking_state,
        blocked_activity.wait_event_type AS blocked_wait_event,
        NOW() - blocked_activity.query_start AS blocked_duration
    FROM pg_catalog.pg_locks blocked_locks
    JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
    JOIN pg_catalog.pg_locks blocking_locks 
        ON blocking_locks.locktype = blocked_locks.locktype
        AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
        AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
        AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
        AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
        AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
        AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
        AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
        AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
        AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
        AND blocking_locks.pid != blocked_locks.pid
    JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
    WHERE NOT blocked_locks.granted;
    """

    try:
        results = execute_readonly_query(query, config=config)

        # 格式化持续时间
        for row in results:
            row["blocked_duration"] = str(row["blocked_duration"])

        return safe_json_dumps({
            "total_blocked_queries": len(results),
            "lock_conflicts": results,
            "has_conflicts": len(results) > 0
        })
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
    max_conn_query = "SELECT setting::int as max_connections FROM pg_settings WHERE name = 'max_connections';"

    # 当前连接统计
    connections_query = """
    SELECT 
        datname as database,
        usename as username,
        state,
        COUNT(*) as connection_count,
        COUNT(*) FILTER (WHERE state = 'idle') as idle_count,
        COUNT(*) FILTER (WHERE state = 'active') as active_count,
        COUNT(*) FILTER (WHERE state = 'idle in transaction') as idle_in_transaction_count
    FROM pg_stat_activity
    WHERE pid <> pg_backend_pid()
    GROUP BY datname, usename, state
    ORDER BY connection_count DESC;
    """

    # 长时间运行的查询
    long_running_query = """
    SELECT 
        pid,
        usename,
        datname,
        state,
        query,
        NOW() - query_start AS duration
    FROM pg_stat_activity
    WHERE state != 'idle' 
        AND query_start IS NOT NULL
        AND NOW() - query_start > interval '5 minutes'
    ORDER BY duration DESC
    LIMIT 10;
    """

    try:
        max_conn = execute_readonly_query(max_conn_query, config=config)
        connections = execute_readonly_query(connections_query, config=config)
        long_running = execute_readonly_query(
            long_running_query, config=config)

        # 计算总连接数
        total_connections = sum(row["connection_count"] for row in connections)
        max_connections = max_conn[0]["max_connections"]
        usage_percent = round((total_connections / max_connections) * 100, 2)

        # 格式化长时间运行的查询
        for row in long_running:
            row["duration"] = str(row["duration"])

        return safe_json_dumps({
            "max_connections": max_connections,
            "current_connections": total_connections,
            "usage_percent": usage_percent,
            "is_near_limit": usage_percent > 80,
            "connections_by_state": connections,
            "long_running_queries": long_running
        })
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
    - 检查连接数、死锁、长事务
    - 检查复制延迟(如果有)
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
        (SELECT setting::int FROM pg_settings WHERE name = 'max_connections') as max_connections,
        (SELECT count(*) FROM pg_stat_activity) as current_connections,
        (SELECT count(*) FROM pg_stat_activity WHERE state = 'active') as active_queries,
        (SELECT count(*) FROM pg_stat_activity WHERE state = 'idle in transaction') as idle_in_transaction,
        (SELECT count(*) FROM pg_stat_activity WHERE NOW() - query_start > interval '1 hour' AND state != 'idle') as long_running_queries,
        (SELECT sum(numbackends) FROM pg_stat_database) as total_backends;
    """

    # 死锁统计
    deadlocks_query = """
    SELECT 
        datname as database,
        deadlocks
    FROM pg_stat_database
    WHERE deadlocks > 0
    ORDER BY deadlocks DESC;
    """

    # 事务年龄(检测未提交事务)
    transaction_age_query = """
    SELECT 
        pid,
        usename,
        datname,
        state,
        NOW() - xact_start AS transaction_age,
        query
    FROM pg_stat_activity
    WHERE xact_start IS NOT NULL
        AND state != 'idle'
    ORDER BY xact_start
    LIMIT 5;
    """

    try:
        stats = execute_readonly_query(stats_query, config=config)[0]
        deadlocks = execute_readonly_query(deadlocks_query, config=config)
        old_transactions = execute_readonly_query(
            transaction_age_query, config=config)

        # 格式化事务年龄
        for row in old_transactions:
            row["transaction_age"] = str(row["transaction_age"])

        # 计算健康评分
        issues = []
        health_score = 100

        # 连接数检查
        conn_usage = (stats["current_connections"] /
                      stats["max_connections"]) * 100
        if conn_usage > 90:
            issues.append("连接数超过90%")
            health_score -= 20
        elif conn_usage > 80:
            issues.append("连接数超过80%")
            health_score -= 10

        # 空闲事务检查
        if stats["idle_in_transaction"] > 10:
            issues.append(f"存在{stats['idle_in_transaction']}个空闲事务")
            health_score -= 15

        # 长时间运行查询检查
        if stats["long_running_queries"] > 0:
            issues.append(f"存在{stats['long_running_queries']}个长时间运行的查询")
            health_score -= 15

        # 死锁检查
        if deadlocks:
            issues.append(f"检测到{len(deadlocks)}个数据库有死锁记录")
            health_score -= 10

        # 确定健康状态
        if health_score >= 90:
            health_status = "healthy"
        elif health_score >= 70:
            health_status = "warning"
        else:
            health_status = "critical"

        return safe_json_dumps({
            "health_status": health_status,
            "health_score": health_score,
            "statistics": stats,
            "issues": issues,
            "deadlocks": deadlocks,
            "old_transactions": old_transactions,
            "recommendations": [
                "定期监控连接数使用情况" if conn_usage > 70 else None,
                "排查并关闭空闲事务" if stats["idle_in_transaction"] > 5 else None,
                "分析长时间运行的查询" if stats["long_running_queries"] > 0 else None,
            ]
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def check_replication_lag(config: RunnableConfig = None):
    """
    检查主从复制延迟

    **何时使用此工具:**
    - 监控复制延迟
    - 排查数据不一致问题
    - 检查从库健康状态

    **工具能力:**
    - 检测复制延迟时间
    - 显示WAL发送和接收状态
    - 识别复制槽状态

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含复制状态信息
    """
    # 复制状态查询(主库视角)
    replication_query = """
    SELECT 
        client_addr,
        client_hostname,
        state,
        sync_state,
        write_lag,
        flush_lag,
        replay_lag,
        pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn) as sent_lag_bytes,
        pg_wal_lsn_diff(pg_current_wal_lsn(), write_lsn) as write_lag_bytes,
        pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn) as flush_lag_bytes,
        pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) as replay_lag_bytes
    FROM pg_stat_replication;
    """

    try:
        results = execute_readonly_query(replication_query, config=config)

        if not results:
            return safe_json_dumps({
                "has_replication": False,
                "message": "未检测到复制配置或当前为从库"
            })

        # 格式化延迟时间
        for row in results:
            row["write_lag"] = str(
                row["write_lag"]) if row["write_lag"] else "0"
            row["flush_lag"] = str(
                row["flush_lag"]) if row["flush_lag"] else "0"
            row["replay_lag"] = str(
                row["replay_lag"]) if row["replay_lag"] else "0"

        return safe_json_dumps({
            "has_replication": True,
            "replica_count": len(results),
            "replicas": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def diagnose_autovacuum_issues(config: RunnableConfig = None):
    """
    诊断AUTOVACUUM问题

    **何时使用此工具:**
    - 表膨胀问题
    - 检查VACUUM是否正常运行
    - 优化VACUUM配置

    **工具能力:**
    - 检查表的最后VACUUM时间
    - 识别长时间未VACUUM的表
    - 显示死元组数量
    - 检查AUTOVACUUM是否被阻塞

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含VACUUM诊断信息
    """
    query = """
    SELECT 
        schemaname,
        relname as table_name,
        n_live_tup as live_tuples,
        n_dead_tup as dead_tuples,
        ROUND(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 2) as dead_tuple_percent,
        last_vacuum,
        last_autovacuum,
        last_analyze,
        last_autoanalyze,
        COALESCE(last_vacuum, last_autovacuum) as last_vacuum_any,
        NOW() - COALESCE(last_vacuum, last_autovacuum) as time_since_vacuum
    FROM pg_stat_user_tables
    WHERE n_dead_tup > 1000 OR COALESCE(last_vacuum, last_autovacuum) < NOW() - interval '7 days'
    ORDER BY n_dead_tup DESC
    LIMIT 20;
    """

    try:
        results = execute_readonly_query(query, config=config)

        # 格式化时间
        for row in results:
            row["last_vacuum"] = str(
                row["last_vacuum"]) if row["last_vacuum"] else "Never"
            row["last_autovacuum"] = str(
                row["last_autovacuum"]) if row["last_autovacuum"] else "Never"
            row["last_analyze"] = str(
                row["last_analyze"]) if row["last_analyze"] else "Never"
            row["last_autoanalyze"] = str(
                row["last_autoanalyze"]) if row["last_autoanalyze"] else "Never"
            row["time_since_vacuum"] = str(
                row["time_since_vacuum"]) if row["time_since_vacuum"] else "Never"

        return safe_json_dumps({
            "tables_need_vacuum": len(results),
            "tables": results,
            "recommendations": [
                "对死元组比例>10%的表手动执行VACUUM",
                "检查autovacuum配置参数",
                "确保autovacuum未被长事务阻塞"
            ]
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def get_failed_transactions(limit: int = 20, config: RunnableConfig = None):
    """
    获取失败和回滚的事务信息

    **何时使用此工具:**
    - 排查应用错误
    - 分析事务失败原因
    - 监控数据库错误率

    Args:
        limit (int, optional): 返回结果数量,默认20
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含失败事务统计
    """
    query = """
    SELECT 
        datname as database,
        xact_commit as committed_transactions,
        xact_rollback as rolled_back_transactions,
        ROUND(100.0 * xact_rollback / NULLIF(xact_commit + xact_rollback, 0), 2) as rollback_percent,
        blks_read as blocks_read,
        blks_hit as blocks_hit,
        ROUND(100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0), 2) as cache_hit_ratio,
        deadlocks,
        conflicts
    FROM pg_stat_database
    WHERE datname NOT IN ('template0', 'template1')
    ORDER BY xact_rollback DESC
    LIMIT %s;
    """

    try:
        results = execute_readonly_query(query, params=(limit,), config=config)

        return safe_json_dumps({
            "databases": results,
            "total_databases": len(results)
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})
