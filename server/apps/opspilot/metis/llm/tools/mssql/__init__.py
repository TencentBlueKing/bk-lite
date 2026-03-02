"""MSSQL运维工具模块

这个模块包含了所有MSSQL相关的运维工具函数,按功能分类到不同的子模块中:
- resources: 基础资源查询工具(数据库/表/索引/角色等)
- dynamic: 动态SQL查询工具(安全的动态查询生成和执行)
- diagnostics: 故障诊断工具(慢查询/锁/连接/复制等)
- monitoring: 监控指标采集工具
- utils: 通用辅助函数
"""

# 工具集构造参数元数据
CONSTRUCTOR_PARAMS = [
    {"name": "host", "type": "string", "required": False, "description": "MSSQL服务器地址,默认localhost"},
    {"name": "port", "type": "integer", "required": False, "description": "端口,默认1433"},
    {
        "name": "database",
        "type": "string",
        "required": False,
        "description": "默认连接的数据库。可选参数,不填时使用master数据库。大多数工具支持动态指定database参数来查询不同数据库",
    },
    {"name": "user", "type": "string", "required": False, "description": "用户名,默认sa"},
    {"name": "password", "type": "string", "required": False, "description": "密码,从环境变量读取或配置传入"},
]

# 导入所有工具函数

# 故障诊断工具
from apps.opspilot.metis.llm.tools.mssql.diagnostics import (  # noqa: E402
    check_database_health,
    check_replication_lag,
    diagnose_connection_issues,
    diagnose_deadlocks,
    diagnose_lock_conflicts,
    diagnose_slow_queries,
    get_failed_queries,
)

# 动态SQL查询工具
from apps.opspilot.metis.llm.tools.mssql.dynamic import (  # noqa: E402
    execute_safe_select,
    explain_query_plan,
    get_sample_data,
    get_table_schema_details,
    search_tables_by_keyword,
)

# 监控指标采集工具
from apps.opspilot.metis.llm.tools.mssql.monitoring import (  # noqa: E402
    check_agent_jobs,
    check_backup_status,
    check_database_size_growth,
    check_replication_status,
    get_database_metrics,
    get_instance_metrics,
    get_io_stats,
    get_table_metrics,
    get_wait_stats,
)

# 基础资源查询工具
from apps.opspilot.metis.llm.tools.mssql.resources import (  # noqa: E402
    get_current_database_info,
    get_database_config,
    get_table_structure,
    list_mssql_databases,
    list_mssql_indexes,
    list_mssql_logins,
    list_mssql_schemas,
    list_mssql_tables,
)

# 通用工具函数
from apps.opspilot.metis.llm.tools.mssql.utils import (  # noqa: E402
    calculate_percentage,
    format_duration,
    format_size,
    parse_mssql_version,
    prepare_context,
)

__all__ = [
    # 构造参数
    "CONSTRUCTOR_PARAMS",
    # 基础资源查询工具 (P0)
    "get_current_database_info",
    "list_mssql_databases",
    "list_mssql_tables",
    "list_mssql_indexes",
    "list_mssql_schemas",
    "get_table_structure",
    "list_mssql_logins",
    "get_database_config",
    # 动态SQL查询工具 (P0) - 安全的动态查询生成和执行
    "get_table_schema_details",
    "search_tables_by_keyword",
    "execute_safe_select",
    "explain_query_plan",
    "get_sample_data",
    # 故障诊断工具 (P0)
    "diagnose_slow_queries",
    "diagnose_lock_conflicts",
    "diagnose_connection_issues",
    "check_database_health",
    "check_replication_lag",
    "diagnose_deadlocks",
    "get_failed_queries",
    # 监控指标采集工具 (P1)
    "get_database_metrics",
    "get_table_metrics",
    "get_wait_stats",
    "get_instance_metrics",
    "get_io_stats",
    "check_backup_status",
    "check_agent_jobs",
    "check_replication_status",
    "check_database_size_growth",
    # 通用工具函数
    "prepare_context",
    "format_size",
    "format_duration",
    "parse_mssql_version",
    "calculate_percentage",
]
