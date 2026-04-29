"""MySQL动态SQL查询工具 - 安全的动态查询生成和执行"""

import re
from typing import List

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from mysql.connector import Error

from apps.opspilot.metis.llm.tools.common.credentials import execute_with_credentials
from apps.opspilot.metis.llm.tools.mysql.connection import build_mysql_normalized_from_runnable, get_mysql_connection_from_item
from apps.opspilot.metis.llm.tools.mysql.utils import execute_readonly_query, safe_json_dumps, validate_sql_safety

SENSITIVE_COLUMNS = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "credential",
    "auth",
}


@tool()
def get_table_schema_details(
    table_name: str,
    database: str = None,
    instance_name: str = None,
    instance_id: str = None,
    config: RunnableConfig = None,
) -> str:
    """获取表的详细结构信息，包括列定义、注释和外键关系，用于构建动态查询和理解数据关系"""
    normalized = build_mysql_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        conn = get_mysql_connection_from_item(item)
        try:
            # 确定数据库
            db = database
            if not db:
                rows = execute_readonly_query(conn, "SELECT DATABASE() AS db")
                db = rows[0]["db"] if rows and rows[0]["db"] else None
            if not db:
                return {"error": "未指定数据库且无法获取当前数据库"}

            # 列信息（含注释）
            columns_query = """
                SELECT
                    COLUMN_NAME, ORDINAL_POSITION, COLUMN_TYPE, IS_NULLABLE,
                    COLUMN_DEFAULT, COLUMN_KEY, EXTRA, COLUMN_COMMENT
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
            """
            columns = execute_readonly_query(conn, columns_query, (db, table_name))

            if not columns:
                return {"error": f"表 {db}.{table_name} 不存在或无列信息"}

            # 外键信息
            fk_query = """
                SELECT
                    rc.CONSTRAINT_NAME,
                    kcu.COLUMN_NAME,
                    kcu.REFERENCED_TABLE_SCHEMA AS foreign_schema,
                    kcu.REFERENCED_TABLE_NAME AS foreign_table,
                    kcu.REFERENCED_COLUMN_NAME AS foreign_column
                FROM information_schema.REFERENTIAL_CONSTRAINTS rc
                JOIN information_schema.KEY_COLUMN_USAGE kcu
                    ON rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
                    AND rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
                WHERE rc.CONSTRAINT_SCHEMA = %s AND rc.TABLE_NAME = %s
            """
            foreign_keys = execute_readonly_query(conn, fk_query, (db, table_name))

            return {
                "database": db,
                "table_name": table_name,
                "columns": columns,
                "foreign_keys": foreign_keys,
            }
        except Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def search_tables_by_keyword(
    keyword: str,
    database: str = None,
    instance_name: str = None,
    instance_id: str = None,
    config: RunnableConfig = None,
) -> str:
    """根据关键字搜索相关的表和列，在表名、表注释、列名、列注释中匹配"""
    normalized = build_mysql_normalized_from_runnable(config, instance_name, instance_id)

    def _executor(item):
        conn = get_mysql_connection_from_item(item)
        try:
            db = database
            if not db:
                rows = execute_readonly_query(conn, "SELECT DATABASE() AS db")
                db = rows[0]["db"] if rows and rows[0]["db"] else None
            if not db:
                return {"error": "未指定数据库且无法获取当前数据库"}

            pattern = f"%{keyword}%"

            # 搜索表
            tables_query = """
                SELECT TABLE_NAME, TABLE_COMMENT, TABLE_ROWS
                FROM information_schema.TABLES
                WHERE TABLE_SCHEMA = %s
                  AND (TABLE_NAME LIKE %s OR TABLE_COMMENT LIKE %s)
                ORDER BY TABLE_ROWS DESC
            """
            tables = execute_readonly_query(conn, tables_query, (db, pattern, pattern))

            # 搜索列
            columns_query = """
                SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, COLUMN_COMMENT
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s
                  AND (COLUMN_NAME LIKE %s OR COLUMN_COMMENT LIKE %s)
                ORDER BY TABLE_NAME, ORDINAL_POSITION
            """
            columns = execute_readonly_query(conn, columns_query, (db, pattern, pattern))

            return {
                "keyword": keyword,
                "database": db,
                "matching_tables": tables,
                "matching_columns": columns,
            }
        except Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def execute_safe_select(
    query: str,
    database: str = None,
    instance_name: str = None,
    instance_id: str = None,
    config: RunnableConfig = None,
) -> str:
    """执行安全的SELECT查询，禁止写操作和SELECT *，自动过滤敏感列并限制返回行数"""
    normalized = build_mysql_normalized_from_runnable(config, instance_name, instance_id)

    # 安全验证
    is_safe, error_msg = validate_sql_safety(query)
    if not is_safe:
        return safe_json_dumps({"error": f"SQL安全检查失败: {error_msg}", "sql": query})

    # 禁止 SELECT *
    sql_normalized = " ".join(query.lower().split())
    if re.search(r"\bselect\s+\*\s+from\b", sql_normalized):
        return safe_json_dumps(
            {
                "error": "安全限制: 禁止使用SELECT *，必须明确指定需要查询的列名",
                "sql": query,
                "suggestion": "请先使用get_table_schema_details查看表结构，然后明确指定需要的列",
            }
        )

    def _executor(item):
        conn = get_mysql_connection_from_item(item)
        try:
            db = database
            if not db:
                rows = execute_readonly_query(conn, "SELECT DATABASE() AS db")
                db = rows[0]["db"] if rows and rows[0]["db"] else None

            if db:
                execute_readonly_query(conn, "SELECT 1")  # keep session
                cursor = conn.cursor()
                cursor.execute(f"USE `{db}`")
                cursor.close()

            # 添加 LIMIT
            sql = query.rstrip().rstrip(";")
            if "limit" not in sql.lower():
                sql = sql + " LIMIT 100"

            results = execute_readonly_query(conn, sql)

            # 过滤敏感列
            if results:
                keys_to_remove = [k for k in results[0] if k.lower() in SENSITIVE_COLUMNS]
                if keys_to_remove:
                    results = [{k: v for k, v in row.items() if k not in keys_to_remove} for row in results]

            return {
                "success": True,
                "row_count": len(results),
                "sql": sql,
                "data": results[:100],
            }
        except Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def explain_query_plan(
    query: str,
    database: str = None,
    instance_name: str = None,
    instance_id: str = None,
    config: RunnableConfig = None,
) -> str:
    """获取查询的执行计划，用于分析和优化SQL性能"""
    normalized = build_mysql_normalized_from_runnable(config, instance_name, instance_id)

    is_safe, error_msg = validate_sql_safety(query)
    if not is_safe:
        return safe_json_dumps({"error": f"SQL安全检查失败: {error_msg}", "sql": query})

    def _executor(item):
        conn = get_mysql_connection_from_item(item)
        try:
            db = database
            if not db:
                rows = execute_readonly_query(conn, "SELECT DATABASE() AS db")
                db = rows[0]["db"] if rows and rows[0]["db"] else None

            if db:
                cursor = conn.cursor()
                cursor.execute(f"USE `{db}`")
                cursor.close()

            sql = query.rstrip().rstrip(";")
            explain_sql = "EXPLAIN " + sql
            results = execute_readonly_query(conn, explain_sql)

            return {
                "success": True,
                "sql": sql,
                "execution_plan": results,
            }
        except Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def get_sample_data(
    table_name: str,
    database: str = None,
    limit: int = 10,
    instance_name: str = None,
    instance_id: str = None,
    config: RunnableConfig = None,
) -> str:
    """获取表的示例数据，自动过滤敏感列，帮助理解数据格式和内容"""
    normalized = build_mysql_normalized_from_runnable(config, instance_name, instance_id)

    # 验证表名
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table_name):
        return safe_json_dumps({"error": "无效的表名，只允许字母、数字和下划线"})

    limit = min(max(1, limit), 100)

    def _executor(item):
        conn = get_mysql_connection_from_item(item)
        try:
            db = database
            if not db:
                rows = execute_readonly_query(conn, "SELECT DATABASE() AS db")
                db = rows[0]["db"] if rows and rows[0]["db"] else None
            if not db:
                return {"error": "未指定数据库且无法获取当前数据库"}

            # 获取列列表
            col_query = """
                SELECT COLUMN_NAME
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
                ORDER BY ORDINAL_POSITION
            """
            col_rows = execute_readonly_query(conn, col_query, (db, table_name))
            if not col_rows:
                return {"error": f"表 {db}.{table_name} 不存在或无列信息"}

            # 过滤敏感列
            safe_columns = [r["COLUMN_NAME"] for r in col_rows if r["COLUMN_NAME"].lower() not in SENSITIVE_COLUMNS]
            if not safe_columns:
                return {"error": "所有列均为敏感列，无法返回示例数据"}

            column_expr = ", ".join(f"`{c}`" for c in safe_columns)
            sample_sql = f"SELECT {column_expr} FROM `{db}`.`{table_name}` LIMIT {limit}"
            results = execute_readonly_query(conn, sample_sql)

            return {
                "success": True,
                "database": db,
                "table_name": table_name,
                "columns": safe_columns,
                "row_count": len(results),
                "sample_data": results,
            }
        except Error as e:
            return {"error": str(e)}
        finally:
            conn.close()

    return safe_json_dumps(execute_with_credentials(normalized, _executor))


@tool()
def execute_safe_select_batch(
    queries: List[str],
    database: str = None,
    instance_name: str = None,
    instance_id: str = None,
    config: RunnableConfig = None,
) -> str:
    """批量执行多条安全的 SELECT 查询，每条独立校验安全性，单条失败不中断其他查询。"""
    normalized = build_mysql_normalized_from_runnable(config, instance_name, instance_id)

    results = []
    succeeded = 0
    failed = 0

    for query in queries:
        # 独立安全检查
        is_safe, error_msg = validate_sql_safety(query)
        if not is_safe:
            results.append({"input": query, "ok": False, "error": f"SQL安全检查失败: {error_msg}"})
            failed += 1
            continue

        sql_normalized = " ".join(query.lower().split())
        if re.search(r"\bselect\s+\*\s+from\b", sql_normalized):
            results.append({"input": query, "ok": False, "error": "安全限制: 禁止使用SELECT *"})
            failed += 1
            continue

        def _executor(item, _query=query):
            conn = get_mysql_connection_from_item(item)
            try:
                db = database
                if not db:
                    rows = execute_readonly_query(conn, "SELECT DATABASE() AS db")
                    db = rows[0]["db"] if rows and rows[0]["db"] else None

                if db:
                    cursor = conn.cursor()
                    cursor.execute(f"USE `{db}`")
                    cursor.close()

                sql = _query.rstrip().rstrip(";")
                if "limit" not in sql.lower():
                    sql = sql + " LIMIT 100"

                rows = execute_readonly_query(conn, sql)
                if rows:
                    keys_to_remove = [k for k in rows[0] if k.lower() in SENSITIVE_COLUMNS]
                    if keys_to_remove:
                        rows = [{k: v for k, v in row.items() if k not in keys_to_remove} for row in rows]
                return {"success": True, "row_count": len(rows), "sql": sql, "data": rows[:100]}
            except Error as e:
                return {"error": str(e)}
            finally:
                conn.close()

        try:
            data = execute_with_credentials(normalized, _executor)
            results.append({"input": query, "ok": True, "data": data})
            succeeded += 1
        except Exception as e:
            results.append({"input": query, "ok": False, "error": str(e)})
            failed += 1

    return safe_json_dumps({"total": len(queries), "succeeded": succeeded, "failed": failed, "results": results})
