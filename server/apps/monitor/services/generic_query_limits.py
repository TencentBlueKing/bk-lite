"""运营分析通用查询在监控侧的执行上限。"""

# 明细每页最多 100 条。
DETAIL_PAGE_SIZE_MAX = 100

# 统计分组最多 500 组。
STAT_GROUP_MAX = 500

# 单次指标查询最多 50 个实例。
METRIC_INSTANCE_MAX = 50

# 指标查询最多返回 20 条序列。
METRIC_SERIES_MAX = 20

# 每条序列最多 1000 个点。query_range 闭区间包含起止两端，点数上界是
# floor(时间范围秒 / 步长) + 1。请求校验与 VictoriaMetrics 实际返回用同一公式。
METRIC_POINTS_MAX = 1000

# 监控告警时间范围最长 90 天。
ALERT_RANGE_MAX_DAYS = 90
ALERT_RANGE_MAX_SECONDS = 90 * 24 * 60 * 60

# 平台 NATS 默认消息上限 1MB。指标读超时不在这里另设，沿用
# VictoriaMetricsConstants.REQUEST_TIMEOUT 的 15 秒。
NATS_MESSAGE_MAX_BYTES = 1_048_576
