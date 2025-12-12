"""PostgreSQL配置分析工具"""
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from apps.opspilot.metis.llm.tools.postgres.utils import (
    execute_readonly_query,
    safe_json_dumps,
    calculate_percentage,
)


@tool()
def analyze_cache_hit_ratio(config: RunnableConfig = None):
    """
    分析缓存命中率

    **何时使用此工具:**
    - 评估shared_buffers配置
    - 优化缓存性能
    - 排查I/O性能问题

    **工具能力:**
    - 计算整体缓存命中率
    - 按数据库分组统计
    - 提供优化建议

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含缓存命中率分析
    """
    query = """
    SELECT 
        datname as database,
        blks_hit as blocks_hit,
        blks_read as blocks_read,
        blks_hit + blks_read as total_blocks,
        ROUND(100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0), 2) as cache_hit_ratio
    FROM pg_stat_database
    WHERE datname NOT IN ('template0', 'template1')
    ORDER BY blks_hit + blks_read DESC;
    """

    try:
        results = execute_readonly_query(query, config=config)

        # 计算总体命中率
        total_hit = sum(row["blocks_hit"] for row in results)
        total_read = sum(row["blocks_read"] for row in results)
        overall_ratio = calculate_percentage(total_hit, total_hit + total_read)

        # 评估缓存性能
        if overall_ratio >= 99:
            performance = "excellent"
            recommendation = "缓存命中率优秀,无需调整"
        elif overall_ratio >= 95:
            performance = "good"
            recommendation = "缓存命中率良好,可以考虑小幅增加shared_buffers"
        elif overall_ratio >= 90:
            performance = "fair"
            recommendation = "建议增加shared_buffers以提高缓存命中率"
        else:
            performance = "poor"
            recommendation = "缓存命中率偏低,强烈建议增加shared_buffers并检查查询模式"

        return safe_json_dumps({
            "overall_cache_hit_ratio": overall_ratio,
            "performance": performance,
            "recommendation": recommendation,
            "by_database": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def analyze_connection_pool_usage(config: RunnableConfig = None):
    """
    分析连接池使用情况

    **何时使用此工具:**
    - 优化连接池配置
    - 排查连接泄漏
    - 分析连接使用模式

    **工具能力:**
    - 统计活跃/空闲连接分布
    - 识别长时间空闲连接
    - 按应用和用户分组

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含连接池分析
    """
    # 连接状态统计
    state_query = """
    SELECT 
        state,
        COUNT(*) as connection_count,
        ROUND(AVG(EXTRACT(EPOCH FROM (NOW() - state_change)))::numeric, 2) as avg_duration_seconds
    FROM pg_stat_activity
    WHERE pid <> pg_backend_pid()
    GROUP BY state
    ORDER BY connection_count DESC;
    """

    # 按应用统计
    app_query = """
    SELECT 
        application_name,
        usename as username,
        COUNT(*) as connection_count,
        COUNT(*) FILTER (WHERE state = 'active') as active_count,
        COUNT(*) FILTER (WHERE state = 'idle') as idle_count
    FROM pg_stat_activity
    WHERE pid <> pg_backend_pid()
    GROUP BY application_name, usename
    ORDER BY connection_count DESC
    LIMIT 20;
    """

    # 长时间空闲连接
    idle_query = """
    SELECT 
        pid,
        usename,
        application_name,
        client_addr,
        state,
        NOW() - state_change as idle_duration,
        query
    FROM pg_stat_activity
    WHERE state = 'idle'
        AND NOW() - state_change > interval '10 minutes'
    ORDER BY state_change
    LIMIT 10;
    """

    try:
        by_state = execute_readonly_query(state_query, config=config)
        by_app = execute_readonly_query(app_query, config=config)
        long_idle = execute_readonly_query(idle_query, config=config)

        # 格式化空闲时长
        for row in long_idle:
            row["idle_duration"] = str(row["idle_duration"])

        total_connections = sum(row["connection_count"] for row in by_state)
        idle_connections = sum(row["connection_count"]
                               for row in by_state if row["state"] == "idle")
        idle_percent = calculate_percentage(
            idle_connections, total_connections)

        return safe_json_dumps({
            "total_connections": total_connections,
            "idle_connections": idle_connections,
            "idle_percent": idle_percent,
            "by_state": by_state,
            "by_application": by_app,
            "long_idle_connections": long_idle,
            "recommendations": [
                "考虑减小连接池大小" if idle_percent > 50 else None,
                f"发现{len(long_idle)}个长时间空闲连接,检查应用连接管理" if long_idle else None,
            ]
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def analyze_table_statistics(schema_name: str = "public", config: RunnableConfig = None):
    """
    分析表统计信息新鲜度

    **何时使用此工具:**
    - 检查ANALYZE是否及时执行
    - 优化查询计划准确性
    - 排查统计信息过时问题

    **工具能力:**
    - 检查最后ANALYZE时间
    - 识别统计信息过时的表
    - 评估数据变更程度

    Args:
        schema_name (str, optional): Schema名,默认public
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含统计信息分析
    """
    query = """
    SELECT 
        schemaname,
        relname as table_name,
        last_analyze,
        last_autoanalyze,
        COALESCE(last_analyze, last_autoanalyze) as last_analyze_any,
        NOW() - COALESCE(last_analyze, last_autoanalyze) as time_since_analyze,
        n_mod_since_analyze as modifications_since_analyze,
        n_live_tup as live_tuples,
        CASE 
            WHEN n_live_tup > 0 THEN ROUND(100.0 * n_mod_since_analyze / n_live_tup, 2)
            ELSE 0
        END as modification_percent
    FROM pg_stat_user_tables
    WHERE schemaname = %s
    ORDER BY n_mod_since_analyze DESC;
    """

    try:
        results = execute_readonly_query(
            query, params=(schema_name,), config=config)

        stale_stats = []
        for row in results:
            row["last_analyze"] = str(
                row["last_analyze"]) if row["last_analyze"] else "Never"
            row["last_autoanalyze"] = str(
                row["last_autoanalyze"]) if row["last_autoanalyze"] else "Never"
            row["time_since_analyze"] = str(
                row["time_since_analyze"]) if row["time_since_analyze"] else "Never"

            # 判断统计信息是否过时
            mod_percent = row["modification_percent"] or 0
            if mod_percent > 20 or row["last_analyze_any"] is None:
                row["is_stale"] = True
                stale_stats.append(row["table_name"])
            else:
                row["is_stale"] = False

        return safe_json_dumps({
            "schema": schema_name,
            "total_tables": len(results),
            "stale_statistics_count": len(stale_stats),
            "tables": results,
            "recommendations": [
                f"对{len(stale_stats)}个表执行ANALYZE更新统计信息" if stale_stats else None,
                "启用autovacuum自动更新统计信息",
            ]
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def analyze_checkpoint_activity(config: RunnableConfig = None):
    """
    分析检查点活动

    **何时使用此工具:**
    - 评估检查点配置
    - 优化WAL写入性能
    - 排查I/O峰值问题

    **工具能力:**
    - 统计检查点次数和类型
    - 显示检查点写入量
    - 分析检查点触发原因

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含检查点统计
    """
    query = """
    SELECT 
        checkpoints_timed,
        checkpoints_req as checkpoints_requested,
        checkpoint_write_time,
        checkpoint_sync_time,
        buffers_checkpoint,
        buffers_clean,
        buffers_backend,
        buffers_backend_fsync,
        buffers_alloc
    FROM pg_stat_bgwriter;
    """

    try:
        result = execute_readonly_query(query, config=config)[0]

        total_checkpoints = result["checkpoints_timed"] + \
            result["checkpoints_requested"]
        timed_percent = calculate_percentage(
            result["checkpoints_timed"], total_checkpoints)

        # 评估检查点配置
        if timed_percent >= 90:
            status = "good"
            recommendation = "检查点主要由定时触发,配置合理"
        elif timed_percent >= 70:
            status = "fair"
            recommendation = "建议适当增加max_wal_size以减少请求触发的检查点"
        else:
            status = "poor"
            recommendation = "检查点频繁由请求触发,强烈建议增加max_wal_size"

        result["total_checkpoints"] = total_checkpoints
        result["timed_percent"] = timed_percent
        result["status"] = status
        result["recommendation"] = recommendation

        return safe_json_dumps(result)
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def analyze_transaction_patterns(limit: int = 20, config: RunnableConfig = None):
    """
    分析事务模式

    **何时使用此工具:**
    - 了解事务提交/回滚比例
    - 识别异常事务模式
    - 优化事务处理

    **工具能力:**
    - 统计提交和回滚事务数
    - 计算回滚率
    - 识别高回滚率数据库

    Args:
        limit (int, optional): 返回结果数量,默认20
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含事务模式分析
    """
    query = """
    SELECT 
        datname as database,
        xact_commit as commits,
        xact_rollback as rollbacks,
        xact_commit + xact_rollback as total_transactions,
        ROUND(100.0 * xact_rollback / NULLIF(xact_commit + xact_rollback, 0), 2) as rollback_percent,
        conflicts,
        deadlocks
    FROM pg_stat_database
    WHERE datname NOT IN ('template0', 'template1')
    ORDER BY xact_commit + xact_rollback DESC
    LIMIT %s;
    """

    try:
        results = execute_readonly_query(query, params=(limit,), config=config)

        # 标记异常
        for row in results:
            rollback_percent = row["rollback_percent"] or 0
            if rollback_percent > 10:
                row["status"] = "high_rollback"
            elif rollback_percent > 5:
                row["status"] = "moderate_rollback"
            else:
                row["status"] = "normal"

        return safe_json_dumps({
            "total_databases": len(results),
            "databases": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})
