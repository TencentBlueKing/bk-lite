"""运营分析通用查询在 CMDB 侧的执行上限。

超限直接失败，不截断、不把超出的部分夹进结果。
"""

# 明细每页最多 100 条。
DETAIL_PAGE_SIZE_MAX = 100

# 分布、聚合等统计分组最多 500 组。
STAT_GROUP_MAX = 500

# 模型 / 实例统计前，扫描实例最多 5 万。
SCAN_INSTANCE_MAX = 50_000

# 图查询超时（毫秒）。FalkorDB 使用该值；Neo4j 事务使用 30 秒。
QUERY_TIMEOUT_MS = 30_000

# 平台 NATS 默认消息上限 1MB。
NATS_MESSAGE_MAX_BYTES = 1_048_576
