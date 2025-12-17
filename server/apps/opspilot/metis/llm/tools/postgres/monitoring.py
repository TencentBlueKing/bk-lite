"""PostgreSQL监控指标采集工具"""
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from apps.opspilot.metis.llm.tools.postgres.utils import (
    execute_readonly_query,
    safe_json_dumps,
    format_size,
    calculate_percentage,
)


@tool()
def get_database_metrics(config: RunnableConfig = None):
    """
    获取数据库级别监控指标

    **何时使用此工具:**
    - 收集数据库性能指标
    - 监控数据库健康状态
    - 生成监控报告

    **工具能力:**
    - 采集连接数、事务数、缓存命中率等核心指标
    - 显示各数据库的资源使用情况
    - 提供趋势分析数据

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含数据库指标
    """
    query = """
    SELECT 
        datname as database,
        numbackends as active_connections,
        xact_commit as transactions_committed,
        xact_rollback as transactions_rolled_back,
        blks_read as disk_blocks_read,
        blks_hit as buffer_blocks_hit,
        ROUND(100.0 * blks_hit / NULLIF(blks_hit + blks_read, 0), 2) as cache_hit_ratio,
        tup_returned as tuples_returned,
        tup_fetched as tuples_fetched,
        tup_inserted as tuples_inserted,
        tup_updated as tuples_updated,
        tup_deleted as tuples_deleted,
        conflicts,
        temp_files as temporary_files,
        temp_bytes as temporary_bytes,
        deadlocks,
        blk_read_time as block_read_time_ms,
        blk_write_time as block_write_time_ms,
        stats_reset
    FROM pg_stat_database
    WHERE datname NOT IN ('template0', 'template1')
    ORDER BY numbackends DESC;
    """

    try:
        results = execute_readonly_query(query, config=config)

        # 格式化和增强数据
        for row in results:
            row["temporary_size"] = format_size(row["temporary_bytes"])
            row["stats_reset"] = str(
                row["stats_reset"]) if row["stats_reset"] else "Never"

            # 计算事务回滚率
            total_xact = row["transactions_committed"] + \
                row["transactions_rolled_back"]
            row["rollback_ratio"] = calculate_percentage(
                row["transactions_rolled_back"], total_xact)

        return safe_json_dumps({
            "total_databases": len(results),
            "databases": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def get_table_metrics(schema_name: str = "public", table: str = None, config: RunnableConfig = None):
    """
    获取表级别监控指标

    **何时使用此工具:**
    - 监控表的访问模式
    - 分析表性能
    - 识别热表

    **工具能力:**
    - 采集表的读写统计
    - 显示索引使用情况
    - 监控表膨胀和维护状态

    Args:
        schema_name (str, optional): Schema名,默认public
        table (str, optional): 表名,不填则返回所有表
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含表指标
    """
    if table:
        query = """
        SELECT 
            schemaname,
            relname as table_name,
            seq_scan,
            seq_tup_read,
            idx_scan,
            idx_tup_fetch,
            n_tup_ins as inserts,
            n_tup_upd as updates,
            n_tup_del as deletes,
            n_tup_hot_upd as hot_updates,
            n_live_tup as live_tuples,
            n_dead_tup as dead_tuples,
            last_vacuum,
            last_autovacuum,
            last_analyze,
            last_autoanalyze,
            vacuum_count,
            autovacuum_count,
            analyze_count,
            autoanalyze_count
        FROM pg_stat_user_tables
        WHERE schemaname = %s AND relname = %s;
        """
        params = (schema_name, table)
    else:
        query = """
        SELECT 
            schemaname,
            relname as table_name,
            seq_scan,
            seq_tup_read,
            idx_scan,
            idx_tup_fetch,
            n_tup_ins as inserts,
            n_tup_upd as updates,
            n_tup_del as deletes,
            n_tup_hot_upd as hot_updates,
            n_live_tup as live_tuples,
            n_dead_tup as dead_tuples,
            last_vacuum,
            last_autovacuum,
            last_analyze,
            last_autoanalyze
        FROM pg_stat_user_tables
        WHERE schemaname = %s
        ORDER BY seq_scan + COALESCE(idx_scan, 0) DESC
        LIMIT 50;
        """
        params = (schema_name,)

    try:
        results = execute_readonly_query(query, params=params, config=config)

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

            # 计算死元组比例
            total_tuples = row["live_tuples"] + row["dead_tuples"]
            row["dead_tuple_ratio"] = calculate_percentage(
                row["dead_tuples"], total_tuples)

        return safe_json_dumps({
            "schema": schema_name,
            "table": table,
            "total_tables": len(results),
            "tables": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def get_replication_metrics(config: RunnableConfig = None):
    """
    获取复制相关监控指标

    **何时使用此工具:**
    - 监控主从复制状态
    - 检测复制延迟
    - 评估复制健康度

    **工具能力:**
    - 显示所有复制连接状态
    - 监控WAL发送和接收延迟
    - 识别复制问题

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含复制指标
    """
    query = """
    SELECT 
        client_addr,
        client_hostname,
        client_port,
        state,
        sync_state,
        sync_priority,
        write_lag,
        flush_lag,
        replay_lag,
        pg_wal_lsn_diff(pg_current_wal_lsn(), sent_lsn) as sent_lag_bytes,
        pg_wal_lsn_diff(pg_current_wal_lsn(), write_lsn) as write_lag_bytes,
        pg_wal_lsn_diff(pg_current_wal_lsn(), flush_lsn) as flush_lag_bytes,
        pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) as replay_lag_bytes,
        backend_start,
        reply_time
    FROM pg_stat_replication;
    """

    try:
        results = execute_readonly_query(query, config=config)

        if not results:
            return safe_json_dumps({
                "has_replication": False,
                "message": "未配置复制或当前为从库"
            })

        # 格式化数据
        for row in results:
            row["write_lag"] = str(
                row["write_lag"]) if row["write_lag"] else "0"
            row["flush_lag"] = str(
                row["flush_lag"]) if row["flush_lag"] else "0"
            row["replay_lag"] = str(
                row["replay_lag"]) if row["replay_lag"] else "0"
            row["sent_lag_size"] = format_size(
                row["sent_lag_bytes"]) if row["sent_lag_bytes"] else "0 B"
            row["write_lag_size"] = format_size(
                row["write_lag_bytes"]) if row["write_lag_bytes"] else "0 B"
            row["flush_lag_size"] = format_size(
                row["flush_lag_bytes"]) if row["flush_lag_bytes"] else "0 B"
            row["replay_lag_size"] = format_size(
                row["replay_lag_bytes"]) if row["replay_lag_bytes"] else "0 B"
            row["backend_start"] = str(row["backend_start"])
            row["reply_time"] = str(
                row["reply_time"]) if row["reply_time"] else None

        return safe_json_dumps({
            "has_replication": True,
            "replica_count": len(results),
            "replicas": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def get_bgwriter_stats(config: RunnableConfig = None):
    """
    获取后台写入进程统计

    **何时使用此工具:**
    - 监控后台写入性能
    - 评估检查点效率
    - 优化I/O配置

    **工具能力:**
    - 显示后台写入统计
    - 监控检查点活动
    - 分析缓冲区分配

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含bgwriter统计
    """
    query = """
    SELECT 
        checkpoints_timed,
        checkpoints_req,
        checkpoint_write_time,
        checkpoint_sync_time,
        buffers_checkpoint,
        buffers_clean,
        maxwritten_clean,
        buffers_backend,
        buffers_backend_fsync,
        buffers_alloc,
        stats_reset
    FROM pg_stat_bgwriter;
    """

    try:
        result = execute_readonly_query(query, config=config)[0]

        # 计算百分比和比率
        total_checkpoints = result["checkpoints_timed"] + \
            result["checkpoints_req"]
        result["total_checkpoints"] = total_checkpoints
        result["timed_checkpoint_ratio"] = calculate_percentage(
            result["checkpoints_timed"],
            total_checkpoints
        )

        total_buffers = result["buffers_checkpoint"] + \
            result["buffers_clean"] + result["buffers_backend"]
        result["checkpoint_buffer_ratio"] = calculate_percentage(
            result["buffers_checkpoint"],
            total_buffers
        ) if total_buffers > 0 else 0

        result["stats_reset"] = str(
            result["stats_reset"]) if result["stats_reset"] else "Never"

        return safe_json_dumps(result)
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def get_wal_metrics(config: RunnableConfig = None):
    """
    获取WAL相关监控指标

    **何时使用此工具:**
    - 监控WAL生成速率
    - 评估WAL配置
    - 排查WAL相关问题

    **工具能力:**
    - 显示当前WAL位置
    - 监控WAL写入统计
    - 检查WAL归档状态

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含WAL指标
    """
    # 获取WAL统计
    wal_query = """
    SELECT 
        pg_current_wal_lsn() as current_wal_lsn,
        pg_walfile_name(pg_current_wal_lsn()) as current_wal_file,
        (SELECT setting FROM pg_settings WHERE name = 'wal_level') as wal_level,
        (SELECT setting FROM pg_settings WHERE name = 'max_wal_size') as max_wal_size,
        (SELECT setting FROM pg_settings WHERE name = 'archive_mode') as archive_mode;
    """

    # WAL统计信息
    stat_query = """
    SELECT 
        wal_records,
        wal_fpi as wal_full_page_images,
        wal_bytes,
        wal_buffers_full,
        wal_write,
        wal_sync,
        wal_write_time,
        wal_sync_time,
        stats_reset
    FROM pg_stat_wal;
    """

    try:
        wal_info = execute_readonly_query(wal_query, config=config)[0]

        # pg_stat_wal在PG14+才有
        try:
            wal_stats = execute_readonly_query(stat_query, config=config)[0]
            wal_stats["wal_size"] = format_size(wal_stats["wal_bytes"])
            wal_stats["stats_reset"] = str(
                wal_stats["stats_reset"]) if wal_stats["stats_reset"] else "Never"
        except:
            wal_stats = {"note": "pg_stat_wal需要PostgreSQL 14+"}

        return safe_json_dumps({
            "wal_info": wal_info,
            "wal_stats": wal_stats
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})
