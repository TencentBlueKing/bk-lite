"""PostgreSQL性能优化建议工具"""
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from apps.opspilot.metis.llm.tools.postgres.utils import (
    execute_readonly_query,
    safe_json_dumps,
    format_size,
)


@tool()
def check_unused_indexes(schema_name: str = "public", size_threshold_mb: int = 10, config: RunnableConfig = None):
    """
    检查未使用的索引

    **何时使用此工具:**
    - 优化磁盘空间使用
    - 减少写入开销
    - 清理冗余索引

    **工具能力:**
    - 识别从未使用的索引
    - 计算可节省的空间
    - 提供删除建议

    Args:
        schema_name (str, optional): Schema名,默认public
        size_threshold_mb (int, optional): 大小阈值(MB),只显示超过此大小的索引,默认10MB
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含未使用索引列表
    """
    query = """
    SELECT 
        schemaname,
        tablename as table_name,
        indexname as index_name,
        pg_relation_size(indexrelid) as index_size_bytes,
        idx_scan as index_scans,
        pg_size_pretty(pg_relation_size(indexrelid)) as index_size
    FROM pg_stat_user_indexes
    WHERE schemaname = %s
        AND idx_scan = 0
        AND pg_relation_size(indexrelid) > %s
        AND indexrelname NOT LIKE '%_pkey'  -- 排除主键
    ORDER BY pg_relation_size(indexrelid) DESC;
    """

    try:
        size_bytes = size_threshold_mb * 1024 * 1024
        results = execute_readonly_query(
            query, params=(schema_name, size_bytes), config=config)

        total_wasted_bytes = sum(row["index_size_bytes"] for row in results)

        return safe_json_dumps({
            "schema": schema_name,
            "unused_index_count": len(results),
            "total_wasted_space": format_size(total_wasted_bytes),
            "total_wasted_bytes": total_wasted_bytes,
            "unused_indexes": results,
            "recommendations": [
                f"考虑删除{len(results)}个未使用的索引,可节省{format_size(total_wasted_bytes)}" if results else "未发现大型未使用索引",
                "删除前确认索引不再需要,或先禁用索引观察影响"
            ]
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def recommend_vacuum_strategy(schema_name: str = "public", config: RunnableConfig = None):
    """
    推荐VACUUM策略

    **何时使用此工具:**
    - 优化VACUUM执行计划
    - 解决表膨胀问题
    - 调整autovacuum参数

    **工具能力:**
    - 识别需要VACUUM的表
    - 推荐VACUUM类型(VACUUM/VACUUM FULL)
    - 评估VACUUM优先级

    Args:
        schema_name (str, optional): Schema名,默认public
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含VACUUM建议
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
        COALESCE(last_vacuum, last_autovacuum) as last_vacuum_any,
        NOW() - COALESCE(last_vacuum, last_autovacuum) as time_since_vacuum,
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||relname)) as table_size
    FROM pg_stat_user_tables
    WHERE schemaname = %s
    ORDER BY n_dead_tup DESC;
    """

    try:
        results = execute_readonly_query(
            query, params=(schema_name,), config=config)

        recommendations = []
        for row in results:
            dead_percent = row["dead_tuple_percent"] or 0
            dead_tuples = row["dead_tuples"] or 0

            # 格式化时间
            row["last_vacuum"] = str(
                row["last_vacuum"]) if row["last_vacuum"] else "Never"
            row["last_autovacuum"] = str(
                row["last_autovacuum"]) if row["last_autovacuum"] else "Never"
            row["time_since_vacuum"] = str(
                row["time_since_vacuum"]) if row["time_since_vacuum"] else "Never"

            # 确定优先级和建议
            if dead_percent > 30 or dead_tuples > 1000000:
                row["priority"] = "critical"
                row["recommendation"] = "立即执行 VACUUM FULL"
                recommendations.append(row)
            elif dead_percent > 20 or dead_tuples > 500000:
                row["priority"] = "high"
                row["recommendation"] = "尽快执行 VACUUM"
                recommendations.append(row)
            elif dead_percent > 10 or dead_tuples > 100000:
                row["priority"] = "medium"
                row["recommendation"] = "计划执行 VACUUM"
                recommendations.append(row)
            else:
                row["priority"] = "low"
                row["recommendation"] = "正常,autovacuum会处理"

        critical_count = sum(
            1 for r in recommendations if r["priority"] == "critical")
        high_count = sum(1 for r in recommendations if r["priority"] == "high")

        return safe_json_dumps({
            "schema": schema_name,
            "total_tables": len(results),
            "critical_priority": critical_count,
            "high_priority": high_count,
            "recommendations": recommendations[:20],  # 只返回前20个
            "general_advice": [
                f"{critical_count}个表需要立即执行VACUUM FULL" if critical_count > 0 else None,
                f"{high_count}个表需要尽快执行VACUUM" if high_count > 0 else None,
                "考虑调整autovacuum_vacuum_scale_factor参数",
                "在低峰时段执行VACUUM FULL操作"
            ]
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def recommend_index_optimization(schema_name: str = "public", table: str = None, config: RunnableConfig = None):
    """
    推荐索引优化

    **何时使用此工具:**
    - 优化查询性能
    - 减少顺序扫描
    - 改进索引设计

    **工具能力:**
    - 识别顺序扫描过多的表
    - 建议创建索引
    - 识别重复和冗余索引

    Args:
        schema_name (str, optional): Schema名,默认public
        table (str, optional): 表名
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含索引优化建议
    """
    # 查找顺序扫描过多的表
    if table:
        query = """
        SELECT 
            schemaname,
            relname as table_name,
            seq_scan as sequential_scans,
            seq_tup_read as sequential_tuples_read,
            idx_scan as index_scans,
            idx_tup_fetch as index_tuples_fetched,
            n_live_tup as live_tuples,
            CASE 
                WHEN seq_scan > 0 THEN ROUND(seq_tup_read::numeric / seq_scan, 2)
                ELSE 0
            END as avg_tuples_per_seq_scan
        FROM pg_stat_user_tables
        WHERE schemaname = %s AND relname = %s;
        """
        params = (schema_name, table)
    else:
        query = """
        SELECT 
            schemaname,
            relname as table_name,
            seq_scan as sequential_scans,
            seq_tup_read as sequential_tuples_read,
            idx_scan as index_scans,
            idx_tup_fetch as index_tuples_fetched,
            n_live_tup as live_tuples,
            CASE 
                WHEN seq_scan > 0 THEN ROUND(seq_tup_read::numeric / seq_scan, 2)
                ELSE 0
            END as avg_tuples_per_seq_scan
        FROM pg_stat_user_tables
        WHERE schemaname = %s
            AND seq_scan > 100
            AND seq_tup_read > 10000
        ORDER BY seq_scan DESC
        LIMIT 20;
        """
        params = (schema_name,)

    try:
        results = execute_readonly_query(query, params=params, config=config)

        recommendations = []
        for row in results:
            total_scans = row["sequential_scans"] + (row["index_scans"] or 0)
            if total_scans > 0:
                seq_scan_ratio = (row["sequential_scans"] / total_scans) * 100
            else:
                seq_scan_ratio = 0

            row["seq_scan_ratio"] = round(seq_scan_ratio, 2)

            # 提供建议
            if seq_scan_ratio > 80 and row["avg_tuples_per_seq_scan"] > 100:
                row["recommendation"] = "考虑添加索引以减少顺序扫描"
                row["priority"] = "high"
                recommendations.append(row)
            elif seq_scan_ratio > 50:
                row["recommendation"] = "可能需要优化现有索引或添加新索引"
                row["priority"] = "medium"
                recommendations.append(row)
            else:
                row["recommendation"] = "索引使用良好"
                row["priority"] = "low"

        return safe_json_dumps({
            "schema": schema_name,
            "table": table,
            "total_tables_analyzed": len(results),
            "needs_optimization": len(recommendations),
            "tables": results,
            "general_advice": [
                "使用EXPLAIN ANALYZE分析慢查询",
                "考虑为频繁查询的WHERE条件列创建索引",
                "避免在低基数列上创建索引",
                "定期重建或REINDEX膨胀的索引"
            ]
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def check_configuration_tuning(config: RunnableConfig = None):
    """
    检查配置参数并提供调优建议

    **何时使用此工具:**
    - 优化数据库性能
    - 评估配置合理性
    - 获取配置调优建议

    **工具能力:**
    - 检查关键配置参数
    - 对比推荐值
    - 提供调优建议

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含配置检查和建议
    """
    query = """
    SELECT 
        name,
        setting,
        unit,
        boot_val as default_value,
        reset_val as current_value,
        source
    FROM pg_settings
    WHERE name IN (
        'shared_buffers',
        'effective_cache_size',
        'maintenance_work_mem',
        'work_mem',
        'max_connections',
        'max_wal_size',
        'checkpoint_completion_target',
        'random_page_cost',
        'effective_io_concurrency',
        'max_worker_processes',
        'max_parallel_workers_per_gather',
        'max_parallel_workers'
    )
    ORDER BY name;
    """

    try:
        results = execute_readonly_query(query, config=config)

        recommendations = []

        # 简单的建议逻辑(实际应根据系统资源动态调整)
        config_advice = {
            "shared_buffers": "建议设置为系统内存的25%",
            "effective_cache_size": "建议设置为系统内存的50-75%",
            "maintenance_work_mem": "建议设置为256MB-2GB",
            "work_mem": "建议根据并发查询数调整,通常4-16MB",
            "max_wal_size": "建议设置为2-4GB以减少检查点频率",
            "checkpoint_completion_target": "建议设置为0.9",
            "random_page_cost": "SSD建议设置为1.1,HDD保持4.0",
            "effective_io_concurrency": "SSD建议设置为200",
        }

        for row in results:
            if row["name"] in config_advice:
                row["advice"] = config_advice[row["name"]]
                recommendations.append(row)

        return safe_json_dumps({
            "total_parameters": len(results),
            "parameters": results,
            "recommendations": recommendations,
            "general_advice": [
                "配置调整后需要重启数据库才能生效(部分参数除外)",
                "建议在测试环境验证配置变更",
                "使用pgtune等工具生成推荐配置",
                "监控配置变更后的性能指标"
            ]
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})
