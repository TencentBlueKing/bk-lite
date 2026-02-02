"""PostgreSQL高级查询分析工具"""
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from apps.opspilot.metis.llm.tools.postgres.utils import (
    execute_readonly_query,
    safe_json_dumps,
    format_size,
    calculate_percentage,
)


@tool()
def query_table_stats(schema_name: str = "public", table_filter: str = None, config: RunnableConfig = None):
    """
    查询表统计信息

    **何时使用此工具:**
    - 分析表的访问模式
    - 了解表的读写比例
    - 优化查询性能

    **工具能力:**
    - 显示表的顺序扫描和索引扫描次数
    - 显示表的插入、更新、删除统计
    - 计算热表(高频访问)

    Args:
        schema_name (str, optional): Schema名,默认public
        table_filter (str, optional): 表名过滤(支持LIKE模式)
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含表统计信息
    """
    if table_filter:
        query = """
        SELECT 
            schemaname,
            relname as table_name,
            seq_scan as sequential_scans,
            seq_tup_read as sequential_tuples_read,
            idx_scan as index_scans,
            idx_tup_fetch as index_tuples_fetched,
            n_tup_ins as tuples_inserted,
            n_tup_upd as tuples_updated,
            n_tup_del as tuples_deleted,
            n_tup_hot_upd as hot_updates,
            n_live_tup as live_tuples,
            n_dead_tup as dead_tuples
        FROM pg_stat_user_tables
        WHERE schemaname = %s AND relname LIKE %s
        ORDER BY seq_scan + COALESCE(idx_scan, 0) DESC;
        """
        params = (schema_name, table_filter)
    else:
        query = """
        SELECT 
            schemaname,
            relname as table_name,
            seq_scan as sequential_scans,
            seq_tup_read as sequential_tuples_read,
            idx_scan as index_scans,
            idx_tup_fetch as index_tuples_fetched,
            n_tup_ins as tuples_inserted,
            n_tup_upd as tuples_updated,
            n_tup_del as tuples_deleted,
            n_tup_hot_upd as hot_updates,
            n_live_tup as live_tuples,
            n_dead_tup as dead_tuples
        FROM pg_stat_user_tables
        WHERE schemaname = %s
        ORDER BY seq_scan + COALESCE(idx_scan, 0) DESC;
        """
        params = (schema_name,)

    try:
        results = execute_readonly_query(query, params=params, config=config)

        # 计算额外指标
        for row in results:
            total_scans = row["sequential_scans"] + (row["index_scans"] or 0)
            if total_scans > 0:
                row["index_scan_ratio"] = calculate_percentage(
                    row["index_scans"] or 0, total_scans)
            else:
                row["index_scan_ratio"] = 0

            row["is_hot_table"] = total_scans > 10000

        return safe_json_dumps({
            "schema": schema_name,
            "total_tables": len(results),
            "tables": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def query_index_usage(schema_name: str = "public", table: str = None, config: RunnableConfig = None):
    """
    查询索引使用统计

    **何时使用此工具:**
    - 识别未使用的索引
    - 分析索引效率
    - 优化索引设计

    **工具能力:**
    - 显示索引扫描次数和读取行数
    - 计算索引使用率
    - 识别冗余索引

    Args:
        schema_name (str, optional): Schema名,默认public
        table (str, optional): 表名
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含索引使用统计
    """
    if table:
        query = """
        SELECT 
            schemaname,
            tablename as table_name,
            indexname as index_name,
            idx_scan as index_scans,
            idx_tup_read as tuples_read,
            idx_tup_fetch as tuples_fetched,
            pg_relation_size(indexrelid) as index_size_bytes
        FROM pg_stat_user_indexes
        WHERE schemaname = %s AND tablename = %s
        ORDER BY idx_scan ASC;
        """
        params = (schema_name, table)
    else:
        query = """
        SELECT 
            schemaname,
            tablename as table_name,
            indexname as index_name,
            idx_scan as index_scans,
            idx_tup_read as tuples_read,
            idx_tup_fetch as tuples_fetched,
            pg_relation_size(indexrelid) as index_size_bytes
        FROM pg_stat_user_indexes
        WHERE schemaname = %s
        ORDER BY idx_scan ASC;
        """
        params = (schema_name,)

    try:
        results = execute_readonly_query(query, params=params, config=config)

        # 格式化并添加分析
        for row in results:
            row["index_size"] = format_size(row["index_size_bytes"])
            row["is_unused"] = row["index_scans"] == 0
            row["efficiency"] = calculate_percentage(
                row["tuples_fetched"] or 0,
                row["tuples_read"] or 1
            )

        unused_count = sum(1 for row in results if row["is_unused"])

        return safe_json_dumps({
            "schema": schema_name,
            "table": table,
            "total_indexes": len(results),
            "unused_indexes": unused_count,
            "indexes": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def query_bloat_analysis(schema_name: str = "public", config: RunnableConfig = None):
    """
    分析表和索引膨胀

    **何时使用此工具:**
    - 检测表膨胀问题
    - 评估VACUUM效果
    - 规划表维护

    **工具能力:**
    - 估算表膨胀率
    - 识别严重膨胀的表
    - 计算可回收空间

    Args:
        schema_name (str, optional): Schema名,默认public
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含膨胀分析结果
    """
    query = """
    SELECT 
        schemaname,
        tablename as table_name,
        pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size,
        n_live_tup as live_tuples,
        n_dead_tup as dead_tuples,
        ROUND(100.0 * n_dead_tup / NULLIF(n_live_tup + n_dead_tup, 0), 2) as dead_tuple_percent,
        last_vacuum,
        last_autovacuum
    FROM pg_stat_user_tables
    WHERE schemaname = %s
        AND n_dead_tup > 0
    ORDER BY n_dead_tup DESC
    LIMIT 50;
    """

    try:
        results = execute_readonly_query(
            query, params=(schema_name,), config=config)

        # 分类膨胀程度
        for row in results:
            dead_percent = row["dead_tuple_percent"] or 0
            if dead_percent > 20:
                row["bloat_level"] = "critical"
            elif dead_percent > 10:
                row["bloat_level"] = "warning"
            else:
                row["bloat_level"] = "normal"

            row["last_vacuum"] = str(
                row["last_vacuum"]) if row["last_vacuum"] else "Never"
            row["last_autovacuum"] = str(
                row["last_autovacuum"]) if row["last_autovacuum"] else "Never"

        critical_count = sum(
            1 for row in results if row["bloat_level"] == "critical")

        return safe_json_dumps({
            "schema": schema_name,
            "total_tables_analyzed": len(results),
            "critical_bloat_count": critical_count,
            "tables": results,
            "recommendations": [
                f"对{critical_count}个严重膨胀的表执行VACUUM FULL" if critical_count > 0 else None,
                "定期执行VACUUM维护",
                "检查autovacuum配置"
            ]
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def query_table_io_stats(schema_name: str = "public", limit: int = 20, config: RunnableConfig = None):
    """
    查询表I/O统计

    **何时使用此工具:**
    - 分析表的I/O性能
    - 识别I/O密集型表
    - 优化缓存配置

    **工具能力:**
    - 显示表的磁盘块读取和缓存命中
    - 计算缓存命中率
    - 识别I/O热点

    Args:
        schema_name (str, optional): Schema名,默认public
        limit (int, optional): 返回结果数量,默认20
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含I/O统计信息
    """
    query = """
    SELECT 
        schemaname,
        relname as table_name,
        heap_blks_read as heap_blocks_read,
        heap_blks_hit as heap_blocks_hit,
        ROUND(100.0 * heap_blks_hit / NULLIF(heap_blks_hit + heap_blks_read, 0), 2) as cache_hit_ratio,
        idx_blks_read as index_blocks_read,
        idx_blks_hit as index_blocks_hit,
        ROUND(100.0 * idx_blks_hit / NULLIF(idx_blks_hit + idx_blks_read, 0), 2) as index_cache_hit_ratio,
        toast_blks_read as toast_blocks_read,
        toast_blks_hit as toast_blocks_hit
    FROM pg_statio_user_tables
    WHERE schemaname = %s
    ORDER BY heap_blks_read + idx_blks_read DESC
    LIMIT %s;
    """

    try:
        results = execute_readonly_query(
            query, params=(schema_name, limit), config=config)

        # 分析I/O模式
        for row in results:
            total_io = row["heap_blocks_read"] + row["index_blocks_read"]
            row["total_disk_reads"] = total_io
            row["is_io_intensive"] = total_io > 100000

            # 标记低缓存命中率
            cache_ratio = row["cache_hit_ratio"] or 0
            row["has_low_cache_hit"] = cache_ratio < 90

        return safe_json_dumps({
            "schema": schema_name,
            "total_tables": len(results),
            "tables": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def search_objects(database: str = None, object_type: str = "table", pattern: str = None, config: RunnableConfig = None):
    """
    搜索数据库对象

    **何时使用此工具:**
    - 查找特定名称的表/视图/函数
    - 模糊搜索数据库对象
    - 了解对象类型分布

    **工具能力:**
    - 支持模糊搜索(LIKE模式)
    - 搜索多种对象类型(表/视图/函数/序列)
    - 显示对象元数据

    Args:
        database (str, optional): 数据库名
        object_type (str, optional): 对象类型(table/view/function/sequence),默认table
        pattern (str, optional): 搜索模式(支持%通配符)
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含搜索结果
    """
    if object_type == "table":
        if pattern:
            query = """
            SELECT 
                schemaname,
                tablename as object_name,
                'table' as object_type,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
            FROM pg_tables
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                AND tablename LIKE %s
            ORDER BY tablename;
            """
            params = (pattern,)
        else:
            query = """
            SELECT 
                schemaname,
                tablename as object_name,
                'table' as object_type,
                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
            FROM pg_tables
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY tablename;
            """
            params = None

    elif object_type == "view":
        if pattern:
            query = """
            SELECT 
                schemaname,
                viewname as object_name,
                'view' as object_type
            FROM pg_views
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                AND viewname LIKE %s
            ORDER BY viewname;
            """
            params = (pattern,)
        else:
            query = """
            SELECT 
                schemaname,
                viewname as object_name,
                'view' as object_type
            FROM pg_views
            WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
            ORDER BY viewname;
            """
            params = None

    else:
        return safe_json_dumps({"error": f"不支持的对象类型: {object_type}"})

    try:
        results = execute_readonly_query(query, params=params, config=config)

        return safe_json_dumps({
            "object_type": object_type,
            "pattern": pattern,
            "total_objects": len(results),
            "objects": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})
