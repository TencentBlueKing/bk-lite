"""Oracle动态SQL查询工具 - 安全的动态查询生成和执行"""

from typing import List, Optional

import oracledb
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.common.credentials import execute_with_credentials
from apps.opspilot.metis.llm.tools.common.sql_guard import (
    detect_select_star,
    filter_sensitive_columns,
    run_blocking,
    sanitize_db_error,
)
from apps.opspilot.metis.llm.tools.oracle.connection import build_oracle_normalized_from_runnable, get_oracle_connection_from_item
from apps.opspilot.metis.llm.tools.oracle.utils import execute_readonly_query, safe_json_dumps, validate_sql_safety


@tool()
def search_tables_by_keyword(
    keyword: str,
    db_schema: Optional[str] = None,
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """按关键字搜索Oracle表名和列名，在ALL_TABLES和ALL_TAB_COLUMNS中匹配"""
    normalized = build_oracle_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        conn = get_oracle_connection_from_item(item)
        try:
            pattern = f"%{keyword.upper()}%"

            if db_schema:
                owner_filter = "AND OWNER = :owner"
                tables_params = {"pattern": pattern, "owner": db_schema.upper()}
                columns_params = {"pattern": pattern, "owner": db_schema.upper()}
            else:
                owner_filter = ""
                tables_params = {"pattern": pattern}
                columns_params = {"pattern": pattern}

            # 搜索表名
            tables_query = f"""
                SELECT OWNER, TABLE_NAME, NUM_ROWS
                FROM ALL_TABLES
                WHERE TABLE_NAME LIKE :pattern
                  {owner_filter}
                ORDER BY NUM_ROWS DESC NULLS LAST
                FETCH FIRST 50 ROWS ONLY
            """
            tables = execute_readonly_query(conn, tables_query, tables_params)

            # 搜索列名
            columns_query = f"""
                SELECT OWNER, TABLE_NAME, COLUMN_NAME, DATA_TYPE
                FROM ALL_TAB_COLUMNS
                WHERE COLUMN_NAME LIKE :pattern
                  {owner_filter}
                ORDER BY OWNER, TABLE_NAME, COLUMN_ID
                FETCH FIRST 50 ROWS ONLY
            """
            columns = execute_readonly_query(conn, columns_query, columns_params)

            return {
                "keyword": keyword,
                "schema": db_schema,
                "matching_tables": tables,
                "matching_columns": columns,
            }
        except oracledb.Error as e:
            return {"error": sanitize_db_error(e, "查询执行")}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def execute_safe_select(
    sql: str,
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """安全执行Oracle SELECT查询（只读模式），禁止写操作和SELECT *，自动过滤敏感列并限制返回行数"""
    normalized = build_oracle_normalized_from_runnable(config, instance_name, instance_id)

    # 安全验证
    is_safe, error_msg = validate_sql_safety(sql)
    if not is_safe:
        return safe_json_dumps({"error": f"SQL安全检查失败: {error_msg}", "sql": sql})

    # 禁止 SELECT *
    if detect_select_star(sql):
        return safe_json_dumps(
            {
                "error": "安全限制: 禁止使用SELECT *，必须明确指定需要查询的列名",
                "sql": sql,
                "suggestion": "请先查看表结构，然后明确指定需要的列",
            }
        )

    def _executor(item):
        conn = get_oracle_connection_from_item(item)
        try:
            # 添加行数限制
            query = sql.rstrip().rstrip(";")
            if "fetch" not in query.lower() and "rownum" not in query.lower():
                query = f"SELECT * FROM ({query}) WHERE ROWNUM <= 100"

            # 使用只读事务执行 (阻塞 IO 卸载到线程, F038)
            def _run():
                cursor = conn.cursor()
                try:
                    cursor.execute("SET TRANSACTION READ ONLY")
                    cursor.execute(query)
                    columns = [col[0] for col in cursor.description]
                    rows = cursor.fetchmany(100)
                    return [dict(zip(columns, row)) for row in rows]
                finally:
                    cursor.close()

            results = filter_sensitive_columns(run_blocking(_run))

            return {
                "success": True,
                "row_count": len(results),
                "sql": query,
                "data": results[:100],
            }
        except oracledb.Error as e:
            return {"error": sanitize_db_error(e, "查询执行")}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def explain_query_plan(
    sql: str,
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """获取Oracle SQL执行计划，用于分析和优化SQL性能"""
    normalized = build_oracle_normalized_from_runnable(config, instance_name, instance_id)

    is_safe, error_msg = validate_sql_safety(sql)
    if not is_safe:
        return safe_json_dumps({"error": f"SQL安全检查失败: {error_msg}", "sql": sql})

    def _executor(item):
        conn = get_oracle_connection_from_item(item)
        try:
            query = sql.rstrip().rstrip(";")

            def _run():
                cursor = conn.cursor()
                try:
                    # 生成执行计划
                    cursor.execute(f"EXPLAIN PLAN FOR {query}")

                    # 读取执行计划输出
                    cursor.execute("SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY())")
                    return [row[0] for row in cursor.fetchall()]
                finally:
                    cursor.close()

            plan_lines = run_blocking(_run)

            return {
                "success": True,
                "sql": query,
                "execution_plan": plan_lines,
            }
        except oracledb.Error as e:
            return {"error": sanitize_db_error(e, "执行计划获取")}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def execute_safe_select_batch(
    queries: List[str],
    instance_name: Optional[str] = None,
    instance_id: Optional[str] = None,
    config: RunnableConfig = None,
) -> str:
    """批量执行多条安全的 Oracle SELECT 查询，每条独立校验安全性，单条失败不中断其他查询。"""
    normalized = build_oracle_normalized_from_runnable(config, instance_name, instance_id)

    results = []
    succeeded = 0
    failed = 0

    for query in queries:
        is_safe, error_msg = validate_sql_safety(query)
        if not is_safe:
            results.append({"input": query, "ok": False, "error": f"SQL安全检查失败: {error_msg}"})
            failed += 1
            continue

        if detect_select_star(query):
            results.append({"input": query, "ok": False, "error": "安全限制: 禁止使用SELECT *"})
            failed += 1
            continue

        def _executor(item, _query=query):
            conn = get_oracle_connection_from_item(item)
            try:
                sql = _query.rstrip().rstrip(";")
                if "fetch" not in sql.lower() and "rownum" not in sql.lower():
                    sql = f"SELECT * FROM ({sql}) WHERE ROWNUM <= 100"

                def _run():
                    cursor = conn.cursor()
                    try:
                        cursor.execute("SET TRANSACTION READ ONLY")
                        cursor.execute(sql)
                        columns = [col[0] for col in cursor.description]
                        rows = cursor.fetchmany(100)
                        return [dict(zip(columns, row)) for row in rows]
                    finally:
                        cursor.close()

                row_dicts = filter_sensitive_columns(run_blocking(_run))
                return {"success": True, "row_count": len(row_dicts), "sql": sql, "data": row_dicts}
            except oracledb.Error as e:
                return {"error": sanitize_db_error(e, "查询执行")}
            finally:
                conn.close()

        try:
            data = execute_with_credentials(normalized, _executor)
            results.append({"input": query, "ok": True, "data": data})
            succeeded += 1
        except Exception as e:
            results.append({"input": query, "ok": False, "error": sanitize_db_error(e, "查询执行")})
            failed += 1

    return safe_json_dumps({"total": len(queries), "succeeded": succeeded, "failed": failed, "results": results})
