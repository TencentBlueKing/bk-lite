"""监控视图实例列表全局排序的规模门槛。"""

# 候选实例超过该值时拒绝排序（明确失败，不退回本页假排序）。
ORDERING_MAX_CANDIDATES = 2000

# 单列全量取数的分批大小；N ≤ 该值时一次查完，更大则按批合并。
ORDERING_METRIC_BATCH_SIZE = 500
