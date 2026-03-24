"""PostgreSQL动态SQL查询工具 - 安全的动态查询生成和执行"""

import re
from typing import Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.postgres.utils import execute_readonly_query, safe_json_dumps


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
        "call",
        "execute",
        "copy",
        "set",
        "reset",
        "vacuum",
        "analyze",
        "cluster",
        "reindex",
        "lock",
        "pg_terminate_backend",
        "pg_cancel_backend",
    ]

    for keyword in forbidden_keywords:
        # 使用单词边界检查,避免误判(如 inserted_at 字段名)
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
def get_table_schema_details(table_name: str, schema_name: str = "public", database: Optional[str] = None, config: RunnableConfig = None):
    """
    获取表的详细结构信息,用于构建动态查询和理解数据关系

    **何时使用此工具:**
    - 需要了解表的完整列信息以构建SELECT查询
    - 需要知道字段类型以构建WHERE条件和JOIN条件
    - 需要了解索引以优化查询性能
    - 需要通过外键理解表之间的关系和层级结构
    - 分析业务实体之间的关联关系(如:知识库→文档→分块)

    **工具能力:**
    - 获取所有列名、类型、是否可空、默认值
    - 获取主键和外键信息(用于JOIN和理解表关系)
    - 获取索引信息(优化查询性能)
    - 获取列注释(理解业务含义)
    - 获取表统计信息(行数估算)

    **业务理解提示:**
    - 外键字段(如xxx_id)通常指向父表,用于关联查询
    - 主键通常是业务实体的唯一标识
    - 表名模式(如prefix_entityname)可能表示业务模块
    - 相同前缀的表可能属于同一业务域

    Args:
        table_name (str): 表名
        schema_name (str): schema名称,默认public
        database (str, optional): 数据库名,不填则使用默认数据库
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含表结构的详细信息,包括:
        - table_info: 表基本信息(行数估算、大小)
        - columns: 列详细信息(名称、类型、约束、注释)
        - indexes: 索引信息(名称、列、是否唯一)
        - foreign_keys: 外键信息(关联的表和列)
    """
    query = """
    WITH table_info AS (
        SELECT
            c.relname as table_name,
            c.reltuples::bigint as estimated_rows,
            pg_size_pretty(pg_total_relation_size(c.oid)) as total_size
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = %s AND c.relname = %s
    ),
    columns_info AS (
        SELECT
            a.attname as column_name,
            a.attnum as column_position,
            pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type,
            NOT a.attnotnull as is_nullable,
            pg_get_expr(d.adbin, d.adrelid) as column_default,
            col_description(a.attrelid, a.attnum) as column_comment,
            CASE
                WHEN pk.conkey IS NOT NULL AND a.attnum = ANY(pk.conkey) THEN true
                ELSE false
            END as is_primary_key
        FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
        LEFT JOIN pg_constraint pk ON pk.conrelid = c.oid AND pk.contype = 'p'
        WHERE n.nspname = %s
            AND c.relname = %s
            AND a.attnum > 0
            AND NOT a.attisdropped
        ORDER BY a.attnum
    ),
    indexes_info AS (
        SELECT
            i.relname as index_name,
            ix.indisunique as is_unique,
            ix.indisprimary as is_primary,
            array_agg(a.attname ORDER BY array_position(ix.indkey, a.attnum)) as columns
        FROM pg_index ix
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_class c ON c.oid = ix.indrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum = ANY(ix.indkey)
        WHERE n.nspname = %s AND c.relname = %s
        GROUP BY i.relname, ix.indisunique, ix.indisprimary
    ),
    foreign_keys AS (
        SELECT
            con.conname as constraint_name,
            array_agg(att.attname) as columns,
            fn.nspname as foreign_schema,
            fc.relname as foreign_table,
            array_agg(fatt.attname) as foreign_columns
        FROM pg_constraint con
        JOIN pg_class c ON con.conrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        JOIN pg_attribute att ON att.attrelid = c.oid AND att.attnum = ANY(con.conkey)
        JOIN pg_class fc ON con.confrelid = fc.oid
        JOIN pg_namespace fn ON fc.relnamespace = fn.oid
        JOIN pg_attribute fatt ON fatt.attrelid = fc.oid AND fatt.attnum = ANY(con.confkey)
        WHERE n.nspname = %s
            AND c.relname = %s
            AND con.contype = 'f'
        GROUP BY con.conname, fn.nspname, fc.relname
    )
    SELECT
        json_build_object(
            'table_info', (SELECT row_to_json(t) FROM table_info t),
            'columns', (SELECT json_agg(row_to_json(c)) FROM columns_info c),
            'indexes', (SELECT json_agg(row_to_json(i)) FROM indexes_info i),
            'foreign_keys', (SELECT json_agg(row_to_json(fk)) FROM foreign_keys fk)
        ) as schema_details
    """

    try:
        result = execute_readonly_query(
            query,
            params=(schema_name, table_name, schema_name, table_name, schema_name, table_name, schema_name, table_name),
            config=config,
            database=database,
        )

        if not result:
            return safe_json_dumps({"error": f"表 {schema_name}.{table_name} 不存在"})

        return safe_json_dumps(result[0]["schema_details"])

    except Exception as e:
        return safe_json_dumps({"error": f"获取表结构失败: {str(e)}"})


@tool()
def search_tables_by_keyword(keyword: str, search_in_comments: bool = True, database: Optional[str] = None, config: RunnableConfig = None):
    """
    根据关键字搜索相关的表和列,帮助发现业务实体及其数据存储位置

    **何时使用此工具:**
    - 不确定业务数据存储在哪个表中(如:知识库、用户、订单)
    - 根据业务关键词查找相关表(如:knowledge→知识库相关表)
    - 查找包含特定列名的表(如:user_id→用户关联表)
    - 探索业务模块的表结构(如:搜索"payment"找支付相关表)

    **工具能力:**
    - 在表名中搜索关键字(返回匹配的表)
    - 在列名中搜索关键字(返回包含该列的表)
    - 在表注释中搜索关键字(业务说明匹配)
    - 返回匹配表的预估行数(了解数据规模)

    **搜索策略提示:**
    - 使用业务术语搜索(如:知识库→knowledge)
    - 使用实体关系词搜索(如:文档→document)
    - 使用关联词搜索(如:chunk→分块)
    - 结果会标注匹配类型(表名匹配/列名匹配)

    **工具能力:**
    - 在表名中搜索关键字
    - 在列名中搜索关键字
    - 在表注释中搜索关键字
    - 在列注释中搜索关键字
    - 返回匹配的表和列信息

    Args:
        keyword (str): 搜索关键字
        search_in_comments (bool): 是否在注释中搜索,默认True
        database (str, optional): 数据库名,不填则使用默认数据库
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含匹配的表和列信息
    """
    # 构建搜索条件
    comment_condition = ""
    if search_in_comments:
        comment_condition = """
            OR obj_description(c.oid, 'pg_class') ILIKE %s
            OR col_description(a.attrelid, a.attnum) ILIKE %s
        """

    query = f"""
    WITH matching_tables AS (
        SELECT DISTINCT
            n.nspname as schema_name,
            c.relname as table_name,
            obj_description(c.oid, 'pg_class') as table_comment,
            c.reltuples::bigint as estimated_rows,
            CASE
                WHEN c.relname ILIKE %s THEN 'table_name'
                WHEN obj_description(c.oid, 'pg_class') ILIKE %s THEN 'table_comment'
                ELSE 'column'
            END as match_type
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        LEFT JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
        WHERE c.relkind = 'r'
            AND n.nspname NOT IN ('pg_catalog', 'information_schema')
            AND (
                c.relname ILIKE %s
                OR a.attname ILIKE %s
                {comment_condition}
            )
    ),
    matching_columns AS (
        SELECT
            n.nspname as schema_name,
            c.relname as table_name,
            a.attname as column_name,
            pg_catalog.format_type(a.atttypid, a.atttypmod) as data_type,
            col_description(a.attrelid, a.attnum) as column_comment,
            CASE
                WHEN a.attname ILIKE %s THEN 'column_name'
                WHEN col_description(a.attrelid, a.attnum) ILIKE %s THEN 'column_comment'
                ELSE 'other'
            END as match_type
        FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE c.relkind = 'r'
            AND n.nspname NOT IN ('pg_catalog', 'information_schema')
            AND a.attnum > 0
            AND NOT a.attisdropped
            AND (
                a.attname ILIKE %s
                {("OR col_description(a.attrelid, a.attnum) ILIKE %s" if search_in_comments else "")}
            )
    )
    SELECT
        mt.schema_name,
        mt.table_name,
        mt.table_comment,
        mt.estimated_rows,
        mt.match_type as table_match_type,
        json_agg(
            json_build_object(
                'column_name', mc.column_name,
                'data_type', mc.data_type,
                'column_comment', mc.column_comment,
                'match_type', mc.match_type
            ) ORDER BY mc.column_name
        ) FILTER (WHERE mc.column_name IS NOT NULL) as matching_columns
    FROM matching_tables mt
    LEFT JOIN matching_columns mc ON mc.schema_name = mt.schema_name AND mc.table_name = mt.table_name
    GROUP BY mt.schema_name, mt.table_name, mt.table_comment, mt.estimated_rows, mt.match_type
    ORDER BY mt.estimated_rows DESC NULLS LAST
    LIMIT 50
    """

    # 构建参数
    search_pattern = f"%{keyword}%"
    if search_in_comments:
        params = (
            search_pattern,
            search_pattern,  # match_type条件
            search_pattern,
            search_pattern,
            search_pattern,
            search_pattern,  # WHERE条件
            search_pattern,
            search_pattern,  # matching_columns的match_type
            search_pattern,
            search_pattern,  # matching_columns的WHERE
        )
    else:
        params = (
            search_pattern,
            search_pattern,  # match_type条件
            search_pattern,
            search_pattern,  # WHERE条件
            search_pattern,
            search_pattern,  # matching_columns的match_type
            search_pattern,  # matching_columns的WHERE
        )

    try:
        results = execute_readonly_query(query, params=params, config=config, database=database)

        return safe_json_dumps({"keyword": keyword, "total_matches": len(results), "tables": results})

    except Exception as e:
        return safe_json_dumps({"error": f"搜索失败: {str(e)}"})


@tool()
def execute_safe_select(sql: str, limit: int = 100, database: Optional[str] = None, config: RunnableConfig = None):
    """
    执行安全的SELECT查询,支持聚合统计、多表关联等复杂查询

    **[警告] 安全要求 - 构建SQL时必须遵守:**
    1. **禁止SELECT ***: 必须明确列出需要的列名
    2. **避免敏感字段**: 不要查询password, secret, token, key, hash, otp等敏感字段
    3. **最小化查询**: 只查询回答问题所需的最少列和行
    4. **使用WHERE过滤**: 合理使用WHERE条件减少数据量
    5. **谨慎JOIN**: 确保JOIN不会导致数据泄露或性能问题

    **安全机制:**
    - 只允许SELECT和WITH查询
    - 禁止所有写操作(INSERT/UPDATE/DELETE等)
    - 禁止DDL操作(CREATE/DROP/ALTER等)
    - 禁止多语句执行
    - 自动添加LIMIT限制(聚合查询除外)
    - 使用只读事务
    - SQL安全验证

    **何时使用此工具:**
    - 执行动态生成的SELECT查询
    - 根据schema信息构建并执行查询
    - 统计聚合数据(COUNT, SUM, AVG等)
    - 多表关联查询(JOIN, 子查询)
    - 验证查询结果

    **工具能力:**
    - 执行复杂的SELECT查询(支持JOIN、子查询、CTE等)
    - 支持聚合函数和GROUP BY统计
    - 支持多表关联和外键JOIN
    - 自动限制返回行数(明细查询)
    - 安全验证SQL语句
    - 返回结构化的查询结果

    **SQL编写规范:**

    [正确] **明细查询示例:**
    ```sql
    SELECT id, name, created_at FROM knowledge_base WHERE status = 'active'
    ```

    [正确] **聚合统计示例:**
    ```sql
    SELECT kb.id, kb.name, COUNT(d.id) as doc_count
    FROM knowledge_base kb
    LEFT JOIN document d ON d.knowledge_base_id = kb.id
    GROUP BY kb.id, kb.name
    ```

    [正确] **多层关联示例:**
    ```sql
    SELECT
        kb.id as kb_id,
        kb.name as kb_name,
        COUNT(DISTINCT d.id) as doc_count,
        COUNT(c.id) as chunk_count
    FROM knowledge_base kb
    LEFT JOIN document d ON d.kb_id = kb.id
    LEFT JOIN chunk c ON c.document_id = d.id
    GROUP BY kb.id, kb.name
    ```

    [错误] **错误示例:**
    - `SELECT * FROM users` (包含敏感字段)
    - `SELECT password, otp_secret FROM users` (查询敏感字段)
    - `SELECT id FROM large_table` (缺少WHERE过滤,数据量过大)

    **业务查询思路提示:**
    - 需要统计数量时,使用 COUNT() 函数
    - 需要分组统计时,使用 GROUP BY
    - 需要关联数据时,根据外键字段使用 JOIN
    - 父子关系通常是 parent.id = child.parent_id
    - 多对多关系通常通过中间表关联

    Args:
        sql (str): SELECT SQL语句 - 必须明确指定列名,禁止使用*
        limit (int): 最大返回行数,默认100,最大1000(聚合查询忽略此参数)
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
    sql_normalized = " ".join(sql.lower().split())  # 规范化空白字符
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
        # 检测是否在SELECT子句中出现敏感关键词
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
    limit = min(max(1, limit), 1000)  # 1-1000之间

    # 移除末尾分号
    sql = sql.rstrip().rstrip(";")

    # 检查是否已有LIMIT子句
    sql_lower = sql.lower()
    if "limit" not in sql_lower:
        sql = f"{sql} LIMIT {limit}"
    else:
        # 如果已有LIMIT,确保不超过最大值
        limit_match = re.search(r"limit\s+(\d+)", sql_lower)
        if limit_match:
            existing_limit = int(limit_match.group(1))
            if existing_limit > limit:
                sql = re.sub(r"limit\s+\d+", f"LIMIT {limit}", sql, flags=re.IGNORECASE)

    try:
        results = execute_readonly_query(sql, config=config, database=database)

        return safe_json_dumps({"success": True, "row_count": len(results), "limit": limit, "sql": sql, "data": results})

    except Exception as e:
        return safe_json_dumps({"error": f"查询执行失败: {str(e)}", "sql": sql})


@tool()
def explain_query_plan(sql: str, analyze: bool = False, database: Optional[str] = None, config: RunnableConfig = None):
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
    - 可选执行EXPLAIN ANALYZE(实际执行并获取真实统计)

    Args:
        sql (str): 要分析的SELECT SQL语句
        analyze (bool): 是否执行EXPLAIN ANALYZE(会实际执行查询),默认False
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

    # 构建EXPLAIN查询
    if analyze:
        explain_sql = f"EXPLAIN (ANALYZE, VERBOSE, BUFFERS, FORMAT JSON) {sql}"
    else:
        explain_sql = f"EXPLAIN (VERBOSE, FORMAT JSON) {sql}"

    try:
        results = execute_readonly_query(explain_sql, config=config, database=database)

        plan = results[0]["QUERY PLAN"][0]

        response = {"success": True, "sql": sql, "execution_plan": plan}

        # 提取关键指标
        if "Plan" in plan:
            plan_info = plan["Plan"]
            response["summary"] = {
                "total_cost": plan_info.get("Total Cost"),
                "estimated_rows": plan_info.get("Plan Rows"),
                "estimated_width": plan_info.get("Plan Width"),
            }

            if analyze:
                response["summary"].update(
                    {
                        "actual_time_ms": plan_info.get("Actual Total Time"),
                        "actual_rows": plan_info.get("Actual Rows"),
                        "execution_time_ms": plan.get("Execution Time"),
                        "planning_time_ms": plan.get("Planning Time"),
                    }
                )

        return safe_json_dumps(response)

    except Exception as e:
        return safe_json_dumps({"error": f"执行计划获取失败: {str(e)}", "sql": sql})


@tool()
def get_sample_data(
    table_name: str,
    schema_name: str = "public",
    limit: int = 5,
    columns: Optional[str] = None,
    database: Optional[str] = None,
    config: RunnableConfig = None,
):
    """
    获取表的示例数据,帮助理解数据格式和内容

    **[警告] 安全要求 - 必须遵守:**
    1. **禁止返回敏感字段**: password, secret, token, key, credential, hash, salt, otp等
    2. **必须明确指定列**: 永远不要使用SELECT *,必须在columns参数中列出需要的具体列名
    3. **最小化数据**: 只查询回答问题所需的最少列数
    4. **优先查询非敏感列**: id, name, username, email(部分脱敏), status, created_at等

    **何时使用此工具:**
    - 需要查看表中实际存储的数据样例(非敏感字段)
    - 了解数据格式以构建正确的查询条件
    - 验证表中是否有数据
    - 理解字段的实际值范围

    **工具能力:**
    - 获取表的前N行数据
    - 必须明确指定需要的列(columns参数)
    - 自动过滤敏感字段
    - 安全限制返回行数

    **最佳实践:**
    - 查询用户表时,只选择: id, username, display_name, email, disabled, last_login等
    - 避免查询: password, otp_secret, api_key, token等敏感字段
    - 优先使用get_table_schema_details了解表结构,然后精确指定需要的列

    Args:
        table_name (str): 表名
        schema_name (str): schema名称,默认public
        limit (int): 返回行数,默认5,最大100
        columns (str, optional): **必填!** 逗号分隔的列名,如"id,username,email,created_at"。禁止不填或使用*
        database (str, optional): 数据库名,不填则使用默认数据库
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含示例数据(已过滤敏感字段)
    """
    # 限制返回行数
    limit = min(max(1, limit), 100)

    # 验证表名和schema名(防止SQL注入)
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", table_name):
        return safe_json_dumps({"error": "无效的表名"})
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", schema_name):
        return safe_json_dumps({"error": "无效的schema名"})

    # 敏感字段黑名单(小写)
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
        "credit_card",
        "bank_account",
        "routing_number",
    }

    # 处理列名
    if not columns or columns.strip() == "*":
        return safe_json_dumps(
            {
                "error": "安全限制: 必须明确指定需要查询的列名,禁止使用SELECT *。请使用get_table_schema_details查看表结构后,明确指定非敏感列。",
                "suggestion": "例如: columns='id,name,created_at,updated_at'",
            }
        )

    # 验证列名并检测敏感字段
    column_list = [c.strip() for c in columns.split(",")]
    sensitive_columns = []
    valid_columns = []

    for col in column_list:
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", col):
            return safe_json_dumps({"error": f"无效的列名: {col}"})

        # 检查是否为敏感字段
        col_lower = col.lower()
        is_sensitive = any(keyword in col_lower for keyword in SENSITIVE_KEYWORDS)

        if is_sensitive:
            sensitive_columns.append(col)
        else:
            valid_columns.append(col)

    # 如果有敏感字段,返回警告
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

    # 使用参数化查询防止注入
    # 注意: 表名和列名不能参数化,但已通过正则验证
    query = f"""
    SELECT {column_expr}
    FROM {schema_name}.{table_name}
    LIMIT %s
    """

    try:
        results = execute_readonly_query(query, params=(limit,), config=config, database=database)

        return safe_json_dumps(
            {"success": True, "table": f"{schema_name}.{table_name}", "row_count": len(results), "limit": limit, "sample_data": results}
        )

    except Exception as e:
        return safe_json_dumps({"error": f"获取示例数据失败: {str(e)}", "table": f"{schema_name}.{table_name}"})
