"""PostgreSQL基础资源查询工具"""
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from apps.opspilot.metis.llm.tools.postgres.utils import (
    execute_readonly_query,
    safe_json_dumps,
    format_size,
)


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
    - 显示PostgreSQL版本
    - 显示当前schema搜索路径

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含当前数据库信息
    """
    query = """
    SELECT 
        current_database() as database_name,
        current_user as username,
        version() as pg_version,
        current_schema() as current_schema,
        (SELECT string_agg(nspname, ', ') FROM pg_namespace WHERE nspname = ANY(current_schemas(false))) as search_path
    """

    try:
        result = execute_readonly_query(query, config=config)[0]

        return safe_json_dumps({
            "current_database": result["database_name"],
            "current_user": result["username"],
            "postgres_version": result["pg_version"],
            "current_schema": result["current_schema"],
            "search_path": result["search_path"]
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def list_postgres_databases(config: RunnableConfig = None):
    """
    列出所有数据库及其基本信息

    **何时使用此工具:**
    - 用户询问"有哪些数据库"、"数据库列表"
    - 需要了解数据库大小、连接数等信息
    - 巡检数据库资源使用情况

    **工具能力:**
    - 列出所有非模板数据库
    - 显示数据库大小、连接数、所有者
    - 显示数据库编码和排序规则

    **典型使用场景:**
    1. 快速查看所有数据库
    2. 检查数据库大小排行
    3. 查看活跃连接数

    Args:
        config (RunnableConfig): 工具配置(自动传递)

    Returns:
        JSON格式,包含数据库列表,每个数据库包含:
        - name: 数据库名
        - size: 大小(格式化字符串)
        - size_bytes: 大小(字节)
        - connections: 当前连接数
        - owner: 所有者
        - encoding: 编码
        - collate: 排序规则
    """
    query = """
    SELECT 
        d.datname as name,
        pg_database_size(d.datname) as size_bytes,
        (SELECT count(*) FROM pg_stat_activity WHERE datname = d.datname) as connections,
        pg_catalog.pg_get_userbyid(d.datdba) as owner,
        pg_encoding_to_char(d.encoding) as encoding,
        d.datcollate as collate
    FROM pg_catalog.pg_database d
    WHERE d.datistemplate = false
    ORDER BY pg_database_size(d.datname) DESC;
    """

    try:
        results = execute_readonly_query(query, config=config)

        # 格式化大小
        for row in results:
            row["size"] = format_size(row["size_bytes"])

        return safe_json_dumps({
            "total_databases": len(results),
            "databases": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def list_postgres_tables(database: str = None, schema_name: str = "public", config: RunnableConfig = None):
    """
    列出指定数据库中的表及其基本信息

    **何时使用此工具:**
    - 用户询问“有哪些表”、“表列表”
    - 查看表大小、行数等信息
    - 分析表空间占用

    **工具能力:**
    - 列出指定schema的所有表
    - 显示表大小(含索引)、估计行数
    - 显示索引数量、最后分析时间

    Args:
        database (str, optional): 数据库名,不填则使用当前连接的数据库
        schema_name (str, optional): Schema名,默认public
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含表列表,每个表包含:
        - table_name: 表名
        - total_size: 总大小(含索引)
        - table_size: 表大小
        - indexes_size: 索引大小
        - row_estimate: 估计行数
        - index_count: 索引数量
        - last_analyze: 最后分析时间
    """
    query = """
    SELECT 
        t.tablename as table_name,
        pg_total_relation_size(quote_ident(t.schemaname)||'.'||quote_ident(t.tablename)) as total_size_bytes,
        pg_relation_size(quote_ident(t.schemaname)||'.'||quote_ident(t.tablename)) as table_size_bytes,
        pg_indexes_size(quote_ident(t.schemaname)||'.'||quote_ident(t.tablename)) as indexes_size_bytes,
        s.n_live_tup as row_estimate,
        (SELECT count(*) FROM pg_indexes WHERE schemaname = t.schemaname AND tablename = t.tablename) as index_count,
        s.last_analyze
    FROM pg_catalog.pg_tables t
    LEFT JOIN pg_stat_user_tables s ON t.schemaname = s.schemaname AND t.tablename = s.relname
    WHERE t.schemaname = %s
    ORDER BY pg_total_relation_size(quote_ident(t.schemaname)||'.'||quote_ident(t.tablename)) DESC;
    """

    try:
        results = execute_readonly_query(
            query, params=(schema_name,), config=config, database=database)

        # 格式化大小
        for row in results:
            row["total_size"] = format_size(row["total_size_bytes"])
            row["table_size"] = format_size(row["table_size_bytes"])
            row["indexes_size"] = format_size(row["indexes_size_bytes"])
            row["last_analyze"] = str(
                row["last_analyze"]) if row["last_analyze"] else "Never"

        return safe_json_dumps({
            "schema": schema_name,
            "database": database or "current",
            "total_tables": len(results),
            "tables": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def list_postgres_indexes(database: str = None, table: str = None, schema_name: str = "public", config: RunnableConfig = None):
    """
    列出索引信息

    **何时使用此工具:**
    - 查看表的索引定义
    - 分析索引大小和使用情况
    - 排查索引相关问题

    **工具能力:**
    - 列出索引定义、大小
    - 显示索引扫描次数和读取行数
    - 识别未使用的索引

    Args:
        database (str, optional): 数据库名
        table (str, optional): 表名,不填则列出所有表的索引
        schema_name (str, optional): Schema名,默认public
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含索引列表
    """
    if table:
        query = """
        SELECT 
            i.indexname as index_name,
            i.tablename as table_name,
            pg_relation_size(quote_ident(i.schemaname)||'.'||quote_ident(i.indexname)) as size_bytes,
            i.indexdef as definition,
            s.idx_scan as index_scans,
            s.idx_tup_read as tuples_read,
            s.idx_tup_fetch as tuples_fetched
        FROM pg_catalog.pg_indexes i
        LEFT JOIN pg_stat_user_indexes s ON i.schemaname = s.schemaname 
            AND i.tablename = s.relname 
            AND i.indexname = s.indexrelname
        WHERE i.schemaname = %s AND i.tablename = %s
        ORDER BY pg_relation_size(quote_ident(i.schemaname)||'.'||quote_ident(i.indexname)) DESC;
        """
        params = (schema_name, table)
    else:
        query = """
        SELECT 
            i.indexname as index_name,
            i.tablename as table_name,
            pg_relation_size(quote_ident(i.schemaname)||'.'||quote_ident(i.indexname)) as size_bytes,
            i.indexdef as definition,
            s.idx_scan as index_scans,
            s.idx_tup_read as tuples_read,
            s.idx_tup_fetch as tuples_fetched
        FROM pg_catalog.pg_indexes i
        LEFT JOIN pg_stat_user_indexes s ON i.schemaname = s.schemaname 
            AND i.tablename = s.relname 
            AND i.indexname = s.indexrelname
        WHERE i.schemaname = %s
        ORDER BY pg_relation_size(quote_ident(i.schemaname)||'.'||quote_ident(i.indexname)) DESC;
        """
        params = (schema_name,)

    try:
        results = execute_readonly_query(query, params=params, config=config)

        # 格式化大小
        for row in results:
            row["size"] = format_size(row["size_bytes"])
            row["is_unused"] = (row["index_scans"] or 0) == 0

        return safe_json_dumps({
            "schema": schema_name,
            "table": table,
            "total_indexes": len(results),
            "indexes": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def list_postgres_schemas(database: str = None, config: RunnableConfig = None):
    """
    列出所有Schema

    **何时使用此工具:**
    - 查看数据库中的Schema列表
    - 了解Schema的所有者和权限
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
        nspname as schema_name,
        pg_catalog.pg_get_userbyid(nspowner) as owner,
        (SELECT count(*) FROM pg_tables WHERE schemaname = nspname) as table_count
    FROM pg_catalog.pg_namespace
    WHERE nspname !~ '^pg_' AND nspname <> 'information_schema'
    ORDER BY nspname;
    """

    try:
        results = execute_readonly_query(
            query, config=config, database=database)

        return safe_json_dumps({
            "database": database or "current",
            "total_schemas": len(results),
            "schemas": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def get_table_structure(table: str, schema_name: str = "public", config: RunnableConfig = None):
    """
    获取表结构详情

    **何时使用此工具:**
    - 查看表的列定义、数据类型
    - 了解表的约束、主键、外键
    - 分析表结构设计

    **工具能力:**
    - 列出所有列及类型、默认值、是否可空
    - 显示主键、唯一约束、外键
    - 显示检查约束和触发器

    Args:
        table (str): 表名(必填)
        schema_name (str, optional): Schema名,默认public
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含表结构详情
    """
    # 查询列信息
    columns_query = """
    SELECT 
        column_name,
        data_type,
        character_maximum_length,
        is_nullable,
        column_default
    FROM information_schema.columns
    WHERE table_schema = %s AND table_name = %s
    ORDER BY ordinal_position;
    """

    # 查询约束信息
    constraints_query = """
    SELECT 
        tc.constraint_name,
        tc.constraint_type,
        kcu.column_name,
        ccu.table_name AS foreign_table_name,
        ccu.column_name AS foreign_column_name
    FROM information_schema.table_constraints AS tc
    LEFT JOIN information_schema.key_column_usage AS kcu
        ON tc.constraint_name = kcu.constraint_name
        AND tc.table_schema = kcu.table_schema
    LEFT JOIN information_schema.constraint_column_usage AS ccu
        ON ccu.constraint_name = tc.constraint_name
        AND ccu.table_schema = tc.table_schema
    WHERE tc.table_schema = %s AND tc.table_name = %s;
    """

    try:
        columns = execute_readonly_query(
            columns_query, params=(schema_name, table), config=config)
        constraints = execute_readonly_query(
            constraints_query, params=(schema_name, table), config=config)

        return safe_json_dumps({
            "schema": schema_name,
            "table": table,
            "columns": columns,
            "constraints": constraints
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def list_postgres_extensions(config: RunnableConfig = None):
    """
    列出已安装的PostgreSQL扩展

    **何时使用此工具:**
    - 查看已安装的扩展列表
    - 了解扩展版本和功能

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含扩展列表
    """
    query = """
    SELECT 
        extname as extension_name,
        extversion as version,
        n.nspname as schema,
        c.description
    FROM pg_catalog.pg_extension e
    LEFT JOIN pg_catalog.pg_namespace n ON n.oid = e.extnamespace
    LEFT JOIN pg_catalog.pg_description c ON c.objoid = e.oid
    ORDER BY extname;
    """

    try:
        results = execute_readonly_query(query, config=config)

        return safe_json_dumps({
            "total_extensions": len(results),
            "extensions": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})


@tool()
def list_postgres_roles(config: RunnableConfig = None):
    """
    列出数据库角色(用户)信息

    **何时使用此工具:**
    - 查看所有角色列表
    - 了解角色权限和属性
    - 审计用户权限配置

    **工具能力:**
    - 列出所有角色
    - 显示角色属性(超级用户、创建DB、创建角色等)
    - 显示角色连接数限制

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含角色列表
    """
    query = """
    SELECT 
        rolname as role_name,
        rolsuper as is_superuser,
        rolcreatedb as can_create_db,
        rolcreaterole as can_create_role,
        rolcanlogin as can_login,
        rolconnlimit as connection_limit,
        rolvaliduntil as valid_until
    FROM pg_catalog.pg_roles
    ORDER BY rolname;
    """

    try:
        results = execute_readonly_query(query, config=config)

        # 格式化日期
        for row in results:
            row["valid_until"] = str(
                row["valid_until"]) if row["valid_until"] else "No expiration"

        return safe_json_dumps({
            "total_roles": len(results),
            "roles": results
        })
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
    - 列出所有配置参数及当前值
    - 显示参数的最小值、最大值
    - 显示参数来源(配置文件、命令行等)

    Args:
        config (RunnableConfig): 工具配置

    Returns:
        JSON格式,包含配置参数列表
    """
    query = """
    SELECT 
        name,
        setting,
        unit,
        category,
        short_desc as description,
        source,
        min_val,
        max_val
    FROM pg_catalog.pg_settings
    WHERE name IN (
        'shared_buffers', 'effective_cache_size', 'maintenance_work_mem', 
        'work_mem', 'max_connections', 'max_wal_size', 'checkpoint_timeout',
        'random_page_cost', 'effective_io_concurrency', 'max_worker_processes',
        'max_parallel_workers_per_gather', 'max_parallel_workers'
    )
    ORDER BY category, name;
    """

    try:
        results = execute_readonly_query(query, config=config)

        return safe_json_dumps({
            "total_settings": len(results),
            "settings": results
        })
    except Exception as e:
        return safe_json_dumps({"error": str(e)})
