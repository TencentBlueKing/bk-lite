"""MySQL运维工具模块

这个模块包含了所有MySQL相关的运维工具函数,按功能分类到不同的子模块中:
- resources: 基础资源查询工具(数据库/表/索引/用户等)
- dynamic: 动态SQL查询工具(安全的动态查询生成和执行)
- diagnostics: 故障诊断工具(慢查询/锁/连接/复制等)
- monitoring: 监控指标采集工具
- optimization: 优化建议工具(索引/碎片/配置)
- analysis: 性能分析工具(缓冲池/查询模式/表统计)
- utils: 通用辅助函数
- connection: 多实例连接管理
"""

# 工具集构造参数元数据
CONSTRUCTOR_PARAMS = [
    {"name": "mysql_instances", "type": "string", "required": False, "description": "MySQL多实例JSON配置"},
    {"name": "mysql_default_instance_id", "type": "string", "required": False, "description": "默认MySQL实例ID"},
]

# 性能分析工具
from apps.opspilot.metis.llm.tools.mysql.analysis import analyze_buffer_pool_usage, analyze_query_patterns, analyze_table_statistics  # noqa: E402

# 故障诊断工具
from apps.opspilot.metis.llm.tools.mysql.diagnostics import (  # noqa: E402
    check_database_health,
    check_replication_lag,
    diagnose_connection_issues,
    diagnose_deadlocks,
    diagnose_lock_conflicts,
    diagnose_slow_queries,
    get_failed_queries,
)

# 动态SQL查询工具
from apps.opspilot.metis.llm.tools.mysql.dynamic import (  # noqa: E402
    execute_safe_select,
    explain_query_plan,
    get_sample_data,
    get_table_schema_details,
    search_tables_by_keyword,
)

# 监控指标采集工具
from apps.opspilot.metis.llm.tools.mysql.monitoring import (  # noqa: E402
    check_binary_log_status,
    check_database_size_growth,
    check_replication_status,
    get_database_metrics,
    get_innodb_stats,
    get_io_stats,
    get_processlist,
    get_table_metrics,
)

# 优化建议工具
from apps.opspilot.metis.llm.tools.mysql.optimization import (  # noqa: E402
    check_configuration_tuning,
    check_table_fragmentation,
    check_unused_indexes,
    recommend_index_optimization,
)

# 基础资源查询工具
from apps.opspilot.metis.llm.tools.mysql.resources import (  # noqa: E402
    get_current_database_info,
    get_database_config,
    get_table_structure,
    list_mysql_databases,
    list_mysql_indexes,
    list_mysql_schemas,
    list_mysql_tables,
    list_mysql_users,
)

# 通用工具函数
from apps.opspilot.metis.llm.tools.mysql.utils import (  # noqa: E402
    calculate_percentage,
    format_duration,
    format_size,
    parse_mysql_version,
    prepare_context,
    safe_json_dumps,
)

__all__ = [
    # 构造参数
    "CONSTRUCTOR_PARAMS",
    # 基础资源查询工具
    "get_current_database_info",
    "list_mysql_databases",
    "list_mysql_tables",
    "list_mysql_indexes",
    "list_mysql_schemas",
    "get_table_structure",
    "list_mysql_users",
    "get_database_config",
    # 动态SQL查询工具
    "get_table_schema_details",
    "search_tables_by_keyword",
    "execute_safe_select",
    "explain_query_plan",
    "get_sample_data",
    # 故障诊断工具
    "diagnose_slow_queries",
    "diagnose_lock_conflicts",
    "diagnose_connection_issues",
    "check_database_health",
    "check_replication_lag",
    "diagnose_deadlocks",
    "get_failed_queries",
    # 监控指标采集工具
    "get_database_metrics",
    "get_table_metrics",
    "get_innodb_stats",
    "get_io_stats",
    "check_binary_log_status",
    "check_replication_status",
    "get_processlist",
    "check_database_size_growth",
    # 优化建议工具
    "check_unused_indexes",
    "recommend_index_optimization",
    "check_table_fragmentation",
    "check_configuration_tuning",
    # 性能分析工具
    "analyze_buffer_pool_usage",
    "analyze_query_patterns",
    "analyze_table_statistics",
    # 通用工具函数
    "prepare_context",
    "format_size",
    "format_duration",
    "parse_mysql_version",
    "safe_json_dumps",
    "calculate_percentage",
]
