"""PostgreSQL运维工具模块

这个模块包含了所有PostgreSQL相关的运维工具函数,按功能分类到不同的子模块中:
- resources: 基础资源查询工具(数据库/表/索引/角色等)
- dynamic: 动态SQL查询工具(安全的动态查询生成和执行)
- query: 高级查询分析工具(统计/膨胀/IO等)
- diagnostics: 故障诊断工具(慢查询/锁/连接/复制等)
- analysis: 配置分析工具(缓存/连接池/统计信息等)
- optimization: 性能优化建议工具(索引/配置/VACUUM等)
- tracing: 慢查询追踪和会话分析工具
- monitoring: 监控指标采集工具
- utils: 通用辅助函数
"""

# 工具集构造参数元数据
from apps.opspilot.metis.llm.tools.postgres.dynamic import (
    get_table_schema_details,
    search_tables_by_keyword,
    execute_safe_select,
    explain_query_plan,
    get_sample_data,
)
from apps.opspilot.metis.llm.tools.postgres.monitoring import (
    get_database_metrics,
    get_table_metrics,
    get_replication_metrics,
    get_bgwriter_stats,
    get_wal_metrics,
)
from apps.opspilot.metis.llm.tools.postgres.tracing import (
    get_top_queries,
    trace_lock_chain,
    get_active_sessions,
    analyze_query_pattern,
)
from apps.opspilot.metis.llm.tools.postgres.optimization import (
    check_unused_indexes,
    recommend_vacuum_strategy,
    recommend_index_optimization,
    check_configuration_tuning,
)
from apps.opspilot.metis.llm.tools.postgres.analysis import (
    analyze_cache_hit_ratio,
    analyze_connection_pool_usage,
    analyze_table_statistics,
    analyze_checkpoint_activity,
    analyze_transaction_patterns,
)
from apps.opspilot.metis.llm.tools.postgres.diagnostics import (
    diagnose_slow_queries,
    diagnose_lock_conflicts,
    diagnose_connection_issues,
    check_database_health,
    check_replication_lag,
    diagnose_autovacuum_issues,
    get_failed_transactions,
)
from apps.opspilot.metis.llm.tools.postgres.query import (
    query_table_stats,
    query_index_usage,
    query_bloat_analysis,
    query_table_io_stats,
    search_objects,
)
from apps.opspilot.metis.llm.tools.postgres.resources import (
    get_current_database_info,
    list_postgres_databases,
    list_postgres_tables,
    list_postgres_indexes,
    list_postgres_schemas,
    get_table_structure,
    list_postgres_extensions,
    list_postgres_roles,
    get_database_config,
)
from apps.opspilot.metis.llm.tools.postgres.utils import (
    prepare_context,
    format_size,
    format_duration,
    parse_pg_version,
    calculate_percentage,
)
CONSTRUCTOR_PARAMS = [
    {
        "name": "host",
        "type": "string",
        "required": False,
        "description": "PostgreSQL服务器地址,默认localhost"
    },
    {
        "name": "port",
        "type": "integer",
        "required": False,
        "description": "端口,默认5432"
    },
    {
        "name": "database",
        "type": "string",
        "required": False,
        "description": "默认连接的数据库。可选参数,不填时使用postgres数据库。大多数工具支持动态指定database参数来查询不同数据库"
    },
    {
        "name": "user",
        "type": "string",
        "required": False,
        "description": "用户名,默认postgres"
    },
    {
        "name": "password",
        "type": "string",
        "required": False,
        "description": "密码,从环境变量读取或配置传入"
    }
]

# 导入所有工具函数


__all__ = [
    # 构造参数
    "CONSTRUCTOR_PARAMS",

    # 基础资源查询工具 (P0)
    "get_current_database_info",  # 新增:获取当前数据库信息
    "list_postgres_databases",
    "list_postgres_tables",
    "list_postgres_indexes",
    "list_postgres_schemas",
    "get_table_structure",
    "list_postgres_extensions",
    "list_postgres_roles",
    "get_database_config",

    # 动态SQL查询工具 (P0) - 安全的动态查询生成和执行
    "get_table_schema_details",  # 获取表的详细结构信息
    "search_tables_by_keyword",  # 根据关键字搜索表和列
    "execute_safe_select",  # 执行安全的SELECT查询
    "explain_query_plan",  # 获取查询执行计划
    "get_sample_data",  # 获取表的示例数据

    # 高级查询分析工具 (P1)
    "query_table_stats",
    "query_index_usage",
    "query_bloat_analysis",
    "query_table_io_stats",
    "search_objects",

    # 故障诊断工具 (P0)
    "diagnose_slow_queries",
    "diagnose_lock_conflicts",
    "diagnose_connection_issues",
    "check_database_health",
    "check_replication_lag",
    "diagnose_autovacuum_issues",
    "get_failed_transactions",

    # 配置分析工具 (P1)
    "analyze_cache_hit_ratio",
    "analyze_connection_pool_usage",
    "analyze_table_statistics",
    "analyze_checkpoint_activity",
    "analyze_transaction_patterns",

    # 性能优化建议工具 (P1)
    "check_unused_indexes",
    "recommend_vacuum_strategy",
    "recommend_index_optimization",
    "check_configuration_tuning",

    # 慢查询追踪和会话分析工具 (P0)
    "get_top_queries",
    "trace_lock_chain",
    "get_active_sessions",
    "analyze_query_pattern",

    # 监控指标采集工具 (P1)
    "get_database_metrics",
    "get_table_metrics",
    "get_replication_metrics",
    "get_bgwriter_stats",
    "get_wal_metrics",

    # 通用工具函数
    "prepare_context",
    "format_size",
    "format_duration",
    "parse_pg_version",
    "calculate_percentage",
]
