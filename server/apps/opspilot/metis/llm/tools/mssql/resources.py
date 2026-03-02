"""MSSQL基础资源查询工具"""

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from apps.opspilot.metis.llm.tools.mssql.utils import execute_readonly_query, format_size, safe_json_dumps


@tool()
def get_current_database_info(config: RunnableConfig = None):
    """
    获取当前连接的数据库信息

    **何时使用此工具:**
    - 确认当前连接的是哪个数据库
    - 获取当前数据库的基本信息
    - 上下文感知,确保操作正确的数据库

    **工具能力:**
    - 显示当前数据库名称
    - 显示当前用户
    - 显示SQL Server版本
    - 显示服务器名称

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含当前数据库信息
    """
    query = """
    SELECT
        DB_NAME() as database_name,
        SUSER_NAME() as username,
        @@VERSION as sql_version,
        @@SERVERNAME as server_name,
        SERVERPROPERTY('Edition') as edition,
        SERVERPROPERTY('ProductVersion') as product_version
    """

    try:
        result = execute_readonly_query(query, config=config)[0]

        return safe_json_dumps(
            {
                "current_database": result["database_name"],
                "current_user": result["username"],
                "sql_version": result["sql_version"],
                "server_name": result["server_name"],
                "edition": result["edition"],
                "product_version": result["product_version"],
            }
        )
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def list_mssql_databases(config: RunnableConfig = None):
    """
    列出所有数据库及其基本信息

    **何时使用此工具:**
    - 用户询问"有哪些数据库"、"数据库列表"
    - 需要了解数据库大小、状态等信息
    - 巡检数据库资源使用情况

    **工具能力:**
    - 列出所有非系统数据库
    - 显示数据库大小、状态、恢复模式
    - 显示数据库排序规则

    **典型使用场景:**
    1. 快速查看所有数据库
    2. 检查数据库大小排行
    3. 查看数据库状态

    Args:
        config (RunnableConfig): 工具配置(自动传递)

    Returns:
        JSON格式,包含数据库列表,每个数据库包含:
        - name: 数据库名
        - size: 大小(格式化字符串)
        - size_bytes: 大小(字节)
        - state: 数据库状态
        - recovery_model: 恢复模式
        - collation: 排序规则
    """
    query = """
    SELECT
        d.name,
        d.database_id,
        d.state_desc as state,
        d.recovery_model_desc as recovery_model,
        d.collation_name as collation,
        CAST(SUM(mf.size) * 8 * 1024 AS BIGINT) as size_bytes
    FROM sys.databases d
    LEFT JOIN sys.master_files mf ON d.database_id = mf.database_id
    WHERE d.database_id > 4  -- 排除系统数据库
    GROUP BY d.name, d.database_id, d.state_desc, d.recovery_model_desc, d.collation_name
    ORDER BY size_bytes DESC;
    """

    try:
        results = execute_readonly_query(query, config=config)

        # 格式化大小
        for row in results:
            row["size"] = format_size(row["size_bytes"])

        return safe_json_dumps({"total_databases": len(results), "databases": results})
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def list_mssql_tables(database: str = None, schema_name: str = "dbo", config: RunnableConfig = None):
    """
    列出指定数据库中的表及其基本信息

    **何时使用此工具:**
    - 用户询问"有哪些表"、"表列表"
    - 查看表大小、行数等信息
    - 分析表空间占用

    **工具能力:**
    - 列出指定schema的所有表
    - 显示表大小(含索引)、行数
    - 显示索引数量

    Args:
        database (str, optional): 数据库名,不填则使用当前连接的数据库
        schema_name (str, optional): Schema名,默认dbo
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含表列表,每个表包含:
        - table_name: 表名
        - total_size: 总大小(含索引)
        - row_count: 行数
        - index_count: 索引数量
    """
    query = """
    SELECT
        t.name as table_name,
        s.name as schema_name,
        p.rows as row_count,
        CAST(SUM(a.total_pages) * 8 * 1024 AS BIGINT) as total_size_bytes,
        CAST(SUM(a.used_pages) * 8 * 1024 AS BIGINT) as used_size_bytes,
        (SELECT COUNT(*) FROM sys.indexes WHERE object_id = t.object_id AND type > 0) as index_count
    FROM sys.tables t
    INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
    INNER JOIN sys.partitions p ON t.object_id = p.object_id AND p.index_id IN (0, 1)
    INNER JOIN sys.allocation_units a ON p.partition_id = a.container_id
    WHERE s.name = ?
    GROUP BY t.name, s.name, t.object_id, p.rows
    ORDER BY SUM(a.total_pages) DESC;
    """

    try:
        results = execute_readonly_query(query, params=(schema_name,), config=config, database=database)

        # 格式化大小
        for row in results:
            row["total_size"] = format_size(row["total_size_bytes"])
            row["used_size"] = format_size(row["used_size_bytes"])

        return safe_json_dumps({"schema": schema_name, "database": database or "current", "total_tables": len(results), "tables": results})
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def list_mssql_indexes(database: str = None, table: str = None, schema_name: str = "dbo", config: RunnableConfig = None):
    """
    列出索引信息

    **何时使用此工具:**
    - 查看表的索引定义
    - 分析索引大小和使用情况
    - 排查索引相关问题

    **工具能力:**
    - 列出索引定义、大小
    - 显示索引类型和列
    - 识别未使用的索引

    Args:
        database (str, optional): 数据库名
        table (str, optional): 表名,不填则列出所有表的索引
        schema_name (str, optional): Schema名,默认dbo
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含索引列表
    """
    if table:
        query = """
        SELECT
            i.name as index_name,
            t.name as table_name,
            i.type_desc as index_type,
            i.is_unique,
            i.is_primary_key,
            CAST(SUM(ps.used_page_count) * 8 * 1024 AS BIGINT) as size_bytes,
            STUFF((
                SELECT ', ' + c.name
                FROM sys.index_columns ic
                INNER JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
                WHERE ic.object_id = i.object_id AND ic.index_id = i.index_id
                ORDER BY ic.key_ordinal
                FOR XML PATH('')
            ), 1, 2, '') as columns,
            us.user_seeks + us.user_scans + us.user_lookups as index_usage,
            us.user_updates as index_updates
        FROM sys.indexes i
        INNER JOIN sys.tables t ON i.object_id = t.object_id
        INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
        LEFT JOIN sys.dm_db_partition_stats ps ON i.object_id = ps.object_id AND i.index_id = ps.index_id
        LEFT JOIN sys.dm_db_index_usage_stats us ON i.object_id = us.object_id AND i.index_id = us.index_id
        WHERE s.name = ? AND t.name = ? AND i.name IS NOT NULL
        GROUP BY i.name, t.name, i.type_desc, i.is_unique, i.is_primary_key, i.object_id, i.index_id,
                 us.user_seeks, us.user_scans, us.user_lookups, us.user_updates
        ORDER BY size_bytes DESC;
        """
        params = (schema_name, table)
    else:
        query = """
        SELECT TOP 100
            i.name as index_name,
            t.name as table_name,
            i.type_desc as index_type,
            i.is_unique,
            i.is_primary_key,
            CAST(SUM(ps.used_page_count) * 8 * 1024 AS BIGINT) as size_bytes,
            us.user_seeks + us.user_scans + us.user_lookups as index_usage,
            us.user_updates as index_updates
        FROM sys.indexes i
        INNER JOIN sys.tables t ON i.object_id = t.object_id
        INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
        LEFT JOIN sys.dm_db_partition_stats ps ON i.object_id = ps.object_id AND i.index_id = ps.index_id
        LEFT JOIN sys.dm_db_index_usage_stats us ON i.object_id = us.object_id AND i.index_id = us.index_id
        WHERE s.name = ? AND i.name IS NOT NULL
        GROUP BY i.name, t.name, i.type_desc, i.is_unique, i.is_primary_key,
                 us.user_seeks, us.user_scans, us.user_lookups, us.user_updates
        ORDER BY size_bytes DESC;
        """
        params = (schema_name,)

    try:
        results = execute_readonly_query(query, params=params, config=config, database=database)

        # 格式化大小
        for row in results:
            row["size"] = format_size(row["size_bytes"])
            row["is_unused"] = (row["index_usage"] or 0) == 0

        return safe_json_dumps({"schema": schema_name, "table": table, "total_indexes": len(results), "indexes": results})
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def list_mssql_schemas(database: str = None, config: RunnableConfig = None):
    """
    列出所有Schema

    **何时使用此工具:**
    - 查看数据库中的Schema列表
    - 了解Schema的所有者
    - 探索数据库结构

    **工具能力:**
    - 列出指定数据库的所有schema(排除系统schema)
    - 显示每个schema的所有者
    - 统计每个schema下的表数量

    Args:
        database (str, optional): 数据库名,不填则使用当前连接的数据库
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含Schema列表
    """
    query = """
    SELECT
        s.name as schema_name,
        p.name as owner,
        (SELECT COUNT(*) FROM sys.tables t WHERE t.schema_id = s.schema_id) as table_count
    FROM sys.schemas s
    INNER JOIN sys.database_principals p ON s.principal_id = p.principal_id
    WHERE s.name NOT IN ('sys', 'INFORMATION_SCHEMA', 'guest', 'db_owner', 'db_accessadmin',
                         'db_securityadmin', 'db_ddladmin', 'db_backupoperator', 'db_datareader',
                         'db_datawriter', 'db_denydatareader', 'db_denydatawriter')
    ORDER BY s.name;
    """

    try:
        results = execute_readonly_query(query, config=config, database=database)

        return safe_json_dumps({"database": database or "current", "total_schemas": len(results), "schemas": results})
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def get_table_structure(table: str, schema_name: str = "dbo", config: RunnableConfig = None):
    """
    获取表结构详情

    **何时使用此工具:**
    - 查看表的列定义、数据类型
    - 了解表的约束、主键、外键
    - 分析表结构设计

    **工具能力:**
    - 列出所有列及类型、默认值、是否可空
    - 显示主键、唯一约束、外键
    - 显示检查约束

    Args:
        table (str): 表名(必填)
        schema_name (str, optional): Schema名,默认dbo
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含表结构详情
    """
    # 查询列信息
    columns_query = """
    SELECT
        c.name as column_name,
        t.name as data_type,
        c.max_length,
        c.precision,
        c.scale,
        c.is_nullable,
        OBJECT_DEFINITION(c.default_object_id) as column_default,
        c.is_identity
    FROM sys.columns c
    INNER JOIN sys.types t ON c.user_type_id = t.user_type_id
    INNER JOIN sys.tables tb ON c.object_id = tb.object_id
    INNER JOIN sys.schemas s ON tb.schema_id = s.schema_id
    WHERE s.name = ? AND tb.name = ?
    ORDER BY c.column_id;
    """

    # 查询约束信息
    constraints_query = """
    SELECT
        kc.name as constraint_name,
        CASE
            WHEN pk.object_id IS NOT NULL THEN 'PRIMARY KEY'
            WHEN uq.object_id IS NOT NULL THEN 'UNIQUE'
            WHEN fk.object_id IS NOT NULL THEN 'FOREIGN KEY'
            WHEN cc.object_id IS NOT NULL THEN 'CHECK'
        END as constraint_type,
        COL_NAME(kc.parent_object_id, kc.parent_column_id) as column_name,
        OBJECT_NAME(fk.referenced_object_id) as foreign_table_name,
        COL_NAME(fk.referenced_object_id, fkc.referenced_column_id) as foreign_column_name
    FROM sys.key_constraints kc
    INNER JOIN sys.tables t ON kc.parent_object_id = t.object_id
    INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
    LEFT JOIN sys.indexes pk ON kc.parent_object_id = pk.object_id AND kc.unique_index_id = pk.index_id AND pk.is_primary_key = 1
    LEFT JOIN sys.indexes uq ON kc.parent_object_id = uq.object_id AND kc.unique_index_id = uq.index_id AND uq.is_unique = 1 AND uq.is_primary_key = 0
    LEFT JOIN sys.foreign_keys fk ON kc.parent_object_id = fk.parent_object_id
    LEFT JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
    LEFT JOIN sys.check_constraints cc ON kc.parent_object_id = cc.parent_object_id
    WHERE s.name = ? AND t.name = ?
    UNION ALL
    SELECT
        fk.name as constraint_name,
        'FOREIGN KEY' as constraint_type,
        COL_NAME(fkc.parent_object_id, fkc.parent_column_id) as column_name,
        OBJECT_NAME(fk.referenced_object_id) as foreign_table_name,
        COL_NAME(fk.referenced_object_id, fkc.referenced_column_id) as foreign_column_name
    FROM sys.foreign_keys fk
    INNER JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
    INNER JOIN sys.tables t ON fk.parent_object_id = t.object_id
    INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = ? AND t.name = ?;
    """

    try:
        columns = execute_readonly_query(columns_query, params=(schema_name, table), config=config)
        constraints = execute_readonly_query(constraints_query, params=(schema_name, table, schema_name, table), config=config)

        return safe_json_dumps({"schema": schema_name, "table": table, "columns": columns, "constraints": constraints})
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def list_mssql_logins(config: RunnableConfig = None):
    """
    列出数据库登录账户信息

    **何时使用此工具:**
    - 查看所有登录账户列表
    - 了解账户权限和属性
    - 审计用户权限配置

    **工具能力:**
    - 列出所有登录账户
    - 显示账户属性(类型、是否禁用等)
    - 显示默认数据库

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含登录账户列表
    """
    query = """
    SELECT
        name as login_name,
        type_desc as login_type,
        is_disabled,
        default_database_name,
        create_date,
        modify_date
    FROM sys.server_principals
    WHERE type IN ('S', 'U', 'G')  -- SQL登录、Windows用户、Windows组
    ORDER BY name;
    """

    try:
        results = execute_readonly_query(query, config=config)

        # 格式化日期
        for row in results:
            row["create_date"] = str(row["create_date"]) if row["create_date"] else None
            row["modify_date"] = str(row["modify_date"]) if row["modify_date"] else None

        return safe_json_dumps({"total_logins": len(results), "logins": results})
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def get_database_config(config: RunnableConfig = None):
    """
    获取数据库配置参数

    **何时使用此工具:**
    - 查看数据库配置参数
    - 审查性能相关配置
    - 对比配置建议

    **工具能力:**
    - 列出关键配置参数及当前值
    - 显示内存、连接、并行度等配置
    - 显示参数值和类型

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含配置参数列表
    """
    query = """
    SELECT
        name,
        value,
        value_in_use,
        minimum,
        maximum,
        description,
        is_dynamic,
        is_advanced
    FROM sys.configurations
    WHERE name IN (
        'max server memory (MB)', 'min server memory (MB)',
        'max degree of parallelism', 'cost threshold for parallelism',
        'max worker threads', 'user connections',
        'remote query timeout (s)', 'query wait (s)',
        'recovery interval (min)', 'fill factor (%)'
    )
    ORDER BY name;
    """

    try:
        results = execute_readonly_query(query, config=config)

        return safe_json_dumps({"total_settings": len(results), "settings": results})
    except Exception as e:
        return safe_json_dumps({"error": str(e)})
