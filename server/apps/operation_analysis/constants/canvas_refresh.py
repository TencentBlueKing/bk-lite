# -- coding: utf-8 --
"""分析画布周期刷新间隔（毫秒）。"""

from apps.operation_analysis.constants.import_export import ObjectType

CANVAS_REFRESH_INTERVAL_MS = (0, 60_000, 300_000, 600_000)
DEFAULT_CANVAS_REFRESH_INTERVAL_MS = 0
LEGACY_NETWORK_TOPOLOGY_REFRESH_SECONDS = 60
CANVAS_REFRESH_OBJECT_TYPES = frozenset(
    {
        ObjectType.DASHBOARD,
        ObjectType.TOPOLOGY,
        ObjectType.SCREEN,
        ObjectType.REPORT,
        ObjectType.NETWORK_TOPOLOGY,
    }
)


def normalize_canvas_refresh_interval(value) -> int:
    """读取或导入时把缺省/非法值（含旧秒语义 60）归一为关。"""
    try:
        interval = int(value)
    except (TypeError, ValueError):
        return DEFAULT_CANVAS_REFRESH_INTERVAL_MS
    # 旧网络拓扑默认 60 秒，不得解释成 60ms 或 1 分钟。
    if interval == LEGACY_NETWORK_TOPOLOGY_REFRESH_SECONDS:
        return DEFAULT_CANVAS_REFRESH_INTERVAL_MS
    if interval in CANVAS_REFRESH_INTERVAL_MS:
        return interval
    return DEFAULT_CANVAS_REFRESH_INTERVAL_MS
