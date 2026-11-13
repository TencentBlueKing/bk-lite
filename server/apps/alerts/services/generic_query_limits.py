"""运营分析通用查询在告警中心侧的执行上限。"""

# 明细每页最多 100 条。
DETAIL_PAGE_SIZE_MAX = 100

# 统计分组最多 500 组。
STAT_GROUP_MAX = 500

# 时间范围必填，最长 90 天。
RANGE_MAX_DAYS = 90
RANGE_MAX_SECONDS = 90 * 24 * 60 * 60

# 平台 NATS 默认消息上限 1MB。
NATS_MESSAGE_MAX_BYTES = 1_048_576
