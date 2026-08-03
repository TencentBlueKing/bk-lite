"""Oracle优化建议工具"""

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
def check_tablespace_usage(instance_name: str = None, instance_id: str = None, config: RunnableConfig = None) -> str:
    """检查Oracle表空间使用率、增长趋势和自动扩展状态"""
    normalized = build_oracle_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        conn = get_oracle_connection_from_item(item)
        try:
            query = """
            SELECT
                df.TABLESPACE_NAME,
                dt.CONTENTS,
                dt.STATUS,
                df.TOTAL_BYTES,
                df.MAX_BYTES,
                NVL(fs.FREE_BYTES, 0) AS FREE_BYTES,
                df.AUTOEXTENSIBLE
            FROM
                (SELECT
                    TABLESPACE_NAME,
                    SUM(BYTES) AS TOTAL_BYTES,
                    SUM(MAXBYTES) AS MAX_BYTES,
                    MAX(AUTOEXTENSIBLE) AS AUTOEXTENSIBLE
                 FROM dba_data_files
                 GROUP BY TABLESPACE_NAME) df
            JOIN dba_tablespaces dt ON df.TABLESPACE_NAME = dt.TABLESPACE_NAME
            LEFT JOIN
                (SELECT TABLESPACE_NAME, SUM(BYTES) AS FREE_BYTES
                 FROM dba_free_space
                 GROUP BY TABLESPACE_NAME) fs
            ON df.TABLESPACE_NAME = fs.TABLESPACE_NAME
            ORDER BY df.TABLESPACE_NAME
            """
            rows = execute_readonly_query(conn, query)

            tablespaces = []
            warnings = []
            for row in rows:
                total = row.get("TOTAL_BYTES") or 0
                free = row.get("FREE_BYTES") or 0
                max_bytes = row.get("MAX_BYTES") or 0
                used = total - free
                usage_pct = calculate_percentage(used, total)
                max_usage_pct = calculate_percentage(used, max_bytes) if max_bytes > 0 else usage_pct
                autoextensible = row.get("AUTOEXTENSIBLE", "NO")

                ts_info = {
                    "tablespace_name": row.get("TABLESPACE_NAME"),
                    "contents": row.get("CONTENTS"),
                    "status": row.get("STATUS"),
                    "total_size": format_size(total),
                    "used_size": format_size(used),
                    "free_size": format_size(free),
                    "max_size": format_size(max_bytes) if max_bytes > 0 else "N/A",
                    "usage_percent": usage_pct,
                    "max_usage_percent": max_usage_pct,
                    "autoextensible": autoextensible,
                }
                tablespaces.append(ts_info)

                if usage_pct > 85:
                    severity = "critical" if usage_pct > 95 else "warning"
                    warnings.append(
                        {
                            "tablespace_name": row.get("TABLESPACE_NAME"),
                            "usage_percent": usage_pct,
                            "autoextensible": autoextensible,
                            "severity": severity,
                            "message": f"表空间 {row.get('TABLESPACE_NAME')} 使用率已达 {usage_pct}%"
                            + (
                                f"，已开启自动扩展，最大空间使用率 {max_usage_pct}%"
                                if autoextensible == "YES"
                                else "，未开启自动扩展，建议扩容或清理"
                            ),
                        }
                    )

            return {
                "tablespaces": tablespaces,
                "warnings": warnings,
                "total_count": len(tablespaces),
                "warning_count": len(warnings),
            }
        except oracledb.Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def check_unused_indexes(db_schema: str = None, instance_name: str = None, instance_id: str = None, config: RunnableConfig = None) -> str:
    """检测Oracle未使用的索引，帮助识别可以删除以减少维护开销的冗余索引"""
    normalized = build_oracle_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        conn = get_oracle_connection_from_item(item)
        try:
            unused_indexes = []

            # 尝试通过 dba_index_usage (12c+) 查找未使用索引
            try:
                usage_query = """
                SELECT
                    i.OWNER,
                    i.INDEX_NAME,
                    i.TABLE_NAME,
                    i.INDEX_TYPE,
                    iu.TOTAL_ACCESS_COUNT,
                    iu.LAST_USED
                FROM dba_indexes i
                LEFT JOIN dba_index_usage iu
                    ON i.OWNER = iu.OWNER AND i.INDEX_NAME = iu.NAME
                WHERE (iu.TOTAL_ACCESS_COUNT = 0 OR iu.TOTAL_ACCESS_COUNT IS NULL)
                  AND i.OWNER NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP', 'WMSYS', 'XDB', 'CTXSYS', 'MDSYS', 'ORDSYS', 'ORDDATA')
                  AND i.INDEX_TYPE != 'LOB'
                """
                if db_schema:
                    usage_query += " AND i.OWNER = :schema"
                    rows = execute_readonly_query(conn, usage_query, (db_schema.upper(),))
                else:
                    rows = execute_readonly_query(conn, usage_query)

                for row in rows:
                    unused_indexes.append(
                        {
                            "owner": row.get("OWNER"),
                            "index_name": row.get("INDEX_NAME"),
                            "table_name": row.get("TABLE_NAME"),
                            "index_type": row.get("INDEX_TYPE"),
                            "total_access_count": row.get("TOTAL_ACCESS_COUNT", 0),
                            "last_used": str(row.get("LAST_USED", "")),
                            "detection_method": "dba_index_usage",
                        }
                    )
            except oracledb.Error:
                # dba_index_usage 不可用，回退到 v$sql_plan 方式
                fallback_query = """
                SELECT
                    i.OWNER,
                    i.INDEX_NAME,
                    i.TABLE_NAME,
                    i.INDEX_TYPE
                FROM dba_indexes i
                WHERE i.OWNER NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP', 'WMSYS', 'XDB', 'CTXSYS', 'MDSYS', 'ORDSYS', 'ORDDATA')
                  AND i.INDEX_TYPE != 'LOB'
                  AND NOT EXISTS (
                      SELECT 1 FROM v$sql_plan sp
                      WHERE sp.OBJECT_OWNER = i.OWNER
                        AND sp.OBJECT_NAME = i.INDEX_NAME
                  )
                """
                if db_schema:
                    fallback_query += " AND i.OWNER = :schema"
                    rows = execute_readonly_query(conn, fallback_query, (db_schema.upper(),))
                else:
                    rows = execute_readonly_query(conn, fallback_query)

                for row in rows:
                    unused_indexes.append(
                        {
                            "owner": row.get("OWNER"),
                            "index_name": row.get("INDEX_NAME"),
                            "table_name": row.get("TABLE_NAME"),
                            "index_type": row.get("INDEX_TYPE"),
                            "last_used": "",
                            "detection_method": "v$sql_plan_absence",
                        }
                    )

            return {
                "unused_indexes": unused_indexes,
                "total_count": len(unused_indexes),
                "schema_filter": db_schema,
                "recommendation": "建议在确认索引确实不再需要后，使用 DROP INDEX 删除冗余索引以减少DML操作的维护开销",
            }
        except oracledb.Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def check_table_fragmentation(db_schema: str = None, instance_name: str = None, instance_id: str = None, config: RunnableConfig = None) -> str:
    """检查Oracle表碎片和行迁移/行链接情况，帮助识别需要重组的表"""
    normalized = build_oracle_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        conn = get_oracle_connection_from_item(item)
        try:
            query = """
            SELECT
                t.OWNER,
                t.TABLE_NAME,
                t.NUM_ROWS,
                t.BLOCKS,
                t.AVG_ROW_LEN,
                t.CHAIN_CNT,
                s.BYTES AS ACTUAL_BYTES
            FROM dba_tables t
            JOIN dba_segments s
                ON t.OWNER = s.OWNER AND t.TABLE_NAME = s.SEGMENT_NAME AND s.SEGMENT_TYPE = 'TABLE'
            WHERE t.NUM_ROWS > 0
              AND t.BLOCKS > 0
              AND t.OWNER NOT IN ('SYS', 'SYSTEM', 'OUTLN', 'DBSNMP', 'WMSYS', 'XDB', 'CTXSYS', 'MDSYS', 'ORDSYS', 'ORDDATA')
            """
            if db_schema:
                query += " AND t.OWNER = :schema"
                rows = execute_readonly_query(conn, query, (db_schema.upper(),))
            else:
                rows = execute_readonly_query(conn, query)

            fragmented_tables = []
            warnings = []
            for row in rows:
                num_rows = row.get("NUM_ROWS") or 0
                avg_row_len = row.get("AVG_ROW_LEN") or 0
                chain_cnt = row.get("CHAIN_CNT") or 0
                actual_bytes = row.get("ACTUAL_BYTES") or 0

                estimated_bytes = num_rows * avg_row_len
                if actual_bytes > 0 and estimated_bytes > 0:
                    fragmentation_pct = round((actual_bytes - estimated_bytes) / actual_bytes * 100, 2)
                else:
                    fragmentation_pct = 0.0

                # 仅对碎片率超过30%或存在行链接的表进行报告
                if fragmentation_pct <= 30 and chain_cnt == 0:
                    continue

                table_info = {
                    "owner": row.get("OWNER"),
                    "table_name": row.get("TABLE_NAME"),
                    "num_rows": num_rows,
                    "blocks": row.get("BLOCKS"),
                    "avg_row_len": avg_row_len,
                    "chain_cnt": chain_cnt,
                    "estimated_size": format_size(estimated_bytes),
                    "actual_size": format_size(actual_bytes),
                    "fragmentation_percent": fragmentation_pct,
                }
                fragmented_tables.append(table_info)

                issues = []
                severity = "info"
                if fragmentation_pct > 50:
                    issues.append(f"碎片率 {fragmentation_pct}%（严重）")
                    severity = "critical"
                elif fragmentation_pct > 30:
                    issues.append(f"碎片率 {fragmentation_pct}%")
                    severity = "warning"

                if chain_cnt > 0:
                    chain_pct = calculate_percentage(chain_cnt, num_rows)
                    issues.append(f"行迁移/行链接数 {chain_cnt}（占比 {chain_pct}%）")
                    if chain_pct > 10:
                        severity = "critical"
                    elif severity != "critical":
                        severity = "warning"

                if issues:
                    warnings.append(
                        {
                            "owner": row.get("OWNER"),
                            "table_name": row.get("TABLE_NAME"),
                            "severity": severity,
                            "issues": issues,
                            "recommendation": "建议使用 ALTER TABLE ... MOVE 或 DBMS_REDEFINITION 在线重组表以消除碎片",
                        }
                    )

            return {
                "fragmented_tables": fragmented_tables,
                "warnings": warnings,
                "total_count": len(fragmented_tables),
                "warning_count": len(warnings),
                "schema_filter": db_schema,
            }
        except oracledb.Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def check_configuration_tuning(instance_name: str = None, instance_id: str = None, config: RunnableConfig = None) -> str:
    """Oracle配置调优建议，检查SGA/PGA自动调优、缓冲区命中率、共享池空闲内存、重做日志大小和进程/会话参数"""
    normalized = build_oracle_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        conn = get_oracle_connection_from_item(item)
        try:
            recommendations = []

            # 检查关键参数
            param_query = """
            SELECT NAME, VALUE, DISPLAY_VALUE
            FROM v$parameter
            WHERE NAME IN (
                'sga_target', 'sga_max_size', 'pga_aggregate_target',
                'memory_target', 'memory_max_target',
                'db_cache_size', 'shared_pool_size',
                'processes', 'sessions', 'open_cursors'
            )
            """
            params = execute_readonly_query(conn, param_query)
            param_map = {row["NAME"]: row for row in params}

            # SGA 自动调优检查
            sga_target = int(param_map.get("sga_target", {}).get("VALUE") or 0)
            memory_target = int(param_map.get("memory_target", {}).get("VALUE") or 0)
            if memory_target > 0:
                recommendations.append(
                    {
                        "category": "内存管理",
                        "item": "自动内存管理(AMM)",
                        "current_value": param_map.get("memory_target", {}).get("DISPLAY_VALUE"),
                        "severity": "info",
                        "message": "已启用自动内存管理(memory_target > 0)，SGA和PGA由Oracle自动调优",
                    }
                )
            elif sga_target > 0:
                recommendations.append(
                    {
                        "category": "内存管理",
                        "item": "SGA自动调优",
                        "current_value": param_map.get("sga_target", {}).get("DISPLAY_VALUE"),
                        "severity": "info",
                        "message": "已启用SGA自动调优(sga_target > 0)",
                    }
                )
            else:
                recommendations.append(
                    {
                        "category": "内存管理",
                        "item": "SGA自动调优",
                        "current_value": "0",
                        "severity": "warning",
                        "message": "SGA自动调优未启用(sga_target = 0)，建议设置 sga_target 以启用SGA自动管理",
                    }
                )

            # PGA 自动调优检查
            pga_target = int(
                param_map.get("pga_aggregate_target", {}).get("VALUE") or 0
            )
            if memory_target == 0:
                if pga_target > 0:
                    recommendations.append(
                        {
                            "category": "内存管理",
                            "item": "PGA自动调优",
                            "current_value": param_map.get("pga_aggregate_target", {}).get("DISPLAY_VALUE"),
                            "severity": "info",
                            "message": "已启用PGA自动调优(pga_aggregate_target > 0)",
                        }
                    )
                else:
                    recommendations.append(
                        {
                            "category": "内存管理",
                            "item": "PGA自动调优",
                            "current_value": "0",
                            "severity": "warning",
                            "message": "PGA自动调优未启用(pga_aggregate_target = 0)，建议设置 pga_aggregate_target 以优化排序和哈希操作的内存分配",
                        }
                    )

            # 缓冲区缓存命中率
            try:
                hit_query = """
                SELECT
                    1 - (SUM(CASE WHEN NAME = 'physical reads' THEN VALUE ELSE 0 END) /
                         NULLIF(SUM(CASE WHEN NAME IN ('db block gets', 'consistent gets') THEN VALUE ELSE 0 END), 0))
                    AS HIT_RATIO
                FROM v$sysstat
                WHERE NAME IN ('physical reads', 'db block gets', 'consistent gets')
                """
                hit_result = execute_readonly_query(conn, hit_query)
                hit_ratio = hit_result[0].get("HIT_RATIO") if hit_result else None
                if hit_ratio is not None:
                    hit_pct = round(float(hit_ratio) * 100, 2)
                    severity = "info" if hit_pct >= 95 else ("warning" if hit_pct >= 90 else "critical")
                    recommendations.append(
                        {
                            "category": "缓存效率",
                            "item": "缓冲区缓存命中率",
                            "current_value": f"{hit_pct}%",
                            "severity": severity,
                            "message": f"缓冲区缓存命中率为 {hit_pct}%"
                            + ("" if hit_pct >= 95 else "，低于95%推荐值，建议增大 db_cache_size 或 sga_target"),
                        }
                    )
            except oracledb.Error:
                pass

            # 共享池空闲内存
            try:
                shared_pool_query = """
                SELECT BYTES FROM v$sgastat
                WHERE POOL = 'shared pool' AND NAME = 'free memory'
                """
                sp_result = execute_readonly_query(conn, shared_pool_query)
                if sp_result:
                    free_mem = int(sp_result[0].get("BYTES") or 0)
                    shared_pool_size = int(
                        param_map.get("shared_pool_size", {}).get("VALUE") or 0
                    )
                    if shared_pool_size > 0:
                        free_pct = calculate_percentage(free_mem, shared_pool_size)
                    else:
                        free_pct = None

                    severity = "info"
                    message = f"共享池空闲内存 {format_size(free_mem)}"
                    if free_pct is not None:
                        message += f"（占比 {free_pct}%）"
                        if free_pct < 5:
                            severity = "critical"
                            message += "，空闲内存过低，可能导致ORA-04031错误，建议增大共享池"
                        elif free_pct < 15:
                            severity = "warning"
                            message += "，空闲内存偏低，建议关注是否频繁出现硬解析"

                    recommendations.append(
                        {
                            "category": "缓存效率",
                            "item": "共享池空闲内存",
                            "current_value": format_size(free_mem),
                            "severity": severity,
                            "message": message,
                        }
                    )
            except oracledb.Error:
                pass

            # 重做日志大小
            try:
                redo_query = """
                SELECT GROUP#, BYTES, STATUS FROM v$log ORDER BY GROUP#
                """
                redo_result = execute_readonly_query(conn, redo_query)
                if redo_result:
                    log_sizes = [int(row.get("BYTES") or 0) for row in redo_result]
                    min_log_size = min(log_sizes) if log_sizes else 0
                    recommended_min = 200 * 1024 * 1024  # 200MB

                    severity = "info" if min_log_size >= recommended_min else "warning"
                    recommendations.append(
                        {
                            "category": "重做日志",
                            "item": "重做日志大小",
                            "current_value": f"{len(redo_result)} 组，最小 {format_size(min_log_size)}",
                            "severity": severity,
                            "message": f"当前 {len(redo_result)} 组重做日志，最小 {format_size(min_log_size)}"
                            + ("" if min_log_size >= recommended_min else f"，建议每组至少 {format_size(recommended_min)} 以减少日志切换频率"),
                        }
                    )
            except oracledb.Error:
                pass

            # 进程/会话参数
            processes_val = int(param_map.get("processes", {}).get("VALUE") or 0)
            sessions_val = int(param_map.get("sessions", {}).get("VALUE") or 0)
            if processes_val > 0:
                try:
                    active_query = """
                    SELECT COUNT(*) AS CNT FROM v$process
                    """
                    active_result = execute_readonly_query(conn, active_query)
                    active_count = (
                        int(active_result[0].get("CNT") or 0)
                        if active_result
                        else 0
                    )
                    usage_pct = calculate_percentage(active_count, processes_val)
                    severity = "info" if usage_pct < 80 else ("warning" if usage_pct < 90 else "critical")
                    recommendations.append(
                        {
                            "category": "连接管理",
                            "item": "进程/会话使用率",
                            "current_value": f"进程 {active_count}/{processes_val}，会话上限 {sessions_val}",
                            "severity": severity,
                            "message": f"当前进程数 {active_count}/{processes_val}（{usage_pct}%）"
                            + ("" if usage_pct < 80 else "，接近上限，建议增大 processes 参数或检查连接泄漏"),
                        }
                    )
                except oracledb.Error:
                    pass

            return {
                "recommendations": recommendations,
                "total_count": len(recommendations),
                "critical_count": sum(1 for r in recommendations if r["severity"] == "critical"),
                "warning_count": sum(1 for r in recommendations if r["severity"] == "warning"),
            }
        except oracledb.Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))
