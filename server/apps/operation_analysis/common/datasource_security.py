"""运营分析数据源的安全退役边界。"""

LEGACY_RAW_MONITOR_QUERY_ROUTES = frozenset(
    {
        "monitor/mm_query",
        "monitor/mm_query_range",
    }
)
LEGACY_RAW_MONITOR_QUERY_ERROR = "该监控裸查询接口已停止新增，仅保留存量数据源兼容"


def is_legacy_raw_monitor_query(*, source_type: str, rest_api: str) -> bool:
    """判断数据源是否直连未按监控实例权限收口的历史查询入口。"""
    return source_type == "nats" and rest_api in LEGACY_RAW_MONITOR_QUERY_ROUTES
