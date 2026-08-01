"""Oracle运行监控工具集"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
import oracledb

from apps.opspilot.metis.llm.tools.common.credentials import execute_with_credentials
from apps.opspilot.metis.llm.tools.oracle.connection import (
    build_oracle_normalized_from_runnable,
    get_oracle_connection_from_item,
)
from apps.opspilot.metis.llm.tools.oracle.utils import (
    calculate_percentage,
    execute_readonly_query,
    format_size,
    safe_json_dumps,
)


@tool()
def get_database_metrics(instance_name: str = None, instance_id: str = None, config: RunnableConfig = None) -> str:
    """获取Oracle数据库核心运行指标，包括物理读写、重做写入、用户提交/回滚、解析次数、执行次数和缓冲区命中率"""
    normalized = build_oracle_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        conn = get_oracle_connection_from_item(item)
        try:
            stat_names = [
                "physical reads",
                "physical writes",
                "redo writes",
                "user commits",
                "user rollbacks",
                "parse count (total)",
                "execute count",
                "db block gets",
                "consistent gets",
            ]
            placeholders = ", ".join([f":{i + 1}" for i in range(len(stat_names))])
            query = f"""
                SELECT NAME, VALUE
                FROM v$sysstat
                WHERE NAME IN ({placeholders})
            """
            rows = execute_readonly_query(conn, query, tuple(stat_names))

            metrics = {}
            for row in rows:
                name = row.get("NAME", "")
                value = int(row.get("VALUE", 0) or 0)
                metrics[name] = value

            db_block_gets = metrics.get("db block gets", 0)
            consistent_gets = metrics.get("consistent gets", 0)
            physical_reads = metrics.get("physical reads", 0)
            total_gets = db_block_gets + consistent_gets
            if total_gets > 0:
                hit_ratio = calculate_percentage(total_gets - physical_reads, total_gets)
            else:
                hit_ratio = 0.0
            metrics["buffer_cache_hit_ratio"] = f"{hit_ratio}%"

            return metrics
        except oracledb.Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def get_table_metrics(
    table_name: str,
    db_schema: str = None,
    instance_name: str = None,
    instance_id: str = None,
    config: RunnableConfig = None,
) -> str:
    """获取Oracle表的详细指标，包括表大小、行数、块数、平均行长度、最后分析时间和统计信息是否过期"""
    normalized = build_oracle_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        conn = get_oracle_connection_from_item(item)
        try:
            owner = db_schema.upper() if db_schema else item["config"].get("user", "").upper()
            upper_table = table_name.upper()

            # 获取表大小
            size_query = """
                SELECT NVL(SUM(BYTES), 0) AS TABLE_SIZE
                FROM dba_segments
                WHERE SEGMENT_NAME = :1 AND OWNER = :2
            """
            size_rows = execute_readonly_query(conn, size_query, (upper_table, owner))
            table_size = (
                int(size_rows[0].get("TABLE_SIZE") or 0)
                if size_rows
                else 0
            )

            # 获取表基本信息
            info_query = """
                SELECT NUM_ROWS, BLOCKS, AVG_ROW_LEN, LAST_ANALYZED
                FROM dba_tables
                WHERE TABLE_NAME = :1 AND OWNER = :2
            """
            info_rows = execute_readonly_query(conn, info_query, (upper_table, owner))

            # 获取统计信息是否过期
            stale_query = """
                SELECT STALE_STATS
                FROM dba_tab_statistics
                WHERE TABLE_NAME = :1 AND OWNER = :2 AND PARTITION_NAME IS NULL
            """
            stale_rows = execute_readonly_query(conn, stale_query, (upper_table, owner))

            info = info_rows[0] if info_rows else {}
            stale_info = stale_rows[0] if stale_rows else {}

            return {
                "owner": owner,
                "table_name": upper_table,
                "table_size": format_size(table_size),
                "table_size_bytes": table_size,
                "num_rows": info.get("NUM_ROWS"),
                "blocks": info.get("BLOCKS"),
                "avg_row_len": info.get("AVG_ROW_LEN"),
                "last_analyzed": info.get("LAST_ANALYZED"),
                "stale_stats": stale_info.get("STALE_STATS"),
            }
        except oracledb.Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def get_sga_pga_stats(instance_name: str = None, instance_id: str = None, config: RunnableConfig = None) -> str:
    """获取Oracle SGA和PGA内存统计，包括SGA各组件大小、SGA详细分配、PGA统计信息和缓冲区命中率"""
    normalized = build_oracle_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        conn = get_oracle_connection_from_item(item)
        try:
            # SGA组件概览
            sga_query = "SELECT NAME, VALUE FROM v$sga"
            sga_rows = execute_readonly_query(conn, sga_query)
            sga_components = {}
            sga_total = 0
            for row in sga_rows:
                name = row.get("NAME", "")
                value = int(row.get("VALUE", 0) or 0)
                sga_components[name] = format_size(value)
                sga_total += value
            sga_components["Total"] = format_size(sga_total)

            # SGA详细分配
            sgastat_query = """
                SELECT POOL, NAME, BYTES
                FROM v$sgastat
                WHERE BYTES > 0
                ORDER BY BYTES DESC
                FETCH FIRST 20 ROWS ONLY
            """
            sgastat_rows = execute_readonly_query(conn, sgastat_query)
            sga_detail = []
            for row in sgastat_rows:
                sga_detail.append(
                    {
                        "pool": row.get("POOL"),
                        "name": row.get("NAME"),
                        "size": format_size(int(row.get("BYTES", 0) or 0)),
                    }
                )

            # PGA统计
            pga_query = "SELECT NAME, VALUE FROM v$pgastat"
            pga_rows = execute_readonly_query(conn, pga_query)
            pga_stats = {}
            for row in pga_rows:
                name = row.get("NAME", "")
                value = row.get("VALUE", 0)
                pga_stats[name] = value

            # 缓冲区命中率
            hit_query = """
                SELECT NAME, VALUE
                FROM v$sysstat
                WHERE NAME IN ('db block gets', 'consistent gets', 'physical reads')
            """
            hit_rows = execute_readonly_query(conn, hit_query)
            hit_metrics = {}
            for row in hit_rows:
                hit_metrics[row.get("NAME", "")] = int(row.get("VALUE", 0) or 0)

            db_block_gets = hit_metrics.get("db block gets", 0)
            consistent_gets = hit_metrics.get("consistent gets", 0)
            physical_reads = hit_metrics.get("physical reads", 0)
            total_gets = db_block_gets + consistent_gets
            if total_gets > 0:
                hit_ratio = calculate_percentage(total_gets - physical_reads, total_gets)
            else:
                hit_ratio = 0.0

            return {
                "sga_components": sga_components,
                "sga_detail_top20": sga_detail,
                "pga_stats": pga_stats,
                "buffer_cache_hit_ratio": f"{hit_ratio}%",
            }
        except oracledb.Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def get_io_stats(instance_name: str = None, instance_id: str = None, config: RunnableConfig = None) -> str:
    """获取Oracle I/O统计信息，包括各数据文件的物理读写次数和读写耗时"""
    normalized = build_oracle_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        conn = get_oracle_connection_from_item(item)
        try:
            query = """
                SELECT d.NAME AS file_name,
                       f.PHYRDS,
                       f.PHYWRTS,
                       f.READTIM,
                       f.WRITETIM
                FROM v$filestat f
                JOIN v$datafile d ON f.FILE# = d.FILE#
                ORDER BY (f.PHYRDS + f.PHYWRTS) DESC
            """
            rows = execute_readonly_query(conn, query)

            io_stats = []
            for row in rows:
                phyrds = int(row.get("PHYRDS", 0) or 0)
                phywrts = int(row.get("PHYWRTS", 0) or 0)
                readtim = int(row.get("READTIM", 0) or 0)
                writetim = int(row.get("WRITETIM", 0) or 0)
                avg_read_time = round(readtim / phyrds, 4) if phyrds > 0 else 0
                avg_write_time = round(writetim / phywrts, 4) if phywrts > 0 else 0

                io_stats.append(
                    {
                        "file_name": row.get("FILE_NAME"),
                        "physical_reads": phyrds,
                        "physical_writes": phywrts,
                        "read_time_cs": readtim,
                        "write_time_cs": writetim,
                        "avg_read_time_cs": avg_read_time,
                        "avg_write_time_cs": avg_write_time,
                    }
                )

            return {"datafile_count": len(io_stats), "io_stats": io_stats}
        except oracledb.Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def check_redo_log_status(instance_name: str = None, instance_id: str = None, config: RunnableConfig = None) -> str:
    """检查Oracle Redo日志和归档状态，包括日志组信息、成员文件、归档日志和数据库日志模式"""
    normalized = build_oracle_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        conn = get_oracle_connection_from_item(item)
        try:
            # Redo日志组和成员
            redo_query = """
                SELECT l.GROUP#,
                       l.MEMBERS,
                       l.BYTES,
                       l.STATUS,
                       l.SEQUENCE#,
                       lf.MEMBER
                FROM v$log l
                JOIN v$logfile lf ON l.GROUP# = lf.GROUP#
                ORDER BY l.GROUP#, lf.MEMBER
            """
            redo_rows = execute_readonly_query(conn, redo_query)

            redo_groups = {}
            for row in redo_rows:
                group_num = row.get("GROUP#")
                if group_num not in redo_groups:
                    redo_groups[group_num] = {
                        "group#": group_num,
                        "members_count": row.get("MEMBERS"),
                        "size": format_size(int(row.get("BYTES", 0) or 0)),
                        "status": row.get("STATUS"),
                        "sequence#": row.get("SEQUENCE#"),
                        "member_files": [],
                    }
                redo_groups[group_num]["member_files"].append(row.get("MEMBER"))

            # 最近归档日志
            archive_query = """
                SELECT NAME, SEQUENCE#, FIRST_TIME, COMPLETION_TIME, BLOCKS, BLOCK_SIZE
                FROM v$archived_log
                WHERE DELETED = 'NO'
                ORDER BY COMPLETION_TIME DESC
                FETCH FIRST 10 ROWS ONLY
            """
            archive_rows = execute_readonly_query(conn, archive_query)
            archived_logs = []
            for row in archive_rows:
                blocks = int(row.get("BLOCKS", 0) or 0)
                block_size = int(row.get("BLOCK_SIZE", 0) or 0)
                archived_logs.append(
                    {
                        "name": row.get("NAME"),
                        "sequence#": row.get("SEQUENCE#"),
                        "first_time": row.get("FIRST_TIME"),
                        "completion_time": row.get("COMPLETION_TIME"),
                        "size": format_size(blocks * block_size),
                    }
                )

            # 数据库日志模式
            mode_query = "SELECT LOG_MODE FROM v$database"
            mode_rows = execute_readonly_query(conn, mode_query)
            log_mode = mode_rows[0].get("LOG_MODE", "UNKNOWN") if mode_rows else "UNKNOWN"

            return {
                "log_mode": log_mode,
                "redo_log_groups": list(redo_groups.values()),
                "recent_archived_logs": archived_logs,
            }
        except oracledb.Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def get_processlist(
    active_only: bool = True,
    instance_name: str = None,
    instance_id: str = None,
    config: RunnableConfig = None,
) -> str:
    """获取Oracle活跃会话列表，包括SID、用户名、程序、SQL ID、等待事件和等待时间等信息"""
    normalized = build_oracle_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        conn = get_oracle_connection_from_item(item)
        try:
            query = """
                SELECT s.SID,
                       s.SERIAL#,
                       s.USERNAME,
                       s.PROGRAM,
                       s.MACHINE,
                       s.SQL_ID,
                       s.EVENT,
                       s.WAIT_CLASS,
                       s.SECONDS_IN_WAIT,
                       s.STATUS,
                       s.TYPE
                FROM v$session s
                LEFT JOIN v$process p ON s.PADDR = p.ADDR
            """
            conditions = []
            if active_only:
                conditions.append("s.STATUS = 'ACTIVE'")
                conditions.append("s.TYPE = 'USER'")

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY s.SECONDS_IN_WAIT DESC"

            rows = execute_readonly_query(conn, query)

            sessions = []
            for row in rows:
                sessions.append(
                    {
                        "sid": row.get("SID"),
                        "serial#": row.get("SERIAL#"),
                        "username": row.get("USERNAME"),
                        "program": row.get("PROGRAM"),
                        "machine": row.get("MACHINE"),
                        "sql_id": row.get("SQL_ID"),
                        "event": row.get("EVENT"),
                        "wait_class": row.get("WAIT_CLASS"),
                        "seconds_in_wait": row.get("SECONDS_IN_WAIT"),
                        "status": row.get("STATUS"),
                    }
                )

            return {"session_count": len(sessions), "sessions": sessions}
        except oracledb.Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))
