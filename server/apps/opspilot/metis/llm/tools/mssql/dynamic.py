"""MSSQL动态SQL查询工具 - 安全的动态查询生成和执行"""

import re
from typing import Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.mssql.utils import execute_readonly_query, format_size, safe_json_dumps


def validate_sql_safety(sql: str) -> tuple[bool, str]:
    """
    验证SQL语句的安全性

    Args:
        sql: 待验证的SQL语句

    Returns:
        tuple: (是否安全, 错误信息)
    """
    # 转换为小写用于检查
    sql_lower = sql.lower().strip()

    # 禁止的关键字列表 - 任何写操作
    forbidden_keywords = [
        "insert",
        "update",
        "delete",
        "drop",
        "create",
        "alter",
        "truncate",
        "grant",
        "revoke",
        "rename",
        "replace",
        "merge",
        "execute",
        "exec",
        "sp_",
        "xp_",
        "bulk",
        "backup",
        "restore",
        "dbcc",
        "kill",
        "shutdown",
        "reconfigure",
        "deny",
        "openquery",
        "openrowset",
        "opendatasource",
    ]

    for keyword in forbidden_keywords:
        # 使用单词边界检查,避免误判
        pattern = r"\b" + keyword + r"\b"
        if re.search(pattern, sql_lower):
            return False, f"SQL包含禁止的关键字: {keyword}"

    # 必须以SELECT开头
    if not sql_lower.startswith("select") and not sql_lower.startswith("with"):
        return False, "SQL必须以SELECT或WITH开头"

    # 禁止分号分隔的多条语句
    if sql.count(";") > 1 or (sql.count(";") == 1 and not sql.strip().endswith(";")):
        return False, "禁止执行多条SQL语句"

    # 禁止注释注入
    if "--" in sql or "/*" in sql:
        return False, "SQL不允许包含注释符号"

    return True, ""


@tool()
def get_table_schema_details(table_name: str, schema_name: str = "dbo", database: Optional[str] = None, config: RunnableConfig = None):
    """
    获取表的详细结构信息,用于构建动态查询和理解数据关系

    **何时使用此工具:**
    - 需要了解表的完整列信息以构建SELECT查询
    - 需要知道字段类型以构建WHERE条件和JOIN条件
    - 需要了解索引以优化查询性能
    - 需要通过外键理解表之间的关系和层级结构
    - 分析业务实体之间的关联关系

    **工具能力:**
    - 获取所有列名、类型、是否可空、默认值
    - 获取主键和外键信息(用于JOIN和理解表关系)
    - 获取索引信息(优化查询性能)
    - 获取表统计信息(行数估算)

    Args:
        table_name (str): 表名
        schema_name (str): schema名称,默认dbo
        database (str, optional): 数据库名,不填则使用默认数据库
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含表结构的详细信息
    """
    # 表基本信息
    table_info_query = """
    SELECT
        t.name as table_name,
        s.name as schema_name,
        p.rows as estimated_rows,
        CAST(SUM(a.total_pages) * 8 * 1024 AS BIGINT) as total_size_bytes
    FROM sys.tables t
    INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
    INNER JOIN sys.partitions p ON t.object_id = p.object_id AND p.index_id IN (0, 1)
    INNER JOIN sys.allocation_units a ON p.partition_id = a.container_id
    WHERE s.name = ? AND t.name = ?
    GROUP BY t.name, s.name, p.rows;
    """

    # 列信息
    columns_query = """
    SELECT
        c.name as column_name,
        c.column_id as column_position,
        tp.name as data_type,
        c.max_length,
        c.precision,
        c.scale,
        c.is_nullable,
        OBJECT_DEFINITION(c.default_object_id) as column_default,
        c.is_identity,
        CASE WHEN pk.column_id IS NOT NULL THEN 1 ELSE 0 END as is_primary_key
    FROM sys.columns c
    INNER JOIN sys.types tp ON c.user_type_id = tp.user_type_id
    INNER JOIN sys.tables t ON c.object_id = t.object_id
    INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
    LEFT JOIN (
        SELECT ic.object_id, ic.column_id
        FROM sys.index_columns ic
        INNER JOIN sys.indexes i ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        WHERE i.is_primary_key = 1
    ) pk ON c.object_id = pk.object_id AND c.column_id = pk.column_id
    WHERE s.name = ? AND t.name = ?
    ORDER BY c.column_id;
    """

    # 索引信息
    indexes_query = """
    SELECT
        i.name as index_name,
        i.is_unique,
        i.is_primary_key,
        STUFF((
            SELECT ', ' + c.name
            FROM sys.index_columns ic
            INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
            WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id
            ORDER BY ic.key_ordinal
            FOR XML PATH('')
        ), 1, 2, '') as columns
    FROM sys.indexes i
    INNER JOIN sys.tables t ON i.object_id = t.object_id
    INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = ? AND t.name = ? AND i.name IS NOT NULL;
    """

    # 外键信息
    foreign_keys_query = """
    SELECT
        fk.name as constraint_name,
        COL_NAME(fkc.parent_object_id, fkc.parent_column_id) as column_name,
        SCHEMA_NAME(rt.schema_id) as foreign_schema,
        rt.name as foreign_table,
        COL_NAME(fkc.referenced_object_id, fkc.referenced_column_id) as foreign_column
    FROM sys.foreign_keys fk
    INNER JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
    INNER JOIN sys.tables t ON fk.parent_object_id = t.object_id
    INNER JOIN sys.tables rt ON fk.referenced_object_id = rt.object_id
    INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = ? AND t.name = ?;
    """

    try:
        table_info = execute_readonly_query(table_info_query, params=(schema_name, table_name), config=config, database=database)

        if not table_info:
            return safe_json_dumps({"error": f"表 {schema_name}.{table_name} 不存在"})

        columns = execute_readonly_query(columns_query, params=(schema_name, table_name), config=config, database=database)

        indexes = execute_readonly_query(indexes_query, params=(schema_name, table_name), config=config, database=database)

        foreign_keys = execute_readonly_query(foreign_keys_query, params=(schema_name, table_name), config=config, database=database)

        table_info[0]["total_size"] = format_size(table_info[0]["total_size_bytes"])

        return safe_json_dumps({"table_info": table_info[0], "columns": columns, "indexes": indexes, "foreign_keys": foreign_keys})

    except Exception as e:
        return safe_json_dumps({"error": f"获取表结构失败: {str(e)}"})


@tool()
def search_tables_by_keyword(keyword: str, database: Optional[str] = None, config: RunnableConfig = None):
    """
    根据关键字搜索相关的表和列,帮助发现业务实体及其数据存储位置

    **何时使用此工具:**
    - 不确定业务数据存储在哪个表中
    - 根据业务关键词查找相关表
    - 查找包含特定列名的表
    - 探索业务模块的表结构

    **工具能力:**
    - 在表名中搜索关键字
    - 在列名中搜索关键字
    - 返回匹配表的预估行数

    Args:
        keyword (str): 搜索关键字
        database (str, optional): 数据库名,不填则使用默认数据库
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含匹配的表和列信息
    """
    query = """
    SELECT DISTINCT
        s.name as schema_name,
        t.name as table_name,
        p.rows as estimated_rows,
        (
            SELECT STRING_AGG(c.name, ', ') WITHIN GROUP (ORDER BY c.column_id)
            FROM sys.columns c
            WHERE c.object_id = t.object_id AND c.name LIKE ?
        ) as matching_columns
    FROM sys.tables t
    INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
    INNER JOIN sys.partitions p ON t.object_id = p.object_id AND p.index_id IN (0, 1)
    LEFT JOIN sys.columns c ON t.object_id = c.object_id
    WHERE t.name LIKE ? OR c.name LIKE ?
    ORDER BY p.rows DESC;
    """

    search_pattern = f"%{keyword}%"

    try:
        results = execute_readonly_query(query, params=(search_pattern, search_pattern, search_pattern), config=config, database=database)

        return safe_json_dumps({"keyword": keyword, "total_matches": len(results), "tables": results})

    except Exception as e:
        return safe_json_dumps({"error": f"搜索失败: {str(e)}"})


@tool()
def execute_safe_select(sql: str, limit: int = 100, database: Optional[str] = None, config: RunnableConfig = None):
    """
    执行安全的SELECT查询,支持聚合统计、多表关联等复杂查询

    **⚠️ 安全要求 - 构建SQL时必须遵守:**
    1. **禁止SELECT ***: 必须明确列出需要的列名
    2. **避免敏感字段**: 不要查询password, secret, token, key, hash等敏感字段
    3. **最小化查询**: 只查询回答问题所需的最少列和行
    4. **使用WHERE过滤**: 合理使用WHERE条件减少数据量
    5. **使用TOP限制**: MSSQL使用TOP而非LIMIT

    **安全机制:**
    - 只允许SELECT和WITH查询
    - 禁止所有写操作(INSERT/UPDATE/DELETE等)
    - 禁止DDL操作(CREATE/DROP/ALTER等)
    - 禁止存储过程执行
    - 自动添加TOP限制
    - SQL安全验证

    **SQL编写规范:**

    ✅ **明细查询示例:**
    ```sql
    SELECT TOP 100 id, name, created_at FROM dbo.users WHERE status = 'active'
    ```

    ✅ **聚合统计示例:**
    ```sql
    SELECT department, COUNT(*) as emp_count
    FROM dbo.employees
    GROUP BY department
    ```

    Args:
        sql (str): SELECT SQL语句 - 必须明确指定列名,禁止使用*
        limit (int): 最大返回行数,默认100,最大1000
        database (str, optional): 数据库名,不填则使用默认数据库
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含:
        - success: 是否成功
        - row_count: 返回行数
        - limit: 应用的LIMIT值
        - sql: 执行的SQL语句
        - data: 查询结果数组
    """
    # 检测SELECT *
    sql_normalized = " ".join(sql.lower().split())
    if re.search(r"\bselect\s+\*\s+from\b", sql_normalized):
        return safe_json_dumps(
            {
                "error": "安全限制: 禁止使用SELECT *,必须明确指定需要查询的列名",
                "sql": sql,
                "suggestion": "请先使用get_table_schema_details查看表结构,然后明确指定需要的列。例如: SELECT id, name, created_at FROM table_name",
            }
        )

    # 检测敏感字段关键词
    SENSITIVE_KEYWORDS = ["password", "secret", "token", "key", "hash", "otp", "credential"]
    for keyword in SENSITIVE_KEYWORDS:
        if re.search(rf"\bselect\b.*\b{keyword}\b.*\bfrom\b", sql_normalized):
            return safe_json_dumps(
                {
                    "error": f"安全限制: SQL中可能包含敏感字段 '{keyword}',请移除敏感字段",
                    "sql": sql,
                    "suggestion": "请确保只查询非敏感字段,如id, name, email, status, created_at等",
                }
            )

    # 安全验证
    is_safe, error_msg = validate_sql_safety(sql)
    if not is_safe:
        return safe_json_dumps({"error": f"SQL安全检查失败: {error_msg}", "sql": sql})

    # 限制返回行数
    limit = min(max(1, limit), 1000)

    # 移除末尾分号
    sql = sql.rstrip().rstrip(";")

    # 检查是否已有TOP子句
    sql_lower = sql.lower()
    if "top" not in sql_lower:
        # 在SELECT后添加TOP
        sql = re.sub(r"\bselect\b", f"SELECT TOP {limit}", sql, count=1, flags=re.IGNORECASE)
    else:
        # 如果已有TOP,确保不超过最大值
        top_match = re.search(r"top\s+(\d+)", sql_lower)
        if top_match:
            existing_top = int(top_match.group(1))
            if existing_top > limit:
                sql = re.sub(r"top\s+\d+", f"TOP {limit}", sql, count=1, flags=re.IGNORECASE)

    try:
        results = execute_readonly_query(sql, config=config, database=database)

        return safe_json_dumps({"success": True, "row_count": len(results), "limit": limit, "sql": sql, "data": results})

    except Exception as e:
        return safe_json_dumps({"error": f"查询执行失败: {str(e)}", "sql": sql})


@tool()
def explain_query_plan(sql: str, database: Optional[str] = None, config: RunnableConfig = None):
    """
    获取查询的执行计划,用于优化动态生成的查询

    **何时使用此工具:**
    - 查询性能较慢,需要优化
    - 验证查询是否使用了索引
    - 了解查询的执行成本
    - 优化动态生成的复杂查询

    **工具能力:**
    - 显示查询执行计划
    - 显示预估成本和行数
    - 显示是否使用索引

    Args:
        sql (str): 要分析的SELECT SQL语句
        database (str, optional): 数据库名,不填则使用默认数据库
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含执行计划详情
    """
    # 安全验证
    is_safe, error_msg = validate_sql_safety(sql)
    if not is_safe:
        return safe_json_dumps({"error": f"SQL安全检查失败: {error_msg}", "sql": sql})

    # 移除末尾分号
    sql = sql.rstrip().rstrip(";")

    # 使用SET SHOWPLAN_TEXT ON获取执行计划
    # 注意: 这需要特殊处理,因为SHOWPLAN需要单独的连接设置
    # 作为替代,我们使用dm_exec_query_plan来获取缓存的执行计划或预估计划

    try:
        # 由于pyodbc不直接支持SET SHOWPLAN_ALL的方式,
        # 我们使用一个替代方案:分析查询的预估行数和索引使用
        estimate_query = """
        SELECT
            qs.execution_count,
            qs.total_worker_time / 1000 as total_cpu_time_ms,
            qs.total_elapsed_time / 1000 as total_elapsed_time_ms,
            qs.total_logical_reads,
            qs.total_physical_reads,
            SUBSTRING(st.text, (qs.statement_start_offset/2)+1,
                ((CASE qs.statement_end_offset
                    WHEN -1 THEN DATALENGTH(st.text)
                    ELSE qs.statement_end_offset
                END - qs.statement_start_offset)/2) + 1) as query_text
        FROM sys.dm_exec_query_stats qs
        CROSS APPLY sys.dm_exec_sql_text(qs.sql_handle) st
        WHERE st.text LIKE ?
        ORDER BY qs.total_elapsed_time DESC;
        """

        # 搜索类似查询的执行统计
        search_pattern = f"%{sql[:50].replace('[', '[[]').replace('%', '[%]')}%"
        results = execute_readonly_query(estimate_query, params=(search_pattern,), config=config, database=database)

        if results:
            return safe_json_dumps({"success": True, "sql": sql, "cached_plan_stats": results[0], "note": "显示的是缓存中类似查询的执行统计"})
        else:
            return safe_json_dumps({"success": True, "sql": sql, "message": "未找到缓存的执行计划,查询可能尚未执行过", "suggestion": "执行查询后可再次查看执行计划统计"})

    except Exception as e:
        return safe_json_dumps({"error": f"执行计划获取失败: {str(e)}", "sql": sql})


@tool()
def get_sample_data(
    table_name: str,
    schema_name: str = "dbo",
    limit: int = 5,
    columns: Optional[str] = None,
    database: Optional[str] = None,
    config: RunnableConfig = None,
):
    """
    获取表的示例数据,帮助理解数据格式和内容

    **⚠️ 安全要求 - 必须遵守:**
    1. **禁止返回敏感字段**: password, secret, token, key, credential, hash等
    2. **必须明确指定列**: 永远不要使用SELECT *
    3. **最小化数据**: 只查询回答问题所需的最少列数

    **何时使用此工具:**
    - 需要查看表中实际存储的数据样例
    - 了解数据格式以构建正确的查询条件
    - 验证表中是否有数据

    Args:
        table_name (str): 表名
        schema_name (str): schema名称,默认dbo
        limit (int): 返回行数,默认5,最大100
        columns (str, optional): **必填!** 逗号分隔的列名,如"id,username,email"
        database (str, optional): 数据库名,不填则使用默认数据库
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含示例数据
    """
    # 限制返回行数
    limit = min(max(1, limit), 100)

    # 验证表名和schema名(防止SQL注入)
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table_name):
        return safe_json_dumps({"error": "无效的表名"})
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", schema_name):
        return safe_json_dumps({"error": "无效的schema名"})

    # 敏感字段黑名单
    SENSITIVE_KEYWORDS = {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "key",
        "credential",
        "hash",
        "salt",
        "otp",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "private_key",
        "session_key",
        "encryption_key",
        "auth_token",
        "bearer",
        "jwt",
        "certificate",
        "cert",
        "passphrase",
        "pin",
        "cvv",
        "ssn",
    }

    # 处理列名
    if not columns or columns.strip() == "*":
        return safe_json_dumps(
            {
                "error": "安全限制: 必须明确指定需要查询的列名,禁止使用SELECT *。请使用get_table_schema_details查看表结构后,明确指定非敏感列。",
                "suggestion": "例如: columns='id,name,created_at'",
            }
        )

    # 验证列名并检测敏感字段
    column_list = [c.strip() for c in columns.split(",")]
    sensitive_columns = []
    valid_columns = []

    for col in column_list:
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", col):
            return safe_json_dumps({"error": f"无效的列名: {col}"})

        col_lower = col.lower()
        is_sensitive = any(keyword in col_lower for keyword in SENSITIVE_KEYWORDS)

        if is_sensitive:
            sensitive_columns.append(col)
        else:
            valid_columns.append(col)

    if sensitive_columns:
        return safe_json_dumps(
            {
                "error": f"安全限制: 禁止查询敏感字段: {', '.join(sensitive_columns)}",
                "sensitive_fields_detected": sensitive_columns,
                "valid_fields": valid_columns if valid_columns else "请指定其他非敏感字段",
                "suggestion": "请移除敏感字段,只查询必要的非敏感信息",
            }
        )

    if not valid_columns:
        return safe_json_dumps({"error": "未指定任何有效的非敏感列"})

    column_expr = ", ".join(valid_columns)

    query = f"SELECT TOP {limit} {column_expr} FROM {schema_name}.{table_name}"

    try:
        results = execute_readonly_query(query, config=config, database=database)

        return safe_json_dumps(
            {"success": True, "table": f"{schema_name}.{table_name}", "row_count": len(results), "limit": limit, "sample_data": results}
        )

    except Exception as e:
        return safe_json_dumps({"error": f"获取示例数据失败: {str(e)}", "table": f"{schema_name}.{table_name}"})
